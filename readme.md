# jenkins-ml-demo

A small but complete CI/CD pipeline for a machine learning model, built with
Jenkins and Docker. The point of this project is a single idea: in ML systems,
passing tests is not enough. The code can be fine, the container can be clean,
and the model can still be garbage. This pipeline puts a quality gate on the
model itself and refuses to ship anything below the bar.

```
git push --> Jenkins --> Train      (produces model.pkl)
                     --> Evaluate   (accuracy < 0.90 = build fails)
                     --> Package    (model baked into the serving image)
                     --> Scan       (Trivy, critical vulnerabilities)
                     --> Smoke      (real predictions against the container)
                     --> Publish    (image pushed to Docker Hub)

metrics.json is archived on every build, including failed ones.
```

The model is a deliberately simple LogisticRegression on a synthetic 2D
dataset. That is on purpose. The interesting part is not the model, it is
the pipeline around it.

## Why a metric gate matters

The training config (`train_config.json`) contains a `label_noise` knob that
simulates the quality of a training data batch. With the default value of
0.05 the model reaches 0.95 accuracy on 200 held-out samples. Change it to
0.4 (a bad data batch) and accuracy drops to 0.54.

Here is the thing: with the bad batch, training still exits cleanly. Unit
tests would pass. The vulnerability scan would pass. Every conventional CI
signal is green. Only the Evaluate stage, which measures the model against
held-out data and applies a threshold in the Jenkinsfile, knows the model is
broken. It fails the build, the bad model never even gets containerized, and
the archived metrics.json shows exactly how bad it was.

That is the entire reason ML CI exists, and this repo demonstrates it in a
form you can run on a laptop.

## What is in the repo

| File                | Purpose                                                            |
|---------------------|--------------------------------------------------------------------|
| `data.py`           | Synthetic dataset generator, fixed seed, contains the noise knob  |
| `train.py`          | Trains LogisticRegression, writes `model.pkl`                     |
| `evaluate.py`       | Accuracy on 200 held-out samples, writes `metrics.json`           |
| `train_config.json` | Training configuration, versioned in git as a build input         |
| `app.py`            | FastAPI service serving the model (`/health`, `/predict`)         |
| `requirements.txt`  | All dependencies, pinned                                          |
| `Dockerfile.train`  | The training environment image                                    |
| `Dockerfile`        | The serving image, runs as non-root                               |
| `smoke-test.sh`     | Starts the container and asserts two known predictions            |
| `Jenkinsfile`       | The six-stage pipeline, including the Groovy metric gate          |

`model.pkl` and `metrics.json` are build outputs. They are in `.gitignore`
and must never be committed. The config that produced them is committed;
the artifacts themselves belong to the build.

## Prerequisites

- Docker Desktop (or Colima) running on your machine
- git
- A GitHub account (any git host works, the instructions assume GitHub)
- A Docker Hub account, only if you want the Publish stage

Everything else, including Python and all libraries, runs inside containers.
You do not need Python installed on the host.

## Step 1: Verify the project locally, before Jenkins

Never debug two things at once. Prove the project works on its own, then
add Jenkins on top.

```bash
git clone https://github.com/manishsinghkuswaha/jenkins-ml-demo.git
cd jenkins-ml-demo

# Train and Evaluate stages, by hand:
docker build -f Dockerfile.train -t inference-trainer .
docker run --rm -v "$PWD":/work -w /work inference-trainer python train.py
docker run --rm -v "$PWD":/work -w /work inference-trainer python evaluate.py
#   -> accuracy on 200 held-out samples: 0.95

# Package and Smoke stages, by hand:
docker build -t inference:ci .
bash smoke-test.sh inference:ci
#   -> predict(2,2)   -> {"prediction":1, ...}
#   -> predict(-2,-2) -> {"prediction":0, ...}
#   -> SMOKE TEST PASSED
```

The first trainer build takes a few minutes while pip installs scikit-learn.
Every build after that reuses the cached layer and is nearly instant, since
the code is copied in at run time and never invalidates the dependency layer.

## Step 2: Run Jenkins with the Docker CLI

This is the step most guides skip, and it is the one that will burn you:
the official Jenkins image does not contain the `docker` command. Mounting
the Docker socket gives Jenkins a phone line to the engine, but it still
needs the phone. So we build a small custom image.

Create a separate folder, for example `~/jenkins/`, with two files.

`~/jenkins/Dockerfile`:

```dockerfile
FROM jenkins/jenkins:lts-jdk17

USER root
RUN apt-get update && apt-get install -y docker.io curl && apt-get clean
USER jenkins
```

`~/jenkins/compose.yaml`:

```yaml
services:
  jenkins:
    build: .
    user: root          # lab shortcut, see note below
    ports:
      - "8080:8080"
      - "50000:50000"
    volumes:
      - jenkins_home:/var/jenkins_home
      - /var/run/docker.sock:/var/run/docker.sock

volumes:
  jenkins_home: {}
```

A note on `user: root`: this is a lab shortcut that avoids docker.sock
permission problems, which vary between Docker Desktop, Colima and Linux.
Production setups use build agents with proper docker group membership
instead. For a laptop lab this trade is worth it.

If port 8080 is already taken on your machine, change the mapping to
something like `"9090:8080"` and use localhost:9090 everywhere below.

Start it and fetch the initial admin password:

```bash
cd ~/jenkins
docker compose up -d --build
docker compose exec jenkins cat /var/jenkins_home/secrets/initialAdminPassword
```

Open http://localhost:8080, paste the password, choose "Install suggested
plugins" and create your admin user. The suggested set includes everything
this pipeline needs (Pipeline and Git plugins).

## Step 3: Create the pipeline job

1. Jenkins, New Item, name it `ml-inference-pipeline`, type Pipeline, OK.
2. Scroll to the Pipeline section. Definition: "Pipeline script from SCM".
   This is the pipeline-as-code option; the Jenkinsfile lives in git,
   not in the Jenkins UI.
3. SCM: Git. Repository URL: your fork or clone of this repo (HTTPS).
   A public repo needs no credentials.
4. Branch: `*/main`. Script Path: `Jenkinsfile`. Save.
5. Build Now.

The first run is slow: the trainer image builds from scratch and Trivy
downloads its vulnerability database. Subsequent runs take well under a
minute. Watch the stage view fill in, then open the build page and find
`metrics.json` under Build Artifacts. That file is the model quality
report, attached to the build permanently.

## Step 4: Add the trigger

Job, Configure, Build Triggers, check "Poll SCM", schedule:

```
H/5 * * * *
```

Save. Now commit any small change, push, and touch nothing in Jenkins.
Within five minutes a build starts by itself, labeled "Started by an SCM
change".

Polling is used instead of webhooks because a Jenkins on localhost is not
reachable from github.com. If you want push-triggered builds with no delay,
expose Jenkins through a tunnel such as ngrok and configure a webhook.

## Step 5: Break the model on purpose

This is the demo that justifies the whole setup. The break lever is one
number in a committed config file:

```bash
# simulate a bad training data batch:
echo '{"label_noise": 0.4}' > train_config.json
git commit -am "retrain with new data batch" && git push
```

Wait for the poll. Train goes green, training "worked". Evaluate goes red:

```
model accuracy: 0.54
ERROR: model accuracy 0.54 below 0.90 - NOT shipping
```

Package, Scan and Smoke are skipped. The bad model never got containerized.
metrics.json is still archived, because artifact archiving runs in a
`post { always }` block, so you can open the failed build and see exactly
how bad the model was.

Then recover:

```bash
echo '{"label_noise": 0.05}' > train_config.json
git commit -am "fix training data" && git push
```

Green across the board. The red build stays in the history next to the
green ones, which is exactly what you want to show people.

## Step 6 (optional): Publish to Docker Hub

1. On hub.docker.com: Account Settings, Personal access tokens, generate
   a token with read and write scope.
2. In Jenkins: Manage Jenkins, Credentials, add a "Username with password"
   credential. Username is your Docker Hub username (not email), password
   is the token. The ID must be exactly `dockerhub-token`, because the
   Jenkinsfile references it by that ID.
3. The Publish stage in this repo's Jenkinsfile is already enabled. If you
   forked an older revision where it is commented out, uncomment it and push.

Each successful build then pushes `<your-user>/inference:<build-number>`
and `<your-user>/inference:latest`. Anyone can run the result:

```bash
docker run -d -p 8000:8000 <your-user>/inference:latest
curl "http://localhost:8000/predict?x1=2&x2=2"
```

## Implementation notes worth knowing

These are the details that took actual debugging and are easy to miss.

**Workspace volume mounts do not work from inside Jenkins.** The pipeline
talks to the host Docker engine through the mounted socket, so any `-v`
path in a `docker run` is resolved on the engine host, not inside the
Jenkins container. The Jenkins workspace lives in a named volume, so the
path simply does not exist on the host and the mount comes up empty, with
no error. The Jenkinsfile therefore avoids mounts entirely: it keeps one
helper container alive for Train and Evaluate, copies files in and out
with `docker cp`, and runs the scripts with `docker exec`. The local
commands in Step 1 use `-v` because on your laptop the paths do exist.

**The smoke test makes requests from inside the container.** For the same
reason, a port published by a container the pipeline starts is published
on the Docker host, not reachable as localhost from inside Jenkins. The
smoke test uses `docker exec` with Python's urllib, which behaves the same
on a laptop and inside Jenkins.

**metrics.json is copied out before the gate check.** Order matters in the
Evaluate stage: first run the evaluation, then copy the metrics out, then
apply the threshold. Doing it in that order is what makes the quality
report available even on failed builds.

**The training config is a build input.** Changing `train_config.json` and
pushing is what retrains the model. This is the core ML CI lesson: data
and configuration changes are code changes, and they go through the same
pipeline and the same gate.

**Everything is pinned.** requirements.txt pins every library including
scipy. An unpinned transitive dependency once produced a scary-looking
sklearn warning in the middle of the training output; pinning removed it
and keeps builds reproducible over time.

## Troubleshooting

- "docker: command not found" in a Jenkins build log: you are running the
  stock Jenkins image. Rebuild with the custom Dockerfile from Step 2.
- Permission denied on /var/run/docker.sock: the compose file runs the
  container as root to avoid this. If you removed `user: root`, put it
  back or set up docker group membership properly.
- Trainer runs but model.pkl does not appear (Jenkins only): you replaced
  the `docker cp` pattern with a `-v` mount. See the implementation notes.
- The Trivy stage fails on vulnerabilities: the gate is set to critical,
  unfixed excluded. If a new critical CVE lands in the base image, update
  the base image tag in both Dockerfiles.
- First build extremely slow: expected. Trainer image build plus Trivy DB
  download. Watch the second build to see the cache working.

## Author

Aditya Devan

LinkedIn: https://www.linkedin.com/in/aditya-devan-72a4832b7/

Questions and suggestions are welcome, open an issue or reach out.
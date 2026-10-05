
````markdown
# jenkins-ml-demo

A complete CI/CD and Kubernetes deployment pipeline for a small machine-learning
inference service using **Jenkins, Docker, Docker Hub, and Kubernetes/Minikube**.

The project demonstrates an important ML CI/CD principle:

> Passing software tests is not enough. The model itself must satisfy a quality
> threshold before it is packaged and shipped.

The project starts with a simple LogisticRegression model and focuses on the
**DevOps pipeline around the model**, rather than the ML algorithm itself.

---

## Architecture

```text
                    Developer
                        |
                        | git push
                        v
                     GitHub
                        |
                        v
                     Jenkins
                        |
        +---------------+----------------+
        |               |                |
      Train          Evaluate          Quality
        |               |                | Gate
    model.pkl      metrics.json       accuracy >= 0.90
        |               |
        +---------------+
                |
             Package
                |
          inference:ci
                |
             Trivy
          Security Scan
                |
             Smoke Test
                |
             Publish
                |
                v
            Docker Hub
                |
                |
                v
          Minikube Cluster
                |
                v
        Pod: inference
                |
        FastAPI :8000
                |
                v
      ClusterIP Service :80
                |
                v
       kubectl port-forward
                |
                v
        localhost:8080
                |
                v
          /predict
````

---

# ML CI/CD Pipeline

The Jenkins pipeline consists of the following stages:

```text
Train
  ↓
Evaluate
  ↓
Quality Gate
  ↓
Package
  ↓
Trivy Scan
  ↓
Smoke Test
  ↓
Publish
```

`metrics.json` is archived on every Jenkins build, including failed builds.

The quality gate prevents a model with accuracy below `0.90` from moving to
the packaging and deployment stages.

---

## Why a metric gate matters

The training configuration contains a `label_noise` parameter that simulates
the quality of a training data batch.

With:

```json
{
  "label_noise": 0.05
}
```

the model reaches approximately:

```text
Accuracy = 0.95
```

on 200 held-out samples.

Changing the configuration to:

```json
{
  "label_noise": 0.4
}
```

produces approximately:

```text
Accuracy = 0.54
```

The training process itself still completes successfully.

This demonstrates why traditional CI checks are not sufficient for ML systems.

The Jenkins pipeline evaluates the model against held-out data and applies:

```text
accuracy >= 0.90
```

If the model fails the gate:

```text
Evaluate ❌
    ↓
Package skipped
Scan skipped
Smoke skipped
Publish skipped
```

`metrics.json` is still archived so the failed model's quality can be
inspected.

---

# Project Structure

```text
jenkins-ml-demo/
│
├── app.py
├── data.py
├── evaluate.py
├── train.py
├── train_config.json
├── requirements.txt
│
├── Dockerfile
├── Dockerfile.train
├── smoke-test.sh
├── Jenkinsfile
├── .gitignore
│
└── k8s/
    └── pod.yaml
```

### Important files

| File                | Purpose                                                         |
| ------------------- | --------------------------------------------------------------- |
| `data.py`           | Generates the reproducible synthetic dataset                    |
| `train.py`          | Trains LogisticRegression and creates `model.pkl`               |
| `evaluate.py`       | Evaluates the model on held-out data and creates `metrics.json` |
| `train_config.json` | Versioned training configuration                                |
| `app.py`            | FastAPI inference service                                       |
| `requirements.txt`  | Pinned Python dependencies                                      |
| `Dockerfile.train`  | Training environment                                            |
| `Dockerfile`        | Production/serving image                                        |
| `smoke-test.sh`     | Tests the running inference container                           |
| `Jenkinsfile`       | Complete Jenkins CI/CD pipeline                                 |
| `k8s/pod.yaml`      | Kubernetes Pod definition                                       |

`model.pkl` and `metrics.json` are generated build artifacts and are excluded
from Git using `.gitignore`.

---

# Local Verification

Before introducing Jenkins, the complete pipeline was verified manually.

### Build the training image

```bash
docker build -f Dockerfile.train -t inference-trainer .
```

### Train

```bash
docker run --rm \
  -v "$PWD":/work \
  -w /work \
  inference-trainer \
  python train.py
```

Expected:

```text
trained LogisticRegression on 800 samples -> model.pkl
```

### Evaluate

```bash
docker run --rm \
  -v "$PWD":/work \
  -w /work \
  inference-trainer \
  python evaluate.py
```

Expected:

```text
accuracy on 200 held-out samples: 0.95
```

### Build serving image

```bash
docker build -t inference:ci .
```

### Run smoke test

```bash
./smoke-test.sh inference:ci
```

Expected:

```text
predict(2,2) -> {"prediction":1,...}
predict(-2,-2) -> {"prediction":0,...}
SMOKE TEST PASSED
```

---

# Jenkins Setup

Jenkins runs inside Docker using a custom Jenkins image containing the Docker
CLI.

The Jenkins container communicates with the host Docker daemon through:

```text
/var/run/docker.sock
```

This is **Docker-outside-of-Docker**, rather than running a separate Docker
daemon inside Jenkins.

## Jenkins infrastructure

The Jenkins setup is kept separately from the application repository:

```text
~/jenkins/
```

The project itself lives in:

```text
~/jenkins-ml-demo/
```

The Jenkins container uses:

```yaml
volumes:
  - jenkins_home:/var/jenkins_home
  - /var/run/docker.sock:/var/run/docker.sock
```

The custom Jenkins image installs:

```text
Docker CLI
curl
```

This allows Jenkins pipeline stages to build, run, and inspect Docker
containers.

---

# Jenkins Pipeline

The Jenkinsfile contains the complete CI/CD flow.

## 1. Train

Jenkins builds the training image:

```bash
docker build --pull -f Dockerfile.train -t inference-trainer .
```

A temporary workbench container is created.

Because Jenkins uses the host Docker socket, the pipeline uses `docker cp`
instead of bind-mounting the Jenkins workspace.

The training script produces:

```text
model.pkl
```

---

## 2. Evaluate

Jenkins runs:

```bash
python evaluate.py --print-accuracy
```

The accuracy is captured by Groovy and converted into a number.

Example:

```text
model accuracy: 0.95
```

The pipeline then applies:

```text
accuracy >= 0.90
```

If the accuracy is below the threshold, Jenkins fails the build.

---

## 3. Package

The trained model is baked into the serving Docker image:

```text
inference:ci
```

The serving image contains:

```text
FastAPI
model.pkl
requirements
app.py
```

The container runs as a non-root user.

---

## 4. Security Scan

Trivy scans the Docker image for vulnerabilities.

The pipeline is configured to fail when unfixed-excluded **CRITICAL**
vulnerabilities are detected.

This prevents a vulnerable image from automatically progressing through the
pipeline.

---

## 5. Smoke Test

The smoke test starts the packaged inference image and checks:

```text
/health
```

and known predictions:

```text
(2,2)     → prediction 1
(-2,-2)   → prediction 0
```

---

## 6. Publish

Successful builds publish the image to Docker Hub using:

```text
<dockerhub-user>/inference:<build-number>
<dockerhub-user>/inference:latest
```

The Docker Hub credential is stored in Jenkins as:

```text
Credential ID: dockerhub-token
```

The Docker Hub access token is stored as a Jenkins secret rather than being
written directly into the Jenkinsfile.

---

# Jenkins Trigger

The Jenkins job uses:

```text
Poll SCM
```

with:

```text
H/5 * * * *
```

Jenkins checks the Git repository approximately every five minutes and starts
a build when it detects a change.

Polling is used because the Jenkins instance runs locally and is not directly
reachable by GitHub webhooks.

---

# Kubernetes Deployment

After Jenkins successfully publishes:

```text
adityadevan/inference:latest
```

the image is deployed to a local Kubernetes cluster using **Minikube**.

The Minikube cluster used for this project:

```text
Kubernetes: v1.37.0
Container runtime: containerd
Driver: Docker
```

The cluster contains a single control-plane node:

```text
minikube
```

---

# Kubernetes Pod

The application is deployed using:

```text
k8s/pod.yaml
```

The Pod uses:

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: inference
  labels:
    app: inference
spec:
  containers:
    - name: api
      image: adityadevan/inference:latest
      ports:
        - containerPort: 8000
```

The image is pulled from Docker Hub by Kubernetes.

The resulting architecture is:

```text
Minikube
   |
   └── Pod: inference
          |
          └── Container: api
                 |
                 └── FastAPI :8000
```

The Pod successfully reached:

```text
READY: 1/1
STATUS: Running
```

---

# Kubernetes Service

The Pod is exposed using a Kubernetes **ClusterIP Service**:

```bash
kubectl expose pod inference \
  --port=80 \
  --target-port=8000 \
  --name=inference-svc
```

The Service was verified with:

```bash
kubectl get svc inference-svc
```

The resulting Service:

```text
Type: ClusterIP
Port: 80
Target Port: 8000
```

The networking flow is:

```text
Service :80
    |
    | target-port
    v
Pod :8000
    |
    v
FastAPI
```

`80` is the Service port.

`8000` is the port where the FastAPI application is listening inside the
container.

The Service is not a NodePort and does not expose the Minikube node directly.

---

# Accessing the Kubernetes Application

A temporary port-forward is used to access the ClusterIP Service from the
local machine:

```bash
kubectl port-forward svc/inference-svc 8080:80
```

The complete request path becomes:

```text
localhost:8080
      |
      v
Service :80
      |
      v
Pod :8000
      |
      v
FastAPI
      |
      v
ML Model
```

Test the model:

```bash
curl 'localhost:8080/predict?x1=2&x2=2'
```

Expected:

```json
{
  "prediction": 1,
  "confidence": 0.9998
}
```

Test another input:

```bash
curl 'localhost:8080/predict?x1=-2&x2=-2'
```

Expected:

```json
{
  "prediction": 0,
  "confidence": 0.9998
}
```

This confirms that the same inference image produced by the CI/CD pipeline
can be deployed and executed inside Kubernetes.

---

# End-to-End Flow

The complete project flow is now:

```text
Developer
    |
    | git push
    v
GitHub
    |
    v
Jenkins
    |
    +--> Train
    |
    +--> Evaluate
    |       |
    |       +--> accuracy >= 0.90
    |
    +--> Package
    |
    +--> Trivy Scan
    |
    +--> Smoke Test
    |
    +--> Publish
             |
             v
        Docker Hub
             |
             v
         Minikube
             |
             v
        Pod: inference
             |
             v
     ClusterIP Service
             |
             v
     localhost:8080
             |
             v
        FastAPI
             |
             v
       ML Prediction
```

---

# Important Implementation Notes

## Jenkins workspace and Docker mounts

Jenkins communicates with the host Docker engine through the Docker socket.

Therefore, a path such as:

```text
/var/jenkins_home/workspace/jenkins-ml-demo
```

exists inside the Jenkins container and should not be assumed to exist at the
same path on the Docker engine host.

The Jenkins pipeline therefore uses:

```text
docker cp
docker exec
```

for the training/evaluation workbench instead of relying on Jenkins workspace
bind mounts.

---

## Training artifacts

The training stage creates:

```text
model.pkl
```

The evaluation stage creates:

```text
metrics.json
```

These files are generated artifacts.

They are not committed to Git.

The configuration that produces them:

```text
train_config.json
```

is committed because it is a versioned build input.

---

## Reproducibility

The project pins Python dependencies in:

```text
requirements.txt
```

The synthetic dataset uses a fixed random seed.

This makes the training and evaluation process reproducible across builds.

---

# Kubernetes Commands Used

Start Minikube:

```bash
minikube start
```

Check cluster:

```bash
minikube status
kubectl get nodes
kubectl get pods -A
```

Deploy Pod:

```bash
kubectl apply -f k8s/pod.yaml
```

Check Pod:

```bash
kubectl get pods
kubectl describe pod inference
```

Create Service:

```bash
kubectl expose pod inference \
  --port=80 \
  --target-port=8000 \
  --name=inference-svc
```

Check Service:

```bash
kubectl get svc inference-svc
```

Forward the Service:

```bash
kubectl port-forward svc/inference-svc 8080:80
```

Test inference:

```bash
curl 'localhost:8080/predict?x1=2&x2=2'
curl 'localhost:8080/predict?x1=-2&x2=-2'
```

---

# Troubleshooting

### Docker command not found in Jenkins

The Jenkins image needs the Docker CLI.

Rebuild the custom Jenkins image.

### Permission denied on Docker socket

The lab setup uses:

```yaml
user: root
```

to avoid Docker socket permission issues.

Production environments should use proper Docker group/agent configuration
instead.

### Trivy reports CRITICAL vulnerabilities

Rebuild the image using the latest base image:

```bash
docker build --pull --no-cache -t inference:ci .
```

Then run the Trivy scan again.

The Jenkins pipeline also uses `--pull` when building the Docker images so
the latest available base image can be checked.

### Pod does not start

Check:

```bash
kubectl get pods
kubectl describe pod inference
```

Pay particular attention to the `Events` section.

### Check application logs

```bash
kubectl logs inference
```

### Service not responding

Check:

```bash
kubectl get svc
kubectl get pods
```

Then verify the port-forward:

```bash
kubectl port-forward svc/inference-svc 8080:80
```

---

# Current Project Status

The following parts have been successfully implemented and verified:

```text
Docker training image                 ✅
Local model training                  ✅
Local model evaluation               ✅
Accuracy quality gate                ✅
Serving Docker image                 ✅
Container smoke test                 ✅
Jenkins CI pipeline                  ✅
Trivy security gate                  ✅
Docker Hub publishing                ✅
Minikube cluster                     ✅
Kubernetes Pod                       ✅
Kubernetes ClusterIP Service         ✅
kubectl port-forward                 ✅
ML inference through Kubernetes      ✅
```

---

## Author

**Aditya Devan**

LinkedIn:

[https://www.linkedin.com/in/aditya-devan-72a4832b/](https://www.linkedin.com/in/aditya-devan19)

Questions and suggestions are welcome. Open an issue or reach out.



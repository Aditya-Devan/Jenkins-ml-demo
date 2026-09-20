// Six-stage ML pipeline:
//   Train -> Evaluate (metric gate) -> Package -> Scan -> Smoke -> [Publish]
// metrics.json is archived on EVERY build (post { always }).
//
// Jenkins runs docker via the host's socket (docker-outside-of-docker),
// so the workspace path inside Jenkins does NOT exist on the engine host
// and -v mounts would come up empty. Instead we keep one helper container
// alive for Train+Evaluate and move files with `docker cp`.

pipeline {
    agent any

    environment {
        IMAGE   = 'inference:ci'
        TRAINER = 'inference-trainer'
        WORKBENCH = "ml-workbench-${env.BUILD_NUMBER}"
    }

    stages {
        stage('Train') {
            steps {
                sh 'docker build -f Dockerfile.train -t "$TRAINER" .'
                sh '''
                    docker rm -f "$WORKBENCH" >/dev/null 2>&1 || true
                    docker run -d --name "$WORKBENCH" "$TRAINER" sleep infinity
                    docker cp "$WORKSPACE/." "$WORKBENCH":/work
                    docker exec -w /work "$WORKBENCH" python train.py
                    docker cp "$WORKBENCH":/work/model.pkl "$WORKSPACE/model.pkl"
                '''
            }
        }

        stage('Evaluate') {
            steps {
                script {
                    def acc = sh(
                        script: 'docker exec -w /work "$WORKBENCH" python evaluate.py --print-accuracy',
                        returnStdout: true
                    ).trim().toFloat()

                    // pull the quality report out BEFORE the gate, so it
                    // is archived even when the build goes red
                    sh 'docker cp "$WORKBENCH":/work/metrics.json "$WORKSPACE/metrics.json"'

                    echo "model accuracy: ${acc}"
                    if (acc < 0.90) {
                        error("model accuracy ${acc} below 0.90 - NOT shipping")
                    }
                }
            }
        }

        stage('Package') {
            steps {
                sh 'docker build -t "$IMAGE" .'
            }
        }

        stage('Scan') {
            steps {
                sh '''
                    docker run --rm \
                      -v /var/run/docker.sock:/var/run/docker.sock \
                      -v trivy-cache:/root/.cache/trivy \
                      aquasec/trivy:latest image \
                      --severity CRITICAL --ignore-unfixed --exit-code 1 \
                      "$IMAGE"
                '''
            }
        }

        stage('Smoke') {
            steps {
                sh 'bash smoke-test.sh "$IMAGE"'
            }
        }

        stage('Publish') {
            steps {
                withCredentials([usernamePassword(
                    credentialsId: 'dockerhub-token',
                    usernameVariable: 'DOCKER_USER',
                    passwordVariable: 'DOCKER_PASS'
                )]) {
                    sh '''
                        echo "$DOCKER_PASS" | docker login -u "$DOCKER_USER" --password-stdin
                        docker tag "$IMAGE" "$DOCKER_USER/inference:$BUILD_NUMBER"
                        docker tag "$IMAGE" "$DOCKER_USER/inference:latest"
                        docker push "$DOCKER_USER/inference:$BUILD_NUMBER"
                        docker push "$DOCKER_USER/inference:latest"
                        docker logout
                    '''
                }
            }
        }
    }

    post {
        always {
            sh 'docker rm -f "$WORKBENCH" >/dev/null 2>&1 || true'
            archiveArtifacts artifacts: 'metrics.json', allowEmptyArchive: true
        }
    }
}

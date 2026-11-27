# Deploying a Java Container to ECS Fargate from ECR

## Lab Objectives

In the CLOUD_PROVIDERS_AWS ecosystem, Amazon ECS orchestrates containers and AWS Fargate provides serverless compute for tasks without managing EC2 instances. Amazon ECR stores private container images. Combining these three services lets development teams package a Java application as an image, push it to ECR, and deploy it as an ECS service running on Fargate.

This hands-on lab builds a small Java 21 HTTP service, packages it with a multi-stage Docker build, pushes the image to a private ECR repository, and deploys an ECS service. The task uses `awsvpc` network mode, CloudWatch Logs, a container health check, and a security group restricting access sources. After deployment, learners inspect task status, read logs, call endpoints, and perform an image update.

This lab uses public subnets and a temporary public IP to keep direct HTTP verification simple. This is a learning configuration. Production environments should place Fargate tasks in private subnets, receive traffic through an Application Load Balancer, enforce HTTPS, and avoid exposing public IPs directly on individual tasks.

After this hands-on lab, learners will be able to:

- Create a Java application with HTTP and health endpoints.
- Write a multi-stage Dockerfile running the container as a non-root user.
- Build an image for the target Linux architecture and test it locally.
- Create a private ECR repository, authenticate, tag, and push the image.
- Distinguish an ECS task execution role from an application task role.
- Create a CloudWatch log group and configure `awslogs`.
- Register a Fargate task definition with CPU, memory, port mapping, and health check.
- Create an ECS cluster and service inside a VPC and public subnets.
- Inspect tasks, ENIs, public IPs, service events, and container logs.
- Deploy a new image version via a new task definition revision.
- Diagnose image pull, IAM, networking, health check, and task startup failures.
- Clean up resources to control costs.

## 1. Architecture and Deployment Flow

Components in this lab:

| Component | Role |
|---|---|
| Java 21 application | HTTP service exposing `/` and `/health` |
| Docker | Packages the application into a container image |
| Amazon ECR | Stores private container images |
| ECS task execution role | Allows ECS/Fargate to pull images from ECR and write logs |
| ECS cluster | Logical grouping managing services and tasks |
| Fargate task definition | Describes image, CPU, memory, ports, health check, and logging |
| ECS service | Maintains desired task count and replaces failed tasks |
| VPC/subnets | Provides networking for task ENIs |
| Security group | Restricts inbound/outbound traffic |
| CloudWatch Logs | Stores container stdout/stderr |

Overall flow:

~~~mermaid
flowchart TD
    DEV[Developer] -->|Build Docker image| IMG[Local container image]
    IMG -->|docker push| ECR[(Amazon ECR private repository)]
    ECR -->|Image pull| TASK[ECS Fargate task]
    IAM[ECS task execution role] -->|ECR and Logs permissions| TASK
    ECS[ECS cluster and service] -->|Schedules and replaces| TASK
    TASK -->|stdout and stderr| CW[CloudWatch Logs]
    CLIENT[HTTP client] -->|TCP 8080| SG[Task security group]
    SG --> TASK
    TASK --> APP[Java HTTP application]
~~~

Key concepts to distinguish:

- **Image** is an immutable artifact built from source code and a Dockerfile.
- **ECR repository** stores multiple image tags/digests.
- **Task definition revision** defines how to run a specific image.
- **Task** is an instantiated running container set based on a task definition.
- **Service** maintains the desired count and manages rolling deployments.
- **Cluster** is a logical boundary containing ECS services and standalone tasks.
- **Fargate** provides compute for tasks; users do not manage EC2 hosts.

## 2. Environment Preparation

Requirements:

- An AWS account with permissions to create ECR repositories, IAM roles, CloudWatch log groups, ECS clusters/services, security groups, and ENIs.
- AWS CLI v2 installed and configured with credentials.
- Docker Desktop or Docker Engine running.
- Java 21 is only needed if building/testing source directly outside Docker; the multi-stage Docker build already includes a JDK in the build stage.
- Bash terminal on Linux/macOS or WSL/Git Bash on Windows.
- A VPC with public subnets, a route to an Internet Gateway, and at least one subnet per AZ if testing multi-AZ placement.

Never put access keys in source code, Dockerfiles, or shell scripts. Use AWS IAM Identity Center/SSO or an assigned role.

Sign in and verify your AWS identity:

~~~bash
aws configure sso
aws sso login --profile lab
export AWS_PROFILE=lab
export AWS_REGION=ap-southeast-1

aws sts get-caller-identity
aws configure get region
docker version
~~~

Replace Region with your chosen lab Region. The ECR repository, ECS cluster, tasks, and CloudWatch log group in this lab must reside in the same Region. IAM roles are account-wide global resources.

If you already have an AWS CLI profile, you can skip `aws configure sso` and `aws sso login`. Do not use a profile with broader permissions than needed.

Set variables for subsequent commands:

~~~bash
export APP_NAME=java-ecs-demo
export AWS_REGION=ap-southeast-1
export ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
export ECR_URI="$(printf '%s.dkr.ecr.%s.amazonaws.com/%s' "$ACCOUNT_ID" "$AWS_REGION" "$APP_NAME")"
export IMAGE_TAG=1.0.0

printf 'Account: %s\nRegion: %s\nRepository: %s\n' \
  "$ACCOUNT_ID" "$AWS_REGION" "$ECR_URI"
~~~

If using `AWS_PROFILE`, export the profile before running commands. Verify the account ID and Region match your lab environment before creating resources.

## 3. Creating the Java 21 Application

Create the directory structure:

~~~text
java-ecs-demo/
├── Dockerfile
└── src/
    └── main/
        └── java/
            └── com/
                └── example/
                    └── Main.java
~~~

The application uses `com.sun.net.httpserver.HttpServer` built into the JDK. Endpoint `/` returns service details, Java runtime version, and container hostname. Endpoint `/health` returns HTTP 200 when the server is running.

File `src/main/java/com/example/Main.java`:

~~~java
package com.example;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.Executors;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) throws IOException {
        int port = Integer.parseInt(
            System.getenv().getOrDefault("PORT", "8080")
        );

        HttpServer server = HttpServer.create(
            new InetSocketAddress("0.0.0.0", port),
            0
        );

        server.createContext("/health", exchange -> {
            if (!"GET".equals(exchange.getRequestMethod())) {
                send(exchange, 405, "text/plain", "method not allowed\n");
                return;
            }
            send(exchange, 200, "text/plain", "ok\n");
        });

        server.createContext("/", exchange -> {
            if (!"GET".equals(exchange.getRequestMethod())) {
                send(exchange, 405, "text/plain", "method not allowed\n");
                return;
            }

            String hostname = System.getenv()
                .getOrDefault("HOSTNAME", "unknown");

            String response = """
                service=java-ecs-demo
                java=%s
                host=%s
                """.formatted(
                    System.getProperty("java.version"),
                    hostname
                );

            send(exchange, 200, "text/plain", response);
        });

        server.setExecutor(Executors.newFixedThreadPool(4));
        server.start();

        System.out.printf(
            "java-ecs-demo listening on 0.0.0.0:%d%n",
            port
        );
    }

    private static void send(
        HttpExchange exchange,
        int status,
        String contentType,
        String body
    ) throws IOException {
        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set(
            "Content-Type",
            contentType + "; charset=utf-8"
        );
        exchange.getResponseHeaders().set("Cache-Control", "no-store");
        exchange.sendResponseHeaders(status, bytes.length);

        try (OutputStream output = exchange.getResponseBody()) {
            output.write(bytes);
        }
    }
}
~~~

The application binds to `0.0.0.0` because the container must accept connections on the task's network interface. Binding only to `127.0.0.1` prevents container port mappings from forwarding external traffic into the server.

`/health` is an HTTP process check endpoint. In production applications, a health endpoint should check mandatory dependencies appropriately while avoiding heavy queries or continuous external service calls on every health check.

## 4. Writing the Multi-Stage Dockerfile

Create `Dockerfile` in the project root:

~~~dockerfile
FROM amazoncorretto:21-alpine-jdk AS build

WORKDIR /workspace
COPY src ./src

RUN mkdir -p out \
    && javac --add-modules jdk.httpserver \
       -d out src/main/java/com/example/Main.java \
    && jar --create \
       --file app.jar \
       --main-class com.example.Main \
       -C out .

FROM amazoncorretto:21-alpine

WORKDIR /app

RUN addgroup -S app \
    && adduser -S -G app app

COPY --from=build --chown=app:app /workspace/app.jar /app/app.jar

USER app

EXPOSE 8080

ENTRYPOINT ["java", "--add-modules", "jdk.httpserver", "-XX:MaxRAMPercentage=70.0", "-jar", "/app/app.jar"]
~~~

Explanation:

- The build stage uses the JDK to compile source code and produce an executable JAR.
- The runtime stage contains only the Java runtime, omitting the compiler and source tree.
- `USER app` runs the process as a non-root user.
- `EXPOSE 8080` documents the port used by the application; it does not open ports on the security group.
- `MaxRAMPercentage` helps the JVM size its heap relative to the container's memory limit.
- `ENTRYPOINT` runs the Java process directly so it receives shutdown signals from the container runtime.

Never include AWS credentials, `.env` files containing secrets, or production config files in the Docker build context. You can add `.dockerignore`:

~~~text
.git
.idea
.vscode
*.log
.env
.aws
target
build
~~~

Multi-stage builds reduce runtime image size and attack surface. For larger applications, pin base images by digest, scan images, and update base images via a vulnerability management process.

## 5. Building and Testing the Container Locally

Build the image for Linux x86_64:

~~~bash
docker build \
  --platform linux/amd64 \
  --tag "$APP_NAME:$IMAGE_TAG" \
  .
~~~

Verify the image is configured to run as a non-root user:

~~~bash
docker image inspect \
  --format '{{.Config.User}}' \
  "$APP_NAME:$IMAGE_TAG"
~~~

Expected output is `app`.

`--platform linux/amd64` prevents architecture mismatches when a developer workstation uses ARM64 while the Fargate task is configured for `X86_64`. To use ARM64, build a `linux/arm64` image and set `runtimePlatform.cpuArchitecture` to `ARM64`.

Run the container:

~~~bash
docker run --rm \
  --name java-ecs-demo-local \
  --publish 8080:8080 \
  "$APP_NAME:$IMAGE_TAG"
~~~

Open another terminal and test:

~~~bash
curl -i http://localhost:8080/
curl -i http://localhost:8080/health
~~~

Expected response:

~~~text
HTTP/1.1 200 OK
Content-type: text/plain; charset=utf-8

service=java-ecs-demo
java=21...
host=...
~~~

The health endpoint must return HTTP 200 and body `ok`. If port 8080 is already in use, pick another host port, such as `--publish 18080:8080`, and call `http://localhost:18080/`.

View container logs:

~~~bash
docker logs java-ecs-demo-local
~~~

Stop the container with Ctrl+C. Because `--rm` was passed, the local container is automatically removed on exit.

## 6. Creating a Private ECR Repository

Create the repository with tag immutability and scan-on-push:

~~~bash
aws ecr create-repository \
  --repository-name "$APP_NAME" \
  --image-tag-mutability IMMUTABLE \
  --image-scanning-configuration scanOnPush=true \
  --encryption-configuration encryptionType=AES256 \
  --region "$AWS_REGION"
~~~

If the repository already exists, use `describe-repositories` to inspect settings instead of recreating it:

~~~bash
aws ecr describe-repositories \
  --repository-names "$APP_NAME" \
  --region "$AWS_REGION"
~~~

Tag immutability prevents overwriting an existing tag. When publishing a new release, bump the version tag such as `1.0.1` or `1.1.0`; do not attempt to push tag `1.0.0` again to an immutable repository.

Verify the repository URI:

~~~bash
aws ecr describe-repositories \
  --repository-names "$APP_NAME" \
  --query 'repositories[0].repositoryUri' \
  --output text \
  --region "$AWS_REGION"
~~~

## 7. Authenticating to ECR and Pushing the Image

ECR uses an authorization token for Docker client authentication. Retrieve the token via the AWS CLI and pipe it directly into `docker login`:

~~~bash
aws ecr get-login-password --region "$AWS_REGION" \
  | docker login \
      --username AWS \
      --password-stdin \
      "$ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com"
~~~

Tag the local image with the repository URI:

~~~bash
docker tag \
  "$APP_NAME:$IMAGE_TAG" \
  "$ECR_URI:$IMAGE_TAG"
~~~

Push the image:

~~~bash
docker push "$ECR_URI:$IMAGE_TAG"
~~~

Verify the image:

~~~bash
aws ecr describe-images \
  --repository-name "$APP_NAME" \
  --image-ids imageTag="$IMAGE_TAG" \
  --query 'imageDetails[0].[imageTags,imageDigest,imageSizeInBytes,imagePushedAt]' \
  --output table \
  --region "$AWS_REGION"
~~~

Record the image digest for traceability. Tags help operators read versions; digests uniquely identify exact image contents. In production pipelines, you can reference images by digest in task definitions to prevent unexpected content changes.

## 8. Creating the ECS Task Execution Role

The ECS task execution role allows ECS/Fargate to perform infrastructure actions on the task's behalf, most commonly:

- Retrieving authorization tokens and pulling images from private ECR.
- Writing container stdout/stderr to CloudWatch Logs.
- Reading secrets or parameters when the task definition references them and the role has matching permissions.

The execution role does not automatically become the identity of the Java application inside the container. If Java code needs to call S3, DynamoDB, or other AWS services, create a separate task role and grant least privilege to the application.

Create trust policy file `ecs-task-trust.json`:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "ecs-tasks.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
~~~

Create the role:

~~~bash
aws iam create-role \
  --role-name "$APP_NAME-execution-role" \
  --assume-role-policy-document file://ecs-task-trust.json
~~~

Attach the managed policy for ECR pulls and CloudWatch Logs:

~~~bash
aws iam attach-role-policy \
  --role-name "$APP_NAME-execution-role" \
  --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy
~~~

Verify the role:

~~~bash
aws iam get-role \
  --role-name "$APP_NAME-execution-role"
~~~

The task definition will reference the role by ARN:

~~~text
arn:aws:iam::<ACCOUNT_ID>:role/java-ecs-demo-execution-role
~~~

If the role already exists, verify its trust relationship and attached policies before proceeding. IAM policies can take a brief moment to propagate. The operator needs `iam:CreateRole`, `iam:AttachRolePolicy`, and appropriate `iam:PassRole` permissions. Scope `iam:PassRole` to the specific roles used by this ECS task.

## 9. Creating the CloudWatch Log Group

Create the log group before launching the service:

~~~bash
aws logs create-log-group \
  --log-group-name "/ecs/$APP_NAME" \
  --region "$AWS_REGION"
~~~

Set 7-day retention for the lab:

~~~bash
aws logs put-retention-policy \
  --log-group-name "/ecs/$APP_NAME" \
  --retention-in-days 7 \
  --region "$AWS_REGION"
~~~

If the log group already exists, `create-log-group` may return `ResourceAlreadyExistsException`; inspect the group and continue with the retention policy.

In the task definition, the `awslogs` log driver ships stdout/stderr to this log group. Set explicit retention so lab logs are not kept indefinitely and increasing costs.

## 10. Preparing the VPC, Public Subnets, and Security Group

Fargate tasks use `awsvpc` network mode. Each task receives its own elastic network interface (ENI) with an attached security group. To make direct HTTP testing easy in this lab, tasks are placed in public subnets routed to an Internet Gateway with public IPs enabled.

Check the default VPC:

~~~bash
export VPC_ID="$(aws ec2 describe-vpcs \
  --filters Name=isDefault,Values=true \
  --query 'Vpcs[0].VpcId' \
  --output text \
  --region "$AWS_REGION")"

printf 'Default VPC: %s\n' "$VPC_ID"
~~~

If the result is `None`, select an existing lab VPC and identify appropriate public subnets. Do not create a new VPC solely for this lab if the account already provides shared networking.

List subnets and Availability Zones:

~~~bash
aws ec2 describe-subnets \
  --filters "Name=vpc-id,Values=$VPC_ID" \
  --query 'Subnets[].{SubnetId:SubnetId,AZ:AvailabilityZone,PublicIP:MapPublicIpOnLaunch,CIDR:CidrBlock}' \
  --output table \
  --region "$AWS_REGION"
~~~

List route tables to confirm subnets have a default route to an Internet Gateway:

~~~bash
aws ec2 describe-route-tables \
  --filters "Name=vpc-id,Values=$VPC_ID" \
  --output table \
  --region "$AWS_REGION"
~~~

Look for a route with destination `0.0.0.0/0` targeting an active Internet Gateway. Verify the route table is associated with your chosen subnets; if subnets rely on the main route table, verify the main association accordingly.

Pick one or two public subnets. If picking two, place them in two different Availability Zones. Confirm the subnet's route table has a `0.0.0.0/0` route to an Internet Gateway (`igw-...`). `MapPublicIpOnLaunch` only controls automatic public IP assignment per subnet config; it does not prove a subnet has an Internet route.

Set subnet IDs:

~~~bash
export SUBNET_A=subnet-REPLACE_WITH_PUBLIC_SUBNET_A
export SUBNET_B=subnet-REPLACE_WITH_PUBLIC_SUBNET_B
~~~

If only one public subnet is available, you can pass a single subnet to `create-service`, though without multi-AZ placement options.

### 10.1. Creating the Security Group

Find the public IP of the machine used for testing. You can check your IP via a public IP lookup service or use your organization's egress IP. Open TCP 8080 strictly from that `/32` client address:

~~~bash
export MY_PUBLIC_CIDR=203.0.113.10/32

export SG_ID="$(aws ec2 create-security-group \
  --group-name "$APP_NAME-sg" \
  --description "Temporary HTTP access for the Java ECS Fargate lab" \
  --vpc-id "$VPC_ID" \
  --query GroupId \
  --output text \
  --region "$AWS_REGION")"

aws ec2 authorize-security-group-ingress \
  --group-id "$SG_ID" \
  --protocol tcp \
  --port 8080 \
  --cidr "$MY_PUBLIC_CIDR" \
  --region "$AWS_REGION"
~~~

Replace `203.0.113.10/32` with your client's actual public IP. Do not use `0.0.0.0/0` for this lab. New security groups allow all outbound traffic by default; the task needs outbound access to ECR, S3, and CloudWatch Logs to pull images and send logs.

In a public subnet, a Fargate task assigned a public IP uses the Internet Gateway route to reach public service endpoints. If a subnet lacks an Internet route, the task may fail to pull images or emit logs.

## 11. Creating the ECS Cluster

Create the cluster:

~~~bash
aws ecs create-cluster \
  --cluster-name "$APP_NAME" \
  --region "$AWS_REGION"
~~~

Verify:

~~~bash
aws ecs describe-clusters \
  --clusters "$APP_NAME" \
  --query 'clusters[0].[clusterName,status,registeredContainerInstancesCount,runningTasksCount]' \
  --output table \
  --region "$AWS_REGION"
~~~

With Fargate, there is no need to register EC2 container instances into the cluster. The cluster is a logical scope for managing ECS services and tasks.

## 12. Registering the Fargate Task Definition

The task definition specifies the image, CPU, memory, port mapping, logging, and health check.

Example `task-definition.json` (replace account ID, Region, and repository URI with your created values):

~~~json
{
  "family": "java-ecs-demo",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "256",
  "memory": "512",
  "executionRoleArn": "arn:aws:iam::111122223333:role/java-ecs-demo-execution-role",
  "runtimePlatform": {
    "operatingSystemFamily": "LINUX",
    "cpuArchitecture": "X86_64"
  },
  "containerDefinitions": [
    {
      "name": "java-app",
      "image": "111122223333.dkr.ecr.ap-southeast-1.amazonaws.com/java-ecs-demo:1.0.0",
      "essential": true,
      "portMappings": [
        {
          "containerPort": 8080,
          "protocol": "tcp"
        }
      ],
      "healthCheck": {
        "command": [
          "CMD-SHELL",
          "wget -q -O /dev/null http://127.0.0.1:8080/health || exit 1"
        ],
        "interval": 30,
        "timeout": 5,
        "retries": 3,
        "startPeriod": 20
      },
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/java-ecs-demo",
          "awslogs-region": "ap-southeast-1",
          "awslogs-stream-prefix": "ecs"
        }
      }
    }
  ]
}
~~~

In practice, replace account ID, Region, and repository URI with your created values. You can generate the file via a heredoc so the shell interpolates variables:

~~~bash
cat > task-definition.json <<EOF
{
  "family": "$APP_NAME",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "256",
  "memory": "512",
  "executionRoleArn": "arn:aws:iam::$ACCOUNT_ID:role/$APP_NAME-execution-role",
  "runtimePlatform": {
    "operatingSystemFamily": "LINUX",
    "cpuArchitecture": "X86_64"
  },
  "containerDefinitions": [
    {
      "name": "java-app",
      "image": "$ECR_URI:$IMAGE_TAG",
      "essential": true,
      "portMappings": [
        {
          "containerPort": 8080,
          "protocol": "tcp"
        }
      ],
      "healthCheck": {
        "command": [
          "CMD-SHELL",
          "wget -q -O /dev/null http://127.0.0.1:8080/health || exit 1"
        ],
        "interval": 30,
        "timeout": 5,
        "retries": 3,
        "startPeriod": 20
      },
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/$APP_NAME",
          "awslogs-region": "$AWS_REGION",
          "awslogs-stream-prefix": "ecs"
        }
      }
    }
  ]
}
EOF
~~~

Lab settings explained:

- `networkMode` `awsvpc` is required by Fargate.
- `requiresCompatibilities` `FARGATE` specifies launch compatibility.
- `cpu` `256` and `memory` `512` correspond to 0.25 vCPU and 0.5 GiB; this is a valid Fargate configuration pair.
- `runtimePlatform` specifies Linux `X86_64`, matching the image built earlier.
- `executionRoleArn` authorizes ECS to pull the image and ship logs.
- `containerPort` must match the port the Java application listens on.
- `healthCheck` executes inside the container; the Alpine image includes `wget` to probe `/health`.
- `awslogs` ships stdout/stderr to CloudWatch Logs.

The task definition omits `taskRoleArn` because the demo app makes no AWS API calls. If the app needs S3 or DynamoDB access, create a dedicated application task role, grant least privilege, and set `taskRoleArn`. Never reuse the execution role as the application role.

Register the task definition:

~~~bash
aws ecs register-task-definition \
  --cli-input-json file://task-definition.json \
  --region "$AWS_REGION"
~~~

Save the returned revision:

~~~bash
export TASK_REVISION="$(aws ecs describe-task-definition \
  --task-definition "$APP_NAME" \
  --query 'taskDefinition.revision' \
  --output text \
  --region "$AWS_REGION")"

printf 'Task definition revision: %s\n' "$TASK_REVISION"
~~~

Every registration that modifies the task definition creates a new revision. Older revisions persist until deregistered; a service runs only the revision referenced by its deployment.

## 13. Creating the ECS Fargate Service

The service maintains the desired count and replaces tasks if a task stops or a deployment triggers replacement. This lab uses desired count 1 to minimize cost.

Create the service:

~~~bash
aws ecs create-service \
  --cluster "$APP_NAME" \
  --service-name "$APP_NAME-service" \
  --task-definition "$APP_NAME:$TASK_REVISION" \
  --desired-count 1 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[$SUBNET_A,$SUBNET_B],securityGroups=[$SG_ID],assignPublicIp=ENABLED}" \
  --deployment-configuration "maximumPercent=200,minimumHealthyPercent=100,deploymentCircuitBreaker={enable=true,rollback=true}" \
  --region "$AWS_REGION"
~~~

If using only one public subnet, omit `$SUBNET_B` and the comma in the subnets list.

Explanation:

- `launch-type FARGATE` selects Fargate compute.
- `awsvpcConfiguration` attaches the task ENI to the subnets and security group.
- `assignPublicIp=ENABLED` assigns a public IP so the task in the public subnet can reach the Internet.
- `desired-count 1` instructs the service to keep one task running.
- Deployment circuit breaker allows ECS to detect unstable deployments and roll back per configuration.

Wait for the service to stabilize:

~~~bash
aws ecs wait services-stable \
  --cluster "$APP_NAME" \
  --services "$APP_NAME-service" \
  --region "$AWS_REGION"
~~~

Inspect the service:

~~~bash
aws ecs describe-services \
  --cluster "$APP_NAME" \
  --services "$APP_NAME-service" \
  --query 'services[0].[status,desiredCount,runningCount,pendingCount,deployments[0].rolloutState]' \
  --output table \
  --region "$AWS_REGION"
~~~

Expected result: service `ACTIVE`, desired count 1, running count 1, pending count 0, and rollout state `COMPLETED`.

If the service does not stabilize, do not jump ahead to HTTP checks. Inspect service events and task stopped reasons first.

## 14. Retrieving the Public IP and Testing the Application

Retrieve the running task ARN:

~~~bash
export TASK_ARN="$(aws ecs list-tasks \
  --cluster "$APP_NAME" \
  --service-name "$APP_NAME-service" \
  --desired-status RUNNING \
  --query 'taskArns[0]' \
  --output text \
  --region "$AWS_REGION")"

printf 'Task: %s\n' "$TASK_ARN"
~~~

Retrieve the ENI ID from the task attachment:

~~~bash
export ENI_ID="$(aws ecs describe-tasks \
  --cluster "$APP_NAME" \
  --tasks "$TASK_ARN" \
  --query "tasks[0].attachments[0].details[?name=='networkInterfaceId'].value | [0]" \
  --output text \
  --region "$AWS_REGION")"

printf 'ENI: %s\n' "$ENI_ID"
~~~

Retrieve the public IP:

~~~bash
export TASK_PUBLIC_IP="$(aws ec2 describe-network-interfaces \
  --network-interface-ids "$ENI_ID" \
  --query 'NetworkInterfaces[0].Association.PublicIp' \
  --output text \
  --region "$AWS_REGION")"

printf 'Task public IP: %s\n' "$TASK_PUBLIC_IP"
~~~

Call the HTTP endpoints:

~~~bash
curl -i "http://$TASK_PUBLIC_IP:8080/"
curl -i "http://$TASK_PUBLIC_IP:8080/health"
~~~

`/` should display the service name, Java version, and container hostname. `/health` should return `200 OK` and `ok`.

If the request times out or cannot connect, verify:

- The client's public IP is within `MY_PUBLIC_CIDR` on the security group.
- The task has a public IP and the subnet has a route to the Internet Gateway.
- The security group permits inbound TCP 8080 from the client.
- The Java server binds `0.0.0.0:8080`.
- Container port mapping is `8080`.
- The task is `RUNNING` and health status is `HEALTHY`.

A task's public IP can change whenever ECS replaces the task or deploys a new revision. Never use this IP as a production endpoint or hardcode it in other applications.

## 15. Reading Logs and Observing the Service

Tail the log stream:

~~~bash
aws logs tail "/ecs/$APP_NAME" \
  --since 15m \
  --follow \
  --region "$AWS_REGION"
~~~

Log streams typically use prefix `ecs/java-app/` followed by the task ID. Use the task ID to correlate logs with running tasks.

Inspect service events:

~~~bash
aws ecs describe-services \
  --cluster "$APP_NAME" \
  --services "$APP_NAME-service" \
  --query 'services[0].events[0:10].[createdAt,message]' \
  --output table \
  --region "$AWS_REGION"
~~~

Inspect task health and container state:

~~~bash
aws ecs describe-tasks \
  --cluster "$APP_NAME" \
  --tasks "$TASK_ARN" \
  --query 'tasks[0].[lastStatus,healthStatus,stopCode,stoppedReason,containers[0].exitCode,containers[0].reason]' \
  --output table \
  --region "$AWS_REGION"
~~~

Task states:

- `PENDING`: ECS is preparing the task or allocating an ENI.
- `PROVISIONING`: Fargate is provisioning compute/network.
- `ACTIVATING`: the task is initializing containers/networking.
- `RUNNING`: containers are running.
- `STOPPED`: the task has stopped; inspect `stoppedReason`, exit code, and logs.
- `HEALTHY`/`UNHEALTHY`: container health check outcome when defined in the task definition.

ECS service events usually reveal placement, image pull, subnet/IP, or deployment failures. CloudWatch Logs reveals errors inside the Java process. Combine both sources when diagnosing issues.

## 16. Deploying a New Java Version

Update the response in `Main.java`, for example adding a version line:

~~~java
String response = """
    service=java-ecs-demo
    release=1.0.1
    java=%s
    host=%s
    """.formatted(
        System.getProperty("java.version"),
        hostname
    );
~~~

Build a new tag because the ECR repository enforces tag immutability:

~~~bash
export IMAGE_TAG=1.0.1

docker build \
  --platform linux/amd64 \
  --tag "$APP_NAME:$IMAGE_TAG" \
  .

docker tag \
  "$APP_NAME:$IMAGE_TAG" \
  "$ECR_URI:$IMAGE_TAG"

docker push "$ECR_URI:$IMAGE_TAG"
~~~

Update the image tag in the task definition JSON and register a new revision:

~~~bash
aws ecs register-task-definition \
  --cli-input-json file://task-definition.json \
  --region "$AWS_REGION"
~~~

Retrieve the new revision:

~~~bash
export NEW_TASK_REVISION="$(aws ecs describe-task-definition \
  --task-definition "$APP_NAME" \
  --query 'taskDefinition.revision' \
  --output text \
  --region "$AWS_REGION")"
~~~

Update the service:

~~~bash
aws ecs update-service \
  --cluster "$APP_NAME" \
  --service "$APP_NAME-service" \
  --task-definition "$APP_NAME:$NEW_TASK_REVISION" \
  --region "$AWS_REGION"
~~~

Wait for the deployment to stabilize:

~~~bash
aws ecs wait services-stable \
  --cluster "$APP_NAME" \
  --services "$APP_NAME-service" \
  --region "$AWS_REGION"
~~~

ECS performs a rolling deployment per service configuration; the old task is replaced once the new task launches according to the deployment strategy. Re-fetch the task ARN, ENI, and public IP following Step 14 since the new task may receive a different IP, then call the endpoints again. If deployment fails, inspect the circuit breaker, service events, and task stopped reason.

Never reuse a mutable tag in production when reproducible deployments are required. Use version tags or image digests and record the deployed task definition revision.

## 17. Increasing Availability and Moving to Production

This lab uses a single task and public IP to focus on the ECR → ECS → Fargate pipeline. Production requires additional layers:

~~~mermaid
flowchart TD
    USER[Users] --> ALB[Application Load Balancer]
    ALB --> SGALB[ALB security group]
    SGALB --> TG[Target group]
    TG --> TASK1[Fargate task in private subnet AZ-A]
    TG --> TASK2[Fargate task in private subnet AZ-B]
    TASK1 --> DB[(Private database or services)]
    TASK2 --> DB
    ECR[(ECR)] --> TASK1
    ECR --> TASK2
    CW[CloudWatch Logs and metrics] <-- TASK1
    CW <-- TASK2
~~~

Key changes:

- Place tasks in private subnets with `assignPublicIp=DISABLED`.
- Place an Application Load Balancer in public subnets and register the ECS service with a target group.
- Have the ALB security group accept HTTPS from clients; have the task security group accept traffic only from the ALB security group on the container port.
- Terminate TLS at the ALB using an ACM certificate.
- Maintain a desired count of at least 2 tasks across two Availability Zones for high availability.
- Configure ECS service auto scaling based on CPU, memory, or request count as appropriate.
- Configure the `/health` path on both the target group health check and the container health check.
- Use Secrets Manager or Systems Manager Parameter Store for secrets; inject them via the task definition using execution role permissions or retrieve them via the application task role.
- Use a dedicated task role to grant permissions to the Java application.
- Enforce ECR image scanning, immutable tags, digest pinning, and a build/scan/deploy pipeline.
- Enable deployment circuit breakers, alarms, and a rollback strategy.
- Provision VPC endpoints for ECR API, ECR Docker registry, S3, and CloudWatch Logs—or a NAT Gateway—so private tasks can reach required services.

Fargate tasks in private subnets do not need public IPs. Without a NAT Gateway or appropriate VPC endpoints, tasks cannot pull ECR images or ship logs. Endpoint designs must account for DNS, route tables, endpoint security groups, and endpoint policies.

## 18. Troubleshooting

| Symptom | Possible Cause | Resolution |
|---|---|---|
| `docker login` to ECR fails | Wrong AWS credentials/Region or expired token | Check `sts get-caller-identity`, Region, and fetch a fresh login password |
| `RepositoryNotFoundException` | Repository not created or wrong Region/name | Check ECR repository URI and Region |
| Push denied | Role lacks ECR push permissions or Docker logged into wrong registry | Check ECR upload permissions and registry hostname |
| Fargate cannot pull image | Execution role lacks permissions, wrong image URI/tag, missing egress, or architecture mismatch | Check execution role, ECR digest, public/private subnet, and `runtimePlatform` |
| `CannotPullContainerError` | Unreachable ECR/S3 endpoints or missing image | Inspect service events, routes/NAT/VPC endpoints, and repository |
| `ResourceInitializationError` | Cannot reach ECR, Secrets Manager, or CloudWatch Logs | Check execution role, DNS, endpoints, NAT, and log group |
| `AccessDenied` registering task definition | Caller lacks `iam:PassRole` | Scope and grant `PassRole` for the target execution/task role |
| Task stops immediately after start | Java exception, wrong entrypoint, architecture mismatch, or OOM | Inspect CloudWatch logs, exit code, and stopped reason |
| Health check `UNHEALTHY` | Server not listening, wrong path, wrong port, or missing command in image | Check `/health`, `wget`, container port, and `startPeriod` |
| Service has no `RUNNING` tasks | Exhausted subnet/IP capacity, placement failure, or deployment error | Inspect ECS service events and task stopped reason |
| HTTP timeout | Wrong SG inbound, missing public IP, missing IGW route, or wrong client CIDR | Check ENI, route table, SG, and Java bind address |
| No CloudWatch Logs visible | Wrong log group/Region or execution role lacks permissions | Check `awslogs` options, log group, and managed policy |
| Java hits OOM | Task memory too low or JVM heap oversized | Tune Fargate memory/CPU and JVM memory percentage |
| New deployment keeps old image | Service still points to older task definition revision | Register a new revision and update the service |
| Cannot push same tag | ECR repository has `IMMUTABLE` tags enabled | Use a new version tag |

When a task transitions to `STOPPED`, inspect task details before deleting or replacing it to capture `stoppedReason`, `stopCode`, container reason, and exit code. An ECS service can continuously spawn replacement tasks; recurring failures can cause endless task churn without fixing the root cause.

## 19. Post-Lab Resource Cleanup

Fargate tasks, public IPv4 addresses, ECR image storage, and CloudWatch Logs can incur charges. When finished, clean up resources in order.

Scale desired count to 0 and wait for tasks to stop:

~~~bash
aws ecs update-service \
  --cluster "$APP_NAME" \
  --service "$APP_NAME-service" \
  --desired-count 0 \
  --region "$AWS_REGION"

aws ecs wait services-stable \
  --cluster "$APP_NAME" \
  --services "$APP_NAME-service" \
  --region "$AWS_REGION"
~~~

Delete the service and cluster:

~~~bash
aws ecs delete-service \
  --cluster "$APP_NAME" \
  --service "$APP_NAME-service" \
  --region "$AWS_REGION"

aws ecs wait services-inactive \
  --cluster "$APP_NAME" \
  --services "$APP_NAME-service" \
  --region "$AWS_REGION"

aws ecs delete-cluster \
  --cluster "$APP_NAME" \
  --region "$AWS_REGION"
~~~

Delete the ECR repository and all lab images:

~~~bash
aws ecr delete-repository \
  --repository-name "$APP_NAME" \
  --force \
  --region "$AWS_REGION"
~~~

Delete the log group:

~~~bash
aws logs delete-log-group \
  --log-group-name "/ecs/$APP_NAME" \
  --region "$AWS_REGION"
~~~

Once the task ENI has been released, delete the security group:

~~~bash
aws ec2 delete-security-group \
  --group-id "$SG_ID" \
  --region "$AWS_REGION"
~~~

If the execution role was created solely for this lab and no other tasks use it, detach the policy and delete the role:

~~~bash
aws iam detach-role-policy \
  --role-name "$APP_NAME-execution-role" \
  --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy

aws iam delete-role \
  --role-name "$APP_NAME-execution-role"
~~~

Task definition revisions can be deregistered after the service is deleted. Never delete IAM roles, security groups, or log groups shared with other applications. If you created VPC endpoints, NAT Gateways, an ALB, or target groups for an extended lab, delete them in dependency order and verify no resources remain in use.

## 20. Lab Completion Criteria

Mark complete once verified:

- [ ] Java application runs locally and `/health` returns HTTP 200.
- [ ] Docker image is built for a Linux architecture compatible with the task definition.
- [ ] Container runs as a non-root user.
- [ ] Private ECR repository exists and the image tag/digest was pushed successfully.
- [ ] ECS task execution role has the appropriate trust policy and managed policy.
- [ ] CloudWatch log group exists with a retention policy configured.
- [ ] Task definition specifies Fargate, `awsvpc`, valid CPU/memory, and the exact image URI.
- [ ] ECS service has desired count 1 and running count 1.
- [ ] Task health check reports `HEALTHY`.
- [ ] `/` and `/health` are reachable via the task public IP from the security-group-permitted client.
- [ ] CloudWatch Logs displays the Java application's startup log.
- [ ] Registered a new task definition revision and verified the updated deployment.
- [ ] Understood how to transition to private subnets and an ALB for production.
- [ ] Cleaned up unused lab resources.

## Conclusion

This lab walked through the complete Java container deployment path: writing an HTTP service, building a multi-stage Docker image, pushing to private ECR, creating an ECS task execution role, registering a Fargate task definition, and deploying a service inside a VPC. The ECS service maintains desired count; Fargate provides compute; ECR supplies images; CloudWatch Logs and health checks verify operation.

When troubleshooting, separate build/push issues, image pull issues, IAM issues, networking issues, container startup issues, and health check failures. Service events, task stopped reasons, and CloudWatch Logs provide complementary views. When releasing new versions, use new image tags or digests and new task definition revisions for controlled deployments.

Direct public IP exposure is strictly for learning. Production deployments should place Fargate tasks in private subnets, put an ALB in public subnets, restrict task security groups to accept traffic only from the ALB, and add TLS, auto scaling, secrets management, monitoring, deployment rollbacks, and image scanning workflows.

## References

- [Amazon ECS developer guide](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/Welcome.html)
- [AWS Fargate launch type](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/AWS_Fargate.html)
- [Creating an ECS task definition for Fargate](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task_definition_parameters.html)
- [Task networking with the awsvpc network mode](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-networking-awsvpc.html)
- [ECS task execution IAM role](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task_execution_IAM_role.html)
- [ECS task IAM role](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-iam-roles.html)
- [Using Amazon ECR images with Amazon ECS](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task_definition_images.html)
- [Pushing a Docker image to Amazon ECR](https://docs.aws.amazon.com/AmazonECR/latest/userguide/docker-push-ecr-image.html)
- [Amazon ECR private repositories](https://docs.aws.amazon.com/AmazonECR/latest/userguide/Repositories.html)
- [ECS container health checks](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/healthcheck.html)
- [ECS service deployments and deployment circuit breaker](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/deployment-circuit-breaker.html)
- [Sending ECS logs to CloudWatch](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/using_awslogs.html)
- [ECS services and load balancing](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/service-load-balancing.html)
- [ECS service auto scaling](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/service-auto-scaling.html)
- [Amazon ECS troubleshooting](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/troubleshooting.html)
- [AWS Fargate pricing](https://aws.amazon.com/fargate/pricing/)
- [Amazon ECR pricing](https://aws.amazon.com/ecr/pricing/)

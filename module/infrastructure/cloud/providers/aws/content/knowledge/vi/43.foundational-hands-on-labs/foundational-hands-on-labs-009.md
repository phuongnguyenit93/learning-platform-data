# Triển khai container Java lên ECS Fargate từ ECR

## Mục tiêu bài thực hành

Trong hệ sinh thái CLOUD_PROVIDERS_AWS, Amazon ECS điều phối container và AWS Fargate cung cấp compute serverless cho task mà không cần quản lý EC2 instance. Amazon ECR lưu trữ container image riêng tư. Kết hợp ba dịch vụ này, đội phát triển có thể đóng gói ứng dụng Java thành image, đẩy image lên ECR rồi triển khai thành ECS service chạy trên Fargate.

Bài thực hành xây dựng một HTTP service Java 21 nhỏ, đóng gói bằng Docker multi-stage build, đẩy image lên private ECR repository và triển khai một ECS service. Task dùng awsvpc network mode, CloudWatch Logs, container health check và security group giới hạn nguồn truy cập. Sau khi triển khai, người học kiểm tra trạng thái task, đọc log, gọi endpoint và thực hiện cập nhật image.

Bài lab dùng public subnet và public IP tạm thời để việc kiểm tra HTTP trực tiếp đơn giản hơn. Đây là cấu hình học tập. Môi trường production nên đặt Fargate tasks trong private subnets, nhận traffic qua Application Load Balancer, dùng HTTPS và không mở public IP trực tiếp cho từng task.

Sau bài thực hành, người học có thể:

- Tạo ứng dụng Java có HTTP endpoint và health endpoint.
- Viết Dockerfile multi-stage, chạy container bằng non-root user.
- Build image đúng kiến trúc Linux và kiểm thử tại local.
- Tạo private ECR repository, đăng nhập, tag và push image.
- Phân biệt ECS task execution role với application task role.
- Tạo CloudWatch log group và cấu hình awslogs.
- Đăng ký Fargate task definition với CPU, memory, port mapping và health check.
- Tạo ECS cluster/service trong VPC và public subnets.
- Kiểm tra task, ENI, public IP, service events và container logs.
- Triển khai phiên bản image mới theo task definition revision.
- Chẩn đoán lỗi image pull, IAM, network, health check và task startup.
- Dọn tài nguyên để kiểm soát chi phí.

## 1. Kiến trúc và luồng triển khai

Các thành phần trong bài lab:

| Thành phần | Vai trò |
|---|---|
| Java 21 application | HTTP service có / và /health |
| Docker | Đóng gói ứng dụng thành container image |
| Amazon ECR | Lưu trữ private container image |
| ECS task execution role | Cho ECS/Fargate pull image từ ECR và ghi log |
| ECS cluster | Nhóm logic quản lý service và task |
| Fargate task definition | Mô tả image, CPU, memory, port, health check và logging |
| ECS service | Duy trì số task mong muốn và thay thế task lỗi |
| VPC/subnets | Cung cấp mạng cho task ENI |
| Security group | Giới hạn inbound/outbound traffic |
| CloudWatch Logs | Lưu stdout/stderr của container |

Luồng tổng thể:

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

Một số khái niệm cần phân biệt:

- **Image** là artifact bất biến được build từ source và Dockerfile.
- **ECR repository** lưu nhiều image tags/digests.
- **Task definition revision** mô tả cách chạy một image cụ thể.
- **Task** là một lần chạy container theo task definition.
- **Service** duy trì desired count và quản lý rolling deployment.
- **Cluster** là phạm vi logic chứa ECS services và standalone tasks.
- **Fargate** cấp compute cho task; người dùng không quản lý EC2 hosts.

## 2. Chuẩn bị môi trường

Cần có:

- AWS account và quyền tạo ECR repository, IAM role, CloudWatch log group, ECS cluster/service, security group và ENI.
- AWS CLI v2 đã cài và cấu hình credentials.
- Docker Desktop hoặc Docker Engine đang chạy.
- Java 21 chỉ cần nếu muốn build/test source trực tiếp ngoài Docker; Docker multi-stage build đã có JDK trong build stage.
- Terminal Bash trên Linux/macOS hoặc WSL/Git Bash trên Windows.
- Một VPC có public subnets, route tới Internet Gateway và ít nhất một subnet ở mỗi AZ nếu muốn kiểm tra placement đa AZ.

Không ghi access key vào source code, Dockerfile hoặc shell script. Dùng AWS IAM Identity Center/SSO hoặc role được cấp cho người thực hiện.

Đăng nhập và xác minh AWS identity:

~~~bash
aws configure sso
aws sso login --profile lab
export AWS_PROFILE=lab
export AWS_REGION=ap-southeast-1

aws sts get-caller-identity
aws configure get region
docker version
~~~

Thay Region bằng Region được chọn cho lab. ECR repository, ECS cluster, task và CloudWatch log group trong bài cần được tạo cùng Region. IAM role là tài nguyên global của account.

Nếu đã có AWS CLI profile, có thể bỏ qua aws configure sso và aws sso login. Không dùng profile có quyền rộng hơn mức cần thiết.

Đặt biến dùng trong các lệnh tiếp theo:

~~~bash
export APP_NAME=java-ecs-demo
export AWS_REGION=ap-southeast-1
export ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
export ECR_URI="$(printf '%s.dkr.ecr.%s.amazonaws.com/%s' "$ACCOUNT_ID" "$AWS_REGION" "$APP_NAME")"
export IMAGE_TAG=1.0.0

printf 'Account: %s\nRegion: %s\nRepository: %s\n' \
  "$ACCOUNT_ID" "$AWS_REGION" "$ECR_URI"
~~~

Nếu dùng AWS_PROFILE, export profile trước khi chạy các lệnh. Hãy xác nhận account ID và Region đúng môi trường lab trước khi tạo tài nguyên.

## 3. Tạo ứng dụng Java 21

Tạo cấu trúc thư mục:

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

Ứng dụng sử dụng com.sun.net.httpserver.HttpServer có sẵn trong JDK. Endpoint / trả thông tin service, Java runtime và container hostname. Endpoint /health trả HTTP 200 khi server đang hoạt động.

File src/main/java/com/example/Main.java:

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

Ứng dụng bind vào 0.0.0.0, vì container phải nhận kết nối từ network interface của task. Nếu chỉ bind 127.0.0.1, port mapping của container không thể chuyển traffic từ bên ngoài vào server.

 /health là endpoint kiểm tra tiến trình HTTP. Trong ứng dụng production, health endpoint nên kiểm tra những dependency bắt buộc ở mức phù hợp, nhưng tránh thực hiện query nặng hoặc gọi dịch vụ bên ngoài liên tục mỗi lần health check.

## 4. Viết Dockerfile multi-stage

Tạo file Dockerfile ở thư mục gốc:

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

Giải thích:

- Build stage dùng JDK để biên dịch source và tạo executable JAR.
- Runtime stage chỉ chứa Java runtime, không mang theo compiler và source tree.
- USER app chạy process bằng non-root user.
- EXPOSE 8080 mô tả port ứng dụng sử dụng; nó không tự mở port trên security group.
- MaxRAMPercentage giúp JVM điều chỉnh heap theo memory limit của container.
- ENTRYPOINT chạy Java process trực tiếp để nhận tín hiệu dừng từ container runtime.

Không đưa AWS credentials, .env chứa secret hoặc file cấu hình production vào Docker build context. Có thể bổ sung .dockerignore:

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

Multi-stage build giảm kích thước và bề mặt tấn công của runtime image. Với ứng dụng lớn, nên pin base image bằng digest, quét image và cập nhật base image theo quy trình quản lý lỗ hổng.

## 5. Build và chạy thử container tại local

Build image cho Linux x86_64:

~~~bash
docker build \
  --platform linux/amd64 \
  --tag "$APP_NAME:$IMAGE_TAG" \
  .
~~~

Kiểm tra image được cấu hình chạy bằng non-root user:

~~~bash
docker image inspect \
  --format '{{.Config.User}}' \
  "$APP_NAME:$IMAGE_TAG"
~~~

Kết quả mong đợi là app.

--platform linux/amd64 giúp tránh lỗi kiến trúc khi máy phát triển dùng ARM64 nhưng task Fargate được cấu hình X86_64. Nếu muốn dùng ARM64, phải build image linux/arm64 và đặt runtimePlatform.cpuArchitecture thành ARM64.

Chạy container:

~~~bash
docker run --rm \
  --name java-ecs-demo-local \
  --publish 8080:8080 \
  "$APP_NAME:$IMAGE_TAG"
~~~

Mở terminal khác và kiểm tra:

~~~bash
curl -i http://localhost:8080/
curl -i http://localhost:8080/health
~~~

Kết quả mong đợi:

~~~text
HTTP/1.1 200 OK
Content-type: text/plain; charset=utf-8

service=java-ecs-demo
java=21...
host=...
~~~

Health endpoint phải trả HTTP 200 và body ok. Nếu port 8080 đã được sử dụng, chọn host port khác, ví dụ --publish 18080:8080, rồi gọi http://localhost:18080/.

Xem log container:

~~~bash
docker logs java-ecs-demo-local
~~~

Dừng container bằng Ctrl+C. Vì đã dùng --rm, container local sẽ tự được xóa khi dừng.

## 6. Tạo private ECR repository

Tạo repository với tag immutability và scan-on-push:

~~~bash
aws ecr create-repository \
  --repository-name "$APP_NAME" \
  --image-tag-mutability IMMUTABLE \
  --image-scanning-configuration scanOnPush=true \
  --encryption-configuration encryptionType=AES256 \
  --region "$AWS_REGION"
~~~

Nếu repository đã tồn tại, dùng describe-repositories để kiểm tra cấu hình thay vì tạo lại:

~~~bash
aws ecr describe-repositories \
  --repository-names "$APP_NAME" \
  --region "$AWS_REGION"
~~~

Tag immutability ngăn ghi đè một tag đã tồn tại. Khi phát hành bản mới, hãy tăng version tag như 1.0.1 hoặc 1.1.0; không cố push lại tag 1.0.0 vào repository immutable.

Xác minh repository URI:

~~~bash
aws ecr describe-repositories \
  --repository-names "$APP_NAME" \
  --query 'repositories[0].repositoryUri' \
  --output text \
  --region "$AWS_REGION"
~~~

## 7. Đăng nhập ECR và push image

ECR dùng authorization token để Docker client xác thực. Lấy token bằng AWS CLI và truyền trực tiếp vào docker login:

~~~bash
aws ecr get-login-password --region "$AWS_REGION" \
  | docker login \
      --username AWS \
      --password-stdin \
      "$ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com"
~~~

Tag local image bằng repository URI:

~~~bash
docker tag \
  "$APP_NAME:$IMAGE_TAG" \
  "$ECR_URI:$IMAGE_TAG"
~~~

Push image:

~~~bash
docker push "$ECR_URI:$IMAGE_TAG"
~~~

Xác minh image:

~~~bash
aws ecr describe-images \
  --repository-name "$APP_NAME" \
  --image-ids imageTag="$IMAGE_TAG" \
  --query 'imageDetails[0].[imageTags,imageDigest,imageSizeInBytes,imagePushedAt]' \
  --output table \
  --region "$AWS_REGION"
~~~

Ghi lại image digest để phục vụ traceability. Tag giúp người vận hành đọc version; digest xác định chính xác nội dung image. Trong quy trình production, có thể tham chiếu image theo digest trong task definition để tránh thay đổi nội dung ngoài dự kiến.

## 8. Tạo ECS task execution role

ECS task execution role cho phép ECS/Fargate thực hiện các thao tác hạ tầng thay mặt task, phổ biến nhất là:

- Lấy authorization token và pull image từ private ECR.
- Ghi stdout/stderr của container vào CloudWatch Logs.
- Đọc secret hoặc parameter khi task definition cấu hình các nguồn này và role được cấp quyền tương ứng.

Execution role không tự động trở thành identity của Java application bên trong container. Nếu code Java cần gọi S3, DynamoDB hoặc dịch vụ AWS khác, tạo task role riêng và cấp least privilege cho application.

Tạo trust policy file ecs-task-trust.json:

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

Tạo role:

~~~bash
aws iam create-role \
  --role-name "$APP_NAME-execution-role" \
  --assume-role-policy-document file://ecs-task-trust.json
~~~

Gắn managed policy cho ECR pull và CloudWatch Logs:

~~~bash
aws iam attach-role-policy \
  --role-name "$APP_NAME-execution-role" \
  --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy
~~~

Xác minh role:

~~~bash
aws iam get-role \
  --role-name "$APP_NAME-execution-role"
~~~

Task definition sẽ tham chiếu role theo ARN:

~~~text
arn:aws:iam::<ACCOUNT_ID>:role/java-ecs-demo-execution-role
~~~

Nếu role đã tồn tại, kiểm tra trust relationship và attached policies trước khi tiếp tục. IAM policy có thể mất một khoảng thời gian ngắn để propagate. Người thực hiện cần quyền iam:CreateRole, iam:AttachRolePolicy và iam:PassRole phù hợp. Giới hạn iam:PassRole vào role dành cho ECS task này.

## 9. Tạo CloudWatch log group

Tạo log group trước khi khởi chạy service:

~~~bash
aws logs create-log-group \
  --log-group-name "/ecs/$APP_NAME" \
  --region "$AWS_REGION"
~~~

Đặt retention 7 ngày cho lab:

~~~bash
aws logs put-retention-policy \
  --log-group-name "/ecs/$APP_NAME" \
  --retention-in-days 7 \
  --region "$AWS_REGION"
~~~

Nếu log group đã tồn tại, lệnh create có thể trả ResourceAlreadyExistsException; kiểm tra group và tiếp tục với retention policy.

Trong task definition, log driver awslogs sẽ gửi stdout/stderr tới log group. Đặt retention rõ ràng để log lab không lưu vô thời hạn và làm tăng chi phí.

## 10. Chuẩn bị VPC, public subnet và security group

Fargate task dùng awsvpc network mode. Mỗi task có elastic network interface (ENI) riêng và gắn security group. Để gọi HTTP trực tiếp trong bài lab, task được đặt ở public subnet có route tới Internet Gateway và bật public IP.

Kiểm tra default VPC:

~~~bash
export VPC_ID="$(aws ec2 describe-vpcs \
  --filters Name=isDefault,Values=true \
  --query 'Vpcs[0].VpcId' \
  --output text \
  --region "$AWS_REGION")"

printf 'Default VPC: %s\n' "$VPC_ID"
~~~

Nếu kết quả là None, chọn VPC hiện có của lab và xác định public subnets phù hợp. Không tạo VPC mới chỉ để chạy bài này nếu account đã có network dùng chung.

Liệt kê subnets và Availability Zones:

~~~bash
aws ec2 describe-subnets \
  --filters "Name=vpc-id,Values=$VPC_ID" \
  --query 'Subnets[].{SubnetId:SubnetId,AZ:AvailabilityZone,PublicIP:MapPublicIpOnLaunch,CIDR:CidrBlock}' \
  --output table \
  --region "$AWS_REGION"
~~~

Liệt kê route tables để xác nhận subnet có default route tới Internet Gateway:

~~~bash
aws ec2 describe-route-tables \
  --filters "Name=vpc-id,Values=$VPC_ID" \
  --output table \
  --region "$AWS_REGION"
~~~

Tìm route có destination 0.0.0.0/0 và target là Internet Gateway có trạng thái active. Kiểm tra route table được associate với subnet đã chọn; nếu subnet dùng main route table, kiểm tra main association tương ứng.

Chọn một hoặc hai public subnets. Nếu chọn hai, chúng nên ở hai Availability Zones khác nhau. Kiểm tra route table của subnet có route 0.0.0.0/0 tới Internet Gateway (igw-...). MapPublicIpOnLaunch chỉ là thuộc tính tự gán public IP cho instance/ENI theo cấu hình subnet; nó không tự chứng minh subnet có đường route Internet.

Đặt subnet IDs:

~~~bash
export SUBNET_A=subnet-REPLACE_WITH_PUBLIC_SUBNET_A
export SUBNET_B=subnet-REPLACE_WITH_PUBLIC_SUBNET_B
~~~

Nếu chỉ có một public subnet, có thể dùng một subnet trong lệnh create service nhưng không có lựa chọn placement đa AZ.

### 10.1. Tạo security group

Lấy public IP của máy dùng để kiểm tra. Có thể xem IP qua dịch vụ kiểm tra IP công khai hoặc dùng IP egress do tổ chức cấp. Chỉ mở TCP 8080 từ địa chỉ /32 của client:

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

Thay 203.0.113.10/32 bằng public IP thực của client. Không dùng 0.0.0.0/0 cho lab này. Security group mới có outbound allow-all mặc định; task cần outbound tới ECR, S3 và CloudWatch Logs khi pull image và gửi log.

Với public subnet, Fargate task được gán public IP sẽ dùng route Internet Gateway để truy cập các public service endpoints. Nếu subnet không có route Internet, task có thể không pull được image hoặc không gửi log.

## 11. Tạo ECS cluster

Tạo cluster:

~~~bash
aws ecs create-cluster \
  --cluster-name "$APP_NAME" \
  --region "$AWS_REGION"
~~~

Xác minh:

~~~bash
aws ecs describe-clusters \
  --clusters "$APP_NAME" \
  --query 'clusters[0].[clusterName,status,registeredContainerInstancesCount,runningTasksCount]' \
  --output table \
  --region "$AWS_REGION"
~~~

Với Fargate, không cần đăng ký EC2 container instance vào cluster. Cluster là phạm vi logic để quản lý ECS services và tasks.

## 12. Đăng ký Fargate task definition

Task definition xác định image, CPU, memory, port mapping, logging và health check.

Ví dụ task-definition.json (thay account ID, Region và repository URI bằng giá trị đã tạo):

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

Trong file thực tế, thay account ID, Region và repository URI bằng giá trị đã tạo. Có thể tạo file bằng heredoc để shell thay biến:

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

Các lựa chọn trong lab:

- networkMode awsvpc là yêu cầu của Fargate.
- requiresCompatibilities FARGATE chỉ định launch compatibility.
- cpu 256 và memory 512 tương ứng 0,25 vCPU và 0,5 GiB; đây là một cặp cấu hình Fargate hợp lệ.
- runtimePlatform yêu cầu Linux x86_64, khớp với image build ở bước trước.
- executionRoleArn cho phép ECS pull image và gửi log.
- containerPort phải trùng port ứng dụng Java đang listen.
- healthCheck chạy trong container; image Alpine có wget để gọi /health.
- awslogs chuyển stdout/stderr sang CloudWatch Logs.

Task definition không khai báo taskRoleArn vì ứng dụng demo không gọi AWS APIs. Nếu ứng dụng cần truy cập S3 hoặc DynamoDB, tạo application task role riêng, cấp quyền tối thiểu và thêm taskRoleArn. Không dùng execution role làm application role.

Đăng ký task definition:

~~~bash
aws ecs register-task-definition \
  --cli-input-json file://task-definition.json \
  --region "$AWS_REGION"
~~~

Lưu revision được trả về:

~~~bash
export TASK_REVISION="$(aws ecs describe-task-definition \
  --task-definition "$APP_NAME" \
  --query 'taskDefinition.revision' \
  --output text \
  --region "$AWS_REGION")"

printf 'Task definition revision: %s\n' "$TASK_REVISION"
~~~

Mỗi lần đăng ký thay đổi task definition, ECS tạo revision mới. Revision cũ vẫn tồn tại cho tới khi được deregister; service chỉ chạy revision được tham chiếu trong deployment.

## 13. Tạo ECS Fargate service

Service duy trì desired count và thay thế task nếu task dừng hoặc deployment cần thay thế. Bài lab dùng desired count 1 để giảm chi phí.

Tạo service:

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

Nếu chỉ có một public subnet, bỏ SUBNET_B và dấu phẩy tương ứng trong danh sách subnets.

Giải thích:

- launch-type FARGATE chọn Fargate compute.
- awsvpcConfiguration gắn task ENI vào subnets và security group.
- assignPublicIp=ENABLED cấp public IP để task trong public subnet có thể truy cập Internet.
- desired-count 1 yêu cầu service duy trì một task.
- Deployment circuit breaker cho phép ECS phát hiện deployment không ổn định và rollback theo cấu hình.

Chờ service ổn định:

~~~bash
aws ecs wait services-stable \
  --cluster "$APP_NAME" \
  --services "$APP_NAME-service" \
  --region "$AWS_REGION"
~~~

Kiểm tra service:

~~~bash
aws ecs describe-services \
  --cluster "$APP_NAME" \
  --services "$APP_NAME-service" \
  --query 'services[0].[status,desiredCount,runningCount,pendingCount,deployments[0].rolloutState]' \
  --output table \
  --region "$AWS_REGION"
~~~

Kết quả mong đợi là service ACTIVE, desired count 1, running count 1, pending count 0 và rollout state COMPLETED.

Nếu service chưa ổn định, không tiếp tục kiểm tra HTTP. Hãy đọc service events và task stopped reason trước.

## 14. Lấy public IP và kiểm tra ứng dụng

Lấy task ARN đang chạy:

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

Lấy ENI ID từ task attachment:

~~~bash
export ENI_ID="$(aws ecs describe-tasks \
  --cluster "$APP_NAME" \
  --tasks "$TASK_ARN" \
  --query "tasks[0].attachments[0].details[?name=='networkInterfaceId'].value | [0]" \
  --output text \
  --region "$AWS_REGION")"

printf 'ENI: %s\n' "$ENI_ID"
~~~

Lấy public IP:

~~~bash
export TASK_PUBLIC_IP="$(aws ec2 describe-network-interfaces \
  --network-interface-ids "$ENI_ID" \
  --query 'NetworkInterfaces[0].Association.PublicIp' \
  --output text \
  --region "$AWS_REGION")"

printf 'Task public IP: %s\n' "$TASK_PUBLIC_IP"
~~~

Gọi HTTP endpoints:

~~~bash
curl -i "http://$TASK_PUBLIC_IP:8080/"
curl -i "http://$TASK_PUBLIC_IP:8080/health"
~~~

Kết quả / phải hiển thị service name, Java version và container hostname. /health phải trả 200 OK và ok.

Nếu request timeout hoặc không kết nối được, kiểm tra:

- Client public IP có nằm trong MY_PUBLIC_CIDR của security group không.
- Task có public IP và subnet có route tới Internet Gateway không.
- Security group cho phép inbound TCP 8080 từ client.
- Java server bind 0.0.0.0:8080.
- Container port mapping là 8080.
- Task đang ở trạng thái RUNNING và health status là HEALTHY.

Public IP của task có thể thay đổi khi ECS thay thế task hoặc deployment. Không dùng IP này làm endpoint production hoặc cấu hình cố định trong ứng dụng khác.

## 15. Đọc log và quan sát service

Xem log stream:

~~~bash
aws logs tail "/ecs/$APP_NAME" \
  --since 15m \
  --follow \
  --region "$AWS_REGION"
~~~

Log stream thường có prefix ecs/java-app/ và task ID. Dùng task ID để ghép log với task đang chạy.

Kiểm tra service events:

~~~bash
aws ecs describe-services \
  --cluster "$APP_NAME" \
  --services "$APP_NAME-service" \
  --query 'services[0].events[0:10].[createdAt,message]' \
  --output table \
  --region "$AWS_REGION"
~~~

Kiểm tra task health và container state:

~~~bash
aws ecs describe-tasks \
  --cluster "$APP_NAME" \
  --tasks "$TASK_ARN" \
  --query 'tasks[0].[lastStatus,healthStatus,stopCode,stoppedReason,containers[0].exitCode,containers[0].reason]' \
  --output table \
  --region "$AWS_REGION"
~~~

Các trạng thái:

- PENDING: ECS đang chuẩn bị task hoặc cấp ENI.
- PROVISIONING: Fargate đang cấp compute/network.
- ACTIVATING: task đang chuẩn bị container/network.
- RUNNING: container đang chạy.
- STOPPED: task đã dừng; xem stoppedReason, exit code và log.
- HEALTHY/UNHEALTHY: kết quả container health check nếu task definition khai báo health check.

ECS service events thường cho biết lỗi placement, image pull, subnet/IP hoặc deployment. CloudWatch logs cho biết lỗi từ Java process. Cần kết hợp cả hai nguồn.

## 16. Triển khai phiên bản Java mới

Sửa response ở Main.java, ví dụ thêm dòng version:

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

Build tag mới vì ECR repository đang bật tag immutability:

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

Cập nhật image tag trong task definition JSON rồi đăng ký revision mới:

~~~bash
aws ecs register-task-definition \
  --cli-input-json file://task-definition.json \
  --region "$AWS_REGION"
~~~

Lấy revision mới:

~~~bash
export NEW_TASK_REVISION="$(aws ecs describe-task-definition \
  --task-definition "$APP_NAME" \
  --query 'taskDefinition.revision' \
  --output text \
  --region "$AWS_REGION")"
~~~

Cập nhật service:

~~~bash
aws ecs update-service \
  --cluster "$APP_NAME" \
  --service "$APP_NAME-service" \
  --task-definition "$APP_NAME:$NEW_TASK_REVISION" \
  --region "$AWS_REGION"
~~~

Chờ deployment ổn định:

~~~bash
aws ecs wait services-stable \
  --cluster "$APP_NAME" \
  --services "$APP_NAME-service" \
  --region "$AWS_REGION"
~~~

ECS thực hiện rolling deployment theo cấu hình service; task cũ được thay thế khi task mới được khởi chạy theo deployment strategy. Lấy lại task ARN, ENI và public IP theo bước 14 vì task mới có thể nhận IP khác, sau đó gọi lại endpoint. Nếu deployment thất bại, kiểm tra circuit breaker, service events và task stopped reason.

Không tái sử dụng một tag mutable trong production nếu muốn triển khai có thể tái lập. Dùng version tag hoặc image digest và lưu task definition revision đã triển khai.

## 17. Tăng độ sẵn sàng và đưa vào production

Bài lab dùng một task và public IP để tập trung vào luồng ECR → ECS → Fargate. Production cần thêm các lớp:

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

Các thay đổi chính:

- Đặt task trong private subnets và assignPublicIp=DISABLED.
- Đặt Application Load Balancer ở public subnets và đăng ký ECS service với target group.
- ALB security group nhận HTTPS từ client; task security group chỉ nhận traffic từ ALB security group trên container port.
- Dùng ACM certificate để kết thúc TLS tại ALB.
- Duy trì desired count ít nhất 2 task ở hai Availability Zones cho ứng dụng cần HA.
- Cấu hình ECS service auto scaling theo CPU, memory hoặc request count phù hợp.
- Dùng health check path /health ở target group và health check container.
- Dùng Secrets Manager hoặc Systems Manager Parameter Store cho secrets; inject qua task definition với execution role permissions hoặc truy xuất từ application task role.
- Dùng task role riêng để cấp quyền cho Java application.
- Dùng ECR image scanning, immutable tags, digest pinning và pipeline build/scan/deploy.
- Dùng deployment circuit breaker, alarms và rollback strategy.
- Dùng VPC endpoints cho ECR API, ECR Docker registry, S3 và CloudWatch Logs hoặc NAT Gateway để task private truy cập các dịch vụ cần thiết.

Fargate task trong private subnet không cần public IP. Nếu không có NAT Gateway hoặc VPC endpoints phù hợp, task có thể không pull được ECR image hoặc không ghi được log. Thiết kế endpoint phải tính tới DNS, route table, endpoint security group và policy.

## 18. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| docker login ECR thất bại | AWS credentials/Region sai hoặc token hết hạn | Kiểm tra sts get-caller-identity, Region và lấy login password mới |
| RepositoryNotFoundException | Repository chưa được tạo hoặc sai Region/name | Kiểm tra ECR repository URI và Region |
| Push bị denied | Role thiếu ECR push permissions hoặc Docker login sai registry | Kiểm tra quyền ECR upload và registry hostname |
| Fargate không pull được image | Execution role thiếu quyền, sai image URI/tag, network egress hoặc image architecture không khớp | Kiểm tra execution role, ECR digest, public/private subnet và runtimePlatform |
| CannotPullContainerError | ECR endpoint/S3 layer access không tới được hoặc image không tồn tại | Kiểm tra service events, route/NAT/VPC endpoints và repository |
| ResourceInitializationError | Không truy cập được ECR, Secrets Manager hoặc CloudWatch Logs | Kiểm tra execution role, DNS, endpoints, NAT và log group |
| AccessDenied khi register task definition | Caller thiếu iam:PassRole | Giới hạn và cấp PassRole cho execution/task role được dùng |
| Task dừng ngay sau start | Java exception, sai entrypoint, architecture mismatch hoặc memory OOM | Đọc CloudWatch log, exit code và stopped reason |
| Health check UNHEALTHY | Server chưa listen, path sai, port sai hoặc command không có trong image | Kiểm tra /health, wget, container port và startPeriod |
| Service không có RUNNING task | Không có subnet/IP capacity, placement hoặc deployment lỗi | Đọc ECS service events và task stopped reason |
| HTTP timeout | SG inbound, public IP, route IGW hoặc client CIDR sai | Kiểm tra ENI, route table, SG và Java bind address |
| Không thấy CloudWatch logs | Log group/Region sai hoặc execution role thiếu quyền | Kiểm tra awslogs options, log group và managed policy |
| Java bị OOM | Memory task quá thấp hoặc JVM heap chiếm quá nhiều | Điều chỉnh Fargate memory/CPU và JVM memory percentage |
| Deployment mới không thay image | Service vẫn dùng task definition revision cũ | Register revision mới và update service |
| Không push được cùng tag | ECR repository bật IMMUTABLE | Tạo version tag mới |

Khi task STOPPED, lấy task details trước khi xóa hoặc thay thế để giữ stoppedReason, stopCode, container reason và exit code. ECS service có thể tự tạo task mới; lỗi lặp lại có thể làm service liên tục thay task mà không khắc phục nguyên nhân.

## 19. Dọn tài nguyên sau lab

Fargate task, public IPv4, ECR image storage và CloudWatch Logs có thể phát sinh chi phí. Sau khi hoàn tất, xóa tài nguyên theo thứ tự.

Giảm desired count về 0 và chờ task dừng:

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

Xóa service và cluster:

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

Xóa ECR repository và tất cả image lab:

~~~bash
aws ecr delete-repository \
  --repository-name "$APP_NAME" \
  --force \
  --region "$AWS_REGION"
~~~

Xóa log group:

~~~bash
aws logs delete-log-group \
  --log-group-name "/ecs/$APP_NAME" \
  --region "$AWS_REGION"
~~~

Sau khi task ENI đã được giải phóng, xóa security group:

~~~bash
aws ec2 delete-security-group \
  --group-id "$SG_ID" \
  --region "$AWS_REGION"
~~~

Nếu execution role được tạo riêng cho lab và không còn task nào dùng role đó, detach policy rồi xóa role:

~~~bash
aws iam detach-role-policy \
  --role-name "$APP_NAME-execution-role" \
  --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy

aws iam delete-role \
  --role-name "$APP_NAME-execution-role"
~~~

Task definition revisions có thể được deregister sau khi service đã xóa. Không xóa IAM role, security group hoặc log group dùng chung với ứng dụng khác. Nếu đã tạo VPC endpoints, NAT Gateway, ALB hoặc target group riêng cho lab mở rộng, xóa chúng theo thứ tự phụ thuộc và xác minh không còn resource nào đang sử dụng.

## 20. Tiêu chí hoàn thành bài lab

Đánh dấu hoàn thành khi xác minh được:

- [ ] Java application chạy local và /health trả HTTP 200.
- [ ] Docker image được build cho Linux architecture tương thích với task definition.
- [ ] Container chạy bằng non-root user.
- [ ] ECR private repository tồn tại và image tag/digest được push thành công.
- [ ] ECS task execution role có trust policy và managed policy phù hợp.
- [ ] CloudWatch log group tồn tại và có retention policy.
- [ ] Task definition dùng Fargate, awsvpc, CPU/memory hợp lệ và image URI đúng.
- [ ] ECS service có desired count 1 và running count 1.
- [ ] Task health check báo HEALTHY.
- [ ] / và /health truy cập được qua task public IP từ client được security group cho phép.
- [ ] CloudWatch Logs hiển thị log khởi động của Java application.
- [ ] Đã đăng ký task definition revision mới và xác minh deployment.
- [ ] Đã hiểu cách chuyển sang private subnets và ALB cho production.
- [ ] Đã dọn các tài nguyên lab không còn sử dụng.

## Kết luận

Bài lab đã đi qua toàn bộ đường triển khai container Java: viết HTTP service, build Docker multi-stage, push image vào private ECR, tạo ECS task execution role, đăng ký Fargate task definition và triển khai service trong VPC. ECS service duy trì desired count; Fargate cấp compute; ECR cung cấp image; CloudWatch Logs và health check giúp xác minh hoạt động.

Khi chẩn đoán, hãy phân biệt lỗi build/push, lỗi pull image, lỗi IAM, lỗi network, lỗi container startup và lỗi health check. Service events, task stopped reason và CloudWatch logs cung cấp các góc nhìn khác nhau. Khi phát hành phiên bản mới, dùng image tag mới hoặc digest và task definition revision mới để deployment có thể kiểm soát.

Cấu hình public IP trực tiếp chỉ phù hợp cho lab. Production nên đặt Fargate tasks trong private subnets, đặt ALB ở public subnets, giới hạn task security group chỉ nhận traffic từ ALB và bổ sung TLS, auto scaling, secrets management, monitoring, deployment rollback cùng quy trình image scanning.

## Tài liệu tham khảo

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


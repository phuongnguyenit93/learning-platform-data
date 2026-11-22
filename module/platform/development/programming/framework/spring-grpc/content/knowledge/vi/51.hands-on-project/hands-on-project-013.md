# Đưa service Spring gRPC vào container và graceful shutdown

Một service gRPC chạy ổn định trên máy phát triển vẫn có thể mất request khi được đóng gói và triển khai. Container nhận tín hiệu dừng từ Docker hoặc Kubernetes; nếu tiến trình Java không nhận được tín hiệu đó, hoặc server đóng kết nối ngay lập tức, các RPC đang xử lý có thể thất bại giữa chừng.

Trong dự án này, bạn sẽ đóng gói một Spring gRPC service thành Docker image nhiều giai đoạn, chạy bằng tài khoản không phải root, cấu hình gRPC Health service và triển khai quy trình graceful shutdown. Bạn sẽ kiểm tra trực tiếp một RPC đang chạy khi container nhận SIGTERM, sau đó triển khai cùng service lên Kubernetes với probe và thời gian kết thúc Pod phù hợp.

## Mục tiêu dự án

Khi hoàn thành, service cần đáp ứng các điều kiện sau:

- Có thể build thành executable JAR và Docker image dùng được trong các môi trường đích.
- Runtime image chỉ chứa JRE và artifact cần thiết; tiến trình chạy bằng user không phải root.
- Java là tiến trình nhận SIGTERM trực tiếp từ container runtime.
- gRPC server ngừng nhận RPC mới, cho RPC đang chạy thời gian hoàn tất và buộc dừng khi hết grace period.
- Health service cung cấp trạng thái riêng cho startup/readiness và liveness.
- Docker Compose và Kubernetes có thời gian chờ dừng dài hơn thời gian graceful shutdown của gRPC.

## Chuẩn bị

- Ứng dụng Spring Boot/Spring gRPC đã chạy được ở local và có Gradle Wrapper.
- Java 21, Docker Engine và Docker Compose plugin.
- grpcurl để gọi thử RPC từ máy host.
- kubectl và một Kubernetes cluster có hỗ trợ native gRPC probe (Kubernetes 1.27 trở lên).

## 1. Bối cảnh và kiến trúc

Giả sử bạn có một ứng dụng Spring Boot sử dụng Spring gRPC, lắng nghe cổng 9090 và đã có ít nhất một service kế thừa generated ImplBase. Ví dụ dưới đây dùng Java 21, Gradle Wrapper, Spring Boot 4.1.x và Spring gRPC 1.1.x. Nếu dự án dùng phiên bản khác, hãy kiểm tra lại tên property và API lifecycle trong tài liệu của đúng phiên bản trước khi áp dụng.

Luồng triển khai:

~~~mermaid
flowchart LR
    C[Client gRPC] --> S[Kubernetes Service]
    S --> P[Pod: Spring gRPC]
    P --> G[Native gRPC server]
    T[Docker / kubelet sends SIGTERM] --> J[Java process]
    J --> L[Spring gRPC lifecycle]
    L --> D[Stop accepting new RPCs]
    D --> I[Drain in-flight RPCs]
    I --> X[Process exits]
~~~

Khi container dừng, Java nhận SIGTERM. Spring gRPC quản lý vòng đời server và gọi quy trình shutdown của gRPC. Server từ chối RPC mới, các RPC đang chạy được tiếp tục trong giới hạn thời gian cấu hình; nếu hết thời gian, server chuyển sang forceful shutdown. Container runtime chờ trong khoảng thời gian của nó trước khi gửi SIGKILL.

## 2. Chuẩn bị ứng dụng và gRPC Health service

### 2.1. Kiểm tra dependency

Spring gRPC có thể tự đăng ký gRPC Health service khi ứng dụng có dependency grpc-services. Dependency này cũng cung cấp HealthStatusManager để cập nhật trạng thái phục vụ.

Với Gradle, thêm dependency sau nếu dự án chưa có:

~~~groovy
dependencies {
    implementation("io.grpc:grpc-services")
}
~~~

Để dependency management của Spring Boot/Spring gRPC quản lý phiên bản grpc-java; không tự chọn một phiên bản grpc-services khác với các thư viện grpc-java còn lại.

### 2.2. Khai báo một RPC dùng để kiểm thử shutdown

Bạn có thể dùng service hiện có. Nếu cần một RPC mô phỏng tác vụ đang chạy, thêm method Wait vào file proto:

~~~proto
syntax = "proto3";

package catalog.v1;

option java_multiple_files = true;
option java_package = "com.example.catalog.grpc";

service CatalogService {
  rpc Wait(WaitRequest) returns (WaitReply);
}

message WaitRequest {
  int32 delay_ms = 1;
}

message WaitReply {
  bool completed = 1;
}
~~~

Triển khai method này trong service đã được Spring quản lý. Ví dụ sau chỉ dùng để mô phỏng một RPC đồng bộ đang xử lý; không dùng Thread.sleep làm cách xử lý tác vụ thực tế:

~~~java
import io.grpc.Context;
import io.grpc.Status;
import io.grpc.stub.StreamObserver;

@Override
public void wait(WaitRequest request, StreamObserver<WaitReply> responseObserver) {
    long remaining = Math.min(Math.max(request.getDelayMs(), 0), 60_000);
    Context rpcContext = Context.current();

    try {
        while (remaining > 0 && !rpcContext.isCancelled()) {
            long slice = Math.min(remaining, 100);
            Thread.sleep(slice);
            remaining -= slice;
        }
        if (rpcContext.isCancelled()) {
            return;
        }
        responseObserver.onNext(
                WaitReply.newBuilder().setCompleted(true).build());
        responseObserver.onCompleted();
    }
    catch (InterruptedException exception) {
        Thread.currentThread().interrupt();
        responseObserver.onError(
                Status.CANCELLED
                        .withDescription("RPC interrupted")
                        .withCause(exception)
                        .asRuntimeException());
    }
}
~~~

Đặt deadline của client dài hơn thời gian mô phỏng. Trong service thật, mỗi RPC cần deadline phù hợp, xử lý cancellation và giới hạn thời gian cho các lời gọi tới hệ thống phụ thuộc.

### 2.3. Tách liveness khỏi readiness

Liveness trả lời câu hỏi “tiến trình còn có thể phục vụ không?”. Readiness trả lời “service đã sẵn sàng nhận công việc chưa?”. Không dùng trạng thái database hoặc một dịch vụ bên ngoài làm liveness, vì sự cố phụ thuộc có thể khiến Kubernetes khởi động lại liên tục một tiến trình vốn vẫn khỏe.

Spring gRPC cung cấp HealthStatusManager khi gRPC Health service được cấu hình. Tạo hai tên health riêng để Kubernetes kiểm tra:

~~~java
import static io.grpc.health.v1.HealthCheckResponse.ServingStatus.NOT_SERVING;
import static io.grpc.health.v1.HealthCheckResponse.ServingStatus.SERVING;

import io.grpc.protobuf.services.HealthStatusManager;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.grpc.server.lifecycle.GrpcServerShutdownEvent;
import org.springframework.stereotype.Component;

@Component
public class GrpcProbeHealth {

    private final HealthStatusManager health;

    public GrpcProbeHealth(HealthStatusManager health) {
        this.health = health;
        health.setStatus("liveness", SERVING);
        health.setStatus("readiness", NOT_SERVING);
    }

    @EventListener(ApplicationReadyEvent.class)
    public void markReady() {
        health.setStatus("readiness", SERVING);
    }

    @EventListener(GrpcServerShutdownEvent.class)
    public void markStopping() {
        health.setStatus("readiness", NOT_SERVING);
    }
}
~~~

ApplicationReadyEvent đánh dấu service sẵn sàng sau khi Spring hoàn tất khởi động. Trong ứng dụng thực tế, chỉ đánh dấu readiness là SERVING sau khi các dependency bắt buộc đã sẵn sàng; nếu chúng có thể mất kết nối trong lúc chạy, hãy cập nhật readiness theo tình trạng đó. Liveness vẫn phản ánh khả năng sống của tiến trình và không nên phụ thuộc vào database.

GrpcServerShutdownEvent được Spring gRPC phát ra trước khi server bắt đầu shutdown. Việc đánh dấu readiness không phục vụ nữa giúp thể hiện ý định ngừng nhận traffic; server lifecycle vẫn chịu trách nhiệm shutdown và drain RPC.

## 3. Cấu hình graceful shutdown trong Spring

Trong application.yml, cấu hình địa chỉ bind, cổng và grace period:

~~~yaml
spring:
  application:
    name: catalog-grpc
  grpc:
    server:
      address: 0.0.0.0
      port: 9090
      health:
        enabled: true
      servlet:
        enabled: false
      shutdown:
        grace-period: 25s
  lifecycle:
    timeout-per-shutdown-phase: 35s
~~~

Các giá trị trong ví dụ có quan hệ với nhau:

| Cấu hình | Giá trị | Vai trò |
| --- | ---: | --- |
| spring.grpc.server.shutdown.grace-period | 25 giây | Thời gian Spring gRPC chờ các RPC đang chạy hoàn tất |
| spring.lifecycle.timeout-per-shutdown-phase | 35 giây | Thời gian Spring chờ một lifecycle phase dừng xong |
| Docker stop_grace_period hoặc Kubernetes terminationGracePeriodSeconds | 45 giây | Ngân sách bên ngoài trước khi container bị buộc dừng |

Thời gian chờ của Spring lifecycle phải đủ để gRPC hoàn thành grace period. Thời gian của Docker/Kubernetes cần dài hơn thời gian ứng dụng dừng, có thêm khoảng dự phòng cho việc đóng connection pool, telemetry exporter và các bean khác.

Lab này chọn native gRPC server để service lắng nghe trực tiếp trên cổng 9090. Nếu ứng dụng dùng servlet transport, gRPC đi qua embedded HTTP server và cần cấu hình cổng, HTTP/2 cũng như shutdown theo mô hình servlet tương ứng.

Property spring.grpc.server.shutdown.grace-period là tên trong Spring Boot 4.1.x và Spring gRPC 1.1.x. Spring gRPC 1.0.x dùng tên cũ spring.grpc.server.shutdown-grace-period; hãy đối chiếu application properties của dependency đang dùng.

Nếu ứng dụng đồng thời chạy một embedded HTTP server cho Actuator, việc graceful shutdown HTTP là một lifecycle riêng. Cấu hình gRPC ở trên không thay thế cấu hình shutdown của HTTP server.

## 4. Đóng gói Docker image

### 4.1. Tạo Dockerfile nhiều giai đoạn

Tạo Dockerfile ở thư mục gốc của ứng dụng:

~~~dockerfile
FROM eclipse-temurin:21-jdk AS build

WORKDIR /workspace
COPY . .

RUN chmod +x ./gradlew \
    && ./gradlew --no-daemon clean bootJar \
    && mkdir -p /out \
    && APP_JAR="$(find build/libs -maxdepth 1 -type f -name '*.jar' ! -name '*-plain.jar' | head -n 1)" \
    && test -n "$APP_JAR" \
    && cp "$APP_JAR" /out/app.jar

FROM eclipse-temurin:21-jre

WORKDIR /app
COPY --from=build --chown=10001:10001 /out/app.jar /app/app.jar

USER 10001:10001
EXPOSE 9090
STOPSIGNAL SIGTERM

ENTRYPOINT ["java", "-XX:MaxRAMPercentage=65.0", "-jar", "/app/app.jar"]
~~~

Stage build có JDK và Gradle Wrapper để tạo executable JAR. Stage runtime chỉ nhận JAR và JRE, giúp image nhỏ hơn và không mang theo compiler hoặc source code. Điều chỉnh đường dẫn build/libs nếu đây là Gradle multi-module và executable JAR nằm trong module con.

USER 10001:10001 chạy Java bằng UID/GID không phải root. ENTRYPOINT ở dạng exec giúp Java trở thành tiến trình chính trong container và nhận SIGTERM trực tiếp. Tránh bọc lệnh Java trong sh -c nếu không có cơ chế forward signal.

MaxRAMPercentage giúp JVM điều chỉnh heap theo giới hạn bộ nhớ container; giá trị 65% là điểm khởi đầu cho bài lab, không phải cấu hình tối ưu cho mọi service. Đo heap, direct memory, thread stack và mức dùng bộ nhớ thực tế trước khi chốt production.

Trong môi trường production, hãy pin image JDK/JRE theo phiên bản patch hoặc digest đã được kiểm tra, quét lỗ hổng image và cập nhật định kỳ.

### 4.2. Tạo .dockerignore

~~~text
.git
.gradle
**/build
**/target
.idea
.run
*.iml
*.log
.env
.env.*
~~~

Không loại bỏ gradlew, gradle/wrapper hoặc source cần cho build. File .dockerignore giúp giảm build context và tránh đưa file môi trường có thể chứa secret vào image.

### 4.3. Build và chạy image

~~~bash
docker build -t catalog-grpc:local .
docker run --rm --name catalog-grpc -p 9090:9090 catalog-grpc:local
~~~

Kiểm tra RPC từ máy host bằng grpcurl và file proto:

~~~bash
grpcurl -plaintext -proto src/main/proto/catalog.proto \
  -d '{"delayMs":100}' \
  localhost:9090 catalog.v1.CatalogService/Wait
~~~

Kết quả mong đợi là response có completed: true. Nếu ứng dụng dùng TLS, thay -plaintext bằng tùy chọn TLS phù hợp và cấu hình certificate/authority chính xác.

## 5. Chạy bằng Docker Compose

Tạo compose.yaml:

~~~yaml
services:
  catalog-grpc:
    build:
      context: .
      dockerfile: Dockerfile
    image: catalog-grpc:local
    ports:
      - "9090:9090"
    stop_grace_period: 45s
    restart: unless-stopped
~~~

stop_grace_period làm cho Docker chờ tối đa 45 giây sau khi gửi tín hiệu dừng trước khi buộc dừng container. Giá trị này dài hơn grace period 25 giây của gRPC server.

Chạy ứng dụng:

~~~bash
docker compose up --build -d
docker compose logs -f catalog-grpc
~~~

Gọi thử RPC bằng grpcurl:

~~~bash
grpcurl -plaintext -proto src/main/proto/catalog.proto \
  -d '{"delayMs":100}' \
  localhost:9090 catalog.v1.CatalogService/Wait
~~~

## 6. Kiểm chứng graceful shutdown trên Docker

Đây là phần quan trọng nhất của dự án. Bạn cần chứng minh một RPC đang chạy có thể hoàn tất khi container nhận SIGTERM.

1. Khởi động service bằng Docker Compose và xác nhận RPC Wait hoạt động.
2. Mở terminal thứ nhất và gọi RPC mất 15 giây:

   ~~~bash
   grpcurl -plaintext -max-time 30s \
     -proto src/main/proto/catalog.proto \
     -d '{"delayMs":15000}' \
     localhost:9090 catalog.v1.CatalogService/Wait
   ~~~

3. Trong lúc RPC đang chạy, mở terminal thứ hai và dừng container:

   ~~~bash
   docker compose stop
   ~~~

4. Quan sát kết quả của client và log ứng dụng.

Kết quả mong đợi:

- RPC đã bắt đầu trước khi shutdown và hoàn tất trong grace period 25 giây.
- Server ngừng nhận RPC mới khi graceful shutdown bắt đầu.
- Container thoát trước khi hết stop_grace_period.
- Log thể hiện Spring context và gRPC server đã dừng.

Khởi động lại service để thử timeout:

~~~bash
docker compose up -d
~~~

Gọi RPC với thời gian 40 giây rồi dừng container. Với grace period 25 giây, RPC không thể được đảm bảo hoàn tất; server sẽ force shutdown khi hết thời gian. Đây là tình huống kiểm tra giới hạn của graceful shutdown, không phải một lần chạy thành công.

Trong một terminal, bắt đầu RPC; ở terminal thứ hai, gọi docker compose stop trước khi RPC hoàn tất. Lệnh kiểm thử có thể dùng:

~~~bash
grpcurl -plaintext -max-time 50s \
  -proto src/main/proto/catalog.proto \
  -d '{"delayMs":40000}' \
  localhost:9090 catalog.v1.CatalogService/Wait
~~~

Trong ví dụ Wait, handler kiểm tra trạng thái cancellation định kỳ để dừng phần việc mô phỏng khi gRPC hủy RPC. Với xử lý thực tế, hãy truyền cancellation tới HTTP/database client hoặc tác vụ nền; chỉ đóng transport không tự hoàn tác side effect đã thực hiện.

Nếu RPC 15 giây bị ngắt ngay khi dừng container, hãy kiểm tra Java có phải PID 1 không, Docker có gửi SIGTERM không, property grace period có được bind không và runtime stop timeout có dài hơn thời gian chờ của ứng dụng không.

## 7. Triển khai lên Kubernetes

### 7.1. Dùng gRPC Health probe

Kubernetes hỗ trợ native gRPC startup, readiness và liveness probe. Cơ chế này yêu cầu ứng dụng triển khai gRPC Health Checking Protocol. grpc-services cùng Health service của Spring gRPC cung cấp endpoint mà probe gọi.

Trong manifest bên dưới:

- Startup probe kiểm tra service readiness trong giai đoạn khởi động.
- Readiness probe chỉ cho Pod nhận traffic khi service sẵn sàng.
- Liveness probe dùng service liveness, độc lập với trạng thái database hoặc hệ thống phụ thuộc.

### 7.2. Tạo Deployment và Service

Tạo k8s/catalog-grpc.yaml:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: catalog-grpc
spec:
  replicas: 2
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app: catalog-grpc
  template:
    metadata:
      labels:
        app: catalog-grpc
    spec:
      terminationGracePeriodSeconds: 45
      containers:
        - name: catalog-grpc
          image: catalog-grpc:local
          imagePullPolicy: IfNotPresent
          ports:
            - name: grpc
              containerPort: 9090
              protocol: TCP
          startupProbe:
            grpc:
              port: 9090
              service: readiness
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 30
          readinessProbe:
            grpc:
              port: 9090
              service: readiness
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 2
          livenessProbe:
            grpc:
              port: 9090
              service: liveness
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 3
          resources:
            requests:
              cpu: 250m
              memory: 512Mi
            limits:
              cpu: "1"
              memory: 1Gi
          securityContext:
            runAsNonRoot: true
            runAsUser: 10001
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities:
              drop:
                - ALL
          volumeMounts:
            - name: tmp
              mountPath: /tmp
      volumes:
        - name: tmp
          emptyDir: {}
---
apiVersion: v1
kind: Service
metadata:
  name: catalog-grpc
spec:
  type: ClusterIP
  selector:
    app: catalog-grpc
  ports:
    - name: grpc
      port: 9090
      targetPort: grpc
      protocol: TCP
      appProtocol: kubernetes.io/h2c
~~~

Kubernetes gRPC probe dùng số port, không dùng tên port. Manifest trên dùng plaintext HTTP/2 (h2c) giữa các Pod. Nếu gRPC server kết thúc TLS trực tiếp, cần kiểm tra khả năng TLS probe của phiên bản Kubernetes/feature gate đang chạy hoặc dùng một probe phù hợp với cấu hình TLS. Không bật TLS probe theo giả định rằng mọi cluster đều hỗ trợ.

terminationGracePeriodSeconds: 45 tạo ngân sách tổng cho quá trình kết thúc Pod. Nếu thêm preStop, thời gian chạy hook cũng bị tính vào 45 giây này; đừng dùng một hook ngủ dài khiến phần thời gian còn lại không đủ cho gRPC drain.

### 7.3. Build và triển khai

Build image:

~~~bash
docker build -t catalog-grpc:local .
~~~

Nếu dùng cluster local như kind, tải image vào cluster theo công cụ của cluster, ví dụ:

~~~bash
kind load docker-image catalog-grpc:local
~~~

Áp dụng manifest và theo dõi rollout:

~~~bash
kubectl apply -f k8s/catalog-grpc.yaml
kubectl rollout status deployment/catalog-grpc
kubectl get pods -l app=catalog-grpc
kubectl get endpointslice -l kubernetes.io/service-name=catalog-grpc
~~~

Có thể kiểm thử từ máy host bằng port-forward:

~~~bash
kubectl port-forward service/catalog-grpc 9090:9090
~~~

Sau đó chạy lại lệnh grpcurl ở phần Docker.

### 7.4. Kiểm thử Pod termination

1. Bảo đảm Deployment có ít nhất hai replica và cả hai Pod đều Ready.
2. Chọn một Pod và mở luồng log trước khi xóa:

   ~~~bash
   kubectl logs <pod-name> --follow
   ~~~

3. Ở terminal thứ hai, mở port-forward trực tiếp tới Pod đã chọn:

   ~~~bash
   kubectl port-forward pod/<pod-name> 9091:9090
   ~~~

4. Ở terminal thứ ba, bắt đầu RPC Wait tới localhost:9091. Khi RPC đang chạy, xóa Pod đã chọn từ terminal thứ tư:

   ~~~bash
   grpcurl -plaintext -max-time 30s \
     -proto src/main/proto/catalog.proto \
     -d '{"delayMs":15000}' \
     localhost:9091 catalog.v1.CatalogService/Wait
   ~~~

   ~~~bash
   kubectl delete pod <pod-name>
   ~~~

5. Quan sát trạng thái Pod và EndpointSlice:

   ~~~bash
   kubectl get pods -l app=catalog-grpc -w
   kubectl get endpointslice -l kubernetes.io/service-name=catalog-grpc
   ~~~

Pod đang kết thúc được loại khỏi tập endpoint phục vụ traffic mới; kubelet chạy preStop nếu có, sau đó gửi tín hiệu dừng đến tiến trình chính. Spring gRPC thực hiện shutdown server và chờ RPC đang chạy trong grace period. Nếu thời gian này vượt ngân sách Pod, kubelet có thể buộc dừng container.

## 8. Tính toán shutdown budget

Không đặt các timeout độc lập một cách tùy ý. Chúng phải tạo thành một ngân sách có thứ tự:

~~~text
gRPC shutdown grace period
        < Spring lifecycle phase timeout
        < container / Pod termination grace period
~~~

Với ví dụ của dự án:

| Tầng | Thời gian |
| --- | ---: |
| gRPC server drain | 25 giây |
| Spring lifecycle phase | 35 giây |
| Docker stop / Kubernetes Pod termination | 45 giây |

Khoảng chênh lệch dành cho việc nhận tín hiệu, đóng các bean khác và hoàn tất tiến trình. Nếu có preStop hoặc sidecar cần dừng theo thứ tự, hãy cộng thời gian đó vào ngân sách tổng.

Graceful shutdown không thay thế deadline của RPC. Client vẫn cần deadline hữu hạn và logic xử lý UNAVAILABLE khi kết nối bị ngắt. Với RPC có tác dụng phụ, hãy thiết kế idempotency hoặc cơ chế đối soát để client có thể xác định kết quả khi response bị mất sau khi server đã xử lý xong.

## 9. Lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Container dừng gần như ngay lập tức | Java không nhận SIGTERM hoặc grace period bằng 0 | Kiểm tra ENTRYPOINT, PID 1, stop signal và property Spring gRPC |
| RPC đang chạy bị ngắt | Server force shutdown trước khi RPC hoàn tất | So sánh thời lượng RPC với gRPC grace period và container timeout |
| Docker chờ rồi gửi SIGKILL | Ứng dụng chưa thoát trong stop grace period | Xem log shutdown và tăng timeout sau khi tìm hiểu bean đang chờ |
| Pod liên tục restart khi database lỗi | Liveness phụ thuộc vào database | Tách liveness khỏi readiness |
| Pod không bao giờ Ready | Health service chưa được đăng ký hoặc readiness không chuyển sang SERVING | Kiểm tra grpc-services, HealthStatusManager và probe service name |
| Probe thất bại khi bật TLS | Native probe đang kết nối plaintext hoặc cluster chưa bật TLS probe | Xác minh feature gate và dùng probe phù hợp với TLS |
| Image chạy được local nhưng lỗi trong cluster | Image chưa được load/push hoặc sai bind address/port | Kiểm tra image, 0.0.0.0, containerPort và Service targetPort |

## 10. Tiêu chí nghiệm thu

Hoàn thành dự án khi bạn có thể chứng minh:

- [ ] Docker image được build từ Dockerfile nhiều giai đoạn.
- [ ] Runtime image chạy Java bằng UID không phải root.
- [ ] Container lắng nghe gRPC trên 0.0.0.0:9090.
- [ ] gRPC Health service trả SERVING cho liveness sau khi tiến trình khởi động.
- [ ] Readiness chỉ chuyển sang SERVING khi ứng dụng sẵn sàng.
- [ ] Một RPC đang chạy có thể hoàn tất khi container nhận SIGTERM trong grace period.
- [ ] RPC mới không được nhận sau khi server bắt đầu graceful shutdown.
- [ ] Docker Compose chờ lâu hơn grace period của gRPC.
- [ ] Kubernetes startup/readiness/liveness probes hoạt động.
- [ ] Pod có termination grace period dài hơn thời gian shutdown của ứng dụng.
- [ ] Có log hoặc bằng chứng quan sát được cho cả trường hợp graceful completion và timeout/force shutdown.

## Tài liệu tham khảo

- [Spring gRPC — gRPC Server](https://docs.spring.io/spring-grpc/reference/server.html): đăng ký service, Health service và HealthStatusManager.
- [Spring Boot — Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/): property spring.grpc.server.shutdown.grace-period.
- [Spring gRPC — Lifecycle API](https://docs.spring.io/spring-grpc/reference/api/java/org/springframework/grpc/server/lifecycle/package-summary.html): vòng đời server và các sự kiện shutdown.
- [gRPC — Graceful Shutdown](https://grpc.io/docs/guides/server-graceful-stop/): dừng nhận RPC mới và chờ RPC đang chạy.
- [Kubernetes — Configure Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/): cấu hình native gRPC probes.
- [Kubernetes — Container Lifecycle Hooks](https://kubernetes.io/docs/concepts/containers/container-lifecycle-hooks/): thời điểm chạy preStop và cách tính termination grace period.
- [Kubernetes — Termination of Pods](https://kubernetes.io/docs/concepts/workloads/pods/pod-termination/): luồng kết thúc Pod và gửi tín hiệu đến tiến trình chính.

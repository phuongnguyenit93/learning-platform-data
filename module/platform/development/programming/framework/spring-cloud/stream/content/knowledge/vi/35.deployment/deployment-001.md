# Đóng gói ứng dụng Spring Boot và image container

Một ứng dụng Spring Cloud Stream thường chạy liên tục để nhận, biến đổi và phát sự kiện qua Kafka, RabbitMQ hoặc một binder tương ứng với hệ thống message broker. Sau khi viết các bean `Supplier`, `Function` và `Consumer`, bước triển khai là đóng gói ứng dụng thành artifact có thể chạy lặp lại và đưa artifact đó vào container image. Image phải mang cùng mã nguồn và dependency ở mọi môi trường; địa chỉ broker, group, credential và các giới hạn tài nguyên được cấp lúc chạy.

Bài học này xây dựng quy trình từ executable JAR của Spring Boot đến OCI image, so sánh Cloud Native Buildpacks với Dockerfile, cấu hình binder trong container và chuẩn bị các yếu tố tối thiểu để triển khai trên Docker hoặc Kubernetes. Ví dụ sử dụng Java 21, Gradle và Kafka binder; cùng nguyên tắc có thể áp dụng với RabbitMQ, Kafka Streams và các Pulsar binder phù hợp với dự án.

## 1. Nhìn tổng thể quy trình triển khai

~~~mermaid
flowchart LR
    A[Mã Java và cấu hình] --> B[Gradle bootJar]
    B --> C[Executable JAR]
    C --> D{Cách tạo image}
    D --> E[Cloud Native Buildpacks]
    D --> F[Dockerfile]
    E --> G[OCI container image]
    F --> G
    G --> H[Container registry]
    H --> I[Docker hoặc Kubernetes]
    I --> J[Kafka / RabbitMQ / Pulsar]
~~~

Có ba lớp cần phân biệt:

| Thành phần | Chứa gì? | Thay đổi khi nào? |
|---|---|---|
| Executable JAR | Bytecode ứng dụng, thư viện Spring Boot và Spring Cloud Stream, cấu hình mặc định | Khi build mã nguồn |
| Container image | JAR hoặc lớp đã trích xuất, Java runtime, metadata, entrypoint | Khi build/publish image |
| Container đang chạy | Image cộng biến môi trường, secret, volume, network, CPU/memory limit | Khi deploy hoặc restart |

Không tạo một image riêng chỉ để đổi địa chỉ Kafka của môi trường dev thành địa chỉ Kafka của staging. Cách tốt hơn là phát hành một image bất biến, rồi truyền cấu hình khác nhau cho từng môi trường. Không ghi password hoặc token trực tiếp vào JAR, Dockerfile hay image layer.

## 2. Chuẩn bị ứng dụng Spring Cloud Stream

Một ứng dụng tiêu thụ message theo mô hình hàm có thể có bean:

~~~java
import java.util.function.Consumer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

record OrderEvent(String orderId, String status) {}

@Configuration
class OrderConsumerConfiguration {

    @Bean
    Consumer<OrderEvent> processOrder() {
        return event -> System.out.printf(
                "orderId=%s status=%s%n",
                event.orderId(),
                event.status());
    }
}
~~~

Ví dụ minh họa logic; trong ứng dụng thực tế, xử lý cần idempotency, cấu hình lỗi và logging có cấu trúc. Khi đóng gói, bean function vẫn được phát hiện như lúc chạy bằng IDE. Binder tạo input binding mặc định tên `processOrder-in-0`.

Các dependency cần thiết trong một ứng dụng Kafka binder có thể là:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter")
    implementation("org.springframework.cloud:spring-cloud-stream")
    implementation("org.springframework.cloud:spring-cloud-stream-binder-kafka")
    implementation("org.springframework.boot:spring-boot-starter-actuator")

    // Chỉ cần khi muốn expose HTTP health/metrics.
    implementation("org.springframework.boot:spring-boot-starter-web")
}
~~~

Giả định dự án đã cấu hình Spring Boot Gradle plugin và import Spring Cloud BOM tương thích. Không tùy tiện ghép các version Spring Boot, Spring Cloud và binder khác release train: cần chọn các phiên bản được hỗ trợ cùng nhau. Nếu chỉ dùng RabbitMQ, thay Kafka binder bằng dependency Rabbit binder tương ứng; nếu dùng Kafka Streams DSL, dùng Kafka Streams binder và cấu hình application ID/state store riêng.

## 3. Cấu hình binding bằng application.yml

Ví dụ cấu hình tối thiểu:

~~~yaml
spring:
  application:
    name: order-event-consumer
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.events
          group: order-processor
      kafka:
        binder:
          brokers: ${KAFKA_BROKERS:localhost:9092}

management:
  endpoints:
    web:
      exposure:
        include: "health,info"
  endpoint:
    health:
      probes:
        enabled: true
~~~

`destination` là topic nhận message; `group` là consumer group ổn định để Kafka lưu tiến độ đọc. Với group đã có offset, ứng dụng thường tiếp tục từ offset đã commit khi được khởi động lại. Nếu mỗi lần tạo container lại dùng group ngẫu nhiên, hành vi phục hồi và khả năng nhân bản consumer sẽ thay đổi.

`KAFKA_BROKERS` là biến môi trường được cấp lúc chạy; `localhost:9092` chỉ là giá trị dự phòng để phát triển trực tiếp trên máy. Trong container, `localhost` trỏ đến chính container, không phải Kafka broker đang chạy ở máy host hoặc container khác. Docker Compose và Kubernetes nên dùng DNS/địa chỉ broker mà container thực sự truy cập được.

Các thông tin môi trường như SASL/TLS, schema registry và thông tin đăng nhập cũng phải được cấp từ config/secret lúc chạy. Chỉ đặt cấu hình mặc định vô hại trong application.yml đóng gói.

## 4. Tạo executable Spring Boot JAR

Spring Boot Gradle plugin cung cấp task `bootJar`. Artifact được tạo là executable JAR chứa dependency và launcher của Spring Boot; ứng dụng có thể chạy bằng `java -jar`.

Trong `build.gradle.kts`, có thể đặt tên JAR ổn định:

~~~kotlin
import org.springframework.boot.gradle.tasks.bundling.BootJar

tasks.named<BootJar>("bootJar") {
    archiveFileName.set("app.jar")
}
~~~

Tạo JAR bằng wrapper:

~~~bash
./gradlew clean bootJar
~~~

Trên Windows PowerShell dùng `.\gradlew.bat clean bootJar`. Artifact sau khi build nằm tại `build/libs/app.jar`.

Chạy thử trực tiếp:

~~~bash
KAFKA_BROKERS=localhost:9092 java -jar build/libs/app.jar
~~~

Lệnh gán biến trên cùng dòng là cú pháp shell kiểu POSIX; trong PowerShell dùng `$env:KAFKA_BROKERS = "localhost:9092"` trước khi chạy `java -jar build/libs/app.jar`.

Kiểm tra JAR khởi động thành công, function được đăng ký, input binding kết nối đến topic và health endpoint trả trạng thái mong đợi. Nếu ứng dụng đã có `jar` task tạo thêm file `*-plain.jar`, không sử dụng wildcard mơ hồ `build/libs/*.jar` trong Dockerfile: wildcard có thể trùng cả JAR không thực thi. Đặt tên `app.jar` rõ ràng để tránh copy nhầm.

Nếu dùng Maven, lệnh tương đương thường là `./mvnw -DskipTests package` và Spring Boot Maven plugin sẽ đóng gói executable JAR. Việc bỏ qua test ở ví dụ chỉ dành cho thao tác build lặp lại khi test đã chạy trong CI; pipeline phát hành thực tế vẫn phải thực thi các test bắt buộc trước khi xuất bản image.

## 5. Cách 1: tạo OCI image bằng Cloud Native Buildpacks

Spring Boot Gradle plugin hỗ trợ task `bootBuildImage` dựa trên Cloud Native Buildpacks. Task này kết hợp JAR với builder và Java runtime được buildpack chọn để tạo image theo chuẩn OCI. Không cần tự viết Dockerfile.

Ví dụ:

~~~bash
./gradlew bootBuildImage --imageName=registry.example.com/events/order-consumer:1.0.0
~~~

Điều kiện: máy build hoặc CI runner có Docker daemon/OCI image service tương thích được task hỗ trợ và có khả năng tải builder/run image. Task tạo image cục bộ với tên và tag đã chọn.

Có thể đặt cấu hình trong Gradle:

~~~kotlin
import org.springframework.boot.gradle.tasks.bundling.BootBuildImage

tasks.named<BootBuildImage>("bootBuildImage") {
    imageName.set("registry.example.com/events/order-consumer:1.0.0")
}
~~~

Trong pipeline, nên lấy tag từ version hoặc commit ID của build thay vì hard-code. Khi publish image, cấu hình quyền truy cập registry ở hệ thống build; không đưa password registry vào source. Spring Boot plugin hỗ trợ lựa chọn publish image qua task, hoặc có thể dùng `docker push` sau khi build.

Ưu điểm của Buildpacks:

- Tự chọn các buildpack phù hợp cho Java và Spring Boot.
- Có cơ chế cache để tái sử dụng layer và giảm thời gian build.
- Cho phép cấu hình runtime và các tùy chọn build qua builder/buildpack.
- Giảm nhu cầu tự duy trì Dockerfile và logic trích xuất JAR.

Vẫn cần quản lý version builder/run image, kiểm tra CVE, SBOM và tái build khi có bản vá nền tảng. Buildpacks không thay thế kiểm thử logic hoặc kiểm thử kết nối broker.

## 6. Cách 2: Dockerfile đơn giản từ JAR đã build

Khi cần kiểm soát runtime image và entrypoint, có thể dùng Dockerfile sau:

~~~dockerfile
FROM eclipse-temurin:21-jre-jammy

WORKDIR /opt/app
RUN chown 10001:10001 /opt/app

COPY --chown=10001:10001 build/libs/app.jar /opt/app/app.jar

USER 10001:10001
EXPOSE 8080

ENTRYPOINT ["java", "-jar", "/opt/app/app.jar"]
~~~

Phần build JAR được thực hiện trước bằng Gradle; Dockerfile chỉ đóng gói artifact. Chọn image Java runtime phù hợp với phiên bản bytecode đã biên dịch. Ví dụ dùng Java 21 JRE cho ứng dụng biên dịch bằng Java 21. Pin tag và kiểm tra digest theo chính sách tổ chức khi phát hành.

Lệnh tạo image:

~~~bash
./gradlew clean bootJar
docker build --tag order-consumer:1.0.0 .
~~~

Các quyết định quan trọng:

- `WORKDIR` tạo thư mục làm việc thống nhất.
- `COPY` đưa đúng executable JAR vào runtime image.
- `USER 10001:10001` chạy bằng UID/GID không phải root, giảm quyền của tiến trình.
- `ENTRYPOINT` ở exec form giúp tiến trình Java nhận tín hiệu dừng như SIGTERM trực tiếp, không bị shell trung gian nuốt tín hiệu.
- `EXPOSE 8080` là metadata về port dự kiến; nó không tự public port ra host.

Container image cần writable location cho file tạm. Nếu Kafka Streams binder cần lưu RocksDB state store, phải cấp một đường dẫn state có quyền ghi; không nên giả định toàn bộ filesystem của container có thể ghi. Container chạy dưới UID 10001 nên mọi volume mount phải có quyền phù hợp.

File `.dockerignore` nên loại bớt các thư mục không liên quan để giảm build context:

~~~text
.git
.gradle
.idea
**/*.log
**/test-results
~~~

Không loại trừ `build/libs/app.jar` nếu Dockerfile đang copy artifact đó. Có thể có quy tắc `.dockerignore` khác tùy dự án, nhưng phải kiểm tra JAR vẫn nằm trong Docker build context.

## 7. Dockerfile nhiều layer để tối ưu cập nhật image

Spring Boot executable JAR thường có nhiều nhóm nội dung: dependency ổn định, snapshot dependency, launcher và mã ứng dụng. Nếu copy cả JAR vào một Docker layer, một thay đổi nhỏ trong code khiến layer chứa toàn bộ JAR thay đổi. Trích xuất layered JAR giúp tái sử dụng các lớp ít biến động.

Với Spring Boot phiên bản hỗ trợ `jarmode=tools`, có thể dùng Dockerfile hai stage:

~~~dockerfile
FROM eclipse-temurin:21-jre-jammy AS extract
WORKDIR /workspace
COPY build/libs/app.jar app.jar
RUN java -Djarmode=tools -jar app.jar extract --layers --destination extracted

FROM eclipse-temurin:21-jre-jammy
WORKDIR /opt/app
RUN chown 10001:10001 /opt/app

COPY --from=extract --chown=10001:10001 /workspace/extracted/dependencies/ ./
COPY --from=extract --chown=10001:10001 /workspace/extracted/spring-boot-loader/ ./
COPY --from=extract --chown=10001:10001 /workspace/extracted/snapshot-dependencies/ ./
COPY --from=extract --chown=10001:10001 /workspace/extracted/application/ ./

USER 10001:10001
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "application.jar"]
~~~

Trong bố cục `extract --layers` hiện hành, `application.jar` ở stage cuối là launcher tham chiếu các layer đã trích xuất; đây không phải JAR gốc đã copy vào stage extract. Cơ chế này cần executable JAR có layer index và hỗ trợ tools jar mode. Các phiên bản Spring Boot cũ có thể dùng `jarmode=layertools` với cú pháp trích xuất khác; không trộn hai cách khi chưa kiểm tra phiên bản.

Nếu ứng dụng sử dụng launch script nhúng để tạo fully executable archive, cần kiểm tra giới hạn của tools jar mode. Với Docker, exec form của entrypoint thường phù hợp hơn launch script nhúng.

Đặt các lệnh `COPY` theo thứ tự layer ít thay đổi đến thường thay đổi. Docker/OCI registry có thể tái sử dụng các layer dependency khi chỉ mã nghiệp vụ đổi. Lợi ích thực tế phụ thuộc cách build tạo nội dung và cache của builder.

## 8. Buildpack hay Dockerfile?

| Tiêu chí | Buildpacks (`bootBuildImage`) | Dockerfile |
|---|---|---|
| Viết cấu hình image | Ít, chủ yếu qua Gradle/plugin | Chủ động viết từng instruction |
| Java runtime | Theo builder/buildpack | Chọn base image cụ thể |
| Layer caching | Do lifecycle buildpack hỗ trợ | Tùy thiết kế Docker layer |
| Runtime user | Theo cấu hình run image của buildpack | Phải chủ động đặt `USER` |
| Tùy chỉnh OS packages | Phụ thuộc builder/buildpack | Linh hoạt hơn |
| Cập nhật base image | Cần quản lý builder/run image | Cần quản lý `FROM` |
| Phù hợp | Ứng dụng Boot tiêu chuẩn | Image có ràng buộc OS hoặc runtime riêng |

Với ứng dụng Spring Cloud Stream thông thường, bắt đầu bằng `bootBuildImage` có thể giảm công bảo trì. Nếu phải tùy biến certificate store, thiết bị nền tảng hoặc công cụ runtime đặc biệt, Dockerfile có thể phù hợp hơn. Cả hai cách đều cần scan image và kiểm thử trước khi phát hành.

## 9. Chạy container và truyền cấu hình broker

Với image đã build, có thể chạy:

~~~bash
docker run --rm \
  --name order-consumer \
  --publish 8080:8080 \
  --env KAFKA_BROKERS=kafka.internal:9092 \
  order-consumer:1.0.0
~~~

Lệnh này giả định `kafka.internal:9092` có thể phân giải và truy cập từ trong container. Nếu Kafka chạy cùng Docker Compose, thường dùng service name trong network của Compose, ví dụ `kafka:9092`.

Nếu Kafka chạy trên máy phát triển, `host.docker.internal` có thể được hỗ trợ tùy nền tảng Docker; đây là tiện ích môi trường local, không phải địa chỉ production. Kafka cũng phải công bố `advertised.listeners` mà client trong container có thể truy cập: kết nối được bootstrap server chưa đủ nếu metadata trả về hostname nội bộ không phân giải được.

Đối với RabbitMQ binder, địa chỉ có thể được truyền qua các thuộc tính `spring.rabbitmq.host`, `spring.rabbitmq.port` hoặc binder environment riêng nếu cấu hình nhiều binder. Với Pulsar, cần cấu hình service URL và chứng chỉ theo binder/client đang sử dụng. Không dùng chung tên biến môi trường của Kafka cho RabbitMQ hoặc Pulsar; mỗi integration có cấu hình kết nối riêng.

## 10. Không nhúng secret vào image

Không đặt SASL password, RabbitMQ password, TLS private key hoặc token schema registry trong Dockerfile, `application.yml` commit lên Git hay tham số build.

Thay vào đó, truyền secret lúc container chạy:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        binder:
          configuration:
            security.protocol: SASL_SSL
            sasl.mechanism: SCRAM-SHA-512
            sasl.jaas.config: ${KAFKA_SASL_JAAS}
~~~

Biến `KAFKA_SASL_JAAS` cần được cấp từ secret manager hoặc Kubernetes Secret và chỉ khả dụng cho workload được phép. Cần đảm bảo biến thực sự tồn tại; cấu hình thiếu secret phải làm triển khai thất bại có thể quan sát được, thay vì fallback sang credential mặc định không an toàn.

Environment variable có thể bị lộ qua quyền đọc cấu hình tiến trình hoặc công cụ quản trị runtime. Với yêu cầu cao hơn, có thể mount secret dưới dạng file có quyền đọc hạn chế hoặc dùng CSI Secret Store và chỉ định đường dẫn phù hợp với Kafka client. Không in giá trị secret khi ứng dụng khởi động hoặc qua Actuator `env`, `configprops`, `bindings`.

Registry credential dùng để `docker push` cũng là secret của pipeline; không đưa vào image. Sử dụng identity của runner hoặc credential store phù hợp.

## 11. CPU, memory và JVM trong container

Không nên đặt heap cố định lớn hơn memory limit của container. JVM hiện đại nhận diện giới hạn cgroup; có thể điều chỉnh tỷ lệ heap trong giới hạn bộ nhớ:

~~~yaml
env:
  - name: JAVA_TOOL_OPTIONS
    value: "-XX:MaxRAMPercentage=65 -XX:+ExitOnOutOfMemoryError"
~~~

Đây là ví dụ cấu hình, không phải tỷ lệ tối ưu cho mọi ứng dụng. Phần bộ nhớ còn lại phải đủ cho metaspace, direct buffers, thread stack, Kafka client buffers và native memory. Kafka Streams có thể dùng RocksDB, page cache và state restore; các thành phần này cần được tính ngoài Java heap.

Khi chọn `resources.requests` và `resources.limits` trên Kubernetes, đo heap, RSS, CPU throttle, GC pause, consumer lag và tốc độ restore state dưới tải thực tế. Nếu container bị OOMKilled, tăng heap theo phần trăm mà không xem native memory có thể làm tình hình xấu hơn.

Không gói các công cụ debug không cần thiết trong runtime image. Khi cần phân tích sự cố, dùng phương thức debug được tổ chức cho phép thay vì tăng quyền root cho image production.

## 12. Health endpoint và readiness/liveness

Ứng dụng có Actuator và HTTP stack có thể expose `/actuator/health/liveness` và `/actuator/health/readiness`. Spring Boot tích hợp các trạng thái `LivenessState` và `ReadinessState`, được Kubernetes probe sử dụng để quyết định restart hoặc tiếp nhận traffic.

Ví dụ:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
  endpoints:
    web:
      exposure:
        include: "health,info"
~~~

Không đưa broker, database hoặc dịch vụ ngoài vào liveness theo cách khiến toàn bộ replica liên tục bị restart khi dependency chung bị lỗi. Liveness nên nói lên khả năng tiến trình tự phục hồi; readiness cần thể hiện khả năng phục vụ traffic theo hợp đồng của ứng dụng.

Đối với ứng dụng chỉ có Kafka consumer mà không phục vụ request HTTP, readiness của web server không tự dừng consumer hoặc bảo đảm tất cả binding đã kết nối. Muốn readiness phản ánh trạng thái binder hoặc Kafka Streams state restoration, cần thiết kế health indicator/readiness contributor phù hợp và kiểm thử khi broker bị lỗi.

Nếu management endpoint chạy trên port riêng, probe có thể trả UP khi HTTP API chính không nhận request. Spring Boot có tùy chọn `management.endpoint.health.probes.add-additional-paths=true` để công bố `/livez` và `/readyz` trên port chính. Chọn cổng probe theo kiến trúc runtime thực tế.

## 13. Kubernetes Deployment tối thiểu

Ví dụ minh họa hai replica của Kafka consumer, mỗi replica dùng cùng một image và consumer group:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-consumer
spec:
  replicas: 2
  selector:
    matchLabels:
      app: order-consumer
  template:
    metadata:
      labels:
        app: order-consumer
    spec:
      terminationGracePeriodSeconds: 60
      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        runAsGroup: 10001
      containers:
        - name: app
          image: registry.example.com/events/order-consumer:1.0.0
          imagePullPolicy: IfNotPresent
          ports:
            - name: http
              containerPort: 8080
          env:
            - name: KAFKA_BROKERS
              value: "kafka-bootstrap.messaging.svc.cluster.local:9092"
            - name: JAVA_TOOL_OPTIONS
              value: "-XX:MaxRAMPercentage=65 -XX:+ExitOnOutOfMemoryError"
          resources:
            requests:
              cpu: "250m"
              memory: "512Mi"
            limits:
              cpu: "1"
              memory: "1Gi"
          startupProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
            failureThreshold: 18
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 10
            failureThreshold: 3
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
            failureThreshold: 3
~~~

Manifest giả định ứng dụng có web/Actuator trên cổng 8080 và các path health được phép truy cập bởi kubelet. Nếu Spring Security bảo vệ Actuator, cần cấp quy tắc phù hợp cho probe trên mạng nội bộ mà không mở các endpoint quản trị nhạy cảm.

Các giá trị `replicas`, CPU/memory, probe timing và grace period là ví dụ cần kiểm tra bằng tải thật. Đặc biệt, `startupProbe` nên đủ thời gian cho ứng dụng khởi tạo; với Kafka Streams có state restore lớn, hãy đo thời gian phục hồi và điều chỉnh.

Không bắt buộc tạo Kubernetes Service cho ứng dụng chỉ tiêu thụ message và không nhận request từ bên ngoài. Nếu cần expose REST endpoint, metrics scraping hoặc Interactive Queries, khai báo Service/network policy theo đúng mục đích. Lưu ý Service load balancing không tự định tuyến Interactive Queries đến instance sở hữu key.

## 14. Graceful shutdown để không ngắt xử lý đột ngột

Khi Kubernetes thay pod, nó gửi SIGTERM trước khi hết `terminationGracePeriodSeconds` và buộc dừng nếu tiến trình chưa thoát. Java nên là tiến trình chính của container để nhận tín hiệu này. Spring Boot xử lý việc đóng application context và dừng các thành phần lifecycle theo thứ tự.

Ví dụ:

~~~yaml
spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
~~~

Trên các phiên bản Spring Boot gần đây, graceful shutdown của embedded web server được bật mặc định; với dự án dùng phiên bản cũ cần xác nhận hoặc cấu hình `server.shutdown: graceful`. Timeout shutdown phải nhỏ hơn ngân sách `terminationGracePeriodSeconds`, có khoảng dự phòng cho sidecar/proxy và các bước dừng khác.

Khi một consumer đang xử lý message:

- Cần xác định handler hoàn tất, ack/commit offset hoặc transaction được đóng vào thời điểm nào.
- Không mặc định mọi binder đều bảo đảm không xử lý lại sau SIGTERM.
- Nếu tiến trình bị SIGKILL hoặc OOMKilled, message đang xử lý có thể được giao lại.
- Tác động phụ quan trọng cần idempotent hoặc dùng inbox/outbox/transaction phù hợp.
- Sau deploy phải kiểm tra consumer lag, queue depth và DLQ để phát hiện việc dừng khởi động lại chưa đúng.

Graceful shutdown giúp giảm gián đoạn, nhưng không thay thế kiểm thử crash. Producer dùng Supplier hoặc StreamBridge cũng cần chờ gửi message in-flight theo cấu hình binder.

## 15. Kafka Streams binder cần lưu ý thêm về state

Ứng dụng Kafka Streams có topology, application ID, task assignment và state store. Khi chạy nhiều replica:

- Các replica cùng tham gia một topology logic phải dùng cùng Kafka Streams `application.id`.
- Nếu có nhiều function processor độc lập trong cùng ứng dụng, có thể phải đặt application ID riêng cho từng processor.
- Mỗi instance có thư mục state cục bộ riêng; không mount cùng một RocksDB state directory cho nhiều pod.
- State có thể được dựng lại từ changelog topic sau khi mất local directory, nhưng quá trình restore tiêu tốn thời gian và mạng.
- Persistent volume có thể giúp tái sử dụng local state khi task/pod được đặt lại phù hợp, song cần chiến lược ownership và cleanup; volume không tự giải quyết rebalance.

Ví dụ cấu hình:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        streams:
          binder:
            applicationId: order-aggregate-v1
            brokers: ${KAFKA_BROKERS:kafka:9092}
            configuration:
              state.dir: /var/lib/kafka-streams
~~~

Nếu dùng `state.dir` như trên, mount một volume ghi được vào `/var/lib/kafka-streams` và đảm bảo UID/GID của Java có quyền. Không dùng chung một hostPath/RWO volume tùy tiện giữa các replica. Với pod nhiều replica có state khác nhau, cân nhắc StatefulSet hoặc volume strategy được vận hành kiểm chứng.

Với bài thử dùng state directory tạm trên từng pod, có thể thêm một `emptyDir` vào container trong manifest Deployment:

~~~yaml
spec:
  template:
    spec:
      securityContext:
        runAsUser: 10001
        runAsGroup: 10001
        fsGroup: 10001
      containers:
        - name: app
          volumeMounts:
            - name: kafka-streams-state
              mountPath: /var/lib/kafka-streams
      volumes:
        - name: kafka-streams-state
          emptyDir: {}
~~~

Đây là đoạn cấu hình bổ sung vào Deployment hiện có, không phải manifest Kubernetes độc lập. `emptyDir` mất khi pod bị xóa; Kafka Streams phải restore state từ changelog nếu state còn được lưu đúng trên Kafka. Trước production, kiểm tra thời gian restore và dung lượng ổ đĩa của node. Nếu dùng persistent volume, cần cấu hình quyền ghi và vòng đời volume phù hợp với task assignment.

Nếu cần Interactive Queries, mỗi Kafka Streams instance cần công bố `application.server` bằng host/port truy cập trực tiếp đến instance đó. Không đặt một địa chỉ Service load-balanced chung cho mọi replica làm metadata `HostInfo`, vì truy vấn theo key có thể được chuyển đến pod không sở hữu partition.

## 16. Rolling update, scaling và bảo đảm giao nhận

Container image mới thường được triển khai theo rolling update. Với Kafka consumer group, thêm/bớt replica có thể gây rebalance; với Kafka Streams, task có thể chuyển sang instance khác và restore state.

Quy trình triển khai nên có:

1. Build và kiểm thử JAR, tạo image có tag bất biến.
2. Scan image, publish lên registry và lưu digest.
3. Triển khai canary hoặc rolling update với số replica/phân vùng phù hợp.
4. Quan sát startup, health, consumer group membership, lag và lỗi binder.
5. Chờ chức năng nghiệp vụ xử lý được message mới, kiểm tra backlog.
6. Nếu cần rollback, triển khai lại image digest trước đó cùng cấu hình tương thích.

Với Kafka, số replica consumer hữu ích trong cùng group bị giới hạn bởi số partition cho các topic/task tương ứng; tăng pod quá số partition không tự tăng thông lượng xử lý message. Với Kafka Streams còn phải tính task assignment, RocksDB restore và standby replicas.

Rolling update có thể tạo bản tin được giao lại. Ngay cả khi binder dùng cơ chế transaction hoặc xử lý at-least-once theo cấu hình, side effect với hệ thống ngoài vẫn cần đánh giá riêng. Không tuyên bố end-to-end exactly-once chỉ vì image triển khai không gián đoạn.

Khi thay schema message, cần giữ compatibility giữa producer/consumer cũ và mới trong khoảng rollout. Nếu một phiên bản chỉ đọc schema mới được deploy trước khi tất cả producer chuyển đổi, consumer có thể lỗi deserialize và đẩy message vào DLQ.

## 17. Kiểm tra image sau build

Các lệnh dưới đây là ví dụ thao tác khi chạy trên máy có Docker và broker phù hợp:

~~~bash
docker image inspect order-consumer:1.0.0
docker run --rm --entrypoint java order-consumer:1.0.0 -version
docker run --rm --name order-consumer \
  --env KAFKA_BROKERS=kafka.internal:9092 \
  order-consumer:1.0.0
~~~

Với Dockerfile dùng `ENTRYPOINT ["java","-jar",...]`, đối số ghi sau tên image sẽ được truyền cho `java -jar`; để xem Java runtime phải ghi đè entrypoint bằng `--entrypoint java` như lệnh thứ hai.

Kiểm tra:

- Image có Java runtime phù hợp với bytecode.
- Tiến trình chạy bằng non-root UID.
- `docker logs` không lộ secret.
- Broker address được resolve từ trong container.
- Function definition và binding name đúng với cấu hình.
- Message test đi qua broker thật và có kết quả nghiệp vụ.
- SIGTERM làm ứng dụng dừng trong grace period.
- Image chạy được dưới CPU/memory limit giống production.

Không lấy trạng thái container `running` làm bằng chứng message đã được xử lý. Cần gửi một sự kiện có ID, theo dõi consumer và xác nhận kết quả ở output topic/queue hoặc cơ sở dữ liệu.

## 18. Bảo mật và chuỗi cung ứng image

Image đóng gói cả mã ứng dụng và dependency nên cũng là đơn vị cần kiểm soát lỗ hổng:

- Ưu tiên runtime image nhỏ và không chạy Java bằng root.
- Pin base image ở tag/digest tin cậy; định kỳ rebuild khi có bản vá.
- Dùng version/tag bất biến hoặc image digest khi deploy, tránh tag `latest` không kiểm soát.
- Quét CVE trong JAR dependency và cả hệ điều hành của image.
- Tạo và lưu SBOM nếu pipeline hỗ trợ.
- Ký image/attestation theo quy trình của tổ chức nếu cần.
- Giới hạn quyền push/pull registry; phân quyền release và rollback.
- Không chứa SSH key, kubeconfig, token, build cache có secret hoặc source không cần thiết trong runtime image.
- Dùng read-only root filesystem nếu ứng dụng và binder đã được cấp writable volume/tmp thích hợp.

Đặc biệt với Kafka SSL và RocksDB, read-only filesystem không có nghĩa là ứng dụng không cần ghi file. Cần mount đường dẫn phù hợp cho state, temp và các certificate được client sử dụng.

## 19. Sự cố đóng gói và triển khai thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra hoặc xử lý |
|---|---|---|
| `no main manifest attribute` khi `java -jar` | Copy nhầm `*-plain.jar` | Dùng `bootJar` và tên file rõ ràng |
| `UnsupportedClassVersionError` | JRE trong image thấp hơn Java compile target | Đồng bộ Java toolchain và runtime |
| Container khởi động nhưng không kết nối Kafka | Dùng `localhost:9092` bên trong container | Dùng broker DNS reachable và kiểm tra advertised listeners |
| Có kết nối bootstrap nhưng vẫn lỗi broker metadata | Kafka `advertised.listeners` trả host client không truy cập được | Sửa listener/advertised address ở broker |
| Không nhận message sau restart | Consumer group hoặc destination thay đổi | Kiểm tra binding, group và committed offsets |
| Pod `CrashLoopBackOff` | App lỗi cấu hình, secret thiếu, OOM hoặc liveness quá chặt | Kiểm tra logs, events, memory và probe |
| Pod `Running` nhưng lag tăng | Consumer chưa kết nối, bị pause, lỗi handler hoặc thiếu partition | Kiểm tra binder health, group assignment, lag/DLQ |
| Image lớn và push chậm | Một layer chứa toàn bộ fat JAR hoặc build context lớn | Dùng layered JAR/Buildpacks và `.dockerignore` |
| `Permission denied` với RocksDB | State dir/volume không ghi được bởi UID non-root | Đặt volume security context/quyền đúng |
| Shutdown bị SIGKILL | Grace period ngắn hoặc handler không dừng kịp | Điều chỉnh graceful timeout và kiểm tra in-flight |
| Readiness vẫn UP nhưng binder không xử lý | Probe chỉ phản ánh trạng thái Spring Boot chung | Bổ sung chỉ báo readiness phù hợp với binder |
| Rollback vẫn deserialize lỗi | Schema không tương thích giữa phiên bản | Thiết kế schema evolution và kiểm thử mixed-version |

## 20. Checklist phát hành ứng dụng

- Dependency Spring Boot, Spring Cloud và binder thuộc các phiên bản tương thích.
- `bootJar` tạo đúng executable JAR và lệnh `java -jar` chạy được.
- Image dùng Java runtime phù hợp và chạy bằng user không phải root.
- Chọn `bootBuildImage` hoặc Dockerfile có chiến lược cập nhật base image.
- Dùng tag bất biến/digest, ghi version và commit của bản phát hành.
- Không có secret trong JAR, Dockerfile, image layer hoặc log khởi động.
- Địa chỉ Kafka/RabbitMQ/Pulsar được truyền đúng lúc chạy và truy cập được từ network container.
- Binding name, destination, group và binder configuration được xác nhận.
- Có Actuator health endpoint, nhưng liveness/readiness được thiết kế theo tác dụng thực tế.
- Memory/CPU limit phù hợp với JVM và client/binder.
- Graceful shutdown và termination grace period đã được kiểm thử.
- Nếu dùng Kafka Streams, state directory và application ID đúng; state store có quyền ghi.
- Rollout có quan sát lag/backlog, retry, DLQ, rebalance và state restoration.
- Có smoke test sau deploy với message ID và kết quả nghiệp vụ.
- Có chiến lược rollback cùng kiểm tra compatibility của message schema.

Đóng gói ứng dụng Spring Cloud Stream không chỉ là đưa một JAR vào container. Một image đáng tin cậy cần chạy đúng Java runtime, đóng gói dependency nhất quán, nhận cấu hình broker từ môi trường, hỗ trợ shutdown và health check phù hợp, đồng thời đảm bảo các consumer/binder tiếp tục xử lý sau khi thay pod. Buildpacks và Dockerfile đều có thể tạo OCI image; lựa chọn nào cũng cần kiểm thử với broker thật và kiểm soát việc phát hành image.

## Tài liệu tham khảo

- [Spring Boot — Packaging OCI Images with Gradle](https://docs.spring.io/spring-boot/gradle-plugin/packaging-oci-image.html)
- [Spring Boot — Dockerfiles and Layered JARs](https://docs.spring.io/spring-boot/reference/packaging/container-images/dockerfiles.html)
- [Spring Boot — Kubernetes Probes and Health Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Boot — Graceful Shutdown](https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html)
- [Spring Cloud Stream — Kafka Binder Configuration](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/config-options.html)
- [Spring Cloud Stream — Kafka Streams Binder Configuration](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/configuration-options.html)
- [Spring Cloud Stream — Kafka Streams Binder Programming Model](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/programming-model.html)

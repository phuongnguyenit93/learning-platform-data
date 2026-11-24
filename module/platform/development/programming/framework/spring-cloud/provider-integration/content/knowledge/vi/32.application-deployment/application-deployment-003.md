# Đóng gói JAR hoặc container và kiểm tra điều kiện môi trường chạy

Một ứng dụng Spring Boot chạy ổn trên máy phát triển chưa chắc sẽ khởi động đúng trong môi trường staging hoặc production. JAR có thể được build bằng JDK khác với JRE trên máy chủ; container có thể thiếu chứng thư CA, sai kiến trúc CPU, thiếu biến môi trường, không có quyền ghi thư mục tạm hoặc bị giới hạn bộ nhớ thấp hơn cấu hình JVM. Vì vậy, đóng gói ứng dụng phải đi cùng việc xác định rõ hợp đồng runtime và kiểm tra các điều kiện thực tế trước khi đưa traffic vào.

Spring Boot có thể được đóng gói thành executable JAR hoặc OCI container image. JAR phù hợp khi nền tảng cung cấp sẵn Java runtime; container image phù hợp khi muốn đóng gói runtime cùng ứng dụng và triển khai nhất quán trên Kubernetes, ECS, Cloud Run hoặc nền tảng container khác. Dù chọn cách nào, artifact cần có phiên bản rõ ràng, cấu hình được cấp từ môi trường, danh tính workload được gắn đúng và quy trình health check/shutdown tương thích với nền tảng.

Bài học thuộc chương **Triển khai ứng dụng** của mô-đun **SPRING_CLOUD_PROVIDER_INTEGRATION**. Mô-đun thực hành tích hợp Spring Boot với dịch vụ managed của AWS, Azure và Google Cloud qua các thư viện Spring Cloud tương ứng; học cấu hình danh tính và quyền, truy cập storage, messaging, dữ liệu, bảo vệ secret, kiểm thử tích hợp và đánh giá khác biệt giữa các cloud provider. Bài này tập trung vào đóng gói executable JAR/container và xác minh Java runtime, cấu hình, network, identity, resource limits, probes và shutdown trước khi ứng dụng phục vụ nghiệp vụ.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt executable JAR với OCI container image và chọn hình thức phù hợp.
- Cấu hình Maven hoặc Gradle để tạo executable JAR của Spring Boot.
- Kiểm tra manifest, dependency và nội dung archive trước khi phát hành.
- Tạo container image bằng Cloud Native Buildpacks hoặc Docker multi-stage build.
- Tối ưu layer của Spring Boot JAR để tận dụng build cache.
- Chọn JRE, kiến trúc CPU và hệ điều hành tương thích với artifact.
- Cấu hình user không phải root, filesystem và cổng mạng trong container.
- Truyền profile, endpoint, secret reference và workload identity từ môi trường chạy.
- Điều chỉnh JVM memory/CPU theo giới hạn container.
- Cấu hình startup, liveness và readiness probe bằng Spring Boot Actuator.
- Cho ứng dụng shutdown graceful khi nền tảng gửi SIGTERM.
- Thực hiện smoke test và xác minh điều kiện runtime trước khi nhận traffic.

## 2. JAR và container image khác nhau thế nào?

**Executable JAR** chứa bytecode ứng dụng, dependency và Spring Boot launcher. Máy chạy phải có Java runtime tương thích. JAR không chứa toàn bộ hệ điều hành hoặc JRE; cùng một JAR có thể chạy ở nhiều môi trường nếu runtime và cấu hình phù hợp.

**OCI container image** đóng gói ứng dụng cùng runtime và filesystem cần thiết. Host vẫn cung cấp kernel và container runtime, nhưng không cần cài Java riêng trên host. Image có thể được chạy bởi Docker, containerd hoặc nền tảng container hỗ trợ OCI.

| Tiêu chí | Executable JAR | Container image |
|---|---|---|
| Java runtime | Máy đích phải cài JRE/JDK tương thích | Thường được đóng gói trong image |
| Kích thước phát hành | Chủ yếu là JAR và dependency | Gồm base image, runtime và ứng dụng |
| Cấu hình | File, environment, system properties | Environment, mounted file/secret, platform config |
| Cô lập runtime | Phụ thuộc cấu hình máy chủ | Có filesystem/process/network namespace |
| Phân phối | Artifact repository, VM, service | OCI registry, orchestrator, container platform |
| Kiểm soát hệ điều hành | Vận hành máy chủ quản lý | Image builder/base image và platform quản lý |
| Health check | Service manager hoặc platform | Container runtime/orchestrator probe |
| Phù hợp | VM, bare metal, PaaS nhận JAR | Kubernetes, ECS, Cloud Run, container apps |

Container không tự động làm ứng dụng an toàn hoặc portable. Image vẫn có thể chứa secret, chạy bằng root, dùng base image lỗi thời hoặc thiếu CA certificate. JAR cũng có thể triển khai an toàn nếu Java runtime, OS, quyền file và cấu hình được quản lý tốt.

## 3. Chuẩn bị dự án Spring Boot để đóng gói

Một dự án Spring Boot thông thường có:

- Main application class được đánh dấu SpringBootApplication.
- Dependency starter cho web, database, messaging hoặc cloud SDK.
- Cấu hình build plugin Spring Boot Maven hoặc Gradle.
- Test và cấu hình profile cần thiết.
- Version Java mục tiêu được khai báo nhất quán.

Ví dụ cấu trúc Maven:

~~~text
orders-service/
  pom.xml
  src/
    main/
      java/
      resources/
        application.yml
    test/
      java/
  Dockerfile
  .dockerignore
~~~

Ví dụ main class:

~~~java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrdersApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
~~~

Chỉ có main class không đủ để tạo executable JAR. Build phải chạy Spring Boot repackage goal hoặc Gradle bootJar task để thêm launcher và tổ chức dependency đúng định dạng.

### 3.1. Chọn Java version

Phiên bản Java dùng để biên dịch và phiên bản Java dùng để chạy phải tương thích. Nếu compile bytecode cho Java 21 thì runtime Java 17 không thể chạy class đó. Chọn một Java baseline mà tất cả môi trường deploy đều hỗ trợ và khai báo nhất quán trong Maven/Gradle, CI image, Docker base image và platform runtime.

Ví dụ Maven dùng Java 21:

~~~xml
<properties>
    <java.version>21</java.version>
</properties>
~~~

Ví dụ Gradle:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
~~~

Toolchain giúp build dùng đúng JDK đã chọn. Runtime vẫn cần Java version tương thích. Không suy luận runtime version chỉ từ máy build.

## 4. Tạo executable JAR bằng Maven

Spring Boot Maven Plugin thực hiện repackage để tạo archive có thể chạy bằng java -jar. Nếu dự án dùng spring-boot-starter-parent, parent đã cấu hình execution cho goal này. Nếu không dùng parent, cần khai báo goal repackage trong execution của plugin.

Ví dụ cấu hình plugin:

~~~xml
<build>
    <finalName>orders-service</finalName>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
            <executions>
                <execution>
                    <goals>
                        <goal>repackage</goal>
                    </goals>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
~~~

Build và kiểm thử:

~~~bash
./mvnw clean verify
~~~

Kết quả executable JAR nằm trong:

~~~text
target/orders-service.jar
~~~

Chạy thử:

~~~bash
java -jar target/orders-service.jar
~~~

Trong CI, chạy test và verify trước khi publish artifact. Không dùng cờ skipTests cho release build nếu pipeline chưa có một stage test độc lập tương đương.

### 4.1. Kiểm tra JAR đã được repackage

Kiểm tra file tồn tại và dung lượng:

~~~bash
ls -lh target/orders-service.jar
~~~

Liệt kê nội dung archive:

~~~bash
jar tf target/orders-service.jar
~~~

Executable JAR của Spring Boot thường có:
- META-INF/MANIFEST.MF.
- org/springframework/boot/loader hoặc package loader tương ứng phiên bản.
- BOOT-INF/classes chứa application classes và resources.
- BOOT-INF/lib chứa dependency JAR.

Đọc manifest:

~~~bash
unzip -p target/orders-service.jar META-INF/MANIFEST.MF
~~~

Manifest của executable JAR có Main-Class trỏ tới Spring Boot launcher và Start-Class trỏ tới main application class. Tên launcher package thay đổi theo phiên bản Spring Boot; không hardcode tên launcher cũ trong script kiểm tra.

Nếu archive chỉ có classes và dependency theo layout JAR thông thường, lệnh java -jar có thể báo thiếu Main-Class hoặc không tìm thấy launcher. Kiểm tra plugin repackage và build output thay vì sửa manifest thủ công.

## 5. Tạo executable JAR bằng Gradle

Spring Boot Gradle Plugin cung cấp task bootJar. Khi plugin được áp dụng, task này đóng gói application classes, resources, dependency và Spring Boot loader.

Ví dụ build:

~~~bash
./gradlew clean test bootJar
~~~

Kết quả thường nằm trong:

~~~text
build/libs/orders-service.jar
~~~

Có thể đặt tên archive ổn định:

~~~groovy
tasks.named('bootJar') {
    archiveFileName = 'orders-service.jar'
}
~~~

Chạy thử:

~~~bash
java -jar build/libs/orders-service.jar
~~~

Phân biệt bootJar và jar:
- bootJar tạo executable Spring Boot archive.
- jar tạo archive Java thông thường.
- Một dự án có thể tạo cả hai nếu cấu hình task cho phép.

Nếu pipeline lấy nhầm file jar thông thường để deploy, ứng dụng có thể không chạy bằng java -jar. Hãy chỉ định rõ artifact path và kiểm tra manifest trong release job.

## 6. Kiểm tra nội dung và metadata artifact

Trước khi phát hành, nên xác minh:

- Tên artifact và version đúng với release.
- JAR được repackage và có launcher.
- Dependency cần cho runtime được đóng gói.
- Không có devtools hoặc dependency chỉ dành cho test trong artifact production.
- Profile production không bị đóng cứng vào file build.
- Không có password, private key, access key hoặc file .env trong archive.
- Metadata build cho biết commit, version, build time và Java baseline.
- Checksum của artifact được lưu để đối chiếu khi deploy.

Không nhúng secret vào application.yml trong JAR. Artifact thường được lưu ở repository, cache CI hoặc registry có nhiều người đọc hơn secret manager. Nếu secret được đóng gói vào JAR, thay đổi secret buộc phải build lại artifact và secret có thể tồn tại trong lịch sử artifact.

Có thể kiểm tra dependency tree để phát hiện dependency không mong muốn:

~~~bash
./mvnw dependency:tree
~~~

Hoặc với Gradle:

~~~bash
./gradlew dependencies
~~~

Kiểm tra dependency không thay thế vulnerability scanning. Dùng công cụ dependency scan/SCA của pipeline và xử lý các CVE theo policy của tổ chức.

## 7. Đóng gói container bằng Cloud Native Buildpacks

Spring Boot Maven Plugin và Gradle Plugin có thể tạo OCI image từ executable JAR bằng Cloud Native Buildpacks (CNB). Buildpack phát hiện ứng dụng, chọn runtime và tạo image theo builder đã cấu hình. Cách này không yêu cầu tự viết Dockerfile cho trường hợp thông thường.

Maven:

~~~bash
./mvnw spring-boot:build-image \
  -Dspring-boot.build-image.imageName=registry.example.com/orders-service:1.0.0
~~~

Gradle:

~~~bash
./gradlew bootBuildImage \
  --imageName=registry.example.com/orders-service:1.0.0
~~~

Buildpack builder cần truy cập Docker daemon hoặc môi trường tương thích để tạo image. Image do Spring Boot build-image tạo chạy bằng user không phải root theo cấu hình mặc định của buildpack.

Sau khi build, kiểm tra image:

~~~bash
docker image inspect registry.example.com/orders-service:1.0.0
docker image ls registry.example.com/orders-service
~~~

Chạy thử:

~~~bash
docker run --rm -p 8080:8080 \
  -e SPRING_PROFILES_ACTIVE=staging \
  registry.example.com/orders-service:1.0.0
~~~

Buildpacks phù hợp khi muốn giảm lượng Dockerfile phải tự quản lý. Tuy nhiên, vẫn cần chọn builder/base image đáng tin cậy, cập nhật builder, kiểm tra image, cấu hình runtime và lưu image theo tag/digest bất biến.

## 8. Đóng gói container bằng Docker multi-stage build

Docker multi-stage build tách giai đoạn build JAR và giai đoạn chạy ứng dụng. Maven/JDK chỉ cần ở build stage; runtime image chỉ chứa JRE và JAR.

Ví dụ Dockerfile:

~~~dockerfile
FROM maven:3.9-eclipse-temurin-21 AS build
WORKDIR /workspace

COPY pom.xml .
COPY src ./src

RUN mvn -B verify

FROM eclipse-temurin:21-jre-jammy AS runtime
WORKDIR /app

RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app \
       --home-dir /nonexistent --shell /usr/sbin/nologin app

COPY --from=build --chown=10001:10001 \
    /workspace/target/orders-service.jar /app/app.jar

USER 10001:10001

EXPOSE 8080

ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Dockerfile giả định Maven finalName đã được đặt thành orders-service. Nếu tên artifact khác, cập nhật đường dẫn COPY. Build stage chạy verify; nếu dự án dùng Maven Wrapper hoặc cần file cấu hình Maven riêng, copy các file đó vào build stage và dùng wrapper.

Build image:

~~~bash
docker build --pull \
  -t registry.example.com/orders-service:1.0.0 .
~~~

Chạy container:

~~~bash
docker run --rm -p 8080:8080 \
  -e SPRING_PROFILES_ACTIVE=staging \
  registry.example.com/orders-service:1.0.0
~~~

### 8.1. Vì sao dùng multi-stage?

- Build tool và source code không nằm trong runtime image.
- Runtime image nhỏ hơn và có ít package hơn.
- Build và runtime có thể chọn base image riêng.
- Có thể cache dependency/build layer.
- Giảm bề mặt tấn công so với image có cả JDK, Maven và công cụ debug.

Không cài thêm shell, curl, package manager hoặc editor vào runtime image nếu ứng dụng không cần chúng. Một image nhỏ vẫn cần được cập nhật và scan định kỳ.

### 8.2. Dùng .dockerignore

Không gửi file không cần thiết vào Docker build context:

~~~text
.git
.gitignore
.idea
.vscode
target
build
.gradle
.mvn/wrapper/maven-wrapper.jar
.env
.env.*
*.log
secrets/
~~~

Điều chỉnh .dockerignore theo quy trình build. Nếu build stage cần Maven Wrapper, không loại bỏ .mvn hoặc mvnw. Không copy thư mục secrets hoặc file .env vào build context.

## 9. Tối ưu layer của Spring Boot JAR

Spring Boot executable JAR có thể được chia thành các layer. Dependency ít thay đổi thường nằm ở layer riêng; application classes thay đổi thường xuyên nằm ở layer cuối. Khi chỉ đổi code, Docker có thể tái sử dụng layer dependency từ build cache.

Các layer mặc định thường gồm:
- dependencies: dependency không phải SNAPSHOT.
- spring-boot-loader: Spring Boot loader.
- snapshot-dependencies: dependency có phiên bản SNAPSHOT.
- application: module dependencies, classes và resources của ứng dụng.

Có thể xem danh sách layer:

~~~bash
java -Djarmode=tools -jar target/orders-service.jar list-layers
~~~

Trích xuất layer:

~~~bash
java -Djarmode=tools -jar target/orders-service.jar \
  extract --layers --destination target/extracted
~~~

Sau đó dùng Dockerfile nhiều stage để copy các thư mục layer theo thứ tự ổn định. Cách làm chính xác phụ thuộc phiên bản Spring Boot và jarmode tools được đóng gói trong archive; tham khảo Dockerfile mẫu trong tài liệu Spring Boot tương ứng với version dự án.

Không tự ý thay đổi thứ tự layer. Đặt dependency ít đổi trước và application layer sau giúp tận dụng cache tốt hơn. Nếu dự án không cần tối ưu cache, buildpacks hoặc Dockerfile copy một JAR duy nhất thường đơn giản hơn.

## 10. Cấu hình runtime image và user

Container nên chạy bằng user không phải root. Nếu process bị khai thác, quyền của attacker trong container sẽ bị giới hạn hơn.

Ví dụ trong Dockerfile:

~~~dockerfile
RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app \
       --home-dir /nonexistent --shell /usr/sbin/nologin app

COPY --chown=10001:10001 target/orders-service.jar /app/app.jar
USER 10001:10001
~~~

Một số image nền tảng đã tạo sẵn non-root user. Đọc tài liệu base image và dùng đúng UID/GID. Nếu orchestrator áp dụng arbitrary UID, bảo đảm thư mục cần ghi có quyền phù hợp.

Các nguyên tắc khác:
- Dùng base image JRE chính thức hoặc publisher được tin cậy.
- Pin tag có version, tốt hơn nữa là digest trong release production.
- Rebuild định kỳ để nhận bản vá OS/JRE.
- Không lưu secret trong Dockerfile ARG, ENV hoặc image layer.
- Không chạy process bằng privileged mode.
- Hạn chế Linux capabilities và dùng read-only root filesystem nếu ứng dụng hỗ trợ.
- Chỉ mở đúng port ứng dụng cần.

## 11. Điều kiện Java runtime và hệ điều hành

Một JAR không phụ thuộc trực tiếp vào hệ điều hành như binary native, nhưng runtime vẫn có các điều kiện cần kiểm tra:

| Điều kiện | Cách xác minh | Lỗi thường gặp |
|---|---|---|
| Java version | java -version | UnsupportedClassVersionError |
| Java vendor/distribution | java -XshowSettings:properties -version | Khác biệt CA bundle hoặc native behavior |
| CPU architecture | uname -m hoặc docker image inspect | Image amd64 chạy trên arm64 không có emulation |
| OS libraries | ldd --version, package inventory | Thiếu native library hoặc libc |
| Timezone | date, cấu hình TZ | Timestamp/cron sai múi giờ |
| Locale/encoding | java -XshowSettings:properties -version | Encoding khác kỳ vọng |
| CA certificates | Kiểm tra trust store và TLS handshake | SSLHandshakeException |
| DNS/network | nslookup/getent và kết nối endpoint | UnknownHostException, timeout |
| File permission | id, ls -ld, kiểm tra volume | AccessDeniedException |
| Memory/CPU | container limits và process metrics | OOMKilled, throttling, latency tăng |

Nếu dùng JNI, native compression, Netty native transport, image processing hoặc thư viện phụ thuộc libc, phải kiểm tra OS và kiến trúc image. Alpine dùng musl libc, trong khi nhiều native dependency được build cho glibc; chọn Alpine chỉ vì image nhỏ có thể làm phát sinh lỗi runtime.

### 11.1. Kiểm tra Java version và JVM flags

Lệnh:

~~~bash
java -version
java -XshowSettings:properties -version
~~~

Có thể kiểm tra class file target bằng javap hoặc công cụ phân tích bytecode nếu cần. Đừng chỉ nhìn version JDK trên máy build; kiểm tra version Java thực tế trong runtime container.

### 11.2. CA certificates và TLS

Các cloud SDK thường kết nối HTTPS tới API managed. Runtime cần trust store có CA phù hợp và thời gian hệ thống chính xác. Nếu dùng private CA, mount certificate theo cơ chế được platform quản lý và cấu hình trust store riêng.

Không tắt hostname verification hoặc trust mọi certificate để sửa lỗi TLS. Kiểm tra certificate chain, hostname, DNS, thời gian hệ thống và CA bundle trước.

## 12. Cấu hình môi trường Spring Boot

Cùng một artifact nên chạy được ở dev, staging và production bằng externalized configuration. Những giá trị thường được cấp khi deploy:

- Active profile.
- Server port và management endpoint.
- Resource endpoint, queue/topic/container name.
- Region, project ID hoặc resource identifier.
- Feature flags và timeout.
- Secret reference hoặc mounted secret.
- JVM options và resource limits.

Ví dụ application.yml mặc định:

~~~yaml
spring:
  application:
    name: orders-service
  profiles:
    default: local

server:
  port: 8080
  shutdown: graceful

app:
  cloud:
    provider: local
    messaging:
      destination: orders-local
    storage:
      container: orders-local
~~~

Production có thể inject:

~~~bash
SPRING_PROFILES_ACTIVE=production
SERVER_PORT=8080
APP_CLOUD_PROVIDER=azure
APP_CLOUD_MESSAGING_DESTINATION=orders-prod-events
APP_CLOUD_STORAGE_CONTAINER=orders-prod-checkpoints
~~~

Spring Boot relaxed binding ánh xạ environment variables sang property. Không cần build một JAR riêng cho từng environment. Không đưa secret value vào image hoặc file cấu hình trong Git; dùng workload identity hoặc secret manager.

### 12.1. Profile không thay thế secret management

Profile chỉ chọn nhóm cấu hình phù hợp môi trường. Không đặt password production trong application-prod.yml được commit vào repository. File profile có thể chứa endpoint/name không nhạy cảm; credential lấy từ Managed Identity, IAM role, Workload Identity hoặc secret volume.

### 12.2. Cổng ứng dụng và cổng management

server.port quyết định cổng HTTP chính. Nếu đặt management.server.port riêng, Actuator có thể lắng nghe trên cổng khác. Khi cấu hình probe hoặc load balancer, phải dùng đúng port và đảm bảo endpoint được expose có kiểm soát.

EXPOSE trong Dockerfile chỉ là metadata mô tả port mà container sử dụng; nó không tự publish port ra host. Khi chạy local cần mapping -p hostPort:containerPort hoặc cấu hình port mapping tương ứng trên platform.

## 13. JVM memory và giới hạn container

Container có thể bị giới hạn memory và CPU. JVM hiện đại nhận biết container limits, nhưng ứng dụng vẫn phải được cấu hình phù hợp với tổng bộ nhớ khả dụng.

Bộ nhớ process không chỉ là Java heap. Nó còn gồm:
- Metaspace và class metadata.
- Thread stack.
- Direct buffer/NIO.
- JIT code cache.
- Native memory của TLS, compression và thư viện native.
- JVM overhead và memory-mapped files.

Nếu đặt Xmx gần bằng memory limit, process có thể bị OOMKilled dù heap chưa đạt Xmx vì native memory không còn đủ.

Có thể đặt phần trăm RAM tối đa cho heap:

~~~bash
JAVA_TOOL_OPTIONS="-XX:MaxRAMPercentage=70 -XX:InitialRAMPercentage=25"
~~~

Giá trị phần trăm chỉ là ví dụ ban đầu; đo tải thực tế, số thread, direct buffer và memory usage trước khi chốt. Tránh đặt cả -Xmx cố định và MaxRAMPercentage một cách mâu thuẫn.

Khi container bị OOMKilled:
1. Kiểm tra memory limit và exit reason.
2. Xem heap usage, GC log, thread count và direct buffer.
3. Kiểm tra memory leak hoặc payload/batch quá lớn.
4. Tăng limit hoặc điều chỉnh heap/native allocation theo dữ liệu đo.
5. Không đơn giản tăng Xmx lên sát limit.

## 14. CPU, thread và concurrency

CPU limit thấp có thể làm GC, JIT và request processing chậm. Khi thread pool quá lớn, ứng dụng có thể tiêu thụ stack memory và context switching cao. Cần xem:
- CPU request/limit của container.
- Số core JVM nhận diện.
- Tomcat/Jetty/Netty thread pool.
- Database connection pool.
- Kafka/Event Hubs/Service Bus consumer concurrency.
- Batch size và số message xử lý song song.

Không đặt thread count theo số CPU của máy phát triển. Container có thể chỉ được cấp một phần CPU của node. Dùng load test để xác định throughput, latency, CPU throttling và connection pool hợp lý.

## 15. Health check với Spring Boot Actuator

Thêm dependency Actuator:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~

Spring Boot cung cấp health endpoint. Với Kubernetes, Spring Boot có health group riêng cho liveness và readiness:

- /actuator/health/liveness: process có thể tiếp tục chạy hay không.
- /actuator/health/readiness: instance có sẵn sàng nhận traffic hay không.
- /actuator/health: health tổng hợp, có thể bao gồm các indicator khác tùy cấu hình.

Cấu hình:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info
  endpoint:
    health:
      probes:
        enabled: true
      show-details: never
      group:
        readiness:
          include: readinessState
~~~

Health endpoint có thể chứa thông tin về dependency hoặc trạng thái nội bộ. Chỉ expose endpoint cần thiết và giữ show-details ở mức phù hợp. Không expose env, configprops hoặc heapdump ra public ingress.

### 15.1. Liveness không nên phụ thuộc cloud service bên ngoài

Liveness trả lời: process có còn hoạt động và có thể tiến triển không? Nếu database hoặc messaging service tạm thời mất kết nối, restart tất cả pod không khắc phục được lỗi shared dependency và có thể tạo cascading failure.

Readiness trả lời: instance này có thể nhận traffic ngay lúc này không? Có thể bổ sung dependency bắt buộc vào readiness group nếu quyết định đưa instance ra khỏi traffic khi dependency không sẵn sàng. Cần cân nhắc kỹ với dependency dùng chung hoặc có circuit breaker/fallback.

## 16. Startup, liveness và readiness probe trên Kubernetes

Ba loại probe có mục đích khác nhau:

| Probe | Câu hỏi | Hành động khi thất bại |
|---|---|---|
| Startup | Ứng dụng đã khởi động xong chưa? | Sau số lần fail cho phép, container bị restart |
| Liveness | Process có bị deadlock hoặc mất khả năng tiến triển không? | Container bị restart |
| Readiness | Instance có thể nhận request không? | Pod bị loại khỏi endpoint phục vụ traffic |

Ví dụ Deployment:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-service
spec:
  replicas: 3
  selector:
    matchLabels:
      app: orders-service
  template:
    metadata:
      labels:
        app: orders-service
    spec:
      terminationGracePeriodSeconds: 45
      containers:
        - name: orders-service
          image: registry.example.com/orders-service:1.0.0
          ports:
            - name: http
              containerPort: 8080
          env:
            - name: SPRING_PROFILES_ACTIVE
              value: production
          resources:
            requests:
              cpu: 250m
              memory: 512Mi
            limits:
              cpu: "1"
              memory: 1Gi
          startupProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
            failureThreshold: 30
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 3
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 3
~~~

Startup probe cho ứng dụng thời gian khởi tạo trước khi liveness/readiness bắt đầu. Readiness fail sẽ ngừng gửi traffic tới pod; liveness fail sẽ restart container. Giá trị trong ví dụ cần được điều chỉnh theo thời gian startup, tải và SLA của dịch vụ.

Nếu management server dùng port riêng, sửa port probe hoặc cấu hình health group bổ sung trên main server port. Một health endpoint trên management port có thể healthy dù HTTP server chính không hoạt động đúng; kiểm tra đường đi thực tế của request.

## 17. Graceful shutdown và xử lý SIGTERM

Khi Kubernetes hoặc container platform dừng instance, runtime thường gửi SIGTERM rồi chờ grace period trước khi kill process. Spring Boot hỗ trợ graceful shutdown cho embedded web server. Cấu hình:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s
~~~

Trong thời gian shutdown:
- Ngừng nhận request mới.
- Cho request đang xử lý hoàn tất trong thời gian cho phép.
- Dừng listener/worker theo lifecycle.
- Đóng connection pool và SDK client.
- Flush telemetry/log nếu có thể.
- Thoát process trước khi orchestrator hết termination grace period.

terminationGracePeriodSeconds của pod phải lớn hơn shutdown timeout và thời gian platform cần để drain traffic. Nếu có preStop hook, tính cả thời gian hook vào tổng grace period.

Với message consumer, shutdown phải dừng nhận message mới, hoàn tất hoặc abandon message đang xử lý theo semantics của broker và ACK/commit đúng thời điểm. Không ACK message chỉ vì process đang shutdown.

## 18. File system, writable directory và container security context

Nhiều container platform cho phép dùng read-only root filesystem. Nếu ứng dụng cần ghi file tạm, chỉ định thư mục writable riêng như /tmp hoặc volume mount. Không ghi log vào file trong container nếu platform thu log từ stdout/stderr.

Ví dụ Docker run với root filesystem read-only và tmpfs cho /tmp:

~~~bash
docker run --rm \
  --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,size=64m \
  -p 8080:8080 \
  registry.example.com/orders-service:1.0.0
~~~

Nếu ứng dụng cần ghi upload hoặc file nghiệp vụ, mount volume/object storage phù hợp; không dựa vào writable layer của container vì dữ liệu có thể mất khi container bị thay thế.

Trên Kubernetes, có thể cấu hình:

~~~yaml
securityContext:
  runAsNonRoot: true
  runAsUser: 10001
  runAsGroup: 10001
  allowPrivilegeEscalation: false
  readOnlyRootFilesystem: true
  capabilities:
    drop:
      - ALL
~~~

Cần bảo đảm image và volume permissions tương thích UID/GID. Nếu dùng volume có quyền ghi, thiết lập fsGroup hoặc ownership theo hướng dẫn của storage driver và security policy.

## 19. Network, DNS, TLS và workload identity

Một container chạy được chưa có nghĩa đã truy cập được dịch vụ managed. Trước khi nhận traffic, kiểm tra:

- DNS resolve đúng hostname.
- Egress/network policy cho phép kết nối tới endpoint.
- Private endpoint, route table, firewall và security group đúng.
- TLS certificate chain được trust.
- Proxy variables nếu môi trường yêu cầu proxy.
- Managed Identity, IAM role hoặc Workload Identity được gắn đúng workload.
- Runtime principal có đúng data-plane role.
- Token endpoint/metadata service có thể truy cập theo platform.
- Không có credential tĩnh bị đóng gói vào image.

Không kiểm tra identity bằng cách in access token hoặc credential vào log. Smoke test nên thực hiện một thao tác data-plane tối thiểu trong resource test hoặc một API read-only phù hợp.

### 19.1. Phân biệt lỗi cấu hình và lỗi tạm thời

| Triệu chứng | Hướng kiểm tra |
|---|---|
| UnknownHostException | DNS, hostname và private DNS zone |
| Connect timed out | Egress, firewall, route, private endpoint |
| SSLHandshakeException | CA trust store, hostname, system clock |
| 401/403 | Workload identity, token audience/issuer, role assignment |
| 404 | Resource name, endpoint, environment output |
| Connection pool exhausted | Pool size, timeout, request concurrency |
| Throttling/429 | Service quota, retry/backoff, concurrency |
| OOMKilled | Container memory limit và JVM heap/native memory |

Không retry vô hạn cho lỗi sai endpoint hoặc thiếu quyền. Retry có backoff cho lỗi transient; lỗi cấu hình phải fail fast hoặc chuyển readiness sang trạng thái không sẵn sàng.

## 20. Log, metrics và thông tin build

Ứng dụng container thường ghi log ra stdout/stderr để platform thu thập. Tránh phụ thuộc file log cục bộ trong filesystem ephemeral.

Nên có:
- Application version và Git commit.
- Build time và Java version.
- Environment/service name.
- Request correlation/trace ID.
- JVM heap, GC pause, thread và CPU metrics.
- Startup duration và readiness transition.
- Dependency latency/error rate.
- Container restart/OOM events.
- Image digest và SBOM liên quan release.

Không đưa secret, access token, password, authorization header hoặc toàn bộ environment vào log. Health endpoint và info endpoint phải được giới hạn quyền truy cập, chỉ công bố thông tin phù hợp.

## 21. Kiểm tra container image và artifact trước phát hành

Sau khi build image:

~~~bash
docker image inspect registry.example.com/orders-service:1.0.0
docker history registry.example.com/orders-service:1.0.0
docker run --rm registry.example.com/orders-service:1.0.0 --version
~~~

Lệnh --version chỉ hoạt động nếu ứng dụng có hỗ trợ tham số này; nếu không, kiểm tra image metadata và endpoint health sau khi start.

Các bước kiểm tra nên có:
1. Build từ source commit đã xác định.
2. Chạy unit/integration test.
3. Scan dependency và base image.
4. Kiểm tra user, entrypoint, port và filesystem.
5. Kiểm tra không có secret trong image layers.
6. Sinh SBOM và lưu cùng release metadata.
7. Gắn tag bất biến và lưu digest.
8. Ký image nếu supply-chain policy yêu cầu.
9. Deploy staging bằng đúng image digest đã kiểm thử.
10. Chạy smoke test trước khi promote production.

Không dùng tag latest làm định danh duy nhất cho production. Một tag có thể trỏ tới digest khác sau lần push mới; pin digest giúp deployment xác định chính xác nội dung image.

## 22. Kiểm thử điều kiện môi trường chạy

| Kịch bản | Cách kiểm thử | Kết quả mong đợi |
|---|---|---|
| JAR executable | Chạy java -jar trong runtime JRE | Application context khởi động |
| Java version không tương thích | Chạy artifact bằng JRE thấp hơn target | Pipeline/runtime phát hiện lỗi version |
| JAR thiếu dependency | Kiểm tra archive và startup | Lỗi classpath được phát hiện trước release |
| Container non-root | Inspect user hoặc chạy id trong container | Process không có UID 0 |
| Image architecture | Inspect platform/manifest | Phù hợp node architecture |
| Config thiếu | Bỏ biến endpoint/profile bắt buộc | App fail fast hoặc readiness fail |
| Secret missing | Không mount secret reference trong test | Không log secret; lỗi cấu hình rõ |
| DNS/network lỗi | Chạy trong network test bị giới hạn | Smoke test phát hiện lỗi |
| IAM/RBAC thiếu | Dùng workload identity thiếu role | Data-plane operation bị từ chối |
| Memory limit thấp | Giới hạn container memory trong test | OOM và heap behavior được quan sát |
| Startup lâu | Dùng startup probe với thời gian phù hợp | Không restart sớm khi app đang khởi tạo |
| Readiness false | Tạm vô hiệu dependency bắt buộc trong test | Pod không nhận traffic |
| Liveness false | Tạo trạng thái process không thể tiến triển trong test | Orchestrator restart theo policy |
| SIGTERM | Dừng container trong lúc có request | Request đang chạy được drain trong grace period |
| Read-only filesystem | Chạy container với rootfs read-only | App chỉ ghi vào path được phép |
| TLS CA thiếu | Dùng test endpoint với CA không được trust | TLS failure được phát hiện rõ |
| Image rollback | Deploy digest trước đó | Phiên bản cũ có thể phục hồi |

Thử lỗi môi trường trong test/staging riêng. Không chủ động thu hồi role, xóa resource hoặc gây OOM trên workload production để kiểm tra.

## 23. Quy trình phát hành đề xuất

Một release pipeline có thể đi theo trình tự:

~~~mermaid
flowchart TD
    SRC["Source commit"] --> BUILD["Build executable JAR"]
    BUILD --> TEST["Unit and integration tests"]
    TEST --> PACKAGE["Inspect JAR and metadata"]
    PACKAGE --> IMAGE["Build OCI image"]
    IMAGE --> SCAN["Scan image and dependencies"]
    SCAN --> PUBLISH["Publish image and digest"]
    PUBLISH --> DEPLOY["Deploy staging"]
    DEPLOY --> RUNTIME["Verify Java, config, identity, network"]
    RUNTIME --> HEALTH["Probe and smoke tests"]
    HEALTH --> APPROVE["Promote release"]
    APPROVE --> PROD["Deploy production"]
~~~

Build một lần rồi promote cùng artifact/image digest qua các môi trường. Chỉ thay cấu hình runtime theo environment; không build lại JAR với endpoint hoặc secret production.

Khi rollback, deploy digest đã được kiểm thử trước đó. Đảm bảo schema database, event contract và resource endpoint vẫn tương thích với phiên bản cũ.

## 24. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| no main manifest attribute | JAR chưa được repackage | Kiểm tra Spring Boot Maven/Gradle plugin |
| UnsupportedClassVersionError | Runtime Java thấp hơn bytecode target | Đồng bộ JDK/JRE version |
| ClassNotFoundException | Dependency không được đóng gói hoặc bị exclude | Kiểm tra dependency tree và BOOT-INF/lib |
| Container exits immediately | Entrypoint/JAR path sai hoặc config lỗi | Xem exit code và startup log |
| Permission denied | UID không có quyền đọc JAR/ghi thư mục | Kiểm tra COPY ownership và volume permissions |
| Container cannot bind port | Port đã bị dùng hoặc cấu hình sai | Kiểm tra server.port và mapping |
| OOMKilled | Heap/native memory vượt container limit | Đo memory và điều chỉnh JVM/resource limit |
| Readiness probe fail | Sai port/path hoặc dependency chưa sẵn sàng | Kiểm tra Actuator, probe timing và readiness policy |
| Liveness probe restart liên tục | Probe phụ thuộc shared external service hoặc timeout quá ngắn | Tách liveness khỏi dependency bên ngoài |
| Shutdown mất message | Listener ACK/commit trước khi xử lý xong | Dừng consumer và xử lý in-flight theo broker semantics |
| SSLHandshakeException | CA bundle hoặc hostname sai | Kiểm tra certificate chain và trust store |
| App chạy local nhưng không chạy container | Khác env, DNS, filesystem, architecture hoặc identity | So sánh runtime contract và smoke test |
| Image quá lớn | Dùng JDK/build tool trong runtime stage | Dùng buildpacks hoặc multi-stage build |
| Secret xuất hiện trong image | Copy file .env hoặc ghi secret trong Dockerfile | Xóa khỏi build context, rotate secret, rebuild |

## 25. Checklist trước production

- **Artifact:** JAR đã repackage, version/commit rõ ràng và checksum được lưu.
- **Java:** JRE version tương thích bytecode và framework.
- **Container:** Image OCI được build từ base image tin cậy, có digest bất biến.
- **Architecture:** Image platform khớp node/runtime architecture.
- **Security:** Process chạy non-root; không privileged; filesystem chỉ writable ở nơi cần.
- **Dependencies:** Dependency/base image đã scan và được cập nhật.
- **Configuration:** Profile, endpoint, port và resource name được cấp từ môi trường.
- **Secrets:** Không có secret trong JAR, image layer, Dockerfile hoặc log.
- **Identity:** Workload identity được gắn và có đúng data-plane permission.
- **Network:** DNS, egress, private endpoint, TLS và CA trust hoạt động.
- **Resources:** JVM heap/native memory phù hợp container memory; CPU/thread pool được đo.
- **Health:** Startup, liveness và readiness probe có path/port/timeout phù hợp.
- **Shutdown:** Graceful shutdown timeout nhỏ hơn termination grace period.
- **Observability:** Log, metrics, trace và build metadata có thể truy vết.
- **Release:** Image digest được promote qua staging/production mà không rebuild.
- **Recovery:** Có rollback digest và kiểm tra tương thích schema/resource.

## 26. Tổng kết

Spring Boot có thể được đóng gói thành executable JAR hoặc OCI container image. Maven Spring Boot Plugin và Gradle Plugin tạo executable archive; Cloud Native Buildpacks có thể tạo image trực tiếp; Docker multi-stage build tách build tool khỏi runtime. Layered JAR giúp tối ưu cache khi application code thay đổi thường xuyên.

Đóng gói chỉ là một phần của triển khai. Môi trường chạy cần Java version và kiến trúc tương thích, cấu hình externalized, workload identity, network/TLS, filesystem permission và giới hạn CPU/memory phù hợp. Trên Kubernetes, startup/liveness/readiness probe phải phản ánh đúng trạng thái ứng dụng; graceful shutdown cần đủ thời gian để drain request và message đang xử lý. Khi pipeline kiểm tra artifact, image digest và runtime contract trước khi promote, ứng dụng Spring Boot có thể chạy nhất quán trên VM, Kubernetes và các managed container platform của AWS, Azure và Google Cloud.

## Tài liệu tham khảo

- [Spring Boot Maven Plugin - Packaging Executable Archives](https://docs.spring.io/spring-boot/maven-plugin/packaging.html)
- [Spring Boot Gradle Plugin - Packaging Executable Archives](https://docs.spring.io/spring-boot/gradle-plugin/packaging.html)
- [Spring Boot Dockerfiles and layered archives](https://docs.spring.io/spring-boot/reference/packaging/container-images/dockerfiles.html)
- [Spring Boot Maven Plugin - Packaging OCI Images](https://docs.spring.io/spring-boot/maven-plugin/build-image.html)
- [Spring Boot Gradle Plugin - Packaging OCI Images](https://docs.spring.io/spring-boot/gradle-plugin/packaging-oci-image.html)
- [Spring Boot Actuator Endpoints and Kubernetes Probes](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Boot Graceful Shutdown](https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html)
- [Docker Build Best Practices](https://docs.docker.com/build/building/best-practices/)
- [Kubernetes Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/concepts/workloads/pods/probes/)
- [Kubernetes Pod Lifecycle](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/)


# Không đưa dịch vụ phát triển vào production do phụ thuộc đóng gói nhầm

## 1. Bài toán: môi trường chạy thật vô tình khởi tạo hạ tầng để thử nghiệm

Trong một ứng dụng **Spring Boot Integration**, môi trường phát triển thường cần PostgreSQL, Redis, Kafka, RabbitMQ hoặc một HTTP server giả lập. Spring Boot có cơ chế hỗ trợ khởi chạy **development-time services** như Docker Compose và Testcontainers để lập trình viên có đủ hạ tầng trên máy cá nhân mà không phải cấu hình mọi địa chỉ kết nối thủ công. Đây là tiện ích rất hữu dụng trong lúc phát triển và kiểm thử, nhưng nó tạo một ranh giới cần kiểm soát: **ứng dụng production phải dùng hạ tầng production được cấp phát và quản lý riêng, không tự dựng hạ tầng thử nghiệm vì phụ thuộc bị đóng gói nhầm**.

Giả sử nhóm phát triển chạy PostgreSQL và Kafka bằng Compose, rồi dùng `spring-boot-docker-compose` để Spring Boot tìm được kết nối. Khi đóng gói và triển khai, nếu thư viện development-time, file Compose hoặc cấu hình `dev` vẫn hoạt động trong môi trường production, ứng dụng có thể:

- Cố gắng gọi Docker CLI/socket để khởi tạo database hoặc broker không thuộc hạ tầng production.
- Lấy thông tin kết nối từ một dịch vụ phát triển và vô tình **ghi vào database khác** database được cấu hình cho production.
- Gây lỗi khởi động vì máy production không có Docker/Compose, không được cấp quyền tới Docker daemon hoặc không thể tải image.
- Khởi tạo Testcontainers hoặc tài nguyên thử nghiệm khi chạy ứng dụng, gây kết nối sai, mất dữ liệu khi container bị xóa và sai phạm vi vận hành.
- Bật các seed data, cấu hình xác thực đơn giản, scheduler hoặc consumer dành cho local trên môi trường thật.

Đây là rủi ro đặc biệt nghiêm trọng với ứng dụng tích hợp: một luồng HTTP → database → outbox → Kafka có thể **báo thành công** nhưng đang dùng database/broker thử nghiệm; hoặc một consumer xử lý message rồi commit offset trên hạ tầng không mong muốn. Kiểm tra mỗi “ứng dụng đã lên trạng thái healthy” là chưa đủ.

~~~mermaid
flowchart TD
    Source["Source code"] --> Build["Build / dependency resolution"]
    Build --> Artifact["Executable JAR / OCI image"]
    Artifact --> Runtime["Production runtime"]
    DevDeps["Docker Compose / Testcontainers / Devtools"] -. "Nếu lọt vào runtime" .-> Artifact
    Runtime --> Prod["Production DB / broker / cache"]
    Runtime -. "Sai cấu hình / service connection" .-> Local["Development-time services"]
    Gate["CI packaging + runtime configuration checks"] --> Artifact
~~~

**Mục tiêu:** phân biệt dịch vụ phát triển với hạ tầng production, cấu hình dependency scope đúng, xác minh nội dung JAR/image, khóa đường kích hoạt nhầm và kiểm thử đủ mạnh để phát hiện một bản phát hành sử dụng service connection ngoài dự kiến.

## 2. Hiểu đúng “development-time service” trong Spring Boot

### 2.1. Spring Boot Docker Compose support

Với các phiên bản Spring Boot có hỗ trợ Docker Compose (từ dòng 3.1), dependency `org.springframework.boot:spring-boot-docker-compose` giúp ứng dụng phát triển tìm file Compose và tương tác với các container tương ứng. Với những image/service được hỗ trợ, Spring Boot có thể tạo **connection details** để cấu hình kết nối tới PostgreSQL, Redis, broker và dịch vụ liên quan.

Ví dụ một `compose.yaml` dùng **chỉ cho local**:

~~~yaml
services:
  postgres:
    image: postgres:17-alpine
    environment:
      POSTGRES_DB: integration_dev
      POSTGRES_USER: dev_user
      POSTGRES_PASSWORD: local_only_password
    ports:
      - "127.0.0.1:15432:5432"

  redis:
    image: redis:7-alpine
    ports:
      - "127.0.0.1:16379:6379"
~~~

Khi chạy Spring Boot trên máy phát triển có Docker, hỗ trợ Compose có thể khởi tạo/nhận diện các dịch vụ và cung cấp kết nối cho ứng dụng. Phần port `127.0.0.1:...` chỉ phục vụ minh họa cục bộ; tên host/port thực tế khác nếu ứng dụng chạy trong container cùng network.

**Điểm dễ bỏ sót:** Compose integration có thể cung cấp `ConnectionDetails` được các auto-configuration sử dụng. Vì thế không nên chỉ đọc `spring.datasource.url` rồi kết luận ứng dụng **chắc chắn** kết nối tới URL đó: nếu có connection details từ development service, cần xác minh đích kết nối **thực tế** ở runtime.

File Compose không nằm **bên trong JAR** chỉ vì module Compose có mặt. Rủi ro xuất hiện khi **thư viện hỗ trợ, file Compose, quyền Docker và điều kiện kích hoạt** cùng tồn tại, hoặc khi runtime dùng sai cấu hình. Phải phân biệt rõ **đóng gói dependency**, **đưa file Compose vào image** và **khởi động container bên ngoài** là ba việc khác nhau.

### 2.2. Testcontainers và `@ServiceConnection`

Testcontainers thường được dùng trong integration test để chạy database hoặc broker tạm thời bằng container. Với `spring-boot-testcontainers`, annotation `@ServiceConnection` có thể tạo thông tin kết nối từ container phù hợp, giúp test không cần hardcode port.

Nếu mã khởi động container đặt ở `src/main/java`, hoặc dependency chỉ dành cho test lại nằm trong runtime classpath, một đoạn cấu hình như “PostgreSQL Testcontainer tự chạy khi start app” có thể vô tình hoạt động ở production. Việc thư viện Testcontainers xuất hiện trong JAR **không tự động có nghĩa** container sẽ được khởi động; phải có mã/cấu hình kích hoạt. Tuy vậy, không để khả năng này nằm trong artifact production vẫn là tuyến phòng vệ cần thiết.

### 2.3. Những thành phần dễ bị nhầm là “chỉ dành cho dev”

| Thành phần | Vai trò trong development/test | Rủi ro khi đưa sang production |
|---|---|---|
| `spring-boot-docker-compose` | Tích hợp dịch vụ từ Docker Compose | Tự tìm/khởi chạy service dev khi có cấu hình và quyền Docker |
| `spring-boot-testcontainers` + Testcontainers | Kết nối database/broker container trong test hoặc dev launcher | Test infrastructure bị đưa vào runtime; có thể bật container khi cấu hình bị quét |
| `spring-boot-devtools` | Hot reload, công cụ tiện phát triển | Hành vi không phù hợp bản release và bề mặt cấu hình thừa |
| Embedded Kafka, broker giả lập, SMTP capture, HTTP stub | Cô lập integration test | Test listener/port/fixture hoặc kết nối giả lọt vào quy trình nghiệp vụ |
| Database H2 và cấu hình seed dữ liệu | Test repository hoặc prototype | Ứng dụng dùng database tạm thời thay vì PostgreSQL thật |
| `application-dev.yml`, `compose.yaml` | Định tuyến các service local | Được kích hoạt/copy nhầm; tiết lộ mật khẩu mẫu, host dev |

Không phải mọi thư viện trong bảng đều **luôn sai** khi xuất hiện trong mọi sản phẩm. Vấn đề là xác định tài nguyên dành riêng cho phát triển, đánh giá nhu cầu thực sự của production và bảo đảm cấu hình thực tế chỉ bật những thành phần đã được phê duyệt.

## 3. Ranh giới quan trọng: compile classpath, runtime classpath và artifact

Một ứng dụng có thể **chạy tốt trong IDE** nhưng artifact phát hành khác hẳn vì các cấu hình dependency:

1. **Compile classpath**: thư viện cần để biên dịch.
2. **Test classpath**: thư viện được đưa vào khi chạy test.
3. **Development/bootRun classpath**: thư viện hữu ích khi chạy local, có thể bao gồm các dependency development-only.
4. **Production runtime classpath**: các thư viện ứng dụng cần khi chạy bản phát hành.
5. **Repackaged executable JAR / Docker image**: sản phẩm cuối cùng được deploy, có thể chịu ảnh hưởng của Spring Boot plugin, cấu hình `bootJar`/`repackage` và Dockerfile.

Không thể suy ra thành phần được đóng gói bằng cách chỉ kiểm tra `build.gradle` hoặc `pom.xml`: Spring Boot plugin có các quy tắc đóng gói riêng; cấu hình tùy chỉnh, shadow jar, sao chép thủ công hoặc image chạy `bootRun` có thể thay đổi kết quả.

~~~mermaid
flowchart LR
    Dev["Local: bootRun / IDE"] --> DevDeps["developmentOnly + runtime"]
    Tests["JUnit / Testcontainers"] --> TestDeps["testImplementation / test scope"]
    Build["Release: bootJar / repackage"] --> Runtime["Production runtime dependencies"]
    Runtime --> JAR["Executable JAR"]
    JAR --> Image["OCI image"]
    DevDeps -. "Không cho chảy vào bản phát hành" .-> JAR
    TestDeps -. "Không cho chảy vào bản phát hành" .-> JAR
~~~

## 4. Khai báo dependency chính xác với Gradle

Với dự án Gradle dùng Spring Boot plugin, ví dụ Groovy DSL:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '<spring-boot-version>'
    id 'io.spring.dependency-management' version '<compatible-version>'
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    runtimeOnly 'org.postgresql:postgresql'

    // Phục vụ chạy local; không đưa vào executable bootJar thông thường.
    developmentOnly 'org.springframework.boot:spring-boot-docker-compose'
    developmentOnly 'org.springframework.boot:spring-boot-devtools'

    // Dùng trong source set test, không đưa vào runtime production.
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:postgresql'
}
~~~

`<spring-boot-version>` và `<compatible-version>` là **placeholder**, không phải giá trị build thật; trong dự án thực dùng version và cơ chế quản lý dependency nhất quán với Spring Boot BOM. Tọa độ module Testcontainers có thể khác giữa các dòng phiên bản lớn; dùng bộ module mà Spring Boot BOM/phiên bản Testcontainers của dự án hỗ trợ.

Ở đây:

- `developmentOnly` thích hợp cho những công cụ được dùng khi chạy ứng dụng **trong môi trường phát triển** và được Spring Boot Gradle plugin xử lý tách khỏi executable JAR mặc định.
- `testImplementation` phù hợp khi Testcontainers được khởi tạo từ bài test, đặc biệt là code nằm trong `src/test/java`.
- `implementation` hoặc `runtimeOnly` cho dependency dev là một lỗi phân loại thường gặp, vì có thể kéo nó vào production runtime classpath.

**Cần kiểm tra khi build customization:** nếu dự án thay cách tạo classpath, dùng `shadowJar`, tự viết tác vụ `Jar`, lắp ghép thư viện vào `BOOT-INF/lib` hoặc copy toàn bộ `build/libs` vào image, quy tắc mặc định có thể không còn đúng. Đặc biệt, không dùng `bootRun` hay một lệnh có development classpath làm **entrypoint production**.

### 4.1. Mẫu test dùng Testcontainers chỉ trong source set test

~~~java
package example.integration;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@SpringBootTest
class OrderRepositoryIntegrationTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:17-alpine");

    @Test
    void repositoryCanPersistOrder() {
        // Gọi repository/service và assert kết quả với database container.
    }
}
~~~

File này phải thuộc `src/test/java`. `@ServiceConnection` cung cấp cấu hình kết nối cho test khi dependency hỗ trợ nằm trong test classpath; không đặt cấu hình container này trong `src/main/java` chỉ vì muốn IDE chạy thuận tiện. Nếu muốn phát triển bằng Testcontainers lúc chạy ứng dụng, có thể dùng **test-only launcher** theo tài liệu Spring Boot, vẫn giữ code dev ngoài artifact runtime.

Đoạn test trên minh họa cấu trúc, không phải bài test hoàn chỉnh: cần thêm setup dữ liệu, gọi repository thực và assertions. Nó cũng cần phiên bản Spring Boot/Testcontainers hỗ trợ các annotation tương ứng.

## 5. Khai báo dependency chính xác với Maven

Ví dụ `pom.xml` cho hỗ trợ Docker Compose khi phát triển:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-jpa</artifactId>
    </dependency>
    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>

    <!-- Hỗ trợ development-time; Spring Boot packaging có quy tắc loại trừ. -->
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-docker-compose</artifactId>
        <scope>runtime</scope>
        <optional>true</optional>
    </dependency>

    <!-- Chỉ thuộc classpath test. -->
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-testcontainers</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.testcontainers</groupId>
        <artifactId>junit-jupiter</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.testcontainers</groupId>
        <artifactId>postgresql</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

**Hai điểm dễ nhầm:**

1. Trong Maven, `optional=true` chủ yếu liên quan đến **tính truyền bắc cầu cho dự án khác phụ thuộc vào module này**; nó không đồng nghĩa “dependency chắc chắn vắng mặt trong runtime classpath của chính module”. Spring Boot Maven plugin có hành vi loại trừ `spring-boot-docker-compose` khi repackaging trong các phiên bản hỗ trợ, nhưng vẫn phải kiểm tra kết quả khi tùy chỉnh plugin, build hoặc cấu hình loại trừ.
2. `scope=test` đưa Testcontainers vào tập thư viện dùng khi test; khác với `runtime` hoặc `compile`, vốn có thể đưa chúng vào artifact. Khi nâng cấp phiên bản lớn của Testcontainers, rà lại artifact tọa độ chính xác theo BOM tương ứng.

Không bật tùy chọn packaging cho phép **bao gồm Docker Compose** trong executable artifact production. Với Maven, kiểm tra cấu hình của `spring-boot-maven-plugin` (bao gồm tùy chọn `excludeDockerCompose` ở phiên bản hỗ trợ), cấu hình `repackage` và các override tại profile build. Đặc biệt, không đánh đồng `<optional>true</optional>` với một kiểm chứng thực tế về nội dung file JAR.

### Vì sao không chỉ dùng Maven/Gradle profile?

Build profile giúp phân tách các nhóm dependency nhưng có thể bị chọn nhầm trên CI, và nếu image chứa nhiều artifact thì profile đúng vẫn chưa bảo đảm artifact được chạy là bản production. Thói quen tốt là **cấu hình scope đúng + build riêng + kiểm tra artifact cuối cùng + kiểm tra runtime config**.

## 6. Bảo vệ bằng cấu hình runtime

### 6.1. Vô hiệu Docker Compose ở profile production

`src/main/resources/application-prod.yml`:

~~~yaml
spring:
  docker:
    compose:
      enabled: false
  datasource:
    url: ${PROD_JDBC_URL}
    username: ${PROD_DB_USER}
    password: ${PROD_DB_PASSWORD}

app:
  integration:
    environment: production
~~~

Ở môi trường triển khai, có thể đặt thêm:

~~~text
SPRING_PROFILES_ACTIVE=prod
SPRING_DOCKER_COMPOSE_ENABLED=false
PROD_JDBC_URL=jdbc:postgresql://<production-db-host>:5432/integration
~~~

Các placeholder cần được cấp từ hệ quản lý secret/config thực tế. Không commit credential production vào repository. **`spring.docker.compose.enabled=false` là lớp phòng vệ khi module Compose bất ngờ hiện diện; mục tiêu chính vẫn là không đóng gói module đó trong artifact production.**

Một số cơ chế cấu hình có thứ tự ưu tiên cao hơn file `application-prod.yml` như biến môi trường hoặc tham số command line. Nếu một script triển khai vô tình đặt lại `SPRING_DOCKER_COMPOSE_ENABLED=true`, cấu hình trong file có thể bị override. Vì vậy phải kiểm tra manifest/deployment được áp dụng thực tế và quan sát endpoint/connection cuối cùng.

Đừng mặc định “production luôn có profile prod” nếu hệ thống không thực sự cấu hình như vậy. Cần có một cơ chế xác nhận cấu hình môi trường trước khi nhận request, ví dụ kiểm tra các property bắt buộc hoặc startup validation phù hợp kiến trúc.

### 6.2. Các quy tắc cấu hình phù hợp với Spring Boot Integration

| Cấu hình/kết nối | Môi trường phát triển | Production |
|---|---|---|
| PostgreSQL | Local Compose/Testcontainers; dữ liệu mẫu | Database được cấp phát, migration có kiểm soát và tài khoản quyền tối thiểu |
| Kafka/RabbitMQ | Broker thử nghiệm, topic riêng | Broker/namespace/ACL đã cấp, consumer group đúng môi trường |
| Redis/cache | Instance cache local, có thể xóa | Cache production với cấu hình TTL, authentication và topology thực |
| HTTP client | WireMock/mock API/test endpoint | Endpoint đối tác được xác minh, TLS, timeout, credential và rate limit |
| Email | Mailpit/GreenMail, recipient giả | Email provider được duyệt, guard người nhận và kiểm soát gửi |
| Scheduler | Có thể kích hoạt ngay để thử | Điều phối cluster, idempotency và trạng thái job bền vững |
| Service connection | Tạo từ dev container | Thông số kết nối production qua cấu hình/secret đáng tin cậy |

Cấu hình “không tự dựng PostgreSQL” chưa đủ nếu `spring.kafka.bootstrap-servers` vẫn trỏ tới `localhost:9092` hoặc `spring.data.redis.host` vẫn dùng giá trị local. Cần kiểm tra **từng adapter** trong luồng tích hợp thay vì chỉ database.

### 6.3. Không phụ thuộc vào điều kiện `@Profile` làm cơ chế duy nhất

Một cấu hình chỉ phục vụ local có thể được đặt như sau:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration(proxyBeanMethods = false)
@Profile("dev")
class LocalIntegrationConfiguration {
    // Chỉ chứa những adapter và stub dành riêng cho phát triển.
}
~~~

Nhưng nếu class này chứa startup logic tạo container và nằm trong `src/main/java`, nó vẫn **được đóng gói**. Nếu ai đó bật nhầm `dev` trong production, bean có thể hoạt động. Với Testcontainers hoặc công cụ mô phỏng không thuộc sản phẩm, **đặt code trong test source set hoặc module development launcher độc lập** giúp loại trừ nguyên nhân từ gốc.

## 7. Kiểm tra executable JAR trước khi phát hành

**Kiểm tra binary được deploy**, vì dependency tree chưa mô tả hoàn toàn kết quả repackaging. Ví dụ một executable Spring Boot JAR thông dụng chứa thư viện dưới `BOOT-INF/lib/`.

Với Gradle:

~~~bash
./gradlew clean bootJar
jar tf build/libs/integration-service.jar
~~~

Với Maven:

~~~bash
./mvnw -DskipTests package
jar tf target/integration-service.jar
~~~

`integration-service.jar` là **tên minh họa**; dùng tên artifact thật từ build output. Lệnh `jar tf` liệt kê thành phần JAR, không thực thi ứng dụng và không cần kết nối production.

Một gate CI đơn giản (môi trường Bash), chạy **sau build**:

~~~bash
set -eu
APP_JAR="build/libs/integration-service.jar"

if jar tf "$APP_JAR" | grep -E \
  '(^|/)BOOT-INF/lib/(spring-boot-docker-compose|spring-boot-testcontainers|spring-boot-devtools|testcontainers-[^/]*|junit-jupiter[^/]*)[^/]*\.jar$'
then
  echo "ERROR: Development/test dependency found in release JAR" >&2
  exit 1
fi

echo "Release JAR dependency check passed."
~~~

Đổi `APP_JAR` sang path build thực tế; ở PowerShell/Windows CI dùng lệnh tương đương. Regex trên là **ví dụ allow/deny policy của dự án**, cần mở rộng theo thư viện Testcontainers và các stub thực sự được dùng; danh sách không tự động bao phủ mọi mô-đun test hoặc trường hợp JAR bị đóng gói lồng theo cách khác.

**Điểm quan trọng của gate:** nếu dự án dùng một thư viện có tên không trùng regex, cần bổ sung chính sách kiểm tra. Nếu `bootJar` không có cấu trúc `BOOT-INF/lib` (ví dụ native image, shaded JAR, layers hoặc packaging khác), phải dùng công cụ kiểm tra phù hợp loại artifact đó. Không được coi một regex trả về rỗng là bằng chứng đầy đủ nếu nó không hiểu định dạng sản phẩm cuối cùng.

### 7.1. Dependency report phục vụ chẩn đoán

Với Gradle, có thể đối chiếu:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencies --configuration testRuntimeClasspath
./gradlew dependencies --configuration developmentOnly
~~~

Với Maven:

~~~bash
./mvnw dependency:tree
~~~

Khi thấy thư viện dev ở `runtimeClasspath`, hãy truy dependency edge đến module đưa nó vào. Tuy nhiên **đừng kết luận JAR đã chứa** hoặc **chưa chứa** chỉ từ dependency tree. Một plugin có thể exclude lúc đóng gói, hoặc một quá trình copy thủ công có thể thêm thư viện từ nguồn khác. Cần đối chiếu **report + artifact thực**.

### 7.2. Kiểm tra Docker/OCI image

Một Dockerfile multi-stage nên đưa **chỉ artifact đã kiểm chứng** vào runtime image:

~~~dockerfile
# Giai đoạn build do CI hoặc builder image thực hiện ở ngoài ví dụ này.
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY integration-service.jar /app/app.jar
USER 10001
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Ví dụ giả định `integration-service.jar` đã được build và kiểm tra. Cấu hình thực tế cần bảo đảm đường dẫn COPY hợp lệ trong build context, Java runtime tương thích ứng dụng và quyền thư mục phù hợp. **Không** đưa Docker CLI, socket `/var/run/docker.sock`, compose file, `src/test` hoặc thư mục fixtures vào image nếu không có nhu cầu được duyệt.

Một anti-pattern dễ gây lỗi:

~~~dockerfile
# KHÔNG dùng làm cách chạy bản release.
COPY . /workspace
WORKDIR /workspace
ENTRYPOINT ["./gradlew", "bootRun"]
~~~

`bootRun` có thể sử dụng classpath phát triển, chạy Gradle và tìm hạ tầng local, không đại diện cho bản release đã khóa dependency. Build image từ executable artifact hoặc phương án packaging chính thức của dự án giúp giảm rủi ro.

Nếu dùng Spring Boot Buildpacks/`bootBuildImage`, vẫn cần kiểm tra image tạo ra và danh sách dependency runtime thực tế. Lớp buildpack khác với việc chạy `bootRun`, nhưng không miễn kiểm thử cấu hình profile và kết nối.

## 8. Không khởi tạo service phát triển khi ứng dụng production bắt đầu

Trước khi chuyển traffic, kiểm tra một số dấu hiệu:

- Log khởi động không xuất hiện bước tự tìm, chạy `docker compose up` hay khởi tạo `Testcontainers`.
- Không có yêu cầu truy cập Docker daemon/socket từ process ứng dụng.
- Các `ConnectionDetails` thực sự trỏ tới database/broker/cache đúng môi trường; địa chỉ cục bộ và cổng được expose động chỉ được dùng khi đó là thiết kế chính thức.
- Startup không thực hiện seed data/test migration vào database sai; chỉ các migration production được duyệt mới chạy.
- Readiness báo sẵn sàng sau khi dependency thiết yếu đúng môi trường hoạt động; một dependency dev chạy được không được thay thế phép kiểm tra đích kết nối thực.

Ví dụ trạng thái startup cần phát hiện:

~~~text
Expected:
  db.host = postgres.prod.internal
  kafka.bootstrap = kafka-prod.internal:9092
  redis.host = redis-prod.internal
  docker.compose.enabled = false

Unexpected:
  db.host = 127.0.0.1:15432
  kafka.bootstrap = localhost:9092
  container.image = postgres:17-alpine (started by application)
~~~

Các host trên là **tên minh họa**, không phải yêu cầu hardcode mọi production host. Trong một số deployment, local sidecar/proxy có thể cố ý xuất hiện; phải đối chiếu cấu hình đã phê duyệt thay vì áp dụng quy tắc tuyệt đối “localhost luôn sai”.

Khi log thông tin kết nối để chẩn đoán, không ghi mật khẩu, token, connection string có embedded credential, hoặc thông tin nhạy cảm. Ưu tiên log `environment`, loại backend và endpoint đã rút gọn cùng trace ID, application version và image digest.

## 9. Các đường lỗi do đóng gói và cấu hình nhầm

| Lỗi | Triệu chứng | Nguyên nhân cần tìm | Phòng ngừa |
|---|---|---|---|
| Thêm Compose vào `implementation`/`runtimeOnly` | Artifact chứa module dev hoặc startup tìm Docker | Phân loại dependency sai, plugin bị tùy chỉnh | Đưa vào `developmentOnly`/cấu hình Maven phù hợp; kiểm tra JAR |
| Testcontainers nằm trong main | Production tải image hoặc đòi Docker socket | Container bean được quét hoặc dev launcher dùng chung | Đưa container config vào `src/test`/module dev riêng |
| Image chạy `bootRun` | Prod dùng classpath local, phụ thuộc source/build tool | Dockerfile dùng command dành cho developer | Chạy executable JAR/native image đã kiểm tra |
| Compose file bị copy vào runtime | Ứng dụng có thể tự dựng dịch vụ local | Build context và COPY quá rộng | Multi-stage, chỉ copy artifact, policy image |
| `SPRING_PROFILES_ACTIVE=dev` trên prod | Kết nối tới sandbox, seed dữ liệu | Deployment env sai | Khóa cấu hình deployment, validation trước traffic |
| `ConnectionDetails` từ dev ghi đè URL kỳ vọng | Database/broker thực tế khác property khai báo | Dev service auto config còn hoạt động | Tắt hỗ trợ, kiểm tra kết nối hiệu lực |
| Dùng DB in-memory ở môi trường thật | Dữ liệu mất khi restart | Fallback test URL/profile | Fail-fast nếu thiếu production URL, không có fallback test |
| Build bỏ qua gate artifact | Release được tạo nhưng chứa jar test | Pipeline chỉ chạy unit test | Thêm bước inspect artifact/image |
| Không có quyền Docker | Startup lỗi dù database production sẵn | Module Compose/Testcontainers bị kích hoạt | Không có module dev ở production, không mount Docker socket |
| Dùng chung broker với local | Consumer chạy nhầm topic/group | Misconfiguration bootstrap/credential | Namespace, ACL, config validation và audit |

### Case: bản release ghi nhầm database

Giả sử production có `PROD_JDBC_URL` đúng nhưng cùng JAR chứa một development service connection. Nếu cấu hình tự động tạo kết nối từ Compose/Testcontainers được sử dụng, repository có thể truy cập một PostgreSQL khác. Migration/schema thậm chí có thể được tạo mới tự động ở database đó, khiến smoke test đơn giản vẫn pass.

Để phát hiện, test cần kiểm tra **database identity** và đối tượng dữ liệu dự kiến, ví dụ hostname/database/schema được xác minh theo deployment manifest và metadata được đo từ connection thực tế. Không chạy một câu SQL thay đổi dữ liệu production chỉ để “thử kết nối”. Một kiểm tra read-only có kiểm soát cùng tracing đủ để xác định nguồn kết nối.

### Case: worker bất đồng bộ làm tăng tác động của lỗi

Một message consumer kết nối nhầm Kafka cluster có thể lắng nghe sai topic, còn một `@Scheduled` job chạy trên nhiều replica có thể gửi dữ liệu qua HTTP hoặc email từ test fixtures ra ngoài. Vì vậy bảo vệ development services phải bao gồm **scheduler, listener, outbound adapter, webhook và email gateway**, không chỉ controller.

## 10. Kiểm thử bảo đảm không rò rỉ development-time services

Có thể thiết kế một tập kiểm tra nhiều lớp:

### 10.1. Kiểm tra dependency và artifact trong CI

1. Build bằng cấu hình **release thực sự**, không chỉ cấu hình được dùng khi chạy IDE.
2. Kiểm tra runtime dependency report; các module dev/test đã xác định phải nằm ở scope phù hợp.
3. Mở executable JAR/OCI image, assert không có những module bị cấm và không có file Compose/test fixture ngoài dự kiến.
4. Chạy smoke test bằng **artifact đó**, không chạy `bootRun` từ source.
5. Đảm bảo Docker socket không được cấp cho app; nếu app cần socket vì mục đích hợp lệ khác, phải tách quyền và đánh giá riêng.

### 10.2. Smoke test production-like

Trong môi trường staging hoặc test deployment có cấu hình gần production:

~~~text
Given:
  artifact = release JAR / OCI image đã kiểm tra
  profile = prod-like
  no Docker socket
  no local compose file
  explicit database, broker, cache endpoints

When:
  khởi động ứng dụng và gọi health/readiness + API read-only

Then:
  ứng dụng không cố truy cập Docker daemon
  các connection details trỏ đúng endpoint được cấp
  không có seed data hoặc container test tự khởi tạo
  các adapter nghiệp vụ chỉ bật theo cấu hình môi trường
~~~

**Giới hạn của smoke test:** việc không có Docker socket có thể khiến dev service âm thầm bỏ qua hoặc log warning; một lần startup thành công không thay thế kiểm tra dependency và thông tin kết nối thực. Nên assert rõ **không có module dev trong artifact** và **không có kết nối dev**.

### 10.3. Kiểm thử hồi quy cho configuration binding

Các test cấu hình có thể xây những trường hợp:

| Ca test | Dữ liệu đầu vào | Kỳ vọng |
|---|---|---|
| Local developer | Profile `dev`, Docker available, Compose local | App dùng đúng container test và không gửi ra production |
| CI integration | Testcontainers trong test classpath | Test tạo/dọn container, artifact runtime không chứa test jar |
| Production artifact | Release JAR, profile `prod` | `spring.docker.compose.enabled=false`, không có dev service |
| Thiếu `PROD_JDBC_URL` | Biến môi trường bắt buộc vắng | Startup fail-fast, không fallback sang H2/local Compose |
| Cấu hình nhầm `dev` | Deployment cố bật dev profile | Validation/policy triển khai từ chối hoặc fail trước traffic |
| Broker sai cluster | Bootstrap servers không thuộc allowlist môi trường | Startup validation hoặc deployment gate phát hiện |
| Rollback phiên bản | Deploy artifact cũ với manifest hiện tại | Không tạo lại hạ tầng dev; schema/adapter tương thích |

Với application context test, kiểm tra bean `DockerComposeLifecycleManager` hay loại hỗ trợ cụ thể có thể phụ thuộc phiên bản Spring Boot; kiểm chứng theo **hành vi và artifact**, thay vì chỉ đếm một bean nội bộ dễ thay đổi giữa các bản nâng cấp.

### 10.4. Thử lỗi kết nối mà không tự cứu bằng dev service

Nếu PostgreSQL production-like tạm không sẵn sàng, ứng dụng cần báo lỗi kết nối đúng, readiness phản ánh trạng thái phù hợp và retry có giới hạn. Nó **không được** chuyển sang một PostgreSQL local khác rồi tiếp tục xử lý request như thể đang hoạt động bình thường.

Phép thử này có giá trị cao trong hệ thống tích hợp vì lỗi dependency là tình huống chắc chắn sẽ gặp trong vận hành; một fallback sang hạ tầng giả làm hỏng sự nhất quán mà các service khác kỳ vọng.

## 11. Phòng ngừa bằng kiến trúc và quy trình phát hành

Một quy trình thuận tiện cho nhóm phát triển nhưng an toàn khi triển khai:

1. **Trong mã nguồn:** đặt Testcontainers/fixtures ở `src/test` hoặc module dev launcher; đóng gói hỗ trợ Compose bằng scope/config chỉ dành cho development.
2. **Trong cấu hình:** tách `application-dev.yml`, `application-test.yml`, `application-prod.yml`; production yêu cầu endpoint/credential bắt buộc, không fallback sang local. Mọi bí mật được cấp từ secret manager.
3. **Trong build:** tạo đúng một artifact release bằng plugin/target đã kiểm soát, cố định BOM và kiểm tra các tùy chọn include/exclude của plugin.
4. **Trong CI:** chạy unit/integration test với Docker/Testcontainers để kiểm chứng các adapter, sau đó inspect artifact và image phát hành thật.
5. **Trong deployment:** không mount Docker socket, không đưa Compose file/local script vào runtime container; cấp quyền mạng, namespace và secret chỉ cho các service cần thiết.
6. **Khi rollout:** đo kết nối hiệu lực, migration/schema, consumer group, topic, cache và external HTTP endpoints; kiểm tra log không có bootstrap dev services.
7. **Khi nâng cấp Spring Boot:** kiểm tra lại dependency graph, hành vi connection details, quy tắc plugin đóng gói và smoke test sau thay đổi phiên bản.

Chốt rõ trách nhiệm: nhóm backend bảo đảm phân loại dependency và code, nhóm platform kiểm soát image/manifest/network, CI kiểm tra binary, còn vận hành đối chiếu connection thực tế. Đây là **các biện pháp bổ trợ** cho cùng một mục tiêu: tránh vận hành hạ tầng thử nghiệm như một phần production.

## 12. Câu hỏi tự kiểm tra

1. Vì sao chạy `./gradlew bootRun` thành công với Compose local không chứng minh executable JAR sẽ có cùng dependency và hạ tầng?
2. Nếu `spring-boot-docker-compose` xuất hiện ở `runtimeOnly`, cách nào chứng minh artifact release thực sự có hoặc không có thư viện đó?
3. `optional=true` trong Maven có đủ để khẳng định dependency không nằm trong executable JAR của module hiện tại không? Vì sao?
4. Khi `@ServiceConnection` tạo connection details từ Testcontainers, điều gì có thể khiến giá trị URL bạn khai báo trong `application.yml` không phải đích kết nối cuối?
5. Đặt container configuration dưới `src/test/java` giúp giảm nguy cơ nào so với đặt dưới `src/main/java` chỉ kèm `@Profile("dev")`?
6. Nếu production startup thành công dù PostgreSQL chính đang không sẵn sàng, các dữ kiện nào giúp phát hiện một dev database đang được dùng ngoài ý muốn?
7. Vì sao chỉ kiểm tra dependency tree chưa đủ khi dự án có custom packaging và Dockerfile tự viết?
8. Với một hệ thống có HTTP client, DB, cache, Kafka và scheduler, cần xác minh những endpoint/adapter nào trước khi chuyển traffic?

**Kết luận:** development-time services giúp tăng tốc lập trình và kiểm thử Spring Boot Integration, nhưng phạm vi của chúng phải dừng ở môi trường phát triển/test. Bảo đảm này cần được thực hiện bằng **dependency scope đúng, source set riêng, cấu hình production fail-fast, artifact/image inspection và kiểm thử kết nối hiệu lực**. Khi tránh đóng gói nhầm Docker Compose/Testcontainers và không kích hoạt nhầm các adapter giả lập, hệ thống sẽ dùng đúng database, cache, broker và HTTP endpoint mà quy trình production kiểm soát.

### Tài liệu tham khảo

- [Spring Boot — Development-time Services](https://docs.spring.io/spring-boot/reference/features/dev-services.html): Docker Compose support, lifecycle và service connections.
- [Spring Boot — Testcontainers](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html): `@ServiceConnection` và tích hợp Testcontainers cho kiểm thử.
- [Spring Boot Gradle Plugin — Packaging Executable Archives](https://docs.spring.io/spring-boot/gradle-plugin/packaging.html): `bootJar`, dependency và hành vi đóng gói.
- [Spring Boot Maven Plugin — Packaging Executable Archives](https://docs.spring.io/spring-boot/maven-plugin/packaging.html): `repackage` và cấu hình loại trừ dependency.
- [Maven — Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html): `scope`, optional dependency và tính truyền bắc cầu.
- [Gradle — Dependency Configurations](https://docs.gradle.org/current/userguide/declaring_configurations.html): các cấu hình dependency và classpath.

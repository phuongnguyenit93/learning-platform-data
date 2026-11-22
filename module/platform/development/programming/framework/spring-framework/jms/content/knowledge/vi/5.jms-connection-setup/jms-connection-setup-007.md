# Cấu hình kết nối Spring JMS qua biến môi trường mà không ghi bí mật vào mã

## 1. Bài toán và nguyên tắc

Một ứng dụng Spring gửi/nhận message qua JMS thường cần các thông số:

- Địa chỉ broker: hostname, port, protocol hoặc connection URI.
- Tài khoản kết nối: tên người dùng và mật khẩu; đôi khi là token hoặc thông tin xác thực riêng của provider.
- Thiết lập bảo mật: TLS, truststore/keystore, chứng chỉ, quyền truy cập queue/topic.
- Tùy chọn vận hành: timeout, reconnect, connection/session caching hoặc pooling.

Nếu ghi thẳng mật khẩu trong mã Java, `application.yml` được commit, script build, Dockerfile hoặc tài liệu dự án, một bí mật dễ bị đưa vào Git history, artifact, image layer, CI log hay bản sao lưu. **Mục tiêu của externalized configuration** là: mã ứng dụng giữ nguyên giữa các môi trường; thông số và bí mật được **cấp lúc triển khai/chạy**, được quản lý độc lập và có thể luân chuyển mà không cần sửa mã.

Ví dụ **không nên dùng**:

~~~java
// SAI: mật khẩu thật không được lưu trong mã nguồn.
String username = "admin";
String password = "production-password";
~~~

~~~yaml
# SAI nếu file này chứa mật khẩu thật và được đưa vào Git/image.
spring:
  artemis:
    user: admin
    password: production-password
~~~

Hướng thực hiện đúng với Spring Boot:

~~~text
CI/CD hoặc secret manager / môi trường vận hành
        │ cung cấp JMS_BROKER_URL, JMS_USERNAME, JMS_PASSWORD
        ▼
Biến môi trường của tiến trình Java (hoặc mounted secret)
        │ Spring Environment / property placeholders
        ▼
spring.artemis.broker-url / user / password
        │ Spring Boot JMS auto-configuration
        ▼
ConnectionFactory → JMS client library → broker Artemis
        │
        ▼
JmsTemplate / @JmsListener / business code
~~~

**Lưu ý:** biến môi trường giúp tách cấu hình khỏi source code, nhưng **không tự mã hóa hay bảo mật tuyệt đối bí mật**. Người có quyền xem runtime/container metadata hoặc dump tiến trình có thể đọc được chúng. Ở production, cần dùng secret manager, quyền truy cập tối thiểu, kênh truyền TLS và quy trình xoay vòng credential.

## 2. Các lớp cần phân biệt

| Lớp | Ví dụ | Trách nhiệm |
| --- | --- | --- |
| **JMS / Jakarta Messaging API** | `ConnectionFactory`, `JMSContext`, `Message` | Hợp đồng Java để gửi/nhận message |
| **Spring JMS** | `JmsTemplate`, `@JmsListener`, listener container | Quản lý thao tác JMS, tài nguyên và consumer |
| **Spring Boot configuration** | `spring.artemis.*`, placeholders, `Environment` | Đọc cấu hình và tạo bean `ConnectionFactory` qua auto-configuration |
| **JMS provider/client** | Apache ActiveMQ Artemis JMS client | Hiện thực JMS API và nói chuyện với broker |
| **Hạ tầng cấp bí mật** | OS environment, Docker/Kubernetes Secrets, Vault | Cấp username/password ngoài mã nguồn |
| **Broker** | Apache ActiveMQ Artemis | Xác thực, phân quyền, định tuyến và lưu trữ message |

Không nhầm mật khẩu **broker dành cho ứng dụng** với tài khoản Git, registry, database hay thông tin đăng nhập hệ điều hành. Mỗi tài khoản nên có quyền nhỏ nhất cần thiết cho đúng queue/topic. Không nhầm `spring.artemis.password` với tùy chọn giao thức JMS chuẩn: đây là property **của Spring Boot cho provider Artemis**, không phải property chung áp dụng cho mọi broker.

**Phân biệt Spring Framework và Spring Boot:** Spring Framework cung cấp Spring JMS nhưng không tự quy định bộ cấu hình `spring.artemis.*`. Spring **Boot** (khi có Artemis starter và điều kiện auto-configuration) mới tự đọc các property đó để tạo `ConnectionFactory`. Nếu ứng dụng chỉ dùng Spring Framework thuần, developer phải tự cấu hình `ConnectionFactory` từ `Environment`/`@Value` hoặc cơ chế dependency injection tương đương.

## 3. Cấu hình Spring Boot bằng placeholder môi trường

Với Spring Boot 3.x, starter Artemis dùng namespace `jakarta.jms.*` và có các property thường gặp:

| Property Spring Boot | Ý nghĩa |
| --- | --- |
| `spring.artemis.mode` | `native`: kết nối broker Artemis riêng; `embedded` là lựa chọn khác khi dependency/phần mềm hỗ trợ |
| `spring.artemis.broker-url` | URI broker mà Artemis client sử dụng |
| `spring.artemis.user` | Username xác thực với broker |
| `spring.artemis.password` | Password tương ứng |
| `spring.jms.template.receive-timeout` | Timeout khi `JmsTemplate` nhận đồng bộ; không phải thời gian timeout TCP mặc định |
| `spring.jms.cache.session-cache-size` | Số session được cache trong wrapper connection factory khi cấu hình phù hợp |

### 3.1. Cách A: application.yml chỉ chứa tên biến, không chứa giá trị bí mật

Tạo `src/main/resources/application.yml`:

~~~yaml
spring:
  artemis:
    mode: native
    broker-url: ${JMS_BROKER_URL}
    user: ${JMS_USERNAME}
    password: ${JMS_PASSWORD}
~~~

Ba placeholder được Spring giải quyết từ `Environment` của ứng dụng. Ví dụ, người vận hành có thể cấp:

~~~text
JMS_BROKER_URL=tcp://broker.example.internal:61616
JMS_USERNAME=orders-producer
JMS_PASSWORD=[giá trị bí mật chỉ cấp khi chạy]
~~~

Đây là **minh họa tên biến**, không phải yêu cầu lưu các dòng chứa password thật trong repository. Spring Boot dùng cú pháp `${PROPERTY_NAME}` và có thể đặt giá trị mặc định dạng `${PROPERTY_NAME:default}`.

- **Broker URL** đôi khi có thể có default an toàn cho local, chẳng hạn `${JMS_BROKER_URL:tcp://localhost:61616}`, nhưng production nên cấu hình rõ.
- **Password** nên dùng `${JMS_PASSWORD}` **không kèm default yếu** như `changeme` hoặc chuỗi rỗng. Điều này giúp lỗi cấu hình xuất hiện sớm khi biến không được cấp.
- **Username** cũng nên do runtime cung cấp; tránh ngầm dùng tài khoản admin chung.
- Không truyền bí mật qua Java arguments dạng `--spring.artemis.password=...` hoặc `-D...` nếu có thể tránh, vì command line có thể xuất hiện trong process list hoặc hệ thống ghi nhận thao tác.

Một tính chất quan trọng của `application.yml` ở ví dụ: **Git chỉ giữ mapping giữa tên property và biến môi trường**, không chứa mật khẩu thực.

### 3.2. Cách B: đặt property trực tiếp từ OS environment

Spring Boot hỗ trợ **relaxed binding**: có thể ánh xạ environment variable sang `@ConfigurationProperties`. Quy tắc chuẩn khi biến đổi tên property: thay dấu chấm bằng gạch dưới, **bỏ dấu gạch ngang**, rồi viết hoa. Ví dụ:

~~~text
spring.artemis.user                → SPRING_ARTEMIS_USER
spring.artemis.password            → SPRING_ARTEMIS_PASSWORD
spring.artemis.broker-url          → SPRING_ARTEMIS_BROKERURL
spring.jms.template.receive-timeout→ SPRING_JMS_TEMPLATE_RECEIVETIMEOUT
~~~

Tùy nguồn cấu hình và phiên bản, một số biến viết theo kiểu snake_case cũng có thể được nhận qua cơ chế môi trường; **để tránh phụ thuộc vào cách chuẩn hóa tên**, ví dụ thực hành bên dưới dùng `application.yml` với ba placeholder rõ ràng `JMS_*`. Nếu chọn cách B, xác minh kết quả binding bằng một bài kiểm thử cấu hình của chính phiên bản Spring Boot đang chạy.

Không dùng đồng thời nhiều tên không cần thiết khiến một giá trị ghi đè giá trị kia khó nhận biết. Chọn một convention cho dự án rồi ghi trong tài liệu triển khai.

### 3.3. Property precedence không phải cơ chế bảo mật

Spring Boot nạp nhiều nguồn cấu hình với thứ tự ưu tiên. Ở cấu hình thông thường, environment variables có thể ghi đè property đặt trong file đóng gói; command-line properties thường có độ ưu tiên cao hơn nhiều nguồn file/env. Điều này giúp triển khai cùng một JAR sang dev/test/prod.

Tuy vậy, **nguồn nào có độ ưu tiên cao nhất chưa chắc là nguồn an toàn nhất**. Tránh để một tham số CLI hoặc file local vô tình thay thế credential production. Nếu cần chẩn đoán property source, chỉ ghi **tên nguồn và trạng thái có/không**; tuyệt đối không in giá trị password.

~~~java
// Minh họa: có thể kiểm tra sự hiện diện của biến, KHÔNG in bí mật.
boolean provided = System.getenv("JMS_PASSWORD") != null;
System.out.println("JMS_PASSWORD provided: " + provided);
~~~

Đoạn trên chỉ nên dùng tạm khi gỡ lỗi, không phải yêu cầu log trạng thái credential ở mọi môi trường. Hệ thống production không cần tiết lộ thông tin chi tiết về cơ chế lưu bí mật vào response công khai.

## 4. Demo thực hành: Spring Boot + Artemis + Docker Compose

Đây là một project hoàn chỉnh cho **Java 17+**, **Maven**, **Docker và Docker Compose v2**, Spring Boot **3.5.7**. Mục tiêu là dùng một file cấu hình có placeholder và đưa credential vào container **chỉ lúc chạy**. Demo gửi một message đơn giản để kiểm tra `ConnectionFactory` dùng đúng thông số. **Không đưa mật khẩu thật vào source, JAR hay Docker image**.

### 4.1. Cấu trúc thư mục

~~~text
jms-env-demo/
├── pom.xml
├── Dockerfile
├── compose.yaml
├── .dockerignore
├── .gitignore
├── .env.example
└── src/
    └── main/
        ├── java/com/example/jms/EnvJmsApplication.java
        └── resources/application.yml
~~~

File `.env.example` chứa **placeholder giả**, có thể commit. File `.env` chứa giá trị thật chỉ dành cho máy local và **phải bị bỏ qua bởi Git**. Một số công ty còn cấm dùng file plaintext `.env` cho production; ở đó phải dùng secret manager thay thế.

### 4.2. Maven — `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>jms-env-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-artemis</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-boot-starter-artemis` giúp Spring Boot cấu hình phần client và `JmsTemplate`. Khi code dùng Artemis provider, property là `spring.artemis.*`. Không dùng tên property của ActiveMQ Classic (`spring.activemq.*`) để giả định nó sẽ cấu hình Artemis.

### 4.3. Cấu hình ứng dụng — `src/main/resources/application.yml`

~~~yaml
spring:
  application:
    name: jms-env-demo
  artemis:
    mode: native
    broker-url: ${JMS_BROKER_URL}
    user: ${JMS_USERNAME}
    password: ${JMS_PASSWORD}
~~~

File này có thể commit: nó **không chứa credential**, chỉ tham chiếu tới ba biến cần cấp. URI thực tế có thể khác nhau ở local host, trong Docker network và ở hạ tầng sản xuất.

### 4.4. Ứng dụng Java — `src/main/java/com/example/jms/EnvJmsApplication.java`

~~~java
package com.example.jms;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.core.JmsTemplate;

@SpringBootApplication
public class EnvJmsApplication {

    public static void main(String[] args) {
        SpringApplication.run(EnvJmsApplication.class, args);
    }

    @Bean
    CommandLineRunner sendOne(JmsTemplate jmsTemplate) {
        return args -> {
            // Dữ liệu nghiệp vụ mẫu, KHÔNG phải credential.
            jmsTemplate.convertAndSend("demo.env.config", "ping");
            System.out.println("JMS send OK");
        };
    }
}
~~~

Không có `System.getenv("JMS_PASSWORD")`, mật khẩu, username hay địa chỉ broker trong Java source. Spring đã inject `JmsTemplate`; Boot tạo `ConnectionFactory` từ thông tin trong `Environment`. Lệnh `convertAndSend` làm việc qua JMS provider; nếu kết nối, xác thực hoặc quyền gửi lỗi, lời gọi sẽ phát sinh exception. Ví dụ này kiểm tra **send thành công**, không ngụ ý consumer đã xử lý message.

Lưu ý broker Artemis demo có thể tự tạo queue theo chính sách mặc định. Production nên provision queue/address và cấp quyền send/consume cụ thể thay vì dựa vào auto-create cho mọi đích.

### 4.5. Dockerfile — build không cần bí mật

~~~dockerfile
FROM maven:3.9.9-eclipse-temurin-17 AS build
WORKDIR /workspace
COPY pom.xml .
COPY src ./src
RUN mvn -q -DskipTests package

FROM eclipse-temurin:17-jre
WORKDIR /app
COPY --from=build /workspace/target/jms-env-demo-0.0.1-SNAPSHOT.jar /app/app.jar
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

**Không khai báo `ARG JMS_PASSWORD` hay `ENV JMS_PASSWORD=...` trong Dockerfile**. Build stage không cần quyền truy cập broker và không cần secret. Mật khẩu phải được cấp ở **runtime**, tránh nằm trong layer/metadata của image.

### 4.6. Docker Compose — `compose.yaml`

~~~yaml
services:
  broker:
    image: apache/artemis:latest-alpine
    environment:
      ARTEMIS_USER: ${JMS_USERNAME:?Set JMS_USERNAME in the environment}
      ARTEMIS_PASSWORD: ${JMS_PASSWORD:?Set JMS_PASSWORD in the environment}
    ports:
      - "127.0.0.1:61616:61616"

  app:
    build: .
    depends_on:
      - broker
    restart: "on-failure:5"
    environment:
      JMS_BROKER_URL: "tcp://broker:61616"
      JMS_USERNAME: ${JMS_USERNAME:?Set JMS_USERNAME in the environment}
      JMS_PASSWORD: ${JMS_PASSWORD:?Set JMS_PASSWORD in the environment}
~~~

Giải thích các quyết định:

1. Compose thay `${JMS_USERNAME}` và `${JMS_PASSWORD}` bằng giá trị tại thời điểm triển khai. Cú pháp `:?` trong **Compose** khiến thiếu/giá trị rỗng báo lỗi; đây **không phải cú pháp placeholder của Spring**.
2. Broker image Artemis nhận `ARTEMIS_USER` và `ARTEMIS_PASSWORD`, còn **ứng dụng** nhận `JMS_USERNAME` và `JMS_PASSWORD` rồi để Spring giải placeholder. Hai bên dùng cùng tài khoản lab cho demo.
3. Trong Docker network, hostname của broker là **tên service** `broker`: `tcp://broker:61616`. `localhost` bên trong container app chỉ trỏ đến **chính container app**, không trỏ đến broker.
4. `depends_on` ngắn chỉ sắp thứ tự khởi động container, **không chứng minh broker đã sẵn sàng nhận kết nối JMS**. `restart: "on-failure:5"` cho app thử lại bằng cách khởi động lại nếu lần đầu bắt gặp broker chưa sẵn sàng. Với production, dùng readiness/healthcheck và retry có giới hạn ở tầng phù hợp.
5. Mapping `127.0.0.1:61616:61616` chỉ phục vụ máy đang chạy demo; container app giao tiếp qua network nội bộ, không cần publish port broker ra toàn mạng.
6. Biến môi trường trong cấu hình Compose này có thể xuất hiện với người có quyền kiểm tra container/config. **Compose env không thay thế secret manager production.**

### 4.7. Không để file secret vào Git hay Docker context

Tạo `.gitignore`:

~~~gitignore
.env
.env.*
!.env.example
target/
~~~

Tạo `.dockerignore`:

~~~dockerignore
.git
.env
.env.*
target/
~~~

`.env` bị Git ignore **không đảm bảo** tuyệt đối: một file đã từng được commit vẫn nằm trong lịch sử Git; `.gitignore` không tự xóa lịch sử. Nếu credential đã lộ, cần **revoke/rotate** ở broker và xử lý repository theo chính sách bảo mật, không chỉ thêm ignore.

Tạo `.env.example` chứa hai placeholder **không có giá trị thật**:

~~~dotenv
JMS_USERNAME=replace-with-local-user
JMS_PASSWORD=replace-with-local-password
~~~

Tại máy local, sao chép file đó thành `.env`, rồi thay hai placeholder bằng username và password riêng của môi trường lab. Không chia sẻ file `.env` qua chat, email, PR, issue hay báo cáo build. Không dùng mật khẩu thật trong ảnh chụp màn hình.

Lệnh tạo bản sao trên Bash:

~~~bash
cp .env.example .env
# Sửa .env bằng editor trên máy cá nhân, không commit.
docker compose up --build
~~~

Lệnh trên PowerShell:

~~~powershell
Copy-Item .env.example .env
# Sửa .env trong editor trước khi chạy.
docker compose up --build
~~~

Compose tự đọc file `.env` trong ngữ cảnh project để **nội suy** các biến `${JMS_*}`. File `.env` không tự động trở thành toàn bộ environment của container: các dòng trong `compose.yaml` thuộc `environment:` mới truyền giá trị cụ thể vào `broker` và `app`. Không nhầm hai bước này.

Nếu broker chạy và app được cấp quyền gửi, log của app có dòng:

~~~text
JMS send OK
~~~

Docker Compose và Spring Boot còn in nhiều log khác; thứ tự log không cố định. Có thể xem log app bằng:

~~~bash
docker compose logs app
~~~

Dừng và dọn container/network của demo:

~~~bash
docker compose down
~~~

Lệnh `down` như trên không yêu cầu xóa các file source hoặc `.env` local. Trong môi trường học, muốn chạy lại sau khi sửa thông số thì dùng `docker compose up --build`. Khi đã tạo broker có volume và lưu state, xem chính sách cập nhật account trước khi kỳ vọng chỉ đổi biến là đổi mật khẩu ngay: nhiều image dùng biến lúc **khởi tạo broker lần đầu**, không phải cơ chế rotation động.

**Giới hạn kỹ thuật của demo:** code và file được thiết kế để chạy với bộ image/dependency nêu trên, nhưng ví dụ chưa mô phỏng một secret store production hoặc TLS. Broker khởi động chậm có thể khiến app lỗi ở lần thử đầu và phải retry/restart; nếu demo phụ thuộc phiên bản image di động, hãy pin image digest ở CI/CD.

## 5. Chạy JAR trên máy local (không dùng container cho app)

Cùng `application.yml` ở phần 4 cũng hoạt động nếu chạy Java trực tiếp trên host. Khi broker nằm trên host/được publish tại host, `JMS_BROKER_URL` có thể là `tcp://localhost:61616`.

**Bash (Linux/macOS)** — cách thiết lập biến môi trường cho session; giá trị password lấy từ quy trình phát bí mật do tổ chức cho phép, không hardcode vào script commit:

~~~bash
export JMS_BROKER_URL="tcp://localhost:61616"
export JMS_USERNAME="local-user"
# Cấp JMS_PASSWORD qua secret manager hoặc shell input bảo vệ.
mvn spring-boot:run
~~~

**PowerShell (Windows)** — ví dụ thiết lập biến không nhạy cảm:

~~~powershell
$env:JMS_BROKER_URL = "tcp://localhost:61616"
$env:JMS_USERNAME = "local-user"
# Cấp JMS_PASSWORD bằng công cụ quản lý bí mật trước khi chạy.
mvn spring-boot:run
~~~

Hai đoạn trên **chưa đủ để chạy** nếu `JMS_PASSWORD` chưa được cấp. Đây là chủ ý: phần thực hành đầy đủ ở Docker Compose mô tả cách cấp hai giá trị từ file `.env` bị ignore; còn khi chạy trực tiếp trên host, bí mật phải đến từ cơ chế phù hợp trên máy đó.

Nếu người học dùng secret store có CLI, nên ưu tiên lệnh hoặc wrapper **tiêm biến trực tiếp vào tiến trình con** mà không in giá trị ra terminal; tên lệnh cụ thể phụ thuộc sản phẩm và quyền truy cập. Không gợi ý copy password vào shell history, câu lệnh dài hay ví dụ tài liệu. Sau khi hoàn thành, cần loại bỏ biến nhạy cảm khỏi session/process theo quy định vận hành của tổ chức.

## 6. Khi nào dùng mounted secret thay vì environment variable?

Biến môi trường thường là điểm bắt đầu thuận tiện; nhưng với bí mật thực sự của production, xem xét **file secret được mount vào container** hoặc cấu hình do Vault/Kubernetes/secret manager cung cấp. Spring Boot có cơ chế **configuration tree**: tên file tương ứng property key, nội dung file trở thành giá trị property.

Ví dụ mount tại `/run/secrets/`:

~~~text
/run/secrets/
  spring.artemis.user
  spring.artemis.password
~~~

Có thể import config tree trong `application.yml` (chỉ bật tại môi trường có mount secret):

~~~yaml
spring:
  config:
    import: "configtree:/run/secrets/"
  artemis:
    mode: native
    broker-url: ${JMS_BROKER_URL}
~~~

Khi đó file `/run/secrets/spring.artemis.user` chứa username và file `/run/secrets/spring.artemis.password` chứa password. **Không đặt nội dung bí mật trong YAML**. Nếu cấu hình secrets không hiện diện thì import không có `optional:` sẽ fail sớm; nếu dùng `optional:configtree:/run/secrets/` thì hệ thống có thể không có secret mà vẫn đi tiếp tới một lỗi khác — lựa chọn tùy chính sách fail-fast.

**Phân biệt configtree với env placeholders:** một cấu hình dùng `${JMS_PASSWORD}` đòi phải có property `JMS_PASSWORD`; file `spring.artemis.password` tạo property **`spring.artemis.password`**. Vì vậy khi chuyển sang configtree, cần bỏ hoặc điều chỉnh placeholder xung đột. **Đừng vừa khai báo `spring.artemis.password: ${JMS_PASSWORD}` vừa kỳ vọng mount file sẽ tự thay thế thiếu env**, vì giá trị placeholder không tự đổi tên thành property key khác.

Kubernetes có thể inject một Secret vào biến môi trường bằng `secretKeyRef`, ví dụ mảnh YAML trong định nghĩa container:

~~~yaml
env:
  - name: JMS_USERNAME
    valueFrom:
      secretKeyRef:
        name: orders-jms-credentials
        key: username
  - name: JMS_PASSWORD
    valueFrom:
      secretKeyRef:
        name: orders-jms-credentials
        key: password
~~~

Đây chỉ là **mảnh cấu hình container**, không phải manifest Deployment độc lập. Secret phải được tạo ngoài mã nguồn bởi pipeline/operator có quyền phù hợp. Kubernetes Secret mặc định là cách phân phối bí mật qua API cluster, **không đồng nghĩa giá trị luôn được mã hóa end-to-end hoặc tự động được rotate**. Cần áp dụng RBAC, encryption at rest, network security và kế hoạch cập nhật Pod khi credential thay đổi.

Một số secret manager còn cấp token ngắn hạn hoặc chứng chỉ động. Nếu tổ chức đã có giải pháp như Vault, cloud secrets manager hoặc workload identity, ưu tiên tích hợp đã được chuẩn hóa trong hệ thống của tổ chức.

## 7. TLS, xác thực và phân quyền: ba lớp khác nhau

Bí mật không nằm trong Git vẫn có thể bị lộ nếu gửi username/password qua kết nối mạng không được bảo vệ.

1. **Authentication:** broker xác minh client. Demo local dùng tài khoản `JMS_USERNAME/JMS_PASSWORD`.
2. **Transport security:** TLS mã hóa luồng mạng và thường xác minh danh tính server bằng chứng chỉ. Chỉ đặt mật khẩu trong env **không mã hóa** lưu lượng JMS.
3. **Authorization:** sau xác thực, broker cho phép hoặc từ chối các hành động cụ thể như send/consume/create trên queue, topic, address.

`tcp://broker:61616` trong demo là endpoint nội bộ của môi trường học, **không phải cấu hình TLS production**. Với Artemis, phải cấu hình acceptor/connector TLS theo tài liệu của phiên bản broker và client, cấp trust material qua mount/secret manager, đồng thời bật xác minh chứng chỉ/hostname. Tránh đưa key password hoặc password dạng query string vào URL có thể bị log.

Phân quyền ví dụ: service producer chỉ cần quyền **send** vào `orders.request`; consumer cần quyền **consume** tương ứng; không mặc định mọi service dùng user admin. Lỗi `AuthorizationException`/`JMSSecurityException` sau khi kết nối được không nên “sửa” bằng cách cấp quyền quản trị toàn bộ broker.

## 8. Quản trị bí mật qua các môi trường

### 8.1. Local development

- Dùng broker riêng hoặc instance test; username/password lab khác hoàn toàn production.
- File `.env` nếu được cho phép phải nằm ngoài version control, giới hạn quyền đọc, không đồng bộ lên nơi chia sẻ công khai.
- Không đẩy giá trị thật vào `application-local.yml` được commit. Nếu cần file local override, đảm bảo file được ignore đúng và chưa từng được commit.
- Các giá trị không nhạy cảm như host/port/topic name có thể nằm trong profile tương ứng; credential vẫn tiêm từ runtime.

### 8.2. CI pipeline

- Cấp credential qua secret variables/secret manager với phạm vi job và môi trường rõ ràng.
- Không đặt password trong `pom.xml`, Maven resource filtering, build arguments, kiểm thử snapshot hay artifact.
- Giới hạn ai được trigger pipeline dùng production secret; tránh cho pipeline chạy trên pull request từ nguồn không tin cậy đọc secrets.
- Không chạy `echo$JMS_PASSWORD`, `printenv`, `env`, `docker compose config` khi chúng có thể in secret. Masking log là lớp giảm thiểu, không phải bảo đảm chống mọi cách lộ.
- Tách build image (không có secrets) khỏi deploy/running (có secrets). Một image có thể được tái dùng giữa các môi trường.

### 8.3. Staging/production

- Mỗi môi trường dùng credential riêng; tốt hơn nữa là mỗi service/role riêng.
- Quản lý lifecycle cấp phát, luân chuyển, revoke, audit và cảnh báo truy cập bất thường.
- Cấp secret cho đúng service account/namespace, không chia sẻ toàn cluster.
- Với container, hiểu rằng environment có thể bị người có quyền trên host/container đọc qua các cơ chế quản trị. Hạn chế quyền xem logs, inspect và exec.
- Đổi password cần phối hợp cả bên ứng dụng và broker; ứng dụng đang dùng cached connection hoặc pool có thể phải tạo connection mới/restart để áp dụng credential mới.
- Nếu credential đã xuất hiện trong Git history, screenshot hoặc log, **rotate ngay** và xử lý lịch sử/retention; việc xóa một dòng trong commit mới không làm bí mật cũ mất khỏi bản sao.

## 9. Những lỗi cấu hình thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra an toàn |
| --- | --- | --- |
| `Could not resolve placeholder 'JMS_PASSWORD'` | Biến chưa được cấp vào **process app**; Compose `.env` chỉ dùng để nội suy, chưa tự inject | Xem key trong Compose `environment`/orchestrator, kiểm tra trạng thái có/không mà không in value |
| `JMSSecurityException` hoặc broker báo authentication failed | Username/password sai, account bị rotate, TLS/auth settings không khớp | Kiểm tra nơi cấp secret, account status và log đã được redacted |
| `Connection refused` | Broker chưa chạy/chưa sẵn sàng, sai port, network hoặc firewall | Xác minh endpoint và readiness, không thử “sửa” bằng cách gắn password vào URL |
| `UnknownHostException: localhost` / không kết nối trong Compose | App container dùng `localhost` thay vì service `broker` | Dùng `tcp://broker:61616` trong Compose network |
| Startup được nhưng `convertAndSend` lỗi | Connection lazy, chưa kết nối broker ở startup, quyền send thiếu, destination sai | Kiểm tra tại lệnh gửi và broker authorization |
| Local chạy được, production không chạy | Khác property source, URI, DNS, TLS, network, namespace Secret | So sánh **tên và nguồn config**, không dump toàn bộ config |
| Secret đã đổi nhưng connection cũ vẫn sống | Connection pooling/cache và rotation chưa đồng bộ | Recycle connection theo quy trình, giảm lifetime nếu cần, kiểm tra rolling restart |
| `@JmsListener` không nhận dù send thành công | Không đúng destination, quyền consume thiếu, listener config hoặc routing khác | Kiểm tra queue depth, consumer count, ack/transaction và routing |
| Build image lộ bí mật | Đã copy `.env` vào Docker context/image hoặc dùng `ARG/ENV` hardcode | Rà soát Dockerfile, history, CI logs, rotate credential và xây lại image |
| App dùng giá trị khác mong đợi | Command-line/Env/Profile/ConfigData ghi đè nhau | Xác minh property source precedence, tuyệt đối không in password |

**Đặc biệt:** `JmsTemplate` có thể tạo kết nối khi thao tác send/receive thực sự xảy ra, nên ứng dụng “khởi động không lỗi” **chưa chứng minh** cấu hình credentials hoạt động. Một smoke test gửi/nhận có quyền phù hợp cung cấp tín hiệu tốt hơn.

### 9.1. Gỡ lỗi mà không ghi lộ secret

Đừng in các thông tin này vào log hoặc endpoint công khai:

~~~java
// KHÔNG làm:
System.out.println(System.getenv("JMS_PASSWORD"));
System.out.println(System.getenv());
~~~

Với Spring Boot Actuator, endpoint `/actuator/env` và `/actuator/configprops` có chức năng quan sát property/config. Những endpoint này phải được bảo vệ, hạn chế truy cập và cấu hình sanitization thích hợp; không mở public chỉ để dò giá trị. Kể cả khi giá trị bị mask, metadata và tên cấu hình vẫn có thể nhạy cảm.

Một số nhóm kiểm tra trạng thái bằng một probe **không tiết lộ giá trị** như sau:

~~~java
boolean hasUser = System.getenv("JMS_USERNAME") != null;
boolean hasPass = System.getenv("JMS_PASSWORD") != null;
if (!hasUser || !hasPass) {
    throw new IllegalStateException(
        "Missing required JMS credentials in runtime configuration");
}
~~~

Đoạn trên là **mảnh code minh họa**, không phải class độc lập; có thể đặt trong startup validation nếu muốn fail-fast. Cần phân biệt **có biến** với **giá trị hợp lệ**; chuỗi rỗng hoặc credential bị revoke vẫn không kết nối được. Ví dụ Compose `:?` ở phần 4 phát hiện cả biến thiếu lẫn rỗng sớm.

## 10. Kiểm thử tối thiểu và tiêu chí nghiệm thu

Trước khi bàn giao một cấu hình JMS externalized, nên có các bài kiểm tra có ý nghĩa:

1. **Không có password:** Compose phải từ chối khởi động khi `JMS_PASSWORD` thiếu/rỗng; app chạy ngoài Compose phải fail rõ khi placeholder không được giải quyết hoặc authentication thất bại.
2. **Đúng credential:** broker nhận kết nối, service có quyền send và bài demo in `JMS send OK`.
3. **Sai credential:** broker từ chối và ứng dụng báo lỗi xác thực; log không được chứa password.
4. **Sai host/port:** thấy lỗi kết nối, có retry/readiness có kiểm soát; không im lặng coi là gửi thành công.
5. **Quyền thiếu:** nếu user không có quyền send vào queue, test phải fail riêng với lỗi authorization.
6. **Khác môi trường:** cùng Docker image/JAR chạy với broker URL và account khác mà không rebuild.
7. **Git/Docker:** bảo đảm `.env` không tracked, không xuất hiện trong image layers, artifacts, logs, error reports; xác minh cả lịch sử nếu trước đó từng commit.
8. **Rotation:** đổi credential trong secret store, cập nhật Pod/process/connection theo quy trình và xác minh kết nối mới; credential cũ bị revoke.
9. **TLS production:** chứng chỉ server được xác minh, thông số TLS được cấp và bảo vệ đúng, không dựa vào plaintext TCP từ demo.
10. **Giới hạn truy cập:** người vận hành chỉ có quyền cần thiết; hạn chế inspect container, exec, CI secret access và các endpoint config.

Có thể dùng integration test với broker test/embedded/container cùng credentials riêng cho test. Không đưa password sản xuất vào test source hay fixture. Để kiểm tra mã, không cần bất kỳ credential production nào.

## 11. Câu hỏi tự kiểm tra

**Câu 1.** Có an toàn nếu chuyển mật khẩu từ Java source sang `application.yml` rồi commit?  
**Trả lời:** Không, nếu giá trị trong YAML là mật khẩu thật thì vẫn bị lưu vào Git. YAML nên chứa **placeholder hoặc đường dẫn/khóa cấu hình**, secret thực cấp tại runtime.

**Câu 2.** Compose có `.env`, tại sao Java app vẫn không thấy `JMS_PASSWORD`?  
**Trả lời:** `.env` chủ yếu phục vụ nội suy biến Compose; ứng dụng chỉ nhận giá trị nếu Compose truyền nó vào container qua `environment`/`env_file` hoặc cơ chế tương đương.

**Câu 3.** Vì sao `tcp://localhost:61616` có thể chạy trên host nhưng lỗi trong app container?  
**Trả lời:** `localhost` của container app trỏ chính nó. Trong Compose example, broker nằm tại hostname service `broker`, nên app dùng `tcp://broker:61616`.

**Câu 4.** Đặt password trong env là đã đủ bảo mật mạng chưa?  
**Trả lời:** Chưa. Phải bổ sung TLS đúng cách, quyền broker tối thiểu, secret storage phù hợp và kiểm soát truy cập môi trường runtime.

**Câu 5.** `spring.artemis.password` có được JVM tự hiểu chỉ vì là env variable không?  
**Trả lời:** Spring Boot `Environment` và cơ chế binding/placeholder mới đọc cấu hình cho bean/provider. Khi chỉ dùng Spring Framework thuần, cần tự bind vào `ConnectionFactory`.

**Câu 6.** Làm sao deploy cùng một JAR sang staging và prod mà không sửa code?  
**Trả lời:** Cho mỗi môi trường cấp `JMS_BROKER_URL`, `JMS_USERNAME`, `JMS_PASSWORD` hoặc mounted secrets riêng. Giữ mã và YAML placeholder giống nhau, phân quyền và security policy riêng.

**Câu 7.** Khi dùng `configtree:/run/secrets/` với file `spring.artemis.password`, có cần cả `${JMS_PASSWORD}` không?  
**Trả lời:** Không tự động; đây là hai tên property khác nhau. Dùng cấu hình thống nhất để file secret cung cấp trực tiếp `spring.artemis.password` hoặc đổi cấu trúc secret/placeholder cho khớp.

**Câu 8.** Nếu password đã bị commit một lần rồi sửa bằng commit mới, đã an toàn chưa?  
**Trả lời:** Chưa. Git history/các clone vẫn có thể giữ bản cũ; cần revoke/rotate và xử lý rò rỉ theo quy trình.

**Câu 9.** Có nên log toàn bộ `Environment` khi gặp lỗi JMS?  
**Trả lời:** Không. Chỉ log metadata đã lọc, error code và nguồn cấu hình; hạn chế Actuator và kiểm tra log sanitization.

**Câu 10.** Vì sao gửi thành công chưa chắc consumer đã xử lý message?  
**Trả lời:** Gửi thành công chủ yếu cho thấy client kết nối, được xác thực/ủy quyền và broker nhận thao tác theo semantics; consumer/ack/transaction/handler nằm ở bước tiếp theo.

## 12. Tài liệu chính thức

1. [Spring Boot Reference — Externalized Configuration: precedence, placeholders, environment variables và config trees](https://docs.spring.io/spring-boot/reference/features/external-config.html)
2. [Spring Boot 3.5 Reference — JMS/ActiveMQ Artemis configuration](https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html)
3. [Spring Boot — Properties and Configuration](https://docs.spring.io/spring-boot/how-to/properties-and-configuration.html)
4. [Spring Framework Reference — JMS, ConnectionFactory và JmsTemplate](https://docs.spring.io/spring-framework/reference/integration/jms/using.html)
5. [Apache ActiveMQ Artemis — Official Docker image và ARTEMIS_USER/ARTEMIS_PASSWORD](https://artemis.apache.org/components/artemis/documentation/latest/docker.html)
6. [Docker Compose — Environment variables và interpolation](https://docs.docker.com/compose/how-tos/environment-variables/variable-interpolation/)
7. [Docker Compose — Define services, environment, depends_on](https://docs.docker.com/reference/compose-file/services/)
8. [Kubernetes — Distribute Credentials Securely Using Secrets](https://kubernetes.io/docs/tasks/inject-data-application/distribute-credentials-secure/)

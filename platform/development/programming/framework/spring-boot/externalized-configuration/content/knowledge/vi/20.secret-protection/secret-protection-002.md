# Tách bí mật khỏi Git, tài nguyên classpath và bản dựng ứng dụng Spring Boot

## 1. Mục tiêu và bối cảnh

Spring Boot hỗ trợ **externalized configuration** để một phiên bản ứng dụng có thể hoạt động ở local, staging và production bằng các giá trị cấu hình khác nhau. Cơ chế này mang lại một lợi ích quan trọng về bảo mật: không cần gắn credential production vào mã nguồn hoặc vào file tài nguyên đóng gói cùng ứng dụng.

Cấu hình ứng dụng có thể được phân nhóm:

- **Thông thường:** port, timeout, chế độ log, feature flag, endpoint không chứa credential.
- **Bí mật:** database password, API token, OAuth client secret, private key, signing key, khóa mã hóa, credential của message broker và các dịch vụ bên ngoài.
- **Metadata nhạy cảm theo ngữ cảnh:** connection string chứa userinfo, đường dẫn secret mount, tenant identifier, hostname nội bộ hoặc resource location có token trong query.

Một lỗi phổ biến là đưa password thật vào `src/main/resources/application-prod.yml`, commit lên Git, rồi build thành executable JAR. Lúc này, secret có thể tồn tại trong ít nhất ba nơi: **Git history**, **classpath của JAR** và **artifact/image được phân phối**. Xóa dòng secret trong phiên bản hiện tại không tự thu hồi các bản sao cũ.

**Nguyên tắc trung tâm:**

> Git và bản dựng nên chứa code, metadata và cấu hình không bí mật; secret thật được cung cấp ở runtime bằng một nguồn được quản lý có phân quyền và vòng đời riêng.

Bài học giải thích:

1. Tại sao `.gitignore` không đủ để bảo vệ secret.
2. Vì sao tài nguyên `src/main/resources` không phải secret store.
3. Những nơi Maven, Gradle, CI và Docker build có thể làm credential bị lưu lại.
4. Các phương án cấp bí mật cho Spring Boot: environment, mounted file, `configtree:` và secret manager.
5. Validation, logging, Actuator, rotation và cách kiểm chứng secret không xuất hiện trong artifact.
6. Quy trình xử lý khi credential đã từng được commit hoặc phát hành.

Không có annotation nào trong Spring Boot tự bảo đảm toàn bộ các điều này. Cần kết hợp thiết kế ứng dụng, hệ thống build và kiểm soát vận hành.

## 2. Ba ranh giới: Git, classpath, artifact

### 2.1. Git là hệ thống lịch sử, không phải vault

Git giữ lại các phiên bản của file theo commit. Một file đã từng chứa credential không biến mất khỏi lịch sử chỉ vì file hiện tại không còn dòng đó.

Ví dụ không an toàn:

~~~properties
# src/main/resources/application-prod.properties
spring.datasource.username=orders_user
spring.datasource.password=REAL_DATABASE_PASSWORD
payment.gateway.api-key=REAL_API_KEY
~~~

Những chuỗi trên là placeholder minh họa, không phải thông tin đăng nhập thực. Trong dự án thật, không được đưa credential có hiệu lực vào file tracked.

Ngay cả private repository cũng có nhiều người và hệ thống có thể đọc: collaborator, CI job, bản clone, mirror, backup hoặc công cụ phân tích source. Quyền đọc Git khác với quyền được sử dụng một secret.

### 2.2. Classpath là phần mềm được phân phối

Các file ở `src/main/resources` thường được Maven hoặc Gradle đưa vào output resources. Trong executable JAR của Spring Boot, chúng thường nằm dưới `BOOT-INF/classes/`.

Ví dụ:

~~~text
src/main/resources/
  application.yml
  application-prod.yml
  keys/private-signing.pem
~~~

Nếu một trong những file này chứa private key thật, nội dung có thể nằm trong JAR. Người có thể tải/extract artifact có thể đọc resource mà không cần chạy ứng dụng hoặc kích hoạt profile production.

### 2.3. Artifact được sao chép và lưu giữ

Sau khi build, JAR có thể được lưu trong artifact repository, CI artifacts, registry, image layer, cache, máy deploy và hệ thống backup. Một tag Docker cũ có thể còn chứa JAR mang secret đã lộ. Xóa image mới hoặc sửa source không tự làm các bản sao đó sạch.

**Kết luận:** cần bảo vệ secret ở **nguồn**, **giai đoạn build**, **output artifact** và **runtime**.

## 3. Sơ đồ mô hình không an toàn

~~~text
Developer
   |
   v
application-prod.yml chứa password thật
   |
   v
Git commit / pull request / clone
   |
   v
Maven hoặc Gradle xử lý resource
   |
   v
target/classes hoặc build/resources/main
   |
   v
Executable JAR / WAR
   |
   v
Docker image / registry / backup
   |
   v
Production runtime
~~~

Nếu credential bị lộ ở bất kỳ bước nào, việc đưa secret ra ngoài runtime ở các bản phát hành sau chưa đủ để bảo đảm credential cũ không còn sử dụng được. Cần rotate/revoke secret và xử lý phạm vi ảnh hưởng.

Các tình huống làm rủi ro tăng thêm:

- CI in giá trị configuration ra log để debug.
- Test snapshot lưu object chứa token.
- Maven/Gradle expand biến môi trường vào resource output.
- Dockerfile copy file rồi xóa ở layer sau.
- Crash report hoặc heap dump giữ lại giá trị trong memory.
- Lỗi binding ghi raw rejected value ra console.

## 4. Sơ đồ mô hình khuyến nghị

~~~text
Git repository
  ├── Java code
  ├── application.yml (không có secret value)
  ├── metadata về tên property và import location
  └── tests với dữ liệu giả
             |
             v
       CI build + scan
             |
             v
      JAR và OCI image sạch
             |
             v
      Deploy cùng artifact
             |
      +------+--------------------+
      |                           |
 Runtime identity          Secret manager /
      |                    mounted secret volume
      +-------------+-------------+
                    |
                    v
             Spring Environment
                    |
                    v
           @ConfigurationProperties
                    |
                    v
             Bean sử dụng secret
~~~

Mục tiêu là một **artifact bất biến** có thể được deploy đến các môi trường khác nhau. Secrets production không cần xuất hiện trong artifact đó; deployment inject thông tin từ nguồn bí mật riêng.

Bản thân Spring Boot vẫn phải nhận và sử dụng giá trị secret trong tiến trình. Vì vậy, “không có secret trong JAR” không có nghĩa “không có secret trong memory hoặc runtime filesystem”.

## 5. Phân loại những gì có thể commit

| Nội dung | Trong Git | Trong classpath/JAR | Nguồn thay thế |
| --- | --- | --- | --- |
| `server.port=8080` | Có | Có thể | Config Data cơ sở |
| `app.client.timeout=3s` | Có | Có thể | Config Data cơ sở |
| Tên property `payment.gateway.api-key` | Có | Có thể | Schema/config metadata |
| API key thật | Không | Không | Runtime secret |
| Password database | Không | Không | Secret manager/volume |
| Private TLS/signing key | Không | Không | Secret manager/runtime file |
| Public certificate | Tùy chính sách | Có thể | Classpath/external file |
| Build token để tải thư viện private | Không | Không | CI/build secret |
| Connection string có credential | Không | Không | Secret source |
| Giá trị giả dùng để test | Có nếu vô hại | Có thể ở test resources | Fake fixture |

Một URL có thể là dữ liệu bình thường nếu nó chỉ chứa địa chỉ dịch vụ, nhưng trở thành dữ liệu nhạy cảm nếu có password trong userinfo hoặc access token trong query parameter.

Đừng quyết định độ nhạy chỉ bằng tên key. Một key `app.endpoint` có thể giữ một URL chứa credential; một field `notes` cũng có thể vô tình chứa token.

## 6. Tại sao `.gitignore` cần thiết nhưng không đủ?

`.gitignore` giúp Git bỏ qua các file **chưa được theo dõi** khớp với quy tắc.

Ví dụ:

~~~gitignore
.env
.env.*
!.env.example

local-secrets/
config/private/
application-local-secret.properties

*.p12
*.pfx
*.key
~~~

Các pattern này cần được điều chỉnh theo chính sách dự án. Một file extension không tự chứng minh dữ liệu có secret; ngược lại, token có thể nằm trong file tên `notes.txt`.

### 6.1. File đã được track không tự bị bỏ track

Nếu `application-prod.yml` đã được commit trước khi thêm vào `.gitignore`, Git vẫn có thể tiếp tục quản lý file đó.

Có thể kiểm tra:

~~~bash
git ls-files src/main/resources/application-prod.yml
~~~

Khi cần ngừng tracking file mà giữ bản local, thao tác Git có chủ đích có thể là:

~~~bash
git rm --cached src/main/resources/application-prod.yml
~~~

Tuy nhiên, lệnh này **không xóa secret khỏi Git history**. Nếu credential đã từng được push, việc đầu tiên thường là thu hồi hoặc thay secret đó theo quy trình xử lý sự cố.

### 6.2. Các đường đi ngoài Git

`.gitignore` không ngăn:

- `git add -f` hoặc thao tác ép stage file.
- Một file đã tracked từ trước.
- Secret được viết thẳng trong Java source hoặc test.
- Token bị đưa vào generated files.
- Docker build lấy file từ filesystem local.
- Secret xuất hiện trong log, screenshot, ticket hoặc CI artifacts.

Do đó cần **pre-commit scan, CI scan, server-side protection, artifact scan** và code review.

### 6.3. File mẫu không chứa giá trị thật

Nên cung cấp:

~~~dotenv
# .env.example
PAYMENT_GATEWAY_APIKEY=
DB_PASSWORD=
APP_CLIENT_TIMEOUT=3s
~~~

File mẫu chỉ thể hiện **tên khóa** và một số giá trị không nhạy cảm. Nó không chứa secret thật và không chứa password mẫu có thể vô tình dùng production.

Lưu ý: Spring Boot không mặc định nạp mọi file `.env` nằm cạnh JAR. Công cụ như Docker Compose có cơ chế đọc `.env` riêng. Đừng xây thiết kế dựa trên giả định Spring tự hiểu file đó nếu chưa cấu hình loader cụ thể.

## 7. Không đặt bí mật trong `src/main/resources`

Các file dưới `src/main/resources` thường được copy vào output classpath:

~~~text
src/main/resources/production-credentials.json
src/main/resources/private-key.pem
src/main/resources/application-prod.yml
src/main/resources/config/secrets.properties
~~~

Nếu những file này chứa secret, secret có thể đi theo JAR. Đặc biệt nguy hiểm nếu nội dung bị đưa vào:

~~~text
src/main/resources/static/
src/main/resources/public/
src/main/resources/templates/
~~~

Một số resource static có thể được phục vụ qua HTTP theo cách ứng dụng cấu hình. Kể cả khi không phục vụ công khai, chúng vẫn không phải nơi phù hợp để lưu private key và credential.

### 7.1. File nào vẫn nên giữ trong classpath?

Một `application.yml` chỉ chứa cấu hình bình thường hoàn toàn có thể được version-control:

~~~yaml
spring:
  application:
    name: payment-service

payment:
  gateway:
    endpoint: "https://gateway.example.test/v1"
    timeout: 3s
~~~

Có thể giữ các thông tin:

- default timeout, retry, log level được phép;
- tên property hoặc prefix để bind;
- profile activation không bí mật;
- đường dẫn import runtime đã được cho phép công khai;
- public certificate hoặc tài nguyên thực sự công khai khi phù hợp.

Không nên coi file `application-prod.yml` là vùng bí mật chỉ vì tên có “prod”. Nếu được đóng gói vào JAR, nội dung của nó nằm trong artifact dù profile không được kích hoạt lúc chạy local.

### 7.2. Placeholder không chứa giá trị thật

Có thể khai báo:

~~~properties
payment.gateway.api-key=${PAYMENT_GATEWAY_APIKEY}
~~~

Đây là **tham chiếu đến một property tại runtime**, không phải chính secret. Nếu environment cung cấp `PAYMENT_GATEWAY_APIKEY`, Spring có thể phân giải giá trị qua `Environment`.

Tuy nhiên, cách này không tự làm environment an toàn hơn. Nếu deployment hoặc CI in toàn bộ biến môi trường, bí mật vẫn có thể lộ. Với Spring Boot relaxed binding, nhiều trường hợp không cần placeholder trung gian vì biến môi trường có thể bind trực tiếp vào `payment.gateway.api-key`.

### 7.3. Không dùng mặc định bí mật

Ví dụ không nên:

~~~properties
payment.gateway.api-key=${PAYMENT_GATEWAY_APIKEY:password123}
~~~

Giá trị mặc định có vẻ giúp ứng dụng khởi động nhưng tạo rủi ro dùng credential mẫu khi triển khai sai. Với secret bắt buộc, nên fail startup rõ ràng nếu thiếu.

## 8. Cấu hình có kiểu và validation

Một lớp `@ConfigurationProperties` có thể định nghĩa nhóm credential:

~~~java
package com.example.payment.config;

import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "payment.gateway")
public class GatewayCredentials {

    @NotBlank
    private String apiKey;

    public String getApiKey() {
        return apiKey;
    }

    public void setApiKey(String apiKey) {
        this.apiKey = apiKey;
    }

    @Override
    public String toString() {
        return "GatewayCredentials{apiKey=<redacted>}";
    }
}
~~~

Đăng ký:

~~~java
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class PaymentApplication {
}
~~~

Với Bean Validation provider tương ứng (thường qua `spring-boot-starter-validation` trên Spring Boot 3.x), `@NotBlank` giúp phát hiện secret thiếu hoặc blank.

**Đừng hiểu custom `toString()` là giải pháp hoàn chỉnh.** Những nơi khác vẫn có thể làm lộ secret: exception từ Binder/converter, serialize object, heap dump, log trực tiếp `getApiKey()`, Actuator hoặc tracing attributes.

### 8.1. Không log bean cấu hình

Không nên:

~~~java
log.info("Gateway settings: {}", credentials);
log.info("API key: {}", credentials.getApiKey());
~~~

Có thể dùng message an toàn:

~~~java
log.info("Gateway credentials configuration initialized");
~~~

Khi xảy ra lỗi:

~~~text
[CFG-SECRET-001] Required payment gateway credential is missing.
Property: payment.gateway.api-key
Action: verify runtime secret source and permissions.
~~~

Không in rejected value, nội dung file secret hoặc toàn bộ `Environment`.

## 9. Cách 1: cấp secret qua environment ở runtime

Spring Boot hỗ trợ environment variables như một nguồn cấu hình. Với tên canonical:

~~~text
payment.gateway.api-key
~~~

tên biến môi trường theo quy tắc relaxed binding điển hình là:

~~~text
PAYMENT_GATEWAY_APIKEY
~~~

Quy tắc: dấu chấm thành underscore, bỏ dấu gạch nối, uppercase. Không mặc nhiên đổi `api-key` thành `API_KEY` theo mọi ngữ cảnh.

Ví dụ local **chỉ sử dụng token giả**:

~~~bash
PAYMENT_GATEWAY_APIKEY="FAKE_LOCAL_TOKEN_NOT_FOR_PRODUCTION" \
  java -jar payment.jar
~~~

Trong production, secret nên do công cụ triển khai inject từ một nguồn được quản lý, không dán token thật vào command được lưu shell history.

### 9.1. Ưu điểm

- Không cần thay JAR.
- Tích hợp đơn giản với nhiều nền tảng triển khai.
- Spring Boot Binder có thể chuyển env var thành property phù hợp.
- Cùng image dùng được ở staging và production.

### 9.2. Hạn chế

- Environment process có thể bị xem bởi người/công cụ có quyền tương ứng.
- Container inspection, crash report, debug dump và CI logs có thể làm lộ giá trị.
- Biến môi trường không phải secret manager.
- Thay environment sau khi tiến trình đã chạy thường không làm bean hiện tại tự cập nhật.
- Dữ liệu multiline hoặc nhị phân không thuận tiện cho env vars.

Nếu secret có yêu cầu nghiêm ngặt hơn, cân nhắc mounted file hoặc tích hợp secret manager.

## 10. Cách 2: mounted files và `configtree:`

Spring Boot hỗ trợ **Configuration Trees** qua `spring.config.import` với prefix `configtree:`. Đây là cách phù hợp khi nền tảng runtime cấp secret dưới dạng nhiều file, mỗi file đại diện một key.

Ví dụ volume runtime:

~~~text
/run/secrets/
└── payment.gateway.api-key
~~~

Nội dung file là credential thật do hệ thống triển khai mount; file này **không nằm trong Git hoặc image**.

Một `application-prod.properties` được phép commit có thể chứa:

~~~properties
spring.config.import=configtree:/run/secrets/
~~~

Khi profile `prod` được bật, Boot import configuration tree. Tên file `payment.gateway.api-key` trở thành property tên `payment.gateway.api-key` trong `Environment`, và có thể bind vào `GatewayCredentials.apiKey`.

### 10.1. Cấu trúc folder cũng tham gia tạo tên property

Một cây:

~~~text
/run/secrets/payment/gateway/api-key
~~~

khi import đúng root có thể biểu diễn property `payment.gateway.api-key`. Spring Boot cũng hỗ trợ tên file chứa dấu chấm, ví dụ `payment.gateway.api-key`.

Không suy rằng Kubernetes Secret object tên `payment-gateway` sẽ tự trở thành prefix `payment.gateway`. **Filename và đường dẫn bên trong config tree** mới quyết định key được import.

### 10.2. Dùng hay không dùng `optional:`?

Có thể khai báo:

~~~properties
spring.config.import=optional:configtree:/run/secrets/
~~~

Với `optional:`, nếu location không tồn tại thì quá trình nạp Config Data có thể tiếp tục. Điều này tiện cho nguồn tùy chọn.

Nếu volume secret bắt buộc ở production, nên cân nhắc:

~~~properties
spring.config.import=configtree:/run/secrets/
~~~

để thiếu location gây lỗi sớm. Dù vậy, directory tồn tại không chứng minh **file bắt buộc** đã có; vẫn cần `@NotBlank` hoặc một required-property check.

### 10.3. `configtree:` không phải tính năng mã hóa

`configtree:` chỉ chuyển file/folder thành property. Nó không mã hóa file, tự cấp quyền, hoặc tự bảo đảm volume an toàn. Những vấn đề đó thuộc secret backend và runtime platform.

Người có quyền đọc file mounted vào container có thể truy cập nội dung. Vì vậy cần giới hạn container user, permission, các volume mount và Pod/container thực sự cần secret.

### 10.4. String và byte array

Spring Boot config trees có thể hỗ trợ binding sang `String` hoặc `byte[]` tùy nội dung. Nếu secret là dữ liệu nhị phân, không nên chuyển tùy tiện sang chuỗi UTF-8 rồi in ra để debug.

Nếu một thư viện cần đường dẫn tới private key/keystore, có thể cấp file qua volume và cấu hình một Spring `Resource` hoặc `Path` tới file đó, thay vì đọc toàn bộ nội dung vào một property `String`.

## 11. Ví dụ Kubernetes Secret mount

Một Kubernetes Deployment có thể yêu cầu mount đúng một key trong Secret object dưới tên file phù hợp:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: payment-service
spec:
  replicas: 2
  selector:
    matchLabels:
      app: payment-service
  template:
    metadata:
      labels:
        app: payment-service
    spec:
      containers:
        - name: app
          image: registry.example.test/payments:1.0.0
          volumeMounts:
            - name: payment-secrets
              mountPath: /run/secrets
              readOnly: true
      volumes:
        - name: payment-secrets
          secret:
            secretName: payment-gateway
            items:
              - key: api-key
                path: payment.gateway.api-key
~~~

Giả sử Secret object đã được cấp an toàn với key `api-key`. Kubernetes projection cung cấp file:

~~~text
/run/secrets/payment.gateway.api-key
~~~

Ứng dụng có:

~~~properties
spring.config.import=configtree:/run/secrets/
~~~

và class `@ConfigurationProperties(prefix = "payment.gateway")` để nhận secret.

**Không commit manifest Kubernetes có secret value thật được encode base64** chỉ vì nó không đọc được trực tiếp bằng mắt. Base64 là encoding, không phải encryption.

### 11.1. Kubernetes Secret không tự bảo đảm bí mật tuyệt đối

Cần xem xét:

- RBAC: ai có quyền đọc Secret API.
- Encryption at rest cho dữ liệu lưu trong etcd nếu được yêu cầu.
- Quyền truy cập của Pod/container vào volume.
- Cơ chế audit và lifecycle của Secret.
- Những công cụ nào có thể xem environment, mount hoặc Pod spec.
- Không dùng chung credential production cho workload không liên quan.

Một Secret object và một Config Tree là hai lớp khác nhau: Kubernetes cung cấp dữ liệu vào filesystem; Spring Boot import dữ liệu đó thành property.

### 11.2. Rotation không đồng nghĩa bean tự đổi

Volume-mounted Secret có thể được nền tảng cập nhật theo cơ chế riêng. Nhưng `@ConfigurationProperties` bean thường đã bind tại startup, và HTTP/database client đã tạo từ giá trị cũ không tự được dựng lại.

Đối với rotation, nên có kế hoạch rolling restart/redeploy hoặc reload đã được thiết kế và kiểm thử. Một số cách mount như `subPath` có hành vi cập nhật khác với volume projection thông thường; cần biết giới hạn của platform.

## 12. Ví dụ Docker Compose secrets

Một môi trường Compose hỗ trợ secrets có thể cấp file runtime:

~~~yaml
services:
  payment-service:
    image: registry.example.test/payments:1.0.0
    secrets:
      - source: payment_gateway_api_key
        target: payment.gateway.api-key

secrets:
  payment_gateway_api_key:
    file: ./local-secrets/api-key.txt
~~~

Container nhận file runtime theo cơ chế Compose phù hợp, thông thường tại:

~~~text
/run/secrets/payment.gateway.api-key
~~~

Và Spring Boot import:

~~~properties
spring.config.import=configtree:/run/secrets/
~~~

Trong repo nên có:

~~~gitignore
local-secrets/
~~~

Và trong Docker build context:

~~~dockerignore
local-secrets/
.env
.env.*
*.key
*.p12
~~~

**Đừng commit `./local-secrets/api-key.txt`.** Mẫu Compose này dùng để minh họa. Trong production, secret file/volume cần được quản lý bởi cơ chế triển khai được tổ chức cho phép.

## 13. Phân biệt build secret và runtime secret

Đây là sự khác biệt rất quan trọng.

| Loại | Ai cần? | Thời điểm | Nguồn phù hợp |
| --- | --- | --- | --- |
| Build secret | Maven/Gradle/Docker builder cần xác thực vào registry private | Build | CI secret/build secret mount |
| Runtime secret | Ứng dụng cần gọi API hoặc database | Khi chạy | Secret manager/runtime volume |
| Test credential | Integration test cần service sandbox | Test | CI secret quyền hạn thấp |
| User credential | Người dùng đăng nhập vào ứng dụng | Runtime request/auth | Authentication flow, không phải application config |

Một ứng dụng không nên đưa runtime API token vào build chỉ để có sẵn trong image. Nếu compile không dùng token đó, builder cũng không cần được cấp quyền đọc token.

### 13.1. Build cần token tải dependency private

Docker BuildKit hỗ trợ secret mount tạm thời trong một lệnh build:

~~~dockerfile
# syntax=docker/dockerfile:1
FROM maven:3-eclipse-temurin-21 AS build
WORKDIR /work
COPY pom.xml .
COPY src ./src
RUN --mount=type=secret,id=maven_settings,target=/root/.m2/settings.xml \
    mvn -B -DskipTests package
~~~

File Maven settings được cung cấp thông qua `docker build --secret` theo hướng dẫn Docker, thay vì đưa token vào `ARG`/`ENV`. Cần bảo đảm build command không ghi secret vào artifact hoặc log.

Build secret mount **không tự biến thành runtime secret** trong final image. Nếu ứng dụng cần token ở runtime, cấp lại theo quy trình runtime riêng.

## 14. Vì sao không dùng Docker `ARG` hoặc `ENV` để lưu secret?

Anti-pattern:

~~~dockerfile
ARG API_TOKEN
ENV API_TOKEN=$API_TOKEN
RUN echo "$API_TOKEN" > /tmp/token
~~~

Build arguments và environment variables không phù hợp làm kênh bảo vệ build secrets. Chúng có thể lộ qua image configuration, metadata, history, provenance, cache hoặc log tùy cách build.

Một anti-pattern khác:

~~~dockerfile
COPY secrets/ /app/secrets/
RUN rm -rf /app/secrets/
~~~

Xóa file ở layer sau **không bảo đảm xóa nó khỏi layer trước hoặc cache**. Nếu secret đã được đưa vào build context và copy vào layer, rủi ro vẫn tồn tại.

### 14.1. Image runtime chỉ chứa artifact sạch

Một Dockerfile đơn giản:

~~~dockerfile
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY target/payment.jar /app/payment.jar
USER 10001
ENTRYPOINT ["java", "-jar", "/app/payment.jar"]
~~~

Đây là ví dụ kỹ thuật, cần hardening theo môi trường. Nó không chứa lệnh copy secret.

**Cảnh báo:** nếu `target/payment.jar` đã có password bên trong, Dockerfile này vẫn đưa password vào image. Bảo vệ build context không thay thế kiểm tra JAR đầu vào.

### 14.2. Vai trò của `.dockerignore`

`.dockerignore` giới hạn những file được gửi vào Docker build context theo rule tương ứng. Một file được `.gitignore` bỏ qua vẫn có thể tồn tại trên disk và lọt vào `COPY . .` nếu không được exclude khỏi context.

Nên dùng cả hai:

- `.gitignore` cho Git workflow.
- `.dockerignore` cho Docker build context.

Nhưng cũng cần quét artifact được tạo bên ngoài Docker; hai file ignore không tự bảo đảm build output sạch.

## 15. Maven và Gradle có thể đưa secret vào output

### 15.1. Maven resources

Maven thường copy `src/main/resources` sang `target/classes`, sau đó package vào JAR. Nếu resource chứa secret thật, nội dung đó có thể tồn tại trong artifact.

Một trường hợp khó phát hiện hơn là **resource filtering**: file nguồn chỉ chứa placeholder, nhưng Maven được cấu hình thay placeholder bằng một environment variable có credential thật, khiến `target/classes/application.yml` chứa secret.

Không nên dùng Maven filtering để bake runtime password vào artifact.

### 15.2. Gradle `processResources`

Tương tự, `processResources` có thể copy, filter hoặc expand nội dung từ source resource vào `build/resources/main`.

Nếu build script được cấu hình dùng environment variable để tạo `application-prod.properties` chứa password thật, file output có thể đi vào JAR. Tên file nguồn không chứa secret không có nghĩa artifact cuối không chứa.

### 15.3. Nơi có thể còn bản sao

- `target/classes`, `build/resources/main`.
- JAR/WAR/native image và các artifact khác.
- Docker layers/cache, image metadata/history.
- Generated source và test reports.
- CI logs và build artifacts.
- Artifact registry, image registry, deployment node, backup.
- Crash dump, heap dump, structured logging pipeline.

**Phải kiểm tra artifact thực tế**, không chỉ source repository.

## 16. Kiểm tra JAR và image một cách an toàn

Có thể liệt kê entry của một JAR:

~~~bash
jar tf target/payment.jar
~~~

Ví dụ cần chú ý:

~~~text
BOOT-INF/classes/application-prod.yml
BOOT-INF/classes/private-key.pem
BOOT-INF/classes/config/secrets.properties
~~~

Tên file chỉ là tín hiệu. Một file tên `application.yml` có thể an toàn; một file tên `notes.txt` có thể chứa token. Không nên chạy script in nguyên toàn bộ file cấu hình ra CI log để tìm secret.

Quy trình kiểm tra:

1. Liệt kê entry đáng ngờ.
2. Quét nội dung artifact bằng secret scanner có cơ chế redaction.
3. Dùng fake canary trong môi trường test để kiểm tra đường copy.
4. Kiểm tra build output trước khi package.
5. Kiểm tra image configuration và các layer theo policy.
6. Không upload bản extract chứa credential lên dịch vụ không đáng tin cậy.
7. Không xuất raw findings có secret ra logs hoặc ticket.

### 16.1. Scan source chưa đủ

Nếu token được chèn ở bước build từ environment, secret scanner chỉ chạy trên Git tree có thể không phát hiện. Cần scan `target/classes`, JAR/image hoặc đầu ra tương đương trước khi phát hành.

### 16.2. Scan image cần hiểu layer

Một image có thể không có `ENV TOKEN=...` nhưng vẫn chứa secret trong file/JAR hoặc layer build. Ngược lại, container đang chạy không có file đó ở filesystem cuối chưa chứng minh các layer cũ và cache an toàn.

## 17. Phân quyền trong CI/CD

Quy trình nên tách nhiệm vụ:

~~~text
Source + PR
   |
Secret scanning và code review
   |
Compile/test với fake values
   |
Package + artifact scan
   |
Build image từ artifact sạch
   |
Image scan + publish
   |
Deploy: inject runtime secret
   |
Health check và safe observability
~~~

Các nguyên tắc:

- Job build không được cấp production runtime secret nếu không cần.
- Job deploy chỉ có quyền ở môi trường đích.
- Có thể dùng OIDC/workload identity và token ngắn hạn khi hạ tầng hỗ trợ.
- Phân biệt credential staging và production.
- Không cấp secret production cho pull request chạy code chưa được tin cậy.
- Dùng CI logs masking nhưng không coi masking là lớp bảo vệ duy nhất.
- Hạn chế các câu lệnh như `env`, `printenv` hoặc `set -x` trong job có secret.

Nếu pipeline tải dependency private, cấp build credential riêng với quyền chỉ đọc phạm vi repository cần thiết. Không dùng chính token thanh toán production cho nhiệm vụ build.

## 18. Secret scanning và pull request

Một chiến lược tốt có nhiều lớp:

1. Pre-commit hook kiểm tra staged changes.
2. Secret scanning trên pull request và branch.
3. Server-side push protection nếu nền tảng hỗ trợ.
4. Scan Git history theo policy.
5. Scan build artifacts và image.
6. Quy trình review false positive không chứa raw secret.
7. Quy trình xử lý nhanh credential bị phát hiện.

Các công cụ như Gitleaks, git-secrets hoặc tính năng secret scanning của Git hosting có thể hỗ trợ. Không có công cụ nào phát hiện mọi secret; token nội bộ có format không phổ biến có thể lọt qua.

Không đặt nguyên secret vào file allowlist của scanner chỉ để vô hiệu hóa cảnh báo. Một exception/suppression nên dùng định danh không nhạy cảm và có lý do.

## 19. Nếu secret đã bị commit: xử lý đúng thứ tự

Giả sử token thật từng được push cùng `application-prod.yml`.

**Đầu tiên:** đánh giá secret như credential có thể đã bị lộ, rồi xử lý quyền truy cập.

Các bước thực tế:

1. **Ngăn phát tán thêm:** không dán token vào chat, issue, ticket hoặc log.
2. **Revoke/rotate:** hủy credential cũ hoặc cấp credential mới theo kế hoạch chuyển đổi.
3. **Xác định phạm vi:** branch, commit, PR, fork, clone, CI logs, artifact, image, backup.
4. **Kiểm tra audit logs:** xác định hoạt động bất thường bằng cơ chế của hệ thống cấp quyền.
5. **Di chuyển secret mới ra nguồn runtime phù hợp:** không tiếp tục hardcode.
6. **Build và triển khai bản sạch:** không để secret thật đi vào JAR/image mới.
7. **Xem xét cleanup/rewrite Git history:** cần phối hợp với cộng tác viên, có thể dùng công cụ phù hợp khi thật sự cần.
8. **Ngăn tái diễn:** scanner, PR checks, artifact checks, least privilege và runbook.

### 19.1. Vì sao rotate quan trọng hơn chỉ xóa history?

Một người có clone/fork hoặc bản cache có thể vẫn giữ giá trị cũ. Rewrite history không thể bảo đảm xóa mọi bản sao. Khi secret đã bị revoke, bản sao cũ không còn mang cùng quyền truy cập.

### 19.2. Không tự ý rewrite shared history

Các công cụ như `git-filter-repo` có thể loại dữ liệu khỏi commit history, nhưng làm thay đổi commit IDs, ảnh hưởng branch, tag, PR và các clone khác. Việc thực hiện cần được phối hợp trong nhóm và tuân thủ chính sách quản trị repo.

### 19.3. Artifact cũ vẫn là bản sao

Nếu JAR/image cũ từng chứa token, không được coi token an toàn chỉ vì image mới đã sạch. Cần thu hồi credential và xử lý bản sao trong registry/cache theo chính sách.

## 20. Secret manager và Spring Boot integration

Secret manager giúp quản lý:

- danh tính workload và quyền đọc;
- phiên bản secret và rotation;
- audit access;
- credential ngắn hạn;
- cấp secret theo môi trường và service;
- lưu trữ có kiểm soát thay vì đưa vào Git.

Ví dụ hệ sinh thái: HashiCorp Vault, AWS Secrets Manager, Azure Key Vault, Google Cloud Secret Manager hoặc dịch vụ quản lý bí mật khác.

**Spring Boot core không tự tích hợp mọi secret manager**. Một số nguồn cần thư viện/starter hoặc Config Data integration phù hợp. Chẳng hạn Spring Cloud Vault có chức năng hỗ trợ externalized configuration từ HashiCorp Vault.

Không tự giả định `spring.config.import=vault://` hoạt động chỉ vì dùng Spring Boot cơ bản. Cần đúng dependency và cơ chế resolver tương ứng.

### 20.1. Runtime identity

Một thiết kế có thể là:

~~~text
Kubernetes Service Account / Cloud Workload Identity
                       |
                       v
                 Authenticate
                       |
                       v
                   Secret manager
                       |
                       v
            Chỉ secret được cấp quyền
                       |
                       v
               Spring Environment
                       |
                       v
                 Application bean
~~~

Không nên hardcode một “master token” lâu dài trong artifact chỉ để lấy token khác. Khả năng dùng identity và credential tạm thời tùy nền tảng.

### 20.2. Secret manager không tự sửa lỗi code

Nếu ứng dụng vẫn log `credentials.getApiKey()`, secret vẫn bị lộ. Lưu trữ bảo mật không thay thế safe logging, validation và quyền hạn ở consumer.

## 21. Config Data và thứ tự ưu tiên

Spring Boot có nhiều nguồn property. Một key có thể xuất hiện từ classpath Config Data, external Config Data, environment, system properties hoặc command line. Binder chọn giá trị hiệu lực theo precedence.

Ví dụ:

~~~properties
# application-prod.properties
spring.config.import=configtree:/run/secrets/
payment.gateway.endpoint=https://gateway.example.test/v1
~~~

Nếu runtime mount cung cấp `payment.gateway.api-key`, Binder có thể đọc key đó. Tuy nhiên, **một nguồn ưu tiên cao hơn** vẫn có thể ghi đè property trong một số cấu hình.

Khi debug, hãy kiểm tra:

1. Prefix Java `@ConfigurationProperties`.
2. Key sinh ra từ file config tree.
3. Profile đang active.
4. Location có thực sự được import.
5. Source nào đang thắng.
6. Validation và conversion.

Đừng dump mọi `PropertySource` cùng raw values chỉ để tìm key. Nên sử dụng metadata và tên key cho phép.

### 21.1. `spring.config.location` khác `spring.config.import`

- `spring.config.location`: điều chỉnh location tìm Config Data, thường thay thế default locations.
- `spring.config.additional-location`: thêm location ngoài mặc định.
- `spring.config.import`: import dữ liệu bổ sung từ location phù hợp, bao gồm `configtree:`.

Nếu runtime cung cấp **một file properties/YAML đầy đủ**, có thể import file qua `file:`. Nếu runtime cung cấp **nhiều file mỗi file một key**, dùng `configtree:` là hướng thích hợp.

## 22. Logging, Actuator và quan sát an toàn

Bí mật tách khỏi JAR vẫn có thể bị lộ trong runtime diagnostics:

- `Throwable.getMessage()` và raw stack traces;
- `record.toString()` hoặc Lombok `@ToString`;
- Actuator `/actuator/env` và `/actuator/configprops`;
- HTTP request/response logging;
- tracing span attributes và baggage;
- metrics labels;
- support tickets và crash dumps.

Ví dụ không nên:

~~~java
log.error("Invalid settings: {}", credentials);
log.error("Rejected API key: {}", credentials.getApiKey());
~~~

Thay bằng:

~~~text
[CFG-SECRET-001] Required credential is missing.
property=payment.gateway.api-key
source-kind=runtime-secret
action=verify secret mount and access policy
~~~

**Không** in raw rejected value hoặc nội dung secret file. Tên key có thể hiển thị cho operator tin cậy nếu đó là định danh tĩnh đã được cho phép.

### 22.1. Actuator sanitization

Actuator có những cơ chế kiểm soát việc hiển thị giá trị cấu hình và endpoint exposure tùy phiên bản. Không mặc định rằng mọi custom key đều sẽ được che trong mọi trường hợp.

Bảo vệ endpoint, giới hạn quyền truy cập, kiểm thử bằng secret giả và không tắt sanitization để thuận tiện debug production.

### 22.2. String trong heap

Một secret dạng `String` có thể nằm trong heap của JVM và có nhiều bản sao. Việc chuyển sang `char[]` hoặc `byte[]` trong một vài API giúp kiểm soát dữ liệu ở một số ranh giới, nhưng không đảm bảo mọi bản sao đã bị xóa khỏi memory.

Bảo vệ heap/core dumps và hạn chế các công cụ debug có quyền đọc process memory vẫn là cần thiết.

## 23. Rotation và khả năng thu hồi

Một vòng đời credential có thể gồm:

~~~text
Provision -> Distribute -> Use -> Monitor -> Rotate -> Revoke -> Retire
~~~

Cần quyết định:

- Ai sở hữu credential và quyền rotation?
- Secret có thời hạn bao lâu?
- Có cơ chế audit và cảnh báo hết hạn không?
- Có thể cấp mới mà không build lại JAR không?
- Client đang dùng secret cũ được tái tạo thế nào?
- Có khoảng chuyển tiếp chấp nhận cả old/new credential không?
- Khi incident, ai có quyền revoke ngay?

### 23.1. Đổi file không có nghĩa tự rebind

`@ConfigurationProperties` thường được bind khi application context khởi động. Thay file mounted secret không làm JavaBean, HTTP client, datasource hoặc message broker client tự nhận giá trị mới.

Một quy trình rotation đơn giản:

1. Cấp secret mới ở nguồn runtime.
2. Đảm bảo hệ thống đích có thể chấp nhận secret mới.
3. Rolling restart/redeploy ứng dụng.
4. Xác nhận health và giao dịch.
5. Revoke secret cũ.

Nếu yêu cầu hot rotation không restart, cần cơ chế reload, đồng bộ và tái tạo client có kiểm thử riêng. Không chỉ dựa vào việc volume đã cập nhật.

## 24. Test canary để phát hiện đường lộ

Sử dụng **giá trị giả**, không phải secret thật:

~~~text
FAKE_CANARY_SECRET_DO_NOT_SHIP_2026
~~~

Trong môi trường test có kiểm soát, cấp chuỗi canary qua nguồn runtime rồi kiểm tra:

- Binding vào `@ConfigurationProperties` hoạt động.
- Canary không xuất hiện trong JAR/image.
- Canary không có trong stdout/stderr hoặc startup logs.
- Canary không xuất hiện ở Actuator/public API.
- Canary không có trong pipeline artifacts ngoài ý định.

Canary giúp kiểm tra một đường đi, nhưng không thay thế secret scanning và policy.

### 24.1. Test thiếu credential

Không cung cấp `payment.gateway.api-key`, kỳ vọng validation hoặc startup checks thất bại với thông báo an toàn. Tách environment test để không tự nhận secret thật từ máy developer.

### 24.2. Test mounted file

Tạo một thư mục tạm có file `payment.gateway.api-key` với nội dung giả, import nó bằng `configtree:` và kiểm tra Binder nhận đúng property. Sau test dọn dữ liệu tạm. Không đưa folder test đó vào build artifact production.

### 24.3. Test output cuối

Ngoài quét Git, kiểm tra `target/classes`/`build/resources/main`, JAR và image. Nếu build plugin đã expand secret từ CI environment vào output, scanner chỉ quét working tree có thể bỏ sót.

## 25. Một mẫu dự án Spring Boot tối thiểu

~~~text
payment-app/
├── src/main/java/com/example/payment/
│   ├── PaymentApplication.java
│   ├── config/GatewayCredentials.java
│   └── service/PaymentGatewayClient.java
├── src/main/resources/
│   ├── application.yml
│   └── application-prod.properties
├── .gitignore
├── .dockerignore
└── Dockerfile
~~~

**`application.yml` — không có secret:**

~~~yaml
spring:
  application:
    name: payment-service

payment:
  gateway:
    endpoint: "https://gateway.example.test/v1"
    timeout: 3s
~~~

**`application-prod.properties` — import location, không có value:**

~~~properties
spring.config.import=configtree:/run/secrets/
~~~

**Secret được mount khi chạy:**

~~~text
/run/secrets/payment.gateway.api-key
~~~

**Lớp cấu hình:**

~~~java
package com.example.payment.config;

import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "payment.gateway")
public class GatewayCredentials {
    @NotBlank
    private String apiKey;

    public String getApiKey() { return apiKey; }
    public void setApiKey(String apiKey) { this.apiKey = apiKey; }

    @Override
    public String toString() {
        return "GatewayCredentials{apiKey=<redacted>}";
    }
}
~~~

**Đăng ký:**

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan
public class PaymentApplication {
}
~~~

Khi profile `prod` active và runtime secret volume đã có, Spring Boot import file và Binder liên kết property với JavaBean. Đây là cơ chế cấp cấu hình, không tự gọi API payment gateway hoặc kiểm chứng token còn hiệu lực.

Điều kiện để hoạt động:

1. Dependency Spring Boot và Validation phù hợp.
2. Bean `GatewayCredentials` được đăng ký.
3. Profile production nạp `spring.config.import`.
4. Mount path và filename khớp tên property.
5. File có quyền đọc và nội dung hợp lệ.
6. Không có nguồn ưu tiên cao hơn ghi đè key ngoài ý định.
7. Artifact đã được kiểm tra không chứa secret.

## 26. Những lỗi thường gặp

### 26.1. Xóa password khỏi file rồi nghĩ Git đã sạch

Commit cũ vẫn giữ nội dung; credential có thể đã bị sao chép. Cần rotate/revoke theo quy trình, không chỉ commit một bản sạch.

### 26.2. Thêm `.gitignore` sau khi commit

`.gitignore` không tự untrack file đã được Git quản lý. Phải kiểm tra index và xử lý có chủ đích.

### 26.3. Đặt secret trong `application-prod.yml` vì “chỉ production đọc”

File vẫn có thể nằm trong JAR dù không active profile. Profile là cơ chế chọn cấu hình, không phải cơ chế bảo mật.

### 26.4. Dùng build filtering đưa runtime password vào resource

Maven/Gradle có thể biến một placeholder trong source thành secret thật trong output. Cần kiểm tra artifact sau build.

### 26.5. Dùng Docker `ARG`/`ENV` để truyền secret lúc build

Build variables có thể lộ qua metadata/history/cache, không phù hợp làm kênh secret. Dùng build secret mount nếu build thật sự cần.

### 26.6. Có `.gitignore` nhưng không có `.dockerignore`

Một file local không được Git track vẫn có thể bị gửi tới Docker build context.

### 26.7. Config tree file có tên không khớp prefix

File `/run/secrets/api-key` không tự trở thành `payment.gateway.api-key`. Kiểm tra root, folder và filename.

### 26.8. Dùng `optional:` cho secret bắt buộc mà không validate

Có thể khiến ứng dụng đi tiếp mà thiếu credential. Khi bắt buộc, fail fast với thông báo không lộ giá trị.

### 26.9. Commit Kubernetes Secret data dạng base64

Base64 không phải encryption. Không commit Secret value thật dưới dạng đã encode.

### 26.10. Đổi Secret volume rồi mong JavaBean tự nhận

Binding thông thường không tự refresh bean và các client. Cần restart hoặc cơ chế reload đã kiểm thử.

### 26.11. Log object config chứa secret

`toString()`, exception cause và serialization có thể lộ nội dung. Không dùng raw value trong diagnostics.

### 26.12. Chỉ scan source mà không scan artifact

Secret có thể được thêm vào lúc build. Kiểm tra JAR/image và log pipeline.

### 26.13. Dùng credential production trong CI PR job

Code chưa được tin cậy có thể truy cập secret. Dùng fake/test credential với quyền hạn thấp và phân tách môi trường.

## 27. Checklist trước khi phát hành

- [ ] Không có credential thật trong source code hoặc Git commit mới.
- [ ] Secret từng lộ trong Git history đã được xử lý sự cố.
- [ ] `.gitignore` chặn file local chưa track; không phụ thuộc vào ignore như giải pháp duy nhất.
- [ ] `src/main/resources` không có private key, password hoặc token thật.
- [ ] File profile-specific chỉ chứa metadata không bí mật.
- [ ] Maven/Gradle không inject runtime secret vào generated resources.
- [ ] JAR, image và build cache được xử lý theo policy.
- [ ] `.dockerignore` loại file nhạy cảm khỏi Docker build context.
- [ ] Build secret và runtime secret có nguồn, quyền và lifecycle khác nhau.
- [ ] CI job không được cấp credential production ngoài nhu cầu.
- [ ] Secret runtime được cấp qua nguồn được tổ chức phê duyệt.
- [ ] `configtree:` root và filename khớp prefix Java.
- [ ] Thiếu credential bắt buộc dẫn đến lỗi an toàn.
- [ ] Không có secret trong log, Actuator, metric, tracing hoặc public API.
- [ ] Có kế hoạch rotation và revoke.
- [ ] Có secret scanner cho source, history, artifact và image.
- [ ] Test canary không xuất hiện trong artifact/log.
- [ ] Cùng một bản JAR/image có thể deploy nhiều môi trường với credentials riêng.

## 28. Kết luận

**Tách bí mật khỏi Git, classpath và bản dựng** không chỉ là chuyển một dòng mật khẩu sang file khác. Đây là quyết định kiến trúc về **nơi lưu trữ, ai được truy cập, thời điểm cấp, cách kiểm chứng và vòng đời của credential**.

Spring Boot cung cấp `Environment`, Config Data, `@ConfigurationProperties`, placeholder và `configtree:` để ứng dụng nhận cấu hình từ runtime. Các cơ chế đó giúp xây một JAR/image **không chứa giá trị bí mật thật**, còn môi trường triển khai có thể cung cấp secret độc lập.

Để bảo vệ end-to-end:

1. Không commit secret hoặc lưu secret thật trong `src/main/resources`.
2. Không bake secret vào JAR/image/build layer/generated resource.
3. Sử dụng runtime secret source với quyền hạn tối thiểu.
4. Không nhầm `.gitignore`, base64 hoặc `configtree:` với hệ thống mã hóa.
5. Validate các secret bắt buộc và không in raw values trong lỗi/log.
6. Thiết kế rotation/revoke độc lập với vòng đời artifact.
7. Nếu credential đã lộ, **thu hồi/thay thế trước**, sau đó xử lý Git history và các bản sao artifact theo quy trình.

### Tài liệu tham khảo

- [Spring Boot Reference — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Boot Reference — Configuration Trees](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.files.importing-configuration-trees)
- [Spring Boot Reference — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties)
- [Docker Docs — Build Secrets](https://docs.docker.com/build/building/secrets/)
- [Docker Docs — Build Variables](https://docs.docker.com/build/building/variables/)
- [Kubernetes Docs — Secrets](https://kubernetes.io/docs/concepts/configuration/secret/)
- [GitHub Docs — Removing Sensitive Data from a Repository](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository)
- [GitHub Docs — Secret Scanning](https://docs.github.com/en/code-security/secret-scanning/introduction/about-secret-scanning)

# Truyền cấu hình vào Docker và phân biệt biến Compose với biến trong container

## 1. Bài toán và điều dễ nhầm

Một ứng dụng Spring Boot có thể chạy local bằng `java -jar` rồi được đóng gói thành Docker image và triển khai với Docker Compose mà không sửa mã. Cấu hình như cổng HTTP, profile, URL dịch vụ, timeout, database URL và credentials có thể đến từ môi trường triển khai. Tuy nhiên, trong Docker Compose có **hai ngữ cảnh biến khác nhau**:

- **Biến dùng bởi Docker Compose CLI khi dựng cấu hình dịch vụ**, ví dụ `HOST_HTTP_PORT` hoặc `IMAGE_TAG` trong file `.env`, được thay vào biểu thức `${HOST_HTTP_PORT:-18080}`.
- **Biến môi trường thực sự của container**, ví dụ `SPRING_PROFILES_ACTIVE`, `SERVER_PORT`, `APP_CLIENT_TIMEOUT`. Những biến này phải được khai báo qua `services.api.environment`, `services.api.env_file`, image `ENV` hoặc cơ chế runtime tương ứng.

**Một biến chỉ được khai báo trong file `.env` phục vụ Compose interpolation không tự động xuất hiện trong môi trường của container.** Ngược lại, biến đã xuất hiện trong container cũng chưa chắc là giá trị cuối Spring Boot sử dụng, vì Spring có các PropertySource và quy tắc precedence riêng.

Bài này xây ví dụ đầy đủ từ `.env`, `compose.yaml` đến `@ConfigurationProperties`, giải thích `--env-file` khác `env_file`, cách đặt tên biến Spring Boot, container networking, host port, Spring profiles, secret mounts, precedence, chẩn đoán lỗi và tình huống thực hành. Các ví dụ dựa trên Docker Compose v2 và Spring Boot 3.x. Cấu hình cụ thể của Docker/Compose có thể có khác biệt theo phiên bản được cài.

## 2. Ba tầng xử lý cần phân biệt

~~~text
Máy chạy lệnh docker compose
   |
   | Biến shell, file .env, --env-file
   v
Docker Compose CLI
   | Nội suy biểu thức trong compose.yaml
   | Tính image, ports, volumes, giá trị environment
   v
Docker Engine / container runtime
   | Dockerfile ENV + services.env_file + services.environment
   v
Process java -jar app.jar
   | System.getenv(...)
   | Spring Boot Environment
   | Config Data, JVM -D, command-line arguments
   v
Spring Boot Binder / @ConfigurationProperties
   |
   v
Bean cấu hình có kiểu Java
~~~

Tầng thứ nhất: **Compose nội suy từ file/host**. Tầng thứ hai: **Docker cấp environment cho container**. Tầng thứ ba: **Spring Boot chọn property cuối cùng rồi bind**.

Không dùng một bảng ưu tiên để giải thích cả ba. Ví dụ shell variable có thể thắng `.env` khi Compose nội suy; `environment` thường thắng `env_file` của service; còn trong Spring Boot, command-line property thường thắng OS environment và các file Config Data thông thường.

## 3. Bốn tên gần giống nhau nhưng chức năng khác nhau

| Khái niệm | Ai đọc? | Dùng vào việc gì? | Tự cấp vào container? |
| --- | --- | --- | --- |
| `.env` ở ngữ cảnh Compose | Compose CLI | Giá trị cho nội suy `${VAR}` | Không |
| `docker compose --env-file path` | Compose CLI | Chỉ định file biến dùng nội suy | Không |
| `services.api.env_file` | Compose khi tạo container | Nạp key/value thành container environment | Có |
| `services.api.environment` | Compose khi tạo container | Đặt environment cụ thể | Có |
| `ENV` trong Dockerfile | Docker image/runtime | Đặt giá trị mặc định trong image | Có, trừ khi runtime ghi đè |
| `docker run --env-file` | Docker run | Trực tiếp đưa biến từ file vào container | Có |
| `docker compose run -e` | Compose run | Override env của one-off service container | Có, cho lần run ấy |

**Lưu ý nhất:** `docker compose --env-file` và `services.api.env_file` **không tương đương**, dù tên gần giống hệt nhau. Lệnh CLI dùng file để tính mô hình Compose; service property đưa file vars vào container.

## 4. Ví dụ cấu trúc dự án

Giả sử repository:

~~~text
order-service/
  compose.yaml
  .env
  env/
    runtime.env
  Dockerfile
  pom.xml
  src/main/java/com/example/orders/
    OrderApplication.java
    config/ClientProperties.java
    service/RemoteClient.java
  src/main/resources/
    application.yml
    application-dev.yml
    application-prod.yml
~~~

Mục đích của hai file:

- `.env`: chỉ cấu hình cho Compose interpolation, không chứa secret thật.
- `env/runtime.env`: giá trị muốn đưa vào container qua `env_file`.

Với production, không commit file nào chứa credential thật chỉ vì tên file là `runtime.env` hay `.env`. Dùng secret manager hoặc mount file được phân quyền.

## 5. File .env được Compose dùng để nội suy

~~~dotenv
# .env
HOST_HTTP_PORT=18080
IMAGE_TAG=local
APP_PROFILE=dev
CLIENT_TIMEOUT=5s
COMPOSE_ONLY_NOTE=this-value-is-not-injected
~~~

Trong `compose.yaml`:

~~~yaml
services:
  api:
    image: "example/order-service:${IMAGE_TAG:-local}"
    ports:
      - "${HOST_HTTP_PORT:-18080}:8080"
~~~

Compose dùng `IMAGE_TAG` để tạo tên image và `HOST_HTTP_PORT` để tạo host port mapping. Nhưng không có khai báo `environment` hay `env_file` cho `HOST_HTTP_PORT`, nên **không được phép kết luận container có biến `HOST_HTTP_PORT`**.

`COMPOSE_ONLY_NOTE` thậm chí không được tham chiếu nên cũng không tự xuất hiện trong container. File `.env` không phải một “bản sao nguyên environment của container”.

## 6. File env/runtime.env được nạp vào container

~~~dotenv
# env/runtime.env
APP_CLIENT_BASEURL=https://api.example.test
APP_FEATURE_ENABLED=true
LOGGING_LEVEL_COM_EXAMPLE_ORDERS=INFO
~~~

Compose:

~~~yaml
services:
  api:
    env_file:
      - ./env/runtime.env
~~~

Giờ container của service `api` nhận các key từ file theo quy tắc Compose. Spring Boot có thể thấy `APP_CLIENT_BASEURL` và `APP_FEATURE_ENABLED` qua OS environment của process.

Đừng nhầm lẫn: việc có file `runtime.env` trên disk không đủ. **Phải tham chiếu nó dưới service bằng `env_file`** hoặc cấp biến qua cách khác.

## 7. compose.yaml mẫu kết hợp cả hai nguồn

~~~yaml
services:
  api:
    image: "example/order-service:${IMAGE_TAG:-local}"
    build:
      context: .
    ports:
      - "${HOST_HTTP_PORT:-18080}:8080"
    env_file:
      - ./env/runtime.env
    environment:
      SERVER_PORT: "8080"
      SPRING_PROFILES_ACTIVE: "${APP_PROFILE:-dev}"
      APP_CLIENT_TIMEOUT: "${CLIENT_TIMEOUT:-3s}"
~~~

Điều thực sự xảy ra với `.env` ở phần trước:

- Compose tính image tag = `local`.
- Compose xuất bản host port `18080` tới container port `8080`.
- Compose lấy `APP_PROFILE=dev` và truyền biến **container** tên `SPRING_PROFILES_ACTIVE=dev`.
- Compose lấy `CLIENT_TIMEOUT=5s` và truyền biến **container** tên `APP_CLIENT_TIMEOUT=5s`.
- `SERVER_PORT=8080` vào container từ `environment`.
- `APP_CLIENT_BASEURL` và `APP_FEATURE_ENABLED` vào container từ `env_file`.
- `COMPOSE_ONLY_NOTE` không tự được đưa vào container.

Image name `example/order-service:local` là minh họa cho image bạn build; không khẳng định một public registry có sẵn image này.

## 8. Dockerfile tối thiểu để chạy Java

Giả sử dự án đã build executable Spring Boot JAR và artifact có tên `order-service.jar`:

~~~dockerfile
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY target/order-service.jar /app/app.jar
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Lệnh cho môi trường dev:

~~~bash
./mvnw -DskipTests package
docker compose up -d --build
~~~

Để ví dụ chạy thực tế, `COPY` phải khớp tên JAR Maven tạo ra (có thể cấu hình tên artifact hoặc chỉnh Dockerfile). `EXPOSE 8080` là metadata của image, **không tự publish cổng ra host**; `ports` trong Compose mới tạo host mapping.

Đừng hardcode password/API key bằng Dockerfile `ARG`, `ENV` hoặc `COPY` vào image. Build layer, registry hoặc lịch sử image có thể lưu credential.

## 9. Spring Boot dùng environment container như thế nào?

File `application.yml`:

~~~yaml
spring:
  application:
    name: order-service

server:
  port: 8080

app:
  client:
    base-url: https://fallback.example.test
    timeout: 2s
  feature:
    enabled: false
~~~

Record Java:

~~~java
package com.example.orders.config;

import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
    URI baseUrl,
    Duration timeout
) {}
~~~

Main class:

~~~java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class OrderApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
~~~

Khi Docker đã cấp:

~~~text
SPRING_PROFILES_ACTIVE=dev
SERVER_PORT=8080
APP_CLIENT_TIMEOUT=5s
APP_CLIENT_BASEURL=https://api.example.test
APP_FEATURE_ENABLED=true
~~~

Spring Boot có thể bind `ClientProperties` thành:

~~~text
baseUrl: https://api.example.test
timeout: Duration.ofSeconds(5)
~~~

Giá trị từ OS environment thường ghi đè các giá trị trong `application.yml` thông thường. **Compose cấp biến; Spring Boot Binder chuyển chuỗi sang `URI`, `Duration` và các kiểu Java.**

## 10. Cú pháp Compose interpolation

| Cú pháp | Ý nghĩa |
| --- | --- |
| `${VAR}` | Lấy value nếu có; khi thiếu có thể thay rỗng và cảnh báo |
| `${VAR:-fallback}` | Dùng fallback nếu biến không được đặt **hoặc** rỗng |
| `${VAR-fallback}` | Dùng fallback nếu biến không được đặt; rỗng vẫn là giá trị |
| `${VAR:?message}` | Báo lỗi nếu biến thiếu hoặc rỗng |
| `${VAR?message}` | Báo lỗi nếu biến chưa được đặt |
| `$$` | Escape để giữ dấu dollar literal trong ngữ cảnh Compose |

Ví dụ:

~~~yaml
services:
  api:
    ports:
      - "${HOST_HTTP_PORT:-18080}:8080"
    environment:
      APP_REGION: "${APP_REGION:-ap-southeast-1}"
      DEPLOY_ENV: "${DEPLOY_ENV:?Set DEPLOY_ENV}"
~~~

Đây là cú pháp do **Compose** giải quyết trước khi container được tạo. `DEPLOY_ENV` thiếu có thể làm Compose dừng với thông báo thay vì chạy một container cấu hình thiếu.

Các giá trị môi trường cuối cùng là **chuỗi**; Spring Boot mới chuyển chuỗi `"false"` thành boolean hoặc `"2s"` thành Duration.

## 11. .env mặc định và biến shell

Giả sử file `.env` ghi:

~~~dotenv
CLIENT_TIMEOUT=5s
~~~

nhưng ở shell chạy Compose có:

~~~bash
export CLIENT_TIMEOUT=10s
docker compose up -d
~~~

Compose thường dùng giá trị shell cho nội suy biểu thức `${CLIENT_TIMEOUT}` thay vì value trong `.env`. Quy tắc tìm file và ưu tiên chi tiết còn phụ thuộc working directory, project directory và `--env-file`; với deployment phức tạp, cần chạy từ một ngữ cảnh rõ ràng và kiểm kết quả một cách an toàn.

Nếu `compose.yaml` không tham chiếu `CLIENT_TIMEOUT` ở `environment`, giá trị của biến shell hay `.env` đều **không tự đi vào container**.

## 12. docker compose --env-file chỉ thay nguồn interpolation

~~~bash
docker compose --env-file ./deploy/prod.compose.env up -d
~~~

Với file:

~~~dotenv
# deploy/prod.compose.env
APP_PROFILE=prod
HOST_HTTP_PORT=18081
~~~

Và Compose:

~~~yaml
services:
  api:
    ports:
      - "${HOST_HTTP_PORT}:8080"
    environment:
      SPRING_PROFILES_ACTIVE: "${APP_PROFILE}"
~~~

Container nhận `SPRING_PROFILES_ACTIVE=prod` vì khai báo `environment`, **không tự nhận `APP_PROFILE` và `HOST_HTTP_PORT`**.

Cũng có cú pháp `docker compose --env-file path -f compose.yaml up -d` trong cùng một lệnh; điều quan trọng là `--env-file` ở mức CLI và được xử lý cho nội suy.

### Không nhầm với docker run --env-file

~~~bash
docker run --env-file ./env/runtime.env example/order-service:local
~~~

`docker run --env-file` thực sự cấp các key từ file vào environment của container. Cùng tên tùy chọn nhưng **không cùng ý nghĩa** với `docker compose --env-file`.

## 13. environment và env_file có thể bổ sung hoặc ghi đè nhau

Giả sử:

~~~dotenv
# env/runtime.env
APP_CLIENT_TIMEOUT=5s
APP_FEATURE_ENABLED=false
~~~

Và:

~~~yaml
services:
  api:
    env_file:
      - ./env/runtime.env
    environment:
      APP_CLIENT_TIMEOUT: "2s"
~~~

Container nhận `APP_CLIENT_TIMEOUT=2s` và `APP_FEATURE_ENABLED=false` trong trường hợp thông thường: khai báo `environment` ưu tiên hơn giá trị cùng key từ `env_file`.

Nếu có nhiều env files:

~~~yaml
services:
  api:
    env_file:
      - ./env/common.env
      - ./env/staging.env
~~~

các giá trị trùng key ở file sau thường ghi đè file trước theo Compose. Đây là thứ tự **giữa các file container env**, không phải thứ tự giữa `.env` và shell variables khi CLI interpolation.

### Key không có value

~~~yaml
environment:
  - DEBUG
~~~

khác với:

~~~yaml
environment:
  - DEBUG=
~~~

Khai báo thứ nhất yêu cầu Compose giải quyết giá trị theo môi trường có sẵn; nếu không giải quyết được, nó có thể bị bỏ khỏi environment. Khai báo thứ hai biểu diễn value rỗng rõ ràng. Mặc định dùng cú pháp mapping với giá trị cụ thể hoặc nội suy có kiểm tra để tránh ambiguity.

## 14. Ba tầng precedence, ba câu hỏi

| Tầng | Cần xác định | Điều nên nhớ |
| --- | --- | --- |
| Compose interpolation | Shell, `.env`, `--env-file` | Biến nào được dùng để dựng Compose model? |
| Container runtime | `environment`, `env_file`, image `ENV`, override run | Container thực sự có key nào và value gì? |
| Spring Boot | OS env, JVM system props, CLI args, Config Data, các PropertySource khác | Property hiệu lực cuối cùng để bind là gì? |

Một câu dễ hiểu: **`.env` không phải một Spring PropertySource** chỉ vì nằm cạnh `compose.yaml`. Khi Compose chuyển một value thành container environment, Spring mới có thể nhìn thấy nó như một OS environment property.

Nếu Spring Boot nhận giá trị khác dự kiến, hãy kiểm container env, nhưng cũng kiểm `--app.client.timeout=...` hoặc `-Dapp.client.timeout=...` có đang ghi đè.

## 15. Tên biến môi trường Spring Boot và relaxed binding

Spring Boot hỗ trợ relaxed binding với `@ConfigurationProperties`. Cách chuyển canonical property name sang tên env phổ biến:

1. Dấu chấm `.` thành `_`.
2. Dấu gạch nối `-` trong segment bị bỏ.
3. Chuyển thành chữ hoa.
4. List index được biểu diễn bằng số và dấu gạch dưới thích hợp.

| Spring Boot property | Environment variable |
| --- | --- |
| `server.port` | `SERVER_PORT` |
| `spring.profiles.active` | `SPRING_PROFILES_ACTIVE` |
| `app.client.timeout` | `APP_CLIENT_TIMEOUT` |
| `app.client.base-url` | `APP_CLIENT_BASEURL` |
| `app.feature.enabled` | `APP_FEATURE_ENABLED` |
| `spring.datasource.url` | `SPRING_DATASOURCE_URL` |
| `spring.datasource.username` | `SPRING_DATASOURCE_USERNAME` |
| `spring.datasource.password` | `SPRING_DATASOURCE_PASSWORD` |
| `app.worker.max-retries` | `APP_WORKER_MAXRETRIES` |
| `app.pipelines[0].name` | `APP_PIPELINES_0_NAME` |
| `app.pipelines[0].retry.backoff` | `APP_PIPELINES_0_RETRY_BACKOFF` |

Chú ý ví dụ `app.client.base-url`: dạng canonical môi trường là `APP_CLIENT_BASEURL`, **không tự giả định** `APP_CLIENT_BASE_URL` có cùng ý nghĩa. Dấu gạch dưới bổ sung có thể biểu đạt một level tên khác.

Khi dự án dùng nhiều custom properties, viết một bảng mapping tên key và kiểm bằng integration test sẽ giảm lỗi deployment đáng kể.

## 16. Placeholder của Compose và placeholder của Spring khác nhau

Trong Compose:

~~~yaml
environment:
  APP_CLIENT_TIMEOUT: "${CLIENT_TIMEOUT:-3s}"
~~~

Biểu thức do Compose giải quyết. Trong `application.yml`:

~~~yaml
app:
  client:
    timeout: "${APP_CLIENT_TIMEOUT:2s}"
~~~

Biểu thức này do Spring Boot Environment giải quyết trong process Java. Luồng:

~~~text
Compose .env: CLIENT_TIMEOUT=5s
    |
    v
Compose ${CLIENT_TIMEOUT:-3s} -> "5s"
    |
    v
container APP_CLIENT_TIMEOUT=5s
    |
    v
Spring ${APP_CLIENT_TIMEOUT:2s} -> "5s"
    |
    v
Binder -> Duration.ofSeconds(5)
~~~

Nếu Compose không truyền `APP_CLIENT_TIMEOUT`, placeholder Spring mới có thể áp dụng fallback `2s`. Đừng vô tình dùng hai default khác nhau cho cùng một contract mà không xác định tầng nào chịu trách nhiệm.

### Khi cần literal dollar trong compose.yaml

Compose có quy tắc `$$` để tránh interpolation một lần khi muốn giữ ký tự dollar cho bước sau. Nhưng nếu chỉ cần Spring placeholder, thường đơn giản hơn khi để nó trong `application.yml`, không nhúng placeholder Spring qua nhiều tầng Compose/YAML/shell.

## 17. Cổng host, cổng container và server.port

~~~yaml
services:
  api:
    ports:
      - "18080:8080"
    environment:
      SERVER_PORT: "8080"
~~~

Đọc theo ba ý:

- `18080`: cổng publish trên **máy host**.
- `8080` ở bên phải dấu `:`: cổng **container** mà Docker chuyển kết nối tới.
- `SERVER_PORT=8080`: cổng mà **Spring Boot** đang nghe trong container.

Từ host:

~~~text
http://localhost:18080
~~~

Từ container khác cùng Compose network:

~~~text
http://api:8080
~~~

Khi đổi `SERVER_PORT=9090` mà giữ `ports: "18080:8080"`, host vẫn gửi đến container 8080, trong khi Spring nghe 9090. Cần đổi container-side mapping tương ứng.

`EXPOSE 8080` trong Dockerfile chỉ mô tả metadata; không tự publish port. Không cần publish cổng của mọi service ra host nếu chỉ có các service nội bộ gọi nhau.

## 18. localhost bên trong container không phải host máy

Với Compose:

~~~yaml
services:
  api:
    image: example/order-service:local
  db:
    image: postgres:17
~~~

Container `api` gọi `localhost:5432` sẽ tìm database trong chính network namespace của `api`, không phải container `db`.

Để truy cập database service qua Compose network, dùng tên service:

~~~yaml
services:
  api:
    environment:
      SPRING_DATASOURCE_URL: "jdbc:postgresql://db:5432/orders"
~~~

`db` là hostname service được Docker DNS trong network phù hợp giải quyết. Đừng lấy host published port để kết nối giữa hai container trong cùng network trừ khi có lý do kiến trúc cụ thể.

`depends_on` cơ bản giúp thứ tự khởi động, **không bảo đảm database đã ready**. Khi cần, dùng healthcheck/`condition: service_healthy` được Compose version hỗ trợ hoặc logic retry kết nối phù hợp.

## 19. Spring profiles và Compose profiles là hai tính năng khác

Compose có service profiles:

~~~yaml
services:
  api:
    image: example/order-service:local

  debug-ui:
    image: example/debug-ui:local
    profiles:
      - debug
~~~

Lệnh:

~~~bash
docker compose --profile debug up -d
~~~

điều khiển service `debug-ui` có tham gia deployment hay không. **Nó không tự đặt** `spring.profiles.active=debug` cho Spring Boot.

Để kích hoạt Spring profile trong Java:

~~~yaml
services:
  api:
    environment:
      SPRING_PROFILES_ACTIVE: "${APP_PROFILE:-dev}"
~~~

File `.env`:

~~~dotenv
APP_PROFILE=prod
~~~

sẽ cấp biến `SPRING_PROFILES_ACTIVE=prod` và Spring Boot có thể đọc `application-prod.yml`. `APP_PROFILE` là tên tùy ý cho Compose; `SPRING_PROFILES_ACTIVE` là tên Spring hiểu.

| Khái niệm | Điều khiển |
| --- | --- |
| Compose `profiles` | Service nào chạy |
| Spring `spring.profiles.active` | Property/bean/profile condition trong ứng dụng |
| Compose `.env` | Biến nội suy model |
| Compose `env_file` | Biến được cấp cho container |

## 20. Dockerfile ENV so với runtime override

~~~dockerfile
FROM eclipse-temurin:21-jre
ENV SERVER_PORT=8080
ENV APP_CLIENT_TIMEOUT=3s
COPY target/order-service.jar /app/app.jar
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Nếu Compose ghi:

~~~yaml
environment:
  APP_CLIENT_TIMEOUT: "5s"
~~~

container dùng runtime value 5s đối với key trùng, thay vì image default 3s. `SERVER_PORT` tiếp tục được kế thừa khi không có override.

Không đặt API token/password trong Dockerfile `ENV`. Giá trị có thể còn trong image metadata và nhiều bản sao của artifact.

Cũng cần kiểm `command` trong Compose: nếu ENTRYPOINT là `java -jar` và Compose truyền `--spring.profiles.active=prod`, Spring Boot thường ưu tiên CLI argument này hơn OS environment `SPRING_PROFILES_ACTIVE`.

## 21. docker run và docker compose run

Với Docker trực tiếp:

~~~bash
docker run --rm \
  -p 18080:8080 \
  -e SPRING_PROFILES_ACTIVE=dev \
  -e APP_CLIENT_TIMEOUT=5s \
  example/order-service:local
~~~

`-e` cấp container environment trực tiếp.

~~~bash
docker run --rm \
  --env-file ./env/runtime.env \
  -p 18080:8080 \
  example/order-service:local
~~~

`docker run --env-file` cũng cấp container environment.

Với Compose:

~~~bash
docker compose run -e APP_CLIENT_TIMEOUT=1s api
~~~

`run` tạo **one-off container** và override env cho lần đó, không tự thay container service vốn đang chạy do `docker compose up -d` tạo ra. Lệnh `run` cũng có khác biệt về việc publish ports; đừng dùng hành vi của `run` để suy luận hoàn toàn về `up`.

## 22. Chẩn đoán Compose model mà không lộ dữ liệu

Các lệnh có thể hữu ích:

~~~bash
docker compose config --quiet
docker compose config --services
~~~

`--quiet` dùng kiểm tra cấu hình mà không xuất bản đầy đủ YAML đã nội suy; `--services` liệt kê tên service.

Lệnh:

~~~bash
docker compose config
~~~

thường in model đã nội suy. Nếu `environment` chứa credential từ `${SECRET}`, output có thể lộ secret. Không gửi nguyên output lên chat, issue, artifact CI không bảo vệ.

Một số Compose version hỗ trợ:

~~~bash
docker compose config --environment
~~~

để xem biến được sử dụng cho interpolation. Output này cũng **có thể chứa giá trị nhạy cảm**. Chỉ dùng trong môi trường/đường log được kiểm soát.

Không dùng debug output đầy đủ như mặc định trong CI job có secrets.

## 23. Xem một số biến trong container một cách an toàn

Sau:

~~~bash
docker compose up -d
~~~

có thể kiểm **một biến không nhạy cảm**:

~~~bash
docker compose exec api sh -lc 'printf "profile=%s\n" "$SPRING_PROFILES_ACTIVE"'
~~~

hoặc:

~~~bash
docker compose exec api sh -lc 'printf "port=%s\n" "$SERVER_PORT"'
~~~

Ví dụ giả định image có `sh`. Với distroless image không có shell, cần cách kiểm an toàn khác.

Đừng chạy rồi chia sẻ `docker compose exec api printenv` trên production: nó có thể in password, API key và token. `docker inspect` cũng có thể làm lộ biến môi trường từ metadata container. Giới hạn quyền truy cập Docker socket và các công cụ chẩn đoán tương ứng.

**Biến có trong container** chưa phải bằng chứng Spring Boot đã chọn value đó; `--app.client.timeout` hoặc JVM `-D` có thể ghi đè.

## 24. Vì sao .env có giá trị nhưng Java không nhận?

Ví dụ:

~~~dotenv
# .env
APP_CLIENT_TIMEOUT=5s
~~~

~~~yaml
services:
  api:
    image: example/order-service:local
~~~

Không có `environment` hay `env_file`, nên Spring Boot không tự nhận `APP_CLIENT_TIMEOUT`.

Hai cách sửa:

~~~yaml
services:
  api:
    environment:
      APP_CLIENT_TIMEOUT: "${APP_CLIENT_TIMEOUT:-3s}"
~~~

hoặc:

~~~yaml
services:
  api:
    env_file:
      - ./.env
~~~

Cách thứ hai cố tình nạp **toàn bộ file `.env` vào container**, có thể cấp cả những biến chỉ dùng nội suy Compose. Nên tách file và chỉ đưa biến cần thiết vào container để tránh leak và môi trường runtime bị nhiễu.

## 25. Vì sao env_file có giá trị nhưng @ConfigurationProperties vẫn dùng fallback?

Ví dụ file:

~~~dotenv
APP_CLIENT_BASE_URL=https://api.example.test
~~~

nhưng model:

~~~java
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(URI baseUrl) {}
~~~

và YAML mặc định:

~~~yaml
app:
  client:
    base-url: https://fallback.example.test
~~~

Có thể tên biến sai: canonical env mapping cho `app.client.base-url` thường là `APP_CLIENT_BASEURL`, không phải `APP_CLIENT_BASE_URL`. Thử sửa tên đúng và tái tạo container để biến runtime được cập nhật.

Cũng cần kiểm:

1. Service có tham chiếu đúng `env_file`?
2. Đường dẫn file đúng trong ngữ cảnh Compose?
3. `environment` có đang ghi đè cùng key?
4. Container đã recreate sau khi sửa file?
5. Bean `@ConfigurationProperties` có được scan/enable?
6. Có CLI argument hoặc PropertySource ưu tiên cao hơn?
7. Value có chuyển kiểu được sang `URI`/`Duration`?

Không chỉnh fallback trong JAR để che vấn đề không truyền biến ở Compose.

## 26. Đổi .env không tự đổi environment của container cũ

Container environment được xác định lúc container được tạo. Khi sửa `.env` hoặc `env/runtime.env` trên host, **process Java đang chạy không tự nhận biến mới**.

Thông thường cần:

1. Đảm bảo Compose đọc phiên bản file mới.
2. Compose tính lại mô hình service.
3. Recreate/redeploy container nếu runtime settings thay đổi.
4. Spring Boot process khởi động và bind lại property.

Lệnh:

~~~bash
docker compose up -d
~~~

thường cho Compose điều chỉnh những service có cấu hình thay đổi. Nếu muốn chủ động recreate trong lab:

~~~bash
docker compose up -d --force-recreate api
~~~

Chú ý lệnh này có thể gây gián đoạn, không tự áp dụng production mà không có rollout plan.

Tương tự, Spring Boot `@ConfigurationProperties` thông thường được bind ở startup, không tự refresh chỉ vì file bên ngoài được sửa.

## 27. Host shell không tự được copy toàn bộ vào container

Giả sử host shell có:

~~~bash
export APP_CLIENT_TIMEOUT=7s
docker compose up -d
~~~

Compose CLI có thể dùng giá trị host trong biểu thức `${APP_CLIENT_TIMEOUT}`. Nhưng nếu service không tham chiếu biến đó, container không mặc nhiên kế thừa toàn bộ shell environment.

Cách truyền rõ ràng:

~~~yaml
services:
  api:
    environment:
      APP_CLIENT_TIMEOUT: "${APP_CLIENT_TIMEOUT:-3s}"
~~~

Phân tách này hữu ích cho bảo mật: container không tự nhận cloud credentials, user secrets hay session metadata vô tình tồn tại trên host. Tránh `env_file` quá rộng hoặc tự động dump toàn bộ shell env vào container.

## 28. Config Data và PropertySource có precedence riêng

Container có:

~~~text
APP_CLIENT_TIMEOUT=7s
~~~

nhưng ứng dụng khởi chạy với:

~~~bash
java -jar app.jar --app.client.timeout=500ms
~~~

Trong Spring Boot thông thường, CLI argument `--app.client.timeout=500ms` có ưu tiên cao hơn OS environment và value được bind có thể là 500 ms.

Một JVM system property:

~~~bash
java -Dapp.client.timeout=1s -jar app.jar
~~~

cũng có thể ghi đè OS environment khi không có nguồn ưu tiên cao hơn.

Những nguồn khác như `SPRING_APPLICATION_JSON` hoặc test PropertySources có thứ tự riêng. Khi debug, xác định **effective Spring property**, không chỉ biến Docker.

## 29. Compose override files và đường dẫn

Với nhiều file:

~~~bash
docker compose -f compose.yaml -f compose.prod.yaml up -d
~~~

Compose merge các mô hình theo quy tắc và thứ tự file. Cần xác định:

- File nào đặt `services.api.environment`?
- File nào đặt `env_file` và đường dẫn file được giải quyết theo base/project directory?
- `ports` nào được dùng sau merge?
- Biến nào được nội suy từ shell/`.env`/`--env-file`?
- Spring process cuối cùng nhận những biến nào?

Không đồng nhất `compose.prod.yaml` với Spring profile `prod`. Một Compose override có thể đặt `SPRING_PROFILES_ACTIVE=prod`, nhưng đó là **khai báo tường minh**, không phải tính năng tự động.

Khi dùng CI/CD, cố định thư mục chạy lệnh, thứ tự `-f` và đường dẫn env files để tránh bản deploy ở runner khác có giá trị khác.

## 30. Secret không nên được nội suy bừa vào environment

Ví dụ có rủi ro:

~~~yaml
services:
  api:
    environment:
      SPRING_DATASOURCE_PASSWORD: "${DB_PASSWORD}"
~~~

Cách trên có thể hoạt động, nhưng secret có thể xuất hiện trong Compose config output, container metadata, process diagnostics hoặc CI logs. File `.env` không tự được mã hóa; đừng commit secret vào repo.

Tùy nền tảng, cân nhắc:

- Secret manager với workload identity.
- Docker Compose secrets được mount thành file.
- File mount với filesystem permissions phù hợp.
- Kênh cấp phát runtime do orchestrator quản lý.
- Least privilege, rotation, audit và hạn chế log.

Environment variables vẫn có các trường hợp dùng hợp lý, nhưng không phải mặc định tốt nhất cho mọi credential. Đừng đưa secret thật vào ví dụ README.

## 31. Docker Compose secrets với Spring Boot configtree

Spring Boot có thể nạp key/value từ file tree qua `configtree:`. Compose có thể mount secret theo tên file mục tiêu. Ví dụ minh họa với PostgreSQL:

~~~yaml
services:
  api:
    image: example/order-service:local
    environment:
      SPRING_DATASOURCE_URL: "jdbc:postgresql://db:5432/orders"
      SPRING_DATASOURCE_USERNAME: "orders_app"
      SPRING_CONFIG_IMPORT: "configtree:/run/secrets/"
    secrets:
      - source: db_password
        target: spring.datasource.password

  db:
    image: postgres:17
    environment:
      POSTGRES_DB: "orders"
      POSTGRES_USER: "orders_app"
      POSTGRES_PASSWORD_FILE: "/run/secrets/db_password"
    secrets:
      - source: db_password
        target: db_password

secrets:
  db_password:
    file: ./secrets/db-password.txt
~~~

Luồng:

~~~text
./secrets/db-password.txt (host file, được bảo vệ)
            |
            v
Docker Compose secret mount cho api:
   /run/secrets/spring.datasource.password
            |
            v
SPRING_CONFIG_IMPORT=configtree:/run/secrets/
            |
            v
Spring Boot property: spring.datasource.password
~~~

Với container `db`, image PostgreSQL đọc file `/run/secrets/db_password` qua `POSTGRES_PASSWORD_FILE`.

**Tên file trong configtree quyết định tên property.** Nếu file trong `/run/secrets/` chỉ tên `db_password`, Spring Boot không tự suy ra `spring.datasource.password`. Khai báo `target: spring.datasource.password` phục vụ yêu cầu này.

Ví dụ cần image ứng dụng đã build, secret file thật nằm ngoài repository và các thiết lập volume/healthcheck thích hợp để thành deployment hoàn chỉnh. Docker Compose secrets dựa trên file host không tự mã hóa file nguồn; vẫn cần quyền truy cập filesystem, backup và cách provision an toàn.

## 32. configtree bắt buộc và optional

Có thể dùng trong Spring Boot:

~~~properties
spring.config.import=configtree:/run/secrets/
~~~

hoặc:

~~~properties
spring.config.import=optional:configtree:/run/secrets/
~~~

`optional:` cho phép bỏ qua location không có theo quy tắc Config Data. Với development, điều đó có thể phù hợp; với production cần password bắt buộc, thường nên fail fast nếu secret mount không tồn tại.

Nếu một volume secret được rotate, Config Data và bean/connection pool đã khởi tạo không tự cập nhật ngay trừ khi ứng dụng có cơ chế refresh/recreate thích hợp. Rotation cần thiết kế rollout và thời điểm thu hồi credential cũ.

## 33. Mount file cấu hình thay vì hàng trăm biến

Với cấu hình lồng nhau dài như danh sách pipeline, map và nhiều endpoints, có thể mount một tệp cấu hình:

~~~yaml
services:
  api:
    volumes:
      - ./deploy/config:/etc/order-config:ro
    environment:
      SPRING_CONFIG_ADDITIONAL_LOCATION: "optional:file:/etc/order-config/"
      SPRING_PROFILES_ACTIVE: "prod"
~~~

Spring Boot có thể tìm Config Data bổ sung ở location theo quy tắc version đang dùng. Với directory location, dùng cú pháp đường dẫn `file:/.../` có dấu slash cuối phù hợp.

File YAML lớn thường dễ quản lý hơn rất nhiều biến `APP_PIPELINES_0_...`. Nhưng file được mount không tự bảo mật: file thường dùng cho non-secret config có thể có quyền truy cập khác so với file chứa secret.

Cần xét precedence: OS environment có thể ghi đè một key trong file bổ sung; file mount không có nghĩa tự thắng mọi nguồn.

## 34. List và Map khi cấp bằng environment

Ví dụ Spring Boot list:

~~~text
APP_PIPELINES_0_NAME=orders
APP_PIPELINES_0_RETRY_MAXATTEMPTS=3
APP_PIPELINES_1_NAME=invoices
~~~

Docker chỉ truyền chuỗi. Spring Boot Binder dựa trên kiểu Java và quy tắc relaxed binding để xây `List<Pipeline>`.

Nhưng với nhiều PropertySource, **list thường được thay thế theo nguồn ưu tiên cao hơn thay vì deep merge từng index**. Chỉ cấp một field của phần tử `[0]` bằng env có thể khiến list cuối không như dự kiến.

Nếu thứ tự không quan trọng và phần tử có tên định danh ổn định, cân nhắc `Map<String,Pipeline>`. Với list có thứ tự quan trọng, nên quản lý trọn list trong một nguồn cấu hình được kiểm soát.

## 35. CI/CD: runner variable không tự là container variable

Một pipeline có:

~~~text
DEPLOY_ENV=prod
HOST_HTTP_PORT=18080
APP_CLIENT_TIMEOUT=2s
~~~

Compose có thể dùng chúng để nội suy. Nhưng container chỉ nhận biến được cấp qua service config hoặc runtime mechanism.

~~~yaml
services:
  api:
    environment:
      SPRING_PROFILES_ACTIVE: "${DEPLOY_ENV:?Missing environment}"
      APP_CLIENT_TIMEOUT: "${APP_CLIENT_TIMEOUT:?Missing timeout}"
~~~

Trong CI, tránh log toàn bộ shell env hoặc chạy `docker compose config` rồi upload output có credentials. Không cấp production secrets cho PR không tin cậy. Ưu tiên token ngắn hạn và chỉ cấp quyền cho những job/service thật sự cần.

## 36. .gitignore và .env.example

Có thể tổ chức:

~~~text
.env.example      # không chứa secret thật, có thể commit
.env              # local; quản lý theo chính sách repo
env/runtime.env   # nếu có secret thật thì không commit
secrets/          # file secret local, hạn chế quyền
~~~

Ví dụ `.env.example`:

~~~dotenv
HOST_HTTP_PORT=18080
APP_PROFILE=dev
CLIENT_TIMEOUT=3s
~~~

Thêm `.env`, `secrets/` vào `.gitignore` giúp giảm commit nhầm file chưa theo dõi, nhưng không tự loại bỏ file đã commit, bản sao trong Git history, image layers hoặc CI artifacts. Nếu credential thật bị lộ, cần revoke/rotate theo quy trình sự cố.

## 37. Quy trình debug 12 bước

1. **Xác định container/service** đang lỗi, không gom chung tất cả env của Compose project.
2. **Phân loại biến**: chỉ dùng để Compose interpolation, container environment, hay Spring property?
3. **Kiểm `compose.yaml`** và các file override `-f` đúng thứ tự.
4. **Kiểm nguồn nội suy**: shell, `.env` và `--env-file`, tránh in secret.
5. **Kiểm `environment` và `env_file`** của đúng service.
6. **Kiểm Spring canonical env naming** như `APP_CLIENT_BASEURL`.
7. **Kiểm container có cần recreate** sau khi sửa file không.
8. **Kiểm một vài biến không nhạy cảm** trong container, không dump toàn bộ.
9. **Kiểm ENTRYPOINT/command** có ghi đè bằng `--spring.*` hoặc `-D` không.
10. **Kiểm Spring profile và Config Data** nào được nạp, kể cả `spring.config.import`.
11. **Kiểm networking/ports**: service DNS, `localhost`, host/container port và DB readiness.
12. **Kiểm Java binding**: `@ConfigurationPropertiesScan`/`@EnableConfigurationProperties`, prefix, kiểu và validation.

Đừng kết luận một lỗi `@ConfigurationProperties` là do Docker không cấp biến trước khi kiểm các tầng còn lại. Cũng đừng debug bằng cách in tất cả credentials.

## 38. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng giải quyết |
| --- | --- | --- |
| Port host đổi nhưng Java không thấy `HOST_HTTP_PORT` | Biến chỉ được Compose nội suy | Truyền tường minh nếu Java thật sự cần |
| `--env-file` có key nhưng container không nhận | Nhầm option CLI với service `env_file` | Dùng `environment`/`env_file` |
| Container nhận timeout cũ | Không recreate sau khi sửa env file | Deploy lại có kiểm soát |
| `env_file` ghi 5s nhưng container có 2s | `environment` ghi đè | Xem precedence runtime |
| Java vẫn dùng URL fallback | Env name/prefix sai hoặc PropertySource khác thắng | Kiểm `APP_CLIENT_BASEURL` và effective value |
| Spring profile không đổi khi `--profile debug` | Compose profiles không phải Spring profiles | Đặt `SPRING_PROFILES_ACTIVE` |
| Container không kết nối `localhost:5432` | Đang gọi chính container | Dùng `db:5432` |
| Host mapping 18080:8080 lỗi sau khi đổi server.port | Listener bên trong không còn nghe 8080 | Cập nhật container port mapping |
| Secret hiện trong `docker compose config` | Nội suy credential trực tiếp | Chọn secret mount/manager, hạn chế debug |
| Configtree không tạo password property | Tên secret file không khớp key | Dùng target `spring.datasource.password` |
| Compose chạy nhưng DB chưa nhận kết nối | DB chưa ready hoặc credential sai | Healthcheck/retry và kiểm credentials |
| List config mất phần tử | Env override một phần list | Quản lý cả list hoặc dùng map phù hợp |

## 39. Bài tập tự luyện

### Bài 1 — .env có HOST_PORT

~~~dotenv
HOST_PORT=18080
~~~

~~~yaml
ports:
  - "${HOST_PORT}:8080"
~~~

**Hỏi:** `HOST_PORT` có tự xuất hiện trong container? **Đáp án:** không. Compose chỉ dùng nó để tính port mapping.

### Bài 2 — Ánh xạ APP_PROFILE

~~~dotenv
APP_PROFILE=prod
~~~

~~~yaml
environment:
  SPRING_PROFILES_ACTIVE: "${APP_PROFILE}"
~~~

**Đáp án:** container nhận `SPRING_PROFILES_ACTIVE=prod`; không suy ra tự nhận `APP_PROFILE`.

### Bài 3 — Chỉ dùng CLI env-file

~~~bash
docker compose --env-file ./deploy/prod.env up -d
~~~

File có `APP_CLIENT_TIMEOUT=9s` nhưng Compose không tham chiếu key này. **Đáp án:** không tự vào container.

### Bài 4 — service env_file

~~~yaml
services:
  api:
    env_file:
      - ./env/runtime.env
~~~

File có `APP_CLIENT_TIMEOUT=9s`. **Đáp án:** đây là nguồn runtime container environment.

### Bài 5 — environment và env_file trùng key

`env_file` có `APP_CLIENT_TIMEOUT=5s`, `environment` có `APP_CLIENT_TIMEOUT=2s`. **Đáp án:** runtime value dự kiến là 2s vì `environment` ưu tiên.

### Bài 6 — Host và container port

`ports: "18080:8080"`, `SERVER_PORT=8080`. **Đáp án:** host dùng 18080; Spring Boot nghe 8080 trong container.

### Bài 7 — Database service DNS

Trong container `api`, JDBC tới `localhost:5432` không tới container `db`. **Đáp án:** dùng `db:5432` nếu cùng network phù hợp.

### Bài 8 — Compose profile và Spring profile

`docker compose --profile debug up -d` có tự active Spring profile `debug` không? **Đáp án:** không.

### Bài 9 — Canonical env name

Property `app.client.base-url` dùng tên env nào? **Đáp án:** `APP_CLIENT_BASEURL` theo canonical Spring Boot relaxed binding.

### Bài 10 — Secret và configtree

Secret file tên `db_password` nhưng Spring Boot import `configtree:/run/secrets/` và mong key `spring.datasource.password`. **Đáp án:** tên file phải được map phù hợp; ví dụ mount target `spring.datasource.password`.

### Bài 11 — Đổi .env

Sửa `.env` nhưng process Java cũ chưa đổi timeout. **Đáp án:** cần cập nhật/recreate container và Spring context theo chính sách deploy.

### Bài 12 — Debug an toàn

Có thể paste full `docker compose config` vào issue khi secret được nội suy không? **Đáp án:** không; output có thể chứa credential.

## 40. Bảng ghi nhớ cuối bài

| Mục đích | Cơ chế |
| --- | --- |
| Biến dùng để tính Compose model | `.env`, shell hoặc `docker compose --env-file` |
| Biến thật bên trong container | `services.environment` hoặc `services.env_file` |
| Giá trị mặc định trong image | Dockerfile `ENV` |
| Host port từ biến | `"${HOST_PORT:-18080}:8080"` |
| Spring active profile | `SPRING_PROFILES_ACTIVE` |
| Cổng lắng nghe của Java | `SERVER_PORT` hoặc `server.port` |
| URL nội bộ database | `jdbc:postgresql://db:5432/orders` |
| Custom Spring property | `APP_CLIENT_TIMEOUT`, `APP_CLIENT_BASEURL` |
| Kiểm Compose model mà không in full values | `docker compose config --quiet` |
| Xem service names | `docker compose config --services` |
| Kiểm vài biến không nhạy cảm | `docker compose exec api sh -lc '...'` |
| Secret file cho Spring Boot | `configtree:/run/secrets/` |
| Bảo vệ production secret | Secret manager/secret mount và least privilege |
| Tránh dùng biến host làm container env vô tình | Chỉ truyền allowlist cần thiết |
| Muốn thay container env | Recreate/redeploy container |
| Biết property cuối Spring dùng | Xem Environment precedence và Binder |

## 41. Kết luận

Hãy nhớ ba mệnh đề:

1. **`.env` và `docker compose --env-file` phục vụ chủ yếu cho Compose interpolation.**
2. **`environment` và `env_file` của service cấp các biến thật vào container; một biến host hoặc Compose-only không tự đi vào.**
3. **Spring Boot Environment và Binder xác định property Java cuối cùng từ các nguồn container, file, CLI và các PropertySource khác.**

Khi một giá trị không đúng, lần theo đúng đường: **shell/.env → Compose interpolation → service runtime environment → process Java → Spring Environment → @ConfigurationProperties**. Khi gặp secret, giới hạn quyền và tránh lộ qua Git, `docker compose config`, `printenv` và Docker metadata. Phân biệt rõ những tầng này giúp ứng dụng chạy nhất quán giữa local, Docker Compose và môi trường triển khai.

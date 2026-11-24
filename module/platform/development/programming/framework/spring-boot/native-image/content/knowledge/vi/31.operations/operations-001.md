# Cung cấp cấu hình, credentials và địa chỉ dịch vụ khi ứng dụng chạy

GraalVM Native Image tạo ra executable có classpath và tập code được xác định trong quá trình build. Điều đó không có nghĩa mọi giá trị cấu hình phải được đóng cứng vào binary. Spring Boot vẫn có thể đọc cấu hình, credentials và địa chỉ dịch vụ khi process khởi động thông qua environment variables, command-line arguments, system properties, file cấu hình ngoài và configuration trees.

Cần phân biệt **giá trị runtime** với **cấu trúc ứng dụng đã được AOT xử lý**. URL database, API key, timeout, port hoặc địa chỉ service có thể thay đổi theo môi trường. Nhưng file cấu hình ngoài không thể thêm class mới vào native executable, và không nên dựa vào việc đổi profile lúc runtime để tạo bean graph khác với graph đã được Spring AOT chuẩn bị.

Bài học thuộc chương **Vận hành** của mô-đun `SPRING_BOOT_NATIVE_IMAGE`. Ta sẽ tổ chức externalized configuration, bind và validate bằng `@ConfigurationProperties`, cấp secrets bằng environment/config tree, cấu hình địa chỉ service trong Docker/Kubernetes, xử lý thay đổi credentials và kiểm tra cấu hình thực tế trên native executable.

## 1. Giá trị runtime và cấu trúc build-time

Khi build native image, GraalVM phân tích code từ entry point và tạo executable theo những gì có thể reach được. Classpath không thể được thay đổi tùy ý sau khi binary đã được tạo. Spring AOT cũng chuẩn bị bean definitions và các thành phần liên quan trong build process.

| Nhóm | Ví dụ | Thời điểm quyết định |
| --- | --- | --- |
| Runtime values | Database URL, username/password, API endpoint, API key, timeout, port | Khi process khởi động hoặc qua cơ chế refresh được hỗ trợ |
| Build/AOT structure | Class, dependency, bean graph, proxy type, implementation được đưa vào executable | Khi compile/AOT/native image build |
| Runtime resources | File YAML ngoài, certificate, mounted secret, template ngoài nếu ứng dụng hỗ trợ đọc | Khi process chạy; phải có file và quyền truy cập |
| Native metadata | Reflection, resource, serialization, JNI, proxy hints | Chủ yếu được xác định trong build |

Có thể đổi địa chỉ database bằng `SPRING_DATASOURCE_URL` khi khởi chạy cùng một native executable ở staging và production. Nhưng không thể mount thêm một JAR chứa driver mới rồi yêu cầu native executable tự nạp driver đó như JVM classpath động.

Tương tự, có thể thay API key hoặc URL của payment service qua cấu hình runtime. Nếu muốn đổi implementation bean dựa trên `@Profile` hoặc `@ConditionalOnProperty`, cần xem giới hạn Spring AOT của phiên bản đang dùng. Bean graph của native application không thể thay đổi tùy ý sau khi build.

## 2. Các nguồn cấu hình Spring Boot

Spring Boot hỗ trợ nhiều nguồn cấu hình:

- File `application.properties` hoặc `application.yaml` trong classpath.
- File cấu hình bên ngoài executable/container.
- Environment variables.
- Java system properties.
- Command-line arguments.
- `SPRING_APPLICATION_JSON`.
- Configuration trees được mount từ Docker/Kubernetes hoặc nền tảng quản lý secret.
- Các nguồn do integration như Spring Cloud Config/Vault cung cấp.

Với các nguồn vận hành thường gặp, giá trị ở nguồn có ưu tiên cao hơn sẽ ghi đè nguồn thấp hơn:

| Thứ tự tương đối | Nguồn | Ví dụ |
| --- | --- | --- |
| Thấp hơn | Default trong code hoặc default properties | Giá trị mặc định an toàn cho timeout |
| | Config data trong executable/classpath | `application.yaml` |
| | Config data ngoài executable | `/etc/orders/application.yaml` |
| | Environment variables | `SPRING_DATASOURCE_URL` |
| | Java system properties | `-Dserver.port=8081` |
| | `SPRING_APPLICATION_JSON` | JSON cấu hình được truyền lúc khởi động |
| Cao hơn | Command-line arguments | `--server.port=8082` |

Đây là cách nhìn rút gọn cho các nguồn phổ biến. Spring Boot có thứ tự PropertySource đầy đủ hơn, bao gồm test properties, JNDI, servlet parameters và các nguồn khác. Khi một property có giá trị bất ngờ, cần kiểm tra toàn bộ nguồn đang tham gia thay vì chỉ nhìn file YAML.

### 2.1. Environment variable mapping

Spring Boot chuyển tên property canonical sang environment variable theo quy tắc:

1. Thay dấu chấm (`.`) bằng dấu gạch dưới (`_`).
2. Bỏ dấu gạch ngang (`-`).
3. Chuyển thành chữ hoa.

| Property | Environment variable |
| --- | --- |
| `spring.datasource.url` | `SPRING_DATASOURCE_URL` |
| `spring.datasource.username` | `SPRING_DATASOURCE_USERNAME` |
| `spring.datasource.password` | `SPRING_DATASOURCE_PASSWORD` |
| `server.port` | `SERVER_PORT` |
| `app.remote.base-url` | `APP_REMOTE_BASEURL` |
| `app.payment.api-key` | `APP_PAYMENT_APIKEY` |

Dấu gạch ngang bị loại bỏ khi tạo tên environment variable. Với property tùy biến có nhiều segment, hãy đối chiếu quy tắc relaxed binding để tránh đặt tên sai.

### 2.2. Command-line arguments và JSON

Spring Boot nhận các tham số bắt đầu bằng `--` và thêm chúng vào Environment:

```bash
./orders-service --server.port=8081 --app.remote.base-url=https://inventory.internal
```

Command-line arguments có ưu tiên cao, thuận tiện cho thử nghiệm hoặc override không thường xuyên. Không truyền password, token hoặc private key qua command line vì arguments có thể xuất hiện trong process inspection, shell history hoặc log của hệ thống chạy process.

Có thể truyền nhiều property trong một JSON object:

```bash
SPRING_APPLICATION_JSON='{"app":{"remote":{"base-url":"https://inventory.internal"}}}' ./orders-service
```

JSON environment variable không phải secret store. Không đặt credential nhạy cảm vào đây nếu môi trường có thể ghi lại environment hoặc command.

## 3. Đặt file cấu hình ngoài executable

Spring Boot mặc định tìm `application.properties` hoặc `application.yaml` ở classpath và một số vị trí bên ngoài working directory, chẳng hạn thư mục hiện tại và `config/`. Có thể thêm hoặc thay vị trí bằng hai property:

- `spring.config.additional-location`: thêm location vào các vị trí mặc định.
- `spring.config.location`: thay thế các vị trí mặc định bằng danh sách đã chỉ định.

Giữ cấu hình mặc định và thêm thư mục mount:

```bash
./orders-service --spring.config.additional-location=file:/etc/orders/
```

Thư mục location nên kết thúc bằng dấu `/`. Spring Boot sẽ tìm file cấu hình theo tên được chọn, thường là `application.yaml`, và các file theo profile nếu phù hợp.

Nếu muốn chỉ dùng file ngoài:

```bash
./orders-service --spring.config.location=file:/etc/orders/
```

Dùng `spring.config.location` cẩn thận vì nó thay thế search locations mặc định. Nếu file ngoài không tồn tại, ứng dụng có thể dừng khởi động. Dùng prefix `optional:` khi location thực sự là tùy chọn:

```bash
./orders-service --spring.config.additional-location=optional:file:/etc/orders/
```

Các property `spring.config.name`, `spring.config.location` và `spring.config.additional-location` được dùng rất sớm để xác định file cần nạp. Hãy truyền chúng qua environment variable, system property hoặc command line ngay từ đầu process; không chờ một bean trong ApplicationContext cung cấp các giá trị này.

## 4. Cấu hình mặc định và override theo môi trường

Một file mặc định có thể giữ các giá trị không nhạy cảm:

```yaml
spring:
  application:
    name: orders-service
  datasource:
    url: jdbc:postgresql://localhost:5432/orders
    hikari:
      connection-timeout: 2s
      maximum-pool-size: 10

server:
  port: 8080

app:
  inventory:
    base-url: http://localhost:8081
    connect-timeout: 2s
    read-timeout: 5s
  payment:
    base-url: https://payments.example.internal
```

Khi chạy trong môi trường container, environment variables có thể thay URL database và service endpoint mà không cần build lại:

```bash
SPRING_DATASOURCE_URL=jdbc:postgresql://postgres:5432/orders APP_INVENTORY_BASEURL=http://inventory-api:8080 ./orders-service
```

Tên `APP_INVENTORY_BASEURL` tương ứng property `app.inventory.base-url` theo quy tắc relaxed binding. Nếu muốn dùng tên environment dễ đọc hơn như `INVENTORY_BASE_URL`, khai báo placeholder trong YAML:

```yaml
app:
  inventory:
    base-url: ${INVENTORY_BASE_URL:http://localhost:8081}
```

Placeholder có dạng `${NAME:default}`. Không đặt default giả cho production credentials. Default local chỉ nên phục vụ development; production cần override rõ ràng.

## 5. Bind cấu hình có kiểu bằng @ConfigurationProperties

Với cấu hình có nhiều thuộc tính, dùng `@ConfigurationProperties` thay vì rải nhiều `@Value` trong các bean. Cách này gom cấu hình theo domain, chuyển đổi kiểu và validate ngay khi khởi động.

Ví dụ cấu hình inventory service:

```java
package com.example.orders.config;

import java.net.URI;
import java.time.Duration;

import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@ConfigurationProperties(prefix = "app.inventory")
@Validated
public record InventoryProperties(
        @NotNull URI baseUrl,
        @NotNull Duration connectTimeout,
        @NotNull Duration readTimeout) {
}
```

Bật scan:

```java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class OrdersApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
```

Cần dependency validation phù hợp, ví dụ `spring-boot-starter-validation`, để các constraint Jakarta Validation được thực thi. Nếu URL thiếu hoặc timeout không bind được, ứng dụng nên fail fast thay vì chạy với endpoint sai. Với yêu cầu scheme/host cụ thể, bổ sung validator riêng để chỉ chấp nhận URI có scheme `http` hoặc `https` và host hợp lệ.

### 5.1. Tạo client từ runtime properties

Ví dụ cấu hình một RestClient dùng base URL lấy từ Environment:

```java
package com.example.orders.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
class InventoryClientConfiguration {

    @Bean
    RestClient inventoryRestClient(
            RestClient.Builder builder,
            InventoryProperties properties) {

        return builder
                .baseUrl(properties.baseUrl().toString())
                .build();
    }
}
```

Địa chỉ được đọc khi ứng dụng khởi tạo bean. Nếu environment variable đổi sau khi process đã chạy, RestClient đã tạo không tự động đổi base URL. Cần restart hoặc dùng cơ chế refresh/configuration được hỗ trợ rõ ràng.

### 5.2. Không bind secret vào log

Có thể bind API key vào một properties record riêng:

```java
package com.example.orders.config;

import jakarta.validation.constraints.NotBlank;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@ConfigurationProperties(prefix = "app.payment")
@Validated
public record PaymentProperties(
        @NotBlank String apiKey) {
}
```

Không override `toString()` để in giá trị secret, không log toàn bộ object properties và không đưa API key vào exception message. Khi debug, chỉ log trạng thái đã cấu hình hay chưa, không log nội dung.

## 6. Cấp credentials bằng environment variables

Environment variables là cách phổ biến để truyền cấu hình vào process/container:

```bash
SPRING_DATASOURCE_USERNAME=orders_app
SPRING_DATASOURCE_PASSWORD=replace-at-deploy-time
APP_PAYMENT_APIKEY=replace-at-deploy-time
./orders-service
```

Các giá trị trên chỉ minh họa tên biến. Không commit password thật vào repository hoặc Dockerfile.

Environment variable có một số hạn chế:

- Có thể bị lộ qua process inspection, diagnostics hoặc crash collection tùy nền tảng.
- Dễ bị ghi vào log nếu script in toàn bộ environment.
- Có thể bị lưu trong metadata của deployment hoặc CI job nếu pipeline cấu hình sai.
- Thay environment của container đang chạy thường không thay đổi environment của process đã tồn tại.

Với credential nhạy cảm, ưu tiên secret manager hoặc mounted secret files. Environment variable phù hợp hơn với cấu hình không nhạy cảm như service URL, port và timeout.

## 7. Dùng configuration tree cho Docker/Kubernetes secrets

Spring Boot hỗ trợ prefix `configtree:` để đọc một thư mục mà tên file trở thành property name, còn nội dung file trở thành property value.

Ví dụ cấu trúc volume:

```text
/run/secrets/orders/
├── spring.datasource.username
├── spring.datasource.password
└── app.payment.api-key
```

Trong `application.yaml`:

```yaml
spring:
  config:
    import: "optional:configtree:/run/secrets/orders/"
```

Các file được ánh xạ thành:

| File | Property |
| --- | --- |
| `spring.datasource.username` | `spring.datasource.username` |
| `spring.datasource.password` | `spring.datasource.password` |
| `app.payment.api-key` | `app.payment.api-key` |

Ứng dụng có thể bind các property này như nguồn cấu hình bình thường. Nếu secret là bắt buộc trong production, cần bảo đảm deployment mount đúng và validation từ chối cấu hình thiếu. Không dùng default rỗng cho credential rồi để lỗi chỉ xuất hiện ở request đầu tiên.

Prefix `optional:` cho phép ứng dụng tiếp tục khi thư mục chưa tồn tại. Điều này tiện cho local development, nhưng không thay thế kiểm tra secret bắt buộc ở production. Có thể dùng cấu hình deployment riêng hoặc bỏ `optional:` trong môi trường yêu cầu secret.

### 7.1. Docker secret mount

Ví dụ Docker run mount thư mục secret chỉ đọc:

```bash
docker run --rm -p 8080:8080 -v /secure/orders-secrets:/run/secrets/orders:ro -e SPRING_CONFIG_IMPORT=configtree:/run/secrets/orders/ orders-service:native
```

Đảm bảo các file có owner/permission cho phép UID chạy ứng dụng đọc được. Không copy thư mục secret vào image bằng Dockerfile.

Nếu dùng Docker Compose, có thể mount secret file vào container. Cơ chế quản lý secret phụ thuộc cách triển khai Compose/Swarm; volume mount thông thường không tự biến file thành secret được mã hóa.

## 8. Ví dụ Kubernetes Secret và Deployment

Kubernetes có thể mount Secret thành file trong container. Secret object nên được tạo từ secret manager hoặc quy trình triển khai bảo mật của tổ chức; không commit credentials thật trong manifest.

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders
spec:
  replicas: 2
  selector:
    matchLabels:
      app: orders
  template:
    metadata:
      labels:
        app: orders
    spec:
      containers:
        - name: orders
          image: registry.example.com/orders:1.0.0
          ports:
            - containerPort: 8080
          env:
            - name: SPRING_CONFIG_IMPORT
              value: "optional:configtree:/run/secrets/orders/"
            - name: APP_INVENTORY_BASEURL
              value: "http://inventory-api:8080"
          volumeMounts:
            - name: orders-secrets
              mountPath: /run/secrets/orders
              readOnly: true
      volumes:
        - name: orders-secrets
          secret:
            secretName: orders-runtime
```

Secret volume có thể chứa các key như `spring.datasource.username`, `spring.datasource.password` và `app.payment.api-key`. Khi mount dạng directory, filename trở thành key của config tree.

Một số điểm vận hành:

- Secret volume nên được mount read-only.
- Không bật log dump toàn bộ environment hoặc config properties.
- Cấp quyền đọc vừa đủ cho UID của container.
- Bảo vệ quyền đọc Secret qua RBAC và chính sách namespace.
- Dùng encryption at rest và secret management phù hợp với cluster.
- Không đưa Secret vào image layer, source control hoặc artifact build.

Nếu secret không được mount, validation phải làm ứng dụng fail fast. Không để ứng dụng khởi động với credential rỗng rồi chỉ phát hiện khi có traffic.

## 9. Cấu hình địa chỉ service trong Docker và Kubernetes

Địa chỉ service không nên được đóng cứng vào native binary. Hãy cung cấp qua property runtime, DNS hoặc service discovery.

### 9.1. Docker Compose

Trong Docker Compose, các service cùng network có thể gọi nhau bằng service name:

```yaml
services:
  orders:
    image: orders-service:native
    environment:
      APP_INVENTORY_BASEURL: http://inventory-api:8080
    ports:
      - "8080:8080"
    depends_on:
      - inventory-api

  inventory-api:
    image: inventory-api:latest
    expose:
      - "8080"
```

Tên `inventory-api` được Docker DNS phân giải trong network Compose. Không dùng `localhost` để gọi container khác: bên trong container, localhost trỏ về chính container hiện tại. `depends_on` chỉ điều khiển thứ tự khởi tạo; nó không mặc nhiên bảo đảm service dependency đã sẵn sàng nhận request.

### 9.2. Kubernetes Service DNS

Trong Kubernetes, ứng dụng nên gọi Service name thay vì Pod IP:

- Cùng namespace: `http://inventory-api:8080`.
- Namespace khác: `http://inventory-api.orders:8080`.
- FQDN thường có dạng `inventory-api.orders.svc.cluster.local`.

Cluster domain có thể được tùy chỉnh, vì vậy không giả định hậu tố luôn là `cluster.local`. Dùng DNS name ổn định của Service và để Kubernetes quản lý endpoint Pod.

Pod IP có thể thay đổi khi rollout hoặc reschedule. Không lưu Pod IP vào native build arguments hoặc file cấu hình đóng gói trong image.

### 9.3. localhost trong container

| Nơi chạy client | `localhost` trỏ tới |
| --- | --- |
| Native executable chạy trực tiếp trên host | Host hiện tại |
| Native executable trong Docker container | Container đó |
| Pod trong Kubernetes | Pod network namespace |
| Container gọi service cùng Compose network | Dùng service name, không dùng localhost |

Nếu cần gọi service trên host từ Docker Desktop, có thể có hostname đặc biệt như `host.docker.internal`, nhưng hỗ trợ phụ thuộc nền tảng. Không dùng hostname này như địa chỉ portable cho mọi Linux/container runtime.

## 10. Cấu hình timeout, pool và retry

Một URL đúng chưa đủ để kết nối ổn định. Cần cấu hình:

- Connect timeout: giới hạn thời gian thiết lập kết nối.
- Read/response timeout: giới hạn thời gian chờ phản hồi.
- Connection pool: số kết nối tối đa, thời gian giữ idle và thời gian sống.
- Retry: số lần thử lại, backoff và loại lỗi được phép retry.
- Circuit breaker/bulkhead: cô lập service chậm hoặc lỗi nếu hệ thống dùng.
- TLS: trust anchor, hostname verification và client certificate khi cần.

Không retry mọi request một cách mù quáng. Request ghi dữ liệu có thể đã được server xử lý dù client timeout; retry cần idempotency key hoặc semantics an toàn.

Đặt timeout theo SLO và timeout tổng của request. Tổng thời gian retry không được vượt quá thời gian caller có thể chờ.

```yaml
app:
  inventory:
    base-url: http://inventory-api:8080
    connect-timeout: 2s
    read-timeout: 5s
    max-connections: 40
```

Bind các giá trị thành `Duration` hoặc integer có đơn vị rõ ràng. Đừng để timeout không giới hạn vì một dependency có thể giữ thread/request lâu và làm cạn pool.

## 11. Credentials và TLS certificate

Kết nối tới database hoặc service bảo mật có thể cần:

- Username/password.
- API key hoặc OAuth client secret.
- Client certificate và private key.
- CA certificate hoặc truststore.
- Token endpoint và audience/scope.

Tách credential khỏi URL nếu URL có thể bị log. Không nhúng password vào JDBC URL hoặc HTTP URL. Bind từng property riêng và cấu hình client qua API phù hợp.

Với TLS:

1. Cấp CA certificate/truststore qua secret hoặc volume mount.
2. Đặt đường dẫn runtime và quyền đọc đúng cho container UID.
3. Cấu hình HTTP/JDBC client dùng truststore phù hợp.
4. Giữ hostname verification bật.
5. Nếu dùng mTLS, bảo vệ private key và giới hạn quyền đọc.
6. Kiểm tra handshake bằng native executable trên đúng base image và GraalVM version.

Cơ chế nạp truststore/certificate có thể phụ thuộc JDK, GraalVM, HTTP client và driver. Không suy luận rằng test JVM thành công sẽ bảo đảm native binary dùng cùng truststore. Hãy test TLS handshake từ executable/container được phát hành.

Không tắt certificate validation để sửa nhanh lỗi TLS. Hãy kiểm tra CA chain, hostname, expiry, clock và truststore.


## 12. Secret rotation và thay đổi cấu hình khi process đang chạy

Environment variables được gán khi process/container khởi động. Thay giá trị trong manifest hoặc secret store không thay environment của process đã tồn tại.

Mounted secret files có thể được nền tảng cập nhật theo cơ chế volume, nhưng Spring Boot không tự động bảo đảm mọi bean đã bind, DataSource, connection pool hoặc HTTP client đều được cấu hình lại khi nội dung file thay đổi.

| Thay đổi | Hành vi thường gặp |
| --- | --- |
| Sửa environment variable trong deployment | Cần tạo/restart container để process nhận giá trị mới |
| Cập nhật Secret volume | File có thể được cập nhật; ứng dụng không mặc nhiên refresh bean |
| Đổi URL trong config file | Cần restart hoặc cơ chế refresh được cấu hình rõ |
| Đổi API key trong bean đã bind | Không tự thay đổi nếu bean/client không hỗ trợ refresh |
| Đổi password database | Pool connection hiện có vẫn có thể giữ session dùng credential cũ |
| Đổi DNS record của Service | Kết nối mới có thể dùng DNS mới; connection đang mở vẫn có thể giữ endpoint cũ |

Quy trình rotation an toàn thường gồm:

1. Tạo credential mới ở hệ thống đích.
2. Cho phép credential cũ và mới cùng hoạt động trong khoảng chuyển tiếp nếu hệ thống hỗ trợ.
3. Cập nhật Secret/config.
4. Rollout/restart application hoặc dùng integration refresh đã được kiểm thử.
5. Xác nhận instance mới kết nối thành công.
6. Drain connection cũ và theo dõi error rate.
7. Thu hồi credential cũ sau khi toàn bộ instance đã chuyển.

Nếu dùng Spring Cloud Vault, Spring Cloud Kubernetes hoặc config refresh integration, kiểm tra rõ property nào được refresh và bean/client nào thực sự nhận thay đổi. Đừng giả định native image tự refresh mọi cấu hình khi file thay đổi.

## 13. Profiles và giới hạn của Spring AOT

Spring Boot profiles có thể cung cấp các property khác nhau như database URL, log level hoặc endpoint. Tuy nhiên, Native Image dựa trên closed-world và Spring AOT tạo bean graph trong build process.

Điều đó có nghĩa:

- Có thể externalize các giá trị cấu hình runtime.
- Không nên dựa vào việc bật một profile tùy ý sau build để thêm bean hoặc implementation chưa được AOT xử lý.
- `@Profile` và `@ConditionalOnProperty` có giới hạn khi chúng làm thay đổi bean graph.
- Nếu các môi trường cần bean graph khác nhau, hãy kiểm tra cách hỗ trợ của phiên bản Spring Boot và cân nhắc build artifact riêng cho từng cấu hình AOT.
- Nếu chỉ khác URL, credential, timeout hoặc feature value, ưu tiên externalized properties trên cùng bean graph.

Staging và production có thể dùng cùng native executable nhưng khác `APP_INVENTORY_BASEURL`. Nếu staging dùng mock bean còn production dùng HTTP client bean qua `@Profile`, cần kiểm tra AOT output và test từng artifact/profile theo cấu hình được hỗ trợ.

## 14. Validate cấu hình và fail fast

Cấu hình sai nên được phát hiện ngay khi khởi động thay vì chờ request đầu tiên.

Nên validate:

- URL có scheme/host hợp lệ.
- Port nằm trong phạm vi hợp lệ.
- Timeout dương và không quá lớn.
- Credentials bắt buộc không rỗng.
- File certificate/truststore tồn tại và đọc được.
- Pool size và retry count trong giới hạn.
- Các service bắt buộc có endpoint cấu hình.

Ví dụ kiểm tra properties:

```java
@ConfigurationProperties(prefix = "app.payment")
@Validated
public record PaymentProperties(
        @NotNull URI baseUrl,
        @NotBlank String apiKey,
        @NotNull Duration responseTimeout) {

    @AssertTrue(message = "payment base-url must use HTTPS")
    public boolean isSecureBaseUrl() {
        return baseUrl != null
                && "https".equalsIgnoreCase(baseUrl.getScheme())
                && baseUrl.getHost() != null;
    }
}
```

Ví dụ cần import các constraint `jakarta.validation.constraints.NotBlank`, `NotNull` và `AssertTrue`. Đảm bảo validation starter có trong dependency.

Không đặt giá trị mặc định như `password=changeme` hoặc `api-key=test-key` trong production config. Default dùng cho local development phải được override rõ ràng; secret bắt buộc cần fail fast khi thiếu.

## 15. Readiness và dependency health

Một service có thể khởi động được nhưng chưa thể phục vụ traffic nếu dependency bắt buộc chưa sẵn sàng.

- **Liveness:** process có còn sống và cần tiếp tục chạy không?
- **Readiness:** instance có thể nhận traffic không?
- **Dependency check:** database hoặc remote service có đang hoạt động không?

Không đưa mọi dependency vào liveness probe. Nếu database tạm thời lỗi mà liveness fail, orchestrator có thể restart hàng loạt instance, làm tình trạng nặng hơn.

Readiness có thể phản ánh dependency bắt buộc nếu ứng dụng thực sự không thể xử lý traffic khi dependency đó unavailable. Với dependency tùy chọn hoặc endpoint có fallback, đánh giá theo behavior thực tế.

```yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
  endpoints:
    web:
      exposure:
        include: health
```

Kubernetes có thể dùng readiness probe tới `/actuator/health/readiness`. Hãy cấu hình startup probe nếu native application cần thời gian khởi động đáng kể trong môi trường có resource limit thấp.


## 16. Kiểm tra cấu hình thực tế khi vận hành

Khi ứng dụng kết nối sai endpoint hoặc thiếu credential, cần biết giá trị nào đang được bind mà không làm lộ secret.

1. Xác nhận environment variables có tên đúng.
2. Xác nhận file cấu hình ngoài được mount vào đúng path.
3. Kiểm tra `spring.config.import` và location được truyền trước startup.
4. Kiểm tra quyền đọc file của container UID.
5. Xác nhận property binding và validation.
6. Kiểm tra DNS/service name từ đúng network namespace.
7. Kiểm tra port, TLS handshake và timeout.
8. Kiểm tra connection pool/retry behavior.
9. Đối chiếu startup logs và metrics đã được redact.

Spring Boot Actuator có các endpoint `env` và `configprops` hữu ích khi điều tra property source và binding. Chỉ expose chúng trên management interface được bảo vệ, giới hạn quyền truy cập và bảo đảm secret values được sanitize theo cấu hình/version. Không công khai toàn bộ Environment hoặc config properties ra endpoint không xác thực.

Có thể log thông tin không nhạy cảm như service host, port, timeout và tên profile. Không log password, API key, access token, private key hoặc toàn bộ command line nếu có thể chứa secret.

## 17. Điều tra lỗi thường gặp

| Hiện tượng | Nguyên nhân cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Native executable dùng URL local trong production | Environment variable không bind đúng tên | Kiểm tra relaxed binding và tên biến |
| Config ngoài không được nạp | Dùng sai location/additional-location, path hoặc thiếu dấu `/` cuối | Kiểm tra startup arguments và file mount |
| Missing config file làm process fail | Location được khai báo là bắt buộc | Dùng `optional:` chỉ khi thực sự tùy chọn |
| Password rỗng | Secret chưa mount hoặc key trong config tree sai | Kiểm tra file name, permission và validation |
| Đổi Secret nhưng app vẫn dùng credential cũ | Bean/pool đã bind ở startup và chưa refresh | Rollout/restart hoặc dùng refresh integration đã kiểm thử |
| Kết nối service qua localhost thất bại | Localhost trỏ vào container/Pod hiện tại | Dùng Docker/Kubernetes service DNS |
| Service DNS resolve được nhưng request timeout | Port, NetworkPolicy, TLS hoặc service chưa ready | Kiểm tra network path, endpoint và timeout |
| JVM chạy nhưng native không đọc config | File/resource hoặc native packaging khác nhau | Kiểm tra file ngoài, resource hints và executable runtime |
| Đổi active profile không đổi bean | Bean graph đã được AOT xử lý | Đồng bộ AOT profile hoặc build artifact phù hợp |
| TLS handshake fail trên native | CA/truststore hoặc native client config không tương thích | Kiểm tra certificate chain và test từ binary |
| Actuator cho thấy giá trị khác dự kiến | PropertySource có ưu tiên cao ghi đè | Kiểm tra env, system properties, JSON và CLI |
| Container không đọc được secret | UID/GID hoặc file mode không phù hợp | Điều chỉnh quyền mount tối thiểu cần thiết |

## 18. Quy trình triển khai cấu hình cho native executable

1. Đóng gói native executable/container image bất biến.
2. Đặt default không nhạy cảm trong `application.yaml`.
3. Xác định property nào phải thay đổi theo môi trường.
4. Cấp database URL và service endpoint bằng environment/config file ngoài.
5. Cấp username/password/API key bằng secret manager hoặc config tree.
6. Mount CA/truststore và kiểm tra TLS nếu có.
7. Validate cấu hình khi startup; dừng process nếu thiếu giá trị bắt buộc.
8. Kiểm tra DNS, port và connectivity từ container/Pod.
9. Chờ readiness trước khi nhận traffic.
10. Kiểm tra endpoint nghiệp vụ và dependency quan trọng.
11. Ghi nhận config version/secret version không nhạy cảm để phục vụ audit.
12. Khi rotation, rollout hoặc refresh theo cơ chế đã kiểm thử.
13. Theo dõi error rate, timeout, connection pool và readiness sau deploy.

Cùng một native image có thể được promote qua staging và production nếu bean graph, target platform và native build assumptions tương thích. Mỗi môi trường cung cấp giá trị runtime riêng qua cơ chế cấu hình được quản lý.

## 19. Checklist vận hành

- [ ] Native executable không chứa database password, API key hoặc private key.
- [ ] Runtime config được truyền qua Environment, config data hoặc secret integration.
- [ ] `spring.config.location` và `spring.config.additional-location` được dùng đúng mục đích.
- [ ] Environment variable tuân theo relaxed binding.
- [ ] Cấu hình phức tạp được bind bằng `@ConfigurationProperties`.
- [ ] Validation phát hiện URL, timeout và credential bắt buộc bị thiếu/sai.
- [ ] Secret được cấp từ secret manager hoặc mounted configuration tree.
- [ ] File secret mount read-only và UID ứng dụng có quyền đọc tối thiểu.
- [ ] Secret không xuất hiện trong command line, log, Dockerfile hoặc CI output.
- [ ] Service address dùng DNS/service discovery ổn định, không dùng Pod IP cố định.
- [ ] Không dùng localhost để gọi container/Pod khác.
- [ ] Connect/read timeout, pool và retry được cấu hình theo SLO.
- [ ] TLS truststore/certificate được kiểm tra trên native executable thật.
- [ ] Bean graph/profile tương thích với Spring AOT build.
- [ ] Secret rotation có quy trình restart/refresh và drain connection.
- [ ] Readiness và liveness được cấu hình theo mục đích khác nhau.
- [ ] Actuator management endpoints được bảo vệ và redact secret.
- [ ] Sau deploy có smoke test và theo dõi error rate/timeout.

### Câu hỏi tự đánh giá

1. Vì sao database URL có thể đổi lúc runtime nhưng native executable không thể nạp một JAR driver mới sau deploy?
2. Thứ tự ưu tiên của config file, environment variables và command-line arguments ảnh hưởng thế nào khi cùng khai báo một property?
3. Khác biệt giữa `spring.config.location` và `spring.config.additional-location` là gì?
4. Vì sao `@ConfigurationProperties` phù hợp với cấu hình nhiều thuộc tính hơn nhiều `@Value` rời rạc?
5. `configtree:` ánh xạ tên file và nội dung file thành property như thế nào?
6. Vì sao không nên truyền password qua command-line argument hoặc ghi vào Dockerfile?
7. Trong Docker/Kubernetes, `localhost` trỏ tới đâu và nên dùng địa chỉ nào để gọi service khác?
8. Vì sao thay Secret volume không bảo đảm DataSource hoặc HTTP client đã bind sẽ tự đổi credential?
9. Spring AOT giới hạn việc thay đổi bean graph bằng profile/conditional property ra sao?
10. Readiness và liveness probe nên phản ánh những trạng thái nào?
11. Khi native TLS handshake thất bại, cần kiểm tra những yếu tố nào?
12. Làm thế nào để xác minh property đang được bind mà không log secret?

## Tài liệu tham khảo

- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): PropertySource precedence, file ngoài, environment variables, `spring.config.import` và configuration trees.
- [Spring Boot — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties): binding, validation và relaxed binding.
- [Spring Boot — GraalVM Native Images](https://docs.spring.io/spring-boot/reference/packaging/native-image/introducing-graalvm-native-images.html): closed-world, classpath cố định và giới hạn Spring AOT.
- [Spring Boot — Application Availability](https://docs.spring.io/spring-boot/reference/features/spring-application.html): startup, liveness và readiness.
- [Kubernetes — Secrets](https://kubernetes.io/docs/concepts/configuration/secret/): tạo, mount và quản lý Secret trong Pod.
- [Docker — Secrets](https://docs.docker.com/engine/swarm/secrets/): cấp secret cho service qua file mount.

**Kết quả cần đạt:** có thể chạy cùng một Spring Boot Native Image ở nhiều môi trường bằng cách cung cấp database URL, credentials, service address, timeout và certificate lúc runtime; biết validate cấu hình khi startup, hiểu giới hạn bean graph do AOT và có quy trình an toàn cho secret rotation, DNS/service discovery và readiness.

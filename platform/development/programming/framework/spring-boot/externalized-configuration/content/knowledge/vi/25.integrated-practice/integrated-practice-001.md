# Khởi tạo ứng dụng mẫu có nhóm cấu hình kết nối dịch vụ bên ngoài — Spring Boot 3.3

## 1. Mục tiêu thực hành

Bài thực hành tạo một ứng dụng **Spring Boot 3.3 / Java 17 / Maven** có nhiệm vụ gọi một **dịch vụ Catalog bên ngoài** qua HTTP. Ứng dụng phải đọc toàn bộ thông tin kết nối từ cấu hình bên ngoài thay vì hard-code vào service:

- URL gốc của đối tác.
- API key dùng trong request header.
- Connection timeout và read timeout.
- Cờ bật/tắt tích hợp.
- Cách override giá trị khi triển khai local, staging và production.

Nhóm cấu hình ví dụ:

```yaml
integrations:
  catalog:
    base-url: "http://localhost:9091"
    enabled: true
    auth:
      api-key: "..."              # không đưa key thật vào Git
    timeouts:
      connect: 2s
      read: 5s
```

Sau khi hoàn thành, luồng hoạt động là:

```text
GET http://localhost:8080/demo/products/p-100
              |
              v
     CatalogController
              |
              v
       CatalogClient
              |
              v
    RestClient đã cấu hình
    - baseUrl
    - X-Api-Key
    - connect timeout
    - read timeout
              |
              v
GET http://localhost:9091/products/p-100
              |
              v
        JSON ProductDto
              |
              v
  Trả kết quả về HTTP caller
```

Trong đó `CatalogClient` và `RestClient` là các thành phần do Spring quản lý; dữ liệu kết nối được đóng gói trong một bean `CatalogProperties` kiểu immutable.

**Kết quả học tập:** biết tạo nhóm property có cấu trúc lồng nhau, đăng ký và validate `@ConfigurationProperties`, xây một outbound client tách khỏi controller, dùng environment/profile/secret để thay giá trị theo deployment, và kiểm thử mà không cần gửi request đến dịch vụ bên ngoài thật.

Tất cả host, API key và dữ liệu sản phẩm trong bài là **giả lập**. Không sử dụng endpoint thật hoặc credential production trong ví dụ.

## 2. Vì sao phải gom cấu hình kết nối thành một nhóm?

Một cách viết ban đầu thường gặp:

```java
@Service
public class OldCatalogService {

    private static final String BASE_URL =
            "https://partner.example.internal";
    private static final String API_KEY = "example-key";

    // Gọi HTTP bằng URL và token viết trực tiếp trong code
}
```

Cách làm này gặp nhiều vấn đề:

1. Muốn đổi URL giữa local/staging/prod phải sửa hoặc build lại code.
2. API key dễ bị đưa vào source control, Docker image hoặc log.
3. Timeout khó điều chỉnh theo độ trễ mạng của mỗi môi trường.
4. Không có một nơi thống nhất để validate giá trị bắt buộc.
5. Test phải sửa code hoặc dùng hack để thay địa chỉ đối tác.
6. Khi tích hợp nhiều dịch vụ, hàng chục `@Value` rải trong service rất khó quản lý.

Cách tốt hơn là xác định một **contract cấu hình**:

```text
integrations.catalog
    ├── base-url
    ├── enabled
    ├── auth
    │   └── api-key
    └── timeouts
        ├── connect
        └── read
```

Mỗi field thuộc đúng một nhóm và một Java type; Spring Boot Binder sẽ liên kết giá trị từ `application.yaml`, environment variables, JVM properties, CLI, Config Data imports hoặc những PropertySources phù hợp.

### 2.1. Tách dữ liệu cấu hình khỏi hành vi

`CatalogProperties` chỉ nên mô tả kết nối, constraints và default. Nó **không** tự mở socket, tạo thread, gọi HTTP hoặc inject các service khác.

`CatalogClientConfiguration` có nhiệm vụ tạo `RestClient` từ properties; `CatalogClient` gọi upstream; `CatalogController` nhận request nội bộ.

Sự phân tách này giúp test từng phần mà không phụ thuộc một môi trường triển khai cụ thể.

## 3. Công nghệ và phiên bản

Bộ công nghệ mẫu:

| Thành phần | Sử dụng |
| --- | --- |
| Java | 17 trở lên, phù hợp Spring Boot 3.3 |
| Spring Boot | Dòng 3.3.x |
| Spring Framework | Dòng 6.1 do Boot 3.3 quản lý |
| Maven | Maven Wrapper nếu tạo bằng Spring Initializr |
| HTTP inbound | `spring-boot-starter-web` (Spring MVC) |
| HTTP outbound | `RestClient` — API blocking |
| Binding | `@ConfigurationProperties` + `@ConfigurationPropertiesScan` |
| Validation | `spring-boot-starter-validation` |
| Metadata IDE | `spring-boot-configuration-processor` |
| Test | `spring-boot-starter-test`, JUnit 5, AssertJ, mock HTTP |

Bài dùng `RestClient` vì là ứng dụng Spring MVC blocking. Nếu dự án sử dụng reactive stack/WebFlux và muốn non-blocking, có thể dùng `WebClient`; không tự thay thành WebClient trong mẫu khi chưa có nhu cầu.

**Lưu ý phiên bản:** ví dụ POM phía dưới dùng Spring Boot `3.3.13`, là một patch thuộc dòng 3.3 được trang tài liệu tham khảo 3.3 hiển thị. Với dự án thực tế hãy dùng bản patch phù hợp với policy, repository và bản vá bảo mật đang được tổ chức hỗ trợ; không trộn dependency Spring Framework thủ công khác dòng.

## 4. Tạo project bằng Spring Initializr

Có thể tạo dự án từ https://start.spring.io với những lựa chọn:

```text
Project: Maven
Language: Java
Spring Boot: 3.3.x (nếu lựa chọn này còn được cung cấp)
Group: com.example
Artifact: catalog-demo
Name: catalog-demo
Package: com.example.catalogdemo
Packaging: Jar
Java: 17

Dependencies:
- Spring Web
- Validation
- Spring Boot Actuator (tùy chọn)
- Spring Configuration Processor
- Spring Boot Starter Test
```

Nếu Initializr chỉ cung cấp các bản mới hơn, tạo skeleton Java/Maven rồi đặt parent version ở POM theo chính sách dùng Spring Boot 3.3 của bài. Không mặc định template mới nhất đã tương thích cú pháp/behavior của 3.3.

### 4.1. pom.xml mẫu

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="
           http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>catalog-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <name>catalog-demo</name>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-configuration-processor</artifactId>
            <optional>true</optional>
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
```

Maven parent quản lý phiên bản các Spring starters, Jakarta Validation, Jackson, JUnit và Spring Framework tương ứng. Không cần khai báo `spring-web` version thủ công.

Nếu dùng Java 21 thay cho Java 17, vẫn cần kiểm tra compatibility của tất cả libraries theo dự án; bài này chọn Java 17 để ví dụ rõ.

### 4.2. Vai trò từng dependency

- `starter-web`: Spring MVC inbound, Jackson JSON serialization và API `RestClient` qua `spring-web`.
- `starter-validation`: Jakarta Bean Validation provider, giúp `@Validated` và constraint annotations có hiệu lực.
- `starter-test`: JUnit Jupiter, AssertJ, Spring Boot test utilities và Spring HTTP mock test.
- `configuration-processor`: sinh `META-INF/spring-configuration-metadata.json` cho IDE. **Không phải dependency bắt buộc để Binder hoạt động runtime.**

## 5. Cấu trúc thư mục dự án

```text
catalog-demo/
├── pom.xml
├── .gitignore
├── mvnw
├── mvnw.cmd
└── src/
    ├── main/
    │   ├── java/com/example/catalogdemo/
    │   │   ├── CatalogDemoApplication.java
    │   │   ├── config/
    │   │   │   ├── CatalogProperties.java
    │   │   │   └── CatalogClientConfiguration.java
    │   │   ├── catalog/
    │   │   │   ├── ProductDto.java
    │   │   │   ├── CatalogClient.java
    │   │   │   ├── CatalogController.java
    │   │   │   └── CatalogErrorHandler.java
    │   └── resources/
    │       ├── application.yaml
    │       └── application-prod.yaml
    └── test/
        └── java/com/example/catalogdemo/
            ├── config/CatalogPropertiesTest.java
            └── catalog/CatalogClientTest.java

mock_catalog.py             # tùy chọn, fake upstream local
```

Có thể viết các class trong ít file hơn, nhưng tách như trên giúp code được tổ chức theo trách nhiệm: `config` chỉ cấu hình và HTTP factory, `catalog` chứa thao tác nghiệp vụ.

**Quy ước package:** ứng dụng main `com.example.catalogdemo` là parent của các package con; nhờ vậy `@ConfigurationPropertiesScan` và component scanning tìm được các thành phần ví dụ.

## 6. Tạo Spring Boot application

File:

```text
src/main/java/com/example/catalogdemo/CatalogDemoApplication.java
```

Nội dung:

```java
package com.example.catalogdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class CatalogDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(CatalogDemoApplication.class, args);
    }
}
```

`@SpringBootApplication` bật auto-configuration, component scanning và cấu hình cần thiết. `@ConfigurationPropertiesScan` tìm các class có `@ConfigurationProperties` trong package của ứng dụng và các subpackages.

**Không đánh dấu `CatalogProperties` là `@Component` trong mô hình record constructor binding này.** Spring Boot 3.3 yêu cầu các constructor-bound configuration properties được đăng ký qua configuration properties scanning hoặc `@EnableConfigurationProperties`; không tạo record đó bằng một `@Bean` method thông thường rồi kỳ vọng constructor binding xảy ra giống hệt.

Nếu dùng `@EnableConfigurationProperties(CatalogProperties.class)` thay cho scan, hãy chỉ chọn một cách đăng ký chính trong bài để tránh khó hiểu.

## 7. Mô hình cấu hình immutable: CatalogProperties

File:

```text
src/main/java/com/example/catalogdemo/config/CatalogProperties.java
```

Nội dung:

```java
package com.example.catalogdemo.config;

import java.net.URI;
import java.time.Duration;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "integrations.catalog")
public record CatalogProperties(
        @NotNull URI baseUrl,
        @DefaultValue("true") boolean enabled,
        @Valid @NotNull Auth auth,
        @Valid @NotNull Timeouts timeouts) {

    public record Auth(
            @NotBlank String apiKey) {
    }

    public record Timeouts(
            @NotNull @DefaultValue("2s") Duration connect,
            @NotNull @DefaultValue("5s") Duration read) {
    }
}
```

### 7.1. Giải thích kiểu Java

| Property canonical | Java component | Ý nghĩa |
| --- | --- | --- |
| `integrations.catalog.base-url` | `URI baseUrl` | Địa chỉ gốc dịch vụ ngoài |
| `integrations.catalog.enabled` | `boolean enabled` | Có bật tích hợp hay không |
| `integrations.catalog.auth.api-key` | `Auth.apiKey` (String) | API key cho request |
| `integrations.catalog.timeouts.connect` | `Timeouts.connect` (Duration) | Chờ thiết lập kết nối |
| `integrations.catalog.timeouts.read` | `Timeouts.read` (Duration) | Chờ đọc dữ liệu từ server |

Dùng `URI` thay vì String để tách phần nào việc kiểm tra cú pháp địa chỉ khỏi HTTP client. Tuy nhiên, một URI hợp lệ về cú pháp **chưa chắc** có scheme `http/https` hoặc host thực sự truy cập được; nếu cần ràng buộc đó, dùng thêm custom validation hoặc checks khi khởi tạo client.

Dùng `Duration` cho timeout để cấu hình có thể biểu diễn `500ms`, `2s`, `1m` rõ ràng. Không nên lưu mọi timeout dạng `int` mà không có mô tả đơn vị.

### 7.2. Constructor binding của record

Record có một canonical constructor, nên Spring Boot 3.3 có thể bind theo tên components. Không cần viết setter; object được tạo bất biến ở mức reference.

`@DefaultValue("true")` và `@DefaultValue("2s")` là giá trị mặc định ở **binding constructor** nếu field con không có property. Điều này khác với metadata `defaultValue` chỉ dành cho IDE.

**Nuance quan trọng:** Nếu toàn bộ nhóm `timeouts` không được cung cấp, nested record `Timeouts` có thể là `null`; `@DefaultValue` ở các components con không nhất thiết khiến cả nhóm nested được tạo. Trong ví dụ, `@NotNull` trên `timeouts` làm thiếu toàn bộ nhóm trở thành lỗi rõ ràng khi Bean Validation hoạt động.

### 7.3. Validation

- `@Validated` yêu cầu Spring Boot xem xét Bean Validation cho configuration properties bean.
- `@NotNull` ngăn thiếu `baseUrl`, `auth` hoặc `timeouts`.
- `@NotBlank` ngăn API key null, chuỗi rỗng hoặc chỉ có whitespace.
- `@Valid` yêu cầu cascade validation vào nested record `Auth` và `Timeouts`.

Nếu không có provider Bean Validation trên classpath, constraints có thể không chạy như mong đợi. Vì vậy đã thêm `spring-boot-starter-validation` trong POM.

**Cảnh báo:** `@NotNull` trên `Duration` không cấm `0s` hoặc duration âm. Một HTTP client có thể diễn giải zero là *infinite timeout*; nên bổ sung kiểm tra duration dương nếu đó là hợp đồng vận hành, ví dụ với một custom Bean Validation constraint hoặc kiểm tra rõ tại bean factory.

### 7.4. Không đưa logic HTTP vào record

Sai trách nhiệm:

```java
public record CatalogProperties(...) {
    public ProductDto fetchProduct(...) {
        // Tự gọi HTTP trong object chỉ nên chứa cấu hình
    }
}
```

Đúng trách nhiệm:

```text
CatalogProperties (dữ liệu)
       |
       v
CatalogClientConfiguration (tạo client)
       |
       v
CatalogClient (gọi HTTP)
       |
       v
CatalogController (HTTP inbound)
```

Cách này giữ configuration class dễ test, không có side effect lúc binding và không buộc binder phải inject service vào constructor.

## 8. Khai báo cấu hình mặc định trong application.yaml

File:

```text
src/main/resources/application.yaml
```

Nội dung:

```yaml
server:
  port: 8080

spring:
  application:
    name: catalog-demo

integrations:
  catalog:
    base-url: "http://127.0.0.1:9091"
    enabled: true
    auth:
      api-key: "${CATALOG_API_KEY:}"
    timeouts:
      connect: 2s
      read: 5s
```

**Vì sao API key dùng placeholder?** Giá trị thật không nằm trong file version-controlled; nó được cấp từ environment variable `CATALOG_API_KEY`. Nếu không có env var, placeholder dùng default rỗng, rồi `@NotBlank` khiến ứng dụng **fail-fast** khi bean cấu hình được tạo.

Đây là chính sách phù hợp với bài thực hành **bắt buộc luôn có key khi service khởi động**, kể cả ở local (dùng key giả). Một cách triển khai khác là không đặt `auth.api-key` trong YAML và cấp trực tiếp canonical env var `INTEGRATIONS_CATALOG_AUTH_APIKEY`.

### 8.1. Hai cách cung cấp key

**Cách A — Biến alias được tham chiếu trong YAML:**

```bash
CATALOG_API_KEY=local-demo-key
```

Tương ứng placeholder:

```yaml
api-key: "${CATALOG_API_KEY:}"
```

**Cách B — OS env trùng canonical property:**

```bash
INTEGRATIONS_CATALOG_AUTH_APIKEY=local-demo-key
```

Cách B thường override trực tiếp property từ Config Data theo Spring Boot PropertySource order. Không cần vừa đặt cả hai biến, vừa lưu bản sao giá trị ở file trừ khi có yêu cầu rõ ràng.

**Quy tắc tên env var canonical:**

```text
integrations.catalog.auth.api-key
  -> INTEGRATIONS_CATALOG_AUTH_APIKEY
```

Thay dot bằng underscore, bỏ dash và uppercase. `INTEGRATIONS_CATALOG_AUTH_API_KEY` không phải dạng chuyển tên canonical được Boot 3.3 khuyến nghị.

### 8.2. Không đặt API key production trong Git

Không nên làm:

```yaml
integrations:
  catalog:
    auth:
      api-key: "real-production-secret"
```

Dù repository riêng tư, secret có thể xuất hiện trong lịch sử Git, artifact, CI logs, bản sao triển khai hoặc backup. Sử dụng cơ chế cấp phát secret được tổ chức phê duyệt, ví dụ environment từ Secret manager hoặc secret volume + Config Data `configtree:`.

## 9. Config Data và override theo môi trường

Spring Boot có thứ tự PropertySource mặc định: Config Data (application files) thấp hơn OS environment, và OS environment thấp hơn JVM system properties và command-line arguments theo các nguồn tương ứng.

Ví dụ file:

```properties
integrations.catalog.timeouts.read=5s
```

Environment:

```bash
INTEGRATIONS_CATALOG_TIMEOUTS_READ=8s
```

Kết quả khi bind thường là **8 giây** nếu không có nguồn cao hơn ghi đè.

Trong Spring Boot 3.3:

- `integrations.catalog.timeouts.read` → `INTEGRATIONS_CATALOG_TIMEOUTS_READ`.
- `integrations.catalog.base-url` → `INTEGRATIONS_CATALOG_BASEURL`.
- `integrations.catalog.enabled` → `INTEGRATIONS_CATALOG_ENABLED`.
- `integrations.catalog.auth.api-key` → `INTEGRATIONS_CATALOG_AUTH_APIKEY`.

### 9.1. Ví dụ chạy production

```bash
CATALOG_API_KEY=... \
INTEGRATIONS_CATALOG_BASEURL=https://catalog.partner.example \
INTEGRATIONS_CATALOG_TIMEOUTS_CONNECT=3s \
INTEGRATIONS_CATALOG_TIMEOUTS_READ=8s \
java -jar target/catalog-demo-0.0.1-SNAPSHOT.jar
```

Các dấu ba chấm tượng trưng cho secret; lệnh này chỉ là **mô tả biến cần cấp**, không phải khuyến nghị đưa giá trị thật lên shell history. Với production, dùng hệ thống cấp phát secret và runtime environment thích hợp.

### 9.2. Profile-specific configuration

Có thể tạo:

```text
src/main/resources/application-prod.yaml
```

```yaml
integrations:
  catalog:
    base-url: "https://catalog.partner.example"
    timeouts:
      connect: 3s
      read: 8s
```

Kích hoạt:

```bash
SPRING_PROFILES_ACTIVE=prod
```

Spring Boot nạp file profile tương ứng, ghi đè những property được định nghĩa trong Config Data theo quy tắc profile. Tuy nhiên, OS environment cùng key thường vẫn có ưu tiên cao hơn file `application-prod.yaml`. Đừng xem tên file "prod" là bảo đảm nó thắng mọi nguồn.

### 9.3. Không trộn quá nhiều nguồn

Nếu API key có thể xuất hiện đồng thời trong:

1. `application-prod.yaml`.
2. Docker/Kubernetes Secret volume.
3. OS environment.
4. `SPRING_APPLICATION_JSON`.
5. CLI `--integrations.catalog.auth.api-key=...`.

thì rất khó xác định credential nào đang có hiệu lực và vòng đời rotation của nó. Chọn một **source of truth vận hành**, hạn chế override không có chủ đích, và kiểm soát quyền thay deployment.

## 10. Tạo RestClient từ CatalogProperties

Spring Boot 3.3 có auto-configured prototype bean `RestClient.Builder` khi sử dụng Spring Web theo cấu hình phù hợp. Nên inject builder thay vì tự gọi `RestClient.create()` mọi nơi để giữ những message converters/customizers được Boot chuẩn bị.

File:

```text
src/main/java/com/example/catalogdemo/config/CatalogClientConfiguration.java
```

Nội dung:

```java
package com.example.catalogdemo.config;

import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
public class CatalogClientConfiguration {

    @Bean("catalogRestClient")
    RestClient catalogRestClient(
            RestClient.Builder builder,
            CatalogProperties properties) {

        Duration connect = properties.timeouts().connect();
        Duration read = properties.timeouts().read();

        if (connect.isZero() || connect.isNegative()
                || read.isZero() || read.isNegative()) {
            throw new IllegalArgumentException(
                    "Catalog timeouts must be positive");
        }

        SimpleClientHttpRequestFactory factory =
                new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(connect);
        factory.setReadTimeout(read);

        return builder
                .baseUrl(properties.baseUrl().toString())
                .requestFactory(factory)
                .defaultHeader(
                    "X-Api-Key", properties.auth().apiKey())
                .build();
    }
}
```

### 10.1. Vì sao tự chọn SimpleClientHttpRequestFactory?

`RestClient.Builder` do Spring Boot cung cấp có thể đã có HTTP request factory được chọn tự động từ classpath và cấu hình. Trong bài, ta **cố ý** dùng `SimpleClientHttpRequestFactory` để minh họa trực tiếp hai timeout theo `Duration` bằng các API của Spring Framework 6.1.

Các method `setConnectTimeout(Duration)` và `setReadTimeout(Duration)` có sẵn trên Spring Framework 6.1 `SimpleClientHttpRequestFactory`. Chúng dựa trên `HttpURLConnection`; đây là giải pháp dễ hiểu cho bài học, **không phải khuyến nghị tuyệt đối** cho mọi ứng dụng có lượng request lớn, HTTP/2 hoặc yêu cầu connection pooling chuyên biệt.

Trong môi trường production, có thể dùng Apache HttpComponents, JDK HttpClient request factory hoặc client khác tùy nhu cầu; khi đổi factory cần kiểm tra semantics của timeout, pooling, proxy, TLS và retry theo client thực tế.

### 10.2. Hai loại timeout không giống nhau

| Cấu hình | Ví dụ | Điều kiểm soát |
| --- | --- | --- |
| `timeouts.connect` | `2s` | Thời gian chờ thiết lập kết nối |
| `timeouts.read` | `5s` | Thời gian chờ đọc dữ liệu từ kết nối theo request factory |
| End-to-end deadline | Chưa triển khai trong ví dụ | Tổng thời gian request, DNS, connect, response và retry theo thiết kế riêng |
| Retry policy | Chưa triển khai | Có thử gửi lại request hay không |

Đừng nhầm `readTimeout=5s` với lời hứa **toàn bộ request chắc chắn kết thúc trong 5 giây**. Semantics của timeout phụ thuộc HTTP stack, giai đoạn thực hiện, DNS và hành vi downstream.

### 10.3. Timeout bằng 0 là một bẫy

Với `SimpleClientHttpRequestFactory`, timeout bằng 0 có thể mang nghĩa **không giới hạn thời gian chờ** ở API dưới. Vì vậy bean factory trong ví dụ từ chối giá trị zero hoặc âm.

Nếu muốn chính sách khác, thay kiểm tra có chủ đích và viết test cho các giá trị biên. Không sử dụng `0s` chỉ với giả định nó nghĩa là "không chờ".

### 10.4. Một RestClient nên có identity rõ

Tên bean:

```java
@Bean("catalogRestClient")
```

cho phép phân biệt với outbound clients khác như `billingRestClient` hoặc `inventoryRestClient` nếu sau này ứng dụng tích hợp thêm đối tác.

Khi chỉ có một `RestClient` bean cũng có thể injection theo type. Nhưng viết qualifier rõ giúp tránh lỗi ambiguous dependency khi thêm dịch vụ thứ hai.

### 10.5. Header chứa secret

`defaultHeader("X-Api-Key", properties.auth().apiKey())` sẽ gắn API key vào request được thực hiện bằng client này trừ khi request overrides theo semantics builder/client.

Không log cả RestClient builder, các request headers hoặc `CatalogProperties`. Cũng không in secret khi một upstream trả lỗi 401/403; chỉ cần log tên upstream, status code, correlation ID và dữ liệu không nhạy cảm.

Nếu chính sách đối tác sử dụng Bearer token thay vì `X-Api-Key`, cần thay đúng scheme và yêu cầu của API thật (ví dụ `Authorization: Bearer ...`), không tự mặc định header minh họa phù hợp mọi nhà cung cấp.

## 11. Tạo model kết quả ProductDto

File:

```text
src/main/java/com/example/catalogdemo/catalog/ProductDto.java
```

```java
package com.example.catalogdemo.catalog;

public record ProductDto(
        String id,
        String name,
        int stock) {
}
```

Mô phỏng JSON trả về:

```json
{
  "id": "p-100",
  "name": "Notebook",
  "stock": 12
}
```

Spring Web starter đã cung cấp message converters thông thường với Jackson để chuyển JSON response thành `ProductDto`. Với API thật, DTO phải phản ánh JSON schema, version contract và nullability của bên ngoài. Nếu API dùng tên khác như `product_id`, dùng Jackson annotation hoặc DTO mapping được khai báo rõ.

**Không dùng entity JPA** trực tiếp làm outbound DTO chỉ vì có các field trùng tên. Việc tách DTO bảo vệ hệ thống nội bộ khỏi thay đổi schema của đối tác.

## 12. Viết CatalogClient gọi dịch vụ bên ngoài

File:

```text
src/main/java/com/example/catalogdemo/catalog/CatalogClient.java
```

```java
package com.example.catalogdemo.catalog;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
public class CatalogClient {

    private final RestClient client;

    public CatalogClient(
            @Qualifier("catalogRestClient") RestClient client) {
        this.client = client;
    }

    public ProductDto getProduct(String id) {
        ProductDto product = client
                .get()
                .uri("/products/{id}", id)
                .retrieve()
                .body(ProductDto.class);

        if (product == null) {
            throw new IllegalStateException(
                    "Catalog service returned an empty body");
        }
        return product;
    }
}
```

### 12.1. Giải thích HTTP call

- `.get()`: outbound HTTP GET.
- `.uri("/products/{id}", id)`: xây URI có path variable thay vì nối chuỗi URL thủ công.
- `.retrieve()`: lấy response qua RestClient response handling.
- `.body(ProductDto.class)`: giải mã JSON thành record theo converter phù hợp.

Nếu upstream trả 4xx hoặc 5xx, `retrieve()` mặc định có thể ném `RestClientResponseException` hoặc subtype thay vì trả DTO thành công. Nếu kết nối timeout hoặc không tới được upstream, có thể gặp `ResourceAccessException`; cần xử lý ở boundary phù hợp.

### 12.2. Không xây URL bằng String concatenation

Nên dùng:

```java
.uri("/products/{id}", id)
```

thay vì:

```java
.uri("/products/" + id)
```

vì template variables giúp code biểu diễn rõ cấu trúc URI và cách encode đường dẫn. Với parameter chứa slash, dấu cách hoặc ký tự đặc biệt, vẫn cần hiểu semantics của encoding và contract của downstream path; không coi template là phương án thay thế validation.

### 12.3. Service không cần đọc Environment nữa

Một lỗi thiết kế:

```java
String url = System.getenv("CATALOG_URL");
String apiKey = System.getenv("CATALOG_API_KEY");
```

được lặp lại trong từng method outbound. Cách này bỏ qua nhóm configuration properties, khó test profile/default/precedence và có thể tạo nhiều nguồn sự thật.

Đúng hơn, `CatalogClient` nhận `RestClient` đã được cấu hình, không cần biết giá trị kết nối đến từ YAML, Docker, Kubernetes hay Secret manager.

## 13. Tạo HTTP endpoint nội bộ để thử client

File:

```text
src/main/java/com/example/catalogdemo/catalog/CatalogController.java
```

```java
package com.example.catalogdemo.catalog;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/demo/products")
public class CatalogController {

    private final CatalogClient catalogClient;

    public CatalogController(CatalogClient catalogClient) {
        this.catalogClient = catalogClient;
    }

    @GetMapping("/{id}")
    public ProductDto getProduct(@PathVariable String id) {
        return catalogClient.getProduct(id);
    }
}
```

Khi gọi:

```http
GET /demo/products/p-100 HTTP/1.1
Host: localhost:8080
```

controller gọi CatalogClient, CatalogClient gọi `GET /products/p-100` ở upstream. Bài này **cố ý để endpoint nội bộ không có auth** để minh họa binding/client. Trước khi public ra Internet, phải thêm authentication/authorization, input validation, rate limiting và chính sách truy cập phù hợp; không đưa controller mẫu lên production công khai như một API an toàn mặc định.

## 14. Xử lý lỗi upstream rõ ràng

Không nên để lỗi kết nối từ đối tác lẫn với lỗi cấu hình khởi động. Có thể đặt một `@RestControllerAdvice` để trả mã HTTP dễ hiểu mà không phơi lộ body upstream hoặc credential.

File:

```text
src/main/java/com/example/catalogdemo/catalog/CatalogErrorHandler.java
```

```java
package com.example.catalogdemo.catalog;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClientResponseException;

@RestControllerAdvice
public class CatalogErrorHandler {

    public record ErrorMessage(
            String code,
            String message) {
    }

    @ExceptionHandler(RestClientResponseException.class)
    public ResponseEntity<ErrorMessage> upstreamHttpError(
            RestClientResponseException ex) {
        return ResponseEntity.status(HttpStatus.BAD_GATEWAY)
                .body(new ErrorMessage(
                        "UPSTREAM_HTTP_ERROR",
                        "External catalog returned an error"));
    }

    @ExceptionHandler(ResourceAccessException.class)
    public ResponseEntity<ErrorMessage> upstreamNetworkError(
            ResourceAccessException ex) {
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                .body(new ErrorMessage(
                        "UPSTREAM_UNAVAILABLE",
                        "External catalog is temporarily unavailable"));
    }
}
```

Đây là mapping tối giản dành cho demo. Trong production, 404 từ upstream có thể có ý nghĩa "sản phẩm không tồn tại", 429 nghĩa là rate-limited, 401/403 nghĩa là lỗi credential/authorization, 5xx là upstream failure; có thể cần chiến lược phân loại riêng thay vì map mọi status thành 502.

### 14.1. Tránh làm lộ secret và thông tin nội bộ

Không trả về nguyên:

```java
ex.getResponseBodyAsString()
```

cho client bên ngoài nếu upstream response có thể chứa thông tin nhạy cảm. Không dump headers vì `Authorization` hoặc `X-Api-Key` có thể nằm trong request context/logging. Error response nên có mã lỗi ổn định, correlation ID và lời nhắn ngắn đã được chuẩn hóa.

### 14.2. Validation lỗi ngay khi startup

Nếu `CatalogProperties` thiếu `api-key`, startup có thể thất bại ở `ConfigurationPropertiesBindException` / validation failure trước khi controller chạy. Đó là lỗi **cấu hình**, không phải "upstream temporarily unavailable".

Cách xử lý đúng là cung cấp secret đúng và restart/rollout, không phải catch exception trong mỗi HTTP method để che lỗi cấu hình.

## 15. Tạo upstream giả để chạy thực hành local

Nếu chưa có dịch vụ Catalog thật, có thể dùng một HTTP server giả bằng **Python standard library**. Nó chỉ phục vụ học tập; không chứa secret thật, không dùng trên mạng production.

Tạo file:

```text
mock_catalog.py
```

```python
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import unquote, urlparse


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlparse(self.path).path

        if not path.startswith("/products/"):
            self.send_response(404)
            self.end_headers()
            return

        # Chỉ là dummy key trong môi trường thử nghiệm.
        if self.headers.get("X-Api-Key") != "local-demo-key":
            self.send_response(401)
            self.end_headers()
            return

        product_id = unquote(path.removeprefix("/products/"))
        data = {
            "id": product_id,
            "name": "Notebook",
            "stock": 12,
        }
        body = json.dumps(data).encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    HTTPServer(("127.0.0.1", 9091), Handler).serve_forever()
```

Chạy upstream trong terminal thứ nhất:

```bash
python3 mock_catalog.py
```

Trên Windows có thể dùng:

```powershell
py -3 mock_catalog.py
```

Nếu Python phiên bản cũ không có `str.removeprefix`, dùng Python 3.9 trở lên hoặc thay bằng slicing. Server giả gắn vào `127.0.0.1` để tránh vô tình mở cho máy bên ngoài.

### 15.1. Kiểm tra upstream trước

```bash
curl -i -H "X-Api-Key: local-demo-key" \
  http://127.0.0.1:9091/products/p-100
```

Đầu ra mong đợi:

```http
HTTP/1.0 200 OK
Content-Type: application/json

{"id":"p-100","name":"Notebook","stock":12}
```

Thứ tự headers và chi tiết output có thể khác, nhưng HTTP status và JSON fields là điều quan trọng. Không cần kỳ vọng đúng mọi byte như ví dụ.

### 15.2. Chạy Spring Boot application

Terminal thứ hai trên Linux/macOS:

```bash
export CATALOG_API_KEY=local-demo-key
./mvnw spring-boot:run
```

Hoặc dùng Maven hệ thống:

```bash
mvn spring-boot:run
```

Trên Windows PowerShell:

```powershell
$env:CATALOG_API_KEY = "local-demo-key"
.\mvnw.cmd spring-boot:run
```

Với file `application.yaml` ở phần 8, app sẽ:

- Bind `baseUrl = http://127.0.0.1:9091`.
- Bind `auth.apiKey = local-demo-key`.
- Bind `timeouts.connect = 2s`.
- Bind `timeouts.read = 5s`.
- Tạo RestClient và controller trên port 8080.

### 15.3. Gửi request qua Spring app

```bash
curl -i http://localhost:8080/demo/products/p-100
```

Kỳ vọng HTTP 200 và body:

```json
{
  "id": "p-100",
  "name": "Notebook",
  "stock": 12
}
```

Luồng chứng minh rằng API key đã đi qua nhóm cấu hình đến RestClient, nhưng response không chứa secret.

### 15.4. Các bài thử lỗi

1. Gỡ `CATALOG_API_KEY` rồi restart app: `@NotBlank` trong `CatalogProperties.Auth` sẽ báo lỗi cấu hình nếu validation đã được kích hoạt đúng.
2. Đặt `INTEGRATIONS_CATALOG_TIMEOUTS_CONNECT=not-a-duration`: Binder có thể lỗi conversion.
3. Tắt mock server rồi gọi endpoint: client gặp lỗi kết nối, controller advice có thể trả 503.
4. Chạy mock server nhưng đặt API key giả khác `local-demo-key`: upstream trả 401, advice trả 502 trong demo.
5. Đặt `INTEGRATIONS_CATALOG_BASEURL=http://127.0.0.1:9999`: app có thể vẫn startup (URI hợp lệ), nhưng outbound request lỗi connection.
6. Đặt `INTEGRATIONS_CATALOG_TIMEOUTS_READ=0s`: bean factory chủ động từ chối timeout zero.
7. Đặt `SPRING_PROFILES_ACTIVE=prod` khi upstream local vẫn chạy: app sẽ dùng base URL từ production profile, nếu env không override, minh họa việc profile làm đổi target.

Mỗi thử nghiệm cần phân biệt **lỗi startup configuration**, **lỗi chuyển đổi/validation** và **lỗi runtime HTTP**.

## 16. Kiểm thử binding không cần gọi upstream thật

Có thể dùng `@SpringBootTest` để xác nhận Boot đã đăng ký record configuration properties và bind giá trị đúng.

File:

```text
src/test/java/com/example/catalogdemo/config/CatalogPropertiesTest.java
```

```java
package com.example.catalogdemo.config;

import static org.assertj.core.api.Assertions.assertThat;

import java.net.URI;
import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(properties = {
    "integrations.catalog.base-url=http://localhost:19091",
    "integrations.catalog.auth.api-key=test-only-key",
    "integrations.catalog.timeouts.connect=250ms",
    "integrations.catalog.timeouts.read=3s"
})
class CatalogPropertiesTest {

    @Autowired
    CatalogProperties properties;

    @Test
    void bindsStructuredExternalServiceSettings() {
        assertThat(properties.baseUrl())
                .isEqualTo(URI.create("http://localhost:19091"));
        assertThat(properties.auth().apiKey())
                .isEqualTo("test-only-key");
        assertThat(properties.timeouts().connect())
                .isEqualTo(Duration.ofMillis(250));
        assertThat(properties.timeouts().read())
                .isEqualTo(Duration.ofSeconds(3));
        assertThat(properties.enabled()).isTrue();
    }
}
```

**Test này không gọi `http://localhost:19091`.** Nó chỉ khởi tạo context và xác nhận binding. `RestClient` bean có thể được tạo từ baseUrl trong test nhưng không nhất thiết mở kết nối ngay tại thời điểm khởi tạo.

Khi tạo test, các property trong `@SpringBootTest(properties=...)` là **test override** ưu tiên cao theo cơ chế test context; không dùng chúng để suy luận mọi precedence ở production.

### 16.1. Kiểm thử thiếu auth

Để kiểm chứng fail-fast, dùng `ApplicationContextRunner` hoặc một `@SpringBootTest` riêng với property thiếu/rỗng. Với `ApplicationContextRunner`, cần đăng ký configuration-properties type và validation auto-configuration phù hợp:

```java
package com.example.catalogdemo.config;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.validation.ValidationAutoConfiguration;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

class CatalogValidationTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                .withConfiguration(
                    AutoConfigurations.of(
                        ValidationAutoConfiguration.class))
                .withUserConfiguration(TestConfig.class);

    @Test
    void failsWhenApiKeyIsBlank() {
        runner.withPropertyValues(
            "integrations.catalog.base-url=http://localhost:19091",
            "integrations.catalog.auth.api-key=",
            "integrations.catalog.timeouts.connect=2s",
            "integrations.catalog.timeouts.read=5s")
            .run(context -> {
                assertThat(context).hasFailed();
            });
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(CatalogProperties.class)
    static class TestConfig {
    }
}
```

`hasFailed()` xác nhận context không tạo được; muốn kiểm tra chính xác root cause, có thể xem `context.getStartupFailure()` và cause chain. Tùy auto-configuration/test setup, cần bảo đảm Bean Validation provider hiện diện. Không kết luận mọi failure đều do `@NotBlank` nếu test có lỗi khác ở hạ tầng.

### 16.2. Kiểm thử bare Duration

```properties
integrations.catalog.timeouts.connect=2
```

Trong Spring Boot 3.3, `Duration` không có unit annotation thường dùng milliseconds mặc định, nên `2` là **2ms**, không phải 2s. Viết test với `Duration.ofMillis(2)` sẽ giúp phát hiện sự nhầm lẫn này; trong cấu hình triển khai nên dùng suffix rõ ràng như `2s` hoặc `500ms`.

### 16.3. Kiểm thử nested validation

Với `@Valid @NotNull Auth auth` và `@NotBlank String apiKey`, cả hai trường hợp cần được từ chối: thiếu nguyên nhóm `auth`, và nhóm `auth` tồn tại nhưng `api-key` là chuỗi trắng.

Nếu bỏ `@Valid`, nested constraints có thể không được cascade như mong đợi. Bài này đặt `@Valid` trực tiếp trên record component để truyền đạt yêu cầu rõ ràng.

## 17. Kiểm thử CatalogClient bằng mock HTTP

Không nên chạy integration test gọi endpoint production. Spring Framework có `MockRestServiceServer`, hỗ trợ buộc một `RestClient.Builder` trả response giả, giúp xác nhận request path, header và JSON mapping.

File:

```text
src/test/java/com/example/catalogdemo/catalog/CatalogClientTest.java
```

```java
package com.example.catalogdemo.catalog;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.header;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;

class CatalogClientTest {

    @Test
    void sendsApiKeyAndReadsProduct() {
        RestClient.Builder builder = RestClient.builder();

        MockRestServiceServer server =
                MockRestServiceServer.bindTo(builder).build();

        RestClient client = builder
                .baseUrl("http://example.test")
                .defaultHeader("X-Api-Key", "test-only-key")
                .build();

        CatalogClient gateway = new CatalogClient(client);

        server.expect(requestTo(
                "http://example.test/products/p-100"))
            .andExpect(header("X-Api-Key", "test-only-key"))
            .andRespond(withSuccess(
                """
                {"id":"p-100","name":"Notebook","stock":12}
                """,
                MediaType.APPLICATION_JSON));

        ProductDto result = gateway.getProduct("p-100");

        assertThat(result.id()).isEqualTo("p-100");
        assertThat(result.name()).isEqualTo("Notebook");
        assertThat(result.stock()).isEqualTo(12);
        server.verify();
    }
}
```

Đây là test của **CatalogClient behavior**, không phải test toàn bộ HTTP request factory/timeouts. Trong test này, MockRestServiceServer gắn request handling vào builder trước khi xây RestClient; vì vậy test không gọi code factory production vốn tùy chỉnh `requestFactory`.

Nếu cần test rằng timeout config được truyền vào factory thật, viết test riêng ở bean configuration hoặc integration test dùng một HTTP mock server có delay thực tế. Không kết luận timeout hoạt động chỉ từ một mock không có network.

### 17.1. Thêm test khi upstream lỗi

Có thể tạo expectation trả HTTP 503:

```java
server.expect(requestTo(
        "http://example.test/products/p-100"))
    .andRespond(org.springframework.test.web.client.response
        .MockRestResponseCreators.withServerError());
```

Sau đó assert CatalogClient ném `RestClientResponseException`/subtype phù hợp. Kiểm thử `@RestControllerAdvice` riêng nếu muốn chứng minh HTTP inbound trả 502/503. Đừng catch tất cả exception trong CatalogClient rồi tự trả một `ProductDto` rỗng vì có thể che outage thật.

## 18. Chạy build và đóng gói

Trên Linux/macOS:

```bash
./mvnw clean test
./mvnw package
java -jar target/catalog-demo-0.0.1-SNAPSHOT.jar
```

Nếu không có Maven Wrapper:

```bash
mvn clean test
mvn package
java -jar target/catalog-demo-0.0.1-SNAPSHOT.jar
```

Trên Windows PowerShell:

```powershell
.\mvnw.cmd clean test
.\mvnw.cmd package
$env:CATALOG_API_KEY = "local-demo-key"
java -jar target/catalog-demo-0.0.1-SNAPSHOT.jar
```

Để ví dụ startup thành công, cần cung cấp `CATALOG_API_KEY` (hoặc env canonical tương đương) và giữ các nhóm cấu hình bắt buộc. Nếu file YAML của bài có `api-key: "${CATALOG_API_KEY:}"` mà không có env, `@NotBlank` khiến startup fail như thiết kế.

### 18.1. Metadata IDE

Với `spring-boot-configuration-processor`, build có thể sinh:

```text
target/classes/META-INF/spring-configuration-metadata.json
```

File này giúp IDE biết các key như `integrations.catalog.base-url` và `integrations.catalog.timeouts.read`. Nó là **metadata cho công cụ**, không phải nơi lưu giá trị runtime. Không ghi API key thật vào metadata hoặc default metadata.

### 18.2. Xác minh dependency versions

Không hard-code Spring Framework version ngoài parent POM khi không cần. Nếu một dependency tự kéo bản Spring Web khác dòng 6.1, ứng dụng có thể gặp `NoSuchMethodError` đối với `RestClient`/timeout methods. Dùng:

```bash
./mvnw dependency:tree
```

khi cần chẩn đoán conflicts; không tùy tiện nâng từng JAR của Spring Framework mà bỏ BOM.

## 19. Docker Compose: override URL và timeout theo deployment

Có thể đóng gói app dưới dạng image theo workflow của dự án. Ví dụ Compose:

```yaml
services:
  catalog-demo:
    image: example/catalog-demo:1.0
    ports:
      - "8080:8080"
    environment:
      SPRING_PROFILES_ACTIVE: "prod"
      INTEGRATIONS_CATALOG_BASEURL: "https://catalog.partner.example"
      INTEGRATIONS_CATALOG_TIMEOUTS_CONNECT: "3s"
      INTEGRATIONS_CATALOG_TIMEOUTS_READ: "8s"
      CATALOG_API_KEY: "${CATALOG_API_KEY}"
```

Trong Compose YAML, `${CATALOG_API_KEY}` là biến interpolation **do Compose xử lý trước khi container chạy**. Chỉ dùng cách này khi nguồn env của Compose được quản trị an toàn; với secret thật nên ưu tiên Docker secrets/secret manager và không in value bằng các lệnh debug.

**Phân biệt hai tầng:**

1. Docker Compose quyết định container nhận environment variables nào.
2. Spring Boot quyết định các biến đó có ghi đè `application.yaml` hoặc Config Data khác không.

Một file `.env` ở Compose project thường dùng cho interpolation, **không mặc nhiên** làm mọi dòng trở thành env vars trong container nếu service không khai báo `environment` hoặc `env_file` tương ứng.

### 19.1. Docker secret volume và configtree

Nếu Docker service mount file:

```text
/run/secrets/integrations.catalog.auth.api-key
```

có thể cho Boot import:

```properties
spring.config.import=configtree:/run/secrets/
```

Nội dung file trở thành `integrations.catalog.auth.api-key`. Tên tệp có dấu chấm/đường dẫn con cần khớp canonical key; không ghi `key=value` vào file nếu đang dùng configtree theo mô hình một key một file.

Khi dùng đường này, cân nhắc bỏ placeholder `CATALOG_API_KEY` trong YAML hoặc giữ một policy rõ về thứ tự Config Data import. Nếu đồng thời có env canonical `INTEGRATIONS_CATALOG_AUTH_APIKEY`, nguồn env mặc định ưu tiên cao hơn Config Data file. Đừng nhân bản secret ở cả hai nguồn nếu không cần.

### 19.2. Tránh bake secret vào image

Không viết:

```dockerfile
ENV CATALOG_API_KEY=real-secret
```

và cũng không `COPY` file chứa secret vào image layer. Tạo image không có secret, cấp khi container chạy, cấu hình quyền truy cập volume/process và cơ chế rotation riêng.

## 20. Kubernetes: lấy cấu hình từ ConfigMap và Secret

Một Deployment có thể cấp giá trị không nhạy cảm qua `env`:

```yaml
env:
  - name: INTEGRATIONS_CATALOG_BASEURL
    value: "https://catalog.partner.example"
  - name: INTEGRATIONS_CATALOG_TIMEOUTS_READ
    value: "8s"
```

Và cấp credential qua Kubernetes Secret:

```yaml
env:
  - name: CATALOG_API_KEY
    valueFrom:
      secretKeyRef:
        name: catalog-client-credentials
        key: api-key
```

Các block trên là **mảnh cấu hình**; khi đưa vào Deployment thật phải gộp thành một mảng `env` trong cùng container.

### 20.1. Một mảnh Deployment đầy đủ hợp lệ

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: catalog-demo
spec:
  replicas: 1
  selector:
    matchLabels:
      app: catalog-demo
  template:
    metadata:
      labels:
        app: catalog-demo
    spec:
      containers:
        - name: app
          image: example/catalog-demo:1.0
          ports:
            - containerPort: 8080
          env:
            - name: SPRING_PROFILES_ACTIVE
              value: "prod"
            - name: INTEGRATIONS_CATALOG_BASEURL
              value: "https://catalog.partner.example"
            - name: INTEGRATIONS_CATALOG_TIMEOUTS_CONNECT
              value: "3s"
            - name: INTEGRATIONS_CATALOG_TIMEOUTS_READ
              value: "8s"
            - name: CATALOG_API_KEY
              valueFrom:
                secretKeyRef:
                  name: catalog-client-credentials
                  key: api-key
```

Kubernetes cần Secret tương ứng trong namespace và quyền truy cập phù hợp. Ví dụ trên **không tạo** Secret object. Ngoài ra, endpoint HTTP mẫu không có authentication và image chỉ là tên minh họa; không triển khai trực tiếp ra Internet.

### 20.2. Secret mount qua configtree

Một lựa chọn khác là mount Kubernetes Secret thành file:

```text
/etc/secrets/catalog/integrations.catalog.auth.api-key
```

Trong container:

```text
SPRING_CONFIG_IMPORT=configtree:/etc/secrets/catalog/
```

Spring Boot đọc file name thành property key và file content thành value. Không cần đưa plaintext credential vào OS environment.

**Hành vi cập nhật:** Kubernetes có thể cập nhật projected Secret volume theo cơ chế riêng, nhưng `@ConfigurationProperties` bean và RestClient được tạo tại startup **không tự hot-reload** chỉ vì file thay đổi. Cần rollout/restart hoặc một cơ chế refresh được thiết kế và kiểm thử riêng. Khi một header được đặt sẵn trong RestClient lúc khởi tạo, client tiếp tục dùng key snapshot cho tới khi được tạo lại.

## 21. enabled=true/false: chọn semantics ngay từ đầu

Trong model hiện tại:

```java
@DefaultValue("true") boolean enabled
```

được bind nhưng **chưa được dùng để vô hiệu hóa CatalogClient** trong code. Điều đó có nghĩa `enabled=false` chỉ thay giá trị bean, không tự ngăn controller gọi upstream.

Nếu dự án cần cờ disable thực sự, có các lựa chọn:

1. Controller/service kiểm tra `properties.enabled()` và trả một lỗi nghiệp vụ rõ ràng trước khi gọi outbound.
2. Dùng conditional bean registration (`@ConditionalOnProperty`) cho một chiến lược có và không có client, đồng thời xử lý injection tương ứng.
3. Thiết kế một interface `CatalogGateway` với implementation thực và disabled/no-op, chọn theo property một cách có kiểm soát.

**Đừng chỉ thêm field enabled rồi khẳng định tính năng đã tắt.** Trong ví dụ hiện tại, đây là một property được bind phục vụ bài học; để có hành vi thật, cần code tiêu thụ nó.

### 21.1. Kiểm tra enabled trong CatalogClient

Nếu muốn làm field có hiệu lực ngay, sửa constructor để nhận `CatalogProperties`, rồi check:

```java
private final RestClient client;
private final CatalogProperties properties;

public CatalogClient(
        @Qualifier("catalogRestClient") RestClient client,
        CatalogProperties properties) {
    this.client = client;
    this.properties = properties;
}

public ProductDto getProduct(String id) {
    if (!properties.enabled()) {
        throw new IllegalStateException(
            "Catalog integration is disabled");
    }
    // gọi client như đoạn chính
}
```

Cần thêm import `CatalogProperties` và một handler/response mapping phù hợp nếu expose lỗi ra HTTP. **Đây là biến thể nâng cao**, không được ghép nguyên xi vào class chính mà quên điều chỉnh constructor/test.

Nếu chính sách là không cần API key khi disabled, cần **validation có điều kiện** phù hợp; model chính luôn yêu cầu key, kể cả khi enabled=false. Thay đổi semantics phải đi cùng thay đổi Bean Validation, bean factory và tests.

## 22. Bảo mật API key trong ứng dụng mẫu

### 22.1. Tại sao String secret có rủi ro?

`String apiKey` thuận tiện cho HTTP header, nhưng có thể nằm trong bộ nhớ và dễ bị lộ qua:

- `record.toString()` mặc định.
- Log đối tượng `CatalogProperties`.
- Exception chứa thông tin cấu hình raw.
- Debug dump toàn bộ Environment hoặc HTTP request.
- Actuator endpoints không được bảo vệ.
- Session recording/HTTP tracing chứa headers.

Record Java có `toString()` tự sinh. Vì thế:

```java
logger.info("Properties: {}", properties);
```

**không an toàn** nếu record chứa API key. Chỉ log thông tin không nhạy cảm (base-url đã kiểm tra, timeout, enabled), và che những thành phần URL có credential/query nếu URL có thể chứa dữ liệu nhạy cảm.

### 22.2. Checklist bảo mật

- Không commit `CATALOG_API_KEY` thật vào Git.
- Không lưu key trong `application-prod.yaml`.
- Không ghi key vào metadata IDE.
- Không đưa secret vào Dockerfile, image layer, command-line args hoặc screenshot.
- Không log `X-Api-Key` hoặc `Authorization` headers.
- Bảo vệ `/actuator/env` và `/actuator/configprops`; kiểm tra masking/sanitization.
- Dùng HTTPS và xác minh TLS của upstream production.
- Giới hạn secret theo workload/principal và dùng rotation định kỳ.
- Không trả upstream error body nguyên văn ra endpoint công khai.
- Thiết kế restart/rollout khi secret thay đổi nếu client giữ key snapshot.
- Áp dụng network egress rules để ứng dụng chỉ gọi các hosts được phép.

**Không coi Config Data hoặc `@ConfigurationProperties` là một secret vault.** Đây là cơ chế nhận cấu hình; bảo mật thực tế đến từ nơi cấp secret, quyền truy cập, transport, logs và vận hành.

## 23. Tránh SSRF khi base-url có thể được cấu hình

`integrations.catalog.base-url` là một URI mà ứng dụng dùng làm đích outbound. Nếu người không được phép có thể điều khiển nó, ứng dụng có nguy cơ trở thành điểm xuất phát của Server-Side Request Forgery (SSRF), gọi đến địa chỉ nội bộ hoặc metadata service.

Đối với production:

- Chỉ cho phép host/service endpoints theo allowlist của tổ chức.
- Bắt buộc `https` ngoại trừ local/test có chủ đích.
- Không cho người dùng HTTP inbound truyền URL tùy ý vào RestClient.
- Giới hạn outbound network egress bằng chính sách hạ tầng.
- Kiểm tra redirect policy của HTTP client nếu API không yêu cầu redirects.
- Phân biệt validation cú pháp URI và authorization của host.
- Không đưa credential vào query string URL.

Ví dụ đơn giản của check tại bean factory:

```java
var scheme = properties.baseUrl().getScheme();
if (!"https".equalsIgnoreCase(scheme)
        && !"http".equalsIgnoreCase(scheme)) {
    throw new IllegalArgumentException(
            "Catalog URL must use HTTP or HTTPS");
}
```

Check scheme chưa đủ chống SSRF; allowlist hostname/IP range và egress control mới là những lớp bảo vệ bổ sung cần thiết. Không bật TLS bypass để “sửa nhanh” lỗi chứng chỉ.

## 24. Retry, circuit breaker và idempotency

Bài mẫu hiện tại **không tự retry** khi HTTP thất bại. Một `RestClient` được tạo với timeout không có nghĩa có chính sách retry/circuit breaker. Nếu cần resilience:

- Quy định số lần retry tối đa, backoff, jitter.
- Phân loại lỗi có thể retry: timeout, connection reset, 429, một số 5xx.
- Tránh retry 401/403 hoặc lỗi cấu hình không thể tự hồi phục.
- Chú ý POST/PUT side effects và idempotency key.
- Có tổng request deadline để ngăn nhiều retries kéo dài vô hạn.
- Bổ sung circuit breaker và bulkhead nếu tải cao và upstream không ổn định.
- Quan sát latency, error rate và số lần retry bằng metrics/traces.
- Không log request body/header chứa secret khi retry.

Nếu thêm các property `integrations.catalog.retry.*`, cần mở rộng `CatalogProperties`, cài implementation thực, validation và tests; metadata/config keys mới **không tự kích hoạt retry**.

### Khi nào chọn WebClient?

`RestClient` là blocking; phù hợp Spring MVC thread-per-request hoặc code imperative. `WebClient` dùng reactive streams và có semantics timeout/retry khác. Không trộn `WebClient.block()` thiếu kiểm soát vào event-loop reactive hoặc dựa vào việc đổi class để giả định toàn bộ hệ thống thành non-blocking.

## 25. Thêm dịch vụ bên ngoài thứ hai

Khi có thêm Billing API, không nên copy nguyên code rồi thay URL string ở nhiều nơi. Có thể tạo nhóm riêng:

```yaml
integrations:
  catalog:
    base-url: "https://catalog.partner.example"
    auth:
      api-key: "${CATALOG_API_KEY:}"
    timeouts:
      connect: 2s
      read: 5s

  billing:
    base-url: "https://billing.partner.example"
    auth:
      api-key: "${BILLING_API_KEY:}"
    timeouts:
      connect: 3s
      read: 8s
```

Sau đó:

- `CatalogProperties` với prefix `integrations.catalog`.
- `BillingProperties` với prefix `integrations.billing`.
- Hai `RestClient` beans với qualifier khác nhau.
- Hai service clients có trách nhiệm rõ ràng.
- Validation và test riêng cho từng đối tác.

Có thể tái sử dụng một nested immutable type cho auth/timeouts, nhưng cần tránh gắn mọi thứ vào một "GenericExternalServiceProperties" khổng lồ nếu contract của mỗi đối tác khác nhau.

### Map<String, ServiceSettings> có phù hợp?

Nếu số lượng endpoint động lớn và chúng có cấu trúc nhất quán, một `Map<String, ServiceSettings>` dưới prefix `integrations.services` có thể hữu ích. Tuy nhiên:

- Map keys cần quy tắc naming và normalization.
- Có thể khó ràng buộc bắt buộc từng dịch vụ.
- Hints/metadata IDE ít cụ thể hơn per-service record.
- Có thể cần whitelist các service keys hợp lệ.
- Bảo mật và rotation của secret theo key cần thiết kế riêng.

Đối với vài tích hợp cố định, tạo typed `@ConfigurationProperties` riêng thường dễ đọc, dễ kiểm thử hơn.

## 26. Phân tích các lỗi thực tế khi khởi động

### 26.1. Thiếu API key

Triệu chứng: app không tạo được `CatalogProperties` vì `auth.apiKey` blank hoặc missing; failure có thể được bọc bởi `ConfigurationPropertiesBindException` hoặc bean creation exception.

Cách xử lý:

1. Kiểm tra env `CATALOG_API_KEY` đã vào đúng JVM chưa.
2. Nếu dùng env canonical, kiểm tra `INTEGRATIONS_CATALOG_AUTH_APIKEY`.
3. Nếu dùng configtree, kiểm tra file mount và import root.
4. Xem active profile và source precedence.
5. Đừng in raw key để chẩn đoán.

### 26.2. Timeout sai định dạng

Ví dụ:

```text
INTEGRATIONS_CATALOG_TIMEOUTS_READ=fast
```

`Duration` không thể parse `fast`; đây là lỗi conversion, không phải DNS hoặc HTTP connection.

Dùng:

```text
INTEGRATIONS_CATALOG_TIMEOUTS_READ=5s
```

### 26.3. Timeout ghi "5" nhưng được hiểu là 5ms

Spring Boot `Duration` mặc định dùng milliseconds cho số trần nếu không có `@DurationUnit`. Viết `5s`, `500ms` hoặc dạng ISO-8601 để người vận hành không đoán sai.

### 26.4. Base URL hợp lệ nhưng kết nối thất bại

`http://127.0.0.1:9091` có URI syntax hợp lệ. Nhưng nếu app chạy trong Docker container, `127.0.0.1` là **chính container đó**, không phải máy host hoặc container upstream khác.

Khi triển khai Docker Compose, dùng service DNS name như `http://mock-catalog:9091` trong cùng network nếu upstream là một service khác. Trong Kubernetes, dùng Kubernetes Service DNS name/port. Địa chỉ `localhost` trong YAML mẫu chỉ dành cho khi cả Java app và mock server chạy trực tiếp trên cùng máy.

### 26.5. 401 Unauthorized từ upstream

Có thể do API key thiếu, sai, hết hạn, tên header sai, URL trỏ nhầm môi trường hoặc đối tác dùng cơ chế Bearer auth thay vì `X-Api-Key`.

`@NotBlank` chỉ kiểm tra key **không rỗng**, không thể chứng minh key được đối tác chấp nhận. Authentication chỉ được xác thực khi gọi upstream hoặc qua cơ chế kiểm tra riêng.

### 26.6. 404 từ upstream

Có thể path endpoint không đúng, version prefix thiếu, ID không tồn tại hoặc URI được nối sai giữa base URL và relative path. Kiểm tra request path mà không in headers nhạy cảm.

### 26.7. 502/503 từ controller nội bộ

Trong example advice:

- Upstream HTTP status lỗi → 502.
- I/O/network exception → 503.

Đây là mapping của demo. Với production phải phân biệt timeout, rate limiting, not found và upstream auth error theo API contract của hệ thống.

### 26.8. Bean ambiguity

Nếu có hai `RestClient` beans, constructor:

```java
public CatalogClient(RestClient client)
```

có thể gây `NoUniqueBeanDefinitionException` nếu không có primary/qualifier tương ứng. Dùng:

```java
@Qualifier("catalogRestClient")
```

đúng với tên bean factory method.

### 26.9. Không tìm thấy CatalogProperties bean

Nếu package main không bao trùm package config hoặc thiếu `@ConfigurationPropertiesScan`/`@EnableConfigurationProperties`, Boot không đăng ký record. Sửa package scanning/registration thay vì tự tạo `new CatalogProperties(...)` ở service.

### 26.10. Cấu hình sửa rồi mà app vẫn dùng value cũ

Khi JVM đã khởi động, `CatalogProperties` record và `RestClient` được tạo với snapshot tại thời điểm bind. Đổi env/secret file/deployment YAML không tự thay đổi object đang chạy. Cần restart/rollout hoặc hạ tầng refresh có chủ đích.

## 27. Đọc lỗi binding và Origin đúng cách

Khi Spring Boot thất bại ở bước bind, thông báo thường có các thông tin:

```text
Property: integrations.catalog.timeouts.read
Value: "fast"
Origin: class path resource [application.yaml] - ...
Reason: failed to convert String to Duration
```

Tên/format thay đổi theo version, source và target. Nếu value đến từ environment variable, Origin có thể không có line/column; không nên coi thiếu line là thiếu source.

Phương pháp phân tích:

1. Tìm `ConfigurationPropertiesBindException` hoặc `BindException` trong cause chain.
2. Xem property path và target Java type.
3. Xem source nào đang thắng precedence.
4. Kiểm tra value syntax và đơn vị.
5. Nếu bind được nhưng vi phạm `@NotBlank`/`@NotNull`, xem Bean Validation.
6. Kiểm tra file YAML đúng indentation và profile được nạp.
7. Không log nguyên giá trị API key hoặc HTTP headers.

Khi app khởi động thành công, có thể quan sát các trường không nhạy cảm:

```java
@Bean
ApplicationRunner describeCatalog(CatalogProperties props) {
    return args -> {
        System.out.println("Catalog URL: " + props.baseUrl());
        System.out.println("Connect timeout: "
                + props.timeouts().connect());
        System.out.println("Read timeout: "
                + props.timeouts().read());
        System.out.println("Enabled: " + props.enabled());
    };
}
```

Đoạn code này thuộc một `@Configuration` class với import `org.springframework.boot.ApplicationRunner`, `org.springframework.context.annotation.Bean`. Nó chỉ là diagnostic tùy chọn, không bắt buộc có trong project chính. **Không gọi `System.out.println(props)`**, vì record có thể đưa API key vào `toString()`.

## 28. Kiểm thử về precedence và profile

Một ma trận ngắn:

| application.yaml | application-prod.yaml | OS env | Giá trị đọc của `timeouts.read` |
| --- | --- | --- | --- |
| `5s` | Không active | Không | `5s` |
| `5s` | `8s`, profile prod active | Không | `8s` |
| `5s` | `8s`, profile prod active | `10s` | `10s` |
| `5s` | Không active | `500ms` | `500ms` |
| `5s` | Không active | `not-time` | Có thể lỗi conversion |
| `5s` | Không active | `0s` | Bean factory ví dụ từ chối |

Bảng giả định chỉ xét các source trên, không có CLI/JVM/JSON/custom source ưu tiên cao hơn. Ngoài ra, nếu `timeouts` subtree bị thiếu hoàn toàn, cấu hình validation có thể thất bại trước khi áp dụng một fallback ý định khác.

Để kiểm thử **precedence thật của OS env**, cần khởi động process với environment variable được cấp trước startup, không chỉ gọi `System.setProperty(...)` sau khi context đã tạo.

## 29. Cách mở rộng validation cho production

Validation trong mẫu đảm bảo URL không null, auth group và timeout group tồn tại, apiKey không blank. Nhưng vẫn có những tình huống cần ràng buộc mạnh hơn:

- Scheme của `baseUrl` phải là `https` trong profile production.
- Host chỉ thuộc allowlist nội bộ/đối tác.
- Timeouts không âm/zero, không lớn hơn ngưỡng policy.
- API key có định dạng mong đợi.
- `enabled=false` có cần bỏ qua yêu cầu key hay không?
- Nếu dùng client certificate, file path và password của keystore phải hợp lệ.
- Namespace để gắn HTTP headers phải đúng hợp đồng đối tác.

Các ràng buộc nhiều trường có thể đặt trong custom validator hoặc một bean kiểm tra cấu hình trước khi dùng client. Cần tránh biến `@ConfigurationProperties` thành service truy cập mạng để "validate credential" trong constructor binding; việc xác minh remote credentials là **runtime integration check**, không phải parse/binding config.

### 29.1. Fail-fast và degrade gracefully

Với một tích hợp **bắt buộc** cho core business, thiếu API key hoặc URL có thể làm startup fail là hành vi mong muốn.

Với một tích hợp **tùy chọn**, policy có thể là:

- Cho phép app startup khi không có key nếu `enabled=false`.
- Tạo implementation `DisabledCatalogClient` trả trạng thái phù hợp.
- Không tạo RestClient/secret-dependent bean khi bị disable.
- Chỉ validate credential khi enabled.

Mỗi policy dẫn tới code và validation khác nhau. Bài hiện tại chọn **fail-fast luôn yêu cầu key** để đơn giản hóa và minh họa việc Spring Boot quản lý cấu hình có cấu trúc.

## 30. Những điểm cần tránh khi triển khai

| Sai lầm | Vì sao có vấn đề | Cách làm tốt hơn |
| --- | --- | --- |
| Hard-code URL/API key trong service | Khó đổi môi trường, lộ secret | `@ConfigurationProperties` và secret injection |
| Dùng nhiều `@Value` rời rạc | Khó quản lý nhóm và validation | Typed config record |
| Thiếu `@ConfigurationPropertiesScan` | Bean không được đăng ký | Scan hoặc `@EnableConfigurationProperties` |
| Đặt record thành `@Component` | Không đúng chiến lược constructor binding chuẩn | Đăng ký qua config properties |
| Dùng String timeout không đơn vị | Dễ hiểu sai `5` = 5ms | `Duration` + `5s` |
| API key rỗng vẫn cho startup | Lỗi đến muộn ở upstream | `@NotBlank`/fail-fast nếu bắt buộc |
| Tin `@NotNull URI` bảo đảm URL dùng được | Không kiểm tra DNS/TLS/host authorization | Check scheme, allowlist, egress |
| Set `enabled=false` mà code không đọc | Flag vô tác dụng | Triển khai disabled strategy rõ |
| Dùng `RestClient.create()` tùy tiện | Bỏ qua Boot builder customization | Inject `RestClient.Builder` |
| Override request factory mà không hiểu HTTP stack | Timeouts/pooling/TLS có thể khác | Chọn factory có chủ đích và test |
| Retry mọi POST khi timeout | Có thể tạo side effect trùng lặp | Idempotency và retry policy |
| Test gọi partner production | Test flaky, tốn chi phí/rủi ro | MockRestServiceServer hoặc mock server |
| Log nguyên config record | `toString()` làm lộ key | Log trường an toàn |
| Đặt `localhost` khi chạy trong Docker | Trỏ về chính container | Dùng service DNS/host phù hợp |
| Bật Actuator env/configprops public | Có nguy cơ lộ cấu hình | Auth, masking, exposure tối thiểu |
| Coi mount secret đổi là client tự refresh | Snapshot config/RestClient không hot-reload | Rollout/restart hoặc refresh riêng |
| Thấy 401 rồi tắt TLS validation | Không giải quyết authentication | Kiểm tra đúng credential và endpoint |
| Viết default API key thật trong YAML | Secret rò qua artifact/repo | Cấp từ Secret manager |

## 31. Checklist hoàn thành bài thực hành

- [ ] Tạo Maven project Java 17, Spring Boot 3.3.
- [ ] Thêm Spring Web, Validation, Test và configuration processor.
- [ ] Tạo `CatalogDemoApplication` có `@ConfigurationPropertiesScan`.
- [ ] Tạo record `CatalogProperties` với prefix `integrations.catalog`.
- [ ] Khai báo nested records `Auth` và `Timeouts`.
- [ ] Đặt `@Validated`, `@Valid`, `@NotNull` và `@NotBlank` ở vị trí phù hợp.
- [ ] File `application.yaml` có base-url, timeouts và placeholder API key.
- [ ] Cấp API key giả cho local, không hard-code secret thật.
- [ ] Tạo bean `catalogRestClient` bằng Boot-provided `RestClient.Builder`.
- [ ] Đặt connect/read timeout qua request factory được chọn.
- [ ] Tạo `ProductDto` và `CatalogClient` có qualifier đúng.
- [ ] Tạo `CatalogController` để gọi outbound qua client.
- [ ] Có mapping lỗi outbound không làm lộ response body hoặc headers nhạy cảm.
- [ ] Chạy fake HTTP Catalog server ở port 9091.
- [ ] Khởi động Boot app ở port 8080 và gọi endpoint demo.
- [ ] Đảm bảo response JSON không chứa API key.
- [ ] Test config binding, nested validation và mock RestClient request.
- [ ] Test timeout unit sai và missing API key.
- [ ] Tạo `application-prod.yaml` hoặc env overrides cho deployment.
- [ ] Kiểm tra env canonical naming, đặc biệt dash → bỏ và dot → underscore.
- [ ] Nếu chạy trong container, thay `127.0.0.1` bằng upstream service address đúng.
- [ ] Có kế hoạch giữ secrets ngoài source/image và rotation.
- [ ] Không coi `enabled` tự có tác dụng khi code chưa sử dụng.
- [ ] Có runbook xử lý DNS, timeout, 401/403, 4xx/5xx và cấu hình startup.
- [ ] Không public demo endpoint không có auth trên production.

## 32. Hướng phát triển tiếp theo

Sau khi hoàn thành ví dụ, có thể mở rộng có kiểm soát:

1. **Thêm một external Billing service**: tạo `BillingProperties`, bean `billingRestClient` và `BillingClient` riêng.
2. **Chuyển API key sang Secret volume**: dùng `spring.config.import=configtree:/etc/secrets/` và file có tên property canonical.
3. **Bổ sung request correlation ID**: truyền context qua outbound headers, lọc secret trước khi log.
4. **Observability**: thiết lập metrics/traces HTTP client tùy hạ tầng và Boot configuration, không log payload/header nhạy cảm.
5. **Retry/circuit breaker**: thêm resilience library khi có requirements, test idempotency, backoff và timeout deadline.
6. **Kiểm thử container**: mock upstream trong cùng Docker Compose network hoặc Kubernetes namespace.
7. **Contract test**: kiểm tra JSON schema và HTTP status rules với upstream giả lập.
8. **Configuration metadata**: thêm mô tả vào JavaDoc hoặc additional metadata để IDE gợi ý keys và units.
9. **Dynamic secret rotation**: thiết kế tái tạo outbound client và rollback, không mặc định Spring Boot tự refresh.
10. **HTTPS/mTLS**: cấu hình SSL bundle, keystore/truststore hoặc request factory theo chính sách của đối tác.

Không cần làm tất cả ngay trong bài mẫu; nền tảng quan trọng là **tách giá trị cấu hình, cơ chế kết nối và logic nghiệp vụ**.

## 33. Tài liệu tham khảo chính thức

- **Spring Boot 3.3 — Externalized Configuration**, PropertySource order, Config Data, YAML, placeholder, type-safe configuration properties, constructor binding, relaxed binding, validation, Duration: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- **Spring Boot 3.3 — Calling REST Services**, phần `RestClient`, builder auto-configuration và customizers: https://docs.spring.io/spring-boot/3.3/reference/io/rest-client.html
- **Spring Framework 6.1 — RestClient**, hướng dẫn fluent blocking HTTP API: https://docs.spring.io/spring-framework/reference/integration/rest-clients.html#rest-restclient
- **Spring Framework 6.1 — SimpleClientHttpRequestFactory Javadoc**, `setConnectTimeout(Duration)` và `setReadTimeout(Duration)`: https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/http/client/SimpleClientHttpRequestFactory.html
- **Spring Boot 3.3 — Configuration Metadata**, processor và metadata phục vụ IDE: https://docs.spring.io/spring-boot/3.3/specification/configuration-metadata/index.html
- **Spring Boot 3.3 — Testing Spring Boot Applications**, test context và test utilities: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
- **Spring Framework — MockRestServiceServer**, test outbound client bằng mock request/response: https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-client.html
- **Docker Compose — Environment variables**, interpolation và service environment: https://docs.docker.com/compose/how-tos/environment-variables/
- **Kubernetes — Secrets**, cách cấp credential cho workload: https://kubernetes.io/docs/concepts/configuration/secret/

## 34. Tổng kết

Trong Spring Boot 3.3, một ứng dụng tích hợp dịch vụ ngoài nên tuân theo tuyến trách nhiệm:

```text
Config Data / OS env / secrets
           |
           v
@Validated @ConfigurationProperties
  CatalogProperties (typed record)
           |
           v
@Configuration tạo RestClient
  URL + timeout + API key
           |
           v
@Service CatalogClient
  HTTP request / response / errors
           |
           v
@RestController CatalogController
  HTTP API nội bộ
```

Ba điều quan trọng nhất:

1. **Một nhóm cấu hình có tên canonical và Java type rõ** giúp local/staging/prod thay đổi URL, timeout, credentials mà không build lại logic nghiệp vụ.
2. **Spring Boot chỉ bind và cung cấp dữ liệu**; việc tạo client, áp dụng timeouts, gắn auth header, xử lý HTTP errors và cờ enabled đều cần code thực thi.
3. **Kiểm thử và bảo mật là một phần của thiết kế**: validation fail-fast cho dữ liệu bắt buộc, mock outbound HTTP trong test, không hard-code/log secret, kiểm soát nguồn override và có kế hoạch rotate/restart khi cấu hình thay đổi.

Bài này tạo được một khuôn mẫu nhỏ nhưng có thể mở rộng: thêm mỗi external service bằng một `@ConfigurationProperties` contract độc lập, một outbound client bean được cấu hình rõ ràng và những test chứng minh kết nối sử dụng đúng các giá trị đã bind.

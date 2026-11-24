# Lớp Config, ánh xạ args và kiểm tra cấu hình đầu vào

## 1. Bài toán: custom GatewayFilter phải có hợp đồng cấu hình

**Spring Cloud Gateway Server WebFlux** nhận request, dùng route predicate để tìm tuyến phù hợp, thực thi filter chain, có thể biến đổi path/header, khám phá instance qua `lb://service-id` rồi proxy request tới microservice. Khi các filter có sẵn không đáp ứng một chính sách riêng, ta có thể viết **GatewayFilterFactory tùy biến**.

Ví dụ, một nhóm muốn gắn dấu vết theo route vào request backend nhận:

~~~http
X-Lab-Tag: catalog_v1
~~~

Thay vì hardcode trong nhiều route, ta cấu hình:

~~~yaml
filters:
  - name: AuditLabel
    args:
      headerName: X-Lab-Tag
      label: catalog_v1
      overwrite: true
      maxLabelLength: 32
~~~

Vấn đề không chỉ là thêm header. Gateway phải biết cách chuyển `args` từ YAML thành một **lớp Config có kiểu dữ liệu rõ ràng**, xử lý các giá trị mặc định và **từ chối cấu hình sai trước khi filter xử lý traffic**. Nếu không, một typo hoặc boolean mặc định sai có thể thay đổi hành vi routing/security mà không ai nhận ra.

Bài thuộc chương **Bộ lọc tùy biến** của module **SPRING_CLOUD_GATEWAY**. Những kỹ thuật ở đây áp dụng khi phát triển API Gateway dùng route predicate, filter chain, biến đổi đường dẫn/header, service discovery và các chức năng xác thực, rate limiting, circuit breaker, retry, TLS, observability. Tuy nhiên, bài tập tập trung vào **Config, ánh xạ args và validation**, không biến một header minh họa thành cơ chế xác thực.

Mục tiêu:

1. Viết `AbstractGatewayFilterFactory<Config>` đúng tên, đúng kiểu và được Spring đăng ký.
2. Ánh xạ cấu hình dạng `name/args` và dạng shortcut có tham số theo vị trí.
3. Dùng typed fields, defaults, Jakarta Bean Validation và quy tắc liên thuộc tính.
4. Phân biệt lỗi parse/binding, validation, route resolution và lỗi tại request runtime.
5. Kiểm thử cả cấu hình hợp lệ, thiếu field, sai kiểu, giá trị nguy hiểm và route refresh.

> **Phạm vi:** Bài dành cho **Gateway Server WebFlux**, không phải Gateway Server MVC. Hai biến thể có API đăng ký custom filters khác nhau. Chọn Spring Boot/Spring Cloud BOM và starter tương thích với phiên bản chạy.

## 2. Hành trình của một đối tượng Config

Một route definition chứa tên filter và map tham số:

~~~yaml
- id: catalog-api
  uri: http://localhost:9091
  predicates:
    - Path=/api/catalog/**
  filters:
    - name: AuditLabel
      args:
        headerName: X-Lab-Tag
        label: catalog_v1
        overwrite: true
~~~

Luồng khái niệm:

~~~mermaid
flowchart TD
    Y["YAML/RouteDefinition<br/>filters name + args"] --> F["Tìm GatewayFilterFactory<br/>name = AuditLabel"]
    F --> B["Binding/Conversion<br/>args → Config"]
    B --> V["Validate fields và<br/>quy tắc liên thuộc tính"]
    V --> A["factory.apply(config)<br/>tạo GatewayFilter"]
    A --> R["Route runtime"]
    R --> Q["Request khớp route"]
    Q --> H["filter(exchange, chain)<br/>biến đổi request"]
    H --> D["Gửi downstream"]
~~~

Đây là **hai pha** cần phân biệt:

- **Cấu hình/route materialization:** tìm factory bean, bind args, validate và gọi `apply(config)`.
- **Runtime:** chạy `GatewayFilter.filter(exchange, chain)` trên mỗi HTTP request đã khớp route.

Một số phiên bản/nguồn route có thể materialize routes **lazily**, chẳng hạn khi có subscription đến route stream hoặc khi refresh. Do đó, không nên hứa mọi cấu hình sai chắc chắn khiến JVM dừng ngay tại startup. Pipeline deploy cần **ép kiểm tra routes đã nạp và smoke test**, không chỉ dựa vào việc process còn chạy.

| Thành phần | Vai trò |
| --- | --- |
| `GatewayFilterFactory<C>` | Contract tạo filter từ config |
| `AbstractGatewayFilterFactory<C>` | Base class thuận tiện cho WebFlux factory |
| `Config` | Object chứa tham số route sau binding |
| `shortcutFieldOrder()` | Xác định tên/thứ tự tham số cho shortcut |
| `GatewayFilter` | Hàm reactive xử lý request/response |
| `RouteDefinition` và `FilterDefinition` | Dữ liệu route/filter từ YAML hoặc nguồn khác |
| `RouteDefinitionRouteLocator` | Chuyển route definition thành route runtime |
| `GlobalFilter` | Filter áp dụng ở phạm vi toàn Gateway, khác factory per-route |

### Quy ước tên và đăng ký bean

Tên class chuẩn:

~~~java
AuditLabelGatewayFilterFactory
~~~

Tên dùng trong YAML:

~~~yaml
name: AuditLabel
~~~

Class custom phải là **Spring bean**, ví dụ có `@Component` hoặc được trả bởi `@Bean`; và phải ở package được component scan. Spring Cloud Gateway khuyến nghị class có hậu tố **`GatewayFilterFactory`**. Không phụ thuộc các biến thể tên class thiếu hậu tố vì chúng không phải quy ước được hỗ trợ lâu dài.

## 3. Thiết kế lớp Config có kiểu và ràng buộc

Ta dùng bốn thuộc tính:

| Trường | Kiểu Java | Có bắt buộc? | Quy tắc |
| --- | --- | --- | --- |
| `headerName` | `String` | Có | Chỉ header bắt đầu bằng `X-`, ký tự an toàn |
| `label` | `String` | Có | Token ngắn chỉ gồm chữ, số, chấm, gạch dưới/gạch nối |
| `overwrite` | `Boolean` | Có | `true` dùng set, `false` dùng append |
| `maxLabelLength` | `Integer` | Có default 32 | Nằm trong [1,64], label không dài quá giới hạn này |

**Vì sao `Boolean` chứ không phải `boolean`?** Với một boolean bắt buộc, `Boolean` cho phép phân biệt **thiếu** (null) với `false`. Nếu dùng primitive, thiếu giá trị có thể âm thầm trở thành false và vượt qua một số kiểm tra.

**Vì sao không đưa mọi thứ vào `Map<String,Object>`?** Typed Config làm rõ contract, hỗ trợ conversion/validation và giúp bắt lỗi sớm. Map tự do chỉ nên dùng cho dữ liệu thật sự động với schema riêng được kiểm soát.

### Validation có tự chạy không?

Trong Spring Boot 3+/4+, Bean Validation dùng namespace **`jakarta.validation.*`**. Annotation như `@NotBlank`, `@Pattern`, `@Min`, `@Max`, `@NotNull` mô tả ràng buộc. Nhưng **đừng chỉ gắn `@Validated` lên Config và giả định tất cả con đường bind GatewayFilterFactory đều chắc chắn chạy validation như `@ConfigurationProperties`**.

Bài này dùng một cách có thể kiểm tra rõ ràng: inject `jakarta.validation.Validator` và gọi `validator.validate(config)` **trong `apply(config)`** trước khi tạo GatewayFilter. Ngoài ra phải kiểm tra ràng buộc **giữa các fields**, ví dụ `label.length() <= maxLabelLength`.

## 4. Cài đặt AuditLabelGatewayFilterFactory hoàn chỉnh

Thêm Bean Validation provider cho dự án Gateway WebFlux; ví dụ Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

Ứng dụng còn phải có Gateway WebFlux starter và Spring Cloud BOM phù hợp. Gateway 4.3.x/5.x có starter WebFlux riêng `spring-cloud-starter-gateway-server-webflux`; nhiều bản 4.2.x cũ dùng `spring-cloud-starter-gateway`. Không thêm Servlet MVC starter khi muốn dùng API filter WebFlux.

Tạo `src/main/java/demo/gateway/filters/AuditLabelGatewayFilterFactory.java`:

~~~java
package demo.gateway.filters;

import java.util.List;
import java.util.Set;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.ConstraintViolationException;
import jakarta.validation.Validator;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;

import org.springframework.cloud.gateway.filter.GatewayFilter;
import org.springframework.cloud.gateway.filter.factory.AbstractGatewayFilterFactory;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.stereotype.Component;

@Component
public class AuditLabelGatewayFilterFactory
        extends AbstractGatewayFilterFactory<
                AuditLabelGatewayFilterFactory.Config> {

    private final Validator validator;

    public AuditLabelGatewayFilterFactory(Validator validator) {
        super(Config.class);
        this.validator = validator;
    }

    // AuditLabel=X-Lab-Tag,catalog_v1,true
    @Override
    public List<String> shortcutFieldOrder() {
        return List.of("headerName", "label", "overwrite");
    }

    @Override
    public GatewayFilter apply(Config config) {
        validateConfig(config);

        // Snapshot bất biến của cấu hình đã validate.
        final String headerName = config.getHeaderName();
        final String label = config.getLabel();
        final boolean overwrite = config.getOverwrite();

        return (exchange, chain) -> {
            ServerHttpRequest request = exchange.getRequest()
                    .mutate()
                    .headers(headers -> {
                        if (overwrite) {
                            headers.set(headerName, label);
                        } else {
                            headers.add(headerName, label);
                        }
                    })
                    .build();

            return chain.filter(
                    exchange.mutate().request(request).build());
        };
    }

    private void validateConfig(Config config) {
        if (config == null) {
            throw new IllegalArgumentException(
                    "AuditLabel config must not be null");
        }

        Set<ConstraintViolation<Config>> violations =
                validator.validate(config);
        if (!violations.isEmpty()) {
            throw new ConstraintViolationException(
                    "Invalid AuditLabel filter configuration",
                    violations);
        }

        // Quy tắc liên thuộc tính, sau @NotNull/@NotBlank.
        if (config.getLabel().length() > config.getMaxLabelLength()) {
            throw new IllegalArgumentException(
                    "AuditLabel label exceeds maxLabelLength");
        }
    }

    public static class Config {
        @NotBlank
        @Pattern(regexp = "X-[A-Za-z0-9-]{1,60}")
        private String headerName;

        @NotBlank
        @Pattern(regexp = "[A-Za-z0-9._-]{1,64}")
        private String label;

        @NotNull
        private Boolean overwrite;

        @NotNull
        @Min(1)
        @Max(64)
        private Integer maxLabelLength = 32;

        public String getHeaderName() {
            return headerName;
        }
        public void setHeaderName(String headerName) {
            this.headerName = headerName;
        }

        public String getLabel() {
            return label;
        }
        public void setLabel(String label) {
            this.label = label;
        }

        public Boolean getOverwrite() {
            return overwrite;
        }
        public void setOverwrite(Boolean overwrite) {
            this.overwrite = overwrite;
        }

        public Integer getMaxLabelLength() {
            return maxLabelLength;
        }
        public void setMaxLabelLength(Integer maxLabelLength) {
            this.maxLabelLength = maxLabelLength;
        }
    }
}
~~~

### Đọc kỹ những quyết định trong code

1. `super(Config.class)` khai báo kiểu binding mà factory chấp nhận.
2. `@Component` bảo đảm Spring có bean tên filter; class nằm trong package được scan.
3. `Config` có constructor không tham số ngầm định và **getters/setters công khai**.
4. `shortcutFieldOrder()` có **đúng ba field** nhận từ chuỗi rút gọn; field thứ tư giữ mặc định khi không khai báo.
5. `validator.validate(config)` **thực sự chạy** các annotation validation, không trông chờ cơ chế tự động không rõ ràng.
6. Sau khi annotation bảo đảm không null, code kiểm tra `label.length() <= maxLabelLength`.
7. Config được đọc **một lần ở `apply(config)`**, giá trị được copy vào các biến local final trước khi tạo lambda. Không đặt request-specific state vào Config.
8. Filter tạo `ServerHttpRequest` đã mutate rồi chuyển request mới bằng `exchange.mutate().request(...).build()`.
9. `headers.set` **thay** giá trị cũ; `headers.add` **thêm** một giá trị khác, nên có thể tạo repeated headers.
10. Không gọi `block()` trong Netty event-loop hoặc sửa request body không cần thiết.

### Vì sao validate trước lambda?

`Config` thuộc **route definition**, không phải dữ liệu thay đổi với mỗi request. Nếu đẩy validation vào lambda, request nào cũng tốn chi phí kiểm tra và lỗi cấu hình chỉ bộc lộ khi có traffic. Việc kiểm tra trong `apply(config)` cho phép route được đánh giá ngay khi chuyển từ definition sang filter runtime. Nếu route definitions được refresh, cấu hình mới phải qua quá trình bind/validate này lần nữa.

## 5. Hai cách ánh xạ args

### 5.1. Fully expanded: định danh trường rõ ràng

~~~yaml
filters:
  - name: AuditLabel
    args:
      headerName: X-Lab-Tag
      label: catalog_v1
      overwrite: true
      maxLabelLength: 32
~~~

Ý nghĩa:

~~~text
args.headerName      → Config.setHeaderName("X-Lab-Tag")
args.label           → Config.setLabel("catalog_v1")
args.overwrite       → Config.setOverwrite(Boolean.TRUE)
args.maxLabelLength  → Config.setMaxLabelLength(32)
~~~

Binder chuyển giá trị YAML sang type Java phù hợp. Nếu `overwrite: not_boolean` không convert được sang Boolean, đó là **lỗi binding/type conversion**, có thể xảy ra trước khi đến validator của code ví dụ.

Với config có nhiều trường, boolean, danh sách, chuỗi dài hoặc giá trị chứa dấu phẩy, **ưu tiên `name/args` đầy đủ** vì dễ review và kiểm tra.

### 5.2. Shortcut: phụ thuộc thứ tự

Trong factory:

~~~java
return List.of("headerName", "label", "overwrite");
~~~

Tương ứng với:

~~~yaml
filters:
  - AuditLabel=X-Lab-Tag,catalog_v1,true
~~~

| Vị trí | Tên trường | Giá trị nhận từ shortcut | Kiểu sau binding |
| ---: | --- | --- | --- |
| 1 | `headerName` | `X-Lab-Tag` | String |
| 2 | `label` | `catalog_v1` | String |
| 3 | `overwrite` | `true` | Boolean |

`maxLabelLength` không nằm trong shortcut nên vẫn là default 32. Dạng shortcut có thể dùng tốt cho các giá trị ngắn, không chứa dấu phẩy và được document chặt chẽ.

~~~yaml
# ĐÚNG
- AuditLabel=X-Lab-Tag,catalog_v1,true

# SAI: đảo vị trí, giá trị cuối không chuyển được sang boolean
- AuditLabel=X-Lab-Tag,true,catalog_v1

# SAI: thiếu overwrite, validation phải phát hiện null
- AuditLabel=X-Lab-Tag,catalog_v1
~~~

Không dùng shortcut cho những chuỗi tự do có dấu phẩy hoặc cấu trúc lồng nhau mà không kiểm tra quy tắc parser của phiên bản Gateway đang dùng. Gateway còn có `ShortcutConfigurable.shortcutType()` dành cho một số dạng đối số khác, nhưng factory trong bài **chỉ cần shortcut mặc định**.

## 6. Cấu hình route theo version Gateway Server WebFlux

Gateway chạy `localhost:8080`, backend echo ở `localhost:9091`; route `/api/demo/**` dùng filter custom và bỏ prefix `api`.

### Gateway Server WebFlux 5.x

~~~yaml
server:
  port: 8080

spring:
  application:
    name: custom-filter-gateway
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: demo-audit-label
              uri: http://localhost:9091
              predicates:
                - Path=/api/demo/**
                - Method=GET
              filters:
                - name: AuditLabel
                  args:
                    headerName: X-Lab-Tag
                    label: gateway_v1
                    overwrite: true
                    maxLabelLength: 32
                - StripPrefix=1
~~~

### Gateway Server WebFlux 4.2.x / 4.3.x

~~~yaml
server:
  port: 8080

spring:
  cloud:
    gateway:
      routes:
        - id: demo-audit-label
          uri: http://localhost:9091
          predicates:
            - Path=/api/demo/**
            - Method=GET
          filters:
            - AuditLabel=X-Lab-Tag,gateway_v1,true
            - StripPrefix=1
~~~

**Chỉ dùng namespace routes của version đang chạy.** Gateway 4.3.x vẫn có route definitions theo `spring.cloud.gateway.routes` trong tài liệu 4.3; Gateway 5.x dùng `spring.cloud.gateway.server.webflux.routes`. Không suy mọi property khác chỉ từ namespace route, nhất là các property đổi theo đợt nâng cấp.

### Kết quả kỳ vọng

Client gửi:

~~~http
GET /api/demo/echo HTTP/1.1
Host: localhost:8080
X-Lab-Tag: client_supplied
~~~

Gateway chọn route, `AuditLabel` dùng `overwrite=true` để thay giá trị thành `gateway_v1`, sau đó `StripPrefix=1` đưa path tới backend thành `/demo/echo`.

Trong ví dụ này, custom filter **không đọc body**, không cache body và không tạo request mới trên mỗi downstream attempt ngoài yêu cầu biến đổi header. Đừng cho rằng một filter thêm header là một security token validator.

## 7. Thực hành backend echo: kiểm chứng Config thực sự có tác dụng

Tạo ứng dụng Spring Boot WebFlux độc lập với dependency `spring-boot-starter-webflux` và port 9091:

~~~yaml
# application.yml của backend
server:
  port: 9091
~~~

Lớp khởi động `src/main/java/demo/echo/EchoApplication.java`:

~~~java
package demo.echo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class EchoApplication {
    public static void main(String[] args) {
        SpringApplication.run(EchoApplication.class, args);
    }
}
~~~

Controller `src/main/java/demo/echo/EchoController.java`:

~~~java
package demo.echo;

import java.util.List;
import java.util.Map;

import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class EchoController {

    @GetMapping("/demo/echo")
    public Map<String, Object> echo(ServerHttpRequest request) {
        List<String> tags =
                request.getHeaders()
                        .getOrDefault("X-Lab-Tag", List.of());
        return Map.of(
                "path", request.getPath().value(),
                "tags", tags);
    }
}
~~~

Backend này **chỉ dành cho lab**. Không công khai endpoint echo nhận token, cookie, thông tin định danh hoặc body nhạy cảm trong production.

Mở hai terminal ở hai dự án riêng (backend và Gateway), với Maven Wrapper:

~~~bash
./mvnw spring-boot:run
~~~

Trên Windows có thể dùng `mvnw.cmd spring-boot:run`. Các ví dụ chỉ mô tả cách tự thực hành; bài viết **không khẳng định đã chạy build/test trên môi trường repository**.

### 7.1. Kiểm tra request đầu tiên

~~~bash
curl -i "http://localhost:8080/api/demo/echo"
~~~

Kỳ vọng response:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"path":"/demo/echo","tags":["gateway_v1"]}
~~~

Điều đó cho thấy:

1. Route `demo-audit-label` đã được nạp và predicate `Path/Method` khớp.
2. Factory `AuditLabelGatewayFilterFactory` được tìm theo tên `AuditLabel`.
3. Config đã được bind và `apply(config)` trả GatewayFilter.
4. `StripPrefix=1` đổi path công khai thành path backend.

### 7.2. Test overwrite từ request do client đặt

~~~bash
curl -i "http://localhost:8080/api/demo/echo" \
  -H "X-Lab-Tag: client_supplied"
~~~

Với `overwrite=true`, backend vẫn phải nhận `gateway_v1`, không phải `client_supplied`.

Nếu chuyển thành `overwrite=false`, backend có thể nhận **hai giá trị**: một giá trị client gửi và một giá trị Gateway thêm. Đây chỉ là ví dụ để thấy khác biệt giữa `headers.set` và `headers.add`; **không dùng append cho header danh tính hoặc quyền truy cập mà backend sẽ tin**.

### 7.3. Chuyển sang shortcut

Thay filter definition thành:

~~~yaml
filters:
  - AuditLabel=X-Lab-Tag,short_v2,true
  - StripPrefix=1
~~~

Nạp lại route hoặc khởi động lại Gateway theo quy trình của phiên bản. Gọi lại endpoint GET; giá trị tag kỳ vọng đổi thành `short_v2`. Nếu backend vẫn thấy `gateway_v1`, hãy kiểm tra Gateway có **refresh route** chưa hoặc request đang đi qua một replica khác dùng cấu hình cũ.

### 7.4. Phân biệt route mismatch với lỗi Config

~~~bash
# Route chỉ khớp GET
curl -i -X POST "http://localhost:8080/api/demo/echo"

# Path ngoài predicate
curl -i "http://localhost:8080/other/echo"
~~~

Khi không có route/handler phù hợp khác, response có thể là 404. **Đây không chứng minh cấu hình custom factory sai**: một route không khớp sẽ không chạy GatewayFilter của nó.

## 8. Cấu hình sai: lỗi binding hay lỗi validation?

### 8.1. Thiếu trường bắt buộc

~~~yaml
- name: AuditLabel
  args:
    headerName: X-Lab-Tag
    label: gateway_v1
    # Thiếu overwrite
~~~

Trong code, `overwrite` là `Boolean` không có giá trị mặc định; `@NotNull` sẽ phát hiện thiếu trường khi `validator.validate(config)` chạy. Nếu dùng primitive `boolean`, giá trị thiếu có thể thành `false` và tránh được kiểm tra này.

### 8.2. Sai kiểu dữ liệu

~~~yaml
- name: AuditLabel
  args:
    headerName: X-Lab-Tag
    label: gateway_v1
    overwrite: not_boolean
~~~

Khi binder không thể convert chuỗi trên sang `Boolean`, cấu hình có thể thất bại **trước khi đến Bean Validation**. Vì vậy, việc chỉ bắt `ConstraintViolationException` chưa đủ để bao mọi lỗi cấu hình.

### 8.3. Giá trị không hợp lệ theo policy

~~~yaml
# Không được phép trong ví dụ
headerName: Authorization

# Không khớp pattern của label
label: "text with spaces"

# Ngoài khoảng được phép
maxLabelLength: 999
~~~

Đó lần lượt là lỗi `@Pattern`, `@Pattern` và `@Max`. Với Gateway production, phải có allowlist cho các header được tạo/chỉnh sửa để tránh vô ý ghi đè `Authorization`, `Cookie`, `Host` hoặc các forwarded headers.

### 8.4. Ràng buộc giữa các trường

~~~yaml
- name: AuditLabel
  args:
    headerName: X-Lab-Tag
    label: very_long_label
    overwrite: true
    maxLabelLength: 5
~~~

Các field có thể đúng kiểu và riêng lẻ hợp lệ, nhưng `label.length() > maxLabelLength`. Phần kiểm tra thủ công trong `validateConfig()` ngăn route được tạo với combination sai.

### 8.5. Typo ở tên args

~~~yaml
args:
  headerName: X-Lab-Tag
  label: gateway_v1
  overwite: true  # Sai tên overwrite
~~~

Tùy binder/version, unknown keys có thể bị từ chối hoặc bị bỏ qua. Trong ví dụ này, nếu key bị bỏ qua, field `overwrite` vẫn null và vi phạm `@NotNull`.

**Không nên giả định mọi unknown arg luôn gây lỗi**. Với cấu hình bảo mật, nên kiểm tra key names bằng schema/CI và test binding thật, không chỉ dựa vào default của framework.

## 9. Kiểm thử tự động cho Config và GatewayFilterFactory

### 9.1. Unit test không cần toàn bộ Gateway

Với JUnit Jupiter, AssertJ và một Jakarta Bean Validation provider:

~~~java
package demo.gateway.filters;

import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThatThrownBy;

class AuditLabelConfigTest {

    private static final ValidatorFactory VALIDATORS =
            Validation.buildDefaultValidatorFactory();

    private final Validator validator = VALIDATORS.getValidator();
    private final AuditLabelGatewayFilterFactory factory =
            new AuditLabelGatewayFilterFactory(validator);

    private AuditLabelGatewayFilterFactory.Config validConfig() {
        var c = new AuditLabelGatewayFilterFactory.Config();
        c.setHeaderName("X-Lab-Tag");
        c.setLabel("gateway_v1");
        c.setOverwrite(true);
        return c;
    }

    @Test
    void rejectMissingOverwrite() {
        var c = validConfig();
        c.setOverwrite(null);

        assertThatThrownBy(() -> factory.apply(c))
                .isInstanceOf(
                        jakarta.validation.ConstraintViolationException.class);
    }

    @Test
    void rejectSensitiveHeader() {
        var c = validConfig();
        c.setHeaderName("Authorization");

        assertThatThrownBy(() -> factory.apply(c))
                .isInstanceOf(
                        jakarta.validation.ConstraintViolationException.class);
    }

    @Test
    void rejectCrossFieldMismatch() {
        var c = validConfig();
        c.setMaxLabelLength(3);

        assertThatThrownBy(() -> factory.apply(c))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("maxLabelLength");
    }

    @AfterAll
    static void closeValidatorFactory() {
        VALIDATORS.close();
    }
}
~~~

Bộ test này thực sự gọi `factory.apply(config)` để chứng minh **validation có chạy**, thay vì chỉ kiểm tra annotations tồn tại. Cần thêm test cho giá trị hợp lệ và định dạng label, nhưng unit test **không xác minh YAML được Gateway binder ánh xạ đúng**.

### 9.2. Integration test phải kiểm tra đường binding thật

Với `@SpringBootTest`, `WebTestClient` và một backend stub/WireMock, cần chứng minh:

1. Config full `name/args` được đọc và backend nhận header.
2. Shortcut nhận đúng thứ tự và boolean conversion.
3. Sai boolean thất bại ở pha binding/conversion.
4. Thiếu/không hợp lệ bị validation từ chối.
5. Factory chưa được đăng ký tạo lỗi **không tìm được GatewayFilterFactory**.
6. Không có route nào vô tình bỏ qua filter bắt buộc khi definition sai.
7. Route refresh cũng kiểm tra lại Config mới.

Nếu framework materialize routes lazily, test cần **kích hoạt resolve route definitions** hoặc gửi request thích hợp; chỉ assert ApplicationContext khởi động là chưa đủ.

### 9.3. Ma trận kiểm thử âm

| Đầu vào | Kỳ vọng |
| --- | --- |
| Đúng full args | Tạo filter, header đúng |
| Đúng shortcut | Hành vi tương đương |
| Thiếu `headerName` | Validation error |
| Thiếu `label` | Validation error |
| Thiếu `overwrite` | Validation error |
| `overwrite: abc` | Binding/conversion error |
| `headerName: Authorization` | Validation error |
| `label: "a b"` | Validation error |
| `maxLabelLength: 0` hoặc 65 | Validation error |
| Label dài hơn maxLabelLength | Cross-field validation error |
| Typo `overwite` | Không chạy filter với fallback sai |
| Factory không được scan | Lỗi name resolution |
| Request không khớp `Path/Method` | Filter không chạy |

Không nên chuyển tất cả các lỗi này thành HTTP 400. Đây là **lỗi cấu hình hệ thống**, thường cần chặn deployment/route publication; chúng không phải lỗi caller của từng request.

## 10. Default, enum, list và nested Config

### 10.1. Chỉ dùng default có chủ đích

~~~java
private Integer maxLabelLength = 32;
~~~

Trường optional có thể có default hữu ích. Nhưng với những field mang ý nghĩa bảo mật, ví dụ `authRequired` hoặc `failOpen`, default nguy hiểm có thể khiến một typo trở thành **mở quyền truy cập**. Hãy yêu cầu khai báo rõ ràng hoặc chọn một default an toàn và kiểm tra logic.

### 10.2. Enum thay cho chuỗi tự do

Nếu một filter hỗ trợ hai chế độ:

~~~java
public enum WriteMode {
    OVERWRITE,
    APPEND
}
~~~

Dùng `WriteMode mode` giúp binder/validator phát hiện giá trị ngoài tập cho phép. Tuy nhiên, kiểm tra enum **không thay thế** kiểm tra quyền sử dụng từng mode theo route.

### 10.3. Cấu hình danh sách và object lồng nhau

Khi có nhiều quy tắc, nên khai báo `List<T>` hoặc nested Config typed:

~~~yaml
# Ví dụ một schema giả định, chưa có CustomPolicyGatewayFilterFactory
- name: CustomPolicy
  args:
    enabled: true
    allowedMethods:
      - GET
      - POST
    limits:
      maxBodyBytes: 131072
      timeoutMillis: 500
~~~

Muốn dùng được, phải tự tạo factory/Config thực tế, binding và validation cho **từng phần tử**. Dạng shortcut phân tách bằng dấu phẩy không phù hợp với cấu hình phức tạp. Nếu field là `Duration`/`DataSize`, quy định đơn vị và kiểm tra range, overflow, negative values.

### 10.4. Không đặt secrets trong args

Route definitions có thể được ghi log, hiển thị qua Actuator routes, lưu ở Config Server hoặc xuất hiện trong pipeline CI. **Không đặt private key, bearer token, client secret** vào `filters[].args`. Nếu factory cần credential, dùng secret manager/bean được inject và tránh in dữ liệu nhạy cảm trong `toString()` hoặc validation exception.

## 11. Config không phải nơi giữ trạng thái từng request

Factory thường là Spring singleton, còn filter được tạo từ Config có thể xử lý **nhiều requests đồng thời**. Không dùng `Config` làm chỗ lưu counter của một người dùng, nội dung body hay request ID:

~~~java
// SAI: minh họa tư duy sai, không phải code dùng được ở apply()
config.setLabel(requestIdOfCurrentUser);
~~~

Nếu request A và B cùng sửa một object Config, chúng có thể ghi đè dữ liệu nhau và rò thông tin. Với dữ liệu mỗi request, dùng biến local trong filter, `ServerWebExchange.getAttributes()` hoặc Reactor Context khi phù hợp. Với trạng thái phân tán như quota, cần store riêng và concurrency semantics rõ ràng.

Trong factory của bài, `headerName/label/overwrite` được chụp lại sau validation; mọi request chỉ đọc các giá trị ấy. Nếu Config thay đổi từ remote route source, cần **materialize filter mới** và có quy trình refresh/rollback thay vì mutate instance đang dùng.

## 12. Filter order, Retry và liên hệ bảo mật

### 12.1. Route order khác filter order

`order` của route quyết định route nào thắng khi nhiều predicates cùng khớp. `GatewayFilter` và `GlobalFilter` được tổng hợp/sắp xếp theo order trong một filter chain. Nếu cần thứ tự rõ ràng, có thể xem xét `OrderedGatewayFilter`, đồng thời hiểu pre/post phases của Gateway.

Không đặt order tùy tiện và cho rằng custom filter sẽ thay thế **Spring Security WebFilter**: đó là tầng bảo mật khác và cần policy riêng.

### 12.2. Retry có thể khiến một filter chạy nhiều lần

Theo cơ chế Retry, các filter **ở phần chain được thử lại** có thể chạy thêm lần nữa khi backend lỗi. Nếu custom filter ghi log audit, trừ quota hoặc tạo message ở mỗi attempt, một client request có thể gây side effects lặp.

Với `AuditLabel`, `overwrite=true` dùng `headers.set` giúp marker đơn trị và ít bị trùng hơn. `overwrite=false` dùng `headers.add` có thể phát sinh repeated header nếu nhiều filter/attempt cùng thêm giá trị. Cần test thực tế khi đặt cạnh Retry, circuit breaker và các filter biến đổi request.

### 12.3. Custom header không phải bằng chứng danh tính

Không nhận `X-Authenticated-User` do client gửi rồi forward xuống backend như một chứng chỉ xác thực. Nếu Gateway muốn truyền identity, nó phải **xác minh JWT/session trước**, xóa các header giả từ client và dùng trust boundary/kênh an toàn tới backend. Header `X-Lab-Tag` trong bài **chỉ phục vụ quan sát**.

## 13. Troubleshooting cấu hình filter

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| Không tìm thấy factory `AuditLabel` | Không có `@Component`, package scan sai, class name sai | Kiểm tra bean và tên filter |
| Shortcut sai, full args đúng | Thứ tự `shortcutFieldOrder()` không đúng | So mapping vị trí |
| Sai boolean nhưng route không hoạt động | Binding/conversion error | Logs route materialization |
| `ConstraintViolationException` | NotBlank/Pattern/NotNull/Min/Max | Sửa config ở nguồn |
| `IllegalArgumentException` max length | Ràng buộc liên thuộc tính | So label và maxLabelLength |
| Backend không nhận header | Route không khớp, filter chưa nạp, proxy xóa header | Quan sát route ID, request downstream |
| Backend thấy nhiều giá trị | `overwrite=false` hoặc filter khác thêm cùng header | Test set/append, Retry order |
| Một số routes bị ảnh hưởng ngoài ý định | Dùng GlobalFilter/default-filters | Kiểm tra scope filter |
| Error chỉ xuất hiện khi refresh | Config mới chưa validate hoặc route loading lazy | Validate CI và kiểm tra sau refresh |
| Startup không báo lỗi nhưng không có route | Sai namespace YAML hoặc source route | Kiểm tra routes runtime và cấu hình version |

Nếu dùng Spring Boot Actuator để quan sát route/filter runtime, **không expose management endpoints công khai trên Internet**. Logs nên có route ID, tên factory và loại lỗi cấu hình; không log nguyên args chứa secrets.

### Kiểm soát phát hành cấu hình

Một quy trình deploy có thể là:

1. Kiểm tra cú pháp YAML và schema/tên args.
2. Unit test `Config`, Bean Validation và cross-field rules.
3. Integration test binder với full/shortcut.
4. Materialize route definitions trong staging.
5. Smoke test HTTP request đi qua filter thực.
6. Chỉ publish/rollout khi đạt; nếu remote config có refresh, chuẩn bị rollback.

Đừng âm thầm bỏ filter bảo mật nếu route definition lỗi. Với một số version, route có thể biến mất hoặc báo error lúc truy vấn mà process vẫn còn sống; vận hành phải phát hiện bằng readiness/route audit chứ không chỉ kiểm tra JVM.

## 14. Checklist production

- [ ] Factory class có hậu tố `GatewayFilterFactory` và là Spring bean trong component scan.
- [ ] Dùng `AbstractGatewayFilterFactory<Config>` và `super(Config.class)`.
- [ ] Typed Config với getters/setters công khai, không dùng Map tự do khi không cần.
- [ ] Field bắt buộc không có default nguy hiểm; boolean bắt buộc có thể dùng `Boolean + @NotNull`.
- [ ] Kiểm tra chuỗi rỗng, độ dài, ký tự hợp lệ; kiểm tra số min/max.
- [ ] Chạy `Validator.validate(config)` **tường minh** và thêm cross-field checks.
- [ ] Full args rõ nghĩa, shortcut có `shortcutFieldOrder()` đúng và được test.
- [ ] Kiểm tra các trường không nhận sai kiểu/typo khi binder đổi version.
- [ ] Có unit tests và integration tests thực sự materialize routes.
- [ ] Không cho phép config tùy ý ghi đè auth/cookie/host/forwarded headers.
- [ ] Không chứa secret trong route args/log/Actuator.
- [ ] Config bất biến trong request path; custom filter không block reactive event loop.
- [ ] Test thứ tự filter, Retry, nhiều request đồng thời và response cuối.
- [ ] Có refresh/rollback, audit route và bảo vệ management endpoints.
- [ ] Không lẫn namespace Gateway Server WebFlux 4.x/5.x với Server MVC.

## 15. Câu hỏi tự kiểm tra

**1. Tại sao dùng `Boolean overwrite` thay cho `boolean overwrite`?**

Để `null` biểu diễn thiếu giá trị, cho phép `@NotNull` phát hiện lỗi; primitive boolean mặc định false có thể che typo.

**2. Khi dùng `AuditLabel=X-Lab-Tag,v1,true`, Gateway biết v1 ứng với trường nào?**

Từ vị trí thứ hai trong `shortcutFieldOrder()`, tương ứng `label`.

**3. Chỉ thêm `@Validated` vào Config có chắc chắn được kiểm tra trong mọi đường binding không?**

Không nên giả định. Ví dụ gọi `validator.validate(config)` trong `apply(config)` để kiểm tra tại thời điểm dựng filter.

**4. Vì sao `label` đúng pattern và `maxLabelLength` đúng range nhưng vẫn có thể bị từ chối?**

Vì còn quy tắc **liên thuộc tính**: chiều dài label không được vượt maxLabelLength.

**5. Tại sao ứng dụng khởi động được chưa đủ chứng minh mọi Config route đều hợp lệ?**

Việc convert route definitions có thể diễn ra lazy/refresh. Cần materialize routes và smoke test.

**6. Vì sao không nên để Config chứa request ID của từng người dùng?**

Vì filter có thể xử lý nhiều request đồng thời với cùng Config; sửa chung sẽ tạo race condition và rò trạng thái.

## 16. Tài liệu tham khảo

1. [Spring Cloud Gateway Server WebFlux — Developer Guide](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/developer-guide.html): custom `GatewayFilterFactory`, `AbstractGatewayFilterFactory` và naming convention.
2. [Gateway WebFlux 4.3 — Developer Guide](https://docs.spring.io/spring-cloud-gateway/reference/4.3/spring-cloud-gateway-server-webflux/developer-guide.html): đối chiếu dòng 4.3.
3. [Gateway WebFlux — Configuring Route Predicate and Filter Factories](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/configuring-route-predicate-factories-and-filter-factories.html): shortcut và fully expanded args.
4. [Gateway WebFlux 4.3 — Filter Factory Configuration](https://docs.spring.io/spring-cloud-gateway/reference/4.3/spring-cloud-gateway-server-webflux/configuring-route-predicate-factories-and-filter-factories.html): cú pháp route 4.3.
5. [Spring Blog — Creating a Custom Spring Cloud Gateway Filter](https://spring.io/blog/2022/08/26/creating-a-custom-spring-cloud-gateway-filter/): `shortcutFieldOrder()` và request mutation.
6. [Spring Framework — Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html): Jakarta Validator và Spring integration.
7. [Spring Cloud Gateway — Global Filters and Ordering](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/global-filters.html): thứ tự filter và pre/post phases.

**Ghi nhớ:** Trong custom GatewayFilterFactory của WebFlux, **`Config` là hợp đồng giữa route YAML và Java**, `shortcutFieldOrder()` là hợp đồng thứ tự cho shortcut, còn `apply(config)` là điểm phù hợp để **kiểm tra config trước khi tạo filter**. Dùng kiểu dữ liệu rõ ràng, defaults có chủ đích, validation tường minh và tests cho cả YAML hợp lệ lẫn lỗi. Một custom filter chất lượng không chỉ chạy đúng khi cấu hình tốt, mà còn **không âm thầm hoạt động với cấu hình nguy hiểm**.

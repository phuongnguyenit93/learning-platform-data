# Đóng gói bộ lọc dùng chung và quản lý tương thích phiên bản trong Spring Cloud Gateway

Trong một hệ thống microservices, nhiều Gateway hoặc nhiều route có thể cùng cần các chức năng như gắn mã tương quan, chuẩn hóa header nội bộ, ghi nhận metrics, kiểm tra giới hạn kích thước và bổ sung metadata khi chuyển tiếp request. Viết lại những logic đó trên từng route hay sao chép Java source giữa các dự án sẽ tạo ra **sự khác biệt khó kiểm soát**, đặc biệt khi Spring Boot hoặc Spring Cloud được nâng cấp.

Với **SPRING_CLOUD_GATEWAY**, cách tiếp cận bền vững là **đóng gói custom filter thành thành phần có hợp đồng rõ ràng, phát hành thành thư viện/starter dùng chung và kiểm thử tương thích theo từng release train**. Bài thuộc chương **Bộ lọc tùy biến**, tập trung vào câu hỏi: *Làm thế nào để nhiều Gateway tái sử dụng cùng filter mà vẫn có thể cấu hình riêng, an toàn về reactive execution, không đụng tên factory và nâng cấp phiên bản có kiểm soát?*

Ngữ cảnh xuyên suốt là Gateway phục vụ route predicates, filter chain, biến đổi path/header, service discovery/load balancing, xác thực, rate limiting, circuit breaker, retry, TLS và quan sát request. Custom filter phải tích hợp với các lớp ấy chứ **không tự giả định có thể thay thế những cơ chế chuẩn**.

> **Phạm vi:** Ví dụ Java hướng đến **Spring Cloud Gateway Server WebFlux**, thường triển khai cùng Spring Boot 3.x/Spring Security reactive và một Spring Cloud release train tương thích. Các dòng Gateway mới hơn có thể đổi starter, artifact, namespace, API và điều kiện auto-configuration. **Gateway Server MVC sử dụng mô hình khác**, không nên nhận cùng filter WebFlux qua classpath rồi kỳ vọng hoạt động. Thư viện dùng chung cần khai báo rõ những phiên bản **đã kiểm thử**, không chỉ ghi một dải version theo cảm tính.

## 1. Phân biệt các điểm mở rộng trước khi tạo thư viện

Trong Spring Cloud Gateway Server WebFlux, các loại filter phổ biến không có cùng phạm vi.

| Thành phần | Khi nào chạy? | Cách cấu hình/chia sẻ | Cảnh báo |
|---|---|---|---|
| `GatewayFilterFactory` | Factory tạo `GatewayFilter` gắn với một route đã match | YAML/Java route DSL, hoặc `default-filters` | Phù hợp filter có `args` cấu hình theo route |
| `GlobalFilter` | Tham gia filter chain của các Gateway routes đã được chọn | Bean trong ứng dụng | Không đồng nghĩa WebFilter bao phủ mọi request không match route |
| `WebFilter` | Trong Spring WebFlux filter chain ở tầng web | Bean/WebFlux registration | Có thể chạy trước route selection; khác về thứ tự và phạm vi |
| `SecurityWebFilterChain` | Xác thực/phân quyền reactive theo security matcher | Spring Security `ServerHttpSecurity` | Không thay bằng header kiểm tra thủ công trong GatewayFilter |
| Built-in filter | Các trường hợp Gateway hỗ trợ sẵn | `RewritePath`, `SetRequestHeader`, `RequestRateLimiter`... | Ưu tiên dùng built-in nếu đủ nhu cầu |

**Nguyên tắc:** Nếu mỗi route cần một tham số khác nhau như `prefix` hoặc hành vi bật/tắt, hãy bắt đầu với **`GatewayFilterFactory`**. Nếu cần chức năng nhất quán trên mọi route Gateway, cân nhắc **`GlobalFilter`**. Nếu cần chặn request kể cả trước khi tìm route (ví dụ logic xác thực, CORS, một số quy tắc edge), phải xem xét tầng **`WebFilter`, Spring Security hoặc ingress** tương ứng.

### Điều gì diễn ra trong pipeline?

~~~mermaid
flowchart TD
    C["Client HTTP request"] --> W["WebFlux WebFilters / Spring Security"]
    W --> M{"Route predicates khớp?"}
    M -->|Không| N["Handler khác / 404 theo cấu hình"]
    M -->|Có| F["FilteringWebHandler"]
    F --> O["Sắp xếp GlobalFilter và GatewayFilter theo order"]
    O --> X["Custom EdgeRequestId GatewayFilter"]
    X --> R["Built-in filters: path/header/Retry/RateLimiter..."]
    R --> B["Routing Netty / LoadBalancer lb://"]
    B --> S["Backend microservice"]
    S --> P["Response đi ngược filter chain"]
~~~

**Không coi thứ tự trong sơ đồ là một thứ tự cứng cho mọi phiên bản.** `GlobalFilter` và route-specific `GatewayFilter` được ghép, sắp theo `Ordered`. Nhiều filter còn có logic trước/sau `chain.filter(exchange)`. Các điểm cần quan sát là **lúc header được thêm**, **lúc path bị rewrite**, **lúc request đi downstream** và **lúc response commit**.

## 2. Chọn một hợp đồng nhỏ, ổn định để tái sử dụng

Ta xây ví dụ **`EdgeRequestIdGatewayFilterFactory`**:

- Nhận cấu hình `prefix` theo route, ví dụ `edge-` hoặc `orders-`.
- Mỗi request tạo một mã mới và **ghi đè** header `X-Edge-Request-Id` trước khi gửi xuống backend.
- Không nhận mã tương quan từ client làm dữ liệu đáng tin. Đây là ID để chẩn đoán, **không phải token xác thực**.
- Giữ nguyên method, path, query, body và không đọc request body.
- Không sử dụng I/O blocking hoặc trạng thái request trong field dùng chung của Bean.
- Có tên factory public ổn định: `EdgeRequestId`.
- Validate cấu hình **khi factory tạo filter** thay vì phát hiện prefix sai cho mỗi request.

### Hợp đồng chức năng

| Đầu vào | Kết quả | Điều không được làm |
|---|---|---|
| Request có `X-Edge-Request-Id: forged` | Header downstream được thay bằng ID do Gateway tạo | Không tin header client là ID đã xác minh |
| Request không có header | Thêm header mới | Không thay đổi body/query |
| Hai requests đồng thời | Hai ID được tạo độc lập | Không dùng static mutable counter không đồng bộ |
| Prefix `orders-` | Giá trị dạng `orders-<UUID>` | Không để prefix không hợp lệ phá cú pháp HTTP |
| Prefix trống/quá dài/ký tự ngoài allowlist | Từ chối cấu hình | Không âm thầm chèn CR/LF hoặc text lạ vào header |
| Route không match | Factory của route đó không chạy | Không gắn nhầm ID ở handler khác |

Đây là ví dụ đủ nhỏ để minh họa **thiết kế API thư viện**, nhưng có thể ứng dụng nguyên tắc tương tự cho header policy, metrics, auditing, định tuyến theo metadata hoặc một số filter resilience tùy biến. Chỉ tạo custom filter khi built-in factory không đáp ứng yêu cầu; mỗi API tự viết là thêm một trách nhiệm tương thích và bảo trì.

## 3. Triển khai một GatewayFilterFactory độc lập

Tạo class trong module thư viện, **không cần `@Component`** vì ở phần đóng gói starter ta sẽ đăng ký Bean qua auto-configuration. Nếu chỉ viết ngay trong một Gateway app, bạn có thể dùng `@Bean` hoặc một cơ chế component scanning nhất quán, nhưng **không dùng cả hai cách đăng ký cùng factory**.

~~~java
package com.acme.edge.filters;

import java.util.List;
import java.util.UUID;
import org.springframework.cloud.gateway.filter.GatewayFilter;
import org.springframework.cloud.gateway.filter.factory.AbstractGatewayFilterFactory;
import org.springframework.http.server.reactive.ServerHttpRequest;

public final class EdgeRequestIdGatewayFilterFactory
        extends AbstractGatewayFilterFactory<
                EdgeRequestIdGatewayFilterFactory.Config> {

    public static final String HEADER_NAME = "X-Edge-Request-Id";

    public EdgeRequestIdGatewayFilterFactory() {
        super(Config.class);
    }

    @Override
    public GatewayFilter apply(Config config) {
        String prefix = config.getPrefix();

        // Chạy khi cấu hình route tạo filter, tránh đầu vào không an toàn.
        if (prefix == null || !prefix.matches("[A-Za-z0-9_-]{1,24}")) {
            throw new IllegalArgumentException(
                "EdgeRequestId.prefix must be 1..24 safe characters");
        }

        // Lưu cấu hình bất biến cho filter được áp dụng trên route này.
        return (exchange, chain) -> {
            String value = prefix + UUID.randomUUID();

            ServerHttpRequest request = exchange.getRequest()
                .mutate()
                .headers(headers -> headers.set(HEADER_NAME, value))
                .build();

            return chain.filter(
                exchange.mutate().request(request).build());
        };
    }

    @Override
    public List<String> shortcutFieldOrder() {
        return List.of("prefix");
    }

    public static final class Config {
        private String prefix = "edge-";

        public String getPrefix() {
            return prefix;
        }

        public void setPrefix(String prefix) {
            this.prefix = prefix;
        }
    }
}
~~~

### Phân tích từng lựa chọn

1. **`AbstractGatewayFilterFactory<Config>`** cung cấp nền tảng factory để Gateway bind cấu hình thành đối tượng `Config`.
2. Tên class kết thúc bằng **`GatewayFilterFactory`**, tạo tên filter cấu hình ngắn **`EdgeRequestId`** theo quy ước đặt tên của Gateway. Không dùng suffix không đúng hoặc mặc định tên Bean Java là tên factory sẽ hiển thị trong YAML.
3. **`Config` là static nested class có no-arg constructor và getter/setter** để binding dễ thực hiện theo cách factory phổ biến. Mỗi route có thể dùng giá trị `prefix` riêng.
4. Validate `prefix` khi `apply` chạy. Allowlist chỉ gồm chữ ASCII, số, gạch ngang và gạch dưới; chặn trường hợp ký tự CR/LF và giá trị tùy ý.
5. `headers.set(...)` **thay toàn bộ giá trị cùng tên** trên request mới, khác `add(...)` có thể giữ thêm giá trị do client gửi.
6. `exchange.getRequest().mutate()` và `exchange.mutate()` tạo wrapper chứa request đã thay đổi, thay vì cố sửa object request bất biến.
7. `chain.filter(...)` luôn được gọi **đúng một lần** trong nhánh thành công. Filter không tự dừng request hoặc phát response.
8. Không dùng `block()`, không subscribe bằng tay và không chia sẻ trạng thái request trong field Bean.
9. `UUID` ở đây là định danh chẩn đoán, **không dùng làm mật khẩu, access token, bằng chứng quyền truy cập hoặc khóa idempotency nghiệp vụ**.
10. `shortcutFieldOrder()` cho phép binder ánh xạ shortcut `EdgeRequestId=orders-` vào `Config.prefix`.

**Lưu ý về Java version:** Code dùng `List.of` (Java 9+) và `UUID.randomUUID()`. Trong các dòng Spring Boot 3 thường cần Java 17 trở lên. Với dòng nền tảng khác, chọn Java target tương thích theo ma trận phiên bản và CI, không tự build bằng Java mới rồi phát hành cho runtime cũ.

## 4. Dùng filter theo route và dùng chung qua default-filters

### Expanded configuration

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: orders-api
          uri: lb://orders-service
          predicates:
            - Path=/api/orders/**
          filters:
            - name: EdgeRequestId
              args:
                prefix: orders-
            - StripPrefix=1
~~~

`EdgeRequestId` là factory **đã được đăng ký Bean** trong Gateway. Nếu starter chưa được thêm hoặc auto-configuration chưa chạy, Gateway có thể báo không tìm được `GatewayFilterFactory` tương ứng.

### Shortcut configuration

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: catalog-api
          uri: lb://catalog-service
          predicates:
            - Path=/api/catalog/**
          filters:
            - EdgeRequestId=catalog-
~~~

Dạng này dùng `shortcutFieldOrder()` để map giá trị sau dấu `=` vào `prefix`. Với filter có nhiều field phức tạp, ưu tiên **expanded form** để dễ review, kiểm tra type và phát hiện cấu hình thiếu.

### Dùng một chính sách chung trên nhiều route

~~~yaml
spring:
  cloud:
    gateway:
      default-filters:
        - EdgeRequestId=edge-
      routes:
        - id: orders
          uri: lb://orders-service
          predicates:
            - Path=/api/orders/**
        - id: catalog
          uri: lb://catalog-service
          predicates:
            - Path=/api/catalog/**
~~~

`default-filters` là lựa chọn phù hợp nếu mọi **Gateway route** đều cần header ấy. Nhưng:

- **Không** tự cho rằng filter chạy với request không match bất kỳ Gateway route nào.
- Không khai báo thêm `EdgeRequestId` trên từng route nếu không muốn cùng một request chạy hai lần và tạo hai ID.
- Khi có route từ DiscoveryClient locator, kiểm tra filter list thực tế và version để biết default filters được áp dụng đúng như thiết kế.
- Khi cần chính sách điều kiện theo tenant/route, hãy cân nhắc cấu hình riêng thay vì dùng một prefix toàn cục.
- Nếu cần phát ID trước security hoặc trước route matching, một `GatewayFilterFactory` không đáp ứng mục tiêu đó; lựa chọn tầng filter khác phải được thiết kế rõ.

### Filter này không tự gửi ID về client

Ví dụ chỉ tạo **request header Gateway → downstream**. Client sẽ **không tự nhìn thấy** `X-Edge-Request-Id` trong response. Nếu muốn trả correlation ID về client, hãy thêm một cơ chế response header được đặt **trước response commit**, cân nhắc CORS `exposedHeaders` và bảo vệ tránh rò metadata. Đừng nhầm `request.getHeaders()` với `response.getHeaders()`.

## 5. Vì sao không dùng một GlobalFilter cho mọi trường hợp?

Một `GlobalFilter` dễ đóng gói khi chức năng áp dụng giống nhau cho tất cả Gateway routes:

~~~java
package com.acme.edge.filters;

import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.cloud.gateway.filter.GlobalFilter;
import org.springframework.core.Ordered;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

public final class RequestMarkerGlobalFilter
        implements GlobalFilter, Ordered {

    @Override
    public int getOrder() {
        return -100;
    }

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            GatewayFilterChain chain) {
        // Mã minh họa: thực hiện policy/tracing đáng tin cậy ở đây.
        return chain.filter(exchange);
    }
}
~~~

Đoạn này chỉ minh họa **chữ ký API và order**, chưa thực hiện chức năng cụ thể. `getOrder() = -100` là số minh họa, **không phải vị trí chạy được bảo đảm an toàn với tất cả filter built-in**.

| Nhu cầu | Ưu tiên |
|---|---|
| Prefix khác nhau theo route | `GatewayFilterFactory` |
| Có khả năng bật/tắt bằng YAML trên một route | `GatewayFilterFactory` |
| Chính sách chung cho tất cả Gateway routes | `GlobalFilter` hoặc `default-filters` tùy cấu hình |
| Chỉ xử lý nhóm path public bằng code ở tầng web | `WebFilter` hoặc security/web routing tương ứng |
| Xác thực Bearer JWT, phân quyền scope | **Spring Security WebFlux**, không phải custom header filter |
| Rate limiting theo user/tenant | Built-in `RequestRateLimiter` + `KeyResolver` trước khi viết limiter khác |
| Retry/CircuitBreaker | Built-in factories theo release train trước khi tạo custom behavior |

**Không đăng ký đồng thời một GlobalFilter và một route filter làm cùng công việc** trừ khi đã có kế hoạch chống lặp. Với observability, điều này có thể tạo hai metrics, hai header hoặc hai span cho cùng request.

## 6. Thiết kế cấu trúc thư viện và starter dùng chung

Một cách tổ chức được nhiều nhóm sử dụng là tách **logic filter** ra khỏi **cơ chế đăng ký Bean/auto-configuration**.

~~~text
edge-gateway-filters/
  edge-filters-core/
    src/main/java/com/acme/edge/filters/
      EdgeRequestIdGatewayFilterFactory.java
  edge-filters-autoconfigure/
    src/main/java/com/acme/edge/autoconfigure/
      EdgeFiltersAutoConfiguration.java
    src/main/resources/META-INF/spring/
      org.springframework.boot.autoconfigure.AutoConfiguration.imports
  edge-filters-starter/
    dependency: edge-filters-core + edge-filters-autoconfigure
  edge-filters-test/
    kiểm thử contract và tương thích với các Gateway runtime
~~~

Đây là **sơ đồ cấu trúc đề xuất**, không phải yêu cầu phải tạo bốn module ngay. Với một filter nhỏ, một thư viện có core + auto-config vẫn có thể phù hợp. Khi thư viện phát triển, tách phần API và tự động đăng ký giúp:

- Không ép tất cả các Gateway phải cài một tập dependencies không dùng tới.
- Cho phép app đăng ký Bean thủ công nếu không dùng starter.
- Quản lý optional integrations như metrics, Redis hoặc Spring Security.
- Phát hành cùng một implementation và test suite cho nhiều Gateway ứng dụng.
- Phân biệt rõ **package API public** với class/helper nội bộ có thể thay đổi.

### Quy tắc cho dependency

Nếu custom filter chỉ sử dụng `AbstractGatewayFilterFactory`, `GatewayFilter` và WebFlux HTTP API, đừng kéo thêm starter OAuth2, Redis hay database không cần thiết vào mọi consumer.

Ở module thư viện:

- Khai báo dependency để **compile được các Gateway/WebFlux API** theo đúng release train; chọn `api`/`implementation`/`compileOnly` tùy mô hình Gradle và runtime ownership.
- Với starter, công bố dependencies cần thiết một cách có chủ đích, không “shade” hay nhúng lại Spring Framework/Spring Cloud classes vào JAR của bạn.
- Không tự chốt version Spring Cloud riêng mâu thuẫn với **BOM của ứng dụng tiêu thụ**.
- Nếu cần JUnit, Reactor Test và test-support classes, đặt vào **test scope**.
- Nếu cần Spring Boot auto-configuration, phụ thuộc vào `spring-boot-autoconfigure` phù hợp, không copy API AutoConfiguration của dòng Boot khác.

**Thư viện dùng chung là một sản phẩm có release**, không chỉ một gói Java có thể copy-paste. Nó cần version, changelog, contract, upgrade guide và phạm vi hỗ trợ rõ ràng.

## 7. Auto-configuration trong starter Spring Boot

Đối với **Spring Boot 3.x**, một thư viện có thể cung cấp class auto-configuration để người dùng chỉ cần thêm dependency mà không phải tự tạo Bean.

~~~java
package com.acme.edge.autoconfigure;

import com.acme.edge.filters.EdgeRequestIdGatewayFilterFactory;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.autoconfigure.condition.ConditionalOnWebApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.cloud.gateway.filter.factory.AbstractGatewayFilterFactory;

@AutoConfiguration
@ConditionalOnClass(AbstractGatewayFilterFactory.class)
@ConditionalOnWebApplication(
    type = ConditionalOnWebApplication.Type.REACTIVE)
@ConditionalOnProperty(
    prefix = "acme.gateway.edge-request-id",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = true)
public class EdgeFiltersAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(EdgeRequestIdGatewayFilterFactory.class)
    EdgeRequestIdGatewayFilterFactory edgeRequestIdGatewayFilterFactory() {
        return new EdgeRequestIdGatewayFilterFactory();
    }
}
~~~

**Ý nghĩa các điều kiện:**

- `@AutoConfiguration`: Spring Boot nhận diện cấu hình khi starter được khai báo đúng cách.
- `@ConditionalOnClass`: chỉ tạo Bean nếu các API Gateway cần thiết hiện diện trên classpath.
- `@ConditionalOnWebApplication(Type.REACTIVE)`: không tự gắn filter WebFlux vào một web stack Servlet/MVC.
- `@ConditionalOnProperty`: cho phép tắt tính năng nếu một app không muốn đăng ký factory.
- `@ConditionalOnMissingBean`: cho ứng dụng tự thay thế Bean factory khi cần tùy biến implementation.

### Tệp đăng ký AutoConfiguration.imports

Với cơ chế auto-configuration của Spring Boot 3.x, JAR auto-config cần chứa đúng path:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Nội dung file văn bản đó là **tên class đầy đủ**, mỗi dòng một class:

~~~text
com.acme.edge.autoconfigure.EdgeFiltersAutoConfiguration
~~~

Đây là nội dung phải được **đóng gói trong JAR**, không phải một thuộc tính `application.yml`. Có file source Java nhưng thiếu AutoConfiguration.imports thì app tiêu thụ **có thể không tự đăng ký Bean**.

**Lưu ý tương thích:** Ở các thế hệ Spring Boot cũ hơn, auto-configuration từng dùng `META-INF/spring.factories` với entry `EnableAutoConfiguration`. Không mặc định một starter viết cho Boot 3 sẽ hoạt động trên Boot 2, hoặc ngược lại. Chọn cơ chế và API cho từng dải phiên bản mà bạn **thực sự build/test**, không thêm đồng thời hai kiểu cấu hình để che giấu vấn đề version.

### Tránh double registration

Nếu class `EdgeRequestIdGatewayFilterFactory` được gắn `@Component` và auto-configuration cũng có `@Bean`, nhiều ứng dụng có thể vô tình đăng ký trùng factory. Khi đó:

- Có thể phát sinh xung đột tên Bean hoặc factory name.
- Tên filter `EdgeRequestId` có thể bị resolve không như mong đợi.
- Cấu hình có thể chạy đúng trên một app nhưng lỗi trên app khác do component scanning.

**Thiết kế rõ một cơ chế sở hữu Bean:** core không annotate component; starter đăng ký qua auto-config; app cần override thì cung cấp Bean trước theo contract được kiểm thử.

## 8. Ứng dụng tiêu thụ starter cần gì?

Sau khi phát hành artifact vào repository nội bộ, một Gateway application có thể phụ thuộc starter tương ứng.

Ví dụ **ý tưởng cấu trúc dependency** của một ứng dụng Gradle với BOM Spring Boot/Spring Cloud đã cấu hình ở build cấp dự án:

~~~groovy
dependencies {
    // Chọn đúng tên Gateway Server WebFlux starter của release train.
    implementation 'org.springframework.cloud:spring-cloud-starter-gateway-server-webflux'

    // Version riêng của thư viện, được kiểm thử với Boot/Cloud BOM này.
    implementation 'com.acme.platform:edge-filters-starter:1.4.0'
}
~~~

Các tọa độ `com.acme.platform` và version `1.4.0` là **giả định minh họa**, không phải artifact sẵn có. Tên starter Gateway thay đổi giữa các dòng Spring Cloud Gateway; nhiều tài liệu cũ dùng `spring-cloud-starter-gateway`. Chọn đúng runtime dependency qua BOM và tài liệu chính thức của dự án.

Cấu hình ứng dụng:

~~~yaml
acme:
  gateway:
    edge-request-id:
      enabled: true

spring:
  cloud:
    gateway:
      routes:
        - id: profile-api
          uri: lb://profile-service
          predicates:
            - Path=/api/profile/**
          filters:
            - EdgeRequestId=profile-
~~~

Khi Gateway khởi động:

1. Starter được tải trên classpath.
2. Boot nhận diện auto-configuration từ JAR.
3. Các điều kiện đúng nên Bean `EdgeRequestIdGatewayFilterFactory` được đăng ký.
4. Gateway bind `EdgeRequestId=profile-` thành `Config.prefix` và tạo `GatewayFilter`.
5. Request match route tạo ID và forward header mới.

Nếu bật `enabled: false`, Bean có thể không được tạo; **những routes vẫn tham chiếu `EdgeRequestId` sẽ không thể bind filter thành công**. Vì vậy tắt factory phải đi kèm thay đổi config route hoặc một kế hoạch fallback hợp lệ. Không xem flag disable là một cách “tự bỏ qua filter YAML” trong mọi phiên bản.

## 9. Thiết kế API ổn định: tên factory và args là hợp đồng public

Với thư viện Gateway filters, **hợp đồng công khai không chỉ là method Java**. Nó còn gồm:

- **Tên factory** trong YAML: `EdgeRequestId`.
- **Tên và kiểu args**: `prefix` là string; giới hạn độ dài/charset.
- **Shortcut syntax**: `EdgeRequestId=edge-` theo `shortcutFieldOrder`.
- **Phạm vi route/default-filters**.
- **Thời điểm thực thi và tác dụng lên path/header/body**.
- **Hành vi lỗi**: không hợp lệ thì fail cấu hình hay bỏ qua?
- **Tương tác với security, rate limiter, retry, circuit breaker và caching**.
- **Tên header tạo/ghi đè** và chính sách không tiết lộ.
- **Phiên bản Java, Spring Boot, Spring Cloud/Gateway hỗ trợ**.

### Ví dụ thay đổi gây breaking change

| Thay đổi | Có nguy cơ breaking? | Vì sao |
|---|---|---|
| Đổi `EdgeRequestId` thành `RequestId` | **Có** | YAML của các app tiêu thụ không còn tìm đúng factory |
| Đổi `prefix` thành `valuePrefix` không có alias | **Có** | Binder không nhận args cũ |
| Đổi shortcut field order | **Có** | Các route shorthand map sai giá trị |
| Đổi từ `headers.set` sang `headers.add` | **Có** | Contract chống giả mạo và multi-value header thay đổi |
| Tự động tạo ID cả khi route không match | **Có** | Thay phạm vi hoạt động và metrics |
| Bổ sung một field optional có default giữ nguyên behavior | Thường không | Cần vẫn kiểm thử binder và backward compatibility |
| Thêm validation chặt hơn | Có thể | Config cũ từng chạy có thể bị từ chối |
| Thay tên package public class | Có thể | Mã Java consumer và auto-config có thể bị ảnh hưởng |
| Thay Java bytecode target lên Java mới | **Có** | Runtime cũ không load class |
| Chỉ thay implementation nội bộ, giữ semantics | Thường không | Vẫn cần contract tests phát hiện hồi quy |

Nên viết release notes **theo góc nhìn người dùng YAML**: cấu hình cũ có còn chạy không, giá trị nào bị từ chối, header thay đổi ra sao, route order có đổi không.

### Schema/config metadata

Nếu một filter có nhiều tham số, hãy duy trì tài liệu cho từng tham số: tên, loại, default, validation, ví dụ expanded và shortcut. Spring Boot configuration metadata cho `@ConfigurationProperties` có thể hữu ích với các thuộc tính auto-config như `acme.gateway.edge-request-id.enabled`, nhưng **args của GatewayFilterFactory không tự giống hoàn toàn một `@ConfigurationProperties` thông thường**.

Không ghi default vào ba nơi rồi để lệch nhau: class `Config`, docs và integration tests phải có cùng kỳ vọng.

## 10. Ma trận tương thích và release train

Spring Cloud Gateway phát hành trong hệ sinh thái **Spring Boot + Spring Cloud release train + Spring Framework + Reactor Netty**. Không nên chọn một artifact version chỉ vì “là bản mới nhất” rồi ép vào app đang chạy phiên bản khác.

Ma trận nên được **xây dựng từ BOM chính thức và kiểm thử thực tế**, ví dụ dạng biểu mẫu:

| Nền tảng của app | Gateway stack | Phiên bản thư viện | Kết quả kiểm thử |
|---|---|---|---|
| Boot dòng A, Cloud train A | Gateway Server WebFlux tương thích A | edge-filters 1.3.x | `SUPPORTED` sau khi chạy CI |
| Boot dòng B, Cloud train B | Gateway Server WebFlux tương thích B | edge-filters 1.4.x | `SUPPORTED` sau khi chạy CI |
| Boot dòng C, Cloud train C | Gateway Server MVC | edge-filters WebFlux | **UNSUPPORTED** nếu chưa có implementation MVC |
| Boot dòng D, Cloud train D | Gateway WebFlux major mới | edge-filters 1.x cũ | `UNVERIFIED` cho đến khi build/test |
| Khác Java runtime target | Bất kỳ | JAR bytecode quá mới | **UNSUPPORTED** |

**A/B/C/D trong bảng chỉ là placeholders**, không phải tên release train thực. Những cột cần điền bằng version cụ thể từ BOM và tài liệu hiện hành của tổ chức. Không tuyên bố hỗ trợ chỉ vì Maven/Gradle giải quyết dependencies thành công.

### Những ranh giới nâng cấp phải kiểm tra

1. **Spring Boot major:** annotation, auto-configuration discovery, minimum Java, AOT/native, property binding.
2. **Spring Cloud release train:** BOM và cặp tương thích với Boot.
3. **Gateway Server WebFlux vs MVC:** package, filter abstraction, request/response API và routing model.
4. **Spring Framework/Reactor:** method signatures, Context propagation, Netty/HTTP encoding và cancellation.
5. **Third-party dependencies:** Caffeine, Micrometer, Jackson, Security, Resilience4j nếu filter phụ thuộc.
6. **Application config namespace:** cách đặt `spring.cloud.gateway.*` có thể thay đổi; không hardcode namespace phiên bản cũ vào hướng dẫn của dòng mới.
7. **Native image/AOT:** reflection/binding của `Config`, auto-config và hints nếu dự án thực sự build native.
8. **Classloader/dependency conflict:** hai JAR khác version cùng cung cấp factory name có thể gây lỗi khó chẩn đoán.

### Version công bố của chính thư viện

Một chính sách dễ hiểu:

- **MAJOR:** đổi tên factory/args, behavior hay nền tảng hỗ trợ theo cách breaking.
- **MINOR:** thêm factory/feature tương thích ngược, field optional mới có default an toàn.
- **PATCH:** sửa bug giữ nguyên contract.

Đây là một cách ứng dụng **semantic versioning**, không phải cam kết mọi lỗi chỉ cần patch. Nếu một bản sửa bảo mật bắt buộc thay hành vi, phải ghi rõ migration impact và kế hoạch rollout.

### Không trộn hai Gateway majors tùy tiện

Một starter WebFlux xây theo API của một release train **không nên tự quảng cáo tương thích** với mọi train bằng cách dùng version range rộng hoặc loại exclusions để ép classpath. Nếu yêu cầu hỗ trợ nhiều nền tảng, có thể phát hành:

- Một nhánh/vòng release cho Boot/Cloud cũ còn được tổ chức hỗ trợ.
- Một nhánh cho Boot/Cloud mới và code adaptation riêng khi API thay đổi.
- Một hợp đồng YAML ổn định phía trên, nhưng implementation tương ứng từng line.

Giữ tối thiểu các line còn hỗ trợ để giảm chi phí bảo trì. **Tương thích runtime phải được chứng minh**, không phải dự đoán.

## 11. Dependency management và tránh xung đột classpath

Ở app tiêu thụ, các version Spring Boot/Cloud phải được điều phối bằng **BOM** tương thích. Nếu thư viện cần các API Gateway để compile, hãy dùng baseline của line tương ứng. Không nên:

- Khai báo tùy tiện một phiên bản Reactor Netty khác với BOM của Gateway app.
- Shade/đóng gói lại `org.springframework.cloud.gateway.*` hoặc `org.springframework.web.*` vào JAR tùy biến.
- Kéo `spring-boot-starter-web` vào Gateway Server WebFlux chỉ vì cần một controller/test helper.
- Thêm cả Gateway Server MVC và WebFlux rồi đoán filter sẽ chạy đúng.
- Trộn một starter Spring Security Servlet vào code `ServerHttpSecurity` reactive.
- Dùng wildcard Gradle/Maven version `+` hoặc `LATEST` trong CI production.

### Phân loại dependency tốt hơn

| Dependency | Cách suy nghĩ |
|---|---|
| Gateway filter API | Cần để compile implementation và chạy trên Gateway runtime |
| Spring WebFlux API | Dùng cho `ServerWebExchange`/`ServerHttpRequest`; phải tương thích với Gateway |
| Spring Boot autoconfigure | Chỉ module auto-config/starter cần, với bản phù hợp |
| Spring Security | Optional nếu filter có chức năng security; tránh ép mọi app dùng |
| Redis/Micrometer/Resilience4j | Optional theo tính năng; không mặc định kéo vào toàn bộ starter |
| JUnit/Reactor Test/WebTestClient | Test-only |
| Logging API | Dùng API phù hợp; không nhúng logging implementation tùy tiện |

Nếu cần một filter để gọi API bên ngoài, ưu tiên `WebClient` với timeout/backpressure và xử lý lỗi reactive, nhưng phải cân nhắc **không gọi remote service trên mọi request** khi một built-in filter có thể đáp ứng dễ hơn.

## 12. Kiểm thử đơn vị contract của GatewayFilterFactory

Một thư viện dùng chung không nên chỉ có test “Spring context khởi động được”. Cần xác minh **đầu ra của filter** qua `GatewayFilterChain` với request giả lập.

~~~java
package com.acme.edge.filters;

import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;
import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.*;

class EdgeRequestIdGatewayFilterFactoryTest {

    private final EdgeRequestIdGatewayFilterFactory factory =
        new EdgeRequestIdGatewayFilterFactory();

    @Test
    void overwritesUntrustedHeaderBeforeForwarding() {
        var config = new EdgeRequestIdGatewayFilterFactory.Config();
        config.setPrefix("orders-");

        var exchange = MockServerWebExchange.from(
            MockServerHttpRequest.get("/api/orders/42")
                .header("X-Edge-Request-Id", "spoofed"));

        AtomicReference<ServerWebExchange> forwarded =
            new AtomicReference<>();

        GatewayFilterChain chain = next -> {
            forwarded.set(next);
            return Mono.empty();
        };

        StepVerifier.create(factory.apply(config)
                .filter(exchange, chain))
            .verifyComplete();

        String header = forwarded.get().getRequest().getHeaders()
            .getFirst("X-Edge-Request-Id");

        assertNotNull(header);
        assertNotEquals("spoofed", header);
        assertTrue(header.startsWith("orders-"));
        assertEquals("/api/orders/42",
            forwarded.get().getRequest().getURI().getPath());
    }

    @Test
    void rejectsUnsafePrefixAtFactoryApplication() {
        var config = new EdgeRequestIdGatewayFilterFactory.Config();
        config.setPrefix("bad prefix\r\n");

        assertThrows(IllegalArgumentException.class,
            () -> factory.apply(config));
    }
}
~~~

**Điểm cần nắm:** `GatewayFilterChain` giả lập nhận **exchange đã mutate**, không gọi backend thật. Unit test vì thế kiểm tra được logic header, cấu hình và bất biến path. Nhưng nó **chưa chứng minh** YAML binding, component auto-configuration hay tương thích với Netty router.

### Bộ contract tests tối thiểu

| Test | Kỳ vọng |
|---|---|
| Prefix mặc định | Không truyền args vẫn sinh ID có prefix đã công bố |
| Prefix tùy biến | `EdgeRequestId=orders-` map đúng `Config.prefix` |
| Header do client giả mạo | Bị ghi đè, không nối thêm `spoofed` |
| Hai request liên tiếp | ID khác nhau theo thiết kế |
| Request path và query | Không bị custom filter làm thay đổi |
| Header có nhiều giá trị | `set` thay toàn bộ giá trị cùng tên |
| Prefix trống/không hợp lệ | Cấu hình thất bại rõ ràng |
| Chain completion/error/cancellation | Không swallow error hoặc subscribe phụ |
| Factory name | `EdgeRequestId` resolve đúng class |
| Bean override | Consumer có Bean tùy biến thì auto-config không tạo bản trùng |
| Disabled property | Khi tắt Bean, routes không tham chiếu factory đó hoặc fail theo kế hoạch |
| Java baseline | Build/bytecode chạy trên JDK hỗ trợ |

Nếu filter thật truy cập session, JWT hoặc token, bổ sung tests thiếu principal, anonymous, token hết hạn, nhiều tenant và log redaction. Đừng dùng mock claim chưa verify làm bằng chứng security correctness của production.

## 13. Integration test: từ YAML đến downstream nhận header

Một bài kiểm thử tích hợp phải khởi động **Gateway runtime thật** với starter được nhúng, đọc route YAML và forward đến backend test (có thể sử dụng WireMock/mock HTTP server phù hợp). Kiểm tra:

1. **AutoConfiguration.imports** đã đưa factory vào context.
2. `@ConditionalOnWebApplication(Type.REACTIVE)` đúng cho ứng dụng WebFlux.
3. `EdgeRequestId=orders-` được bind từ YAML.
4. Route `Path` match và filter chạy trước routing.
5. Backend nhận header mới, không nhận `spoofed`.
6. Response status/body từ backend vẫn giữ nguyên theo policy.
7. Một request không match route không bị filter xử lý ngoài phạm vi.
8. Trên một Gateway app khác dùng cùng starter, contract vẫn như nhau.

Ví dụ lệnh kiểm tra thủ công khi mock backend cung cấp endpoint echo header:

~~~bash
curl -i "http://localhost:8080/api/orders/42" \
  -H "X-Edge-Request-Id: spoofed"
~~~

Backend test nên ghi nhận **ID do Gateway sinh** (khác `spoofed`), trong khi dữ liệu nghiệp vụ không đổi. Nếu backend trả chính header ấy về client để quan sát trong lab, nhớ rằng việc đó **không xảy ra tự động**; phải do backend/response filter chủ động thực hiện.

### Thử tương tác với những filter khác

| Kết hợp | Rủi ro cần thử |
|---|---|
| `RewritePath`/`StripPrefix` | ID không đổi, path downstream đúng |
| `SetRequestHeader` cùng tên | Filter chạy sau có thể ghi đè ID, phải xác định owner |
| `AddRequestHeader` cùng tên | Header có thể thành đa giá trị, phá contract |
| `RequestRateLimiter` | 429 do limiter có thể dừng chain trước filter tạo ID tùy order |
| `Retry` | Một client request có thể tạo nhiều outbound attempts; ID tạo ở tầng nào, có đổi giữa attempts? |
| `CircuitBreaker`/fallback | Fallback có nhận ID đáng tin cậy không, có chuyển raw error data không? |
| `LocalResponseCache` | Hit có thể không gọi backend; không gắn nhầm metric “downstream received ID” |
| `lb://service-id` | Mỗi instance downstream nhận ID theo cùng contract |
| Spring Security | Filter không thay xác thực hoặc cấp quyền |
| CORS/response headers | Browser có cần đọc ID ở response không; nếu có, expose header đúng |
| TLS/mTLS | Định danh chẩn đoán không là bằng chứng caller được xác thực |

**Lưu ý Retry:** nếu filter tạo UUID bao bên ngoài Retry, những outbound attempts trong cùng client request có thể chia ID; nếu filter tạo ID trong phần chain được Retry gọi lại, mỗi attempt có thể có ID mới. Phải định nghĩa rõ **request ID** (cho một lượt client) và **attempt ID** (cho từng lần outbound) là hai mục đích khác nhau. Không suy chỉ từ thứ tự dòng YAML; kiểm tra runtime execution và trace spans.

## 14. Tương thích phiên bản phải được kiểm thử theo ma trận

Mỗi lần phát hành starter cần chạy một bộ test ở **những cặp Boot/Cloud/Gateway thực sự được tổ chức hỗ trợ**. Một CI tốt thường gồm:

~~~text
Build thư viện ở Java baseline
    |
    +--> Unit contract tests (Config, header, errors)
    |
    +--> Starter auto-configuration tests (đúng/không đúng điều kiện)
    |
    +--> Gateway Server WebFlux integration tests
    |       - route YAML shortcut / expanded
    |       - downstream HTTP echo
    |       - Spring Security / Retry / header order
    |
    +--> Dependency/BOM alignment checks
    |
    +--> Multi-instance smoke tests nếu có state liên quan
    |
    +--> Native/AOT tests nếu release cam kết hỗ trợ
    |
    +--> Publish artifacts + changelog + migration notes
~~~

Không nên sử dụng **chỉ một bộ unit tests chạy không cần Gateway runtime** để tuyên bố tương thích. Các lỗi thường chỉ lộ khi app thật khởi động và bind routes.

### Kiểm tra binary/source/config compatibility

| Kiểu tương thích | Ví dụ lỗi | Cách phát hiện |
|---|---|---|
| **Binary** | `NoSuchMethodError`, `NoClassDefFoundError` | Khởi động app với BOM mục tiêu, integration test |
| **Source** | Import/package/method signature đổi | Compile tests trên từng baseline |
| **Configuration** | `EdgeRequestId`/`prefix` không bind | Test YAML/shortcut/expanded trực tiếp |
| **Behavior** | Filter order, response commit, header mutation đổi | HTTP end-to-end assertions |
| **Security** | Tin header client, lộ token hoặc bypass auth | Negative security tests |
| **Performance** | Tăng latency/CPU/allocation | So sánh P95/P99 và profiling phù hợp |
| **Native/AOT** | Bean/Config thiếu metadata/hints | Native build + smoke test khi thực sự hỗ trợ |
| **Deployment** | Node cũ/mới ghi header khác nhau | Canary/rolling-upgrade compatibility test |

Nếu cần tool đo binary API diff như japicmp hoặc Revapi, coi đó là **một trong nhiều lớp kiểm tra**, không thay việc chạy route trong Gateway runtime thật.

## 15. Quan sát, logging và độ an toàn của thư viện dùng chung

Một filter được dùng bởi nhiều ứng dụng có phạm vi ảnh hưởng lớn: một thay đổi logging nhỏ có thể làm **mọi Gateway** phát sinh lỗi hoặc lộ thông tin.

### Nguyên tắc logging

- Log **factory name, route ID, kết quả và correlation ID** trong phạm vi phù hợp.
- Không log nguyên `Authorization`, `Cookie`, API key, JWT, session ID hoặc request body nhạy cảm.
- Không dùng full URL query chứa PII làm metric label.
- Không dùng ID ngẫu nhiên cho mỗi request làm tag Micrometer/Prometheus vì cardinality tăng vô hạn.
- Khi cần trace, ưu tiên cơ chế quan sát/tracing chuẩn của hệ sinh thái; không thay chuẩn `traceparent` bằng custom header tùy tiện.
- Nếu filter thêm metadata chẩn đoán, quy định rõ **ai được quyền đọc** và có nên forward sang bên thứ ba hay không.

### Hiệu năng và reactive constraints

| Cách viết có rủi ro | Hệ quả |
|---|---|
| `block()` trong GatewayFilter | Chặn event loop, tăng latency khi có nhiều kết nối |
| Tự `subscribe()` rồi tiếp tục chain | Race condition, lỗi bị thất lạc, không tôn trọng cancellation |
| Giữ request-specific state trong singleton Bean | Rò state giữa requests, race khi concurrent |
| Buffer mọi request body chỉ để log | Memory pressure, PII exposure, ảnh hưởng streaming |
| Thực hiện remote call không timeout | Request có thể treo, gây cascading failure |
| Gắn response header sau khi đã commit | Header không còn sửa được hoặc lỗi runtime |
| Gọi `chain.filter(exchange)` hai lần | Có thể tạo double forwarding/side effect |
| Dùng exception message làm metric tag | High cardinality và rò chi tiết nội bộ |

**Quy tắc:** Filter phải **compose publisher** (`Mono`/`Flux`) và để framework quản lý subscription, cancellation, backpressure. Nếu có tài nguyên ngoài như HTTP client, Redis, thread pool hay cache, thiết kế lifecycle, timeout và cleanup phù hợp, thay vì khởi tạo chúng theo từng request.

## 16. Triển khai, nâng cấp và rollback có kiểm soát

Một quy trình release thực tế cho thư viện dùng chung:

1. **Thiết kế và review contract**: factory name, args, defaults, tác động tới path/header, security, error semantics.
2. **Build và unit test** trên Java baseline; khóa dependencies bằng BOM phù hợp.
3. **Chạy test matrix** cho từng Boot/Cloud/Gateway đã công bố.
4. **Publish phiên bản bất biến** của JAR và changelog, không ghi đè cùng version.
5. **Canary một Gateway app** với phiên bản mới, đo startup failures, route binding, 4xx/5xx, latency, memory.
6. **Triển khai từng nhóm app**, quan sát tương thích khi các node trong cluster còn chạy các bản khác nhau.
7. **Rollback** sang artifact và config đã biết hoạt động nếu contract hoặc policy bị lỗi.
8. **Thu hồi/phát hành bản sửa** theo quy trình bảo mật khi có lỗ hổng lớn.

### Vì sao rolling upgrade khó hơn vẻ ngoài?

Giả sử Gateway node A đã dùng starter mới sinh header `X-Edge-Request-Id`, node B vẫn dùng bản cũ có tên `X-Trace-Id`. Backend phải hiểu sự không đồng nhất trong thời gian rollout, hoặc tổ chức phải giữ **cả hai tên** theo giai đoạn chuyển đổi. Đó là một thay đổi **giao thức nội bộ**, không chỉ đổi JAR.

Tương tự, nếu library filter đổi behavior của `Retry` hoặc thứ tự header trước `RequestRateLimiter`, việc nâng cấp không đồng thời giữa các Gateway nodes có thể tạo chính sách khác nhau theo request. Có thể cần:

- Phát hành một bản chuyển tiếp hỗ trợ cả tên cũ và mới.
- Rollout backend hỗ trợ hợp đồng mới **trước** khi đổi Gateway.
- Giữ version cũ đủ lâu để rollback.
- Chặn phát hành nếu config route không có migration path.

**Không chỉ tăng version và “mong mọi ứng dụng tự cập nhật”.** Thư viện dùng chung có thể có hàng chục consumer và lịch deploy riêng; tương thích chuyển tiếp phải được thiết kế.

## 17. Troubleshooting khi filter dùng chung không hoạt động

| Triệu chứng | Nguyên nhân đáng kiểm tra | Hướng xử lý |
|---|---|---|
| `Unable to find GatewayFilterFactory with name EdgeRequestId` | JAR chưa vào classpath, auto-config chưa đăng ký Bean, sai factory name hoặc disable flag | Kiểm tra imports/conditions, starter dependency và tên class |
| App không startup sau nâng BOM | API/bytecode/runtime không tương thích | Xem `NoSuchMethodError`, `ClassNotFoundException`, ma trận hỗ trợ |
| Đăng ký hai Bean cùng factory | `@Component` và `@Bean` cùng bật | Chọn một registration strategy, test override |
| YAML `prefix` không có tác dụng | Sai property name, thiếu setter/Config binding | Test expanded và shortcut theo version |
| Shortcut fail còn expanded chạy | `shortcutFieldOrder` sai hoặc format shortcut chưa hỗ trợ đúng | Kiểm tra List args order và YAML |
| Header client `spoofed` vẫn tới backend | Filter không chạy, một filter sau ghi đè, hoặc dùng `add` | Xem route runtime, order và echo backend |
| Một số requests không có ID | Request không match route, bị Security/RateLimiter chặn sớm, cache hit bỏ routing | Xác định tầng cần gắn ID |
| Header bị tạo hai lần | Có default-filter và route filter, hoặc GlobalFilter trùng | Loại đăng ký lặp và kiểm tra response/request |
| Node A hoạt động, B lỗi | Artifact/config khác nhau, auto-config disabled | So sánh version, conditions, runtime routes |
| Gateway Server MVC không nhận filter | Sử dụng abstraction WebFlux trong stack Servlet | Triển khai factory phù hợp Server MVC |
| Version bump gây khác status/headers | Behavior changed giữa release | Contract tests và release notes/migration |
| App tốn memory sau khi thêm filter | Body buffering, state per request, metric cardinality | Profiling và kiểm tra code reactive |
| 401/403 vẫn xuất hiện dù filter có ID | Header tương quan không thay authentication | Kiểm tra Spring Security riêng |
| CORS không cho JS đọc X-Edge-Request-Id | Header chỉ được gắn request, không có trong response hoặc chưa expose | Cấu hình response header và `exposedHeaders` nếu cần |
| Retry tạo ID khác nhau từng attempt | Filter nằm trong phần chain được retry lại | Thiết kế request-id vs attempt-id và xác minh order |
| Native build lỗi | Auto-config/hints không tương thích AOT | Chạy native tests, bổ sung hints theo phiên bản nếu cần |

### Sáu câu hỏi giúp khoanh vùng nhanh

1. **Đúng web stack** chưa: Gateway Server WebFlux hay MVC?
2. **Starter/version** nào đang chạy và có phù hợp Boot/Cloud BOM không?
3. **Bean factory** có được tạo duy nhất không, auto-config conditions có match không?
4. **Route runtime** có thật sự chứa `EdgeRequestId` và cấu hình args chính xác không?
5. **GatewayFilterChain order** và các filter khác có ghi đè/loại header không?
6. **Backend thực nhận gì**, và lỗi xuất hiện trước route, trong filter, ở routing hay sau response commit?

Sử dụng Actuator Gateway route inspection khi phiên bản hỗ trợ, nhưng **bảo vệ management endpoints** bằng mạng và phân quyền. Không công khai API quản trị để debug bằng cách bỏ xác thực.

## 18. Checklist nghiệm thu thư viện custom filters

- [ ] Tôi phân biệt `GatewayFilterFactory`, `GlobalFilter`, `WebFilter` và `SecurityWebFilterChain`.
- [ ] Tôi chỉ tạo custom filter khi built-in factories không đáp ứng được hợp đồng.
- [ ] Tôi dùng tên factory ổn định, class có suffix `GatewayFilterFactory` và `Config` dễ bind.
- [ ] Tôi có validation cho args và xác định rõ hành vi khi cấu hình sai.
- [ ] Filter không tin request headers do client tự gửi làm nguồn xác thực.
- [ ] Filter không `block()`, tự `subscribe()`, lưu state request trong singleton hoặc gọi chain lặp.
- [ ] Tôi kiểm tra response commit và không mutate response sau thời điểm được phép.
- [ ] Tôi có unit tests cho header, path, concurrency, errors và shortcut binding.
- [ ] Tôi có integration tests đọc YAML, startup Bean và forward HTTP thật.
- [ ] Tôi không đăng ký trùng `@Component` và starter `@Bean` cho cùng factory.
- [ ] Với Boot 3, JAR auto-config có `AutoConfiguration.imports` đúng path.
- [ ] Tôi khai báo dải Boot/Cloud/Gateway/Java **đã kiểm thử**, không đoán tương thích theo số version.
- [ ] Tôi không ép Servlet/MVC dependencies vào Gateway WebFlux.
- [ ] Tôi dùng BOM tương thích, không shade framework classes hay tự override bừa Reactor.
- [ ] Tôi có versioning, changelog, migration guide và quy trình rollback.
- [ ] Tôi kiểm tra breaking changes ở tên factory, args, shortcut, response/header semantics và filter order.
- [ ] Tôi đã thử phối hợp với Spring Security, Retry, CircuitBreaker, RateLimiter, CORS và LoadBalancer.
- [ ] Tôi đo P95/P99, errors, memory và audit mà không log raw tokens/PII.
- [ ] Tôi kiểm tra rollout khi nhiều Gateway apps/nodes còn chạy các versions khác nhau.
- [ ] Tôi chỉ công bố support matrix sau khi CI chạy thật trên các nền tảng đã cam kết.

## Tài liệu tham khảo chính thức

- [Spring Cloud Gateway Reference](https://docs.spring.io/spring-cloud-gateway/reference/) — mục **Writing Custom GatewayFilter Factories**, **Global Filters**, filter ordering, route configuration và Server WebFlux.
- [Spring Cloud Gateway Project](https://spring.io/projects/spring-cloud-gateway) — xác định phiên bản và release train.
- [Spring Boot — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html) — `@AutoConfiguration`, `AutoConfiguration.imports` và điều kiện đăng ký Bean trong Spring Boot hiện đại.
- [Spring Boot — Dependency Management](https://docs.spring.io/spring-boot/gradle-plugin/managing-dependencies.html) — quản lý BOM và tránh xung đột phiên bản.
- [Spring Framework WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html) — `ServerWebExchange`, reactive filters và response lifecycle.
- [Project Reactor Reference](https://projectreactor.io/docs/core/release/reference/) — `Mono`, cancellation, non-blocking composition và Reactor Context.
- [Micrometer Reference](https://docs.micrometer.io/micrometer/reference/) — metrics, tags và giới hạn cardinality.
- [Semantic Versioning](https://semver.org/) — cách phân biệt API breaking changes và các cấp phiên bản của thư viện.

**Ghi nhớ:** Bộ lọc dùng chung không chỉ là **một class Java tái sử dụng**. Nó là **hợp đồng YAML/Java và hành vi HTTP**, có tên factory, args, thứ tự, phạm vi chạy, giới hạn bảo mật và phiên bản runtime được hỗ trợ. Để mở rộng nhiều Gateway an toàn, hãy đóng gói bằng starter/auto-configuration phù hợp, kiểm thử **từ Bean registration đến downstream request thật**, quản lý release train qua BOM và triển khai theo ma trận tương thích có bằng chứng.

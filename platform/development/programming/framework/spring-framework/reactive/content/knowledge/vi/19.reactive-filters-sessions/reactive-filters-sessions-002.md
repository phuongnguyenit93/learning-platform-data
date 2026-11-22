# Thứ tự filter bằng Ordered và @Order

**Ngữ cảnh:** Spring Framework Reactive → **Filter và phiên**.

Trong Spring WebFlux, `WebFilter` là điểm chặn ở tầng web dùng để áp dụng logic chung trước và sau khi request đi qua phần còn lại của filter chain và handler. Những việc thường đặt ở đây gồm correlation ID, logging, CORS, xác thực, kiểm tra tenant, giới hạn request, quan sát metrics và tích hợp session.

Khi có nhiều `WebFilter`, thứ tự rất quan trọng. Filter tạo request context phải chạy trước filter cần đọc context đó; CORS phải được xử lý đúng vị trí so với security; filter ghi log response cần bao quanh phần xử lý mà nó muốn quan sát. Spring cho phép sắp thứ tự bằng hai cách:

- **`@Order(value)`:** khai báo thứ tự bằng annotation trên class hoặc bean method.
- **`Ordered#getOrder()`:** cung cấp thứ tự bằng code thông qua interface `Ordered`.

Quy tắc cốt lõi: **số order càng nhỏ thì độ ưu tiên càng cao và filter được gọi càng sớm**. Nếu filter A có order 10 và filter B có order 20, request đi vào A rồi B; khi xử lý kết thúc, phần sau của B chạy trước phần sau của A.

## 1. WebFilter nằm ở đâu trong WebFlux?

Một request đi qua server adapter và web handler chain. `WebFilter` bao quanh phần xử lý tiếp theo:

```text
HTTP request
    |
    v
WebFilter A (order = 10)
    |  before
    v
WebFilter B (order = 20)
    |  before
    v
WebFilter C (order = 30)
    |  before
    v
DispatcherHandler / Router / Controller
    |
    v
Response hoàn tất hoặc lỗi
    |
    v
WebFilter C (after)
    |
    v
WebFilter B (after)
    |
    v
WebFilter A (after)
    |
    v
HTTP response
```

Mỗi filter nhận `ServerWebExchange` và `WebFilterChain`, rồi trả `Mono<Void>`:

```java
public interface WebFilter {
    Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain);
}
```

- `ServerWebExchange` chứa request, response, attributes và quyền truy cập tới session.
- `WebFilterChain` cho phép gọi filter tiếp theo hoặc handler cuối.
- `Mono<Void>` biểu diễn thời điểm xử lý request/response hoàn tất; lỗi và cancellation cũng được truyền theo publisher.

Filter có thể **cho request đi tiếp** bằng `return chain.filter(exchange)`, hoặc **dừng chain** bằng cách tự tạo response và không gọi filter tiếp theo. Ví dụ xác thực thất bại có thể trả 401 ngay tại filter.

Spring WebFlux tự phát hiện các bean `WebFilter` trong application context và đưa chúng vào web handler chain. Khi cần thứ tự, bean có thể dùng `@Order` hoặc implement `Ordered`. <https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html>

## 2. Quy tắc số order

`Ordered` định nghĩa hai hằng số hữu ích:

| Hằng số | Giá trị | Ý nghĩa |
|---|---:|---|
| `Ordered.HIGHEST_PRECEDENCE` | `Integer.MIN_VALUE` | Độ ưu tiên cao nhất |
| `Ordered.LOWEST_PRECEDENCE` | `Integer.MAX_VALUE` | Độ ưu tiên thấp nhất |

Ví dụ:

| Filter | Order | Thứ tự request |
|---|---:|---:|
| Correlation ID | -200 | 1 |
| Authentication context | -100 | 2 |
| Audit | 0 | 3 |
| Response metrics | 100 | 4 |

Các con số chỉ minh họa. Hãy chọn giá trị dựa trên các filter thực tế của ứng dụng, Spring Security và auto-configuration. Không sao chép một giá trị order của Spring Boot từ phiên bản khác rồi giả định nó luôn giống nhau.

### 2.1. Số nhỏ chạy trước

```java
@Order(10)
@Component
class FirstFilter implements WebFilter {
    // ...
}

@Order(20)
@Component
class SecondFilter implements WebFilter {
    // ...
}
```

`FirstFilter` có precedence cao hơn `SecondFilter` vì 10 nhỏ hơn 20.

Đừng diễn giải “order 20 lớn hơn” thành “chạy sớm hơn”. Với `Ordered`, giá trị càng lớn thì priority càng thấp.

### 2.2. Giá trị bằng nhau không có thứ tự ổn định

Nếu hai filter đều có order 10, Spring không bảo đảm filter nào đứng trước. Javadoc của `Ordered` nêu rõ các phần tử cùng order có thể được sắp ở vị trí tùy ý.

Không dựa vào:

- Thứ tự khai báo class trong file.
- Thứ tự alphabet của tên bean.
- Thứ tự component được scan.
- Thứ tự tình cờ thấy trong log ở một lần chạy.

Nếu thứ tự có ý nghĩa nghiệp vụ, hãy cấp các giá trị khác nhau, ví dụ 10, 20, 30. Tham khảo [Ordered Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/Ordered.html).

## 3. Cách 1: dùng @Order

`@Order` là annotation khai báo thứ tự. Với một `WebFilter` dạng component, đặt annotation trên class:

```java
@Component
@Order(10)
public class CorrelationWebFilter implements WebFilter {

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        exchange.getAttributes().put(
                "request.source", "web");

        return chain.filter(exchange);
    }
}
```

Spring đăng ký bean này và dùng giá trị 10 khi sắp xếp filter. Annotation không tự tạo bean; class vẫn phải được đăng ký bằng component scanning hoặc cấu hình bean.

Có thể đặt `@Order` trên method `@Bean`:

```java
@Configuration
class WebFilterConfiguration {

    @Bean
    @Order(15)
    WebFilter tenantContextFilter() {
        return (exchange, chain) -> {
            exchange.getAttributes().put(
                    "tenant.checked", Boolean.TRUE);
            return chain.filter(exchange);
        };
    }
}
```

Cách này hữu ích khi không muốn gắn annotation vào class, hoặc filter được tạo từ factory method. `@Order` hỗ trợ class và bean method; giá trị mặc định nếu không khai báo là `Ordered.LOWEST_PRECEDENCE`.

### 3.1. @Order không phải thứ tự chạy của mọi loại filter

Annotation này chỉ có tác dụng ở những điểm mở rộng có hỗ trợ ordering. Trong bài này, nó được dùng cho bean `WebFilter` do WebFlux quản lý.

Không suy ra rằng gắn `@Order` vào bất kỳ object nào cũng tự thay đổi mọi chuỗi filter. Ví dụ `HandlerFilterFunction` trong WebFlux.fn được ghép vào `RouterFunction` theo cách xây dựng router; nó không phải bean `WebFilter` toàn cục được sắp xếp cùng nhóm chỉ vì có annotation.

## 4. Cách 2: implement Ordered

Khi thứ tự cần tính bằng code hoặc class tự quản lý giá trị, implement `Ordered`:

```java
@Component
public class AuditWebFilter implements WebFilter, Ordered {

    @Override
    public int getOrder() {
        return 20;
    }

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        return chain.filter(exchange);
    }
}
```

Spring gọi `getOrder()` để lấy precedence. Ví dụ trên đặt filter ở order 20.

Có thể trả về hằng số thay vì số literal:

```java
@Override
public int getOrder() {
    return Ordered.LOWEST_PRECEDENCE - 100;
}
```

Cách này thường dễ đọc hơn khi cần diễn đạt “gần cuối chain” thay vì một số tùy ý. Tuy nhiên, hãy tránh phép cộng/trừ có thể overflow ở hai giá trị cực trị.

### 4.1. Nên chọn @Order hay Ordered?

| Tiêu chí | `@Order` | `Ordered` |
|---|---|---|
| Cách khai báo | Annotation | Implement interface |
| Giá trị | Cố định tại class hoặc bean method | Trả về từ `getOrder()` |
| Dễ nhìn khi review | Rõ ngay trên bean | Cần xem method |
| Giá trị tính động | Không phù hợp | Có thể tính bằng code |
| Dùng khi | Thứ tự đơn giản, ổn định | Cần logic hoặc cấu hình programmatic |

Với filter có thứ tự cố định, `@Order` thường gọn. Với component cần quyết định thứ tự bằng code, `Ordered` phù hợp hơn.

**Tránh khai báo hai nguồn order trên cùng một filter** nếu không có lý do rõ ràng. Chọn một cách để người đọc không phải đoán giá trị nào được dùng. Khi một class implement `Ordered`, giá trị programmatic từ `getOrder()` là nguồn order cần chú ý.

## 5. Vì sao thứ tự response đảo ngược?

Filter chain hoạt động theo kiểu lồng nhau. Filter trước gọi filter tiếp theo và giữ publisher mà filter sau trả về:

```java
return chain.filter(exchange)
        .doFinally(signal -> log.info("after"));
```

Nếu A gọi B, B gọi C và C gọi handler, phần trước chạy theo thứ tự A → B → C. Khi publisher kết thúc, các callback nằm trên đường quay về được thực thi C → B → A.

Ví dụ:

```text
A before
  B before
    Handler
  B after
A after
```

Đây là cách hiểu hữu ích cho:

- Mở/đóng tracing span.
- Ghi thời gian request.
- Đặt và dọn context.
- Ghi log status sau khi response hoàn tất.
- Quan sát lỗi hoặc cancellation.

`doFinally` chạy với complete, error hoặc cancel. Nếu chỉ muốn xử lý thành công, có thể cân nhắc `doOnSuccess`; nếu muốn quan sát lỗi, dùng `doOnError`. Đừng đặt cleanup chỉ trên nhánh success nếu resource phải được giải phóng cả khi lỗi hoặc client disconnect.

## 6. Ví dụ ba filter có thứ tự rõ ràng

Giả sử ứng dụng có ba nhiệm vụ:

1. Correlation filter gắn request ID.
2. Authentication filter đọc thông tin xác thực.
3. Audit filter ghi nhận kết quả xử lý.

Một thứ tự minh họa:

```java
@Component
@Order(10)
class CorrelationWebFilter implements WebFilter {
    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        String requestId = UUID.randomUUID().toString();
        exchange.getAttributes().put("requestId", requestId);

        return chain.filter(exchange)
                .doFinally(signal ->
                        log.info("request {} finished: {}",
                                requestId, signal));
    }
}

@Component
@Order(20)
class AuthenticationWebFilter implements WebFilter {
    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        String token = exchange.getRequest().getHeaders()
                .getFirst("Authorization");

        if (token == null) {
            exchange.getResponse().setStatusCode(
                    HttpStatus.UNAUTHORIZED);
            return exchange.getResponse().setComplete();
        }

        return chain.filter(exchange);
    }
}

@Component
class AuditWebFilter implements WebFilter, Ordered {
    @Override
    public int getOrder() {
        return 30;
    }

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        return chain.filter(exchange)
                .doFinally(signal ->
                        log.info("audit finished: {}", signal));
    }
}
```

Đây là ví dụ cấu trúc; cần import, logger, token validator và chính sách audit thực tế. Đoạn authentication ở trên chỉ kiểm tra header tồn tại, **không xác minh chữ ký/token**.

Thứ tự vào request là correlation → authentication → audit → handler. Nếu thiếu Authorization, authentication filter trả 401 và không gọi chain tiếp; audit filter và handler ở phía sau không được chạy. Correlation filter vẫn nhận tín hiệu kết thúc để ghi log.

Trong production, nên dùng Spring Security cho authentication/authorization thay vì tự xây cơ chế bảo mật bằng một filter minh họa. Giá trị order của các filter tự viết cần được phối hợp với filter chain của Spring Security và filter do Boot tự cấu hình.

## 7. Filter có thể dừng chain (short-circuit)

Không phải filter nào cũng bắt buộc gọi `chain.filter`. Ví dụ từ chối request:

```java
@Component
@Order(5)
class MaintenanceFilter implements WebFilter {

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        boolean maintenance = true;

        if (maintenance) {
            exchange.getResponse().setStatusCode(
                    HttpStatus.SERVICE_UNAVAILABLE);
            return exchange.getResponse().setComplete();
        }

        return chain.filter(exchange);
    }
}
```

Nếu filter này đứng trước các filter khác, request bị dừng tại đây. Các filter nằm sau nó và handler không được gọi. Các filter ở phía ngoài đã gọi chain vẫn quan sát completion của response.

Short-circuit hữu ích cho maintenance mode, từ chối request quá hạn mức hoặc preflight CORS tùy cấu hình. Hãy bảo đảm response được hoàn tất bằng API reactive; không gọi `block()` hoặc tự `subscribe()` vào `setComplete()`.

## 8. WebFilter toàn cục và HandlerFilterFunction theo route

WebFlux có hai mức filter thường bị nhầm:

| Loại | API | Phạm vi | Cách xác định thứ tự |
|---|---|---|---|
| Global web filter | `WebFilter` | Web handler chain, áp dụng rộng cho request | `Ordered` / `@Order` |
| Functional route filter | `HandlerFilterFunction<T,R>` | Route hoặc nhóm route trong WebFlux.fn | Cách ghép filter trong RouterFunction builder |
| Security filter chain | WebFlux Security | Chuỗi bảo mật do Spring Security quản lý | Thứ tự của security chain và vị trí WebFilter bean tương ứng |

Ví dụ route-local filter:

```java
@Bean
RouterFunction<ServerResponse> routes(PeopleHandler handler) {
    return RouterFunctions.route()
            .GET("/people/{id}", handler::getOne)
            .filter((request, next) -> {
                if (request.headers().firstHeader("X-Client") == null) {
                    return ServerResponse.badRequest().build();
                }
                return next.handle(request);
            })
            .build();
}
```

Đây là snippet cần `PeopleHandler` và imports. Filter chỉ thuộc router được khai báo. `@Order` trên một bean `HandlerFilterFunction` không tự đưa nó vào global `WebFilter` chain.

Nếu cần filter cho toàn bộ request, dùng `WebFilter`. Nếu logic chỉ liên quan một nhóm route, route-local filter giúp giới hạn phạm vi và làm dependency rõ hơn.

## 9. Thứ tự với Spring Security, CORS và filter tích hợp

Trong ứng dụng thực, chain có cả filter tự viết lẫn filter framework:

- CORS cần được xử lý ở vị trí thích hợp trước bước bảo mật có thể từ chối preflight.
- Authentication/authorization cần chạy trước handler nghiệp vụ.
- Correlation ID thường cần có sớm để cả lỗi xác thực cũng được gắn mã truy vết.
- Audit/metrics có thể cần bao quanh phần xử lý để quan sát status và terminal signal.
- Filter biến đổi request/header cần chạy trước filter đọc các giá trị đã biến đổi.

Spring khuyến nghị dùng CORS support phù hợp và bảo đảm CORS filter đứng trước Spring Security filter chain khi kết hợp hai cơ chế. <https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html>

Spring Boot cũng có thể tự đăng ký các WebFilter như observability hoặc Spring Security. Giá trị order của chúng phụ thuộc phiên bản và cấu hình. Hãy xem tài liệu của đúng phiên bản Boot đang chạy; không coi bảng order trong một bản phát hành cũ là hằng số của mọi dự án. <https://docs.spring.io/spring-boot/reference/web/reactive.html>

**Không dùng số order để thay thế cấu hình security.** Nếu cần xác định CORS, authentication hoặc authorization, hãy cấu hình đúng subsystem và chỉ dùng order để đặt vị trí tương đối giữa các filter.

## 10. Filter thao tác WebSession phải giữ tính reactive

`ServerWebExchange` cung cấp `getSession()` trả `Mono<WebSession>`. Khi filter cần đọc session, hãy compose publisher thay vì chặn thread:

```java
@Component
@Order(15)
class SessionUserFilter implements WebFilter {

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        return exchange.getSession()
                .flatMap(session -> {
                    String userId =
                            session.getAttribute("userId");

                    if (userId == null) {
                        exchange.getResponse().setStatusCode(
                                HttpStatus.UNAUTHORIZED);
                        return exchange.getResponse().setComplete();
                    }

                    exchange.getAttributes().put(
                            "userId", userId);

                    return chain.filter(exchange);
                });
    }
}
```

Đây là snippet cần cấu hình WebSession, session store và chính sách xác thực thực tế. Nó minh họa việc lấy session theo kiểu reactive; việc session có được tạo mới khi chưa tồn tại phụ thuộc `WebSessionManager` và cách session được truy xuất. Không dùng ví dụ này thay thế cơ chế authentication hoàn chỉnh.

Thứ tự filter session cần được quyết định theo dependency:

- Filter cần session trước thì phải chạy trước filter đọc attribute từ session.
- Filter xác thực dựa trên session phải chạy trước handler nghiệp vụ.
- Filter ghi audit sau xử lý có thể đọc user ID đã được đặt trong exchange attribute.
- Không lưu dữ liệu nhạy cảm tùy tiện trong session hoặc exchange attributes.

Không gọi `exchange.getSession().block()`. Việc chờ session phải nằm trong chuỗi `Mono<Void>` để cancellation và lỗi vẫn thuộc request hiện tại.

## 11. Ví dụ tích hợp Java 17+ chạy được: kiểm tra thứ tự bằng WebTestClient

Ví dụ dưới đây dùng Spring Boot WebFlux và JUnit 5. Hai filter sử dụng hai cơ chế khác nhau: một filter dùng `@Order`, filter còn lại implement `Ordered`. Test gửi request tới embedded server và xác nhận thứ tự trước/sau handler.

Cấu trúc project:

```text
webflux-filter-order-demo/
├── pom.xml
└── src
    ├── main/java/demo/FilterOrderApplication.java
    └── test/java/demo/FilterOrderIntegrationTest.java
```

### 11.1. pom.xml

```xml
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

    <groupId>demo</groupId>
    <artifactId>webflux-filter-order-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

### 11.2. FilterOrderApplication.java

```java
package demo;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Mono;

@SpringBootApplication
public class FilterOrderApplication {

    public static final List<String> EVENTS =
            new CopyOnWriteArrayList<>();

    public static void main(String[] args) {
        SpringApplication.run(
                FilterOrderApplication.class, args);
    }
}

@Component
@Order(10)
class CorrelationFilter implements WebFilter {

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        return Mono.defer(() -> {
            FilterOrderApplication.EVENTS.add(
                    "correlation:before");

            return chain.filter(exchange)
                    .doFinally(signal ->
                            FilterOrderApplication.EVENTS.add(
                                    "correlation:after"));
        });
    }
}

@Component
class AuditFilter implements WebFilter, Ordered {

    @Override
    public int getOrder() {
        return 20;
    }

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        return Mono.defer(() -> {
            FilterOrderApplication.EVENTS.add(
                    "audit:before");

            return chain.filter(exchange)
                    .doFinally(signal ->
                            FilterOrderApplication.EVENTS.add(
                                    "audit:after"));
        });
    }
}

@RestController
class ProbeController {

    @GetMapping("/probe")
    Mono<String> probe() {
        FilterOrderApplication.EVENTS.add("handler");
        return Mono.just("ok");
    }
}
```

### 11.3. FilterOrderIntegrationTest.java

```java
package demo;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class FilterOrderIntegrationTest {

    @Autowired
    WebTestClient webTestClient;

    @BeforeEach
    void clearEvents() {
        FilterOrderApplication.EVENTS.clear();
    }

    @Test
    void filtersRunInAscendingOrderAndUnwindInReverse() {
        webTestClient.get()
                .uri("/probe")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("ok");

        assertThat(FilterOrderApplication.EVENTS)
                .containsExactly(
                        "correlation:before",
                        "audit:before",
                        "handler",
                        "audit:after",
                        "correlation:after");
    }
}
```

Chạy test từ thư mục project với JDK 17+ và Maven:

```bash
mvn test
```

**Chuỗi sự kiện mà assertion yêu cầu:**

```text
correlation:before
audit:before
handler
audit:after
correlation:after
```

Test không phụ thuộc thứ tự startup log của Spring Boot. Nó xác nhận thứ tự quan sát được trong một request qua embedded WebFlux server. Nếu thêm filter khác vào application context, hãy cập nhật kỳ vọng theo order thực tế.

## 12. Debug thứ tự filter

Khi filter chạy sai thứ tự, kiểm tra theo các bước:

1. Filter có thực sự được đăng ký thành bean không?
2. Bean có implement đúng `WebFilter` không?
3. Order đến từ `@Order` trên class/bean method hay `Ordered#getOrder()`?
4. Có filter khác cùng order không?
5. Có Spring Security hoặc auto-configured filter tham gia không?
6. Filter có gọi `chain.filter(exchange)` không, hay đang short-circuit?
7. Có route-local `HandlerFilterFunction` bị nhầm với global `WebFilter` không?
8. Log trước/sau có được đặt trong publisher chain đúng vị trí không?
9. Có nhiều context/child context hoặc cấu hình server tùy chỉnh làm thay đổi danh sách filter không?
10. Test có chạy đúng application context và server mode như production không?

Có thể bật log framework phù hợp hoặc ghi tên filter/order khi khởi tạo. Đừng chỉ nhìn log thời gian khởi tạo bean: **thứ tự tạo bean không phải bằng chứng chắc chắn về thứ tự thực thi request**.

## 13. Lỗi thường gặp

1. **Nghĩ order lớn hơn sẽ chạy trước.** Số nhỏ mới có precedence cao hơn.
2. **Hai filter cùng order nhưng mong thứ tự cố định.** Giá trị bằng nhau không bảo đảm thứ tự; dùng số khác nhau.
3. **Đặt @Order nhưng class không phải bean.** Annotation không tự đăng ký filter.
4. **Implement Ordered nhưng quên getOrder().** Không có giá trị programmatic đúng thì không đạt thứ tự mong muốn.
5. **Dùng @Order trên HandlerFilterFunction rồi mong global sorting.** Route-local filter được ghép trong RouterFunction, không thuộc nhóm WebFilter bean.
6. **Nhầm thứ tự request với thứ tự response.** Request đi vào theo precedence; phần sau xử lý quay ra theo thứ tự ngược.
7. **Ghi log after ngay sau khi gọi chain.filter.** Publisher bất đồng bộ chưa chắc đã kết thúc; đặt callback trong chuỗi bằng doFinally/doOnSuccess phù hợp.
8. **Không gọi chain.filter và tưởng request vẫn tới controller.** Không delegate nghĩa là filter đang dừng chain.
9. **Gọi subscribe trong filter.** Tạo subscription tách rời, làm mất liên kết lỗi/cancel với request.
10. **Gọi block trong filter.** Chặn event-loop và phá non-blocking execution.
11. **Đặt CORS sau security khi preflight cần được xử lý trước.** Cấu hình thứ tự theo hướng dẫn CORS/Security của Spring.
12. **Hard-code order của Boot từ tài liệu cũ.** Built-in filter và order có thể thay đổi theo phiên bản/cấu hình.
13. **Dùng order để thay thế authorization.** Thứ tự không tự xác minh identity hoặc quyền truy cập.
14. **Giữ mutable request state trong field của singleton filter.** Nhiều request đồng thời sẽ ghi đè dữ liệu của nhau; dùng exchange attributes hoặc Reactor Context.
15. **Quên nhánh error/cancel khi cleanup.** Dùng doFinally hoặc quản lý resource reactive để dọn trong mọi terminal path.
16. **Cho rằng filter chỉ chạy một lần khi ứng dụng khởi động.** Filter được gọi cho từng exchange/request, không phải chỉ một lần.
17. **Dùng filter toàn cục cho logic chỉ thuộc một route.** Cân nhắc HandlerFilterFunction để thu hẹp phạm vi.
18. **Đọc session bằng block.** Dùng `exchange.getSession()` và compose Mono thay vì chặn thread.

## 14. Checklist thiết kế

Trước khi thêm hoặc thay đổi filter, hãy trả lời:

- Filter là global `WebFilter` hay route-local `HandlerFilterFunction`?
- Filter có được đăng ký thành bean đúng application context không?
- Cần chạy trước những filter nào và sau những filter nào?
- Có chọn một nguồn order rõ ràng: `@Order` hoặc `Ordered`?
- Các giá trị order có khác nhau ở những chỗ thứ tự thực sự quan trọng không?
- Có filter của Spring Boot/Security/CORS tham gia không?
- Request pre-processing và response post-processing có đúng thứ tự mong đợi không?
- Filter có thể short-circuit không? Status và body có đúng contract?
- Nếu dùng session, có compose `Mono<WebSession>` mà không block không?
- Mọi lỗi và cancellation có được truyền/cleanup đúng không?
- Có test integration xác nhận chuỗi sự kiện trước và sau handler không?
- Có giữ request-specific state ở exchange/context thay vì field singleton không?

**Ghi nhớ:** `@Order` và `Ordered` đều khai báo precedence cho bean `WebFilter`. **Order số nhỏ chạy trước; order số lớn chạy sau.** Vì filter bao quanh chain, phần trước xử lý đi vào theo thứ tự tăng dần, còn phần sau xử lý quay ra theo thứ tự ngược. Giá trị bằng nhau không có thứ tự bảo đảm. Hãy phối hợp thứ tự với CORS, Spring Security, session và filter auto-configured; dùng integration test để xác nhận chuỗi thực tế.

## Tài liệu tham khảo

- Spring Framework — [Reactive Core: WebFilter registration and ordering](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html).
- Spring Framework — [Ordered Javadoc: precedence and equal-order behavior](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/Ordered.html).
- Spring Framework — [@Order Javadoc: annotation targets and default order](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/annotation/Order.html).
- Spring Boot — [Reactive Web Applications: WebFilter beans and auto-configured order](https://docs.spring.io/spring-boot/reference/web/reactive.html).
- Spring Framework — [WebFlux Functional Endpoints: HandlerFilterFunction](https://docs.spring.io/spring-framework/reference/web/webflux-functional.html).
- Spring Framework — [WebSession API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/WebSession.html).

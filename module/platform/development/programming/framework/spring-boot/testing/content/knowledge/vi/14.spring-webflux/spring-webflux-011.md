# Giới hạn của web slice khi cần kiểm chứng toàn bộ ứng dụng

Trong Spring WebFlux, `@WebFluxTest` giúp kiểm tra nhanh một HTTP endpoint mà không phải dựng toàn bộ ứng dụng. Nó thường nạp controller, những thành phần WebFlux phù hợp, bộ chuyển đổi dữ liệu và một `WebTestClient` cấu hình sẵn; service, repository và các collaborator bên ngoài web layer thường không được scan. Đây là **lợi ích**, không phải lỗi. Một request test có thể trả HTTP 200 và JSON chuẩn nhưng vẫn **không chứng minh** rằng repository truy vấn đúng, chính sách tính giá đúng, transaction hoạt động, WebClient gọi đúng dịch vụ ngoài, hay ứng dụng có thể khởi động với toàn bộ cấu hình production.

Vì vậy, khi yêu cầu chuyển từ “controller nhận và trả JSON đúng không?” sang “toàn bộ luồng ứng dụng có chạy đúng không?”, phải biết **giới hạn của web slice và chọn test ở ranh giới rộng hơn**. Giải pháp có thể là unit test của service, integration test adapter, `@SpringBootTest` với mock HTTP environment, `@SpringBootTest(webEnvironment = RANDOM_PORT)` với HTTP server thật, hoặc một bài kiểm thử end-to-end được kiểm soát.

Bài Knowledge này tập trung vào **Spring WebFlux** trong module Spring Boot testing, sử dụng **Java 17+, Spring Boot 3.5.x, Spring Framework 6.2.x, JUnit Jupiter 5, Reactor và WebTestClient**. Các ví dụ chỉ nạp hạ tầng nội bộ có kiểm soát, không kết nối payment/database production. Những API và package có thể thay đổi ở Spring Boot 4.x; hãy đối chiếu tài liệu của phiên bản bạn dùng.

## 1. Kết quả cần đạt

Sau bài học, bạn có thể:

- Giải thích rõ `@WebFluxTest` là một **slice test**, không phải full-context test.
- Phân biệt controller, `@RestControllerAdvice`, `WebFilter`, `WebExceptionHandler`, service, repository, configuration properties và auto-configuration trong WebFlux slice.
- Biết chính xác **những điều một test xanh thực sự chứng minh** và những điều nó không thể bảo vệ.
- Dùng `@MockitoBean` tại ranh giới service trong slice test mà không nhầm mock với logic thật.
- Chọn `WebTestClient` bind đến controller/context hoặc connect đến HTTP server thật.
- Viết `@SpringBootTest` full context dùng mock web environment hoặc `RANDOM_PORT` và hiểu sự khác nhau.
- Nhận diện giới hạn khi kiểm functional routes, security, filter order, JSON/validation, lỗi toàn cục, WebClient, R2DBC, transaction và reactive streams.
- Dùng `StepVerifier` để kiểm chứng `Mono`/`Flux` và phân biệt kiểm tra publisher với kiểm thử qua HTTP.
- Thiết kế ma trận test từ unit tới integration, tránh việc thay service thật bằng mock rồi kết luận nghiệp vụ đã đúng.

## 2. Bài test cần chứng minh hợp đồng nào?

Trước khi chọn annotation, hãy viết một câu:

> “Bài test phải thất bại nếu **điều gì** trong hệ thống bị sai?”

Ví dụ một endpoint `GET /api/quotes/BOOK?quantity=2&member=true` có thể phải đáp ứng các hợp đồng khác nhau:

| Hợp đồng cần bảo vệ | Lỗi phải phát hiện | Cấp test thích hợp |
|---|---|---|
| URL, query param, JSON response đúng | Mapping sai path hoặc trả sai field | `@WebFluxTest` |
| Handler dùng status/error advice đúng | 404 thành 500; body lỗi sai | `@WebFluxTest` nếu advice nằm trong slice |
| Catalog trả đúng giá BOOK | Giá trong catalog sai | Unit/integration test catalog hoặc repository |
| Hội viên giảm 10% | Chính sách tính sai | Unit test policy và service thật |
| Service nối catalog với policy đúng | Logic phối hợp sai | Unit test của service, collaborator thật/fake phù hợp |
| Spring inject đủ dependency | Missing/ambiguous bean, profile sai | `@SpringBootTest` full context |
| Request chạy qua server TCP thật | Cấu hình server, filter/protocol hoặc runtime khác biệt | `@SpringBootTest(RANDOM_PORT)` |
| SQL/R2DBC query và transaction đúng | Query/mapping/commit/rollback sai | Integration test dùng DB phù hợp |
| Outbound HTTP client đúng giao thức | Header/body/timeout/retry mapping sai | Adapter test với mock HTTP server hoặc sandbox |
| Toàn bộ luồng nhiều dịch vụ chạy đúng | Sự cố phối hợp qua network, queue, persistence | End-to-end hoặc system test được cô lập |

**Một test xanh chỉ chứng minh những đường code thực sự chạy và các assertion thực sự kiểm.** Nếu dùng mock service trả sẵn `QuoteView`, HTTP JSON đúng không bảo đảm giá tính đúng. Nếu một full-context test chỉ kiểm `contextLoads()`, nó chỉ nói context có thể khởi tạo trong **cấu hình test đó**, không chứng minh nghiệp vụ chạy đúng.

## 3. `@WebFluxTest` nạp những gì?

Trong Spring Boot 3.5, `@WebFluxTest` auto-configure hạ tầng WebFlux phục vụ kiểm thử controller và tự cấu hình `WebTestClient`. Nó giới hạn component scanning đối với những thành phần thích hợp cho web layer.

Các loại thành phần có thể được đưa vào, tùy classpath và cấu hình:

- `@Controller`, `@RestController` và `@ControllerAdvice`/`@RestControllerAdvice`.
- `@JsonComponent` và những thành phần JSON được slice/auto-configuration hỗ trợ.
- `Converter`, `GenericConverter`, Jackson `Module` khi phù hợp.
- `WebFluxConfigurer`, `WebExceptionHandler` và `WebFilter` khi phù hợp theo loại/type filter của phiên bản.
- Infrastructure cần cho routing annotation-based, HTTP message reader/writer, codec, validation và cách xử lý request.
- Các bean được **test thêm có chủ đích** qua `@Import`, `@MockitoBean`, `@TestConfiguration` hoặc cơ chế bean override tương ứng.

Thông thường **không tự scan**:

- `@Service` chứa business workflow.
- `@Repository` truy vấn dữ liệu.
- Các `@Component`/adapter không thuộc loại WebFlux slice.
- Mọi `@ConfigurationProperties` như trong full application context nếu không được bật riêng.
- Toàn bộ application auto-configuration hoặc infrastructure production.

Điều này không đồng nghĩa toàn bộ các loại bean trên bị “cấm tuyệt đối”. Một test có thể dùng `@Import` hoặc annotation override để đăng ký **có chủ đích** một service, fake hoặc configuration. Chính vì vậy, nhìn thấy một bean trong slice **không đủ để kết luận component scan đã nạp bean thật**; phải xác định bean đến từ scan, import hay mock.

Trong Spring Boot 3.5, API `WebFluxTest` còn cho phép chỉ định controller cụ thể, thêm include/exclude filters và tắt default filters khi có nhu cầu. Không nên chỉnh những thuộc tính này bừa bãi chỉ để chữa lỗi thiếu dependency: điều đó có thể phá ranh giới slice.

## 4. Sơ đồ: hai cách kiểm thử cùng một endpoint

```text
(A) WEB SLICE
JUnit test
  |
  +-- @WebFluxTest(QuoteController.class)
  |        |
  |        +-- WebFlux routing, codec, advice, WebTestClient
  |        +-- QuoteController THẬT
  |        +-- QuoteService MOCK do @MockitoBean
  |        |
  |        +-- Không tự chạy CatalogAdapter / DiscountPolicy thật
  |
  +-- WebTestClient (mock request/response, không TCP)
  |        |
  |        v
  +------ HTTP 200 / JSON do mock trả -> ASSERT

(B) FULL APPLICATION / REAL HTTP
JUnit test
  |
  +-- @SpringBootTest(webEnvironment = RANDOM_PORT)
  |        |
  |        +-- SpringApplication / full ApplicationContext
  |        +-- embedded HTTP server lắng nghe trên random port
  |        +-- QuoteController THẬT
  |        +-- QuoteService THẬT
  |        +-- DiscountPolicy THẬT
  |        +-- FixedCatalogAdapter THẬT (fixture nội bộ)
  |
  +-- WebTestClient (HTTP qua localhost TCP)
           |
           v
         Reactive HTTP server -> controller -> service -> catalog/policy
           |
           v
         HTTP 200 / JSON tính thật -> ASSERT
```

Đây là mô hình **vai trò**, không phải sơ đồ call stack chi tiết. Full context không đồng nghĩa mọi dependency được triển khai thật trên production: một `FixedCatalogAdapter` trong ví dụ vẫn chỉ là fixture/in-memory adapter. Chỉ những tầng thực sự được kết nối mới được kiểm chứng.

## 5. Giới hạn quan trọng nhất: mock service che logic nghiệp vụ

Xét ví dụ sau:

```java
@WebFluxTest(QuoteController.class)
class QuoteControllerSliceTest {

    @MockitoBean
    QuoteService service;

    // WebTestClient test gọi HTTP endpoint,
    // còn service.quote(...) trả Mono được test cấu hình trước.
}
```

Đây là **snippet** chỉ để hiểu ranh giới; file test đầy đủ sẽ xuất hiện ở mục 11.

Nếu test viết:

```java
when(service.quote("BOOK", 2, true))
        .thenReturn(Mono.just(
                new QuoteView("BOOK", 2, 240_000L,
                        24_000L, 216_000L)));
```

thì những số `240000`, `24000` và `216000` đã được test **tự đặt ra**, không phải kết quả chạy policy thật. Test có thể kiểm controller chuyển đúng argument và serialize response, nhưng **không phát hiện** khi production giảm 5% thay vì 10%.

Để bảo vệ nghiệp vụ:

- Unit test `DiscountPolicy` thật với những trường hợp biên.
- Unit test `QuoteService` thật với `CatalogGateway` fake hoặc adapter thật có kiểm soát.
- Full-context/integration test khi cần xác minh Spring bean wiring và các đường phối hợp thực.

**Không gọi đây là thất bại của `@WebFluxTest`.** Nó hoạt động đúng mục tiêu của slice. Sai lầm nằm ở việc **diễn giải quá rộng ý nghĩa của test xanh**.

## 6. `WebTestClient` có nhiều chế độ hoạt động

`WebTestClient` là công cụ quan sát request/response phù hợp với WebFlux và có thể sử dụng theo nhiều cách:

| Cách tạo | Có Spring context thật? | Mở HTTP server TCP? | Bảo vệ điều gì |
|---|---|---|---|
| `WebTestClient.bindToController(controller)` | Không bắt buộc | Không | Handler + WebFlux infrastructure tối thiểu cho controller đã chọn |
| `WebTestClient.bindToRouterFunction(route)` | Không bắt buộc | Không | Functional route đã đưa trực tiếp vào test |
| `WebTestClient.bindToApplicationContext(context)` | Có context đang cung cấp | Không | WebHandler chain được xây từ context đó |
| `@WebFluxTest` với injected `WebTestClient` | MVC? **Không**; WebFlux slice context | Không | WebFlux slice, controller, codec/filter/advice được nạp |
| `@SpringBootTest` + `@AutoConfigureWebTestClient` với mock environment | Full Boot context | Không | Bean wiring/config/application chain nhưng không test TCP server |
| `@SpringBootTest(RANDOM_PORT)` + injected `WebTestClient` | Full Boot context | Có | Request/response qua embedded server thật |
| `WebTestClient.bindToServer().baseUrl(...)` | Phụ thuộc server ngoài | Có | HTTP endpoint đang chạy ở URL đó |

Hai câu phải phân biệt:

1. **Client thật** không nhất thiết đồng nghĩa **server thật**. `WebTestClient` có thể dùng mock request/response dù API client tương tự như khi kết nối TCP.
2. **Full context** không nhất thiết đồng nghĩa **HTTP server thật**. `@SpringBootTest` với mặc định `MOCK` có thể nạp nhiều bean nhưng chưa mở cổng mạng.

Không thể khẳng định đã kiểm socket, port binding, network timeout, reverse proxy, TLS, load balancer hay HTTP runtime thực nếu bạn chỉ dùng mock server binding.

### 6.1. WebFlux không phải Spring MVC

`@WebFluxTest` là slice cho WebFlux reactive stack. `@WebMvcTest` và `MockMvc` là lựa chọn thường dùng cho Spring MVC servlet stack. `WebTestClient` có thể dùng với cả hai theo các adapter/configuration thích hợp, nhưng **không thể suy ra rằng test đang chạy WebFlux chỉ vì loại client là WebTestClient**.

Nếu cả `spring-boot-starter-web` và `spring-boot-starter-webflux` đều có trên classpath, Boot thường chọn **servlet MVC application type** theo mặc định. Khi viết test giới hạn vào WebFlux, cần xem starter và `spring.main.web-application-type` có thực sự tạo reactive application không. Ví dụ runnable ở dưới **chỉ thêm starter-webflux**, tránh tình huống mơ hồ này.

## 7. Ba câu hỏi trước khi chọn slice hay full context

1. **Điều cần kiểm là HTTP contract hay business workflow?** Nếu chỉ mapping, parameter binding, status, JSON, validation và controller advice: WebFlux slice đủ. Nếu cần tính giá/repository/business coordination: phải để logic thật chạy ở một test khác hoặc full context.
2. **Điều cần kiểm là bean wiring hay server/network behavior?** Nếu DI/config/profile là mục tiêu, full context với mock web environment có thể đủ. Nếu cần server thực, dùng random port.
3. **Điều cần kiểm là đơn lẻ trong một JVM hay nhiều hệ thống phối hợp?** Một `@SpringBootTest(RANDOM_PORT)` với fake DB/HTTP không tự chứng minh event broker, payment provider hay database production vận hành đúng. Khi cần các boundary thật, thêm integration/contract/E2E test chuyên biệt.

Chọn mức nhỏ nhất **đủ để bắt loại bug bạn quan tâm**. Không có annotation nào có thể thay thế việc viết assertion đúng trên các hợp đồng đó.

## 8. Những thành phần thường bị bỏ sót trong `@WebFluxTest`

### 8.1. `@Service` và `@Repository`

Slice thường không scan `@Service` hoặc `@Repository`. Nếu controller constructor cần `QuoteService`, test phải cung cấp collaborator qua `@MockitoBean` hoặc import/config có chủ đích. Đây không phải bằng chứng repository production hoạt động.

### 8.2. Configuration properties và profile

`@ConfigurationProperties` không tự được scan như trong full Boot context. Nếu controller trực tiếp cần một properties bean, có thể sử dụng `@EnableConfigurationProperties(TheProperties.class)` hoặc import configuration tương ứng. Nhưng một test property được set đúng không chứng minh toàn bộ cấu hình production hoạt động. Profile, secret, TLS, connection pool hoặc resource location phải được kiểm ở cấp phù hợp.

### 8.3. Cấu hình hạ tầng ngoài web

R2DBC datasource, Redis client, Kafka producer, scheduled job hoặc outbound WebClient adapter thường ở ngoài phạm vi slice. Nếu chúng được import cưỡng bức vào slice để “giống production”, test dễ mất tốc độ và cô lập, trong khi vẫn có thể thiếu những cơ chế khác của ứng dụng.

### 8.4. Functional routing

Đây là giới hạn **rất cụ thể**: trong Spring Boot 3.5, `@WebFluxTest` không tự phát hiện đầy đủ các route được khai báo bằng **functional WebFlux** (`RouterFunction`) như cách nó scan annotated controllers. Nếu muốn test router function, dùng `WebTestClient.bindToRouterFunction(...)`, import `RouterFunction`/handler có chủ đích hoặc dùng `@SpringBootTest`.

### 8.5. Security và WebFilter

`WebFilter`, `WebExceptionHandler` và các thành phần security WebFlux có thể là một phần của web slice tùy annotation, component scan, auto-configuration và classpath. Vì vậy không được nói “slice luôn bỏ toàn bộ filter/security”.

Điều chưa được đảm bảo là **cấu hình security production đầy đủ** có tồn tại trong test context theo đúng đường triển khai. Cần kiểm bean/filter chain được nạp và kiểm hành vi authorization/authentication với test security setup phù hợp. Đừng tắt CSRF/auth chỉ để test xanh mà vẫn tuyên bố endpoint production an toàn.

### 8.6. Reactive data and transaction boundaries

Slice có thể trả đúng `Mono<Dto>` được mock mà không chạy R2DBC repository hoặc transaction. Với Spring reactive, giao dịch thường dựa trên **Reactor Context**, không phải đơn thuần ThreadLocal. Một test HTTP server thật thường chạy xử lý ở luồng/context riêng so với JUnit test method; transaction của test method không tự rollback những thay đổi do HTTP server thực hiện.

## 9. Ví dụ đầy đủ: cùng endpoint, hai mức độ xác minh

Chúng ta xây một ứng dụng tạo **báo giá** cho sản phẩm:

- BOOK có đơn giá 120.000 VND, PEN có đơn giá 20.000 VND.
- Số lượng phải lớn hơn 0.
- Hội viên được giảm 10% trên tạm tính, làm tròn xuống theo phép chia nguyên trong ví dụ.
- SKU không tồn tại trả HTTP 404 với JSON error.
- Input sai trả HTTP 400 với JSON error.
- Một test web slice dùng mocked `QuoteService` để xác minh mapping/JSON.
- Một full HTTP test gọi **QuoteService, FixedCatalogAdapter và DiscountPolicy thật** qua server thực.

Trong sản phẩm thực tế, tiền tệ nên có money type, currency, rounding policy, overflow protection và idempotency. Ví dụ dùng **long số nguyên VND** để tập trung vào kiến trúc test. Catalog adapter chỉ đọc dữ liệu cố định trong memory, **không có network, DB hoặc tài khoản production**.

### 9.1. Cây thư mục

```text
src/main/java/com/example/webfluxscope/
    QuoteDemoApplication.java
    QuoteView.java
    ApiError.java
    CatalogGateway.java
    FixedCatalogAdapter.java
    DiscountPolicy.java
    QuoteNotFoundException.java
    QuoteService.java
    QuoteController.java
    QuoteErrors.java

src/test/java/com/example/webfluxscope/
    QuoteServiceUnitTest.java
    QuoteWebFluxSliceTest.java
    QuoteFullHttpTest.java
```

Các file được đặt trong cùng package `com.example.webfluxscope`. Project cần Java 17+, Spring Boot 3.5.x, Reactor và dependency test đúng như ở mục 21.

### 9.2. Ứng dụng WebFlux

**`src/main/java/com/example/webfluxscope/QuoteDemoApplication.java`**

```java
package com.example.webfluxscope;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class QuoteDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(QuoteDemoApplication.class, args);
    }
}
```

Với chỉ `spring-boot-starter-webflux`, Boot chọn reactive application type theo convention. Ứng dụng này không cần thêm `@EnableWebFlux`; tự ý thêm `@EnableWebFlux` có thể thay cơ chế auto-configuration của Boot và làm ví dụ khác đi.

### 9.3. Record cho dữ liệu trả về và error

**`src/main/java/com/example/webfluxscope/QuoteView.java`**

```java
package com.example.webfluxscope;

public record QuoteView(
        String sku,
        int quantity,
        long subtotalVnd,
        long discountVnd,
        long totalVnd) {
}
```

**`src/main/java/com/example/webfluxscope/ApiError.java`**

```java
package com.example.webfluxscope;

public record ApiError(String code, String message) {
}
```

Java records phù hợp cho immutable DTO đơn giản: accessor như `totalVnd()`, `equals` và `hashCode` được Java tạo. Jackson trong Spring Boot 3.5 có thể serialize chúng thành JSON object.

### 9.4. Port và repository giả lập có logic thật

**`src/main/java/com/example/webfluxscope/CatalogGateway.java`**

```java
package com.example.webfluxscope;

import reactor.core.publisher.Mono;

public interface CatalogGateway {
    Mono<Long> findUnitPrice(String sku);
}
```

**`src/main/java/com/example/webfluxscope/FixedCatalogAdapter.java`**

```java
package com.example.webfluxscope;

import org.springframework.stereotype.Repository;
import reactor.core.publisher.Mono;

@Repository
public class FixedCatalogAdapter implements CatalogGateway {

    @Override
    public Mono<Long> findUnitPrice(String sku) {
        return switch (sku) {
            case "BOOK" -> Mono.just(120_000L);
            case "PEN" -> Mono.just(20_000L);
            default -> Mono.empty();
        };
    }
}
```

`FixedCatalogAdapter` là một **adapter thực sự được Spring tạo khi full context chạy**, nhưng nó chỉ đọc hai giá trị in-memory. Test này có thể xác minh đường gọi tới adapter, **không xác minh SQL, R2DBC mapping, connection pool hoặc database transaction**. Tên annotation `@Repository` cho thấy vai trò kiến trúc, không khiến một database thật xuất hiện.

### 9.5. Policy nghiệp vụ thật

**`src/main/java/com/example/webfluxscope/DiscountPolicy.java`**

```java
package com.example.webfluxscope;

import org.springframework.stereotype.Component;

@Component
public class DiscountPolicy {

    public long discountVnd(long subtotalVnd, boolean member) {
        if (subtotalVnd < 0L) {
            throw new IllegalArgumentException(
                    "subtotal must not be negative");
        }
        return member ? subtotalVnd / 10L : 0L;
    }
}
```

Nếu ai sửa giảm 10% thành 5% trên đoạn code này, **full HTTP test** và **service unit test** bên dưới sẽ đỏ, trong khi test slice có thể vẫn xanh vì output từ mock không thay đổi. Đây chính là minh họa trọng tâm của bài.

### 9.6. Exception cho SKU không tìm thấy

**`src/main/java/com/example/webfluxscope/QuoteNotFoundException.java`**

```java
package com.example.webfluxscope;

public class QuoteNotFoundException extends RuntimeException {
    public QuoteNotFoundException(String sku) {
        super("Unknown sku: " + sku);
    }
}
```

### 9.7. Reactive service với logic thật và subscription semantics

**`src/main/java/com/example/webfluxscope/QuoteService.java`**

```java
package com.example.webfluxscope;

import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class QuoteService {
    private final CatalogGateway catalog;
    private final DiscountPolicy policy;

    public QuoteService(CatalogGateway catalog, DiscountPolicy policy) {
        this.catalog = catalog;
        this.policy = policy;
    }

    public Mono<QuoteView> quote(
            String sku, int quantity, boolean member) {

        return Mono.defer(() -> {
            if (sku == null || sku.isBlank()) {
                return Mono.error(new IllegalArgumentException(
                        "sku must not be blank"));
            }
            if (quantity <= 0) {
                return Mono.error(new IllegalArgumentException(
                        "quantity must be positive"));
            }

            return catalog.findUnitPrice(sku)
                    .switchIfEmpty(Mono.error(
                            new QuoteNotFoundException(sku)))
                    .map(unitPrice -> {
                        long subtotal = Math.multiplyExact(
                                unitPrice, quantity);
                        long discount = policy.discountVnd(
                                subtotal, member);
                        long total = Math.subtractExact(
                                subtotal, discount);
                        return new QuoteView(sku, quantity,
                                subtotal, discount, total);
                    });
        });
    }
}
```

Cấu trúc reactive:

1. `Mono.defer` hoãn việc kiểm input và gọi catalog cho đến khi publisher được **subscribe**.
2. `findUnitPrice` trả `Mono<Long>`, không chặn thread.
3. `switchIfEmpty` chuyển SKU không tồn tại thành `onError`.
4. `map` chạy phép tính giá/chiết khấu thật khi có giá trị.
5. Overflow số học bị `Math.multiplyExact` hoặc `Math.subtractExact` phát hiện; cần error mapping riêng nếu product có thể đạt giá trị cực lớn.

**Không gọi `block()` hoặc `subscribe()` bên trong controller/service** để “ép Mono chạy”. WebFlux quản lý subscription khi xử lý HTTP; gọi block trên event-loop có thể dẫn tới lỗi vận hành hoặc giảm throughput. Muốn kiểm publisher riêng ở unit test, dùng `StepVerifier`.

### 9.8. Annotated reactive controller

**`src/main/java/com/example/webfluxscope/QuoteController.java`**

```java
package com.example.webfluxscope;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/quotes")
public class QuoteController {
    private final QuoteService service;

    public QuoteController(QuoteService service) {
        this.service = service;
    }

    @GetMapping("/{sku}")
    public Mono<QuoteView> getQuote(
            @PathVariable String sku,
            @RequestParam(defaultValue = "1") int quantity,
            @RequestParam(defaultValue = "false") boolean member) {
        return service.quote(sku, quantity, member);
    }
}
```

Controller có một nhiệm vụ: bind request rồi gọi service, trả `Mono<QuoteView>` cho WebFlux. Nó **không tính tiền trực tiếp**. Đây là ranh giới thuận lợi để mock service khi kiểm MVC-style HTTP contract của WebFlux, và chạy service thật khi cần test use case.

### 9.9. Error handler dùng chung

**`src/main/java/com/example/webfluxscope/QuoteErrors.java`**

```java
package com.example.webfluxscope;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import reactor.core.publisher.Mono;

@RestControllerAdvice
public class QuoteErrors {

    @ExceptionHandler(QuoteNotFoundException.class)
    @ResponseStatus(HttpStatus.NOT_FOUND)
    public Mono<ApiError> notFound(QuoteNotFoundException failure) {
        return Mono.just(new ApiError(
                "SKU_NOT_FOUND", failure.getMessage()));
    }

    @ExceptionHandler(IllegalArgumentException.class)
    @ResponseStatus(HttpStatus.BAD_REQUEST)
    public Mono<ApiError> badRequest(IllegalArgumentException failure) {
        return Mono.just(new ApiError(
                "INVALID_REQUEST", failure.getMessage()));
    }
}
```

`@RestControllerAdvice` thuộc loại web-layer component nên `@WebFluxTest` có thể nạp handler này. Test slice có thể bảo vệ lỗi được chuyển thành HTTP 404/400 với JSON. Nhưng **không phải mọi exception trong server production đều đi qua cùng handler**; security exception, WebFilter error, malformed body và default global error handler có thể cần test riêng.

## 10. Unit test của service: bảo vệ logic không cần Spring context

**`src/test/java/com/example/webfluxscope/QuoteServiceUnitTest.java`**

```java
package com.example.webfluxscope;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class QuoteServiceUnitTest {

    private final CatalogGateway catalog = sku -> switch (sku) {
        case "BOOK" -> Mono.just(120_000L);
        case "PEN" -> Mono.just(20_000L);
        default -> Mono.empty();
    };

    private final QuoteService service =
            new QuoteService(catalog, new DiscountPolicy());

    @Test
    void computesRealMemberDiscount() {
        StepVerifier.create(
                service.quote("BOOK", 2, true))
                .expectNext(new QuoteView(
                        "BOOK", 2, 240_000L,
                        24_000L, 216_000L))
                .verifyComplete();
    }

    @Test
    void computesFullPriceForNonMember() {
        StepVerifier.create(
                service.quote("PEN", 3, false))
                .expectNext(new QuoteView(
                        "PEN", 3, 60_000L, 0L, 60_000L))
                .verifyComplete();
    }

    @Test
    void rejectsUnknownSkuReactively() {
        StepVerifier.create(
                service.quote("UNKNOWN", 1, false))
                .expectErrorMatches(failure ->
                        failure instanceof QuoteNotFoundException
                        && failure.getMessage().equals(
                                "Unknown sku: UNKNOWN"))
                .verify();
    }

    @Test
    void rejectsInvalidQuantity() {
        StepVerifier.create(
                service.quote("BOOK", 0, true))
                .expectError(IllegalArgumentException.class)
                .verify();
    }
}
```

Đây là **unit test thật của domain + service**: không khởi động Spring, không dùng Mockito, không mở HTTP. Vì `DiscountPolicy` là object thật, test sẽ phát hiện lỗi tính giảm giá. `CatalogGateway` là fake cố định, không kiểm tra truy vấn database.

`StepVerifier` subscribe vào publisher và kiểm **onNext, onComplete hoặc onError**. Khi Publisher trả `Mono.empty()` và test mong một `QuoteView`, assertion sẽ đỏ thay vì lặng lẽ bỏ qua. Unit test reactive còn có thể kiểm retry, timeout, cancellation hoặc `Flux`, nhưng các operator ấy cần được đưa vào logic SUT cụ thể mới có giá trị.

## 11. Web slice test: controller thật, service mock

**`src/test/java/com/example/webfluxscope/QuoteWebFluxSliceTest.java`**

```java
package com.example.webfluxscope;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.core.publisher.Mono;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.mockingDetails;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@WebFluxTest(QuoteController.class)
class QuoteWebFluxSliceTest {

    @Autowired
    WebTestClient client;

    @Autowired
    ApplicationContext context;

    @MockitoBean
    QuoteService service;

    @Test
    void mapsRequestAndSerializesStubbedQuote() {
        when(service.quote("BOOK", 2, true))
                .thenReturn(Mono.just(new QuoteView(
                        "BOOK", 2, 240_000L,
                        24_000L, 216_000L)));

        client.get()
                .uri(uri -> uri.path("/api/quotes/BOOK")
                        .queryParam("quantity", 2)
                        .queryParam("member", true)
                        .build())
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.sku").isEqualTo("BOOK")
                .jsonPath("$.quantity").isEqualTo(2)
                .jsonPath("$.subtotalVnd").isEqualTo(240_000)
                .jsonPath("$.discountVnd").isEqualTo(24_000)
                .jsonPath("$.totalVnd").isEqualTo(216_000);

        verify(service).quote("BOOK", 2, true);

        assertEquals(0, context.getBeanNamesForType(
                FixedCatalogAdapter.class).length);
        assertTrue(mockingDetails(service).isMock());
    }

    @Test
    void mapsServiceErrorThroughControllerAdvice() {
        when(service.quote("UNKNOWN", 1, false))
                .thenReturn(Mono.error(
                        new QuoteNotFoundException("UNKNOWN")));

        client.get()
                .uri("/api/quotes/UNKNOWN")
                .exchange()
                .expectStatus().isNotFound()
                .expectBody()
                .jsonPath("$.code").isEqualTo("SKU_NOT_FOUND")
                .jsonPath("$.message")
                .isEqualTo("Unknown sku: UNKNOWN");

        verify(service).quote("UNKNOWN", 1, false);
    }
}
```

### 11.1. Test này chứng minh được gì?

- `GET /api/quotes/BOOK?quantity=2&member=true` mapping vào controller đúng và truyền ba argument đúng.
- WebFlux serialize Java record thành JSON đúng field/giá trị **do mock cung cấp**.
- `@RestControllerAdvice` đã nạp trong slice và chuyển `QuoteNotFoundException` do publisher trả về thành 404.
- `FixedCatalogAdapter` không được scan; đây là kỳ vọng của slice, không phải thiếu bean production.
- `QuoteService` trong context là **Mockito mock**, không phải implementation thật.

### 11.2. Test này chưa chứng minh được gì?

- `QuoteService.quote` thực hiện toán đúng hay không.
- `DiscountPolicy` có giảm đúng 10% hay không.
- `FixedCatalogAdapter` đọc SKU đúng hay không.
- Full Boot context có wiring đủ hay không.
- Embedded HTTP server có mở cổng được hay không.
- Database, transaction, security production, outbound HTTP client hay một luồng tích hợp thật có hoạt động hay không.

Vì vậy tên test `mapsRequestAndSerializesStubbedQuote` minh bạch hơn `checkoutWorksEndToEnd`. **Tên test là một lời cam kết về phạm vi kiểm chứng**.

## 12. Full HTTP test: ứng dụng thực sự tạo context và mở port

**`src/test/java/com/example/webfluxscope/QuoteFullHttpTest.java`**

```java
package com.example.webfluxscope;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.mockito.Mockito.mockingDetails;

@SpringBootTest(
        classes = QuoteDemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class QuoteFullHttpTest {

    @Autowired
    WebTestClient client;

    @Autowired
    QuoteService realService;

    @Autowired
    FixedCatalogAdapter realCatalog;

    @Test
    void realHttpServerRunsServiceCatalogAndPolicy() {
        client.get()
                .uri(uri -> uri.path("/api/quotes/BOOK")
                        .queryParam("quantity", 2)
                        .queryParam("member", true)
                        .build())
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.sku").isEqualTo("BOOK")
                .jsonPath("$.quantity").isEqualTo(2)
                .jsonPath("$.subtotalVnd").isEqualTo(240_000)
                .jsonPath("$.discountVnd").isEqualTo(24_000)
                .jsonPath("$.totalVnd").isEqualTo(216_000);

        assertFalse(mockingDetails(realService).isMock());
        assertFalse(mockingDetails(realCatalog).isMock());
    }

    @Test
    void unknownSkuMapsTo404FromRealService() {
        client.get()
                .uri("/api/quotes/UNKNOWN")
                .exchange()
                .expectStatus().isNotFound()
                .expectBody()
                .jsonPath("$.code").isEqualTo("SKU_NOT_FOUND");
    }

    @Test
    void invalidQuantityMapsTo400() {
        client.get()
                .uri(uri -> uri.path("/api/quotes/BOOK")
                        .queryParam("quantity", 0)
                        .build())
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code").isEqualTo("INVALID_REQUEST");
    }
}
```

Với `RANDOM_PORT`, Spring Boot khởi động embedded reactive HTTP server trên một port khả dụng và cấu hình `WebTestClient` để gọi đến server đó. Vì project demo chỉ có `spring-boot-starter-webflux`, request đi qua WebFlux runtime của ứng dụng.

**Sự khác biệt có thể kiểm chứng:**

- Controller không phải mock.
- Service `@Service` và catalog `@Repository` được Spring tạo thật; policy `@Component` chạy thật.
- JSON tổng tiền được tính từ adapter + service + policy, **không phải dữ liệu do test stub**.
- HTTP server thật được khởi động; status và serialization được quan sát qua kết nối thực đến localhost.

Vì adapter catalog chỉ là dữ liệu cố định, đây **chưa phải integration test với database production**. Nói chính xác: full HTTP integration test của **ứng dụng demo nội bộ**, không phải end-to-end của toàn hệ sinh thái.

Nếu runtime test thực sự cần database/queue, phải cung cấp test infrastructure an toàn và assert side effects tương ứng. Đừng biến full-context test thành test phá dữ liệu thật.

## 13. Full context nhưng không cần mở HTTP server

Có trường hợp cần kiểm bean wiring, codec, profile hoặc WebFlux handler chain đầy đủ nhưng **chưa cần network TCP thật**. Dùng:

```java
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureWebTestClient
class FullContextMockWebTest {
    @Autowired WebTestClient client;
    // @Test methods...
}
```

Đây là **snippet**: cần import annotation/bean class và method `@Test` thực tế. `@AutoConfigureWebTestClient` nằm trong package `org.springframework.boot.test.autoconfigure.web.reactive` của Spring Boot 3.5.

So sánh:

| Tiêu chí | `@WebFluxTest` | Full context + `@AutoConfigureWebTestClient` | Full context + `RANDOM_PORT` |
|---|---|---|---|
| Bean ứng dụng | Slice giới hạn | Nhiều bean thật theo config | Nhiều bean thật theo config |
| `WebTestClient` | Tự cấu hình | Cấu hình qua annotation | Boot có thể autowire client kết nối server |
| Embedded server | Không | Không | Có |
| Kiểm logic service thật | Không, nếu service mock | Có nếu không bị mock | Có nếu không bị mock |
| Kiểm Spring wiring | Chỉ wiring của slice | Wiring của full context test | Wiring của full context test |
| Kiểm TCP, port và runtime server | Không | Không | Có |
| Chi phí | Thường thấp nhất | Cao hơn slice | Thường cao hơn vì server |

**Không đồng nhất “full-context” với “RANDOM_PORT”.** Cấp độ context và việc có mạng thật là **hai trục độc lập**. Một integration test dùng mock web environment có thể rất có giá trị khi bạn muốn kiểm end-to-end xử lý Java/Spring trong process nhưng không cần kiểm transport.

## 14. Functional routes: giới hạn rất thường bị quên

Spring WebFlux hỗ trợ hai cách định nghĩa endpoint:

1. **Annotated controllers**: `@RestController`, `@GetMapping`, `@RequestMapping`.
2. **Functional endpoints**: `RouterFunction<ServerResponse>` kết hợp handler.

`@WebFluxTest` tập trung vào annotated web components. Tài liệu Spring Boot 3.5 nêu rõ nó **không tự phát hiện các route được đăng ký bằng functional web framework**. Nếu ứng dụng dùng functional router, việc `@WebFluxTest` chỉ thấy controller khác và test xanh không chứng minh route functional đã đăng ký.

Ví dụ dạng khái niệm:

```java
// Snippet: cần một QuoteHandler thật và imports RouterFunctions.
@Bean
RouterFunction<ServerResponse> quoteRoutes(QuoteHandler handler) {
    return RouterFunctions.route(
            RequestPredicates.GET("/functional/quotes/{sku}"),
            handler::get);
}
```

Đây không phải file runnable độc lập vì `QuoteHandler` chưa được định nghĩa. Các hướng kiểm:

- Với route logic riêng lẻ, dùng `WebTestClient.bindToRouterFunction(routes)` để test handler chain theo scope mong muốn.
- Nếu muốn chạy route trong Spring context, import `RouterFunction`/configuration và handler có chủ đích.
- Nếu cần chứng minh ứng dụng production đăng ký route đầy đủ, dùng `@SpringBootTest` và gọi endpoint qua mock WebFlux environment hoặc real server.

**Bẫy:** một test `bindToRouterFunction` với router object tạo bằng `new` không chứng minh Spring full context có bean router đó. Để xác minh **wiring**, test phải truy cập context thật.

## 15. Reactive publisher: HTTP test chưa thay `StepVerifier`

Trong WebFlux, một endpoint có thể trả `Mono<T>` hoặc `Flux<T>`. `WebTestClient` kiểm HTTP status/body và có thể tiêu thụ một stream; `StepVerifier` kiểm **chuỗi tín hiệu reactive** (subscription, onNext, onComplete, onError, cancellation, virtual time).

| Câu hỏi | Công cụ phù hợp |
|---|---|
| JSON của HTTP 200 đúng không? | `WebTestClient` |
| Mono phát đúng một QuoteView rồi complete không? | `StepVerifier` |
| Mono lỗi đúng loại khi SKU không tồn tại không? | `StepVerifier` |
| SSE stream gửi đúng event trong transport HTTP không? | `WebTestClient` với response stream test phù hợp |
| Retry/backoff theo virtual time có đúng không? | `StepVerifier.withVirtualTime` với logic reactive thích hợp |
| Netty server thực xử lý stream/timeout ra sao? | HTTP integration test với running server và client có timeout |

Ví dụ trong unit test:

```java
StepVerifier.create(service.quote("BOOK", 2, true))
        .expectNext(new QuoteView(
                "BOOK", 2, 240_000L, 24_000L, 216_000L))
        .verifyComplete();
```

Nếu một method trả `Mono<Void>` chỉ thể hiện **completion**, HTTP 204 có thể không bảo vệ được side effect ngầm; cần assert repository/event sink phù hợp ở cấp khác.

Nếu method trả `Flux` **không kết thúc**, không gọi `expectComplete()` vô hạn. Với stream SSE, dùng `take(n)`/`thenCancel()` và timeout khi phù hợp, đồng thời cần ít nhất một HTTP integration test nếu protocol/flush/network là một phần contract.

### 15.1. Backpressure và operator không được mock service bảo vệ

Khi `@WebFluxTest` stub `when(service.events()).thenReturn(Flux.just(...))`, test có thể chứng minh controller chuyển Flux thành SSE theo thiết lập, nhưng không thử backpressure, concurrency hoặc buffering của service thật. Kiểm logic stream bằng StepVerifier và kiểm transport bằng HTTP test, không rút kết luận “reactive pipeline đúng” từ một Flux giả có hai event.

### 15.2. Tránh blocking trong event loop

Một test slice có publisher `Mono.just(...)` rất nhanh không phát hiện code production dùng JDBC blocking hoặc `Thread.sleep` trong Netty event-loop nếu service bị mock. Unit test có thể dùng BlockHound (khi thích hợp và cấu hình tương thích) hoặc các test tích hợp concurrency/performance để phát hiện blocking; quan trọng hơn là code review và ranh giới adapter rõ. Không thêm `block()` vào service chỉ để đáp ứng test.

## 16. Security WebFlux và filter chain

`@WebFluxTest` có thể nạp `WebFilter` và các phần security theo classpath/cấu hình. Nhưng nếu ứng dụng production có:

- `SecurityWebFilterChain` tùy chỉnh;
- Reactive authentication manager;
- JWT/OAuth2 resource server;
- Role/permission checks, CSRF;
- WebFilter theo profile hoặc tenant;
- Cấu hình CORS và exception translation;

thì một test slice chỉ xác nhận **cấu hình security nào thực sự có trong context test**. Nếu test dùng `@WithMockUser`, nó mô phỏng principal, không thực hiện toàn bộ quá trình parse/verify token qua gateway.

Một chiến lược hợp lý:

1. Unit test policy quyết định permission với input rõ.
2. WebFlux slice test route authorization/status với security test support đúng version.
3. Full context/HTTP test cho vài luồng security quan trọng để xác nhận filter chain và boot configuration.
4. Test với token thật ký bởi test key/provider sandbox nếu yêu cầu kiểm decoder/issuer/audience/cors.

**Cảnh báo:** Nếu test HTTP 401/403 thất bại do thiếu credentials hoặc CSRF, đừng tắt security globally chỉ để chuyển sang 200. Hãy xác định contract, thiết lập security fixture phù hợp và giữ ít nhất các integration test bảo vệ policy quan trọng.

Ví dụ runnable ở mục 9–12 **không khai báo dependency Spring Security**. Vì vậy dự kiến request không bị security chặn; trong dự án thật thêm dependency có thể đổi status/behavior.

## 17. Transaction, R2DBC và database: web slice không đủ

`@WebFluxTest` không mặc định nạp reactive repository hoặc R2DBC connection pool. Nếu endpoint trả sẵn dữ liệu từ mocked service, toàn bộ SQL, schema, converter và mapping vẫn chưa chạy.

Với Spring Data R2DBC hoặc reactive DB, cần quan tâm:

- SQL/query thực sự có hợp lệ trên DB mục tiêu không?
- Entity/table mapping, converter và null handling có đúng không?
- Reactive transaction có áp dụng qua `TransactionalOperator` hoặc `@Transactional` theo cơ chế reactive phù hợp không?
- Hành vi commit/rollback thực tế đúng không?
- Concurrent requests, optimistic locking hoặc unique constraint có được bảo vệ không?

Đó là lý do nên có **repository integration tests** với database được kiểm soát, migrations và fixture phù hợp. Fake repository trong memory chỉ chứng minh những đường logic sử dụng fake, không chứng minh SQL.

### 17.1. `@Transactional` trên method test không bảo đảm rollback HTTP server

Khi dùng `@SpringBootTest(RANDOM_PORT)`, JUnit client và HTTP server thường xử lý trên những thread/transaction contexts khác nhau. Transaction gắn với test method **không tự bao trùm** transaction mà server tạo để xử lý request. Trong WebFlux, transaction reactive còn có Reactor Context semantics.

Vì thế, viết:

```java
// PHẢN VÍ DỤ suy luận:
// @Transactional trên JUnit test không tự rollback
// tất cả writes do HTTP server thực hiện ở luồng riêng.
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@Transactional
class DatabaseHttpTest {
}
```

không đủ bảo đảm database sạch sau mỗi test. Đây chỉ là snippet, không có repository/config chạy. Hãy dùng database test riêng, dữ liệu cô lập, cleanup/fixture reset hoặc transaction setup đúng boundary, và kiểm việc commit/rollback tại nơi nó xảy ra.

## 18. WebClient, broker, scheduler: full context cũng có giới hạn

Ngay cả `@SpringBootTest(RANDOM_PORT)` vẫn chưa tự trở thành E2E của một hệ thống phân tán.

| Boundary | Test cần thiết ngoài web slice | Giới hạn cần nhớ |
|---|---|---|
| Outbound HTTP qua `WebClient` | Adapter test với mock HTTP server, test timeout/status/header/retry | Nếu mock adapter, không kiểm HTTP protocol thật |
| Kafka/RabbitMQ | Producer/consumer integration test với broker test | `verify(publisher)` chỉ kiểm interaction, không kiểm delivery |
| Redis/cache | Test cache key/TTL/serialization với test Redis nếu cần | Fake map không kiểm TTL hoặc wire protocol |
| Scheduler/async event | Test job trigger, event handling, lifecycle riêng | Slice thường không nạp job; full HTTP test không mặc định chờ side effect async |
| Remote auth/OAuth2 | Test token validation + HTTP security boundary | Mock principal không xác minh remote provider |
| PostgreSQL/MySQL/R2DBC | Repository + migration + transaction integration tests | In-memory fake không chứng minh SQL và locking |
| Actual API gateway/TLS/ingress | Staging E2E/contract/infrastructure tests | localhost HTTP server không đi qua production gateway |

**Full context** có nghĩa Spring nạp application configuration cho phạm vi test, **không đồng nghĩa mọi remote service production đã được bật hoặc đã được gọi**. Cần phân biệt logic thật, fake/fixture và external resources cụ thể.

### 18.1. Không gọi dịch vụ production từ test

Bài kiểm thử nên tránh phụ thuộc credential production, data thật hoặc đối tác bên ngoài không có sandbox. Các lựa chọn gồm mock HTTP server, Testcontainers, local fake và test tenant/database riêng. Với test thực sự gọi sandbox, nên kiểm soát timeout, retry, cleanup và giới hạn tần suất.

### 18.2. “Nhiều bean thật” không phải mục tiêu tự thân

Nếu mục tiêu chỉ là endpoint JSON contract, nạp Kafka consumer, DB migrations và scheduled jobs để “test giống thật hơn” có thể làm suite chậm, flaky và tăng rủi ro. Tăng độ tích hợp **khi hợp đồng và loại lỗi cần bắt đòi hỏi**, không phải vì annotation lớn hơn được cho là tốt hơn.

## 19. Bean override đúng chỗ: `@MockitoBean` không phải thuốc chữa mọi lỗi

Trong Spring Boot 3.4+/Spring Framework 6.2+, `@MockitoBean` của package `org.springframework.test.context.bean.override.mockito` cho phép override hoặc tạo mock bean trong TestContext. Với `@WebFluxTest`, đây là cách phổ biến để cung cấp service cho constructor controller.

So sánh:

| Kỹ thuật | Tác động vào context | Dùng khi |
|---|---|---|
| `Mockito.mock(QuoteService.class)` trong unit test | Không | Tự tạo controller/service và truyền dependency |
| `@Mock` cùng MockitoExtension | Không trực tiếp thay Spring bean | Unit test Mockito thuần |
| `@MockitoBean QuoteService service` | Đưa mock vào context hoặc thay bean | Web slice test cần service collaborator |
| `@MockitoSpyBean` | Wrap bean thật theo cơ chế TestContext | Partial mocking thật sự cần thiết, chú ý side effects và AOP |
| `@TestConfiguration` + `@Import` | Đưa test beans vào context | Fake implementation có hành vi ổn định |
| `@SpringBootTest` | Nạp application context rộng | Kiểm wiring/config/integration |

**Những rủi ro khi override sai:**

1. Nếu test đang kiểm `QuoteService` nhưng lại dùng `@MockitoBean QuoteService`, test không chạy logic mà nó tuyên bố kiểm.
2. Nếu cần chắc chắn bean production tồn tại và được thay, trong Spring Framework 6.2+ có `@MockitoBean(enforceOverride = true)` để báo lỗi khi thiếu bean đích. Trong MVC/WebFlux slice, service thật thường không có, nên `enforceOverride=true` có thể làm test fail đúng như thiết kế.
3. Nhiều bean cùng type có thể cần qualifier/bean name cụ thể; framework không phải lúc nào cũng biết bạn muốn thay bean nào.
4. Các cấu hình mock khác nhau có thể thay context cache key, khiến suite tạo thêm nhiều context.
5. Mock bean thay thế có thể không mang advice của bean cũ; không dùng nó để khẳng định behavior `@Transactional`, retry, security hoặc cache production.

Với Spring Boot 3.3 trở về trước, `@MockBean` là API thường dùng; trong Boot 3.4 nó đã được deprecated để chuyển sang API Spring TestContext mới. Đừng trộn version/annotation mà không kiểm lại context behavior.

## 20. Performance, context cache và test isolation

Một bộ test được chia lớp hợp lý vừa bắt lỗi tốt vừa có chi phí vận hành dễ kiểm soát.

- **Unit test + StepVerifier**: không cần context; thường nhanh và ít phụ thuộc môi trường.
- **WebFlux slice**: nạp web infrastructure cần thiết, thường nhẹ hơn full Boot context.
- **Full context mock HTTP**: kiểm wiring/auto-configuration và flow Spring thật, nhưng không dùng TCP.
- **Full context random port**: kiểm thêm embedded server và transport; startup/test runtime tốn hơn.
- **DB/broker/remote integration**: thêm công cụ và cleanup; chi phí cao nhưng bảo vệ contract không thể thay bằng mock.

Spring TestContext cache `ApplicationContext` theo cấu hình. Hai test có cùng bootstrap settings có thể chia sẻ context trong JVM; hai test khác nhau về `@ActiveProfiles`, test properties, `@MockitoBean`, import hoặc web environment thường cần cache key khác. Vì vậy, dùng hàng chục tổ hợp `@SpringBootTest`/mock bean không cần thiết có thể làm CI chậm dù mỗi test chỉ vài dòng.

**Test isolation:** full context có singleton bean, connection pool và data store; một test thay state có thể ảnh hưởng test khác. Context cache không tự reset mọi singleton mutable hoặc data ngoài. Dùng dữ liệu test độc lập, cleanup/fake reset và test design có chủ đích. Đừng gắn `@DirtiesContext` vào mọi method chỉ để ép test pass; nó tăng chi phí khởi động và không cleanup mọi tài nguyên ngoài context.

## 21. Gradle và lệnh chạy bộ ví dụ

Trong một dự án Gradle đã cấu hình **Spring Boot 3.5.x plugin/BOM**, Java 17+ và repositories, có thể dùng phần dependencies:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Đây là **đoạn cấu hình bổ sung cho build đã có plugins và version management**, không phải file `build.gradle` độc lập. Nếu `spring-boot-starter-test` đã mang `reactor-test` theo dependency graph của phiên bản bạn dùng, không cần thêm lặp; có thể kiểm bằng Gradle dependencies.

**Không thêm `spring-boot-starter-web` vào ví dụ** vì điều đó có thể chuyển application type sang servlet theo mặc định và làm mất tính nhất quán của mục tiêu WebFlux.

Thư mục test cần có ba file:

```text
QuoteServiceUnitTest.java
QuoteWebFluxSliceTest.java
QuoteFullHttpTest.java
```

Lệnh chạy:

```bash
./gradlew test --tests com.example.webfluxscope.QuoteServiceUnitTest --tests com.example.webfluxscope.QuoteWebFluxSliceTest --tests com.example.webfluxscope.QuoteFullHttpTest
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat test --tests com.example.webfluxscope.QuoteServiceUnitTest --tests com.example.webfluxscope.QuoteWebFluxSliceTest --tests com.example.webfluxscope.QuoteFullHttpTest
```

Với multi-project Gradle, dùng đúng `:your-module:test` theo tên module thực tế.

**Kết quả được thiết kế trong code ví dụ:**

- `QuoteServiceUnitTest` có **4** test bảo vệ policy/service reactive thật.
- `QuoteWebFluxSliceTest` có **2** test bảo vệ mapping/JSON/error advice của WebFlux slice với mock service.
- `QuoteFullHttpTest` có **3** test bảo vệ HTTP request qua server thật, service/policy/catalog thật và 404/400.
- Tổng cộng **9 test methods**. Nếu project được cấu hình đúng, tất cả dự kiến xanh; Gradle báo `BUILD SUCCESSFUL`.
- Phần service demo không in stdout nghiệp vụ cố định. Log server, port ngẫu nhiên và thời gian chạy không được xem là expected output cố định.

Đây là **kết quả dự kiến từ phân tích mã**, không phải tuyên bố đã chạy Gradle hoặc dựng server trong repository hiện tại. Các đoạn ghi **snippet** ở những mục khác không phải file Java độc lập trong danh sách runnable.

Có thể mở báo cáo của Gradle tại `build/reports/tests/test/index.html`, hoặc XML ở `build/test-results/test/` tương ứng với build directory của module.

## 22. Troubleshooting: đọc lỗi theo tầng

| Triệu chứng | Nguyên nhân khả dĩ | Cách xử lý |
|---|---|---|
| `NoSuchBeanDefinitionException: QuoteService` trong slice | `@WebFluxTest` không scan service | Dùng `@MockitoBean` ở boundary hoặc import collaborator cần thiết |
| Slice pass nhưng production tính tiền sai | Service trong slice bị mock | Thêm unit/service test chạy logic thật và integration test phù hợp |
| Slice 404 cho functional endpoint | RouterFunction không được tự phát hiện | `bindToRouterFunction`, `@Import` hoặc full Boot test |
| HTTP 200 trong slice nhưng full context fail | Bean, property, profile, auto-config hoặc external dependency chưa được slice nạp | Debug root cause ở full context, không “chữa” bằng nhiều mock ngẫu nhiên |
| `WebTestClient` null trong full mock context | Chưa `@AutoConfigureWebTestClient` hoặc web application type sai | Thêm annotation đúng và kiểm starter/type |
| Full random-port test không kết nối được | Server startup fail, port/client wiring hoặc web stack không phù hợp | Đọc log startup, root exception, dùng random port, kiểm dependencies |
| Response 401/403 bất ngờ | SecurityWebFilterChain khác kỳ vọng hoặc test credentials thiếu | Thiết lập security test đúng contract, không tắt security bừa |
| HTTP test không rollback DB | Server request chạy ở transaction/context khác | Dùng DB test isolation và cleanup riêng, đừng dựa vào test method transaction |
| Test Flux bị treo | Stream không hoàn thành nhưng test đợi completion | Assert số event hữu hạn, cancellation và timeout |
| Reactive code lỗi do blocking call | Service thật dùng I/O blocking trên event loop | Tách blocking adapter, dùng scheduler phù hợp hoặc reactive driver; bổ sung integration/concurrency test |
| Một test pass riêng nhưng fail trong suite | Data/state singleton/DB/context cache dùng chung | Dữ liệu độc lập, cleanup, tránh test order assumption |
| Bật cả web và webflux thì test chuyển stack | Servlet/MVC app type được Boot ưu tiên | Chọn starter/type rõ ràng và test đúng web stack |
| Mock server pass nhưng thực tế TLS/gateway fail | Slice/full mock env không có network transport tương ứng | Dùng HTTP staging/infrastructure test qua boundary thật |
| Context full rất chậm | Nạp quá nhiều infrastructure hoặc context cache phân mảnh | Đẩy logic thuần về unit tests, dùng slice/targeted integration, gom cấu hình |

**Cách debug từng bước:**

1. Xác định test annotation và `webEnvironment`.
2. Xác định `WebTestClient` đang bind vào controller/context hay TCP server.
3. Kiểm bean nào là Mockito mock, bean nào là implementation thật.
4. Đọc root cause của `Failed to load ApplicationContext`, phân biệt missing bean/auto-config/profile/connection.
5. Xác nhận dữ liệu test thuộc fake/in-memory hay adapter ngoài.
6. Chọn thêm test ở ranh giới còn thiếu; không mở toàn bộ ứng dụng chỉ vì một controller test fail.
7. Sau sửa, chạy lại cả test nhanh và integration test tương ứng để không mất coverage ở tầng khác.

## 23. Bài tập tự kiểm tra

### Bài A — test xanh có chứng minh nghiệp vụ đúng không?

`@WebFluxTest` dùng `@MockitoBean QuoteService` để trả `QuoteView(totalVnd=216000)`. Controller trả đúng JSON; test pass. Nếu `DiscountPolicy` production bị đổi từ 10% thành 5%, test có đỏ không?

**Đáp án:** Không nhất thiết, vì service và policy thật không chạy. Hãy bổ sung `StepVerifier` trên service thật, và một integration test chạy service/policy khi cần.

### Bài B — chọn đúng một trong ba môi trường

Yêu cầu:

1. Kiểm `@GetMapping` và JSON field.
2. Kiểm wiring của controller/service/repository trong Spring context mà không cần network.
3. Kiểm real HTTP server port binding.

**Đáp án định hướng:** (1) `@WebFluxTest`, (2) `@SpringBootTest` + `@AutoConfigureWebTestClient` với mock web environment, (3) `@SpringBootTest(RANDOM_PORT)`.

### Bài C — functional routing

Một ứng dụng khai báo endpoint bằng `RouterFunction<ServerResponse>`. Test `@WebFluxTest` chỉ có annotated controller khác, endpoint functional biến mất. Có phải route production sai?

**Đáp án:** Chưa đủ bằng chứng. `@WebFluxTest` không tự phát hiện functional routes đầy đủ. Test bằng `bindToRouterFunction` hoặc import router/handler có chủ đích; để kiểm production registration dùng full Boot context.

### Bài D — database reactive và HTTP

JUnit method có `@Transactional`, test gọi HTTP qua `RANDOM_PORT` và sau đó thấy record vẫn nằm trong DB. Vì sao rollback của test không xử lý?

**Đáp án:** HTTP server xử lý ở request/transaction context khác; reactive transaction dùng Reactor Context và có ranh giới riêng. Phải có cleanup, isolated test DB hoặc thiết kế transaction/fixture đúng.

### Bài E — đánh giá test double

Trong web slice, `QuoteService` mock là hợp lý vì mục tiêu là controller. Trong service unit test, mock chính `QuoteService` rồi assert kết quả mock trả về có ý nghĩa không?

**Đáp án:** Hầu như không kiểm code thật; chỉ chứng minh stubbing. Unit test nên dùng service thật, fake/mock outbound gateway, assert các business outcomes.

### Bài F — security

Một test có `@WithMockUser` đi qua WebFlux slice và nhận HTTP 200. Có thể kết luận JWT parser và OAuth2 issuer production hoạt động không?

**Đáp án:** Không. Mock user giả lập principal; cần security integration/HTTP test cho decoder/issuer/authority mapping và filter chain thật, với token fixture phù hợp.

### Bài G — streaming

Endpoint trả `Flux<ServerSentEvent<Event>>` vô hạn. Vì sao `StepVerifier.expectComplete()` sẽ treo? Nêu cách kiểm số event hữu hạn và `thenCancel` hoặc timeout. Nếu điều cần bảo vệ là flushing qua TCP, test nào phải bổ sung?

**Đáp án:** Stream không emit onComplete theo contract; dùng finite expectation + cancellation và HTTP stream integration test với server thật khi cần.

### Bài H — định nghĩa “full”

Bạn có `@SpringBootTest(RANDOM_PORT)`, nhưng repository là in-memory fake và outbound WebClient bị mock. Có thể gọi đây là E2E với DB và remote service thật không?

**Đáp án:** Không. Đây là full application/server test trong phạm vi các dependency được cấu hình. Chỉ báo coverage theo những component thực sự chạy.

## 24. Checklist chốt test WebFlux

- [ ] Tôi viết rõ bug nào bài test phải bắt.
- [ ] Tôi biết `@WebFluxTest` nạp web layer và thường không nạp service/repository.
- [ ] Tôi không nhầm bean mock do test tạo với service thật được scan.
- [ ] Tôi kiểm HTTP contract qua `WebTestClient`, không tuyên bố đã kiểm business policy nếu policy không chạy.
- [ ] Tôi có unit/service tests dùng `StepVerifier` cho logic reactive cốt lõi.
- [ ] Functional routes được kiểm bằng router test/import/full context phù hợp.
- [ ] Tôi phân biệt mock web environment với HTTP server `RANDOM_PORT`.
- [ ] Khi cần kiểm DI/profile/auto-config, tôi dùng full context mà không vô tình mock hết bean quan trọng.
- [ ] Khi cần network runtime, tôi khởi động server thật và xác minh request qua TCP.
- [ ] Khi cần DB/transaction, tôi dùng repository/DB test đúng boundary, không dựa vào fake.
- [ ] Tôi không cho rằng transaction của JUnit method rollback thay server requests.
- [ ] Security, WebFilter, error handler và config thực sự được nạp đúng cho hợp đồng cần kiểm.
- [ ] Reactive streams, error, backpressure và cancellation được kiểm ở cấp phù hợp.
- [ ] External HTTP/broker/queue có contract hoặc integration tests riêng; không gọi production ngoài quyền kiểm soát.
- [ ] Singleton state, context cache và dữ liệu test được cô lập.
- [ ] Test suite có nhiều cấp nhỏ, dễ hiểu; không dùng full context cho mọi phép tính rẻ.

**Kết luận:** `@WebFluxTest` là công cụ tốt để xác minh **lát cắt web**. Nó nhanh và đúng mục tiêu vì không chạy mọi service, repository, transaction, functional route hoặc external adapter của hệ thống. Nhưng chính vì thế, một response JSON đúng từ mocked service **không phải bằng chứng toàn bộ ứng dụng chạy đúng**. Để bảo vệ đầy đủ, hãy giữ những test nhỏ kiểm logic thật, rồi thêm `@SpringBootTest`, HTTP server, database và external-contract tests **đúng nơi loại lỗi cần bắt đòi hỏi**.

### Tài liệu tham khảo chính thức

- Spring Boot 3.5 — Testing Spring Boot Applications, *Auto-configured Spring WebFlux Tests*: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Boot 3.5 JavaDoc — `@WebFluxTest` và giới hạn component scan: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/web/reactive/WebFluxTest.html
- Spring Framework — `WebTestClient`, controller/context/router/server binding: https://docs.spring.io/spring-framework/reference/testing/webtestclient.html
- Spring Framework — Reactive Transactions: https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html
- Reactor — Testing & `StepVerifier`: https://projectreactor.io/docs/core/release/reference/testing.html

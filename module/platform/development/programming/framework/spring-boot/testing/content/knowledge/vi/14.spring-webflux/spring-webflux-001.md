# @WebFluxTest và thành phần web được đưa vào context trong Spring Boot

## 1. Mục tiêu: kiểm thử WebFlux handler mà không dựng toàn bộ ứng dụng

Một ứng dụng Spring Boot sử dụng **Spring WebFlux** có thể có controller phản hồi bằng `Mono<T>` hoặc `Flux<T>`, đọc JSON request body, chuyển đổi path/query parameters, áp dụng Bean Validation, xử lý lỗi qua `@RestControllerAdvice` và chạy `WebFilter`. Những hành vi web này cần được kiểm tra **qua pipeline Spring WebFlux thực**, nhưng không nhất thiết phải kết nối cơ sở dữ liệu, message broker hoặc chạy toàn bộ hệ thống.

`@WebFluxTest` là **test slice** chuyên biệt của Spring Boot để kiểm tra tầng web reactive (annotated controllers). Nó cố gắng tạo một `ApplicationContext` chỉ bao gồm hạ tầng WebFlux và những loại bean web cần thiết, đồng thời tránh nạp toàn bộ `@Service`, `@Repository` và các cấu hình hạ tầng không thuộc phạm vi.

Ví dụ, endpoint `GET /api/items/41` có thể gặp các lỗi:
- Request không map tới controller do sai `@GetMapping` hoặc `@PathVariable`.
- Tham số SKU không được chuyển sang kiểu miền như `Sku`.
- Kết quả `Mono<ItemView>` được serialize thành JSON sai cấu trúc.
- `Mono.error(new ItemNotFoundException(...))` không được advice biến thành HTTP 404.
- `@Valid` không kích hoạt hoặc trả lỗi khác hợp đồng khi request body sai.
- Một `WebFilter` không được đăng ký hoặc vô tình chặn request.

Các lỗi này **không được phát hiện** khi chỉ unit test trực tiếp `ItemService`. Ngược lại, mở cả application context chỉ để kiểm tra JSON mapping có thể làm test chậm, phụ thuộc DB, API ngoài và khó chẩn đoán.

**Phạm vi đúng của `@WebFluxTest`:** chứng minh request/response và các thành phần WebFlux **đã được đưa vào slice**, không phải toàn bộ nghiệp vụ, persistence, security production hay HTTP socket thật đều đã được xác minh.

## 2. WebFlux khác Spring MVC tại pipeline kiểm thử

Spring WebFlux và Spring MVC đều hỗ trợ annotation như `@RestController`, `@GetMapping`, `@RequestBody`, `@ControllerAdvice`, nhưng hạ tầng bên dưới khác nhau.

```text
WebTestClient request
        |
        v
WebFlux WebHandler / WebFilter chain
        |
        v
HandlerMapping tìm @RestController
        |
        v
HandlerAdapter + argument resolvers
        |        |
        |        +-- Converter/Formatter cho @PathVariable, @RequestParam
        |        +-- Body readers/decoders cho JSON request
        |        +-- Validation nếu cấu hình/provider phù hợp
        |
        v
ItemController (implementation thật)
        |
        +----> ItemService mock (trả Mono/Flux theo test)
        |
        v
Mono/Flux được subscribe bởi WebFlux runtime
        |
        +----> @RestControllerAdvice khi lỗi phù hợp
        +----> HttpMessageWriter/Encoder cho JSON response
        |
        v
WebFilter có thể hoàn tất/biến đổi response
        |
        v
HTTP status + headers + body được WebTestClient kiểm tra
```

Sơ đồ là cách nhìn khái niệm; thứ tự xử lý filter, handler và lỗi phụ thuộc cấu hình thực tế. `WebFilter` thường bao quanh chain, nên nó có thể chạy trước và sau khi xử lý phần phía trong theo tín hiệu reactive.

| Vấn đề | Spring MVC | Spring WebFlux |
|---|---|---|
| Test slice tiêu biểu | `@WebMvcTest` | `@WebFluxTest` |
| Client test phổ biến | `MockMvc` | `WebTestClient` |
| Filter cấp web | Servlet `Filter` / `OncePerRequestFilter` | `WebFilter` |
| Đọc/ghi body | `HttpMessageConverter` | `HttpMessageReader` / `HttpMessageWriter` và codecs |
| Mô hình handler | Thường gọi đồng bộ; có thể hỗ trợ async | Nền Reactive Streams, trả `Mono`/`Flux` |
| Web request thực | Servlet container khi chạy server | Reactive server tùy runtime (ví dụ Reactor Netty) |
| Security filter chain | `SecurityFilterChain` (servlet) | `SecurityWebFilterChain` (reactive) |
| Component quét trong slice | Loại MVC-related | Loại WebFlux-related |

**Đừng nhập nhằng `MockMvc` và `WebTestClient`:** WebTestClient có thể được **bind vào `ApplicationContext`** không có listening TCP port hoặc kết nối tới **HTTP server đang chạy**; API gọi khá giống nhau nhưng phạm vi bằng chứng khác.

## 3. @WebFluxTest thực sự nạp những loại bean nào?

Khai báo điển hình:

```java
@WebFluxTest(controllers = ItemController.class)
class ItemControllerWebFluxTest {
    // @Autowired WebTestClient client;
}
```

Đây là mẫu annotation, chưa phải tệp test độc lập. `controllers = ...` giới hạn các **controller được chọn**; nó không có nghĩa context chỉ có đúng một bean hay tự động loại mọi advice/filter dùng chung.

Trong Spring Boot 3.4/3.5, `@WebFluxTest` áp dụng type filtering tập trung vào web layer. Các nhóm thường được giữ lại khi chúng được quét/đăng ký phù hợp:

| Loại bean | Vai trò | Cần hiểu gì? |
|---|---|---|
| `@Controller`, `@RestController` | Mapping request tới handler | Có thể giới hạn bằng `controllers=...` |
| `@ControllerAdvice`, `@RestControllerAdvice` | `@ExceptionHandler`, quy tắc xử lý chung | Advice toàn cục vẫn có thể xuất hiện cùng một selected controller |
| `@JsonComponent` | Jackson serializer/deserializer đặc thù | Hữu ích khi codec JSON được cấu hình tương ứng |
| `Converter`, `GenericConverter` | Chuyển đổi giá trị trong binding | Phải thực sự đăng ký vào conversion service được handler dùng |
| `WebFluxConfigurer` | Tùy biến formatters, codecs, CORS và các phần WebFlux khác | Có thể kéo theo cấu hình hoặc bean phụ thuộc nếu quét quá rộng |
| `WebFilter` | Lọc request/response trong reactive chain | Cần xác minh filter thật sự thực thi, không chỉ có bean |
| Infrastructure WebFlux | Mapping, handler adapters, readers/writers, validation... | Tùy auto-configuration/classpath và các customizers được nạp |
| `WebTestClient` | Thực thi request test và assert response | `@WebFluxTest` thường tự auto-configure client |

**Không phải mọi `@Component` tùy ý đều được nạp.** `@Service`, `@Repository`, custom persistence components và nhiều configuration ngoài web slice thường bị loại. Một `@Component` **đồng thời triển khai kiểu được phép** như `WebFilter` hoặc `WebFluxConfigurer` có thể được giữ, trong khi một business component thuần túy không.

Các `WebExceptionHandler`, `SecurityWebFilterChain`, custom `CodecCustomizer`, `RouterFunction` và những thành phần nâng cao **không nên mặc nhiên được coi là đã nạp**: chúng phụ thuộc phiên bản Boot, auto-configuration, component scan, import và cơ chế đăng ký của dự án. Test phải xác nhận phạm vi khi chúng thuộc yêu cầu.

### 3.1. @WebFluxTest không tự mang vào những gì?

Ví dụ controller cần `ItemService`:

```java
@RestController
class ItemController {
    private final ItemService items;

    ItemController(ItemService items) {
        this.items = items;
    }
}
```

Nếu `ItemService` chỉ là một service implementation bình thường và không có bean trong slice, controller có thể không tạo được, gây `UnsatisfiedDependencyException` khi context khởi động. Đây là **hành vi slice đúng**: nó không nạp business layer chỉ vì controller tham chiếu tới business layer.

Cách giải quyết là **cung cấp mock/fake service rõ ràng**, hoặc chuyển sang integration test nếu mục tiêu thực sự là kiểm tra business/persistence. Đừng mở toàn bộ `@SpringBootTest` cho mọi test controller chỉ để tránh khai báo mock.

## 4. Cấu hình @MockitoBean cho dependency bên ngoài web slice

Với Spring Framework 6.2+ / Spring Boot 3.4–3.5, dùng:

```java
@MockitoBean
ItemService service;
```

Import: `org.springframework.test.context.bean.override.mockito.MockitoBean`.

`@MockitoBean` tạo hoặc thay một bean trong Spring TestContext bằng Mockito mock. Controller thật được Spring inject mock này. Trong test, ta có thể quy định:

```java
when(service.findById(41L))
        .thenReturn(Mono.just(new ItemView(41L, "Mouse", 125_000)));
```

Những đoạn này là ví dụ minh họa trong một test có khai báo `service`, `ItemView`, `Mono` và imports Mockito; phần code chạy đầy đủ ở mục 5.

| Công cụ | Có thay bean trong context? | Khi nào dùng |
|---|---|---|
| Mockito `@Mock` | **Không tự động** | Unit test tạo controller/service thủ công |
| `@MockitoBean` của Spring TestContext | **Có** | Slice/integration test giữ controller thật |
| `@MockBean` cũ của Spring Boot | Có ở các phiên bản Boot hỗ trợ | Dự án Boot cũ; từ Boot 3.4 đã được đánh dấu deprecated |
| `@Bean` fake trong `@TestConfiguration` | Có nếu test config được import/nạp | Khi muốn fake có trạng thái hoặc hành vi được định nghĩa rõ |

Không dùng import `@MockitoBean` của Spring Framework 6.2 với một dự án Boot 3.2 hoặc 3.3 chưa nâng Spring TestContext tương ứng. Trong ví dụ, `@MockitoBean` nhắm **Boot 3.4/3.5 + Java 17+**. Với các dòng lớn mới hơn, cần kiểm tra lại packages/dependencies trên phiên bản thật.

**Không mock controller** khi muốn kiểm tra route, binding, validation hay advice. `@WebFluxTest` hướng tới controller implementation thật cùng infrastructure reactive; chỉ giả lập dependency không thuộc phạm vi đang kiểm chứng.

## 5. Ví dụ Java 17+ chạy được: Controller + Advice + Converter + WebFilter

### 5.1. Hợp đồng API và điều kiện chạy

Ta xây dựng một API mặt hàng có các yêu cầu:

1. `GET /api/items/{id}`: trả `200` và JSON khi service phát ra một `ItemView`.
2. Nếu service phát `Mono.error(ItemNotFoundException)`: `@RestControllerAdvice` trả `404` với `{"code":"ITEM_NOT_FOUND"}`.
3. `GET /api/items/sku/{sku}`: chuyển chuỗi `ab-7` thành `Sku("AB-7")` thông qua `Converter<String,Sku>`, rồi đưa `"AB-7"` vào service.
4. `POST /api/items`: đọc JSON body thành `CreateItemRequest`, kiểm tra `@NotBlank` và `@Positive`, tạo `201` với JSON item mới.
5. Body vi phạm validation: trả `400`, JSON lỗi `{"code":"INVALID_ITEM"}`, và **không gọi service**.
6. `WebFilter` gắn `X-WebFlux-Filter: applied`; test phải quan sát header để xác nhận filter thực sự chạy.

Ví dụ cần một dự án **Spring Boot 3.4/3.5** dùng Java 17+, WebFlux stack, Bean Validation provider, Jackson JSON, JUnit Jupiter, Mockito và Spring TestContext. Để tránh security filter cản request vô danh trong ví dụ, **không thêm Spring Security starter** vào dependency mẫu; nếu dự án đã có security, xem mục 9.

Cấu hình Gradle Groovy DSL minh họa, giả định build script đã thiết lập Spring Boot plugin, Java toolchain và Maven Central:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Đây là một **đoạn build script**, không phải toàn bộ `build.gradle`. Không đồng thời đưa `spring-boot-starter-web` vào chỉ để dùng `MockMvc`: MVC và WebFlux có cơ chế chọn web application type khác nhau; nếu dự án cố tình có cả hai, phải nêu rõ stack nào được chọn và test nào đang chạy.

Cấu trúc tệp:

```text
src/main/java/com/example/webfluxtest/
    WebFluxSliceApplication.java
    ItemView.java
    CreateItemRequest.java
    Sku.java
    ItemService.java
    ItemNotFoundException.java
    ItemController.java
    ItemErrorAdvice.java
    SkuWebFluxConfigurer.java
    TraceHeaderWebFilter.java

src/test/java/com/example/webfluxtest/
    ItemControllerWebFluxTest.java
```

### 5.2. Application bootstrap để xác định package scan

Tệp `src/main/java/com/example/webfluxtest/WebFluxSliceApplication.java`:

```java
package com.example.webfluxtest;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebFluxSliceApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebFluxSliceApplication.class, args);
    }
}
```

Dù có lớp `@SpringBootApplication`, `@WebFluxTest` **không** nạp tất cả bean ứng dụng theo cách full integration test. Nó dùng Boot test bootstrapper và slice filters để giới hạn phạm vi.

### 5.3. DTO, giá trị miền và service contract

Tệp `src/main/java/com/example/webfluxtest/ItemView.java`:

```java
package com.example.webfluxtest;

public record ItemView(long id, String name, int price) {}
```

Tệp `src/main/java/com/example/webfluxtest/CreateItemRequest.java`:

```java
package com.example.webfluxtest;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Positive;

public record CreateItemRequest(
        @NotBlank String name,
        @Positive int price) {}
```

Tệp `src/main/java/com/example/webfluxtest/Sku.java`:

```java
package com.example.webfluxtest;

public record Sku(String value) {}
```

Tệp `src/main/java/com/example/webfluxtest/ItemService.java`:

```java
package com.example.webfluxtest;

import reactor.core.publisher.Mono;

public interface ItemService {
    Mono<ItemView> findById(long id);
    Mono<ItemView> findBySku(String sku);
    Mono<ItemView> create(CreateItemRequest request);
}
```

Tệp `src/main/java/com/example/webfluxtest/ItemNotFoundException.java`:

```java
package com.example.webfluxtest;

public final class ItemNotFoundException
        extends RuntimeException {

    public ItemNotFoundException(String message) {
        super(message);
    }
}
```

`ItemService` **chỉ là interface**: ví dụ không có implementation service hay repository. Test cung cấp bean mock và các publisher `Mono.just(...)`/`Mono.error(...)` để chủ động điều khiển kết quả reactive. `ItemView` và `CreateItemRequest` là Java records thật; record có equality theo component, giúp kiểm tra chính xác DTO được truyền qua mock.

### 5.4. Controller thật trả Mono

Tệp `src/main/java/com/example/webfluxtest/ItemController.java`:

```java
package com.example.webfluxtest;

import jakarta.validation.Valid;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/items")
public class ItemController {

    private final ItemService service;

    public ItemController(ItemService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    public Mono<ItemView> findById(@PathVariable("id") long id) {
        return service.findById(id);
    }

    @GetMapping("/sku/{sku}")
    public Mono<ItemView> findBySku(@PathVariable("sku") Sku sku) {
        return service.findBySku(sku.value());
    }

    @PostMapping
    public Mono<ResponseEntity<ItemView>> create(
            @Valid @RequestBody CreateItemRequest request) {
        return service.create(request)
                .map(item -> ResponseEntity
                        .status(HttpStatus.CREATED)
                        .body(item));
    }
}
```

Ở đây:
- `@PathVariable("id") long` dùng converter mặc định để đọc số từ URL.
- `@PathVariable("sku") Sku` cần converter được đăng ký ở mục tiếp theo.
- `@Valid @RequestBody` yêu cầu decode JSON thành `CreateItemRequest` và validate sau binding.
- `Mono<ItemView>` cho phép WebFlux subscribe vào publisher rồi viết JSON qua codec.
- `Mono<ResponseEntity<ItemView>>` cho phép quyết định status sau khi có giá trị từ service, ở đây là `201 Created`.

**Không dùng `.block()` trong controller**: một trong những mục tiêu của reactive handler là không chặn thread chờ publisher. WebTestClient sẽ chờ response hoàn tất trong ngữ cảnh test theo cơ chế của nó.

### 5.5. WebFluxConfigurer đăng ký Converter cho SKU

Tệp `src/main/java/com/example/webfluxtest/SkuWebFluxConfigurer.java`:

```java
package com.example.webfluxtest;

import java.util.Locale;

import org.springframework.core.convert.converter.Converter;
import org.springframework.format.FormatterRegistry;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.config.WebFluxConfigurer;

@Component
public class SkuWebFluxConfigurer implements WebFluxConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(new SkuConverter());
    }

    private static final class SkuConverter
            implements Converter<String, Sku> {

        @Override
        public Sku convert(String source) {
            if (source == null || source.isBlank()) {
                throw new IllegalArgumentException("SKU is blank");
            }
            return new Sku(
                    source.trim().toUpperCase(Locale.ROOT));
        }
    }
}
```

`WebFluxConfigurer` là một nhóm type được MVC/WebFlux slice filter giữ lại trong cấu hình WebFlux tương ứng. Trong ví dụ, class cùng package gốc và `@Component` được dùng để Spring nhận diện. Method `addFormatters` chủ động đăng ký `String -> Sku`, nên test không cần dựa vào việc một converter riêng lẻ có tự động được gắn vào đúng conversion service hay không.

**Phân biệt:** `Converter<String,Sku>` này xử lý **binding của path variable**, không phải JSON codec. Phần JSON body dùng reactive HTTP message readers/writers thông qua Jackson và các `CodecConfigurer` được nạp.

Nếu một ứng dụng có custom `WebFluxConfigurer` nằm ngoài package scan của test hoặc đã bị filter loại, nó có thể không được đăng ký. Khi đó có thể dùng `@Import(SkuWebFluxConfigurer.class)` và xác minh thông qua argument được mock service nhận.

### 5.6. Advice cho lỗi nghiệp vụ và validation

Tệp `src/main/java/com/example/webfluxtest/ItemErrorAdvice.java`:

```java
package com.example.webfluxtest;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.bind.support.WebExchangeBindException;

@RestControllerAdvice
public class ItemErrorAdvice {

    @ExceptionHandler(ItemNotFoundException.class)
    public ResponseEntity<Map<String, String>> missing(
            ItemNotFoundException ex) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(Map.of("code", "ITEM_NOT_FOUND"));
    }

    @ExceptionHandler(WebExchangeBindException.class)
    public ResponseEntity<Map<String, String>> invalid(
            WebExchangeBindException ex) {
        return ResponseEntity.badRequest()
                .body(Map.of("code", "INVALID_ITEM"));
    }
}
```

`@RestControllerAdvice` có thể được `@WebFluxTest` nạp trong phạm vi web slice. Khi `service.findById(...)` trả `Mono.error(ItemNotFoundException)`, exception được WebFlux chuyển theo luồng error signal và có thể được `@ExceptionHandler` ánh xạ thành HTTP 404.

`WebExchangeBindException` thường xuất hiện với lỗi bind/validate `@Valid @RequestBody` trong WebFlux. Những lỗi khác có thể phát sinh từ JSON sai cú pháp (`ServerWebInputException`), validation ở method parameters (tùy Spring version/cấu hình), hoặc codecs. **Không mặc định mọi HTTP 400 đều đi qua handler `WebExchangeBindException`**.

Advice trong ví dụ trả JSON một trường `code`, đủ để kiểm tra một hợp đồng nhỏ. Trong ứng dụng production, error schema có thể còn `message`, field errors, trace ID và Problem Details; chỉ assert những trường API công bố.

### 5.7. Reactive WebFilter thêm response header

Tệp `src/main/java/com/example/webfluxtest/TraceHeaderWebFilter.java`:

```java
package com.example.webfluxtest;

import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Mono;

@Component
public class TraceHeaderWebFilter implements WebFilter {

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        exchange.getResponse().getHeaders()
                .set("X-WebFlux-Filter", "applied");
        return chain.filter(exchange);
    }
}
```

`WebFilter` là interface reactive, khác hoàn toàn với `jakarta.servlet.Filter`. Nó nhận `ServerWebExchange` và `WebFilterChain`, trả `Mono<Void>` cho tác vụ xử lý response.

Trong ví dụ, header được đặt **trước khi** tiếp tục chain. Test dùng `expectHeader()` để chứng minh filter thật sự tham gia request; chỉ kiểm tra `ApplicationContext.getBean(TraceHeaderWebFilter.class)` không đủ chứng minh execution.

Một `WebFilter` có thể trả một error signal, kết thúc response sớm hoặc chặn chain. Trong các test lỗi, cần xem response thực tế để biết request đã tới controller/advice chưa. Với tác vụ logging/tracing, không nên lưu trạng thái per-request trong field mutable singleton của filter; sử dụng thông tin thuộc `ServerWebExchange` hoặc Reactor Context theo yêu cầu.

### 5.8. Test dùng WebTestClient và mock service

Tệp `src/test/java/com/example/webfluxtest/ItemControllerWebFluxTest.java`:

```java
package com.example.webfluxtest;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.core.publisher.Mono;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@WebFluxTest(controllers = ItemController.class)
class ItemControllerWebFluxTest {

    @Autowired
    WebTestClient client;

    @MockitoBean
    ItemService service;

    @Test
    void getUsesJsonCodecAndWebFilter() {
        when(service.findById(41L)).thenReturn(
                Mono.just(new ItemView(41L, "Mouse", 125_000)));

        client.get()
                .uri("/api/items/41")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(
                        "X-WebFlux-Filter", "applied")
                .expectHeader().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON)
                .expectBody()
                .jsonPath("$.id").isEqualTo(41)
                .jsonPath("$.name").isEqualTo("Mouse")
                .jsonPath("$.price").isEqualTo(125_000);

        verify(service).findById(41L);
    }

    @Test
    void converterNormalizesPathSkuBeforeServiceCall() {
        when(service.findBySku("AB-7")).thenReturn(
                Mono.just(new ItemView(7L, "Adapter", 19_000)));

        client.get()
                .uri("/api/items/sku/ab-7")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.id").isEqualTo(7)
                .jsonPath("$.name").isEqualTo("Adapter");

        verify(service).findBySku("AB-7");
    }

    @Test
    void restControllerAdviceMapsDomainErrorTo404() {
        when(service.findById(404L)).thenReturn(
                Mono.error(new ItemNotFoundException("not found")));

        client.get()
                .uri("/api/items/404")
                .exchange()
                .expectStatus().isNotFound()
                .expectBody()
                .jsonPath("$.code").isEqualTo("ITEM_NOT_FOUND");

        verify(service).findById(404L);
    }

    @Test
    void invalidPostBodyReturns400BeforeServiceCall() {
        client.post()
                .uri("/api/items")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new CreateItemRequest("", 0))
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code").isEqualTo("INVALID_ITEM");

        verifyNoInteractions(service);
    }

    @Test
    void validPostDeserializesAndReturns201() {
        when(service.create(any(CreateItemRequest.class)))
                .thenReturn(Mono.just(
                        new ItemView(72L, "Keyboard", 75_000)));

        client.post()
                .uri("/api/items")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(
                        new CreateItemRequest("Keyboard", 75_000))
                .exchange()
                .expectStatus().isCreated()
                .expectBody()
                .jsonPath("$.id").isEqualTo(72)
                .jsonPath("$.name").isEqualTo("Keyboard")
                .jsonPath("$.price").isEqualTo(75_000);

        verify(service).create(
                new CreateItemRequest("Keyboard", 75_000));
    }
}
```

### 5.9. Đọc đúng ý nghĩa của năm ca test

| Test | Hành vi thực được kiểm tra | Chưa chứng minh |
|---|---|---|
| `getUsesJsonCodecAndWebFilter` | Request GET, JSON encoding, content type, header của WebFilter | Service lấy dữ liệu thật, HTTP socket thật |
| `converterNormalizesPathSkuBeforeServiceCall` | `WebFluxConfigurer` đăng ký converter và `Sku` được bind đúng | Truy vấn SKU trong database |
| `restControllerAdviceMapsDomainErrorTo404` | `Mono.error` từ mock qua advice thành HTTP 404/JSON | Exception thực từ repository có cùng loại |
| `invalidPostBodyReturns400BeforeServiceCall` | Body decode, Bean Validation, advice 400, không gọi service | Validation rule trong service/DB thật |
| `validPostDeserializesAndReturns201` | JSON request → record, mock service nhận đúng record, HTTP 201/JSON response | Hóa đơn/bản ghi được commit hoặc event được phát thật |

Với Spring Boot 3.4/3.5, Java 17+, các dependencies được nêu và các component trong package được slice filter giữ lại, **năm test được thiết kế để đạt**. Chúng không in `stdout` riêng; Gradle/Maven hiển thị report tùy runner. Không tuyên bố các test đã chạy trên một dự án cụ thể nếu mới chỉ biên soạn bài.

Điểm mấu chốt là **controller, advice, conversion và filter chạy thật trong WebFlux slice**, còn `ItemService` là mock. `verify(service)...` kiểm tra cách controller gọi dependency, không chứng minh service/repository implementation thật.

### 5.10. Chạy test

Gradle wrapper trên Linux/macOS:

```bash
./gradlew test --tests "com.example.webfluxtest.ItemControllerWebFluxTest"
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests "com.example.webfluxtest.ItemControllerWebFluxTest"
```

Maven wrapper trên Linux/macOS:

```bash
./mvnw -Dtest=ItemControllerWebFluxTest test
```

Windows PowerShell:

```powershell
.\mvnw.cmd -Dtest=ItemControllerWebFluxTest test
```

Cần wrapper và task/plugin JUnit Jupiter tương thích; Gradle thường dùng `useJUnitPlatform()`. Xem report thực sự của module tại `build/reports/tests/test/index.html` (Gradle task `test`) hoặc `target/surefire-reports/` (Maven Surefire). Với project đa module, tên package/class và task có thể khác.

## 6. @ControllerAdvice: lỗi Mono/Flux khác ngoại lệ ném ngay

Trong WebFlux, handler có thể:

- Ném exception trước khi trả publisher, ví dụ lỗi binding hoặc kiểm tra tham số.
- Trả `Mono.error(exception)` và phát error signal khi có subscriber.
- Kết thúc `Mono.empty()` không có giá trị.
- Phát một phần `Flux<T>` rồi lỗi sau khi response đã bắt đầu ghi.

`@RestControllerAdvice` có thể xử lý **lỗi phát sinh trong pipeline phù hợp trước khi HTTP response được commit**, nhưng không bảo đảm có thể thay status/body nếu response headers đã gửi hoặc streaming response đang phát dở.

**Đặc biệt: `Mono.empty()` không tự đồng nghĩa HTTP 404.** Nếu controller trả `Mono<ItemView>` trống, handler có thể hoàn thành với status thành công và body rỗng theo đường đi thực tế. Khi hợp đồng nói không tìm thấy phải là 404, service/controller phải **chuyển vắng mặt thành lỗi hoặc ResponseEntity tương ứng**.

Ví dụ minh họa bên trong handler (không phải tệp độc lập):

```java
return service.findById(id)
        .switchIfEmpty(Mono.error(
                new ItemNotFoundException("Item missing")));
```

Nếu service có thể trả `Mono.empty()`, đoạn trên biến tín hiệu empty thành `Mono.error` để advice 404 xử lý. Tránh dùng `.block()` trong handler chỉ để ném exception theo kiểu đồng bộ.

**Validation cũng có nhiều nhánh:**
- `@Valid @RequestBody CreateItemRequest` với constraint vi phạm thường tạo `WebExchangeBindException`.
- JSON sai cú pháp hoặc kiểu dữ liệu không đọc được thường tạo `ServerWebInputException` hoặc lỗi decode được chuyển đổi.
- Method parameter validation có thể có exception riêng theo version/cấu hình, ví dụ `HandlerMethodValidationException` trong Spring Framework mới.

Nếu API chuẩn hóa mọi lỗi đầu vào thành cùng JSON schema, phải thêm handlers/tests đúng cho các nhánh đó. Ví dụ mục 5 chỉ xử lý **domain not found** và **binding validation**, không tự xử lý mọi lỗi decoding.

## 7. Converter, Formatter và Codec: ba vấn đề không nên nhầm

Trong WebFlux, chuyển đổi giá trị path/query param và chuyển đổi HTTP body **không phải cùng cơ chế**.

| Thành phần | Hướng chuyển đổi | Ví dụ |
|---|---|---|
| `Converter<String,Sku>` | Giá trị Java `String` thành kiểu miền `Sku` | `/sku/ab-7` → `Sku("AB-7")` |
| `Formatter<T>` | Parse/print `String` theo quy tắc format | Ngày tháng, số có định dạng locale |
| `WebFluxConfigurer#addFormatters` | Đăng ký converters/formatters cho binding WebFlux | Gọi `registry.addConverter(...)` |
| `HttpMessageReader` / `Decoder` | HTTP body bytes → object/stream | JSON body → `CreateItemRequest` |
| `HttpMessageWriter` / `Encoder` | Java object/stream → HTTP body bytes | `ItemView` → JSON |
| `CodecCustomizer` / `ServerCodecConfigurer` | Tùy biến lựa chọn và cấu hình codecs | Cấu hình Jackson, max in-memory size, codec custom |

Một `Converter<String,Sku>` **không** đảm bảo Jackson hiểu mọi biến thể JSON của `Sku`. Ngược lại, một `JsonDeserializer<Sku>` sẽ không tự đăng ký thành converter cho path variable.

Khi test `GET /api/items/sku/ab-7` trả JSON thành công, chỉ thế chưa đủ chứng minh `SkuConverter` chạy: có thể service mock được stub quá rộng. Bởi vậy, ví dụ còn `verify(service).findBySku("AB-7")` để kiểm tra **giá trị thực sau conversion**.

Nếu dùng custom `ObjectMapper` hoặc codecs trong production, phải xem chúng có được **nạp vào WebFlux slice** không. Một `@JsonComponent` trong phạm vi scan có thể được nạp; nhưng một `@Configuration` tùy biến nằm ngoài slice không tự được chọn. Khi JSON contract phụ thuộc config đó, dùng `@Import` hoặc test slice được cấu hình rõ, rồi assert JSON. Đừng dựa vào default codec nếu production có custom date formatting, polymorphism hoặc null policy khác.

## 8. WebFilter, HandlerFilterFunction và SecurityWebFilterChain

Ba nhóm dễ nhầm:

1. **`WebFilter`**: reactive web filter áp dụng cho WebFlux `WebHandler` chain trong phạm vi đăng ký.
2. **`HandlerFilterFunction`**: filter trong cơ chế **functional endpoints**, thường được áp vào `RouterFunction`, không đồng nghĩa `WebFilter` toàn web app.
3. **`SecurityWebFilterChain`**: Spring Security reactive chain, thường được chọn/điều phối bởi `WebFilterChainProxy` của Spring Security.

`@WebFluxTest` có thể giữ lại `WebFilter` beans được nhận diện nhưng **không cam kết toàn bộ functional routing hoặc security config của production được tải**. Một `WebFilter` đã có trong context cũng nên được kiểm tra bằng tác dụng trên response/request, không chỉ bằng việc bean tồn tại.

**Những lỗi thường gặp với WebFilter:**
- Quên `return chain.filter(exchange)` khiến request không tới controller.
- Đặt header **sau** khi response đã commit, làm header không xuất hiện.
- Gọi `.subscribe()` thủ công trong filter thay vì trả publisher kết hợp, khiến lỗi và lifecycle khó kiểm soát.
- Dùng mutable fields trong singleton filter để chứa dữ liệu per-request, gây race khi nhiều request song song.
- Chặn event-loop bằng I/O blocking trong filter.
- Nhầm reactive `WebFilter` với Servlet `Filter` và mang đoạn `doFilterInternal` từ MVC sang WebFlux.

Ví dụ ở mục 5 cố ý dùng `exchange.getResponse().getHeaders().set(...)` **trước** `chain.filter(exchange)`, để header tồn tại ngay cả khi handler phát domain error đã được advice xử lý.

## 9. Spring Security trên WebFluxTest: 401/403 và CSRF

Nếu dự án có Spring Security reactive trên classpath với auto-configuration/security beans phù hợp, một request WebTestClient vô danh có thể bị chặn trước controller:

- Endpoint yêu cầu authentication có thể trả `401 Unauthorized` hoặc redirect tùy entry point.
- Endpoint yêu cầu quyền có thể trả `403 Forbidden`.
- POST/PUT/DELETE theo cấu hình CSRF có thể trả `403` khi thiếu CSRF token.
- Một request bị security chặn không đi tới `@Valid` hoặc service, vì vậy `verifyNoInteractions(service)` **không tự chứng minh validation đã chạy**.

Để kiểm tra security thực, dùng các công cụ trong `spring-security-test` tương thích với reactive stack, ví dụ `SecurityMockServerConfigurers.mockUser()` hoặc `csrf()` thông qua `WebTestClient.mutateWith(...)`. Khai báo `@WithMockUser` cũng có thể được dùng trong các test Spring Security phù hợp, nhưng phải kiểm soát context/security config đang được thực thi.

Ví dụ minh họa (test đã có `client`, imports và SecurityWebFilterChain phù hợp):

```java
client.mutateWith(mockUser("editor").roles("EDITOR"))
        .mutateWith(csrf())
        .post()
        .uri("/api/items")
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(new CreateItemRequest("Keyboard", 75_000))
        .exchange()
        .expectStatus().isCreated();
```

Đoạn trên **không phải một test độc lập**: nó chỉ có thể đạt `201` khi chính sách security cho phép user/role đó, CSRF config tương thích và service được stub trả item thành công. Import các post-processors phản ứng từ `org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers` nếu dùng API tương ứng.

**Phân biệt WebFlux với MVC:** `SecurityWebFilterChain` của reactive stack khác Servlet `SecurityFilterChain`; `WebTestClient` không dùng `MockMvcRequestPostProcessors` vốn dành cho MVC. Nếu cần test WebFlux method security (`@PreAuthorize` trên service), nên giữ service implementation thật với method-security infrastructure trong một test riêng; mock service ở web slice không tự chứng minh service method security.

Nếu chỉ kiểm tra JSON/mapping và chủ động vô hiệu hóa security trong một slice test được cấu hình riêng, phải ghi rõ **bằng chứng không bao gồm security** và duy trì security tests độc lập. Không trình bày các test đã bỏ security filters như bằng chứng endpoint được bảo vệ.

## 10. @WebFluxTest và @SpringBootTest + WebTestClient

Hai lựa chọn trông giống nhau ở API assertions nhưng khác phạm vi context.

| Thuộc tính | @WebFluxTest | @SpringBootTest với WebFlux |
|---|---|---|
| Mục tiêu | Annotated controller/web slice | Context ứng dụng rộng hơn, các thành phần thật phù hợp |
| Controller | Được chọn/nạp trong slice | Theo toàn bộ application config |
| Service/repository | Không tự nạp toàn bộ; thường mock service | Có thể nạp implementation thật |
| Advice/converter/WebFilter | Những bean web được chọn theo slice/filter | Theo full application config |
| JSON codecs | Cấu hình phù hợp slice | Theo app/auto-config đang bật |
| WebTestClient | Thường auto-configure | Dùng `@AutoConfigureWebTestClient` khi cần bind-to-context, hoặc client được cấu hình cho real server |
| HTTP TCP server | **Không** khi chỉ là slice | Chỉ có khi `webEnvironment=RANDOM_PORT/DEFINED_PORT` thích hợp |
| Database/transaction/R2DBC | Không tự kiểm tra | Có thể kiểm tra khi datasource/connection factories thật được nạp |
| Chi phí | Thường nhanh, cô lập lỗi | Thường rộng và nặng hơn |
| Bằng chứng | Contract của web handler trong slice | Tích hợp giữa các tầng **thực sự đã tham gia** |

Ví dụ full integration test chạy HTTP thật:

```java
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class RealHttpWebFluxTest {
    @Autowired
    WebTestClient client;
}
```

Đây là **mẫu ngắn**, cần thêm application config, imports và test methods. Với `RANDOM_PORT`, client tương ứng được Boot auto-configure khi dependencies phù hợp, và gọi qua cổng HTTP của server. Còn `@WebFluxTest` thường dùng `WebTestClient` bind vào context **không đi qua một HTTP listener thật**.

Để test WebFlux với context rộng nhưng không khởi động server, dùng `@SpringBootTest(webEnvironment = MOCK)` cùng `@AutoConfigureWebTestClient` khi phù hợp với WebFlux application type. Việc chọn `MOCK` chỉ định mô phỏng web environment, không cam kết một số bean custom được nạp nếu configuration chưa đúng.

**Không ép `@WebFluxTest` thành full integration test** bằng hàng chục `@Import` service/repository/DB chỉ để loại thiếu bean; nếu mục tiêu là controller → R2DBC repository → database, hãy chuyển sang integration test với Testcontainers hoặc setup tương ứng.

## 11. WebFlux functional endpoints: RouterFunction không tương đương @Controller

WebFlux có hai phong cách endpoint:

- **Annotated controllers**: `@RestController`, `@GetMapping`, `@PostMapping`. Đây là trọng tâm của `@WebFluxTest(controllers=...)`.
- **Functional routing**: `RouterFunction<ServerResponse>`, `HandlerFunction<ServerResponse>`, `RouterFunctions.route(...)`.

`@WebFluxTest` không phải cam kết tự nạp tất cả `RouterFunction` và handler functional của ứng dụng. Một test chỉ chọn `ItemController.class` cũng không chứng minh route functional `GET /router/items` đã tồn tại. Với functional endpoints, có thể:

1. Tạo `RouterFunction` và test bằng `WebTestClient.bindToRouterFunction(router).build()` khi chỉ cần mapping/filter chức năng.
2. Dùng context test với `RouterFunction` được đăng ký tường minh.
3. Dùng `@SpringBootTest` nếu cần chứng minh cấu hình functional routing cùng những bean/phụ thuộc thật.

Tương tự, `HandlerFilterFunction` áp dụng cho router được tạo, trong khi `WebFilter` áp dụng ở WebFlux web handler chain. Không coi một test annotated-controller thành bằng chứng cho functional route config.

## 12. Reactive Streams: các đặc trưng khi kiểm tra Mono và Flux

`WebTestClient` thường khởi phát/subscribe tới publisher của controller để hoàn thành HTTP exchange. Việc service mock trả `Mono` hoặc `Flux` phù hợp là thiết yếu: một Mockito mock reactive method **không được stub** có thể trả `null` (tùy cấu hình default answers), dẫn đến lỗi handler không thuộc hợp đồng API.

Khi stubbing:
- `Mono.just(value)`: một kết quả.
- `Mono.error(exception)`: error signal cần advice/error handler xử lý.
- `Mono.empty()`: hoàn thành không có value; **không tự suy ra 404**.
- `Flux.just(a, b)`: hai phần tử theo thứ tự emission.
- `Flux.error(exception)`: lỗi trong stream; nếu response đã bắt đầu ghi, không thể luôn thay status/body như một lỗi trước khi ghi.

Nếu endpoint trả JSON array từ `Flux<ItemView>`, hãy assert cả số phần tử, nội dung và thứ tự nếu hợp đồng bảo đảm thứ tự. Với server-sent events hoặc streaming `application/x-ndjson`, WebTestClient có thể dùng `returnResult(...)` rồi `StepVerifier` để kiểm soát event stream; nhớ timeout/hủy subscription thích hợp để test không treo.

Một ví dụ minh họa khi đã có `Flux<ItemView>` được serialize thành JSON array và `WebTestClient` phù hợp:

```java
client.get()
        .uri("/api/items")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$[0].id").isEqualTo(1)
        .jsonPath("$[1].id").isEqualTo(2);
```

Đoạn trên **không thuộc chương trình mẫu**, vì `ItemController` ở mục 5 chưa khai báo route `GET /api/items`. Đây chỉ là mẫu assertion khi endpoint đó thật sự tồn tại, không phải lời khẳng định test hoàn chỉnh.

Không đặt `Thread.sleep` cố định để đợi một reactive pipeline không được subscribe hoặc một background task đang xử lý. Khi cần test time-based operators ở tầng service, có thể dùng `StepVerifier.withVirtualTime` nếu code và scheduler tương thích; controller HTTP contract vẫn nên kiểm tra bằng WebTestClient.

## 13. Test slice đúng không có nghĩa production web stack hoàn toàn giống

WebFlux slice và production có thể khác nhau do:

- Một `@Configuration` ngoài web-related types không được nạp.
- Jackson `ObjectMapper` hoặc codec customizers của production thiếu trong slice.
- Global `WebFilter` có dependency ngoài slice, cần fake/mock đúng.
- Security configuration hoặc reactive authentication manager không được đưa vào giống production.
- Controller gọi client/repository reactive thật trong production nhưng mock trong slice.
- Quá trình startup chỉ xảy ra trong full application context.
- Production có reverse proxy/gateway, CORS, rate limiting, TLS hoặc network behavior mà WebTestClient bind-to-context không kiểm tra.

Vì vậy, bộ test chất lượng thường kết hợp:
- Unit test cho logic thuần Java/reactive service.
- `@WebFluxTest` cho HTTP contract của controller, advice, converters, codecs và WebFilters.
- Test repository với database thích hợp (R2DBC/JPA theo kiến trúc).
- `@SpringBootTest`/real HTTP integration cho đường request qua các tầng quan trọng và những configuration ngoài slice.

**Lưu ý về blocking:** WebFlux không biến một thao tác JDBC/blocking I/O thành nonblocking chỉ vì controller trả `Mono`. Nếu service thật gọi JDBC hoặc `.block()` trên event-loop, đây là rủi ro performance/concurrency cần test và thiết kế phù hợp; một `@WebFluxTest` với mock service không phát hiện vấn đề blocking ở service production.

## 14. Những lỗi thường gặp khi @WebFluxTest không hoạt động như mong đợi

| Dấu hiệu | Nguyên nhân có thể | Cách chẩn đoán |
|---|---|---|
| `Failed to load ApplicationContext` vì thiếu service | Service/repository bị slice filter loại | Thêm `@MockitoBean` hoặc fake bean đúng type/name |
| GET trả 404 | Controller chưa được chọn, URI sai hoặc mapping không đăng ký | Kiểm tra `controllers=...`, `@GetMapping` và URL thực |
| GET/POST trả 401, 403 | Reactive security filter/CSRF chặn | Kiểm tra `SecurityWebFilterChain`, authentication, CSRF config |
| `@MockitoBean` không tồn tại trong dependency | Dự án Boot/Spring Framework cũ | Dùng API mock bean tương thích version |
| Handler ném NullPointerException từ `Mono` | Mock reactive method không stub nên trả null | Trả `Mono.just`, `Mono.empty` hoặc `Mono.error` đúng hợp đồng |
| Domain error bị trả 500 thay vì 404 | Advice không được nạp, handler exception không khớp | Xác nhận `@RestControllerAdvice` và error signal |
| Invalid JSON trả 400 nhưng error schema khác | JSON decode error khác `WebExchangeBindException` | Tách test malformed JSON và validation failure |
| `@Valid` không chặn request lỗi | Thiếu `@Valid`, provider hoặc constraint | Kiểm tra starter-validation và DTO annotations |
| SKU converter không chạy | `WebFluxConfigurer` chưa đăng ký, mapping sai | `verify(service).findBySku("AB-7")`, import config khi cần |
| JSON fields/content type khác | Codec/Jackson config khác production hoặc DTO serialization sai | Assert JSON và kiểm tra codecs thực sự được nạp |
| Header từ WebFilter không có | WebFilter không đăng ký, chain bị chặn hoặc response commit sớm | Test header và inspect filter registrations |
| Slice vô tình kéo database/external service | Broad import/scan/custom configuration | Giảm import, mock đúng dependency ngoài web |
| Test xanh dù service logic lỗi | Controller dùng mock service và stub cố định | Bổ sung unit/integration test cho service thật |
| HTTP streaming fail sau một số phần tử | Lỗi phát sau response commit, không thể sửa status | Test reactive signal, error handling/streaming contract |
| Test chỉ xanh khi chạy riêng | Shared static state, context cache, mock setup hoặc security context | Tách fixture và quản lý context/test isolation |

Phân tích lỗi theo **giai đoạn**: test context startup → handler mapping → argument binding/codec → validation → controller → reactive signal → advice/filter → response. Một lỗi khởi tạo context thường xuất hiện **trước khi code test gọi WebTestClient**, trong khi một assertion JSON sai xảy ra khi request đã được xử lý.

## 15. Checklist khi review WebFlux slice test

- [ ] Đã xác định ứng dụng đang dùng Spring WebFlux reactive, không nhầm với Spring MVC khi classpath có cả hai starters.
- [ ] `@WebFluxTest(controllers=...)` chọn đúng annotated controller và test không vô tình nạp business/persistence layer ngoài ý định.
- [ ] Controller thật, service/gateway mock hoặc fake với bean override hợp phiên bản; reactive methods được stub trả publisher hợp lệ.
- [ ] Đã xác minh WebTestClient đang bind vào WebFlux context của slice, không diễn giải thành HTTP server thật.
- [ ] Đã test đúng path, HTTP method, query/path binding, status, headers, JSON body và content type.
- [ ] Khi dùng `Converter`/`WebFluxConfigurer`, đã xác minh giá trị chuyển đổi thực sự tới controller/service.
- [ ] Khi dùng custom Jackson codecs, đã kiểm tra config tương ứng có mặt trong slice.
- [ ] `@RestControllerAdvice` được nạp, handle domain exception và validation đúng schema; không nhầm `Mono.empty()` với HTTP 404.
- [ ] `WebFilter` thực sự được thực thi; phân biệt nó với Servlet Filter và SecurityWebFilterChain.
- [ ] Nếu Security có mặt, đã kiểm tra authentication, authority và CSRF phù hợp, không tự bypass filters trong security test.
- [ ] Với `Flux`/streaming, đã test nội dung, ordering nếu cần, lỗi/timeout và lifecycle của subscription.
- [ ] Không dùng kết quả mock service làm bằng chứng JPA/R2DBC, transaction, broker hoặc full application context.
- [ ] Đã chạy đúng test và xem report Gradle/Maven/CI trước khi tuyên bố đạt trên dự án.

**Kết luận:** `@WebFluxTest` là công cụ hiệu quả để kiểm tra **annotated controller cùng hạ tầng WebFlux được chọn**: `@RestControllerAdvice`, converters/formatters, reactive JSON codecs, `WebFilter`, validation và xử lý `Mono`/`Flux`. Dùng `WebTestClient` để assert HTTP contract, giữ controller thật và giả lập service ngoài slice. Vì context này có chủ đích **không phải toàn bộ Spring Boot app**, mọi kết luận về database, transaction, gateway thật hoặc security/configuration bị loại phải được chứng minh bằng những test bổ sung có phạm vi phù hợp.
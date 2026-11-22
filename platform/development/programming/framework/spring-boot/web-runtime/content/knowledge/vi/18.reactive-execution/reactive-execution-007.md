# Xử lý lỗi có chọn lọc với `onErrorResume` trong Spring WebFlux

## Mục tiêu

Sau bài này, bạn có thể dùng `onErrorResume` để phục hồi một lỗi **đã dự kiến và có phương án thay thế hợp lệ**, đồng thời bảo toàn các lỗi lập trình, lỗi dữ liệu, lỗi phân quyền và lỗi hệ thống chưa được phép xử lý. Nội dung đặt trong bối cảnh **Spring Boot WebFlux, Project Reactor, `Mono` và `Flux`**.

Nguyên tắc quan trọng nhất:

> **Chỉ fallback cho đúng loại lỗi được nghiệp vụ cho phép. Những lỗi khác phải tiếp tục đi theo kênh lỗi, được chuyển thành HTTP status phù hợp và được quan sát.**

`onErrorResume` không phải một câu lệnh “bắt mọi lỗi cho ứng dụng không bị hỏng”. Nếu dùng quá rộng, nó có thể biến lỗi 500, mất quyền truy cập hoặc dữ liệu sai thành HTTP 200 giả tạo, khiến giám sát và người dùng hiểu nhầm là tác vụ thành công.

## 1. Cơ chế lỗi của Reactor: tín hiệu `onError` là điểm kết thúc

Một `Publisher` Reactive Streams gửi các sự kiện theo thứ tự:

- `onNext(value)`: phát một giá trị (nếu có).
- `onComplete()`: kết thúc thành công.
- `onError(error)`: kết thúc vì lỗi.

Một chuỗi chỉ có thể kết thúc bằng **một trong hai** `onComplete` hoặc `onError`. Khi nguồn đã phát `onError`, nó **không tiếp tục phát thêm phần tử**. Operator `onErrorResume` chặn tín hiệu lỗi tương ứng ở phía upstream, rồi **đăng ký và chuyển sang một publisher fallback mới**. Nó không khởi động lại phần còn lại của nguồn đã hỏng.

```text
Nguồn Mono/Flux --- onNext ... --- onError(ExpectedException) --- X
                                               |
                                      onErrorResume(chỉ lỗi này)
                                               |
                                      Publisher fallback mới
                                               |
                                       onNext -> onComplete
```

Nếu loại lỗi không khớp điều kiện `onErrorResume`, tín hiệu lỗi đi tiếp xuống subscriber. Nếu chính publisher fallback bị lỗi, lỗi **của fallback** cũng đi tiếp, trừ khi có cơ chế xử lý riêng tiếp theo.

Với `Mono<T>`, sau xử lý thường có một giá trị, hoàn thành rỗng hoặc lỗi. Với `Flux<T>`, đã phát một số phần tử trước lỗi thì các phần tử ấy không bị “rút lại”; phần chưa phát của nguồn gốc không tự động được xử lý tiếp. Đây là điểm đặc biệt quan trọng khi xây dựng API trả về stream hoặc cập nhật dữ liệu nhiều bản ghi.

## 2. Vì sao `onErrorResume(error -> default)` thường nguy hiểm?

Ví dụ **không nên dùng** ở cuối toàn bộ pipeline nghiệp vụ:

```java
return fetchProduct(id)
    .map(this::calculatePrice)
    .onErrorResume(error -> Mono.just(ProductView.empty()));
```

Đây chỉ là đoạn minh họa: `fetchProduct`, `calculatePrice` và `ProductView` là các thành phần do ứng dụng định nghĩa. Cách viết này phục hồi cả các trường hợp không nên bị che, ví dụ:

- Timeout tạm thời từ upstream có thể chấp nhận dùng cache (nếu hợp đồng API cho phép).
- `IllegalArgumentException` do dữ liệu đầu vào sai, đáng ra phải báo 400.
- `NullPointerException` hoặc `IllegalStateException` do bug trong `calculatePrice`, đáng ra phải được phát hiện và sửa.
- Lỗi phân quyền, không nên chuyển thành dữ liệu mặc định như thể truy cập được cho phép.
- Lỗi giải mã JSON, schema bị đổi hoặc dữ liệu không nhất quán, cần được quan sát.

Tương tự, `onErrorResume(error -> Mono.empty())` **nuốt lỗi thành hoàn thành rỗng**, không tự động đồng nghĩa “404 Not Found”. WebFlux có thể tạo response rỗng với status khác 404 tùy handler; ý nghĩa lỗi ban đầu biến mất.

**Sửa theo hướng an toàn**: đặt operator sát ranh giới dịch vụ dễ hỏng và giới hạn bằng exception class hoặc predicate, ưu tiên tên exception gắn với nguyên nhân có thể phục hồi:

```java
return fetchProduct(id)
    .onErrorResume(
        CatalogTemporarilyUnavailableException.class,
        original -> readCache(id)
            .switchIfEmpty(Mono.error(original))
    )
    .map(this::calculatePrice);
```

Đây cũng là **đoạn minh họa**; các method, type cần được định nghĩa trong dự án. Ở đây:

1. Chỉ `CatalogTemporarilyUnavailableException` (và subtype của nó) được phép thử cache.
2. Nếu cache trống, lỗi gốc được phát lại bằng `Mono.error(original)`.
3. `calculatePrice` đặt **sau** `onErrorResume`, vì vậy bug trong phép tính không bị operator fallback ấy che.
4. Nếu cache bị lỗi, lỗi mới vẫn lan xuống, thay vì bị chuyển thành một giá trị thành công giả.

Nếu lỗi cần xử lý dựa trên điều kiện cụ thể thay vì lớp exception, dùng overload có predicate:

```java
.onErrorResume(
    error -> error instanceof WebClientResponseException ex
        && ex.getStatusCode().value() == 503,
    error -> loadStaleCache()
)
```

Chỉ dùng fallback với HTTP 503 nếu dữ liệu dự phòng được phép đáp ứng request; `401`, `403`, `404`, lỗi mapping và các `5xx` khác không nên tự động bị đánh đồng với 503.

## 3. Ba dạng `onErrorResume` cần biết

| Dạng | Ý nghĩa | Khi dùng |
| --- | --- | --- |
| `onErrorResume(error -> fallback(error))` | Function nhận **bất kỳ lỗi upstream** nào | Chỉ an toàn khi bên trong có phân nhánh rõ và phát lại lỗi còn lại |
| `onErrorResume(SomeException.class, ex -> fallback(ex))` | Chỉ khớp exception class đó và các subtype | Ưu tiên cho một lỗi nghiệp vụ/công nghệ đã định nghĩa rõ |
| `onErrorResume(predicate, ex -> fallback(ex))` | Chỉ khớp lỗi thỏa điều kiện | Khi cần xét HTTP status, metadata hoặc nguyên nhân có khả năng phục hồi |

Nếu bắt buộc xử lý nhiều loại lỗi trong một function, hãy **phát lại lỗi không phù hợp**:

```java
.onErrorResume(error -> {
    if (error instanceof CatalogTemporarilyUnavailableException) {
        return readCache(id);
    }
    if (error instanceof java.util.concurrent.TimeoutException) {
        return readCache(id);
    }
    return Mono.error(error); // bảo toàn mọi lỗi ngoài danh sách cho phép
})
```

Đoạn này cần đặt đúng vị trí trên pipeline và `readCache` phải có chính sách rõ cho cache miss; nếu cache miss phải bảo toàn lỗi thì dùng `switchIfEmpty(Mono.error(error))`. Đừng tự thêm mọi `RuntimeException`, `Exception` hay `Throwable` vào danh sách lỗi “có thể bỏ qua”.

**Phạm vi quan trọng:** `onErrorResume` bắt lỗi phát ra từ upstream của vị trí đặt operator, gồm cả lỗi do callback `map`/`flatMap` ở phía trước ném ra. Chọn đúng type **và** đúng vị trí để không vô tình bắt lỗi lập trình khác cùng loại. Nếu cần phân loại lỗi mạng ở lớp tích hợp, nên chuẩn hóa thành exception riêng tại chính lớp đó.

## 4. Ví dụ hoàn chỉnh: Spring Boot WebFlux phục hồi lỗi kết nối catalogue bằng cache

Ví dụ có **năm nhánh**: đọc thành công, nguồn catalog tạm ngừng nhưng có cache, nguồn tạm ngừng và cache trống, đầu vào lỗi, lỗi lập trình. Nhánh trả 404 cũng được giữ riêng.

Tạo một dự án từ Spring Initializr với:

- **Java 17+**, Spring Boot **3.x** có hỗ trợ WebFlux, dependency **Spring Reactive Web** (`spring-boot-starter-webflux`).
- Nếu kiểm thử theo phần 5, thêm **Spring Boot Starter Test** và `io.projectreactor:reactor-test` (scope `test`).
- Với ví dụ này, không thêm `spring-boot-starter-web` để tránh Spring MVC được chọn mặc định khi cả hai web starter cùng xuất hiện.

Tạo file duy nhất `src/main/java/com/example/demo/SafeFallbackApplication.java`:

```java
package com.example.demo;

import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Mono;

@SpringBootApplication
@RestController
public class SafeFallbackApplication {

    // Chỉ một mã có dữ liệu cache hợp lệ để dùng khi catalog tạm lỗi.
    private final Map<String, Book> cache = Map.of(
        "offline", new Book("offline", "Sách lấy từ cache", true)
    );

    public static void main(String[] args) {
        SpringApplication.run(SafeFallbackApplication.class, args);
    }

    @GetMapping("/books/{id}")
    public Mono<Book> getBook(@PathVariable String id) {
        return queryCatalog(id)
            // Chỉ phục hồi khi catalog tạm không sẵn sàng.
            .onErrorResume(
                CatalogUnavailableException.class,
                original -> readCache(id)
                    .switchIfEmpty(Mono.error(original))
            )
            // Nếu cả nguồn chính và cache không đáp ứng, trả 503.
            .onErrorMap(
                CatalogUnavailableException.class,
                original -> new ResponseStatusException(
                    HttpStatus.SERVICE_UNAVAILABLE,
                    "Catalog temporarily unavailable",
                    original
                )
            )
            // Lỗi đầu vào vẫn là 400, không được biến thành giá trị giả.
            .onErrorMap(
                InvalidBookIdException.class,
                original -> new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    original.getMessage(),
                    original
                )
            );
    }

    private Mono<Book> queryCatalog(String id) {
        return Mono.defer(() -> {
            switch (id) {
                case "ok":
                    return Mono.just(
                        new Book("ok", "Reactive Java", false)
                    );
                case "offline":
                case "offline-no-cache":
                    return Mono.error(
                        new CatalogUnavailableException(
                            "Catalog is temporarily offline"
                        )
                    );
                case "bad":
                    return Mono.error(
                        new InvalidBookIdException("Invalid book id")
                    );
                case "bug":
                    return Mono.error(
                        new IllegalStateException("Unexpected mapping bug")
                    );
                default:
                    return Mono.error(
                        new ResponseStatusException(
                            HttpStatus.NOT_FOUND, "Book not found"
                        )
                    );
            }
        });
    }

    private Mono<Book> readCache(String id) {
        return Mono.defer(() -> Mono.justOrEmpty(cache.get(id)));
    }

    public record Book(String id, String title, boolean stale) {}

    static final class CatalogUnavailableException
            extends RuntimeException {
        CatalogUnavailableException(String message) {
            super(message);
        }
    }

    static final class InvalidBookIdException
            extends RuntimeException {
        InvalidBookIdException(String message) {
            super(message);
        }
    }
}
```

Mô hình trên dùng `Mono.defer` để tạo tín hiệu lỗi/giá trị khi có subscription, không tạo công việc ngoại vi trước lúc subscriber đến. `readCache` là map trong bộ nhớ để ví dụ tự chạy, **không phải cache production**, không có TTL hay cơ chế cập nhật. Các request trên WebFlux được phục vụ theo pipeline reactive; không gọi `block()` trong controller.

Chạy bằng Maven wrapper của dự án:

```bash
./mvnw spring-boot:run
```

Trên Windows, dùng `mvnw.cmd spring-boot:run`. Mở terminal khác và gọi lần lượt (Windows PowerShell có thể cần `curl.exe`):

```bash
curl -i http://localhost:8080/books/ok
curl -i http://localhost:8080/books/offline
curl -i http://localhost:8080/books/offline-no-cache
curl -i http://localhost:8080/books/bad
curl -i http://localhost:8080/books/bug
curl -i http://localhost:8080/books/missing
```

| Request | Kết quả dự kiến | Giải thích |
| --- | --- | --- |
| `GET /books/ok` | HTTP **200**, JSON có `"id":"ok"`, `"title":"Reactive Java"`, `"stale":false` | Nguồn chính thành công; không chạy fallback |
| `GET /books/offline` | HTTP **200**, JSON có `"id":"offline"`, `"title":"Sách lấy từ cache"`, `"stale":true` | Chỉ lỗi catalog tạm thời được phục hồi bằng dữ liệu có sẵn |
| `GET /books/offline-no-cache` | HTTP **503** | Cache trống -> phát lại exception gốc -> `onErrorMap` chuyển thành 503 |
| `GET /books/bad` | HTTP **400** | Lỗi input đi qua `onErrorResume` và được ánh xạ thành 400 |
| `GET /books/bug` | HTTP **500** | `IllegalStateException` không được che; WebFlux xử lý lỗi server |
| `GET /books/missing` | HTTP **404** | `ResponseStatusException` đi qua nguyên trạng |

Các header, timestamp, trường JSON của **error body** và nội dung log phụ thuộc Spring Boot/WebFlux và cấu hình trả lỗi. Không coi body lỗi là stdout cố định; điều đáng kiểm chứng là **HTTP status**, lỗi nào được phép phục hồi và trường `stale` trong response thành công.

**Tại sao cách này không che lỗi ngoài ý muốn?** `onErrorResume` nhận duy nhất `CatalogUnavailableException`. Nếu cache không có giá trị, `Mono.error(original)` trả lại chính exception ban đầu; lúc ấy `onErrorMap` chuyển nó sang HTTP 503 mà vẫn bảo toàn cause. Những loại lỗi khác không hề được thay bằng `Book`; lỗi đầu vào được trả 400, lỗi lập trình được để lộ cho luồng xử lý lỗi 500 và hệ thống giám sát.

## 5. Kiểm thử cả nhánh thành công lẫn lỗi không được nuốt

Có thể kiểm thử **trực tiếp pipeline** bằng `StepVerifier` mà không cần khởi chạy HTTP server. Với Maven, bảo đảm dự án có JUnit Jupiter từ `spring-boot-starter-test` và dependency này trong `pom.xml`, bên trong `<dependencies>`:

```xml
<dependency>
    <groupId>io.projectreactor</groupId>
    <artifactId>reactor-test</artifactId>
    <scope>test</scope>
</dependency>
```

Tạo file `src/test/java/com/example/demo/SafeFallbackApplicationTest.java`:

```java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.web.server.ResponseStatusException;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;

class SafeFallbackApplicationTest {

    private final SafeFallbackApplication app =
        new SafeFallbackApplication();

    @Test
    void happyPathDoesNotUseCache() {
        StepVerifier.create(app.getBook("ok"))
            .expectNext(new SafeFallbackApplication.Book(
                "ok", "Reactive Java", false
            ))
            .verifyComplete();
    }

    @Test
    void knownOutageCanUseExistingCache() {
        StepVerifier.create(app.getBook("offline"))
            .expectNext(new SafeFallbackApplication.Book(
                "offline", "Sách lấy từ cache", true
            ))
            .verifyComplete();
    }

    @Test
    void cacheMissPreservesFailureAs503() {
        StepVerifier.create(app.getBook("offline-no-cache"))
            .expectErrorSatisfies(error -> {
                ResponseStatusException responseError =
                    assertInstanceOf(ResponseStatusException.class, error);
                assertEquals(503, responseError.getStatusCode().value());
                assertInstanceOf(
                    SafeFallbackApplication.CatalogUnavailableException.class,
                    responseError.getCause()
                );
            })
            .verify();
    }

    @Test
    void invalidInputIsNotHidden() {
        StepVerifier.create(app.getBook("bad"))
            .expectErrorSatisfies(error -> {
                ResponseStatusException responseError =
                    assertInstanceOf(ResponseStatusException.class, error);
                assertEquals(400, responseError.getStatusCode().value());
            })
            .verify();
    }

    @Test
    void programmingErrorIsNotHidden() {
        StepVerifier.create(app.getBook("bug"))
            .expectError(IllegalStateException.class)
            .verify();
    }

    @Test
    void missingBookRemains404() {
        StepVerifier.create(app.getBook("missing"))
            .expectErrorSatisfies(error -> {
                ResponseStatusException responseError =
                    assertInstanceOf(ResponseStatusException.class, error);
                assertEquals(404, responseError.getStatusCode().value());
            })
            .verify();
    }
}
```

Chạy:

```bash
./mvnw test
```

Nếu mã và dependencies đúng như mô tả, **sáu test đều pass**; đây là kết quả kỳ vọng để bạn tự xác minh bằng lệnh, không phải kết quả đã chạy trong một dự án cụ thể. `StepVerifier` chỉ được dùng trong kiểm thử, không thay thế cơ chế subscribe của WebFlux khi phục vụ HTTP.

Nên bổ sung WebTestClient integration tests nếu cần xác nhận response HTTP 200/400/404/500/503 thực tế, JSON, header và mapping exception ở web server.

## 6. Vị trí đặt operator ảnh hưởng loại lỗi bị bắt

Xem hai pipeline minh họa:

```java
// A: fallback bao trùm cả lỗi do chuyển đổi dữ liệu.
fetchDto()
    .map(this::convertDto)
    .onErrorResume(CatalogUnavailableException.class, ex -> cachedResult());

// B: fallback chỉ áp dụng vào phạm vi gọi nguồn dữ liệu.
fetchDto()
    .onErrorResume(CatalogUnavailableException.class, ex -> cachedDto())
    .map(this::convertDto);
```

Các method/type ở đây là giả định, không phải mã biên dịch độc lập. Nếu `convertDto` phát ra lỗi thuộc loại khớp fallback (ví dụ vô tình dùng lại `CatalogUnavailableException`), pipeline A cũng bắt lỗi đó; pipeline B **không**. Với lỗi lập trình thuần `NullPointerException`, cả hai đều truyền lỗi nếu fallback chỉ khớp `CatalogUnavailableException`, nhưng B đặt ranh giới chính xác hơn.

Các nguyên tắc đặt vị trí:

1. **Ở gần boundary** gọi network/database/service có thể phục hồi; không đặt `onErrorResume` rộng ở cuối cả pipeline.
2. **Trước phép biến đổi nhạy cảm** (parse, validate, mapping nghiệp vụ) nếu muốn lỗi từ các phép biến đổi ấy luôn nổi lên.
3. Với lỗi cần chuyển đổi type, dùng `onErrorMap` có chọn lọc và **giữ cause**. Không biến mọi exception thành một lỗi phổ quát khiến hệ thống mất khả năng phân biệt.
4. Một pipeline có thể có nhiều `onErrorResume` được chia theo từng boundary; mỗi nơi cần sở hữu rõ chính sách fallback của mình.

`onErrorResume` nhận exception dưới dạng tín hiệu reactive; nó không tự “bắt” lỗi ngoài subscription như lỗi xảy ra lúc tạo object trước khi dựng publisher. Dùng `Mono.defer` / `Mono.fromCallable` cho công việc có thể ném lỗi cần trì hoãn; với I/O blocking phải cân nhắc scheduler phù hợp như `Schedulers.boundedElastic()`. Không bọc I/O blocking vào `Mono.just(blockingCall())` vì lời gọi chạy ngay khi tạo publisher.

## 7. `Flux`: đặt fallback theo từng phần tử để không làm rơi cả dòng

Sai lầm thường gặp với nhiều key:

```java
Flux.fromIterable(ids)
    .flatMap(this::fetchOne)
    .onErrorResume(CatalogUnavailableException.class,
        error -> Flux.empty());
```

Ở đây `fetchOne` trả về `Mono<Item>` (mã minh họa). Một lỗi có thể kết thúc **cả chuỗi Flux**, làm rớt các key chưa hoàn tất; `Flux.empty()` thay lỗi bằng hoàn thành rỗng nhưng không tiếp tục xử lý nguồn ban đầu.

Nếu mỗi key có thể phục hồi độc lập, đặt fallback **bên trong `flatMap`**:

```java
Flux.fromIterable(ids)
    .flatMap(id ->
        fetchOne(id)
            .onErrorResume(
                CatalogUnavailableException.class,
                original -> readOneFromCache(id)
                    .switchIfEmpty(Mono.error(original))
            )
    );
```

Lúc đó mỗi phần tử được xử lý theo chính sách riêng. Tuy nhiên, nếu **một phần tử vẫn phát lỗi không được phục hồi**, `flatMap` mặc định có thể làm chuỗi kết thúc và hủy các tác vụ còn lại. Nếu yêu cầu nghiệp vụ là “tổng hợp kết quả độc lập của mọi key kể cả khi vài key lỗi”, hãy thiết kế **kiểu kết quả tường minh** như `Success/Failure` theo từng item và xác định loại lỗi được chuyển thành dữ liệu; đừng âm thầm nuốt lỗi bằng `onErrorResume(ex -> Mono.empty())`.

Với streaming HTTP đã gửi một phần response, lỗi ở giữa stream có thể xảy ra **sau khi response đã commit status/headers**; lúc đó không thể bảo đảm đổi toàn bộ HTTP status thành 500 như với `Mono` chưa phát dữ liệu.

## 8. Trong WebClient: lỗi HTTP, lỗi kết nối và lỗi giải mã khác nhau

`WebClient.retrieve().bodyToMono(Dto.class)` mặc định tạo `WebClientResponseException` với HTTP response **4xx/5xx**. Lỗi không nhận được HTTP response do vấn đề kết nối/transport thường là `WebClientRequestException`; lỗi parse/decode body lại thuộc nhóm exception khác. Chính sách fallback nên **phân loại theo nguồn và loại lỗi**.

Ví dụ khi nghiệp vụ chấp nhận cache chỉ với upstream trả **503 Service Unavailable**:

```java
return webClient.get()
    .uri("/catalog/{id}", id)
    .retrieve()
    .bodyToMono(BookDto.class)
    .onErrorResume(
        WebClientResponseException.ServiceUnavailable.class,
        original -> readCachedDto(id)
            .switchIfEmpty(Mono.error(original))
    )
    .map(this::toBook);
```

Đây là snippet tích hợp vào service có `webClient`, `BookDto`, `readCachedDto` và `toBook` được định nghĩa sẵn; nó không độc lập chạy. Với cách đặt này, lỗi giải mã response và bug ở `toBook` không bị thay bằng cache. HTTP **401/403/404** từ service khác cũng không bị coi là 503. Nếu mạng mất kết nối là một trường hợp được phép phục hồi, có thể thêm nhánh `onErrorResume(WebClientRequestException.class, ...)` sau khi cân nhắc mức độ tin cậy và cache; đừng bắt mọi `WebClientException` không phân biệt.

Có thể dùng `retrieve().onStatus(...)` để **chuyển HTTP status thành domain exception** tại boundary WebClient rồi `onErrorResume` chỉ domain exception đó. Đây là cách giúp controller không lệ thuộc quá chặt vào exception cụ thể của HTTP client.

Chú ý khi phối hợp `retryWhen`:

- `retryWhen` **đứng trước** `onErrorResume` nếu muốn thử lại các lỗi tạm thời rồi mới dùng fallback.
- Áp dụng `filter` để chỉ retry lỗi transient thực sự; dùng giới hạn lần thử, backoff, timeout và giám sát.
- Không retry vô hạn, không tự động retry thao tác ghi/POST có tác dụng phụ nếu không bảo đảm idempotency.
- Lỗi phân quyền, dữ liệu không hợp lệ, bug và schema mismatch không được retry hoặc fallback bừa bãi.

## 9. Phân biệt các operator xử lý lỗi và empty

| Operator | Tác dụng | Có thể che lỗi nếu dùng sai? |
| --- | --- | --- |
| `onErrorResume` | Thay lỗi đủ điều kiện bằng một publisher khác | **Có**, nếu predicate quá rộng hoặc fallback trả thành công giả |
| `onErrorReturn` | Thay lỗi bằng một giá trị cố định; có overload filter | Có; ít linh hoạt để kiểm tra cache miss |
| `onErrorComplete` | Biến lỗi thành hoàn thành bình thường | Có; dễ làm mất thông tin sự cố |
| `onErrorMap` | Chuyển đổi exception thành exception khác | Có, nếu gom mọi lỗi thành một type và làm mất cause |
| `doOnError` | Side effect như log/metrics; **không phục hồi lỗi** | Không đổi tín hiệu lỗi, nhưng có thể log trùng nếu đặt nhiều tầng |
| `switchIfEmpty` | Chuyển sang publisher khác khi nguồn **hoàn thành rỗng** | Không phải operator bắt lỗi; không xử lý `onError` |
| `onErrorContinue` | Cho phép một số operator tương thích bỏ phần tử lỗi và tiếp tục | Dễ gây hành vi khó lường; không phải thay thế tổng quát cho fallback có chủ đích |

`switchIfEmpty` áp dụng cho một nghiệp vụ “không tìm thấy dữ liệu” biểu diễn bằng `Mono.empty()`; còn 404 phải được **ánh xạ tường minh** nếu API yêu cầu 404. Ngược lại, lỗi thật cần được biểu diễn bằng tín hiệu `onError` và chỉ phục hồi khi có chính sách rõ.

Đừng dùng `onErrorContinue` như “cứ gặp lỗi là bỏ qua dòng đó” ở cuối pipeline phức tạp: operator này có hỗ trợ giới hạn tùy nguồn, có thể ảnh hưởng ngược tới upstream và khiến mất phần tử bất ngờ.

## 10. Giám sát và xử lý HTTP đúng nghĩa

Fallback thành công có thể làm API trả HTTP 200, trong khi nguồn chính đang hỏng. Nếu chỉ xem tỷ lệ 5xx tại API đầu ra, hệ thống dễ **không phát hiện được upstream outage**. Cần quan sát riêng các sự kiện:

- **Fallback triggered:** ghi metrics/counter theo loại lỗi và upstream, cùng tỉ lệ dùng cache.
- **Fallback succeeded/failed:** phân biệt trả cache thành công, cache trống, cache hỏng; đặt cảnh báo khi tỉ lệ fallback bất thường.
- **Unexpected error:** giữ stack trace/cause trong log hoặc tracing nội bộ, trả response đã chuẩn hóa với status thích hợp (thường 500), không làm lộ exception details nhạy cảm cho client.
- **Trace/correlation ID:** dùng thông tin tracing phù hợp reactive context; không phụ thuộc mặc định `ThreadLocal` khi chain chuyển scheduler.

Đặt `doOnError` **trước** `onErrorResume` nếu muốn ghi nhận lỗi đã được fallback che ở response; đặt quan sát riêng **sau** fallback nếu cần ghi nhận lỗi không phục hồi. Tránh log stack trace trùng lặp ở nhiều tầng. Có thể ghi metric ngay trong callback fallback và gắn nhãn `stale` hoặc metadata nguồn trong response, như ví dụ `Book.stale`.

Không tùy tiện trả dữ liệu cũ trong nghiệp vụ nhạy cảm như số dư, quyền truy cập, số lượng tồn kho có tác động tài chính hoặc nội dung đã bị thu hồi. Dữ liệu cache phải có tính hợp lệ, TTL, phạm vi tenant/user và chính sách sử dụng được nghiệp vụ đồng ý; không dùng cache chung gây lộ dữ liệu giữa người dùng.

Đầu ra HTTP cần phân biệt rõ:

- **400**: input không hợp lệ; không fallback thành một giá trị hợp lệ giả.
- **401/403**: lỗi xác thực/phân quyền; không chuyển thành dữ liệu từ cache của người khác.
- **404**: dữ liệu không tồn tại; không mặc nhiên coi là lỗi kết nối.
- **503**: nguồn thiết yếu tạm thời không phục vụ và không có phương án thay thế đáp ứng yêu cầu.
- **500**: bug hoặc lỗi ngoài dự kiến cần được phát hiện/điều tra.
- **200 có dấu hiệu `stale`**: chỉ khi nghiệp vụ thực sự chấp nhận response fallback.

Bảng trên là **chính sách minh họa**; status cuối cùng phụ thuộc contract API, exception mapping và thời điểm response đã được commit.

## 11. Checklist trước khi áp dụng `onErrorResume`

1. **Lỗi nào là expected/transient?** Có exception type hoặc predicate xác định được không?
2. **Fallback có đúng dữ liệu và quyền truy cập không?** Có cache miss, stale, TTL, tenant isolation hoặc lỗi fallback cần xử lý không?
3. **Operator nằm ở đâu?** Có bao trùm lỗi mapping, validate hoặc bug không liên quan không?
4. **Nếu fallback thất bại thì sao?** Có giữ lỗi gốc hoặc phát lỗi rõ ràng thay vì rỗng thành công không?
5. **Lỗi không nằm trong danh sách có còn đi tiếp?** Test rõ 400/401/403/404/500 theo hợp đồng của API.
6. **Đang xử lý một Mono hay nhiều phần tử Flux?** Có hiểu việc `onError` kết thúc nguồn gốc, cả stream có thể bị hủy không?
7. **Có đủ quan sát?** Metrics fallback, exception cause, log, trace, timeout và alert có giữ được bức tranh lỗi thật không?
8. **Đã test cả nhánh hỏng chưa?** Test thành công, lỗi được phục hồi, cache miss, fallback error và lỗi lập trình.

### Tự kiểm tra

**Câu 1.** `Mono.error(new IllegalStateException("bug")).onErrorResume(CatalogUnavailableException.class, e -> Mono.just(value))` có trả fallback không? **Không**; type không khớp, `IllegalStateException` tiếp tục lan xuống.

**Câu 2.** Dùng `onErrorResume(ex -> Mono.empty())` sau WebClient có tự sinh HTTP 404 không? **Không**; nó chỉ đổi lỗi thành publisher hoàn thành rỗng, còn HTTP status cần quy tắc khác.

**Câu 3.** `Flux` phát A, B, sau đó lỗi; `onErrorResume` có tự tiếp tục phần còn lại của nguồn gốc không? **Không**; nó chuyển sang publisher fallback mới, không hồi sinh upstream đã kết thúc.

**Câu 4.** Nếu chỉ lỗi 503 của downstream được phép dùng cache, nên dùng `onErrorResume(WebClientException.class, ...)` không? **Không**; quá rộng. Dùng subclass/predicate khớp 503 và giữ nguyên lỗi khác.

**Câu 5.** Sau khi dùng fallback, API vẫn trả 200 nhiều lần; theo dõi 5xx có đủ không? **Không**; phải đo cả tỉ lệ fallback, cache miss và nguyên nhân upstream.

## Tài liệu đối chiếu

- Project Reactor, *Handling Errors*: https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html
- Reactor Core `Mono.onErrorResume` API: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html
- Spring Framework, *WebClient retrieve()*: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-retrieve.html
- Spring Framework, *WebFlux Error Responses*: https://docs.spring.io/spring-framework/reference/web/webflux/ann-rest-exceptions.html
- Project Reactor, *Testing with StepVerifier*: https://projectreactor.io/docs/core/release/reference/testing.html

**Điểm cần nhớ:** `onErrorResume` là công cụ phục hồi **có điều kiện**, không phải cơ chế nuốt lỗi. Hãy phân loại lỗi trước, giới hạn phạm vi operator, bảo toàn nguyên nhân khi fallback không hợp lệ, và kiểm thử rằng lỗi bất ngờ vẫn được quan sát và trả đúng HTTP status.
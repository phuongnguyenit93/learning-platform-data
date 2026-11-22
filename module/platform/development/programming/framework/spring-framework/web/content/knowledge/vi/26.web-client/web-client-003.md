# WebClient: `retrieve()`, `onStatus()`, `exchangeToMono()` và `exchangeToFlux()`

## 1. Mục tiêu và bối cảnh

`WebClient` là HTTP client thuộc Spring WebFlux, xây trên Reactor (`Mono`/`Flux`). Nó có thể dùng trong ứng dụng Spring WebFlux lẫn Spring MVC. Bốn phương thức trong bài giải quyết hai câu hỏi khác nhau:

1. **Ai quyết định cách xử lý HTTP status?** `retrieve()` cung cấp cách xử lý thông thường (mặc định biến HTTP 4xx/5xx thành lỗi), `onStatus()` tùy biến quy tắc đó; `exchangeToMono()` và `exchangeToFlux()` đưa toàn bộ `ClientResponse` vào hàm của bạn để bạn tự rẽ nhánh.
2. **Kết quả có bao nhiêu phần tử?** `Mono<T>` có tối đa một phần tử (hoặc rỗng/lỗi); `Flux<T>` có 0..N phần tử (hoặc lỗi). Chọn theo giao thức dữ liệu và nhu cầu xử lý, không chọn theo việc endpoint là GET hay POST.

Luồng xử lý điển hình:

```text
WebClient.get()/post() → uri()/headers() → gửi HTTP khi subscribe
                                           ├─ retrieve()
                                           │    ├─ onStatus(...) tùy chọn
                                           │    └─ bodyToMono / bodyToFlux / toEntity...
                                           ├─ exchangeToMono(response -> Mono<T>)
                                           └─ exchangeToFlux(response -> Flux<T>)
```

Điểm nền tảng: `Mono`/`Flux` là pipeline *lazy*: chỉ xây pipeline thường chưa gửi request; request được thực hiện khi có subscriber (ví dụ do framework subscribe hoặc trong ví dụ CLI dùng `block()`). Không gọi `block()` trên luồng xử lý non-blocking/event-loop của WebFlux.

## 2. `retrieve()`: đường đi chuẩn cho phản hồi thường gặp

`retrieve()` trả về `WebClient.ResponseSpec` để chọn cách lấy nội dung. Dùng khi muốn decode response bình thường, đồng thời chấp nhận quy tắc status mặc định.

```java
record Product(long id, String name) {}

WebClient client = WebClient.create("https://api.example.com");

Mono<Product> one = client.get()
    .uri("/products/{id}", 42)
    .accept(MediaType.APPLICATION_JSON)
    .retrieve()
    .bodyToMono(Product.class);

Flux<Product> many = client.get()
    .uri("/products")
    .retrieve()
    .bodyToFlux(Product.class);

Mono<ResponseEntity<Product>> withMetadata = client.get()
    .uri("/products/{id}", 42)
    .retrieve()
    .toEntity(Product.class);
```

Các đoạn trên là **minh họa**: cần import WebClient, MediaType, Reactor và ResponseEntity, cần server thực sự ở URL ví dụ. `bodyToMono(Product.class)` đọc một đối tượng; `bodyToFlux(Product.class)` đọc nhiều đối tượng, chẳng hạn JSON array hoặc một luồng định dạng có decoder thích hợp. `toEntity(Product.class)` giữ HTTP status/headers cùng body; đây là cách lấy metadata mà vẫn dùng `retrieve()`.

**Mặc định lỗi HTTP:** nếu không có handler khớp, status từ 400 trở lên được ánh xạ thành `WebClientResponseException` (bao gồm các subclass phù hợp, ví dụ NotFound). Exception chứa status, headers và có thể chứa body lỗi. Thành công HTTP không có nghĩa JSON luôn decode thành công: body không hợp lệ hoặc content type không phù hợp vẫn có thể phát sinh lỗi codec. Lỗi DNS, kết nối hoặc timeout là một nhóm lỗi khác (`WebClientRequestException` hoặc nguyên nhân tương ứng); `onStatus()` chỉ dành cho phản hồi đã nhận được HTTP status.

`retrieve()` không trả trực tiếp `ClientResponse` để bạn tùy ý đọc body hai lần. Khi cần chọn decoder theo status hoặc content-type theo logic riêng, xem `exchangeToMono()` / `exchangeToFlux()`.

## 3. `onStatus()`: ánh xạ HTTP status thành lỗi nghiệp vụ

`onStatus(Predicate<HttpStatusCode>, Function<ClientResponse, Mono<? extends Throwable>>)` được gọi **sau `retrieve()`, trước thao tác đọc body**. Predicate chọn status; hàm thứ hai trả về publisher tạo ra exception cần phát downstream.

```java
Mono<Product> product = client.get()
    .uri("/products/{id}", 42)
    .retrieve()
    .onStatus(
        status -> status.value() == 404,
        response -> response.bodyToMono(String.class)
            .defaultIfEmpty("Không có mô tả lỗi")
            .map(message -> new ProductNotFoundException(message))
    )
    .onStatus(
        HttpStatusCode::is5xxServerError,
        response -> response.createException()
    )
    .bodyToMono(Product.class);
```

Trong đó `ProductNotFoundException` là class exception nghiệp vụ do ứng dụng định nghĩa (đoạn trên không phải chương trình độc lập). Cần import `org.springframework.http.HttpStatusCode`. Handler đọc body 404 thành chuỗi rồi tạo exception; khi không có body, `defaultIfEmpty` đảm bảo vẫn phát lỗi. `response.createException()` tạo `Mono<WebClientResponseException>` theo status/headers/body. Ví dụ 5xx minh họa việc giữ thông tin HTTP gốc; nếu không cần đổi quy tắc này, có thể bỏ handler 5xx vì mặc định đã xử lý.

Ba lựa chọn dễ nhầm:

- Trả `Mono.just(new MyException(...))` hoặc một `Mono` phát ra `Throwable` → `retrieve()` biến thành **tín hiệu lỗi**.
- Trả `Mono.empty()` từ **hàm `onStatus`** → *bỏ xử lý status đó như lỗi*, để response đi tiếp qua bộ giải mã body. Đây **không phải** là bỏ qua response, cũng không biến 404 thành body rỗng.
- Gọi `onErrorResume(...)` **sau** `bodyToMono(...)` → quyết định cách khôi phục từ lỗi đã phát, ví dụ fallback một giá trị mặc định; nó có thể bắt cả lỗi status, kết nối hoặc decode tùy loại exception được lọc.

```java
Mono<String> displayName = client.get()
    .uri("/profiles/{id}", 42)
    .retrieve()
    .onStatus(
        status -> status.value() == 404,
        response -> response.bodyToMono(String.class)
            .map(message -> new IllegalArgumentException("Profile absent: " + message))
    )
    .bodyToMono(String.class)
    .onErrorResume(IllegalArgumentException.class, error -> Mono.just("Khách ẩn danh"));
```

**Thứ tự handler có ý nghĩa:** khi nhiều predicate khớp, handler khớp đầu tiên được áp dụng. Đặt quy tắc chuyên biệt (ví dụ 404) trước quy tắc tổng quát (4xx). Chú ý API có `onRawStatus(IntPredicate, ...)` nếu cần xử lý mã số tùy biến.

## 4. `exchangeToMono()`: quyết định từ `ClientResponse`, trả một kết quả

`exchangeToMono(response -> Mono<T>)` cho truy cập trực tiếp status và headers, rồi chọn cách decode hoặc lỗi. Đây là lựa chọn khi *mỗi status có thể mang body schema khác nhau*, hoặc ứng dụng muốn coi 404 là một kết quả hợp lệ.

```java
Mono<Optional<Product>> result = client.get()
    .uri("/products/{id}", 42)
    .exchangeToMono(response -> {
        int status = response.statusCode().value();
        if (status == 404) {
            return Mono.just(Optional.<Product>empty());
        }
        if (response.statusCode().is2xxSuccessful()) {
            return response.bodyToMono(Product.class).map(Optional::of);
        }
        return response.createException()
            .flatMap(error -> Mono.error(error));
    });
```

Đây là **đoạn minh họa** cần import `Optional`; body 404 cố ý không đọc vì không cần nó. Loại kết quả của mọi nhánh phải nhất quán thành `Mono<Optional<Product>>`. Với 2xx có body trống, nhánh minh họa phát `Mono.empty()` (không có Optional); nếu nghiệp vụ đòi kết quả `Optional.empty()`, bổ sung `.defaultIfEmpty(Optional.empty())` sau nhánh body.

Sự khác biệt quan trọng:

- **Không có cơ chế `onStatus()` ở đây**: status 404/500 **không tự bị chuyển thành lỗi** như khi dùng `retrieve()`. Hàm callback chịu trách nhiệm đầy đủ cho mọi status mà ứng dụng quan tâm.
- Để giữ lỗi HTTP gốc, dùng `response.createException()` hoặc `response.createError()` thay vì lặng lẽ decode body lỗi thành đối tượng thành công.
- Phải **decode/consume body bên trong callback** nếu cần. Sau khi `Mono` do callback trả về kết thúc, phần body chưa dùng được Spring kiểm tra và giải phóng; không thể cất `ClientResponse` để decode body sau ở phía downstream. Không cố đọc cùng body hai lần.
- Có thể truy cập `response.headers().contentType()` rồi rẽ nhánh decoder theo content type nếu endpoint có nhiều dạng body; phải xử lý cả trường hợp header vắng mặt.

## 5. `exchangeToFlux()`: quyết định từ `ClientResponse`, trả luồng nhiều phần tử

`exchangeToFlux(response -> Flux<T>)` tương tự `exchangeToMono` nhưng callback trả `Flux<T>`. Chọn khi cần chuỗi kết quả nhiều phần tử, ví dụ danh sách sản phẩm hoặc stream sự kiện. Đây không nhất thiết là streaming qua mạng: JSON array cũng có thể được decode thành `Flux<Product>`; luồng nhận dần từng chunk cần server cung cấp định dạng/đường truyền phù hợp (SSE, NDJSON, v.v.).

```java
Flux<Product> products = client.get()
    .uri("/products")
    .accept(MediaType.APPLICATION_JSON)
    .exchangeToFlux(response -> {
        if (response.statusCode().is2xxSuccessful()) {
            return response.bodyToFlux(Product.class);
        }
        if (response.statusCode().value() == 404) {
            return Flux.empty();
        }
        return response.createException()
            .flatMapMany(error -> Flux.error(error));
    });
```

`Flux.empty()` ở nhánh 404 diễn đạt rõ quyết định nghiệp vụ: danh sách không tồn tại được coi như không có phần tử. Trong nhiều API, 404 phải được xem là lỗi; đừng tự động chuyển mọi 404 thành danh sách trống.

Nếu decode trực tiếp qua `retrieve().bodyToFlux(Product.class)` đã đủ, **không cần** `exchangeToFlux()`. Tương tự `exchangeToMono`, body chỉ còn khả dụng trong lifecycle của callback.

## 6. Ví dụ chạy độc lập, phản hồi giả lập không cần server HTTP

Ví dụ dưới dùng `ExchangeFunction` giả lập bốn HTTP response. Vì vậy có thể chạy và kiểm chứng kết quả mà không gọi internet. Mẫu dùng Java 17+, Gradle và Spring Boot Starter WebFlux 3.3.13; dữ liệu JSON được Jackson decode thành Java `record`. Cấu trúc:

```text
webclient-status-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/WebClientStatusDemo.java
```

**`settings.gradle`**

```groovy
rootProject.name = 'webclient-status-demo'
```

**`build.gradle`**

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux:3.3.13'
}

application {
    mainClass = 'demo.WebClientStatusDemo'
}
```

**`src/main/java/demo/WebClientStatusDemo.java`**

```java
package demo;

import java.util.List;

import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.client.ClientResponse;
import org.springframework.web.reactive.function.client.ExchangeFunction;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public class WebClientStatusDemo {
    public record Book(int id, String name) {}

    private static ClientResponse json(String body) {
        return ClientResponse.create(HttpStatus.OK)
            .header(HttpHeaders.CONTENT_TYPE, MediaType.APPLICATION_JSON_VALUE)
            .body(body)
            .build();
    }

    public static void main(String[] args) {
        ExchangeFunction fakeHttp = request -> {
            ClientResponse response = switch (request.url().getPath()) {
                case "/book" -> json("{\"id\":7,\"name\":\"Lan\"}");
                case "/books" -> json(
                    "[{\"id\":7,\"name\":\"Lan\"},{\"id\":8,\"name\":\"Minh\"}]");
                case "/missing" -> ClientResponse.create(HttpStatus.NOT_FOUND)
                    .header(HttpHeaders.CONTENT_TYPE, MediaType.TEXT_PLAIN_VALUE)
                    .body("missing book")
                    .build();
                default -> ClientResponse.create(HttpStatus.INTERNAL_SERVER_ERROR)
                    .body("unexpected route")
                    .build();
            };
            return Mono.just(response);
        };

        WebClient client = WebClient.builder()
            .exchangeFunction(fakeHttp)
            .build();

        Book book = client.get().uri("/book")
            .retrieve()
            .bodyToMono(Book.class)
            .block();
        System.out.println("retrieve: " + book);

        String statusResult = client.get().uri("/missing")
            .retrieve()
            .onStatus(
                status -> status.value() == 404,
                response -> response.bodyToMono(String.class)
                    .map(msg -> new IllegalStateException("HTTP 404: " + msg))
            )
            .bodyToMono(Book.class)
            .map(Book::name)
            .onErrorResume(IllegalStateException.class,
                error -> Mono.just(error.getMessage()))
            .block();
        System.out.println("onStatus: " + statusResult);

        String notFound = client.get().uri("/missing")
            .exchangeToMono(response -> {
                if (response.statusCode().value() == 404) {
                    return Mono.just("Không tìm thấy");
                }
                if (response.statusCode().is2xxSuccessful()) {
                    return response.bodyToMono(String.class);
                }
                return response.createException()
                    .flatMap(error -> Mono.error(error));
            })
            .block();
        System.out.println("exchangeToMono: " + notFound);

        List<Book> books = client.get().uri("/books")
            .exchangeToFlux(response -> {
                if (response.statusCode().is2xxSuccessful()) {
                    return response.bodyToFlux(Book.class);
                }
                return response.createException()
                    .flatMapMany(error -> Flux.error(error));
            })
            .collectList()
            .block();
        System.out.println("exchangeToFlux: " + books);
    }
}
```

Chạy từ thư mục dự án với JDK 17+ và Gradle đã cài (hoặc thay `gradle` bằng `./gradlew` nếu có Gradle Wrapper):

```bash
gradle run --quiet
```

**Các dòng do chương trình in** (thư viện có thể in thêm log trong một số môi trường):

```text
retrieve: Book[id=7, name=Lan]
onStatus: HTTP 404: missing book
exchangeToMono: Không tìm thấy
exchangeToFlux: [Book[id=7, name=Lan], Book[id=8, name=Minh]]
```

Giải thích: phản hồi `/book` có JSON object nên `bodyToMono` sinh một `Book`. `/missing` ở đường `retrieve()` được `onStatus` chuyển thành `IllegalStateException` và `onErrorResume` đổi lỗi thành thông báo; cùng mã 404 được `exchangeToMono` chủ động coi là kết quả "Không tìm thấy". `/books` chứa JSON array, `bodyToFlux` decode hai phần tử rồi `collectList()` gom thành `List<Book>`. `block()` chỉ dùng để dễ quan sát trong hàm `main` kiểu CLI.

## 7. Bảng chọn nhanh

| Nhu cầu | API phù hợp | Ai xử lý status? | Kiểu kết quả điển hình |
| --- | --- | --- | --- |
| Đọc object JSON, nhận mặc định 4xx/5xx là lỗi | `retrieve().bodyToMono(...)` | Spring mặc định | `Mono<T>` |
| Đọc danh sách/stream, status mặc định | `retrieve().bodyToFlux(...)` | Spring mặc định | `Flux<T>` |
| Map 404/422/5xx thành exception nghiệp vụ | `retrieve().onStatus(...).bodyToMono/Flux(...)` | Spring + handler tùy biến | `Mono<T>` hoặc `Flux<T>` |
| 404 thành Optional rỗng; 200 giải mã theo schema riêng | `exchangeToMono(...)` | Chính callback | `Mono<T>` |
| Trả 0..N phần tử theo status/content type | `exchangeToFlux(...)` | Chính callback | `Flux<T>` |

Quy tắc thực hành: **bắt đầu với `retrieve()`**, thêm `onStatus()` khi chỉ cần tùy biến lỗi. Chọn `exchangeToMono()`/`exchangeToFlux()` khi nghiệp vụ phải điều khiển toàn bộ cách diễn giải response.

## 8. Lỗi phổ biến và cách tránh

1. **Tưởng `onStatus` dùng được sau `exchangeToMono`.** `onStatus` là phương thức của `ResponseSpec` sinh từ `retrieve`; ở nhánh `exchangeTo*` hãy rẽ nhánh theo `response.statusCode()` trong callback.
2. **Chỉ kiểm tra 2xx trong `exchangeTo*` và bỏ qua nhánh còn lại.** Không có mapping 4xx/5xx mặc định như `retrieve`; hãy dùng `createException`/`createError` hoặc một lựa chọn nghiệp vụ tường minh.
3. **Trả `Mono.empty()` từ `onStatus` rồi cho rằng request 404 đã bị bỏ qua.** Nó chỉ bỏ trạng thái lỗi; decode body vẫn tiếp tục và có thể thất bại nếu response là HTML/text, còn DTO mong JSON.
4. **Đọc body lỗi hai lần.** Body response là luồng tiêu thụ một lần; nếu cần chi tiết lỗi, decode ngay trong `onStatus` hay `exchangeTo*`, sau đó tạo exception hoặc một giá trị kết quả.
5. **Nhầm `bodyToFlux` với bảo đảm truyền dữ liệu real-time.** Flux biểu diễn 0..N phần tử, nhưng streaming thực sự còn phụ thuộc server, media type, codec và proxy/buffering.
6. **`onErrorResume` bắt mọi lỗi và trả success giả.** Nên lọc exception cụ thể; phân biệt HTTP status, kết nối, timeout, giải mã, và chỉ fallback khi hợp đồng nghiệp vụ cho phép.
7. **Gọi `block()` trong request handler WebFlux.** Việc chặn event loop có thể làm giảm khả năng phục vụ hoặc gây lỗi; trả thẳng `Mono`/`Flux`, phối hợp bằng `map`, `flatMap`, `zip`.
8. **Không xử lý body rỗng.** `bodyToMono` có thể hoàn thành không phát giá trị (ví dụ 204); cân nhắc `switchIfEmpty`, `defaultIfEmpty`, hoặc `Mono<Void>` theo hợp đồng endpoint.
9. **Trộn retry với mọi 4xx.** Retry chỉ nên áp dụng lỗi tạm thời có thể phục hồi, có giới hạn số lần và backoff; tránh retry mù request gây tác dụng phụ (POST không idempotent).
10. **Dựa vào `retrieve()` để nhận headers nhưng bỏ mất chúng.** Dùng `toEntity(...)`/`toEntityList(...)` nếu muốn status/headers và body nhưng không cần control flow của `exchangeTo*`.

## 9. Kiểm tra hiểu bài

- Endpoint GET `/orders/9` trả 404 kèm JSON lỗi. Nếu muốn phát `OrderNotFoundException` thì dùng gì? → `retrieve().onStatus(...)`, parse body lỗi và tạo exception; nếu 404 là một kết quả bình thường với schema khác, `exchangeToMono(...)` có thể phù hợp hơn.
- Endpoint trả JSON array 200 và 500 HTML. Nếu muốn danh sách hoặc lỗi HTTP chuẩn? → `retrieve().bodyToFlux(Order.class)` đã đủ. Nếu HTTP 404 phải trở thành luồng trống, có thể viết callback `exchangeToFlux(...)` rõ ràng.
- Với `onStatus(status -> status.value() == 404, response -> Mono.empty())` thì điều gì xảy ra? → Response 404 đi tiếp vào decoder; không tự động phát `Mono.empty()` ở downstream.
- Vì sao không giữ `ClientResponse` rồi decode ở `flatMap` bên ngoài `exchangeToMono`? → Callback phải quyết định và tiêu thụ body trong phạm vi của nó; phần body chưa dùng sẽ được giải phóng sau khi publisher callback kết thúc.

## 10. Tài liệu tham khảo

- Spring Framework — WebClient: https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html
- Spring Framework — `retrieve()` và `onStatus()`: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-retrieve.html
- Spring Framework — `exchangeToMono()` / `exchangeToFlux()`: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-exchange.html
- Spring Framework API — `WebClient.ResponseSpec`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/function/client/WebClient.ResponseSpec.html

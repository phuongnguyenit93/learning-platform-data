# Phân biệt lỗi giao thức HTTP với lỗi trong luồng Publisher

Trong ứng dụng reactive dùng Spring WebFlux, một endpoint có thể trả về `Mono<T>` hoặc `Flux<T>`. Khi xử lý lỗi, cần phân biệt **HTTP error response** với **lỗi terminal signal của Publisher**. Hai hiện tượng có thể liên quan nhưng không đồng nghĩa:

- HTTP error response là một HTTP response hợp lệ có status như 400, 404 hoặc 500. Client vẫn nhận được status, header và có thể có error body.
- Publisher error là tín hiệu `onError` kết thúc một reactive stream. Bản thân tín hiệu này không chứa HTTP status. Spring có thể chuyển lỗi thành HTTP response nếu lỗi được xử lý trước khi response được commit.
- Transport error xảy ra khi không nhận được HTTP response, ví dụ kết nối bị từ chối, timeout hoặc kết nối bị đóng bất ngờ.

Trong bài này, cụm “lỗi HTTP” nói đến response có status 4xx/5xx. Đây vẫn là response HTTP hợp lệ, không phải lỗi cú pháp hoặc framing của giao thức như status line hay header sai định dạng.

Khi kiểm thử bằng `WebTestClient`, phải xác định đang kiểm tra status của response, lỗi phát ra khi đọc body Publisher hay lỗi kết nối. Nếu gộp chúng thành một khái niệm, test có thể kết luận sai rằng một HTTP 200 luôn có body thành công hoặc mọi `onError` đều phải trở thành HTTP 500.

## 1. HTTP error response là gì?

HTTP response có status code, header và có thể có body. Status code mô tả kết quả xử lý ở tầng HTTP:

| Nhóm status | Ý nghĩa | Ví dụ |
|---|---|---|
| 2xx | Request được xử lý thành công. | 200 OK, 201 Created, 204 No Content. |
| 3xx | Client cần thực hiện điều hướng hoặc xử lý tiếp. | 301 Moved Permanently, 302 Found, 304 Not Modified. |
| 4xx | Request có vấn đề từ phía client hoặc tài nguyên/điều kiện được yêu cầu không phù hợp. | 400 Bad Request, 401 Unauthorized, 403 Forbidden, 404 Not Found. |
| 5xx | Server không thể hoàn thành request do lỗi phía server hoặc thành phần upstream. | 500 Internal Server Error, 502 Bad Gateway, 503 Service Unavailable. |

Một response 404 không phải là Publisher error. Server đã gửi một response HTTP hợp lệ, trong đó status là 404. Client có thể đọc status và error body như với bất kỳ response nào khác.

Ví dụ:

~~~http
HTTP/1.1 404 Not Found
Content-Type: application/json

{
  "code": "ITEM_NOT_FOUND",
  "message": "Item does not exist"
}
~~~

Trong test, ta kiểm tra trực tiếp status và body:

~~~java
client.get()
    .uri("/items/999")
    .exchange()
    .expectStatus().isNotFound()
    .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
    .expectBody()
    .jsonPath("$.code").isEqualTo("ITEM_NOT_FOUND");
~~~

`WebTestClient.exchange()` cho phép kiểm tra status 4xx/5xx như một phần của response. Nó không mặc định biến mọi status lỗi thành exception giống cách `WebClient.retrieve()` thường làm khi đọc response. Vì vậy, với WebTestClient, hãy dùng `expectStatus()` để xác nhận status theo hợp đồng API.

## 2. Publisher error là gì?

Reactive Streams định nghĩa ba tín hiệu chính:

- `onNext(value)`: Publisher phát một phần tử.
- `onComplete()`: Publisher kết thúc bình thường.
- `onError(error)`: Publisher kết thúc bằng lỗi.

`onError` là tín hiệu terminal: sau khi phát `onError`, Publisher không tiếp tục phát thêm `onNext` hoặc `onComplete`.

Ví dụ:

~~~java
Flux<Integer> numbers = Flux.concat(
    Flux.just(1, 2),
    Flux.error(new IllegalStateException("calculation failed"))
);
~~~

Luồng tín hiệu:

~~~text
onSubscribe
    |
    v
onNext(1)
    |
    v
onNext(2)
    |
    v
onError(IllegalStateException)
~~~

Publisher này không tự tạo ra HTTP 500. Nó chỉ phát hai phần tử rồi kết thúc bằng lỗi. Khi Publisher được dùng làm response body trong WebFlux, Spring phải chuyển tín hiệu reactive đó thành hành vi HTTP phù hợp với trạng thái hiện tại của response.

## 3. Spring WebFlux chuyển Publisher error thành HTTP response như thế nào?

Kết quả phụ thuộc vào thời điểm lỗi xảy ra và response đã được commit hay chưa.

### Lỗi xảy ra trước khi response được commit

Nếu Publisher lỗi trước khi server gửi status/header hoặc ghi body khiến response được commit, Spring WebFlux vẫn có cơ hội xử lý exception. Các cơ chế như `@ExceptionHandler`, `@RestControllerAdvice` hoặc `WebExceptionHandler` có thể chuyển lỗi thành một HTTP response có status phù hợp.

Ví dụ controller trả về Mono:

~~~java
import reactor.core.publisher.Mono;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ItemController {

    private final ItemService itemService;

    ItemController(ItemService itemService) {
        this.itemService = itemService;
    }

    @GetMapping("/items/{id}")
    Mono<Item> findById(@PathVariable long id) {
        return itemService.findById(id)
            .switchIfEmpty(Mono.error(new ItemNotFoundException(id)));
    }
}
~~~

Exception handler chuyển lỗi nghiệp vụ thành HTTP 404:

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
class ApiExceptionHandler {

    @ExceptionHandler(ItemNotFoundException.class)
    ResponseEntity<ApiError> handleItemNotFound(ItemNotFoundException exception) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
            .body(new ApiError("ITEM_NOT_FOUND", exception.getMessage()));
    }
}

record ApiError(String code, String message) {}
~~~

Publisher của service phát lỗi, nhưng Spring xử lý lỗi trước khi ghi response. Client cuối cùng nhận một HTTP 404 có error body.

Test:

~~~java
client.get()
    .uri("/items/999")
    .exchange()
    .expectStatus().isNotFound()
    .expectBody()
    .jsonPath("$.code").isEqualTo("ITEM_NOT_FOUND");
~~~

Điều test xác nhận là hợp đồng HTTP mà client nhận được. Nó không cần biết bên trong service đã dùng `Mono.error(...)`, ném exception đồng bộ hay một cơ chế khác tạo ra lỗi.

### Lỗi xảy ra sau khi response đã được commit

Khi response đã được commit, status và header HTTP không thể đổi lại. Nếu Publisher body phát một số phần tử rồi mới phát `onError`, server không thể quay lại thay status 200 thành 500 hoặc thay phần body đã gửi.

Tình huống này thường gặp với response streaming, ví dụ NDJSON hoặc Server-Sent Events, nơi dữ liệu có thể được ghi dần xuống client.

Ví dụ:

~~~java
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;

@RestController
class NumberStreamController {

    @GetMapping(value = "/numbers", produces = MediaType.APPLICATION_NDJSON_VALUE)
    Flux<Integer> numbers() {
        return Flux.concat(
            Flux.just(1, 2),
            Flux.error(new IllegalStateException("stream failed"))
        );
    }
}
~~~

Khi stream bắt đầu gửi dữ liệu, response có thể đã được commit với status 200. Sau đó Publisher lỗi. Client có thể nhận được các phần tử đã phát rồi gặp lỗi khi đọc phần còn lại. Lớp HTTP không thể thay status đã gửi thành 500.

Biểu hiện cụ thể ở client phụ thuộc media type, message writer, connector và thời điểm commit. Với response streaming, client có thể nhận một stream kết thúc bất thường; với một số kiểu body được buffer trước khi ghi, framework có thể phát hiện lỗi sớm hơn và vẫn tạo được error response. Vì vậy, không nên kết luận chỉ dựa trên việc Publisher đã phát `onNext`; hãy xét trạng thái response commitment thực tế.

## 4. Bảng phân biệt các loại lỗi

| Tình huống | Có HTTP response không? | Client quan sát điều gì? | Cách kiểm thử |
|---|---|---|---|
| Controller trả 404 có error body | Có | Status 404 và body lỗi. | `expectStatus().isNotFound()`, kiểm tra body. |
| Publisher lỗi trước khi response commit và được exception handler ánh xạ | Có | Status được handler chọn, ví dụ 400 hoặc 500. | Kiểm tra status và error body bằng WebTestClient. |
| Publisher body lỗi sau khi response commit | Response đã bắt đầu; status/header đã cố định. | Có thể nhận một phần body rồi body stream kết thúc bằng lỗi. | Kiểm tra status ban đầu và dùng StepVerifier trên response body Publisher. |
| Publisher lỗi được phục hồi bằng onErrorResume | Có response bình thường nếu recovery hoàn tất. | Giá trị fallback hoặc dữ liệu thay thế. | Kiểm tra status và body bình thường. |
| Kết nối bị từ chối hoặc timeout trước khi nhận response | Không. | Exchange thất bại bằng transport exception. | Kiểm tra lỗi ở client hoặc integration test với server/connector. |

Một status 500 vẫn là HTTP response. Một `onError` vẫn là tín hiệu reactive. Một connection reset vẫn là lỗi transport. Chúng có thể phát sinh từ cùng một sự cố, nhưng phải được kiểm tra theo đúng tầng.

## 5. Dùng onErrorResume để phục hồi Publisher

Nếu lỗi có thể được xử lý ngay trong reactive pipeline, ta có thể thay thế lỗi bằng một giá trị hoặc Publisher khác trước khi lỗi lan đến tầng HTTP.

Ví dụ:

~~~java
Flux<Integer> numbers = Flux.concat(
        Flux.just(1, 2),
        Flux.error(new IllegalStateException("temporary failure"))
    )
    .onErrorResume(error -> Flux.just(-1));
~~~

Kết quả quan sát được:

~~~text
onNext(1)
onNext(2)
onNext(-1)
onComplete()
~~~

Lỗi gốc đã được xử lý trong pipeline. Subscriber phía dưới không nhận `onError`, mà nhận giá trị fallback và `onComplete`.

Controller có thể áp dụng cách tương tự:

~~~java
@GetMapping("/numbers/recovered")
Flux<Integer> recoveredNumbers() {
    return Flux.concat(
            Flux.just(1, 2),
            Flux.error(new IllegalStateException("temporary failure"))
        )
        .onErrorResume(error -> Flux.just(-1));
}
~~~

Test:

~~~java
client.get()
    .uri("/numbers/recovered")
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .json("[1, 2, -1]");
~~~

Response này thành công vì Publisher đã được phục hồi trước khi Spring hoàn tất response. Không có HTTP error status và client cũng không nhận Publisher error.

### Các toán tử xử lý lỗi thường gặp

| Toán tử | Hành vi |
|---|---|
| `onErrorReturn(value)` | Thay lỗi bằng một giá trị fallback rồi kết thúc bình thường. |
| `onErrorResume(error -> publisher)` | Chuyển sang Publisher khác để phục hồi hoặc thay thế luồng. |
| `onErrorMap(error -> mapped)` | Biến đổi exception rồi tiếp tục phát lỗi mới. |
| `doOnError(consumer)` | Quan sát lỗi, thường dùng log/metric; không phục hồi lỗi. |
| `retry(...)` | Đăng ký thực hiện lại khi gặp lỗi theo chính sách retry. |

Ví dụ:

~~~java
return itemService.findById(id)
    .doOnError(error -> log.warn("Cannot load item {}", id, error))
    .onErrorMap(TimeoutException.class,
        error -> new UpstreamUnavailableException("Item service timeout", error));
~~~

`doOnError` không làm Publisher trở thành thành công. `onErrorMap` cũng không phục hồi; nó chỉ đổi loại exception. Nếu exception được chuyển thành lỗi nghiệp vụ rồi tới exception handler, Spring vẫn có thể ánh xạ nó thành HTTP response phù hợp.

Không nên dùng `onErrorResume` để che giấu mọi lỗi bằng một giá trị mặc định chung. Fallback phải phù hợp với ý nghĩa nghiệp vụ và hợp đồng API. Nếu dữ liệu fallback khiến client hiểu nhầm rằng thao tác đã thành công, hãy trả một HTTP error response rõ ràng thay vì âm thầm thay thế dữ liệu.

## 6. Kiểm thử HTTP status lỗi bằng WebTestClient

Với một lỗi được ánh xạ thành HTTP response, test nên kiểm tra status và cấu trúc error body:

~~~java
client.get()
    .uri("/items/999")
    .exchange()
    .expectStatus().isNotFound()
    .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
    .expectBody()
    .jsonPath("$.code").isEqualTo("ITEM_NOT_FOUND")
    .jsonPath("$.message").isNotEmpty();
~~~

Có thể kiểm tra các nhóm status khác:

~~~java
client.get().uri("/validation-error")
    .exchange()
    .expectStatus().isBadRequest();

client.get().uri("/forbidden")
    .exchange()
    .expectStatus().isForbidden();

client.get().uri("/upstream-unavailable")
    .exchange()
    .expectStatus().is5xxServerError();
~~~

Không nên chỉ kiểm tra rằng status là 4xx hoặc 5xx nếu API đã định nghĩa status cụ thể. Ví dụ, lỗi tài nguyên không tồn tại thường phải là 404, dữ liệu đầu vào không hợp lệ là 400, còn lỗi upstream có thể là 502 hoặc 503 tùy hợp đồng.

## 7. Kiểm thử Publisher error trực tiếp bằng StepVerifier

Nếu mục tiêu là xác nhận một service hoặc Publisher phát đúng tín hiệu reactive, hãy kiểm thử Publisher trực tiếp bằng `StepVerifier`. Cách này tách hành vi reactive khỏi HTTP serialization và response commitment.

Ví dụ service:

~~~java
import reactor.core.publisher.Flux;

class NumberService {

    Flux<Integer> stream() {
        return Flux.concat(
            Flux.just(1, 2),
            Flux.error(new IllegalStateException("stream failed"))
        );
    }
}
~~~

Test:

~~~java
import org.junit.jupiter.api.Test;
import reactor.test.StepVerifier;
import java.time.Duration;

class NumberServiceTests {

    private final NumberService service = new NumberService();

    @Test
    void emitsValuesThenTerminatesWithError() {
        StepVerifier.create(service.stream())
            .expectNext(1, 2)
            .expectErrorMatches(error ->
                error instanceof IllegalStateException
                    && error.getMessage().equals("stream failed"))
            .verify(Duration.ofSeconds(5));
    }
}
~~~

Các bước của StepVerifier:

1. Subscribe vào Publisher.
2. Xác nhận các phần tử phát ra theo thứ tự.
3. Xác nhận tín hiệu kết thúc là `onError` với exception mong đợi.
4. Gọi `verify()` để thực sự chạy kịch bản và chờ terminal signal.

Các expectation thường dùng:

| API | Mục đích |
|---|---|
| `expectNext(value)` | Xác nhận phần tử tiếp theo. |
| `expectNext(a, b)` | Xác nhận nhiều phần tử theo thứ tự. |
| `expectNextCount(n)` | Xác nhận số phần tử tiếp theo. |
| `expectNextMatches(predicate)` | Xác nhận phần tử thỏa điều kiện. |
| `expectComplete()` | Xác nhận `onComplete`. |
| `expectError()` | Xác nhận có `onError`. |
| `expectError(Class)` | Xác nhận loại exception. |
| `expectErrorMessage(message)` | Xác nhận thông điệp lỗi. |
| `expectErrorMatches(predicate)` | Xác nhận exception theo điều kiện. |
| `verify(Duration)` | Chạy và đặt giới hạn thời gian chờ. |

StepVerifier kiểm tra tín hiệu Publisher. Nó không kiểm tra HTTP status, header, JSON serialization hoặc hành vi của connector.

## 8. Kiểm thử lỗi trong response body stream

Nếu endpoint trả về streaming response, có thể kiểm tra status trước rồi lấy response body Publisher để xác nhận các phần tử và terminal error.

Controller:

~~~java
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;

@RestController
class StreamController {

    @GetMapping(value = "/stream", produces = MediaType.APPLICATION_NDJSON_VALUE)
    Flux<Integer> stream() {
        return Flux.concat(
            Flux.just(1, 2),
            Flux.error(new IllegalStateException("stream failed"))
        );
    }
}
~~~

Test với WebTestClient và StepVerifier:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.FluxExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.test.StepVerifier;

import static org.springframework.test.web.reactive.server.WebTestClient.bindToController;

class StreamControllerTests {

    private final WebTestClient client = bindToController(new StreamController())
        .build();

    @Test
    void responseBodyTerminatesWithErrorAfterStreamingValues() {
        FluxExchangeResult<Integer> result = client.get()
            .uri("/stream")
            .accept(MediaType.APPLICATION_NDJSON)
            .exchange()
            .expectStatus().isOk()
            .returnResult(Integer.class);

        StepVerifier.create(result.getResponseBody())
            .expectNext(1, 2)
            .expectError()
            .verify();
    }
}
~~~

Test này thể hiện hai assertion ở hai tầng:

- `expectStatus().isOk()` xác nhận HTTP response đã bắt đầu với status 200.
- StepVerifier xác nhận body Publisher phát hai giá trị rồi kết thúc bằng lỗi.

Với mock WebTestClient binding, lỗi có thể được chuyển trực tiếp qua response body Publisher. Khi kiểm thử với server thật, lỗi sau khi response commit có thể được quan sát dưới dạng lỗi đọc body hoặc kết nối đóng bất thường; loại exception cụ thể phụ thuộc connector và client. Vì vậy, nếu mục tiêu là kiểm tra terminal error của Publisher, test trực tiếp service bằng StepVerifier là cách ổn định hơn. Nếu mục tiêu là kiểm tra hành vi truyền dữ liệu qua mạng khi stream lỗi, cần integration test với server thật và assertion theo connector đang dùng.

Nếu dùng `expectBodyList(...)` để gom toàn bộ stream thành một list, body Publisher phải hoàn tất bình thường. Khi nó phát `onError`, việc aggregate sẽ thất bại. Với streaming response cần kiểm tra từng phần tử và terminal signal, hãy dùng `returnResult(...)` rồi StepVerifier trên `getResponseBody()`.

## 9. Vì sao status có thể là 200 dù body Publisher lỗi?

HTTP status và header thường được ghi trước hoặc cùng lúc với quá trình gửi body. Với response streaming, server có thể gửi status 200 và bắt đầu ghi phần tử đầu tiên. Khi Publisher phát lỗi sau đó, status đã được gửi đi và không thể thay đổi.

Ví dụ:

~~~text
Server gửi:
HTTP/1.1 200 OK
Content-Type: application/x-ndjson

1
2

Publisher phát onError(...)
~~~

Client đã nhận status 200 và hai dòng dữ liệu. Phần còn lại của body không được hoàn tất bình thường. Đây không phải response 500; đây là response 200 có body stream bị kết thúc bất thường.

Nếu API cần báo lỗi nghiệp vụ trong một stream đã bắt đầu, cần thiết kế giao thức body để biểu diễn lỗi như một phần tử dữ liệu, hoặc kết thúc stream theo một quy ước được client hiểu. Không thể thay đổi status HTTP sau khi response đã commit.

Ví dụ event stream có thể dùng một event type riêng để mô tả lỗi nghiệp vụ:

~~~text
event: data
data: {"value": 1}

event: error
data: {"code": "UPSTREAM_FAILED"}
~~~

Đây là quy ước của payload streaming, không phải một HTTP error status mới. Client phải hiểu event type và xử lý theo hợp đồng của stream.

## 10. Lỗi xảy ra trước khi có bất kỳ response nào

Một request có thể thất bại trước khi server trả về HTTP response:

- DNS không phân giải được hostname.
- Kết nối TCP bị từ chối.
- TLS handshake thất bại.
- Client timeout khi chờ kết nối hoặc response.
- Connection bị reset trước khi nhận status line.

Trong các trường hợp này, không có status code để kiểm tra. `expectStatus()` không thể xác nhận 500 nếu server chưa gửi response 500.

Với WebTestClient kết nối server thật, có thể kiểm tra lỗi exchange bằng assertion ở tầng client hoặc bằng test framework bắt exception:

~~~java
import static org.assertj.core.api.Assertions.assertThatThrownBy;

WebTestClient client = WebTestClient.bindToServer()
    .baseUrl(unavailableBaseUrl)
    .build();

assertThatThrownBy(() ->
    client.get()
        .uri("/")
        .exchange()
)
    .isInstanceOf(RuntimeException.class);
~~~

Trong ví dụ, `unavailableBaseUrl` là địa chỉ test được cấu hình để không có server lắng nghe. Đoạn minh họa cần được điều chỉnh theo loại exception thực tế của client/connector và cách cấu hình WebTestClient. Không nên khóa test vào một lớp exception nội bộ nếu loại lỗi phụ thuộc runtime. Trong integration test, hãy xác định rõ mục tiêu là connection refused, timeout hay response bị đóng giữa chừng.

## 11. So sánh WebTestClient và WebClient khi gặp HTTP error

Hai API có cách sử dụng response khác nhau:

| API | Hành vi mặc định khi nhận 4xx/5xx |
|---|---|
| `WebTestClient.exchange()` | Trả response spec để test assertion status, header và body. |
| `WebClient.retrieve().bodyToMono(...)` | Mặc định chuyển status 4xx/5xx thành `WebClientResponseException` khi body được đọc qua retrieve pipeline. |
| `WebClient.exchangeToMono(...)` | Cho phép tự kiểm tra ClientResponse và quyết định cách xử lý status/body. |

Ví dụ WebClient:

~~~java
webClient.get()
    .uri("/items/999")
    .retrieve()
    .bodyToMono(Item.class)
    .onErrorResume(WebClientResponseException.NotFound.class, error -> Mono.empty());
~~~

Trong đoạn này, HTTP 404 được WebClient `retrieve()` chuyển thành exception chuyên biệt. Đây là hành vi của WebClient retrieval API, không có nghĩa server đã phát một Publisher `onError` từ response body. Server chỉ trả HTTP response 404; WebClient chọn biểu diễn status đó thành exception cho caller.

Khi dùng WebTestClient để kiểm thử endpoint, hãy kiểm tra status trực tiếp. Khi kiểm thử code client dùng WebClient, hãy kiểm tra cách client xử lý status response và body tương ứng.

## 12. Phân biệt lỗi của request body Publisher và response body Publisher

Reactive client cũng có thể gửi request body bằng Publisher. Nếu request body Publisher phát `onError` trong lúc gửi, lỗi xảy ra ở chiều client-to-server:

~~~java
client.post()
    .uri("/imports")
    .contentType(MediaType.APPLICATION_NDJSON)
    .body(Flux.concat(
        Flux.just(new ImportLine("A")),
        Flux.error(new IllegalStateException("upload stream failed"))
    ), ImportLine.class)
    .exchange();
~~~

Đây là lỗi khi client tạo/gửi request body. Server có thể đã nhận được một phần body, có thể hủy việc đọc hoặc có thể trả error response tùy thời điểm và connector. Không thể mặc định rằng client sẽ nhận được một HTTP 500.

Ngược lại, response body Publisher phát lỗi là lỗi ở chiều server-to-client. Hãy xác định Publisher nào đang lỗi trước khi phân tích log hoặc viết assertion.

| Hướng dữ liệu | Publisher thuộc về | Vị trí lỗi |
|---|---|---|
| Request body | Client gửi request | Khi encode hoặc gửi body lên server. |
| Response body | Server trả response | Khi serialize hoặc stream body xuống client. |
| Service Publisher | Logic ứng dụng phía server | Khi gọi dependency, truy vấn hoặc xử lý nghiệp vụ. |

Service Publisher error có thể trở thành response error nếu xảy ra trước commit và được framework xử lý. Nó cũng có thể trở thành response body stream error nếu xảy ra sau commit.

## 13. Chọn cách xử lý lỗi trong reactive pipeline

Không phải lỗi nào cũng nên biến thành HTTP 500. Hãy phân loại lỗi theo ý nghĩa:

| Loại lỗi | Xử lý thường phù hợp |
|---|---|
| Dữ liệu đầu vào không hợp lệ | Trả 400 với thông tin validation có kiểm soát. |
| Không tìm thấy tài nguyên | Trả 404. |
| Không có quyền truy cập | Trả 401 hoặc 403 theo ngữ cảnh xác thực. |
| Dependency upstream không khả dụng | Có thể trả 502 hoặc 503 theo hợp đồng API. |
| Lỗi lập trình không dự kiến | Để exception handler tạo 500 và ghi log đầy đủ ở server. |
| Lỗi có thể phục hồi trong stream | Dùng fallback phù hợp bằng onErrorResume hoặc retry có giới hạn. |
| Stream đã bắt đầu rồi mới lỗi | Thiết kế quy ước lỗi ở tầng stream hoặc chấp nhận terminal error; status đã commit không thể đổi. |

Ví dụ chuyển lỗi kỹ thuật thành lỗi nghiệp vụ:

~~~java
import java.util.concurrent.TimeoutException;

return upstreamClient.fetchItem(id)
    .onErrorMap(TimeoutException.class,
        error -> new UpstreamUnavailableException(
            "Inventory service timed out",
            error
        ));
~~~

Sau đó exception handler có thể ánh xạ lỗi:

~~~java
@ExceptionHandler(UpstreamUnavailableException.class)
ResponseEntity<ApiError> handleUpstreamUnavailable(
    UpstreamUnavailableException exception
) {
    return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
        .body(new ApiError("UPSTREAM_UNAVAILABLE", exception.getMessage()));
}
~~~

Việc chuyển lỗi nên giữ nguyên nguyên nhân gốc để log và quan sát hệ thống vẫn có đủ thông tin. Không đưa stack trace hoặc thông tin nhạy cảm nội bộ vào error body gửi client.

## 14. Các lỗi thường gặp khi viết test

### Nghĩ rằng mọi Publisher error đều là HTTP 500

Publisher error có thể được map thành 400, 404, 503 hoặc status khác; cũng có thể xảy ra sau khi response commit và không còn status để thay đổi. Hãy xác định thời điểm lỗi và exception mapping.

### Chỉ kiểm tra status mà bỏ qua body stream

Với response streaming, status 200 không đảm bảo body hoàn tất bình thường. Nếu body Publisher là một phần của hợp đồng, hãy lấy response body Publisher và dùng StepVerifier để kiểm tra các phần tử cùng terminal signal.

### Dùng StepVerifier để kiểm tra HTTP status

StepVerifier kiểm tra Reactive Streams signals. Nó không kiểm tra status, header hoặc HTTP serialization. Dùng WebTestClient cho HTTP response và StepVerifier cho Publisher.

### Dùng WebTestClient để suy luận nguyên nhân Publisher

Client có thể quan sát lỗi decode hoặc transport sau khi stream bị cắt. Lớp exception ở client không nhất thiết là exception gốc được phát từ server Publisher. Nếu cần xác nhận exception gốc, test Publisher/service trực tiếp bằng StepVerifier.

### Dùng doOnError rồi cho rằng lỗi đã được xử lý

`doOnError` chỉ quan sát lỗi. Publisher vẫn phát `onError`. Muốn phục hồi, dùng `onErrorResume`, `onErrorReturn` hoặc một toán tử phù hợp khác.

### Retry vô hạn hoặc fallback không đúng nghiệp vụ

Retry vô hạn có thể giữ request quá lâu và làm cạn tài nguyên. Fallback tùy tiện có thể khiến client nhận dữ liệu sai mà tưởng thành công. Đặt giới hạn retry, timeout và chính sách fallback theo hợp đồng nghiệp vụ.

### Mong muốn đổi status sau khi stream đã gửi dữ liệu

Khi response đã commit, status/header không thể thay đổi. Nếu cần truyền thông tin lỗi sau thời điểm đó, hãy biểu diễn nó trong giao thức stream hoặc kết thúc stream bằng lỗi có thể quan sát.

## 15. Ma trận kiểm thử gợi ý

| Kịch bản | Assertion chính | Công cụ |
|---|---|---|
| Tài nguyên không tồn tại | HTTP 404 và error body đúng schema. | WebTestClient `expectStatus`, `expectBody`. |
| Validation thất bại | HTTP 400 và field errors. | WebTestClient + JSONPath. |
| Publisher lỗi trước commit, được ánh xạ | Status do exception handler quy định. | WebTestClient. |
| Service Publisher phát lỗi cụ thể | Các giá trị trước lỗi và exception terminal. | StepVerifier. |
| Publisher được phục hồi | Fallback values và `onComplete`. | StepVerifier; WebTestClient cho response contract. |
| Streaming response lỗi sau commit | Status ban đầu, các giá trị đã nhận và body terminal error. | WebTestClient + StepVerifier. |
| Không kết nối được server | Không có HTTP status; exchange lỗi. | WebTestClient với server/connector thật. |
| Request body Publisher lỗi | Lỗi khi gửi request và hành vi server khi nhận body dở dang. | Integration test với client/server thật. |

Một test tốt chỉ nên khẳng định những gì tầng đang kiểm tra có thể quan sát. Test HTTP không cần biết mọi chi tiết nội bộ của service Publisher; test Publisher không cần dựng HTTP server nếu mục tiêu chỉ là kiểm tra tín hiệu reactive.

## 16. Quy trình phân tích khi test thất bại

Khi một test reactive thất bại, hãy lần lượt xác định:

1. **Có nhận được HTTP response không?** Nếu không, điều tra connection, timeout, TLS hoặc transport.
2. **Status code là gì?** Nếu nhận được 4xx/5xx, đây là HTTP response; kiểm tra exception mapping và error body.
3. **Body có phải Publisher/stream không?** Nếu có, kiểm tra terminal signal bằng StepVerifier hoặc body consumer thích hợp.
4. **Response đã commit trước khi lỗi xảy ra chưa?** Nếu đã commit, status không thể đổi; lỗi có thể chỉ xuất hiện khi client đọc body.
5. **Publisher error có được phục hồi không?** Kiểm tra `onErrorResume`, `onErrorReturn`, retry và các toán tử chuyển đổi.
6. **Test đang kiểm tra đúng tầng chưa?** Dùng WebTestClient cho HTTP, StepVerifier cho Publisher và integration test cho transport/container.

HTTP status mô tả response mà server đã gửi. Publisher `onError` mô tả cách một reactive stream kết thúc. Transport error mô tả việc giao tiếp không hoàn thành ở tầng kết nối. Phân biệt ba tầng này giúp xây dựng exception handling đúng và viết test WebFlux phản ánh chính xác hành vi mà client hoặc subscriber thực sự quan sát được.

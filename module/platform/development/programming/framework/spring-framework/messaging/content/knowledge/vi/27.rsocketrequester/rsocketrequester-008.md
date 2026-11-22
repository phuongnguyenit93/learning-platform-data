# Nhận luồng kết quả bằng `RSocketRequester.retrieveFlux()`

## Mục tiêu

Sau bài này, bạn có thể chọn `retrieveFlux()` khi một yêu cầu RSocket cần nhận nhiều kết quả, ghép đúng route với handler phía responder, tiêu thụ `Flux<T>` theo kiểu reactive và xử lý backpressure, hủy luồng, lỗi cùng kiểu dữ liệu trả về.

## 1. `retrieveFlux()` dùng để làm gì?

`RSocketRequester` là API fluent của Spring để gửi request qua RSocket bằng object Java thay vì tự thao tác với payload dạng byte buffer. `retrieveFlux(Class<T>)` khai báo kiểu dữ liệu của từng phần tử phản hồi và trả về `reactor.core.publisher.Flux<T>`.

RSocket có bốn interaction model thường gặp:

| Interaction | Dữ liệu gửi | Dữ liệu nhận | API requester thường dùng |
| --- | --- | --- | --- |
| Request-Response | Một message | Một message | `retrieveMono()` |
| Request-Stream | Một message | Nhiều message | `retrieveFlux()` |
| Request-Channel | Một luồng message | Một luồng message | `retrieveFlux()` |
| Fire-and-Forget | Một message | Không chờ phản hồi | `send()` |

Với trường hợp phổ biến của bài học, client gửi một object duy nhất và server trả về nhiều object. Spring chọn interaction **Request-Stream**. Cần nhớ rằng `retrieveFlux()` không phải lúc nào cũng là Request-Stream: nếu payload đầu vào được truyền dưới dạng một `Publisher` nhiều phần tử, Spring chọn **Request-Channel**. Loại interaction được suy ra từ số lượng phần tử đầu vào và đầu ra.

## 2. Gửi một request và nhận một stream

Ví dụ client gửi yêu cầu lấy báo giá cho mã `ACME`:

```java
Flux<Quote> quotes = requester
    .route("market.quotes")
    .data(new QuoteRequest("ACME"))
    .retrieveFlux(Quote.class);
```

Ý nghĩa từng bước:

1. `route("market.quotes")` đặt route vào metadata của request. Route phải khớp với route mà responder đăng ký.
2. `data(new QuoteRequest("ACME"))` đặt payload của request. Trong ví dụ này chỉ có một payload.
3. `retrieveFlux(Quote.class)` yêu cầu Spring giải mã mỗi response thành một object `Quote` và trả về `Flux<Quote>`.

Có thể tạo requester qua TCP như sau:

```java
RSocketRequester requester = RSocketRequester.builder()
    .tcp("localhost", 7000);
```

Việc gọi `tcp()` chuẩn bị requester; kết nối dùng chung được thiết lập khi request thực sự được thực thi và sau đó được tái sử dụng. Ứng dụng cũng có thể dùng WebSocket hoặc cấu hình `RSocketStrategies` khi cần codec hay metadata riêng.

## 3. Handler phía server

Route ở client phải khớp với `@MessageMapping` ở responder. Một handler tối giản có thể trả về `Flux<Quote>`:

```java
import java.time.Duration;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Flux;

@Controller
class QuoteController {

    @MessageMapping("market.quotes")
    Flux<Quote> quotes(QuoteRequest request) {
        return Flux.interval(Duration.ofSeconds(1))
            .take(5)
            .map(sequence -> new Quote(request.symbol(), sequence));
    }
}

record QuoteRequest(String symbol) {}
record Quote(String symbol, long sequence) {}
```

Handler nhận một `QuoteRequest` và phát ra tối đa năm `Quote`. Vì đầu vào là một payload còn đầu ra là nhiều phần tử, phương thức này xử lý Request-Stream. Mỗi phần tử của `Flux` được Spring mã hóa thành một response payload gửi về requester; khi stream kết thúc, phía client nhận tín hiệu complete.

Đây là đoạn minh họa cho handler trong một ứng dụng Spring đã cấu hình RSocket server và codec phù hợp. Nó không phải chương trình Java độc lập để chạy chỉ bằng `javac`.

## 4. Tiêu thụ kết quả ở client

Trong một chương trình dòng lệnh hoặc ví dụ kiểm thử, có thể chờ đến khi stream hoàn tất bằng `blockLast()`:

```java
requester.route("market.quotes")
    .data(new QuoteRequest("ACME"))
    .retrieveFlux(Quote.class)
    .doOnNext(System.out::println)
    .blockLast();
```

Với handler ở trên, output có dạng chính xác sau:

```text
Quote[symbol=ACME, sequence=0]
Quote[symbol=ACME, sequence=1]
Quote[symbol=ACME, sequence=2]
Quote[symbol=ACME, sequence=3]
Quote[symbol=ACME, sequence=4]
```

Trong ứng dụng reactive như WebFlux, nên trả `Flux<Quote>` cho tầng gọi tiếp theo để framework quản lý subscription. Tránh gọi `block()`, `blockFirst()` hoặc `blockLast()` trên event-loop vì thao tác đó chặn thread đang xử lý nhiều request.

Khi cần xử lý trực tiếp bằng callback, `subscribe()` trả về `Disposable`:

```java
Disposable subscription = requester.route("market.quotes")
    .data(new QuoteRequest("ACME"))
    .retrieveFlux(Quote.class)
    .take(10)
    .subscribe(
        quote -> log.info("quote={}", quote),
        error -> log.error("Stream failed", error),
        () -> log.info("Stream completed")
    );

// Khi không cần nhận tiếp dữ liệu:
subscription.dispose();
```

`take(10)` tự kết thúc sau mười phần tử và hủy subscription upstream. Có thể gọi `dispose()` khi vòng đời của màn hình, kết nối hoặc tác vụ kết thúc. Trong service reactive, thường nên trả publisher thay vì tự `subscribe()` bên trong, để caller kiểm soát vòng đời và lỗi.

## 5. Backpressure và hủy stream

`Flux` tuân theo Reactive Streams. Với Request-Stream và Request-Channel, tín hiệu demand được truyền qua ranh giới mạng: requester báo số phần tử đang cần, responder phải tôn trọng nhu cầu đó. Nhờ vậy client có thể điều tiết tốc độ nhận dữ liệu và tránh yêu cầu server phát vô hạn vào một bộ đệm không được kiểm soát.

Ví dụ giới hạn tốc độ yêu cầu từ phía client:

```java
Flux<Quote> quotes = requester.route("market.quotes")
    .data(new QuoteRequest("ACME"))
    .retrieveFlux(Quote.class)
    .limitRate(32);
```

`limitRate(32)` điều chỉnh cách downstream yêu cầu dữ liệu upstream theo từng đợt. Nó không thay thế việc thiết kế nguồn phát có khả năng tôn trọng backpressure. Nếu nguồn là hot publisher hoặc không thể giảm tốc, cần chọn chính sách rõ ràng như buffer có giới hạn, drop hoặc latest; tránh buffer không giới hạn vì có thể làm tăng bộ nhớ cho đến khi ứng dụng lỗi.

Các operator như `take(n)`, `take(Duration)` và việc dispose subscription giúp kết thúc luồng khi không còn nhu cầu. Hủy subscription cũng gửi tín hiệu cancel qua RSocket; nguồn phía responder có thể dừng công việc tương ứng nếu hỗ trợ cancellation.

Không nên gọi `collectList()` cho stream dài hoặc không giới hạn nếu mục tiêu là xử lý từng phần tử ngay khi nhận. `collectList()` phải giữ toàn bộ phần tử trong bộ nhớ và chỉ phát một `Mono<List<T>>` khi stream hoàn tất.

## 6. Phản hồi có kiểu generic

Khi response là một kiểu generic như `ApiEvent<Quote>`, `Class<T>` không giữ đủ tham số kiểu do type erasure của Java. Dùng overload nhận `ParameterizedTypeReference<T>`:

```java
Flux<ApiEvent<Quote>> events = requester.route("market.quote-events")
    .data(new QuoteRequest("ACME"))
    .retrieveFlux(new ParameterizedTypeReference<ApiEvent<Quote>>() {});
```

Import `org.springframework.core.ParameterizedTypeReference`. Cách này giữ được thông tin `ApiEvent<Quote>` để codec giải mã đúng kiểu lồng nhau.

## 7. Hoàn tất, lỗi và dữ liệu rỗng

- Nếu responder không phát phần tử nào rồi hoàn tất, client nhận một stream rỗng và tín hiệu `onComplete`; không có phần tử `null` đại diện cho kết quả rỗng.
- Nếu responder, kết nối hoặc quá trình giải mã gặp lỗi, `Flux` phát `onError` và kết thúc. Xử lý lỗi bằng các operator như `doOnError`, `onErrorResume` hoặc `retryWhen` tùy chính sách của ứng dụng.
- Chỉ retry khi thao tác có thể lặp an toàn. Một request được gửi lại có thể khiến server thực hiện lại công việc hoặc phát lại side effect.
- Với stream dài, xác định rõ điều kiện kết thúc, timeout cho khoảng thời gian không có dữ liệu nếu phù hợp, và cách giải phóng subscription khi caller rời đi.

Ví dụ dùng fallback cho một lỗi có thể phục hồi:

```java
Flux<Quote> quotes = requester.route("market.quotes")
    .data(new QuoteRequest("ACME"))
    .retrieveFlux(Quote.class)
    .onErrorResume(RecoverableQuoteException.class, error -> fallbackQuotes());
```

`fallbackQuotes()` phải trả về `Flux<Quote>`. Trong ứng dụng thực tế, chỉ xử lý loại lỗi đã xác định; không nên biến mọi lỗi thành stream rỗng vì điều đó có thể che giấu sự cố kết nối hoặc lỗi dữ liệu.

## 8. Codec và kiểu dữ liệu hai đầu

Tham số `Quote.class` hoặc `ParameterizedTypeReference` mô tả kiểu mong đợi ở phía nhận. Nó không tự định nghĩa cách tuần tự hóa payload. Requester và responder phải có encoder/decoder tương thích với định dạng dữ liệu và MIME type của kết nối.

Ở cấu hình Spring Framework cơ bản, các codec mặc định chủ yếu hỗ trợ `String`, `byte[]` và `ByteBuffer`. Để truyền DTO như `QuoteRequest` hoặc `Quote`, cần đăng ký encoder/decoder phù hợp, thường dùng Jackson JSON hoặc CBOR qua `RSocketStrategies`. Spring Boot có thể tự cấu hình codec khi có các dependency tương ứng. Nếu thiếu codec hoặc hai đầu dùng định dạng không tương thích, request có thể thất bại trong lúc encode/decode.

## 9. So sánh nhanh và lỗi thường gặp

| Tình huống | Cách xử lý |
| --- | --- |
| Một request, một response | Dùng `retrieveMono()` |
| Một request, nhiều response | Dùng `retrieveFlux()` với payload đơn |
| Nhiều request payload và có response stream | Dùng `retrieveFlux()` với input là `Publisher`; Spring chọn Request-Channel |
| Chỉ gửi message, không cần response | Dùng `send()` |

Các lỗi cần kiểm tra:

1. Dùng `retrieveMono()` khi server trả nhiều phần tử; kiểu tương tác và cardinality không khớp.
2. Route trong `route()` không khớp với `@MessageMapping` hoặc route được cấu hình ở responder.
3. Tạo `Flux` nhưng không trả nó cho caller và cũng không subscribe; khi không có subscriber, pipeline không được tiêu thụ.
4. Gọi `subscribe()` trong service rồi bỏ mất `Disposable`, khiến vòng đời và xử lý lỗi khó kiểm soát.
5. Nghĩ rằng mọi lần gọi `retrieveFlux()` đều là Request-Stream; đầu vào nhiều phần tử sẽ dẫn tới Request-Channel.
6. Dùng `Class` cho response generic rồi mong Java giữ lại kiểu tham số; hãy dùng `ParameterizedTypeReference`.
7. Gom một stream vô hạn bằng `collectList()` hoặc dùng buffer không giới hạn, làm tăng bộ nhớ.
8. Chỉ cấu hình codec ở client hoặc server mà quên đầu còn lại, khiến payload không giải mã được.

## 10. Tóm tắt

`retrieveFlux()` là lựa chọn để nhận một chuỗi response đã giải mã thành `Flux<T>`. Khi gửi một payload đơn, nó tạo Request-Stream: một request và nhiều response. Khi gửi input nhiều phần tử, nó tạo Request-Channel. Hãy để subscription điều khiển việc tiêu thụ, tận dụng backpressure, hủy stream khi không còn nhu cầu và cấu hình codec tương thích ở cả hai đầu.

## Tài liệu tham khảo

- [Spring Framework Reference — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring Framework Javadoc — RSocketRequester.RetrieveSpec](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.RetrieveSpec.html)

# Trình tự REQUEST_RESPONSE, PAYLOAD, COMPLETE và ERROR

RSocket dùng tương tác **request-response** khi bên gọi gửi một request và mong đợi tối đa một response. Trên wire, bên gọi mở tương tác bằng frame `REQUEST_RESPONSE`. Nếu xử lý thành công, bên nhận trả về frame `PAYLOAD`; cờ `COMPLETE` trong frame này đánh dấu tương tác đã kết thúc. Nếu xử lý thất bại, bên nhận gửi frame `ERROR` trên cùng stream ID.

Trong mô hình reactive của Java, request-response thường được biểu diễn bằng `Mono<T>`: publisher có thể phát tối đa một giá trị rồi hoàn tất, hoàn tất mà không có giá trị, hoặc kết thúc bằng lỗi. Hiểu cách các tín hiệu đó được ánh xạ thành frame giúp đọc log, xử lý timeout và thiết kế API RSocket chính xác.

## 1. Bốn khái niệm trong vòng đời request-response

| Tên | Vai trò | Hướng truyền thường gặp |
|---|---|---|
| `REQUEST_RESPONSE` | Frame mở đầu tương tác, mang payload request gồm data và metadata tùy chọn. | Requester → Responder |
| `PAYLOAD` | Frame mang payload response. Với request-response, response có tối đa một payload. | Responder → Requester |
| `COMPLETE` | Cờ trong frame `PAYLOAD`, báo rằng stream đã hoàn tất. Đây không phải một frame type độc lập. | Đi cùng `PAYLOAD` |
| `ERROR` | Frame terminal báo lỗi của stream, chứa mã lỗi và thông điệp lỗi. | Responder → Requester |

`REQUEST_RESPONSE` và `PAYLOAD` là hai loại frame khác nhau. Request ban đầu không phải là một `PAYLOAD` response. Sau khi nhận request, responder xử lý nghiệp vụ và gửi `PAYLOAD` để trả kết quả. Nếu có lỗi, responder gửi `ERROR` thay cho response thành công.

`COMPLETE` thường được nhắc cùng `PAYLOAD` vì nó là một cờ điều khiển nằm trong header của frame `PAYLOAD`. Không có frame type tên `COMPLETE` riêng trong trình tự request-response.

## 2. Trình tự thành công: REQUEST_RESPONSE → PAYLOAD + COMPLETE

Giả sử client yêu cầu báo giá mới nhất của mã `ACME`:

```text
Requester (Client)                       Responder (Server)
       |                                         |
       | REQUEST_RESPONSE, streamId=1           |
       | data={"symbol":"ACME"}                |
       |---------------------------------------->|
       |                                         |
       |                          xử lý request  |
       |                                         |
       | PAYLOAD, streamId=1                     |
       | flags: NEXT=1, COMPLETE=1               |
       | data={"symbol":"ACME","price":42.5}  |
       |<----------------------------------------|
       |                                         |
       | stream kết thúc                         |
```

Các bước diễn ra như sau:

1. Requester tạo một tương tác mới và cấp stream ID theo quy tắc của kết nối. Nếu requester là phía khởi tạo kết nối, ID thường thuộc dãy số lẻ; nếu server chủ động mở tương tác, ID thuộc dãy số chẵn.
2. Requester gửi `REQUEST_RESPONSE` cùng payload request. Payload có thể chứa data và metadata, chẳng hạn route metadata để Spring định tuyến đến handler.
3. Responder nhận frame, giải mã payload và gọi logic nghiệp vụ.
4. Khi có kết quả, responder gửi một frame `PAYLOAD` với cờ `NEXT` và `COMPLETE` được bật. `NEXT` cho biết frame mang một phần tử; `COMPLETE` cho biết không còn phần tử nào tiếp theo trong tương tác này.
5. Requester nhận payload, phát giá trị cho subscriber và kết thúc `Mono` bằng tín hiệu hoàn tất.

Response dùng **cùng stream ID** với frame `REQUEST_RESPONSE`. Responder không cấp một stream ID mới cho response, bởi response là phần còn lại của tương tác đã được requester mở.

Request-response chỉ có tối đa một response nên không cần frame `REQUEST_N` để yêu cầu thêm phần tử như request-stream. Nhu cầu nhận một response đã nằm trong chính kiểu tương tác `REQUEST_RESPONSE`.

## 3. PAYLOAD và cờ NEXT, COMPLETE

Frame `PAYLOAD` có thể mang data, metadata hoặc cả hai. Các cờ trong header cho biết frame có mang phần tử mới hay kết thúc stream:

| NEXT | COMPLETE | Ý nghĩa |
|---:|---:|---|
| `1` | `1` | Có một payload mới và stream kết thúc sau payload này. Đây là dạng response thành công phổ biến của request-response. |
| `1` | `0` | Có payload mới nhưng stream vẫn tiếp tục. Trạng thái này thường gặp ở request-stream hoặc request-channel, không phải response thông thường của request-response. |
| `0` | `1` | Stream hoàn tất mà không phát payload mới. Có thể dùng để biểu diễn kết quả rỗng. |
| `0` | `0` | Không có phần tử mới và cũng không có tín hiệu hoàn tất; không phải một frame terminal hữu ích cho response request-response. |

Với request-response, requester mong đợi tối đa một phần tử. Nếu responder có kết quả, `PAYLOAD` thường mang cả `NEXT` và `COMPLETE`. Nếu publisher phía responder hoàn tất mà không phát giá trị, tầng giao thức có thể báo hoàn tất mà không có `NEXT`; khi đó requester nhận một `Mono` rỗng.

Trong Reactor, ba trạng thái này tương ứng với ba kết quả khác nhau:

```java
// Một giá trị rồi hoàn tất.
Mono<Quote> found = Mono.just(new Quote("ACME", 42.5));

// Không có giá trị nhưng hoàn tất bình thường.
Mono<Quote> missing = Mono.empty();

// Kết thúc bằng lỗi.
Mono<Quote> failed = Mono.error(new QuoteServiceException("Price unavailable"));
```

`Mono.empty()` không đồng nghĩa với lỗi. Nếu nghiệp vụ cần phân biệt “không tìm thấy” với “request thất bại”, hãy quyết định rõ nên trả kết quả rỗng, một response DTO có trạng thái nghiệp vụ, hay một lỗi giao thức.

## 4. Trình tự lỗi: REQUEST_RESPONSE → ERROR

Nếu responder không thể xử lý request, nó có thể kết thúc stream bằng frame `ERROR`:

```text
Requester (Client)                       Responder (Server)
       |                                         |
       | REQUEST_RESPONSE, streamId=3           |
       | data={"symbol":"UNKNOWN"}             |
       |---------------------------------------->|
       |                                         |
       |                          xử lý request  |
       |                          phát hiện lỗi  |
       |                                         |
       | ERROR, streamId=3                       |
       | code=APPLICATION_ERROR                  |
       | message="Unknown symbol"               |
       |<----------------------------------------|
       |                                         |
       | stream kết thúc bằng onError            |
```

Frame `ERROR` mang mã lỗi và thông điệp mô tả. Với lỗi của một request-response cụ thể, `ERROR` dùng stream ID của request đã gây ra lỗi. Khi requester nhận được frame này, `Mono` kết thúc bằng `onError`; không có response `PAYLOAD` thành công theo sau trên cùng stream.

Một số mã lỗi thường gặp trong RSocket:

| Mã lỗi | Ý nghĩa khái quát |
|---|---|
| `APPLICATION_ERROR` | Ứng dụng hoặc handler gặp lỗi khi xử lý tương tác. |
| `REJECTED` | Request bị peer từ chối, ví dụ do chính sách hoặc giới hạn tiếp nhận. |
| `CANCELED` | Tương tác bị hủy. |
| `INVALID` | Frame hoặc nội dung tương tác không hợp lệ. |
| `CONNECTION_ERROR` | Lỗi ở phạm vi kết nối. |
| `CONNECTION_CLOSE` | Kết nối được đóng. |

Phải đọc cả loại frame và stream ID để xác định phạm vi lỗi. `ERROR` có stream ID khác `0` thường là lỗi của stream tương ứng; `ERROR` với stream ID `0` báo lỗi ở cấp kết nối và có thể ảnh hưởng nhiều tương tác đang chạy trên kết nối đó.

## 5. Phân biệt lỗi giao thức và lỗi nghiệp vụ trong response

Không phải mọi kết quả nghiệp vụ không mong muốn đều cần trở thành frame `ERROR`. Ví dụ, “không có báo giá cho mã này” có thể là một kết quả hợp lệ của truy vấn. Ứng dụng có thể chọn một trong hai cách:

**Cách 1: Trả response mô tả kết quả nghiệp vụ**

```java
public record QuoteResult(
    boolean found,
    Quote quote,
    String reason
) {}

Mono<QuoteResult> result = Mono.just(
    new QuoteResult(false, null, "UNKNOWN_SYMBOL"));
```

Requester nhận được một response bình thường; stream hoàn tất thành công. Caller đọc `found` hoặc `reason` để quyết định bước nghiệp vụ tiếp theo.

**Cách 2: Kết thúc tương tác bằng lỗi**

```java
Mono<Quote> result = Mono.error(
    new QuoteNotFoundException("Unknown symbol"));
```

Lỗi được truyền qua chuỗi reactive. Với Spring RSocket, lỗi thoát khỏi handler có thể được framework ánh xạ thành frame `ERROR` để peer nhận lỗi của tương tác.

Chọn response nghiệp vụ khi đó là một kết quả dự kiến mà client cần xử lý như một phần của luồng bình thường. Dùng lỗi khi request không thể được xử lý theo hợp đồng đã thống nhất, chẳng hạn dữ liệu đầu vào sai, không được phép hoặc dịch vụ phụ thuộc gặp sự cố. Hợp đồng API cần nhất quán để client không phải đoán một trạng thái có thể xuất hiện dưới cả response thành công lẫn lỗi giao thức.

## 6. Triển khai request-response với Spring RSocket

Ở phía server, handler thường trả về `Mono<T>`. Spring kết nối publisher này với tương tác RSocket đến và quản lý việc subscribe theo vòng đời request:

```java
@Controller
public class QuoteController {

    private final QuoteService quoteService;

    public QuoteController(QuoteService quoteService) {
        this.quoteService = quoteService;
    }

    @MessageMapping("quotes.latest")
    public Mono<Quote> latest(QuoteRequest request) {
        return quoteService.findLatest(request.symbol());
    }
}
```

Nếu `quoteService.findLatest(...)` phát một `Quote`, Spring gửi response payload và hoàn tất tương tác. Nếu publisher rỗng, tương tác hoàn tất mà không có phần tử. Nếu publisher phát lỗi, framework xử lý lỗi theo cơ chế RSocket của nó và gửi tín hiệu lỗi về requester.

Ở phía client, `RSocketRequester` xây dựng request-response publisher:

```java
public Mono<Quote> findLatest(String symbol) {
    return requester
        .route("quotes.latest")
        .data(new QuoteRequest(symbol))
        .retrieveMono(Quote.class);
}
```

`retrieveMono(Quote.class)` biểu diễn response tối đa một đối tượng `Quote`. Khi publisher được subscribe, requester thực hiện tương tác và nhận response hoặc lỗi. Nếu phương thức service trả `Mono` cho controller hoặc caller reactive, hãy để framework/caller quản lý subscription; tránh gọi `subscribe()` thủ công bên trong service vì khi đó lỗi và cancellation có thể tách khỏi vòng đời của request bên ngoài.

### Xử lý lỗi ở phía client

Client có thể chuyển lỗi giao thức thành lỗi miền ứng dụng hoặc áp dụng fallback:

```java
Mono<Quote> quote = requester
    .route("quotes.latest")
    .data(new QuoteRequest("ACME"))
    .retrieveMono(Quote.class)
    .onErrorMap(error -> new RemoteQuoteException(
        "Cannot retrieve quote", error));
```

Nếu cần fallback, hãy chỉ xử lý những lỗi mà ứng dụng có thể phục hồi:

```java
Mono<Quote> quote = requester
    .route("quotes.latest")
    .data(new QuoteRequest("ACME"))
    .retrieveMono(Quote.class)
    .onErrorResume(TimeoutException.class, error -> quoteCache.find("ACME"));
```

Không nên biến mọi lỗi thành `Mono.empty()` một cách mặc định. Cách đó có thể làm mất khác biệt giữa “không có dữ liệu”, “peer từ chối request”, “kết nối hỏng” và “server gặp lỗi”.

## 7. Hủy request-response và timeout

Requester có thể không còn cần kết quả trước khi responder trả lời, ví dụ người dùng rời màn hình hoặc request vượt quá thời gian chờ. Khi subscription bị hủy, RSocket có thể gửi frame `CANCEL` trên stream ID của tương tác đang chạy để báo cho peer dừng công việc nếu có thể.

```java
Mono<Quote> quote = requester
    .route("quotes.latest")
    .data(new QuoteRequest("ACME"))
    .retrieveMono(Quote.class)
    .timeout(Duration.ofSeconds(2));
```

Nếu timeout xảy ra trước khi có response, operator `timeout` phát lỗi timeout ở phía client và hủy subscription upstream. Tín hiệu hủy có thể được truyền tới RSocket để dừng tương tác. Tuy nhiên, nếu server đã hoàn tất xử lý hoặc response đang trên đường truyền, cancellation có thể đến quá muộn; ứng dụng không nên giả định rằng timeout ở client đồng nghĩa nghiệp vụ phía server chắc chắn chưa xảy ra.

Điều này đặc biệt quan trọng với request có side effect như tạo đơn hàng hoặc ghi giao dịch. Nếu client retry sau timeout, server có thể đã xử lý request đầu tiên nhưng response bị mất. Hãy cân nhắc idempotency key hoặc mã yêu cầu duy nhất ở tầng nghiệp vụ để tránh thực hiện side effect hai lần.

## 8. Thứ tự frame và stream ID khi đọc log

Stream ID được cấp bởi endpoint mở tương tác. Response và lỗi của tương tác đó dùng lại ID ban đầu:

```text
Client                                  Server
  |                                       |
  | REQUEST_RESPONSE (streamId=1) ------->|
  |                                       |
  |<------- PAYLOAD (streamId=1) ---------|  NEXT + COMPLETE
  |                                       |
```

Nếu server chủ động mở request-response hướng đến client, server cấp ID thuộc dãy của server (thường là số chẵn). Client trả `PAYLOAD` hoặc `ERROR` trên chính ID đó. Parity cho biết bên khởi tạo stream, không cho biết bên gửi frame response.

Khi xem log, hãy kiểm tra theo trình tự:

1. Tìm frame `REQUEST_RESPONSE` và ghi lại stream ID.
2. Xác định endpoint gửi request và payload đầu vào.
3. Tìm frame terminal cùng stream ID: `PAYLOAD` có `COMPLETE` hoặc `ERROR`.
4. Nếu là `PAYLOAD`, kiểm tra cờ `NEXT` để biết response có mang giá trị hay chỉ hoàn tất rỗng.
5. Nếu là `ERROR`, đọc error code và message; kiểm tra ID `0` hay ID của stream để xác định phạm vi.
6. Nếu không có frame terminal, kiểm tra timeout, cancellation, lỗi transport và trạng thái kết nối.

Ví dụ log:

```text
C -> S  REQUEST_RESPONSE  stream=1  route=quotes.latest
S -> C  PAYLOAD           stream=1  NEXT=true COMPLETE=true

C -> S  REQUEST_RESPONSE  stream=3  route=quotes.latest
S -> C  ERROR             stream=3  code=APPLICATION_ERROR

C -> S  REQUEST_RESPONSE  stream=5  route=quotes.latest
C -> S  CANCEL            stream=5
```

Trong ví dụ, stream `1` hoàn tất thành công; stream `3` kết thúc bằng lỗi; stream `5` bị requester hủy trước khi nhận kết quả. Mỗi tương tác có một stream ID riêng và không dùng chung ID của tương tác khác.

## 9. Kiểm thử kết quả và lỗi

Ở tầng ứng dụng, `StepVerifier` giúp kiểm tra ba kết quả chính của `Mono`: có giá trị rồi hoàn tất, hoàn tất rỗng và kết thúc bằng lỗi.

```java
StepVerifier.create(quoteService.findLatest("ACME"))
    .expectNextMatches(quote -> quote.symbol().equals("ACME"))
    .verifyComplete();
```

Kiểm tra trường hợp rỗng:

```java
StepVerifier.create(quoteService.findLatest("MISSING"))
    .verifyComplete();
```

Kiểm tra lỗi:

```java
StepVerifier.create(quoteService.findLatest("INVALID"))
    .expectError(QuoteServiceException.class)
    .verify();
```

Các kiểm thử này xác minh ngữ nghĩa reactive của service. Để kiểm tra việc ánh xạ sang frame RSocket, cần có kiểm thử tích hợp client-server: gửi request qua requester thật, xác minh response DTO, xác minh lỗi được nhận ở client và kiểm tra cancellation/timeout khi nghiệp vụ mất thời gian. Log frame hoặc packet capture có thể bổ sung bằng chứng về `REQUEST_RESPONSE`, `PAYLOAD`, cờ `COMPLETE` và `ERROR`.

## 10. Những lỗi thường gặp

| Cách hiểu hoặc cách làm sai | Hệ quả | Cách xử lý |
|---|---|---|
| Nghĩ `COMPLETE` là một frame type độc lập. | Đọc sai trình tự frame và log. | Xem `COMPLETE` là cờ trong frame `PAYLOAD`. |
| Cho rằng response dùng stream ID mới. | Không ghép được response với request ban đầu. | Dùng cùng stream ID cho `REQUEST_RESPONSE`, `PAYLOAD` và `ERROR` của tương tác. |
| Nghĩ request-response cần `REQUEST_N`. | Nhầm với cơ chế điều tiết của request-stream/request-channel. | Request-response vốn chỉ có tối đa một response nên không cần yêu cầu thêm phần tử. |
| Coi `Mono.empty()` là lỗi. | Client xử lý sai trường hợp không có kết quả. | Phân biệt hoàn tất rỗng với `onError`; xác định hợp đồng API cho trường hợp không tìm thấy. |
| Chuyển mọi exception thành response thành công. | Client không thể phân biệt lỗi xử lý với kết quả nghiệp vụ bình thường. | Chọn rõ response DTO hoặc lỗi giao thức theo hợp đồng. |
| Gọi `subscribe()` bên trong handler/service. | Subscription tách khỏi vòng đời request, lỗi và cancellation của caller. | Trả `Mono` cho Spring hoặc ghép các tác vụ bằng operator reactive. |
| Retry request có side effect mà không có idempotency. | Một thao tác có thể được thực hiện nhiều lần sau timeout hoặc mất response. | Dùng idempotency key và thiết kế thao tác có thể retry an toàn. |
| Xem timeout là bằng chứng server chưa xử lý. | Client có thể retry trong khi request đầu tiên đã được thực hiện. | Coi timeout là trạng thái không chắc chắn; đối soát bằng mã yêu cầu hoặc idempotency key. |

## Kết luận

Trong RSocket request-response, `REQUEST_RESPONSE` mở một tương tác và mang request payload. Khi thành công, responder trả một `PAYLOAD` trên cùng stream ID; cờ `NEXT` cho biết có response value và `COMPLETE` đánh dấu kết thúc. Khi thất bại, responder gửi `ERROR` trên stream đó để requester nhận `onError`. Ở Spring RSocket, `Mono` là biểu diễn tự nhiên cho ba kết quả: có một giá trị, hoàn tất rỗng hoặc lỗi. Nắm rõ sự khác nhau giữa payload, completion, error và cancellation giúp thiết kế hợp đồng API, xử lý timeout và chẩn đoán tương tác hai chiều đáng tin cậy.

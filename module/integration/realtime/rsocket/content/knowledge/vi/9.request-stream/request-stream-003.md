# Trình tự REQUEST_STREAM, PAYLOAD và REQUEST_N

RSocket dùng tương tác **request-stream** khi bên gọi gửi một request và mong đợi nhận về một chuỗi gồm không hoặc nhiều kết quả. Trên wire, bên gọi mở tương tác bằng frame `REQUEST_STREAM`. Frame này mang payload request và lượng dữ liệu ban đầu mà bên gọi sẵn sàng nhận. Responder gửi từng phần tử bằng frame `PAYLOAD`; khi cần nhận thêm, requester gửi frame `REQUEST_N` để cấp thêm demand.

Đây là cơ chế backpressure ở cấp giao thức. Nó giúp bên nhận điều tiết tốc độ phát dữ liệu của bên gửi theo khả năng tiêu thụ hiện tại. Trong Java, request-stream thường được biểu diễn bằng `Flux<T>` của Reactor: subscriber yêu cầu dữ liệu, xử lý từng phần tử và có thể hủy subscription khi không còn cần luồng.

## 1. Ba frame chính trong request-stream

| Frame | Vai trò | Hướng truyền trong request-stream thông thường |
|---|---|---|
| `REQUEST_STREAM` | Mở một stream mới, mang request payload và initial request N. | Requester → Responder |
| `PAYLOAD` | Mang một phần tử response; cờ `NEXT` cho biết có phần tử mới, cờ `COMPLETE` cho biết stream đã kết thúc. | Responder → Requester |
| `REQUEST_N` | Yêu cầu responder phát thêm một số lượng payload. | Requester → Responder |

Mỗi tương tác có một stream ID khác `0`. `REQUEST_STREAM`, các frame `PAYLOAD` và các frame `REQUEST_N` của tương tác đó đều dùng cùng stream ID. Responder không cấp ID mới cho từng phần tử trả về.

`REQUEST_N` không mang dữ liệu nghiệp vụ. Nó chỉ cập nhật lượng demand còn được phép phát. Ngược lại, `PAYLOAD` mang nội dung thực tế của response. Việc tách frame dữ liệu khỏi frame điều khiển giúp hai phía quản lý luồng độc lập với nội dung ứng dụng.

## 2. Trình tự tổng thể: REQUEST_STREAM → PAYLOAD → REQUEST_N

Giả sử client yêu cầu server gửi các báo giá của mã `ACME`. Ban đầu, client sẵn sàng nhận hai phần tử:

```text
Requester (Client)                         Responder (Server)
       |                                           |
       | REQUEST_STREAM, streamId=1, initialN=2   |
       | data={"symbol":"ACME"}                  |
       |------------------------------------------>|
       |                                           |
       |                         xử lý request    |
       |                                           |
       | PAYLOAD, streamId=1, NEXT=1               |
       |<------------------------------------------|
       | PAYLOAD, streamId=1, NEXT=1               |
       |<------------------------------------------|
       |                                           |
       | REQUEST_N, streamId=1, n=3                |
       |------------------------------------------>|
       |                                           |
       | PAYLOAD, streamId=1, NEXT=1               |
       |<------------------------------------------|
       | PAYLOAD, streamId=1, NEXT=1               |
       |<------------------------------------------|
       | PAYLOAD, streamId=1, NEXT=1, COMPLETE=1   |
       |<------------------------------------------|
       |                                           |
       | stream kết thúc                           |
```

Trình tự có thể diễn giải thành các bước:

1. Requester tạo stream mới, cấp stream ID và gửi `REQUEST_STREAM` cùng request payload.
2. `REQUEST_STREAM` chứa trường **initial request N**, cho biết số payload ban đầu mà requester cho phép responder gửi.
3. Responder bắt đầu xử lý request và phát các phần tử bằng `PAYLOAD`. Mỗi payload có cờ `NEXT` tiêu thụ một đơn vị demand.
4. Khi requester cần nhận thêm dữ liệu, nó gửi `REQUEST_N` với số lượng bổ sung `n`.
5. Responder có thể phát thêm tối đa số payload được cấp bởi demand mới, đồng thời tuân thủ demand còn lại từ trước.
6. Khi hết dữ liệu, responder đánh dấu hoàn tất bằng cờ `COMPLETE` trong frame `PAYLOAD`. Stream cũng có thể kết thúc bằng `ERROR` nếu xử lý thất bại.

Trong ví dụ, initial request N là `2`, nên responder được phép gửi hai payload đầu tiên. Sau khi requester gửi `REQUEST_N(n=3)`, responder có thêm quyền gửi ba payload. Payload cuối cùng vừa mang một phần tử (`NEXT=1`) vừa kết thúc stream (`COMPLETE=1`).

## 3. Initial request N trong REQUEST_STREAM

Khác với `REQUEST_RESPONSE`, frame `REQUEST_STREAM` có trường số lượng phần tử ban đầu. Trường này thường được gọi là `initialRequestN` hoặc `initialN` trong API và tài liệu triển khai.

```text
REQUEST_STREAM frame
+----------------------+--------------------------+
| Stream ID            | Frame type / flags       |
+----------------------+--------------------------+
| Initial request N    | Payload (data/metadata)  |
+----------------------+--------------------------+
```

Initial request N là lượng demand ban đầu, tính theo **số payload response**, không phải số byte, số packet TCP hay thời gian chờ. Giá trị này phải lớn hơn `0` theo quy tắc của request-stream. Sau khi dùng hết demand ban đầu, requester gửi `REQUEST_N` để cấp thêm.

Ví dụ, nếu initial N bằng `5`, responder có thể phát tối đa năm payload có `NEXT` trước khi cần thêm demand. Nếu requester chỉ cần ba kết quả, nó có thể hủy stream sau phần tử thứ ba; responder không cần chờ gửi hết năm phần tử.

Initial N và các lần `REQUEST_N` tiếp theo cùng tạo thành lượng demand tích lũy của stream. Mỗi lần requester gửi `REQUEST_N(n)`, nó cấp thêm `n` payload; đây không phải là giá trị demand tổng mới thay thế lượng demand cũ.

## 4. REQUEST_N cấp thêm demand như thế nào?

`REQUEST_N` là frame điều khiển flow control. Nó chứa số lượng payload bổ sung mà requester cho phép responder gửi trên stream tương ứng.

```text
REQUEST_N frame
+----------------------+--------------------------+
| Stream ID            | Frame type / flags       |
+----------------------+--------------------------+
| N (additional demand)|                          |
+----------------------+--------------------------+
```

Các quy tắc cần nhớ:

- `n` phải là số dương. `REQUEST_N(n=0)` không phải cách báo tạm dừng stream.
- Mỗi `PAYLOAD` có cờ `NEXT` tiêu thụ một đơn vị demand.
- Nhiều lần `REQUEST_N` cộng dồn vào demand còn lại; chúng cấp thêm quyền phát, không đặt lại bộ đếm về một giá trị tuyệt đối.
- `REQUEST_N` dùng stream ID của request-stream đã mở. Nó không tạo stream mới.
- Demand áp dụng cho từng stream. Một requester có thể cấp demand khác nhau cho nhiều stream đồng thời.

Ví dụ với initial N bằng `2`:

| Sự kiện | Demand được cấp thêm | Payload đã phát | Demand còn lại |
|---|---:|---:|---:|
| Gửi `REQUEST_STREAM(initialN=2)` | 2 | 0 | 2 |
| Responder gửi payload thứ nhất | 0 | 1 | 1 |
| Responder gửi payload thứ hai | 0 | 1 | 0 |
| Gửi `REQUEST_N(n=3)` | 3 | 0 | 3 |
| Responder gửi thêm hai payload | 0 | 2 | 1 |
| Responder gửi payload cuối và COMPLETE | 0 | 1 | 0, stream kết thúc |

Đây là cách nhìn theo demand của ứng dụng. Một implementation có thể có buffer hoặc prefetch nội bộ, nhưng trên giao thức responder vẫn phải tuân thủ lượng payload được requester cho phép.

## 5. PAYLOAD, NEXT và COMPLETE

Frame `PAYLOAD` mang data, metadata hoặc cả hai. Hai cờ `NEXT` và `COMPLETE` xác định ý nghĩa của frame trong vòng đời stream:

| NEXT | COMPLETE | Ý nghĩa |
|---:|---:|---|
| `1` | `0` | Có một phần tử mới; stream tiếp tục. |
| `1` | `1` | Có một phần tử mới và stream kết thúc ngay sau phần tử đó. |
| `0` | `1` | Stream hoàn tất mà không phát thêm phần tử. |
| `0` | `0` | Không có phần tử mới và cũng chưa kết thúc; không phải tín hiệu dữ liệu hữu ích thông thường. |

Với stream có nhiều phần tử, các frame giữa luồng thường dùng `NEXT=1, COMPLETE=0`. Phần tử cuối có thể dùng `NEXT=1, COMPLETE=1`. Một cách biểu diễn khác là gửi phần tử cuối với `NEXT=1, COMPLETE=0`, rồi gửi frame hoàn tất riêng với `NEXT=0, COMPLETE=1`.

Nếu publisher hoàn tất mà không phát phần tử nào, responder có thể gửi tín hiệu hoàn tất mà không có `NEXT`. Khi đó requester nhận một `Flux` hoàn tất rỗng. `COMPLETE` là cờ trong frame `PAYLOAD`, không phải một frame type độc lập.

`ERROR` là tín hiệu terminal khác với `COMPLETE`. Khi stream kết thúc bằng lỗi, responder gửi frame `ERROR` trên stream ID đó; requester nhận `onError` thay vì `onComplete`.

## 6. Backpressure trong Reactive Streams và RSocket

Reactive Streams mô tả nhu cầu dữ liệu bằng `Subscription.request(n)`. RSocket ánh xạ nhu cầu đó sang cơ chế flow control của giao thức:

```text
Subscriber của ứng dụng
        |
        | request(n)
        v
Reactor Flux / các operator
        |
        | demand được runtime chuyển thành initialN / REQUEST_N
        v
RSocket requester  ====================>  RSocket responder
                                               |
                                               | phát PAYLOAD theo demand
                                               v
                                         Flux phía server
```

Ở phía client, subscriber quyết định lượng dữ liệu nó sẵn sàng xử lý. Reactor truyền demand ngược qua các operator. RSocket runtime dùng demand đó để tạo initial N hoặc `REQUEST_N`. Ở phía server, demand được chuyển tới publisher trả về từ handler để publisher phát dữ liệu phù hợp.

Backpressure giúp tránh việc responder đẩy vô hạn dữ liệu đến một requester đang xử lý chậm. Nó không phải cam kết về tốc độ theo giây; nó là giới hạn số phần tử được phép phát tại một thời điểm. Ngoài ra, flow control của RSocket hoạt động theo từng stream, trong khi TCP có cơ chế cửa sổ và điều tiết byte riêng ở tầng transport.

Không nên đồng nhất `request(n)` ở một operator với đúng một frame `REQUEST_N(n)` trên wire. Các operator có thể yêu cầu theo lô hoặc prefetch, và runtime có thể gộp hoặc chuyển demand theo cách phù hợp. Điều cần đảm bảo là tổng payload có `NEXT` được phát không vượt quá demand hợp lệ.

## 7. Triển khai request-stream với Spring RSocket

Ở phía server, handler thường trả về `Flux<T>`. Spring gắn publisher này với request-stream đến và quản lý subscription theo vòng đời tương tác:

```java
@Controller
public class QuoteController {

    private final QuoteService quoteService;

    public QuoteController(QuoteService quoteService) {
        this.quoteService = quoteService;
    }

    @MessageMapping("quotes.stream")
    public Flux<Quote> stream(QuoteRequest request) {
        return quoteService.stream(request.symbol());
    }
}
```

Handler trả về `Flux<Quote>` để Spring chuyển từng phần tử thành response payload. Không gọi `subscribe()` bên trong handler; framework cần sở hữu subscription để điều phối demand, lỗi và cancellation từ client.

Ở phía client, `RSocketRequester` tạo publisher request-stream:

```java
public Flux<Quote> streamQuotes(String symbol) {
    return requester
        .route("quotes.stream")
        .data(new QuoteRequest(symbol))
        .retrieveFlux(Quote.class);
}
```

`retrieveFlux(Quote.class)` biểu diễn một chuỗi kết quả. Khi subscriber đăng ký và yêu cầu dữ liệu, RSocket runtime mở tương tác và quản lý initial request N cùng các lần cấp thêm demand. Ứng dụng làm việc với `Flux` mà không cần tự tạo frame `REQUEST_STREAM` hoặc `REQUEST_N`.

## 8. Điều khiển demand từ subscriber

Các overload `subscribe()` tiện dụng thường yêu cầu dữ liệu không giới hạn. Nếu cần quan sát rõ backpressure, có thể dùng `BaseSubscriber` để yêu cầu từng phần tử:

```java
BaseSubscriber<Quote> subscriber = new BaseSubscriber<>() {
    @Override
    protected void hookOnSubscribe(Subscription subscription) {
        request(1);
    }

    @Override
    protected void hookOnNext(Quote quote) {
        processQuote(quote);
        request(1);
    }

    @Override
    protected void hookOnError(Throwable error) {
        log.error("Quote stream failed", error);
    }

    @Override
    protected void hookOnComplete() {
        log.info("Quote stream completed");
    }
};

streamQuotes("ACME").subscribe(subscriber);

// Khi người dùng rời màn hình hoặc không còn cần dữ liệu:
subscriber.dispose();
```

Subscriber yêu cầu một phần tử khi bắt đầu. Sau khi xử lý xong phần tử hiện tại, nó yêu cầu thêm một phần tử. Demand đi qua Reactor và RSocket runtime để điều tiết responder. Khi gọi `dispose()`, subscription bị hủy và runtime có thể gửi `CANCEL` cho stream đang hoạt động.

Nếu muốn xử lý theo lô, subscriber có thể yêu cầu nhiều phần tử sau mỗi lần xử lý:

```java
request(32);
```

Điều này cấp thêm demand cho 32 payload. Hãy chọn kích thước lô theo thời gian xử lý, bộ nhớ và độ trễ mà ứng dụng chấp nhận.

## 9. Giới hạn tốc độ, buffer và nguồn hot

Trong một pipeline reactive, các operator có thể thay đổi cách demand được truyền lên upstream:

```java
Flux<Quote> quotes = quoteService.stream("ACME")
    .limitRate(64)
    .map(this::enrichQuote);
```

`limitRate(64)` điều chỉnh cách Reactor chia nhỏ demand thành các đợt yêu cầu upstream. Đây là công cụ điều tiết hữu ích khi xử lý luồng lớn; con số `64` không nên được hiểu là cam kết mỗi frame wire sẽ có đúng `REQUEST_N(n=64)`.

Một số nguồn hot có thể phát độc lập với demand của subscriber. Khi kết nối một nguồn như vậy vào pipeline, cần chọn chính sách khi bên nhận xử lý chậm:

```java
// Giữ tối đa 100 phần tử đang chờ; khi đầy, overflow theo chính sách đã chọn.
Flux<Event> buffered = hotEvents.onBackpressureBuffer(100);

// Bỏ các phần tử mới khi downstream không theo kịp.
Flux<Event> dropping = hotEvents.onBackpressureDrop();

// Chỉ giữ giá trị mới nhất trong khi downstream đang bận.
Flux<Event> latest = hotEvents.onBackpressureLatest();
```

Các chính sách buffer/drop/latest có ngữ nghĩa nghiệp vụ khác nhau. Buffer cần giới hạn dung lượng và cách xử lý overflow; drop có thể làm mất sự kiện; latest bỏ qua các giá trị trung gian. Với dữ liệu tài chính, giao dịch hoặc sự kiện không được mất, cần thiết kế lưu trữ/đọc lại hoặc cơ chế xác nhận riêng thay vì âm thầm bỏ phần tử.

## 10. Hoàn tất, lỗi và hủy stream

Một request-stream có thể kết thúc theo ba cách chính:

- **Hoàn tất bình thường:** responder gửi `PAYLOAD` có cờ `COMPLETE`, có thể kèm phần tử cuối (`NEXT=1`) hoặc không (`NEXT=0`). Client nhận `onComplete`.
- **Lỗi:** responder gửi `ERROR` trên stream ID tương ứng. Client nhận `onError`; các stream độc lập khác trên cùng kết nối có thể tiếp tục nếu đây chỉ là lỗi stream.
- **Hủy:** requester không còn cần dữ liệu và hủy subscription. Runtime có thể gửi frame `CANCEL` để responder dừng việc phát dữ liệu hoặc giải phóng tài nguyên.

Ví dụ giới hạn stream ở client:

```java
Flux<Quote> firstTen = requester
    .route("quotes.stream")
    .data(new QuoteRequest("ACME"))
    .retrieveFlux(Quote.class)
    .take(10);
```

`take(10)` hoàn tất downstream sau tối đa mười phần tử và hủy upstream. Điều này giúp dừng stream khi caller chỉ cần một phần dữ liệu đầu tiên. Responder nên xử lý cancellation để ngừng truy vấn, đóng tài nguyên hoặc dừng công việc nền khi có thể.

Không nên giả định cancellation luôn ngăn được side effect đã bắt đầu. Nếu publisher đã thực hiện ghi dữ liệu hoặc gửi lệnh đến hệ thống khác, hủy subscription không tự động hoàn tác nghiệp vụ đó.

## 11. Stream ID và nhiều request-stream đồng thời

Mỗi request-stream có stream ID riêng trên kết nối. Endpoint khởi tạo stream cấp ID theo dãy của mình; với kết nối được thiết lập bởi client, client thường dùng ID lẻ và server dùng ID chẵn khi chủ động mở tương tác. Các frame `PAYLOAD`, `REQUEST_N`, `CANCEL` hoặc `ERROR` của một stream giữ nguyên ID đó.

Nhiều stream có thể chạy đồng thời và frame của chúng xen kẽ nhau trên cùng kết nối:

```text
Client                                  Server
  |                                       |
  | REQUEST_STREAM (id=1, initialN=2) --->|
  | REQUEST_STREAM (id=3, initialN=1) --->|
  |                                       |
  |<--------- PAYLOAD (id=3) -------------|
  |<--------- PAYLOAD (id=1) -------------|
  |<--------- PAYLOAD (id=1) -------------|
  |                                       |
  | REQUEST_N (id=3, n=4) --------------->|
```

Demand của stream `1` không cấp quyền phát cho stream `3`. Mỗi stream có bộ đếm demand và vòng đời độc lập. Vì vậy, khi phân tích log, luôn ghép `REQUEST_N` với stream ID tương ứng thay vì cộng demand của cả kết nối.

## 12. Kiểm thử backpressure và vòng đời stream

Ở tầng Reactor, `StepVerifier` có thể kiểm tra thứ tự phần tử và việc subscriber yêu cầu theo từng đợt:

```java
Flux<Integer> source = Flux.range(1, 5);

StepVerifier.create(source, 0)
    .thenRequest(2)
    .expectNext(1, 2)
    .thenRequest(3)
    .expectNext(3, 4, 5)
    .verifyComplete();
```

Ví dụ này xác minh publisher tuân thủ demand ở tầng Reactive Streams. Nó không tự chứng minh chính xác frame `REQUEST_N` nào đã đi qua mạng; để kiểm tra wire protocol, cần kiểm thử tích hợp requester-responder hoặc quan sát frame bằng công cụ logging/packet capture phù hợp.

Nên có các trường hợp kiểm thử sau:

1. Subscriber yêu cầu một phần tử mỗi lần và nhận dữ liệu theo đúng thứ tự.
2. Subscriber yêu cầu theo lô; publisher không phát vượt quá demand.
3. Publisher hoàn tất sau một số phần tử và client nhận `onComplete`.
4. Publisher phát lỗi và client nhận `onError` trên đúng stream.
5. Client hủy subscription; server dừng publisher hoặc giải phóng tài nguyên liên quan.
6. Hai hoặc nhiều stream chạy đồng thời; demand và cancellation của stream này không ảnh hưởng stream khác.
7. Nguồn hot vượt quá khả năng tiêu thụ; chính sách buffer/drop/latest hoạt động đúng giới hạn đã cấu hình.

## 13. Những lỗi thường gặp

| Cách hiểu hoặc cách làm sai | Hệ quả | Cách xử lý |
|---|---|---|
| Nhầm initial request N với số byte cần nhận. | Cấp demand sai và hiểu sai kích thước dữ liệu. | Initial N đếm số payload response, không đếm byte. |
| Nghĩ `REQUEST_N(n)` đặt tổng demand thành `n`. | Có thể đánh giá thấp hoặc cao lượng dữ liệu còn được phép gửi. | `REQUEST_N` cấp thêm `n` đơn vị demand. |
| Gửi `REQUEST_N` với `n=0`. | Không tạo ra một yêu cầu dữ liệu hợp lệ. | Dùng số dương; hủy stream nếu muốn dừng nhận. |
| Nghĩ `REQUEST_N` mở một stream mới. | Ghép sai frame và stream ID. | Dùng stream ID của `REQUEST_STREAM` ban đầu. |
| Coi `COMPLETE` là frame riêng. | Đọc sai wire sequence. | `COMPLETE` là cờ của `PAYLOAD`. |
| Nghĩ `Flux` tự động tạo backpressure đúng cho mọi nguồn. | Nguồn hot hoặc operator buffer có thể tích lũy dữ liệu, tràn bộ nhớ hoặc bỏ sự kiện. | Chọn chính sách demand, buffer và overflow có giới hạn. |
| Gọi `subscribe()` bên trong handler. | Framework mất quyền kiểm soát demand, lỗi và cancellation của stream. | Trả `Flux` cho Spring quản lý. |
| Không xử lý cancellation ở publisher dài hạn. | Tác vụ nền, subscription hoặc tài nguyên có thể tiếp tục chạy. | Dùng operator cleanup và kiểm tra tín hiệu cancel. |
| Cộng demand giữa nhiều stream. | Một stream có thể phát vượt quá giới hạn riêng. | Theo dõi demand theo từng stream ID. |

## 14. Cách đọc log REQUEST_STREAM

Khi một stream bị treo, phát thiếu phần tử hoặc phát quá nhanh, hãy kiểm tra lần lượt:

1. Tìm `REQUEST_STREAM`, ghi lại stream ID, request payload và initial N.
2. Đếm các frame `PAYLOAD` có `NEXT=1` để theo dõi số demand đã tiêu thụ.
3. Tìm các frame `REQUEST_N` cùng stream ID và cộng lượng demand bổ sung.
4. So sánh tổng demand với số payload responder đã phát; kiểm tra có frame nào vượt quá demand hay không.
5. Kiểm tra frame terminal: `PAYLOAD` có `COMPLETE`, `ERROR` hoặc `CANCEL`.
6. Nếu stream không tiến triển, kiểm tra subscriber có yêu cầu thêm dữ liệu hay đang giữ demand ở một operator downstream.
7. Nếu stream tiêu thụ bộ nhớ tăng dần, kiểm tra prefetch, buffer, nguồn hot và chính sách overflow.

Ví dụ log rút gọn:

```text
C -> S  REQUEST_STREAM  stream=1 initialN=2
S -> C  PAYLOAD         stream=1 NEXT=true COMPLETE=false
S -> C  PAYLOAD         stream=1 NEXT=true COMPLETE=false
C -> S  REQUEST_N       stream=1 n=3
S -> C  PAYLOAD         stream=1 NEXT=true COMPLETE=false
S -> C  PAYLOAD         stream=1 NEXT=true COMPLETE=false
S -> C  PAYLOAD         stream=1 NEXT=true COMPLETE=true
```

Requester đã cấp tổng cộng năm payload: hai từ initial N và ba từ `REQUEST_N`. Responder phát đúng năm payload, trong đó payload cuối kết thúc stream. Đây là trình tự hợp lệ về demand.

## Kết luận

Trong request-stream, `REQUEST_STREAM` mở tương tác và mang initial request N; `PAYLOAD` truyền từng phần tử; `REQUEST_N` cấp thêm demand khi requester muốn nhận tiếp. Mỗi payload có `NEXT` tiêu thụ một đơn vị demand, còn `COMPLETE` đánh dấu kết thúc stream. Cơ chế này kết nối backpressure của Reactive Streams với flow control của RSocket. Khi triển khai bằng Spring, hãy trả `Flux` từ handler, để framework quản lý subscription, chọn chính sách buffer có giới hạn cho nguồn không thể điều tiết và xử lý cancellation để giải phóng tài nguyên. Hiểu đúng demand theo từng stream giúp hệ thống truyền realtime ổn định khi số lượng dữ liệu và tốc độ tiêu thụ thay đổi.

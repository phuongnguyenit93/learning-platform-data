# Thời hạn chờ phản hồi và hủy yêu cầu

Trong giao tiếp realtime, một yêu cầu không nên chờ vô hạn. Dịch vụ đích có thể xử lý chậm, mất kết nối hoặc không phát phản hồi. Nếu client tiếp tục giữ request, stream và tài nguyên liên quan, số lượng yêu cầu đang chờ có thể tăng lên và làm hệ thống quá tải.

RSocket hỗ trợ hủy một tương tác đang hoạt động bằng frame **CANCEL**. Trong ứng dụng Java dùng Reactor, thao tác hủy thường bắt đầu khi subscriber hủy subscription hoặc một operator như **timeout** kết thúc việc chờ và hủy nguồn upstream. Để sử dụng đúng cơ chế này, cần thiết kế thời hạn chờ ở cả client và server, hiểu cách cancellation lan truyền, đồng thời biết rằng hủy giao tiếp không đồng nghĩa với rollback nghiệp vụ.

## 1. Vì sao cần giới hạn thời gian chờ?

Một request-response thường đi qua nhiều bước: client gửi request, server nhận và giải mã payload, xác thực, gọi service hoặc database, tạo response rồi gửi về client. Bất kỳ bước nào cũng có thể kéo dài hơn dự kiến.

Nếu client không có timeout, request có thể giữ tài nguyên trong thời gian rất lâu:

- Subscription và trạng thái stream vẫn còn tồn tại.
- Bộ nhớ được giữ bởi request, response hoặc các closure liên quan.
- Kết nối tới database hoặc dịch vụ downstream có thể bị chiếm dụng.
- Người dùng phải chờ mà không biết thao tác còn tiến triển hay đã bị treo.
- Khi tải tăng, số request đang chờ có thể làm cạn thread, connection pool hoặc bộ nhớ.

Timeout đặt ra giới hạn thời gian mà một bên sẵn sàng chờ. Khi hết thời hạn, bên đó dừng chờ và có thể yêu cầu hủy tương tác đang hoạt động.

## 2. Phân biệt timeout, deadline và cancellation

Ba khái niệm có liên quan nhưng không giống nhau:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Timeout | Khoảng thời gian tối đa một thao tác được phép chờ | Chờ response tối đa 2 giây |
| Deadline | Thời điểm tuyệt đối mà thao tác phải hoàn tất | Request phải xong trước 10:30:05 UTC |
| Cancellation | Tín hiệu dừng một công việc hoặc tương tác đang hoạt động | Client không còn cần response và gửi CANCEL |

Timeout thường được tính từ lúc bắt đầu subscribe hoặc gửi request. Deadline thể hiện ngân sách thời gian còn lại của toàn bộ nghiệp vụ, có thể bao gồm nhiều lần gọi dịch vụ.

Ví dụ, một API gateway có tổng ngân sách 3 giây. Nó đã dùng 1 giây để xác thực và xử lý bước đầu, nên request RSocket downstream chỉ còn khoảng 2 giây. Nếu mỗi tầng tự đặt timeout 3 giây, tổng thời gian có thể vượt quá ngân sách ban đầu.

RSocket cung cấp cơ chế hủy stream, nhưng deadline nghiệp vụ xuyên nhiều dịch vụ cần được ứng dụng quy ước và truyền đi, chẳng hạn qua metadata. Không nên giả định một giá trị timeout tùy ý trong metadata là trường deadline chuẩn mà mọi RSocket peer tự động hiểu.

## 3. Timeout ở phía client với Reactor

Với Mono, operator **timeout(Duration)** phát lỗi TimeoutException nếu nguồn không phát tín hiệu trong thời hạn đã đặt. Khi timeout xảy ra, operator hủy subscription của nguồn upstream.

Ví dụ client gọi một route request-response:

~~~java
import java.time.Duration;
import reactor.core.publisher.Mono;

public Mono<OrderDetails> findOrder(String orderId) {
    return requester
        .route("orders.find")
        .data(orderId)
        .retrieveMono(OrderDetails.class)
        .timeout(Duration.ofSeconds(2));
}
~~~

Trong ví dụ này, client chờ tối đa 2 giây. Nếu response đến trước thời hạn, Mono phát kết quả bình thường. Nếu không, client nhận TimeoutException và Reactor hủy nguồn upstream.

Có thể ghi nhận việc nguồn bị hủy để quan sát hành vi:

~~~java
public Mono<OrderDetails> findOrder(String orderId) {
    return requester
        .route("orders.find")
        .data(orderId)
        .retrieveMono(OrderDetails.class)
        .doOnCancel(() -> log.debug(
            "RSocket request cancelled: {}", orderId))
        .timeout(Duration.ofSeconds(2));
}
~~~

Khi timeout, operator timeout hủy subscription của retrieveMono; doOnCancel đặt ở upstream sẽ quan sát được tín hiệu hủy. Trong tích hợp RSocket, việc hủy subscription của một request đang hoạt động được chuyển thành cơ chế hủy stream của giao thức.

### Trả về fallback khi timeout

Một số nghiệp vụ có thể dùng dữ liệu cache nếu dịch vụ chính phản hồi quá chậm:

~~~java
public Mono<OrderDetails> findOrder(String orderId) {
    Mono<OrderDetails> remote = requester
        .route("orders.find")
        .data(orderId)
        .retrieveMono(OrderDetails.class);

    return remote.timeout(
        Duration.ofSeconds(2),
        Mono.defer(() -> cache.findOrder(orderId))
    );
}
~~~

Khi timeout, Reactor hủy nguồn remote và chuyển sang publisher fallback. Fallback cũng cần có giới hạn thời gian và xử lý lỗi riêng. Không nên dùng cache cho dữ liệu cần tính nhất quán tức thời nếu nghiệp vụ không cho phép kết quả cũ.

### Xử lý riêng lỗi timeout

Có thể phân biệt timeout với lỗi khác để trả thông điệp phù hợp:

~~~java
return requester
    .route("orders.find")
    .data(orderId)
    .retrieveMono(OrderDetails.class)
    .timeout(Duration.ofSeconds(2))
    .onErrorMap(
        TimeoutException.class,
        ex -> new OrderServiceTimeoutException(orderId, ex)
    );
~~~

Không nên biến mọi lỗi thành timeout hoặc trả stack trace nội bộ cho client. Timeout, lỗi ứng dụng từ server, lỗi kết nối và lỗi giải mã có ý nghĩa khác nhau; giữ chúng riêng giúp retry và giám sát chính xác hơn.

## 4. Timeout cho stream khác timeout cho một response đơn

Với Flux, cách hiểu timeout cần được chú ý. Operator **timeout(Duration)** theo dõi thời gian chờ tín hiệu tiếp theo: nếu không có phần tử mới trong khoảng thời gian đó, stream phát TimeoutException và hủy upstream.

~~~java
Flux<PriceUpdate> prices = requester
    .route("prices.stream")
    .data("ACME")
    .retrieveFlux(PriceUpdate.class)
    .timeout(Duration.ofSeconds(5));
~~~

Ví dụ này đặt giới hạn 5 giây cho khoảng im lặng giữa các tín hiệu. Nếu thị trường không có cập nhật trong hơn 5 giây, stream sẽ timeout, dù kết nối vẫn hoạt động.

Đây không phải giới hạn tổng thời lượng stream. Nếu stream có dữ liệu đều đặn mỗi 2 giây, nó có thể chạy hàng giờ mà không timeout.

Nếu muốn giới hạn tổng thời gian theo dõi, có thể dùng **take(Duration)**:

~~~java
Flux<PriceUpdate> firstMinute = requester
    .route("prices.stream")
    .data("ACME")
    .retrieveFlux(PriceUpdate.class)
    .take(Duration.ofMinutes(1));
~~~

take(Duration) kết thúc stream sau một phút và hủy upstream. Nó hoàn tất bình thường theo ngữ nghĩa của Reactor, trong khi timeout(Duration) phát lỗi timeout nếu không có tín hiệu đúng hạn.

Cần chọn theo nghiệp vụ:

- Request-response: timeout thường là tổng thời gian chờ một response.
- Request-stream: timeout có thể là thời gian tối đa chờ giữa hai phần tử hoặc deadline tổng của phiên.
- Request-channel: cần cân nhắc thời hạn cho từng hướng, thời hạn tổng và cách đóng một phía.
- Heartbeat/keepalive: kiểm tra sức khỏe kết nối, không thay thế timeout nghiệp vụ cho từng request.

## 5. Hủy yêu cầu hoạt động thế nào trong RSocket?

Mỗi tương tác RSocket có Stream ID. Khi một peer không còn cần tương tác đang chạy, nó có thể gửi frame **CANCEL** với Stream ID tương ứng. Peer còn lại nhận được tín hiệu và nên dừng công việc liên quan đến stream đó.

Một request-stream có thể diễn ra như sau:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as RSocket Server
    C->>S: REQUEST_STREAM
    S-->>C: PAYLOAD 1
    S-->>C: PAYLOAD 2
    Note over C: Timeout hoặc người dùng dừng theo dõi
    C->>S: CANCEL (Stream ID)
    Note over S: Hủy publisher và giải phóng tài nguyên
~~~

Trong ứng dụng Reactor, Subscription.cancel() là tín hiệu ở tầng Reactive Streams. Thư viện RSocket kết nối tín hiệu đó với frame CANCEL của stream đang hoạt động.

Cancellation có thể xảy ra khi:

- Client gọi dispose() hoặc hủy subscription.
- Operator timeout hết thời hạn.
- Operator take đã nhận đủ số phần tử hoặc hết thời gian.
- Người dùng đóng màn hình hoặc dừng một thao tác.
- Một bước xử lý downstream không còn quan tâm tới kết quả.

CANCEL kết thúc tương tác tương ứng. Nó không đóng toàn bộ kết nối RSocket; các stream khác trên cùng phiên vẫn có thể tiếp tục.

## 6. Server cần phản ứng với cancellation

Server nên xây dựng publisher có khả năng dừng khi subscription bị hủy. Với Reactor, có thể quan sát cancellation bằng doOnCancel hoặc mọi tín hiệu kết thúc bằng doFinally.

~~~java
@MessageMapping("reports.stream")
public Flux<ReportRow> streamReport(ReportQuery query) {
    return reportService.streamRows(query)
        .doOnCancel(() -> log.info(
            "Report stream cancelled: {}", query.reportId()))
        .doFinally(signal -> log.debug(
            "Report stream finished: {}", signal));
}
~~~

Khi client gửi CANCEL, subscription phía server được hủy. Một publisher reactive hợp tác sẽ dừng phát phần tử mới và giải phóng tài nguyên mà nó sở hữu.

### Cancellation không tự dừng mọi công việc

Nếu handler đã gọi một API blocking, khởi chạy một tác vụ ngoài Reactor hoặc gửi lệnh đến một hệ thống không hỗ trợ hủy, cancellation có thể không dừng được công việc đó.

Ví dụ, nếu một thread đang thực thi truy vấn blocking và thư viện database không hỗ trợ hủy, việc client gửi CANCEL không đảm bảo truy vấn dừng ngay. Tương tự, một email đã gửi hoặc một giao dịch đã commit không tự được thu hồi chỉ vì requester không còn chờ response.

Để cancellation có hiệu quả:

- Ưu tiên API non-blocking và publisher hỗ trợ cancellation.
- Truyền tín hiệu hủy tới client database hoặc HTTP downstream nếu thư viện hỗ trợ.
- Dừng vòng lặp phát dữ liệu khi nhận cancellation.
- Giải phóng cursor, file handle, buffer và tài nguyên tạm.
- Không bắt và bỏ qua cancellation như một lỗi nghiệp vụ thông thường.
- Với tác vụ dài hạn không thể hủy ngay, kiểm tra cờ hủy tại các điểm an toàn.

## 7. Timeout ở phía server

Client timeout bảo vệ thời gian chờ của người gọi. Server cũng cần giới hạn thời gian cho công việc nội bộ, vì một client có thể không đặt timeout hoặc kết nối bị mất mà không được phát hiện ngay.

Ví dụ, server giới hạn thời gian truy vấn:

~~~java
@MessageMapping("orders.find")
public Mono<OrderDetails> findOrder(String orderId) {
    return orderService.findOrder(orderId)
        .timeout(Duration.ofSeconds(3))
        .doOnCancel(() -> log.debug(
            "Order lookup cancelled: {}", orderId));
}
~~~

Nếu service không phát tín hiệu trong 3 giây, publisher server-side phát lỗi timeout. Framework sẽ ánh xạ lỗi đó thành lỗi tương tác RSocket theo cơ chế xử lý lỗi đã cấu hình. Cần chuẩn hóa mã lỗi và thông điệp trả về để không làm lộ chi tiết nội bộ.

Timeout server không thay thế timeout client. Hai phía có mục tiêu khác nhau:

- Client giới hạn thời gian người gọi chờ.
- Server giới hạn thời gian tài nguyên được dùng để xử lý request.
- Downstream database hoặc HTTP client cần timeout riêng phù hợp với ngân sách còn lại.

## 8. Truyền deadline qua nhiều dịch vụ

Một request có thể đi qua gateway, service A, service B và database. Nếu mỗi tầng bắt đầu một timeout mới mà không tính thời gian đã dùng, tổng thời gian có thể vượt quá mức người dùng chấp nhận.

Có thể dùng deadline tuyệt đối hoặc thời gian còn lại trong metadata ứng dụng. Ví dụ:

1. Gateway tạo deadline 5 giây kể từ lúc nhận request.
2. Sau 1 giây, gateway gọi service A và truyền thời gian còn lại là 4 giây.
3. Service A dùng 1,5 giây, còn 2,5 giây trước khi gọi service B.
4. Service B không được tự cấp lại toàn bộ 5 giây; nó phải tôn trọng ngân sách còn lại.

Nếu truyền deadline tuyệt đối, các máy cần đồng bộ đồng hồ đủ tốt. Nếu truyền thời gian còn lại, cần trừ thời gian đã tiêu thụ ở mỗi hop và tránh kéo dài ngân sách do sai lệch đồng hồ hoặc xử lý metadata không nhất quán.

Metadata deadline là hợp đồng ở cấp ứng dụng. Hãy quy định đơn vị, định dạng, giá trị tối đa, cách xử lý giá trị thiếu hoặc không hợp lệ và không tin dữ liệu deadline từ peer chưa được phép gọi route.

## 9. Phân biệt timeout, CANCEL, COMPLETE và ERROR

Các tín hiệu này biểu đạt trạng thái khác nhau:

| Tín hiệu | Ý nghĩa | Hành động thường thấy |
|---|---|---|
| Timeout phía client | Client đã chờ quá lâu | Báo timeout cục bộ và hủy request upstream |
| CANCEL | Một peer yêu cầu dừng stream đang hoạt động | Peer kia hủy publisher và dọn tài nguyên |
| COMPLETE | Một hướng stream hoàn tất bình thường | Đóng hướng phát dữ liệu đó |
| ERROR | Tương tác kết thúc do lỗi | Chuyển lỗi cho subscriber và dọn tài nguyên |

Timeout không phải là một frame RSocket độc lập. Nó là chính sách thời gian ở tầng ứng dụng hoặc thư viện. Khi timeout khiến subscription bị hủy, RSocket có thể truyền việc hủy đó bằng CANCEL.

CANCEL không đồng nghĩa với ERROR: bên hủy chỉ nói rằng nó không còn cần stream. COMPLETE biểu thị hoàn tất bình thường. ERROR biểu thị kết thúc do lỗi.

Trong request-channel, COMPLETE từ một phía có thể chỉ kết thúc hướng gửi của phía đó; hướng còn lại vẫn có thể hoạt động. CANCEL hủy tương tác theo Stream ID, nên cần phân biệt việc một phía hoàn tất gửi với việc toàn bộ tương tác bị hủy.

## 10. Retry sau timeout và tính idempotent

Một timeout không cho biết chắc chắn server đã thực hiện nghiệp vụ hay chưa. Có thể server chưa nhận request, đang xử lý, đã commit thay đổi nhưng response bị trễ, hoặc response đã gửi nhưng client không nhận được.

Vì vậy, retry một lệnh ghi có thể tạo tác dụng phụ lặp lại. Ví dụ, client tạo thanh toán, hết timeout rồi gửi lại; nếu server đã ghi nhận lần đầu, lần thứ hai có thể tạo giao dịch trùng.

Với thao tác có tác dụng phụ:

- Dùng idempotency key hoặc request ID duy nhất.
- Lưu kết quả xử lý gắn với key để request lặp có thể nhận lại kết quả cũ.
- Phân biệt lỗi có thể retry với lỗi validation hoặc authorization.
- Dùng exponential backoff và jitter để tránh nhiều client retry đồng thời.
- Đặt tổng deadline cho cả chuỗi retry.
- Chỉ retry tự động khi nghiệp vụ cho phép.

Cancellation cũng không rollback một giao dịch đã commit. Nếu cần hủy một thao tác đã bắt đầu, hãy thiết kế một lệnh nghiệp vụ riêng, có kiểm tra trạng thái và quy tắc bù trừ.

## 11. Kiểm thử timeout và cancellation

Có thể dùng Reactor Test để xác nhận timeout và cancellation mà không phải chờ thời gian thực.

### Kiểm thử timeout

~~~java
StepVerifier.withVirtualTime(() ->
        Mono.<String>never().timeout(Duration.ofSeconds(3)))
    .expectSubscription()
    .thenAwait(Duration.ofSeconds(3))
    .expectError(TimeoutException.class)
    .verify();
~~~

Virtual time giúp kiểm tra operator timeout nhanh và ổn định. Bài test xác nhận nguồn không phát tín hiệu trong thời hạn sẽ tạo lỗi timeout.

### Kiểm thử cancellation

~~~java
AtomicBoolean cancelled = new AtomicBoolean();

Mono<String> source = Mono.<String>never()
    .doOnCancel(() -> cancelled.set(true));

StepVerifier.create(source)
    .thenCancel()
    .verify();

assertThat(cancelled).isTrue();
~~~

Bài test này xác nhận subscriber hủy thì publisher quan sát được cancellation.

### Kiểm thử tích hợp RSocket

Ở mức tích hợp client/server, nên kiểm tra thêm:

1. Client gọi request-response và nhận response trước timeout.
2. Server không phản hồi; client timeout và server quan sát cancellation nếu stream còn hoạt động.
3. Client hủy request-stream sau một số phần tử; server dừng phát.
4. Server timeout ở một downstream call; client nhận lỗi đã chuẩn hóa.
5. Kết nối bị đóng khi request đang chạy; tài nguyên được dọn dẹp.
6. Một thao tác đã commit trước khi timeout; retry với cùng idempotency key không tạo tác dụng phụ lần hai.
7. Nhiều request cùng timeout; hệ thống không giữ lại subscription, buffer hoặc connection không cần thiết.

## 12. Checklist thiết kế thời hạn chờ

Trước khi đưa route vào production, hãy xác định:

- Timeout mặc định và timeout tối đa của route.
- Deadline tổng của nghiệp vụ và cách truyền ngân sách qua metadata.
- Timeout riêng cho database và dịch vụ downstream.
- Hành vi khi timeout: trả lỗi, dùng cache hay fallback.
- Publisher nào có thể quan sát và thực hiện cancellation.
- Tài nguyên nào phải giải phóng khi client hủy hoặc disconnect.
- Những thao tác nào cần idempotency key trước khi retry.
- Metrics cho timeout, cancellation, request đang chạy và thời gian xử lý.
- Log có correlation ID nhưng không chứa dữ liệu nhạy cảm.

## 13. Kết luận

Timeout giới hạn thời gian chờ; deadline quản lý ngân sách thời gian xuyên suốt nghiệp vụ; cancellation yêu cầu dừng một tương tác đang hoạt động. Trong RSocket, CANCEL kết thúc stream theo Stream ID. Trong Reactor, timeout, take, dispose hoặc việc hủy subscription có thể kích hoạt tín hiệu cancellation và truyền xuống publisher RSocket.

Để hệ thống realtime ổn định, hãy đặt timeout phù hợp ở client, server và các dịch vụ downstream; thiết kế publisher có khả năng hủy; giải phóng tài nguyên đúng lúc; và dùng idempotency cho các thao tác có tác dụng phụ. Luôn nhớ rằng client ngừng chờ không chứng minh server chưa thực hiện nghiệp vụ, nên timeout, cancellation và retry phải được thiết kế cùng nhau.


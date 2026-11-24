# Xử lý bên nhận chậm, gián đoạn và lỗi giữa luồng

Một request-stream có thể hoạt động trong thời gian dài và phát ra nhiều phần tử. Trong thực tế, consumer có thể xử lý chậm hơn tốc độ producer, kết nối có thể bị gián đoạn hoặc một lỗi nghiệp vụ có thể xuất hiện sau khi stream đã phát một số phần tử. Nếu không có chính sách rõ ràng, hệ thống dễ tích lũy dữ liệu trong bộ nhớ, làm mất cập nhật hoặc kết thúc stream theo cách khó dự đoán.

RSocket cung cấp flow control dựa trên demand để điều tiết số payload được gửi; Reactive Streams và Reactor truyền tín hiệu nhu cầu qua pipeline. Tuy vậy, backpressure không tự giải quyết mọi tình huống: nguồn phát có thể không dừng được, ứng dụng vẫn có thể tạo buffer nội bộ, và lỗi hoặc mất kết nối vẫn cần chiến lược xử lý. Bài học này trình bày cách thiết kế consumer chậm, xử lý gián đoạn và quyết định nên tiếp tục, khôi phục hay bắt đầu lại một stream.

## 1. Vì sao consumer có thể bị chậm?

Consumer là thành phần nhận và xử lý các phần tử của stream. Tốc độ xử lý có thể giảm vì:

- Mỗi phần tử cần truy vấn database hoặc gọi dịch vụ bên ngoài.
- Một tác vụ tính toán tiêu tốn CPU hoặc bộ nhớ.
- Nhiều stream cùng chia sẻ thread, connection pool hoặc scheduler.
- Consumer xử lý tuần tự trong khi producer phát dữ liệu theo burst.
- Mạng hoặc thiết bị phía client có thông lượng thấp.
- Một phần tử lớn hoặc phức tạp mất nhiều thời gian giải mã và xử lý.

Giả sử producer phát 1.000 sự kiện/giây trong khi consumer chỉ xử lý được 600 sự kiện/giây. Nếu mọi sự kiện tiếp tục được nhận và xếp hàng, backlog tăng khoảng 400 sự kiện mỗi giây. Sau 30 giây, có thể có khoảng 12.000 sự kiện đang chờ. Bộ nhớ tăng và dữ liệu được xử lý ngày càng muộn.

Mục tiêu không chỉ là giữ cho kết nối còn mở. Hệ thống cần kiểm soát lượng công việc đang chờ, biết khi nào phải giảm tốc, và xác định rõ điều gì xảy ra khi không thể theo kịp.

## 2. Demand và backpressure giúp điều tiết stream

Trong Reactive Streams, subscriber yêu cầu số phần tử nó sẵn sàng nhận bằng Subscription.request(n). Publisher chỉ được phát trong phạm vi tổng demand chưa được đáp ứng.

RSocket áp dụng cơ chế flow control này cho request-stream. Khi requester mở stream, nó gửi initial request N; sau đó có thể gửi REQUEST_N để cấp thêm nhu cầu. Responder chỉ được phát số payload nằm trong lượng demand đã cấp.

~~~mermaid
sequenceDiagram
    participant C as Consumer
    participant R as RSocket Responder
    C->>R: REQUEST_STREAM (initial N = 2)
    R-->>C: PAYLOAD 1
    R-->>C: PAYLOAD 2
    Note over C: Xử lý hai phần tử
    C->>R: REQUEST_N (N = 1)
    R-->>C: PAYLOAD 3
    Note over C: Chưa yêu cầu thêm
~~~

Khi consumer xử lý chậm và chưa yêu cầu thêm phần tử, responder phải chờ demand mới. Điều này giúp áp lực từ downstream truyền ngược về upstream, giảm việc gửi dữ liệu mà consumer chưa sẵn sàng nhận.

Với request-channel, hai peer có thể cùng gửi stream. Demand được quản lý cho từng hướng dữ liệu; consumer ở mỗi phía điều tiết lượng payload mà phía kia gửi đến. Một hướng tạm ngừng yêu cầu không nhất thiết kết thúc hướng còn lại.

Backpressure hoạt động tốt khi các thành phần trong pipeline tuân thủ demand. Nếu nguồn là callback, cảm biến hoặc thư viện không thể tạm dừng, cần một chính sách ở ranh giới nhận dữ liệu như buffer hữu hạn, lấy mẫu hoặc loại bỏ phần tử.

## 3. Buffer và chính sách khi consumer không theo kịp

Buffer giữ tạm các phần tử đã được nhận nhưng chưa được xử lý. Nó hữu ích để hấp thụ burst ngắn, nhưng không làm tăng năng lực xử lý lâu dài của consumer.

Nếu tốc độ đầu vào trung bình luôn lớn hơn tốc độ xử lý, mọi buffer hữu hạn cuối cùng đều có thể đầy. Vì vậy, cần quyết định trước hành vi khi đầy.

| Chính sách | Hành vi | Khi phù hợp |
|---|---|---|
| Backpressure | Giảm hoặc tạm dừng phát theo demand | Nguồn phát có thể tuân thủ demand |
| Buffer hữu hạn | Giữ phần tử trong giới hạn, overflow thì báo lỗi hoặc áp dụng handler | Burst ngắn, cần giữ dữ liệu trong một khoảng giới hạn |
| Drop | Bỏ một số phần tử khi consumer không theo kịp | Dữ liệu trung gian có thể mất |
| Latest | Chỉ giữ giá trị mới nhất trong lúc downstream bận | Trạng thái hiện tại quan trọng hơn lịch sử |
| Sample/window | Lấy mẫu hoặc gom nhóm dữ liệu theo thời gian | Telemetry tần suất cao, dashboard |
| Durable queue/log | Ghi sự kiện vào hệ thống lưu trữ bền vững | Cần đọc lại sau khi consumer gián đoạn |

Ví dụ, dashboard hiển thị nhiệt độ hiện tại thường có thể bỏ các giá trị trung gian và chỉ giữ giá trị mới nhất. Ngược lại, sự kiện thanh toán hoặc audit không được âm thầm loại bỏ; cần backpressure, lưu bền vững hoặc một cơ chế xác nhận và xử lý lại.

### Buffer hữu hạn trong Reactor

Có thể đặt giới hạn cho buffer và xử lý overflow:

~~~java
Flux<Reading> readings = sensorSource
    .onBackpressureBuffer(
        1_000,
        overflowed -> log.warn("Buffer overflow at event: {}", overflowed)
    );
~~~

Với overload này, callback được gọi khi buffer tràn và luồng kết thúc bằng lỗi overflow. Nó không âm thầm bỏ phần tử rồi tiếp tục. Nếu nghiệp vụ cho phép drop và tiếp tục, hãy chọn operator hoặc overload có chính sách drop rõ ràng, đồng thời ghi nhận số phần tử bị loại. Callback cũng không thay thế việc lưu lại sự kiện ở một nguồn bền vững nếu nghiệp vụ yêu cầu không mất dữ liệu.

Với nguồn phát không thể bị điều tiết, operator onBackpressureBuffer có thể hấp thụ chênh lệch trong giới hạn đã đặt. Nếu nguồn tiếp tục phát vượt quá tốc độ xử lý, buffer sẽ đầy và ứng dụng phải thực hiện chính sách đã chọn.

### Giữ trạng thái mới nhất

Với dữ liệu mà chỉ giá trị gần nhất có ý nghĩa:

~~~java
Flux<Temperature> latestTemperature = sensorSource
    .onBackpressureLatest();
~~~

Operator này giữ giá trị mới nhất khi downstream chưa sẵn sàng nhận. Các giá trị trung gian có thể bị bỏ. Không dùng cách này cho sự kiện mà mỗi phần tử đều có ý nghĩa nghiệp vụ.

### Điều tiết theo lô và giới hạn công việc đồng thời

limitRate chia demand thành các lô nhỏ hơn khi truyền upstream:

~~~java
Flux<Event> events = eventSource
    .limitRate(128);
~~~

limitRate điều tiết số phần tử được yêu cầu theo lô, không phải giới hạn tốc độ theo giây. Nếu cần giới hạn 100 sự kiện/giây, phải dùng rate limiter hoặc cơ chế điều tiết theo thời gian.

Nếu mỗi sự kiện cần ghi database và phải giữ thứ tự, có thể xử lý tuần tự:

~~~java
Flux<WriteResult> results = events
    .concatMap(event -> repository.save(event), 32);
~~~

concatMap đợi tác vụ hiện tại hoàn tất trước khi xử lý tác vụ tiếp theo. Prefetch giới hạn lượng phần tử lấy trước để chờ xử lý. Nếu cho phép xử lý song song, có thể dùng flatMap với concurrency giới hạn và cân nhắc thứ tự kết quả.

## 4. Tránh tạo backlog ở những ranh giới bất đồng bộ

Ngay cả khi RSocket flow control hoạt động đúng, ứng dụng vẫn có thể tích lũy queue trong pipeline. Các vị trí thường gặp:

- publishOn chuyển xử lý sang scheduler khác và có hàng đợi cùng prefetch.
- flatMap giữ nhiều publisher con và kết quả đang chờ.
- buffer và window gom phần tử theo số lượng hoặc thời gian.
- Client database, HTTP hoặc executor có queue riêng.
- Bộ giải mã, transport và ứng dụng có thể giữ các bản sao của payload.

Ví dụ, publishOn có thể tách tốc độ đọc và tốc độ xử lý:

~~~java
Flux<EnrichedEvent> enriched = incoming
    .publishOn(Schedulers.parallel(), 64)
    .map(this::enrich);
~~~

Prefetch 64 giới hạn lượng phần tử được lấy trước tại ranh giới này theo cơ chế của operator. Nếu công việc trong map quá nặng hoặc scheduler bị nghẽn, cần theo dõi queue và latency. Tăng prefetch không làm tăng năng lực xử lý thực tế.

Nên đo tổng số phần tử đang chờ và kích thước byte của chúng. Giới hạn theo số phần tử chưa đủ nếu payload có kích thước rất khác nhau.

## 5. Phân biệt lỗi của một phần tử với lỗi kết thúc stream

Trong Reactive Streams, onError là tín hiệu terminal: sau khi publisher phát lỗi, stream đó không tiếp tục phát thêm phần tử. RSocket biểu đạt lỗi của tương tác bằng frame ERROR theo Stream ID.

Điều này khác với trường hợp một phần tử có dữ liệu không hợp lệ nhưng stream vẫn có thể tiếp tục. Ứng dụng cần quyết định lỗi đó là lỗi của cả stream hay chỉ là kết quả thất bại của một sự kiện.

| Tình huống | Cách biểu diễn phù hợp |
|---|---|
| Kết nối database bị lỗi, không thể tiếp tục stream | Kết thúc stream bằng lỗi |
| Một bản ghi sai định dạng, các bản ghi sau vẫn xử lý được | Trả kết quả lỗi cho riêng phần tử hoặc bỏ qua có ghi nhận |
| Người gọi không có quyền truy cập stream | Từ chối tương tác |
| Nguồn dữ liệu đã phát hết | Hoàn tất bình thường |
| Client không còn cần dữ liệu | Hủy stream |

Nếu cần tiếp tục sau lỗi của một phần tử, có thể biểu diễn kết quả theo từng sự kiện:

~~~java
public record EventResult(
    String eventId,
    boolean successful,
    String errorCode
) {}
~~~

Sau đó xử lý lỗi trong từng tác vụ con thay vì để lỗi thoát ra toàn bộ Flux:

~~~java
Flux<EventResult> results = incomingEvents
    .flatMap(event ->
        process(event)
            .map(result -> new EventResult(
                event.id(), true, null))
            .onErrorResume(ex -> Mono.just(
                new EventResult(
                    event.id(), false, classify(ex))))
    , 8);
~~~

Trong ví dụ này, lỗi của một lần process được chuyển thành EventResult thất bại; stream ngoài có thể tiếp tục với phần tử sau. Cần giới hạn concurrency và quyết định rõ thứ tự xử lý nếu thứ tự sự kiện có ý nghĩa.

## 6. Xử lý lỗi giữa stream bằng Reactor

Khi lỗi thực sự làm publisher kết thúc, Reactor cung cấp các operator để chọn cách phản ứng. Không có một cách xử lý phù hợp với mọi lỗi.

### Chuyển sang nguồn dự phòng

~~~java
Flux<Quote> quotes = primaryQuoteFeed()
    .onErrorResume(error -> {
        log.warn("Primary quote feed failed", error);
        return backupQuoteFeed();
    });
~~~

onErrorResume đăng ký publisher dự phòng sau khi nguồn chính phát lỗi. Nguồn dự phòng có thể phát dữ liệu tiếp tục cho subscriber, nhưng không có nghĩa stream gốc đã được nối lại từ đúng vị trí bị ngắt. Nếu cần không mất dữ liệu, phải có cursor, sequence hoặc nguồn lưu trữ có thể đọc lại.

### Chuyển lỗi thành giá trị

~~~java
Mono<Quote> quote = loadQuote(symbol)
    .onErrorReturn(Quote.unavailable(symbol));
~~~

Cách này phù hợp khi có giá trị thay thế rõ ràng. Không nên biến mọi lỗi thành dữ liệu mặc định nếu điều đó che giấu lỗi hệ thống hoặc làm client hiểu nhầm dữ liệu là chính xác.

### Retry có giới hạn

~~~java
Flux<Quote> quotes = quoteFeed()
    .retryWhen(
        Retry.backoff(3, Duration.ofMillis(200))
            .maxBackoff(Duration.ofSeconds(2))
            .filter(this::isTransientFailure)
    );
~~~

Retry chỉ nên áp dụng cho lỗi tạm thời có thể phục hồi. Với request-stream, retry có thể tạo subscription mới và bắt đầu một stream mới. Nếu không có resume token, sequence hoặc cursor, dữ liệu đã nhận trước lỗi có thể bị phát lại hoặc bị bỏ qua tùy nguồn.

Không retry vô hạn. Cần giới hạn số lần, backoff, jitter và tổng deadline để tránh tạo vòng lặp gây quá tải.

## 7. Xử lý mất kết nối và gián đoạn phiên

Mất kết nối transport có thể làm các tương tác đang chạy gặp lỗi. Ứng dụng cần phân biệt hai tình huống:

- **Phiên không hỗ trợ resume hoặc resume thất bại:** client phải xử lý lỗi và quyết định có mở stream mới hay không.
- **Phiên hỗ trợ RSocket Resumption và còn đủ trạng thái để khôi phục:** hai peer có thể tiếp tục phiên đã gián đoạn theo cơ chế resume của protocol.

Resumption là tính năng tùy chọn. Hai phía phải hỗ trợ và cấu hình phù hợp; phía responder cần giữ trạng thái phiên và dữ liệu frame đã gửi trong khoảng thời gian cần thiết. Khi kết nối được thiết lập lại, peer dùng resume token và vị trí frame để thương lượng tiếp tục phiên.

Resumption giúp khôi phục việc truyền frame trong phạm vi trạng thái còn được giữ. Nó không phải một event log bền vững, không đảm bảo dữ liệu nghiệp vụ được lưu qua việc tiến trình server bị mất hoàn toàn, và không tự cung cấp exactly-once processing cho các tác dụng phụ của ứng dụng.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as Server
    C->>S: REQUEST_STREAM
    S-->>C: PAYLOAD 1
    S-->>C: PAYLOAD 2
    Note over C,S: Transport bị gián đoạn
    C->>S: RESUME (nếu phiên hỗ trợ)
    S-->>C: RESUME_OK
    S-->>C: Tiếp tục frame chưa được xác nhận
    S-->>C: PAYLOAD tiếp theo
~~~

Nếu resume không khả thi, client có thể tạo stream mới. Để tránh bỏ sót dữ liệu, API nên hỗ trợ cursor hoặc sequence number:

- Mỗi sự kiện có ID hoặc sequence tăng đơn điệu trong phạm vi phù hợp.
- Client lưu vị trí cuối cùng đã xử lý thành công.
- Khi kết nối lại, client yêu cầu dữ liệu sau vị trí đó.
- Server xác định khoảng dữ liệu còn khả dụng và trả lời nếu cursor đã quá cũ.
- Client xử lý trùng bằng idempotency hoặc deduplication.

Cơ chế cursor phụ thuộc vào ứng dụng và nguồn dữ liệu; RSocket không tự tạo lịch sử sự kiện cho một stream.

## 8. KEEPALIVE, timeout và phục hồi

RSocket có frame KEEPALIVE để peer kiểm tra trạng thái phiên và phát hiện kết nối không còn phản hồi. Cấu hình keepalive gồm chu kỳ gửi và thời gian tối đa không nhận được keepalive hợp lệ trước khi xem kết nối là đã mất.

Keepalive hỗ trợ phát hiện kết nối chết, nhưng không cho biết một truy vấn nghiệp vụ có đang tiến triển hay không. Một peer có thể trả keepalive trong khi một route bị nghẽn hoặc database downstream bị chậm.

Vì vậy cần kết hợp:

- Keepalive cho sức khỏe của phiên transport.
- Timeout hoặc deadline cho từng request và stream.
- Metrics cho thời gian xử lý và độ trễ giữa các phần tử.
- Chính sách reconnect hoặc resume.
- Cursor và sequence nếu ứng dụng cần tiếp tục từ vị trí đã xử lý.

Không nên đặt keepalive quá ngắn khiến kết nối bình thường bị coi là mất khi mạng có jitter. Cũng không nên dùng keepalive thay cho timeout nghiệp vụ.

## 9. Cancellation khi consumer không còn theo dõi

Khi client đóng màn hình, đổi bộ lọc hoặc không còn cần stream, nó nên hủy subscription. Với tương tác RSocket đang hoạt động, cancellation được truyền bằng frame CANCEL theo Stream ID.

~~~java
Disposable subscription = requester
    .route("events.stream")
    .data(filter)
    .retrieveFlux(Event.class)
    .subscribe(this::renderEvent, this::showError);

// Khi người dùng rời màn hình hoặc bỏ theo dõi:
subscription.dispose();
~~~

Server cần để publisher phản ứng với cancellation và giải phóng cursor, subscription tới nguồn, buffer hoặc tài nguyên khác. Cancellation không rollback một giao dịch đã commit và cũng không bảo đảm một tác vụ blocking đã dừng ngay lập tức.

Nếu nguồn không thể hủy, cần giới hạn công việc phát sinh và dừng ở các điểm an toàn. Không để một stream đã bị client bỏ theo dõi tiếp tục tạo tác vụ nền không giới hạn.

## 10. Thiết kế chiến lược phục hồi theo loại dữ liệu

Không nên dùng cùng một chính sách cho mọi stream. Hãy dựa vào ý nghĩa dữ liệu và khả năng đọc lại.

| Loại stream | Khi consumer chậm | Khi mất kết nối |
|---|---|---|
| Giá hiện tại hoặc trạng thái thiết bị | Latest hoặc sample | Đăng ký lại và lấy snapshot mới |
| Telemetry có thể tổng hợp | Batch/window, drop có kiểm soát | Đọc lại từ cursor nếu có lưu trữ |
| Audit hoặc sự kiện tài chính | Backpressure và lưu bền vững | Resume hoặc replay từ sequence đã xác nhận |
| Thông báo tạm thời | Buffer hữu hạn, giới hạn tuổi dữ liệu | Có thể bỏ thông báo cũ theo nghiệp vụ |
| Lệnh điều khiển | Giới hạn tốc độ, xác nhận, idempotency | Tra cứu trạng thái lệnh trước khi gửi lại |

Đối với dữ liệu có thể mất, chính sách latest hoặc drop giúp giữ độ trễ thấp. Đối với dữ liệu không được mất, cần lưu bền vững và xác nhận tiến độ xử lý. Một stream RSocket đang mở không thay thế message broker hoặc event store.

## 11. Quan sát và kiểm thử slow consumer

Cần theo dõi các chỉ số để phát hiện consumer đang tụt lại:

- Số phần tử được phát và số phần tử được xử lý mỗi giây.
- Demand hiện tại hoặc mức độ thường xuyên requester cấp REQUEST_N.
- Độ sâu buffer và số lần overflow.
- Số phần tử bị drop hoặc thay thế bởi latest.
- Độ trễ từ lúc phát đến lúc xử lý.
- Số stream đang hoạt động, số cancellation và số lỗi.
- Số lần disconnect, reconnect, resume thành công và resume thất bại.
- Số sự kiện được replay và số sự kiện trùng bị loại bỏ.

### Kiểm thử demand có kiểm soát

StepVerifier có thể xác nhận publisher chỉ phát phần tử khi test cấp demand:

~~~java
StepVerifier.create(eventSource, 0)
    .expectSubscription()
    .thenRequest(2)
    .expectNext(firstEvent, secondEvent)
    .thenRequest(1)
    .expectNext(thirdEvent)
    .thenCancel()
    .verify();
~~~

Bài test bắt đầu với demand bằng 0, yêu cầu hai phần tử rồi yêu cầu thêm một phần tử. Sau đó subscriber hủy stream. Đây là kiểm thử publisher ở tầng Reactive Streams; cần thêm kiểm thử tích hợp RSocket để xác nhận flow control và cancellation được ánh xạ đúng qua transport.

### Kiểm thử lỗi giữa stream

~~~java
StepVerifier.create(
        Flux.just(1, 2)
            .concatWith(Mono.error(
                new IllegalStateException("source failed"))))
    .expectNext(1, 2)
    .expectError(IllegalStateException.class)
    .verify();
~~~

Test này xác nhận hai phần tử được phát trước khi stream kết thúc bằng lỗi. Có thể bổ sung test cho onErrorResume, retry giới hạn và chính sách kết quả lỗi theo từng phần tử.

### Kiểm thử gián đoạn và phục hồi

Ở mức tích hợp client/server, nên mô phỏng:

1. Consumer xử lý chậm hơn producer và xác nhận demand giảm hoặc buffer tăng trong giới hạn.
2. Buffer đầy và kiểm tra đúng chính sách overflow.
3. Một phần tử lỗi nhưng stream vẫn tiếp tục theo kiểu kết quả từng phần tử.
4. Lỗi nguồn làm stream kết thúc và retry chỉ xảy ra theo giới hạn đã đặt.
5. Transport disconnect khi stream đang hoạt động.
6. Resume khi cả hai peer còn trạng thái cần thiết.
7. Resume thất bại rồi đăng ký lại từ cursor.
8. Sự kiện được phát lại không gây tác dụng phụ trùng.
9. Client hủy stream và server giải phóng tài nguyên.

## 12. Quy trình xử lý sự cố giữa luồng

Khi một stream realtime chậm, lỗi hoặc bị gián đoạn, có thể kiểm tra theo thứ tự:

1. **Xác định phạm vi:** chỉ một stream, một route hay toàn bộ kết nối bị ảnh hưởng?
2. **Kiểm tra tốc độ:** producer phát nhanh hơn consumer hay nguồn đã ngừng phát?
3. **Kiểm tra demand và queue:** consumer có cấp thêm demand không, buffer nào đang tăng?
4. **Phân loại kết thúc:** stream hoàn tất, bị hủy, phát ERROR hay transport disconnect?
5. **Chọn phục hồi:** tiếp tục phiên bằng resume, retry nguồn, hay tạo stream mới từ cursor?
6. **Bảo vệ dữ liệu:** dùng sequence, idempotency và deduplication nếu có replay.
7. **Xác minh tài nguyên:** đảm bảo subscription cũ, queue, cursor và tác vụ nền đã được dọn dẹp.

Không nên retry ngay mọi lỗi. Một lỗi validation hoặc authorization thường không tự hết khi thử lại. Một lỗi tạm thời của mạng hoặc dịch vụ downstream có thể retry, nhưng phải có backoff, giới hạn và ngân sách thời gian.

## 13. Kết luận

Khi consumer chậm, demand và backpressure giúp điều tiết lượng payload được gửi; buffer hữu hạn hấp thụ burst ngắn và cần chính sách rõ khi đầy. Khi một phần tử lỗi, hãy quyết định lỗi đó chỉ ảnh hưởng phần tử hay phải kết thúc toàn bộ stream. Khi transport gián đoạn, có thể dùng RSocket Resumption nếu phiên được cấu hình và còn trạng thái, hoặc mở stream mới từ cursor/sequence do ứng dụng quản lý.

Một hệ thống RSocket realtime ổn định cần phối hợp flow control, giới hạn queue, xử lý lỗi, cancellation, timeout, keepalive và phục hồi dữ liệu. Hãy chọn chính sách dựa trên việc dữ liệu có thể mất hay cần lưu bền vững; đo backlog và độ trễ; đồng thời kiểm thử consumer chậm, lỗi giữa luồng và reconnect để tránh mất dữ liệu hoặc xử lý trùng.


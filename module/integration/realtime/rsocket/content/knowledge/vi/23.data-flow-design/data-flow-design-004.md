# Chọn chính sách cho bên nhận chậm theo yêu cầu nghiệp vụ

Trong hệ thống realtime, bên nhận có thể xử lý chậm hơn tốc độ bên gửi tạo dữ liệu. Nguyên nhân có thể là mạng yếu, thiết bị di động chuyển nền, consumer đang ghi database, downstream bị nghẽn hoặc một subscriber có ít tài nguyên hơn những subscriber khác.

Nếu không có chính sách rõ ràng, dữ liệu sẽ tích lũy trong buffer, độ trễ tăng dần và cuối cùng gây cạn bộ nhớ hoặc làm ảnh hưởng các stream khác. Tuy nhiên, bỏ dữ liệu cũng không phải lúc nào cũng chấp nhận được. Một dashboard giá có thể chỉ cần giá mới nhất; một lệnh thanh toán hoặc bản ghi audit cần được xử lý đầy đủ và có thể kiểm chứng.

Vì vậy, chính sách cho slow receiver phải xuất phát từ yêu cầu nghiệp vụ: **dữ liệu có được phép mất không, cần giữ thứ tự đến đâu, độ mới quan trọng thế nào, có thể phát lại không và bên nhận chậm được phép giữ bao nhiêu tài nguyên**.

## 1. Slow receiver là gì?

Slow receiver (bên nhận chậm hoặc slow consumer) là subscriber không tiêu thụ dữ liệu nhanh bằng tốc độ publisher tạo ra. Trong RSocket, tình huống này thường xuất hiện ở request-stream, request-channel và các luồng server phát sự kiện tới nhiều client.

Ví dụ:

- Server tạo 1.000 sự kiện telemetry mỗi giây nhưng thiết bị di động chỉ xử lý 100 sự kiện mỗi giây.
- Client nhận thay đổi trạng thái đơn hàng nhưng database local ghi chậm.
- Một subscriber mở dashboard ở mạng yếu và thường xuyên bị ngắt quãng.
- Một service nhận stream từ nhiều thiết bị rồi ghi từng event vào kho dữ liệu.
- Một channel nhận command liên tục trong khi handler phải gọi một dịch vụ downstream đang quá tải.

Tốc độ producer cao hơn tốc độ consumer trong thời gian ngắn có thể chỉ là burst. Nếu chênh lệch kéo dài, backlog sẽ tăng liên tục. Không có buffer hữu hạn nào giải quyết được tình trạng producer luôn nhanh hơn consumer trong thời gian không giới hạn.

### Mô hình tốc độ

Gọi:

- λ (lambda) là tốc độ producer tạo phần tử mỗi giây.
- μ (mu) là tốc độ consumer xử lý phần tử mỗi giây.
- Q là số phần tử đang chờ trong queue.

Nếu λ lớn hơn μ, queue tăng với tốc độ xấp xỉ λ − μ. Với queue có dung lượng Qmax, thời gian gần đúng để queue đầy khi tốc độ ổn định là:

\[
T_{\text{full}} \approx \frac{Q_{\max}-Q_0}{\lambda-\mu}
\]

Trong đó Q0 là số phần tử đã có sẵn trong queue. Đây là ước lượng đơn giản; burst, kích thước message, retry và thời gian xử lý biến động sẽ làm kết quả thực tế khác đi.

Buffer chỉ hấp thụ được burst hữu hạn. Nếu tốc độ trung bình của producer tiếp tục cao hơn consumer, hệ thống phải giảm tốc, lưu bền vững, loại bỏ dữ liệu hoặc ngắt consumer.

## 2. Trước khi chọn chính sách, hãy xác định yêu cầu nghiệp vụ

Không nên bắt đầu bằng câu hỏi “dùng buffer bao nhiêu phần tử?”. Trước hết cần trả lời dữ liệu được sử dụng để làm gì.

| Yêu cầu | Câu hỏi cần trả lời |
|---|---|
| Độ đầy đủ | Có được phép mất một message không? |
| Thứ tự | Có phải xử lý đúng thứ tự phát sinh không? |
| Độ mới | Giá trị mới nhất có quan trọng hơn các giá trị trung gian không? |
| Độ trễ | Chấp nhận chậm tối đa bao lâu? |
| Khả năng phát lại | Có thể lấy lại dữ liệu từ log, database hoặc cursor không? |
| Tính bền vững | Dữ liệu phải sống sót sau restart hay chỉ cần trong bộ nhớ? |
| Cách ly | Một subscriber chậm có được làm chậm subscriber khác không? |
| Chi phí | Có thể dành bao nhiêu bộ nhớ, lưu trữ và băng thông cho mỗi subscriber? |

Một số ví dụ:

- Lệnh chuyển tiền: không được âm thầm bỏ lệnh; cần xác nhận, lưu bền vững và chống xử lý trùng.
- Bản ghi audit: cần giữ đủ, có thứ tự theo phạm vi nghiệp vụ và có thể truy vết.
- Giá thị trường trên dashboard: thường ưu tiên giá mới nhất; các giá trị trung gian có thể được gộp hoặc lấy mẫu.
- Telemetry cảm biến: có thể chấp nhận lấy mẫu cho màn hình, nhưng luồng lưu trữ phân tích có thể cần đầy đủ.
- Chat: thường cần giữ thứ tự và phát lại tin nhắn sau khi reconnect; một client quá chậm có thể bị ngắt và đồng bộ lại.
- Vị trí xe hoặc trạng thái thiết bị: giá trị cũ nhanh chóng mất ý nghĩa; latest-value thường phù hợp hơn queue chứa mọi vị trí cũ.

## 3. Những chính sách phổ biến

Có sáu nhóm chính sách thường dùng. Chúng có thể kết hợp, ví dụ backpressure trong điều kiện bình thường, buffer có giới hạn để hấp thụ burst và disconnect/replay khi subscriber vượt ngưỡng lag.

| Chính sách | Hành vi | Khi phù hợp | Đánh đổi |
|---|---|---|---|
| Backpressure / lossless | Producer chỉ phát theo demand; không bỏ message | Consumer có thể điều tiết nguồn và cần giữ đủ dữ liệu | Producer có thể bị chậm theo |
| Bounded buffer | Lưu tạm tối đa N phần tử | Burst ngắn, có giới hạn bộ nhớ | Queue đầy thì cần hành động tiếp theo |
| Drop newest | Bỏ message mới khi không còn chỗ | Giữ backlog cũ để bảo toàn chuỗi đã bắt đầu xử lý | Consumer không thấy cập nhật mới |
| Drop oldest | Bỏ message cũ nhất để nhận message mới | Ưu tiên độ mới, chấp nhận mất lịch sử trung gian | Có khoảng trống trong chuỗi sự kiện |
| Latest-value / coalescing / sampling | Chỉ giữ giá trị mới nhất, gộp hoặc lấy mẫu | Dashboard, telemetry, trạng thái | Không phù hợp với event cần xử lý từng cái |
| Disconnect / replay | Ngắt subscriber quá chậm rồi phát lại từ cursor | Dữ liệu cần đầy đủ nhưng không thể giữ queue vô hạn trong RAM | Cần nguồn dữ liệu bền vững và giao thức resume ở tầng ứng dụng |

### Sơ đồ quyết định

~~~mermaid
flowchart TD
    A[Consumer chậm hơn producer] --> B{Có được phép mất message?}
    B -->|Không| C{Nguồn có thể pause theo demand?}
    C -->|Có| D[Backpressure]
    C -->|Không| E{Có thể lưu bền vững?}
    E -->|Có| F[Durable queue / log + cursor]
    E -->|Không| G[Bounded buffer + reject / disconnect]
    B -->|Có| H{Cần giá trị mới nhất?}
    H -->|Có| I[Latest-value / coalescing]
    H -->|Không| J{Có thể bỏ mẫu?}
    J -->|Có| K[Sampling]
    J -->|Không| L[Drop oldest hoặc drop newest]
    F --> M[Replay / resume theo cursor]
    G --> M
~~~

Không có chính sách nào đúng cho mọi loại dữ liệu. Một route có thể cần chính sách khác với route khác dù chúng dùng cùng một kết nối RSocket.

## 4. Backpressure: điều tiết theo demand

Reactive Streams định nghĩa demand: subscriber yêu cầu publisher phát một số phần tử bằng request(n). Publisher không được phát vượt tổng demand đã cấp.

RSocket dùng cơ chế flow control tương ứng. Với request-stream, responder nhận initial request N và có thể nhận thêm REQUEST_N khi requester cần nhiều phần tử hơn. Với request-channel, hai hướng có demand độc lập: demand của client đối với response và demand của server đối với request.

Khi consumer chậm, nó cấp demand chậm hơn. Nếu publisher tuân thủ Reactive Streams và nguồn có thể pause, áp lực được truyền ngược về phía producer.

Ưu điểm:

- Không cần tích lũy vô hạn message ở phía consumer.
- Producer có thể giảm tốc theo tốc độ xử lý thực tế.
- Giữ được dữ liệu và thứ tự nếu toàn bộ pipeline tuân thủ demand.
- Tài nguyên có thể được giới hạn tốt hơn.

Nhược điểm:

- Một nguồn nóng (hot source) như callback từ thiết bị hoặc broker có thể không dừng phát chỉ vì subscriber chậm.
- Adapter từ API không reactive có thể phải buffer, drop hoặc tạm ngừng nhận dữ liệu.
- Backpressure có thể làm chậm upstream và tăng độ trễ cho các thành phần phụ thuộc.
- Demand đếm số phần tử, không giới hạn byte của từng payload.

Backpressure chỉ hoạt động đúng nếu từng đoạn trong pipeline truyền demand và xử lý cancellation. Nếu một operator hoặc adapter tạo queue không giới hạn, hệ thống vẫn có thể cạn bộ nhớ dù giao thức RSocket có flow control.

## 5. Bounded buffer: hấp thụ burst có giới hạn

Buffer hữu ích khi producer có burst ngắn nhưng tốc độ trung bình vẫn có thể được consumer xử lý. Giới hạn buffer phải dựa trên ngân sách bộ nhớ và độ trễ tối đa.

Giả sử:

- Queue chứa tối đa 500 phần tử.
- Kích thước trung bình mỗi phần tử là 2 KB.
- Chỉ tính payload, queue cần khoảng 1 MB; thực tế còn overhead object, reference, allocator và các queue khác.

Nếu có 2.000 subscriber và mỗi subscriber giữ một queue riêng, chi phí có thể tăng lên đáng kể. Vì vậy phải tính theo tổng số subscriber và kích thước payload thực tế, không chỉ nhìn dung lượng một queue.

### Buffer đầy thì sao?

Một buffer hữu hạn luôn cần chính sách overflow:

- Báo lỗi và kết thúc stream.
- Bỏ phần tử mới.
- Bỏ phần tử cũ.
- Ghi sang durable storage.
- Ngắt subscriber và cho phép replay.

Không dùng buffer không giới hạn để che giấu chênh lệch tốc độ. Nó chỉ trì hoãn thời điểm hệ thống gặp sự cố và thường khiến độ trễ tăng trước khi bộ nhớ cạn.

### Ước lượng queue và độ trễ

Nếu consumer xử lý μ phần tử mỗi giây và queue có Q phần tử, thời gian chờ gần đúng của phần tử cuối queue là:

\[
W_{\text{queue}} \approx \frac{Q}{\mu}
\]

Ví dụ consumer xử lý 100 phần tử/giây, queue có 1.000 phần tử thì phần tử ở cuối queue có thể phải đợi khoảng 10 giây trước khi được xử lý, chưa tính thời gian xử lý riêng. Buffer lớn hơn không tự động làm hệ thống tốt hơn; nó có thể biến overload thành latency rất cao.

## 6. Drop newest: giữ backlog cũ

Drop newest giữ lại những phần tử đã có trong queue và bỏ phần tử mới đến khi queue đầy.

Ví dụ:

- Queue đang giữ event 101, 102, 103.
- Consumer chưa xử lý kịp.
- Event 104 đến nhưng queue đã đầy.
- Event 104 bị bỏ, backlog cũ vẫn được xử lý theo thứ tự.

Chính sách này có thể phù hợp khi:

- Thứ tự chuỗi sự kiện đang xử lý quan trọng.
- Message cũ đã được xếp hàng cần hoàn tất trước.
- Dữ liệu mới có thể được gửi lại từ nguồn sau này.
- Hệ thống muốn tránh thay đổi thứ tự của phần backlog hiện tại.

Nhược điểm là consumer tiếp tục xử lý dữ liệu ngày càng cũ. Với dashboard hoặc trạng thái thiết bị, xử lý một giá trị cũ trong khi giá trị mới đã đến thường không có ích.

Drop newest chỉ an toàn khi việc mất dữ liệu mới được nghiệp vụ cho phép hoặc có cơ chế phát hiện và bù lại.

## 7. Drop oldest: ưu tiên dữ liệu mới

Drop oldest loại bỏ phần tử cũ nhất trong queue khi cần chỗ cho phần tử mới. Queue luôn giữ một cửa sổ gần nhất của dữ liệu.

Ví dụ:

- Queue đang giữ event 101, 102, 103.
- Event 104 đến khi queue đầy.
- Event 101 bị loại, queue trở thành 102, 103, 104.

Chính sách này phù hợp với:

- Telemetry hiển thị trạng thái gần nhất.
- Dashboard cập nhật liên tục.
- Vị trí xe, trạng thái thiết bị hoặc giá trị cảm biến.
- Dữ liệu mà giá trị mới thay thế ý nghĩa của giá trị cũ.

Không dùng drop oldest cho:

- Lệnh chuyển tiền hoặc lệnh điều khiển thiết bị cần thực thi đầy đủ.
- Audit log.
- Event tạo ra chuyển trạng thái mà mỗi bước đều quan trọng.
- Dữ liệu cần đối soát hoặc tái dựng lịch sử.

Khi bỏ dữ liệu, hệ thống nên ghi metric về số phần tử bị drop và có thể gắn sequence number để client biết đã có khoảng trống.

## 8. Latest-value và coalescing: giữ trạng thái thay vì giữ mọi event

Một số luồng thực chất truyền trạng thái liên tục, không phải các sự kiện độc lập. Trong trường hợp này, việc giữ mọi giá trị trung gian có thể gây lãng phí.

Ví dụ một cảm biến nhiệt độ phát:

~~~text
28.1, 28.2, 28.3, 28.4, 28.5, 28.6
~~~

Nếu dashboard chỉ cần hiển thị nhiệt độ hiện tại, có thể chỉ giữ 28.6 khi consumer sẵn sàng. Các giá trị cũ không cần xếp hàng.

**Latest-value** giữ giá trị mới nhất chưa được tiêu thụ. Khi consumer yêu cầu tiếp, nó nhận giá trị mới nhất hiện có.

**Coalescing** gộp nhiều cập nhật thành một kết quả. Ví dụ thay vì phát 100 lần thay đổi số lượng đơn trong 1 giây, có thể gộp thành tổng số lượng cuối cùng trong khoảng đó.

Phân biệt:

- Latest-value bỏ các giá trị trung gian, chỉ giữ trạng thái cuối.
- Coalescing kết hợp nhiều thay đổi theo một hàm nghiệp vụ, ví dụ cộng delta.
- Debounce chờ một khoảng yên lặng rồi mới phát giá trị cuối.
- Throttle giới hạn tần suất phát tối đa.
- Sampling lấy một giá trị ở mỗi chu kỳ cố định.

Không được gộp các sự kiện không có phép gộp đúng. Ví dụ không thể cộng hoặc bỏ các lệnh chuyển tiền; còn các cập nhật vị trí mới có thể thay thế vị trí cũ trong một giao diện bản đồ.

## 9. Sampling: giảm tần suất dữ liệu

Sampling phù hợp khi consumer không cần mọi mẫu. Ví dụ sensor gửi 1.000 mẫu/giây nhưng màn hình chỉ cần cập nhật 10 lần/giây.

Nếu lấy mẫu mỗi 100 ms, consumer nhận tối đa khoảng 10 giá trị/giây. Cần xác định quy tắc chọn mẫu:

- Lấy mẫu cuối cùng trong chu kỳ để ưu tiên trạng thái mới.
- Lấy trung bình, min/max hoặc percentile để giữ thông tin thống kê.
- Lấy mẫu ngẫu nhiên nếu cần phân tích phân phối.
- Lấy mẫu theo sự kiện quan trọng nếu có ngưỡng cảnh báo.

Sampling làm giảm tải nhưng có thể bỏ lỡ sự kiện ngắn. Với cảnh báo vượt ngưỡng, nên kiểm tra điều kiện trên nguồn trước sampling hoặc gửi cảnh báo riêng không bị sampling.

## 10. Disconnect và replay: khi cần đủ dữ liệu nhưng không thể chờ mãi

Với dữ liệu quan trọng, consumer quá chậm không nên được giữ bằng queue RAM vô hạn. Một lựa chọn là ngắt stream khi lag vượt ngưỡng, sau đó consumer kết nối lại và phát lại từ cursor.

Một quy trình điển hình:

1. Mỗi event có sequence number hoặc offset.
2. Server theo dõi vị trí cuối cùng consumer đã xác nhận xử lý.
3. Khi lag vượt giới hạn, server hủy stream hoặc đóng subscription.
4. Consumer reconnect và gửi cursor cuối cùng đã xử lý.
5. Server phát lại các event sau cursor.
6. Consumer xử lý idempotent và xác nhận cursor mới.

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant L as Durable Log
    participant S as RSocket Server
    participant C as Slow Consumer
    P->>L: Append event 101..N
    L->>S: Read by cursor
    S->>C: Stream events
    Note over C: Consumer xử lý chậm, lag vượt ngưỡng
    S-->>C: Cancel / close stream
    C->>S: Reconnect with last committed cursor
    S->>L: Replay after cursor
    L-->>S: Events chưa xác nhận
    S->>C: Replay stream
    C-->>S: Ack cursor sau khi commit
~~~

RSocket Resumption có thể hỗ trợ khôi phục session và frame trong một số trường hợp, nhưng không thay thế cursor bền vững hoặc xác nhận nghiệp vụ. Nếu ứng dụng cần bảo đảm không mất event sau process restart, phải lưu event và cursor ở tầng ứng dụng hoặc broker bền vững.

Replay có thể phát lại event đã được consumer nhận nhưng chưa xác nhận. Vì vậy handler cần idempotency key, event ID hoặc sequence number để tránh tác dụng phụ trùng lặp.

## 11. Áp dụng chính sách trong Reactor

Reactor cung cấp các operator để thể hiện chính sách khi downstream không yêu cầu kịp. Cần chọn operator theo ý nghĩa dữ liệu và hiểu hành vi upstream.

### Drop phần tử mới

~~~java
Flux<Telemetry> stream = telemetrySource()
    .onBackpressureDrop(dropped ->
        metrics.incrementDropped("telemetry"));
~~~

Operator bỏ các phần tử đến khi downstream không có demand và gọi callback để ghi nhận. Phù hợp với dữ liệu có thể mất; không phù hợp với lệnh hoặc audit cần đầy đủ.

onBackpressureDrop không tạo queue để giữ backlog cũ. Nếu muốn giữ tối đa 256 phần tử đã đến trước và chỉ bỏ phần tử mới khi buffer đầy, dùng bounded buffer với DROP_LATEST:

~~~java
Flux<Event> keepOlderPending = eventSource()
    .onBackpressureBuffer(
        256,
        dropped -> metrics.incrementDropped("new-event"),
        BufferOverflowStrategy.DROP_LATEST
    );
~~~

### Giữ giá trị mới nhất

~~~java
Flux<PriceTick> latestPrices = priceSource()
    .onBackpressureLatest();
~~~

Khi downstream chưa sẵn sàng, operator giữ giá trị mới nhất và thay thế giá trị chưa được tiêu thụ trước đó. Consumer nhận trạng thái gần nhất khi có demand tiếp.

### Buffer có giới hạn và bỏ phần tử cũ nhất

~~~java
Flux<DeviceState> states = deviceStateSource()
    .onBackpressureBuffer(
        256,
        dropped -> metrics.incrementDropped("device-state"),
        BufferOverflowStrategy.DROP_OLDEST
    );
~~~

Queue chỉ giữ tối đa 256 phần tử. Khi đầy, phần tử cũ nhất bị loại để chừa chỗ cho giá trị mới. Callback giúp quan sát việc mất dữ liệu.

Nếu dùng BufferOverflowStrategy.ERROR hoặc operator onBackpressureError(), stream có thể phát lỗi khi không thể nhận thêm phần tử. Client cần xử lý lỗi và có thể reconnect theo chính sách.

### Sampling

~~~java
Flux<TemperatureSample> sampled = sensorSource()
    .sample(Duration.ofMillis(100));
~~~

Ví dụ lấy mẫu tối đa khoảng 10 lần/giây, giữ giá trị cuối cùng trong mỗi chu kỳ sampling. Đây là chính sách cho dữ liệu hiển thị hoặc phân tích chấp nhận giảm tần suất, không phải cơ chế giữ đầy đủ lịch sử.

### Điều tiết request upstream bằng limitRate

~~~java
Flux<Event> controlled = eventSource()
    .limitRate(64);
~~~

limitRate chia demand downstream thành các batch request upstream. Nó giúp điều tiết cách yêu cầu phần tử từ publisher hỗ trợ backpressure. Nó không tự drop event, không giới hạn kích thước byte và không thay thế queue có giới hạn cho nguồn nóng không tuân thủ demand.

### Giới hạn concurrency khi xử lý

~~~java
Flux<Result> processed = commands
    .flatMap(command -> process(command), 8, 16);
~~~

Ví dụ cho phép tối đa 8 tác vụ xử lý đồng thời với prefetch 16. Nếu cần giữ thứ tự command, dùng concatMap hoặc flatMapSequential theo đúng yêu cầu. Concurrency và prefetch cũng là một phần của ngân sách bộ nhớ.

Lưu ý quan trọng: các operator onBackpressureDrop, onBackpressureLatest và onBackpressureBuffer thường yêu cầu upstream không giới hạn rồi áp dụng drop, latest hoặc buffer ngay tại operator. Chúng xử lý nguồn phát nhanh bằng chính sách cục bộ; không tự làm chậm nguồn upstream. limitRate mới chia demand thành các batch request để điều tiết publisher upstream có hỗ trợ backpressure. Cần đo buffer, allocation, số phần tử drop và latency trong workload thực tế.

## 12. Kết hợp nhiều lớp chính sách

Trong thực tế, một pipeline có thể kết hợp nhiều cơ chế:

- RSocket demand điều tiết số response được gửi qua network.
- Reactor limitRate điều tiết batch request đến upstream.
- Bounded buffer hấp thụ burst ngắn từ nguồn nóng.
- Latest-value hoặc sampling giảm dữ liệu không cần thiết.
- Timeout và lag threshold ngắt subscriber không theo kịp.
- Durable log cho phép replay dữ liệu quan trọng.

Ví dụ luồng telemetry cho dashboard:

~~~java
Flux<DeviceState> dashboardStream(String deviceId) {
    return telemetrySource(deviceId)
        .sample(Duration.ofMillis(200))
        .onBackpressureLatest()
        .limitRate(16);
}
~~~

Ví dụ này ưu tiên trạng thái gần nhất và giảm tần suất cập nhật. Nếu dashboard cần cảnh báo không được bỏ lỡ, hãy tách cảnh báo thành một luồng riêng có lưu bền vững hoặc xử lý ngưỡng ở phía producer.

Ví dụ command cần giữ đầy đủ:

~~~java
Flux<CommandResult> commandStream(Flux<Command> commands) {
    return commands
        .concatMap(command ->
            commandStore.persist(command)
                .then(commandService.execute(command))
                .flatMap(result ->
                    commandStore.markCompleted(command.id(), result)
                        .thenReturn(result)
                )
        );
}
~~~

Ví dụ trên tuần tự hóa command và lưu trạng thái trước/sau xử lý. Một triển khai thật cần transaction, idempotency key, retry có giới hạn và xử lý trạng thái khi process chết giữa hai bước. Không dùng drop operator cho command.

## 13. Request-stream và request-channel trong RSocket

RSocket flow control hoạt động theo stream. Với request-stream, requester gửi một request ban đầu rồi cấp demand cho response. Responder chỉ phát trong lượng demand đã nhận.

Với request-channel, hai hướng có demand độc lập:

- Client cấp demand cho các response mà nó nhận.
- Server cấp demand cho các request mà nó tiêu thụ.

Điều này giúp một hướng chậm không nhất thiết buộc hướng kia phải có cùng tốc độ. Tuy nhiên, logic ứng dụng vẫn có thể liên kết hai hướng. Ví dụ server chỉ phát acknowledgement sau khi xử lý command; nếu command bị chậm, response cũng bị chậm theo.

Fire-and-forget không có response payload để xác nhận xử lý nghiệp vụ. Nếu cần biết server đã lưu hoặc thực thi command, hãy thiết kế acknowledgement qua request-response, request-channel hoặc một trạng thái có thể truy vấn. Không suy ra rằng message đã được xử lý bền vững chỉ từ việc client đã gửi xong.

Flow control của RSocket giới hạn số payload được phát theo demand, nhưng payload có thể có kích thước rất khác nhau. Cần kết hợp max frame size, max payload size, giới hạn metadata và quota theo stream/principal.

## 14. Cách ly subscriber chậm

Trong hệ thống fan-out, một publisher có thể phát cùng dữ liệu tới nhiều subscriber. Nếu tất cả dùng chung một queue hoặc một pipeline bị chặn bởi subscriber chậm, một client yếu có thể ảnh hưởng toàn bộ người dùng.

Các chiến lược cách ly:

- Queue riêng có giới hạn cho từng subscriber.
- Chính sách overflow riêng theo loại subscriber.
- Ngắt subscriber vượt lag threshold.
- Phân nhóm subscriber theo chất lượng dịch vụ hoặc loại dữ liệu.
- Không để một subscriber yêu cầu dữ liệu vô hạn làm tăng buffer dùng chung.
- Tách pipeline realtime và pipeline lưu trữ đầy đủ.

Ví dụ: dashboard chỉ cần latest-value; hệ thống audit cần lưu tất cả event. Không nên dùng cùng một multicast policy cho cả hai vì mục tiêu dữ liệu khác nhau.

Nếu dùng shared hot source, hãy kiểm tra semantics của sink, multicast và backpressure trong Reactor version đang triển khai. Một sink có thể buffer theo cấu hình hoặc từ chối emission khi subscriber không theo kịp. Cần xử lý kết quả emit và giới hạn buffer thay vì bỏ qua tín hiệu overflow.

## 15. Đo lag và đặt ngưỡng hành động

Không thể chọn chính sách tốt nếu không biết consumer đang chậm đến mức nào. Nên đo:

- Queue depth hoặc số phần tử pending.
- Số byte đang giữ trong buffer.
- Thời gian từ lúc event được tạo đến lúc consumer xử lý xong.
- Sequence number mới nhất và sequence cuối đã xác nhận.
- Tỷ lệ drop, overflow và timeout.
- Số subscriber bị ngắt vì quá lag.
- Thời gian replay và số event replay.
- Tốc độ producer và consumer theo từng route.

Một số ngưỡng có thể dùng:

| Điều kiện | Hành động tham khảo |
|---|---|
| Queue dưới 50% và latency bình thường | Tiếp tục |
| Queue vượt 70% trong một khoảng thời gian | Cảnh báo, giảm producer hoặc concurrency |
| Queue đầy | Áp dụng overflow policy đã chọn |
| Lag vượt số event cho phép | Ngắt stream và yêu cầu replay |
| Latency vượt SLA | Sampling, latest-value hoặc giảm tần suất |
| Consumer không có tiến triển | Timeout và cleanup |

Không nên đặt ngưỡng chỉ dựa vào một snapshot. Dùng cửa sổ thời gian, percentile và xu hướng để tránh phản ứng quá mức với burst ngắn.

## 16. Chọn chính sách theo từng loại nghiệp vụ

| Loại dữ liệu | Chính sách khuyến nghị | Điều kiện bổ sung |
|---|---|---|
| Lệnh thanh toán/chuyển tiền | Lossless, backpressure, durable queue, ack | Idempotency, audit, trạng thái xử lý |
| Lệnh điều khiển thiết bị | Lossless hoặc reject rõ ràng | Sequence, expiry, xác nhận thiết bị |
| Audit log | Durable append, replay | Không drop âm thầm, retention |
| Sự kiện đơn hàng | Lossless hoặc durable replay | Thứ tự theo order ID, dedup |
| Giá thị trường trên dashboard | Latest-value hoặc sampling | Sequence để phát hiện khoảng trống |
| Telemetry dashboard | Sampling/latest-value | Tách luồng lưu trữ đầy đủ |
| Vị trí xe | Latest-value hoặc drop-oldest | Timestamp để bỏ dữ liệu cũ |
| Chat | Bounded buffer rồi disconnect/replay | Message ID, thứ tự, cursor |
| Metrics hệ thống | Sampling/aggregation | Giữ riêng alert quan trọng |
| Video frame realtime | Drop-oldest hoặc latest-frame | Ưu tiên độ trễ thấp hơn đầy đủ |

Bảng là điểm khởi đầu. Một hệ thống có thể có nhiều consumer cho cùng một event: dashboard dùng latest-value, trong khi data lake nhận đầy đủ qua durable log.

## 17. Kiểm thử chính sách slow receiver

Mỗi policy cần được kiểm tra khi consumer nhanh, chậm, dừng hẳn và reconnect.

| Tình huống | Điều cần xác minh |
|---|---|
| Consumer xử lý bình thường | Không drop ngoài dự kiến, latency trong SLA |
| Consumer chậm trong burst ngắn | Buffer hấp thụ burst và trở lại mức bình thường |
| Producer nhanh liên tục | Queue không tăng vô hạn; overflow policy được kích hoạt |
| Drop newest | Phần tử mới bị drop đúng quy tắc, metric tăng |
| Drop oldest | Phần tử cũ nhất bị loại, giá trị mới vẫn đến |
| Latest-value | Consumer nhận giá trị mới nhất khi có demand |
| Sampling | Tần suất phát đúng giới hạn |
| Disconnect/replay | Không mất event đã lưu; event trùng được deduplicate |
| Cancellation | Nguồn và buffer được cleanup |
| Nhiều subscriber | Subscriber chậm không làm nghẽn subscriber khác |
| Payload lớn | Byte limit hoạt động dù số message ít |
| Restart server | Durable cursor và replay hoạt động theo hợp đồng |

Dùng StepVerifier để kiểm tra demand và cancellation ở mức publisher. Integration test nên chạy RSocket client/server thật để xác nhận REQUEST_N, channel hai chiều, cancellation và lỗi được truyền qua transport.

Ví dụ kiểm tra latest-value với một nguồn test có thể phát nhanh hơn demand:

~~~java
StepVerifier.create(
        Flux.just(1, 2, 3)
            .onBackpressureLatest(),
        0
    )
    .thenRequest(1)
    .expectNext(3)
    .thenCancel()
    .verify();
~~~

Test này minh họa chính sách latest-value: khi chưa có demand, các giá trị cũ bị thay thế và consumer nhận giá trị mới nhất khi yêu cầu một phần tử.

## 18. Checklist trước khi triển khai

- Đã phân loại dữ liệu: command, event, state, telemetry hay metric.
- Đã xác định dữ liệu có được phép mất không.
- Đã xác định thứ tự, độ mới, latency và durability cần thiết.
- Đã xác định nguồn có hỗ trợ backpressure hay là hot source.
- Buffer có giới hạn theo cả số phần tử và byte.
- Đã chọn hành vi khi queue đầy.
- Có metric cho lag, queue depth, byte, drop và replay.
- Có giới hạn concurrency, prefetch và active stream.
- Subscriber chậm được cách ly hoặc ngắt theo chính sách.
- Dữ liệu quan trọng có durable log/cursor và idempotency.
- Cancellation và timeout giải phóng tài nguyên.
- Đã kiểm thử consumer chậm, dừng hẳn, reconnect và nhiều subscriber.

## 19. Kết luận

Chọn chính sách cho bên nhận chậm là quyết định nghiệp vụ về độ đầy đủ, thứ tự, độ mới, độ trễ và khả năng phục hồi dữ liệu. Backpressure phù hợp khi nguồn có thể điều tiết theo demand và dữ liệu cần được giữ. Bounded buffer hấp thụ burst ngắn; khi queue đầy, phải có overflow policy rõ ràng. Drop newest, drop oldest, latest-value và sampling phù hợp với những luồng cho phép mất dữ liệu hoặc ưu tiên trạng thái mới. Với dữ liệu cần đầy đủ nhưng consumer có thể bị chậm lâu, hãy dùng durable log, cursor, disconnect và replay.

RSocket REQUEST_N giúp điều tiết số payload trên từng stream, còn request-channel có demand độc lập ở hai hướng. Nhưng flow control không giới hạn byte của từng payload và không thay thế quota, bounded queue, persistence hay authorization. Hãy đo lag, đặt ngưỡng, cách ly subscriber và kiểm thử mọi nhánh overflow/cancellation để một bên nhận chậm không làm suy giảm toàn bộ hệ thống realtime.

Tài liệu tham khảo:
- [Reactive Streams Specification](https://www.reactive-streams.org/)
- [Project Reactor Reference – Backpressure](https://projectreactor.io/docs/core/release/reference/coreFeatures/simple-ways-to-create-a-flux-or-mono-and-subscribe-to-it.html)
- [RSocket Protocol](https://rsocket.io/about/protocol/)


# Hàng đợi có giới hạn, điều tiết lưu lượng và loại tải

Một hệ thống reactive có thể tiếp nhận sự kiện nhanh hơn tốc độ mà các dịch vụ phía sau xử lý. Nếu cứ giữ mọi phần tử trong một hàng đợi không giới hạn, hệ thống có thể trông vẫn hoạt động trong một thời gian nhưng bộ nhớ tăng dần, độ trễ kéo dài và cuối cùng cạn tài nguyên. Khi đó, một đợt tăng tải ngắn có thể biến thành sự cố kéo dài.

Thiết kế hệ thống phản ứng cần quy định rõ lượng công việc được phép chờ, tốc độ công việc được đưa vào và cách xử lý khi năng lực xử lý đã đạt giới hạn. Hàng đợi có giới hạn, backpressure, giới hạn concurrency và load shedding là những công cụ bổ sung cho nhau. Chúng giúp hệ thống duy trì giới hạn tài nguyên và đưa ra phản hồi có thể dự đoán khi quá tải.

Bài học thuộc chương **Hệ thống phản ứng** của module **REACTIVE_PROGRAMMING**. Module hướng dẫn tư duy reactive qua các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và backpressure của Reactive Streams; người học thực hành **Mono**, **Flux**, kết hợp toán tử, kiểm soát scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java. Nội dung tập trung vào cách tổ chức hàng đợi, điều tiết lưu lượng và loại bỏ công việc khi năng lực hệ thống không đủ đáp ứng.

## Vì sao hàng đợi phải có giới hạn?

Hàng đợi hấp thụ chênh lệch tạm thời giữa tốc độ đến và tốc độ xử lý. Nếu tốc độ đến thấp hơn tốc độ xử lý trong thời gian đủ dài, hàng đợi có thể trở về trạng thái rỗng. Nếu tốc độ đến cao hơn tốc độ xử lý liên tục, số phần tử chờ sẽ tăng cho đến khi một giới hạn tài nguyên bị chạm tới.

Giả sử một dịch vụ có khả năng xử lý trung bình 400 yêu cầu mỗi giây, nhưng trong một đợt tải nó nhận 500 yêu cầu mỗi giây. Mỗi giây có thêm khoảng 100 yêu cầu chờ. Hàng đợi chứa 2.000 yêu cầu có thể đầy sau khoảng 20 giây nếu chênh lệch tốc độ giữ nguyên. Hàng đợi chỉ trì hoãn thời điểm quá tải; nó không làm tăng năng lực xử lý của dịch vụ.

Một hàng đợi không giới hạn có thể gây ra:

- **Tăng bộ nhớ:** mỗi phần tử chờ giữ payload, metadata và tham chiếu tới các đối tượng liên quan.
- **Tăng độ trễ:** yêu cầu nằm lâu trong hàng đợi trước khi được xử lý.
- **Cạn tài nguyên ở tầng sau:** worker, connection, buffer hoặc transaction bị giữ lâu hơn.
- **Hiệu ứng dây chuyền:** một dịch vụ chậm khiến hàng đợi của dịch vụ gọi nó tăng, rồi làm các dịch vụ khác cũng chậm.
- **Xử lý công việc đã lỗi thời:** yêu cầu có thể hết hạn trước khi đến lượt xử lý.

Giới hạn hàng đợi là một phần của hợp đồng vận hành. Khi hàng đợi đầy, hệ thống cần một chính sách rõ ràng: làm chậm nguồn, từ chối yêu cầu mới, bỏ dữ liệu có thể bỏ, gộp sự kiện, chuyển công việc sang lưu trữ bền vững hoặc trả lỗi có thể thử lại.

## Ước lượng kích thước hàng đợi

Không nên chọn kích thước hàng đợi chỉ bằng cách thử một con số lớn rồi quan sát xem hệ thống có hết bộ nhớ hay không. Hãy bắt đầu từ giới hạn độ trễ và năng lực xử lý.

Định luật Little mô tả quan hệ giữa số phần tử trung bình trong hệ thống, tốc độ hoàn tất và thời gian lưu lại:

\[
L = \lambda W
\]

Trong đó:

- \(L\) là số công việc trung bình đang ở trong hệ thống, gồm cả đang xử lý và đang chờ nếu đo toàn bộ hệ thống.
- \(\lambda\) là tốc độ hoàn tất trung bình, tính bằng công việc mỗi giây trong trạng thái ổn định.
- \(W\) là thời gian trung bình một công việc ở trong hệ thống.

Nếu chỉ xét hàng đợi, dùng quan hệ `Lq = λWq`: `Lq` là số công việc trung bình đang chờ và `Wq` là thời gian chờ trung bình trước khi được xử lý. Không dùng thời gian chờ trong hàng đợi để tính số công việc của toàn hệ thống, vì `L` và `W` ở công thức phía trên bao gồm cả thời gian đang xử lý.

Nếu một dịch vụ hoàn tất 400 yêu cầu mỗi giây và mục tiêu thời gian chờ trung bình trong hàng đợi là khoảng 2 giây, số yêu cầu chờ trung bình tương ứng xấp xỉ 800 theo quan hệ `Lq = λWq` trong điều kiện ổn định. Đây là ước lượng ban đầu, không phải bảo đảm độ trễ tối đa hay kích thước buffer bắt buộc. Tải theo burst, phân bố thời gian xử lý, kích thước payload và số worker đồng thời đều ảnh hưởng kết quả thực tế.

Khi chọn giới hạn, hãy xét đồng thời:

1. Tốc độ đến bình thường và tốc độ đến trong burst.
2. Throughput xử lý ổn định của từng tầng.
3. Độ trễ chờ tối đa mà nghiệp vụ chấp nhận.
4. Bộ nhớ trung bình và trường hợp payload lớn.
5. Số phần tử đang được xử lý đồng thời ngoài hàng đợi.
6. Thời gian hết hạn của yêu cầu và giá trị của công việc khi đã cũ.

Nếu kích thước phần tử thay đổi mạnh, giới hạn số phần tử chưa đủ để bảo vệ bộ nhớ. Có thể cần thêm giới hạn byte, giới hạn payload hoặc từ chối các thông điệp quá lớn. Hãy tính cả phần tử đang được xử lý, prefetch và các hàng đợi ở những toán tử khác; một hàng đợi 1.000 phần tử không có nghĩa toàn pipeline chỉ giữ tối đa 1.000 phần tử.

## Backpressure điều tiết demand, còn hàng đợi giữ phần tử chờ

Reactive Streams định nghĩa giao thức demand: Subscriber gọi `request(n)` để yêu cầu Publisher phát tối đa số phần tử đã yêu cầu. Một Publisher tuân thủ giao thức sẽ không phát `onNext` vượt quá demand còn lại. Backpressure giúp downstream điều tiết tốc độ phát dữ liệu từ upstream khi cả hai đầu hỗ trợ giao thức này.

Hàng đợi giải quyết một vấn đề khác: giữ những phần tử đã được tiếp nhận nhưng chưa thể xử lý ngay. Hàng đợi hữu ích khi cần hấp thụ burst hoặc tách producer khỏi consumer. Nếu hàng đợi không có giới hạn, nó có thể che giấu việc upstream và downstream mất cân bằng.

Hai cơ chế thường phối hợp:

- Backpressure giảm hoặc trì hoãn việc upstream phát phần tử theo demand.
- Hàng đợi có giới hạn hấp thụ một lượng công việc đã được chấp nhận trong thời gian ngắn.
- Khi hàng đợi đạt giới hạn, chính sách overflow quyết định bước tiếp theo.

Không phải mọi nguồn đều có thể bị backpressure. Ví dụ, callback từ thiết bị, message broker cấu hình push, sự kiện giao diện hoặc UDP packet có thể tiếp tục đến dù downstream chưa sẵn sàng. Ở ranh giới đó, adapter phải chọn cách buffer, drop, coalesce hoặc báo lỗi. Không thể chỉ thêm `Flux` rồi giả định producer bên ngoài sẽ tự chậm lại.

## Các chính sách khi hàng đợi đầy

Một hàng đợi có giới hạn cần chính sách overflow phù hợp với ý nghĩa dữ liệu:

| Chính sách | Hành vi | Dữ liệu phù hợp |
|---|---|---|
| Backpressure / chờ | Yêu cầu producer chậm lại nếu giao thức hỗ trợ | Luồng có thể điều tiết và không được mất phần tử |
| Reject / error | Từ chối phần tử mới hoặc kết thúc luồng bằng lỗi | Lệnh cần xác nhận rõ ràng khi hệ thống không nhận thêm |
| Drop newest | Bỏ phần tử mới đến khi hàng đợi đầy | Sự kiện phụ có thể bỏ, phần tử cũ đang chờ có giá trị hơn |
| Drop oldest | Bỏ phần tử cũ nhất để nhận dữ liệu mới | Dữ liệu trạng thái gần nhất quan trọng hơn lịch sử chờ |
| Keep latest | Chỉ giữ giá trị mới nhất | Trạng thái cảm biến hoặc vị trí hiện tại, nơi giá trị cũ nhanh chóng lỗi thời |
| Coalesce / aggregate | Gộp nhiều sự kiện thành một cập nhật | Bộ đếm, số liệu tổng hợp hoặc thay đổi có thể gộp |
| Durable queue | Ghi công việc vào broker hoặc kho bền vững | Công việc cần được xử lý sau, kể cả khi tiến trình khởi động lại |

Không có chính sách tốt cho mọi loại dữ liệu. Bỏ một bản cập nhật vị trí cũ có thể chấp nhận được; bỏ một lệnh chuyển tiền hoặc lệnh tạo đơn hàng thì không. Với lệnh quan trọng, reject phải trả phản hồi rõ ràng để caller có thể thử lại theo idempotency key hoặc đưa vào luồng xử lý khác.

## Dùng các toán tử Reactor để biểu diễn overflow policy

Reactor cung cấp các toán tử backpressure cho `Flux`. Chúng đặc biệt hữu ích ở ranh giới mà nguồn có thể phát nhanh hơn downstream:

~~~java
Flux<Reading> latestReadings = sensorEvents
    .onBackpressureLatest()
    .publishOn(processingScheduler);
~~~

`onBackpressureLatest()` giữ giá trị mới nhất khi downstream chưa có demand. Chính sách này phù hợp với trạng thái cảm biến hiện tại nếu các mẫu cũ không còn giá trị khi mẫu mới đã đến. Nó không phù hợp với luồng sự kiện mà mọi phần tử đều phải được ghi nhận.

Nếu có thể bỏ từng phần tử mới khi downstream chưa sẵn sàng:

~~~java
Flux<AuditHint> hints = incomingHints
    .onBackpressureDrop(dropped ->
        metrics.recordDroppedHint(dropped.type()));
~~~

Callback giúp quan sát số lượng và loại dữ liệu bị bỏ. Không nên bỏ dữ liệu một cách im lặng nếu việc mất phần tử ảnh hưởng đến nghiệp vụ hoặc khả năng điều tra.

Với dữ liệu cần được giữ trong một khoảng đệm hữu hạn, có thể dùng buffer có giới hạn:

~~~java
Flux<Command> commands = incomingCommands
    .onBackpressureBuffer(500);
~~~

Khi buffer đầy, overload giới hạn sẽ phát lỗi overflow. Ứng dụng cần xử lý lỗi đó ở ranh giới phù hợp và trả phản hồi từ chối hoặc kích hoạt chính sách quá tải. Không nên đổi sang buffer không giới hạn chỉ để tránh nhìn thấy lỗi.

Nếu dữ liệu có thể bỏ phần tử cũ nhất, Reactor hỗ trợ chiến lược overflow tường minh:

~~~java
Flux<DashboardUpdate> dashboardUpdates = incomingUpdates
    .onBackpressureBuffer(
        100,
        dropped -> metrics.recordEvictedUpdate(),
        BufferOverflowStrategy.DROP_OLDEST
    );
~~~

`DROP_OLDEST` chỉ phù hợp khi cập nhật mới thay thế được cập nhật cũ. Với command hoặc audit record cần bảo toàn, hãy chọn reject hoặc lưu bền vững. Các toán tử này kiểm soát hành vi tại ranh giới trong pipeline Reactor; chúng không tự cấu hình giới hạn hàng đợi ở message broker, web server, driver hoặc thư viện nguồn. Các toán tử `onBackpressureBuffer`, `onBackpressureDrop` và `onBackpressureLatest` có thể yêu cầu upstream phát không giới hạn rồi tự buffer hoặc loại phần tử khi downstream thiếu demand. Vì vậy, chúng là chính sách xử lý tại ranh giới, không phải bằng chứng rằng producer bên ngoài đã được làm chậm. Nếu nguồn hỗ trợ demand và mục tiêu là điều tiết upstream, hãy ưu tiên để demand truyền ngược hoặc dùng cơ chế request phù hợp.

## Điều tiết concurrency của công việc bất đồng bộ

Ngay cả khi hàng đợi đầu vào có giới hạn, pipeline vẫn có thể tạo quá nhiều thao tác đồng thời ở downstream. `flatMap` cho phép giới hạn số Publisher con đang hoạt động:

~~~java
Flux<ProcessedOrder> processedOrders = orderIds
    .flatMap(
        orderId -> orderService.process(orderId),
        32,
        1
    );
~~~

Trong ví dụ:

- `32` giới hạn số Publisher con hoạt động đồng thời.
- `1` là prefetch cho mỗi Publisher con.
- Các kết quả được phát khi từng Publisher con hoàn tất; thứ tự giữa các đơn hàng không được bảo toàn.

Giới hạn concurrency bảo vệ các tài nguyên phía sau như connection pool hoặc dịch vụ HTTP. Prefetch kiểm soát lượng phần tử được yêu cầu trước từ mỗi Publisher con; nó không phải giới hạn bộ nhớ tổng của toàn pipeline. Các toán tử khác vẫn có thể có hàng đợi và buffer riêng.

Nếu cần xử lý tuần tự và giữ thứ tự theo đầu vào, dùng `concatMap`:

~~~java
Flux<ProcessedOrder> processedOrders = orderIds
    .concatMap(orderId -> orderService.process(orderId));
~~~

`concatMap` chỉ đăng ký Publisher con tiếp theo sau khi Publisher hiện tại hoàn tất. Cách này giảm số công việc đồng thời nhưng có thể giảm throughput nếu mỗi thao tác mất nhiều thời gian.

Đừng dùng concurrency lớn để che giấu một dịch vụ downstream chậm. Hãy đo thời gian xử lý và đặt giới hạn dựa trên năng lực thực tế của dịch vụ đó.

## limitRate và giới hạn tốc độ là hai khái niệm khác nhau

`limitRate(n)` chia demand downstream thành các request nhỏ hơn khi yêu cầu upstream. Nó giúp điều tiết lượng phần tử được yêu cầu trước và có thể giảm burst tại một ranh giới:

~~~java
Flux<Event> controlled = source
    .limitRate(64)
    .publishOn(workerScheduler);
~~~

`limitRate` không phải bộ giới hạn tốc độ theo giây. Nó không có nghĩa hệ thống chỉ xử lý tối đa 64 phần tử mỗi giây. Nó điều chỉnh cách request được chia lô, còn tốc độ thực tế phụ thuộc nguồn, thời gian xử lý và demand downstream.

Nếu cần giới hạn theo thời gian, ví dụ tối đa 100 request mỗi giây tới một dịch vụ bên ngoài, cần một rate limiter theo cửa sổ thời gian hoặc token bucket. Có thể dùng thư viện rate limiting, gateway hoặc một thành phần điều phối riêng. `delayElements` có thể làm chậm việc phát phần tử trong một pipeline đơn giản, nhưng không thay thế đầy đủ rate limiter khi cần quota theo key, burst allowance, chia sẻ giới hạn giữa nhiều instance hoặc phối hợp với retry.

## Admission control và load shedding

Admission control quyết định có nhận thêm công việc hay không trước khi đưa nó vào hàng đợi hoặc cấp tài nguyên. Load shedding loại bỏ công việc mà hệ thống không thể xử lý trong giới hạn đã định. Hai cơ chế này giúp hệ thống từ chối sớm thay vì nhận mọi yêu cầu rồi để chúng chờ đến khi hết hạn.

Một request có thể bị từ chối khi:

- Số tác vụ đang hoạt động đã đạt giới hạn.
- Hàng đợi đã đầy.
- Deadline còn lại ngắn hơn thời gian xử lý dự kiến.
- Một dependency đang ở trạng thái quá tải hoặc circuit breaker đang mở.
- Request thuộc loại ưu tiên thấp trong lúc hệ thống cần bảo vệ tác vụ quan trọng.

Ví dụ ở tầng HTTP, hệ thống có thể trả `429 Too Many Requests` khi client vượt quota hoặc `503 Service Unavailable` khi dịch vụ tạm thời không thể nhận thêm công việc. Phản hồi nên kèm thông tin retry phù hợp nếu hệ thống có thể ước lượng thời điểm thử lại. Không nên yêu cầu client retry ngay lập tức theo vòng lặp dày đặc, vì điều đó có thể khuếch đại quá tải.

Với một luồng sự kiện, có thể loại bỏ các cập nhật đã lỗi thời trước khi đưa vào công việc tốn tài nguyên:

~~~java
Flux<Position> positions = incomingPositions
    .sample(Duration.ofMillis(100))
    .flatMap(position -> routeService.recalculate(position), 8);
~~~

`sample` chỉ giữ mẫu theo chu kỳ và bỏ qua các phần tử xen giữa. Cách này có thể phù hợp với giao diện theo dõi vị trí nếu chỉ cần cập nhật gần nhất theo nhịp 100 ms. Nó không phù hợp với nhật ký định vị cần lưu mọi điểm hoặc tính toán quãng đường chính xác từ từng mẫu.

Load shedding phải dựa trên ý nghĩa nghiệp vụ. Có thể bỏ telemetry phụ hoặc gộp cập nhật dashboard; không được tự ý bỏ lệnh ghi dữ liệu quan trọng, thanh toán hoặc audit.

## Hàng đợi trong bộ nhớ hay hàng đợi bền vững?

Hàng đợi trong bộ nhớ phù hợp để hấp thụ burst ngắn và điều phối công việc trong vòng đời một tiến trình. Nếu tiến trình dừng hoặc bị khởi động lại, các phần tử chưa xử lý có thể mất. Hàng đợi bền vững như message broker phù hợp khi công việc phải tồn tại qua lần deploy, restart hoặc sự cố máy.

| Tiêu chí | Hàng đợi trong bộ nhớ | Hàng đợi bền vững |
|---|---|---|
| Độ trễ | Thường thấp | Có thêm chi phí ghi/đọc và mạng |
| Khả năng chịu restart | Mất phần tử chưa xử lý nếu không có cơ chế khôi phục | Có thể giữ thông điệp qua restart |
| Giới hạn tài nguyên | Cần giới hạn bộ nhớ của tiến trình | Cần quota, retention và giới hạn broker |
| Điều phối consumer | Thường nằm trong ứng dụng | Broker hỗ trợ consumer group hoặc cơ chế tương đương |
| Xử lý lại | Ứng dụng phải tự thiết kế | Thường có cơ chế redelivery, offset hoặc acknowledgement |

Chuyển công việc sang broker không làm quá tải biến mất. Broker cũng cần giới hạn dung lượng, retention, consumer throughput và chính sách khi backlog tăng. Hãy theo dõi tuổi của thông điệp cũ nhất, tốc độ tăng backlog và tốc độ consumer xử lý.

## Đo lường tình trạng quá tải

Chỉ đo CPU và bộ nhớ chưa đủ để phát hiện hàng đợi đang trở thành nút thắt. Nên theo dõi:

- **Queue depth:** số phần tử đang chờ.
- **Queue age:** tuổi của phần tử cũ nhất hoặc thời gian chờ trước khi xử lý.
- **Enqueue/dequeue rate:** tốc độ nhận và lấy công việc.
- **Active work:** số thao tác đang chạy đồng thời.
- **Rejected/dropped count:** số yêu cầu bị từ chối hoặc phần tử bị bỏ.
- **Processing latency:** thời gian xử lý ở từng tầng.
- **Timeout and cancellation rate:** số thao tác hết hạn hoặc bị hủy.
- **Resource saturation:** connection pool pending, worker utilization, buffer và bộ nhớ.

Queue depth thấp không luôn đồng nghĩa hệ thống khỏe. Một hàng đợi nhỏ nhưng chứa các công việc đã chờ quá lâu có thể đã vi phạm deadline. Ngược lại, một hàng đợi có độ sâu lớn nhưng được tiêu thụ nhanh và vẫn trong ngân sách độ trễ có thể chưa phải sự cố. Kết hợp độ sâu với tuổi phần tử và tốc độ tăng backlog sẽ giúp quyết định chính xác hơn.

Khi cảnh báo, hãy dùng ngưỡng gắn với năng lực và SLA. Ví dụ, cảnh báo khi queue age vượt deadline nội bộ hoặc khi tốc độ enqueue liên tục cao hơn dequeue. Tránh cảnh báo chỉ theo một giá trị queue depth cố định mà không xét kích thước payload và throughput.

## Kiểm thử hành vi khi quá tải

Kiểm thử cần xác nhận chính sách overflow, không chỉ xác nhận pipeline hoạt động khi tải thấp. Với nguồn không tuân theo demand hoặc producer phát nhanh, có thể kiểm tra các trường hợp:

1. Buffer còn chỗ: phần tử được giữ và xử lý khi downstream có demand.
2. Buffer đầy: phần tử mới bị reject, drop hoặc thay thế theo chính sách đã chọn.
3. Consumer chậm: queue age tăng nhưng vẫn nằm trong giới hạn chấp nhận.
4. Subscription bị hủy: công việc không còn cần thiết được dừng hoặc giải phóng tài nguyên theo khả năng nguồn.
5. Burst kết thúc: tốc độ dequeue vượt enqueue và backlog giảm về mức bình thường.

Ví dụ minh họa kiểm tra overflow của buffer có giới hạn bằng `StepVerifier`:

~~~java
Flux<Integer> bounded = Flux.range(1, 10)
    .onBackpressureBuffer(2);

StepVerifier.create(bounded, 0)
    .expectErrorMatches(Exceptions::isOverflow)
    .verify();
~~~

`StepVerifier` bắt đầu với demand bằng 0. Buffer có giới hạn chỉ giữ được một số phần tử; khi nguồn đồng bộ phát vượt sức chứa, pipeline kết thúc bằng lỗi overflow. Kiểm thử thực tế nên dùng đúng loại nguồn mà hệ thống tích hợp, vì nguồn tuân thủ demand có thể tự chờ thay vì làm đầy buffer.

Với chính sách drop hoặc latest, hãy kiểm thử rõ phần tử nào được giữ và ghi nhận số lượng phần tử bị bỏ. Với admission control ở tầng HTTP hoặc broker, cần integration test để xác nhận phản hồi từ chối, quota, retry-after và hành vi khi nhiều request đồng thời.

## Những lỗi thường gặp

| Cách làm | Vấn đề | Cách xử lý |
|---|---|---|
| Dùng buffer không giới hạn | Backlog có thể chiếm hết bộ nhớ | Đặt giới hạn và chính sách overflow |
| Tăng queue size để giải quyết throughput thấp | Chỉ kéo dài thời gian trước khi đầy và tăng độ trễ | Tăng năng lực xử lý hoặc giảm tải đầu vào |
| Drop mọi phần tử khi quá tải | Có thể làm mất command hoặc dữ liệu audit | Chọn policy theo ngữ nghĩa dữ liệu |
| Cho rằng `limitRate(64)` là 64 phần tử/giây | `limitRate` điều chỉnh demand theo lô, không đặt quota thời gian | Dùng rate limiter theo thời gian |
| Chỉ giới hạn hàng đợi mà không giới hạn concurrency | Quá nhiều thao tác đang chạy vẫn có thể chiếm tài nguyên | Kết hợp queue capacity và concurrency cap |
| Dùng `onBackpressureLatest` cho lệnh nghiệp vụ | Lệnh cũ có thể bị thay thế và không được thực hiện | Dùng reject hoặc durable queue |
| Chỉ theo dõi queue depth | Bỏ sót phần tử đã chờ quá lâu | Theo dõi cả queue age và throughput |
| Retry ngay khi bị từ chối | Tạo thêm tải trong lúc hệ thống quá tải | Backoff, jitter và quota retry |

## Nguyên tắc thiết kế

Khi thiết kế hàng đợi và chính sách điều tiết lưu lượng, hãy xác định:

1. Nguồn có hỗ trợ backpressure hay tiếp tục phát độc lập với demand?
2. Mỗi loại phần tử có được phép drop, gộp hoặc thay thế không?
3. Kích thước hàng đợi dựa trên ngân sách độ trễ, throughput và bộ nhớ nào?
4. Concurrency tối đa ở từng tầng là bao nhiêu?
5. Khi đầy, hệ thống chờ, từ chối, bỏ, gộp hay lưu bền vững?
6. Công việc còn giá trị khi đã chờ lâu hay cần loại bỏ theo deadline?
7. Queue depth, queue age, throughput, rejection và resource saturation được quan sát ra sao?
8. Kiểm thử có mô phỏng burst, consumer chậm, overflow và cancellation không?

Hàng đợi có giới hạn bảo vệ bộ nhớ và độ trễ; backpressure điều tiết demand; concurrency cap bảo vệ tài nguyên xử lý; admission control và load shedding giúp từ chối công việc khi hệ thống không còn khả năng nhận thêm. Khi chọn chính sách theo ý nghĩa dữ liệu và đo cả độ sâu lẫn tuổi hàng đợi, hệ thống reactive có thể duy trì hành vi ổn định hơn trong những đợt tải tăng đột biến.

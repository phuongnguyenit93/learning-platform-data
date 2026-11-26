# Queue

Trong module **SPRING_MODULITH_APPLICATION_EVENTS**, application events giúp các module Spring Modulith giao tiếp qua publisher và listener. Khi sự kiện cần đi qua RabbitMQ, queue là nơi broker giữ message để consumer có thể nhận và xử lý theo tốc độ của mình. Thiết kế queue ảnh hưởng đến khả năng chịu tải, độ bền dữ liệu, thứ tự xử lý, retry và phục hồi khi consumer gặp sự cố.

Queue không tự quyết định message nào được gửi vào nó. Trong mô hình AMQP 0-9-1 của RabbitMQ, publisher gửi message đến exchange; exchange định tuyến message qua binding đến một hoặc nhiều queue. Consumer đăng ký nhận message từ queue. Hiểu rõ ba thành phần exchange, binding và queue là nền tảng để thiết kế luồng event đáng tin cậy.

## 1. Queue trong mô hình RabbitMQ

Queue là vùng lưu message đang chờ consumer xử lý. Một queue có tên, thuộc tính và vòng đời riêng. Message được đưa vào queue thông qua quy tắc định tuyến của exchange; consumer lấy message ra và xác nhận khi xử lý theo chính sách acknowledgement.

Một luồng cơ bản:

1. Publisher gửi message đến exchange.
2. Exchange xét loại exchange, routing key và binding.
3. RabbitMQ định tuyến message đến queue phù hợp.
4. Queue giữ message cho đến khi consumer nhận và xử lý.
5. Consumer gửi acknowledgement (ack) hoặc negative acknowledgement (nack/reject).
6. Broker xóa message đã được xác nhận, hoặc xử lý message bị từ chối theo cấu hình requeue/dead-letter.

Các thành phần:

| Thành phần | Trách nhiệm | Ví dụ |
|---|---|---|
| Exchange | Nhận message từ publisher và định tuyến | orders.events |
| Binding | Quy tắc nối exchange với queue | routing key orders.confirmed |
| Queue | Giữ message chờ consumer | orders.confirmed.q |
| Publisher | Phát message | Module Đơn hàng |
| Consumer | Nhận và xử lý message | Dịch vụ Kho |

Trong exchange kiểu direct, routing key phải khớp binding key. Topic exchange hỗ trợ pattern như **orders.*** hoặc **orders.#**. Fanout exchange phát message đến tất cả queue được bind. Headers exchange định tuyến dựa trên header. Việc chọn exchange quyết định cách message đến queue; queue quyết định cách message được lưu và giao cho consumer.

Một event có thể được định tuyến đến nhiều queue để nhiều consumer xử lý độc lập. Ví dụ, OrderConfirmed có thể đến queue của Kho, Hóa đơn và Phân tích. Mỗi consumer có backlog, tốc độ và chính sách retry riêng.

## 2. Chọn tên queue và ranh giới trách nhiệm

Tên queue nên cho biết domain hoặc consumer sở hữu và loại message được nhận. Ví dụ:

- **orders.fulfillment.q**: consumer Kho nhận sự kiện liên quan đến thực hiện đơn.
- **orders.invoice.q**: consumer Hóa đơn nhận sự kiện đơn hàng cần lập hóa đơn.
- **orders.analytics.q**: consumer Phân tích nhận sự kiện đơn hàng.
- **orders.confirmed.dlq**: nơi cách ly message không thể xử lý sau chính sách retry.

Không nên dùng một queue chung cho mọi loại event nếu chúng có mức ưu tiên, quyền truy cập, tốc độ xử lý hoặc retention khác nhau. Một consumer chậm có thể làm queue chung tăng backlog và ảnh hưởng các nhóm công việc không liên quan.

Cũng không nên tạo queue riêng cho từng message nếu không có nhu cầu độc lập. Mỗi queue tạo thêm topology, binding, ACL, metric, cảnh báo, retention và quy trình vận hành. Hãy nhóm queue theo consumer hoặc luồng nghiệp vụ có cùng yêu cầu xử lý.

Đối với nhiều instance của cùng một consumer, các instance thường cùng consume một queue theo mô hình competing consumers. RabbitMQ phân phối message cho các consumer đang đăng ký queue đó. Nếu muốn nhiều hệ thống độc lập đều nhận một bản sao message, hãy tạo queue riêng cho từng hệ thống và bind từng queue vào exchange; nhiều consumer cùng đọc một queue không tạo ra bản sao cho mỗi consumer.

## 3. Khai báo queue và thuộc tính

Queue có thể được khai báo chủ động qua ứng dụng hoặc được tạo sẵn bởi hạ tầng. Khai báo thường bao gồm:

- Tên queue.
- Durable hay transient.
- Exclusive hay không.
- Auto-delete hay không.
- Các argument bổ sung như queue type, TTL, dead-letter exchange, max length hoặc priority.

Khai báo queue đã tồn tại với cùng thuộc tính thường là thao tác idempotent. Tuy nhiên, nếu ứng dụng khai báo lại cùng tên nhưng thuộc tính không tương thích, broker có thể từ chối bằng lỗi channel như **PRECONDITION_FAILED**. Vì vậy, tên và cấu hình queue cần được quản lý như một phần của topology, không phải thay đổi tùy tiện lúc runtime.

Nên thống nhất một nguồn sở hữu topology. Nếu ứng dụng tự khai báo queue, exchange và binding, cần đảm bảo mọi instance triển khai cùng cấu hình. Nếu đội nền tảng quản lý topology tập trung, ứng dụng phải khai báo đúng tên và quyền truy cập được cấp.

## 4. Durable queue và persistent message

Hai khái niệm thường bị nhầm lẫn:

- **Durable queue**: định nghĩa queue được giữ qua lần broker restart theo cơ chế lưu trữ của RabbitMQ.
- **Persistent message**: message được đánh dấu persistent để broker có thể lưu bền vững theo cơ chế tương ứng.

Một durable queue không tự biến mọi message trong đó thành persistent. Ngược lại, message persistent được publish đến queue transient cũng không giúp queue tồn tại qua restart.

Với event nghiệp vụ cần giao đáng tin cậy, thường cần đánh giá đồng thời:

1. Queue có durable hay không.
2. Message có delivery mode persistent hay không.
3. Publisher có publisher confirms để biết broker đã xác nhận nhận message hay không.
4. Consumer có acknowledgement sau xử lý hay không.
5. Broker có cơ chế lưu trữ và replication phù hợp với mức độ quan trọng của dữ liệu hay không.

Durability không đồng nghĩa với bảo đảm tuyệt đối không mất dữ liệu. Cần hiểu cấu hình node, storage, replication, disk alarm, backup và cách broker xác nhận message. Publisher confirm chỉ xác nhận broker đã xử lý publish theo semantics của nó; nó không chứng minh consumer đã hoàn tất nghiệp vụ.

## 5. Chọn queue type

RabbitMQ cung cấp các loại queue với đặc tính và trade-off khác nhau. Hãy chọn theo yêu cầu độ bền, thông lượng, thứ tự và khả năng vận hành.

### Classic queue

Classic queue là loại queue thông dụng cho nhiều trường hợp cơ bản. Nó phù hợp với workload không cần replication dữ liệu queue ở mức quorum. Có thể dùng durable classic queue cùng persistent message và publisher confirms, nhưng mức chịu lỗi node khác với quorum queue.

Không nên dựa vào cơ chế mirrored classic queue cũ cho kiến trúc mới; RabbitMQ đã loại bỏ classic queue mirroring khỏi các phiên bản hiện đại. Nếu cần queue replicated và khả năng chịu lỗi node, hãy đánh giá quorum queue.

### Quorum queue

Quorum queue là loại queue replicated dựa trên Raft, phù hợp với message quan trọng cần khả năng chịu lỗi node. Queue cần một nhóm replica và hoạt động theo quorum để duy trì tính nhất quán.

Quorum queue thường phù hợp với command hoặc event nghiệp vụ cần lưu bền vững và có yêu cầu phục hồi cao. Đổi lại, replication tạo thêm chi phí network, disk và tài nguyên; số replica, vị trí node và quorum cần được thiết kế phù hợp.

Không nên chọn quorum queue chỉ vì nó có chữ “quorum”. Hãy đánh giá throughput, latency, kích thước message, thời gian lưu, số queue và khả năng vận hành cluster. Với message có thể tái tạo hoặc dữ liệu telemetry có thể mất theo chính sách, classic queue có thể là lựa chọn phù hợp hơn.

### Stream

RabbitMQ Streams là cấu trúc lưu message dạng append-only log, hỗ trợ đọc lại và nhiều consumer offset độc lập. Stream có semantics khác queue truyền thống: consumer có thể đọc lại dữ liệu theo offset và message không bị loại khỏi log theo acknowledgement của một queue thông thường.

Nếu yêu cầu là phân phối công việc cho competing consumers và xóa message sau khi xử lý, queue truyền thống thường phù hợp hơn. Nếu cần replay lịch sử, nhiều consumer đọc độc lập hoặc retention theo log, hãy đánh giá Streams như một mô hình khác thay vì xem nó là một queue type tương đương.

## 6. Exclusive, auto-delete và queue tạm thời

Queue có thể được khai báo với vòng đời khác nhau:

- **Exclusive queue** chỉ được kết nối sở hữu sử dụng và thường bị xóa khi connection sở hữu đóng.
- **Auto-delete queue** được xóa sau khi consumer cuối cùng đã đăng ký rời đi, theo điều kiện của broker.
- **Server-named queue** để broker sinh tên, hữu ích cho queue tạm thời hoặc reply queue.

Các thuộc tính này phù hợp với reply-to, RPC tạm thời hoặc subscription có vòng đời ngắn. Không nên dùng exclusive hoặc auto-delete cho queue nghiệp vụ cần tồn tại khi ứng dụng restart hoặc khi consumer tạm thời offline.

Với queue tạm thời, hãy xác định timeout và hành vi khi connection bị ngắt. Nếu reply đến sau khi queue đã bị xóa, publisher hoặc requester cần có quy tắc xử lý timeout rõ ràng.

## 7. Binding và định tuyến message vào queue

Queue không tự lọc event theo nội dung payload. Exchange quyết định định tuyến qua binding.

Ví dụ với direct exchange:

~~~text
Exchange: orders.events
Binding key: orders.confirmed
Queue: orders.fulfillment.q
~~~

Publisher gửi message có routing key **orders.confirmed**. Exchange direct tìm binding key tương ứng và đưa message vào queue.

Với topic exchange, có thể dùng pattern:

| Binding key | Match |
|---|---|
| orders.* | Một segment sau orders |
| orders.# | Không hoặc nhiều segment sau orders |
| orders.confirmed | Chỉ routing key chính xác này |
| *.confirmed | Một segment bất kỳ trước confirmed |

Một message có thể được định tuyến đến nhiều queue nếu nhiều binding khớp. Nếu không có queue phù hợp, message có thể bị discard hoặc trả về publisher tùy thuộc mandatory flag, alternate exchange và cấu hình. Với message quan trọng, hãy thiết kế xử lý unroutable message và kiểm tra publisher confirms cùng return callback theo semantics của client.

## 8. Consumer acknowledgement

Acknowledgement cho broker biết consumer đã xử lý message đến đâu. Đây là một phần cốt lõi của độ tin cậy.

Các chế độ thường gặp:

- **Automatic acknowledgement ở giao thức RabbitMQ (autoAck=true):** broker xem message đã được xác nhận ngay khi giao cho consumer. Nếu consumer chết trước khi xử lý xong, message có thể mất khỏi queue.
- **Manual acknowledgement:** consumer gửi ack sau khi xử lý thành công; nếu connection đóng trước ack, broker có thể giao lại message.
- **Negative acknowledgement (nack/reject):** consumer từ chối message. Tùy cờ requeue và cấu hình dead-letter, message có thể được đưa lại queue hoặc chuyển sang dead-letter exchange.

Với event nghiệp vụ, acknowledgement nên xảy ra sau khi consumer hoàn thành công việc cần bảo vệ. Nếu consumer cập nhật database rồi ack, có một cửa sổ lỗi: database commit thành công nhưng ack bị mất. Broker có thể giao message lại. Vì vậy, consumer cần idempotency để xử lý lặp an toàn.

Ack không tạo transaction nguyên tử giữa RabbitMQ và database ứng dụng. Nếu cần đồng bộ trạng thái database và việc ghi nhận message đã xử lý, có thể lưu event ID đã xử lý trong cùng transaction với thay đổi nghiệp vụ, sau đó ack sau commit.

Lưu ý tên chế độ dễ gây nhầm: **AUTO** của Spring AMQP không đồng nghĩa với cờ **autoAck=true** của giao thức RabbitMQ. Với Spring AMQP AUTO, listener container gửi ack khi listener hoàn tất thành công; nếu listener ném exception, hành vi retry/requeue phụ thuộc cấu hình container và recoverer.

## 9. Prefetch và số message đang xử lý

Prefetch giới hạn số message chưa được acknowledge mà broker có thể giao trước cho consumer. Nó ảnh hưởng lượng công việc đang nằm trong bộ nhớ consumer và cách phân phối message giữa các consumer.

- Prefetch quá lớn có thể khiến một consumer nhận nhiều message hơn khả năng xử lý, làm tăng memory và thời gian chờ.
- Prefetch quá nhỏ có thể làm giảm throughput khi message có latency xử lý cao.
- Prefetch cần được chọn cùng concurrency, số consumer, kích thước message và năng lực database/downstream.
- Khi dùng nhiều consumer, cần quan sát phân phối message để tránh một consumer giữ quá nhiều message đang chờ ack.

Prefetch là một phần của backpressure phía consumer. Nó không giới hạn tổng dung lượng queue và không tự điều tiết tốc độ publisher. Muốn kiểm soát toàn luồng, cần kết hợp giới hạn consumer với admission control, publisher flow control và giám sát backlog.

## 10. TTL, queue length và overflow

RabbitMQ hỗ trợ các giới hạn vòng đời và dung lượng cho queue/message.

### Message TTL và queue TTL

Message TTL xác định khoảng thời gian message được phép nằm trong queue. Message hết hạn có thể bị loại bỏ hoặc dead-letter tùy cấu hình. Queue TTL có thể làm queue tự xóa sau thời gian không được sử dụng theo điều kiện của broker.

Không đặt TTL ngắn hơn thời gian gián đoạn downstream có thể chịu được nếu event cần được giao sau khi dịch vụ phục hồi. TTL là chính sách vòng đời, không phải cơ chế retry.

### Maximum length

Queue có thể giới hạn số lượng message hoặc tổng dung lượng message. Khi vượt giới hạn, hành vi phụ thuộc overflow policy:

- Loại message cũ nhất (drop-head) để giữ message mới.
- Từ chối publish mới (reject-publish), có thể khiến publisher nhận kết quả không thành công tùy cơ chế xác nhận.

Với event nghiệp vụ cần bảo toàn, cần đánh giá kỹ chính sách overflow. Không dùng drop-head mà không chấp nhận rõ việc mất message cũ. Reject-publish cần được publisher phát hiện và xử lý bằng retry hoặc lưu bền vững khác.

### Quản lý bằng policy

Các thuộc tính như TTL, dead-letter và max length thường có thể được quản lý bằng RabbitMQ policies. Policy cho phép điều chỉnh một số hành vi vận hành mà không phải sửa và redeploy ứng dụng. Các thuộc tính bất biến hoặc loại queue vẫn cần được khai báo đúng khi tạo queue.

## 11. Dead-letter queue và retry

Dead-letter exchange (DLX) nhận message bị dead-letter, ví dụ khi consumer reject/nack không requeue, message hết TTL hoặc queue vượt giới hạn theo cấu hình phù hợp.

Dead-letter queue (DLQ) giúp cách ly message không thể xử lý để điều tra. Nó không tự giải quyết lỗi và không nên trở thành nơi chứa message vô thời hạn mà không có người theo dõi.

Một topology thường có:

- Queue chính nhận message bình thường.
- Dead-letter exchange nhận message bị dead-letter.
- Dead-letter queue lưu message cần điều tra hoặc phát lại.
- Retry queue có TTL nếu cần trì hoãn trước lần thử tiếp theo.

Không nên requeue message lỗi ngay lập tức trong vòng lặp. Điều đó có thể tạo hot loop, tăng CPU và log, đồng thời làm queue không tiến triển. Dùng retry có backoff, giới hạn số lần thử và dead-letter sau khi vượt ngưỡng. Khi phát lại, cần giữ event ID và đảm bảo consumer idempotent.

## 12. Ví dụ khai báo topology với Spring AMQP

Ví dụ sau khai báo direct exchange, quorum queue chính, dead-letter exchange, dead-letter queue và binding. Tên và cấu hình là minh họa, cần điều chỉnh theo topology của môi trường.

~~~java
@Configuration
class OrdersRabbitConfiguration {

    @Bean
    Declarables ordersTopology() {
        DirectExchange eventsExchange =
            new DirectExchange("orders.events");

        DirectExchange deadLetterExchange =
            new DirectExchange("orders.dlx");

        Queue ordersQueue = QueueBuilder
            .durable("orders.confirmed.q")
            .quorum()
            .deadLetterExchange("orders.dlx")
            .deadLetterRoutingKey("orders.confirmed.failed")
            .build();

        Queue deadLetterQueue = QueueBuilder
            .durable("orders.confirmed.dlq")
            .build();

        Binding ordersBinding = BindingBuilder
            .bind(ordersQueue)
            .to(eventsExchange)
            .with("orders.confirmed");

        Binding deadLetterBinding = BindingBuilder
            .bind(deadLetterQueue)
            .to(deadLetterExchange)
            .with("orders.confirmed.failed");

        return new Declarables(
            eventsExchange,
            deadLetterExchange,
            ordersQueue,
            deadLetterQueue,
            ordersBinding,
            deadLetterBinding
        );
    }
}
~~~

Ví dụ cần các import Spring AMQP tương ứng như org.springframework.amqp.core.* và org.springframework.context.annotation.*. Việc khai báo queue chính tham chiếu DLX không thay thế việc khai báo exchange và queue đích; ví dụ đã khai báo cả hai exchange và binding cần thiết.

Khai báo topology qua bean chỉ có tác dụng nếu ứng dụng có quyền tạo topology và RabbitAdmin được cấu hình để khai báo. Nếu topology do nền tảng quản lý, hãy dùng đúng tên và thuộc tính đã được provision thay vì để nhiều ứng dụng cạnh tranh quản lý cùng tài nguyên.

## 13. Consumer với Spring AMQP

Một listener có thể đăng ký trực tiếp với queue bằng **@RabbitListener**:

~~~java
@Component
class OrderConfirmedConsumer {

    private final OrderFulfillmentService fulfillment;

    OrderConfirmedConsumer(OrderFulfillmentService fulfillment) {
        this.fulfillment = fulfillment;
    }

    @RabbitListener(queues = "orders.confirmed.q")
    public void handle(OrderConfirmed event) {
        fulfillment.start(event.orderId());
    }
}
~~~

Container listener của Spring AMQP quản lý việc nhận message và acknowledgement theo cấu hình acknowledgement mode. Với chế độ AUTO phổ biến, container xác nhận khi listener hoàn tất thành công và xử lý exception theo cấu hình requeue/retry. Cần cấu hình retry, recoverer và dead-letter rõ ràng; không nên dựa vào một hành vi mặc định chưa được kiểm chứng ở phiên bản đang chạy.

Nếu dùng manual acknowledgement, listener hoặc adapter phải ack/nack đúng thời điểm. Không ack trước khi công việc nghiệp vụ được bảo vệ hoàn tất. Cũng không giữ message unacked quá lâu mà không giới hạn concurrency hoặc prefetch, vì điều đó có thể làm giảm khả năng phân phối và tăng áp lực bộ nhớ.

## 14. Idempotency và thứ tự xử lý

RabbitMQ có thể giao lại message khi consumer mất kết nối trước acknowledgement. Vì vậy, consumer cần giả định một message có thể được nhận nhiều lần.

Một cách phổ biến là ghi event ID vào bảng processed_events với unique constraint trong cùng transaction với thay đổi nghiệp vụ. Nếu event ID đã tồn tại, consumer biết event đã được xử lý và có thể ack mà không lặp tác dụng phụ. Với API bên ngoài, sử dụng idempotency key nếu API hỗ trợ.

Thứ tự xử lý cần được đánh giá riêng:

- Một queue FIFO cơ bản giữ thứ tự enqueue ở mức queue, nhưng nhiều consumer xử lý đồng thời có thể hoàn tất theo thứ tự khác nhau.
- Redelivery có thể khiến message cũ xuất hiện lại sau message mới.
- Retry queue và DLQ có thể làm thay đổi thứ tự xử lý.
- Nếu cần thứ tự theo aggregate, dùng một routing/partition strategy phù hợp và tuần tự hóa xử lý trong phạm vi aggregate đó.
- Không mặc định có thứ tự toàn cục giữa nhiều queue hoặc nhiều consumer.

Nếu event OrderConfirmed phải được xử lý trước OrderShipped, consumer cần có version hoặc sequence theo order ID để phát hiện message đến sai thứ tự và quyết định chờ, retry hoặc cách ly.

## 15. Queue, Spring Modulith và externalization

Spring Modulith quản lý application event và publication registry trong ranh giới ứng dụng. RabbitMQ là transport bên ngoài dùng để chuyển message giữa các tiến trình hoặc hệ thống. Queue RabbitMQ không thay thế publication registry của Spring Modulith.

Một luồng có thể được chia thành:

1. Module nghiệp vụ phát application event trong transaction.
2. Publication registry ghi nhận publication theo transaction boundary đã cấu hình.
3. Adapter externalization gửi message đến RabbitMQ.
4. Exchange định tuyến message đến queue.
5. Consumer độc lập nhận và xử lý.
6. Consumer ack sau khi hoàn tất theo chính sách.

Cần phân biệt trạng thái publication trong ứng dụng với trạng thái message ở broker. Publication được đánh dấu hoàn tất khi adapter hoàn thành chặng giao nhận theo semantics tích hợp; điều đó không có nghĩa consumer đã hoàn tất nghiệp vụ. Consumer cần acknowledgement và cơ chế idempotency riêng.

Nếu yêu cầu là chuyển message ra broker đáng tin cậy, cần cấu hình publisher confirms, xử lý message unroutable, persistent delivery, durable/replicated queue và consumer acknowledgement phù hợp. Đừng suy ra rằng chỉ cần khai báo một queue là toàn bộ luồng đã có bảo đảm end-to-end.

## 16. Quan sát queue và xử lý sự cố

Theo dõi các chỉ số sau cho mỗi queue:

| Metric | Ý nghĩa |
|---|---|
| Ready messages | Số message đang chờ consumer nhận |
| Unacknowledged messages | Số message đã giao nhưng chưa ack |
| Publish rate | Tốc độ message được publish |
| Deliver/ack rate | Tốc độ broker giao và consumer xác nhận |
| Consumer count | Số consumer đang đăng ký |
| Oldest message age | Tuổi của message cũ nhất |
| Redelivery rate | Tỷ lệ message được giao lại |
| Dead-letter rate | Số message bị chuyển sang DLQ |
| Queue memory/disk | Mức sử dụng tài nguyên lưu trữ |
| Connection/channel errors | Lỗi kết nối hoặc channel |

Một queue có ready message tăng liên tục thường cho thấy consumer không theo kịp. Unacked tăng có thể cho thấy consumer đang xử lý chậm, prefetch quá cao hoặc listener bị treo. Queue không có consumer cần được cảnh báo nếu nó được kỳ vọng phải có consumer hoạt động.

Khi backlog tăng:

1. Kiểm tra publish rate và ack rate.
2. Xem số consumer, unacked, redelivery và oldest message age.
3. Kiểm tra log consumer, thời gian gọi downstream và connection pool.
4. Xác định có hot key, message quá lớn hoặc poison message hay không.
5. Điều chỉnh prefetch/concurrency khi downstream còn năng lực.
6. Dùng retry có backoff và DLQ để cách ly lỗi vĩnh viễn.
7. Chỉ tăng consumer khi database và dịch vụ phía sau chịu được tải tăng thêm.

Không xóa queue hoặc purge message để làm giảm backlog nếu chưa xác định tác động nghiệp vụ và có phương án phục hồi.

## 17. Bảo mật và quyền truy cập

RabbitMQ phân quyền theo virtual host, configure, write và read permission. Producer thường cần quyền write vào exchange; consumer cần quyền read queue; thành phần khai báo topology cần quyền configure phù hợp.

Các nguyên tắc:

- Tách virtual host hoặc namespace theo môi trường và ranh giới tin cậy khi cần.
- Cấp quyền tối thiểu cho từng producer và consumer.
- Dùng TLS cho kết nối qua mạng không tin cậy.
- Quản lý credential qua secret store, không hardcode trong source.
- Giới hạn ai có thể khai báo hoặc xóa exchange, queue và binding.
- Không đưa dữ liệu nhạy cảm vào routing key, queue name hoặc log.
- Đặt retention, backup và quyền truy cập DLQ phù hợp vì message lỗi có thể chứa payload nhạy cảm.

## 18. Checklist thiết kế queue

- [ ] Đã xác định consumer sở hữu queue và loại message được nhận.
- [ ] Exchange, routing key và binding đã được mô tả rõ.
- [ ] Tên queue phản ánh domain hoặc trách nhiệm consumer.
- [ ] Đã chọn classic hay quorum theo yêu cầu độ bền và tải.
- [ ] Đã phân biệt durable queue với persistent message.
- [ ] Publisher confirms và xử lý unroutable message được cấu hình khi cần.
- [ ] Consumer acknowledgement phù hợp với thời điểm hoàn tất nghiệp vụ.
- [ ] Prefetch và concurrency phù hợp với năng lực consumer.
- [ ] TTL, max length và overflow policy có quyết định rõ.
- [ ] DLX, DLQ và retry có backoff được cấu hình nếu cần.
- [ ] Consumer idempotent và có chiến lược xử lý thứ tự.
- [ ] Topology được quản lý bởi một nguồn sở hữu rõ ràng.
- [ ] Có metric backlog, unacked, redelivery và oldest message age.
- [ ] Quyền truy cập, TLS và secret được quản lý an toàn.
- [ ] Đã kiểm thử restart broker, consumer crash, redelivery và backlog recovery.

## 19. Nguyên tắc sử dụng queue

Queue là ranh giới lưu trữ và phân phối công việc giữa broker với consumer. Hãy thiết kế queue theo trách nhiệm consumer, chọn queue type theo yêu cầu durability và replication, cấu hình acknowledgement cùng prefetch phù hợp và đặt giới hạn TTL/dung lượng có chủ đích.

Với Spring Modulith, publication registry bảo vệ việc theo dõi giao application event trong ứng dụng; RabbitMQ exchange và queue đảm nhiệm định tuyến, lưu trữ và phân phối message bên ngoài. Khi hai lớp được cấu hình đúng, kết hợp publisher confirms, consumer acknowledgement, idempotency, DLQ và quan sát backlog, hệ thống có thể giao sự kiện đáng tin cậy qua ranh giới module và tiến trình.

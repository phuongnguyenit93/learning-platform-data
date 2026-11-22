# SourcePollingChannelAdapter và nguồn tạo message

Trong Spring Integration, nhiều nguồn dữ liệu không chủ động đẩy sự kiện vào ứng dụng. Ứng dụng phải định kỳ hỏi nguồn xem đã có dữ liệu mới hay chưa. Cơ chế này được triển khai bằng **SourcePollingChannelAdapter** kết hợp với một **MessageSource**.

MessageSource chịu trách nhiệm lấy một message từ nguồn. SourcePollingChannelAdapter chịu trách nhiệm gọi nguồn theo lịch, nhận message, rồi gửi message đó vào channel của flow. Poller quyết định nhịp lấy dữ liệu và số message tối đa được lấy trong một chu kỳ.

Đây là mô hình pull: ứng dụng chủ động lấy dữ liệu. Nó phù hợp với bảng dữ liệu cần quét định kỳ, thư mục file, hàng đợi có API nhận, nguồn trạng thái hoặc hệ thống không hỗ trợ push. Hiểu đúng adapter và nguồn giúp kiểm soát độ trễ, tải hệ thống, transaction, retry và việc dừng ứng dụng an toàn.

## 1. Kiến trúc nguồn polling

Một source polling flow thường có các thành phần:

- **Nguồn dữ liệu**: database, file system, API, queue hoặc một nguồn tùy chỉnh.
- **MessageSource<T>**: abstraction lấy dữ liệu và trả về Message<T> hoặc null khi chưa có dữ liệu.
- **SourcePollingChannelAdapter**: endpoint thực hiện việc polling MessageSource và gửi message vào output channel.
- **Poller**: mô tả trigger, giới hạn số message trong mỗi lần poll và các advice liên quan.
- **TaskScheduler**: lập lịch lần thực thi polling tiếp theo.
- **Channel và các endpoint phía sau**: tiếp nhận và xử lý message như các flow Spring Integration khác.

~~~mermaid
flowchart LR
    A["Database / File / API / Queue"] --> B["MessageSource"]
    B --> C["SourcePollingChannelAdapter"]
    T["Poller + Trigger"] --> C
    S["TaskScheduler"] --> T
    C --> D["Output MessageChannel"]
    D --> E["Handler / Service Activator"]
    E --> F["Flow tiếp theo"]
    C -. "exception" .-> X["Error handling"]
~~~

MessageSource không tự lên lịch. Nó chỉ định nghĩa cách lấy một message. Adapter mới là thành phần gắn source với lịch polling và channel đầu ra.

Phân biệt adapter này với một inbound adapter event-driven. Với listener của broker hoặc callback của hệ thống ngoài, nguồn chủ động gọi ứng dụng khi có sự kiện. Với SourcePollingChannelAdapter, ứng dụng chủ động gọi receive() theo lịch. Hai kiểu inbound này có cách điều khiển tải, độ trễ và lifecycle khác nhau.

## 2. Hợp đồng của MessageSource

MessageSource<T> là abstraction cốt lõi của nguồn polling. Hợp đồng chính là:

~~~java
public interface MessageSource<T> {
    Message<T> receive();
}
~~~

Khi được gọi:

- Nếu có dữ liệu, source trả về một Message<T>.
- Nếu hiện chưa có dữ liệu, source trả về null.
- Nếu không thể lấy dữ liệu do lỗi, source có thể ném exception.

null có ý nghĩa bình thường: lần poll này không có message để gửi. Nó không phải một message rỗng và cũng không nhất thiết là lỗi. Polling adapter dùng kết quả này để biết không còn message trong lượt lấy dữ liệu hiện tại.

Message trả về có thể được tạo ngay trong source bằng MessageBuilder, hoặc được tạo bởi một adapter bọc quanh API trả về payload. Khi source trả về message, nó có thể đặt header cần thiết như source identifier, partition, tenant, timestamp nghiệp vụ hoặc metadata để downstream xử lý.

Ví dụ một source đơn giản:

~~~java
@Component
class PendingOrderSource implements MessageSource<Order> {

    private final OrderRepository repository;

    PendingOrderSource(OrderRepository repository) {
        this.repository = repository;
    }

    @Override
    public Message<Order> receive() {
        Order order = repository.claimNextPendingOrder();

        if (order == null) {
            return null;
        }

        return MessageBuilder.withPayload(order)
                .setHeader("app.orderId", order.id())
                .setHeader("app.source", "pending-orders")
                .build();
    }
}
~~~

Ví dụ giả định repository có thao tác claimNextPendingOrder() phù hợp để nhận quyền xử lý một bản ghi. Với nhiều instance ứng dụng, việc chọn và claim bản ghi phải được thiết kế nguyên tử ở database hoặc thông qua cơ chế khóa/lease. Chỉ chạy SELECT rồi cập nhật trạng thái ở hai thao tác tách rời có thể khiến hai instance lấy cùng một đơn hàng.

Một MessageSource nên có các đặc tính:

- Mỗi lần receive() có chi phí và thời gian chờ dự đoán được.
- Chỉ trả null khi nguồn hiện không có message.
- Không âm thầm nuốt lỗi kết nối hoặc lỗi dữ liệu.
- Có quy tắc rõ ràng về việc bản ghi đã được claim, acknowledge, commit hay sẽ được đọc lại.
- Trả metadata đủ để theo dõi nguồn, correlation và trạng thái xử lý.

## 3. SourcePollingChannelAdapter làm gì trong một chu kỳ?

Ở mức khái niệm, một chu kỳ polling diễn ra như sau:

1. Scheduler kích hoạt polling task theo trigger.
2. Adapter gọi MessageSource.receive().
3. Nếu source trả null, adapter kết thúc lượt lấy message.
4. Nếu source trả message, adapter gửi message đến output channel.
5. Poller có thể tiếp tục gọi source trong cùng chu kỳ cho đến khi đạt maxMessagesPerPoll hoặc source không còn message.
6. Khi chu kỳ kết thúc, scheduler chờ lần kích hoạt tiếp theo.

~~~mermaid
flowchart TD
    A["Đến thời điểm poll"] --> B["Gọi MessageSource.receive()"]
    B --> C{"Có Message?"}
    C -- "Không: null" --> G["Kết thúc chu kỳ"]
    C -- "Có" --> D["Gửi vào output channel"]
    D --> E{"Đạt maxMessagesPerPoll?"}
    E -- "Chưa" --> B
    E -- "Rồi" --> G
    G --> H["Chờ trigger tiếp theo"]
    H --> A
~~~

Lưu ý rằng SourcePollingChannelAdapter không nhất thiết chỉ gọi source một lần trong một lần kích hoạt scheduler. Số lần gọi phụ thuộc vào maxMessagesPerPoll và việc source còn trả message hay không.

Nếu maxMessagesPerPoll là số dương, nó giới hạn số message tối đa được lấy trong một chu kỳ. Giá trị -1 được dùng để tiếp tục nhận cho đến khi source trả null. Batch lớn có thể tăng throughput nhưng cũng làm một lần poll kéo dài, chiếm scheduler thread lâu hơn và làm tăng độ trễ của các tác vụ khác nếu scheduler dùng chung.

## 4. Cấu hình poller trong Java DSL

Java DSL cho phép tạo flow trực tiếp từ một MessageSource và cấu hình poller cho endpoint nguồn.

~~~java
@Bean
IntegrationFlow pendingOrders(
        PendingOrderSource source,
        OrderService orderService) {

    return IntegrationFlow.from(source,
                    endpoint -> endpoint.poller(
                            Pollers.fixedDelay(Duration.ofSeconds(1))
                                    .maxMessagesPerPoll(20)))
            .handle(orderService, "process")
            .get();
}
~~~

Trong ví dụ:

- source là MessageSource<Order>.
- fixedDelay(Duration.ofSeconds(1)) đặt khoảng delay giữa các lần thực thi polling theo cấu hình.
- maxMessagesPerPoll(20) giới hạn tối đa 20 message trong một chu kỳ.
- handle(...) là bước xử lý tiếp theo của flow.

Nếu source chỉ có 3 message, chu kỳ kết thúc khi source trả null; adapter không chờ để lấy đủ 20 message. Nếu nguồn liên tục có dữ liệu, một chu kỳ có thể lấy đủ 20 message rồi mới nhường cho lịch tiếp theo.

### Dùng MessageSource dạng bean

Có thể khai báo source riêng như một bean để tách logic lấy dữ liệu khỏi định nghĩa flow:

~~~java
@Bean
MessageSource<Order> orderSource(OrderRepository repository) {
    return () -> {
        Order order = repository.claimNextPendingOrder();
        return order == null
                ? null
                : MessageBuilder.withPayload(order).build();
    };
}

@Bean
IntegrationFlow orderPollingFlow(MessageSource<Order> orderSource,
                                 OrderService orderService) {
    return IntegrationFlow.from(orderSource,
                    endpoint -> endpoint.poller(
                            Pollers.fixedDelay(500)
                                    .maxMessagesPerPoll(10)))
            .handle(orderService, "process")
            .get();
}
~~~

Cách này thuận tiện khi muốn unit test source độc lập, tái sử dụng source hoặc thay implementation mà không phải thay đổi flow.

## 5. Dùng @InboundChannelAdapter

Ngoài Java DSL, có thể dùng annotation @InboundChannelAdapter để đăng ký một method hoặc bean làm nguồn inbound polling.

~~~java
@Bean
@InboundChannelAdapter(
        channel = "orders.in",
        poller = @Poller(
                fixedDelay = "1000",
                maxMessagesPerPoll = "10"))
public MessageSource<Order> ordersSource(OrderRepository repository) {
    return () -> {
        Order order = repository.claimNextPendingOrder();
        return order == null
                ? null
                : MessageBuilder.withPayload(order).build();
    };
}

@Bean
IntegrationFlow processOrders(OrderService orderService) {
    return IntegrationFlow.from("orders.in")
            .handle(orderService, "process")
            .get();
}
~~~

Annotation tạo hạ tầng inbound adapter từ cấu hình method. Kênh orders.in là nơi adapter gửi message vào flow.

Có thể dùng method trả payload hoặc trả Message tùy cách khai báo và API cụ thể. Khi cần header tùy chỉnh, trả về Message giúp thể hiện rõ payload và metadata. Cần tránh tạo thêm một poller cho cùng một nguồn chỉ vì flow downstream cũng có cấu hình polling: @InboundChannelAdapter đã là nguồn polling; các endpoint event-driven sau đó nhận message qua channel.

## 6. Chọn trigger: fixed delay, fixed rate và cron

Poller cần trigger để scheduler biết khi nào thực hiện lần polling tiếp theo.

| Trigger | Ý nghĩa | Khi phù hợp |
|---|---|---|
| Fixed delay | Đợi một khoảng thời gian sau khi lần thực thi trước hoàn tất rồi mới chạy tiếp | Source có thời gian xử lý thay đổi hoặc cần tránh dồn tải |
| Fixed rate | Lập lịch theo nhịp thời gian cố định | Cần nhịp poll tương đối đều và tác vụ có thời gian chạy ổn định |
| Cron | Chạy theo biểu thức lịch | Đồng bộ theo giờ làm việc, đầu/cuối ngày hoặc lịch nghiệp vụ |

Ví dụ fixed delay:

~~~java
Pollers.fixedDelay(Duration.ofSeconds(2))
~~~

Ví dụ fixed rate:

~~~java
Pollers.fixedRate(Duration.ofSeconds(5))
~~~

Ví dụ cron:

~~~java
Pollers.cron("0 */5 * * * *")
~~~

Cú pháp cron của Spring thường có sáu trường, bao gồm giây. Cần kiểm tra timezone và quy tắc DST khi lịch phụ thuộc giờ địa phương.

Fixed delay thường dễ kiểm soát khi mỗi lượt poll có thời gian xử lý không ổn định. Fixed rate phù hợp với nhịp đều, nhưng nếu tác vụ mất nhiều thời gian hơn khoảng kỳ vọng, lịch thực tế có thể bị trễ tùy scheduler và cấu hình thực thi. Cron phù hợp với lịch nghiệp vụ nhưng không tự giải quyết việc một lượt chạy trước vẫn còn đang xử lý.

Không nên chọn chu kỳ polling quá ngắn chỉ để giảm latency. Polling mỗi vài millisecond có thể tạo nhiều lần gọi rỗng, tăng tải database hoặc API và chiếm scheduler. Hãy cân bằng độ trễ chấp nhận được với chi phí mỗi lần kiểm tra nguồn.

## 7. maxMessagesPerPoll và kích thước batch

maxMessagesPerPoll là giới hạn số message mà adapter lấy từ source trong một lần kích hoạt poller.

| Giá trị | Hành vi |
|---|---|
| Số dương, ví dụ 10 | Lấy tối đa 10 message trong một chu kỳ |
| -1 | Tiếp tục lấy đến khi source trả null |
| Giá trị mặc định | Phụ thuộc cấu hình poller/phiên bản và cách endpoint được tạo; nên cấu hình rõ khi batch có ý nghĩa vận hành |

Giá trị lớn có thể tăng throughput vì giảm overhead lập lịch trên mỗi message. Tuy nhiên, batch quá lớn có thể:

- Làm một lần poll chiếm scheduler thread lâu.
- Tạo burst message đến downstream.
- Làm transaction của một lượt polling kéo dài.
- Tăng số message đang nằm trong bộ nhớ hoặc queue.
- Làm các nguồn khác dùng chung scheduler bị trễ.

Giá trị nhỏ làm các chu kỳ nhường tài nguyên thường xuyên hơn nhưng có thể tăng overhead và giảm throughput. Hãy chọn batch dựa trên tốc độ nguồn, thời gian xử lý trung bình, giới hạn downstream và SLA latency.

maxMessagesPerPoll không phải số thread xử lý song song. Đặt giá trị 20 không có nghĩa 20 message chạy đồng thời. Với flow đồng bộ, các message có thể được xử lý nối tiếp trong cùng polling task. Muốn tăng concurrency phải thiết kế execution model riêng.

Không nên nhầm receiveTimeout của poller dùng với PollableChannel với timeout của MessageSource. Hợp đồng MessageSource.receive() không nhận tham số timeout; nếu thao tác đọc nguồn có thể chờ, implementation phải tự cấu hình timeout cho database, socket hoặc API client. Nếu receive() block quá lâu, polling task và scheduler thread có thể bị giữ lại.

## 8. Scheduler và executor: ai làm việc gì?

Trong mô hình polling, các vai trò cần phân biệt:

- **TaskScheduler** lên lịch thời điểm thực hiện polling task.
- **Poller** chứa trigger và các chính sách của chu kỳ polling.
- **MessageSource** lấy message từ nguồn.
- **TaskExecutor** có thể được dùng ở các ranh giới thực thi bất đồng bộ hoặc theo cấu hình executor của endpoint.
- **Channel** quyết định message được dispatch đồng bộ, broadcast, buffer hay chuyển sang executor.

Không nên đồng nhất scheduler với executor. Scheduler quyết định thời điểm chạy; executor điều phối việc thực thi task trên thread pool. Trong cấu hình thực tế, một scheduler có thể dùng cho nhiều endpoint. Nếu một source bị chặn lâu, nó có thể làm giảm khả năng đáp ứng của các poller khác nếu cùng chia sẻ scheduler với số thread hạn chế.

Có thể cấu hình scheduler riêng cho ứng dụng hoặc hạ tầng Integration khi cần tách các nhóm poller có đặc tính tải khác nhau. Khi thay đổi thread pool, cần đo số lần poll, thời gian poll, độ trễ và tình trạng queue của executor.

Nếu cần xử lý message song song, có thể đưa message qua ExecutorChannel hoặc một endpoint bất đồng bộ được cấu hình executor. Nhưng khi thêm ranh giới này, cần đánh giá lại thứ tự message, transaction, error handling và cách shutdown.

## 9. Nguồn tạo message thường gặp

Spring Integration có nhiều implementation MessageSource hoặc adapter dựa trên polling.

| Loại nguồn | Ví dụ | Đặc điểm |
|---|---|---|
| Database | JdbcPollingChannelAdapter | Chạy query định kỳ để lấy bản ghi; cần chiến lược claim/mark processed |
| File system | FileReadingMessageSource | Quét thư mục và phát file; cần quản lý filter, locking và archive |
| Method ứng dụng | @InboundChannelAdapter | Gọi method theo lịch và bọc kết quả thành message |
| Queue hoặc store | Source đọc từ hàng đợi có API pull | Cần xác định ack/delete và redelivery |
| Nguồn tùy chỉnh | MessageSource<T> do ứng dụng viết | Toàn quyền định nghĩa lấy dữ liệu và metadata |

### Database source

Database polling thường truy vấn các bản ghi đang chờ. Sau khi lấy được bản ghi, hệ thống phải quyết định khi nào đánh dấu đã nhận hoặc đã xử lý.

Một thiết kế thường dùng trạng thái như PENDING, PROCESSING, DONE, FAILED cùng thời điểm claim và lease. Nhiều instance có thể cùng chạy poller nên câu query và thao tác claim phải tránh chọn trùng bản ghi. Một transaction có thể bao việc claim và xử lý nếu toàn bộ thao tác cùng transaction manager và cùng execution thread; nếu flow chuyển bất đồng bộ, cần transaction boundary mới ở consumer.

### File source

File source thường quét thư mục, áp dụng filter để tránh đọc file chưa hoàn tất hoặc đã xử lý. Sau khi phát file, ứng dụng có thể chuyển file sang thư mục archive, rename hoặc ghi nhận trạng thái xử lý. Việc file đã được source phát ra không tự động có nghĩa nghiệp vụ xử lý thành công; cần quy tắc hoàn tất và phục hồi nếu downstream lỗi.

### Source tùy chỉnh

Khi viết MessageSource riêng, hãy giữ phần receive() tập trung vào việc lấy/claim một message và tạo metadata. Tránh nhúng cả quy trình nghiệp vụ dài vào source. Tách source khỏi handler giúp kiểm thử, retry và transaction boundary rõ ràng hơn.

## 10. Transaction và tính nhất quán khi polling

Poller có thể gắn transaction advice qua adviceChain. Điều này cho phép transaction bao quanh một lần polling hoặc một phần công việc được cấu hình cho poller.

Ví dụ Java DSL:

~~~java
@Bean
IntegrationFlow transactionalPolling(
        MessageSource<Order> source,
        OrderService orderService,
        PlatformTransactionManager transactionManager) {

    return IntegrationFlow.from(source,
                    e -> e.poller(Pollers.fixedDelay(Duration.ofSeconds(1))
                            .maxMessagesPerPoll(10)
                            .transactional(transactionManager)))
            .handle(orderService, "process")
            .get();
}
~~~

Tên method và overload cụ thể có thể khác theo phiên bản Spring Integration; khi dùng DSL của dự án, hãy kiểm tra API tương ứng. Về mặt thiết kế, điều quan trọng là transaction được gắn vào poller và bao đúng các thao tác cần nguyên tử.

Transaction có ích khi source đọc từ tài nguyên hỗ trợ transaction, chẳng hạn database. Nếu claim bản ghi và cập nhật trạng thái xử lý nằm trong cùng transaction, rollback có thể khôi phục trạng thái khi xử lý thất bại.

Tuy nhiên, không phải mọi nguồn đều có thể rollback:

- Đọc file từ filesystem không tự động tham gia transaction database.
- Gọi API bên ngoài có thể đã tạo side effect dù transaction database rollback.
- Message đã được gửi sang broker ngoài transaction có thể không bị thu hồi khi database rollback.
- Nếu flow đi qua ExecutorChannel hoặc queue bất đồng bộ, transaction thread ban đầu không tự truyền sang consumer.

Với các hệ thống nhiều tài nguyên, hãy cân nhắc idempotency, outbox/inbox, ack sau xử lý và cơ chế bù trừ. Đừng giả định transaction của poller tạo ra exactly-once cho toàn bộ chuỗi tích hợp.

## 11. Lỗi khi source hoặc downstream thất bại

Có thể phát sinh lỗi ở nhiều vị trí:

- MessageSource.receive() không kết nối được nguồn hoặc query lỗi.
- Source tạo message nhưng dữ liệu không hợp lệ.
- Output channel từ chối message hoặc hết capacity.
- Handler downstream ném exception.
- Transaction commit thất bại sau khi handler đã chạy.

Cách xử lý phụ thuộc vào lỗi xảy ra trong source, lúc gửi message hay ở endpoint phía sau, và flow đồng bộ hay bất đồng bộ.

Với flow đồng bộ qua DirectChannel, lỗi downstream có thể truyền ngược về polling task. Với ranh giới bất đồng bộ như executor hoặc queue, lỗi có thể xuất hiện ở thread hoặc endpoint consumer khác; cần theo dõi error channel và error handler của consumer tương ứng.

Có thể dùng poller advice để gắn retry, transaction hoặc logging advice. Retry nên áp dụng cho lỗi tạm thời, có giới hạn số lần và backoff. Không retry vô hạn lỗi dữ liệu vĩnh viễn hoặc lỗi cấu hình vì sẽ làm poller liên tục thất bại.

Nếu source đã đánh dấu bản ghi là đã lấy trước khi gửi vào channel, nhưng downstream gửi thất bại, bản ghi có thể bị mất khỏi luồng nếu không có cơ chế phục hồi. Nếu source chỉ đọc mà chưa claim, cùng bản ghi có thể được phát lặp ở lần poll sau. Vì vậy cần quy định rõ trạng thái source và cách acknowledge.

## 12. Acknowledgement, redelivery và idempotency

MessageSource không áp đặt một chiến lược acknowledgement chung cho mọi nguồn. Ý nghĩa của receive() phụ thuộc implementation:

- Có source chỉ đọc bản ghi và không thay đổi trạng thái nguồn.
- Có source claim hoặc xóa message ngay khi nhận.
- Có source chỉ đánh dấu hoàn tất sau một thao tác riêng.
- Có adapter dùng transaction để thao tác nhận và commit/rollback theo tài nguyên.

Cần trả lời ba câu hỏi:

1. Khi nào nguồn xem message đã được giao cho ứng dụng?
2. Khi nào nguồn xem message đã xử lý thành công?
3. Nếu ứng dụng dừng giữa hai thời điểm đó, message được phát lại, giữ ở trạng thái processing hay bị mất?

Nếu nguồn acknowledge trước khi nghiệp vụ hoàn tất, cần cơ chế lưu trạng thái và khôi phục. Nếu nguồn redeliver khi không nhận được ack, handler cần idempotent để tránh tạo side effect trùng.

Một cách thiết kế phổ biến là sử dụng khóa nghiệp vụ ổn định như orderId hoặc eventId, lưu kết quả đã xử lý và từ chối thực hiện side effect lần thứ hai. Không nên dùng MessageHeaders.id làm khóa idempotency xuyên lần phát lại vì message mới có thể nhận ID mới.

## 13. Lifecycle của SourcePollingChannelAdapter

SourcePollingChannelAdapter là một endpoint do Spring quản lý lifecycle. Trong cấu hình thông thường, nó được khởi tạo cùng application context, đăng ký poller, và bắt đầu lịch polling khi endpoint được start.

Các khái niệm lifecycle cần biết:

- **autoStartup**: endpoint có tự động start khi lifecycle processor của Spring khởi động hay không.
- **phase**: thứ tự tương đối giữa các thành phần SmartLifecycle khi start và stop.
- **start()**: bắt đầu hoạt động endpoint.
- **stop()**: ngừng hoạt động endpoint và hủy lịch polling đang được đăng ký.
- **isRunning()**: cho biết endpoint đang ở trạng thái chạy hay không.

Có thể điều khiển endpoint bằng bean name hoặc thông qua các cơ chế quản lý Integration endpoint. Với flow động, IntegrationFlowContext cho phép đăng ký và hủy flow cùng endpoint liên quan trong runtime.

### autoStartup

Nếu autoStartup bật, endpoint được lifecycle processor khởi động cùng context. Nếu tắt, ứng dụng có thể kiểm soát thời điểm start thủ công sau khi đã sẵn sàng kết nối nguồn hoặc sau khi hoàn thành bước khởi tạo nghiệp vụ.

Điều này hữu ích khi nguồn chỉ được phép polling sau khi cấu hình tenant, credential hoặc schema đã sẵn sàng.

### phase

phase xác định thứ tự start/stop giữa các bean SmartLifecycle. Khi nhiều endpoint phụ thuộc nhau, có thể đặt phase để nguồn vào chỉ bắt đầu sau khi thành phần downstream đã sẵn sàng. Khi dừng, lifecycle processor thực hiện theo thứ tự ngược để hạn chế message được gửi đến endpoint đã dừng.

Không nên đặt phase tùy tiện cho từng bean. Hãy mô hình hóa dependency thực tế: channel và consumer phải sẵn sàng trước khi source phát message; khi shutdown, source nên dừng nhận thêm dữ liệu trước khi downstream bị đóng.

## 14. Dừng polling an toàn

Dừng một polling adapter không đồng nghĩa mọi message đang xử lý đều tự động rollback hoặc hoàn tất. Cần phân biệt:

- Lịch polling tiếp theo được hủy.
- Một lần receive() đang chạy có thể đã vào source.
- Message đang được xử lý đồng bộ có thể cần thời gian để hoàn tất.
- Message đã được gửi sang queue/executor có thể vẫn đang chờ consumer.
- Transaction có thể đang ở giữa commit hoặc rollback.

Một quy trình shutdown an toàn thường là:

1. Ngừng nhận công việc mới bằng cách stop source adapter hoặc cơ chế quiesce tương đương.
2. Chờ các lượt xử lý đang chạy hoàn tất trong giới hạn shutdown timeout.
3. Cho consumer downstream hoàn tất hoặc drain queue theo chính sách của ứng dụng.
4. Đóng source, connection và tài nguyên phụ thuộc sau khi endpoint đã ngừng.
5. Ghi nhận các message chưa hoàn tất để có thể retry hoặc phục hồi sau restart.

Với source tùy chỉnh có thao tác blocking, cần đặt timeout cho I/O và đảm bảo stop không bị treo vô hạn. Không nên dựa vào việc interrupt thread nếu implementation của source không hỗ trợ interruption an toàn.

## 15. Throughput, latency và backpressure

Polling là một điểm điều tiết intake. Ba yếu tố chính ảnh hưởng đến thông lượng:

- **Tần suất poll**: poll càng thường xuyên thì độ trễ phát hiện dữ liệu mới có thể giảm, nhưng chi phí kiểm tra nguồn tăng.
- **Batch size**: maxMessagesPerPoll càng lớn thì overhead trên mỗi message có thể giảm, nhưng mỗi chu kỳ có thể kéo dài và tạo burst.
- **Tốc độ downstream**: nếu handler chậm hơn tốc độ lấy dữ liệu, queue hoặc executor phía sau có thể tích tụ message.

SourcePollingChannelAdapter không tự tạo backpressure end-to-end theo kiểu Reactive Streams. Polling có thể giới hạn intake theo trigger và batch, nhưng khi gửi vào channel có buffer, nguồn có thể tiếp tục lấy message nhanh hơn khả năng xử lý của consumer. Cần dùng bounded queue, timeout, giới hạn batch và chính sách dừng/giảm tải phù hợp.

### Dấu hiệu vận hành

| Dấu hiệu | Nguyên nhân cần kiểm tra | Hướng xử lý |
|---|---|---|
| Poller chạy thường xuyên nhưng không có message | Trigger quá ngắn hoặc nguồn ít dữ liệu | Tăng delay, dùng cron hoặc cơ chế event-driven nếu nguồn hỗ trợ |
| Polling task kéo dài | Source query chậm, I/O blocking hoặc batch lớn | Đo riêng thời gian receive và send; tối ưu query, timeout và batch |
| Queue downstream tăng | Intake nhanh hơn tốc độ xử lý | Giảm batch/tần suất, tăng consumer có kiểm soát hoặc giới hạn queue |
| Cùng bản ghi được xử lý nhiều lần | Source không claim nguyên tử hoặc redelivery | Dùng lease/ack và idempotency key |
| Bản ghi biến mất sau lỗi | Source đã xóa/ack trước khi xử lý hoàn tất | Đổi thứ tự ack, dùng transaction hoặc trạng thái phục hồi |
| Shutdown mất nhiều thời gian | Source blocking hoặc handler chưa hoàn tất | Đặt I/O timeout, giới hạn drain và theo dõi in-flight work |

Đo riêng số lần poll, số lần source trả null, số message nhận được, thời gian xử lý mỗi chu kỳ, lỗi và backlog. Những số liệu này giúp phân biệt nguồn không có dữ liệu với nguồn đang chậm hoặc adapter không gửi được message.

## 16. Kiểm thử MessageSource và polling flow

Nên kiểm thử source tách biệt với adapter:

- Khi nguồn có dữ liệu, receive() trả message đúng payload và header.
- Khi nguồn rỗng, receive() trả null.
- Khi lỗi nguồn xảy ra, exception được truyền theo chính sách đã thiết kế.
- Khi claim dữ liệu, hai consumer đồng thời không nhận trùng nếu yêu cầu nghiệp vụ không cho phép.
- Khi xử lý thất bại, source có quy tắc redelivery hoặc trạng thái phục hồi rõ ràng.

Với flow, kiểm thử các hành vi:

- Poller kích hoạt source theo cấu hình.
- maxMessagesPerPoll giới hạn số message đúng mong đợi.
- Output channel nhận message và downstream được gọi.
- Endpoint start/stop làm lịch polling bắt đầu và dừng.
- Exception được xử lý qua error handler/advice như thiết kế.
- Transaction rollback hoặc commit có tác dụng đúng trên nguồn thật được sử dụng.

Tránh dùng Thread.sleep() dài trong unit test. Có thể dùng source giả có bộ đếm, latch hoặc scheduler test phù hợp để xác nhận số lần gọi và trạng thái lifecycle một cách xác định.

## 17. Checklist triển khai

Trước khi đưa một source polling vào production, hãy kiểm tra:

- Nguồn có implement MessageSource đúng hợp đồng, trả null khi không có dữ liệu và không nuốt exception không?
- receive() có timeout và thời gian thực thi giới hạn không?
- Trigger có phù hợp với độ trễ nghiệp vụ và tải nguồn không?
- maxMessagesPerPoll có giới hạn phù hợp, tránh một chu kỳ chiếm scheduler quá lâu không?
- Scheduler có đủ thread cho các poller dùng chung không?
- Source claim/ack/commit dữ liệu ở thời điểm nào?
- Nhiều instance có thể lấy trùng dữ liệu không?
- Transaction bao đúng thao tác cần nguyên tử không?
- Retry có giới hạn và chỉ áp dụng cho lỗi có thể hồi phục không?
- Downstream có bounded queue và khả năng xử lý backlog không?
- Endpoint có autoStartup và phase phù hợp với startup/shutdown không?
- Shutdown có xử lý in-flight message và source blocking không?
- Metrics có phân biệt poll rỗng, lỗi nguồn, lỗi gửi và xử lý chậm không?

Khi các điểm này rõ ràng, SourcePollingChannelAdapter trở thành ranh giới intake có thể dự đoán: nguồn nào được hỏi, hỏi vào lúc nào, mỗi lượt lấy bao nhiêu message, message được gửi đi đâu, lỗi được xử lý thế nào và khi nào adapter dừng.

## Tài liệu tham khảo

Các tài liệu dưới đây thuộc Spring Integration Reference Guide. API và default có thể thay đổi theo phiên bản; hãy đối chiếu với phiên bản dependency của ứng dụng.

- [Channel Adapters và inbound adapters](https://docs.spring.io/spring-integration/reference/channel-adapter.html)
- [Message Endpoints và Pollers](https://docs.spring.io/spring-integration/reference/endpoint.html)
- [Java DSL](https://docs.spring.io/spring-integration/reference/dsl.html)
- [Annotation Configuration](https://docs.spring.io/spring-integration/reference/configuration/annotations.html)
- [Transaction Support](https://docs.spring.io/spring-integration/reference/transactions.html)
- [Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html)
- [Metrics and Management](https://docs.spring.io/spring-integration/reference/metrics.html)


# Lỗi cấu hình

Luồng application events có thể thất bại dù logic publisher và listener đều đúng nếu cấu hình Spring, transaction, persistence, serializer hoặc message broker không khớp nhau. Những lỗi này thường xuất hiện khi ứng dụng khởi động, khi publish event đầu tiên, khi listener nhận payload hoặc chỉ khi chạy ở một môi trường cụ thể.

Lỗi cấu hình cần được phát hiện sớm và phân biệt với lỗi tạm thời của hạ tầng hay lỗi dữ liệu của một event cụ thể. Nếu cấu hình sai nhưng hệ thống liên tục retry từng event, backlog sẽ tăng mà nguyên nhân gốc vẫn không được sửa. Với Spring Modulith, cần kiểm tra cả ranh giới module và Event Publication Registry; nếu event đi qua broker, cần kiểm tra thêm topology, converter, quyền truy cập và acknowledgement.

Bài này hệ thống hóa các nhóm lỗi cấu hình thường gặp, cách thiết kế cấu hình có kiểm tra, cách chẩn đoán theo từng ranh giới và cách kiểm thử để phát hiện sai lệch trước khi triển khai.

## 1. Nhận diện lỗi cấu hình trong event flow

Lỗi cấu hình là trạng thái ứng dụng hoặc một thành phần tích hợp được khai báo sai, thiếu hoặc không tương thích với môi trường thực thi. Ví dụ:

- Listener không được đăng ký vì bean không nằm trong component scan hoặc profile hiện tại.
- Listener yêu cầu AFTER_COMMIT nhưng publisher chạy ngoài transaction.
- Event Publication Registry không có persistence implementation hoặc schema chưa được tạo.
- Message converter không đọc được payload do content type hoặc type mapping không khớp.
- Producer publish tới exchange sai tên hoặc routing key không có binding.
- Consumer không có quyền đọc queue hoặc credential trỏ nhầm virtual host.
- Retry policy vô tình requeue message lỗi vô hạn.

Không phải mọi exception đều là lỗi cấu hình. Hãy phân biệt theo dấu hiệu:

| Nhóm lỗi | Ví dụ | Cách xử lý chính |
|---|---|---|
| Cấu hình | Sai exchange, thiếu bean, sai transaction manager | Sửa cấu hình, xác thực lại và triển khai |
| Hạ tầng tạm thời | Broker mất kết nối, database timeout | Retry có backoff và theo dõi phục hồi |
| Dữ liệu/contract | Payload không hợp lệ, schema version không hỗ trợ | Quarantine hoặc dead-letter, xử lý hợp đồng/dữ liệu |
| Lỗi nghiệp vụ | Không đủ tồn kho, đơn hàng đã hủy | Xử lý theo quy tắc nghiệp vụ hoặc compensation |
| Lỗi triển khai | Null pointer, bug trong listener | Sửa code, kiểm thử và triển khai bản mới |

Một lỗi cấu hình cố định thường làm mọi message của cùng luồng thất bại theo cùng một cách. Lỗi tạm thời thường có thể tự hết khi dependency phục hồi. Tuy nhiên, không chỉ dựa vào số lần retry để phân loại; cần xem exception, trạng thái broker/database và cấu hình đang chạy.

## 2. Cấu hình Spring và đăng ký listener

### 2.1. Bean listener không được tạo

Một listener chỉ nhận event khi bean được đăng ký trong ApplicationContext và phương thức listener được phát hiện đúng. Các nguyên nhân phổ biến:

- Class thiếu @Component hoặc annotation stereotype tương ứng.
- Package nằm ngoài phạm vi component scan.
- Bean bị loại bởi @Profile hoặc @ConditionalOnProperty.
- Cấu hình test không nạp module chứa listener.
- Có nhiều bean cùng loại và dependency injection không xác định được bean phù hợp.

Ví dụ listener:

~~~java
@Component
class ReserveInventoryOnOrderPlaced {

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        // Gọi application service của module Inventory
    }
}
~~~

Nếu class không được tạo, event publisher vẫn có thể hoạt động bình thường nhưng listener không được gọi. Với ứng dụng Spring Modulith, hãy kiểm tra cấu trúc module và vị trí package của listener, sau đó xác minh bean thực sự tồn tại trong ApplicationContext.

Không nên thêm component scan toàn bộ root package chỉ để làm listener xuất hiện nếu việc đó phá vỡ ranh giới module. Đặt bean trong package được quản lý đúng và khai báo dependency module có chủ đích.

### 2.2. Event type không khớp listener

Listener chỉ nhận event phù hợp với kiểu tham số và cơ chế dispatch của Spring. Những lỗi thường gặp:

- Publisher phát một DTO mới nhưng listener vẫn lắng nghe class cũ.
- Có wrapper/envelope nhưng listener đăng ký kiểu payload bên trong.
- Generic event bị xóa kiểu hoặc không được resolve như mong đợi.
- Event được serialize rồi deserialize thành kiểu khác với listener dự kiến.

Khi thay đổi event contract, cần cập nhật publisher, listener và test contract cùng nhau. Tránh dùng Object làm tham số listener rồi tự đoán kiểu trong runtime nếu có thể khai báo event type cụ thể.

### 2.3. Profile và conditional configuration

Một cấu hình chạy được ở local có thể không tồn tại ở staging hoặc production do profile khác nhau. Ví dụ:

~~~java
@Configuration
@Profile("rabbit")
class RabbitEventConfiguration {
    // Khai báo publisher, listener container và topology
}
~~~

Nếu môi trường production kích hoạt profile amqp nhưng cấu hình lại yêu cầu rabbit, bean sẽ không được tạo. Hãy quản lý tên profile tập trung, kiểm tra profile đang active lúc startup và có test khởi động cho từng tổ hợp profile được hỗ trợ.

Với @ConditionalOnProperty, đặt matchIfMissing một cách có chủ ý. Một property bị thiếu không nên âm thầm chuyển ứng dụng sang chế độ best-effort nếu nghiệp vụ yêu cầu giao event bền vững.

## 3. Transaction và pha xử lý event

### 3.1. Listener AFTER_COMMIT không được kích hoạt

@TransactionalEventListener mặc định gắn với transaction đang hoạt động. Nếu publisher chạy ngoài transaction, listener có thể không được gọi khi không bật fallbackExecution.

Ví dụ nguồn event cần được gọi qua transaction proxy:

~~~java
@Service
@RequiredArgsConstructor
class PlaceOrderService {

    private final OrderRepository orders;
    private final ApplicationEventPublisher events;

    @Transactional
    public UUID place(PlaceOrderCommand command) {
        Order order = Order.place(command);
        orders.save(order);

        events.publishEvent(new OrderPlaced(order.getId()));
        return order.getId();
    }
}
~~~

Một lỗi phổ biến là gọi phương thức @Transactional từ một phương thức khác trong cùng bean (self-invocation). Lời gọi nội bộ có thể bỏ qua proxy transaction của Spring, khiến transaction không được mở như mong đợi.

Hãy kiểm tra đường gọi thực tế và xác minh transaction đang hoạt động tại thời điểm publish. Không bật fallbackExecution chỉ để che lỗi publisher chạy ngoài transaction nếu event bắt buộc phải gắn với commit nghiệp vụ.

### 3.2. Sai transaction manager

Ứng dụng có thể có nhiều datasource hoặc nhiều transaction manager. Nếu dữ liệu nghiệp vụ dùng transaction manager A nhưng Event Publication Registry hoặc outbox dùng transaction manager B, hai bản ghi không còn được commit/rollback nguyên tử.

Kiểm tra:

- Transaction manager được chọn cho service nghiệp vụ.
- Transaction manager được sử dụng bởi repository publication/outbox.
- Datasource và connection thực tế của từng repository.
- Cấu hình @Transactional(transactionManager = "...") nếu ứng dụng có nhiều manager.

Yêu cầu nguyên tử chỉ đúng khi các thao tác cùng tham gia một transaction resource phù hợp. Không giả định hai repository cùng dùng một database server là đã tự động nằm trong cùng transaction.

### 3.3. Async executor không phù hợp

Listener bất đồng bộ phụ thuộc executor và cấu hình thread pool. Executor thiếu, queue quá nhỏ hoặc rejection policy không phù hợp có thể làm event không được xử lý như mong muốn.

Cần kiểm tra:

- Executor nào được dùng cho listener.
- Core/max pool size và queue capacity.
- Rejection policy khi queue đầy.
- Thread naming để truy vết log.
- Shutdown behavior khi ứng dụng dừng.
- Exception handling cho tác vụ bất đồng bộ.

Không dùng executor dùng chung với tác vụ nền không liên quan nếu một nhóm tác vụ có thể chiếm hết thread và làm listener bị starvation. Với listener quan trọng, cần metric active threads, queue depth và task rejection.

## 4. Event Publication Registry và persistence

Spring Modulith Event Publication Registry theo dõi publication tới từng listener. Để phục hồi sau restart, registry cần persistence implementation bền vững được cấu hình đúng.

### 4.1. Thiếu persistence module hoặc schema

Các lỗi thường gặp:

- Chưa thêm dependency persistence tương ứng với JDBC, JPA hoặc MongoDB.
- Chưa tạo schema/bảng collection theo hướng dẫn của phiên bản đang dùng.
- Migration chưa chạy ở môi trường triển khai.
- Ứng dụng kết nối nhầm database hoặc schema.
- User database thiếu quyền insert/update/select.
- Tên bảng hoặc cấu trúc schema không tương thích với phiên bản thư viện.

Khi registry không ghi được publication, event có thể lỗi ngay lúc publish hoặc mất khả năng phục hồi tùy implementation và cấu hình. Hãy kiểm tra log startup, migration history và quyền database. Không tự tạo bảng theo phỏng đoán; dùng schema/migration đúng phiên bản Spring Modulith.

### 4.2. Publication được ghi nhưng không được hoàn tất

Nếu listener ném exception, publication có thể ở trạng thái chưa hoàn tất. Đây có thể là lỗi nghiệp vụ hoặc lỗi cấu hình phụ thuộc, ví dụ listener không kết nối được database đích.

Kiểm tra theo thứ tự:

1. Event type và listener được đăng ký đúng chưa?
2. Listener có được gọi không?
3. Exception đầu tiên là gì?
4. Transaction của listener có commit không?
5. Registry có cập nhật trạng thái hoàn tất không?
6. Có lỗi quyền ghi hoặc timeout khi cập nhật registry không?

Không xóa publication chưa hoàn tất để làm sạch backlog. Trước khi resubmit, xác định lỗi gốc và bảo đảm listener idempotent.

### 4.3. Kiểm tra persistence khi startup

Với luồng yêu cầu độ tin cậy cao, nên fail fast khi cấu hình persistence bắt buộc bị thiếu. Có thể dùng migration tool để kiểm soát schema và một startup check đọc metadata cần thiết.

Startup check không nên tự chạy một event nghiệp vụ thật. Chỉ xác minh kết nối, schema version, quyền truy cập tối thiểu và cấu hình bean.

## 5. Cấu hình event contract và serialization

Khi event đi qua broker, producer và consumer phải thống nhất format, content type, encoding và schema version.

### 5.1. Content type và converter không khớp

Ví dụ producer gửi JSON nhưng header content type lại là application/octet-stream, hoặc consumer đang dùng converter kỳ vọng JSON. Consumer có thể không deserialize được message.

Cần xác minh:

- Content-Type và content encoding.
- Serializer phía producer.
- MessageConverter phía consumer.
- Envelope và payload structure.
- Type mapping và schema version.
- Quy tắc xử lý trường mới, trường thiếu và enum mới.

Ví dụ cấu hình Jackson converter trong Spring AMQP:

~~~java
@Configuration
class AmqpMessageConfiguration {

    @Bean
    MessageConverter messageConverter(ObjectMapper objectMapper) {
        return new Jackson2JsonMessageConverter(objectMapper);
    }
}
~~~

Producer và consumer phải dùng cùng quy ước. Không yêu cầu consumer tải class Java nội bộ từ producer. Hợp đồng nên là DTO độc lập hoặc schema được version hóa.

### 5.2. Trusted packages và type mapping

Một số converter có kiểm tra package được phép deserialize để tránh nhận object tùy ý. Nếu trusted package thiếu, consumer có thể từ chối payload hợp lệ; nếu mở quá rộng, bề mặt rủi ro tăng lên.

Ưu tiên type mapping rõ ràng từ event type/schema version sang DTO phía consumer. Chỉ cho phép các kiểu cần thiết. Không dùng cấu hình tin cậy toàn bộ package để né lỗi mapping.

### 5.3. Schema version

Khi producer thêm trường bắt buộc hoặc đổi kiểu dữ liệu, consumer cũ có thể thất bại. Mọi event integration nên có schema version hoặc một chiến lược tương thích được định nghĩa rõ.

Các quy tắc thực hành:

- Thêm trường tùy chọn với default tương thích khi có thể.
- Không đổi ý nghĩa trường hiện tại mà không version hóa.
- Không tái sử dụng tên event cho payload có semantics khác.
- Kiểm thử fixture của các version cũ.
- Có adapter/upcaster khi cần chuyển đổi dữ liệu lịch sử.

Lỗi schema thường không tự hết khi retry. Hãy dead-letter hoặc quarantine message, ghi version và nguyên nhân, rồi sửa contract hoặc converter.

## 6. Cấu hình RabbitMQ và AMQP

Khi dùng Spring AMQP, cấu hình sai có thể làm message không được route, producer không nhận confirm hoặc consumer không đọc được queue.

### 6.1. Exchange, queue và binding

Kiểm tra các giá trị:

- Exchange name và exchange type.
- Queue name và durability.
- Binding key hoặc routing key.
- Virtual host.
- Queue arguments, dead-letter exchange và TTL.
- Topology đã tồn tại có cùng thuộc tính với khai báo ứng dụng hay không.

Một producer publish thành công tới exchange không có nghĩa message đã vào queue. Với routing bắt buộc, bật mandatory publish và xử lý publisher returns để phát hiện message không được route.

### 6.2. Publisher confirms và returns

Publisher confirm ACK xác nhận broker đã xử lý publish theo semantics của broker; nó không chứng minh consumer đã xử lý. Confirm NACK hoặc timeout cần được quan sát và xử lý.

Nếu bật mandatory publish, message không được route có thể được trả về producer. Cần kiểm tra cả confirm và returned message trước khi relay đánh dấu outbox SENT.

Tên property và callback API của Spring AMQP thay đổi theo phiên bản. Hãy đối chiếu dependency đang dùng và kiểm thử integration với broker thực tế, tránh sao chép cấu hình từ phiên bản khác.

### 6.3. Consumer acknowledgement và retry

Listener container có thể dùng AUTO, MANUAL hoặc chế độ acknowledgement phù hợp khác. Cấu hình sai thời điểm ack có thể làm mất message hoặc tạo redelivery.

Với side effect database, consumer cần commit transaction nghiệp vụ trước khi ack. Nếu consumer ack rồi mới commit và process dừng, message đã bị xác nhận dù dữ liệu chưa lưu.

Retry policy cần phân loại lỗi tạm thời và lỗi không thể phục hồi. Requeue ngay lập tức không giới hạn có thể tạo vòng lặp nóng. Dead-letter exchange/queue cần được cấu hình và giám sát.

## 7. Cấu hình broker, credential và quyền truy cập

Một cấu hình connection sai có thể khiến ứng dụng không kết nối được hoặc kết nối nhầm môi trường.

Các giá trị cần kiểm tra:

- Host, port và virtual host.
- Username, password hoặc cơ chế xác thực.
- TLS, trust store và hostname verification.
- Connection timeout, heartbeat và channel cache.
- Quyền configure, write và read trên exchange/queue.
- Network policy, firewall và DNS.

Không lưu secret trong source code, file cấu hình được commit hoặc log. Dùng secret manager hoặc biến môi trường được quản lý. Khi credential được rotate, cần bảo đảm connection pool được tạo lại hoặc refresh theo cơ chế ứng dụng hỗ trợ.

Phân quyền tối thiểu: publisher chỉ cần quyền write tới exchange cần thiết; consumer chỉ cần read queue được cấp. Không dùng tài khoản administrator cho mọi service.

## 8. Cấu hình retry và dead-letter

Retry policy là một phần của cấu hình vận hành. Một policy sai có thể làm message thất lạc, bị xử lý lặp hoặc gây tải lớn.

Cần xác định:

- Số lần retry tối đa.
- Initial delay, multiplier, max delay và jitter.
- Loại exception được retry.
- Loại exception phải dead-letter ngay.
- Requeue behavior.
- Dead-letter destination.
- Retention và quy trình replay.
- Cảnh báo khi backlog hoặc DLQ tăng.

Lỗi cấu hình cố định như exchange không tồn tại hoặc credential sai thường không nên retry từng event trong thời gian dài. Nên phát hiện ở startup hoặc health check, dừng luồng gửi và cảnh báo rõ. Lỗi broker tạm thời có thể retry theo backoff.

Không dùng một retry policy chung cho mọi listener nếu các dependency có SLA và semantics khác nhau. Một lỗi schema không cần retry giống lỗi timeout database.

## 9. Quản lý cấu hình theo môi trường

Cấu hình local, test, staging và production cần cùng một cấu trúc nhưng giá trị khác nhau. Tránh tạo những khác biệt ẩn khiến lỗi chỉ xuất hiện khi triển khai.

Ví dụ dùng @ConfigurationProperties:

~~~java
@ConfigurationProperties(prefix = "app.events")
@Validated
public record EventProperties(
        @NotBlank String exchange,
        @NotBlank String routingKey,
        @NotBlank String queue,
        @Min(1) int maxAttempts,
        @NotNull Duration initialBackoff
) {}
~~~

File application.yml có thể khai báo giá trị theo profile:

~~~yaml
app:
  events:
    exchange: business.events
    routing-key: order.placed
    queue: inventory.order-events
    max-attempts: 5
    initial-backoff: 2s
~~~

Giá trị trên chỉ là ví dụ. Production nên lấy endpoint và secret từ nguồn cấu hình bảo mật. Hãy bật validation khi khởi động để thiếu exchange, queue hoặc retry limit làm ứng dụng báo lỗi rõ ràng thay vì âm thầm chạy sai.

Không để default value nguy hiểm. Ví dụ, nếu publisher-confirms bị thiếu, ứng dụng không nên tự chuyển sang chế độ không đợi confirm khi event có yêu cầu không được mất.

## 10. Fail fast và kiểm tra cấu hình

Fail fast nghĩa là ứng dụng phát hiện cấu hình bắt buộc sai ngay lúc khởi động hoặc trước khi nhận traffic. Một số kiểm tra có thể thực hiện:

- Property bắt buộc có giá trị hợp lệ.
- Bean publisher/listener cần thiết đã được tạo.
- Transaction manager và persistence implementation được chọn đúng.
- Database schema/migration phù hợp.
- Broker connection và quyền tối thiểu hoạt động.
- Exchange, queue và binding cần thiết tồn tại hoặc được khai báo thành công.
- Serializer/deserializer có thể đọc fixture schema được hỗ trợ.
- Retry, DLQ và acknowledgement mode phù hợp với luồng.

Có thể dùng ApplicationRunner hoặc health indicator để kiểm tra dependency, nhưng cần giới hạn timeout và phân biệt trạng thái startup với trạng thái dependency tạm thời. Không gửi message nghiệp vụ giả chỉ để xác minh broker.

Health check nên có hai mức:

- Liveness: process còn hoạt động và không bị deadlock.
- Readiness: dependency bắt buộc và cấu hình cần thiết đã sẵn sàng nhận traffic.

Không làm liveness fail chỉ vì broker tạm thời mất kết nối nếu ứng dụng có thể tiếp tục phục vụ phần nội bộ và có outbox bền vững; readiness và metric sẽ phản ánh khả năng gửi ra ngoài.

## 11. Chẩn đoán lỗi theo ranh giới

Khi event không tới nơi nhận, hãy lần theo từng ranh giới thay vì sửa ngẫu nhiên nhiều property.

| Dấu hiệu | Kiểm tra đầu tiên | Bằng chứng cần thu thập |
|---|---|---|
| Listener không được gọi | Bean registration, event type, transaction phase | ApplicationContext, listener log, publication record |
| Event bị bỏ qua khi không có transaction | Đường gọi @Transactional, proxy, fallback setting | Transaction active state tại publish |
| Publication không được lưu | Persistence bean, schema, transaction manager | SQL/DB log, migration version |
| Publication chưa hoàn tất liên tục | Exception listener, transaction listener, registry update | Event ID, listener ID, stack trace |
| Producer không kết nối broker | Host, port, vhost, credential, TLS | Connection exception, broker log |
| Message không vào queue | Exchange, routing key, binding, mandatory return | Returned message, broker topology |
| Consumer deserialize thất bại | Content type, converter, type mapping, schema | Message headers, payload version |
| Message redeliver liên tục | Ack mode, exception handler, retry/DLX | Redelivery count, consumer log |
| Outbox backlog tăng | Relay health, confirms, permissions, lease | Outbox age, send result, broker metrics |

Nên có eventId, correlationId và aggregateId xuyên suốt log để ghép nối các bước. Không log secret hoặc payload nhạy cảm.

Khi điều tra, ghi nhận cấu hình đã áp dụng tại runtime (đã loại secret), profile active, phiên bản thư viện và thời điểm triển khai. Đây là dữ liệu quan trọng để tìm lỗi chỉ xảy ra ở một môi trường.

## 12. Kiểm thử cấu hình

Cấu hình phải được kiểm thử như một phần của ứng dụng, không chỉ được xem là file YAML hợp lệ.

### 12.1. Configuration binding test

Xác minh property được bind đúng kiểu và validation từ chối giá trị thiếu hoặc không hợp lệ. Test cả profile mặc định và profile được hỗ trợ.

### 12.2. Application context test

Khởi động context với cấu hình tương ứng để phát hiện:

- Bean bị thiếu hoặc tạo trùng.
- Conditional configuration không khớp.
- Qualifier/transaction manager sai.
- Listener không được đăng ký.
- Message converter không tương thích.

Không cần khởi động toàn bộ hệ thống cho mọi unit test; chỉ context test các cấu hình quan trọng và một số profile đại diện.

### 12.3. Module event test

Dùng Spring Modulith test support để xác minh event được phát tới listener module mong muốn và cấu trúc module không vi phạm dependency rule. Kiểm tra cả trường hợp publisher transaction rollback và listener thất bại.

Test module không thay thế integration test broker. Nó xác minh giao tiếp nội bộ và ranh giới module.

### 12.4. Broker integration test

Với RabbitMQ hoặc broker tương ứng, kiểm thử:

- Exchange/queue/binding được khai báo đúng.
- Routing key đưa message tới queue mong muốn.
- Publisher confirm và returned message được xử lý.
- Consumer ack sau transaction.
- Retry và dead-letter hoạt động theo policy.
- Payload cũ/mới deserialize đúng hoặc bị từ chối có kiểm soát.
- Credential và permission tối thiểu đủ cho thao tác cần thiết.

Dùng container broker hoặc môi trường test tương thích để xác minh semantics thật. Mock RabbitTemplate chỉ kiểm tra lời gọi code, không chứng minh topology và acknowledgement.

### 12.5. Kiểm tra cấu hình đã triển khai

CI có thể validate file cấu hình, nhưng vẫn cần kiểm tra deployment manifest, environment variable và secret reference sau khi render. Tránh in giá trị secret trong log CI. Có thể kiểm tra sự hiện diện và định dạng của biến mà không tiết lộ nội dung.

## 13. Thay đổi cấu hình an toàn

Một thay đổi cấu hình có thể ảnh hưởng mọi message đang chờ. Cần có kế hoạch rollout:

1. Xác định property hoặc topology sẽ thay đổi và các consumer bị ảnh hưởng.
2. Kiểm tra tương thích giữa producer và consumer trong giai đoạn rolling deployment.
3. Nếu đổi exchange, queue hoặc schema, tạo binding/consumer mới trước khi chuyển producer khi cần.
4. Giữ khả năng rollback và không xóa queue có message chưa xử lý.
5. Triển khai theo từng môi trường, quan sát confirm, backlog và DLQ.
6. Chỉ dọn topology cũ khi đã xác minh không còn producer/consumer sử dụng.

Với thay đổi credential, có thể tạo credential mới, cấp quyền, triển khai ứng dụng dùng credential mới, xác minh kết nối rồi mới thu hồi credential cũ. Với schema, ưu tiên triển khai consumer tương thích trước producer phát version mới.

Không thay đổi nhiều nhóm cấu hình cùng lúc nếu chưa có cách xác định nguyên nhân khi rollout thất bại.

## 14. Các lỗi cấu hình thường gặp

**Listener không nằm trong component scan.** Bean không được tạo nên event không có consumer. Kiểm tra package, stereotype và profile.

**Sai event type.** Publisher phát DTO mới nhưng listener vẫn đăng ký kiểu cũ. Kiểm tra contract và converter.

**Publisher chạy ngoài transaction.** AFTER_COMMIT listener không được kích hoạt theo kỳ vọng. Kiểm tra proxy và transaction boundary.

**Sai transaction manager.** Dữ liệu nghiệp vụ và publication/outbox không commit cùng nhau. Kiểm tra datasource và transaction manager thực tế.

**Thiếu persistence schema cho registry.** Publication không được lưu bền vững hoặc listener lỗi khi ghi trạng thái. Dùng migration đúng phiên bản.

**Sai exchange hoặc binding.** Producer gửi nhưng không có queue nhận. Kiểm tra mandatory returns và topology.

**Sai content type hoặc schema.** Consumer không deserialize được. Kiểm tra converter, headers và schema version.

**Credential thiếu quyền.** Kết nối thành công nhưng publish/consume bị từ chối. Cấp quyền tối thiểu đúng vhost và resource.

**Retry vô hạn cho lỗi cấu hình.** Backlog tăng mà nguyên nhân không đổi. Fail fast hoặc dừng luồng liên quan, sửa cấu hình rồi phục hồi có kiểm soát.

**Default value che lỗi.** Ứng dụng chạy ở chế độ yếu hơn yêu cầu. Validate property bắt buộc và fail startup khi thiếu.

## 15. Quy trình xử lý một lỗi cấu hình event

Khi phát hiện luồng event không hoạt động, có thể làm theo trình tự:

1. Xác định eventId, publisher, listener/consumer và môi trường xảy ra lỗi.
2. Phân loại lỗi là cấu hình, hạ tầng tạm thời, dữ liệu hay nghiệp vụ.
3. Kiểm tra bean registration, event type và transaction phase.
4. Kiểm tra Event Publication Registry/outbox persistence nếu có.
5. Nếu qua broker, kiểm tra connection, vhost, permission, exchange, queue và binding.
6. Kiểm tra content type, serializer, schema version và retry/ack policy.
7. Sửa một nhóm cấu hình có phạm vi rõ, validate và triển khai.
8. Kiểm thử một event đại diện qua đúng luồng.
9. Phục hồi publication/outbox/DLQ bị ảnh hưởng bằng retry hoặc replay có kiểm soát.
10. Theo dõi backlog, lỗi mới và metric sau khi phục hồi.

Không xóa publication, outbox record hoặc message trong DLQ trước khi biết trạng thái side effect. Nếu không chắc consumer đã xử lý hay chưa, kiểm tra idempotency record hoặc trạng thái nghiệp vụ trước khi replay.

Cấu hình event tốt phải có validation, quan sát được và được kiểm thử ở đúng ranh giới. Spring Modulith giúp tổ chức publisher, listener và publication registry trong ứng dụng; adapter và broker bổ sung các cấu hình vận chuyển riêng. Khi bean, transaction, persistence, schema, topology, permission và retry policy được kiểm tra rõ ràng, lỗi cấu hình có thể được phát hiện trước khi tạo backlog và phục hồi mà không làm mất hoặc nhân đôi side effect.

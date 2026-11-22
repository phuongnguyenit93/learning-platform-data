# Khởi động lại flow và kiểm chứng không mất trạng thái cần thiết

## 1. Đặt vấn đề: flow chạy lại được chưa chắc phục hồi đúng

Một **integration flow** trong Spring Boot thường nối nhiều bước: nhận HTTP/JMS, đọc dữ liệu từ database hoặc file, biến đổi payload, gọi HTTP client, cập nhật cache, ghi database và gửi thông điệp cho broker. Trong Spring Integration, các bước đó có thể nằm trên các channel, endpoint, poller, aggregator, resequencer và adapter khác nhau.

Khi tiến trình Spring Boot dừng đột ngột, container bị thay thế, kết nối broker bị ngắt hoặc flow được stop/start, trạng thái còn trong bộ nhớ có thể biến mất. Việc ứng dụng **khởi động thành công** chỉ chứng minh bean và endpoint có thể hoạt động trở lại; nó không chứng minh những công việc đã nhận trước khi dừng được xử lý đầy đủ.

Ví dụ: một flow nhận sự kiện **OrderAccepted**, đợi đủ các kết quả xác nhận tồn kho rồi phát **OrderReady**. Ngay trước khi restart, một nhóm aggregation đã có hai trong ba sự kiện. Nếu nhóm đó chỉ tồn tại trong bộ nhớ, khi ứng dụng trở lại có thể không còn cách hoàn tất đơn hàng. Nếu input được broker phát lại toàn bộ, nhóm mới có thể được tạo lại nhưng cũng có nguy cơ gửi **OrderReady** hai lần.

Mục tiêu của bài này là trả lời ba câu hỏi:

1. **Trạng thái nào cần tồn tại qua lần restart?** Không phải mọi biến hay message trong bộ nhớ đều cần lưu bền.
2. **Tại ranh giới nào một message có thể bị mất hoặc được xử lý lặp?** Phải xét transaction, acknowledgement, checkpoint và hệ thống ngoài.
3. **Kiểm chứng bằng cách nào?** Cần đối soát message nghiệp vụ, trạng thái đã lưu và hành vi phục hồi sau các điểm lỗi có chủ đích.

Đây là một phần của chủ đề **Lỗi và trạng thái flow** trong module **SPRING_BOOT_INTEGRATION**: quản lý cấu hình, hợp đồng dữ liệu, giao dịch, lỗi, chống trùng lặp, kiểm thử và quan sát các luồng tích hợp thực tế giữa database, HTTP, cache, broker và adapter của Spring Integration.

## 2. Định nghĩa chính xác “không mất trạng thái cần thiết”

Một hệ thống không nhất thiết phải giữ mọi đối tượng Java, thread hay queue trong RAM sau khi restart. Nó cần giữ **đủ thông tin để phục hồi kết quả nghiệp vụ một cách đúng đắn**.

Với mỗi sự kiện đã được hệ thống **chấp nhận bền vững**, yêu cầu phục hồi thường là:

- Sự kiện đã xử lý thành công có bằng chứng kết quả hoặc dấu xử lý để tránh tác động lặp.
- Sự kiện chưa xử lý xong vẫn còn ở **nguồn bền vững** hoặc hàng đợi/trạng thái trung gian bền vững để tiếp tục.
- Sự kiện không thể xử lý được chuyển vào trạng thái lỗi có thể điều tra, như **dead-letter queue (DLQ)** hoặc bảng lỗi, thay vì biến mất lặng lẽ.
- Dữ liệu đã commit, ý định phát sự kiện và các tác dụng phụ không bị diễn giải sai khi flow chạy lại.
- Correlation ID, thứ tự cần thiết, tiến độ xử lý và trạng thái gom nhóm được lưu nếu thiếu chúng không thể tạo lại kết quả đúng.

Một bất biến hữu ích để đối soát là:

> Với mọi **eventId** đã được tiếp nhận bền vững, hệ thống phải xác định được kết quả đã xử lý, trạng thái còn chờ xử lý hoặc nơi lưu lỗi để phục hồi; không có eventId biến mất không lý do.

Đây là mục tiêu **không mất công việc nghiệp vụ**, không đồng nghĩa broker không bao giờ giao trùng. Trên thực tế, phối hợp nhiều tài nguyên thường thiết kế **at-least-once delivery** và **idempotent processing**.

### Phân loại trạng thái

| Loại trạng thái | Ví dụ | Cần bền vững khi nào? |
| --- | --- | --- |
| **Trạng thái nghiệp vụ** | Đơn hàng đã thanh toán, tồn kho đã giữ, mã giao dịch thanh toán. | Gần như luôn phải bền vững; phải tuân thủ tính toàn vẹn và giao dịch của nguồn dữ liệu chính. |
| **Message đang chờ** | Sự kiện đã nhận nhưng chưa xử lý, message trong queue nội bộ. | Khi không có nguồn upstream bảo đảm phát lại sau restart hoặc việc nhận upstream đã được xác nhận. |
| **Tiến độ đọc/checkpoint** | Offset, cursor, tên file đã xử lý, thời điểm polling cuối, watermark. | Khi việc đọc lại từ đầu quá đắt hoặc sẽ tạo sai lệch; phải phối hợp với commit kết quả. |
| **Trạng thái tương quan** | Các phần của một nhóm aggregator, sequence/correlation key, timeout chưa hết. | Khi nhóm có thể kéo dài qua restart và không thể tái dựng an toàn từ nguồn. |
| **Dấu xử lý/idempotency** | Khóa eventId, paymentId hoặc operationId đã áp dụng. | Khi có thể nhận lại thông điệp và xử lý lặp gây thay đổi nghiệp vụ. |
| **Ý định phát sự kiện** | Outbox record chưa publish. | Khi database đã commit nhưng broker có thể chưa nhận sự kiện. |
| **Trạng thái lỗi** | Payload lỗi, số lần retry, lý do thất bại, DLQ. | Khi cần thử lại, sửa dữ liệu hoặc điều tra sau restart. |
| **Trạng thái tạm có thể tái tạo** | Cache tính toán lại được, biến cục bộ, kết nối TCP, thread đang chạy. | Thường không cần bền vững, miễn cách tái tạo và mức nhất quán chấp nhận được đã rõ. |

**Điểm quyết định** không phải “có dùng message store hay không” mà là **có thể chứng minh một công việc đã được tiếp nhận sẽ không biến mất sau khi hệ thống dừng ở bất kỳ bước nào hay không**.

## 3. Thành phần Spring Integration giữ trạng thái như thế nào?

### 3.1. Channel và sự khác nhau giữa truyền, xếp hàng, lưu bền

| Thành phần/cách dùng | Hành vi quan trọng khi restart |
| --- | --- |
| **DirectChannel** | Chuyển message đồng bộ cho subscriber trong luồng gọi hiện tại; không tạo queue bền vững. Độ an toàn phụ thuộc nguồn và transaction gọi vào channel. |
| **ExecutorChannel** | Chuyển việc xử lý sang executor; công việc còn trong bộ nhớ hoặc hàng đợi của executor có thể mất khi tiến trình chết. Ranh giới thread cũng có thể cắt transaction context ban đầu. |
| **QueueChannel** dùng store mặc định trong bộ nhớ | Message chưa được nhận vẫn có thể mất khi JVM chết. |
| **QueueChannel** có persistent message store phù hợp | Message lưu trong store có thể được lấy lại sau restart; vẫn phải xét thời điểm xóa khỏi queue so với commit công việc downstream. |
| **PublishSubscribeChannel** | Phân phát cho subscriber; không tự cung cấp cơ chế lưu bền/replay cho mọi subscriber. Khi xử lý bất đồng bộ, phải xét từng nhánh và cơ chế xác nhận riêng. |
| **JMS/AMQP/Kafka adapter** | Có thể dựa vào broker/log bền vững, nhưng phụ thuộc delivery mode, acknowledgement/offset, retention, consumer group và chính sách retry cụ thể. |

Chẳng hạn, việc đặt một **QueueChannel** giữa hai handler chỉ tạo bộ đệm nội bộ. Nếu lưu message trong bộ nhớ, shutdown cưỡng bức có thể làm mất buffer. Nếu dùng **JdbcChannelMessageStore** để lưu queue trên database, dữ liệu có khả năng tồn tại qua restart, với điều kiện schema, lưu trữ và cách lấy message được cấu hình đúng.

Lưu bền queue **không tự động** làm toàn bộ flow có giao dịch nguyên tử. Nếu message bị lấy khỏi queue và transaction xóa message commit **trước** khi handler ghi kết quả, crash tại giữa hai thao tác vẫn có thể làm mất công việc. Cần đặt ranh giới transaction của poller/store và cập nhật nghiệp vụ phù hợp, hoặc thiết kế khả năng replay và dedup.

### 3.2. Aggregator, resequencer và công việc chờ thời điểm

**Aggregator** cần lưu các message đã vào một nhóm, khóa tương quan (**correlation key**), điều kiện release, timeout và trạng thái nhóm. **Resequencer** cần nhớ các phần đang chờ để khôi phục thứ tự. Nếu dùng message group store trong bộ nhớ, những phần chưa hoàn chỉnh có thể mất khi restart.

Spring Integration có các khái niệm **MessageStore** và **MessageGroupStore**; có thể sử dụng các triển khai JDBC phù hợp, như **JdbcMessageStore**, để lưu trạng thái nhóm trên database. Phải kiểm tra:

- Group ID và correlation key có ổn định qua deploy và quá trình serialize/deserialize hay không.
- Store có thực sự giữ cả payload, header, sequence và metadata cần cho release hay không.
- Quy tắc **release**, **expire**, **discard** và xử lý partial result sau timeout có làm mất dữ liệu cần thiết không.
- Việc đánh dấu nhóm hoàn tất/xóa nhóm có được phối hợp với việc downstream nhận kết quả bền vững không.
- Các instance song song có dùng cùng store, lock thích hợp và quy tắc ownership để không release một nhóm lặp hoặc tranh chấp.

Chỉ lưu group chưa đủ nếu aggregator đã xóa group sau khi tạo output nhưng output chưa được một bước bền vững tiếp nhận. Ngược lại, nếu output được gửi thành công mà group chưa đánh dấu hoàn tất, restart có thể gửi lại. Cần phân tích cả hai **failure window**.

Các công việc bị **delay**, scheduler nội bộ hoặc retry đang đợi trong RAM cũng cần được xem xét. Một timer trong JVM không phải một hàng đợi công việc bền vững; nếu thời hạn nghiệp vụ phải sống qua restart, hãy lưu **dueAt**, ID nghiệp vụ và trạng thái xử lý ở kho bền vững để scheduler truy xuất lại.

### 3.3. Metadata store và checkpoint của inbound adapter

Các adapter đọc file, remote file hoặc nguồn polling thường dùng **MetadataStore** để ghi nhận khóa đã thấy, thời gian sửa đổi, giá trị cursor hoặc thông tin giúp tránh đọc trùng. Một **SimpleMetadataStore** đặt trong bộ nhớ sẽ mất trạng thái sau restart. Tùy bài toán có thể dùng **JdbcMetadataStore** hoặc một kho metadata bền vững khác.

Tuy nhiên, **checkpoint đã lưu không chứng minh dữ liệu đã được xử lý xong**. Ví dụ:

1. File adapter ghi “file A đã xem”.
2. Handler chưa commit dữ liệu của file A.
3. JVM dừng.
4. Lần khởi động sau, bộ lọc bỏ qua file A vì metadata nói đã đọc.

Đây là tình huống mất công việc dù metadata được lưu rất tốt. Giải pháp cần ràng buộc checkpoint với việc chấp nhận hoặc hoàn tất xử lý bền vững, hoặc cố ý cho đọc lại rồi loại trùng bằng khóa nghiệp vụ. Với file, có thể dùng vùng **incoming / processing / completed / failed**, tên file ổn định, manifest hoặc bảng inbox, đồng thời kiểm tra file chưa được ghi dở.

### 3.4. Retry và error channel

**RequestHandlerRetryAdvice** hoặc retry trong một handler có thể giúp vượt lỗi tạm thời mà không cần restart. Nhưng số lần thử và trạng thái backoff chỉ ở trong bộ nhớ, nếu không cấu hình cơ chế lưu bền riêng, sẽ không mặc nhiên sống qua lần chết tiến trình.

**errorChannel** giúp route lỗi trong Spring Integration; việc có error flow không đồng nghĩa lỗi đã được lưu vào kho bền vững. Nếu yêu cầu xử lý lại sau restart, phải chuyển lỗi sang **DLQ**, bảng lỗi hoặc nguồn lưu bền tương đương. Quy tắc xử lý exception rất quan trọng: nếu handler nuốt lỗi và trả về thành công, nguồn có thể xác nhận message dù công việc thất bại.

## 4. Tìm “cửa sổ mất dữ liệu” bằng ranh giới commit và acknowledge

Sơ đồ sau mô tả một flow nhận sự kiện từ broker rồi cập nhật database:

~~~mermaid
sequenceDiagram
    participant B as Broker bền vững
    participant A as Inbound adapter
    participant H as Integration handler
    participant D as Database
    B->>A: Giao eventId=E-101
    A->>H: Message
    H->>D: BEGIN, thay đổi nghiệp vụ và lưu dấu E-101
    D-->>H: COMMIT
    H-->>A: Xử lý thành công
    A->>B: ACK/COMMIT nhận
    Note over A,B: Có thể chết sau DB commit nhưng trước ACK
~~~

Nếu database commit xong mà adapter chưa xác nhận nguồn, broker có thể gửi lại **E-101**. Đây là hành vi cần dự liệu, không tự động là lỗi. Nếu dấu đã xử lý **E-101** và thay đổi nghiệp vụ được commit **trong cùng transaction database**, lần nhận lại có thể bỏ qua một cách an toàn.

Nguy hiểm hơn là **ACK hoặc checkpoint nguồn xảy ra trước khi có bằng chứng kết quả bền vững**. Nếu ứng dụng chết sau ACK nhưng trước database commit, upstream có thể không phát lại. Điều này làm mất công việc.

| Thời điểm dừng | Nguồn còn khả năng phát lại? | Kết quả nghiệp vụ? | Thiết kế phục hồi |
| --- | --- | --- | --- |
| Trước khi nguồn xác nhận và trước DB commit | Thường có, nếu nguồn bền vững và cấu hình ACK/offset đúng. | Chưa commit. | Cho retry; dữ liệu đầu vào còn ở nguồn. |
| Sau DB commit, trước ACK | Có thể được phát lại. | Đã commit. | Ghi dấu idempotency cùng transaction; lần sau nhận lại nhưng không áp dụng lặp. |
| Sau ACK, trước DB commit | Có thể **không** còn. | Chưa chắc có. | Tránh thứ tự này; đưa payload vào inbox bền vững hoặc thay đổi ranh giới ACK. |
| Sau DB commit, trước khi gửi sự kiện outbound | Nguồn có thể đã ACK. | Đã commit nhưng downstream chưa nhận tín hiệu. | Transactional outbox cho ý định phát sự kiện. |
| Sau khi outbound được broker nhận, trước khi đánh dấu đã phát | Có thể phát lại outbound. | Downstream có thể thấy trùng. | Stable eventId và downstream dedup/idempotency. |

Các cột “còn khả năng phát lại” phụ thuộc thực tế vào cấu hình broker, retention, consumer offset, retry policy và trạng thái commit; không suy luận tuyệt đối từ việc dùng một adapter.

### Transaction của Spring không tự đi xuyên qua mọi endpoint

Một **@Transactional** ở service chỉ quản lý tài nguyên được transaction manager đó bao bọc. **DirectChannel** thường gọi downstream đồng bộ và có thể duy trì transaction context cùng thread, nhưng **ExecutorChannel**, task executor, asynchronous gateway hoặc một lần gửi qua broker tạo ranh giới khác.

Giao dịch JDBC/JPA không mặc nhiên bao gồm ACK JMS, gửi HTTP hay cache. Để commit đồng thời JMS và database ở mức tài nguyên có thể cần **JTA/XA** với các resource đã tham gia; ngay cả XA không bao gồm tác dụng phụ của HTTP hoặc email thông thường.

Với nhiều luồng tích hợp thực tế, lựa chọn rõ ràng hơn là **nguồn bền vững + idempotent consumer + transactional inbox/outbox**, chấp nhận việc chuyển trạng thái giữa các hệ thống theo cơ chế eventual consistency và có đối soát.

## 5. Mẫu thiết kế có thể phục hồi

### Mẫu A — Đọc lại từ nguồn bền vững và xử lý idempotent

Nguồn có thể là broker còn lưu message, transaction log hoặc bảng inbox trong database. Đặt khóa nghiệp vụ ổn định (**eventId**, **paymentId**, **sourceId + sequence**) vào payload và dùng khóa đó để quyết định đã xử lý hay chưa.

Nếu lần retry chỉ tạo message mới với **MessageHeaders.ID** khác, không nên dùng ID runtime này làm khóa nghiệp vụ duy nhất. ID message ở tầng framework có thể thay đổi khi message được tái tạo, chuyển đổi hoặc gửi lại. Khóa idempotency phải ổn định đối với **cùng một thao tác nghiệp vụ**, kể cả qua deploy/restart.

### Mẫu B — Chấp nhận vào inbox bền vững trước khi ACK nguồn

Khi adapter gốc không cung cấp redelivery đủ tin cậy, một bước nhận có thể ghi **payload + eventId + trạng thái** vào bảng inbox hoặc queue bền vững. Chỉ ACK nguồn khi đã xác minh inbox commit. Worker xử lý các record ở trạng thái **PENDING** và chuyển thành **DONE/FAILED** bằng giao dịch rõ ràng.

Lưu ý vẫn có thể có cửa sổ **inbox commit rồi ACK thất bại**; nguồn phát lại cùng eventId. Unique constraint của inbox giúp điều đó trở thành retry an toàn.

### Mẫu C — Lưu message/group/checkpoint cho stateful flow

Nếu lưu state trong Spring Integration là cần thiết, lựa chọn store bền vững theo đúng vai trò:

- **JdbcChannelMessageStore** cho những channel có khả năng lưu message cần nhận lại sau restart.
- **JdbcMessageStore / MessageGroupStore** cho aggregation và các nhóm message cần tồn tại qua restart.
- **JdbcMetadataStore** cho khóa metadata, cursor hoặc trạng thái lọc cần giữ qua lần deploy.
- **JdbcLockRegistry** hoặc cơ chế điều phối tương đương nếu nhiều instance cùng tranh một công việc và store chung.

Các lớp và cách khởi tạo cụ thể phụ thuộc phiên bản Spring Integration, database và cấu hình schema JDBC; cần áp dụng schema store đúng phiên bản thư viện. Phải cấu hình transaction/poller thích hợp để việc lấy message ra khỏi store, xử lý và ghi kết quả không tạo ra khoảng mất công việc.

### Mẫu D — Outbox cho chiều phát sự kiện

Nếu flow cập nhật database rồi phát JMS/Kafka hoặc gọi một adapter outbound, lưu **kết quả nghiệp vụ + outbox event** trong một database transaction. Relay đọc outbox và gửi đi sau, đánh dấu trạng thái phát khi broker chấp nhận. Relay có thể gửi trùng sau crash, nên consumer cần xử lý idempotent.

Outbox bảo vệ **ý định gửi**; nó không có nghĩa chỉ có đúng một lần gửi vật lý. Khi downstream cần thứ tự theo từng đơn hàng, payload nên có **aggregateId** và **version/sequence**, kèm quy tắc bảo toàn hoặc xác minh thứ tự.

### Mẫu E — Bù trừ khi đã gọi hệ thống bên ngoài

Nếu handler đã gọi HTTP tạo thanh toán, gửi email hay cập nhật một hệ thống không tham gia transaction, việc replay vô điều kiện có thể tạo tác dụng phụ lặp. Dùng **idempotency key** phía API, truy vấn trạng thái sau timeout và hành động bù trừ tương ứng (ví dụ hoàn tiền hoặc hủy giữ chỗ). Một giao dịch database rollback không tự đảo ngược những hành động đó.

## 6. Ví dụ: khởi động lại flow xử lý sự kiện đơn hàng

### 6.1. Mục tiêu và ranh giới

Giả sử broker đang giữ sự kiện **OrderReady** với **eventId** duy nhất theo nghiệp vụ. Spring Integration dùng inbound adapter chuyển payload đã giải mã thành Java record, rồi chuyển qua **DirectChannel** đến một handler cập nhật database.

Luồng mong muốn:

~~~mermaid
flowchart LR
    A[(Broker bền vững)] -->|OrderReady, eventId| B[Inbound adapter]
    B --> C[DirectChannel]
    C --> D[Service xử lý]
    D --> E[(orders)]
    D --> F[(processed_flow_events)]
    D --> G[(outbox_events)]
    G --> H[Relay phát sự kiện]
    H --> I[(Broker / consumer khác)]
~~~

**DirectChannel** không lưu bền đầu vào. Hệ thống dựa vào broker giữ message chưa ACK và service xử lý trong transaction database. Khi cần tách luồng bất đồng bộ, không được đơn giản thay bằng ExecutorChannel rồi coi trạng thái đang chờ vẫn an toàn sau restart.

Để giữ thao tác nghiệp vụ và dấu xử lý trong cùng một database transaction, tạo bảng:

~~~sql
CREATE TABLE processed_flow_events (
    flow_name    VARCHAR(100) NOT NULL,
    event_id     VARCHAR(150) NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (flow_name, event_id)
);
~~~

Bảng đơn hàng **orders** có **id** và **status**; giá trị ban đầu **NEW**, sau khi xử lý sẽ là **READY**. Mỗi OrderReady chứa ID nghiệp vụ bền vững:

~~~java
public record OrderReady(String eventId, long orderId) {}
~~~

### 6.2. Tiếp nhận vào Spring Integration

Ví dụ với Spring Integration sử dụng annotation (phần import và cấu hình adapter nguồn được lược bớt):

~~~java
@Configuration
class OrderChannels {
    @Bean
    MessageChannel orderEvents() {
        return new DirectChannel();
    }
}

@Component
class OrderFlowHandler {
    private final OrderEventService service;

    OrderFlowHandler(OrderEventService service) {
        this.service = service;
    }

    @ServiceActivator(inputChannel = "orderEvents")
    public void handle(Message<OrderReady> message) {
        service.applyOnce(message.getPayload());
    }
}
~~~

Inbound adapter phải gửi đúng payload kiểu **OrderReady** vào channel **orderEvents** và được cấu hình để **chỉ xác nhận nguồn sau khi handler xử lý thành công**. Đây là giả định kiến trúc phải kiểm tra bằng integration test đối với adapter và broker thực tế; code trên chưa tự cấu hình acknowledgement cho JMS/Kafka.

### 6.3. Ghi dấu và cập nhật nghiệp vụ cùng transaction

Ví dụ dưới đây dùng **JdbcTemplate + PostgreSQL** và một database transaction manager cho service:

~~~java
@Service
class OrderEventService {
    private final JdbcTemplate jdbc;

    OrderEventService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void applyOnce(OrderReady event) {
        if (event.eventId() == null || event.eventId().isBlank()) {
            throw new IllegalArgumentException("eventId is required");
        }

        int inserted = jdbc.update("""
            INSERT INTO processed_flow_events(flow_name, event_id)
            VALUES (?, ?)
            ON CONFLICT DO NOTHING
            """, "order-ready-flow", event.eventId());

        if (inserted == 0) {
            return; // Event đã được xử lý trong transaction trước.
        }

        int updated = jdbc.update("""
            UPDATE orders
               SET status = 'READY'
             WHERE id = ?
               AND status = 'NEW'
            """, event.orderId());

        if (updated != 1) {
            throw new IllegalStateException(
                "Order not found or unexpected previous state");
        }

        // Nếu cần phát event, INSERT outbox record tại đây
        // trong cùng database transaction.
    }
}
~~~

Điều kiện then chốt:

1. **@Transactional** phải được thực thi qua Spring proxy và chọn đúng transaction manager của database; nếu có nhiều manager, cần chỉ định rõ.
2. Dấu event và **UPDATE orders** phải thuộc **cùng transaction**. Nếu UPDATE lỗi, INSERT dấu event cũng rollback để lần nhận sau còn xử lý được.
3. **ON CONFLICT DO NOTHING** là cú pháp PostgreSQL. Database khác cần ràng buộc unique và cú pháp insert phù hợp.
4. Nếu có eventId khác nhau đại diện cùng một sự kiện nghiệp vụ, dedup theo eventId chưa đủ: phải thêm ràng buộc theo khóa nghiệp vụ và kiểm tra trạng thái chuyển đổi.
5. Payload phải được xác thực về nguồn, đơn hàng, phiên bản contract và các giá trị nghiệp vụ; không ghi trạng thái tùy ý từ một event không đáng tin cậy.

### 6.4. Chứng minh hành vi sau restart

Giả sử có các thời điểm:

~~~text
T0: Broker đã lưu OrderReady(E-101).
T1: Inbound adapter giao E-101 cho handler.
T2: Database bắt đầu transaction.
T3: INSERT processed_flow_events + UPDATE orders.
T4: Database commit thành công.
T5: Adapter xác nhận E-101 với broker.
~~~

**Crash trước T4:** transaction SQL chưa commit phải rollback; broker còn khả năng gửi lại E-101 nếu adapter chưa ACK. Handler chạy lại và cập nhật một lần.

**Crash từ T4 đến trước T5:** đơn hàng và dấu E-101 đã commit; broker có thể gửi lại. Lần nhận sau gặp khóa unique và bỏ qua phần cập nhật, sau đó ACK thành công.

**Crash sau T5:** nguồn coi E-101 đã xử lý; kết quả nghiệp vụ đã commit nên không cần replay.

Nếu không thể bảo đảm thứ tự **DB commit trước ACK**, cần thay đổi ranh giới xử lý hoặc dùng durable inbox thay vì coi đây là luồng an toàn.

### 6.5. Trường hợp dữ liệu được gom nhóm trước khi cập nhật

Nếu flow phải chờ ba thông điệp riêng cho cùng orderId, không thể chỉ lưu **processed_flow_events** cho output cuối và bỏ qua hai phần đã nhận. Trạng thái chờ của aggregator cũng là dữ liệu cần thiết:

~~~text
Order 42:
  inventory-confirmed  -> arrived
  fraud-reviewed       -> arrived
  payment-authorized   -> pending
  group-state          -> WAITING
~~~

Khi restart, một persistent **MessageGroupStore** cần còn nhóm chưa hoàn tất hoặc nguồn phải có khả năng phát lại chính xác các input. Khi đủ ba phần, phát output qua một ranh giới bền vững và cập nhật trạng thái nhóm theo thứ tự/transaction thích hợp. Nếu xóa group trước khi output được bền vững tiếp nhận, dữ liệu có thể mất; nếu output được tiếp nhận trước nhưng group chưa được đánh dấu hoàn tất, output có thể phát lại, nên consumer vẫn cần idempotency.

## 7. Quy trình stop, restart và resume có kiểm soát

### Trước khi dừng có kế hoạch

1. **Giảm nhận mới:** tạm ngừng inbound adapter/poller/consumer theo cơ chế quản lý lifecycle thực tế của từng nguồn. Không dừng database hay broker khi đang cần commit các giao dịch cuối.
2. **Drain công việc đang chạy:** theo dõi in-flight tasks, group đang chờ, queue depth, retry và outbox. Đặt giới hạn thời gian; nếu phải dừng cưỡng bức thì phải biết các nguồn nào sẽ replay.
3. **Chụp checkpoint và chỉ số:** ghi thời điểm, version ứng dụng, tổng event đã nhận, đã commit, còn trong queue, đang chờ aggregation và DLQ. Giữ correlation ID để đối soát.
4. **Kiểm tra store:** xác định database/message store/metadata store bền vững sẵn sàng và vẫn dùng cùng namespace/schema sau deploy.
5. **Đóng có thứ tự:** bảo đảm transaction được hoàn tất hoặc rollback; tránh đánh dấu đã xử lý trước khi kết quả commit.

### Khi khởi động lại

1. **Đảm bảo schema và contract tương thích:** payload, class, serialization, header, outbox và message store còn đọc được với phiên bản mới.
2. **Phục hồi tài nguyên:** kết nối database, broker, message store, lock registry; kiểm tra các lock/lease cũ được thu hồi đúng thời gian và không có hai worker cùng nhận ownership.
3. **Khôi phục stateful components:** xác nhận message group, queue bền vững, metadata/cursor, lịch công việc tới hạn và trạng thái lỗi chưa hoàn tất còn tồn tại.
4. **Bật xử lý với concurrency an toàn:** giới hạn tốc độ ban đầu nếu backlog lớn, tránh quá tải downstream và bùng nổ retry.
5. **Đối soát:** so sánh số lượng và danh sách event, kết quả nghiệp vụ, queue/outbox/DLQ; chỉ xem resume hoàn tất khi bất biến dữ liệu đạt.

**Lưu ý:** stop/start một endpoint Spring Integration có thể giữ trạng thái bean trong cùng JVM nhưng khác hoàn toàn với restart tiến trình hoặc triển khai container mới. Kiểm thử **kill process** là cách cần thiết để phát hiện state bị giữ riêng trong RAM mà bài test stop/start thông thường bỏ sót.

### Khi restart sau sự cố bất ngờ

Không tự động xóa queue, reset offset, dọn group, đổi ID hay gọi replay toàn bộ trước khi biết trạng thái nguồn. Trước hết phân loại:

- **Đã xử lý nhưng chưa ACK:** cho redelivery và dedup.
- **Đã ACK nhưng chưa xử lý:** nếu có, phải phục hồi từ inbox, log nguồn, DLQ hoặc bản ghi nghiệp vụ; đây là dấu hiệu sai thiết kế commit.
- **Message kẹt trong persistent store:** xác minh trạng thái lock, poison message, timeout và worker ownership rồi mới cho tiếp tục.
- **Group chưa hoàn tất:** giữ group hoặc xác định có thể phát lại input; đừng ép release nhóm thiếu thành phần nếu nghiệp vụ không chấp nhận.
- **Outbox chưa publish:** tiếp tục relay; coi duplicate là trường hợp bình thường.

## 8. Kiểm chứng “không mất” bằng đối soát dữ liệu

### 8.1. Đếm đúng đại lượng

Chỉ nhìn **số message đầu vào** và **số lần handler được gọi** thường sai do retry và duplicate. Cần phân biệt:

- **accepted_unique**: số eventId duy nhất đã được nguồn hoặc inbox tiếp nhận bền vững trong một phạm vi kiểm thử xác định.
- **processed_unique**: số eventId duy nhất có kết quả nghiệp vụ hợp lệ, được commit.
- **pending_unique**: số eventId có thể tiếp tục xử lý từ broker, inbox, durable queue hoặc group state.
- **quarantined_unique**: số eventId ở DLQ/bảng lỗi còn đủ dữ liệu để điều tra và phục hồi.

Một bất biến cần kiểm tra theo **tập ID** là:

~~~text
Accepted IDs
    = Processed IDs ∪ Pending IDs ∪ Quarantined IDs

Và không có Accepted ID nào nằm ngoài hợp của ba tập.
~~~

Một event có thể tạm xuất hiện trong cả nguồn và bảng processed nếu ACK chưa commit. Vì vậy **không cộng số đếm thô** khi các tập chồng nhau; cần so sánh khóa eventId và trạng thái với quy tắc ưu tiên/chuẩn hóa. Các nguồn tham gia đối soát phải được chụp tại cùng watermark hoặc trong khoảng đã ngừng ghi, nếu không số lượng sẽ thay đổi liên tục.

Với sự kiện bị xử lý lặp, bất biến bổ sung là:

~~~text
Mỗi eventId hợp lệ -> tối đa 1 tác động nghiệp vụ được commit.
Mỗi eventId đã chấp nhận -> có thể xác định kết cục hoặc chỗ chờ phục hồi.
~~~

Nếu có quan hệ nhiều event → một đơn hàng, phải bổ sung **khóa nghiệp vụ**, version và quy tắc chuyển trạng thái; một eventId duy nhất không luôn tương đương một lần thay đổi đơn hàng.

### 8.2. Truy vấn minh họa trên database

Thống kê số event đã ghi dấu theo flow:

~~~sql
SELECT flow_name, COUNT(*) AS processed_unique
FROM processed_flow_events
GROUP BY flow_name
ORDER BY flow_name;
~~~

Nếu hệ thống có **inbox_events(event_id, status, accepted_at)**, có thể tìm event đã tiếp nhận nhưng chưa có dấu xử lý:

~~~sql
SELECT i.event_id, i.status, i.accepted_at
FROM inbox_events i
LEFT JOIN processed_flow_events p
  ON p.event_id = i.event_id
 AND p.flow_name = 'order-ready-flow'
WHERE p.event_id IS NULL;
~~~

Các hàng trả về **không mặc nhiên là mất dữ liệu**: chúng có thể đang PENDING, RETRY hoặc FAILED và cần được kiểm tra ở queue/DLQ. Nếu nguồn được quản lý bởi broker ngoài database, hãy xuất tập ID từ broker/log hoặc lưu một ledger tiếp nhận; không thể dùng riêng bảng **processed_flow_events** để chứng minh không có message nào mất từ trước khi được ghi dấu.

Đối với aggregator, cũng cần đối soát **groupId**, số thành phần mong đợi, số đã có, timeout, trạng thái release và output eventId. Với file adapter, kiểm tra danh sách file ở incoming/processing/completed/failed đối chiếu metadata và kết quả ghi database.

## 9. Kiểm thử chịu lỗi: dừng ở đúng điểm nguy hiểm

Để kiểm chứng khả năng phục hồi, sử dụng môi trường có **database và broker thật hoặc tương đương production**, nguồn dữ liệu xác định và cơ chế chụp eventId trước khi chạy. Mô phỏng sự cố bằng cách dừng cưỡng bức tiến trình/pod tại các điểm có chủ đích, sau đó khởi động lại và đối soát toàn bộ.

| Điểm fault injection | Kết quả cần chứng minh |
| --- | --- |
| Trước khi adapter gửi message vào channel | Nguồn vẫn giữ event hoặc có thể phát lại; không mất event đã accepted. |
| Sau khi nhận vào queue nội bộ, trước khi handler lấy ra | Với RAM queue sẽ lộ nguy cơ mất; với durable store đúng cấu hình, event vẫn tồn tại. |
| Sau khi lấy message từ persistent queue, trước business commit | Message quay về trạng thái có thể xử lý hoặc có cơ chế replay; không biến mất do xóa khỏi store quá sớm. |
| Giữa transaction database | Thay đổi nghiệp vụ và dấu idempotency rollback cùng nhau; retry có thể áp dụng đúng. |
| Sau DB commit, trước ACK nguồn | Có thể giao lại; không phát sinh tác động nghiệp vụ thứ hai. |
| Sau khi 2/3 phần aggregation đã tới | Phần còn thiếu có thể tới sau restart và nhóm vẫn hoàn tất đúng một cách có thể đối soát. |
| Sau khi group release, trước khi output được bền vững nhận | Không mất output; hoặc có thể replay và dedup; không bị “group đã xóa nhưng output mất”. |
| Sau khi file/checkpoint được ghi, trước business commit | File/event không bị bỏ qua vĩnh viễn; có cơ chế xác định và làm lại. |
| Sau khi outbox gửi thành công, trước đánh dấu published | Relay có thể gửi lại nhưng downstream không thực hiện tác dụng phụ lần hai. |
| Khi broker/database mất kết nối, deploy nhiều instance cùng lúc | Có retry/backoff và lock/lease phù hợp; không xóa nhầm tiến độ hoặc xử lý tranh chấp. |
| Khi payload persisted đã được tạo bởi phiên bản trước | Phiên bản mới đọc/di trú được dữ liệu hoặc có kế hoạch tương thích đã kiểm thử. |

### Quy trình kiểm thử mẫu

1. Sinh tập đầu vào hữu hạn với **eventId** cố định, thêm một số duplicate có chủ đích và lưu danh sách kỳ vọng.
2. Bật flow, dừng đột ngột tại một checkpoint kiểm thử hoặc thời điểm đã xác nhận bằng log/metrics.
3. Khởi động lại cùng database/store/broker, cho flow chạy đến khi ổn định và backlog được xử lý hoặc cách ly lỗi.
4. So sánh **tập eventId**, bất biến nghiệp vụ và tác dụng phụ downstream; phân biệt duplicate delivery với duplicate business effect.
5. Lặp với nhiều instance, redelivery, payload lỗi, timeout, thay đổi schema và nâng cấp phiên bản ứng dụng.

Không chỉ thử **graceful shutdown**: lúc shutdown nhẹ nhàng framework có thời gian hoàn tất task trong RAM, che giấu vấn đề mà crash thực tế gây ra.

## 10. Quan sát flow trước và sau restart

Để phát hiện “mất âm thầm”, nên đưa các trường sau vào log/trace/metric một cách nhất quán:

| Nhóm tín hiệu | Ví dụ cần quan sát |
| --- | --- |
| **Định danh xuyên suốt** | eventId, correlationId, business key, source partition/file, flow version, traceId. |
| **Nguồn đầu vào** | Offset/checkpoint, số message ready/unacked, tuổi message cũ nhất, ingest rate, redelivery count. |
| **Queue/persistent store** | Độ sâu queue, số message chưa xử lý, độ tuổi backlog, lỗi serialization, store access failure. |
| **Aggregator/resequencer** | Số group mở, group quá hạn, nhóm thiếu thành phần, số lần release/expire, duplicate sequence. |
| **Xử lý nghiệp vụ** | Số eventId đã commit, số duplicate bị bỏ qua, rollback, lock timeout, conflict unique, lỗi quy tắc nghiệp vụ. |
| **Outbound** | Outbox pending/failed, tuổi event chưa phát, retry count, DLQ và latency của downstream. |
| **Khởi động lại** | Thời điểm ngừng/khởi động, số event trước/sau restart, thời gian bắt kịp backlog, khoảng mất kết nối. |

Không nên dùng **HTTP health check trả 200** làm bằng chứng duy nhất cho flow đã phục hồi. Readiness có thể kiểm tra kết nối/phụ thuộc thiết yếu, nhưng tính đầy đủ cần **reconciliation** dựa trên sự kiện và trạng thái nghiệp vụ.

Đặt cảnh báo khi **pending age tăng liên tục**, **group không hoàn tất quá SLA**, **DLQ tăng**, **outbox backlog không giảm**, **consumer lag kéo dài** hoặc chênh lệch ID accepted/processed/pending xuất hiện. Log không nên đưa payload có dữ liệu nhạy cảm; eventId và correlationId thường đủ để tra cứu có kiểm soát.

## 11. Các sai lầm thường gặp

**“QueueChannel nghĩa là message luôn được giữ sau restart.”** Không. QueueChannel dùng bộ nhớ là queue tạm thời; chỉ các cấu hình có store bền vững cùng xử lý transaction phù hợp mới có thể phục hồi message đã lưu.

**“Có JdbcMessageStore là toàn bộ flow đã an toàn.”** Không. Nếu message bị xóa khỏi store trước khi downstream commit, hoặc nhóm aggregator bị dọn trước khi output được chấp nhận bền vững, vẫn có cửa sổ mất công việc.

**“Lưu offset/checkpoint ngay khi đọc xong giúp tránh duplicate.”** Có thể tránh đọc lặp nhưng tạo nguy cơ bỏ qua công việc chưa commit. An toàn thường ưu tiên cho replay và dedup hơn là checkpoint tiến quá sớm.

**“Đổi async channel chỉ ảnh hưởng hiệu năng.”** Bất đồng bộ làm thay đổi thread, transaction boundary và trạng thái in-flight. Phải kiểm tra nguồn replay hoặc durable handoff.

**“Retry trong RAM đủ cho mọi sự cố.”** Crash có thể xóa retry state. Nếu cần hồi phục sau restart, phải còn message ở nguồn, trong DLQ hoặc persistent work queue.

**“Message ID của framework là khóa chống trùng bền vững.”** ID có thể thay đổi khi tái tạo message. Dùng khóa nghiệp vụ ổn định và unique constraint bền vững.

**“Một đơn hàng đã READY nghĩa là không hề mất event.”** Có thể một số event khác đã biến mất; cần đối soát **tập eventId đã accepted**, không chỉ trạng thái cuối của một vài đơn hàng.

**“Stop/start flow trong cùng JVM là đủ để kiểm chứng crash recovery.”** Không. Nó thường giữ nhiều bean và dữ liệu RAM sống qua stop/start; phải thử cả restart JVM/pod và mất kết nối tại điểm commit.

## 12. Runbook khôi phục và checklist bàn giao

### Runbook khi flow phải khởi động lại

1. **Khoanh vùng:** xác định flow ID, instance, source adapter, thời điểm lỗi, phiên bản schema/contract và các thành phần liên quan.
2. **Bảo toàn trạng thái:** ghi lại queue depth, group count, source checkpoint, inbox/outbox/DLQ, transaction đang dở dang và log lỗi. Không reset offset hay dọn metadata trước khi kiểm tra.
3. **Xác định điểm đã commit:** sự kiện nào đã ACK, thay đổi nghiệp vụ nào đã commit, output nào đã được downstream nhận; đối chiếu theo khóa nghiệp vụ.
4. **Chọn cách phục hồi:** redelivery từ broker, replay từ inbox/log, resume persistent queue/group, retry outbox hoặc bù trừ tác dụng phụ bên ngoài.
5. **Khởi động có giới hạn:** dùng concurrency và backoff phù hợp, giám sát lock/lease, backlog, tỉ lệ duplicate và các lỗi lặp.
6. **Đối soát hoàn tất:** kiểm chứng eventId accepted thuộc processed/pending/quarantine, không có tác động nghiệp vụ trùng, không còn group/outbox tồn đọng trái SLA.
7. **Ghi nhận:** lưu nguyên nhân, failure window, cách khôi phục và thay đổi thiết kế cần bổ sung cho lần sau.

### Checklist trước khi đưa flow vào production

- [ ] Đã liệt kê trạng thái nghiệp vụ và trạng thái kỹ thuật cần giữ qua restart.
- [ ] Có nguồn đầu vào hoặc inbox bền vững cho mọi message đã chấp nhận; ACK không vượt trước khi công việc được giữ bền.
- [ ] Queue/channel, aggregator và metadata store cần bền vững đã được cấu hình đúng, có schema/namespace/lock tương thích nhiều instance.
- [ ] Idempotency key ổn định; dấu đã xử lý và hiệu ứng database nằm trong cùng transaction khi có thể.
- [ ] Có phương án outbox hoặc phục hồi outbound khi tác vụ cần phát sự kiện sau database commit.
- [ ] Retry, timeout, DLQ và quy trình replay không xóa mất dữ liệu lỗi hoặc tạo vòng lặp vô hạn.
- [ ] Có kế hoạch tương thích hoặc di trú đối với payload/header/state đã lưu từ phiên bản trước.
- [ ] Đã fault-inject crash trước/sau commit, ACK, checkpoint, group release và outbound publish.
- [ ] Có đối soát theo tập eventId và khóa nghiệp vụ; đo được backlog, tuổi công việc, duplicate và event lỗi.
- [ ] Runbook nêu rõ ai được reset checkpoint, mở lại flow, xử lý DLQ và xác nhận khôi phục hoàn tất.

## 13. Kết luận

**Khởi động lại flow an toàn là bài toán khôi phục công việc nghiệp vụ và chứng minh kết quả, không chỉ khởi động lại bean của Spring Integration.** Để tránh mất trạng thái cần thiết, cần nhận diện nơi message hoặc tiến độ đang nằm, chọn kho bền vững cho trạng thái không thể tái dựng, đặt ACK/checkpoint theo đúng ranh giới commit và chấp nhận redelivery kèm idempotency. Sau restart, tính đúng đắn phải được kiểm chứng bằng **đối soát eventId, trạng thái nghiệp vụ và các tác dụng phụ**, cùng những bài thử dừng đột ngột tại từng điểm lỗi có thể xảy ra.

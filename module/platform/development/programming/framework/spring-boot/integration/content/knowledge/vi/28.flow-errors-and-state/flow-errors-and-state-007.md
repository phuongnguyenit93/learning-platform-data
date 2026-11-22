# MetadataStore, IdempotentReceiverInterceptor và đánh dấu hoặc loại thông điệp trùng

## 1. Bối cảnh và mục tiêu

Trong module **SPRING_BOOT_INTEGRATION**, các luồng tích hợp Spring Boot trao đổi dữ liệu với HTTP client, cơ sở dữ liệu, cache, message broker và những adapter của Spring Integration. Một bài toán lặp đi lặp lại là **cùng một sự kiện hoặc yêu cầu có thể đến nhiều lần**: broker giao lại khi consumer chưa ACK, bộ nhận file quét lại dữ liệu sau restart, HTTP caller retry vì chưa nhận response, hoặc ứng dụng khôi phục từ checkpoint cũ.

Chương **Lỗi và trạng thái flow** xem xét cách nhận diện và duy trì trạng thái để một bản tin trùng không vô tình gây ra tác động nghiệp vụ lần thứ hai. Spring Integration cung cấp hai cơ chế quan trọng:

- **MetadataStore / ConcurrentMetadataStore**: nơi lưu cặp khóa–giá trị mô tả trạng thái đã gặp hoặc đã xử lý.
- **IdempotentReceiverInterceptor**: advice gắn vào một **MessageHandler** để quyết định thông điệp nào là mới, thông điệp nào trùng; sau đó **đánh dấu**, **chuyển sang kênh loại**, hoặc **từ chối bằng exception** tùy cấu hình.

Đây là công cụ thực hiện mẫu thiết kế **Idempotent Receiver** (bộ nhận có tính lũy đẳng), nhưng bản thân việc bật interceptor **không bảo đảm exactly-once** cho cả hệ thống. Phần đảm bảo thực sự phụ thuộc vào khóa nghiệp vụ, thời điểm ghi trạng thái, transaction, xử lý lỗi và tác động bên ngoài.

Sau bài học, bạn cần:

1. Phân biệt định danh message kỹ thuật và định danh sự kiện/nghiệp vụ.
2. Hiểu hợp đồng của MetadataStore, ConcurrentMetadataStore và MetadataStoreSelector.
3. Gắn IdempotentReceiverInterceptor vào một endpoint bằng Java DSL hoặc annotation.
4. Chọn **đánh dấu trùng** bằng header hay **loại trùng** bằng discard channel cho từng tình huống.
5. Thiết kế xử lý thất bại, trạng thái sau restart, nhiều instance và event đến đảo thứ tự.
6. Kiểm thử và quan sát một flow chống xử lý trùng trong điều kiện redelivery thực tế.

## 2. Vì sao thông điệp bị giao lại?

Giả sử consumer nhận sự kiện **OrderPaid** từ broker:

~~~json
{
  "eventId": "evt-7821",
  "orderId": "ord-204",
  "paymentVersion": 7,
  "paidAt": "2026-11-21T03:20:00Z"
}
~~~

Consumer ghi trạng thái đơn đã thanh toán vào database, rồi ACK thông điệp. Nếu tiến trình chết **sau khi database commit nhưng trước khi ACK**, broker có thể giao lại event **evt-7821**. Nếu handler không chống trùng, nó có thể cộng doanh thu lần thứ hai, phát thêm thông báo, hoặc ghi thêm một dòng ledger.

~~~mermaid
sequenceDiagram
    participant B as Message broker
    participant F as Spring Integration flow
    participant D as Database
    B->>F: OrderPaid evt-7821
    F->>D: Commit trạng thái thanh toán
    D-->>F: Thành công
    Note over F: Crash trước ACK
    B->>F: Redelivery evt-7821
    F->>F: Kiểm tra khóa chống trùng
    alt Khóa đã được ghi nhận
        F-->>B: Bỏ qua tác động lặp, ACK theo chính sách
    else Chưa có khóa
        F->>D: Xử lý với bảo vệ nghiệp vụ
        F-->>B: ACK khi hoàn thành
    end
~~~

Nguồn phát sinh trùng thường gặp:

| Nguồn | Vì sao có thể trùng | Ý nghĩa của khóa chống trùng |
| --- | --- | --- |
| Broker giao theo **at-least-once** | Mất ACK, retry hoặc rebalance | Event ID ổn định qua các lần giao lại |
| HTTP client retry | Timeout sau khi server đã xử lý | Idempotency key do caller gửi hoặc business request ID |
| File/SFTP polling | Quét lại sau restart, đọc lại file/record | Đường dẫn + fingerprint, nguồn + offset/record ID |
| CDC/outbox | Phát lại do replay, checkpoint | Event ID hoặc cặp nguồn–vị trí |
| Retry nội bộ | Flow thử lại sau lỗi xử lý | Key của cùng một thao tác nghiệp vụ |

**Không dùng mặc định header message.id để chống trùng** nếu nó được sinh mới khi chuyển message, deserialize, gateway hoặc redelivery. ID được broker/sender cung cấp phải được kiểm chứng có ổn định qua retry và có phạm vi duy nhất như nghiệp vụ yêu cầu.

## 3. MetadataStore lưu gì?

### 3.1. MetadataStore so với ConcurrentMetadataStore

**org.springframework.integration.metadata.MetadataStore** có hợp đồng key–value đơn giản:

~~~java
public interface MetadataStore {
    void put(String key, String value);
    String get(String key);
    String remove(String key);
}
~~~

**ConcurrentMetadataStore** mở rộng bằng những phép thao tác nguyên tử:

~~~java
public interface ConcurrentMetadataStore extends MetadataStore {
    String putIfAbsent(String key, String value);
    boolean replace(String key, String oldValue, String newValue);
}
~~~

Chữ ký rút gọn để giải thích. **putIfAbsent** trả về **null** khi khóa chưa có và giá trị mới được đặt thành công; nếu khóa đã tồn tại, nó trả giá trị cũ. **replace** thay giá trị chỉ khi giá trị hiện tại khớp giá trị dự kiến.

Vì vậy, kiểm tra–ghi bằng hai lệnh riêng biệt là không an toàn dưới cạnh tranh:

~~~java
// KHÔNG dùng để đảm bảo chỉ một consumer nhận một key:
if (store.get(key) == null) {
    store.put(key, "seen");
    process(message);
}
~~~

Hai worker có thể cùng thấy **null** rồi đều xử lý. Đối với cổng chống trùng, dùng **ConcurrentMetadataStore** có phép **putIfAbsent** nguyên tử:

~~~java
boolean firstArrival = store.putIfAbsent(key, "seen") == null;
if (firstArrival) {
    process(message);
}
~~~

Ví dụ trên chỉ nói về thao tác **giành quyền xử lý key**; nó chưa giải quyết trường hợp **process() thất bại sau khi đã ghi key**. Vấn đề đó được phân tích ở phần sau.

### 3.2. Chọn backend phù hợp

| Store | Trạng thái tồn tại qua restart? | Phạm vi phối hợp | Khi nào dùng |
| --- | --- | --- | --- |
| **SimpleMetadataStore** | Không | Trong một application context/JVM | Demo, test, xử lý chỉ cần dedupe ngắn hạn ở một instance |
| **PropertiesPersistingMetadataStore** | Có khi được flush/lưu đúng cách | Thích hợp hơn với trạng thái local, không mặc định là kho chia sẻ cluster | Tiến trình đơn, trạng thái nhỏ, hiểu rõ cơ chế persist |
| **JdbcMetadataStore** | Có | Nhiều instance nếu dùng chung DB và transaction được cấu hình đúng | Muốn metadata bền vững và có thể tham gia transaction JDBC |
| **RedisMetadataStore** | Phụ thuộc cấu hình Redis/persistence | Nhiều instance dùng chung Redis, trong giới hạn atomicity của triển khai/topology | Cổng dedupe tốc độ cao, cần đánh giá vận hành/TTL |
| **MongoDbMetadataStore**, **ZookeeperMetadataStore**, các biến thể khác | Theo backend | Theo backend và cơ chế nguyên tử tương ứng | Đã dùng hạ tầng đó cho việc chia sẻ state |

Khi không tham chiếu rõ một store, một số thành phần Spring Integration có cơ chế tìm bean tên **metadataStore**, rồi fallback sang **SimpleMetadataStore**. Nhưng để dễ kiểm soát phạm vi và tránh vô tình dùng store in-memory, nên **inject một ConcurrentMetadataStore được đặt tên rõ** vào selector của flow.

**Không nhầm MetadataStore với MessageStore.** MetadataStore lưu cặp string key/value phục vụ trạng thái nhận diện; MessageStore lưu thông điệp hoặc nhóm thông điệp cho các mẫu như aggregator hay persistent channel. Một bản ghi metadata **không chứa đủ nội dung message để replay lại toàn bộ nghiệp vụ**.

## 4. MetadataStoreSelector quyết định trùng như thế nào?

**org.springframework.integration.selector.MetadataStoreSelector** là một **MessageSelector** dùng **MessageProcessor** để tính khóa từ Message và **ConcurrentMetadataStore** để kiểm tra/đặt trạng thái.

Luồng mặc định khi **không** có chính sách so sánh giá trị:

~~~mermaid
flowchart TD
    A["Message vào handler"] --> B["Tính idempotent key"]
    B --> C["ConcurrentMetadataStore.putIfAbsent(key, value)"]
    C --> D{"Kết quả trả về"}
    D -->|"null: chưa tồn tại"| E["accept = true"]
    D -->|"Giá trị cũ: đã tồn tại"| F["accept = false"]
    E --> G["Handler được xử lý theo advice"]
    F --> H["Interceptor đánh dấu hoặc loại"]
~~~

Nếu không chỉ định **valueStrategy**, selector lấy giá trị từ **timestamp** header của message (biểu diễn theo cách nội bộ của selector). Với **khóa chống trùng dựa trên eventId**, giá trị lưu bên cạnh key thường không cần dùng để ra quyết định; nhưng bạn vẫn phải xác định vòng đời, kích thước và chính sách xóa metadata.

Ví dụ selector cho sự kiện thanh toán:

~~~java
@Bean
MetadataStoreSelector paidEventSelector(
        @Qualifier("paymentIdempotencyStore") ConcurrentMetadataStore store) {

    return new MetadataStoreSelector(message -> {
        OrderPaid event = (OrderPaid) message.getPayload();
        return "order-paid:consumer-v1:" + event.eventId();
    }, store);
}
~~~

Ở đây **OrderPaid** là DTO của ứng dụng có phương thức **eventId()**, ví dụ Java record:

~~~java
public record OrderPaid(
        String eventId,
        String orderId,
        long paymentVersion,
        Instant paidAt) {
}
~~~

Trong production phải kiểm tra **eventId không null/rỗng**, có định dạng hợp lệ và ổn định giữa các lần retry. Prefix **order-paid:consumer-v1** là namespace xác định **mục đích xử lý**, tránh một consumer khác vô tình dùng cùng key khiến bản tin hợp lệ bị loại.

### Chọn khóa theo nghĩa nghiệp vụ

| Mục tiêu | Key đề xuất | Tránh |
| --- | --- | --- |
| Một sự kiện thanh toán chỉ cập nhật ledger một lần | consumer + eventId | Chỉ dùng orderId nếu đơn có thể có nhiều payment event |
| Một lệnh HTTP có idempotency key | operation + tenant + clientRequestId | Hash payload duy nhất nếu các yêu cầu giống nội dung vẫn có thể là hai lệnh hợp lệ |
| Đồng bộ theo version mới nhất | source + aggregateId, value = version | Lưu key bằng eventId nếu mục tiêu là từ chối bản cập nhật cũ |
| Dòng file phân tách | source/file identity + line offset hoặc record ID | Dùng riêng tên file nếu file có thể được ghi lại |
| Chống phát email cho một business action | loại email + tenant + actionId | Chỉ dùng recipient, vì một người có thể nhận nhiều email hợp lệ |

Khóa cần có **phạm vi**, **tính ổn định** và **chính sách hết hạn** phù hợp. Dữ liệu định danh nhạy cảm không nên được đưa trực tiếp vào key/log nếu có thể dùng mã băm hoặc định danh vô danh hóa.

## 5. IdempotentReceiverInterceptor: mặc định đánh dấu, chưa tự loại

**IdempotentReceiverInterceptor** là một **advice** áp dụng cho **MessageHandler.handleMessage(Message<?>)**, không phải endpoint độc lập và không tự bắt toàn bộ các phương thức Java trong ứng dụng.

Khi selector trả **false** vì key đã tồn tại:

1. **Mặc định**, interceptor tạo message với header **duplicateMessage = true** rồi vẫn để handler xử lý.
2. Khi cấu hình **discardChannel**, interceptor chuyển message không được chấp nhận sang kênh đó và **không gọi target handler**.
3. Khi **throwExceptionOnRejection = true**, interceptor **không gọi target handler** và ném **MessageRejectedException**. Nếu đồng thời có discard channel, nó gửi tới kênh discard rồi vẫn có thể ném exception.

Phân biệt:

| Cấu hình | Handler nghiệp vụ có nhận duplicate? | Kết quả đối với duplicate |
| --- | --- | --- |
| Chỉ selector, mặc định | **Có** | Message được đánh dấu header **duplicateMessage=true** |
| Có discardChannel | **Không** | Message gửi tới discard channel |
| Discard vào nullChannel | **Không** | Message bị nuốt có chủ đích |
| throwExceptionOnRejection=true | **Không** | Ném MessageRejectedException |
| Có cả discardChannel và throwExceptionOnRejection=true | **Không** | Gửi discard rồi ném exception theo cấu hình |

**Lỗi cấu hình nguy hiểm:** đặt interceptor và tưởng nó tự loại trùng, trong khi mặc định handler vẫn được gọi. Nếu handler bỏ qua header, side effect vẫn có thể chạy lần nữa.

## 6. Ví dụ 1 — Đánh dấu trùng để handler tự quyết định

Mục tiêu: một flow nhận sự kiện thanh toán; handler có thể ghi audit/metric cho redelivery và quyết định kết quả phù hợp. Minh họa này dùng **SimpleMetadataStore** để dễ chạy trên một instance; production nên thay bằng shared persistent store.

### 6.1. Bean cấu hình

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.handler.advice.IdempotentReceiverInterceptor;
import org.springframework.integration.metadata.ConcurrentMetadataStore;
import org.springframework.integration.metadata.SimpleMetadataStore;
import org.springframework.integration.selector.MetadataStoreSelector;
import org.springframework.beans.factory.annotation.Qualifier;

@Configuration
public class PaidEventFlowConfiguration {

    @Bean("paymentIdempotencyStore")
    ConcurrentMetadataStore paymentIdempotencyStore() {
        return new SimpleMetadataStore();
    }

    @Bean
    IdempotentReceiverInterceptor markPaidDuplicates(
            @Qualifier("paymentIdempotencyStore") ConcurrentMetadataStore store) {

        MetadataStoreSelector selector = new MetadataStoreSelector(
                message -> "paid:v1:"
                        + ((OrderPaid) message.getPayload()).eventId(),
                store);

        // Không set discardChannel hoặc throwExceptionOnRejection:
        // thông điệp trùng vẫn đi vào handler, có header duplicateMessage.
        return new IdempotentReceiverInterceptor(selector);
    }

    @Bean
    IntegrationFlow paidEventFlow(
            IdempotentReceiverInterceptor markPaidDuplicates) {

        return IntegrationFlow.from("paidEventsInput")
                .handle("paidEventHandler", "handle",
                        e -> e.advice(markPaidDuplicates))
                .get();
    }
}
~~~

**Import còn thiếu:** các lớp domain và một số annotation thông thường nằm trong ứng dụng; cần có **spring-boot-starter-integration** hoặc các module Spring Integration tương ứng theo phiên bản Boot. **IntegrationFlow.from("paidEventsInput")** dùng một input channel tên **paidEventsInput**; adapter broker hoặc gateway gửi message vào channel này. Ví dụ giả định DTO **OrderPaid** đã được chuyển đổi từ JSON trước khi tới handler.

### 6.2. Handler có nhánh xử lý duplicate

~~~java
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;

@Component("paidEventHandler")
public class PaidEventHandler {
    private final PaidOrderService paidOrderService;

    public PaidEventHandler(PaidOrderService paidOrderService) {
        this.paidOrderService = paidOrderService;
    }

    public void handle(Message<?> message) {
        boolean duplicate = Boolean.TRUE.equals(
                message.getHeaders().get(
                        IntegrationMessageHeaderAccessor.DUPLICATE_MESSAGE));

        if (duplicate) {
            // Ghi metric/audit theo chính sách, không chạy side effect lần nữa.
            return;
        }

        paidOrderService.applyPayment((OrderPaid) message.getPayload());
    }
}
~~~

Với mode này, thông điệp trùng **đến được handler** để ứng dụng quyết định phản hồi hoặc ghi dấu cho upstream. Tuy nhiên, vì key thường được ghi vào store **trước khi applyPayment hoàn thành**, việc kiểm tra duplicate đơn thuần chưa đủ an toàn khi downstream thất bại. Phần 10 giải thích cách tránh chặn vĩnh viễn bản tin hợp lệ sau lỗi.

## 7. Ví dụ 2 — Loại message trùng tại ranh giới handler

Nếu sự kiện trùng có thể được ACK như đã xử lý thành công và **không cần business handler xem lại**, cấu hình discard channel rõ ràng:

~~~java
@Bean
IdempotentReceiverInterceptor dropPaidDuplicates(
        @Qualifier("paymentIdempotencyStore") ConcurrentMetadataStore store) {

    MetadataStoreSelector selector = new MetadataStoreSelector(
            m -> "paid:v1:" + ((OrderPaid) m.getPayload()).eventId(),
            store);

    IdempotentReceiverInterceptor advice =
            new IdempotentReceiverInterceptor(selector);
    advice.setDiscardChannelName("nullChannel");
    return advice;
}

@Bean
IntegrationFlow dropDuplicateFlow(
        @Qualifier("dropPaidDuplicates")
        IdempotentReceiverInterceptor advice) {

    return IntegrationFlow.from("paidEventsInputForDiscard")
            .handle("paidEventHandler", "handle", e -> e.advice(advice))
            .get();
}
~~~

Đây là **phương án thay thế** mode đánh dấu ở phần 6, không phải hai flow nên cùng dùng một channel và một store trong production. Nếu copy cả hai ví dụ vào một ứng dụng, cần quyết định một chiến lược, tên bean/channel và namespace state rõ ràng.

**nullChannel** là channel có sẵn của Spring Integration để tiêu thụ message mà không xử lý tiếp. Không nhầm với **không cấu hình discardChannel**: nếu không cấu hình thì interceptor mặc định **đánh dấu** trùng và **cho handler chạy**.

Khi muốn quan sát thông điệp trùng, có thể cung cấp channel audit thay cho nullChannel:

~~~java
@Bean
MessageChannel duplicateAuditChannel() {
    return new DirectChannel();
}

@Bean
IntegrationFlow duplicateAuditFlow() {
    return IntegrationFlow.from("duplicateAuditChannel")
            .handle(message -> {
                // Ghi metric; không chứa credential/payload nhạy cảm.
                // Tránh để audit throw làm gián đoạn ACK nếu không mong muốn.
            })
            .get();
}
~~~

Và dùng **advice.setDiscardChannelName("duplicateAuditChannel")**. Đoạn này chỉ minh họa wiring; nếu audit cần bền vững, hãy dùng một store/queue phù hợp thay vì tin rằng một DirectChannel đồng bộ đã lưu lịch sử.

### Khi nào cần ném lỗi khi gặp duplicate?

~~~java
advice.setThrowExceptionOnRejection(true);
~~~

Khi bật cờ này, **MessageRejectedException** báo rằng selector từ chối message. Đây thường **không phải** cách tốt nhất cho duplicate được kỳ vọng trong consumer at-least-once: adapter có thể coi exception là thất bại rồi **redeliver liên tục cùng bản tin**. Chỉ bật khi hệ thống thực sự muốn chuyển duplicate sang nhánh xử lý lỗi, dead-letter hoặc trả lỗi có chủ đích và chính sách ACK/retry đã rõ.

## 8. Dùng annotation trên endpoint

Ngoài Java DSL advice chain, Spring Integration hỗ trợ **@IdempotentReceiver** để gắn interceptor theo tên vào endpoint được khai báo bằng messaging annotation:

~~~java
@Bean
IdempotentReceiverInterceptor paidAdvice(
        @Qualifier("paymentIdempotencyStore") ConcurrentMetadataStore store) {
    return new IdempotentReceiverInterceptor(
            new MetadataStoreSelector(
                    m -> "paid:v1:"
                            + ((OrderPaid) m.getPayload()).eventId(),
                    store));
}

@Bean
@ServiceActivator(inputChannel = "paidEventsInput")
@IdempotentReceiver("paidAdvice")
MessageHandler paidMessageHandler(PaidEventHandler processor) {
    return processor::handle;
}
~~~

Ví dụ trên giả định **PaidEventHandler.handle(Message<?>)** đã được khai báo. Dùng tham số Message<?> để method reference khớp giao diện MessageHandler; phần thân handler kiểm tra và ép kiểu payload sang OrderPaid sau khi adapter đã chuyển đổi/validate. Chọn **một** cách cấu hình endpoint: **DSL e.advice(...)** hoặc **@IdempotentReceiver** gắn trên endpoint; không nên vô tình áp dụng cùng selector hai lần cho cùng một message, vì lần kiểm tra thứ hai sẽ nhìn thấy key đã tồn tại và tự coi bản tin đầu tiên là duplicate.

Trong ứng dụng dùng Java config, kiểm tra import annotation tương ứng của Spring Integration và phiên bản framework. Interceptor là advice cho **MessageHandler**; đặt nó vào một bean Java bất kỳ không đủ để tạo cơ chế chống trùng nếu handler không được kết nối qua endpoint.

## 9. Chọn MetadataStore bền vững trong production

**SimpleMetadataStore** chỉ giữ state trong bộ nhớ tiến trình. Khi restart, key cũ mất và cùng event có thể được chấp nhận như lần đầu. Với nhiều replica chạy song song, mỗi replica có store riêng nên cả hai có thể cùng chấp nhận một event.

Nếu cần chia sẻ trạng thái và chịu được restart, nên cân nhắc **JdbcMetadataStore** hoặc store phân tán khác có các thao tác nguyên tử thích hợp.

### 9.1. JdbcMetadataStore

Để dùng JDBC, cần Spring Integration JDBC module (ví dụ **org.springframework.integration:spring-integration-jdbc**), **DataSource**, transaction manager tương ứng và bảng metadata. Ví dụ:

~~~java
import javax.sql.DataSource;
import org.springframework.context.annotation.Bean;
import org.springframework.integration.jdbc.metadata.JdbcMetadataStore;
import org.springframework.integration.metadata.ConcurrentMetadataStore;

@Bean("paymentIdempotencyStore")
ConcurrentMetadataStore paymentIdempotencyStore(DataSource dataSource) {
    JdbcMetadataStore store = new JdbcMetadataStore(dataSource);
    store.setRegion("paid-events-v1");
    return store;
}
~~~

**setRegion** tách không gian key để các flow/consumer không dùng lẫn trạng thái. Với cùng bảng metadata, khóa thực tế được phân biệt bởi cặp **(METADATA_KEY, REGION)**. Không nên thay region mỗi lần deploy nếu vẫn muốn chống trùng xuyên các lần triển khai.

Ví dụ DDL dạng PostgreSQL (bạn cần chọn script đúng database):

~~~sql
CREATE TABLE INT_METADATA_STORE (
    METADATA_KEY VARCHAR(255) NOT NULL,
    METADATA_VALUE VARCHAR(4000) NOT NULL,
    REGION VARCHAR(100) NOT NULL,
    CONSTRAINT INT_METADATA_STORE_PK
        PRIMARY KEY (METADATA_KEY, REGION)
);
~~~

Schema mẫu của Spring Integration cho từng RDBMS nằm trong module JDBC. Áp dụng qua Flyway/Liquibase hoặc quy trình migration phù hợp; **không giả định starter tự tạo bảng cho production**. Một số phiên bản Spring Integration kiểm tra sự tồn tại bảng khi khởi động và sẽ báo lỗi nếu bảng thiếu.

**JdbcMetadataStore** có thể tham gia transaction JDBC. Khi metadata write nằm trong **cùng transaction** với những thay đổi nghiệp vụ dùng cùng database và transaction manager, rollback có thể hoàn tác cả entry metadata. Nhưng **đừng mặc định rằng @Transactional đặt trên handler đủ để bao lấy selector**: interceptor chạy trước khi handler được gọi; phải kiểm tra vị trí transaction advice, cùng DataSource và thời điểm commit thực tế.

### 9.2. Redis và các backend phân tán

**RedisMetadataStore** dùng Redis làm nơi giữ metadata chia sẻ giữa nhiều instance. Dùng Redis có thể đáp ứng nhu cầu thông lượng, nhưng phải xác minh đặc tính atomic compare-and-set của **phiên bản triển khai và topology**; ví dụ một số thao tác replace dựa trên WATCH có giới hạn ở Redis Cluster. Cũng cần thiết kế persistence, replication, eviction, thời gian sống key và xử lý khi Redis không sẵn sàng.

**Không coi bất kỳ persistent store nào là bảo đảm exactly-once cho side effect khác backend.** Nếu metadata ở Redis còn dữ liệu nghiệp vụ nằm ở PostgreSQL hoặc thao tác cuối là HTTP call, không có transaction phân tán tự động giữa chúng.

### 9.3. Giới hạn dung lượng và thời gian giữ key

Với **một key cho mỗi eventId**, tổng số key tăng theo số sự kiện đã thấy:

~~~text
10.000 event/phút × 60 × 24 × 7 ngày
    = 100.800.000 key cho một tuần
~~~

Hệ thống phải xác định **deduplication window** dựa trên thời gian broker có thể redeliver, thời gian replay thủ công, nghiệp vụ và ràng buộc pháp lý. Việc xóa metadata quá sớm làm event cũ được chấp nhận lại; giữ mọi key mãi mãi làm kho trạng thái phình to.

Không phải mọi MetadataStore tự có TTL ở cấp key. Nếu dùng cơ chế TTL của backend hoặc một reaper dọn định kỳ, cần chứng minh xóa key an toàn với replay, retry và điều kiện cạnh tranh. Đừng áp dụng một TTL mặc định mà chưa có số liệu retention của hệ thống gửi.

## 10. Bẫy lớn nhất: đánh dấu trước khi handler thành công

Khi **MetadataStoreSelector.accept(message)** thực thi, nó thường ghi key thành công **trước khi** target handler chạy. Đây là thời điểm **admission/claimed**, chưa phải chứng cứ **side effect đã commit**.

~~~mermaid
sequenceDiagram
    participant B as Broker
    participant M as MetadataStore
    participant H as Business handler
    B->>M: evt-7821
    M->>M: putIfAbsent(evt-7821) thành công
    M->>H: Cho phép xử lý
    H--xH: Lỗi database / timeout
    Note over B,H: Key vẫn có nếu không rollback đồng bộ
    B->>M: Redelivery evt-7821
    M-->>B: Duplicate → bị loại
    Note over B,H: Có thể mất tác động nghiệp vụ
~~~

Vì vậy cần phân biệt:

| Mô hình | Điều đảm bảo được | Rủi ro chính |
| --- | --- | --- |
| Mark key trước handler, **không** có rollback state | Một key thường chỉ được chấp nhận một lần trong cửa sổ lưu | Handler lỗi sau khi mark khiến redelivery bị chặn |
| Xóa key thủ công khi handler lỗi | Có thể cho phép thử lại | Xóa nhầm key khi có worker đồng thời; side effect đã thực hiện một phần |
| Metadata JDBC + business write trong **cùng DB transaction** | Mark và side effect DB cùng commit/rollback khi bao đúng transaction | Không bao phủ HTTP, broker hoặc backend khác |
| Bảng **processed_event** có unique constraint trong cùng transaction nghiệp vụ | Có thể bảo vệ một nghiệp vụ/consumer ngay tại DB nguồn sự thật | Cần định nghĩa khi nào ACK, giữ trạng thái và xử lý transaction |
| Business operation lũy đẳng theo request key | Retry an toàn hơn ngay cả khi gate lỗi hoặc metadata bị mất | Phải thiết kế ở từng side effect liên quan |

### 10.1. Ví dụ outbox/consumer có business transaction

Khi có yêu cầu “một event chỉ được ghi nhận một lần vào sổ thanh toán”, một cách chắc chắn hơn là **unique constraint ngay trong database nghiệp vụ**:

~~~sql
CREATE TABLE processed_event (
    consumer_name VARCHAR(120) NOT NULL,
    event_id VARCHAR(120) NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Ví dụ PostgreSQL trong service:

~~~java
@Service
public class PaidOrderService {
    private final JdbcTemplate jdbc;

    public PaidOrderService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void applyPayment(OrderPaid event) {
        int accepted = jdbc.update("""
            INSERT INTO processed_event (consumer_name, event_id)
            VALUES (?, ?)
            ON CONFLICT DO NOTHING
            """, "paid-order-v1", event.eventId());

        if (accepted == 0) {
            // Đã commit trước đó hoặc một transaction khác sở hữu key;
            // kết quả cụ thể phụ thuộc isolation/unique lock của DB.
            return;
        }

        int changed = jdbc.update("""
            UPDATE orders SET paid = TRUE
            WHERE order_id = ?
            """, event.orderId());

        if (changed != 1) {
            // Ném RuntimeException để rollback cả marker và thay đổi DB.
            throw new IllegalStateException("Unknown order");
        }
    }
}
~~~

Trong ví dụ này, **processed_event** và bảng **orders** phải thuộc **cùng DataSource/transaction manager**. Khi update lỗi, rollback xóa marker chưa commit; khi transaction commit, redelivery có thể được coi là đã xử lý. **ON CONFLICT DO NOTHING** là cú pháp PostgreSQL: nếu dùng DB khác, thay bằng cú pháp tương đương và kiểm thử concurrency/unique constraint thật.

Đây là **hàng rào đúng đắn tại tầng nghiệp vụ**, còn IdempotentReceiverInterceptor có thể làm lớp lọc sớm nhằm giảm tải. Tuy nhiên, nếu layer lọc sớm có thể chặn redelivery của một transaction chưa commit, nó không được phép trở thành nguồn quyết định duy nhất. Có thể bỏ lọc sớm, hoặc tổ chức cùng transaction một cách kiểm chứng được, hoặc dùng trạng thái **IN_PROGRESS / COMPLETED** với lease, recovery và fencing.

### 10.2. Idempotency khác với transaction và exactly-once

- **Idempotency**: cùng thao tác được lặp lại vẫn cho hiệu ứng nghiệp vụ mong muốn tương đương một lần.
- **Atomic transaction**: một nhóm thay đổi trong phạm vi transaction cùng commit hoặc rollback.
- **Delivery guarantee**: broker có thể giao at-most-once, at-least-once hoặc cơ chế khác; không tự động đồng nhất với hiệu ứng nghiệp vụ exactly-once.
- **Exactly-once effect** qua nhiều hệ thống: cần ranh giới và giao thức phù hợp, thường kết hợp idempotency, transactional outbox, consumer inbox, reconciliation hoặc cơ chế cụ thể của broker.

Đừng dùng log “duplicate discarded” như bằng chứng business handler đã chạy thành công trước đó.

## 11. Thông điệp trùng khác thông điệp lỗi và sự kiện đến đảo thứ tự

**Duplicate:** cùng eventId (hoặc cùng business operation ID) đến lại, về bản chất yêu cầu không thực hiện side effect lần hai.

**Out-of-order:** event hợp lệ nhưng version cũ đến sau version mới; đây không nhất thiết là duplicate theo eventId.

**Transient failure:** event mới chưa hoàn tất vì DB/broker/upstream không sẵn sàng; cần retry và khả năng phục hồi.

**Poison message:** cấu trúc/loại message không hợp lệ và có thể luôn thất bại; cần validation, dead-letter và quy trình khắc phục riêng.

Ví dụ nhận snapshot tồn kho theo **sku** và **sourceVersion**. Mỗi SKU chỉ cần nhận version **lớn hơn** version gần nhất:

~~~java
@Bean
MetadataStoreSelector inventoryVersionSelector(
        @Qualifier("inventoryVersionStore") ConcurrentMetadataStore store) {

    return new MetadataStoreSelector(
            msg -> "inventory:v1:"
                    + ((InventoryChanged) msg.getPayload()).sku(),
            msg -> Long.toString(
                    ((InventoryChanged) msg.getPayload()).sourceVersion()),
            store)
            .compareValues((oldValue, newValue) ->
                    Long.parseLong(newValue) > Long.parseLong(oldValue));
}
~~~

Ví dụ dùng DTO:

~~~java
public record InventoryChanged(
        String sku, long sourceVersion, int availableQuantity) {}
~~~

**compareValues** cho phép chấp nhận message mới theo giá trị version, cập nhật metadata bằng thao tác so sánh/thay thế của store. Điều này hữu ích để chặn **version cũ hoặc bằng**. Tuy nhiên, việc tăng checkpoint trong MetadataStore **không đảm bảo side effect hoàn tất theo thứ tự**: hai message version 7 và 8 có thể cùng được chấp nhận rồi handler version 7 ghi sau version 8.

Muốn snapshot không quay về giá trị cũ, phải bảo vệ trực tiếp tại nguồn dữ liệu nghiệp vụ, ví dụ **UPDATE ... WHERE stored_version < incoming_version**, optimistic locking, hoặc tuần tự hóa xử lý theo key. Cũng phải xem xét crash sau khi checkpoint tăng nhưng trước khi business write hoàn tất.

## 12. Tương tác với broker, retry, error channel và ACK

Đặt chống trùng vào flow phải tính cả semantics của adapter và channel:

~~~text
Inbound broker adapter
   ↓ deserialize / validate
Input channel
   ↓ IdempotentReceiverInterceptor tại handler
   ├─ new → handler → DB/update → thành công → ACK
   ├─ duplicate → mark hoặc discard theo chính sách → ACK phù hợp
   ├─ transient error → retry giới hạn → DLQ/requeue có điều kiện
   └─ invalid/poison → xử lý lỗi và DLQ theo hợp đồng
~~~

**ACK, transaction và error propagation không giống nhau giữa Kafka, RabbitMQ, JMS, HTTP gateway hoặc file adapter.** Cần đọc cấu hình adapter thực tế (manual/auto acknowledgment, transaction mode, commit, error channel, retry advice) để biết khi nào broker thật sự nhận ACK.

Một số lỗi thiết kế:

- Nếu **throwExceptionOnRejection(true)** khiến adapter ném lỗi cho duplicate đã xử lý, nó có thể bị retry vô hạn nếu policy coi mọi exception là retryable.
- Nếu **discardChannel** gửi message sang handler audit có thể ném exception, ACK có thể bị ảnh hưởng tùy chuỗi xử lý. Quy định rõ audit là best-effort hay bắt buộc.
- Nếu giao message qua **ExecutorChannel** hoặc queue bất đồng bộ, transaction ở thread đầu vào có thể không bao trùm handler downstream; không giả định rollback một thread tự rollback metadata ở thread khác.
- Nếu retry advice và interceptor cùng nằm trên một endpoint, **thứ tự advice** có thể làm mỗi lần retry chạy selector lại hoặc sử dụng selector một lần; phải kiểm thử luồng thực thay vì chỉ dựa vào tên bean.
- Nếu metadata store chập chờn, đó là **lỗi hạ tầng**, không phải kết quả “duplicate”. Đừng catch mọi exception rồi âm thầm discard.

**Một quy tắc quan trọng:** chỉ ACK bản tin khi hệ thống đã đạt trạng thái mà việc broker giao lại không còn cần thiết theo hợp đồng nghiệp vụ. Đối với duplicate đã xử lý hoàn tất, ACK thường hợp lý; đối với message mới bị lỗi tạm thời, cần duy trì khả năng retry.

## 13. Kiểm thử: cả selector lẫn ranh giới thất bại

### 13.1. Kiểm thử selector tại chỗ

Một test nhỏ xác minh **putIfAbsent** cho cùng một khóa:

~~~java
@Test
void firstMessageAcceptedSecondRejected() {
    ConcurrentMetadataStore store = new SimpleMetadataStore();
    MetadataStoreSelector selector = new MetadataStoreSelector(
            m -> "paid:v1:" + m.getHeaders().get("eventId"),
            store);

    Message<String> first = MessageBuilder.withPayload("paid")
            .setHeader("eventId", "evt-7821")
            .build();

    Message<String> redelivery = MessageBuilder.withPayload("paid")
            .setHeader("eventId", "evt-7821")
            .build();

    assertTrue(selector.accept(first));
    assertFalse(selector.accept(redelivery));
}
~~~

Đây là test về **selector**, chưa chứng minh interceptor đánh dấu/loại đúng, cũng chưa chứng minh state được chia sẻ qua hai JVM.

### 13.2. Kiểm thử luồng có advice

Với Spring Integration Test hoặc một test context nhỏ có input channel và mocked business handler:

1. Gửi message **evt-7821** lần đầu → handler được gọi một lần.
2. Gửi lại với **eventId giống hệt** nhưng message.id mới → nếu **mark mode**, handler vẫn được gọi và nhận header duplicateMessage=true; nếu **discard mode**, handler không được gọi thêm.
3. Gửi **evt-7822** → được xử lý bình thường, không bị ảnh hưởng bởi khóa cũ.
4. Chạy hai thread đồng thời cùng eventId → với store atomic, chỉ một request được selector chấp nhận.
5. Khởi động lại context/instance và gửi lại → store bền vững chặn duplicate; SimpleMetadataStore thường không làm được.
6. Giả lập handler lỗi sau khi selector ghi key → xác minh redelivery và rollback/khả năng phục hồi theo mô hình đã thiết kế.
7. Giả lập metadata store không sẵn sàng → lỗi đi qua retry/error channel đúng, không bị coi thành duplicate.
8. Với compareValues, gửi version 8 rồi 7, đồng thời 7 và 8 → kiểm tra cả **business state** chứ không chỉ metadata checkpoint.

Ví dụ một kiểm tra handler đọc đúng header trong mark mode:

~~~java
boolean markedDuplicate = Boolean.TRUE.equals(
        message.getHeaders().get(
                IntegrationMessageHeaderAccessor.DUPLICATE_MESSAGE));
assertTrue(markedDuplicate);
~~~

### 13.3. Tích hợp với backend thật

Với **JdbcMetadataStore**, kiểm thử qua hai application context hoặc hai instance cùng DB; nên dùng Testcontainers/DB phù hợp để kiểm tra unique key, transaction rollback, lock behavior và restart. Với RedisMetadataStore, kiểm tra đúng topology Redis thực tế và cách backend xử lý CAS, failover hoặc TTL.

**Mock MetadataStore không chứng minh tính nguyên tử phân tán.** Test unit chỉ hữu ích cho việc chọn key và nhánh flow. Test tích hợp mới chứng minh backend đúng khi cạnh tranh và khôi phục.

## 14. Quan sát và vận hành một flow chống trùng

Một chính sách dedupe khó vận hành nếu chỉ log “duplicate detected”. Nên đo:

| Metric/tín hiệu | Ý nghĩa |
| --- | --- |
| **messages_received_total** theo consumer/flow | Tổng đầu vào, bao gồm redelivery |
| **idempotent_accepted_total** | Số lần key mới được chấp nhận |
| **idempotent_duplicate_total** | Số lần key bị từ chối theo selector |
| **idempotent_discarded_total** theo lý do | Số message thật sự bị chuyển sang discard |
| **metadata_store_latency / errors** | Nút thắt hoặc sự cố ở nơi giữ state |
| **handler_success / failure** | Phân biệt đã nhận với đã xử lý nghiệp vụ |
| **retry / DLQ / lag** | Dấu hiệu hệ thống đang replay hoặc tồn đọng |
| **retention/key count** | Nguy cơ bộ nhớ và storage vượt giới hạn |

Đừng nhầm **đã chấp nhận bởi selector** với **đã commit nghiệp vụ**. Tracing nên nối được broker message ID, business eventId, idempotency key (ẩn/băm nếu nhạy cảm), metadata operation và transaction ID/correlation ID.

Với flow cần độ tin cậy cao, có thể lập dashboard so sánh:

- accepted − business_success: có thể là request đang xử lý hoặc thất bại sau admission;
- duplicate tăng đột ngột: broker redelivery, retry policy hoặc sai key;
- store timeout tăng: tải metadata quá lớn, DB lock, Redis saturation;
- discard tăng nhưng ACK/DLQ bất thường: cần kiểm tra kênh discard và exception policy.

Không dùng eventId/tenantId/customerId làm metric label có cardinality cao. Tránh log trọn payload, token hoặc thông tin cá nhân; dùng các định danh đã mã hóa/băm hoặc sampling có kiểm soát.

## 15. Sai lầm thường gặp và cách khắc phục

**“Chỉ gắn interceptor là duplicate tự bị loại.”** Sai. Mặc định nó **đánh dấu header** và vẫn gọi handler. Muốn loại phải cấu hình discard channel hoặc throwExceptionOnRejection.

**“MetadataStore.get() rồi put() đã an toàn concurrency.”** Sai. Hai worker có thể cùng đọc null. Dùng **ConcurrentMetadataStore.putIfAbsent**/compare-and-set phù hợp.

**“SimpleMetadataStore đủ cho nhiều pod Kubernetes.”** Sai nếu cần chống trùng giữa pod hoặc xuyên restart. Dùng store chia sẻ bền vững và kiểm thử atomicity.

**“Chỉ cần dùng headers.id.”** Không chắc: message ID kỹ thuật có thể thay đổi khi redelivery hoặc chuyển đổi. Phải định nghĩa business event ID ổn định.

**“Selector đã put key thì chắc chắn handler thành công.”** Sai. Key được ghi trước handler; nếu lỗi sau admission, redelivery có thể bị chặn. Dùng transaction, inbox/processed_event hoặc recovery protocol phù hợp.

**“Mọi exception đều là duplicate.”** Sai. Lỗi store, lỗi network, lỗi validation và duplicate là trạng thái khác nhau; cần ghi metric và xử lý riêng.

**“Cứ xóa key khi handler lỗi là xong.”** Không đủ. Có thể đụng concurrency hoặc side effect đã xảy ra; cần biết old value, in-flight state và transaction trước khi bù trừ.

**“Chống duplicate theo eventId giải quyết luôn out-of-order.”** Sai. Event khác ID nhưng version cũ vẫn có thể làm lùi state; dùng version checkpoint và kiểm soát ghi nghiệp vụ.

**“TTL càng ngắn càng tiết kiệm.”** TTL phải ít nhất phù hợp cửa sổ replay hợp lệ; xóa sớm có thể cho phép xử lý lại sự kiện cũ.

**“ACK khi interceptor accept xong là đủ.”** Sai nếu side effect chưa commit. Điểm ACK phải phản ánh trạng thái xử lý theo hợp đồng adapter/broker.

## 16. Checklist thiết kế trước khi triển khai

1. Định nghĩa **thế nào là trùng** cho mỗi consumer: eventId, operationId, version hay một khóa kết hợp.
2. Đặt prefix/region có phạm vi rõ; không làm trùng key của các flow/nghiệp vụ khác.
3. Chọn **mark mode** nếu handler cần nhìn duplicate; chọn **discard mode** khi duplicate được phép loại bỏ hoàn toàn.
4. Không dùng **throwExceptionOnRejection** nếu adapter sẽ retry mãi những duplicate vốn là trạng thái bình thường.
5. Dùng **ConcurrentMetadataStore** với atomic putIfAbsent/replace, xác minh backend và topology thực.
6. Quy định thời điểm **claim, business commit, ACK** và cách phục hồi khi crash ở từng điểm.
7. Nếu cần bảo đảm tác động nghiệp vụ một lần, bảo vệ ngay tại database hoặc API đích bằng unique key/idempotency key/conditional write.
8. Phân biệt **duplicate, out-of-order, retryable failure và poison message** trong routing/error channel.
9. Đặt retention/TTL theo thời gian broker có thể redeliver và nhu cầu replay; theo dõi tăng trưởng metadata.
10. Kiểm thử mark/discard, restart, cạnh tranh đa instance, lỗi handler, lỗi store và transaction rollback.
11. Đo accepted, discarded, handler success, retries, DLQ và store latency; không để dữ liệu nhạy cảm vào log/metric.

**Điểm mấu chốt:** **MetadataStore** giữ trạng thái, **MetadataStoreSelector** kiểm tra/đặt key, còn **IdempotentReceiverInterceptor** quyết định đường đi của message trùng ở handler. Tính đúng đắn của luồng tích hợp đến từ cách phối hợp ba cơ chế này với commit nghiệp vụ, ACK, retry và phục hồi sau lỗi.

## Tài liệu tham khảo

- [Spring Integration Reference — Metadata Store](https://docs.spring.io/spring-integration/reference/meta-data-store.html): hợp đồng metadata, lựa chọn store và thời gian sống.
- [Spring Integration Reference — Idempotent Receiver Enterprise Integration Pattern](https://docs.spring.io/spring-integration/reference/handler-advice/idempotent-receiver.html): cơ chế interceptor, duplicateMessage, discardChannel và throwExceptionOnRejection.
- [Spring Integration API — MetadataStoreSelector](https://docs.spring.io/spring-integration/api/org/springframework/integration/selector/MetadataStoreSelector.html): constructor, putIfAbsent và compareValues.
- [Spring Integration Reference — JDBC Metadata Store](https://docs.spring.io/spring-integration/reference/jdbc/metadata-store.html): JdbcMetadataStore, schema, transaction và atomicity.
- [Spring Integration Reference — Idempotent Downstream Processing a Split File](https://docs.spring.io/spring-integration/reference/file/splitter.html): ví dụ checkpoint với compareValues.
- [Spring Integration API — IdempotentReceiverInterceptor](https://docs.spring.io/spring-integration/docs/6.4.2/api/org/springframework/integration/handler/advice/IdempotentReceiverInterceptor.html): hành vi đánh dấu/loại/từ chối thông điệp trùng.

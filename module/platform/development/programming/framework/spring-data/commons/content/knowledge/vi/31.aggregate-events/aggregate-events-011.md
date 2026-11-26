# Ranh giới giữa phát sự kiện cục bộ với outbox hoặc broker bên ngoài

## 1. Ba việc cần được phân biệt

Trong chương **Sự kiện aggregate** của module **SPRING_DATA_COMMONS**, một aggregate có thể ghi nhận sự kiện khi thực hiện hành vi nghiệp vụ. Hạ tầng repository phù hợp có thể lấy các sự kiện đó và chuyển chúng vào cơ chế application event của Spring.

Tuy nhiên, ba việc sau có các bảo đảm khác nhau:

1. **Phát sự kiện trong ứng dụng:** chuyển event cho cơ chế listener trong process đang chạy.
2. **Lưu ý định gửi một cách bền vững:** ghi một bản ghi để sau lỗi hoặc khởi động lại vẫn biết cần gửi gì.
3. **Giao nhận qua broker:** chuyển thông điệp tới hạ tầng bên ngoài và để consumer xử lý theo hợp đồng giao nhận.

Một lời gọi `publishEvent(...)` không tự hoàn thành cả ba việc. Tương tự, thêm `@DomainEvents` lên aggregate không tự biến repository thành producer bền vững của một message broker.

Ví dụ, khi đơn hàng được duyệt, hệ thống có thể cần:

- Thông báo cho một thành phần cục bộ trong ứng dụng.
- Ghi trạng thái `APPROVED` vào database.
- Đảm bảo hệ thống giao hàng cuối cùng nhận được thông điệp tích hợp.

Mỗi yêu cầu cần một ranh giới trách nhiệm rõ ràng. Điểm khó không chỉ là gọi API gửi, mà là xử lý thời điểm database, process, mạng hoặc consumer gặp lỗi.

## 2. Phát sự kiện cục bộ cung cấp điều gì?

Spring Data Commons cung cấp các abstraction như `@DomainEvents`, `@AfterDomainEventPublication` và `AbstractAggregateRoot` để phối hợp sự kiện của aggregate với các lời gọi repository được hỗ trợ.

Luồng khái quát:

~~~text
Hành vi nghiệp vụ
    → aggregate đăng ký event
    → lời gọi repository phù hợp
    → application event publisher
    → listener trong ứng dụng
~~~

Danh sách event chờ publication trên aggregate thông thường là dữ liệu trong bộ nhớ. Nó không tự là một bảng event, một outbox hay một hàng đợi phục hồi sau khi tiến trình dừng.

### 2.1. Cục bộ là ranh giới của application context

Application event được định tuyến cho listener trong hạ tầng ứng dụng liên quan. Nếu cùng một dịch vụ có ba instance, không nên mặc định event được phát ở instance A sẽ tự đến listener ở B và C.

Muốn liên lạc giữa các process, cần một cơ chế ngoài việc publication cục bộ, chẳng hạn broker, giao tiếp mạng hoặc một nguồn dữ liệu chung có quy trình đọc tương ứng.

### 2.2. Đồng bộ hay bất đồng bộ không quyết định độ bền

Trong cấu hình multicaster đồng bộ thông thường, listener được thực thi trên luồng publication. Cấu hình executor hoặc listener bất đồng bộ có thể thay đổi điều này.

Chuyển listener sang bất đồng bộ không tự tạo một hàng đợi bền vững. Nếu tác vụ chỉ nằm trong bộ nhớ và process dừng, ứng dụng có thể mất công việc chưa hoàn tất.

Ngược lại, một listener đồng bộ có thể ghi dữ liệu bền vững nếu nó tham gia đúng transaction và kho lưu trữ. Độ bền đến từ cơ chế lưu và phục hồi, không chỉ từ việc chạy trên luồng nào.

### 2.3. Dọn event không phải xác nhận của broker

`@AfterDomainEventPublication` thường được dùng để dọn danh sách sự kiện sau publication. Callback này không đồng nghĩa:

- Transaction nghiệp vụ chắc chắn đã commit.
- Broker đã lưu thông điệp theo yêu cầu độ bền.
- Consumer đã xử lý xong.
- Một tác dụng phụ bên ngoài, như gửi thư hoặc thu tiền, chỉ xảy ra một lần.

Không dùng trạng thái “danh sách event đã rỗng” làm bằng chứng về việc giao nhận bên ngoài.

## 3. Transaction của database không tự bao trùm lời gọi mạng

Giả sử một service vừa cập nhật đơn hàng, vừa gửi thông điệp:

~~~text
update order
send message
commit database
~~~

Nếu broker nhận thông điệp nhưng database rollback sau đó, consumer có thể thấy một sự kiện về thay đổi chưa được commit.

Đổi thứ tự cũng có khe hở:

~~~text
update order
commit database
send message
~~~

Nếu process dừng sau commit nhưng trước khi gửi, dữ liệu đã đổi nhưng không có thông điệp tương ứng được giao.

| Trình tự | Điểm lỗi | Hệ quả có thể xảy ra |
| --- | --- | --- |
| Gửi trước commit | Database rollback sau khi broker nhận | Thông điệp mô tả thay đổi không tồn tại trong dữ liệu đã commit |
| Gửi sau commit | Process dừng trước lần gửi | Thay đổi đã commit nhưng thông điệp chưa được gửi |
| Gửi và nhận lỗi timeout | Không biết broker đã nhận hay chưa | Retry có thể tạo thông điệp trùng |
| Broker đã nhận, chưa đánh dấu tiến độ | Process dừng | Relay có thể gửi lại cùng thông điệp |

Một transaction local của JPA hoặc JDBC không tự làm lời gọi tới một broker bất kỳ trở thành một phần của cùng quyết định commit.

Broker có thể có các transaction và cơ chế khử trùng riêng trong phạm vi của nó. Không nên suy những bảo đảm đó thành tính nguyên tử tự động giữa database ứng dụng, broker và mọi hệ thống bên ngoài.

## 4. AFTER_COMMIT chọn thời điểm, chưa tạo công việc bền vững

`@TransactionalEventListener` cho phép gắn việc xử lý với phase của transaction. Với `AFTER_COMMIT`, listener được lên lịch xử lý theo lần commit thành công của transaction phù hợp.

Điều này hữu ích để tránh xử lý như một thay đổi đã commit khi transaction đã rollback. Nhưng vẫn tồn tại khoảng trống:

~~~text
Database commit thành công
    → process dừng
    → listener chưa gửi được thông điệp
~~~

Nếu chưa lưu một công việc gửi bền vững, sau khi khởi động lại có thể không còn dữ liệu nào cho biết cần thực hiện lần gửi đó.

Các điểm cần hiểu:

- Listener theo transaction cần một transaction phù hợp; fallback khi không có transaction là một lựa chọn cấu hình riêng.
- Lỗi của listener sau commit không thể làm transaction đã commit quay lại rollback.
- Không có một hàng đợi retry bền vững chỉ nhờ annotation này.
- Nếu listener sau commit cần ghi database, phải thiết kế transaction phù hợp cho lần ghi đó.

Một callback sau commit có thể đánh thức relay để giảm độ trễ, nhưng nguồn công việc đáng tin cậy vẫn phải là dữ liệu đã lưu. Nếu tín hiệu đánh thức bị mất, relay vẫn phải có cách tìm lại công việc.

## 5. Transactional outbox đưa ý định gửi vào cùng local transaction

Mẫu outbox lưu thay đổi nghiệp vụ và bản ghi cần phát trong cùng một transaction tại kho dữ liệu hỗ trợ ranh giới đó:

~~~text
BEGIN
    cập nhật đơn hàng
    thêm bản ghi outbox
COMMIT
~~~

Khi transaction commit, cả trạng thái nghiệp vụ và ý định gửi đều tồn tại. Khi transaction rollback, cả hai đều không trở thành dữ liệu đã commit.

Một relay riêng đọc các bản ghi outbox đã commit rồi gửi tới broker.

~~~mermaid
flowchart LR
    A["Application service"] --> B["Local transaction"]
    B --> C["Dữ liệu aggregate"]
    B --> D["Outbox"]
    D --> E["Relay: đọc và retry"]
    E --> F["Broker"]
    F --> G["Consumer"]
    G --> H["Dữ liệu hoặc tác dụng phụ phía nhận"]
~~~

Outbox giải quyết việc lưu bền vững **ý định gửi cùng thay đổi nghiệp vụ**. Relay và consumer vẫn có những ranh giới lỗi riêng.

### 5.1. Điều kiện của tính nguyên tử

Không phải mọi thao tác ghi vào hai nơi đều tự trở thành outbox nguyên tử.

Ví dụ, cập nhật đơn hàng trong database A rồi ghi một bản ghi mang tên outbox vào database B bằng transaction riêng vẫn có thể để lại trạng thái chỉ một bên thành công.

Cần xác định rõ:

- Hai lần ghi dùng cùng transaction thực tế hay không.
- Cùng transaction manager và tài nguyên được quản lý phù hợp hay không.
- Lỗi ghi outbox có làm transaction nghiệp vụ rollback theo hợp đồng hay không.
- Có đường thay đổi nghiệp vụ nào bỏ qua việc ghi outbox không.

## 6. Phân công trách nhiệm giữa aggregate, outbox và broker

| Thành phần | Trách nhiệm chính | Không nên tự suy ra |
| --- | --- | --- |
| Aggregate | Giữ quy tắc nghiệp vụ, xác định một fact hoặc hành vi đã được chấp nhận | Biết cách retry kết nối broker |
| Application service | Điều phối transaction và việc lưu dữ liệu cần thiết | Local transaction tự điều khiển mọi hệ thống ngoài |
| Publisher/listener cục bộ | Truyền tín hiệu trong ứng dụng theo cấu hình | Tự có độ bền sau process crash |
| Outbox | Lưu nội dung và tiến độ phát theo thiết kế | Consumer chắc chắn đã xử lý |
| Relay | Gửi, xác nhận tiến độ, retry, phối hợp nhiều worker | Có thể tránh mọi bản sao chỉ bằng một lần gửi |
| Broker | Định tuyến và lưu/giao thông điệp theo cấu hình, giao thức cụ thể | Mọi tác dụng phụ business đã hoàn thành |
| Consumer | Kiểm tra hợp đồng, xử lý, chống trùng, xác nhận theo quy tắc | Chỉ nhận một bản sao duy nhất |

Một event nghiệp vụ trong model có thể được chuyển thành một thông điệp tích hợp ổn định dành cho hệ thống ngoài. Không nhất thiết phải công khai nguyên class nội bộ của aggregate.

## 7. Ví dụ JPA: ghi outbox tường minh trong service

Ví dụ dưới đây minh họa đường ghi nguyên tử tại một database dùng Spring Data JPA và Jakarta Persistence. Java cần hỗ trợ `record`; mỗi public type được đặt trong file riêng.

Ví dụ giả định ứng dụng đã có datasource, quét entity/repository, bean `Clock` và `ObjectMapper` được cấu hình hỗ trợ các kiểu dữ liệu sử dụng, bao gồm `Instant`.

Đây là mẫu ghi outbox tường minh. Nó không phụ thuộc một listener sau commit để tạo ý định gửi.

### 7.1. Fact nghiệp vụ và payload tích hợp

~~~java
import java.time.Instant;
import java.util.UUID;

public record OrderApproved(
        UUID eventId,
        UUID orderId,
        Instant occurredAt) {
}
~~~

~~~java
import java.time.Instant;
import java.util.UUID;

public record OrderApprovedV1(
        UUID orderId,
        Instant approvedAt) {
}
~~~

`OrderApproved` là kết quả nghiệp vụ trong ví dụ. `OrderApprovedV1` là phần dữ liệu của hợp đồng tích hợp phiên bản 1. Metadata như event ID và event type sẽ được lưu cùng payload trong outbox.

### 7.2. Entity nghiệp vụ

~~~java
import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

@Entity
@Table(name = "sales_order")
public class SalesOrder {

    @Id
    private UUID id;

    @Version
    private Long version;

    private String status;

    protected SalesOrder() {
    }

    public SalesOrder(UUID id) {
        this.id = Objects.requireNonNull(id, "id");
        this.status = "DRAFT";
    }

    public OrderApproved approve(Instant occurredAt) {
        Objects.requireNonNull(occurredAt, "occurredAt");

        if (!"DRAFT".equals(status)) {
            throw new IllegalStateException(
                    "Only a draft order can be approved");
        }

        status = "APPROVED";

        return new OrderApproved(
                UUID.randomUUID(), id, occurredAt);
    }
}
~~~

`approve(...)` ở đây trả fact cho service. Class không tự đăng ký thêm một đường publication bằng `@DomainEvents`. Cách này giúp thấy rõ lần ghi outbox nào thuộc transaction.

Nếu domain model thực tế còn đăng ký local event, phải phân công luồng tạo outbox để không vô tình ghi hai bản ghi tích hợp cho cùng một fact qua hai đường độc lập.

### 7.3. Bản ghi outbox

~~~java
public enum OutboxStatus {
    PENDING,
    PUBLISHED
}
~~~

~~~java
import java.time.Instant;
import java.util.UUID;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Lob;
import jakarta.persistence.Table;

@Entity
@Table(name = "outbox_message")
public class OutboxMessage {

    @Id
    private UUID eventId;

    @Column(nullable = false)
    private String aggregateId;

    @Column(nullable = false)
    private String eventType;

    @Column(nullable = false)
    private int schemaVersion;

    @Column(nullable = false)
    private Instant occurredAt;

    @Lob
    @Column(nullable = false)
    private String payloadJson;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private OutboxStatus status;

    protected OutboxMessage() {
    }

    public OutboxMessage(
            UUID eventId,
            String aggregateId,
            String eventType,
            int schemaVersion,
            Instant occurredAt,
            String payloadJson) {

        this.eventId = eventId;
        this.aggregateId = aggregateId;
        this.eventType = eventType;
        this.schemaVersion = schemaVersion;
        this.occurredAt = occurredAt;
        this.payloadJson = payloadJson;
        this.status = OutboxStatus.PENDING;
    }
}
~~~

Entity này chỉ minh họa nội dung tối thiểu của lần ghi outbox. Các cột phục vụ claim, lease, số lần thử, lịch retry và trạng thái lỗi được bổ sung theo thiết kế relay; chưa có relay hoàn chỉnh trong đoạn Java này.

Khóa `eventId` nhận diện thông điệp. Nó không tự chống việc một command bị thực hiện lại và sinh một event ID mới; idempotency của command là một hợp đồng khác.

### 7.4. Repository và service

~~~java
import java.util.UUID;

import org.springframework.data.jpa.repository.JpaRepository;

public interface SalesOrderRepository
        extends JpaRepository<SalesOrder, UUID> {
}
~~~

~~~java
import java.util.UUID;

import org.springframework.data.jpa.repository.JpaRepository;

public interface OutboxMessageRepository
        extends JpaRepository<OutboxMessage, UUID> {
}
~~~

~~~java
import java.time.Clock;
import java.util.UUID;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ApproveOrderService {

    private final SalesOrderRepository orders;
    private final OutboxMessageRepository outbox;
    private final ObjectMapper objectMapper;
    private final Clock clock;

    public ApproveOrderService(
            SalesOrderRepository orders,
            OutboxMessageRepository outbox,
            ObjectMapper objectMapper,
            Clock clock) {

        this.orders = orders;
        this.outbox = outbox;
        this.objectMapper = objectMapper;
        this.clock = clock;
    }

    @Transactional
    public UUID approve(UUID orderId) {
        SalesOrder order = orders.findById(orderId)
                .orElseThrow(() -> new IllegalArgumentException(
                        "Order not found"));

        OrderApproved fact = order.approve(clock.instant());

        String payload = encode(new OrderApprovedV1(
                fact.orderId(), fact.occurredAt()));

        orders.save(order);

        outbox.save(new OutboxMessage(
                fact.eventId(),
                fact.orderId().toString(),
                "order.approved",
                1,
                fact.occurredAt(),
                payload));

        return fact.eventId();
    }

    private String encode(OrderApprovedV1 payload) {
        try {
            return objectMapper.writeValueAsString(payload);
        } catch (JsonProcessingException exception) {
            throw new IllegalStateException(
                    "Cannot encode integration event", exception);
        }
    }
}
~~~

Các repository trong mẫu phải tham gia cùng transaction manager và database. Method service phải được gọi theo cách làm transaction của Spring thực sự có hiệu lực.

Lỗi serialize được chuyển thành lỗi runtime thay vì bị nuốt rồi tiếp tục commit trạng thái đơn hàng mà không có payload. Các lỗi ghi dữ liệu cũng phải được xử lý theo quy tắc rollback đã chọn.

Hai lần gọi `save` không tự commit hai transaction riêng khi chúng tham gia outer transaction này. `flush`, nếu được dùng để phát hiện lỗi sớm, cũng không tự thay thế commit.

Với entity JPA đang managed, dirty checking có thể ghi thay đổi mà không cần gọi lại `save`. Điều cốt yếu của mẫu là thay đổi nghiệp vụ và bản ghi outbox nằm trong cùng transaction, không phải số lần gọi repository.

## 8. Có thể dùng local event để ghi outbox không?

Có thể, nếu đường local event được thiết kế để việc ghi outbox vẫn nằm trong cùng transaction nghiệp vụ.

Ví dụ về điều kiện cần:

- Transaction được mở tại application service.
- Aggregate được đưa qua lời gọi repository thực sự hỗ trợ publication.
- Listener ghi outbox chạy tại thời điểm còn có thể tham gia transaction đó.
- Listener sử dụng cùng tài nguyên giao dịch phù hợp.
- Lỗi ghi outbox phải làm transaction thất bại theo hợp đồng.

Một listener đồng bộ có kiểm soát transaction, hoặc một listener ở phase `BEFORE_COMMIT` với cấu hình phù hợp, có thể là điểm tổ chức việc ghi này. Phải kiểm chứng luồng thực tế, đặc biệt khi có custom repository, listener bất đồng bộ hoặc nhiều transaction manager.

Nếu chọn cách này, nên làm rõ hoặc cưỡng chế yêu cầu có transaction thay vì âm thầm chạy ngoài transaction.

Không dùng việc ghi outbox lần đầu ở `AFTER_COMMIT` như một cách đạt tính nguyên tử với thay đổi đã commit trước đó. Hai lần ghi đó không còn thuộc cùng quyết định commit.

Giữa cách ghi trực tiếp trong service và cách qua listener, chọn một nơi chịu trách nhiệm tạo thông điệp cho mỗi hợp đồng. Local event có thể giúp tách thành phần, nhưng không nên che mất ranh giới transaction.

## 9. Relay là một vòng xử lý có thể phục hồi

Relay đọc outbox và gửi tới broker. Một vòng xử lý khái quát:

~~~text
1. Chọn và claim một nhóm bản ghi đến hạn.
2. Hoàn tất transaction claim theo chiến lược đã chọn.
3. Gửi từng thông điệp với eventId ổn định.
4. Chờ kết quả xác nhận theo hợp đồng client/broker.
5. Ghi tiến độ đã gửi, hoặc lên lịch retry.
6. Khôi phục các claim hết hạn khi worker bị lỗi.
~~~

### 9.1. Claim cần ngăn xử lý tranh chấp theo thiết kế

Nếu có nhiều relay, một truy vấn “tìm tất cả PENDING” rồi cập nhật sau không tự ngăn hai worker cùng đọc một nhóm bản ghi.

Các hướng triển khai có thể gồm khóa phù hợp, cập nhật có điều kiện, optimistic locking hoặc lease có thời hạn. Lựa chọn phụ thuộc store và yêu cầu thứ tự.

Không có một câu SQL claim duy nhất dùng nguyên xi cho mọi database. Cần kiểm chứng cách khóa, mức cô lập, index và khả năng mở rộng của hệ thống thực tế.

### 9.2. Không giữ transaction database dài chỉ để chờ mạng nếu chưa có lý do rõ

Một thiết kế thường dùng claim ngắn, gửi ngoài transaction claim rồi ghi kết quả trong transaction khác. Nó giảm thời gian giữ khóa, nhưng phải xử lý worker mất lease hoặc dừng giữa các bước.

Khi dùng lease, cập nhật tiến độ nên kiểm tra quyền sở hữu claim phù hợp để một worker cũ không ghi đè kết quả của worker đã tiếp quản. Lease cũng không tự ngăn mọi lần gửi trùng khi một worker đang chậm.

### 9.3. Không đánh dấu hoàn tất trước khi có xác nhận phù hợp

Nếu relay đánh dấu `PUBLISHED` rồi mới gửi, process dừng ở giữa có thể làm thông điệp bị bỏ qua vĩnh viễn.

Ngược lại, gửi thành công rồi mới đánh dấu tiến độ giữ được khả năng retry, nhưng chấp nhận nguy cơ gửi lại khi process dừng sau lần gửi.

Ý nghĩa của xác nhận phụ thuộc client và broker: một API trả về, một future hoàn tất và một xác nhận lưu bền vững có thể là các mốc khác nhau. Thiết kế phải dùng đúng mốc mà hợp đồng yêu cầu.

## 10. Outbox vẫn có thể tạo thông điệp trùng

Một tình huống điển hình:

~~~text
Relay gửi event E.
Broker xác nhận đã nhận E.
Relay dừng trước khi ghi PUBLISHED.
Relay khác đọc lại bản ghi và gửi E lần nữa.
~~~

Không thể giải quyết khoảng trống này chỉ bằng việc đọc outbox theo một thứ tự khác. Phải có hợp đồng xử lý trùng hoặc một cơ chế giao dịch phù hợp với phạm vi các thành phần tham gia.

Trong cách triển khai outbox với retry phổ biến, cần thiết kế cho khả năng cùng event được giao nhiều lần. Mục tiêu là không làm mất ý định gửi đã commit và có khả năng tiếp tục xử lý khi hạ tầng phục hồi.

Điều này còn phụ thuộc vận hành: relay phải tiếp tục chạy, bản ghi lỗi phải được quan sát, dữ liệu chưa gửi không bị xóa sớm và lỗi hợp đồng phải có cách xử lý.

`PUBLISHED` nên được định nghĩa là một mốc cụ thể, chẳng hạn broker đã xác nhận theo cấu hình gửi. Nó không tự có nghĩa mọi consumer đã hoàn tất tác dụng phụ nghiệp vụ.

## 11. Consumer cần idempotency tại ranh giới của nó

Một consumer không nên chỉ dựa vào niềm tin rằng producer sẽ không bao giờ gửi trùng.

Một cách thường dùng là lưu dấu nhận thông điệp, còn gọi là inbox hoặc processed-message record, với khóa duy nhất theo consumer và event ID.

Luồng logic khi tác dụng phụ nằm trong cùng database phía consumer:

~~~text
BEGIN consumer transaction
    thử ghi dấu (consumerName, eventId) chưa xử lý
    nếu event đã được xử lý thành công: bỏ qua thay đổi business
    nếu là event mới: cập nhật dữ liệu business
COMMIT
ACK thông điệp theo giao thức nhận
~~~

Dấu xử lý thành công và cập nhật business phải được điều phối nguyên tử. Không nên ghi “đã xử lý” rồi commit riêng trước khi thực hiện business, vì lỗi sau đó có thể làm những lần nhận lại bị bỏ qua sai.

Nếu consumer commit thành công nhưng chưa ACK thì nhận lại, dấu xử lý cho phép tránh áp dụng cùng thay đổi database thêm lần nữa.

### 11.1. Kiểm tra trùng phải xử lý được đồng thời

Mẫu “query xem event đã tồn tại chưa, nếu chưa thì insert” có race condition khi hai worker nhận cùng event. Cần một ràng buộc duy nhất hoặc một cơ chế nguyên tử phù hợp và xử lý xung đột đúng transaction.

Việc xử lý lỗi unique constraint cũng phụ thuộc database và framework; không mặc định có thể bắt mọi lỗi rồi tiếp tục sử dụng transaction như chưa có gì xảy ra.

### 11.2. Tác dụng phụ bên ngoài vẫn có ranh giới lỗi khác

Nếu consumer gửi thư, gọi nhà cung cấp thanh toán hoặc cập nhật một database khác, transaction inbox local không tự bao trùm các lời gọi đó.

Có thể cần idempotency key ở hệ thống đích, một outbox phía consumer, quy trình bù hoặc cơ chế đối soát theo hợp đồng nghiệp vụ.

“Consumer idempotent” phải được phát biểu theo tác dụng phụ cụ thể. Không chỉ thêm một bảng inbox rồi tuyên bố mọi hành động ngoài database sẽ xảy ra đúng một lần.

## 12. Thứ tự cần được định nghĩa theo phạm vi

Các loại thứ tự thường bị trộn lẫn:

- Thứ tự code đăng ký local event.
- Thứ tự transaction nghiệp vụ commit.
- Thứ tự relay đọc outbox.
- Thứ tự broker lưu hoặc giao thông điệp trên một luồng.
- Thứ tự consumer hoàn tất xử lý.

Chúng không tự giống nhau.

Ví dụ, hai worker relay có thể claim hai event của cùng đơn hàng và gửi xong theo thứ tự ngược. Consumer xử lý song song cũng có thể hoàn tất event sau trước event trước.

Nếu nghiệp vụ yêu cầu thứ tự theo từng aggregate, cần thiết kế kết hợp:

- Định danh aggregate làm khóa phân luồng phù hợp.
- Sequence hoặc version có ý nghĩa theo từng aggregate.
- Cách claim không phá thứ tự cần giữ.
- Cách consumer phát hiện event đến trễ, trùng hoặc thiếu mốc.

Một timestamp có thể trùng do độ chính xác. Một ID tăng dần được cấp trước commit cũng không tự chứng minh thứ tự commit toàn cục. Không dùng riêng hai thông tin này làm bằng chứng cho mọi quan hệ trước sau.

Outbox không bắt buộc cung cấp thứ tự toàn cục giữa mọi aggregate. Chỉ yêu cầu phạm vi thứ tự mà nghiệp vụ thực sự cần.

## 13. Hợp đồng tích hợp nên tách khỏi entity persistence

Thông điệp gửi ngoài ứng dụng nên có một envelope và payload được định nghĩa rõ, ví dụ:

~~~json
{
  "eventId": "ab14b20c-8186-4e7b-b100-30fba68cce2c",
  "eventType": "order.approved",
  "schemaVersion": 1,
  "aggregateId": "b3fb4fd0-69d7-4d08-a214-1bfbc9ad471a",
  "occurredAt": "2026-03-10T09:30:00Z",
  "data": {
    "orderId": "b3fb4fd0-69d7-4d08-a214-1bfbc9ad471a",
    "approvedAt": "2026-03-10T09:30:00Z"
  }
}
~~~

Trong ví dụ JPA, các cột metadata và `payloadJson` chứa dữ liệu để relay xây envelope như vậy.

Không serialize trực tiếp một entity JPA mutable với toàn bộ quan hệ chỉ vì nó đang có sẵn:

- Entity có thể chứa proxy hoặc quan hệ lazy không còn truy cập được lúc gửi.
- Model persistence có thể thay đổi độc lập với hợp đồng tích hợp.
- Quan hệ có thể làm payload quá lớn hoặc có vòng tham chiếu.
- Dữ liệu nội bộ không cần thiết có thể bị đưa ra ngoài.

Chụp payload cần thiết khi ghi outbox cũng tránh việc relay tải trạng thái hiện tại về sau rồi vô tình gửi nội dung của một thay đổi khác.

Schema version cần có quy tắc tương thích, consumer hỗ trợ và quy trình chuyển đổi khi thay đổi kiểu hoặc ý nghĩa field. Tên class Java nội bộ không nên là hợp đồng duy nhất giữa hai hệ thống.

## 14. Polling và CDC là hai cách đưa outbox tới broker

### 14.1. Polling relay

Ứng dụng hoặc một worker truy vấn các bản ghi đến hạn rồi gửi. Cách này cho phép kiểm soát retry và tiến độ theo model của ứng dụng, nhưng cần thiết kế index, claim và chu kỳ đọc phù hợp.

Không nên tải toàn bộ bảng outbox bằng một truy vấn không giới hạn mỗi vòng. Dùng batch có kích thước phù hợp, điều kiện chọn và thứ tự rõ ràng.

### 14.2. CDC relay

Một pipeline change data capture có thể đọc thay đổi đã commit của outbox từ cơ chế database được hỗ trợ rồi chuyển tiếp tới broker.

CDC không loại bỏ việc thiết kế hợp đồng, lưu offset, xử lý trùng, giám sát độ trễ hoặc quản lý retention. Cần xét cả initial snapshot, khởi động lại và các thay đổi trạng thái vận hành của bản ghi outbox để tránh phát nhầm loại thay đổi.

### 14.3. CDC bảng nghiệp vụ khác CDC outbox

Theo dõi cột `status` đổi từ `DRAFT` sang `APPROVED` trên bảng nghiệp vụ không tự cho biết đầy đủ ý định, lý do hoặc ngữ cảnh của một event nghiệp vụ.

Outbox cho phép ứng dụng ghi rõ thông điệp tích hợp tại ranh giới hành vi. CDC có thể là phương tiện vận chuyển thông điệp đó; nó không phải lúc nào cũng là nơi suy diễn ý nghĩa business từ dữ liệu thô.

## 15. Giới hạn của abstraction chung và khả năng từng store

Spring Data Commons không tự cung cấp một outbox hoặc broker dùng thống nhất cho mọi loại kho dữ liệu.

| Môi trường | Điều cần xác nhận |
| --- | --- |
| Spring Data JPA | Entity nghiệp vụ và outbox có cùng transaction manager, database và ranh giới commit không |
| Spring Data JDBC | Các lần ghi có tham gia cùng transaction và tôn trọng ranh giới aggregate không |
| Spring Data MongoDB | Cấu hình triển khai và thao tác đang dùng có hỗ trợ ranh giới nguyên tử cần thiết không |
| Spring Data R2DBC | Các lần ghi có nằm trong cùng reactive transaction và thực sự được thực thi trong pipeline không |
| Hai store khác nhau | Có cơ chế phối hợp nào thực sự bảo đảm tính nguyên tử, hay cần thiết kế khác |

Không chuyển nguyên một ví dụ JPA sang store khác rồi giữ nguyên mọi lời khẳng định về transaction.

Trong reactive flow, việc tạo một publisher chưa đồng nghĩa các lần ghi đã được thực thi. Ngữ cảnh transaction và việc subscribe là phần của thiết kế cần kiểm chứng.

Repository, derived query, phân trang và sắp xếp giúp triển khai việc đọc outbox, nhưng chúng không tự giải quyết claim đồng thời, độ bền giao nhận hay idempotency.

Projection có thể lấy các field relay cần dùng. Một projection chỉ là hình dạng dữ liệu đọc; không phải một khóa bảo đảm quyền xử lý độc quyền bản ghi.

## 16. Quan sát và lưu giữ là một phần của khả năng phục hồi

Một outbox chưa gửi không có giá trị phục hồi nếu không có worker tiếp tục đọc hoặc lỗi không được phát hiện.

Các chỉ số hữu ích:

- Số bản ghi đang chờ và tuổi của bản ghi chờ lâu nhất.
- Số lần thử, thời điểm thử tiếp theo và nhóm lỗi.
- Số claim hết hạn hoặc được tiếp quản.
- Độ trễ từ ghi outbox tới broker xác nhận.
- Lỗi schema, thông điệp bị cách ly và tiến độ consumer.

Event không thể xử lý sau nhiều lần thử cần một quy trình rõ ràng: cách ly, điều tra, sửa nguyên nhân, phát lại hoặc xử lý nghiệp vụ phù hợp. Chỉ tăng số lần retry vô hạn không giải quyết một payload sai hợp đồng.

Retention phải phân biệt bản ghi chưa gửi, đã gửi và dữ liệu cần replay. Xóa bản ghi chưa được xử lý chỉ vì đã quá một khoảng thời gian có thể phá mục tiêu phục hồi.

Event ID và mã tương quan giúp truy vết qua service, relay, broker và consumer. Không cần ghi toàn bộ payload nhạy cảm vào mọi log chỉ để nối các bước xử lý.

## 17. Chọn cơ chế theo yêu cầu thực tế

| Yêu cầu | Hướng phù hợp để xem xét |
| --- | --- |
| Thông báo một thành phần cục bộ trong process | Application event với mô hình lỗi và thời điểm listener rõ ràng |
| Cập nhật thêm dữ liệu trong cùng database, cần commit cùng nhau | Thực hiện trong cùng transaction, trực tiếp hoặc qua listener được kiểm soát |
| Chỉ xử lý sau commit và chấp nhận mất công việc khi process lỗi | Listener sau commit có thể đủ theo hợp đồng chấp nhận đó |
| Thay đổi đã commit phải để lại công việc gửi có thể phục hồi | Outbox hoặc cơ chế bền vững tương đương phù hợp với store |
| Giao tiếp giữa các process | Broker hoặc phương tiện truyền thông ngoài process, kèm hợp đồng độ bền cần thiết |
| Consumer có thể nhận lại cùng event | Idempotency và phối hợp ACK với tác dụng phụ |
| Cần phục dựng trạng thái từ toàn bộ chuỗi event | Xem xét thiết kế event store/event sourcing; outbox tự nó chưa phải nguồn lịch sử đầy đủ |

Outbox và broker thường bổ sung cho nhau. Outbox giữ ý định tại ranh giới commit của ứng dụng; broker cung cấp khả năng giao nhận bên ngoài theo cấu hình cụ thể.

Không phải mọi local event đều cần gửi ra broker. Cũng không phải mọi event đã gửi thành công còn phải được giữ vô hạn trong bảng outbox. Thiết kế theo mục đích, độ bền và thời hạn dữ liệu đã cam kết.

## 18. Tình huống cần kiểm chứng

Các tình huống sau là tiêu chí thiết kế kiểm thử, không phải báo cáo đã chạy kiểm thử hoặc xác nhận một hệ thống broker cụ thể:

| Tình huống | Điều cần quan sát |
| --- | --- |
| Transaction nghiệp vụ commit | Có trạng thái mới và bản ghi outbox tương ứng |
| Ghi outbox lỗi | Thay đổi nghiệp vụ rollback theo hợp đồng |
| Transaction nghiệp vụ rollback | Relay không thấy một outbox đã commit cho thay đổi đó |
| Broker ngừng hoạt động | Outbox giữ công việc và relay retry theo chính sách |
| Process dừng trước lần gửi | Công việc vẫn tìm lại được sau khi khởi động |
| Broker nhận nhưng relay chưa đánh dấu tiến độ | Có thể gửi lại cùng event ID, consumer không nhân đôi tác dụng phụ đã được bảo vệ |
| Nhiều relay chạy đồng thời | Claim và việc cập nhật tiến độ tuân thủ quyền sở hữu đã thiết kế |
| Consumer commit nhưng chưa ACK | Lần nhận lại được xử lý idempotent |
| Consumer lỗi giữa ghi inbox và cập nhật business | Transaction phía nhận không để lại dấu thành công sai |
| Event đến không đúng thứ tự | Consumer áp dụng quy tắc sequence hoặc xử lý trễ theo hợp đồng |
| Schema chưa được consumer hỗ trợ | Có cách quan sát, cách ly và xử lý, không bỏ qua âm thầm |
| Local listener không có transaction phù hợp | Không suy ra outbox đã được ghi nguyên tử |

Kiểm thử unit với mock publisher có thể chứng minh code gọi một method. Nó không đủ chứng minh commit nguyên tử, độ bền broker hoặc phục hồi sau process crash.

Khi kiểm chứng transaction, cần đường persistence thực tế phù hợp. Khi kiểm chứng giao nhận, cần mô phỏng hoặc tạo lỗi tại các ranh giới gửi, xác nhận và ghi tiến độ thay vì chỉ kiểm tra luồng thành công.

## 19. Tự kiểm tra kiến thức

**Vì sao `@DomainEvents` chưa bảo đảm thông điệp ra broker?**

Vì annotation tham gia cơ chế publication của aggregate trong ứng dụng; nó không tự lưu công việc gửi hay cấu hình broker và consumer.

**Vì sao gửi ở `AFTER_COMMIT` vẫn có thể mất công việc?**

Process có thể dừng sau commit nhưng trước khi gửi, trong khi chưa có một bản ghi công việc bền vững để phục hồi.

**Outbox làm nguyên tử những gì?**

Trong ranh giới transaction đã thiết kế, nó làm thay đổi nghiệp vụ và ý định gửi cùng commit hoặc cùng rollback. Nó không tự bao trùm việc xử lý của mọi consumer.

**Tại sao vẫn cần chống trùng?**

Relay hoặc consumer có thể lỗi sau khi một bước đã thành công nhưng trước khi ghi tiến độ hoặc ACK, khiến cùng event được gửi hay giao lại.

**Có thể tạo outbox từ local listener không?**

Có thể nếu lần ghi đó thực sự tham gia cùng transaction cần bảo vệ, đúng thời điểm và đúng quy tắc rollback. Không mặc định mọi listener đều đáp ứng các điều kiện này.

**Outbox có thay broker không?**

Không tự thay. Nó lưu ý định và tiến độ gửi; broker thực hiện vai trò giao nhận ngoài process theo hợp đồng riêng.

**Điều gì quyết định chọn local event hay pipeline bền vững?**

Yêu cầu về phạm vi process, khả năng mất công việc, phục hồi sau lỗi, tính nhất quán và tác dụng phụ cần bảo vệ. Ranh giới đó phải được mô tả bằng các mốc commit và xác nhận cụ thể, thay vì chỉ bằng tên annotation hoặc tên công nghệ.

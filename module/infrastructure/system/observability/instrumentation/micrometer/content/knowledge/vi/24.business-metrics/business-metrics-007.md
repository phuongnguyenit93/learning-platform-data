# Xác định kết quả sau giao dịch hoàn tất và tránh số liệu thành công sai

Business metrics giúp quan sát kết quả nghiệp vụ như đơn hàng được tạo, thanh toán được chấp thuận, giao dịch bị từ chối hoặc báo cáo được phát hành. Để các con số có ý nghĩa, ứng dụng phải xác định chính xác thời điểm một kết quả được xem là hoàn tất. Nếu tăng Counter trước khi transaction commit, dashboard có thể báo thành công cho một giao dịch sau đó bị rollback.

Nguyên tắc quan trọng là đo đúng sự kiện nghiệp vụ đã xảy ra. Với thao tác được bảo vệ bởi transaction, chỉ ghi nhận kết quả thành công sau khi commit. Lần thử, yêu cầu được tiếp nhận, lỗi validation, lỗi kỹ thuật và kết quả hoàn tất cần có semantics riêng. Một metric tên orders.created phải phản ánh đơn hàng thực sự được tạo, không phải số lần người dùng nhấn nút hoặc số lần service bắt đầu xử lý.

## 1. Xác định rõ một business outcome

Trước khi tạo meter, hãy viết định nghĩa cho sự kiện cần đo. Định nghĩa nên trả lời:

- Sự kiện nghiệp vụ nào đã xảy ra?
- Điều kiện nào chứng minh sự kiện hoàn tất?
- Thời điểm nào hệ thống có thể khẳng định kết quả?
- Một yêu cầu retry có được tính thành một kết quả mới không?
- Có những trạng thái trung gian nào cần đo riêng?

Ví dụ với quy trình đặt hàng:

| Sự kiện | Ý nghĩa | Metric gợi ý |
|---|---|---|
| Người dùng gửi yêu cầu | Một lần thử tạo đơn | orders.create.attempts |
| Hệ thống chấp nhận đưa vào xử lý | Yêu cầu đã được nhận | orders.create.accepted |
| Transaction tạo đơn commit | Đơn hàng được tạo thành công | orders.created |
| Validation từ chối | Dữ liệu không đáp ứng quy tắc | orders.create.rejected |
| Xử lý lỗi trước commit | Thao tác không hoàn tất do lỗi | orders.create.failures |

Các metric này trả lời những câu hỏi khác nhau. Không gộp tất cả vào một Counter tên orders.created, vì khi đó số liệu thành công sẽ bị phóng đại và không thể phân biệt lỗi nghiệp vụ với lỗi kỹ thuật.

Định nghĩa sự kiện cần khớp với ngôn ngữ nghiệp vụ. Ví dụ “payment authorized” không nhất thiết đồng nghĩa “payment captured”, và “order accepted” không đồng nghĩa “order fulfilled”. Chọn tên phản ánh đúng trạng thái mà hệ thống đã xác nhận.

## 2. Không tăng Counter trước khi biết transaction đã thành công

Một lỗi phổ biến là tăng Counter ngay trong phương thức @Transactional sau khi gọi repository.save():

~~~java
@Transactional
public Order createOrder(CreateOrder command) {
    Order order = repository.save(toOrder(command));

    // Không an toàn: transaction vẫn có thể rollback sau dòng này.
    ordersCreated.increment();

    return order;
}
~~~

Repository.save() thường chỉ đưa thay đổi vào persistence context. Việc ghi dữ liệu xuống database và commit transaction có thể diễn ra sau khi method trả về, trong transaction interceptor. Nếu một thao tác tiếp theo ném exception hoặc commit thất bại, dữ liệu bị rollback nhưng Counter trong process đã tăng.

Ví dụ:

~~~text
1. createOrder() bắt đầu
2. repository.save() đưa Order vào persistence context
3. orders.created tăng lên 1
4. thao tác ghi audit gặp lỗi
5. transaction rollback
6. database không có Order mới, Counter vẫn tăng
~~~

Dashboard lúc này thể hiện một đơn hàng thành công dù database không lưu đơn hàng đó. Metric đã ghi nhận một sự kiện không xảy ra.

Với Counter mô tả kết quả sau commit, hãy đặt thao tác tăng sau ranh giới commit hoặc phát một domain event chỉ được xử lý sau commit.

## 3. Dùng TransactionalEventListener với AFTER_COMMIT

Spring cung cấp @TransactionalEventListener để xử lý event theo pha của transaction. Với business outcome chỉ hợp lệ sau commit, dùng TransactionPhase.AFTER_COMMIT.

Service tạo đơn hàng phát event trong transaction:

~~~java
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {
    private final OrderRepository repository;
    private final ApplicationEventPublisher events;

    public OrderService(
            OrderRepository repository,
            ApplicationEventPublisher events) {
        this.repository = repository;
        this.events = events;
    }

    @Transactional
    public Order createOrder(CreateOrder command) {
        Order order = repository.save(toOrder(command));

        events.publishEvent(
            new OrderCreated(order.getSalesChannel())
        );

        return order;
    }
}
~~~

Event được publish khi transaction còn đang chạy. Listener chỉ được gọi ở pha AFTER_COMMIT:

Ví dụ giả định createOrder luôn tạo một đơn hàng mới. Nếu service hỗ trợ idempotency và có thể trả về đơn hàng đã tồn tại, chỉ publish OrderCreated trong nhánh thực sự tạo mới; không phát lại event khi trả kết quả cũ cho request retry.

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class OrderBusinessMetrics {
    private final MeterRegistry registry;

    public OrderBusinessMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderCreated(OrderCreated event) {
        Counter.builder("orders.created")
            .description("Số đơn hàng đã được tạo và commit")
            .tag("channel", event.channel().metricValue())
            .register(registry)
            .increment();
    }
}
~~~

Nếu transaction commit, listener được gọi và Counter tăng. Nếu transaction rollback, listener ở pha AFTER_COMMIT không được gọi nên Counter không tăng.

Mặc định, transactional event listener yêu cầu có transaction đang hoạt động. Nếu event được publish ngoài transaction, listener không chạy khi fallbackExecution vẫn là false. Chỉ bật fallbackExecution khi nghiệp vụ thực sự muốn xử lý cả event không gắn với transaction; không bật chỉ để “cho chắc”.

Ví dụ dùng enum cho channel để tag có tập giá trị hữu hạn:

~~~java
public enum SalesChannel {
    WEB("web"),
    MOBILE("mobile"),
    PARTNER("partner");

    private final String metricValue;

    SalesChannel(String metricValue) {
        this.metricValue = metricValue;
    }

    public String metricValue() {
        return metricValue;
    }
}

public record OrderCreated(SalesChannel channel) {}
~~~

Không đưa order ID, customer ID hoặc URL vào tag. Những giá trị đó định danh từng giao dịch và có thể tạo cardinality rất cao.

## 4. Đăng ký Counter một lần và dùng tag ổn định

Trong ví dụ trên, registry được tra cứu khi listener chạy. Với tập tag nhỏ và cố định, có thể tạo trước các Counter trong constructor để bảo đảm schema metric rõ ràng:

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

import java.util.EnumMap;
import java.util.Map;

@Component
public class OrderBusinessMetrics {
    private final Map<SalesChannel, Counter> createdByChannel;

    public OrderBusinessMetrics(MeterRegistry registry) {
        Map<SalesChannel, Counter> counters =
            new EnumMap<>(SalesChannel.class);

        for (SalesChannel channel : SalesChannel.values()) {
            counters.put(
                channel,
                Counter.builder("orders.created")
                    .description("Số đơn hàng đã được tạo và commit")
                    .tag("channel", channel.metricValue())
                    .register(registry)
            );
        }

        this.createdByChannel = Map.copyOf(counters);
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderCreated(OrderCreated event) {
        createdByChannel.get(event.channel()).increment();
    }
}
~~~

Mỗi channel được đăng ký một meter identity. Khi event đến, listener chỉ cập nhật Counter tương ứng. Số lượng time series bị giới hạn bởi số enum value.

Nếu channel đến từ request tự do, hãy map nó sang enum hoặc nhóm giá trị được cho phép trước khi phát event. Không dùng raw string của request làm tag. Việc chuẩn hóa ở nguồn vừa giảm cardinality vừa giúp metric phản ánh các nhóm nghiệp vụ mà dashboard thực sự cần.

## 5. Phân biệt AFTER_COMMIT với các pha transaction khác

Spring transactional event listener hỗ trợ các pha khác nhau. Chọn pha theo ý nghĩa của event:

| Phase | Thời điểm | Ví dụ sử dụng |
|---|---|---|
| BEFORE_COMMIT | Ngay trước khi transaction commit | Kiểm tra hoặc chuẩn bị công việc cần hoàn tất trước commit |
| AFTER_COMMIT | Sau khi commit thành công | Đếm kết quả đã được lưu thành công |
| AFTER_ROLLBACK | Sau khi transaction rollback | Quan sát giao dịch bị rollback |
| AFTER_COMPLETION | Sau khi transaction kết thúc, bất kể commit hay rollback | Cleanup hoặc xử lý phụ thuộc kết quả hoàn tất |

Với Counter orders.created, AFTER_COMMIT là lựa chọn phù hợp vì metric mô tả kết quả đã được commit.

Nếu cần đo số transaction rollback, có thể dùng listener ở AFTER_ROLLBACK và một metric riêng như orders.create.rollbacks. Không tăng orders.created trong AFTER_COMPLETION vì pha này cũng chạy khi rollback.

Không dùng BEFORE_COMMIT để khẳng định dữ liệu đã được lưu thành công. Commit vẫn có thể thất bại sau callback ở pha trước commit.

## 6. Tách attempts, accepted, completed và failures

Một quy trình bất đồng bộ thường có nhiều trạng thái. Ví dụ API nhận yêu cầu xuất báo cáo và trả HTTP 202:

~~~text
Request đến
    |
    v
Tăng report.export.attempts
    |
    +---- validation lỗi ------> report.export.rejected
    |
    v
Đưa job vào queue thành công
    |
    v
Tăng report.export.accepted
    |
    v
Worker bắt đầu
    |
    v
Tạo báo cáo
    |
    +---- lỗi -----------------> report.export.failures
    |
    v
Báo cáo được lưu hoàn tất
    |
    v
Tăng report.export.completed
~~~

HTTP 202 chỉ nói rằng yêu cầu đã được chấp nhận xử lý bất đồng bộ. Nó không chứng minh báo cáo đã tạo xong. Nếu tăng report.export.completed ngay khi trả 202, metric sẽ báo thành công trước khi worker thực hiện công việc.

Có thể định nghĩa các Counter riêng:

~~~java
Counter attempts = registry.counter("report.export.attempts");
Counter accepted = registry.counter("report.export.accepted");
Counter completed = registry.counter("report.export.completed");
Counter failures = registry.counter("report.export.failures");
Counter rejected = registry.counter("report.export.rejected");
~~~

Tăng từng Counter tại đúng transition:

- attempts: khi hệ thống bắt đầu xử lý một yêu cầu.
- accepted: khi queue hoặc workflow engine xác nhận đã nhận công việc.
- completed: khi kết quả cuối cùng được xác nhận và lưu thành công.
- failures: khi công việc kết thúc do lỗi kỹ thuật hoặc lỗi xử lý theo định nghĩa đã chọn.
- rejected: khi quy tắc nghiệp vụ từ chối yêu cầu trước khi chấp nhận.

Nếu cần phân biệt failure theo nhóm, dùng tag hữu hạn như dependency, timeout, validation hoặc internal. Không dùng exception message làm tag.

## 7. Retry và idempotency: một kết quả không phải nhiều lần thử

Một request có thể được gửi lại do timeout, mất kết nối hoặc client không nhận được response. Nếu server đã commit đơn hàng nhưng response bị mất, client có thể retry cùng idempotency key.

Ví dụ:

~~~text
Lần 1: request được xử lý -> order được commit -> response bị mất
Lần 2: client retry cùng idempotency key
       -> server tìm thấy kết quả đã có
       -> trả lại order cũ
~~~

Nếu cả hai lần đều tăng orders.created, dashboard sẽ đếm hai đơn hàng trong khi database chỉ có một.

Hãy tách hai khái niệm:

- Một lần request hoặc attempt có thể được đếm mỗi lần hệ thống nhận xử lý.
- Một business outcome chỉ được đếm khi có transition mới thực sự xảy ra.

Khi xử lý idempotency, chỉ phát OrderCreated nếu transaction thực sự tạo mới kết quả. Nếu request là replay của một kết quả đã commit, trả lại kết quả cũ mà không phát business event mới.

Nếu sự kiện được truyền qua message broker, consumer có thể nhận lại message. Khi đó cần deduplication bằng event ID hoặc cơ chế idempotent tương ứng trước khi tăng business counter. Không giả định delivery exactly-once chỉ vì producer gửi một lần.

## 8. Event sau commit và transactional outbox

@TransactionalEventListener chạy trong process của ứng dụng. Nó phù hợp cho công việc phụ trợ không cần độ bền độc lập, như cập nhật Counter cục bộ sau commit.

Tuy nhiên, có một khoảng thời gian nhỏ giữa database commit và lúc listener hoàn tất. Nếu process bị dừng đột ngột trong khoảng đó, callback có thể không chạy hoặc metrics chưa kịp được scrape. In-process event không phải một hàng đợi bền vững.

Khi cần chuyển business event sang hệ thống khác với độ tin cậy cao, cân nhắc transactional outbox:

~~~text
Một database transaction
    |
    +--> INSERT Order
    |
    +--> INSERT OutboxEvent(OrderCreated)
    |
    v
COMMIT
    |
    v
Outbox publisher đọc event chưa gửi
    |
    v
Message broker
    |
    v
Consumer xử lý idempotent
    |
    v
Business metrics / downstream workflow
~~~

Order và OutboxEvent được ghi trong cùng transaction. Nếu rollback, cả hai đều không tồn tại. Nếu commit, publisher có thể gửi lại event cho đến khi được xác nhận theo chính sách của hệ thống.

Outbox thường cung cấp delivery at-least-once, nên consumer vẫn phải xử lý duplicate. Khi consumer đã xử lý event duy nhất theo event ID, nó mới cập nhật business metric hoặc trạng thái tổng hợp.

Không cần dùng outbox chỉ để tăng một Counter trong cùng process nếu sai số nhỏ có thể chấp nhận. Hãy dùng outbox khi business event phải được truyền bền vững tới hệ thống khác hoặc khi workflow cần phục hồi sau crash.

## 9. Metrics không phải sổ cái nghiệp vụ

Micrometer Counter là số đếm trong vòng đời registry/process. Nó có thể reset khi ứng dụng restart, bị mất nếu process dừng trước lần scrape, hoặc không phản ánh đầy đủ event nếu export backend gặp sự cố.

Vì vậy:

- Dùng Counter để quan sát xu hướng, throughput, tỷ lệ lỗi và cảnh báo vận hành.
- Dùng database, ledger hoặc event store làm nguồn dữ liệu có thẩm quyền cho số lượng giao dịch và doanh thu.
- Dùng truy vấn hoặc báo cáo đối soát để xác nhận số liệu tài chính.
- Dùng outbox và consumer idempotent khi cần luồng event bền vững.

Ví dụ, orders.created_total của Prometheus có thể thấp hơn số đơn trong database do process restart hoặc scrape gián đoạn. Đây không nhất thiết là lỗi nghiệp vụ. Metric phục vụ quan sát, không thay thế báo cáo tài chính hoặc dữ liệu giao dịch chính thức.

Nếu cần so sánh, hãy xác định khoảng thời gian, phạm vi instance và semantics của từng nguồn. Không lấy giá trị Counter hiện tại làm tổng số đơn hàng từ trước đến nay.

## 10. Kiểm thử commit và rollback

Kiểm thử quan trọng nhất là xác nhận Counter chỉ tăng khi transaction commit. Có thể dùng TransactionTemplate để điều khiển kết quả transaction:

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest
class OrderBusinessMetricsTest {

    @Autowired
    ApplicationEventPublisher events;

    @Autowired
    MeterRegistry registry;

    @Autowired
    PlatformTransactionManager transactionManager;

    @Test
    void incrementsOnlyAfterCommit() {
        TransactionTemplate tx =
            new TransactionTemplate(transactionManager);

        Counter created = registry.get("orders.created")
            .tag("channel", "web")
            .counter();

        double before = created.count();

        tx.execute(status -> {
            events.publishEvent(new OrderCreated(SalesChannel.WEB));
            return null;
        });

        assertEquals(before + 1.0, created.count());
    }

    @Test
    void doesNotIncrementAfterRollback() {
        TransactionTemplate tx =
            new TransactionTemplate(transactionManager);

        Counter created = registry.get("orders.created")
            .tag("channel", "web")
            .counter();

        double before = created.count();

        tx.execute(status -> {
            events.publishEvent(new OrderCreated(SalesChannel.WEB));
            status.setRollbackOnly();
            return null;
        });

        assertEquals(before, created.count());
    }
}
~~~

Test này giả sử OrderBusinessMetrics và các Counter đã được tạo trong Spring context, TransactionManager hoạt động và event được publish bên trong transaction. Với test commit, listener AFTER_COMMIT được gọi. Với test rollback, listener không chạy và giá trị Counter giữ nguyên.

Nên bổ sung test cho các trường hợp:

- Event được phát khi transaction không tồn tại và fallbackExecution mặc định không bật.
- Request retry cùng idempotency key không phát business event lần thứ hai.
- Validation rejection tăng rejected nhưng không tăng created.
- Lỗi trước commit không tăng created.
- Nhiều transaction commit đồng thời không làm mất lần tăng.
- Tag channel luôn thuộc tập giá trị cho phép.

## 11. Xử lý lỗi trong listener sau commit

Listener AFTER_COMMIT chạy sau khi dữ liệu đã commit. Nếu listener ném exception, transaction không thể rollback lại dữ liệu đã commit. Tùy cách exception lan truyền qua transaction synchronization và caller, request có thể nhận lỗi dù đơn hàng đã được lưu thành công.

Điều này nguy hiểm nếu client hiểu response lỗi là giao dịch chưa thành công rồi retry. Vì vậy, listener đo metrics nên ngắn, ít phụ thuộc và không thực hiện nghiệp vụ có thể thất bại.

Đối với thao tác tăng Counter trong registry cục bộ, giữ logic đơn giản và không gọi database hoặc network. Nếu listener cần gửi message, gọi dịch vụ bên ngoài hoặc thực hiện công việc có thể lỗi, hãy dùng outbox hoặc cơ chế retry bền vững thay vì đặt toàn bộ công việc trong callback AFTER_COMMIT.

Không bắt mọi exception rồi âm thầm bỏ qua nếu điều đó che giấu lỗi nghiêm trọng. Hãy định nghĩa cách ghi log, retry hoặc phát cảnh báo phù hợp, đồng thời bảo đảm lỗi phụ trợ không khiến caller hiểu sai trạng thái transaction đã commit.

## 12. Các lỗi thường gặp

- **Tăng Counter ngay sau repository.save():** save chưa đồng nghĩa transaction đã commit.
- **Dùng một metric cho attempt và success:** số liệu thành công bị phóng đại.
- **Tăng Counter trước validation:** request bị từ chối vẫn bị đếm là thành công.
- **Đếm mỗi lần retry thành một business outcome:** một giao dịch có thể bị tính nhiều lần.
- **Dùng HTTP 200 hoặc 202 làm bằng chứng hoàn tất:** response status không nhất thiết tương đương trạng thái nghiệp vụ cuối.
- **Dùng AFTER_COMPLETION để đếm success:** pha này cũng chạy sau rollback.
- **Bật fallbackExecution tùy tiện:** event ngoài transaction có thể được xử lý dù chưa có commit boundary.
- **Cho rằng in-process event bền vững:** process crash có thể làm mất callback hoặc dữ liệu metrics chưa scrape.
- **Dùng metrics làm sổ cái:** Counter có thể reset hoặc mất mẫu và không bảo đảm đối soát.
- **Đưa ID hoặc exception message vào tag:** cardinality tăng và có thể lộ dữ liệu nhạy cảm.
- **Đặt logic network trong AFTER_COMMIT listener:** lỗi phụ trợ có thể làm caller hiểu nhầm kết quả đã commit.
- **Không kiểm thử rollback:** dễ bỏ sót Counter tăng sai khi transaction thất bại.

## 13. Checklist xác định business outcome

- [ ] Định nghĩa chính xác sự kiện nghiệp vụ được tính là thành công.
- [ ] Phân biệt attempt, accepted, completed, rejected và failure.
- [ ] Chỉ tăng success Counter sau khi transaction commit.
- [ ] Dùng AFTER_COMMIT cho event cần xác nhận commit.
- [ ] Không dùng AFTER_COMPLETION thay cho AFTER_COMMIT.
- [ ] Giữ fallbackExecution mặc định nếu event phải gắn với transaction.
- [ ] Chỉ phát event khi có business state transition mới.
- [ ] Xử lý retry bằng idempotency key hoặc event ID.
- [ ] Dùng tag có tập giá trị hữu hạn và chuẩn hóa ở nguồn.
- [ ] Giữ listener metrics ngắn và không phụ thuộc network.
- [ ] Dùng transactional outbox khi cần event bền vững tới hệ thống khác.
- [ ] Dùng database/ledger làm nguồn dữ liệu đối soát chính thức.
- [ ] Kiểm thử cả commit, rollback, retry và rejection.
- [ ] Theo dõi Counter như tín hiệu vận hành, không xem là sổ cái.

Một business metric chỉ có ý nghĩa khi nó được tăng tại đúng thời điểm kết quả nghiệp vụ được xác nhận. Với thao tác có transaction, phát domain event trong transaction và xử lý bằng AFTER_COMMIT giúp tránh ghi nhận thành công cho dữ liệu đã rollback. Tách riêng attempt, accepted, completed và failure; kết hợp idempotency, tag hữu hạn và nguồn dữ liệu có thẩm quyền để dashboard phản ánh đúng hoạt động mà không biến metrics thành sổ cái giao dịch.


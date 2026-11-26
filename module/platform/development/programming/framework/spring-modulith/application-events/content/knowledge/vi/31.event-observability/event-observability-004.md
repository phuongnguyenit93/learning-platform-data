# Metric số lượng event

*Đo lường lưu lượng, kết quả xử lý và backlog của application event trong Spring Modulith*

Khi nhiều module giao tiếp qua application event, nhóm vận hành cần biết mỗi luồng đang phát bao nhiêu event, listener xử lý được bao nhiêu, có bao nhiêu lần retry và publication nào đang bị tồn đọng. **Metric số lượng event** cung cấp số liệu tổng hợp để quan sát lưu lượng và phát hiện bất thường trước khi người dùng nhận thấy dữ liệu chậm hoặc quy trình nghiệp vụ bị đình trệ.

Một con số “số event” có thể mang nhiều ý nghĩa. Một event nghiệp vụ được phát một lần có thể được giao cho nhiều listener; một listener có thể nhận lại cùng event nhiều lần; một lần xử lý có thể thất bại rồi retry. Vì vậy, cần định nghĩa rõ đang đếm event được tạo, publication được gửi, lần giao, lần xử lý hay event duy nhất đã hoàn tất. Nếu không tách các khái niệm này, dashboard có thể tăng số liệu dù không có thêm giao dịch nghiệp vụ mới.

## 1. Xác định chính xác thứ cần đếm

Một luồng event trong ứng dụng thường có nhiều điểm quan sát:

1. **Created / published:** module nguồn tạo và phát application event.
2. **Publication:** registry ghi nhận việc giao event đến một listener hoặc externalization target.
3. **Delivery attempt:** listener hoặc adapter bắt đầu một lần xử lý/gửi.
4. **Processed:** một lần xử lý hoàn tất thành công.
5. **Failed:** một lần xử lý kết thúc với lỗi.
6. **Retried / redelivered:** event được giao lại sau một lần lỗi hoặc trạng thái chưa hoàn tất.
7. **Duplicate skipped:** handler nhận event đã được áp dụng và bỏ qua nhờ idempotency.
8. **Dead-lettered:** message được chuyển sang luồng cần điều tra hoặc xử lý thủ công.

Các số liệu này không thể thay thế lẫn nhau. Ví dụ, một `OrderCompleted` có thể tạo một event nhưng ba publication cho ba listener. Nếu listener thông báo retry hai lần rồi thành công, hệ thống có một event nghiệp vụ, một số publication theo listener, nhiều delivery attempt và một lần xử lý thành công cuối cùng cho listener đó.

| Tên số liệu | Đơn vị đếm | Câu hỏi trả lời |
|---|---|---|
| Event created | Lần phát event ở module nguồn | Module đang tạo bao nhiêu event? |
| Publication created | Publication theo listener/target | Có bao nhiêu công việc giao được registry ghi nhận? |
| Delivery attempts | Số lần listener/adapter được gọi | Hệ thống đang phải thử bao nhiêu lần? |
| Processing successes | Số lần xử lý thành công | Consumer hoàn tất được bao nhiêu lần xử lý? |
| Processing failures | Số lần xử lý thất bại | Có bao nhiêu lần xử lý gặp lỗi? |
| Duplicate skipped | Số lần nhận trùng được bỏ qua | Retry/redelivery tạo ra bao nhiêu lần trùng? |
| Incomplete publications | Số publication hiện còn chưa hoàn tất | Backlog hiện tại là bao nhiêu? |

Hãy ghi định nghĩa và điểm tăng metric trong tài liệu vận hành. Ví dụ, `processed` có thể được định nghĩa là một lần listener hoàn tất thành công, không phải số event ID duy nhất trong toàn hệ thống.

## 2. Counter, gauge và timer

Micrometer cung cấp các loại meter phù hợp với những câu hỏi khác nhau:

- **Counter:** số lần một sự kiện đo lường xảy ra. Giá trị tăng đơn điệu trong vòng đời meter; thường dùng cho event created, delivery attempts, success, failure, retry và duplicate.
- **Gauge:** giá trị hiện tại có thể tăng hoặc giảm. Dùng cho số publication chưa hoàn tất, queue depth, số worker đang hoạt động hoặc số event đang ở trạng thái `PROCESSING`.
- **Timer:** đo thời gian của một thao tác và đồng thời ghi số lần quan sát. Dùng cho thời gian listener xử lý, độ trễ giao event hoặc thời gian chờ publication.
- **Distribution summary:** phân bố một đại lượng không phải thời gian, ví dụ kích thước payload nếu cần quan sát giới hạn message.

Counter phù hợp với tổng số lần xử lý trong một khoảng thời gian; gauge phù hợp với backlog tại thời điểm hiện tại. Không dùng counter để biểu diễn số publication đang chờ vì giá trị đó cần giảm khi publication hoàn tất. Không dùng gauge cho tổng số lần event đã phát vì nó không biểu diễn lịch sử tích lũy.

Timer đã có số lần ghi nhận thông qua `count`. Nếu mục tiêu chỉ là đếm số lần xử lý và đo thời gian, không cần tạo thêm một counter trùng ý nghĩa mà không có lý do rõ ràng. Hãy tránh tạo nhiều metric khác tên nhưng cùng một định nghĩa khiến dashboard khó đối chiếu.

## 3. Bộ metric cơ bản cho event flow

Một bộ metric thực dụng có thể bắt đầu với các nhóm sau:

| Metric logic | Loại | Tag gợi ý | Ý nghĩa |
|---|---|---|---|
| `application.events.created` | Counter | `event_type`, `module` | Event được module nguồn phát |
| `application.events.delivery.attempts` | Counter | `event_type`, `listener`, `target` | Số lần listener hoặc adapter được gọi |
| `application.events.processing` | Timer | `event_type`, `listener`, `outcome` | Số lần và thời gian xử lý |
| `application.events.processing.failures` | Counter | `event_type`, `listener`, `error_category` | Số lần xử lý thất bại theo nhóm lỗi |
| `application.events.retries` | Counter | `event_type`, `listener`, `retry_reason` | Số lần thử lại |
| `application.events.duplicates` | Counter | `event_type`, `consumer` | Số lần handler bỏ qua event đã xử lý |
| `application.events.publications.incomplete` | Gauge | `listener` hoặc `target` | Số publication hiện chưa hoàn tất |
| `application.events.publication.oldest.age` | Gauge hoặc Timer-derived | `listener` hoặc `target` | Tuổi publication chưa hoàn tất lâu nhất |
| `application.events.dead.lettered` | Counter | `event_type`, `destination` | Số message chuyển sang dead-letter |

Đây là tên metric logic để thống nhất trong ứng dụng. Micrometer và registry xuất metric có thể chuẩn hóa tên khác nhau theo backend; hãy kiểm tra tên thực tế trên endpoint scrape hoặc hệ thống giám sát. Không cần triển khai toàn bộ ngay từ đầu. Chọn metric giúp trả lời câu hỏi vận hành quan trọng nhất rồi mở rộng khi có nhu cầu.

## 4. Đếm event được phát ở module nguồn

Event created nên tăng tại một điểm có định nghĩa rõ ràng trong module nguồn. Ví dụ, sau khi use case quyết định phát event, ứng dụng ghi nhận metric theo event type và module. Metric này cho biết lưu lượng nghiệp vụ đi vào event flow, nhưng không chứng minh listener đã nhận hoặc xử lý event.

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

@Component
class ApplicationEventMetrics {

    private final MeterRegistry registry;

    ApplicationEventMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    void eventCreated(String eventType, String module) {
        Counter.builder("application.events.created")
            .description("Number of application events emitted by a module")
            .tag("event_type", eventType)
            .tag("module", module)
            .register(registry)
            .increment();
    }
}
```

Trong ứng dụng thực tế, `eventType` và `module` nên đến từ danh sách tên đã kiểm soát, chẳng hạn tên event contract và tên module cố định. Không lấy tên class được tạo động, tên tenant hoặc dữ liệu request làm tag nếu tập giá trị có thể tăng không giới hạn.

Metric được cập nhật trong bộ nhớ không tham gia transaction cơ sở dữ liệu. Nếu transaction rollback sau khi counter tăng, số đo có thể vẫn ghi nhận lần phát đã thử nhưng nghiệp vụ không commit. Vì vậy, cần đặt tên và định nghĩa đúng điểm đo, ví dụ `events.publish.requested` nếu đo trước commit hoặc `events.created` tại điểm đã xác nhận nghiệp vụ commit. Nếu cần số liệu kiểm toán chính xác, hãy lấy từ dữ liệu bền vững như event store, outbox hoặc bảng nghiệp vụ; metric phục vụ quan sát tổng hợp.

## 5. Đếm lần giao và kết quả xử lý của listener

Một event có thể được gửi đến nhiều listener. Nên đếm delivery attempt và outcome theo listener để phát hiện module nào đang chậm hoặc lỗi. Counter attempt tăng khi listener bắt đầu một lần xử lý; counter success hoặc failure tăng khi đã biết kết quả của lần đó.

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

@Component
class ListenerMetrics {

    private final MeterRegistry registry;

    ListenerMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    void attempt(String eventType, String listener) {
        counter("application.events.delivery.attempts", eventType, listener, "attempt")
            .increment();
    }

    void outcome(String eventType, String listener, String outcome) {
        counter("application.events.processing.outcomes", eventType, listener, outcome)
            .increment();
    }

    private Counter counter(
            String name, String eventType, String listener, String outcome) {
        return Counter.builder(name)
            .tag("event_type", eventType)
            .tag("listener", listener)
            .tag("outcome", outcome)
            .register(registry);
    }
}
```

`outcome` cần là tập giá trị hữu hạn như `success`, `failure`, `duplicate` hoặc `rejected`. Đoạn code minh họa API Micrometer; trong ứng dụng nên bọc instrumentation ở thành phần dùng chung hoặc observation convention để mọi listener ghi metric nhất quán. Nếu đặt metric trong listener, hãy tăng `success` sau khi logic xử lý hoàn tất thành công. Khi exception được ném ra, ghi nhận `failure` ở lớp bao quanh có thể quan sát kết quả cuối cùng.

Với `@ApplicationModuleListener`, có thể dùng wrapper/interceptor hoặc thành phần instrumentation phù hợp với cơ chế listener của phiên bản Spring Modulith đang dùng. Tránh sao chép logic metric thủ công khác nhau ở mọi listener vì dễ bỏ sót một nhánh hoặc đếm một lần xử lý hai lần.

## 6. Đo thời gian xử lý và số lần qua Timer

Số lượng event cho biết lưu lượng; thời gian xử lý cho biết consumer có theo kịp hay không. Timer ghi cả số lần quan sát và phân bố thời gian:

```java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.time.Duration;

class EventProcessingTimer {

    private final MeterRegistry registry;

    EventProcessingTimer(MeterRegistry registry) {
        this.registry = registry;
    }

    void record(
            String eventType,
            String listener,
            String outcome,
            Duration elapsed) {
        Timer.builder("application.events.processing")
            .tag("event_type", eventType)
            .tag("listener", listener)
            .tag("outcome", outcome)
            .register(registry)
            .record(elapsed);
    }
}
```

Từ Timer có thể quan sát count, tổng thời gian và các percentile/histogram nếu cấu hình hỗ trợ. Percentile cần được cấu hình có chủ đích vì histogram tạo thêm chuỗi thời gian và chi phí lưu trữ. Dùng p50, p95 hoặc p99 khi cần phát hiện đuôi phân bố chậm; trung bình đơn thuần có thể che giấu một nhóm nhỏ event xử lý rất lâu.

Định nghĩa rõ khoảng thời gian được đo: từ lúc listener bắt đầu đến khi handler hoàn tất, hay từ lúc event được tạo đến lúc consumer xử lý xong. Hai khoảng này khác nhau. Nếu cần đo end-to-end latency, phải có timestamp nguồn và timestamp xử lý với đồng hồ được đồng bộ; Timer cục bộ chỉ đo thời gian trong tiến trình.

## 7. Đo backlog bằng Gauge

Backlog là số publication hoặc message đang chờ xử lý tại thời điểm đo. Có thể biểu diễn bằng gauge:

```java
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.stereotype.Component;

@Component
class PublicationBacklogMetrics {

    private final AtomicLong incompleteCount = new AtomicLong();

    PublicationBacklogMetrics(MeterRegistry registry) {
        Gauge.builder(
                "application.events.publications.incomplete",
                incompleteCount,
                AtomicLong::doubleValue)
            .description("Current number of incomplete event publications")
            .register(registry);
    }

    void updateSnapshot(long count) {
        incompleteCount.set(count);
    }
}
```

`updateSnapshot` cần được gọi từ cơ chế cập nhật trạng thái hoặc tác vụ lấy snapshot phù hợp. Giữ tham chiếu đến đối tượng được gauge quan sát trong suốt vòng đời bean; nếu đối tượng bị thu gom, gauge có thể không còn giá trị. Không chạy truy vấn database nặng mỗi lần scrape metric. Có thể cập nhật snapshot định kỳ hoặc khi trạng thái publication thay đổi, tùy lưu lượng và chi phí truy vấn.

Với Spring Modulith, event publication registry cung cấp trạng thái publication chưa hoàn tất. Cách truy vấn hoặc tích hợp trạng thái đó thành gauge phụ thuộc phiên bản và persistence implementation. Hãy dùng API/repository được hỗ trợ trong ứng dụng và đo theo listener hoặc externalization target; không giả định có sẵn một metric built-in với tên cố định ở mọi phiên bản.

Backlog count nên đi kèm tuổi publication lâu nhất. Một backlog nhỏ nhưng tồn tại nhiều giờ có thể nghiêm trọng hơn backlog lớn đang được xử lý nhanh. Nếu dùng broker như Kafka hoặc RabbitMQ, kết hợp gauge của publication registry với consumer lag, queue depth hoặc unacknowledged messages của broker để thấy toàn bộ đường đi.

## 8. Chọn tag có cardinality thấp

Mỗi tổ hợp tag tạo một time series riêng. Nếu tag có quá nhiều giá trị, số chuỗi thời gian tăng nhanh, làm tốn bộ nhớ, dung lượng lưu trữ và chi phí truy vấn. Đây là vấn đề cardinality.

Tag thường phù hợp:

- `module`: tên module cố định như `orders`, `billing`, `reporting`.
- `event_type`: tên event contract thuộc danh sách hữu hạn.
- `listener`: tên listener cố định trong ứng dụng.
- `outcome`: tập trạng thái nhỏ như `success`, `failure`, `duplicate`.
- `error_category`: nhóm lỗi chuẩn hóa như `timeout`, `connection`, `serialization`, `business`.
- `destination`: tên topic/queue/target được cấu hình trước.

Không dùng các giá trị sau làm tag metric:

- `eventId`, `aggregateId`, `orderId`, `customerId` hoặc `correlationId`.
- URL đầy đủ, exception message hoặc stack trace.
- Timestamp, request ID, email, tenant ID có tập giá trị lớn.
- Payload hoặc giá trị do người dùng gửi lên.

Các định danh cụ thể nên nằm trong log hoặc trace có kiểm soát, không nằm trong label metric. Khi cần điều tra một event, dùng event ID trong log và liên kết trace; metric chỉ cho biết xu hướng tổng hợp.

## 9. Tính đúng của số đếm khi retry và duplicate

Counter đo số lần instrumentation được gọi, không tự biết một event ID có duy nhất hay không. Nếu listener được gọi ba lần và hai lần đầu thất bại, `delivery.attempts` tăng ba; `processing.successes` tăng một; `processing.failures` tăng hai. Nếu lần cuối handler phát hiện event đã được áp dụng và bỏ qua, có thể tăng `duplicates` theo định nghĩa riêng.

Không cộng `success + retry + failure` rồi gọi đó là số event duy nhất. Retry là một lần thử, không phải một event mới. Một event có thể tạo nhiều publication cho nhiều listener, nên tổng delivery attempts cũng không bằng số event được phát ở module nguồn.

Counter trong tiến trình cũng có thể mất giá trị khi ứng dụng restart. Backend giám sát thường xử lý counter reset khi tính rate, nhưng số liệu không phải sổ cái bền vững. Nếu cần biết chính xác có bao nhiêu event nghiệp vụ duy nhất đã commit trong một kỳ, hãy truy vấn nguồn dữ liệu bền vững có event ID và quy tắc loại trùng.

## 10. Tính rate, error ratio và throughput

Số đếm tích lũy hữu ích cho tổng quan, nhưng vận hành thường cần tốc độ thay đổi theo thời gian. Với counter, có thể tính:

- **Event rate:** số lần event được phát hoặc xử lý mỗi giây/phút.
- **Failure rate:** số lần xử lý thất bại trong một đơn vị thời gian.
- **Retry rate:** số lần retry trong một đơn vị thời gian.
- **Success ratio:** số lần thành công chia cho tổng số lần xử lý có kết quả trong cùng cửa sổ.
- **Duplicate ratio:** số lần duplicate bị bỏ qua chia cho tổng số delivery attempt.

Ví dụ truy vấn Prometheus minh họa:

```promql
sum(rate(application_events_delivery_attempts_total[5m]))
```

Tốc độ thất bại có thể được tính tương tự trên counter failure. Error ratio cần dùng cùng phạm vi label và cùng cửa sổ thời gian ở tử số/mẫu số. Nếu không có attempt hoặc outcome trong cửa sổ, kết quả có thể không xác định; dashboard cần xử lý trường hợp không có dữ liệu thay vì hiển thị 0% như thể hệ thống khỏe.

Tên metric thực tế do Micrometer registry và backend chuẩn hóa. Ví dụ PromQL chỉ minh họa cách tính trên counter được export dưới tên tương ứng; hãy kiểm tra endpoint metrics của ứng dụng trước khi dùng trong dashboard.

## 11. Kết hợp metric với Event Publication Registry

Event publication registry theo dõi trạng thái giao event đến transactional listener hoặc externalization target. Có thể dùng dữ liệu này để xây dựng các metric về publication:

- Số publication được tạo trong khoảng thời gian.
- Số publication hiện chưa hoàn tất.
- Số publication hoàn tất và số publication bị đánh dấu thất bại theo cơ chế ứng dụng.
- Tuổi publication chưa hoàn tất lâu nhất.
- Số lần resubmit hoặc số publication hoàn tất sau resubmit nếu ứng dụng ghi nhận được.

Các metric cần phản ánh đúng lifecycle của registry. Không coi một publication chưa hoàn tất là một event nghiệp vụ mới. Một event có nhiều listener có thể có nhiều publication; trạng thái hoàn tất của từng listener độc lập.

Spring Modulith và persistence implementation có thể thay đổi API truy cập hoặc cách cấu hình registry theo phiên bản. Hãy tạo adapter metrics dựa trên API được hỗ trợ trong phiên bản dự án. Không đọc trực tiếp bảng nội bộ hoặc phụ thuộc vào tên cột của implementation nếu không có hợp đồng ổn định.

Metric registry cũng không thay thế dữ liệu chi tiết phục vụ điều tra. Khi gauge backlog tăng, dùng log, trace và thông tin publication có định danh để tìm listener hoặc event gây nghẽn. Không thêm event ID vào tag chỉ để drill-down.

## 12. Dashboard và alert từ metric số lượng

Dashboard nên sắp xếp số liệu theo câu hỏi vận hành:

1. **Lưu lượng:** event created, delivery attempts và processed theo module/event type.
2. **Kết quả:** success, failure, retry, duplicate và dead-letter theo listener.
3. **Tồn đọng:** incomplete publications, queue depth, consumer lag và tuổi publication lâu nhất.
4. **Hiệu năng:** processing duration p50/p95/p99 và end-to-end latency nếu đo được.
5. **So sánh:** tốc độ phát so với tốc độ xử lý để biết consumer có theo kịp producer không.

Alert có thể kích hoạt khi backlog tăng liên tục, tuổi publication vượt SLO, failure ratio cao trong nhiều cửa sổ hoặc dead-letter xuất hiện ở luồng trọng yếu. Đừng alert chỉ vì counter failure tăng một đơn vị; cần xét tỷ lệ, độ kéo dài và tác động nghiệp vụ.

Một luồng có thể phát ít event theo mùa hoặc không có traffic vào ban đêm. Alert “không có event” chỉ hợp lý khi có kỳ vọng lưu lượng rõ ràng, chẳng hạn batch bắt buộc phải chạy mỗi giờ. Với luồng không có lịch cố định, absence of traffic không đồng nghĩa lỗi.

## 13. Kiểm thử metric

Kiểm thử instrumentation giúp tránh đếm thiếu, đếm trùng hoặc tạo tag không kiểm soát. Với Micrometer có thể dùng `SimpleMeterRegistry` trong unit test:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

class ApplicationEventMetricsTest {

    @Test
    void incrementsCreatedCounterForEventType() {
        var registry = new SimpleMeterRegistry();
        var metrics = new ApplicationEventMetrics(registry);

        metrics.eventCreated("OrderCompleted", "orders");
        metrics.eventCreated("OrderCompleted", "orders");

        double count = registry.get("application.events.created")
            .tag("event_type", "OrderCompleted")
            .tag("module", "orders")
            .counter()
            .count();

        assertEquals(2.0, count);
    }
}
```

Các test nên xác nhận:

- Counter tăng đúng tại điểm event created, attempt, success, failure, retry và duplicate.
- Retry làm tăng attempt nhưng không bị tính thành event created mới.
- Timer ghi nhận count và duration đúng outcome.
- Gauge phản ánh số publication hiện tại và giảm khi publication hoàn tất.
- Tag chỉ dùng tập giá trị được kiểm soát; event ID không xuất hiện trong tag.
- Một listener không ghi metric hai lần cho cùng một outcome do instrumentation bị đặt ở nhiều lớp.
- Metric export có tên và tag đúng trên registry/backend đang dùng.

Unit test với `SimpleMeterRegistry` kiểm tra logic instrumentation. Integration test nên xác nhận metric được export trong cấu hình Spring Boot Actuator/registry thực tế và các dashboard query dùng đúng tên đã chuẩn hóa.

## 14. Quy trình triển khai và vận hành

Khi bổ sung metric cho một event flow, hãy bắt đầu bằng việc thống nhất định nghĩa số đếm với nhóm sở hữu module và nhóm vận hành. Chọn một vài metric cốt lõi như created, delivery attempts, processing outcomes và incomplete publications. Đặt tag có cardinality thấp, sau đó xác nhận số liệu trên dashboard bằng một kịch bản phát event có kiểm soát.

Khi thấy delivery attempts tăng nhưng success không tăng tương ứng, kiểm tra listener failure và retry. Khi event created ổn định nhưng backlog tăng, consumer có thể chậm hoặc dependency đang lỗi. Khi failure giảm nhưng backlog vẫn cao, cần xem tốc độ xử lý hiện tại có đủ để bắt kịp producer hay không. Khi duplicate tăng, kiểm tra retry/redelivery và idempotency; duplicate được bỏ qua đúng cách có thể là hành vi an toàn, nhưng mức tăng bất thường có thể báo hiệu broker hoặc consumer đang chập chờn.

Không dùng metric để tự động xóa publication hoặc bỏ qua event. Metric chỉ cung cấp tín hiệu; mọi hành động retry, resubmit, replay hoặc sửa trạng thái phải theo quy trình vận hành có kiểm soát và giữ dấu vết phục vụ đối soát.

## 15. Những điểm cần nhớ

- Phân biệt event created, publication, delivery attempt, processing outcome, retry, duplicate và backlog trước khi đặt tên metric.
- Counter đo số lần xảy ra; gauge đo giá trị hiện tại; timer đo thời gian và cũng cung cấp count.
- Đo số lần listener xử lý theo event type và listener để tìm luồng nghẽn.
- Dùng gauge cho publication chưa hoàn tất, queue depth và consumer lag; theo dõi thêm tuổi backlog.
- Giữ tag cardinality thấp; không đưa event ID, aggregate ID, correlation ID hoặc payload vào tag.
- Counter phục vụ quan sát tổng hợp, không phải sổ cái chính xác cho số event nghiệp vụ duy nhất.
- Kết hợp metric với Event Publication Registry, log và trace để theo dõi và điều tra event flow.

Khi định nghĩa rõ từng loại số đếm, đặt instrumentation ở đúng điểm xử lý và giữ tag có cardinality thấp, metric giúp nhóm vận hành hiểu lưu lượng event, nhận ra consumer tụt lại và phát hiện retry bất thường. Kết hợp Counter, Gauge, Timer với trạng thái publication của Spring Modulith tạo nền tảng quan sát đáng tin cậy cho giao tiếp giữa các module.

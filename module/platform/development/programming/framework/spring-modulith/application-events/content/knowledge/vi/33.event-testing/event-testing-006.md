# Kiểm thử retry

Trong module SPRING_MODULITH_APPLICATION_EVENTS, application events giúp các module giao tiếp qua sự kiện và giảm phụ thuộc trực tiếp. Khi listener xử lý event gặp lỗi tạm thời, ứng dụng cần có khả năng thử lại mà không làm mất dấu công việc hoặc tạo side effect trùng lặp. Kiểm thử retry phải chứng minh được cả ba điều: lỗi được ghi nhận đúng, event có thể được giao lại, và lần xử lý thành công không làm nghiệp vụ bị áp dụng nhiều lần.

Với Spring Modulith, Event Publication Registry theo dõi publication tới từng listener. Nếu listener chưa hoàn tất, publication có thể còn ở trạng thái incomplete để ứng dụng phục hồi hoặc resubmit theo chính sách. Registry cung cấp thông tin và cơ chế giao lại; lịch retry, backoff, giới hạn số lần, cảnh báo và xử lý lỗi cuối cùng vẫn cần được thiết kế ở tầng ứng dụng.

## 1. Cần kiểm thử điều gì?

Một chiến lược retry đáng tin cậy cần xác minh các hành vi:

- Listener được gọi khi application event được publish.
- Khi listener lỗi, publication không bị đánh dấu hoàn tất.
- Ứng dụng có thể chọn publication phù hợp để resubmit.
- Lần giao lại gọi listener với cùng event và cùng định danh.
- Khi listener thành công, publication được đánh dấu hoàn tất.
- Lỗi lặp lại không tạo vòng retry vô hạn ngoài chính sách.
- Side effect không bị nhân đôi khi cùng event được giao nhiều lần.
- Publication pending vẫn được phục hồi sau khi ứng dụng khởi động lại nếu registry dùng persistence bền vững.

Phân biệt retry lời gọi dependency bên trong listener với retry publication của Spring Modulith. Spring Retry hoặc Resilience4j có thể thử lại một HTTP call trong một lần listener chạy. Event Publication Registry theo dõi việc giao application event tới listener và cho phép resubmit publication chưa hoàn tất. Hai cơ chế có thể cùng dùng, nhưng cần retry budget tổng để tránh số lần gọi tăng theo cấp số nhân.

## 2. Vòng đời publication khi listener lỗi

Với listener được quản lý bởi Spring Modulith, publication được đăng ký cho listener. Khi listener hoàn tất, publication được đánh dấu completed. Nếu listener ném exception, publication chưa hoàn tất có thể được giữ lại trong registry để phục hồi.

~~~mermaid
sequenceDiagram
    participant P as Publisher
    participant R as Event Publication Registry
    participant L as Listener
    P->>R: Publish event và đăng ký publication
    R->>L: Giao event lần đầu
    L-->>R: Exception
    Note over R: Publication còn incomplete
    R->>L: Resubmit cùng publication
    L-->>R: Xử lý thành công
    R->>R: Đánh dấu completed
~~~

Đừng kiểm tra retry chỉ bằng số lần listener được gọi. Cần xác minh trạng thái publication và side effect nghiệp vụ. Một listener có thể được gọi lại nhưng event vẫn chưa hoàn tất nếu lần sau tiếp tục lỗi.

## 3. Thiết kế listener có thể kiểm thử

Ví dụ event có định danh ổn định để theo dõi qua các lần giao:

~~~java
import java.time.Instant;
import java.util.UUID;

public record OrderConfirmed(
        UUID eventId,
        UUID orderId,
        Instant occurredAt) {
}
~~~

Listener gọi một cổng nghiệp vụ. Trong ví dụ, gateway có thể thất bại tạm thời ở lần đầu:

~~~java
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class InventoryListener {

    private final InventoryService inventory;

    InventoryListener(InventoryService inventory) {
        this.inventory = inventory;
    }

    @ApplicationModuleListener
    void on(OrderConfirmed event) {
        inventory.reserve(event.orderId(), event.eventId());
    }
}
~~~

Giữ listener mỏng giúp test tập trung vào việc điều phối event. Chính sách idempotency và tương tác với hệ thống ngoài nên được đặt trong service hoặc gateway có hợp đồng rõ ràng.

## 4. Unit test cho hành vi idempotent

Trước khi kiểm tra registry, hãy kiểm thử riêng logic nghiệp vụ để bảo đảm cùng event ID không tạo side effect lặp. Ví dụ dưới đây minh họa một service ghi nhận event đã xử lý trong cùng transaction với cập nhật projection:

~~~java
import java.util.UUID;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class InventoryService {

    private final ProcessedEventRepository processedEvents;
    private final InventoryRepository inventory;

    InventoryService(
            ProcessedEventRepository processedEvents,
            InventoryRepository inventory) {
        this.processedEvents = processedEvents;
        this.inventory = inventory;
    }

    @Transactional
    public void reserve(UUID orderId, UUID eventId) {
        if (processedEvents.existsById(eventId)) {
            return;
        }

        inventory.reserveFor(orderId);
        processedEvents.save(new ProcessedEvent(eventId));
    }
}
~~~

Kiểm thử service cần xác minh gọi hai lần với cùng event ID chỉ tạo một lần cập nhật nghiệp vụ. Trong database thật, dùng unique constraint trên event ID để bảo vệ trước hai lần xử lý đồng thời; kiểm tra rồi ghi mà không có ràng buộc nguyên tử vẫn có thể gặp race condition.

Với side effect gọi API ngoài, transaction database không thể rollback thao tác từ xa. Khi đó cần truyền idempotency key ổn định tới API đích hoặc có cách tra cứu kết quả trước khi gửi lại. Test chỉ xác minh repository trong bộ nhớ sẽ không chứng minh được API ngoài chống trùng.

## 5. Integration test: lỗi lần đầu, thành công khi resubmit

Integration test nên chạy application context với Event Publication Registry thực tế của cấu hình test. Listener có thể dùng một dependency giả có hành vi xác định: lần đầu ném exception, lần tiếp theo thành công.

Ví dụ test fixture:

~~~java
import java.util.UUID;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.stereotype.Component;

@Component
class FlakyInventoryService {

    private final AtomicInteger attempts = new AtomicInteger();

    void reserve(UUID orderId) {
        if (attempts.incrementAndGet() == 1) {
            throw new IllegalStateException("Temporary inventory failure");
        }
    }

    int attempts() {
        return attempts.get();
    }
}
~~~

Listener test sử dụng fixture này:

~~~java
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class RetryTestListener {

    private final FlakyInventoryService inventory;

    RetryTestListener(FlakyInventoryService inventory) {
        this.inventory = inventory;
    }

    @ApplicationModuleListener
    void on(OrderConfirmed event) {
        inventory.reserve(event.orderId());
    }
}
~~~

Test publish một event duy nhất, đợi lần xử lý đầu tiên thất bại và publication xuất hiện trong danh sách incomplete. Sau đó chủ động resubmit publication đó và chờ listener thành công:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

import java.time.Duration;
import java.time.Instant;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.modulith.events.EventPublicationRegistry;

@SpringBootTest
class EventRetryIntegrationTests {

    @Autowired ApplicationEventPublisher events;
    @Autowired EventPublicationRegistry publications;
    @Autowired FlakyInventoryService inventory;

    @Test
    void resubmitsIncompletePublication() {
        var event = new OrderConfirmed(
                UUID.randomUUID(),
                UUID.randomUUID(),
                Instant.now());

        events.publishEvent(event);

        await().atMost(Duration.ofSeconds(5)).untilAsserted(() ->
                assertThat(inventory.attempts()).isEqualTo(1));

        await().atMost(Duration.ofSeconds(5)).untilAsserted(() ->
                assertThat(publications.findIncompletePublications())
                        .anyMatch(publication ->
                                publication.getEvent().equals(event)));

        publications.resubmitIncompletePublications(publication ->
                publication.getEvent().equals(event));

        await().atMost(Duration.ofSeconds(5)).untilAsserted(() ->
                assertThat(inventory.attempts()).isEqualTo(2));

        await().atMost(Duration.ofSeconds(5)).untilAsserted(() ->
                assertThat(publications.findIncompletePublications())
                        .noneMatch(publication ->
                                publication.getEvent().equals(event)));
    }
}
~~~

Đây là mẫu integration test minh họa API của Event Publication Registry; đối chiếu chữ ký phương thức với phiên bản Spring Modulith mà dự án sử dụng. Test cần bảo đảm listener thực sự chạy bất đồng bộ theo cấu hình và registry dùng persistence adapter đang được kiểm tra. Nếu dùng database in-memory hoặc adapter khác production, hãy có thêm kiểm thử phù hợp cho cấu hình persistence production.

Awaitility chờ điều kiện cụ thể với timeout, tránh `Thread.sleep` cố định. Timeout phải đủ cho môi trường CI nhưng vẫn giới hạn thời gian test khi listener bị treo. Nếu listener có thể chạy song song hoặc test context được dùng chung, fixture cần reset và cô lập trạng thái giữa các test.

## 6. Kiểm tra retry policy và backoff

Resubmit publication là thao tác giao lại; nó không tự định nghĩa lịch retry. Ứng dụng cần quyết định khi nào publication đủ điều kiện thử lại, số lần thử và thời gian chờ. Có thể kiểm thử policy riêng bằng clock giả hoặc scheduler giả để không phải chờ thời gian thực.

Ví dụ một policy đơn giản:

~~~java
import java.time.Duration;
import java.time.Instant;

record RetryPolicy(
        int maxAttempts,
        Duration initialDelay,
        Duration maxDelay,
        double multiplier) {

    Duration delayFor(int failedAttempts) {
        double factor = Math.pow(multiplier, Math.max(0, failedAttempts - 1));
        long delayMillis = Math.round(initialDelay.toMillis() * factor);
        return Duration.ofMillis(Math.min(delayMillis, maxDelay.toMillis()));
    }

    boolean isDue(Instant lastAttemptAt, int attempts, Instant now) {
        return attempts < maxAttempts
                && !now.isBefore(lastAttemptAt.plus(delayFor(attempts)));
    }
}
~~~

Đây là logic minh họa để kiểm thử chính sách thời gian, không phải API của Spring Modulith. Production cần giới hạn delay tối đa, cân nhắc jitter, lưu attempt/next-attempt bền vững nếu cần qua restart và phân loại exception trước khi lên lịch.

Kiểm thử policy nên bao gồm:

- Không retry trước khi hết delay.
- Retry đúng thời điểm đủ điều kiện.
- Delay tăng theo multiplier nhưng không vượt giới hạn cấu hình.
- Không retry khi đã hết max attempts.
- Lỗi không retry được bị loại khỏi lịch resubmit.
- Clock hoặc scheduler giả giúp test không phụ thuộc thời gian thực.

## 7. Kiểm thử lỗi lặp lại và giới hạn retry

Không chỉ kiểm thử trường hợp lần đầu lỗi rồi thành công. Cần kiểm tra listener vẫn lỗi sau mọi lần thử:

1. Publish event và làm listener thất bại.
2. Resubmit theo policy cho tới khi đạt giới hạn.
3. Xác minh publication vẫn incomplete hoặc được chuyển sang trạng thái xử lý lỗi cuối cùng theo thiết kế.
4. Xác minh không có thêm lần gọi ngoài retry budget.
5. Kiểm tra cảnh báo hoặc bản ghi quarantine được tạo nếu chính sách yêu cầu.

Đừng đánh dấu publication completed chỉ để dừng retry nếu nghiệp vụ chưa được xử lý. Nếu cần kết thúc tự động, hãy lưu trạng thái failed/quarantined ở một workflow hoặc kho vận hành riêng và giữ dấu vết event để điều tra.

## 8. Kiểm thử event trùng và side effect

Publication có thể được resubmit sau khi listener đã thực hiện một phần side effect nhưng thất bại trước khi đánh dấu hoàn tất. Vì vậy, test cần mô phỏng tình huống side effect đã xảy ra rồi listener ném exception.

Ví dụ: service ghi nhận yêu cầu giữ hàng thành công, nhưng bước gọi dependency tiếp theo lỗi. Khi event được giao lại, hệ thống không được tạo yêu cầu giữ hàng thứ hai. Kiểm thử nên xác minh:

- Cùng event ID được dùng qua mọi lần giao lại.
- Bản ghi processed event hoặc idempotency key được lưu bền vững.
- Hai lần xử lý đồng thời không tạo side effect trùng.
- Khi API ngoài trả timeout sau khi đã xử lý, lần gửi lại dùng cùng idempotency key.
- Retry không làm mất hoặc ghi đè kết quả thành công đã có.

Đối với database, kiểm tra unique constraint và transaction boundary. Đối với API ngoài, dùng mock server để xác minh header idempotency và mô phỏng response bị mất sau side effect.

## 9. Kiểm thử persistence và phục hồi sau restart

Event Publication Registry chỉ hỗ trợ phục hồi qua restart khi publication được lưu bền vững theo cấu hình. Kiểm thử persistence cần xác minh:

1. Publish event và làm listener thất bại để tạo publication incomplete.
2. Đóng application context hoặc khởi động lại ứng dụng test theo cách phù hợp.
3. Khởi động lại với cùng database và persistence adapter.
4. Xác minh publication incomplete vẫn tồn tại.
5. Resubmit publication và xác minh listener hoàn tất.
6. Xác minh publication completed được lưu đúng trạng thái.

Test này nên chạy với loại database và adapter tương thích production. Một test chỉ dùng mock registry không chứng minh được dữ liệu được lưu và khôi phục qua restart.

## 10. Kiểm thử lỗi và phân loại exception

Retry mọi exception có thể làm test xanh nhưng che giấu chính sách sai. Tạo các trường hợp riêng:

| Tình huống | Kỳ vọng |
| --- | --- |
| Timeout hoặc connection reset | Có thể retry theo backoff và giới hạn |
| HTTP 503 hoặc 429 | Retry theo chính sách, cân nhắc `Retry-After` |
| HTTP 400 hoặc payload sai | Không retry nguyên trạng; ghi nhận lỗi dữ liệu |
| HTTP 401/403 | Không retry liên tục; cảnh báo lỗi credential/ACL |
| Lỗi nghiệp vụ không thể phục hồi | Chuyển trạng thái nghiệp vụ hoặc quarantine |
| KMS/broker/database tạm thời không sẵn sàng | Retry theo budget của đúng tầng phụ thuộc |

Test phải xác minh exception nào được ném ra, exception nào được retry và exception nào được truyền tới cơ chế xử lý lỗi cuối cùng. Tránh assert chỉ dựa vào số lần gọi mà không kiểm tra loại lỗi.

## 11. Quan sát retry trong test

Retry cần để lại dấu vết đủ để điều tra. Kiểm thử có thể xác minh metrics hoặc log có các thuộc tính ổn định:

- Event ID và event type.
- Listener hoặc publication target.
- Attempt number và nhóm exception.
- Thời điểm lần thử gần nhất và thời điểm thử tiếp theo nếu được lưu.
- Kết quả success, pending hoặc exhausted.

Không đưa event ID, order ID hoặc correlation ID thành metric tag có cardinality cao. Dùng structured log hoặc trace để tìm một event cụ thể. Với metrics, dùng tag ổn định như listener, event type đã chuẩn hóa, outcome và exception class.

Kiểm tra dashboard/alert cho các tình huống backlog tăng, publication pending quá lâu, retry vượt ngưỡng và lỗi cuối cùng. Cảnh báo cần phản ánh SLA của luồng nghiệp vụ, không chỉ cảnh báo mọi lần retry đơn lẻ.

## 12. Những sai lầm cần tránh

- Chỉ kiểm thử listener method trực tiếp mà không kiểm tra publication registry.
- Dùng `Thread.sleep` cố định cho test bất đồng bộ.
- Giả định Event Publication Registry tự retry theo lịch mà ứng dụng không cần cấu hình.
- Coi listener được gọi lại là bằng chứng side effect không bị trùng.
- Không kiểm tra trạng thái incomplete/completed của publication.
- Retry mọi exception, kể cả lỗi dữ liệu và lỗi nghiệp vụ cố định.
- Không kiểm thử retry sau restart với persistence adapter thật.
- Dùng mock registry rồi kết luận khả năng phục hồi production đã được xác minh.
- Đánh dấu completed để loại publication khỏi backlog khi nghiệp vụ chưa thành công.

## Kết luận

Kiểm thử retry cần xác minh toàn bộ vòng đời publication: listener thất bại, publication còn incomplete, ứng dụng resubmit theo policy, listener thành công và publication được đánh dấu completed. Kết hợp unit test cho idempotency và backoff với integration test dùng Event Publication Registry, Awaitility và persistence adapter phù hợp. Kiểm thử cả lỗi lặp lại, event trùng, exception không retry được và phục hồi sau restart để bảo đảm retry có giới hạn, có quan sát và không tạo side effect trùng.

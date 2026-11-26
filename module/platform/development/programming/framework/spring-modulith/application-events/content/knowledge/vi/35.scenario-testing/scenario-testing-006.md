# Chờ xử lý bất đồng bộ

Trong Spring Modulith, application event thường được xử lý bất đồng bộ để module phát event không phải chờ mọi listener hoàn tất. Cách tổ chức này giúp giảm phụ thuộc thời gian chạy, nhưng làm cho kết quả của listener không nhất thiết xuất hiện ngay sau lời gọi publish. Khi viết scenario test, bài kiểm thử phải chờ đúng điều kiện nghiệp vụ cần xác minh thay vì giả định công việc nền đã hoàn tất.

Chờ xử lý bất đồng bộ là một phần của việc kiểm thử hành vi hệ thống: kích hoạt use case, đợi event hoặc trạng thái đích xuất hiện trong một khoảng thời gian giới hạn, sau đó xác minh kết quả. Một bài test tốt phải kết thúc nhanh khi điều kiện đạt, thất bại rõ ràng khi hết thời gian và không phụ thuộc vào tốc độ máy chạy test.

## 1. Vì sao scenario test phải chờ?

Giả sử module Orders xác nhận đơn hàng và publish `OrderConfirmed`. Module Inventory nhận event để cập nhật projection tồn kho. Lời gọi `orders.confirm(orderId)` có thể trả về sau khi transaction Orders commit, trong khi listener Inventory vẫn đang chạy trên executor khác.

~~~mermaid
sequenceDiagram
    participant T as Scenario test
    participant O as Orders
    participant DB as Orders database
    participant L as Inventory listener
    participant P as Inventory projection
    T->>O: confirm(orderId)
    O->>DB: Update order
    DB-->>O: Commit
    O-->>T: Return
    Note over T,L: Listener vẫn đang chạy bất đồng bộ
    O-->>L: OrderConfirmed
    L->>P: Update projection
    P-->>L: Commit
    T->>P: Chờ điều kiện projection được cập nhật
~~~

Nếu test đọc projection ngay sau khi `confirm` trả về, nó có thể quan sát dữ liệu cũ. Kết quả phụ thuộc lịch chạy thread và tải của môi trường; test có thể lúc xanh lúc đỏ dù code không thay đổi.

Chờ bất đồng bộ cần có ba thành phần:

1. **Trigger:** hành động kích hoạt công việc, ví dụ gọi use case hoặc publish event.
2. **Condition:** kết quả quan sát được cần chờ, ví dụ event đã tới listener, projection có version mới hoặc task chuyển sang COMPLETED.
3. **Timeout:** thời gian tối đa cho phép condition xuất hiện; khi hết hạn, test phải thất bại với thông tin đủ để điều tra.

## 2. Chờ condition thay vì ngủ cố định

Cách đơn giản nhưng không đáng tin cậy là gọi `Thread.sleep` sau khi publish event:

~~~java
orders.confirm(orderId);
Thread.sleep(1_000);
assertThat(projections.findByOrderId(orderId)).isPresent();
~~~

Đoạn test này luôn chờ một giây dù listener hoàn tất sau 20 ms. Nếu môi trường CI chậm hơn một giây, test vẫn có thể đọc quá sớm. Tăng thời gian ngủ làm suite chậm hơn nhưng không loại bỏ được race condition.

Thay vào đó, hãy chờ một condition cụ thể với timeout:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

import java.time.Duration;

orders.confirm(orderId);

await().atMost(Duration.ofSeconds(5)).untilAsserted(() ->
        assertThat(projections.findByOrderId(orderId))
                .isPresent());
~~~

`untilAsserted` chạy lại assertion cho tới khi assertion thành công hoặc hết timeout. Test kết thúc ngay khi projection xuất hiện. Nếu listener không chạy hoặc bị lỗi, Awaitility ném assertion/timeout failure thay vì để test treo vô hạn.

Chọn timeout dựa trên SLA và môi trường test. Với listener nội bộ chạy nhanh, vài giây có thể đủ; với integration test dùng broker hoặc container, cần khoảng thời gian lớn hơn. Timeout phải hữu hạn và đủ ngắn để lỗi được phát hiện sớm.

## 3. Dùng Scenario API của Spring Modulith

Spring Modulith cung cấp `Scenario` trong test support để kích hoạt một hành động và chờ event được phát sinh. API này phù hợp khi test muốn mô tả luồng nghiệp vụ theo kiểu Given/When/Then mà không tự quản lý polling cho event.

Ví dụ scenario test chờ `OrderConfirmed` sau khi gọi use case:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.Scenario;

@ApplicationModuleTest
class OrderConfirmationScenarioTests {

    @Autowired OrderApplicationService orders;
    @Autowired Scenario scenario;

    @Test
    void publishesOrderConfirmedAfterConfirmation() {
        UUID orderId = UUID.randomUUID();

        scenario.stimulate(() -> orders.confirm(orderId))
                .andWaitForEventOfType(OrderConfirmed.class)
                .toArrive()
                .matching(event -> event.orderId().equals(orderId));
    }
}
~~~

`Scenario` kích hoạt hành động trong test và chờ event thuộc kiểu mong đợi. Predicate `matching` giúp phân biệt event của use case hiện tại với event khác có thể được phát đồng thời trong cùng application context.

Scenario API phù hợp để xác minh event đã được phát và quan sát được. Nếu mục tiêu là xác minh listener đã cập nhật database hoặc tạo side effect, hãy chờ trạng thái đích đó nữa. Event được publish không đồng nghĩa mọi listener đã hoàn tất.

API và cách cấu hình test support có thể khác giữa các phiên bản Spring Modulith; dùng phiên bản thư viện đồng bộ với ứng dụng và kiểm tra import `org.springframework.modulith.test` tương ứng.

## 4. Chờ kết quả listener, không chỉ chờ event

Một scenario thường cần xác minh tác động cuối cùng. Ví dụ, sau `OrderConfirmed`, Inventory listener cập nhật read model. Có thể gọi use case rồi chờ projection đạt trạng thái mong đợi:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

import java.time.Duration;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class InventoryProjectionScenarioTests {

    @Autowired OrderApplicationService orders;
    @Autowired InventoryProjectionRepository projections;

    @Test
    void updatesProjectionAsynchronously() {
        UUID orderId = UUID.randomUUID();

        orders.confirm(orderId);

        await().atMost(Duration.ofSeconds(5)).untilAsserted(() -> {
            var projection = projections.findByOrderId(orderId);
            assertThat(projection).isPresent();
            assertThat(projection.orElseThrow().status())
                    .isEqualTo("CONFIRMED");
        });
    }
}
~~~

Không đánh dấu test thành công chỉ vì listener method đã được gọi. Hãy xác minh kết quả quan trọng với người dùng hoặc module tiêu thụ: row đã được ghi, trạng thái đã đổi, message đã được gửi hoặc task đã chuyển sang trạng thái mong đợi.

Nếu listener tạo nhiều thay đổi, chờ một điều kiện đại diện cho trạng thái hoàn chỉnh. Chờ một row xuất hiện trong khi các row liên quan chưa được ghi có thể khiến test kết thúc quá sớm.

## 5. Chọn điều kiện chờ ổn định

Condition cần phản ánh kết quả nghiệp vụ và có thể đọc lặp lại an toàn. Các condition phù hợp:

- Một projection có aggregate version bằng hoặc lớn hơn version của event.
- Một task có trạng thái COMPLETED.
- Một bản ghi outbox được đánh dấu SENT.
- Một event phản hồi có correlation ID tương ứng đã tới.
- Một số lượng bản ghi đạt giá trị mong đợi.

Tránh dùng condition không ổn định như số thread hiện tại, thời gian CPU hoặc một log line tình cờ. Các tín hiệu này có thể thay đổi mà không chứng minh nghiệp vụ đã hoàn tất.

Nếu test chỉ cần chờ event, dùng Scenario API. Nếu cần chờ database hoặc một trạng thái bên ngoài, dùng Awaitility hoặc cơ chế đồng bộ hóa phù hợp với tài nguyên đó.

## 6. Cấu hình Awaitility rõ ràng

Awaitility cho phép cấu hình thời gian chờ tối đa, khoảng polling và độ trễ trước lần kiểm tra đầu:

~~~java
import static org.awaitility.Awaitility.await;
import static java.util.concurrent.TimeUnit.MILLISECONDS;

await()
        .pollDelay(50, MILLISECONDS)
        .pollInterval(100, MILLISECONDS)
        .atMost(5, java.util.concurrent.TimeUnit.SECONDS)
        .untilAsserted(() ->
                assertThat(projections.findByOrderId(orderId))
                        .isPresent());
~~~

Khoảng polling quá ngắn có thể tạo nhiều truy vấn database hoặc tải không cần thiết. Khoảng quá dài làm test phản hồi chậm khi condition đã đạt. Chọn giá trị vừa phải theo chi phí kiểm tra và độ trễ dự kiến.

Có thể đặt timeout mặc định ở cấp test suite, nhưng test quan trọng nên thể hiện timeout của chính nó để người đọc hiểu kỳ vọng. Không dùng timeout cực lớn để che giấu listener bị treo.

## 7. Tránh transaction test giữ event chưa được commit

Spring Modulith thường xử lý application event sau khi transaction phát event commit. Nếu test được đánh dấu `@Transactional`, transaction của test có thể chưa commit cho tới khi phương thức test kết thúc; nhiều test framework còn rollback transaction đó. Khi đó listener đăng ký `AFTER_COMMIT` sẽ không chạy trong lúc test đang chờ.

Với scenario kiểm tra xử lý sau commit:

- Ưu tiên để use case tự mở và commit transaction của nó; không bọc toàn bộ test trong một transaction ngoài.
- Nếu cần kiểm soát transaction trong test, chủ động commit bằng cơ chế test transaction phù hợp trước khi chờ listener.
- Không chờ event từ một transaction chưa commit rồi kết luận listener bị lỗi.

Ví dụ test không có `@Transactional` ở lớp hoặc phương thức:

~~~java
@SpringBootTest
class AfterCommitEventTests {

    @Autowired OrderApplicationService orders;
    @Autowired InventoryProjectionRepository projections;

    @Test
    void listenerRunsAfterBusinessCommit() {
        UUID orderId = UUID.randomUUID();

        orders.confirm(orderId); // Transaction trong use case commit khi method return.

        await().atMost(Duration.ofSeconds(5)).untilAsserted(() ->
                assertThat(projections.findByOrderId(orderId)).isPresent());
    }
}
~~~

Điều này giúp test quan sát đúng ranh giới transaction của production. Nếu cần test rollback, hãy viết scenario riêng xác minh event không được xử lý khi transaction nguồn rollback.

## 8. Chờ listener chạy song song và tránh race condition

Listener bất đồng bộ có thể chạy trên executor khác thread test. Vì vậy:

- Không đọc hoặc ghi một `ArrayList`/`HashMap` dùng chung mà không có đồng bộ phù hợp.
- Dùng repository hoặc cấu trúc thread-safe để quan sát kết quả.
- Mỗi test dùng ID duy nhất để tránh nhầm dữ liệu do test khác tạo.
- Không dùng một `AtomicInteger` singleton dùng chung giữa nhiều test song song nếu không reset/cô lập.
- Chờ theo ID hoặc correlation ID của scenario thay vì chỉ chờ tổng số event toàn hệ thống.

Test song song có thể làm một listener nhận event của scenario khác. Predicate theo aggregate ID hoặc event ID giúp điều kiện chờ gắn đúng luồng.

## 9. Dùng CountDownLatch khi cần đồng bộ tại một điểm

Trong một số test cấp thấp, cần xác nhận callback đã đi qua một điểm cụ thể. `CountDownLatch` có thể cung cấp tín hiệu rõ ràng:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

CountDownLatch handled = new CountDownLatch(1);

// Test listener giảm latch khi đã tới điểm cần xác minh.
boolean completed = handled.await(5, TimeUnit.SECONDS);

assertThat(completed).isTrue();
~~~

Latch phải có timeout; không gọi `await()` vô hạn. Nó phù hợp cho một tín hiệu một lần, còn Awaitility phù hợp hơn khi cần polling trạng thái repository hoặc condition có thể thay đổi theo thời gian. Không dùng latch để bỏ qua việc kiểm tra kết quả nghiệp vụ.

## 10. Chờ retry và publication phục hồi

Khi listener lỗi tạm thời, Event Publication Registry có thể giữ publication ở trạng thái chưa hoàn tất để ứng dụng phục hồi hoặc resubmit theo chính sách. Scenario test có thể kiểm tra các giai đoạn:

1. Publish event và chờ lần xử lý đầu tiên thất bại.
2. Xác minh publication vẫn incomplete.
3. Kích hoạt cơ chế resubmit hoặc retry được ứng dụng cấu hình.
4. Chờ listener hoàn tất.
5. Xác minh publication không còn incomplete và side effect chỉ xuất hiện một lần.

Không giả định registry tự tạo lịch retry theo một khoảng thời gian cụ thể nếu ứng dụng chưa cấu hình scheduler hoặc quy trình resubmit. Test nên kích hoạt cơ chế retry thật của ứng dụng hoặc gọi abstraction điều phối retry mà hệ thống sở hữu.

Với retry có backoff, không chờ một khoảng cố định rồi đoán rằng retry đã xảy ra. Hãy quan sát attempt, trạng thái publication hoặc side effect và đặt timeout lớn hơn retry budget dự kiến.

## 11. Kiểm thử externalization và consumer bất đồng bộ

Khi event được externalize sang Kafka hoặc broker khác, có nhiều chặng bất đồng bộ:

~~~mermaid
flowchart LR
    A[Business transaction] --> B[Publication registry]
    B --> C[Externalization listener]
    C --> D[Broker]
    D --> E[Consumer]
    E --> F[Consumer database]
~~~

Test cần chờ đúng ranh giới:

- Nếu kiểm tra publisher/adapter, chờ send result hoặc message xuất hiện ở broker test.
- Nếu kiểm tra consumer, chờ trạng thái trong database của consumer hoặc event phản hồi.
- Nếu kiểm tra end-to-end, chờ kết quả nghiệp vụ cuối cùng bằng correlation ID.

Không dùng trạng thái externalization listener completed làm bằng chứng consumer đã xử lý. Với Kafka, consumer lag và offset commit là tín hiệu vận hành; test nghiệp vụ nên ưu tiên xác minh trạng thái mà consumer ghi ra.

## 12. Timeout và thông tin khi test thất bại

Timeout là một phần của hợp đồng test. Khi hết thời gian, failure cần giúp phân biệt:

- Trigger không chạy hoặc transaction chưa commit.
- Event không được publish.
- Listener không được đăng ký hoặc không được gọi.
- Listener đang chạy nhưng bị treo ở dependency.
- Listener đã lỗi và publication còn incomplete.
- Listener hoàn tất nhưng test đang đọc nhầm database, tenant hoặc ID.

Trong thông báo lỗi, có thể thêm event ID, aggregate ID, listener, timeout và trạng thái mong đợi. Không đưa payload nhạy cảm vào assertion message hoặc log test.

Tránh tăng timeout ngay khi test đỏ. Trước hết xác định condition có đúng không, listener có được kích hoạt không, transaction đã commit chưa và dependency có phản hồi không. Chỉ tăng timeout khi độ trễ hợp lệ của môi trường thực sự lớn hơn.

## 13. Kiểm thử dọn dẹp và cô lập dữ liệu

Listener có thể tiếp tục chạy sau khi test method đã kết thúc nếu test timeout hoặc cleanup quá sớm. Để tránh test sau bị ảnh hưởng:

- Chờ listener đạt trạng thái kết thúc trước khi xóa dữ liệu fixture.
- Dùng ID duy nhất cho từng test và lọc truy vấn theo ID.
- Dọn dữ liệu projection, processed event và task sau khi đã xác nhận xử lý hoàn tất.
- Cô lập executor hoặc reset fake dependency khi test context được chia sẻ.
- Không xóa publication đang pending trong khi listener vẫn có thể xử lý.

Nếu test chạy song song, cân nhắc tắt song song cho các scenario chia sẻ tài nguyên toàn cục hoặc cung cấp namespace riêng cho mỗi test.

## 14. Những sai lầm cần tránh

- Dùng `Thread.sleep` để đoán listener đã chạy xong.
- Chỉ chờ event được publish trong khi mục tiêu là kết quả của listener.
- Chờ không có timeout khiến test suite treo vô hạn.
- Bọc test trong transaction chưa commit khi kiểm tra listener `AFTER_COMMIT`.
- Dùng ID cố định làm các test song song đọc nhầm dữ liệu của nhau.
- Chờ tổng số event thay vì event có ID/correlation ID của scenario.
- Coi publication completed là consumer bên ngoài đã hoàn tất.
- Retry test bằng cách gọi listener trực tiếp rồi kết luận event pipeline đã được kiểm chứng.
- Tăng timeout để che lỗi trigger, transaction hoặc dependency.

## Kết luận

Scenario test cho xử lý bất đồng bộ cần kích hoạt use case, chờ một condition quan sát được và giới hạn thời gian chờ. Dùng Scenario API của Spring Modulith để chờ event, Awaitility để chờ trạng thái projection hoặc database, và latch khi cần tín hiệu đồng bộ một lần. Kiểm tra transaction đã commit, gắn condition với event ID/correlation ID, cô lập dữ liệu và phân biệt publication, listener, broker với consumer. Cách chờ có chủ đích giúp test ổn định, nhanh và chỉ ra chính xác chặng xử lý chưa hoàn tất.

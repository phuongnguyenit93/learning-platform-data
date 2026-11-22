# Kiểm thử thứ tự khi nghiệp vụ thật sự yêu cầu

Trong Spring Framework Application Events, một sự kiện có thể được nhiều listener xử lý. Đôi khi nghiệp vụ có phụ thuộc thật sự: *xác nhận đã đặt chỗ* phải xảy ra trước khi *gửi thông báo đặt chỗ thành công*. Khi đó, kiểm thử cần chứng minh thứ tự có ý nghĩa đối với kết quả nghiệp vụ. Nếu các listener độc lập (ghi metric, gửi thông báo phụ, cập nhật chỉ số), việc cố định thứ tự gọi thường làm test giòn và ghép các thành phần không cần thiết.

Bài này tập trung vào cách xác định hợp đồng thứ tự, viết test quan sát được bằng Spring Test + JUnit 5, và phân biệt thứ tự gọi listener với hoàn tất xử lý khi có bất đồng bộ hoặc transaction.

## 1. Xác định trước: nghiệp vụ có thật sự cần thứ tự không?

| Tình huống | Có nên kiểm thử thứ tự? | Điều cần bảo đảm |
| --- | --- | --- |
| Listener A lập trạng thái `RESERVED`, listener B chỉ được thông báo khi trạng thái đó tồn tại | **Có**, nếu hệ thống chủ đích dùng cùng một sự kiện và xử lý đồng bộ | B không chạy thành công trước khi A thiết lập trạng thái |
| Listener A ghi metric, listener B ghi audit độc lập | **Không** | Mỗi hiệu ứng cần thiết xảy ra; không ràng buộc A/B |
| Gửi email sau khi dữ liệu đơn hàng đã commit | **Kiểm thử pha transaction**, không đơn thuần thứ tự `@Order` | Chỉ gửi sau commit thành công; rollback thì không gửi |
| Hai listener chạy bằng `@Async` hoặc executor chung | **Không kiểm thử bằng thứ tự kết thúc tùy ý** | Kiểm thử điều kiện đồng bộ hoặc hợp đồng xử lý bất đồng bộ |
| Hai instance ứng dụng nhận sự kiện qua message broker | **Không dùng `@Order` để cam kết thứ tự toàn hệ thống** | Dùng cơ chế có bảo đảm thứ tự/khóa nghiệp vụ và idempotency nếu cần |

Câu hỏi quyết định: **Nếu đổi chỗ A và B mà dữ liệu, quyết định, hoặc quy tắc nghiệp vụ vẫn đúng, có lý do gì để bắt test thất bại?** Nếu không, hãy kiểm thử kết quả riêng của từng listener.

Ví dụ có phụ thuộc thực sự:

1. Khi hệ thống nhận `PaymentCaptured(orderId)`, listener A đánh dấu đơn hàng đã được giữ chỗ.
2. Listener B kiểm tra đã giữ chỗ rồi mới ghi nhận thông báo.
3. Yêu cầu nghiệm thu: thông báo chỉ được tạo khi giữ chỗ thành công.

Ở ví dụ này ta có thể kiểm tra thứ tự **trong cùng một lần phát sự kiện đồng bộ**. Trong hệ thống thực tế, nếu hai bước tạo thành quy trình bắt buộc, một service điều phối tường minh hoặc sự kiện kế tiếp như `ReservationCompleted` thường làm phụ thuộc rõ hơn so với dựa lâu dài vào ưu tiên listener.

## 2. Cơ chế `@Order` và phạm vi của bảo đảm

Mặc định, Spring ApplicationContext dùng `SimpleApplicationEventMulticaster` để phát sự kiện **đồng bộ trong thread của bên publish**, khi chưa cấu hình executor bất đồng bộ. Với các listener nhận **cùng loại sự kiện** trong cùng lượt dispatch:

- `@EventListener` đánh dấu method nhận sự kiện.
- `@Order(10)` có ưu tiên trước `@Order(20)`: **số nhỏ hơn được gọi trước**.
- `@Order` trên method `@EventListener` điều khiển thứ tự gọi tương ứng; nó không tạo transaction và không biến nhiều listener thành một thao tác nguyên tử.
- Khi listener ném lỗi trong chế độ đồng bộ mặc định và không có error handler nuốt lỗi, lỗi có thể truyền ngược đến bên publish; listener đến sau có thể không được gọi. Vì vậy test cũng cần phản ánh cách xử lý lỗi dự kiến.

Phạm vi trên thay đổi khi bật `@Async`, thiết lập `TaskExecutor` cho multicaster, áp dụng `@TransactionalEventListener` hoặc để nhiều publisher/thread phát đồng thời. **Thứ tự bắt đầu/gọi không đồng nghĩa thứ tự hoàn tất tác vụ**, và thứ tự ở một JVM không bảo đảm thứ tự xuyên tiến trình.

## 3. Viết điều kiện kiểm thử theo hành vi có thể quan sát

Hãy viết hợp đồng theo *Given – When – Then*:

- **Given:** Có listener giữ chỗ `@Order(10)` và listener thông báo `@Order(20)`; cả hai được quản lý bởi Spring trong một context đồng bộ.
- **When:** Publish một `PaymentCaptured("O-42")`.
- **Then:** Hệ thống ghi `reserved:O-42` trước `notified:O-42`, đồng thời listener thông báo xác nhận trạng thái đặt chỗ đã tồn tại.

Nên kiểm tra **cả kết quả nghiệp vụ và chuỗi bước có ý nghĩa**. Test chỉ `verify(listenerA)` rồi `verify(listenerB)` không nhất thiết chứng minh thứ tự; test chỉ đếm số sự kiện cũng không chứng minh thứ tự listener.

## 4. Ví dụ kiểm thử tích hợp Spring + JUnit 5

Ví dụ Java 17+ sau là **một file test hoàn chỉnh**, không cần Spring Boot application. Đặt tại `src/test/java/example/events/ListenerOrderTest.java`. Dự án test cần Spring Context, Spring Test và JUnit Jupiter; `SpringJUnitConfig` tích hợp Spring TestContext với JUnit 5.

~~~java
package example.events;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(ListenerOrderTest.TestConfig.class)
class ListenerOrderTest {

    @Autowired
    ApplicationEventPublisher publisher;

    @Autowired
    Trace trace;

    @Test
    void reservationMustPrecedeNotification() {
        publisher.publishEvent(new PaymentCaptured("O-42"));

        assertEquals(
            List.of("reserved:O-42", "notified:O-42"),
            trace.steps()
        );
    }

    record PaymentCaptured(String orderId) { }

    static class Trace {
        private final List<String> steps = new ArrayList<>();
        private final Set<String> reservedOrders = new HashSet<>();

        void reserve(String orderId) {
            reservedOrders.add(orderId);
            steps.add("reserved:" + orderId);
        }

        void notifyIfReserved(String orderId) {
            if (!reservedOrders.contains(orderId)) {
                throw new IllegalStateException(
                    "Cannot notify before reservation: " + orderId
                );
            }
            steps.add("notified:" + orderId);
        }

        List<String> steps() {
            return List.copyOf(steps);
        }
    }

    static class BusinessListeners {
        private final Trace trace;

        BusinessListeners(Trace trace) {
            this.trace = trace;
        }

        @EventListener
        @Order(10)
        public void reserve(PaymentCaptured event) {
            trace.reserve(event.orderId());
        }

        @EventListener
        @Order(20)
        public void notifyCustomer(PaymentCaptured event) {
            trace.notifyIfReserved(event.orderId());
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class TestConfig {
        @Bean
        Trace trace() {
            return new Trace();
        }

        @Bean
        BusinessListeners businessListeners(Trace trace) {
            return new BusinessListeners(trace);
        }
    }
}
~~~

**Cách chạy:** trong một dự án Gradle đã cấu hình các dependency test ở trên và sử dụng JUnit Platform, chạy:

~~~bash
./gradlew test --tests "example.events.ListenerOrderTest"
~~~

Trên Windows PowerShell có thể dùng `./gradlew.bat` thay cho `./gradlew`. Khi mọi dependency và cấu hình test đúng, bài test **pass**; chương trình không in chuỗi `reserved:...` hay `notified:...` ra stdout, vì hai giá trị đó được lưu trong `Trace` và so bằng assertion.

**Vì sao test này kiểm tra đúng thứ tự?**

1. `@SpringJUnitConfig` tạo context thật; `BusinessListeners` là bean có hai method `@EventListener`.
2. `publishEvent` gửi sự kiện đúng loại vào multicaster đồng bộ mặc định; test không tự gọi hai listener theo thứ tự mong muốn.
3. `@Order(10)` khiến `reserve` được gọi trước `@Order(20)` của `notifyCustomer`.
4. `notifyIfReserved` chứa điều kiện nghiệp vụ: nếu thứ tự bị đảo, phương thức sẽ ném `IllegalStateException`; test thất bại.
5. `assertEquals` kiểm tra thêm dấu vết quan sát được, phát hiện trường hợp thiếu hoặc gọi lặp một bước.

Để thử tính nhạy của test, đổi tạm `@Order(10)` và `@Order(20)`: với multicaster đồng bộ mặc định, listener thông báo sẽ gặp trạng thái chưa được giữ chỗ và làm test thất bại. Hoàn tác thay đổi sau khi kiểm chứng. Việc này giúp xác nhận assertion bảo vệ phụ thuộc nghiệp vụ thật, thay vì chỉ luôn pass.

Lưu ý: `Trace` dùng `ArrayList` và `HashSet` cố ý để ví dụ đơn giản và chỉ phù hợp với luồng xử lý đồng bộ nêu trên. Nếu chuyển sang bất đồng bộ, các cấu trúc này và toàn bộ kiểu kiểm thử cần được thiết kế lại cho an toàn luồng.

## 5. Khi không có phụ thuộc thứ tự: kiểm thử điều đúng cần đúng

Giả sử một listener cập nhật metric, listener khác ghi audit. Không có quy tắc nào buộc metric phải hoàn thành trước audit. Khi đó:

- Kiểm tra số lượng/giá trị metric và audit thực sự được tạo.
- Kiểm tra một lần publish tạo đúng sự kiện, không tạo lặp ngoài ý muốn.
- Không assert `List.of("metric", "audit")`, không khóa số `@Order` chỉ để test ổn định.

Spring TestContext cung cấp `@RecordApplicationEvents` và `ApplicationEvents` để ghi lại **sự kiện đã phát** trong mỗi test. Ví dụ trích đoạn đặt bên trong một test class được cấu hình Spring:

~~~java
@RecordApplicationEvents
@SpringJUnitConfig(TestConfig.class)
class PublicationTest {
    @Autowired
    ApplicationEventPublisher publisher;

    @Test
    void publishesOnePaymentEvent(ApplicationEvents events) {
        publisher.publishEvent(new PaymentCaptured("O-42"));

        assertEquals(1, events.stream(PaymentCaptured.class).count());
    }
}
~~~

Đoạn trên **minh họa ý tưởng**, không phải file độc lập: cần định nghĩa `TestConfig`, `PaymentCaptured` và import các lớp như ở ví dụ trước, cùng `org.springframework.test.context.event.ApplicationEvents` và `org.springframework.test.context.event.RecordApplicationEvents`. Nó chứng minh có một sự kiện được publish, **không chứng minh listener A đã chạy trước B**. Với listener có tác dụng phụ, cần assertion riêng trên trạng thái/tương tác của tác dụng phụ đó.

## 6. Trường hợp bất đồng bộ: không suy ra thứ tự hoàn thành từ `@Order`

Khi một method listener có `@Async` (và có bật hỗ trợ async), hoặc `SimpleApplicationEventMulticaster` sử dụng executor, việc dispatch có thể dẫn đến công việc được thực thi trên thread khác. **Không được giả định rằng listener có `@Order(10)` sẽ hoàn thành trước listener có `@Order(20)`**.

Test dạng dưới đây không đáng tin:

~~~java
publisher.publishEvent(new PaymentCaptured("O-42"));
assertEquals(List.of("reserved:O-42", "notified:O-42"), trace.steps());
// Có thể assert khi tác vụ chưa hoàn thành, hoặc chịu ảnh hưởng scheduler.
~~~

Với xử lý async, hãy kiểm thử theo hợp đồng thực sự:

- Nếu hai tác vụ độc lập: dùng cơ chế chờ có timeout xác định (`CountDownLatch`, `CompletableFuture`, hoặc tiện ích kiểm thử chuyên dụng) rồi xác nhận **cả hai kết quả**, không kiểm tra thứ tự hoàn thành.
- Nếu B phụ thuộc đầu ra A: mô hình hóa phụ thuộc bằng chuỗi xử lý rõ ràng, ví dụ A hoàn tất rồi publish `ReservationCompleted` để kích hoạt B, hoặc dùng service điều phối; sau đó kiểm thử B không chạy trước điều kiện sẵn sàng.
- Không dùng `Thread.sleep(...)` để “ổn định” thứ tự: sleep không thiết lập quan hệ happens-before theo hợp đồng nghiệp vụ, dễ tạo test chập chờn khi CI tải cao.
- Test async phải quan sát ngoại lệ và timeout rõ ràng. Ngoại lệ trong async listener không tự động truyền ngược về lệnh publish; không được coi publish trả về bình thường là bằng chứng listener thành công.

Nếu nhiều luồng cùng publish, ngay cả khi listener trong **từng lần** dispatch đồng bộ, các bước từ hai sự kiện khác nhau vẫn có thể xen kẽ. Phải kiểm tra theo `orderId`/correlation ID và thiết kế ràng buộc dữ liệu phù hợp; đừng áp đặt một chuỗi sự kiện toàn cục.

## 7. Trường hợp transaction: kiểm thử thời điểm commit/rollback

`@TransactionalEventListener` gắn việc xử lý với một pha transaction. Mặc định là `TransactionPhase.AFTER_COMMIT`; ngoài ra có `BEFORE_COMMIT`, `AFTER_ROLLBACK`, `AFTER_COMPLETION`. Nếu không có transaction thích hợp đang hoạt động, listener thường không chạy trừ khi bật `fallbackExecution = true`.

Ví dụ listener gửi thông báo sau commit:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void sendAfterCommit(PaymentCaptured event) {
    notificationSink.send(event.orderId());
}
~~~

Đây là **trích đoạn method** trong bean Spring, cần import `TransactionalEventListener` và `TransactionPhase`. Trong integration test có transaction manager thực sự, kiểm thử nên quan sát:

1. Khi đang ở **bên trong** transaction, notification chưa được gửi.
2. Sau khi commit thành công, notification được gửi đúng một lần.
3. Sau khi rollback, notification không được gửi.

Một cách điều khiển thời điểm kết thúc trong test là dùng `TransactionTemplate` (trích đoạn trong test đã inject `transactionTemplate`, `publisher`, `notificationSink`):

~~~java
transactionTemplate.executeWithoutResult(status -> {
    publisher.publishEvent(new PaymentCaptured("O-42"));
    assertEquals(0, notificationSink.count());
});
assertEquals(1, notificationSink.count()); // Sau khi commit.

notificationSink.reset();
transactionTemplate.executeWithoutResult(status -> {
    publisher.publishEvent(new PaymentCaptured("O-43"));
    status.setRollbackOnly();
});
assertEquals(0, notificationSink.count()); // Rollback không kích hoạt AFTER_COMMIT.
~~~

Đoạn này mô tả **kịch bản kiểm thử**, không phải chương trình độc lập. Nó giả định có transaction manager hoạt động và `notificationSink` là test double quan sát được. Trong test Spring có `@Transactional` ở chính method test, mặc định Spring TestContext thường rollback khi kết thúc; callback `AFTER_COMMIT` vì thế **không chạy như trường hợp commit**. Chỉ đặt `@Commit` trên method test cũng không giúp assertion chạy **bên trong** method quan sát được thời điểm sau commit; hãy chủ động kết thúc transaction bằng công cụ test thích hợp (ví dụ `TestTransaction`) hoặc dùng `TransactionTemplate` trong test không bị bao bởi test-managed transaction.

`@Order` có thể tham gia việc sắp xếp listener khi cùng điểm xử lý thích hợp, nhưng **không dùng thứ tự ưu tiên để thay thế bảo đảm “sau commit”**. Việc so sánh listener bình thường với listener `AFTER_COMMIT` chỉ bằng các số `@Order` là sai phạm vi.

## 8. Chọn cấp độ kiểm thử phù hợp

| Mức kiểm thử | Nên xác nhận | Điểm cần tránh |
| --- | --- | --- |
| Unit test của listener | Một listener tuân thủ tiền điều kiện, cập nhật đúng trạng thái, xử lý lỗi đúng | Unit test hai method bằng cách gọi thủ công rồi kết luận Spring sắp thứ tự đúng |
| Integration test với Spring Context | `@EventListener`, `@Order`, multicaster thực tế và kết quả business trong cùng một lượt publish | Mock toàn bộ cơ chế dispatch, khiến test không còn kiểm tra cấu hình |
| Integration test có transaction | Không gửi trước commit, gửi sau commit, không gửi sau rollback | Nhầm test rollback mặc định với commit thật |
| Async/concurrency test | Hoàn tất có timeout, quan hệ phụ thuộc đúng, không mất/nhân đôi hiệu ứng | Dựa vào sleep, tốc độ thread hoặc thứ tự log không ổn định |
| End-to-end qua broker/nhiều instance | Hợp đồng thứ tự theo khóa nghiệp vụ, retry và idempotency | Suy từ `@Order` cục bộ thành thứ tự toàn hệ thống |

Nếu chỉ kiểm tra **publisher đã phát sự kiện**, `@RecordApplicationEvents` là công cụ phù hợp. Nếu muốn chứng minh **listener nào chạy trước**, phải quan sát hành vi thực sự của listener qua một context có cấu hình dispatch tương ứng. Nếu muốn chứng minh **quy tắc nghiệp vụ bất biến**, assert trên dữ liệu/trạng thái sau xử lý mới là trọng tâm.

## 9. Lỗi thường gặp và cách tránh

**1. Khóa thứ tự mọi listener vì “đã có `@Order`”.** Thêm listener mới có thể làm test hỏng dù kết quả nghiệp vụ vẫn đúng. Chỉ assert cặp hành động có phụ thuộc đã được phân tích.

**2. Kiểm thử thứ tự bằng cách tự gọi A rồi B.** Cách đó xác nhận code test, không xác nhận `ApplicationEventMulticaster`. Hãy publish qua `ApplicationEventPublisher` trong context có bean listener thật.

**3. Dùng `@RecordApplicationEvents` để kết luận thứ tự thực thi.** Nó ghi lại **event đã publish**; listener của cùng một event không được biểu diễn như một chuỗi “A trước B” trong API đó.

**4. Giả định `@Order` giải quyết cạnh tranh dữ liệu.** Nó không cấp lock, không thiết lập điều phối xuyên thread, không bảo đảm xử lý thành công và không xử lý retry.

**5. Nhầm commit với thời điểm gọi listener bình thường.** Kiểm thử callback transaction phải kiểm soát commit/rollback, cấu hình transaction manager và pha tương ứng.

**6. Assertion phụ thuộc timestamp/log.** Timestamp sát nhau, độ phân giải đồng hồ và buffering log đều có thể gây nhiễu. Nên quan sát dữ liệu nghiệp vụ hoặc một trace có khóa sự kiện ngay tại điểm thay đổi trạng thái.

**7. Không kiểm tra nhánh lỗi.** Với phụ thuộc bắt buộc, hãy thử trường hợp listener chuẩn bị thất bại: thông báo không được phát như thể quy trình đã thành công. Nếu lỗi phải được phục hồi bằng retry/idempotency, đó là hợp đồng riêng cần test.

## 10. Checklist trước khi giữ một order-test trong codebase

- Có thể diễn đạt lý do nghiệp vụ buộc A trước B bằng một câu có thể kiểm chứng.
- Test publish qua Spring context thật và biết rõ multicaster chạy đồng bộ hay bất đồng bộ.
- Test quan sát kết quả và tiền điều kiện, không phụ thuộc thứ tự các bước độc lập.
- Có test/thiết kế riêng cho transaction, thread, hoặc broker nếu những ranh giới đó tồn tại.
- Test sẽ thất bại có ý nghĩa khi thứ tự cần thiết bị đảo, và vẫn pass khi thay đổi các listener không liên quan.
- Nếu phụ thuộc là điều kiện sống còn, cân nhắc điều phối tường minh hoặc event nối tiếp thay vì chỉ dựa vào `@Order`.

**Ghi nhớ:** kiểm thử thứ tự nhằm bảo vệ **quy tắc nghiệp vụ**, không bảo vệ một trật tự tình cờ của framework. Trong mô hình đồng bộ, `@Order` có thể kiểm chứng được bằng một integration test gọn; khi sang async, transaction hoặc đa tiến trình, hợp đồng và test phải bám vào cơ chế bảo đảm tương ứng.

## Tài liệu tham khảo

- [Spring Framework – Application Events và ordering listeners](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework – Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Framework TestContext – Recording Application Events](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/application-events.html)

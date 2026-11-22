# Kiểm chứng listener có điều kiện và lỗi xử lý

Khi một ứng dụng Spring phát sự kiện, việc gọi `ApplicationEventPublisher.publishEvent(...)` mới chỉ xác nhận sự kiện đã được gửi vào cơ chế phát sự kiện của `ApplicationContext`. Ta còn cần kiểm chứng listener phù hợp có thực sự được gọi hay không, điều kiện lọc có loại đúng sự kiện hay không và lỗi từ listener được xử lý theo chính sách nào.

Hai điểm này có quan hệ trực tiếp với nhau. Một listener có thể được đăng ký đúng nhưng bị bỏ qua vì biểu thức `condition` trả về `false`. Ngược lại, listener có thể được gọi đúng nhưng ném exception làm cho lời gọi phát sự kiện thất bại. Bài kiểm thử tốt cần tạo sự kiện thật trong một Spring context, quan sát kết quả xử lý và xác nhận cả đường chạy thành công lẫn đường chạy lỗi.

## 1. Cơ chế cần kiểm chứng

Spring hỗ trợ khai báo listener bằng `@EventListener` trên một bean:

```java
@Component
class PaymentListener {

    @EventListener
    public void onPaymentReceived(PaymentReceived event) {
        // Xử lý sự kiện.
    }
}
```

Khi `ApplicationContext` khởi tạo, Spring phát hiện phương thức có `@EventListener` và đăng ký nó vào bộ phát sự kiện. Khi ứng dụng gọi `publishEvent`, Spring tìm các listener có kiểu tham số tương thích với kiểu sự kiện được phát rồi gọi những listener đó.

Listener có thể khai báo thêm thuộc tính `condition`. Đây là biểu thức Spring Expression Language (SpEL) được đánh giá cho từng sự kiện. Chỉ khi biểu thức trả về `true`, Spring mới gọi phương thức listener. Ví dụ:

```java
@EventListener(condition = "#root.args[0].amount >= 1000")
public void onLargePayment(PaymentReceived event) {
    // Chỉ xử lý khoản thanh toán từ 1.000 trở lên.
}
```

Trong ngữ cảnh biểu thức, `#root.args` là danh sách đối số truyền vào phương thức listener. `#root.args[0]` là đối số đầu tiên, ở ví dụ này chính là sự kiện `PaymentReceived`. Cách viết này thể hiện rõ dữ liệu mà điều kiện đang kiểm tra và không phụ thuộc vào việc Spring có khám phá được tên tham số Java hay không.

Mặc định, `SimpleApplicationEventMulticaster` gọi listener đồng bộ trên luồng phát sự kiện. Vì vậy, kết quả xử lý và exception của listener có thể ảnh hưởng trực tiếp đến lời gọi `publishEvent`. Nếu ứng dụng cấu hình bộ thực thi bất đồng bộ hoặc listener dùng `@Async`, thời điểm và nơi nhận lỗi sẽ thay đổi. Kiểm thử phải phản ánh đúng cấu hình mà ứng dụng đang sử dụng.

## 2. Kiểm chứng điều kiện của listener

Ta dùng một sự kiện đơn giản để kiểm tra ngưỡng thanh toán. Spring cho phép phát một object bất kỳ làm payload event; class sự kiện không bắt buộc phải kế thừa `ApplicationEvent`.

```java
public record PaymentReceived(String paymentId, int amount) {
}
```

Listener lưu lại những sự kiện đã được chấp nhận để bài kiểm thử có thể quan sát kết quả:

```java
import java.util.ArrayList;
import java.util.List;

import org.springframework.context.event.EventListener;

public class LargePaymentListener {

    private final List<PaymentReceived> receivedPayments = new ArrayList<>();

    @EventListener(condition = "#root.args[0].amount >= 1000")
    public void onPaymentReceived(PaymentReceived event) {
        receivedPayments.add(event);
    }

    public List<PaymentReceived> receivedPayments() {
        return List.copyOf(receivedPayments);
    }
}
```

Ta có thể kiểm tra listener bằng `AnnotationConfigApplicationContext`. Đây là Spring context thực, đủ để Spring đăng ký và gọi `@EventListener`, nhưng không cần khởi động toàn bộ Spring Boot application:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

class LargePaymentListenerTest {

    @Test
    void handlesOnlyPaymentsAtOrAboveTheThreshold() {
        try (var context = new AnnotationConfigApplicationContext()) {
            context.registerBean(LargePaymentListener.class);
            context.refresh();

            var listener = context.getBean(LargePaymentListener.class);
            var belowThreshold = new PaymentReceived("PAY-001", 999);
            var atThreshold = new PaymentReceived("PAY-002", 1000);
            var aboveThreshold = new PaymentReceived("PAY-003", 1500);

            context.publishEvent(belowThreshold);
            context.publishEvent(atThreshold);
            context.publishEvent(aboveThreshold);

            assertEquals(
                    List.of(atThreshold, aboveThreshold),
                    listener.receivedPayments());
        }
    }
}
```

Các sự kiện được phát qua `context.publishEvent`, nên bài kiểm thử đi qua cơ chế dispatch thực của Spring. Kết quả mong đợi chứng minh ba trường hợp: khoản thanh toán thấp hơn ngưỡng bị bỏ qua, khoản bằng ngưỡng được xử lý và khoản cao hơn ngưỡng cũng được xử lý.

Khi kiểm tra điều kiện, nên chọn dữ liệu ở hai phía của ngưỡng và ngay tại ngưỡng. Chỉ kiểm tra một giá trị lớn hơn ngưỡng có thể bỏ sót lỗi dùng nhầm `>` thay cho `>=`. Nếu điều kiện có nhiều nhánh, hãy tạo một sự kiện cho từng nhánh và xác nhận tập sự kiện đã xử lý một cách rõ ràng.

### Khi nào nên dùng `@SpringBootTest`?

`AnnotationConfigApplicationContext` phù hợp khi mục tiêu là kiểm tra việc đăng ký listener, đánh giá SpEL và dispatch sự kiện. Dùng `@SpringBootTest` khi listener phụ thuộc vào cấu hình thực của ứng dụng, chẳng hạn bean được tạo bởi component scan, profile, cấu hình điều kiện hoặc các thành phần tích hợp khác.

Trong bài kiểm thử tích hợp, có thể inject `ApplicationEventPublisher` rồi phát sự kiện qua publisher đó. Cần bảo đảm bean listener đang kiểm tra thực sự có trong context của bài test. Nếu thay listener bằng mock hoặc chỉ mock `ApplicationEventPublisher`, bài kiểm thử sẽ không còn xác nhận được cơ chế đăng ký và dispatch của Spring.

## 3. Kiểm chứng lỗi với listener đồng bộ

Với bộ phát sự kiện đồng bộ mặc định, listener được gọi ngay trong lời gọi `publishEvent`. Nếu listener ném một exception không được xử lý, exception runtime có thể truyền ngược về nơi phát sự kiện.

Ví dụ listener từ chối một khoản thanh toán không hợp lệ:

```java
import org.springframework.context.event.EventListener;

public class RejectingPaymentListener {

    @EventListener
    public void onPaymentReceived(PaymentReceived event) {
        throw new IllegalArgumentException(
                "Unsupported payment: " + event.paymentId());
    }
}
```

Bài kiểm thử cần xác nhận exception xuất hiện đúng lúc phát sự kiện và giữ được thông tin lỗi có ý nghĩa:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

class RejectingPaymentListenerTest {

    @Test
    void propagatesRuntimeFailureToThePublisher() {
        try (var context = new AnnotationConfigApplicationContext()) {
            context.registerBean(RejectingPaymentListener.class);
            context.refresh();

            var exception = assertThrows(
                    IllegalArgumentException.class,
                    () -> context.publishEvent(
                            new PaymentReceived("PAY-004", -1)));

            assertEquals("Unsupported payment: PAY-004", exception.getMessage());
        }
    }
}
```

Kiểm thử này xác nhận hợp đồng lỗi của cấu hình đồng bộ mặc định: exception runtime từ listener làm cho thao tác phát sự kiện thất bại. Nếu ứng dụng có cấu hình `ErrorHandler`, executor hoặc cơ chế bất đồng bộ riêng, kết quả có thể khác; khi đó bài kiểm thử phải dựng đúng cấu hình ấy.

## 4. Kiểm chứng `ErrorHandler` của bộ phát sự kiện

Ứng dụng có thể cấu hình `ErrorHandler` cho `SimpleApplicationEventMulticaster` để tập trung xử lý exception phát sinh trong listener. Ví dụ, handler ghi nhận lỗi để logging, giám sát hoặc chuyển tiếp đến một cơ chế xử lý khác.

Ta đăng ký bean có tên `applicationEventMulticaster` trước khi refresh context. Spring sẽ dùng bean này làm bộ phát sự kiện của context:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.event.SimpleApplicationEventMulticaster;
```

Hai listener sau giúp quan sát cả nhánh lỗi và nhánh xử lý bình thường:

```java
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.context.event.EventListener;

public class HealthyPaymentListener {

    private final AtomicInteger handledCount;

    public HealthyPaymentListener(AtomicInteger handledCount) {
        this.handledCount = handledCount;
    }

    @EventListener
    public void onPaymentReceived(PaymentReceived event) {
        handledCount.incrementAndGet();
    }
}
```

`RejectingPaymentListener` ở phần trước là listener cố ý ném `IllegalArgumentException`. Bài kiểm thử cấu hình `ErrorHandler` để ghi nhận exception:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.event.SimpleApplicationEventMulticaster;

class PaymentListenerErrorHandlerTest {

    @Test
    void recordsListenerFailureAndContinuesDispatching() {
        List<Throwable> failures = new ArrayList<>();
        var healthyListenerCalls = new AtomicInteger();

        try (var context = new AnnotationConfigApplicationContext()) {
            context.registerBean(
                    "applicationEventMulticaster",
                    SimpleApplicationEventMulticaster.class,
                    () -> {
                        var multicaster = new SimpleApplicationEventMulticaster();
                        multicaster.setErrorHandler(failures::add);
                        return multicaster;
                    });
            context.registerBean(RejectingPaymentListener.class);
            context.registerBean(
                    HealthyPaymentListener.class,
                    () -> new HealthyPaymentListener(healthyListenerCalls));
            context.refresh();

            context.publishEvent(new PaymentReceived("PAY-005", 1200));

            assertEquals(1, failures.size());
            assertTrue(failures.get(0) instanceof IllegalArgumentException);
            assertEquals(1, healthyListenerCalls.get());
        }
    }
}
```

Trong ví dụ này, `ErrorHandler` nhận exception và trả về bình thường. Bộ phát sự kiện vì thế có thể tiếp tục gọi listener còn lại. Bài kiểm thử xác nhận cả hai kết quả: lỗi đã được ghi nhận và listener khỏe vẫn được gọi.

Hành vi tiếp tục dispatch phụ thuộc vào việc `ErrorHandler` có hoàn tất bình thường hay không. Nếu chính handler ném exception, lỗi đó có thể thoát ra khỏi quá trình phát sự kiện. `ErrorHandler` cũng không tự thực hiện retry; nếu nghiệp vụ yêu cầu thử lại, cần thiết kế và kiểm thử chính sách retry riêng.

## 5. Phân biệt lỗi đồng bộ và bất đồng bộ

Không nên áp dụng kỳ vọng của listener đồng bộ cho listener chạy bất đồng bộ.

| Cấu hình | Nơi thực thi | Cách kiểm chứng lỗi |
|---|---|---|
| `SimpleApplicationEventMulticaster` mặc định | Cùng luồng gọi `publishEvent` | Dùng `assertThrows` để kiểm tra exception truyền về publisher. |
| Multicaster có `TaskExecutor` | Executor được cấu hình | Publisher không nhất thiết chờ listener hoàn tất; kiểm tra kết quả qua cơ chế đồng bộ hóa hoặc trạng thái do listener ghi nhận. |
| Phương thức listener dùng `@Async` | Executor của Spring Async | Với phương thức trả về `void`, cấu hình `AsyncUncaughtExceptionHandler` để quan sát exception. Với kiểu trả về `Future`/`CompletableFuture`, kiểm tra lỗi qua kết quả bất đồng bộ. |

Khi kiểm thử bất đồng bộ, không nên gọi `publishEvent` rồi lập tức kiểm tra một biến đếm và giả định listener đã chạy xong. Dùng `CountDownLatch`, `CompletableFuture` hoặc thư viện chờ điều kiện như Awaitility để đợi một kết quả có giới hạn thời gian. Cách này vừa tránh race condition vừa giúp bài test thất bại rõ ràng khi listener không hoàn tất.

Ví dụ ý tưởng với `CountDownLatch`:

```java
var completed = new CountDownLatch(1);

// Listener gọi completed.countDown() sau khi xử lý xong.
context.publishEvent(event);

assertTrue(completed.await(2, TimeUnit.SECONDS));
```

Đoạn mã trên minh họa cách đồng bộ hóa; trong bài test thực tế, hãy đặt latch vào listener được Spring quản lý và xác nhận thêm kết quả hoặc exception đã được ghi nhận. Tránh dùng `Thread.sleep`, vì thời gian ngủ không chứng minh listener đã hoàn tất và có thể làm bài test chậm hoặc chập chờn.

## 6. Các lỗi kiểm thử thường gặp

### Chỉ phát sự kiện mà không xác nhận kết quả

Lời gọi `publishEvent` thành công không chứng minh listener có điều kiện đã chạy. Điều kiện có thể trả về `false`, kiểu sự kiện có thể không tương thích hoặc bean listener có thể chưa được đăng ký. Hãy xác nhận trạng thái đầu ra, số lần gọi hoặc một hiệu ứng quan sát được.

### Mock publisher khi mục tiêu là kiểm tra dispatch

Mock `ApplicationEventPublisher` chỉ kiểm tra tương tác với mock. Nó không chạy `EventListenerMethodProcessor`, không đánh giá SpEL và không gọi listener. Muốn kiểm tra các hành vi đó, hãy dùng Spring context thật và phát sự kiện qua context hoặc publisher do context cung cấp.

### Chỉ kiểm tra một phía của điều kiện

Với ngưỡng `>= 1000`, cần kiểm tra ít nhất giá trị nhỏ hơn ngưỡng và giá trị bằng ngưỡng. Nếu điều kiện phức tạp hơn, tạo dữ liệu cho từng nhánh để phát hiện biểu thức sai hoặc truy cập nhầm thuộc tính.

### Giả định listener luôn chạy theo thứ tự đăng ký

Không nên dựa vào thứ tự bean được tạo hoặc đăng ký để suy luận thứ tự listener. Nếu thứ tự là yêu cầu nghiệp vụ, khai báo `@Order` phù hợp và viết bài kiểm thử xác nhận thứ tự đó. Nếu thứ tự không phải hợp đồng, hãy kiểm tra kết quả cuối cùng thay vì thứ tự gọi.

### Bỏ qua cấu hình lỗi của ứng dụng

Một test dùng context mặc định có thể cho kết quả khác ứng dụng thực tế nếu ứng dụng cấu hình `ErrorHandler`, executor hoặc `@Async`. Khi kiểm thử tích hợp, cần đưa cấu hình liên quan vào context và xác nhận đúng đường đi của exception.

## 7. Checklist cho bài kiểm thử

- [ ] Spring context có đăng ký bean chứa phương thức `@EventListener`.
- [ ] Kiểu sự kiện được phát tương thích với tham số listener.
- [ ] Có trường hợp điều kiện không thỏa mãn và trường hợp điều kiện thỏa mãn.
- [ ] Các giá trị biên của điều kiện được kiểm tra.
- [ ] Bài test xác nhận listener được gọi hoặc bị bỏ qua bằng kết quả quan sát được.
- [ ] Bài test lỗi xác nhận đúng exception hoặc đúng `ErrorHandler` đã cấu hình.
- [ ] Nếu dispatch bất đồng bộ, bài test chờ kết quả bằng cơ chế đồng bộ hóa có timeout.
- [ ] Bài test không phụ thuộc vào thứ tự listener nếu thứ tự đó không phải hợp đồng của ứng dụng.

Kiểm chứng listener có điều kiện cần xác nhận cả việc Spring dispatch sự kiện và kết quả đánh giá biểu thức SpEL. Kiểm chứng lỗi cần dựng đúng chế độ đồng bộ hoặc bất đồng bộ cùng chính sách `ErrorHandler` của ứng dụng. Khi hai phần này được kiểm tra riêng và kết hợp, bài test sẽ chỉ ra rõ listener nào được gọi, điều kiện nào chặn xử lý và exception được chuyển đến đâu.

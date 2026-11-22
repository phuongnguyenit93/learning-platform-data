# Timeout thông thường so với timeout đổi luồng

Timeout trong JUnit Jupiter giúp phát hiện một test hoặc một đoạn thực thi mất nhiều thời gian hơn giới hạn cho phép. Tuy nhiên, “hết thời gian” có thể được xử lý theo hai cách khác nhau: tiếp tục chạy trên chính thread đang thực thi test và gửi tín hiệu ngắt, hoặc chạy phần việc trong một thread riêng để framework có thể lấy lại quyền điều khiển khi hết hạn.

Sự khác biệt này ảnh hưởng đến lifecycle của test, khả năng dừng tác vụ, transaction, ThreadLocal và các context gắn với thread. Vì vậy, chọn timeout không chỉ là chọn một con số như một giây hay năm giây; còn phải hiểu đoạn code sẽ chạy ở thread nào và chuyện gì xảy ra khi nó không phản hồi tín hiệu ngắt.

## Timeout giải quyết vấn đề gì?

Một test có thể bị treo do deadlock, chờ một dịch vụ không phản hồi, vòng lặp không kết thúc, chờ lock hoặc một tác vụ bất đồng bộ không hoàn thành. Nếu không có giới hạn thời gian, test suite có thể phải chờ rất lâu mới phát hiện lỗi.

JUnit Jupiter cung cấp timeout ở nhiều cấp độ:

- Annotation `@Timeout` đặt giới hạn cho test method hoặc lifecycle method.
- `assertTimeout()` đo thời gian thực thi một đoạn code và thất bại nếu đoạn code chạy quá lâu.
- `assertTimeoutPreemptively()` chạy đoạn code trong thread riêng và áp dụng timeout theo hướng preemptive.

Ba cách này có mục đích gần nhau nhưng ngữ nghĩa thực thi khác nhau. Đặc biệt, `assertTimeout()` không dừng đoạn code ngay tại deadline; còn `assertTimeoutPreemptively()` chuyển đoạn code sang thread khác.

## Hai thread mode của @Timeout

JUnit Jupiter có annotation `@Timeout` với thuộc tính `threadMode`. Hai chế độ chính là `SAME_THREAD` và `SEPARATE_THREAD`; chế độ `INFERRED` cho phép lấy lựa chọn từ cấu hình JUnit.

### SAME_THREAD: thực thi trên thread hiện tại

Nếu không chỉ định thread mode khác, `@Timeout` mặc định sử dụng `SAME_THREAD` trong cấu hình thông thường. Phương thức test chạy trên cùng thread mà JUnit dùng để gọi nó.

~~~java
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;

class SameThreadTimeoutTest {

    @Test
    @Timeout(value = 2, unit = TimeUnit.SECONDS)
    void completesWithinTwoSeconds() {
        performOperation();
    }

    private void performOperation() {
        // Hành vi cần kiểm tra.
    }
}
~~~

Khi thời gian vượt quá giới hạn, JUnit gửi tín hiệu interrupt đến thread thực thi test. Thread vẫn phải hợp tác với cơ chế interrupt để dừng kịp thời. Ví dụ, các thao tác chờ như `Thread.sleep()`, `BlockingQueue.take()` hoặc một số thao tác I/O có thể ném `InterruptedException`.

Điểm quan trọng là interrupt không phải lệnh cưỡng bức kết thúc thread. Nếu code bắt `InterruptedException` rồi bỏ qua, hoặc chạy vòng lặp không kiểm tra trạng thái interrupt, phương thức có thể tiếp tục chạy. Vì test vẫn chiếm thread thực thi đó, JUnit không thể đơn giản thu hồi thread và chuyển sang chạy phần tiếp theo như thể tác vụ đã kết thúc.

Ưu điểm của `SAME_THREAD` là phương thức test chạy cùng thread với phần lifecycle gọi nó. Những dữ liệu gắn với thread như transaction test-managed của Spring, security context hoặc MDC có thể tiếp tục được nhìn thấy theo cách thông thường trong đoạn code đồng bộ của test.

### SEPARATE_THREAD: thực thi trên thread riêng

Với `SEPARATE_THREAD`, JUnit chạy phương thức test trên một thread riêng. Khi timeout xảy ra, JUnit gửi interrupt đến thread thực thi đó và có thể tiếp tục điều khiển test engine mà không phải chờ vô hạn trên thread gọi test.

~~~java
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;

class SeparateThreadTimeoutTest {

    @Test
    @Timeout(
        value = 2,
        unit = TimeUnit.SECONDS,
        threadMode = Timeout.ThreadMode.SEPARATE_THREAD
    )
    void completesWithinTwoSeconds() {
        performOperation();
    }

    private void performOperation() {
        // Hành vi cần kiểm tra.
    }
}
~~~

Chế độ này hữu ích khi muốn giới hạn thời gian một đoạn test có thể chiếm thread điều khiển của JUnit. Nếu code phản hồi interrupt, thread riêng sẽ dừng và test thất bại vì vượt deadline.

Tuy nhiên, nếu code không phản hồi interrupt, nó có thể tiếp tục chạy trong thread riêng ngay cả sau khi JUnit đã đánh dấu test thất bại và tiếp tục xử lý test khác. Thread còn sống có thể tiếp tục sửa database, ghi file, giữ lock, gửi message hoặc làm thay đổi trạng thái dùng chung. Do đó, `SEPARATE_THREAD` không phải cơ chế kill thread an toàn.

### INFERRED: lấy thread mode từ cấu hình

`Timeout.ThreadMode.INFERRED` yêu cầu JUnit xác định thread mode dựa trên configuration parameter `junit.jupiter.execution.timeout.thread.mode.default`. Cách này hữu ích khi dự án muốn thống nhất chính sách timeout qua cấu hình mà không phải khai báo lại mode ở từng test.

Nếu không có cấu hình thay thế, hành vi mặc định của JUnit là `SAME_THREAD`. Khi sử dụng cấu hình chung, hãy ghi rõ giá trị trong tài liệu hoặc cấu hình test của dự án để người đọc biết test đang chạy trên thread nào.

## So sánh @Timeout, assertTimeout và assertTimeoutPreemptively

JUnit có cả timeout dạng annotation và timeout dạng assertion. Khi đọc một test, cần nhìn vào API được sử dụng thay vì chỉ nhìn tên “timeout”.

| API | Thread thực thi | Khi vượt thời gian | Đặc điểm chính |
|---|---|---|---|
| `@Timeout` với `SAME_THREAD` | Thread gọi test | Gửi interrupt đến thread đó | Giữ cùng thread với lifecycle của test |
| `@Timeout` với `SEPARATE_THREAD` | Thread riêng | Gửi interrupt đến thread riêng; engine có thể tiếp tục nếu thread không dừng | Tách việc thực thi khỏi thread điều khiển |
| `assertTimeout()` | Thread gọi assertion | Chờ đoạn code hoàn tất rồi mới báo thất bại nếu quá hạn | Không preempt đoạn code tại deadline |
| `assertTimeoutPreemptively()` | Thread riêng | Hết hạn thì interrupt thread thực thi và báo timeout | Có thể lấy lại quyền điều khiển sớm hơn, nhưng thay đổi thread context |

### assertTimeout: đợi hoàn tất rồi mới kết luận

`assertTimeout()` chạy đoạn code trên cùng thread đang gọi assertion. Nếu thời gian thực thi vượt giới hạn, assertion chỉ báo thất bại sau khi đoạn code đã kết thúc.

~~~java
import java.time.Duration;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertTimeout;

class AssertTimeoutTest {

    @Test
    void operationShouldFinishWithinOneSecond() {
        assertTimeout(Duration.ofSeconds(1), () -> {
            service.performOperation();
        });
    }
}
~~~

Ví dụ trên kiểm tra thời lượng thực tế. Nếu `performOperation()` mất ba giây, assertion thất bại sau khi lời gọi ba giây hoàn tất. Nó không ngắt lời gọi ở giây thứ nhất.

Cách này phù hợp khi cần đo thời gian một đoạn code nhưng muốn giữ nguyên thread context. Nó không phù hợp để bảo vệ test suite khỏi một đoạn code có khả năng treo vô hạn, vì assertion phải chờ đoạn code trở về mới có thể kết luận.

### assertTimeoutPreemptively: thực thi đoạn code ở thread riêng

`assertTimeoutPreemptively()` chạy executable hoặc supplier trên một thread riêng. Nếu quá thời gian, JUnit gửi interrupt và báo timeout mà không phải chờ vô hạn trên thread gọi assertion.

~~~java
import java.time.Duration;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertTimeoutPreemptively;

class PreemptiveTimeoutTest {

    @Test
    void operationShouldFinishWithinOneSecond() {
        assertTimeoutPreemptively(Duration.ofSeconds(1), () -> {
            service.performOperation();
        });
    }
}
~~~

Cách này có tính chất gần với `@Timeout(threadMode = SEPARATE_THREAD)`: đoạn code chạy ở thread khác và có thể không còn thấy những context gắn với thread ban đầu. Nếu đoạn code bỏ qua interrupt, nó vẫn có thể tiếp tục chạy sau khi assertion đã thất bại.

Vì thế, không nên thay tất cả `assertTimeout()` bằng `assertTimeoutPreemptively()` chỉ vì muốn test “dừng nhanh hơn”. Hãy cân nhắc thread context và side effect trước khi chuyển sang chế độ preemptive.

## Thread context thay đổi như thế nào?

Java có nhiều cơ chế gắn trạng thái vào thread hiện tại. Ví dụ:

- `ThreadLocal` lưu dữ liệu riêng theo từng thread.
- Spring Test thường gắn transaction test-managed với thread thực thi test.
- Spring Security có thể lưu SecurityContext theo thread.
- Logging framework có thể lưu MDC theo thread.
- `RequestContextHolder` của Spring giữ thông tin request theo thread trong các tình huống đồng bộ.

Khi đoạn code chạy trên thread riêng, những giá trị trên không tự động được chuyển từ thread của test sang thread mới. Nếu code dựa vào chúng, hành vi có thể khác với lúc chạy đồng bộ trên thread ban đầu.

### Rủi ro với transaction của Spring Test

Spring Test thường bắt đầu transaction cho test và gắn transaction đó với thread thực thi test. Hãy hình dung test có dạng:

~~~java
@SpringJUnitConfig(PersistenceTestConfig.class)
@Transactional
class CustomerTimeoutTest {

    @Autowired
    private CustomerRepository customerRepository;

    @Test
    void insertsCustomer() {
        assertTimeoutPreemptively(
            Duration.ofSeconds(2),
            () -> customerRepository.save(new Customer("C-200", "Lan"))
        );
    }
}
~~~

Trong ví dụ này, transaction do Spring Test quản lý nằm trên thread của test. Phần lambda bên trong `assertTimeoutPreemptively()` chạy ở thread khác, nên nó không tự động tham gia transaction test-managed đó.

Nếu repository hoặc service bắt đầu một transaction riêng trên thread mới, thay đổi có thể được commit độc lập. Khi thread test kết thúc và rollback transaction của nó, thay đổi được commit từ thread kia có thể vẫn còn trong database.

Đây là lý do quan trọng để tránh dùng timeout đổi luồng cho đoạn code cần tham gia transaction test-managed. Với Spring Test, nên ưu tiên `SAME_THREAD` hoặc `assertTimeout()` khi cần giữ transaction và thread context hiện tại. Nếu bắt buộc kiểm tra hành vi đa luồng, hãy thiết kế transaction và cleanup phù hợp cho từng thread thay vì dựa vào rollback của thread test.

Cảnh báo này cũng áp dụng với security context, request context và MDC: nếu test cần các giá trị đó, phải truyền hoặc thiết lập chúng có chủ đích trên thread thực thi.

## Interrupt là tín hiệu hợp tác, không phải lệnh giết thread

Cả `SAME_THREAD` và `SEPARATE_THREAD` đều dựa vào interrupt để báo cho đoạn code rằng thời gian đã hết. Code cần phản hồi tín hiệu này đúng cách.

Ví dụ, nếu phải bắt `InterruptedException`, hãy khôi phục trạng thái interrupt hoặc truyền exception ra ngoài:

~~~java
void waitForWork() {
    try {
        Thread.sleep(10_000);
    } catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
        throw new IllegalStateException("Operation was interrupted", ex);
    }
}
~~~

Không nên nuốt interrupt:

~~~java
void waitIncorrectly() {
    try {
        Thread.sleep(10_000);
    } catch (InterruptedException ignored) {
        // Bỏ qua tín hiệu hủy.
    }
}
~~~

Trong ví dụ sai, code xóa trạng thái interrupt và tiếp tục như thể không có yêu cầu dừng. Nếu thao tác thực tế là vòng lặp dài, cần kiểm tra `Thread.currentThread().isInterrupted()` tại các điểm an toàn và kết thúc công việc khi nhận tín hiệu.

Không phải mọi thao tác đều có thể bị interrupt. Một đoạn CPU-bound không kiểm tra cờ interrupt có thể tiếp tục vô thời hạn. Một lời gọi native hoặc thư viện không hỗ trợ cancellation cũng có thể không dừng theo cách mong muốn. Timeout báo lỗi cho test; nó không đảm bảo mọi tài nguyên do test tạo ra đã được thu hồi.

Khi dùng `SEPARATE_THREAD` hoặc `assertTimeoutPreemptively()`, hãy đặc biệt cẩn thận với thread còn chạy nền sau timeout. Cần có cơ chế đóng tài nguyên, hủy tác vụ, chờ thread kết thúc và tránh để tác vụ đó tiếp tục sửa dữ liệu mà test sau sẽ sử dụng.

## Khi nào chọn từng cách?

| Tình huống | Lựa chọn nên cân nhắc | Lý do |
|---|---|---|
| Test đồng bộ thông thường, cần giữ transaction hoặc ThreadLocal | `@Timeout` mặc định / `SAME_THREAD` | Không chuyển phần thực thi sang thread khác |
| Cần xác nhận thời lượng một lời gọi nhưng vẫn muốn chờ nó hoàn tất | `assertTimeout()` | Cùng thread, không preempt |
| Đoạn code có nguy cơ treo và cần JUnit lấy lại quyền điều khiển | `SEPARATE_THREAD` hoặc `assertTimeoutPreemptively()` | Tách đoạn thực thi khỏi thread gọi |
| Test phụ thuộc Spring test-managed transaction | Ưu tiên `SAME_THREAD` hoặc `assertTimeout()` | Giữ transaction gắn với thread của test |
| Kiểm thử tác vụ bất đồng bộ do ứng dụng chủ động tạo | Chờ Future/CompletionStage hoặc điều kiện hoàn tất có timeout | Timeout của test method không tự chứng minh worker task đã kết thúc |
| Đo hiệu năng hoặc benchmark | Công cụ benchmark chuyên dụng | Timeout test không phải phép đo hiệu năng ổn định |

Với tác vụ bất đồng bộ, hãy chờ chính kết quả của tác vụ:

~~~java
@Test
void asynchronousOperationCompletes() throws Exception {
    Future<Result> future = executor.submit(() -> service.performAsyncWork());

    Result result = future.get(2, TimeUnit.SECONDS);

    assertThat(result.isSuccessful()).isTrue();
}
~~~

`Future.get(timeout, unit)` giới hạn thời gian chờ kết quả. Nếu hết hạn, nó ném `TimeoutException`; test có thể gọi `future.cancel(true)` và thực hiện cleanup. Việc hủy vẫn dựa vào tác vụ hợp tác với interrupt, nên cần quản lý vòng đời executor và tài nguyên liên quan.

## Cấu hình timeout nhất quán trong dự án

Có thể đặt timeout ở cấp phương thức:

~~~java
@Test
@Timeout(value = 3, unit = TimeUnit.SECONDS)
void respondsWithinBudget() {
    service.respond();
}
~~~

Hoặc đặt ở cấp class để áp dụng một giới hạn chung cho các phương thức thuộc class:

~~~java
@Timeout(value = 5, unit = TimeUnit.SECONDS)
class ServiceIntegrationTest {

    @Test
    void firstScenario() {
        // ...
    }

    @Test
    void secondScenario() {
        // ...
    }
}
~~~

JUnit Jupiter cũng cho phép cấu hình thread mode mặc định qua configuration parameter `junit.jupiter.execution.timeout.thread.mode.default`. Khi dùng `Timeout.ThreadMode.INFERRED`, mode được suy ra từ cấu hình đó. Nên ghi rõ cấu hình trong `junit-platform.properties` hoặc cấu hình test tương ứng để chính sách không phụ thuộc vào môi trường chạy khó quan sát.

Không nên đặt timeout quá sát thời gian chạy trung bình. CI có thể chậm do tải máy, khởi tạo context, I/O hoặc chạy song song. Giới hạn quá nhỏ làm test chập chờn và biến nhiễu môi trường thành lỗi giả. Timeout nên phản ánh ngưỡng tối đa hợp lý cho hành vi, có đủ biên độ cho biến động thông thường.

## Các nhầm lẫn thường gặp

**Nghĩ rằng timeout hết hạn sẽ giết thread.** JUnit gửi interrupt. Code không phản hồi có thể vẫn chạy. Cần thiết kế cancellation và cleanup rõ ràng.

**Nghĩ rằng `assertTimeout()` dừng code ngay tại deadline.** Nó đợi code hoàn tất rồi mới so sánh thời gian. Muốn preempt cần hiểu rõ `assertTimeoutPreemptively()` hoặc `SEPARATE_THREAD`.

**Dùng timeout đổi luồng cho test có transaction Spring.** Transaction test-managed thường gắn với thread ban đầu. Đoạn code trên thread khác có thể chạy ngoài transaction đó và để lại dữ liệu đã commit.

**Cho rằng thread riêng tự động an toàn hơn.** Thread riêng tách việc thực thi khỏi thread gọi nhưng có thể tiếp tục chạy sau timeout, giữ tài nguyên hoặc làm hỏng trạng thái dùng chung.

**Dùng timeout để đo benchmark.** Test timeout chủ yếu phát hiện hành vi quá thời hạn hoặc bị treo. Đo hiệu năng cần kiểm soát warm-up, dữ liệu, JVM, tải máy và thống kê bằng công cụ benchmark.

**Không dọn dẹp sau khi tác vụ timeout.** Một test thất bại không đồng nghĩa thread nền đã dừng, file đã xóa hoặc message đã thu hồi. Cleanup phải bao phủ các tài nguyên do test tạo ra.

## Cách chọn timeout có chủ đích

Trước khi thêm timeout, hãy xác định đoạn code nào cần được giới hạn và vì sao nó có thể mất quá nhiều thời gian. Nếu test cần giữ thread context của Spring, hãy chọn cách chạy cùng thread. Nếu chỉ muốn kiểm tra thời lượng một thao tác đồng bộ, `assertTimeout()` là lựa chọn dễ hiểu. Nếu cần tách đoạn code khỏi thread gọi để engine có thể tiếp tục sau deadline, hãy cân nhắc timeout đổi luồng và chuẩn bị cho khả năng tác vụ không phản hồi interrupt.

Đối với công việc bất đồng bộ, giới hạn thời gian chờ kết quả của chính Future hoặc CompletionStage, rồi hủy và dọn dẹp tác vụ khi cần. Đối với mọi chế độ, hãy bảo đảm code phản hồi interrupt, không để side effect tồn tại ngoài phạm vi test và không để thread cũ tiếp tục ảnh hưởng đến test sau.

`SAME_THREAD` ưu tiên tính liên tục của thread context; `SEPARATE_THREAD` ưu tiên tách phần thực thi khỏi thread điều khiển; `assertTimeout()` đo thời gian mà không preempt; `assertTimeoutPreemptively()` chạy callback trên thread riêng. Chọn đúng cơ chế giúp timeout phát hiện test bị chậm hoặc treo mà không vô tình làm sai transaction, context hay dữ liệu của bài kiểm thử.

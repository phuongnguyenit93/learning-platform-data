# Đo thời gian bằng điểm bắt đầu và khối dọn dẹp

## 1. Mục tiêu của đo thời gian trong around advice

Trong lập trình hướng khía cạnh (Aspect-Oriented Programming — AOP), một **around advice** bao quanh join point được pointcut lựa chọn. Nó có thể thực hiện công việc trước khi chuyển điều khiển tới thao tác gốc, gọi thao tác gốc qua cơ chế **`proceed`** hoặc một hàm chuyển tiếp tương đương, rồi thực hiện công việc khi thao tác kết thúc. Mẫu đo thời gian tiêu biểu là:

> **Lấy mốc bắt đầu trước khi chuyển tiếp, gọi thao tác cần đo, và tính thời gian đã trôi qua trong khối dọn dẹp được bảo đảm chạy khi rời phạm vi.**

Với Java, ta thường dùng `System.nanoTime()` để đo **elapsed time** (thời lượng đã trôi qua), kết hợp `try/finally` để ghi nhận cả trường hợp trả về bình thường lẫn trường hợp ném ngoại lệ.

Ở bài này, **điểm bắt đầu** là thời điểm lấy số đo trước khi gọi `proceed`; **khối dọn dẹp** là `finally` bao quanh lời gọi ấy. Từ “dọn dẹp” không bắt buộc phải giải phóng file hay connection: trong ví dụ, nó là nơi **chốt phép đo và cập nhật số liệu** ngay trước khi rời phạm vi around advice.

Ví dụ, phương thức `checkout()` có thể hoàn tất thành công trong một lần gọi nhưng ném `IllegalArgumentException` trong lần khác. Nếu chỉ lấy thời gian ở nhánh thành công, ta sẽ thiếu dữ liệu của những ca thất bại — đôi khi chính là những ca chậm cần điều tra. Khi đặt phép tính elapsed trong `finally`, ta có thể quan sát cả hai nhánh **mà không buộc phải bắt và nuốt ngoại lệ nghiệp vụ**.

## 2. Luồng điều khiển cốt lõi

Sơ đồ ý niệm:

~~~text
Caller
  |
  v
[Join point khớp pointcut]
  |
  v
[Around advice]
  |
  +-- start = monotonicNow()
  |
  +-- try -------------------------+
  |      |                         |
  |      v                         |
  |    proceed()                  |
  |      |                         |
  |      +--> normal return -------+
  |      |                         |
  |      +--> exception -----------+
  |                                |
  +-- finally ---------------------+
         |
         +-- end = monotonicNow()
         +-- elapsed = end - start
         +-- record(elapsed)
  |
  v
Caller nhận kết quả hoặc ngoại lệ
~~~

Với `try/finally`, mã trong `finally` chạy khi đường `try` **rời phạm vi theo cơ chế thực thi thông thường của Java**. Nó chạy khi `proceed` trả bình thường hoặc ném ngoại lệ, kể cả khi nhánh `try` thực hiện `return`. Tuy nhiên:

- `finally` không phải bảo đảm tuyệt đối khi tiến trình bị kết thúc cưỡng bức, máy ảo dừng bất thường hoặc phạm vi advice chưa từng được đi vào.
- Nếu chính mã `finally` ném một ngoại lệ khác, ngoại lệ ấy **có thể thay thế lỗi gốc** hoặc làm caller không nhận kết quả vốn đã tính thành công.
- Nếu pointcut không khớp hoặc một đường gọi bỏ qua proxy/weaving, không có advice được kích hoạt và khối `finally` của advice cũng không chạy.
- Nếu around advice cố ý **không gọi `proceed`**, phép đo có thể là thời gian của đường fallback/cache/từ chối trong advice, không phải thời gian nghiệp vụ gốc.
- Nếu `proceed` được gọi nhiều lần để retry, định nghĩa thời lượng có thể là thời gian của toàn bộ chuỗi thử hoặc chỉ từng lần thử, tùy vị trí đo.

Bởi vậy, ngoài việc viết đúng `try/finally`, người thiết kế phải định nghĩa **chính xác phạm vi đang đo**.

## 3. `System.nanoTime()` khác `System.currentTimeMillis()` như thế nào?

Java cung cấp nhiều API liên quan đến thời gian, nhưng không phải API nào cũng phục vụ đo elapsed time.

| API | Ý nghĩa | Dùng cho phép đo nào? |
| --- | --- | --- |
| `System.nanoTime()` | Giá trị bộ đếm thời gian độ phân giải nano giây, mốc gốc tùy ý | **Đo khoảng thời gian** giữa hai lần đọc trong cùng tiến trình |
| `System.currentTimeMillis()` | Thời điểm lịch/epoch theo milli giây | Ghi mốc thời gian thực tế, đối chiếu với hệ thống ngoài |
| `Instant.now()` | Đối tượng thời điểm theo clock thời gian thực | Audit mốc giờ, dữ liệu có ý nghĩa lịch |
| `Duration` | Biểu diễn một khoảng thời gian với đơn vị rõ ràng | Lưu trữ, hiển thị và tính toán thời lượng đã xác định |

**Vì sao ưu tiên `nanoTime`?** Phép đo thời lượng cần lấy **hiệu số giữa hai mốc** của cùng đồng hồ monotonic phục vụ đo interval. Đồng hồ lịch có thể được điều chỉnh do đồng bộ giờ hoặc thay đổi cấu hình hệ thống, khiến một phép lấy hiệu thời điểm lịch không phải lựa chọn lý tưởng cho đo latency.

Cách tính:

~~~java
long started = System.nanoTime();
try {
    return operation();
} finally {
    long elapsedNanos = System.nanoTime() - started;
    recordElapsed(elapsedNanos);
}
~~~

Đây là **đoạn minh họa**, chưa độc lập vì `operation()` và `recordElapsed()` được đại diện bằng tên hàm giả định. Đoạn Java chạy đầy đủ xuất hiện ở phần sau.

Lưu ý:

1. **Đơn vị nano giây không đồng nghĩa với độ chính xác thực tế một nano giây.** Độ phân giải và sai số phụ thuộc JVM, hệ điều hành, bộ đếm phần cứng và tải hệ thống.
2. Giá trị tuyệt đối của `nanoTime()` **không có ý nghĩa lịch** và có thể mang dấu âm vì mốc gốc tùy ý. Chỉ quan tâm `end - start` trong cùng hệ đồng hồ.
3. Không lấy `nanoTime()` rồi diễn giải như số nano giây từ Unix epoch. Muốn log lúc nào lời gọi bắt đầu theo giờ thực, ghi thêm một timestamp riêng.
4. Với các interval thực tế ngắn hơn phạm vi tràn số của phép trừ `long` (xấp xỉ 292 năm), cách lấy hiệu thời gian thông thường là phù hợp. Không lưu mốc bắt đầu vào cấu trúc tồn tại qua nhiều tiến trình và mặc định chúng có cùng mốc `nanoTime`.
5. Nếu chỉ muốn hiển thị milli giây, chuyển **sau khi đã tính hiệu**: `TimeUnit.NANOSECONDS.toMillis(elapsedNanos)`. Việc làm tròn có thể khiến nhiều lời gọi nhanh đều hiện `0 ms`.
6. Đo trên một đường chạy thực có độ biến thiên. **Không khẳng định** phép đo trong một lần chạy là số hằng chính xác hoặc luôn ổn định giữa các lần chạy.

## 4. Dùng `try/finally` để bảo toàn cả hai đường kết thúc

Mẫu đáng nhớ:

~~~java
long started = System.nanoTime();
try {
    return proceed();
} finally {
    long elapsed = System.nanoTime() - started;
    metrics.record(elapsed);
}
~~~

Về ngữ nghĩa Java:

- Nếu `proceed()` trả một giá trị bình thường, `finally` chạy **trước khi caller nhận được** giá trị `return` từ wrapper; sau đó giá trị được chuyển tiếp.
- Nếu `proceed()` ném một ngoại lệ, `finally` vẫn chạy trong quá trình tháo ngăn xếp; nếu `finally` không tạo ngoại lệ khác, ngoại lệ gốc tiếp tục lan truyền.
- Nếu wrapper cần hỗ trợ method `void` hoặc giá trị `null`, adapter/engine phải giữ đúng hợp đồng return type; không được ép mọi kết quả thành `String`.
- Nếu `metrics.record(...)` chậm hoặc lỗi, nó có thể làm thay đổi latency và kết quả mà caller quan sát. **`finally` chỉ bảo đảm nơi mã được thực thi, không tự làm mã metrics an toàn.**

Trong một advice chỉ đo lường, việc **trả lại nguyên kết quả và ném lại nguyên ngoại lệ** là bất biến thiết kế tốt. Không cần `catch (Throwable)` quanh toàn bộ target chỉ để đo elapsed time; `finally` đủ để chốt thời gian ở hai nhánh. Chỉ thêm `catch` khi có nhu cầu phân loại lỗi hoặc chính sách chuyển đổi đã được công bố.

## 5. Điều gì chính xác được tính vào thời gian đo?

Khoảng thời gian bằng:

\[
\Delta t = t_{\mathrm{end}} - t_{\mathrm{start}}
\]

Nếu bắt đầu ngay trước `proceed` và kết thúc ngay sau khi `proceed` rời phạm vi:

- Bao gồm thời gian thực thi thao tác gốc **cùng mọi tầng advice nằm bên trong** ranh giới đo.
- Có thể bao gồm thời gian chờ khóa, I/O, scheduling delay, garbage collection hoặc các tác vụ đồng bộ mà thao tác thực hiện.
- Không đo riêng **CPU time**. Elapsed/wall-clock duration có thể lớn dù thread dành phần lớn thời gian chờ.
- Không nhất thiết bao gồm logic chạy **trước khi đo bắt đầu** hoặc **sau khi đã tính end**, bao gồm thao tác gửi metric nếu vị trí đặt end trước khi ghi metric.
- Không tự bao gồm công việc bất đồng bộ tiếp tục sau khi phương thức đã trả Future hoặc schedule task.

Ví dụ:

~~~text
Around outer metric: start
  Audit before
    Authorization check
      Business performs I/O
    Authorization after
  Audit after
Around outer metric: end
Send metric
~~~

Nếu `outer metric` đo bao ngoài toàn chuỗi, số đo có thể bao gồm audit, kiểm quyền và nghiệp vụ bên trong. Nếu chỉ muốn **thời gian thực thi nghiệp vụ sau kiểm quyền**, phải chọn ranh giới hoặc precedence khác. Đừng đặt tên metric `business_duration` khi thực tế nó đo cả một chuỗi wrapper.

### 5.1. Thời gian do chính metrics gây ra

Thông thường, người viết lấy `end` **trước khi gọi sink metrics** để tránh cộng chính việc phát metric vào thời lượng của thao tác đang đo. Điều đó không có nghĩa metrics miễn phí: nếu sink chạy đồng bộ trên cùng lời gọi, caller vẫn phải đợi sink hoàn thành. Khi cần đánh giá **end-to-end caller latency**, phải đo ở một ranh giới ngoài hơn hoặc dùng một phép đo độc lập tính cả overhead.

### 5.2. Nested join points và đo nhiều lần

Nếu `checkout()` gọi `reserve()` và cả hai đều khớp pointcut:

~~~text
measure(checkout)
  checkout
    measure(reserve)
      reserve
~~~

Ta có hai số đo. Thời gian `checkout` có thể **bao gồm** thời gian `reserve`. Cộng hai số đo rồi gọi tổng là “thời gian CPU” hoặc “tổng latency không trùng lặp” sẽ dẫn đến **double-counting**. Cần phân biệt inclusive duration và exclusive duration hoặc phân tích theo trace/span parent-child.

### 5.3. Retry và đo từng lần thử

Nếu advice retry bao trong stopwatch:

~~~text
Stopwatch
  Retry
    attempt 1 -> failed
    attempt 2 -> success
~~~

Stopwatch có thể báo thời gian **cả hai lần thử cùng khoảng chờ**. Nếu stopwatch nằm bên trong retry, mỗi attempt có phép đo riêng. Cả hai đều hợp lý khi được đặt tên rõ `request_duration` và `attempt_duration`. Khi đo retry, tuyệt đối không để đo lường vô tình thay đổi số lần gọi `proceed`.

## 6. Ví dụ Java 17+: around advice đo thời gian với `finally`

Ví dụ chạy độc lập này dùng **JDK dynamic proxy** để mô phỏng một around advice quanh phương thức `buy(int)`; `health()` nằm ngoài bộ chọn nên không được đo. `CheckoutCore` giữ logic nghiệp vụ, `StopwatchAdvice` chỉ bọc và ghi thời gian, `Metrics` là sink chuyên trách.

Để đầu ra **có thể kiểm chứng chính xác**, chương trình sử dụng một **đồng hồ giả monotonic** trả các mốc `0, 100, 200, ...` theo thứ tự. Khi triển khai thực tế, cung cấp `System::nanoTime` thay cho đồng hồ giả. Giá trị `100ns` trong đầu ra **chỉ là phép đo giả lập để kiểm thử**, không phải khẳng định code thật luôn mất 100 nano giây.

Tạo file `AroundTimingDemo.java`:

~~~java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.function.LongSupplier;

public final class AroundTimingDemo {
    interface Checkout {
        String buy(int quantity);
        String health();
    }

    static final class CheckoutCore implements Checkout {
        private int successes;

        @Override
        public String buy(int quantity) {
            if (quantity <= 0) {
                throw new IllegalArgumentException("quantity must be positive");
            }
            successes++;
            System.out.println("BUSINESS buy " + quantity);
            return "order:" + quantity;
        }

        @Override
        public String health() {
            return "READY";
        }

        int successes() {
            return successes;
        }
    }

    @FunctionalInterface
    interface Proceeding {
        Object proceed() throws Throwable;
    }

    static final class Metrics {
        boolean unavailable;

        void record(String operation, long elapsedNanos) {
            if (unavailable) {
                throw new IllegalStateException("sink unavailable");
            }
            System.out.println("METRIC " + operation + " " + elapsedNanos + "ns");
        }
    }

    static final class StopwatchAdvice {
        private final LongSupplier clock;
        private final Metrics metrics;

        StopwatchAdvice(LongSupplier clock, Metrics metrics) {
            this.clock = clock;
            this.metrics = metrics;
        }

        Object around(String operation, Proceeding next) throws Throwable {
            long started = clock.getAsLong();
            try {
                return next.proceed();
            } finally {
                long elapsed = clock.getAsLong() - started;
                try {
                    metrics.record(operation, elapsed);
                } catch (RuntimeException sinkFailure) {
                    System.out.println("METRIC_ERROR " + operation + " "
                            + sinkFailure.getClass().getSimpleName());
                }
            }
        }
    }

    static Object targetCall(Checkout target, Method method, Object[] args)
            throws Throwable {
        try {
            return method.invoke(target, args);
        } catch (InvocationTargetException wrapper) {
            throw wrapper.getCause();
        }
    }

    static Checkout instrument(Checkout target, StopwatchAdvice timer) {
        return (Checkout) Proxy.newProxyInstance(
                Checkout.class.getClassLoader(),
                new Class<?>[] { Checkout.class },
                (proxy, method, args) -> {
                    if (!method.getName().equals("buy")) {
                        return targetCall(target, method, args);
                    }
                    return timer.around("buy",
                            () -> targetCall(target, method, args));
                });
    }

    public static void main(String[] args) {
        // Fake monotonic clock: 0, 100, 200, ... for stable demo output.
        final long[] ticks = {0L};
        LongSupplier fakeClock = () -> {
            long now = ticks[0];
            ticks[0] += 100L;
            return now;
        };
        Metrics metrics = new Metrics();
        CheckoutCore core = new CheckoutCore();
        Checkout api = instrument(core, new StopwatchAdvice(fakeClock, metrics));

        System.out.println("STATUS " + api.health());
        System.out.println("RESULT " + api.buy(2));
        try {
            api.buy(0);
        } catch (IllegalArgumentException error) {
            System.out.println("CALLER " + error.getMessage());
        }
        metrics.unavailable = true;
        System.out.println("RESULT " + api.buy(3));
        try {
            api.buy(-1);
        } catch (IllegalArgumentException error) {
            System.out.println("CALLER " + error.getMessage());
        }
        System.out.println("BUSINESS_SUCCESSES " + core.successes());
    }
}
~~~

Biên dịch và chạy trên JDK 17 hoặc mới hơn:

~~~bash
javac --release 17 -encoding UTF-8 AroundTimingDemo.java
java AroundTimingDemo
~~~

Đầu ra đã kiểm chứng:

~~~text
STATUS READY
BUSINESS buy 2
METRIC buy 100ns
RESULT order:2
METRIC buy 100ns
CALLER quantity must be positive
BUSINESS buy 3
METRIC_ERROR buy IllegalStateException
RESULT order:3
METRIC_ERROR buy IllegalStateException
CALLER quantity must be positive
BUSINESS_SUCCESSES 2
~~~

### 6.1. Phân tích ba nhánh đo

**Nhánh thành công, sink hoạt động:** `buy(2)` trả `"order:2"`, `finally` nhận hai mốc giả cách nhau `100ns`, sink ghi metric, rồi caller nhận kết quả ban đầu. Không có phép biến đổi return.

**Nhánh target ném ngoại lệ, sink hoạt động:** `buy(0)` ném `IllegalArgumentException` trước khi in `BUSINESS buy`. `finally` vẫn chạy và ghi `METRIC buy 100ns`. Caller nhận lại thông điệp lỗi nghiệp vụ. Advice không biến một lần thất bại thành “thành công”.

**Nhánh sink lỗi, target thành công hoặc thất bại:** sau khi `metrics.unavailable=true`, hai lượt `buy(3)` và `buy(-1)` khiến sink tự ném `IllegalStateException`. Ví dụ bắt **riêng lỗi RuntimeException của sink** và in `METRIC_ERROR`, không để nó che kết quả `"order:3"` hay `IllegalArgumentException` từ target. Đây là lựa chọn **fail-open riêng cho sink metrics** của ví dụ, không phải chính sách bắt buộc cho mọi hệ thống. Nếu metric là nghĩa vụ bắt buộc thì có thể cần fail-closed hoặc cơ chế bảo đảm khác.

`BUSINESS_SUCCESSES 2` cho biết chỉ hai lần mua với số lượng hợp lệ chạy thành công. Có **bốn phép đo được thử ghi**, nhưng hai lần sau sink lỗi nên không có metric bình thường. Không được lấy số lần `finally` chạy làm số “giao dịch thành công”.

### 6.2. Hợp đồng và giới hạn của chương trình

- `fakeClock` được triển khai bằng mảng `long[]` nhằm có stdout dự đoán được. Nó **không an toàn cho truy cập đồng thời** và không phải bộ đo thời gian production. Trong ứng dụng thực, có thể khởi tạo `new StopwatchAdvice(System::nanoTime, metrics)` và thay sink bằng hệ thống metrics phù hợp.
- `targetCall()` dùng `Method.invoke()` rồi bóc `InvocationTargetException` để truyền tiếp ngoại lệ gốc. Nếu không bóc, lớp bọc reflection có thể làm sai loại lỗi mà caller nhận.
- `Method.getName().equals("buy")` chỉ là pointcut mô phỏng. Nếu interface có nhiều overload `buy`, cần chọn theo chữ ký rõ hơn.
- Proxy chỉ chặn lời gọi **qua đối tượng `api`**. Lời gọi trực tiếp vào `core` hoặc self-invocation không đi qua proxy này.
- `catch (RuntimeException)` quanh `metrics.record` chỉ xử lý loại lỗi hạ tầng phù hợp chính sách demo. Không dùng `catch (Throwable)` rộng để che `Error` nghiêm trọng trong hệ thống thực. Thậm chí lệnh báo lỗi trong `catch` vẫn có thể tự thất bại; muốn fail-open mạnh hơn cần một chiến lược quan sát độc lập và được kiểm thử.
- Dữ liệu nhãn `operation` là chuỗi cố định `"buy"`, tránh đưa định danh người dùng/đơn hàng vào metric label gây tăng cardinality và lộ dữ liệu.

## 7. Đặt mốc bắt đầu ở đâu cho đúng?

Một lỗi phổ biến là lấy mốc bắt đầu **sau khi đã gọi `proceed`**:

~~~java
Object result = next.proceed();
long started = System.nanoTime(); // Sai nếu muốn đo thời gian của proceed()
~~~

Ở đây phép đo không bao giờ bao gồm thời gian của thao tác vừa chạy. Một lỗi khác là đặt mốc `started` trong nhánh điều kiện mà một số đường đi không thực hiện, rồi sử dụng một biến chưa được khởi tạo chính xác.

Mẫu nhất quán:

~~~text
start = clock.now()
try:
    result = proceed()
    return result
finally:
    elapsed = clock.now() - start
    recordSafely(elapsed)
~~~

Đây là **pseudocode**, không phải cú pháp Java. Nguyên tắc: lấy mốc bắt đầu ngay trước vùng công việc muốn đo; chốt mốc kết thúc ngay sau vùng ấy trong `finally`. Nếu cần đo thêm tiền xử lý trước `proceed` thì chuyển `start` ra trước bước tiền xử lý; nếu muốn chỉ đo target, đặt `start` sát lời chuyển tiếp.

### 7.1. Trạng thái theo từng lần gọi

`started` phải là biến **cục bộ của một lần advice invocation** hoặc được quản lý theo đúng phạm vi tương đương. Không lưu `startTime` trong field của advice dùng chung giữa nhiều thread vì lần gọi B có thể ghi đè mốc của lần gọi A.

Phần mềm đo nhiều lời gọi đồng thời cần giữ một cặp mốc cho **mỗi lần thực thi**, đồng thời sink metrics phải hỗ trợ cập nhật đồng thời.

### 7.2. Khi lời gọi lồng và đệ quy

Mỗi lần vào around advice nên có mốc bắt đầu riêng. Ví dụ `factorial(5)` tự gọi `factorial(4)` và nhiều mức thấp hơn, nếu mọi lần đều được can thiệp, ta có thể thu nhiều quan sát duration. Đừng dùng một biến `static started` hoặc bộ đếm toàn cục như một mốc duy nhất vì các lần gọi sẽ chồng lấn lên nhau.

### 7.3. Khi around cố ý bỏ qua `proceed`

Với cache hit, một advice có thể trả kết quả mà không gọi target. Nếu đồng hồ bắt đầu trước quyết định cache và kết thúc ở `finally`, phép đo vẫn hợp lệ **cho thao tác quanh lời gọi**, nhưng không phải “thời gian chạy target”. Khi mục tiêu là metrics của cache, hãy phân biệt `cache_lookup_duration` và `business_execution_duration` theo phạm vi thực tế.

## 8. Khi `finally` tự gây lỗi: bảo toàn hợp đồng ngoại lệ

Xét đoạn mã:

~~~java
long start = System.nanoTime();
try {
    return next.proceed();
} finally {
    metrics.record(System.nanoTime() - start); // có thể ném exception
}
~~~

Đây là đoạn Java minh họa không độc lập (thiếu `next`, `metrics`). Nếu `next.proceed()` ném `IllegalArgumentException` và `metrics.record(...)` lại ném `IllegalStateException`, caller có thể nhận ngoại lệ **của metrics** thay vì lỗi nghiệp vụ gốc. Điều này phá tính quan sát và gây khó debug.

Thiết kế cần nêu chính sách:

| Chính sách lỗi metrics | Cách tiếp cận | Hệ quả cần chấp nhận |
| --- | --- | --- |
| **Fail-open** | Xử lý những lỗi sink được dự đoán; báo chúng qua kênh riêng; trả/throw tiếp như trước | Có thể thiếu dữ liệu đo, cần health monitoring |
| **Fail-closed** | Cho lỗi đo lường ảnh hưởng lời gọi nếu nghĩa vụ bắt buộc | Khả năng phục vụ của nghiệp vụ phụ thuộc hạ tầng quan sát |
| **Buffered/async sink** | Đẩy quan sát vào hàng đợi/buffer có giới hạn và chính sách backpressure | Cần quyết định mất mẫu, flush và vòng đời; không tự có độ bền chắc chắn |

Một hệ thống metric thông thường ưu tiên giảm ảnh hưởng lên nghiệp vụ, nhưng **không phải mọi dữ liệu quan sát đều tùy chọn**; audit bắt buộc có thể cần bảo đảm khác. Đây là quyết định kiến trúc, không được che bằng một `catch` vô điều kiện.

Nếu `clock.getAsLong()` tự gây lỗi trước khi vào `try`, `finally` chưa bắt đầu nên không thể bảo đảm chốt metric. Vì vậy việc đọc đồng hồ phải là thao tác nhẹ, có hợp đồng ổn định. `System.nanoTime()` thường thích hợp; đồng hồ giả nên được kiểm thử riêng.

## 9. Đo thành công và thất bại: elapsed time không phải outcome

`finally` chỉ bảo đảm thời điểm chốt, không tự cung cấp nhãn **thành công nghiệp vụ**. Nếu muốn phân loại:

- **Normal completion:** `proceed` trả bình thường, kể cả trả `null`, `false` hoặc `Result.failure`.
- **Exceptional completion:** `proceed` ném lỗi ra khỏi phạm vi được quan sát.
- **Business success/failure:** xác định bằng quy tắc miền, có thể khác hai nhóm trên.
- **Cancellation/timeout:** phụ thuộc cơ chế đồng bộ/bất đồng bộ; có thể là exception, trạng thái kết quả hoặc hoàn tất theo cách riêng.

Một around advice có thể ghi `outcome=normal` khi `proceed` trả bình thường và `outcome=exceptional` khi nó ném lỗi, rồi ghi metric thời gian ở `finally`. Nhưng nếu yêu cầu chỉ là đo elapsed, không nên nhồi mọi luật phân loại nghiệp vụ vào advice đo thời gian. Hãy cân nhắc một advice hoặc dịch vụ chuyên trách phân loại, có kiểm thử riêng.

### 9.1. Không để lỗi ghi metric biến thành “lỗi nghiệp vụ”

Nếu sink thất bại sau khi target thành công, một wrapper ngoài nhìn thấy exception do sink chứ không phải do target. Cần phân biệt nguồn lỗi trước khi tính tỷ lệ lỗi của nghiệp vụ; nếu không, số liệu reliability sẽ sai. Cấu trúc bọc lỗi trong ví dụ cố ý bắt riêng exception của sink để tránh tình huống này theo chính sách fail-open.

### 9.2. Không coi mọi `finally` là một lần target chạy

Với caching, authorization denial hoặc around advice khác bỏ `proceed`, khối `finally` của stopwatch vẫn chạy, nhưng target có thể chưa được thực hiện. Số lượt đo của wrapper là **số lượt join point đi qua wrapper**, không tự đồng nghĩa với số lần thực thi nghiệp vụ.

## 10. Bất đồng bộ: đo method return khác đo task completion

Giả sử:

~~~java
CompletableFuture<String> startWork() {
    return CompletableFuture.supplyAsync(() -> performWork());
}
~~~

Đoạn này là **mã minh họa chưa độc lập**; `performWork()` là thao tác do ứng dụng cung cấp.

Nếu around advice lấy `start`, gọi `proceed` và chốt `finally` ngay sau khi `startWork()` trả `CompletableFuture`, số đo là **thời gian tạo/trả Future**. Tác vụ bên trong có thể chạy sau hàng giây, thất bại hoặc bị hủy. Việc `finally` đã chạy **không có nghĩa toàn bộ task đã hoàn tất**.

Muốn đo “thời lượng tác vụ đến khi hoàn tất”, cần thiết kế **điểm kết thúc** gắn với sự kiện completion thật, có thể dùng callback hoặc instrumentation của runtime:

~~~java
long started = System.nanoTime();
CompletableFuture<String> future = startWork();
future.whenComplete((value, error) -> {
    long elapsed = System.nanoTime() - started;
    recordTaskDuration(elapsed, error);
});
~~~

Đây là đoạn minh họa, chưa chạy độc lập vì thiếu định nghĩa `startWork` và `recordTaskDuration`. Nó đo khoảng thời gian từ lúc tạo tác vụ đến khi stage `future` hoàn tất, **không phải CPU time** của tác vụ. Callback có thể chạy ở thread khác; trạng thái ngữ cảnh, cancellation, lỗi callback và vòng đời đồng hồ phải được xem xét.

Quan trọng: `whenComplete` trong Java trả **một stage mới**; nếu bỏ qua stage đó, lỗi của callback có thể khó được quan sát. Khi instrument nhiều lớp Future, cần bảo đảm không làm thay đổi result/cancellation/exception của API chỉ để gắn metric.

## 11. Đồng hồ giả và cách kiểm thử phép đo

Kiểm thử có sử dụng `Thread.sleep(50)` rồi yêu cầu duration chính xác `50ms` rất dễ không ổn định do hệ điều hành scheduling, CPU load và thời gian khởi động JVM. Mẫu tốt hơn là **tiêm nguồn đồng hồ** hoặc một `LongSupplier` vào advice, rồi cho nguồn đồng hồ trả trước những giá trị đã biết.

Ví dụ trong chương trình chạy được:

~~~java
final long[] ticks = {0L};
LongSupplier fakeClock = () -> {
    long now = ticks[0];
    ticks[0] += 100L;
    return now;
};
~~~

Đồng hồ giả cung cấp cặp mốc khác nhau `100` đơn vị nanosecond giả cho mỗi lần `buy()`. Việc `buy()` nhanh hay chậm ngoài đời không ảnh hưởng assertion của bài test. Nó giúp chứng minh **đọc đồng hồ hai lần, trừ đúng thứ tự và ghi sau khi `proceed` thoát**, thay vì vô tình đo sau khi target đã xong.

Lưu ý:

- Trong ví dụ này, clock giả được gọi tuần tự và **không thread-safe**. Test đồng thời cần đồng hồ giả được đồng bộ hoặc thiết kế riêng.
- Clock giả chỉ chứng minh **logic phép tính và đường điều khiển**, không chứng minh hiệu năng production.
- Khi test thực tế, có thể kiểm tra elapsed **không âm** trong phạm vi giả định phù hợp nhưng tránh assertion cứng “phải đúng N nano giây” cho đồng hồ thật.
- Kiểm tra cả nhánh thành công, nhánh ngoại lệ và sink thất bại. Một test chỉ đo normal return không chứng minh `finally` được dùng đúng.
- Nếu ghi histogram, xác minh đơn vị đo và bucket. Nhầm `ns` với `ms` có thể làm số liệu sai một triệu lần.

## 12. Chi phí đo lường và tác dụng phụ của metrics

Advice đo thời gian vẫn có overhead: đọc clock, lựa chọn pointcut, gọi wrapper, boxing, ghi metric và có thể gửi sự kiện đi nơi khác. Với join point gọi hàng triệu lần, overhead nhỏ trên từng lần vẫn có thể tích lũy đáng kể.

Các thực hành có ích:

1. **Giới hạn pointcut**: không đo mọi getter/công cụ helper nếu mục tiêu là latency của API quan trọng.
2. **Đọc clock với chi phí thấp**: `System.nanoTime()` phù hợp hơn một lời gọi mạng để lấy giờ.
3. **Chốt thời gian trước khi ghi metric**: tách duration của target khỏi chi phí xuất metric nếu đó là định nghĩa mong muốn.
4. **Không ghi mọi mẫu thành log đầy đủ** nếu khối lượng lớn; cân nhắc histogram, thống kê aggregate hoặc sampling theo yêu cầu.
5. **Đặt tên metric và đơn vị rõ ràng** như `operation_duration_seconds` hoặc nhãn `elapsed_nanos` tùy hệ thống lưu. Nếu backend yêu cầu seconds, chuyển từ nano giây sang seconds đúng cách.
6. **Giới hạn cardinality** của nhãn: tên operation chuẩn hóa là đủ trong nhiều trường hợp; đừng gắn mỗi `orderId`, `userId` hoặc URL đầy đủ có tham số vào nhãn.
7. **Chính sách lỗi sink và backpressure rõ ràng**: không cho lời gọi nghiệp vụ bị treo vô hạn vì một hệ metrics không phản hồi, trừ khi hợp đồng ứng dụng chủ động yêu cầu.

### 12.1. Histogram, percentile và trung bình

Một lượt stopwatch chỉ tạo ra **một mẫu thời lượng**. Muốn trả lời “p95 của checkout trong 5 phút” cần thu nhiều mẫu đúng phạm vi, có phân phối/biểu đồ phù hợp. Một giá trị average không mô tả hết tail latency; một percentile được tính sai trên dữ liệu đã gom trung bình từ trước cũng gây hiểu nhầm.

Nếu có nhiều tầng around, kiểm tra có ghi trùng các mẫu cùng một lời gọi hay không trước khi phân tích thống kê. Nên gắn outcome, operation và loại đường chạy theo tập nhãn có giới hạn, không dùng nhãn động gây cardinality vô hạn.

### 12.2. Concurrency và timer shared

`long started` trong method `around` là biến cục bộ nên mỗi lần gọi có mốc riêng. Không lưu `started` thành mutable field của singleton advice: hai thread có thể ghi đè, dẫn đến hiệu số sai. Nếu metrics dùng counter hoặc histogram chia sẻ, sink phải thread-safe theo hợp đồng.

## 13. Phạm vi của proxy, weaving và điểm đo

Một công cụ AOP thường chỉ can thiệp những join point mà mô hình của nó hỗ trợ. Với JDK dynamic proxy trong ví dụ, chỉ có các lời gọi đi qua interface proxy `Checkout` mới được bọc. Lời gọi trực tiếp vào `CheckoutCore` sẽ không chạy `StopwatchAdvice`. Một lời gọi nội bộ qua `this.otherMethod()` cũng có thể bỏ qua proxy.

Với cơ chế weaving khác, tập join point có thể bao gồm method execution, constructor hoặc những điểm sâu hơn, **nếu công nghệ thật sự hỗ trợ** và mã được đưa vào phạm vi weaving. Không coi mọi phương thức `private`, `final`, `static` hay thư viện ngoài tự động được instrument.

Định nghĩa phép đo phải chỉ rõ **call join point** hay **execution join point**. Một phép đo ở caller có thể bao gồm overhead dispatch/chuyển tiếp khác phép đo bắt đầu khi thân method ở callee thực thi.

Nếu pointcut chọn quá nhiều lời gọi cùng một đường call stack, có thể có nested timing. Nếu một lời gọi không khớp, không có observation: đó có thể là behavior đúng của pointcut, không phải lỗi timer.

## 14. Thứ tự advice: thời gian của phần nào?

Với ba wrapper:

~~~text
Audit (outer)
  Timer (middle)
    Authorization (inner)
      Business
~~~

`Timer` ở giữa có thể tính cả `Authorization` và `Business` nhưng không tính phần audit nằm bên ngoài. Đảo vị trí `Timer` ra ngoài thì số đo bao gồm cả audit. Đặt `Timer` sau authorization thì những yêu cầu bị từ chối trước khi vào Timer không có observation.

Khi có `Retry`, vị trí Timer quyết định metric đo toàn bộ request hay từng attempt. Khi có cache, Timer bên ngoài cache đo cả cache hit; Timer chỉ bên trong nhánh miss có thể không thấy cache hit. **Không có một thứ tự “luôn đúng” cho mọi chính sách.**

Hãy công bố:

- Tên thời lượng đang đo: caller-observed request, business execution, downstream I/O, cache lookup hay attempt.
- Ranh giới bắt đầu và kết thúc.
- Có đo lời gọi bị từ chối/exception không.
- Có đo `proceed` khi target được bỏ qua hay lặp không.
- Outcome được phân loại tại tầng nào.
- Chi phí ghi metrics có được tính vào số đo hay không.

Thứ tự nhiều advice không nên suy ra từ thứ tự file hoặc tên class; phải dựa trên hợp đồng precedence và quy tắc weaving của công nghệ AOP đang dùng.

## 15. Quy trình thiết kế và kiểm thử

Một quy trình ngắn nhưng chặt chẽ:

1. **Viết mục tiêu đo:** “Elapsed time từ trước khi chuyển vào `buy` đến lúc nó return/throw qua wrapper”.
2. **Chọn pointcut đúng mức:** giới hạn theo loại join point, chữ ký và phạm vi nghiệp vụ, tránh chọn nhầm overload.
3. **Quyết định vị trí Timer trong chuỗi advice:** đo request, attempt hay business; ghi rõ phạm vi.
4. **Tiêm hoặc chọn đồng hồ monotonic:** `System::nanoTime` là lựa chọn thực tế cho elapsed interval trong cùng tiến trình.
5. **Lấy mốc trước `proceed`, tính hiệu trong `finally`:** không bị thiếu nhánh ngoại lệ.
6. **Giữ hợp đồng caller:** không đổi kết quả, không che lỗi target; định nghĩa chính sách khi metrics sink lỗi.
7. **Dùng sink thích hợp:** đơn vị đúng, nhãn có giới hạn, thread-safe, có chính sách overhead và backpressure.
8. **Kiểm thử đồng hồ giả:** thành công, ngoại lệ, bypass pointcut, sink lỗi, nested calls, nhiều advice, retry và async nếu có.
9. **Kiểm chứng instrumentation thật:** một unit test gọi trực tiếp `around()` chưa chứng minh proxy/weaving đã áp dụng đúng.
10. **Đo overhead production:** so sánh độ trễ/throughput có và không có advice dưới tải đại diện.

Ma trận kiểm thử gợi ý:

| Kịch bản | Kỳ vọng đo | Kỳ vọng đối với nghiệp vụ |
| --- | --- | --- |
| `buy(2)` thành công | Một elapsed observation | Caller nhận `"order:2"` |
| `buy(0)` ném lỗi | Vẫn chốt duration trong `finally` | Caller nhận `IllegalArgumentException` gốc |
| `health()` không khớp | Không tạo metric | Chạy bình thường |
| Metrics sink lỗi, target thành công | Theo chính sách fail-open của ví dụ: ghi lỗi sink riêng | Caller vẫn nhận kết quả |
| Metrics sink lỗi, target ném lỗi | Không để lỗi sink che lỗi target | Caller vẫn nhận ngoại lệ gốc |
| Around cache hit không gọi target | Có thể đo wrapper nếu khớp | Không giả định target đã chạy |
| Retry bao trong timer | Đo tổng các lần thử nếu timer ngoài retry | Số lần gọi theo chính sách retry |
| Timer nằm trong retry | Có thể đo từng attempt | Không tự làm thay đổi số attempt |
| Lời gọi đồng thời | Mốc bắt đầu mỗi lần độc lập | Không lẫn số đo giữa thread |
| Future trả pending | Đo thời gian return Future | Không đồng nhất với task completion |
| Gọi target trực tiếp bỏ qua proxy | Không kỳ vọng metric của proxy | Target vẫn chạy theo hợp đồng |

## 16. Lỗi thường gặp

- **Lấy `start` sau `proceed`:** không đo được thời gian thao tác gốc.
- **Chỉ ghi duration ở nhánh return thành công:** thiếu các lời gọi lỗi, gây sai thống kê latency.
- **Dùng đồng hồ lịch để làm elapsed timer:** phép đo có thể bị ảnh hưởng bởi điều chỉnh giờ hệ thống.
- **Đọc `nanoTime` rồi coi là timestamp Unix:** sai bản chất mốc gốc.
- **Nhầm nanosecond với millisecond:** báo cáo sai đơn vị.
- **Để mã metrics trong `finally` ném lỗi che exception gốc:** caller nhìn sai nguyên nhân thất bại.
- **Catch mọi `Throwable` rồi bỏ qua:** che những lỗi nghiêm trọng và làm mất quan sát sự cố.
- **Đặt mốc bắt đầu vào field của advice dùng chung:** race condition khi nhiều lời gọi đồng thời.
- **Cộng duration của cha và con rồi gọi tổng không trùng lặp:** double-counting.
- **Không xét retry và cache:** số lần ghi metric khác số lần target thực thi.
- **Coi Future đã return là tác vụ hoàn tất:** bỏ sót độ trễ và lỗi bất đồng bộ.
- **Đặt Timer ở tầng không đúng:** đo cả audit hoặc bỏ qua authorization denial ngoài ý định.
- **Ghi nhãn metric với dữ liệu không giới hạn như user ID:** cardinality cao và có thể rò rỉ thông tin.
- **Đo mọi helper rất ngắn mà không xem overhead:** số liệu có thể bị ảnh hưởng đáng kể bởi chính instrumentation.
- **Cho rằng định nghĩa pointcut là đủ:** lời gọi bỏ qua proxy/weaving không tự được đo.

## 17. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao phép ghi duration nên đặt trong `finally` thay vì ngay sau câu lệnh `proceed`?  
**Đáp án:** Nếu `proceed` ném ngoại lệ, câu lệnh sau nó trong cùng nhánh sẽ bị bỏ qua. `finally` cho phép chốt thời lượng khi phạm vi rời đi qua cả hai đường thông thường.

**Câu 2.** `System.nanoTime()` trả số lớn. Có thể chuyển nó trực tiếp thành ngày giờ theo lịch không?  
**Đáp án:** Không. Mốc gốc của nó tùy ý; chỉ dùng hiệu giữa hai lần đọc phù hợp để đo elapsed time.

**Câu 3.** Nếu metrics sink trong `finally` ném exception, điều gì có thể xảy ra?  
**Đáp án:** Nó có thể che lỗi nghiệp vụ hoặc ngăn caller nhận kết quả. Cần chính sách rõ và kiểm thử xử lý lỗi của sink.

**Câu 4.** Một lần `checkout` gọi hai helper, mỗi helper có timer. Có được cộng cả ba duration thành tổng latency không trùng lặp không?  
**Đáp án:** Không. Duration của checkout có thể bao gồm thời gian helper, vì thế cộng vào tạo trùng lặp.

**Câu 5.** Vì sao test dùng fake monotonic clock hữu ích hơn `sleep` rồi so sánh chính xác millisecond?  
**Đáp án:** Có thể kiểm tra phép trừ và đường chạy một cách tất định, không phụ thuộc tải hệ thống và scheduling.

**Câu 6.** Method trả `CompletableFuture` ngay, công việc còn chạy. `finally` của around trên method đo được gì?  
**Đáp án:** Thời gian đến lúc method trả Future, không tự đo trọn công việc; muốn đo task completion cần quan sát completion riêng.

**Câu 7.** Vì sao số `METRIC buy` không tự đồng nghĩa với số đơn thành công?  
**Đáp án:** `finally` chạy cả ở lần target ném lỗi hoặc wrapper bỏ qua target; ý nghĩa metric là số lượt được quan sát theo phạm vi, không phải business success.

## 18. Tổng kết

**Mẫu đo thời gian bằng điểm bắt đầu và khối dọn dẹp trong around advice** là: lấy mốc từ một đồng hồ thích hợp như `System.nanoTime()`, gọi `proceed` đúng hợp đồng, rồi tính `elapsed = end - start` trong `finally` trước khi ghi metric. Cấu trúc này thu được thời lượng ở cả nhánh normal và exceptional completion, nhưng chỉ an toàn khi **việc ghi metric không vô tình che lỗi hoặc thay kết quả nghiệp vụ**. Hãy định nghĩa rõ phạm vi đo, thứ tự các advice, retry/cache, các lời gọi lồng nhau và giới hạn bất đồng bộ; tiêm đồng hồ giả để test phép tính, đồng thời kiểm thử đường gọi proxy/weaving thật. Một timer có giá trị nhất khi số đo có **đơn vị đúng, ngữ nghĩa rõ, overhead được kiểm soát và hợp đồng caller được bảo toàn**.
# Đo khoảng thời gian bằng nguồn thời gian đơn điệu trong Java Instrumentation

**Bài toán:** một Java agent muốn đo một phương thức, truy vấn, tác vụ hoặc span mất bao lâu để hoàn thành. Cần chọn **nguồn thời gian đo khoảng cách giữa hai mốc** thay vì lấy hai giá trị ngày/giờ trên lịch rồi trừ. Trong Java, API cơ bản là **`System.nanoTime()`**; cách dùng đúng là lấy hai mẫu trong cùng JVM và tính **`end - start`**.

~~~java
long start = System.nanoTime();
try {
    // Công việc cần đo nằm trong khoảng này.
} finally {
    long elapsedNanos = System.nanoTime() - start;
    // Ghi nhận elapsedNanos bằng một recorder không ném lỗi.
}
~~~

Đây là **fragment** minh họa vị trí đặt đồng hồ, không phải chương trình hoàn chỉnh. Bài này giải thích vì sao phải dùng nguồn đơn điệu, cách xử lý tràn số, cách bao phủ đường `return` và exception, điểm đặt timer trong instrumentation, độ chính xác và tác động tới metrics, cùng các ví dụ Java 17 có thể biên dịch/chạy độc lập.

## 1. Thời gian trên đồng hồ và khoảng thời gian là hai đại lượng khác nhau

Một hệ thống thường cần hai câu hỏi:

1. **Sự kiện xảy ra lúc mấy giờ?** Ví dụ `2026-10-31T08:05:00Z`. Đây là *wall-clock timestamp*, dùng cho log, audit và tương quan sự kiện theo thời điểm.
2. **Công việc chạy mất bao lâu?** Ví dụ `42.3 ms`. Đây là *elapsed duration*, được tính bằng hiệu giữa hai mẫu lấy từ **cùng một nguồn thời gian dùng để đo khoảng cách**.

So sánh API trong Java:

| API | Trả về | Phù hợp | Không phù hợp |
|---|---|---|---|
| `System.currentTimeMillis()` | Số mili giây từ Unix epoch (wall clock) | Ghi mốc ngày/giờ gần đúng, một số log | Đo latency vì wall clock có thể được chỉnh và có độ phân giải hạn chế |
| `Instant.now()` | Thời điểm trên lịch UTC từ clock hệ thống | Timestamp sự kiện, audit | Mặc định không phải nguồn đơn điệu để đo elapsed |
| `Clock.systemUTC().instant()` | Timestamp dựa vào clock hệ thống | Thời điểm có thể cấu hình, inject trong ứng dụng | Không đồng nghĩa với đồng hồ đơn điệu |
| **`System.nanoTime()`** | Giá trị `long` nanosecond theo **mốc gốc tùy ý của JVM** | **Đo elapsed**, timeout, khoảng thời gian trong JVM | Không dùng như epoch, không hiển thị trực tiếp thành ngày giờ |
| `ThreadMXBean.getCurrentThreadCpuTime()` | CPU time của thread, khi JVM có hỗ trợ và bật tính năng | Phân tích **CPU của thread** | Không thay thế duration của giao dịch bao gồm I/O/chờ |

**Vì sao wall clock không thích hợp?** Giờ hệ thống có thể được đồng bộ/chỉnh bởi NTP, quản trị viên hoặc cơ chế hệ điều hành. Nếu tính:

~~~java
long startMs = System.currentTimeMillis();
doWork();
long elapsedMs = System.currentTimeMillis() - startMs;
~~~

thì bạn có thể nhận khoảng thời gian âm hoặc bất thường nếu wall clock bị chỉnh giữa hai lần đọc. Đo bằng `nanoTime()` tránh phụ thuộc vào việc hiển thị ngày giờ trên lịch.

`Instant.now()` có API nanosecond không có nghĩa clock nền có độ phân giải thực một nanosecond hoặc cung cấp tính chất đơn điệu. **Đơn vị dữ liệu, độ chính xác và loại nguồn clock là ba đặc tính khác nhau.**

## 2. `System.nanoTime()`: chỉ hiệu giữa hai mẫu mới có ý nghĩa

Đặc tả Java SE định nghĩa `nanoTime()` trả về giá trị `long` từ nguồn thời gian phân giải cao của JVM. **Mốc gốc cố định nhưng tùy ý**, có thể nằm trong tương lai so với thời điểm hiện tại; số trả về **có thể âm**. Hai JVM khác nhau có thể có các mốc gốc khác nhau.

~~~java
long startNanos = System.nanoTime();
performOperation();
long endNanos = System.nanoTime();

long elapsedNanos = endNanos - startNanos;
double elapsedMillis = elapsedNanos / 1_000_000.0;
~~~

Đây là fragment minh họa trong phương thức đã có `performOperation()`; phần phép tính là cú pháp Java đầy đủ.

Điểm cần hiểu:

- **`startNanos` không phải timestamp**. Không chuyển trực tiếp nó thành `Instant`, không ghi giá trị nguyên vào log để tưởng là số nanosecond từ Unix epoch.
- **Chỉ lấy hiệu `end - start` từ cùng JVM**. Không lấy `nanoTime()` của service A trên JVM A trừ `nanoTime()` của service B trên JVM B.
- **Nanosecond precision không đồng nghĩa nanosecond resolution**: loại trả về và đơn vị là nanosecond, nhưng clock có thể không thay đổi sau mỗi nanosecond; hai lời gọi gần nhau có thể cho cùng giá trị, dẫn tới duration bằng 0.
- Độ chính xác thực tế phụ thuộc JVM, OS và phần cứng. **Không** kết luận một tác vụ thực sự mất đúng 1 ns chỉ vì API dùng đơn vị ns.
- Cách đo thông thường là đo khoảng thời gian trôi qua (*elapsed/wall duration*), **không đo riêng CPU time**. Thời gian chờ khóa, chờ I/O, bị thread scheduler trì hoãn hoặc GC có thể nằm trong duration tùy vị trí đặt mốc.

Tên gọi “đồng hồ đơn điệu” trong thiết kế điểm đo nhấn mạnh **dùng nguồn thời gian tương đối không bị điều chỉnh theo lịch**. Đừng dựa vào giá trị tuyệt đối của số `nanoTime` để suy ra thứ tự thời gian trên một hệ thống phân tán.

## 3. Công thức chuẩn và lỗi so sánh mốc thời gian

Khuôn an toàn nhất để đo duration:

~~~text
t0 = System.nanoTime()
      [đoạn công việc]
t1 = System.nanoTime()

elapsedNanos = t1 - t0
elapsedMillis = elapsedNanos / 1_000_000.0
~~~

Nếu cần giới hạn timeout, so sánh **hiệu** với timeout:

~~~java
long started = System.nanoTime();
long timeoutNanos = java.util.concurrent.TimeUnit.MILLISECONDS.toNanos(250);

// Sau khi thực hiện một số việc:
boolean timedOut = System.nanoTime() - started >= timeoutNanos;
~~~

Không nên dùng:

~~~java
long deadline = started + timeoutNanos;
boolean timedOut = System.nanoTime() >= deadline;
~~~

Trong trường hợp giá trị `long` đi qua biên số, phép cộng deadline và phép so sánh tuyệt đối có thể tạo kết quả sai. Đặc tả Java khuyến nghị **`System.nanoTime() - start >= timeoutNanos`** thay cho `now >= start + timeoutNanos`.

### Tràn số: vì sao phép trừ vẫn có thể đúng?

`System.nanoTime()` dùng `long` có dấu, nên bản thân giá trị có thể đi qua `Long.MAX_VALUE` rồi trở thành số âm. Khi khoảng thời gian thực ngắn hơn khoảng **2^63 ns**, tức xấp xỉ **292 năm**, hiệu theo phép trừ `long` hai phần bù vẫn biểu diễn đúng khoảng thời gian trong phạm vi hợp lệ. Nếu khoảng cách vượt giới hạn này, đặc tả **không bảo đảm** hiệu tính đúng do overflow.

**Ví dụ số học mô phỏng tràn `long`:**

~~~text
start = Long.MAX_VALUE - 3
end   = Long.MIN_VALUE + 6

end - start = 10 (nanosecond, theo phép trừ long)
~~~

Không khẳng định một JVM thật vừa chạy qua biên 292 năm; ví dụ chỉ làm rõ **vì sao so sánh giá trị thô `end >= start` là sai**. Sau đoạn tràn giả lập này, giá trị `end` âm nhưng duration bằng 10 ns vẫn hợp lệ.

Các quy tắc thực tế:

1. Chỉ tính elapsed từ **hai lần lấy mẫu trong cùng JVM**.
2. Chỉ so sánh với **timeout không âm**; nếu nhận timeout từ người dùng, kiểm tra dấu và tránh overflow khi chuyển đổi đơn vị.
3. Timeout và khoảng đo thực tế cần nằm trong giới hạn biểu diễn `long` thích hợp.
4. Không sử dụng giá trị `nanoTime()` như khóa thời gian toàn cục hoặc ID sự kiện liên JVM.

## 4. Đặt mốc ở đâu mới đo đúng mục tiêu?

Trong instrumentation, **điểm bắt đầu và kết thúc quyết định ý nghĩa của metric**. Hãy đặt tên metric dựa trên ngữ nghĩa thực tế.

~~~text
Nhận request
    |
    v
[ t0: vào method handler ]
    |
    +---- validate
    +---- query database       (có chờ I/O)
    +---- serialize response
    |
[ t1: rời method handler ]
    |
    v
Trả response
~~~

`elapsed = t1 - t0` đo **thời gian từ khi vào đến khi thoát method**, bao gồm phần chờ và scheduling xảy ra trong khoảng ấy. Nó không nhất thiết đo toàn bộ thời gian từ lúc gói tin tới socket đến khi byte cuối cùng gửi cho client. Nếu muốn latency end-to-end, cần instrument tại ranh giới đúng của giao thức/request.

| Điểm đặt timer | Metric phản ánh |
|---|---|
| Quanh thân method đồng bộ | Thời gian gọi method từ entry tới return/throw |
| Quanh gọi JDBC | Thời gian caller bị giữ trong API JDBC, có thể gồm chờ driver/network |
| Quanh một task trong executor | Nếu bắt đầu sau khi task được dequeue: *execution time*; nếu bắt đầu trước `submit`: có cả *queue time* |
| Quanh `CompletableFuture` đến lúc hoàn thành | Thời gian chờ kết quả bất đồng bộ, không chỉ thời gian tạo future |
| Quanh một vòng retry | Tổng độ trễ **của mọi lần thử** và khoảng nghỉ nếu nằm trong timer |
| Quanh từng attempt riêng | Độ trễ mỗi lần thử; khác tổng request latency |

Cần quyết định **đếm một lần mỗi request** hay **mỗi attempt**, và ghi metric khác nhau nếu muốn cả hai. Sai vị trí đặt timer là nguồn sai số ngữ nghĩa lớn hơn nhiều so với chênh lệch vài nanosecond của clock.

## 5. Bao phủ đường thành công, `return`, exception bằng `try/finally`

Khi instrument một method đồng bộ, một sai lầm phổ biến là đặt đồng hồ cuối method:

~~~java
long start = System.nanoTime();
Result result = doWork();
long elapsed = System.nanoTime() - start;
record(elapsed);
return result;
~~~

Fragment trên **không ghi duration nếu `doWork()` ném exception**. Ngoài ra, method có nhiều nhánh `return` sẽ rất dễ bỏ sót. Dùng `finally` để đặt thời điểm đo kết thúc:

~~~java
long start = System.nanoTime();
try {
    return doWork();
} finally {
    long elapsedNanos = System.nanoTime() - start;
    record(elapsedNanos);
}
~~~

Đây là fragment minh họa, cần có `doWork()` và `record(...)` trong chương trình thật. `finally` vẫn được thực thi khi luồng điều khiển rời `try` qua `return` hoặc exception bình thường. Không đảm bảo `finally` chạy nếu process bị tắt cưỡng bức, JVM bị halt hoặc có tình huống hệ thống không thể tiếp tục.

**Cẩn thận:** Nếu `record(...)` tự ném exception từ `finally`, nó có thể **che mất exception gốc** hoặc làm thay đổi kết quả của method. Recorder của agent nên là thao tác rất nhẹ, chịu lỗi và tránh side effect nguy hiểm:

~~~java
long start = System.nanoTime();
try {
    return doWork();
} finally {
    long elapsed = System.nanoTime() - start;
    try {
        metrics.record(elapsed);
    } catch (RuntimeException metricsError) {
        // Không làm lỗi đo đạc che mất kết quả/lỗi nghiệp vụ.
    }
}
~~~

Đây chỉ là phác thảo strategy; production cần quyết định cách ghi lỗi metrics riêng, không lặng lẽ bỏ qua mọi lỗi mà không quan sát. Trong những hệ thống đặt yêu cầu độ tin cậy cao, có thể dùng recorder không throw ngay từ thiết kế, và kiểm tra hợp đồng API của nó.

## 6. Ví dụ Java 17 chạy độc lập: đo thành công và lỗi, kiểm thử bằng ticker giả

Không nên kiểm thử timing bằng cách assert cứng “code chạy 5 ms”: lịch thread, máy ảo và OS sẽ làm giá trị dao động. Thay vào đó, **inject nguồn thời gian** để unit test có thể trả các mẫu định trước. Trong production, nguồn thật vẫn là `System::nanoTime`.

Lưu file **`MonotonicTimingDemo.java`** với nội dung:

~~~java
import java.util.function.LongConsumer;
import java.util.function.LongSupplier;

public final class MonotonicTimingDemo {
    @FunctionalInterface
    interface CheckedSupplier<T> {
        T get() throws Exception;
    }

    static <T> T timed(
            CheckedSupplier<T> task,
            LongSupplier ticker,
            LongConsumer recorder) throws Exception {
        long start = ticker.getAsLong();
        try {
            return task.get();
        } finally {
            long elapsedNanos = ticker.getAsLong() - start;
            recorder.accept(elapsedNanos);
        }
    }

    static LongSupplier scripted(long first, long second) {
        return new LongSupplier() {
            private int calls;

            @Override
            public long getAsLong() {
                return switch (calls++) {
                    case 0 -> first;
                    case 1 -> second;
                    default -> throw new IllegalStateException("no more ticks");
                };
            }
        };
    }

    public static void main(String[] args) throws Exception {
        long[] recorded = new long[2];
        String value = timed(
                () -> "OK",
                scripted(1_000L, 1_250L),
                nanos -> recorded[0] = nanos);
        System.out.println("value=" + value);
        System.out.println("successNanos=" + recorded[0]);

        try {
            timed(() -> {
                throw new IllegalStateException("boom");
            }, scripted(500L, 950L), nanos -> recorded[1] = nanos);
        } catch (IllegalStateException e) {
            System.out.println("caught=" + e.getMessage());
        }
        System.out.println("failureNanos=" + recorded[1]);

        long[] liveNanos = new long[1];
        int answer = timed(
                () -> 40 + 2,
                System::nanoTime,
                nanos -> liveNanos[0] = nanos);
        System.out.println("answer=" + answer);
        if (liveNanos[0] < 0) {
            throw new AssertionError("Unexpected negative real duration");
        }
    }
}
~~~

Biên dịch và chạy với JDK 17+:

~~~bash
javac --release 17 MonotonicTimingDemo.java
java MonotonicTimingDemo
~~~

**Stdout đã được kiểm chứng khi biên dịch và chạy ví dụ:**

~~~text
value=OK
successNanos=250
caught=boom
failureNanos=450
answer=42
~~~

Vì sao output này **ổn định**:

- Ticker giả trả `1_000` và `1_250`, nên phép trừ đúng `250 ns`; task trả `"OK"`.
- Ở đường ném lỗi, ticker giả trả `500` và `950`, nên `finally` **vẫn ghi** `450 ns`, rồi exception `"boom"` được bắt ở `main`.
- Nhánh cuối dùng `System::nanoTime` thật nhưng **không in duration biến động**. Nó chỉ in `answer=42` và bảo đảm duration thực bình thường không âm.
- `long[]` trong demo là nơi giữ giá trị đơn giản vì chạy một luồng. Với collector đa luồng, dùng cơ chế ghi metric thread-safe và tránh chia sẻ mảng thô không đồng bộ.

Đối tượng `LongSupplier` cho phép **kiểm tra hành vi thời gian một cách tất định** mà không tự thay `System.nanoTime()` bằng đồng hồ wall clock. `LongConsumer` cho phép kiểm thử việc ghi metric trên cả hai đường thực thi.

Ví dụ dùng `switch` expression (từ trước Java 17), `@FunctionalInterface`, generics và các API có sẵn trong Java 17, không cần Maven hoặc thư viện ngoài.

## 7. Ví dụ Java 17: kiểm tra timeout khi `long` vượt biên

File **`TimeoutDemo.java`**:

~~~java
public final class TimeoutDemo {
    static boolean expired(
            long startNanos, long timeoutNanos, long nowNanos) {
        if (timeoutNanos < 0) {
            throw new IllegalArgumentException("timeout < 0");
        }
        return nowNanos - startNanos >= timeoutNanos;
    }

    public static void main(String[] args) {
        long start = Long.MAX_VALUE - 3;
        long end = Long.MIN_VALUE + 6;

        System.out.println("elapsed=" + (end - start));
        System.out.println("expired8=" + expired(start, 8, end));
        System.out.println("expired15=" + expired(start, 15, end));
    }
}
~~~

Lệnh:

~~~bash
javac --release 17 TimeoutDemo.java
java TimeoutDemo
~~~

**Stdout đã kiểm chứng:**

~~~text
elapsed=10
expired8=true
expired15=false
~~~

Bài kiểm thử này dùng **mốc giả lập trên kiểu `long`**, không dùng `System.nanoTime` và không phải bằng chứng về việc clock thật đã rollover. Nó xác nhận cách so sánh **hiệu trước, timeout sau** hoạt động đúng trong một ví dụ overflow ở biên. Lưu ý trường hợp thực tế có elapsed vượt khoảng 292 năm **không** thuộc vùng bảo đảm của API.

## 8. Chuyển đơn vị đúng cách

Mỗi phép trừ của `System.nanoTime` trả đơn vị **nanosecond**. Không được ghi số này dưới nhãn `ms` hoặc `seconds` mà quên chuyển đổi.

~~~java
long elapsedNanos = 2_345_678L;

double elapsedMillis = elapsedNanos / 1_000_000.0;
long wholeMillis =
        java.util.concurrent.TimeUnit.NANOSECONDS.toMillis(elapsedNanos);

System.out.println(elapsedMillis);
System.out.println(wholeMillis);
~~~

Nếu đặt bên trong `main`, stdout:

~~~text
2.345678
2
~~~

Phân biệt:

- Chia cho `1_000_000.0` cho kết quả **mili giây dạng số thực**.
- `TimeUnit.NANOSECONDS.toMillis` trả `long`, **bỏ phần lẻ** khi đổi đơn vị. Một phép đo `999_999 ns` thành `0 ms`, không có nghĩa task mất 0 ns.
- `Duration.ofNanos(elapsedNanos)` biểu diễn độ dài thời gian dưới dạng đối tượng `Duration`, phù hợp cho API ứng dụng; `Duration` không phải nguồn đọc clock.
- Khi ghi vào histogram, nên giữ **`long` nanosecond** đến lớp chuyển đổi hoặc đúng đơn vị mà metric SDK yêu cầu, tránh chuyển qua lại làm giảm độ phân giải.
- Nếu người dùng nhập `Duration` rất lớn, `Duration.toNanos()` **có thể ném `ArithmeticException`** nếu không vừa `long`. Hãy kiểm tra phạm vi trước khi biến thành timeout.

Ví dụ annotation nên đặt rõ tên trường: `elapsed_nanos`, `duration_ms`, `timeout_nanos`. Một giá trị số không có **unit** là metric dễ bị đọc sai.

## 9. Instrumentation bytecode: cách đặt điểm đo vào method

Java agent thường can thiệp class file qua `ClassFileTransformer`, ASM, Byte Buddy hoặc Java Class-File API (chuẩn hóa ở JDK 24). Dù công cụ nào, logic cần tạo ra tương đương:

~~~text
Method entry:
    startNanos = System.nanoTime()

Original method body:
    ... lệnh JVM gốc ...

Normal return:
    elapsed = System.nanoTime() - startNanos
    record(elapsed)
    return originalResult

Exceptional exit:
    elapsed = System.nanoTime() - startNanos
    record(elapsed)
    rethrow originalThrowable
~~~

Đây là **pseudocode về control flow**, không phải syntax ASM/JVM bytecode có thể chạy nguyên văn. Khi biến đổi bytecode thật, cần:

1. **Chèn tại điểm method hợp lệ** và tạo local slot `long` (chiếm hai slot JVM) để lưu start time.
2. **Đảm bảo mọi đường return và exception thoát method đều có điểm kết thúc**. Đặt một callback chỉ trước opcode `RETURN` đầu tiên sẽ bỏ sót `IRETURN`, `ARETURN`, các return khác và exception.
3. Duy trì **giá trị trả về gốc**: lúc chèn code trước return, bảo toàn operand stack và không đổi kiểu trả về.
4. Xây **exception handler/finally** cẩn thận để đo đường throw không làm đổi exception gốc; xử lý nested handlers và code có sẵn.
5. Cập nhật **stack map frames, max stack/max locals, label và exception table** để class file mới pass verifier.
6. Tránh đo sai constructor: một số thao tác trước khi gọi `super(...)`/`this(...)` có hạn chế về `uninitializedThis`. Không cài đặt trình chèn constructor giống hệt method thông thường mà không xét quy tắc verifier.
7. Chỉ instrument method **có code**; phương thức `abstract` và `native` không có `Code` attribute để chèn các opcode Java theo cách thông thường.
8. Nếu dùng transformer được gọi khi retransform, bảo đảm phép biến đổi không chèn timer **lặp lại nhiều lớp** theo từng lần gọi, dẫn đến double-count.

Một ví dụ biến đổi tưởng đúng nhưng sai:

~~~text
onMethodEnter: start = nanoTime()
onMethodExit(RETURN): record(nanoTime() - start)
~~~

Tổ hợp trên **không bao phủ đường method ném exception** nếu hook chỉ chạy cho return bình thường. Một số thư viện cho phép hook nhận **các opcode exit**; ngay cả khi bắt `ATHROW`, exception có thể thoát từ một lời gọi khác mà không có opcode `ATHROW` ở method đang instrument. Muốn bao phủ mọi exceptional exit, cần thiết kế handler/finally thích hợp, không chỉ dựa vào tìm opcode `ATHROW`.

## 10. Đồng bộ và bất đồng bộ: đừng dừng timer quá sớm

Nếu một method **trả về `CompletableFuture` ngay**, thời gian thực thi method thường chỉ đo thời gian **tạo/lên lịch** future, không phải thời gian công việc bất đồng bộ hoàn thành.

**Sai mục tiêu nếu muốn đo end-to-end latency:**

~~~java
long start = System.nanoTime();
try {
    return service.callAsync();
} finally {
    record(System.nanoTime() - start);
}
~~~

Đây là fragment: `finally` chạy ngay khi return future, dù future chưa hoàn thành. Nếu mục tiêu là **thời gian callAsync() trả về future**, cách này đúng. Nếu mục tiêu là **từ khi gọi đến khi future hoàn thành**, hãy kết thúc timer ở completion callback.

**Phác thảo đúng ngữ nghĩa đo duration bất đồng bộ:**

~~~java
long start = System.nanoTime();
try {
    CompletableFuture<Result> future = service.callAsync();
    return future.whenComplete((value, error) -> {
        long elapsed = System.nanoTime() - start;
        record(elapsed);
    });
} catch (RuntimeException immediateFailure) {
    record(System.nanoTime() - start);
    throw immediateFailure;
}
~~~

Đây là **fragment** nằm trong method đã có `service`, `Result` và `record` tương ứng, với import `java.util.concurrent.CompletableFuture`. `whenComplete` kích hoạt khi future nguồn hoàn tất; đồng hồ được đọc trong callback. Callback có thể chạy với độ trễ nhỏ phụ thuộc scheduler/thực thi, nên số đo phản ánh thời điểm callback thực sự được gọi. Nếu `record` ném lỗi, dependent future có thể có kết quả lỗi khác: **recorder phải an toàn**.

Trong trường hợp pipeline có nhiều `CompletionStage`, hãy xác định chính xác **stage nào biểu diễn thời điểm hoàn thành nghiệp vụ**. Nếu trả future đã hoàn tất từ trước, callback có thể chạy ngay, nhưng đó là hành vi bình thường. Nếu muốn tính cả queue time, lấy start **trước khi enqueue**; nếu chỉ đo execution time, lấy start **trong worker khi task bắt đầu thực thi**.

Nguồn `System.nanoTime()` có cùng origin trong **một JVM**, nên lấy mẫu ở hai thread khác nhau trong JVM đó vẫn có thể có ý nghĩa nếu control flow được đồng bộ/happens-before đúng cách. **Không mang raw start tick từ JVM A qua message để JVM B lấy end tick rồi trừ**.

## 11. Logging, metrics và tracing nên dùng hai loại thời gian khác nhau

Một span hoặc event thực tế có thể cần cả **mốc thời điểm** và **duration**:

~~~text
timestamp_utc = Instant.now()          // mốc ngày/giờ để gắn log
start_tick    = System.nanoTime()      // mốc tương đối
... operation ...
duration_ns   = System.nanoTime() - start_tick
~~~

Lưu ý hai mẫu đầu không được đọc trong cùng một thao tác atomic; timestamp để liên hệ log có thể lệch duration nhỏ theo overhead. Không cố tính timestamp hoàn thành bằng cách chuyển trực tiếp `start_tick` thành epoch.

Trong production, nên ghi một **histogram/timer** cho thời gian xử lý thay vì log từng request:

| Thông tin | Cách biểu diễn tốt |
|---|---|
| Thời gian mỗi operation | Duration bằng số, có unit |
| Latency phân bố | Histogram với buckets nhất quán; quan sát p50/p95/p99 từ dữ liệu phù hợp |
| Số lần xử lý | Counter |
| Thành công/thất bại | Status/tag ít giá trị khác nhau |
| Thời gian xảy ra sự kiện | Wall-clock timestamp riêng |
| Liên kết các bước xử lý | Trace/span ID và context, không phải raw `nanoTime` |

**Tránh cardinality cao**: đừng dùng user ID, URL có UUID, transaction ID hoặc duration duy nhất làm label của histogram. Làm vậy có thể khiến số time series tăng khổng lồ.

**Tránh tính trung bình sai**: độ trễ p99 của một luồng không thể lấy bằng phép trung bình đơn giản của các p99 tại mỗi instance. Histogram cần có phương thức tổng hợp phù hợp.

**Không dùng một phép đo latency làm CPU benchmark**: duration có thể bao gồm I/O, lock contention, GC và thời gian thread không được CPU chạy. Nếu muốn đo riêng CPU, cân nhắc `ThreadMXBean`, profiler hoặc JFR trong hoàn cảnh được hỗ trợ.

## 12. Hiểu giới hạn của clock và overhead instrumentation

`System.nanoTime()` là lựa chọn phổ biến cho elapsed, nhưng không phải dụng cụ đo siêu nhỏ hoàn hảo.

- **Overhead gọi clock**: hai lần gọi `nanoTime()` và một lần ghi metric có chi phí; với method cực ngắn, overhead có thể chiếm tỉ lệ đáng kể.
- **Instrumentation làm thay đổi chính thứ đang đo** (*observer effect*). Có thể ảnh hưởng JIT inlining, register pressure, class loading và performance profile.
- **Resolution khác precision**: nếu hai lần đọc cho giá trị giống nhau, duration bằng 0 là kết quả hợp lệ về độ phân giải quan sát, không có nghĩa công việc chạy “không tốn thời gian”.
- **Warm-up/JIT/GC**: kết quả lần gọi đầu và sau warm-up có thể khác mạnh; so sánh phải định nghĩa cùng điều kiện.
- **Scheduling/virtual threads**: nguồn đo elapsed tiếp tục phản ánh thời gian trôi qua trong khi task bị chặn/chờ; điều này phù hợp service latency nhưng không đo riêng CPU.
- **Clock jitter và môi trường ảo hóa** có thể ảnh hưởng phép đo; tránh khẳng định độ phân giải cố định trên mọi OS/JVM.
- **Recording và export**: nếu exporter chặn thread, phần lớn overhead có thể nằm ở recorder chứ không ở phép đọc clock; nên đo/tối ưu recorder riêng.

Với **microbenchmark** yêu cầu so sánh các đoạn code ngắn, nên dùng **JMH** vì benchmark thủ công dễ bị tối ưu hóa, dead-code elimination, ảnh hưởng JIT và sai kiểm soát iteration. Với **điểm đo ứng dụng thực tế**, `nanoTime()` + phạm vi đo chính xác + metrics nhẹ thường là nền tảng hợp lý.

**Không** tự lấy nhiều triệu mẫu `nanoTime` rồi suy ra “độ chính xác của clock” từ một con số duy nhất; số liệu đó còn chịu scheduling và timing API overhead.

## 13. Timeout, deadline và việc chờ

Một deadline có thể được biểu diễn bằng `Instant` khi cần lịch trên hệ thống, nhưng **timeout của một hoạt động đang chạy** nên được so với một khoảng tương đối:

~~~java
long started = System.nanoTime();
long budgetNanos = java.util.concurrent.TimeUnit.SECONDS.toNanos(2);

while (!finished()) {
    if (System.nanoTime() - started >= budgetNanos) {
        throw new java.util.concurrent.TimeoutException("budget expired");
    }
    doOneStep();
}
~~~

Đây là fragment có các phương thức `finished()`/`doOneStep()` do ứng dụng cung cấp; nó minh họa kiểm tra timeout, không phải polling loop tối ưu. Trong hệ thống thật, nên dùng cơ chế block có timeout như `Lock.tryLock`, `Condition.awaitNanos`, `Future.get(timeout, unit)` hoặc `ScheduledExecutorService`, thay vì busy-spin liên tục chỉ để đọc đồng hồ.

Các điều cần nhớ:

1. **Không dùng `Thread.sleep(2000)` như bằng chứng thời gian chính xác 2.000 ms**. Sleep thường có scheduling delay và không bảo đảm đánh thức đúng nanosecond.
2. Khi tính `remaining = budgetNanos - (now-start)`, có thể phải xử lý trường hợp remaining <= 0 trước khi truyền cho API yêu cầu duration dương.
3. Nếu budget đã hết trước khi bắt đầu I/O mới, timeout nên được **propagate** hoặc kiểm tra trước bước I/O đó, tránh thực hiện operation có thể block vô hạn.
4. Khi một request đi qua nhiều service/process, truyền **deadline hoặc remaining budget theo giao thức phù hợp**, không gửi raw `System.nanoTime` từ process này cho process khác.
5. Timeout đo thời gian trôi qua không đồng nghĩa cancellation đã thành công; sau khi hết hạn, vẫn cần cơ chế hủy/cleanup tùy API.

## 14. Các lỗi thường gặp khi thiết kế điểm đo

| Biểu hiện | Nguyên nhân khả dĩ | Cách khắc phục |
|---|---|---|
| Duration âm bất thường khi dùng `currentTimeMillis` | Wall clock bị chỉnh | Dùng `System.nanoTime()` cho elapsed |
| Duration âm khi lấy `nanoTime()` hai JVM | Mốc gốc không chung | Chỉ trừ các mẫu cùng JVM; dùng tracing protocol cho liên service |
| Không thấy kết quả đo khi method throw | Chỉ chèn ghi duration ở đường return | Dùng `finally`/exception handler cho mọi lối thoát |
| Method trả `CompletableFuture` nhưng duration rất nhỏ | Dừng timer khi return future | Nếu muốn end-to-end, kết thúc ở completion callback |
| Metric ghi đơn vị `ms` nhưng số lấy từ `nanoTime` | Quên chuyển từ ns | Đổi đơn vị đúng hoặc ghi `elapsed_nanos` |
| Có quá nhiều metric series | Dùng dynamic ID/URL làm label | Thiết kế labels cardinality thấp |
| Thêm timer làm hiệu năng xấu | Ghi log/metrics blocking, allocation hoặc instrument quá nhiều method | Filter mục tiêu, sampling phù hợp, recorder nhẹ |
| Sai timeout gần tràn `long` | So `now >= started + timeout` | So `now - started >= timeout` |
| Thấy `0 ns` cho một thao tác nhỏ | Nguồn clock không có resolution 1 ns | Không suy ra task miễn phí; dùng phân bố nhiều mẫu |
| Chạy lại transformer làm timer lồng nhiều lần | Instrumentation không kiểm tra idempotence | Duy trì transform pipeline không nhân bản điểm đo |
| CPU time thấp nhưng latency cao | Task đang chờ I/O/lock/scheduling | Phân biệt duration với CPU time |
| Lỗi metrics che exception gốc | Recorder ném lỗi trong `finally` | Xây recorder không throw hoặc xử lý lỗi riêng |

**Checklist khi triển khai:** xác định ranh giới nghiệp vụ → dùng một nguồn nanoTime cho cặp start/end → ghi delta chứ không ghi tick tuyệt đối → bao phủ success/error → thống nhất unit → kiểm tra async boundary → bảo đảm low-overhead và thread-safe → kiểm thử bằng ticker giả → quan sát phân bố latency trên môi trường thật.

## 15. Tự kiểm tra

1. **`nanoTime()` có phải số nanosecond từ Unix epoch?** Không; origin cố định nhưng tùy ý cho một JVM.
2. **Có thể lấy `nanoTime()` JVM A trừ `nanoTime()` JVM B?** Không; hai origin có thể khác.
3. **Vì sao nên đo duration với `System.nanoTime()` thay vì `currentTimeMillis()`?** Vì không phụ thuộc đồng hồ lịch có thể bị chỉnh, và thích hợp cho elapsed.
4. **Hai lời gọi `nanoTime()` có thể trả cùng số?** Có; nanosecond precision không bảo đảm nanosecond resolution.
5. **Khi kiểm tra timeout, nên dùng `now >= start + budget` hay `now - start >= budget`?** Dùng phép trừ trước, trong giới hạn elapsed của `long`.
6. **Timer quanh method chỉ đo đường return bình thường có đủ?** Không; cần bao phủ exception.
7. **`finally` có thể gây lỗi instrumentation nào?** Recorder trong `finally` có thể che lỗi gốc nếu nó ném exception.
8. **Method trả `CompletableFuture` ngay; timer trong `finally` đo gì?** Thời gian method trả future, không nhất thiết đo khi future hoàn tất.
9. **`TimeUnit.NANOSECONDS.toMillis(999_999)` là bao nhiêu?** `0` vì chuyển đổi `long` bỏ phần lẻ.
10. **Metric yêu cầu “thời gian chạy CPU”; `nanoTime` có đủ?** Không; nó đo elapsed, bao gồm cả thời gian chờ.
11. **Vì sao unit test nên inject `LongSupplier`?** Để tạo mẫu thời gian định trước, kiểm thử nhánh success/error và phép trừ mà không phụ thuộc scheduling.
12. **Khi instrument bytecode, chỉ chèn trước lệnh `RETURN` là đủ?** Không; cần nhiều opcode return và exceptional exits, đồng thời giữ stack map frames hợp lệ.

### Tài liệu tham khảo

- [Oracle Java SE 21 — `System.nanoTime()` và `currentTimeMillis()`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/System.html): origin tùy ý, cặp phép đo, timeout và giới hạn overflow.
- [Oracle Java SE 21 — `TimeUnit`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/TimeUnit.html): chuyển đổi đơn vị độ dài thời gian.
- [Oracle Java SE 21 — `Duration`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Duration.html): biểu diễn duration và kiểm soát overflow khi chuyển sang nanosecond.
- [Oracle Java SE 21 — `CompletableFuture`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CompletableFuture.html): callback `whenComplete` cho ranh giới hoàn thành bất đồng bộ.
- [Oracle Java SE 21 — `ThreadMXBean`](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadMXBean.html): CPU time của thread, không đồng nhất với latency.
- [OpenJDK JMH](https://github.com/openjdk/jmh): công cụ microbenchmark Java dành cho so sánh code ở độ hạt nhỏ.

**Ghi nhớ:** cần một *duration* thì hãy đọc `System.nanoTime()` **hai lần trong cùng JVM** và dùng **`end - start`**. Chọn đúng ranh giới nghiệp vụ, đo đầy đủ đường thành công/lỗi và phân biệt rõ **elapsed duration**, **wall-clock timestamp** và **CPU time**.
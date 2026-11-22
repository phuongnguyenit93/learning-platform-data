# Đo thời gian trôi qua bằng `System.nanoTime()` trong Java 17

**Chủ đề:** Java 17  
**Chương:** Nguồn thời gian  
**Bài học:** Đo thời gian trôi qua bằng System.nanoTime

Khi cần biết một thao tác mất bao lâu, cần chọn đúng nguồn thời gian. Java có nhiều API liên quan đến thời gian, nhưng chúng phục vụ những mục đích khác nhau:

- `System.currentTimeMillis()` trả về thời gian hiện tại theo đồng hồ hệ thống, tính bằng mili giây kể từ epoch Unix.
- `Instant.now()` biểu diễn một thời điểm trên dòng thời gian toàn cầu, phù hợp ghi nhận timestamp.
- **`System.nanoTime()`** cung cấp nguồn thời gian đơn điệu (*monotonic time source*) với đơn vị nanosecond, phù hợp đo **khoảng thời gian đã trôi qua** (*elapsed time*).

Đối với đo thời lượng chạy của một đoạn code, cách dùng chuẩn là lấy hai lần đọc `nanoTime()` rồi trừ:

```java
long start = System.nanoTime();

// Đoạn công việc cần theo dõi
doWork();

long elapsed = System.nanoTime() - start;
```

Kết quả `elapsed` là khoảng thời gian đã trôi qua, tính theo nanosecond. Không diễn giải giá trị đọc trực tiếp từ `nanoTime()` như ngày giờ hoặc timestamp. Mốc gốc của đồng hồ này là tùy ý và chỉ hiệu số giữa các lần đọc trong cùng JVM mới có ý nghĩa.

## 1. Vì sao cần đồng hồ monotonic?

Một đồng hồ dùng để hiển thị ngày giờ phải phản ánh thời gian lịch. Đồng hồ hệ thống có thể được điều chỉnh bởi người dùng, dịch vụ đồng bộ thời gian, hệ điều hành hoặc môi trường ảo hóa.

Ví dụ, chương trình đọc thời gian hệ thống trước và sau một thao tác:

```java
long start = System.currentTimeMillis();

doWork();

long elapsedMillis = System.currentTimeMillis() - start;
```

Nếu đồng hồ hệ thống bị chỉnh lùi hoặc tiến trong khi thao tác chạy, hiệu số có thể không phản ánh chính xác thời gian thực tế đã trôi qua. Kết quả thậm chí có thể âm nếu đồng hồ bị lùi đủ xa.

`System.nanoTime()` được thiết kế cho việc đo thời lượng. Trong cùng JVM, hiệu số giữa hai lần đọc là cách dùng phù hợp vì nguồn này không bị ảnh hưởng bởi việc chỉnh đồng hồ lịch như `currentTimeMillis()`.

### 1.1. Hai loại thời gian, hai mục đích

| API | Ý nghĩa | Dùng cho |
|---|---|---|
| `System.currentTimeMillis()` | Thời gian hệ thống tính bằng millisecond từ epoch | Timestamp đơn giản, log thời điểm |
| `Instant.now()` | Thời điểm hiện tại trên dòng thời gian | Ngày giờ, timestamp, trao đổi dữ liệu |
| `System.nanoTime()` | Bộ đếm thời gian đơn điệu, mốc gốc tùy ý | Đo elapsed time, timeout, deadline |
| `LocalDateTime.now()` | Ngày giờ địa phương không kèm offset/zone | Hiển thị lịch địa phương, nghiệp vụ lịch |
| `Duration` | Khoảng thời gian theo giây và nano | Biểu diễn thời lượng sau khi đã đo hoặc tính toán |

Ví dụ, nếu cần ghi “người dùng gửi yêu cầu lúc 10:15:30”, dùng `Instant.now()` hoặc API ngày giờ phù hợp. Nếu cần đo “xử lý yêu cầu mất 18 ms”, dùng `System.nanoTime()`.

### 1.2. Monotonic không có nghĩa là thời gian lịch

Đồng hồ monotonic cung cấp một nguồn đo tiến về phía trước phù hợp để tính hiệu số. Nó không cho biết:

- Bây giờ là ngày nào.
- Thời điểm đọc tương ứng với epoch Unix nào.
- Giá trị tuyệt đối có thể chuyển thành `Instant` hay không.
- Hai máy khác nhau đang ở cùng một mốc thời gian hay không.

Có thể hình dung:

```text
Đồng hồ lịch (Instant/currentTimeMillis)
  2026-11-15 10:00:00
          |
          +-- có thể được điều chỉnh bởi hệ thống

Đồng hồ monotonic (nanoTime)
  mốc tùy ý ->  ... ->  ... ->  ...
       |                     |
      start                 end
       +------ end - start --+
              elapsed
```

Dùng đồng hồ lịch để biết **khi nào**; dùng đồng hồ monotonic để biết **bao lâu**.

## 2. Cách dùng cơ bản: lấy hiệu hai lần đọc

`System.nanoTime()` trả về một giá trị kiểu `long`, đơn vị nanosecond.

Một nanosecond là:

\[
1\text{ ns} = 10^{-9}\text{ giây}
\]

Ví dụ:

```java
public class ElapsedTimeExample {
    public static void main(String[] args) {
        long start = System.nanoTime();

        calculate();

        long end = System.nanoTime();
        long elapsedNanos = end - start;

        System.out.println("Elapsed: " + elapsedNanos + " ns");
    }

    private static void calculate() {
        long sum = 0;

        for (int i = 0; i < 1_000_000; i++) {
            sum += i;
        }

        // Giữ kết quả được sử dụng để minh họa công việc.
        System.out.println("sum = " + sum);
    }
}
```

Công thức quan trọng:

\[
\text{elapsed} = \text{end} - \text{start}
\]

Không cần biết giá trị tuyệt đối của `start` hoặc `end` là bao nhiêu. Chỉ cần hai lần đọc thuộc cùng nguồn monotonic trong cùng JVM và lấy hiệu đúng thứ tự.

### 2.1. Vì sao nên lưu thời điểm bắt đầu trước công việc?

```java
long start = System.nanoTime();
doWork();
long elapsed = System.nanoTime() - start;
```

Khoảng đo bắt đầu ngay trước `doWork()` và kết thúc ngay sau khi `doWork()` trả về. Những thao tác nằm ngoài hai điểm đó không được tính.

Nếu đặt việc tạo dữ liệu đầu vào, mở kết nối hoặc ghi log vào trong vùng đo, thời gian đó cũng được tính. Vì vậy, hãy xác định rõ **đang muốn đo phần nào** trước khi đặt hai điểm lấy mẫu.

### 2.2. Dùng tên biến thể hiện đơn vị

Tránh đặt tên chung như `time` hoặc `result` khi giá trị là một số thời gian. Nên dùng:

```java
long startNanos = System.nanoTime();
doWork();
long elapsedNanos = System.nanoTime() - startNanos;
```

Tên `elapsedNanos` giúp người đọc biết giá trị là thời lượng và đơn vị đang dùng là nanosecond.

## 3. Chuyển đổi nanosecond sang đơn vị dễ đọc

`nanoTime()` trả kết quả theo nanosecond, nhưng không phải lúc nào cũng cần hiển thị ở đơn vị đó.

Các quan hệ:

| Đơn vị | Số nanosecond |
|---|---:|
| 1 microsecond (µs) | 1.000 ns |
| 1 millisecond (ms) | 1.000.000 ns |
| 1 second (s) | 1.000.000.000 ns |
| 1 minute | 60.000.000.000 ns |

Có thể tự chia:

```java
long elapsedNanos = 25_000_000L;

double elapsedMillis = elapsedNanos / 1_000_000.0;
double elapsedSeconds = elapsedNanos / 1_000_000_000.0;

System.out.println(elapsedMillis + " ms"); // 25.0 ms
System.out.println(elapsedSeconds + " s"); // 0.025 s
```

Dùng số thực ở phép chia nếu muốn giữ phần lẻ. Nếu viết `elapsedNanos / 1_000_000` với hai toán hạng kiểu nguyên, Java thực hiện chia nguyên và bỏ phần dư.

### 3.1. Dùng `TimeUnit`

`java.util.concurrent.TimeUnit` hỗ trợ chuyển đổi đơn vị:

```java
import java.util.concurrent.TimeUnit;

long elapsedNanos = 25_123_456L;

long millis = TimeUnit.NANOSECONDS.toMillis(elapsedNanos);
long micros = TimeUnit.NANOSECONDS.toMicros(elapsedNanos);

System.out.println(millis + " ms"); // 25 ms
System.out.println(micros + " µs"); // 25123 µs
```

Các phương thức chuyển đổi sang đơn vị lớn hơn thường **cắt phần lẻ** theo phép chia nguyên. Vì vậy, `25_123_456 ns` chuyển thành `25 ms`, không phải `25.123456 ms`.

Nếu cần phần lẻ, hãy chuyển sang `double` với hệ số phù hợp hoặc dùng `Duration` để giữ phần giây và nanosecond.

### 3.2. Dùng `Duration` để biểu diễn thời lượng

`java.time.Duration` biểu diễn một khoảng thời gian với độ phân giải nanosecond:

```java
import java.time.Duration;

long start = System.nanoTime();
doWork();
long elapsedNanos = System.nanoTime() - start;

Duration elapsed = Duration.ofNanos(elapsedNanos);

System.out.println(elapsed);
System.out.println(elapsed.toMillis() + " ms");
System.out.println(elapsed.toNanos() + " ns");
```

`Duration` hữu ích khi cần truyền thời lượng giữa các tầng ứng dụng hoặc định dạng kết quả. Nó không thay thế việc chọn đúng đồng hồ: vẫn dùng `nanoTime()` để đo, rồi chuyển hiệu số sang `Duration`.

### 3.3. Chú ý phép chuyển đổi có thể mất độ chính xác

`Duration.toMillis()` trả số mili giây nguyên; phần nhỏ hơn một millisecond không còn trong kết quả đó.

Ví dụ:

```java
Duration duration = Duration.ofNanos(1_500_000);

System.out.println(duration.toNanos()); // 1500000
System.out.println(duration.toMillis()); // 1
System.out.println(duration);            // PT0.0015S
```

Nếu yêu cầu chẩn đoán cần giữ chính xác phần nanosecond đã đo, lưu `elapsedNanos` hoặc giữ `Duration` thay vì chỉ lưu `toMillis()`.

## 4. Độ chính xác và độ phân giải không giống nhau

Tên `nanoTime` có chữ “nano”, nhưng điều đó **không bảo đảm** mọi lần đọc đều cách nhau đúng 1 nanosecond hoặc hệ thống có thể đo chính xác tới từng nanosecond.

Cần phân biệt:

- **Đơn vị (unit):** Giá trị được trả về tính theo nanosecond.
- **Độ phân giải (resolution):** Khoảng thay đổi nhỏ nhất có thể quan sát ở nguồn đồng hồ trên hệ thống hiện tại.
- **Độ chính xác (accuracy):** Mức độ gần với thời gian thực tế mà phép đo phản ánh.
- **Chi phí đọc đồng hồ:** Thời gian và chi phí thực hiện một lần gọi API.

Javadoc của `System.nanoTime()` nêu rõ giá trị trả về có đơn vị nanosecond nhưng độ phân giải ít nhất phải tốt như `currentTimeMillis()`; độ phân giải thực tế phụ thuộc hệ thống. Do đó, một thao tác rất ngắn có thể cho hiệu số bằng 0 hoặc một giá trị được làm tròn theo độ phân giải phần cứng/hệ điều hành.

Ví dụ:

```java
long start = System.nanoTime();
int result = 1 + 1;
long elapsed = System.nanoTime() - start;

System.out.println(elapsed);
```

Không nên kết luận rằng thao tác cộng chỉ mất đúng 0 ns nếu kết quả in ra là 0. Điều đó chỉ cho biết khoảng đo nhỏ hơn mức có thể quan sát trong lần đo đó, hoặc bị ảnh hưởng bởi độ phân giải và chi phí đo.

### 4.1. Đo thao tác rất ngắn bằng cách lặp nhiều lần

Đối với thao tác rất nhanh, có thể đo tổng thời gian của nhiều lần thực hiện rồi tính trung bình sơ bộ:

```java
int iterations = 1_000_000;

long start = System.nanoTime();

for (int i = 0; i < iterations; i++) {
    performOperation();
}

long elapsed = System.nanoTime() - start;

double averageNanos = (double) elapsed / iterations;

System.out.println("Average: " + averageNanos + " ns/op");
```

Cách này giảm ảnh hưởng của việc đo một thao tác quá ngắn, nhưng vẫn **không phải benchmark đáng tin cậy** nếu thiếu warmup, kiểm soát JIT, dead-code elimination, GC và các yếu tố môi trường. Phần benchmark chuyên nghiệp được trình bày ở mục 10.

## 5. Tính chất và giới hạn của giá trị trả về

`System.nanoTime()` trả về `long`. Giá trị này:

- Có thể âm.
- Có mốc gốc tùy ý.
- Không phải số nanosecond kể từ epoch.
- Chỉ có ý nghĩa khi lấy hiệu giữa các lần đọc trong cùng JVM.
- Có thể tràn khi bộ đếm đi qua giới hạn của kiểu `long`, vì vậy cần dùng phép trừ theo đúng mẫu.

### 5.1. Không so sánh trực tiếp hai giá trị tuyệt đối

Không nên viết:

```java
long start = System.nanoTime();

// ...

long end = System.nanoTime();

if (end > start) {
    // Không phải cách kiểm tra elapsed time được khuyến nghị.
}
```

Hãy tính hiệu:

```java
long elapsed = end - start;

if (elapsed >= 0) {
    // Khoảng đo theo thứ tự thông thường.
}
```

Tuy nhiên, trong code thực tế không cần kiểm tra `elapsed >= 0` chỉ để xác nhận đồng hồ. Hãy dùng hiệu số theo đúng công thức và so sánh với ngưỡng thời lượng cần thiết.

### 5.2. Vì sao phép trừ vẫn dùng được khi bộ đếm tràn?

`long` có miền giá trị hữu hạn. Nếu bộ đếm đơn điệu quay vòng từ giá trị lớn nhất sang giá trị âm nhỏ nhất, phép trừ `end - start` theo số học hai bù vẫn cho hiệu đúng khi khoảng thời gian cần đo nhỏ hơn nửa miền chu kỳ của `long`.

Với nanosecond, giới hạn này xấp xỉ 292 năm. Đối với timeout và thời lượng trong ứng dụng thông thường, khoảng đo luôn nhỏ hơn giới hạn đó.

Do vậy, mẫu được khuyến nghị là:

```java
long start = System.nanoTime();

// ...

long elapsed = System.nanoTime() - start;
```

Không cần xử lý trường hợp wrap-around bằng cách so sánh tuyệt đối hoặc tự kiểm tra giá trị âm.

### 5.3. Không lưu giá trị nanoTime làm timestamp lâu dài

Không lưu `System.nanoTime()` vào database rồi dùng nó như thời điểm xảy ra sự kiện. Giá trị tuyệt đối không có mốc epoch được đảm bảo và không có ý nghĩa giữa các tiến trình hoặc máy khác nhau.

Nếu cần lưu timestamp, dùng `Instant`:

```java
import java.time.Instant;

Instant occurredAt = Instant.now();
```

Nếu cần lưu thời lượng, lưu `Duration` hoặc số nanosecond/millisecond theo hợp đồng dữ liệu đã thống nhất:

```java
long elapsedNanos = 12_345_678L;
Duration elapsed = Duration.ofNanos(elapsedNanos);
```

## 6. Đo thời gian với try/finally

Nếu đoạn code được đo có thể ném exception, có thể dùng `finally` để bảo đảm ghi nhận thời lượng dù thành công hay thất bại.

```java
long start = System.nanoTime();

try {
    processRequest();
} finally {
    long elapsed = System.nanoTime() - start;
    System.out.println("processRequest took " + elapsed + " ns");
}
```

`finally` chạy khi khối `try` kết thúc bình thường hoặc do exception, trừ các trường hợp JVM/process bị kết thúc bất thường. Cách này hữu ích khi cần log thời gian thực thi để chẩn đoán.

Trong ứng dụng thực tế, nên đưa logic đo vào một tiện ích để không lặp lại:

```java
import java.util.concurrent.TimeUnit;

static long measureNanos(Runnable task) {
    long start = System.nanoTime();

    try {
        task.run();
    } finally {
        long elapsed = System.nanoTime() - start;
        System.out.println(
                "Elapsed: " + TimeUnit.NANOSECONDS.toMicros(elapsed) + " µs"
        );
    }

    return System.nanoTime() - start;
}
```

Ví dụ trên chỉ minh họa ý tưởng; vì lấy thời gian một lần trong `finally` rồi lại lấy lần nữa khi `return`, giá trị trả về có thể dài hơn thời lượng được in. Trong code cần một kết quả duy nhất, hãy lưu hiệu số một lần:

```java
static long measureNanos(Runnable task) {
    long start = System.nanoTime();
    long elapsed;

    try {
        task.run();
    } finally {
        elapsed = System.nanoTime() - start;
        System.out.println("Elapsed: " + elapsed + " ns");
    }

    return elapsed;
}
```

Nếu `task.run()` ném exception, phương thức vẫn thực hiện `finally` nhưng exception tiếp tục được truyền ra; giá trị trả về không được sử dụng trong trường hợp đó. Nếu muốn trả cả trạng thái thành công/thất bại và thời lượng, hãy thiết kế kiểu kết quả riêng thay vì nuốt exception.

## 7. Dùng nanoTime để thực hiện timeout

Một ứng dụng thường cần giới hạn một thao tác: chờ tài nguyên, thử lại request hoặc đợi tác vụ hoàn thành tối đa một khoảng thời gian.

Có thể đo elapsed so với timeout:

```java
long timeoutNanos = TimeUnit.SECONDS.toNanos(2);
long start = System.nanoTime();

while (!isReady()) {
    if (System.nanoTime() - start >= timeoutNanos) {
        throw new IllegalStateException("Timed out");
    }
}
```

Cách này dùng hiệu số monotonic, không phụ thuộc đồng hồ lịch bị chỉnh.

### 7.1. Viết helper kiểm tra timeout

```java
static boolean hasTimedOut(long startNanos, long timeoutNanos) {
    return System.nanoTime() - startNanos >= timeoutNanos;
}
```

Sử dụng:

```java
long start = System.nanoTime();
long timeout = TimeUnit.MILLISECONDS.toNanos(500);

while (!isReady()) {
    if (hasTimedOut(start, timeout)) {
        break;
    }

    Thread.onSpinWait();
}
```

`Thread.onSpinWait()` là gợi ý cho JVM/CPU rằng vòng lặp đang chờ bận (*spin-wait*); nó không làm cho vòng lặp trở thành cơ chế chờ hiệu quả trong mọi trường hợp. Nếu có thể, hãy dùng `wait`, `Condition.await`, `BlockingQueue.poll(timeout, unit)` hoặc API chờ có timeout để tránh tiêu thụ CPU liên tục.

### 7.2. Vì sao so sánh hiệu số thay vì cộng deadline?

Một cách viết dễ nghĩ tới là:

```java
long deadline = System.nanoTime() + timeoutNanos;

if (System.nanoTime() >= deadline) {
    // timeout
}
```

Cách này có thể gặp vấn đề khi phép cộng tràn `long` và khi so sánh tuyệt đối qua điểm wrap-around. Mẫu hiệu số:

```java
if (System.nanoTime() - startNanos >= timeoutNanos) {
    // timeout
}
```

là cách thông dụng và phù hợp với quy tắc dùng `nanoTime()`, miễn là khoảng thời gian cần đo nhỏ hơn nửa chu kỳ của bộ đếm (khoảng 292 năm).

### 7.3. Chuyển timeout từ Duration

```java
import java.time.Duration;

Duration timeout = Duration.ofSeconds(2);
long timeoutNanos = timeout.toNanos();
long start = System.nanoTime();

while (!isReady()) {
    if (System.nanoTime() - start >= timeoutNanos) {
        throw new IllegalStateException("Timed out");
    }
}
```

`Duration.toNanos()` có thể ném `ArithmeticException` nếu thời lượng quá lớn để biểu diễn bằng `long` nanosecond. Với timeout thực tế của ứng dụng, thường không gặp giới hạn này; nếu nhận duration do người dùng cấu hình, cần xác thực phạm vi.

### 7.4. Không dùng busy loop nếu có cơ chế chờ phù hợp

Đoạn vòng lặp trên chỉ minh họa cách tính timeout. Nếu chờ một điều kiện do thread khác thay đổi, dùng cơ chế đồng bộ hoặc API có timeout sẽ tốt hơn:

```java
boolean completed = latch.await(2, TimeUnit.SECONDS);

if (!completed) {
    throw new IllegalStateException("Timed out");
}
```

`CountDownLatch.await(timeout, unit)` đã nhận thời lượng chờ và tự quản lý việc chờ. Không cần tự quay vòng đọc `nanoTime()` nếu API đồng bộ đã hỗ trợ timeout đúng nhu cầu.

## 8. Đo thời gian thực thi nhiều tác vụ

Khi có nhiều tác vụ, cần xác định muốn đo:

- Thời gian của từng tác vụ riêng.
- Tổng thời gian từ lúc bắt đầu đến khi tất cả hoàn tất (*wall-clock elapsed time*).
- Tổng thời gian CPU mà các thread tiêu thụ.

`System.nanoTime()` đo khoảng thời gian trôi qua theo đồng hồ monotonic, không phải CPU time. Nếu nhiều thread chạy song song, tổng elapsed thường nhỏ hơn tổng thời gian thực thi riêng của tất cả thread.

### 8.1. Đo thời gian toàn bộ batch

```java
long start = System.nanoTime();

runAllTasksAndWaitForCompletion();

long elapsed = System.nanoTime() - start;

System.out.println("Batch elapsed: " + elapsed + " ns");
```

Đặt điểm kết thúc **sau khi** tất cả tác vụ đã hoàn thành. Nếu chỉ đo đến lúc submit task vào executor, kết quả là thời gian submit chứ không phải thời gian xử lý xong.

### 8.2. Đo từng tác vụ

```java
Runnable timedTask = () -> {
    long start = System.nanoTime();

    try {
        doWork();
    } finally {
        long elapsed = System.nanoTime() - start;
        System.out.println(
                Thread.currentThread().getName()
                        + " took " + elapsed + " ns"
        );
    }
};
```

Mỗi lần chạy `timedTask` tự lấy mốc riêng, do đó có thể ghi nhận elapsed của từng worker. Trong hệ thống có nhiều tác vụ, nên dùng metrics hoặc logger có cấu trúc thay vì in đồng thời quá nhiều dòng ra console.

### 8.3. Wall-clock elapsed khác tổng CPU time

Ví dụ hai thread mỗi thread chạy trong khoảng 1 giây đồng thời:

```text
Thời gian trôi qua của batch (wall-clock): khoảng 1 giây
Tổng thời gian của hai tác vụ:              khoảng 2 giây
```

`nanoTime()` quanh toàn bộ batch đo khoảng thời gian trôi qua của batch. Nó không cộng CPU time của từng thread. Nếu cần đo CPU time, cần dùng API quản lý thread như `ThreadMXBean` khi môi trường hỗ trợ và cho phép.

## 9. Phân biệt nanoTime với sleep và lịch chạy

`Thread.sleep()` yêu cầu thread tạm dừng trong một khoảng thời gian tối thiểu theo hợp đồng API; thread có thể thức dậy muộn hơn do scheduler, tải hệ thống hoặc độ phân giải timer.

```java
long start = System.nanoTime();

Thread.sleep(100);

long elapsed = System.nanoTime() - start;

System.out.println(elapsed / 1_000_000.0 + " ms");
```

Kết quả thường lớn hơn hoặc xấp xỉ 100 ms, không nên kỳ vọng luôn đúng 100.000.000 ns. `nanoTime()` đo khoảng thực tế đã trôi qua, còn `sleep` chỉ yêu cầu tạm dừng ít nhất khoảng thời gian được chỉ định.

Tương tự, một task được lên lịch bằng `ScheduledExecutorService` có thể chạy trễ so với thời điểm dự kiến. Dùng `nanoTime()` để quan sát độ trễ thực tế, không giả định scheduler sẽ thực thi đúng từng nanosecond.

## 10. Đo benchmark: nanoTime hữu ích nhưng không thay thế JMH

Một đoạn đo đơn giản:

```java
long start = System.nanoTime();

for (int i = 0; i < 1_000_000; i++) {
    calculate();
}

long elapsed = System.nanoTime() - start;

System.out.println(elapsed + " ns");
```

hữu ích để chẩn đoán sơ bộ, nhưng không phải benchmark vi mô đáng tin cậy. JVM tối ưu mã khi chạy, ví dụ:

- **JIT compilation:** phương thức có thể được biên dịch tối ưu sau một số lần chạy.
- **Warmup:** những lần chạy đầu có thể chịu chi phí nạp lớp, biên dịch và khởi tạo.
- **Dead-code elimination:** kết quả không được sử dụng có thể khiến compiler loại bỏ một phần công việc.
- **Constant folding:** biểu thức chỉ gồm hằng số có thể được tính trước.
- **Garbage collection:** GC có thể ảnh hưởng đến thời gian một lần đo.
- **CPU frequency scaling và scheduler:** tải hệ thống và tần số CPU thay đổi kết quả.
- **Fork và trạng thái JVM:** các lần đo trong cùng JVM có thể ảnh hưởng lẫn nhau.

### 10.1. Dùng JMH cho benchmark Java

JMH (Java Microbenchmark Harness) là công cụ chuyên dụng để đo benchmark Java. Nó cung cấp cơ chế warmup, measurement iteration, fork, tiêu thụ kết quả và báo cáo thống kê.

Ví dụ benchmark tối giản với JMH:

```java
import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.State;
import org.openjdk.jmh.annotations.Scope;

@State(Scope.Thread)
public class CalculationBenchmark {

    @Benchmark
    public long sum() {
        long result = 0;

        for (int i = 0; i < 1_000; i++) {
            result += i;
        }

        return result;
    }
}
```

JMH sẽ quản lý vòng đo và sử dụng kết quả benchmark theo cơ chế của nó để hạn chế tối ưu loại bỏ công việc. Không tự viết vòng lặp gọi `nanoTime()` cho từng phép toán rồi coi kết quả là benchmark chính xác.

### 10.2. Khi nào dùng nanoTime trực tiếp?

| Tình huống | Cách phù hợp |
|---|---|
| Log thời gian xử lý một request | `System.nanoTime()` lấy hiệu |
| Đo một đoạn code trong quá trình debug | `System.nanoTime()` |
| Timeout trong vòng lặp hoặc API đồng bộ | `nanoTime()` hoặc API nhận timeout |
| Benchmark so sánh hai implementation | JMH |
| Ghi nhận thời điểm xảy ra sự kiện | `Instant.now()` |
| Đo thời gian CPU của thread | `ThreadMXBean` khi phù hợp |

## 11. Xây dựng tiện ích đo thời gian có thể tái sử dụng

Nếu cần đo một thao tác trả về kết quả, có thể viết helper dùng `Supplier<T>` và trả về cả giá trị lẫn thời lượng. Đoạn dưới đây chỉ đọc đồng hồ hai lần: một lần trước và một lần sau thao tác.

```java
import java.time.Duration;
import java.util.function.Supplier;

public final class Timer {

    private Timer() {
    }

    public record Measurement<T>(T value, Duration elapsed) {}

    public static <T> Measurement<T> measure(Supplier<T> action) {
        long start = System.nanoTime();

        T value = action.get();

        long elapsed = System.nanoTime() - start;
        return new Measurement<>(value, Duration.ofNanos(elapsed));
    }
}
```

Nếu `action.get()` ném exception, exception tiếp tục được truyền ra và không có `Measurement`. Đây thường là hành vi phù hợp nếu caller cần xử lý lỗi theo luồng thông thường.

Nếu cần ghi thời lượng cả khi thao tác thất bại, có thể đo trong `finally` nhưng không cần trả thời lượng từ helper:

```java
static <T> T measureAndLog(Supplier<T> action) {
    long start = System.nanoTime();

    try {
        return action.get();
    } finally {
        long elapsed = System.nanoTime() - start;
        System.out.println("Elapsed: " + elapsed + " ns");
    }
}
```

Ở đây `finally` chỉ ghi nhận thời lượng; nếu thao tác ném exception, exception vẫn tiếp tục truyền ra. Không nên bắt rồi bỏ qua exception chỉ để lấy được số đo.

Với tác vụ không trả kết quả, dùng `Runnable`:

```java
static Duration measure(Runnable action) {
    long start = System.nanoTime();

    action.run();

    return Duration.ofNanos(System.nanoTime() - start);
}
```

Các helper này phù hợp cho tiện ích nhỏ hoặc chẩn đoán. Trong ứng dụng lớn, hãy cân nhắc metrics/tracing hiện có để tránh tự xây dựng một lớp đo lường trùng lặp.

Sử dụng:

```java
Timer.Measurement<String> measurement =
        Timer.measure(() -> loadData());

System.out.println(measurement.value());
System.out.println(measurement.elapsed().toMillis() + " ms");
```

## 12. Các lỗi thường gặp

### Lỗi 1. Dùng `currentTimeMillis()` để đo elapsed

Đồng hồ hệ thống có thể bị điều chỉnh. Dùng `System.nanoTime()` cho thời lượng.

### Lỗi 2. Xem giá trị nanoTime là timestamp

Mốc gốc tùy ý. Không chuyển trực tiếp giá trị sang `Instant`, không lưu làm thời điểm lịch.

### Lỗi 3. So sánh giá trị tuyệt đối thay vì hiệu số

Dùng `end - start`. Không dựa vào `end > start` để kiểm tra elapsed.

### Lỗi 4. Cho rằng nanoTime bảo đảm độ phân giải 1 ns

Đơn vị là nanosecond, nhưng độ phân giải thực tế phụ thuộc hệ thống. Một phép đo rất ngắn có thể cho kết quả 0.

### Lỗi 5. Chia nguyên làm mất phần lẻ

`elapsedNanos / 1_000_000` là phép chia nguyên nếu cả hai toán hạng là kiểu nguyên. Dùng `1_000_000.0` nếu cần phần thập phân.

### Lỗi 6. Đo thời gian submit thay vì thời gian hoàn thành task

Đặt điểm kết thúc sau khi các task hoàn tất hoặc sau khi `Future.get()`/`awaitTermination()` hoàn thành, tùy cấu trúc chương trình.

### Lỗi 7. Tự benchmark một lần rồi kết luận

JIT, warmup, GC và scheduler có thể làm kết quả biến động. Dùng JMH cho benchmark nghiêm túc.

### Lỗi 8. Tạo deadline bằng phép cộng rồi so sánh tuyệt đối

Dùng mẫu hiệu số `System.nanoTime() - start >= timeout` để tránh các vấn đề so sánh qua wrap-around.

### Lỗi 9. Dùng nanoTime để đo CPU time

`nanoTime` đo elapsed time. Khi nhiều thread chạy đồng thời, elapsed không phải tổng CPU time của chúng.

### Lỗi 10. Chuyển đổi đơn vị rồi bỏ phần dư ngoài ý muốn

`TimeUnit.NANOSECONDS.toMillis` trả millisecond nguyên. Nếu cần độ chính xác phần lẻ, giữ nanosecond hoặc dùng `Duration`.

## 13. Ví dụ hoàn chỉnh: đo thời gian xử lý và định dạng Duration

Lưu chương trình sau thành `NanoTimeDemo.java`:

```java
import java.time.Duration;
import java.util.concurrent.TimeUnit;

public class NanoTimeDemo {

    private static long doWork() {
        long result = 0;

        for (int i = 0; i < 5_000_000; i++) {
            result += i;
        }

        return result;
    }

    public static void main(String[] args) {
        long startNanos = System.nanoTime();

        long result = doWork();

        long elapsedNanos = System.nanoTime() - startNanos;

        Duration elapsed = Duration.ofNanos(elapsedNanos);

        System.out.println("result = " + result);
        System.out.println("elapsed ns = " + elapsedNanos);
        System.out.println(
                "elapsed ms = "
                        + TimeUnit.NANOSECONDS.toMillis(elapsedNanos)
        );
        System.out.println("duration = " + elapsed);
    }
}
```

Biên dịch và chạy bằng JDK 17:

```bash
javac --release 17 NanoTimeDemo.java
java NanoTimeDemo
```

Thời lượng cụ thể phụ thuộc máy, JDK, tải hệ thống và trạng thái JIT; không có một con số output cố định. Điều quan trọng là:

- `startNanos` được lấy ngay trước công việc.
- `elapsedNanos` là hiệu số giữa hai lần đọc.
- `Duration.ofNanos` chuyển thời lượng sang kiểu biểu diễn rõ nghĩa.
- `TimeUnit` chuyển sang millisecond nguyên để hiển thị.
- Kết quả `result` được sử dụng, tránh ví dụ công việc chỉ tạo ra giá trị không dùng đến.

## 14. Bài tập tự luyện

### Bài 1. Tính elapsed

Cho:

```java
long start = System.nanoTime();

// work

long elapsed = System.nanoTime() - start;
```

**Câu hỏi:** `elapsed` có đơn vị gì?

**Đáp án:** Nanosecond, vì `System.nanoTime()` trả giá trị theo đơn vị nanosecond.

### Bài 2. Chọn API đúng

Một hệ thống cần ghi thời điểm user đăng nhập và thời lượng xử lý đăng nhập.

**Đáp án:** Dùng `Instant.now()` để ghi thời điểm; dùng `System.nanoTime()` lấy hiệu để đo thời lượng.

### Bài 3. Vì sao không cộng deadline?

Một lập trình viên viết `long deadline = System.nanoTime() + timeout;` rồi so sánh `System.nanoTime() >= deadline`.

**Đáp án:** Cách này có thể sai khi giá trị tràn và qua điểm wrap-around. Dùng hiệu `System.nanoTime() - start >= timeout`.

### Bài 4. Chuyển đổi đơn vị

Nếu `elapsedNanos = 1_500_000`, `TimeUnit.NANOSECONDS.toMillis(elapsedNanos)` trả về bao nhiêu?

**Đáp án:** `1` millisecond vì phép chuyển đổi trả giá trị nguyên và bỏ phần dư 0.5 ms.

### Bài 5. Độ phân giải

Một đoạn code rất ngắn cho kết quả `elapsed == 0`. Có thể kết luận code không tiêu tốn thời gian không?

**Đáp án:** Không. Nguồn đồng hồ có độ phân giải hữu hạn; khoảng đo có thể nhỏ hơn mức thay đổi quan sát được.

### Bài 6. Đo batch song song

Một chương trình khởi chạy 10 task rồi đo ngay sau khi submit. Kết quả phản ánh điều gì?

**Đáp án:** Chủ yếu phản ánh thời gian submit task, không phải thời gian hoàn tất. Cần đợi các task hoàn thành trước khi lấy mốc kết thúc.

### Bài 7. Benchmark

Một vòng lặp gọi phương thức 1 lần rồi lấy nanoTime để kết luận phương thức A nhanh hơn B. Kết luận có đáng tin không?

**Đáp án:** Không. Cần nhiều iteration, warmup và kiểm soát các yếu tố JVM; dùng JMH cho microbenchmark.

### Bài 8. Phân biệt elapsed và CPU time

Hai thread chạy đồng thời, mỗi thread mất khoảng 2 giây. Đo quanh toàn batch bằng nanoTime có nhất thiết trả 4 giây không?

**Đáp án:** Không. Nếu chạy đồng thời, elapsed có thể gần 2 giây. Tổng CPU time hoặc tổng thời lượng riêng của hai task là khái niệm khác.

## 15. Tài liệu tham khảo chính thức

- [JDK 17 API — System.nanoTime()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#nanoTime()): hợp đồng API, mốc gốc tùy ý, đơn vị nanosecond và cách lấy hiệu để đo elapsed.
- [JDK 17 API — System.currentTimeMillis()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#currentTimeMillis()): thời gian lịch tính theo millisecond từ epoch.
- [JDK 17 API — Duration](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Duration.html): biểu diễn thời lượng và chuyển đổi đơn vị.
- [JDK 17 API — TimeUnit](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/TimeUnit.html): chuyển đổi giữa các đơn vị thời gian.
- [JDK 17 API — Instant](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html): biểu diễn một thời điểm trên dòng thời gian.
- [OpenJDK JMH](https://openjdk.org/projects/code-tools/jmh/): công cụ benchmark vi mô cho Java và JVM.

**Ghi nhớ:** Để đo thời gian trôi qua, lấy `start = System.nanoTime()` trước công việc và tính `System.nanoTime() - start` sau công việc. Chỉ dùng hiệu số trong cùng JVM, không xem giá trị tuyệt đối như timestamp. Chuyển đổi sang `TimeUnit` hoặc `Duration` khi cần hiển thị, dùng mẫu hiệu số cho timeout và chọn JMH nếu mục tiêu là benchmark nghiêm túc.

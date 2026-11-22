# Đo thời gian chạy trong Java

Đo thời gian chạy giúp trả lời một câu hỏi cụ thể: một đoạn code, tác vụ hoặc request mất bao lâu để hoàn thành? Trong Java, lựa chọn phổ biến nhất để đo **thời gian đã trôi qua (elapsed time)** là **System.nanoTime()**. Nếu cần timestamp theo lịch hoặc thời điểm bắt đầu/kết thúc để ghi log, dùng **Instant.now()** hoặc **System.currentTimeMillis()**.

Với một đoạn code lớn hoặc một thao tác nghiệp vụ, đo bằng nanoTime thường đủ để biết thời gian thực tế. Với microbenchmark cần so sánh các method rất nhanh, nên dùng **JMH (Java Microbenchmark Harness)** để xử lý warm-up, JIT compilation, dead-code elimination, fork và sai số thống kê.

Bài này phân biệt đồng hồ wall-clock, elapsed time và CPU time; hướng dẫn cách đo đúng, đổi đơn vị, xử lý async/concurrency, tránh sai lệch do JVM và xây dựng benchmark đáng tin cậy.

## 1. Ba loại thời gian cần phân biệt

Không có một loại đồng hồ phù hợp cho mọi câu hỏi. Trước khi viết code, xác định bạn muốn đo đại lượng nào.

| Loại thời gian | Câu hỏi | API thường dùng |
|---|---|---|
| Wall-clock time | Bây giờ là mấy giờ? Sự kiện xảy ra lúc nào? | Instant.now(), System.currentTimeMillis() |
| Elapsed time | Từ lúc bắt đầu đến khi kết thúc đã trôi qua bao lâu? | System.nanoTime() |
| Thread CPU time | Một thread thực sự dùng CPU bao lâu? | ThreadMXBean |

### Wall-clock time

Wall-clock time biểu diễn thời điểm theo lịch, thường tính từ Unix epoch. Nó phù hợp để ghi timestamp trong log, lưu thời điểm tạo dữ liệu hoặc đối chiếu sự kiện giữa nhiều hệ thống.

Ví dụ:

~~~java
Instant startedAt = Instant.now();
// Thực hiện công việc
Instant finishedAt = Instant.now();

System.out.println("Started at: " + startedAt);
System.out.println("Finished at: " + finishedAt);
~~~

Đồng hồ hệ thống có thể được điều chỉnh bởi NTP, quản trị viên, hypervisor hoặc hệ điều hành. Vì vậy, hiệu của hai wall-clock timestamp không phải lựa chọn tốt nhất để đo thời lượng chính xác.

### Elapsed time

Elapsed time là thời gian thực tế trôi qua giữa hai điểm trong cùng một tiến trình đo. Nó bao gồm thời gian thread chạy CPU, bị scheduler tạm dừng, chờ lock, chờ file/network I/O và các khoảng chờ khác.

Dùng System.nanoTime() cho mục tiêu này:

~~~java
long start = System.nanoTime();

performTask();

long elapsed = System.nanoTime() - start;
~~~

nanoTime có nguồn gốc thời gian tùy ý, không phải Unix timestamp. Giá trị có thể âm và không có ý nghĩa khi so sánh giữa hai máy hoặc giữa các lần chạy JVM. Chỉ tính hiệu giữa hai lần đọc trong cùng JVM.

### Thread CPU time

Thread CPU time đo lượng thời gian CPU mà một thread đã thực sự sử dụng. Nó không bao gồm thời gian thread ngủ hoặc chờ I/O.

Ví dụ, một request mất 500 ms elapsed time nhưng thread chỉ dùng 20 ms CPU time có thể đang chờ database, network, lock hoặc scheduler.

Dùng java.lang.management.ThreadMXBean khi cần phân biệt CPU work với waiting. Khả năng hỗ trợ phụ thuộc JVM và hệ điều hành.

## 2. System.nanoTime(): lựa chọn cho elapsed time

System.nanoTime() trả về giá trị của nguồn thời gian có độ phân giải cao theo đơn vị nanosecond. Phương thức này được thiết kế để đo khoảng thời gian đã trôi qua.

Ví dụ:

~~~java
long start = System.nanoTime();

performTask();

long end = System.nanoTime();
long elapsedNanos = end - start;

System.out.println("Elapsed: " + elapsedNanos + " ns");
~~~

Công thức cần nhớ:

~~~java
elapsed = end - start;
~~~

Không dùng end hoặc start riêng lẻ làm timestamp. Chỉ hiệu của hai giá trị mới có ý nghĩa.

### Độ chính xác và độ phân giải không giống nhau

Đơn vị trả về là nanosecond, nhưng điều đó không bảo đảm đồng hồ thay đổi chính xác từng nanosecond. Độ phân giải thực tế phụ thuộc hệ điều hành, phần cứng và JVM.

- **Precision:** mức chi tiết biểu diễn của con số.
- **Resolution:** khoảng thời gian nhỏ nhất mà nguồn đồng hồ có thể phân biệt.
- **Accuracy:** mức gần đúng với thời gian thực cần đo.

Một giá trị có nhiều chữ số thập phân không tự động có nghĩa phép đo chính xác hơn.

### Không so sánh giá trị tuyệt đối

Không dùng giá trị nanoTime như timestamp hoặc mốc thời gian toàn cục. Khi tính timeout, nên so sánh hiệu để tránh vấn đề nguồn thời gian có origin tùy ý và giá trị có thể wrap:

~~~java
long start = System.nanoTime();
long timeoutNanos = TimeUnit.SECONDS.toNanos(5);

while (System.nanoTime() - start < timeoutNanos) {
    // Chờ hoặc kiểm tra điều kiện
}
~~~

Phép trừ hai lần đọc nanoTime là cách tính elapsed time đúng. Với các khoảng thời gian thực tế của ứng dụng, wrap-around không phải vấn đề; không dùng các giá trị tuyệt đối như timestamp.

## 3. System.currentTimeMillis() và Instant.now()

### System.currentTimeMillis()

Phương thức này trả về số milliseconds kể từ Unix epoch (1970-01-01T00:00:00Z).

~~~java
long timestamp = System.currentTimeMillis();
System.out.println("Epoch millis: " + timestamp);
~~~

Dùng khi cần timestamp dạng số tương thích với hệ thống cũ hoặc API nhận epoch milliseconds.

Không ưu tiên currentTimeMillis để đo thời lượng rất ngắn vì:

- Độ phân giải có thể thấp hơn nanosecond.
- Đồng hồ hệ thống có thể được điều chỉnh.
- Hai lần đọc liên tiếp có thể trả về cùng giá trị.
- Clock correction có thể khiến hiệu không phản ánh elapsed time thực.

### Instant.now()

Instant biểu diễn một thời điểm trên timeline UTC. Nó phù hợp với timestamp có kiểu dữ liệu rõ ràng hơn long.

~~~java
Instant startedAt = Instant.now();

// Thực hiện công việc

Instant finishedAt = Instant.now();
Duration elapsed = Duration.between(startedAt, finishedAt);

System.out.println("Started: " + startedAt);
System.out.println("Elapsed: " + elapsed);
~~~

Instant.now() vẫn lấy wall-clock time từ clock của hệ thống. Nó phù hợp để ghi thời điểm, nhưng không phải lựa chọn tốt nhất cho đo elapsed time cần tính đơn điệu.

### Khi nào dùng Clock?

Nếu code nghiệp vụ cần biết thời điểm hiện tại, hãy cân nhắc inject java.time.Clock thay vì gọi Instant.now() trực tiếp ở nhiều nơi. Trong test có thể dùng Clock.fixed() để kiểm soát thời gian.

~~~java
Clock testClock = Clock.fixed(
        Instant.parse("2026-01-01T00:00:00Z"),
        ZoneOffset.UTC
);

Instant now = Instant.now(testClock);
~~~

Clock.fixed giúp test logic dựa trên ngày giờ có kết quả lặp lại. Nó không thay thế nanoTime cho benchmark.

## 4. Chuyển đổi đơn vị thời gian

nanoTime trả về nanoseconds. Các đơn vị thường gặp:

| Đơn vị | Quy đổi |
|---|---:|
| 1 microsecond (µs) | 1.000 ns |
| 1 millisecond (ms) | 1.000.000 ns |
| 1 second (s) | 1.000.000.000 ns |

Có thể đổi đơn vị bằng phép chia:

~~~java
long elapsedNanos = 1_234_567;

double elapsedMicros = elapsedNanos / 1_000.0;
double elapsedMillis = elapsedNanos / 1_000_000.0;
double elapsedSeconds = elapsedNanos / 1_000_000_000.0;
~~~

Kết quả minh họa:

- 1.234567 ms
- 1234.567 µs
- 0.001234567 s

Dùng số thực khi cần giữ phần lẻ. Nếu chia hai số nguyên, phần thập phân sẽ bị bỏ.

### Dùng TimeUnit

~~~java
long elapsedNanos = 1_234_567;

long millis = TimeUnit.NANOSECONDS.toMillis(elapsedNanos);
long micros = TimeUnit.NANOSECONDS.toMicros(elapsedNanos);
~~~

Các phép đổi sang đơn vị lớn hơn trả về số nguyên và cắt phần lẻ. Nếu cần hiển thị chính xác đến microsecond hoặc phần lẻ millisecond, hãy dùng double hoặc BigDecimal theo yêu cầu báo cáo.

### Dùng Duration

Duration biểu diễn một khoảng thời gian:

~~~java
Duration duration = Duration.ofNanos(elapsedNanos);

System.out.println(duration.toNanos());
System.out.println(duration.toMillis());
System.out.println(duration.toSeconds());
~~~

toMillis() và toSeconds() trả về số nguyên nên cắt phần lẻ. Duration.toNanos() có thể ném ArithmeticException nếu giá trị vượt phạm vi long nanoseconds.

Không nhân elapsed với một hằng số lớn một cách tùy tiện nếu có thể gây tràn long. Trước hết hãy tính hiệu nanoTime, sau đó chuyển đổi bằng đơn vị phù hợp.

## 5. Đo một đoạn code đúng cách

Một phép đo cơ bản cần đặt start ngay trước vùng cần đo và end ngay sau khi vùng đó hoàn tất.

~~~java
long start = System.nanoTime();

Result result = service.calculate(input);

long elapsed = System.nanoTime() - start;

System.out.printf(
        Locale.ROOT,
        "calculate took %.3f ms%n",
        elapsed / 1_000_000.0
);
~~~

Một số nguyên tắc:

- Đặt timer quanh đúng vùng cần đo.
- Không đưa log, format string hoặc output console vào vùng đo nếu chúng không thuộc công việc cần đo.
- Nếu cần đo end-to-end, bao gồm toàn bộ bước cần đánh giá.
- Nếu cần đo riêng một method, không vô tình tính cả setup hoặc teardown.
- Dùng cùng một cách đo khi so sánh trước và sau tối ưu.
- Không kết luận từ một lần chạy.

### Đo cả khi method ném exception

Nếu cần ghi duration kể cả khi tác vụ thất bại, dùng finally:

~~~java
long start = System.nanoTime();

try {
    service.process();
} finally {
    long elapsed = System.nanoTime() - start;
    metrics.recordDuration(elapsed);
}
~~~

Nếu process() ném exception, finally vẫn chạy và duration được ghi nhận. Hãy bảo đảm metrics.recordDuration() không che mất exception gốc; trong hệ thống thực tế nên dùng cơ chế ghi metric an toàn.

### Đừng đo quá nhiều thứ cùng lúc

Nếu mục tiêu là đo database call, không nên vô tình tính cả JSON serialization, HTTP response rendering và logging. Ngược lại, nếu mục tiêu là user-perceived request latency, phải đo cả pipeline cần thiết.

Đặt ranh giới đo theo câu hỏi cần trả lời.

## 6. Ví dụ Java 17+: đo thời gian chạy bằng nanoTime

Chương trình sau warm-up method tính tổng trước, sau đó đo trung bình của năm lần chạy. Kết quả checksum được sử dụng sau phép đo để tránh việc kết quả bị bỏ đi.

Tạo file **ExecutionTimeDemo.java**:

~~~java
import java.util.Locale;

public final class ExecutionTimeDemo {
    private static volatile long warmupSink;

    private static long sumUpTo(int limit) {
        long sum = 0;
        for (int i = 0; i < limit; i++) {
            sum += i;
        }
        return sum;
    }

    public static void main(String[] args) {
        final int limit = 1_000_000;
        final int warmupIterations = 20;
        final int measuredIterations = 5;

        for (int i = 0; i < warmupIterations; i++) {
            warmupSink = sumUpTo(limit);
        }

        long start = System.nanoTime();
        long checksum = 0;

        for (int i = 0; i < measuredIterations; i++) {
            checksum += sumUpTo(limit);
        }

        long elapsedNanos = System.nanoTime() - start;
        double averageMillis =
                elapsedNanos / 1_000_000.0 / measuredIterations;

        System.out.println("Checksum: " + checksum);
        System.out.printf(
                Locale.ROOT,
                "Average: %.3f ms/op%n",
                averageMillis
        );
    }
}
~~~

Biên dịch:

~~~bash
javac --release 17 ExecutionTimeDemo.java
~~~

Chạy:

~~~bash
java ExecutionTimeDemo
~~~

Dòng checksum có giá trị xác định:

~~~text
Checksum: 2499997500000
~~~

Dòng thời gian có dạng:

~~~text
Average: <giá trị thay đổi> ms/op
~~~

Giá trị thời gian thay đổi theo CPU, JDK, hệ điều hành, tải máy và trạng thái JIT/GC. Đây là ví dụ học cách đặt timer, không phải benchmark đáng tin cậy để so sánh hai thuật toán.

## 7. Đo thời gian bất đồng bộ

Một lỗi phổ biến là chỉ đo thời gian gọi method trả về CompletableFuture. Method có thể trả về rất nhanh trong khi công việc thực tế vẫn đang chạy.

Ví dụ chưa đúng mục tiêu end-to-end:

~~~java
long start = System.nanoTime();
CompletableFuture<Result> future = service.calculateAsync(input);
long elapsed = System.nanoTime() - start;
~~~

Đoạn trên chỉ đo thời gian tạo hoặc trả về future.

Để đo đến khi future hoàn tất:

~~~java
long start = System.nanoTime();

CompletableFuture<Result> future =
        service.calculateAsync(input);

future.whenComplete((result, error) -> {
    long elapsed = System.nanoTime() - start;

    if (error != null) {
        System.err.println("Task failed after " + elapsed + " ns");
    } else {
        System.out.println("Task completed after " + elapsed + " ns");
    }
});
~~~

Đoạn này ghi elapsed time từ lúc gọi async method đến khi completion callback được thực thi. Thời gian callback được scheduler chạy cũng có thể góp vào kết quả; nếu cần latency chính xác theo semantics của service, hãy xác định rõ mốc bắt đầu và kết thúc nghiệp vụ.

### Đo một nhóm tác vụ concurrent

Nếu muốn đo tổng wall-clock time để tất cả tác vụ hoàn thành, đặt timer trước khi submit và dừng sau khi allOf hoàn tất:

~~~java
long start = System.nanoTime();

CompletableFuture<Void> all =
        CompletableFuture.allOf(task1, task2, task3);

all.join();

long elapsed = System.nanoTime() - start;
System.out.println("All tasks elapsed: " + elapsed + " ns");
~~~

Đây là elapsed time của cả nhóm tác vụ. Không cộng duration của từng task để thay thế thời gian tổng vì các task có thể chạy song song.

Nếu cần latency riêng của từng task, đo riêng mỗi task và gắn kết quả với task ID.

## 8. Đo CPU time của một thread

Elapsed time bao gồm cả lúc thread chờ. Nếu muốn biết thread thực sự dùng CPU bao lâu, dùng ThreadMXBean.

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadMXBean;

ThreadMXBean bean =
        ManagementFactory.getThreadMXBean();

if (bean.isCurrentThreadCpuTimeSupported()) {
    if (!bean.isThreadCpuTimeEnabled()) {
        bean.setThreadCpuTimeEnabled(true);
    }

    long cpuStart = bean.getCurrentThreadCpuTime();

    performTask();

    long cpuElapsed =
            bean.getCurrentThreadCpuTime() - cpuStart;

    System.out.println("Thread CPU ns: " + cpuElapsed);
}
~~~

Các lưu ý:

- CPU time chỉ được hỗ trợ nếu JVM và nền tảng cho phép.
- Việc bật thread CPU time có thể cần quyền quản lý phù hợp.
- Giá trị có thể không khả dụng trên một số JVM.
- CPU time của một thread không bằng CPU time của toàn process.
- CPU time không bao gồm thời gian chờ I/O hoặc lock.

Ví dụ, nếu một tác vụ mất 1 giây elapsed nhưng chỉ dùng 50 ms CPU, phần lớn thời gian có thể là waiting. Nếu elapsed và CPU time gần nhau trên một thread, tác vụ có thể thiên về CPU-bound.

## 9. Vì sao đo một lần thường không đáng tin?

JVM là runtime động. Kết quả của lần chạy đầu tiên có thể khác nhiều lần chạy sau.

### Class loading và initialization

Lần đầu sử dụng class có thể phải load, verify, link và initialize class. Nếu chỉ đo lần đầu, kết quả có thể bao gồm startup overhead mà các lần sau không có.

### JIT compilation

HotSpot bắt đầu thực thi bytecode bằng interpreter hoặc code chưa được tối ưu. Khi method trở nên hot, JIT compiler có thể biên dịch thành native code và áp dụng inlining, escape analysis, loop optimization cùng các kỹ thuật khác.

Do đó, method có thể chạy nhanh hơn sau warm-up.

### Garbage collection

Allocation trong vùng đo có thể kích hoạt GC. Một phép đo bị dừng bởi GC có thể dài hơn đáng kể. Ngược lại, lần đo sau có thể không gặp GC và cho kết quả khác.

Không nên xóa toàn bộ GC impact khỏi benchmark nếu allocation là một phần tự nhiên của workload; cần xác định mục tiêu là đo code thuần hay hành vi ứng dụng thực tế.

### OS scheduling và background activity

Thread có thể bị scheduler tạm dừng vì process khác, antivirus, backup, update, CPU throttling hoặc tải hệ thống. Các yếu tố này làm elapsed time thay đổi.

### CPU frequency và thermal throttling

CPU có thể thay đổi xung nhịp theo tải và nhiệt độ. Hai lần chạy trên cùng máy vẫn có thể có hiệu năng khác nhau.

### Dead-code elimination và constant folding

JIT có thể loại bỏ công việc không tạo ra kết quả quan sát được hoặc tính trước biểu thức có giá trị cố định.

Nếu kết quả của method không được sử dụng, benchmark tự viết có thể đo một đoạn code đã bị tối ưu loại bỏ.

## 10. Không dùng vòng lặp nanoTime tự viết để benchmark micro

Một cách làm dễ gặp:

~~~java
long start = System.nanoTime();

for (int i = 0; i < 1_000_000; i++) {
    doWork();
}

long elapsed = System.nanoTime() - start;
System.out.println(elapsed);
~~~

Cách này hữu ích để minh họa elapsed time hoặc đo một batch nghiệp vụ lớn. Nhưng nó không đủ tin cậy cho microbenchmark vì:

- JIT có thể tối ưu toàn bộ vòng lặp.
- Warm-up không được kiểm soát.
- GC và class loading có thể ảnh hưởng kết quả.
- Không có fork độc lập để tách trạng thái JVM.
- Kết quả có thể phụ thuộc thứ tự chạy.
- Không có thống kê sai số hoặc phân bố.
- Việc gọi nanoTime và vòng lặp có thể ảnh hưởng phép đo các method cực ngắn.

Nếu cần so sánh method mất vài nanosecond hoặc microsecond, dùng JMH.

## 11. JMH: công cụ chuẩn cho microbenchmark Java

JMH là Java Microbenchmark Harness, framework chuyên dùng để xây dựng và chạy benchmark Java trên JVM.

JMH xử lý nhiều vấn đề khó khi tự đo:

- Warm-up iterations.
- Measurement iterations.
- Fork JVM process.
- Benchmark state và setup.
- Dead-code elimination.
- Kết quả được tiêu thụ qua return value hoặc Blackhole.
- Nhiều benchmark mode.
- Tổng hợp kết quả và sai số thống kê.

JMH không làm mọi benchmark tự động đúng. Người viết vẫn phải chọn workload đại diện, input hợp lý, state đúng và tránh benchmark sai câu hỏi.

### Các benchmark mode

| Mode | Đo gì? | Khi dùng |
|---|---|---|
| AverageTime | Thời gian trung bình mỗi operation | So sánh latency của method |
| Throughput | Số operation trên đơn vị thời gian | Đánh giá tốc độ xử lý |
| SampleTime | Phân bố thời gian operation theo mẫu | Xem percentile và tail behavior |
| SingleShotTime | Thời gian một lần thực thi | Đo cold/single invocation có kiểm soát |
| All | Chạy nhiều mode | Khảo sát tổng quan, tốn thời gian hơn |

AverageTime thường hiển thị ns/op, µs/op hoặc ms/op tùy OutputTimeUnit. Throughput thường hiển thị ops/s. Với AverageTime, giá trị thấp hơn thường tốt hơn; với Throughput, giá trị cao hơn thường tốt hơn.

## 12. Tạo benchmark JMH với Java 17+

Ví dụ dưới đây so sánh vòng lặp for với Stream để tính tổng cùng một mảng số nguyên.

Cấu trúc thư mục:

~~~text
timing-benchmarks/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── org/
                └── example/
                    └── SumBenchmark.java
~~~

### pom.xml

Dùng JMH 1.37, Maven Compiler Plugin và Shade Plugin để tạo executable benchmark JAR.

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>org.example</groupId>
    <artifactId>timing-benchmarks</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.openjdk.jmh</groupId>
            <artifactId>jmh-core</artifactId>
            <version>1.37</version>
        </dependency>
        <dependency>
            <groupId>org.openjdk.jmh</groupId>
            <artifactId>jmh-generator-annprocess</artifactId>
            <version>1.37</version>
            <scope>provided</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                    <annotationProcessorPaths>
                        <path>
                            <groupId>org.openjdk.jmh</groupId>
                            <artifactId>jmh-generator-annprocess</artifactId>
                            <version>1.37</version>
                        </path>
                    </annotationProcessorPaths>
                </configuration>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-shade-plugin</artifactId>
                <version>3.5.3</version>
                <executions>
                    <execution>
                        <phase>package</phase>
                        <goals>
                            <goal>shade</goal>
                        </goals>
                        <configuration>
                            <finalName>benchmarks</finalName>
                            <transformers>
                                <transformer implementation="org.apache.maven.plugins.shade.resource.ManifestResourceTransformer">
                                    <mainClass>org.openjdk.jmh.Main</mainClass>
                                </transformer>
                            </transformers>
                        </configuration>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### SumBenchmark.java

~~~java
package org.example;

import java.util.Arrays;
import java.util.concurrent.TimeUnit;

import org.openjdk.jmh.annotations.*;

@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.MICROSECONDS)
@Warmup(iterations = 5, time = 1)
@Measurement(iterations = 5, time = 1)
@Fork(2)
public class SumBenchmark {
    @Param({"1000", "100000"})
    public int size;

    private int[] values;

    @Setup(Level.Trial)
    public void setup() {
        values = new int[size];

        for (int i = 0; i < values.length; i++) {
            values[i] = i % 100;
        }
    }

    @Benchmark
    public long sumWithLoop() {
        long sum = 0;

        for (int value : values) {
            sum += value;
        }

        return sum;
    }

    @Benchmark
    public long sumWithStream() {
        return Arrays.stream(values)
                .asLongStream()
                .sum();
    }
}
~~~

### Chạy benchmark

Từ thư mục timing-benchmarks:

~~~bash
mvn clean package
java -jar target/benchmarks.jar SumBenchmark
~~~

Có thể chỉ định rõ số warm-up, measurement và fork từ command line:

~~~bash
java -jar target/benchmarks.jar SumBenchmark -wi 5 -i 5 -f 2
~~~

Trong ví dụ:

- -wi 5: 5 warm-up iterations.
- -i 5: 5 measurement iterations.
- -f 2: chạy 2 fork JVM độc lập.

Các annotation trong class cũng đặt cấu hình tương ứng. Tham số command line cho phép thay đổi khi cần thử nghiệm.

### Đọc kết quả JMH

JMH sẽ in bảng kết quả với benchmark name, mode, count, score, error và unit. Ví dụ minh họa:

~~~text
Benchmark                  Mode  Cnt   Score   Error  Units
SumBenchmark.sumWithLoop   avgt   10   12.5 ± 0.4  us/op
SumBenchmark.sumWithStream avgt   10   18.2 ± 0.7  us/op
~~~

Các số trên chỉ minh họa định dạng. Kết quả thực tế phụ thuộc máy, JDK, workload và cấu hình.

Đừng chỉ nhìn Score. Xem cả Error, số fork, input size, JVM version và điều kiện chạy. Chạy nhiều lần và kiểm tra kết quả có ổn định không.

## 13. Các nguyên tắc thiết kế benchmark đáng tin cậy

### Warm-up đủ trước khi đo

Warm-up giúp JVM load class, chạy interpreter, thu thập profiling information và biên dịch method nóng bằng JIT. Nếu đo ngay từ lần đầu, benchmark có thể phản ánh startup thay vì steady-state performance.

### Dùng fork độc lập

Fork tạo JVM process mới cho lần benchmark. Điều này giúp giảm ảnh hưởng từ trạng thái JIT, heap và benchmark trước đó. Nhiều fork giúp đánh giá độ ổn định tốt hơn.

### Chuẩn bị input ngoài vùng đo

Dùng @Setup để tạo array, object hoặc fixture trước measurement nếu mục tiêu không phải đo chi phí setup. Nếu setup là một phần nghiệp vụ cần đánh giá, hãy đưa nó vào benchmark một cách có chủ đích.

### Bảo đảm kết quả được sử dụng

Nếu kết quả không được quan sát, JIT có thể loại bỏ computation. JMH xử lý bằng cách tiêu thụ return value hoặc sử dụng Blackhole:

~~~java
@Benchmark
public void calculate(Blackhole blackhole) {
    long result = expensiveCalculation();
    blackhole.consume(result);
}
~~~

Không dùng Blackhole một cách máy móc nếu benchmark method có thể trả về kết quả; return value thường đơn giản hơn.

### Không benchmark hằng số hoặc dữ liệu quá đơn giản

Nếu input luôn giống nhau và compiler có thể tính trước kết quả, benchmark không phản ánh workload thật. Dùng @Param hoặc state được chuẩn bị hợp lý để kiểm soát input.

### Tránh benchmark nhiều việc không liên quan

Không trộn network, file I/O, logging, random generation và thuật toán vào một benchmark nếu câu hỏi chỉ là so sánh hai implementation của thuật toán.

Nếu muốn đo end-to-end, hãy đo toàn bộ workload như một integration/load test riêng.

### Chạy trong môi trường ổn định

- Dùng cùng JDK vendor/version và JVM flags.
- Đóng tác vụ nền không cần thiết.
- Dùng input và dataset tương đương.
- Ghi nhận CPU, RAM, OS, container limit và power profile.
- Tránh chạy hai benchmark cạnh tranh CPU cùng lúc.
- Không chọn kết quả tốt nhất trong nhiều lần chạy mà bỏ qua các lần còn lại.

## 14. Đo thời gian chạy hay đo hiệu năng toàn hệ thống?

Một method nhanh hơn không nhất thiết làm toàn bộ service nhanh hơn. Có thể bottleneck nằm ở database, network, queue, lock hoặc GC.

Chọn cấp độ đo:

| Cấp độ | Mục tiêu | Công cụ phù hợp |
|---|---|---|
| Một vùng code | Elapsed time thực tế | System.nanoTime() |
| Microbenchmark | So sánh method/algorithm nhỏ | JMH |
| Một request | End-to-end latency | Application timing, tracing |
| Nhiều request đồng thời | Throughput, p95/p99, error rate | Load testing và metrics |
| Phân tích nguyên nhân CPU/I/O | Method samples, event, stack trace | JFR/JMC |
| CPU time của thread | Thời gian thread thực sự chạy CPU | ThreadMXBean |

Không dùng microbenchmark để thay thế load test của service. Không dùng JFR event count làm phép đo latency end-to-end.

## 15. Kết hợp JFR để tìm nguyên nhân chậm

JMH cho biết implementation nào nhanh hơn trong benchmark. JFR giúp điều tra vì sao ứng dụng thực tế chậm.

Bắt đầu recording ngắn cho JVM đang chạy:

~~~bash
jcmd <pid> JFR.start name=runtime-check settings=profile duration=30s filename=runtime-check.jfr
~~~

Xem summary:

~~~bash
jfr summary runtime-check.jfr
~~~

Mở file bằng JDK Mission Control để kiểm tra:

- CPU hot methods.
- Execution samples và thread CPU load.
- Garbage collection.
- File/socket I/O events.
- Lock contention.
- Allocation và object statistics.

Profile settings thu thập nhiều dữ liệu hơn default và có overhead cao hơn. Dùng trong thời gian ngắn, với workload đại diện và theo dõi tác động.

## 16. Lỗi thường gặp khi đo thời gian

### Dùng currentTimeMillis cho method rất nhanh

Độ phân giải có thể không đủ và clock có thể bị điều chỉnh. Dùng nanoTime để đo elapsed time.

### Lấy nanoTime làm timestamp

Origin của nanoTime tùy ý. Không lưu giá trị này làm thời điểm lịch hoặc so sánh giữa các máy.

### Quên lấy hiệu end - start

Chỉ hiệu hai lần đọc nanoTime mới biểu diễn elapsed time. Không so sánh trực tiếp giá trị tuyệt đối.

### Chỉ đo một lần

Kết quả bị ảnh hưởng bởi JIT, class loading, GC và OS scheduling. Dùng warm-up, nhiều iteration và JMH khi cần benchmark.

### Chia số nguyên rồi mất phần lẻ

elapsedNanos / 1_000_000 là phép chia số nguyên nếu cả hai toán hạng là integer. Dùng 1_000_000.0 để giữ phần thập phân.

### Đo async method nhưng dừng timer quá sớm

Nếu method trả CompletableFuture, phải đo đến lúc future hoàn tất nếu mục tiêu là thời gian tác vụ. Đo quanh lời gọi chỉ cho biết thời gian submit.

### Kết quả bị tối ưu loại bỏ

Nếu kết quả không được dùng, JIT có thể loại bỏ computation. Trả về kết quả, dùng checksum hoặc JMH Blackhole.

### So sánh hai implementation bằng hai môi trường khác nhau

JDK, CPU, JVM flags, heap, input và tải nền có thể làm kết quả lệch. So sánh trong cùng điều kiện và nhiều fork.

### Dùng Thread.sleep để tạo thời gian đo

sleep chỉ yêu cầu thread tạm dừng ít nhất một khoảng thời gian; scheduler có thể đánh thức muộn hơn. Nó không phải bộ đo thời gian chính xác.

## 17. Quy trình đo và tối ưu có thể lặp lại

1. Xác định câu hỏi: elapsed time, CPU time, method latency hay service throughput.
2. Chọn đồng hồ phù hợp: nanoTime, Instant/currentTimeMillis hoặc ThreadMXBean.
3. Xác định chính xác ranh giới vùng đo.
4. Dùng input và workload đại diện.
5. Tách setup, warm-up và measurement khi cần.
6. Nếu là microbenchmark, viết JMH benchmark thay vì vòng lặp nanoTime tự chế.
7. Chạy nhiều warm-up, measurement iterations và forks.
8. Lưu JDK version, JVM flags, hardware, OS và benchmark parameters.
9. Kiểm tra sai số, độ ổn định và phân bố kết quả.
10. Dùng JFR hoặc profiler để tìm nguyên nhân khi có chênh lệch.
11. Tối ưu một yếu tố chính mỗi lần.
12. Chạy lại cùng workload để xác nhận cải thiện và tránh regression.

## 18. Checklist đo thời gian chạy

- Dùng nanoTime cho elapsed time.
- Dùng Instant/currentTimeMillis cho timestamp theo lịch.
- Dùng ThreadMXBean khi cần CPU time của thread.
- Luôn tính end - start.
- Không so sánh hoặc lưu nanoTime như timestamp toàn cục.
- Nhớ nanosecond precision không đồng nghĩa nanosecond resolution.
- Chuyển đổi đơn vị bằng double nếu cần phần lẻ.
- Đo đúng ranh giới nghiệp vụ.
- Đo đến completion của async task nếu cần end-to-end duration.
- Không dùng một lần chạy làm benchmark.
- Tránh dead-code elimination và constant folding.
- Dùng JMH cho microbenchmark.
- Có warm-up, measurement iterations và fork.
- Dùng workload đại diện và cùng môi trường khi so sánh.
- Dùng JFR/JMC để chẩn đoán nguyên nhân, không thay thế benchmark.
- Ghi nhận error, units, JDK, flags và cấu hình chạy.

## 19. Thuật ngữ cần nhớ

| Thuật ngữ | Ý nghĩa |
|---|---|
| Wall-clock time | Thời điểm theo lịch |
| Elapsed time | Thời gian thực tế trôi qua giữa hai mốc |
| CPU time | Thời gian CPU thực sự dành cho thread/process |
| System.nanoTime() | API đo elapsed time độ phân giải cao |
| System.currentTimeMillis() | Timestamp milliseconds từ Unix epoch |
| Instant | Một thời điểm trên timeline UTC |
| Duration | Khoảng thời gian giữa hai mốc |
| Clock | Abstraction cung cấp wall-clock time, có thể inject vào code |
| Warm-up | Giai đoạn để JVM nạp class và tối ưu JIT |
| JIT | Just-In-Time compiler |
| Dead-code elimination | Tối ưu loại bỏ computation không tạo kết quả quan sát được |
| Constant folding | Tính trước biểu thức có giá trị xác định |
| Fork | Chạy benchmark trong JVM process độc lập |
| Iteration | Một chu kỳ warm-up hoặc measurement |
| JMH | Java Microbenchmark Harness |
| Blackhole | Cơ chế tiêu thụ kết quả để tránh computation bị loại bỏ |
| Throughput | Số operation hoàn thành trên đơn vị thời gian |
| Latency | Thời gian hoàn thành một operation/request |
| Percentile | Phân vị như p50, p95 hoặc p99 |
| JFR | Java Flight Recorder dùng ghi runtime events |

Đo thời gian chạy đúng bắt đầu từ việc chọn đúng đại lượng. Dùng nanoTime cho elapsed time, wall-clock API cho timestamp và ThreadMXBean cho CPU time của thread. Với method rất nhỏ, hãy dùng JMH để kiểm soát warm-up, JIT và sai số; với ứng dụng thực tế, kết hợp benchmark, JFR và metrics để hiểu cả hiệu năng lẫn nguyên nhân.

## Tài liệu tham khảo

- Oracle Java SE 24 API — System.nanoTime(): https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/System.html#nanoTime()
- Oracle Java SE 24 API — System.currentTimeMillis(): https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/System.html#currentTimeMillis()
- Oracle Java SE 24 API — Instant: https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/time/Instant.html
- Oracle Java SE 24 API — Duration: https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/time/Duration.html
- Oracle Java SE 24 API — ThreadMXBean: https://docs.oracle.com/en/java/javase/24/docs/api/java.management/java/lang/management/ThreadMXBean.html
- OpenJDK — Java Microbenchmark Harness (JMH): https://github.com/openjdk/jmh
- Oracle JDK 24 — Java Flight Recorder: https://docs.oracle.com/en/java/javase/24/jfapi/flight-recorder-api-programmers-guide.pdf
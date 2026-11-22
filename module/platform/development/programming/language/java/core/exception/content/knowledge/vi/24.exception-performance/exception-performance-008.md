# Đo bằng benchmark có tình huống lỗi và tần suất thực tế

Khi tối ưu xử lý exception trong Java, một kết quả kiểu “ném exception mất X ns” có thể đúng trong một phép thử rất hẹp nhưng **không phản ánh hiệu năng ứng dụng thật**. Hệ thống thực có những request thành công, những lỗi hiếm, các đợt lỗi dồn dập khi dependency gặp sự cố, đường xử lý khác nhau và chi phí log/cleanup. Nếu benchmark luôn ném lỗi ở 100% vòng lặp, bạn đang đo một workload không giống production; nếu benchmark không có lỗi, bạn cũng không biết ứng dụng sẽ chịu tải thế nào khi error burst.

Một benchmark tốt phải trả lời trước: **đo phần nào của quá trình xử lý lỗi, với phân phối tình huống và tần suất nào, trên JVM/hệ thống nào, bằng metric nào?** Chỉ sau khi xác định workload và bảo đảm tính đúng đắn của code mới có ý nghĩa để so sánh tốc độ.

Bài này thuộc mục **Hiệu năng** của Java core – exception. Trọng tâm là thiết kế phép đo có cả nhánh thành công và nhánh thất bại, không nhầm tỷ lệ lỗi với tỷ lệ CPU, sử dụng Java Microbenchmark Harness (JMH) khi cần microbenchmark, và kiểm chứng bằng profiling/load test trong ngữ cảnh thực tế. Mã ví dụ tương thích Java 17 trở lên.

## 1. Benchmark exception cần mô hình hóa điều gì?

Một lời gọi có thể trải qua:

```text
Nhận request / record
         |
         v
Kiểm tra điều kiện
     /           \
 Thành công     Thất bại
     |              |
 Tính toán      Tạo exception
     |              |
 Trả kết quả    throw/unwind
                    |
                    v
              catch hoặc boundary
                    |
                    v
            ghi log / metric / cleanup
                    |
                    v
             trả kết quả lỗi
```

Không phải tất cả nhánh thất bại đều có cùng chi phí. Một `IllegalArgumentException` được ném và bắt ngay trong phương thức sẽ khác `IOException` phát sinh sau một lần gọi mạng, đi qua nhiều tầng và có log stack trace. Vì vậy cần chọn rõ **đơn vị công việc** thay vì gọi chung mọi điều đó là “overhead của exception”.

Các yếu tố nên nêu trong định nghĩa benchmark:

| Yếu tố | Câu hỏi cần trả lời | Vì sao quan trọng |
| --- | --- | --- |
| Mục tiêu | Đo cấp phát, throughput, latency hay p99? | Mỗi metric trả lời vấn đề khác nhau. |
| Đường thành công | Việc gì diễn ra khi không lỗi? | Phần lớn lưu lượng có thể nằm ở nhánh này. |
| Đường thất bại | Exception nào, được tạo ở đâu, catch ở đâu? | Constructor/backtrace, throw và cleanup khác nhau. |
| Tần suất | 0%, 0,1%, 1%, 10%, 50%, 100% hay phân phối khác? | Giá thành trung bình thay đổi rất mạnh theo tỷ lệ lỗi. |
| Phân bố thời gian | Lỗi rải đều hay dồn thành burst? | Burst tạo áp lực log, GC và hàng đợi. |
| Logging | Tắt, bật, đồng bộ, bất đồng bộ hay sampling? | I/O/formatting có thể lấn át throw/catch. |
| Độ sâu call stack | Throw tại chỗ hay qua nhiều phương thức? | Stack capture/unwind và finally thay đổi. |
| Môi trường | JDK, GC, CPU, memory, log destination? | Không thể chuyển mọi con số giữa các máy. |
| Dữ liệu | Request đơn giản hay payload lớn, cache nóng/lạnh? | Có thể đo nhầm parsing/I/O thay vì exception. |

**Không có một tỷ lệ lỗi chuẩn chung cho mọi dịch vụ.** Một API người dùng có 0,1% lỗi trong giờ bình thường; một parser batch có 20% dữ liệu sai; một dịch vụ phụ thuộc hạ tầng có thể có 70% lỗi trong vài phút. Những tỷ lệ dưới đây đều là **kịch bản giả định để thiết kế phép thử**, không phải số liệu thống kê của một ứng dụng cụ thể.

## 2. Phân biệt chi phí từng pha với chi phí toàn đường lỗi

Một phép đo thực tế của `throw new IllegalStateException(...)` thường đã bao gồm **constructor, cấp phát, backtrace, throw/unwind và catch**. Nếu handler còn ghi log, kết quả còn có chi phí format/ghi bản ghi. Muốn tối ưu đúng nơi, cần chia nhóm benchmark:

1. **Successful path** – chạy phần bình thường, có thể có `try/catch` nhưng không ném.
2. **Create-only** – tạo đối tượng `Throwable` nhưng không `throw`; mục đích đánh giá riêng constructor/stack capture khi có thể.
3. **Throw pre-created** – ném một exception đã tạo; giúp tách tương đối phần throw/catch nhưng không còn stack trace tại vị trí lỗi mới và không mô phỏng đường production phổ biến.
4. **Throw new and catch** – đo đường lỗi quen thuộc gồm tạo, ném và bắt.
5. **Throw across frames** – ném ở tầng dưới, unwind qua một hay nhiều frame và `finally`/`try-with-resources`.
6. **Catch and handle** – logic phân loại, chuyển lỗi, trả fallback, cập nhật counter.
7. **Catch and log** – bổ sung render stack, formatting, appender, queue và flush theo cấu hình.
8. **End-to-end request** – validation, xử lý chính, persistence/network, error mapping, logging và response.

Khi báo cáo, ghi rõ phép đo thuộc nhóm nào. Không được lấy benchmark “throw new + catch + log” rồi kết luận **riêng** opcode `throw` chậm bằng toàn bộ thời gian đó.

### Cách nhìn về chi phí trung bình

Nếu chỉ có hai đường thành công/thất bại và bỏ qua tương tác hệ thống, độ trễ trung bình có thể được **ước lượng**:

\[
E[T] \approx (1-p)\,E[T\mid success] + p\,E[T\mid failure]
\]

Trong đó `p` là tỷ lệ lỗi thực tế, không phải con số tùy ý dùng trong vòng lặp benchmark. Ví dụ **minh họa bằng giả định**: success mất 1 đơn vị, failure mất 101 đơn vị; với `p = 0.01`, chi phí trung bình theo mô hình là `0.99·1 + 0.01·101 = 2` đơn vị. Điều này không có nghĩa CPU, p99 hay throughput thực tế tăng đúng hai lần, vì còn concurrency, scheduling, I/O, GC, logging và tải hệ thống.

Cách tính trung bình không mô tả được **tail latency** hay tình huống nhiều lỗi xảy ra đồng thời. Phép đo phải bổ sung latency distribution và workload burst khi những điều đó quan trọng.

## 3. Xác định tỷ lệ lỗi dựa trên production

Trước khi chạy benchmark, hãy xác định tần suất lỗi cho từng loại workload:

- **Theo request:** số request thất bại / tổng request trong cùng cửa sổ.
- **Theo record:** số record lỗi / tổng record xử lý; có thể khác tỷ lệ request vì một request chứa nhiều record.
- **Theo thao tác phụ thuộc:** số lần query/HTTP attempt lỗi / tổng số attempt; nếu một request retry nhiều lần, tỷ lệ attempt có thể khác tỷ lệ request cuối cùng bị lỗi.
- **Theo loại lỗi:** validation, data not found, timeout, connection reset, resource exhaustion, bug nội bộ… Không gộp tất cả thành một exception duy nhất.
- **Theo khoảng thời gian:** tỷ lệ 1 phút và tỷ lệ 1 giờ có thể khác nhau rất lớn; trung bình cả ngày có thể giấu một incident nghiêm trọng.

Nếu chưa có dữ liệu thật, hãy **nêu rõ giả định** và thử một ma trận có giá trị học tập, ví dụ:

| Kịch bản giả định | Tỷ lệ lỗi | Dùng để kiểm tra |
| --- | ---: | --- |
| Healthy | 0% | Baseline đường thành công. |
| Mostly healthy | 0,1% | Lỗi hiếm, chi phí exception được pha loãng. |
| Normal mixed | 1% | Mix ít lỗi để quan sát overhead khi lệch từ 0%. |
| Degraded | 10% | Thay đổi phân phối latency và tần suất log. |
| High rejection/bad batch | 50% | Workload mà lỗi là trạng thái rất thường xuyên. |
| Incident | 100% trong cửa sổ ngắn | Khả năng chịu burst, GC/logging/circuit breaker. |

Các tỷ lệ này là **mốc khảo sát**, không phải mục tiêu SLA và không có nghĩa “50% lỗi” là bình thường. Sau khi lấy metrics, thay ma trận giả định bằng phân phối của dịch vụ thật.

Cần phân biệt **tần suất exception được ném** với **tần suất request thất bại**. Một request có thể ném và bắt nhiều exception bên trong rồi vẫn hoàn thành thành công. Trong retry, một request có thể tạo 3 exception I/O trước khi lần thử thứ tư thành công. Phép đo theo request và phép đo theo exception event trả lời hai câu hỏi khác nhau.

## 4. Dữ liệu thực tế: phân phối lỗi và sự tương quan

Một benchmark ngẫu nhiên có 1% lỗi rải đều không tương đương workload 1% lỗi nhưng tất cả dồn vào một phút. Cả hai có cùng tỷ lệ tổng thể nhưng khác đặc điểm hệ thống:

**Lỗi rải đều:**

```text
S S S S E S S S S S S S S E S S S S S ...
```

**Lỗi dồn thành đợt:**

```text
S S S S S S S S E E E E E E E E S S ...
```

Ở đây `S` là thành công và `E` là lỗi. Burst có thể khiến nhiều request cùng ghi stack trace, làm đầy queue log, tăng allocation rate, gây GC và kéo dài p99. Cũng có thể nhiều thread cùng retry vào một dependency hỏng, dẫn đến tải tăng và incident kéo dài.

Các chiều workload hữu ích:

- **Phân phối thời gian:** rải đều, burst, theo chu kỳ, lỗi tương quan theo host hoặc shard.
- **Kích thước input:** bản ghi nhỏ/lớn, loại payload, độ sâu parse.
- **Loại lỗi:** validation giá rẻ khác I/O/network timeout hoặc exception khi cleanup.
- **Độ sâu stack:** catch gần nơi throw hay ở boundary trên cùng.
- **Tỷ lệ log:** 0%, tất cả, sampled; sync vs async.
- **Số worker:** 1 thread, số thread theo CPU, pool chịu queue contention.
- **Trạng thái hạ tầng:** cache hit/miss, dependency healthy/unavailable, disk/network throughput.

Muốn benchmark đo hiệu ứng của **tần suất** thì thay đổi một biến độc lập tại mỗi thí nghiệm, giữ các yếu tố khác ổn định. Nếu vừa thay tỷ lệ lỗi, vừa thay logger và số thread rồi quan sát throughput khác nhau, không thể quy nguyên nhân cho exception.

## 5. Ví dụ Java 17: tạo workload có tỷ lệ lỗi xác định

Bài trước tiên cần một chương trình **chạy độc lập**, chứng minh dữ liệu đầu vào thật sự có tỷ lệ lỗi dự kiến. Chương trình sau dựng 10.000 input, đưa giá trị âm vào đúng một phần theo phép hoán vị số học để tạo lỗi rải đều. Đồng thời so sánh với tình huống tất cả lỗi nằm ở đầu batch (*burst*). Kết quả chỉ đếm thành công/thất bại, **không giả vờ là số đo hiệu năng**.

Tạo file `ErrorRateScenarioDemo.java`:

```java
public class ErrorRateScenarioDemo {

    private static final int TOTAL = 10_000;

    private static final class InvalidValueException
            extends RuntimeException {
        InvalidValueException() {
            super("negative input");
        }
    }

    private record Stats(int success, int failures, long checksum) {}

    private static int process(int input) {
        if (input < 0) {
            throw new InvalidValueException();
        }
        return input + 1;
    }

    private static Stats run(int badCount, boolean burst) {
        int success = 0;
        int failures = 0;
        long checksum = 0;

        for (int i = 0; i < TOTAL; i++) {
            // 37 nguyên tố cùng nhau với 10000:
            // (i * 37) % TOTAL đi qua mỗi giá trị 0..9999 một lần.
            int position = burst ? i : (i * 37) % TOTAL;
            int input = position < badCount ? -1 : i;

            try {
                checksum += process(input);
                success++;
            } catch (InvalidValueException ex) {
                failures++;
            }
        }

        return new Stats(success, failures, checksum);
    }

    public static void main(String[] args) {
        int[] badCounts = {0, 10, 100, 1000, 5000, 10000};

        for (int count : badCounts) {
            Stats stats = run(count, false);
            System.out.println(
                "scattered " + count + "/10000"
                    + " success=" + stats.success()
                    + " failure=" + stats.failures()
            );
        }

        Stats burst = run(1000, true);
        System.out.println(
            "burst 1000/10000 success=" + burst.success()
                + " failure=" + burst.failures()
        );
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 ErrorRateScenarioDemo.java
java ErrorRateScenarioDemo
```

Stdout chính xác:

```text
scattered 0/10000 success=10000 failure=0
scattered 10/10000 success=9990 failure=10
scattered 100/10000 success=9900 failure=100
scattered 1000/10000 success=9000 failure=1000
scattered 5000/10000 success=5000 failure=5000
scattered 10000/10000 success=0 failure=10000
burst 1000/10000 success=9000 failure=1000
```

Giải thích:

1. `TOTAL = 10_000` cố định. Do `gcd(37, 10000) = 1`, phép tính `(i * 37) % 10000` hoán vị tất cả các vị trí 0 đến 9999, vì vậy so sánh với `badCount` tạo **đúng** số lỗi cần thiết.
2. Với `badCount = 10`, tỷ lệ lỗi là 0,1%; `100` là 1%; `1000` là 10%; `5000` là 50%.
3. Nhánh `burst = true` chọn `position=i` nên 1000 lỗi đầu tiên nằm liền nhau, nhưng tổng số lỗi bằng trường hợp phân tán.
4. `Stats.checksum` giúp giữ dữ liệu xử lý trong mã; ví dụ không in checksum vì mục đích ở đây là kiểm chứng tỷ lệ.
5. Chương trình **không đo nanosecond, throughput hay p99**. Nó chỉ là bộ tạo tình huống đúng số lượng, có thể chuyển vào test/benchmark thực.
6. Trong benchmark thật, việc chuẩn bị dữ liệu nên tách khỏi vùng đo nếu mục tiêu là chi phí xử lý input, không phải chi phí dựng dataset.

Phép hoán vị đơn giản ở đây **không đại diện phân phối thời gian của production**, và khi thực hiện tuần tự chỉ thay đổi thứ tự lỗi giữa các phần tử. Để đánh giá burst gây queue contention, log backpressure và concurrency, cần workload đa luồng/load test có thời gian đến request được kiểm soát.

## 6. Vì sao không dùng System.nanoTime một lần làm kết luận?

Một ví dụ thường thấy:

```java
long begin = System.nanoTime();

for (int i = 0; i < 1_000_000; i++) {
    try {
        throw new IllegalArgumentException("bad");
    } catch (IllegalArgumentException ignored) {
    }
}

System.out.println(System.nanoTime() - begin);
```

Đây là **đoạn minh họa một phép thử chưa đủ tin cậy**, không phải benchmark chuẩn. Vấn đề gồm:

- Chỉ có **100% lỗi**, không mô tả request thực tế có 0,1% hoặc 1% lỗi.
- Gộp constructor/stack capture, `throw` và `catch` làm một.
- Không có phép thử đối chứng đường thành công với cùng dữ liệu/công việc.
- Một lần chạy có thể chưa warm-up JIT; kết quả trộn startup, class loading và GC.
- JIT có thể tối ưu code khác với dự đoán, đặc biệt khi kết quả không được tiêu thụ một cách có ý nghĩa.
- Thời gian đo tổng vòng lặp không cho biết phân phối latency request hoặc p99.
- Không log, không cleanup, không concurrency, không network, không lỗi dồn theo đợt.
- Thời điểm thread được OS scheduling và tải nền trên máy có thể chi phối biến thiên.

`System.nanoTime()` là API đồng hồ đơn điệu dùng để đo khoảng thời gian tương đối và có ích khi đo đúng cách, nhưng **bản thân API không biến một vòng lặp thành benchmark khoa học**. Không nên quảng bá một số đo duy nhất từ đoạn code trên như thông số hiệu năng của exception Java.

## 7. Dùng JMH cho microbenchmark

**JMH (Java Microbenchmark Harness)** là công cụ của hệ sinh thái OpenJDK để thiết kế microbenchmark có warm-up, measurement iterations, fork JVM, cách tiêu thụ kết quả chống loại bỏ công việc vô ích và công cụ thống kê phù hợp. JMH **không nằm trong thư viện chuẩn của JDK**, nên cần project và dependency JMH thích hợp.

Các thành phần quen thuộc:

| Chú thích/cấu hình | Công dụng |
| --- | --- |
| `@Benchmark` | Đánh dấu phương thức đo. |
| `@State(Scope.Thread)` | Dữ liệu benchmark riêng cho mỗi worker đo, giảm chia sẻ không chủ đích. |
| `@Param(...)` | Chạy từng cấu hình tỷ lệ lỗi/độ sâu stack/logging. |
| `@Setup(Level.Trial)` | Tạo input trước phép đo, tránh trộn chi phí dựng dataset. |
| `@BenchmarkMode(Mode.Throughput)` | Đo số invocation/đơn vị thời gian. |
| `@BenchmarkMode(Mode.AverageTime)` | Đo thời gian trung bình mỗi invocation/operation. |
| `@Warmup` / `@Measurement` | Thiết lập vòng làm nóng và đo. |
| `@Fork` | Chạy benchmark trong các JVM fork độc lập hơn. |
| `@Threads` | Kiểm soát số thread đo; cần hiểu shared state/contention. |
| `Blackhole` | Tiêu thụ dữ liệu mà không để kết quả bị bỏ qua dễ dàng. |
| `@OperationsPerInvocation` | Diễn giải số operations bên trong một invocation khi phù hợp với mục tiêu đo. |

Không cần gắn mọi annotation cùng lúc. Chọn những thông số thể hiện mục tiêu rồi **ghi rõ toàn bộ cấu hình trong báo cáo** để người khác có thể tái lập.

### Mẫu JMH: thay đổi tần suất lỗi có kiểm soát

Mã dưới đây là **lớp JMH thực**, không phải chương trình Java chỉ dùng `javac` trần: nó yêu cầu project đã cài JMH và annotation processor tương ứng. Ví dụ kiểm tra `badPerTenThousand` ở các mức 0%, 0,1%, 1%, 10%, 50%, 100%. Mỗi invocation xử lý một batch 10.000 record, tránh quyết định kiểu dữ liệu đầu vào bằng random bên trong vùng đo.

File `ErrorRateBenchmark.java` (đặt trong package project JMH, điều chỉnh package phù hợp):

```java
import java.util.concurrent.TimeUnit;
import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.BenchmarkMode;
import org.openjdk.jmh.annotations.Fork;
import org.openjdk.jmh.annotations.Level;
import org.openjdk.jmh.annotations.Measurement;
import org.openjdk.jmh.annotations.Mode;
import org.openjdk.jmh.annotations.OperationsPerInvocation;
import org.openjdk.jmh.annotations.OutputTimeUnit;
import org.openjdk.jmh.annotations.Param;
import org.openjdk.jmh.annotations.Scope;
import org.openjdk.jmh.annotations.Setup;
import org.openjdk.jmh.annotations.State;
import org.openjdk.jmh.annotations.Warmup;

@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.NANOSECONDS)
@Warmup(iterations = 3)
@Measurement(iterations = 5)
@Fork(2)
public class ErrorRateBenchmark {

    private static final int TOTAL = 10_000;

    @Param({"0", "10", "100", "1000", "5000", "10000"})
    public int badPerTenThousand;

    private int[] values;

    @Setup(Level.Trial)
    public void prepare() {
        values = new int[TOTAL];
        for (int i = 0; i < TOTAL; i++) {
            int position = (i * 37) % TOTAL;
            values[i] = position < badPerTenThousand ? -1 : i;
        }
    }

    private static int withException(int value) {
        if (value < 0) {
            throw new IllegalArgumentException("negative");
        }
        return value + 1;
    }

    @Benchmark
    @OperationsPerInvocation(TOTAL)
    public long throwAndCatch() {
        long sum = 0;
        for (int value : values) {
            try {
                sum += withException(value);
            } catch (IllegalArgumentException ex) {
                // Đường lỗi được xử lý; không ghi log trong phép đo này.
            }
        }
        return sum;
    }

    @Benchmark
    @OperationsPerInvocation(TOTAL)
    public long conditionalResult() {
        long sum = 0;
        for (int value : values) {
            if (value >= 0) {
                sum += value + 1;
            }
        }
        return sum;
    }
}
```

Cách chuẩn bị project JMH:

1. Tạo project Maven/Gradle hoặc template JMH chính thức theo version phù hợp với JDK đang dùng.
2. Thêm JMH core và annotation processor `jmh-generator-annprocess` theo cấu hình build tool; **không tự chọn một version khác nhau** cho hai module này.
3. Đặt lớp trong source set mà JMH annotation processor xử lý; một số cấu hình/template yêu cầu package có tên thay vì default package.
4. Build project theo hướng dẫn của template để sinh benchmark runner; chạy benchmark bằng runner JMH.
5. Ghi nhận command thực tế, version JMH/JDK, warm-up, measurement, fork, threads, CPU và GC khi công bố kết quả.

Ví dụ cú pháp chạy với **JMH runner đã được build sẵn**, không phải lệnh chạy bằng Java JDK thuần:

```bash
java -jar target/benchmarks.jar ErrorRateBenchmark -wi 3 -i 5 -f 2
```

Tên JAR và đường dẫn phụ thuộc cách project JMH được cấu hình; lệnh trên chỉ đúng khi build tạo `target/benchmarks.jar`. **Không có một số stdout cố định** cho benchmark này: số ns/op thực tế phụ thuộc máy, JVM và workload. Không nên chép kết quả giả vào tài liệu.

Điểm cần hiểu khi đọc kết quả:

- `@OperationsPerInvocation(TOTAL)` giúp JMH diễn giải phép đo một batch gồm 10.000 phần tử như số operations tương ứng. Nhưng phép đo vẫn gồm overhead vòng lặp, check và cộng dồn; không có “ns thuần của throw”.
- `throwAndCatch` có constructor/backtrace khi lỗi, nhưng `conditionalResult` không tạo exception. Đây là so sánh **hai chiến lược API/đường lỗi**, không phải đo riêng catch.
- `@Param` tạo kết quả theo từng tỷ lệ lỗi; khi phân tích, so sánh trong cùng cấu hình và cùng môi trường.
- `@State(Scope.Thread)` làm mỗi JMH worker có dataset riêng. Nếu muốn đo contention, cần một phép thử khác với shared state đã được xác định.
- Việc phương thức trả `long` giúp kết quả được tiêu thụ theo cơ chế JMH, giảm nguy cơ toàn bộ phép tính bị loại bỏ. Nhưng cần kiểm tra mã máy/profile nếu kết quả bất thường; không có benchmark nào miễn nhiễm mọi tối ưu.
- Ở tỷ lệ lỗi lớn, logic exception và logic branch không có cùng đặc tính bộ nhớ/JIT. Một kết quả chênh lệch không chứng minh “exception không bao giờ nên dùng”: còn phụ thuộc việc lỗi có là trạng thái nghiệp vụ dự kiến hay không.

Nếu cấu hình JMH cần đo **throughput theo batch** thay vì thời gian trung bình của một record, có thể bỏ `@OperationsPerInvocation` hoặc thay mode/đơn vị phù hợp. Luôn nói rõ “operation” là **một record** hay **một batch**.

## 8. Kiểm chứng dữ liệu và tính tương đương trước khi đo

Một benchmark chỉ có giá trị nếu hai phương án tạo **kết quả nghiệp vụ tương đương** trên cùng input. Với ví dụ trên:

- Cả `throwAndCatch` và `conditionalResult` cộng `value+1` cho mỗi input không âm.
- Với input âm, cả hai bỏ qua phần tử đó.
- Không có bên nào ghi log, retry hoặc gọi I/O.
- Bộ dữ liệu cố định được dựng từ cùng `badPerTenThousand`.
- Các phép tính đều trả `long` để tránh tràn `int` đối với tổng 10.000 phần tử.

Tuy nhiên, hai API **không tương đương về khả năng chẩn đoán**: một bên tạo `IllegalArgumentException` có stack trace, bên kia coi lỗi dữ liệu là một nhánh điều kiện không ném. Đây là khác biệt thiết kế phải được ghi nhận, không thể chỉ nhìn ns/op rồi tuyên bố branch luôn đúng.

Nếu muốn so sánh hai implementation có cùng hợp đồng exception, hãy giữ nguyên loại lỗi, message cần thiết, đường catch và semantic side effect; tránh để một implementation bỏ phần logging/validation mà implementation kia phải làm.

### Thử tần suất trước khi chạy benchmark

Có thể dùng test kiểm tra `@Param`:

```text
badPerTenThousand = 0      → 0 lỗi / 10.000 record
badPerTenThousand = 10     → 10 lỗi / 10.000 record
badPerTenThousand = 100    → 100 lỗi / 10.000 record
badPerTenThousand = 1000   → 1.000 lỗi / 10.000 record
badPerTenThousand = 5000   → 5.000 lỗi / 10.000 record
badPerTenThousand = 10000  → 10.000 lỗi / 10.000 record
```

Đây là bảng dữ liệu mong đợi theo code, không phải số hiệu năng. Kiểm tra count **ngoài vùng benchmark** để không thêm overhead của phép kiểm tra vào mẫu đo chính.

## 9. Tách một lỗi hiếm khỏi lỗi dồn đợt

Một phép đo JMH xử lý batch tuần tự thường cho biết thời gian trung bình theo workload, nhưng **không mô phỏng đầy đủ sự sụp đổ của hệ thống khi lỗi bùng phát cùng lúc**.

Để đánh giá burst:

1. Xây dựng hai kịch bản có **cùng tổng số request và tổng số lỗi**: phân tán so với lỗi tập trung theo cửa sổ thời gian.
2. Tạo tải bằng công cụ load test/driver bên ngoài, kiểm soát request rate và concurrency. Có thể mô phỏng dependency lỗi vào khoảng thời gian xác định.
3. Giữ số worker, queue capacity, log destination, timeout và retry policy như production.
4. Quan sát throughput, p50/p95/p99, request timeout, GC pause, CPU, memory, log dropped/block time và queue length.
5. Ghi lại thời điểm bắt đầu/kết thúc đợt lỗi để phân biệt thời gian hệ thống **chịu tải** và thời gian **hồi phục**.
6. Kiểm tra correctness: có job nào xử lý trùng, có thất thoát dữ liệu, có resource nào không cleanup, có status nào bị nhầm “thành công” do fallback không?

Ví dụ ứng dụng có 1.000 request/s và 1% lỗi tổng. Một kịch bản có 10 lỗi/s đều đặn khác kịch bản 100 lỗi/s trong một khoảng ngắn rồi không có lỗi. Với log sync hoặc queue giới hạn, hai kịch bản có thể gây độ trễ rất khác. Các con số ở đây chỉ để minh họa cách phân bố, **không phải số đo thực nghiệm**.

### Đừng để cơ chế tạo lỗi làm thay đổi workload ngoài ý muốn

Nếu fault injection được thực hiện bằng cách chủ động `Thread.sleep(500)` trước khi ném, bạn đang đo thêm **500 ms chờ** chứ không chỉ chi phí exception. Nếu thử timeout network, thời gian chờ là một phần đúng của scenario end-to-end nhưng không phải chi phí `throw`. Gắn nhãn scenario chính xác:

- `ValidationException` tại chỗ, không I/O.
- `IOException` do fake adapter ném ngay, không network.
- Timeout thật do network hoặc fake delay có chủ đích.
- Lỗi DB/HTTP có transaction, retry, backoff và cleanup thực tế.

Đây là các tình huống hữu ích khác nhau; không trộn thành một “benchmark exception” duy nhất.

## 10. Thay đổi tần suất mà không thêm random overhead vào hot path

Một lỗi thường gặp là:

```java
for (...) {
    if (random.nextDouble() < errorProbability) {
        throw new RuntimeException();
    }
    doWork();
}
```

Đây là snippet minh họa, `random`/`errorProbability`/`doWork` chưa định nghĩa. Nếu mục tiêu là đo chi phí của exception, bạn còn đo cả sinh số ngẫu nhiên, branch và sự thay đổi dữ liệu. Bản thân random có thể là phần workload thật, nhưng lúc đó phải ghi rõ.

Giải pháp phổ biến:

- **Precompute input** hoặc trạng thái phát lỗi trong `@Setup`.
- Dùng cùng dataset cho hai chiến lược.
- Dùng seed cố định nếu cần phép thử ngẫu nhiên có thể lặp.
- Kết hợp các mẫu phân bố khác nhau, không chỉ một pattern có tính dự đoán mạnh.
- Tách **tỷ lệ lỗi** khỏi **thứ tự lỗi**. Cùng 1% nhưng phân bố rải đều/burst/nhóm theo key có thể tạo chênh lệch JIT/cache/concurrency.
- Khi so sánh, đổi thứ tự chạy benchmark hoặc dùng fork độc lập để hạn chế ảnh hưởng nhiệt độ CPU, JIT state và cache state.

Không nhất thiết cấm random trong benchmark. Nếu random là phần công việc production phải làm, nó có thể là đối tượng đo. Quan trọng là **biết mình đang đo gì** và giữ mô hình nhất quán với câu hỏi.

## 11. Đo stack trace, construction, throw và catch riêng

Nếu profiling cho thấy exception allocation đáng kể, có thể thiết kế thêm các benchmark phụ:

**Construct-only:** tạo `new IllegalStateException("invalid")` nhưng không `throw`. Phải tiêu thụ object để JIT không xóa công việc một cách vô ích. Chi phí mặc định có thể gồm stack capture.

**Throw cached:** tạo exception ở setup, ném lại object cũ; đo khác biệt chi phí construction. Nhưng stack trace lúc ném lại không phải stack thực tế nơi thất bại; object dùng chung có rủi ro nếu đi nhiều thread. Đây là **kỹ thuật cách ly chi phí để hiểu**, không phải mẹo production nên áp dụng tự động.

**Throw new local:** tạo rồi ném/catch ngay, không log và không cleanup. So với construct-only để hiểu thêm phần control-flow/unwind, nhưng hiệu số giữa hai benchmark **không phải phép trừ tuyệt đối chính xác cho từng opcode**, vì JIT/code shape khác nhau.

**Throw across depth:** có chuỗi nhiều method và số frame thay đổi; phân biệt stack-capture với việc rời scope có `finally`.

**Log disabled/enabled:** benchmark riêng chi phí tạo message, render stack và appender. Một call log với formatting nặng dù level tắt có thể vẫn tốn CPU nếu biểu thức được đánh giá eager.

**Cleanup failure:** nếu `close()` cũng ném, chi phí khác vì Java phải giữ suppressed exception. Chỉ đưa vào scenario nếu đường này có ý nghĩa.

Cần ghi rõ mức bảo đảm thông tin lỗi. Exception không stack trace bằng constructor `Throwable(String, Throwable, boolean, boolean)` có thể tạo đường nhanh hơn nhưng **đánh đổi khả năng chẩn đoán**. Không so sánh với exception đầy đủ rồi coi chúng có hợp đồng tương đương.

### Cẩn thận với tối ưu fast-throw của HotSpot

Một số phiên bản/cấu hình HotSpot có tối ưu cho một số exception **do JVM tự sinh thường xuyên** tại cùng vị trí, ví dụ implicit `NullPointerException` hoặc bounds check. Stack trace có thể bị lược bỏ trong hoàn cảnh đặc biệt. Không suy rộng kết quả ấy sang `throw new DomainException(...)` hoặc mọi JVM.

Nếu benchmark cho số bất thường nhỏ sau warm-up, kiểm tra loại exception, JVM version/flags, số frame stack và assembly/profile nếu cần. **Không dùng behavior phụ thuộc HotSpot làm hợp đồng API ổn định**.

## 12. Logging: biến số cần đo tách biệt

Ghi log exception có thể vượt xa chi phí throw/catch nếu phát nhiều stack trace. Một phép thử production nên ghi rõ:

| Cấu hình | Điều đang đo | Điều dễ bị bỏ sót |
| --- | --- | --- |
| Không log | Constructor + throw/catch + handler nhẹ | Không đại diện đường vận hành có audit bắt buộc. |
| Log tắt theo level | Overhead kiểm tra level/chuẩn bị message | Biểu thức log eager vẫn có thể chạy trước khi logger quyết định bỏ qua. |
| Log message, không stack | Định dạng và appender cho thông điệp ngắn | Ít thông tin điều tra lỗi. |
| Log stack đầy đủ | Render frames/cause/suppressed, I/O | Chi phí tăng theo depth và chain, số dòng log. |
| Async logging | Enqueue và consumer xử lý nền | Hàng đợi đầy có thể block hoặc drop theo policy. |
| Sampling/rate limit | Lọc phần lớn log trong burst | Phải giữ metric tổng số lỗi để không che incident. |

Với `java.util.logging` có thể dùng dạng message supplier để hoãn phần formatting nếu không bật level:

```java
logger.log(Level.FINE, () -> expensiveMessage(context));
```

Đây là **snippet minh họa**, `logger`/`context`/`expensiveMessage` giả định đã có, cần import `java.util.logging.Level`. Supplier giúp tránh tạo message khi không cần trong cấu hình phù hợp, nhưng không làm chi phí của exception đã được tạo biến mất.

Không log nguyên payload, token, thông tin xác thực, SQL chứa dữ liệu nhạy cảm hoặc toàn bộ context cá nhân chỉ để benchmark có nhiều byte hơn. Log độ nặng giả định phải được tạo bằng dữ liệu kiểm thử không nhạy cảm.

### Log storm trong lỗi burst

Nếu 10.000 lỗi cùng ghi stack trace một lúc, logger có thể:
- Tăng mạnh allocation và GC;
- Chờ đồng bộ khi ghi console/file;
- Tăng queue size và block worker;
- Làm rơi bản ghi hoặc tạo thời gian chờ dài;
- Chiếm băng thông và dung lượng lưu trữ;
- Làm chậm việc xử lý các request không lỗi.

Vì thế khi đánh giá throughput/latency của dịch vụ, không chỉ bật/tắt `logger` rồi đo trung bình. Cần quan sát **log rate, queue occupancy, dropped log count, CPU appender và tốc độ drain** khi lỗi dồn theo thời gian.

## 13. Metric nên ghi cùng benchmark

Một bảng báo cáo tối thiểu có thể gồm:

| Metric | Đơn vị | Ý nghĩa |
| --- | --- | --- |
| Throughput | request/s hoặc record/s | Công việc hoàn thành trên đơn vị thời gian. |
| Mean latency | ms/operation | Trung bình; dễ bị ảnh hưởng bởi tỷ lệ success/failure. |
| p50/p95/p99 latency | ms | Phân phối độ trễ; đặc biệt quan trọng với incident. |
| Allocation rate | MB/s hoặc B/op | Áp lực cấp phát, stack trace, logging. |
| GC pause/frequency | ms/count | Ảnh hưởng đến tail latency/throughput. |
| CPU utilization | % theo core/process | Tải xử lý thực, không chỉ thời gian chờ. |
| Error/exception rate | lỗi/s và % request | Kiểm chứng scenario; tránh suy từ log count. |
| Log volume/drop/block | records/s, bytes/s, count, ms | Chi phí và mức độ mất dữ liệu quan sát. |
| Queue depth | số job/log record | Dấu hiệu backpressure/saturation. |
| Retry attempts | attempts/request | Phân biệt load gốc và tải phát sinh từ retry. |
| Resource usage | file descriptors, connections, threads | Tình trạng cleanup khi lỗi liên tiếp. |

Với JMH microbenchmark, kết quả `ns/op`, `ops/s` và confidence/error estimates hữu ích; chúng **không tự mang p99 latency của request end-to-end**. Muốn p99 cho dịch vụ, dùng công cụ tải/quan sát phù hợp có timestamp và kiểm soát workload. Nếu đo latency từ phía client, lưu ý network, TLS, scheduling và queueing.

### Quan sát bằng Java Flight Recorder và profiler

Java Flight Recorder (JFR) và profiler có thể hỗ trợ tìm hot spot, phân tích allocation, CPU, pause và exception activity theo khả năng/sự kiện đã bật. Khi thu thập cần ghi cấu hình recording và overhead của profiling. **Không giả định mọi sự kiện exception đều được ghi đầy đủ trong mọi cấu hình mặc định của JFR**, vì event settings/threshold có thể khác.

Một quy trình thực dụng:

1. Chạy baseline healthy và degraded với cùng JVM/cấu hình và dữ liệu đã kiểm soát.
2. Thu throughput/latency/allocations/GC/log metrics.
3. Profile để thấy chi phí ở constructor exception, stack trace, logger, serializer, I/O hay business code.
4. Chỉ tối ưu bộ phận chiếm đáng kể tài nguyên.
5. Chạy lại cùng scenario và xác nhận không giảm correctness, observability hay khả năng chẩn đoán.

Không nên tắt stack trace hoặc nuốt exception trước khi biết đây thật sự là bottleneck.

## 14. Benchmark phải phân biệt “request thành công sau retry” với “attempt lỗi”

Ví dụ một request gọi dependency ba lần:

```text
Request #1:
  attempt 1: IOException
  attempt 2: IOException
  attempt 3: success
Result: request thành công, nhưng 2 exception đã phát sinh.
```

Nếu hệ thống báo 0% request lỗi nhưng mỗi request retry hai lần, exception rate có thể rất cao. Benchmark theo `request` phải mô phỏng retry policy và backoff nếu đây là hành vi production; benchmark theo `attempt` nên gắn nhãn riêng.

Đừng so sánh một phiên bản “không retry” với một phiên bản “có retry” rồi kết luận phiên bản sau chậm vì exception. Nó đang làm nhiều công việc hơn.

Khi retry trên lỗi timeout, cần biết attempt cũ còn đang chạy hay không, có side effect không và có idempotency không. Không cần thiết kế benchmark làm phát sinh giao dịch thật ngoài môi trường kiểm thử chỉ để có “lỗi thực tế”.

## 15. Concurrency, pooling và ảnh hưởng của lỗi đến thread

Một phép thử một thread và một vòng lặp trong memory không phản ánh:

- Executor queue đang có backlog;
- Thread worker bị chặn khi logger sync;
- Cùng dependency không hoạt động làm hàng nghìn request retry;
- Circuit breaker chuyển trạng thái;
- Semaphore hoặc connection pool cạn vì cleanup không đúng;
- GC pause ảnh hưởng đồng thời nhiều request;
- Tail latency tăng khi một lượng nhỏ request giữ tài nguyên quá lâu.

Trong load test nên đo số worker và số request đồng thời, tránh dùng số thread cao không kiểm soát khiến benchmark đo thread scheduling overhead thay vì exception. Nếu workload là HTTP server, theo dõi open-loop request arrival rate (phát request theo tốc độ định trước) hoặc closed-loop concurrency có chủ đích và ghi rõ mô hình tải.

Một bẫy là **coordinated omission**: nếu tool sinh request mới chỉ sau khi request trước trả kết quả, lúc server chậm, nó tự giảm tải và không ghi nhận những request đáng lẽ đã đến. Khi cần SLO/tail latency, chọn mô hình tải và phép đo tránh che khoảng thời gian hệ thống quá tải.

## 16. Đảm bảo độ công bằng giữa hai implementation

Hai phương án muốn so sánh phải được đánh giá về **cùng khối lượng công việc và cùng hợp đồng**:

- Cùng input dataset/tỷ lệ lỗi/thứ tự input theo scenario.
- Cùng kết quả thành công và cùng cách xử lý lỗi.
- Cùng mức độ logging/metrics nếu đang đo end-to-end.
- Cùng tần suất retry, giới hạn deadline, cleanup.
- Cùng JVM flags, heap/GC, hardware, container limits.
- JMH warm-up/fork và môi trường ổn định tương đương.
- Không cho một phiên bản bỏ validation hoặc bỏ I/O rồi tuyên bố “nhanh hơn”.

Nếu phương án result type không cung cấp stack trace còn phương án exception có full trace, chúng **khác semantics**. Vẫn có thể so sánh để quyết định thiết kế, nhưng kết luận phải nêu rõ trade-off thay vì gọi đó là tối ưu “miễn phí”.

### Chống tối ưu hóa benchmark không thực tế

Các lỗi thường gặp:

- Kết quả bị bỏ qua nên JIT loại bỏ tính toán;
- Giá trị đầu vào là hằng mà JIT có thể suy ra luôn;
- Dữ liệu được tạo ngẫu nhiên trong vùng đo nhưng production đã có dữ liệu;
- Benchmark chỉ ném một exception singleton nên mất construction/stack capture;
- Benchmark chỉ dùng một loại `NullPointerException` implicit đang được JVM tối ưu đặc biệt;
- So sánh các phép đo chạy trên CPU bị thermal throttling khác nhau;
- Fork quá ít, chỉ lấy một số “nhanh nhất”;
- Lấy kết quả benchmark run không lỗi để dự đoán hiệu năng error burst.

JMH giúp giảm một số nguy cơ, nhưng **không tự sửa một workload sai**. Review kịch bản quan trọng hơn việc thêm nhiều annotation.

## 17. Báo cáo benchmark nên có cấu trúc thế nào?

Một báo cáo có thể dùng khung:

```text
Mục tiêu: đo chi phí lựa chọn xử lý lỗi cho parser batch.
JDK: <version và vendor thực tế>
JMH: <version thực tế>
Hardware/OS: <CPU, memory, giới hạn container thực tế>
GC/JVM flags: <giá trị thực tế>
Work unit: một record / một batch 10000 record
Scenario: 0%, 0.1%, 1%, 10%, 50%, 100% lỗi
Exception: IllegalArgumentException tạo mới; catch tại chỗ
Logging: OFF trong JMH; scenario riêng khi logging ON
Warm-up/measurement/forks: <giá trị thực tế>
Output: throughput, average time, B/op, GC metrics
Load test: request/s, p50/p95/p99, queue/log backpressure
Correctness: output và số lượng lỗi khớp giữa hai phương án
Kết luận: <thay đổi nào giúp workload nào, đánh đổi ra sao>
```

Đây là **mẫu báo cáo**, không phải số liệu đo và các mục giữa dấu `<...>` chỉ là tên trường cần điền từ phép thử thật. Không điền số giả để tạo vẻ đã benchmark.

Mỗi kết luận nên giới hạn bởi dữ liệu:

> Trong môi trường X, với input Y và tỷ lệ lỗi Z, phương án A có B/op thấp hơn phương án B và throughput tốt hơn; kết quả chưa chứng minh tác động lên p99 khi log được bật.

Không nên kết luận:

> Exception Java luôn chậm gấp 1000 lần và không nên dùng.

Đây là khẳng định thiếu điều kiện, không có một benchmark phù hợp mọi workload và mọi JVM.

## 18. Tình huống áp dụng: validation, parse và lỗi hệ thống

### 18.1. Lỗi validation hiếm

Một API công khai nhận phần lớn request hợp lệ, chỉ khoảng 0,1% vi phạm ràng buộc. Nếu hệ thống đã có exception rõ loại và hợp đồng tốt, độ trễ trung bình có thể không đáng kể. Benchmark đường thành công với `try/catch` và đường lỗi hiếm; đừng vội sửa API chỉ vì thấy benchmark 100% throw chậm.

### 18.2. Parser batch thường gặp dữ liệu sai

Nếu 20–40% record lỗi là **trạng thái được dự kiến**, việc ném exception cho từng record có thể tốn allocation/GC đáng kể. Một result type như `ValidationResult` có thể phù hợp hơn. Nhưng phải giữ thống kê lỗi và vị trí record; tối ưu không được xóa thông tin kiểm tra cần thiết.

### 18.3. Lỗi mạng diện rộng

Một lỗi network timeout có thể tiêu tốn hàng trăm milliseconds chờ; chi phí tạo `IOException` có thể rất nhỏ so với thời gian chờ. Nhưng khi hàng chục nghìn request đồng thời nhận exception rồi ghi full stack, logging/GC có thể trở thành tải lớn. Đo end-to-end, retry và log throughput, đừng chỉ đo throw/catch tại chỗ.

### 18.4. Worker bị ngắt và dọn dẹp tài nguyên

Nếu tác vụ bị cancel, `InterruptedException` có thể khiến `finally`/`try-with-resources` đóng socket, trả connection hoặc unlock. Benchmark đường cancel phải tính thời gian cleanup thật nếu câu hỏi là **thời gian shutdown**; không được bỏ cleanup để có con số đẹp.

### 18.5. CompletableFuture và task failure

`CompletableFuture` có thể lưu exceptional completion; `join`/`get` còn tạo hoặc đưa ra wrapper `CompletionException`/`ExecutionException` theo API. Nếu workload async, đo cả pipeline/callback, queueing, executor và cách fallback ảnh hưởng kết quả. Microbenchmark ném exception trên một thread không đại diện cho độ trễ hoàn thành cả async pipeline.

## 19. Những lỗi phổ biến khi đánh giá performance

**Luôn ném exception trong benchmark rồi áp dụng số liệu cho production có 0,1% lỗi.** Đây là sai mô hình tần suất. Phải đo workload mixed với tỷ lệ thực.

**Lấy số lượng log làm số lượng exception.** Một exception có thể bị log nhiều lần hoặc không được log; dùng counter ở boundary phù hợp.

**Giả định mọi lỗi giống nhau.** Validation, timeout, OOM, I/O, cancellation có chi phí và chính sách khác nhau.

**Dùng `System.nanoTime` một lần rồi chọn kết quả thấp nhất.** Chưa xử lý warm-up, JIT, GC, variance và noise môi trường.

**Đo không có control group.** Muốn nói throw/catch tạo overhead bao nhiêu, cần xác định baseline có cùng logic thành công/validation.

**Không kiểm tra tính đúng của dataset.** Nghĩ chạy ở 1% lỗi nhưng dữ liệu thật sinh 0% hoặc 100%, dẫn đến kết luận sai.

**Tạo random, format message và ghi log trong benchmark throw nhưng không ghi nhận.** Chi phí đang bị trộn; tách bài kiểm tra hoặc ghi rõ đó là workload end-to-end.

**Dùng cached exception nhưng suy rộng sang throw new.** Tái sử dụng object bỏ qua constructor/backtrace và thay stack trace semantics.

**Tắt stack trace chỉ để giảm ns/op.** Có thể làm mất thông tin điều tra production; cần chứng minh lợi ích và đánh đổi.

**Đo trung bình nhưng bỏ p99.** Exception burst có thể khiến một số request chậm nghiêm trọng dù mean chỉ tăng nhẹ.

**Không xét queue/log backpressure.** Async logging không làm chi phí biến mất mà chuyển sang consumer và hàng đợi.

**So sánh khác JDK/hardware/configuration.** Một số kết quả phụ thuộc JVM, JIT, GC và flag như fast-throw; cần ghi môi trường.

**Không chạy lại sau tối ưu.** Một kết luận có giá trị phải dựa trên phép đo lặp, cùng scenario và kiểm tra regression đúng.

## 20. Checklist thực hành

Trước khi tin một benchmark exception, hãy xác nhận:

- [ ] Đã xác định **câu hỏi đo**: constructor, throw/catch, logging hay end-to-end?
- [ ] Đã có baseline đường thành công và xử lý lỗi tương đương.
- [ ] Đã xác định **đơn vị**: invocation, record, request, task hay retry attempt.
- [ ] Đã có tỷ lệ lỗi dựa trên dữ liệu hoặc **đánh dấu rõ giả định**.
- [ ] Có ít nhất một kịch bản lỗi hiếm và một kịch bản lỗi cao/burst phù hợp.
- [ ] Input có cùng phân phối/kích thước giữa các implementation; đã test đếm lỗi.
- [ ] Mọi giá trị trả về được tiêu thụ; không vô tình benchmark code bị JIT loại bỏ.
- [ ] JMH có cấu hình warm-up, measurement, forks, threads và trạng thái rõ ràng.
- [ ] Log enabled/disabled, message formatting và output destination được ghi nhận.
- [ ] GC/allocation metrics được xem cùng CPU/throughput.
- [ ] Khi cần SLO, đã đo p95/p99 bằng load test có tải và concurrency phù hợp.
- [ ] Không lược bỏ cleanup, cause/stack trace hoặc validation để đạt số nhanh hơn.
- [ ] Báo cáo có môi trường, version, lệnh chạy và mức sai số; không dùng kết quả giả.
- [ ] Đã thử lại trên workload thực tế và kiểm tra correctness sau tối ưu.

## 21. Bài tập tự kiểm tra

**Câu 1.** API có 1 triệu request, 1.000 request lỗi. Benchmark ném exception trong tất cả 1 triệu iteration có đại diện tỷ lệ production không?

**Trả lời:** Không. Tỷ lệ request lỗi là `1000/1_000_000 = 0,1%`. Một phép thử 100% throw có thể là stress scenario, nhưng phải có phép thử 0,1% để mô phỏng bình thường.

**Câu 2.** Hai benchmark cùng 10% lỗi. A rải đều, B dồn hết lỗi vào giai đoạn đầu. Kết quả end-to-end có thể khác không?

**Trả lời:** Có. Burst có thể làm queue log đầy, contention, retry và GC tăng đột ngột. Hai tỷ lệ tổng bằng nhau không bảo đảm cùng p99.

**Câu 3.** Benchmark `throw new IllegalArgumentException` so với `throw cachedException` chênh đáng kể. Có nên dùng cached exception trong production?

**Trả lời:** Không kết luận vội. Cached exception bỏ qua chi phí tạo/stack capture ở mỗi lần và làm stack trace có thể không còn phản ánh nơi thất bại; cần xem contract, chẩn đoán và độ chính xác trước khi đánh đổi.

**Câu 4.** Một vòng `try/catch` không xảy ra lỗi có phải trả chi phí đầy đủ của stack trace không?

**Trả lời:** Không. Nếu không tạo Throwable và không throw, stack trace của exception không phát sinh chỉ vì có cấu trúc `catch`.

**Câu 5.** Ở đường lỗi I/O, phần lớn thời gian là timeout 2 giây. Việc tối ưu constructor exception có thể giảm p99 đáng kể không?

**Trả lời:** Không thể khẳng định. Nếu thời gian chờ I/O chiếm phần lớn, constructor có thể không phải bottleneck. Cần profiling và tách thời gian chờ, cleanup, retry, log.

**Câu 6.** JMH cho biết một phương án nhanh hơn 20% trong 100% failure, nhưng prod chỉ lỗi 0,1%. Có thể công bố toàn dịch vụ nhanh hơn 20% không?

**Trả lời:** Không. Cần đo mix thực tế và end-to-end. Kết quả cho trường hợp 100% failure không tự suy ra mức cải thiện toàn bộ workload.

## 22. Kết luận

**Đo exception đúng nghĩa là đo đúng workload.** Mỗi phép đo cần biết tỷ lệ lỗi, phân bố theo thời gian, đơn vị công việc, loại lỗi, đường catch/cleanup/logging và mục tiêu metric. Dùng JMH để khám phá chi phí vi mô dưới cấu hình có kiểm soát; dùng load test, JFR/profiler và metrics để xác nhận ảnh hưởng trong hệ thống thật. Đối chiếu thành công, lỗi hiếm, lỗi nhiều và error burst; không suy từ một phép thử 100% throw thành kết luận tuyệt đối cho mọi ứng dụng.

Tối ưu đáng tin là tối ưu **được đo, có thể tái lập và không làm thay đổi hợp đồng hoặc mất khả năng chẩn đoán**. Giảm exception trong đường nóng khi đó là trạng thái dự kiến có thể có ích; nhưng không hy sinh validation, stack trace cần thiết, cause, cleanup và logging có trách nhiệm chỉ để có con số ns/op nhỏ hơn.
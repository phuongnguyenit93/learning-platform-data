# Benchmark Reflection với warmup, lời gọi trực tiếp và workload thực tế

## 1. Mục tiêu

Khi xây dựng công cụ dùng Java Reflection, một câu hỏi thường gặp là: **gọi phương thức qua `Method.invoke` có thực sự ảnh hưởng đến hiệu năng ứng dụng không?** Muốn trả lời chính xác, cần so sánh với lời gọi trực tiếp trong những điều kiện tương đương, tách chi phí lookup metadata khỏi chi phí invocation, làm nóng JVM và chạy công việc đủ giống production.

Sau bài này, bạn sẽ biết cách:

- Thiết kế baseline **direct invocation** và phép đo **cached reflective invocation** có cùng đầu vào, cùng logic và đầu ra.
- Giải thích vai trò của warmup, JIT, inlining, dead-code elimination, GC và tiered compilation.
- Phân biệt bài toán đo overhead thuần của lời gọi với bài toán đo thời gian của một workload thực tế.
- Viết benchmark minh họa độc lập bằng Java 17+, rồi chuyển sang **JMH** để lấy số đo dùng cho quyết định kỹ thuật.
- Đọc `ns/op`, throughput, độ biến động, fork và kết quả benchmark mà không rút ra kết luận quá mức.
- Quyết định khi nào việc cache `Method` có giá trị; khi nào cần profile và benchmark cả pipeline.

Bài học chỉ tập trung vào benchmark và thiết kế đo hiệu năng. Các API reflection để tìm method và gọi method được sử dụng làm công cụ trong ví dụ.

## 2. Trước tiên phải xác định chính xác đang đo gì

Một request trong công cụ reflection có thể đi theo quy trình:

```text
Nhận input -> parse -> xác định class/method -> chuyển đổi đối số
           -> gọi method -> xử lý kết quả -> trả response
```

Các phép đo khác nhau trả lời **các câu hỏi khác nhau**:

| Kịch bản | Nội dung đo | Khi nào hữu ích |
| --- | --- | --- |
| **Direct** | `Target.operation(input)` | Baseline của cùng thao tác nghiệp vụ |
| **Cached reflection** | `cachedMethod.invoke(target, input)` | Đo đường gọi reflective khi `Method` đã được tìm trước |
| **Lookup + invocation** | `getMethod(...); invoke(...)` trong mỗi lần gọi | Đo tổng chi phí tra cứu và gọi khi không cache |
| **End-to-end** | Parse, validation, dispatch, method invocation, output | Đo tác động đến trải nghiệm thực tế hoặc throughput |

Nếu so sánh direct với `getMethod(...).invoke(...)` trong cùng vòng lặp, số đo phản ánh **cả lookup lẫn invoke**. Không được diễn giải toàn bộ chênh lệch thành chi phí riêng của `Method.invoke`.

`Method.invoke` dùng kiểu `Object` cho đầu vào/đầu ra, có thể kéo theo boxing, unboxing, kiểm tra hoặc chuyển đổi primitive hợp lệ. JIT có thể tối ưu khác nhau giữa các đường gọi. Vì vậy không thể khẳng định “Reflection luôn chậm X lần” nếu chưa chỉ rõ workload, JVM và cấu hình.

Một cách nhìn hữu ích:

```text
Tổng chi phí công cụ ≈ parse + lookup/cache + convert + dispatch + target + response
```

Đây là mô hình phân tích chứ không phải phương trình chính xác trong hệ thống nhiều luồng. Các phần có thể tương tác qua GC, CPU cache, contention và scheduler.

## 3. Warmup: lý do số đo ban đầu dễ sai

JVM có thể bắt đầu thực thi bytecode bằng interpreter hoặc mã biên dịch ít tối ưu, sau đó thu thập profile và dùng JIT để biên dịch những đường code nóng. JIT có thể inline, loại bỏ phép tính thừa, chuyên biệt hóa kiểu tại call site, hoặc deoptimize khi giả định trước đó không còn đúng.

Do vậy, thời gian ở vài lời gọi đầu thường khác so với trạng thái ổn định (*steady state*).

Quy trình minh họa:

```text
Khởi tạo dữ liệu và cache Method
    |
    v
Warmup direct và reflection (cùng phân bố input)
    |
    v
Đo nhiều lượt, cân bằng thứ tự chạy
    |
    v
Kiểm tra checksum / kết quả đúng
    |
    v
Phân tích kết quả, độ biến động và giới hạn phép đo
```

Các nguyên tắc:

1. **Warmup cả hai đường gọi.** Không làm nóng direct 100.000 lượt nhưng đo reflection ngay từ lần đầu.
2. **Dùng input đại diện.** Warmup bằng đối tượng/method khác có thể không làm nóng đúng đường code cần đo.
3. **Không xem số vòng warmup cố định là bảo đảm.** JVM có thể tiếp tục JIT/GC sau warmup; cần xem tính ổn định qua nhiều lần đo.
4. **Tách cold start khỏi steady state.** Ứng dụng CLI ngắn hạn có thể quan tâm thời gian khởi động, lookup lần đầu; server chạy lâu có thể quan tâm throughput đã warm.
5. **Không đo riêng một lượt rồi kết luận.** Sự khác biệt nhỏ có thể chìm trong nhiễu hệ điều hành, lịch CPU hoặc GC.

## 4. Benchmark minh họa Java 17+: direct và cached Method.invoke

Ví dụ độc lập sử dụng hai workload:

- **TINY:** `plusOne(int)` chỉ cộng 1, để thấy chi phí đường gọi có thể nổi bật khi target quá nhỏ.
- **REALISTIC:** `parseOrder(String)` tách bản ghi, trim/uppercase vùng, parse số lượng và giá, rồi tính kết quả. Đây là workload CPU/chuỗi đơn giản mang tính đại diện hơn, dù vẫn chưa thay thế tác vụ production.

Cả hai dùng cùng dữ liệu cho direct/reflection. `getMethod` được gọi **trước** khi đo. Có checksum để xác nhận hai đường cho cùng kết quả. Benchmark chạy warmup mỗi đường, lấy nhiều mẫu và đảo thứ tự chạy giữa các mẫu.

Tạo tệp `ReflectionBenchmarkDemo.java`:

```java
import java.lang.reflect.Method;
import java.util.Locale;

public final class ReflectionBenchmarkDemo {
    private static final String[] ROWS = {
            "VN|2|350", "US|4|150", "JP|1|800", "DE|5|99"
    };
    private static final int WARMUP_CALLS = 20_000;
    private static final int CALLS_PER_SAMPLE = 60_000;
    private static final int SAMPLES = 5;
    private static volatile long sink;

    public static int plusOne(int value) {
        return value + 1;
    }

    public static long parseOrder(String row) {
        String[] fields = row.split("\\|", -1);
        String region = fields[0].trim().toUpperCase(Locale.ROOT);
        int quantity = Integer.parseInt(fields[1]);
        long cents = Long.parseLong(fields[2]);
        return quantity * cents + region.length() * 7L;
    }

    private static long run(Method method, boolean realistic,
                            boolean reflective, int calls) throws Exception {
        long checksum = 0;
        for (int i = 0; i < calls; i++) {
            if (realistic) {
                String row = ROWS[i % ROWS.length];
                long result = reflective
                        ? (Long) method.invoke(null, row)
                        : parseOrder(row);
                checksum += result;
            } else {
                int value = i * 31 + 5;
                int result = reflective
                        ? (Integer) method.invoke(null, value)
                        : plusOne(value);
                checksum += result;
            }
        }
        return checksum;
    }

    private static double timed(Method method, boolean realistic,
                                boolean reflective) throws Exception {
        long start = System.nanoTime();
        long checksum = run(method, realistic, reflective, CALLS_PER_SAMPLE);
        long elapsed = System.nanoTime() - start;
        sink = checksum;
        return (double) elapsed / CALLS_PER_SAMPLE;
    }

    private static void compare(Method method, boolean realistic) throws Exception {
        String label = realistic ? "REALISTIC" : "TINY";
        long direct = run(method, realistic, false, CALLS_PER_SAMPLE);
        long reflection = run(method, realistic, true, CALLS_PER_SAMPLE);
        if (direct != reflection) {
            throw new AssertionError("Different results: " + label);
        }
        sink = direct;
        for (int warm = 0; warm < 8; warm++) {
            sink = run(method, realistic, false, WARMUP_CALLS);
            sink = run(method, realistic, true, WARMUP_CALLS);
        }

        System.out.println(label + ": same checksum = true");
        for (int sample = 0; sample < SAMPLES; sample++) {
            double directNs;
            double reflectionNs;
            if (sample % 2 == 0) {
                directNs = timed(method, realistic, false);
                reflectionNs = timed(method, realistic, true);
            } else {
                reflectionNs = timed(method, realistic, true);
                directNs = timed(method, realistic, false);
            }
            System.out.printf(Locale.ROOT,
                    "sample %d: direct %.1f ns/op, reflection %.1f ns/op%n",
                    sample + 1, directNs, reflectionNs);
        }
    }

    public static void main(String[] args) throws Exception {
        Method tiny = ReflectionBenchmarkDemo.class.getMethod("plusOne", int.class);
        Method realistic = ReflectionBenchmarkDemo.class.getMethod(
                "parseOrder", String.class);
        compare(tiny, false);
        compare(realistic, true);
    }
}
```

Biên dịch và chạy:

```bash
javac ReflectionBenchmarkDemo.java
java ReflectionBenchmarkDemo
```

Chương trình đã được chạy thực tế với JDK. Output có hai dòng xác thực kết quả:

```text
TINY: same checksum = true
REALISTIC: same checksum = true
```

Hai dòng đó **không liền nhau trong stdout**: sau dòng `TINY` có năm dòng `sample ...` rồi mới đến dòng `REALISTIC` và năm dòng `sample ...` tiếp theo. Mỗi dòng mẫu chứa `direct ... ns/op` và `reflection ... ns/op`. Các con số đo **không có stdout cố định**, phụ thuộc CPU, phiên bản JVM, tải máy và tối ưu JIT.

Trong một lần chạy thử, direct TINY có thể được báo thấp hơn 1 ns/op. Đó là tín hiệu phải đánh giá **mức độ tối ưu của JIT đối với benchmark**, không thể khẳng định một lần gọi ứng dụng thực tế nhất định chỉ tốn từng ấy thời gian.

### Giải thích code

- Hai `Method` được lấy trước `compare`, nên đây là **cached invocation**.
- `run` dùng cùng đối số cho mỗi cặp direct/reflection. Phương thức static sử dụng `method.invoke(null, ...)` vì không có receiver instance.
- Reflection trả `Object`; phép ép `(Integer)`/`(Long)` unbox kết quả đúng primitive.
- Kiểm tra checksum trước đo xác nhận hai đường cho cùng kết quả. Đo nhanh hơn nhưng tính sai là vô nghĩa.
- Warmup lặp lại cả hai đường, trước khi vào năm mẫu đo.
- Thứ tự direct/reflection thay đổi giữa mẫu chẵn và lẻ để giảm một phần thiên lệch thứ tự.
- `System.nanoTime()` đo **elapsed time**, rồi chia cho số lần gọi để ước lượng `ns/op`.
- `volatile sink` làm kết quả có thể quan sát được, nhưng vẫn không bảo đảm loại bỏ mọi vấn đề tối ưu.

**Giới hạn:** chương trình dùng một JVM process, vòng lặp riêng và số lượng input nhỏ; không tạo fork độc lập hay có công cụ kiểm soát JIT đầy đủ. Nó là ví dụ có thể chạy để học, **không phải số benchmark đủ tin cậy cho quyết định tối ưu sản phẩm**.

## 5. Những điều dễ làm sai phép đo

### 5.1. Inlining, constant folding và dead-code elimination

Phép cộng đơn giản `plusOne(x)` có thể bị JIT inline, đơn giản hóa hoặc tối ưu toàn vòng lặp. Nếu kết quả không được sử dụng, JVM có thể loại bỏ nhiều công việc. Dù có `volatile sink` sau vòng lặp, trình biên dịch vẫn có quyền thực hiện nhiều biến đổi bảo toàn kết quả quan sát được.

Đặc biệt, so sánh direct với reflection trên target cực nhỏ dễ phóng đại chênh lệch bởi đường direct tối ưu vượt xa mã nguồn tưởng tượng ban đầu. Điều đó không có nghĩa số đo “lỗi” theo nghĩa công cụ đo sai thời gian; nó có nghĩa **mã máy đang được đo không nhất thiết đại diện cho production**.

JMH cho phép trả về giá trị của `@Benchmark` hoặc dùng `Blackhole` để tiêu thụ output; đây là một trong nhiều biện pháp chống dead-code elimination. Tuy nhiên, chính input và cấu trúc workload vẫn phải được thiết kế đúng.

### 5.2. GC, allocation và boxing

`Method.invoke` dùng API nhận/trả `Object` nên trường hợp primitive có thể liên quan boxing/unboxing. Một số phân bổ có thể bị JVM tối ưu, nhưng vẫn cần phân biệt trường hợp tham số primitive với đối tượng.

Workload chuỗi có thể tạo mảng từ `split` và đối tượng parse/normalize; khi target làm nhiều việc như thế, chi phí gọi reflective có thể trở thành tỷ lệ nhỏ. GC có thể làm một mẫu bị chậm đột biến. Nếu đối tượng được cấp phát nhiều, nên theo dõi lượng allocation/GC song song với `ns/op`.

### 5.3. Nhiễu hệ thống và số lượng mẫu

Một phép đo microbenchmark quá ngắn dễ bị ảnh hưởng bởi chi phí gọi đồng hồ và scheduling. Một lần chạy dễ bị lệch do JIT hoặc nhiệt độ CPU. Vì vậy:

- Thu thập **nhiều iteration và nhiều fork**.
- Đo trong môi trường tương đối ổn định, ghi JDK vendor/version, flags, CPU, OS, heap.
- Không đặt logging/format output vào vùng đo trừ khi mục tiêu đo chính chúng.
- Giữ đầu vào tương đương giữa đường direct và reflection.
- Xem phân bố, độ lệch và error thay vì chỉ lấy một con số đẹp.

## 6. Benchmark nghiêm túc bằng JMH

[JMH (Java Microbenchmark Harness)](https://openjdk.org/projects/code-tools/jmh/) của OpenJDK có cơ chế warmup, measurement, JVM fork, benchmark mode và quản lý tiêu thụ kết quả phù hợp hơn phép đo thủ công. JMH không tự làm workload trở nên đại diện; nó là hạ tầng đo.

Một cách bắt đầu là tạo dự án Maven bằng JMH archetype với **phiên bản ví dụ 1.37** (cần Maven và khả năng tải dependencies):

```bash
mvn archetype:generate -DinteractiveMode=false -DarchetypeGroupId=org.openjdk.jmh -DarchetypeArtifactId=jmh-java-benchmark-archetype -DarchetypeVersion=1.37 -DgroupId=demo -DartifactId=reflection-bench -Dversion=1.0
```

Lưu class sau thành `reflection-bench/src/main/java/demo/ReflectionJmh.java`. Cấu hình project build với JDK 17 trở lên.

```java
package demo;

import java.lang.reflect.Method;
import java.util.Locale;
import java.util.concurrent.TimeUnit;
import org.openjdk.jmh.annotations.*;

@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.NANOSECONDS)
@Warmup(iterations = 5, time = 1)
@Measurement(iterations = 5, time = 1)
@Fork(2)
public class ReflectionJmh {
    private final String[] rows = {
            "VN|2|350", "US|4|150", "JP|1|800", "DE|5|99"
    };
    private int index;
    private Method tinyMethod;
    private Method realisticMethod;

    public static int plusOne(int x) {
        return x + 1;
    }

    public static long parseOrder(String row) {
        String[] fields = row.split("\\|", -1);
        String region = fields[0].trim().toUpperCase(Locale.ROOT);
        int quantity = Integer.parseInt(fields[1]);
        long cents = Long.parseLong(fields[2]);
        return quantity * cents + region.length() * 7L;
    }

    @Setup(Level.Trial)
    public void setUp() throws ReflectiveOperationException {
        tinyMethod = ReflectionJmh.class.getMethod("plusOne", int.class);
        realisticMethod = ReflectionJmh.class.getMethod(
                "parseOrder", String.class);
    }

    private String nextRow() {
        return rows[(index++) & 3];
    }

    @Benchmark
    public int directTiny() {
        return plusOne(index++);
    }

    @Benchmark
    public int reflectiveTiny() throws ReflectiveOperationException {
        return (Integer) tinyMethod.invoke(null, index++);
    }

    @Benchmark
    public long directRealistic() {
        return parseOrder(nextRow());
    }

    @Benchmark
    public long reflectiveRealistic() throws ReflectiveOperationException {
        return (Long) realisticMethod.invoke(null, nextRow());
    }
}
```

Sau khi tạo class và có Maven/JMH dependencies từ archetype:

```bash
cd reflection-bench
mvn clean verify
java -jar target/benchmarks.jar ".*ReflectionJmh.*" -rf json -rff results.json
```

Lệnh ghi kết quả vào `results.json`; không có bảng số cố định vì chạy trên JVM/máy khác nhau cho kết quả khác nhau.

**Ý nghĩa thiết kế:**

- `@Setup(Level.Trial)` cache `Method` ngoài phần đo; đây là phép đo **cached reflection**, không tính chi phí lookup.
- `@State(Scope.Thread)` cung cấp state riêng theo thread; `index` thay đổi theo lần gọi để tránh dùng một literal bất biến làm input duy nhất.
- `@Warmup`, `@Measurement` và `@Fork` cấu hình warmup, số lượt đo và số JVM fork. Có thể tăng khi độ biến động lớn.
- JMH sử dụng kết quả trả về của `@Benchmark` để hạn chế những tối ưu làm phép đo biến mất.
- Hai benchmark tiny so sánh lời gọi xử lý primitive; hai benchmark realistic cùng chạy `parseOrder` trên bộ input tương đương.
- `@BenchmarkMode(Mode.AverageTime)` kết hợp `@OutputTimeUnit(TimeUnit.NANOSECONDS)` cho score kiểu `ns/op`.

Ví dụ JMH này minh họa cách chuẩn bị một phép so sánh độc lập. Trước khi dùng cho quyết định thật, cần xác minh phân bố input gần production, không có thay đổi state ngoài dự kiến, và các target không bị JIT đơn giản hóa tới mức vô nghĩa. Có thể thiết kế benchmark thứ ba cho lookup hoặc cache miss, thay vì đưa lookup vào phép đo cached invocation.

## 7. Workload thực tế quan trọng hơn một phép cộng

Một benchmark tiny có thể làm overhead gọi nổi bật. Nhưng phần lớn sản phẩm phải parse request, validate, thao tác dữ liệu, gọi I/O hoặc giao tiếp database. Các tác vụ đó có thể tốn nhiều hơn cơ chế gọi phương thức.

Cần chọn workload đại diện theo ít nhất các chiều:

| Chiều cần mô phỏng | Ví dụ |
| --- | --- |
| Độ phức tạp target | Trả primitive; parse chuỗi; xử lý object; truy vấn dữ liệu |
| Loại tham số | Primitive, wrapper, String, DTO, mảng, nhiều tham số |
| Kết quả | Primitive, đối tượng, void, exception |
| Cache pattern | Một method nóng, nhiều method hiếm gọi, cache hit/miss |
| Tải | Một thread, nhiều thread, request bị contention |
| Input | Độ dài, tỷ lệ lỗi, số loại request, phân bố thực tế |
| Cấu hình runtime | Cold start, warmup lâu, kích thước heap, GC và JDK |

Không đánh đồng benchmark `parseOrder` với workload có I/O; nó vẫn là tác vụ CPU/chuỗi. Với DB/network hoặc service thực tế, nên **profile và load test end-to-end**, lấy p50/p95/p99 latency, throughput, allocation và CPU. Microbenchmark không thay thế kiểm chứng hệ thống dưới tải.

### Tỷ trọng overhead

Giả sử **chỉ để minh họa phép tính**, chi phí tăng thêm do cơ chế gọi là 100 ns:

| Chi phí target | Overhead thêm | Tỷ lệ tăng tương đối |
| ---: | ---: | ---: |
| 100 ns | 100 ns | 100% |
| 1.000.000 ns (1 ms) | 100 ns | 0,01% |

Công thức minh họa: `overhead / target time × 100%`. Đây **không phải số đo thật** về `Method.invoke`. Bài học là cùng một chi phí cố định có thể rất quan trọng ở target cực nhỏ và gần như không đáng kể khi target nặng; phải đo production workload mới kết luận được.

## 8. Cache Method: quyết định dựa trên dữ liệu

Cache `Method` giúp tránh lặp lại tra cứu metadata nếu cùng chữ ký được dùng thường xuyên. Nhưng caching có chi phí bộ nhớ, khởi tạo, lookup key và vòng đời.

Khi quyết định cache, hãy kiểm tra:

1. **Cache hit ratio**: nếu đa số request gọi lại một số ít method, lợi ích lookup có thể đáng kể.
2. **Key đầy đủ**: phải phân biệt class, method name, danh sách kiểu tham số (overload), và ngữ cảnh class loader nếu liên quan. Chỉ key theo tên method là không đủ.
3. **Scope cache**: instance, class loader hay toàn application? Tham chiếu mạnh tới `Class`/`Method` có thể cản trở class unloading khi ứng dụng nạp module động.
4. **Thread safety**: việc đọc/ghi cache có tạo contention không?
5. **Kích thước và eviction**: cache vô hạn cho nhiều class/method có thể gây tăng heap.
6. **Profile thực tế**: có chắc lookup đang chiếm thời gian đáng kể, hay toàn request bị chi phối bởi parse/network/DB?
7. **Đo tách biệt**: benchmark direct, cached invoke, lookup+invoke và full pipeline trước/sau cache.

`ClassValue` có thể hữu ích khi dữ liệu cache gắn với vòng đời của từng `Class`. Với class loader động, tránh xây cache toàn cục giữ mãi strong reference mà không có chính sách vòng đời.

Nếu muốn so sánh thêm `MethodHandle`, hãy chuẩn bị handle và adapter trước phép đo khi thí nghiệm chỉ quan tâm invocation. Không kết luận `MethodHandle` luôn nhanh hơn từ tên API; chữ ký, call-site type, inlining và cách xây adapter đều ảnh hưởng kết quả.

## 9. Cách đọc kết quả và báo cáo

Một báo cáo kỹ thuật nên chứa:

- **Câu hỏi**: cached `Method.invoke` so với direct trong workload nào?
- **Môi trường**: JDK vendor/version, flags, CPU, OS, cấu hình GC/heap.
- **Dữ liệu**: số lượng và phân bố input, phương thức được benchmark, kiểu tham số/return.
- **Thiết lập đo**: warmup, measurement iterations, số fork, số thread, benchmark mode.
- **Kết quả**: score, đơn vị, sai số/độ phân tán, các mẫu bất thường, checksum hoặc kiểm tra chức năng.
- **Giới hạn**: thiếu I/O, dataset không đại diện, case cold start, cache miss hoặc mô hình concurrency chưa được đo.

Các đại lượng không nên nhầm:

| Đại lượng | Cách hiểu |
| --- | --- |
| `ns/op` | Số nanosecond trung bình cho một operation; thấp hơn thường tốt |
| `ops/s` | Throughput; cao hơn thường tốt |
| Error/độ lệch | Độ bất định của kết quả; chênh lệch nhỏ có thể không đáng tin |
| `p50/p95/p99` | Phân vị độ trễ request; quan trọng khi đánh giá tail latency |
| Allocation/GC | Thông tin về cấp phát và dừng GC có thể làm thay đổi độ trễ |

Đừng lấy một mẫu nhanh nhất rồi công bố thành tốc độ “chuẩn”. Nếu confidence/error giữa direct và reflection chồng lấn đáng kể, cần tăng số phép đo hoặc kết luận rằng khác biệt chưa được xác định chắc chắn.

## 10. Lỗi phổ biến

1. **Đo không warmup**, nhưng báo số liệu như steady-state.
2. **Đo lookup + invoke** rồi gán chênh lệch cho riêng `Method.invoke`.
3. **Direct làm ít việc hơn reflection**, ví dụ một bên parse dữ liệu, bên kia đã có tham số kiểu đúng.
4. **Không dùng kết quả**, khiến JIT có thể loại bỏ công việc.
5. **Input quá đơn điệu**, làm compiler đơn giản hóa vòng lặp hơn ứng dụng thật.
6. **Bỏ qua boxing/unboxing hoặc allocation** khi giải thích khác biệt.
7. **Đưa in kết quả hoặc logging vào vòng đo** nhưng không có ý định đo chính logging.
8. **Chạy chỉ một lần, trên một JVM**, rồi kết luận tỉ lệ cố định cho mọi môi trường.
9. **Nhìn mỗi ns/op tiny**, bỏ qua latency/throughput của request có target thật.
10. **Cache mọi metadata vô hạn**, gây tăng memory hoặc giữ class loader không cần thiết.
11. **So sánh JMH modes khác nhau** mà không kiểm tra đơn vị, số thread và kết quả.
12. **Benchmark chỉ đường thành công**, không kiểm tra input bất hợp lệ, exception hoặc tỷ lệ cache miss khi chúng xuất hiện nhiều trong production.

## 11. Tự kiểm tra

**Câu 1.** `service.getClass().getMethod("work").invoke(service)` trong vòng lặp có là phép đo overhead thuần của `Method.invoke` không?

Không. Mỗi lượt bao gồm tra cứu method. Nếu cần cached invocation, hãy tạo `Method` trước vòng đo.

**Câu 2.** Tại sao warmup cả direct và reflection?

Mỗi đường có JIT profile khác nhau; warmup một phía có thể làm sai so sánh trạng thái ổn định.

**Câu 3.** Nếu thấy direct tiny chỉ khoảng 0,2 ns/op, có nên tuyên bố đây là chi phí mọi lời gọi Java trực tiếp?

Không. JIT có thể inline, tối ưu loop hoặc constant folding. Con số mô tả mã benchmark được tối ưu dưới điều kiện cụ thể, không mặc nhiên đại diện mọi request.

**Câu 4.** Vì sao checksum cần khớp?

Nếu hai đường cho kết quả khác nhau, có thể chúng đang thực hiện lượng công việc hoặc logic khác nhau, khiến kết quả tốc độ không có ý nghĩa.

**Câu 5.** Workload mục tiêu chạy 5 ms do I/O, benchmark một method trả `int` có đủ để quyết định thay reflection không?

Không. Phải đo overhead trong pipeline thực tế; network, DB, GC và queueing có thể chi phối độ trễ.

**Câu 6.** JMH có thay thế profiling và load test không?

Không. JMH đo một phép microbenchmark đã định nghĩa tốt; profiling tìm điểm nghẽn, còn load test đánh giá end-to-end latency/throughput và contention.

**Bài tập:** thêm phép đo lookup riêng, thay số lượng method nóng và tỷ lệ cache hit; sau đó chạy JMH trên các JDK mục tiêu. Chỉ đề xuất cache hoặc thay API khi số liệu mới phản ánh workload thực tế.

## 12. Điểm cần nhớ

Một benchmark Reflection đáng tin phải có **baseline trực tiếp**, **cùng input/cùng kết quả**, **warmup**, **cache metadata khi đo cached invocation**, **nhiều mẫu/fork** và **workload đại diện**. Benchmark phép tính nhỏ giúp nhận ra overhead của lời gọi; benchmark nghiệp vụ thật mới giúp quyết định tối ưu có đáng hay không. Với kết luận quan trọng, dùng JMH và ghi rõ toàn bộ ngữ cảnh phép đo.

Tài liệu chính thức:

- [OpenJDK JMH](https://openjdk.org/projects/code-tools/jmh/)
- [Mã nguồn JMH](https://github.com/openjdk/jmh)
- [Method.invoke — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html#invoke(java.lang.Object,java.lang.Object...))
- [System.nanoTime — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#nanoTime())
# Đo sau khi làm nóng, kiểm tra kết quả và chi phí bộ nhớ

Vector API có thể biểu diễn phép tính SIMD, nhưng viết mã vector chưa đủ để kết luận chương trình nhanh hơn. HotSpot cần thời gian chạy để thu thập profile và biên dịch mã nóng; hiệu năng còn phụ thuộc kích thước dữ liệu, cache, băng thông bộ nhớ, CPU và cách xử lý phần tử dư. Vì vậy, cần đo sau warmup, kiểm tra kết quả trước khi benchmark và tách chi phí tính toán khỏi chi phí cấp phát bộ nhớ.

Trong JDK 26, Vector API là **JEP 529 — Eleventh Incubator**; JDK 27 tiếp tục là **JEP 537 — Twelfth Incubator**. API vẫn nằm trong module `jdk.incubator.vector`. Bài này dùng JMH để so sánh một vòng lặp scalar với Vector API, kiểm tra kết quả và quan sát allocation/GC. Đây là phương pháp đo có thể áp dụng cho các JDK hiện hành, đồng thời giữ đúng trạng thái incubator của Vector API.

## 1. Vì sao phải warmup trước khi đo?

Java chạy trên JVM có nhiều tầng thực thi. Khi ứng dụng mới khởi động, một phần mã được thông dịch hoặc chạy ở mức tối ưu thấp. Khi một method được gọi đủ thường xuyên, JVM thu thập profile rồi có thể biên dịch method đó thành machine code tối ưu hơn bằng JIT compiler.

Nếu đo ngay từ những lần gọi đầu tiên, kết quả có thể phản ánh chi phí khởi động, thông dịch và biên dịch thay vì hiệu năng ổn định của phép tính. Một benchmark tốt cần tách:

1. **Setup:** cấp phát mảng, tạo dữ liệu đầu vào, kiểm tra kết quả. Những việc này thường không thuộc phần cần đo.
2. **Warmup:** gọi benchmark nhiều lần để JVM đạt trạng thái thực thi ổn định hơn.
3. **Measurement:** thu thập thời gian hoặc throughput sau warmup.
4. **Fork:** chạy benchmark trong các JVM process độc lập để giảm ảnh hưởng của profile, JIT state và thứ tự benchmark trước đó.

Warmup không có một số vòng cố định phù hợp với mọi chương trình. Mã càng phức tạp hoặc có nhiều nhánh/kiểu dữ liệu thì càng cần quan sát score qua các iteration. Nếu kết quả còn biến động mạnh giữa các vòng, hãy tìm nguyên nhân trước khi kết luận.

## 2. Dùng JMH thay vì tự đo bằng vòng lặp thời gian

**JMH (Java Microbenchmark Harness)** là framework chuyên dùng để đo benchmark trên JVM. JMH quản lý warmup, measurement, fork, thread, tiêu thụ kết quả và xuất thống kê. Không nên tự viết một vòng lặp `System.nanoTime()` rồi lấy thời gian trung bình làm kết luận cho phép tính nhỏ.

Các annotation thường dùng:

| Annotation | Vai trò |
| --- | --- |
| `@Benchmark` | Đánh dấu method cần đo |
| `@State(Scope.Thread)` | Cấp state riêng cho mỗi benchmark thread |
| `@Param` | Chạy cùng benchmark với nhiều kích thước/giá trị đầu vào |
| `@Setup(Level.Trial)` | Chuẩn bị dữ liệu một lần cho mỗi trial, trước warmup và measurement |
| `@Warmup` | Cấu hình các vòng làm nóng |
| `@Measurement` | Cấu hình các vòng thu thập kết quả |
| `@Fork` | Chạy benchmark trong JVM process riêng |
| `@BenchmarkMode` | Chọn kiểu đo như throughput hoặc average time |
| `@OutputTimeUnit` | Chọn đơn vị hiển thị kết quả |

JMH nên được đặt trong benchmark source set riêng hoặc module benchmark, không trộn annotation và dependency JMH vào mã production. Dự án cần `jmh-core` cùng annotation processor `jmh-generator-annprocess`; dùng phiên bản JMH tương thích với JDK và build tool của dự án. Tài liệu JMH có các sample chính thức để cấu hình Maven/Gradle và tạo executable benchmark JAR.

## 3. Tạo benchmark so sánh scalar và Vector API

Ví dụ sau đo phép nhân từng phần tử của hai mảng `float`. Cả hai phiên bản dùng cùng dữ liệu, cùng output buffer và cùng số phần tử. `@Param` cho phép kiểm tra từ mảng nhỏ đến mảng lớn để thấy ảnh hưởng của cache và memory bandwidth.

```java
package benchmarks;

import jdk.incubator.vector.FloatVector;
import jdk.incubator.vector.VectorSpecies;
import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.BenchmarkMode;
import org.openjdk.jmh.annotations.Fork;
import org.openjdk.jmh.annotations.Measurement;
import org.openjdk.jmh.annotations.Mode;
import org.openjdk.jmh.annotations.OutputTimeUnit;
import org.openjdk.jmh.annotations.Param;
import org.openjdk.jmh.annotations.Scope;
import org.openjdk.jmh.annotations.Setup;
import org.openjdk.jmh.annotations.State;
import org.openjdk.jmh.annotations.Level;
import org.openjdk.jmh.annotations.Warmup;
import org.openjdk.jmh.annotations.Threads;

import java.util.concurrent.TimeUnit;

@State(Scope.Thread)
@Threads(1)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.MICROSECONDS)
@Warmup(iterations = 5, time = 1, timeUnit = TimeUnit.SECONDS)
@Measurement(iterations = 8, time = 1, timeUnit = TimeUnit.SECONDS)
@Fork(value = 3, jvmArgsAppend = {"--add-modules=jdk.incubator.vector"})
public class MultiplyBenchmark {
    private static final VectorSpecies<Float> SPECIES =
            FloatVector.SPECIES_PREFERRED;

    @Param({"128", "4096", "65536", "1048576"})
    public int size;

    private float[] a;
    private float[] b;
    private float[] result;

    @Setup(Level.Trial)
    public void setup() {
        a = new float[size];
        b = new float[size];
        result = new float[size];

        for (int i = 0; i < size; i++) {
            a[i] = (i % 1000) * 0.25f - 100.0f;
            b[i] = (i % 97) * 0.5f + 1.0f;
        }

        // Kiểm tra tính đúng trước khi JMH bắt đầu warmup/measurement.
        float[] scalarResult = new float[size];
        float[] vectorResult = new float[size];
        scalarKernel(a, b, scalarResult);
        vectorKernel(a, b, vectorResult);

        for (int i = 0; i < size; i++) {
            if (Float.floatToIntBits(scalarResult[i])
                    != Float.floatToIntBits(vectorResult[i])) {
                throw new IllegalStateException("Mismatch at index " + i);
            }
        }
    }

    private static void scalarKernel(float[] a, float[] b, float[] out) {
        for (int i = 0; i < a.length; i++) {
            out[i] = a[i] * b[i];
        }
    }

    private static void vectorKernel(float[] a, float[] b, float[] out) {
        int i = 0;
        int upperBound = SPECIES.loopBound(a.length);

        for (; i < upperBound; i += SPECIES.length()) {
            FloatVector va = FloatVector.fromArray(SPECIES, a, i);
            FloatVector vb = FloatVector.fromArray(SPECIES, b, i);
            va.mul(vb).intoArray(out, i);
        }

        // Scalar tail cho số phần tử chưa đủ một vector.
        for (; i < a.length; i++) {
            out[i] = a[i] * b[i];
        }
    }

    @Benchmark
    public float[] scalarReuseOutput() {
        scalarKernel(a, b, result);
        return result;
    }

    @Benchmark
    public float[] vectorReuseOutput() {
        vectorKernel(a, b, result);
        return result;
    }

    @Benchmark
    public float[] scalarAllocateOutput() {
        float[] out = new float[size];
        scalarKernel(a, b, out);
        return out;
    }

    @Benchmark
    public float[] vectorAllocateOutput() {
        float[] out = new float[size];
        vectorKernel(a, b, out);
        return out;
    }
}
```

Trong ví dụ:

- `@State(Scope.Thread)` tạo dữ liệu và output riêng cho mỗi benchmark thread; không có nhiều thread cùng ghi một mảng kết quả.
- `@Threads(1)` giữ phép so sánh ở một benchmark thread. Mục tiêu là đo SIMD, không đo tăng throughput bằng cách tăng số thread.
- `@Setup(Level.Trial)` tạo dữ liệu và kiểm tra hai kernel trước khi đo. Thời gian setup không nằm trong score của benchmark method.
- `@Warmup` cho JVM năm vòng làm nóng; `@Measurement` lấy score từ tám vòng đo.
- `@Fork(3)` chạy ba JVM độc lập. Cờ `--add-modules` được thêm cho các JVM fork.
- Các method benchmark trả về output array để kết quả được JMH tiêu thụ, tránh phép tính bị loại bỏ như dead code.
- `scalarReuseOutput` và `vectorReuseOutput` tái sử dụng mảng kết quả, tập trung đo kernel.
- `scalarAllocateOutput` và `vectorAllocateOutput` cấp phát mảng mới trong mỗi invocation, đo thêm chi phí cấp phát và ghi output.

Các giá trị `@Param` là ví dụ. Hãy bổ sung kích thước phù hợp với dữ liệu production, đồng thời tránh chạy quá nhiều combination khiến thời gian benchmark tăng không cần thiết.

## 4. Kiểm tra tính đúng trước khi so sánh tốc độ

Benchmark chỉ có ý nghĩa khi hai phiên bản thực hiện cùng một công việc và cho kết quả đúng. Không nên chỉ nhìn score mà bỏ qua output.

Trong `setup()` ở ví dụ trên, hai kernel chạy trên cùng dữ liệu và kết quả được so sánh trước warmup. Phép nhân từng phần tử `float` có cùng phép toán scalar ở cả hai nhánh, nên ví dụ kiểm tra bit pattern bằng `Float.floatToIntBits`.

Với thuật toán khác, cách kiểm tra có thể cần điều chỉnh:

- Với số nguyên hoặc phép toán có kết quả xác định chính xác, so sánh từng phần tử hoặc dùng `Arrays.equals`.
- Với floating-point reduction, thứ tự phép cộng giữa scalar và vector có thể khác; dùng sai số tuyệt đối/tương đối phù hợp với miền dữ liệu và yêu cầu nghiệp vụ.
- Với dữ liệu ngẫu nhiên, dùng seed cố định để kết quả có thể tái lập; bổ sung các trường hợp biên như mảng rỗng, mảng ngắn hơn một vector, độ dài chia hết và không chia hết cho số lane.
- Kiểm tra NaN, vô cực, signed zero và overflow nếu thuật toán có thể gặp các giá trị đó.
- Kiểm tra cả input lẫn output không bị thay đổi ngoài ý muốn.

Không đặt vòng kiểm tra toàn bộ output vào trong method benchmark nếu mục tiêu là chỉ đo kernel; thao tác so sánh có thể lớn hơn chính phép tính. Dùng setup, unit test hoặc một bước validation riêng trước khi chạy JMH.

## 5. Vì sao phải đo nhiều kích thước dữ liệu?

Một benchmark với một kích thước mảng có thể dẫn đến kết luận sai. Dữ liệu nhỏ có thể nằm trọn trong cache gần CPU; dữ liệu lớn có thể bị giới hạn bởi memory bandwidth. SIMD tăng số phép toán trên mỗi lệnh, nhưng không làm RAM truyền dữ liệu nhanh hơn.

Với phép nhân hai mảng `float` và ghi một mảng kết quả, lượng dữ liệu logic tối thiểu cho mỗi phần tử là:

- Đọc `a[i]`: 4 byte.
- Đọc `b[i]`: 4 byte.
- Ghi `out[i]`: 4 byte.

Tổng cộng khoảng **12 byte cho mỗi phần tử** trước khi xét cache line, write-allocate, prefetch và các chi tiết của memory subsystem. Với 1.048.576 phần tử, ba mảng chiếm xấp xỉ 12 MiB bộ nhớ dữ liệu.

| Kích thước `size` | Bộ nhớ của 3 mảng `float` | Điều cần quan sát |
| ---: | ---: | --- |
| 128 | 1,5 KiB | Chi phí gọi method, loop và vector setup có thể đáng kể |
| 4.096 | 48 KiB | Có thể nằm trong cache gần CPU tùy phần cứng |
| 65.536 | 768 KiB | Có thể vượt L1/L2 và phụ thuộc cache cấp cao hơn |
| 1.048.576 | 12 MiB | Bắt đầu thấy rõ ảnh hưởng của cache lớn và memory bandwidth |

Các mức này chỉ là ví dụ; dung lượng cache khác nhau theo CPU. Không gắn nhãn L1/L2/L3 cho một kích thước nếu chưa kiểm tra phần cứng thực tế. Hãy chạy nhiều kích thước và quan sát nơi lợi thế vector bắt đầu xuất hiện hoặc giảm đi.

## 6. Chạy JMH đúng cách

Vì benchmark tham chiếu `jdk.incubator.vector`, module phải được phân giải khi biên dịch. Ví dụ với Maven Compiler Plugin:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <configuration>
        <compilerArgs>
            <arg>--add-modules</arg>
            <arg>jdk.incubator.vector</arg>
        </compilerArgs>
    </configuration>
</plugin>
```

Đồng thời, JMH cần annotation processor `jmh-generator-annprocess` để tạo benchmark harness. Cấu hình build phải đưa cả benchmark source set và annotation processor vào quá trình biên dịch.

Sau khi build ra executable benchmark JAR, chạy trên JDK 26 hoặc 27:

```bash
java --add-modules jdk.incubator.vector \
     -jar target/benchmarks.jar '.*MultiplyBenchmark.*' \
     -p size=128,4096,65536,1048576
```

Trong ví dụ, `@Warmup`, `@Measurement`, `@Fork` đã cấu hình trên class. `java --add-modules` giúp JVM chạy JMH parent phân giải module; `jvmArgsAppend` trong `@Fork` thêm module cho các JVM con thực hiện benchmark. Nếu dùng tùy chọn dòng lệnh để thay cấu hình fork, JMH hỗ trợ `-jvmArgs` và `-jvmArgsAppend`; bảo đảm cờ module vẫn có ở forked JVM.

Vector API là incubator module, nên cần `--add-modules jdk.incubator.vector`; không cần `--enable-preview` chỉ vì dùng Vector API. Khi chuyển JDK, dùng đúng JDK cho cả compiler, JMH parent và forked JVM. JDK 26 là Eleventh Incubator, JDK 27 là Twelfth Incubator; biên dịch lại trên JDK đích trước khi so sánh.

## 7. Đọc score: AverageTime, Throughput và sai số

JMH có nhiều benchmark mode. Hai mode thường dùng:

| Mode | Kết quả | Cách diễn giải |
| --- | --- | --- |
| `Mode.AverageTime` | Thời gian trung bình mỗi invocation | Số càng thấp thường càng tốt |
| `Mode.Throughput` | Số invocation hoàn thành trong một đơn vị thời gian | Số càng cao thường càng tốt |
| `Mode.SampleTime` | Phân phối thời gian các invocation được lấy mẫu | Hữu ích khi quan tâm tail latency |

Ví dụ trên dùng `AverageTime` với đơn vị microsecond. Mỗi invocation xử lý một mảng; score là thời gian của cả mảng, không phải thời gian của một phần tử. Khi so sánh các kích thước khác nhau, phải đọc cột `size` cùng score.

JMH hiển thị số lần đo (`Cnt`), score và error. Không nên chỉ so hai con số trung bình rồi tuyên bố vector nhanh hơn. Hãy xem độ biến động, khoảng sai số, sự nhất quán giữa các fork và mức chênh lệch có ý nghĩa thực tế hay không. Nếu score scalar/vector gần nhau hơn nhiễu đo, chưa có bằng chứng rõ rằng Vector API cải thiện workload đó.

Có thể đổi mode khi chạy:

```bash
java --add-modules jdk.incubator.vector \
     -jar target/benchmarks.jar '.*MultiplyBenchmark.*' \
     -bm thrpt -p size=65536,1048576
```

Throughput của benchmark này là số mảng xử lý mỗi đơn vị thời gian. Muốn suy ra số phần tử/giây, nhân throughput với `size`, đồng thời ghi rõ kích thước đang xét. Không so throughput của hai benchmark nếu chúng thực hiện lượng công việc khác nhau.

## 8. Đo allocation và chi phí GC

Phép tính vector không nhất thiết cấp phát một object Java cho mỗi vector operation; các vector value thường được JIT biểu diễn bằng vector registers hoặc scalar values tùy implementation. Tuy nhiên, chương trình vẫn có thể cấp phát mảng kết quả, wrapper, object trung gian hoặc cấu trúc dữ liệu khác.

Trong benchmark ở trên, hai method `*ReuseOutput` tái sử dụng `result`, còn hai method `*AllocateOutput` tạo `new float[size]` cho mỗi invocation. Chạy GC profiler:

```bash
java --add-modules jdk.incubator.vector \
     -jar target/benchmarks.jar '.*MultiplyBenchmark.*AllocateOutput' \
     -prof gc
```

Các metric cần chú ý:

| Metric | Ý nghĩa |
| --- | --- |
| `gc.alloc.rate` | Tốc độ cấp phát, thường hiển thị MB/giây |
| `gc.alloc.rate.norm` | Lượng cấp phát chuẩn hóa trên mỗi operation, thường là B/op |
| `gc.count` | Số lần GC trong thời gian đo |
| `gc.time` | Tổng thời gian dành cho GC |

`gc.alloc.rate.norm` đặc biệt hữu ích khi so sánh hai cách triển khai vì nó thể hiện số byte cấp phát cho một invocation. `gc.alloc.rate` còn phụ thuộc tốc độ benchmark: cùng số byte/op nhưng benchmark nhanh hơn sẽ có MB/s cao hơn.

Nếu mục tiêu là đo riêng chi phí phép tính, dùng các method reuse output. Nếu muốn đo chi phí end-to-end của một thao tác thực tế có cấp phát kết quả, dùng các method allocate output. Không trộn hai câu hỏi này thành một score duy nhất.

## 9. Phân biệt chi phí tính toán, cấp phát và memory bandwidth

Một benchmark vector có thể nhanh hơn ở mảng nhỏ nhưng không cải thiện nhiều ở mảng lớn. Một số nguyên nhân:

- **Compute-bound:** phép tính số học chiếm phần lớn thời gian; SIMD có thể tăng số phép tính trên mỗi lệnh.
- **Memory-bound:** thời gian chủ yếu dùng để nạp/ghi dữ liệu; tăng vector width không làm băng thông bộ nhớ tăng tương ứng.
- **Allocation-bound:** cấp phát mảng/object và GC chiếm phần đáng kể; tối ưu phép nhân có thể không thay đổi tổng thời gian nhiều.
- **Cache-bound:** dữ liệu thường xuyên nằm trong cache thì kết quả khác so với khi phải lấy từ RAM.
- **JIT/code-shape-bound:** JIT có thể tự vector hóa vòng lặp scalar hoặc không sinh được vector instruction cho một shape/operation cụ thể.

Để tách nguyên nhân, chạy ít nhất các phép đo sau:

1. Reuse output để đo kernel, không tính cấp phát output.
2. Allocate output để đo cả cấp phát và phép tính.
3. Dùng `-prof gc` để xem allocation/GC.
4. Chạy nhiều kích thước dữ liệu để quan sát cache và memory bandwidth.
5. Nếu cần hiểu code thực thi, dùng profiler phù hợp hoặc xem assembly do JIT sinh ra trên đúng CPU/JDK; đừng chỉ suy luận từ source code.

Đừng ép GC giữa mỗi iteration chỉ để score ổn định. `-gc` của JMH có thể làm thay đổi hành vi GC tự nhiên và ảnh hưởng kết quả. Chỉ dùng khi có giả thuyết đo cụ thể, sau đó đối chiếu với phép đo mặc định.

## 10. Những lỗi benchmark thường gặp

| Lỗi | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Đo ngay từ lần gọi đầu | Bao gồm interpreter/JIT warmup | Dùng warmup iteration đủ dài và xem score qua từng iteration |
| Không dùng fork | Benchmark bị ảnh hưởng bởi JIT/profile hoặc benchmark chạy trước | Dùng nhiều fork JVM độc lập |
| Không tiêu thụ kết quả | JIT có thể loại bỏ phép tính không quan sát được | Trả kết quả hoặc dùng `Blackhole` theo hướng dẫn JMH |
| Tạo dữ liệu trong method benchmark | Đo cả setup/random generation thay vì kernel | Chuẩn bị dữ liệu ở `@Setup(Level.Trial)` |
| Scalar và vector xử lý dữ liệu khác nhau | So sánh không công bằng | Dùng cùng input, cùng kích thước, cùng output semantics |
| Chỉ benchmark một kích thước | Không thấy ảnh hưởng cache/memory | Dùng `@Param` nhiều kích thước đại diện |
| Không kiểm tra kết quả | Có thể đo một thuật toán sai hoặc bỏ sót phần tử cuối | Validate trước benchmark và có unit tests |
| Chỉ nhìn một score | Bỏ qua sai số và biến động giữa fork | Xem score, error, Cnt và kết quả lặp lại |
| Trộn allocation với kernel | Không biết cải thiện đến từ phép tính hay cấp phát | Đo riêng reuse output và allocate output |
| Tăng benchmark thread khi muốn đo SIMD | Trộn hiệu quả SIMD với concurrency và tranh chấp bộ nhớ | Bắt đầu bằng một thread; đo scaling riêng nếu cần |
| Dùng `System.nanoTime()` trong vòng lặp thủ công | Timer, JIT và dead-code elimination gây sai lệch | Dùng JMH và tuân theo sample chính thức |

## 11. Cách kết luận từ một lần đo

Một báo cáo benchmark nên ghi lại tối thiểu:

- Phiên bản JDK, vendor/build và cờ JVM.
- CPU model, kiến trúc, số core, hệ điều hành và cấu hình nguồn điện nếu có thể ảnh hưởng xung nhịp.
- Kích thước dữ liệu, kiểu phần tử, số byte đọc/ghi và cách khởi tạo dữ liệu.
- JMH version, benchmark mode, warmup, measurement, số fork và số thread.
- Scalar baseline, Vector API variant, species được chọn và cách xử lý tail.
- Score cùng sai số, allocation B/op, GC count/time nếu đo bộ nhớ.
- Kết quả correctness và cách xác minh.

Ví dụ kết luận tốt: “Với JDK 26 trên CPU X, mảng 65.536 phần tử, Vector API giảm average time so với scalar baseline trong ba fork; mảng 128 phần tử không có lợi ích rõ ràng. `gc.alloc.rate.norm` tương đương khi reuse output. Kết quả chỉ áp dụng cho workload và cấu hình đã ghi.” Không kết luận rằng Vector API luôn nhanh hơn trên mọi CPU hoặc mọi kích thước dữ liệu.

## 12. Trạng thái và tính ổn định của Vector API

Vector API là incubator module, không phải preview feature. Trong JDK 26, module là JEP 529 — Eleventh Incubator; JDK 27 là JEP 537 — Twelfth Incubator. Vì vậy:

- Thêm module bằng `--add-modules jdk.incubator.vector` ở compile time và runtime.
- Không cần `--enable-preview` chỉ vì sử dụng Vector API.
- Dùng đúng JDK cho compile, JMH parent và forked JVM.
- Khi nâng JDK, đọc lại JEP/API Specification, biên dịch và chạy correctness test/benchmark lại.
- Không để kiểu incubator trở thành hợp đồng public của thư viện dài hạn nếu không kiểm soát được phiên bản JDK.

## Ghi nhớ

- Warmup cho JVM thời gian thu thập profile và JIT compile; measurement mới là các vòng dùng để tính score.
- Dùng JMH, nhiều fork và nhiều iteration; tránh tự đo microbenchmark bằng `System.nanoTime()`.
- Kiểm tra correctness trước benchmark, giữ cùng input và semantics cho scalar/vector.
- Đo nhiều kích thước để thấy ảnh hưởng của cache, memory bandwidth và overhead.
- Tách benchmark reuse output khỏi benchmark allocate output để phân biệt kernel với allocation.
- Dùng `-prof gc` và xem `gc.alloc.rate.norm` để đo byte cấp phát trên mỗi operation.
- Trả kết quả hoặc dùng Blackhole để tránh dead-code elimination.
- Vector API vẫn incubator: JDK 26 JEP 529, JDK 27 JEP 537; cần `--add-modules`, không cần preview flag.

## Tài liệu tham khảo

- [OpenJDK JMH project](https://openjdk.org/projects/code-tools/jmh/) — framework benchmark và hướng dẫn sử dụng.
- [JMH Samples](https://github.com/openjdk/jmh/tree/master/jmh-samples/src/main/java/org/openjdk/jmh/samples) — ví dụ chính thức về warmup, state, fork, blackhole và profiler.
- [JMH Sample 09 — Blackholes](https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_09_Blackholes.java) — cách giữ kết quả benchmark không bị loại bỏ.
- [JMH Sample 35 — Profilers](https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_35_Profilers.java) — đọc `gc.alloc.rate.norm`, allocation và GC metrics.
- [JMH Command Line Options, JMH Core API](https://javadoc.io/doc/org.openjdk.jmh/jmh-core/latest/org/openjdk/jmh/runner/options/CommandLineOptions.html) — `-wi`, `-i`, `-f`, `-jvmArgs` và `-jvmArgsAppend`.
- [JEP 529 — Vector API (Eleventh Incubator)](https://openjdk.org/jeps/529) và [JEP 537 — Vector API (Twelfth Incubator)](https://openjdk.org/jeps/537) — trạng thái incubator trong JDK 26/27.
- [Package `jdk.incubator.vector`, Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.incubator.vector/jdk/incubator/vector/package-summary.html) — scalar tail, preferred species và performance notes.
- [Vector, Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.incubator.vector/jdk/incubator/vector/Vector.html) — khả năng SIMD và giới hạn phần cứng.

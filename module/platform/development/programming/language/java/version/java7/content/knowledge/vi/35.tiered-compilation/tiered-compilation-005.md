# Tác động của quá trình làm nóng (warm-up) tới phép đo hiệu năng khi dùng JIT phân tầng

## 1. Câu hỏi thực tế: tại sao cùng một đoạn Java chạy lần đầu chậm hơn?

Bạn chạy một hàm Java nhiều lần, đo bằng `System.nanoTime()` và nhận thấy những lượt đầu có thể chậm hơn các lượt sau. Đôi khi thời gian lại tăng vọt giữa chừng, thậm chí lượt sau chậm hơn lượt trước. Điều đó **không đủ để kết luận hàm đã tối ưu hoặc có regression**: JVM HotSpot thay đổi chiến lược thực thi trong lúc chương trình hoạt động.

Trong JDK hiện đại, **tiered compilation** kết hợp interpreter, compiler C1 và compiler tối ưu C2 để cân bằng khởi động nhanh với hiệu năng khi chạy lâu. JVM có thể thu thập hồ sơ thực thi (*profile*), biên dịch phương thức nóng, biên dịch lại lên tier khác, thay mã đã biên dịch hoặc **deoptimize** để trở về đường thực thi an toàn khi một giả định tối ưu không còn đúng. Đồng thời, class loading, cache, garbage collection (GC), JIT background threads, CPU scheduling và I/O cũng ảnh hưởng thời gian đo.

**Warm-up** là giai đoạn thực hiện workload trước khi lấy số liệu nhằm giảm tác động của các công việc khởi tạo, thu thập profile và compilation ban đầu. Không có một “số lượt warm-up chuẩn” dùng được cho mọi method, JVM, thiết bị hoặc workload.

Bài này giúp bạn:
- Giải thích warm-up ảnh hưởng thế nào đến kết quả đo **thời gian, throughput và độ ổn định**.
- Nhận biết các tier biên dịch trong HotSpot và lý do hiệu năng không tăng tuyến tính theo số lượt gọi.
- Viết thí nghiệm Java 17+ quan sát số liệu động nhưng **không nhầm demo với benchmark đáng tin**.
- Thiết kế phép đo steady-state bằng **JMH**, tách warm-up/measurement/fork và chống dead-code elimination.
- Phân biệt yêu cầu **cold-start latency** với **steady-state throughput/latency** khi đưa ra quyết định hiệu năng thực tế.

**Phạm vi:** đây là kiến thức áp dụng cho HotSpot/JDK hiện đại, không dùng bộ quy tắc đo lường theo một phiên bản Java cũ. Tiered compilation xuất hiện từ Java 7 nhưng tiếp tục tiến hóa; các mức/tùy chọn HotSpot ở đây là chi tiết triển khai, không phải hợp đồng bắt buộc của mọi Java Virtual Machine.

## 2. HotSpot JIT phân tầng thay đổi trạng thái thực thi như thế nào?

HotSpot có các mức tối ưu hóa thông dụng:

| Level | Cơ chế | Ý nghĩa với phép đo |
| --- | --- | --- |
| 0 | Interpreter | Bytecode được thực thi với thông tin profiling cơ bản; lời gọi ban đầu có thể mang chi phí chưa được tối ưu. |
| 1 | C1, ít hoặc không thu thập profile | Có native code nhanh được tạo sớm cho một số phương thức, ví dụ phương thức nhỏ. |
| 2 | C1 với profiling giới hạn | Cân bằng chi phí profiling và tốc độ; **không phải mọi phương thức đều đi qua level này**. |
| 3 | C1 với profiling đầy đủ | Thu thập thông tin kiểu, nhánh và tần suất để compiler tối ưu sử dụng. |
| 4 | C2 tối ưu sâu | Có thể inline, tối ưu vòng lặp, loại tính toán không cần, khai thác profile; thường hướng tới throughput lâu dài. |

Đây là **mô hình khái quát** của HotSpot: một method có thể đi thẳng từ interpreter tới một tier thích hợp, được giữ ở C1, được biên dịch theo *on-stack replacement* (OSR) cho vòng lặp nóng, hoặc không cần lên level 4. Không thể dùng số lần gọi `N` cố định để suy ra chắc chắn tier hiện tại.

Dòng thời gian thường gặp:

~~~text
JVM khởi động
   |
   v
Class loading / initialization -> Interpreter (L0)
   |                               |
   |                     Thu thập invocation/branch/type profile
   |                               |
   +------------------> C1 native code (L1/L2/L3)
                                   |
                            Hot code + profile
                                   |
                                   v
                             C2 native code (L4)
                                   |
                    Profile assumption mất hiệu lực?
                         /                     \
                       Có                      Không
                       |                        |
             Deoptimization/recompile       Tiếp tục chạy
                       |
                 Tăng hoặc đổi latency tạm thời
~~~

Một phép đo được lấy ở giai đoạn L0/C1 có thể khác hẳn phép đo sau C2. Nếu profile ban đầu chỉ có một kiểu dữ liệu, JVM có thể inline một đường gọi cụ thể; khi workload sau đó đưa vào kiểu mới, giả định trở nên sai và JVM phải deoptimize. Vì vậy **làm nóng bằng dữ liệu không đại diện có thể làm méo kết quả**, ngay cả khi đã warm-up hàng chục nghìn lượt.

### Những thành phần dễ bị nhầm là “chỉ do JIT”

- **Class loading, verification, linking, static initialization:** lần đầu truy cập lớp hoặc endpoint có thể kích hoạt tải và khởi tạo; thời gian này không đồng nghĩa chi phí của JIT.
- **Framework initialization:** dependency injection, ORM mappings, serializer, proxy/lazy initialization, DNS hoặc TLS handshakes có thể làm lượt đầu chậm.
- **CPU instruction/data caches và branch predictor:** nhiều lượt chạy cùng dữ liệu có thể nhanh hơn vì cache nóng. Một benchmark “hot cache” khác với luồng nghiệp vụ đọc dữ liệu thay đổi.
- **GC và allocation:** đối tượng được cấp phát trong warm-up làm thay đổi heap occupancy và thời điểm GC của phần measurement.
- **OS scheduling/CPU frequency/thermal throttling/container quota:** cùng bytecode nhưng tốc độ vẫn biến thiên.
- **Code cache và compiler threads:** background compilation tiêu tốn CPU; code cache đầy hoặc compiler đang bận cũng ảnh hưởng việc chuyển tier.

Do đó **warm-up là nhiều hiệu ứng chồng nhau**, không phải công tắc “bật JIT xong là ổn định”.

## 3. Warm-up gây sai lệch cho phép đo ra sao?

### 3.1. Trộn cold và hot làm trung bình thiếu ý nghĩa

Giả sử một workload có thời gian xử lý (chỉ để minh họa):

| Lượt | Thời gian |
| --- | ---: |
| 1 | 12 ms |
| 2 | 8 ms |
| 3 | 5 ms |
| 4 | 2 ms |
| 5 | 2 ms |

Trung bình cả năm lượt = **5,8 ms**, trong khi trung bình hai lượt cuối = **2 ms**. Kết luận nào đúng phụ thuộc **đối tượng cần đo**:

- Nếu đánh giá **độ trễ lần đầu**, không được bỏ lượt 1; dùng thước đo cold-start cụ thể.
- Nếu đánh giá **steady-state service**, có thể coi các lượt đầu là warm-up và đo sau khi hệ thống đạt trạng thái đại diện.
- Nếu workload thật thường xuyên scale-to-zero, restart hoặc có nhiều endpoint ít được truy cập, coi tất cả là steady-state có thể đánh giá quá tốt.

Cả 5,8 ms lẫn 2 ms ở ví dụ đều không cho biết mức phân tán, p95/p99, GC pauses hoặc throughput khi đồng thời phục vụ nhiều request.

### 3.2. Warm-up quá ít

JIT compilation chưa hoàn tất, class/load còn diễn ra, các cache còn lạnh. Dữ liệu measurement thường có xu hướng giảm theo thời gian. Hai phiên bản được so sánh có thể được lấy ở **hai trạng thái JVM khác nhau**: bản A đã tới C2, bản B còn ở C1. Khi đó chênh lệch đo không đại diện cho chênh lệch thuật toán.

### 3.3. Warm-up quá nhiều hoặc không đại diện

Nếu warm-up liên tục trên cùng một mảng nhỏ, dữ liệu có thể luôn ở CPU cache, profile nhánh/kiểu lệch so với thực tế và GC behavior khác workload production. Nếu warm-up bị tính vào thời gian sử dụng tài nguyên tổng thể hoặc tạo nhiều retained objects, nó có thể làm measurement sau đó tốn nhiều CPU/GC hơn.

**Không chọn số lượt dựa trên cảm tính.** Hãy quan sát tiến triển của các lần đo, JIT/GC events, và so sánh mức ổn định qua **nhiều tiến trình JVM độc lập**.

### 3.4. Một plateau không chắc là tối ưu cuối

Một giai đoạn chạy ổn định ngắn có thể vẫn là code C1; C2 xuất hiện muộn làm kết quả đổi lần nữa. JIT có thể deoptimize khi dữ liệu khác profile hoặc heap/CPU thay đổi. Vì vậy chỉ nhìn “ba lượt cuối giống nhau” chưa đủ để khẳng định benchmark đã đạt steady-state cho mọi đầu vào.

## 4. Demo Java 17+: quan sát các lượt đo liên tiếp

Ví dụ này được thiết kế để **quan sát tác động của warm-up**, không dùng để tuyên bố phương pháp A nhanh hơn B trong sản xuất. Mỗi lượt chạy cùng workload trên một mảng có dữ liệu khởi tạo từ code; kết quả được sử dụng qua biến `volatile` để hạn chế benchmark bị loại bỏ hoàn toàn. Thời gian đo từng lượt vẫn chịu JIT, OS, cache và GC.

**Tệp `JitWarmupDemo.java`:**

~~~java
import java.util.Locale;

public final class JitWarmupDemo {
    private static final int[] DATA = new int[4096];
    private static volatile long sink;

    static {
        for (int i = 0; i < DATA.length; i++) {
            DATA[i] = (i * 31 + 7) & 1023;
        }
    }

    private static long compute(int salt) {
        long total = 0;
        for (int value : DATA) {
            total += Integer.rotateLeft(value ^ salt, salt & 15);
        }
        return total;
    }

    private static long runBatch() {
        long total = 0;
        for (int i = 0; i < 4_000; i++) {
            total += compute(i & 31);
        }
        return total;
    }

    public static void main(String[] args) {
        long previous = Long.MIN_VALUE;
        boolean consistent = true;

        for (int round = 1; round <= 8; round++) {
            long start = System.nanoTime();
            long result = runBatch();
            long elapsed = System.nanoTime() - start;

            sink = result;
            if (round > 1 && result != previous) {
                consistent = false;
            }
            previous = result;

            System.out.printf(Locale.ROOT, "Round %d: %.3f ms%n",
                    round, elapsed / 1_000_000.0);
        }

        System.out.println("Results equal: " + consistent);
        System.out.println("Checksum: " + sink);
    }
}
~~~

Biên dịch và chạy với JDK 17+:

~~~bash
javac -encoding UTF-8 JitWarmupDemo.java
java JitWarmupDemo
~~~

Dạng kết quả thường thấy (các số đo thời gian dưới đây **chỉ minh họa**, luôn lấy từ máy của bạn):

~~~text
Round 1: 50.000 ms
Round 2: 20.000 ms
Round 3: 13.000 ms
Round 4: 12.000 ms
Round 5: 12.000 ms
Round 6: 13.000 ms
Round 7: 12.000 ms
Round 8: 12.000 ms
Results equal: true
Checksum: <giá trị số cố định do chương trình tính>
~~~

Dòng `Results equal: true` dự kiến ổn định nếu không sửa input; **thời gian không có bảo đảm tăng/giảm đơn điệu**. Dòng checksum phụ thuộc tính toán của ví dụ và được in ra khi chạy, không sử dụng placeholder này như stdout chính xác của chương trình trong báo cáo tự động.

Vì sao không coi đây là benchmark chính thức?

- Mỗi lượt chỉ có một phép đo bao trùm cả batch, không có nhiều JVM forks hay khoảng tin cậy.
- JIT có thể tiếp tục biên dịch giữa các vòng. Lượt đầu có thể bao gồm khởi tạo các lớp liên quan và chi phí biên dịch.
- Mảng đầu vào giữ nguyên nên caching, branch profile và hành vi truy cập dữ liệu khác một workload thực.
- `System.nanoTime()` trả thời gian trên đồng hồ đơn điệu cho đo khoảng thời gian; phép trừ này có ý nghĩa cho **elapsed time**, không chỉ ra chính xác CPU time của riêng hàm.
- Việc ghi vào `volatile sink` giúp giữ kết quả có thể quan sát được, nhưng không giải quyết hết dead-code elimination, constant folding hoặc các tối ưu của compiler. JMH cung cấp harness tốt hơn.

**Để quan sát JIT compilation khi chạy demo:**

~~~bash
java -XX:+PrintCompilation JitWarmupDemo
~~~

Bạn sẽ thấy các dòng có tên method/level và trạng thái compilation, xen kẽ stdout của chương trình. Nội dung log phụ thuộc JDK, máy và thời điểm; đừng hard-code số lần compilation như kỳ vọng của test. Có thể redirect stdout sang file để phân tích:

~~~bash
java -XX:+PrintCompilation JitWarmupDemo > jit-compilation.log
~~~

Trong log HotSpot thường thấy các level 3/4, dấu `%` gắn với OSR hoặc chuỗi `made not entrant` khi bản mã đã biên dịch bị thay thế/vô hiệu hóa. Đừng diễn giải một dấu “not entrant” đơn độc như lỗi ứng dụng hay kết luận rằng mỗi lần thay mã đều là deoptimization; phải đặt trong bối cảnh compilation và workload.

## 5. Dùng JMH để đo steady-state đúng cách

**JMH (Java Microbenchmark Harness)** của OpenJDK được thiết kế cho microbenchmark JVM. Nó cung cấp warm-up iterations, measurement iterations, nhiều process forks, harness sử dụng kết quả và cơ chế state/setup nhằm giảm các lỗi đo phổ biến. JMH không bảo đảm benchmark tự động đúng nếu workload hoặc dữ liệu thiết kế sai; phải chọn đúng thứ cần đo.

Các khái niệm:

| Cơ chế JMH | Tác dụng | Sai lầm nếu bỏ qua |
| --- | --- | --- |
| `@Warmup` | Chạy benchmark trước measurement trong cùng fork; mặc định không tính vào score. | Vô tình tính startup/JIT ban đầu vào số steady-state. |
| `@Measurement` | Chỉ định số iteration và thời lượng mỗi iteration để lấy số liệu. | Chỉ lấy một mẫu rất nhiễu. |
| `@Fork` | Chạy trong những JVM process độc lập; mỗi fork có warm-up và measurement riêng. | Kết quả của benchmark trước làm thay đổi profile/JIT/heap của benchmark sau. |
| `@State` | Quản lý dữ liệu benchmark, tách setup khỏi phần cần đo. | Tính luôn thời gian chuẩn bị input không mong muốn. |
| `@Setup(Level.Trial/Iteration)` | Chuẩn bị dữ liệu theo mức phù hợp. | State cũ thay đổi qua các lượt và workload trở nên khác nhau. |
| `@Benchmark` và giá trị trả về / `Blackhole` | Làm kết quả có thể quan sát để compiler không loại bỏ toàn bộ công việc. | Đo phần code đã bị JIT tối ưu biến mất. |
| `@Param` | Thử nhiều kích thước/hình dạng input có chủ đích. | Chỉ tối ưu cho một mảng bé nằm trong cache. |
| `@BenchmarkMode` | Chọn AverageTime, Throughput, SampleTime... theo câu hỏi. | Diễn giải nanoseconds/op như requests/s hoặc tail latency service. |

### Ví dụ JMH chuẩn cho một phép đo đã làm nóng

**Tệp `JitWarmupBenchmark.java`**, đặt trong **dự án JMH đã cấu hình dependency và annotation processor** theo hướng dẫn chính thức của OpenJDK. Đây **không phải chương trình độc lập** có thể biên dịch bằng `javac` không có thư viện JMH:

~~~java
import java.util.concurrent.TimeUnit;
import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.BenchmarkMode;
import org.openjdk.jmh.annotations.Fork;
import org.openjdk.jmh.annotations.Level;
import org.openjdk.jmh.annotations.Measurement;
import org.openjdk.jmh.annotations.Mode;
import org.openjdk.jmh.annotations.OutputTimeUnit;
import org.openjdk.jmh.annotations.Param;
import org.openjdk.jmh.annotations.Scope;
import org.openjdk.jmh.annotations.Setup;
import org.openjdk.jmh.annotations.State;
import org.openjdk.jmh.annotations.Warmup;

@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.MICROSECONDS)
@Warmup(iterations = 5, time = 1, timeUnit = TimeUnit.SECONDS)
@Measurement(iterations = 5, time = 1, timeUnit = TimeUnit.SECONDS)
@Fork(3)
public class JitWarmupBenchmark {
    @Param({"256", "4096"})
    public int size;

    private int[] data;

    @Setup(Level.Trial)
    public void setUp() {
        data = new int[size];
        for (int i = 0; i < data.length; i++) {
            data[i] = (i * 31 + 7) & 1023;
        }
    }

    @Benchmark
    public long sumSquares() {
        long total = 0;
        for (int value : data) {
            total += (long) value * value;
        }
        return total;
    }
}
~~~

Cách sử dụng khi dự án JMH đã tạo được `target/benchmarks.jar` theo hướng dẫn chính thức:

~~~bash
java -jar target/benchmarks.jar JitWarmupBenchmark
~~~

Hoặc truyền tham số rõ ràng:

~~~bash
java -jar target/benchmarks.jar JitWarmupBenchmark -wi 5 -w 1s -i 5 -r 1s -f 3
~~~

- `-wi 5 -w 1s`: năm warm-up iteration, mỗi iteration khoảng một giây.
- `-i 5 -r 1s`: năm measurement iteration, mỗi iteration khoảng một giây.
- `-f 3`: ba JVM forks độc lập.
- `Mode.AverageTime`: báo chi phí trung bình mỗi operation, ở đây tính bằng microsecond/op, **không phải p99 request latency**.
- `@Param` chạy với các kích thước dữ liệu khác nhau. `@Setup(Level.Trial)` tạo input trước khi đo; benchmark chỉ tính vòng lặp cộng bình phương. Giá trị trả về được JMH tiêu thụ.

**Các con số 5 iteration, 1 giây, 3 fork là cấu hình học tập**, không phải quy tắc đúng cho mọi workload. Tăng thời lượng, số fork hoặc dữ liệu nếu kết quả còn biến động; xem score từng iteration và độ phân tán. Nếu chương trình thật bị cold-start, hãy thiết kế bài đo startup riêng thay vì tăng warm-up để che đi chi phí đó.

### Lưu ý về setup và state

Nếu benchmark gọi `sort` liên tục trên cùng một mảng, lượt đầu sắp xếp dữ liệu chưa có thứ tự, còn các lượt sau sắp xếp mảng đã có thứ tự; khi đó đo **hai workload khác nhau**. Nếu mục tiêu là “sắp xếp mảng chưa sắp xếp”, cần tạo/copy/reset input theo đúng cấp `@Setup` phù hợp và xác định rõ overhead của việc copy có thuộc phần đo hay không. Tránh `@Setup(Level.Invocation)` một cách máy móc vì bản thân setup mỗi invocation có overhead và có thể phá cơ hội tối ưu như ngoài thực tế. Với phép đo có trạng thái, mô tả workload là phần quan trọng nhất của thí nghiệm.

## 6. Phân biệt mục tiêu đo: startup, ramp-up, steady-state và tail latency

| Mục tiêu | Warm-up nên xử lý thế nào? | Metric nên báo |
| --- | --- | --- |
| **Cold startup** — process vừa khởi động đến lúc sẵn sàng | **Không loại** thời gian khởi động và bước lazy initialization cần thiết. Chạy nhiều process mới. | Time-to-ready, startup CPU/RSS, độ trễ request đầu tiên. |
| **Ramp-up** — hiệu năng tăng dần khi hệ thống nóng lên | Giữ toàn bộ dòng thời gian; đừng chỉ lấy trung bình sau warm-up. | Throughput và latency theo thời gian, số giây đạt mức SLO ổn định. |
| **Steady-state microbenchmark** — hiệu năng kernel Java khi đã nóng | Dùng JMH warm-up + measurement + forks; kiểm tra ổn định thực tế. | Score trung bình hoặc throughput, phân tán và cấu hình thí nghiệm. |
| **Dịch vụ phục vụ traffic lâu dài** | Pre-warm chỉ khi production có cơ chế tương tự; chạy workload representative dưới tải thật. | Throughput, p95/p99 request latency, error rate, CPU, heap/RSS, GC. |
| **Batch job / serverless / scale-to-zero** | Không tự ý bỏ startup nếu thời gian sống thường ngắn. | End-to-end elapsed time trên process mới, chi phí warm-up/khởi tạo. |

Một endpoint có trung bình 20 µs/op trong JMH không có nghĩa ứng dụng đạt 50.000 HTTP requests/s: mạng, serialization, thread scheduling, lock, DB, queue và contention không được đo trong benchmark hàm nhỏ. Tương tự, warm-up có thể giảm latency sau khởi động nhưng **không thay thế** capacity planning cho throughput và tail latency.

## 7. Cách chứng minh chính JIT gây ra thay đổi

Nếu thấy kết quả cải thiện qua các lượt, hãy kiểm chứng giả thuyết bằng nhiều nguồn dữ liệu:

1. **In các lượt đo theo thời gian** và xem có thay đổi về mức ổn định hay không. Không chỉ so trung bình đầu/cuối, vì một GC pause có thể tạo outlier.
2. **Quan sát compilation** với `-XX:+PrintCompilation` trên một bản chạy chẩn đoán. Xem phương thức của bạn được compile ở tier nào và khi nào, nhưng lưu ý output chẩn đoán có overhead và có thể đổi timing.
3. **Thu JFR** ở một run riêng nếu cần phân tích phương thức nóng, compilation, allocation/GC và CPU; các JFR events có thể phụ thuộc cấu hình recording, nên phải kiểm tra sự kiện thực có.
4. **So sánh GC/cpu:** bật Unified JVM Logging `-Xlog:gc` hoặc JFR để phát hiện GC ngay lúc thời gian tăng. Log class loading `-Xlog:class+load=info` hữu ích khi nghi ngờ lazy initialization (có thể rất nhiều dòng).
5. **Lặp lại trong JVM mới:** mô hình “lượt đầu chậm, các lượt sau nhanh” có tái xuất hiện ở nhiều process không? Nếu chỉ một process bị chậm, có thể là OS background activity.
6. **Thử workload đại diện:** đổi kiểu đầu vào, kích thước, polymorphism, độ phân tán của nhánh hoặc tình trạng cache; nếu hiệu ứng đảo chiều, nguyên nhân có thể là profile và data locality.

Ví dụ các lệnh chẩn đoán trên Java 17+:

~~~bash
java -XX:+PrintCompilation JitWarmupDemo > jit-compilation.log
java -Xlog:gc=info JitWarmupDemo
java -Xlog:class+load=info JitWarmupDemo > class-loading.log
java -XX:StartFlightRecording=filename=warmup.jfr,settings=profile,dumponexit=true JitWarmupDemo
~~~

Chạy **từng lệnh trong một process mới**, thay vì coi chúng là cùng một process đo. Dữ liệu từ `jit-compilation.log` không phải log đo benchmark sạch vì chứa diagnostic output. File `warmup.jfr` có thể mở bằng Java Mission Control hoặc công cụ đọc JFR. Demo chạy ngắn nên số sự kiện hữu ích có thể ít; hãy chọn thời gian thí nghiệm phù hợp.

### Dấu hiệu hot compile và deoptimization

- Một method xuất hiện ở C1 tier 3 rồi C2 tier 4 thường cho thấy nó đã “nóng” đủ trong run đó, nhưng **không chứng minh** toàn bộ chương trình đã đạt steady-state.
- Biên dịch lại hoặc `made not entrant` có thể phản ánh việc thay mã đã biên dịch; muốn xác nhận deoptimization liên quan input/assumptions cần chẩn đoán sâu hơn.
- Một method vẫn ở C1 không tự động là “lỗi”: method ngắn, độ nóng, compiler load, policy và nhiều điều kiện khác ảnh hưởng tier.
- Warm-up chưa ổn khi thời gian còn thay đổi theo cùng điểm xuất hiện GC/JIT, nhưng thời gian ổn định cũng không tự chứng minh mọi compiler event đã kết thúc.

**Không tắt tiered compilation để benchmark “công bằng”** nếu production thực tế vẫn dùng nó. Cờ `-XX:-TieredCompilation` thay đổi chiến lược compiler và có thể thay đổi cả startup lẫn steady-state; chỉ dùng như một thí nghiệm chẩn đoán có mục đích, tuyệt đối không lấy kết quả đó đại diện cho cấu hình sản xuất.

## 8. Phương pháp thực nghiệm để so hai implementation

Giả sử muốn so sánh hai cách xử lý `List` hoặc hai cấu trúc dữ liệu:

1. **Định nghĩa workload**: kích thước, phân phối đầu vào, tỷ lệ đọc/ghi, độ biến thiên kiểu dữ liệu, bộ nhớ tối đa và concurrency phải giống tình huống thật.
2. **Kiểm tra tính đúng**: hai implementation phải trả cùng kết quả. Không so một hàm làm ít việc hơn với một hàm làm đầy đủ yêu cầu.
3. **Tách startup**: nếu đo cold start, bắt đầu từ JVM process mới và đo riêng; nếu đo steady-state, dùng JMH/runner có warm-up.
4. **Tránh cùng process trộn trạng thái**: dùng nhiều JMH forks; thay đổi thứ tự biến thể hoặc dùng chạy có kiểm soát để tránh bias do cache, thermal và compiler profile.
5. **Thiết lập nền như nhau**: cùng JDK vendor/build/version, JVM flags, heap/GC, CPU quota, kiến trúc máy, isolation, input và mức tải.
6. **Đo nhiều lần**: ghi từng iteration, fork và variability; điều tra outlier thay vì xóa tùy tiện.
7. **Phân tích điểm cân bằng**: kiểm tra allocation/GC, CPU và RSS nếu implementation nhanh hơn nhưng tiêu thụ bộ nhớ quá lớn; latency metric của dịch vụ mới quyết định SLO.
8. **Ghi đủ thông tin để tái hiện**: OS, CPU, JVM, benchmark version, command, dataset, thời gian warm-up/measurement, số fork và raw output.

Mẫu bảng thí nghiệm (điền số liệu **sau** khi chạy, không suy đoán):

| Biến thể | Workload | Warm-up/forks | Score steady-state | Độ biến thiên | Peak RSS/GC | Kết luận theo SLO |
| --- | --- | --- | --- | --- | --- | --- |
| A | [mô tả] | [thời gian / số fork] | [số đo] | [số đo] | [số đo] | [nhận định] |
| B | [mô tả] | [thời gian / số fork] | [số đo] | [số đo] | [số đo] | [nhận định] |

Đối với yêu cầu “mất bao lâu để ứng dụng nhanh lên?”, báo thêm đồ thị *time since startup → throughput/latency*. Benchmark steady-state không thể thay thế đường cong ramp-up.

## 9. Các sai lầm gây kết luận sai

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Gọi method đúng một lần rồi đo `nanoTime()` | Trộn class loading, interpreter, JIT, cache và OS scheduling | Đo cold-start riêng hoặc warm-up + đo nhiều iteration/forks. |
| Chạy 10.000 vòng trước khi đo và coi đó là “JIT đã xong” | Tier phụ thuộc workload, profile, compiler policy và CPU; không có ngưỡng cố định | Quan sát ổn định và JIT events; dùng JMH khi cần microbenchmark. |
| Warm-up bằng dữ liệu khác production | JIT có thể profile nhánh/kiểu khác; cache state không đại diện | Warm-up và measurement theo phân phối workload thực. |
| Benchmark hai hàm trong cùng main rồi đo liên tiếp | Tạo hiệu ứng thứ tự, JIT/cache/GC dùng chung | Tách forks, random hóa/cân bằng thứ tự khi phù hợp. |
| Không dùng kết quả phép tính | JIT có thể xóa code không tạo observable side effect | Dùng return/`Blackhole` trong JMH; đảm bảo tính đúng. |
| Tính thời gian khởi tạo dữ liệu vào benchmark hàm | Đo setup + operation ngoài ý định | Dùng `@State`/`@Setup`, định nghĩa rõ phạm vi đo. |
| Tái sử dụng đầu vào đã bị thay đổi | Lượt sau đo workload khác lượt đầu | Reset/copy dữ liệu theo đúng semantics và ghi rõ overhead. |
| Chỉ báo average sau warm-up | Có thể che tail latency/GC pauses, phân tán giữa forks | Báo variance, percentile phù hợp, raw runs, metrics dịch vụ. |
| Dựa vào JMH score để tuyên bố throughput HTTP | Không đo network, DB, thread contention hay framework | Test end-to-end với realistic load để đánh giá SLO hệ thống. |
| Tắt JIT/đổi JVM flags để xóa nhiễu rồi so với production | Đo runtime khác tình huống thật | Giữ production flags, thay đổi có kiểm soát chỉ cho chẩn đoán. |
| Dùng `Thread.sleep` như warm-up | Ngủ không thực thi hot methods, không tạo profile tương ứng | Chạy workload thật để làm nóng, theo dõi trạng thái. |
| Chọn riêng lần nhanh nhất | Loại bỏ outlier theo ý muốn gây thiên lệch | Thiết kế nhiều iteration/fork và báo phân phối kết quả. |

## 10. Checklist trước khi công bố số liệu

- [ ] Tôi biết mục tiêu là **cold startup**, **ramp-up**, **steady-state microbenchmark** hay **service end-to-end**.
- [ ] Warm-up thực thi đúng workload đại diện và không bị nhầm thành measurement nếu mục tiêu steady-state.
- [ ] JMH được dùng cho microbenchmark; state được cấu hình đúng, kết quả không bị tối ưu biến mất.
- [ ] Có nhiều fork JVM độc lập; số iteration/duration đủ để kiểm tra ổn định.
- [ ] Đã xem xét JIT compilation, deoptimization, GC, class loading, CPU cache và OS scheduling.
- [ ] Dữ liệu dùng để so sánh có cùng JDK/flags, hardware, memory/CPU quota, concurrency và input.
- [ ] Score, biến thiên và raw data được lưu; không chỉ trình bày số nhanh nhất.
- [ ] Không dùng kết quả steady-state để phủ nhận cold-start cost của ứng dụng thật.
- [ ] Nếu quyết định ảnh hưởng hệ thống, có kiểm chứng bằng throughput, p95/p99 và memory/GC ở mức ứng dụng.

## Tài liệu đối chiếu (đang có giá trị)

- [Oracle JDK 25 — Java HotSpot Virtual Machine Performance Enhancements, Tiered Compilation](https://docs.oracle.com/en/java/javase/25/vm/java-hotspot-virtual-machine-performance-enhancements.html): mục tiêu và cơ chế tiered compiler.
- [Oracle JDK 25 — The java Command, Advanced JIT Compiler Options](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): `-XX:+PrintCompilation`, `-XX:-TieredCompilation`, code cache và JVM flags.
- [OpenJDK — Java Microbenchmark Harness (JMH)](https://github.com/openjdk/jmh): cách tổ chức benchmark, annotation processing và samples.
- [OpenJDK — JMH Warmup annotation](https://github.com/openjdk/jmh/blob/master/jmh-core/src/main/java/org/openjdk/jmh/annotations/Warmup.java): số iteration/thời lượng warm-up và khả năng override.
- [Microsoft Java Engineering — How Tiered Compilation works in OpenJDK](https://devblogs.microsoft.com/java/how-tiered-compilation-works-in-openjdk/): diễn giải HotSpot C1/C2, profile và compilation policy.

**Ghi nhớ:** việc JVM đã chạy nhiều lần không tự chứng minh kết quả đo đáng tin. Muốn đo performance khi đã làm nóng, cần workload đúng, warm-up có kiểm chứng, nhiều JVM forks và metric phù hợp; muốn đo startup, phải **giữ nguyên** chi phí khởi động/JIT thay vì loại bỏ nó.
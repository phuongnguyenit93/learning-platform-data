# Warmup, JIT, GC và yếu tố gây sai lệch phép đo

Kết quả benchmark Java có thể thay đổi đáng kể giữa lúc ứng dụng vừa khởi động và lúc chạy ổn định. JVM cần nạp lớp, diễn giải bytecode, thu thập profile thực thi và biên dịch các đoạn mã nóng bằng JIT; đồng thời garbage collector (GC) xử lý các đối tượng được cấp phát trong quá trình chạy. Nếu đo quá sớm, bỏ qua GC hoặc để các yếu tố môi trường thay đổi giữa các lần chạy, con số thu được có thể không đại diện cho hiệu năng thực tế.

Khi đo hiệu năng Java 21, trước hết hãy xác định mục tiêu là **cold start** hay **steady state**. Sau đó chọn phương pháp đo phù hợp, thường là JMH cho microbenchmark và load test cho hiệu năng end-to-end. Warmup, JIT và GC là một phần của hành vi runtime; cần kiểm soát và quan sát chúng thay vì cố tình loại bỏ mọi hoạt động nền khỏi phép đo.

## 1. Phân biệt cold start và steady state

Hai câu hỏi đo hiệu năng khác nhau cần hai phương pháp khác nhau:

- **Cold start:** ứng dụng mất bao lâu từ lúc khởi chạy tiến trình đến khi sẵn sàng phục vụ? Chỉ số có thể gồm thời gian khởi động JVM, nạp lớp, khởi tạo framework, kết nối dependency và thời gian đến readiness.
- **Steady state:** sau khi ứng dụng đã chạy đủ lâu và runtime đã thích nghi với workload, mỗi thao tác mất bao lâu và hệ thống hoàn thành bao nhiêu công việc?

| Mục tiêu | Cần đo | Cách tiếp cận |
|---|---|---|
| Cold start | Thời gian process start đến readiness, thời gian khởi tạo thành phần | Khởi chạy process mới cho mỗi lần đo; không warmup trước khi lấy số liệu |
| Steady-state method performance | Thời gian hoặc throughput của một đoạn code sau khi JIT đã tối ưu | JMH với warmup, measurement iterations và nhiều fork |
| Service performance | Throughput, latency phân vị, lỗi và tài nguyên dưới tải | Load test trên service chạy lâu, có giai đoạn warmup riêng |
| Startup regression sau deploy | Thời gian khởi động cùng các bước initialization | Đo lặp lại từ process mới với cùng môi trường và cấu hình |

Không dùng warmup để đo cold start, vì làm như vậy sẽ bỏ qua chính khoảng thời gian cần đo. Ngược lại, không kết luận steady-state performance từ vài lần gọi đầu tiên sau khi JVM khởi động.

## 2. Vì sao JVM cần warmup?

Java source được biên dịch thành bytecode. Khi chạy, HotSpot JVM có thể thông dịch bytecode và biên dịch các đoạn mã thường xuyên được thực thi thành mã máy. Runtime thu thập thông tin về hành vi thực tế như kiểu đối tượng, nhánh thường được chọn, lời gọi method và tần suất thực thi để JIT có cơ sở tối ưu.

Trong giai đoạn đầu, hiệu năng có thể biến động vì:

- Lớp và dependency chưa được nạp hoặc khởi tạo.
- Bytecode được thông dịch trước khi một số method trở thành hot.
- JIT compiler đang biên dịch method hoặc loop trong khi ứng dụng vẫn chạy.
- Profile runtime còn ít dữ liệu nên tối ưu hóa chưa đạt trạng thái ổn định.
- Cache CPU, branch predictor, connection pool và cache của ứng dụng chưa có trạng thái đại diện.
- Heap và GC chưa đi vào chu kỳ hoạt động giống giai đoạn tải ổn định.

Warmup là giai đoạn chạy workload đại diện trước khi lấy số liệu chính. Mục tiêu là để JVM và ứng dụng tiến gần trạng thái cần đo, không phải chạy một số vòng lặp tùy ý cho đủ số lần.

## 3. JIT và tiered compilation trong HotSpot

HotSpot thường sử dụng **tiered compilation** để cân bằng chi phí biên dịch và hiệu năng mã máy. Tùy tần suất thực thi và profile, code có thể đi qua các mức thông dịch, biên dịch nhanh và tối ưu sâu hơn. Các mức cụ thể và quyết định biên dịch là chi tiết triển khai của JVM, không phải hợp đồng cố định của Java language.

Một cách nhìn đơn giản:

```text
Bytecode được thực thi
        |
        v
   Interpreter
        |
        v
 Thu thập profile
        |
        v
 Biên dịch nhanh (C1)
        |
        v
 Tối ưu sâu hơn khi đủ nóng (C2)
        |
        v
 Mã máy được tối ưu cho profile hiện tại
```

Không phải method nào cũng đi hết mọi mức hoặc được biên dịch bởi C2. JVM quyết định dựa trên profile, ngưỡng và tài nguyên runtime. Một method có thể vẫn được thông dịch hoặc chạy mã đã biên dịch ở mức khác.

### Các yếu tố JIT làm thay đổi phép đo

- **Compilation:** CPU dành cho biên dịch có thể cạnh tranh với benchmark trong warmup hoặc measurement.
- **On-stack replacement (OSR):** một vòng lặp chạy lâu có thể được chuyển từ thực thi thông dịch sang mã đã biên dịch ngay khi đang chạy; thời gian của các vòng đầu và vòng sau có thể khác nhau.
- **Inlining:** lời gọi method có thể được gộp vào caller, làm chi phí đo được khác với khi chạy method độc lập.
- **Escape analysis:** JVM có thể loại bỏ hoặc thay đổi cách cấp phát một số object nếu chứng minh chúng không thoát khỏi phạm vi cần thiết.
- **Dead-code elimination:** phép tính không ảnh hưởng đến kết quả quan sát được có thể bị loại bỏ.
- **Speculative optimization:** JIT có thể tối ưu dựa trên profile hiện tại và giả định về kiểu hoặc nhánh thường gặp.
- **Deoptimization:** khi giả định tối ưu không còn đúng, JVM có thể bỏ mã tối ưu và quay về thực thi ở mức ít tối ưu hơn trong khi thu thập profile mới.

Vì vậy, warmup cần dùng cùng loại dữ liệu và đường code với measurement. Warmup bằng một nhánh dễ nhưng measurement bằng một nhánh khác có thể tạo profile không đại diện.

## 4. Warmup không có nghĩa là JIT đã ổn định hoàn toàn

Không có một số vòng warmup cố định phù hợp cho mọi benchmark. Một method nhỏ có thể nóng nhanh; một ứng dụng lớn cần nhiều thời gian để nạp framework, biên dịch các đường code quan trọng và đạt trạng thái cache/GC đại diện.

Các dấu hiệu cần xem xét:

- Thời gian mỗi warmup iteration còn thay đổi mạnh hay đã ổn định tương đối?
- JIT vẫn đang biên dịch nhiều method trong measurement không?
- Workload warmup có đại diện cho dữ liệu và nhánh thực tế không?
- Có class loading, connection initialization hoặc lazy initialization xuất hiện lần đầu trong measurement không?
- GC có đang hoạt động ở measurement nhưng không xuất hiện trong warmup, hoặc ngược lại không?

Không nên loại bỏ một iteration chỉ vì kết quả không đẹp. Nếu kết quả chưa ổn định, tăng warmup, điều tra nguyên nhân hoặc ghi nhận rõ benchmark đang đo giai đoạn chuyển tiếp.

## 5. GC ảnh hưởng đến phép đo như thế nào?

Java cấp phát object trên heap. Khi object không còn reachable, GC có thể thu hồi vùng nhớ đó. Hoạt động GC có thể ảnh hưởng đến thời gian và throughput qua nhiều yếu tố:

- **Allocation rate:** số byte được cấp phát mỗi giây. Tác vụ tạo nhiều object có thể kích hoạt GC thường xuyên hơn.
- **Live set:** lượng object còn sống và cần được giữ lại. Live set lớn làm tăng lượng dữ liệu GC phải quản lý.
- **Collection frequency:** tần suất young/old hoặc các chu kỳ collection tùy collector.
- **Pause time:** thời gian ứng dụng bị dừng ở các pha cần stop-the-world.
- **Concurrent GC work:** công việc GC chạy đồng thời vẫn tiêu thụ CPU và băng thông bộ nhớ.
- **Promotion/retention:** object sống lâu có thể chuyển sang vùng được quản lý theo chính sách của collector.

Một benchmark tạo nhiều object có thể cho kết quả rất khác khi GC chạy trong measurement. Đây không nhất thiết là nhiễu cần loại bỏ: nếu workload production cũng cấp phát với tốc độ đó, chi phí GC là một phần của hiệu năng cần đo.

### Warmup và trạng thái heap

Trong warmup, heap dần chứa các object sống lâu, cache được lấp đầy và các object ngắn hạn được tạo rồi thu hồi. Measurement bắt đầu khi heap còn gần như trống có thể không đại diện cho ứng dụng chạy lâu. Tuy nhiên, nếu warmup tạo một live set khác production, trạng thái heap sau warmup cũng có thể sai lệch.

Hãy dùng dữ liệu và vòng đời object gần với workload thật. Đừng cố ép một lần GC để tạo trạng thái “sạch” rồi coi đó là điều kiện chuẩn cho mọi benchmark.

### Không dùng System.gc() để chuẩn hóa benchmark

`System.gc()` chỉ là yêu cầu JVM xem xét thực hiện garbage collection; nó không bảo đảm một full GC diễn ra ngay lập tức hoặc tạo ra trạng thái heap giống production. Gọi nó trước mỗi phép đo có thể làm benchmark đo một kịch bản nhân tạo và làm thay đổi timing, heap layout cũng như trạng thái cache.

Nếu cần nghiên cứu tác động GC, hãy cấu hình collector và heap rõ ràng, thu GC log hoặc JFR, rồi so sánh cùng workload. Không dùng `System.gc()` như nút reset chung cho benchmark.

## 6. Warmup và measurement với JMH

JMH (Java Microbenchmark Harness) là công cụ chuyên dụng để đo các đoạn code nhỏ trên JVM. JMH quản lý warmup iteration, measurement iteration, fork JVM, đồng bộ thread và tiêu thụ kết quả để giảm nhiều sai lệch phổ biến của microbenchmark.

Các khái niệm thường dùng:

| Annotation/thành phần | Vai trò |
|---|---|
| `@Benchmark` | Đánh dấu method cần đo |
| `@Warmup` | Số iteration và thời lượng warmup |
| `@Measurement` | Số iteration và thời lượng lấy số liệu |
| `@Fork` | Số JVM process độc lập chạy benchmark |
| `@State` | Khai báo phạm vi dữ liệu benchmark được chia sẻ |
| `@Setup` / `@TearDown` | Chuẩn bị và thu dọn state ở level phù hợp |
| `@BenchmarkMode` | Chọn average time, throughput, sample time hoặc single-shot |
| `@OutputTimeUnit` | Đơn vị hiển thị kết quả |
| `Blackhole` | Tiêu thụ kết quả để tránh dead-code elimination |

Ví dụ:

```java
import java.util.concurrent.TimeUnit;
import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.BenchmarkMode;
import org.openjdk.jmh.annotations.Fork;
import org.openjdk.jmh.annotations.Level;
import org.openjdk.jmh.annotations.Measurement;
import org.openjdk.jmh.annotations.OutputTimeUnit;
import org.openjdk.jmh.annotations.Param;
import org.openjdk.jmh.annotations.Scope;
import org.openjdk.jmh.annotations.Setup;
import org.openjdk.jmh.annotations.State;
import org.openjdk.jmh.annotations.Warmup;
import org.openjdk.jmh.annotations.Mode;
import org.openjdk.jmh.infra.Blackhole;

@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.MICROSECONDS)
@Warmup(iterations = 5, time = 1)
@Measurement(iterations = 5, time = 1)
@Fork(3)
public class WarmupGcBenchmark {
    @Param({"100", "10000"})
    public int size;

    private int[] values;

    @Setup(Level.Trial)
    public void setup() {
        values = new int[size];
        for (int i = 0; i < values.length; i++) {
            values[i] = i + 1;
        }
    }

    @Benchmark
    public long sumValues() {
        long sum = 0;
        for (int value : values) {
            sum += value;
        }
        return sum;
    }

    @Benchmark
    public void allocateAndConsume(Blackhole blackhole) {
        blackhole.consume(new byte[size]);
    }
}
```

Trong ví dụ:

- `@Warmup` chạy 5 iteration, mỗi iteration 1 giây trước khi đo.
- `@Measurement` lấy số liệu trong 5 iteration, mỗi iteration 1 giây.
- `@Fork(3)` chạy benchmark trong ba JVM process độc lập để giảm ảnh hưởng của profile và trạng thái JVM từ lần chạy trước.
- `@Setup(Level.Trial)` tạo dữ liệu trước các iteration; thời gian chuẩn bị không nằm trong method benchmark.
- `sumValues()` trả kết quả để JMH tiêu thụ.
- `allocateAndConsume()` đưa object mới vào `Blackhole` để kết quả cấp phát có thể quan sát được.

Các con số iteration, thời lượng và fork chỉ là điểm khởi đầu. Benchmark thật cần điều chỉnh theo thời gian chạy, độ ổn định và chi phí khởi động của workload.

Đoạn code là benchmark class cần được biên dịch trong project đã cấu hình JMH core và annotation processor; nó không phải chương trình Java độc lập chỉ cần chạy `main`. Khi chạy, dùng JMH runner hoặc benchmark JAR do build tạo ra để JMH quản lý forks và iterations.

## 7. Chọn đúng benchmark mode

JMH có các mode phục vụ mục tiêu khác nhau:

| Mode | Đo gì? | Khi phù hợp |
|---|---|---|
| `Mode.AverageTime` | Thời gian trung bình mỗi operation | So sánh chi phí trung bình của method nhỏ |
| `Mode.Throughput` | Số operation hoàn thành trên đơn vị thời gian | Đo năng suất xử lý khi chạy lặp |
| `Mode.SampleTime` | Phân phối thời gian mẫu của operation | Quan sát độ phân tán và tail trong benchmark |
| `Mode.SingleShotTime` | Thời gian cho một lần thực thi benchmark | Đo thao tác đơn lẻ hoặc kịch bản không lặp liên tục; cần thiết kế fork/warmup phù hợp |

Không suy ra latency end-to-end của service từ average time của một method. JMH chủ yếu đo microbenchmark trong JVM; service thực tế còn có network, queue, connection pool, serialization, scheduling và các dependency khác.

Nếu mục tiêu là p95/p99 latency của API, hãy dùng load test có khả năng tạo tải phù hợp và đo từ client hoặc ranh giới request đã định nghĩa. JMH `SampleTime` hữu ích để nghiên cứu phân phối thời gian method nhưng không thay thế phép đo phân vị của toàn service.

## 8. Tránh dead-code elimination và constant folding

JIT tối ưu chương trình dựa trên hành vi có thể quan sát được. Nếu kết quả benchmark không được sử dụng, phép tính có thể bị loại bỏ. Nếu đầu vào là hằng số mà compiler/JIT có thể biết trước, kết quả có thể được tính trước hoặc đơn giản hóa.

Ví dụ sai:

```java
@Benchmark
public void wrongBenchmark() {
    int result = 40 * 2;
    // result không được sử dụng; phép tính có thể bị loại bỏ.
}
```

Ví dụ tốt hơn:

```java
@Benchmark
public int calculate() {
    return computeFromRuntimeState();
}
```

JMH tiêu thụ giá trị trả về của benchmark. Nếu benchmark có nhiều kết quả hoặc không thể trả về trực tiếp, dùng `Blackhole`:

```java
@Benchmark
public void calculateAndConsume(Blackhole blackhole) {
    blackhole.consume(computeFromRuntimeState());
}
```

Đầu vào nên phản ánh dữ liệu runtime và không để JIT biết trước toàn bộ kết quả. Tuy nhiên, không tạo dữ liệu ngẫu nhiên trong chính vùng được đo nếu mục tiêu là đo thuật toán xử lý dữ liệu; hãy chuẩn bị input trong `@Setup` và kiểm soát seed để có thể lặp lại.

## 9. Tránh loop benchmark sai cách

Tự viết vòng lặp lớn quanh một method để lấy thời gian trung bình có thể làm sai kết quả. JIT có thể inline, unroll, vectorize, hoist hoặc tối ưu toàn bộ loop theo cách khác với từng lời gọi riêng. Chi phí vòng lặp và benchmark harness cũng có thể bị tính chung hoặc bị tối ưu.

Không nên mặc định viết:

```java
long start = System.nanoTime();
for (int i = 0; i < 1_000_000; i++) {
    operation();
}
long elapsed = System.nanoTime() - start;
```

để suy ra chi phí một operation bằng `elapsed / 1_000_000`. Đoạn code có thể hữu ích cho một phép đo thô được thiết kế cẩn thận, nhưng không thay thế JMH cho microbenchmark. JMH quản lý vòng lặp, warmup, fork và kết quả theo cách có kiểm soát hơn.

`System.nanoTime()` vẫn là API phù hợp để đo khoảng thời gian trôi qua trong một tiến trình vì nó không phụ thuộc giờ lịch; vấn đề nằm ở cách dựng benchmark thủ công, không phải ở bản thân `nanoTime()`. `System.currentTimeMillis()` là đồng hồ thời gian lịch và không phù hợp để đo duration ngắn.

Trong JMH, thông thường một invocation của method `@Benchmark` là đơn vị thao tác. Nếu operation tự nó rất nhỏ, để JMH điều phối thay vì tự thêm loop lớn. Nếu workload thật là xử lý batch, benchmark batch đó như một operation và mô tả kích thước batch rõ ràng.

## 10. Setup, state và mức độ chia sẻ dữ liệu

`@Setup` có thể chạy ở các level khác nhau:

- `Level.Trial`: chạy một lần cho mỗi trial; phù hợp để tạo dữ liệu dùng xuyên suốt benchmark.
- `Level.Iteration`: chạy trước mỗi iteration; hữu ích khi cần reset state giữa các iteration, nhưng chi phí setup không được tính vào method benchmark.
- `Level.Invocation`: chạy trước mỗi invocation; chỉ dùng khi thật sự cần reset từng operation, vì overhead và thay đổi trạng thái có thể ảnh hưởng đáng kể đến phép đo.

Chọn `@State` theo mức chia sẻ:

- `Scope.Thread`: mỗi benchmark thread có state riêng, giảm tranh chấp ngoài mục tiêu đo.
- `Scope.Benchmark`: các thread chia sẻ một state; phù hợp khi muốn đo cấu trúc dùng chung hoặc contention.
- `Scope.Group`: state được chia sẻ trong một nhóm benchmark thread.

Nếu muốn đo hiệu năng concurrent access, phải tạo đúng contention mà production có. Nếu chỉ muốn đo thuật toán tuần tự, state riêng theo thread thường giúp tránh lock/false sharing không thuộc mục tiêu đo.

## 11. Fork để tránh nhiễm trạng thái giữa các lần đo

JVM giữ profile JIT, code cache, class loading state và nhiều trạng thái runtime khác trong suốt vòng đời process. Chạy nhiều benchmark khác nhau trong cùng một process có thể khiến benchmark sau bị ảnh hưởng bởi code đã được biên dịch hoặc profile do benchmark trước tạo ra.

JMH dùng fork để chạy benchmark trong JVM process mới. Nhiều fork giúp đánh giá độ biến thiên giữa các process độc lập và giảm nguy cơ kết quả chỉ đúng với một trạng thái JVM tình cờ.

Fork không loại bỏ mọi nguồn sai lệch. Máy vẫn có thể bị tác vụ nền, CPU frequency scaling, thermal throttling hoặc giới hạn container ảnh hưởng. Hãy ghi lại JDK, JVM flags, phần cứng, hệ điều hành và cấu hình benchmark khi so sánh.

## 12. Quan sát JIT và GC khi benchmark

Không nên chỉ nhìn kết quả cuối cùng. Khi benchmark có kết quả bất thường, hãy thu thập bằng chứng runtime.

### GC logging

Java 21 hỗ trợ Unified Logging cho GC:

```shell
java -Xlog:gc*:file=gc.log:time,uptime,level,tags -jar app.jar
```

Với JMH, có thể truyền JVM arguments cho fork qua cấu hình JMH hoặc command line runner phù hợp. Sau đó đối chiếu thời điểm GC với measurement iteration và kết quả latency/throughput.

### JMH GC profiler

JMH có profiler `gc` để thu thập các chỉ số như allocation rate, số lần GC và thời gian GC:

```shell
java -jar target/benchmarks.jar -prof gc
```

Các metric thường hữu ích gồm:

- `gc.alloc.rate`: tốc độ cấp phát ước tính.
- `gc.alloc.rate.norm`: lượng byte cấp phát chuẩn hóa theo operation.
- `gc.count`: số lần GC trong khoảng đo.
- `gc.time`: tổng thời gian GC được ghi nhận.

Đọc các giá trị này cùng benchmark score. Hai thuật toán có thời gian xử lý gần nhau nhưng một thuật toán cấp phát nhiều hơn có thể tạo áp lực GC cao hơn khi chạy ở quy mô service.

### JFR

JFR giúp xem các sự kiện compilation, GC, allocation, thread scheduling và CPU sampling trong cùng một recording:

```shell
java -XX:StartFlightRecording=filename=benchmark.jfr,dumponexit=true -jar app.jar
```

Có thể dùng `jcmd` để bắt đầu recording trên tiến trình đang chạy nếu quyền và runtime cho phép. JFR hữu ích khi cần liên hệ JIT compilation hoặc GC activity với thời điểm latency tăng.

Không bật mọi log/profiler chi tiết trong lần benchmark dùng để công bố con số cuối cùng nếu overhead của công cụ làm thay đổi workload. Hãy dùng một lần chạy riêng để chẩn đoán, rồi đo lại với cấu hình ít xâm lấn.

## 13. Các yếu tố môi trường gây sai lệch

Ngay cả khi code benchmark và JVM flags giống nhau, môi trường vẫn có thể làm kết quả thay đổi:

| Yếu tố | Tác động có thể có | Cách kiểm soát |
|---|---|---|
| CPU frequency scaling/turbo | Tần số CPU thay đổi theo tải và nhiệt độ | Ghi nhận power mode, lặp lại nhiều lần và giữ điều kiện nguồn ổn định |
| Thermal throttling | CPU giảm xung khi quá nóng | Theo dõi nhiệt độ, tránh chạy benchmark quá lâu liên tục |
| Process nền | Tranh chấp CPU, cache và I/O | Giảm tác vụ nền, chạy trên máy/runner chuyên dụng khi cần |
| Container CPU quota | CPU bị throttling dù host còn core | Ghi lại CPU limit/quota và benchmark trong cùng giới hạn |
| Memory/container limit | GC hoặc hệ điều hành chịu áp lực bộ nhớ | Ghi heap, RSS, direct memory và memory limit |
| JDK vendor/update | JIT, GC và runtime implementation có thể khác | Ghi rõ vendor, version và build number |
| JVM flags | Heap, collector, compiler hoặc thread policy thay đổi | Ghi toàn bộ flags và giữ giống nhau khi so sánh |
| CPU architecture/OS | JIT sinh mã máy và native library khác nhau | So sánh trên cùng nền tảng mục tiêu |
| Cache/data state | Cache lạnh và cache nóng có latency khác nhau | Xác định rõ cần đo cold-cache hay warm-cache |
| Background GC/compilation | Công việc runtime cạnh tranh CPU | Thu JFR/GC log trong lần chẩn đoán riêng |

Không so sánh trực tiếp hai con số nếu chúng được đo trên hai máy, hai container quota hoặc hai bản JDK khác nhau mà không ghi rõ các khác biệt.

## 14. Đo latency: average không nói hết câu chuyện

Average time có thể che khuất một nhóm operation rất chậm. Với hệ thống phục vụ request, hãy xem phân phối latency:

- **p50:** một nửa request có latency không vượt quá giá trị này.
- **p95:** 95% request có latency không vượt quá giá trị này.
- **p99:** 99% request có latency không vượt quá giá trị này.
- **Maximum:** giá trị lớn nhất trong mẫu; nhạy với outlier và kích thước tập đo.

Ví dụ:

| Chỉ số | Latency |
|---|---:|
| p50 | 18 ms |
| p95 | 75 ms |
| p99 | 240 ms |
| Maximum | 680 ms |

Kết quả cho thấy phần lớn request nhanh nhưng có tail latency đáng kể. GC pause, JIT compilation, queueing, lock contention, network hoặc downstream đều có thể góp phần tạo tail; cần dùng JFR, GC log và trace để xác định nguyên nhân thay vì suy đoán từ percentile.

Với load test, chú ý **coordinated omission**: nếu load generator chỉ gửi request mới sau khi request trước hoàn tất, khi service bị chậm nó cũng giảm tốc độ gửi và có thể bỏ sót latency mà người dùng sẽ gặp dưới một tốc độ đến cố định. Chọn mô hình tải phù hợp (closed-loop hoặc open-loop), theo dõi offered load và completed throughput, đồng thời dùng histogram/percentile có cách ghi nhận rõ ràng.

## 15. Các sai lầm thường gặp

| Sai lầm | Vì sao sai lệch | Cách làm phù hợp |
|---|---|---|
| Đo ngay lần gọi đầu tiên rồi kết luận steady state | JIT, class loading và initialization chưa ổn định | Có warmup riêng; cold start đo theo kịch bản riêng |
| Warmup bằng workload khác measurement | Profile JIT và cache không đại diện | Dùng cùng đường code và phân phối input |
| Chạy benchmark chỉ một JVM process | Kết quả có thể phụ thuộc trạng thái JIT/profile tình cờ | Dùng nhiều fork và báo cáo độ biến thiên |
| Bỏ qua GC để kết quả “sạch” | Chi phí GC có thể là phần thật của workload | Đo allocation/GC và giữ điều kiện heap nhất quán |
| Gọi `System.gc()` trước mỗi phép đo | Không bảo đảm trạng thái heap chuẩn và làm thay đổi workload | Dùng GC log/JFR; thiết kế state đúng mục tiêu |
| Không tiêu thụ kết quả | JIT có thể loại bỏ phép tính | Trả kết quả hoặc dùng JMH `Blackhole` |
| Dùng hằng số đầu vào | JIT có thể constant-fold hoặc tối ưu đặc biệt | Dùng state/input runtime có thể kiểm soát |
| Tự viết loop lớn và chia thời gian cho số vòng | Loop optimization và overhead làm sai chi phí mỗi operation | Dùng JMH và benchmark đúng đơn vị operation |
| Đặt setup trong vùng đo ngoài ý muốn | Initialization lấn át chi phí cần đo | Chọn `@Setup` level và scope phù hợp |
| Chỉ báo cáo average | Tail latency bị che khuất | Báo p50/p95/p99 cho service và mô tả histogram |
| Bật profiler nặng trong lần đo cuối | Công cụ quan sát làm thay đổi hiệu năng | Chẩn đoán riêng rồi đo lại với overhead thấp |
| Không ghi lại JVM flags/JDK build | Không thể tái lập hoặc giải thích khác biệt | Lưu metadata môi trường cùng kết quả |

## 16. Quy trình benchmark có thể lặp lại

Một quy trình thực tế cho Java 21:

1. **Xác định mục tiêu:** cold start, method latency, throughput, allocation rate hay service p99.
2. **Chọn công cụ:** JMH cho microbenchmark; load test cho service; JFR/GC log để chẩn đoán runtime.
3. **Cố định môi trường:** JDK vendor/update, OS, CPU, container quota, heap, GC và JVM flags.
4. **Chuẩn bị input:** tạo dữ liệu đại diện, kiểm soát seed và tránh constant input không thực tế.
5. **Warmup:** chạy cùng workload cho đến khi số liệu có tính ổn định phù hợp với mục tiêu.
6. **Measurement:** thu nhiều iteration và nhiều fork; không trộn thời gian setup nếu không phải điều cần đo.
7. **Quan sát GC/JIT:** dùng profiler hoặc recording riêng để tìm compilation, allocation, GC và pause bất thường.
8. **Lặp lại và so sánh:** chạy nhiều lần, xem trung vị/độ biến thiên giữa fork và không chọn riêng lần chạy tốt nhất.
9. **Báo cáo:** ghi score, đơn vị, warmup/measurement config, forks, JDK, flags, phần cứng, workload và giới hạn phép đo.

Nếu mục tiêu là cold start, mỗi mẫu phải bắt đầu từ process mới và đo đến readiness. Nếu mục tiêu là steady state, warmup phải được tách khỏi measurement nhưng vẫn dùng workload đại diện. Không trộn hai mục tiêu vào một con số duy nhất.

## 17. Checklist trước khi công bố kết quả

- Xác định rõ phép đo cold start hay steady state.
- Dùng JMH cho microbenchmark thay vì tự viết timer/loop đơn giản.
- Cấu hình warmup, measurement và forks đủ để thấy độ ổn định.
- Dùng cùng workload/input distribution trong warmup và measurement.
- Đảm bảo kết quả được tiêu thụ để tránh dead-code elimination.
- Tránh constant folding và loop benchmark không đại diện.
- Chọn `@State` và `@Setup` đúng mục tiêu, tránh contention hoặc setup overhead ngoài ý muốn.
- Theo dõi allocation rate, GC count/time và heap occupancy.
- Không dùng `System.gc()` như cách reset benchmark.
- Ghi lại JDK vendor/update, JVM flags, GC, heap, OS, CPU và container limits.
- Báo cáo throughput và latency phân vị phù hợp, không chỉ average.
- Kiểm tra coordinated omission trong load test và ghi rõ mô hình tải.
- Dùng JFR/GC log để chẩn đoán riêng và đo lại sau khi tắt công cụ có overhead lớn.
- Lặp lại benchmark và báo cáo biến thiên giữa các fork/lần chạy.

Warmup giúp JVM thu thập profile và JIT tối ưu đường code thường dùng; GC và allocation phản ánh chi phí quản lý object của workload. Đo hiệu năng đáng tin cậy cần tách cold start khỏi steady state, dùng công cụ phù hợp như JMH, kiểm soát môi trường, tiêu thụ kết quả và quan sát runtime. Khi ghi rõ điều kiện đo và giới hạn của kết quả, nhóm phát triển mới có thể so sánh các thay đổi Java 21 một cách có cơ sở.

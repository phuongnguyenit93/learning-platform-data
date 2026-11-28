# Thiết kế benchmark bằng JMH và tránh kết quả đo sai trong Java 27

**Benchmark** là một thí nghiệm có kiểm soát để đo đặc tính hiệu năng của một thao tác hoặc hệ thống. Đối với ứng dụng chạy trên JVM, một phép đo tưởng như đơn giản có thể bị sai vì JIT compiler tối ưu mất công việc, dữ liệu đầu vào quá dễ đoán, chưa warmup, garbage collector, thread contention, CPU frequency, cache hoặc cách tính số operations.

**Java Microbenchmark Harness (JMH)** là bộ công cụ do dự án OpenJDK phát triển để xây dựng và chạy benchmark Java/JVM theo phương pháp có cấu trúc. JMH giúp tổ chức warmup, measurement, fork JVM, thông số thử nghiệm, kiểm soát lifecycle và báo cáo kết quả. Tuy nhiên, **JMH không tự biến một thí nghiệm thiết kế sai thành kết quả đúng**.

Bài thuộc chương **Chẩn đoán và hiệu năng** của lộ trình **Java 27 và các kiến thức liên quan**. Nội dung sử dụng JMH và API Java đang được áp dụng, phân tích cách thiết kế thí nghiệm có ý nghĩa, cung cấp ví dụ thực hành và chỉ ra những ngộ nhận dễ dẫn đến quyết định tối ưu sai.

## 1. Đo thứ gì trước khi hỏi "nhanh hơn bao nhiêu?"

Một benchmark chỉ có ý nghĩa khi trả lời được một câu hỏi cụ thể:

- **Tác vụ:** Ví dụ, tính tổng một mảng 4.096 số nguyên hay thực hiện một request HTTP hoàn chỉnh?
- **Đại lượng:** Thời gian một phép gọi, throughput, phân phối độ trễ, lượng cấp phát, hay tổng CPU?
- **Phạm vi:** Chỉ thân phương thức, cả bước chuẩn bị dữ liệu, hay toàn bộ pipeline?
- **Điều kiện:** Kích thước dữ liệu, số thread, tỷ lệ đọc/ghi, kiểu input, CPU và JVM nào?
- **Tiêu chí đúng:** Hai phương án có tạo **cùng kết quả và đáp ứng cùng hợp đồng nghiệp vụ** không?

Ví dụ câu hỏi tốt:

> Trên Java 27, với một mảng int có 4.096 phần tử được chuẩn bị sẵn, phép tính tổng bằng vòng for khác bao nhiêu về thời gian mỗi phép tính so với IntStream.sum sau warmup, ở một thread?

Ví dụ câu hỏi quá mơ hồ:

> Stream có nhanh hơn for không?

Vì câu thứ hai không cố định kích thước, kiểu dữ liệu, operation, số thread hay tính chất input, kết luận có thể hoàn toàn khác giữa các workload.

### 1.1. Các tầng cần phân biệt

| Loại kiểm tra | Tìm hiểu | Công cụ phù hợp |
|---|---|---|
| Unit test | Hàm có đúng không? | JUnit hoặc test phù hợp |
| Microbenchmark | Một đoạn xử lý có chi phí bao nhiêu trong điều kiện xác định? | JMH |
| Component benchmark | Một module, parser, cache, truy vấn hoàn chỉnh hoạt động ra sao? | JMH khi workload đo hợp lý; công cụ profiling/benchmark bổ trợ |
| Load test | Hệ thống đáp ứng thế nào dưới tải từ client? | Công cụ tạo tải và đo dịch vụ |
| Production profiling | Thời gian CPU, allocation hoặc chờ ở đâu trong hệ thống thực? | JFR, JDK Mission Control, async-profiler và công cụ tương ứng |

**Không dùng điểm số microbenchmark để tuyên bố một dịch vụ production sẽ cải thiện cùng tỷ lệ.** Trong hệ thống thực tế, I/O, queue, GC, network và database có thể áp đảo chi phí của một hàm nhỏ.

## 2. Vì sao System.nanoTime và vòng lặp tự viết dễ đánh lừa?

Đoạn mã sau **không phải benchmark đủ tin cậy**:

~~~java
long start = System.nanoTime();

for (int i = 0; i < 1_000_000; i++) {
    compute(42);
}

long elapsed = System.nanoTime() - start;
System.out.println(elapsed);
~~~

Ngay cả khi `compute` được định nghĩa và code chạy được, có ít nhất tám câu hỏi:

1. Kết quả `compute(42)` có được sử dụng không, hay JIT loại bỏ vì không có tác dụng quan sát được?
2. Giá trị 42 cố định có cho phép **constant folding** không?
3. JIT đã biên dịch code tối ưu hay đang ở giai đoạn interpreter/C1/C2?
4. Compiler có đưa phép tính ra ngoài vòng lặp (**loop-invariant code motion**) không?
5. Một phép chạy có bị ảnh hưởng bởi GC, OS scheduler hoặc CPU frequency không?
6. Kết quả đo có gộp cả khởi tạo dữ liệu hay log/đồng bộ không?
7. Tác vụ lặp triệu lần có giống workload thực tế hay tối ưu hóa khác hẳn một lời gọi?
8. Kích thước dữ liệu có vừa hết trong L1/L2 cache, trong khi production thường đọc dữ liệu lớn hơn không?

`System.nanoTime()` là API hợp lệ để đo **khoảng thời gian** trong ứng dụng. Vấn đề không nằm ở bản thân đồng hồ, mà ở việc **thiếu một quy trình kiểm soát phép đo**.

JMH giải quyết phần lớn vấn đề về harness, nhưng người viết vẫn phải đảm bảo workload và input có ý nghĩa.

## 3. JMH là gì và vị trí của nó trong Java 27

JMH là một **thư viện/công cụ riêng của dự án OpenJDK**, không phải API trong `java.base` và cũng không tự đi kèm mọi bộ cài JDK. Một dự án JMH thường sử dụng:

- `org.openjdk.jmh:jmh-core`: API và runtime thực thi benchmark.
- `org.openjdk.jmh:jmh-generator-annprocess`: annotation processor sinh mã harness.
- Maven archetype `jmh-java-benchmark-archetype`: tạo dự án với cấu hình sinh mã và đóng gói phù hợp.

Ví dụ chọn **JMH 1.37**, phiên bản hiện được công bố trên Maven Central tại thời điểm tài liệu được biên soạn. Khi sử dụng trong dự án thật, kiểm tra lại phiên bản phù hợp và cố định version trong build để đảm bảo tái lập.

**Không chỉ thêm mỗi dependency `jmh-core` rồi hy vọng mọi benchmark hoạt động**: JMH cần generated harness từ annotation processing hoặc cơ chế sinh bytecode phù hợp. README chính thức của OpenJDK khuyến nghị bắt đầu bằng Maven archetype.

### 3.1. Luồng chạy JMH

~~~text
                   Mã nguồn @Benchmark
                            |
                     annotation processor
                            |
                      generated harness
                            |
                       Maven package
                            |
                    target/benchmarks.jar
                            |
                +-----------+-----------+
                |                       |
           Warmup phase            Measurement phase
        (không tính điểm số)     (lấy các mẫu số liệu)
                |                       |
                +-----------+-----------+
                            |
                   Các fork JVM riêng
                            |
                     Score + Error
~~~

JMH có thể chạy nhiều benchmark, nhiều giá trị tham số, nhiều thread và nhiều fork. Mỗi combination là một **trường hợp thí nghiệm**, không phải bằng chứng chung cho toàn bộ workload khác.

## 4. Tạo dự án JMH độc lập bằng Maven

Cách tổ chức ổn định là một project hoặc submodule benchmark riêng, phụ thuộc vào JAR chứa mã đang cần đo. Cách này hạn chế tác động của IDE, plugin tùy chỉnh hoặc class path tình cờ.

Chuẩn bị JDK 27 và Maven phù hợp trên máy thực hiện phép đo:

~~~shell
java --version
javac --version
mvn --version
~~~

Tạo project bằng **archetype chính thức**:

~~~shell
mvn archetype:generate -DinteractiveMode=false -DarchetypeGroupId=org.openjdk.jmh -DarchetypeArtifactId=jmh-java-benchmark-archetype -DarchetypeVersion=1.37 -DgroupId=dev.example -DartifactId=jmh-lab -Dversion=1.0-SNAPSHOT
~~~

Chuyển vào dự án được tạo:

~~~shell
cd jmh-lab
~~~

Cấu trúc điển hình:

~~~text
jmh-lab/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── dev/
                └── example/
                    └── MyBenchmark.java
~~~

Đường dẫn và tên class mẫu của archetype có thể khác tùy phiên bản. Khi thêm ví dụ trong bài, đặt mã nguồn tại package riêng, chẳng hạn `dev.example.bench`, và đảm bảo Maven biên dịch được.

### 4.1. Java release trong dự án benchmark

Khi nghiên cứu **Java 27**, cần sử dụng đúng JDK 27 cho Maven và cả JVM thực sự chạy benchmark. Nếu muốn benchmark bytecode mục tiêu Java 27, đảm bảo Maven compiler configuration dùng `--release 27` hoặc thiết lập tương đương:

~~~xml
<properties>
    <maven.compiler.release>27</maven.compiler.release>
</properties>
~~~

Đây là đoạn cấu hình để đưa vào `pom.xml` theo plugin Maven Compiler tương thích, **không phải một file POM hoàn chỉnh**. Trong dự án thật, xác minh JDK, phiên bản plugin compiler và cấu hình archetype đã tạo.

**Build bằng JDK 27 và chạy bằng JDK khác có thể làm kết quả khác**. Hãy ghi lại cả hai nếu chúng không trùng nhau.

### 4.2. Build và chạy

~~~shell
mvn clean verify
java -jar target/benchmarks.jar
~~~

JAR do archetype tạo thường chứa phần hạ tầng cần thiết để chạy benchmark. Trước khi chạy mọi benchmark, xem danh sách:

~~~shell
java -jar target/benchmarks.jar -l
java -jar target/benchmarks.jar -h
~~~

Các lệnh trên là hướng dẫn cho người học **tại dự án JMH của họ**; bài viết này không tự chạy Maven hoặc tác động vào các file ngoài bài học được giao.

### 4.3. Vì sao không chỉ bấm Run trên IDE?

IDE có thể đưa vào:

- Các agent hỗ trợ debugger/profiler.
- Class path và JVM options không giống production.
- Cơ chế build chưa chạy đúng annotation processor.
- Process khác tiêu thụ CPU/bộ nhớ.
- Điều kiện warmup khác.

JMH có thể được gọi từ code Java qua `org.openjdk.jmh.runner.Runner`, nhưng **chạy JAR benchmark từ command line** thường rõ ràng, dễ tái lập và dễ ghi nhận môi trường hơn.

## 5. Những annotation quan trọng trong JMH

| Annotation | Chức năng |
|---|---|
| `@Benchmark` | Đánh dấu phương thức được harness gọi để đo |
| `@BenchmarkMode` | Chọn đại lượng đo: throughput, average time, sample time, single shot |
| `@OutputTimeUnit` | Chọn đơn vị biểu diễn kết quả |
| `@State` | Khai báo trạng thái và phạm vi chia sẻ giữa các thread |
| `@Param` | Tạo nhiều bộ input thử nghiệm |
| `@Setup` | Chuẩn bị trạng thái theo trial/iteration/invocation |
| `@TearDown` | Dọn dẹp hoặc kiểm tra sau các pha |
| `@Warmup` | Số và thời lượng các iteration chuẩn bị |
| `@Measurement` | Số và thời lượng iteration được tính điểm |
| `@Fork` | Số JVM process riêng được chạy cho benchmark |
| `@Threads` | Số worker threads để thực hiện benchmark |
| `@Group`, `@GroupThreads` | Mô hình các tác vụ reader/writer chạy đồng thời theo nhóm |
| `@OperationsPerInvocation` | Khai báo số logical operations trong một lần invocation nếu thật sự cần |
| `@AuxCounters` | Báo thêm metric dạng counter theo hợp đồng JMH |

Không cần sử dụng mọi annotation trên một benchmark. Càng nhiều tham số chạy và vòng đời khác nhau, càng phải cân nhắc khả năng diễn giải đúng kết quả.

## 6. Chọn đúng chế độ đo

JMH có nhiều `Mode`; cách hiểu số đo là một phần của thiết kế thí nghiệm.

| Mode | Ý nghĩa | Đơn vị ví dụ | Phù hợp |
|---|---|---|---|
| `Mode.Throughput` | Số operation hoàn thành mỗi đơn vị thời gian | ops/s | Khả năng xử lý |
| `Mode.AverageTime` | Thời gian trung bình mỗi operation | us/op hoặc ns/op | Chi phí mỗi lượt gọi |
| `Mode.SampleTime` | Phân phối thời gian của các operation được lấy mẫu | ns/op và percentile | Quan sát sự khác nhau giữa các lần |
| `Mode.SingleShotTime` | Thời gian chạy một invocation/batch đơn lẻ | ms/op | Cold-start hoặc operation dài, có cấu hình cẩn thận |
| `Mode.All` | Chạy nhiều mode được hỗ trợ | Nhiều loại | Khám phá, không phải một metric duy nhất |

### 6.1. Throughput và AverageTime không luôn nghịch đảo trực tiếp

Với **một thread thực hiện một operation tuần tự**, throughput và average time có thể gợi ra quan hệ gần nghịch đảo. Nhưng khi chạy N thread, các thread cùng tạo công việc đồng thời và có thể tranh chấp tài nguyên.

Không suy ra `1 / throughput` chính là latency trung bình của một client request trong hệ thống nhiều thread. Throughput, service time và end-to-end latency khác nhau, nhất là khi có queue.

### 6.2. SampleTime không đảm bảo mô tả toàn hệ thống production

`SampleTime` giúp xem phân phối các invocation được lấy mẫu. Nó không tự đo queue time, network hop hoặc tail latency của request ngoài ứng dụng. Không lấy percentile của một phương thức nhỏ rồi gọi đó là **p99 API latency**.

### 6.3. SingleShot cần nêu rõ trạng thái "cold"

Một benchmark `SingleShotTime` vẫn chịu ảnh hưởng của JVM startup, class loading, page cache và state setup tùy cách cấu hình. Nếu thực sự muốn đo **startup toàn tiến trình**, chỉ đo một method bên trong JMH không tương đương thời gian từ lúc OS tạo process đến lúc ứng dụng sẵn sàng phục vụ.

## 7. Warmup, Measurement và Fork

Ba khái niệm này thường bị trộn lẫn.

### 7.1. Warmup: chạy trước khi thu điểm

~~~java
@Warmup(iterations = 5, time = 1, timeUnit = TimeUnit.SECONDS)
~~~

Trong ví dụ, JMH chạy 5 warmup iterations, mỗi iteration mục tiêu 1 giây. Warmup giúp JVM hình thành profile, tải class, biên dịch JIT, khởi tạo đường đi nóng và ổn định một phần dữ liệu/cache.

Warmup **không bảo đảm** mọi code đã đạt trạng thái ổn định. Một bài toán có tiered compilation, kích thước dataset lớn hoặc thay đổi profile muộn có thể cần theo dõi đồ thị iteration và điều chỉnh warmup.

### 7.2. Measurement: thời gian tính kết quả

~~~java
@Measurement(iterations = 7, time = 2, timeUnit = TimeUnit.SECONDS)
~~~

Bảy iteration được đo, mỗi iteration mục tiêu 2 giây. JMH tính các chỉ số theo mode và tổng hợp những kết quả này. Không đánh đồng **7 iterations** với **7 lần gọi method**: trong mode throughput/average time, method có thể được gọi hàng triệu lần trong một iteration.

### 7.3. Fork: JVM process độc lập

~~~java
@Fork(3)
~~~

JMH chạy benchmark trong ba JVM process tách biệt, hữu ích để giảm phụ thuộc vào JIT profile, class loading, GC history hoặc trạng thái ngẫu nhiên còn lại từ một lần chạy.

Forks không thay thế việc lặp lại trên nhiều máy, nhiều thời điểm hoặc một cấu hình môi trường có kiểm soát.

**Tránh `@Fork(0)` trong phép đo cần độ tin cậy cao**, vì benchmark chạy cùng JVM với harness, dễ nhiễm các yếu tố profile và cấu hình không độc lập.

### 7.4. Thời gian dự kiến của phép đo

Nếu một benchmark có 5 warmup iterations × 1 giây và 7 measurement iterations × 2 giây, mỗi fork mất ít nhất xấp xỉ 19 giây cho phần iteration, chưa tính khởi động JVM, setup, cleanup và các overhead khác. Ba forks và nhiều `@Param` có thể khiến tổng thời gian tăng mạnh.

Đây là lý do không nên bật mọi combination một cách thiếu kiểm soát; trước khi đo toàn bộ, chọn các tình huống đại diện.

## 8. Ví dụ hoàn chỉnh: tính tổng mảng bằng vòng for và IntStream

**Câu hỏi:** Trong Java 27, một invocation tính tổng toàn bộ mảng có kích thước xác định bằng vòng `for` khác gì với cách dùng `Arrays.stream(...).asLongStream().sum()`?

Mã dưới đây dùng cùng input cho hai phương án, không cấp phát dữ liệu ở trong timed method, và trả kết quả để JMH có thể quan sát.

Tạo file `src/main/java/dev/example/bench/ArraySumBenchmark.java` trong dự án JMH.

~~~java
package dev.example.bench;

import java.util.Arrays;
import java.util.Random;
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
import org.openjdk.jmh.annotations.Threads;
import org.openjdk.jmh.annotations.Warmup;

@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.MICROSECONDS)
@Warmup(iterations = 5, time = 1, timeUnit = TimeUnit.SECONDS)
@Measurement(iterations = 7, time = 1, timeUnit = TimeUnit.SECONDS)
@Fork(3)
@Threads(1)
public class ArraySumBenchmark {

    @Param({"128", "4096", "65536"})
    public int size;

    private int[] values;

    @Setup(Level.Trial)
    public void setup() {
        Random random = new Random(1234567L);
        values = new int[size];

        for (int i = 0; i < values.length; i++) {
            values[i] = random.nextInt(1000);
        }
    }

    @Benchmark
    public long sumForLoop() {
        long sum = 0;
        for (int value : values) {
            sum += value;
        }
        return sum;
    }

    @Benchmark
    public long sumIntStream() {
        return Arrays.stream(values).asLongStream().sum();
    }
}
~~~

### 8.1. Những đặc tính tốt của ví dụ

1. **Cùng phép toán**: cả hai tính tổng toàn bộ phần tử và dùng kết quả `long`.
2. **Input được tạo trước vòng đo**: `@Setup(Level.Trial)` tạo mảng một lần mỗi trial.
3. **Dữ liệu không phải hằng số compile-time**: giá trị mảng được sinh từ `Random` trong setup và đọc từ field.
4. **Không có I/O trong timed method**: không in log, không đọc disk hay gọi service.
5. **Kết quả được sử dụng**: phương thức trả `long`, JMH tiêu thụ kết quả để hạn chế dead-code elimination.
6. **Một logical operation là tính tổng một mảng hoàn chỉnh**, không phải cộng một phần tử.
7. **Thay đổi kích thước với `@Param`**: biết liệu kết quả thay đổi khi mảng vượt các mức cache.
8. **`Scope.Thread`**: mỗi worker benchmark có trạng thái riêng, tránh tình cờ thêm tranh chấp dữ liệu.

Ví dụ **không chứng minh Stream nhanh/chậm hơn for trong mọi chương trình**. Cả hai phương án có thể được JIT tối ưu hóa theo hình dạng input và runtime cụ thể. Người đo phải quan sát số liệu thực tế.

### 8.2. Chạy riêng benchmark

Build project đã tạo bằng archetype:

~~~shell
mvn clean verify
~~~

Xem benchmark nào được biên dịch:

~~~shell
java -jar target/benchmarks.jar -l
~~~

Chạy:

~~~shell
java -jar target/benchmarks.jar ArraySumBenchmark -wi 5 -i 7 -f 3 -t 1
~~~

`-wi` là số warmup iterations, `-i` là số measurement iterations, `-f` là số forks, `-t` là số benchmark threads. Các option command line có thể ghi đè cấu hình annotation tương ứng. Để tái lập thí nghiệm, lưu lại cả command line.

### 8.3. Đo cùng work, nhưng không luôn cùng "chi phí"

Hai implementation có thể có profile cấp phát, inlining, vectorization và truy cập cache khác nhau. Nếu muốn đánh giá production workload, phải mô phỏng tần suất gọi, kích thước array và độ biến thiên input của workload đó.

Nếu phiên bản khác dùng `Stream.parallel()`, đây là **một thí nghiệm khác**: cần định nghĩa số core, pool và chi phí chia tác vụ; không so sánh nó với một phép for-loop đơn luồng mà bỏ qua việc sử dụng CPU nhiều hơn.

## 9. Đọc kết quả JMH: Score, Error, Units và parameters

Ví dụ **số liệu giả định để học cách đọc**, không phải kết quả đo trên phần cứng cụ thể:

~~~text
Benchmark                     (size)  Mode  Cnt   Score    Error   Units
ArraySumBenchmark.sumForLoop      128  avgt   21   0.080 ± 0.010  us/op
ArraySumBenchmark.sumIntStream    128  avgt   21   0.130 ± 0.020  us/op
ArraySumBenchmark.sumForLoop     4096  avgt   21   1.100 ± 0.150  us/op
ArraySumBenchmark.sumIntStream   4096  avgt   21   1.250 ± 0.180  us/op
~~~

Lưu ý cấu trúc bảng trên mang tính minh họa; output thực tế phụ thuộc mode và format của JMH.

- **Benchmark**: phương thức được đo.
- **(size)**: tham số `@Param`.
- **Mode = avgt**: `AverageTime`.
- **Cnt**: số kết quả iteration được tổng hợp trong báo cáo (phụ thuộc cấu hình).
- **Score**: điểm ước lượng theo mode.
- **Error**: biên sai số mà JMH tính theo cấu hình thống kê của báo cáo.
- **Units = us/op**: microsecond mỗi invocation.

Điểm thấp hơn thường tốt hơn với **AverageTime**; điểm cao hơn thường tốt hơn với **Throughput**. Không trộn `ops/s` với `us/op` trong một phép so sánh trực tiếp.

**Không được kết luận từ các con số minh họa rằng `for` nhanh hơn `IntStream` trên Java 27.** Hãy đo với JDK, dữ liệu và môi trường thực tế.

### 9.1. Error không phải phần trăm sai số của đồng hồ

Biên `Error` phản ánh độ biến thiên của các số đo được tổng hợp theo phương pháp thống kê mà JMH sử dụng, **không phải cam kết rằng thời gian thực lúc production sẽ nằm trong khoảng đó**.

Hai khoảng error chồng nhau không tự chứng minh hai cách tương đương; hai khoảng không chồng nhau cũng không tự chứng minh một thay đổi có lợi trong production. Hãy xem phân phối qua forks/iterations, hiệu ứng kích thước, và mức độ quan trọng nghiệp vụ.

### 9.2. Không so kết quả giữa những phép đo không cùng điều kiện

Ví dụ đo trên JDK 27 với GC mặc định không nên gộp thành một đồ thị mà không ghi chú cùng kết quả trên một JDK khác dùng bộ thu gom rác hay CPU khác. Điều kiện môi trường là **một phần dữ liệu thí nghiệm**.

## 10. Dead-code elimination (DCE): JIT có thể xóa việc không ai dùng

Một lỗi điển hình:

~~~java
@Benchmark
public void wrong(StateData state) {
    expensivePureComputation(state.value);
    // Không dùng kết quả.
}
~~~

Nếu compiler xác định lời gọi thuần và kết quả không được quan sát, nó có thể loại bỏ toàn bộ hoặc một phần công việc. Benchmark khi đó không còn đo chi phí mong muốn.

Hai cách phổ biến để bảo vệ kết quả:

~~~java
@Benchmark
public long returnResult(StateData state) {
    return expensivePureComputation(state.value);
}
~~~

Hoặc:

~~~java
@Benchmark
public void consumeResult(StateData state, Blackhole blackhole) {
    blackhole.consume(
            expensivePureComputation(state.value)
    );
}
~~~

Các đoạn trên là ví dụ khái niệm: `StateData` và `expensivePureComputation` cần được định nghĩa; `Blackhole` là `org.openjdk.jmh.infra.Blackhole`.

### 10.1. Chọn return hay Blackhole?

- **Return** rất phù hợp khi benchmark tạo ra một kết quả cần kiểm tra/tiêu thụ; JMH có thể dùng nó để hạn chế DCE.
- **`Blackhole.consume(...)`** phù hợp khi một invocation sinh nhiều giá trị hoặc muốn làm rõ đầu ra của công việc.
- Không thêm `Blackhole` tùy tiện vào mọi dòng code: việc tiêu thụ có overhead và có thể thay đổi cấu trúc tối ưu hóa đang muốn đo.

**JMH không thể bảo vệ một phép tính mà bạn đã vô tình xóa khỏi workload**. Nếu mã trả về giá trị không liên quan hoặc dữ liệu bị coi như hằng, kết quả vẫn có thể sai bản chất.

## 11. Constant folding: dữ liệu đầu vào quá dễ dự đoán

Ví dụ nguy hiểm:

~~~java
@Benchmark
public int suspicious() {
    return 10 * 20;
}
~~~

JIT có thể thay phép nhân bằng hằng số 200. Kết quả rất nhanh nhưng không phản ánh chi phí nhân hai biến đầu vào thực tế.

Trường hợp tinh vi hơn:

~~~java
private static final int CONSTANT = 42;

@Benchmark
public int suspiciousWithMethod() {
    return transform(CONSTANT);
}
~~~

Nếu `transform` được inline và là hàm thuần, compiler có thể tính trước hoặc đơn giản hóa mạnh.

### 11.1. Cách tránh

- Sử dụng `@State` chứa dữ liệu được tạo trước thời gian đo.
- Chọn input có độ biến thiên phù hợp, không làm bài toán vô nghĩa.
- Nếu cần kiểm tra nhiều cỡ dữ liệu, dùng `@Param`.
- Bảo đảm phép toán thực sự được gọi trong timed path.
- Kiểm tra kết quả logic bằng test riêng.

Dữ liệu cố định có seed xác định giúp tái lập, nhưng **không đồng nghĩa mọi hình dạng input đều đại diện cho thực tế**. Với parser, cần thêm input phổ biến, input hiếm, input có lỗi và kích thước lớn; với thuật toán sort, cần random, sorted, reverse, nhiều duplicate, v.v.
## 12. Đừng tự lặp micro-operation trong một vòng lặp khổng lồ

Một cách đo dễ sai là nhân một phép toán rất nhỏ thành hàng triệu lần rồi lấy tổng thời gian chia cho số lần:

~~~java
@Benchmark
public long misleadingLoop() {
    long total = 0;
    for (int i = 0; i < 1_000_000; i++) {
        total += smallOperation(i);
    }
    return total;
}
~~~

Đoạn trên có thể **đúng** nếu toàn bộ vòng lặp là workload cần nghiên cứu. Nhưng nếu muốn biết chi phí của **một lời gọi độc lập**, JIT có thể inline, unroll, vectorize, gộp phép tính qua các vòng hoặc biến đổi thuật toán theo cách không xảy ra khi một lần gọi được thực hiện riêng.

Mẫu cần ưu tiên khi đo từng lời gọi:

~~~java
@Benchmark
public long oneOperation(InputState state) {
    return smallOperation(state.value);
}
~~~

`InputState` và `smallOperation` chỉ là thành phần minh họa. Khi muốn đo phép cộng cực nhỏ, để **JMH lặp những invocation** theo harness, thay vì cố tự khử overhead bằng một vòng lặp không kiểm soát.

### 12.1. @OperationsPerInvocation không bảo vệ khỏi tối ưu hóa

`@OperationsPerInvocation(N)` thông báo rằng một invocation làm N logical operations để JMH chuẩn hóa kết quả. Nó **không** bảo đảm JIT thật sự thực thi N lần như người viết tưởng. Nếu vòng lặp bị hoist hoặc constant folded, chia cho N chỉ tạo ra một con số sai với vẻ ngoài hợp lý.

Khi cả tác vụ thực tế là “tính tổng một mảng”, một invocation xử lý hết mảng là hợp lệ. Nhưng nếu bạn muốn so chi phí **mỗi phép cộng**, đó là câu hỏi khác và cần thiết kế khác.

## 13. @State và phạm vi chia sẻ

`@State` không chỉ giúp JMH cấp phát input. Nó còn quyết định **thread nào dùng chung dữ liệu**, từ đó có thể thay đổi kết quả do contention và cache.

| Scope | Ý nghĩa | Khi thích hợp |
|---|---|---|
| `Scope.Thread` | Mỗi JMH worker có state riêng | Benchmark đơn luồng không chủ ý chia sẻ dữ liệu |
| `Scope.Benchmark` | Các worker của cùng benchmark chia sẻ state | Counter/lock/cache có tranh chấp |
| `Scope.Group` | Những worker trong cùng một group chia sẻ state | Reader/writer hoặc producer/consumer |

Ví dụ:

~~~java
@State(Scope.Thread)
public static class PrivateState {
    int value;
}

@State(Scope.Benchmark)
public static class SharedState {
    int value;
}
~~~

Với `PrivateState`, mỗi worker có `value` riêng. Với `SharedState`, nhiều worker có thể cùng chạm một field. `@State` **không** làm phép `state.value++` tự trở thành atomic: nếu cùng sửa `SharedState` mà thiếu đồng bộ, vẫn là data race.

Để đo thuật toán thuần, thường bắt đầu bằng `Scope.Thread`. Để đo contention, cố ý chọn phạm vi chia sẻ và cấu trúc thread-safe.

## 14. @Param và sự phân bố dữ liệu

Một tham số không đủ để kết luận một thuật toán nhanh/chậm nói chung.

~~~java
@Param({"64", "1024", "16384"})
public int size;
~~~

Mỗi size trở thành một trường hợp thí nghiệm. Có thể thêm một tham số nữa:

~~~java
@Param({"RANDOM", "SORTED"})
public String distribution;
~~~

Khi có nhiều `@Param`, JMH tạo ma trận combination phù hợp. Nhưng ma trận 5 kích thước × 4 kiểu dữ liệu × 4 số thread × 3 forks có thể tốn thời gian lớn; hãy chọn trường hợp đại diện trước.

### 14.1. Dữ liệu tái lập được nhưng không giả tạo

~~~java
@Setup(Level.Trial)
public void setup() {
    Random random = new Random(8675309L);
    values = new int[size];
    for (int i = 0; i < size; i++) {
        values[i] = random.nextInt();
    }
}
~~~

Seed cố định giúp trial tái lập, nhưng một seed và một distribution có thể không đại diện production. Với sort, cần thử dữ liệu random, đã sắp xếp, đảo ngược, nhiều giá trị trùng; với parser, cần cả chuỗi phổ biến và trường hợp khó.

Không đặt `random.nextInt()` trong timed method nếu mục tiêu chỉ là đo thuật toán nhận input, vì khi đó benchmark còn đo cả random generation.

### 14.2. Kiểm soát dữ liệu lớn/cold cache

Một mảng nhỏ được duyệt liên tục có thể nằm gần như hoàn toàn trong CPU cache. Trong production, hệ thống có thể đọc nhiều tập dữ liệu không lặp lại. Nên khảo sát các kích thước vượt qua mức cache, hoặc thiết kế dataset/working set phản ánh thực tế thay vì chỉ đo cùng 128 phần tử.

## 15. Tính đúng trước, tốc độ sau

Trước khi đo A so với B, phải xác nhận hai phương án thực hiện **hợp đồng tương đương**:

- Cùng đầu vào hợp lệ và bất thường.
- Cùng kiểu kết quả (kể cả overflow, NaN, độ chính xác).
- Cùng chính sách lỗi và validation.
- Cùng phạm vi công việc được tính thời gian.
- Trạng thái ban đầu tương đương cho mỗi iteration/invocation.

Nếu một parser bỏ qua xác thực mà parser khác kiểm tra schema đầy đủ, một kết quả `ns/op` tốt hơn không chứng minh phương án đầu phù hợp hơn.

### 15.1. State bị thay đổi sau mỗi lần gọi

~~~java
@Benchmark
public int removeFirst(MyState state) {
    return state.list.remove(0);
}
~~~

Nếu list cạn dần trong quá trình đo, mỗi invocation có đầu vào khác và cuối cùng có thể lỗi. `MyState` phải được định nghĩa và chiến lược reset cần phù hợp. Có thể dùng trạng thái vòng lặp ổn định, `@Setup(Level.Iteration)` hoặc `@Setup(Level.Invocation)` nếu thực sự cần, nhưng phải biết việc reset ảnh hưởng cache/GC thế nào.

**Không đặt `System.gc()` trong setup mỗi invocation** với ý định làm sạch phép đo. Đây có thể là nguồn nhiễu lớn, không phải cách khôi phục trạng thái chuẩn.

## 16. @Setup và @TearDown ở các cấp khác nhau

| Level | Thời điểm | Phù hợp |
|---|---|---|
| `Level.Trial` | Trước/sau toàn bộ trial | Tạo dataset hoặc tài nguyên dài hạn |
| `Level.Iteration` | Trước/sau từng iteration | Đặt lại dữ liệu giữa các khoảng đo |
| `Level.Invocation` | Trước/sau từng lời gọi timed method | Reset state không tái sử dụng được; cần cực kỳ cẩn thận |

Ví dụ một benchmark sort cần mảng chưa được sắp xếp trước mỗi invocation:

~~~java
@State(Scope.Thread)
public static class SortState {
    @Param({"1000", "10000"})
    public int size;

    private int[] original;
    int[] scratch;

    @Setup(Level.Trial)
    public void prepare() {
        Random random = new Random(12345L);
        original = new int[size];
        for (int i = 0; i < size; i++) {
            original[i] = random.nextInt();
        }
    }

    @Setup(Level.Invocation)
    public void reset() {
        scratch = original.clone();
    }
}
~~~

Code trên có ý nghĩa minh họa; cần các import JMH và Java thích hợp. Clone nằm trong setup, nhưng vẫn **thay đổi locality, cache và áp lực GC**. Nếu production phải copy rồi sort, phải tính cả copy trong timed method thay vì loại bỏ khỏi số đo.

JMH hỗ trợ `Level.Invocation`, nhưng overhead và tính tương tác giữa setup/measurement có thể đáng kể. Đừng chọn nó chỉ vì muốn benchmark “trông công bằng”; hãy mô tả chính xác công việc cần đo.

## 17. Benchmark đa luồng cần thiết kế contention có chủ đích

Benchmark CPU với một thread không đại diện cho lock/counter trong ứng dụng nhiều thread.

Ví dụ hoàn chỉnh so sánh **chỉ thao tác cập nhật counter** trong tình huống nhiều JMH worker cùng sửa một đối tượng dùng chung:

~~~java
package dev.example.bench;

import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.LongAdder;

import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.BenchmarkMode;
import org.openjdk.jmh.annotations.Fork;
import org.openjdk.jmh.annotations.Level;
import org.openjdk.jmh.annotations.Measurement;
import org.openjdk.jmh.annotations.Mode;
import org.openjdk.jmh.annotations.OutputTimeUnit;
import org.openjdk.jmh.annotations.Scope;
import org.openjdk.jmh.annotations.Setup;
import org.openjdk.jmh.annotations.State;
import org.openjdk.jmh.annotations.Warmup;

@State(Scope.Benchmark)
@BenchmarkMode(Mode.Throughput)
@OutputTimeUnit(TimeUnit.SECONDS)
@Warmup(iterations = 5, time = 1, timeUnit = TimeUnit.SECONDS)
@Measurement(iterations = 5, time = 1, timeUnit = TimeUnit.SECONDS)
@Fork(3)
public class CounterContentionBenchmark {

    private AtomicLong atomic;
    private LongAdder adder;

    @Setup(Level.Trial)
    public void setup() {
        atomic = new AtomicLong();
        adder = new LongAdder();
    }

    @Benchmark
    public void atomicIncrement() {
        atomic.incrementAndGet();
    }

    @Benchmark
    public void adderIncrement() {
        adder.increment();
    }
}
~~~

Chạy riêng với các cấu hình thread:

~~~shell
java -jar target/benchmarks.jar CounterContentionBenchmark -t 1 -f 3
java -jar target/benchmarks.jar CounterContentionBenchmark -t 4 -f 3
java -jar target/benchmarks.jar CounterContentionBenchmark -t 8 -f 3
~~~

Các benchmark method có side effect lên state dùng chung; không cần tạo return giả chỉ để hiển thị. Nhưng **AtomicLong và LongAdder không có cùng hợp đồng đọc**: `LongAdder.sum()` không là snapshot nguyên tử dưới cập nhật đồng thời. Số `ops/s` cho riêng phép tăng không chứng minh chúng thay thế nhau trong mọi tác vụ nghiệp vụ.

### 17.1. Chọn Scope.Benchmark thay vì Scope.Thread khi đo contention

Nếu mỗi worker có một counter riêng, bạn đang đo cập nhật **không tranh chấp**. Để đo một counter bị nhiều thread sửa, cần sử dụng cùng một `@State(Scope.Benchmark)` hoặc nhóm worker phù hợp.

### 17.2. @Group cho reader/writer

JMH hỗ trợ `@Group` và `@GroupThreads` để định nghĩa một tập tác vụ hoạt động cùng lúc, chẳng hạn ba reader và một writer:

~~~java
@Benchmark
@Group("readMostly")
@GroupThreads(3)
public long read(GroupState state) {
    return state.counter.get();
}

@Benchmark
@Group("readMostly")
@GroupThreads(1)
public void write(GroupState state) {
    state.counter.incrementAndGet();
}
~~~

Đây là mẫu minh họa; `GroupState` phải được định nghĩa có `@State(Scope.Group)` và `AtomicLong counter`. Kết quả của từng role cần được diễn giải trong bối cảnh tổng nhóm, không so kiểu cộng đơn thuần các score.

### 17.3. False sharing

Hai thread ghi các biến khác nhau vẫn có thể chậm nếu các biến nằm trên cùng cache line, gây **false sharing**. Đây không nhất thiết là data race. Khi kết quả đa luồng bất thường, xem cả layout dữ liệu, worker placement, CPU topology và contention. OpenJDK JMH có sample riêng cho hiện tượng này.

## 18. JIT có thể thay đổi đúng code đang được đo

Một số tối ưu JVM quan trọng:

| Hiện tượng | Tác động đến benchmark |
|---|---|
| Inlining | Loại bỏ overhead lời gọi và mở đường tối ưu khác |
| Escape analysis | Một allocation có thể không cần thực hiện như code nguồn gợi ý |
| Scalar replacement | Trạng thái object được biểu diễn như các giá trị riêng |
| Loop unrolling/vectorization | Lặp nhiều thao tác khác biệt một invocation độc lập |
| Loop-invariant code motion | Hoist phép toán không đổi ra khỏi vòng lặp |
| Tiered compilation | Thay đổi code máy trong quá trình warmup/measurement |
| Deoptimization | JVM loại bỏ giả định tối ưu không còn đúng |
| Profile pollution | Những lần chạy khác tác động đến cách JIT tối ưu |

Fork giúp tách lịch sử JIT và trạng thái JVM giữa trial nhưng **không xóa nhiễu ở cấp hệ điều hành**.

### 18.1. Không tắt JIT làm giải pháp chung

`-Xint` hoặc các flag điều khiển compiler có thể hữu ích để kiểm chứng một giả thuyết nghiên cứu. Nhưng chạy interpreter-only thường không phản ánh ứng dụng production sử dụng JIT.

Nếu benchmark có điểm số khó tin, sửa input và kết quả được quan sát trước; không mặc định tắt compiler để “ngăn tối ưu hóa”.

### 18.2. @CompilerControl chỉ dùng cho câu hỏi hẹp

JMH cung cấp `@CompilerControl` để chủ động thay đổi một số quyết định compilation. Cấm inline có thể giúp đo overhead lời gọi không inline, nhưng **không** còn là measurement cho đường đi đã được JVM tối ưu như production. Dùng có chủ đích và ghi rõ điều kiện.

## 19. GC, allocation và bộ nhớ được giữ lại là các đại lượng khác nhau

Hai phương án có `us/op` gần nhau nhưng profile allocation khác nhau. Trên service chạy dài, allocation cao có thể tăng GC overhead và ảnh hưởng tail latency.

JMH hỗ trợ GC profiler:

~~~shell
java -jar target/benchmarks.jar ArraySumBenchmark -prof gc -f 3
~~~

Trong những cấu hình được hỗ trợ, profiler có thể bổ sung:

- `gc.alloc.rate`: tốc độ cấp phát được quan sát.
- `gc.alloc.rate.norm`: byte cấp phát chuẩn hóa theo operation, thường hiển thị B/op.
- `gc.count`, `gc.time`: GC activity trong phần đo.

Danh sách profiler và một số metric tùy thuộc phiên bản JMH/JVM/OS:

~~~shell
java -jar target/benchmarks.jar -lprof
~~~

### 19.1. B/op không phải retained memory

Một operation có thể cấp phát hàng nghìn byte rồi giải phóng nhanh, hoặc không cấp phát trong timed method nhưng giữ một cache lớn ở `@Setup`.

Phân biệt **allocation rate**, **live/retained heap**, **off-heap memory** và **tổng RSS của process**. Để đánh giá memory leak cần đo theo thời gian và kiểm tra heap/native memory, không chỉ dựa vào `gc.alloc.rate.norm`.

### 19.2. Không ép System.gc() để “ổn định”

~~~java
System.gc();
long start = System.nanoTime();
operation();
~~~

Không có bảo đảm `System.gc()` sẽ tạo một trạng thái đo cố định; lời gọi có thể bị bỏ qua hoặc tác động mạnh đến cache/heap. Đây không phải phương pháp mặc định cho benchmark ổn định.

## 20. Môi trường hệ thống tạo nhiễu như thế nào?

| Yếu tố | Rủi ro |
|---|---|
| JDK vendor/build | Khác biệt JIT, GC hoặc class library |
| CPU model/architecture | Cache, memory bandwidth, instruction set |
| Turbo boost/governor | Tần số CPU biến thiên giữa các runs |
| Thermal throttling | CPU nóng làm kết quả run sau bất lợi |
| Hyperthreading/SMT | Các worker tranh chấp execution resources |
| NUMA | Truy cập bộ nhớ của NUMA node khác chậm hơn |
| Background load | CPU scheduler/IO/cache bị cạnh tranh |
| Container quotas/cpuset | “8 threads” không tương đương 8 core độc quyền |
| Heap/GC flags | GC behavior và allocation latency |
| Disk page cache | Warm cache vs cold storage |
| OS/kernel | Scheduling, page fault, timer |
| IDE/debugger/profiler | Thêm instrumentation và overhead |

Một phép đo đáng tin cậy cần **điều kiện ổn định và được ghi lại**. Laptop đang mở IDE/trình duyệt phù hợp để khám phá, nhưng không phải bằng chứng cuối cho workload server trên phần cứng khác.

### 20.1. Thứ tự A rồi B có thể gây thiên lệch

Nếu đo A trước rồi B khi CPU đã nóng hoặc power mode đổi, B có thể chậm chỉ vì điều kiện môi trường. Hãy chạy nhiều fork, thử lại vào thời điểm khác và có thể xen kẽ thứ tự trong chiến dịch đo dài; nếu theo dõi nhiệt độ/tần số, ghi vào metadata.

## 21. Đọc Score, Error và ý nghĩa thống kê

Ví dụ giả định:

~~~text
Method A: 1.01 us/op, Error ± 0.10 us/op
Method B: 0.98 us/op, Error ± 0.11 us/op
~~~

Đây **không phải số đo thực trên Java 27**. Chênh lệch trung bình nhỏ so với độ biến thiên, nên không đủ cơ sở để quảng bá B tốt hơn.

- `Score` phải được đọc cùng **Mode, Unit, @Param, thread count**.
- `Error` là biên bất định thống kê theo cách JMH tổng hợp số đo, không phải sai số tuyệt đối của `System.nanoTime`.
- Nhiều invocation trong cùng iteration **không phải** nhiều mẫu độc lập hoàn toàn.
- Kết quả ở nhiều forks đáng quan tâm hơn một điểm số duy nhất.
- Một sai lầm trong workload vẫn có thể cho `Error` cực nhỏ nếu JIT đã tối ưu bỏ công việc.

### 21.1. Practical significance

Ngay cả khi khác biệt ổn định, việc tăng tốc một method nhỏ có thể không ảnh hưởng toàn bộ hệ thống. Xác định trước một ngưỡng cải thiện có ý nghĩa, ví dụ giảm CPU cost đủ lớn để thay đổi số core cần triển khai hoặc giảm tail latency được đo bằng load test.

### 21.2. Amdahl's law

Nếu `parse()` chỉ chiếm 20% thời gian request và được tăng tốc gấp đôi, tốc độ tối đa toàn request trong mô hình lý tưởng:

\[
S = \frac{1}{(1-p)+p/s}
  = \frac{1}{0.8+0.2/2}
  \approx 1.11
\]

Nghĩa là khoảng **11%** tăng tốc toàn request, không phải 100%. Trong production, tranh chấp, queue, GC và I/O có thể làm kết quả khác. Dùng profiler để biết tối ưu hóa đang nhắm đúng điểm nóng không.

## 22. Xuất kết quả và lưu metadata thí nghiệm

JMH hỗ trợ xuất JSON:

~~~shell
java -jar target/benchmarks.jar ArraySumBenchmark -wi 5 -i 7 -f 3 -t 1 -rf json -rff result-array-sum.json
~~~

Ngoài file JSON, hãy lưu:

| Trường | Vì sao quan trọng |
|---|---|
| Source revision / commit | Biết chính xác mã đã đo |
| JMH version | Reproduce harness behavior |
| Java runtime và JVM flags | JIT/GC/heap/runtime options |
| CPU, số core, SMT, NUMA | Giải thích contention và cache |
| OS và container quota | Scheduling, resource limits |
| Benchmark command line | Forks, iterations, mode, threads |
| Input size/distribution/seed | Biết phép thử dùng dữ liệu nào |
| Profiler đang bật | Overhead và chỉ số phụ |
| Raw result files | Kiểm tra phân phối/thử nghiệm sau |
| Ngày giờ và môi trường tải | Giải thích biến động giữa runs |

Không coi file JSON của JMH là kho metadata đầy đủ tự động. Cần lưu riêng thông tin thí nghiệm và log tương ứng.
## 23. Phương pháp A/B: biến benchmark thành một thí nghiệm có thể phản biện

Thay vì chỉ đo “phương án mới nhanh hơn”, hãy mô tả thí nghiệm theo cấu trúc:

| Thành phần | Ví dụ |
|---|---|
| Giả thuyết | Cách B giảm chi phí parse với input 4 KiB |
| Biến độc lập | Implementation A hoặc B |
| Biến kiểm soát | Cùng dataset, JDK, JMH, heap, threads, máy |
| Đại lượng chính | Thời gian trung bình mỗi parse |
| Đại lượng phụ | B/op, GC activity |
| Điều kiện đại diện | Dữ liệu phân bố theo traffic production |
| Tiêu chí chấp nhận | Kết quả đúng và cải thiện đủ lớn, ổn định qua nhiều fork |
| Kế hoạch xác nhận | Chạy load test trên service thật |

Một thí nghiệm tốt có **control**, baseline và câu hỏi định sẵn trước khi nhìn số liệu. Tránh thay đổi input, GC flags hoặc kích thước heap sau khi thấy kết quả không như mong muốn mà vẫn gộp tất cả vào một kết luận duy nhất.

### 23.1. Đo cả baseline và treatment

Giả sử có hai cách parse cùng một format:

~~~java
@Benchmark
public ParsedRecord baseline(ParseState state) {
    return parseOriginal(state.input);
}

@Benchmark
public ParsedRecord treatment(ParseState state) {
    return parseOptimized(state.input);
}
~~~

Đoạn code minh họa; `ParsedRecord`, `ParseState` và hai hàm parser cần được định nghĩa. Phải kiểm tra output và lỗi của hai parser có tương đương cho các input đã chọn. Việc benchmark trả `ParsedRecord` giúp JMH quan sát đầu ra nhưng **không thay thế unit test correctness**.

### 23.2. Tránh thay đổi nhiều thứ cùng lúc

Nếu phương án B vừa đổi algorithm, thay cache, thêm thread và đổi GC, kết quả dù tốt cũng khó quy cho nguyên nhân nào. Tách các thay đổi khi có thể:

1. Đo baseline.
2. Đổi thuật toán, giữ nguyên môi trường.
3. Đổi chính sách allocation, giữ nguyên thuật toán.
4. Thử cấu hình thread riêng.
5. Cuối cùng đánh giá combination trong workload thực.

Trong các hệ thống phức tạp, interaction effects có thể tồn tại. Việc tách bước không đảm bảo tổng hiệu quả của các thay đổi bằng phép cộng đơn giản; cần một phép đo tích hợp cuối.

## 24. Chọn workload và đơn vị đo đúng cho từng bài toán

### 24.1. Parser và serializer

Một operation nên là parse/serialize một tài liệu có kích thước và hình dạng xác định. Ghi rõ:

- Tài liệu có hợp lệ hay không.
- Kích thước tính bằng byte hay ký tự.
- Cấu trúc nông/sâu và số trường.
- Có tạo object output không.
- Có validation hay caching không.

Không chỉ dùng chuỗi ASCII cực ngắn nếu production xử lý JSON nhiều tầng với Unicode.

### 24.2. Collection và thuật toán

Với `HashMap` hoặc `TreeMap`, input nên gồm các tình huống hit/miss và phân bố khóa có ý nghĩa. Benchmark chỉ lookup một khóa cố định trên một map nhỏ có thể phản ánh CPU cache hơn là sản phẩm.

Với sort, phải kiểm soát trạng thái input giữa các invocation. Nếu sort đi sort lại chính mảng đã sắp xếp, bạn đang đo workload khác.

### 24.3. I/O và network

Benchmark method có network hay file I/O thật **có thể dùng JMH**, nhưng kết quả lúc đó có thể bị chi phối bởi network, server, file cache, đồng bộ storage và shared resources.

Để đo end-to-end latency, thường cần một công cụ load test/metrics hệ thống phù hợp, với controlled arrival rate, concurrency và queueing. JMH tự động gọi phương thức càng nhanh càng tốt trong nhiều mode; điều đó không mô phỏng mọi **mô hình yêu cầu đến từ bên ngoài**.

### 24.4. Virtual threads và executor

So sánh `Executors.newVirtualThreadPerTaskExecutor()` với fixed platform-thread pool chỉ có ý nghĩa khi xác định:

- Số tác vụ đồng thời, tỷ lệ I/O vs CPU.
- Giới hạn connection hoặc tài nguyên ngoài.
- Có blocking I/O hay không.
- Có tạo executor trong mỗi timed invocation hay tái sử dụng.
- Có đo toàn thời gian tạo/đóng executor theo workload thực không.
- Có chờ tất cả task hoàn thành trước khi trả kết quả không.

Không dùng `Thread.sleep` để đại diện cho CPU work; `sleep` chủ yếu mô phỏng chờ. Một microbenchmark cho 10.000 virtual threads ngủ không chứng minh 10.000 tác vụ CPU cùng xử lý sẽ nhanh hơn.

## 25. Profiler bổ sung: tìm nguyên nhân thay vì chỉ nhìn điểm số

JMH trả lời “bao nhiêu” ở workload đã thiết kế. Khi muốn biết “vì sao”, hãy sử dụng profiler với ý thức về overhead.

### 25.1. JMH profiler

Liệt kê profiler khả dụng:

~~~shell
java -jar target/benchmarks.jar -lprof
~~~

GC profiler phổ biến:

~~~shell
java -jar target/benchmarks.jar ArraySumBenchmark -prof gc -f 3
~~~

Trên những môi trường có hỗ trợ, JMH có thể cung cấp profiler cho stack, compiler hoặc hardware events. **Danh sách và khả năng dùng thay đổi theo OS/JVM/quyền**, vì vậy không ghi sẵn một tên profiler không kiểm tra như thể chạy được ở mọi máy.

Profiler có thể làm thay đổi tải CPU, code layout và kết quả. Khi đưa ra kết luận so sánh latency, thường chạy thêm **benchmark không bật profiler**.

### 25.2. Java Flight Recorder (JFR)

JFR là cơ chế profiling/observability hiện hành của JDK, có thể hỗ trợ xem:

- Allocation và GC.
- CPU samples và method activity.
- Thread events, blocking và synchronization.
- I/O hoặc sự kiện runtime được hỗ trợ.

Một ứng dụng Java thông thường có thể khởi động với recording phù hợp:

~~~shell
java -XX:StartFlightRecording=filename=recording.jfr,dumponexit=true -jar app.jar
~~~

Đây là **ví dụ chẩn đoán một ứng dụng thực tế**, không phải lệnh thay thế trực tiếp cho việc chạy `target/benchmarks.jar` ở mọi tình huống. Khi phân tích benchmark JMH, nên hiểu vòng đời forks (các JVM con) và dùng cấu hình profiler phù hợp từng fork nếu cần.

### 25.3. Dùng profiler để kiểm tra giả thuyết

Ví dụ:

> B giảm AverageTime nhưng tăng `gc.alloc.rate.norm` và tạo nhiều GC hơn.

Khi đó nên xem:

- B có cấp phát đối tượng tạm mới không?
- Escape analysis có bị vô hiệu hóa bởi cấu trúc code B không?
- Input size nào làm B chậm đi?
- B có tăng dữ liệu giữ sống trong heap không?
- Những lần chạy cùng GC/heap có lặp lại xu hướng không?

Benchmark và profiler nên hỗ trợ nhau; **không diễn giải một chỉ số phụ thành nguyên nhân duy nhất khi chưa có bằng chứng**.

## 26. Bảng những lỗi benchmark phổ biến

| Lỗi | Triệu chứng | Hướng xử lý |
|---|---|---|
| Không tiêu thụ kết quả | `ns/op` phi lý hoặc gần bằng baseline trống | Trả kết quả hoặc dùng `Blackhole` |
| Input toàn hằng số | JIT constant folding | `@State` và input có ý nghĩa |
| Tự lặp hàng triệu lần | Điểm giảm mạnh khi tăng số vòng | Cho JMH quản lý số invocation |
| Chỉ chạy một lần | Kết quả biến động rất lớn | Warmup, nhiều iteration/fork |
| Chỉ một fork với môi trường nhiễu | Phụ thuộc JIT/OS | Tăng số fork, chạy lại |
| Chạy trực tiếp trong IDE/debugger | Instrumentation và môi trường khó kiểm soát | JMH JAR từ CLI |
| State dùng chung ngoài ý muốn | Contention làm chậm thuật toán vốn độc lập | `Scope.Thread` khi phù hợp |
| Muốn đo contention nhưng dùng state riêng | Không có sharing | `Scope.Benchmark` hoặc `Scope.Group` |
| State bị cạn/thay đổi | Invocation sau khác đầu | Thiết kế reset/lifecycle |
| Reset input không kiểm soát | Cache và allocation bị méo | Định nghĩa rõ phạm vi công việc |
| Đo cả log hoặc console | I/O che lấp CPU cost | Đưa log ra ngoài timed method |
| Đo cả random generation ngoài ý muốn | Kết quả không chỉ phản ánh thuật toán | Sinh input trước |
| So thuật toán đúng với thuật toán bỏ validation | Đối chiếu không tương đương | Unit tests và cùng contract |
| Không kiểm tra GC | Thời gian tốt nhưng allocation quá cao | `-prof gc` và memory profile |
| Thay JVM flags giữa A và B | Sai phép đối chứng | Giữ môi trường cố định |
| CPU nóng trong run B | B chậm vì throttling | Nhiều lượt, xen kẽ, theo dõi nhiệt độ |
| Chạy song song nhiều benchmark CPU | Cạnh tranh CPU/cache | Cách ly benchmark process |
| Một size rất nhỏ | Kết luận sai cho dữ liệu lớn | `@Param` theo working set |
| Dùng throughput thay latency production | Bỏ qua queue và network | Load test end-to-end |
| Lấy Error nhỏ làm bằng chứng đúng | Benchmark sai nhưng ổn định | Review workload, correctness, DCE |
| Lưu mỗi Score | Không tái lập được | Lưu raw output và metadata |
| Không xem số core/quota container | Thread count không đại diện | Ghi CPU topology và limits |
| Quên rằng JMH là thư viện riêng | Build lỗi do thiếu generator | Dùng official archetype |
| Cố ép `System.gc()` | Nhiễu GC/cache lớn | Thiết kế workload và kiểm soát heap |

Không có một cấu hình JMH thần kỳ tránh được mọi lỗi. Các bẫy tương tác với nhau; một thí nghiệm cần được review như code production.

## 27. Quy trình thực tế từ ý tưởng đến quyết định

**Bước 1 — Xác định vấn đề.** Dựa vào production profiling, metrics hoặc một giả thuyết kỹ thuật cụ thể. Không tối ưu theo cảm giác.

**Bước 2 — Viết hợp đồng.** Xác định input, output, tính đúng, latency/throughput, số thread và số thao tác được đo.

**Bước 3 — Chuẩn bị code.** Tách benchmark vào module riêng, dùng JMH archetype, unit test correctness, không đặt log trong timed method.

**Bước 4 — Thiết lập state.** Chọn `@State`, `@Param`, seed, `@Setup` và giới hạn bộ nhớ. Tránh dataset bị biến đổi không chủ đích qua các invocation.

**Bước 5 — Chạy thử.** Chạy một số combination nhỏ, xác nhận harness hoạt động và phép toán trả kết quả có ý nghĩa.

**Bước 6 — Thu thập chính thức.** Thiết lập warmup, measurement, forks, mode và threads; kiểm soát môi trường, xuất JSON.

**Bước 7 — Kiểm tra tính hợp lệ.** Xem outliers, log lỗi, GC activity, JIT-related pitfalls và sự ổn định của các forks.

**Bước 8 — Rút kết luận hẹp.** Viết rõ “Trong điều kiện X, với input Y và metric Z, A có kết quả…” thay vì “A luôn nhanh hơn B”.

**Bước 9 — Xác nhận trên workload lớn hơn.** Chạy component/load tests, profiler và đánh giá memory/GC/production risk.

**Bước 10 — Lưu artifact.** Commit benchmark, kết quả thô, command line và metadata; làm cho một người khác có thể tái hiện.

## 28. Case study: benchmark lựa chọn cách parse bản ghi

Giả sử một service nhận hàng triệu dòng CSV ngắn. Bạn đang cân nhắc thay parser A bằng parser B.

### 28.1. Thiết kế sai

- Benchmark một chuỗi cố định `"a,b,c"`.
- Parser B bỏ qua xử lý escaped quote mà parser A có hỗ trợ.
- Mỗi invocation in kết quả ra console.
- Chạy đúng một lần trên laptop đang chạy IDE.
- Kết luận B nhanh gấp 3 từ một điểm số.

Tất cả yếu tố trên đều có thể khiến kết luận không có ý nghĩa production.

### 28.2. Thiết kế phù hợp hơn

1. Phân loại input: 3, 20, 100 cột; có/không có quoted field; ASCII/Unicode; dòng hợp lệ và lỗi.
2. Đảm bảo A/B xử lý cùng schema và lỗi theo hợp đồng.
3. `@Param` chọn loại input và số cột.
4. Tạo dữ liệu ở `@Setup(Level.Trial)` với seed xác định.
5. Đo một logical operation là parse một record.
6. Dùng `@BenchmarkMode(Mode.AverageTime)` cho service time, thêm `-prof gc` để xem allocation.
7. Chạy nhiều forks và lưu raw results.
8. Kiểm tra thay đổi độ lớn của lợi ích qua input shapes.
9. Đo lại trong pipeline thực với queue, I/O và GC.

### 28.3. Báo cáo mẫu không chứa số đo giả

Một báo cáo nên có định dạng:

~~~text
Giả thuyết: Parser B giảm chi phí CPU cho bản ghi có quoted fields.
JDK: [vendor/build Java 27 thực tế]
JMH: [version]
CPU/OS/heap/GC: [thông số máy đo]
Benchmark: [class/method]
Input: [format, kích thước, seed, phân bố]
Mode: AverageTime
Warmup: [số iteration, thời lượng]
Measurement: [số iteration, thời lượng]
Forks: [số forks]
Raw result: [đường dẫn JSON]
Kết quả: [score/error A và B sau đo]
Correctness: [các test đã chạy]
Kết luận: [chỉ phạm vi có bằng chứng]
Giới hạn: [những workload chưa thử]
~~~

**Không điền trước một điểm số tùy ý để làm “kết quả Java 27”**. Ví dụ kết quả ở mục 9 và 21 chỉ để minh họa cách đọc, không được dùng làm kết quả thực nghiệm.

## 29. CI benchmark và ngưỡng regression

Có thể đưa benchmark vào CI để phát hiện thay đổi hiệu năng đáng kể, nhưng môi trường shared CI thường biến động:

- CPU chia sẻ với runner khác.
- Cache và frequency không đồng nhất.
- JVM startup noise.
- Container quota thay đổi.
- Số mẫu quá ít để CI chạy nhanh.

Một pipeline hợp lý có thể tách:

- **Smoke benchmark:** kiểm tra code biên dịch, chạy được và không ném lỗi; thời lượng ngắn.
- **Đo chính thức:** máy đo chuyên dụng hoặc hạ tầng ổn định, nhiều iterations/forks.
- **Regression investigation:** chỉ cảnh báo khi khác biệt vượt ngưỡng đủ lớn và được lặp lại.

Tránh đặt gate cứng `"ns/op phải chính xác dưới X"` trên shared runner khi môi trường không đủ ổn định. Kết quả CI nên đi kèm metadata và đường dẫn raw results.

### 29.1. Nên lưu artifact theo từng lần chạy

~~~text
bench-results/
└── run-id/
    ├── jmh-results.json
    ├── environment.txt
    ├── benchmark-command.txt
    ├── source-revision.txt
    └── analysis.md
~~~

Cấu trúc trên chỉ minh họa artifact đầu ra của **một workflow benchmark**; bài học hiện tại không tạo hoặc thay đổi những file đó.

## 30. Những câu hỏi thường gặp

### 30.1. Có cần đặt @Fork trên từng method không?

Không bắt buộc. Có thể đặt annotation ở class để áp dụng cấu hình chung, và chỉ override khi một method có yêu cầu riêng. Điều quan trọng là báo cáo và CLI ghi rõ số fork cuối cùng.

### 30.2. @Warmup 10 lần có luôn tốt hơn 5 lần?

Không. Thời lượng warmup đủ hay không phụ thuộc workload và JVM profile. Quan sát kết quả iteration, allocation và tình trạng JIT thay đổi; tăng thời gian nếu cần, không chọn theo con số cố định.

### 30.3. Có nên luôn dùng Mode.Throughput?

Không. Chọn metric theo câu hỏi: throughput cho số công việc hoàn tất, AverageTime cho service time, SampleTime cho phân phối, SingleShotTime cho trường hợp non-steady-state phù hợp.

### 30.4. @Benchmark có thể dùng synchronized không?

Có. Nếu việc dùng lock là một phần workload thật, đo nó cùng trạng thái chia sẻ và số thread thích hợp. Không loại bỏ `synchronized` chỉ để “làm benchmark nhanh hơn”.

### 30.5. Dùng virtual threads trong JMH có hợp lệ?

Có, nếu câu hỏi nghiên cứu phù hợp và phương thức benchmark hoàn thành công việc theo cách đo rõ ràng. Nhưng JMH worker threads và task virtual threads mà benchmark tạo ra là hai tầng khác nhau. Phải đo cả lifecycle/task completion theo phạm vi cần thiết.

### 30.6. Vì sao benchmark mới rất nhanh nhưng sản phẩm không nhanh lên?

Có thể do Amdahl's law, cache behavior, allocation, queue, I/O, GC, khác input hoặc thậm chí benchmark bị JIT loại bỏ công việc. Cần xem production profile và đối chiếu workload.

### 30.7. Vì sao cùng source nhưng hai lần chạy ra điểm khác nhau?

JIT, GC, scheduler, CPU frequency, thermal, OS page cache, runtime flags hoặc nhiễu môi trường đều có thể gây ra khác biệt. Dùng nhiều forks, lưu môi trường và điều tra nếu biến động lớn.

## 31. Bài tập thực hành

### Bài tập 1: Bắt lỗi dead-code elimination

Tạo hai benchmark gọi một hàm tính toán thuần: một cái bỏ kết quả, một cái trả kết quả. Chạy nhiều forks và xem số đo thay đổi.

**Câu hỏi:** Vì sao giá trị `ns/op` nhỏ không tự chứng minh thuật toán tốt?

### Bài tập 2: Khảo sát kích thước mảng

Mở rộng `ArraySumBenchmark` với `@Param({"16","256","4096","65536","1048576"})`. Giữ input và output tương đương, đo cả for và stream.

**Câu hỏi:** Những size nào có thể tạo ranh giới cache? Có sự thay đổi xu hướng theo CPU không?

### Bài tập 3: So state chia sẻ

Chạy `CounterContentionBenchmark` với 1, 2, 4, 8 threads. Ghi thêm thông tin CPU quota và SMT.

**Câu hỏi:** Sự thay đổi throughput có ý nghĩa gì về contention? `LongAdder` và `AtomicLong` có thể thay thế nhau trong mọi yêu cầu đọc nhất quán không?

### Bài tập 4: Đo sort có kiểm soát

Tạo benchmark sort với hai chính sách input: array mới copy ở timed method, hoặc reset ở `@Setup(Level.Invocation)`.

**Câu hỏi:** Hai benchmark đang đo công việc khác nhau ở đâu? Vì sao chuẩn bị input vẫn có thể làm thay đổi cache và GC?

### Bài tập 5: Bổ sung profiler

Chạy một benchmark với và không có `-prof gc`, lưu kết quả cả hai. So sánh latency, B/op và GC activity.

**Câu hỏi:** Vì sao một phương án có B/op thấp hơn chưa chắc giữ ít RAM hơn?

### Bài tập 6: Viết báo cáo có thể tái lập

Lưu raw JSON, JDK version, JMH version, CPU/OS, JVM flags, command line, seed và bản commit. Yêu cầu một người khác chạy lại trên máy khác rồi phân tích giới hạn của việc so sánh.

## 32. Checklist trước khi tin vào một điểm số JMH

- [ ] Có một câu hỏi đo cụ thể và đại lượng chính rõ ràng?
- [ ] Hai phương án đúng cùng hợp đồng nghiệp vụ?
- [ ] Input đại diện workload và có nhiều `@Param` khi cần?
- [ ] Kết quả phép toán được return hoặc consume?
- [ ] Đã kiểm tra nguy cơ DCE/constant folding?
- [ ] Không tự lặp micro-operation hàng triệu lần để “khử overhead” thiếu kiểm soát?
- [ ] `@State` đúng phạm vi chia sẻ?
- [ ] State không tự biến đổi làm workload sai qua các invocation?
- [ ] `@Setup` có đúng Level và không vô tình che chi phí thực tế?
- [ ] Warmup đủ để kết quả tương đối ổn định?
- [ ] Measurement đủ iterations/duration và có nhiều forks?
- [ ] Chọn Mode/Units phù hợp, không nhầm throughput với latency?
- [ ] Ghi đúng số threads, group/role và CPU quota?
- [ ] Không có log, debug, GC cưỡng bức hoặc profiler không kiểm soát trong timed path?
- [ ] Đã xem allocation/GC khi bài toán có cấp phát?
- [ ] Đã kiểm soát hoặc ghi lại OS/CPU/JDK/GC/heap?
- [ ] Có kiểm tra biến động theo fork/iteration?
- [ ] Không biến Error nhỏ thành bằng chứng benchmark đúng?
- [ ] Có raw results, benchmark command và source revision?
- [ ] Đã xác định mức khác biệt có ý nghĩa thực tế?
- [ ] Có xác nhận bằng load test/profiler khi kết luận ảnh hưởng production?
- [ ] Mọi số liệu công bố đều là kết quả đo thật, không dùng số minh họa?

## 33. Tóm tắt

- **JMH** là harness benchmark của OpenJDK, không phải một class có sẵn trong mọi JDK. Dùng archetype chính thức để tạo đúng cấu hình sinh mã và chạy benchmark.
- **Chọn workload và metric trước**, không chọn annotation ngẫu nhiên rồi suy kết luận.
- **Warmup, measurement và fork** phục vụ các mục đích khác nhau; đủ nhiều samples giúp kiểm soát nhưng không loại bỏ mọi nhiễu.
- **Dead-code elimination, constant folding và loop optimizations** có thể làm một benchmark sai trông nhanh đáng kinh ngạc.
- **Trả kết quả hoặc dùng `Blackhole`** để bảo đảm phép tính có tác dụng quan sát được, nhưng vẫn phải bảo đảm code thực sự đo đúng nghiệp vụ.
- **`@State`, `@Param` và `@Setup`** quyết định dữ liệu, sharing, lifecycle và tính đại diện của phép đo.
- **Throughput, AverageTime, SampleTime và SingleShotTime** trả lời các câu hỏi khác nhau; không trộn đơn vị.
- **GC, CPU/cache, OS scheduling và container quotas** có thể làm thay đổi kết quả, nhất là dưới nhiều threads.
- **Error thấp không đủ** để chứng minh benchmark hợp lệ; phải kiểm tra correctness, input, compiler optimization và variation.
- **Microbenchmark không thay thế production profiling hay load test**. Chỉ dùng nó để trả lời câu hỏi nhỏ có thể kiểm soát, rồi xác nhận ở tầng hệ thống.
- **Lưu metadata và raw results** để việc đánh giá hiệu năng có thể được kiểm chứng và lặp lại.

## 34. Tài liệu tham khảo chính thức và tài liệu nguồn

- [OpenJDK — Java Microbenchmark Harness (JMH)](https://github.com/openjdk/jmh)
- [OpenJDK JMH README — hướng dẫn setup, build và chạy](https://github.com/openjdk/jmh/blob/master/README.md)
- [OpenJDK JMH Samples — ví dụ chính thức](https://github.com/openjdk/jmh/tree/master/jmh-samples/src/main/java/org/openjdk/jmh/samples)
- [JMHSample_03_States — phạm vi chia sẻ](https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_03_States.java)
- [JMHSample_08_DeadCode — dead-code elimination](https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_08_DeadCode.java)
- [JMHSample_09_Blackholes — tiêu thụ kết quả](https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_09_Blackholes.java)
- [JMHSample_11_Loops — sai lầm với vòng lặp](https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_11_Loops.java)
- [JMHSample_22_FalseSharing — hiệu năng nhiều luồng](https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_22_FalseSharing.java)
- [Maven Central — JMH Core](https://central.sonatype.com/artifact/org.openjdk.jmh/jmh-core)
- [Maven Central — JMH Java Archetype](https://central.sonatype.com/artifact/org.openjdk.jmh/jmh-java-benchmark-archetype)
- [Java SE 27 — System.nanoTime](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/System.html#nanoTime())
- [Java SE 27 — Java Flight Recorder](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.jfr/module-summary.html)
- [Java SE 27 — The java Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html)

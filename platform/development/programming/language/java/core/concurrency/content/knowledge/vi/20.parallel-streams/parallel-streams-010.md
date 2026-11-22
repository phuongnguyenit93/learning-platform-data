# Dùng benchmark để xác định ngưỡng có lợi của Parallel Streams

## 1. Bài toán cần trả lời

`parallelStream()` hoặc `stream().parallel()` yêu cầu thư viện Stream xử lý một pipeline theo hướng song song. Điều đó **không bảo đảm chương trình chạy nhanh hơn**. Khi chia nguồn dữ liệu thành các phần, lập lịch công việc, chạy trên nhiều worker rồi kết hợp kết quả, JVM phải trả một khoản chi phí. Với dữ liệu nhỏ hoặc thao tác mỗi phần tử quá nhẹ, chi phí ấy có thể lớn hơn thời gian tính toán tiết kiệm được.

Câu hỏi thực tiễn không chỉ là “parallel nhanh hơn sequential hay không?” mà là:

> Với loại dữ liệu, lượng việc trên mỗi phần tử, số phần tử, số CPU, cấu hình JVM và tải thực tế này, từ kích thước nào `parallel()` mang lại mức cải thiện ổn định đủ lớn để đáng sử dụng?

Ta gọi mốc đó là **ngưỡng hòa vốn (break-even threshold)** hay **ngưỡng có lợi**. Không có giá trị mặc định kiểu “hơn 1.000 phần tử thì dùng parallel” áp dụng cho mọi chương trình Java.

Ví dụ, 100.000 phần tử mà mỗi phần tử chỉ cộng một số nguyên có thể quá ít việc để bù chi phí chia/gộp; 5.000 phần tử mà mỗi phần tử đòi hỏi một phép tính CPU phức tạp lại có thể đem lại lợi ích. Kết quả còn tùy hệ thống có bao nhiêu lõi CPU thực sự khả dụng và có tác vụ khác đang dùng những lõi đó không.

**Mục tiêu học tập**: tự thiết kế phép đo đúng, lập bảng kích thước/dạng workload, đọc kết quả JMH, chọn ngưỡng bằng bằng chứng và biết trường hợp nên giữ luồng tuần tự.

## 2. Cơ chế tạo ra điểm hòa vốn

Một pipeline như:

```java
long result = data.parallelStream()
        .mapToLong(Record::expensiveMetric)
        .sum();
```

có thể gồm các bước: tách nguồn bằng `Spliterator`, tạo các tác vụ con, phân phối cho worker, chạy hàm ánh xạ và cuối cùng gộp kết quả phép `sum()`. `ForkJoinPool.commonPool()` thường tham gia xử lý parallel stream trên OpenJDK/HotSpot, và thread gọi terminal operation cũng có thể tham gia công việc. Không nên giả định số worker chạy thực tế luôn bằng số lõi CPU hay mỗi phần tử được giao cho một thread riêng.

Một mô hình để **suy nghĩ**, không phải công thức dự đoán chính xác thời gian JVM, là:

```text
T_seq(N) ≈ C_setup_seq + N × C_element

T_par(N, P) ≈ C_setup_par
             + C_split(N)
             + N × C_element / P_effective
             + C_merge(N)
             + C_contention(N)
```

Trong đó:

- `N`: số phần tử thực sự được xử lý.
- `C_element`: chi phí xử lý mỗi phần tử, gồm thao tác ánh xạ/lọc.
- `P_effective`: mức song song hữu hiệu; thường **nhỏ hơn hoặc bằng** số năng lực xử lý thực tế, có thể giảm do mất cân bằng, giới hạn bộ nhớ, tranh chấp và tải hệ thống.
- `C_split` / `C_merge`: chi phí tách và kết hợp các phần của stream.
- `C_contention`: chi phí đồng bộ, cạnh tranh cache/băng thông bộ nhớ và tài nguyên dùng chung.

Parallel chỉ thắng khi thời gian tính toán tiết kiệm được **lớn hơn tổng chi phí thêm**. Nếu chi phí mỗi phần tử tăng, ngưỡng N có thể giảm. Nếu chi phí split/merge hoặc contention tăng, ngưỡng N có thể tăng hoặc **không tồn tại** trong miền dữ liệu có ý nghĩa. Quan hệ thường không tuyến tính nên chỉ benchmark thực tế mới xác nhận được.

Định nghĩa quan sát được:

```text
speedup(N)          = T_sequential(N) / T_parallel(N)
relativeSaving(N)   = (T_sequential(N) - T_parallel(N)) / T_sequential(N)

speedup(N) > 1: parallel có thời gian thấp hơn trong phép đo đó
speedup(N) = 1: gần điểm hòa vốn
speedup(N) < 1: parallel chậm hơn trong phép đo đó
```

Đo được `speedup > 1` một lần **chưa đủ** để bật parallel mặc định. Chênh lệch phải ổn định qua lần chạy, đủ lớn so với nhiễu, và không làm xấu các chỉ số quan trọng khác.

## 3. Những biến làm dịch chuyển ngưỡng

| Biến | Tác động lên benchmark | Điều phải kiểm soát |
| --- | --- | --- |
| Số phần tử `N` | N nhỏ thường không bù được chi phí song song | Thử dải kích thước tăng dần, có điểm gần ngưỡng |
| Lượng CPU mỗi phần tử | Tính toán nặng hơn có thể tạo cơ hội tăng tốc | Đo nhiều mức chi phí nhưng giữ cùng logic giữa hai nhánh |
| Nguồn dữ liệu / `Spliterator` | `ArrayList`, mảng, `IntStream.range` thường dễ phân hoạch hơn nguồn khó split | Giữ nguyên nguồn giữa các biến thể; đo lại khi đổi loại nguồn |
| Pipeline và terminal operation | `sorted`, `distinct`, `limit`, `findFirst`, `forEachOrdered` và collector có yêu cầu riêng | Benchmark **cả pipeline**, gồm thao tác gộp/giữ thứ tự |
| Boxing và allocation | `Stream<Integer>` có thể tạo chi phí khác `IntStream` | So sánh đúng kiểu dữ liệu ứng dụng dùng |
| Số processor khả dụng | Giới hạn cơ hội tính song song | Ghi lại `Runtime.availableProcessors()` và CPU quota |
| Cache và băng thông bộ nhớ | Có thể bão hòa trước khi tận dụng hết lõi | Đo dữ liệu nhỏ/vừa/lớn, theo dõi CPU/cache/GC khi cần |
| Tải đồng thời khác | Cạnh tranh common pool và CPU | Đo môi trường cô lập, rồi xác minh tải thực tế |
| JVM/JDK và warmup | JIT, profiling và GC làm số đo thay đổi | Cố định JDK/flags, warmup và dùng nhiều fork |

**Nguồn khó phân chia** làm một nhánh nhận quá nhiều việc, để những worker khác rảnh. `Spliterator` có các đặc tính như `SIZED`/`SUBSIZED` giúp biết kích thước và chia các phần có dự đoán tốt; nhưng chỉ nhìn cờ chưa đủ để khẳng định tăng tốc. Với danh sách liên kết, pipeline có thể tốn công tạo chunk; với mảng, phân hoạch theo chỉ số thường thuận lợi.

**Pipeline có thứ tự** cũng ảnh hưởng. `forEachOrdered` bảo toàn thứ tự encounter, có thể hạn chế lợi ích song song; `forEach` cho phép thứ tự thực thi không xác định. Nếu kết quả không cần order, một số pipeline có thể cải thiện khi `unordered()` được dùng đúng ngữ nghĩa. Không bỏ ràng buộc thứ tự chỉ để cải thiện benchmark nếu nghiệp vụ cần nó.

**Công việc I/O** như gọi mạng/đĩa/DB là workload khác. Dùng parallel stream để gọi I/O blocking số lượng lớn có thể giữ worker và gây nghẽn các công việc dùng chung pool; benchmark CPU-bound không thể được dùng để biện minh cho quyết định I/O-bound. Với I/O thường cần cơ chế giới hạn đồng thời và quản lý timeout riêng.

## 4. Thiết kế phép đo: ba biến thể phải làm cùng một việc

Nên có ít nhất ba cách xử lý một phép tính:

1. **For-loop tuần tự**: đường cơ sở để thấy overhead chung của Stream API.
2. **Sequential stream**: cùng nguồn và phép tính, gọi `stream()` hoặc `Arrays.stream(...)`.
3. **Parallel stream**: cùng pipeline, khác duy nhất ở cờ `parallel()`.

Nếu chỉ so sánh `parallelStream()` với for-loop, người đọc có thể nhầm **chi phí Stream API** với **chi phí bật song song**. Nếu chỉ đo hai biến thể stream, vẫn nên biết vòng lặp thường có nhanh hơn cả hai hay không.

Một ma trận thí nghiệm mẫu:

| Chiều thay đổi | Các mức nên thử ban đầu | Ý nghĩa |
| --- | --- | --- |
| `N` — số phần tử | 1.000, 10.000, 100.000, 1.000.000 | Tìm đoạn chuyển giao theo kích thước |
| `work` — vòng xử lý CPU mỗi phần tử | 8, 128 | So sánh phép tính nhẹ và nặng |
| Số CPU hữu hiệu | Cố định cho một lượt, đo lại trên môi trường đích | Biết ngưỡng dịch chuyển theo phần cứng |
| Loại pipeline | Trước hết chỉ map + sum; sau đó pipeline thật | Tách chi phí cơ bản khỏi các toán tử đặc biệt |

Dải trên **chỉ là điểm khởi đầu**, không phải danh sách ngưỡng chuẩn của Java. Nếu điểm giao xảy ra gần 10.000, bổ sung các mức 4.000, 8.000, 12.000, 16.000 để khoanh vùng; nếu không thấy giao, mở rộng tới miền dữ liệu khả thi hoặc ghi kết luận “chưa thấy ngưỡng có lợi”.

Mỗi biến thể phải:

- Đọc **cùng nội dung dữ liệu**; tạo input ngoài khoảng thời gian đang đo nếu chi phí tạo dữ liệu không nằm trong thao tác ứng dụng cần tối ưu.
- Dùng **cùng phép tính thực sự** và tạo **cùng kết quả** theo quy tắc so sánh phù hợp.
- Có kết quả được benchmark harness sử dụng để JVM không dễ loại bỏ toàn bộ phần việc.
- Chạy với cấu hình JDK, heap, hệ điều hành và tình trạng tài nguyên tương đương.
- Không in log, đọc file cấu hình, tải dữ liệu từ mạng, hoặc tạo dữ liệu ngẫu nhiên **bên trong** đoạn đang đo nếu đó không phải đối tượng phép đo.

Không đưa `Thread.sleep()` vào hàm tính toán để giả lập “CPU work”: sleep mô phỏng chờ chứ không phản ánh chi phí CPU và dễ làm kết luận sai.

## 5. Vì sao System.nanoTime() một lần dễ đánh lừa?

`System.nanoTime()` phù hợp cho phép đo thời gian trôi qua ở mức đơn giản, nhưng đoạn:

```java
long start = System.nanoTime();
long sum = input.parallelStream().mapToLong(x -> x).sum();
long elapsed = System.nanoTime() - start;
System.out.println(elapsed);
```

**không đủ để kết luận hiệu năng**:

- Lần đầu có thể chịu tải class loading, JIT compilation và khởi tạo cấu trúc runtime; các lần sau có thể nhanh khác hẳn.
- GC, scheduler của OS, CPU frequency scaling và tác vụ nền làm sai lệch từng mẫu.
- JVM tối ưu code theo profile: benchmark quá đơn giản, không dùng kết quả, hoặc input bất biến hoàn toàn có thể không đại diện ứng dụng.
- Nếu chạy sequential trước rồi parallel sau, kết quả parallel có thể được hưởng cache/warmup mà sequential không được hưởng (hoặc ngược lại).
- Timer một lần không cho phân bố, độ dao động hay khoảng tin cậy.
- Dữ liệu quá nhỏ khiến chi phí harness/timer chiếm tỷ lệ đáng kể.

Dùng `nanoTime()` để **quan sát sơ bộ hoặc test trải nghiệm** có thể hữu ích, nhưng với microbenchmark quyết định ngưỡng nên dùng **JMH (Java Microbenchmark Harness)**. JMH hỗ trợ warmup, iteration đo, fork JVM riêng, tiêu thụ kết quả và báo cáo thống kê. JMH không tự biến một benchmark thiết kế sai thành đáng tin: vẫn cần xác nhận workload, equality và môi trường.

## 6. JMH thực hành: xây benchmark có thể chạy

OpenJDK khuyến nghị dùng archetype chính thức để scaffold một project có annotation processor và cấu hình build của JMH. Cần có **JDK 17+** và Maven; có thể dùng JDK 21 để khớp runtime học tập.

Từ thư mục rỗng không chứa project Maven sẵn có, chạy:

```bash
mvn archetype:generate -DinteractiveMode=false -DarchetypeGroupId=org.openjdk.jmh -DarchetypeArtifactId=jmh-java-benchmark-archetype -DgroupId=org.sample -DartifactId=parallel-threshold-bench -Dversion=1.0-SNAPSHOT
cd parallel-threshold-bench
```

Archetype tạo cấu hình JMH và dependency phù hợp; kiểm tra build/JDK mà project sinh ra sử dụng. Tạo tệp **`src/main/java/org/sample/ParallelThresholdBenchmark.java`** với nội dung đầy đủ:

```java
package org.sample;

import java.util.Arrays;
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

@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.MILLISECONDS)
@Warmup(iterations = 3, time = 1, timeUnit = TimeUnit.SECONDS)
@Measurement(iterations = 5, time = 1, timeUnit = TimeUnit.SECONDS)
@Fork(2)
@Threads(1)
@State(Scope.Thread)
public class ParallelThresholdBenchmark {
    @Param({"1000", "10000", "100000", "1000000"})
    public int size;

    @Param({"8", "128"})
    public int work;

    private int[] input;

    @Setup(Level.Trial)
    public void setup() {
        input = new int[size];
        for (int i = 0; i < size; i++) {
            input[i] = i * 31 + 7;
        }

        // Kiểm tra ngữ nghĩa trước benchmark, không tính vào score.
        long expected = sequentialKernel();
        long actual = parallelKernel();
        if (expected != actual) {
            throw new AssertionError("Different results");
        }
    }

    private long compute(int value) {
        long x = Integer.toUnsignedLong(value);
        for (int i = 0; i < work; i++) {
            x = (x * 1664525L + 1013904223L + i) & 0xFFFF_FFFFL;
        }
        return x;
    }

    private long sequentialKernel() {
        return Arrays.stream(input)
                .mapToLong(this::compute)
                .sum();
    }

    private long parallelKernel() {
        return Arrays.stream(input)
                .parallel()
                .mapToLong(this::compute)
                .sum();
    }

    @Benchmark
    public long forLoop() {
        long sum = 0L;
        for (int value : input) {
            sum += compute(value);
        }
        return sum;
    }

    @Benchmark
    public long sequentialStream() {
        return sequentialKernel();
    }

    @Benchmark
    public long parallelStream() {
        return parallelKernel();
    }
}
```

Các điểm thiết kế có chủ ý:

- `@State(Scope.Thread)` cấp state riêng cho mỗi JMH harness worker; `@Threads(1)` giữ **một thread JMH gọi phép đo mỗi lần**. Parallel stream bên trong vẫn được phép dùng nhiều worker JVM, nên `@Threads(1)` **không biến parallel stream thành tuần tự**.
- `@Param` tạo tích Descartes giữa các `size` và `work`; mỗi tổ hợp được đo cho cả ba phương thức.
- `@Setup(Level.Trial)` tạo mảng và xác thực kết quả ngoài phần score. Input có công thức xác định; hai stream cùng đọc mảng không bị sửa trong khi đo.
- `compute` dùng toán học nguyên và vòng lặp cố định; phép tính là **stateless**, độc lập từng phần tử. Phép cộng `long` có thứ tự kết quả nhất quán trên cả hai cách xử lý; nếu muốn kiểm tra for-loop cũng có thể so với `expected`.
- Mỗi `@Benchmark` trả giá trị `long`. JMH sử dụng kết quả thay vì để phương thức đo trở thành lời gọi “không làm gì” không quan sát được.
- `@Warmup` cho thời gian JVM tối ưu và ổn định phần nào trước khi ghi score; `@Measurement` đo nhiều lượt, `@Fork(2)` chạy trên các tiến trình JVM mới. Các giá trị annotation là lựa chọn thực hành mẫu, có thể tăng khi kết quả nhiễu.

**Không kết luận từ một máy:** benchmark trên dữ liệu mảng CPU-bound này chưa mô phỏng chi phí allocation, điều kiện lọc, gộp collector, thứ tự, tính không đồng đều của phần tử hoặc I/O trong pipeline thật. Muốn ra quyết định ứng dụng, phải benchmark **đúng pipeline** sau khi kiểm chứng phép đo cơ bản.

### Build và chạy

```bash
mvn clean verify

# Chạy đầy đủ benchmark; với nhiều tổ hợp có thể tốn thời gian.
java -jar target/benchmarks.jar ParallelThresholdBenchmark -t 1 -rf csv -rff target/parallel-results.csv
```

Để **khám phá nhanh** khi chưa cần số liệu quyết định cuối cùng:

```bash
java -jar target/benchmarks.jar ParallelThresholdBenchmark -t 1 -p size=1000,10000,100000 -p work=8,128 -wi 2 -i 3 -w 1s -r 1s -f 1
```

Các cờ chính:

| Cờ | Công dụng |
| --- | --- |
| `-t 1` | Số thread mà JMH dùng để gọi benchmark; khác số worker của parallel stream |
| `-p size=...` và `-p work=...` | Chọn tập tham số trong `@Param` để chạy |
| `-wi 2` và `-i 3` | Số iteration warmup/measurement; **đè** annotation trong lần chạy này |
| `-w 1s`, `-r 1s` | Độ dài mỗi iteration warmup/measurement |
| `-f 1` | Một fork cho khảo sát nhanh; quyết định chính thức thường cần nhiều fork |
| `-rf csv -rff ...` | Đưa kết quả về CSV để lưu/so sánh theo tham số |

Bảng kết quả JMH sẽ có phương thức, các param, `Mode=avgt`, `Cnt`, `Score`, `Error` và đơn vị (ví dụ `ms/op`). Với **AverageTime**, score thấp hơn thường tốt hơn. `Error` là mức bất định thống kê do JMH báo theo phương pháp của nó; không nên đọc thành bảo đảm chắc chắn kết quả trong mọi tải thực tế.

Không có “stdout chuẩn” về thời gian: con số thay đổi theo CPU, JDK, nhiệt độ, hệ điều hành, container, JVM flags và tác vụ nền. Nếu chương trình in cùng một score trên mọi máy thì chính phép đo ấy cần bị nghi ngờ.

## 7. Đọc điểm giao từ bảng kết quả

Sau khi chạy, gom score theo cùng `work` và `size`; so sánh riêng ba phương thức. **Ví dụ minh họa giả định** (không phải kết quả đo thực tế):

| size | work | Sequential stream (ms/op) | Parallel stream (ms/op) | Speedup | Nhận xét |
| ---: | ---: | ---: | ---: | ---: | --- |
| 1.000 | 8 | 0,03 | 0,30 | 0,10× | Parallel thua rõ |
| 10.000 | 8 | 0,20 | 0,34 | 0,59× | Vẫn không lợi |
| 100.000 | 8 | 1,90 | 1,20 | 1,58× | Có dấu hiệu lợi |
| 1.000 | 128 | 0,85 | 1,10 | 0,77× | Chưa hòa vốn |
| 10.000 | 128 | 8,20 | 3,90 | 2,10× | Có dấu hiệu lợi |

Những con số này **chỉ minh họa cách đọc**, không dự đoán kết quả chương trình ở phần 6.

Chẳng hạn với `size=100000, work=8`:

```text
speedup = 1,90 / 1,20 ≈ 1,58
relativeSaving = (1,90 - 1,20) / 1,90 ≈ 36,8%
```

Nếu mức độ sai số/độ dao động khiến hai kết quả chồng lấn nhiều, không thể gọi đây là ngưỡng đáng tin. Đo lại gần điểm giao với nhiều kích thước hơn, nhiều fork và số lần lặp dài hơn. Một miền có lợi tốt nên xuất hiện **liên tiếp ở các kích thước lân cận**, không phải chỉ một mẫu may mắn.

Đừng ép kết quả thành một con số duy nhất. Một báo cáo đúng có thể là:

- Với `work=8`, parallel chưa ổn định cho `N < 50000`, có lợi rõ khi `N >= 100000` trên môi trường thử.
- Với `work=128`, parallel bắt đầu có lợi từ một mức thấp hơn trên cùng môi trường.
- Ở máy chỉ có một CPU khả dụng, không tìm thấy lợi ích đáng kể.
- Với pipeline có `forEachOrdered` hoặc `groupingBy`, ngưỡng khác hẳn pipeline chỉ `mapToLong().sum()`.

Đây là **ví dụ về hình thức kết luận**; phải thay mốc bằng số đã đo của chính dự án.

## 8. Quy trình chọn ngưỡng thực sự sử dụng được

1. **Xác định tiêu chí thắng trước khi đo.** Ví dụ yêu cầu parallel giảm ít nhất 10% thời gian xử lý trên môi trường đích và chênh lệch vượt nhiễu quan sát được; mức 10% ở đây là tiêu chí kinh doanh/kỹ thuật **do nhóm chọn**, không phải quy tắc Java.
2. **Cố định điều kiện thử.** Ghi phiên bản JDK, vendor, CPU, số processor JVM thấy, RAM, heap, GC, flags, OS, loại input, tình trạng tải và lệnh JMH.
3. **Đo lưới kích thước thưa.** Lấy log-scale N để tìm khoảng có điểm giao. Không chọn “ngưỡng theo số phần tử” khi chi phí mỗi phần tử biến động lớn mà không nhóm theo workload.
4. **Đo dày quanh điểm giao.** Tăng forks/iterations, tính `speedup`, xem khoảng bất định và chạy lại vào thời điểm khác.
5. **Đo trên workload gần thực tế.** Dùng phân phối dữ liệu, tỷ lệ filter, collector, mức độ skew, kích thước heap và concurrency tương ứng production.
6. **Đánh giá tác động toàn hệ thống.** Kiểm tra throughput tổng, CPU, GC, tail latency, fairness và ảnh hưởng lên tác vụ khác cùng dùng CPU/common pool.
7. **Đưa quyết định và guardrail vào mã.** Chỉ dùng parallel cho miền đã đo có lợi; theo dõi và đánh giá lại khi thay JDK, phần cứng hay pipeline.

Một ví dụ quyết định **sau khi đã đo**, sử dụng threshold cấu hình được:

```java
static long sumMetrics(int[] values, int threshold) {
    var stream = Arrays.stream(values);
    if (values.length >= threshold) {
        stream = stream.parallel();
    }
    return stream.mapToLong(MyClass::metric).sum();
}
```

Đoạn trên **minh họa nằm trong `MyClass`** có phương thức `static long metric(int)` và import `java.util.Arrays`; không phải một tệp chạy độc lập. `threshold` là **kết quả tuning** được định nghĩa cho một môi trường/workload, không nên điền số tùy tiện vào bài học. Nếu `values.length` không phản ánh lượng tính toán (ví dụ 99% bị filter), tiêu chí kích thước mảng có thể gây quyết định sai; cân nhắc phép đo rẻ hơn thể hiện lượng công việc thật.

Độ dài `N` cũng không phải lúc nào cũng đủ. Một tập chứa số ít phần tử rất đắt và nhiều phần tử rẻ có thể gây **load imbalance**; cần benchmark đúng phân phối và xem có cải thiện được phân hoạch hay không.

## 9. Một số bẫy vi mô đặc biệt với parallel streams

### 9.1. Không dùng state bên ngoài trong map/filter

Ví dụ sai khi nhiều phần tử ghi vào cùng collection mutable:

```java
List<Integer> output = new ArrayList<>();
input.parallelStream().forEach(output::add); // không an toàn
```

Có thể gặp race condition hoặc sai dữ liệu. Dùng reduction/collector chuẩn:

```java
List<Integer> output = input.parallelStream().toList();
```

Hai đoạn trên minh họa đặt trong scope có `input` là `List<Integer>` và import `ArrayList`/`List`; `Stream.toList()` có từ Java 16. Kết quả của `toList()` là danh sách không cho phép chỉnh sửa bằng các mutator chuẩn, nên đừng dùng nó để thay thế trực tiếp một collection cần mutable.

Benchmark có tác dụng phụ không thread-safe không có ý nghĩa: một phép tính “nhanh hơn” mà trả sai kết quả không thể là lựa chọn tốt.

### 9.2. Cẩn thận phép gộp không kết hợp được

Các phép reduction song song cần tính **associative** đúng nghĩa để việc chia/gộp không đổi kết quả. Cộng `long` là phép toán kết hợp theo ngữ nghĩa số nguyên Java (kể cả overflow modulo 2^64); trừ và chia nói chung **không kết hợp**.

Với `double`, thứ tự cộng khác nhau có thể cho sai khác rounding:

```java
double a = DoubleStream.of(1e16, 1.0, -1e16).sum();
double b = DoubleStream.of(1e16, 1.0, -1e16).parallel().sum();
```

Hai dòng trên là ví dụ về bài toán độ chính xác số dấu phẩy động, **không khẳng định** chúng luôn in ra hai giá trị khác nhau trên mọi JDK. Nếu nghiệp vụ cần sai số nhỏ hoặc tái lập bit-by-bit, phải thiết kế phép so sánh với tolerance và/hoặc chiến lược số học phù hợp trước khi kết luận về hiệu năng.

### 9.3. Nhớ chi phí allocation và collector

Dùng `Stream<Integer>` kèm boxing, `Collectors.groupingBy`, `sorted` hoặc kết hợp các map/list có thể có hành vi allocation/merge rất khác pipeline dùng `IntStream`/`LongStream`. Collector concurrent đôi khi có lợi nếu không cần encounter order, nhưng có thể phải đánh đổi thứ tự dữ liệu và contention. Đo **terminal operation hoàn chỉnh**, đừng bỏ `collect()` ra khỏi vùng benchmark chỉ để nhận số đẹp.

### 9.4. Benchmark loại bỏ công việc hoặc tự thay đổi workload

- Không benchmark pipeline **thiếu terminal operation** rồi kết luận vì intermediate operations của stream là lazy.
- Không cố tình bỏ kết quả; trả giá trị từ `@Benchmark` hoặc dùng JMH `Blackhole` đúng cách khi kết quả là object.
- Không ghi `System.out.println` hay I/O vào mapper khi mục tiêu là hiệu năng tính toán.
- Không sửa input trong khi cả hai stream đọc; ngoài vấn đề data race còn làm phép đo biến động.
- Không dùng một workload cố định “quá đẹp” làm kết quả đại diện cho input thật; dữ liệu ngẫu nhiên cũng cần seed và setup có kiểm soát.

### 9.5. CPU contention và băng thông bộ nhớ

Trong tiến trình JVM nhiều tác vụ, common pool có thể đang xử lý parallel stream khác hoặc công việc dùng `ForkJoinPool.commonPool()`. Một microbenchmark chạy một mình thấy tăng tốc lớn không chứng minh việc bật parallel cho hàng nghìn request đồng thời sẽ cải thiện **throughput tổng**. Khi load thực tế cao, số core hữu hạn và chi phí tranh chấp có thể khiến sequential nhanh hơn cho từng request hoặc mang lại tail latency tốt hơn.

Không đặt `System.setProperty("java.util.concurrent.ForkJoinPool.common.parallelism", "...")` trong thân benchmark để đổi cấu hình pool giữa các lượt đo; đặc tính này liên quan lúc common pool được khởi tạo và ảnh hưởng các thành phần khác. Muốn khảo sát ảnh hưởng số worker cần chạy JVM riêng với flag cấu hình rõ ràng, ghi lại môi trường và hiểu rằng giới hạn pool không thay đổi số core thực tế.

## 10. Khi nào nên chọn sequential dù parallel có điểm nhanh hơn?

- Mức nhanh hơn chỉ vài phần trăm, nhỏ hơn nhiễu đo và chưa có bằng chứng lặp lại.
- Đầu vào ứng dụng thường nhỏ hơn vùng có lợi; thỉnh thoảng có vài request lớn không đáng tăng độ phức tạp.
- Pipeline bị ràng buộc thứ tự mạnh, có side-effect cần đồng bộ, hoặc kết quả số học nhạy với thứ tự gộp.
- Ứng dụng đang bão hòa CPU hoặc common pool, mục tiêu cần tối ưu throughput/tail latency cho cả hệ thống.
- Dữ liệu phụ thuộc I/O, database hay tài nguyên ngoài; phép đo CPU không đại diện.
- Vòng lặp đơn giản đang nhanh hơn cả sequential và parallel stream, và codebase không yêu cầu Stream API.
- Cần đơn giản hóa khả năng debug/tái lập thứ tự; lợi ích parallel không đủ bù rủi ro vận hành.

Không nên “tối ưu bằng parallel” trước khi đo bottleneck. Nếu phần nặng nhất là network, locks hay allocation, thay đổi `stream()` sang `parallelStream()` có thể không giải quyết nguyên nhân.

## 11. Checklist kết quả và bài tập tự đánh giá

Khi trình bày kết luận benchmark cho đồng đội, báo cáo ít nhất:

| Hạng mục | Thông tin bắt buộc |
| --- | --- |
| Bài toán | Pipeline thực sự, input, kết quả mong đợi, side effects/ordering |
| Môi trường | JDK/version/vendor, OS, core/CPU quota, heap, GC, tải nền |
| Thiết kế benchmark | JMH version, @Param, warmup, measurement, forks, threads, đơn vị |
| Tính đúng | Sequential/parallel/for-loop cho kết quả tương đương theo tiêu chí xác định |
| Kết quả | Score và Error theo từng size/work; speedup; dữ liệu gốc/CSV |
| Quyết định | Miền có lợi, mức cải thiện tối thiểu, giới hạn và điều kiện đo lại |

**Bài tập 1:** Chạy benchmark JMH phần 6 với `size=1000,10000,100000`, `work=8,128` trên máy của bạn. Lập bảng `speedup`. Có ngưỡng chung cho hai giá trị `work` không? Giải thích bằng chi phí tính toán mỗi phần tử.

**Bài tập 2:** Thêm biến thể sử dụng `Stream<Integer>` có boxing rồi so với `IntStream` trên cùng đầu vào. Ghi nhận khác biệt về `Score` và allocation khi có công cụ đo phù hợp. Vì sao kết quả này không thể ngoại suy sang tất cả pipeline object stream?

**Bài tập 3:** Chuyển một nguồn từ mảng sang `LinkedList<Integer>` và đo lại, giữ logic xử lý tương đương. Quan sát chi phí nguồn/splitting và những chi phí boxing/allocation phát sinh; không quy mọi khác biệt cho riêng Spliterator.

**Bài tập 4:** Giả sử JMH đo `T_seq=2,0 ms/op` và `T_par=1,8 ms/op` cho một điểm, nhưng độ biến động ở từng lượt vào khoảng 0,3 ms. Có đủ cơ sở để đặt ngưỡng tại điểm này? **Chưa**: cần thêm mẫu/fork và đánh giá thống kê, vì chênh lệch nhỏ hơn dao động quan sát.

**Bài tập 5:** Đo lại trên một môi trường chịu tải nhiều request đồng thời. Giải thích vì sao ngưỡng có lợi của microbenchmark độc lập có thể không còn hợp lý.

## 12. Tài liệu tham khảo chính thức

- [OpenJDK JMH — Java Microbenchmark Harness](https://github.com/openjdk/jmh): archetype, cấu hình, cách chạy JMH, ví dụ và những lỗi benchmark.
- [OpenJDK JMH Samples](https://github.com/openjdk/jmh/tree/master/jmh-samples/src/main/java/org/openjdk/jmh/samples): tham khảo `@State`, `@Param`, warmup, fork, phương pháp đo.
- [Java SE 21 — java.util.stream](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/package-summary.html): stateless/non-interfering behavior, parallelism, ordering, reduction, side effects.
- [Java SE 21 — Spliterator](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Spliterator.html): `trySplit` và các đặc tính hỗ trợ phân hoạch.
- [Java SE 21 — ForkJoinPool](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ForkJoinPool.html): cơ chế work-stealing, common pool.
- [Oracle — Parallelism in Streams](https://docs.oracle.com/javase/tutorial/collections/streams/parallelism.html): lựa chọn parallel, order và các yêu cầu về side effects.

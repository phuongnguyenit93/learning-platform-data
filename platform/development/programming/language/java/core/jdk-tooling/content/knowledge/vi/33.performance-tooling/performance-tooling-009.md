# So sánh hiệu năng trước và sau tối ưu

So sánh hiệu năng trước và sau giúp xác định một thay đổi code hoặc cấu hình có thực sự cải thiện hệ thống hay không. Quy trình đáng tin cậy phải đo cùng một công việc trong điều kiện tương đương, xác nhận kết quả nghiệp vụ không đổi, thu thập đủ lần chạy và kiểm tra cả những chỉ số có thể bị ảnh hưởng.

Không nên kết luận từ một lần chạy hoặc chỉ nhìn vào một con số thời gian. Một thay đổi có thể làm một method nhanh hơn nhưng tăng allocation, memory usage, CPU contention, error rate hoặc p99 latency của service. Vì vậy, cần kết hợp benchmark, load test, JFR và application metrics tùy cấp độ cần so sánh.

## 1. Xác định chính xác điều cần so sánh

Trước khi đo, viết rõ câu hỏi và phạm vi thay đổi.

Ví dụ:

- Một method mới có nhanh hơn method cũ không?
- Thay ArrayList bằng HashSet có giảm thời gian lookup không?
- Cấu hình heap mới có giảm GC pause không?
- Phiên bản service mới có tăng throughput mà vẫn giữ p95/p99 latency không?
- Một thay đổi database query có giảm thời gian xử lý request không?
- Bản build mới có giảm CPU hoặc memory trên cùng workload không?

Mỗi câu hỏi cần một loại phép đo phù hợp.

| Phạm vi | Câu hỏi | Công cụ phù hợp |
|---|---|---|
| Một method nhỏ | Method nào nhanh hơn? | JMH |
| Một vùng code trong ứng dụng | Thời gian đã trôi qua bao lâu? | System.nanoTime() |
| Một JVM đang chạy | CPU, GC, allocation hoặc I/O thay đổi ra sao? | JFR/JMC |
| Một request | Latency end-to-end thay đổi thế nào? | Application metrics, tracing |
| Toàn service dưới tải | Throughput, p95/p99 và error rate thay đổi ra sao? | Load test |
| Một process/container | CPU, RSS và memory limit thay đổi ra sao? | OS/container metrics |

Không dùng microbenchmark để thay thế load test. Một method nhanh hơn không bảo đảm service xử lý được nhiều request hơn nếu bottleneck nằm ở database, network, lock hoặc queue.

## 2. Thiết lập baseline trước khi thay đổi

**Baseline** là số liệu tham chiếu thu thập từ phiên bản hiện tại trước khi tối ưu. Nếu không có baseline đáng tin cậy, bạn không thể xác định mức cải thiện thực tế.

Một baseline tốt cần ghi lại:

- Commit, build number hoặc version đang chạy.
- JDK vendor và version.
- JVM flags, heap size và garbage collector.
- CPU, RAM, OS và container limits.
- Dataset và input parameters.
- Số thread, concurrency và request rate.
- Warm-up duration và measurement duration.
- Số lần chạy, số fork và benchmark settings.
- Throughput, latency, CPU, memory, allocation, GC và error rate.
- Thời điểm chạy và các tác vụ nền có thể ảnh hưởng.

### Giữ nguyên điều kiện so sánh

Khi so sánh trước và sau, các yếu tố không thuộc thay đổi cần thử phải được giữ ổn định:

- Cùng phần cứng hoặc instance tương đương.
- Cùng JDK vendor/version và JVM flags.
- Cùng heap size và GC configuration.
- Cùng input, dataset và data distribution.
- Cùng concurrency và workload arrival rate.
- Cùng cache state: cold với cold, warm với warm.
- Cùng database snapshot hoặc dữ liệu có phân bố tương đương.
- Cùng network path và dependency.
- Cùng thời lượng warm-up và measurement.

Nếu thay đồng thời JDK, GC, heap và code, bạn không thể biết yếu tố nào tạo ra thay đổi.

### Xác nhận baseline có tính đại diện

Không chọn một khoảng thời gian bất thường làm baseline. Chọn workload phản ánh hành vi thực tế, bao gồm các trường hợp phổ biến và các input có chi phí cao.

Với service, nên bao gồm:

- Request mix theo tỷ lệ gần production.
- Payload size nhỏ, trung bình và lớn.
- Peak và steady-state traffic.
- Các dependency thường dùng.
- Error và retry behavior nếu chúng là một phần của workload.

## 3. Xác nhận tính đúng trước khi đo hiệu năng

Một phiên bản chạy nhanh hơn nhưng trả kết quả sai không phải là tối ưu thành công.

Trước khi so sánh:

1. Chạy unit test và integration test.
2. Xác nhận baseline và candidate cho cùng kết quả với cùng input.
3. Kiểm tra edge cases, null, empty input và dữ liệu lớn.
4. Kiểm tra thứ tự, precision, rounding và exception behavior nếu liên quan.
5. Xác nhận transaction, resource cleanup và concurrency semantics.
6. Chạy correctness test trước performance test.

Với thuật toán thay thế, hãy kiểm tra output bằng nhau trên nhiều input, không chỉ một ví dụ nhỏ.

Không bỏ qua correctness chỉ vì benchmark cho thấy tốc độ tăng lớn.

## 4. Chọn metric phù hợp

Không có một metric duy nhất mô tả đầy đủ hiệu năng.

| Metric | Ý nghĩa | Khi cần quan sát |
|---|---|---|
| Latency | Thời gian hoàn thành một operation/request | Người dùng phải chờ bao lâu |
| Throughput | Số operation/request hoàn thành trên đơn vị thời gian | Hệ thống xử lý được bao nhiêu |
| p50 | Median latency | Trải nghiệm request điển hình |
| p95 | 95% request hoàn thành trong thời gian này hoặc thấp hơn | Độ trễ của nhóm request chậm |
| p99 | 99% request hoàn thành trong thời gian này hoặc thấp hơn | Tail latency |
| Error rate | Tỷ lệ request thất bại | Tính ổn định và correctness |
| CPU utilization | Mức sử dụng CPU | Chi phí xử lý |
| Heap/Process memory | Bộ nhớ heap hoặc toàn process | Memory pressure |
| Allocation rate | Lượng object/bộ nhớ được cấp phát mỗi giây | GC pressure |
| GC pause/time | Thời gian và tần suất GC | Tác động lên latency |
| I/O latency | Thời gian thao tác file/socket | Bottleneck storage/network |
| Queue depth | Số công việc đang chờ | Saturation và backpressure |

### Latency trung bình không đủ

Giả sử trước tối ưu có p50 = 40 ms, p95 = 100 ms, p99 = 250 ms. Sau tối ưu p50 giảm còn 30 ms nhưng p99 tăng lên 500 ms.

Average hoặc median có thể trông tốt hơn trong khi một nhóm người dùng lại chịu tail latency nghiêm trọng. Vì vậy, hãy xem ít nhất p50, p95, p99 và error rate đối với service.

### Throughput phải đi cùng latency

Một service có thể tăng throughput bằng cách tăng concurrency nhưng đồng thời làm queue dài hơn và p99 latency tăng. Không xem throughput tăng là cải thiện nếu latency hoặc error rate vượt SLO.

## 5. Công thức so sánh trước và sau

Gọi:

- **Before:** kết quả baseline.
- **After:** kết quả sau thay đổi.

### Phần trăm giảm latency

Với latency, giá trị thấp hơn thường tốt hơn:

\[
\text{Latency reduction (\%)} =
\frac{\text{Before} - \text{After}}{\text{Before}} \times 100
\]

Ví dụ: latency trung bình giảm từ 100 ms xuống 80 ms:

\[
\frac{100-80}{100}\times100=20\%
\]

Latency giảm 20%.

Nếu kết quả âm, latency đã tăng. Đừng đổi dấu hoặc diễn giải số âm thành cải thiện.

### Speedup ratio

\[
\text{Speedup} = \frac{\text{Before time}}{\text{After time}}
\]

Nếu trước mất 100 ms và sau mất 50 ms, speedup = 2x. Tác vụ mới nhanh gấp hai lần theo metric đang đo.

Speedup không giống phần trăm giảm latency: 2x speedup tương ứng giảm 50% thời gian.

### Phần trăm tăng throughput

Với throughput, giá trị cao hơn thường tốt hơn:

\[
\text{Throughput improvement (\%)} =
\frac{\text{After} - \text{Before}}{\text{Before}} \times 100
\]

Nếu throughput tăng từ 1.000 lên 1.200 request/s:

\[
\frac{1200-1000}{1000}\times100=20\%
\]

Throughput tăng 20%.

### So sánh tài nguyên

Có thể dùng công thức tương tự để tính CPU hoặc memory reduction:

\[
\text{Resource reduction (\%)} =
\frac{\text{Before} - \text{After}}{\text{Before}} \times 100
\]

Luôn ghi rõ đơn vị, phạm vi và điều kiện đo. CPU percentage của một core, CPU của toàn process và CPU của cả container không phải cùng một metric.

## 6. Không dựa vào một lần chạy

Kết quả hiệu năng có nhiễu do:

- JIT compilation và warm-up.
- Class loading và initialization.
- Garbage collection.
- OS scheduling.
- CPU frequency scaling và thermal throttling.
- Background process.
- Container CPU throttling.
- Cache state.
- Network và database variability.
- Thread contention.

Một lần chạy nhanh hơn có thể chỉ là may mắn.

### Chạy nhiều lần và xem phân bố

Với benchmark nhỏ, dùng nhiều measurement iterations và nhiều fork. Với load test, lặp lại các run độc lập và so sánh phân bố latency.

Các thống kê thường dùng:

- Mean: trung bình.
- Median: giá trị giữa sau khi sắp xếp.
- Standard deviation: độ phân tán quanh mean.
- Percentile: p50, p90, p95, p99.
- Confidence interval: khoảng tin cậy của ước lượng.
- JMH error: sai số được báo cáo cùng score.

Không chỉ lấy kết quả tốt nhất. Hãy báo cáo số lần chạy, độ phân tán và khoảng tin cậy khi có thể.

### Thứ tự chạy có thể gây bias

Nếu luôn chạy baseline trước và candidate sau, candidate có thể được hưởng lợi từ cache nóng hoặc JIT đã warm-up. Ngược lại, candidate có thể chịu tải nền khác.

Có thể luân phiên thứ tự chạy, ví dụ:

~~~text
Run 1: Baseline -> Candidate
Run 2: Candidate -> Baseline
Run 3: Baseline -> Candidate
Run 4: Candidate -> Baseline
~~~

Với benchmark quan trọng, JMH forks tạo JVM process độc lập và giúp giảm ảnh hưởng trạng thái từ lần chạy trước.

### So sánh confidence interval

Nếu khoảng sai số của hai kết quả chồng lấn nhiều, chưa đủ bằng chứng để khẳng định thay đổi có cải thiện thực sự. Tăng số lần chạy, giảm nhiễu hoặc dùng thiết kế thử nghiệm tốt hơn.

Đừng tuyên bố một thay đổi 1% là có ý nghĩa nếu biến động tự nhiên của benchmark cũng khoảng 5%.

## 7. Ví dụ Java 17+: so sánh List lookup với HashSet lookup

Ví dụ này so sánh hai cách kiểm tra một giá trị có nằm trong tập dữ liệu hay không:

- **Baseline:** dùng ArrayList.contains(), tìm kiếm tuyến tính.
- **Candidate:** dùng HashSet.contains(), tra cứu theo hash.

Dataset và queries được tạo ngoài vùng đo. Cả hai implementation nhận cùng queries và phải trả cùng số kết quả. Chương trình warm-up trước, đo nhiều vòng, luân phiên thứ tự và so sánh median.

Đây là demonstration có kiểm soát, không thay thế JMH.

Tạo file **BeforeAfterDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.Arrays;

public final class BeforeAfterDemo {
    private static volatile int sink;

    private static int countLinear(
            List<Integer> values, int[] queries) {
        int matches = 0;

        for (int query : queries) {
            if (values.contains(query)) {
                matches++;
            }
        }

        return matches;
    }

    private static int countHashed(
            Set<Integer> values, int[] queries) {
        int matches = 0;

        for (int query : queries) {
            if (values.contains(query)) {
                matches++;
            }
        }

        return matches;
    }

    private static double medianMillis(long[] nanos) {
        long[] sorted = nanos.clone();
        Arrays.sort(sorted);

        return sorted[sorted.length / 2] / 1_000_000.0;
    }

    public static void main(String[] args) {
        final int dataSize = 5_000;
        final int queryCount = 2_000;
        final int warmupIterations = 3;
        final int measurementIterations = 7;

        List<Integer> list = new ArrayList<>(dataSize);
        Set<Integer> set = new HashSet<>(dataSize * 2);

        for (int i = 0; i < dataSize; i++) {
            list.add(i);
            set.add(i);
        }

        int[] queries = new int[queryCount];

        for (int i = 0; i < queryCount; i++) {
            queries[i] = (i * 31) % (dataSize * 2);
        }

        for (int i = 0; i < warmupIterations; i++) {
            sink = countLinear(list, queries);
            sink = countHashed(set, queries);
        }

        long[] linearTimes = new long[measurementIterations];
        long[] hashedTimes = new long[measurementIterations];
        int expectedMatches = countLinear(list, queries);

        for (int i = 0; i < measurementIterations; i++) {
            int linearResult;
            int hashedResult;

            if (i % 2 == 0) {
                long start = System.nanoTime();
                linearResult = countLinear(list, queries);
                linearTimes[i] = System.nanoTime() - start;

                start = System.nanoTime();
                hashedResult = countHashed(set, queries);
                hashedTimes[i] = System.nanoTime() - start;
            } else {
                long start = System.nanoTime();
                hashedResult = countHashed(set, queries);
                hashedTimes[i] = System.nanoTime() - start;

                start = System.nanoTime();
                linearResult = countLinear(list, queries);
                linearTimes[i] = System.nanoTime() - start;
            }

            if (linearResult != expectedMatches
                    || hashedResult != expectedMatches) {
                throw new IllegalStateException(
                        "Implementations returned different results");
            }

            sink = linearResult + hashedResult;
        }

        double linearMedian = medianMillis(linearTimes);
        double hashedMedian = medianMillis(hashedTimes);

        System.out.println("Matches per run: " + expectedMatches);
        System.out.println("Correctness: PASS");
        System.out.printf(
                Locale.ROOT,
                "Median baseline: %.3f ms%n",
                linearMedian);
        System.out.printf(
                Locale.ROOT,
                "Median optimized: %.3f ms%n",
                hashedMedian);
        System.out.printf(
                Locale.ROOT,
                "Median speedup: %.2fx%n",
                linearMedian / hashedMedian);
    }
}
~~~

Biên dịch với Java 17 trở lên:

~~~bash
javac --release 17 BeforeAfterDemo.java
~~~

Chạy:

~~~bash
java BeforeAfterDemo
~~~

Phần output xác định:

~~~text
Matches per run: 1033
Correctness: PASS
~~~

Ba dòng thời gian có dạng:

~~~text
Median baseline: <giá trị thay đổi> ms
Median optimized: <giá trị thay đổi> ms
Median speedup: <giá trị thay đổi>x
~~~

Thời gian thay đổi theo CPU, JDK, OS và tải nền. Trong một lần kiểm tra bằng OpenJDK 24.0.2, chương trình cho median baseline 3.393 ms, median optimized 0.074 ms và speedup 46.16x. Đây chỉ là kết quả của môi trường kiểm tra cụ thể, không phải cam kết hiệu năng cho mọi máy.

### Giải thích kết quả

List.contains() có chi phí tìm kiếm tuyến tính theo số phần tử. HashSet.contains() có độ phức tạp trung bình gần O(1) khi hash distribution phù hợp, nhưng dùng thêm memory và có thể chịu ảnh hưởng của hash collision.

Ví dụ minh họa này cố định dataset, query distribution và số vòng chạy. Trong ứng dụng thực tế, cần đo thêm chi phí tạo HashSet, memory footprint, update dữ liệu và concurrency nếu các chi phí đó nằm trong workload nghiệp vụ.

## 8. Dùng JMH để so sánh implementation nghiêm túc

JMH phù hợp khi so sánh method hoặc thuật toán nhỏ. Nó quản lý warm-up, measurement, fork, state và tiêu thụ kết quả để giảm các lỗi phổ biến của benchmark tự viết.

Ví dụ benchmark cùng dataset và query cho hai implementation:

~~~java
package org.example;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.concurrent.TimeUnit;

import org.openjdk.jmh.annotations.*;

@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.MICROSECONDS)
@Warmup(iterations = 5, time = 1)
@Measurement(iterations = 5, time = 1)
@Fork(3)
public class LookupComparison {
    @Param({"1000", "5000", "20000"})
    public int size;

    private List<Integer> list;
    private Set<Integer> set;
    private int[] queries;

    @Setup(Level.Trial)
    public void setup() {
        list = new ArrayList<>(size);
        set = new HashSet<>(size * 2);

        for (int i = 0; i < size; i++) {
            list.add(i);
            set.add(i);
        }

        queries = new int[2000];

        for (int i = 0; i < queries.length; i++) {
            queries[i] = (i * 31) % (size * 2);
        }
    }

    @Benchmark
    public int baselineListContains() {
        int matches = 0;

        for (int query : queries) {
            if (list.contains(query)) {
                matches++;
            }
        }

        return matches;
    }

    @Benchmark
    public int candidateHashSetContains() {
        int matches = 0;

        for (int query : queries) {
            if (set.contains(query)) {
                matches++;
            }
        }

        return matches;
    }
}
~~~

Trong ví dụ, @Setup(Level.Trial) chuẩn bị dữ liệu trước khi benchmark. Hai method trả về số match để JMH tiêu thụ kết quả.

### Cấu hình Maven tối thiểu

Thêm JMH 1.37 và annotation processor vào pom.xml:

~~~xml
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
~~~

Cấu hình compiler release 17 và annotation processor tương ứng; dùng Maven Shade Plugin với main class org.openjdk.jmh.Main để tạo executable benchmark JAR. Có thể dùng archetype chính thức của JMH để khởi tạo project.

Chạy benchmark:

~~~bash
mvn clean package
java -jar target/benchmarks.jar LookupComparison
~~~

Lưu kết quả JSON:

~~~bash
java -jar target/benchmarks.jar LookupComparison -rf json -rff comparison.json
~~~

Thử thêm profiler allocation:

~~~bash
java -jar target/benchmarks.jar LookupComparison -prof gc
~~~

### Đọc kết quả

JMH hiển thị benchmark name, mode, count, score, error và unit. Với AverageTime, score thấp hơn là tốt hơn. Với Throughput, score cao hơn là tốt hơn.

So sánh:

- Cùng input size.
- Cùng mode và output unit.
- Cùng warm-up, measurement và fork.
- Score cùng error.
- Allocation và GC khi dùng -prof gc.
- Kết quả qua nhiều fork.

Không so sánh AverageTime của một bản với Throughput của bản khác. Không thay đổi benchmark configuration giữa hai phiên bản rồi quy toàn bộ khác biệt cho code.

## 9. So sánh service bằng load test

Một method benchmark không thể mô phỏng toàn bộ service. Để so sánh trước và sau deploy, cần chạy cùng workload lên hai phiên bản trong môi trường tương đương.

### Các bước

1. Deploy baseline vào môi trường benchmark.
2. Deploy candidate vào môi trường tương đương.
3. Dùng cùng dataset, request mix và concurrency.
4. Warm-up cả hai phiên bản.
5. Chạy load test trong cùng thời lượng.
6. Thu throughput, p50, p95, p99, error rate và resource usage.
7. Lặp lại nhiều run.
8. So sánh phân bố và các khoảng tin cậy.
9. Kiểm tra regression ở endpoint hoặc workload riêng.
10. Chỉ kết luận khi cải thiện vượt mức nhiễu và không vi phạm SLO.

### Ví dụ bảng kết quả

Bảng dưới đây là dữ liệu giả định để minh họa cách trình bày:

| Metric | Before | After | Nhận xét |
|---|---:|---:|---|
| Throughput | 1.000 req/s | 1.180 req/s | Tăng 18% |
| p50 latency | 40 ms | 35 ms | Giảm 12,5% |
| p95 latency | 110 ms | 90 ms | Giảm 18,2% |
| p99 latency | 260 ms | 240 ms | Giảm 7,7% |
| Error rate | 0,10% | 0,08% | Giảm |
| CPU | 75% | 82% | Tăng chi phí CPU |
| Memory | 1,8 GB | 2,0 GB | Tăng 0,2 GB |

Trong ví dụ này throughput và latency cải thiện nhưng CPU và memory tăng. Cần xem giới hạn tài nguyên, headroom và chi phí vận hành trước khi quyết định rollout.

## 10. Dùng JFR để giải thích vì sao kết quả thay đổi

JFR hỗ trợ chẩn đoán khác biệt giữa baseline và candidate. Nên ghi recording trong cùng workload, thời lượng và settings.

Bắt đầu recording:

~~~bash
jcmd <pid> JFR.start name=before settings=profile duration=60s filename=before.jfr
~~~

Sau khi deploy candidate, ghi recording tương đương:

~~~bash
jcmd <pid> JFR.start name=after settings=profile duration=60s filename=after.jfr
~~~

Xem summary:

~~~bash
jfr summary before.jfr
jfr summary after.jfr
~~~

Mở hai file bằng JDK Mission Control và so sánh:

- CPU hot methods và execution samples.
- Allocation rate và object allocation.
- Garbage collection count, pause và total time.
- File/socket I/O duration.
- Lock contention và thread parking.
- Thread CPU load.
- JIT compilation và class loading.

Profile settings thu thập nhiều dữ liệu hơn default settings và có overhead cao hơn. Giữ cấu hình giống nhau giữa hai recording và tránh so sánh một recording profile với một recording default.

JFR giải thích hoạt động JVM; nó không thay thế load test hoặc application-level latency metrics.

## 11. Phân biệt cải thiện thật với thay đổi do nhiễu

Một thay đổi nhỏ có thể nằm trong phạm vi biến động tự nhiên.

Ví dụ:

| Run | Before | After |
|---|---:|---:|
| 1 | 10,2 ms | 9,8 ms |
| 2 | 9,7 ms | 10,0 ms |
| 3 | 10,1 ms | 9,9 ms |
| 4 | 9,9 ms | 9,7 ms |
| 5 | 10,3 ms | 10,1 ms |

Các số trên là ví dụ giả định. Candidate có vẻ hơi nhanh hơn, nhưng độ phân tán có thể lớn hơn chênh lệch. Cần thêm run hoặc dùng JMH để đánh giá error và confidence interval.

### Khi kết quả không ổn định

Kiểm tra:

- CPU có bị cạnh tranh bởi process khác không?
- Có thermal throttling hoặc power saving không?
- Container có bị CPU throttling không?
- GC có xảy ra khác thời điểm không?
- Cache có cùng trạng thái không?
- Input có cùng phân bố không?
- Database hoặc remote dependency có biến động không?
- Có background job chạy xen kẽ không?
- Số sample/iteration có đủ không?

Nếu nhiễu lớn, cải thiện phép đo trước khi kết luận về code.

## 12. Những sai lầm thường gặp

### Chỉ đo một lần trước và một lần sau

Một lần chạy dễ bị ảnh hưởng bởi JIT, GC, cache và OS scheduling. Chạy nhiều iteration và fork.

### Chỉ nhìn average latency

Average có thể cải thiện trong khi p99 xấu đi. Xem percentile và error rate.

### Chỉ nhìn throughput

Throughput tăng có thể do queue dài hơn, concurrency cao hơn hoặc latency tăng. Đánh giá đồng thời latency và SLO.

### Thay nhiều yếu tố cùng lúc

Nếu thay code, JDK, heap và GC cùng lúc, không thể quy nguyên nhân cho một thay đổi. Thay từng yếu tố hoặc thiết kế thử nghiệm có kiểm soát.

### So sánh cold cache với warm cache

Candidate có thể được hưởng lợi từ cache đã nóng. Xác định rõ cold-start hay steady-state và áp dụng giống nhau.

### Dùng benchmark không đại diện

Một method benchmark nhỏ có thể không phản ánh allocation, I/O, lock hoặc request mix của production. Dùng load test cho service.

### Chỉ tối ưu method đứng đầu profiler

Method hot có thể là thư viện được gọi nhiều từ caller. Xem call tree và workload trước khi sửa.

### Bỏ qua chi phí setup

Nếu candidate cần xây dựng cache hoặc HashSet trước mỗi operation nhưng benchmark loại setup khỏi vùng đo, kết quả chỉ đúng khi cấu trúc đó được tái sử dụng trong thực tế.

### Báo speedup mà không nêu điều kiện

Luôn ghi JDK, CPU, input, warm-up, iterations, forks, mode và đơn vị. Không công bố một con số speedup tách rời môi trường đo.

## 13. Đưa kết quả vào quyết định rollout

Sau khi benchmark và load test, cần quyết định candidate có đủ an toàn để rollout hay không.

### Canary hoặc gradual rollout

Khi có thể, triển khai candidate cho một tỷ lệ traffic nhỏ trước. So sánh cùng thời điểm và cùng request mix để phát hiện regression.

Theo dõi:

- Error rate.
- p50/p95/p99 latency.
- Throughput.
- CPU và memory.
- GC pause.
- Saturation của thread pool, connection pool và queue.
- Các endpoint quan trọng.

Đặt ngưỡng rollback trước khi triển khai. Nếu candidate vượt SLO hoặc gây error spike, dừng rollout và quay lại baseline theo quy trình.

### Kiểm tra regression ngoài phạm vi tối ưu

Một thay đổi có thể cải thiện endpoint A nhưng làm endpoint B chậm hơn. Kiểm tra các nhóm request khác nhau và toàn service.

Đừng chỉ đo đường code vừa sửa; cần xác nhận không có regression ở những workload liên quan.

### Lưu bằng chứng so sánh

Một báo cáo performance nên ghi:

- Baseline và candidate version/commit.
- Mục tiêu thay đổi.
- Môi trường và cấu hình.
- Workload và input.
- Công cụ, settings và thời gian đo.
- Số lần chạy và phương pháp tổng hợp.
- Bảng metric before/after.
- Confidence/error hoặc độ phân tán.
- Correctness result.
- Regression và trade-off.
- Kết luận và điều kiện rollout.

## 14. Quy trình so sánh trước và sau hoàn chỉnh

1. Xác định mục tiêu tối ưu và metric chính.
2. Chọn công cụ theo cấp độ: nanoTime, JMH, JFR hoặc load test.
3. Ghi lại baseline version, JDK, JVM flags và môi trường.
4. Chuẩn bị dataset và workload đại diện.
5. Chạy correctness tests cho baseline và candidate.
6. Warm-up cả hai phiên bản theo cùng cách.
7. Chạy nhiều measurement iterations hoặc load-test runs.
8. Luân phiên thứ tự hoặc dùng fork độc lập để giảm bias.
9. Thu latency, throughput, percentile, error rate và tài nguyên.
10. Dùng JFR để giải thích CPU, GC, I/O, allocation và lock.
11. Tính phần trăm cải thiện và speedup bằng đúng metric.
12. Đánh giá độ phân tán và ý nghĩa thống kê.
13. Kiểm tra memory, CPU và endpoint khác có regression không.
14. Lưu báo cáo cùng cấu hình và bằng chứng.
15. Canary/gradual rollout và theo dõi SLO.
16. Giữ candidate khi cải thiện có thể lặp lại và không vi phạm yêu cầu chất lượng.

## 15. Checklist trước khi công bố cải thiện

- [ ] Correctness của baseline và candidate đã được xác nhận.
- [ ] Có baseline trước thay đổi.
- [ ] Cùng JDK, JVM flags và phần cứng.
- [ ] Cùng dataset, input và request mix.
- [ ] Cùng warm-up, measurement và concurrency.
- [ ] Có đủ iteration/fork/run.
- [ ] Không chọn kết quả tốt nhất một cách tùy tiện.
- [ ] Có mean/median và percentile phù hợp.
- [ ] Có error hoặc confidence interval khi cần.
- [ ] Latency và throughput được đánh giá cùng nhau.
- [ ] Error rate và SLO không bị xấu đi.
- [ ] CPU, memory, allocation và GC đã được kiểm tra.
- [ ] Đã kiểm tra regression ở workload khác.
- [ ] JFR recording dùng cùng settings nếu so sánh.
- [ ] Có ghi lại môi trường, version và lệnh chạy.
- [ ] Có kế hoạch rollout/rollback nếu áp dụng production.

## 16. Thuật ngữ cần nhớ

| Thuật ngữ | Ý nghĩa |
|---|---|
| Baseline | Kết quả tham chiếu trước thay đổi |
| Candidate | Phiên bản hoặc phương án đang được đánh giá |
| Before/After | Số liệu trước và sau thay đổi |
| Benchmark | Phép đo có kiểm soát cho một workload |
| JMH | Java Microbenchmark Harness |
| Load test | Kiểm tra service dưới workload và concurrency xác định |
| Latency | Thời gian hoàn thành một operation/request |
| Throughput | Số operation/request hoàn thành trên đơn vị thời gian |
| p50/p95/p99 | Các phân vị latency |
| Speedup | Tỷ lệ thời gian baseline chia cho thời gian candidate |
| Warm-up | Giai đoạn để JVM nạp class và tối ưu JIT |
| Fork | JVM process độc lập dùng cho benchmark |
| Confidence interval | Khoảng tin cậy của một ước lượng |
| Noise | Biến động không thuộc thay đổi đang thử |
| Regression | Một metric hoặc workload xấu đi sau thay đổi |
| Canary | Triển khai cho một phần nhỏ traffic để quan sát |
| SLO | Mục tiêu mức độ dịch vụ |
| JFR | Java Flight Recorder, công cụ ghi runtime events |
| JMC | JDK Mission Control, công cụ phân tích JFR |

So sánh trước và sau chỉ đáng tin khi correctness, workload, môi trường và cách đo được kiểm soát. Dùng JMH cho microbenchmark, load test cho service, JFR để giải thích hoạt động JVM và metrics để đánh giá tác động thực tế. Chỉ công bố cải thiện khi kết quả lặp lại được, sai số được hiểu rõ và không tạo regression ở latency, error rate hoặc tài nguyên.

## Tài liệu tham khảo

- OpenJDK — [Java Microbenchmark Harness (JMH)](https://github.com/openjdk/jmh)
- Oracle JDK 24 — [System.nanoTime()](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/System.html#nanoTime())
- Oracle JDK 24 — [Java Flight Recorder](https://docs.oracle.com/en/java/javase/24/jfapi/flight-recorder-api-programmers-guide.pdf)
- Oracle JDK 24 — [Troubleshoot Performance Issues Using Flight Recorder](https://docs.oracle.com/en/java/javase/24/troubleshoot/troubleshoot-performance-issues-using-jfr.html)
- Oracle JDK 24 — [The jcmd Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html)
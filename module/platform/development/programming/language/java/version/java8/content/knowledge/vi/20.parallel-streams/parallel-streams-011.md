# Đo throughput, latency và độ đúng thay vì mặc định Stream song song nhanh hơn

`parallelStream()` không đồng nghĩa “chạy nhanh hơn”. Nó cho phép Java chia pipeline Stream để xử lý các phần trên nhiều luồng, nhưng phải trả thêm chi phí **chia tác vụ, lập lịch, phối hợp kết quả, đồng bộ và dùng tài nguyên**. Có tình huống giảm thời gian xử lý, có tình huống tăng latency hoặc giảm throughput, thậm chí sai kết quả nếu pipeline có shared mutable state hay phép reduction không đáp ứng hợp đồng.

Trong thực hành Java 8 và các JDK hiện đại, quyết định dùng `stream()` hay `parallelStream()` nên dựa vào **ba nhóm bằng chứng độc lập**:

1. **Độ đúng (correctness)**: hai cách thực thi có tạo kết quả đúng theo hợp đồng nghiệp vụ trong mọi trường hợp quan trọng không?
2. **Latency**: một tác vụ hoặc yêu cầu mất bao lâu, nhất là mức p95/p99 chứ không chỉ trung bình?
3. **Throughput**: hệ thống hoàn tất bao nhiêu tác vụ/yêu cầu trên một đơn vị thời gian với mức tải và giới hạn tài nguyên xác định?

Bài này thuộc chủ đề **Stream song song**, chỉ sử dụng các nguyên tắc và API vẫn áp dụng cho Java hiện đại. Ví dụ đầy đủ tương thích Java 8, chạy với JDK 17+; benchmark chuyên nghiệp dùng JMH của OpenJDK.

## 1. Hiểu đúng ba thước đo

### 1.1. Latency: thời gian của một công việc

**Latency** là khoảng từ khi bắt đầu đến khi hoàn tất một phép xử lý. Với một tác vụ Stream độc lập, có thể đo **wall-clock duration** bằng `System.nanoTime()`:

~~~java
long start = System.nanoTime();
long answer = data.stream().mapToLong(Item::getValue).sum();
long elapsedNanos = System.nanoTime() - start;
~~~

Đây là **mã minh họa, không phải chương trình độc lập**; giả sử `data` và `Item` tồn tại. Thời gian đó bao gồm tạo/tiêu thụ pipeline và những chi phí trong đoạn đo. Nó **không đại diện mặc nhiên cho toàn bộ latency HTTP request** nếu request còn truy cập DB, serialize JSON, chờ queue, gửi mạng...

Đừng đánh giá bằng một số duy nhất; lấy phân phối qua nhiều lần chạy:

- **p50 (median)**: 50% lần đo không vượt mức này.
- **p95**: khoảng 95% lần đo không vượt mức này; hữu ích khi xem “đuôi chậm”.
- **p99**: tập trung vào các trường hợp hiếm nhưng rất chậm.
- **Max**: lần chậm nhất trong mẫu, nhạy với nhiễu; cần diễn giải theo kích thước mẫu.

Ví dụ giả định: hai cách cùng có p50 = 4 ms, nhưng cách parallel có p99 = 90 ms thay vì 12 ms do contention. Nếu người dùng cần phản hồi ổn định, parallel có thể **không đạt mục tiêu** dù p50 bằng nhau. Các con số ở đây chỉ để minh họa cách phân tích, **không phải số liệu đo thực tế**.

### 1.2. Throughput: lượng công việc hoàn tất

Với `N` tác vụ hoàn thành trong thời gian tường `T` giây:

~~~text
throughput = N / T
~~~

Đơn vị thường là **calls/s**, **records/s**, **requests/s (RPS)** hoặc **MB/s**. Quan trọng phải nói rõ “một đơn vị công việc” là gì.

- **Throughput một caller**: một vòng lặp gọi phép tính liên tục, không có nhiều client đồng thời. Chỉ cho biết tốc độ hoàn tất khi một caller liên tục gửi tác vụ.
- **Throughput hệ thống**: nhiều yêu cầu có thể ở trạng thái đang xử lý cùng lúc, chia sẻ CPU, pool, I/O và bộ nhớ. Phải đo dưới một mức tải/độ đồng thời cụ thể, thường bằng load test.
- Một tác vụ parallel có thể có latency thấp hơn nhưng tiêu thụ nhiều CPU hơn; ở tải lớn, nhiều tác vụ parallel cạnh tranh làm throughput tổng **giảm**.

Vì vậy đừng viết “parallel nhanh gấp 2 lần” nếu chưa nói **đo latency hay throughput, kích thước input, mức concurrency và cấu hình máy**.

### 1.3. Correctness: điều kiện bắt buộc trước tối ưu

Kết quả nhanh nhưng sai dữ liệu không phải tối ưu. Với nguồn và yêu cầu giống nhau, cần kiểm tra:

- **Giá trị**: tổng, số lượng, min/max, map và đối tượng kết quả có đúng không?
- **Tính đầy đủ**: không mất phần tử, không đếm lặp, không tạo thêm phần tử.
- **Thứ tự**: có phải giữ *encounter order* không? Hay chỉ cần tập/đa tập phần tử?
- **Tính ổn định**: chạy lại nhiều lần và nhiều phân phối dữ liệu có ra kết quả theo cùng hợp đồng không?
- **Ngoại lệ và side effects**: dữ liệu nguồn có bị sửa ngoài ý muốn, lỗi có được xử lý đúng không?
- **Tính chính xác số học**: `double` có thể sai khác do làm tròn khi thứ tự gộp khác nhau.

Khi hai cách không tương đương về nghiệp vụ, **chưa được phép so sánh tốc độ như hai phương án thay thế**.

## 2. Vì sao parallel Stream không mặc định nhanh hơn?

### 2.1. Cái được và chi phí phải trả

Khi `LongStream.range(0, n).parallel().sum()` chạy, Java có cơ hội chia nguồn thành nhiều phần, tính các tổng cục bộ rồi kết hợp. Điều này hiệu quả khi công việc đủ lớn, chia đều và có phép gộp đúng. Nhưng có thêm:

1. **Splitting**: `Spliterator` phải chia nguồn. `ArrayList`, array và numeric ranges thường chia thuận lợi; nguồn khó chia hoặc truy cập tuần tự có thể không thuận lợi.
2. **Scheduling**: tạo/điều phối tác vụ và chuyển ngữ cảnh tốn chi phí.
3. **Combining**: phải hợp nhất partial results; collector sử dụng map hoặc danh sách có thể tốn bộ nhớ và công sức merge.
4. **Synchronization/contention**: dùng cấu trúc concurrent hoặc chia sẻ tài nguyên có thể gây nghẽn.
5. **Memory bandwidth/cache/GC**: nhiều luồng cùng đọc/ghi, boxing và cấp phát thêm đối tượng có thể tăng áp lực bộ nhớ.
6. **Ordering constraints**: một số thao tác cần giữ thứ tự, làm mất cơ hội tối ưu song song.
7. **Pool contention**: những request parallel khác có thể dùng chung tài nguyên xử lý.

Vì vậy tổng thời gian không chỉ là “chi phí tuần tự chia cho số core”. Một phần công việc vẫn phải chạy tuần tự, và thêm overhead có thể vượt lợi ích.

### 2.2. Amdahl và điểm hòa vốn

Nếu tỷ lệ công việc có thể song song là `p` và ta có tối đa `k` phần xử lý hiệu quả, mô hình đơn giản cho giới hạn tăng tốc:

~~~text
speedup lý tưởng ≈ 1 / ((1 - p) + p / k)
~~~

Ví dụ khi `p = 0.8` và `k = 4`, tăng tốc tối đa lý tưởng là `1 / (0.2 + 0.2) = 2.5 lần`, **chưa tính overhead**. Công thức chỉ là một mô hình; CPU thực, memory bandwidth, GC, scheduling và độ cân bằng tác vụ làm kết quả thay đổi.

**Điểm hòa vốn** là kích thước dữ liệu/cường độ công việc mà lợi ích parallel bắt đầu vượt overhead. Điểm này **không có một con số cố định** cho tất cả pipeline; phụ thuộc nguồn, thao tác mỗi phần tử, máy, JDK và tình trạng tải.

### 2.3. Nguồn và phép toán ảnh hưởng lớn

| Điều kiện | Tác động thường gặp | Cách kiểm chứng |
| --- | --- | --- |
| Array/`ArrayList`/`IntStream.range` chia đều | Có tiềm năng tốt hơn | Đo với n nhỏ, vừa, lớn |
| Nguồn khó chia hoặc dữ liệu rất ít | Overhead có thể chiếm ưu thế | So sánh thời gian và allocations |
| Mapper tốn CPU và stateless | Có cơ hội tận dụng nhiều core | Xác nhận CPU và speedup dưới tải phù hợp |
| `sorted()`, `distinct()`, `limit()`, `skip()` với yêu cầu ordered | Có thể thêm phối hợp/buffer | Đo riêng pipeline thật, giữ nguyên semantics |
| `forEachOrdered()` | Giữ thứ tự hành động, có thể giảm lợi ích parallel | So với giải pháp đúng theo yêu cầu thứ tự |
| Collector xây map/list lớn | Chi phí combine và cấp phát | Đo heap/GC, throughput, latency |
| Nhiều khóa “nóng”, synchronized update | Tranh chấp tăng | Thử phân bố khóa lệch và đồng đều |
| Blocking I/O trong mapper/accumulator | Có thể cạn tài nguyên luồng | Cân nhắc thiết kế bất đồng bộ/bounded executor |
| Nhiều request dùng parallel cùng lúc | Tranh CPU và tài nguyên chung | Load test với concurrency tăng dần |

Không được tự bỏ `ORDERED`, thay `findFirst()` thành `findAny()` hoặc thay `forEachOrdered()` thành `forEach()` chỉ vì đo thấy nhanh hơn; các thay đổi đó **có thể thay đổi hợp đồng kết quả**.

## 3. Độ đúng của parallel Stream: quy tắc tối thiểu

### 3.1. Không can thiệp nguồn và hạn chế side effects

Một lambda trong pipeline nên **stateless** và **non-interfering**: không dựa vào trạng thái mutable chia sẻ và không sửa nguồn đang xử lý. Ví dụ sai:

~~~java
// PHẢN VÍ DỤ — ArrayList không an toàn khi nhiều thread cùng add().
List<Integer> results = new ArrayList<>();
numbers.parallelStream().forEach(results::add);
~~~

Đoạn trên không độc lập: `numbers` là danh sách giả định và cần import `List`/`ArrayList`. Kết quả có thể thiếu phần tử, sai thứ tự hoặc hỏng cấu trúc dữ liệu.

Cách đúng nếu cần danh sách giữ encounter order:

~~~java
List<Integer> results = numbers.parallelStream()
    .map(x -> x * 2)
    .collect(Collectors.toList());
~~~

`Collectors.toList()` được Stream framework điều phối đúng cho parallel reduction; **không yêu cầu `ArrayList` tự thread-safe**. Với nguồn có encounter order như `List`, thứ tự phần tử của kết quả được duy trì theo ngữ nghĩa collector, nhưng loại List cụ thể và mutability không được `Collectors.toList()` bảo đảm.

Nếu mục tiêu là đếm/tổng, ưu tiên `count()`/`sum()`/`reduce()` thay vì ghi vào một biến ngoài rồi dùng `forEach`.

### 3.2. Phép reduction cần identity và associativity đúng

~~~java
// Đúng: 0 là identity của cộng, cộng long có tính kết hợp
long sum = numbers.parallelStream()
    .mapToLong(Integer::longValue)
    .sum();
~~~

Không dùng:

~~~java
// Sai: 10 không phải identity của phép cộng; parallel có thể cộng 10 nhiều lần.
int bad = numbers.parallelStream().reduce(10, Integer::sum);
~~~

`reduce(identity, accumulator)` yêu cầu identity thật sự trung hòa; accumulator phải associative, stateless và không can thiệp nguồn. Phép trừ thường không kết hợp; thứ tự gộp trong parallel không cố định.

### 3.3. Thứ tự: kết quả bằng nhau không có nghĩa thứ tự giống nhau

~~~java
List<Integer> ordered = numbers.parallelStream()
    .map(x -> x * 2)
    .collect(Collectors.toList());
~~~

Với `List` ordered, collector tạo danh sách theo encounter order. Nhưng:

~~~java
numbers.parallelStream().forEach(System.out::println);
~~~

không bảo đảm thứ tự in của từng phần tử. Nếu nghiệp vụ chỉ cần tập giá trị, so sánh theo tập/đa tập thay vì so sánh chuỗi in ra; nếu cần thứ tự, dùng thao tác có hợp đồng giữ thứ tự và đưa chi phí đó vào benchmark.

`findAny()` cho phép chọn bất kỳ phần tử nào thỏa, nên không nên đánh dấu thất bại chỉ vì phần tử chọn khác `findFirst()` khi yêu cầu chỉ là “một phần tử bất kỳ”. Tương tự, collector concurrent/unordered không có nghĩa có quyền bỏ phần tử.

### 3.4. Dấu phẩy động: đúng theo toán học hay đúng theo bit?

Với `double`, `(a+b)+c` có thể khác `a+(b+c)` do rounding. Parallel Stream có thể gộp theo nhóm khác phiên bản tuần tự; tổng/average có thể khác các bit cuối dù thuật toán hợp lệ.

Khi so kết quả thực, quyết định **tolerance** theo miền dữ liệu (độ lớn giá trị, độ chính xác mong muốn, số phần tử); kiểm tra cả `NaN`/Infinity. Đừng dùng một epsilon cố định thiếu cơ sở cho mọi bài toán. Nếu cần giá trị thập phân chính xác tuyệt đối, cân nhắc `BigDecimal` và chiến lược làm tròn xác định.

### 3.5. Đúng dưới tải và chạy lặp lại

Lỗi concurrency có thể không xuất hiện trong lần chạy đầu tiên. Hãy test:

- Stream rỗng, một phần tử, rất nhiều phần tử; dữ liệu âm, trùng, extreme values.
- Nguồn ordered và unordered; cả tuần tự và song song.
- Lặp lại nhiều lần ở kích thước lớn, nhiều core và các độ đồng thời khác nhau.
- Collector với combiner: không mất phần tử khi merge partial results.
- Phát hiện race bằng kiểm thử và công cụ phù hợp; **một lần chạy đúng không chứng minh thread-safe**.

## 4. Quy trình đo có ý nghĩa: từ correctness tới latency và throughput

### Bước 1 — Chốt workload và định nghĩa kết quả đúng

Giữ **cùng input và cùng phép toán** cho hai phiên bản. Ví dụ so sánh `Arrays.stream(values).filter(...).map(...).sum()` tuần tự với chính pipeline đó nhưng thêm `parallel()`. Không được đổi thuật toán, bỏ filter hoặc đổi điều kiện thứ tự rồi coi là so sánh ngang bằng.

Kiểm tra reference result độc lập (công thức toán, đối chiếu mẫu nhỏ, assertion hoặc đặc tả nghiệp vụ). Khi kết quả không tương đương, dừng benchmark và sửa logic trước.

### Bước 2 — Xác định hai mục tiêu đo

**Single-call latency:** mỗi lần thực thi một pipeline; đo nhiều mẫu và báo p50/p95/p99, median, max.

**Throughput:** xác định số tác vụ hoàn tất mỗi giây, kích thước input cho một tác vụ và số caller đồng thời. Nếu dùng **một caller tuần tự gọi** 100 lần, kết quả chỉ là throughput của một caller, không phải hiệu năng server có 100 request đồng thời.

Với HTTP service, đo thêm RPS, error rate, latency end-to-end dưới tải đều và tải đỉnh; phân biệt **offered load** (yêu cầu gửi) và **completed throughput** (yêu cầu thực sự xử lý xong).

### Bước 3 — Warm-up, forks và môi trường

JIT compiler tối ưu sau khi mã chạy một thời gian; số đo cold-start và steady-state khác nhau. Để đo steady-state, phải có warm-up; benchmark cần nhiều iteration và nhiều JVM fork để giảm thiên lệch do trạng thái JVM.

Ghi rõ:

- Phiên bản JDK, cờ JVM, số core/CPU quota container, RAM và GC.
- Kích thước nguồn, cách phân bố dữ liệu, số khóa, độ nặng mapper, ordered hay unordered.
- Số thread gọi benchmark, tình trạng CPU/GC, CPU nhiệt/giới hạn nguồn, tải nền.
- Tỷ lệ chạy tuần tự và song song, cùng số lần warm-up/measurement.
- Benchmark đo **riêng phép tính** hay cả đọc DB, cấp phát nguồn và serialize kết quả.

Không thay đổi phần lớn các yếu tố cùng lúc. Một benchmark tốt có thể tái lập và có mục tiêu đo rõ ràng.

### Bước 4 — Đo latency đúng cách

Với một đoạn chương trình Java thông thường, `System.nanoTime()` dùng đo **elapsed duration**, không dùng `currentTimeMillis()` để suy ra chi tiết thời gian ngắn. Thu nhiều mẫu, sắp xếp và lấy các percentile. Đừng in log bên trong vùng đo, vì console I/O sẽ lấn át phép xử lý.

**Lưu ý:** một vòng `nanoTime()` thủ công chỉ phù hợp để minh họa/kiểm tra sơ bộ. JIT, dead-code elimination, GC, allocation, scheduling và sự chia sẻ CPU có thể làm lệch kết quả. Khi cần benchmark nghiêm túc, sử dụng **JMH**.

### Bước 5 — Đo throughput dưới tải tương ứng

Với batch gồm 100 lời gọi hoàn tất trong 2 giây, throughput của đúng batch và kiểu caller đó là **50 calls/s**. Nhưng nếu server có 50 request đồng thời, mỗi request lại gọi `parallelStream()`, tổng CPU có thể bão hòa và latency đuôi tăng.

Với ứng dụng server, thử nhiều mức concurrency/RPS và thu **latency distribution, completed throughput, errors, CPU, GC, heap, thread activity**. Xem điểm bão hòa: tăng tải mà throughput không tăng nữa, p95/p99 và hàng đợi tăng thì việc tối ưu một request đơn lẻ chưa chắc giúp toàn hệ thống.

### Bước 6 — Ra quyết định trên ràng buộc nghiệp vụ

Ví dụ tiêu chí có thể là:

~~~text
Điều kiện bắt buộc: kết quả đúng, không race/lost updates.
SLO latency: p95 dưới ngưỡng cam kết ở mức tải mục tiêu.
Throughput: RPS hoàn tất không thấp hơn baseline.
Tài nguyên: CPU, heap, GC và số thread nằm trong ngân sách.
~~~

Đặt ngưỡng dựa vào hệ thống thật thay vì lấy ví dụ trong tài liệu làm mặc định. Chỉ giữ parallel khi có cải thiện **ở mục tiêu quan trọng** và không phá vỡ các ràng buộc còn lại.

## 5. Ví dụ Java hoàn chỉnh: kiểm tra đúng, đo sơ bộ p50/p95 và calls/s

Chương trình sau có thể chạy bằng JDK 17+ và chỉ dùng API đã có từ Java 8. Nó cố ý tách **kết quả chắc chắn** khỏi **thời gian thay đổi theo máy**. Đây là công cụ thử nghiệm nhỏ để hiểu cách đo, **không thay thế JMH**.

Lưu thành **`ParallelStreamMetricsDemo.java`**:

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.Locale;
import java.util.stream.Collectors;
import java.util.stream.LongStream;

public class ParallelStreamMetricsDemo {
    private static final int SIZE = 200_000;
    private static final int WARMUP = 10;
    private static final int REPETITIONS = 40;
    private static final long[] DATA =
            LongStream.range(0, SIZE).toArray();

    private static volatile long sink;

    static long calculate(boolean parallel) {
        LongStream stream = Arrays.stream(DATA);
        if (parallel) {
            stream = stream.parallel();
        }
        return stream
                .filter(x -> x % 3L == 0L)
                .map(x -> x + 1L)
                .sum();
    }

    static final class Metrics {
        final double p50Ms;
        final double p95Ms;
        final double callsPerSecond;

        Metrics(double p50Ms, double p95Ms,
                double callsPerSecond) {
            this.p50Ms = p50Ms;
            this.p95Ms = p95Ms;
            this.callsPerSecond = callsPerSecond;
        }
    }

    static Metrics sample(boolean parallel) {
        long[] latencies = new long[REPETITIONS];
        long batchStart = System.nanoTime();

        for (int i = 0; i < REPETITIONS; i++) {
            long begin = System.nanoTime();
            sink = calculate(parallel);
            latencies[i] = System.nanoTime() - begin;
        }

        long batchNanos = System.nanoTime() - batchStart;
        Arrays.sort(latencies);

        int p50Index = (int) Math.ceil(
                0.50 * latencies.length) - 1;
        int p95Index = (int) Math.ceil(
                0.95 * latencies.length) - 1;

        return new Metrics(
                latencies[p50Index] / 1_000_000.0,
                latencies[p95Index] / 1_000_000.0,
                REPETITIONS * 1_000_000_000.0 / batchNanos
        );
    }

    static void show(String name, Metrics m) {
        System.out.printf(Locale.ROOT,
                "%s: throughput=%.1f calls/s p50=%.3f ms p95=%.3f ms%n",
                name, m.callsPerSecond, m.p50Ms, m.p95Ms);
    }

    public static void main(String[] args) {
        // Có 66_667 số chia hết cho 3 trong [0, 200_000).
        // Mỗi số x góp (x + 1) vào tổng.
        long count = (SIZE + 2L) / 3L;
        long expected = 3L * count * (count - 1L) / 2L + count;

        long sequential = calculate(false);
        long parallel = calculate(true);

        List<Long> seqList = LongStream.range(0, 10)
                .boxed().collect(Collectors.toList());
        List<Long> parList = LongStream.range(0, 10)
                .parallel().boxed().collect(Collectors.toList());

        System.out.println("expectedSum=" + expected);
        System.out.println("sequentialSum=" + sequential);
        System.out.println("parallelSum=" + parallel);
        System.out.println("correct=" +
                (expected == sequential && expected == parallel));
        System.out.println("orderedEquivalent=" +
                seqList.equals(parList));
        System.out.println("emptyParallelSum=" +
                LongStream.empty().parallel().sum());

        if (sequential != expected || parallel != expected) {
            throw new AssertionError("Incorrect result");
        }

        // Warm-up cả hai cách trước khi lấy mẫu.
        for (int i = 0; i < WARMUP; i++) {
            sink = calculate(false);
            sink = calculate(true);
        }

        // Thứ tự hai lượt đo vẫn có thể tạo bias:
        // dùng JMH với nhiều forks cho kết luận thực sự.
        Metrics seqMetrics = sample(false);
        Metrics parMetrics = sample(true);

        show("sequential", seqMetrics);
        show("parallel", parMetrics);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 ParallelStreamMetricsDemo.java
java ParallelStreamMetricsDemo
~~~

**Sáu dòng đầu của stdout sẽ là:**

~~~text
expectedSum=6666700000
sequentialSum=6666700000
parallelSum=6666700000
correct=true
orderedEquivalent=true
emptyParallelSum=0
~~~

Sau đó chương trình in **hai dòng** có nhãn `sequential` và `parallel` với throughput, p50 và p95 đo thực tế. Các số đo **phụ thuộc máy/JVM/tải hiện tại** nên không có một stdout số thời gian duy nhất đúng cho mọi môi trường; đừng tự đặt số giả làm kết quả chạy.

### Giải thích thiết kế và giới hạn

- Cùng mảng `DATA`, cùng phép `filter`, `map` và `sum`; chỉ thay đổi `parallel()`.
- Kết quả kỳ vọng `6_666_700_000` được tính bằng **công thức dãy số** độc lập với pipeline; cả hai cách phải khớp.
- `LongStream` giảm boxing, tổng `long` tránh tràn `int` trong trường hợp này.
- `sink` là biến `volatile` để kết quả được sử dụng và khó bị tối ưu xóa công việc; điều đó **không thay thế các biện pháp blackhole/kiểm soát JIT của JMH**.
- `sample` dùng `System.nanoTime()` thu 40 lần và xác định percentile bằng *nearest-rank*; throughput tính từ số lần hoàn tất trong thời gian wall-clock của cả batch.
- `REPETITIONS = 40` là số mẫu nhỏ: p95 dễ nhiễu. Nếu cần p99, hãy thu đủ mẫu và dùng công cụ benchmark chuyên dụng; không suy diễn p99 đáng tin từ vài chục lời gọi.
- Hai lượt đo chạy nối tiếp, dễ chịu ảnh hưởng bởi JIT/GC/cache/thermal. Mã này **chỉ giúp hiểu công thức và kiểm tra correctness**, không dùng làm căn cứ khẳng định parallel nhanh hơn.
- `Collectors.toList()` trên nguồn ordered giữ encounter order, dù pipeline sử dụng `parallel()`. Đừng suy ra hành động `forEach` cũng giữ thứ tự.

### Vì sao mã không in “parallel speedup = 3.2x” cố định?

Vì speedup là **kết quả đo**, không phải đặc tính API. Với mảng 200.000 phần tử và filter/map rẻ, parallel có thể chậm hơn; máy nhiều core, CPU đang rảnh hoặc tải khác có thể cho kết quả khác. Báo cáo khoa học phải lấy số từ lần chạy trong môi trường mục tiêu, không từ một ví dụ tùy ý.

## 6. Benchmark chuẩn bằng OpenJDK JMH

**JMH (Java Microbenchmark Harness)** là dự án OpenJDK để đo hiệu năng JVM ổn định hơn một vòng `nanoTime()` tự viết. JMH hỗ trợ warm-up, measurement iterations, nhiều JVM forks, các mode throughput/average/sample time và báo cáo phân phối. Nó không thay thế load test toàn hệ thống, nhưng phù hợp để so sánh hai implementation tính toán trong JVM.

### 6.1. Mẫu benchmark JMH

Đây là **mã cho một dự án JMH**, không phải chương trình chỉ có thể chạy bằng `javac` thuần: cần dependency `org.openjdk.jmh` và annotation processing theo hướng dẫn chính thức. Tạo một dự án từ archetype JMH của OpenJDK rồi đặt mã vào source benchmark của dự án:

~~~java
import java.util.Arrays;
import java.util.concurrent.TimeUnit;
import java.util.stream.LongStream;
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
@Fork(3)
@Warmup(iterations = 5)
@Measurement(iterations = 5)
@Threads(1)
@BenchmarkMode({Mode.Throughput, Mode.SampleTime})
@OutputTimeUnit(TimeUnit.MILLISECONDS)
public class ParallelStreamBenchmark {
    @Param({"1000", "100000", "1000000"})
    public int size;

    private long[] data;

    @Setup(Level.Trial)
    public void prepare() {
        data = LongStream.range(0, size).toArray();
    }

    @Benchmark
    public long sequential() {
        return Arrays.stream(data)
                .filter(x -> x % 3L == 0L)
                .map(x -> x + 1L)
                .sum();
    }

    @Benchmark
    public long parallel() {
        return Arrays.stream(data)
                .parallel()
                .filter(x -> x % 3L == 0L)
                .map(x -> x + 1L)
                .sum();
    }
}
~~~

JMH đặt dữ liệu trong `@Setup(Level.Trial)` để benchmark **không vô tình đo bước tạo mảng**. `@Param` thử nhiều kích thước nhằm tìm điểm hòa vốn. `@Threads(1)` đo trường hợp một caller JMH; parallel pipeline vẫn có thể sử dụng các worker bên trong. Để kiểm tra tải nhiều caller, phải có một bộ thử riêng với thread/concurrency phù hợp, đồng thời phân biệt các mode kết quả.

Trong kết quả JMH, **`Mode.Throughput`** và **`Mode.SampleTime`** đo hai ý nghĩa khác nhau. Với `@OutputTimeUnit(TimeUnit.MILLISECONDS)`, throughput được biểu diễn theo đơn vị hoạt động mỗi mili giây; đổi đơn vị khi so sánh sang calls/s nếu cần. `SampleTime` cung cấp phân phối và các percentile thời gian mẫu. Không trộn một cột throughput với thời gian latency rồi so lớn/nhỏ trực tiếp.

Có thể tạo dự án từ [hướng dẫn JMH chính thức](https://github.com/openjdk/jmh), sau đó dùng quy trình Maven được cấu hình bởi archetype:

~~~bash
mvn -DskipTests package
java -jar target/benchmarks.jar ParallelStreamBenchmark -f 3 -wi 5 -i 5
~~~

Lệnh trên **áp dụng trong dự án JMH đã cấu hình đúng**; không phải lệnh xây dựng Java thuần với duy nhất tệp `ParallelStreamBenchmark.java`. Các cờ đại diện forks/warm-up/measurement; tùy dự án và phiên bản JMH hiện hành có thể cần điều chỉnh để chọn đúng benchmark. Không ghim một phiên bản JMH cụ thể trong bài khi không cần thiết.

### 6.2. Đọc kết quả JMH có trách nhiệm

- Với mode throughput, **số lớn hơn** là tốt hơn khi cùng đơn vị và cùng workload.
- Với latency/average time, **số nhỏ hơn** thường tốt hơn, nhưng xét cả mức p95/p99 và chi phí tài nguyên.
- So sánh **nhiều forks/iterations**, sai số và độ phân tán, không tuyên bố chiến thắng dựa trên một lần đo.
- Kiểm tra phép benchmark có thật sự tính cùng kết quả; tránh tối ưu không mong muốn hoặc phép tính bị lược bỏ.
- Tách so sánh **size nhỏ/vừa/lớn** thay vì chỉ thử một kích thước thuận lợi cho parallel.
- Nếu benchmark cùng máy đang có nhiều tiến trình nền, CPU quota nhỏ hoặc throttling, báo cáo hạn chế này.

## 7. Throughput và latency trong ứng dụng nhiều request

Kết quả JMH một caller không phản ánh đầy đủ production. Ví dụ một request xử lý 1 triệu phần tử:

~~~text
Sequential: một request thường chiếm gần một CPU worker.
Parallel: một request có thể sử dụng nhiều CPU worker cùng lúc.
~~~

Nếu có 30 request đồng thời, phiên bản parallel có thể tăng cạnh tranh với request khác hoặc tác vụ khác dùng `ForkJoinPool.commonPool()` (đây là hành vi thường gặp của triển khai JDK, **không phải cam kết cố định về thread/pool cho mọi ngữ cảnh**). Latency một request khi máy rảnh có thể giảm, trong khi p95 và throughput toàn server dưới tải lại xấu đi.

Một load test hữu ích cần có:

- **Mức đồng thời / arrival rate**: ví dụ thử từ thấp đến cao theo tải thật.
- **Completed RPS**, không chỉ số request phát đi.
- **p50/p95/p99 end-to-end latency** và timeout/error rate.
- **CPU utilization, core quota, heap, allocation, GC pauses, thread pool** và mức độ chờ.
- **Độ đúng của kết quả** ở mỗi mức tải; phát hiện timeout, mất cập nhật, thiếu phần tử.
- **Ngưỡng SLO**, ví dụ p95 dưới yêu cầu ở RPS mục tiêu, và giới hạn sử dụng CPU.

Nếu dùng workload có DB hay I/O, nhớ rằng thời gian chờ không giảm tự động nhờ parallel Stream; tăng số tác vụ blocking đồng thời còn có thể làm cạn connection pool hoặc thread worker. Đối với fan-out I/O, cân nhắc API async hoặc executor có giới hạn, cùng kiểm soát backpressure và timeout.

## 8. Các lỗi benchmark rất thường gặp

### 8.1. Đo một lần rồi kết luận

~~~java
long begin = System.nanoTime();
input.parallelStream().map(...).count();
System.out.println(System.nanoTime() - begin);
~~~

Đây là **mã minh họa, không độc lập**; việc gọi `count()` trong một số pipeline còn có thể được Stream tối ưu bằng thông tin kích thước nguồn mà không duyệt qua mọi mapper. Vậy nên không dùng `count()` để đo “chi phí map” mà mặc nhiên tin map đã chạy. Chọn terminal operation buộc thực hiện công việc mong muốn và xác nhận kết quả đúng.

### 8.2. Quên warm-up hoặc chạy hai bản trong điều kiện khác nhau

Lần đầu có thể gồm class loading và JIT warm-up. Nếu luôn đo parallel sau sequential, cache/JIT/GC có thể thiên lệch. Dùng JMH, nhiều forks và các kế hoạch đo cân bằng; ghi rõ điều kiện đầu vào và tài nguyên.

### 8.3. “Tối ưu” bằng cách bỏ tính đúng

Bỏ `forEachOrdered`, bỏ `sorted` hay đổi `findFirst` thành `findAny` có thể nhanh hơn nhưng **đang đo bài toán khác**. Muốn thay đổi hợp đồng phải có quyết định nghiệp vụ rõ ràng và test mới, không tự coi là tối ưu tương đương.

### 8.4. Dùng `ArrayList` hoặc biến cộng chung trong `forEach`

~~~java
// SAI — mutable state chung, không atomic:
long[] total = {0L};
LongStream.range(0, 1_000_000).parallel()
    .forEach(x -> total[0] += x);
~~~

Chạy vài lần có thể cho đáp án đúng tình cờ, nhưng `total[0] += x` không nguyên tử. Dùng `sum()` hoặc phép reduction có identity/associativity đúng. Đừng chỉ thay bằng synchronized và mặc định có speedup: đồng bộ có thể triệt tiêu lợi ích parallel.

### 8.5. So kết quả số thực bằng `==` vô điều kiện

Chạy parallel có thể đổi thứ tự cộng `double` và khác số bit cuối, dù mọi phần tử đều được xử lý. Chọn tiêu chí so sánh dựa trên yêu cầu độ chính xác thực tế, kiểm tra cả NaN, Infinity và các trường hợp mất mát do rounding.

### 8.6. Nhầm throughput một caller với throughput server

Vòng benchmark một thread thực hiện 100 pipeline nối tiếp có thể cho `calls/s` cao, nhưng chưa đo khi nhiều request cùng dùng CPU chung. Đừng công bố kết quả như RPS toàn hệ thống. Thử load đồng thời, đo completed throughput và tail latency.

### 8.7. Không so CPU và tài nguyên

Parallel có thể giảm một chút p50 nhưng tiêu thụ nhiều CPU, tăng GC hoặc làm dịch vụ khác chậm. Chọn tối ưu theo **ngân sách tài nguyên và SLO**, không chỉ chỉ số nào đó của một benchmark đơn lẻ.

### 8.8. Thiếu thống kê và điều kiện tái lập

Báo cáo “parallel nhanh hơn 1,7 lần” mà không ghi JDK, core, input, số iteration, mức tải, p95, confidence/spread thì không đủ cơ sở triển khai. Cần giữ raw results và lặp lại trên máy tương tự production.

## 9. Mẫu báo cáo kết quả benchmark nên có

Báo cáo không cần phức tạp nhưng phải rõ ngữ cảnh. Ví dụ khung:

| Trường | Thông tin cần ghi |
| --- | --- |
| Bài toán và correctness | Pipeline, input, oracle/reference result và pass/fail |
| Môi trường | JDK/JVM, CPU cores/quota, RAM, GC, trạng thái tải |
| Dữ liệu | Số phần tử, phân bố, loại nguồn và chi phí mapper |
| Kiểu chạy | Sequential vs parallel, mức concurrency, thứ tự/ordering |
| Phương pháp | JMH mode, forks, warmup, measurement; hoặc load test |
| Latency | p50/p95/p99, đơn vị, kích thước mẫu, spread |
| Throughput | calls/s hay RPS, điều kiện số caller, completed requests |
| Tài nguyên | CPU, heap, allocation, GC và pool contention |
| Kết luận | Đạt correctness/SLO không, cải thiện có đủ lớn và ổn định không |

Khi thay đổi kích thước dữ liệu hoặc concurrency, ghi kết quả trên **nhiều hàng cho nhiều cấu hình**; đừng chỉ chọn cấu hình có số liệu đẹp nhất. Trong môi trường CI, benchmark cần được chạy trên máy ít nhiễu hoặc máy dành riêng; nếu không, cân nhắc xem đây là tín hiệu tham khảo hơn là điều kiện pass/fail cứng.

## 10. Checklist quyết định có dùng `parallelStream()`

1. **Kiểm tra đúng trước:** kết quả tham chiếu độc lập, stream rỗng, dữ liệu lớn, trùng, biên, chạy lặp, thứ tự và side effects.
2. **Kiểm tra hợp đồng Stream:** các lambda stateless/non-interfering, phép reduction associative và có identity đúng, collector hỗ trợ parallel theo hợp đồng.
3. **Giữ workload tương đương:** cùng dữ liệu, cùng thuật toán nghiệp vụ và cùng đầu ra.
4. **Đo latency:** p50/p95/p99 với số mẫu đủ lớn, không chỉ một lần `nanoTime()`.
5. **Đo throughput:** calls/s hoặc RPS đã hoàn tất, ghi số caller/concurrency và điều kiện tải.
6. **Đo tài nguyên:** CPU, memory bandwidth, allocation, GC, pool contention và blocking.
7. **Kiểm tra điểm hòa vốn:** thử n nhỏ/vừa/lớn; nguồn dễ chia và mapper CPU-bound thường có cơ hội hơn.
8. **Kiểm tra ứng dụng nhiều request:** tránh làm giảm throughput toàn server để đổi lấy một ít latency lúc nhàn rỗi.
9. **Dùng JMH cho microbenchmark, load test cho server:** hai công cụ trả lời hai loại câu hỏi khác nhau.
10. **Chỉ áp dụng khi vượt rào correctness và SLO:** không đổi thứ tự/semantics để lấy một con số đẹp.

**Ghi nhớ:** Không có quy tắc “Stream song song luôn nhanh hơn”. Quyết định đúng là đo **độ đúng**, **latency** và **throughput** dưới workload/tải phù hợp, đồng thời nhìn chi phí CPU/GC và khả năng tái lập. Khi dữ liệu ít hoặc phép toán rẻ, `stream()` có thể tốt hơn. Khi nguồn chia thuận lợi, công việc đủ nặng, phép kết hợp đúng và máy còn tài nguyên, `parallelStream()` có thể giúp — nhưng chỉ số đo thực tế mới xác nhận điều đó.

## Tài liệu chuẩn đang áp dụng

- [Oracle Java SE 26 — java.util.stream: parallelism, associativity, stateful operations, ordering](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/package-summary.html)
- [Oracle Java SE 26 — LongStream: parallel, sum, reduce, limit và hành vi terminal operations](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/LongStream.html)
- [Oracle Java SE 26 — Stream: non-interference, reduce, collectors](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Stream.html)
- [OpenJDK JMH — tài liệu chính thức và Maven archetype](https://github.com/openjdk/jmh)
- [OpenJDK JMH sample — Benchmark modes (Throughput, AverageTime, SampleTime)](https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_02_BenchmarkModes.java)

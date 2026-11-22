# Tính toán chia để trị và điều chỉnh ngưỡng Fork/Join trong Java

**Chủ đề cha:** Thực hành tổng hợp  
**Bài học:** Tính toán chia để trị và điều chỉnh ngưỡng Fork/Join  
**Môi trường:** Java 17+; các API `java.util.concurrent.ForkJoinPool`, `ForkJoinTask`, `RecursiveTask` vẫn được hỗ trợ trong Java hiện đại.

Khi một phép tính CPU-bound có thể chia thành nhiều phần **độc lập**, Fork/Join cho phép phân chia dữ liệu thành các công việc nhỏ, xử lý chúng trên một nhóm worker, rồi kết hợp kết quả. Điểm cần thực hành không chỉ là viết `fork()`/`join()`, mà là chọn **ngưỡng dừng chia (threshold)** hợp lý: chia quá ít làm thiếu parallelism; chia quá nhiều khiến chi phí tạo task, xếp lịch, work stealing và kết hợp kết quả vượt lợi ích.

Bài này xây dựng một phép tính checksum trên mảng `long[]` bằng thuật toán chia để trị, kiểm thử sự tương đương với phiên bản tuần tự, chạy nhiều giá trị threshold, diễn giải log/timing và đưa ra cách điều chỉnh phù hợp với tải thật. Nội dung tập trung vào cơ chế còn dùng được trong Java ngày nay.

## 1. Fork/Join phù hợp với bài toán nào?

Một bài toán có dạng **divide → compute → combine** thường thích hợp khi:

- Mỗi đoạn dữ liệu có thể xử lý độc lập, chẳng hạn tính tổng, đếm, tìm giá trị lớn nhất, biến đổi ảnh theo vùng, phân tích mảng hoặc xử lý cây.
- Kết quả từ hai nhánh có phép kết hợp đúng và rõ ràng, ví dụ `sumLeft + sumRight` hay `Math.max(left, right)`.
- Công việc trên mỗi phần đủ nặng so với chi phí điều phối task.
- Có nhiều lõi CPU thực sự có thể chạy đồng thời và bộ nhớ/cache đáp ứng được.
- Task không phụ thuộc lẫn nhau theo chu trình và không bị chặn lâu bởi I/O.

Không phải mọi vòng lặp đều nên được parallelize. Vòng lặp đơn giản chỉ cộng vài phần tử có thể chạy tuần tự nhanh hơn. Nếu việc cần làm là **đợi database/network/file**, Fork/Join tính toán CPU không phải lựa chọn đầu tiên; dùng phương án bất đồng bộ, bounded executor hoặc virtual threads tùy kiến trúc và yêu cầu. `ForkJoinPool.ManagedBlocker` tồn tại cho trường hợp blocking có chủ đích trong Fork/Join, nhưng không biến tác vụ I/O thành tính toán hiệu quả trên nhiều lõi.

## 2. Mô hình hoạt động của `ForkJoinPool`

`ForkJoinPool` triển khai cơ chế **work stealing**: các worker có deque task; worker xử lý công việc của mình, còn worker rảnh có thể lấy công việc thích hợp từ worker khác. Điều này giúp cân bằng tải khi những nhánh chia để trị có thời gian chạy không đều.

Các lớp/phương thức chính:

| API | Vai trò |
|---|---|
| `RecursiveTask<V>` | Task có kết quả kiểu `V`; override `compute()` để xử lý. |
| `RecursiveAction` | Task không cần kết quả trả về; cũng override `compute()`. |
| `ForkJoinPool` | Pool thực thi các `ForkJoinTask`, hỗ trợ work stealing và các phương thức `invoke`/`submit`. |
| `ForkJoinPool.invoke(task)` | Gửi task gốc, chờ hoàn tất và trả kết quả; lỗi từ task có thể được truyền đến caller. |
| `fork()` | Đánh dấu một task để có thể thực hiện bất đồng bộ trong pool; không có nghĩa tạo một Java thread mới cho mỗi task. |
| `compute()` | Thực thi logic của task ngay trong thread hiện tại theo lời gọi trực tiếp. |
| `join()` | Chờ kết quả của task forked và trả giá trị; có thể tham gia thực thi công việc để tiến tới hoàn tất. |
| `getParallelism()` | Mức parallelism mục tiêu mà pool cấu hình; không phải chứng cứ mọi worker luôn bận. |
| `shutdown()`, `awaitTermination(...)` | Quản lý vòng đời pool tự tạo và đợi worker kết thúc. |

Trong chương trình Java 17, khi tự tạo `ForkJoinPool` nên dọn bằng `shutdown()`/`awaitTermination(...)`; không dùng `try (pool)` trong mã biên dịch với `--release 17` vì `ExecutorService.close()` được đưa vào từ Java 19. `ForkJoinPool.commonPool()` là pool dùng chung do JVM quản lý; **không shutdown common pool** từ một thư viện hoặc một tác vụ riêng.

### Cách chia và kết hợp một đoạn dữ liệu

```text
Task [0, n)
     |
     +-- size <= threshold ? -- yes --> xử lý tuần tự đoạn hiện tại
     |
     no
     |
     +-- fork [0, mid) ------------+
     |                              |
     +-- compute [mid, n)           |
     |                              |
     +-- join kết quả nhánh trái <--+
     |
     +-- combine(left, right)
```

Mẫu **fork một nhánh, tự compute nhánh còn lại, rồi join** giúp thread hiện tại làm việc hữu ích và để các worker khác có cơ hội steal nhánh đã fork. Tránh fork cả hai nhánh ngay rồi chờ một nhánh, vì dễ tăng overhead không cần thiết. Khi đã `fork` task, phải bảo đảm đường chờ/kết hợp phù hợp, không bỏ quên kết quả.

**Chỉ chia đoạn có kích thước lớn hơn threshold**. Với khoảng nửa mở `[from, to)`, midpoint an toàn là `from + (to - from) / 2`. Hai con `[from, mid)` và `[mid, to)` không trùng, không bỏ sót phần tử. Điều kiện `threshold > 0` là cần thiết để recursion chắc chắn chấm dứt.

## 3. Ý nghĩa của ngưỡng threshold

Giả sử dữ liệu có `n` phần tử và mỗi task lá xử lý tối đa `T` phần tử:

- **`T` rất nhỏ:** nhiều task lá, nhiều đối tượng task và thao tác `fork/join`; worker có nhiều việc để chia nhưng chi phí điều phối có thể lớn.
- **`T` vừa đủ:** số task lớn hơn mức parallelism một chút để chia việc, nhưng mỗi task đủ nhiều CPU work để bù overhead.
- **`T` rất lớn:** ít task, có thể có ít việc hơn số worker; một vài worker chạy hết công việc, những worker khác không có gì để steal.
- **`T >= n`:** task gốc xử lý cả đoạn ngay trong `compute()`, không gọi `fork()`; nếu vẫn đi qua `pool.invoke()`, vẫn tồn tại overhead submit một task gốc.

Độ phức tạp tính toán tổng vẫn thường là **O(n)** đối với phép tính mỗi phần tử chi phí O(1), còn chi phí điều phối tăng theo số nhánh. Độ sâu cây cân bằng khoảng **O(log(n/T))**. Với mảng có `n = 262144` (2^18), chia đúng đôi và threshold là các lũy thừa của hai:

| Threshold T | Số task lá | Tổng số `RecursiveTask` trong cây đầy đủ | Ý nghĩa |
|---:|---:|---:|---|
| 256 | 1024 | 2047 | Độ mịn cao, nhiều việc quản lý |
| 1024 | 256 | 511 | Nhiều nhánh có thể được steal |
| 4096 | 64 | 127 | Ít overhead hơn |
| 16384 | 16 | 31 | Số nhánh nhỏ, có thể đủ với vài worker |
| 262144 | 1 | 1 | Không chia; chỉ một task |

Đây là **con số chính xác của cấu trúc cây trong ví dụ** nhờ kích thước mảng và threshold đều là lũy thừa hai. Với `n` và `T` tùy ý, cây có thể không hoàn toàn cân bằng theo số phần tử; đừng hardcode bảng này thành công thức chung cho mọi workload.

Không có ngưỡng “chuẩn” được Java cam kết. Một task xử lý 1024 phép cộng đơn giản khác hẳn một task giải mã 1024 bản ghi nặng CPU. **Threshold là quyết định hiệu năng của ứng dụng**, phải đo theo đơn vị công việc thật và kích thước dữ liệu điển hình.

## 4. Ví dụ Java 17+ hoàn chỉnh: tính checksum bằng chia để trị

### Mục tiêu của chương trình

Ta sinh **262144 giá trị `long` với seed xác định**, áp dụng một hàm tính toán thuần `work(long)` cho mỗi phần tử, rồi cộng tất cả kết quả vào checksum `long`. Hàm `work` cố ý có nhiều phép bitwise và phép nhân để bài toán có CPU work đáng kể.

Cùng một mảng được tính bằng:

1. `sequential(long[])` để tạo kết quả tham chiếu.
2. `RecursiveTask<Long>` trên một `ForkJoinPool` có parallelism cố định trong một lần chạy.
3. Năm threshold: `256`, `1024`, `4096`, `16384`, `262144`.

Mỗi threshold chạy **hai lượt warmup** và **năm lượt đo**, lấy median của năm thời gian `System.nanoTime()`. Mỗi lần tính đều phải ra **đúng checksum tham chiếu**, nếu lệch thì chương trình ném `AssertionError`. Khoảng thời gian đo chỉ là **thí nghiệm gợi ý**, chưa đủ điều kiện để gọi là benchmark khoa học; phần 8 sẽ chỉ cách đo nghiêm túc.

Ta dùng `long` và phép cộng `long` thay vì `double` vì cộng `long` có quy tắc overflow xác định modulo 2^64; kết quả tổng độc lập với thứ tự gộp nhánh theo ngữ nghĩa số nguyên Java. Với `double`, phép cộng **không có tính kết hợp chính xác** do làm tròn; việc gộp theo thứ tự khác nhau có thể tạo kết quả khác dù không có race.

Tạo tệp UTF-8 **`ForkJoinThresholdDemo.java`**:

```java
import java.util.Arrays;
import java.util.Locale;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveTask;
import java.util.concurrent.TimeUnit;

public final class ForkJoinThresholdDemo {
    private static final int SIZE = 1 << 18;
    private static final int[] THRESHOLDS = {256, 1024, 4096, 16384, SIZE};
    private static volatile long resultSink;

    private static long work(long value) {
        long x = value;
        for (int i = 0; i < 12; i++) {
            x ^= x >>> 30;
            x *= 0xbf58476d1ce4e5b9L;
            x ^= x >>> 27;
            x *= 0x94d049bb133111ebL;
            x ^= x >>> 31;
        }
        return x;
    }

    private static long sequential(long[] values) {
        long sum = 0;
        for (long value : values) {
            sum += work(value);
        }
        return sum;
    }

    private static final class SumTask extends RecursiveTask<Long> {
        private final long[] values;
        private final int from;
        private final int to;
        private final int threshold;

        private SumTask(long[] values, int from, int to, int threshold) {
            this.values = values;
            this.from = from;
            this.to = to;
            this.threshold = threshold;
        }

        @Override
        protected Long compute() {
            int size = to - from;
            if (size <= threshold) {
                long sum = 0;
                for (int i = from; i < to; i++) {
                    sum += work(values[i]);
                }
                return sum;
            }

            int mid = from + size / 2;
            SumTask left = new SumTask(values, from, mid, threshold);
            SumTask right = new SumTask(values, mid, to, threshold);
            left.fork();
            long rightResult = right.compute();
            return left.join() + rightResult;
        }
    }

    private static long parallel(ForkJoinPool pool, long[] values, int threshold) {
        if (threshold <= 0) throw new IllegalArgumentException("threshold");
        return pool.invoke(new SumTask(values, 0, values.length, threshold));
    }

    private static double medianMillis(
            ForkJoinPool pool, long[] values, int threshold, long expected) {
        for (int i = 0; i < 2; i++) {
            if (parallel(pool, values, threshold) != expected) {
                throw new AssertionError("Warmup mismatch for " + threshold);
            }
        }

        long[] nanos = new long[5];
        for (int i = 0; i < nanos.length; i++) {
            long start = System.nanoTime();
            long actual = parallel(pool, values, threshold);
            nanos[i] = System.nanoTime() - start;
            if (actual != expected) {
                throw new AssertionError("Result mismatch for " + threshold);
            }
            resultSink = actual;
        }
        Arrays.sort(nanos);
        return nanos[nanos.length / 2] / 1_000_000.0;
    }

    public static void main(String[] args) throws InterruptedException {
        long[] values = new long[SIZE];
        long state = 0x1234abcd5678ef90L;
        for (int i = 0; i < values.length; i++) {
            state ^= state >>> 12;
            state ^= state << 25;
            state ^= state >>> 27;
            values[i] = state * 0x2545f4914f6cdd1dL;
        }

        long expected = sequential(values);
        int workers = Math.max(1,
                Math.min(4, Runtime.getRuntime().availableProcessors()));
        System.out.println("LENGTH=" + values.length);
        System.out.println("EXPECTED_CHECKSUM=" + expected);
        System.out.println("POOL_PARALLELISM=" + workers);

        ForkJoinPool pool = new ForkJoinPool(workers);
        try {
            for (int threshold : THRESHOLDS) {
                double ms = medianMillis(pool, values, threshold, expected);
                System.out.printf(Locale.ROOT,
                        "THRESHOLD=%d MEDIAN_MS=%.3f MATCH=true%n",
                        threshold, ms);
            }
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(30, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Pool did not terminate");
            }
        }
        System.out.println("ALL_MATCH=true");
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp với **JDK 17 trở lên**:

```bash
javac --release 17 -encoding UTF-8 ForkJoinThresholdDemo.java
java ForkJoinThresholdDemo
```

Các phần stdout **cố định** theo dữ liệu trong ví dụ:

```text
LENGTH=262144
EXPECTED_CHECKSUM=-4389990420511303985
POOL_PARALLELISM=<phụ thuộc số CPU mà JVM nhìn thấy, tối đa 4>
THRESHOLD=256 MEDIAN_MS=<biến đổi> MATCH=true
THRESHOLD=1024 MEDIAN_MS=<biến đổi> MATCH=true
THRESHOLD=4096 MEDIAN_MS=<biến đổi> MATCH=true
THRESHOLD=16384 MEDIAN_MS=<biến đổi> MATCH=true
THRESHOLD=262144 MEDIAN_MS=<biến đổi> MATCH=true
ALL_MATCH=true
```

Các phần trong dấu `<...>` là **mô tả chỗ có thể khác nhau**, không phải chuỗi chương trình in ra. Chương trình thực sự in số worker và số mili-giây đo được (định dạng ba chữ số thập phân theo `Locale.ROOT`). Trên một môi trường thử có 4 worker, một lượt chạy từng ghi nhận **xấp xỉ** 0,824 ms (256), 0,757 ms (1024), 0,742 ms (4096), 0,763 ms (16384), 2,938 ms (262144); đây **không phải tốc độ bảo đảm** và không có giá trị dùng để chọn threshold trên máy khác.

**Diễn giải kết quả:**

- `EXPECTED_CHECKSUM` âm vì phép toán `long` có thể overflow theo quy tắc xác định của Java. Giá trị âm **không phải lỗi**; nó là checksum tham chiếu tính ra từ dữ liệu seed cố định.
- Mọi dòng `MATCH=true` chứng minh phiên bản song song cho đúng giá trị so với tính tuần tự trên **bộ dữ liệu này**; không chứng minh chương trình đã đạt tốc độ tối ưu.
- `THRESHOLD=262144` không chia task, nhưng mã vẫn đi qua `pool.invoke`; đó là **baseline một task**, chưa phải phép đo thuần của vòng lặp `sequential`.
- `POOL_PARALLELISM` là mục tiêu số worker của pool ta tạo, được giới hạn tối đa 4 để thí nghiệm không tự chiếm quá nhiều CPU. Nếu JVM chỉ nhìn thấy 1 CPU, parallelism là 1 và **không thể kỳ vọng tốc độ nhanh nhờ chạy đồng thời trên nhiều lõi**.
- Task con chỉ **đọc** mảng chung; mỗi task tính `sum` cục bộ rồi trả về; caller kết hợp qua `join()`. Không có chia sẻ bộ tích lũy có thể ghi đồng thời, nên không cần `synchronized` trong vòng lặp.
- `resultSink` được cập nhật bên ngoài thời gian tính sau mỗi lượt để giữ kết quả có đường sử dụng quan sát được. Đây không phải công cụ chống tất cả tối ưu benchmark; phép so checksum mới là điều kiện kiểm tra chính.

## 5. Tại sao `fork()`/`compute()`/`join()` đúng chỗ?

Đoạn lõi trong `SumTask.compute()`:

```java
SumTask left = new SumTask(values, from, mid, threshold);
SumTask right = new SumTask(values, mid, to, threshold);
left.fork();                      // Có thể chạy ở worker khác
long rightResult = right.compute(); // Thread hiện tại tiếp tục làm việc
return left.join() + rightResult; // Hợp nhất sau khi left hoàn tất
```

Đây là **trích đoạn nằm trong `compute()`**, không phải chương trình hoàn chỉnh để biên dịch riêng.

Điểm mấu chốt là **không** gọi `left.join()` ngay sau `left.fork()` rồi mới xử lý `right`. Nếu chờ quá sớm, thread hiện tại có thể không tự xử lý công việc sẵn có, giảm khả năng phân phối. Thứ tự fork một nhánh, compute nhánh kia, rồi join thường thích hợp cho bài toán chia để trị có DAG phụ thuộc rõ ràng.

Với các nhánh cân bằng nhưng khối lượng không đều, work stealing giúp worker rảnh tìm task trong pool; nó **không cam kết** phân phối hoàn hảo hay tất cả core hoạt động liên tục. Nếu một nhánh phụ thuộc kết quả của nhánh kia, không thể mặc định chạy hai nhánh độc lập; phải thiết kế đồ thị phụ thuộc đúng trước.

Ngoại lệ runtime từ một nhánh có thể được phản ánh khi `join()`/`invoke()` hoàn tất bất thường. Đừng nuốt exception rồi xuất kết quả sai; cần chiến lược trả lỗi/cancel tương ứng ở tầng gọi. `cancel(true)` của `ForkJoinTask` cũng không bảo đảm interrupt một task đang chạy như cách nhiều người kỳ vọng với thread thông thường; task dài cần có **cơ chế hủy hợp tác** nếu ứng dụng yêu cầu.

## 6. Quy tắc đúng đắn khi chia và gộp kết quả

**Ranh giới khoảng:** Dùng `[from, to)` để phần tử ở index `to` không được xử lý. Hai task con bao phủ chính xác đoạn cha, không chồng lấn, không bỏ sót. Với `size <= threshold` luôn quay về xử lý tuần tự, và `mid = from + size / 2` khiến đoạn con nhỏ hơn khi `size > threshold > 0`.

**Dữ liệu bất biến trong lúc chạy:** Các task chỉ đọc `values[]`. Nếu thread khác sửa mảng khi task đang tính, chương trình có thể có data race, kết quả không còn ổn định. Để tính song song đúng, hãy đảm bảo nguồn dữ liệu không bị ghi cạnh tranh, hoặc dùng cấu trúc/đồng bộ phù hợp.

**Hàm lá phải thuần hoặc có phân vùng sở hữu rõ ràng:** `work(long)` ở ví dụ không đọc/ghi shared mutable state. Với bài toán ghi ra mảng đích, mỗi task phải sở hữu một đoạn đích **không chồng lấn**; khi có chia sẻ trạng thái cần đồng bộ thích hợp, tránh tranh chấp khóa trong hot path.

**Phép kết hợp phải phù hợp:** Tổng số nguyên `long` có phép cộng xác định theo mô-đun 2^64 nên có thể kết hợp các nhánh mà không đổi bit kết quả. Với số thực, `(a+b)+c` có thể khác `a+(b+c)` vì rounding; với chuỗi cần giữ thứ tự; với các phép có tác dụng phụ thì việc đổi thứ tự có thể sai. Không lấy “chạy song song ra số hơi khác” làm hợp lệ nếu hợp đồng nghiệp vụ yêu cầu bit-exact.

**Xử lý trường hợp biên:** Mảng rỗng có tổng 0 trong cài đặt này; threshold không dương bị từ chối bằng `IllegalArgumentException`; mảng quá lớn cần kiểm tra ràng buộc kích thước/index/bộ nhớ ở tầng gọi. Chia theo hai nửa giúp độ sâu stack logarithmic trong ví dụ; đừng dùng chia cực lệch tạo recursion sâu không kiểm soát.

**Overflow:** Phép `long` trong `work` và checksum có thể wrap. Bài toán checksum này chủ ý tận dụng tính chất bit-level đó; nếu đang tính **tổng tiền, số lượng quan trọng hoặc dữ liệu không cho phép overflow**, dùng kiểm tra như `Math.addExact` hoặc kiểu số phù hợp, không mặc nhiên chấp nhận wrap.

## 7. Chọn threshold từ bằng chứng thay vì đoán

Trước khi tune, phải xác định **mục tiêu**: tốc độ của một yêu cầu, throughput khi nhiều yêu cầu đồng thời, mức CPU trung bình, hoặc độ trễ đuôi. Một threshold tối ưu cho latency của một tác vụ đơn lẻ có thể làm hệ thống tổng thể tệ đi khi hàng chục request cùng tranh CPU.

Một quy trình có thể làm theo:

1. **Xây bản tuần tự đúng.** Kiểm tra kết quả với dữ liệu nhỏ/biên, mảng rỗng, một phần tử, kích thước không phải lũy thừa hai và dữ liệu lớn.
2. **Viết chia để trị đúng.** Xác nhận `[from, mid)` và `[mid, to)` phủ kín đoạn cha, không ghi cạnh tranh và phép gộp hợp lệ.
3. **Chọn nhóm threshold theo cấp số nhân.** Ví dụ `256 → 1024 → 4096 → 16384`, thêm `>= n` để so với một task. Những giá trị này chỉ là **các ứng viên thử**, không phải công thức chuẩn.
4. **Giữ số worker và dữ liệu ổn định** giữa các lần thử, theo dõi `Runtime.availableProcessors()` và giới hạn CPU trong container. Không tăng pool lên hàng trăm worker chỉ vì cây có hàng nghìn task.
5. **Warm up rồi đo nhiều lần.** Cần chú ý JIT compilation, garbage collection, frequency scaling, scheduler, nhiệt độ CPU và thứ tự chạy test. Đảo/luân phiên thứ tự threshold trong benchmark có kiểm soát để giảm thiên lệch thứ tự.
6. **Giữ kết quả sống và xác nhận tính đúng.** Kiểm tra checksum trong và sau phép đo; tránh benchmark bị JIT loại bỏ do kết quả không được sử dụng.
7. **Đánh giá cùng kết quả tuần tự thật.** Với workload quá nhỏ, cách nhanh nhất có thể là **không tạo ForkJoinTask**. Đo thêm thời gian vòng lặp tuần tự trực tiếp để biết overhead của một lần submit task.
8. **Chọn threshold dựa trên tổng thể.** Khi chênh lệch thời gian nằm trong nhiễu đo, chọn cấu hình đơn giản, ít overhead và dễ kiểm soát. Sau đó đo trên dữ liệu tải thực tế, không chỉ mảng demo.

### Heuristic để hiểu chi phí

Một cách mô tả định tính:

```text
Tổng thời gian ≈ công việc hữu ích / parallelism thực tế
              + chi phí tách task, fork/join, steal
              + chi phí truy cập bộ nhớ/cache và phối hợp
              + ảnh hưởng JIT/GC/scheduler
```

Đây chỉ là **mô hình giải thích**, không phải công thức dự báo chính xác: hiệu quả parallelism bị giới hạn bởi phần không thể song song, memory bandwidth và load balance. Điều chỉnh `T` thay đổi lượng overhead quản lý và độ mịn của việc phân phối tải; nó không thể vượt giới hạn CPU/memory của máy.

## 8. Đo hiệu năng nghiêm túc bằng JMH

Đo `System.nanoTime()` như demo đủ để **quan sát xu hướng khi học**, không đủ để công bố threshold tối ưu. Trong benchmark thực sự, nên dùng **JMH (Java Microbenchmark Harness)** của OpenJDK, một công cụ vẫn được duy trì, để quản lý warmup, đo, fork JVM và kiểm soát tối ưu hoá compiler.

Tổ chức benchmark:

- Dùng dữ liệu được tạo **ngoài vùng đo**, với seed/lượng dữ liệu và trạng thái bộ nhớ được kiểm soát.
- `@Param` cho threshold và kích thước dữ liệu, thử thêm số worker nếu có lý do; giữ các biến khác cố định.
- Trả checksum hoặc tiêu thụ nó đúng cách bằng `Blackhole`; không cho code bị loại bỏ vì kết quả không ai dùng.
- Dùng warmup, nhiều vòng measurement, nhiều fork; theo dõi GC allocations và biến thiên (percentile/độ lệch), không chỉ một median.
- So với `sequential` và một task `ForkJoinPool` không chia để xác định lợi ích song song và overhead điều phối.
- Chạy trong tải đại diện, lặp trên JDK/CPU/giới hạn container sẽ triển khai; không diễn giải kết quả của máy phát triển thành hợp đồng của Java.
- Nếu benchmark có nhiều request cùng lúc, đo **throughput và latency tổng hệ thống**; quá nhiều task song song cùng pool có thể làm độ trễ đuôi tăng.

Không cần thêm JMH dependency để **chạy chương trình Java độc lập** ở mục 4. JMH là công cụ riêng cho phép đo nghiêm túc; không tự gắn các annotation `@Benchmark` vào tệp chưa có thư viện rồi kỳ vọng `javac` chuẩn có thể biên dịch.

## 9. Shared pool, thread pool riêng và vòng đời

`ForkJoinPool.commonPool()` phù hợp cho nhiều tình huống dùng chung tài nguyên, nhưng chương trình thực hành sử dụng `new ForkJoinPool(workers)` để kiểm soát mục tiêu parallelism và tránh gây nhiễu bởi những task không liên quan trên common pool.

**Pool riêng** có chi phí tạo worker và quản lý vòng đời, nên trong ứng dụng thật thường tạo một pool có đời sống phù hợp, **tái sử dụng** giữa nhiều tác vụ thay vì tạo pool cho từng phép tính nhỏ. Không nên dùng pool riêng cho mỗi request; có thể làm số worker tăng quá mức dưới tải.

Trong Java 17+, mẫu `try/finally` với `shutdown()` và `awaitTermination(...)` vẫn hợp lệ. Với Java mới có `ExecutorService.close()`, vẫn cần xác định thời điểm đóng đúng nhưng bài này giữ source tương thích `--release 17`.

Không gọi `commonPool().shutdown()` để “dọn” khi thư viện dùng chung hoàn tất. Pool có thể được sử dụng bởi phần khác của ứng dụng. Khi dùng parallel streams hay các tác vụ bất đồng bộ có common pool, cân nhắc việc tranh tài nguyên với Fork/Join đang chạy.

### Blocking và cấu trúc task

- Task Fork/Join lý tưởng là **CPU-bound**, không chờ lock, network hoặc disk lâu.
- Nếu cần blocking thật, thiết kế lại luồng xử lý hoặc xem xét `ForkJoinPool.ManagedBlocker` trong trường hợp phù hợp; không mặc định pool luôn bù đủ worker khi bị chặn I/O ngoài tầm kiểm soát.
- Không giữ `synchronized` rồi `join()` theo cách tạo phụ thuộc vòng; ForkJoinTask yêu cầu đồ thị dependency **không có chu trình** để tránh deadlock.
- `join()` chờ task; không phải API giới hạn thời gian. Nếu nghiệp vụ cần timeout/cancellation, chọn luồng điều phối và hợp đồng hủy phù hợp ở tầng trên.

## 10. Những lỗi thường gặp khi thực hành

| Lỗi | Hệ quả và cách sửa |
|---|---|
| `threshold = 0` hoặc âm | Có thể làm chia đệ quy vô hạn ở một số cài đặt; validate `threshold > 0`. |
| `mid` sai, hai đoạn giao nhau | Phần tử được tính hai lần/không tính; dùng khoảng `[from, to)` và midpoint an toàn. |
| `fork` cả hai nhánh và `join` ngay từng nhánh | Overhead không cần thiết, worker hiện tại ít tự làm; fork một, compute một, join. |
| `join` trước khi compute nhánh còn lại | Làm giảm cơ hội song song thực tế. |
| Threshold quá nhỏ | Quá nhiều object/task, chi phí scheduling/GC lớn hơn lợi ích. |
| Threshold quá lớn | Thiếu task để phân phối giữa các worker. |
| Chia sẻ một biến `sum` mutable cho mọi task | Data race, kết quả không đúng; tổng cục bộ và combine. |
| Giả định `double` luôn ra bit-identical khi đổi cấu trúc gộp | Sai vì floating-point rounding; cần hợp đồng số học phù hợp. |
| Tự tạo pool cho mỗi phần tử/request | Nổ số worker và chi phí tạo pool; dùng pool có vòng đời đúng. |
| Dùng chung common pool rồi shutdown | Làm ảnh hưởng các thành phần khác; chỉ đóng pool do mình sở hữu. |
| Đo một lần `nanoTime()` rồi kết luận | Nhiễu JIT/GC/OS/lịch task; benchmark nhiều lượt/fork với JMH. |
| Chỉ đo thời gian mà không so kết quả | Có thể “nhanh” vì xử lý thiếu dữ liệu hoặc bị compiler tối ưu bỏ. |
| Bật parallelism cao hơn CPU available không có lý do | Có thể tăng context switching, contention, cache misses. |
| Giả định work stealing bảo đảm nhanh hơn | Nó hỗ trợ cân bằng tải nhưng không bảo đảm speedup cho task quá nhỏ/không đồng đều/giới hạn bandwidth. |

## 11. Kiểm thử bổ sung cho thuật toán của bạn

Ngoài chương trình chính, nên thêm các ca kiểm thử có kỳ vọng rõ ràng trong dự án:

| Ca | Kết quả cần kiểm |
|---|---|
| Mảng rỗng, threshold dương | Tổng bằng 0; kết thúc không fork vô hạn. |
| Mảng một phần tử | Trả đúng `work(value)`. |
| `n` lẻ, ví dụ 7, threshold 2 | Kết quả bằng tuần tự; không bỏ/trùng phần tử tại midpoint. |
| Threshold lớn hơn `n` | Một task leaf xử lý cả đoạn, vẫn trả checksum đúng. |
| Threshold bằng 0 hoặc âm | `IllegalArgumentException`. |
| Mảng có đủ `Long.MAX_VALUE`/`Long.MIN_VALUE` gây overflow | Kết quả theo hợp đồng `long`; không vô tình đổi sang tính `double`. |
| Nhiều lần chạy cùng input | Checksum phải giống nhau, bất kể thứ tự scheduling. |
| Parallelism 1 và nhiều worker | Vẫn đúng; hiệu năng có thể khác. |
| Task lá chủ động ném runtime exception | Caller nhìn thấy lỗi; không chấp nhận checksum giả. |
| Input bị chỉnh sửa cạnh tranh | Bài toán phải loại bỏ data race bằng thiết kế hoặc đồng bộ, không gắn kỳ vọng checksum. |

Nếu cần thử workload không cân bằng, cho mỗi phần tử khối lượng CPU khác nhau **một cách xác định**, rồi đối chiếu result với sequential. Mục tiêu là thấy sự phân phối task và khả năng steal có tác dụng; không dùng sleep để mô phỏng CPU-bound work.

## 12. Tổng kết kiến thức cần nhớ

- **Divide-and-conquer đúng** bắt đầu từ chia đoạn không trùng và phép gộp kết quả hợp lệ.
- **Fork/Join** thực thi nhiều task trên số worker có giới hạn qua cơ chế work stealing; task không đồng nghĩa với thread.
- **Threshold** cân bằng **số task đủ để chạy song song** với **chi phí điều phối đủ thấp**. Không có threshold mặc định tối ưu cho mọi bài toán.
- **Kết quả đúng** phải được kiểm tra độc lập với tốc độ; ví dụ dùng checksum `long` ổn định để phát hiện xử lý thiếu/trùng.
- **Kết quả đo** trong vòng lặp nhỏ chỉ là gợi ý; muốn chọn cấu hình có căn cứ phải benchmark bằng JMH/tải đại diện.
- **Vòng đời pool** và lựa chọn CPU-bound so với blocking phải được thiết kế đúng trong ứng dụng thực tế.

**Tài liệu hiện hành:** [ForkJoinPool — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ForkJoinPool.html), [ForkJoinTask — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ForkJoinTask.html), [RecursiveTask — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/RecursiveTask.html), [Oracle Java Concurrency](https://docs.oracle.com/en/java/javase/25/core/concurrency.html), [OpenJDK JMH](https://github.com/openjdk/jmh). Các API và nguyên tắc nêu trên vẫn được áp dụng; ví dụ biên dịch trực tiếp bằng Java 17 mà không cần API hoặc kỹ thuật legacy.
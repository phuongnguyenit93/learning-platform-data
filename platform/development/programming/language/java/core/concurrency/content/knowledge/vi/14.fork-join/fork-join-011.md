# Benchmark Fork/Join so với thực thi tuần tự trong Java

## 1. Câu hỏi cần kiểm chứng

Fork/Join giúp chia một công việc thành những phần nhỏ để nhiều worker xử lý đồng thời, rồi ghép kết quả. Tuy nhiên, **có thể chia được** không có nghĩa **chạy nhanh hơn**. Khi công việc ngắn, số lượng phần nhỏ quá lớn, memory bandwidth bị nghẽn hoặc máy không có đủ lõi CPU, chi phí tạo task, scheduling, work stealing và ghép kết quả có thể vượt phần thời gian tiết kiệm.

Một benchmark có ích phải trả lời những câu hỏi cụ thể:

1. Cùng một đầu vào và cùng một phép tính, phiên bản **tuần tự** và **Fork/Join** có kết quả giống nhau không?
2. Với kích thước dữ liệu và cấu hình máy đang xét, phiên bản nào hoàn thành nhanh hơn?
3. Kết quả thay đổi thế nào khi tăng kích thước dữ liệu, số worker hoặc ngưỡng chia nhỏ task?
4. Số đo có đủ tin cậy để đưa ra quyết định hay chỉ là nhiễu từ JIT, GC, khởi tạo pool và tải hệ thống?
5. Khi đưa vào ứng dụng thật, throughput, latency, CPU và memory có chuyển biến như microbenchmark dự báo không?

Bài này thuộc **Java Concurrency nói chung**, sử dụng API chuẩn của JDK, không phụ thuộc Spring.

## 2. Hai cách thực thi cùng một phép tính

Giả sử cần tính tổng kết quả của một hàm biến đổi cho từng phần tử mảng:

\[
S = \sum_{i=0}^{N-1} f(a_i)
\]

**Tuần tự:** một thread duyệt toàn bộ mảng, gọi cùng hàm \(f\) rồi cộng kết quả.

**Fork/Join:** mỗi tác vụ quản lý đoạn chỉ số nửa mở \([lo, hi)\). Khi đoạn nhỏ hơn hoặc bằng \`threshold\`, tính tuần tự trong đoạn đó. Khi lớn hơn, chia làm hai, \`fork()\` nhánh trái, tính nhánh phải trên worker hiện tại, sau đó \`join()\` nhánh trái và cộng hai tổng.

Sơ đồ:

\`\`\`text
sum[0, N)
    |
    +-- sum[0, N/2)  -- fork
    |      |
    |      +-- các đoạn nhỏ tính tuần tự
    |
    +-- sum[N/2, N)  -- compute trên worker hiện tại
           |
           +-- các đoạn nhỏ tính tuần tự
    |
    +-- join và cộng hai kết quả
\`\`\`

Hai cách phải thực hiện **chính xác cùng một workload**. Nếu nhánh tuần tự dùng thuật toán khác, nhánh Fork/Join bỏ qua một phần dữ liệu hoặc một nhánh được hưởng bộ nhớ đệm đã nóng hơn, phép so sánh sẽ không còn công bằng.

Với tổng số nguyên \`long\`, Java thực hiện phép cộng modulo \(2^{64}\) khi tràn; phép cộng theo bit pattern vẫn có tính kết hợp. Bởi vậy, thay đổi thứ tự cộng theo các nhánh không làm thay đổi bit pattern của kết quả. Với \`double\` hoặc \`float\`, thứ tự cộng **có thể thay đổi kết quả** do quy tắc làm tròn của số dấu phẩy động. Benchmark số thực cần so sánh theo sai số phù hợp, không tự khẳng định kết quả luôn khớp bit.

## 3. Vì sao ForkJoinPool có thể nhanh hơn — và khi nào không?

\`ForkJoinPool\` dùng nhiều worker cùng xử lý những phần việc có thể tách ra. Thuật toán **work stealing** cho phép worker rảnh lấy công việc từ hàng đợi của worker khác, giúp phân phối các phần việc không đều. \`RecursiveTask<V>\` biểu diễn tác vụ có kết quả và \`RecursiveAction\` biểu diễn tác vụ không trả về giá trị.

\`\`\`java
// Fragment mô tả thao tác cốt lõi của RecursiveTask<Long>:
if (hi - lo <= threshold) {
    return computeDirectly(lo, hi);
}
int mid = lo + (hi - lo) / 2;
SumTask left = new SumTask(data, lo, mid, threshold);
SumTask right = new SumTask(data, mid, hi, threshold);
left.fork();
long rightValue = right.compute();
return left.join() + rightValue;
\`\`\`

Đây là fragment: lớp \`SumTask\` và \`computeDirectly\` được định nghĩa đầy đủ trong chương trình chạy ở phần tiếp theo.

Các loại chi phí cần tính:

| Nguồn chi phí | Thực thi tuần tự | Fork/Join |
| --- | --- | --- |
| Tính toán thật | Có | Có |
| Tạo đối tượng task | Không cần cho vòng lặp thuần | Có, theo số nút chia |
| Scheduling/work stealing | Gần như không có ở vòng lặp thuần | Có |
| Đồng bộ kết quả | Tổng cộng dồn ngay | \`join()\` và kết hợp kết quả |
| Cache, memory bandwidth | Có | Có; nhiều worker có thể tranh băng thông |
| JIT, GC và warmup | Có | Có, đôi khi bị ảnh hưởng khác |
| Số lõi vật lý khả dụng | Một luồng tính toán | Có thể tận dụng nhiều lõi nếu đủ việc |

Nếu mỗi leaf chỉ thực hiện vài phép cộng, overhead có thể chiếm phần lớn tổng thời gian. Nếu mỗi leaf chứa rất nhiều phép tính độc lập, việc song song hóa có thể bù được overhead. Nếu mỗi task cần truy cập một tài nguyên tuần tự hoặc chia sẻ lock, nhiều worker chưa chắc giúp ích.

**Không có ngưỡng leaf size “tốt nhất” chung cho mọi chương trình.** Ngưỡng phụ thuộc phép tính, kích thước dữ liệu, cache, tốc độ CPU, số worker và khả năng tranh chấp tài nguyên.

## 4. Chương trình benchmark Java 17 chạy độc lập

Ví dụ này có đủ hai phiên bản của cùng một phép tính. Hàm \`transform\` thực hiện một số vòng biến đổi số nguyên trên từng phần tử để công việc không quá nhẹ. Kết quả được kiểm tra **trước và trong khi đo**. Chương trình dùng pool riêng, warmup và nhiều lần đo, báo cáo **median** thay vì chỉ dựa vào một lần chạy.

Lưu thành **\`ForkJoinVsSequentialBenchmark.java\`**:

\`\`\`java
import java.util.Arrays;
import java.util.Locale;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveTask;
import java.util.concurrent.TimeUnit;

public class ForkJoinVsSequentialBenchmark {
    private static final int SIZE = 1_000_000;
    private static final int THRESHOLD = 32_768;
    private static final int WARMUPS = 3;
    private static final int TRIALS = 7;

    // Ngăn kết quả chỉ tồn tại trong phép đo mà không được dùng.
    private static volatile long resultSink;

    private static long transform(long value) {
        long x = value;
        for (int i = 0; i < 16; i++) {
            x ^= x >>> 27;
            x *= 0x3C79AC492BA7B653L;
            x ^= x >>> 33;
        }
        return x;
    }

    private static long sequential(long[] data, int lo, int hi) {
        long sum = 0L;
        for (int i = lo; i < hi; i++) {
            sum += transform(data[i]);
        }
        return sum;
    }

    private static final class SumTask extends RecursiveTask<Long> {
        private final long[] data;
        private final int lo;
        private final int hi;
        private final int threshold;

        SumTask(long[] data, int lo, int hi, int threshold) {
            this.data = data;
            this.lo = lo;
            this.hi = hi;
            this.threshold = threshold;
        }

        @Override
        protected Long compute() {
            if (hi - lo <= threshold) {
                return sequential(data, lo, hi);
            }
            int mid = lo + (hi - lo) / 2;
            SumTask left = new SumTask(data, lo, mid, threshold);
            SumTask right = new SumTask(data, mid, hi, threshold);

            left.fork();
            long rightResult = right.compute();
            long leftResult = left.join();
            return leftResult + rightResult;
        }
    }

    private static long parallel(
            ForkJoinPool pool, long[] data, int threshold) {
        return pool.invoke(new SumTask(data, 0, data.length, threshold));
    }

    private static long timedSequential(long[] data, long expected) {
        long start = System.nanoTime();
        long value = sequential(data, 0, data.length);
        long elapsed = System.nanoTime() - start;

        if (value != expected) {
            throw new AssertionError("Sequential checksum mismatch");
        }
        resultSink = value;
        return elapsed;
    }

    private static long timedParallel(
            ForkJoinPool pool, long[] data, int threshold, long expected) {
        long start = System.nanoTime();
        long value = parallel(pool, data, threshold);
        long elapsed = System.nanoTime() - start;

        if (value != expected) {
            throw new AssertionError("Fork/Join checksum mismatch");
        }
        resultSink = value;
        return elapsed;
    }

    private static long median(long[] measurements) {
        long[] ordered = measurements.clone();
        Arrays.sort(ordered);
        return ordered[ordered.length / 2]; // TRIALS là số lẻ.
    }

    public static void main(String[] args) throws InterruptedException {
        long[] data = new long[SIZE];
        for (int i = 0; i < data.length; i++) {
            data[i] = 13L * i + 7L;
        }

        int processors = Runtime.getRuntime().availableProcessors();
        int parallelism = Math.max(1, Math.min(processors, 4));
        ForkJoinPool pool = new ForkJoinPool(parallelism);

        try {
            long expected = sequential(data, 0, data.length);

            // Làm nóng cả hai đường tính, không tính vào các trial.
            for (int i = 0; i < WARMUPS; i++) {
                if (sequential(data, 0, data.length) != expected
                        || parallel(pool, data, THRESHOLD) != expected) {
                    throw new AssertionError("Different results");
                }
            }

            long[] sequentialNanos = new long[TRIALS];
            long[] parallelNanos = new long[TRIALS];

            // Đảo thứ tự phép đo giữa các trial để giảm thiên lệch.
            for (int i = 0; i < TRIALS; i++) {
                if (i % 2 == 0) {
                    sequentialNanos[i] = timedSequential(data, expected);
                    parallelNanos[i] =
                            timedParallel(pool, data, THRESHOLD, expected);
                } else {
                    parallelNanos[i] =
                            timedParallel(pool, data, THRESHOLD, expected);
                    sequentialNanos[i] = timedSequential(data, expected);
                }
            }

            double seqMs = median(sequentialNanos) / 1_000_000.0;
            double parMs = median(parallelNanos) / 1_000_000.0;
            double speedup = seqMs / parMs;

            System.out.println("Checksums equal: true");
            System.out.println("Trials per variant: " + TRIALS);
            System.out.println("Parallelism: " + parallelism);
            System.out.printf(Locale.ROOT,
                    "Sequential median: %.3f ms%n", seqMs);
            System.out.printf(Locale.ROOT,
                    "Fork/Join median: %.3f ms%n", parMs);
            System.out.printf(Locale.ROOT,
                    "Speedup: %.2fx%n", speedup);
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
\`\`\`

Chạy với JDK 17 trở lên:

\`\`\`bash
javac ForkJoinVsSequentialBenchmark.java
java ForkJoinVsSequentialBenchmark
\`\`\`

**Ba dòng đầu có cấu trúc xác định**, tuy nhiên \`Parallelism\` phụ thuộc số processor JVM nhận thấy:

\`\`\`text
Checksums equal: true
Trials per variant: 7
Parallelism: 4
\`\`\`

Dòng \`Parallelism: 4\` ở trên ứng với máy có ít nhất bốn processor khả dụng; nếu JVM chỉ thấy một hoặc hai processor, nó in số tương ứng. Ba dòng cuối in **thời gian median đo thực tế** (mili giây, ba chữ số thập phân) và \`Speedup\` (hai chữ số thập phân). Không có giá trị thời gian hay speedup cố định cho mọi máy.

Nếu chương trình in \`Speedup: 1.60x\`, điều đó nghĩa median thời gian tuần tự lớn hơn median Fork/Join khoảng 1,6 lần **trong phép đo này**. Nếu \`Speedup: 0.70x\`, Fork/Join chậm hơn tuần tự. Không mặc định kết quả phải lớn hơn 1.

### Vì sao kết quả chính xác?

- Hai đường tính dùng **chính cùng hàm \`transform\`**, cùng mảng và cùng khoảng chỉ số.
- \`SumTask\` chia đoạn nửa mở thành hai đoạn **không chồng lấn**, nên không bỏ sót phần tử và không tính trùng.
- Tổng \`long\` có thể tràn, nhưng phép cộng \`long\` của Java vẫn cho cùng kết quả bit pattern bất kể thứ tự nhóm phép cộng.
- \`pool.invoke(...) \` chờ kết quả của root task trước khi trả về.
- Trong vòng đo, phép kiểm tra \`value == expected\` đảm bảo không dùng một số đo nhanh nhờ tính sai; \`resultSink\` giữ kết quả có thể quan sát.

### Đây có phải benchmark đủ để đưa ra kết luận hiệu năng cuối cùng?

**Chưa.** Đây là một **harness học tập** dùng \`System.nanoTime()\`. Nó minh họa thiết kế so sánh công bằng, cách warmup, lặp thử nghiệm và xác nhận kết quả. JIT có thể biên dịch ở những thời điểm khác nhau; GC, turbo boost, CPU frequency scaling, nhiệt độ, OS scheduler, background process và layout bộ nhớ có thể ảnh hưởng số đo. Để công bố hoặc tối ưu microbenchmark một cách nghiêm túc, xem phần JMH bên dưới.

Không chạy cả hai biến thể **đồng thời** rồi đem thời gian so sánh: chúng sẽ tranh CPU/cache và đo một tình huống khác. Trong harness này mỗi lần đo kết thúc trước lần tiếp theo, xen kẽ thứ tự để giảm một số sai lệch đơn giản.

## 5. Công thức speedup và hiệu suất song song

Đặt:

- \(T_s\): thời gian của bản tuần tự.
- \(T_p\): thời gian của bản Fork/Join với \(P\) worker.
- \(S = T_s/T_p\): **speedup** (hệ số tăng tốc).
- \(E = S/P\): hiệu suất song song tương đối với số worker cấu hình.

| Ví dụ số đo | Speedup | Ý nghĩa |
| --- | --- | --- |
| \(T_s = 100\) ms, \(T_p = 50\) ms | \(2.0\times\) | Fork/Join mất một nửa thời gian |
| \(T_s = 100\) ms, \(T_p = 80\) ms | \(1.25\times\) | Có cải thiện, nhưng không tuyến tính |
| \(T_s = 100\) ms, \(T_p = 140\) ms | \(0.71\times\) | Fork/Join chậm hơn |
| \(T_s = 100\) ms, \(T_p = 100\) ms | \(1.0\times\) | Không thấy cải thiện |

Các số trên chỉ giải thích cách tính, không phải kết quả chạy của chương trình.

Với công việc có phần không thể song song, định luật **Amdahl** cho ước tính lý tưởng:

\[
S(P) \leq \frac{1}{(1-f) + f/P}
\]

Trong đó \(f\) là tỷ lệ thời gian có thể song song hóa và \(P\) là số worker. Công thức lý tưởng này còn **chưa tính** chi phí chia task, đồng bộ, memory bandwidth và cân bằng tải; vì vậy số thực tế thường thấp hơn ước tính.

Ví dụ khi chỉ 80% công việc có thể song song hóa và dùng 4 worker, tốc độ tối đa lý tưởng là \(1/(0.2+0.8/4)=2.5\times\), dù có bốn worker. Không nên kỳ vọng \`4x\` chỉ vì \`parallelism=4\`.

Một chỉ số khác là **throughput** (đơn vị công việc/giây). Nếu benchmark chạy một batch với kích thước cố định, tốc độ tính ra là \(N/T\). Với ứng dụng phục vụ yêu cầu đồng thời, cần đo thêm latency p95/p99, số task xếp hàng, CPU utilization và GC, vì batch speedup không tự động đồng nghĩa cải thiện toàn hệ thống.

## 6. Tác động của threshold và kích thước công việc

\`threshold\` là kích thước đoạn nhỏ nhất được xử lý trực tiếp. Nó chi phối số lượng task và lượng công việc trên mỗi leaf.

- **Threshold quá nhỏ:** tạo nhiều \`RecursiveTask\`, tốn cấp phát, scheduling và \`join()\`; các leaf quá nhẹ.
- **Threshold quá lớn:** không tạo đủ nhánh để nhiều worker có việc; một số worker rảnh, khả năng cân bằng tải kém.
- **Threshold phù hợp:** mỗi leaf đủ lớn để chi phí tính toán vượt overhead, nhưng đủ nhỏ để phân chia công việc cho pool.

Với một mảng có \(N\) phần tử và threshold \(L\), cách chia đôi thường tạo xấp xỉ \(N/L\) leaf task khi \(N\) lớn hơn \(L\); số nút trung gian cũng tăng theo số leaf. Đây là ước lượng định hướng, không phải số task chính xác cho mọi \(N\) và \(L\).

### Ma trận thí nghiệm hữu ích

| Biến cần thay đổi | Các giá trị minh họa | Muốn quan sát |
| --- | --- | --- |
| Kích thước dữ liệu \(N\) | 10 nghìn, 100 nghìn, 1 triệu, 10 triệu | Điểm giao mà song song bắt đầu có lợi |
| Leaf threshold | 512, 4.096, 32.768, 262.144 | Chi phí task so với mức tận dụng worker |
| Parallelism | 1, 2, 4, 8 (nếu có tài nguyên thật) | Khả năng mở rộng và bão hòa CPU |
| Công việc mỗi phần tử | Cộng đơn giản, biến đổi nhiều vòng | Workload nhẹ và nặng khác nhau |
| Dữ liệu phân bố không đều | Đoạn có độ khó khác nhau | Giá trị của work stealing |

Các hàng là **thiết kế thí nghiệm**, không phải cam kết mọi máy có RAM hoặc lõi đủ để chạy tất cả tổ hợp. Giữ các biến còn lại cố định khi khảo sát một biến. Nên chạy nhiều fork/trial độc lập, lưu median hoặc phân phối thời gian, và báo cấu hình JDK/CPU/heap/OS.

Trong chương trình ví dụ, thử sửa \`THRESHOLD\` lần lượt thành 1.024, 8.192, 32.768 và 131.072 để quan sát sự thay đổi. Không đổi thuật toán \`transform\` giữa hai biến thể trong cùng một phép so sánh.

## 7. Work stealing và cân bằng tải thực tế

Fork/Join hữu ích nhất khi bài toán có thể chia thành các phần độc lập, bao gồm những trường hợp khối lượng tính toán **không đồng đều** như đệ quy, tìm kiếm, duyệt cây hoặc xử lý dữ liệu theo nhánh.

Một worker có thể có nhiều task trong deque của nó. Khi một worker khác rảnh, nó có thể **steal** task để tiếp tục làm việc. Việc này cải thiện sử dụng CPU khi không biết trước nhánh nào tốn thời gian hơn.

Tuy nhiên:
- Work stealing cũng có chi phí điều phối.
- Nếu mọi leaf đều cực kỳ nhẹ, worker dành nhiều thời gian để quản lý task.
- Nếu mọi worker cùng đọc/ghi dữ liệu lớn, memory bandwidth và cache contention có thể thành nút thắt.
- Nếu các task tranh lock hoặc ghi cùng một biến, độ song song hữu ích giảm mạnh.
- Task blocking trên I/O dài hạn có thể giữ worker mà không tiêu thụ CPU hữu ích; Fork/Join thiết kế tốt cho công việc CPU-bound có thể tách, không phải giải pháp mặc định cho mọi I/O blocking.

Trong Java, \`ForkJoinPool.managedBlock(...)\` là cơ chế chuyên biệt để pool có thể xử lý một số tình huống chặn có quản lý. Nó không tự biến mọi I/O thành non-blocking và không nên thêm vào benchmark CPU chỉ để tăng số thread.

## 8. Tránh các bẫy khi dùng System.nanoTime()

\`System.nanoTime()\` phù hợp để đo **khoảng thời gian tương đối** trong một tiến trình JVM:

\`\`\`java
long started = System.nanoTime();
long result = doWork();
long elapsedNanos = System.nanoTime() - started;
\`\`\`

Đây là fragment; \`doWork()\` do ứng dụng định nghĩa. Không dùng \`System.currentTimeMillis()\` để đo thời lượng ngắn vì độ phân giải và khả năng đồng hồ hệ thống bị chỉnh. \`nanoTime()\` có đơn vị nano giây nhưng **độ phân giải thực tế không mặc nhiên là 1 ns**.

Các lỗi thường gặp:

1. **Không warmup:** đo luôn lần đầu có thể chủ yếu đo class loading và JIT compilation.
2. **Chỉ một trial:** kết luận bị ảnh hưởng bởi scheduling, GC hoặc thermal throttling.
3. **Không dùng kết quả:** compiler/JIT có thể loại bỏ hoặc thay đổi một phần công việc nếu nó chứng minh không ảnh hưởng hành vi quan sát.
4. **Đặt việc chuẩn bị dữ liệu vào thời gian đo của chỉ một phiên bản:** so sánh không cùng phạm vi.
5. **Tạo \`ForkJoinPool\` trong vòng đo:** đo cả khởi tạo và shutdown pool mà phiên bản tuần tự không gánh; nếu use case thực tế tạo pool mỗi request thì phải đo riêng tình huống đó, không trộn với benchmark xử lý đã có pool.
6. **Đo cả in console:** \`System.out.println()\` và flush đầu ra có chi phí biến động, che khuất chi phí tính toán.
7. **Cho hai phiên bản chạy đồng thời:** chúng tranh CPU và cache, biến phép đo thành benchmark contention.
8. **Không kiểm tra checksum:** một phiên bản xử lý thiếu phần tử có thể trông nhanh hơn một cách sai lệch.
9. **Dùng số worker bằng số logical core mà mặc định đạt speedup tương ứng:** hyperthreading, container CPU quota và workload memory-bound có thể làm khác xa dự đoán.
10. **Dựa vào median mà quên độ phân tán:** nên xem min/max, p95 hoặc khoảng tin cậy khi cần quyết định đầu tư tối ưu hóa.

Warmup và median giúp tốt hơn một phép đo đơn lẻ, nhưng **không khắc phục toàn bộ** sai lệch JIT, DCE, GC và tối ưu hóa phụ thuộc cấu trúc benchmark.

## 9. Khi nào nên dùng JMH?

**JMH (Java Microbenchmark Harness)** là công cụ benchmark chuyên biệt của hệ sinh thái OpenJDK, được sử dụng khi cần so sánh microbenchmark Java có độ tin cậy cao hơn. JMH **không có sẵn trong thư viện chuẩn JDK**: cần thêm dependency và chạy bằng cấu hình build/harness phù hợp.

JMH hỗ trợ:
- Warmup iterations và measurement iterations.
- Nhiều **fork JVM** độc lập, giảm tác động trạng thái giữa các lượt.
- Đơn vị đo, throughput/average time/sample time.
- \`Blackhole\` để tiêu thụ kết quả, tránh một số dạng dead-code elimination.
- Trạng thái benchmark (\`@State\`) và lifecycle (\`@Setup\`, \`@TearDown\`).
- Tham số (\`@Param\`) để tự động thử nhiều threshold, kích thước dữ liệu hoặc số worker.

Một ví dụ **fragment cần JMH dependency** (không phải chương trình \`javac\` độc lập):

\`\`\`java
@State(Scope.Benchmark)
public class SumBenchmark {
    @Param({"8192", "32768", "131072"})
    public int threshold;

    private long[] data;
    private ForkJoinPool pool;

    @Setup(Level.Trial)
    public void setUp() {
        data = createInput();
        pool = new ForkJoinPool(4);
    }

    @TearDown(Level.Trial)
    public void tearDown() {
        pool.shutdown();
    }

    @Benchmark
    public long sequential() {
        return sumSequential(data);
    }

    @Benchmark
    public long forkJoin() {
        return pool.invoke(new SumTask(data, 0, data.length, threshold));
    }
}
\`\`\`

Cấu trúc trên chỉ minh họa JMH annotations và phạm vi setup: cần các import từ \`org.openjdk.jmh.annotations\`, dependency JMH, cùng các helper \`createInput\`, \`sumSequential\` và \`SumTask\` từ ứng dụng thử nghiệm. Kết quả benchmark trả ra \`long\`, để harness có thể tiêu thụ, không tự in console trong method \`@Benchmark\`.

Quan trọng: cùng một bộ dữ liệu, cùng hàm tính toán, cùng số worker, cùng JDK/JVM flags và có đủ thời gian warmup. Ngay cả JMH cũng không bảo đảm kết quả đại diện cho workload production nếu thao tác được đo khác thực tế.

Tham khảo dự án chính thức: [OpenJDK JMH](https://github.com/openjdk/jmh). Khi cần số liệu để ra quyết định, lưu cả cấu hình benchmark, phiên bản JDK/JMH, phần cứng và phân phối kết quả để người khác có thể chạy lại.

## 10. Đọc kết quả benchmark đúng ngữ cảnh

Giả sử thử nghiệm cho thấy:

- Input nhỏ: tuần tự nhanh hơn do chi phí chia task.
- Input vừa: Fork/Join bắt đầu ngang hoặc nhỉnh hơn.
- Input lớn, CPU-bound: Fork/Join có thể nhanh hơn nếu có nhiều lõi.
- Input lớn nhưng memory-bound: tăng worker có thể không tăng tốc nhiều.
- Workload có lock chung: nhiều worker có thể chậm hơn do contention.

Đây là **những xu hướng có thể xảy ra**, không phải quy luật tuyệt đối. Cần đo và kiểm chứng trên máy/production tương ứng.

### Báo cáo benchmark nên chứa gì?

| Thông tin | Vì sao cần |
| --- | --- |
| Bài toán, input size và đặc tính dữ liệu | Đảm bảo hai phiên bản xử lý cùng việc |
| Phiên bản JDK và JVM flags | JIT/GC có thể khác |
| CPU, core/thread, RAM, container quota | Để giải thích khả năng song song thực tế |
| Parallelism, threshold, pool lifecycle | Các tham số quyết định số task và overhead |
| Warmup, số trial/fork, metric được báo | Phân biệt độ ổn định và phép đo may mắn |
| Kết quả đúng/checksum | Tránh so sánh thuật toán không tương đương |
| Thời gian, speedup, phân phối thời gian | Cung cấp bằng chứng thay vì một số đơn lẻ |
| CPU, allocation và GC nếu có | Giải thích chi phí được chuyển sang nơi khác |

Nếu Fork/Join nhanh hơn trong một microbenchmark nhưng API production chậm hơn, xem thêm queueing delay, contention với request khác, garbage collection, cache, I/O và giới hạn tài nguyên. **Latency của batch** khác với **throughput toàn ứng dụng**.

## 11. Những sai lầm riêng của thuật toán Fork/Join

### Không gọi fork rồi join ngay một cách vô ích

Mẫu kém:

\`\`\`java
left.fork();
long leftValue = left.join();
long rightValue = right.compute();
\`\`\`

Worker có thể bị chặn chờ \`left\` trước khi bắt đầu tính \`right\`, giảm khả năng tận dụng song song. Mẫu thường được khuyến nghị:

\`\`\`java
left.fork();
long rightValue = right.compute();
long leftValue = left.join();
return leftValue + rightValue;
\`\`\`

Code trên là fragment trong \`compute()\`, hai task đã được xây dựng trước đó. Nó giúp worker hiện tại có việc hữu ích trong lúc các worker khác có thể lấy task đã fork.

### Không chia mãi đến một phần tử

Mỗi task có overhead. Dừng ở ngưỡng được lựa chọn dựa trên phép đo, rồi xử lý leaf bằng vòng lặp tuần tự. Các nhánh không nhất thiết đều nhau nếu chi phí xử lý của từng phần tử thay đổi; với bài toán chia đều dễ dự đoán, chia đôi khoảng chỉ số là baseline tốt.

### Không chia sẻ biến tổng có tranh chấp

Tránh để tất cả worker cập nhật \`static long sum\` hoặc một \`AtomicLong\` duy nhất trên mỗi phần tử nếu mục tiêu benchmark là phép cộng song song hiệu quả. Điều này có thể gây data race hoặc contention. Mỗi leaf nên trả tổng cục bộ và root kết hợp kết quả qua \`join()\`.

### Chú ý integer overflow và floating point

Với phép tính \`long\`, overflow được xác định ở cấp ngôn ngữ và kết quả mod \(2^{64}\) tương đương khi đổi cách nhóm phép cộng. Nếu nghiệp vụ yêu cầu **tổng toán học chính xác vượt giới hạn \`long\`**, dùng \`BigInteger\` hoặc thuật toán phù hợp cho cả hai biến thể rồi benchmark lại. Với \`double\`, thứ tự cộng khác nhau có thể dẫn tới số khác nhau; dùng tolerance và kiểm tra độ chính xác số học.

### Không mặc định dùng commonPool cho mọi phép đo

\`ForkJoinPool.commonPool()\` được chia sẻ bởi nhiều đoạn code trong tiến trình; tải từ phần khác của ứng dụng có thể ảnh hưởng benchmark. Pool riêng giúp xác định \`parallelism\` và lifecycle rõ hơn, nhưng **không làm máy tách biệt khỏi các tiến trình/luồng hệ thống khác**.

## 12. Checklist thí nghiệm và kết luận

1. **Định nghĩa cùng một workload:** đầu vào, hàm tính, số phần tử, thao tác đọc/ghi giống nhau.
2. **Kiểm tra đúng trước khi đo:** checksum/result giống nhau; với floating point xác định tolerance.
3. **Chọn baseline tuần tự tối giản:** không buộc bản tuần tự chịu overhead không cần thiết.
4. **Kiểm soát pool:** tạo một pool có parallelism xác định và quản lý shutdown ngoài vùng đo nếu đo steady state.
5. **Warmup và lặp lại:** không kết luận từ lần đầu hoặc một trial.
6. **Khảo sát threshold, data size và parallelism:** tìm vùng mà overhead đã được bù.
7. **Giảm nhiễu môi trường:** đóng chương trình nặng khác, giữ cấu hình JDK và máy nhất quán.
8. **Đo kết quả thực tế:** median, độ phân tán, speedup, CPU và GC; JMH khi cần độ tin cậy cao.
9. **Kiểm thử correctess/concurrency:** phân chia không trùng, không sót, task không sửa state dùng chung thiếu đồng bộ.
10. **Xác nhận ở production workload:** batch benchmark không thay cho phép đo end-to-end.

## 13. Câu hỏi tự kiểm tra

**1. Cứ tăng \`parallelism\` thì Fork/Join sẽ nhanh hơn?**  
Không. Speedup bị giới hạn bởi phần việc tuần tự, số lõi thực, overhead, contention và memory bandwidth.

**2. Vì sao threshold quá nhỏ thường xấu?**  
Số lượng \`RecursiveTask\`, operations \`fork/join\` và scheduling lớn so với lượng tính toán mỗi leaf.

**3. Có thể so sánh hai thuật toán trả kết quả khác nhau không?**  
Không thể kết luận tốc độ của **cùng bài toán** nếu chúng không tương đương về ý nghĩa kết quả. Cần kiểm tra correctness và định nghĩa phép đo.

**4. \`System.nanoTime()\` có làm benchmark tự động chính xác?**  
Không. Nó chỉ giúp đo khoảng thời gian; phải xử lý warmup, JIT, GC, dead-code elimination, tải máy và nhiều trial.

**5. Speedup \(0.8\times\) nghĩa là gì?**  
Fork/Join chậm hơn baseline tuần tự trong phép đo đó, vì \(T_s/T_p = 0.8\).

**6. Vì sao nên giữ \`left.fork(); right.compute(); left.join();\`?**  
Worker hiện tại tiếp tục thực hiện việc có ích trong khi nhánh trái có thể được worker khác xử lý.

**7. JMH giải quyết vấn đề gì?**  
Nó cung cấp harness chuyên dụng để warmup, measurement, JVM forks và tiêu thụ kết quả, giảm một số bẫy của microbenchmark thủ công.

**8. Khi nào cần kiểm thử cả ở mức ứng dụng?**  
Khi muốn biết hiệu năng thật dưới cạnh tranh CPU/GC, queue, latency yêu cầu, I/O và nhu cầu của workload production.

## Tài liệu tham khảo

- [Java SE 17 — ForkJoinPool](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ForkJoinPool.html)
- [Java SE 17 — ForkJoinTask](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ForkJoinTask.html)
- [Java SE 17 — RecursiveTask](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/RecursiveTask.html)
- [OpenJDK — Java Microbenchmark Harness (JMH)](https://github.com/openjdk/jmh)

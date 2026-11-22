# Chọn ngưỡng xử lý tuần tự thay vì tách thêm tác vụ

**Chủ đề:** Computer Science Algorithms · Thuật toán song song

## 1. Vì sao không nên chia mãi thành những tác vụ nhỏ?

Một chương trình xử lý dữ liệu bằng chia để trị thường chia bài toán thành các phần nhỏ, chạy trên nhiều worker threads, rồi ghép kết quả. Tuy nhiên **tác vụ càng nhỏ chưa chắc chương trình càng nhanh**.

Một tác vụ song song có chi phí ngoài phép tính chính:
- Tạo đối tượng tác vụ và các trường trạng thái.
- Đưa tác vụ vào deque/hàng đợi, được worker khác **work stealing** khi cần.
- Gửi lệnh fork, đợi join và xử lý kết quả.
- Quản lý scheduling, đồng bộ và phụ thuộc giữa các nhánh.
- Gây allocation, garbage collection và thay đổi locality/cache.
- Đôi khi gây tranh chấp cache, memory bandwidth hoặc locks.

Nếu một đoạn chỉ gồm vài số long để cộng, thời gian tạo tác vụ có thể lớn hơn thời gian cộng chúng.

**Sequential cutoff** (còn gọi **grain size / task size threshold**) là ngưỡng mà dưới đó một bài toán con được **xử lý tuần tự**, không tách thành tác vụ con mới. Đây là một quyết định về **độ hạt tác vụ**, không phải chỉ là một con số tuỳ chọn trong API.

Quy tắc:

\[
\boxed{\text{Nếu size}\le c,\ \text{chạy tuần tự};\quad
\text{nếu size}>c,\ \text{chia và phối hợp}.}
\]

Ngưỡng c cần được chọn sao cho **mỗi lá có đủ việc hữu ích để bù overhead**, đồng thời vẫn tạo **đủ lá để khai thác nhiều cores**. Không có cutoff tối ưu phổ quát cho mọi bài toán, kích thước dữ liệu, JVM hay CPU.

## 2. Ví dụ xuyên suốt: tổng mảng bằng Fork/Join

Cho mảng long[] a có n phần tử. Mục tiêu:

\[
S=\sum_{i=0}^{n-1}a[i].
\]

Bài này phù hợp để minh hoạ vì:
- Kết quả có **oracle tuần tự** rất đơn giản.
- Có thể chia mảng tại giữa thành hai đoạn **không chồng lấn**.
- Hai nhánh chỉ đọc dữ liệu, không cần cập nhật tổng chia sẻ.
- Sau cùng kết hợp bằng phép cộng.
- Tổng phải xử lý **long overflow** rõ ràng.

Một đoạn [from,to) là nửa mở, bao gồm from và không bao gồm to. Khi length=to−from:

~~~text
sumRange(a, from, to, cutoff):
    if length <= cutoff:
        sum = 0
        for i = from .. to-1:
            sum += a[i]
        return sum

    mid = from + floor(length/2)
    fork right = sumRange(a, mid, to, cutoff)
    left = sumRange(a, from, mid, cutoff) // compute inline
    right = join(right)
    return left + right
~~~

Tách tại giữa tạo:
- Trái [from,mid).
- Phải [mid,to).

Hai đoạn **rời nhau và phủ trọn** [from,to). Nếu length>cutoff và cutoff≥1, cả hai đoạn đều **nhỏ hơn đoạn ban đầu**, nên cuối cùng sẽ đến base case. Điều kiện cutoff phải **dương**: ngưỡng 0 có thể khiến đoạn độ dài 1 tiếp tục tách thành đoạn 0 và 1, làm đệ quy không kết thúc.

### 2.1. Vì sao fork một nhánh, tính nhánh còn lại inline?

Trong mô hình ForkJoinPool, một mẫu phổ biến là:

~~~java
right.fork();
Stats leftStats = left.compute();
Stats rightStats = right.join();
return combine(leftStats, rightStats);
~~~

Worker đang chạy vẫn **làm việc hữu ích** ở nhánh trái trong lúc nhánh phải sẵn sàng cho worker khác lấy. Nếu fork cả hai nhánh hoặc gọi join ngay sau fork, chương trình có thể chịu thêm overhead hoặc bỏ phí cơ hội song song.

Đây là quy tắc triển khai tốt trong nhiều bài chia để trị, **không có nghĩa fork một nhánh luôn tối ưu trên mọi runtime**. Kết quả phụ thuộc workload và scheduler.

### 2.2. Chứng minh tính đúng

Gọi F(l,r) là tổng những phần tử có index thuộc [l,r).

**Cơ sở:** khi r−l≤c, vòng lặp duyệt đúng mọi a[l],…,a[r−1], không bỏ hay lặp vị trí nào, nên trả F(l,r).

**Quy nạp:** khi r−l>c, đặt mid ở giữa. Theo giả thiết quy nạp, nhánh trái trả F(l,mid), nhánh phải trả F(mid,r). Vì hai đoạn không giao và phủ toàn [l,r):

\[
F(l,r)=F(l,mid)+F(mid,r).
\]

Do đó kết quả ghép đúng tổng toàn đoạn. Thứ tự scheduling không làm thay đổi tính đúng của **số học nguyên không overflow**, vì các nhánh chỉ đọc và trả kết quả riêng.

**Giới hạn:** phép cộng double không hoàn toàn associative trong số học máy do rounding, nên những thứ tự cộng khác nhau có thể cho kết quả bit khác. Code Java dùng Math.addExact với long để tránh âm thầm tràn số.

## 3. Cutoff thay đổi hình dạng cây công việc

Xét mảng gồm 16 phần tử:

~~~text
a = [5, -2, 7, 1, 3, 0, -4, 8,
     2, 6, -1, 9, 4, -3, 10, 1]
sum = 46
~~~

Từ một đoạn dài 16, thuật toán chia đôi đến khi mỗi lá có chiều dài không quá c.

| Cutoff c | Nodes trong cây | Lá tuần tự | Fork calls | Max depth | Sum |
|---:|---:|---:|---:|---:|---:|
| 1 | 31 | 16 | 15 | 4 | 46 |
| 2 | 15 | 8 | 7 | 3 | 46 |
| 4 | 7 | 4 | 3 | 2 | 46 |
| 8 | 3 | 2 | 1 | 1 | 46 |
| 16 | 1 | 1 | 0 | 0 | 46 |
| 32 | 1 | 1 | 0 | 0 | 46 |

Giải thích:
- c=1 tạo một lá cho từng phần tử, làm số lời gọi và fork rất nhiều so với lượng tính toán thực.
- c=4 chỉ tạo bốn lá, mỗi lá cộng bốn phần tử.
- c=8 tạo hai lá, nên tối đa hai nhánh lá có thể làm việc đồng thời.
- c=16 hoặc c=32: toàn bộ mảng xử lý tuần tự trong một lá, không fork thêm nhánh con.

Mọi hàng trả **cùng tổng 46**. Bảng **không chứng minh cutoff nào nhanh nhất** vì chưa đo thời gian.

### 3.1. Số nút, số lá và số fork

Với cây đệ quy mà mỗi nút trong sinh đúng hai con:
- L là số lá tuần tự.
- I=L−1 là số nút trong.
- Nnodes=2L−1.
- Nếu tại mỗi nút trong fork đúng **nhánh phải**, số lệnh fork thực hiện là L−1.

Đó là số **đơn vị đệ quy/tác vụ**, không phải số thread OS. Một worker có thể xử lý hàng nghìn tác vụ; một pool với parallelism 4 không có nghĩa mọi lúc đều có đúng 4 threads đang chạy.

### 3.2. Mảng không phải lũy thừa hai

Với n=17 và cutoff=4:

~~~text
17 -> 8 + 9
8  -> 4 + 4
9  -> 4 + 5
5  -> 2 + 3
leaf lengths: 4, 4, 4, 2, 3
~~~

Tổng cộng **5 lá, 9 nút, 4 fork, depth=3**. Các lá không bắt buộc có chiều dài bằng cutoff; chúng chỉ phải **không vượt cutoff**.

Với chia đôi tương đối cân bằng, số lá thường có bậc:

\[
L=\Theta(\max(1,n/c)).
\]

Nhưng L không luôn bằng chính xác n/c. Khi n≤c thì L=1, kể cả n=0 trong demo.

## 4. Hai rủi ro đối nghịch

### 4.1. Cutoff quá nhỏ: overhead thống trị

Giả sử mỗi phần tử cần t đơn vị tính toán, còn việc tạo/schedule một nhánh tốn khoảng \(\sigma\). Một lá c phần tử có công việc hữu ích gần:

\[
T_{\mathrm{leaf}}\approx c\,t.
\]

Nếu:

\[
ct\ll\sigma,
\]

thì overhead tác vụ có thể lớn hơn việc thực sự tính toán. Ví dụ cộng một long thường rẻ hơn rất nhiều so với tạo/schedule một RecursiveTask mới.

Với n lớn và c rất bé, số lá cỡ n/c, số fork cỡ n/c; chi phí chung có thể xấp xỉ:

\[
W\approx n\,t+\sigma\Theta(n/c).
\]

Càng tách nhiều, **work phát sinh không cần thiết** càng lớn. Ngoài chi phí scheduler, nhiều object nhỏ làm tăng GC hoặc pressure lên cache.

### 4.2. Cutoff quá lớn: không đủ tác vụ cho workers

Giả sử pool có P=8 workers, bài n=16 nhưng cutoff c=8 ⇒ chỉ có **hai lá**. Nếu lượng việc chia đều, tối đa hai lá có thể làm việc cùng lúc; sáu workers khác không có nhánh lá độc lập để xử lý.

Nếu n/c nhỏ hơn P, thường không có đủ đơn vị công việc để tận dụng tất cả worker. Đối với workload không đều, cần thêm các tác vụ dự phòng để worker rảnh có thể **steal** việc.

Mặt khác, không phải cứ tăng lá lên hàng triệu là tăng throughput. Chọn cutoff là một bài cân bằng giữa:
1. Công việc trong một lá.
2. Chi phí tạo/điều phối tác vụ.
3. Số worker/CPU cores có thể sử dụng.
4. Mức độ đều của các nhánh.
5. Cache locality, memory bandwidth và GC.

## 5. Mô hình Work và Span

Để lý luận về khả năng song song hóa, phân biệt:

**Work W:** tổng số công việc của toàn thuật toán khi cộng tất cả nhánh, bao gồm overhead theo mô hình phân tích.

**Span S:** chiều dài chuỗi phụ thuộc dài nhất trong đồ thị tác vụ (critical path). Một lịch thực thi không thể nhanh hơn đường găng ngay cả với vô số processors.

Với P processors, luôn có cận dưới:

\[
\boxed{T_P\ge\max(W/P,S)}.
\]

Trong mô hình lịch chạy lý tưởng thích hợp, một cận kinh điển là \(O(W/P+S)\). Với JVM thực, còn overhead task queues, work stealing, GC, cache, contention và băng thông bộ nhớ.

### 5.1. Work của chia đôi tổng mảng

Tổng số phần tử được cộng tại các lá đúng bằng n. Bỏ overhead thì work Θ(n). Nếu mỗi nút trong tốn thêm chi phí trung bình \(\sigma\), tổng có thể mô hình hóa:

\[
W=\Theta(n t+(n/c)\sigma)
\quad(n\gg c).
\]

C tăng giúp giảm số nút trong và overhead, nhưng có thể làm giảm parallelism.

### 5.2. Span lý tưởng

Nếu tách cân bằng và gộp hai tổng trong O(1), một đường từ gốc đến lá có:
- Khoảng log2(n/c) tầng chia khi n>c.
- Một lá xử lý tuần tự tối đa c phần tử.
- Chi phí kết hợp mỗi tầng hằng số trong mô hình đơn giản.

Vậy:

\[
S=O(c+\log(n/c))
\quad(n>c),
\]

và khi n≤c thì S=O(n) vì thực hiện tuần tự một đoạn.

Giảm cutoff có thể giảm thời gian tại lá trên đường găng nhưng **tăng work overhead**. Chỉ tối ưu span lý tưởng mà bỏ chi phí scheduling không đủ để chọn cutoff tốt.

### 5.3. Parallelism có sẵn

Tỷ số W/S biểu thị mức parallelism lý thuyết của DAG. Nếu W/S nhỏ, việc tăng P thêm nhiều không còn hữu ích; nếu W/S lớn, cũng không bảo đảm scale hoàn hảo do giới hạn tài nguyên thật.

Với phép tính tổng đơn giản, thao tác mỗi phần tử rẻ nên nhiều tình huống chương trình trở thành **memory-bandwidth bound**. Các lõi thêm không tạo ra băng thông RAM vô hạn.

## 6. Amdahl và giới hạn kỳ vọng speedup

Nếu tỷ lệ s của chương trình không thể song song hóa và phần còn lại lý tưởng chạy trên P processors:

\[
Speedup(P)\le\frac1{s+(1-s)/P}.
\]

Ví dụ s=0,1, P=8:

\[
Speedup(8)\le\frac1{0,1+0,9/8}\approx4,71.
\]

Đây là **cận lý thuyết của mô hình Amdahl**, không phải kết quả chạy benchmark Java trên máy cụ thể. Overhead scheduler hoặc memory contention có thể làm speedup thấp hơn, thậm chí bản song song chậm hơn bản tuần tự.

Định nghĩa khi đo:
- \(Speedup(P)=T_{\mathrm{sequential}}/T_P\).
- \(Efficiency(P)=Speedup(P)/P\).

Báo cả số liệu thời gian, không chỉ số lá hay số task.

## 7. Một quy trình chọn cutoff

### 7.1. Bước 1: xác định đơn vị work

Trong phép tính tổng, length là số phần tử và chi phí mỗi phần tử khá đều.

Trong các thuật toán khác:
- Phân tích cú pháp: chi phí có thể phụ thuộc nội dung token.
- QuickSort: partition có thể cân bằng hoặc lệch.
- Xử lý ảnh: work phụ thuộc nội dung, tile size và cache.
- DFS hoặc nhánh-cận: một subtree nhỏ về số node ban đầu có thể nở ra rất lớn.
- Mã hóa/nén: chi phí trên byte có thể thay đổi theo dữ liệu.

Một cutoff đo **số phần tử** chỉ là heuristic. Nếu work mỗi phần tử không đều, có thể cân nhắc ước lượng chi phí thật hoặc policy thích ứng.

### 7.2. Bước 2: so công việc lá với chi phí fork/join

Đo thời gian tuần tự của một chunk và overhead fork/join trên môi trường đích. Chọn vùng c để một lá có đủ việc, thường muốn ct lớn hơn đáng kể \(\sigma\).

Không ấn định sẵn c=1000 hoặc c=8192 cho mọi máy/bài toán. Với một phép cộng long, ngưỡng có thể phải lớn hơn nhiều so với một tác vụ tính toán chuyên sâu trên mỗi phần tử.

### 7.3. Bước 3: bảo đảm đủ lá để worker làm việc

Với n phần tử, số lá xấp xỉ n/c. Để có ít nhất P lá độc lập:

\[
n/c\gtrsim P.
\]

Đối với workload không đều, thường nên có **nhiều hơn P** tasks để work stealing giúp cân tải. Nhưng quá nhiều tasks sẽ làm overhead tăng. Đây chỉ là vùng thử nghiệm ban đầu, **không phải định lý tối ưu hóa c**.

### 7.4. Bước 4: thử nhiều ngưỡng

Có thể bắt đầu với các giá trị c tăng lũy thừa hai:
- 16,32,64,128,256,512,…
- Sau đó thử giá trị nằm gần vùng cho thời gian tốt và ổn định.

Thử nhiều giá trị n, P, kiểu dữ liệu, số request đồng thời. Không kết luận dựa vào một benchmark đơn lẻ trên máy tính cá nhân.

### 7.5. Bước 5: ưu tiên hợp đồng sản phẩm

Ngưỡng tốt nhất về median throughput có thể không tốt nhất về p99 latency, peak memory hay throughput dưới tải đồng thời. Với một dịch vụ, cần giới hạn tài nguyên và tránh oversubscription khi nhiều request cùng chạy.

Nếu bài nhỏ, xử lý hoàn toàn tuần tự thường nhanh và đáng tin hơn việc kích hoạt pool chỉ để “dùng nhiều threads”.

## 8. ForkJoinPool và các API Java 17

Java cung cấp:
- **ForkJoinPool:** executor hỗ trợ tác vụ chia để trị và work stealing.
- **RecursiveTask<V>:** tác vụ tính toán có giá trị trả về.
- **RecursiveAction:** tác vụ không trả về giá trị.
- **fork():** lên lịch một tác vụ để có thể thực thi song song.
- **join():** lấy kết quả và chờ nếu chưa hoàn tất.
- **invoke():** bắt đầu tác vụ gốc và chờ hoàn thành.

Một mẫu triển khai:

~~~java
SumTask right = new SumTask(a, mid, to, cutoff);
right.fork();
Stats left = new SumTask(a, from, mid, cutoff).compute();
Stats rightResult = right.join();
return combine(left, rightResult);
~~~

Worker hiện tại có thể tính nhánh trái, trong khi nhánh phải có thể được thực thi hoặc đánh cắp bởi worker khác.

### 8.1. Tác vụ khác thread

**Một tác vụ không phải một thread riêng**. Worker threads có thể xử lý nhiều nhiệm vụ liên tiếp. Một ForkJoinPool cấu hình parallelism=4 hướng tới bốn workers cho xử lý CPU, nhưng không bảo đảm đúng bốn workers bận tại mọi thời điểm.

**Số nodes và leaves** của cây đệ quy là đặc tính của thuật toán; nó không cho biết đã sử dụng bao nhiêu CPU cores thực tế.

### 8.2. Không đặt điểm join quá sớm

Đoạn này dễ gây chờ không cần thiết:

~~~java
right.fork();
Stats rightResult = right.join();
Stats leftResult = left.compute();
~~~

Nó chờ nhánh phải xong trước khi nhánh trái được tính, bỏ cơ hội làm công việc độc lập ở worker hiện tại.

Mẫu nên dùng trong bài:

~~~java
right.fork();
Stats leftResult = left.compute();
Stats rightResult = right.join();
~~~

### 8.3. Tránh blocking I/O trong tác vụ CPU-bound

ForkJoinPool phù hợp nhất với những tác vụ CPU-bound nhỏ và nhiều. Nếu mỗi leaf chờ I/O, lock hay tác vụ mạng kéo dài, workers có thể bị block và tiến độ giảm. Có thể cần executor/async I/O khác hoặc dùng cơ chế phù hợp với blocking như ForkJoinPool.ManagedBlocker, tùy hợp đồng hệ thống.

Một cutoff hợp lý **không tự giải quyết** vấn đề blocking I/O hay thiết kế đồng bộ.

### 8.4. Tái sử dụng pool

Tạo một ForkJoinPool cho mỗi đoạn nhỏ có thể khiến thời gian khởi tạo/teardown lấn át công việc. Code demo tạo pool riêng **một lần** cho toàn bộ các lượt c, sau đó shutdown khi xong.

Trong phần mềm nhiều thành phần, dùng commonPool() cần cân nhắc nó là **tài nguyên chia sẻ**, có thể cạnh tranh với parallel streams và các tác vụ khác.

## 9. Java 17 hoàn chỉnh: SequentialCutoffDemo.java

Bản demo có:
- Một RecursiveTask<Stats> tách đoạn dài hơn cutoff.
- Một vòng lặp tuần tự ở lá.
- Nhánh phải fork, nhánh trái compute inline, sau đó join.
- Một record Stats bất biến cho sum, nodes, leaves, maxDepth.
- Số fork tính từ leaves−1 trong chính cây nhị phân này.
- Baseline sequentialSum và kiểm tra Math.addExact.
- Một ForkJoinPool với parallelism=4, tái sử dụng.
- Kiểm thử 500 mảng ngẫu nhiên bằng oracle tuần tự, so sum và bất biến cây.
- Kết quả mẫu **không in thời gian** vì latency tùy hệ thống/JIT/GC.

**Hợp đồng:**
1. Mảng không được null và không được mutate từ thread khác trong lúc chạy.
2. Cutoff phải ≥1.
3. Parallelism phải ≥1.
4. Input/partial sums phải vừa trong long; Math.addExact phát hiện overflow thay vì silent wrap.
5. Đoạn là nửa mở [from,to).
6. Mảng rỗng trả tổng 0, không có fork con.
7. Code Stats mang instrumentation: nó không đại diện benchmark tối ưu cho chính phép sum.

~~~java
import java.util.Arrays;
import java.util.Objects;
import java.util.Random;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveTask;

public final class SequentialCutoffDemo {
    private SequentialCutoffDemo() {
    }

    public record Stats(
            long sum, long nodes,
            long leaves, int maxDepth) {
        public long forks() {
            return leaves - 1;
        }
    }

    private static final class SumTask
            extends RecursiveTask<Stats> {
        private final long[] a;
        private final int from;
        private final int to;
        private final int cutoff;

        private SumTask(
                long[] a, int from, int to, int cutoff) {
            this.a = a;
            this.from = from;
            this.to = to;
            this.cutoff = cutoff;
        }

        @Override
        protected Stats compute() {
            int length = to - from;

            // Sequential base case: no child tasks.
            if (length <= cutoff) {
                long result = 0;
                for (int i = from; i < to; i++) {
                    result = Math.addExact(result, a[i]);
                }
                return new Stats(result, 1, 1, 0);
            }

            int mid = from + (length >>> 1);

            // Only one branch is forked; other runs inline.
            SumTask right = new SumTask(a, mid, to, cutoff);
            right.fork();

            Stats leftResult =
                    new SumTask(a, from, mid, cutoff).compute();
            Stats rightResult = right.join();

            // No shared mutable accumulator or counters.
            return new Stats(
                    Math.addExact(
                            leftResult.sum(), rightResult.sum()),
                    1 + leftResult.nodes() + rightResult.nodes(),
                    leftResult.leaves() + rightResult.leaves(),
                    1 + Math.max(
                            leftResult.maxDepth(),
                            rightResult.maxDepth()));
        }
    }

    public static long sequentialSum(long[] a) {
        Objects.requireNonNull(a, "array");
        long result = 0;
        for (long value : a) {
            result = Math.addExact(result, value);
        }
        return result;
    }

    private static Stats runOnPool(
            ForkJoinPool pool, long[] a, int cutoff) {
        Objects.requireNonNull(pool, "pool");
        Objects.requireNonNull(a, "array");
        if (cutoff <= 0) {
            throw new IllegalArgumentException(
                    "cutoff must be positive");
        }

        return pool.invoke(
                new SumTask(a, 0, a.length, cutoff));
    }

    public static Stats runParallel(
            long[] a, int cutoff, int parallelism) {
        if (parallelism <= 0) {
            throw new IllegalArgumentException(
                    "parallelism must be positive");
        }

        ForkJoinPool pool = new ForkJoinPool(parallelism);
        try {
            return runOnPool(pool, a, cutoff);
        } finally {
            pool.shutdown();
        }
    }

    private static void showCutoff(
            ForkJoinPool pool, long[] a, int cutoff) {
        Stats s = runOnPool(pool, a, cutoff);

        System.out.println("Cutoff " + cutoff
                + ": sum=" + s.sum()
                + ", nodes=" + s.nodes()
                + ", leaves=" + s.leaves()
                + ", forkCalls=" + s.forks()
                + ", depth=" + s.maxDepth());
    }

    private static void require(
            boolean ok, String message) {
        if (!ok) {
            throw new AssertionError(message);
        }
    }

    // Deterministic correctness tests, not benchmarks.
    private static int selfTest(ForkJoinPool pool) {
        Random random = new Random(5332026L);

        for (int test = 0; test < 500; test++) {
            int n = random.nextInt(129);
            long[] a = new long[n];

            for (int i = 0; i < n; i++) {
                a[i] = random.nextInt(2001) - 1000;
            }

            int cutoff = 1 + random.nextInt(80);
            Stats got = runOnPool(pool, a, cutoff);
            long expected = sequentialSum(a);

            require(got.sum() == expected, "Wrong sum");
            require(
                    got.nodes() == 2 * got.leaves() - 1,
                    "Wrong node count");
            require(
                    got.forks() == got.leaves() - 1,
                    "Wrong fork count");

            if (n <= cutoff) {
                require(
                        got.nodes() == 1
                        && got.leaves() == 1
                        && got.maxDepth() == 0,
                        "Base case incorrectly split");
            }

            require(
                    got.leaves() >= 1
                    && got.leaves() <= Math.max(1, n),
                    "Impossible leaf count");
        }
        return 500;
    }

    public static void main(String[] args) {
        long[] values = {
            5, -2, 7, 1, 3, 0, -4, 8,
            2, 6, -1, 9, 4, -3, 10, 1
        };

        long[] odd = {
            -1, 8, 0, 3, 3, 2, 5, -4, 2,
            8, 1, 9, -2, 5, 0, 1, 6
        };

        final int configuredParallelism = 4;
        ForkJoinPool pool =
                new ForkJoinPool(configuredParallelism);

        try {
            System.out.println(
                    "Array: " + Arrays.toString(values));
            System.out.println(
                    "Sequential sum: " + sequentialSum(values));
            System.out.println(
                    "Configured parallelism: "
                    + configuredParallelism);

            for (int cutoff : new int[]{
                    1, 2, 4, 8, 16, 32}) {
                showCutoff(pool, values, cutoff);
            }

            Stats oddResult = runOnPool(pool, odd, 4);
            System.out.println(
                    "Odd n=17 cutoff=4: sum="
                    + oddResult.sum()
                    + ", nodes=" + oddResult.nodes()
                    + ", leaves=" + oddResult.leaves()
                    + ", forkCalls=" + oddResult.forks()
                    + ", depth=" + oddResult.maxDepth());

            Stats empty = runOnPool(pool, new long[0], 4);
            System.out.println(
                    "Empty: sum=" + empty.sum()
                    + ", nodes=" + empty.nodes()
                    + ", leaves=" + empty.leaves()
                    + ", depth=" + empty.maxDepth());

            Stats single = runOnPool(
                    pool, new long[]{42}, 4);
            System.out.println(
                    "Single: sum=" + single.sum()
                    + ", nodes=" + single.nodes()
                    + ", leaves=" + single.leaves()
                    + ", depth=" + single.maxDepth());

            try {
                runOnPool(pool, values, 0);
                System.out.println(
                        "Invalid cutoff rejected: false");
            } catch (IllegalArgumentException expected) {
                System.out.println(
                        "Invalid cutoff rejected: true");
            }

            try {
                runParallel(values, 4, 0);
                System.out.println(
                        "Invalid parallelism rejected: false");
            } catch (IllegalArgumentException expected) {
                System.out.println(
                        "Invalid parallelism rejected: true");
            }

            try {
                runOnPool(pool, null, 4);
                System.out.println(
                        "Null array rejected: false");
            } catch (NullPointerException expected) {
                System.out.println(
                        "Null array rejected: true");
            }

            try {
                sequentialSum(new long[]{
                        Long.MAX_VALUE, 1});
                System.out.println(
                        "Overflow detected: false");
            } catch (ArithmeticException expected) {
                System.out.println(
                        "Overflow detected: true");
            }

            System.out.println(
                    "Self-test: " + selfTest(pool)
                    + " cases PASS");
        } finally {
            pool.shutdown();
        }
    }
}
~~~

### 9.1. Biên dịch và chạy

Dùng **JDK 17 trở lên**, lưu đúng tên **SequentialCutoffDemo.java**:

~~~bash
javac -encoding UTF-8 SequentialCutoffDemo.java
java SequentialCutoffDemo
~~~

**Stdout dự kiến:**

~~~text
Array: [5, -2, 7, 1, 3, 0, -4, 8, 2, 6, -1, 9, 4, -3, 10, 1]
Sequential sum: 46
Configured parallelism: 4
Cutoff 1: sum=46, nodes=31, leaves=16, forkCalls=15, depth=4
Cutoff 2: sum=46, nodes=15, leaves=8, forkCalls=7, depth=3
Cutoff 4: sum=46, nodes=7, leaves=4, forkCalls=3, depth=2
Cutoff 8: sum=46, nodes=3, leaves=2, forkCalls=1, depth=1
Cutoff 16: sum=46, nodes=1, leaves=1, forkCalls=0, depth=0
Cutoff 32: sum=46, nodes=1, leaves=1, forkCalls=0, depth=0
Odd n=17 cutoff=4: sum=46, nodes=9, leaves=5, forkCalls=4, depth=3
Empty: sum=0, nodes=1, leaves=1, depth=0
Single: sum=42, nodes=1, leaves=1, depth=0
Invalid cutoff rejected: true
Invalid parallelism rejected: true
Null array rejected: true
Overflow detected: true
Self-test: 500 cases PASS
~~~

### 9.2. Đọc đúng output

**Sequential sum 46:** tổng chính xác của 16 phần tử gồm cả số âm là 46.

**Configured parallelism 4:** cấu hình pool là bốn workers đích, không phải lời cam kết bốn threads thực sự tính toán ở mọi thời điểm.

**Cutoff 1:** có 16 lá, 31 nút đệ quy và 15 fork, depth=4. Mỗi lá chỉ cộng một phần tử, quá ít việc để tự suy ra rằng dùng nhiều workers sẽ nhanh hơn.

**Cutoff 2,4,8:** lần lượt có 8,4,2 lá. Tổng vẫn đúng 46 nhưng số nhánh được fork giảm mạnh.

**Cutoff 16,32:** một lá tuần tự, không sinh nhánh. Bản demo vẫn gọi một root task qua pool; production có thể xử lý trực tiếp khi cả input đã nhỏ hơn cutoff để bỏ cả chi phí root task.

**Odd n=17:** chia thành lá dài 4,4,4,2,3, số lá 5, số nút 9 và maxDepth 3. Không cần mọi lá có kích thước bằng nhau.

**Empty/Single:** base case chứa mảng rỗng trả 0 và mảng một phần tử trả 42, không truy cập ngoài mảng.

**Invalid cutoff:** từ chối ngưỡng 0 để bảo đảm đệ quy kết thúc. **Invalid parallelism:** từ chối pool size không dương. **Null array:** không tự coi null là empty. **Overflow:** phát hiện tổng số nguyên vượt long.

**Self-test 500 cases PASS:** sinh các mảng dài 0..128, giá trị [-1000,1000] và cutoff 1..80; đối chiếu với phép cộng tuần tự và các bất biến cây. Nó là **QA tính đúng**, không phải báo cáo milliseconds hay speedup.

## 10. Vì sao không đếm nút bằng AtomicLong dùng chung?

Nếu mọi leaf và internal node cùng gọi:

~~~java
sharedCounter.incrementAndGet();
~~~

thì nhiều threads có thể tranh chấp một biến atomic và tạo overhead đáng kể. Điều đó làm kết quả benchmark **không phản ánh chi phí của thuật toán không instrumentation**.

Code dùng Stats bất biến:
- Lá trả nodes=1, leaves=1, depth=0.
- Nút trong trả nodes=1+nodes(left)+nodes(right).
- leaves=leaves(left)+leaves(right).
- depth=1+max(depth(left),depth(right)).

Mỗi nhánh tính và trả kết quả riêng, nên **không có shared mutable counter**.

Tuy nhiên số lượng Stats objects vẫn tỷ lệ số nút. Muốn benchmark thuật toán thật, có thể viết RecursiveTask<Long> trả chỉ tổng long, loại bỏ thống kê và so với baseline cùng hợp đồng.

## 11. Vì sao không thể chọn cutoff chỉ từ Big-O?

Mọi cutoff hợp lệ vẫn cho phép tính đúng tổng và có công việc hữu ích Θ(n). Nhưng Big-O ẩn:
- Hằng số tạo RecursiveTask.
- Chi phí phân bổ đối tượng và GC.
- Khác biệt scheduling theo P.
- Memory locality, cache misses và false sharing nếu có ghi.
- Memory bandwidth đã bão hòa.
- Chi phí khởi tạo pool và warm-up JIT.
- Độ lệch giữa các nhánh.
- Tải của các tiến trình khác.

Cùng công thức O(n) hữu ích không cho biết c=64, c=1024 hay c=65536 tối ưu. Muốn chọn theo hiệu năng, **phải benchmark**.

### 11.1. Benchmark đúng phương pháp

1. Viết **bản tuần tự baseline** không có thống kê debug.
2. Warm up JVM để giảm nhiễu JIT.
3. Tái sử dụng pool, tránh tạo pool cho mỗi lần đo.
4. Thử nhiều n, P và c, không chỉ một input.
5. Tính và kiểm kết quả, tránh bị tối ưu bỏ công việc.
6. Chạy nhiều lần, lấy median và phân tán; xem cả p95/p99.
7. Ghi allocations/GC, CPU, memory bandwidth và throughput.
8. Với dịch vụ, thử nhiều request đồng thời để phát hiện oversubscription.
9. Đặt cùng chính sách CPU/turbo/thermal và điều kiện máy tương đương.
10. Tách thời gian **pool setup** khỏi steady-state nếu mục tiêu là throughput, nhưng vẫn đo end-to-end nếu API thực sự phải tạo pool.

**Không bịa con số runtime:** chương trình Java in metrics cấu trúc cây và không giả vờ đã benchmark một máy cụ thể.

### 11.2. Hiệu năng không phải tính đúng

Một cutoff cho speedup thấp hoặc âm vẫn có thể **tính đúng hoàn toàn**. Ngược lại, một chương trình nhanh nhưng dùng shared accumulator không đồng bộ có thể sai ngẫu nhiên do race; tốc độ không sửa lỗi tính đúng.

Bước QA phải tách:
- **Correctness tests:** đối chiếu oracle và bất biến.
- **Performance tests:** thời gian, speedup, resource usage và phương sai trên máy thật.

## 12. Các biến thể cutoff ngoài sum

### 12.1. Parallel merge sort

Một cách dùng cutoff:
- Nếu đoạn dài≤c, sort tuần tự bằng Arrays.sort hoặc một thuật toán base case phù hợp.
- Nếu đoạn lớn hơn c, chia hai nửa, sort song song, join và merge.

Lưu ý: **bước merge lớn có thể vẫn tuần tự** và trở thành đường găng. Cutoff tối ưu cho sum không có lý do toán học để cũng tối ưu cho mergesort, vì merge cost, memory allocation và critical path khác.

### 12.2. Parallel quicksort

Quicksort chia theo pivot. Nếu pivot lệch, một nhánh có thể rất lớn và nhánh kia gần rỗng. Cần:
- Cutoff cho partition nhỏ.
- Pivot/partition tốt, xử lý khóa trùng.
- Chiến lược fork phù hợp kích thước hai nhánh.
- Độ sâu giới hạn hoặc fallback để tránh worst-case.
- Test trên đầu vào đã sorted, reverse và đối kháng.

Ngay cả cutoff tốt cũng không cứu được một partition sai hoặc pivot quá tồi.

### 12.3. Đồ thị, nhánh-cận, tìm kiếm cây

Độ lớn work của subtree có thể thay đổi hàng bậc lớn do branching và pruning. Cutoff theo số node hiện tại hoặc độ sâu chỉ là xấp xỉ.

Có thể dùng:
- Ước lượng kích thước subtree.
- Giới hạn độ sâu tạo tasks.
- Xử lý các nhánh nhỏ trên worker hiện tại.
- Cân bằng tải qua work stealing.
- Kiểm soát shared incumbent và correctness khi cắt nhánh.

### 12.4. Ma trận và xử lý ảnh

Tile size phải cân nhắc:
- Cache locality và vectorization.
- NUMA/memory bandwidth.
- False sharing nếu các workers ghi gần nhau.
- Mức độ song song và kích thước vùng đệm.
- Chi phí mỗi pixel hoặc mỗi ô ma trận.

Cutoff có thể tính bằng số byte, số pixel, work estimate, không nhất thiết là số phần tử của một mảng.

## 13. Trường hợp biên và an toàn dữ liệu

### 13.1. Mảng rỗng và singleton

Mảng rỗng có tổng 0. Với n=0, length≤cutoff nên vòng lặp rỗng và trả Stats(0,1,1,0). Với n=1, chỉ cộng một phần tử. Không có truy cập index âm hoặc vượt to.

### 13.2. Cutoff lớn hơn n

Một lá duy nhất xử lý tuần tự. Mặc dù không có fork nhánh con, demo vẫn gọi một root task. Trong production có thể thêm fast path chạy trực tiếp để tránh overhead của pool cho công việc quá nhỏ.

### 13.3. Ngưỡng 0 hoặc âm

Không hợp lệ. Đối với length=1 và cutoff=0, cách chia mid có thể tạo hai đoạn độ dài 0 và 1; nhánh độ dài 1 tiếp tục bị chia và không tiến tới base case. Phải validate cutoff trước khi invoke.

### 13.4. Mảng bị mutate đồng thời

Những SumTask chỉ **đọc** a. Điều đó an toàn khi không có thread khác sửa a trong lúc xử lý. Nếu có writer đồng thời, kết quả có thể pha trộn giá trị cũ/mới và không tương ứng một snapshot nhất quán. Cần copy, locking hoặc hợp đồng immutable input.

### 13.5. Overflow và dấu phẩy động

Math.addExact ném ArithmeticException nếu một bước tổng vượt long, tránh silent wrap. Nếu bài toán có thể cho tổng rất lớn, dùng BigInteger hoặc định nghĩa modular arithmetic rõ ràng.

Phép cộng double có rounding không associative bit-exact. Thay đổi hình dạng cây có thể thay đổi thứ tự cộng và vài bit cuối, ngay cả khi thuật toán toán học đúng; cần nêu chính sách tolerance và cách cộng nếu tái lập bit-for-bit là yêu cầu.

### 13.6. Oversubscription

Nếu 100 requests đồng thời mỗi request tạo ForkJoinPool(8), có thể tạo quá nhiều worker threads so với cores thực. Quản lý **pool lifecycle và concurrency toàn dịch vụ** quan trọng không kém cutoff trong từng request.

### 13.7. Blocking I/O

Không nên vô tình đưa I/O blocking dài vào hàng nghìn RecursiveTask CPU-bound. Work stealing không tự cứu khi nhiều workers đều chờ I/O; cần thiết kế executor/async hoặc blocking-aware phù hợp.

## 14. Kiểm thử thuật toán và thí nghiệm

### 14.1. Oracle và bất biến

Cho mảng ngắn:
- Tính sum bằng vòng lặp tuần tự.
- Tính với các ngưỡng c khác nhau.
- Kiểm mọi kết quả bằng nhau trong miền không overflow.
- Kiểm nodes=2×leaves−1.
- Kiểm forkCalls=leaves−1.
- Nếu n≤c, kiểm nodes=1, leaves=1, depth=0.
- Kiểm đoạn [from,to) không bỏ/nhân đôi index.
- Chạy nhiều lần để phát hiện shared state/race.

### 14.2. Các ca bắt buộc

- n=0,1,2.
- n=c−1,c,c+1 khi c≥1.
- n=15,16,17 và các ngưỡng 1,2,4,8,16.
- Số âm, số 0, phần tử lặp.
- Cutoff=0 hoặc âm phải từ chối.
- Parallelism≤0 phải từ chối.
- Null input phải từ chối.
- Tổng vượt long phải báo exception.
- P=1,2,4,8 để kiểm tính đúng bất kể cấu hình.
- Input lớn và concurrent requests để đo tài nguyên.

### 14.3. Kiểm tra ước lượng work

Nếu code cho task rất nhỏ dù một leaf chỉ thực hiện một phép cộng, kết quả đúng vẫn có thể chậm. Thử nhiều c, ghi **number of fork calls**, milliseconds và allocations; phân biệt cận lý thuyết với kết quả đo thật.

### 14.4. Từ test sang benchmark

Các property tests không chứng minh hiệu năng, nhưng giúp tin thuật toán trước khi tối ưu. Benchmark cần warm-up, repetitions, machine isolation, baseline và thống kê phân tán; không dùng một lần chạy để tuyên bố ngưỡng tối ưu.

## 15. Lỗi phổ biến

1. **Chia tới từng phần tử** mà không xét overhead tạo task.
2. **Cho rằng một task tương ứng một thread riêng**, nhầm lịch chạy.
3. **Chọn cutoff theo một con số cố định cho mọi thuật toán**.
4. **Ngưỡng quá nhỏ** gây nhiều fork/join, queue operations và GC.
5. **Ngưỡng quá lớn** khiến chỉ còn 1–2 lá, các workers khác rảnh.
6. **Dùng cutoff=0**, làm base case một phần tử không dừng.
7. **Viết length<cutoff nhưng giải thích length≤cutoff**, sai ở biên.
8. **Sai ranh giới đoạn [from,mid) / [mid,to)**, gây lặp/mất phần tử.
9. **Chia mid sai** khiến một nhánh không giảm kích thước.
10. **Fork cả hai nhánh rồi chờ sớm** trong khi có thể compute một nhánh inline.
11. **Join ngay sau fork** trước khi xử lý công việc độc lập.
12. **Dùng biến sum chung không đồng bộ**, tạo data race.
13. **Dùng AtomicLong chung cho instrumentation** làm benchmark bị contention.
14. **Đếm số lá rồi tuyên bố đó là số CPU cores được sử dụng**.
15. **Dùng số fork để kết luận runtime mà không đo**.
16. **Benchmark một lần trước warm-up JIT**, bị nhiễu.
17. **Tạo ForkJoinPool mới trong từng leaf**, phí pool vô ích.
18. **Không so với baseline tuần tự**, chỉ so các cutoff với nhau.
19. **Chỉ benchmark một kích thước n**, bỏ tương tác n/c.
20. **Không kiểm sum với oracle**, tốc độ cao nhưng kết quả có thể sai.
21. **Không phát hiện overflow long**, trả silent modulo.
22. **Giả định double associative bit-exact**, bỏ sai khác rounding.
23. **Mảng bị mutate đồng thời**, input không còn snapshot ổn định.
24. **Cho rằng configured parallelism=P tức luôn có P workers bận**.
25. **Bỏ giới hạn memory bandwidth**, ước lượng speedup phi thực tế.
26. **Cho tác vụ CPU-block I/O lâu**, gây starvation.
27. **Dùng commonPool không xem workload khác**, cạnh tranh tài nguyên.
28. **Nhầm Work và Span**, tối ưu một mặt rồi bỏ mặt kia.
29. **Diễn giải Amdahl như kết quả benchmark**, sai bản chất mô hình.
30. **Giả định quicksort luôn chia cân bằng**, bỏ worst-case.
31. **Áp cutoff cho sum sang mergesort/graph traversal** mà không benchmark lại.
32. **Không kiểm overhead của Stats/logging**, đo nhầm thuật toán.
33. **Không xét n nhỏ hơn cutoff**, vẫn tạo pool/nhiều task không cần.
34. **Tạo quá nhiều pool dưới tải cao**, oversubscription và p99 xấu.
35. **Bắt buộc chia song song dù tuần tự nhanh hơn**, trái mục tiêu tối ưu.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Sequential cutoff là gì?

**Đáp án:** Ngưỡng mà bài toán con đủ nhỏ để xử lý tuần tự thay vì tạo các tác vụ con.

**Câu 2.** Vì sao fork có chi phí?

**Đáp án:** Tạo task object, scheduling, queue/work stealing, join và ảnh hưởng allocation/cache.

**Câu 3.** Bài sum dùng điều kiện nào cho base case?

**Đáp án:** length≤cutoff, với cutoff≥1.

**Câu 4.** Vì sao chỉ fork một trong hai nhánh?

**Đáp án:** Worker hiện tại vẫn có việc để làm, trong khi nhánh còn lại có thể chạy song song, giảm fork/join overhead.

**Câu 5.** Cutoff=1 trên n=16 cho bao nhiêu lá?

**Đáp án:** 16 lá, 31 nút và 15 fork.

**Câu 6.** Cutoff=4 trên n=16 cho bao nhiêu lá?

**Đáp án:** 4 lá, 7 nút, 3 fork, maxDepth=2.

**Câu 7.** Cutoff=16 có tác vụ con được fork không?

**Đáp án:** Không; cả mảng là một lá tuần tự.

**Câu 8.** n=17, c=4 có mấy lá?

**Đáp án:** 5 lá, độ dài lần lượt 4,4,4,2,3.

**Câu 9.** Mọi cutoff trong ví dụ trả sum gì?

**Đáp án:** 46.

**Câu 10.** Work W và Span S khác nhau thế nào?

**Đáp án:** W là tổng công việc; S là đường phụ thuộc dài nhất.

**Câu 11.** Cận dưới thời gian song song trên P processors?

**Đáp án:** \(T_P\ge\max(W/P,S)\).

**Câu 12.** Cutoff quá nhỏ ảnh hưởng gì?

**Đáp án:** Tăng nhiều task/fork/join/GC so với công việc hữu ích.

**Câu 13.** Cutoff quá lớn ảnh hưởng gì?

**Đáp án:** Quá ít lá độc lập, không tận dụng hết workers.

**Câu 14.** Chỉ nhìn n/c có chọn được cutoff tối ưu không?

**Đáp án:** Không; còn chi phí mỗi phần tử, overhead, cache, P và phân phối work.

**Câu 15.** Amdahl s=10%, P=8 cho speedup giới hạn bao nhiêu?

**Đáp án:** Khoảng 4,71 trong mô hình lý tưởng.

**Câu 16.** ForkJoinPool với parallelism=4 có luôn chạy bốn tác vụ không?

**Đáp án:** Không; đó là cấu hình pool, số task chạy thực tế còn tùy scheduler và số tasks sẵn có.

**Câu 17.** Vì sao không dùng shared sum accumulator?

**Đáp án:** Các threads có thể cập nhật cạnh tranh, gây data race và mất phép cộng.

**Câu 18.** Stats bất biến có lợi gì?

**Đáp án:** Không cần global counters đồng bộ; dễ kiểm các bất biến của cây.

**Câu 19.** Vì sao bản Java không in milliseconds?

**Đáp án:** Runtime phụ thuộc máy/JVM/JIT/GC và không thể đưa một stdout thời gian đúng cho mọi môi trường.

**Câu 20.** Vì sao một benchmark phải có warm-up?

**Đáp án:** Tránh nhầm ảnh hưởng JIT, class loading và cache ban đầu với hiệu năng ổn định.

**Câu 21.** Nếu input bị mutate cùng lúc, chuyện gì xảy ra?

**Đáp án:** Kết quả có thể không tương ứng một snapshot và có data race.

**Câu 22.** Math.addExact được dùng để làm gì?

**Đáp án:** Phát hiện long overflow thay vì im lặng trả giá trị đã quấn.

**Câu 23.** Nếu nhiều requests cùng chạy, chỉ chỉnh cutoff có đủ không?

**Đáp án:** Không; còn phải kiểm pool sharing, số workers tổng, RAM và oversubscription.

**Câu 24.** Khi nào giữ xử lý tuần tự là quyết định tốt?

**Đáp án:** Khi bài nhỏ hoặc overhead/giới hạn memory bandwidth lớn hơn lợi ích từ parallelism.

## 17. Bài tập thực hành

**Bài 1 — Bảng cutoff:** chạy mảng n=2^20 với c=16,32,64,…,65536, P=1,2,4,8. Warm up trước khi lấy thời gian, kiểm tổng rồi vẽ median time theo c.

**Bài 2 — Cây tác vụ:** dự đoán nodes/leaves/depth cho n=31 và c=8; đối chiếu với chương trình.

**Bài 3 — Chi phí khác nhau:** thay phép cộng đơn giản bằng một hàm CPU chuyên sâu cho từng phần tử; kiểm cutoff phù hợp có đổi không.

**Bài 4 — Work không đều:** tạo cây mà nhánh trái và phải có thời lượng khác nhau; đề xuất cutoff theo work estimate thay cho length.

**Bài 5 — Mergesort:** dùng Arrays.sort tuần tự khi đoạn nhỏ, ForkJoinTask khi đoạn lớn; phân tích riêng critical path của bước merge.

**Bài 6 — Tải đồng thời:** so một pool được quản lý chung với việc tạo pool cho từng request, đo throughput/RAM/p99.

**Bài 7 — Chứng minh quy nạp:** chứng minh các đoạn [from,mid) và [mid,to) rời nhau và phủ [from,to), nên mỗi phần tử được tính một lần.

**Bài 8 — Instrumentation:** bỏ Stats, dùng RecursiveTask<Long> và benchmark lại; giải thích vì sao kết quả thời gian có thể khác.

## 18. Ghi nhớ

**Chọn ngưỡng xử lý tuần tự thay vì tách thêm tác vụ** là quyết định điều chỉnh **task granularity**. Cutoff nhỏ giúp có nhiều nhánh cho workers nhưng làm tăng chi phí fork/join, scheduling, allocation và GC. Cutoff lớn giảm overhead nhưng có thể để CPU cores rảnh. Đánh đổi tốt nhất phụ thuộc chi phí một đơn vị work, số workers, độ lệch nhánh, cache và memory bandwidth.

Trong Java 17, ForkJoinPool cùng RecursiveTask có thể fork một nhánh, tính nhánh kia inline rồi join. Khi length≤cutoff, xử lý trực tiếp bằng vòng lặp tuần tự. Work/Span giải thích giới hạn lý thuyết; oracle đảm bảo tính đúng; **benchmark đáng tin trên workload thật** mới giúp chọn ngưỡng nhanh và ổn định.

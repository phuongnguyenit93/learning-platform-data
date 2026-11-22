# Tránh tạo quá nhiều tác vụ nhỏ trong Fork/Join của Java

## 1. Mục tiêu bài học

Sau bài học, bạn có thể:

- Giải thích **Fork/Join** và vì sao chiến lược chia để trị (*divide and conquer*) không có nghĩa “càng chia nhỏ càng nhanh”.
- Phân biệt **đơn vị dữ liệu**, **đơn vị tính toán**, **ForkJoinTask** và **platform thread**: một task không đồng nghĩa một thread.
- Hiểu chi phí của **fork(), join(), quản lý hàng đợi, work stealing, cấp phát đối tượng, hợp nhất kết quả**, và lý do tác vụ quá nhỏ khiến overhead lấn át công việc có ích.
- Chọn **sequential cutoff/threshold**, giới hạn độ sâu chia, hoặc **batching/chunking** để số task có ý nghĩa đối với kích cỡ dữ liệu và số worker.
- Dùng mẫu **fork một nhánh, compute trực tiếp nhánh còn lại, join nhánh đã fork**; nhận ra khi nào nên xử lý tuần tự ngay thay vì tạo thêm task.
- Tránh các lỗi như fork vô hạn, quên join, tạo task trên mỗi phần tử, blocking I/O trong ForkJoinPool mà không có chiến lược thích hợp, shared mutable accumulator và benchmark dựa trên một lần chạy.
- Tạo, biên dịch và chạy những ví dụ Java 17+ cho kết quả đúng, có phép đếm task kiểm chứng được; hiểu các giới hạn khi suy luận về hiệu năng thực tế.

Phạm vi là **Fork/Join của Java concurrency nói chung**, không phải các executor hoặc tính năng riêng của Spring. Bài sử dụng các API của JDK 17+ như **ForkJoinPool**, **RecursiveTask**, **ForkJoinTask** và **ExecutorService**.

## 2. Task không phải thread

Một worker có thể xử lý nhiều `ForkJoinTask`. Fork, join, bookkeeping, cấp phát và điều phối hàng đợi đều có chi phí, nên chia tới từng phần tử có thể tệ hơn xử lý một batch tuần tự.

Trọng tâm bài này là **đếm số task sinh ra và giảm overhead** qua threshold, batching, giới hạn độ sâu hoặc fast path. Số task lớn không đồng nghĩa số core chạy tăng tương ứng.
## 3. Vì sao tác vụ quá nhỏ làm Fork/Join chậm?

Giả sử phép cộng một số mất rất ít thời gian. Nếu mỗi số là một RecursiveTask, với một triệu số sẽ có lượng object và thao tác điều phối rất lớn trong khi phép cộng vốn rất rẻ.

Các nguồn overhead quan trọng:

1. **Tạo object task:** mỗi task mang thông tin phạm vi, tham chiếu input, trường completion và có thể bị cấp phát trên heap.
2. **fork và queue:** task được đưa vào cơ chế scheduling; ngay cả khi worker hiện tại tự lấy lại task, vẫn có công việc quản lý.
3. **Work stealing:** worker khác có thể lấy task từ queue của worker đang bận. Đây là cơ chế hữu ích nhưng không miễn phí.
4. **join và đồng bộ completion:** thread cần biết task khác hoàn tất, nhận kết quả và/hoặc phối hợp giúp thực hiện task khác.
5. **Đệ quy và chia dữ liệu:** tính midpoint, gọi hàm, tạo kết quả trung gian, merge.
6. **Cache và memory bandwidth:** nhiều task nhỏ cùng đọc dữ liệu, cập nhật metadata, hoặc tranh cache line có thể làm kém hiệu quả.
7. **Garbage collection:** nếu task object được tạo hàng loạt, GC và pressure lên heap có thể tăng.
8. **Contention khi dùng shared counters:** nếu mọi task cập nhật một AtomicLong chung để ghi kết quả, điểm nóng có thể lấn át lợi ích chia việc.

**Điểm mấu chốt:** lợi ích song song chỉ thắng khi **lượng việc hữu ích trong từng task đủ lớn** so với các chi phí trên và khi máy còn tài nguyên để chạy song song.

### Không phải mọi chi phí đều giống nhau

Một task tính tổng 8 số int rất khác task mã hóa 8 khối dữ liệu lớn, giải nén một ảnh hoặc tính toán ma trận tốn CPU. Vì thế **threshold=1000** không phải hằng số đúng cho mọi thuật toán.

Độ nặng của mỗi phần tử, tính đồng đều dữ liệu, số lõi CPU hiệu dụng, độ trễ bộ nhớ, cấu trúc tree và JVM/JIT đều ảnh hưởng điểm cân bằng.

## 4. Cỡ hạt (granularity) là quyết định thiết kế

**Task granularity** mô tả lượng công việc được gom trong một đơn vị task. Hai trường hợp cực đoan đều có thể bất lợi:

~~~text
Task quá nhỏ:
   1 | 1 | 1 | 1 | 1 | 1 | ... hàng triệu task
   Quản lý task và join chiếm tỷ lệ lớn.

Task quá lớn:
   [          1 task xử lý tất cả          ]
   Những worker khác không có cơ hội làm phần độc lập.

Cỡ hạt cân đối:
   [chunk A] [chunk B] [chunk C] [chunk D] ...
   Có song song, mỗi chunk đủ công việc hữu ích.
~~~

Tác vụ quá lớn có thể gây **load imbalance**, ví dụ một worker xử lý 90% dữ liệu trong khi worker khác rảnh. Tác vụ quá nhỏ có thể gây **task explosion**. Mục tiêu không phải tối thiểu hóa tuyệt đối số task, mà là tối ưu tổng thời gian/throughput/độ trễ dưới những điều kiện được đo.

### Mô hình chi phí trực giác

Có thể hình dung:

~~~text
Tổng thời gian ≈ công việc hữu ích được phân phối
              + chi phí tạo/sắp xếp task
              + chi phí join/hợp nhất
              + chờ tranh chấp và mất cân bằng
              + ảnh hưởng cache, GC và scheduling
~~~

Đây là mô hình giải thích, **không phải công thức dự đoán thời gian chính xác**. Khi task nhỏ dần, lượng công việc hữu ích trên một task giảm nhưng số task và các chi phí đi kèm có thể tăng rất nhanh.

Không được cộng thời gian CPU của mọi thread rồi xem đó là wall-clock elapsed time. Với benchmark cần phân biệt **throughput, CPU time và wall-clock latency**.

## 5. Sequential threshold: ngừng chia khi đoạn đã đủ nhỏ

Giải pháp cơ bản nhất là định nghĩa **ngưỡng tuần tự** (*sequential cutoff*):

~~~java
// Mảnh code minh họa trong compute() của RecursiveTask.
int length = end - start;

if (length <= threshold) {
    return sequentialSum(data, start, end);
}

// Chỉ chia tiếp khi phần việc còn đủ lớn.
~~~

Code này là mảnh logic trong một class thực tế, không phải chương trình độc lập. **threshold** là kích cỡ đoạn nhỏ nhất đáng xử lý tuần tự; **không phải số thread**, **không phải thời gian ngủ**, cũng không phải lời hứa có đúng threshold task.

### Vì sao ngưỡng tốt hơn chia tới từng phần tử?

Với đoạn N=1024 và thuật toán chẻ đôi cân bằng:

- Nếu **threshold=1**, có **1024 leaf task** cho từng phần tử và **1023 internal task**: tổng cộng **2047 lời compute() cho 2047 node**.
- Nếu **threshold=64**, mỗi leaf xử lý **64 phần tử tuần tự**. Có **16 leaf task** và **15 internal task**: tổng **31 node**.
- Kết quả phép cộng vẫn y hệt: tổng từ 1 đến 1024 là **524800**.
- Số node giảm từ 2047 xuống 31, tức chỉ khoảng **1/66** số node ban đầu.

Những con số trên đúng cho **N=1024 là lũy thừa của hai** và cây chia đôi tới đúng cutoff. Với N bất kỳ và điều kiện dừng khác, số node có thể khác; không khẳng định một công thức chính xác chung cho mọi dữ liệu.

**Ít task hơn không tự chứng minh chạy nhanh hơn**: threshold=64 có thể tốt hơn với phép cộng, nhưng vẫn phải đo trên workload thật. Dữ liệu lệch hoặc phép tính mỗi phần tử rất nặng có thể cần threshold khác.

## 6. Ví dụ 1: đếm chính xác số task theo threshold

Ví dụ sau tạo pool 4 worker, tính tổng 1..1024 bằng RecursiveTask. Mỗi khi compute() được thực hiện, một AtomicInteger dùng **chỉ để quan sát** tăng lên. Kết quả tổng **không** được lưu trong shared mutable counter; mỗi task trả kết quả lên cây join.

Tệp **ForkJoinGranularityDemo.java**:

~~~java
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveTask;
import java.util.concurrent.atomic.AtomicInteger;

public class ForkJoinGranularityDemo {
    static final class SumTask extends RecursiveTask<Long> {
        private final int[] data;
        private final int start;
        private final int end;
        private final int threshold;
        private final AtomicInteger nodes;

        SumTask(int[] data, int start, int end,
                int threshold, AtomicInteger nodes) {
            this.data = data;
            this.start = start;
            this.end = end;
            this.threshold = threshold;
            this.nodes = nodes;
        }

        @Override
        protected Long compute() {
            nodes.incrementAndGet();

            if (end - start <= threshold) {
                long total = 0;
                for (int i = start; i < end; i++) {
                    total += data[i];
                }
                return total;
            }

            int middle = start + (end - start) / 2;
            SumTask left = new SumTask(
                    data, start, middle, threshold, nodes);
            SumTask right = new SumTask(
                    data, middle, end, threshold, nodes);

            left.fork();
            long rightTotal = right.compute();
            long leftTotal = left.join();
            return leftTotal + rightTotal;
        }
    }

    private static void runCase(
            ForkJoinPool pool, int[] data, int threshold) {
        AtomicInteger nodes = new AtomicInteger();
        long sum = pool.invoke(new SumTask(
                data, 0, data.length, threshold, nodes));

        System.out.println("threshold = " + threshold);
        System.out.println("sum = " + sum);
        System.out.println("nodes = " + nodes.get());
    }

    public static void main(String[] args) {
        int[] data = new int[1024];
        for (int i = 0; i < data.length; i++) {
            data[i] = i + 1;
        }

        ForkJoinPool pool = new ForkJoinPool(4);
        try {
            runCase(pool, data, 1);
            runCase(pool, data, 64);
        } finally {
            pool.shutdown();
        }
    }
}
~~~

Biên dịch/chạy bằng Java 17+:

~~~bash
javac -encoding UTF-8 ForkJoinGranularityDemo.java
java ForkJoinGranularityDemo
~~~

Stdout:

~~~text
threshold = 1
sum = 524800
nodes = 2047
threshold = 64
sum = 524800
nodes = 31
~~~

**Giải thích chi tiết:**

1. Mỗi lần compute chạy, nodes tăng một lần. Task đệ quy cũng được tính, nên nodes là tổng **leaf + internal**.
2. Ngưỡng 1 khiến cây chia đến các đoạn chứa 1 phần tử. Vì có 1024 phần tử và chia đôi hoàn toàn, cây nhị phân đầy đủ có 2047 node.
3. Ngưỡng 64 khiến mỗi leaf duyệt tuần tự 64 phần tử: 16 leaf, 15 internal node, tổng 31.
4. Hai bài toán có **cùng dữ liệu** và **cùng kết quả**; biến duy nhất là kích cỡ task.
5. **AtomicInteger** chỉ dùng trong ví dụ để đếm node an toàn. Trong code tối ưu hiệu năng, bỏ metric cấp-node hoặc dùng phương thức đo ít gây contention hơn vì việc đếm atomic cũng là overhead.
6. Thứ tự thực hiện các node có thể khác nhau, nhưng **cấu trúc cây và số node** cố định theo N/threshold. Vì thế stdout xác định.

**Bài học:** tạo ít node hơn thường giảm chi phí quản lý. Nhưng chương trình này chủ yếu **chứng minh cấu trúc và số task**, không phải benchmark chứng minh một threshold nhanh hơn threshold khác.

### Tại sao dùng long thay vì int cho kết quả?

Tổng nhiều int có thể tràn **int**. Dùng **long** cho accumulator giúp ví dụ tránh tràn ở kích cỡ dữ liệu được chọn. Với bài toán thực, vẫn cần cân nhắc giới hạn long và đặc tả overflow.

## 7. Mẫu đúng: fork một nhánh, compute nhánh kia, join

Một idiom Fork/Join phổ biến:

~~~java
// Mã minh họa khi left/right là hai RecursiveTask<Long>.
left.fork();
long rightValue = right.compute();
long leftValue = left.join();
return leftValue + rightValue;
~~~

Ý tưởng:

- **fork(left)** tạo cơ hội cho worker khác lấy left.
- Thread hiện tại **tiếp tục xử lý right trực tiếp**, không cần enqueue thêm một task mà chính nó có thể làm.
- **join(left)** lấy kết quả sau khi left hoàn tất. Trong quá trình đợi, worker Fork/Join có thể tham gia thực hiện công việc khác theo cơ chế của pool.
- Chỉ **hợp nhất kết quả khi cả hai phía hoàn tất**.

### Vì sao không fork cả hai nhánh vô điều kiện?

~~~java
// Có thể đúng về kết quả nhưng tạo thêm công việc scheduling:
left.fork();
right.fork();
return left.join() + right.join();
~~~

Đoạn này đôi khi vẫn đúng theo hợp đồng, nhưng trong nhiều thuật toán binary divide-and-conquer, fork cả hai làm tăng số lần enqueue và khó tận dụng worker hiện tại cho một nhánh ngay lập tức. **Fork một nhánh, compute nhánh còn lại** thường là điểm khởi đầu tốt và được dễ dàng kiểm tra.

**Không nhầm compute() với submit một task mới:** gọi right.compute() **chạy trực tiếp** logic của right trên thread hiện tại. Nó vẫn là một node trong cây về mặt thuật toán, nhưng không cần được lên lịch qua fork ở lượt ấy.

### Không quên join

Nếu fork một task rồi trả kết quả của nhánh kia ngay mà **không join**, parent có thể xem là xong khi nhánh con vẫn chạy. Kết quả tổng thiếu phần việc hoặc code có thể truy cập dữ liệu chưa hoàn tất.

Phải xác định **điểm hoàn tất** của tất cả task con và quan hệ dữ liệu trước khi publish result.

## 8. Ví dụ 2: chặn sự bùng nổ bằng giới hạn độ sâu

Threshold theo số phần tử không phải công cụ duy nhất. Khi bài toán có kích thước phân đoạn khó đo hoặc chứa dữ liệu rất lệch, có thể bổ sung **maxDepth** để hạn chế việc tách cây.

Ví dụ N=1024, chia đôi, **maxDepth=3** tính từ root ở depth 0. Có tối đa 8 leaf (depth 3) và 15 node. Mỗi leaf trong bài toán cân bằng chứa 128 phần tử.

Tệp **ForkJoinDepthCapDemo.java**:

~~~java
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveTask;
import java.util.concurrent.atomic.AtomicInteger;

public class ForkJoinDepthCapDemo {
    static final class Task extends RecursiveTask<Long> {
        private final int[] data;
        private final int start;
        private final int end;
        private final int depth;
        private final int maxDepth;
        private final AtomicInteger nodes;

        Task(int[] data, int start, int end,
             int depth, int maxDepth, AtomicInteger nodes) {
            this.data = data;
            this.start = start;
            this.end = end;
            this.depth = depth;
            this.maxDepth = maxDepth;
            this.nodes = nodes;
        }

        @Override
        protected Long compute() {
            nodes.incrementAndGet();

            if (end - start <= 1 || depth >= maxDepth) {
                long sum = 0;
                for (int i = start; i < end; i++) {
                    sum += data[i];
                }
                return sum;
            }

            int middle = start + (end - start) / 2;
            Task left = new Task(
                    data, start, middle,
                    depth + 1, maxDepth, nodes);
            Task right = new Task(
                    data, middle, end,
                    depth + 1, maxDepth, nodes);

            left.fork();
            long r = right.compute();
            return left.join() + r;
        }
    }

    public static void main(String[] args) {
        int[] data = new int[1024];
        for (int i = 0; i < data.length; i++) {
            data[i] = i + 1;
        }

        AtomicInteger nodes = new AtomicInteger();
        ForkJoinPool pool = new ForkJoinPool(4);
        try {
            long sum = pool.invoke(new Task(
                    data, 0, data.length, 0, 3, nodes));

            System.out.println("sum = " + sum);
            System.out.println("nodes = " + nodes.get());
            System.out.println("leaves at depth 3 = 8");
        } finally {
            pool.shutdown();
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 ForkJoinDepthCapDemo.java
java ForkJoinDepthCapDemo
~~~

Stdout:

~~~text
sum = 524800
nodes = 15
leaves at depth 3 = 8
~~~

**Giải thích:**

- Root ở depth 0, tách thành 2 node depth 1, rồi 4 node depth 2, rồi 8 node depth 3.
- Ở depth 3, compute() **ngừng fork**, chuyển sang vòng for tuần tự, tổng 8 leaf.
- Cây có 1+2+4+8 = 15 node; số node cố định cho N và maxDepth đã chọn.
- Ví dụ dùng AtomicInteger để minh họa chi phí cấu trúc, không nên cập nhật metric toàn cục trên từng node trong code hiệu năng cao.

### Max depth có thay thế threshold hoàn toàn?

Không. Nếu N cực lớn, 8 leaf vẫn có thể quá nặng so với tài nguyên; nếu N rất nhỏ, 8 leaf có thể quá nhỏ. Độ sâu là **rào bảo vệ thứ hai** hữu ích nhưng không tự chọn granularity tối ưu.

Một chính sách thực tế có thể dừng khi:

~~~text
rangeSize <= threshold
       HOẶC
depth >= maxDepth
       HOẶC
chi phí ước lượng của đoạn quá nhỏ để fork
~~~

**Mỗi predicate phải có ngữ nghĩa rõ ràng.** Nếu chỉ thấy maxDepth lớn hơn 0 rồi chia mọi đoạn, cần vẫn bảo vệ trường hợp đoạn rỗng hoặc chỉ có một phần tử để tránh đệ quy vô hạn.

## 9. Dựa trên số worker: đừng hiểu sai parallelism

**ForkJoinPool.getParallelism()** báo mức parallelism mục tiêu/cấu hình của pool. Có thể dùng nó như một **đầu vào** khi chọn số chunk, nhưng không bảo đảm có đúng P CPU khả dụng mọi lúc.

Một công thức gợi ý ban đầu:

~~~text
P = max(1, pool.getParallelism())
targetChunks = P * 4          (ví dụ hệ số 4 là heuristic)
chunkSize = max(minChunk, ceil(N / targetChunks))
~~~

Cách chọn này nhắm đến một số phần việc **nhiều hơn P nhưng không vô hạn**. Hệ số 4 không phải quy tắc của JDK: tùy workload có thể muốn P, 2P, 8P hoặc giá trị khác. **minChunk** phải căn cứ lượng công việc hữu ích mỗi phần tử.

### Điều chỉnh theo trọng lượng công việc

Nếu mỗi phần tử thực hiện nhiều phép tính CPU đắt đỏ, chunk nhỏ hơn có thể vẫn đủ lớn để bù overhead. Nếu mỗi phần tử chỉ là một phép cộng, chunk có thể cần lớn hơn rất nhiều. Nếu phân đoạn không cân bằng về khối lượng, hãy ước lượng **work units** chứ không chỉ length.

**Không khẳng định getParallelism() là số CPU thực**: container quotas, worker đang bận, common pool, GC, memory bandwidth và hệ thống khác có thể giảm parallelism hữu ích.

### Nên đo cả ngưỡng thấp và cao

Với cùng input và thuật toán, thử nhiều threshold theo lũy thừa 2 như 256, 512, 1024, 2048, 4096... nhưng đây chỉ là **cách quét tham số**; không có bảo đảm một số trong danh sách là tối ưu.

Khi đo, cần so với **phiên bản tuần tự tốt**; có những phép tính quá nhẹ khiến Fork/Join thua tuần tự ở mọi threshold hữu ích.

## 10. Batching: nhiều phần tử cho một task

Có bài toán vốn không cần cây đệ quy sâu. Nếu chỉ cần thực hiện phép biến đổi độc lập trên các chunk, ta có thể **tạo một số Callable theo batch**, submit vào ForkJoinPool (vốn triển khai ExecutorService) và gom kết quả qua Future.

Ưu điểm:

- Điều khiển trực tiếp **số task được gửi**, ví dụ 8 batch thay vì 1024 phần tử.
- Dễ giới hạn độ lớn batch và xác định ranh giới dữ liệu.
- Không cần chuỗi RecursiveTask lồng nhau nếu bài toán chỉ là map/reduce độc lập theo chunk.
- Có thể theo dõi kết quả, lỗi, cancellation của từng batch qua Future.

Nhược điểm:

- Nếu batch không đồng đều, một batch lớn có thể giữ worker lâu trong khi các batch khác đã xong.
- Nếu số batch ít hơn số worker, có thể không khai thác hết song song.
- Nếu giữ hàng nghìn Future và hàng triệu batch, chính batching lại tạo overhead mới.
- Sử dụng pool không làm side effect trên shared mutable object tự động thread-safe.

## 11. Ví dụ 3: gom 1024 phần tử thành 8 batch

Tệp **ForkJoinBatchingDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.Future;

public class ForkJoinBatchingDemo {
    public static void main(String[] args) throws Exception {
        int[] data = new int[1024];
        for (int i = 0; i < data.length; i++) {
            data[i] = i + 1;
        }

        int batchSize = 128;
        List<Callable<Long>> batches = new ArrayList<>();

        for (int begin = 0; begin < data.length;
                begin += batchSize) {
            final int from = begin;
            final int to = Math.min(data.length, begin + batchSize);

            batches.add(() -> {
                long subtotal = 0;
                for (int i = from; i < to; i++) {
                    subtotal += data[i];
                }
                return subtotal;
            });
        }

        ForkJoinPool pool = new ForkJoinPool(4);
        try {
            List<Future<Long>> futures = pool.invokeAll(batches);

            long total = 0;
            for (Future<Long> future : futures) {
                total += future.get();
            }

            System.out.println("batches = " + batches.size());
            System.out.println("sum = " + total);
        } finally {
            pool.shutdown();
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 ForkJoinBatchingDemo.java
java ForkJoinBatchingDemo
~~~

Stdout:

~~~text
batches = 8
sum = 524800
~~~

**Vì sao đúng?**

1. N=1024, mỗi batch chứa 128 phần tử, nên có **8 Callable**.
2. Mỗi Callable chỉ đọc một phạm vi riêng của mảng và trả subtotal; không cập nhật một accumulator dùng chung.
3. **pool.invokeAll(batches)** theo giao diện ExecutorService đợi tất cả task hoàn tất; mỗi Future tiếp tục cho phép get() nhận kết quả hoặc exception.
4. Tổng các đoạn không chồng lấn, phủ chính xác 0..1023, nên kết quả luôn là tổng 1..1024.
5. Số batch được cố định bởi code, không tùy lịch CPU; stdout xác định.

**Phân biệt quan trọng:** đây là cách **batching bằng ExecutorService API trên ForkJoinPool**, không phải cây fork/join đệ quy. Nó chứng minh cùng nguyên tắc giảm granularity quá nhỏ bằng cách gom công việc. Nếu workload là cây chia để trị thực sự, RecursiveTask/RecursiveAction vẫn tự nhiên hơn.

### Khi nào dùng batching thay vì recursion?

- Đã biết các đoạn độc lập tương đối đồng đều.
- Dữ liệu dạng array/file chunk/range có ranh giới rõ.
- Kết quả có thể reduce ở cuối mà không cần task con phát sinh động.
- Muốn dễ kiểm soát số task được nhận và cancellation theo batch.

Nếu bài toán phát sinh nhánh **không biết trước** (ví dụ duyệt cây, tìm kiếm đệ quy, phân hoạch biến thiên), Fork/Join recursive có thể phù hợp hơn.

## 12. Tránh một task trên mỗi phần tử trong stream xử lý

Một anti-pattern phổ biến là:

~~~java
// Mã minh họa lỗi granularity; pool và items giả định đã có.
for (Item item : items) {
    pool.submit(() -> process(item));
}
~~~

Nếu items chứa hàng triệu phần tử và process(item) chỉ là phép tính rất nhỏ, mỗi phần tử bị bọc trong một Runnable/Callable và một cơ chế scheduling. Ngoài overhead, danh sách Future nếu lưu hết cũng có thể chiếm nhiều bộ nhớ.

Các hướng thay thế:

1. Chia danh sách thành **range/chunk** phù hợp, mỗi task duyệt nhiều item.
2. Nếu mỗi item rất nhẹ và có thể xử lý một luồng đủ nhanh, dùng **vòng lặp tuần tự**.
3. Nếu mỗi item có I/O hoặc chờ lâu, ForkJoinPool không chắc là mô hình worker thích hợp; cần thiết kế concurrency và giới hạn tài nguyên riêng.
4. Nếu task cần viết vào cùng map, counter hay database, phải xét synchronization/idempotency, không phải chỉ giảm số lượng task.

Đoạn mã trên không độc lập: **Item**, **items**, **pool**, **process()** là các thành phần giả định.

## 13. Không tạo task chỉ để bọc một vòng lặp quá ngắn

ForkJoinPool.invoke(new Task(...)) bản thân nó cũng có chi phí. Nếu toàn bộ input **nhỏ hơn threshold**, một API ứng dụng có thể **xử lý tuần tự ngay tại caller** thay vì luôn tạo root task.

Ví dụ:

~~~java
// Minh họa trong một phương thức có data, pool và threshold.
if (data.length <= threshold) {
    return sequentialSum(data, 0, data.length);
}
return pool.invoke(new SumTask(data, 0, data.length, threshold));
~~~

Đây là phần thân minh họa của một phương thức trả long. **SumTask** là lớp giả định của chính chương trình và cần có constructor phù hợp; không biên dịch độc lập.

### Vì sao có fast path?

- Không tạo root task cho input quá nhỏ.
- Không bắt caller chờ pool chỉ để tính vài phần tử.
- Tránh tác động đến pool có thể đang xử lý việc khác.
- Hành vi vẫn đúng vì cùng thuật toán tuần tự tính kết quả.

**Cần phân biệt hợp đồng API:** nếu method của bạn hứa trả **Future bất đồng bộ** chứ không trả kết quả trực tiếp, không tự ý biến đường nhỏ thành synchronous mà thay đổi tính chất giao diện; thay vào đó có thể trả một completed future hoặc thiết kế API rõ ràng. Tối ưu granularity không được phá contract caller.

## 14. Ví dụ 4: tổng hợp một snapshot kết quả, không tranh accumulator chung

Một lỗi khác không nằm ở số task mà ở **cách kết quả của task con được hợp nhất**. Nếu mọi task cập nhật một AtomicLong toàn cục, kết quả có thể đúng nhưng làm tăng contention.

Thay vào đó, từng leaf trả kết quả bất biến; parent kết hợp sau khi join. Ví dụ trạng thái gồm **sum và count**.

Tệp **ForkJoinStatsDemo.java**:

~~~java
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveTask;

public class ForkJoinStatsDemo {
    record Stats(long sum, int count) {}

    static final class StatsTask extends RecursiveTask<Stats> {
        private final int[] data;
        private final int from;
        private final int to;
        private final int threshold;

        StatsTask(int[] data, int from, int to, int threshold) {
            this.data = data;
            this.from = from;
            this.to = to;
            this.threshold = threshold;
        }

        @Override
        protected Stats compute() {
            if (to - from <= threshold) {
                long sum = 0;
                for (int i = from; i < to; i++) {
                    sum += data[i];
                }
                return new Stats(sum, to - from);
            }

            int mid = from + (to - from) / 2;
            StatsTask left =
                    new StatsTask(data, from, mid, threshold);
            StatsTask right =
                    new StatsTask(data, mid, to, threshold);

            left.fork();
            Stats b = right.compute();
            Stats a = left.join();

            return new Stats(
                    a.sum() + b.sum(),
                    a.count() + b.count()
            );
        }
    }

    public static void main(String[] args) {
        int[] data = new int[512];
        for (int i = 0; i < data.length; i++) {
            data[i] = i + 1;
        }

        ForkJoinPool pool = new ForkJoinPool(4);
        try {
            Stats result =
                    pool.invoke(new StatsTask(data, 0, data.length, 64));

            System.out.println("sum = " + result.sum());
            System.out.println("count = " + result.count());
            System.out.println("average = "
                    + (result.sum() / result.count()));
        } finally {
            pool.shutdown();
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 ForkJoinStatsDemo.java
java ForkJoinStatsDemo
~~~

Stdout:

~~~text
sum = 131328
count = 512
average = 256
~~~

**Giải thích:**

- Mỗi leaf xử lý tối đa 64 phần tử tuần tự và trả **Stats immutable record**.
- Parent nhận hai Stats đã hoàn tất, cộng sum và count thành một Stats mới.
- Không có shared mutable accumulator giữa các task; không cần lock hoặc AtomicLong cho kết quả chính.
- **join** thiết lập điểm completion để parent dùng kết quả hai nhánh.
- Tổng từ 1 đến 512 là 131328; phép chia nguyên cho 512 trả 256 (giá trị trung bình thực là 256,5, nhưng phép chia **long / int** trong Java lấy phần nguyên).

**Cẩn thận:** tạo một record cho mỗi internal task cũng có chi phí allocation. Nếu kết quả chỉ là một số, hãy trả Long như ví dụ đầu; dùng object kết quả nhiều trường khi invariant/thiết kế thực sự cần. Mục tiêu là **giảm tranh chấp và giữ kết quả đúng**, không phải tối đa hóa số object.

## 15. Một số chiến lược ngưỡng thực tế

### 15.1. Ngưỡng cố định theo dữ liệu

~~~text
if (length <= THRESHOLD) {
    computeSequentially();
} else {
    splitAndJoin();
}
~~~

Dễ hiểu, dễ benchmark. Phù hợp khi chi phí mỗi phần tử tương đối đồng đều.

### 15.2. Ngưỡng theo estimated work

Có thuật toán mà hai phân đoạn cùng length nhưng chi phí rất khác. Ví dụ một node chứa chuỗi văn bản ngắn còn node khác chứa ảnh lớn; threshold theo số node có thể gây lệch.

Có thể định nghĩa **estimatedWork(range)** dựa trên kích cỡ byte, số phép tính ước lượng hoặc trọng số domain. Dừng chia khi chi phí dự kiến quá nhỏ.

**Tránh tính estimatedWork đắt hơn chính việc xử lý**. Nếu phải quét toàn đoạn để quyết định chia rồi lại quét đoạn để xử lý, overhead ước lượng có thể hủy lợi ích.

### 15.3. Giới hạn độ sâu

Cố định maxDepth để ngăn cây task tăng không kiểm soát. Dùng cùng ngưỡng theo dữ liệu để không chia đoạn cực nhỏ.

### 15.4. Chia một nhánh, xử lý nhánh còn lại

Giữ ít task queued hơn trong khi vẫn có work stealing. Đây là idiom cơ bản, không đảm bảo mọi workload đều tối ưu.

### 15.5. Batching đầu vào

Chia thành số chunk hữu hạn và gửi task theo batch. Dễ kiểm soát số lượng Future và tránh overload trên queue.

### 15.6. Giảm task khi pool đã có quá nhiều công việc

Có thể dựa vào một số tín hiệu nội bộ/heuristic như **ForkJoinTask.getSurplusQueuedTaskCount()** trong code đang chạy ở worker để cân nhắc không fork thêm. Đây là **gợi ý phụ thuộc trạng thái tức thời**, không phải chứng minh đúng đắn và không nên là cơ chế duy nhất quyết định tính kết thúc của thuật toán.

Một chương trình dễ bảo trì thường bắt đầu bằng **cutoff đơn giản**, sau đó chỉ thêm adaptive logic nếu benchmark và profiling cho thấy rõ lợi ích.

## 16. Cỡ hạt, load balancing và work stealing

**Work stealing** hỗ trợ cân bằng tải: worker rảnh có thể tìm task ở worker khác. Tuy nhiên work stealing chỉ hữu ích khi còn **công việc có thể lấy**.

- **Quá ít task:** một worker có thể giữ phần lớn công việc, worker khác rảnh.
- **Quá nhiều task rất nhỏ:** worker dành tỷ lệ lớn thời gian quản lý task thay vì tính toán.
- **Các task có thời lượng rất lệch:** vài task cuối rất nặng có thể kéo dài thời gian hoàn tất, dù phần lớn worker đã rảnh.
- **Chia tương đối cân đối:** tăng cơ hội phân phối đều khi mỗi task đủ lớn.

### Nhánh bất cân bằng

Giả sử 99% công việc nằm ở nhánh trái và 1% ở nhánh phải. Chỉ chia một lần rồi giao hai task có thể vẫn khiến một worker bận rất lâu. Có thể tiếp tục chia nhánh nặng hoặc dùng work estimate để quyết định. Nhưng nếu nhánh 99% vốn có nhiều subtask nhỏ hơn chi phí scheduling, chia thêm lại không hiệu quả.

**Mục tiêu là vừa đủ việc song song và cân đối**, không phải chỉ giảm số task về mức thấp nhất.

## 17. Tránh shared mutable accumulator

Anti-pattern:

~~~java
// Mã minh họa: mỗi leaf cập nhật chung AtomicLong.
sharedTotal.addAndGet(localSum);
~~~

Nếu quá nhiều leaf cùng update, tất cả tranh một điểm nóng. Dù AtomicLong giúp tránh lost update, mỗi lần update vẫn tạo contention. Với reduction có tính kết hợp như sum/min/max, hãy **trả kết quả cục bộ rồi join** thay vì bắt mọi leaf cạnh tranh một biến.

Đối với những phép reduce **không kết hợp** hoặc yêu cầu thứ tự (ví dụ nối chuỗi theo thứ tự, các phép toán floating-point cần reproducibility), không tự giả định việc đổi cây hợp nhất giữ nguyên kết quả.

### Floating-point không kết hợp hoàn toàn

Trong toán học lý tưởng, (a+b)+c = a+(b+c). Nhưng với số thực IEEE 754, thứ tự cộng có thể thay đổi sai số làm tròn:

~~~text
(a + b) + c
a + (b + c)
=> có thể khác bit kết quả vì rounding
~~~

Fork/Join có thể đổi **thứ tự reduction** so với vòng lặp tuần tự; hãy đặt yêu cầu tolerance, reproducibility hoặc thuật toán cộng bù thích hợp. Không khẳng định kết quả double luôn bitwise bằng nhau chỉ vì dùng cùng input.

### Cấu trúc dữ liệu chia sẻ

Nếu các task con ghi vào **các đoạn không giao nhau** của cùng mảng, có thể không cần khóa trên từng phần tử nếu chứng minh rõ ranh giới và không có tác vụ nào đọc phần dữ liệu đang viết khi chưa hoàn tất. Nếu task con cập nhật **cùng vị trí** hoặc cùng map mutable, phải dùng cơ chế đồng bộ phù hợp.

**“Đều chạy trong ForkJoinPool” không tự biến code thành thread-safe.**

## 18. Blocking I/O trong ForkJoinPool: vấn đề khác granularity

ForkJoinPool chủ yếu được thiết kế để khai thác những tác vụ có thể chia và phối hợp với work stealing. Nếu các task làm **blocking I/O dài** hoặc giữ lock chờ tài nguyên ngoài, worker có thể bị chiếm và những task khác chờ lâu.

Ví dụ rủi ro:

~~~java
// Mã minh họa bên trong compute() (không phải chương trình đầy đủ):
socket.read(buffer);  // Có thể chặn vì mạng.
~~~

ForkJoinPool không có phép màu tự tạo đủ worker cho mọi loại blocking. Một số kiểu chờ được runtime biết đến (như join) có hỗ trợ riêng; với blocking không do ForkJoinPool quản lý, có thể xem xét **ForkJoinPool.managedBlock(ManagedBlocker)** khi thật sự phù hợp, hoặc tách công việc blocking sang mô hình khác.

### ManagedBlocker không thay cho thiết kế concurrency

**ForkJoinPool.managedBlock(...)** cho phép thông báo một thao tác blocking có thể kéo dài, giúp pool có cơ hội điều chỉnh hoạt động worker trong các điều kiện thích hợp. Tuy nhiên:

- Không bảo đảm số thread tăng vô hạn hoặc luôn bù được worker.
- Không làm I/O tự timeout/cancel.
- Không thay transaction, ownership hoặc resource limits.
- Không phù hợp để bọc mọi phép toán CPU ngắn.
- Cần implement đúng hai phương thức **isReleasable()** và **block()** nếu dùng ManagedBlocker tùy chỉnh.

Nhiều hệ thống chọn **pool riêng cho blocking I/O** và ForkJoinPool cho divide-and-conquer CPU-bound. Với Java 17, việc tạo cached platform threads không giới hạn cũng có rủi ro; phải có quota/backpressure phù hợp.

### Không chờ task phụ thuộc vào worker bị chiếm

Nếu một task giữ một khóa hoặc đang chiếm toàn bộ worker rồi chờ task phụ cần chính tài nguyên đó, hệ thống có thể tự tạo **thread-starvation deadlock**. Ngưỡng task đúng không sửa được dependency cycle. Cần phân tích thứ tự khóa, chờ kết quả và số worker.

## 19. ForkJoinPool.commonPool() và pool riêng

**ForkJoinPool.commonPool()** là pool dùng chung trong JVM và có thể được sử dụng bởi những API/lời gọi khác, trong đó có nhiều trường hợp của **parallel streams** hoặc **CompletableFuture** khi không có executor chỉ định.

Ưu điểm: tái sử dụng pool có sẵn, không cần tạo/shutdown pool riêng. Rủi ro:

- Một tác vụ quá nặng hoặc blocking có thể ảnh hưởng workload không liên quan đang dùng pool chung.
- Bạn không tự kiểm soát chính xác mọi hành vi của code thư viện trong pool chung.
- Benchmark trên common pool có thể nhiễu bởi hoạt động khác.
- Không nên gọi shutdown() để “dọn” common pool; đó là pool chia sẻ mà lifecycle thuộc runtime.

**Pool riêng** như **new ForkJoinPool(4)** giúp thử nghiệm một mức parallelism rõ ràng và cô lập tương đối workload. Nhưng tạo nhiều pool riêng cũng tạo thêm worker/memory và overhead; không phải cứ tách mọi request thành một pool mới sẽ tốt.

### Không tạo pool cho mỗi request

~~~java
// Anti-pattern minh họa:
ForkJoinPool pool = new ForkJoinPool();
try {
    pool.invoke(task);
} finally {
    pool.shutdown();
}
~~~

Nếu cách này chạy trong mỗi request, tạo/khởi động/đóng worker nhiều lần có thể rất tốn kém. Tái sử dụng một pool có vòng đời rõ ràng thường hợp lý hơn. Đây là mã minh họa; task cần được khai báo và chính sách lifecycle tùy ứng dụng.

### Đừng nhầm commonPool parallelism với CPU thực tế

Common pool có thể có cấu hình và mức tranh chấp khác pool riêng. Khi đo, phải ghi rõ dùng pool nào, P bao nhiêu, dữ liệu ra sao và có tác vụ khác cạnh tranh không.

## 20. Parallel streams cũng cần suy nghĩ về granularity

Các thao tác song song trên stream có thể dùng Spliterator để phân chia dữ liệu. Nhưng không phải cứ thêm **parallel()** là sẽ nhanh hơn vòng lặp:

~~~java
// Minh họa (không phải file độc lập):
long sum = java.util.stream.IntStream.rangeClosed(1, 1000)
        .parallel()
        .asLongStream()
        .sum();
~~~

Với 1000 phần tử và chỉ một phép cộng, chi phí phân chia/reduction có thể lớn hơn lợi ích. API parallel stream tự quản lý cách chia theo nguồn dữ liệu và implementation; bạn **không điều khiển trực tiếp threshold của RecursiveTask trong ví dụ trên**.

Đối với nguồn có Spliterator phân tách kém, thao tác có side effect, ordered operation hoặc bước xử lý quá nhẹ, parallel stream có thể không mang lại cải thiện.

**Đừng cho rằng parallel stream và ForkJoinPool task thủ công có cùng granularity/chi phí**: cần đo và xét contract của từng API.

## 21. Benchmark thế nào để chọn threshold?

**Không đo bằng cách chạy một lần** và kết luận cutoff 1024 nhanh hơn cutoff 64. Các yếu tố nhiễu gồm JIT compilation, warmup, GC, frequency scaling, container quota, CPU load và độ lớn dữ liệu.

Một quy trình thực dụng:

1. Viết **phiên bản tuần tự đúng** làm baseline.
2. Viết phiên bản Fork/Join với cùng thuật toán/kết quả.
3. Kiểm chứng output và invariant trước khi đo thời gian.
4. Chọn các dataset có kích cỡ nhỏ, trung bình, lớn; cả dữ liệu cân bằng và lệch nếu bài toán có biến thiên.
5. Thử vài cutoff phù hợp, ví dụ dựa trên power-of-two hoặc estimate work.
6. Giữ mức parallelism cụ thể; tránh workload khác trên common pool khi đo.
7. Warmup để JIT có cơ hội tối ưu; có nhiều lượt đo và phân tích phân phối thay vì một con số.
8. Dùng **JMH** cho microbenchmark quan trọng; tránh dead-code elimination, constant folding và đo cả phần không thuộc thuật toán.
9. Quan sát allocation rate, GC, CPU utilization, fork/join/steal activity, throughput và p95/p99 nếu quan trọng.
10. Đánh giá lợi ích so với độ phức tạp code và tài nguyên, không chỉ phần trăm cải thiện tốt nhất trong một cấu hình.

### Các metric đáng theo dõi

| Metric | Ý nghĩa | Cảnh giác |
| --- | --- | --- |
| Wall-clock time | Độ trễ hoàn tất một bài toán | Phụ thuộc tải hệ thống |
| Throughput | Số tác vụ lớn xử lý mỗi giây | Có thể khác mục tiêu latency |
| CPU utilization | Worker có việc hữu ích không | CPU 100% có thể do overhead |
| Allocations/GC | Áp lực tạo task object | JIT có thể tối ưu tùy trường hợp |
| ForkJoinPool.getStealCount() | Thông tin về work stealing | Là snapshot/ước lượng, không phải chỉ số “càng cao càng tốt” |
| getQueuedTaskCount() | Ước lượng task queued của workers | Thay đổi nhanh, không dùng điều khiển nghiệp vụ |
| getActiveThreadCount() | Ước lượng worker đang làm việc | Không thay cho kiểm chứng hiệu quả |
| Task count / leaf count | Chỉ ra granularity của cây | Đo bằng counter toàn cục có thể tự tạo overhead |
| Correctness/error | Chứng minh invariant | Chạy nhanh nhưng sai không có giá trị |

**Ngưỡng tối ưu không phải hằng số phổ quát.** Với workload khác, kích cỡ element khác hoặc JVM khác, cần điều chỉnh lại theo bằng chứng.

## 22. Phân tích kết quả của ví dụ: điều gì đo được, điều gì chưa?

**ForkJoinGranularityDemo** chứng minh:

- Với N=1024 chia đôi cân bằng, threshold 1 dẫn tới 2047 node; threshold 64 dẫn tới 31.
- Cả hai cho tổng 524800.
- Không chứng minh ngưỡng 64 nhanh hơn trong mọi JVM, máy hoặc workload.

**ForkJoinDepthCapDemo** chứng minh:

- maxDepth=3 tạo 15 node cho bài toán cân bằng N=1024.
- Độ sâu có thể chặn task explosion.
- Không chứng minh 8 leaf là số task tốt nhất khi pool có 4 worker.

**ForkJoinBatchingDemo** chứng minh:

- Dữ liệu có thể gom thành 8 Callable, mỗi batch xử lý 128 phần tử.
- Kết quả vẫn bằng tổng tuần tự.
- Không chứng minh batching luôn tốt hơn RecursiveTask cho những cây công việc không đồng đều.

**ForkJoinStatsDemo** chứng minh:

- Có thể reduce sum/count mà không dùng shared mutable accumulator.
- Mỗi leaf làm ít nhất một lượng việc hữu ích trước khi trả kết quả.
- Không chứng minh tạo nhiều record là miễn phí.

**Các số trong stdout là kết quả chức năng/đếm cấu trúc, không phải kết quả performance benchmark.**

## 23. Anti-pattern và cách sửa

| Anti-pattern | Tác hại | Hướng sửa |
| --- | --- | --- |
| Tạo một task cho mỗi phép cộng | Overhead scheduling lớn hơn tính toán | Sequential cutoff và chunking |
| Split cho tới đoạn rỗng hoặc không giảm size | Đệ quy vô hạn/StackOverflowError | Kiểm tra base case, tiến triển của split |
| Threshold quá lớn so với dữ liệu | Không đủ task cho work stealing | Đo và giảm threshold có kiểm soát |
| Threshold quá nhỏ | Task explosion, GC, join overhead | Tăng cutoff, thêm depth cap |
| Fork cả hai nhánh rồi join tùy tiện | Có thể tạo thêm queue/scheduling | Fork một nhánh, compute một nhánh |
| Fork nhưng quên join | Kết quả thiếu hoặc kết thúc quá sớm | Join mọi task có kết quả cần dùng |
| Mọi leaf cộng vào một AtomicLong | Contention trên accumulator | Trả subtotal và reduce sau join |
| Tự tạo ForkJoinPool cho từng item/request | Overhead thread/lifecycle | Dùng pool có vòng đời phù hợp |
| Dùng commonPool cho blocking I/O dài vô giới hạn | Worker bị chiếm, workload khác bị trễ | Tách blocking workload, quota, ManagedBlocker khi cần |
| Gọi join/wait khi giữ lock mà child cần | Deadlock hoặc starvation | Phân tích dependency/lock order |
| Tăng parallelism rồi nghĩ sẽ tăng tốc tương ứng | Memory/cache contention, giới hạn CPU | Benchmark nhiều mức P |
| Dựa vào Thread.sleep để “cho task kịp xong” | Race, test chập chờn | invoke/join/Future completion |
| Chia input không bao phủ hết hoặc chồng lấn | Sai kết quả, ghi trùng | Range half-open [start, end), test boundaries |
| Shared mutable object trong leaf không được bảo vệ | Data race | Confinement, immutable result, lock/CAS phù hợp |
| Tin parallel() luôn nhanh | Overhead và phép toán quá nhỏ | Đo với baseline tuần tự |
| Tối ưu task count nhưng quên độ nặng từng task | Load imbalance | Cân bằng work estimate, dynamic split có kiểm soát |

## 24. Edge cases cần bảo vệ

### Input rỗng

Nếu **start == end**, một phép tổng tuần tự trả **0**. Có thể xử lý ngay không tạo task. Trong RecursiveTask, điều kiện **end-start <= threshold** phải bao phủ đoạn 0 nếu threshold hợp lệ dương.

### Input một phần tử

Không nên split đoạn độ dài 1. Nếu thực hiện mid=start+(end-start)/2, mid có thể bằng start, tạo một nhánh rỗng và một nhánh không nhỏ hơn. Nếu base case thiếu điều kiện length<=1, có thể **đệ quy không tiến triển**.

### Threshold bằng 0 hoặc âm

Với bài toán tổng, threshold không dương là cấu hình vô nghĩa. **Validate threshold > 0** trước khi chạy hoặc có base case length<=1 an toàn. Không dùng cutoff 0 chỉ để cố tạo nhiều task hơn.

### Số worker bằng 1

ForkJoinPool(1) vẫn có thể tính đúng kết quả, nhưng không có parallelism đa worker cho bài toán CPU-bound. Mỗi fork/join vẫn có overhead; với dữ liệu nhẹ, xử lý tuần tự có thể hợp lý hơn.

### Range rất lớn

Tránh overflow khi tính midpoint bằng **(start+end)/2** nếu int có thể vượt giới hạn; sử dụng **start + (end-start)/2** với range hợp lệ. Cân nhắc giá trị tổng có thể tràn int/long và hạn chế allocation.

### Exception trong task con

Nếu một task ném exception, join/invoke có thể đưa lỗi tới caller theo hợp đồng ForkJoinTask. Không giả định mọi nhánh đã kết thúc an toàn hoặc side effect đã được rollback. Cần quy định cách xử lý lỗi, cancellation, cleanup và kết quả một phần.

### Cancellation và interrupt

**ForkJoinTask.cancel(...)** không được xem là cơ chế bảo đảm interrupt worker giống Future của một số executor khác; ForkJoinTask có hợp đồng riêng, và cờ mayInterruptIfRunning **không bảo đảm thread đang chạy bị interrupt**. Task dài cần cơ chế hủy hợp tác rõ nếu cần dừng giữa chừng.

### Side effect không idempotent

Nếu leaf làm I/O hoặc ghi DB, retry cả parent có thể lặp side effect đã thành công ở vài leaf trước. Fork/Join không tự cung cấp transaction. Đặt idempotency, commit protocol và trạng thái nghiệp vụ ở tầng phù hợp.

## 25. Checklist thiết kế granularity

**Correctness:**

- [ ] Mỗi lần split thực sự giảm kích cỡ/range hoặc tiến triển theo measure chặt chẽ.
- [ ] Base case xử lý đoạn 0, 1 phần tử và threshold dương rõ ràng.
- [ ] Các range con phủ đầy range cha, không thiếu hoặc trùng dữ liệu.
- [ ] Mọi kết quả cần dùng đều được join và combine đúng.
- [ ] Có cơ sở happens-before cho việc đọc kết quả/ghi dữ liệu sau completion.
- [ ] Không dùng shared mutable accumulator mà chưa phân tích synchronization.
- [ ] Exception, cancellation và external side effect có chính sách riêng.

**Granularity/performance:**

- [ ] Có sequential cutoff thay vì fork đến từng phần tử.
- [ ] Threshold phản ánh **lượng việc hữu ích**, không chỉ số element.
- [ ] Có kiểm tra task count/leaf count trên dữ liệu đại diện.
- [ ] Số task đủ cho work stealing nhưng không vượt xa nhu cầu thực tế.
- [ ] Có benchmark so với code tuần tự, không dựa vào một lần elapsed time.
- [ ] Nếu workload lệch, có chiến lược chia nhánh nặng hơn.
- [ ] Nếu input nhỏ, có fast path không tạo task dư thừa.
- [ ] Không dùng getStealCount/getQueuedTaskCount như một cơ chế correctness.

**Vận hành:**

- [ ] Pool được tái sử dụng theo lifecycle hợp lý, không tạo mới mỗi request.
- [ ] ForkJoinPool chung không bị lạm dụng bởi blocking I/O kéo dài.
- [ ] Có capacity/queue/overload policy cho nguồn task ngoài nếu cần.
- [ ] Có telemetry về thời gian xử lý, allocation, GC và worker utilization.
- [ ] Có kiểm thử trên số CPU hiệu dụng và dữ liệu thực tế.
- [ ] Không coi “thêm task” hay “thêm thread” là mục tiêu tự thân.

## 26. Câu hỏi tự kiểm tra

**Câu 1.** ForkJoinPool có bốn worker thì có bắt buộc tạo đúng bốn task không?  
**Trả lời:** Không. Task count và worker count là hai đại lượng khác. Có thể có nhiều task hơn worker để cân bằng, nhưng tạo quá nhiều task nhỏ gây overhead.

**Câu 2.** Với 1024 phần tử, chẻ đôi tới một phần tử, cây nhị phân đầy đủ có bao nhiêu node?  
**Trả lời:** 2047 node, gồm 1024 leaf và 1023 internal.

**Câu 3.** Vì sao threshold=64 cho cùng 1024 phần tử chỉ còn 31 node?  
**Trả lời:** Có 16 leaf, mỗi leaf xử lý tuần tự 64 phần tử, và 15 internal node.

**Câu 4.** Fork một nhánh rồi compute nhánh kia mang lại điều gì?  
**Trả lời:** Worker hiện tại làm một nhánh ngay, nhánh kia có cơ hội bị worker khác steal; giảm một số thao tác scheduling không cần thiết so với fork cả hai vô điều kiện.

**Câu 5.** Nếu input chỉ có 20 phần tử và threshold=100, có cần pool.invoke(new Task(...)) không?  
**Trả lời:** Không nhất thiết; một API đồng bộ có thể xử lý tuần tự trực tiếp. Nhưng phải giữ đúng contract nếu API hứa trả Future bất đồng bộ.

**Câu 6.** Ít task hơn có chắc nhanh hơn không?  
**Trả lời:** Không. Quá ít task làm các worker rảnh, mất cân bằng; phải benchmark so với baseline và nhiều threshold.

**Câu 7.** Vì sao không dùng AtomicLong.addAndGet trên mọi leaf?  
**Trả lời:** Dù đúng về atomicity, mọi leaf tranh cùng biến. Có thể trả kết quả cục bộ và reduce qua join để giảm contention.

**Câu 8.** Một task con bị fork mà parent không join có sao không?  
**Trả lời:** Parent có thể trả sớm hoặc bỏ qua kết quả, và không có điểm completion rõ cho dữ liệu từ task con. Phải theo đúng giao thức khi cần kết quả.

**Câu 9.** Chọn threshold theo số phần tử có luôn đủ không?  
**Trả lời:** Không nếu chi phí mỗi phần tử chênh lệch mạnh. Có thể dùng work estimate hoặc chiến lược phân chia động có kiểm soát.

**Câu 10.** Tại sao work stealing không chứng minh Fork/Join luôn nhanh hơn tuần tự?  
**Trả lời:** Scheduling/stealing/join có chi phí; khi task quá nhẹ hoặc băng thông bộ nhớ là nút cổ chai, song song có thể không bù được overhead.

**Câu 11.** ForkJoinPool có phù hợp mặc định cho hàng nghìn tác vụ I/O blocking dài không?  
**Trả lời:** Không nên mặc định như vậy. Cần giới hạn tài nguyên, pool/mô hình blocking phù hợp hoặc ManagedBlocker khi thực sự cần.

**Câu 12.** Vì sao stress test chạy nhanh một lần không đủ để chọn cutoff?  
**Trả lời:** Bị nhiễu bởi JIT, warmup, GC, CPU load và scheduling. Cần benchmark có phương pháp, nhiều mẫu và baseline tuần tự.

**Câu 13.** Có thể giữ cùng một mảng để các leaf ghi song song không?  
**Trả lời:** Có thể nếu mỗi leaf sở hữu phạm vi ghi không chồng lấn và parent chỉ đọc sau completion đúng; nếu nhiều task sửa cùng ô thì cần synchronization phù hợp.

**Câu 14.** Kết quả phép cộng double theo cây có chắc giống bitwise với cộng tuần tự không?  
**Trả lời:** Không. Floating-point rounding phụ thuộc thứ tự cộng; nên dùng tolerance hoặc thuật toán phù hợp với yêu cầu reproducibility.

## 27. Kết luận

**Fork/Join hiệu quả nhờ chia việc vừa đủ, không nhờ tạo càng nhiều task càng tốt.** Với công việc nhỏ, chi phí tạo task, queue, work stealing, join, allocation và GC có thể lớn hơn phép tính hữu ích. Với việc quá lớn, worker khác không có phần việc để làm, gây mất cân bằng.

Cách bắt đầu vững chắc là:

1. Định nghĩa đúng **base case** và **sequential threshold**.
2. **Fork một nhánh, compute một nhánh, join kết quả** để giảm điều phối không cần thiết.
3. Nếu cần, thêm **maxDepth**, **batching** hoặc **work estimate** cho workload phức tạp.
4. Ưu tiên **kết quả cục bộ + reduce** thay vì mọi leaf tranh accumulator chung.
5. So với **baseline tuần tự**, benchmark nhiều ngưỡng/dữ liệu và quan sát allocation, CPU, GC, task count.
6. Giữ rõ ranh giới giữa **CPU divide-and-conquer**, **blocking I/O** và **side effect liên tiến trình**.

Lựa chọn ngưỡng là một **quyết định có căn cứ từ tính đúng đắn và đo đạc**, không phải một con số thần kỳ chung cho mọi máy hoặc thuật toán.

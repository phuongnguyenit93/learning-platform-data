# Phân chia tác vụ độc lập và phân chia dữ liệu

> **Module:** Computer Science Algorithms — **Thuật toán song song**.  
> **Bài học:** Thiết kế hai kiểu phân rã công việc để tính song song đúng và hiệu quả: **task parallelism** (các tác vụ độc lập) và **data parallelism** (cùng phép tính trên các phân vùng dữ liệu). Trình bày điều kiện độc lập, DAG, phân hoạch chỉ số nửa mở, reduction, cân bằng tải, Java 17 `ExecutorService`/`Future`/`ForkJoinPool`, bộ nhớ Java, kiểm thử oracle, giới hạn work-span và các phản ví dụ.

## 1. Mục tiêu và tư duy thiết kế

Tăng số thread **không** tự biến một thuật toán tuần tự thành thuật toán song song đúng. Cần chứng minh những phần việc nào có thể chạy đồng thời và những phần nào phải chờ.

Một giải pháp phải làm rõ:

1. **Decomposition:** Chia theo công việc độc lập hay theo dữ liệu?
2. **Dependency:** Một tác vụ có đọc kết quả/ghi trạng thái của tác vụ khác không?
3. **Ownership:** Mỗi worker sở hữu phần đầu ra nào? Có nhiều worker ghi cùng địa chỉ không?
4. **Synchronization:** Điểm nào cần `join` hoặc `Future.get`?
5. **Combination:** Kết quả cục bộ được reduce/merge theo phép toán nào?
6. **Performance:** Công việc có đủ lớn để overhead thread/task không chiếm ưu thế?

Ví dụ ba bộ dữ liệu cần ba báo cáo độc lập phù hợp với **task parallelism**. Một mảng lớn cần tính tổng hoặc histogram phù hợp với **data parallelism**. Một dãy `dp[i]=dp[i-1]+cost[i]` có dependency nên không được song song hóa trực tiếp từng i bằng cách tăng số worker.

## 2. Task parallelism và data parallelism

| Tiêu chí | Task parallelism | Data parallelism |
|---|---|---|
| Đơn vị chia | Tác vụ, chức năng, request, batch độc lập | Chunk, block, tile, partition của cùng dữ liệu |
| Ví dụ | Analyze batch A, B, C | Sum, map, filter, histogram trên mảng |
| Điều kiện đúng | Không có dependency chưa được thỏa | Không thiếu/trùng dữ liệu; cập nhật riêng; reduce đúng |
| Ghép kết quả | Theo task ID hoặc DAG dependency | Theo phép toán reduce, đôi khi theo thứ tự block |
| Cân bằng tải | Dynamic queue cho task dài/ngắn | Block, cyclic, guided hoặc Fork/Join |
| Lỗi phổ biến | Chạy sớm task phụ thuộc, thiếu wait | Bỏ remainder, overlap, race, reduce sai |
| Java 17 | `ExecutorService`, `Callable`, `Future` | Executor với slice, `ForkJoinPool` |

Hai mô hình có thể **lồng nhau**: mỗi tác vụ đọc một batch độc lập, sau đó xử lý batch ấy bằng nhiều chunk song song.

### 2.1. Ví dụ DAG

```text
Analyze A ----\
               ---> Merge ---> Publish
Analyze B ----/
```

A và B chạy đồng thời được vì chỉ đọc dữ liệu riêng và trả kết quả. Merge phải chờ A và B. Publish phải chờ Merge. Đó là *directed acyclic graph* (DAG) của phụ thuộc, không phải ba tác vụ hoàn toàn độc lập.

### 2.2. Không nên suy luận từ tên hàm

Hai `Callable` khác nhau vẫn có thể không độc lập nếu cùng cập nhật một counter, cùng ghi file hoặc cùng thay đổi một tài khoản ở hệ thống ngoài. Tính độc lập dựa trên **read/write dependencies và side effects**, không dựa trên tên class.

## 3. Tính độc lập và trạng thái dùng chung

Hai tác vụ X và Y có thể chạy đồng thời một cách đơn giản khi:

- Chúng chỉ đọc input đã được chuẩn bị đầy đủ và không bị sửa.
- Mỗi task tạo kết quả cục bộ của riêng nó.
- Không task nào cần dùng kết quả task kia trước khi task đó hoàn tất.
- Mọi side effect được loại bỏ hoặc có chính sách thứ tự/đồng bộ rõ ràng.

### 3.1. Read-read so với write-write

Hai worker đọc cùng `int[]` không đổi thường an toàn. Hai worker cùng thực hiện `counter++` **không** an toàn mặc định: cả hai có thể cùng đọc0 rồi ghi1, dù số lần tăng đúng là2 (*lost update*).

`volatile` hỗ trợ visibility nhưng không biến `counter++` thành một phép cộng nguyên tử. Cách đơn giản cho aggregation là **local counter rồi merge**. Atomic counters và lock là lựa chọn khác nhưng có thể gây contention.

### 3.2. Thread-safe không đồng nghĩa nhanh

Mọi worker có thể dùng `AtomicLong` chung để cộng an toàn, nhưng việc mọi lõi tranh chấp một biến hot có thể chậm hơn local reduction. Khi công việc là thống kê cuối cùng, local sum hoặc local histogram thường vừa dễ chứng minh đúng vừa có performance tốt.

### 3.3. Đừng đọc nửa kết quả

Khi một task đang ghi vùng output riêng, thread chính phải chờ nó hoàn tất trước khi dùng kết quả tổng hợp. `Future.get()`/`join()` không chỉ lấy giá trị: nó tạo điểm chờ và quan hệ quan sát kết quả đã hoàn thành. Tuy nhiên vẫn phải xử lý `ExecutionException`/`InterruptedException` theo contract.

## 4. Công việc W, span D và speedup

Đối với một DAG công việc:

- **Work W:** tổng khối lượng tất cả phép tính.
- **Span D:** chiều dài đường phụ thuộc lớn nhất (critical path).

Với p bộ xử lý lý tưởng:

`T_p ≥ max(W/p,D)`.

Hệ quả speedup lý tưởng:

`S_p ≤ min(p,W/D)` nếu T1 tương ứng W.

**Ví dụ:** W=100, D=40, p=4 ⇒ `T4≥max(25,40)=40`, nên speedup tối đa là100/40=**2.5**, không phải4.

### 4.1. Amdahl

Nếu f là tỷ lệ phần không thể song song hóa:

`S(p) ≤ 1/(f+(1−f)/p)`.

f=0.1, p=4 ⇒ giới hạn `1/(0.1+0.9/4)≈3.077`.

Khi p→∞, cận là `1/f=10`. Overhead, I/O, contention, memory bandwidth có thể làm speedup thực tế thấp hơn đáng kể.

### 4.2. Efficiency

Đặt `speedup=T1/Tp`, `efficiency=speedup/p`. T1=100ms,T4=40ms ⇒ speedup2.5, efficiency0.625. Phải **đo** Tp bằng benchmark, không giả định rằng có bốn worker thì T4=T1/4.

## 5. Tác vụ độc lập: thống kê ba batch

Ba batch:

```text
B0 = [3,1,4,1,5]
B1 = [2,7,1,8]
B2 = [6,5,3]
```

Mỗi tác vụ tính count, sum, squareSum.

| Batch | Count | Sum | SquareSum |
|---|---:|---:|---:|
| B0 | 5 | 14 | 52 |
| B1 | 4 | 18 | 118 |
| B2 | 3 | 14 | 70 |
| Tổng | **12** | **46** | **240** |

Từng batch độc lập. Thread chính gửi ba Callable, sau đó đọc Future theo thứ tự submit, nên stdout vẫn ổn định bất kể scheduler.

### 5.1. Đừng để worker tự in

Nếu worker in log trực tiếp, thứ tự có thể khác nhau qua các lần chạy. Chỉ in kết quả sau khi thread chính đã nhận Future, với `id` lưu từ lúc submit. *Completion order* khác *submission order*.

### 5.2. Task có lỗi

Nếu `future.get()` ném `ExecutionException`, task tương ứng đã thất bại. Không nên âm thầm bỏ kết quả task lỗi rồi vẫn báo tổng thành công. Cần chính sách fail-fast, retry có kiểm soát hoặc kết quả partial được ghi rõ.

## 6. Java 17 — IndependentTasksDemo

Lưu **IndependentTasksDemo.java**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class IndependentTasksDemo {
    record Stat(int id, int count, long sum, long squareSum) {}

    static Stat analyze(int id, int[] a) {
        long sum = 0, squareSum = 0;
        for (int x : a) {
            sum += x;
            squareSum += (long) x * x;
        }
        return new Stat(id, a.length, sum, squareSum);
    }

    public static void main(String[] args) throws Exception {
        int[][] batches = {
            {3, 1, 4, 1, 5},
            {2, 7, 1, 8},
            {6, 5, 3}
        };

        ExecutorService pool = Executors.newFixedThreadPool(3);
        try {
            List<Future<Stat>> futures = new ArrayList<>();
            for (int i = 0; i < batches.length; i++) {
                final int id = i;
                Callable<Stat> task = () -> analyze(id, batches[id]);
                futures.add(pool.submit(task));
            }

            long count = 0, sum = 0, squares = 0;
            for (Future<Stat> future : futures) {
                Stat stat = future.get();
                System.out.printf(
                    "batch %d count=%d sum=%d squareSum=%d%n",
                    stat.id(), stat.count(),
                    stat.sum(), stat.squareSum());
                count += stat.count();
                sum += stat.sum();
                squares += stat.squareSum();
            }
            System.out.printf(
                "total count=%d sum=%d squareSum=%d%n",
                count, sum, squares);

            long exactCount = 0, exactSum = 0, exactSquares = 0;
            for (int[] batch : batches) {
                for (int x : batch) {
                    exactCount++;
                    exactSum += x;
                    exactSquares += (long) x * x;
                }
            }
            boolean correct = count == exactCount
                    && sum == exactSum && squares == exactSquares;
            System.out.println("sequential oracle=" + correct);
        } finally {
            pool.shutdown();
        }
    }
}
```

Lệnh chạy:

```bash
javac -encoding UTF-8 IndependentTasksDemo.java
java IndependentTasksDemo
```

Stdout:

```text
batch 0 count=5 sum=14 squareSum=52
batch 1 count=4 sum=18 squareSum=118
batch 2 count=3 sum=14 squareSum=70
total count=12 sum=46 squareSum=240
sequential oracle=true
```

**Chứng minh:** Mỗi `analyze` trả giá trị chỉ phụ thuộc batch của nó. Thread chính chỉ gộp sau `future.get()`. Các batch không bị bỏ hay nhân đôi; oracle tuần tự duyệt từng phần tử input độc lập với kết quả worker.

**Giới hạn:** Demo dùng input nhỏ và số học long không vượt miền. Trong production, cần chính sách timeout, cancellation, exception và snapshot input; `shutdown()` được gọi trong finally.

## 7. Chia dữ liệu: phân hoạch chỉ số không thiếu, không trùng

Với mảng n phần tử, p worker (p≥1), đặt:

`boundary(i)=floor(i*n/p)` cho `i=0..p`.

Worker i xử lý đoạn nửa mở:

`[boundary(i),boundary(i+1))`.

Đây là dạng chuẩn dễ chứng minh:

- `boundary(0)=0`, `boundary(p)=n`.
- `boundary(i+1)=boundary(i+1)` chính là biên chung giữa hai worker liên tiếp.
- Các đoạn không chồng lặp vì `[L,R)` không chứa R.
- Hợp các đoạn bằng `[0,n)`.
- Độ dài các đoạn lệch nhau tối đa1 khi chi phí mỗi phần tử đồng đều.

Trong Java tính:

```java
int lo = (int) ((long) i * n / p);
int hi = (int) ((long) (i + 1) * n / p);
```

**Cast long trước phép nhân:** Viết `(i*n)/p` kiểu int có thể overflow dù kết quả cuối không lớn.

### 7.1. n=11, p=4

`a=[2,-1,4,7,0,3,-2,6,8,1,5]`.

| Worker | Đoạn | Local sum |
|---:|---|---:|
| 0 | `[0,2)` | 1 |
| 1 | `[2,5)` | 11 |
| 2 | `[5,8)` | 7 |
| 3 | `[8,11)` | 14 |

Global sum=**33**. Nếu chỉ chia mỗi worker `n/p=2` phần tử rồi dừng, sẽ mới xử lý8 phần tử và **bỏ sót3 phần tử**.

### 7.2. p>n

n=3,p=5 tạo:

`[0,0), [0,1), [1,1), [1,2), [2,3)`.

Một vài đoạn rỗng là bình thường. Nếu dữ liệu rỗng n=0, mọi đoạn đều `[0,0)` và sum=0. Production có thể bỏ task rỗng cho nhanh nhưng không được tạo overlap hay mất index.

### 7.3. Kiểm phủ bằng mảng visited

Tạo `visited[0..n−1]`. Với từng block, duyệt index trong `[lo,hi)`, nếu `visited[index]` đã true thì lỗi **trùng**, nếu chưa thì đặt true. Sau tất cả, mọi index phải true để chứng minh **không thiếu**.

Chỉ kiểm sum đúng chưa đủ: có thể bỏ một giá trị và đếm trùng một giá trị bằng nó mà tổng vẫn đúng.

## 8. Java 17 — BlockPartitionSumDemo

Lưu **BlockPartitionSumDemo.java**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class BlockPartitionSumDemo {
    record Block(int id, int start, int end, long sum) {}

    static Block[] solve(int[] a, int workers) throws Exception {
        if (a == null || workers < 1)
            throw new IllegalArgumentException("Invalid input");

        int threads = Math.min(workers, Math.max(1, a.length));
        ExecutorService pool = Executors.newFixedThreadPool(threads);
        try {
            List<Future<Block>> pending = new ArrayList<>();
            for (int i = 0; i < workers; i++) {
                final int id = i;
                final int lo = (int) ((long) i * a.length / workers);
                final int hi = (int) ((long) (i + 1) * a.length / workers);
                pending.add(pool.submit(() -> {
                    long sum = 0;
                    for (int j = lo; j < hi; j++) sum += a[j];
                    return new Block(id, lo, hi, sum);
                }));
            }
            Block[] result = new Block[workers];
            for (int i = 0; i < workers; i++)
                result[i] = pending.get(i).get();
            return result;
        } finally {
            pool.shutdown();
        }
    }

    static long total(Block[] blocks) {
        long sum = 0;
        for (Block b : blocks) sum += b.sum();
        return sum;
    }

    static long sequential(int[] a) {
        long sum = 0;
        for (int x : a) sum += x;
        return sum;
    }

    static boolean exactCover(int n, Block[] blocks) {
        boolean[] seen = new boolean[n];
        for (Block b : blocks) {
            if (b.start() < 0 || b.start() > b.end()
                    || b.end() > n) return false;
            for (int j = b.start(); j < b.end(); j++) {
                if (seen[j]) return false;
                seen[j] = true;
            }
        }
        for (boolean x : seen) if (!x) return false;
        return true;
    }

    public static void main(String[] args) throws Exception {
        int[] a = {2, -1, 4, 7, 0, 3, -2, 6, 8, 1, 5};
        Block[] blocks = solve(a, 4);
        for (Block b : blocks)
            System.out.printf("block %d [%d,%d) sum=%d%n",
                    b.id(), b.start(), b.end(), b.sum());
        System.out.println("parallel sum=" + total(blocks));
        System.out.println("sequential sum=" + sequential(a));
        System.out.println("partition exact="
                + exactCover(a.length, blocks));
        System.out.println("empty sum=" + total(solve(new int[0], 3)));
        System.out.println("workers>n sum="
                + total(solve(new int[] {2, -1, 4}, 5)));

        boolean rejected = false;
        try {
            solve(a, 0);
        } catch (IllegalArgumentException ex) {
            rejected = true;
        }
        System.out.println("invalid workers rejected=" + rejected);
    }
}
```

Lệnh:

```bash
javac -encoding UTF-8 BlockPartitionSumDemo.java
java BlockPartitionSumDemo
```

Stdout:

```text
block 0 [0,2) sum=1
block 1 [2,5) sum=11
block 2 [5,8) sum=7
block 3 [8,11) sum=14
parallel sum=33
sequential sum=33
partition exact=true
empty sum=0
workers>n sum=5
invalid workers rejected=true
```

**Bất biến:** Worker i chỉ đọc `[lo,hi)` và trả sum riêng. Các đoạn nối nhau ở biên, không overlap, phủ `[0,n)`, nên reduction các `Block.sum` bằng tổng tuần tự.

**Giới hạn hiệu năng:** Bản demo submit cả block rỗng để minh họa; trường hợp p≫n thực tế nên không tạo quá nhiều task. Bộ nhớ metadata/Future O(p) ngoài input.

## 9. Block, cyclic và dynamic scheduling

### 9.1. Contiguous block

Các phần tử liên tiếp trong một chunk, tốt cho locality/cache khi mỗi item tốn công gần giống nhau. Nhược điểm khi một vùng chứa nhiều item nặng.

### 9.2. Cyclic partition

Worker i xử lý `i,i+p,i+2p,...`. Có thể phân tán item nặng theo vị trí, nhưng truy cập không liên tục, locality kém và dễ có false sharing trên output.

### 9.3. Chunked cyclic và dynamic queue

Cấp phát nhiều chunk có kích thước B; worker rảnh nhận chunk tiếp theo. Dynamic scheduling hữu ích khi task cost không dự đoán được. Nếu chunk quá nhỏ, chi phí scheduling áp đảo; nếu chunk quá lớn, load imbalance.

### 9.4. Hot key/skew

Với phân chia theo key `owner(key)=floorMod(hash(key),p)`, state mỗi key có một owner, nhưng một hot key chiếm80% sự kiện vẫn khiến owner đó quá tải. Cần kỹ thuật split hot keys rồi merge hoặc tái thiết kế nếu chi phí lớn.

## 10. Local reduction với histogram

Đếm bucket trực tiếp vào một array dùng chung bằng `counts[value]++` là race khi hai thread cập nhật cùng bucket.

Giải pháp:

1. Mỗi task xử lý block `[lo,hi)`.
2. Task tạo `long[bins]` riêng và tăng local counts.
3. Chờ Future.
4. Thread chính cộng các local array theo bucket.

Với `bins=B`, `workers=p`, bộ nhớ local là **O(pB)**, công việc đếm N phần tử là O(N), công việc merge O(pB).

### 10.1. Ví dụ 15 phần tử

`data=[0,3,1,2,3,0,2,2,1,3,0,2,1,3,3]`.

| Worker | Đoạn | Local histogram |
|---:|---|---|
| 0 | `[0,3)` | `[1,1,0,1]` |
| 1 | `[3,7)` | `[1,0,2,1]` |
| 2 | `[7,11)` | `[1,1,1,1]` |
| 3 | `[11,15)` | `[0,1,1,2]` |

Reduction theo từng bucket:

`[3,3,4,5]`.

Tổng `3+3+4+5=15` đúng N. Nhưng cần test **từng bucket**, không chỉ tổng N.

### 10.2. Khi B rất lớn

Cấp B counters cho mọi worker có thể tốn nhiều RAM. Nếu dữ liệu thưa, local `HashMap<key,count>` rồi merge có thể phù hợp hơn.

## 11. Java 17 — LocalHistogramDemo

Lưu **LocalHistogramDemo.java**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class LocalHistogramDemo {
    record Part(int id, int start, int end, long[] counts) {}

    static Part[] solve(int[] data, int bins, int workers)
            throws Exception {
        if (data == null || bins < 1 || workers < 1)
            throw new IllegalArgumentException("Invalid input");
        for (int x : data)
            if (x < 0 || x >= bins)
                throw new IllegalArgumentException("Invalid bucket");

        ExecutorService pool = Executors.newFixedThreadPool(
                Math.min(workers, Math.max(1, data.length)));
        try {
            List<Future<Part>> futures = new ArrayList<>();
            for (int i = 0; i < workers; i++) {
                final int id = i;
                final int lo =
                        (int) ((long) i * data.length / workers);
                final int hi =
                        (int) ((long) (i + 1) * data.length / workers);
                futures.add(pool.submit(() -> {
                    long[] local = new long[bins];
                    for (int j = lo; j < hi; j++)
                        local[data[j]]++;
                    return new Part(id, lo, hi, local);
                }));
            }
            Part[] result = new Part[workers];
            for (int i = 0; i < workers; i++)
                result[i] = futures.get(i).get();
            return result;
        } finally {
            pool.shutdown();
        }
    }

    static long[] reduce(Part[] parts, int bins) {
        long[] total = new long[bins];
        for (Part part : parts)
            for (int b = 0; b < bins; b++)
                total[b] += part.counts()[b];
        return total;
    }

    static long[] sequential(int[] data, int bins) {
        long[] counts = new long[bins];
        for (int x : data) counts[x]++;
        return counts;
    }

    public static void main(String[] args) throws Exception {
        int[] a = {
            0, 3, 1, 2, 3, 0, 2, 2,
            1, 3, 0, 2, 1, 3, 3
        };
        Part[] parts = solve(a, 4, 4);
        for (Part part : parts)
            System.out.printf("part %d [%d,%d): %s%n",
                    part.id(), part.start(), part.end(),
                    Arrays.toString(part.counts()));

        long[] parallel = reduce(parts, 4);
        long[] serial = sequential(a, 4);
        System.out.println("merged histogram="
                + Arrays.toString(parallel));
        System.out.println("serial histogram="
                + Arrays.toString(serial));
        System.out.println("identical="
                + Arrays.equals(parallel, serial));
        long sum = 0;
        for (long count : parallel) sum += count;
        System.out.println("total counted=" + sum);

        boolean rejected = false;
        try {
            solve(a, 0, 4);
        } catch (IllegalArgumentException ex) {
            rejected = true;
        }
        System.out.println("invalid bins rejected=" + rejected);
    }
}
```

Lệnh:

```bash
javac -encoding UTF-8 LocalHistogramDemo.java
java LocalHistogramDemo
```

Stdout:

```text
part 0 [0,3): [1, 1, 0, 1]
part 1 [3,7): [1, 0, 2, 1]
part 2 [7,11): [1, 1, 1, 1]
part 3 [11,15): [0, 1, 1, 2]
merged histogram=[3, 3, 4, 5]
serial histogram=[3, 3, 4, 5]
identical=true
total counted=15
invalid bins rejected=true
```

**Tính đúng:** Các block không overlap. Mỗi worker tạo local array mới và chỉ mình nó ghi; thread chính merge sau các Future.get. Vì vậy mỗi input xuất hiện đúng một lần ở bucket tương ứng.

## 12. ForkJoin: phân chia dữ liệu theo cây đệ quy

`ForkJoinPool` phù hợp thuật toán chia để trị:

1. Nếu đoạn `[lo,hi)` đủ nhỏ, tính tuần tự.
2. Nếu lớn, chọn `mid=lo+(hi-lo)/2`.
3. Chia thành `[lo,mid)` và `[mid,hi)`.
4. Fork nhánh phải, tính nhánh trái, join nhánh phải.
5. Reduce hai kết quả.

Điểm quan trọng là `mid` nằm trong đoạn và **hai nửa không trùng, không thiếu**. Threshold phải dương để đệ quy kết thúc.

### 12.1. Work stealing

Nhiều task nhỏ hơn số worker có thể được phân phối lại khi worker rảnh. Điều này giúp với cây task bất cân bằng nhưng không tự rút ngắn đường găng của một tác vụ không thể tách.

### 12.2. Phân tích

Tổng số phần tử được cộng là N: O(N) work cộng overhead task. Cây chia cân bằng có chiều sâu O(log N) khi threshold cố định. Tốc độ thực vẫn phụ thuộc overhead, băng thông RAM, số core và scheduler.

## 13. Java 17 — ForkJoinSumDemo

Lưu **ForkJoinSumDemo.java**:

```java
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveTask;

public class ForkJoinSumDemo {
    static final class SumTask extends RecursiveTask<Long> {
        final int[] a;
        final int lo, hi, threshold;

        SumTask(int[] a, int lo, int hi, int threshold) {
            this.a = a;
            this.lo = lo;
            this.hi = hi;
            this.threshold = threshold;
        }

        @Override
        protected Long compute() {
            if (hi - lo <= threshold) {
                long result = 0;
                for (int i = lo; i < hi; i++)
                    result += a[i];
                return result;
            }
            int mid = lo + (hi - lo) / 2;
            SumTask right = new SumTask(a, mid, hi, threshold);
            right.fork();
            long leftResult =
                    new SumTask(a, lo, mid, threshold).compute();
            return leftResult + right.join();
        }
    }

    static long sum(int[] a, int threads, int threshold) {
        if (a == null || threads < 1 || threshold < 1)
            throw new IllegalArgumentException("Invalid input");
        ForkJoinPool pool = new ForkJoinPool(threads);
        try {
            return pool.invoke(new SumTask(a, 0, a.length, threshold));
        } finally {
            pool.shutdown();
        }
    }

    static long sequential(int[] a) {
        long sum = 0;
        for (int x : a) sum += x;
        return sum;
    }

    public static void main(String[] args) {
        int[] a = {2, -1, 4, 7, 0, 3, -2, 6, 8, 1, 5};
        System.out.println("forkjoin sum=" + sum(a, 3, 3));
        System.out.println("sequential sum=" + sequential(a));
        System.out.println("empty sum=" + sum(new int[0], 2, 3));

        boolean rejected = false;
        try {
            sum(a, 3, 0);
        } catch (IllegalArgumentException ex) {
            rejected = true;
        }
        System.out.println("invalid threshold rejected=" + rejected);
    }
}
```

Lệnh:

```bash
javac -encoding UTF-8 ForkJoinSumDemo.java
java ForkJoinSumDemo
```

Stdout:

```text
forkjoin sum=33
sequential sum=33
empty sum=0
invalid threshold rejected=true
```

**Quy nạp:** Lá tính đúng tổng đoạn. Node trong chia đoạn cha thành hai nửa không giao, hai tổng con cộng ra đúng tổng cha. Join đợi nhánh fork trước khi dùng kết quả.

## 14. Khi các block chưa độc lập: prefix scan

Không phải cứ có mảng là chỉ cần chia rồi nối output.

`a=[2,1,3,4,2,5]`.

Chia thành:

- Block0 `[0,3)`: prefix local `[2,3,6]`, sum6.
- Block1 `[3,6)`: prefix local `[4,6,11]`, sum11.

Nối hai local prefix ra `[2,3,6,4,6,11]` là **sai** vì block1 chưa tính tổng block trước.

Cách đúng:

1. Mỗi block tính prefix local và block sum song song.
2. Tính exclusive prefix của các block sums: offsets `[0,6]`.
3. Cộng offset vào mọi local prefix thuộc block tương ứng.
4. Thu prefix đúng `[2,3,6,10,12,17]`.

Vậy dữ liệu có dependency qua aggregate cần **một DAG nhiều pha**, không phải chạy mọi phase độc lập.

## 15. Reduction, tính kết hợp và floating-point

Phép toán gộp cần phù hợp với việc đổi thứ tự.

- Cộng số nguyên toán học có tính kết hợp.
- Nối chuỗi/list phụ thuộc thứ tự nên cần merge theo block ID.
- Java `long` có thể overflow nếu tổng thật ngoài miền biểu diễn.
- Floating-point addition không kết hợp bitwise.

Ví dụ với `double`:

`(1e16+1)+(-1e16)` thường cho0, còn `(1e16+(-1e16))+1` cho1.

Nếu cần kết quả bitwise reproducible, cố định reduction tree/order hoặc dùng chiến lược tích lũy số phù hợp. Không mặc định một `parallelStream().sum()` luôn trả cùng bits khi đổi kiểu reduction.

## 16. Memory model, false sharing và visibility

**Race:** Hai worker ghi một biến mà không đồng bộ, có thể sai kết quả. **False sharing:** Hai worker ghi **biến khác nhau** nhưng cùng cache line, kết quả có thể vẫn đúng nhưng chạy chậm do cache coherence.

Việc `Future.get()` chờ một Callable hoàn tất hỗ trợ thread chính quan sát kết quả đã công bố. Tuy nhiên nếu một thread khác sửa input trong lúc Callable đang đọc mà không đồng bộ thì vẫn có vấn đề.

Các mô hình sở hữu dễ kiểm:

- Input immutable, nhiều reader.
- Mỗi worker ghi một vùng `[L,R)` của output.
- Mỗi worker tạo local aggregation.
- Chỉ thread reducer merge sau khi mọi task xong.

## 17. Cân bằng tải và chọn độ hạt công việc

Có bốn task có cost `[100,1,1,1]` và hai worker. Cho dù ba task nhỏ hoàn thành nhanh, một task100 không thể hoàn tất trước100 đơn vị nếu nó không chia được. Dynamic scheduling không chữa được span của task nguyên khối.

**Chunk lớn:** overhead nhỏ, load imbalance có thể cao.  
**Chunk nhỏ:** cân bằng tải tốt hơn, nhưng tốn enqueue, Future, cache và GC.  
**Contiguous block:** locality tốt khi cost đều.  
**Cyclic/dynamic:** có ích khi cost phân bố lệch.

Tăng số CPU-bound thread lên vượt xa số core không bảo đảm speedup; memory bandwidth và context switching có thể chi phối.

## 18. Kiểm thử độc lập

| Kỹ thuật | Oracle tuần tự | Điều kiện cần kiểm |
|---|---|---|
| Independent tasks | Quét batch bằng vòng for | Mỗi batch đúng một Stat |
| Block sum | Sum toàn mảng trực tiếp | Coverage: mỗi index đúng một lần |
| Histogram | Histogram tuần tự theo bucket | Từng bucket khớp, tổng bằng N |
| ForkJoin sum | Sum tuần tự | Đoạn chia không overlap, kết quả khớp |
| Prefix scan | Prefix từ đầu đến mỗi i | Block offsets chính xác |

Các input quan trọng: n=0, p=1, p>n, n không chia hết p, giá trị âm/0, hot bucket, task runtime lệch, threshold khác nhau, exception trong task, cùng input chạy nhiều lần với worker count khác nhau.

**Không chỉ kiểm một tổng:** Có thể bỏ một phần tử và đếm trùng một phần tử cùng giá trị, khiến sum vẫn trùng. Phải kiểm coverage. Histogram có thể có tổng N nhưng phân bố bucket sai, cần so toàn vector.

### 18.1. Test biến hình

- Thay p=1,2,4,>n nhưng integer sum vẫn bằng nhau nếu không overflow.
- Tách một block thành hai block rồi giảm/ghép đúng: tổng không đổi.
- Hoán vị input histogram: histogram toàn cục không đổi.
- Thay ForkJoin threshold: sum không đổi.
- Đổi lịch worker: result theo ID không đổi.
- Thêm empty block: tổng không đổi.

### 18.2. Benchmark khác correctness oracle

Oracle chứng minh một số input thử đúng, không đo tốc độ. Benchmark phải warm up JIT, dùng input đủ lớn, đo nhiều lần, so baseline tuần tự, tránh ép kết luận từ một phép đo input nhỏ. Ngược lại benchmark nhanh không chứng minh code không có race.

## 19. Sai lầm phổ biến

1. Chỉ tạo nhiều thread mà không chứng minh độc lập.
2. Cho task B chạy trước khi A tạo xong dữ liệu mà B cần.
3. Dùng shared `total += value`.
4. Tưởng volatile làm increment atomic.
5. Quên chờ Future/join.
6. Không xử lý ExecutionException/InterruptedException.
7. Không shutdown executor.
8. Worker in stdout trực tiếp rồi giả định thứ tự cố định.
9. Trộn task ID với worker/thread ID.
10. Input dùng chung bị sửa trong khi worker đọc.
11. Chia `n/p` phần tử rồi bỏ remainder.
12. Dùng `(i*n)/p` kiểu int và overflow.
13. Dùng `[L,R]` ở một nơi và `[L,R)` ở nơi khác.
14. Không xử lý block rỗng khi p>n.
15. Không xử lý n=0.
16. Hai worker đếm cùng index do chia overlap.
17. Chỉ kiểm tổng nhưng không kiểm coverage.
18. Shared histogram bucket++ gây lost update.
19. Atomic hot bucket làm nghẽn contention.
20. Không tính bộ nhớ O(pB) local histogram.
21. Dùng hash(key) partition nhưng bỏ qua hot key/skew.
22. Tưởng số phần tử bằng nhau thì thời gian bằng nhau.
23. Để một task rất lớn không chia được.
24. Tạo nhiều task cực nhỏ hơn phép tính.
25. Tăng worker vô hạn rồi dự đoán speedup vô hạn.
26. Dùng double reduce mà yêu cầu bitwise deterministic không có chính sách.
27. Nối output theo completion order dù cần input order.
28. Không kiểm overflow của long.
29. ForkJoin chia nhầm mid, mất/trùng phần tử.
30. Fork mà quên join.
31. Cho threshold=0 khiến đệ quy không đúng.
32. Dùng CPU ForkJoinPool cho blocking I/O dài.
33. Nối local prefix mà quên offset các block trước.
34. Nhầm data race với false sharing.
35. Chỉ thử một p hoặc một threshold.
36. So multiset output nhưng quên ID.
37. Chỉ đo thời gian một lần và coi là speedup.
38. Dùng Amdahl như benchmark thực nghiệm.
39. Quên phân biệt work W và span D.
40. Dùng random tests thay cho chứng minh bất biến.

## 20. Bài tập có đáp án

### Bài 1 — Task hay data?

Ba batch riêng cần ba báo cáo. **Đáp án:** Task parallelism.

### Bài 2 — Histogram

Một mảng lớn cùng phép đếm. **Đáp án:** Data parallelism với local histogram.

### Bài 3 — Read-only

Hai worker đọc cùng input không đổi. **Đáp án:** Có thể chạy song song nếu dữ liệu được publish an toàn.

### Bài 4 — Race

Hai worker `counter++`. **Đáp án:** Không an toàn mặc định.

### Bài 5 — DAG

B cần kết quả A. **Đáp án:** B phải chờ hoặc nối stage sau A.

### Bài 6 — Future

`Future.get()` làm gì? **Đáp án:** Chờ, nhận kết quả và exception của task.

### Bài 7 — Batch0

`[3,1,4,1,5]` có sum? **Đáp án:** 14.

### Bài 8 — Batch0 squareSum

**Đáp án:** 52.

### Bài 9 — Ba batch tổng

**Đáp án:** Count12, sum46, squareSum240.

### Bài 10 — Work/span

W100,D40,p4; thời gian lý tưởng tối thiểu? **Đáp án:** 40.

### Bài 11 — Speedup bound

Bài trên speedup tối đa? **Đáp án:** 2.5.

### Bài 12 — Amdahl

f=0.1,p=4. **Đáp án:** Speedup cận xấp xỉ3.077.

### Bài 13 — n11,p4

Các đoạn? **Đáp án:** `[0,2)`, `[2,5)`, `[5,8)`, `[8,11)`.

### Bài 14 — Remainder

Chia n11 mỗi worker2 item sẽ bỏ bao nhiêu? **Đáp án:** 3.

### Bài 15 — Sum blocks

Local sums? **Đáp án:** 1,11,7,14; tổng33.

### Bài 16 — p>n

n3,p5 có block rỗng? **Đáp án:** Có.

### Bài 17 — Empty

n0 sum? **Đáp án:** 0.

### Bài 18 — Cast long

Vì sao cast trước `i*n`? **Đáp án:** Tránh overflow int.

### Bài 19 — Histogram0

Bucket0 có bao nhiêu? **Đáp án:** 3.

### Bài 20 — Histogram3

Bucket3? **Đáp án:** 5.

### Bài 21 — Histogram total

`[3,3,4,5]` cộng? **Đáp án:** 15.

### Bài 22 — Bộ nhớ

p local histogram, B bins? **Đáp án:** O(pB).

### Bài 23 — ForkJoin

Threshold nhỏ gây gì? **Đáp án:** Task overhead lớn.

### Bài 24 — Split

`[lo,hi)` chia mid thành gì? **Đáp án:** `[lo,mid)` và `[mid,hi)`.

### Bài 25 — Join

Vì sao join? **Đáp án:** Chờ kết quả nhánh fork trước khi cộng.

### Bài 26 — Prefix scan

Block1 local `[4,6,11]`, offset6: kết quả? **Đáp án:** `[10,12,17]`.

### Bài 27 — Hot key

80% dữ liệu cùng key, hash partition cân bằng không? **Đáp án:** Không chắc.

### Bài 28 — False sharing

Hai biến khác nhau cùng cache line? **Đáp án:** Có thể chậm dù không race.

### Bài 29 — Coverage

Bên cạnh sum phải kiểm gì? **Đáp án:** Mỗi index xử lý đúng một lần.

### Bài 30 — Worker count

Đổi p nhưng không đổi input, integer sum phải ra sao? **Đáp án:** Giống nhau khi không overflow và đúng partition.

### Bài 31 — Side effects

Hai task cùng ghi một tài khoản có độc lập? **Đáp án:** Không nếu thiếu chính sách đồng bộ/giao dịch.

### Bài 32 — Benchmark

Một input rất nhỏ đo một lần có đáng tin? **Đáp án:** Không.

### Bài 33 — Amdahl max

f=0.1,p→∞; speedup cận? **Đáp án:** 10.

## 21. Checklist trước khi kết luận thuật toán đúng

1. Đã chọn task/data decomposition rõ ràng?
2. Đã lập dependency DAG?
3. Shared input có bất biến?
4. Side effects chung đã được xử lý?
5. Không có shared mutable sum không đồng bộ?
6. Có ownership cho output?
7. Có giữ ID gốc của task?
8. Có chờ Future/join?
9. Có xử lý exceptions?
10. Có shutdown pool?
11. Có validate p≥1?
12. Có validate threshold≥1?
13. Có dùng `[start,end)`?
14. Có cast long trước phép nhân biên?
15. Có kiểm n không chia hết p?
16. Có kiểm p>n?
17. Có kiểm n=0?
18. Có kiểm p=1?
19. Có assert coverage từng index?
20. Có kiểm không overlap?
21. Có tránh bỏ remainder?
22. Có chọn block/cyclic/dynamic theo workload?
23. Có tránh task quá nhỏ?
24. Có test dữ liệu lệch tải?
25. Có so với oracle tuần tự độc lập?
26. Có so từng histogram bucket?
27. Có tính memory O(pB)?
28. Có giảm shared bucket contention?
29. Reduction có kết hợp đúng?
30. Nếu order-sensitive, có ghép theo ID?
31. Nếu double, có quy tắc tính tái lập?
32. Có kiểm overflow của tổng?
33. ForkJoin có chia đúng hai nửa?
34. Fork có join tương ứng?
35. Có tránh I/O blocking trong CPU pool?
36. Prefix scan có offset đúng?
37. Có xử lý hot keys?
38. Có phân biệt race và false sharing?
39. Có thử nhiều p/threshold?
40. Có benchmark warmup và input đủ lớn?
41. Có phân tích W/span và overhead?
42. Có đo memory bandwidth khi cần?
43. Có so kết quả logic thay vì lịch thread?
44. Có nêu rõ giả thiết input/side effect?

**Kết luận:** Task parallelism cần **độc lập và đúng phụ thuộc**; data parallelism cần **phân hoạch đủ, không chồng lặp, rồi reduction chính xác**. `ExecutorService`/`Future` cho tác vụ độc lập, công thức floor chia block có chứng minh coverage, local histogram tránh write race, `ForkJoinPool` hỗ trợ chia để trị. Correctness phải dựa trên bất biến và đối chiếu oracle; speedup phải đo, vì đường găng, điều phối và bộ nhớ hạn chế lợi ích của nhiều worker.

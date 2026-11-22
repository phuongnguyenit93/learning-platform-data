# Chia để trị cho bài toán tính toán có thể tách nhỏ bằng Fork/Join

**Chủ đề:** Java 7 — Fork/Join  
**Bài học:** Chia để trị cho bài toán tính toán có thể tách nhỏ  
**Phiên bản:** Java 17+ (các API `java.util.concurrent.ForkJoinPool`, `ForkJoinTask`, `RecursiveTask`, `RecursiveAction` và `ForkJoinPool.ManagedBlocker` được giới thiệu từ Java 7 và vẫn được sử dụng trong Java hiện đại). Các ví dụ không phụ thuộc Maven/Gradle hay thư viện ngoài JDK.

## 1. Vì sao cần Fork/Join?

Có nhiều bài toán CPU-bound mà một kết quả lớn có thể tạo từ các kết quả độc lập của những bài toán nhỏ hơn: tính tổng một mảng, tìm giá trị lớn nhất, đếm ký tự, phân tích dữ liệu theo phân đoạn, áp dụng một phép biến đổi độc lập lên từng phần tử hoặc sắp xếp kiểu merge sort.

Giả sử cần tính tổng một mảng dài. Cách tuần tự:

```java
long sum = 0;
for (long value : values) {
    sum = Math.addExact(sum, value);
}
```

Đây là **snippet minh họa**, yêu cầu biến `values` được khai báo trước. Độ phức tạp công việc là O(n), và một thread xử lý toàn bộ. Nếu phần tử nhiều và công việc trên mỗi phần tử đủ lớn, có thể chia dải thành các đoạn:

```text
                         sum[0..16)
                         /        \
                   sum[0..8)     sum[8..16)
                    /    \          /    \
               [0..4)  [4..8)   [8..12)  [12..16)
                  |       |         |         |
                sum     sum       sum       sum
                  \       /         \         /
                   combine           combine
                         \           /
                          final sum
```

Mỗi **leaf** xử lý một đoạn nhỏ, rồi **join** các kết quả. Các leaf không phải đợi nhau nếu chỉ đọc những vùng không thay đổi. Kết quả của các nhánh được kết hợp bằng phép cộng có điều kiện kiểm soát tràn số.

**Fork/Join** là framework Java hỗ trợ mô hình **divide and conquer**:

1. **Divide:** kiểm tra kích thước công việc; nếu quá lớn, tách thành các subtasks.
2. **Fork:** cho phép một hoặc nhiều subtasks được scheduling để thực hiện đồng thời.
3. **Compute:** xử lý nhánh còn lại hoặc xử lý trực tiếp phần nhỏ.
4. **Join:** đợi lấy kết quả của nhánh đã fork, phối hợp với kết quả nhánh hiện tại.
5. **Combine:** trả kết quả của bài toán gốc hoặc cập nhật vùng dữ liệu mà task sở hữu.

**Không phải mọi recursion đều phù hợp Fork/Join.** Để có lợi, các nhánh nên độc lập hoặc chỉ có quan hệ kết hợp rõ ràng, làm việc đủ lớn để bù chi phí scheduling, và không đòi shared mutable state phức tạp.

### 1.1. Mẫu bài toán phù hợp

| Bài toán | Cách chia | Cách kết hợp | Rủi ro cần quản lý |
| --- | --- | --- | --- |
| Tổng hoặc đếm trên mảng | Hai dải [lo, mid), [mid, hi) | Cộng kết quả | Tràn số, thứ tự kết hợp số thực |
| Tìm max/min | Hai dải | `Math.max/min` | Mảng rỗng, identity |
| Đếm ký tự/byte | Hai vùng dữ liệu | Cộng số lượng | Offset và encoding |
| Áp dụng biến đổi phần tử | Hai dải riêng | Không cần kết quả; chờ tất cả xong | Hai nhánh cùng sửa một phần tử |
| Merge sort | Sắp xếp hai nửa độc lập | Trộn hai nửa đã sort | Scratch buffer, duplicate, allocation |
| Xử lý ảnh theo ô | Các tiles không chồng lấn | Ghép kết quả vào ảnh | Border dependencies, cache locality |
| Phân tích cây | Các cây con | Kết hợp kết quả | Cây quá lệch, giới hạn độ sâu |
| Reduce thống kê | Chia records | Combine partial aggregations | Phép gộp có thực sự associative? |

Mô hình đặc biệt hợp với **tính toán CPU-bound** có work units tương đối đồng đều. Đối với networking, database calls, file I/O, hoặc chờ remote service, điều kiện bottleneck có thể nằm ở latency/tài nguyên bên ngoài chứ không phải CPU: không được mặc định Fork/Join là giải pháp tốt.

### 1.2. Fork/Join không có nghĩa luôn nhanh hơn

Chi phí khi chia nhỏ gồm tạo object task, quản lý hàng đợi, dispatch, steal, join, cache misses, GC và phân phối dữ liệu. Với 100 số nguyên, một vòng for tuần tự có thể nhanh và đơn giản hơn một cây task. Với hàng triệu phần tử và tính toán nặng mỗi phần tử, chia để trị có thể phát huy lợi ích — nhưng vẫn cần đo.

Công thức tư duy:

```text
thời gian song song ≈
    công việc hữu ích được phân phối
  + chi phí tạo/scheduling tasks
  + chi phí đồng bộ/join/combine
  + chi phí cache/memory/GC
  + thời gian nhàn rỗi do mất cân bằng tải
```

Đây là **mô hình định tính**, không phải một công thức dự đoán chính xác runtime. Tốc độ còn phụ thuộc số CPU lõi, SMT, JIT, memory bandwidth, workload và môi trường triển khai.

## 2. Các thành phần cốt lõi

| Thành phần | Vai trò |
| --- | --- |
| `ForkJoinPool` | Executor chuyên dùng cho các tác vụ Fork/Join, có cơ chế **work stealing** |
| `ForkJoinTask<V>` | Abstraction của một công việc; có `fork`, `join`, `invoke`, trạng thái hoàn tất/cancel/lỗi |
| `RecursiveTask<V>` | Task đệ quy **trả kết quả V**; override `compute()` |
| `RecursiveAction` | Task đệ quy **không có kết quả trả về**; override `compute()` |
| `ForkJoinPool.commonPool()` | Pool dùng chung toàn JVM cho nhiều công việc, không tự shutdown khi xong một request |
| `ForkJoinPool.ManagedBlocker` | Hợp đồng giúp pool có thể điều chỉnh khi một worker buộc phải chờ việc blocking |
| `CountedCompleter` | API Fork/Join nâng cao cho completion dependencies, không cần dùng trong ví dụ chia đôi cơ bản |

Các class này **vẫn có trong Java 17/21**, không phải kỹ thuật legacy chỉ vì được giới thiệu từ Java 7. Bạn có thể chọn các API mới hơn cho mục đích khác (parallel streams hoặc virtual threads) nhưng không cần bỏ Fork/Join khi bài toán vốn phù hợp.

### 2.1. RecursiveTask hay RecursiveAction?

- Dùng `RecursiveTask<Long>` khi tính tổng và cần giá trị `long`.
- Dùng `RecursiveTask<Integer>` khi tìm max và cần giá trị `int`.
- Dùng `RecursiveAction` khi thao tác trên **những phân đoạn không chồng lấp của mảng**, và caller chỉ cần biết khi nào đã xử lý xong.
- Với công việc phân tách thành nhiều nhánh không có cấu trúc cây hai nhánh tự nhiên, có thể xem xét `CountedCompleter` hoặc một abstraction khác, nhưng không nên ép dùng nó cho bài toán đơn giản.

`RecursiveTask` và `RecursiveAction` đều là `ForkJoinTask`; phương thức `join` chờ hoàn tất tác vụ. Với `RecursiveAction`, `join()` trả `null` kiểu `Void`, nên mục đích thường là **đợi hoàn tất và truyền lỗi**.

### 2.2. Ai khởi động tác vụ gốc?

Một client bình thường, không đang chạy bên trong Fork/Join computation, có thể:

```java
ForkJoinPool pool = new ForkJoinPool(4);
try {
    long result = pool.invoke(new SumTask(/* tham số */));
    // Dùng kết quả khi cây tính toán đã hoàn tất.
} finally {
    pool.shutdown();
}
```

Đây là **snippet khái niệm**, `SumTask` là class mà bạn tự viết. `pool.invoke(task)` thực hiện công việc và chờ kết quả, ném lỗi unchecked nếu task fail; gọi từ main thread có thể block. `pool.submit(task)` trả Future-like task để caller đợi sau, còn `execute(task)` chỉ khởi động.

Đừng gọi `new ForkJoinPool(...)` ở mỗi phần tử hoặc mỗi subtask. Bên trong `compute()`, dùng `fork`/`join`/`compute` của subtasks để tận dụng pool đang thực thi.

## 3. Cơ chế work stealing

Một `ForkJoinPool` tạo hoặc quản lý các worker threads. Mỗi worker có thể giữ hàng đợi tasks fork ra, và khi worker thiếu việc, nó **thử lấy việc từ worker khác** (work stealing). Điều này phù hợp với cây công việc phân chia không đều: một nhánh xử lý rất nhanh, nhánh khác nặng hơn; worker rảnh có thể giúp xử lý các subtasks đang chờ.

```text
Worker 1: task ROOT
   |
   +-- fork LEFT     [queue của Worker 1]
   |
   +-- compute RIGHT trên chính Worker 1
             |
             +-- fork RIGHT-LEFT
             +-- compute RIGHT-RIGHT

Worker 2: đang rảnh -> steal LEFT -> tính một nhánh khác
Worker 3: đang rảnh -> có thể steal một task khả dụng
Worker 1: join LEFT nếu cần kết quả
```

Điều quan trọng:

- Pool cố gắng **giữ workers bận với task hữu ích**, không đảm bảo cứ fork là mở thêm một thread.
- Số tasks có thể **nhiều hơn** số worker threads. Tasks là các đơn vị công việc nhẹ hơn threads.
- Target parallelism không phải giới hạn tuyệt đối của mọi thread nội bộ, cũng không chứng minh có đúng số đó đang chạy ở từng thời điểm.
- Không được suy từ `getStealCount()` rằng mọi thực thi sẽ có ít nhất một lần steal; bộ đếm có thể bằng 0 với bài nhỏ hoặc lịch scheduling khác.
- Work stealing giúp cân bằng tải, **không giải quyết data races, blocking I/O hay vòng chờ lẫn nhau**.

### 3.1. Local queue và tính locality

Theo triển khai Fork/Join, các worker có thể ưu tiên xử lý tasks địa phương theo chính sách thích hợp, còn workers khác steal từ một đầu hàng đợi khác. Điều này có thể cải thiện locality và tránh queue contention. **Không phụ thuộc vào thứ tự LIFO/FIFO cụ thể như một hợp đồng tính đúng đắn**: task scheduling và execution order có thể khác theo JDK, số lõi và tải.

Bài toán chia để trị phải cho **cùng kết quả hợp lệ bất kể các nhánh hoàn tất theo thứ tự nào**. Nếu kết quả dựa vào thứ tự chạy của threads, thiết kế có thể không an toàn hoặc cần một cơ chế gộp có thứ tự riêng.

### 3.2. DAG và quan hệ join

Mô hình fork/join hiệu quả thường là **directed acyclic graph** của dependencies: task cha phụ thuộc các task con, và không có task con lại chờ cha. Nếu A chờ B trong khi B chờ A, work stealing không “biến vòng chờ thành đúng”. Các phép `join` chỉ hợp lý khi dependency graph không có cycle.

Một cây chia đôi tự nhiên:

```text
                 ROOT
              /        \
           LEFT        RIGHT
          /   \        /   \
         A     B      C     D

A,B,C,D chỉ xử lý vùng dữ liệu mà mình sở hữu.
LEFT đợi A,B; RIGHT đợi C,D; ROOT đợi LEFT,RIGHT.
Không có đường từ A quay lại chờ ROOT.
```

Không dùng `Thread.sleep`, `CountDownLatch.await`, `Future.get` của một dịch vụ bên ngoài hoặc I/O không có giới hạn trong task chỉ vì pool có cơ chế work stealing; chờ tài nguyên không được pool quản lý có thể làm nghẽn workers.

## 4. Mẫu fork-one, compute-one, join-one

Đây là mẫu dễ đọc và thường có hiệu quả cho bài toán phân nhánh đôi:

```java
@Override
protected Long compute() {
    if (hi - lo <= threshold) {
        return calculateDirectly(lo, hi);
    }
    int mid = lo + (hi - lo) / 2;
    SumTask left = new SumTask(data, lo, mid, threshold);
    SumTask right = new SumTask(data, mid, hi, threshold);

    left.fork();                  // Đưa nhánh trái thành công việc có thể được steal.
    long rightValue = right.compute(); // Worker hiện tại xử lý nhánh phải.
    long leftValue = left.join();       // Đợi kết quả nhánh trái khi cần.
    return Math.addExact(leftValue, rightValue);
}
```

Đây là **snippet**, các field và method `calculateDirectly` chưa được khai báo. Phần sau có chương trình hoàn chỉnh.

**Vì sao không fork cả hai rồi join cả hai?** Điều đó cũng có thể đúng, nhưng thường tạo thêm công việc đưa vào scheduler khi thread đang chạy có thể **tự tính một nhánh** ngay. Mẫu `fork(left) → compute(right) → join(left)` làm tốt việc cân bằng giữa song song và overhead.

**Tại sao join sau khi compute nhánh còn lại?** Khi task trái đang sẵn sàng cho worker khác, worker hiện tại làm công việc hữu ích. Nếu ngay sau `left.fork()` đã gọi `left.join()`, có thể bỏ lỡ cơ hội overlap tính toán nhánh còn lại.

**Không gọi `fork()` sau đó `join()` rồi mới `right.compute()`** nếu mục tiêu là để hai nhánh có khả năng tiến song song. Trong bài toán CPU-bound với nhánh độc lập, thứ tự fork/computation/join ảnh hưởng cơ hội khai thác parallelism, dù kết quả logic vẫn có thể đúng.

## 5. Ví dụ 1: tính tổng bằng RecursiveTask<Long>

Tạo file `ForkJoinSumDemo.java`:

```java
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveTask;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
public class ForkJoinSumDemo {
  static final class SumTask extends RecursiveTask<Long> {
    private static final long serialVersionUID = 1L;
    final long[] values;
    final int from, to, threshold;
    final AtomicInteger leaves;
    SumTask(long[] values,int from,int to,int threshold,AtomicInteger leaves){
      this.values=values;this.from=from;this.to=to;this.threshold=threshold;this.leaves=leaves;
    }
    @Override protected Long compute(){
      if(to-from<=threshold){
        leaves.incrementAndGet();
        long sum=0;
        for(int i=from;i<to;i++) sum=Math.addExact(sum,values[i]);
        return sum;
      }
      int mid=from+(to-from)/2;
      SumTask left=new SumTask(values,from,mid,threshold,leaves);
      SumTask right=new SumTask(values,mid,to,threshold,leaves);
      left.fork();
      long rightResult=right.compute();
      long leftResult=left.join();
      return Math.addExact(leftResult,rightResult);
    }
  }
  public static void main(String[] args) throws Exception {
    long[] values=new long[16];
    for(int i=0;i<values.length;i++) values[i]=i+1L;
    AtomicInteger leaves=new AtomicInteger();
    ForkJoinPool pool=new ForkJoinPool(4);
    try{
      long result=pool.invoke(new SumTask(values,0,values.length,4,leaves));
      System.out.println("sum="+result);
      System.out.println("leaf-tasks="+leaves.get());
      System.out.println("parallelism="+pool.getParallelism());
    }finally{
      pool.shutdown();
      if(!pool.awaitTermination(5,TimeUnit.SECONDS))pool.shutdownNow();
    }
  }
}
```

Biên dịch/chạy bằng JDK 17+:

```bash
javac -encoding UTF-8 -Xlint:all ForkJoinSumDemo.java
java ForkJoinSumDemo
```

**stdout đã kiểm thử:**

```text
sum=136
leaf-tasks=4
parallelism=4
```

### 5.1. Phân tích cây công việc

Mảng 16 phần tử chứa `1..16`. `threshold=4` nên:

1. Root `[0,16)` tách thành `[0,8)` và `[8,16)`.
2. Mỗi nửa 8 phần tử lại tách thành 2 dải 4 phần tử.
3. Bốn leaf là `[0,4)`, `[4,8)`, `[8,12)` và `[12,16)`.
4. Các leaf lần lượt có tổng 10, 26, 42, 58.
5. Khi combine, `10 + 26 + 42 + 58 = 136`.

`AtomicInteger leaves` chỉ được đưa vào để **đếm leaf trong demo**, vì nhiều tasks có thể cập nhật đồng thời. Trong code tính toán hiệu năng cao, việc ghi chung một atomic counter mỗi leaf cũng có chi phí và có thể trở thành contention; không phải lúc nào nên bật metrics này trong hot path.

`pool.getParallelism()==4` nghĩa **target parallelism của dedicated pool** là 4, không chứng minh cả 4 threads đã hoạt động đồng thời. Kết quả tổng và số leaf **không phụ thuộc scheduling**.

### 5.2. Vì sao dùng Math.addExact?

`long` có giới hạn; phép `+` thường **overflow theo mô hình số nguyên bù hai** và có thể cho kết quả sai nghiệp vụ mà không tự ném exception. `Math.addExact` làm rõ chính sách: **phát hiện overflow bằng `ArithmeticException`**. Nếu dữ liệu là thống kê/tiền tệ và không cho phép overflow, đây là một lựa chọn hợp lý.

Một bài toán chấp nhận arithmetic theo modulo `2^64` có thể dùng cộng thường, nhưng phải nói rõ contract; không đổi ngữ nghĩa một cách vô tình khi song song hóa.

**Quan trọng hơn:** thứ tự combine có thể khác tuần tự; với dữ liệu có số âm lớn/dương lớn, một phép toán `Math.addExact` có thể phát hiện overflow trung gian theo thứ tự cây khác so với một vòng for tuần tự, ngay cả khi kết quả toán học cuối có thể nằm trong miền `long`. Nếu yêu cầu kết quả chính xác không phụ thuộc thứ tự trung gian, dùng số học có miền đủ rộng (`BigInteger` hoặc một thiết kế số học khác) hay chứng minh giới hạn đầu vào, và benchmark vì object allocations có thể lớn.

### 5.3. Ý nghĩa của [from, to)

Trong bài, mọi dải dùng **half-open interval**: `[from,to)` bao gồm chỉ số `from`, không bao gồm `to`. Nó cho phép:

- Hai nhánh `[from,mid)` và `[mid,to)` **không chồng lấp**.
- Độ dài dải là `to-from`.
- Mảng rỗng `[0,0)` có độ dài 0.
- Vòng `for(int i=from;i<to;i++)` phù hợp.
- Dễ chứng minh mỗi phần tử chỉ xử lý một lần.

Chọn `mid=from+(to-from)/2` để hạn chế overflow khi tính trung điểm, so với `mid=(from+to)/2` nếu hai số lớn.

## 6. Ví dụ 2: tìm max và xử lý input rỗng

Đối với tổng, phép gộp có phần tử trung hòa `0`. Đối với max, mảng **rỗng** có thể không có max theo nghiệp vụ. Tránh tự trả `0` khi tất cả phần tử âm.

Tạo `ForkJoinMaxDemo.java`:

```java
import java.util.concurrent.*;
public class ForkJoinMaxDemo {
  static final class MaxTask extends RecursiveTask<Integer> {
    private static final long serialVersionUID=1L;
    final int[] values;final int from,to,threshold;
    MaxTask(int[] values,int from,int to,int threshold){
      this.values=values;this.from=from;this.to=to;this.threshold=threshold;
    }
    @Override protected Integer compute(){
      if(to-from<=threshold){
        int max=Integer.MIN_VALUE;
        for(int i=from;i<to;i++)max=Math.max(max,values[i]);
        return max;
      }
      int mid=from+(to-from)/2;
      MaxTask left=new MaxTask(values,from,mid,threshold);
      left.fork();
      int right=new MaxTask(values,mid,to,threshold).compute();
      return Math.max(left.join(),right);
    }
  }
  static int maximum(ForkJoinPool pool,int[] values){
    if(values.length==0)throw new IllegalArgumentException("Empty array");
    return pool.invoke(new MaxTask(values,0,values.length,3));
  }
  public static void main(String[] args)throws Exception{
    ForkJoinPool pool=new ForkJoinPool(2);
    try{
      System.out.println("max="+maximum(pool,new int[]{-5,7,2,12,-3,4}));
      System.out.println("negative-max="+maximum(pool,new int[]{-9,-3,-7}));
      boolean emptyRejected=false;
      try{maximum(pool,new int[0]);}catch(IllegalArgumentException ex){emptyRejected=true;}
      System.out.println("empty-rejected="+emptyRejected);
    }finally{pool.shutdown();pool.awaitTermination(5,TimeUnit.SECONDS);}
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all ForkJoinMaxDemo.java
java ForkJoinMaxDemo
```

**stdout đã kiểm thử:**

```text
max=12
negative-max=-3
empty-rejected=true
```

**Vì sao bài này đáng học?** Việc song song hóa không được thay đổi semantics của phép reduce. Nếu dùng `max=0` ở leaf, một mảng toàn số âm sẽ cho kết quả **0 không tồn tại trong dữ liệu**. `Integer.MIN_VALUE` là identity phù hợp khi có ít nhất một phần tử, còn wrapper `maximum` chủ động reject mảng rỗng.

Có thể định nghĩa API trả `OptionalInt` cho đầu vào rỗng; trong demo chọn `IllegalArgumentException` rõ ràng để nhấn mạnh precondition.

**Nguyên tắc:** trước khi chia để trị, xác định phép combine có phần tử trung hòa, tính kết hợp, điều kiện dừng và behavior của empty/invalid input.

## 7. Ví dụ 3: RecursiveAction cho xử lý mảng tại các vùng riêng biệt

Không phải task nào cũng cần trả giá trị. Nếu mỗi subtask **sửa chính vùng dữ liệu mà nó sở hữu**, có thể dùng `RecursiveAction`.

Tạo `ForkJoinTransformDemo.java`:

```java
import java.util.Arrays;
import java.util.concurrent.*;
public class ForkJoinTransformDemo {
  static final class DoubleTask extends RecursiveAction {
    private static final long serialVersionUID=1L;
    final int[] values;final int lo,hi,threshold;
    DoubleTask(int[] values,int lo,int hi,int threshold){
      this.values=values;this.lo=lo;this.hi=hi;this.threshold=threshold;
    }
    @Override protected void compute(){
      if(hi-lo<=threshold){
        for(int i=lo;i<hi;i++) values[i]=Math.multiplyExact(values[i],2);
        return;
      }
      int mid=lo+(hi-lo)/2;
      DoubleTask left=new DoubleTask(values,lo,mid,threshold);
      DoubleTask right=new DoubleTask(values,mid,hi,threshold);
      left.fork();right.compute();left.join();
    }
  }
  public static void main(String[] args)throws Exception{
    int[] values={1,2,3,4,5,6,7,8};
    ForkJoinPool pool=new ForkJoinPool(4);
    try{
      pool.invoke(new DoubleTask(values,0,values.length,2));
      System.out.println("values="+Arrays.toString(values));
      System.out.println("length="+values.length);
    }finally{pool.shutdown();pool.awaitTermination(5,TimeUnit.SECONDS);}
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all ForkJoinTransformDemo.java
java ForkJoinTransformDemo
```

**stdout đã kiểm thử:**

```text
values=[2, 4, 6, 8, 10, 12, 14, 16]
length=8
```

### 7.1. Vì sao chia mảng vẫn có thể an toàn?

Mỗi leaf nhận một interval không chồng lấn. `left` không ghi phần tử mà `right` ghi. Khi `pool.invoke(...)` trả thành công, mọi nhánh cần thiết đã hoàn tất và main có thể quan sát mảng đã biến đổi.

**Tuy nhiên “cùng một array” không đồng nghĩa luôn an toàn:**

- Nếu hai subtasks ghi **cùng index**, có data race hoặc lost update.
- Nếu một subtask sửa metadata/`List` structure trong khi subtask khác duyệt, có thể gặp lỗi hoặc kết quả không xác định.
- Nếu mỗi leaf ghi một shared `ArrayList.add(...)`, `ArrayList` không thread-safe; cần thiết kế khác.
- Nếu mỗi task ghi một slot khác nhau nhưng ở cùng cache line, vẫn có thể bị **false sharing/cache coherence overhead** trên nhiều CPU.
- Nếu có một consumer đọc array **trước khi root task hoàn tất**, nó có thể quan sát trạng thái xử lý dở.

**Hướng tốt:** làm trên các dải riêng; combine vào partial results; hoặc merge sau `join` khi mọi nhánh con hoàn thành.

### 7.2. Khi tác vụ có thể throw lỗi

`Math.multiplyExact` ném `ArithmeticException` nếu nhân vượt miền `int`. Với `RecursiveAction` đang sửa mảng tại chỗ, một vài leaf khác có thể đã sửa dữ liệu trước khi task root fail. **Fork/Join không tự rollback dữ liệu của các nhánh đã hoàn tất**. Nếu yêu cầu atomicity, dùng output buffer riêng và publish chỉ sau khi toàn bộ tác vụ thành công, hoặc thiết kế transaction tại tầng ứng dụng.

## 8. Ví dụ 4: merge sort song song với bộ nhớ phụ

Merge sort là ví dụ divide-and-conquer kinh điển:

1. Nếu đoạn ngắn, sort trực tiếp.
2. Nếu đoạn dài, tách thành trái/phải.
3. Fork một nửa, compute nửa còn lại.
4. Join để chắc chắn **hai nửa đã được sort**.
5. Merge hai nửa theo thứ tự vào dải gốc.

**Phân biệt từ đầu:** Fork/Join có thể giúp xử lý **hai nửa sort độc lập**; bước merge tại một node vẫn cần tuần tự trong chương trình mẫu. Nên không được kỳ vọng tốc độ tăng tuyến tính mãi khi thêm threads.

Tạo `ForkJoinMergeSortDemo.java`:

```java
import java.util.Arrays;
import java.util.concurrent.*;
public class ForkJoinMergeSortDemo {
  static final class SortTask extends RecursiveAction {
    private static final long serialVersionUID=1L;
    final int[] values, scratch;final int lo,hi,threshold;
    SortTask(int[] values,int[] scratch,int lo,int hi,int threshold){
      this.values=values;this.scratch=scratch;this.lo=lo;this.hi=hi;this.threshold=threshold;
    }
    @Override protected void compute(){
      if(hi-lo<=threshold){Arrays.sort(values,lo,hi);return;}
      int mid=lo+(hi-lo)/2;
      SortTask left=new SortTask(values,scratch,lo,mid,threshold);
      left.fork();
      new SortTask(values,scratch,mid,hi,threshold).compute();
      left.join();
      System.arraycopy(values,lo,scratch,lo,hi-lo);
      int a=lo,b=mid;
      for(int k=lo;k<hi;k++){
        if(a>=mid)values[k]=scratch[b++];
        else if(b>=hi)values[k]=scratch[a++];
        else if(scratch[a]<=scratch[b])values[k]=scratch[a++];
        else values[k]=scratch[b++];
      }
    }
  }
  public static void main(String[] args)throws Exception{
    int[] values={8,3,5,2,9,1,4,7,6,0};
    int[] scratch=new int[values.length];
    ForkJoinPool pool=new ForkJoinPool(4);
    try{
      pool.invoke(new SortTask(values,scratch,0,values.length,3));
      System.out.println("sorted="+Arrays.toString(values));
      System.out.println("first="+values[0]+",last="+values[values.length-1]);
    }finally{pool.shutdown();pool.awaitTermination(5,TimeUnit.SECONDS);}
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all ForkJoinMergeSortDemo.java
java ForkJoinMergeSortDemo
```

**stdout đã kiểm thử:**

```text
sorted=[0, 1, 2, 3, 4, 5, 6, 7, 8, 9]
first=0,last=9
```

### 8.1. Vì sao một scratch array dùng chung vẫn hợp lệ trong ví dụ?

Những nhánh ở **cùng mức** luôn xử lý các dải `[lo,mid)` và `[mid,hi)` không chồng lấp. Mỗi nhánh chỉ copy/merge trong **chính dải** của nó. Parent chỉ bắt đầu merge sau khi đã `join` nhánh fork và tính xong nhánh còn lại. Vì vậy parent không copy/ghi lên dải của hai children khi chúng vẫn đang chạy.

Điều này **không đồng nghĩa mọi scratch array dùng chung đều an toàn**: nếu thay code để hai tasks cùng dùng `scratch[0..n)` làm vùng tạm bất kể interval, kết quả sẽ lỗi. Tính đúng phụ thuộc cách chia **disjoint ranges**, không chỉ phụ thuộc việc có `join`.

### 8.2. Độ phức tạp

Merge sort có công việc tổng O(n log n) và cần O(n) scratch array trong thiết kế demo. Các nhánh sort có thể làm đồng thời, nhưng merge root vẫn tiêu tốn O(n) công việc trong một nhánh. Vì vậy speedup phụ thuộc kích thước mảng, ngưỡng và memory bandwidth; với mảng rất nhỏ, `Arrays.sort` tuần tự có thể hiệu quả hơn.

**Trong sản phẩm thật:** Java có `Arrays.parallelSort` cho những kiểu dữ liệu phù hợp, được hỗ trợ hiện đại và sử dụng mô hình sorting song song bên dưới. Khi chỉ cần sort mảng, thường ưu tiên API thư viện đã kiểm thử/benchmark thay vì tự viết merge sort. Bài tập này để hiểu divide-and-conquer, không phải yêu cầu thay thế `Arrays.parallelSort`.

## 9. Chọn ngưỡng dừng: granularity quan trọng hơn số lần fork

Mỗi task có `threshold`. Nếu đoạn có độ dài không quá threshold, nó xử lý **trực tiếp trên cùng thread** mà không fork thêm.

- Threshold **quá nhỏ** → rất nhiều leaf/tasks, nhiều object allocations và scheduling, có thể chậm vì overhead.
- Threshold **quá lớn** → ít leaf/tasks, thiếu parallelism, một worker làm quá nhiều việc.
- Threshold **phù hợp** → đủ tasks cho workers có việc để steal, nhưng một leaf thực hiện đủ công việc hữu ích trước khi kết thúc.

**Không có ngưỡng chuẩn áp dụng mọi bài toán.** Threshold 1.024 phần tử có thể quá nhỏ nếu phép toán mỗi phần tử rẻ, nhưng quá lớn nếu mỗi phần tử làm hashing/parse rất nặng. Cần benchmark trên dữ liệu/CPU mục tiêu.

### 9.1. Ví dụ runnable: cùng kết quả nhưng số leaf khác nhau

Tạo `ForkJoinThresholdDemo.java`:

```java
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;
public class ForkJoinThresholdDemo {
  static final class SumTask extends RecursiveTask<Long> {
    private static final long serialVersionUID=1L;
    final int[] data;final int lo,hi,threshold;final AtomicInteger leaves;
    SumTask(int[] data,int lo,int hi,int threshold,AtomicInteger leaves){
      this.data=data;this.lo=lo;this.hi=hi;this.threshold=threshold;this.leaves=leaves;
    }
    @Override protected Long compute(){
      if(hi-lo<=threshold){
        leaves.incrementAndGet();
        long sum=0;for(int i=lo;i<hi;i++)sum+=data[i];
        return sum;
      }
      int mid=lo+(hi-lo)/2;
      SumTask left=new SumTask(data,lo,mid,threshold,leaves);
      left.fork();
      long right=new SumTask(data,mid,hi,threshold,leaves).compute();
      return left.join()+right;
    }
  }
  public static void main(String[] args)throws Exception{
    int[] data=new int[32];
    for(int i=0;i<data.length;i++)data[i]=i+1;
    ForkJoinPool pool=new ForkJoinPool(4);
    try{
      AtomicInteger large=new AtomicInteger(),small=new AtomicInteger();
      long a=pool.invoke(new SumTask(data,0,data.length,8,large));
      long b=pool.invoke(new SumTask(data,0,data.length,2,small));
      System.out.println("threshold8-leaves="+large.get());
      System.out.println("threshold2-leaves="+small.get());
      System.out.println("same-sum="+(a==b&&a==528));
    }finally{pool.shutdown();pool.awaitTermination(5,TimeUnit.SECONDS);}
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all ForkJoinThresholdDemo.java
java ForkJoinThresholdDemo
```

**stdout đã kiểm thử:**

```text
threshold8-leaves=4
threshold2-leaves=16
same-sum=true
```

Cùng mảng 32 phần tử:

- Với threshold=8: 4 leaves.
- Với threshold=2: 16 leaves.
- Cả hai cho tổng 528, vì logic reduce độc lập threshold.
- 16 leaves **không cam kết chạy nhanh hơn 4 leaves**.

`AtomicInteger` đếm số leaf một cách thread-safe, nhưng bản thân việc đếm là instrumentation; đo performance nên tách bộ đếm khỏi hot path để tránh benchmark bị méo.

### 9.2. Ngưỡng cần dương và luôn phải tiến đến điều kiện dừng

Nếu `threshold <= 0`, một đoạn chỉ còn một phần tử có thể tiếp tục bị chia thành những đoạn rỗng và không tiến, dẫn đến task explosion hoặc stack overflow. Một API production phải validate threshold:

```java
if (threshold < 1) {
    throw new IllegalArgumentException("threshold must be positive");
}
```

Đây là snippet precondition, không phải chương trình độc lập.

Ngoài threshold, kiểm tra `from >= 0`, `to <= data.length` và `from <= to`. Đừng cho untrusted input tạo range âm/khổng lồ hoặc recursion theo depth không giới hạn.

### 9.3. Ngưỡng theo khối lượng công việc, không nhất thiết theo phần tử

Một số bài toán có chi phí không đồng đều:

- Dữ liệu text: record dài hay ngắn, Unicode decoding, regex.
- Cây tìm kiếm: mỗi node có số con/chi phí khác nhau.
- Phân tích ảnh: vùng trống và vùng phức tạp khác nhau.
- Dữ liệu sparse: một dải chứa ít phần tử thực, dải khác chứa nhiều.

Có thể cân nhắc threshold dựa trên ước lượng **work** thay vì chỉ số phần tử, hoặc dùng partition strategy thích hợp. Work stealing giúp một phần, nhưng không sửa được cách chia quá mất cân bằng.

## 10. Math của reduction: phép combine có thật sự phù hợp?

Để cây chia nhánh tính ra kết quả nhất quán, phép gộp cần đáp ứng một số tính chất.

### 10.1. Associativity

Tính kết hợp toán học:

```text
(a ⊕ b) ⊕ c = a ⊕ (b ⊕ c)
```

Nếu phép kết hợp associative và leaves cover toàn bộ input đúng một lần, ta có thể thay đổi cấu trúc cây mà vẫn có kết quả theo mô hình toán học.

Ví dụ:

- `max` trên tập không rỗng là associative.
- Tổng số nguyên **không tràn trong miền được chứng minh** là associative theo toán học.
- Tổng theo `BigInteger` là exact nhưng có overhead allocations.
- Nối chuỗi là associative về nội dung, nhưng **thứ tự** các đoạn phải giữ đúng; không thể tùy tiện đảo các nhánh.

### 10.2. Không phải phép combine nào cũng associative

**Phép trừ** không associative:

```text
(10 - 3) - 2 = 5
10 - (3 - 2) = 9
```

Không được chia để trị bằng cách trừ mỗi nhánh theo thứ tự tùy ý rồi kỳ vọng kết quả giống vòng lặp.

**Số thực floating-point** cũng có vấn đề do làm tròn:

```text
(a + b) + c có thể khác a + (b + c) khi tính bằng double.
```

Ví dụ giá trị rất lớn cộng với số nhỏ rồi trừ giá trị lớn có thể mất độ chính xác. Nếu yêu cầu reproducibility bit-for-bit với sequential baseline, cần định nghĩa reduction order, phương pháp số học ổn định hoặc dùng kiểu số phù hợp; song song hóa không được lén thay hợp đồng kết quả.

### 10.3. Identity của reduce

Một số phép gộp cần phần tử trung hòa:

- Tổng: 0.
- Nhân: 1 (với điều kiện overflow xử lý đúng).
- AND: true, OR: false.
- Max: có thể dùng MIN_VALUE làm identity cho các `int` values, nhưng API mảng rỗng có thể nên trả empty/throw tùy nghiệp vụ.
- Trộn lists: empty list, nhưng phải giữ order và tránh append vào một shared mutable list từ nhiều workers.

**Tách rõ tính đúng của phép toán với tính đúng của scheduling.** Work stealing không giúp sửa bug identity hoặc phép combine.

## 11. Lỗi trong leaf: exception đi qua join/invoke như thế nào?

`ForkJoinTask` hoạt động như Future nhưng có phương thức `join` riêng.

- `join()` có thể **ném unchecked exception** (hoặc Error) khi task fail.
- `ForkJoinPool.invoke(task)` ném unchecked exception/Error khi computation thất bại.
- `ForkJoinTask.get()` theo hợp đồng `Future` có thể ném `ExecutionException` đối với lỗi trong task, và thêm `InterruptedException`.
- Một subtask ném exception không đảm bảo mọi sibling task đang chạy đã được dừng ngay lập tức.
- Các side effects ở sibling/leaf có thể đã xảy ra **trước khi root thất bại**.

### 11.1. Ví dụ runnable: phát hiện số học overflow

Tạo `ForkJoinFailureDemo.java`:

```java
import java.util.concurrent.*;
public class ForkJoinFailureDemo {
  static final class CheckedSumTask extends RecursiveTask<Long> {
    private static final long serialVersionUID=1L;
    final long[] values;final int lo,hi;
    CheckedSumTask(long[] values,int lo,int hi){this.values=values;this.lo=lo;this.hi=hi;}
    @Override protected Long compute(){
      if(hi-lo<=1)return hi==lo?0L:values[lo];
      int mid=lo+(hi-lo)/2;
      CheckedSumTask left=new CheckedSumTask(values,lo,mid);
      left.fork();
      long right=new CheckedSumTask(values,mid,hi).compute();
      return Math.addExact(left.join(),right);
    }
  }
  public static void main(String[] args)throws Exception{
    ForkJoinPool pool=new ForkJoinPool(2);
    try{
      boolean overflow=false;
      try{
        pool.invoke(new CheckedSumTask(new long[]{Long.MAX_VALUE,1L},0,2));
      }catch(ArithmeticException ex){overflow=true;}
      System.out.println("overflow-detected="+overflow);
      System.out.println("pool-open="+!pool.isShutdown());
    }finally{pool.shutdown();pool.awaitTermination(5,TimeUnit.SECONDS);}
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all ForkJoinFailureDemo.java
java ForkJoinFailureDemo
```

**stdout đã kiểm thử:**

```text
overflow-detected=true
pool-open=true
```

`Math.addExact(Long.MAX_VALUE,1L)` ném `ArithmeticException`. `pool.invoke` truyền lỗi unchecked đến caller; task không silently trả giá trị bị tràn. Pool vẫn tồn tại trước khi vào `finally` và shutdown.

**Cần chú ý:** bắt lỗi tại root không tự rollback mảng, file, database hay các side effects mà subtasks đã làm. Với tính toán thuần/immutable data, retry hoặc trả lỗi thường đơn giản hơn nhiều so với công việc có side effects.

## 12. Cancellation, interruption và phạm vi bảo đảm

Một `ForkJoinTask` có trạng thái cancel và các phương thức `cancel(boolean)`, `isCancelled()`. Tuy nhiên:

- `cancel(true)` **không phải cam kết** ngắt thread đang thực hiện tác vụ bằng interrupt. Theo `ForkJoinTask`, cancellation chủ yếu cập nhật trạng thái; execution có thể vẫn tiếp tục trong một số tình huống.
- `join()` trên task bị cancel có thể ném `CancellationException`.
- `shutdownNow()` là yêu cầu dừng/cancel tốt nhất theo framework, **không phải transaction rollback**.
- Một task thuần CPU nặng có thể cần **cooperative cancellation** thông qua token/flag mà code của bạn chủ động kiểm tra ở các vòng lặp hoặc trước khi chia nhánh mới.
- Nếu dùng cancellation flag chung, phải có visibility semantics phù hợp, ví dụ `AtomicBoolean` hoặc `volatile`.

### 12.1. Ví dụ runnable: task cancel trước khi chạy

Tạo `ForkJoinCancellationDemo.java`:

```java
import java.util.concurrent.*;
public class ForkJoinCancellationDemo {
  static final class ValueTask extends RecursiveTask<Integer>{
    private static final long serialVersionUID=1L;
    @Override protected Integer compute(){return 42;}
  }
  public static void main(String[] args){
    ValueTask task=new ValueTask();
    boolean accepted=task.cancel(false);
    boolean joinRejected=false;
    try{task.join();}catch(CancellationException ex){joinRejected=true;}
    System.out.println("cancel-accepted="+accepted);
    System.out.println("is-cancelled="+task.isCancelled());
    System.out.println("join-rejected="+joinRejected);
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all ForkJoinCancellationDemo.java
java ForkJoinCancellationDemo
```

**stdout đã kiểm thử:**

```text
cancel-accepted=true
is-cancelled=true
join-rejected=true
```

Demo **cố ý cancel trước khi submit** để hành vi xác định; nó không chứng minh rằng một task đã chạy có thể bị dừng giữa phép tính theo ý muốn. Trong hệ thống thật, thiết kế abort signal và kiểm tra token theo các safe points, đảm bảo pool/task resources được giải phóng.

**Không tái sử dụng một `ForkJoinTask` đã hoàn thành/cancel tùy tiện như object command tái khởi chạy.** Thông thường, mỗi lần tính mới tạo một cây task mới; các cơ chế `reinitialize` là API chuyên biệt, không cần cho pattern divide-and-conquer thông thường.

## 13. Pool riêng hay commonPool?

`ForkJoinPool.commonPool()` là một pool **dùng chung**, được nhiều API JDK và code ứng dụng có thể sử dụng. Nó giúp tránh tạo pools tràn lan cho những công việc nhỏ, và phù hợp với nhiều tác vụ CPU ngắn, độc lập.

**Ưu điểm của commonPool:**

- Giảm overhead quản lý pools nếu tasks phù hợp.
- Scheduler/work stealing được tái sử dụng.
- Thuận tiện trong code nhỏ hoặc những thư viện tận dụng common execution.

**Rủi ro:**

- Các subsystem độc lập có thể tranh chấp cùng threads.
- Một thư viện lạm dụng I/O/blocking trong commonPool có thể gây ảnh hưởng lan sang phần khác.
- Khó áp dụng isolation, quota, SLA từng tenant/workload.
- Kích thước pool phụ thuộc môi trường và cấu hình JVM, không nên hard-code giả định.

**Pool riêng** phù hợp khi cần cô lập workload, điều chỉnh parallelism, monitoring và shutdown do component sở hữu. Nhưng nếu một microservice tạo hàng trăm `new ForkJoinPool(8)` cho mỗi request, overhead/memory/threads có thể rất lớn.

### 13.1. Lifecycle của dedicated ForkJoinPool

Một pool do bạn tạo có quyền sở hữu rõ:

```java
ForkJoinPool pool = new ForkJoinPool(parallelism);
try {
    return pool.invoke(rootTask);
} finally {
    pool.shutdown();
    // Caller/service quyết định awaitTermination với deadline.
}
```

Đây là snippet, `rootTask` và `parallelism` phải hợp lệ. Nếu dùng pool làm member của service, không tạo/close nó trong mỗi request; tạo một lần và shutdown lúc service kết thúc.

**Quan trọng về Java version:** overload đóng bằng `ForkJoinPool.close()` được thêm trong những phiên bản Java **sau Java 17** (API Java 21 có nó). Để ví dụ **chạy trên Java 17+**, bài dùng `shutdown()` và `awaitTermination(...)`, không gọi `close()` trực tiếp. `commonPool()` không nên bị shutdown bởi một module; JavaDoc ghi rằng shutdown không thay đổi run state của common pool.

### 13.2. Parallelism khác số task

`new ForkJoinPool(4)` đặt **target parallelism=4**, không giới hạn số task. Một cây có thể tạo 1.000 leaf tasks dù pool chỉ nhắm 4 workers. Cách scheduling tùy runtime, trạng thái work stealing và liệu tasks có thực sự đủ lớn.

Không dùng `Thread.activeCount()` hoặc đếm names của threads để kết luận performance. Dùng `getParallelism` để biết target level và metrics như `getActiveThreadCount`, `getStealCount`, `getQueuedTaskCount` làm **ước lượng giám sát**, không phải invariant cho business logic.

### 13.3. So sánh với parallel streams

Java có `Stream.parallel()` và `Arrays.parallelSort` ở những API hiện đại. Parallel stream có thể phân chia và reduce dữ liệu mà không cần tự viết `RecursiveTask`. Với một reduce đơn giản, cách này thường gọn:

```java
long result = Arrays.stream(values)
        .parallel()
        .asLongStream()
        .sum();
```

Đây là snippet, `values` là `int[]`. Parallel streams thường dùng common fork/join machinery theo implementation JDK thông thường, nhưng không đồng nghĩa bạn có toàn quyền điều phối cách chia, threshold hoặc scheduling như class `RecursiveTask` tự viết.

**Chọn abstraction theo mục tiêu:**

- Chỉ cần sum/filter/map/reduce: xem `Stream` API trước.
- Cần kiểm soát cách chia cây, threshold, custom merge và task metrics: `ForkJoinPool`/`RecursiveTask` phù hợp hơn.
- Chỉ cần sort mảng: ưu tiên `Arrays.sort`/`Arrays.parallelSort` theo workload.
- Nhiều công việc chờ I/O: cân nhắc asynchronous APIs, bounded executor hoặc virtual threads trên JDK hỗ trợ; không ép thành CPU-bound fork/join.
- Một bài rất nhỏ: vòng for tuần tự thường rõ ràng hơn.

### 13.4. Ví dụ runnable: Fork/Join, parallel stream và tuần tự cùng kết quả

Tạo `ForkJoinVsStreamDemo.java`:

```java
import java.util.Arrays;
import java.util.concurrent.*;
public class ForkJoinVsStreamDemo {
  static final class SumTask extends RecursiveTask<Long>{
    private static final long serialVersionUID=1L;
    final int[] items;final int lo,hi;
    SumTask(int[] items,int lo,int hi){this.items=items;this.lo=lo;this.hi=hi;}
    @Override protected Long compute(){
      if(hi-lo<=3){long sum=0;for(int i=lo;i<hi;i++)sum+=items[i];return sum;}
      int mid=lo+(hi-lo)/2;
      SumTask left=new SumTask(items,lo,mid);
      left.fork();
      long right=new SumTask(items,mid,hi).compute();
      return left.join()+right;
    }
  }
  public static void main(String[] args)throws Exception{
    int[] data={1,2,3,4,5,6,7,8,9,10};
    ForkJoinPool pool=new ForkJoinPool(2);
    try{
      long forkJoin=pool.invoke(new SumTask(data,0,data.length));
      long stream=Arrays.stream(data).parallel().asLongStream().sum();
      long sequential=Arrays.stream(data).asLongStream().sum();
      System.out.println("forkjoin="+forkJoin);
      System.out.println("parallel-stream="+stream);
      System.out.println("sequential="+sequential);
      System.out.println("same-result="+(forkJoin==stream&&stream==sequential));
    }finally{pool.shutdown();pool.awaitTermination(5,TimeUnit.SECONDS);}
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all ForkJoinVsStreamDemo.java
java ForkJoinVsStreamDemo
```

**stdout đã kiểm thử:**

```text
forkjoin=55
parallel-stream=55
sequential=55
same-result=true
```

**Không dùng stdout này để khẳng định tốc độ của ba cách.** Chương trình chỉ xác nhận **tính đúng** với 10 số nguyên và ngữ nghĩa phù hợp. Đo hiệu năng cần warmup, JIT, input sizes thực tế, CPU availability và benchmark setup đúng (ví dụ JMH).

## 14. Blocking I/O và ManagedBlocker

`ForkJoinPool` hoạt động tốt khi workers chủ yếu làm CPU work và dùng `fork/join` do framework quản lý. Nếu tasks đi chờ:

- HTTP response.
- Database JDBC.
- File/network storage latency.
- Locks, semaphore hoặc latch do ứng dụng quản lý.
- Một tác vụ khác không có cơ chế trợ giúp tiến triển phù hợp.

...thì một worker có thể bị giữ trong trạng thái block và pool khó dự đoán throughput. Work stealing **không thể lấy lại một worker đang blocked** chỉ bằng việc có task ở queue.

`ForkJoinPool.ManagedBlocker` cho phép task **thông báo với pool** rằng nó sắp thực hiện một thao tác có thể blocking. Pool có thể cấp thêm workers để bù parallelism khi điều kiện cho phép. Tuy nhiên:

- **Không cam kết** luôn thêm thread hoặc khắc phục mọi kiểu blocking/deadlock.
- Không thay thế thiết kế async I/O hoặc chọn executor phù hợp.
- Không nên dùng để biện minh cho hàng triệu tasks chờ network vô hạn trong commonPool.
- Nếu A đợi B còn B lại phụ thuộc lock do A giữ, thêm workers cũng không phá được vòng chờ logic.
- Phải implement `ManagedBlocker.isReleasable()` và `block()` đúng contract.

### 14.1. Ví dụ runnable: ManagedBlocker cho một latch demo

Tạo `ForkJoinManagedBlockDemo.java`:

```java
import java.util.concurrent.*;
public class ForkJoinManagedBlockDemo {
  static final class Gate implements ForkJoinPool.ManagedBlocker {
    private final CountDownLatch ready;
    Gate(CountDownLatch ready){this.ready=ready;}
    @Override public boolean block()throws InterruptedException{
      ready.await();return true;
    }
    @Override public boolean isReleasable(){return ready.getCount()==0L;}
  }
  static final class WaitTask extends RecursiveTask<String> {
    private static final long serialVersionUID=1L;
    private final transient CountDownLatch gate;
    WaitTask(CountDownLatch gate){this.gate=gate;}
    @Override protected String compute(){
      try{
        ForkJoinPool.managedBlock(new Gate(gate));
        return "OPEN";
      }catch(InterruptedException ex){
        Thread.currentThread().interrupt();
        return "INTERRUPTED";
      }
    }
  }
  public static void main(String[] args)throws Exception{
    CountDownLatch gate=new CountDownLatch(1);
    ForkJoinPool pool=new ForkJoinPool(1);
    try{
      ForkJoinTask<String> waiting=pool.submit(new WaitTask(gate));
      gate.countDown();
      System.out.println("managed-result="+waiting.get(5,TimeUnit.SECONDS));
      System.out.println("pool-parallelism="+pool.getParallelism());
    }finally{gate.countDown();pool.shutdown();pool.awaitTermination(5,TimeUnit.SECONDS);}
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all ForkJoinManagedBlockDemo.java
java ForkJoinManagedBlockDemo
```

**stdout đã kiểm thử:**

```text
managed-result=OPEN
pool-parallelism=1
```

**Ý nghĩa:** `Gate.isReleasable` kiểm tra latch đã mở chưa; `Gate.block` chờ đến khi latch được mở, rồi trả true. `managedBlock` gọi theo protocol cho đến khi barrier đã thỏa, đồng thời cho pool cơ hội quản lý parallelism. Main chủ động mở latch và đợi kết quả với deadline.

**Đây không phải benchmark về khả năng pool tăng số worker threads:** demo mở latch ngay nên không bảo đảm pool cần cấp thread thay thế. Output chỉ chứng minh ManagedBlocker contract, không chứng minh có một thread mới được tạo.

`transient` ở field `gate` cho phép code demo biên dịch sạch với `javac -Xlint:all` vì `ForkJoinTask` là serializable trong khi `CountDownLatch` không serializable. Task này **chỉ hoạt động nội bộ trong cùng JVM**, không được thiết kế để serialize/deserialize. Đừng coi `transient` là giải pháp serialization cho task có state bất đồng bộ.

### 14.2. Nếu thật sự cần xử lý I/O nhiều

Thường hợp lý hơn:

- Dùng executor có giới hạn theo số connections, quotas và backpressure.
- Dùng asynchronous network/file APIs nếu phù hợp.
- Với Java 21+ có thể cân nhắc virtual threads cho blocking I/O, nhưng vẫn cần giới hạn tài nguyên bên ngoài (DB pool, endpoint, buffers).
- Để CPU-bound reductions trong pool riêng, tránh tranh chấp với tasks chờ I/O dài.
- Nếu bắt buộc `ManagedBlocker`, kiểm thử under load và theo dõi worker expansion/queue latency; không dùng mù quáng.

## 15. Các giới hạn thiết kế: shared state, locks, false sharing và nested pools

### 15.1. Shared mutable collection

Anti-pattern:

```java
List<Integer> results = new ArrayList<>();
// Nhiều RecursiveAction cùng gọi results.add(value).
```

Đây là snippet **sai nếu add đồng thời**, vì `ArrayList` không thread-safe và có thể mất dữ liệu hoặc hỏng nội dung. Giải pháp không chỉ là đồng bộ mọi lần `add` (tạo lock hotspot), mà thường là:

- Mỗi task tính **partial result** rồi parent combine sau `join`.
- Ghi kết quả vào **vùng array không chồng lấp**.
- Khi cần collector, dùng API/concurrent data structure đúng semantics và đánh giá contention.
- Nếu kết quả cần thứ tự, combine theo thứ tự dải, không theo thứ tự task hoàn tất.

### 15.2. Lock hoặc synchronized quanh toàn bộ leaf

Nếu mỗi leaf cùng vào một khóa bao quanh phần tính toán, về thực chất bạn đã tuần tự hóa bottleneck. Fork/Join vẫn tạo task overhead mà không được song song thật.

**Giữ critical section ngắn** và chỉ khi cần. Một thiết kế không chia sẻ mutable state thường vừa dễ chứng minh đúng vừa chạy tốt hơn.

### 15.3. False sharing

Hai workers có thể ghi hai biến hoặc phần tử mảng **khác nhau nhưng cùng cache line**. CPU vẫn phải đồng bộ cache line giữa cores, làm giảm throughput. Đây là overhead phần cứng, không nhất thiết data race.

Để đo vấn đề này, dùng profiler/benchmark có workload thực; không tự thêm padding/Unsafe hoặc cấu trúc bộ nhớ phức tạp vào mọi task. Partition theo vùng liên tiếp đủ lớn thường có ích cho locality.

### 15.4. Nested pool và blocking join sai chỗ

Trong `compute()`, đừng mở thêm một `ForkJoinPool` cho nhánh con rồi gọi `invoke` trên pool mới chỉ để “tăng parallelism”; bạn có thể tạo hàng trăm thread pools và vòng chờ giữa các pools. Trong cùng cây, dùng `fork`/`join`/`compute`. Nếu cần các workload tách biệt, kiến trúc service định nghĩa pools từ bên ngoài, không theo mỗi recursion node.

### 15.5. Một task fork quá nhiều children

Cấu trúc cây cân bằng thông thường có thể sinh **rất nhiều tasks** khi threshold quá thấp. Với data cực lớn, điều kiện dừng bắt buộc tránh stack overflow và task explosion. Nếu số nhánh rất nhiều hoặc irregular, xem xét work queues/`CountedCompleter` hoặc framework khác và benchmark.

## 16. Correctness: parallel program cần giữ các bất biến nào?

Một phép chia để trị thường phải chứng minh:

**Coverage:** mọi phần tử/đơn vị công việc được xử lý đúng số lần mà bài toán quy định. Với sum, mỗi index phải được tính **chính xác một lần**.

**Non-overlap:** các nhánh ghi dữ liệu mutable không chồng lấn trừ khi có synchronization hợp lệ.

**Termination:** mỗi lần chia làm bài toán nhỏ hơn cho đến ngưỡng; không tạo task mới vô hạn.

**Combine correctness:** kết quả của parent bằng phép kết hợp hợp lệ của các children, có xét identity và input empty.

**Visibility:** caller chỉ dùng kết quả hoặc data sau khi root `invoke/join/get` hoàn tất thành công.

**No cyclic waits:** parent chờ children, children không chờ ngược parent hoặc shared lock mà parent giữ.

**Error propagation:** leaf failure không bị âm thầm biến thành dữ liệu hợp lệ.

**Resource ownership:** owner của dedicated pool chịu trách nhiệm shutdown, không ảnh hưởng common pool và tác vụ của subsystem khác.

### 16.1. Chứng minh bằng interval induction

Đối với sum của dải `[lo,hi)`:

- **Base:** khi `hi-lo <= threshold`, tính tuần tự đúng các phần tử có index từ lo đến hi-1.
- **Inductive split:** mid nằm giữa lo/hi; hai intervals `[lo,mid)` và `[mid,hi)` không giao nhau, hợp lại đúng `[lo,hi)`.
- **Inductive result:** nếu mỗi nhánh trả đúng partial result, phép combine hợp lệ trả kết quả đúng dải cha.
- **Root:** `[0,n)` bao phủ toàn mảng.

Cách suy luận này vẫn đúng khi lịch các threads khác nhau, miễn rằng dữ liệu input không bị sửa không đồng bộ và phép combine đáp ứng các assumptions.

### 16.2. Đừng nhầm "thread-safe pool" với "thread-safe task"

`ForkJoinPool` quản lý threads/queues. Nó **không** tự biến các field reference tới mutable array/list/map trong `RecursiveTask` thành thread-safe. Việc dùng một `final int[] values` chỉ làm reference không đổi; nội dung mảng vẫn có thể bị thay từ threads khác.

Để an toàn, cần immutable input/snapshot hoặc partition ownership rõ, và đảm bảo external writers không sửa dữ liệu trong suốt job.

## 17. Kiểm thử có kiểm soát và benchmarking

### 17.1. Unit tests cho tính đúng

Trước khi đo tốc độ, kiểm tra:

1. Mảng rỗng: tổng trả 0 hay reject theo API? Max có nên throw?
2. Một phần tử; threshold bằng 1.
3. Dải có kích thước lẻ: mid chia thành 2 phần không bằng nhau.
4. Dữ liệu âm, dương, 0, trùng lặp và biên của kiểu số.
5. Kích thước ngay dưới/ngang/trên threshold.
6. Các giá trị có thể overflow.
7. Số workers 1, 2, 4 (nếu runtime cho phép) đều cho kết quả hợp lệ.
8. Chạy nhiều lần và so với baseline tuần tự.
9. Input không bị sửa bởi một thread khác nếu contract yêu cầu immutable.
10. Với mutation disjoint ranges, mỗi phần tử được cập nhật đúng một lần.
11. Exception trong leaf được báo tới caller.
12. Cancellation trước khi chạy và policy khi cancellation trong lúc đang chạy.
13. Dedicated pool shutdown đúng, không làm hỏng common pool.
14. Không có vòng chờ khi một task thất bại còn sibling đang chạy.

**Không assert** số steals, thứ tự task, thread names, hay thời gian dưới 1ms: đó không phải hợp đồng tính đúng. `AtomicInteger leaves` trong demo có số đúng do cấu trúc phân chia cố định, không phải do scheduling.

### 17.2. Khi nào dùng JMH?

Nếu muốn so threshold=128 với threshold=8192:

- Tạo data trước measurement, không trộn thời gian random generation.
- Warm up đầy đủ để JIT/GC phản ánh steady-state.
- Dùng input kích thước đại diện và lặp lại theo nhiều forks.
- So sequential baseline, parallel stream và custom fork/join.
- Theo dõi allocation, CPU utilization và memory bandwidth.
- Test trên máy có số cores/container CPU quota thực tế.
- Tránh benchmark chỉ 10 phần tử vì overhead khác hoàn toàn workload thật.
- Đảm bảo kết quả được tiêu thụ để compiler không loại bỏ phép tính.
- Không dùng `System.nanoTime` quanh một lần tính rồi tuyên bố phương án nào nhanh hơn.

**JMH** là công cụ benchmarking của OpenJDK, nhưng **không bắt buộc** cho các ví dụ tính đúng trong bài này. Chúng chỉ cần JDK 17+.

### 17.3. Theo dõi pool dưới tải

`ForkJoinPool` cung cấp một số metrics hữu ích:

| Metric | Diễn giải |
| --- | --- |
| `getParallelism()` | Mức parallelism mục tiêu |
| `getPoolSize()` | Ước lượng số worker threads |
| `getActiveThreadCount()` | Ước lượng workers đang steal/execute tasks |
| `getRunningThreadCount()` | Ước lượng workers không bị chặn trong công việc nội bộ |
| `getQueuedTaskCount()` | Ước lượng tổng local queued tasks |
| `getQueuedSubmissionCount()` | Ước lượng submissions chưa bắt đầu |
| `getStealCount()` | Ước lượng số lần steal hoàn tất |
| `isQuiescent()` | Pool đang không còn tasks để workers xử lý theo định nghĩa |
| `isShutdown()/isTerminated()` | Vòng đời executor riêng |

Tất cả các số đo có thể thay đổi giữa lúc bạn đọc. **Không dùng để quyết định tính đúng của kết quả**, và không đặt logic nghiệp vụ quan trọng dựa vào một threshold queue-length được ước lượng tức thời.

## 18. Bảo mật, quotas và input không tin cậy

Một dịch vụ nhận khối dữ liệu lớn từ client rồi chạy Fork/Join có các nguy cơ:

- Client yêu cầu xử lý một mảng quá dài dẫn đến CPU/memory exhaustion.
- Input xây dựng cây đệ quy quá sâu hoặc mất cân bằng.
- Threshold không hợp lệ gây chia vô hạn.
- Quá nhiều concurrent jobs chia task vô hạn vào cùng pool.
- Mutable shared input bị thay khi tính.
- Overflow tạo kết quả sai rồi được dùng cho tài chính/authorization.
- Task nhận input độc hại dẫn tới exception sau khi đã có side effects một phần.
- Cấu hình common pool bị những thư viện khác chiếm dụng lâu, gây ảnh hưởng nhiều requests.
- Log không giới hạn, thu metrics ở mọi leaf gây contention/tốn memory.
- Test/production dùng file I/O hoặc HTTP trong leaf khiến CPU pool bị blocking.

**Phòng vệ nhiều lớp:**

1. Validate array sizes, range bounds, threshold và recursion depth.
2. Giới hạn số jobs đang active và số bytes/objects in-flight.
3. Dùng immutable snapshot hoặc partition ownership.
4. Thêm request deadlines và cooperative cancellation.
5. Isolation giữa workloads khi cần SLA/tenant quotas.
6. Chọn numeric semantics rõ ràng, xử lý overflow/reproducibility.
7. Không chạy code không tin cậy trong cùng process/thread pool mà không có sandbox/authorization.
8. Đo resources và rejection policy, không xem pool là queue vô hạn của production.
9. Kết quả được publish **chỉ sau khi job thành công**; nếu side effects một phần có thể tồn tại thì phải có recovery/transaction.
10. Giảm dữ liệu nhạy cảm xuất hiện trong exceptions/logs.

## 19. Chọn Fork/Join hay một mô hình khác?

| Nhu cầu | Lựa chọn cân nhắc | Ghi chú |
| --- | --- | --- |
| Một phép reduce đơn giản trên mảng lớn | `Arrays.stream(...).parallel()` hoặc `ForkJoinPool` | So sánh hiệu năng và độ phức tạp |
| Cây tính toán tùy biến, các nhánh độc lập | `RecursiveTask` | Dễ điều khiển split/threshold/combine |
| Cập nhật các phân đoạn disjoint | `RecursiveAction` | Cần ownership rõ |
| Sắp xếp mảng cơ bản | `Arrays.sort` hoặc `Arrays.parallelSort` | Ưu tiên JDK API trước khi tự viết |
| CPU job một khối không chia nhỏ được | `ExecutorService` / thread tương ứng | Không tạo Fork/Join nếu không có subtasks |
| Nhiều I/O blocking tasks | Bounded executor, async API hoặc virtual threads phiên bản phù hợp | Fork/Join CPU pool không phải mặc định tốt |
| Multi-stage pipeline phụ thuộc dữ liệu | `CompletableFuture`/structured composition tùy version | Không cần ép thành cây Fork/Join |
| Sự kiện không join, mô hình phức tạp | `CountedCompleter` hoặc framework khác | Chỉ dùng khi có lợi thế rõ |
| Tính toán một ít phần tử | Vòng lặp tuần tự | Tránh overhead task allocation |

**Virtual threads (Java 21+) không thay thế Fork/Join cho CPU divide-and-conquer**. Virtual threads chủ yếu giúp diễn đạt nhiều tác vụ có thể blocking theo phong cách dễ đọc, còn CPU-bound parallelism vẫn giới hạn bởi CPU capacity. Cũng không thể dùng nhiều virtual threads để giải quyết một vòng chờ dữ liệu A↔B hoặc shared lock sai.

## 20. Các anti-pattern cần tránh

| Anti-pattern | Hậu quả | Cách sửa |
| --- | --- | --- |
| Fork task cho từng phần tử | Overhead rất lớn | Leaf xử lý chunk đủ lớn |
| Không có base case | Recursion vô hạn/task explosion | Threshold dương và range giảm |
| Fork trái rồi join ngay, sau đó compute phải | Giảm cơ hội parallelism | Fork trái, compute phải, join trái |
| Fork cả hai nhánh trong mọi node dù không cần | Tăng scheduling overhead | Một nhánh fork, một nhánh compute |
| `Math.max` leaf khởi tạo 0 | Sai với mảng toàn số âm | Correct identity và empty input policy |
| Dùng `int sum` khi tổng có thể overflow | Sai kết quả âm thầm | `long`/`Math.addExact`/`BigInteger` theo contract |
| Sum double rồi assert bitwise giống sequential | Floating-point order khác | Dùng reduction policy rõ |
| Hai tasks cùng sửa một array index | Data race | Disjoint partitions |
| Mọi leaf ghi shared ArrayList | Races/contended lock | Partial results rồi combine |
| Giữ lock khi đợi `join` | Có thể tạo deadlock với children | Thả lock trước join |
| Task con chờ chính task cha | Dependency cycle | Thiết kế DAG acyclic |
| Gọi blocking I/O trong leaf | Pool bị stall | Tách I/O hoặc dùng ManagedBlocker khi buộc |
| Gọi `new ForkJoinPool` trong mỗi recursion | Tốn threads/pools | Dùng pool đang thực thi |
| Shutdown `commonPool()` sau request | Can thiệp tài nguyên dùng chung, thường vô hiệu | Chỉ quản lý pool do mình sở hữu |
| Coi task cancellation sẽ interrupt tức thì | Không bảo đảm | Cooperative cancellation |
| Có exception rồi tin mọi siblings chưa chạy | Side effects có thể đã xảy ra | Purity/rollback policy |
| Dùng pool metrics làm kết quả tính đúng | Metrics là ước lượng | Validate output độc lập |
| Tự viết sort phức tạp chỉ để tăng tốc | Dễ bug/cost cao | Ưu tiên `Arrays.parallelSort` |
| Benchmark bằng một lần `nanoTime` | Không ổn định | Dùng JMH và baseline |
| Tăng số workers vô hạn | Contention/GC/OS overhead | Tuning theo CPU & workload |
| Dùng threshold từ một bài demo cho mọi dữ liệu | Không phản ánh work mỗi item | Benchmark nhiều thresholds |
| Coi `final array` là immutable data | Nội dung mảng vẫn mutable | Snapshot hoặc ownership |
| Cho user quyết định recursion depth không giới hạn | CPU/memory DoS | Quotas, bounds, cancellation |

## 21. Checklist code review

1. Bài toán có thật sự **chia thành các nhánh độc lập** không?
2. Các nhánh có đủ work để bù chi phí tạo và scheduling không?
3. Có baseline tuần tự đúng để so kết quả không?
4. `RecursiveTask` hay `RecursiveAction` phù hợp với việc cần result?
5. Điều kiện dừng luôn đạt tới chưa; threshold có được validate > 0 không?
6. Mỗi lần chia có làm interval nhỏ hơn và non-overlap không?
7. Có dùng `mid=lo+(hi-lo)/2` và range half-open nhất quán không?
8. Có tính từng phần tử đúng một lần (hoặc đúng số lần protocol yêu cầu) không?
9. Có fork một nhánh, compute nhánh kia rồi join theo đúng dependency không?
10. Có ngầm phụ thuộc task execution order/worker thread name không?
11. Phép combine associative/identity hợp lệ theo numeric/domain semantics không?
12. Có xử lý mảng rỗng và dữ liệu toàn số âm khi max/min không?
13. Có kiểm soát overflow/rounding và yêu cầu reproducibility không?
14. Có tránh shared mutable state hoặc đã chứng minh synchronization/ownership không?
15. Hai tasks có ghi vùng chung của array/scratch buffer không?
16. Parent có chỉ merge sau khi children hoàn tất không?
17. Có side effects nửa chừng nếu một task fail không? Policy rollback?
18. Có xét cancellation token và giới hạn công việc đang chạy không?
19. Có tránh blocking I/O/locks/dependencies không do pool quản lý trong `compute` không?
20. Nếu dùng `ManagedBlocker`, có thật sự cần và xử lý đúng lifecycle không?
21. Có tránh `join` theo dependency graph có chu trình không?
22. Có không mở pool mới trong từng subtask không?
23. Nếu dùng common pool, có hiểu nó chia sẻ workload với code khác không?
24. Nếu dùng dedicated pool, có owner, reuse và shutdown/await không?
25. Có không gọi API chỉ có Java 19+ (như `ForkJoinPool.close()`) trong code hứa chạy Java 17 không?
26. Có đọc metrics như ước lượng chứ không phải invariant không?
27. Có test với 1/2/4 workers và nhiều thresholds không?
28. Có test edge cases, integer overflow và runtime exceptions không?
29. Có đo performance với JMH/representative data và tránh microbenchmarks méo không?
30. Có giới hạn size/workload/recursion depth với dữ liệu không tin cậy không?
31. Có so API `Arrays.parallelSort`/parallel stream khi thư viện đã đủ không?
32. Có không mặc định CPU parallelism giải được networking/database latency không?

## 22. Bài tập thực hành

**Bài 1 — Vẽ cây phân tách.** Với 16 phần tử và threshold=4, vẽ các intervals mà `ForkJoinSumDemo` tạo ra. Vì sao có đúng bốn leaf? Tại sao trình tự chạy các leaf có thể thay đổi nhưng tổng vẫn 136?

**Bài 2 — Tổng không chia hết đôi.** Đổi dữ liệu thành 17 phần tử; kiểm tra interval `[0,17)`, tính coverage một lần và so với vòng for. Dùng `Math.addExact` để phát hiện tràn.

**Bài 3 — Empty input.** Chạy `ForkJoinMaxDemo` rồi đề xuất một overload trả `OptionalInt`. Vì sao max của mảng rỗng không nên tự trả 0?

**Bài 4 — RecursiveAction.** Chạy `ForkJoinTransformDemo` với threshold=1/2/8. Kiểm tra mỗi phần tử được nhân đúng hai lần? Thực tế mỗi phần tử **chỉ được nhân một lần với hệ số 2**, không nhân lặp trong các ancestors. Trình bày chứng minh partition ownership.

**Bài 5 — Merge sort.** Chạy `ForkJoinMergeSortDemo` với dữ liệu trùng lặp và giá trị âm. Dùng baseline `Arrays.sort` để đối chiếu; phân tích vì sao parent merge chỉ chạy sau join.

**Bài 6 — Scratch buffer.** Cố tình thiết kế hai nhánh ghi cùng `scratch[0]` trong một chương trình sandbox để quan sát rủi ro, sau đó sửa bằng disjoint ranges. Không đưa thiết kế lỗi vào sản phẩm.

**Bài 7 — Threshold.** Chạy `ForkJoinThresholdDemo`, đổi threshold thành 1/4/16; dự đoán số leaf và so sánh kết quả. Không suy số leaf lớn là throughput cao.

**Bài 8 — Overflow.** Chạy `ForkJoinFailureDemo`, thay `Math.addExact` bằng `+` và quan sát sai lệch nếu overflow. Viết một version dùng `BigInteger` có semantics chính xác.

**Bài 9 — Floating point.** Tạo một mảng `double` có số rất lớn, nhỏ và âm; so kết quả sequential/parallel với một tolerance policy. Nêu trường hợp bắt buộc reproducibility theo thứ tự cố định.

**Bài 10 — Cancellation.** Chạy `ForkJoinCancellationDemo`; giải thích vì sao `cancel(true)` không phải bảo đảm interrupt running task. Thiết kế cooperative token cho computation dài.

**Bài 11 — Stream vs Fork/Join.** Chạy `ForkJoinVsStreamDemo`. Đối chiếu correctness, không dùng test nhỏ này để khẳng định performance. Đề xuất tiêu chí chọn một trong hai.

**Bài 12 — ManagedBlocker.** Chạy `ForkJoinManagedBlockDemo`. Mô tả vai trò `isReleasable`/`block`. Vì sao ví dụ không thể kết luận pool đã tạo spare worker?

**Bài 13 — Pool lifecycle.** Tạo một class service sở hữu dedicated `ForkJoinPool`, submit nhiều root tasks, ngừng nhận jobs mới, shutdown và awaitTermination ở cuối service. Không tạo pool per request.

**Bài 14 — Benchmark.** Dùng JMH để so sequential sum, parallel stream và Fork/Join sum trên 10³/10⁵/10⁷ phần tử với các thresholds. Theo dõi CPU, allocations và memory bandwidth.

**Bài 15 — Data race.** Dùng shared `ArrayList.add` trong multiple leaves (sandbox), rồi sửa bằng partial lists và merge theo interval order. Kiểm tra đúng số lượng phần tử.

**Bài 16 — Task tree imbalance.** Thiết kế một cây mà một nhánh tốn gấp 100 lần nhánh khác. Điều chỉnh partition strategy và quan sát work-stealing metrics dưới tải.

**Bài 17 — Max/min trên cây.** Cho một cây binary với trọng số tại nodes, viết `RecursiveTask<Integer>` tìm max với điều kiện dừng phù hợp, xử lý cây rỗng rõ.

**Bài 18 — Quotas.** API nhận dữ liệu mảng từ client: giới hạn số phần tử, concurrency, timeout và allocated bytes. Giải thích ranh giới giữa throttling requests và số ForkJoin leaf tasks nội bộ.

**Bài 19 — Reduction correctness.** Hãy xác định phép combine có associative không với: cộng số nguyên giới hạn, max, trừ, nối chuỗi theo thứ tự, và phép cộng double. Chọn policy để output không mơ hồ.

**Bài 20 — Production review.** Thiết kế xử lý batch CPU-heavy với immutable input, bounded job scheduling, diagnostics, failure propagation và dedicated pool. Viết checklist trước khi tăng parallelism.

## 23. Kết luận

- Fork/Join triển khai **divide and conquer** cho công việc CPU-bound có thể phân chia thành các subtasks độc lập, rồi **fork / compute / join / combine**.
- `RecursiveTask<V>` dùng khi cần kết quả; `RecursiveAction` dùng khi chỉ cần hành động và thời điểm hoàn tất.
- `ForkJoinPool` sử dụng **work stealing** giúp workers rảnh nhận công việc, nhưng scheduling **không được dùng làm cơ sở tính đúng đắn**.
- Mẫu **fork một nhánh, compute nhánh kia, join nhánh đã fork** thường giảm overhead so với tạo quá nhiều tasks rồi chờ.
- **Threshold là quyết định hiệu năng quan trọng**: quá nhỏ tăng overhead, quá lớn thiếu parallelism; cần benchmark trên workload thực.
- **Coverage, non-overlap, associative combine và termination** là điều kiện để kết quả đúng; phải xét input rỗng, tràn số và floating point.
- `ForkJoinTask.join` truyền unchecked failure; cancellation **không tự ngắt mọi task hay rollback side effects**.
- **Tránh blocking I/O và vòng chờ lẫn nhau** trong CPU pool; `ManagedBlocker` là công cụ cho trường hợp blocking buộc phải có, không phải cách thay thế kiến trúc phù hợp.
- **Pool dùng chung khác pool riêng**: commonPool không nên bị shutdown bởi module; dedicated pool cần owner, reuse và shutdown đúng.
- **Không phải mọi việc cần Fork/Join**: loop tuần tự, parallel streams hoặc `Arrays.parallelSort` có thể tốt hơn tùy bài toán.
- Hướng dẫn dựa trên **API vẫn được hỗ trợ ở Java 17+**, không đòi công cụ/hành vi legacy.

## Tài liệu chính thức

- [ForkJoinPool — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ForkJoinPool.html): work stealing, commonPool, invoke/submit, parallelism, ManagedBlocker và pool metrics.
- [ForkJoinTask — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ForkJoinTask.html): fork/join, invokeAll, cancellation, lỗi và dependency tasks.
- [RecursiveTask — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/RecursiveTask.html): divide-and-conquer task có kết quả.
- [RecursiveAction — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/RecursiveAction.html): action không có kết quả trả về và ví dụ sort.
- [CountedCompleter — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CountedCompleter.html): completion-based fork/join tasks nâng cao.
- [Arrays — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Arrays.html): `sort` và `parallelSort`.
- [Stream — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/Stream.html): parallel stream và reduction.
- [Math — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Math.html): `addExact`, `multiplyExact`, overflow policies.
- [Future — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Future.html): get, timeout và cancellation.

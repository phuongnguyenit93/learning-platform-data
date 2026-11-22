# Thực thi nhiều tác vụ bằng invokeAll trong Fork/Join của Java

**Chủ đề:** Java 7 — Fork/Join  
**Bài học:** Thực thi nhiều tác vụ bằng `invokeAll`  
**Phiên bản thực hành:** Java 17+; `java.util.concurrent.ForkJoinTask`, `RecursiveTask`, `RecursiveAction`, `ForkJoinPool` và `ExecutorService` vẫn là các API Java được hỗ trợ hiện nay. Bài chỉ sử dụng kiến thức còn áp dụng, không dùng API bị thay thế/legacy.

## 1. Vấn đề mà invokeAll giải quyết

Hãy hình dung bạn cần tính tổng một mảng rất lớn. Một tác vụ có thể tự tính toàn bộ mảng; nhưng nếu có nhiều CPU cores và hai nửa mảng không phụ thuộc lẫn nhau, bạn có thể:

1. Chia mảng thành hai dải `[lo, mid)` và `[mid, hi)`.
2. Tạo hai `RecursiveTask<Long>` riêng.
3. **Khởi chạy cả hai nhiệm vụ và đợi chúng kết thúc** bằng `ForkJoinTask.invokeAll(left, right)`.
4. Đọc hai kết quả bằng `left.join()`, `right.join()`.
5. Gộp hai partial sums theo đúng hợp đồng tính toán.

```text
                      Root SumTask
                      [0, 16)
                      /     \
                    /         \
          Left [0, 8)        Right [8, 16)
             /   \               /    \
        [0,4)   [4,8)       [8,12)   [12,16)
          |        |            |          |
        leaf      leaf         leaf       leaf
          \        /            \          /
          invokeAll              invokeAll
             \                      /
               combine results
                      |
                    136
```

`ForkJoinTask.invokeAll` là **tiện ích fork/join một nhóm task**, phù hợp khi các nhánh có thể được thực hiện độc lập và bước tiếp theo **cần kết quả của tất cả**.

**Điểm mấu chốt:** `invokeAll` **không có nghĩa mỗi task sở hữu một thread**, **không đảm bảo thứ tự chạy**, và **không tự kết hợp giá trị trả về**. Nó quản lý việc thực hiện và chờ hoàn thành; bạn vẫn phải viết logic `compute` và `combine`.

Trong một `RecursiveTask` thường có hai lựa chọn hợp lệ:

```java
// Cách 1: viết thủ công khi chỉ có hai nhánh.
left.fork();
Result rightValue = right.compute();
Result leftValue = left.join();
return combine(leftValue, rightValue);

// Cách 2: tiện ích invokeAll.
ForkJoinTask.invokeAll(left, right);
return combine(left.join(), right.join());
```

Đây là **snippet minh họa**, `Result`, `left`, `right` và `combine` do ứng dụng định nghĩa. Hai phong cách có thể cho cùng logic tính toán, nhưng khác cách biểu đạt và chi tiết scheduling. Không ép luôn dùng cách 2 cho mọi nhánh, và không tự khẳng định cách nào nhanh hơn khi chưa benchmark.

### 1.1. Khi nào nên dùng?

- Có **hai hoặc nhiều** nhánh công việc độc lập.
- Các nhánh có **điều kiện dừng** rõ ràng; lượng công việc đủ lớn để parallelism có ích.
- Sau khi mọi nhánh hoàn tất, parent sẽ **đọc kết quả hoặc merge dữ liệu**.
- Dữ liệu đầu vào không bị thay đổi bất ngờ, hoặc từng nhánh **sở hữu dải ghi riêng**.
- Quan hệ phụ thuộc là một DAG không chu trình, không có child chờ ngược parent.
- Task chủ yếu CPU-bound; không làm I/O/blocking lâu trong pool chỉ vì API có chữ “parallel”.

Ví dụ phù hợp: tổng, đếm, min/max, merge sort, phân tích nhiều phân đoạn độc lập, xử lý những ô ảnh không chồng lấp hoặc từng nhánh phân tích một cây con.

Không nhất thiết dùng khi có chỉ vài giá trị, hoặc khi phần lớn thời gian nằm ở network/database latency; việc tách thành hàng nghìn task rất nhỏ thường chỉ thêm overhead.

## 2. Cần phân biệt **hai họ invokeAll** trong Java

Đây là chỗ người học thường nhầm nhất.

| API | Nhận vào | Trả về | Ý nghĩa |
| --- | --- | --- | --- |
| `ForkJoinTask.invokeAll(t1, t2)` — static | Hai `ForkJoinTask<?>` | `void` | Fork các task, chờ khi hoàn tất hoặc gặp exception |
| `ForkJoinTask.invokeAll(tasks...)` — static | Varargs `ForkJoinTask<?>...` | `void` | Tiện ích thực thi nhiều ForkJoinTasks |
| `ForkJoinTask.invokeAll(Collection<T>)` — static | Collection các `ForkJoinTask` | **Chính collection đã truyền vào** | Thực thi nhóm tasks và trả cùng collection để tiện sử dụng |
| `ForkJoinPool.invokeAll(Collection<Callable<T>>)` — instance | Collection các `Callable<T>` | `List<Future<T>>` | API `ExecutorService` để thực thi/đợi một batch Callables |

**Không được viết** `List<Future<Integer>> fs = ForkJoinTask.invokeAll(tasks)`. Với overload collection của `ForkJoinTask`, kiểu trả về là `Collection<T>` của các **task gốc**, không phải một list Futures mới; hai overload còn lại **trả void**.

`ForkJoinPool` là một `ExecutorService`, nên nó **có** `invokeAll(Collection<Callable<T>>)` như những executor khác. Đó là **một phương thức khác, với hợp đồng về lỗi, interruption và Future khác**. Bài có ví dụ so sánh riêng.

### 2.1. Chữ invoke có nhiều vị trí

Phân biệt bốn trường hợp thường gặp:

- `pool.invoke(rootTask)`: chạy **một root `ForkJoinTask`**, đợi và nhận kết quả.
- `rootTask.invoke()`: bản thân một `ForkJoinTask` bắt đầu chạy và đợi hoàn tất.
- `ForkJoinTask.invokeAll(left, right)`: tiện ích thực thi **nhiều ForkJoinTasks** và đợi hoàn tất/lỗi.
- `pool.invokeAll(callables)`: API của `ExecutorService`, nhận **Callable collection**, trả `List<Future<T>>`.

Đừng đoán ý nghĩa chỉ từ chữ “invoke”; hãy xem **class đứng trước dấu chấm**, **kiểu tham số** và **kiểu trả về**.

### 2.2. Vì sao nên gọi static invokeAll bên trong compute?

Pattern tự nhiên là root task được `ForkJoinPool` thực thi, rồi `compute()` tạo subtasks và gọi `ForkJoinTask.invokeAll`. Khi đó tasks được fork/join như một phần của cây công việc và có thể tận dụng worker scheduling/work stealing của pool.

Không tạo một `new ForkJoinPool` trong mỗi leaf hoặc mỗi lần `invokeAll`. Chủ sở hữu pool nên quản lý lifecycle ở cấp service/main và chỉ fork/compute/join trong cây.

## 3. Overload hai task: invokeAll(left, right)

Chữ ký rút gọn:

```java
public static void invokeAll(ForkJoinTask<?> t1, ForkJoinTask<?> t2);
```

Đây là **chữ ký API**, không phải chương trình runnable. Nó nhận hai task và **không trả kết quả dạng object**. Sau khi lời gọi hoàn tất **bình thường**, cả hai tasks đều đã có trạng thái `isDone()==true`, và bạn có thể gọi `join()` để lấy kết quả typed.

Nếu một nhánh thất bại bằng unchecked exception, `invokeAll` có thể **ném lại exception**; khi đó **không** được suy mọi siblings đều hoàn tất bình thường. Các task khác **có thể** bị cancel, đang chạy, hoàn tất hoặc chưa xử lý; cần kiểm tra trạng thái cụ thể nếu recovery cần biết.

### 3.1. Ví dụ runnable: tổng từ 1 đến 16

Tạo file `InvokeAllPairSumDemo.java`:

```java
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;
public class InvokeAllPairSumDemo {
  static final class SumTask extends RecursiveTask<Long> {
    private static final long serialVersionUID=1L;
    private final long[] values;
    private final int lo,hi,threshold;
    private final AtomicInteger leaves;
    SumTask(long[] values,int lo,int hi,int threshold,AtomicInteger leaves){
      this.values=values;this.lo=lo;this.hi=hi;this.threshold=threshold;this.leaves=leaves;
    }
    @Override protected Long compute(){
      if(hi-lo<=threshold){
        leaves.incrementAndGet();
        long sum=0;for(int i=lo;i<hi;i++)sum=Math.addExact(sum,values[i]);
        return sum;
      }
      int mid=lo+(hi-lo)/2;
      SumTask left=new SumTask(values,lo,mid,threshold,leaves);
      SumTask right=new SumTask(values,mid,hi,threshold,leaves);
      ForkJoinTask.invokeAll(left,right);
      return Math.addExact(left.join(),right.join());
    }
  }
  public static void main(String[] args)throws Exception{
    long[] values=new long[16];
    for(int i=0;i<values.length;i++)values[i]=i+1L;
    AtomicInteger leaves=new AtomicInteger();
    ForkJoinPool pool=new ForkJoinPool(4);
    try{
      long sum=pool.invoke(new SumTask(values,0,values.length,4,leaves));
      System.out.println("sum="+sum);
      System.out.println("leaves="+leaves.get());
      System.out.println("parallelism="+pool.getParallelism());
    }finally{pool.shutdown();pool.awaitTermination(5,TimeUnit.SECONDS);}
  }
}
```

Biên dịch và chạy với JDK 17+:

```bash
javac -encoding UTF-8 -Xlint:all InvokeAllPairSumDemo.java
java InvokeAllPairSumDemo
```

**stdout đã kiểm thử:**

```text
sum=136
leaves=4
parallelism=4
```

Giải thích:

1. Mỗi task sở hữu dải **[lo, hi)**, nghĩa là bao gồm `lo` và không bao gồm `hi`.
2. Nếu dải còn không quá 4 phần tử, leaf tự tính tổng; biến `leaves` dùng `AtomicInteger` để đếm chính xác qua nhiều worker threads.
3. Nếu dải lớn hơn, task chia tại `mid=lo+(hi-lo)/2`, tạo `left` và `right`.
4. `ForkJoinTask.invokeAll(left,right)` điều phối **hai** subtask; parent đợi chúng hoàn tất bình thường trước khi đọc partial sums.
5. `left.join()`/`right.join()` cung cấp kết quả `long` theo `RecursiveTask<Long>`, không chạy lại các computations đã thành công.
6. `Math.addExact` phát hiện tràn số theo chính sách demo, thay vì để số học `long` wrap âm thầm.
7. `pool.invoke(root)` là ranh giới main thread chờ toàn cây; dedicated pool được shutdown trong `finally`.

**Vì sao đúng 4 leaves?** Từ 16 phần tử: 16 → hai dải 8 → bốn dải 4. Tổng `1+2+...+16=136`. Lịch worker khác nhau không ảnh hưởng số leaves hoặc tổng vì partition cố định.

**Cần tránh diễn giải sai:** `parallelism=4` chỉ là mục tiêu parallelism của pool riêng, không chứng minh 4 threads đã thực sự chạy đồng thời. `invokeAll` không cam kết thứ tự leaf hoặc thứ tự hoàn tất.

### 3.2. Có cần join sau invokeAll?

Có **nếu muốn lấy typed result**. Với `RecursiveTask<Long>`, `join()` trả `Long`. `invokeAll` hai task trả `void`, không tạo biến kết quả cho bạn.

Khi `invokeAll` đã **trả về bình thường**, các lần `join` thành công thông thường chỉ lấy kết quả đã có; không phải “fork lần hai”. Nếu overload đã **ném exception**, code sau lời gọi không được chạy như thể các results đều có sẵn.

Nếu mục tiêu chỉ là chờ hai `RecursiveAction` cập nhật hai dải dữ liệu, có thể không cần gọi `join` riêng sau `invokeAll` thành công.

### 3.3. So với fork-one/compute-one/join-one

Mẫu thủ công:

```java
left.fork();
long rightSum = right.compute();
long leftSum = left.join();
return Math.addExact(leftSum, rightSum);
```

Đây là snippet, cần class và biến thích hợp. Nó biểu lộ rõ ý định **fork một nhánh, tận dụng thread hiện tại tính nhánh kia, rồi join**. `ForkJoinTask.invokeAll(left,right)` gọn hơn khi bạn muốn **cùng một bước điều phối và chờ nhiều tasks**.

Không mặc định overload `invokeAll` luôn nhanh hơn mẫu thủ công. Cần đo với kích thước dữ liệu, threshold, số cores và implementation thực tế.

## 4. Varargs: invokeAll(task1, task2, task3, ...)

Có thể có ba hoặc nhiều nhánh:

```java
ForkJoinTask.invokeAll(taskA, taskB, taskC);
```

Đây là snippet. Overload varargs nhận `ForkJoinTask<?>...`, trả `void`, và chờ tới khi tất cả tasks hoàn tất hoặc exception theo API. Nhóm tasks **không bắt buộc có cùng generic result type**, vì varargs dùng wildcard; nhưng nếu muốn cộng kết quả, thường nên dùng tasks có type tương thích và semantics gộp rõ.

### 4.1. Ví dụ runnable: ba phép bình phương

Tạo `InvokeAllVarargsDemo.java`:

```java
import java.util.concurrent.*;
public class InvokeAllVarargsDemo {
  static final class SquareTask extends RecursiveTask<Integer> {
    private static final long serialVersionUID=1L;
    final int x;
    SquareTask(int x){this.x=x;}
    @Override protected Integer compute(){return Math.multiplyExact(x,x);}
  }
  static final class Root extends RecursiveTask<Integer> {
    private static final long serialVersionUID=1L;
    @Override protected Integer compute(){
      SquareTask a=new SquareTask(2),b=new SquareTask(3),c=new SquareTask(4);
      ForkJoinTask.invokeAll(a,b,c);
      System.out.println("all-done="+(a.isDone()&&b.isDone()&&c.isDone()));
      System.out.println("squares="+a.join()+","+b.join()+","+c.join());
      return a.join()+b.join()+c.join();
    }
  }
  public static void main(String[] args)throws Exception{
    ForkJoinPool pool=new ForkJoinPool(2);
    try{System.out.println("total="+pool.invoke(new Root()));}
    finally{pool.shutdown();pool.awaitTermination(5,TimeUnit.SECONDS);}
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all InvokeAllVarargsDemo.java
java InvokeAllVarargsDemo
```

**stdout đã kiểm thử:**

```text
all-done=true
squares=4,9,16
total=29
```

Phân tích:

- Ba `SquareTask` trả 4, 9, 16.
- Lời gọi varargs **không trả list**; các đối tượng `a`, `b`, `c` vẫn giữ results.
- Khi `invokeAll` trả thành công, `isDone` true cho cả ba.
- `join` lấy từng giá trị, tổng được tính `4+9+16=29`.
- Thứ tự xuất hiện của `squares` trong stdout là **thứ tự code nối chuỗi `a,b,c`**, không phải thứ tự tasks chạy.

**Chú ý với in log:** nếu từng child tự in tên thread hoặc thứ tự bắt đầu, stdout sẽ thay đổi giữa các runs. Trong ví dụ, output in từ root **sau khi invokeAll thành công**, vì thế kết quả là deterministic.

### 4.2. Hạn chế của cách viết varargs rất lớn

Nếu có 10.000 branches, đừng nhồi 10.000 tham số vào một lệnh hoặc tạo một task cho mỗi phần tử. Nên dùng **Collection overload**, hoặc thiết kế partition tree có leaf work đủ lớn. Varargs tiện khi số task nhỏ, rõ ngay tại nơi gọi.

Với một task duy nhất, `task.invoke()` hoặc `task.compute()` trong đúng ngữ cảnh có thể dễ hiểu hơn một lời gọi `invokeAll` chỉ để thể hiện một nhánh.

## 5. Collection: invokeAll(Collection<T>) khi số nhánh thay đổi

Chữ ký khái niệm:

```java
public static <T extends ForkJoinTask<?>>
Collection<T> invokeAll(Collection<T> tasks);
```

Đây là chữ ký API, không phải chương trình độc lập. Overload nhận **Collection các ForkJoinTasks**, và **trả lại chính collection đó** để tiện code chaining. Nó không thay thế mỗi task bằng một `Future` mới.

### 5.1. Ví dụ runnable: một collection bốn task

Tạo `InvokeAllCollectionDemo.java`:

```java
import java.util.*;
import java.util.concurrent.*;
public class InvokeAllCollectionDemo {
  static final class DoubleTask extends RecursiveTask<Integer>{
    private static final long serialVersionUID=1L;
    final int value;
    DoubleTask(int value){this.value=value;}
    @Override protected Integer compute(){return value*2;}
  }
  static final class Root extends RecursiveTask<Integer>{
    private static final long serialVersionUID=1L;
    @Override protected Integer compute(){
      List<DoubleTask> tasks=new ArrayList<>();
      for(int value=1;value<=4;value++)tasks.add(new DoubleTask(value));
      Collection<DoubleTask> returned=ForkJoinTask.invokeAll(tasks);
      int sum=0;for(DoubleTask t:tasks)sum+=t.join();
      System.out.println("same-collection="+(returned==tasks));
      System.out.println("all-done="+tasks.stream().allMatch(ForkJoinTask::isDone));
      System.out.println("task-count="+tasks.size());
      return sum;
    }
  }
  public static void main(String[] args)throws Exception{
    ForkJoinPool pool=new ForkJoinPool(3);
    try{System.out.println("sum="+pool.invoke(new Root()));}
    finally{pool.shutdown();pool.awaitTermination(5,TimeUnit.SECONDS);}
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all InvokeAllCollectionDemo.java
java InvokeAllCollectionDemo
```

**stdout đã kiểm thử:**

```text
same-collection=true
all-done=true
task-count=4
sum=20
```

Bốn task nhân đôi các giá trị 1, 2, 3, 4 → 2, 4, 6, 8 → tổng 20. Biểu thức `returned == tasks` chứng minh **cùng một collection object** được trả về, đúng contract của overload này.

**Không được thêm/xóa phần tử collection trong lúc `invokeAll` đang thực thi** rồi phụ thuộc vào kết quả. Tạo collection hoàn chỉnh trước khi fork, đảm bảo các task references không `null` và không chia sẻ task đang chạy trong cây khác.

### 5.2. Collection chứa các task khác kiểu kết quả

Do generic bound `T extends ForkJoinTask<?>`, bạn có thể dùng collection các ForkJoinTasks khác nhau. Tuy nhiên, khi trộn `RecursiveTask<Integer>` và `RecursiveTask<String>` trong một collection của `ForkJoinTask<?>`, việc gộp kết quả sẽ kém tiện/khó type-safe.

**Khuyến nghị:** nếu tất cả subtasks cùng loại công việc, dùng `List<RangeSumTask>` hoặc `List<ParseChunkTask>`, không trộn tùy tiện rồi cast results. Nếu khác loại, cân nhắc adapter record/typed result hoặc tách các loại nhiệm vụ.

## 6. RecursiveAction: invokeAll chỉ để hoàn tất nhiều nhánh

`RecursiveAction` là `ForkJoinTask<Void>` thực hiện tác động (ví dụ biến đổi một vùng mảng), không trả kết quả để parent cộng. Khi các regions không chồng lấp, `invokeAll` rất rõ nghĩa:

```java
ForkJoinTask.invokeAll(
    new ChangeSegment(data, 0, 2),
    new ChangeSegment(data, 2, 4)
);
// Sau khi trở về bình thường: cả hai vùng đã được cập nhật xong.
```

Đây là snippet, `ChangeSegment` do ứng dụng định nghĩa.

### 6.1. Ví dụ runnable: bốn phân đoạn không chồng lấp

Tạo `InvokeAllActionDemo.java`:

```java
import java.util.*;
import java.util.concurrent.*;
public class InvokeAllActionDemo {
  static final class ChangeSegment extends RecursiveAction{
    private static final long serialVersionUID=1L;
    final int[] data;final int lo,hi;
    ChangeSegment(int[] data,int lo,int hi){this.data=data;this.lo=lo;this.hi=hi;}
    @Override protected void compute(){
      for(int i=lo;i<hi;i++)data[i]=Math.multiplyExact(data[i],3);
    }
  }
  static final class Root extends RecursiveAction{
    private static final long serialVersionUID=1L;
    final int[] data;Root(int[] data){this.data=data;}
    @Override protected void compute(){
      List<ChangeSegment> chunks=List.of(
        new ChangeSegment(data,0,2),new ChangeSegment(data,2,4),
        new ChangeSegment(data,4,6),new ChangeSegment(data,6,8));
      ForkJoinTask.invokeAll(chunks);
      System.out.println("done="+chunks.stream().allMatch(ForkJoinTask::isDone));
    }
  }
  public static void main(String[] args)throws Exception{
    int[] data={1,2,3,4,5,6,7,8};
    ForkJoinPool pool=new ForkJoinPool(4);
    try{
      pool.invoke(new Root(data));
      System.out.println("values="+Arrays.toString(data));
    }finally{pool.shutdown();pool.awaitTermination(5,TimeUnit.SECONDS);}
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all InvokeAllActionDemo.java
java InvokeAllActionDemo
```

**stdout đã kiểm thử:**

```text
done=true
values=[3, 6, 9, 12, 15, 18, 21, 24]
```

Mỗi `ChangeSegment` xử lý một dải riêng của mảng, và không có hai task cùng viết một index. Parent dùng `ForkJoinTask.invokeAll(chunks)` để đợi cả bốn task **hoàn tất bình thường**; sau đó main đọc kết quả mảng.

### 6.2. Điều kiện an toàn khi các nhánh sửa dữ liệu

**Không được suy “ForkJoinTask là thread-safe” ⇒ tất cả dữ liệu mà task chạm vào cũng thread-safe.** Pool quản lý queue/scheduling; còn array, `ArrayList`, `HashMap` và object mutable vẫn cần cơ chế sở hữu/synchronization.

Với mảng trong ví dụ:

- `[0,2)`, `[2,4)`, `[4,6)` và `[6,8)` là **disjoint**.
- Mỗi phần tử được nhân **một lần** bởi task sở hữu.
- `pool.invoke(root)` trả về sau khi các nhánh cần thiết hoàn tất.
- Không có consumer đọc mảng trong khi những nhánh vẫn đang ghi.
- `Math.multiplyExact` có thể ném lỗi; nếu fail giữa chừng, **một phần mảng có thể đã bị sửa** — Fork/Join không rollback.

Nếu cần “all-or-nothing”, tính trên output array riêng rồi **publish kết quả sau thành công**, hoặc dùng giao thức transaction thích hợp. Chỉ dựa vào `invokeAll` để có atomic transaction là sai.

## 7. Nếu một task thất bại: invokeAll sẽ như thế nào?

Theo JavaDoc của `ForkJoinTask.invokeAll`, các overload:

- Fork các tasks được truyền vào.
- Trả về khi `isDone` đúng với từng task **hoặc một unchecked exception được phát hiện**; exception đó được ném lại.
- Nếu nhiều tasks ném exception, có thể ném **bất kỳ một exception trong số đó**.
- Khi một task fail, những tasks khác **có thể bị cancel**.
- Sau khi lời gọi **trả về bằng exception**, trạng thái từng task **không được bảo đảm**: có thể hoàn tất bình thường, thất bại, bị cancel hoặc chưa xử lý.

**Đặc biệt:** không viết code như sau rồi nghĩ đã có transaction:

```java
ForkJoinTask.invokeAll(updateA, updateB, updateC);
// Không có nghĩa "hoặc tất cả cùng commit hoặc không cập nhật gì".
```

Đây là snippet minh họa; thao tác có side effects có thể đã sửa một phần dữ liệu dù một task khác fail.

### 7.1. Ví dụ runnable: exception truyền về root caller

Tạo `InvokeAllFailureDemo.java`:

```java
import java.util.concurrent.*;
public class InvokeAllFailureDemo {
  static final class Work extends RecursiveTask<Integer>{
    private static final long serialVersionUID=1L;
    final int value;
    Work(int value){this.value=value;}
    @Override protected Integer compute(){
      if(value<0)throw new IllegalArgumentException("Negative work");
      return value*2;
    }
  }
  static final class Root extends RecursiveTask<Integer>{
    private static final long serialVersionUID=1L;
    @Override protected Integer compute(){
      Work good=new Work(2),bad=new Work(-1),other=new Work(3);
      ForkJoinTask.invokeAll(good,bad,other);
      return good.join()+bad.join()+other.join();
    }
  }
  public static void main(String[] args)throws Exception{
    ForkJoinPool pool=new ForkJoinPool(2);
    try{
      boolean failed=false;
      try{pool.invoke(new Root());}
      catch(RuntimeException ex){failed=true;}
      System.out.println("failure-propagated="+failed);
      System.out.println("pool-still-running="+!pool.isShutdown());
    }finally{pool.shutdown();pool.awaitTermination(5,TimeUnit.SECONDS);}
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all InvokeAllFailureDemo.java
java InvokeAllFailureDemo
```

**stdout đã kiểm thử:**

```text
failure-propagated=true
pool-still-running=true
```

`bad` chủ động ném `IllegalArgumentException` nên lời gọi từ root thất bại. Main catch `RuntimeException` và xử lý. Pool **không tự shutdown** chỉ vì một task fail; `finally` của owner vẫn phải shutdown pool riêng.

**Không kiểm tra status của siblings trong stdout.** Theo JavaDoc, khi một task fail, `invokeAll` không cam kết số phận mỗi task còn lại. Một test portable **không nên** assert `good.isCompletedNormally()==true` hoặc `other.isCancelled()==true` mà không điều phối bổ sung.

**Trong production:** ghi nhận lỗi với correlation ID, mark job failed, không publish aggregate output sai, và dùng status/recovery policy nếu có side effects. Với tính toán thuần không ghi shared state, việc bỏ partial results thường dễ dàng hơn rollback hoạt động bên ngoài.

### 7.2. Cách xem trạng thái từng task nếu phải dọn dẹp

`ForkJoinTask` cung cấp:

- `isDone()`: task đạt trạng thái terminal (thành công/bất thường).
- `isCompletedNormally()`: task hoàn thành bình thường.
- `isCompletedAbnormally()`: kết thúc bất thường, gồm exception hoặc cancel.
- `isCancelled()`: task bị cancel.
- `getException()`: chi tiết exception nếu có theo trạng thái.

Những calls này **không thay thế synchronization/recovery** cho side effects và không chứng minh dữ liệu bên ngoài đã được rollback. Cần định nghĩa state transition của job từ đầu.

### 7.3. InterruptedException và cancellation có gì khác?

`ForkJoinTask.join()` thường ném unchecked failure và **không trả về bằng `InterruptedException`** chỉ vì thread đợi bị interrupt. `ForkJoinTask.get()`, theo hợp đồng `Future`, có thể ném `InterruptedException`/`ExecutionException`.

Mặt khác, `ExecutorService.invokeAll(Collection<Callable<T>>)` là API **khác**, được khai báo `throws InterruptedException` và có quy tắc cancel tasks chưa hoàn tất khi thread đợi bị interrupt. Không mang quy tắc đó áp vào static `ForkJoinTask.invokeAll`.

Đồng thời, `ForkJoinTask.cancel(true)` **không bảo đảm interrupt một running worker** như nhiều người tưởng; cancellation thường cần code CPU kiểm tra một token riêng nếu muốn dừng có kiểm soát.

## 8. Rất quan trọng: ForkJoinPool.invokeAll không phải ForkJoinTask.invokeAll

Khi bạn có tập các `Callable<T>` thay vì tự tạo `RecursiveTask<T>`, `ForkJoinPool` (qua `ExecutorService`) có phương thức instance:

```java
<T> List<Future<T>> invokeAll(Collection<? extends Callable<T>> tasks)
        throws InterruptedException;
```

Đây là chữ ký API rút gọn. Phương thức thực thi các Callables và **trả list Futures theo thứ tự iterator của collection đầu vào** khi các tasks đã hoàn tất; từng `Future.get()` sẽ trả kết quả hoặc `ExecutionException` nếu task đó thất bại.

**Khác biệt xử lý lỗi:** một Callable fail không làm `ExecutorService.invokeAll` (bản không timeout) tự ném ngay exception nghiệp vụ đó; nó **đợi tất cả tasks hoàn thành**, và bạn phải kiểm tra `Future.get()` của từng task để biết lỗi.

### 8.1. Ví dụ runnable: batch Callable qua ForkJoinPool

Tạo `ExecutorInvokeAllContrastDemo.java`:

```java
import java.util.*;
import java.util.concurrent.*;
public class ExecutorInvokeAllContrastDemo {
  public static void main(String[] args)throws Exception{
    ForkJoinPool pool=new ForkJoinPool(2);
    try{
      List<Callable<Integer>> callables=List.of(()->10,()->20,()->30);
      List<Future<Integer>> futures=pool.invokeAll(callables);
      int sum=0;for(Future<Integer> f:futures)sum+=f.get();
      System.out.println("futures-count="+futures.size());
      System.out.println("all-done="+futures.stream().allMatch(Future::isDone));
      System.out.println("callables-sum="+sum);
    }finally{pool.shutdown();pool.awaitTermination(5,TimeUnit.SECONDS);}
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all ExecutorInvokeAllContrastDemo.java
java ExecutorInvokeAllContrastDemo
```

**stdout đã kiểm thử:**

```text
futures-count=3
all-done=true
callables-sum=60
```

Đây là **instance method `pool.invokeAll`**, với ba `Callable<Integer>`. Bạn nhận **List<Future<Integer>>** và phải gọi `get` để lấy `10+20+30=60`. Không có `RecursiveTask` tự định nghĩa và không dùng static `ForkJoinTask.invokeAll`.

**Bản có timeout:**

```java
List<Future<Integer>> futures =
        pool.invokeAll(callables, 5, TimeUnit.SECONDS);
```

Đây là snippet. Theo `ExecutorService`, khi method trở về, tasks chưa hoàn tất được cancel nếu đã hết timeout; mỗi `Future` có thể thành công, fail hoặc cancel. **Không suy kết quả đều thành công** chỉ vì `invokeAll` đã trả về. Trong sản phẩm cần kiểm tra `isCancelled`/`get` và policy cho incomplete work.

### 8.2. Bảng so sánh xử lý kết quả và lỗi

| Thuộc tính | Static ForkJoinTask.invokeAll | ExecutorService/ForkJoinPool.invokeAll |
| --- | --- | --- |
| Tham số | `ForkJoinTask` objects | `Callable<T>` objects |
| Kết quả lời gọi | `void` hoặc cùng Collection tasks | `List<Future<T>>` |
| Lấy giá trị task | `task.join()` | `future.get()` |
| Một task ném unchecked exception | `invokeAll` có thể ném ngay; trạng thái siblings không bảo đảm | Method chờ hết batch; task failure nằm ở `Future.get` |
| Bản timed overload | Không có tham số timeout cho static overloads cơ bản | Có `invokeAll(tasks,timeout,unit)` |
| InterruptedException | `join` không ném checked InterruptedException | `invokeAll` và `Future.get` có thể ném |
| Thứ tự trả kết quả | Người gọi duy trì references/Collection | Futures trong list theo iterator order |
| Đầu vào tốt nhất | Cây `RecursiveTask/RecursiveAction` | Batch `Callable` độc lập |
| Một root cho toàn job | Thường `pool.invoke(new Root(...))` | Trực tiếp `pool.invokeAll(callables)` |

## 9. InvokeAll cho reduce phức hợp: một lần chia, nhiều thống kê

Tổng số không phải reduction duy nhất. Bạn có thể tính cùng lúc `count`, `sum`, `min`, `max` bằng một `RecursiveTask<Stats>` rồi gộp hai `Stats` con.

Một `record` Java là container bất biến tương đối gọn khi các components là primitive types. Records là tính năng Java hiện đại (đã ổn định trước Java 17), phù hợp với Java 17+.

### 9.1. Ví dụ runnable: trả record Stats

Tạo `InvokeAllStatsDemo.java`:

```java
import java.util.concurrent.*;
public class InvokeAllStatsDemo {
  record Stats(long count,long sum,int min,int max){
    Stats merge(Stats other){
      return new Stats(count+other.count,Math.addExact(sum,other.sum),
        Math.min(min,other.min),Math.max(max,other.max));
    }
  }
  static final class StatsTask extends RecursiveTask<Stats>{
    private static final long serialVersionUID=1L;
    final int[] data;final int lo,hi;
    StatsTask(int[] data,int lo,int hi){this.data=data;this.lo=lo;this.hi=hi;}
    @Override protected Stats compute(){
      if(hi-lo<=2){
        if(hi==lo)return new Stats(0,0,Integer.MAX_VALUE,Integer.MIN_VALUE);
        long sum=0;int min=Integer.MAX_VALUE,max=Integer.MIN_VALUE;
        for(int i=lo;i<hi;i++){sum=Math.addExact(sum,data[i]);min=Math.min(min,data[i]);max=Math.max(max,data[i]);}
        return new Stats(hi-lo,sum,min,max);
      }
      int mid=lo+(hi-lo)/2;
      StatsTask a=new StatsTask(data,lo,mid),b=new StatsTask(data,mid,hi);
      ForkJoinTask.invokeAll(a,b);
      return a.join().merge(b.join());
    }
  }
  public static void main(String[] args)throws Exception{
    int[] data={-3,10,8,1,0,2};
    ForkJoinPool pool=new ForkJoinPool(3);
    try{
      Stats result=pool.invoke(new StatsTask(data,0,data.length));
      System.out.println("count="+result.count());
      System.out.println("sum="+result.sum());
      System.out.println("min="+result.min());
      System.out.println("max="+result.max());
    }finally{pool.shutdown();pool.awaitTermination(5,TimeUnit.SECONDS);}
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all InvokeAllStatsDemo.java
java InvokeAllStatsDemo
```

**stdout đã kiểm thử:**

```text
count=6
sum=18
min=-3
max=10
```

Đây là một cây `invokeAll(a,b)` đệ quy. Mỗi leaf trả một `Stats` cho phạm vi của mình; parent nhận hai records rồi merge theo các phép reduce. Không ghi chung vào một `ArrayList` hay shared non-thread-safe map.

**Giới hạn:** `Stats(0,0,Integer.MAX_VALUE,Integer.MIN_VALUE)` dùng hai sentinels như identity cho min/max; đây là thiết kế nội bộ. Nếu API công khai cần phân biệt “không có min/max vì collection rỗng”, hãy quy định count=0 là trường hợp đặc biệt, dùng `OptionalInt` hoặc throw theo business contract — đừng biểu diễn một giá trị min giả.

### 9.2. Tính kết hợp và độ chính xác

`Math.min`/`Math.max` có tính kết hợp phù hợp với int. `sum` với `long` cần chọn cách xử lý overflow. `Math.addExact` phát hiện overflow trong quá trình combine, nhưng với tập vừa có giá trị dương/âm cực lớn, **một thứ tự gộp khác có thể overflow trung gian dù tổng toán học cuối vẫn hợp lệ**.

Nếu đầu vào có miền rộng, bạn có thể dùng `BigInteger` hoặc thiết kế tính toán có chứng minh giới hạn, thay vì đổi cấu trúc cây rồi giả định mọi numeric semantics hoàn toàn không đổi.

Với `double`/`float`, sự khác nhau về thứ tự cộng có thể làm thay đổi rounding. Nếu cần reproducibility bit-for-bit, không tùy ý gộp theo thứ tự thực thi không xác định. Nếu chỉ cần sai số trong tolerance, định nghĩa tolerance/algorithm theo domain.

## 10. Chia batch với collection: tránh task cho từng phần tử

`invokeAll(Collection)` hữu ích khi số child tasks tính từ input, chẳng hạn mảng có N phần tử và mỗi task xử lý một khối `chunkSize`.

```text
N = 24; chunkSize = 6

Task 1: [ 0,  6)
Task 2: [ 6, 12)
Task 3: [12, 18)
Task 4: [18, 24)

ForkJoinTask.invokeAll(List.of(t1, t2, t3, t4))
Sau successful completion: join từng task rồi cộng results.
```

**Bắt buộc validate** `chunkSize > 0`. Nếu chunkSize=0, vòng chia batch có thể không tiến và gây vòng lặp vô hạn; nếu chunkSize âm, còn có khả năng sai offset nghiêm trọng.

### 10.1. Ví dụ runnable: một collection được tạo động

Tạo `InvokeAllChunkBatchDemo.java`:

```java
import java.util.*;
import java.util.concurrent.*;
public class InvokeAllChunkBatchDemo {
  static final class ChunkSum extends RecursiveTask<Long>{
    private static final long serialVersionUID=1L;
    final int[] data;final int lo,hi;
    ChunkSum(int[] data,int lo,int hi){this.data=data;this.lo=lo;this.hi=hi;}
    @Override protected Long compute(){
      long result=0;for(int i=lo;i<hi;i++)result+=data[i];
      return result;
    }
  }
  static final class Batch extends RecursiveTask<Long>{
    private static final long serialVersionUID=1L;
    final int[] data;final int chunkSize;
    Batch(int[] data,int chunkSize){this.data=data;this.chunkSize=chunkSize;}
    @Override protected Long compute(){
      if(chunkSize<=0)throw new IllegalArgumentException("chunkSize must be positive");
      List<ChunkSum> tasks=new ArrayList<>();
      for(int lo=0;lo<data.length;lo+=chunkSize){
        tasks.add(new ChunkSum(data,lo,Math.min(data.length,lo+chunkSize)));
      }
      ForkJoinTask.invokeAll(tasks);
      long sum=0;for(ChunkSum task:tasks)sum+=task.join();
      System.out.println("chunks="+tasks.size());
      return sum;
    }
  }
  public static void main(String[] args)throws Exception{
    int[] data=new int[24];for(int i=0;i<data.length;i++)data[i]=i+1;
    ForkJoinPool pool=new ForkJoinPool(4);
    try{
      System.out.println("sum="+pool.invoke(new Batch(data,6)));
      System.out.println("empty-sum="+pool.invoke(new Batch(new int[0],6)));
    }finally{pool.shutdown();pool.awaitTermination(5,TimeUnit.SECONDS);}
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all InvokeAllChunkBatchDemo.java
java InvokeAllChunkBatchDemo
```

**stdout đã kiểm thử:**

```text
chunks=4
sum=300
chunks=0
empty-sum=0
```

Đây là tổng các số từ 1 đến 24, bằng 300. Vì `24/6=4`, có đúng bốn task. Đầu vào mảng rỗng tạo **collection rỗng**, vẫn là trường hợp hợp lệ: `invokeAll(tasks)` không cần fork task nào, và tổng phần tử trung hòa là 0.

**Chú ý:** bài toán này có thể giải bằng một vòng for rất nhanh với 24 phần tử. Mục đích demo là kiểm tra cơ chế collection và identity của reduce, không khẳng định Fork/Join tăng hiệu năng trên input nhỏ.

### 10.2. Granularity: chọn chunkSize như thế nào?

Với `chunkSize=1` và hàng triệu phần tử, bạn có thể tạo **hàng triệu objects task**, làm GC, allocation và scheduling chiếm phần lớn chi phí. Với chunk quá lớn, chỉ một vài tasks có thể không tận dụng workers.

Hãy cân bằng:

- Chi phí xử lý mỗi phần tử.
- Số lõi CPU thực tế và quota của container.
- Chi phí tạo task/call `invokeAll`/join.
- Cache locality, memory bandwidth và kích thước buffer.
- Sự mất cân bằng tải giữa các chunks.
- Chi phí gộp kết quả và type boxing.
- Mức memory cần giữ cho collection tasks.

Một nguyên tắc thực dụng là **mỗi leaf nên thực hiện đủ tính toán hữu ích để bù overhead**, và tổng số tasks nên đủ để workers có thể phân chia công việc. Tuy nhiên, **không có con số leaf/chunk chuẩn áp dụng cho mọi workload**: benchmark trên dữ liệu mục tiêu.

### 10.3. Về scalability của một Collection khổng lồ

Lời gọi `invokeAll` với một collection rất lớn vẫn cần tạo/giữ tất cả task objects và coordination state. Với dữ liệu cực lớn, cân nhắc:

- Một cây đệ quy theo threshold.
- Chia thành batches có giới hạn.
- Pipeline có backpressure và giới hạn jobs in-flight.
- Một cách reduce khác (`IntStream`/`LongStream`/parallel stream) nếu đủ phù hợp.
- Chọn xử lý tuần tự nếu computation đơn giản, data nhỏ hoặc memory bandwidth đang bão hòa.

Không hiểu `invokeAll` là cơ chế tự động điều tiết số task objects, giới hạn RAM hoặc input quotas.

## 11. Edge cases: collection rỗng và task null

API có các validation quan trọng:

- `ForkJoinTask.invokeAll((Collection<T>)null)` → `NullPointerException`.
- Collection chứa một task `null` → `NullPointerException`.
- Overload hai task nhận `null` → `NullPointerException`.
- Empty collection/empty varargs được chấp nhận; không có công việc cần thực hiện.
- Task đã sử dụng hoàn tất trong cây khác không nên tái sử dụng tùy tiện như một command có thể chạy đi chạy lại; thường tạo **task instance mới cho mỗi lượt**.

### 11.1. Ví dụ runnable: empty collection và null input

Tạo `InvokeAllEmptyAndValidationDemo.java`:

```java
import java.util.*;
import java.util.concurrent.*;
public class InvokeAllEmptyAndValidationDemo {
  static final class Root extends RecursiveTask<Integer>{
    private static final long serialVersionUID=1L;
    @Override protected Integer compute(){
      List<ForkJoinTask<?>> none=new ArrayList<>();
      Collection<ForkJoinTask<?>> returned=ForkJoinTask.invokeAll(none);
      ForkJoinTask.invokeAll(new ForkJoinTask<?>[0]);
      System.out.println("empty-same-reference="+(returned==none));
      System.out.println("empty-size="+returned.size());
      boolean nullRejected=false;
      try{ForkJoinTask.invokeAll((ForkJoinTask<?>)null,new RecursiveTask<Integer>(){
        private static final long serialVersionUID=1L;
        @Override protected Integer compute(){return 1;}
      });}catch(NullPointerException ex){nullRejected=true;}
      System.out.println("null-rejected="+nullRejected);
      return 0;
    }
  }
  public static void main(String[] args)throws Exception{
    ForkJoinPool pool=new ForkJoinPool(2);
    try{System.out.println("result="+pool.invoke(new Root()));}
    finally{pool.shutdown();pool.awaitTermination(5,TimeUnit.SECONDS);}
  }
}
```

```bash
javac -encoding UTF-8 -Xlint:all InvokeAllEmptyAndValidationDemo.java
java InvokeAllEmptyAndValidationDemo
```

**stdout đã kiểm thử:**

```text
empty-same-reference=true
empty-size=0
null-rejected=true
result=0
```

Phần `null` được kiểm tra chủ động; chương trình **không** xem `null` là “bỏ qua task”. Trong thực tế, không nên dựa vào việc exception xảy ra tại một index cố định sau khi một vài tasks đã được fork. Validate toàn bộ collection trước khi gọi nếu side effects/partial execution là vấn đề.

### 11.2. Không mutate danh sách tasks trong khi chạy

Với collection dùng chung, nếu thread khác thêm/xóa task trong lúc `invokeAll` đang chạy, bạn có thể gặp vấn đề consistency hoặc fail-fast tùy collection. API không hứa sẽ tạo một snapshot an toàn thay cho bạn.

Trong những hệ thống nhiều producer, hãy **gom dữ liệu thành một danh sách bất biến/snapshot** rồi submit batch; không cho producers chỉnh collection của một batch đang được thực thi.

## 12. Kết quả, visibility và thứ tự

### 12.1. Task scheduling không bảo đảm thứ tự

`invokeAll(taskA,taskB,taskC)` không bảo đảm:

- A luôn bắt đầu trước B.
- B luôn hoàn tất trước C.
- A chạy trên thread số 1.
- Một task riêng phải tạo một thread mới.
- Số task chạy đồng thời bằng số `getParallelism` trong mọi thời điểm.
- Mỗi task luôn được “steal” đúng một lần hoặc bất kỳ lần nào.

**Đừng in từng task vào stdout rồi assert đúng một thứ tự**. Test phần tính toán **đầu ra**; nếu business cần thứ tự, gộp theo index/offset đã định nghĩa.

### 12.2. Join cung cấp đồng bộ kết quả

Sau khi `ForkJoinTask.invokeAll` trở về **bình thường**, mỗi task đã `isDone` và `join` trả kết quả tương ứng. Bạn có thể đọc dữ liệu đã được cập nhật hợp lệ theo các quy tắc đồng bộ của `ForkJoinTask`, miễn là dữ liệu không bị một thread khác tiếp tục sửa ngoài protocol.

**Không** đọc shared output array trước khi root hoàn tất nếu những task con vẫn đang ghi. **Không** dùng một `ArrayList` thường để cho nhiều tasks đồng thời `add`, vì collection đó không thread-safe.

### 12.3. Kiểu trả về của RecursiveAction

`RecursiveAction` không có kết quả application-level; nó là `ForkJoinTask<Void>`. Khi static `invokeAll` returns normally, công việc của action đã kết thúc. Không cần ép `join` trả một `String` hoặc một `Integer` để đánh dấu thành công.

### 12.4. Thứ tự gộp khi cần reproducibility

Một phép combine với tính kết hợp thật sự (`Math.max`, sum integer trong miền không overflow) có thể gộp theo cây. Với nối String/byte arrays, thứ tự nhánh **quan trọng**: bạn cần gộp kết quả theo offset, không theo callback completion order.

Với floating-point, phép cộng chịu rounding, nên thay thứ tự reduce có thể thay bit-level result. Nếu yêu cầu ổn định tuyệt đối, định nghĩa thứ tự, numeric algorithm và chính sách so sánh.

## 13. Work stealing, pool và performance

`ForkJoinPool` dùng **work stealing**, giúp workers có thể lấy nhiệm vụ đang chờ từ workers khác. Mẫu divide-and-conquer thích hợp vì một task có thể fork nhánh còn lại rồi tự thực hiện công việc.

`invokeAll` có thể giảm code điều phối khi nhiều tasks phải được thực thi. Tuy nhiên:

- Nó vẫn có overhead scheduling và join.
- Số task có thể rất nhiều hơn số workers.
- Parallelism cao không bảo đảm tăng tốc nếu bộ nhớ là bottleneck.
- Unbalanced branches có thể làm workers không đều việc.
- Nếu trong leaf có blocking I/O, database wait hoặc lock contended, work stealing không thể tự giải quyết tài nguyên ngoài CPU.
- Không suy tốc độ từ `getStealCount()` hay `getQueuedTaskCount()` tại một thời điểm duy nhất.

### 13.1. Mẫu lựa chọn pool

**Pool riêng** hợp khi subsystem cần isolation/quota/lifecycle rõ ràng:

```java
ForkJoinPool pool = new ForkJoinPool(4);
try {
    Result result = pool.invoke(rootTask);
    // Sử dụng result đã hoàn tất.
} finally {
    pool.shutdown();
}
```

Đây là snippet. Trong service dài hạn, tạo pool một lần rồi reuse; không tạo pool per request/per leaf. Với Java 17, dùng `shutdown`/`awaitTermination`; không dùng `ForkJoinPool.close()` trong ví dụ hứa chạy Java 17 vì overload `close` chỉ có trong các phiên bản mới hơn.

**Common pool:** `ForkJoinPool.commonPool()` được nhiều thành phần có thể chia sẻ. Nó thích hợp với một số jobs CPU ngắn và được quản lý JVM; module của bạn **không nên tự shutdown common pool**. Nếu SLA/tenant isolation quan trọng, dedicated pool có thể tốt hơn.

### 13.2. Cách benchmark có ý nghĩa

Đo **sequential baseline**, rồi thử `fork-one-compute-one-join`, `invokeAll`, parallel stream và những thresholds khác nhau. Khi đo:

1. Dùng dữ liệu đủ lớn, đa dạng giống production.
2. Warm up JIT và tránh đo lần class loading đầu tiên.
3. Không trộn bước tạo mảng/random data với thời gian computation.
4. Quan sát allocation/GC, CPU, throughput và tail latency.
5. Kiểm tra input có cache locality/memory bandwidth thực tế.
6. Đặt workload parallelism hợp với CPU quota/container, không chỉ số cores trên host.
7. So correctness bằng baseline sau mỗi trial.
8. Tránh kết luận từ một lần `System.nanoTime` trên bài demo nhỏ.
9. Dùng JMH nếu cần microbenchmark có kiểm soát.
10. Đo cả **chi phí gộp kết quả**, không chỉ thời gian children.

**Không có bảo đảm** `invokeAll` nhanh hơn `fork()/compute()/join()` trong mọi bài toán. Chọn ngữ nghĩa rõ và đo performance trước khi “tối ưu” theo trực giác.

## 14. Exception, cancellation và dữ liệu cập nhật một phần

Một lần `invokeAll` thất bại có hai tầng cần phân biệt.

**Tầng task:** một child ném unchecked exception, bị cancel hoặc tạo partial side effects.

**Tầng job:** root task có thể truyền lỗi tới caller, nhưng pool không tự rollback database/file/array; các siblings có thể đã làm việc xong hoặc chưa.

Các nguyên tắc production:

- Với **pure computations**, trả immutable partial result; chỉ publish khi toàn root thành công.
- Với mutable arrays, chia **disjoint ranges**; nếu require atomic publish, dùng output array riêng.
- Với database/network writes, Fork/Join không thay thế transaction/idempotency.
- Khi exception xảy ra, không assume mọi sibling đều bị cancel hoặc đã hoàn tất.
- Nếu có cancellation token, dùng `AtomicBoolean`/`volatile` theo yêu cầu visibility.
- Không dùng `Thread.stop` hoặc các API legacy để ép dừng; chúng không an toàn.
- Không re-run một `ForkJoinTask` đã completed bằng cách gọi lại `invokeAll` trên cùng object mà kỳ vọng `compute` chạy lại.
- Định nghĩa failure policy: fail-fast, collect errors, best-effort partial result hay all-or-nothing tùy bài toán.

### 14.1. Muốn thu tất cả lỗi thay vì fail-fast thì sao?

Static `ForkJoinTask.invokeAll` **không phải tiện ích “thu tất cả exceptions rồi đưa về list”**. Nếu muốn có một kết quả lỗi/đúng cho từng nhánh, bạn có thể:

- Để mỗi task bắt **lỗi nghiệp vụ dự kiến** rồi trả một result kiểu `Success/Failure`, tránh làm task fail bất thường.
- Dùng `ExecutorService.invokeAll` để có một `Future` cho mỗi Callable, rồi đọc mỗi `get` và thu `ExecutionException.getCause()` — vẫn cần xử lý interruption và không cho fail mọi job vì một error nếu domain cho phép.
- Dùng `CompletableFuture.allOf` khi có những tác vụ được quản lý dưới dạng CompletableFuture và cần phối hợp chúng, nhưng lưu ý API/semantics khác, không tự giải quyết rollback/cancellation bên dưới.
- Không bắt `Throwable` chung trong mọi leaf rồi lặng lẽ coi mọi Error là một dữ liệu thường. Phân biệt lỗi domain có thể phục hồi với lỗi hạ tầng/JVM nghiêm trọng.

### 14.2. Không dùng join đợi một dependency có chu trình

Sai về cấu trúc:

```text
Task A: invokeAll(B, C) → đợi B và C
Task B: chờ Future A hoặc lock do A giữ
Task C: hoàn tất nhanh
Task A: không thể trở lại vì B không thể tiến
```

ForkJoinPool có work stealing **không tự phá được dependency cycle**. Đảm bảo graph parent→children không chu trình, tránh giữ lock cần bởi children khi gọi `invokeAll`/`join`.

### 14.3. Bounded work và input không tin cậy

Không cho request client tự do tạo hàng triệu tasks cho đến khi JVM hết RAM. Áp dụng:

- Quota input size (số phần tử, kích thước dữ liệu).
- Chunk threshold dương được validate.
- Giới hạn jobs đang active ở cấp service; **pool parallelism không tự giới hạn số task objects**.
- Deadline của request, cancellation token và cleanup policy.
- Metrics cho queue size, running workers, latency và exceptions.
- Backpressure/rejection khi hệ thống bận.
- Bảo vệ ownership của dữ liệu và validation trước khi publish output.

## 15. Kiểm thử và QA

Khi viết test cho `invokeAll`, **không giả định thứ tự chạy threads**. Một bộ test tốt nên xác minh:

1. Tổng mảng sau fork/join bằng baseline tuần tự.
2. Hai overload hai-task và varargs cho kết quả đúng.
3. Collection overload trả chính object collection đầu vào.
4. Sau **normal return**, các tasks trong nhóm đã `isDone`.
5. Hai `RecursiveAction`/nhiều segments không ghi chồng cùng index.
6. Input rỗng hoạt động theo identity của bài toán, ví dụ sum=0.
7. Null tasks bị từ chối, không bị coi là “skip”.
8. Task lỗi khiến root báo lỗi, nhưng không assert tất cả siblings đã cancel.
9. Kết quả không đổi với parallelism=1,2,4 nếu phép combine hợp lệ.
10. Threshold=1/4/16 thay đổi số leaf, **không thay đổi correctness**.
11. Negative input và trường hợp overflow được xử lý rõ.
12. Multiple nested tasks không vô tình tạo cyclic waits.
13. Task có side effects không tự động được coi là transaction.
14. Dedicated pool được shutdown đúng, không làm common pool bị ngừng.
15. Không phụ thuộc số steals hoặc task execution order.
16. Với dữ liệu thực, benchmark và theo dõi resource use.

### 15.1. Chạy cả chín chương trình

Mỗi chương trình trong bài là một file `.java` độc lập, tên file đúng bằng tên `public class`. Biên dịch từng file:

```bash
javac -encoding UTF-8 -Xlint:all InvokeAllPairSumDemo.java
javac -encoding UTF-8 -Xlint:all InvokeAllVarargsDemo.java
javac -encoding UTF-8 -Xlint:all InvokeAllCollectionDemo.java
javac -encoding UTF-8 -Xlint:all InvokeAllActionDemo.java
javac -encoding UTF-8 -Xlint:all InvokeAllFailureDemo.java
javac -encoding UTF-8 -Xlint:all ExecutorInvokeAllContrastDemo.java
javac -encoding UTF-8 -Xlint:all InvokeAllStatsDemo.java
javac -encoding UTF-8 -Xlint:all InvokeAllChunkBatchDemo.java
javac -encoding UTF-8 -Xlint:all InvokeAllEmptyAndValidationDemo.java
```

Sau đó chạy class mong muốn:

```bash
java InvokeAllPairSumDemo
```

Mã dùng các API chuẩn của JDK 17+; không cần Maven/Gradle hoặc external dependency. Các stdout nêu ở từng chương trình đã được kiểm tra bằng cách chạy mã. Một số snippet rút gọn bên ngoài các `public class` là **minh họa**, không phải source hoàn chỉnh.

### 15.2. Kiểm thử stress tránh false assumptions

Không assert “task1 luôn chạy trước task2” — scheduling không được hứa. Không assert số active workers luôn bằng configured parallelism — worker availability biến thiên. Không sleep 10ms rồi kết luận tasks đã hoàn tất — hãy dùng `pool.invoke(root)`, `join` hoặc `Future.get(timeout)` ở harness phù hợp.

Với code có mutation disjoint ranges, so toàn bộ output array sau khi root hoàn tất. Với reduce, so exact result cho integer inputs trong miền bảo đảm hoặc so tolerance/domain contract cho floating-point.

## 16. Các anti-pattern thường gặp

| Anti-pattern | Vấn đề | Sửa |
| --- | --- | --- |
| Gọi `ForkJoinTask.invokeAll` rồi mong có `List<Future>` | Sai overload/return type | Dùng chính task references và `join` |
| Nhầm `pool.invokeAll(callables)` là static task utility | Hai API khác nhau | Đọc class và parameter types |
| Coi “invokeAll xong” là transaction all-or-nothing | Không rollback side effects | Output riêng, publish sau success |
| Task fail nhưng vẫn đọc mọi siblings như đã thành công | Trạng thái sau exceptional return không bảo đảm | Kiểm tra status/recovery |
| Assert sibling luôn bị cancel nếu một task fail | Javadoc không hứa | Không phụ thuộc cancellation order |
| Tạo một task cho từng item nhỏ | Overhead/GC lớn | Chunk threshold, batching |
| Không có base case trong RecursiveTask | Recursion vô tận/task explosion | Điều kiện dừng giảm kích thước |
| Trộn task types rồi cast result mù | ClassCastException/khó bảo trì | Type-safe collection và explicit result |
| Dùng collection mutable đang bị thread khác sửa | Không có batch snapshot nhất quán | Snapshot immutable before submit |
| Gửi `null` task để chỉ “không có việc” | `NullPointerException` | Loại null trước, collection rỗng |
| Dùng task đã completed cho một lượt tính mới | Không chạy lại như new task | Tạo task instance mới |
| Gọi `new ForkJoinPool` trong mỗi compute | Cạn threads/resources | Dùng pool cấp service |
| Shutdown common pool sau một batch | Ảnh hưởng tài nguyên chung hoặc vô hiệu | Chỉ shutdown dedicated pool |
| Hai RecursiveAction cùng ghi một index | Data race/corruption | Disjoint ranges/synchronization |
| Đọc array trước khi root complete | Thấy state chưa đầy đủ | Join/invoke root rồi đọc |
| Mọi leaf ghi `ArrayList.add` không khóa | Collection không thread-safe | Partial results rồi merge |
| Nhiều task giữ cùng lock khi tính | Gần như tuần tự, có nguy cơ deadlock | Giảm shared mutation |
| Gọi blocking I/O/JDBC trong hot leaf | CPU workers bị block | Executor/I/O model phù hợp |
| Thêm workers vô hạn để “giải deadlock” | Không phá wait-for cycle | Sửa dependency graph |
| Ignore overflow/reduction order | Sai dữ liệu nghiệp vụ | Numeric contract và tests |
| Đo thời gian bằng một run trên 10 phần tử | Kết luận thiếu tin cậy | JMH/representative workload |
| Dựa vào `getStealCount` làm correctness | Metric là quan sát runtime | So dữ liệu đầu ra |
| Chạy task với input size do client quyết định vô hạn | DoS CPU/RAM | Quotas/backpressure |

## 17. Checklist code review cho invokeAll

1. Bạn đang gọi **static `ForkJoinTask.invokeAll`** hay **instance `ForkJoinPool.invokeAll`**?
2. Tham số là `ForkJoinTask` objects hay `Callable`? Kiểu trả về nào?
3. Mỗi task có nhiệm vụ độc lập hoặc dependency DAG không chu trình không?
4. Có base case và threshold dương bảo đảm termination không?
5. Mỗi lần chia có tạo intervals không chồng lấp không?
6. Có `mid=lo+(hi-lo)/2` để tránh overflow trong tính midpoint không?
7. Có tránh giữ lock khi đợi `invokeAll`/`join` không?
8. Có biết `invokeAll` không tự gộp kết quả cho bạn không?
9. Với `RecursiveTask`, có `join` đúng type để lấy result sau normal return không?
10. Với `RecursiveAction`, có chờ hoàn tất trước khi đọc vùng shared output không?
11. Có xử lý **exceptional return** mà không assume siblings đều kết thúc tốt không?
12. Có không phụ thuộc thứ tự tasks chạy/hoàn tất không?
13. Có bảo vệ dữ liệu shared mutable hoặc dùng disjoint ranges không?
14. Có snapshot input hoặc quy tắc ownership nếu thread khác có thể mutate không?
15. Có phần tử trung hòa/reduce semantics chính xác với input rỗng không?
16. Có tránh `Math.max` dùng identity sai khi dữ liệu âm không?
17. Có xét overflow/rounding và reproducibility yêu cầu bởi domain không?
18. Có validate null collection/null elements trước khi tạo side effects không?
19. Có tránh sửa collection trong lúc `invokeAll` chạy không?
20. Có tránh reuse completed task object cho lần job mới không?
21. Có chọn chunk threshold dựa trên đo lường, không copy ngẫu nhiên từ demo không?
22. Có giới hạn số jobs/tasks in-flight và số bytes/objects được giữ không?
23. Có không chạy blocking I/O dài trong CPU-bound fork/join pool không?
24. Nếu dùng commonPool, có hiểu các workloads chia sẻ tài nguyên không?
25. Nếu dedicated pool, có owner và shutdown/await hợp lệ không?
26. Có không dùng API chỉ có JDK mới hơn khi hứa Java 17 không?
27. Có dùng baseline tuần tự và cases cực trị để test correctness không?
28. Có biết static invokeAll không có timed overload tương đương ExecutorService không?
29. Có chính sách interruption/cancel phù hợp với từng API không?
30. Có coi code thành công và thất bại là hai đường lifecycle riêng không?
31. Có xác nhận bằng benchmark trước khi khẳng định đạt speedup không?
32. Có đảm bảo dữ liệu/buffer/pool đều được dọn kể cả khi exception không?

## 18. Bài tập thực hành

**Bài 1 — Hai task.** Chạy `InvokeAllPairSumDemo` với threshold=2. Dự đoán số leaves rồi đối chiếu stdout; giải thích tại sao tổng vẫn giữ 136.

**Bài 2 — Chỉ một task trả result.** Sửa chương trình pair để một nhánh tính sum và nhánh kia tính số phần tử, trả một record chứa cả hai. Kiểm tra contract gộp.

**Bài 3 — Varargs.** Chạy `InvokeAllVarargsDemo` với bốn `SquareTask` từ 2 đến 5. Kiểm tra tất cả `isDone` sau normal return và tổng bình phương.

**Bài 4 — Collection.** Chạy `InvokeAllCollectionDemo` với 10 task và kiểm tra `returned == tasks`. Vì sao nó không phải một `List<Future<Integer>>` mới?

**Bài 5 — RecursiveAction.** Chạy `InvokeAllActionDemo` với mảng 100 phần tử chia thành các intervals có kích thước khác nhau. Xác minh mỗi phần tử được nhân đúng một lần.

**Bài 6 — Exception.** Chạy `InvokeAllFailureDemo`. Thử nhiều tasks cùng ném exception và giải thích vì sao API không cam kết ném một exception cụ thể hay trạng thái sibling cụ thể.

**Bài 7 — ExecutorService contrast.** Chạy `ExecutorInvokeAllContrastDemo`, thêm một Callable ném `IllegalArgumentException`; quan sát `pool.invokeAll` trả list Futures và `Future.get` nào ném `ExecutionException`.

**Bài 8 — Timed invokeAll của ExecutorService.** Thiết kế test có tasks đang chờ latch (đặt deadline, tránh CI treo); gọi overload `pool.invokeAll(tasks,timeout,unit)` và kiểm tra `isCancelled` theo contract. So sánh với static ForkJoinTask.invokeAll không có timed overload.

**Bài 9 — Stats.** Chạy `InvokeAllStatsDemo` với mảng có số âm, số dương và trùng lặp. Thêm trường countPositive/average và định nghĩa chính xác behavior của mảng rỗng.

**Bài 10 — Merge sort.** Dùng `ForkJoinTask.invokeAll(leftSort,rightSort)` ở mỗi node, sau khi thành công merge hai phần đã sort. So với `Arrays.sort` trên dữ liệu ngẫu nhiên.

**Bài 11 — Batching.** Chạy `InvokeAllChunkBatchDemo` với 25 phần tử và chunkSize=6. Xác định số chunks/intervals và sum chính xác, không đoán các tasks sẽ chạy theo thứ tự.

**Bài 12 — Invalid chunkSize.** Thử chunkSize=0 và -1, đảm bảo `IllegalArgumentException` được báo thay vì chạy vòng lặp không tiến.

**Bài 13 — Empty tasks.** Chạy `InvokeAllEmptyAndValidationDemo`. Giải thích khác nhau giữa empty collection hợp lệ và phần tử null không hợp lệ.

**Bài 14 — Cancellation.** Cancel một `RecursiveTask` trước khi chạy rồi gọi `join()`; ghi nhận `CancellationException`. Không khẳng định cancel(true) sẽ interrupt running workers.

**Bài 15 — Failure và side effects.** Thiết kế `RecursiveAction` ghi vào output array riêng; nếu một task lỗi, không publish array. Giải thích vì sao `invokeAll` không tự rollback dữ liệu đã sửa.

**Bài 16 — Associativity.** So phép cộng, max, phép trừ, string concatenation và double sum. Chọn phép gộp nào an toàn khi thay cấu trúc cây hoặc thứ tự combine?

**Bài 17 — CommonPool vs dedicated pool.** Chạy cùng một cây trong `ForkJoinPool.commonPool()` và pool riêng, so correctness/metrics. Không gọi shutdown commonPool từ một module.

**Bài 18 — Performance.** Dùng JMH, thử sequential loop, manual fork-one/compute-one/join-one, `ForkJoinTask.invokeAll` và parallel stream với N=10³/10⁶/10⁷; đo speedup, allocation và CPU utilization.

**Bài 19 — Thread safety.** Tạo hai tasks ghi chồng index (sandbox), nhận diện data race, sửa bằng disjoint ranges hoặc immutable partial results.

**Bài 20 — Production review.** Thiết kế batch CPU-bound xử lý đầu vào lớn do client cung cấp: validate size, chunk threshold, quota, executor ownership, exception aggregation, graceful shutdown, metrics và rollback/publish policy.

## 19. Tổng kết

- `ForkJoinTask.invokeAll` là tiện ích **thực thi và phối hợp nhiều `ForkJoinTask`** theo mô hình divide-and-conquer.
- Có **ba overload static**: hai task (`void`), varargs (`void`), và collection (**trả lại chính collection**).
- Sau **normal return**, nhóm tasks đã hoàn tất; với `RecursiveTask<V>` dùng `join()` để lấy typed results, với `RecursiveAction` có thể chỉ cần biết tất cả actions xong.
- Khi một task lỗi, `invokeAll` **có thể ném ngay unchecked exception** và trạng thái các siblings **không được bảo đảm**; không có transaction/rollback tự động.
- **Đừng nhầm** với `ForkJoinPool.invokeAll(Collection<Callable<T>>)` từ `ExecutorService`, trả `List<Future<T>>` và có overload timeout/interruption khác.
- Work stealing có thể giúp phân bố tasks, nhưng **không cam kết tốc độ, thứ tự, số threads hoạt động hay an toàn của shared mutable state**.
- Threshold, non-overlap, kết hợp hợp lệ, overflow, lỗi và cancellation quyết định tính đúng đắn của bài toán.
- Với collection lớn, phải quản lý chunking, task counts, quotas và backpressure; một task cho từng phần tử nhỏ thường gây overhead.
- So với parallel stream, `Arrays.parallelSort` và vòng lặp tuần tự, chọn API theo nhu cầu thật và benchmark.
- Những ví dụ dùng **Java 17+ hiện hành**, không dựa vào kỹ thuật legacy.

## Tài liệu chính thức

- [ForkJoinTask — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ForkJoinTask.html): ba overload static `invokeAll`, `join`, exception và cancellation semantics.
- [ForkJoinTask — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ForkJoinTask.html): tài liệu cho các Java LTS hiện đại.
- [ForkJoinPool — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ForkJoinPool.html): pool invoke, pool invokeAll, work stealing, parallelism và lifecycle.
- [ExecutorService — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html): `invokeAll(Collection<Callable<T>>)`, timed overload và Future ordering.
- [RecursiveTask — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/RecursiveTask.html): task trả giá trị.
- [RecursiveAction — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/RecursiveAction.html): task không trả giá trị.
- [Future — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Future.html): `get`, cancellation và errors.
- [Arrays — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Arrays.html): `sort`, `parallelSort`.
- [Math — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Math.html): `addExact`, `multiplyExact` và chính sách phát hiện overflow.

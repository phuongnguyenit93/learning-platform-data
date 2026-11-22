# `RecursiveTask` cho kết quả và `RecursiveAction` cho hành động trong Java Fork/Join

## 1. Tình huống: cùng chia để trị, nhưng hai kiểu đầu ra khác nhau

Khi xử lý một mảng rất lớn, chúng ta có thể chia nó thành nhiều khoảng nhỏ, xử lý độc lập rồi ghép kết quả. Đây là hướng *divide and conquer* (chia để trị) phù hợp với Java Fork/Join framework. Tuy nhiên, có hai dạng nhu cầu khác nhau:

- **Tính toán và trả về một kết quả:** tính tổng, giá trị lớn nhất, thống kê, số lượng phần tử thỏa điều kiện, cây kết quả... Khi đó, ta thường tạo lớp kế thừa `RecursiveTask<V>`, hiện thực `protected V compute()` và **trả về một giá trị V**.
- **Thực hiện một hành động mà không có giá trị trả về:** biến đổi các phần tử trong mảng tại vị trí độc lập, điền dữ liệu vào những vùng không chồng lấp, thực hiện một công việc có side effect được kiểm soát... Khi đó, ta thường tạo lớp kế thừa `RecursiveAction`, hiện thực `protected void compute()` và hoàn tất mà **không trả về giá trị ứng dụng**.

Cả hai đều là con của `ForkJoinTask` và được lập lịch qua `ForkJoinPool`, có thể sử dụng `fork()`, `join()` và `invokeAll(...)` để phối hợp các nhiệm vụ con. Khác biệt quyết định là **kiểu và ý nghĩa của kết quả**: `RecursiveTask<Long>` cho một `Long`, còn `RecursiveAction` là `ForkJoinTask<Void>`, nên kết quả của `join()`/`invoke()` là `null` nếu hoàn tất bình thường. Điều này không có nghĩa hành động không có tác dụng; tác dụng thường nằm ở **trạng thái đầu ra mà nhiệm vụ đã sửa đổi**.

**Đề bài trực tiếp:** “RecursiveTask cho kết quả và RecursiveAction cho hành động”, thuộc nhóm “Fork/Join”.

**Phạm vi và Special Note:** hai lớp là API có từ Java 7 và **vẫn được hỗ trợ trên Java 17, Java 21 và JDK hiện đại**. Bài dùng Java NIO? **Không**: chúng thuộc `java.util.concurrent`, dành chủ yếu cho bài toán tính toán có thể chia nhỏ. Mọi ví dụ lập trình chính được kiểm thử bằng **JDK 21**. Không khuyến nghị API lỗi thời, legacy implementation hay sử dụng internal classes.

Bạn sẽ nắm được:

1. Chọn `RecursiveTask<V>` khi cần kết quả, `RecursiveAction` khi cần một hành động.
2. Viết đúng chữ ký `compute()`, base case, ngưỡng `THRESHOLD` và phép chia khoảng `[from, to)`.
3. Dùng `fork()`, `join()`, `invokeAll(...)`, `ForkJoinPool.invoke(...)` và `ForkJoinPool.submit(...)` đúng ngữ nghĩa.
4. Hiểu work-stealing và vì sao không phải “tạo một thread mới cho từng task”.
5. Cách tránh chia quá nhỏ, chờ task sai thứ tự, blocking I/O và race khi viết vào dữ liệu chia sẻ.
6. Xử lý kết quả `Void`, ngoại lệ, hủy bỏ, pool lifecycle và các lỗi đo hiệu năng.
7. Chạy chương trình Java 21 minh họa cả hai kiểu task với stdout có thể đối chiếu.

## 2. Bức tranh Fork/Join

Giả sử có tám số:

~~~text
[1, 2, 3, 4, 5, 6, 7, 8]
             |
          divide
             |
       +-----+------+
       |            |
   [1,2,3,4]     [5,6,7,8]
       |            |
     /   \\        /   \\
   [1,2][3,4]  [5,6][7,8]
     |    |      |    |
    3     7     11   15
     \\   /        \\   /
      10           26
        \\         /
             36
~~~

Đây là sơ đồ **`RecursiveTask<Long>` tính tổng**: mỗi lá tính tổng của một đoạn; mỗi nút cha ghép hai `Long` thành một `Long` mới. Kết quả cuối là `36`.

Cũng có thể chia mảng tương tự nhưng chọn **`RecursiveAction`** để nhân đôi *tại chỗ*:

~~~text
Mảng đầu vào (bản sao): [1, 2, 3, 4, 5, 6, 7, 8]
                     /                      \\
             [0,4)                            [4,8)
             /   \\                            /    \\
          [0,2) [2,4)                      [4,6) [6,8)
           |      |                          |      |
     sửa ô 0..1  2..3                      4..5   6..7
           \\      /                          \\      /
          không trả kết quả                   không trả kết quả
                     \\                       /
                  mảng sau: [2,4,6,8,10,12,14,16]
~~~

Ở dạng thứ hai, mỗi task **chỉ sửa các index trong khoảng mình sở hữu**; parent chờ chúng hoàn tất rồi trả về `void`. Vì các khoảng **không chồng lấp**, không cần các child tranh nhau ghi cùng một phần tử. Nếu không chia quyền sở hữu vùng dữ liệu, chỉ đổi `RecursiveTask` thành `RecursiveAction` sẽ **không tự giải quyết race condition**.

## 3. Định nghĩa và chữ ký Java

Hai lớp nằm trong `java.util.concurrent`:

~~~java
public abstract class RecursiveTask<V> extends ForkJoinTask<V> {
    protected abstract V compute();
}

public abstract class RecursiveAction extends ForkJoinTask<Void> {
    protected abstract void compute();
}
~~~

Đây là **chữ ký khái niệm rút gọn**; không phải nguyên mã source của JDK, vì JDK còn triển khai `getRawResult`, `setRawResult`, `exec` và các thành phần khác.

### 3.1. `RecursiveTask<V>`

Ví dụ nhiệm vụ trả về kiểu `Long`:

~~~java
final class SumTask extends RecursiveTask<Long> {
    private static final long serialVersionUID = 1L;
    private final long[] numbers;
    // ... phạm vi from/to và constructor ...

    @Override
    protected Long compute() {
        // Base case: tính tổng và return Long.
        // Recursive case: fork subtask và join lấy kết quả.
        return 0L;
    }
}
~~~

Đây là **minh họa chưa độc lập**: các fields và logic tính tổng còn được giải thích sau. `Long` là **wrapper type** vì generics `V` không nhận kiểu nguyên thủy `long`. Tại Java source, `protected Long compute()` trả đối tượng Long (auto-boxing nếu return biểu thức long), còn `join()` nhận `Long` rồi có thể unbox khi cần.

Nhiệm vụ có thể trả kiểu khác như `Integer`, `BigInteger`, `Map`, record kết quả thống kê hoặc cấu trúc cây. Nhưng bài toán phải định nghĩa phép **ghép kết quả các nhánh** (ví dụ cộng tổng, chọn max, hợp nhất bảng đếm), không chỉ “chạy song song”.

### 3.2. `RecursiveAction`

Ví dụ nhiệm vụ sửa dữ liệu:

~~~java
final class DoubleAction extends RecursiveAction {
    private static final long serialVersionUID = 1L;
    private final long[] numbers;
    // ... from/to và constructor ...

    @Override
    protected void compute() {
        // Base case: sửa các phần tử numbers[i] trong khoảng sở hữu.
        // Recursive case: invokeAll hai hành động con.
    }
}
~~~

Đây là **minh họa chưa độc lập**; chương trình đầy đủ ở phần sau có code thực.

**Lưu ý không phải `RecursiveAction<Boolean>`:** `RecursiveAction` **không có generic parameter V** và luôn là `ForkJoinTask<Void>`. Nếu muốn báo một boolean kết quả, nên dùng `RecursiveTask<Boolean>` hoặc một đối tượng kết quả phù hợp, không đặt field mutable rồi coi đó là return value từ action.

### 3.3. Bảng so sánh nhanh

| Khía cạnh | `RecursiveTask<V>` | `RecursiveAction` |
| --- | --- | --- |
| Lớp cha | `ForkJoinTask<V>` | `ForkJoinTask<Void>` |
| Hàm cần override | `protected V compute()` | `protected void compute()` |
| Kết quả của `join()` | `V` | `null` (kiểu `Void`) |
| Kết quả của `pool.invoke(...)` | `V` | `null` |
| Hành vi mong muốn | Tính/gộp và trả giá trị | Thực thi công việc, thường sửa vùng dữ liệu độc lập |
| Khi chia nhỏ | Kết hợp `left.join()` + `right.compute()` | `invokeAll(left, right)` rồi không return value |
| Tính an toàn | Cần dữ liệu đầu vào/đầu ra an toàn, kết hợp đúng | Cần side effects không chồng lấp hoặc synchronization phù hợp |
| Cách biết hoàn tất | `join()`/`invoke()`/`get()` | Cũng có các phương thức đó; chỉ **không có result có ý nghĩa** |
| Ngoại lệ | Task failure chuyển lên join/invoke hoặc Future.get | Tương tự; `void` không có nghĩa “không thể fail” |
| Ví dụ | Sum, count, min/max, histogram | In-place transform, tách vùng ảnh, dựng dữ liệu vào mảng |

Một `RecursiveTask` vẫn **có thể gây side effect**, và một `RecursiveAction` vẫn **có thể ghi kết quả vào một object**. Sự phân loại ở đây dựa trên *giao diện kết quả mà task hứa với caller*, không phải một luật cứng về purity của mọi chương trình.

## 4. Fork/Join hoạt động thế nào?

### 4.1. Work-stealing không tạo một thread cho mỗi task

`ForkJoinPool` có các worker threads. Khi một task chia thành nhiều subtasks, các subtasks thường được đặt vào deque/queue của pool. Worker rảnh có thể **đánh cắp task** từ worker khác để cân bằng tải. Ý tưởng chính là tận dụng nhiều lõi CPU cho công việc **CPU-bound, độc lập và có thể chia nhỏ**.

~~~text
Worker 1: Sum[0,8) -> fork Sum[0,4), compute Sum[4,8)
                  |
Worker 2: steal Sum[0,4) -> tiếp tục chia và xử lý
                  |
Worker 3/4: có thể giúp thực thi những task có thể đánh cắp
                  |
Các task join kết quả của children và ghép thành tổng
~~~

Sơ đồ không dự đoán chính xác worker nào sẽ chạy một task. **Số worker thực tế, thứ tự scheduling và việc có work-steal hay không phụ thuộc runtime và workload**. Chạy pool parallelism 4 không đồng nghĩa mọi lúc đều có bốn task chạy song song, càng không bảo đảm nhanh hơn sequential.

### 4.2. `fork()`

Trong `compute()`:

~~~java
left.fork();
~~~

Lệnh này **sắp lịch một task** để có thể được thực thi bất đồng bộ bởi pool; nó **không đợi** task đó hoàn tất và không trả về kết quả tính toán của task. Giá trị trả về là chính đối tượng `ForkJoinTask` để có thể chain nếu muốn.

### 4.3. `join()`

~~~java
long leftSum = left.join();
~~~

`join()` chờ task hoàn tất và lấy kết quả `V`. Nó có semantics của fork/join, có thể hỗ trợ worker xử lý task khác trong khi đợi. Nếu computation ném unchecked exception, `join()` có thể ném tiếp exception đó. Không coi `join()` luôn thành công.

### 4.4. `invokeAll(...)`

~~~java
invokeAll(
        new DoubleAction(values, from, mid),
        new DoubleAction(values, mid, to));
~~~

Đây là đoạn minh họa trong `RecursiveAction.compute()`. `invokeAll` **fork và chờ** các subtasks theo contract; khi trở về bình thường, chúng đều hoàn tất. Với action, không có danh sách return values phải ghép, nên cách này rõ ý. Nếu có lỗi trong một child, propagation/cancellation của các subtasks khác theo contract cần được hiểu; đừng coi đây là transaction rollback.

### 4.5. Quy tắc fork một nhánh, tính một nhánh

Với `RecursiveTask`, pattern thường hiệu quả hơn fork cả hai rồi chờ sớm:

~~~java
left.fork();
long rightSum = right.compute();
long leftSum = left.join();
return Math.addExact(leftSum, rightSum);
~~~

Ở đây:

1. `left.fork()` đưa nhánh trái vào pool, cho worker khác cơ hội xử lý.
2. Thread hiện tại **tính trực tiếp nhánh phải**, không đứng đợi ngay.
3. `left.join()` lấy kết quả nhánh trái khi cần.
4. `Math.addExact(...)` ghép kết quả và phát hiện overflow của `long` trong ví dụ.

Không gọi `left.fork(); left.join(); right.compute()` một cách máy móc vì chờ nhánh trái ngay có thể hạn chế concurrency. Pattern tốt thường **fork một nhánh → compute nhánh còn lại → join nhánh đã fork**. Với nhiều subtasks, join innermost-first hoặc theo hướng tương ứng lịch thực thi.

### 4.6. `invoke(...)` và `submit(...)` khác nhau

Từ thread bên ngoài một computation Fork/Join:

~~~java
long total = pool.invoke(new SumTask(values, 0, values.length));
~~~

`pool.invoke(task)` thực hiện task và **chờ trả kết quả** cho caller. Nếu task lỗi unchecked, lỗi được ném lên caller. Đây là cách đơn giản để chạy bài toán có một root task.

~~~java
ForkJoinTask<Void> submitted = pool.submit(
        new DoubleAction(values, 0, values.length));
// Có thể làm việc khác độc lập khi task đang xử lý.
Void result = submitted.join();
~~~

`pool.submit(...)` trả task/future để caller chờ sau; `result == null` với `RecursiveAction` hoàn tất bình thường. Vì `ForkJoinTask` implements `Future<V>`, cũng có thể dùng `get()`/`get(timeout,unit)` với kiểu checked-exception conventions của `Future`.

### 4.7. Đừng gọi `compute()` của root task từ bên ngoài nếu mục đích là điều phối bằng pool

~~~java
// Không phải cách khởi động root task bằng custom pool:
new SumTask(values, 0, values.length).compute();
~~~

Đây là **phản ví dụ về ý định sử dụng**. Nó chỉ gọi method như một lời gọi Java thông thường. Nếu code bên trong `compute()` fork children, việc chọn pool có thể khác kỳ vọng khi gọi ngoài worker context (có thể dùng common pool). Muốn rõ ownership và parallelism, gọi `pool.invoke(rootTask)` hoặc `pool.submit(rootTask)`.

## 5. Base case và ngưỡng chia task `THRESHOLD`

Nếu mỗi task cứ chia mãi mà không có điểm dừng, recursion có thể vô hạn, tạo vô số objects hoặc tràn stack. **Base case** là điều kiện chọn xử lý tuần tự thay vì chia tiếp, thường dựa trên kích thước đoạn.

~~~java
if (to - from <= THRESHOLD) {
    long sum = 0;
    for (int i = from; i < to; i++) {
        sum = Math.addExact(sum, values[i]);
    }
    return sum;
}
~~~

Đây là **đoạn từ mẫu tính tổng**; nó giả định `values` và các boundaries đã được validation. Khoảng `[from, to)` là **start inclusive, end exclusive**:

- `from=0, to=3` gồm các index 0, 1, 2.
- `from=3, to=8` gồm 3, 4, 5, 6, 7.
- Hai khoảng con `[from, mid)` và `[mid, to)` không chồng lấp, không bỏ sót phần tử.
- Khi `from==to`, đoạn trống; tổng bằng 0, action không thực hiện gì.
- Khi đoạn chỉ dài 1, base case phải đảm bảo không chia thành các khoảng cùng kích thước gây lặp vô hạn.

Tính midpoint an toàn:

~~~java
int middle = from + (to - from) / 2;
~~~

Với boundaries hợp lệ và `from <= to`, biểu thức này tránh overflow kiểu cộng trực tiếp `(from + to) / 2`. Trên mảng Java thực, các index phải nằm trong `[0, values.length]`.

### 5.1. Ngưỡng lớn hay nhỏ?

**Không có một `THRESHOLD` tối ưu chung cho mọi workload.** Khi quá nhỏ, số subtasks và chi phí scheduling/join có thể lớn hơn lợi ích song song. Khi quá lớn, số leaves ít hơn số worker, CPU khó được tận dụng và load có thể lệch.

Ví dụ trong chương trình chạy, `THRESHOLD=2` chỉ giúp **quan sát recursion trên mảng có 8 phần tử**, không phải cấu hình production. Với dữ liệu lớn, cần benchmark threshold trên workload và hardware thực:

- Tính toán đơn giản mỗi phần tử (cộng số) thường cần chunk lớn.
- Phép tính CPU đắt tiền mỗi phần tử có thể chia nhỏ hơn.
- Dữ liệu không cân bằng cần cân nhắc chia theo chi phí thay vì chỉ theo số phần tử.
- Kích thước cache, allocation, contention và parallelism ảnh hưởng throughput.
- Từ tài liệu `ForkJoinTask`, task quá nhỏ hoặc quá lớn đều có thể kém hiệu quả; các con số chỉ là hướng dẫn thô, không phải invariant API.

### 5.2. Vì sao dùng `Math.addExact` / `Math.multiplyExact`?

Dù `long` rộng hơn `int`, nó vẫn có thể overflow nếu tổng quá lớn. `Math.addExact` và `Math.multiplyExact` làm rõ policy: **ném `ArithmeticException` khi tràn** thay vì âm thầm wrap-around. Điều này giúp bài học không dạy kết quả số học sai khi vượt phạm vi.

Tuy nhiên, trong `RecursiveAction`, nếu có overflow ở một leaf sau khi nhiều leaves khác đã sửa mảng, action **không tự rollback phần đã sửa**. Nếu nghiệp vụ cần all-or-nothing, phải thiết kế kết quả immutable hoặc buffer staging/transaction riêng. Mảng ví dụ 1..8 nhân 2 không overflow nên đầu ra quyết định.

## 6. Chương trình Java 21 hoàn chỉnh: một RecursiveTask, một RecursiveAction

Chương trình dưới đây cho thấy hai mô hình trên **cùng một dữ liệu**:

1. Tạo `numbers` gồm 1 đến 8; giữ nguyên để sum task chỉ đọc.
2. `SumTask extends RecursiveTask<Long>` tính tổng của `numbers` và trả 36.
3. Tạo bản sao `changed = numbers.clone()` để action không sửa đầu vào ban đầu.
4. `DoubleAction extends RecursiveAction` chia theo đoạn không chồng lấp và **nhân đôi tại chỗ** các phần tử trong `changed`.
5. `ForkJoinTask<Void> action = pool.submit(...)` và `action.join()` trả `null`; sau join, mảng có giá trị đã biến đổi.
6. `SumTask` tính lại tổng của mảng mới thành 72.
7. Thử cả hai kiểu với mảng rỗng; base case hoạt động, không chia vô hạn.
8. Đóng `ForkJoinPool` riêng bằng `shutdown`/`awaitTermination` và xác nhận đã terminated.

Tạo tệp `src/main/java/demo/TaskVsActionExample.java`:

~~~java
package demo;

import java.util.Arrays;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.ForkJoinTask;
import java.util.concurrent.RecursiveAction;
import java.util.concurrent.RecursiveTask;
import java.util.concurrent.TimeUnit;

public final class TaskVsActionExample {
    private static final int THRESHOLD = 2;

    private TaskVsActionExample() {}

    private static final class SumTask extends RecursiveTask<Long> {
        private static final long serialVersionUID = 1L;

        private final long[] values;
        private final int from;
        private final int to;

        SumTask(long[] values, int from, int to) {
            this.values = values;
            this.from = from;
            this.to = to;
        }

        @Override
        protected Long compute() {
            if (to - from <= THRESHOLD) {
                long sum = 0;
                for (int i = from; i < to; i++) {
                    sum = Math.addExact(sum, values[i]);
                }
                return sum;
            }

            int middle = from + (to - from) / 2;
            SumTask left = new SumTask(values, from, middle);
            SumTask right = new SumTask(values, middle, to);
            left.fork();
            long rightSum = right.compute();
            long leftSum = left.join();
            return Math.addExact(leftSum, rightSum);
        }
    }

    private static final class DoubleAction extends RecursiveAction {
        private static final long serialVersionUID = 1L;

        private final long[] values;
        private final int from;
        private final int to;

        DoubleAction(long[] values, int from, int to) {
            this.values = values;
            this.from = from;
            this.to = to;
        }

        @Override
        protected void compute() {
            if (to - from <= THRESHOLD) {
                for (int i = from; i < to; i++) {
                    values[i] = Math.multiplyExact(values[i], 2L);
                }
                return;
            }

            int middle = from + (to - from) / 2;
            invokeAll(
                    new DoubleAction(values, from, middle),
                    new DoubleAction(values, middle, to));
        }
    }

    public static void main(String[] args) throws InterruptedException {
        long[] numbers = {1, 2, 3, 4, 5, 6, 7, 8};
        long[] changed = numbers.clone();

        ForkJoinPool pool = new ForkJoinPool(4);
        try {
            long originalSum = pool.invoke(
                    new SumTask(numbers, 0, numbers.length));
            System.out.println("original-sum=" + originalSum);
            System.out.println("original=" + Arrays.toString(numbers));

            ForkJoinTask<Void> action = pool.submit(
                    new DoubleAction(changed, 0, changed.length));
            Void actionResult = action.join();
            System.out.println("action-result=" + actionResult);
            System.out.println("changed=" + Arrays.toString(changed));

            long changedSum = pool.invoke(
                    new SumTask(changed, 0, changed.length));
            System.out.println("changed-sum=" + changedSum);

            long[] empty = {};
            System.out.println("empty-sum=" + pool.invoke(
                    new SumTask(empty, 0, empty.length)));
            pool.invoke(new DoubleAction(empty, 0, empty.length));
            System.out.println("empty-action=" + Arrays.toString(empty));
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Pool did not terminate");
            }
        }
        System.out.println("pool-terminated=" + pool.isTerminated());
    }
}
~~~

Chạy từ thư mục chứa `src/` với **JDK 21**:

~~~sh
javac --release 21 -encoding UTF-8 -Xlint:all -d out src/main/java/demo/TaskVsActionExample.java
java -cp out demo.TaskVsActionExample
~~~

**Stdout chính xác đã được kiểm thử:**

~~~text
original-sum=36
original=[1, 2, 3, 4, 5, 6, 7, 8]
action-result=null
changed=[2, 4, 6, 8, 10, 12, 14, 16]
changed-sum=72
empty-sum=0
empty-action=[]
pool-terminated=true
~~~

### 6.1. Giải thích từng dòng

| Dòng | Diễn giải |
| --- | --- |
| `original-sum=36` | `SumTask.compute()` trả kết quả tổng các số 1..8 |
| `original=[1,...,8]` | `RecursiveTask` chỉ đọc; mảng đầu vào không bị sửa |
| `action-result=null` | `DoubleAction` là `ForkJoinTask<Void>`, `join()` trả `null` khi thành công |
| `changed=[2,4,...,16]` | Side effect có chủ đích của `RecursiveAction` xuất hiện trên bản sao |
| `changed-sum=72` | `SumTask` mới tính tổng bản sao đã nhân đôi |
| `empty-sum=0` | Đoạn trống đi qua base case; tổng theo phép cộng có giá trị đơn vị 0 |
| `empty-action=[]` | Action với đoạn trống không thao tác, không gây lỗi |
| `pool-terminated=true` | Pool riêng đã shutdown và kết thúc sau khi tất cả root tasks hoàn thành |

Output không in thread name, thời gian hoặc thứ tự các leaves, vì đó là chi tiết scheduling **không được bảo đảm**. Đầu ra ổn định do bài toán thuần về số học và quyền sở hữu vùng mảng tách biệt.

### 6.2. Vì sao `SumTask` dùng `Long`?

`RecursiveTask<V>` là generic class; Java generic type arguments không dùng primitive `long`, nên phải chọn `RecursiveTask<Long>`. Trong `compute()`, có thể dùng biến `long` cho tính toán và để Java boxing khi trả về. `join()` trả `Long`, có thể unbox vào `long` trong phép cộng.

Nếu số liệu vượt xa phạm vi 64-bit, chọn `BigInteger` và phép cộng tương ứng, nhưng nhớ object allocation/chi phí combine. Không dùng `int` chỉ vì ví dụ nhỏ; hãy chọn kiểu số theo nghiệp vụ.

### 6.3. Vì sao `DoubleAction` dùng `invokeAll`?

Hành động chỉ cần **cả hai child hoàn tất**; không cần lấy kết quả để cộng. `invokeAll(leftAction, rightAction)` nói rõ dependency: parent chỉ hoàn tất sau children (khi không lỗi). Các children có khoảng `[from, middle)` và `[middle, to)` không chồng lấp, nên không cần synchronize writes trên từng element.

### 6.4. Vì sao đọc mảng sau `join()` là hợp lý?

`action.join()` chờ action hoàn tất bình thường, trong đó `invokeAll` đã đợi các actions con. Với tác vụ hợp lệ, những writes vào mảng do children thực hiện **được phối hợp qua completion/join**, nên caller đọc `changed` sau join. Không đọc `changed` từ thread khác **khi action còn đang sửa** mà không có synchronization thích hợp.

### 6.5. Vì sao dùng `serialVersionUID`?

`ForkJoinTask` triển khai `Serializable`, nên khi bật `javac -Xlint:all`, các lớp con có thể cảnh báo vì thiếu `serialVersionUID`. Ví dụ khai báo `private static final long serialVersionUID = 1L;` để **biên dịch không cảnh báo**. Đây không phải lời khuyên serialize một task đang chạy để truyền giữa máy hoặc lưu trạng thái execution — Fork/Join không tự là cơ chế distributed computation.

### 6.6. Vì sao shutdown pool trong finally?

`ForkJoinPool pool = new ForkJoinPool(4)` tạo pool **riêng** cho chương trình. Sau khi hoàn tất các tasks, `pool.shutdown()` từ chối submissions mới và cho các tasks đã nhận hoàn tất. `awaitTermination(5, TimeUnit.SECONDS)` kiểm tra đã dừng trước deadline test hay chưa.

Nếu chương trình ném lỗi trước đoạn cuối, `finally` vẫn thực hiện cleanup. `awaitTermination` có thể ném `InterruptedException`, nên `main` khai báo `throws InterruptedException`. Trong production, nếu timeout cần cảnh báo/hủy/điều phối phù hợp, không coi timeout là termination. **Không tự shutdown `ForkJoinPool.commonPool()`**; nó là pool dùng chung của JVM và `shutdown()` không thay đổi run state của common pool.

## 7. Khi nào dùng `RecursiveTask` và khi nào dùng `RecursiveAction`?

### 7.1. Chọn `RecursiveTask<V>` khi kết quả là phần quan trọng của hợp đồng

Ví dụ:

- Tổng `long` trên mảng, kết quả `Long`.
- Tìm min/max: `RecursiveTask<OptionalLong>` hoặc kết quả có trạng thái rỗng rõ.
- Đếm số mục hợp lệ: `RecursiveTask<Long>`.
- Tính nhiều thống kê: `RecursiveTask<Stats>`, trong đó `Stats` là record giữ count/sum/min/max và có hàm merge.
- Duyệt cây và trả tập kết quả (nếu memory/merge cost được thiết kế).
- Đếm số lần xuất hiện của token trong các phân đoạn, sau đó ghép các map kết quả.

Với các kết quả này, nên tránh mutable global accumulator mà mọi task cùng cập nhật nếu có thể. Cho mỗi subtask trả **kết quả riêng**, rồi merge ở parent. Mô hình giảm mutable shared state thường dễ kiểm tra hơn.

### 7.2. Chọn `RecursiveAction` khi hành động là kết quả thực sự

Ví dụ:

- Áp dụng biến đổi pixel trên các dải ảnh không chồng lấp.
- Chuẩn hóa/ghi dữ liệu vào mảng đã phân đoạn theo index.
- Điền một bảng/ma trận đã phân hoạch rõ quyền sở hữu.
- Chuyển đổi in-place một tập dữ liệu mà không cần trả giá trị aggregate.
- Viết nhiều phần độc lập vào buffer có phân vùng an toàn.

Chọn action phải có **quy tắc side effects**. “Không có return value” không chứng minh race-free. Nếu các tasks cùng `list.add(...)` vào một `ArrayList`, chúng vẫn có thể gây race và corrupt state. Nên dùng vùng kết quả độc lập rồi ghép sau, hoặc cấu trúc concurrent/synchronization phù hợp.

### 7.3. Không chọn chỉ dựa trên return type của một helper nội bộ

Có thể một thuật toán tạo ra side effects *và* cần một kết quả. Khi đó cân nhắc:

- Trả về một đối tượng kết quả `RecursiveTask<Result>` bao gồm dữ liệu và metadata.
- Chia nhiệm vụ rõ ràng thành giai đoạn compute/result và giai đoạn apply/action.
- Nếu action in-place, có commit/rollback policy rõ khi một child thất bại.
- Tránh thiết kế `RecursiveAction` rồi ép side effect vào biến `static` để “lấy lại kết quả”.

**Nguyên tắc:** Type choice nên làm rõ hợp đồng: caller cần gì sau khi `join()` thành công?

## 8. `join()`, `get()` và xử lý lỗi

### 8.1. `join()` của `ForkJoinTask`

`RecursiveTask` và `RecursiveAction` đều kế thừa `ForkJoinTask`, nên có `join()`:

~~~java
long result = sumTask.join(); // Long nếu SumTask extends RecursiveTask<Long>.
Void nothing = action.join(); // null nếu action hoàn tất bình thường.
~~~

Đây là đoạn minh họa khi `sumTask` và `action` đã được lập lịch/đang chạy một cách hợp lệ. `join` chờ task hoàn tất và có thể **ném unchecked exception** nếu task lỗi, không buộc caller catch `ExecutionException` như `Future.get()`.

### 8.2. `get()` theo conventions của `Future`

`ForkJoinTask<V>` implements `Future<V>`. Khi muốn timeout hoặc interruptible wait:

~~~java
try {
    Long total = sumTask.get(5, TimeUnit.SECONDS);
    System.out.println(total);
} catch (TimeoutException ex) {
    // Chưa có kết quả trước deadline; task có thể vẫn chạy.
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
} catch (ExecutionException ex) {
    // getCause() chứa lỗi do task gây ra.
}
~~~

Đây là **đoạn minh họa** (cần imports/cấu trúc xử lý ngoại lệ đầy đủ). `get()`/`get(timeout,unit)` dùng checked exceptions; `join()` sử dụng unchecked/propagated exception style của ForkJoinTask. Không đồng nhất `ForkJoinTask.join()` với `Thread.join()`: cả hai tên giống nhau nhưng có contract khác.

### 8.3. Nếu một nhánh lỗi thì sao?

Giả sử `SumTask` gọi `Math.addExact` với tổng vượt giới hạn long: leaf hoặc combine có thể ném `ArithmeticException`. Nếu bạn dùng `pool.invoke(root)`, lỗi unchecked sẽ được truyền lên caller. Với `DoubleAction`, một `Math.multiplyExact` có thể lỗi giữa lúc một số vùng đã sửa.

**Không có transaction tự động** giữa các subtasks:

- Kết quả sum task thất bại thì không có tổng hợp lệ để dùng.
- In-place action có thể đã sửa một phần mảng trước khi lỗi.
- `invokeAll`/`join` không rollback writes và không khôi phục object về trạng thái cũ.
- Cancellation là request về trạng thái task, không phải đảm bảo mọi task đang tính sẽ ngừng ngay và hoàn nguyên side effects.
- Nếu cần all-or-nothing, hãy biến đổi trên bản sao/staging buffers, xác minh sau join thành công rồi mới publish result.

### 8.4. `isDone()` không chứng minh task thành công

Có các phương thức `isDone()`, `isCompletedNormally()`, `isCompletedAbnormally()`, `isCancelled()` và `getException()`. `isDone()` có thể true khi task thành công, lỗi hoặc bị hủy. `getException()` hữu ích khi đã biết task hoàn tất bất thường, nhưng không thay thế xử lý chính qua `join()`/`invoke()`/`get()`.

### 8.5. Checked exceptions trong `compute()`

`compute()` không khai báo `throws IOException` hay checked exceptions tùy ý. Task chủ yếu dành cho tính toán; nếu bạn cần làm I/O có checked exceptions, phải định nghĩa cách chuyển/báo lỗi. Nhưng đừng coi việc bọc mọi `IOException` vào `RuntimeException` là đủ lý do để biến blocking I/O thành một tác vụ Fork/Join phù hợp về mặt hiệu năng. Với workload I/O-heavy, chọn executor phù hợp hơn; Java hiện đại còn có virtual threads cho nhiều tình huống blocking I/O (Java 21+), tùy kiến trúc.

## 9. Những sai lầm lập lịch phổ biến

### 9.1. Fork cả hai rồi join ngay một nhánh

~~~java
left.fork();
right.fork();
long leftSum = left.join();
long rightSum = right.join();
~~~

Đây là **minh họa hợp lệ về correctness**, nhưng thường có thêm overhead trong khi thread hiện tại có thể tính trực tiếp một nhánh. Cân nhắc:

~~~java
left.fork();
long rightSum = right.compute();
long leftSum = left.join();
~~~

Pattern thứ hai thường khai thác tốt work-stealing cho thuật toán chia đôi; không phải theorem rằng nhanh nhất ở mọi workload, vẫn cần đo.

### 9.2. Join trước khi tạo cơ hội song song

~~~java
left.fork();
long a = left.join();
long b = right.compute();
~~~

Đây là **phản ví dụ về hiệu năng**: có thể chờ nhánh trái trước khi làm nhánh phải, giảm độ song song hữu ích. Thường hãy compute nhánh phải trong khi nhánh trái chạy/đang ở queue.

### 9.3. Không có base case

~~~java
@Override
protected Long compute() {
    int mid = from + (to - from) / 2;
    return new SumTask(values, from, mid).invoke()
         + new SumTask(values, mid, to).invoke();
}
~~~

Đây là **phản ví dụ**; với đoạn 0/1 phần tử, một nhánh có thể lặp kích thước cũ dẫn tới recursion không kết thúc. Ngoài ra, gọi `invoke()` tuần tự theo cách này làm giảm lợi ích chia task. Phải có `if (to-from <= threshold)` và ghép đúng child ranges.

### 9.4. Hai actions ghi cùng index

~~~java
invokeAll(
        new DoubleAction(values, 0, 6),
        new DoubleAction(values, 4, 8));
~~~

Đây là **phản ví dụ**: index 4 và 5 thuộc cả hai children, có thể bị nhân đôi **hai lần** hoặc xảy ra race. Phải dùng hai đoạn không chồng lấp như `[0,4)` và `[4,8)`.

### 9.5. Biến tổng cộng dồn global trong nhiều tasks

~~~java
static long total;
// Nhiều tasks đồng thời:
total += value;
~~~

Đây là **phản ví dụ**. `+=` gồm đọc, tính, ghi; nhiều workers có thể mất cập nhật. Thay vì dùng lock/atomic cho từng phần tử, thường tốt hơn để `RecursiveTask<Long>` trả tổng cục bộ và ghép khi join. Nếu thực sự cần shared aggregation, dùng thiết kế concurrent phù hợp và đo contention.

### 9.6. Blocking I/O trong compute

Một `ForkJoinPool` tối ưu cho nhiều tasks tính toán chia nhỏ. Nếu mỗi `compute()` lại đọc HTTP/database đồng bộ lâu, các worker bị giữ, pool có thể thiếu threads cho những tasks đang chờ. `ForkJoinPool.ManagedBlocker` hỗ trợ một số kiểu chặn được thông báo trước, nhưng không biến mọi blocking I/O thành giải pháp tối ưu; với I/O phổ biến, cân nhắc executor chuyên dụng hoặc virtual threads Java 21+.

### 9.7. Dùng commonPool như pool riêng có thể đóng

~~~java
ForkJoinPool pool = ForkJoinPool.commonPool();
pool.shutdown(); // Với common pool, shutdown không ảnh hưởng run state.
~~~

Đây là **đoạn cảnh báo**, không nên dùng như cách dừng công việc chung. Common pool được chia sẻ bởi JVM/các thành phần, nên không tự điều chỉnh/dừng nó như một pool thuộc service riêng. Muốn kiểm soát lifecycle và parallelism, tạo `new ForkJoinPool(parallelism)` và cleanup đúng.

### 9.8. Chia quá nhỏ chỉ để “chạy nhiều task”

Với vài phần tử và phép cộng rất rẻ, overhead Fork/Join có thể lớn hơn vòng lặp `for`. Không đo `parallelism=4` rồi tự khẳng định “nhanh gấp bốn”. Benchmark với input lớn hơn, warm-up JIT, workload thật, đo memory/GC/CPU; nếu cần benchmark nghiêm túc, dùng công cụ như JMH và đọc kết quả theo điều kiện thiết bị.

## 10. Tính độc lập, thread safety và visibility

### 10.1. Mảng chỉ đọc trong RecursiveTask

Trong ví dụ, `numbers` không bị sửa trong thời gian `SumTask` đang chạy. Mỗi leaf chỉ đọc vùng `[from,to)` và tính tổng local. Parent lấy kết quả riêng của children qua join. Điều này tránh race vì không có shared mutable accumulator.

Nếu thread ngoài sửa `numbers` **trong lúc** SumTask đọc, kết quả có thể không nhất quán. `final long[] values` chỉ làm reference final, **không khiến nội dung mảng bất biến**. Để bảo đảm snapshot, có thể clone input, dùng immutable representation hoặc synchronize theo yêu cầu.

### 10.2. Mảng ghi trong RecursiveAction

`DoubleAction` dùng cùng reference `changed` nhưng **không cùng index**. Nếu đảm bảo toàn bộ intervals phân hoạch đúng, các leaves không tranh nhau ghi một phần tử. Parent chờ `invokeAll`, root được caller `join`; sau đó caller đọc mảng đã hoàn tất.

Nếu một thread khác đọc `changed` trong lúc action đang chạy, nó có thể thấy mảng được nhân đôi **một phần**, vì task không tạo transaction/snapshot atomic. Không publish một mảng đang mutate cho các consumers khác mà thiếu coordination.

### 10.3. Mutable attachments và task fields

Trường `final from,to,values` giúp một task không bị đổi phạm vi khi đang chạy. Nhưng object chứa `values` vẫn mutable. Nếu tasks cùng tham chiếu một `List` hoặc `Map` mutable, cần xem xét writes, keys, thread safety và cách publish kết quả.

Một mô hình thường hữu ích là **mỗi task chỉ sở hữu một dải chỉ số**, còn kết quả aggregate được trả về `RecursiveTask<Result>`. Hạn chế synchronized global locks trong phần hot loop.

### 10.4. Đừng tạo quan hệ join vòng tròn

`ForkJoinTask` phù hợp các dependencies không có chu kỳ. Nếu task A chờ B và B lại chờ A, có thể không tiến triển. Thiết kế cây fork/join thông thường là DAG: parent sinh children, children tính xong, parent join; không để child join parent.

## 11. `ForkJoinPool` lifecycle và lựa chọn pool

Một chương trình có thể dùng:

~~~java
ForkJoinPool pool = new ForkJoinPool(4);
try {
    long total = pool.invoke(new SumTask(values, 0, values.length));
    // Dùng total sau khi invoke xong.
} finally {
    pool.shutdown();
    pool.awaitTermination(5, TimeUnit.SECONDS);
}
~~~

Đây là **đoạn minh họa**, cần biến `values`, imports và xử lý `InterruptedException`/timeout. Khi tạo pool riêng, bạn chịu trách nhiệm dừng. Nếu ứng dụng dùng pool chung do một framework sở hữu, không tự shutdown từ helper.

### 11.1. Parallelism không phải số task chạy đồng thời tuyệt đối

`new ForkJoinPool(4)` đặt **mức song song mục tiêu** cho pool, không phải cam kết có đúng bốn threads luôn running. Có thể có scheduling overhead, CPU throttling, tranh chấp tài nguyên hoặc blocking khiến số worker runnable khác mức đó. `Runtime.getRuntime().availableProcessors()` thường là một điểm bắt đầu để xét CPU-bound workload; vẫn cần benchmark.

### 11.2. `ForkJoinPool.commonPool()`

`commonPool()` hữu ích trong nhiều ứng dụng nếu không cần sở hữu lifecycle, nhưng nó được chia sẻ. Một job lớn, chặn lâu hoặc tạo quá nhiều tasks có thể ảnh hưởng code khác trong JVM cũng dùng common pool. Không thay đổi global parallelism property trong thư viện chỉ để tối ưu một thuật toán riêng.

### 11.3. `shutdown()`, `shutdownNow()`, `awaitTermination()`

- `shutdown()`: orderly shutdown, nhận đã submit thì tiếp tục hoàn tất; không nhận submissions mới.
- `shutdownNow()`: cố gắng hủy/dừng các tasks để kết thúc, không phải rollback side effects; ForkJoinPool theo contract có thể trả list rỗng dù task vẫn bị hủy.
- `awaitTermination(timeout,unit)`: chờ trong một thời hạn, **trả false nếu chưa terminated**, không thể thay bằng `isShutdown()`.
- `close()` trên `ForkJoinPool` được hỗ trợ từ các JDK hiện đại (Java 19+), nhưng code trong bài dùng explicit shutdown để vẫn áp dụng thuận tiện trên Java 17.
- Với `commonPool`, `shutdown()` và `shutdownNow()` không thay đổi run state theo Javadoc; không có ownership để dừng kiểu pool riêng.

### 11.4. Xử lý interruption trong cleanup

Nếu thread đợi `awaitTermination` bị interrupt, phải propagate hoặc restore interrupt tùy tầng. Ví dụ `main throws InterruptedException` để tập trung kiến thức chính; service production thường thực hiện bounded cleanup rồi báo trạng thái thực. Không im lặng bắt interruption rồi tiếp tục chờ vô hạn.

## 12. Khi dùng parallel streams, structured concurrency hoặc virtual threads?

Fork/Join vẫn hữu ích nhưng **không phải lựa chọn duy nhất** cho song song hóa trên JDK hiện nay.

| Công cụ | Trọng tâm | Khi phù hợp |
| --- | --- | --- |
| `RecursiveTask<V>` | Divide-and-conquer, trả result | Tính toán song song có reducer/merge |
| `RecursiveAction` | Divide-and-conquer, action | In-place độc lập theo vùng dữ liệu |
| `ForkJoinPool` | Work-stealing executor | Nhiều tác vụ CPU-bound có chia con |
| `Arrays.parallelSort` | Sắp xếp mảng song song đã có API | Không cần tự viết recursive sort khi API phù hợp |
| `Stream.parallel()` | Data parallelism biểu đạt bằng pipeline | Dữ liệu/operations phù hợp, kiểm tra side effects và thứ tự |
| `ExecutorService` thông thường | Nhiệm vụ độc lập, lifecycle | Workloads không cần fork/join recursion |
| Virtual threads (Java 21+) | Nhiều blocking tasks, đặc biệt I/O | Không phải thay thế trực tiếp work-stealing CPU-bound |
| `CompletableFuture` | Phối hợp các kết quả bất đồng bộ | Dependency chains hoặc services, cần chọn executor rõ |
| Structured concurrency | Quản lý lifetime của subtasks theo scope | Tính khả dụng/API phụ thuộc phiên bản JDK; không coi preview API là lựa chọn mặc định |

Đối với việc nhân đôi một mảng nhỏ, vòng lặp đơn giản thường dễ hiểu và đủ nhanh. Đối với một mảng lớn và CPU-heavy computation, RecursiveTask/Action có thể đáng dùng nếu bạn kiểm soát được overhead, memory và hiệu năng. Khi có API chuẩn trực tiếp giải quyết bài toán, ưu tiên thư viện chuẩn thay vì tự xây một scheduler phức tạp.

## 13. Test cases cần có trước khi dùng thật

Để chứng minh tính đúng của thuật toán thay vì chỉ “có kết quả nhanh”:

1. **Mảng rỗng:** SumTask trả 0, DoubleAction không làm gì.
2. **Một phần tử:** không chia recursion vô hạn.
3. **Hai phần tử:** base case theo threshold.
4. **Kích thước lẻ:** `middle` và khoảng `[from,to)` không bỏ sót/nhân đôi index.
5. **Số âm:** SumTask trả tổng đúng, DoubleAction nhân 2 đúng nếu không overflow.
6. **Giá trị 0:** không gây trường hợp chia sai.
7. **Nhiều giá trị lớn:** xác định policy overflow; `Math.addExact`/`multiplyExact` ném `ArithmeticException` khi cần.
8. **Cùng input, nhiều lần chạy:** kết quả tổng phải như nhau; output array phải giống nhau sau khi chờ completion.
9. **Không mutation ngoài ý muốn:** SumTask không sửa input; DoubleAction chỉ sửa bản sao/đầu ra cho phép.
10. **Không overlap:** hai action children có intervals disjoint.
11. **Threshold khác nhau:** 1, 2, vài nghìn; kết quả đúng không phụ thuộc threshold hợp lệ.
12. **Parallelism khác nhau:** pool 1, 2, 4, CPU cores; correctness không đổi.
13. **Exception path:** nếu action lỗi sau khi sửa một phần, biết rằng không có rollback tự động.
14. **Cancellation/timeout:** tránh để caller hiểu nhầm một task đang chạy đã dừng hoàn toàn.
15. **Pool cleanup:** shutdown và awaitTermination/close theo API phiên bản, không leak threads.
16. **Benchmark:** so với sequential baseline, input đủ lớn, warm-up JIT, đo allocation và GC; không in log trong hot loop.
17. **Concurrent mutation bên ngoài:** cố ý test và thiết kế snapshot/ownership để không gây race.
18. **Single task vs many tasks:** đo overhead khi task quá nhỏ và khi chia quá ít.

### 13.1. Unit-test tổng không cần dựa vào lịch threads

Trong test, so sánh kết quả `pool.invoke(new SumTask(...))` với một vòng lặp tuần tự trên cùng input. Không assert worker-name, task-order hay số lần steal; chúng không thuộc hợp đồng kết quả của thuật toán. Với DoubleAction, chờ join rồi so sánh mảng với bản nhân đôi tuần tự.

### 13.2. Test lỗi một child có nghĩa gì?

Nếu `DoubleAction` ném exception ở một leaf do `Math.multiplyExact`, các leaves khác có thể đã thực hiện thay đổi. Vì thế test không nên assert “mảng nguyên vẹn sau lỗi” trừ khi ứng dụng đã có lớp staging/atomic publish riêng. Đây là lý do cần phân biệt **task completion** với **transaction semantics**.

## 14. Câu hỏi tự kiểm tra có đáp án

**Câu 1.** Lớp nào dùng khi muốn một nhiệm vụ chia nhỏ trả kết quả tổng?  
**Đáp án:** `RecursiveTask<Long>`, override `protected Long compute()`, ghép kết quả các children.

**Câu 2.** Vì sao `RecursiveAction` không cần kiểu generic kết quả?  
**Đáp án:** Vì nó kế thừa `ForkJoinTask<Void>` và `compute()` có kiểu `void`; các tác động được thực hiện trực tiếp qua trạng thái cho phép.

**Câu 3.** `new DoubleAction(...).join()` có tự khởi chạy task chưa submit không?  
**Đáp án:** Không nên dùng như cách khởi động task. Hãy `pool.invoke(action)`, `pool.submit(action)` hoặc fork theo đúng ngữ cảnh. `join` là để chờ task đã được sắp lịch/thực thi.

**Câu 4.** `RecursiveAction.join()` trả gì khi hoàn tất thành công?  
**Đáp án:** `null` (kiểu `Void`), không phải boolean thành công hay số lượng phần tử được sửa.

**Câu 5.** `fork()` có luôn tạo OS thread mới không?  
**Đáp án:** Không. Nó đưa task vào cơ chế lập lịch work-stealing của pool, dùng các worker threads có sẵn.

**Câu 6.** Tại sao pattern `left.fork(); right.compute(); left.join()` thường tốt?  
**Đáp án:** Nó cho worker khác cơ hội chạy trái trong khi worker hiện tại tính phải, rồi chỉ chờ khi cần kết quả trái.

**Câu 7.** Có nên fork cả hai child rồi join child đầu trước khi tính gì khác?  
**Đáp án:** Đúng về kết quả trong nhiều trường hợp, nhưng có thể gây overhead/đợi không cần thiết; benchmark và chọn pattern phù hợp.

**Câu 8.** `invokeAll(left,right)` có tự ghép các giá trị return của RecursiveTask không?  
**Đáp án:** Không. Nó lập lịch và chờ; caller vẫn phải lấy các kết quả từ tasks nếu cần combine.

**Câu 9.** `THRESHOLD` có giá trị tiêu chuẩn cố định do JDK đề xuất cho mọi bài toán không?  
**Đáp án:** Không. Phụ thuộc chi phí tính, kích thước input, workload và CPU; phải đo.

**Câu 10.** Vì sao `[from,mid)` và `[mid,to)` giúp DoubleAction an toàn hơn?  
**Đáp án:** Hai intervals disjoint, mỗi index được ghi bởi đúng một leaf; tránh tranh chấp cùng ô.

**Câu 11.** `final long[] values` có khiến nội dung mảng immutable không?  
**Đáp án:** Không. `final` bảo vệ tham chiếu field, không làm phần tử mảng bất biến.

**Câu 12.** Vì sao SumTask dùng `Math.addExact`?  
**Đáp án:** Để phát hiện long overflow thay vì silently wrap; tùy nghiệp vụ có thể dùng BigInteger.

**Câu 13.** Nếu DoubleAction bị lỗi sau khi một số leaves sửa mảng, Fork/Join có tự rollback không?  
**Đáp án:** Không. Hành động có side effects không tạo transaction; cần staging hoặc chính sách phục hồi.

**Câu 14.** Vì sao không nên dùng blocking network I/O lâu trong `compute()`?  
**Đáp án:** ForkJoinPool chủ yếu phù hợp CPU-bound subtasks; blocking có thể giữ workers và giảm tiến triển, trừ khi được thiết kế/managed blocking phù hợp.

**Câu 15.** `ForkJoinTask.get(timeout)` khác `join()` thế nào?  
**Đáp án:** `get(timeout)` cung cấp chờ có thời hạn và checked Future exceptions; `join()` không có tham số timeout và truyền unchecked failure theo ForkJoinTask semantics.

**Câu 16.** Gọi `ForkJoinPool.commonPool().shutdown()` có dừng common pool không?  
**Đáp án:** Không theo contract Java SE 21; common pool là shared và các lời gọi shutdown không ảnh hưởng execution state.

**Câu 17.** Vì sao trong demo `changed-sum=72` và `action-result=null` cùng đúng?  
**Đáp án:** Action thay đổi từng phần tử của mảng thành gấp đôi, nhưng không có return value; task tính tổng mới trả 72 sau đó.

**Câu 18.** Mảng có hàng triệu phần tử có luôn chạy nhanh hơn khi chia thành hàng triệu tasks?  
**Đáp án:** Không. Overhead task creation/scheduling/join và GC có thể rất lớn. Nên dùng chunk đủ lớn, benchmark và giảm số tasks.

**Câu 19.** `RecursiveTask` có bắt buộc phải không gây side effect?  
**Đáp án:** Không bắt buộc theo type system, nhưng thiết kế thuần tính toán/trả kết quả thường dễ kiểm chứng và tránh race hơn.

**Câu 20.** Một RecursiveAction không có return value có thể hoàn tất thất bại không?  
**Đáp án:** Có. Ngoại lệ/cancellation vẫn được truyền qua `join()`/`invoke()`/`get()`; không được bỏ qua chỉ vì result là `Void`.

## 15. Checklist áp dụng trong code review

- [ ] Đề bài cần value → chọn `RecursiveTask<V>`; cần action được kiểm soát → chọn `RecursiveAction`.
- [ ] Override đúng `protected V compute()` hoặc `protected void compute()`.
- [ ] Tất cả nhánh recursion có base case và threshold.
- [ ] Chia đúng intervals `[from,to)`, không rơi/đếm trùng index.
- [ ] Tính middle bằng `from + (to-from)/2` để tránh overflow số học.
- [ ] Không chia quá nhỏ dẫn đến overhead; benchmark threshold thật.
- [ ] Dùng `fork()`/`compute()`/`join()` theo thứ tự hợp lý.
- [ ] Không dùng `join` của task chưa chạy như cơ chế khởi tạo.
- [ ] Nếu dùng `invokeAll` với actions, bảo đảm mọi children hoàn tất trước parent.
- [ ] Với RecursiveTask, kết quả merge đúng và xử lý empty case.
- [ ] Với RecursiveAction, mỗi child chỉ ghi vùng được sở hữu; tránh data races.
- [ ] Không dùng global mutable accumulator khi có thể return kết quả.
- [ ] Không coi `Void` là “không có lỗi” hoặc “đã rollback side effects”.
- [ ] Hiểu `get` khác `join` về timeout/interruption/exception.
- [ ] Xử lý long overflow theo yêu cầu nghiệp vụ, không bỏ qua.
- [ ] Dữ liệu đầu vào không bị sửa đồng thời khi task chỉ đọc, trừ khi đồng bộ/snapshot.
- [ ] Tránh blocking I/O bên trong `compute()`; cân nhắc executor khác khi thích hợp.
- [ ] Dùng custom ForkJoinPool khi cần quản lý parallelism/lifecycle riêng.
- [ ] Không shutdown common pool; shutdown/awaitTermination pool mình sở hữu.
- [ ] Test mảng rỗng, lẻ, một phần tử, overflow và exception.
- [ ] Kiểm tra tốc độ với JMH hoặc phép đo đúng, so với sequential baseline.
- [ ] Chỉ dùng Fork/Join API vẫn được hỗ trợ trên Java hiện đại, không dựa vào hướng dẫn legacy.

## 16. Tài liệu chính thức Java SE 21

- [RecursiveTask<V>](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/RecursiveTask.html): generic task trả kết quả, chữ ký `compute()`, ví dụ fork một nhánh và join.
- [RecursiveAction](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/RecursiveAction.html): action không trả value, `Void` result, in-place parallel operations.
- [ForkJoinTask<V>](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ForkJoinTask.html): `fork`, `join`, `invoke`, `invokeAll`, scheduling và exception/cancellation.
- [ForkJoinPool](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ForkJoinPool.html): work-stealing, `invoke`, `submit`, pool lifecycle, common pool và `ManagedBlocker`.
- [Future](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Future.html): `get`, `get(timeout)` và cancellation.
- [Math](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Math.html): `addExact`, `multiplyExact` và overflow semantics.
- [Arrays](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Arrays.html): `toString`, `parallelSort` và các thao tác mảng có sẵn.

**Kết luận:** `RecursiveTask<V>` trả **giá trị kết quả** được tính và ghép từ các subtasks, còn `RecursiveAction` hoàn tất một **hành động** và có `Void` result (`join() == null` khi thành công). Cả hai dùng cùng cơ chế Fork/Join work-stealing, nhưng phải phân chia dữ liệu đúng, giữ base case, chọn threshold hợp lý, chờ children hoàn tất và xử lý lỗi/side effects riêng. Đúng về concurrency không đồng nghĩa tự động nhanh hơn; hãy chọn API theo output contract và đo hiệu năng trên bài toán thật.

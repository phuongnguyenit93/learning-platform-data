# Vì sao `compute()` trả về chưa đồng nghĩa `CountedCompleter` đã hoàn tất?

Trong Java Fork/Join, `CountedCompleter<T>` là một loại `ForkJoinTask<T>` hỗ trợ **hoàn tất dựa trên tín hiệu và số lượng phần việc còn cần phối hợp**, thay vì chỉ dựa trên việc một phương thức trả về. Đây là điểm khác biệt cốt lõi khiến người mới dễ nhầm:

> **`CountedCompleter.compute()` có thể trả về bình thường nhưng task vẫn chưa ở trạng thái hoàn tất.** Việc hoàn tất phụ thuộc giao thức gọi `tryComplete()`, `propagateCompletion()` hoặc thao tác hoàn tất tường minh tương ứng; nếu thiếu tín hiệu, root task có thể bị chờ mãi.

Điều này không phải lỗi của JVM. `CountedCompleter` cố ý tách **thực thi phần thân `compute`** khỏi **hoàn tất của cây công việc** vì parent có thể chỉ fork các subtasks rồi trả về, trong khi nhiều nhánh con vẫn phải chạy và gửi tín hiệu hoàn tất.

Bài này giải thích cơ chế trong **Java SE 17+**, thuộc nhóm **Fork/Join** của **Java concurrency nói chung**, không sử dụng các lớp/annotation concurrency của Spring Framework.

## 1. Khác biệt ngữ nghĩa với `RecursiveTask` và `RecursiveAction`

`RecursiveTask<V>` và `RecursiveAction` quen thuộc hơn trong mô hình chia để trị:

- `RecursiveTask<V>.compute()` trả `V`, và khi implementation thực thi task bình thường, kết quả đó được dùng để hoàn tất `ForkJoinTask`.
- `RecursiveAction.compute()` trả `void`; khi task được thực thi bình thường, quá trình thực thi của task theo mô hình này đi tới hoàn tất.
- `CountedCompleter<T>.compute()` cũng trả `void`, nhưng **việc return đơn thuần không tự động quyết định trạng thái hoàn tất**. Nó sử dụng **completion protocol** với pending count và completer chain.

| Khía cạnh | `RecursiveTask<V>` | `RecursiveAction` | `CountedCompleter<T>` |
| --- | --- | --- | --- |
| Chữ ký `compute` | `V compute()` | `void compute()` | `void compute()` |
| Cơ chế quen thuộc | Tính rồi trả kết quả | Hoàn tất hành động | Tín hiệu completion, parent completer, pending count |
| Return bình thường của `compute` khi executor thực thi | Thường hoàn tất task | Thường hoàn tất task | **Không đủ để suy ra task hoàn tất** |
| Phối hợp nhánh con | Thường `fork` rồi `join` | Thường `fork` rồi `join` | Thường `tryComplete` hoặc `propagateCompletion` qua chain |
| Dạng bài toán | Reduction cần result | Tác vụ phân đoạn không result | Completion-driven tree, fan-out và dependency graph thích hợp |
| Lấy kết quả | Result của task | Không có result nghiệp vụ | Mặc định `null`; muốn trả `T` có thể override `getRawResult` |

Trong `CountedCompleter`, **task đã được thực thi** và **task đã hoàn tất** là hai sự kiện cần phân biệt. Điều đó cho phép tác vụ gốc **không block trong `compute()` để chờ từng đứa con**, nhưng vẫn cho caller ở ngoài cây dùng `pool.invoke(root)` để chờ toàn bộ giao thức hoàn tất.

## 2. `CountedCompleter` là gì?

Chữ ký khái quát:

```java
public abstract class CountedCompleter<T>
        extends ForkJoinTask<T> {
    public abstract void compute();
    public void onCompletion(CountedCompleter<?> caller);
    public final void tryComplete();
    public final void propagateCompletion();
    public final int getPendingCount();
    public final void setPendingCount(int count);
    public final void addToPendingCount(int delta);
}
```

Đây là **trích lược các member để học**, không phải class có thể đem biên dịch: `CountedCompleter` thật nằm trong JDK với nhiều method/chi tiết khác.

Các thành phần quan trọng:

- **`compute()`:** làm việc tại một node: xử lý trực tiếp hoặc tạo các nhánh con.
- **`completer`:** tham chiếu tới node sẽ nhận tác động completion từ task hiện tại; thường là parent.
- **`pendingCount`:** bộ đếm nguyên tử của những **tín hiệu completion cần phối hợp** tại node.
- **`tryComplete()`:** gửi một lần tín hiệu vào giao thức completion; có thể giảm pending hoặc, nếu pending đã bằng 0, thực thi `onCompletion` và đi tiếp lên completer.
- **`onCompletion(caller)`:** callback khi node đến ngưỡng hoàn tất bình thường; thường dùng gộp kết quả từ những task con.
- **`propagateCompletion()`:** như `tryComplete` ở cơ chế đếm/truyền tín hiệu, nhưng không gọi `onCompletion` trên đường truyền.
- **Task status** (`isDone`, `join`, `get`): đối với **root**, nó phản ánh khi giao thức completion đã đánh dấu root hoàn tất.

`CountedCompleter` được thiết kế cho những thuật toán có cây phụ thuộc; nó không tự ghi nhớ danh tính mọi subtask. **Pending count không phải một bộ đếm con "đăng ký tự động"** — người viết thuật toán có trách nhiệm tăng/đặt count và gửi đúng tín hiệu.

## 3. Điều gì xảy ra khi `compute()` trả về?

Một hình dung dễ gây lỗi:

```text
compute() bắt đầu
   |
   v
fork tasks
   |
   v
compute() return
   |
   v
[KHÔNG TỰ SUY RA isDone == true]
```

Với `CountedCompleter`, đường hoàn tất bình thường không phải "executor thấy method return thì lập tức complete". Thay vào đó, completion được điều phối bởi các lời gọi trong nhiệm vụ hoặc các nhánh con. Có thể mô tả:

```text
                 compute() return
                       |
                       v
          node có thể chưa hoàn tất
                       |
           các nhánh con còn làm việc
                       |
          child.tryComplete() / ...
                       |
              pending transitions
                       |
             onCompletion nếu có
                       |
             truyền về completer
                       |
              root được đánh dấu
                    complete
```

Cần nhớ **`compute` không phải `Future.get`**. Return của code trong worker khác với việc caller đang giữ handle quan sát trạng thái của `ForkJoinTask`. Một root có thể trả khỏi `compute` trong khi `pool.invoke(root)` vẫn còn đợi vì root chưa được hoàn tất bằng protocol.

Điều này rất hữu ích: parent có thể **fork một loạt nhánh rồi trả thread cho pool**, nhờ đó worker tiếp tục thực thi task khác, thay vì parent giữ stack frame và chờ `join` cho từng nhánh.

## 4. Ví dụ Java 17+: gọi `compute()` trực tiếp rồi kiểm tra trạng thái

Lưu thành `BareComputeReturnDemo.java`:

```java
import java.util.concurrent.CountedCompleter;

public class BareComputeReturnDemo {
    static final class NoSignal extends CountedCompleter<Void> {
        @Override
        public void compute() {
            // Cố ý không gọi tryComplete() hoặc complete(...).
        }
    }

    public static void main(String[] args) {
        NoSignal task = new NoSignal();

        task.compute();
        System.out.println("Returned from compute: true");
        System.out.println("Done after return: " + task.isDone());

        task.tryComplete();
        System.out.println("Done after signal: " + task.isDone());
    }
}
```

Chạy với JDK 17+:

```bash
javac BareComputeReturnDemo.java
java BareComputeReturnDemo
```

Stdout chính xác:

```text
Returned from compute: true
Done after return: false
Done after signal: true
```

Phân tích:

1. `compute()` chạy đồng bộ trên main thread, return bình thường.
2. Không có lời gọi completion nào, nên `isDone()` vẫn false.
3. Task không có completer, pending mặc định 0. `tryComplete()` thấy pending bằng 0, chạy `onCompletion` mặc định (không làm gì), rồi đánh dấu root hoàn tất.
4. `isDone()` chuyển true.

**Giới hạn ví dụ:** đây là lời gọi `compute()` **trực tiếp**, chưa đưa task vào `ForkJoinPool`; nó dùng để chứng minh phân biệt **return** với **task completion** mà không phụ thuộc scheduling. Trong thực tế, thường submit/invoke root qua pool, không coi gọi trực tiếp `compute()` là cách khởi chạy framework.

## 5. `tryComplete()`: mỗi lời gọi có thể chỉ giảm count

Javadoc Java SE 17 định nghĩa ý nghĩa cơ bản:

- Nếu pending hiện tại **khác 0**, `tryComplete()` **giảm nó đi một đơn vị** và **dừng cuộc truyền completion ở node đó**.
- Nếu pending hiện tại **bằng 0**, `tryComplete()` thực hiện `onCompletion(caller)` rồi tiếp tục quy trình tương tự với completer; khi đường đi đến root không còn completer, root được đánh dấu hoàn tất.
- Tín hiệu có thể xuất phát từ **chính node** hoặc từ **node con**, tùy thuật toán.
- Các thao tác pending-count là atomic trong giới hạn method đã định nghĩa; chúng **không tự quản lý** identity/lifecycle của nhánh con.

Sơ đồ ba lần gọi vào một node có `pendingCount = 2`:

```text
Ban đầu node.pending = 2
signal #1: tryComplete() => 2 -> 1, CHƯA complete
signal #2: tryComplete() => 1 -> 0, CHƯA complete
signal #3: tryComplete() => thấy 0, gọi onCompletion,
                           rồi truyền lên completer/root
```

Đây là **điểm dễ nhầm nhất**: **pending bằng 0 chưa chắc task đã complete**. Một lời gọi `tryComplete` tiếp theo phải quan sát pending đang bằng 0 để thực hiện completion action theo cơ chế này.

Trong nhiều thuật toán, số lượng lời gọi `tryComplete` được thiết kế là **pending ban đầu + 1** ở node đó. Tuy nhiên, còn các kiểu tối ưu bỏ một tín hiệu ở parent và đặt pending thấp hơn, nên **không được coi pending luôn bằng chính xác số task con còn chạy**.

## 6. Tại sao pending count không phải "đếm task tự động"?

Nếu viết:

```java
setPendingCount(2);
new Child(this).fork();
new Child(this).fork();
```

đây là snippet minh họa trong một `CountedCompleter`, không có định nghĩa class `Child` trong đoạn này. Forking hai child **không tự giảm count khi chúng return**. Mỗi child phải thực hiện giao thức `tryComplete` hoặc `propagateCompletion`, hoặc parent phải quản lý tín hiệu theo cách khác.

Do đó count có thể sai theo cả hai hướng:

- **Thiếu tín hiệu:** task gốc mãi chưa complete, caller `join/get/invoke` có thể chờ vô hạn.
- **Dư tín hiệu/đặt count thiếu:** một node có thể kích hoạt completion quá sớm, khi còn nhánh chạy hoặc dữ liệu gộp chưa sẵn sàng.
- **Bỏ qua lỗi:** một nhánh exception hoặc bị cancel có thể không gửi normal completion như mong đợi; failure policy cần phân biệt với normal path.
- **Không đồng bộ external changes:** `setPendingCount` không tự bảo vệ những mutable field khác nếu ngoài thuật toán còn có writer cạnh tranh.

Tài liệu nên nói **"pending là bộ đếm tín hiệu completion theo giao thức của thuật toán"**, thay vì "pending là số thread đang chạy" hay "pending chắc chắn là số child chưa xong".

## 7. Hai chiến lược đếm đúng khi có hai child

Giả sử parent chia thành hai child hoàn toàn độc lập.

**Chiến lược A — parent cũng gửi tín hiệu riêng:**

```java
setPendingCount(2);
left.fork();
right.fork();
tryComplete(); // Tín hiệu của parent: đã xong việc phát child.
```

Mỗi child sau khi xử lý xong gọi `tryComplete()` với `completer = parent`. Tổng ba tín hiệu tới parent: một từ parent + hai từ child. Với pending khởi tạo 2, tín hiệu thứ ba quan sát count 0 và hoàn tất parent.

**Chiến lược B — parent trực tiếp chạy một child:**

```java
setPendingCount(1);
right.fork();
left.compute(); // Child này tự tryComplete() ở nhánh hoàn tất.
```

Parent **không gọi `tryComplete()` thêm một lần** ở đường này. Có hai completion signal từ hai child, pending được đặt 1 để tín hiệu đầu giảm về 0, tín hiệu thứ hai hoàn tất parent.

Hai snippet là phần thân `compute` minh họa, giả định các child có completer chính xác và xử lý xong sẽ gửi một tín hiệu phù hợp. Không dùng hai chiến lược chung một chỗ: nếu ở chiến lược B vẫn gọi parent `tryComplete` thêm lần nữa, parent có thể hoàn tất sớm khi một child chưa xong.

**Nguyên tắc:** chọn count dựa trên **số tín hiệu thực tế sẽ tới**, không dựa trên việc code có bao nhiêu lời gọi `fork()`.

## 8. Ví dụ Java 17+: hai child + một tín hiệu parent

Lưu thành `CountedCompleterSignalsDemo.java`:

```java
import java.util.concurrent.CountedCompleter;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.atomic.AtomicInteger;

public class CountedCompleterSignalsDemo {
    static final class Root extends CountedCompleter<Void> {
        final AtomicInteger childActions = new AtomicInteger();
        final AtomicInteger rootHooks = new AtomicInteger();

        @Override
        public void compute() {
            setPendingCount(2);
            new Child(this).fork();
            new Child(this).fork();

            // Parent đã xong công việc phát nhánh, nhưng child có thể chưa xong.
            tryComplete();
        }

        @Override
        public void onCompletion(CountedCompleter<?> caller) {
            rootHooks.incrementAndGet();
        }
    }

    static final class Child extends CountedCompleter<Void> {
        private final Root root;

        Child(Root parent) {
            super(parent);
            this.root = parent;
        }

        @Override
        public void compute() {
            root.childActions.incrementAndGet();
            tryComplete(); // Gửi tín hiệu qua completer = root.
        }
    }

    public static void main(String[] args) {
        ForkJoinPool pool = new ForkJoinPool(2);
        Root root = new Root();

        try {
            pool.invoke(root);

            System.out.println("Child actions: "
                    + root.childActions.get());
            System.out.println("Root onCompletion: "
                    + root.rootHooks.get());
            System.out.println("Pending: " + root.getPendingCount());
            System.out.println("Root done: " + root.isDone());
        } finally {
            pool.shutdown();
        }
    }
}
```

```bash
javac CountedCompleterSignalsDemo.java
java CountedCompleterSignalsDemo
```

Stdout chính xác:

```text
Child actions: 2
Root onCompletion: 1
Pending: 0
Root done: true
```

**Giải thích vì sao không phụ thuộc lịch chạy:**

1. Parent đặt pending = 2 **trước khi fork**, để child không gửi completion trước lúc count được thiết lập.
2. Có đúng **ba** tín hiệu vào root: parent `tryComplete` và hai child `tryComplete`.
3. Hai tín hiệu đầu giảm count theo atomic protocol; tín hiệu cuối quan sát 0 và chạy root `onCompletion` một lần.
4. `pool.invoke(root)` chỉ trả bình thường sau khi root được đánh dấu hoàn tất; lúc đó hai child đã cập nhật `childActions`.
5. Thứ tự parent/child gửi tín hiệu **không được giả định**, nhưng tổng tín hiệu và kết quả không đổi.
6. `rootHooks` được tăng trong callback normal completion, không phải bởi constructor hoặc việc `compute` return.
7. Không có lời gọi `join()` tới từng child; parent nhận completion bằng tín hiệu từ các child thay vì block khi chờ từng nhánh.

Nếu bỏ một trong ba lời gọi tín hiệu mà không điều chỉnh protocol, root có thể **không hoàn tất**, dù child action đã xong.

## 9. Tình huống khó thấy: pending đã 0 mà root vẫn chưa `isDone()`

Giả sử parent chỉ có một child và viết:

```java
setPendingCount(1);
new Child(this).fork();
// BỎ QUÊN tryComplete() của parent.
```

Child hoàn tất rồi gọi `tryComplete`; thao tác này thấy pending của parent là 1 và **giảm xuống 0**, sau đó dừng. Không còn tín hiệu nào để quan sát 0 và kích hoạt completion của root.

Sau cùng có thể có:

```text
child compute: đã chạy
child.tryComplete: đã gọi
root.pendingCount: 0
root.isDone(): false
root.join(): có thể chờ vô thời hạn
```

Đây là lỗi **thiếu một tín hiệu hoàn tất**, không phải lỗi `join` không làm việc hoặc pool thiếu thread. Tăng parallelism của pool không tự sửa một completion protocol sai.

Để khắc phục, parent phải gửi tín hiệu của mình (`tryComplete`) **sau khi đã fork**, hoặc đổi thuật toán sang chiến lược đếm phù hợp với số tín hiệu thực sự tồn tại.

## 10. Ví dụ Java 17+: lỗi thiếu tín hiệu và cách hoàn tất có kiểm soát

Lưu thành `MissingCompletionSignalDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.CountedCompleter;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class MissingCompletionSignalDemo {
    static final class Parent extends CountedCompleter<Void> {
        final CountDownLatch childReported = new CountDownLatch(1);

        @Override
        public void compute() {
            setPendingCount(1);
            new Child(this).fork();
            // BUG: thiếu tryComplete() của parent.
        }
    }

    static final class Child extends CountedCompleter<Void> {
        private final Parent parent;

        Child(Parent parent) {
            super(parent);
            this.parent = parent;
        }

        @Override
        public void compute() {
            parent.tryComplete(); // Root pending: 1 -> 0.
            parent.childReported.countDown();
        }
    }

    public static void main(String[] args) throws Exception {
        ForkJoinPool pool = new ForkJoinPool(2);
        Parent parent = new Parent();

        try {
            pool.execute(parent);
            parent.childReported.await();

            boolean gotTimeout = false;
            try {
                parent.get(30, TimeUnit.MILLISECONDS);
            } catch (TimeoutException e) {
                gotTimeout = true;
            }

            System.out.println("Pending after child: "
                    + parent.getPendingCount());
            System.out.println("Done before fix: " + parent.isDone());
            System.out.println("Timed get expired: " + gotTimeout);

            // Chỉ để kết thúc demo lỗi có kiểm soát.
            parent.tryComplete();
            System.out.println("Done after missing signal: "
                    + parent.isDone());
        } finally {
            pool.shutdownNow();
        }
    }
}
```

```bash
javac MissingCompletionSignalDemo.java
java MissingCompletionSignalDemo
```

Stdout chính xác trong lần chạy bình thường:

```text
Pending after child: 0
Done before fix: false
Timed get expired: true
Done after missing signal: true
```

**Điểm chủ đích của demo:** `childReported` chỉ được đếm sau khi child đã gửi một tín hiệu vào parent; parent còn thiếu tín hiệu của chính nó. `get(timeout)` không bị treo mãi, giúp **quan sát rằng task chưa hoàn tất**. Sau đó main gửi tín hiệu còn thiếu để giải phóng root.

Đây **không phải mẫu sửa lỗi production bằng cách cho thread ngoài tự gọi `tryComplete` tùy ý**. Trong thuật toán thật, chính parent/child phải tuân theo protocol rõ ràng; nếu dùng tín hiệu từ ngoài để vá, dễ tạo double completion hoặc race dữ liệu ở workload phức tạp.

Đừng thay timeout bằng `parent.join()` khi đang cố tình trình diễn code sai: `join` có thể đợi vô hạn và làm test treo.

## 11. `onCompletion(caller)` không phải callback sau mọi lần `compute`

`onCompletion(CountedCompleter<?> caller)` chạy khi completion protocol kích hoạt normal completion của node theo `tryComplete` hoặc `complete`; **không phải cứ return `compute` là callback chạy**.

Một số trường hợp:

- Nếu `pendingCount > 0`, một `tryComplete` chỉ giảm count, **không** gọi `onCompletion`.
- Nếu `pendingCount == 0` tại lúc một `tryComplete` tới, callback được gọi trên node đó.
- Nếu một child gửi completion lên parent, tham số `caller` giúp phân biệt child nào kích hoạt đường completion.
- Với `complete(T)`, callback được gọi bất kể pendingCount, vì đây là thao tác hoàn tất tường minh theo hợp đồng.
- `propagateCompletion` **không gọi** `onCompletion` trong quá trình truyền bình thường.

Javadoc ghi rằng `caller` có thể là chính task hoặc một task con; không nên giả định luôn là parent hoặc luôn bằng `this`. Trong thuật toán giảm (reduction), `onCompletion` thường gộp kết quả các child khi biết tất cả đã sẵn sàng.

## 12. Chiến lược tối ưu: fork một child, compute child còn lại

Khác với ví dụ parent phát hai child rồi gửi tín hiệu riêng, một thuật toán chia đôi có thể viết:

```java
setPendingCount(1);
right.fork();
left.compute(); // left là một CountedCompleter có parent này.
```

Nếu cả left và right cuối cùng gửi tín hiệu completion một lần về parent, **hai tín hiệu** đủ để:

1. Một tín hiệu giảm pending parent từ 1 xuống 0.
2. Tín hiệu còn lại quan sát count 0, gọi `onCompletion` và truyền lên ancestor.

Parent không cần tự gửi `tryComplete` ở cuối nhánh này. Lý do: một phần công việc của parent được **chuyển thành lời gọi compute trực tiếp** trên left, và chính left sẽ gửi completion.

**Cảnh báo:** nếu caller hiểu nhầm rồi thêm `tryComplete` vào parent nữa, có thể có **ba tín hiệu trong khi count chỉ dành cho hai**. Root có thể được đánh dấu hoàn tất khi một child còn đang chạy, khiến result hoặc side effect chưa sẵn sàng.

Tương tự, nếu left chỉ return khỏi `compute` mà **quên gọi `tryComplete`**, parent có thể không nhận đủ tín hiệu — không thể dựa vào return của child để tự hoàn tất.

## 13. Ví dụ Java 17+: tính tổng bằng `CountedCompleter<Long>`

Ví dụ này sử dụng `onCompletion` để gộp kết quả **sau khi hai child đã gửi tín hiệu**.

Lưu thành `CountedCompleterSumDemo.java`:

```java
import java.util.concurrent.CountedCompleter;
import java.util.concurrent.ForkJoinPool;

public class CountedCompleterSumDemo {
    static final class SumTask extends CountedCompleter<Long> {
        private final int[] data;
        private final int start;
        private final int end;

        private SumTask left;
        private SumTask right;
        private long result;

        SumTask(SumTask parent, int[] data, int start, int end) {
            super(parent);
            this.data = data;
            this.start = start;
            this.end = end;
        }

        @Override
        public void compute() {
            if (end - start <= 4) {
                long sum = 0;
                for (int i = start; i < end; i++) {
                    sum += data[i];
                }
                result = sum;
                tryComplete();
                return;
            }

            int mid = start + (end - start) / 2;
            left = new SumTask(this, data, start, mid);
            right = new SumTask(this, data, mid, end);

            // Hai child gửi hai completion signals.
            setPendingCount(1);
            right.fork();
            left.compute();
        }

        @Override
        public void onCompletion(CountedCompleter<?> caller) {
            if (left != null) {
                result = left.result + right.result;
            }
        }

        @Override
        public Long getRawResult() {
            return result;
        }
    }

    public static void main(String[] args) {
        int[] input = new int[16];
        for (int i = 0; i < input.length; i++) {
            input[i] = i + 1;
        }

        ForkJoinPool pool = new ForkJoinPool(4);
        try {
            SumTask root = new SumTask(
                    null, input, 0, input.length);

            long sum = pool.invoke(root);

            System.out.println("Sum: " + sum);
            System.out.println("Root done: " + root.isDone());
        } finally {
            pool.shutdown();
        }
    }
}
```

```bash
javac CountedCompleterSumDemo.java
java CountedCompleterSumDemo
```

Stdout chính xác:

```text
Sum: 136
Root done: true
```

**Giải thích chi tiết:**

- Mảng có các số 1 đến 16, nên tổng đúng là `16 × 17 / 2 = 136`.
- Mỗi node non-leaf tạo hai child có `completer` trỏ về parent.
- Node non-leaf dùng `setPendingCount(1)` vì **hai child** sẽ lần lượt gửi completion signal, và parent không tự gọi `tryComplete` ở nhánh tách.
- Một child được `fork`; child còn lại được tính **trực tiếp trên current thread**. Return của parent `compute` không tự kết thúc parent.
- Leaf tính tổng riêng vào `result` rồi gọi `tryComplete`. Tín hiệu đó cuối cùng truyền qua những ancestor khi count của chúng đã sẵn sàng.
- `onCompletion` của internal node chỉ gộp khi hai child đã hoàn tất phần dữ liệu cần thiết. Callback này có thể chạy trên thread thực hiện **tín hiệu completion cuối**, không nhất thiết thread đã tạo parent.
- `getRawResult()` trả giá trị root để `pool.invoke` có thể trả `Long`. Mặc định `CountedCompleter` trả `null` nếu không override result phù hợp.
- Không cần `join()` từng child; **root completion** là ranh giới synchronization của toàn bộ reduction.

Quan trọng: đây là mô hình reduction **không gộp dữ liệu bằng mutable accumulator chung**; mỗi leaf có result riêng, các internal nodes chỉ đọc child result khi protocol completion đã bảo đảm sẵn sàng.

## 14. Có được gọi `join()` trên những child của `CountedCompleter` không?

Về mặt API, `CountedCompleter` vẫn là `ForkJoinTask`, nên có `join()`. Nhưng **trạng thái task của những node có completer có thể không chuyển sang "done" theo cách một người dùng `RecursiveTask` dự đoán**.

Javadoc Java 17 nêu rằng một CountedCompleter **không có completer** (root) có thể dùng như một ForkJoinTask độc lập với completion status có ý nghĩa; còn các CountedCompleter **có completer** thường là internal helpers và **task status riêng của chúng có thể mang tính tùy ý**, chỉ thay đổi bởi các thao tác completion tường minh hoặc exceptional completion được hỗ trợ.

Điều này dẫn tới lỗi:

```java
Child child = new Child(parent);
child.fork();
child.join(); // Có thể đợi không đúng giao thức
```

Đây là snippet minh họa. Nếu child gửi `tryComplete` **về parent** mà bản thân child không được đánh dấu complete, `child.join()` không tự có semantics "đã xong việc child" như với `RecursiveTask`.

**Thường hãy chờ root**, ví dụ `pool.invoke(root)`, `root.join()` sau khi root đã được submit/fork đúng ngữ cảnh, hoặc `root.get(timeout, unit)` để kiểm tra có giới hạn thời gian. Không dựa vào `child.isDone()` như bộ đếm tiến độ của toàn bộ cây.

## 15. `getPendingCount()==0` có chứng minh `isDone()==true` không?

**Không.** Đây là hai loại trạng thái khác nhau:

| Quan sát | Điều có thể suy ra |
| --- | --- |
| `getPendingCount() == 0` | Bộ đếm pending hiện đang bằng 0 |
| `isDone() == true` của root | Root task đã được đánh dấu hoàn tất bình thường, bất thường hoặc hủy theo contract |
| `isCompletedNormally() == true` của root | Root task đã hoàn tất bình thường |
| `isCompletedAbnormally() == true` | Task hoàn tất bất thường hoặc canceled theo contract |
| `root.join()` trả bình thường | Root được hoàn tất và caller nhận được raw result theo contract |

Như `MissingCompletionSignalDemo` cho thấy, pending root đã 0 nhưng root chưa có tín hiệu tiếp theo để kích hoạt completion. Ngược lại, `complete(T)` có thể đánh dấu task hoàn tất **bất kể pendingCount**. Vì vậy không có tương đương hai chiều giữa pending == 0 và task status.

Ngoài ra, đọc pendingCount ở một thời điểm chỉ là **ảnh chụp giá trị**. Nó không thay thế contract chờ của `join/get/invoke`, không phải cách đo số worker hiện đang chạy hay dự đoán deadline completion.

## 16. `propagateCompletion()` khác `tryComplete()` thế nào?

Theo hợp đồng:

- `tryComplete()` có thể gọi `onCompletion` tại node khi pending bằng 0, sau đó truyền tín hiệu lên chain.
- `propagateCompletion()` thực hiện cơ chế giảm pending/truyền completion tương ứng **nhưng không gọi `onCompletion`** trên đường đi.

Dùng `propagateCompletion` khi thuật toán **không cần callback gộp kết quả** trên mỗi node, ví dụ mỗi leaf ghi vào vùng dữ liệu riêng rồi chỉ cần biết toàn bộ cây đã xong.

Không thay `tryComplete` bằng `propagateCompletion` trong một reduction cần `onCompletion` để tính tổng: root có thể được đánh dấu complete nhưng trường `result` chưa được gộp đúng.

Hình dung:

```text
tryComplete:
  pending > 0 -> decrement
  pending = 0 -> onCompletion -> parent -> ... -> root completion

propagateCompletion:
  pending > 0 -> decrement
  pending = 0 ->               parent -> ... -> root completion
```

Cả hai vẫn phải tuân thủ **đúng số tín hiệu**. `propagateCompletion` không tự tìm các child còn chưa xong và không tự sửa pending thiếu/thừa.

## 17. Ví dụ Java 17+: `propagateCompletion` bỏ qua callback nhưng vẫn complete root

Lưu thành `PropagateCompletionDemo.java`:

```java
import java.util.Arrays;
import java.util.concurrent.CountedCompleter;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.atomic.AtomicInteger;

public class PropagateCompletionDemo {
    static final class Root extends CountedCompleter<Void> {
        final int[] values = {1, 2, 3, 4};
        final AtomicInteger callbacks = new AtomicInteger();

        @Override
        public void compute() {
            setPendingCount(2);

            new Leaf(this, values, 0, 2).fork();
            new Leaf(this, values, 2, 4).fork();

            propagateCompletion();
        }

        @Override
        public void onCompletion(CountedCompleter<?> caller) {
            callbacks.incrementAndGet();
        }
    }

    static final class Leaf extends CountedCompleter<Void> {
        private final int[] data;
        private final int from;
        private final int to;

        Leaf(Root parent, int[] data, int from, int to) {
            super(parent);
            this.data = data;
            this.from = from;
            this.to = to;
        }

        @Override
        public void compute() {
            for (int i = from; i < to; i++) {
                data[i] *= 2;
            }
            propagateCompletion();
        }
    }

    public static void main(String[] args) {
        ForkJoinPool pool = new ForkJoinPool(2);
        Root root = new Root();

        try {
            pool.invoke(root);

            System.out.println("Values: "
                    + Arrays.toString(root.values));
            System.out.println("Root callback calls: "
                    + root.callbacks.get());
            System.out.println("Root done: " + root.isDone());
        } finally {
            pool.shutdown();
        }
    }
}
```

```bash
javac PropagateCompletionDemo.java
java PropagateCompletionDemo
```

Stdout chính xác:

```text
Values: [2, 4, 6, 8]
Root callback calls: 0
Root done: true
```

**Giải thích:**

- Hai leaf ghi vào các vùng `[0,2)` và `[2,4)` không chồng lấn.
- Parent đặt pending = 2 và gửi một tín hiệu sau khi fork; hai leaf gửi hai tín hiệu qua `propagateCompletion`.
- Ba tín hiệu hoàn tất root, nên `pool.invoke(root)` trả về.
- Không có `onCompletion` nào được gọi vì toàn bộ đường completion dùng `propagateCompletion`.
- Kết quả array chính xác vì các leaf đã hoàn tất mutation cần thiết trước khi root được hoàn tất.

Với tác vụ biến đổi phân đoạn, `propagateCompletion` giúp tránh callback kết hợp không cần thiết; nhưng nếu có mutable shared state khác, vẫn phải có ownership hoặc synchronization đúng.

## 18. `complete(T)`: hoàn tất tường minh, không đợi pending về 0

`CountedCompleter.complete(T rawResult)` có semantics khác với `tryComplete()`:

1. Nó **không** cần pendingCount bằng 0.
2. Nó gọi `setRawResult(rawResult)` theo hợp đồng (mặc định `CountedCompleter` không làm gì đặc biệt).
3. Nó gọi `onCompletion`.
4. Nó đánh dấu task đó hoàn tất.
5. Nó gửi tiếp completion theo giao thức tới completer nếu có.

Điều này hữu ích cho một số thuật toán **early termination** khi đã có kết quả đủ tốt, hoặc một task có thể chủ động công bố kết quả mà không cần chờ mọi nhánh. Nhưng dùng sai có thể làm caller nhìn thấy result chưa sẵn sàng hoặc những nhánh vẫn ghi state.

Ví dụ minh họa:

```java
final class SimpleCompleter
        extends java.util.concurrent.CountedCompleter<Void> {
    @Override
    public void compute() {
        complete(null);
    }
}
```

Đây là class minh họa, không có `main`. `complete(null)` có thể hoàn tất task dù không gọi `tryComplete`. Với computation phức tạp, **không gọi `complete` chỉ để "chữa lỗi join treo"** khi pending protocol đang sai.

Nếu task có type `T` và muốn trả result từ `join/invoke`, có thể override `getRawResult()` để đọc field result. `setRawResult` mặc định không lưu giá trị như người dùng `RecursiveTask<V>` có thể kỳ vọng.

## 19. `quietlyCompleteRoot()`: kết thúc sớm root theo thiết kế

`quietlyCompleteRoot()` đánh dấu root hoàn tất bình thường theo API ForkJoin mà không nhất thiết gọi `onCompletion` của mọi node.

Ví dụ tìm một phần tử bất kỳ thỏa điều kiện: nếu một nhánh đã công bố kết quả bằng `AtomicReference.compareAndSet(null, found)`, thuật toán có thể **chủ động hoàn tất root** để caller nhận kết quả sớm, thay vì đợi toàn bộ các nhánh chưa cần thiết.

Nhưng phải phân biệt:

- Root có thể được đánh dấu complete **trước khi mọi child thật sự dừng**, nếu thuật toán cho phép.
- Các child còn chạy cần được phép tiếp tục hoặc phải có cancellation policy riêng.
- Dữ liệu kết quả cần được công bố an toàn, ví dụ qua atomic reference.
- Không dùng early completion nếu caller sẽ đọc mutable shared state vẫn còn bị các child sửa mà không có giao thức.
- "Đã có kết quả" không có nghĩa các side effect ngoại vi được hoàn tác hoặc những task khác tự bị cancel.

Vì vậy, `quietlyCompleteRoot` là công cụ **early-exit chuyên biệt**, không phải lời gọi thay thế bừa bãi cho `tryComplete` bị bỏ quên.

## 20. `onCompletion` chạy trên thread nào?

Đối với CountedCompleter, callback `onCompletion` có thể được kích hoạt bởi một lời gọi `tryComplete` từ **node hiện tại** hoặc từ **một subtask**. Vì vậy thread thực hiện callback có thể là **worker vừa hoàn tất tín hiệu cuối**, không nhất thiết worker đã tạo node đó.

Điều này ảnh hưởng:

- **Thread affinity:** không được mặc định `onCompletion` của parent chạy trên worker đã gọi parent.`compute()`.
- **Logging context / ThreadLocal:** dữ liệu gắn với thread có thể khác giữa `compute` và `onCompletion`.
- **Shared state:** chỉ dựa vào hiệu ứng completion protocol khi có đủ tín hiệu, không dựa vào thread ID.
- **I/O hoặc callback chậm:** chạy nhiều logic blocking trong `onCompletion` có thể giữ worker Fork/Join lâu và ảnh hưởng throughput.
- **Exception:** nếu `onCompletion` ném exception, computation có thể hoàn tất bất thường; không được coi kết quả gộp đã chắc chắn hợp lệ.

Không sử dụng tên thread hoặc thứ tự log để xác nhận hoàn tất. Kết quả toán học, pending protocol và root completion là những điều cần kiểm tra.

## 21. Memory visibility: khi nào được đọc kết quả của child?

Một thuật toán CountedCompleter thường để mỗi child ghi vào field kết quả riêng, rồi parent đọc trong `onCompletion`. Javadoc nêu rằng **nếu pending count và completion protocol được dùng đúng**, các truy cập kết quả của những task đã hoàn tất có thể được thực hiện an toàn trong completion callback, không cần thêm synchronization chỉ cho việc đọc những field đó.

Tuy nhiên, điều đó **không có nghĩa mọi shared mutable state trở nên thread-safe**:

- Child phải viết result trước khi gửi completion signal.
- Parent chỉ đọc result sau khi giao thức đã nhận đủ tín hiệu tương ứng.
- Các task không được tiếp tục sửa cùng result sau khi đã báo "hoàn tất phần việc".
- Nếu một thread bên ngoài sửa cùng field không qua giao thức, vẫn có data race.
- Nếu dùng shared `ArrayList` và nhiều child `add` concurrent, cần synchronization hoặc thiết kế local results + combine.
- Nếu cho phép early root completion, caller có thể đọc state trong lúc các child còn làm việc; phải định nghĩa state nào ổn định.

Trong `CountedCompleterSumDemo`, child leaf ghi `result` trước `tryComplete`, parent `onCompletion` chỉ gộp sau khi đủ hai child signals. Đây là điểm bảo đảm tính đúng, không phải vì trường `result` được đặt tên đặc biệt.

## 22. `onExceptionalCompletion`: lỗi không phải normal completion

`CountedCompleter` có hook:

```java
public boolean onExceptionalCompletion(
        Throwable ex,
        CountedCompleter<?> caller)
```

Hook có thể được gọi khi task hoàn tất **bất thường**, chẳng hạn `compute` ném exception hoặc task được đánh dấu exceptional. Theo mặc định, nó trả `true` để cho phép truyền exceptional completion tới completer nếu phù hợp.

Nếu override, hãy hiểu return value: `true` cho phép exception tiếp tục truyền lên chain, còn `false` ngăn việc truyền theo con đường đó. Đây **không phải** callback normal completion `onCompletion`.

Nếu một child lỗi, parent có thể không nhận normal signal; việc truyền exceptional completion được thiết kế để tránh parent cứ đợi thành công một phép tính đã thất bại. Nhưng không phải mọi failure/cancellation của mọi task ngoài hệ thống đều tự được truyền đúng ý nghĩa — chỉ khi task và completion chain tuân thủ hợp đồng.

**Không tự động catch exception rồi gọi `tryComplete` như thể child đã thành công** nếu dữ liệu của child chưa hợp lệ; điều đó có thể khiến root hoàn tất bình thường với kết quả sai.

## 23. Ví dụ Java 17+: exception từ `compute` có thể hoàn tất task bất thường

Lưu thành `ExceptionalCountedCompleterDemo.java`:

```java
import java.util.concurrent.CountedCompleter;
import java.util.concurrent.ForkJoinPool;

public class ExceptionalCountedCompleterDemo {
    static final class FailingTask extends CountedCompleter<Void> {
        @Override
        public void compute() {
            throw new IllegalStateException("bad input");
        }
    }

    public static void main(String[] args) {
        ForkJoinPool pool = new ForkJoinPool(2);
        FailingTask task = new FailingTask();

        try {
            boolean caughtExpected = false;
            try {
                pool.invoke(task);
            } catch (IllegalStateException e) {
                caughtExpected = true;
            }

            System.out.println("Caught exception: " + caughtExpected);
            System.out.println("Completed abnormally: "
                    + task.isCompletedAbnormally());
            System.out.println("Done: " + task.isDone());
        } finally {
            pool.shutdown();
        }
    }
}
```

```bash
javac ExceptionalCountedCompleterDemo.java
java ExceptionalCountedCompleterDemo
```

Stdout trên đường chạy bình thường:

```text
Caught exception: true
Completed abnormally: true
Done: true
```

**Vì sao không mâu thuẫn với tiêu đề?** Quy tắc "return khỏi compute chưa complete" nói về **normal return mà không có completion signal**. Ở ví dụ này, `compute` **không return bình thường** mà ném exception; Fork/Join ghi nhận abnormal completion. Đây là **một đường hoàn tất khác**, không phải cơ chế tự động hoàn tất normal CountedCompleter.

Không cần truyền `InterruptedException` trong ví dụ lỗi này; nó là `IllegalStateException` unchecked để làm nổi bật exceptional path.

## 24. Khi child có completer, vì sao `isDone()` riêng có thể không đáng tin?

Trong nhiều thuật toán CountedCompleter, child đơn giản:

```java
@Override
public void compute() {
    doWork();
    tryComplete();
}
```

Đây là snippet minh họa, với `doWork()` của ứng dụng. Khi child có completer:

1. `tryComplete` trên child thấy pending của child bằng 0, kích hoạt callback child.
2. Nó truyền tín hiệu lên parent và có thể giảm pending parent hoặc kích hoạt parent completion.
3. **Task status của child** có thể không được đánh dấu hoàn tất bình thường giống `RecursiveTask` trong khi root vẫn tiến.
4. Vì thế polling `child.isDone()` hoặc `child.join()` để xác nhận thuật toán đã hoàn tất dễ sai contract.

Root không có completer thì thường là **điểm chờ công bố kết quả**. Nếu muốn từng child thực sự có Future hoàn tất riêng, thiết kế có thể cần kiểu task khác hoặc dùng thao tác hoàn tất tường minh một cách có chủ đích; đừng vô tình trộn hai mô hình.

**Quan sát pending và task status khác nhau:** pending field có thể về 0 nhưng child chưa được mark done, và điều này không nhất thiết là lỗi nếu root protocol tiến triển đúng.

## 25. `firstComplete()`, `nextComplete()` và completion traversal

Ngoài `tryComplete`, `CountedCompleter` hỗ trợ:

- `firstComplete()`: khi pending khác 0, giảm count và trả `null`; nếu pending bằng 0, trả chính task để bắt đầu một completion traversal.
- `nextComplete()`: tiến lên completer, có thể giảm pending của parent hoặc trả parent khi đã đến điều kiện hoàn tất; ở root, xử lý việc đánh dấu hoàn tất.
- `getRoot()`: lấy root của completion chain.
- `helpComplete(maxTasks)`: hỗ trợ thực thi một số task trong đường completion khi có thể.

Những API này hữu ích cho thuật toán tùy biến, nhưng khó dùng đúng hơn `tryComplete` đối với người mới. Nếu không cần traversal riêng, hãy ưu tiên **protocol rõ ràng với pending count và một signal cuối mỗi đường thành công**.

Không thay `tryComplete` bằng `firstComplete` riêng lẻ rồi quên `nextComplete`; việc tự điều khiển traversal yêu cầu hiểu chính xác những callback nào phải chạy và root được mark done lúc nào.

## 26. Những lỗi thường gặp

**1. "`compute()` return là task complete."** Sai với normal completion của `CountedCompleter` nếu thiếu completion signal.

**2. "`pendingCount=0` nghĩa `join()` chắc chắn trả."** Sai. Count có thể bằng 0 nhưng chưa có lời gọi quan sát 0 để kích hoạt completion.

**3. "`fork()` tự đăng ký và giảm pending."** Sai. CountedCompleter không tự ghi nhớ danh tính và trạng thái các child theo kiểu đếm này.

**4. "Hai child thì luôn `setPendingCount(2)`."** Không. Nếu parent cũng `tryComplete`, count 2 hợp lý; nếu chỉ hai child gửi tín hiệu, count 1 có thể đúng. Phải đếm signals.

**5. "Cứ gọi `tryComplete` ở mọi điểm cho chắc."** Sai. Dư signal có thể hoàn tất sớm khi data chưa sẵn sàng.

**6. "`tryComplete` khi pending=1 hoàn tất node ngay."** Sai. Nó giảm 1 xuống 0; tín hiệu sau mới kích hoạt `onCompletion`.

**7. "`onCompletion` chạy khi bất cứ child nào xong."** Sai. Nó chạy khi completion protocol xác định đủ tín hiệu (hoặc có explicit `complete`), không phải callback riêng cho mỗi child bất kỳ.

**8. "`onCompletion` chắc chắn chạy trên thread parent."** Sai. Thread gửi tín hiệu cuối có thể là một worker khác.

**9. "`propagateCompletion` cũng thực thi `onCompletion`."** Sai. Nó bỏ qua hook này.

**10. "`complete(null)` chỉ hoạt động khi pending đã 0."** Sai. `complete` bỏ qua pending count; dùng sai có thể báo hoàn tất quá sớm.

**11. "`quietlyCompleteRoot` tự dừng mọi child."** Sai. Nó đánh dấu root complete; cancellation/cleanup của child khác là việc riêng.

**12. "`child.join()` tương đương chờ child `compute` return."** Không được suy như vậy với CountedCompleter có completer; child status có thể mang tính tùy ý.

**13. "Child ném exception thì root vẫn phải đợi normal signals mãi."** Exceptional completion có đường truyền riêng qua `onExceptionalCompletion` khi protocol thiết kế đúng.

**14. "Cứ tăng số thread trong ForkJoinPool sẽ sửa task bị treo."** Không. Nếu thiếu tín hiệu completion, thêm worker không tự tạo tín hiệu đó.

**15. "`getRawResult` mặc định tự lưu biến được truyền vào `complete(T)`."** Không. CountedCompleter mặc định trả null; cần override để trả kết quả thực sự.

**16. "Tất cả child results đều tự động thread-safe vì cùng ForkJoinPool."** Sai. Ownership và completion protocol đúng mới cho phép truy cập an toàn ở ranh giới cần thiết.

**17. "Một root có `isDone` true đồng nghĩa mọi child đều đã dừng."** Không nếu thuật toán chủ động early complete; phải đọc contract của ứng dụng.

**18. "Đo thời gian sleep sẽ kiểm chứng completion."** Không. Dùng root `get(timeout)`, latch hoặc completion state có nghĩa, không dựa vào delay tùy ý.

## 27. Cách debug khi `pool.invoke(root)` hoặc `root.join()` bị kẹt

Nếu root không về, kiểm tra theo thứ tự:

1. **Root có gọi completion signal không?** Nếu `compute` fork child rồi return, root có đang chờ child và đã hạch toán đúng parent signal?
2. **Mọi leaf thành công có gọi `tryComplete()/propagateCompletion()` không?** Có nhánh `return` sớm quên signal?
3. **`setPendingCount` có được thực hiện trước `fork` không?** Nếu child chạy nhanh trước khi count set, có race làm đếm sai.
4. **Count đang mô hình số tín hiệu nào?** Parent có gửi signal không, child có bao nhiêu signal, count ban đầu là mấy?
5. **Có thừa/thiếu completion signal ở nhánh lỗi?** Exception có được propagate, hay bị catch rồi bỏ quên?
6. **Có ai gọi `complete/quietlyCompleteRoot` sớm?** Nếu có, root có thể báo done trong khi dữ liệu chưa hợp lệ.
7. **Có vòng chờ với monitor/lock không?** Parent giữ lock rồi chờ task cần lock đó dễ deadlock.
8. **Có blocking I/O bên trong worker không?** Pool có thể bị thiếu worker tiến triển nếu task block lâu.
9. **Có đang join task con thay vì root không?** Child status không nhất thiết là completion marker phù hợp.
10. **Có thử tăng parallelism để che bug không?** Thử với pool nhỏ và case deterministic, nhưng sửa contract chứ không chỉ tăng thread.
11. **Dữ liệu gộp được ghi trước signal chưa?** Nếu ghi sau signal, parent có thể gộp dữ liệu chưa sẵn.
12. **Có tự thay pending count ở nhiều thread không kiểm soát không?** Method là atomic nhưng logic tổng thể vẫn phải đúng.

Thread dump có thể cho thấy worker đang chờ, nhưng **nó không trực tiếp chỉ ra tín hiệu completion nào bị quên**. Kết hợp counters ở leaf, số signal dự kiến, `root.getPendingCount()`, callbacks và `get(timeout)` để phân tích.

## 28. Khi nào nên dùng `CountedCompleter` thay vì `RecursiveTask`?

`CountedCompleter` hữu ích khi:

- Có nhiều subtask chỉ cần **báo hoàn tất theo cây** mà parent không cần chờ từng child bằng `join`.
- Có fan-out/fan-in lớn, kết quả được gộp qua completion action.
- Một số thuật toán có thể **kết thúc sớm** khi tìm được một kết quả chấp nhận được.
- Cần traversal hoặc completion dependency phức tạp mà mô hình fork/join thuần gây nhiều blocking joins.
- Có thể chứng minh chính xác **count/signals/ownership** của mọi đường thành công và lỗi.

Nhưng nó **khó dùng hơn `RecursiveTask`** vì người viết phải tự đảm bảo pending protocol. Nếu chỉ tính tổng một mảng, `RecursiveTask<Long>` với `left.fork(); right.compute(); left.join()` thường dễ đọc và dễ review hơn.

Đừng chọn `CountedCompleter` chỉ vì muốn tránh chữ `join` hoặc vì nghe "nhanh hơn". Chi phí và lợi ích phụ thuộc cây dữ liệu, kích thước leaf, work-stealing, contention và thuật toán thực tế.

## 29. Câu hỏi tự kiểm tra

**Câu 1:** `CountedCompleter.compute()` trả về bình thường nhưng không gọi completion method. `isDone()` của root có chắc true không?

**Không.** Không có cơ chế tự động hoàn tất normal CountedCompleter chỉ từ return; root có thể vẫn chưa done.

**Câu 2:** `pendingCount` ban đầu là 2, hai lần `tryComplete()` được gọi trên cùng node. Node có bắt buộc complete chưa?

**Chưa.** Hai lời gọi có thể chỉ giảm 2→1→0. Lời gọi tiếp theo thấy 0 mới kích hoạt `onCompletion`.

**Câu 3:** Hai child được fork và parent cũng có một `tryComplete` sau khi fork. Pending của parent nên đặt mấy theo chiến lược đơn giản này?

**2**, tương ứng tổng ba completion signals (parent + hai child); tín hiệu cuối quan sát 0.

**Câu 4:** Parent fork right và tính left trực tiếp; cả hai child đều gửi signal, parent không gửi signal riêng. Pending nên đặt bao nhiêu?

**1**, để có hai signals: một giảm về 0 và một kích hoạt completion.

**Câu 5:** `getPendingCount()==0` có chứng minh `root.join()` sẽ trả không?

**Không.** Đã có thể giảm về 0 mà chưa có completion action; phải xem trạng thái root và protocol còn thiếu tín hiệu không.

**Câu 6:** Vì sao không nên `join()` trên mọi child trong một CountedCompleter tree?

Vì internal CountedCompleter có completer thường chỉ là helper; task status riêng của chúng có thể không được đánh dấu hoàn tất như `RecursiveTask`. Root completion là điểm chờ đáng tin theo thiết kế.

**Câu 7:** `propagateCompletion` phù hợp khi nào?

Khi không cần `onCompletion` để gộp kết quả; nó truyền completion nhưng bỏ qua callback, miễn tín hiệu được đếm đúng.

**Câu 8:** Nếu child cần trả result, nên đặt logic gộp ở đâu?

Thường ở `onCompletion` của parent, sau khi completion protocol xác nhận mọi child result cần thiết đã sẵn sàng. Với root result, override `getRawResult` phù hợp.

**Câu 9:** `complete(T)` có đợi pendingCount về 0 không?

**Không.** Nó hoàn tất tường minh bất kể count; phải chỉ dùng khi contract cho phép kết thúc theo cách đó.

**Câu 10:** Child đã ném exception trong `compute`, có thể coi là normal signal không?

Không. Exceptional completion có cơ chế riêng và có thể propagate qua `onExceptionalCompletion`; không biến exception thành normal result giả.

**Câu 11:** Tăng `ForkJoinPool` từ 2 lên 32 worker có sửa lỗi thiếu `tryComplete` không?

Không. Thiếu tín hiệu là lỗi logic, không phải thiếu worker.

**Câu 12:** Vì sao `onCompletion` có thể chạy trên thread khác với `compute` của parent?

Vì tín hiệu cuối có thể do child đang chạy ở một worker khác gửi vào completion chain.

## 30. Checklist trước khi đưa vào production

1. **Định nghĩa root và completer tree rõ ràng.** Task nào là root không có completer, task nào là helper?
2. **Ghi cụ thể số signal sẽ đến từng node.** Parent có tự signal không, mỗi child có signal không?
3. **Đặt pending count trước khi fork child.** Tránh child hoàn tất quá nhanh trước khi count được cấu hình.
4. **Mọi đường hoàn tất bình thường đều gửi tín hiệu đúng số lần.** Không quên nhánh early return.
5. **Không double signal.** Thừa signal có thể hoàn tất sớm và làm callback đọc dữ liệu chưa sẵn.
6. **Nếu có result, ghi dữ liệu trước signal.** Parent đọc khi completion protocol đủ tín hiệu.
7. **Chọn `tryComplete` hay `propagateCompletion` có chủ ý.** Đừng bỏ callback combine vì đổi API tùy tiện.
8. **Dùng `onCompletion` để gộp khi có đầy đủ dependency.** Không dựa vào thứ tự thread chạy.
9. **Root là điểm chờ công bố kết quả.** Đừng mặc định child `isDone/join` tương đương completion signal.
10. **Exception và cancellation được định nghĩa riêng.** Không biến partial failure thành normal completion.
11. **Không tự sửa bằng `complete(null)` không kiểm chứng.** Explicit completion có thể phá điều kiện chờ đủ child.
12. **Không đợi task trong khi giữ monitor cần thiết cho chính task đó.** Tránh deadlock do vòng chờ lock.
13. **Đặt timeout cho test lỗi protocol.** `root.get(timeout)` giúp tránh test treo mãi nếu task thiếu tín hiệu.
14. **Đo lường task size và overhead.** CountedCompleter không giúp một thuật toán chia quá nhỏ tự nhanh.
15. **Benchmark so với `RecursiveTask` đơn giản.** Chọn công cụ có lợi ích thực sự.
16. **Quản lý lifecycle ForkJoinPool riêng.** `shutdown` nếu sở hữu pool; không shutdown shared common pool.
17. **Đọc lại Javadoc API của phiên bản Java dùng.** Đừng dựa vào giả định "compute return == complete" từ task type khác.

## 31. Tổng kết

- **`CountedCompleter.compute()` return không đồng nghĩa task complete.** Thiết kế của lớp này cho phép parent fork child rồi trả về trong khi completion còn được điều phối.
- **`pendingCount` là bộ đếm completion signals**, không phải số child hoặc số worker được quản lý tự động.
- **`tryComplete()` khi count > 0 chỉ giảm count**; khi count đã bằng 0, một tín hiệu mới gọi `onCompletion` và truyền lên completer.
- **`getPendingCount()==0` không đủ để kết luận `root.isDone()==true`**.
- **`propagateCompletion()`** giữ cơ chế tín hiệu nhưng bỏ qua `onCompletion`; không dùng cho reduction cần callback gộp result.
- **`complete(T)`** có thể hoàn tất tường minh bất kể pending; dùng sai có thể báo kết quả quá sớm.
- **Internal CountedCompleter có completer không nhất thiết có task status hợp lý để join riêng**; hãy thiết kế lấy kết quả/chờ ở root theo contract.
- **Mọi leaf phải gửi tín hiệu sau khi hoàn thành dữ liệu cần thiết**, và pending count phải đặt trước khi fork.
- **Exception/cancellation là đường hoàn tất khác**, không được tự đánh đồng với normal signals.
- **Không cần fork nhiều hơn hoặc tăng số worker để sửa lỗi thiếu tín hiệu**; phải sửa completion protocol.

**Câu hỏi then chốt khi review code:** *"Mỗi node đang chờ bao nhiêu completion signals, ai sẽ gửi chúng, và lời gọi nào cuối cùng quan sát pending bằng 0 để đánh dấu root hoàn tất?"* Nếu không trả lời được chính xác, việc `compute()` return rất có thể chỉ có nghĩa **một worker đã xong phần thân method**, chứ chưa có nghĩa toàn bộ CountedCompleter computation đã hoàn thành.

**Tham khảo API:** [Java SE 17 — CountedCompleter Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountedCompleter.html).
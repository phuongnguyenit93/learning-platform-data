# CountedCompleter: mục đích và khác biệt với RecursiveTask, RecursiveAction

**`CountedCompleter<T>`** là một loại `ForkJoinTask<T>` trong `java.util.concurrent`, được thiết kế cho công việc có **quan hệ hoàn tất phụ thuộc nhiều tác vụ con**. Thay vì mỗi parent task phải gọi `join()` để đợi từng child, nó sử dụng **pending count**, liên kết **completer** (thường trỏ về parent) và các phương thức **`tryComplete()` / `onCompletion()`** để kích hoạt xử lý khi các nhánh liên quan đã báo xong.

Điều đó khiến `CountedCompleter` hữu ích với các phép duyệt/phân rã dữ liệu lớn, thao tác độc lập trên từng phần tử, tác vụ có thời gian xử lý chênh lệch, tổng hợp kết quả và những cấu trúc hoàn tất dạng cây hoặc đồ thị. Đổi lại, **giao thức đếm completion phức tạp hơn đáng kể** so với `RecursiveTask` và `RecursiveAction`: quên một lời báo hoàn tất, đặt sai pending count hoặc thiếu đồng bộ cho dữ liệu chung có thể khiến root không bao giờ hoàn tất hoặc tổng hợp sai.

Bài này tập trung vào **Java concurrency nói chung**, sử dụng API JDK 17+, không phụ thuộc Spring. Ví dụ đều phân biệt rõ chương trình chạy độc lập với snippet giải thích thuật toán.

## 1. Nhắc lại Fork/Join

`ForkJoinPool` là executor hướng tới **công việc có thể chia nhỏ**. Một tác vụ đang chạy có thể fork nhiều subtasks; các worker dùng cơ chế *work stealing* để tận dụng các nhánh còn chờ trên các deque. Ba loại `ForkJoinTask` quan trọng:

- **`RecursiveTask<V>`**: chia nhỏ tính toán **có kết quả kiểu V**, thường `fork()` child, `join()` để lấy kết quả rồi combine.
- **`RecursiveAction`**: chia nhỏ **công việc không có kết quả trả về qua Task**, thường `invokeAll(...)` hoặc `fork/join`; side effects phải được thiết kế thread-safe.
- **`CountedCompleter<T>`**: **completion-driven**; các node báo hoàn tất bằng `tryComplete()` để một chuỗi completer biết khi nào nên `onCompletion()` và đánh dấu root hoàn tất. Nó có thể trả kết quả nhưng thường dùng với `CountedCompleter<Void>` và state/output bên ngoài.

### Ví dụ tư duy: tổng các đoạn của mảng

```text
                 [0..8) root
                    /    \
               [0..4)    [4..8)
               /   \       /   \
             [0..2)[2..4) [4..6)[6..8)
```

Với `RecursiveTask<Integer>`, mỗi node có thể chờ `join()` của child và cộng hai kết quả. Với `RecursiveAction`, mỗi leaf cập nhật một cấu trúc kết quả được đồng bộ (ví dụ `AtomicInteger`) rồi các parent chỉ chờ children kết thúc. Với `CountedCompleter`, một node có thể **fork children và return khỏi `compute()` ngay**, nhưng **completion của root chưa được công bố** cho caller cho đến khi đủ tín hiệu `tryComplete()` đi ngược cây.

**Return khỏi `compute()` không nhất thiết là task đã hoàn thành theo `ForkJoinTask.isDone()`**. Đây là khác biệt lớn cần ghi nhớ.

## 2. Bảng so sánh ba loại task

| Tiêu chí | `RecursiveTask<V>` | `RecursiveAction` | `CountedCompleter<T>` |
| --- | --- | --- | --- |
| Kế thừa | `ForkJoinTask<V>` | `ForkJoinTask<Void>` | `ForkJoinTask<T>` |
| Method chính phải implement | `protected V compute()` | `protected void compute()` | `public void compute()` |
| Mục tiêu phổ biến | Tính toán trả một kết quả | Biến đổi/duyệt không trả qua Task | Điều phối completion của nhiều nhánh |
| Cách đợi subtasks điển hình | `fork` rồi `join`, hoặc `invokeAll` | `invokeAll` / `join` | **Pending count + `tryComplete`**, không cần join từng child |
| Cách lấy kết quả | Giá trị trả từ `compute` | Side effect/output bên ngoài | `getRawResult()` override hoặc state ngoài; mặc định thường `null` |
| Logic khi các nhánh kết thúc | Parent sau `join` tự combine | Parent sau `join`/`invokeAll` tiếp tục | `onCompletion(caller)` được kích hoạt khi pending count đạt điều kiện |
| Trạng thái child | Child `join` có ý nghĩa trực tiếp | Child `join` có ý nghĩa trực tiếp | **Child nội bộ có completer** thường không nên dùng `join`/`isDone` như root |
| Mức khó | Dễ đọc, dễ review với divide-and-conquer thông thường | Dễ dùng nếu tác vụ độc lập | Dễ sai pending count, caller, result publication |
| Trường hợp nên chọn | Merge sort, sum, max, tree reduction | Apply transformation từng phần tử | Completion trees, completion triggers, custom traversal, irregular workloads |

**Không có lựa chọn “nhanh nhất trong mọi trường hợp”**. `CountedCompleter` tránh việc mỗi parent phải chờ child theo lối `join` thông thường; nhưng bookkeeping cũng có overhead. Workload đơn giản, tree nhỏ hoặc cần kết quả trực tiếp thường dễ bảo trì hơn với `RecursiveTask`.

## 3. Constructor, completer và pending count

`CountedCompleter` có thể được tạo bằng:

```java
super();                   // Không có completer, pending = 0.
super(parent);             // Có completer, pending = 0.
super(parent, initial);    // Có completer, pending = initial.
```

Đây là snippet nằm trong constructor lớp con, `parent` là `CountedCompleter<?>` và `initial` là `int` không âm theo protocol đang thiết kế. **Completer** là task sẽ nhận propagation khi node hiện tại đủ điều kiện hoàn tất, thường là node parent trong cây.

Các thao tác đếm:

- `getPendingCount()`: đọc số pending hiện tại của node.
- `setPendingCount(n)`: đặt số pending theo thiết kế của node.
- `addToPendingCount(delta)`: cộng pending theo cách atomic.
- `compareAndSetPendingCount(expected, update)`: CAS pending count.
- `decrementPendingCountUnlessZero()`: giảm nếu nonzero, trả giá trị trước thao tác.
- `tryComplete()`: nếu pending nonzero, giảm rồi dừng; nếu pending **đang bằng zero**, gọi `onCompletion` cho node này và tiếp tục thử hoàn tất completer, cuối cùng đánh dấu root hoàn tất.
- `propagateCompletion()`: tương tự `tryComplete` nhưng **không gọi `onCompletion`** ở các node đi qua.
- `firstComplete()` / `nextComplete()`: hỗ trợ traversal tùy biến sau khi completion đủ điều kiện.
- `quietlyCompleteRoot()`: đánh dấu root hoàn tất không cần toàn bộ child đã báo xong, hữu ích trong các thuật toán tìm kiếm trả sớm được thiết kế cẩn thận.
- `complete(value)`: ép hoàn tất node này **không phụ thuộc pending count**, có chạy `onCompletion` và propagates tới completer. Không phải thay thế chung cho `tryComplete`.

**Pending count không chứa danh tính children.** Nó là **bộ đếm tín hiệu chưa đủ**, không phải `List<ForkJoinTask<?>>`. Nếu cần lấy kết quả của từng child, programmer phải tự giữ tham chiếu/state phù hợp.

## 4. Hiểu chính xác `tryComplete()`

Có thể nhớ cơ chế lõi bằng pseudocode:

```text
tryComplete(node, caller):
    if node.pending > 0:
        atomically decrement pending
        stop
    else:
        node.onCompletion(caller)
        if node.completer exists:
            move to node.completer (caller becomes previous node)
            repeat
        else:
            mark root as completed
```

Đây là **pseudocode giải thích**, không phải mã Java/JDK source được sao chép. Điều dễ gây bất ngờ: **nếu pending đang là 1 và bạn gọi `tryComplete()`, count trở thành 0 nhưng callback chưa chạy trong chính lời gọi ấy**. Một lần `tryComplete()` **tiếp theo** thấy pending đã là zero mới kích hoạt `onCompletion`.

### Ví dụ: parent có hai children

Một lựa chọn dễ kiểm tra là:

```java
setPendingCount(2);
new Node(this, leftRange).fork();
new Node(this, rightRange).fork();
tryComplete(); // Parent báo "phần việc của tôi đã xong".
```

Đây là snippet trong `compute()` của `Node extends CountedCompleter<Void>`, các constructor/method phụ thuộc lớp. Có **ba đường báo hoàn tất** vào parent: parent tự báo sau fork, left báo, right báo. Pending bắt đầu 2:

```text
Kịch bản một thứ tự có thể xảy ra:
    pending = 2
    parent.tryComplete(): 2 -> 1
    left completes:       1 -> 0
    right completes:      0 => onCompletion(parent), propagate upward

Hoặc children hoàn tất trước parent:
    pending = 2
    left completes:       2 -> 1
    right completes:      1 -> 0
    parent.tryComplete(): 0 => onCompletion(parent), propagate upward
```

**Trong cả hai thứ tự, parent được complete đúng một lần theo protocol**, miễn là mỗi node báo một lần, pending được đặt đúng và không có lỗi bất thường phá completion. **Không suy ra node nào chắc chắn là caller cuối cùng**: callback `onCompletion(caller)` có thể được kích hoạt từ parent tự báo hoặc từ child, tùy interleaving.

**Đặt pending trước khi fork.** Nếu fork children trước rồi mới set pending, child có thể chạy xong và báo completion khi parent chưa đăng ký dependency, dẫn tới complete quá sớm hoặc trạng thái sai.

### Vì sao JDK đôi khi dùng pending = 1 cho hai nửa?

Một optimization trong Javadoc: parent fork một child, còn nửa kia **được compute trực tiếp trên current worker** (không tạo một parent callback `tryComplete` độc lập). Khi đó count và số lần báo completion khác công thức đơn giản `setPendingCount(2)`. Đoạn ví dụ tối ưu có thể trông “lệch một”, nhưng đúng khi phân tích **tất cả đường tryComplete thật sự xảy ra**. Đừng copy số pending từ bài toán khác mà không đếm arrivals.

## 5. Điều gì xảy ra khi `compute()` return?

Đối với `RecursiveTask`, `compute()` trả về kết quả; ForkJoinTask thường chuyển task sang trạng thái hoàn tất theo execution protocol. Với `RecursiveAction`, return cũng gắn với hoàn tất body, và parent thường join children trước khi return.

Với `CountedCompleter`, `compute()` **có thể chỉ tạo một số children và return**. Root vẫn còn đợi completion propagation; khi pending count chưa được xử lý đúng, một lời gọi `pool.invoke(root)` hay `root.join()` có thể **chờ mãi** dù mọi `compute()` đều đã return.

### Sai lầm minh họa

```java
class Broken extends CountedCompleter<Void> {
    @Override
    public void compute() {
        doWork();
        // BUG: không báo tryComplete() hoặc equivalent completion.
    }
}
```

Đây là **snippet chưa đủ class/method**, không chạy độc lập. `ForkJoinPool.invoke(new Broken())` có thể chờ vô hạn vì root không được đánh dấu hoàn tất. `compute()` return **không** đồng nghĩa `CountedCompleter` complete.

Đúng về mặt nguyên tắc:

```java
@Override
public void compute() {
    doWork();
    tryComplete();
}
```

Đây vẫn là snippet, `doWork` phải tuân thủ xử lý exception/cancellation. Với node có children, **đặt pending chính xác trước fork**; `tryComplete` ở cuối chỉ báo phần việc hiện tại hoàn thành, chưa nhất thiết đánh dấu node/root ngay.

## 6. Java 17: cùng một phép tính với ba loại ForkJoinTask

Chương trình sau tính tổng mảng `{1,2,3,4,5,6,7,8}` bằng ba cách:

1. `RecursiveTask<Integer>`: mỗi parent join kết quả children và cộng.
2. `RecursiveAction`: cập nhật `AtomicInteger` bên ngoài, dùng `invokeAll` để hoàn tất children.
3. `CountedCompleter<Integer>`: các leaves đóng góp vào `AtomicInteger`; parent dùng pending + `tryComplete`, không gọi join children, root override `getRawResult` để trả tổng sau completion.

Tạo tệp **`ForkJoinThreeWays.java`**:

```java
import java.util.concurrent.CountedCompleter;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveAction;
import java.util.concurrent.RecursiveTask;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class ForkJoinThreeWays {
    static final class SumTask extends RecursiveTask<Integer> {
        private final int[] data;
        private final int lo, hi;

        SumTask(int[] data, int lo, int hi) {
            this.data = data;
            this.lo = lo;
            this.hi = hi;
        }

        @Override
        protected Integer compute() {
            if (hi - lo <= 2) {
                int result = 0;
                for (int i = lo; i < hi; i++) result += data[i];
                return result;
            }

            int mid = (lo + hi) >>> 1;
            SumTask left = new SumTask(data, lo, mid);
            SumTask right = new SumTask(data, mid, hi);
            left.fork();
            int rightResult = right.compute();
            return left.join() + rightResult;
        }
    }

    static final class SumAction extends RecursiveAction {
        private final int[] data;
        private final int lo, hi;
        private final AtomicInteger total;

        SumAction(int[] data, int lo, int hi,
                  AtomicInteger total) {
            this.data = data;
            this.lo = lo;
            this.hi = hi;
            this.total = total;
        }

        @Override
        protected void compute() {
            if (hi - lo <= 2) {
                for (int i = lo; i < hi; i++) {
                    total.addAndGet(data[i]);
                }
                return;
            }

            int mid = (lo + hi) >>> 1;
            invokeAll(
                    new SumAction(data, lo, mid, total),
                    new SumAction(data, mid, hi, total));
        }
    }

    static final class SumCompleter
            extends CountedCompleter<Integer> {
        private final int[] data;
        private final int lo, hi;
        private final AtomicInteger total;

        SumCompleter(SumCompleter parent, int[] data,
                     int lo, int hi, AtomicInteger total) {
            super(parent);
            this.data = data;
            this.lo = lo;
            this.hi = hi;
            this.total = total;
        }

        @Override
        public void compute() {
            if (hi - lo > 2) {
                int mid = (lo + hi) >>> 1;
                setPendingCount(2);  // Register before forking.
                new SumCompleter(this, data, lo, mid, total).fork();
                new SumCompleter(this, data, mid, hi, total).fork();
            } else {
                for (int i = lo; i < hi; i++) {
                    total.addAndGet(data[i]);
                }
            }

            tryComplete(); // This node's own contribution is done.
        }

        @Override
        public Integer getRawResult() {
            return total.get();
        }
    }

    public static void main(String[] args) throws Exception {
        int[] data = {1, 2, 3, 4, 5, 6, 7, 8};
        ForkJoinPool pool = new ForkJoinPool(4);

        try {
            int viaTask =
                    pool.invoke(new SumTask(data, 0, data.length));

            AtomicInteger actionTotal = new AtomicInteger();
            pool.invoke(new SumAction(
                    data, 0, data.length, actionTotal));

            AtomicInteger completerTotal = new AtomicInteger();
            int viaCompleter = pool.invoke(new SumCompleter(
                    null, data, 0, data.length, completerTotal));

            System.out.println("RecursiveTask=" + viaTask);
            System.out.println("RecursiveAction=" + actionTotal.get());
            System.out.println("CountedCompleter=" + viaCompleter);
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
                throw new IllegalStateException("Pool not terminated");
            }
        }
    }
}
```

Biên dịch và chạy trên JDK 17+:

```bash
javac ForkJoinThreeWays.java
java ForkJoinThreeWays
```

Stdout khi chạy thành công:

```text
RecursiveTask=36
RecursiveAction=36
CountedCompleter=36
```

### Giải thích đúng semantics

- Với `SumTask`, parent thực sự **đợi kết quả** từ `left.join()` rồi cộng với nửa phải tính trực tiếp. Task trả kết quả qua `compute()`.
- Với `SumAction`, `invokeAll` đảm bảo các children hoàn thành; `AtomicInteger` bảo vệ tổng chia sẻ. `RecursiveAction` không truyền tổng qua return value.
- Với `SumCompleter`, parent đăng ký **2 pending arrivals trước khi fork**. Parent tự gọi `tryComplete()` khi xong phần việc fork; từng child khi hoàn tất sẽ truyền tín hiệu ngược cây. Khi root hoàn tất, tổng atomic đã nhận mọi phần tử; `getRawResult()` trả tổng.
- `CountedCompleter<Integer>` ở đây không dùng giá trị `return` trong `compute()` (method là `void`). **Override `getRawResult()`** để `pool.invoke(root)` nhận được kết quả; theo JDK, `setRawResult` mặc định không tự lưu giá trị.
- `AtomicInteger` trong hai nhánh Action/Completer là lựa chọn **đơn giản để minh họa completion**, không chứng minh đây là cách sum nhanh nhất. Với mảng rất lớn, hotspot trên atomic total có thể ảnh hưởng hiệu năng; một reducer per-branch thường tốt hơn nếu cần tối ưu.

**Điểm nhấn:** cùng đáp án 36 nhưng cách xác định **khi nào công việc kết thúc** khác nhau. Với `CountedCompleter`, **`compute()` của root return trước children là hoàn toàn hợp lệ**, còn `pool.invoke(root)` vẫn chỉ trở về khi root được completion protocol đánh dấu xong.

## 7. `onCompletion(caller)` dùng để làm gì?

Method:

```java
@Override
public void onCompletion(CountedCompleter<?> caller) {
    // Combine results, record a completion, release a stage...
}
```

là snippet trong lớp con `CountedCompleter`. Callback chạy khi một đường `tryComplete()` thấy pending count của node **đã bằng zero**, hoặc khi `complete(value)` được gọi theo contract. Mặc định nó không làm gì.

Các ứng dụng thường thấy:

- **Kết hợp dữ liệu của children** khi cả các nhánh có liên quan đã hoàn tất.
- **Chuyển từ giai đoạn map sang reduce** khi đã có đủ kết quả.
- **Cập nhật trạng thái node parent** một lần để phục vụ completion propagation.
- **Kích hoạt phase tiếp theo** nếu thuật toán đã giải quyết đúng ownership, thứ tự, exception và side effects.

**Lưu ý:** tham số `caller` là task khiến traversal tới node này; nó có thể bằng `this` hoặc là một subtask. Với giao thức `setPendingCount(2)` + parent `tryComplete()` + hai children, **không thể dự đoán interleaving nào sẽ gọi callback**; không viết code mà chỉ xử lý kết quả khi `caller != this` trừ khi đã chứng minh điều kiện ấy từ protocol chính xác đang dùng.

## 8. Java 17: callback completion và tổng hợp cây, không join child

Ví dụ thứ hai giữ kết quả riêng trong từng node, không dùng một `AtomicInteger` để cộng tất cả phần tử. Mỗi node parent chỉ combine `left.value + right.value` trong `onCompletion`, khi **cả hai children đã báo hoàn tất**. Đây là dạng reducer cho phép hiểu việc CountedCompleter xử lý kết quả theo callback.

Tạo **`CountedCompleterReduceDemo.java`**:

```java
import java.util.concurrent.CountedCompleter;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class CountedCompleterReduceDemo {
    static final class SumNode extends CountedCompleter<Integer> {
        private final int[] data;
        private final int lo, hi;
        private final AtomicInteger callbacks;
        private SumNode left, right;
        private int value;

        SumNode(SumNode parent, int[] data, int lo, int hi,
                AtomicInteger callbacks) {
            super(parent);
            this.data = data;
            this.lo = lo;
            this.hi = hi;
            this.callbacks = callbacks;
        }

        @Override
        public void compute() {
            if (hi - lo <= 2) {
                int sum = 0;
                for (int i = lo; i < hi; i++) {
                    sum += data[i];
                }
                value = sum;
            } else {
                int mid = (lo + hi) >>> 1;
                left = new SumNode(this, data, lo, mid, callbacks);
                right = new SumNode(this, data, mid, hi, callbacks);

                setPendingCount(2);
                left.fork();
                right.fork();
            }

            tryComplete();
        }

        @Override
        public void onCompletion(CountedCompleter<?> caller) {
            if (left != null) {
                value = left.value + right.value;
            }
            callbacks.incrementAndGet();
        }

        @Override
        public Integer getRawResult() {
            return value;
        }
    }

    public static void main(String[] args) throws Exception {
        int[] data = {1, 2, 3, 4, 5, 6, 7, 8};
        AtomicInteger callbacks = new AtomicInteger();
        ForkJoinPool pool = new ForkJoinPool(4);
        SumNode root = new SumNode(
                null, data, 0, data.length, callbacks);

        try {
            int sum = pool.invoke(root);

            System.out.println("sum=" + sum);
            System.out.println("completionCallbacks="
                    + callbacks.get());
            System.out.println("rootPending="
                    + root.getPendingCount());
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
                throw new IllegalStateException("Pool not terminated");
            }
        }
    }
}
```

```bash
javac CountedCompleterReduceDemo.java
java CountedCompleterReduceDemo
```

Stdout khi chạy bình thường:

```text
sum=36
completionCallbacks=7
rootPending=0
```

**Vì sao 7 callbacks?** Mảng có 8 phần tử, threshold leaf size 2 ⇒ cây nhị phân có **4 leaves + 2 node trung gian + 1 root = 7 nodes**. Mỗi node đi qua `onCompletion` đúng một lần theo giao thức pending của ví dụ; callback của parent cộng hai giá trị children sau khi chúng hoàn tất.

`caller` có thể khác nhau tùy thứ tự chạy, nhưng số node và tổng là xác định. Bài này **không in tên thread hoặc thứ tự callback** vì scheduler không cam kết chúng.

**Quan trọng về memory semantics:** Dữ liệu `left/right/value` ở đây thuộc mỗi node, được ghi trước khi nhánh báo hoàn tất qua giao thức CountedCompleter. Javadoc mô tả rằng khi dùng pending counts đúng, `onCompletion` có thể truy cập các field của các subtasks đã hoàn tất mà không cần thêm đồng bộ riêng cho việc combine này. Điều đó **không** cho phép sửa `value` đồng thời ở code khác ngoài protocol; callback phải đi theo cây completion đã thiết kế.

**Khi dữ liệu có thứ tự:** `left.value + right.value` là phép cộng giao hoán, nên dễ kiểm chứng. Nếu kết quả cần thứ tự như nối chuỗi, serialize, hoặc sắp xếp, hãy dùng vị trí `left/right` rõ ràng và combine theo đúng thứ tự nghiệp vụ, **không dựa vào task nào xong trước**.

## 9. Cây completion có phải CountDownLatch không?

Cả `CountDownLatch` và pending count của `CountedCompleter` đều sử dụng tư duy “chờ đủ tín hiệu”. Nhưng khác nhau:

| `CountDownLatch` | `CountedCompleter` |
| --- | --- |
| Một object latch độc lập, caller có thể `await()` | Một `ForkJoinTask` với completer chain |
| `countDown` làm giảm số đếm tới 0 | `tryComplete` có thể giảm pending hoặc gọi callback/propagate khi count **đang** bằng 0 |
| Caller có thể block chờ điều kiện | Completion của node có thể được kích hoạt bởi thread đang hoàn tất child |
| Không tự phân rã task tree | Task có thể fork children và quản lý completion |
| Không tự combine result | `onCompletion` có thể combine |
| Một lần mở latch rồi tồn tại mở | Mỗi CountedCompleter node có một protocol completion riêng |

**Không thay thế `CountDownLatch(2)` bằng `setPendingCount(2)` một cách máy móc.** Pending count trong CountedCompleter thường **phải tính cả `tryComplete` của node parent** nếu node parent cũng báo một lần; vì vậy số ban đầu thể hiện **số lượt giảm trước khi đến lượt kích hoạt callback**, không đơn thuần là “còn 2 con chưa xong”.

## 10. `propagateCompletion()` và chi phí callback

Khi không cần `onCompletion` ở các node, có thể dùng:

```java
propagateCompletion();
```

trong một implementation CountedCompleter. Nó tương tự `tryComplete` về pending decrement và propagation tới root, nhưng **bỏ qua callbacks `onCompletion`** trên đường đi. Đây là lựa chọn hợp lý cho một số tác vụ **for-each side-effect** không cần combine tại parent.

**Không dùng `propagateCompletion` khi cần reduce trong `onCompletion`**. Nếu thay `tryComplete` bằng `propagateCompletion` trong `CountedCompleterReduceDemo`, các node parent sẽ không cộng kết quả con theo callback; tổng trả về có thể sai.

`firstComplete()/nextComplete()` dành cho thuật toán cần **completion traversal tùy chỉnh**. Chúng dùng pending counts để xác định node nào đã sẵn sàng; logic thực sự chạy bên trong vòng traversal do programmer viết. Cơ chế nâng cao này hữu ích cho reduce phức tạp nhưng khó review, nên không cần khi `onCompletion` đã diễn đạt được hành vi.

## 11. Kết quả trả về của CountedCompleter

Đối với `RecursiveTask<V>`:

```java
@Override
protected Integer compute() {
    return 42;
}
```

là snippet: ForkJoinTask nhận giá trị trực tiếp từ compute.

Đối với `CountedCompleter<T>`, method `compute()` là **`void`**. Thông thường các implementation dùng `CountedCompleter<Void>` và không trả kết quả qua task. Nếu muốn caller gọi `invoke()/join()` nhận giá trị, cần quản lý result state và **override `getRawResult()`**:

```java
private int result;

@Override
public Integer getRawResult() {
    return result;
}
```

Đây là snippet bên trong `CountedCompleter<Integer>`. Dữ liệu `result` phải được thiết lập đúng trước khi root được đánh dấu complete. **`setRawResult(T)` mặc định không đóng vai trò lưu giá trị** trong CountedCompleter. `complete(value)` không làm một object tự động biết cách trả value trừ khi result accessors được thiết kế đúng.

Khi chọn result API, hãy phân biệt:

- **Kết quả root**: khi `pool.invoke(root)` return, root có thể trả value phù hợp.
- **Kết quả subtask nội bộ**: child có completer, không nên đợi `join()` như mô hình RecursiveTask bình thường; theo Javadoc, status của child nội bộ **không được quản lý giống root** trừ khi có explicit completion/cancel/exception.
- **Side effects**: nếu kết quả được ghi vào array/map/shared accumulator, cần thiết kế atomicity/ownership và publication đúng, không mặc định mọi field mutable là thread-safe.

## 12. `getCompleter()`, `getRoot()` và cách ánh xạ parent

`getCompleter()` trả node completer gắn lúc tạo task; `getRoot()` đi theo chain cho tới node không có completer. Chúng có ý nghĩa **completion topology**.

Trong cây:

```text
root (completer=null)
  |
  +-- left (completer=root)
  |     +-- left-left (completer=left)
  |     +-- left-right (completer=left)
  |
  +-- right (completer=root)
```

Khi leaf gọi `tryComplete()` đúng protocol, nó có thể góp phần làm hoàn tất parent, grandparent và cuối cùng root. Chain này **không phải liên kết đợi kiểu `join`**, cũng không tự lưu reference ngược tới tất cả children. Trong reducer, chúng ta phải tự giữ `left`/`right` nếu muốn đọc từng kết quả.

Nếu bạn cần một dependency graph **không phải cây** (một node được nhiều công việc khác nhau kích hoạt), phải thiết kế arrivals, completion owner, cancellation, failure và các paths phù hợp. Không tự gán một child có hai completers: constructor chỉ thiết lập **một** completer link, dù có thể xây trigger object riêng để nhận nhiều arrivals.

## 13. Ngoại lệ và `onExceptionalCompletion`

Trong `RecursiveTask`, exception ở child có thể được quan sát khi caller `join()` nó. Với `CountedCompleter`, child nội bộ có thể báo exceptional completion **dọc completer chain** theo contract.

Có callback:

```java
@Override
public boolean onExceptionalCompletion(
        Throwable error, CountedCompleter<?> caller) {
    return true; // Cho phép propagation theo contract.
}
```

Đây là snippet trong subclass `CountedCompleter<?>`. Default implementation trả true; return false có thể ngăn propagation lên completer tiếp theo. Tuy nhiên một callback này **không tự rollback** những leaf đã hoàn tất, không đóng mọi tài nguyên, không hủy mọi subtasks đang chạy và không biến các side effects đã xảy ra thành transaction.

### Nếu một leaf ném exception

- Root có thể hoàn thành exceptional tùy cách propagation và trạng thái đã complete.
- Các sibling có thể đang chạy, chưa kịp nhìn thấy lỗi; **root exception không phải bằng chứng tất cả sibling đã dừng**.
- Nếu cần dừng sớm, hãy thiết kế shared cancellation flag, cooperative checks, hoặc cơ chế quản lý khác.
- Dùng `try/finally`/`try-with-resources` để cleanup resource thuộc từng leaf; không mong `onCompletion` bình thường được chạy trên mọi đường exceptional.
- Khi caller `invoke(root)`, cần xử lý exception theo contract của ForkJoinTask; lỗi unchecked có thể được bọc/lan truyền tùy API.
- Với kết quả nghiệp vụ quan trọng, ghi rõ chính sách partial results; một số leaf đã cập nhật shared state trước khi leaf khác thất bại.

**Không bắt `Throwable` rồi chỉ `tryComplete()` và im lặng tiếp tục** nếu bạn cần báo lỗi. Một lời báo completion bình thường có thể che sự thật rằng xử lý một partition đã thất bại.

## 14. Early termination: `quietlyCompleteRoot()`

Một số bài toán chỉ cần **một kết quả bất kỳ**: tìm phần tử đầu tiên phù hợp điều kiện theo nghĩa “một phần tử bất kỳ tìm thấy”, phát hiện sự tồn tại, hoặc kết thúc khi có winner.

Nếu một leaf tìm thấy kết quả và công bố nó an toàn qua `AtomicReference`, nó có thể đánh dấu root hoàn tất sớm bằng:

```java
if (found.compareAndSet(null, candidate)) {
    quietlyCompleteRoot();
}
```

Đây là snippet trong subclass `CountedCompleter`, `found` là `AtomicReference<T>`. **Không dùng cách này cho bài toán phải chạy hết toàn bộ leaves** như tổng và duyệt với side effects bắt buộc.

**Rất quan trọng:** root “đã complete” sớm **không đồng nghĩa tất cả sibling tasks đã dừng**. Các subtasks vẫn có thể chạy hoặc đã được queue. Chúng nên định kỳ đọc `found` hoặc cancellation state để bỏ qua công việc không còn cần, nhưng cần xử lý cleanup và lifecycle riêng.

Nếu bài toán đòi **phần tử đầu tiên theo thứ tự mảng** chứ không phải bất kỳ match nào, winner theo `compareAndSet(null, candidate)` có thể phụ thuộc scheduling; không thể gọi nó là “first by index” nếu không có logic so sánh vị trí.

`complete(value)` ép task complete bất kể pending count và kích hoạt callback/propagation khác `quietlyCompleteRoot`. Không dùng tùy tiện để “chữa” một root bị treo do đếm sai.

## 15. Vì sao CountedCompleter tránh một số dạng chờ?

Trong divide-and-conquer thông thường:

```java
left.fork();
int b = right.compute();
int a = left.join();
return a + b;
```

Parent worker có thể dành thời gian tại `join()`; ForkJoinPool có cơ chế hỗ trợ work stealing/helping nên không nên hiểu đó là một OS thread **luôn bị idle blocking**. Nhưng code parent vẫn được viết dưới dạng **wait for child result**.

Với CountedCompleter:

```java
setPendingCount(2);
left.fork();
right.fork();
tryComplete();
return; // Không join children.
```

Đây là snippet trong `compute()` của subclass CountedCompleter; `left/right` là subtasks có completer đúng. Worker chạy parent có thể chuyển sang thực thi task khác sau khi fork và return; **completion action** do một lời báo hoàn tất cuối cùng kích hoạt.

Điều này có thể hữu ích khi:
- Leaf tasks có thời gian chạy rất khác nhau.
- Kết quả có thể combine bằng callback trên completion.
- Một chuỗi processing stage nên được kích hoạt khi đủ arrivals.
- Task graph có nhiều nhánh mà việc chờ từng nhánh trong parent gây code kém linh hoạt.

**Không có bảo đảm CountedCompleter luôn nhanh hơn join.** Nó thêm số đếm, CAS, linkages và logic callback. Với tree cân bằng và tính toán thuần nhỏ, `RecursiveTask` thường dễ viết, dễ kiểm chứng và đủ nhanh.

## 16. Những lỗi điển hình của pending count

| Sai lầm | Hậu quả | Cách tránh |
| --- | --- | --- |
| Quên `tryComplete()` ở leaf | Root không nhận đủ tín hiệu, `invoke`/`join` treo | Mỗi đường normal completion phải có protocol rõ |
| Quên parent tự `tryComplete()` khi dùng `setPendingCount(2)` cho 2 children | Count có thể xuống 0 nhưng callback chưa chạy | Đếm đủ arrivals, include parent path |
| Fork child trước khi set pending | Child hoàn tất trước khi parent đăng ký | Đăng ký count trước fork |
| Đặt pending nhỏ hơn số arrivals thực | Parent complete quá sớm, kết quả thiếu | Kiểm tra số callers và timing |
| Đặt pending lớn hơn số arrivals | Callback/root không bao giờ đạt completion | Sơ đồ trạng thái và tests có timeout |
| Tưởng `setPendingCount(0)` làm task complete ngay | Pending 0 chưa gọi callback/complete | Cần đúng lời gọi `tryComplete`/protocol |
| Gọi `tryComplete` nhiều lần cho một completion | Callback sớm hoặc sai protocol | Mỗi arrival gửi một tín hiệu theo thiết kế |
| Đọc `getPendingCount()==0` rồi tự combine | Count 0 không đồng nghĩa callback đã được gọi | Dùng `onCompletion`/completion semantics |
| Dùng `propagateCompletion` trong reducer cần callback | Bỏ qua combine | `tryComplete` khi cần `onCompletion` |
| Dùng `join` các internal CountedCompleter children | Child status không theo mô hình root | Chờ root hoặc dùng result/trigger protocol |
| Root `compute` return mà không signal | Root không complete | Báo `tryComplete` đúng chỗ |
| Side effect external trong completion callback không idempotent | Lỗi khó khôi phục nếu exception/retry hệ thống | Ownership, transaction và policy rõ |
| Shared output là `ArrayList` unsynchronized | Data race/corruption | Immutable partition, concurrent structure, lock/atomic |
| Combine theo thứ tự child hoàn tất thay thứ tự logic | Kết quả sai với operation không giao hoán | Giữ left/right hoặc index cố định |
| Complete root sớm khi chưa đủ required results | Trả partial state | Chỉ early complete nếu hợp đồng cho phép |
| Phụ thuộc caller == child cố định | Interleaving thay đổi caller | Không dự đoán ai là last signal |

## 17. Granularity, threshold và hiệu năng

Fork/Join **không nên tạo một task cho mỗi phần tử** khi số phần tử rất lớn và thao tác quá nhỏ. Mỗi task/fork/pending update có overhead. Hãy chọn threshold để một leaf xử lý **một lô đủ lớn**:

- Với xử lý CPU thuần, threshold dựa trên kích thước dữ liệu, lượng CPU work mỗi phần tử, số cores.
- Với workloads có độ lệch lớn, chia nhỏ hơn có thể giúp work stealing nhưng tăng overhead.
- Với I/O blocking, ForkJoinPool thường không phải công cụ đầu tiên; một worker blocking có thể giảm năng lực xử lý, tùy cơ chế managed blocking và API.
- Với nhiều leaf cùng cập nhật một `AtomicInteger`, contention có thể gây bottleneck; cân nhắc per-subtask result + `onCompletion` như `CountedCompleterReduceDemo`.
- `ForkJoinPool.commonPool()` là tài nguyên dùng chung; đừng để task chặn rất lâu hoặc shutdown common pool theo cách gây ảnh hưởng phần khác. Với ví dụ cần cô lập, dùng `new ForkJoinPool(n)` và shutdown đúng.
- Đo throughput, p95/p99 và CPU theo các thresholds, core counts, input distributions; không suy ra tăng số subtasks luôn nhanh hơn.

### Work stealing không giải quyết mọi liveness bug

Nếu pending count sai, một worker có thể không làm gì nữa, còn root đang chờ một tín hiệu **sẽ không bao giờ xuất hiện**. Work stealing không tạo ra `tryComplete()` còn thiếu. Lập luận đúng completion protocol vẫn quan trọng hơn tuning pool.

## 18. Khi nào không nên chọn CountedCompleter?

Chọn `RecursiveTask` hoặc `RecursiveAction` nếu:

- Bài toán là divide-and-conquer rõ ràng và combine sau `join` dễ hiểu.
- Cây task nhỏ, kết quả từ child cần trực tiếp ở parent, không có pipeline completion phức tạp.
- Nhóm chưa có kinh nghiệm kiểm tra đúng pending counts và exception path.
- Yêu cầu maintenance/readability quan trọng hơn tối ưu callback-based scheduling.
- Cần semantics cancellation, exception hoặc structured ownership đơn giản hơn.

Chọn `CountedCompleter` nếu:

- Tác vụ phân rã và xử lý các nhánh bất quy tắc.
- Muốn **completion-driven callbacks** khi nhiều phần việc xong.
- Có thể thiết kế count rõ và không cần parent join từng child.
- Muốn reduce qua `onCompletion` hoặc custom completion traversal.
- Muốn early-exit theo winner được công bố an toàn (với xử lý orphan tasks đúng).
- Đang phát triển một thư viện/concurrent component mà throughput, complexity và progress được test kỹ.

**Đừng nhầm `CountedCompleter` với `CompletableFuture`:** CompletableFuture là một abstraction để biểu diễn/compose stages hoàn tất, thường dễ dùng hơn cho workflow async ở mức business; CountedCompleter là **ForkJoinTask primitive** để xây completion protocol cấp thấp với pending count và completer chain.

## 19. Tình huống áp dụng

### Duyệt mảng thực hiện action độc lập

Nếu mỗi phần tử cần được xử lý đúng một lần và không phải thu kết quả, dùng `CountedCompleter<Void>`, fork partitions và `tryComplete`. Tuy nhiên, với công việc nhỏ, `Arrays.parallelSetAll` hoặc stream phù hợp đôi khi đơn giản hơn; phải cân nhắc semantics.

### Cộng/ghép kết quả các partitions

Dùng `RecursiveTask` nếu phép combine ở parent dễ viết. Dùng `CountedCompleter` nếu muốn child completion kích hoạt `onCompletion` mà không bắt parent chờ `join`. Nếu combine không giao hoán, record thứ tự left/right.

### Tìm kiếm “một match bất kỳ”

Dùng `AtomicReference`/`AtomicInteger` để công bố winner và `quietlyCompleteRoot` nếu hợp đồng cho phép early completion. Các sibling cần tự kiểm tra state để dừng; root complete sớm không tự kill chúng.

### Pipeline completion

Một node có thể đại diện giai đoạn chỉ được kích hoạt sau một số nhánh upstream. CountedCompleter cung cấp primitive đếm arrivals, nhưng không tự cung cấp retry, durable messaging, exactly-once side effects hay backpressure. Với workflow nghiệp vụ phân tán, cần công cụ/transaction thích hợp.

## 20. Kiểm thử đúng đắn với nhiều interleavings

Một test chỉ chạy một lần và in đúng tổng không đủ chứng minh đúng trong mọi lịch. Khi review CountedCompleter, hãy test:

1. Input rỗng, một phần tử, hai phần tử, threshold boundary.
2. Nhiều kích thước lẻ/chẵn, depth khác nhau.
3. Thread pool có 1 worker, 2 workers và nhiều workers.
4. Child hoàn tất rất sớm trước khi parent `tryComplete`.
5. Parent `tryComplete` chạy trước tất cả children.
6. Một leaf ném exception; root không bị chờ mãi và lỗi được báo đúng.
7. Nhiều leaves cùng ghi shared state; kiểm tra memory visibility/atomicity.
8. Callback `onCompletion` có được gọi đúng một lần theo protocol không.
9. `propagateCompletion` có làm mất bước combine cần thiết không.
10. Early completion có làm sibling vẫn chạy/side effect dư không.
11. Cancellation/timeout/shutdown; root wait không treo vô hạn.
12. Performance khi threshold quá nhỏ hoặc skewed partitions.

### Thực hành test có deadline

```java
ForkJoinPool pool = new ForkJoinPool(2);
try {
    CountedCompleter<?> root = createRoot();
    pool.execute(root);
    root.get(5, TimeUnit.SECONDS);
} finally {
    pool.shutdownNow();
}
```

Đây là **snippet** cần import `ForkJoinPool`, `CountedCompleter`, `TimeUnit`; `createRoot()` do ứng dụng định nghĩa và method caller khai báo/handle checked exceptions từ `get`. Timeout giúp phát hiện **liveness failure**, nhưng **không chứng minh cancellation dừng mọi child**; `shutdownNow()` chỉ cố interrupt, không nên dựa vào nó để hoàn tất một protocol hỏng.

**Không viết test đếm chính xác thứ tự callback theo tên thread**; work stealing và scheduling thay đổi. Hãy assert invariant như tổng, callback count, completion status, và rằng tất cả hiệu ứng được phép đã xảy ra.

## 21. FAQ quan trọng

**1. `CountedCompleter` có phải chỉ là `RecursiveAction` thêm một counter?** Không. Nó thay đổi **completion protocol**: compute return chưa đủ, pending count và completer chain quyết định khi root được complete; có callbacks, traversal và early completion API.

**2. Mặc định pending count là mấy?** Bằng 0 nếu constructor không truyền initial count.

**3. `setPendingCount(2)` nghĩa là còn đúng hai children đang chạy?** Không nhất thiết. Nó là internal count cho **số lần `tryComplete` cần làm giảm trước lần trigger tiếp theo**. Protocol còn phụ thuộc parent có tự báo hay không.

**4. Khi `tryComplete` giảm 1→0 có gọi `onCompletion` ngay không?** Không. Khi vào method mà pending nonzero, nó giảm rồi return; lời `tryComplete` tiếp theo thấy zero mới gọi callback/propagate.

**5. Có thể fork children xong rồi set pending không?** Không an toàn; children có thể chạy và báo completion trước, làm protocol sai.

**6. Có cần `join()` từng child không?** Thường không; đó là điểm mạnh của CountedCompleter. Đợi **root** hoàn tất, không mặc nhiên join child nội bộ có completer.

**7. `onCompletion` do parent hay child gọi?** Nó chạy trong đường traversal do **lượt `tryComplete` cuối cùng phù hợp** kích hoạt. `caller` có thể là node hiện tại hoặc child; không dự đoán scheduler.

**8. `CountedCompleter<Integer>` có tự trả kết quả từ `compute()` không?** Không: `compute()` là void. Muốn `invoke/join` trả value, override `getRawResult()` hoặc quản lý result theo hợp đồng.

**9. `propagateCompletion` khác `tryComplete` thế nào?** Nó bỏ qua `onCompletion` trên traversal. Không dùng nếu reducer dựa vào callback.

**10. `quietlyCompleteRoot` có dừng mọi subtasks không?** Không. Nó đánh dấu root hoàn tất sớm; những task khác có thể tiếp tục chạy.

**11. CountedCompleter bảo đảm wait-free không?** Không. Pending counts và ForkJoinPool không tự tạo wait-free guarantee cho toàn thuật toán. Root có thể chờ mãi nếu protocol lỗi.

**12. Với sum đơn giản, loại nào dễ kiểm chứng nhất?** Thường `RecursiveTask<Integer>` vì kết quả rõ ràng qua `join`; CountedCompleter có giá trị khi cần completion-driven architecture hoặc workload đặc thù.

**13. Exception từ một leaf có thể ảnh hưởng root không?** Có theo exceptional completion propagation; nhưng không đồng nghĩa mọi sibling đã bị hủy hay mọi side effects đã rollback.

**14. Có thể dùng `CountedCompleter<Void>` và shared array để ghi kết quả không?** Có nếu mỗi leaf có ownership của vùng không trùng nhau hoặc dùng đồng bộ hợp lệ, rồi chờ root complete trước khi đọc. Task structure không tự làm array writes nguyên tử cho cùng một phần tử.

**15. Một `CountedCompleter` internal child `isDone()==false` sau khi nó đã báo hoàn tất có phải bug không?** Chưa chắc. Theo API, status của các completers có parent có thể không được đánh dấu như root nếu không có explicit completion, dù đã báo completion qua chain.

## 22. Checklist trước khi dùng trong production

- **Tại sao cần CountedCompleter thay cho RecursiveTask/RecursiveAction?** Có lợi ích completion-driven đo được hay không?
- Mỗi node có **đúng một completer parent** và biết nhiệm vụ của nó chưa?
- `pending count` đã được tính theo **số arrivals thực**, gồm cả parent `tryComplete` nếu có?
- Set pending **trước** khi fork có khả năng child hoàn tất?
- Mọi normal execution path có `tryComplete`/`propagateCompletion` đúng chỗ?
- `onCompletion` có cần combine? Nếu cần, **không dùng propagateCompletion**.
- State của children được giữ như thế nào? Có thứ tự left/right và visibility hợp lệ?
- Root `getRawResult` có trả dữ liệu sau khi hoàn tất đúng protocol?
- Có test exceptional paths, cancellation và early-complete với sibling tasks không?
- Có tránh I/O blocking dài trên common pool và shutdown đúng owner?
- Threshold/granularity có đo bằng workload thực và số cores phù hợp?
- Có tránh shared accumulator gây contention không cần thiết?
- Test có deadline, nhiều pool sizes và input boundary cases?
- Mọi side effects phải hoàn tất hay có được phép trả sớm? Contract quy định rõ chưa?

**Tóm lại:** `RecursiveTask` **trả kết quả** và thường chờ child qua `join`; `RecursiveAction` **không trả kết quả** và thường chờ các nhánh hoàn tất; `CountedCompleter` cung cấp **giao thức hoàn tất điều khiển bằng pending count và callback**. Ưu thế là parent không nhất thiết join children; đổi lại, programmer chịu trách nhiệm đếm arrivals, propagate completion, combine kết quả, xử lý lỗi và liveness. **Chỉ chọn CountedCompleter khi cấu trúc completion thực sự đem lại lợi ích đủ lớn để bù độ phức tạp.**

### Tài liệu tham khảo

- Oracle Java SE 17 API: [CountedCompleter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountedCompleter.html)
- Oracle Java SE 17 API: [RecursiveTask](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/RecursiveTask.html)
- Oracle Java SE 17 API: [RecursiveAction](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/RecursiveAction.html)
- Oracle Java SE 17 API: [ForkJoinPool](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ForkJoinPool.html)
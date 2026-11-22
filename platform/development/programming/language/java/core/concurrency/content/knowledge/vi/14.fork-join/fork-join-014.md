# Quan hệ completer, pending count và cây hoàn tất của CountedCompleter trong Java

## 1. CountedCompleter giải quyết bài toán gì?

Trong Fork/Join, một phép tính có thể được chia thành nhiều phần việc nhỏ. Với `RecursiveTask` hoặc `RecursiveAction`, cách thường gặp là tạo subtask, `fork()` một phần, rồi `join()` để chờ kết quả. Với những bài toán có nhiều nhánh độc lập, độ dài xử lý mỗi nhánh không đồng đều hoặc cần tổng hợp kết quả khi toàn bộ nhánh hoàn tất, **CountedCompleter** cho phép xây dựng một **cây thông báo hoàn tất** mà các worker không nhất thiết phải block bằng `join()` ở từng nút cha.

`java.util.concurrent.CountedCompleter<T>` là một lớp trừu tượng kế thừa `ForkJoinTask<T>`, có từ Java 8. Mỗi task có thể giữ:

- Một tham chiếu **completer**: thường là task cha sẽ nhận thông tin hoàn tất từ task hiện tại.
- Một số nguyên **pending count**: lượng tín hiệu hoàn tất còn phải được tiêu thụ trước khi task đủ điều kiện thực hiện hành động hoàn tất.
- Một hàm `compute()`: thực hiện công việc, có thể tạo thêm task con.
- Một callback `onCompletion(CountedCompleter<?> caller)`: thực hiện công việc cuối, ví dụ gộp kết quả các nhánh.
- Một cơ chế `tryComplete()`: tự giảm pending khi còn dương, hoặc kích hoạt completion callback rồi đi tiếp lên chuỗi completer khi pending đã bằng 0.

**Điều dễ nhầm nhất:** `pending count` **không** phải một danh sách child task do JVM tự theo dõi. Bạn phải **tự thiết lập đúng số lượt thông báo**, sắp xếp thời điểm fork, và bảo đảm tất cả nhánh tham gia protocol gọi `tryComplete()` hoặc cơ chế propagation phù hợp.

Bài này giới hạn ở **Fork/Join và concurrency của Java nói chung**, sử dụng API của JDK 17+. Không đi vào cách các framework khác bọc hoặc sử dụng executor.

### Kết quả học tập

Sau bài học, bạn cần có khả năng:

1. Phân biệt **completer**, **pending count**, **parent/child computation** và **trạng thái hoàn tất của ForkJoinTask**.
2. Vẽ và giải thích cây completion, biết tín hiệu nào làm pending giảm và tín hiệu nào thực sự kích hoạt `onCompletion()`.
3. Dùng `setPendingCount`, `addToPendingCount` và `tryComplete` đúng thứ tự, tránh hoàn tất sớm hoặc treo mãi.
4. Xây dựng chương trình Java 17+ chạy được gồm cây task, phép tổng hợp kết quả và một dạng propagation không cần callback.
5. Biết điểm khác nhau giữa `tryComplete()`, `propagateCompletion()`, `complete(T)`, `quietlyCompleteRoot()`, `firstComplete()/nextComplete()`.
6. Hiểu xử lý exception, cancellation, memory visibility, giới hạn liveness và những trường hợp nên chọn `RecursiveTask` đơn giản hơn.

## 2. Cấu trúc cơ bản của CountedCompleter

### 2.1. Các constructor

~~~java
// Chữ ký minh họa API; không phải chương trình độc lập.
protected CountedCompleter();
protected CountedCompleter(CountedCompleter<?> completer);
protected CountedCompleter(
    CountedCompleter<?> completer,
    int initialPendingCount
);
~~~

- Constructor không tham số tạo một task không có completer, pending ban đầu **0**.
- Constructor nhận `completer` tạo liên kết tới một CountedCompleter khác, pending ban đầu **0**.
- Constructor ba đối số cho phép thiết lập pending count ban đầu một cách có chủ ý.
- `getCompleter()` cho biết liên kết completer được tạo trong constructor.
- `getRoot()` lần theo completer để lấy gốc chuỗi completion.
- Một task gốc có `getCompleter() == null`; nó có thể được `invoke()` hoặc submit vào `ForkJoinPool`.

### 2.2. Compute không đồng nghĩa complete

`CountedCompleter` buộc subclass override:

~~~java
// Mẫu cấu trúc trong subclass; không phải chương trình độc lập.
@Override
public void compute() {
    performLocalWork();
    tryComplete();
}
~~~

`compute()` chỉ mô tả phần việc chính. Task **không nhất thiết được đánh dấu hoàn tất chỉ vì compute() return**. Việc completion phụ thuộc protocol CountedCompleter; thường cần gọi `tryComplete()` ở điểm cuối.

Tại sao phải thiết kế như vậy? Cha có thể fork các con rồi kết thúc phần việc *local* rất nhanh. Nhưng cha chỉ nên công bố hoàn tất khi các tín hiệu completion từ phần việc còn thiếu đã được xử lý đúng.

Ở `RecursiveTask`, lập trình viên hay viết `left.fork(); right.compute(); left.join();`. Ở `CountedCompleter`, phần kết nối sau khi các nhánh hoàn thành được biểu diễn bằng **pending count + completer chain**, không cần block cha tại `join()` ở mỗi mức.

### 2.3. Nút gốc, nút trung gian và lá

~~~text
Root  (completer = null)
 |
 +-- Branch A (completer = Root)
 |      |
 |      +-- Leaf A1 (completer = Branch A)
 |      +-- Leaf A2 (completer = Branch A)
 |
 +-- Branch B (completer = Root)
        |
        +-- Leaf B1 (completer = Branch B)
        +-- Leaf B2 (completer = Branch B)
~~~

Trong sơ đồ này, **completer tree** là cây các quan hệ **completion**. Nó thường giống cây chia thuật toán nhưng không bắt buộc giống mọi quan hệ gọi method trong chương trình.

Ví dụ, một task có thể **trực tiếp gọi `compute()` của một nhánh** để giảm số lần fork, trong khi nhánh đó vẫn có completer là task cha. Quan hệ “task nào thực hiện trên thread nào” khác với liên kết completer.

## 3. Pending count thực sự đếm cái gì?

### 3.1. Không phải số task đang chạy

Một cách hiểu hữu ích: pending count là số lần `tryComplete()` gặp giá trị **khác 0** và phải giảm nó **trước khi** một lần gọi sau đó gặp 0 để kích hoạt completion của node.

Giả sử pending count của Root được đặt là **2**:

~~~text
Root.pending = 2

Lần tryComplete đến Root thứ 1:
    thấy pending = 2 -> giảm còn 1; không gọi onCompletion

Lần tryComplete đến Root thứ 2:
    thấy pending = 1 -> giảm còn 0; không gọi onCompletion

Lần tryComplete đến Root thứ 3:
    thấy pending = 0 -> gọi Root.onCompletion(caller)
                       -> nếu Root không có completer:
                          đánh dấu Root hoàn tất
~~~

**Chú ý “off-by-one”:** Pending bằng 2 trong cơ chế này tương ứng với **hai lần giảm và một lần gọi ở trạng thái 0** để kích hoạt completion. Nó không đơn giản có nghĩa “hai child đã hoàn tất thì mọi việc tự xong” nếu bạn chưa tính cả lần `tryComplete()` của parent.

Đây là nguyên nhân mẫu dễ đọc nhất khi có **N child được fork** thường là:

~~~java
// Mẫu trong compute() của parent; không phải chương trình độc lập.
setPendingCount(N);             // Trước khi fork.
for (int i = 0; i < N; i++) {
    createChild(this, i).fork();
}
tryComplete();                  // Parent góp một lượt completion.
~~~

Khi parent và N child mỗi bên góp **một lần** vào giao thức, tổng có N+1 lần, đủ để parent có N lần giảm từ N về 0 rồi một lần kích hoạt callback. Các lượt đến có thể mang thứ tự bất kỳ mà vẫn được kế toán đúng.

### 3.2. Vì sao set count trước fork?

Nếu parent fork child trước rồi mới gọi `setPendingCount`, một worker khác có thể xử lý child nhanh và gọi `tryComplete()` về parent **trước khi parent ghi pending**. Khi đó parent có thể hoàn tất sớm, tổng hợp kết quả chưa đủ, hoặc các lượt giảm bị ghi đè bởi `setPendingCount` đến muộn.

Thứ tự đúng là:

~~~text
Parent:
  1. Tạo hoặc xác định số nhánh cần chờ
  2. Thiết lập pending count
  3. Công bố các child bằng fork()
  4. Hoàn thành phần việc của chính parent
  5. Gọi tryComplete() theo thiết kế đã đếm
~~~

Nếu việc tạo nhánh động, `addToPendingCount(delta)` có thể tăng pending một cách nguyên tử. Nhưng **phải tăng trước khi đưa nhánh có thể hoàn tất vào hàng chạy**, và phải chứng minh số lần tăng/giảm cân bằng với số tín hiệu thực tế.

### 3.3. Atomicity của bộ đếm

Các method liên quan:

| Method | Công dụng |
| --- | --- |
| `getPendingCount()` | Đọc số pending hiện tại |
| `setPendingCount(int)` | Đặt pending, chỉ an toàn khi việc thay đổi phù hợp protocol |
| `addToPendingCount(int)` | Cộng delta nguyên tử |
| `compareAndSetPendingCount(expected, update)` | CAS trên pending count |
| `decrementPendingCountUnlessZero()` | Giảm nếu hiện tại không phải 0; trả giá trị quan sát trước phép giảm theo contract |
| `tryComplete()` | Giảm pending nếu khác 0, hoặc kích hoạt completion nếu bằng 0 |
| `propagateCompletion()` | Cơ chế propagation tương tự nhưng **không gọi onCompletion** |

Bộ đếm được cập nhật bằng primitive atomic của JDK, nên nhiều child có thể thông báo đồng thời mà không mất update của chính pending. Tuy vậy, **tính đúng đắn của số lượt thông báo vẫn là trách nhiệm thuật toán**: JVM không tự biết bạn tạo bao nhiêu child, child nào “hợp lệ”, hoặc result nào đã sẵn sàng.

Không lấy một snapshot `getPendingCount() == 0` rồi suy ra toàn bộ cây đã được đánh dấu done. Có thể pending đã về 0 **nhưng chưa có lần gọi tiếp theo để kích hoạt completion**.

## 4. tryComplete() đi qua cây như thế nào?

### 4.1. Mô hình tư duy (không phải mã triển khai JDK)

~~~java
// PSEUDOCODE, không phải đoạn Java độc lập hoặc source của JDK.
void tryCompleteConceptually(CountedCompleter<?> originalCaller) {
    CountedCompleter<?> node = this;
    CountedCompleter<?> caller = originalCaller;

    for (;;) {
        int pending = node.getPendingCount();

        if (pending != 0) {
            if (node.compareAndSetPendingCount(pending, pending - 1)) {
                return;
            }
            continue; // CAS thua; kiểm tra lại.
        }

        node.onCompletion(caller);
        CountedCompleter<?> parent = node.getCompleter();
        if (parent == null) {
            // Đánh dấu root hoàn tất theo cơ chế ForkJoinTask.
            return;
        }

        caller = node;
        node = parent;
    }
}
~~~

Mã này chỉ là **mô hình ý nghĩa** của traversal, không phải bản chép mã thực thi JDK. Điều cần nhìn:

1. Tại node có pending khác 0: atomic decrement và **dừng traversal** tại đó.
2. Tại node có pending bằng 0: gọi `onCompletion(caller)`, sau đó đi tới completer.
3. Nếu đi tới root có pending bằng 0: sau callback, root được đánh dấu complete.
4. Khi nhiều nhánh cùng báo completion, CAS giúp mỗi lần giảm là nguyên tử; callback chỉ nên được kích hoạt theo giao thức đếm đã chứng minh.
5. `caller` là task đã làm traversal đi tới node hiện tại: có thể là chính node hoặc một descendant vừa hoàn tất. Tham số này giúp kết hợp kết quả ở từng nút.

Không có cơ chế tự động “giảm pending đúng 1 lần cho mỗi child được fork”. Chính các lời gọi completion tạo các lượt đó.

### 4.2. Timeline minh họa với hai child

Dùng pattern parent `setPendingCount(2)`, fork C1/C2 và tự gọi `tryComplete()`:

~~~text
Root.pending = 2
Root forks C1 and C2

Root.tryComplete() -> Root.pending: 2 -> 1
C1.tryComplete()   -> C1.pending=0, C1.onCompletion()
                   -> Root.pending: 1 -> 0
C2.tryComplete()   -> C2.pending=0, C2.onCompletion()
                   -> Root.pending=0, Root.onCompletion(caller=C2)
                   -> Root completed
~~~

Nếu C1 và C2 hoàn tất **trước** lời gọi của Root:

~~~text
Root.pending = 2
C1.tryComplete()   -> Root.pending: 2 -> 1
C2.tryComplete()   -> Root.pending: 1 -> 0
Root.tryComplete() -> Root.pending=0, Root.onCompletion(caller=Root)
                   -> Root completed
~~~

Cả hai thứ tự đều có thể hợp lệ. Vì vậy **không nên viết logic trong `onCompletion` mà giả định caller luôn là child cuối**. Javadoc cho phép `caller == this` trong một số đường traversal; callback phải dựa trên invariant về kết quả đã sẵn sàng, không dựa vào một lịch CPU cụ thể.

## 5. Ví dụ 1 — root chờ hai leaf và chỉ hoàn tất khi đủ tín hiệu (Java 17+)

Ta xây một cây đơn giản gồm Root và hai Leaf. Mỗi leaf cộng một số vào `AtomicInteger`. Root có `onCompletion` ghi snapshot tổng cuối và đếm số lần callback chạy. Vì các leaf độc lập, không có thứ tự thực thi nào bị cố định.

Tạo tệp `SimpleCompleterTreeDemo.java`:

~~~java
import java.util.concurrent.CountedCompleter;
import java.util.concurrent.atomic.AtomicInteger;

public class SimpleCompleterTreeDemo {
    static final class Root extends CountedCompleter<Void> {
        private final AtomicInteger sum = new AtomicInteger();
        private final AtomicInteger completionCalls =
            new AtomicInteger();
        private int finalSum;

        @Override
        public void compute() {
            setPendingCount(2);

            new Leaf(this, sum, 5).fork();
            new Leaf(this, sum, 7).fork();

            tryComplete(); // Tín hiệu của chính Root.
        }

        @Override
        public void onCompletion(CountedCompleter<?> caller) {
            finalSum = sum.get();
            completionCalls.incrementAndGet();
        }

        int result() {
            return finalSum;
        }

        int completionCount() {
            return completionCalls.get();
        }
    }

    static final class Leaf extends CountedCompleter<Void> {
        private final AtomicInteger sum;
        private final int contribution;

        Leaf(Root parent, AtomicInteger sum, int contribution) {
            super(parent);
            this.sum = sum;
            this.contribution = contribution;
        }

        @Override
        public void compute() {
            sum.addAndGet(contribution);
            tryComplete();
        }
    }

    public static void main(String[] args) {
        Root root = new Root();
        root.invoke();

        System.out.println("sum = " + root.result());
        System.out.println(
            "root completion calls = " + root.completionCount()
        );
        System.out.println("root done = " + root.isDone());
        System.out.println("root pending = " + root.getPendingCount());
    }
}
~~~

Biên dịch và chạy bằng JDK 17+:

~~~bash
javac SimpleCompleterTreeDemo.java
java SimpleCompleterTreeDemo
~~~

Stdout khi các task hoàn thành bình thường:

~~~text
sum = 12
root completion calls = 1
root done = true
root pending = 0
~~~

**Vì sao output xác định được?**

- Hai leaf cộng 5 và 7 bằng `AtomicInteger.addAndGet`, nên dù chạy thứ tự nào, tổng là 12.
- Root **đặt pending = 2 trước khi fork**, rồi gọi `tryComplete()` một lần.
- Mỗi leaf thực hiện phần việc rồi gọi `tryComplete()`; traversal của leaf có pending 0 dẫn tới completer Root.
- Tổng ba lượt báo completion vào Root làm hai lần giảm và một lần kích hoạt `onCompletion`.
- `root.invoke()` chỉ trả về sau khi root được đánh dấu complete; vì vậy kết quả tổng hợp `finalSum` và callback count có thể được đọc sau đó.
- `root.isDone() == true` là trạng thái của **root**, không chỉ là việc `compute()` đã return.
- Không cần biết leaf nào chạy trước hoặc thread nào gọi `onCompletion`.

**Đừng nhầm:** `completionCalls` là biến đếm dùng để kiểm chứng bài học. CountedCompleter không tự tạo cho bạn một counter này; logic cần tự cung cấp kết quả nghiệp vụ.

### Nếu quên tryComplete ở Root?

Giả sử Root đặt pending=2, fork hai leaf nhưng **không tự gọi tryComplete()**. Hai leaf chỉ có hai lượt báo về Root: pending đi từ 2 → 1 → 0, nhưng **không còn lượt thứ ba** để kích hoạt root callback. `invoke()` có thể chờ mãi. Đây là lỗi kế toán completion, không phải lỗi `AtomicInteger` hay lỗi scheduler.

### Nếu đặt pending=1 và vẫn gọi tryComplete ở Root?

Với hai leaf, tổng ba lượt báo và chỉ cần hai lượt cho pending=1, Root có thể **complete trước khi tất cả công việc đã bảo đảm kết thúc**, tùy thứ tự interleaving. Vì vậy không tự đổi pending count chỉ để “trông hợp lý” nếu chưa chứng minh lại protocol.

## 6. Cây hoàn tất nhiều tầng: child không đồng nghĩa completed ForkJoinTask

Xét cây:

~~~text
             Root (pending theo số tín hiệu)
             /   \
        Branch1  Branch2
        /    \     /    \
      L1     L2   L3    L4
~~~

Khi L1 hoàn tất và gọi `tryComplete()`, traversal có thể đi tới Branch1 và **giảm pending của Branch1 rồi dừng**, chưa tới Root. Khi Branch1 nhận đủ tín hiệu, nó gọi `onCompletion` rồi mới đi tới Root. Điều đó giúp Root chờ **cả nhóm công việc dưới từng branch**.

Một CountedCompleter *nằm trong cây, có completer khác null* thường chỉ là **nút phối hợp nội bộ**. Javadoc lưu ý trạng thái `isDone()` riêng của loại node này **không nhất thiết phản ánh** việc đã thông báo completion lên cha. Trạng thái đó chỉ thay đổi khi có các thao tác hoàn tất rõ ràng, hủy hoặc exception theo hợp đồng.

**Quan trọng:** `tryComplete()` có thể chuyển completion lên completer mà **không đánh dấu done cho từng node trung gian**. Đừng gọi `join()` trên mọi node nội bộ như thể chúng là `RecursiveTask` thông thường. Thường nên invoke/join **root**, hoặc dùng một giao thức ghi nhận completion của các nhánh nếu thật sự cần chờ từng nhánh.

## 7. Ví dụ 2 — cây chia để trị và gộp kết quả trong onCompletion (Java 17+)

Bài toán: tính tổng một mảng `int[]`. Mỗi node phụ trách một khoảng `[lo, hi)`. Nếu khoảng nhỏ, tính local sum. Nếu lớn, chia làm hai child; hai child hoàn tất rồi node parent gộp kết quả trong `onCompletion`.

Tạo tệp `CompleterReduceDemo.java`:

~~~java
import java.util.concurrent.CountedCompleter;
import java.util.concurrent.atomic.AtomicInteger;

public class CompleterReduceDemo {
    static final class Node extends CountedCompleter<Integer> {
        private final int[] data;
        private final int lo;
        private final int hi;
        private final AtomicInteger merges;
        private Node left;
        private Node right;
        private int result;

        Node(
                CountedCompleter<?> parent,
                int[] data,
                int lo,
                int hi,
                AtomicInteger merges
        ) {
            super(parent);
            this.data = data;
            this.lo = lo;
            this.hi = hi;
            this.merges = merges;
        }

        @Override
        public void compute() {
            if (hi - lo <= 2) {
                int local = 0;
                for (int i = lo; i < hi; i++) {
                    local += data[i];
                }
                result = local;
                tryComplete();
                return;
            }

            int mid = (lo + hi) >>> 1;
            left = new Node(this, data, lo, mid, merges);
            right = new Node(this, data, mid, hi, merges);

            setPendingCount(2);
            left.fork();
            right.fork();
            tryComplete(); // Một lượt của node cha.
        }

        @Override
        public void onCompletion(CountedCompleter<?> caller) {
            if (left != null) {
                result = left.result + right.result;
                merges.incrementAndGet();
            }
        }

        @Override
        public Integer getRawResult() {
            return result;
        }
    }

    public static void main(String[] args) {
        int[] data = {1, 2, 3, 4, 5, 6, 7, 8};
        AtomicInteger merges = new AtomicInteger();
        Node root = new Node(null, data, 0, data.length, merges);

        Integer total = root.invoke();

        System.out.println("sum = " + total);
        System.out.println("merge callbacks = " + merges.get());
        System.out.println("root complete = " + root.isDone());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac CompleterReduceDemo.java
java CompleterReduceDemo
~~~

Stdout:

~~~text
sum = 36
merge callbacks = 3
root complete = true
~~~

**Cách chứng minh kết quả:**

- Mảng có tám số từ 1 tới 8, nên tổng là 36.
- Khi khoảng có độ dài tối đa 2, node lá tính tổng cục bộ rồi `tryComplete()`.
- Một node không phải lá tạo hai con, đặt pending=2 **trước** khi fork, rồi tự báo completion.
- Khi cả hai nhánh đã có kết quả, `onCompletion` của node cha đọc `left.result` và `right.result`, gộp vào `result`.
- Cây tám phần tử với ngưỡng lá hai phần tử có bốn leaf và **ba node nội bộ** (hai node chia 4 và một root), nên `merges` tăng đúng ba lần.
- `getRawResult()` trả trường `result` của node. CountedCompleter **không tự đặt raw result** cho bạn chỉ vì `onCompletion` đã gộp kết quả.
- `root.invoke()` chỉ trở về khi root đã hoàn tất; kết quả gộp cuối cùng được đọc ở root.

**Điểm concurrency:** Hai child có thể chạy song song. Javadoc CountedCompleter cho phép sử dụng kết quả của các subtask **đã hoàn tất theo protocol** trong `onCompletion` mà không cần thêm synchronized cho truy cập kết quả của các child đã hoàn tất. Điều này **không** nghĩa rằng mọi mutable field được đọc ở bất kỳ thời điểm nào đều an toàn; quy tắc đó dựa vào việc pending count thật sự bảo đảm child đã ghi xong.

**Hạn chế ví dụ:** Cộng `int` có thể overflow với mảng rất lớn; nếu domain yêu cầu tổng chính xác vượt khoảng int, dùng `long` hoặc `Math.addExact`/policy nghiệp vụ. Với mảng ngắn, overhead tạo nhiều ForkJoinTask có thể lớn hơn lợi ích parallelism; nên dùng threshold lớn hơn theo benchmark thực tế.

## 8. Callback onCompletion(caller): caller có thể là ai?

### 8.1. Tại sao có tham số caller?

Method:

~~~java
// Chữ ký trong CountedCompleter, không phải chương trình độc lập.
public void onCompletion(CountedCompleter<?> caller)
~~~

`caller` là task gây ra traversal tới node hiện tại. Nó có thể:

- **Bằng chính node** (`caller == this`) khi node tự gọi `tryComplete()` đúng thời điểm pending đã bằng 0.
- **Là một subtask/descendant** đã thông báo và đi lên qua completer chain.

Ở ví dụ gộp kết quả, callback đọc `left/right.result` đã được tính theo protocol, nên không cần dựa vào caller. Với cấu trúc cây khác, callback có thể dùng caller để truy ra nhánh vừa tới, kết quả nhánh đó hoặc liên kết sibling.

### 8.2. Không dựa vào “child cuối chạy”

Một lỗi tinh vi:

~~~java
// SAI nếu lập luận rằng caller chắc chắn là child cuối.
// Đây chỉ là pseudocode, không phải chương trình độc lập.
@Override
public void onCompletion(CountedCompleter<?> caller) {
    Child last = (Child) caller;
    // Giả định last luôn child hợp lệ khác this.
}
~~~

Nếu callback được kích hoạt bởi chính task cha (`caller == this`), cast sẽ sai. Ngay cả khi callback được gọi từ child, thứ tự nào là “cuối” còn phụ thuộc scheduling. Nếu cần kết hợp theo thứ tự trái/phải, ghi rõ `left`/`right` và sử dụng **vị trí trong cây**, không dựa vào thời điểm hoàn tất.

### 8.3. Callback dùng cho reduce hoặc continuation

Các thao tác hợp lý trong `onCompletion`:

- Gộp kết quả của nhánh đã xong.
- Đánh dấu một phase/tổng hợp đủ điều kiện hoàn tất.
- Đưa một kết quả lên node cha.
- Ghi trạng thái kết thúc dựa trên dữ liệu đã được công bố.

Không thích hợp khi muốn callback block vô hạn chờ subtask khác; pending count đúng đã đại diện cho chờ. Nếu callback lại gọi `join()` trên một task phụ thuộc chính completion chain, có thể tự tạo deadlock. Hãy thiết kế callback ngắn, có invariant rõ, và không ném exception ngoài ý muốn.

## 9. Completion tree không phải cây ForkJoinTask.join thông thường

| Khía cạnh | `RecursiveTask/RecursiveAction` | `CountedCompleter` |
| --- | --- | --- |
| Cách ghép phụ thuộc | Thường `join()` nhánh đã fork | Pending count + `tryComplete()`/`onCompletion()` |
| Cha có thể dừng compute() sớm? | Nếu còn cần join, compute sẽ đợi theo logic của nó | Có, compute return không đồng nghĩa root done |
| Quan hệ cha/con | Thường qua reference tới child task | Qua completer chain, cộng thêm reference nghiệp vụ |
| Gộp kết quả | Thường làm trong compute sau `join` | Có thể làm trong `onCompletion` |
| Giao thức completion | Framework của từng fork/join thông thường | Lập trình viên tự cân đối pending/arrival |
| Nguy cơ chính | Wait/block không hợp lý, nhiều task nhỏ | Thiếu/dư signal, race khi tăng pending, hiểu sai task status |
| Độ khó debug | Tương đối trực quan | Cần vẽ cây và đếm tín hiệu |
| Trường hợp phù hợp | Chia để trị tiêu chuẩn, cần kết quả mỗi nhánh | Completion graph nhiều nhánh, search/forEach/continuation |

**Lưu ý:** `CountedCompleter` vẫn **là một ForkJoinTask** và có `fork/invoke/join` ở cấp API. Sự khác biệt ở *cách completion được kích hoạt*, không phải nó chạy ngoài ForkJoinPool.

Không chọn CountedCompleter chỉ vì muốn code “nonblocking” theo mọi nghĩa. Một task vẫn có thể dùng I/O blocking hoặc gọi code chờ trong `compute`. Đặc tính linh hoạt là **tránh phụ thuộc join tại mỗi node cha trong thuật toán hoàn tất**, không tự động biến mọi công việc thành nonblocking I/O.

## 10. Các biến thể cân bằng số pending: N hay N-1?

### 10.1. Mẫu dễ kiểm chứng: N child + parent arrival

~~~java
// Trong compute(), N xác định và N >= 0.
// Không phải chương trình độc lập.
setPendingCount(N);
for (int i = 0; i < N; i++) {
    forkChildWithCompleter(this, i);
}
tryComplete();
~~~

Phải tính chính xác mỗi child sẽ gọi `tryComplete()` một lần theo đường đi đúng, kể cả nhánh rỗng hoặc nhánh trả về sớm. Nếu `N == 0`, parent đặt pending=0 rồi tự gọi `tryComplete()` và có thể hoàn tất ngay.

### 10.2. Mẫu tối ưu trong Javadoc: N-1 child arrivals, không gọi riêng ở parent

Javadoc của CountedCompleter có ví dụ giảm overhead bằng cách **không fork tất cả nhánh**, mà fork nhánh phải và xử lý nhánh trái trực tiếp. Khi parent không tự góp một lượt cuối mà để các nhánh gọi completion, pending count có thể trông **“lệch một”**.

Ví dụ mẫu được tối ưu phải có lập luận chính xác về số lượt arrival:

~~~java
// Pseudocode thuật toán: phải chứng minh số lượt.
// Không phải chương trình độc lập.
setPendingCount(1);
right.fork();
left.compute();  // Nhánh trái làm việc trực tiếp,
                 // và các leaf gọi tryComplete().
~~~

Với hai nhánh góp tổng hai lượt completion cho parent: lần thứ nhất giảm 1 → 0, lần thứ hai kích hoạt completion. Parent **không** tự gọi thêm `tryComplete()` trên đường này.

**Không được trộn hai mẫu:** Nếu dùng pending=1 nhưng parent cũng gọi `tryComplete()` như mẫu N child hoàn chỉnh, có thể làm node hoàn tất sớm. Nếu dùng pending=2 nhưng chỉ có hai arrival child và không có arrival của parent, có thể treo mãi. Hãy ghi ra *ai gọi tryComplete, bao nhiêu lần, và khi nào*.

### 10.3. Cách kiểm chứng bằng bảng tín hiệu

| Thiết kế | Pending ban đầu | Các lượt arrival dự kiến | Đủ để onCompletion? |
| --- | ---: | ---: | --- |
| 0 child, parent tự gọi | 0 | 1 | Có |
| 2 child + parent tự gọi | 2 | 3 | Có |
| 2 child, parent không gọi | 1 | 2 | Có, nếu mọi child báo đúng |
| 2 child, parent không gọi | 2 | 2 | **Không**, có thể kẹt |
| 2 child + parent tự gọi | 1 | 3 | **Sai kế toán**, có thể hoàn tất sớm |
| 3 child + parent tự gọi | 3 | 4 | Có |

Tuy nhiên, **đếm đúng số lượt chỉ là điều kiện cần**. Cần thêm bảo đảm các child đã ghi đủ kết quả và được đăng ký trước khi task có thể hoàn tất. Nếu tăng count muộn hoặc chia sẻ state không an toàn, kết quả vẫn có thể sai.

## 11. propagateCompletion() khác tryComplete() như thế nào?

`propagateCompletion()` dùng cùng kiểu duyệt completer và pending count như `tryComplete()`, nhưng **không gọi `onCompletion()`** trên đường duyệt.

Mục đích: tối ưu các cây mà nhiệm vụ chỉ là thực thi tác động tại leaf (ví dụ ghi mỗi phần tử mảng, tích lũy kết quả vào bộ đếm atomic độc lập) và **không cần callback reduce** ở mỗi node.

So sánh:

| Method | Pending nonzero | Pending zero | Có gọi onCompletion? |
| --- | --- | --- | --- |
| `tryComplete()` | Giảm count, dừng | Đi lên completer chain và hoàn tất root khi đủ | **Có** |
| `propagateCompletion()` | Giảm count, dừng | Đi lên chain và hoàn tất root khi đủ | **Không** |
| `complete(T)` | Không chờ pending count | Hoàn tất task được gọi và kích hoạt propagation tới completer | Có callback ở task được gọi |
| `quietlyCompleteRoot()` | Không đợi đếm đủ | Đánh dấu root complete | Không thay toàn bộ business bookkeeping |

Đừng đổi `tryComplete()` thành `propagateCompletion()` trong cây cần `onCompletion()` để gộp kết quả: root có thể trở về trong khi tổng hợp không chạy.

## 12. Ví dụ 3 — propagateCompletion không cần callback (Java 17+)

Tạo tệp `PropagationOnlyDemo.java`:

~~~java
import java.util.concurrent.CountedCompleter;
import java.util.concurrent.atomic.AtomicInteger;

public class PropagationOnlyDemo {
    static final class Root extends CountedCompleter<Void> {
        final AtomicInteger visits = new AtomicInteger();

        @Override
        public void compute() {
            setPendingCount(2);

            new Leaf(this, visits).fork();
            new Leaf(this, visits).fork();

            propagateCompletion();
        }
    }

    static final class Leaf extends CountedCompleter<Void> {
        private final AtomicInteger visits;

        Leaf(Root parent, AtomicInteger visits) {
            super(parent);
            this.visits = visits;
        }

        @Override
        public void compute() {
            visits.incrementAndGet();
            propagateCompletion();
        }
    }

    public static void main(String[] args) {
        Root root = new Root();
        root.invoke();

        System.out.println("visits = " + root.visits.get());
        System.out.println("root done = " + root.isDone());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac PropagationOnlyDemo.java
java PropagationOnlyDemo
~~~

Stdout:

~~~text
visits = 2
root done = true
~~~

Hai leaf tăng `AtomicInteger` riêng của root. Vì không có callback nào cần chạy, `propagateCompletion()` chỉ quản lý pending và hoàn tất gốc. Với các tác động độc lập, điều này có thể phù hợp hơn việc định nghĩa callback no-op tại từng node.

**Quan trọng:** Đây không phải chứng minh `propagateCompletion()` nhanh hơn trong mọi trường hợp. Chọn method theo việc **có cần onCompletion hay không**, sau đó đo workload thực tế nếu muốn tối ưu.

## 13. complete(T), quietlyCompleteRoot và các method traversal khác

### 13.1. complete(T) không đợi pending

`complete(T rawResult)` hoàn tất **task được gọi** bất kể pending count hiện tại. Theo hợp đồng CountedCompleter, nó gọi `onCompletion(this)` của task đó, đánh dấu task complete, rồi kích hoạt `tryComplete()` trên completer (nếu có).

Điều này hữu ích khi thuật toán có một **điểm hoàn tất dứt khoát** không cần đợi phần việc còn lại, nhưng cũng có thể phá protocol nếu dùng sai.

~~~java
// Minh họa, không phải chương trình độc lập.
task.complete(result);
~~~

Đừng dùng `complete(...)` như một cách “chữa” pending count tính sai trong thuật toán cần chờ tất cả child. Nó **bỏ qua pending tại task được gọi**, nên có thể cho kết quả thiếu.

### 13.2. quietlyCompleteRoot()

`quietlyCompleteRoot()` đánh dấu root completion mà không chờ mọi pending count đi về 0. Nó thường xuất hiện trong thuật toán **search**: một nhánh đã tìm được đáp án, không cần đợi tất cả nhánh khác hoàn thành trước khi trả result.

Nhưng:

- Những nhánh còn lại có thể đang chạy hoặc chưa dừng ngay.
- Để cắt bớt công việc, chúng phải **tự kiểm tra tín hiệu dừng** (ví dụ một `AtomicReference` đã có kết quả).
- Tác động phụ đã xảy ra ở những nhánh khác không tự rollback.
- Không dùng completion sớm nếu invariant yêu cầu **mọi nhánh** đều phải thực hiện xong.

### 13.3. firstComplete() và nextComplete()

Hai method `firstComplete()`/`nextComplete()` cho phép tạo một **completion traversal tùy chỉnh**:

- `firstComplete()` trả chính node nếu pending bằng 0; nếu pending khác 0 thì giảm và trả `null`.
- `nextComplete()` tiếp tục trên completer, hoặc đánh dấu root hoàn tất khi đến gốc.

Chúng hữu ích cho thuật toán reduce cần duy trì danh sách child/sibling và tự duyệt các completion. Vì dễ sai nếu dùng cùng lúc với `tryComplete` không kiểm soát, hãy bắt đầu từ mẫu đơn giản `tryComplete + onCompletion` trước khi tối ưu.

### 13.4. getRoot() và helpComplete()

`getRoot()` lần theo completer của task để lấy root. `helpComplete(int maxTasks)` cho phép cố giúp xử lý một số task chưa xử lý có task hiện tại trên completion path, theo giới hạn API.

`helpComplete` không bảo đảm “xử lý đúng maxTasks task” hoặc thay thế mọi cơ chế scheduling. Không dùng nó để khắc phục cây thiếu completion signal; lỗi logic pending không được chữa bằng việc thêm worker hoặc gọi help nhiều lần.

## 14. Kết quả trả về: getRawResult và setRawResult

Rất nhiều CountedCompleter dùng kiểu `CountedCompleter<Void>` vì kết quả thực tế là **side effect trên cấu trúc dữ liệu** hoặc việc bảo đảm toàn bộ phần việc xong. Khi đó `invoke()` thường trả `null`.

Nếu muốn trả giá trị như `CountedCompleter<Integer>`, phải thiết kế **nơi lưu result**:

~~~java
// Mẫu trong subclass, không phải chương trình độc lập.
private int result;

@Override
public Integer getRawResult() {
    return result;
}
~~~

Javadoc lưu ý `setRawResult(T)` mặc định không đóng vai trò thiết lập kết quả hữu ích trong CountedCompleter, nên không mặc nhiên kỳ vọng nó được dùng để lưu aggregation giống một số `ForkJoinTask` khác.

Ví dụ `CompleterReduceDemo` override `getRawResult()` để trả số tổng gộp sau khi root hoàn tất. Với một nút nội bộ có completer khác null, đừng dựa vào `join()` của node đó để lấy aggregation nếu chưa thiết kế rõ **cơ chế task status**. Kênh kết quả tổng hợp thông thường là **root**.

## 15. Exceptional completion và truyền lỗi trong cây

### 15.1. Exception từ compute

Nếu `compute()` ném một exception, ForkJoinTask có thể đánh dấu task **completed exceptionally**. Với CountedCompleter, exception **có thể được truyền lên completer chain** theo hợp đồng.

Callback liên quan:

~~~java
// Chữ ký trong subclass, không phải chương trình độc lập.
@Override
public boolean onExceptionalCompletion(
        Throwable error,
        CountedCompleter<?> caller
) {
    // Ghi nhận/đưa ra quyết định có propagate tiếp không.
    return true;
}
~~~

Theo mặc định, `onExceptionalCompletion` trả `true` để cho phép truyền lỗi lên các completer chưa hoàn tất. Trả `false` có thể chặn propagation tiếp lên trên; nhưng đây không phải lựa chọn nên làm chỉ để “ẩn lỗi”.

**Không suy luận:** `onCompletion` chỉ áp dụng cho normal completion. Một nhánh ném exception không đồng nghĩa các child còn lại tự dừng hoặc tổng hợp partial result được rollback. Caller cần xác định error policy và cleanup.

### 15.2. Lỗi khác với việc thiếu tín hiệu

Nếu child bị lỗi và protocol không có đường exceptional completion/cancellation phù hợp, một root chờ normal signal có thể không thể hoàn tất bình thường. Ngược lại, một root kết thúc exceptionally không có nghĩa mọi nhánh đã thực hiện cleanup xong.

Khi dùng CountedCompleter cho công việc thật:

1. Xác định task nào là **gốc chịu trách nhiệm báo lỗi**.
2. Quyết định propagation qua `onExceptionalCompletion`.
3. Thu thập exception đầy đủ nếu nhiều nhánh có thể lỗi; một throwable đầu tiên không tự là danh sách mọi lỗi.
4. Định nghĩa có cần hủy những nhánh còn lại hay không và bằng cơ chế cooperative cancellation phù hợp.
5. Không cho callback aggregate dùng result của nhánh chưa hoàn tất bình thường.
6. Quản lý pool lifecycle và tài nguyên ngoài thread pool.

### 15.3. InterruptedException và tác vụ chặn

`CountedCompleter` **không** tự khiến mọi `compute()` trở nên interruptible. Nếu bạn gọi I/O hoặc một API blocking trong compute, nó vẫn có những giới hạn của API đó. `ForkJoinPool` được thiết kế chủ yếu cho tác vụ chia nhỏ, ngắn hoặc có cơ chế hỗ trợ blocking như `ForkJoinPool.ManagedBlocker` ở nơi phù hợp.

Không xem exception propagation là lời hứa tự động dừng mọi thread. Mỗi nhánh phải có giao thức dừng và cleanup nếu có side effect quan trọng.

## 16. Pending-count bugs: cách nhận diện và sửa đúng

### 16.1. Missing arrival: root không hoàn tất

**Triệu chứng:** Root đã fork các child, tất cả child dường như xong nhưng `root.invoke()/join()` vẫn chờ. Nguyên nhân thường gặp: node giữ pending > 0 vì thiếu `tryComplete()` hoặc bị tính sai số lượt arrival.

Ví dụ:

~~~java
// SAI nếu chỉ có hai child báo và parent không tự báo.
setPendingCount(2);
left.fork();
right.fork();
// Thiếu tryComplete của parent.
~~~

Hai child thông báo tối đa hai lượt, làm pending 2 → 1 → 0 nhưng không có lượt thứ ba tới node ở trạng thái 0. **Cách sửa:** thêm `tryComplete` của parent theo mẫu N child, hoặc thiết kế lại pending=1 và đảm bảo chỉ hai child góp tín hiệu, không trộn cả hai.

### 16.2. Extra arrival: hoàn tất sớm

**Triệu chứng:** `onCompletion` đọc giá trị chưa tính xong, root trả về khi child còn chạy, kết quả thay đổi giữa các lần chạy.

Nguồn gốc có thể là:

- Đặt pending quá thấp so với số lượt completion thực tế.
- Một nhánh gọi `tryComplete()` hai lần (ví dụ một lần trong `try` và một lần trong `finally`).
- Parent vừa tự báo, vừa dùng công thức pending đã tối ưu cho trường hợp parent **không** báo.
- Tạo nhánh động mà tăng pending sau fork.

**Cách sửa:** vẽ cây completion và liệt kê **mọi đường gọi tryComplete/propagateCompletion/complete**. Chứng minh mỗi đường đi chỉ báo đúng số lần và result được công bố trước thông báo. Không chữa triệu chứng bằng `Thread.sleep()` hoặc thay scheduler.

### 16.3. setPendingCount muộn

~~~java
// SAI về thứ tự, không phải chương trình độc lập.
child.fork();
setPendingCount(1);
~~~

Child có thể hoàn tất rất nhanh, vì vậy parent nhận tín hiệu khi count vẫn ở 0 rồi complete sớm. Thiết lập trước khi child có thể chạy là yêu cầu cơ bản.

### 16.4. Trộn complete với tryComplete

`complete(T)` là **unconditional completion** cho task đích. Nếu code vừa chủ động complete child vừa cho child gọi tryComplete theo đường bình thường, có thể sinh những tín hiệu vượt thiết kế hoặc phá việc tổng hợp đủ nhánh.

Chọn một protocol nhất quán. Nếu cần early completion, phải xác định rõ **lý do cho phép bỏ qua các pending task** và ý nghĩa cleanup của các task còn lại.

### 16.5. Hiểu sai isDone của node trung gian

Có thể thấy một child/completer đã góp phần đẩy completion lên cha nhưng `child.isDone()` vẫn không phản ánh status như một ForkJoinTask độc lập thông thường. Đây là đặc điểm được Javadoc mô tả. Không tạo test “mọi internal node isDone == true” trừ khi chương trình thật sự gọi những method thay đổi trạng thái node theo contract.

### 16.6. Deadlock do join phụ thuộc ngược

Nếu node A giữ logic chờ `B.join()`, còn việc B hoàn tất phụ thuộc callback/chữ ký signal từ A, A có thể tự tạo cycle. CountedCompleter được thiết kế để dùng completion chain thay cho nhiều chỗ join, nhưng **không tự ngăn deadlock** nếu code thêm khóa hoặc chờ không hợp lý.

### 16.7. Kết quả có thứ tự

Nếu kết quả cần giữ đúng thứ tự trái/phải (ví dụ nối string, ghép log theo thứ tự), đừng dùng “child hoàn tất trước” để quyết định thứ tự. Gắn nhãn trái/phải trong cấu trúc, đọc đúng field của từng child ở onCompletion.

## 17. Thread safety và Java Memory Model

### 17.1. Child result được công bố cho onCompletion

Theo Javadoc CountedCompleter, nếu pending count được quản lý đúng, hành động trong `onCompletion` có thể truy cập các field kết quả của child đã hoàn tất theo protocol mà **không phải thêm đồng bộ hóa thủ công chỉ để công bố các kết quả đó**.

Nhưng bảo đảm này gắn với **giao thức completion đúng**. Nếu callback chạy sớm do pending thấp hoặc child được báo hoàn tất trước khi ghi result, không có memory primitive nào biến kết quả chưa tính thành kết quả đúng.

Trong `CompleterReduceDemo`, child ghi `result` trước khi gọi `tryComplete()`; parent chỉ gộp khi các tín hiệu đã được cân đối đúng.

### 17.2. Array và shared mutable data

Nếu mỗi child xử lý một đoạn **không chồng lấn** của mảng, các vùng ghi có thể an toàn theo ownership. Nhưng nếu các child cùng cập nhật một bộ đếm, dùng `AtomicInteger` hoặc cấu trúc phù hợp. CountedCompleter pending count **chỉ bảo vệ kế toán completion**, không tự làm mọi field nghiệp vụ atomic.

Ví dụ `SimpleCompleterTreeDemo` dùng AtomicInteger cho tổng vì cả hai leaf cùng cập nhật. Ví dụ reduce lưu partial sum trong mỗi Node khác nhau, sau đó parent đọc các result khi được phép gộp.

### 17.3. Root completion và phía gọi

`root.invoke()`/`root.join()` là các điểm đợi completion của root theo contract `ForkJoinTask`. Caller không nên đọc một trường `result` chưa đồng bộ hóa ở giữa lúc root đang RUNNING rồi kỳ vọng snapshot nhất quán.

Không nên nghĩ pending count là transaction hoặc memory barrier tổng quát cho mọi object liên quan. Khi side effect nằm ở database/network, cần synchronization/transaction và policy lỗi riêng cho domain đó.

## 18. Hiệu năng và cách chọn kích thước nhánh

### 18.1. Fork quá mịn

Nếu một bài toán có vài nghìn phần tử mà mỗi phần tử tạo một ForkJoinTask, overhead cấp phát task, scheduling, queueing, callback và cache contention có thể lớn hơn thời gian xử lý dữ liệu.

Một implementation hiệu quả thường:

- Dừng chia khi khoảng có tối đa **threshold** phần tử.
- Xử lý tuần tự cả một đoạn trong leaf thay vì mỗi phần tử một task.
- Fork ít nhánh, xử lý một nhánh trực tiếp trong worker khi hợp lý.
- Cân nhắc cấu trúc cây cân bằng để tránh mọi thông báo đổ về một root quá nóng.
- Đo chi phí tạo task và tỉ lệ idle worker theo workload.

Threshold là tham số performance, **không phải điều kiện correctness**, miễn chia nhánh giữ invariant không chồng lấn và mỗi nhánh báo completion đúng.

### 18.2. Tree completion và contention

Với một root chứa hàng chục nghìn child trực tiếp, tất cả child có thể cùng tranh chấp cập nhật **một pending count của root**. Chia thành nhiều branch có thể phân tán tranh chấp; mỗi nhánh chỉ báo một lượt lên parent sau khi tập child dưới nó hoàn tất.

Tree giúp giảm fan-in tại một điểm, nhưng cũng tăng số node và callback. Lựa chọn số mức cây và fan-out nên dựa vào benchmark trên dữ liệu thực.

### 18.3. Work stealing

`ForkJoinPool` được thiết kế hỗ trợ work stealing: worker có thể lấy task từ queue khác khi rảnh. `CountedCompleter` tích hợp với cơ chế scheduling này nhưng **không bảo đảm** mỗi task chạy trên một thread riêng hoặc tất cả task chạy song song ngay.

Khi đo hiệu năng, cần xem độ lệch thời gian giữa các nhánh, số core, pool parallelism, độ dài leaf, GC, allocation và contention. Đừng kết luận “không block join nên luôn nhanh hơn RecursiveTask”; cấu trúc cơ bản đơn giản thường tốt hơn nếu workload không cần completion callback phức tạp.

## 19. Test cây completion có ý nghĩa

### 19.1. Test kết quả và số callback

Từ các ví dụ runnable:

- Với root có hai leaf, tổng phải là 12 và `onCompletion` của root chạy một lần.
- Với mảng 1..8, sum phải là 36, có ba merge callback do ba node nội bộ.
- Với propagation-only, số lượt visit phải là 2, root done.

Tất cả số đo đó nên được kiểm sau `root.invoke()`/`join()`, không đọc kết quả chưa công bố khi thread khác còn đang cập nhật.

### 19.2. Test các interleaving khác nhau

Đừng dựa vào `Thread.sleep(50)` rồi giả định child đã xử lý. Sử dụng `CountDownLatch` hoặc `CyclicBarrier` nếu cần ép một số nhánh đến một điểm chờ, và đặt **timeout** ở tầng test để không treo test suite khi pending bị tính sai.

Nên kiểm:

1. Child hoàn tất **trước** khi parent tự gọi `tryComplete()`.
2. Parent tự báo completion **trước** các child.
3. Các child đồng thời gọi `tryComplete()` lên cùng node.
4. Nhánh rỗng hoặc ngưỡng leaf nhỏ: có còn một lần completion hợp lệ?
5. Child ném exception: root báo lỗi hoặc protocol exceptional completion đúng.
6. Ngừng sớm trong search: root hoàn tất nhưng những nhánh còn lại có thể vẫn chạy.
7. Multiple invocation hoặc reuse task: không tùy tiện tái `invoke()` một CountedCompleter đã hoàn tất mà không thiết kế reset.
8. Tất cả giá trị trên mảng được xử lý đúng một lần theo domain, không trùng hoặc thiếu.

### 19.3. Khi test bị treo

Nếu `invoke()` chờ vô hạn:

- Ghi lại giá trị `getPendingCount()` ở các node quan trọng (đọc như snapshot chẩn đoán, không tự thay đổi logic).
- Liệt kê số lần `setPendingCount`, `addToPendingCount` và `tryComplete` dự kiến.
- Xem exception của child: có đường nào return sớm hoặc throw không gọi signal bình thường?
- Dùng thread dump để xem worker đang chờ hay có deadlock do lock khác.
- Kiểm tra parent có thể hoàn tất trước khi child được publish hay không.
- Chứng minh lại **N+1 lượt cho pending=N** của mẫu fork N child + parent arrival.

Timeout không tự chứng minh deadlock monitor; có thể chỉ là root không bao giờ nhận đủ tín hiệu completion.

## 20. Checklist review code CountedCompleter

| Câu hỏi | Tiêu chí |
| --- | --- |
| Mỗi node có completer đúng? | `super(parent)` hoặc constructor phù hợp; root có parent null |
| Pending count đặt khi nào? | Trước khi fork child có thể báo hoàn tất |
| Có bao nhiêu lượt completion đến node? | Đã đếm cả parent arrival và child arrival |
| Mỗi leaf có báo `tryComplete`/propagate đúng? | Không thiếu do return/throw hoặc báo hai lần |
| Có callback gộp kết quả? | Dùng `tryComplete` và `onCompletion` |
| Không cần callback? | Có thể dùng `propagateCompletion` |
| Mọi kết quả được ghi trước thông báo? | Child publish result trước `tryComplete` |
| `onCompletion(caller)` có xét caller==this? | Không cast mù vào child |
| Root có được complete trước khi đủ nhánh? | Tránh pending thấp/complete vô điều kiện |
| Có dùng `join()` trên node trung gian không? | Hiểu rõ trạng thái node nội bộ |
| Exception có propagation policy? | `onExceptionalCompletion` hoặc xử lý root rõ ràng |
| Có side effect ngoài JVM? | Có policy rollback/cleanup riêng |
| Task có đủ lớn để fork? | Benchmark threshold và contention |
| Có test với nhiều thứ tự interleaving? | Dùng latches, timeout, kiểm invariant |
| Có nhầm pending count với số child tự theo dõi? | Chỉ là atomic counter do code quản lý |

## 21. Câu hỏi tự kiểm tra

**1.** Một parent fork 3 child và **cũng tự gọi `tryComplete()`** sau khi fork. Cần `setPendingCount` bao nhiêu theo mẫu đơn giản?

**3**. Có 4 lượt arrival (parent + 3 child); ba lượt giảm pending từ 3 về 0, lượt thứ tư kích hoạt callback.

**2.** Pending đã bằng 0, có đủ để kết luận root `isDone()` chưa?

Chưa. Có thể chưa có lượt `tryComplete()` tiếp theo để vào nhánh callback và đánh dấu root hoàn tất.

**3.** Nếu child gọi `tryComplete()` trước khi parent gọi `setPendingCount` thì có sao không?

Có thể sai. Child có thể làm node complete sớm khi pending vẫn 0, rồi parent ghi count muộn. **Thiết lập pending trước khi fork**.

**4.** Vì sao `onCompletion(caller)` không được luôn cast caller thành một child?

Vì `caller` đôi khi **bằng chính node** khi node tự kích hoạt completion; không phải lúc nào là một child khác.

**5.** `propagateCompletion()` có kích hoạt `onCompletion()` không?

Không. Nó tiếp tục cơ chế đếm và propagation **mà không gọi completion callback** trên đường đi.

**6.** Gọi `complete(result)` có chờ pending về 0 không?

Không. Nó hoàn tất task được gọi bất kể pending, sau đó kích hoạt propagation tới completer nếu có.

**7.** Vì sao `RecursiveTask.join()` trên mọi node nội bộ không phải cách suy luận mặc định cho CountedCompleter?

Vì các node có completer có thể chỉ truyền completion lên cha; status `isDone()` riêng của chúng không nhất thiết được đánh dấu normal completion qua traversal. Thường chờ root hoặc một kết quả được thiết kế riêng.

**8.** Trong reduce, khi nào parent được đọc `left.result` và `right.result`?

Khi đã bảo đảm hai nhánh **ghi xong** và completion protocol thực sự cho phép parent chạy `onCompletion`; không phải chỉ vì đã fork hoặc parent compute return.

**9.** Tại sao một root có 10.000 child trực tiếp có thể bị contention?

Vì rất nhiều child cùng cập nhật một pending count của root. Chia thành các branch có thể giảm fan-in, đổi lại tăng node/callback.

**10.** Nếu muốn return ngay khi một nhánh search tìm thấy kết quả, có thể dùng API nào?

`quietlyCompleteRoot()` kết hợp một nơi lưu kết quả thread-safe (ví dụ `AtomicReference`) và protocol để những nhánh còn lại tự nhận biết có thể dừng. Không tự động giết các nhánh khác.

**11.** Exception của một child có thể ảnh hưởng root không?

Có. `onExceptionalCompletion` mặc định cho phép truyền exceptional completion lên completer khi hợp đồng cho phép. Nhưng không tự đảm bảo mọi nhánh khác được hủy hoặc side effect rollback.

**12.** Khi nào nên chọn `RecursiveTask` thay vì `CountedCompleter`?

Khi thuật toán chỉ cần fork nhánh, join kết quả rồi gộp trực tiếp, một `RecursiveTask` thường dễ viết, dễ review và ít nguy cơ sai pending hơn. Dùng CountedCompleter khi thực sự cần completion traversal/continuation nhiều nhánh.

## 22. Tài liệu chuẩn và kết luận

Javadoc chính thức Java 17:

- [CountedCompleter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountedCompleter.html): định nghĩa `pending count`, `completer`, `tryComplete()`, `onCompletion()`, `propagateCompletion()`, `firstComplete()`, `nextComplete()` và các ví dụ forEach/map-reduce/search.
- [ForkJoinTask](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ForkJoinTask.html): vòng đời task, `fork`, `invoke`, `join`, cancellation và exceptional completion.
- [ForkJoinPool](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ForkJoinPool.html): work stealing, scheduling và worker quản lý task.

**Ghi nhớ:** `CountedCompleter` không tự đếm số child. Một **completer tree** là chuỗi các task nhận thông báo hoàn tất; **pending count** là bộ đếm arrival do thuật toán cấu hình; `tryComplete()` giảm pending khi còn khác 0 hoặc kích hoạt `onCompletion()` và đi lên parent khi đã bằng 0. Với mẫu **N child + parent tự báo**, dùng `pending = N`, tăng pending trước fork, đảm bảo mỗi đường hợp lệ báo đúng một lần. Chỉ khi kế toán completion và công bố kết quả đều đúng, root mới thể hiện một phép tính đã hoàn thành đáng tin.
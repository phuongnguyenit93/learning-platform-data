# Ví dụ tìm kiếm không đều và dừng sớm bằng CountedCompleter

Khi tìm một giá trị trong **cây có các nhánh dài/ngắn không đều**, một cách đơn giản là dùng đệ quy tuần tự: duyệt từng nhánh cho đến khi tìm thấy. Khi dữ liệu đủ lớn, có thể chia nhiều nhánh cho các worker trong `ForkJoinPool` xử lý song song. Tuy nhiên, nếu đã tìm được kết quả, việc bắt toàn bộ nhánh còn lại chạy xong rồi mới trả về thường lãng phí.

`CountedCompleter<T>` là một biến thể của `ForkJoinTask<T>` được thiết kế cho các tác vụ có **quan hệ hoàn tất thông qua bộ đếm pending**, đặc biệt phù hợp với cây công việc không đều, phân nhánh động, kết quả cần gộp hoặc **dừng chờ sớm** khi một nhánh tìm được đáp án. Một task có thể báo việc hoàn tất tới completer cha bằng `tryComplete()`; một nhánh tìm thấy đáp án có thể dùng `quietlyCompleteRoot()` để **đánh dấu root hoàn tất ngay**.

**Hai điều phải phân biệt:**

1. **Root hoàn tất sớm:** `pool.invoke(root)`, `root.join()` hoặc `root.get()` có thể trả về sau khi root được complete.
2. **Các task con đã thật sự dừng:** không tự động đúng chỉ vì root completed; task khác có thể vẫn đang chạy hoặc đã được fork nhưng chưa kiểm tra tín hiệu dừng.

Vì vậy, ta cần kết hợp **`CountedCompleter` + kết quả công bố an toàn bằng `AtomicReference` + kiểm tra cờ kết quả tại các điểm hợp tác**, đồng thời quản lý vòng đời pool. Nội dung hoàn toàn thuộc Java concurrency của JDK (Java 17+), không dùng framework khác.

## 1. Bài toán tìm kiếm không đều là gì?

Giả sử một cây có nhánh trái rất sâu, nhánh phải chỉ một vài nút và có chứa giá trị cần tìm:

```text
                 ROOT
                /    \
               /      \
         LEFT (sâu)  RIGHT
            |          |
          ...        TARGET = 42
            |
         nhiều nút
```

Nếu duyệt tuần tự từ trái sang phải, chương trình có thể tốn nhiều công việc vô ích trước khi sang nhánh phải. Nếu dùng Fork/Join, mỗi nhánh có thể thành một task nhỏ để worker rảnh **work-steal** và xử lý. Vì cây không đều nên các worker không nhất thiết nhận khối lượng công việc bằng nhau; cơ chế work-stealing giúp giảm mất cân bằng khi có đủ task.

Nhưng yêu cầu tìm kiếm thường là **tìm được bất kỳ một phần tử thỏa điều kiện**, không nhất thiết là phần tử nhỏ nhất theo thứ tự duyệt. Khi một nhánh thấy `42`, ta có thể trả kết quả sớm và để các nhánh khác **tự kiểm tra tín hiệu dừng**.

Cần xác định hợp đồng trước:

- **Find any:** chấp nhận một trong nhiều match; có thể dùng CAS để chọn đúng một “winner”. Kết quả có thể khác giữa các lần chạy nếu có nhiều match.
- **Find first/min index:** phải bảo đảm thứ tự lựa chọn; chỉ lấy match đầu tiên do scheduler tìm được **không đúng**. Cần thuật toán so sánh vị trí/tối ưu hóa khác và chỉ kết luận khi các nhánh có thể chứa đáp án ưu tiên đã được xử lý.
- **Stop early:** yêu cầu hợp tác để bớt công việc, không phải bảo đảm tất cả worker bị interrupt ngay lập tức.

Các ví dụ dưới đây chọn **find any** và chỉ có một nút match, nên kết quả in ra **xác định**.

## 2. CountedCompleter khác RecursiveTask thế nào?

`RecursiveTask<V>` thường được viết theo kiểu: chia đôi, `left.fork()`, `right.compute()`, `left.join()`, rồi cộng kết quả. Cây tính toán có quan hệ khá rõ: task cha chờ kết quả con để gộp.

`CountedCompleter<T>` cho phép mô hình linh hoạt hơn:

- Task có **completer cha**, nhưng không bắt buộc đợi trực tiếp từng child bằng `join()`.
- Mỗi task có **pending count** để biểu thị những tín hiệu hoàn tất còn cần trước khi có thể complete nó.
- Child khi hoàn tất gọi `tryComplete()`; việc complete có thể truyền ngược chuỗi completer.
- Task có thể override `onCompletion(CountedCompleter<?> caller)` để gộp/hoàn thiện khi đủ công việc.
- Một nhánh có đáp án có thể gọi `quietlyCompleteRoot()` để đánh dấu root hoàn tất mà **không phải đợi cây pending về 0**.
- Vì result mặc định của `CountedCompleter` không tự là giá trị tìm thấy, ta có thể công bố winner qua `AtomicReference` hoặc tự triển khai giao thức result đúng cách.

| Thành phần | Ý nghĩa thực tế |
|---|---|
| `CountedCompleter<T>` | Base class cho task có cơ chế hoàn tất dạng pending/completer. |
| `new Child(this, ...)` | Đặt task hiện tại làm completer cha. |
| `setPendingCount(n)` | Thiết lập số lượng tín hiệu pending theo giao thức của thuật toán. |
| `addToPendingCount(n)` | Tăng số pending nếu phát sinh thêm công việc. |
| `fork()` | Đưa child task vào cơ chế lập lịch Fork/Join. |
| `tryComplete()` | Báo một lần hoàn tất/đã đến điểm cuối nhánh; có thể giảm pending hoặc complete và truyền lên cha. |
| `onCompletion(caller)` | Callback khi task thực sự được complete qua đường `tryComplete()`. |
| `quietlyCompleteRoot()` | Đánh dấu **root** đã hoàn tất ngay, không phải chờ toàn bộ các child. |

**Quan trọng:** `pending count` không phải chính là số thread, số node còn trong queue hoặc `CountDownLatch`. Nó là **giao thức completion** do code xây dựng. Đặt count sai hoặc thiếu `tryComplete()` có thể khiến root chờ mãi khi **không tìm được** đáp án.

## 3. Hiểu chính xác giao thức pending count

Ta dùng pattern nhất quán sau cho một node có `n` child:

```java
@Override
public void compute() {
    int n = node.children.length;
    setPendingCount(n);

    for (Node child : node.children) {
        new SearchTask(this, child, shared).fork();
    }

    tryComplete();
}
```

Đây là **trích đoạn**, cần định nghĩa các class và biến `node`/`shared`. Mỗi child cũng gọi `tryComplete()` khi xong. Cách đếm:

- Parent đặt pending = `n`.
- Parent tự gọi `tryComplete()` sau khi fork; việc này được xem là **một lượt tham gia** của parent trong giao thức.
- Mỗi child hoàn tất sẽ gọi `tryComplete()`; khi child không có pending, nó truyền một lượt hoàn tất cho completer cha.
- Trong số `n + 1` lượt (parent + n child), **n lượt đầu** làm pending giảm tới 0; **lượt cuối** thấy count bằng 0 nên thực sự complete parent và có thể truyền tiếp lên cha.

Do parent và các child chạy đồng thời, thứ tự các lượt là **không xác định**. Không giả định “parent luôn là lượt đầu tiên” hoặc “child cuối theo thứ tự danh sách sẽ thực hiện callback”. Pattern trên đúng nhờ số lượng tín hiệu và biến đếm nguyên tử, không nhờ lịch chạy.

Với **leaf** không có child, pending mặc định = 0; gọi `tryComplete()` sẽ hoàn thành leaf và báo tiếp cho completer cha.

Đây chỉ là **một convention hợp lệ**, không phải cách duy nhất dùng CountedCompleter. Một pattern khác có thể fork `n-1` child, tự tính child còn lại rồi thay đổi pending tương ứng. Điều quan trọng là **số pending và số lượt `tryComplete` thực tế phải khớp**.

## 4. Quy trình tìm kiếm song song và dừng sớm

Một `SearchTask` sẽ làm như sau:

```text
SearchTask.compute()
       |
       v
winner != null ? -------- yes ------> tryComplete(); return
       |
       no
       |
node thỏa predicate ? ---- yes -----> CAS(null, node)
       |                                   |
       |                              CAS thắng?
       |                                   |
       |                                  yes
       |                                   v
       |                             quietlyCompleteRoot()
       |                                   |
       |                              tryComplete()
       |
       no
       |
setPendingCount(children.length)
       |
fork từng child với completer = this
       |
tryComplete()
```

Một `AtomicReference<Node>` giữ match đầu tiên được commit. Khi nhiều worker cùng tìm thấy match, `compareAndSet(null, node)` chỉ có **một lần thắng**. Những worker khác đọc `winner.get() != null` rồi bỏ qua phần công việc còn chưa bắt đầu.

Từ “dừng sớm” ở đây có hai cấp độ:

1. **Dừng chờ ở root:** winner thắng gọi `quietlyCompleteRoot()`; các thread chờ root có thể lấy kết quả ngay.
2. **Giảm tính toán còn lại:** các nhánh khác phải **tự kiểm tra winner** và trả về ở điểm an toàn. Nếu một task đang tính toán dài hoặc blocking mà không kiểm tra, nó vẫn có thể tiếp tục sau khi root complete.

Không gọi `Thread.stop()` hoặc dựa vào `ForkJoinTask.cancel(true)` để cưỡng bức chấm dứt task. Trong ForkJoinTask, `mayInterruptIfRunning` không có tác dụng như một lời hứa interrupt worker theo kiểu `FutureTask`. Với phép tính CPU, kiểm tra cờ winner/cancellation flag định kỳ là phương pháp hợp tác phù hợp.

## 5. Ví dụ 1 — Tìm một nút trong cây không đều

Ta tạo cây có một nhánh trái kéo dài và các nhánh phải ngắn. Root chia việc cho các child, worker rảnh có thể steal task. Nếu một nhánh tìm được `42`, nó ghi winner bằng CAS và gọi `quietlyCompleteRoot()`.

Tạo file **`CountedCompleterIrregularSearch.java`**:

```java
import java.util.concurrent.CountedCompleter;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class CountedCompleterIrregularSearch {
    static final class Node {
        final int value;
        final Node[] children;

        Node(int value, Node... children) {
            this.value = value;
            this.children = children;
        }
    }

    static final class SearchTask extends CountedCompleter<Void> {
        private final Node node;
        private final AtomicReference<Node> winner;

        SearchTask(
                CountedCompleter<?> parent,
                Node node,
                AtomicReference<Node> winner) {
            super(parent);
            this.node = node;
            this.winner = winner;
        }

        @Override
        public void compute() {
            if (winner.get() != null) {
                tryComplete();
                return;
            }

            if (node.value == 42) {
                if (winner.compareAndSet(null, node)) {
                    quietlyCompleteRoot();
                }
                tryComplete();
                return;
            }

            setPendingCount(node.children.length);
            for (Node child : node.children) {
                new SearchTask(this, child, winner).fork();
            }
            tryComplete();
        }
    }

    static Node irregularBranch(int levels) {
        Node current = new Node(-1);
        for (int i = 0; i < levels; i++) {
            current = new Node(-1, current, new Node(-1));
        }
        return current;
    }

    public static void main(String[] args)
            throws InterruptedException {
        Node rootNode = new Node(
                -1,
                irregularBranch(12),
                new Node(-1, new Node(42))
        );

        AtomicReference<Node> winner = new AtomicReference<>();
        SearchTask root = new SearchTask(null, rootNode, winner);
        ForkJoinPool pool = new ForkJoinPool(4);

        try {
            pool.invoke(root);
            Node found = winner.get();
            System.out.println("Found: "
                    + (found == null ? "none" : found.value));
            System.out.println("Root done: " + root.isDone());
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
                pool.shutdownNow();
                throw new IllegalStateException("Pool did not terminate");
            }
        }
    }
}
```

Lệnh chạy JDK 17+:

```bash
javac CountedCompleterIrregularSearch.java
java CountedCompleterIrregularSearch
```

Kết quả khi không bị tác động bởi interrupt/thiếu tài nguyên bên ngoài:

```text
Found: 42
Root done: true
```

**Giải thích:**

- `irregularBranch(12)` tạo một nhánh có 12 tầng, tại mỗi tầng có thêm một nhánh con ngắn. Nhánh bên phải của root chỉ có nút trung gian rồi đến `42`.
- `SearchTask` của mỗi node tự `setPendingCount(children.length)`, fork các child và gọi `tryComplete()`. Các leaf gọi `tryComplete()` để báo kết thúc; nếu không có match, tín hiệu hoàn tất truyền ngược về root.
- Khi match được tìm thấy, `winner.compareAndSet(null,node)` chọn kết quả đầu tiên; `quietlyCompleteRoot()` làm root hoàn tất để `pool.invoke(root)` có thể trở về.
- **Không có cam kết match được tìm trước khi worker khác đã duyệt hết nhánh dài.** Work-stealing, thứ tự thực thi và độ sâu scheduling là không xác định. Điều được bảo đảm ở ví dụ là giá trị match duy nhất.
- Sau khi `pool.invoke(root)` trả về, main có thể chưa biết tất cả child đã xong. `pool.shutdown()` cùng `awaitTermination()` được dùng để quản lý lifecycle của **pool riêng** trước khi thoát chương trình.

### Vì sao dùng AtomicReference thay vì volatile Node?

Vì thuật toán có thể có **nhiều match** khi mở rộng dữ liệu. `volatile Node winner` cho phép reader thấy reference được ghi, nhưng hai writer có thể cùng kiểm tra `winner == null` rồi ghi đè nhau. CAS trên `AtomicReference` cho phép **chỉ một winner được commit**. Nếu bài toán chấp nhận bất kỳ match và không cần tính duy nhất của lượt commit, volatile có thể đủ trong thiết kế khác; nhưng với “first successful claim” CAS rõ ràng và dễ kiểm chứng.

Nếu muốn **nút có key nhỏ nhất** hoặc **vị trí nhỏ nhất**, việc chọn “worker đầu tiên thắng CAS” **không đảm bảo** kết quả đó. Phải chỉnh thuật toán chọn kết quả và điểm có thể kết luận sớm theo thứ tự ưu tiên.

## 6. Tại sao CountedCompleter mặc định không trả về winner?

Đừng giả định:

```java
CountedCompleter<Node> root = ...;
Node result = pool.invoke(root);
```

sẽ tự trả về `Node` vừa tìm được. Đây chỉ là trích đoạn kiểu, không phải chương trình. `CountedCompleter` **mặc định không tích hợp cơ chế lưu kết quả giá trị** như `RecursiveTask.compute()` trả `V`; implementation mặc định của `getRawResult()` là `null`. Nếu muốn trả trực tiếp dữ liệu qua `ForkJoinTask`, phải triển khai result protocol thích hợp và bảo đảm publish/complete đúng.

Các ví dụ dùng `CountedCompleter<Void>` cho completion và một `AtomicReference<Node>` cho winner. Vì CAS công bố winner **trước** `quietlyCompleteRoot()`, caller sau khi nhận root-completion và đọc AtomicReference có thể lấy kết quả đã công bố. Điều này rõ ràng hơn việc kỳ vọng `invoke()` tự trả Node.

**Không nhầm:** `quietlyCompleteRoot()` đặt trạng thái completion của root nhưng không chạy `onCompletion()` cho root bằng cách giả lập đủ pending, và không tự động thực thi cleanup của các child. Nếu cần gộp kết quả/cleanup ở `onCompletion()`, không được coi quietlyCompleteRoot là tương đương completion bình thường của toàn cây.

## 7. Ví dụ 2 — Chứng minh root kết thúc trước nhánh chậm

Để chứng minh **early completion không đồng nghĩa mọi child đã dừng**, ta tạo hai nhánh:

- **SLOW:** đã bắt đầu, nhưng chờ một latch `releaseSlow` chưa mở.
- **HIT:** chờ cho SLOW bắt đầu, rồi tìm thấy đáp án và gọi `quietlyCompleteRoot()`.
- Main đợi root hoàn tất; khi đó SLOW **chắc chắn chưa được release** nên còn chưa đi qua cleanup. Main in kết quả, sau đó mở latch để SLOW tiếp tục và chờ pool thực sự terminated.

Đây là ví dụ điều phối có chủ đích. **Blocking trong ForkJoin worker không phải mẫu hiệu năng được khuyến cáo** cho workload thực tế; dùng latch chỉ để chứng minh sự khác nhau về completion.

Tạo file **`CountedCompleterEarlyStop.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.CountedCompleter;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;

public class CountedCompleterEarlyStop {
    enum Kind { ROOT, SLOW, HIT }

    static final class SearchTask extends CountedCompleter<Void> {
        private final Kind kind;
        private final CountDownLatch slowStarted;
        private final CountDownLatch releaseSlow;
        private final AtomicReference<String> winner;
        private final AtomicBoolean slowFinished;

        SearchTask(
                CountedCompleter<?> parent,
                Kind kind,
                CountDownLatch slowStarted,
                CountDownLatch releaseSlow,
                AtomicReference<String> winner,
                AtomicBoolean slowFinished) {
            super(parent);
            this.kind = kind;
            this.slowStarted = slowStarted;
            this.releaseSlow = releaseSlow;
            this.winner = winner;
            this.slowFinished = slowFinished;
        }

        private SearchTask child(Kind childKind) {
            return new SearchTask(
                    this, childKind, slowStarted,
                    releaseSlow, winner, slowFinished
            );
        }

        @Override
        public void compute() {
            if (kind == Kind.ROOT) {
                setPendingCount(2);
                child(Kind.SLOW).fork();
                child(Kind.HIT).fork();
                tryComplete();
                return;
            }

            if (kind == Kind.SLOW) {
                slowStarted.countDown();
                try {
                    releaseSlow.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                } finally {
                    slowFinished.set(true);
                }
                tryComplete();
                return;
            }

            // HIT chỉ tìm ra đáp án sau khi SLOW bắt đầu.
            try {
                slowStarted.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(e);
            }

            if (winner.compareAndSet(null, "HIT")) {
                quietlyCompleteRoot();
            }
            tryComplete();
        }
    }

    public static void main(String[] args) throws Exception {
        CountDownLatch slowStarted = new CountDownLatch(1);
        CountDownLatch releaseSlow = new CountDownLatch(1);
        AtomicReference<String> winner = new AtomicReference<>();
        AtomicBoolean slowFinished = new AtomicBoolean();
        ForkJoinPool pool = new ForkJoinPool(3);

        SearchTask root = new SearchTask(
                null, Kind.ROOT, slowStarted, releaseSlow,
                winner, slowFinished
        );

        try {
            pool.submit(root);
            root.get(5, TimeUnit.SECONDS);

            System.out.println("Found: " + winner.get());
            System.out.println("Root done: " + root.isDone());
            System.out.println("Slow finished before release: "
                    + slowFinished.get());
        } finally {
            releaseSlow.countDown();
            pool.shutdown();
            if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
                pool.shutdownNow();
                throw new IllegalStateException("Pool did not terminate");
            }
        }

        System.out.println("Slow finished after release: "
                + slowFinished.get());
    }
}
```

```bash
javac CountedCompleterEarlyStop.java
java CountedCompleterEarlyStop
```

Đầu ra khi không có external interrupt:

```text
Found: HIT
Root done: true
Slow finished before release: false
Slow finished after release: true
```

**Đây là mấu chốt của dừng sớm:**

1. Root đặt pending=2 và fork hai child.
2. SLOW báo đã bắt đầu rồi đợi latch. HIT đợi đúng tín hiệu đó trước khi công bố kết quả.
3. HIT CAS winner và gọi `quietlyCompleteRoot()`; `root.get()` có thể trả về trong khi SLOW vẫn chưa được release.
4. Vì SLOW chỉ đặt `slowFinished=true` khi rời khỏi `await()`, main thấy **false** tại thời điểm root đã done.
5. Cuối cùng main mở latch, pool được shutdown và chờ termination; sau đó SLOW đã đặt flag true.

Chỉ vì `root.isDone() == true` **không** suy ra tất cả child đã hoàn tất. Đây là lý do thuật toán sản xuất phải cân nhắc ownership: nếu task con còn dùng stream, file hoặc dữ liệu dùng chung, caller không nên đóng tài nguyên của chúng chỉ vì root đã được quietly complete.

Trong ví dụ, nhánh SLOW cố ý **không tự dừng khi winner xuất hiện** để chứng minh ranh giới này. Ở thuật toán tìm kiếm thực, các nhánh phải kiểm tra winner thường xuyên và kết thúc hợp tác tại điểm an toàn.

## 8. Ví dụ 3 — Khi không có kết quả, phải chờ toàn bộ cây

Một thuật toán tìm kiếm cần xử lý cả trường hợp **không có match**. Khi đó không ai gọi `quietlyCompleteRoot()`; root chỉ hoàn tất khi **toàn bộ nhánh đã báo đủ** qua `tryComplete()`. Nếu quên một child, đặt pending count sai hoặc return sớm mà không gọi `tryComplete()`, root có thể treo vĩnh viễn.

Ví dụ này chia một mảng thành các đoạn và cố tìm giá trị không tồn tại. Mỗi leaf tăng một bộ đếm cho mỗi phần tử đã kiểm tra. Vì không có match, sau `pool.invoke(root)` bộ đếm phải bằng tổng số phần tử.

Tạo file **`CountedCompleterNoMatch.java`**:

```java
import java.util.concurrent.CountedCompleter;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.atomic.AtomicInteger;

public class CountedCompleterNoMatch {
    static final class ScanTask extends CountedCompleter<Void> {
        private final int[] data;
        private final int from;
        private final int to;
        private final int target;
        private final AtomicInteger visited;

        ScanTask(
                CountedCompleter<?> parent,
                int[] data, int from, int to,
                int target, AtomicInteger visited) {
            super(parent);
            this.data = data;
            this.from = from;
            this.to = to;
            this.target = target;
            this.visited = visited;
        }

        @Override
        public void compute() {
            if (to - from <= 4) {
                for (int i = from; i < to; i++) {
                    visited.incrementAndGet();
                    if (data[i] == target) {
                        throw new IllegalStateException(
                                "Unexpected target"
                        );
                    }
                }
                tryComplete();
                return;
            }

            int middle = from + (to - from) / 2;
            setPendingCount(2);
            new ScanTask(
                    this, data, from, middle, target, visited
            ).fork();
            new ScanTask(
                    this, data, middle, to, target, visited
            ).fork();
            tryComplete();
        }
    }

    public static void main(String[] args) {
        int[] data = new int[32];
        for (int i = 0; i < data.length; i++) {
            data[i] = i;
        }

        AtomicInteger visited = new AtomicInteger();
        ScanTask root = new ScanTask(
                null, data, 0, data.length, 99, visited
        );
        ForkJoinPool pool = new ForkJoinPool(4);

        try {
            pool.invoke(root);
            System.out.println("All checked: "
                    + (visited.get() == data.length));
            System.out.println("Visited: " + visited.get());
            System.out.println("Root done: " + root.isDone());
        } finally {
            pool.shutdown();
        }
    }
}
```

```bash
javac CountedCompleterNoMatch.java
java CountedCompleterNoMatch
```

Kết quả:

```text
All checked: true
Visited: 32
Root done: true
```

Tất cả `[from,to)` không giao nhau, được chia cho tới đoạn tối đa bốn phần tử. Mỗi phần tử chỉ tăng `visited` một lần. Không có target=99, vì vậy **không có early completion**; giao thức pending và `tryComplete()` phải kết thúc đầy đủ để `pool.invoke(root)` trở về. `AtomicInteger` cho bộ đếm demo giúp các nhánh tăng cùng một counter mà không mất cập nhật.

Trong một ứng dụng tìm kiếm thật, thay vì ném exception khi có match, ta sẽ dùng `AtomicReference` và quy tắc winner như ví dụ 1. Ví dụ 3 cố ý **chỉ kiểm tra đường no-match**, một tình huống nhiều implementation CountedCompleter viết sai vì thiết kế chỉ nghĩ đến trường hợp tìm thấy sớm.

## 9. Root completion, child completion và cleanup

Trên lý thuyết có ba mốc khác nhau:

```text
match phát hiện
     |
     v
winner.compareAndSet(null, value)
     |
     v
quietlyCompleteRoot()
     |
     +---- root.get()/join()/invoke() có thể trở về
     |
     +---- các task con khác có thể vẫn đang chạy
                              |
                              v
                      hợp tác dừng hoặc hoàn tất
                              |
                              v
                       toàn bộ task kết thúc
                              |
                              v
                  cleanup/pool termination (khi có)
```

Không được coi root completion đồng nghĩa với `pool.awaitTermination()`. Với pool riêng mà ứng dụng sở hữu, có thể shutdown và đợi termination sau khi root hoàn tất; với **commonPool**, không được tự shutdown pool chia sẻ chỉ để chờ nhánh con của một request.

Để quản lý các nhánh còn hoạt động khi root đã completed:

- Chỉ **đọc dữ liệu chung immutable** hoặc truy cập theo giao thức synchronization.
- Cho mỗi nhánh kiểm tra `winner != null` trước khi mở rộng cây và **định kỳ trong leaf lớn**.
- Không giữ lock/resource ở caller rồi đóng ngay sau `root.get()` nếu task khác còn sử dụng chúng.
- Nếu cần bảo đảm **mọi child đã dừng trước khi trả ra ngoài**, thuật toán phải có **mốc completion toàn bộ cây riêng**, hoặc không gọi quietlyCompleteRoot trước khi mọi child đã xong. Đánh dấu root done sớm và đợi mọi child là hai mục tiêu khác nhau.
- Nếu có cancellation thật, truyền cờ dừng và định nghĩa điểm hủy an toàn. `ForkJoinTask.cancel(true)` không có nghĩa interrupt toàn bộ child task đã fork.

**Quan hệ bộ nhớ:** lời CAS winner thành công và các lần đọc `AtomicReference.get()` có hiệu ứng bộ nhớ tương ứng với đọc/ghi volatile theo Java Memory Model. Điều đó giúp công bố result an toàn. Việc root complete chỉ là mốc completion của root; **không chứng minh các ghi chưa xảy ra của child khác đã hoàn tất hoặc có thể quan sát**.

## 10. Work-stealing giúp tìm kiếm không đều ra sao?

Trong cây không đều, có nhánh chứa nhiều node hơn hẳn nhánh khác. Nếu chia theo `ForkJoinTask`, một worker rảnh có thể **steal** task đang chờ từ deque của worker bận, tăng cơ hội xử lý nhánh nhanh độc lập.

Nhưng work-stealing **không cam kết**:

- Một nhánh cụ thể được chạy trước nhánh khác.
- Nhánh chứa match luôn được tìm trước.
- `parallelism=4` nghĩa có đúng bốn task chạy đồng thời mọi lúc.
- Tốc độ tìm kiếm luôn tăng tuyến tính theo số lõi.
- Task con được tự động hủy sau khi root completed.

Với nhánh nhỏ, overhead fork/steal có thể còn lớn hơn tự duyệt tuần tự. Với cây rất sâu hoặc có rất nhiều node, fork tại mỗi node có thể tạo số task lớn, gây áp lực cấp phát và quản lý completion.

**Threshold phù hợp:** chỉ fork khi subtree đủ lớn (có thể ước lượng bằng kích thước/độ sâu/chi phí), còn subtree nhỏ thì duyệt tuần tự có kiểm tra winner. Ví dụ đầu tiên fork mỗi node để phơi bày cơ chế CountedCompleter; đó là **ví dụ giáo dục**, chưa phải cấu hình benchmark/production tối ưu.

## 11. Tránh các lỗi phổ biến

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Fork `n` child nhưng đặt pending sai số tín hiệu. | Root có thể không complete khi no-match, hoặc complete quá sớm. | Chọn convention rõ và kiểm thử đường no-match. |
| Quên gọi `tryComplete()` ở leaf hoặc nhánh bỏ qua vì winner đã có. | Completer chain không nhận đủ completion; tree không kết thúc bình thường. | Gọi `tryComplete()` trong mọi đường exit phù hợp. |
| Gọi `quietlyCompleteRoot()` rồi nghĩ tất cả child bị cancel. | Task còn chạy, dùng resource chưa được cleanup. | Cooperative checks và mốc xác nhận toàn bộ child. |
| Ghi `winner = node` mà nhiều thread cùng ghi. | Match có thể bị ghi đè; chọn winner không rõ. | `AtomicReference.compareAndSet(null, node)`. |
| Bảo đảm “first match theo thứ tự” bằng CAS first writer. | Chọn theo scheduler, không theo vị trí ưu tiên. | Thiết kế deterministic ordering và điểm được phép kết luận. |
| Giữ một shared mutable accumulator không đồng bộ. | Lost update hoặc đọc kết quả chưa nhất quán. | Immutable results, atomic/lock hoặc phân vùng. |
| Đặt `pendingCount=0` và complete parent trước khi child fork xong. | Bỏ mất child/hoàn tất sớm ngoài ý muốn. | Thiết lập pending trước khi fork, hoàn tất theo giao thức. |
| Gọi `tryComplete()` quá số lần đối với một nhánh. | Có thể complete sai/callback không đúng dự kiến. | Một protocol rõ và chỉ báo khi công việc thuộc nhánh xong. |
| Phụ thuộc vào `onCompletion()` của root sau quietlyCompleteRoot. | Callback có thể không chạy theo đường complete sớm. | Tách winner publication và cleanup khỏi callback chỉ được gọi khi bình thường. |
| Bỏ qua trường hợp không có match. | Root có thể chờ vô hạn khi mọi leaf đều không tìm thấy. | Test no-match và đếm đủ toàn bộ phân nhánh. |
| Dùng ForkJoinPool cho nhiều I/O blocking dài. | Worker bị giữ, giảm tiến triển hoặc deadlock. | Ưu tiên API/executor phù hợp hoặc managedBlock khi có lý do. |
| Fork task cho mỗi node cực nhỏ mà không đánh giá overhead. | Task creation/stealing đắt hơn duyệt cây. | Batch/traversal tuần tự ở subtree nhỏ. |

## 12. Exceptions, hủy và trạng thái bất thường

`CountedCompleter` vẫn là một `ForkJoinTask`, có trạng thái hoàn tất bình thường, ngoại lệ hoặc canceled. Một exception không được xử lý trong `compute()` có thể dẫn tới hoàn tất bất thường, nhưng không nên giả định rằng mọi child sẽ tự động dừng hoặc mọi resource đã được giải phóng.

Điểm lưu ý:

1. Nếu `compute()` ném exception trước khi gọi `tryComplete()`, cần hiểu đường **exceptional completion** và `onExceptionalCompletion()` theo API; không “nuốt” lỗi rồi khiến pending tree bị mắc kẹt.
2. Nếu có nhiều child lỗi, thiết kế phải xác định lỗi nào được báo cho caller và child còn lại được phép làm gì.
3. Nếu root đã quietly completed do một match, exception đến sau từ child khác không thể tự động biến lời get đã thành công thành rollback.
4. Khi dùng `get(timeout)`, `TimeoutException` chỉ giới hạn lần chờ của caller; nó **không tự hủy tree**.
5. `ForkJoinTask.cancel(true)` không phải cơ chế cưỡng bức interrupt các child đang thực hiện; cần cờ hợp tác.
6. Nếu kết quả yêu cầu side effect (gửi yêu cầu, ghi file), tránh đặt hành động ngoài JVM trong một vùng có thể thực hiện cạnh tranh bởi nhiều worker mà không có idempotency/transaction.

Một cách an toàn là **tách tìm ra winner** (CAS, không có side effect) khỏi **hành động nghiệp vụ trên winner**. Caller xử lý winner sau khi có mốc completion cần thiết, đồng thời xác định các child còn lại có thể tiếp tục truy cập gì.

## 13. CountedCompleter và RecursiveTask: chọn kiểu nào?

| Bài toán | Thường phù hợp | Lý do |
|---|---|---|
| Tổng mảng/chia đôi và đợi cả hai nửa | `RecursiveTask<Long>` | Return result và `join()` để combine đơn giản. |
| Sửa các đoạn mảng không giao nhau, đợi toàn bộ | `RecursiveAction` | Không cần giá trị trả về; có thể `invokeAll()`. |
| Cây công việc động, fan-out không đều, hoàn tất theo tín hiệu con | `CountedCompleter` | Pending/completer chain linh hoạt. |
| “Find any” và cho root có thể trả sớm sau match | `CountedCompleter` + atomic winner | `quietlyCompleteRoot()` cho early root completion. |
| Tìm kết quả phải đúng thứ tự ưu tiên | Thuật toán có ordering/completion proof riêng | CAS first winner theo lịch chạy chưa đủ. |
| Một lời tìm kiếm đơn giản, dữ liệu nhỏ | Vòng lặp/đệ quy tuần tự | Dễ kiểm chứng, không tốn task scheduling. |

Nếu bài toán chỉ cần fork trái, compute phải, join trái, `RecursiveTask` thường dễ đọc và dễ bảo trì hơn. `CountedCompleter` mạnh nhưng **phức tạp hơn ở protocol pending**, vì vậy nên dùng khi lợi ích từ cây hoàn tất động/early completion thật sự đáng giá.

## 14. Checklist xây dựng tìm kiếm dừng sớm đúng

1. **Định nghĩa kết quả:** tìm một match bất kỳ hay match đầu tiên theo thứ tự?
2. **Chọn dữ liệu chia việc:** cây/đồ thị/khối tìm kiếm độc lập, tránh việc nhiều task sửa cùng dữ liệu không đồng bộ.
3. **Xác định base case:** không child thì kiểm tra predicate rồi `tryComplete()`.
4. **Quy định pending:** với convention ở ví dụ, `setPendingCount(n)`, fork n child, parent gọi `tryComplete()`, từng child cũng báo hoàn tất.
5. **Đặt pending trước fork:** child có thể hoàn tất rất nhanh.
6. **Công bố winner nguyên tử:** `AtomicReference.compareAndSet(null, found)`.
7. **Early root completion có chủ đích:** chỉ winner hợp lệ gọi `quietlyCompleteRoot()`.
8. **Cooperative stop:** mọi nhánh đọc winner trước khi mở rộng, các leaf dài cũng kiểm tra định kỳ.
9. **Không dùng root done thay cho all children done:** nếu cần cleanup toàn cây, có mốc xác nhận khác.
10. **Kiểm thử no-match:** root phải complete bình thường khi toàn bộ leaf không tìm thấy.
11. **Kiểm thử multi-match:** kết quả thỏa predicate nhưng không mặc định ưu tiên nhỏ nhất.
12. **Kiểm thử cây không đều:** nhánh sâu/ngắn, child hoàn tất trước parent và thứ tự chạy thay đổi.
13. **Kiểm thử timeout và lỗi:** task không hợp tác, exception ở leaf, cancel giữa chừng.
14. **Đo hiệu năng:** so với duyệt tuần tự, điều chỉnh threshold, quan sát overhead tạo task, work-stealing và GC.
15. **Quản lý pool:** phân biệt root completion và termination của pool riêng; không shutdown common pool do một request.

## 15. Tự kiểm tra kiến thức

1. **`CountedCompleter` có luôn dùng `join()` để đợi từng child không?** Không; pending count và `tryComplete()` phối hợp completion.
2. **`setPendingCount(n)` có tự fork n task không?** Không; code phải tạo/fork task và phát tín hiệu completion tương ứng.
3. **Vì sao đặt pending trước khi fork?** Child có thể chạy rất nhanh và báo hoàn tất trước khi parent kết thúc compute.
4. **`quietlyCompleteRoot()` làm gì?** Đánh dấu root hoàn tất sớm, không tự hủy các child.
5. **Sau root.get() thành công có thể đóng ngay resource mà child còn dùng không?** Không nếu root completed sớm; cần quản lý ownership và child termination.
6. **Tại sao dùng `AtomicReference.compareAndSet(null, node)`?** Chỉ một worker được quyền công bố winner khi nhiều match cạnh tranh.
7. **Khi không có match, điều gì khiến root hoàn tất?** Mọi nhánh báo đủ `tryComplete()` theo pending protocol.
8. **`CountedCompleter.getRawResult()` mặc định có trả winner không?** Không; phải tự thiết kế result storage/protocol hoặc dùng atomic winner ngoài.
9. **`onCompletion()` có được đảm bảo chạy chỉ vì gọi quietlyCompleteRoot() không?** Không; early completion là đường khác với normal pending completion.
10. **Work-stealing có bảo đảm nhánh match được chạy đầu tiên không?** Không, lịch chạy và fan-out không cố định.
11. **Nếu có hai match, CAS first winner có đảm bảo vị trí nhỏ nhất không?** Không; người thắng phụ thuộc cạnh tranh.
12. **Vì sao cần kiểm tra winner trong leaf lớn?** Để bớt công việc sau khi nhánh khác tìm ra đáp án.
13. **`cancel(true)` của ForkJoinTask có chắc interrupt worker đang chạy không?** Không; cần dừng hợp tác.
14. **Khi nào RecursiveTask đơn giản hơn?** Khi phải xử lý tất cả nhánh và gộp kết quả rõ bằng join.
15. **Vì sao CountedCompleter khó hơn?** Vì correctness phụ thuộc protocol pending signals, early completion và lifecycle của các child.

**Ghi nhớ:** `CountedCompleter` dùng **pending count + tryComplete()** để điều phối cây công việc, còn **AtomicReference + quietlyCompleteRoot()** giúp công bố một match và giải phóng caller khỏi việc đợi toàn cây. **Root done sớm không đồng nghĩa mọi child đã dừng**: cooperative cancellation, ownership và cleanup phải được thiết kế riêng.

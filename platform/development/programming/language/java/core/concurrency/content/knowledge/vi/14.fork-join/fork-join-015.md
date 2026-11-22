# Thiết lập pending count trước khi fork để tránh hoàn tất sớm trong Java CountedCompleter

> **Phạm vi:** cơ chế **Fork/Join** của Java SE 17+, tập trung vào `java.util.concurrent.CountedCompleter` và thứ tự **đăng ký pending completions trước khi gọi `fork()`**. Bài học giải thích mô hình completion theo cây, cơ chế `tryComplete()`, lỗi root hoàn tất sớm, biến thể đếm “off by one”, bảo đảm dữ liệu và các bài thực hành có thể biên dịch/chạy. Chỉ đề cập **Java concurrency nói chung**, không trộn với cơ chế Fork/Join hay scheduling dành riêng cho Spring.

## 1. Vấn đề cốt lõi: task con có thể hoàn thành ngay sau fork

Trong Fork/Join, `fork()` làm một `ForkJoinTask` đủ điều kiện được xử lý bất đồng bộ. Không có bảo đảm thread cha sẽ chạy xong những dòng tiếp theo trước khi một worker khác hoàn thành task con.

Với `CountedCompleter`, mỗi task duy trì một **pending count** mô tả số tín hiệu completion còn phải được ghi nhận theo **giao thức mà người viết thuật toán chọn**. Khi task con hoàn tất, nó có thể lan tín hiệu completion lên task cha thông qua `tryComplete()`.

Nếu thread cha **fork con trước rồi mới set pending count**, task con có thể gọi `tryComplete()` khi cha vẫn có pending count mặc định bằng **0**. Khi đó đường completion thấy cha “không còn pending” và có thể gọi `onCompletion`, lan lên ông/bà hoặc đánh dấu root đã hoàn tất **trước khi những phần việc con khác kết thúc**.

**Quy tắc vàng:**

```java
setPendingCount(numberOfChildren);  // Đăng ký trước
child1.fork();
child2.fork();
tryComplete();                       // Tín hiệu phần việc của node hiện tại
```

Đây là **pseudocode Java minh họa bên trong `compute()`**, với `child1`, `child2` là các `CountedCompleter` có `this` làm completer và `numberOfChildren` tương ứng với số con thực sự fork. Trong biến thể này, nếu có hai child cần đợi thì dùng `setPendingCount(2)`. Không được quên `tryComplete()` của chính parent, hoặc thiết kế counting tương đương khác.

Trọng tâm là thứ tự **register-before-publish**: hoàn tất việc đăng ký dependencies trước khi công bố task con để worker khác có thể thực thi.

## 2. Phân biệt CountedCompleter với RecursiveTask/RecursiveAction

Java Fork/Join có nhiều kiểu task:

| Kiểu | Mô hình completion | Khi nào phù hợp |
|---|---|---|
| `RecursiveTask<V>` | `compute()` trả V; thường `fork()` rồi `join()` con để kết hợp kết quả | Divide-and-conquer cần trả kết quả lên cây |
| `RecursiveAction` | `compute()` không trả V; thường `join()`/`invokeAll` con | Tác vụ song song không trả về giá trị trực tiếp |
| `CountedCompleter<T>` | Hoàn tất bằng **pending completion signals**, `tryComplete` và optional `onCompletion`; không nhất thiết gọi `join` từng con | Completion tree, fan-out, traverse, map/reduce, phối hợp nhiều nhánh mà không blocking join theo cách cổ điển |

`CountedCompleter<T>` kế thừa `ForkJoinTask<T>` và là một abstract class. Một class cụ thể phải triển khai `compute()`; có thể override `onCompletion(CountedCompleter<?> caller)` hoặc `onExceptionalCompletion(Throwable, CountedCompleter<?> caller)` khi cần.

Lớp này thường được khai báo `CountedCompleter<Void>` nếu không cần trả một giá trị qua `invoke()`/`join()`. Khi có kết quả thực sự, cần hiểu `getRawResult()` và cách publish/đọc result; không tự suy rằng kết quả của các child được cộng lại bởi `CountedCompleter`.

**Khác biệt quan trọng:** với `RecursiveTask`, việc `join()` một child thường rõ ràng là ranh giới “đợi child”. Với `CountedCompleter`, **parent root completion phụ thuộc vào số lần báo complete đúng**. Nếu đếm sai hoặc gọi `tryComplete` sai, root có thể hoàn tất sớm hoặc chờ mãi.

## 3. Pending count là gì, và không phải là gì?

Trong `CountedCompleter`, count ban đầu mặc định là **0**, trừ khi truyền initial pending count vào constructor.

Các API cốt lõi:

```java
getPendingCount()
setPendingCount(int count)
addToPendingCount(int delta)
compareAndSetPendingCount(int expected, int count)
decrementPendingCountUnlessZero()
tryComplete()
propagateCompletion()
```

Đây là **danh sách chữ ký rút gọn**, không phải code độc lập. `setPendingCount` gán giá trị; `addToPendingCount` tăng/giảm nguyên tử theo delta; `tryComplete` vừa tham gia giảm count hoặc kích hoạt completion, tùy giá trị count tại thời điểm được gọi.

Pending count **không tự biết các task nào tồn tại**. Nó chỉ là một số nguyên nguyên tử, **không phải một danh sách child hoặc ownership registry**. `CountedCompleter` không tự theo dõi rằng bạn vừa fork bao nhiêu child, child nào đã xử lý xong và mỗi child có gọi complete đúng một lần hay không.

Điều đó có nghĩa:

- Bạn phải xác định rõ **số tín hiệu completion** cần thiết.
- Bạn phải đảm bảo **mọi child cần chờ đều được đăng ký trước khi nó có thể signal**.
- Không được cho cùng một child báo `tryComplete` hai lần vô tình.
- Phải có đường completion cho node hiện tại và đường completion của các child theo quy ước counting.
- Khi task bị lỗi/cancel, phải có exception/cancellation policy thay vì mặc định mọi nhánh đều báo normal completion.
- Giá trị `pending == 0` **không tự có nghĩa task đã được đánh dấu done**. Trong thuật toán `tryComplete`, còn cần một invocation quan sát count bằng 0 để kích hoạt `onCompletion`/lan lên completer/root.

## 4. Semantics chính xác của tryComplete()

Theo đặc tả Java SE 17, khi gọi `tryComplete()` trên một task T:

1. Nếu pending count của T đang **khác 0**, nó được giảm một cách nguyên tử rồi lời gọi **kết thúc**, không tự gọi `onCompletion` chỉ vì lần giảm ấy làm count bằng 0.
2. Nếu pending count của T đang **bằng 0** ở thời điểm kiểm tra, `onCompletion(caller)` được kích hoạt cho T.
3. Sau đó cơ chế có thể đi tiếp lên completer của T và áp dụng cùng quy tắc.
4. Nếu đi tới root (không còn completer), root được đánh dấu hoàn thành bình thường theo completion traversal.

Một cách hình dung:

```text
tryComplete() trên task X
       |
       v
pending(X) > 0 ?
   | yes: giảm 1 rồi return
   |
   no: gọi X.onCompletion(caller)
       |
       v
       X có completer P ?
           | yes: tiếp tục completion traversal tại P
           | no: root hoàn thành
```

**Cực kỳ quan trọng:** “giảm từ 1 xuống 0” thường **chưa kích hoạt completion callback trong chính lời gọi đó**. Cần một tín hiệu tiếp theo thấy count đã là 0. Vì vậy một số mẫu sử dụng `setPendingCount(n)` cho n children rồi **parent tự gọi `tryComplete()`**: có tổng cộng **n + 1 tín hiệu** (n children, một của parent), khiến tín hiệu cuối thấy pending bằng 0 và kích hoạt completion.

### Bảng trạng thái với hai child

Giả sử parent có `setPendingCount(2)`, hai child A/B được fork và parent tự gọi `tryComplete`:

| Sự kiện | Pending trước | Hành vi | Pending sau |
|---|---:|---|---:|
| Parent `setPendingCount(2)` | 0 | Đăng ký hai signals từ children | 2 |
| Parent `tryComplete()` (trước khi 2 child báo) | 2 | Giảm 1 và return | 1 |
| A hoàn thành, lan signal tới parent | 1 | Giảm 1 và return | 0 |
| B hoàn thành, lan signal tới parent | 0 | `onCompletion` của parent, tiếp tục lên root | 0 |

**Lịch có thể khác**: A hoặc B có thể về trước parent tự gọi `tryComplete`. Bảng chỉ minh họa một thứ tự, không phải yêu cầu execution order. Với số lượng tín hiệu và đăng ký chính xác, tín hiệu cuối cùng sẽ kích hoạt completion dù các tín hiệu đến theo interleaving khác nhau.

### Không lạm dụng số 0 như “counter của việc đang chạy”

`pendingCount` không thay thế `Thread.State`, không là số thread thực thi hay kích thước `ForkJoinPool` queue. Nó là **state của giao thức completion** do thuật toán định nghĩa. Cần phân biệt “task đã hoàn thành” với “pending count đọc được bằng 0” và với “thread worker đang idle”.

## 5. Tại sao setPendingCount phải đứng trước fork?

Consider hai threads:

```text
Thread cha (P)                         Worker chạy child (C)
----------------------------------    --------------------------------------
new Child(P).fork()  ----------------> compute()
                                       xử lý nhanh
                                       tryComplete()
                                           child pending == 0
                                           -> P pending == 0
                                           -> P.onCompletion(...)
                                           -> có thể hoàn thành root
P.setPendingCount(1)  (QUÁ MUỘN)
P còn định fork/ xử lý nhánh khác
```

Đây là một **interleaving hợp lệ về mặt concurrency**. Thread cha có thể bị deschedule ngay sau `fork()`. Worker có thể chạy và hoàn tất child trong khoảng ấy. Kết quả:

- `P.onCompletion` có thể chạy khi P chưa đăng ký dependency.
- Nếu P là root, `invoke()`/`join()` ở caller có thể được mở khóa quá sớm.
- Caller đọc kết quả tổng hợp chưa chứa toàn bộ dữ liệu, hoặc cleanup resource khi các child khác còn làm việc.
- Nếu P ghi lại pending count sau khi đã completed, trạng thái count trở nên **không phản ánh lifecycle**; tăng count muộn không “undo” root đã hoàn thành.
- Callback có thể bị kích hoạt sai nhịp; nếu có tác động ngoài, việc chạy trước thời điểm mong muốn có thể làm sai invariant.

Dùng thứ tự đúng:

```java
setPendingCount(1);
new Child(this).fork();
tryComplete();
```

Đây là **đoạn code minh họa trong `compute()`**, với `Child` được xây sao cho `getCompleter() == this` và child gọi `tryComplete` khi hoàn tất. Count đã được tăng/thiết lập **trước khi** công bố child cho scheduler.

**Không nên “sửa” bằng `Thread.sleep()` giữa fork và setPendingCount.** Sleep không tạo ra ordering rule đảm bảo worker luôn chậm hơn. Thậm chí ngủ còn làm child có nhiều cơ hội chạy trước hơn.

## 6. Bảo toàn thứ tự với nhiều children

Với n child độc lập cần chờ, một phiên bản dễ hiểu nhất là:

```java
@Override
public void compute() {
    int n = children.size();
    setPendingCount(n);          // Đăng ký toàn bộ trước

    for (Child child : children) {
        child.fork();
    }

    tryComplete();               // Tín hiệu của chính parent
}
```

Đây là **pseudocode có cú pháp Java**, không phải class hoàn chỉnh; `children` chứa các child CountedCompleter dùng `this` làm completer, và `Child` có logic compute kết thúc bằng `tryComplete`.

Điều kiện đúng:

- n phải bằng **số nhánh con dự kiến báo completion**, không chỉ số object được tạo.
- Mọi child đang được đếm phải có completer phù hợp với parent.
- Không child nào hoàn thành hai lần theo cùng protocol.
- `setPendingCount(n)` phải chạy **trước khi có bất cứ child nào được fork/execute trực tiếp ở thread khác**.
- Parent `tryComplete` được gọi sau khi hoàn thành phần việc riêng của parent (trong mẫu này).
- Trong nhánh không tạo child (n=0), `tryComplete` trên pending 0 cho phép hoàn tất trực tiếp.

### Khi một child tự chia thêm các child

`Child.compute()` có thể lại `setPendingCount(k)` rồi fork k grandchildren. Khi grandchildren hoàn tất đúng protocol, child mới báo completion lên parent. Bởi vậy parent **đếm những child trực tiếp**, không tự cộng toàn bộ grandchildren vào count của parent nếu grandchildren đã được quản lý bởi child.

Hình cây:

```text
                    Root (pending=2)
                    /              \
              Left (pending=2)    Right (pending=2)
                /       \           /        \
              L1         L2       R1          R2

Mỗi nút nội bộ:
  - Đăng ký 2 trước khi fork 2 child.
  - Tự gọi tryComplete().
  - Nhận tín hiệu hoàn thành từ 2 children.

Chỉ khi Left và Right hoàn tất mới lan tới Root.
```

Điều này cho phép triển khai decomposition đệ quy, trong đó task con được fork có thể có vòng đời lâu hơn đoạn code cha vừa thực hiện.

## 7. Java 17 runnable: đảm bảo root chỉ hoàn tất khi mọi leaf đã xử lý

Chương trình sau tạo cây chia đôi một mảng gồm 8 phần tử. Mỗi internal node:

1. Tính `mid`.
2. Gọi **`setPendingCount(2)` trước khi fork bất kỳ child nào**.
3. Fork hai child có `this` làm completer.
4. Gọi `tryComplete()` cho phần việc riêng của node.

Mỗi leaf cộng một phần tử vào `AtomicLong sum`, tăng `AtomicInteger leaves`, rồi gọi `tryComplete()`. Root override `onCompletion` để đếm số lần root completion. Caller dùng `ForkJoinPool.invoke(root)` để chờ root hoàn tất rồi kiểm tra kết quả.

Tạo file **`PendingCountDemo.java`**:

```java
import java.util.concurrent.CountedCompleter;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

public class PendingCountDemo {
    static final class SumTask extends CountedCompleter<Void> {
        final int[] values;
        final int lo, hi;
        final AtomicLong sum;
        final AtomicInteger leaves;
        final AtomicInteger rootCompletions;

        SumTask(SumTask parent, int[] values, int lo, int hi,
                AtomicLong sum, AtomicInteger leaves,
                AtomicInteger rootCompletions) {
            super(parent);
            this.values = values;
            this.lo = lo;
            this.hi = hi;
            this.sum = sum;
            this.leaves = leaves;
            this.rootCompletions = rootCompletions;
        }

        @Override
        public void compute() {
            if (hi - lo >= 2) {
                int mid = (lo + hi) >>> 1;
                setPendingCount(2); // MUST happen before either fork
                new SumTask(this, values, lo, mid, sum, leaves,
                        rootCompletions).fork();
                new SumTask(this, values, mid, hi, sum, leaves,
                        rootCompletions).fork();
            } else if (hi > lo) {
                sum.addAndGet(values[lo]);
                leaves.incrementAndGet();
            }
            tryComplete(); // current task's completion signal
        }

        @Override
        public void onCompletion(CountedCompleter<?> caller) {
            if (getCompleter() == null) {
                rootCompletions.incrementAndGet();
            }
        }
    }

    static void runCase(ForkJoinPool pool, int[] input, String label) {
        AtomicLong sum = new AtomicLong();
        AtomicInteger leaves = new AtomicInteger();
        AtomicInteger completedRoot = new AtomicInteger();
        SumTask root = new SumTask(null, input, 0, input.length,
                sum, leaves, completedRoot);
        pool.invoke(root);
        System.out.println(label + "Sum=" + sum.get());
        System.out.println(label + "Leaves=" + leaves.get());
        System.out.println(label + "RootCompletions=" + completedRoot.get());
        System.out.println(label + "RootDone=" + root.isDone());
        System.out.println(label + "Pending=" + root.getPendingCount());
    }

    public static void main(String[] args) {
        ForkJoinPool pool = new ForkJoinPool(4);
        try {
            runCase(pool, new int[] {1, 2, 3, 4, 5, 6, 7, 8}, "data");
            runCase(pool, new int[0], "empty");
        } finally {
            pool.shutdown();
        }
    }
}
```

Biên dịch và chạy bằng JDK 17:

```bash
javac --release 17 PendingCountDemo.java
java PendingCountDemo
```

**Stdout đã biên dịch và chạy xác minh:**

```text
dataSum=36
dataLeaves=8
dataRootCompletions=1
dataRootDone=true
dataPending=0
emptySum=0
emptyLeaves=0
emptyRootCompletions=1
emptyRootDone=true
emptyPending=0
```

### Đọc kết quả đúng

- `dataSum=36` vì 1+2+3+4+5+6+7+8 = 36.
- `dataLeaves=8` vì cây xử lý đúng một lần cho mỗi ô của mảng.
- `dataRootCompletions=1` nghĩa callback `onCompletion` trên root được kích hoạt một lần trong lần chạy đã xác minh, sau khi các nhánh đã báo completion.
- `dataRootDone=true` cho thấy root đã được đánh dấu hoàn tất, nhờ đó `pool.invoke(root)` trở về.
- `dataPending=0` là pending count cuối cùng trong protocol này. **Đừng dùng một mình con số 0 làm chứng minh task đã done**; chính `isDone`/`invoke` cung cấp tín hiệu lifecycle.
- `emptySum=0`, `emptyLeaves=0` và `emptyRootCompletions=1` kiểm tra cả nhánh n=0: không tạo child, `tryComplete` đủ để root hoàn tất.

### Vì sao demo có AtomicLong/AtomicInteger?

Nhiều leaves có thể chạy đồng thời trên nhiều workers. Mỗi leaf cộng vào **một shared counter**, nên `sum += values[lo]` trên `long` thường sẽ có nguy cơ lost update. Dùng `AtomicLong.addAndGet` và `AtomicInteger.incrementAndGet` đảm bảo các updates riêng lẻ không bị mất.

**CountedCompleter pending count không tự biến mọi field do leaves cùng cập nhật thành thread-safe.** Nó điều phối completion; shared result vẫn cần ownership, atomic operations, hoặc thiết kế map/reduce qua `onCompletion` và kết quả từ các child phù hợp.

### Vì sao dùng invoke(root)?

`ForkJoinPool.invoke(root)` đợi root task kết thúc rồi mới trả cho caller. Nếu protocol completion bị sai và root hoàn tất **sớm**, phương thức này cũng có thể trở về sớm; `invoke` không thể biết child nào đã bị thiếu trong pending count. Vì vậy nguồn sự thật là **mối quan hệ dependency mà thuật toán đăng ký chính xác**.

### Vì sao không dùng Thread.sleep để chứng minh?

Thread scheduling có thể đổi giữa các lần chạy. Demo dựa vào invariants của API và completion traversal. Không cần đặt sleep trong leaf để “ép” root đợi đủ lâu. Kiểm thử đúng nên chứng minh tính đúng qua số signals và dùng `invoke` làm ranh giới hoàn tất, không dựa vào thời gian.

## 8. Chứng minh count cho cây chia đôi

Với một internal node có đúng hai child:

- `setPendingCount(2)` thiết lập pending = 2.
- Node hiện tại gọi `tryComplete()` một lần khi hoàn thành phần việc riêng.
- Child A báo hoàn thành một lần qua `tryComplete()` và lan tới node.
- Child B báo tương tự.

Tổng có **3 tín hiệu completion** đến node, trong đó **hai tín hiệu đầu** làm pending 2→1→0, **tín hiệu thứ ba** thấy pending 0 và kích hoạt `onCompletion` rồi đi lên completer.

**Thứ tự tín hiệu có thể là bất kỳ**:

```text
Lịch 1: self, A, B  -> 2->1, 1->0, onCompletion
Lịch 2: A, self, B  -> 2->1, 1->0, onCompletion
Lịch 3: B, A, self  -> 2->1, 1->0, onCompletion
```

Các lịch này đều đúng nếu tất cả các tín hiệu đến chính xác một lần và parent count được set trước khi children có thể chạy. `tryComplete`/pending operations sử dụng thao tác nguyên tử theo contract, nên nhiều workers có thể gửi tín hiệu completion mà không làm mất một lần giảm count như với `int--` không đồng bộ.

### Induction cho toàn bộ cây

**Base case:** leaf không fork children, pending mặc định 0; sau khi xử lý phần tử, leaf gọi `tryComplete`. Nó kích hoạt onCompletion của leaf và lan một signal tới parent.

**Inductive step:** mỗi child subtree đã hoàn tất trước khi child gửi tín hiệu lên parent; parent đã đăng ký hai child trước fork; parent chỉ kích hoạt completion khi có đủ hai child và tín hiệu của chính parent. Vì vậy một parent hoàn tất sau toàn bộ leaves thuộc subtree của nó.

**Kết luận:** root chỉ hoàn tất sau mọi leaf được đăng ký trong cây đã xử lý xong. Đây là lý do pending count phải được set trước publication: nếu không, bước inductive về “parent đã biết các dependencies” bị phá.

**Điều kiện giả định:** mọi task luôn đi tới normal completion, không có uncaught exception/cancel làm thiếu tín hiệu, không có child báo completion hai lần, không có logic cố ý gọi `quietlyCompleteRoot` hoặc `complete` để ép root hoàn tất sớm và không có lỗi của code ngoài CountedCompleter.

## 9. Biến thể tối ưu: fork một child, compute child còn lại trực tiếp

API CountedCompleter JavaDoc cũng mô tả một biến thể:

```java
// Đặt trong compute() của class Task extends CountedCompleter<Void>:
if (hi - lo >= 2) {
    int mid = (lo + hi) >>> 1;
    setPendingCount(1);                 // Chỉ một child được fork
    new Task(this, mid, hi).fork();     // Right child bất đồng bộ
    new Task(this, lo, mid).compute();  // Left child chạy trực tiếp
} else {
    if (hi > lo) {
        process(array[lo]);
    }
    tryComplete();
}
```

Đây là **code minh họa trong class**, với `Task`, `lo`, `hi`, `array` và `process` do ứng dụng cung cấp. Không phải tệp độc lập.

Tại sao `setPendingCount(1)` khi có **hai nhánh logic**?

- Chỉ **right child** được `fork()`, trở thành task bất đồng bộ cần đếm riêng.
- Left child chạy **trực tiếp** bằng `compute()` trong thread đang làm việc.
- **Không có `tryComplete()` riêng ở parent sau nhánh recursion**. Tín hiệu của left completion đi qua completer chain và đóng vai trò “phần việc parent vẫn đang làm”.
- Một signal từ right và một từ left là **hai tín hiệu**: count 1→0, rồi tín hiệu tiếp theo kích hoạt onCompletion. Điều này giải thích tại sao nó trông “off by one” nhưng hợp lệ.

**Đừng sao chép `setPendingCount(1)` mà giữ nguyên code fork cả hai child và tự gọi tryComplete, hoặc ngược lại**. Pending count phải khớp **cấu trúc tín hiệu thực tế**, không khớp máy móc số dòng `new Task`.

### So sánh hai mẫu

| Mẫu | Số child fork | Pending đăng ký | Self tryComplete | Điều kiện completion |
|---|---:|---:|---|---|
| Dễ hiểu: fork cả hai | 2 | 2 | Có, sau fork | 2 child + self signal |
| Tối ưu: fork phải, tính trái trực tiếp | 1 | 1 | Không ở nhánh nội bộ; leaf gọi | Right + Left signals |
| Leaf không fork | 0 | 0 | Có, sau xử lý | Leaf signal duy nhất |

**Tối ưu không nên đánh đổi tính rõ ràng khi mới học.** Bắt đầu với mẫu set count bằng số child fork, self tryComplete, và chứng minh lịch completion đúng. Chỉ chuyển sang biến thể tinh gọn khi hiểu chính xác count protocol và đã có tests.

## 10. addToPendingCount(1) trước từng fork: khi nào dùng?

Khi số lượng children được tạo dần, không biết trước n, có thể dùng `addToPendingCount(1)` **trước từng lần fork**:

```java
// Minh họa trong compute() của CountedCompleter:
for (WorkItem item : discoveredItems) {
    addToPendingCount(1);             // Đăng ký một child trước fork
    new Child(this, item).fork();
}
tryComplete();                        // Chỉ sau khi đăng ký tất cả
```

Đây là code minh họa, các types/variables cần định nghĩa. Điều quan trọng:

- `addToPendingCount(1)` thực hiện atomically.
- **Mỗi child được đăng ký trước khi công bố nó**.
- Trong mẫu này parent **chưa gọi self tryComplete trước khi vòng phát sinh child kết thúc**, nên không vô tình đánh dấu complete khi còn định đăng ký thêm việc.
- Nếu child hoàn tất nhanh, count có thể giảm lại về 0 trước lần register tiếp theo. Điều đó **không tự kích hoạt onCompletion** vì chỉ lời gọi `tryComplete` quan sát count 0 mới làm completion traversal; self signal của parent vẫn được giữ đến cuối phase đăng ký.
- Tuy nhiên, nếu có một luồng khác có thể đưa thêm child sau khi parent tự signal completion hoặc sau khi root đã done, count protocol cần thiết kế mới, không chỉ gọi add tùy ý.

**Bẫy:** `setPendingCount(n)` sau khi một số child đã hoàn thành không tương đương việc add n mới. `setPendingCount` **ghi đè giá trị hiện tại**; nó có thể xóa những decrement đã diễn ra. Chỉ set một lần trước publication, hoặc dùng increment có kiểm soát trước từng fork theo protocol rõ.

### Vì sao không dùng một AtomicInteger đếm work bên ngoài?

Có thể tạo một completion protocol khác với `AtomicInteger` và latch, nhưng khi đã dùng `CountedCompleter`, pending count chính là phần của **control flow completion** mà ForkJoin hỗ trợ. Một counter ngoài không tự thông báo cho completer và không làm `ForkJoinPool.invoke(root)` biết khi nào root completed.

## 11. Sai lầm: count bằng n nhưng không có self tryComplete

Giả sử:

```java
setPendingCount(2);
new Child(this).fork();
new Child(this).fork();
// BUG: compute() return mà không tryComplete().
```

Đây là snippet minh họa lỗi trong `compute()`.

Với hai children, tín hiệu đầu giảm 2→1, tín hiệu thứ hai giảm 1→0. **Không có tín hiệu thứ ba quan sát pending 0**, nên root có thể **không được đánh dấu complete**. Caller `join()`/`invoke()` có nguy cơ chờ vô hạn.

Có hai cách sửa, tùy giao thức:

1. **Giữ setPendingCount(2)** và gọi `tryComplete()` một lần của parent sau khi fork, như ví dụ runnable.
2. Chọn một counting variant khác đã được chứng minh, ví dụ `setPendingCount(1)` cùng parent không self-signal trong một cấu trúc tail-call hợp lệ. Không đơn giản “giảm count tùy ý” mà không xét số tín hiệu.

Một pending count 0 là **state trung gian**, còn completion event cần được kích hoạt đúng.

## 12. Sai lầm: count ít hơn số child và completion sớm

Ví dụ cố tình sai:

```java
setPendingCount(1); // Sai với mẫu fork 2 children + self signal.
new Child(this, slowTask).fork();
new Child(this, fastTask).fork();
tryComplete();
```

Đây là snippet minh họa, không phải class độc lập.

Nếu self signal đến đầu tiên, count 1→0. Sau đó **fast child** báo completion và quan sát pending 0, khiến parent onCompletion/propagate, trong khi **slow child vẫn có thể đang chạy**. Root hoàn tất sớm là hậu quả logic.

Nếu dùng `ForkJoinPool.invoke(root)`, caller có thể đọc kết quả tổng hợp **trước khi slow child ghi phần của nó**. Không phải vì `invoke` hỏng: root đã được algorithm **báo hoàn tất sai**.

Đây là dạng sai giống mục tiêu bài học: phải đảm bảo số lượng việc được đăng ký **đúng và đủ** trước fork.

## 13. Sai lầm: count lớn hơn số child và chờ mãi

Ví dụ:

```java
setPendingCount(3); // Sai: thực tế chỉ có 2 children + self signal.
new Child(this, left).fork();
new Child(this, right).fork();
tryComplete();
```

Đây là mã minh họa. Tổng ba tín hiệu đến parent: count 3→2→1→0. **Không tín hiệu nào quan sát count 0 ở đầu**, nên root có thể không hoàn tất mặc dù toàn bộ child đã xong.

Các kết quả dễ quan sát là `join` treo, task “active” mãi, `onCompletion` không được gọi, pool không báo lỗi rõ. Đừng vá bằng một lời gọi `tryComplete` thừa không có ngữ nghĩa; sửa việc tính số child và signal sources.

## 14. Sai lầm: set count sau khi fork và race với child hoàn thành

Ví dụ nguy hiểm nhất:

```java
new Child(this, left).fork();
new Child(this, right).fork();
setPendingCount(2); // SAI: một child có thể đã báo complete.
tryComplete();
```

Đây là snippet minh họa lỗi.

Có thể xảy ra nhiều kết quả không mong muốn tùy interleaving:

- Child nhanh thấy parent pending 0, kích hoạt parent/root completion trước khi count được set.
- Sau khi parent viết pending 2, các child đã hoàn thành không thể “báo lại”, nên pending còn dương và một caller khác có thể không thấy đường completion mới.
- Nếu parent đã onCompletion và kết quả được tổng hợp sớm, các child chậm vẫn có thể đang mutate shared state sau khi caller nghĩ công việc xong.
- Nếu callback có side effect (ghi final result, đóng stream), side effect có thể xảy ra trước thời điểm hợp lệ.

**Bằng chứng correctness không thể là “tôi chạy 1.000 lần đều thấy đúng”.** Race có thể rất hiếm khi child chưa được cấp CPU kịp. Hãy chứng minh bằng ordering: parent count được đăng ký **trước publication**, bất kể scheduler interleaving.

## 15. Các API completion khác: không được thay thế máy móc

### `propagateCompletion()`

`propagateCompletion()` đi theo traversal tương tự `tryComplete()`, nhưng **không gọi `onCompletion`** khi đi qua những completers. Nó phù hợp nếu không cần tổng hợp kết quả trong callback.

```java
// Minh họa khi các node không cần onCompletion:
addToPendingCount(1);
new Child(this).fork();
// ... xử lý local work
propagateCompletion();
```

Đây là đoạn minh họa trong class CountedCompleter. **Tính đúng của số tín hiệu vẫn phải chứng minh**. Đổi `tryComplete` thành `propagateCompletion` có thể làm mất bước combine quan trọng nếu `onCompletion` đang thực hiện reduction.

### `complete(T rawResult)`

`complete` có thể ép một task hoàn thành **không phụ thuộc pending count**, gọi `onCompletion`, đánh dấu task done và tham gia thông báo lên completer. Nó phù hợp cho một số thuật toán “bất kỳ kết quả đầu tiên là đủ”, nhưng **không phù hợp thay cho `tryComplete`** khi mục tiêu là chờ đủ tất cả children.

### `quietlyCompleteRoot()`

`quietlyCompleteRoot` đánh dấu root hoàn tất mà không theo đường normal completion count của tất cả child. Có thể có giá trị với early-result search, nhưng nếu bài toán bắt buộc mọi child xong thì gọi nó sớm sẽ phá contract.

### `firstComplete()` và `nextComplete()`

Đây là các primitive traversal cho những thuật toán cần kết hợp kết quả/chuỗi completion tùy biến. Nếu chưa có lý do cụ thể, dùng `tryComplete`/`onCompletion` đơn giản sẽ dễ chứng minh hơn.

## 16. onCompletion(caller): thời điểm tổng hợp kết quả

`onCompletion(CountedCompleter<?> caller)` có thể được override để kết hợp kết quả child khi một node đã đủ tín hiệu completion. `caller` biểu diễn task nào kích hoạt completion traversal; có thể là chính node đó hoặc child/subtask của nó.

Ý tưởng với map-reduce:

```java
@Override
public void onCompletion(CountedCompleter<?> caller) {
    // Khi count protocol đúng, mọi child cần chờ đã hoàn tất.
    // Kết hợp dữ liệu do child ghi vào các field/result holder:
    result = left.result + right.result;
}
```

Đây là **snippet minh họa**, cần có các field `result`, `left`, `right` tương ứng. Không độc lập và không an toàn nếu các child chưa được đăng ký đúng, nếu child data bị mutate ngoài protocol, hoặc nếu kết quả chưa được publish hợp lệ.

**Điều kiện chính:** parent không thể giả định child done chỉ dựa vào `getPendingCount()==0`. Callback đúng thời điểm phụ thuộc số completions đã được đăng ký và đã đến. Thêm một callback chỉ vì “count hiện đang 0” có thể tổng hợp sớm nếu count bị thiếu.

Theo JavaDoc, khi giao thức pending count đúng, những hành động kết hợp kết quả trong `onCompletion` có thể dựa vào cơ chế completion để truy cập dữ liệu của các subtasks đã hoàn tất. Tuy nhiên, nếu dữ liệu shared còn bị worker **không thuộc completion tree** sửa, cần synchronization/ownership riêng.

## 17. Memory visibility: completion đúng không tự làm mọi dữ liệu thread-safe

`CountedCompleter` giúp tạo quan hệ completion và phối hợp task, nhưng không nên nhầm với một synchronized block bao quanh mọi field.

### Trong demo

- Các leaves cập nhật `sum` qua `AtomicLong.addAndGet`, nên không mất increments do interleaving.
- `leaves` dùng `AtomicInteger.incrementAndGet`.
- Parent/child liên kết qua constructor `super(parent)` và các field `final`.
- Sau `ForkJoinPool.invoke(root)`, caller quan sát root đã complete; các updates bình thường trong subtree đã đăng ký đúng đều xảy ra trước completion mà caller chờ.
- Nếu có một task không thuộc tree tiếp tục sửa `sum`, root completion không tự chờ task ngoài đó.

### Khi chia kết quả theo child

Một cách khác là mỗi child có result riêng, ghi result trước khi gọi `tryComplete()`, rồi parent kết hợp trong `onCompletion`. Phương án này thường tránh nhiều workers tranh cùng một atomic counter, nhưng cần thiết kế structure result/parent links hợp lý. Không chỉ sửa `sum` thành `long` thường dùng chung rồi hy vọng pending count bảo vệ phép cộng.

### Happens-before trong ForkJoinTask

Java concurrent task/future/join semantics cung cấp các bảo đảm memory ordering cần thiết cho việc công bố kết quả khi completion được quản lý đúng. Một caller gọi `invoke()/join()` để chờ **task đã hoàn tất hợp lệ** có thể sử dụng kết quả đã được chuẩn bị trước completion theo protocol tương ứng.

**Nếu root bị đánh dấu done sớm**, caller không còn một completion barrier đúng với những children bị bỏ sót. Không thể dùng câu “invoke() bảo đảm visibility” để cứu một dependency graph chưa được đăng ký.

## 18. Pending count và số lượng thread khác nhau thế nào?

Một root có thể có pending count 100 nhưng pool chỉ có 4 workers. Count phản ánh **100 completion dependencies** theo protocol, không phản ánh 100 threads. ForkJoinPool dùng work-stealing để xử lý nhiều tasks trên một số workers hữu hạn.

Ngược lại, pool có 32 workers nhưng root chỉ có pending count 2 vì nó chỉ chờ hai child trực tiếp. Hai children có thể mỗi đứa lại chờ cả nghìn subtasks. Root đếm **trực tiếp two completions**, không phải tất cả grandchildren.

Đừng viết logic dạng:

```java
setPendingCount(pool.getParallelism()); // SAI nếu số child khác số workers.
```

Đây là snippet minh họa lỗi, với `pool` là ForkJoinPool. `parallelism` là thông số của pool, không phải số dependencies của task.

Tương tự, `ForkJoinPool.getQueuedTaskCount()` là estimate của queue, không dùng làm pending count. Không được dựa vào snapshot queue size để suy chính xác bao nhiêu children còn phải hoàn tất.

## 19. Error handling và exceptional completion

Normal completion của CountedCompleter và exceptional completion là hai chuyện cần thiết kế riêng.

- Nếu `compute()` của child ném exception, `ForkJoinTask`/CountedCompleter có semantics exceptional completion riêng.
- `onExceptionalCompletion(Throwable ex, CountedCompleter<?> caller)` cho phép customize việc lan truyền exception lên completer theo contract.
- Nếu child fail trước khi gửi normal `tryComplete`, parent không nên chỉ **chờ normal signals mãi** mà không có failure propagation hoặc cancellation policy.
- Nếu cần thu thập **tất cả lỗi** từ nhiều children, phải định nghĩa shared error holder/aggregation và cách các children tiếp tục hoặc dừng; không suy rằng default CountedCompleter lưu mọi exception tự động.
- `quietlyCompleteRoot()` có thể dừng sớm một số thuật toán search, nhưng không được lạm dụng để bỏ qua phần việc còn dang dở nếu yêu cầu tất cả children hoàn tất.

Một pattern minh họa:

```java
@Override
public boolean onExceptionalCompletion(
        Throwable ex, CountedCompleter<?> caller) {
    recordFailure(ex); // method do ứng dụng định nghĩa
    return true;       // Cho phép propagate theo contract
}
```

Đây là method minh họa trong subclass CountedCompleter. `recordFailure` phải thread-safe, bounded và tránh ném exception mới làm che cause ban đầu. Phải đọc JavaDoc để hiểu return boolean của callback và tránh đếm một failure ở nhiều cấp như nhiều failure độc lập.

**Quan trọng:** ví dụ runnable ở trên là phép cộng đơn giản không ném exception; ta cố ý giữ failure logic riêng để không biến một sample ngắn thành một framework lỗi/phục hồi khó kiểm chứng.

## 20. Cancellation và early completion

Nếu caller `cancel()` root trong khi children vẫn chạy, cancellation không tự đảm bảo các child đã ngừng ngay. Nếu algorithm dùng `quietlyCompleteRoot()` khi tìm thấy kết quả đầu tiên, root có thể done dù những branches khác còn tác vụ đang tiến triển.

Vì vậy phải phân biệt ba loại contract:

1. **All-work completion:** root chỉ done khi tất cả children cần chờ đã hoàn tất. Dùng pending count chính xác và normal completion traversal.
2. **First-result completion:** root có thể done sớm khi có kết quả đủ tốt, nhưng phải quản lý task khác/cancellation và side effects cẩn thận.
3. **Failure-fast completion:** root kết thúc bất thường khi một child lỗi, trong khi các children khác có thể cần cancel/cleanup.

Chủ đề **“thiết lập pending count trước fork”** đặc biệt liên quan loại 1. Không được âm thầm biến nó thành first-result completion chỉ để làm `invoke` trả về sớm.

## 21. Nếu công việc tạo thêm child động thì sao?

Với cây động, ta thường không biết trước toàn bộ descendants. Có hai cách chính:

- **Đăng ký batch children hiện tại:** tính n và `setPendingCount(n)` trước khi fork batch.
- **Đăng ký incremental:** `addToPendingCount(1)` trước mỗi child `fork`, giữ self completion signal đến khi phase đăng ký kết thúc.

Nếu **child có thể sinh thêm child** sau khi parent đã báo completion của chính nó, phải tạo một subtree CountedCompleter riêng và parent chờ **completion của child đó**; child quản lý grandchildren bằng pending count nội bộ.

**Không để thread khác bất kỳ thêm dependency vào parent sau khi parent đã có thể complete.** Đó không còn là cấu trúc fork-join truyền thống đơn giản, và có thể cần một coordination protocol khác, chẳng hạn `Phaser` hoặc ownership-based task registry, nếu số participants động.

### Example reasoning: task stream fan-out

Giả sử một node đọc 5 work items rồi fork 5 children. Cần:

```text
discover items
setPendingCount(5)
fork item 1
fork item 2
fork item 3
fork item 4
fork item 5
tryComplete()
```

Nếu không biết số items trước khi đọc hết, đừng set count 0 rồi fork lung tung. Hoặc đọc xong list trước (nếu bộ nhớ cho phép), hoặc dùng mỗi `addToPendingCount(1)` **trước từng fork** và giữ phase registration không hoàn tất quá sớm.

## 22. Test race: không kiểm chứng bằng một lịch chạy may mắn

Một chương trình CountedCompleter có count sai có thể chạy đúng hàng nghìn lần nếu parent may mắn kịp gọi `setPendingCount` trước khi workers xử lý child. Vì thế test cần có hai lớp:

### A. Kiểm tra logic đếm bằng invariant

Với mỗi internal node:

1. Có bao nhiêu completions cần đợi?
2. Chúng đến từ những child nào?
3. Parent có gửi self completion signal không?
4. Các tín hiệu được gửi đúng một lần chứ?
5. Count được đăng ký **trước khi bất cứ child nào có thể gửi signal** chứ?
6. Khi chưa hoàn tất đủ dependencies, có đường nào dùng `complete`/`quietlyCompleteRoot` để đánh dấu done sớm không?
7. Nếu child fail, path exceptional completion là gì?

Test không thể thay thế việc trả lời những câu hỏi này.

### B. Stress có kiểm soát

- Dùng input rỗng, một phần tử, hai phần tử, kích thước không phải lũy thừa 2, hàng nghìn phần tử.
- Chạy trên `ForkJoinPool(1)`, `ForkJoinPool(2)`, và số workers lớn hơn để thay đổi mức interleaving.
- Đảm bảo tổng số leaves xử lý đúng với số phần tử và kết quả tổng/hàm reduce đúng.
- Chèn `CountDownLatch` hoặc `Phaser` để mô phỏng child có thể hoàn tất sớm hơn parent làm bước tiếp theo, nhưng không biến test thành deadlock.
- Dùng `ForkJoinTask.get(timeout, unit)` để test bị treo có thể fail theo deadline; không dùng `Thread.sleep()` như một chứng minh đã xong.
- Khi test trường hợp count sai, chạy nó trong harness có timeout và cancellation; **không đưa cố tình sai vào production**.

### Vì sao test lỗi “late pending count” khó thấy?

Vì fork có thể chỉ enqueue child và current worker vẫn được chạy tiếp. Nếu parent lập tức `setPendingCount` ngay sau fork, trên một máy/tải cụ thể parent có thể thắng race. Nhưng một worker đang rảnh khác hoàn toàn có thể steal child và hoàn tất trước. Bảo đảm đúng phải độc lập với ai chạy trước.

## 23. Quan sát ForkJoinPool và task completion

Khi hệ thống không tiến triển, cần xem:

- `ForkJoinPool.getActiveThreadCount()` và `getRunningThreadCount()`: snapshots/estimates về hoạt động workers, không chứng minh root done.
- `getQueuedTaskCount()`: estimate những task đang nằm trong queues, không phải số dependencies chưa complete.
- `getStealCount()`: lượng work stealing xấp xỉ theo API, hữu ích khi nghiên cứu load balance.
- `ForkJoinTask.isDone()`, `isCompletedNormally()`, `isCompletedAbnormally()`: lifecycle của task.
- `CountedCompleter.getPendingCount()`: số completion signals còn theo protocol của task.
- Callback `onCompletion`: nơi kết hợp kết quả sau dependencies, nhưng chỉ có ý nghĩa nếu pending bookkeeping đúng.
- Exception outcome của `join`/`get`: phân biệt failure, cancel và timeout.

Một số lệnh chẩn đoán JVM:

```bash
jcmd <PID> Thread.print -l
```

Thay `<PID>` bằng PID process thật. Thread dump cho biết worker đang chạy, chờ, hay block ở nơi khác; nó không ghi được toàn bộ lịch completion count trong quá khứ. Nếu debug lỗi hiếm, cần thêm event tracing có chọn lọc thay vì log mọi task ở mức tần suất cao gây contention.

**Đừng trông chờ thread dump sẽ tự chỉ rõ “quên setPendingCount trước fork”.** Đây là lỗi protocol ở mã nguồn. Một số workers có thể đã idle trong khi root pending >0 và caller vẫn chờ.

## 24. Hiệu năng: fork đủ lớn và đừng giữ global atomics không cần thiết

Mẫu chia mỗi phần tử thành một leaf task trong demo là **để minh họa completion**, không tối ưu hiệu năng. Với dữ liệu lớn, tạo hàng triệu CountedCompleters có thể tốn allocations, queue operations và contention.

Tối ưu thường là:

- Chia tới một **grain size** đủ lớn, ví dụ mỗi leaf xử lý một đoạn 1.000 phần tử thay vì 1 phần tử, tùy workload.
- Dùng kỹ thuật **fork một nhánh, xử lý nhánh còn lại trực tiếp** để giảm task count.
- Để mỗi leaf giữ local result và combine trong `onCompletion` thay vì mọi leaf cùng cạnh tranh một `AtomicLong`.
- Tránh blocking I/O không cần thiết trên ForkJoinPool workers; work-stealing phù hợp hơn với các computations có thể chia nhỏ.
- Profile allocation, CPU, queue/steal counts và tail latency trước khi quyết định tuning.
- Không sacrifice correctness để giảm một lệnh `setPendingCount`; race hoàn tất sớm có thể rất khó phát hiện.

### Khi nào không cần CountedCompleter?

Nếu thuật toán đơn giản trả một kết quả bằng cách fork một child rồi join trong parent, `RecursiveTask<V>` có thể dễ hiểu hơn. Nếu chỉ cần chạy N tác vụ độc lập và đợi tất cả, `ExecutorService.invokeAll`, `CompletableFuture.allOf` hoặc `CountDownLatch` có thể phù hợp tùy kiểu dữ liệu và lifecycle.

Chọn primitive diễn đạt rõ nhất dependencies, đừng dùng `CountedCompleter` chỉ vì “không cần join” mà không có lý do.

## 25. Những lỗi phổ biến và cách sửa

1. **Fork trước rồi mới set pending count.** Child có thể complete trước khi được đăng ký; đặt count trước mọi fork.
2. **setPendingCount(2) cho hai children nhưng quên self tryComplete.** Hai tín hiệu chỉ giảm 2→1→0; chưa kích hoạt completion.
3. **setPendingCount(1) trong mẫu fork hai children + self signal.** Parent có thể complete khi còn child đang chạy.
4. **setPendingCount(3) cho hai children + self signal.** Parent có thể đứng ở pending 0 và chờ vô hạn vì thiếu tín hiệu kích hoạt final completion.
5. **Dùng getPendingCount()==0 để khẳng định done.** Cần `isDone`/completion callback và protocol đúng.
6. **Lấy pool parallelism làm pending count.** Pending đếm logical completions, không phải worker threads.
7. **Mọi child gọi tryComplete hai lần.** Có thể tạo premature completion hoặc kích hoạt callback sai.
8. **Child không có đúng completer.** Signal không tới parent dự kiến, root có thể treo.
9. **setPendingCount lại khi child đã bắt đầu hoàn thành.** Có thể ghi đè atomic decrements và làm mất progress.
10. **Quên child cuối cùng phải signal cả khi không có data.** Empty subtree cũng cần completion path nếu đã được đăng ký.
11. **Dùng complete()/quietlyCompleteRoot() để chữa deadlock count sai.** Có thể báo done khi công việc chưa xong.
12. **Cho rằng invoke sẽ tự đợi mọi task được fork trong JVM.** Invoke chỉ đợi root ForkJoinTask theo completion protocol của root.
13. **Cho rằng CountedCompleter làm long++ thread-safe.** Shared mutable results vẫn cần atomic/lock/partitioned ownership.
14. **Không phân biệt normal vs exceptional completion.** Child throw có thể đòi failure propagation/cancel policy.
15. **Dùng Thread.sleep để ép parent chạy trước child.** Không có bảo đảm, chỉ làm timing khác đi.
16. **Đọc onCompletion và tưởng callback do parent thread chạy.** Callback có thể được kích hoạt trên worker hoàn tất tín hiệu cuối, không nhất thiết là thread ban đầu chạy parent.
17. **Coi mọi child đều cần pendingCount=1.** Leaf có thể dùng pending=0 và tryComplete để lan signal; count là state của mỗi node.
18. **Thấy pending 0 rồi addToPendingCount mới sau completion.** Không thể hồi sinh một root đã được đánh dấu done bằng cách tăng count muộn.
19. **Tối ưu off-by-one mà không chỉnh code signaling.** Số count phải khớp variant; không copy riêng một dòng setPendingCount.
20. **Tạo millions tiny tasks và nghĩ work stealing luôn nhanh hơn loop tuần tự.** Grain size và overhead cần đo.
21. **Cho rằng child hoàn tất đồng nghĩa toàn bộ grandchildren xong mà không cần protocol.** Child phải quản lý subtree của nó và signal parent đúng thời điểm.
22. **Dùng CountedCompleter làm distributed job coordinator.** Nó quản lý task completion trong JVM; không có durability/replay khi process crash.

## 26. Checklist review thuật toán CountedCompleter

Trước khi merge code:

- **Cây phụ thuộc:** child nào có completer là node hiện tại? Có parent/child bị liên kết nhầm?
- **Tín hiệu:** mỗi node sẽ nhận bao nhiêu completion signals?
- **Count:** initial/set/add pending count có khớp số signals và tự signal không?
- **Thứ tự:** toàn bộ pending child cần chờ đã được đăng ký **trước bất cứ fork nào** chưa?
- **Tail-call variant:** có thay cấu trúc fork/direct-compute mà quên sửa count/self tryComplete?
- **Leaf:** mọi nhánh base case, kể cả mảng rỗng, có gọi tryComplete đúng một lần không?
- **Kết hợp:** onCompletion có chạy sau toàn bộ dữ liệu child cần thiết? Result holder có shared mutation ngoài tree không?
- **Exception:** khi child throw, root xử lý failure thế nào, có phải cancel nhánh khác không?
- **Cancellation:** khi caller hủy root, children có còn side effects đang chạy?
- **Memory:** dữ liệu được publish an toàn, tránh races độc lập với completion count?
- **Liveness:** có tín hiệu bị thiếu khiến pending count còn dương hoặc bằng 0 mà root chưa done?
- **Testing:** input rỗng/nhỏ/lẻ/lớn, các parallelism khác nhau, timeout, stress, và invariants được assert?
- **Giám sát:** metrics nhận biết queue/worker và trạng thái done/exception của root có rõ?
- **Phiên bản JDK:** sample chạy được trên JDK 17; nếu dùng API mới cần ghi chú version.

## 27. Câu hỏi tự kiểm tra và đáp án

**Câu 1.** Vì sao phải gọi `setPendingCount` trước `fork`?  
**Đáp án:** Sau `fork`, child có thể được worker khác xử lý và gọi `tryComplete` ngay. Nếu parent vẫn pending 0, completion có thể lan quá sớm trước khi dependency được đăng ký.

**Câu 2.** Nếu parent fork hai children rồi tự `tryComplete` theo mẫu đơn giản, pending nên khởi tạo bao nhiêu?  
**Đáp án:** 2. Có tổng 3 tín hiệu (parent và 2 children); hai tín hiệu đầu giảm 2→1→0, tín hiệu thứ ba kích hoạt completion.

**Câu 3.** Tại sao pending giảm từ 1 xuống 0 chưa chắc onCompletion chạy ngay?  
**Đáp án:** `tryComplete` khi thấy count khác 0 sẽ decrement rồi return; một invocation sau đó phải quan sát count 0 mới thực hiện callback.

**Câu 4.** Khi `getPendingCount()==0` có thể tuyên bố root đã `isDone()==true` không?  
**Đáp án:** Không. Count bằng 0 là một trạng thái của protocol, task completion phải được kích hoạt đúng.

**Câu 5.** `CountedCompleter` có tự theo dõi danh sách children đã fork không?  
**Đáp án:** Không. Pending là một số nguyên, không gắn ID task. Người viết thuật toán quản lý completer links và signals.

**Câu 6.** Nếu có 8 leaves nhưng ForkJoinPool chỉ có 2 workers, root phải set pending count bằng 8 hay 2?  
**Đáp án:** Không thể suy từ hai con số ấy. Root thường đếm các **child trực tiếp**, ví dụ 2; mỗi child quản lý subtree của nó. Pending không phải parallelism.

**Câu 7.** Với n=0 children và pending mặc định 0, làm sao root normal-complete?  
**Đáp án:** Sau khi xử lý phần việc node (có thể không có dữ liệu), gọi `tryComplete()` để kích hoạt callback/root completion.

**Câu 8.** Với hai child, vì sao biến thể right.fork()/left.compute() có thể dùng pending 1?  
**Đáp án:** Parent không self tryComplete ở nhánh nội bộ; nó đợi một nhánh fork và completion signal từ nhánh tính trực tiếp. Hai tín hiệu là đủ cho count 1→0 rồi callback.

**Câu 9.** Gọi `setPendingCount(2)` sau khi một child đã báo completion có sửa được race không?  
**Đáp án:** Không. Completion có thể đã lan lên root, hoặc count mới ghi đè decrement. Đăng ký phải xảy ra trước publication.

**Câu 10.** `pool.invoke(root)` có chắc chắn chờ mọi ForkJoinTask trong pool không?  
**Đáp án:** Không. Nó chờ root theo lifecycle của root. Nếu dependency graph thiếu, root có thể done sớm dù tasks khác còn chạy.

**Câu 11.** Shared `long sum` được các leaves dùng `sum += value` có an toàn chỉ vì pending count đúng không?  
**Đáp án:** Không. Pending điều phối completion, không atomic hóa các updates concurrent. Dùng AtomicLong hoặc local results và combine.

**Câu 12.** Khi onCompletion được gọi, thread thực thi callback có chắc là thread cha không?  
**Đáp án:** Không. Callback có thể chạy trên thread cuối kích hoạt completion traversal.

**Câu 13.** `complete(T)` có giống `tryComplete` không?  
**Đáp án:** Không. Complete có thể kết thúc task bất kể pending count, phù hợp early-completion của một số thuật toán nhưng sai với all-work completion nếu dùng sớm.

**Câu 14.** `propagateCompletion` khác `tryComplete` thế nào?  
**Đáp án:** Nó dùng completion traversal nhưng bỏ qua `onCompletion`; phù hợp khi không cần callback kết hợp kết quả.

**Câu 15.** Khi đếm thiếu child, kết quả nào có thể xảy ra?  
**Đáp án:** Root completed sớm, onCompletion tổng hợp dữ liệu thiếu, caller invoke return sớm, một số child vẫn chạy/ghi state.

**Câu 16.** Khi đếm thừa hoặc quên self signal, kết quả nào có thể xảy ra?  
**Đáp án:** Root không nhận đủ một invocation quan sát pending 0, nên `join/invoke` có thể chờ vô hạn.

**Câu 17.** Vì sao stress test pass nhiều lần chưa đủ chứng minh count đúng?  
**Đáp án:** Lịch thread có thể chỉ hiếm khi child hoàn tất trước parent set count. Phải chứng minh register-before-fork cho mọi interleaving hợp lệ.

**Câu 18.** Có thể cho thread khác thêm child sau khi root đã done không?  
**Đáp án:** Có thể có code làm vậy, nhưng nó **không thuộc completion protocol hợp lệ** của root đã done; cần thiết kế coordination khác thay vì tăng pending muộn.

## 28. Tài liệu tham khảo

- [Java SE 17 — CountedCompleter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountedCompleter.html): đặc tả pending count, `setPendingCount`, `addToPendingCount`, `tryComplete` và ví dụ **“must set pending count before fork”**.
- [Java SE 17 — ForkJoinTask](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ForkJoinTask.html): `fork`, `join`, `invoke`, lifecycle/exception handling.
- [Java SE 17 — ForkJoinPool](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ForkJoinPool.html): work stealing, `invoke`, parallelism và monitoring.
- [Java SE 17 — RecursiveTask](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/RecursiveTask.html): kiểu Fork/Join task trả kết quả.
- [Java SE 17 — RecursiveAction](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/RecursiveAction.html): kiểu Fork/Join task không trả giá trị.
- [Java SE 17 — AtomicLong](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicLong.html): atomic addition cho shared counters.
- [Java Language Specification `17 — Threads and Locks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): data race, happens-before và memory ordering.

**Ghi nhớ cuối cùng:** `fork()` có thể khiến child chạy và kết thúc **trước câu lệnh tiếp theo của parent**. Vì vậy **đăng ký pending count trước khi fork** không phải một mẹo tối ưu mà là điều kiện correctness của CountedCompleter. Với mẫu dễ hiểu `setPendingCount(n); fork n children; tryComplete();`, count và signals phải khớp; với các biến thể tối ưu, phải chứng minh lại số signals. Chỉ khi đó `onCompletion` và `invoke(root)` mới biểu thị đúng “toàn bộ dependencies đã hoàn tất”.
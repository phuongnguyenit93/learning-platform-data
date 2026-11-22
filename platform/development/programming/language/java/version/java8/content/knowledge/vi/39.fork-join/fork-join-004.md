# CountedCompleter và cơ chế hoàn tất theo quan hệ tác vụ trong Java

`CountedCompleter<T>` thuộc `java.util.concurrent`, là một lớp trừu tượng kế thừa `ForkJoinTask<T>`. Khác với mô hình thường gặp của `RecursiveTask` hoặc `RecursiveAction`, nơi task cha có thể gọi `join()` để **đợi từng task con**, `CountedCompleter` cho phép tổ chức việc hoàn tất qua **quan hệ completer và bộ đếm pending**. Khi một task con hoàn tất, nó có thể thông báo dọc theo chuỗi completer; task cha chỉ kích hoạt hành động hoàn tất ở thời điểm giao thức đếm cho phép.

Điều đó có ích khi ta có **nhiều nhánh công việc**, muốn chạy các nhánh độc lập và xử lý kết quả khi những nhánh cần thiết đã xong, mà không bắt một worker trong Fork/Join pool chặn trên `join()` của từng task con.

~~~java
class Example extends CountedCompleter<Void> {
    Example(CountedCompleter<?> parent) {
        super(parent);
    }

    @Override
    public void compute() {
        // Xử lý công việc.
        tryComplete(); // Tín hiệu hoàn tất theo cây completer.
    }
}
~~~

Đây là **minh họa class**, không phải chương trình hoàn chỉnh; cần import `java.util.concurrent.CountedCompleter`. `compute()` phải được tự triển khai; trong phần lớn thiết kế, nó sẽ gọi `tryComplete()` đúng theo giao thức hoàn tất đã chọn.

**Điểm then chốt:** `CountedCompleter` không quản lý danh sách tác vụ con cho bạn. **`pending count` chỉ là một bộ đếm nguyên tử**, không phải số lượng task được thư viện tự theo dõi. Đặt pending count bao nhiêu, ai gọi `tryComplete()`, ai fork nhánh nào và khi nào root được coi là xong đều phải được thiết kế nhất quán.

API này có từ **Java 8** và **vẫn được hỗ trợ trong Java hiện đại**. Bài giải thích các bảo đảm hiện hành, công thức đếm, `onCompletion`, `propagateCompletion`, cách đưa kết quả lên root, exceptional completion, các trường hợp trigger và ví dụ Java chạy được trên **JDK 17+**. Đây là chủ đề riêng của phần **Fork/Join**; `CompletableFuture` và `CountDownLatch` được nhắc để đối chiếu mục tiêu, không thay thế cơ chế CountedCompleter.

## 1. Vì sao cần một mô hình hoàn tất khác ForkJoinTask thông thường?

Một bài toán chia để trị có thể gồm:

~~~text
                  ROOT
                /      \
             LEFT      RIGHT
            /    \     /    \
           A      B   C      D
~~~

Trong `RecursiveTask<T>`, cách phổ biến là task cha fork một nhánh, compute nhánh kia rồi `join()` để lấy kết quả nhánh đã fork. Cách này **đúng** và work-stealing của Fork/Join có cơ chế hỗ trợ join. Nhưng có những bài toán mà việc nhánh con phải đợi hoặc thời gian xử lý giữa các nhánh rất khác nhau khiến mô hình **continuation theo hoàn tất** thuận tiện hơn.

Với `CountedCompleter`, mỗi child có thể giữ tham chiếu `completer` trỏ về parent. Khi child báo đã xong, bộ đếm pending ở parent được xử lý; **nhánh cuối cùng làm bộ đếm đủ điều kiện** sẽ thực hiện `onCompletion(...)` của parent rồi tiếp tục đi lên.

Ý nghĩa:

- Worker xử lý leaf xong có thể **thông báo** thay vì phải giữ một stack chờ các sibling bằng `join()`.
- Parent có thể **kết hợp** kết quả trong `onCompletion(...)` khi các child cần thiết đã báo xong.
- Root chỉ chuyển sang trạng thái hoàn tất bình thường sau khi giao thức hoàn tất thực sự **truyền tới root**.
- Không tự động có **thứ tự chạy** hay **thứ tự kết thúc** cố định giữa các child.
- Không tự động có **hủy công việc con** hoặc kiểm tra mọi state nghiệp vụ; người viết task phải thiết kế chúng.

Tài liệu chính thức lưu ý CountedCompleter thường **khó trực quan hơn** các dạng ForkJoinTask khác. Chỉ dùng khi cần lợi ích cụ thể của completion tree, custom trigger hoặc hiệu năng được đo, không chọn vì nó “mạnh hơn” trong mọi bài toán.

## 2. Những thành phần của CountedCompleter

| API/thành phần | Tác dụng | Lưu ý quan trọng |
| --- | --- | --- |
| `CountedCompleter<T>` | Task có quan hệ hoàn tất đến một completer khác | Kế thừa `ForkJoinTask<T>` |
| `compute()` | Nội dung công việc do subclass định nghĩa | Thường gọi `tryComplete()` hoặc `propagateCompletion()` sau khi làm việc |
| `getCompleter()` | Lấy parent/completer liên kết trong constructor | Không đồng nghĩa parent đang chạy |
| `getRoot()` | Lấy gốc của chuỗi completer | Có thể gọi `quietlyCompleteRoot()` khi chính sách cho phép |
| `getPendingCount()` | Đọc số pending hiện tại | Là số **tín hiệu đếm**, không phải danh sách con |
| `setPendingCount(n)` | Gán số pending | Phải thiết lập đúng thời điểm, trước khi fork tác vụ có thể báo xong |
| `addToPendingCount(delta)` | Điều chỉnh pending count bằng thao tác nguyên tử | Dùng khi số nhánh tăng dần trong phân rã |
| `compareAndSetPendingCount(old,new)` | CAS pending count | Có ích cho state machine tùy chỉnh |
| `decrementPendingCountUnlessZero()` | Giảm nếu nonzero, trả giá trị trước khi giảm | Không tự gọi `onCompletion` |
| `tryComplete()` | Báo một completion và đi lên khi đủ điều kiện | Có thể chạy `onCompletion` tại nhiều nút trên chuỗi |
| `propagateCompletion()` | Giống tryComplete về việc xử lý count/đi lên | **Không chạy `onCompletion`** dọc chuỗi |
| `onCompletion(caller)` | Callback khi node đạt điều kiện completion | Có thể được chạy bởi thread hoàn tất nhánh cuối |
| `onExceptionalCompletion(ex,caller)` | Xử lý và quyết định có lan truyền lỗi lên completer không | Mặc định trả `true` |
| `firstComplete()`/`nextComplete()` | Duyệt tùy chỉnh các node đạt điều kiện completion | Phải tuân thủ giao thức riêng, không trộn tùy tiện với tryComplete |
| `getRawResult()` | Cung cấp kết quả của CountedCompleter có giá trị T | Mặc định thường trả `null` nếu không override |
| `complete(T)` | Buộc task hoàn tất bất kể pending count | Không phải một tín hiệu đếm bình thường |
| `quietlyCompleteRoot()` | Đánh dấu root hoàn tất bình thường, không gọi `onCompletion` của root | Phù hợp một số trường hợp đã tìm được câu trả lời sớm |
| `helpComplete(maxTasks)` | Cố hỗ trợ một số task chưa xử lý trên completion path | Không phải `join()` hoặc đảm bảo tiến độ vô hạn |

**Không nhầm `pending count` với `ForkJoinPool.getQueuedTaskCount()`**: một cái là trạng thái giao thức hoàn tất của một task, cái kia là ước lượng hàng đợi làm việc của pool. Chúng không có cùng ngữ nghĩa.

## 3. Constructor: completer và pending count được gắn thế nào?

`CountedCompleter` cung cấp constructor nhận một parent/completer và số pending ban đầu:

~~~java
class Part extends CountedCompleter<Void> {
    Part(CountedCompleter<?> parent) {
        super(parent); // Pending mặc định là 0.
    }

    Part(CountedCompleter<?> parent, int pending) {
        super(parent, pending);
    }

    @Override
    public void compute() {
        tryComplete();
    }
}
~~~

Đây là class **minh họa**, không phải chương trình chính. Có thể tạo root bằng `super(null)` hoặc constructor mặc định; các child lấy parent đã tạo làm completer.

~~~text
ROOT  getCompleter() -> null
LEFT  getCompleter() -> ROOT
RIGHT getCompleter() -> ROOT
LEAF  getCompleter() -> LEFT
~~~

Quan hệ completer này là quan hệ **điểm nhận completion**, không bắt buộc giống quan hệ object sở hữu toàn bộ dữ liệu. Nếu bạn cần kết quả child khi callback parent chạy, phải **tự lưu liên kết** như `left`/`right` hoặc một cấu trúc lưu result phù hợp.

### 3.1. Parent có thể không bao giờ chạy compute()

Một CountedCompleter có thể chỉ làm **trigger node**: nó không được fork hoặc execute trực tiếp, mà được tạo để nhận hai tín hiệu completion từ hai tác vụ khác. Khi tín hiệu đủ điều kiện, callback `onCompletion` chạy và root được đánh dấu done.

Với kiểu trigger đó, số pending ban đầu có thể trông “lệch một”. Lý do sẽ rõ khi hiểu chính xác `tryComplete`.

## 4. Quy tắc của tryComplete(): **đếm đến zero rồi một tín hiệu nữa kích hoạt**

Mô tả chính thức của `tryComplete()`:

1. Nếu `pending count != 0`: **giảm đi một**; **không** gọi `onCompletion` cho node ở lần này.
2. Nếu `pending count == 0` khi bước đó được thực hiện: gọi `onCompletion(caller)`, rồi **tiếp tục thông báo completer** của node.
3. Khi chuỗi đến root không còn completer, root được đánh dấu hoàn tất bình thường để `invoke()/join()` có thể trả kết quả.

Pseudo-flow:

~~~text
tryComplete(task):
    node = task
    caller = task
    loop:
        if node.pending != 0:
            atomically decrement node.pending
            return
        node.onCompletion(caller)
        caller = node
        if node.completer == null:
            complete root status
            return
        node = node.completer
~~~

Đây là **mô hình khái niệm**, không phải mã nguồn Java nội bộ. Nó giải thích ý nghĩa API ở mức contract.

### 4.1. Công thức đếm tín hiệu

Nếu một node sẽ nhận **K lời gọi tryComplete theo đúng giao thức**, và muốn lời gọi **thứ K** làm node hoàn tất, giá trị pending ban đầu thường là **K − 1**:

~~~text
pending ban đầu = 2

Tín hiệu 1 -> pending 2 thành 1
Tín hiệu 2 -> pending 1 thành 0
Tín hiệu 3 -> thấy 0 -> onCompletion
~~~

Đây là cách nhìn phù hợp cho ví dụ một node nhận ba tín hiệu.

Tuy nhiên, **K không nhất thiết bằng số child**. Nếu parent tự gọi `tryComplete()` sau khi đã fork các child, tín hiệu của parent cũng tham gia. Vì thế mẫu “hai child + một lần parent tự báo” có **ba tín hiệu**; pending ban đầu đúng là **2**.

### 4.2. Mẫu hai child được fork và parent tự gọi tryComplete

~~~java
@Override
public void compute() {
    if (hi - lo >= 2) {
        int mid = (lo + hi) >>> 1;

        setPendingCount(2); // Hai child + parent = ba tín hiệu.
        new Task(this, lo, mid).fork();
        new Task(this, mid, hi).fork();
    } else {
        // Xử lý leaf.
    }
    tryComplete(); // Tín hiệu của chính node (hoặc leaf).
}
~~~

Đây là **mẫu minh họa**, class `Task`/fields được định nghĩa ở ví dụ đầy đủ bên dưới. Cần **đặt pending trước khi fork**, vì child có thể chạy và báo hoàn tất ngay lập tức.

Lịch tín hiệu có thể là parent trước, child A trước hay child B trước; tính đúng không phụ thuộc lịch nào là thứ nhất, miễn **có đúng ba tín hiệu** và mỗi child chỉ báo khi công việc thuộc nhánh của nó đã hoàn tất.

### 4.3. Mẫu một child fork, một child compute trực tiếp

Javadoc đưa ra tối ưu hóa thường dùng:

~~~java
@Override
public void compute() {
    if (hi - lo >= 2) {
        int mid = (lo + hi) >>> 1;
        setPendingCount(1);
        new Task(this, mid, hi).fork();
        new Task(this, lo, mid).compute();
        // Không gọi tryComplete() thêm ở nhánh internal này.
    } else {
        processLeaf();
        tryComplete();
    }
}
~~~

Đây là **mã minh họa**; `processLeaf` và các fields không được định nghĩa riêng trong đoạn. Hai child thông báo hai lần, nên pending = 1; parent không tự gửi tín hiệu thứ ba. Chiến lược này tránh tạo/fork quá nhiều task và tránh chặn bằng `join` ở parent. Không copy giá trị pending của mô hình này sang mô hình có thêm một `tryComplete` của parent.

**Quy tắc review:** trước khi viết code, vẽ **từng nguồn phát completion**; sau đó đếm xem cần bao nhiêu lần giảm và lần nào thật sự kích hoạt callback. Đừng coi pending là counter được runtime tự tăng khi gọi `fork()` — nó **không tự tăng**.

## 5. Quan hệ completion đi lên cây diễn ra thế nào?

Xét cây hai child:

~~~text
               ROOT (pending=2)
               /             \
        LEFT (0)           RIGHT (0)
~~~

Mẫu parent fork cả LEFT và RIGHT, rồi tự gọi `tryComplete()`:

- ROOT gọi `tryComplete`: một tín hiệu, pending có thể từ 2 → 1.
- LEFT hoàn thành và gọi `tryComplete`: callback `onCompletion` của LEFT chạy, rồi đi lên ROOT. ROOT thấy pending có thể từ 1 → 0.
- RIGHT hoàn thành và gọi `tryComplete`: callback của RIGHT chạy, rồi đi lên ROOT. ROOT thấy 0, chạy `ROOT.onCompletion(RIGHT)` và đánh dấu ROOT done.

Trong một lịch khác, LEFT/RIGHT có thể xong trước khi ROOT tự báo. Khi đó ROOT có thể là **caller của chính mình** ở tín hiệu cuối. Điều quan trọng là **hoàn tất đúng sau khi đã nhận đủ tín hiệu**, không giả định “thread xử lý RIGHT luôn gọi callback của ROOT”.

### 5.1. onCompletion(caller) không phải callback của một thread cố định

`onCompletion(CountedCompleter<?> caller)` nhận một object tham chiếu đến node gây completion cuối. Nó có thể bằng `this` hoặc một child, tùy thiết kế và timing.

~~~java
@Override
public void onCompletion(CountedCompleter<?> caller) {
    // Không suy rằng caller luôn là RIGHT.
    // Thông thường đọc result từ các child đã hoàn tất.
}
~~~

Trong mẫu cây lưu `left`/`right`, parent có thể dùng các field child đó để ghép kết quả, thay vì suy ra toàn bộ dữ liệu chỉ từ `caller`. Theo Javadoc, khi pending được dùng đúng, việc đọc field của task đã hoàn tất trong `onCompletion` được thiết kế để không cần thêm synchronized chỉ nhằm bảo vệ **liên kết kết quả đã hoàn tất của chính mô hình đó**. Điều này không có nghĩa mọi object mutable bên ngoài tự thread-safe.

### 5.2. onCompletion chỉ phục vụ normal completion

`onCompletion` là hook cho **đường hoàn tất bình thường**, không phải finally block bắt mọi lỗi. Nếu `compute()` hoặc một child ném exception, cần xem cơ chế exceptional completion riêng. Không viết nghiệp vụ “luôn xóa tài nguyên” chỉ trong `onCompletion` nếu tài nguyên cũng phải dọn khi task lỗi.

## 6. Tại sao một internal CountedCompleter không nhất thiết là isDone()?

Đây là điểm khác lớn với `RecursiveTask` thông thường. Oracle Javadoc giải thích CountedCompleter **có completer khác** thường được xem là helper nội bộ; trạng thái `ForkJoinTask.isDone()` của helper đó **không nhất thiết trùng** với việc nó đã báo hoàn tất trong cây.

Khi một internal CountedCompleter gọi `tryComplete()`, completion có thể được **truyền lên completer** mà không đánh dấu trạng thái ForkJoinTask của chính internal node thành done theo cách bạn kỳ vọng. Trạng thái ForkJoinTask của child chỉ thay đổi qua một số thao tác explicit, và không nên dùng `join()` trên các internal helper như cách chờ tiêu chuẩn của CountedCompleter tree.

**Thiết kế đúng:** thường `ForkJoinPool.invoke(root)` hoặc `root.join()` ở **gốc** để chờ việc xử lý cả cây đã báo hoàn tất. Tránh vòng `for (child : children) child.join()` trên các child CountedCompleter, vì các child không có cùng semantics isDone với RecursiveTask. Phụ thuộc chính của mô hình nằm ở **completer chain**, không phải join từng helper.

### 6.1. Root là ranh giới kết quả

Root thường có `getCompleter() == null`. Khi tín hiệu đi tới root trong trạng thái đủ điều kiện, task root được đánh dấu hoàn tất. `invoke()/join()` trên root có thể trả về.

Nếu root không có result T, khai báo `CountedCompleter<Void>` và `invoke()` sẽ nhận `null` khi thành công. Nếu root phải mang một giá trị, override `getRawResult()`; nội dung này có ví dụ ở phần sau.

## 7. propagateCompletion(): khi không cần chạy onCompletion

`propagateCompletion()` đi theo quy tắc giảm count/đi lên completer **tương tự `tryComplete()`** nhưng **không gọi `onCompletion(...)`** trên chuỗi.

| Chọn API | Có xử lý pending/đi lên completer? | Chạy onCompletion? | Trường hợp phù hợp |
| --- | --- | --- | --- |
| `tryComplete()` | Có | Có khi node đủ điều kiện | Cần kết hợp kết quả hoặc thực hiện completion hook |
| `propagateCompletion()` | Có | **Không** | Chỉ cần báo hoàn tất theo cây, không có callback per-node |
| `complete(value)` | Không chờ pending count của task đó | Gọi `onCompletion` của task rồi đánh dấu nó xong, truyền tín hiệu lên parent | Ép hoàn tất có chủ đích, không phải thay thế thường xuyên cho tryComplete |
| `quietlyCompleteRoot()` | Không thực hiện hành động pending count thông thường | **Không** gọi onCompletion của root | Hoàn tất gốc sớm theo policy riêng |

### 7.1. Khi nào propagateCompletion là tối ưu hợp lệ?

Nếu mỗi leaf chỉ làm side effect idempotent/đếm sự kiện, và **không có node nào cần `onCompletion`** để ghép kết quả, có thể dùng `propagateCompletion()` cuối nhánh.

~~~java
@Override
public void compute() {
    processAssignedChunk();
    propagateCompletion();
}
~~~

Đoạn này là minh họa, `processAssignedChunk` do ứng dụng định nghĩa. Nhưng **không dùng propagateCompletion trong một cây phải thực hiện phép reduce ở onCompletion**, vì khi đó bạn bỏ qua chính logic kết hợp cần thiết.

### 7.2. Không nhầm với `complete(T)`

`complete(T)` khác hẳn: nó **buộc task hoàn tất bất kể pending count**, gọi hook và báo lên completer. Đây là một công cụ mạnh cho những thiết kế trigger kết quả sớm, nhưng dễ sai nếu dùng để “cho join khỏi treo” trong một thuật toán vốn cần chờ tất cả child.

Nếu chưa chứng minh được bất biến “đã đủ dữ liệu để hoàn tất ngay”, đừng gọi `complete(value)` như một cách xử lý pending count sai.

## 8. Kết hợp kết quả trong onCompletion: cần lưu child references

`CountedCompleter` **không tự thu thập** danh sách con. Muốn tính tổng kết quả của hai child, parent phải có liên kết:

~~~java
class SumTask extends CountedCompleter<Integer> {
    final int[] data;
    final int lo, hi;
    SumTask left, right;
    int result;

    // Constructor/compute/getRawResult xem bản đầy đủ.
    
    @Override
    public void onCompletion(CountedCompleter<?> caller) {
        if (left != null) {
            result = left.result + right.result;
        }
    }

    @Override
    public Integer getRawResult() {
        return result;
    }
}
~~~

Đoạn này là **trích minh họa**, chưa tự biên dịch vì thiếu constructor và compute. Leaf sẽ tính `result` trên đoạn dữ liệu của nó; internal node chờ cả hai child có result, rồi `onCompletion` cộng lại. Điều kiện `left != null` dùng vì ở leaf không có child để ghép.

**Nếu phép ghép không giao hoán** như phép nối chuỗi theo thứ tự hoặc tính toán cần left trước right, phải giữ **liên kết trái/phải rõ ràng**, không giả định child nào complete trước là “left”.

### 8.1. getRawResult() bắt buộc khi root cần giá trị

CountedCompleter thường dùng `CountedCompleter<Void>` và không cần result. Với `CountedCompleter<Integer>` muốn `invoke()` trả 36, override:

~~~java
@Override
public Integer getRawResult() {
    return result;
}
~~~

Tài liệu Oracle lưu ý `getRawResult()` mặc định thường trả `null` ở CountedCompleter; `setRawResult(T)` mặc định không có vai trò cho mô hình phổ biến này. Đừng chỉ thay generic thành `<Integer>` rồi kỳ vọng ForkJoin runtime tự gom tất cả kết quả.

## 9. firstComplete() và nextComplete(): tự duyệt đường completion

Khi `onCompletion` không thuận tiện, `CountedCompleter` cung cấp:

- **`firstComplete()`**: nếu pending của node đang là zero, trả chính node; nếu nonzero, giảm pending và trả `null`.
- **`nextComplete()`**: từ một node đã sẵn sàng, cố tiến lên completer; nếu pending của completer nonzero thì giảm và dừng; nếu zero thì trả completer; đến root, đánh dấu root complete và trả null.

Mẫu sử dụng:

~~~java
for (CountedCompleter<?> node = firstComplete();
     node != null;
     node = node.nextComplete()) {
    // Chạy một logic hoàn tất tùy chỉnh trên node
    // vừa được phép hoàn thành ở đường duyệt.
}
~~~

Đây là **mẫu minh họa bên trong một subclass CountedCompleter**. Tài liệu có ví dụ map/reduce duyệt các liên kết child bằng cơ chế này để ghép kết quả theo cây.

### 9.1. Đừng chạy hai cơ chế hoàn tất cho cùng một tín hiệu

Nếu một leaf đã gọi `firstComplete()/nextComplete()` theo protocol riêng, thường **không gọi `tryComplete()` lần nữa cho cùng completion event**. Làm vậy có thể làm thừa tín hiệu, khiến node cha hoàn tất sớm, hoặc thay đổi pending count sai.

Chọn **một giao thức completion rõ ràng** cho mỗi nhánh. Chỉ phối hợp hai loại khi đã chứng minh chính xác trạng thái đếm ở từng đường đi.

## 10. Exceptional completion: lỗi của child có thể đi lên completer

Bất kỳ `compute()` nào ném exception đều có thể làm CountedCompleter của task đó hoàn thành exceptional. API hỗ trợ:

~~~java
@Override
public boolean onExceptionalCompletion(
        Throwable ex, CountedCompleter<?> caller) {
    // Có thể ghi nhận exception ở phạm vi thích hợp.
    return true; // Cho phép lan truyền lên completer.
}
~~~

Đoạn trên là một **override minh họa** trong subclass; Javadoc nêu **mặc định trả true**, cho phép lan truyền lỗi lên chuỗi completer nếu parent chưa hoàn tất.

Điểm quan trọng:

- **`onCompletion` và `onExceptionalCompletion` là hai đường khác nhau.**
- Khi child thất bại, parent/root có thể hoàn thành exceptional mà **chưa cần mọi sibling đều chạy xong**.
- Root `invoke()/join()` có thể ném exception; không được coi task đã hoàn tất thành công.
- Sibling được fork trước đó có thể **tiếp tục chạy**, vì exceptional completion không phải cam kết dừng toàn bộ công việc bên dưới.
- Return `false` từ `onExceptionalCompletion` **ngăn lan truyền qua hook đó**, nhưng không có nghĩa “đã tự khôi phục nghiệp vụ”; muốn recovery phải thiết kế trạng thái, dữ liệu kết quả và completion protocol riêng.

### 10.1. Dọn tài nguyên khi cả success và failure

Nếu ứng dụng mở resource cần đóng, đừng chỉ đóng ở `onCompletion` nếu nhánh lỗi không vào callback ấy. Dùng `try/finally` trong phần xử lý có ownership tài nguyên, hoặc một cơ chế giám sát/lifecycle trên root xử lý cả normal và exceptional.

~~~java
@Override
public void compute() {
    Resource r = openResource();
    try {
        process(r);
        tryComplete();
    } finally {
        r.close();
    }
}
~~~

Đây là **pseudocode minh họa**, `Resource`/`openResource`/`process` do ứng dụng định nghĩa. Nếu `process` ném, `tryComplete` không chạy và exceptional completion được ForkJoin framework xử lý. `finally` vẫn đóng resource.

### 10.2. Side effects và idempotency

Nếu leaf gọi API bên ngoài gây side effect, completion tree không tự cung cấp exactly-once, retry hay transaction. Khi root lỗi, không tự chạy lại mọi leaf nếu có nguy cơ gửi thanh toán/ghi đơn hàng hai lần. Phân tách logic tính toán có thể chạy lại, side effect có policy idempotency, và giám sát lỗi.

## 11. Kích hoạt completion theo hai tác vụ không cần chạy root.compute()

CountedCompleter còn có thể là một **trigger** nhận nhiều completion event. Ví dụ hai tác vụ độc lập là `header` và `body`, khi cả hai xong thì mới gửi packet:

~~~text
HeaderBuilder ----\
                   >-- Coordinator.onCompletion -> send
BodyBuilder -------/
~~~

Một Coordinator **không bao giờ được execute** mà chỉ nhận hai tín hiệu có thể dùng:

~~~java
class Coordinator extends CountedCompleter<Void> {
    Coordinator() {
        super(null, 1);
    }

    @Override
    public void compute() {
        // Không được gọi: chỉ làm completion trigger.
    }

    @Override
    public void onCompletion(CountedCompleter<?> caller) {
        // Thực hiện việc cần thiết sau hai tín hiệu.
    }
}
~~~

Đây là mã minh họa; cần hai child có `super(coordinator)` và mỗi child gọi `tryComplete()` khi xong. Tại sao pending = **1**, không phải 2?

~~~text
Coordinator.pending = 1
Header hoàn tất -> Coordinator.tryComplete -> 1 thành 0
Body hoàn tất   -> Coordinator.tryComplete -> thấy 0 -> onCompletion
~~~

Vì **Coordinator không tự gửi tín hiệu**, chỉ có đúng **hai** completion events. Đây là một ví dụ chính thức cho thấy pending count **không tự bằng “số child”**.

**Không lạm dụng:** nếu trigger yêu cầu dữ liệu từ cả header/body, callback phải có cách đọc các giá trị tương ứng an toàn. Nếu một child lỗi, callback bình thường có thể không chạy và lỗi có thể được truyền lên coordinator theo exceptional-completion contract. Một trigger có side effect quan trọng vẫn phải xử lý retry, timeout, idempotency.

## 12. complete(T), quietlyCompleteRoot() và short-circuit

Không phải thuật toán nào cũng cần chờ toàn bộ child. Ví dụ tìm kiếm song song: một nhánh tìm được giá trị mong muốn, ta có thể muốn **báo root đã có câu trả lời** để caller không cần đợi tất cả nhánh còn lại hoàn tất bình thường.

API hỗ trợ hai hướng:

1. `complete(T value)`: ép một CountedCompleter hoàn thành, gọi `setRawResult(value)` (mặc định không có tác dụng), `onCompletion`, rồi thông báo completer. Cần hiểu tác dụng của việc không đợi pending.
2. `quietlyCompleteRoot()`: đánh dấu root hoàn tất **không gọi `onCompletion` của root**. Tài liệu dùng cùng `AtomicReference` chia sẻ kết quả để một nhánh tìm được có thể đánh dấu root done.

~~~java
if (result.compareAndSet(null, found)) {
    quietlyCompleteRoot();
}
~~~

Đây là **mã minh họa bên trong task tìm kiếm**, `result` là `AtomicReference<T>`; không phải toàn bộ chương trình. Các nhánh khác cần tự kiểm tra `result.get()!=null` để dừng sớm theo policy, nếu không chúng có thể vẫn tiếp tục chạy.

**Quan trọng:** hoàn tất root sớm không phải cancellation/interrupt của các leaf đang chạy; không được dùng trong thuật toán đòi tất cả side effect hoặc bắt buộc tổng hợp mọi dữ liệu, vì root có thể trả trước khi phần việc đó đã hoàn tất.

## 13. helpComplete(maxTasks) và cân bằng tải

`helpComplete(int maxTasks)` có thể cố xử lý tối đa một số task chưa được xử lý mà CountedCompleter nằm trên đường completer của chúng. Nếu `maxTasks <= 0` thì không xử lý task nào.

Đây là một công cụ hỗ trợ hợp tác khi có cây completion và task đang pending, không phải lời hứa:

- Tất cả task sẽ hoàn tất ngay.
- Nó sẽ chờ đến khi root done.
- Nó sửa pending count sai.
- Nó tạo thêm worker vô hạn.
- Nó thay thế `ForkJoinPool.invoke(root)`.

Trong phần lớn ví dụ dạy nhập môn, chỉ cần `fork` và `invoke(root)`; chỉ xem xét `helpComplete` khi thiết kế đã hiểu rõ cây task và có nhu cầu điều khiển tiến độ đặc biệt.

## 14. Chương trình Java hoàn chỉnh: ba kiểu quan hệ hoàn tất

Ví dụ sau minh họa **đúng ba cơ chế** trong một chương trình:

- **`ForEachAction`**: cây tác vụ cập nhật một `AtomicInteger`, mỗi internal node fork hai child rồi **tự gọi `tryComplete`**, nên dùng `setPendingCount(2)`. Đếm số lần callback `onCompletion` để xác minh completion của mọi node.
- **`SumTask`**: cây tính tổng, mỗi child ghi kết quả vào field riêng, parent ghép chúng trong `onCompletion`, root override `getRawResult` để `invoke(root)` trả kết quả.
- **`Coordinator` + `Part`**: root đóng vai trò trigger, **không chạy compute**, chờ **hai** child báo hoàn tất; pending = **1**.

Chương trình không dùng `Thread.sleep`, không in tên thread và chỉ in sau các điểm hoàn tất được bảo đảm. Vì vậy thứ tự worker được lên lịch không làm thay đổi expected stdout.

Lưu vào **`CountedCompleterGuideDemo.java`**:

~~~java
import java.util.concurrent.CountedCompleter;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.atomic.AtomicInteger;

public final class CountedCompleterGuideDemo {

    private CountedCompleterGuideDemo() {
    }

    static final class ForEachAction
            extends CountedCompleter<Void> {
        final int[] data;
        final int lo, hi;
        final AtomicInteger sum;
        final AtomicInteger processed;
        final AtomicInteger completedNodes;

        ForEachAction(
                CountedCompleter<?> parent,
                int[] data,
                int lo,
                int hi,
                AtomicInteger sum,
                AtomicInteger processed,
                AtomicInteger completedNodes) {

            super(parent);
            this.data = data;
            this.lo = lo;
            this.hi = hi;
            this.sum = sum;
            this.processed = processed;
            this.completedNodes = completedNodes;
        }

        @Override
        public void compute() {
            if (hi - lo > 2) {
                int mid = (lo + hi) >>> 1;

                // Hai child + self tryComplete = 3 signals.
                setPendingCount(2);

                new ForEachAction(
                        this, data, lo, mid,
                        sum, processed, completedNodes)
                        .fork();

                new ForEachAction(
                        this, data, mid, hi,
                        sum, processed, completedNodes)
                        .fork();

            } else {
                for (int i = lo; i < hi; i++) {
                    sum.addAndGet(data[i]);
                    processed.incrementAndGet();
                }
            }
            tryComplete();
        }

        @Override
        public void onCompletion(CountedCompleter<?> caller) {
            completedNodes.incrementAndGet();
        }
    }

    static final class SumTask
            extends CountedCompleter<Integer> {
        final int[] data;
        final int lo, hi;
        SumTask left, right;
        int result;

        SumTask(
                CountedCompleter<?> parent,
                int[] data,
                int lo,
                int hi) {

            super(parent);
            this.data = data;
            this.lo = lo;
            this.hi = hi;
        }

        @Override
        public void compute() {
            if (hi - lo > 2) {
                int mid = (lo + hi) >>> 1;

                left = new SumTask(this, data, lo, mid);
                right = new SumTask(this, data, mid, hi);

                // Hai child + self signal = ba signals.
                setPendingCount(2);
                left.fork();
                right.fork();
            } else {
                int local = 0;
                for (int i = lo; i < hi; i++) {
                    local += data[i];
                }
                result = local;
            }
            tryComplete();
        }

        @Override
        public void onCompletion(CountedCompleter<?> caller) {
            // Chỉ internal node có left/right.
            // Đủ completion -> hai child đã có result.
            if (left != null) {
                result = left.result + right.result;
            }
        }

        @Override
        public Integer getRawResult() {
            return result;
        }
    }

    static final class Coordinator
            extends CountedCompleter<Void> {
        final AtomicInteger finishedParts =
                new AtomicInteger();
        final AtomicInteger completionCalls =
                new AtomicInteger();

        Coordinator() {
            // Chỉ HAI child báo hoàn tất, coordinator
            // KHÔNG tự gọi tryComplete().
            super(null, 1);
        }

        @Override
        public void compute() {
            // Chỉ là completion trigger; không execute.
        }

        @Override
        public void onCompletion(CountedCompleter<?> caller) {
            if (finishedParts.get() != 2) {
                throw new AssertionError(
                    "Coordinator completed too early");
            }
            completionCalls.incrementAndGet();
        }
    }

    static final class Part
            extends CountedCompleter<Void> {
        final Coordinator coordinator;

        Part(Coordinator coordinator) {
            super(coordinator);
            this.coordinator = coordinator;
        }

        @Override
        public void compute() {
            coordinator.finishedParts.incrementAndGet();
            tryComplete();
        }
    }

    public static void main(String[] args) {
        int[] data = {1, 2, 3, 4, 5, 6, 7, 8};

        ForkJoinPool pool = new ForkJoinPool(4);
        try {
            AtomicInteger sum = new AtomicInteger();
            AtomicInteger processed = new AtomicInteger();
            AtomicInteger nodeCompletions =
                    new AtomicInteger();

            ForEachAction foreach = new ForEachAction(
                null, data, 0, data.length,
                sum, processed, nodeCompletions);

            // invoke chờ ROOT hoàn tất, không join leaf.
            Void noValue = pool.invoke(foreach);

            System.out.println("forEachResultNull="
                    + (noValue == null));
            System.out.println("forEachSum=" + sum.get());
            System.out.println("elementsProcessed="
                    + processed.get());

            // 8 phần tử, mỗi leaf xử lý 2 phần tử:
            // 4 leaves + 3 internal nodes = 7.
            System.out.println("onCompletionCalls="
                    + nodeCompletions.get());
            System.out.println("rootPending="
                    + foreach.getPendingCount());

            SumTask root =
                    new SumTask(null, data, 0, data.length);

            int reduced = pool.invoke(root);
            System.out.println("reducedSum=" + reduced);
            System.out.println("rawResult="
                    + root.getRawResult());
            System.out.println("rootDone="
                    + root.isDone());

            Coordinator coordinator = new Coordinator();

            // Coordinator không được submit/invoke trực tiếp.
            // Chỉ hai Part làm việc trong ForkJoinPool.
            pool.execute(new Part(coordinator));
            pool.execute(new Part(coordinator));

            // Root hoàn tất nhờ chuỗi child -> completer.
            coordinator.join();

            System.out.println("parts="
                    + coordinator.finishedParts.get());
            System.out.println("triggerCalls="
                    + coordinator.completionCalls.get());
            System.out.println("coordinatorDone="
                    + coordinator.isDone());

        } finally {
            pool.shutdown();
        }
    }
}
~~~

### Biên dịch và chạy

~~~bash
javac -encoding UTF-8 CountedCompleterGuideDemo.java
java CountedCompleterGuideDemo
~~~

**Đầu ra dự kiến** (không in thứ tự task, chỉ in sau completion):

~~~text
forEachResultNull=true
forEachSum=36
elementsProcessed=8
onCompletionCalls=7
rootPending=0
reducedSum=36
rawResult=36
rootDone=true
parts=2
triggerCalls=1
coordinatorDone=true
~~~

### 14.1. Vì sao ForEachAction hoàn tất đúng?

`data` có tám phần tử, threshold leaf là tối đa hai phần tử. Cây gồm bốn leaf và ba internal, tổng cộng **bảy CountedCompleter nodes**.

- Mỗi leaf cộng giá trị của hai phần tử vào `AtomicInteger` và tăng `processed` hai lần.
- Mỗi leaf có pending mặc định 0, gọi `tryComplete()` khiến chính nó chạy `onCompletion` và truyền một tín hiệu lên parent.
- Mỗi internal node set pending = 2, fork hai child, rồi tự gọi `tryComplete`. Hai child hoàn tất là hai tín hiệu còn lại; khi đủ **ba** tín hiệu, parent chạy `onCompletion` và báo tiếp lên trên.
- Mỗi node có đúng một callback `onCompletion` theo protocol; `nodeCompletions` đạt 7.
- Root `pool.invoke(foreach)` chờ completion tree thông báo đến gốc; vì là `CountedCompleter<Void>` nên kết quả của invoke là `null`.
- Sau khi root hoàn tất, `sum=1+2+3+4+5+6+7+8=36` và `processed=8`.
- `getPendingCount()` của root là 0 vì tín hiệu cuối chỉ chạy callback khi đếm đang bằng zero.

**Cẩn thận:** không assert thứ tự từng callback giữa các nhánh; phép tăng số callback được bảo vệ bởi `AtomicInteger`.

### 14.2. Vì sao SumTask trả đúng Integer?

`SumTask` lưu `left` và `right` trong parent trước khi fork. Mỗi leaf tính `result` của đoạn 1–2 phần tử của nó. Khi cả hai nhánh hoàn tất, `onCompletion` tại internal node đọc `left.result + right.result` và gán vào `result` của parent.

Phép tổng dần đi lên đến root. `getRawResult()` được override để trả field `result` đã được tính, do đó `pool.invoke(root)` trả `Integer 36`. Đây không phải một `RecursiveTask<Integer>` phải join từng child: **kết quả được ghép qua callback completion**.

Theo hợp đồng Oracle, `onCompletion` được dùng để đọc kết quả từ những child đã hoàn tất; không cần tự thêm một `synchronized` quanh từng field result của child trong thiết kế này chỉ để truyền kết quả lên, miễn pending/protocol đúng. Nhưng nếu bạn thay đổi child.result ngoài protocol hoặc chia sẻ dữ liệu với những writer không tham gia vào cây completion, cần đồng bộ thích hợp.

### 14.3. Vì sao Coordinator chỉ cần pending = 1?

`Coordinator` không chạy `compute()` và không tự `tryComplete()`. Chỉ **hai** đối tượng `Part` báo completed. Tín hiệu thứ nhất giảm pending 1 → 0; tín hiệu thứ hai thấy 0 và gọi `onCompletion`. Vì `Part.compute()` tăng `finishedParts` **trước** khi báo, callback nhìn thấy 2 ở thời điểm hoàn tất.

`coordinator.join()` chờ trạng thái root được đánh dấu done bởi chuỗi completer; root không cần được submit vào pool. `completionCalls==1` vì chỉ một tín hiệu thắng thời điểm pending của coordinator đang zero.

Đây là lý do pending phải được tính theo **số lần gọi completion**, không lấy một quy tắc “có hai con thì pending luôn là hai” áp dụng mọi mô hình.

### 14.4. Vì sao không có deadlock do join?

Trong `ForEachAction`/`SumTask`, parent chỉ **fork child rồi báo việc của mình**, không chặn worker để join child. Các child được pool thực thi rồi tự thông báo lên cây. Root được main chờ bằng `pool.invoke`. Trong trigger, main dùng `coordinator.join`; hai Part là những task pool có thể tiếp tục chạy.

Nếu bạn đặt `child.join()` ở các internal CountedCompleter tùy tiện, ngoài rủi ro chặn worker, **isDone của helper nội bộ có thể không có ngữ nghĩa như RecursiveTask**. Đây là một lỗi thiết kế đặc thù của CountedCompleter.

## 15. Phân biệt CountedCompleter, RecursiveTask, CompletableFuture và CountDownLatch

| Cấu trúc | Mục đích chính | Cách điều phối |
| --- | --- | --- |
| `RecursiveAction` | Chia để trị không trả giá trị | `compute/fork/join` theo kiểu ForkJoinTask |
| `RecursiveTask<T>` | Chia để trị có giá trị T | `fork/join`, parent ghép kết quả |
| `CountedCompleter<T>` | Chia/ghép công việc theo **completion tree** hoặc trigger, có pending count | Child báo `tryComplete`, callback `onCompletion`, root hoàn tất khi giao thức cho phép |
| `CompletableFuture<T>` | Pipeline async và phối hợp completion stages theo API cấp cao | `thenApply`, `thenCompose`, `allOf`, exception handlers |
| `CountDownLatch` | Đồng bộ một lần, đợi số lượng tín hiệu giảm về 0 | `countDown()/await()`, không tự tạo cây task hay callback ghép kết quả |
| `Phaser` | Phối hợp nhiều giai đoạn đồng bộ | `register/arrive/awaitAdvance` theo phase |

**Điểm không tương đương:** `CountDownLatch(2)` thực sự có hai `countDown` để về zero và giải phóng await. `CountedCompleter(pending=2)` theo quy tắc `tryComplete` cần **lần tín hiệu thứ ba để chạy onCompletion** nếu node không dùng cơ chế khác. Hai primitive dùng hai ngữ nghĩa đếm khác nhau.

Dùng `CompletableFuture.allOf` sẽ dễ hiểu hơn nếu ứng dụng chỉ có vài lời gọi async độc lập, cần đợi cả hai và xử lý lỗi. CountedCompleter phù hợp hơn khi cần **thuật toán phân rã tùy chỉnh**, completion traversal hoặc trigger trực tiếp trong hệ Fork/Join. Đừng viết CountedCompleter phức tạp chỉ để thay một `allOf` đơn giản.

## 16. Lỗi thường gặp khi dùng CountedCompleter

### Lỗi 1 — Đặt pendingCount bằng số child mà không đếm tín hiệu của parent

Nếu parent có hai child **và** tự gọi `tryComplete`, tổng ba tín hiệu, nên pending ban đầu **2**. Nếu chỉ có hai child và parent **không tự báo**, pending **1**. Đặt sai có thể khiến root hoàn tất quá sớm hoặc không bao giờ completed.

### Lỗi 2 — Quên gọi tryComplete ở leaf

Một leaf tính xong nhưng không báo completion, parent có thể mãi chờ pending. Không sửa bằng sleep hoặc timeout giả; sửa **giao thức báo hoàn tất**.

### Lỗi 3 — Fork trước rồi mới setPendingCount

Child có thể chạy và báo completion trước khi parent được cấu hình, khiến hoàn tất sai. **Luôn thiết lập pending trước khi fork** theo mẫu chính thức.

### Lỗi 4 — Gọi tryComplete hai lần cho cùng một completion event

Một tín hiệu thừa có thể làm parent hoàn tất sớm, dữ liệu child còn chưa sẵn sàng. Hãy ghi rõ ai là nguồn phát từng completion, không gọi trong cả nhánh con và finally mà không tính số lần.

### Lỗi 5 — Gọi tryComplete sau nhánh internal tối ưu đã có child.compute trực tiếp

Trong mẫu tối ưu pending 1 với hai child báo, parent **không** tự gửi tín hiệu. Nếu thêm `tryComplete` của parent, bạn có ba tín hiệu nhưng vẫn pending 1: đây là lỗi off-by-one.

### Lỗi 6 — Dùng propagateCompletion khi cần onCompletion để reduce

`propagateCompletion` không gọi hook kết hợp. Nếu SumTask dùng nó thay tryComplete mà không có logic ghép khác, root có thể không có tổng đúng.

### Lỗi 7 — Mong getRawResult tự thu giá trị child

`CountedCompleter<Integer>` không tự tính T. Cần lưu result, override `getRawResult()` và kết hợp trong callback hoặc giao thức riêng.

### Lỗi 8 — Join từng internal child như RecursiveTask

Theo Javadoc, trạng thái `isDone` của helper có completer có thể không phản ánh completion event đã đi lên cha. Đợi root, không join tùy tiện các helper.

### Lỗi 9 — Dùng CountedCompleter như một CountDownLatch(2) thông thường

`CountDownLatch` kích hoạt khi count **giảm thành zero**; `tryComplete` **giảm nonzero nhưng chỉ gọi onCompletion khi nó đã bằng zero lúc kiểm tra**. Cần hiểu công thức K−1.

### Lỗi 10 — Coi onCompletion chạy trên thread của parent

Callback có thể do thread hoàn tất tín hiệu cuối chạy. Không dùng `ThreadLocal`/thread identity để suy ra ownership của callback. Nếu dùng context nghiệp vụ, truyền qua field/data có quy tắc publication đúng.

### Lỗi 11 — Coi onCompletion luôn chạy dù child lỗi

Lỗi của `compute` đi theo exceptional-completion path; `onExceptionalCompletion` quyết định propagation. Dọn resource qua finally hoặc lifecycle đúng.

### Lỗi 12 — Tưởng root exceptional sẽ tự interrupt sibling

Một sibling có thể tiếp tục chạy sau khi root fail. Nếu cần stop sớm, thiết kế cancellation flag/kiểm tra hợp tác, hoặc API hủy I/O ở nguồn. Không tự suy ForkJoinTask.cancel là giao dịch rollback.

### Lỗi 13 — Chia mỗi phần tử thành một task quá nhỏ

Nếu xử lý một phép cộng nhỏ mà tạo một task cho mỗi phần tử, overhead fork/steal/allocation có thể lớn hơn tính toán. Dùng threshold/leaf chunk phù hợp; đo JMH hoặc benchmark ứng dụng thật.

### Lỗi 14 — Để onCompletion làm I/O blocking lâu

Thread xử lý completion có thể giữ worker phục vụ các task khác. Với I/O blocking, cân nhắc tách stage sang executor/cơ chế phù hợp, không khóa cả completion path bằng callback dài.

### Lỗi 15 — Không lưu liên kết child mà vẫn muốn reduce

CountedCompleter không giữ danh sách pending task. Nếu muốn cộng kết quả, parent phải lưu `left/right` hoặc một cấu trúc lưu result có đồng bộ thích hợp.

### Lỗi 16 — Ghép dữ liệu non-associative không kiểm soát thứ tự

Hai nhánh có thể hoàn tất theo thứ tự bất kỳ. Nếu phép kết hợp phụ thuộc thứ tự, giữ đúng vị trí trái/phải và thứ tự toán học; đừng giảm theo “task nào xong trước”.

### Lỗi 17 — Đọc pendingCount như “số task còn sống”

Nó chỉ là bộ đếm completion signals của protocol. `getPendingCount()==0` chưa đủ chứng minh root đã được đánh dấu done hay tất cả side effects bên ngoài đã hoàn thành. Dùng `root.join/invoke` để chờ root theo hợp đồng.

### Lỗi 18 — Gọi complete(value) để chữa một cây bị treo

`complete(value)` bỏ qua pending count của task đó; có thể bỏ qua công việc bắt buộc của child. Sửa nguyên nhân thiếu tín hiệu, không ép thành công giả.

### Lỗi 19 — Coi quietlyCompleteRoot là hủy hết công việc

Nó chỉ đánh dấu root done, không đảm bảo sibling ngừng chạy. Dùng khi thuật toán thật sự có thể trả sớm và quản lý work còn lại.

### Lỗi 20 — Chia sẻ mutable state bên ngoài không đồng bộ

CountedCompleter bảo vệ pending count/đường hoàn tất, không biến một `ArrayList`, `HashMap` hay phép `int++` của ứng dụng thành thread-safe. Dùng immutable data, `AtomicInteger`, concurrent collections hoặc giao thức ownership đúng.

### Lỗi 21 — Quên đóng ForkJoinPool do ứng dụng tạo

`ForkJoinPool pool = new ForkJoinPool(n)` nên có lifecycle và shutdown phù hợp. Đừng tùy tiện shutdown `ForkJoinPool.commonPool()` do cả JVM dùng chung.

### Lỗi 22 — Đặt pendingCount tùy ý để “không lỗi compile”

Giá trị pending count đúng là một phần **chứng minh thuật toán**, không phải giá trị config thử đại. Phải đếm đủ các đường phát completion của từng task khi viết, khi review và khi test.

## 17. Kiểm thử đúng đắn và tranh chấp

Một test CountedCompleter đáng tin cần:

1. **Kiểm tra root hoàn tất:** `root.isDone()` sau `pool.invoke(root)`; kiểm tra trạng thái normal/exceptional.
2. **Kiểm tra đầy đủ công việc:** dùng bộ đếm atomic hoặc output thu được, không chỉ xem không có exception.
3. **Kiểm tra số onCompletion:** với cây có cấu trúc xác định, assert số node được callback đúng một lần.
4. **Kiểm tra pending cuối:** với mẫu đơn giản, root pending = 0, nhưng không dùng duy nhất điều này để quyết định done.
5. **Kiểm tra rỗng/một phần tử:** range `[lo,hi)` trống và size=1 cần xử lý đúng, không sinh vòng chia vô hạn.
6. **Kiểm tra cây bất cân xứng:** số phần tử không phải lũy thừa hai, threshold khác nhau, task xử lý lâu/ngắn.
7. **Kiểm tra exception:** một leaf ném lỗi; root phải không bị hiểu là success và error phải có nơi quan sát.
8. **Kiểm tra timeout bên ngoài:** trong test có thể dùng `get(timeout,unit)` trên root để phát hiện thiếu tín hiệu, sau đó cleanup executor; không tự coi timeout đã dừng mọi task.
9. **Kiểm tra data race:** mọi field kết quả/side effect có thuộc đúng protocol completion không?
10. **Kiểm tra executor lifecycle:** pool được shutdown, không tạo vô hạn work.
11. **Không dùng Thread.sleep để đo completion:** dùng `CountDownLatch`/`Future.get`/`join` và state xác định.
12. **Không kết luận nhanh hơn RecursiveTask khi chưa benchmark:** hiệu năng phụ thuộc leaf threshold, số core, chi phí callback và phân bố nhánh.

### 17.1. Test trường hợp một phần tử và mảng trống

Với `ForEachAction` ở chương trình, range trống `[0,0)` vẫn vào leaf, không xử lý phần tử nào, gọi `tryComplete`, root bình thường. Với SumTask, leaf trống có result 0, đúng với identity của phép cộng. Dù demo chính dùng tám phần tử để có cây bảy node, cách xử lý range trống quan trọng cho tính đúng tổng quát.

### 17.2. Test trường hợp nhiều phần tử lẻ

Với `hi-lo=7`, phép chia giữa bằng midpoint vẫn tạo hai vùng không giao nhau và phủ toàn bộ `[lo,hi)`. Test nên assert từng phần tử xử lý đúng một lần và reduce ra tổng đúng. Không hardcode “mỗi lần chia tạo đúng bốn leaf” cho mọi n.

### 17.3. Không phải mọi lần treo join đều do pool thiếu thread

Root có thể treo vì một tín hiệu completion không bao giờ đến, pending count bị set sai hoặc một nhánh không gọi `tryComplete` trên success. Tăng số worker có thể che lỗi scheduling nhưng **không giải quyết protocol**. Để debug, vẽ cây, đếm số tín hiệu từng node, ghi log task ID/parent/children/pending biến đổi bằng công cụ quan sát thích hợp.

## 18. Hiệu năng và lựa chọn ngưỡng chia nhỏ

### 18.1. Cân bằng chi phí công việc và overhead

Chia quá nhỏ tạo thêm object, fork/steal và callback. Chia quá lớn hạn chế parallelism, tăng thời gian task dài nhất. Một threshold hợp lý phụ thuộc:

- Số phần tử, chi phí xử lý mỗi phần tử, bộ nhớ/cache locality.
- Độ lệch thời gian giữa các leaf.
- Số core, số worker ForkJoinPool, JDK/hardware.
- Loại workload: CPU-bound hay blocking I/O.
- Chi phí `onCompletion` khi cần ghép kết quả.
- Mức độ giao tiếp giữa nhánh và tính đồng bộ của result.

Ví dụ bản chính chia leaf tối đa hai phần tử **để dễ học**, không phải threshold tối ưu cho production. Với phép cộng các số nguyên, threshold lớn hơn thường tránh tạo nhiều task thừa. Đo trên workload thật bằng JMH khi phù hợp; không đưa số “nhanh gấp X” nếu chưa có số liệu đo.

### 18.2. Fork/Join và blocking operations

ForkJoinPool được thiết kế cho nhiều tác vụ chia nhỏ, thường ưu tiên CPU-bound. Các tác vụ blocking I/O dài có thể giữ worker và giảm throughput; `ForkJoinPool.ManagedBlocker` hỗ trợ một số tình huống blocking có chủ đích, nhưng không thay thế chính sách timeout và tài nguyên.

Trong ứng dụng mới Java 21+, virtual threads là một lựa chọn cho nhiều workload blocking; điều này **không làm CountedCompleter lỗi thời** cho bài toán custom completion tree CPU-bound, cũng không biến các leaf I/O blocking thành nonblocking. Nếu không cần custom tree, API cấp cao như `CompletableFuture` hoặc structured concurrency (theo phiên bản JDK và trạng thái API tương ứng) có thể dễ hiểu hơn; không thêm API đang preview vào ví dụ Java 8.

### 18.3. Đo đúng thứ cần đo

Benchmark nên tách:

- **Overhead tạo/fork task** với lượng công việc mỗi leaf.
- **Throughput tổng** khi tăng số worker.
- **P95/p99 latency** khi task leaf có thời gian phân bố không đều.
- **CPU và GC allocations** khi tạo nhiều node.
- **Tính đúng**: số phần tử xử lý, kết quả tổng, callback once, exception propagation.

Một implementation vô tình bỏ qua child có thể “nhanh hơn” vì làm thiếu việc. **Correctness là điều kiện trước benchmark**, không phải một metric tùy chọn.

## 19. Checklist thiết kế CountedCompleter

- [ ] Bài toán thật sự cần completion tree/trigger phức tạp hay chỉ cần `RecursiveTask`/`CompletableFuture`?
- [ ] Đã xác định root và các liên kết `getCompleter` theo cây rõ ràng?
- [ ] Đã đếm **từng nguồn gọi tryComplete/propagateCompletion** vào mỗi node?
- [ ] Nếu dùng mẫu hai child + parent tự báo, pending có đúng bằng 2 và có đúng ba tín hiệu?
- [ ] Nếu dùng mẫu hai child không có parent tự báo, pending có đúng bằng 1?
- [ ] Pending được thiết lập **trước fork** mọi child có thể kết thúc sớm?
- [ ] Mỗi leaf có xử lý đúng range và báo hoàn tất đúng một lần?
- [ ] Có tránh gọi cùng một completion signal cả trong nhánh chính lẫn finally?
- [ ] Có chọn `tryComplete` khi cần onCompletion và `propagateCompletion` khi không cần hook?
- [ ] Có lưu `left/right` hoặc liên kết child phù hợp nếu parent cần reduce?
- [ ] Đã override `getRawResult` khi result-bearing root cần giá trị T?
- [ ] Có tránh `join` helper nội bộ có completer như RecursiveTask?
- [ ] Có xử lý lỗi `compute`/`onCompletion` qua exceptional completion và làm sạch resource?
- [ ] Nếu short-circuit root, có kiểm soát sibling work còn lại và side effect không?
- [ ] Callback onCompletion có ngắn và tránh blocking không cần thiết không?
- [ ] Có tránh shared mutable state không đồng bộ trong leaf?
- [ ] Có test empty input, one element, odd size, nhiều nhánh và exception?
- [ ] Có dùng `pool.invoke(root)` hoặc `root.join()` làm ranh giới hoàn tất đúng?
- [ ] Có quản lý ForkJoinPool và tránh shutdown commonPool tùy tiện?
- [ ] Có đo threshold, số worker và work-stealing theo workload trước khi tuyên bố cải thiện hiệu năng?

**Kết luận:** `CountedCompleter` cho phép tổ chức việc hoàn tất theo **quan hệ completer và bộ đếm pending**, giúp parent tiếp tục khi những tín hiệu cần thiết đã được nhận mà không bắt phải `join` từng child. `tryComplete()` giảm pending khi nonzero và **chỉ chạy `onCompletion()` khi thấy zero**; `propagateCompletion()` không chạy hook; `onCompletion()` cho phép ghép kết quả; `getRawResult()` cung cấp kết quả của root; `onExceptionalCompletion()` quản lý lan truyền lỗi. Cách dùng đúng bắt đầu bằng **vẽ cây và đếm số tín hiệu completion**, rồi mới tối ưu cách fork/compute và đo hiệu năng.

## Tài liệu chính thức

- [Oracle Java SE 26 — CountedCompleter: hợp đồng pending, tryComplete, propagateCompletion, onCompletion, complete, firstComplete/nextComplete và các ví dụ mẫu](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/CountedCompleter.html)
- [Oracle Java SE 26 — ForkJoinTask: compute/exec, invoke, join, exceptional completion](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ForkJoinTask.html)
- [Oracle Java SE 26 — ForkJoinPool: work-stealing, invoke, execute, shutdown và ManagedBlocker](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ForkJoinPool.html)
- [Oracle Java SE 26 — RecursiveTask: divide-and-conquer với result](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/RecursiveTask.html)
- [Oracle Java SE 26 — CompletableFuture: completion-stage composition](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/CompletableFuture.html)

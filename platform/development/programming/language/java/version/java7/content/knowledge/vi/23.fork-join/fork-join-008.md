# Tránh dữ liệu dùng chung và phụ thuộc tạo chu kỳ trong Java Fork/Join

## 1. Hai nguy cơ lớn của thuật toán chia để trị song song

Khi sử dụng `ForkJoinPool`, `RecursiveTask<V>`, `RecursiveAction` và `ForkJoinTask.fork()/join()`, lập trình viên thường quan tâm đến việc chia nhỏ tác vụ để chạy trên nhiều lõi CPU. Nhưng chương trình chạy song song **đúng** trước rồi mới tính đến tốc độ. Hai nhóm sai lầm quan trọng trong chủ đề này là:

1. **Dữ liệu mutable bị dùng chung không kiểm soát:** nhiều tasks đọc/ghi chung biến, mảng, `ArrayList`, `HashMap` hoặc trạng thái phiên xử lý mà không có quy tắc sở hữu và đồng bộ phù hợp. Hậu quả có thể là *data race*, mất cập nhật, kết quả không quyết định, thấy trạng thái trung gian, hoặc lỗi khi cấu trúc dữ liệu bị sửa đồng thời.
2. **Quan hệ chờ kết quả tạo thành chu kỳ:** task A `join()` B, B `join()` C, rồi C lại cần A hoàn tất. Đây không phải một cây phụ thuộc có thể hoàn thành từ lá tới gốc. Theo **Javadoc Java SE 21 của `ForkJoinTask`, `join` chỉ thích hợp khi dependency graph là DAG (directed acyclic graph)**; phụ thuộc có chu kỳ có thể dẫn đến một dạng deadlock.

Hai lỗi có thể xảy ra độc lập. Một bài toán không có race vẫn có thể deadlock vì chờ vòng tròn; một cây fork/join có thứ tự chờ đúng vẫn có thể cho kết quả sai nếu các lá cùng cập nhật một biến global.

**Đề bài chính:** “Tránh dữ liệu dùng chung và phụ thuộc tạo chu kỳ”, trong nhóm “Fork/Join”.

**Special Note:** Chỉ dùng kiến thức **vẫn còn áp dụng trên các JDK hiện đại**; không đưa hướng dẫn lỗi thời hoặc legacy làm phương pháp khuyến nghị. `ForkJoinTask`, `ForkJoinPool`, `RecursiveTask` và `RecursiveAction` là API tiêu chuẩn có từ Java 7 và vẫn hiện hành trên Java 17/21. Mã thực hành dùng Java 21 để tận dụng `record`, `Map.of` và `List.of`; không nhận là các cú pháp này có sẵn từ Java 7.

Sau bài học, bạn sẽ biết:

- Tại sao `private final int[] numbers` chỉ bảo đảm **tham chiếu field không được gán lại**, chứ không làm các phần tử mảng bất biến.
- Thiết kế một `RecursiveTask` **trả kết quả cục bộ** và chỉ hợp nhất qua `join`, không dùng biến tích lũy `static` dùng chung.
- Thiết kế một `RecursiveAction` ghi **vào các vùng chỉ số không giao nhau** của mảng kết quả, tránh nhiều tasks ghi cùng phần tử.
- Đảm bảo dữ liệu đầu vào là snapshot hoặc không bị sửa đồng thời trong vòng đời computation.
- Hiểu phụ thuộc A→B→C và phát hiện chu kỳ bằng DFS trước khi tạo các task chờ nhau.
- Dùng `fork`, `compute`, `join`, `invokeAll` có hướng và base case đúng; tránh self-join, child-join-parent và lock-order cycle.
- Phân biệt `join` với `get(timeout)`, cancellation, failure propagation; timeout không tự sửa đồ thị phụ thuộc.
- Dùng Fork/Join cho CPU-bound work; không vô tình làm cạn worker pool bằng blocking I/O hoặc đồng bộ khóa vòng.
- Thực hành một Java 21 demo chạy được và **không thực sự tạo deadlock** chỉ để chứng minh lỗi.

## 2. Minh họa data race: hai workers cùng cập nhật một biến

Giả sử mỗi child task phải đếm số phần tử hợp lệ và viết vào biến `static long total`:

~~~java
static long total;

// Nhiều subtasks cùng thực hiện:
total += countOfThisChunk;
~~~

Đây là **phản ví dụ**, không phải mã ứng dụng nên dùng. `total += x` gồm nhiều thao tác logic: đọc total cũ, tính tổng mới, ghi total mới. Hai worker có thể cùng thấy giá trị cũ rồi ghi đè nhau:

~~~text
Ban đầu total = 0

Worker A                      Worker B
đọc total -> 0                đọc total -> 0
tính 0 + 5 = 5                tính 0 + 7 = 7
ghi total = 5                 ghi total = 7

Kết quả cuối: 7 hoặc 5, thay vì 12
~~~

Lịch chạy thực có thể khác sơ đồ; nó chỉ minh họa **mất cập nhật** (*lost update*). Khai báo field `volatile` **không biến phép `+=` thành atomic**. `volatile` có thuộc tính visibility/ordering nhưng không tự làm read-modify-write thành một thao tác nguyên tử.

Dùng `AtomicLong.addAndGet` hoặc `LongAdder.add` có thể sửa phần lost-update trong một số tình huống, nhưng mỗi phần tử đồng thời cập nhật một shared counter vẫn có thể gây contention và khiến thuật toán khó ghép/kiểm thử. Với Fork/Join có phép kết hợp rõ ràng, cách thường tốt hơn là **mỗi task trả subtotal riêng, parent ghép kết quả**.

### 2.1. Dữ liệu dùng chung không nhất thiết luôn nguy hiểm

Hãy phân biệt:

- Nhiều tasks **chỉ đọc** một snapshot không đổi trong suốt computation: thường an toàn nếu object đã được publish/khởi tạo đúng.
- Mỗi task **ghi một vùng riêng** của mảng đầu ra, không overlap, và caller chỉ đọc sau khi root hoàn tất: có thể an toàn.
- Nhiều tasks **cùng ghi một index** hoặc mutation cấu trúc collection không thread-safe: nguy hiểm nếu không có cơ chế đồng bộ rõ.
- Một thread bên ngoài **đang sửa snapshot** trong khi leaves đọc: dữ liệu đầu vào có thể không nhất quán, kể cả task fields là `final`.

Vì vậy “tránh dữ liệu dùng chung” nên hiểu là **tránh chia sẻ trạng thái mutable một cách thiếu kỷ luật**, không phải “cấm mọi task tham chiếu cùng một mảng”.

## 3. Mô hình an toàn thứ nhất: mỗi task trả kết quả riêng

Với bài toán tính tổng:

~~~text
             Sum[0,8) -> Summary(sum=36,count=8)
                    /                    \
           Sum[0,4) -> 10             Sum[4,8) -> 26
             /        \                 /        \
           [0,2)    [2,4)            [4,6)     [6,8)
             3         7                11        15
~~~

Ở mỗi lá, `subtotal` là biến **local** của invocation `compute()`, không nằm trong một shared static field. Parent tạo hai children với intervals không chồng lấp:

~~~java
int middle = from + (to - from) / 2;
SumTask left = new SumTask(snapshot, from, middle);
SumTask right = new SumTask(snapshot, middle, to);

left.fork();
Summary rightResult = right.compute();
Summary leftResult = left.join();
return leftResult.merge(rightResult);
~~~

Đây là **đoạn trích minh họa** của class trong chương trình hoàn chỉnh phần 8. Các ý chính:

1. `left.fork()` sắp lịch child trái, **không chờ** kết quả.
2. Thread hiện tại tính child phải bằng `right.compute()`, cho phép tiến triển hữu ích.
3. Sau đó `left.join()` nhận kết quả trái khi cần.
4. `Summary.merge(...)` ghép hai kết quả theo phép toán có nghĩa.
5. Task gốc trả về một `Summary` mới; không có biến `total` toàn cục phải cập nhật từ nhiều worker.

Đây là một *reduction tree*: thứ tự quan hệ **parent đợi children**, không có child nào đợi parent. Nó tạo ra một **DAG không có chu kỳ** nếu mỗi lần chia bảo đảm đoạn nhỏ hơn và task mới là child riêng.

### 3.1. Kết quả immutable

Trong Java 21, có thể dùng record:

~~~java
record Summary(long sum, long count) {
    Summary merge(Summary other) {
        return new Summary(Math.addExact(sum, other.sum),
                Math.addExact(count, other.count));
    }
}
~~~

Đây là class dùng trong chương trình hoàn chỉnh. Các fields của record này là final và chỉ có hai primitive values, nên `Summary` là **immutable value object**; không lộ một mutable list hoặc array bên trong. Nếu record chứa `List` hoặc `int[]`, record **không tự làm cấu trúc bên trong immutable**: cần defensive copy/immutable container khi hợp đồng yêu cầu.

Kết quả đã join có thể được đọc theo phối hợp hoàn tất task, thay vì thread khác polling một mutable accumulator trong lúc task đang chạy. Khi tính với số rất lớn, chọn `Math.addExact` để phát hiện overflow; nếu cần phạm vi vô hạn, cân nhắc `BigInteger` hoặc định nghĩa chính sách số học riêng.

### 3.2. Dữ liệu đầu vào phải ổn định

Trong ví dụ, `int[] snapshot = input.clone()` tạo bản sao trước khi nộp tasks. Sau khi submit root task, không sửa `snapshot` cho tới khi computation kết thúc. Điều này quan trọng vì:

~~~java
private final int[] snapshot;
~~~

`final` chỉ nói reference `snapshot` của task không được gán lại. Nó **không ngăn** một thread khác thực hiện `snapshot[0] = 999` giữa lúc leaves đọc và cho tổng không quyết định.

Trong ứng dụng thật, chọn một trong các cách: dữ liệu immutable; defensive snapshot trước khi submit; ownership/handoff độc quyền; hay synchronization/snapshot transaction phù hợp. Đừng clone dữ liệu khổng lồ một cách máy móc nếu chi phí bộ nhớ quá cao — khi đó cần thiết kế ownership hoặc immutable representations phù hợp.

## 4. Mô hình an toàn thứ hai: ghi kết quả theo vùng không giao nhau

Không phải lúc nào cũng cần trả một object cho mỗi child. Nếu muốn nhân đôi các phần tử của mảng, có thể dùng `RecursiveAction`. Nhưng mỗi action phải **sở hữu một khoảng output**.

~~~text
Nguồn snapshot (chỉ đọc):
 [1,2,3,4,5,6,7,8]

Đích destination (khởi tạo riêng):
 [0,0,0,0,0,0,0,0]

Action[0,8)
   /                                 \
Action[0,4)                       Action[4,8)
 /       \                          /       \
[0,2)    [2,4)                  [4,6)     [6,8)
  |         |                       |         |
ghi 0,1   ghi 2,3                ghi 4,5   ghi 6,7

Sau khi root Action hoàn tất:
 [2,4,6,8,10,12,14,16]
~~~

Hai actions dùng **cùng tham chiếu tới mảng đích** nhưng không ghi cùng index; không có lost update cho phần tử. Đây là **partitioned ownership**.

Ví dụ phần `compute()`:

~~~java
@Override
protected void compute() {
    if (to - from <= THRESHOLD) {
        for (int i = from; i < to; i++) {
            destination[i] = Math.multiplyExact(source[i], 2);
        }
        return;
    }
    int middle = from + (to - from) / 2;
    invokeAll(new DoubleAction(source, destination, from, middle),
            new DoubleAction(source, destination, middle, to));
}
~~~

Đây là **đoạn trích minh họa** trong class hoàn chỉnh. Parent chia `[from,to)` thành hai đoạn **nửa mở**:

- `[from,middle)` gồm from tới middle-1.
- `[middle,to)` gồm middle tới to-1.
- Hai đoạn không giao nhau và hợp lại đúng interval ban đầu.
- `invokeAll` phối hợp để parent chỉ hoàn tất khi children đã hoàn tất bình thường.
- `source` chỉ đọc, `destination` chỉ ghi các indices riêng.
- Sau khi `pool.invoke(new DoubleAction(...))` trở về bình thường, caller mới dùng output.

### 4.1. Phản ví dụ: overlap phạm vi

~~~java
invokeAll(
    new DoubleAction(source, destination, 0, 6),
    new DoubleAction(source, destination, 4, 8)
);
~~~

Đây là **phản ví dụ**: indices 4 và 5 nằm trong cả hai child tasks. Dù cả hai cùng ghi giá trị “giống nhau” trong một trường hợp, đây vẫn là conflicting writes/race không nên dựa vào. Nếu công thức là `destination[i] += ...`, kết quả có thể sai rõ ràng.

Để tránh lỗi, dùng `mid` duy nhất và ranh giới half-open, validate `0 <= from <= to <= length` ở public entrypoint. Với bài toán chia 2D, đảm bảo mỗi task sở hữu một hình chữ nhật/tile không chồng lấp.

### 4.2. Tách source và destination để hạn chế side effect

Ví dụ dùng `input.clone()` và tạo `new int[snapshot.length]` cho kết quả. Một action thất bại vì overflow có thể đã viết **một phần output**, nhưng **không làm thay đổi input**. Chỉ publish output cho phần khác của hệ thống **sau khi root hoàn tất thành công**. Đây là một cách staging đơn giản, không biến `RecursiveAction` thành một database transaction tự động.

Nếu cần mutate in-place để tiết kiệm bộ nhớ, chỉ thực hiện khi không có reader/writer khác và chấp nhận semantics khi task lỗi; nếu yêu cầu all-or-nothing, phải có chiến lược rollback/staging riêng.

## 5. Phụ thuộc tạo chu kỳ trong Fork/Join là gì?

Một task thường chỉ nên join **những task con đã được nó tạo/sắp lịch**. Nếu task đợi một task vốn lại đợi chính nó trực tiếp hoặc gián tiếp, quan hệ chờ trở thành vòng:

~~~text
A  --join/wait-->  B
B  --join/wait-->  C
C  --join/wait-->  A

Không có task nào có thể hoàn tất để giải phóng vòng chờ.
~~~

Đó là **cyclic dependency**. Theo Javadoc Java SE 21 của `ForkJoinTask`, `join()` và các variants chỉ thích hợp khi completion dependencies **acyclic**, nghĩa là computation biểu diễn được dưới dạng **DAG**. Nếu tạo vòng chờ, chương trình **có thể deadlock**: tasks chờ nhau mãi, không có result dù pool có work-stealing.

Có hai loại thường gặp:

- **Self-dependency:** A đợi chính A hoàn tất; chưa có một computation độc lập nào làm cho A hoàn tất.
- **Mutual/transitive dependency:** A đợi B, B đợi A; hoặc A→B→C→A.

Lưu ý không phải mọi đồ thị task có cạnh hai chiều về *dữ liệu* đều tạo deadlock; điều nguy hiểm là **completion-wait dependency**. Nếu hai tasks chỉ đọc thông tin của nhau ở những thời điểm có sẵn và không chờ vòng, có thể vẫn hợp lệ. Ngược lại, một vòng `join()` thật trên các tasks chưa hoàn tất là sai.

### 5.1. Phản ví dụ ý tưởng — đừng chạy

~~~text
Task A.compute():
    fork B
    wait until B completes (B.join())

Task B.compute():
    wait until A completes (A.join())

A chưa thể hoàn tất vì đang đợi B.
B chưa thể hoàn tất vì đang đợi A.
~~~

Đây là **pseudocode chỉ để phân tích**, cố ý **không** cung cấp một chương trình Java có thể treo máy khi chạy. Bài kiểm thử sẽ **phát hiện** chu kỳ trên graph descriptor trước khi nộp tasks, thay vì khởi chạy deadlock thật.

### 5.2. Vì sao tăng số worker không tự giải quyết?

Work-stealing cho phép một worker rảnh thực hiện các tasks sẵn sàng chạy, nhưng nó không thể làm cho A hoàn tất khi A chỉ được phép hoàn tất sau B và B lại chỉ được phép hoàn tất sau A. Thêm threads không làm dependency graph trở thành acyclic.

`ForkJoinPool` có cơ chế hỗ trợ tiến triển của worker trong một số hình thức join/blocking, nhưng **không có hợp đồng tự phân tích và phá mọi chu kỳ `join` mà ứng dụng tạo ra**. Đừng kỳ vọng pool tự sửa lỗi dependency design.

### 5.3. Đúng: parent đợi child, child không đợi parent

~~~text
             ROOT
            /    \
         LEFT    RIGHT
        /   \    /   \
      L1    L2  R1   R2

ROOT depends on LEFT and RIGHT
LEFT depends on L1 and L2
RIGHT depends on R1 and R2

L1, L2, R1, R2 là base cases: không đợi ROOT.
~~~

Cây là một DAG đặc biệt. Với DAG tổng quát, một child có thể được **chia sẻ logic** giữa hai parents nhưng cần rõ ownership/execution/completion, không fork cùng một `ForkJoinTask` instance nhiều lần khi nó đang pending. Có thể dùng kết quả immutable và graph scheduler được thiết kế riêng thay vì lạm dụng `fork()` trên cùng object.

### 5.4. “Khởi tạo sau rồi join trước” cũng nguy hiểm

Đừng gọi `join()` trên task chưa được fork/submit/invoke và không có thread nào sẽ chạy nó, rồi mong `join` tự đảm bảo mọi task sẽ được xử lý. `join()` là **cơ chế chờ task**, không phải một API đăng ký root computation vào custom pool. Từ outside pool, khởi chạy root với `pool.invoke(root)` hoặc `pool.submit(root)`.

Trong recursion, mẫu phổ biến là:

~~~java
left.fork();
Result rightResult = right.compute();
Result leftResult = left.join();
return combine(leftResult, rightResult);
~~~

Đây là **pseudocode Java** với các kiểu `Result` và `combine` do ứng dụng định nghĩa, không phải đoạn độc lập. Quan hệ chờ rõ ràng là parent đợi left, không tạo cạnh ngược từ left về parent.

## 6. Kiểm tra DAG trước khi lập lịch tasks phụ thuộc lẫn nhau

Nếu dữ liệu nghiệp vụ mô tả một graph các công việc: mỗi node có danh sách task phải hoàn tất trước, hãy **kiểm tra chu kỳ trước** khi tạo những joins tương ứng.

Ví dụ graph hợp lệ:

~~~text
deploy -> build -> generate
       -> test  -> build

Quy ước: X -> Y nghĩa X cần Y hoàn tất trước.
Không có đường quay từ generate trở lại deploy.
~~~

Ví dụ graph không hợp lệ:

~~~text
A -> B
B -> C
C -> A   (chu kỳ A -> B -> C -> A)
~~~

Một thuật toán DFS có thể dùng hai tập:

- `visiting` (*đang nằm trên call stack hiện tại*, màu xám).
- `completed` (*đã được duyệt và không có chu kỳ trong subtree*, màu đen).

Khi DFS đi vào task:
1. Nếu đã `completed`, bỏ qua vì đã kiểm tra.
2. Nếu task không tồn tại trong graph, báo **unknown dependency**, không âm thầm coi là task rỗng.
3. Nếu task đang `visiting` mà bị đi vào lần nữa, ta đã tìm được **back-edge tạo chu kỳ**.
4. Nếu chưa, đánh dấu `visiting`, duyệt từng dependency.
5. Khi kết thúc, gỡ khỏi `visiting` và thêm vào `completed`.

Complexity là **O(V+E)** cho V nodes, E dependency edges nếu sets/maps có thao tác trung bình O(1). DFS đệ quy dùng O(V) stack trong trường hợp chuỗi sâu; với graph khổng lồ hoặc input không tin cậy, cân nhắc **DFS lặp/topological sort (Kahn)** để tránh `StackOverflowError` và giới hạn số nodes/edges.

### 6.1. Validation khác execution

Đồ thị `Map<String,List<String>>` chỉ là **mô tả dependencies**. Hàm `requireAcyclic` trong ví dụ sắp tới **không chạy các ForkJoinTasks của graph**. Nó là một bước *preflight* an toàn. Sau khi graph hợp lệ, bạn vẫn cần thiết kế scheduler đếm dependencies, chỉ phát việc khi prerequisites đã hoàn tất, tránh submit task chưa sẵn sàng mà lại chờ ngược trong pool.

Với tác vụ chia mảng ở đây, task graph thực tế **tự nhiên là cây**; graph validator được đặt cạnh để minh họa rõ điều kiện cấm phụ thuộc vòng trong một bài độc lập.

### 6.2. Không nên dùng timeout như bộ dò chu kỳ

`task.get(5, TimeUnit.SECONDS)` ném `TimeoutException` nếu chưa xong trong thời hạn, **nhưng một task tính toán hợp lệ cũng có thể mất hơn 5 giây**. Timeout không chứng minh có chu kỳ; đồng thời nó **không tự hủy/bẻ vòng** các dependencies.

Ngược lại, phát hiện một chu kỳ bằng graph DFS trước scheduling là kiểm chứng cấu trúc rõ ràng, không phải dựa trên tốc độ máy hoặc thread timing. Với hệ thống động, cần đảm bảo graph không bị sửa đồng thời giữa lúc validate và lúc schedule, hoặc có validation/locking ở mỗi lần thêm dependency.

## 7. Mẫu thiết kế cùng giải quyết hai nguy cơ

Kết hợp hai nhóm nguyên tắc:

| Vấn đề | Thay thế an toàn hơn | Vì sao |
| --- | --- | --- |
| Mỗi leaf cập nhật `static long total` | `RecursiveTask<Summary>` trả subtotal riêng | Không có shared accumulator |
| Các leaves cùng `ArrayList.add` | Trả lists riêng rồi merge, hoặc collection concurrent theo contract | Tránh mutation cấu trúc không an toàn |
| Mọi action ghi chung buffer tùy ý | `[from,to)` chia thành vùng độc quyền | Không có conflicting writes |
| Input bị thread khác sửa khi workers đọc | Immutable snapshot/handoff rõ | Không đọc trạng thái biến động |
| Task A `join()` B và B `join()` A | DAG: parent→children, children không join ancestor | Không có cycle |
| Root task `join()` task chưa submit | `pool.invoke(root)` / `pool.submit(root)` | Có task được lập lịch thực |
| Một task có reference tới parent mutable state | Truyền input/immutable context và return value | Dependency rõ và giảm races |
| Dùng `synchronized` lồng nhau trong compute | Thực hiện tính cục bộ/merge, tránh nhiều locks | Giảm deadlocks và contention |
| Tasks làm network I/O blocking lâu | Executor riêng/virtual threads theo workload | Không giữ hết ForkJoin workers |
| Shared `ForkJoinTask` instance bị fork hai lần | Mỗi logical subtask có instance riêng, kết quả shared immutable | Không dùng lại task pending sai contract |
| Ngưỡng chia bằng 0 không có base case | Base case dừng ở đoạn đủ nhỏ | Không tạo recursion vô hạn |
| Không xử lý exceptions của children | `join/invoke/get` và policy error | Không để lỗi bị che |

Các hướng trên **không thay thế** việc test concurrency; chúng tạo những bất biến (*invariants*) dễ kiểm chứng hơn.

## 8. Chương trình Java 21 hoàn chỉnh và kết quả thực tế

Chương trình `SafeForkJoinExample` chứng minh hai vế:

**Vế 1: không chia sẻ mutable state không kiểm soát.** `SumTask extends RecursiveTask<Summary>` chỉ đọc snapshot và trả kết quả; `DoubleAction extends RecursiveAction` ghi các đoạn riêng vào một mảng destination độc lập. Không có biến `static` cộng tổng và không có hai leaves ghi cùng index. Caller chỉ đọc output sau `pool.invoke(action)` trở về bình thường.

**Vế 2: không tạo cyclic joins.** `requireAcyclic` duyệt một DAG hợp lệ và một graph có chu kỳ. Nó báo lỗi **trước khi lập lịch các tác vụ mô tả bởi graph**, nên bài thử không làm chương trình tự treo bằng một vòng join thật.

**Kế hoạch của chương trình:**

1. Tạo mảng số 1..8; clone làm snapshot ổn định.
2. Dùng `ForkJoinPool(4)` chạy root `SumTask`; nhận `Summary(sum=36,count=8)`.
3. Tạo mảng đích riêng, chạy `DoubleAction` để có giá trị gấp đôi.
4. Xác nhận input gốc không bị sửa.
5. Test mảng rỗng cho cả result-bearing task và action.
6. Validate DAG `deploy→build/test`, `test→build`, `build→generate`.
7. Validate graph A→B→C→A, bắt `IllegalArgumentException`, in `cycle-rejected=true`.
8. `shutdown()` pool do chương trình sở hữu và `awaitTermination` có giới hạn.
9. Không in tên threads hay thứ tự leaves vì scheduling work-stealing không được API bảo đảm.

Tạo file `src/main/java/demo/SafeForkJoinExample.java`:

~~~java
package demo;

import java.util.Arrays;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveAction;
import java.util.concurrent.RecursiveTask;
import java.util.concurrent.TimeUnit;

public final class SafeForkJoinExample {
    private static final int THRESHOLD = 2;

    private SafeForkJoinExample() {}

    record Summary(long sum, long count) {
        Summary merge(Summary other) {
            return new Summary(Math.addExact(sum, other.sum),
                    Math.addExact(count, other.count));
        }
    }

    private static final class SumTask extends RecursiveTask<Summary> {
        private static final long serialVersionUID = 1L;
        private final int[] snapshot;
        private final int from;
        private final int to;

        SumTask(int[] snapshot, int from, int to) {
            this.snapshot = snapshot;
            this.from = from;
            this.to = to;
        }

        @Override
        protected Summary compute() {
            if (to - from <= THRESHOLD) {
                long subtotal = 0;
                for (int i = from; i < to; i++) {
                    subtotal = Math.addExact(subtotal, snapshot[i]);
                }
                return new Summary(subtotal, to - from);
            }

            int middle = from + (to - from) / 2;
            SumTask left = new SumTask(snapshot, from, middle);
            SumTask right = new SumTask(snapshot, middle, to);
            left.fork();
            Summary rightSummary = right.compute();
            Summary leftSummary = left.join();
            return leftSummary.merge(rightSummary);
        }
    }

    private static final class DoubleAction extends RecursiveAction {
        private static final long serialVersionUID = 1L;
        private final int[] source;
        private final int[] destination;
        private final int from;
        private final int to;

        DoubleAction(int[] source, int[] destination, int from, int to) {
            this.source = source;
            this.destination = destination;
            this.from = from;
            this.to = to;
        }

        @Override
        protected void compute() {
            if (to - from <= THRESHOLD) {
                for (int i = from; i < to; i++) {
                    destination[i] = Math.multiplyExact(source[i], 2);
                }
                return;
            }

            int middle = from + (to - from) / 2;
            invokeAll(new DoubleAction(source, destination, from, middle),
                    new DoubleAction(source, destination, middle, to));
        }
    }

    static void requireAcyclic(Map<String, List<String>> graph) {
        Set<String> visiting = new HashSet<>();
        Set<String> completed = new HashSet<>();
        for (String task : graph.keySet()) {
            visit(task, graph, visiting, completed);
        }
    }

    private static void visit(String task,
                              Map<String, List<String>> graph,
                              Set<String> visiting,
                              Set<String> completed) {
        if (completed.contains(task)) {
            return;
        }
        if (!graph.containsKey(task)) {
            throw new IllegalArgumentException("Unknown dependency: " + task);
        }
        if (!visiting.add(task)) {
            throw new IllegalArgumentException("Cyclic dependency: " + task);
        }
        for (String dependency : graph.get(task)) {
            visit(dependency, graph, visiting, completed);
        }
        visiting.remove(task);
        completed.add(task);
    }

    public static void main(String[] args) throws InterruptedException {
        int[] input = {1, 2, 3, 4, 5, 6, 7, 8};
        int[] snapshot = input.clone();
        int[] destination = new int[snapshot.length];
        ForkJoinPool pool = new ForkJoinPool(4);
        try {
            Summary summary = pool.invoke(new SumTask(snapshot, 0, snapshot.length));
            System.out.println("snapshot=" + Arrays.toString(snapshot));
            System.out.println("summary=sum=" + summary.sum()
                    + ",count=" + summary.count());

            pool.invoke(new DoubleAction(snapshot, destination, 0, snapshot.length));
            System.out.println("transformed=" + Arrays.toString(destination));
            System.out.println("original-unchanged=" + Arrays.equals(input, snapshot));

            int[] empty = {};
            Summary emptySummary = pool.invoke(new SumTask(empty, 0, empty.length));
            System.out.println("empty-summary=sum=" + emptySummary.sum()
                    + ",count=" + emptySummary.count());
            pool.invoke(new DoubleAction(empty, new int[0], 0, empty.length));
            System.out.println("empty-output=[]");

            Map<String, List<String>> dag = Map.of(
                    "deploy", List.of("build", "test"),
                    "build", List.of("generate"),
                    "test", List.of("build"),
                    "generate", List.of());
            requireAcyclic(dag);
            System.out.println("dag-valid=true");

            Map<String, List<String>> cyclic = Map.of(
                    "A", List.of("B"),
                    "B", List.of("C"),
                    "C", List.of("A"));
            boolean cycleRejected = false;
            try {
                requireAcyclic(cyclic);
            } catch (IllegalArgumentException expected) {
                cycleRejected = true;
            }
            System.out.println("cycle-rejected=" + cycleRejected);
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("ForkJoinPool did not terminate");
            }
        }
        System.out.println("pool-terminated=" + pool.isTerminated());
    }
}
~~~

Biên dịch và chạy bằng **JDK 21** từ thư mục chứa `src`:

~~~sh
javac --release 21 -encoding UTF-8 -Xlint:all -d out src/main/java/demo/SafeForkJoinExample.java
java -cp out demo.SafeForkJoinExample
~~~

**Stdout chính xác đã kiểm thử với Java 21:**

~~~text
snapshot=[1, 2, 3, 4, 5, 6, 7, 8]
summary=sum=36,count=8
transformed=[2, 4, 6, 8, 10, 12, 14, 16]
original-unchanged=true
empty-summary=sum=0,count=0
empty-output=[]
dag-valid=true
cycle-rejected=true
pool-terminated=true
~~~

### 8.1. Từng dòng output có nghĩa gì?

| Output | Ý nghĩa |
| --- | --- |
| `snapshot=[1,...,8]` | Snapshot không bị các children thay đổi |
| `summary=sum=36,count=8` | Tổng và số lượng được ghép qua `Summary.merge`, không có shared mutable counter |
| `transformed=[2,4,...,16]` | `DoubleAction` đã ghi vào destination của từng khoảng không overlap |
| `original-unchanged=true` | Phần tử của mảng input vẫn giữ nguyên sau computation |
| `empty-summary=sum=0,count=0` | Đoạn trống đi qua base case đúng và trả phần tử đơn vị |
| `empty-output=[]` | Action với mảng rỗng không sinh tác vụ đệ quy vô hạn |
| `dag-valid=true` | DFS không tìm thấy cycle trong graph nhiệm vụ hợp lệ |
| `cycle-rejected=true` | DFS tìm back-edge của A→B→C→A và từ chối trước khi schedule |
| `pool-terminated=true` | Custom pool đã shutdown và kết thúc trong giới hạn test |

Đầu ra không phụ thuộc thứ tự worker chạy, vì không có shared counter và graph validator chạy tuần tự trước khi scheduling graph. Không có sleep và không tạo một ví dụ cyclic joins thực sự để rồi treo chương trình.

### 8.2. Vì sao `Summary` an toàn hơn global accumulator?

- Mỗi leaf tạo ra một đối tượng `Summary` mới.
- Mỗi parent ghép **kết quả riêng của hai children**.
- Không có field `static long total` mà nhiều worker cùng cập nhật.
- `join()` đồng bộ completion của child trước khi parent dùng kết quả đó.
- Mọi dữ liệu đọc là snapshot không bị sửa trong suốt computation.
- Tính đúng không dựa vào ai chạy trước hay số lần work-steal.

### 8.3. Vì sao `DoubleAction` vẫn dùng chung một mảng?

Hai child tasks tham chiếu cùng `destination` nhưng **quyền ghi được phân vùng theo chỉ số**. Nếu đảm bảo mọi node chia đúng `[from,middle)` và `[middle,to)`, không có hai leaves ghi cùng phần tử. Sau `pool.invoke(root)` hoàn tất bình thường, caller mới tiêu thụ mảng.

Lưu ý: một action có thể thất bại sau khi đã ghi một phần, vì vậy **chỉ publish destination sau root thành công**. Java Fork/Join không tự rollback arrays.

### 8.4. Vì sao `requireAcyclic` không sử dụng ForkJoinPool?

Validation graph phải diễn ra **trước khi chạy những tác vụ có khả năng chờ vòng**, nên chạy DFS đơn giản trên graph descriptor. Nó không phải là một scheduler DAG tổng quát. Nếu input là graph rất lớn, DFS đệ quy có nguy cơ `StackOverflowError`; ứng dụng thực có thể dùng topo sort lặp, giới hạn graph, và chặn mutations đồng thời trong giai đoạn validation.

### 8.5. `serialVersionUID` có liên quan đến chủ đề không?

`ForkJoinTask` implements `Serializable` nên `javac -Xlint:all` có thể cảnh báo subclass thiếu `serialVersionUID`. Hai subclasses của demo khai báo `private static final long serialVersionUID = 1L;` để biên dịch sạch. Điều này **không biến task thành một đối tượng nên serialize khi đang chạy**, càng không làm Fork/Join thành distributed scheduler.

### 8.6. Vì sao `THRESHOLD=2`?

Ngưỡng 2 chỉ để dễ quan sát cây chia nhỏ với 8 phần tử. Trong ứng dụng thật, task quá nhỏ gây overhead của allocation/scheduling; task quá lớn khiến không khai thác được parallelism. Chọn threshold qua benchmark với workload thực và số cores/GC/CPU cache. Không có threshold tối ưu chung.

## 9. Ngoài data race: tránh deadlock do synchronized và blocking

Ngay cả khi task dependency graph là DAG, chương trình vẫn có thể deadlock do **khóa hoặc điều kiện chờ bên ngoài**.

### 9.1. Đảo thứ tự lấy lock

~~~java
// Task A giữ lockX rồi chờ lockY.
// Task B giữ lockY rồi chờ lockX.
~~~

Đây là **pseudocode cảnh báo**, không phải mã runnable. Nếu hai threads giữ lock đầu tiên rồi cần lock của nhau, chúng có thể deadlock dù cấu trúc `fork/join` của các tasks không có cycle tường minh.

Thay thế: tránh shared mutable state nên giảm nhu cầu synchronized; nếu bắt buộc nhiều locks, áp dụng **một thứ tự lock thống nhất** trong toàn bộ code, giữ critical sections ngắn, không gọi `join()` khi đang giữ lock có thể được child cần.

### 9.2. Chờ child khi giữ lock mà child cần

~~~text
Parent holds lock L
  Parent forks child
  Parent joins child while still holding L
Child tries to acquire L to finish
=> Có thể không tiến triển.
~~~

Đây là một ví dụ **phụ thuộc chéo giữa completion và lock ownership**. Không có lý do tốt để giữ một global lock qua `join()` của một child mà chính child có thể cần lock đó. Hãy tạo dữ liệu cục bộ ngoài lock, release lock, rồi fork/join, hoặc viết lại thuật toán trả result thay vì thao tác shared state.

### 9.3. Blocking I/O trong ForkJoinPool

Javadoc Java 21 khuyên ForkJoinTasks nên hạn chế synchronized và các blocking operations ngoài cơ chế phối hợp Fork/Join. Nếu tất cả workers bị giữ bởi file/network/database I/O, các subtasks khác có thể bị trì hoãn, thậm chí gặp tình trạng thiếu tiến triển nếu có dependency chéo.

`ForkJoinPool.managedBlock(ForkJoinPool.ManagedBlocker)` có thể thông báo một số trường hợp blocking để pool cân nhắc bù workers. Nhưng nó không biến cyclic task joins thành hợp lệ và không phải giải pháp chung cho mọi tác vụ I/O. Nếu workload chủ yếu chờ mạng/DB, cân nhắc executor phù hợp; trên Java 21 có virtual threads hữu ích cho nhiều blocking tasks, nhưng chúng không thay thế Fork/Join cho phép chia CPU-bound thuần.

### 9.4. Dùng một `CompletableFuture` cho hai phía chờ vòng cũng không an toàn

Mẫu bất kỳ trong đó completion của promise A phụ thuộc B còn completion của B lại phụ thuộc A cũng không có điểm bắt đầu thực sự. Đổi từ `ForkJoinTask.join()` sang `CompletableFuture.join()` **không tự cắt vòng phụ thuộc**. Thiết kế hướng dependency phải là acyclic hoặc dùng một mô hình tương tác/phối hợp khác có các state transitions tiến triển.

## 10. Những vấn đề thường bị nhầm với chu kỳ

| Triệu chứng | Có chắc là cycle? | Cách phân biệt |
| --- | --- | --- |
| Job chạy chậm lâu | Không | Có thể task quá lớn, GC, CPU contention |
| `get(timeout)` quá hạn | Không | Timeout không chứng minh cyclic dependency |
| Một task `join()` child quá lâu | Không | Child có thể blocking hoặc bị thiếu workers |
| A đợi B, B đợi A | Có chu kỳ completion nếu cả hai chưa hoàn tất | Vẽ task wait-for graph |
| Một task đợi chính task đó | Self-cycle nếu chưa hoàn tất | Tránh self-join/self-wait |
| Hai tasks cùng dùng shared lock | Chưa chắc | Phụ thuộc thứ tự lấy/giữ locks |
| Một task cùng xuất hiện trong hai branches | Chưa chắc, nhưng cần ownership rõ | Đừng fork lại cùng pending task instance |
| Recursion không có base case | Có thể không phải dependency cycle; vẫn vô hạn | Đảm bảo input range nhỏ dần |
| Workers bị block do I/O | Không nhất thiết | Đo trạng thái threads và blocking tasks |
| Kết quả thay đổi giữa các lần chạy | Thường gợi ý race/undefined ownership | Kiểm tra mutable state, input mutation, ordering |

**Cần chẩn đoán theo cấu trúc chờ thực**, không dùng thêm threads hoặc tăng timeout làm “cách sửa” chung.

## 11. Contract của ForkJoinTask và cách xử lý lỗi

### 11.1. `fork()` và `join()`

`fork()` sắp lịch task, không đợi kết quả. `join()` đợi completion rồi lấy result. Trong một thuật toán dạng cây, parent nên fork child trái, tính child phải, join trái, rồi combine.

Nếu child ném unchecked exception trong `compute()`, `join()`/`invoke()` của parent có thể truyền lỗi đó lên. **Không coi exception là một kết quả cục bộ hợp lệ** rồi tiếp tục hợp nhất như không có gì xảy ra.

### 11.2. `get(timeout)` và cancellation

`ForkJoinTask` implements `Future`. `get(timeout, unit)` có thể ném `TimeoutException`, `InterruptedException`, `ExecutionException` hoặc `CancellationException` theo outcome tương ứng. Timeout trên caller **không tự làm các children ngừng chạy**, và cancellation không có nghĩa mọi side effects đã rollback. Nếu có lỗi, cần quyết định có chấp nhận output một phần hay discard toàn bộ.

### 11.3. Không fork lại một pending task

Javadoc nói dùng lại một task đã `fork()` mà chưa completed/reinitialized là **usage error**, dù không phải lúc nào cũng được framework phát hiện ngay. Mỗi logical subtask nên có một instance mới, hoặc thiết kế DAG scheduler sử dụng promise/result chung một cách có chủ ý, không gọi `fork()` hai lần trên cùng `ForkJoinTask`.

### 11.4. `isDone()` chưa đủ để biết thành công

`isDone()` có thể true khi task thành công, fail hoặc cancel. Dùng `join()`/`get()` hoặc `isCompletedNormally()`/`isCompletedAbnormally()` và các nguyên nhân tương ứng. Đừng công bố mảng output chỉ vì một cờ done không phân biệt error path.

### 11.5. Debugging cyclic dependencies

Một cách tìm vấn đề:

1. Liệt kê từng task ID và những tasks mà nó **phải đợi để hoàn tất**.
2. Vẽ directed edges `A -> B` nghĩa A chờ B.
3. Tìm DFS back-edge hoặc chạy topological sort để phát hiện chu kỳ.
4. Kiểm tra cả non-ForkJoin waits: locks, semaphores, external queues và callbacks.
5. Nếu graph động, log ID/task parent/dependency khi thêm cạnh, kiểm tra cycle trước khi commit edge.
6. Thêm bounded metrics/diagnostic timeout để quan sát, **không** coi timeout là vòng đã được sửa.
7. Nếu gặp cycle, sửa thiết kế phụ thuộc (phá vòng bằng state machine/event/message, hoặc dời bước trao đổi dữ liệu ra khỏi completion dependency).

Trong công việc production, có thể dùng thread dump/JFR/JDK tooling để xem threads đang block ở đâu, nhưng kết luận vẫn phải dựa trên quan hệ chờ thật.

## 12. Khi cần graph phức tạp hơn một cây

Fork/Join rất tự nhiên khi có cây recursion:

~~~text
parent computes:
   child1 = new Task(leftRange)
   child2 = new Task(rightRange)
   child1.fork()
   rightResult = child2.compute()
   leftResult = child1.join()
   return combine(leftResult, rightResult)
~~~

Nếu công việc có các dependency **giao nhau** (một node cần nhiều prerequisites và nhiều nodes khác phụ thuộc cùng một kết quả), hãy thiết kế DAG scheduler:

- Validation DAG trước execution, hoặc validation khi thêm cạnh.
- Mỗi node chỉ được thực thi khi **tất cả prerequisites** đã hoàn tất.
- Mỗi logical node có result/status và ownership rõ.
- Chỉ tạo một execution cho một logical task; các consumers chia sẻ **kết quả immutable** sau completion.
- Thêm backpressure và bounded concurrency.
- Khi một node lỗi, cập nhật dependents theo failure policy (fail-fast, skip, retry có kiểm soát).
- Không bắt các worker đứng chờ vô hạn ở mỗi node thay vì scheduling những nodes đã sẵn sàng.

`CompletableFuture` có thể biểu diễn một số DAG completion workflows; `CountedCompleter` là API Fork/Join được thiết kế cho những trường hợp completed actions kích hoạt hành động khác và có thể tránh một số patterns join trực tiếp. Nhưng đó **không phải** giấy phép để tạo cycle vô hạn: vẫn phải chứng minh progression và điều kiện dừng, tránh coi advanced API là cách sửa tự động cho graph sai.

### 12.1. Kahn topological sort là lựa chọn khác DFS

Một graph với cạnh `task -> prerequisite` có thể được xử lý bằng việc đếm dependencies và chọn những task có **zero prerequisites** trước. Kahn algorithm:

1. Xác định số prerequisites chưa thỏa của mỗi task.
2. Đưa các task có zero prerequisites vào queue.
3. Khi task hoàn tất, giảm số prerequisites của các dependents.
4. Các dependents chuyển về zero được cho phép chạy.
5. Nếu còn nodes nhưng không có node sẵn sàng, graph có cycle hoặc tình huống thiếu dependency.

Đây là mô hình hữu ích cho một DAG scheduler production. Cần index reverse edges (prerequisite -> dependents), không dùng raw Map input mà không kiểm tra node tồn tại, duplicates và concurrency. Đây là lựa chọn thiết kế, **không phải thuật toán chạy của `ForkJoinPool` tự động**.

## 13. Hiệu năng: correctness rồi mới song song hóa

Tránh shared mutable state thường còn giúp giảm **contention**. Nhưng việc tạo hàng triệu result objects cũng có chi phí. Cần cân bằng:

- **Chunk/threshold:** với tác vụ đơn giản trên mỗi phần tử, dùng chunk đủ lớn để giảm overhead.
- **Merge cost:** `Summary.merge` nhỏ và rẻ; nếu trả các `Map` hàng triệu entries, chi phí merge có thể áp đảo.
- **Memory:** clone snapshot và tạo destination tăng memory; cân nhắc đổi với trách nhiệm ownership.
- **Cache:** phân chia đoạn liên tục cải thiện locality, hạn chế false sharing của writes gần nhau trong một số workload.
- **Parallelism:** `new ForkJoinPool(4)` là mục tiêu song song, không hứa đúng bốn threads luôn bận.
- **Task lifetime:** tránh fork/join từ quá nhiều nested small tasks nếu vòng lặp tuần tự rẻ hơn.
- **Measurement:** benchmark cùng input, có warm-up JIT, không in log trong hot loop, so với sequential baseline và sử dụng công cụ như JMH nếu cần.
- **Scalability:** nếu mọi leaf đều cần cùng một global lock, thêm nhiều workers có thể không tăng throughput.

### 13.1. Ngưỡng chia task và base case

Trong ví dụ `THRESHOLD=2` để test tám phần tử. Một algorithm production phải đảm bảo `to-from` giảm sau mỗi recursion và base case xử lý tất cả đoạn nhỏ, kể cả đoạn trống. Nếu không có base case, recursion có thể lặp vô hạn/`StackOverflowError` dù task graph vẫn có vẻ dạng cây. Đây là **lỗi termination riêng**, không nhất thiết là cyclic `join`.

### 13.2. Dữ liệu rất lớn và overflow

Ví dụ dùng `Math.addExact` và `Math.multiplyExact` để phát hiện integer overflow rõ ràng thay vì wrap âm thầm. Nếu một leaf báo `ArithmeticException`, có thể một số other leaves đã xử lý. Với output staging, không publish mảng khi root fail. Nếu cần tính tổng vượt `long`, thiết kế `BigInteger` hoặc kết quả số học phù hợp.

### 13.3. Khi chia dữ liệu không đều

Nếu mỗi phần tử có chi phí tính khác nhau, chia interval theo số lượng có thể gây load imbalance. Cân nhắc work estimates/partitioning động; tuy nhiên luôn giữ **ownership của output** và **acyclic dependency**. Không đổi bằng cách cho mọi task cập nhật một object mutable global.

## 14. Bảng kiểm lỗi và cách sửa

| Sai lầm | Điều có thể xảy ra | Cách đúng |
| --- | --- | --- |
| `static long sum` cập nhật từ mọi task | Lost updates | Return subtotal qua `RecursiveTask` |
| Thêm `volatile` vào `sum` rồi tin `+=` atomic | Lost updates vẫn tồn tại | Per-task reduction hoặc atomic theo nhu cầu |
| Nhiều tasks gọi `ArrayList.add` lên cùng list | Race/structure corruption | Return local lists rồi merge |
| Nhiều tasks ghi cùng index mảng | Conflicting writes | Partition disjoint intervals |
| Tasks đọc array đang bị sửa bên ngoài | Không nhất quán | Snapshot hoặc handoff/lock |
| `final int[]` được cho là immutable | Người khác vẫn sửa phần tử | Defensive copy và ownership |
| Child join parent | Wait-cycle | Parent→children only |
| Task A join B, B join A | Có thể deadlock | Validate DAG và thay dependency |
| Một task join chính nó | Self-wait | Không self-join |
| Join task chưa từng submit/fork | Có thể chờ không tiến triển | Khởi chạy root qua pool |
| Fork lại cùng task pending | Vi phạm usage contract | Task instance mới/result shared |
| Giữ lock khi join child cần lock đó | Lock/wait deadlock | Thả lock trước join |
| Mọi worker bị block I/O | Starvation/throughput thấp | Executor phù hợp hoặc managed blocking |
| Catch exception của child rồi publish output partial | Dữ liệu không đầy đủ | Fail closed, staging, error policy |
| Dùng `get(timeout)` để “phá” cycle | Cycle vẫn còn | Sửa graph |
| Task quá nhỏ | Scheduling overhead | Tune threshold bằng benchmark |
| Không có base case | Recursion vô hạn | Đảm bảo kích thước giảm |
| `isDone()` được coi là success | Có thể task fail/cancel | Kiểm tra completion normal |
| Dừng common pool | Ảnh hưởng toàn JVM hoặc không hiệu lực như mong | Custom pool đúng ownership |
| Pool riêng không shutdown | Threads và resources còn sống | shutdown + awaitTermination |

## 15. Câu hỏi tự kiểm tra và đáp án

**Câu 1.** Nhiều `RecursiveTask` cùng cập nhật một `static long total` có thể sai ra sao?  
**Đáp án:** Các phép `+=` không atomic, có thể mất cập nhật. Tránh shared accumulator, cho mỗi task trả subtotal và merge qua `join`.

**Câu 2.** Thêm `volatile` cho `total` có đủ chưa?  
**Đáp án:** Chưa. Visibility không biến phép read-modify-write thành atomic.

**Câu 3.** Hai tasks chỉ đọc một mảng dùng chung có bắt buộc bị race không?  
**Đáp án:** Không nếu mảng đã được publish đúng và không có thread nào sửa nó trong khi tasks đọc.

**Câu 4.** `final int[] snapshot` bảo đảm các phần tử bất biến không?  
**Đáp án:** Không. `final` chỉ ngăn field tham chiếu bị gán lại; phần tử mảng vẫn mutable.

**Câu 5.** Vì sao dùng record `Summary` hữu ích?  
**Đáp án:** Mỗi task trả immutable value, không cần ghi global state; parent merge các kết quả đã hoàn tất.

**Câu 6.** Vì sao `DoubleAction` ghi cùng một mảng destination mà vẫn có thể an toàn?  
**Đáp án:** Mỗi leaf chỉ ghi một đoạn index **không chồng lấp**, caller chỉ đọc sau root hoàn tất thành công.

**Câu 7.** Nếu hai actions cùng ghi index 5 thì sao?  
**Đáp án:** Có conflicting writes và có thể mất cập nhật, race hoặc thứ tự tác động khó kiểm soát.

**Câu 8.** Tại sao cần base case?  
**Đáp án:** Ngăn recursion vô hạn và giảm overhead khi xử lý đoạn đủ nhỏ.

**Câu 9.** `A.join(B)`, `B.join(C)`, `C.join(A)` có vấn đề gì?  
**Đáp án:** Completion dependencies có chu kỳ, theo `ForkJoinTask` Javadoc có thể deadlock. Đây là ký hiệu wait-for, không phải chữ ký Java thật.

**Câu 10.** Dùng `new ForkJoinPool(32)` có tự chữa cycle không?  
**Đáp án:** Không. Vấn đề là quan hệ dependency không có điểm giải phóng, không phải thiếu workers đơn thuần.

**Câu 11.** Đồ thị DAG có thể có node dùng chung giữa hai parents không?  
**Đáp án:** Có ở mức graph, nhưng scheduler phải bảo đảm một logical node được thực thi một lần hoặc có semantics rõ, không fork lại cùng pending task instance.

**Câu 12.** Một task `join()` task chưa khởi chạy có sao?  
**Đáp án:** Có thể chờ không tiến triển. `join` chờ, không phải cách submit task root cho custom pool.

**Câu 13.** `get(timeout)` timeout có nghĩa đồ thị chắc chắn có cycle không?  
**Đáp án:** Không. Task hợp lệ có thể chậm; timeout không chứng minh hoặc phá cycle.

**Câu 14.** DFS phát hiện cycle dựa vào dấu hiệu gì?  
**Đáp án:** Trong lúc DFS từ một node, gặp lại node **đang nằm trong visiting/current recursion stack** → back-edge/cycle.

**Câu 15.** Nếu graph tham chiếu một dependency không tồn tại, có nên bỏ qua?  
**Đáp án:** Không. Bài demo ném `IllegalArgumentException`; production cần policy validation minh bạch.

**Câu 16.** Vì sao bài test không chạy một cặp tasks tự join nhau thật?  
**Đáp án:** Vì nó có nguy cơ deadlock, treo worker/pool. Kiểm tra graph trước scheduling an toàn và cho kết quả quyết định hơn.

**Câu 17.** `ForkJoinTask.join()` có tự động rollback side effects nếu child lỗi không?  
**Đáp án:** Không. Nếu action ghi một phần output rồi fail, phải discard/stage/compensate theo application policy.

**Câu 18.** Vì sao không nên giữ `synchronized(lock)` bao quanh `child.join()` nếu child cần lock?  
**Đáp án:** Parent giữ lock rồi chờ child, child cần lock mới xong → có thể deadlock.

**Câu 19.** Blocking I/O trong `compute()` có lợi cho work-stealing không?  
**Đáp án:** Thường không; giữ worker pool có thể gây thiếu tiến triển. Dùng executor thích hợp hoặc managed blocking khi thật sự cần.

**Câu 20.** Vì sao demo in `pool-terminated=true` sau `awaitTermination`?  
**Đáp án:** Pool do demo sở hữu được shutdown và đã hoàn tất tasks; không mặc nhiên coi `shutdown()` đã tương đương termination.

**Câu 21.** `ForkJoinTask.isDone() == true` có nghĩa task đã thành công?  
**Đáp án:** Không. Nó cũng true khi task cancel/fail; dùng `join/get` hoặc `isCompletedNormally()`.

**Câu 22.** Có bắt buộc dùng `RecursiveTask` nếu muốn tránh shared mutable state không?  
**Đáp án:** Không. `RecursiveAction` với disjoint ownership và output staging cũng có thể an toàn. Lựa chọn dựa vào hợp đồng kết quả/hành động.

## 16. Checklist code review

- [ ] Task graph có hướng từ parent tới các prerequisites/children và **không có chu kỳ completion**.
- [ ] Không self-join, child-join-parent hoặc mutual joins chưa có điều kiện hoàn tất.
- [ ] Nếu graph động/từ người dùng, validate DAG hoặc bảo vệ cạnh được thêm trước scheduling.
- [ ] Không bỏ qua unknown dependencies; không lập lịch nodes chưa sẵn sàng.
- [ ] Mỗi subtask pending là một instance/scheduling contract hợp lệ.
- [ ] Dữ liệu đầu vào không bị mutate concurrent; có snapshot/immutable ownership.
- [ ] Không dùng global mutable counter/list/map nếu result local + merge đáp ứng bài toán.
- [ ] Nếu có `volatile`, không nhầm với atomic compound update.
- [ ] Các actions ghi output theo intervals không giao nhau.
- [ ] Caller chỉ đọc/publish output sau root hoàn tất bình thường.
- [ ] Không giữ locks có thể được child cần khi `join()`.
- [ ] Không dùng unbounded blocking I/O/`sleep` làm logic đồng bộ giữa fork/join workers.
- [ ] Có base case, threshold, khoảng `[from,to)` và midpoint chính xác.
- [ ] Kết quả empty input và overflow được định nghĩa.
- [ ] Có chính sách failure/cancellation/timeout; không giả định side effects tự rollback.
- [ ] `join`/`get`/`invoke` đều được dùng đúng ngữ cảnh và xử lý error.
- [ ] Không coi timeout là bằng chứng cycle; dùng graph analysis.
- [ ] Không chọn parallelism/threshold dựa trên lời hứa speedup cố định.
- [ ] Với graph lớn/không tin cậy, giới hạn nodes/edges và tránh DFS recursive stack overflow.
- [ ] Không tự shutdown `ForkJoinPool.commonPool()` trong thư viện.
- [ ] Pool riêng được shutdown/awaitTermination, không báo completed khi timeout.
- [ ] Test empty/single/odd-size/race/overlap/cycle/error cùng sequential baseline.
- [ ] Sử dụng API Java Fork/Join còn được hỗ trợ trên JDK hiện đại.

## 17. Tài liệu chính thức Java SE 21

- [ForkJoinTask](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ForkJoinTask.html): hạn chế shared mutable state, blocking, `fork()`/`join()`, yêu cầu completion dependencies là DAG; cảnh báo deadlock khi cyclic.
- [RecursiveTask](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/RecursiveTask.html): task trả kết quả, `compute()` và cách fork một nhánh, compute một nhánh rồi join.
- [RecursiveAction](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/RecursiveAction.html): action không trả value, chia việc và xử lý vùng dữ liệu.
- [ForkJoinPool](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ForkJoinPool.html): work-stealing, pool lifecycle, `ManagedBlocker`.
- [Future](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Future.html): `get`, cancellation và trạng thái completion.
- [HashSet](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/HashSet.html): sets sử dụng cho `visiting`/`completed` trong DFS validator.
- [Map](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Map.html): biểu diễn task→dependencies và `Map.of`.
- [Java Language Specification — Memory Model](https://docs.oracle.com/javase/specs/jls/se21/html/jls-17.html): happens-before, data races, `final` và visibility.

**Kết luận:** trong Fork/Join, muốn chạy nhanh mà vẫn đúng, hãy **giảm shared mutable state**, dùng kết quả cục bộ và immutable merge hoặc phân hoạch vùng ghi độc quyền, đồng thời giữ quan hệ `fork/join` là **DAG không có vòng chờ**. `fork()` tạo cơ hội song song, `join()` lấy kết quả và phối hợp completion — không phải công cụ phá các phụ thuộc chu kỳ. Chuẩn hóa ownership, xác minh DAG, test các boundary cases và hiểu failure semantics giúp thuật toán vừa an toàn vừa dễ tối ưu trên Java hiện đại.

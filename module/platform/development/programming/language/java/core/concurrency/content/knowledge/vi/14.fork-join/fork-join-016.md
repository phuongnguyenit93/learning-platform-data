# tryComplete(), propagateCompletion() và onCompletion(): cơ chế lan truyền hoàn tất trong Java

Khi dùng `ForkJoinPool` theo mô hình `RecursiveTask`, lập trình viên thường tạo hai task con, gọi `fork()` và chờ `join()`. Tuy nhiên, không phải thuật toán song song nào cũng phù hợp với kiểu **cha đợi từng con**. Một số bài toán là fan-out/fan-in: rất nhiều tác vụ con có độ dài khác nhau, và khi đủ tín hiệu hoàn tất thì một tác vụ cha cần thực hiện bước tiếp theo **mà không bắt một worker ngồi chờ từng child**.

`java.util.concurrent.CountedCompleter<T>` giải quyết bằng **completion count** và **completion chain**. Nó mở rộng `ForkJoinTask<T>`, lưu tham chiếu đến một *completer* (thường là cha), số lượng *pending* cần được ghi nhận, và cung cấp ba API trọng tâm:

- `tryComplete()`: ghi nhận một tín hiệu hoàn tất; khi pending count đang bằng 0, chạy `onCompletion(caller)` rồi **lan lên completer**.
- `propagateCompletion()`: cùng cơ chế ghi nhận và lan lên, nhưng **không gọi `onCompletion`** trên đường lan truyền.
- `onCompletion(CountedCompleter<?> caller)`: callback cho nhánh hoàn tất bình thường khi đủ tín hiệu, dùng để hợp nhất result hoặc thực hiện continuation.

Cách dùng đúng phụ thuộc rất lớn vào **quy tắc đếm tín hiệu**, không phải chỉ nhớ tên method. Đếm sai có thể làm root kết thúc quá sớm, callback hợp nhất dữ liệu chưa sẵn sàng, hoặc khiến `invoke()/join()` chờ mãi.

Bài Knowledge này thuộc nhóm **Fork/Join của Java Concurrency nói chung**, không sử dụng cơ chế riêng của Spring. Các ví dụ chính chạy trên **JDK 17+**, kèm lệnh biên dịch, stdout và phân tích đường hoàn tất.

## 1. Khi nào cần CountedCompleter thay vì RecursiveTask?

Hãy tưởng tượng quét một tập dữ liệu lớn được chia thành các đoạn. Mỗi đoạn được xử lý độc lập; sau khi mọi đoạn con hoàn tất, bước cuối mới được phép tổng hợp kết quả.

Với `RecursiveTask`, parent thường viết:

~~~java
left.fork();
long rightValue = right.compute();
long leftValue = left.join();
return leftValue + rightValue;
~~~

Đây là **mảnh minh họa** thuộc một `compute()` của `RecursiveTask<Long>`, chưa phải chương trình chạy độc lập. `join()` trên child là điểm phối hợp rõ ràng; ForkJoinPool có cơ chế trợ giúp khi chờ join, nhưng cấu trúc thuật toán vẫn gắn với cách parent đợi child.

Với `CountedCompleter`, parent có thể:

1. Thiết lập **số tín hiệu còn phải nhận**.
2. Tạo/fork các child và cho phần thân `compute()` của mình kết thúc mà không đợi bằng `join()`.
3. Mỗi child khi xử lý xong gọi `tryComplete()` hoặc `propagateCompletion()`.
4. Tín hiệu dồn qua chuỗi completer; một callback tại nút cha chỉ chạy khi đã đủ tín hiệu theo protocol.
5. Root được đánh dấu hoàn tất khi quá trình lan truyền thật sự tới root và hoàn tất đúng quy tắc.

Đây là **mô hình continuation dựa trên completion count**, thích hợp khi cấu trúc task phức tạp hơn một cây join tuần tự. Nó không tự cung cấp data aggregation, lock cho shared state hoặc transaction.

### 1.1 Các thuộc tính quan trọng

| Thành phần | Mục đích |
| --- | --- |
| `CountedCompleter<T>` | Task dạng fork/join với protocol completion dựa trên counter. |
| `getCompleter()` | Trả về completer được truyền vào constructor, thường là parent; root thường có `null`. |
| `getPendingCount()` | Đọc pending count **hiện tại**, không phải danh sách child thực sự. |
| `setPendingCount(n)` | Đặt số tín hiệu cần theo contract algorithm. |
| `addToPendingCount(delta)` | Tăng/giảm pending count bằng thao tác atomic, dùng khi sinh task động. |
| `tryComplete()` | Nhận một tín hiệu; có thể decrement hoặc callback và đi lên. |
| `propagateCompletion()` | Nhận tín hiệu/đi lên **không chạy callback**. |
| `onCompletion(caller)` | Xử lý normal completion tại một nút khi pending count đạt điều kiện. |
| `onExceptionalCompletion(ex, caller)` | Hook cho đường hoàn tất ngoại lệ, **khác** normal completion. |
| `getRawResult()` | Cách cung cấp giá trị cho task trả về `T`; mặc định không tự lấy giá trị từ biến tuỳ ý. |

**Lưu ý:** CountedCompleter không tự duy trì danh sách những child nào đang chạy, đã xong hoặc đã thất bại. Pending count chỉ là **số nguyên đồng bộ**; chương trình phải tự duy trì liên hệ child→parent và dữ liệu kết quả nếu cần.

## 2. Pending count: không đơn giản là “số child”

Phát biểu chính xác về `tryComplete()` trong Java 17:

- Nếu `getPendingCount() > 0` tại thời điểm thử, thao tác **decrement count một lần** rồi trở về, không gọi `onCompletion` tại nút đó.
- Nếu pending count **đã bằng 0** tại thời điểm thử, gọi `onCompletion(caller)` rồi tiếp tục thử hoàn tất **completer của nút này**.
- Khi đường lan đến một **root không có completer**, root cuối cùng được đánh dấu hoàn tất bình thường để caller `invoke()/join()` được giải phóng.
- Khi callback được thực thi ở một nút, tham số `caller` là task đã kích hoạt bước lan truyền đến nút đó; có thể bằng `this` hoặc một child.

Điều hơi ngược trực giác: **lần tín hiệu làm pending từ 1 về 0 không gọi callback**. Phải có **một lần gọi tiếp theo** khi count đã bằng 0 để kích hoạt callback.

### 2.1 Một task có pending count ban đầu là 2

~~~text
Pending lúc đầu: 2

tryComplete() lần 1:
    thấy pending=2 -> giảm còn 1 -> return

tryComplete() lần 2:
    thấy pending=1 -> giảm còn 0 -> return

tryComplete() lần 3:
    thấy pending=0 -> onCompletion(caller)
                   -> thử tiếp ở completer/đánh dấu root done
~~~

Vì vậy, số pending ban đầu thường bằng **số tín hiệu sẽ tới nút trước tín hiệu chốt cuối cùng**.

| Có bao nhiêu lời gọi báo hoàn tất sẽ tới nút? | Pending ban đầu thường đặt |
| --- | --- |
| 1 tín hiệu | 0 |
| 2 tín hiệu | 1 |
| 3 tín hiệu | 2 |
| N tín hiệu | N−1 |

Bảng là **một quy tắc cho pattern mà mỗi tín hiệu đến đúng một lần và không có dynamic registration**. Nó không thay mọi thuật toán CountedCompleter: nếu node tự gọi `tryComplete()` sau khi đăng ký child, tổng số tín hiệu cũng phải tính thêm phần **self signal**.

### 2.2 Không đọc pending như số child chưa hoàn tất

Pending count không biết danh tính task; nó chỉ biết có bao nhiêu lần điều chỉnh. Vì vậy:

- `pending == 0` **không tự chứng minh** mọi child đã hoàn tất nếu có child chưa báo tín hiệu.
- `pending == 0` cũng **không tự có nghĩa root done**. Còn cần một lần `tryComplete()`/`propagateCompletion()` để kích hoạt đường cuối.
- `getPendingCount()` là snapshot đồng thời, không dùng riêng để quyết định transaction/snapshot của dữ liệu child.
- `setPendingCount(...)` không phải “đặt số lượng thread muốn dùng”; đó là phần của giao thức completion.

Sai lầm phổ biến là đặt pending bằng số child rồi chỉ để mỗi child gọi `tryComplete()` một lần: nút có thể còn ở 0 nhưng **chưa hề chạy onCompletion** vì thiếu tín hiệu chốt.

## 3. Hai mẫu đếm hợp lệ: self-signal và child-only

Giả sử một parent tạo đúng hai child.

### Mẫu A — Parent cũng tự báo hoàn tất

~~~text
Parent: pending = 2

Parent chuẩn bị/fork children xong -> parent.tryComplete()
Child 1 kết thúc -> child.tryComplete() -> báo lên parent
Child 2 kết thúc -> child.tryComplete() -> báo lên parent

Tổng ba tín hiệu: parent + child1 + child2.
pending=2 -> 1 -> 0 -> callback của parent -> propagation.
~~~

Mẫu này thường thấy khi parent có phần việc riêng hoặc quá trình tạo child động. **Phải tăng pending trước khi child có thể hoàn tất**.

### Mẫu B — Chỉ hai child báo hoàn tất

~~~text
Parent: pending = 1

Parent tạo child1, child2, không gọi parent.tryComplete().
Child 1 -> báo lên parent: pending 1 -> 0
Child 2 -> báo lên parent: pending 0 -> onCompletion/propagate

Tổng hai tín hiệu. Không có self-signal.
~~~

Đây là mẫu mà các ví dụ cây tính tổng trong bài dùng: parent giao việc cho hai child, còn chính parent không tiếp tục gửi một tín hiệu thứ ba. Nếu thay `pending=1` bằng `pending=2` mà không thêm `parent.tryComplete()`, root có thể **không bao giờ complete**.

### 3.1 Trường hợp child hoàn thành trước khi parent compute trở về

CountedCompleter không yêu cầu parent đợi child ở cuối `compute()`. Child được fork có thể xong trước hoặc sau khi parent trả về. Giao thức vẫn đúng nếu:

1. Đăng ký pending/child references **trước khi fork** để không race với completion.
2. Mỗi đường child hoàn tất chỉ gửi một tín hiệu đúng số lần.
3. Callback đọc result chỉ khi các tín hiệu đã đại diện đầy đủ cho dữ liệu cần hợp nhất.
4. Không gọi `quietlyCompleteRoot()` sớm khi các child còn có side effect cần chờ.

## 4. tryComplete(): callback rồi leo lên chuỗi completer

Xét cây:

~~~text
                       Root
                      /    \
                     A      B
                   /  \    /  \
                  A1  A2  B1  B2
~~~

Mỗi leaf có pending 0. Mỗi internal node có pending 1 vì chỉ có hai child gửi tín hiệu.

Nếu A1 xong trước A2:

~~~text
A1.tryComplete()
  A1.pending=0 -> A1.onCompletion(A1)
  -> A.tryComplete(): A.pending=1 -> giảm thành 0; dừng

A2.tryComplete()
  A2.pending=0 -> A2.onCompletion(A2)
  -> A.tryComplete(): A.pending=0 -> A.onCompletion(A2)
  -> Root.tryComplete(): ...
~~~

Nhánh B làm tương tự. Khi A và B đều báo xong cho Root, callback của Root được thực thi một lần và Root được đánh dấu done.

Điểm quan trọng:

- **Parent không tự gọi `join()` trên từng child**.
- Worker nào thực thi callback tại parent phụ thuộc đường tín hiệu cuối cùng; **đừng dựa vào tên thread** để khẳng định callback được parent thread chạy.
- Tham số `caller` có thể là child kích hoạt bước cuối, hoặc `this` trong self-signal pattern. Không cố định là “child bên phải” hay “child submit sau”.
- Callback của một node được kích hoạt **sau khi đủ tín hiệu**, không nhất thiết ngay khi method `compute()` của node trở về.

### 4.1 onCompletion mặc định làm gì?

Implementation mặc định của `onCompletion(CountedCompleter<?> caller)` **không làm gì**. Nó là điểm mở rộng cho application logic, chẳng hạn hợp nhất kết quả hai nhánh hoặc đánh dấu một bước continuation.

Nếu cây không cần callback ở các nút, `propagateCompletion()` thường đơn giản và tránh chi phí gọi method callback không cần thiết.

## 5. Ví dụ Java 17+: cây tổng với onCompletion hợp nhất kết quả

Ví dụ sau phân rã mảng 8 phần tử. Mỗi leaf tính tổng đoạn nhỏ; mỗi internal node tính tổng hai child **trong `onCompletion`**. Không cần một `AtomicLong` chung để tất cả worker cùng cộng.

Tạo `CountedCompleterSumDemo.java`:

~~~java
import java.util.concurrent.CountedCompleter;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public final class CountedCompleterSumDemo {
    private static final class SumTask extends CountedCompleter<Long> {
        private static final int THRESHOLD = 2;
        private final long[] values;
        private final int start, end;
        private final AtomicInteger callbackCount;
        private SumTask left, right;
        private long result;

        SumTask(CountedCompleter<?> parent, long[] values, int start,
                int end, AtomicInteger callbackCount) {
            super(parent);
            this.values = values;
            this.start = start;
            this.end = end;
            this.callbackCount = callbackCount;
        }

        @Override public void compute() {
            if (end - start <= THRESHOLD) {
                long local = 0;
                for (int i = start; i < end; i++) local += values[i];
                result = local;
                tryComplete();
                return;
            }

            int mid = start + (end - start) / 2;
            left = new SumTask(this, values, start, mid, callbackCount);
            right = new SumTask(this, values, mid, end, callbackCount);
            setPendingCount(1); // Hai child signal; last signal completes.
            right.fork();
            left.compute();
        }

        @Override public void onCompletion(CountedCompleter<?> caller) {
            if (left != null) result = left.result + right.result;
            callbackCount.incrementAndGet();
        }

        @Override public Long getRawResult() { return result; }
    }

    public static void main(String[] args)
            throws InterruptedException {
        long[] values = {1, 2, 3, 4, 5, 6, 7, 8};
        AtomicInteger callbacks = new AtomicInteger();
        ForkJoinPool pool = new ForkJoinPool(4);

        try {
            Long sum = pool.invoke(
                    new SumTask(null, values, 0, values.length, callbacks));
            System.out.println("Sum: " + sum);
            System.out.println("onCompletion calls: " + callbacks.get());
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS))
                pool.shutdownNow();
        }
    }
}
~~~

Biên dịch/chạy bằng JDK 17+:

~~~bash
javac CountedCompleterSumDemo.java
java CountedCompleterSumDemo
~~~

Stdout:

~~~text
Sum: 36
onCompletion calls: 7
~~~

**Giải thích:**

1. Mảng gồm 8 số từ 1 đến 8; tổng đúng là **36**.
2. Threshold bằng 2: cây có **4 leaf** (mỗi leaf xử lý 2 phần tử), **2 internal node trung gian**, **1 root** — tổng cộng 7 node.
3. Leaf tính `result` của chính mình rồi `tryComplete()`. Pending 0 ở leaf nên callback của leaf chạy và tín hiệu đi lên parent.
4. Internal node tạo hai child, **đặt pending=1 trước khi fork**, fork nhánh phải và chạy nhánh trái trực tiếp. Chính internal node không gọi tryComplete ngay sau khi spawn, vì chỉ hai child báo completion.
5. Child đầu báo lên làm pending của parent giảm 1→0; child cuối đến khi pending đã 0 kích hoạt `onCompletion` của parent.
6. Trong callback của parent, `left.result` và `right.result` đã được tính bởi các subtrees theo protocol; parent ghi `result = left.result + right.result`.
7. `getRawResult()` trả `result` của task. `CountedCompleter<Long>` **không tự suy ra result** chỉ từ return type; ta phải override để `pool.invoke(root)` đọc được giá trị đã ghi.
8. Mỗi node gọi `onCompletion` đúng một lần: 7 callbacks. `AtomicInteger` chỉ dùng để đếm callback phục vụ demo, không dùng để cộng toàn bộ dữ liệu, tránh contention không cần thiết.

Tổng và số callback là **xác định theo cây**, còn callback chạy trên worker nào hay thứ tự print nếu tự in trong callback là **không xác định**; vì vậy demo chỉ in sau khi `pool.invoke(root)` hoàn tất.

### 5.1 Vì sao result của child có thể đọc trong callback?

Theo hợp đồng CountedCompleter, nếu pending counts và luồng tín hiệu được dùng đúng, `onCompletion` được thực thi sau khi đủ bước completion từ các child; tài liệu Java nêu rằng không cần thêm đồng bộ hóa **trong onCompletion** để đọc fields của task và các child đã hoàn tất trong giao thức đó.

Điều kiện này **không phải giấy phép đọc mọi biến toàn cục**: một thread ngoài có thể sửa `values` đồng thời, hoặc một child có thể signal trước khi thực sự viết xong result, thì tính đúng đắn vẫn bị phá. Hãy bảo vệ ownership của input, viết result **trước** khi signal và không cho writer ngoài bỏ qua contract.

## 6. propagateCompletion(): lan truyền mà không gọi onCompletion

Nếu callback ở các node **không cần thiết**, dùng `propagateCompletion()`:

- Nếu pending count ở node đang dương, decrement một lần và return.
- Nếu pending bằng 0, **không gọi `onCompletion`**, mà tiếp tục truyền tín hiệu lên completer.
- Ở root không có completer, đánh dấu root done bình thường khi đường lan truyền tới đó.
- Kết quả sẽ **không được hợp nhất tự động**. Nếu cần reduction, phải có một protocol khác để chuẩn bị kết quả; đừng đổi `tryComplete` thành `propagateCompletion` trong ví dụ tổng rồi vẫn mong callback gộp child results.

### 6.1 So sánh trực tiếp

| Điều kiện tại node | `tryComplete()` | `propagateCompletion()` |
| --- | --- | --- |
| Pending đang > 0 | Decrement một và return. | Decrement một và return. |
| Pending đang = 0 | Gọi `onCompletion(caller)` rồi lên completer. | **Bỏ qua callback**, lên completer ngay. |
| Lên tới root | Đánh dấu root hoàn tất sau đường callback cần thiết. | Đánh dấu root hoàn tất **không qua callbacks**. |
| Dùng khi | Parent phải merge result, cleanup/continuation khi đủ child. | Chỉ cần bảo đảm tất cả leaf xong, không có logic mỗi-nút cần chạy. |
| Hậu quả nếu chọn sai | Callback có thể chạy khi không mong muốn. | Bỏ mất aggregation/continuation phụ thuộc callback. |

## 7. Ví dụ Java 17+: propagateCompletion không gọi callback

Ví dụ dưới chuyển từng phần tử `input[i]` thành `output[i] = input[i] + 1`. Các vùng ghi không chồng lấn; **không cần callback hợp nhất**: sau khi root complete, main có thể tính tổng output tuần tự.

Tạo `CountedCompleterPropagateDemo.java`:

~~~java
import java.util.concurrent.CountedCompleter;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public final class CountedCompleterPropagateDemo {
    private static final class MapTask extends CountedCompleter<Void> {
        private static final int THRESHOLD = 2;
        private final int[] input, output;
        private final int start, end;
        private final AtomicInteger callbacks;

        MapTask(CountedCompleter<?> parent, int[] input, int[] output,
                int start, int end, AtomicInteger callbacks) {
            super(parent);
            this.input = input;
            this.output = output;
            this.start = start;
            this.end = end;
            this.callbacks = callbacks;
        }

        @Override public void compute() {
            if (end - start <= THRESHOLD) {
                for (int i = start; i < end; i++)
                    output[i] = input[i] + 1;
                propagateCompletion();
                return;
            }

            int mid = start + (end - start) / 2;
            setPendingCount(1);
            new MapTask(this, input, output, mid, end, callbacks).fork();
            new MapTask(this, input, output, start, mid, callbacks).compute();
        }

        @Override public void onCompletion(CountedCompleter<?> caller) {
            callbacks.incrementAndGet();
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        int[] input = {1, 2, 3, 4, 5, 6, 7, 8};
        int[] output = new int[input.length];
        AtomicInteger callbacks = new AtomicInteger();
        ForkJoinPool pool = new ForkJoinPool(3);

        try {
            pool.invoke(new MapTask(
                    null, input, output, 0, input.length, callbacks));
            int sum = 0;
            for (int value : output) sum += value;

            System.out.println("Transformed sum: " + sum);
            System.out.println("onCompletion calls: " + callbacks.get());
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS))
                pool.shutdownNow();
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac CountedCompleterPropagateDemo.java
java CountedCompleterPropagateDemo
~~~

Stdout:

~~~text
Transformed sum: 44
onCompletion calls: 0
~~~

**Phân tích:**

- Output đúng là `{2,3,4,5,6,7,8,9}` và tổng bằng 44.
- Mỗi leaf ghi đoạn output riêng rồi gọi `propagateCompletion()`; đường completion qua internal nodes không thực thi callback.
- Override `onCompletion` cố ý tăng counter nếu từng được gọi, để kiểm chứng **số callback bằng 0**.
- Root vẫn được đánh dấu done khi mọi tín hiệu từ các child đã lan đúng đến root, nên main an toàn đọc output sau `pool.invoke`.
- Phải dùng đúng pending count và phạm vi không chồng lấn; `propagateCompletion` không biến các phép ghi data-race thành an toàn một cách tự động.

Đây là ví dụ về **completion barrier qua CountedCompleter**, không có nhu cầu merge tại từng node. Nếu bước tiếp theo cần hợp nhất theo cây, dùng `tryComplete` cùng callback phù hợp hoặc cơ chế reduction khác.

## 8. onCompletion(caller): nội dung callback, tham số caller

`onCompletion(CountedCompleter<?> caller)` được gọi khi đường **normal completion** của `tryComplete()` tới một node mà pending count đang bằng 0. Mặc định method này không làm gì; override khi cần thực hiện một bước sau khi đủ tín hiệu từ các child.

Các trường hợp thường thấy:

- **Leaf:** pending 0; leaf gọi `tryComplete()` nên `onCompletion(leaf)` có `caller == this`.
- **Parent do child cuối kích hoạt:** `caller` có thể là chính child kích hoạt chain, thường `caller != this`.
- **Parent tự gửi self-signal cuối:** `caller == this` có thể xảy ra nếu parent gọi `tryComplete()` khi pending đã về 0.

Vì vậy tuyệt đối **không dựa vào caller luôn là một child** hoặc luôn là `this`. Nếu dùng caller để lấy result, phải hiểu rõ giao thức và có đường xử lý cho cả hai trường hợp.

### 8.1 Callback hợp nhất kết quả

Trong `CountedCompleterSumDemo`:

~~~java
@Override public void onCompletion(CountedCompleter<?> caller) {
    if (left != null) result = left.result + right.result;
    callbackCount.incrementAndGet();
}
~~~

Đây là mảnh thuộc class đã định nghĩa. Node có `left == null` là leaf, đã có `result` từ compute; callback không cần thay result. Node có hai child hợp nhất sau khi **cả hai subtree đã báo đủ tín hiệu**.

Nếu callback có side effect như gửi network message hoặc gọi code không kiểm soát:

- Có thể làm chậm critical path hoàn tất của root.
- Có thể throw exception và biến completion path thành abnormal completion.
- Không có bảo đảm callback chạy trên một worker cố định.
- Nếu callback cập nhật shared state toàn cục, vẫn phải đồng bộ như bình thường.
- Nếu đòi thứ tự aggregation, phải lưu child positions và kết hợp theo đúng thứ tự nghiệp vụ; caller cuối cùng không tự quyết định thứ tự dữ liệu.

### 8.2 “Một lần mỗi node” phụ thuộc protocol

Tài liệu mô tả callback được kích hoạt một lần khi sử dụng pending counts đúng. Nhưng nếu code tự gọi `tryComplete()` dư nhiều lần, dùng `complete()` tùy tiện hoặc tái sử dụng task sai lifecycle, không thể giữ một kết luận “luôn một lần” trên một protocol bị phá.

**Định nghĩa số tín hiệu, ai gửi và khi nào gửi** trước khi triển khai callback.

## 9. Ví dụ Java 17+: self-signal và one-child pattern

Một parent có một child và chính nó cũng gửi một tín hiệu khi hoàn tất bước tạo child. Khi đó cần **hai tín hiệu tổng**, pending khởi tạo bằng 1.

Tạo `CountedCompleterSelfSignalDemo.java`:

~~~java
import java.util.concurrent.CountedCompleter;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public final class CountedCompleterSelfSignalDemo {
    private static final class Root extends CountedCompleter<Void> {
        private final AtomicInteger callbacks = new AtomicInteger();

        Root() { super(null, 1); }

        @Override public void compute() {
            new Child(this).fork();
            tryComplete(); // Root's own work is complete.
        }

        @Override public void onCompletion(CountedCompleter<?> caller) {
            callbacks.incrementAndGet();
        }
    }

    private static final class Child extends CountedCompleter<Void> {
        Child(CountedCompleter<?> parent) { super(parent); }
        @Override public void compute() { tryComplete(); }
    }

    public static void main(String[] args)
            throws InterruptedException {
        ForkJoinPool pool = new ForkJoinPool(2);
        try {
            Root root = new Root();
            pool.invoke(root);
            System.out.println("Root callbacks: " + root.callbacks.get());
            System.out.println("Root done: " + root.isDone());
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS))
                pool.shutdownNow();
        }
    }
}
~~~

Lệnh:

~~~bash
javac CountedCompleterSelfSignalDemo.java
java CountedCompleterSelfSignalDemo
~~~

Stdout:

~~~text
Root callbacks: 1
Root done: true
~~~

**Giải thích:**

- Root cần hai tín hiệu: từ **Root.compute()** và từ **Child.compute()**. Pending=1.
- Nếu Root.tryComplete chạy trước, nó giảm pending 1→0; khi Child.tryComplete tới Root, pending 0 kích hoạt root callback.
- Nếu Child kết thúc trước, tín hiệu từ Child giảm pending 1→0; Root.tryComplete tới sau kích hoạt root callback.
- Trong hai lịch, callback root chạy **đúng một lần**; nhưng **caller** có thể là Root hoặc Child. Vì vậy demo không in caller/thread name mà chỉ in counter sau `invoke()`.
- Root không dùng `join()` trên Child mà vẫn không đánh dấu done trước khi nhận đủ hai tín hiệu.

Đây là ví dụ thu nhỏ minh họa vì sao công thức pending count phụ thuộc số tín hiệu, không chỉ số child.

## 10. So sánh ba API theo từng thời điểm

Với một node `N` có pending ban đầu là 1:

~~~text
Ban đầu: N.pending=1

Signal 1: childA.tryComplete()/propagateCompletion()
          -> tới N, thấy 1, giảm xuống 0, return

Signal 2: childB.tryComplete()
          -> tới N, thấy 0
          -> N.onCompletion(childB)
          -> tiếp tục đến N.getCompleter()

Signal 2': childB.propagateCompletion()
          -> tới N, thấy 0
          -> KHÔNG gọi N.onCompletion
          -> tiếp tục đến N.getCompleter()
~~~

Dùng ví dụ này để nhớ:

- `tryComplete()` là **count + callback + propagation**.
- `propagateCompletion()` là **count + propagation**, bỏ callback.
- `onCompletion(...)` **không phải method gửi tín hiệu**. Nó là một hook **được gọi từ tryComplete/complete theo contract**.

Nếu lập trình viên tự gọi `onCompletion(caller)` từ compute, đó chỉ là một lời gọi method Java thông thường; nó không tự decrement pending hay đánh dấu root done. Đừng thay `tryComplete()` bằng lời gọi callback trực tiếp.

## 11. Đường lan truyền hoàn tất không phải completion status của mọi child

Một nuance quan trọng trong Javadoc `CountedCompleter`: task có `getCompleter() != null` thường là **helper nội bộ**, và trạng thái `isDone()` của chính helper đó **không nhất thiết phản ánh lúc nó đã gửi completion signal**. Việc chuyển tín hiệu lên cha không nhất thiết đánh dấu task helper riêng lẻ completed theo cách một `RecursiveTask.join()` thường được dùng.

Do đó:

- Nên `invoke(root)` / `join(root)` để đợi **toàn bộ giao thức completion của root**.
- **Không mặc định** gọi `child.join()` cho mọi helper CountedCompleter rồi đòi chúng đều có completion status như task độc lập.
- `child.getPendingCount()==0` không phải một Future completion flag.
- Root hoàn tất bình thường chỉ khi đường completion đến nó đúng protocol, không phải vì parent compute return.
- Nếu tự dùng `complete(T)`/`quietlyCompleteRoot()` để đánh dấu sớm, bạn có thể khiến root done trước khi một số child còn side effect; cần hiểu mức độ bảo đảm của thuật toán.

Cách suy nghĩ đúng là **đồ thị các tín hiệu hoàn tất**, không phải mỗi parent đều đang đứng tại dòng `join()` chờ child.

## 12. complete(T), quietlyCompleteRoot() và vì sao chúng khác tryComplete

Ngoài ba API trọng tâm, CountedCompleter có một số method mạnh hơn:

### 12.1 complete(T rawResult)

Theo Java 17, `complete(rawResult)`:

1. Gọi `setRawResult(rawResult)`;
2. Gọi `onCompletion(this)`;
3. Đánh dấu **task hiện tại** completed;
4. Kích hoạt `tryComplete()` trên completer nếu có.

Nó thực hiện đường **unconditional completion**: không đợi pending count về 0 và **không tự điều chỉnh pending count** của task đang được complete. Vì vậy không dùng `complete(result)` để thay một lần “child finished” thông thường nếu parent thật sự cần tất cả children.

Với `CountedCompleter<T>`, default `setRawResult(T)` có thể **không lưu giá trị hữu ích**; muốn `get()/join()` trả `T`, subclass phải triển khai result management thích hợp, thường override `getRawResult()` và/hoặc `setRawResult()`.

### 12.2 quietlyCompleteRoot()

`quietlyCompleteRoot()` đánh dấu **root** complete mà không theo đường callback thông thường. Nó hữu ích cho **search first-match** nơi một nhánh tìm thấy đáp án và muốn cho root trả kết quả sớm.

Tuy nhiên khi root đã complete sớm:

- Những worker/child khác có thể **vẫn đang chạy**.
- Root completed không tự cancel/interrupt mọi child.
- Không được dùng nếu ứng dụng yêu cầu tất cả child side effects đã kết thúc trước khi trả.
- Để huỷ các branch còn lại có kiểm soát, có thể publish cờ kết quả qua `AtomicReference` và cho child tự kiểm tra tại safe points, hoặc dùng cancellation policy phù hợp.

`quietlyCompleteRoot()` không phải cách sửa pending count bị tính sai; nó sẽ **che lỗi** mà không chứng minh mọi task đã xong.

## 13. onExceptionalCompletion: ngoại lệ đi theo đường khác

`onCompletion(...)` là hook cho **normal completion**. Nếu `compute()` ném exception hoặc task được hoàn tất bất thường bằng `completeExceptionally(Throwable)`, `CountedCompleter` có đường **exceptional completion** riêng.

Hook:

~~~java
@Override
public boolean onExceptionalCompletion(
        Throwable error, CountedCompleter<?> caller) {
    logFailure(error);
    return true; // Cho phép lỗi truyền lên completer theo contract.
}
~~~

Đây là **mảnh minh họa**; method `logFailure` giả định có sẵn, và phải được đặt trong subclass CountedCompleter. Default implementation của `onExceptionalCompletion` trả `true` mà không làm gì thêm, thường cho phép lỗi được propagate lên cha nếu cha chưa hoàn tất.

Điểm cần lưu ý:

- Lỗi có thể **đi lên completer chain** mà không chạy các callback normal còn thiếu.
- `false` là quyết định không tiếp tục exception propagation theo hợp đồng; **không** có nghĩa tự động rollback hay thay thế kết quả.
- Một child bị cancel không mặc nhiên cancel toàn bộ các child còn lại.
- Không bắt `Throwable` rồi âm thầm gọi `tryComplete()` như thể task đã thành công, trừ khi contract định nghĩa **fallback result hợp lệ** và vẫn giữ invariant.
- Nếu callback `onCompletion` tự ném exception, nó cũng làm đường hoàn tất phức tạp; callback nên nhỏ, rõ và tránh external side effect khó rollback.

Khi muốn lấy failure từ root, có thể dùng `pool.invoke(root)` (ném unchecked abnormal completion phù hợp) hoặc `Future.get()` theo hợp đồng checked `ExecutionException`. Không coi việc `compute()` của một helper đã return là chứng minh root success.

## 14. Đúng trình tự đăng ký child trước khi fork

Một race tinh vi xuất hiện khi tạo child rồi fork ngay, **sau đó mới tăng pending**:

~~~java
new Child(this).fork();
addToPendingCount(1); // Rủi ro: Child có thể hoàn tất trước khi đăng ký.
~~~

Đây là **mảnh sai**. Nếu child hoàn tất rất nhanh, nó có thể gọi `tryComplete()`, lan tới parent và thấy count chưa được tăng. Parent có thể chạy callback/propagate quá sớm, trong khi main còn định đăng ký thêm work.

Mẫu đúng:

~~~java
addToPendingCount(1);
new Child(this).fork();
~~~

Đây là mảnh minh họa trong trường hợp **parent có thêm một tín hiệu tương ứng với cấu trúc thuật toán**, không phải quy tắc “mỗi child luôn add 1” không cần nghĩ. Phải tính từ **tổng số tín hiệu** theo pattern, không tăng bừa.

Với một parent có hai child và **không tự gửi tín hiệu**, ví dụ đã kiểm chứng đặt `setPendingCount(1)` trước khi fork hai child. Với self-signal cộng N child, một mô hình thường đặt pending=N rồi cho self và N child mỗi bên báo một lần.

### 14.1 Nếu sinh child động

Khi số child chưa biết trước:

1. Parent là owner của việc đăng ký child.
2. Trước khi fork mỗi child mới, tăng pending count tương ứng **theo giao thức có self-signal hoặc trigger cuối**.
3. Sau khi không tạo thêm child, parent gửi self-signal qua `tryComplete()` nếu mô hình yêu cầu.
4. Child hoàn thành gọi tryComplete/propagate đúng một lần.
5. Không đăng ký child mới **sau khi root có thể đã được đánh dấu hoàn tất**, trừ khi thuật toán có protocol riêng rõ ràng.

Một race đăng ký muộn có thể tạo callback trước khi tất cả work được biết đến, khiến kết quả thiếu dữ liệu. `CountedCompleter` không tự quản lý danh sách children để cứu tình huống này.

## 15. Result aggregation, side effects và ownership

Trong bài toán tổng mảng, node ghi `result` của chính nó; callback của parent đọc child results **sau khi đủ signals**. Đây là pattern hợp lý vì mỗi node có một owner viết result, và parent chỉ đọc sau completion.

Hãy xác định rõ:

| Dữ liệu | Ai ghi? | Khi nào đọc an toàn? |
| --- | --- | --- |
| Input array immutable trong lúc chạy | Caller chuẩn bị trước khi invoke. | Các leaf có thể đọc song song theo contract publication. |
| `leaf.result` | Chính leaf khi tính xong. | Parent callback sau leaf hoàn tất theo đúng signal protocol. |
| `parent.result` | Parent trong onCompletion. | Grandparent callback sau parent đã báo completion. |
| Global counter metrics | Nhiều worker có thể ghi. | Dùng `AtomicInteger`/`LongAdder` theo consistency requirement. |
| Output array theo partition | Leaf sở hữu vùng `[start,end)` không giao nhau. | Caller đọc sau root complete. |
| Shared List/Map mutable | Có thể nhiều writer. | Cần cấu trúc concurrent, lock hoặc ownership riêng. |

### 15.1 Không để callback tự đặt ra thứ tự hoàn tất

`onCompletion(caller)` có thể được thực thi bởi worker khác nhau tùy nhánh nào đến cuối. Nếu phép gộp **không giao hoán** (ví dụ nối chuỗi phải giữ thứ tự, merge cây thứ tự khóa), phải lưu left/right slot rõ ràng và kết hợp theo **left rồi right**, không theo “child nào gọi callback sau”.

Trong `SumTask`, cộng số nguyên giao hoán nên lựa chọn left/right không ảnh hưởng. Với concat hoặc thao tác trên event stream, thứ tự có thể là một phần của correctness.

### 15.2 Không đặt I/O chậm trong callback nếu không cần

Một `onCompletion` gọi remote API có thể giữ đường critical path của root lâu, làm worker bị chặn, và nếu ném exception thì ảnh hưởng completion chain. Nên để callback chỉ làm aggregation nhỏ/thuần, rồi đặt I/O sau khi root hoàn tất hoặc trong executor/layer phù hợp. Nếu callback phải block trên ForkJoinPool, xem xét API `managedBlock` và deadline theo yêu cầu; nó không sửa deadlock hay tự rollback state.

## 16. Callback caller có thể là ai? Vì sao không nên assert tên thread?

Với self-signal pattern, hai lịch hợp lệ:

~~~text
Lịch A:
Root.tryComplete()  -> pending 1→0
Child.tryComplete() -> Root.onCompletion(caller=Child)

Lịch B:
Child.tryComplete() -> pending 1→0
Root.tryComplete()  -> Root.onCompletion(caller=Root)
~~~

Hai lịch đều tạo cùng kết quả nghiệp vụ. Vì vậy:

- `caller == this` **không** luôn đúng.
- `caller != this` **không** luôn đúng.
- Callback không chạy bắt buộc trên thread đã tạo parent object.
- Số thứ tự log trong callback không phải invariant khi worker thực hiện song song.

Viết callback theo **dữ liệu/node relationship** và contract tổng hợp; không phụ thuộc vào worker name, CPU hay số nanosecond.

## 17. Tại sao internal task isDone có thể gây hiểu nhầm?

Một `CountedCompleter` đóng vai trò helper có completer thường chỉ là mắt xích xử lý tín hiệu. Theo Java 17 Javadoc, **trạng thái hoàn tất của chính helper** có thể không được thay đổi trừ khi nó được `complete`, `cancel`, `completeExceptionally` hoặc có exceptional completion qua `compute` theo đường riêng.

Do đó:

~~~java
CountedCompleter<?> child = ...; // Helper có completer.
child.fork();
child.join(); // Không phải mẫu đợi cây CountedCompleter chuẩn.
~~~

Đây là **mảnh code minh họa chống mẫu**, không chạy độc lập. Nếu child chỉ gọi `tryComplete()` để gửi tín hiệu lên cha, `join()` trên child không được dùng như thước đo thay thế cho việc root đã nhận mọi completion. Thay vào đó:

~~~java
CountedCompleter<?> root = ...; // Root với protocol hoàn tất đúng.
pool.invoke(root);
~~~

Mảnh này giả định root và pool hợp lệ, method xử lý exception thích hợp. Caller nên chờ **root**, còn các helper tham gia lan truyền tín hiệu theo thiết kế.

Một vấn đề tương tự xảy ra khi dùng `getPendingCount() == 0` như một điều kiện dừng: pending 0 vẫn chưa chứng minh completion callback đã chạy hoặc root được đánh dấu done.

## 18. Cancellation, progress và deadlock

`CountedCompleter` giúp giảm nhu cầu chờ từng child bằng join, nhưng không bảo đảm mọi chương trình không có deadlock/starvation.

Rủi ro thường gặp:

- **Thiếu một signal:** một leaf return mà quên `tryComplete/propagateCompletion`; root vẫn đợi.
- **Dư một signal:** gọi hai lần hoặc double-complete khiến callback chạy quá sớm/duplicate.
- **Pending đăng ký sau fork:** fast child hoàn tất trước khi parent tăng count.
- **Leaf block vô hạn:** completion không thể tiến lên dù counter đúng.
- **Deadlock lock:** parent/child giữ monitor rồi chờ code cần monitor đó.
- **Side effect chưa xong:** child signal trước khi ghi dữ liệu hoàn tất.
- **Cancellation đơn lẻ:** cancel helper không tự hoàn thành/cancel toàn bộ root và các helper khác.
- **Error bị nuốt:** catch exception rồi báo normal completion với state sai.
- **Task tree quá sâu/nhỏ:** overhead fork, GC và work stealing có thể lấn át công việc hữu ích.

### 18.1 Progress của root không phải dấu hiệu mọi resource đã giải phóng

Một thuật toán có thể **early complete** root sau khi tìm ra kết quả đầu tiên bằng `quietlyCompleteRoot()`. Các branch khác cần **tự kiểm tra cờ hoàn tất/cancel** nếu muốn dừng nhanh. Phải có policy quản lý executor/cleanup. `root.isDone()` lúc ấy không tự chứng minh mọi task phụ đã ngừng và mọi tài nguyên đã đóng.

### 18.2 Interruption và deadline

`ForkJoinTask.join()` không ném checked `InterruptedException` theo hợp đồng bình thường. Nếu chương trình cần deadline, cân nhắc `get(timeout, unit)` ở entrypoint phù hợp, cộng với **cooperative cancellation** của tasks. Timed get hết hạn chỉ giới hạn thời gian chờ caller, không dừng toàn cây. Tránh cố "fix" deadlock bằng cách đột ngột stop thread đang giữ lock.

## 19. Test và quan sát cơ chế hoàn tất

Kiểm thử tốt không suy từ thứ tự log vốn không xác định. Thay vào đó:

1. **Result chính xác:** bài toán tổng mảng có sum=36, biến đổi output có sum=44.
2. **Số callback:** cây 7 node đúng protocol gọi 7 `onCompletion` với tryComplete; dùng propagateCompletion thì 0.
3. **Self-signal race:** thử cả hai thứ tự parent/child báo hoàn tất bằng latch, xác minh root callback đúng một lần.
4. **Zero-length input:** định nghĩa leaf behavior rõ; không fork vô hạn.
5. **Threshold:** chỉ số biên không chồng lấn, node tree có base case.
6. **Failure injection:** child throw exception; root phải hoàn tất bất thường hoặc có fallback có kiểm soát, không chờ vô hạn.
7. **Timeout:** test có deadline phù hợp, không để thread non-daemon treo CI.
8. **Callback side effects:** nếu callback ghi shared mutable state, verify thread safety và idempotency.
9. **Duplicate/missing signal:** review static protocol và có metric để phát hiện pending không về đúng.
10. **Multiple JDK/CPU environments:** kết quả phải đúng bất kể thứ tự workers.

### 19.1 Phân biệt callback count và steal count

`ForkJoinPool.getStealCount()` ước lượng số lần work stealing, không có liên hệ số học cố định với `onCompletion()` callback count. Một task tree có thể chạy trên một worker mà không có steal nhưng vẫn có đủ mọi callback. Đừng assert rằng phải steal mới chứng minh CountedCompleter hoạt động.

### 19.2 Đừng kiểm tra completion bằng sleep

~~~java
root.fork();
Thread.sleep(100);
System.out.println(root.isDone());
~~~

Đây là **mảnh chống mẫu**, giả định code có xử lý `InterruptedException`. `sleep` không bảo đảm root đã hoàn tất; test có thể flaky. Dùng `pool.invoke(root)`, `root.join()` (đối với root) hoặc `get(timeout)` và assert kết quả/callback.

## 20. Cách chọn giữa tryComplete và propagateCompletion

| Câu hỏi | Nếu “Có” thì nên cân nhắc |
| --- | --- |
| Parent phải hợp nhất result của các child **khi đủ signals**? | `tryComplete` + `onCompletion`. |
| Chỉ cần đợi root biết toàn bộ cây đã xong, output được ghi vào các vùng riêng? | `propagateCompletion`, không callback. |
| Thuật toán tìm thấy kết quả sớm và không cần chờ các branch khác hoàn tất? | `quietlyCompleteRoot`/early-completion pattern có protocol dừng và cleanup riêng. |
| Root cần trả `T` từ `invoke()`? | Override `getRawResult` và quản lý result field an toàn. |
| Parent tạo số child động? | `addToPendingCount` **trước fork**, và một self-signal/trigger cuối phù hợp. |
| Một child có thể thất bại? | Thiết kế `onExceptionalCompletion` và root failure semantics. |
| Parent cần tự nhận biết child nào báo xong? | Lưu child references/results; pending count **không** lưu identity. |

### 20.1 Khi nào không dùng CountedCompleter?

Nếu bài toán chỉ là một cây nhị phân tổng mảng đơn giản, `RecursiveTask<Long>` với `left.fork(); right.compute(); left.join();` có thể **dễ đọc và ít lỗi hơn**. CountedCompleter đáng giá khi bạn thực sự cần **continuation/callback dựa trên nhiều signals**, task tree fan-out lớn hoặc giảm join trực tiếp, chứ không phải vì tên API cao cấp.

Nếu chỉ cần chờ N independent tasks, `CountDownLatch` hoặc `CompletionService` cũng có thể đơn giản hơn tùy việc cần value/error/partial results. Đừng dựng một task tree có completer chỉ để thay một bộ đếm sự kiện rất đơn giản.

## 21. Những lỗi thường gặp

| Lỗi | Hậu quả | Sửa thế nào |
| --- | --- | --- |
| Đặt pending=2 cho hai child nhưng parent không self-signal. | Cả hai child chỉ decrement, thiếu lần kích hoạt callback. | Pending=1 cho child-only 2 signals, hoặc thêm self-signal đúng protocol. |
| Gọi `tryComplete` ở leaf trước khi ghi result. | Parent có thể đọc result chưa sẵn. | Ghi đầy đủ dữ liệu rồi mới signal. |
| Fork child trước khi tăng pending. | Child quá nhanh khiến parent complete sớm. | Đăng ký pending trước fork. |
| Thay `tryComplete` bằng `propagateCompletion` trong cây reduction. | Không còn callback để gộp child results. | Giữ tryComplete hoặc chuyển result aggregation sang protocol khác. |
| Nghĩ onCompletion chỉ chạy trên parent thread. | Race/giả định scheduling sai. | Callback phải thread-safe, không dựa vào worker identity. |
| Dùng caller cuối cùng như “thứ tự đúng” của kết quả. | Merge không giao hoán bị sai order. | Lưu left/right positions và dùng thứ tự nghiệp vụ. |
| Dùng `child.join()` trên helper internal. | Helper có thể không marked done như một root task. | Đợi root có completion protocol đúng. |
| Dùng `pending==0` làm completed flag. | Count 0 nhưng chưa có tín hiệu cuối/callback. | Dựa vào root completion qua invoke/join/get. |
| Bỏ qua exceptional completion. | Root có thể báo lỗi/chờ khó chẩn đoán. | Có failure contract và onExceptionalCompletion nếu cần. |
| `complete(T)` để bypass pending vì “đã có một child”. | Root/task complete quá sớm, thiếu dữ liệu. | Dùng tín hiệu normal hoặc early-completion contract rõ. |
| `onCompletion` gọi remote I/O/block dài. | Giữ critical path, worker bị chặn. | Callback nhẹ, postprocessing ngoài task tree. |
| Cùng child gửi signal hai lần. | Dư completion, callback sớm hoặc duplicate. | Mỗi completion path signal đúng một lần. |
| Tăng pending sau khi đã cho tín hiệu cuối qua. | Race với callback/early root completion. | Ownership cho registration và state machine rõ. |
| Kết luận sẽ có work stealing vì có CountedCompleter. | False assumption; scheduling vẫn tùy workload. | Đo bằng pool metrics nếu cần, không assert steal count. |
| Không xử lý shutdown pool do mình tạo. | Resource/lifecycle khó quản lý. | Try/finally, shutdown/awaitTermination có timeout. |

## 22. Checklist để review một lớp CountedCompleter

- [ ] Root/completer graph không có vòng và links được thiết lập đúng.
- [ ] Mỗi node xác định **bao nhiêu tín hiệu sẽ tới** (self + child).
- [ ] Pending count được đặt/tăng **trước khi** các child có thể finish.
- [ ] Với N tín hiệu theo fixed pattern, pending=N−1 hoặc một protocol chứng minh tương đương.
- [ ] Tất cả đường normal completion đều gửi đúng một tín hiệu.
- [ ] Leaf ghi result/state an toàn **trước** `tryComplete/propagateCompletion`.
- [ ] Callback không dựa vào caller identity hay worker thread ngoài những điều contract bảo đảm.
- [ ] Nếu aggregation dùng callback, leaf/internal phân biệt đúng và result field đã sẵn sàng.
- [ ] Nếu bỏ callback, `propagateCompletion` thực sự phù hợp logic nghiệp vụ.
- [ ] Result-bearing task override `getRawResult()` phù hợp.
- [ ] Error/cancel/timeout có đường thoát, tránh root chờ mãi.
- [ ] Không nhầm `child.isDone()` với completion của root.
- [ ] Không gọi `complete/quietlyCompleteRoot` để che lỗi pending count.
- [ ] Không có chờ I/O/lock dưới callback gây deadlock hoặc starvation.
- [ ] Pool lifecycle có owner, không tự shutdown common pool.
- [ ] Test với input nhỏ/lớn, nhiều lịch scheduling và failure injection.

## 23. Câu hỏi tự kiểm tra

**1.** `tryComplete()` thấy pending=3 sẽ làm gì?  
**Đáp:** Giảm pending còn 2 rồi return; chưa gọi onCompletion.

**2.** `tryComplete()` thấy pending=0 sẽ làm gì?  
**Đáp:** Gọi onCompletion(caller), sau đó tiếp tục thử completion trên completer; tại root thì đánh dấu done theo contract.

**3.** Hai child gửi đúng hai signals, parent không tự signal. Pending ban đầu bao nhiêu?  
**Đáp:** 1, vì signal đầu giảm 1→0, signal thứ hai kích hoạt callback.

**4.** Parent có hai child **và** parent gọi tryComplete sau khi sinh con. Pending ban đầu bao nhiêu?  
**Đáp:** Theo self-signal pattern là 2 cho tổng ba signals; phải đăng ký đúng trước khi fork.

**5.** Pending count bằng 0 có nghĩa root đã done chưa?  
**Đáp:** Chưa chắc. Cần tín hiệu tiếp theo tại pending 0 để kích hoạt callback/đánh dấu root completed.

**6.** `propagateCompletion` khác `tryComplete` ở đâu?  
**Đáp:** Cùng ghi nhận count và propagate, nhưng propagateCompletion bỏ qua onCompletion trên toàn đường đi.

**7.** Nếu cần merge result của child trong onCompletion, chọn method nào?  
**Đáp:** tryComplete với pending đúng và callback truy cập child results đã sẵn.

**8.** Tại sao fork child trước addToPendingCount nguy hiểm?  
**Đáp:** Child có thể hoàn tất và kích hoạt parent trước khi parent đăng ký pending, dẫn đến premature completion.

**9.** Caller của onCompletion có luôn là child bên phải không?  
**Đáp:** Không. Có thể là this hoặc child cuối; không có guarantee thứ tự.

**10.** Task helper CountedCompleter có completer thì `isDone()` có luôn true sau khi signal cha?  
**Đáp:** Không; task status của helper và việc truyền tín hiệu cho parent là hai điều khác nhau.

**11.** `getRawResult()` vì sao cần override trong CountedCompleter<Long>?  
**Đáp:** Để cung cấp result được tính/lưu vào field cho invoke/join/get; generic type không tự sinh value.

**12.** Đổi mọi tryComplete sang propagateCompletion trong ví dụ tổng sẽ in 36 không?  
**Đáp:** Không có bảo đảm: các callback gộp kết quả không chạy, nên internal result chưa được tính.

**13.** `complete(result)` có tôn trọng pending count không?  
**Đáp:** Không. Đó là unconditional completion, dùng khi thật sự muốn bypass các pending bình thường theo contract.

**14.** `quietlyCompleteRoot()` có chắc mọi child đã dừng chưa?  
**Đáp:** Không; nó có thể đánh dấu root complete sớm trong search pattern khi child khác vẫn chạy.

**15.** Khi compute ném exception, có chắc onCompletion chạy như đường bình thường không?  
**Đáp:** Không. Có đường exceptional completion và hook onExceptionalCompletion riêng.

**16.** Dùng CountedCompleter có làm mọi shared mutable map thread-safe không?  
**Đáp:** Không. Completion signaling không thay mutual exclusion/invariant protocol.

**17.** Hai leaf chạy xong gần đồng thời, có dự đoán callback trên worker nào không?  
**Đáp:** Không. Callback được kích hoạt theo đường tín hiệu cuối và scheduling runtime.

**18.** Vì sao ví dụ transform dùng propagateCompletion là hợp lý?  
**Đáp:** Mỗi leaf viết một đoạn output riêng, không có việc merge mỗi internal node; root chỉ cần biết tất cả đã xong.

**19.** Lỗi nào làm root đợi vô hạn dù mọi leaf đã chạy xong?  
**Đáp:** Ví dụ pending đặt quá cao, leaf quên signal hoặc một đường completion không lan lên parent.

**20.** Khi nào nên dùng RecursiveTask thay CountedCompleter?  
**Đáp:** Khi cây join/reduce đơn giản, logic fork/compute/join dễ hiểu hơn và không cần continuation đặc biệt.

**Ghi nhớ:** `CountedCompleter` dùng **pending signals và completer chain** để điều phối hoàn tất. `tryComplete()` giảm pending hoặc (khi bằng 0) gọi `onCompletion` rồi đi lên; `propagateCompletion()` đi lên nhưng bỏ callback; `onCompletion(caller)` là nơi hợp nhất/continuation sau khi đủ tín hiệu. Muốn chương trình đúng, phải đếm chính xác **self + child signals**, đăng ký trước fork, ghi result trước signal và chỉ dựa vào **completion của root** để xác nhận toàn cây theo đúng contract.

## Tài liệu tham khảo

- [CountedCompleter — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountedCompleter.html): tài liệu gốc về pending count, tryComplete, propagateCompletion, onCompletion, result và callback.
- [ForkJoinTask — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ForkJoinTask.html): lifecycle và các phương thức fork/invoke/join/get.
- [ForkJoinPool — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ForkJoinPool.html): scheduling và work stealing.
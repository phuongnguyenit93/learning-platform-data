# onExceptionalCompletion(): xử lý và lan truyền ngoại lệ của CountedCompleter

## 1. Tại sao CountedCompleter có callback cho ngoại lệ?

`CountedCompleter<T>` là một dạng `ForkJoinTask<T>` thuộc `java.util.concurrent`, được thiết kế cho các thuật toán chia việc theo cây và báo hoàn tất bằng **completer chain**. Mỗi task có thể liên kết với một `CountedCompleter` cha, có bộ đếm **pending** để quản lý quá trình hoàn thành bình thường. Khác với cách `RecursiveTask` thường fork rồi join từng nhánh, `CountedCompleter` có thể cho các nhánh gọi `tryComplete()` để tiếp tục tiến trình hoàn tất của cây mà không buộc cha phải join trực tiếp từng con.

Có hai luồng sự kiện khác nhau:

- **Hoàn thành bình thường**: các nhánh hoàn tất công việc và gọi `tryComplete()`; khi đủ điều kiện, `onCompletion(caller)` có thể thực thi, rồi quá trình completion đi tiếp tới completer cha.
- **Hoàn thành bất thường**: `compute()` ném exception ra ngoài hoặc task được gọi `completeExceptionally(Throwable)`. Khi đó Java sử dụng **`onExceptionalCompletion(Throwable ex, CountedCompleter<?> caller)`** để xử lý callback lỗi và quyết định lỗi có đi tiếp lên completer cha hay không.

Trong ứng dụng thực tế, failure có thể xảy ra ở một leaf nhỏ nhưng phải làm cả phép xử lý thất bại. Ngược lại, có bài toán cho phép bỏ qua một số leaf lỗi. Callback này cung cấp một **điểm điều khiển lan truyền exception**. Tuy nhiên nó không thay thế quy trình phục hồi dữ liệu, quản lý pending count, hủy các sibling hay cleanup.

**Phạm vi:** bài học sử dụng Java Concurrency/Fork/Join nói chung, không gắn với API hay vòng đời của framework khác.

## 2. Chữ ký và hợp đồng chính xác

Phương thức có chữ ký:

~~~java
@Override
public boolean onExceptionalCompletion(
        Throwable ex, CountedCompleter<?> caller) {
    // Có thể ghi nhận lỗi hoặc cập nhật trạng thái thread-safe.
    return true;
}
~~~

Đây là **đoạn minh họa nằm trong subclass**; nó cần đi cùng phần `extends CountedCompleter<...>` và một `compute()` thích hợp mới thành chương trình độc lập.

| Thành phần | Ý nghĩa |
|---|---|
| `ex` | `Throwable` của đường lỗi hiện tại; exception có thể đi qua nhiều completer |
| `caller` | Task kích hoạt callback tại mắt xích hiện tại; có thể là `this` hoặc task con |
| `this` | `CountedCompleter` đang xử lý exceptional completion |
| `return true` | Cho phép lỗi tiếp tục lan đến completer cha, **nếu cha tồn tại và chưa hoàn tất** |
| `return false` | Chặn lan exception từ mắt xích này lên completer cha |
| Triển khai mặc định | Không xử lý thêm, **trả về `true`** |

**Điểm cốt lõi:** khi callback được gọi, task hiện tại đã ở trạng thái **completed abnormally**. `return false` **không biến nó thành thành công**, không xóa exception đã xảy ra, không tự giảm pending count và không hoàn tác side effect.

Nếu `this` không có completer cha (root), return true không còn nhánh cha để lan tiếp. Nếu cha đã hoàn tất bình thường, propagation cũng không có tác dụng hồi tố thay đổi trạng thái của cha. Đừng diễn giải true là “root luôn thất bại”; điều kiện về chuỗi completer và trạng thái của từng node vẫn quan trọng.

### `caller` không phải lúc nào cũng là `this`

Tại leaf nơi `compute()` ném exception, callback có thể nhận `caller == this`. Khi exception được lan lên parent, `caller` có thể là **child đã truyền lỗi**. Vì vậy hai tham số `this` và `caller` cho phép phân biệt “node đang bị đánh dấu lỗi” và “node kích hoạt việc lan lỗi”.

Không giả định `caller` luôn là leaf ban đầu ở mọi cấp của cây; mỗi mắt xích thường nhận task ở ngay phía dưới nó. Nếu cần giữ identity lỗi gốc qua nhiều cấp, hãy quản lý metadata riêng một cách thread-safe.

## 3. Trường hợp nào kích hoạt callback?

| Trường hợp | onExceptionalCompletion được gọi? | Giải thích |
|---|---|---|
| `compute()` ném `RuntimeException` ra ngoài | Có | Task bị ghi nhận exceptional |
| `completeExceptionally(ex)` trên task chưa hoàn tất | Có | Chủ động đưa task vào nhánh lỗi |
| `compute()` bắt lỗi, dùng fallback hợp lệ, rồi `tryComplete()` | Không | Task kết thúc bình thường theo logic đã phục hồi |
| `tryComplete()` bình thường | Không | Đi theo `onCompletion()` |
| `cancel(true)` hoặc `cancel(false)` | Không kích hoạt callback lỗi như hai trường hợp đầu | Cancellation có cơ chế trạng thái riêng |
| Một task khác trong pool bị lỗi nhưng không thuộc completer chain này | Không do lỗi đó | Không có propagation qua quan hệ không tồn tại |

Hợp đồng exception của `CountedCompleter` không có nghĩa “chỉ cần có câu lệnh throw xuất hiện đâu đó”. Nếu code bắt và phục hồi hoàn toàn trước khi trả về bình thường, callback không có lý do chạy.

Ngoài ra, `ForkJoinTask` không cưỡng chế luồng nào thực thi callback tại mỗi thời điểm; đừng dựa vào thứ tự log của nhiều worker để suy luận thứ tự nguyên nhân–kết quả của các task độc lập.

## 4. Luồng lan lỗi qua cây completer

Giả sử cây ba tầng:

~~~text
                     ROOT
                       |
                    BRANCH
                       |
                      LEAF
                  compute() ném lỗi
~~~

Nếu mọi callback trả true và parent chưa hoàn tất:

1. LEAF hoàn tất bất thường; `LEAF.onExceptionalCompletion(ex, LEAF)` được gọi.
2. LEAF trả true, BRANCH được hoàn tất bất thường bởi lỗi được truyền lên; `BRANCH.onExceptionalCompletion(ex, LEAF)` được gọi.
3. BRANCH trả true, ROOT được đánh dấu bất thường nếu ROOT chưa kết thúc; callback của ROOT được gọi với `caller` là BRANCH trong đường lan truyền này.
4. Thread đợi ROOT qua `pool.invoke(root)`, `root.join()` hoặc `root.get()` có thể nhận lỗi theo hợp đồng của API tương ứng.

Nếu BRANCH trả **false**, ROOT không tự được đánh dấu exceptional bởi nhánh này. LEAF và BRANCH **vẫn thất bại**. Lỗi không được “xử lý xong” chỉ vì callback trả false.

**Lưu ý về tính đồng thời:** nếu parent đã hoàn tất trước khi exception lan tới, việc propagation không thể đổi kết quả parent sau đó. Những sibling đã fork có thể tiếp tục thực thi ngay cả khi ROOT thất bại.

### Khác nhau giữa failure propagation và normal completion

`tryComplete()` là cơ chế dùng pending count để hoàn tất **bình thường**; một exception từ child không tự gọi `tryComplete()` thay cho child đó. Do vậy khi chặn propagation bằng false, parent có thể mất cả **tín hiệu lỗi** lẫn **tín hiệu hoàn thành bình thường**. Nếu parent còn pending, một caller chờ root có thể **kẹt vô thời hạn**.

Muốn bỏ qua lỗi hợp lệ, phải thiết kế riêng cách ghi nhận kết quả thiếu, cập nhật completion accounting và đưa root tới trạng thái kết thúc rõ ràng. Không nên thay true bằng false mà không định nghĩa điều kiện kết thúc.

## 5. Ví dụ Java 17: so sánh trực tiếp true và false

Chương trình dưới đây tạo một **Parent** và một **Child** liên kết bởi `super(parent)`. Chỉ **Child được gửi vào ForkJoinPool**; Parent là đối tượng để quan sát trạng thái lan truyền. Child luôn ném `IllegalArgumentException`, callback của nó trả true hoặc false theo từng lượt thử.

Cách tổ chức này cố ý **không gửi parent vào pool**, tránh làm ví dụ tự treo khi chọn false. Trong hệ thống thật, một root có công việc và pending count của riêng nó cần chiến lược completion đầy đủ.

Lưu file **ExceptionalPropagationDemo.java**:

~~~java
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;

public class ExceptionalPropagationDemo {
    static final class Parent extends CountedCompleter<Void> {
        final AtomicBoolean hookCalled = new AtomicBoolean();
        final AtomicBoolean callerIsChild = new AtomicBoolean();
        Child child;

        @Override
        public void compute() {
            tryComplete();
        }

        @Override
        public boolean onExceptionalCompletion(
                Throwable ex, CountedCompleter<?> caller) {
            hookCalled.set(true);
            callerIsChild.set(caller == child);
            return true;
        }
    }

    static final class Child extends CountedCompleter<Void> {
        final boolean propagate;
        final AtomicBoolean childHookCalled = new AtomicBoolean();
        final AtomicBoolean callerIsSelf = new AtomicBoolean();

        Child(Parent parent, boolean propagate) {
            super(parent);
            this.propagate = propagate;
        }

        @Override
        public void compute() {
            throw new IllegalArgumentException("invalid item");
        }

        @Override
        public boolean onExceptionalCompletion(
                Throwable ex, CountedCompleter<?> caller) {
            childHookCalled.set(true);
            callerIsSelf.set(caller == this);
            return propagate;
        }
    }

    public static void main(String[] args) throws Exception {
        ForkJoinPool pool = new ForkJoinPool(2);
        try {
            for (boolean propagate : new boolean[]{true, false}) {
                Parent parent = new Parent();
                Child child = new Child(parent, propagate);
                parent.child = child;
                try {
                    pool.invoke(child);
                } catch (IllegalArgumentException expected) {
                    System.out.println("child exception="
                            + expected.getClass().getSimpleName());
                }

                if (propagate) {
                    try {
                        parent.get(2, TimeUnit.SECONDS);
                    } catch (ExecutionException expected) {
                        System.out.println("parent get="
                                + expected.getClass().getSimpleName());
                    }
                }

                System.out.println("propagate=" + propagate);
                System.out.println("child abnormal=" + child.isCompletedAbnormally());
                System.out.println("child hook called=" + child.childHookCalled.get());
                System.out.println("child caller is self=" + child.callerIsSelf.get());
                System.out.println("parent abnormal=" + parent.isCompletedAbnormally());
                System.out.println("parent hook called=" + parent.hookCalled.get());
                System.out.println("parent caller is child=" + parent.callerIsChild.get());
                System.out.println("parent done=" + parent.isDone());
            }
        } finally {
            pool.shutdown();
        }
    }
}
~~~

Biên dịch/chạy bằng JDK 17 trở lên:

~~~bash
javac ExceptionalPropagationDemo.java
java ExceptionalPropagationDemo
~~~

Kết quả:

~~~text
child exception=IllegalArgumentException
parent get=ExecutionException
propagate=true
child abnormal=true
child hook called=true
child caller is self=true
parent abnormal=true
parent hook called=true
parent caller is child=true
parent done=true
child exception=IllegalArgumentException
propagate=false
child abnormal=true
child hook called=true
child caller is self=true
parent abnormal=false
parent hook called=false
parent caller is child=false
parent done=false
~~~

**Phân tích từng nhánh:**

- **True:** child vẫn lỗi và callback child chạy; lỗi được lan tới Parent, callback Parent chạy với `caller == child`. Parent hoàn tất bất thường. Khi đợi bằng `parent.get(timeout)`, caller nhận `ExecutionException`, là wrapper checked theo API Future.
- **False:** child **vẫn** `isCompletedAbnormally() == true`, còn parent không nhận exceptional completion từ child, nên `parent.isDone() == false` trong ví dụ. Chúng ta không gọi `parent.get()` trên nhánh này.
- `pool.invoke(child)` truyền exception dạng unchecked cho caller; chuỗi thông báo/stack trace có thể khác nếu lỗi được di chuyển qua worker, nên ví dụ kiểm tra **loại exception** chứ không so sánh toàn bộ message.

**Không áp dụng máy móc Parent trong ví dụ như một tác vụ sản xuất:** `Parent.compute()` được định nghĩa để lớp hoàn chỉnh và hợp lệ nhưng không được thực thi. Bài toán thực tế phải thiết kế pending count, xử lý các child và root completion một cách nhất quán.

## 6. Ví dụ Java 17: ném lỗi, recovery, completeExceptionally và cancel

Các trường hợp sau làm rõ callback chỉ phản ánh **đường trạng thái exceptional**, không phải mọi lỗi từng xuất hiện trong thân phương thức.

Lưu file **CompletionCallbackDemo.java**:

~~~java
import java.util.concurrent.CountedCompleter;
import java.util.concurrent.ForkJoinPool;

public class CompletionCallbackDemo {
    static final class Probe extends CountedCompleter<Void> {
        private final String mode;
        private int exceptionalCalls;
        private int normalCalls;

        Probe(String mode) { this.mode = mode; }

        @Override
        public void compute() {
            if (mode.equals("throw")) {
                throw new IllegalStateException("failed");
            }
            if (mode.equals("recover")) {
                try {
                    throw new IllegalArgumentException("bad input");
                } catch (IllegalArgumentException handled) {
                    // Đã có chính sách fallback cụ thể.
                }
            }
            tryComplete();
        }

        @Override
        public void onCompletion(CountedCompleter<?> caller) {
            normalCalls++;
        }

        @Override
        public boolean onExceptionalCompletion(
                Throwable ex, CountedCompleter<?> caller) {
            exceptionalCalls++;
            return true;
        }
    }

    public static void main(String[] args) {
        ForkJoinPool pool = new ForkJoinPool(2);
        try {
            Probe throwing = new Probe("throw");
            try {
                pool.invoke(throwing);
            } catch (IllegalStateException expected) {
                System.out.println("throw: abnormal="
                        + throwing.isCompletedAbnormally()
                        + ", exceptional hook=" + throwing.exceptionalCalls);
            }

            Probe recovered = new Probe("recover");
            pool.invoke(recovered);
            System.out.println("recover: normal hook=" + recovered.normalCalls
                    + ", exceptional hook=" + recovered.exceptionalCalls);

            Probe manual = new Probe("idle");
            manual.completeExceptionally(
                    new IllegalStateException("manual"));
            System.out.println("manual: abnormal=" + manual.isCompletedAbnormally()
                    + ", exceptional hook=" + manual.exceptionalCalls);

            Probe cancelled = new Probe("idle");
            cancelled.cancel(true);
            System.out.println("cancel: cancelled=" + cancelled.isCancelled()
                    + ", exceptional hook=" + cancelled.exceptionalCalls);
        } finally {
            pool.shutdown();
        }
    }
}
~~~

Lệnh chạy:

~~~bash
javac CompletionCallbackDemo.java
java CompletionCallbackDemo
~~~

Stdout:

~~~text
throw: abnormal=true, exceptional hook=1
recover: normal hook=1, exceptional hook=0
manual: abnormal=true, exceptional hook=1
cancel: cancelled=true, exceptional hook=0
~~~

Ở `throw`, task ném lỗi và hook exceptional được gọi. Với `recover`, ví dụ cố ý bắt lỗi rồi tiếp tục `tryComplete()`, nên `onCompletion` chạy mà `onExceptionalCompletion` không chạy. Trong ứng dụng thực, chỉ làm như vậy khi **đã có fallback thực sự hợp lệ**; bắt exception rồi bỏ qua không phải cơ chế sửa lỗi dữ liệu.

Ở `manual`, `completeExceptionally` được gọi trên task chưa submit vào pool, vẫn kích hoạt đường callback lỗi. Ở `cancel`, task bị hủy theo cơ chế cancellation, không gọi hook exceptional theo ví dụ.

## 7. onCompletion và onExceptionalCompletion không thay thế nhau

| Thuộc tính | `onCompletion(caller)` | `onExceptionalCompletion(ex, caller)` |
|---|---|---|
| Đường thực thi | Hoàn tất bình thường từ cơ chế completion | Hoàn tất bất thường do lỗi |
| Vai trò | Gộp kết quả, cập nhật bước completion hợp lệ | Ghi nhận lỗi, quyết định propagation |
| Giá trị trả về | `void` | `boolean` |
| Tham số lỗi | Không có | `Throwable ex` |
| Có thể lan lên cha? | Qua cơ chế normal completion | Qua exceptional completion nếu callback trả true và cha còn đủ điều kiện |
| Tự rollback hay hủy sibling? | Không | Không |

`onCompletion` được gọi trong những trường hợp completion bình thường theo hợp đồng `tryComplete()` hoặc `complete(...)`; có thể dùng `caller` để xác định nhánh đã hoàn tất. `onExceptionalCompletion` được gọi trong nhánh lỗi và tham số `ex` cho phép biết nguyên nhân. Cả hai callback nên **ngắn, không blocking lâu, tránh ném lỗi mới không cần thiết**, vì chúng có thể chạy trong bối cảnh worker Fork/Join.

Nếu `onCompletion` ném lỗi, việc hoàn tất có thể đi vào nhánh bất thường. Do đó logic gộp kết quả trong callback bình thường cũng cần kiểm thử và quản lý exception.

## 8. Pending count và vì sao return false có thể làm root treo

`CountedCompleter` chỉ cung cấp các primitive để người lập trình thiết kế trạng thái hoàn thành:

| API | Ý nghĩa |
|---|---|
| `setPendingCount(int count)` | Đặt pending count của task |
| `addToPendingCount(int delta)` | Điều chỉnh pending count một cách nguyên tử |
| `tryComplete()` | Giảm pending khi khác 0; khi bằng 0 thì xử lý normal completion và đi tiếp trong chain |
| `onCompletion(caller)` | Callback của đường bình thường |
| `propagateCompletion()` | Lan normal completion mà không chạy `onCompletion` |
| `complete(T result)` | Hoàn tất task bằng API đặc biệt |
| `completeExceptionally(ex)` | Hoàn tất task theo đường exception |

Pending count **không phải số thread**, cũng không phải số tác vụ pool tự động duy trì. Nếu leaf bị exception trước khi `tryComplete()` và hook trả false, cha **không tự được giảm pending** và cũng **không tự bị đánh dấu exceptional**. Nếu root vẫn đợi tín hiệu từ leaf đó, `join()`, `get()` hoặc `invoke(root)` có thể chờ mãi.

**Không sửa nhanh bằng cách gọi `tryComplete()` tùy tiện trên mọi nhánh lỗi.** Một nhánh chưa cung cấp kết quả hợp lệ có thể khiến root công bố thành công thiếu dữ liệu; sibling khác cũng có thể đang chạy. Nếu nghiệp vụ chấp nhận lỗi một phần, cần có quy tắc completion rõ ràng, ví dụ lưu `Result<value,error>` ở bộ tổng hợp, cập nhật pending đúng một lần, áp điều kiện thành công tổng thể và có deadline.

Nếu không chủ định xây recovery phức tạp, giữ `return true` mặc định thường dễ suy luận hơn: thất bại của leaf được báo đến root còn đang xử lý thay vì biến thành một root pending không rõ nguyên nhân.

### Root đã hoàn tất trước khi lỗi lan đến

Một completer đã hoàn tất bình thường **không bị đổi kết quả hồi tố** bởi exception phát sinh ở child muộn. Điều này không phải bug của callback, mà phản ánh rằng thuật toán đã công bố completion trước khi chắc chắn mọi nhánh bắt buộc xong. Thiết kế pending count cần ngăn trường hợp thành công quá sớm.

## 9. Root thất bại không bảo đảm sibling ngừng chạy

Ví dụ có hai child cùng được fork. Child A ném exception, propagation thành công đánh dấu root abnormal. Child B có thể đã bắt đầu xử lý mảng hoặc vẫn còn đang chạy. **Root exceptional không tự hủy Child B**, không chờ nó dọn dẹp, không rollback side effect và không bảo đảm vùng dữ liệu chung đã an toàn để dùng lại.

Với thuật toán có side effect, cần thiết kế thêm:

1. **Tín hiệu dừng hợp tác** (ví dụ `AtomicBoolean`) để các worker khác kiểm tra tại điểm an toàn.
2. **Bộ theo dõi task còn chạy** hoặc một cơ chế báo cleanup hoàn tất, đặc biệt trước khi tái sử dụng dữ liệu.
3. **Chính sách giới hạn tài nguyên và deadline**, tránh fork liên tục sau khi đã có lỗi.
4. **Quản lý tính nhất quán**, ví dụ hoàn tác, idempotency, transaction hoặc compensation khi có side effect ngoại hệ thống.
5. **Ghi nhận lỗi có ngữ cảnh**, tránh đếm mỗi callback ở leaf/parent/root thành các lỗi nghiệp vụ độc lập.

**Callback không phải công cụ quản lý toàn bộ vòng đời của cây.** Nó chỉ quyết định một mắt xích của exception propagation. Nếu cần thu thập tất cả lỗi sibling, phải lưu các lỗi ở cấu trúc thread-safe riêng; một root có thể hoàn tất abnormal bởi lỗi đầu tiên trước khi các lỗi khác tới.

## 10. Cách xử lý lỗi ở nhiều cấp

Một thiết kế lỗi rõ ràng phân biệt ba nhóm:

**Nhóm A — Fail-fast:** bất kỳ leaf quan trọng nào lỗi đều làm toàn bộ root thất bại. Giữ `return true` và tại caller xử lý exception từ root. Nếu cần giảm lãng phí, đặt cờ stop hợp tác cho sibling và chờ cleanup theo cơ chế riêng.

**Nhóm B — Partial success có định nghĩa:** lỗi một số nhánh được phép, nhưng phải ghi nhận thiếu hụt và đánh dấu completion cho chúng theo quy ước. Cân nhắc bắt/recover exception **bên trong compute** khi có fallback hợp lệ, hoặc có một coordinator rõ ràng; `return false` chỉ là một phần nhỏ của chính sách, không phải toàn bộ.

**Nhóm C — Retry có giới hạn:** lỗi tạm thời có thể retry. Không retry vô hạn trong callback của worker. Nên giới hạn số lần, backoff, deadline và mức đồng thời, đảm bảo không tạo trùng side effect. Nếu retry thành công trong compute, task có thể hoàn thành bình thường; nếu hết retry, để lỗi thoát ra và được propagate theo chính sách.

Một số nhiệm vụ được đưa qua `ForkJoinPool.commonPool()` chia sẻ tài nguyên với các thành phần khác; tránh callback blocking hoặc retry kéo dài làm chiếm worker. Nếu cần kiểm soát ownership/lifecycle riêng, dùng `ForkJoinPool` được tạo cho thành phần đó và quản lý shutdown khi không còn task.

## 11. Xử lý Throwable, caller, exception wrapper và cancellation

**Throwable:** callback nhận `Throwable ex` và có thể quan sát nguyên nhân tại mỗi cấp. Nếu exception được truyền giữa các worker, chuỗi message hoặc stack trace hiển thị có thể khác theo cơ chế chuyển tiếp, vì vậy kiểm thử nên xác nhận loại exception/trạng thái và ngữ cảnh quan trọng, không dựa vào thứ tự log hoặc nguyên văn stack trace.

**Caller:** phân biệt task hiện tại (`this`) với task đã kích hoạt callback. Ví dụ đầu sử dụng so sánh identity để xác minh ở leaf `caller == this` và ở parent `caller == child`.

**get/join/invoke:** theo hợp đồng Future, `get()` khi task exceptional có thể ném checked `ExecutionException`; còn `join()/invoke()` thường truyền unchecked exception của công việc. Không coi exception từ root là kết quả `null` hay thành công âm thầm. Exception từ những node khác có thể bị ghi nhận độc lập trước khi lên root.

**Cancellation:** hủy task qua `cancel(true)` không phải lệnh cưỡng ép kill worker. Với ForkJoinTask, tham số interrupt không có cùng bảo đảm hủy thread như một số implementation khác; chủ sở hữu thuật toán nên đặt trạng thái hủy hợp tác. Hủy node nội bộ không tự hủy toàn cây hoặc kích hoạt callback exceptional như một lỗi compute.

**Một ngoại lệ không nhất thiết tạo callback ở mọi node:** nếu một node đã completed, nếu callback ở giữa trả false hoặc nếu completer không tồn tại, đường propagation sẽ dừng. Cần lưu vết lỗi gốc riêng nếu audit đầy đủ là yêu cầu hệ thống.

## 12. Kiểm thử lỗi và completion

| Ca kiểm thử | Kết quả cần quan sát |
|---|---|
| Leaf throw, callback true | Leaf abnormal; parent chưa completed nhận exceptional completion |
| Leaf throw, callback false | Leaf vẫn abnormal; parent không tự nhận lỗi từ leaf |
| Child fail và parent còn pending | Không để root `get()` chờ vô thời hạn khi chặn propagation |
| Parent đã done trước propagation | Không giả định exception đổi trạng thái parent |
| compute bắt lỗi và fallback | Normal completion được gọi, exceptional hook không chạy |
| completeExceptionally trên task chưa done | Callback exceptional chạy theo hợp đồng |
| cancel trên CountedCompleter | Không nhầm trạng thái cancelled với exceptional hook |
| Hai sibling cùng lỗi | Có cách thu thập/dedupe lỗi nếu nghiệp vụ yêu cầu |
| Root exceptional, sibling vẫn chạy | Cleanup và đồng bộ dữ liệu được thiết kế |
| Hook chạy trên worker | Không blocking lâu, không gây contention mới |

Khi test concurrency, ưu tiên **CountDownLatch**, timeout và trạng thái của `ForkJoinTask` thay vì chỉ `Thread.sleep()` rồi đoán thứ tự thực thi. Đặc biệt, một Future đã exceptional không bảo đảm tất cả task khác trong pool đều hoàn tất.

## 13. Lỗi thường gặp

- **Cho rằng `return false` là đã nuốt exception của child:** child vẫn abnormal, caller chờ child vẫn nhận lỗi.
- **Cho rằng `return true` luôn khiến root lỗi:** propagation chỉ tới những completer chưa hoàn tất và còn liên kết.
- **Dùng hook exceptional để gọi `tryComplete()` mà không có policy:** parent có thể báo thành công dù dữ liệu lỗi.
- **Quên pending count khi cho phép partial failure:** root có thể chờ mãi.
- **Nghĩ `caller` luôn là `this`:** mất ngữ cảnh lỗi từ task con.
- **Log cùng một exception tại mọi cấp như các lỗi khác nhau:** metrics và cảnh báo trùng.
- **Tưởng root exceptional là tất cả sibling đã bị hủy:** các nhánh khác có thể tiếp tục chạy.
- **Bắt và bỏ qua mọi exception ở compute rồi báo thành công:** dữ liệu không nhất quán.
- **Đặt I/O blocking/retry dài trong hook:** chiếm worker Fork/Join, giảm khả năng work stealing.
- **Bỏ qua `ExecutionException` từ `get()` và unchecked exception từ `join()/invoke()`:** lỗi thực tế không được báo đúng cho caller.

## 14. Checklist và kết luận

Trước khi override callback, hãy xác định **loại lỗi nào cần lan lên root**, **loại nào được phép phục hồi**, **parent còn pending gì**, **ai xử lý sibling đang chạy**, và **caller sẽ nhận thông tin thất bại theo cơ chế nào**. Một phương thức chỉ trả boolean không thể thay thế chính sách lỗi và hoàn tất cho cả cây.

**Ghi nhớ:** `onExceptionalCompletion(ex, caller)` là callback của nhánh **exceptional completion**; `return true` cho phép lan lỗi tới completer cha chưa hoàn tất, còn `return false` ngăn bước lan đó. **Cả hai không làm task thất bại trở thành thành công.** Nếu chặn propagation, phải có cơ chế hoàn tất/root cleanup có chủ đích, nếu không cây có thể kẹt chờ.

Tham khảo API chính thức: [CountedCompleter – Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountedCompleter.html).

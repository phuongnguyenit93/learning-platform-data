# Bài tập tổng hợp: Xây dựng aspect có ngữ cảnh riêng cho lời gọi đồng thời

## 1. Bối cảnh và mục tiêu

Một hệ thống Java nhận nhiều yêu cầu cùng lúc. Mỗi yêu cầu đi qua cùng một aspect để ghi nhận mã lời gọi, quan hệ cha–con và tình trạng thành công hoặc lỗi. Nếu aspect đặt thông tin của yêu cầu hiện tại vào một biến instance dùng chung, các luồng có thể ghi đè dữ liệu của nhau: yêu cầu A bất ngờ mang mã B, log liên kết sai, thông tin nội bộ rò sang lời gọi khác. Nếu lưu ngữ cảnh bằng ThreadLocal mà không xóa khi hoàn thành, một thread trong pool có thể sử dụng lại ngữ cảnh của yêu cầu trước.

**Nhiệm vụ:** xây dựng một cơ chế chặn lời gọi kiểu AOP sao cho mỗi lần vào join point có **ngữ cảnh riêng**, nhiều lời gọi đồng thời không ghi đè lên nhau, lời gọi lồng nhau có quan hệ cha–con rõ ràng, ngữ cảnh được dọn đúng cả khi phát sinh ngoại lệ. Sau đó chủ động chạy hai lời gọi đồng thời và kiểm tra các bất biến.

Bài tập dùng **AOP theo nghĩa chung**: điểm áp dụng (join point), phép chọn điểm (pointcut), advice bao quanh (around advice), context và chính sách vòng đời. Để có chương trình Java 17 tự chạy chỉ với JDK, ví dụ hiện thực hành vi chặn lời gọi bằng JDK dynamic proxy. Đây là **một cách hiện thực interception**, không phải bộ dệt bytecode tổng quát; không thể mặc định nó chặn constructor, field access, self-invocation vào target hay mọi loại join point của những công cụ AOP khác.

Sau bài học, bạn cần làm được:

1. Giải thích sự khác nhau giữa **một ngữ cảnh cho mỗi lần gọi**, **một ngữ cảnh đang hoạt động trên mỗi thread** và **một ngữ cảnh được chuyển tường minh sang tác vụ bất đồng bộ**.
2. Định nghĩa hợp đồng ngữ cảnh với định danh duy nhất, metadata cần thiết và quan hệ lời gọi cha–con.
3. Tạo around advice theo mô hình **enter → gọi target → exit trong finally**, giữ đúng kết quả và ngoại lệ.
4. Cô lập lời gọi song song; hỗ trợ lời gọi lồng nhau theo ngăn xếp, không chỉ ghi đè một giá trị ThreadLocal.
5. Chứng minh cleanup với trường hợp thành công và lỗi, gồm thread pool tái sử dụng.
6. Nhận biết giới hạn khi công việc chuyển sang một thread khác và thiết kế context propagation chủ động.
7. Tạo các test có đối chứng, kiểm tra số lần advice chạy, phạm vi pointcut, race condition và chi phí.

## 2. Kiến thức nền cần dùng

Trong một triển khai AOP:

- **Join point:** điểm thực thi có thể được mở rộng bằng advice. Tập join point được hỗ trợ tùy cơ chế AOP.
- **Pointcut:** quy tắc chọn những join point mà concern cần tác động. Không nên bắt rộng ngoài phạm vi bài.
- **Around advice:** chạy trước và sau lời gọi, có thể quản lý context, trả kết quả và chuyển ngoại lệ. Việc tiếp tục lời gọi gốc được thể hiện bằng cơ chế riêng của từng công cụ.
- **Weaving/interception:** tạo điều kiện cho advice thực sự xuất hiện trong luồng chạy; có thể thực hiện tại build/load time hoặc qua proxy ở runtime.
- **Invocation context:** dữ liệu gắn với **một lần đi vào join point**. Nếu method được gọi lại, dù cùng thread và cùng input, vẫn có một invocation riêng.
- **Execution context:** ngữ cảnh cần biết trong lúc thực hiện: correlation ID, trace/span ID, deadline, thông tin quan sát đã được giảm thiểu dữ liệu. Những giá trị này có thể cần được truyền qua các thành phần và qua ranh giới bất đồng bộ.

Điểm cốt lõi: **ThreadLocal cô lập giá trị theo thread, không tự cô lập “mỗi request” trong mọi hoàn cảnh**. Thread pool tái sử dụng thread; một request có thể chuyển qua nhiều thread; một thread cũng có thể xử lý lời gọi lồng nhau. Vì vậy, ThreadLocal chỉ là **cơ chế lưu trạng thái đang hoạt động trên thread tại thời điểm nhất định**. Hợp đồng vòng đời và truyền context mới bảo đảm ngữ nghĩa.

### 2.1. Ba phạm vi dễ nhầm

| Phạm vi | Có nghĩa gì | Ví dụ | Lưu ý |
| --- | --- | --- | --- |
| Per invocation | Mỗi lần gọi nhận một ID/scope riêng | Gọi A hai lần tạo hai invocation ID | Đây là mục tiêu chính của bài |
| Per thread | Mỗi thread có vị trí lưu trạng thái hiện hành riêng | ThreadLocal giữ đỉnh ngăn xếp context | Một thread có thể lần lượt chạy nhiều invocation |
| Per logical operation | Một công việc có thể gồm nhiều invocation và chuyển thread | Một request phát sinh hai tác vụ async | Cần propagation và quan hệ nhân quả rõ ràng |

Một lời gọi có thể có ID riêng nhưng cùng correlation ID với tác vụ cha. **Không dùng chung một đối tượng mutable** cho hai phạm vi này. Nếu cần chia sẻ metadata, dùng bản chụp (snapshot) bất biến và tạo scope mới ở từng lần tiếp tục công việc.

### 2.2. Vì sao một field dùng chung là sai?

Thiết kế nguy hiểm thường trông như sau:

```java
// Mã minh họa lỗi thiết kế; KHÔNG dùng làm aspect thật.
final class UnsafeInvocationState {
    String currentRequestId; // Một field có thể bị nhiều thread ghi cùng lúc.

    void before(String requestId) {
        currentRequestId = requestId;
    }

    String readCurrent() {
        return currentRequestId;
    }
}
```

Khi thread T1 gán A rồi nhường CPU, T2 gán B, T1 đọc lại có thể nhận B. Thêm `volatile` chỉ giúp một số thuộc tính hiển thị bộ nhớ, **không biến field thành trạng thái riêng cho từng lời gọi**. Dùng `synchronized` bao trùm toàn bộ tác vụ có thể vô tình tuần tự hóa các yêu cầu, thay đổi thông lượng và vẫn không giải quyết semantics của công việc bất đồng bộ. Sửa đúng phải bắt đầu từ **mô hình ownership của context**.

## 3. Đặc tả bài tập và tiêu chí đạt

Giả sử có một interface nghiệp vụ `Action.execute(String input)`. Cơ chế AOP cần đáp ứng hợp đồng:

| Mã | Yêu cầu | Bằng chứng đạt |
| --- | --- | --- |
| R1 | Mỗi invocation có ID duy nhất | Hai gọi đồng thời thu được hai ID khác nhau |
| R2 | Metadata của lời gọi A không trở thành metadata B | Trong target, `context.input` khớp tham số đã gọi |
| R3 | Scope được gắn trước khi vào target | Target đọc được context không-null |
| R4 | Target trả về cùng kết quả như khi không bọc, trừ metadata quan sát được quy định | Kết quả nghiệp vụ không bị sửa |
| R5 | Ngoại lệ gốc được truyền tới caller | `IllegalArgumentException` không biến thành exception phản chiếu |
| R6 | Cleanup xảy ra dù thành công hay lỗi | Sau khi thoát lời gọi, trên thread đó `current() == null` |
| R7 | Invocation lồng nhau tạo context con và khi thoát khôi phục context cha | `INNER.parentId` bằng `OUTER.id`; OUTER còn hiệu lực sau INNER |
| R8 | Có thể tái hiện và kiểm tra concurrency | Hai worker bị buộc gặp nhau trong cùng một giai đoạn bằng barrier |
| R9 | Chỉ những điểm được chọn có advice | Test một đường đi qua proxy và một đường gọi trực tiếp |
| R10 | Không để state của thread được giữ lại sau khi xong | Thread pool tái sử dụng mà không mang context cũ |

Các điều kiện R1–R8 được minh họa trực tiếp bằng chương trình hoàn chỉnh ở dưới. R9–R10 cần được mở rộng thêm bằng thử nghiệm hồi quy và môi trường triển khai cụ thể.

**Giới hạn:** không nhét toàn bộ dữ liệu yêu cầu, thông tin xác thực hoặc dữ liệu nhạy cảm vào context chỉ vì có thể lấy được từ mọi advice. Ngữ cảnh nên chứa ít thông tin nhất phục vụ concern, có thời gian sống ngắn và quy tắc truy cập rõ.

## 4. Thiết kế cấu trúc context và vòng đời

Ta chọn một đối tượng bất biến:

```java
record CallContext(long id, Long parentId, String input) {}
```

- `id`: số định danh của invocation mới, lấy từ `AtomicLong` để việc sinh ID giữa các thread không đụng nhau trong **một lần chạy tiến trình**. Đây là ID minh họa, chưa phải trace ID phân tán toàn hệ thống.
- `parentId`: null nếu là lời gọi gốc; ngược lại trỏ đến ID lời gọi đang hoạt động khi một invocation mới đi vào.
- `input`: giá trị bài tập dùng để chứng minh context không bị ghi đè; trong sản phẩm thực tế nên cân nhắc chỉ lưu dữ liệu không nhạy cảm hoặc metadata đã giảm thiểu.

Vì lời gọi có thể lồng nhau trên cùng thread, lưu ngăn xếp:

```text
Thread T1:
    [ OUTER(id=3, parent=null) ]
                 |
       INNER bắt đầu trên T1
                 v
    [ INNER(id=4, parent=3), OUTER(id=3, parent=null) ]
                 |
       INNER kết thúc, pop
                 v
    [ OUTER(id=3, parent=null) ]
                 |
       OUTER kết thúc, pop và ThreadLocal.remove()
                 v
    [ không có context ]

Thread T2:
    [ A(id=1, parent=null) ]  // độc lập với T1

Thread T3:
    [ B(id=2, parent=null) ]  // độc lập với T1 và T2
```

Đây là sơ đồ minh họa; số ID phụ thuộc thứ tự scheduler nên không được coi đây là thứ tự thực tế cố định.

Khi vào advice:

1. Đọc context hiện tại làm parent (nếu có).
2. Lấy stack riêng của thread hoặc tạo một stack mới nếu chưa có.
3. Tạo context **mới, bất biến**, push vào stack.
4. Tiếp tục lời gọi gốc **một lần**, trừ khi bài toán công khai yêu cầu semantics khác.
5. Trong `finally`, pop scope của lần gọi hiện tại; nếu stack rỗng thì `ThreadLocal.remove()`.

Khi lời gọi con kết thúc, stack vẫn chứa lời gọi cha; vì vậy chỉ xóa hẳn ThreadLocal **khi stack rỗng**. Không gọi `remove()` vô điều kiện khi trả về từ INNER vì sẽ xóa nhầm context OUTER còn sống.

Điều cần bảo toàn về thứ tự là **LIFO** (last in, first out): mỗi scope được mở sau phải đóng trước scope bên ngoài. Một thao tác cleanup không được thay đổi kết quả hoặc nuốt ngoại lệ nghiệp vụ.

## 5. Chương trình Java 17 hoàn chỉnh

Để tập trung vào tính đồng thời thay vì phụ thuộc thư viện AOP ngoài JDK, ví dụ dùng `java.lang.reflect.Proxy` chặn lời gọi qua interface `Action`. Mỗi lần chặn là một invocation scope. `ThreadLocal<Deque<CallContext>>` lưu **ngăn xếp đang hoạt động trên mỗi thread**, `AtomicLong` cấp ID duy nhất và `CyclicBarrier` làm hai lời gọi A/B cùng có mặt tại đoạn nghiệp vụ trước khi trả về.

Tạo file **ConcurrentAspectExercise.java** với toàn bộ nội dung sau:

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Proxy;
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.Set;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.AtomicReference;

public class ConcurrentAspectExercise {
    @FunctionalInterface
    interface Action { String execute(String input); }

    record CallContext(long id, Long parentId, String input) {}
    record WorkerResult(String value, boolean cleaned) {}

    private static final ThreadLocal<Deque<CallContext>> STACK = new ThreadLocal<>();
    private static final AtomicLong IDS = new AtomicLong();
    private static final AtomicLong ADVICE_RUNS = new AtomicLong();

    static CallContext current() {
        Deque<CallContext> stack = STACK.get();
        return stack == null ? null : stack.peek();
    }

    static Action withContext(Action target) {
        return (Action) Proxy.newProxyInstance(
                Action.class.getClassLoader(),
                new Class<?>[]{Action.class},
                (proxy, method, args) -> {
                    if (!method.getName().equals("execute")) {
                        try {
                            return method.invoke(target, args);
                        } catch (InvocationTargetException ex) {
                            throw ex.getCause();
                        }
                    }
                    CallContext parent = current();
                    Deque<CallContext> stack = STACK.get();
                    if (stack == null) {
                        stack = new ArrayDeque<>();
                        STACK.set(stack);
                    }
                    CallContext ctx = new CallContext(
                            IDS.incrementAndGet(),
                            parent == null ? null : parent.id(),
                            (String) args[0]);
                    stack.push(ctx);
                    ADVICE_RUNS.incrementAndGet();
                    try {
                        return method.invoke(target, args);
                    } catch (InvocationTargetException ex) {
                        throw ex.getCause();
                    } finally {
                        stack.pop();
                        if (stack.isEmpty()) STACK.remove();
                    }
                });
    }

    public static void main(String[] args) throws Exception {
        CyclicBarrier sameTime = new CyclicBarrier(2);
        Set<Long> concurrentIds = ConcurrentHashMap.newKeySet();
        AtomicReference<Action> self = new AtomicReference<>();
        AtomicBoolean nestedParentFound = new AtomicBoolean();

        Action target = input -> {
            CallContext ctx = current();
            if (ctx == null || !input.equals(ctx.input())) {
                throw new AssertionError("Context missing or wrong");
            }
            if (input.equals("FAIL")) {
                throw new IllegalArgumentException("rejected");
            }
            if (input.equals("OUTER")) {
                return "outer>" + self.get().execute("INNER");
            }
            if (input.equals("INNER")) {
                nestedParentFound.set(ctx.parentId() != null);
                return "inner";
            }
            concurrentIds.add(ctx.id());
            try {
                sameTime.await(10, TimeUnit.SECONDS);
            } catch (Exception ex) {
                throw new IllegalStateException("Workers did not overlap", ex);
            }
            return input + "#" + ctx.id();
        };

        Action observed = withContext(target);
        self.set(observed);
        ExecutorService pool = Executors.newFixedThreadPool(2);
        boolean isolated;
        try {
            Future<WorkerResult> a = pool.submit(() -> {
                String value = observed.execute("A");
                return new WorkerResult(value, current() == null);
            });
            Future<WorkerResult> b = pool.submit(() -> {
                String value = observed.execute("B");
                return new WorkerResult(value, current() == null);
            });
            WorkerResult ra = a.get(15, TimeUnit.SECONDS);
            WorkerResult rb = b.get(15, TimeUnit.SECONDS);
            isolated = ra.value().startsWith("A#")
                    && rb.value().startsWith("B#")
                    && !ra.value().equals(rb.value())
                    && concurrentIds.size() == 2
                    && ra.cleaned() && rb.cleaned();
        } finally {
            pool.shutdownNow();
        }

        String nested = observed.execute("OUTER");
        boolean nestingOk = nested.equals("outer>inner")
                && nestedParentFound.get() && current() == null;

        boolean thrown = false;
        try {
            observed.execute("FAIL");
        } catch (IllegalArgumentException ex) {
            thrown = ex.getMessage().equals("rejected");
        }

        System.out.println("Concurrent calls isolated: " + isolated);
        System.out.println("Nested context restored: " + nestingOk);
        System.out.println("Failure cleanup: " + (thrown && current() == null));
        System.out.println("Advice invocations: " + ADVICE_RUNS.get());
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 ConcurrentAspectExercise.java
java ConcurrentAspectExercise
```

**Kết quả chuẩn khi hai worker hoàn thành trong thời hạn chờ:**

```text
Concurrent calls isolated: true
Nested context restored: true
Failure cleanup: true
Advice invocations: 5
```

Mã được viết theo Java 17 và chỉ sử dụng API chuẩn của JDK. Việc dùng `javac --release 17` bảo đảm cú pháp, API nền tảng và class-file target phù hợp Java 17. Nếu môi trường quá tải khiến hai worker không gặp nhau trước timeout, chương trình sẽ báo lỗi đồng bộ thay vì in các khẳng định thành công; đó là vấn đề điều kiện chạy thử cần được đánh giá riêng.

### 5.1. Giải thích từng phần

**Một stack cho từng thread.** `STACK` là một biến `static`, nhưng giá trị liên kết với nó do `ThreadLocal` lưu riêng cho từng thread. Hai thread sẽ không cùng thao tác trên một `ArrayDeque` trong chương trình này. `ArrayDeque` không thread-safe, nhưng vẫn hợp lệ ở đây vì mỗi deque do một thread sở hữu và không được gửi sang thread khác. Nếu vô tình chia sẻ tham chiếu deque qua thread, tính an toàn đó không còn đúng.

**Một context cho từng invocation.** `IDS.incrementAndGet()` tạo ID mới bất kể thread nào đang gọi. Cùng một thread gọi A hai lần cũng phải có hai ID khác nhau. `CallContext` là `record`, giúp metadata của một invocation bất biến sau khi tạo. Không đặt `currentId` thành một field mutable trong singleton aspect.

**Quan hệ cha–con.** `parent = current()` được lấy **trước khi push** context mới. Khi OUTER gọi INNER qua chính proxy `self.get()`, INNER sẽ có parent ID của OUTER. Sau khi INNER trả về, `stack.pop()` chỉ loại phần tử INNER; OUTER vẫn ở đỉnh và cuối cùng được dọn đúng lúc OUTER kết thúc.

**Nhận diện lỗi và giữ ngoại lệ.** `Method.invoke` bọc ngoại lệ do target ném trong `InvocationTargetException`. Advice lấy `getCause()` và ném lại để caller nhận đúng `IllegalArgumentException` của target. `finally` vẫn chạy khi có ngoại lệ nên context không bị bỏ lại. Đoạn code không áp dụng retry, không nuốt lỗi và không tự thay kết quả nghiệp vụ.

**Kiểm chứng đồng thời.** Hai callable A và B chạy trên pool có hai thread. `CyclicBarrier(2)` buộc cả hai đi vào một pha trước khi chạy tiếp. Target ghi ID vào concurrent set, kết quả chứa input và ID; test kiểm tra đúng input, hai ID khác nhau và context sạch sau khi lời gọi trên thread worker đã trả về. Không in ID cụ thể, vì thứ tự cấp ID phụ thuộc scheduler và không được giả định cố định.

**Đếm advice.** Có hai invocation song song A, B; hai invocation lồng nhau OUTER, INNER; và một invocation lỗi FAIL. Tổng cộng đúng năm lần advice được thực thi. Bộ đếm `AtomicLong` dùng chung nhưng chỉ chứa **số liệu tổng hợp**, không giữ context của từng yêu cầu. Đây là khác biệt quan trọng giữa state chia sẻ có đồng bộ để quan sát và state riêng để mô tả lời gọi.

### 5.2. Vì sao không dùng `ThreadLocal.withInitial(ArrayDeque::new)`?

Cách dùng `withInitial` cũng hợp lệ nếu mọi đường đi được thiết kế và dọn đúng. Trong bài, `new ThreadLocal<>()` cho phép `current()` trả về null khi thread không có context mà không tạo một deque trống mới. Nó làm phép kiểm tra cleanup trở nên rõ ràng. Quy tắc quan trọng là **không để context còn sống sau khi scope cuối kết thúc**; không phải phải dùng chính xác một kiểu khởi tạo.

### 5.3. Điều gì xảy ra nếu bỏ `finally`?

Nếu chỉ pop ở đường thành công, lần gọi FAIL sẽ để lại một context trên thread hiện tại. Khi thread đó được tái sử dụng trong pool, lời gọi mới có thể nhận nhầm context cũ làm parent; nhật ký và phân tích nguyên nhân lỗi trở nên sai. Ngay cả khi method được gọi liên tục trên cùng thread, lỗi dọn context vẫn có thể ảnh hưởng lời gọi kế tiếp.

Nếu chỉ gọi `STACK.remove()` sau mỗi lần gọi, scope INNER sẽ xóa toàn bộ context, khiến OUTER mất trạng thái đang có. Vì vậy phải **pop một scope và chỉ remove khi deque rỗng**.

## 6. Tự chạy bộ kiểm thử bổ sung

Ví dụ đã kiểm tra các tình huống trọng tâm. Để thật sự hiểu thiết kế, bổ sung các test sau mà không đổi bản chất bài:

### Test A — nhiều lời gọi tuần tự trên một thread trong pool

Tạo `Executors.newSingleThreadExecutor()`, lần lượt submit hai tác vụ đi qua proxy. Vì cùng worker thread có thể được tái sử dụng, sau mỗi lời gọi hãy assert `current() == null` ở bên trong worker, kiểm tra ID hai invocation khác nhau và parent ID null. Đây là test trực tiếp của điều kiện không rò ngữ cảnh khi thread được tái sử dụng.

**Lưu ý:** target demo có barrier 2 parties dành riêng cho A/B. Khi thêm test một thread, tạo target khác không chờ barrier hoặc thêm một nhánh input riêng để tránh deadlock do thiếu party.

### Test B — nested invocation sâu hơn hai tầng

Cho `OUTER → MIDDLE → INNER`. Trong mỗi lời gọi, ghi lại cặp (id, parentId). Assert:

- OUTER có parentId null.
- MIDDLE có parentId là id của OUTER.
- INNER có parentId là id của MIDDLE.
- Sau INNER, đỉnh stack lại là MIDDLE; sau MIDDLE, đỉnh lại là OUTER.
- Sau OUTER, `current() == null`.

Một biến ThreadLocal chỉ giữ **một** context sẽ không tự khôi phục đúng ba tầng. Cấu trúc stack giải quyết trường hợp này.

### Test C — ngoại lệ từ lời gọi bên trong

Cho INNER ném lỗi. Nếu MIDDLE không bắt lỗi, ngoại lệ sẽ đi ngược qua MIDDLE và OUTER. Mỗi scope vẫn phải pop trong `finally`. Nếu MIDDLE bắt lỗi và tiếp tục, ngay sau khi INNER kết thúc, context của MIDDLE phải được khôi phục và vẫn hoạt động hợp lệ. Cần kiểm tra **cả trường hợp có và không có handler ở scope cha**.

### Test D — kiểm chứng đường đi qua proxy

Gọi `observed.execute(...)` rồi so với `target.execute(...)` khi target không phụ thuộc context, để xác định lời gọi trực tiếp không kích hoạt advice. Trong demo chính, target cố ý yêu cầu context nên muốn thử trực tiếp phải thay bằng một target đơn giản có thể chạy cả hai đường. Test này chỉ ra **giới hạn điểm áp dụng** của proxy: lời gọi không đi qua wrapper không được tự động instrument. Với một công cụ weaving khác, tập join point có thể khác và phải kiểm tra đúng cơ chế đó.

### Test E — stress test và race detection

Chạy hàng nghìn invocation ngắn, nhiều thread, ghi tuple (input, invocationId, threadId, parentId, outcome). Assert mỗi invocation ID là duy nhất trong lần chạy, giá trị input tại target khớp đối tượng đang thực thi, không có context còn lại khi scope kết thúc và số lần target khớp số lần được phép. Sau đó thêm lỗi ngẫu nhiên có seed cố định và kiểm tra cleanup. Bài stress test không phải bằng chứng toán học loại trừ mọi race, nhưng giúp phát hiện việc dùng nhầm state chung và hành vi không ổn định.

## 7. Mở rộng nâng cao: context qua tác vụ bất đồng bộ

`ThreadLocal` **không tự truyền context** qua `ExecutorService.submit()`. Nếu lời gọi gốc đang có context nhưng một `Callable` được chạy trên thread pool khác, thread mới có thể có context rỗng hoặc một context riêng. Điều này là đúng theo phạm vi lưu trữ thread, nhưng có thể **không đúng theo yêu cầu quan hệ nhân quả** của hệ thống.

Nếu cần liên hệ công việc async với invocation cha, nên:

1. **Chụp snapshot bất biến** của metadata được phép truyền khi còn ở trong scope gốc (ví dụ correlationId, traceId, deadline).
2. **Truyền tường minh** snapshot vào tác vụ mới hoặc thông qua thư viện propagation được thiết kế rõ ràng.
3. Khi worker bắt đầu, **mở scope mới** gắn với snapshot; tạo invocation ID mới thay vì tái sử dụng ID của lần gọi cha làm ID của lần gọi con.
4. Thực thi tác vụ và đóng scope trong `finally`, khôi phục context trước đó của worker nếu có.
5. Xác định quan hệ parent/span theo semantics: một tác vụ async có thể bắt đầu sau khi scope cha đã đóng; không được kỳ vọng còn giữ nguyên stack live của thread cha.

Ví dụ khái niệm (pseudocode, **không phải đoạn Java độc lập**):

```text
// Trong scope hiện tại:
snapshot = immutableCopyOfAllowedContextFields(current())
future = executor.submit(() -> {
    scope = openChildScopeFrom(snapshot)  // context mới trên worker
    try {
        return performAsyncWork()
    } finally {
        scope.close()                    // khôi phục context cũ của worker
    }
})
```

**Không làm**:

- Đưa trực tiếp `ArrayDeque` của ThreadLocal sang worker: nó là state có thể thay đổi và không được thiết kế chia sẻ giữa thread.
- Lấy toàn bộ object request để đưa vào thread pool vô thời hạn, vì vừa kéo dài vòng đời dữ liệu vừa tạo nguy cơ rò và race.
- Dựa vào `InheritableThreadLocal` như cơ chế propagation mặc định cho thread pool; thread trong pool thường được tạo ở thời điểm khác và tái sử dụng, nên giá trị kế thừa lúc tạo thread không phản ánh ngữ cảnh của từng task submit.
- Mặc định tác vụ đã hoàn thành chỉ vì method đã **trả về** một `Future`; phải làm rõ đo ở mốc trả Future hay mốc công việc async kết thúc.

Java 17 có thể sử dụng executor và ThreadLocal theo mô hình trên. Những cơ chế context tiên tiến khác ở các phiên bản JDK mới cần kiểm tra tài liệu runtime và chiến lược propagation tương ứng; không nên đưa đặc tính của phiên bản mới vào yêu cầu chạy Java 17.

### 7.1. Scope token và vòng đời an toàn hơn

Ở hệ thống lớn, có thể đóng gói vào một abstraction kiểu `Scope` triển khai `AutoCloseable`, cho phép:

```java
// Mã phác thảo API, chưa phải chương trình biên dịch độc lập.
try (InvocationScope scope = contextManager.open(metadata)) {
    return action.execute();
}
```

Thiết kế này có lợi khi có nhiều đường thoát. Tuy nhiên, `close()` phải bảo đảm LIFO và khôi phục context cũ, tránh đóng hai lần, tránh dùng scope từ thread khác khi cơ chế không hỗ trợ, và xử lý exception từ cleanup. Dù dùng `AutoCloseable`, việc giữ đúng vòng đời vẫn là trách nhiệm thiết kế, không tự động có được chỉ nhờ cú pháp try-with-resources.

### 7.2. Per-invocation, per-object và per-target khác nhau

Một số mô hình AOP hỗ trợ phạm vi aspect instance liên quan đến đối tượng đích, đối tượng gọi, luồng control flow hoặc những điều kiện khác. Phạm vi **aspect instance** không đương nhiên đồng nhất với **invocation context**. Một aspect instance phục vụ nhiều method call theo thời gian vẫn cần context riêng cho từng call. Trong bài, proxy `observed` là đối tượng duy nhất nhưng mỗi lần gọi có `CallContext` mới.

Trường hợp sử dụng một aspect instance riêng cho một đối tượng nghiệp vụ vẫn có thể xuất hiện hai thread cùng gọi vào đối tượng đó; do vậy không thể coi field instance là per-invocation chỉ vì target object khác nhau.

## 8. Tính đúng đắn trước các tình huống thất bại

Một implementation context được coi là đáng tin khi giữ invariant ở **mọi đường thoát**:

| Tình huống | Kỳ vọng | Sai lầm thường gặp |
| --- | --- | --- |
| Target trả về bình thường | Caller nhận đúng kết quả; stack được pop | Quên dọn, giữ request cũ |
| Target ném ngoại lệ | Caller nhận ngoại lệ gốc; stack được pop | Catch lỗi rồi trả null, hoặc bỏ qua finally |
| Advice đo thời gian/logging thất bại | Áp dụng chính sách failure đã công bố và bảo toàn ngoại lệ ưu tiên | Lỗi ghi metric che lỗi nghiệp vụ |
| Lời gọi lồng nhau | Khôi phục context cha ngay khi con kết thúc | Remove ThreadLocal ngay khi con trả về |
| Hai thread gọi đồng thời | Context không chia sẻ mutable state | Một field currentContext trên aspect instance |
| Task chuyển executor | Context được snapshot và truyền rõ ràng nếu cần | Giả định ThreadLocal “theo request” xuyên thread |
| Task bị hủy/timeout | Dọn scope ở worker khi nó thực sự kết thúc | Coi timeout ở caller đồng nghĩa worker đã dừng |
| Pointcut bị mở rộng | Join point ngoài hợp đồng không bị chặn | Wildcard quá rộng, không có negative test |

**Đặc biệt quan trọng:** trong Java, việc caller hủy một `Future` không tự bảo đảm tác vụ đã dừng; tùy khả năng hợp tác xử lý interruption và I/O. Scope trên worker phải được dọn khi đoạn thực thi trên worker thực sự thoát. Nếu một async task sống lâu, metadata giữ cùng nó cũng có thể sống lâu; cần có giới hạn thời gian và tài nguyên tương ứng.

## 9. Kiểm soát pointcut và thứ tự advice

Mẫu dynamic proxy ở ví dụ chỉ có một nhánh chặn `execute`. Trong một hệ AOP thực sự, tập join point có thể được chọn qua biểu thức điểm cắt, cấu hình, annotation hoặc cơ chế khác. Không nên bắt tất cả method của toàn ứng dụng để tiện có context, vì các lời gọi hạ tầng logging và chính cơ chế context có thể bị chặn, gây đệ quy hoặc tạo context con không mong đợi.

Trước khi triển khai, định nghĩa tập điểm áp dụng:

- Entry point nào cần tạo context **gốc**?
- Các method con nào phải dùng context cha hay mở **invocation con**?
- Đường gọi nào cố ý không có context?
- Có chặn cả code hạ tầng của advice không?
- Có lời gọi direct/self-invocation không qua proxy nhưng người dùng kỳ vọng nó được chặn không?
- Nếu nhiều advice cùng chặn, điều gì xảy ra khi context scope được đặt trước hoặc sau advice retry, đo thời gian hay transaction?

**Thứ tự có ý nghĩa.** Nếu một advice retry bao ngoài advice tạo context, mỗi attempt có thể nhận invocation ID mới; nếu advice tạo context bao ngoài retry, nhiều attempt có thể nằm trong cùng một scope. Cả hai đều có thể có lý tùy bạn định nghĩa một invocation là “yêu cầu logic” hay “một lần thực thi target”. Cần lựa chọn rõ ràng, đặc biệt khi ghi log, metric, tracing, kiểm toán và idempotency key.

Đối với bài này, một invocation được định nghĩa là **mỗi lần đi qua proxy.execute**. Lời gọi OUTER và lời gọi INNER vì đi qua proxy hai lần nên là hai invocation có quan hệ cha–con. Khi thêm retry, phải cập nhật định nghĩa hoặc thứ tự advice và bài test đếm số lần thực thi.

## 10. Thiết kế logger và telemetry không làm hỏng context

Một aspect có thể ghi sự kiện enter/exit để giải thích hệ thống; song logger cũng có giới hạn:

- **Nhận dạng:** ghi invocation ID, correlation ID phù hợp, tên thao tác đã được cho phép và trạng thái. Không mặc định log toàn bộ input, token hoặc thông tin cá nhân.
- **Phân biệt pha:** enter, success, failure, cleanup; có thể ghi thời lượng nếu có thiết kế đo đúng.
- **Tính đồng thời:** dùng cấu trúc thread-safe và exporter phù hợp, tránh danh sách dùng chung không đồng bộ.
- **Số lần sự kiện:** nested calls tạo nhiều event; xác định metric cần đếm mỗi invocation hay mỗi request. Không cộng nhầm.
- **Failure policy:** logger/external exporter hỏng có làm thất bại tác vụ không? Tùy concern và yêu cầu; cần chọn rõ trước khi viết advice.
- **Backpressure:** ghi đồng bộ mọi join point có thể tăng độ trễ và làm queue đầy; dùng sampling/batching nếu phù hợp, đồng thời theo dõi số event bị drop.
- **Cleanup:** đừng để một lỗi logger ở finally ngăn stack pop. Có thể tách việc dọn state bắt buộc khỏi thao tác xuất dữ liệu có thể thất bại.

Nếu cần log hành vi của nhiều luồng để debug, không nên dựa vào thứ tự tổng của các sự kiện để suy ra quan hệ nhân quả. Nên dùng ID, parent ID, monotonic timestamps và event boundaries, rồi dựng cây/lịch sử thực thi. Hai thread có thể xen kẽ log hợp lệ theo rất nhiều thứ tự khác nhau.

## 11. Đo hiệu năng và tài nguyên của cơ chế context

Context per invocation cũng có chi phí: cấp phát record, push/pop, phép truy cập ThreadLocal, sinh ID atomic và xuất dữ liệu quan sát. Không thể kết luận “ThreadLocal luôn rẻ” hoặc “AtomicLong chắc chắn là nút thắt” nếu chưa đo dưới tải đại diện.

Thiết kế benchmark có đối chứng:

| Biến thể | Cấu hình | Điều cần đo |
| --- | --- | --- |
| B0 | Gọi target trực tiếp, không advice | Baseline logic nghiệp vụ |
| B1 | Qua proxy nhưng advice không tạo context | Chi phí interception |
| B2 | Qua proxy, tạo/đóng context, không ghi log ngoài | Chi phí scope, allocation, atomic ID |
| B3 | Context + logging/tracing như production | Chi phí toàn bộ concern, I/O và queue |

Đo latency p50/p95/p99, throughput, CPU, allocation rate, GC và số context/advice mỗi yêu cầu. Thử cả ít thread và nhiều thread; tỷ lệ nested call cao; workload ngắn và dài; trạng thái bình thường và lỗi. Dùng cùng dữ liệu và cùng offered load, warm-up và lặp nhiều lượt. Vi mô có thể dùng công cụ benchmark chuyên dụng thay vì kết luận từ một vòng lặp `System.nanoTime()` tự viết. Đo end-to-end cũng cần máy phát tải và cấu hình runtime ổn định.

Sự khác nhau giữa cơ chế AOP được dùng cũng có thể thay đổi chi phí. Kết quả đo proxy mẫu không đại diện tuyệt đối cho weaving bytecode; chỉ suy rộng trong phạm vi đã chứng minh.

## 12. Lỗi phổ biến và cách sửa

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Một field `currentContext` chia sẻ | Lời gọi đồng thời ghi đè nhau | Lưu state theo scope, per-thread stack khi phù hợp |
| Chỉ dùng ThreadLocal một giá trị | Nested invocation mất context cha | Dùng stack hoặc scope có cơ chế lưu/khôi phục |
| Quên cleanup khi throw | Thread pool mang context của yêu cầu trước | `finally` + pop + remove khi rỗng |
| Gọi remove trong INNER | OUTER không còn context | Chỉ xóa khi scope cuối cùng kết thúc |
| Truyền trực tiếp mutable deque sang thread khác | Race, corrupt stack, leakage | Truyền snapshot bất biến, tạo scope mới tại worker |
| Cho rằng ThreadLocal đi theo Future | Task async thiếu context | Propagation có chủ đích và kiểm thử |
| Chia sẻ một ID cho mọi nested invocation | Không phân biệt mỗi call với nhóm request | Tách invocation ID và correlation/parent ID |
| Proxy không áp dụng cho self-invocation | Điểm kỳ vọng không có advice | Test đúng đường gọi; thay cơ chế/wiring nếu cần |
| Pointcut quá rộng | Advice bắt cả logger, dễ recursion | Hợp đồng pointcut và negative tests |
| Retry bên trong/ngoài scope thiếu định nghĩa | Sai quan hệ attempt/request, đếm log lệch | Chốt order và đơn vị quan sát |
| Chỉ thử lần chạy tuần tự | Không lộ ghi đè context | Barrier, nhiều thread và lặp stress |
| Chỉ assert ID không trùng | Có thể vẫn lộ input hoặc lỗi cleanup | Kiểm tra data isolation, nesting, exception, cleanup |

## 13. Nâng cấp bài tập thành một thành phần thực tế

Sau khi chương trình mẫu đạt yêu cầu, có thể refactor thành ba thành phần độc lập:

1. **`ContextManager`:** tạo ID, lưu stack, trả `current()`, mở/đóng scope và quản lý snapshot. Phần này không phụ thuộc công cụ AOP.
2. **`ContextAdvice`:** xác định enter/exit tại join point, dùng ContextManager, không nhúng logic nghiệp vụ. Bản adapter cho cơ chế AOP cụ thể có trách nhiệm gọi target và bảo toàn exceptions.
3. **`ContextPropagation`:** tạo wrapper cho executor/callback và chuyển snapshot sang task mới theo chính sách, không chia sẻ live mutable stack.

Tách như vậy giúp test context manager mà không cần weaving, test advice để xác minh mỗi join point mở đúng một scope, và test propagation ở ranh giới async. Một interface scope có thể hỗ trợ tài liệu hóa trách nhiệm cleanup và xây dựng invariant rõ ràng.

Khi đưa vào code thật, bổ sung giới hạn độ dài chuỗi metadata, chính sách bảo mật dữ liệu, định nghĩa thời điểm bắt đầu/kết thúc span, chiến lược ID đủ phạm vi hệ thống, cơ chế cancellation, hỗ trợ nested lỗi phức tạp và khả năng quan sát việc mất context.

**Không biến lời gọi async thành synchronous chỉ để ThreadLocal tiện sử dụng.** Nếu một công việc logic đi qua nhiều thread, giải pháp là mô hình propagation tường minh hoặc công cụ hỗ trợ context được kiểm chứng, không phải buộc mọi tác vụ vào một thread.

## 14. Checklist đánh giá bài hoàn thành

- [ ] Cấu trúc dữ liệu nói rõ scope: invocation ID, parent ID và metadata an toàn.
- [ ] Hai lời gọi A/B đồng thời có context riêng; không ghi đè input/ID.
- [ ] Advice thiết lập context **trước khi** target chạy.
- [ ] Advice bảo toàn return/exception của target theo hợp đồng.
- [ ] Cleanup đặt trong `finally`; không rò sau success hoặc failure.
- [ ] Lời gọi lồng nhau khôi phục context cha bằng LIFO.
- [ ] Worker thread tái sử dụng không nhận context cũ.
- [ ] Số lần target và advice đúng theo định nghĩa invocation.
- [ ] Có negative test cho đường không nằm trong pointcut.
- [ ] Có kiểm thử concurrency thực sự, không dựa vào một biến chia sẻ hoặc `sleep` như bằng chứng duy nhất.
- [ ] Hạn chế đặc trưng của proxy/weaving được giải thích chính xác.
- [ ] Với async, metadata truyền bằng snapshot, mỗi worker mở/đóng scope rõ ràng.
- [ ] Không có logger/telemetry hoặc advice khác làm phá cleanup.
- [ ] Có kế hoạch đo tác động tài nguyên nếu concern chạy ở tần suất cao.

### Câu hỏi tự kiểm tra

**1. Vì sao AtomicLong sinh ID duy nhất nhưng không thay thế ThreadLocal?** AtomicLong chỉ quản lý một bộ đếm dùng chung an toàn; nó không giữ được context riêng để target đang chạy tìm lại metadata của chính invocation đó.

**2. Vì sao một ThreadLocal chứa đúng một context vẫn sai trong lời gọi lồng nhau?** INNER sẽ ghi đè context OUTER và khi kết thúc có thể không khôi phục được OUTER. Stack hoặc scope lưu giá trị trước đó mới bảo đảm nesting.

**3. Khi nào `finally` chạy?** Khi thoát khối `try` theo đường bình thường hoặc do exception, kể cả khi exception được chuyển tiếp. Không được suy rộng thành “finally luôn chạy trong mọi hoàn cảnh” khi JVM/process bị chấm dứt cưỡng bức.

**4. Vì sao không dựa vào thứ tự ID A=1, B=2?** Các thread được scheduler chạy không theo một trật tự toàn cục có thể dự đoán. Test nên xác minh invariant: tính duy nhất, đúng input và cleanup, không cố định phân phối ID cho thread.

**5. Vì sao propagation khác với chia sẻ ngăn xếp ThreadLocal?** Propagation chuyển một **snapshot của ý nghĩa công việc** để worker tạo scope của chính nó; chia sẻ stack mutable tạo race và phá quy tắc LIFO.

**6. Nếu một advice retry gọi target ba lần, có bao nhiêu invocation?** Phụ thuộc điểm đặt scope và định nghĩa invocation. Nếu advice context mở **một lần ngoài retry**, có một scope cho yêu cầu và ba attempt. Nếu mỗi attempt đi qua join point context, có ba scope. Phải quy định và kiểm thử rõ ràng.

**7. Một lời gọi bất đồng bộ trả Future có nghĩa tác vụ gốc đã hoàn tất chưa?** Chưa chắc. Method có thể đã trả đối tượng Future trong khi tác vụ tiếp tục chạy. Cần chọn rõ scope theo lần gọi đồng bộ hay theo vòng đời công việc async.

## 15. Kết quả mong đợi

Hoàn thành bài tập nghĩa là bạn có thể giải thích và chứng minh rằng **mỗi lần gọi có context riêng**, không bị trộn giữa các luồng, hỗ trợ quan hệ cha–con cho lời gọi lồng nhau, cleanup chính xác trong mọi đường thoát và biết giới hạn của context khi công việc chuyển thread. Một thiết kế AOP tốt không chỉ làm các concern dùng chung dễ tái sử dụng; nó còn làm vòng đời và ownership của dữ liệu ngữ cảnh **có thể kiểm chứng** dưới tải đồng thời.

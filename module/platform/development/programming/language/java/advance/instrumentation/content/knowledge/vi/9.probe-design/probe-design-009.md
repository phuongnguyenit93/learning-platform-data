# Đếm lời gọi lồng nhau, đệ quy và giữ cặp sự kiện nhất quán

## 1. Tại sao bài toán khó hơn một biến đếm?

Khi instrument một phương thức Java, ta thường muốn biết **bao nhiêu lần được gọi**, **bao nhiêu lần hoàn tất**, **bao nhiêu lần thất bại** và những lời gọi đó **lồng nhau ra sao**. Chỉ tăng một bộ đếm lúc vào phương thức chưa đủ nếu cần tái dựng cây lời gọi, tính số lời gọi đang chạy hoặc tìm những sự kiện bị thất lạc.

Một ví dụ đơn giản:

~~~text
root()
  -> sumDown(2)
       -> sumDown(1)
            -> sumDown(0)
  -> fail()   // ném exception, root bắt và xử lý
~~~

Ở đây:

- `sumDown` được gọi **ba lần**, không phải một lần chỉ vì cùng tên method.
- Toàn bộ chuỗi có **năm invocation**: `root`, ba `sumDown`, một `fail`.
- `fail` thất bại nhưng `root` có thể **hoàn tất thành công** vì đã bắt exception.
- Các sự kiện `ENTER` và `EXIT` **không bắt buộc xen kẽ**: có thể gặp ba `ENTER` liên tiếp rồi mới thấy một `EXIT`.
- Nếu mỗi `ENTER` không lưu **invocation ID** riêng, không thể ghép chắc chắn các lần vào/ra của method đệ quy cùng tên.

Bài học thuộc phạm vi **thiết kế điểm đo**: định nghĩa ý nghĩa của số đếm, tạo và kết thúc ngữ cảnh từng lần gọi, xử lý nested/recursive calls, giữ cặp event ngay cả khi exception và lựa chọn cơ chế an toàn khi nhiều thread cùng chạy.

## 2. Định nghĩa các đại lượng trước khi viết instrumentation

| Đại lượng | Tăng khi nào? | Diễn giải |
| --- | --- | --- |
| `started` / `attempted` | Một invocation đi qua điểm `ENTER` thành công | Số **lần gọi**, kể cả đệ quy và lồng nhau |
| `ended` / `completed` | Invocation đi qua điểm `EXIT` đúng một lần | Số lần đã rời khỏi phạm vi quan sát |
| `success` | Invocation kết thúc bằng return bình thường | Kết quả tại chính ranh giới method đó |
| `failure` | Invocation rời khỏi method bằng exception/error được quan sát | Không nhất thiết là số **lỗi gốc** của một request |
| `active` / `inFlight` | `+1` khi bắt đầu, `-1` khi kết thúc | Số invocation đang hoạt động |
| `depth` | Độ sâu stack hiện tại khi vào | `0` cho call gốc của thread, `1` cho con trực tiếp |
| `parentId` | ID của frame phía trên lúc vào | Dùng tái dựng cây lời gọi lồng nhau |
| `invocationId` | Cấp mới cho **mỗi lần gọi** | Phân biệt các lần gọi cùng method, kể cả recursion |

**Không nhầm tên method với ID một lần gọi.** Hai invocation của `sumDown(int)` có cùng class, tên và descriptor nhưng phải có ID khác nhau. Nếu muốn tổng hợp số gọi *theo phương thức*, tạo một nhóm metric theo **method key** (ví dụ owner + name + descriptor + loại class loader khi cần); nếu muốn ghép *event*, phải dựa trên **invocation ID**.

Đếm `started` ở method entry là đếm “đã thực sự đi vào method sau điểm đo”, **không phải** số lần caller *định* gọi. Exception xảy ra trước khi tới entry hook hoặc một method bị loại khỏi phạm vi instrument sẽ không được tính. Vì vậy cần mô tả rõ **ranh giới quan sát** của dashboard.

### 2.1. Điều kiện nhất quán khi không còn invocation đang chạy

Sau khi tất cả tác vụ đã kết thúc và event không bị mất:

~~~text
started = ended
ended   = success + failure
active  = 0

Đang chạy:
started = ended + active
~~~

Ba đẳng thức là **bất biến logic khi snapshot đồng bộ và scope được bảo đảm**. Trong hệ thống nhiều thread, đọc các `LongAdder.sum()` ở các thời điểm khác nhau **không tạo snapshot nguyên tử**; do đó báo cáo giữa lúc hoạt động có thể thấy lệch tạm thời ngay cả khi code đúng. Kiểm tra số đếm chính xác sau khi tất cả task hoàn thành hoặc dùng cơ chế snapshot nhất quán hơn.

Không xem `ENTER` và `EXIT` là hai lời gọi: chúng là **hai sự kiện của cùng một invocation**. Một event `EXIT` báo kết thúc một call, không phải tạo thêm call count.

## 3. Cặp sự kiện ENTER/EXIT phải mang những gì?

Cấu trúc tối thiểu có thể biểu diễn bằng dữ liệu sau:

~~~text
ENTER {
  invocationId, parentId, methodKey, depth,
  threadId, startTime?, traceId?
}

EXIT {
  invocationId, parentId, depth,
  outcome: OK | ERROR,
  endTime?, errorType?
}
~~~

Đây là **schema minh họa**, không phải Java code. Những trường cần thiết tùy mục tiêu giám sát. Với nested/recursive calls, **invocationId** và **parentId** là quan trọng nhất; `depth` giúp kiểm tra cây lời gọi.

Quy tắc ghép cặp:

1. **Mỗi invocation được instrument có một `ENTER` và nhiều nhất một `EXIT`**, nếu chưa thoát thì đang ở trạng thái active.
2. `EXIT.invocationId == ENTER.invocationId`; **không** ghép theo tên method, thread ID hoặc thời gian.
3. Đối với lời gọi đồng bộ cùng thread, mỗi `ENTER` con gắn `parentId` bằng ID frame đang ở đỉnh stack; khi kết thúc, frame con phải rời stack **trước** frame cha (LIFO).
4. Một invocation đệ quy là **frame mới**, không ghi đè ID, start time hoặc trạng thái outcome của frame trước.
5. Khi exception đi xuyên nhiều method, mỗi method có thể có `EXIT ERROR` riêng; khi một method bắt được exception và return bình thường, chính method ấy là `OK`.
6. Không sinh `EXIT` lần nữa trong `catch` nếu đã có logic `finally` chịu trách nhiệm kết thúc.

**Một call có thể có nhiều child nhưng chỉ có một parent trực tiếp.** Với trace liên luồng qua executor, cần mang ngữ cảnh cha riêng; `ThreadLocal` tự nó không truyền tree context sang thread khác.

### 3.1. Minh họa stack của lời gọi đệ quy

~~~text
Bước                        Stack đang hoạt động (đáy -> đỉnh)
ENTER root [id=1]            [1]
ENTER sumDown(2) [id=2]      [1,2]
ENTER sumDown(1) [id=3]      [1,2,3]
ENTER sumDown(0) [id=4]      [1,2,3,4]
EXIT sumDown(0) [id=4]       [1,2,3]
EXIT sumDown(1) [id=3]       [1,2]
EXIT sumDown(2) [id=2]       [1]
ENTER fail [id=5]            [1,5]
EXIT fail ERROR [id=5]       [1]
EXIT root OK [id=1]          []
~~~

Ở đây `depth` của `root` bằng 0; ba call `sumDown` có depth lần lượt 1, 2, 3. Cách biểu diễn dùng **stack frame**, không chỉ một `ThreadLocal<Integer> depth`. Đếm depth đơn thuần không giữ được `parentId`, start time hay outcome cho từng invocation.

## 4. Thiết kế scope cho Java: begin ở entry, end trong finally

Mẫu triển khai cơ bản:

~~~java
Frame frame = begin(methodKey);
String outcome = "OK";
try {
    return callOriginalMethod();
} catch (RuntimeException | Error failure) {
    outcome = "ERROR";
    throw failure;
} finally {
    end(frame, outcome);
}
~~~

Đây chỉ là **pseudocode Java ở trong một wrapper method phù hợp**, vì `begin`, `end`, `methodKey` và `callOriginalMethod` là API do người viết instrumentation định nghĩa. Mục đích là nhấn mạnh: entry tạo frame **một lần**, outcome được ghi nhận theo cách method thực sự rời khỏi scope, và **`finally` là nơi duy nhất phát event kết thúc**.

Điểm cần nhớ:

- Nếu body `return` sớm, `finally` vẫn chạy trước khi method thực sự trả kết quả.
- Nếu body ném unchecked exception hoặc `Error`, `finally` vẫn được thực hiện trong quá trình stack unwind thông thường.
- Nếu parent bắt lỗi từ child, child kết thúc bằng `ERROR` nhưng parent có thể là `OK`.
- `finally` không có bảo đảm thực thi khi JVM/process bị kết thúc bất thường, `Runtime.halt`, máy bị mất điện hoặc một số sự cố runtime nghiêm trọng; không được tuyên bố “event luôn được gửi” trong mọi tình huống.
- `finally` gọi code instrumentation cũng có thể **ném exception**. Trong production phải thiết kế phát event theo chính sách **fail-open**, hạn chế cấp phát/log và tránh làm lỗi đo đạc che mất exception nghiệp vụ.
- Nếu dùng `Supplier<T>`, body không khai báo checked exception; `catch (RuntimeException | Error)` bao phủ các lỗi có thể thoát theo hợp đồng thông thường. Nếu dùng `Callable<T>`, phải xử lý/rethrow cả checked `Exception` đúng signature.

### 4.1. Vì sao không tăng `end` trong cả catch và finally?

Mẫu sai:

~~~java
try {
    business();
} catch (RuntimeException ex) {
    ended.increment(); // SAI: sẽ đếm hai lần nếu finally cũng tăng
    throw ex;
} finally {
    ended.increment();
}
~~~

Nếu `business()` ném lỗi, `ended` tăng **hai lần**, khiến `started < ended`. Cách đúng là catch chỉ **đánh dấu outcome**, còn `finally` tăng `ended` **một lần**.

Nếu dùng `try-with-resources` và `AutoCloseable.close()` làm exit hook, cần nhớ `close()` **không tự biết** body vừa return hay throw. Muốn phân biệt `OK`/`ERROR` phải lưu trạng thái rõ ràng trong wrapper hoặc thiết kế advice/error hook tương ứng. Không suy diễn rằng `close` được gọi vì lỗi.

## 5. Ví dụ Java 17+ chạy độc lập

Ví dụ dưới đây không cần Java agent hay thư viện ngoài JDK. Nó dùng một **wrapper tạo điểm đo** để mô phỏng chính xác luồng method-entry/method-exit mà một agent có thể tạo ra. Mục tiêu là nhìn rõ event pairing khi có **nested calls, recursion, exception và exception được parent bắt**.

**Tệp: `NestedInvocationDemo.java`**

~~~java
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.Queue;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.LongAdder;
import java.util.function.Supplier;

public final class NestedInvocationDemo {
    private static final Trace TRACE = new Trace();

    private static int sumDown(int n) {
        return TRACE.call("sumDown", () ->
                n == 0 ? 0 : n + sumDown(n - 1));
    }

    private static int root() {
        return TRACE.call("root", () -> {
            int result = sumDown(2);
            try {
                TRACE.call("fail", () -> {
                    throw new IllegalStateException("boom");
                });
            } catch (IllegalStateException expected) {
                // root da xu ly loi cua con.
            }
            return result;
        });
    }

    public static void main(String[] args) {
        int result = root();
        TRACE.events.forEach(System.out::println);
        System.out.println("result=" + result);
        System.out.println("started=" + TRACE.started.sum());
        System.out.println("ended=" + TRACE.ended.sum());
        System.out.println("ok=" + TRACE.ok.sum());
        System.out.println("error=" + TRACE.error.sum());
        System.out.println("active=" + TRACE.active.sum());
        if (TRACE.started.sum() != TRACE.ended.sum()
                || TRACE.active.sum() != 0) {
            throw new AssertionError("Unpaired calls");
        }
    }

    private record Frame(long id, long parentId, int depth, String name) {}

    private static final class Trace {
        private final AtomicLong nextId = new AtomicLong();
        private final ThreadLocal<Deque<Frame>> stack =
                ThreadLocal.withInitial(ArrayDeque::new);
        private final Queue<String> events = new ConcurrentLinkedQueue<>();
        private final LongAdder started = new LongAdder();
        private final LongAdder ended = new LongAdder();
        private final LongAdder ok = new LongAdder();
        private final LongAdder error = new LongAdder();
        private final LongAdder active = new LongAdder();

        private <T> T call(String name, Supplier<T> operation) {
            Deque<Frame> frames = stack.get();
            Frame parent = frames.peek();
            Frame current = new Frame(
                    nextId.incrementAndGet(),
                    parent == null ? 0 : parent.id(),
                    frames.size(), name);
            frames.push(current);
            started.increment();
            active.increment();
            events.add("ENTER id=" + current.id()
                    + " parent=" + current.parentId()
                    + " depth=" + current.depth()
                    + " name=" + current.name());
            String outcome = "OK";
            try {
                return operation.get();
            } catch (RuntimeException | Error failure) {
                outcome = "ERROR";
                throw failure;
            } finally {
                Frame finished = frames.pop();
                if (finished != current) {
                    throw new AssertionError("Stack order violated");
                }
                ended.increment();
                active.decrement();
                if ("OK".equals(outcome)) {
                    ok.increment();
                } else {
                    error.increment();
                }
                events.add("EXIT id=" + current.id()
                        + " parent=" + current.parentId()
                        + " depth=" + current.depth()
                        + " outcome=" + outcome);
                if (frames.isEmpty()) {
                    stack.remove();
                }
            }
        }
    }
}
~~~

Trong demo, `Frame` là **record bất biến** lưu ID, parent, depth và tên method. `Trace` có một `ThreadLocal<Deque<Frame>>`: mỗi thread nhận stack riêng. `AtomicLong` sinh ID duy nhất trong phạm vi một instance `Trace`. Các `LongAdder` thu số đếm và `ConcurrentLinkedQueue` giữ event; queue giúp lưu lại trước khi in, tránh gọi logger ngay giữa callback.

**Chi tiết quan trọng:** `AssertionError("Stack order violated")` ở cuối là **kiểm tra bất biến dành cho demo/test**. Ở agent production không nên phát sinh thêm exception từ telemetry rồi làm che exception của chương trình; khi thiết kế fail-open, tách kênh diagnostic, ghi nhận sự cố instrument và phục hồi ngữ cảnh theo chính sách an toàn. Demo giả định việc ghi event/counters nội bộ thành công.

### 5.1. Biên dịch và chạy

Với JDK 17 trở lên:

~~~bash
javac --release 17 NestedInvocationDemo.java
java NestedInvocationDemo
~~~

**Stdout chính xác** của ví dụ trên khi chạy một thread:

~~~text
ENTER id=1 parent=0 depth=0 name=root
ENTER id=2 parent=1 depth=1 name=sumDown
ENTER id=3 parent=2 depth=2 name=sumDown
ENTER id=4 parent=3 depth=3 name=sumDown
EXIT id=4 parent=3 depth=3 outcome=OK
EXIT id=3 parent=2 depth=2 outcome=OK
EXIT id=2 parent=1 depth=1 outcome=OK
ENTER id=5 parent=1 depth=1 name=fail
EXIT id=5 parent=1 depth=1 outcome=ERROR
EXIT id=1 parent=0 depth=0 outcome=OK
result=3
started=5
ended=5
ok=4
error=1
active=0
~~~

Ý nghĩa của từng dòng:

- ID 1 được cấp cho `root`; ID 2–4 là **ba invocation đệ quy** khác nhau của `sumDown`.
- `sumDown(0)` thoát trước `sumDown(1)` rồi `sumDown(2)`, tuân theo LIFO của stack đồng bộ.
- ID 5 (method `fail`) ném `IllegalStateException` nên có `EXIT ERROR`.
- `root` **bắt** exception con, tiếp tục return tổng `2 + 1 + 0 = 3`, vì thế ID 1 có `EXIT OK`.
- Có năm `ENTER`, năm `EXIT`, bốn `OK`, một `ERROR` và không còn active scope.

Đây là kết quả **đã được kiểm thử bằng lệnh `javac --release 17` và `java`**, không phải stdout giả định. Chạy song song nhiều thread sẽ cho thứ tự ID/event khác nhau; **không** lấy thứ tự toàn cục của ví dụ một thread làm hợp đồng cho trường hợp concurrent.

### 5.2. Vì sao `ThreadLocal.remove()` được gọi khi stack rỗng?

Khi một invocation ngoài cùng kết thúc, không còn frame hoạt động trên thread hiện tại. `stack.remove()` bỏ bản sao của biến ThreadLocal gắn với thread đó, giúp tránh giữ ngữ cảnh/request cũ trong thread pool sống lâu. Khi thread dùng lại `stack.get()` ở lần sau, `ThreadLocal.withInitial` có thể tạo deque mới.

Không nên gọi `remove()` sau **mỗi** nested call: nếu còn parent trong deque, xóa ThreadLocal sẽ làm mất stack cha. Chỉ xóa khi **toàn bộ stack của thread đã rỗng**.

## 6. Hai kiểu đếm khác nhau: invocation và request gốc

Giả sử một HTTP request gọi:

~~~text
request()
  -> dao.query()
  -> retry()
       -> dao.query()
       -> dao.query()
~~~

Nếu đếm **mỗi method invocation** của `dao.query` thì có ba lần. Nếu đếm **logical database operation** mà retry xử lý thì có thể chỉ có một hoặc hai thao tác cấp nghiệp vụ, tùy cách định nghĩa; nếu đếm **HTTP request** thì chỉ một. Các bộ đếm trả lời những câu hỏi khác nhau.

Vì vậy trước khi instrument cần chọn:

| Câu hỏi | Đối tượng đếm đúng |
| --- | --- |
| Method `foo` được vào bao nhiêu lần? | Mỗi `ENTER` tại method boundary |
| Bao nhiêu request hoàn tất? | Mỗi request root đã hoàn thành |
| Retry trung bình mỗi operation? | Số attempt chia số logical operations |
| Có bao nhiêu method đang chạy? | Số frame active trong phạm vi đó |
| Bao nhiêu phương thức lỗi? | Số `EXIT ERROR` của các invocation |
| Bao nhiêu lỗi nghiệp vụ độc lập? | Theo error/request ID hoặc sự kiện nguyên nhân, **không** đơn giản cộng error ở mọi tầng stack |

Khi một exception đi qua ba frame mà không được bắt, **ba `EXIT ERROR` có thể đúng** theo metric method failure. Nhưng nếu dashboard nói “ba lỗi production độc lập” từ ba event đó thì sai ngữ nghĩa. Để tổng hợp root cause, cần correlation/trace ID và chính sách khử trùng lặp.

**Đệ quy** làm lỗi đếm dễ thấy rõ: mọi lần method tự gọi chính nó vẫn là một invocation hợp lệ. Không thể dùng một flag `ThreadLocal<Boolean> insideMethod` để bỏ qua mọi lời gọi lồng nhau nếu mục tiêu là đếm **từng lần gọi**.

## 7. Phân biệt đệ quy nghiệp vụ và tái nhập do chính agent

Cần tách hai hiện tượng:

1. **Đệ quy nghiệp vụ:** `factorial(3) -> factorial(2) -> factorial(1)`. Nếu đang đo số invocation, phải đếm đủ cả ba frame.
2. **Tái nhập instrumentation:** advice/transformer gọi logger hoặc helper, rồi logger/helper lại bị chính agent instrument, dẫn đến chuỗi hook tự gọi lại vô hạn.

Sai lầm thường gặp là ngăn tự instrument bằng điều kiện “`depth > 0` thì không đo”. Điều đó loại **tất cả** method con hợp lệ và làm metric đệ quy sai.

Cách tốt hơn:

- **Loại trừ namespace agent, helper, logger, exporter và framework instrumentation** khỏi matcher của transformer.
- Với recorder/advice có nguy cơ tự tái nhập, dùng một **reentrancy guard dành riêng cho quá trình ghi event**, tách khỏi stack invocation nghiệp vụ.
- Khi guard cho biết recorder đang hoạt động, không tiếp tục instrument **mã recorder**; nhưng các method nghiệp vụ lồng nhau vẫn phải tạo frame riêng khi được phép.
- Không cấp ID, không đẩy frame khi quyết định **skip** hẳn invocation, để tránh tạo `ENTER` thiếu `EXIT`. Nếu vẫn cần duy trì parent context của đoạn skip, phải có quy tắc rõ cho “transparent scope”.

`ThreadLocal<Boolean> guard` và `ThreadLocal<Deque<Frame>> callStack` là **hai mục đích khác nhau**, không dùng một biến Boolean để thay thế cả hai.

## 8. Method entry/exit trong bytecode hoặc Java agent

Ví dụ ở mục 5 dùng wrapper để dễ chạy. Trong instrumentation bytecode thật, logic tương đương phải được chèn thành **một cặp hook**:

~~~text
METHOD_ENTRY:
    frame = recorder.begin(methodKey, currentContext)
    save frame in invocation-local state

METHOD_EXIT (normal return OR thrown exception):
    outcome = method threw ? ERROR : OK
    recorder.end(frame, outcome)
~~~

Đây là **pseudocode**, không phải cú pháp chuẩn của một thư viện. Nếu dùng Byte Buddy Advice, cần bảo đảm exit advice bao phủ cả trường hợp ném exception theo đúng tùy chọn thư viện, truyền token của entry hook sang exit hook và tránh ghi event ở nhiều nơi. Nếu dùng ASM/Class-File API, cần xử lý đường return và exceptional control flow đúng chuẩn bytecode, gồm exception table và frame verification.

### 8.1. Không chỉ chèn ở mọi `return`

Một phương thức có thể rời đi bằng:

- `return`, `ireturn`, `areturn` ... với nhiều nhánh.
- `athrow` trong method.
- Exception từ một method con hoặc instruction bất kỳ, **không có lệnh `athrow` tường minh trong method đang instrument**.
- Exception được bắt **bên trong method** rồi method return bình thường.

Chỉ thêm `EXIT` trước các opcode return **bỏ sót đường exceptional exit**. Chỉ thêm một `EXIT ERROR` ngay khi method con ném exception cũng có thể sai vì exception có thể được method cha bắt và xử lý nội bộ. Hook phải bám theo **ranh giới method** và outcome thực sự khi method rời scope.

Khi tự instrument bytecode, cách an toàn về ngữ nghĩa thường là biến đổi method body trong vùng `try/finally` tương đương (với xử lý return/exception và frames đúng). Không tự thêm đoạn catch-all tùy tiện nếu chưa hiểu verifier, synchronized methods, constructors và thứ tự initialization.

### 8.2. Token của điểm vào phải là **per-invocation**

Với đệ quy, biến global như:

~~~java
static long lastStartNanos; // SAI nếu dùng cho mọi invocation
~~~

sẽ bị lần gọi con ghi đè. Khi unwind, parent nhận start time của child, dẫn tới duration sai và event không còn ghép đúng.

Thay vào đó, token/scope phải được lưu trong local riêng của **mỗi invocation** hoặc trong `ThreadLocal<Deque<Frame>>` theo LIFO. Token chứa ít nhất `id`; khi cần đo thời gian, chứa cả `startNanos` và liên kết `parentId`. Không dùng một `ThreadLocal<Long>` duy nhất nếu có nested call mà bạn cần lưu thời điểm bắt đầu riêng.

### 8.3. Inclusive và exclusive duration

Nếu bổ sung thời gian:

~~~text
inclusiveTime(frame) = thời gian từ ENTER đến EXIT của frame
exclusiveTime(frame) = inclusiveTime(frame) - tổng thời gian child đồng bộ được tính vào frame
~~~

Các con chạy lồng nhau có thể được trừ khỏi parent bằng cách cộng `childDuration` vào frame parent **khi child kết thúc**. Đây là một phép tính khác với đếm invocation. Cẩn thận khi child chạy bất đồng bộ hoặc song song: phép trừ đơn giản có thể sai hoặc âm vì thời gian các child **chồng lấn**, nên cần định nghĩa lại cách tính.

Dùng `System.nanoTime()` cho elapsed time trong một JVM, không dùng `System.currentTimeMillis()` để suy duration ngắn. Không trộn nanoTime từ hai JVM rồi lấy hiệu vì mốc gốc của chúng không được định nghĩa chung.

## 9. Nhiều thread, executor và lời gọi bất đồng bộ

`ThreadLocal<Deque<Frame>>` có ích khi các lời gọi **đồng bộ trên cùng thread**. Nhưng nó không tự truyền parent context qua `ExecutorService`, `CompletableFuture` hoặc một callback trên thread khác.

~~~text
Thread A: HTTP request id=10
    -> submit task ------------+
                               |
Thread B:                      +-> task id=11, parentId=10
                                   -> DB call id=12, parentId=11
~~~

Nếu thread B bắt đầu với stack trống, `parentId` sẽ là 0 nếu không được truyền tường minh; tree mất liên kết. Cần **capture context** ở điểm submit, mang qua task wrapper, restore vào thread B trước khi chạy, rồi dọn/restoring context cũ trong `finally`. Một trace/correlation ID dùng chung nên phân biệt với **invocation ID** đơn lẻ.

Đừng giả định `InheritableThreadLocal` giải quyết thread pool: thread được tái sử dụng, không phải lúc nào cũng tạo mới theo request. Context có thể bị rò hoặc gán sai. Có thể dùng cơ chế context propagation của thư viện tracing hiện hành, nhưng vẫn cần hiểu contract và điểm cleanup.

### 9.1. “Method đã kết thúc” có phải async operation kết thúc?

Không nhất thiết. Với method:

~~~java
CompletableFuture<String> fetchAsync() {
    return startRemoteCall();
}
~~~

Đây là **mảnh code minh họa** giả định có `startRemoteCall()`. Method `fetchAsync` kết thúc **khi trả về future**, không phải khi remote call hoàn tất. Nếu đo *method invocation*, `EXIT` đặt ở return là đúng. Nếu muốn đo *async operation*, phải tạo **một scope logic riêng** kết thúc khi future complete/cancel/exception và ghép theo ID của operation, không giữ frame method trên stack ThreadLocal sau return.

Đồng bộ và bất đồng bộ khác nhau về vòng đời. Tránh dùng chung một bộ đếm active mà không phân biệt rõ ranh giới, vì có thể thấy `active=0` dù còn nhiều future đang chạy (đúng với metric method, sai với metric operation).

### 9.2. Event order trong hệ thống concurrent

Trong một thread đồng bộ, stack tự có thứ tự LIFO. Nhưng event của nhiều thread có thể xen kẽ:

~~~text
T1 ENTER id=100
T2 ENTER id=200
T2 EXIT  id=200
T1 EXIT  id=100
~~~

Không diễn giải đây là hai lời gọi lồng nhau chỉ vì chúng đan xen trên một stream. Phải có `threadId`, `parentId`, `traceId` và `invocationId` tương ứng. Khi gửi qua hàng đợi, mạng hoặc hệ thống phân tán, timestamp/event order còn có thể không phản ánh chính xác thời gian thực giữa các node.

## 10. Giữ nhất quán khi event có thể bị mất

Ngay cả nếu code trong một JVM luôn gọi end hook đúng, hệ thống thu thập ngoài JVM vẫn có thể bị mất một event: queue đầy, exporter timeout, process restart, network failure hoặc sampling khác nhau ở hai đầu.

Cần phân biệt ba lớp bảo đảm:

| Lớp | Câu hỏi | Cách kiểm tra |
| --- | --- | --- |
| **Method lifecycle** | Một invocation có được end hook đúng một lần không? | Unit/integration test cho normal, exception, nested, recursive |
| **Recorder/buffer** | Cả hai event có được ghi nhận nội bộ không? | Kiểm tra ID, dropped-event counters, queue/backpressure |
| **Transport/backend** | Cả hai event có tới hệ thống phân tích không? | Dedupe theo event key, reconciliation, retry có giới hạn |

**Cặp event không tự nhiên có tính nguyên tử khi phát độc lập.** Một backend có thể thấy `ENTER` mà chưa thấy `EXIT` vì invocation còn active, hoặc vì event đến trễ/mất. Không đánh đồng “open span” với “memory leak” ngay lập tức. Có thể đặt TTL và trạng thái `UNKNOWN/TIMED_OUT` cho invocation không thấy exit sau ngưỡng, thay vì tự tạo `EXIT OK` giả.

### 10.1. Sampling phải nhất quán theo invocation

Sai:

~~~text
onEnter: random() < 0.1 -> emit ENTER
onExit:  random() < 0.1 -> emit EXIT
~~~

Hai quyết định độc lập tạo `ENTER` mồ côi hoặc `EXIT` không có `ENTER`. Cách đúng là quyết định **một lần** tại entry, lưu `sampled` trên frame/token rồi dùng **cùng quyết định** tại exit. Nếu bỏ qua một invocation nhưng vẫn cần giữ cây của những child được chọn, quy ước parent “nearest recorded ancestor” hoặc virtual root phải được ghi rõ.

Với đệ quy sâu, sampling ở từng invocation có thể cắt mất một số frame. Nếu mục tiêu là tái dựng **toàn bộ một cây lời gọi**, thường cần chọn sampling nhất quán theo trace/root và cơ chế bảo đảm các đoạn được thu đều có parent hợp lệ.

### 10.2. Tránh double emission và retry trùng

Với mỗi invocation, có thể dùng `eventId = (processRunId, invocationId, phase)` để backend dedupe hai phase `ENTER`/`EXIT`. `invocationId` từ một `AtomicLong` chỉ duy nhất **trong instance recorder/process**; sau restart ID có thể xuất hiện lại. Thêm `processRunId` hoặc trace namespace nếu lưu lâu hoặc tổng hợp từ nhiều JVM.

Nếu exporter retry sau timeout, backend có thể nhận hai bản sao một `EXIT`. Dedupe theo event ID giúp giữ đúng số liệu, thay vì cộng số event nhận được mà không xét sự lặp lại.

## 11. Counter và hiệu năng khi tần suất lời gọi lớn

Demo dùng `LongAdder` vì nó có hiệu quả tốt khi nhiều thread cùng cập nhật counters. Nhưng:

- `LongAdder.sum()` **không phải atomic snapshot** nếu đang có cập nhật đồng thời; dùng sau khi quiescent hoặc hiểu sai số tạm thời.
- `AtomicLong` phù hợp tạo sequence ID monotonic trong một recorder và được dùng cho những giá trị cần atomic update; không nhất thiết dùng `AtomicLong` cho tất cả metric.
- Đừng nhồi dữ liệu của **mọi invocation** vào một `ConcurrentLinkedQueue` vô hạn như demo khi chạy production. Hệ thống thực cần buffer giới hạn, chính sách drop và exporter có backpressure.
- Nếu chỉ cần tổng lời gọi theo method, **đếm trực tiếp** có chi phí thấp hơn lưu mọi `ENTER`/`EXIT`. Nếu cần flame graph, tree, profiling hoặc duration, mới lưu frame/event theo mức sampling thích hợp.
- Metric labels nên có cardinality hữu hạn: tên method đã chuẩn hóa, outcome, service; không thêm `invocationId` vào label của metric counter vì sẽ sinh một series cho từng lần gọi.
- Java agent có thể instrument nhiều class, gồm logger/recorder của chính nó. Nên exclude các package này và bảo vệ hook trước tái nhập; nếu không, đếm sự kiện sẽ tự sinh thêm sự kiện.

### 11.1. Per-method counters và per-invocation context là hai tầng

Một hệ thống thực có thể dùng:

~~~text
methodKey -> LongAdder started/ended/success/failure (tổng hợp)
thread    -> Deque<Frame> (context đang chạy đồng bộ)
eventBus  -> ENTER/EXIT mang invocationId/parentId (nếu cần trace)
~~~

Không đặt cả ba mục tiêu vào một map chỉ theo tên method. Bản đồ thống kê theo method **không đủ** để tái dựng từng lời gọi; ngược lại mỗi invocation ID trong metric labels sẽ khiến cardinality tăng ngoài kiểm soát.

## 12. Các lỗi triển khai hay gặp

| Sai lầm | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| Chỉ có một `lastStartTime` cho mỗi thread | Child đệ quy ghi đè thời điểm của parent | Frame riêng trên stack hoặc local token theo invocation |
| Chỉ ghép theo tên method | Các frame recursion cùng tên không phân biệt | Unique `invocationId` |
| Gọi `end` trong `catch` **và** `finally` | Một lỗi tạo hai `EXIT` | Một exit duy nhất ở `finally` |
| Chèn hook ở opcode `return` mà quên exception | Method throw ra nhưng không có `EXIT` | Bao phủ normal và exceptional exit |
| Cộng error cho parent dù parent đã bắt lỗi | Sai outcome tại ranh giới parent | Xác định lỗi có thoát khỏi method không |
| Đếm mỗi recursive method đúng một lần cho một request | Sai metric method invocation | Đếm mỗi entry hoặc thiết kế metric logical request khác |
| Dùng guard `if (depth > 0) skip` | Mất nested/recursive invocation hợp lệ | Guard riêng cho self-instrumentation |
| Dùng chung một `ArrayDeque` trên nhiều thread | Race và parentId sai | `ThreadLocal<Deque<Frame>>` hoặc context quản lý đúng |
| Quên `ThreadLocal.remove` khi stack rỗng | Context có thể tồn tại qua nhiều task trong pool | Cleanup đúng sau outermost exit |
| Phát log chi tiết trong hook | Tăng overhead, có thể tái nhập recorder | Giới hạn và tách exporter ra khỏi hook |
| Lấy `LongAdder.sum` giữa lúc các thread cập nhật rồi assert equality | Các số đo không là snapshot cùng thời điểm | Assert sau quiescence hoặc chụp snapshot đồng bộ |
| Độc lập sampling ở enter/exit | Event mồ côi | Lưu sampling decision trên frame |
| Coi `CompletableFuture` return là operation complete | Duration/active của tác vụ bất đồng bộ sai | Tách method scope khỏi logical async scope |
| Coi orphan event luôn là lỗi code | Có thể do in-flight, exporter chậm hoặc loss | Kiểm tra TTL, trạng thái task, dropped-event metrics |
| Nuốt lỗi instrumentation rồi báo thành công | Che mất dữ liệu thất lạc | Fail-open rõ ràng, báo dropped/skipped event |

## 13. Checklist kiểm thử một thiết kế điểm đo

Trước khi đưa Java agent/recorder vào ứng dụng, kiểm tra ít nhất:

- [ ] **Một lời gọi thường:** một `ENTER`, một `EXIT OK`, đúng một lần tăng `started`/`ended`.
- [ ] **Nhiều return sớm:** mọi nhánh đều đóng frame một lần.
- [ ] **Method throw:** một `EXIT ERROR` và exception nghiệp vụ vẫn giữ nguyên type/stack/cause.
- [ ] **Child throw, parent bắt:** child `ERROR` nhưng parent `OK` nếu return bình thường.
- [ ] **Exception lan qua nhiều tầng:** mỗi frame thoát bằng exception có `ERROR`; phân biệt method failure với logical error.
- [ ] **Đệ quy:** mỗi lần gọi có ID khác nhau; depth tăng theo entry và giảm theo exit; parentId chính xác.
- [ ] **Sibling calls:** hai con cùng parent, không bị nhầm với nhau.
- [ ] **Nhiều thread:** không lẫn stack và parent; counter đúng sau khi task hoàn tất.
- [ ] **Thread pool reuse:** sau outermost exit, ngữ cảnh cũ được xóa.
- [ ] **Async context:** truyền trace/parent tường minh; có quy ước về thời điểm kết thúc operation.
- [ ] **Sampling/backpressure:** không tạo cặp event không nhất quán mà backend không thể giải thích; có thống kê dropped.
- [ ] **Agent self-exclusion:** không instrument lại logger, helper, exporter hoặc recorder.
- [ ] **Đường lỗi của telemetry:** policy khi recorder/exporter lỗi không làm hỏng business call.
- [ ] **Sau quiescence:** đối chiếu `started = ended`, `ended = success + failure` và `active = 0`.
- [ ] **Overhead:** benchmark CPU, allocation, GC, độ sâu stack và cardinality trước/sau bật instrumentation.

Với chương trình mẫu ở mục 5, hãy thử thay `sumDown(2)` bằng `sumDown(3)`: ta sẽ có **một invocation `sumDown` mới** cùng parent/child ID được nối đúng, chứ không phải chỉ tăng depth mà giữ nguyên số lần gọi.

## 14. Câu hỏi tự kiểm tra

1. Vì sao `sumDown(2)` ở ví dụ tạo **ba** lần gọi `sumDown`, không phải một?
2. Nếu child ném exception và parent bắt rồi trả bình thường, kết quả `EXIT` của mỗi invocation là gì?
3. Tại sao `lastStartTime` duy nhất trong một `ThreadLocal` không đủ cho method đệ quy?
4. Khi nào các đẳng thức `started=ended` và `success+failure=ended` có thể được kiểm chứng chính xác?
5. Tại sao một lời gọi `CompletableFuture` có thể có `EXIT` method trước khi tác vụ bất đồng bộ hoàn tất?
6. Nếu dispatcher chạy trên thread B, cần mang ngữ cảnh nào từ thread A để xác định `parentId`?
7. Vì sao sampling ngẫu nhiên độc lập ở entry/exit tạo cặp event sai?
8. Nếu backend nhận hai bản sao `EXIT` vì retry, có nên cộng cả hai không?
9. Tại sao loại bỏ tất cả `depth > 0` không phải cách hợp lệ để tránh tự instrument?
10. Event `EXIT` bị thiếu trong một khoảng thời gian có chắc chắn do hook không chạy không?

**Kết luận:** Đếm đúng lời gọi lồng nhau và đệ quy đòi hỏi **một frame/ID cho mỗi invocation**. Dùng `ThreadLocal<Deque<Frame>>` hoặc token local cho lời gọi đồng bộ; phát `ENTER` khi thực sự bắt đầu và bảo đảm **một `EXIT` duy nhất từ `finally`** theo outcome tại chính boundary của call. Khi mở rộng ra nhiều thread, async, sampling hoặc network, phải chủ động truyền context, giữ quyết định sampling theo frame và xử lý event đến trễ/không tới. Chỉ như vậy metric tổng hợp và cây sự kiện mới mang ý nghĩa nhất quán.

### Tài liệu tham khảo chính thức

- [Java 17 — ThreadLocal, withInitial và remove](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ThreadLocal.html)
- [Java 17 — LongAdder, sum không phải atomic snapshot](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html)
- [Java 17 — AtomicLong](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicLong.html)
- [Java 17 — java.lang.instrument và vòng đời transformer](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html)

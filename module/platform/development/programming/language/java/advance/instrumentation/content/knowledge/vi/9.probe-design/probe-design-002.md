# Ghi sự kiện bắt đầu và kết thúc một lời gọi

**Chủ đề:** Java Advance → instrumentation → **Thiết kế điểm đo**.

Một điểm đo lời gọi (*call instrumentation*) thường phát hai sự kiện: **START** khi một lời gọi bước vào vùng quan sát và **END** khi vùng ấy kết thúc. Hai sự kiện phải có đủ thông tin để **ghép đúng cùng một lần gọi**, kể cả khi phương thức bị gọi đệ quy, nhiều thread chạy đồng thời hoặc có ngoại lệ. Từ cặp sự kiện này, hệ thống có thể tính thời lượng, tỉ lệ thành công/thất bại, quan hệ cha–con và những đoạn thực thi chậm.

Thách thức không nằm ở việc đặt hai lệnh `println`. Bạn cần định nghĩa **đo chính xác ranh giới nào**, **lúc nào ghi END**, **giữ nguyên giá trị trả về và ngoại lệ**, và **làm sao để hệ thống ghi sự kiện không gây thêm lỗi hay chi phí quá lớn**.

Bài sử dụng **Java 17+** cho ví dụ chạy độc lập, sau đó liên hệ trực tiếp tới bytecode instrumentation bằng `ClassFileTransformer`/ASM. Ví dụ Java chạy được minh họa hợp đồng START/END; phần sơ đồ opcode và ASM là kỹ thuật chèn lệnh để triển khai cùng hợp đồng trên bytecode.

## 1. Thế nào là “một lời gọi”?

Xem hai phương thức:

```java
static int add(int a, int b) {
    return a + b;
}

static int total() {
    return add(2, 3) + add(4, 5);
}
```

Đây là **fragment**, chưa phải chương trình độc lập. `total()` có **hai lần gọi** `add` dù cả hai có cùng tên phương thức. Nếu ta ghi event ở lần vào/ra `add`, phải tạo **hai cặp START/END khác nhau**.

```text
time ─────────────────────────────────────────────────────────►

total():  ├───────────────────────────────────────────────────┤
add(2,3):      START #1 ───────────── END #1
add(4,5):                                  START #2 ── END #2

Events:
  START(callId=1, method=add(II)I)
  END  (callId=1, outcome=OK, elapsedNanos=...)
  START(callId=2, method=add(II)I)
  END  (callId=2, outcome=OK, elapsedNanos=...)
```

**Tên phương thức không phải ID lời gọi.** Một ID hợp lệ cần phân biệt được từng *invocation instance*; ID có thể là số tăng dần **trong một process** ở ví dụ học tập, hoặc `traceId` + `spanId` đối với hệ thống phân tán.

### 1.1. Hai cách xác định ranh giới điểm đo

| Ranh giới | Khi bắt đầu/kết thúc | Bao phủ gì? | Điểm cần nhớ |
| --- | --- | --- | --- |
| **Callee boundary** (entry/exit của method) | Bắt đầu khi method đích thực sự vào, kết thúc khi method trả về/ném exception ra ngoài | Những lần thực thi đi vào method được instrument, từ nhiều caller | Không thấy exception xảy ra **trước khi method bắt đầu**, ví dụ null receiver gây lỗi tại caller |
| **Caller / invocation site** (quanh `invoke*`) | Bắt đầu sát trước bytecode gọi, kết thúc sau kết quả hoặc exception của đúng call site | Một vị trí gọi cụ thể trong code caller; có thể bao gồm lỗi khi dispatch hoặc resolve call | Cần phân biệt thời điểm đánh giá receiver/arguments; instrument một call site không tự phủ mọi caller khác |

Ví dụ `String s = null; s.length();`: phép `invokevirtual` có thể ném `NullPointerException` tại call site; thân `String.length()` **không chạy**, nên điểm đo ở **callee** không tạo START cho lời gọi này. Điểm đo tại **caller** có thể ghi START và END(ERROR) quanh invocation.

Trong bài này, các ví dụ runnable đo ranh giới **quanh một lời gọi đồng bộ** (*call span*). Khi instrument trực tiếp method, logic tương tự được chèn vào entry, tất cả normal returns và một exception handler tổng quát. Cần chọn một ranh giới nhất quán trước khi đánh giá kết quả.

### 1.2. Những quyết định phải được ghi rõ

- **Đơn vị đo:** một lần gọi thực tế, không phải một tên method hay một dòng source.
- **Vị trí START:** trước khi chuyển quyền điều khiển cho callee hay sau khi đã vào thân method?
- **Vị trí END:** sau khi callee trả về **thành công** hoặc khi exception thoát khỏi ranh giới.
- **Trạng thái END:** ít nhất `OK` và `ERROR`; có thể thêm `CANCELLED`/`TIMEOUT` khi nghiệp vụ xác định.
- **Ngữ nghĩa thời gian:** đo wall-clock từ đầu tới cuối invocation, không tự suy ra CPU time, thời gian riêng của method, hay thời gian hoàn thành tác vụ async.
- **Lời gọi lồng nhau:** START con có thể xảy ra trước END cha; hai lần gọi cùng method vẫn cần ID riêng.
- **Điều kiện loại trừ:** những đường không bao giờ vào điểm đo (filtered method, sampling không thu thập, JVM chết trước khi end) được xử lý thế nào?

## 2. Thiết kế schema của sự kiện

Một schema tối thiểu cho observability có thể như sau:

| Trường | START | END | Lý do |
| --- | --- | --- | --- |
| `eventType` | `CALL_START` | `CALL_END` | Phân biệt hai thời điểm |
| `callId` / `spanId` | Bắt buộc | **Đúng ID đó** | Ghép một lần gọi |
| `traceId` | Nếu có trace | Giữ nguyên | Liên kết các lời gọi cùng request |
| `parentSpanId` | Nếu có parent | Có thể lược nếu START đã ghi | Dựng cây lời gọi |
| `methodId` | Owner + name + descriptor | Có thể lặp | Phân biệt overload/method trùng tên |
| `timeUtc` | Timestamp UTC để đối chiếu log | Timestamp UTC nếu cần | Liên hệ hệ thống ngoài |
| `startedNanos` / nội bộ | Lấy từ `System.nanoTime()` | Không xuất raw timestamp giữa nhiều JVM | Tính khoảng thời gian cùng JVM |
| `elapsedNanos` | Chưa có | Có | Duration chính xác của vùng đo |
| `outcome` | Chưa xác định | `OK`/`ERROR` | Đếm thành công/thất bại |
| `errorType` | Không có | Nếu `ERROR` | Kiểu exception, ví dụ `IllegalArgumentException` |
| `threadId`, process/service identity | Tùy nhu cầu | Tùy nhu cầu | Chẩn đoán đa thread/multi-process |

**Ví dụ log có tính minh họa về hình thức**, không phải output của một JDK cụ thể:

```json
{"eventType":"CALL_START","traceId":"trace-abc","spanId":"span-17",
 "parentSpanId":"span-3","methodId":"demo/Service.save(Ljava/lang/String;)V",
 "threadId":22,"timeUtc":"2026-01-01T00:00:00Z"}
{"eventType":"CALL_END","traceId":"trace-abc","spanId":"span-17",
 "outcome":"OK","elapsedNanos":187400}
```

Phân biệt **`spanId`**, **`traceId`** và **method name**: `spanId` định danh một lần gọi; `traceId` định danh cả request/trace có thể đi qua nhiều service; `methodId` chỉ định danh code được gọi. Với tracer trong một JVM, ID số tăng dần có thể dùng để demo; trong hệ thống nhiều process, cần ID/namespace đủ tránh trùng lặp.

Không đưa trực tiếp `password`, access token, dữ liệu khách hàng, toàn bộ tham số/return objects hoặc stack trace đầy đủ vào mọi sự kiện. Các trường có **cardinality cao** (ID người dùng, URL có query tùy ý, arguments) không nên biến thành nhãn metric; áp dụng chính sách bảo mật, sampling và giới hạn dữ liệu trước khi gửi đi.

## 3. Đo thời lượng đúng: đồng hồ nào?

Java có hai nhóm thời gian khác mục đích:

- `Instant.now()` hoặc đồng hồ UTC dùng cho **timestamp liên hệ với log bên ngoài**. Wall clock có thể bị điều chỉnh bởi đồng bộ giờ hoặc quản trị hệ thống.
- **`System.nanoTime()`** là nguồn thời gian độ phân giải cao dùng cho **khoảng thời gian đã trôi qua** trong **cùng JVM**. Giá trị tuyệt đối có origin tùy ý, không phải Unix timestamp, có thể âm; chỉ hiệu `end - start` là có ý nghĩa.

Mẫu chuẩn:

```java
long startNanos = System.nanoTime();
try {
    doWork();
} finally {
    long elapsedNanos = System.nanoTime() - startNanos;
    // Gửi elapsedNanos cùng CALL_END (nếu collector đáng tin).
}
```

Đây là **fragment minh họa**; `doWork()` là code của ứng dụng. `nanoTime` có độ chính xác biểu diễn nanosecond nhưng không bảo đảm cảm biến đo được từng nanosecond, và phép trừ rất xa nhau (khoảng hơn 292 năm) có thể tràn `long`. Tránh tính elapsed bằng `Instant.now().toEpochMilli()` khi cần đồng hồ đo khoảng thời gian ổn định.

**Ranh giới đo ảnh hưởng số liệu:** đặt START trước khi ghi log sync sẽ tính cả chi phí log START; đặt `startNanos` sau bước log có thể bỏ qua thời gian hook. Hãy quyết định theo mục tiêu và đo overhead bằng benchmark trước khi so latency của phương thức rất ngắn. `elapsedNanos` là **elapsed wall time** của vùng đã chọn, không phải CPU time.

## 4. Hợp đồng START/END và các đường thoát

Một lời gọi có thể kết thúc bởi:

| Đường thoát | Sự kiện cần ghi | Hành vi chương trình phải giữ |
| --- | --- | --- |
| `return` bình thường | `CALL_END(outcome=OK)` | Trả **đúng giá trị**, kể cả `null` |
| `void return` | `CALL_END(outcome=OK)` | Không tạo giá trị trả về mới |
| `throw new ...` trong method | `CALL_END(outcome=ERROR)` nếu exception **thoát ranh giới** | Ném lại đúng exception |
| Callee con ném exception không được bắt | `CALL_END(outcome=ERROR)` của method cha khi unwinding | Không biến lỗi thành success |
| Exception bị bắt và xử lý ngay trong method | `CALL_END(outcome=OK)` nếu method vẫn trả về bình thường | Không tự gắn ERROR cho một exception đã xử lý |
| Phương thức trả `CompletableFuture` chưa hoàn tất | END của **method return** là `OK` nếu trả stage thành công | Không được nhầm với END khi **tác vụ async** hoàn thành |
| JVM bị kill/abort trước END | Có thể **thiếu END** | Collector cần phát hiện span treo/mất, timeout |

**`try/finally`** là mô hình kiểm tra tốt nhất ở mức Java:

```java
long callId = onStart("methodName");
Throwable error = null;
try {
    return callOriginal();
} catch (Throwable failure) {
    error = failure;
    throw failure;
} finally {
    onEnd(callId, error);
}
```

Đoạn trên là **pseudocode theo cú pháp Java** (không độc lập): `onStart`, `callOriginal`, `onEnd` được định nghĩa theo thiết kế thực tế. `finally` chạy khi code rời block bằng `return` hoặc exception, với các ngoại lệ của cơ chế kết thúc process/JVM; nó không đảm bảo giao hàng log từ collector mất kết nối. Nếu **chính `onEnd` ném exception**, nó có thể **che khuất kết quả hoặc exception gốc** — đây là lỗi instrumentation nghiêm trọng cần kiểm soát ở mức sink.

Một điểm quan trọng khác: **thời điểm ghi END** phải thống nhất. Nếu END được gọi trước thực tế khi return value/exception đã xác định, reporter không nên ghi trạng thái thành công trước khi vùng đo còn khả năng thất bại.

## 5. Ví dụ Java 17+ chạy được: cặp START/END cho nested call và exception

Ví dụ đầu tiên là một bộ đo bao quanh code bằng Java thông thường. Nó chưa sửa bytecode, nhưng mô tả chính xác **hợp đồng sự kiện** mà bytecode instrumentation cần tạo ra. Có ID riêng cho từng invocation, quan hệ parent/child, duration bằng `nanoTime`, cleanup `ThreadLocal` và ghi ERROR mà vẫn ném lại exception.

Lưu **`TraceCallsDemo.java`**:

```java
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.Queue;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.atomic.AtomicLong;

public final class TraceCallsDemo {
    private TraceCallsDemo() {}

    private record Frame(
            long id, long parentId, String method, long startedNanos) {}
    private record Completed(
            long id, String status, long elapsedNanos, String errorType) {}

    private static final AtomicLong NEXT_ID = new AtomicLong();
    private static final ThreadLocal<Deque<Frame>> STACK =
            ThreadLocal.withInitial(ArrayDeque::new);
    private static final Queue<Completed> HISTORY =
            new ConcurrentLinkedQueue<>();

    @FunctionalInterface
    interface Work<T> {
        T run() throws Throwable;
    }

    static <T> T traced(String method, Work<T> work) throws Throwable {
        Deque<Frame> frames = STACK.get();
        Frame parent = frames.peek();

        Frame current = new Frame(
                NEXT_ID.incrementAndGet(),
                parent == null ? 0 : parent.id(),
                method,
                System.nanoTime());
        frames.push(current);

        System.out.println("START id=" + current.id()
                + " parent=" + current.parentId()
                + " method=" + current.method());

        String status = "OK";
        String errorType = null;
        try {
            return work.run();
        } catch (Throwable failure) {
            status = "ERROR";
            errorType = failure.getClass().getSimpleName();
            throw failure;
        } finally {
            long elapsedNanos = System.nanoTime() - current.startedNanos();
            frames.pop();
            if (frames.isEmpty()) {
                STACK.remove();
            }
            HISTORY.add(new Completed(
                    current.id(), status, elapsedNanos, errorType));
            System.out.println("END id=" + current.id()
                    + " status=" + status);
        }
    }

    public static void main(String[] args) throws Throwable {
        int answer = traced("outer", () ->
                traced("inner", () -> 5) + 3);
        System.out.println("RESULT=" + answer);

        try {
            traced("fail", () -> {
                throw new IllegalArgumentException("bad");
            });
        } catch (IllegalArgumentException e) {
            System.out.println("CAUGHT=" + e.getMessage());
        }

        System.out.println("COMPLETED=" + HISTORY.size());
    }
}
```

Chạy bằng JDK 17 trở lên:

```bash
javac TraceCallsDemo.java
java TraceCallsDemo
```

**Stdout chính xác trong ví dụ chạy tuần tự này** (duration được lưu vào `HISTORY`, không in giá trị thay đổi theo máy):

```text
START id=1 parent=0 method=outer
START id=2 parent=1 method=inner
END id=2 status=OK
END id=1 status=OK
RESULT=8
START id=3 parent=0 method=fail
END id=3 status=ERROR
CAUGHT=bad
COMPLETED=3
```

**Đọc kết quả:**

1. `outer` bắt đầu với `id=1`, không có parent nên `parent=0` trong **quy ước của demo**.
2. `inner` chạy trong `outer` nên có `id=2, parent=1`. `END 2` xảy ra **trước `END 1`** vì stack lồng nhau.
3. `RESULT=8` chứng minh wrapper trả nguyên kết quả `5+3` và không đổi logic tính toán.
4. `fail` có `id=3`, END ghi `ERROR` rồi exception **vẫn truyền** tới catch trong `main`, tạo `CAUGHT=bad`.
5. `COMPLETED=3` chứng minh ba lần gọi đều được ghi nhận. `HISTORY` lưu cả `elapsedNanos` và `errorType`; demo không hiển thị duration nên output ổn định.

**Giới hạn của ví dụ:** `System.out.println` là sink đồng bộ phục vụ học tập. Nếu logger bị lỗi trong START/END, demo chưa thực hiện chính sách fail-open để không ảnh hưởng ứng dụng. `AtomicLong` đảm bảo ID khác nhau trong một process đang chạy, **không** đảm bảo duy nhất qua nhiều process/restart. `ThreadLocal` chỉ tự động giữ quan hệ parent khi các lời gọi ở cùng thread; không được tự coi nó là distributed trace context.

### 5.1. Vì sao phải dọn `ThreadLocal`?

Nếu dùng worker threads từ thread pool, thread có thể xử lý nhiều request nối tiếp. Giữ lại stack/trace context của request cũ sẽ gây ghép nhầm parent ở request sau và giữ tham chiếu không cần thiết.

Trong demo, `frames.pop()` cân bằng `frames.push(current)` và `STACK.remove()` khi stack rỗng. Đây là nguyên tắc sử dụng `ThreadLocal` ở **đúng ranh giới lifecycle**. Với asynchronous callbacks, virtual threads, `Executor` hoặc reactive streams, context cần được truyền/khôi phục rõ ràng, không phụ thuộc ngầm vào thread mà callback cuối cùng chạy.

## 6. Ví dụ Java 17+ thứ hai: ghi sự kiện tự động quanh lời gọi qua interface

Để thấy có thể đo mà **không sửa thân phương thức đích**, ví dụ tiếp dùng **JDK Dynamic Proxy** cho một interface. Proxy chỉ ghi những lời gọi đi **qua proxy**, không instrument toàn bộ JVM và không đo những lệnh `this.otherMethod()` trong implementation nếu chúng bỏ qua proxy.

Lưu **`ProxyEventsDemo.java`**:

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Proxy;
import java.util.concurrent.atomic.AtomicLong;

public final class ProxyEventsDemo {
    private ProxyEventsDemo() {}

    public interface Calculator {
        int add(int a, int b);
        void fail();
    }

    public static final class CalculatorImpl implements Calculator {
        public int add(int a, int b) {
            return a + b;
        }

        public void fail() {
            throw new IllegalStateException("stop");
        }
    }

    private static final AtomicLong IDS = new AtomicLong();

    public static void main(String[] args) {
        Calculator target = new CalculatorImpl();

        Calculator proxy = (Calculator) Proxy.newProxyInstance(
                Calculator.class.getClassLoader(),
                new Class<?>[] {Calculator.class},
                (proxyObject, method, arguments) -> {
                    long id = IDS.incrementAndGet();
                    String status = "OK";
                    System.out.println("START id=" + id
                            + " method=" + method.getName());

                    try {
                        return method.invoke(target, arguments);
                    } catch (InvocationTargetException failure) {
                        status = "ERROR";
                        throw failure.getCause();
                    } catch (ReflectiveOperationException failure) {
                        status = "ERROR";
                        throw new IllegalStateException(failure);
                    } finally {
                        System.out.println("END id=" + id
                                + " status=" + status);
                    }
                });

        System.out.println("VALUE=" + proxy.add(2, 3));
        try {
            proxy.fail();
        } catch (IllegalStateException e) {
            System.out.println("CAUGHT=" + e.getMessage());
        }
    }
}
```

Lệnh:

```bash
javac ProxyEventsDemo.java
java ProxyEventsDemo
```

Stdout:

```text
START id=1 method=add
END id=1 status=OK
VALUE=5
START id=2 method=fail
END id=2 status=ERROR
CAUGHT=stop
```

Ở đây `Method.invoke` bọc exception từ target vào `InvocationTargetException`; handler lấy lại **`getCause()`** rồi ném tiếp để caller vẫn thấy `IllegalStateException("stop")`. `finally` phát đúng một END cho hai đường ở ví dụ.

**Ranh giới:** Dynamic Proxy áp dụng cho **interfaces mà lời gọi đi qua proxy**. Nó không tự động intercept mọi phương thức `private`/`static`, constructor hoặc self-invocation trên đối tượng thực. Khi muốn đo tất cả các lần vào một method bất kể caller, phải chọn điểm đo **bytecode entry/exit** hoặc cơ chế instrumentation tương ứng.

## 7. Từ Java `try/finally` sang bytecode instrumentation

Một `ClassFileTransformer` sửa định nghĩa `.class` lúc load/retransform; ASM hoặc Class-File API có thể hỗ trợ chèn các lệnh quanh phương thức/call site. Transformer phải **đọc input `classfileBuffer` mà không sửa tại chỗ**, và trả về mảng class file mới hợp lệ nếu có transform.

Trong JVM, lời gọi tới phương thức có thể dùng opcode như:

- `invokevirtual`: instance method có virtual dispatch.
- `invokeinterface`: gọi qua interface.
- `invokestatic`: static method.
- `invokespecial`: các lời gọi đặc biệt, gồm constructor và một số phương thức private/super.
- `invokedynamic`: call site động (lambda metafactory, string concatenation và các cơ chế liên quan); không giống `invokevirtual` thông thường.

Với method-level instrumentation, **entry** có thể là điểm ngay sau prologue mà thư viện chèn tạo ra; **normal exit** xảy ra trước các lệnh:

| Return opcode | Giá trị trên operand stack trước return | Yêu cầu khi chèn END |
| --- | --- | --- |
| `ireturn` | `int` (cả boolean/byte/char/short ở bytecode) | Còn nguyên một `int` sau khi gọi hook |
| `lreturn` | `long` (category 2) | Giữ nguyên một `long`; nếu copy bằng opcode thì cần thao tác category 2 như `dup2` |
| `freturn` | `float` | Giữ nguyên `float` |
| `dreturn` | `double` (category 2) | Giữ nguyên `double` |
| `areturn` | reference | Giữ nguyên reference, kể cả `null` |
| `return` | Không có return value | Hook không được đòi một return operand |

**Không được** làm mất giá trị trả về. Ví dụ trước `ireturn`, operand stack có `[result:int]`:

```text
...                           stack = [result]
getstatic System.out          stack = [result, out]
ldc "END"                     stack = [result, out, "END"]
invokevirtual println(String) stack = [result]
ireturn                       trả result cho caller
```

Đây là **sơ đồ bytecode**, không phải chương trình Java độc lập; `getstatic`/`invokevirtual` trong class file thật cần owner/name/descriptor và constant-pool references chính xác. Hook `println(String)` tiêu thụ `out` và `"END"` nên `result` vẫn ở đúng vị trí. Với logger tiêu thụ chính kết quả, cần `dup`/`dup2` hoặc lưu giá trị vào local tạm rồi nạp lại. Điều tương tự áp dụng cho `lreturn`/`dreturn` và mọi return opcode.

Đối với **caller-site instrumentation**, trước `invoke*` có thể đã có receiver/arguments trên operand stack. Chèn lệnh logger mà làm thay đổi thứ tự đó có thể làm class bị verifier từ chối hoặc gọi sai method. Sau `invoke*`, giữ nguyên kết quả return trên stack khi phát END. Trong trường hợp exception, điểm END(ERROR) phải được thực thi qua đường unwind.

## 8. Vì sao chèn tại từng `return` và `athrow` vẫn chưa đủ?

ASM cung cấp `org.objectweb.asm.commons.AdviceAdapter` với:

- `onMethodEnter()` để sinh mã khi bắt đầu method (ở constructor, callback được trì hoãn tới sau lời gọi constructor cha/thích hợp).
- `onMethodExit(int opcode)` để sinh mã **trước các lệnh exit tường minh**: sáu nhóm `return` và `ATHROW`.

Điểm dễ mắc lỗi: **`onMethodExit(ATHROW)` không tự động bắt tất cả exception ngầm xảy ra trong quá trình chạy**, ví dụ:

```java
static int parseNumber(String s) {
    return Integer.parseInt(s);
}
```

Đây là **fragment**. Nếu `Integer.parseInt(s)` ném `NumberFormatException` rồi exception đi thẳng ra khỏi `parseNumber`, bytecode của `parseNumber` có thể **không có opcode `athrow`** tại đường thoát ấy. Nó chỉ có `invokestatic parseInt` rồi `ireturn` trên đường bình thường. Vì thế AdviceAdapter chỉ chèn “exit before return/ATHROW” có thể **mất sự kiện END(ERROR)** cho lời gọi này.

Để quan sát *mọi exception thoát khỏi vùng* theo ngữ nghĩa Java, một thiết kế bytecode thông dụng là thêm **catch-all exception handler** quanh thân được đo, rồi rethrow:

```text
on method entry:
    callId = Trace.start(methodId)
tryStart:
    <các lệnh gốc của method>
    ... mỗi normal return:
        Trace.end(callId, OK)
        return originalValue
tryEnd:
catch (Throwable t):
    Trace.end(callId, ERROR, typeOf(t))
    throw t
```

**Đây là pseudocode thuật toán ASM**, không phải Java source hoặc bytecode assembly độc lập. Cần bảo đảm try region bắt đầu **sau START thành công**, bao phủ vùng cần đo, có label boundary chính xác và handler không tự nằm trong vùng catch của nó. Sử dụng một phương án END(ERROR) duy nhất cho cùng exception: nếu vừa gọi `onMethodExit(ATHROW)` để ghi END(ERROR) **và** catch-all handler cũng ghi END(ERROR), một exception có thể tạo **hai END**.

Các exception bị handler **nội bộ** bắt và xử lý trước khi method trả về bình thường nên cuối cùng được ghi `OK`. Nếu chỉ muốn đếm mọi exception *phát sinh*, đó là loại event khác (`EXCEPTION_THROWN`) và không được đánh đồng với tình trạng thất bại của invocation.

### 8.1. Những cập nhật class file bắt buộc sau khi chèn

- **`max_stack`:** extra instructions và hook parameters có thể làm tăng stack peak.
- **`max_locals`:** một call ID, thời gian bắt đầu hoặc Throwable local mới cần đúng slot; giá trị `long`/`double` chiếm hai slots.
- **`StackMapTable` / verification frames:** hợp lệ tại branch targets và handler entries sau khi thêm nhánh try/catch.
- **`exception_table`:** `[start_pc,end_pc)` và `handler_pc` phải trỏ tới offsets mới; catch-all handler cần đúng thứ tự ưu tiên với handler gốc.
- **Các jump targets, switch padding, debug tables:** điều chỉnh khi code_length/offsets thay đổi.
- **Method descriptor và return opcode:** bảo toàn đúng kiểu. Bytecode trả sai loại có thể gây `VerifyError`.
- **Constructor `<init>`:** không truy cập `this` trước khi đối tượng được khởi tạo đầy đủ; dùng AdviceAdapter đúng ngữ nghĩa constructor.
- **`abstract`/`native` methods:** không có `Code` attribute để chèn instruction trực tiếp; phải dùng chiến lược khác nếu cần.
- **Synchronized methods:** điểm bắt đầu/kết thúc tương đối với monitor acquisition/release khác nhau tùy placement; không đo sai lock-wait time.

Ví dụ với ASM, `ClassWriter.COMPUTE_MAXS`/`COMPUTE_FRAMES` có thể hỗ trợ tính toán metadata, nhưng không sửa được **logic hook** sai, không giải quyết mọi trường hợp class loader/hierarchy và không bảo đảm code giữ nguyên ngữ nghĩa. Hãy xác minh bằng `javap -c -v` và chạy class đã biến đổi.

## 9. Tại điểm gọi (caller): lúc nào đặt START?

Với source:

```java
int result = service.calculate(expensiveArgument());
```

Bytecode thường tính receiver/arguments **trước** khi thực thi `invokevirtual`. Nếu START được chèn **ngay trước `invokevirtual`**, nó **không** tính thời gian của `expensiveArgument()`. Nếu START được chèn **trước quá trình đánh giá arguments**, nó sẽ tính thêm thời gian chuẩn bị và side effects trước call.

```text
aload service
invokestatic expensiveArgument()I  // đánh giá đối số
START(callId)                      // điểm đo A: call dispatch
invokevirtual calculate(I)I
END_OK(callId)
...                                // dùng result
```

Đây là **sơ đồ trình tự**, không phải opcode listing hoàn chỉnh: đối tượng nhận/arguments đã nằm trên operand stack nên mã chèn phải bảo toàn chúng. Nếu `expensiveArgument()` ném exception thì điểm A chưa tạo START, vì lời gọi `calculate` chưa được dispatch. Nếu muốn đo toàn biểu thức, START phải đặt sớm hơn theo ý định nghiệp vụ.

Với **callee method entry**, END tương ứng với thời điểm method hoàn thành. Với **caller call-site**, END có thể bao gồm cả lỗi tại `invokevirtual` do receiver null hoặc việc resolve/link xảy ra tại call site. Hai phép đo **có thể khác nhau hợp lệ**, vì ranh giới khác nhau.

Không instrument tràn lan mọi `invoke*`: một method có thể gọi logger, JDK internals, các hàm rất nhỏ hàng triệu lần hoặc `invokedynamic`. Chọn mục tiêu theo owner/name/descriptor hoặc policy cấu hình, và phải loại trừ chính các lớp telemetry để tránh instrumentation đệ quy.

## 10. Kết thúc đồng bộ và kết thúc tác vụ async khác nhau

Ví dụ:

```java
CompletionStage<String> submit() {
    return CompletableFuture.supplyAsync(() -> slowWork());
}
```

Đây là **fragment**; cần các import và `slowWork()`. Nếu instrument tại **method entry/return**, END(OK) xảy ra **khi `submit` trả stage**, dù `slowWork()` còn đang chạy. Số đo đó là **thời gian submit / tạo stage**, không phải thời gian tác vụ thực tế hoàn thành.

Nếu mục tiêu là **thời gian hoàn thành asynchronous task**, attach callback vào stage:

```java
// Fragment minh họa: giả định id đã tạo và Trace.end không ném lỗi.
CompletionStage<String> stage = submit();
return stage.whenComplete((value, error) ->
        Trace.end(id, error == null ? "OK" : "ERROR"));
```

Đây là **fragment**, không phải chương trình đầy đủ. Cần xử lý thêm trường hợp **`submit()` ném lỗi trước khi trả stage**, stage hoàn thành bằng cancellation, executor khác, hoặc callback gặp lỗi. `whenComplete` tạo một dependent stage; **nếu callback ném exception**, nó có thể ảnh hưởng đường hoàn thành stage mới. Hãy thiết kế reporter **non-throwing** hoặc cô lập lỗi telemetry phù hợp.

Với context chuyển thread, `ThreadLocal` không tự đi theo `CompletableFuture`, `Executor` hoặc reactive pipeline. Truyền ID/context rõ ràng và quyết định ai sở hữu END; nếu đồng thời instrument method return **và** stage completion, tạo **hai loại span khác nhau**, tránh dùng chung một spanId khiến END nhân đôi.

## 11. Tính đúng khi xảy ra ngoại lệ và lỗi trong reporter

Một logger/hook có thể tự ném exception (serialization lỗi, lỗi kết nối, `OutOfMemoryError`), block vì I/O hoặc gọi vào chính một method đang bị instrument. Hậu quả có thể là:

- END(OK) được ghi rồi hook ném lỗi, khiến caller nhìn thấy ERROR dù code gốc lẽ ra thành công.
- END(ERROR) ném lỗi thứ hai, che mất exception gốc.
- START thành công nhưng END bị drop do queue đầy, hệ thống có span “mồ côi”.
- Hook gọi một service mà điểm đo lại instrument, tạo vòng lặp log không dừng.
- Sampling/filters của START và END khác nhau, khiến hai bên không ghép được.

**Thiết kế cần có chính sách rõ:** telemetry có thể fail-open để giữ nguyên behavior, hoặc một chế độ fail-closed được chủ sở hữu chấp thuận. Trong monitoring thông thường, mong muốn giữ nguyên kết quả/ngoại lệ ứng dụng, nên phải cô lập phần ghi dữ liệu, hạn chế reentrancy, dùng buffer/queue có giới hạn và đo số event bị drop.

Nếu cần ghi lỗi của chính tracer, dùng kênh riêng, rate limit và guards; không đặt logging chồng chéo vào đường nóng. Không cố catch `Throwable` rồi **nuốt lỗi ứng dụng**: trong ví dụ `TraceCallsDemo`, catch chỉ nhằm đánh dấu `ERROR` và **ném lại nguyên đối tượng**.

### 11.1. “Exactly once” là điều kiện cục bộ, không phải bảo đảm mạng

Ở vùng code chạy bình thường, mục tiêu là **mỗi START được chấp nhận tạo tối đa một END tương ứng**, và mọi đường thoát được bao phủ. Nhưng trên collector phân tán, queue, crash, restart và retry có thể dẫn tới sự kiện mất, trùng hoặc đến không đúng thứ tự.

Vì vậy event nên mang `spanId` và event kind; pipeline nhận dữ liệu nên deduplicate khi thích hợp, đặt timeout cho span thiếu END và đánh dấu dấu vết không hoàn chỉnh. **Không** tuyên bố event delivery exactly-once chỉ vì code có `finally`.

## 12. Phân tích sự kiện nhiều luồng và đệ quy

### 12.1. Hai thread gọi cùng method

```text
Thread-A: START(id=31, method=fetch) ───────── END(id=31)
Thread-B:     START(id=32, method=fetch) ─ END(id=32)

Event arrival:
START 31
START 32
END   32
END   31
```

Nếu ghép “END gần nhất cùng tên method”, cả hai sẽ bị ghép sai. Ghép theo **ID**, không theo thứ tự thời gian hay method name. Với nested call trong một thread, stack LIFO có thể hỗ trợ parent tracking, nhưng ID vẫn cần nếu sự kiện được gửi qua queue/collector.

### 12.2. Recursion

```text
factorial(3) START span1
  factorial(2) START span2, parent=span1
    factorial(1) START span3, parent=span2
    factorial(1) END span3
  factorial(2) END span2
factorial(3) END span1
```

Ba lần gọi có cùng `methodId` nhưng khác `spanId`. Nếu chỉ dùng tên method làm key cho bản đồ `startTime`, lần gọi trong cùng method sẽ **ghi đè** thời điểm của lần gọi bên ngoài. Muốn giữ quan hệ parent, dùng scope stack hoặc context có nesting rõ ràng; với async crossing threads, truyền context qua task boundary.

### 12.3. Synchronous nested spans và thời gian

Với parent span `P` chứa child `C`, thông thường:

- **Inclusive duration P:** thời gian từ START(P) tới END(P), bao gồm thời gian chờ child và các hoạt động trong khoảng đó.
- **Exclusive time P:** phần thời gian của parent không nằm trong các child intervals thuộc phạm vi đo tương ứng; việc trừ `sum(duration(children))` đơn giản có thể **sai** khi child spans chồng lấn hoặc thực thi song song.
- **Wall time** khác CPU time, IO wait và lock wait. Đừng gán nhãn “CPU cost” cho dữ liệu `nanoTime`.

Chính xác cần xác định metric/trace dùng **inclusive**, **exclusive**, **service time**, **queue wait**, hay **end-to-end latency**.

## 13. Sampling, cardinality và giới hạn hiệu năng

Ghi START/END cho mọi lần gọi cực nhỏ có thể tốn nhiều chi phí hơn chính công việc đang đo. Trước khi triển khai production, quyết định:

| Quyết định | Cách áp dụng |
| --- | --- |
| **Chọn mục tiêu** | Instrument service boundaries hoặc methods phù hợp; tránh mọi getter/setter trong JVM |
| **Sampling** | Chọn có thu thập hay không **khi START**, giữ quyết định cho END; tránh lấy mẫu START và END độc lập |
| **Buffering** | Dùng queue/batch async có giới hạn; xác định cách drop khi full |
| **Cardinality** | Dùng tên method đã chuẩn hóa; không tạo metric label cho argument/userId ngẫu nhiên |
| **Chi phí stack** | Tối thiểu local allocation/boxing, logging và số nhánh chèn |
| **Reentrancy** | Loại trừ collector/logger/agent helper classes khỏi instrument |
| **Privacy** | Chỉ ghi loại exception và thông tin cần thiết; redaction cho data nhạy cảm |
| **Clock & IDs** | Monotonic time đo duration; trace/span identifiers cho correlation; không ghép bằng timestamp |
| **Khả năng khôi phục** | Phân biệt event drop, exporter fail, service crash và timeout |

Nếu một invocation **không được lấy mẫu**, thông thường **không emit cả START lẫn END** cho span đó. Nhưng quyết định sampling có thể phải giữ trong một scope rất nhẹ để các child spans và parent relationships vẫn nhất quán.

`System.out.println` trong ví dụ giúp học dễ nhìn; khi instrument method nóng, dùng sink thực tế với asynchronous batching và backpressure. Tránh “mỗi END = một HTTP request” vì làm méo latency và tạo khả năng khuếch đại lỗi.

## 14. Kiểm thử điểm đo trước khi đưa vào ứng dụng

### 14.1. Các tình huống bắt buộc

1. **Một lời gọi trả bình thường:** đúng một START và một END(OK), cùng ID.
2. **`void` và các return types:** `int`, `long`, `double`, reference và `null` vẫn trả đúng giá trị; không phá operand stack.
3. **Explicit exception:** `throw new ...` thoát khỏi vùng, END(ERROR), original Throwable giữ nguyên.
4. **Implicit exception:** phương thức gọi phương thức khác, callee ném lỗi; END(ERROR) vẫn xuất hiện nếu exception thoát method được instrument.
5. **Caught exception:** lỗi được xử lý nội bộ và method return bình thường => END(OK) cho invocation.
6. **Nhiều return branches:** `if/else`, early return, loops đều phát một END.
7. **Nested & recursion:** ID riêng, `parentSpanId` đúng và END có thể đảo thứ tự theo nesting.
8. **Concurrency:** không có shared timestamp bị ghi đè; không ghép event theo thread name.
9. **Async:** phân biệt thời gian method return với thời gian hoàn thành future/publisher.
10. **Logger failure:** hook không được che exception gốc nếu yêu cầu fail-open.
11. **Bytecode verifier:** class đã biến đổi load thành công; stack map frames, handler ranges, offsets hợp lệ.
12. **Coverage:** không instrument nhầm logger/JDK core, method abstract/native hoặc class từ loader không hỗ trợ.

### 14.2. Dùng `javap` để xác nhận chèn đúng

Sau khi có snapshot class **BEFORE** và **AFTER** từ transformer:

```bash
javap -classpath before -c -v -p demo.Target > before.javap.txt
javap -classpath after  -c -v -p demo.Target > after.javap.txt
diff -u before.javap.txt after.javap.txt
```

Đây là **mẫu lệnh cho Linux/macOS** khi hai thư mục `before` và `after` tồn tại và có `demo/Target.class`. Trên Windows dùng dấu phân cách path phù hợp, có thể dùng `Compare-Object`. Phần quan trọng khi so là: START tại entry hoặc trước call site, END trên **mọi normal return**, exception handler bao phủ đúng phạm vi, stack maps/`max_stack`/`max_locals` được tính lại và ứng dụng chạy đúng.

Với Java agent instrument khi runtime, `javap` trên class file gốc **không tự đọc bytecode đã biến đổi trong JVM**. Nếu cần so, dùng snapshot của **bytes output thực tế của transformer** ghi ra vị trí riêng trong môi trường test. Không tự sửa file gốc rồi coi đó là output của agent.

### 14.3. Các chỉ số QA dễ kiểm tra

- `starts - ends` của **những spans đã hoàn thành và giao hàng đầy đủ** phải bằng 0; spans đang active là ngoại lệ dự kiến.
- Mỗi `spanId` có một START và **tối đa một END hợp lệ** sau deduplication.
- `elapsedNanos` là hiệu của hai lần đọc `nanoTime` trong cùng JVM, không phải phép trừ UTC từ các host.
- Exception kết thúc method phải tạo END(ERROR), caller vẫn thấy đúng Throwable; nếu nội bộ catch rồi return thì END(OK).
- Cùng bộ input, kết quả phương thức trước/sau instrumentation giống nhau, trừ side effects telemetry được chấp nhận.
- Khi vô hiệu hóa instrumentation, overhead và behavior trở lại mức kỳ vọng; kiểm tra các metrics dropped events, queue pressure và recursion guard.

## 15. Các sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Ghi log START/END chỉ bằng tên method | Không ghép được concurrent/recursive calls | ID riêng cho mỗi invocation |
| Ghi END chỉ trước `return` | Mất END khi exception thoát | Catch-all/finally đúng phạm vi |
| Dựa vào `onMethodExit(ATHROW)` cho mọi lỗi | Không thấy exception ngầm từ lời gọi khác | Catch-all handler của vùng đo |
| END hai lần: tại `ATHROW` và catch-all | Event trùng, duration tính hai lần | Một đường duy nhất ghi ERROR |
| Nạp thêm logger làm mất giá trị trên stack | `VerifyError` hoặc đổi return | Bảo toàn stack và return operand |
| Dùng `currentTimeMillis` làm đồng hồ elapsed chuẩn | Bị ảnh hưởng điều chỉnh wall-clock/độ phân giải | Dùng hiệu `System.nanoTime()` |
| Dùng `nanoTime` như timestamp UTC | Không so được giữa JVM/host | Dùng UTC timestamp riêng |
| Coi method trả future là hoàn thành task | Latency đo thiếu phần async | Tạo span riêng quanh completion stage |
| `ThreadLocal` không remove trên thread pool | Leak context, ghép parent sai | Pop và remove khi kết thúc scope |
| START và END sampling độc lập | Span chỉ có một đầu | Giữ sampling decision theo invocation |
| Reporter ném exception trong `finally` | Che lỗi gốc hoặc đổi success thành failure | Reporter non-throwing/fail-open theo policy |
| Instrument cả lớp logger | Reentrancy và stack overflow | Exclusion/filter + recursion guard |
| Đưa arguments/toString vào metric labels | Lộ dữ liệu, cardinality nổ | Chỉ dùng tên method chuẩn hóa, sanitization |
| Đếm `duration` cha bằng tổng duration con | Sai khi spans chồng lấn/parallel | Tính bằng ranh giới START(P)/END(P) |
| Chỉ test normal return | Production thiếu END(ERROR) | Test explicit/implicit exceptions và branches |
| Cho rằng có `finally` là giao hàng exactly-once | Crash/network/queue vẫn có thể mất/trùng | Span IDs, deduplication, timeout & exporter metrics |

## 16. Bài tập tự kiểm tra

1. **Trong `total()` có hai lần gọi `add`. Nếu chỉ lưu start time theo key `add`, điều gì sai?**  
   **Đáp án:** các lần gọi, đặc biệt lồng nhau/concurrent, có thể ghi đè cùng một key. Dùng `callId`/`spanId` riêng và scope context.

2. **Một method chỉ có `return Integer.parseInt(s);`. Khi `s="x"`, chèn END trước `IRETURN` có đủ không?**  
   **Đáp án:** không. `parseInt` ném exception khiến `IRETURN` không được chạy; cần handler cho exceptional exit.

3. **Một method bắt `IOException` và trả giá trị fallback bình thường. END là OK hay ERROR?**  
   **Đáp án:** nếu END mô tả **trạng thái kết thúc invocation**, đó là `OK`. Có thể ghi event `EXCEPTION_HANDLED` riêng nếu nghiệp vụ cần.

4. **Với return `long`, có dùng `dup` giống return `int` không?**  
   **Đáp án:** không. `long` thuộc category 2, cần thao tác thích hợp như `dup2` hoặc store/load vào slot `long` đúng kiểu.

5. **Hai thread ghi START(id=1), START(id=2), END(id=2), END(id=1). Có phải log sai thứ tự?**  
   **Đáp án:** không. Những lời gọi chồng lấn có thể kết thúc bất kỳ thứ tự nào; ghép theo ID.

6. **START đặt trước `invokevirtual` sau khi tính arguments. Thời gian tính arguments có nằm trong duration không?**  
   **Đáp án:** không, trừ khi ranh giới START được đặt sớm hơn.

7. **`CompletableFuture` được trả ngay, task hoàn thành sau 500 ms. Method-level END đo 500 ms chứ?**  
   **Đáp án:** không. END tại method return chỉ đo thời gian tạo/trả future; muốn đo completion phải thiết kế span riêng theo lifecycle future.

8. **Vì sao `onMethodExit(ATHROW)` và một catch-all đều gọi END(ERROR) là nguy hiểm?**  
   **Đáp án:** cùng một exception có thể tạo hai END; chọn một đường kết thúc duy nhất.

9. **`try/finally` có đảm bảo event đã lên collector chưa?**  
   **Đáp án:** không. Nó chỉ bảo đảm lời gọi local hook trên các đường thoát Java bình thường; queue, network hoặc crash vẫn có thể gây thiếu event.

10. **Muốn ghép span giữa hai microservice, có nên dùng số `AtomicLong` cục bộ?**  
    **Đáp án:** không đủ. Cần trace/span IDs có phạm vi phù hợp giữa process, truyền context qua network headers, và phân biệt service/process identities.

11. **Vì sao logger trong END phải được thiết kế không ném exception khi mục tiêu là transparency?**  
    **Đáp án:** vì END thường chạy sát `return`/exception unwind; lỗi logger có thể thay đổi return hoặc che nguyên nhân gốc.

12. **Tại sao “END(ERROR)” không nên được ghi mọi khi code thực thi một `throw`?**  
    **Đáp án:** exception có thể bị catch nội bộ và invocation vẫn hoàn thành thành công. Trạng thái END phải xét exception **thoát khỏi ranh giới đo**.

## 17. Tài liệu tham khảo chính thức

- Oracle JDK 17 — **`System.nanoTime()`** (đo elapsed time, arbitrary origin): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#nanoTime()
- Oracle JDK 17 — **`ThreadLocal`** và `remove()`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ThreadLocal.html
- Oracle JDK 17 — **`java.lang.reflect.Proxy`**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Proxy.html
- Oracle JDK 17 — **`Method.invoke` / `InvocationTargetException`**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html
- Oracle JDK 17 — **`ClassFileTransformer`** và `Instrumentation.addTransformer`: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html
- ASM Javadoc — **`AdviceAdapter`**, `onMethodEnter`, `onMethodExit` và constructor behavior: https://asm.ow2.io/javadoc/org/objectweb/asm/commons/AdviceAdapter.html
- JVM Specification 17 — **`Code` attribute, exception table (`4.7.3)**: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7.3
- JVM Specification 17 — **`invoke*`, `ireturn`/`lreturn`/`areturn`/`athrow` instructions**: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html
- W3C — **Trace Context** (trace-id, parent-id và phân tán): https://www.w3.org/TR/trace-context/

Khi thiết kế điểm đo, hãy xác định rõ **ranh giới**, tạo **một ID cho từng invocation**, ghi **START** một lần, ghi **END** trên cả normal và exceptional exits, tính thời lượng bằng **hiệu `nanoTime`**, và bảo toàn nguyên trạng return value/exception. Những quyết định này mới làm cặp sự kiện có ý nghĩa và đủ tin cậy để phân tích hiệu năng.

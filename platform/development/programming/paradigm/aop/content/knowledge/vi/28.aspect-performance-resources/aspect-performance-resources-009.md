# Kiểm tra rò rỉ bộ nhớ, khóa và tài nguyên giữ quá lâu trong Aspect (AOP)

## Mục tiêu học tập

Khi sử dụng lập trình hướng khía cạnh (Aspect-Oriented Programming, AOP), một **aspect** có thể thêm logging, đo thời gian, tracing, bảo vệ tài nguyên hoặc cơ chế đồng bộ vào nhiều điểm của chương trình. Nếu advice giữ tham chiếu, khóa hoặc tài nguyên sau khi thao tác đã kết thúc, lỗi nhỏ có thể được khuếch đại lên hàng nghìn lời gọi và tồn tại khó nhận ra.

Bài này hướng dẫn cách **phát hiện, phân loại, điều tra và phòng tránh** ba nhóm vấn đề:

1. **Rò rỉ bộ nhớ (memory leak)**: object không còn cần thiết nhưng vẫn có đường tham chiếu mạnh từ GC roots nên chưa thể thu gom.
2. **Khóa bị giữ quá lâu hoặc không được nhả**: thread bị chặn, giảm throughput, có thể dẫn đến deadlock hoặc starvation.
3. **Tài nguyên bị giữ quá vòng đời cần thiết**: file, socket, kết nối, stream, buffer, handle, semaphore permit hoặc ngữ cảnh gắn với thread không được giải phóng kịp lúc.

Các ví dụ dùng Java 17+, nhưng nguyên tắc về vòng đời advice, ownership và đường thực thi lỗi áp dụng cho AOP nói chung. Mỗi công nghệ AOP hỗ trợ loại join point và chiến lược weaving khác nhau; khi áp dụng cần kiểm tra khả năng và thứ tự advice của công nghệ đang dùng.

## 1. AOP tạo thêm những vòng đời nào?

Nhắc lại các khái niệm:

- **Join point**: vị trí có thể chèn hành vi bổ sung, chẳng hạn khi gọi hoặc thực thi một phương thức.
- **Pointcut**: biểu thức lựa chọn tập join point.
- **Advice**: logic chạy trước, sau, khi lỗi hoặc bao quanh join point.
- **Aspect**: thành phần gom pointcut, advice và có thể cả trạng thái hỗ trợ.
- **Weaving**: gắn hành vi của aspect vào đường thực thi, theo cơ chế của từng hệ thống.

Trong một **around advice**, mã phụ trợ có thể khởi tạo tài nguyên, chạy thao tác gốc (thường qua cơ chế tiếp tục/proceed), rồi dọn dẹp:

```text
Lời gọi vào join point
         |
         v
     Around advice
         |
         +--> Lấy context / cấp phát / có thể lấy khóa
         |
         +--> Thực thi nghiệp vụ gốc
         |       |
         |       +--> Trả kết quả
         |       +--> Hoặc ném ngoại lệ
         |
         +--> Giải phóng tài nguyên trong mọi đường kết thúc
         |
         v
   Trả kết quả / truyền tiếp lỗi
```

Lỗi thường nảy sinh khi advice giả định chỉ có đường thành công. Nếu mã dọn dẹp đặt sau lệnh gọi có thể ném ngoại lệ mà không dùng `finally` hoặc cấu trúc tự đóng, phần dọn dẹp có thể bị bỏ qua.

Bốn vòng đời cần xác định riêng là: **vòng đời một lần gọi**, **vòng đời một thread/tác vụ**, **vòng đời của đối tượng được chặn**, và **vòng đời instance/classloader của aspect**. Một tham chiếu chỉ cần tồn tại trong một lời gọi có thể thành rò rỉ khi bị lưu vào state sống lâu hơn lời gọi.

## 2. Phân biệt memory leak với tăng bộ nhớ bình thường

Trong môi trường có garbage collector, *memory leak* thường không phải do lập trình viên quên giải phóng thủ công. GC chỉ thu hồi object **không còn truy cập được từ GC roots**. Nếu aspect tiếp tục giữ một tham chiếu mạnh, object có thể sống đến hết vòng đời ứng dụng dù nghiệp vụ đã hoàn tất.

Ví dụ một cache không có giới hạn:

```java
// Mã minh họa, chưa phải chương trình độc lập.
private static final Map<String, Object[]> SAVED_ARGS =
        new ConcurrentHashMap<>();

void beforeInvocation(String invocationId, Object[] arguments) {
    SAVED_ARGS.put(invocationId, arguments);
}
```

Mỗi `arguments` có thể dẫn đến một đồ thị object lớn. Nếu `invocationId` luôn mới và không bao giờ có chính sách xóa, map tăng theo số lượt gọi. Bản thân `ConcurrentHashMap` an toàn cho truy cập đồng thời nhưng **không tự giới hạn kích thước hoặc thời gian sống**.

Không phải mọi tăng trưởng heap đều là leak:

| Hiện tượng | Cách hiểu |
| --- | --- |
| Heap tăng rồi ổn định sau warm-up | Có thể do JIT, cache có giới hạn, pool hoặc nhu cầu hợp lệ |
| Heap tăng giữa các chu kỳ GC nhưng giảm sau GC | Có thể là allocation bình thường |
| **Live set** sau các lần GC tương đương cứ tăng theo tải, không về mức ổn định | Dấu hiệu đáng điều tra về retained objects |
| Cache tăng đến giới hạn cấu hình và giữ ổn định | Có thể là hành vi thiết kế, vẫn cần đánh giá dung lượng |
| Bộ nhớ tiến trình tăng trong khi Java heap ổn định | Cần kiểm tra native memory, thread stacks, direct buffers, mã thư viện hoặc tài nguyên ngoài heap |

**Live set** là tập object vẫn còn sống sau thu gom; các lần đo phải cùng điều kiện tải và giai đoạn chạy. Không kích hoạt full GC liên tục trên production chỉ để lấy biểu đồ đẹp: việc này có thể tạo độ trễ đáng kể và làm thay đổi hiện tượng đang điều tra.

### 2.1. Những nguồn giữ tham chiếu hay gặp trong aspect

**State của aspect sống lâu:** instance hoặc trường `static` có thể giữ request, argument, result, exception, context hay danh sách listeners. Vòng đời cụ thể của instance phụ thuộc cách aspect được tạo và gắn với đối tượng/điểm cắt. Không giả định mọi aspect là singleton, cũng không giả định chúng đều tạo mới mỗi lời gọi.

**ThreadLocal không được dọn:** thread pool thường tái sử dụng thread. Nếu advice `set(...)` nhưng quên `remove()` hoặc phục hồi giá trị cũ, dữ liệu của request trước có thể còn trong thread và hiện diện ở request sau. Việc key `ThreadLocal` có weak reference ở cấu trúc nội bộ không khiến value lớn được dọn ngay, và không thay thế nghĩa vụ cleanup.

**Cache thiếu chính sách vòng đời:** cache phản chiếu metadata phương thức đôi khi hữu ích, nhưng cache theo từng argument hoặc request ID dễ không giới hạn. Cần hiểu key/value nào giữ những gì. `WeakHashMap` không phải thuốc chữa chung: value có thể tham chiếu ngược về key; trong trường hợp đó key vẫn có thể được giữ sống qua value.

**Callback và listener:** đăng ký listener tại mỗi join point rồi không hủy đăng ký làm nơi phát sự kiện giữ callback; callback có thể giữ đối tượng nghiệp vụ qua closure.

**Lưu invocation/context vào queue hoặc task dài hạn:** lambda/future/tracing event có thể capture `this`, `args`, request hoặc đối tượng lớn. Hàng đợi logging/tracing không giới hạn hoặc consumer bị chậm cũng làm số tham chiếu tăng nhanh.

**Đệ quy do pointcut quá rộng:** advice chặn cả formatter, logger hoặc bản thân API giám sát có thể tạo vòng gọi, nhiều object hoặc nhiều task ngoài dự kiến. Cần loại trừ các vùng nội bộ.

**Classloader/module được thay thế:** registry hoặc cache sống toàn tiến trình giữ `Class`, `Method`, aspect instance hay callback của classloader cũ có thể khiến classloader chưa thể giải phóng. Đây là tình huống cần chú ý trong ứng dụng có nạp lại thành phần động.

## 3. Khóa bị giữ quá lâu: triệu chứng và nguyên nhân

Khóa bảo vệ trạng thái dùng chung nhưng gây tác động xấu nếu phạm vi khóa rộng hơn phần trạng thái cần bảo vệ, hoặc đường lỗi bỏ qua giải phóng.

Phân biệt:

- **Contention**: nhiều thread phải chờ một khóa, dù cuối cùng vẫn lấy được.
- **Long hold time**: một thread giữ khóa quá lâu, thường do I/O, serialize lớn, sleep, callback hoặc gọi nghiệp vụ bên trong vùng khóa.
- **Deadlock**: các thread tạo chu trình chờ tài nguyên, không thể tiếp tục nếu không có can thiệp hoặc timeout thích hợp.
- **Starvation**: một số thread liên tục không nhận được cơ hội thực thi hoặc lấy tài nguyên, dù hệ thống vẫn có tiến triển.
- **Lock leak / unreleased permit**: mã quên unlock hoặc quên trả semaphore permit trên một đường đi. Với một số loại lock, thread kết thúc mà không unlock vẫn có thể khiến công việc khác mắc kẹt.

Ví dụ không an toàn:

```java
// Mã minh họa, chưa phải chương trình độc lập.
lock.lock();
Object result = proceed();  // Có thể ném ngoại lệ.
lock.unlock();              // Có thể không bao giờ chạy!
return result;
```

Thay bằng:

```java
// Mã minh họa, chưa phải chương trình độc lập.
lock.lock();
try {
    return proceed();
} finally {
    lock.unlock();
}
```

Nhưng `finally` chỉ đảm bảo thao tác unlock được *thử thực hiện*: người viết vẫn phải xác định đúng thread sở hữu, đúng khóa, đúng số lần reentrant acquisition và thời điểm acquire thành công. Không unlock một khóa chưa lấy được.

### 3.1. Có unlock đúng vẫn có thể chậm

```java
// Mã minh họa, chưa phải chương trình độc lập.
lock.lock();
try {
    serializeEntireRequest();
    sendToRemoteLogSink();    // Có thể bị chặn bởi mạng.
    return proceed();
} finally {
    lock.unlock();
}
```

Ở đây khóa được nhả trên đường thoát, nhưng bị giữ suốt quá trình tạo payload, truy cập mạng và gọi nghiệp vụ. Chỉ một sink chậm cũng có thể khiến hàng loạt lời gọi nối đuôi chờ khóa.

Thiết kế tốt hơn là chỉ khóa **đoạn thật sự cập nhật trạng thái dùng chung**, tạo bản ghi an toàn và gửi log ngoài critical section nếu tính đúng đắn cho phép. Nếu cần nhất quán dữ liệu, có thể chụp snapshot nhỏ trong khóa rồi xử lý snapshot sau khi nhả khóa. Không tùy ý chuyển thao tác phụ thuộc tính nguyên tử ra ngoài khóa.

### 3.2. Thứ tự khóa và tính tái nhập

AOP khiến thứ tự khóa phức tạp hơn khi có nhiều advice lồng nhau:

```text
Thread A: Advice X lấy lock L1 → nghiệp vụ → đợi L2
Thread B: Advice Y lấy lock L2 → callback → đợi L1
=> Có thể hình thành vòng chờ L1 ↔ L2.
```

Các biện pháp:

1. Xác định **thứ tự lấy khóa toàn cục** nhất quán nếu có nhiều khóa.
2. Tránh gọi mã nghiệp vụ tùy ý, callback hay I/O trong vùng khóa.
3. Với khóa hỗ trợ timeout, dùng `tryLock(timeout, unit)` và có cách xử lý timeout; không giả định timeout tự xử lý deadlock.
4. Chỉ dùng khóa reentrant khi thực sự phù hợp; không phải mọi cơ chế khóa đều hỗ trợ cùng một thread lấy lại.
5. Ghi nhận lock wait time, hold time và số timeout. Tránh ghi log quá nhiều ngay bên trong lock đang nghi ngờ.
6. Kiểm tra advice chạy theo thứ tự nào. Kết quả phụ thuộc thứ tự bọc và cách triển khai AOP; không suy diễn chỉ từ tên advice.

Với monitor Java dùng `synchronized`, JVM tự giải phóng monitor khi thoát khối, kể cả khi có ngoại lệ. Tuy vậy mã vẫn có thể giữ monitor quá lâu; đây là vấn đề về **phạm vi và độ dài**, chứ không nhất thiết là “quên unlock”. Còn `ReentrantLock` yêu cầu người dùng gọi `unlock()` chính xác.

## 4. Tài nguyên giữ quá lâu: xác định ai sở hữu và ai giải phóng

Tài nguyên ngoài heap thường có chi phí hữu hạn: file descriptor, socket, DB connection, direct buffer, semaphore permit, thread, session hoặc handle hệ điều hành. Advice dùng một tài nguyên không đúng vòng đời có thể khiến hệ thống hết kết nối dù heap vẫn bình thường.

Nên lập bảng ownership trước khi triển khai:

| Tài nguyên | Ai tạo hoặc mượn? | Ai được phép kết thúc? | Vòng đời đúng |
| --- | --- | --- | --- |
| File hoặc stream do advice mở | Advice | Advice | Một lần advice / một scope |
| Context tạm trong `ThreadLocal` | Advice thiết lập | Advice phục hồi | Scope đang thực thi |
| DB connection do nghiệp vụ truyền vào | Nghiệp vụ/caller | Chủ sở hữu hợp đồng | Theo hợp đồng của caller |
| Lock do advice lấy | Advice | Thread đã lấy đúng lock | Critical section |
| Trace span do advice bắt đầu | Advice | Advice | Phải hoàn tất cả trên đường lỗi |
| Executor/hàng đợi dùng chung | Thành phần quản lý ứng dụng | Thành phần quản lý ứng dụng | Suốt vòng đời thành phần |

Nguyên tắc: **người sở hữu tài nguyên phải kết thúc tài nguyên theo hợp đồng của nó**. Một advice không được tự đóng stream, result hoặc connection do caller sở hữu chỉ vì “muốn dọn dẹp”. Điều đó làm thay đổi hành vi ứng dụng và có thể gây lỗi khó đoán.

Với tài nguyên `AutoCloseable` thuộc quyền advice, sử dụng `try-with-resources`:

```java
// Mã minh họa, chưa phải chương trình độc lập.
try (ResourceScope resource = openAdviceResource()) {
    return proceed();
}
```

Nếu `proceed()` ném lỗi và `close()` cũng ném lỗi, Java try-with-resources giữ lỗi từ body làm ngoại lệ chính, đồng thời thêm lỗi đóng vào các *suppressed exceptions*. Cần kiểm tra cơ chế báo lỗi thực tế, nhưng tránh thay đổi ngoại lệ nghiệp vụ chỉ để báo lỗi telemetry.

Các sai lầm khác: mở scope sớm nhưng giải phóng rất muộn sau khi response hoàn tất; mượn connection rồi giữ trong callback bất đồng bộ không có owner rõ; trì hoãn close đến finalize/GC; tạo thread/Executor trong mỗi lần advice mà không shutdown; giới hạn queue lớn đến mức backpressure đến quá muộn.

## 5. ThreadLocal và tác vụ bất đồng bộ

Một tình huống rò rỉ ngữ cảnh điển hình:

```java
// Mã minh họa, chưa phải chương trình độc lập.
static final ThreadLocal<RequestContext> CURRENT = new ThreadLocal<>();

void before(RequestContext context) {
    CURRENT.set(context);
}

Object around() throws Throwable {
    return proceed();  // Nếu không dọn, thread pool có thể giữ context.
}
```

Mã an toàn hơn phải **phục hồi giá trị trước đó**, không chỉ xóa vô điều kiện nếu có lời gọi AOP lồng nhau:

```java
// Mã minh họa, chưa phải chương trình độc lập.
RequestContext previous = CURRENT.get();
CURRENT.set(current);
try {
    return proceed();
} finally {
    if (previous == null) {
        CURRENT.remove();
    } else {
        CURRENT.set(previous);
    }
}
```

Khi xử lý chuyển sang thread khác, `ThreadLocal` thông thường không tự chuyển context giữa các thread. Cần quản lý việc truyền context theo mô hình task/executor cụ thể, kết thúc scope tại nơi nó được thiết lập và tránh lưu tham chiếu đến toàn bộ request trong task dài hạn. Việc tự động copy toàn bộ context có thể làm rò rỉ dữ liệu hoặc kéo dài vòng đời nếu không có chính sách rõ ràng.

## 6. Ví dụ Java 17+: cleanup đúng cả khi nghiệp vụ thất bại

Ví dụ dưới đây dùng `java.lang.reflect.Proxy` để mô phỏng một lớp chặn lời gọi kiểu around advice. Proxy này làm việc với interface và **không biểu diễn mọi khả năng của một hệ thống AOP**. Điểm cần quan sát là: advice tự sở hữu một resource, lấy khóa, gắn context tạm; sau khi lời gọi thành công hoặc thất bại, cả ba đều được dọn đúng vòng đời.

Tạo file `AdviceLifetimeDemo.java`:

```java
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.locks.ReentrantLock;

public class AdviceLifetimeDemo {
    private static final ThreadLocal<String> TRACE = new ThreadLocal<>();
    private static final AtomicInteger OPENED = new AtomicInteger();
    private static final AtomicInteger CLOSED = new AtomicInteger();

    public interface Operation {
        String execute(boolean fail);
    }

    static final class BusinessOperation implements Operation {
        @Override
        public String execute(boolean fail) {
            if (fail) {
                throw new IllegalStateException("boom");
            }
            return "ok";
        }
    }

    static final class AdviceResource implements AutoCloseable {
        AdviceResource() {
            OPENED.incrementAndGet();
        }

        @Override
        public void close() {
            CLOSED.incrementAndGet();
        }
    }

    static final class SafeAdvice implements InvocationHandler {
        private final Operation target;
        private final ReentrantLock gate = new ReentrantLock();

        SafeAdvice(Operation target) {
            this.target = target;
        }

        @Override
        public Object invoke(Object proxy, Method method, Object[] args)
                throws Throwable {
            String previous = TRACE.get();
            TRACE.set("trace-demo");
            boolean acquired = false;
            try {
                acquired = gate.tryLock(200, TimeUnit.MILLISECONDS);
                if (!acquired) {
                    throw new IllegalStateException("lock timeout");
                }

                try (AdviceResource resource = new AdviceResource()) {
                    try {
                        return method.invoke(target, args);
                    } catch (InvocationTargetException ex) {
                        // Giữ nguyên ngoại lệ gốc từ nghiệp vụ.
                        throw ex.getCause();
                    }
                }
            } finally {
                if (acquired) {
                    gate.unlock();
                }
                if (previous == null) {
                    TRACE.remove();
                } else {
                    TRACE.set(previous);
                }
            }
        }
    }

    public static void main(String[] args) {
        SafeAdvice advice = new SafeAdvice(new BusinessOperation());
        Operation operation = (Operation) Proxy.newProxyInstance(
                Operation.class.getClassLoader(),
                new Class<?>[] {Operation.class},
                advice
        );

        System.out.println("result=" + operation.execute(false));

        try {
            operation.execute(true);
        } catch (IllegalStateException ex) {
            System.out.println("failure=" + ex.getMessage());
        }

        System.out.println("resourceClosed="
                + CLOSED.get() + "/" + OPENED.get());
        System.out.println("lockReleased=" + !advice.gate.isLocked());
        System.out.println("contextRestored=" + (TRACE.get() == null));
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac AdviceLifetimeDemo.java
java AdviceLifetimeDemo
```

Đầu ra:

```text
result=ok
failure=boom
resourceClosed=2/2
lockReleased=true
contextRestored=true
```

Giải thích:

- `tryLock(200, TimeUnit.MILLISECONDS)` đặt một giới hạn chờ lấy khóa, thay vì chờ vô hạn. Biến `acquired` giúp chỉ nhả khóa khi đã lấy thành công.
- `try-with-resources` gọi `close()` cho `AdviceResource` trên cả hai đường hoàn thành. Bộ đếm giả lập chứng minh có hai lượt mở và hai lượt đóng, nhưng **không chứng minh mọi tài nguyên thật đã được giải phóng**.
- `finally` bảo đảm khối dọn lock và `ThreadLocal` chạy kể cả khi target ném lỗi.
- `InvocationTargetException` là wrapper từ lời gọi reflection; `getCause()` được chuyển tiếp để caller nhận đúng lỗi nghiệp vụ.
- `TRACE` được phục hồi về giá trị trước đó; trong chương trình demo nó ban đầu bằng `null`, nên sau mọi lượt gọi kết quả kiểm tra là `true`.

Ví dụ cố ý chứa khóa để minh họa cleanup, **không khuyến nghị bọc khóa quanh toàn bộ nghiệp vụ trong mọi aspect**. Trong ứng dụng thực tế, vùng khóa cần hẹp, phù hợp ownership và tính đúng đắn. Nếu việc dọn tài nguyên tự ném lỗi, cần chính sách xử lý riêng để giữ khả năng chẩn đoán và tránh vô tình che lỗi gốc; ví dụ có `close()` không ném lỗi nhằm làm rõ vòng đời.

## 7. Điều tra rò rỉ bộ nhớ có hệ thống

Đừng suy ra nguyên nhân chỉ từ biểu đồ heap tăng. Điều tra theo các bước để tránh kết luận sai:

### Bước 1 — Xác nhận triệu chứng và mốc phát sinh

Ghi nhận thời điểm bắt đầu, tải, phiên bản, lượng request, những pointcut mới thêm, thời gian chạy, heap đã cấp phát và mức GC. So sánh cùng lưu lượng trước/sau khi bật advice nếu có thể. Chú ý thay đổi về loại payload, số worker thread và cấu hình cache/queue.

### Bước 2 — Xác định vùng bộ nhớ tăng

Phân biệt:

- Java heap: object tham số, context, map, buffer, task.
- Native/off-heap: direct buffer, thread stack, native allocations.
- Tài nguyên kernel và pool: file descriptor, socket, DB connection, thread.

Chỉ xem `Runtime.totalMemory()` hoặc mức RAM hệ điều hành là không đủ để quy kết memory leak Java heap.

### Bước 3 — Kiểm tra xu hướng đối tượng sống

Có thể dùng công cụ JDK và trình quan sát JVM phù hợp:

```bash
# Xác định Java process phù hợp.
jcmd -l

# Quan sát histogram các class đang tồn tại (tác động tùy tùy chọn/JDK).
jcmd <PID> GC.class_histogram

# Thu thập heap dump để phân tích bằng công cụ heap.
jcmd <PID> GC.heap_dump /path/to/aspect-heap.hprof

# Quan sát thông tin thread nếu nghi có khóa hoặc task bị giữ.
jcmd <PID> Thread.print
```

Các lệnh minh họa dùng placeholder `<PID>` và đường dẫn; cần thay bằng giá trị thật. Một số thao tác như heap dump, live-object inspection có thể tạm dừng ứng dụng, tiêu tốn tài nguyên lớn và sinh file chứa dữ liệu nhạy cảm. Thực hiện có kiểm soát, ưu tiên staging hoặc thời điểm vận hành phù hợp. Tên tùy chọn và mức hỗ trợ phụ thuộc JDK.

Để phân tích sâu, xem **GC roots**, **retained size** và **dominator tree** trong công cụ heap. Một object có *shallow size* nhỏ như entry của map có thể gián tiếp giữ một đồ thị dữ liệu lớn; retained size giúp đánh giá lượng bộ nhớ sẽ có khả năng được giải phóng nếu bỏ được đường giữ tương ứng.

### Bước 4 — Tìm đường giữ object

Các chuỗi giữ tham chiếu đáng kiểm tra:

```text
GC root
  → static field của AspectRegistry
  → Map<invocationId, Object[]>
  → arguments
  → request payload lớn

GC root
  → thread pool worker
  → ThreadLocalMap
  → RequestContext
  → object graph của request cũ

GC root
  → hàng đợi tác vụ/logging
  → callback hoặc event
  → captured request / target
```

Nếu classloader cũ không được thu hồi, kiểm tra cache, callback hoặc registry sống lâu hơn classloader có giữ `Class`/`Method` hay instance cũ hay không.

### Bước 5 — Kiểm chứng giả thuyết bằng thay đổi có mục tiêu

Chẳng hạn, thêm chính sách giới hạn cache, đảm bảo `ThreadLocal` được dọn hoặc ngăn advice capture object lớn. Dưới cùng mức tải, đo lại live set, số object, allocation rate và CPU. Chỉ kết luận lỗi đã sửa khi đường giữ đã bị xóa và số liệu ổn định; việc tăng kích thước heap chỉ có thể che giấu vấn đề.

## 8. Điều tra khóa bị giữ lâu hoặc deadlock

**Thread dump** và **Java Flight Recorder (JFR)** hữu ích khi nhiều thread đứng chờ. Cần quan sát nhiều thời điểm vì một snapshot có thể không đại diện toàn bộ quá trình.

Ví dụ lệnh chụp trạng thái:

```bash
jcmd <PID> Thread.print

# Khởi chạy recording JFR trên JVM đang chạy, khi phù hợp.
jcmd <PID> JFR.start name=aspect-diagnostics settings=profile duration=60s filename=/path/to/aspect.jfr
```

Phân tích kết quả để tìm:

- Thread ở `BLOCKED` khi tranh chấp monitor, hoặc `WAITING`/`TIMED_WAITING` ở cơ chế chờ tương ứng; **trạng thái thread đơn lẻ không chứng minh deadlock**.
- Stack trace có advice/pointcut liên quan trước khi gọi I/O, serializer hoặc thực thi nghiệp vụ.
- Lock identity, thread owner, vị trí acquisition và chu trình chờ; tính sẵn có của dữ liệu owner tùy loại lock và công cụ.
- Khoảng thời gian bị block, tỷ lệ contention, số lần timeout và phần thời gian thực thi bên trong critical section.
- Hệ quả qua throughput, `p95/p99` và số task đang đợi.

Java có `ThreadMXBean.findDeadlockedThreads()` để tìm deadlock liên quan đến monitor và ownable synchronizers được hỗ trợ. Kết quả `null` **không bảo đảm không có** deadlock ở mọi loại tài nguyên, chẳng hạn chờ network, DB lock hay chu trình ở cơ chế tự viết. Đồng thời, contention hoặc wait kéo dài không có chu trình vẫn có thể gây treo nghiệp vụ.

### 8.1. Xác định khóa từ trạng thái thread

Một cách tiếp cận thực tế:

1. Chụp thread dump/JFR tại lúc hệ thống chậm, ghi lại thời gian và tải.
2. Nhóm thread đang chờ cùng lock/condition; tìm thread giữ khóa nếu có thông tin.
3. Kiểm tra stack frame của owner: có đang làm logging, serialize, I/O hay callback bên trong advice không?
4. Kiểm tra thứ tự các advice và các khóa mà mỗi thành phần đang giữ.
5. Giới hạn vùng khóa, bỏ I/O khỏi vùng khóa hoặc bổ sung timeout khi phù hợp hợp đồng.
6. Đo lại wait time, hold time, throughput và percentile độ trễ.

Cẩn trọng: vì thread pool có nhiều tác vụ liên tục, một thread dump tại thời điểm khác có thể chỉ ra task khác. Nên đối chiếu theo timestamp, trace ID và dữ liệu recording thay vì gán nguyên nhân từ một frame xuất hiện ngẫu nhiên.

## 9. Điều tra tài nguyên ngoài heap hoặc tài nguyên hệ điều hành

Với file/socket/connection bị giữ lâu, heap dump có thể chỉ thấy wrapper Java mà không trực tiếp phản ánh số handle hệ điều hành. Cần thêm các chỉ số:

| Dấu hiệu | Dữ liệu cần đo | Nguyên nhân AOP có thể có |
| --- | --- | --- |
| Số file descriptor tăng đều | Số FD theo thời gian, tệp/socket đang mở | Advice mở sink/stream mỗi lần nhưng không đóng |
| Pool kết nối cạn | Active, idle, waiters, acquisition timeout | Mượn kết nối quá lâu hoặc bỏ qua return |
| Queue/tác vụ phình to | Queue depth, enqueue rate, consumer rate | Advice tạo event nhanh hơn sink xử lý |
| Số thread tăng bất thường | Live threads, thread state, executor lifecycle | Advice tạo executor/thread mới theo mỗi lời gọi |
| Direct/native memory tăng | Native memory, direct buffer statistics | Buffer hoặc native handle được giữ quá lâu |
| Semaphore permit không hồi phục | Available permits, waiters, error path | Một nhánh advice không trả permit |

**Chủ sở hữu** là thông tin quan trọng nhất. Đối chiếu điểm acquire/open và release/close ở mọi đường success, failure, cancellation, timeout và interruption. Một số tác vụ bất đồng bộ hoàn tất sau khi around advice trả về; cần chuyển ownership một cách tường minh thay vì đóng tài nguyên quá sớm hoặc bỏ mặc không ai đóng.

## 10. Chẩn đoán AOP mà không tạo thêm lỗi

Việc thêm advice để “quan sát tất cả” có thể tự gây memory leak, contention hoặc overhead. Các quy tắc tối thiểu:

- Chọn pointcut đủ hẹp; tránh advice nội bộ logger, serializer, heap sampler, metric recorder hoặc chính mã chẩn đoán.
- Ưu tiên đếm sự kiện, kích thước, trạng thái và thời lượng. Không giữ nguyên object request/result trong collection dài hạn để “xem sau”.
- Nếu cần log lỗi, chọn trường an toàn; tránh gọi `toString()` hoặc serialize toàn bộ object trên đường đang thiếu bộ nhớ.
- Đặt giới hạn cứng cho kích thước buffer/cache/queue; có metric cho số lần drop/backpressure.
- Giữ observer không phụ thuộc trực tiếp vào chính đối tượng nó đang theo dõi nếu có thể, và quản lý vòng đời listener.
- Không ném ngoại lệ mới che ngoại lệ nghiệp vụ chỉ vì hệ thống telemetry hỏng.
- Xem xét tác động của logging dưới khóa: lời gọi quan sát có thể làm thời gian giữ khóa dài hơn và bóp méo phép đo.
- Nếu cần tương quan giữa nhiều thread, tạo context ngắn gọn, truyền tường minh theo task và dọn sạch đúng scope.

## 11. Quy trình kiểm thử dành cho aspect quản lý trạng thái/tài nguyên

Để tránh chỉ thử “happy path”, lập ma trận các trường hợp:

| Tình huống | Phải xác nhận |
| --- | --- |
| Lời gọi thành công | Trả đúng kết quả, release/close đúng một lần |
| Nghiệp vụ ném ngoại lệ | Truyền tiếp đúng lỗi, vẫn dọn tài nguyên |
| Không lấy được khóa | Không unlock nhầm; context đã phục hồi |
| Thread bị interrupt hoặc task bị cancel | Không bỏ sót cleanup ở phần đã acquire |
| Lời gọi lồng nhau | Phục hồi context trước đó, không xóa mất scope bên ngoài |
| Các thread chạy đồng thời | Không có shared state lỗi, race hoặc contention không cần thiết |
| Logger/sink/serializer thất bại | Không giữ lock hoặc resource; xử lý lỗi phụ theo chính sách |
| Tải lặp lại trong thời gian dài | Live heap, số FD, thread, queue và pool ổn định theo mức tải kỳ vọng |
| Advice được gỡ hoặc đối tượng hết vòng đời | Không còn listener/cache/registry giữ instance hoặc classloader đã hết hạn |

Với Java, kiểm thử đơn vị có thể mô phỏng lời gọi thành công, lỗi và timeout; kiểm thử dài hạn với tải ổn định sẽ cung cấp bằng chứng tốt hơn cho nghi ngờ rò rỉ. Dùng metric phù hợp để bảo đảm việc dọn tài nguyên thực sự xảy ra, thay vì suy luận từ log “đã close” do một phương thức có thể ghi nhận trước khi close thất bại.

## 12. Những sai lầm phổ biến và cách sửa

**Sai lầm 1: lưu mọi tham số để debug.** Điều này duy trì tham chiếu đến toàn bộ đồ thị request. Cách sửa là chỉ ghi snapshot nhỏ, đã lọc và giới hạn; không giữ object gốc nếu không có owner/vòng đời cần thiết.

**Sai lầm 2: gọi `remove()` sau `proceed()`.** Nếu `proceed()` ném lỗi, cleanup bị bỏ qua. Cách sửa: đặt trong `finally`, phục hồi giá trị context cũ khi có lời gọi lồng nhau.

**Sai lầm 3: dùng một lock quanh toàn bộ advice.** Có thể tuần tự hóa mọi lời gọi, kể cả thao tác độc lập. Cách sửa: xác định chính xác trạng thái chung nào phải bảo vệ, khóa phạm vi nhỏ nhất bảo đảm tính đúng đắn và đo contention.

**Sai lầm 4: xử lý timeout bằng cách retry vô hạn trong advice.** Một request duy nhất có thể tiếp tục chiếm thread và kéo dài thời gian giữ tài nguyên. Cách sửa: áp dụng deadline, giới hạn retry và chính sách lỗi phù hợp.

**Sai lầm 5: đóng mọi thứ khi kết thúc advice.** Resource của caller hoặc kết quả lazy có thể cần sống lâu hơn advice. Cách sửa: xác định ownership và hợp đồng vòng đời; chỉ đóng tài nguyên do advice sở hữu hoặc được giao trách nhiệm đóng rõ ràng.

**Sai lầm 6: xem mọi heap tăng là memory leak.** JIT, cache được giới hạn và tải khác nhau có thể gây tăng trưởng hợp lệ. Cách sửa: so sánh live set, GC roots, retained size và xu hướng theo tải.

**Sai lầm 7: nghĩ cứ có `finally` là hết rủi ro.** `finally` không thu hẹp thời gian giữ khóa, không chặn deadlock do thứ tự khóa và không tự đóng resource thuộc scope khác. Cách sửa: kiểm tra cả **ownership, ordering, duration, cancellation và concurrency**.

**Sai lầm 8: bật profiling quá nặng rồi kết luận bằng số đo đó.** Heap dump và logging dày có thể làm ứng dụng chậm hoặc biến đổi vấn đề. Cách sửa: sử dụng số liệu ít xâm lấn trước, lựa chọn thời điểm phân tích chuyên sâu và đối chiếu với tải thực tế.

## 13. Checklist thực hành trước khi đưa một aspect vào hệ thống

- [ ] Pointcut khớp đúng nơi cần, không tự chặn mã chẩn đoán.
- [ ] Mỗi tham chiếu lưu trong state có thời hạn sống và chính sách loại bỏ.
- [ ] Cache/queue có giới hạn và quan sát được tình trạng đầy.
- [ ] `ThreadLocal` được dọn hoặc phục hồi trong `finally`, kể cả lời gọi lồng nhau.
- [ ] Lock chỉ bảo vệ critical section thực sự; mọi nhánh acquire/unlock cân bằng.
- [ ] Thứ tự các lock và advice không tạo chu trình chờ; timeout có cách xử lý rõ ràng.
- [ ] Mọi file/socket/connection/span/permit có owner chịu trách nhiệm kết thúc.
- [ ] Lỗi nghiệp vụ và lỗi cleanup được xử lý đúng hợp đồng, không âm thầm mất thông tin.
- [ ] Test có success, exception, timeout, interrupt, nested calls và concurrency.
- [ ] Sau kiểm thử tải, theo dõi live heap, thread, FD, queue, wait/hold time và latency.

## Kết luận

Với AOP, lỗi về tài nguyên thường nằm ở **vòng đời và phạm vi** của hành vi được chèn thêm: giữ tham chiếu lâu hơn lời gọi, giữ khóa qua I/O hoặc quên dọn context/tài nguyên trên đường ngoại lệ. Điều tra hiệu quả bắt đầu từ việc phân biệt memory retention, contention, deadlock và resource exhaustion; tiếp theo là xác định GC root hoặc owner của khóa/tài nguyên, rồi đối chiếu đường acquire với đường release.

Một aspect an toàn cần phạm vi pointcut rõ ràng, trạng thái được giới hạn, cơ chế dọn dẹp đáng tin cậy và bằng chứng đo đạc dưới tải. Khi đó chức năng quan sát hoặc bảo vệ do AOP cung cấp có thể hoạt động mà không âm thầm làm cạn tài nguyên hoặc thay đổi ngữ nghĩa nghiệp vụ.

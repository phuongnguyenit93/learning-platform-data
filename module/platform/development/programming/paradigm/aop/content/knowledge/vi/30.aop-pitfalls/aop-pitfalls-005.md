# Lưu trạng thái yêu cầu trong aspect dùng chung: sai lầm thường gặp trong AOP

## 1. Bài toán: một aspect được nhiều yêu cầu sử dụng

Trong lập trình hướng khía cạnh (Aspect-Oriented Programming, AOP), **aspect** tập trung những hành vi áp dụng xuyên suốt nhiều vị trí trong chương trình, như ghi nhật ký, đo thời gian, tracing, kiểm tra điều kiện hoặc kiểm soát tài nguyên. **Pointcut** chọn các **join point**; **advice** là phần mã bổ sung được thực hiện tại các vị trí đó. Với **around advice**, mã có thể thực hiện việc chuẩn bị, gọi tiếp hành vi gốc, quan sát kết quả rồi dọn dẹp.

Một sai lầm nguy hiểm là đưa **trạng thái riêng của từng yêu cầu (request/invocation state)** vào một trường (field) của **aspect instance dùng chung**, chẳng hạn:

- ID yêu cầu, ID truy vết hoặc người dùng hiện tại.
- Thời điểm bắt đầu xử lý để đo latency.
- Tham số, kết quả, ngoại lệ hoặc thông tin phân quyền của lần gọi.
- Cờ đánh dấu đang ghi log, đang mở transaction hoặc đang thực hiện advice.
- Danh sách resource, buffer, span hoặc object dùng để theo dõi một yêu cầu.

Khi nhiều thread hoặc nhiều tác vụ đồng thời đi qua cùng một aspect instance, các trường có thể bị **ghi đè, đọc nhầm, phát sinh data race hoặc giữ object lâu hơn vòng đời yêu cầu**.

**Điểm cần xác định ngay:** AOP không quy định mọi aspect đều có duy nhất một instance. Mô hình khởi tạo có thể theo toàn ứng dụng, theo đối tượng đích, theo từng lần gọi, theo cấu hình weaving hoặc theo cơ chế khác. Sai lầm ở đây xuất hiện **khi trạng thái của từng lần gọi bị đặt vào một instance thực sự được chia sẻ bởi nhiều lần gọi**. Hãy kiểm tra vòng đời aspect trong công nghệ sử dụng, thay vì mặc định “aspect luôn singleton”.

### Mục tiêu sau bài học

Bạn sẽ biết cách phân biệt **cấu hình có thể chia sẻ** và **dữ liệu chỉ thuộc một lần gọi**; giải thích vì sao `volatile`, `synchronized` và các collection concurrent không tự giải quyết nhầm lẫn ownership; lựa chọn biến cục bộ, context theo phạm vi thực thi, `ThreadLocal` hoặc cơ chế truyền context tường minh; và viết kiểm thử đồng thời phát hiện lỗi rò rỉ dữ liệu giữa các yêu cầu.

## 2. Trạng thái chia sẻ khác trạng thái theo yêu cầu như thế nào?

Một instance aspect có thể được tái sử dụng hợp lệ. Vấn đề không nằm ở việc tái sử dụng aspect, mà ở **loại dữ liệu được gắn với vòng đời của nó**.

| Loại dữ liệu | Ví dụ | Vòng đời hợp lý |
| --- | --- | --- |
| Cấu hình không đổi | Tên thao tác, quy tắc pointcut, ngưỡng cấu hình, danh sách trường an toàn | Có thể lưu tại instance dùng chung nếu bất biến hoặc đồng bộ đúng |
| Bộ đếm tổng hợp | Số lần advice chạy, tổng số lỗi | Có thể chia sẻ qua cấu trúc concurrent/atomic, không chứa danh tính một request |
| Trạng thái một invocation | `startNanos`, `requestId`, tham số, kết quả, exception | Thuộc duy nhất một lần chạy advice |
| Context theo luồng | Correlation context, cờ chống đệ quy khi chạy đồng bộ | Chỉ dùng nếu thread ownership và cleanup được bảo đảm |
| Context đi qua nhiều thread | Trace context, deadline, thông tin tác vụ | Cần truyền tường minh hoặc abstraction có scope phù hợp |
| Tài nguyên theo yêu cầu | File tạm, span, buffer, permit, kết nối do advice mượn | Phải có owner và đường kết thúc rõ ràng |

Một trường `final` chứa cấu hình bất biến thường an toàn để đọc từ nhiều thread. Nhưng `final` trên một tham chiếu trỏ đến `HashMap` có thể thay đổi **không làm map bất biến hoặc thread-safe**. Tương tự, dùng `ConcurrentHashMap` đúng cách có thể bảo vệ thao tác cấu trúc của map, nhưng nếu dùng map để lưu vô hạn mọi request thì vẫn có nguy cơ rò rỉ bộ nhớ và lẫn thông tin.

## 3. Ví dụ sai: đưa request ID vào trường của aspect

Đây là mã giả minh họa một around advice trong aspect dùng chung; `proceed()` đại diện cho lời gọi tiếp tục đến logic gốc theo API AOP tương ứng:

```java
// Minh họa sai, không phải chương trình Java độc lập.
final class SharedRequestAdvice {
    private String currentRequestId;  // Trường thuộc instance dùng chung.

    Object around(String requestId) throws Throwable {
        currentRequestId = requestId;
        Object result = proceed();
        recordAudit(currentRequestId, result);
        return result;
    }
}
```

Giả sử hai yêu cầu A và B cùng đi vào một instance:

```text
Thời điểm    Thread A                         Thread B
----------------------------------------------------------------------
t1           currentRequestId = "A"
t2                                            currentRequestId = "B"
t3           proceed() hoàn tất
t4           recordAudit("B", resultOfA)       ← Sai yêu cầu!
t5                                            recordAudit("B", resultOfB)
```

Lỗi không yêu cầu JVM “hỏng bộ nhớ”. Nó phát sinh do hai lời gọi hợp lệ cùng dùng một vị trí lưu dữ liệu không phù hợp vòng đời. Kết quả có thể là log của A mang correlation ID của B, metric ghi nhầm tenant hoặc phản hồi của một người dùng bị liên kết với thông tin người dùng khác.

Nếu `currentRequestId` là trường thường, còn có thêm vấn đề về **data race và khả năng nhìn thấy dữ liệu** theo Java Memory Model. Nhưng ngay cả khi thay bằng:

```java
// Vẫn sai về ownership nếu state thuộc từng lời gọi.
private volatile String currentRequestId;
```

thì mỗi lần gọi vẫn ghi chung một ô trạng thái. `volatile` giúp thiết lập một số bảo đảm visibility/happens-before cho hoạt động đọc/ghi, **không tạo một biến request ID riêng cho từng lời gọi**.

Tương tự, thay trường bằng `AtomicReference<String>` chỉ làm cập nhật tham chiếu trở thành atomic; nó không bảo đảm lời gọi A luôn đọc ID của A nếu B cập nhật xen giữa.

## 4. Phân loại hậu quả

### 4.1. Dữ liệu sai hoặc rò rỉ giữa các yêu cầu

Trường chia sẻ lưu `requestId`, danh tính người dùng hoặc metadata phân quyền có thể gây cross-request contamination. Nguy cơ nghiêm trọng hơn khi advice dựa trên trường này để **ra quyết định**, ví dụ chọn tenant, kiểm tra giới hạn truy cập hoặc tìm dữ liệu của người dùng.

Đây vừa là lỗi đồng thời vừa là lỗi bảo mật và tính đúng đắn. Không nên xem đây đơn thuần là “log hơi sai”.

### 4.2. Đo latency sai

Ví dụ:

```java
// Minh họa sai, không phải chương trình độc lập.
private long startNanos;

Object around() throws Throwable {
    startNanos = System.nanoTime();
    try {
        return proceed();
    } finally {
        long elapsed = System.nanoTime() - startNanos;
        emitLatency(elapsed);
    }
}
```

Nếu A ghi thời điểm bắt đầu rồi B ghi đè `startNanos` trước khi A tính thời lượng, số đo của A sẽ sai. Thay `long` bằng một kiểu atomic hoặc `volatile` vẫn không sửa việc **dùng chung biến cho hai invocation khác nhau**.

### 4.3. Trạng thái trước và sau không còn khớp nhau

Một aspect có thể giữ `arguments` lúc vào phương thức để so sánh với `result` lúc thoát. Nếu giữ các giá trị này trong field dùng chung, advice sau có thể ghép tham số của request B với kết quả request A. Với logic quản lý resource, nhầm resource giữa hai lần gọi còn có thể dẫn tới đóng sai handle hoặc giải phóng nhầm permit.

### 4.4. Rò rỉ bộ nhớ

Nếu aspect giữ reference đến `request`, `response`, `args`, exception hoặc context sau khi lời gọi xong, object graph có thể tiếp tục reachable qua aspect instance lâu sống. Vì vậy GC chưa thể thu gom dù request đã kết thúc.

Một biến field duy nhất thường chỉ giữ *một* đồ thị object tại một thời điểm, nhưng vẫn có thể giữ đồ thị đó quá lâu. Một `Map<requestId, Context>` hoặc danh sách được tích lũy không giới hạn thì còn có thể tăng bộ nhớ tỷ lệ với số lần gọi.

### 4.5. Deadlock và suy giảm hiệu năng khi sửa sai bằng khóa quá rộng

Một phản ứng phổ biến là thêm `synchronized` cho toàn bộ around advice. Cách này có thể làm hai request không ghi đè lên nhau tại thời điểm đó, **nhưng lại tuần tự hóa mọi lời gọi dùng chung lock**. Nếu `proceed()` chứa I/O, gọi dịch vụ từ xa hoặc chờ tác vụ khác, contention và độ trễ có thể tăng mạnh; còn có nguy cơ deadlock khi luồng gọi lồng nhau giữ các khóa khác.

Giải pháp đúng thường là **không chia sẻ state của invocation**, thay vì khóa toàn bộ quá trình xử lý chỉ để bảo vệ một biến đáng lẽ là biến cục bộ.

## 5. Cách sửa ưu tiên: biến cục bộ trong around advice

Với lời gọi đồng bộ, biến cục bộ thường là lựa chọn đơn giản và rõ ràng nhất:

```java
// Mã giả, phụ thuộc cơ chế proceed của hệ thống AOP.
Object around(String requestId) throws Throwable {
    long startNanos = System.nanoTime();
    String correlationId = requestId;

    try {
        Object result = proceed();
        recordSuccess(correlationId, result);
        return result;
    } catch (Throwable error) {
        recordFailure(correlationId, error);
        throw error;
    } finally {
        recordLatency(correlationId, System.nanoTime() - startNanos);
    }
}
```

Mỗi invocation có một bộ local variables riêng, kể cả khi nhiều invocation chạy song song trên cùng một instance aspect. Không có field mutable cần tranh chấp cho `correlationId` hay `startNanos`.

Các điểm cần nhớ:

1. Một **reference cục bộ** vẫn có thể trỏ vào một object mutable được các thread khác chia sẻ. Local variable không tự làm object trở nên thread-safe; nó chỉ tách vị trí lưu tham chiếu theo invocation.
2. `requestId` phải lấy từ nguồn đáng tin và được kiểm tra phù hợp; không mặc định có thể đưa mọi ID/người dùng vào log.
3. Nếu telemetry có thể lỗi, cần chính sách bảo đảm sự cố logging không vô tình che ngoại lệ nghiệp vụ. Một `finally` chứa lệnh ném lỗi vẫn có thể thay thế kết quả/ngoại lệ ban đầu.
4. Nếu `proceed()` trả về một tác vụ bất đồng bộ, thời điểm **trả đối tượng đại diện cho kết quả** không nhất thiết là thời điểm **công việc hoàn tất**. Để đo thời lượng tác vụ, phải gắn cleanup với lifecycle của tác vụ đó.

Biến local phù hợp khi tất cả logic cần context nằm trong một dynamic call scope. Nếu nhiều method cần đọc cùng context mà không thể truyền qua tham số, cân nhắc công cụ truyền context có scope rõ ràng.

## 6. Ví dụ chạy được: tái hiện ghi đè state giữa hai request

Mô phỏng dưới đây dùng `java.lang.reflect.Proxy` để đặt một lớp advice trước một interface nghiệp vụ. Đây là **một minh họa của runtime interception**, không phải định nghĩa đầy đủ về pointcut hoặc weaving trong mọi hệ thống AOP.

Chương trình sử dụng `CountDownLatch` để chủ động sắp xếp hai lời gọi:

- A ghi `currentRequestId = "A"` rồi tạm chờ.
- B ghi `currentRequestId = "B"` sau khi A đã ghi.
- A và B cùng đọc field. Cả hai thấy `"B"` mặc dù A thuộc request khác.
- Bản sửa lưu ID của từng invocation vào **biến cục bộ**.

Tạo tệp `SharedAspectStateDemo.java`:

```java
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class SharedAspectStateDemo {

    interface Operation {
        String handle(String requestId);
    }

    static final class BusinessOperation implements Operation {
        @Override
        public String handle(String requestId) {
            return "ok:" + requestId;
        }
    }

    // Sai: trạng thái invocation được giữ trong cùng một instance advice.
    static final class UnsafeAdvice implements InvocationHandler {
        private final Operation target;
        private volatile String currentRequestId;

        private final CountDownLatch aStored = new CountDownLatch(1);
        private final CountDownLatch bStored = new CountDownLatch(1);

        final Map<String, String> observed = new ConcurrentHashMap<>();

        UnsafeAdvice(Operation target) {
            this.target = target;
        }

        @Override
        public Object invoke(Object proxy, Method method, Object[] args)
                throws Throwable {
            String requestId = (String) args[0];

            if ("A".equals(requestId)) {
                currentRequestId = requestId;
                aStored.countDown();
                bStored.await();
            } else if ("B".equals(requestId)) {
                aStored.await();
                currentRequestId = requestId;
                bStored.countDown();
            } else {
                throw new IllegalArgumentException("Unknown demo request");
            }

            // A đọc "B": field đã bị B ghi đè trong khi A đang chờ.
            observed.put(requestId, currentRequestId);
            return callOriginal(target, method, args);
        }
    }

    // Đúng: mỗi invocation dùng tham chiếu requestId cục bộ của mình.
    static final class SafeAdvice implements InvocationHandler {
        private final Operation target;
        final Map<String, String> observed = new ConcurrentHashMap<>();

        SafeAdvice(Operation target) {
            this.target = target;
        }

        @Override
        public Object invoke(Object proxy, Method method, Object[] args)
                throws Throwable {
            String requestId = (String) args[0];

            // Mỗi lần gọi có requestId riêng, không ghi vào field chia sẻ.
            observed.put(requestId, requestId);
            return callOriginal(target, method, args);
        }
    }

    private static Object callOriginal(
            Operation target, Method method, Object[] args) throws Throwable {
        try {
            return method.invoke(target, args);
        } catch (InvocationTargetException failure) {
            throw failure.getCause();
        }
    }

    private static Operation wrap(
            Operation target, InvocationHandler advice) {
        return (Operation) Proxy.newProxyInstance(
                Operation.class.getClassLoader(),
                new Class<?>[]{Operation.class},
                advice
        );
    }

    private static String[] runTwoRequests(Operation operation)
            throws Exception {
        ExecutorService executor = Executors.newFixedThreadPool(2);
        try {
            Future<String> a = executor.submit(() -> operation.handle("A"));
            Future<String> b = executor.submit(() -> operation.handle("B"));

            return new String[]{
                    a.get(5, TimeUnit.SECONDS),
                    b.get(5, TimeUnit.SECONDS)
            };
        } finally {
            executor.shutdownNow();
        }
    }

    public static void main(String[] args) throws Exception {
        Operation target = new BusinessOperation();

        UnsafeAdvice unsafeAdvice = new UnsafeAdvice(target);
        Operation unsafe = wrap(target, unsafeAdvice);
        String[] businessResults = runTwoRequests(unsafe);

        SafeAdvice safeAdvice = new SafeAdvice(target);
        Operation safe = wrap(target, safeAdvice);
        runTwoRequests(safe);

        System.out.println("unsafe A observed="
                + unsafeAdvice.observed.get("A"));
        System.out.println("unsafe B observed="
                + unsafeAdvice.observed.get("B"));
        System.out.println("safe A observed="
                + safeAdvice.observed.get("A"));
        System.out.println("safe B observed="
                + safeAdvice.observed.get("B"));
        System.out.println("business results="
                + businessResults[0] + "," + businessResults[1]);
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac SharedAspectStateDemo.java
java SharedAspectStateDemo
```

Kết quả mong đợi khi chương trình chạy bình thường:

```text
unsafe A observed=B
unsafe B observed=B
safe A observed=A
safe B observed=B
business results=ok:A,ok:B
```

**Vì sao kết quả có tính xác định?** `aStored` buộc B chờ A lưu `"A"`; `bStored` buộc A chờ B lưu `"B"` trước khi A đọc. Sau đó cả hai đọc trường `volatile` đã được B cập nhật. Đây là tình huống có điều phối rõ ràng, không dựa vào việc “chạy nhiều lần may ra gặp race”. Hai request vẫn trả đúng kết quả nghiệp vụ, nhưng bản ghi quan sát của A đã sai; đây chính là kiểu lỗi có thể ẩn rất lâu trong hệ thống thật.

Map `observed` trong demo được dùng như **bộ sưu tập kết quả kiểm thử**, có hai key cố định. Nó không phải lời khuyên lưu mọi request vĩnh viễn trong map của aspect thật: với request ID liên tục mới, map không có eviction có thể tăng không giới hạn.

**Giới hạn của ví dụ:** `Proxy` chỉ áp dụng cho lời gọi đi qua proxy interface này; một hệ thống weave trực tiếp vào bytecode có thể có các join point khác. Quy tắc tránh state dùng chung vẫn đúng bất kể loại interception nếu instance advice được tái sử dụng. Các timeout 5 giây là guard cho demo, không phải bảo đảm hiệu năng ở mọi môi trường.

## 7. Vì sao khóa, volatile và atomic không thay thế được scope?

Bốn kỹ thuật thường bị nhầm lẫn:

| Cách xử lý | Nó bảo đảm điều gì? | Tại sao chưa đủ cho request state? |
| --- | --- | --- |
| `volatile` | Visibility và quy tắc ordering nhất định cho đọc/ghi biến | A vẫn có thể thấy giá trị B vừa ghi |
| `AtomicReference` | Thao tác atomic trên **một** tham chiếu dùng chung | Tham chiếu vẫn thuộc một chỗ lưu cho nhiều request |
| `synchronized` hoặc lock | Bảo vệ critical section theo cùng cơ chế khóa | Muốn A giữ ID của A qua toàn bộ `proceed()` có thể phải khóa cả nghiệp vụ, gây contention và deadlock |
| Concurrent collection | An toàn ở các thao tác được công cụ bảo đảm trên cấu trúc dữ liệu | Không tự đặt hạn dùng, ownership, quan hệ giữa record và invocation |

Một lock bao quanh chỉ lệnh ghi `currentRequestId` không bảo đảm A đọc được ID A sau khi B cập nhật. Muốn dùng cấu trúc dùng chung một cách đúng đắn cần **định danh chính xác mỗi invocation, quản lý vòng đời và chỉ giữ dữ liệu cần thiết**; nhưng với một ID chỉ được dùng tại entry/exit, local variable ngắn gọn hơn nhiều.

Khi có trạng thái tổng hợp thực sự được phép chia sẻ (ví dụ tổng số lần advice chạy), các bộ đếm atomic hoặc loại concurrent phù hợp là hợp lý:

```java
// Minh họa: đây là aggregate metric, không phải state một request.
private final java.util.concurrent.atomic.LongAdder callCount =
        new java.util.concurrent.atomic.LongAdder();

void beforeInvocation() {
    callCount.increment();
}
```

`LongAdder` phù hợp cho bộ đếm cộng dồn trong nhiều kịch bản cạnh tranh; khi đọc `sum()` đồng thời với cập nhật, kết quả là snapshot không nhất thiết atomic so với tất cả cập nhật đang diễn ra. Nó không thích hợp để lưu correlation ID hay identity của request.

## 8. Khi cần context ở nhiều lớp lời gọi: ThreadLocal có giới hạn rõ ràng

Trong một call stack đồng bộ, đôi khi nhiều lời gọi sâu bên trong cần đọc cùng correlation context mà không truyền tham số qua từng hàm. `ThreadLocal` gắn một giá trị với từng thread và có thể giúp tránh chia sẻ giá trị giữa các thread *khi được quản lý đúng*.

**Mã sai:**

```java
// Minh họa, không phải chương trình Java độc lập.
static final ThreadLocal<RequestContext> CURRENT = new ThreadLocal<>();

Object around(RequestContext request) throws Throwable {
    CURRENT.set(request);
    return proceed(); // Nếu lỗi hoặc thread pool tái sử dụng, context còn sót.
}
```

Nếu dùng thread pool, thread có thể xử lý request khác sau đó. Vì thiếu cleanup, context cũ có thể bị giữ lâu, lộ sang xử lý sau hoặc làm object graph không thể được GC thu gom theo kỳ vọng.

**Mẫu quản lý scope tốt hơn:**

```java
// Minh họa, không phải chương trình Java độc lập.
private static final ThreadLocal<RequestContext> CURRENT =
        new ThreadLocal<>();

Object around(RequestContext current) throws Throwable {
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
}
```

Vì sao phải lưu `previous`? Nếu advice có thể lồng nhau trên cùng thread, một scope bên trong cần **phục hồi context của scope ngoài**, thay vì xóa bỏ nó. `finally` được dùng để xử lý cả đường trả kết quả và đường ngoại lệ.

Điều kiện để cách này phù hợp:

1. Nhiệm vụ được thực hiện trong thread có vòng đời rõ ràng.
2. Việc thiết lập và phục hồi được cân bằng ở **mọi đường kết thúc**, kể cả failure.
3. Context nhỏ, không giữ các object khổng lồ hoặc bí mật không cần thiết.
4. Một context không bị dùng làm căn cứ phân quyền vượt quá thời điểm hoặc nơi đã được kiểm chứng.
5. Nếu công việc chuyển thread, có cơ chế truyền context riêng; `ThreadLocal` thông thường **không tự động đi theo logical request**.

**Tránh lạm dụng `InheritableThreadLocal`:** nó không phải cơ chế truyền context request đáng tin cậy qua executor pool; thread đã tồn tại có thể không nhận giá trị mới và thời điểm sao chép không tương ứng vòng đời task. Một số runtime cung cấp cơ chế structured context hoặc scoped context riêng; cần đối chiếu phiên bản Java và đặc tính công nghệ thay vì giả định chúng giống `ThreadLocal`.

## 9. Yêu cầu bất đồng bộ: vòng đời logic dài hơn lời gọi phương thức

Đây là trường hợp dễ bị bỏ sót khi đã quen với advice đồng bộ.

Giả sử `proceed()` trả về `CompletionStage<T>`. Method có thể trả về ngay trong khi phép tính còn chạy ở thread khác. Nếu quanh advice chỉ lưu thời điểm bắt đầu và ghi “hoàn tất” trong `finally` sau khi `proceed()` trả về stage, số đo là **thời gian tạo stage**, chưa chắc là thời gian công việc thật sự hoàn tất.

Mô hình thời gian:

```text
Thread gọi
  around advice bắt đầu
        |
        +--> proceed() trả CompletionStage [chưa xong]
        |
  around advice thoát -------------------------------+
                                                       |
Worker thread                                          |
  thực thi công việc -----------------------------------+
  stage hoàn tất
        |
        +--> callback ghi nhận kết quả/cleanup
```

Khi muốn theo dõi *completion* của tác vụ, context theo invocation phải được gắn đúng vòng đời bất đồng bộ. Ví dụ ở mức ý tưởng:

```java
// Minh họa, không phải chương trình độc lập.
// Hàm delegate() được giả định trả CompletionStage<Result>.
long startNanos = System.nanoTime();
String localRequestId = requestId;

CompletionStage<Result> stage = delegate();

return stage.whenComplete((result, failure) -> {
    long elapsed = System.nanoTime() - startNanos;
    recordOutcome(localRequestId, elapsed, failure);
});
```

**Những giới hạn quan trọng của minh họa:**

- Callback `whenComplete` có thể chạy trên thread hoàn tất stage hoặc thread khác, tùy completion state và thư viện. Không đọc `ThreadLocal` của thread ban đầu bên trong callback rồi tưởng nó vẫn đại diện cho request.
- `whenComplete` tạo một stage phụ thuộc. Nếu callback ném ngoại lệ, cách stage kết thúc có thể bị ảnh hưởng theo hợp đồng `CompletionStage`. Logger/metric recorder phải có chính sách lỗi rõ ràng.
- Nếu lời gọi tạo stage thất bại **trước khi trả stage**, advice cần xử lý đường ngoại lệ đồng bộ.
- Nếu một thao tác bị hủy, timeout hoặc không bao giờ hoàn tất, cần thiết kế hợp đồng cleanup/deadline và tránh giữ state vô hạn.
- Một closure callback capture request object lớn có thể giữ nó trong toàn bộ thời gian stage pending. Chỉ capture thông tin tối thiểu, bất biến và được phép sử dụng.
- Không giả định `CompletableFuture.cancel(...)` sẽ tự dừng thread hoặc đóng mọi resource; quản lý cancellation phụ thuộc hợp đồng của công việc thực tế.

Nếu nhiều request cùng chạy, **context theo logical task** là cách mô tả đúng hơn context “mỗi thread” trong hệ thống bất đồng bộ. Truyền context qua tham số hoặc một immutable context object thường dễ kiểm tra ownership hơn.

## 10. Vòng đời, phạm vi aspect và quản lý trạng thái đúng chỗ

Trước khi chọn nơi lưu state, phân biệt:

**Per-invocation:** dữ liệu có ý nghĩa duy nhất trong một lần lời gọi, như `startNanos` hoặc `requestId`. Nên đặt trong biến cục bộ advice hoặc một context riêng được truyền qua các bước liên quan.

**Per-target/per-object:** dữ liệu thuộc về một đối tượng nghiệp vụ cụ thể. Có thể đặt ở owner của đối tượng đó hoặc mô hình aspect có vòng đời gắn với đối tượng khi công nghệ hỗ trợ. Nhưng nhiều thread có thể đồng thời sử dụng **cùng đối tượng đích**, nên per-target không tự đồng nghĩa thread-safe.

**Per-thread:** chỉ hợp lý khi ngữ nghĩa thực sự theo thread và cleanup chuẩn. Một request chuyển qua hai thread không còn trùng một per-thread scope; hai request chạy nối tiếp trên một thread cũng không được chia sẻ ngữ cảnh.

**Per-application/per-aspect-instance:** phù hợp cho configuration không đổi, bộ đếm tổng hợp, cache có chính sách và những resource được chia sẻ có owner rõ ràng. Không phù hợp cho field `currentUser`, `currentTenant` hoặc `requestResult` dùng như “biến hiện tại”.

**Per-transaction/per-operation:** đôi khi logical operation kéo dài qua nhiều lời gọi lồng nhau. Cần một context độc lập có ID, lifecycle và owner rõ ràng, thay vì dựa vào field singleton. Nếu nhiều operations có thể overlap, cơ chế lưu phải tách từng operation.

Một cache hoặc registry tập trung đôi khi là yêu cầu thực sự. Khi đó cần policy gồm: key ổn định đúng identity, giới hạn số entry, TTL hoặc signal hoàn tất để xóa, xử lý cancel/failure, không chứa bí mật thô, và monitoring retained memory. Đừng biến map không giới hạn thành giải pháp mặc định cho vấn đề chia sẻ state.

## 11. Reentrancy: lời gọi lồng nhau ngay trong cùng một thread

Lỗi tương tự có thể xảy ra **không cần hai thread** nếu aspect được gọi lồng nhau và ghi state vào cùng field:

```text
Advice outer: currentMethod = "outer"
  → proceed(outer)
      → gọi inner
          → Advice inner: currentMethod = "inner"
          → proceed(inner), rồi trả về
  → Advice outer đọc currentMethod = "inner"  ← Sai!
```

`synchronized` trên method advice có thể **không giúp**, vì một lock reentrant cho phép cùng thread vào lại và thay đổi field. Trường hợp này củng cố nguyên tắc: **request state phải gắn với invocation, không gắn với thread hoặc instance một cách tùy tiện**.

Nếu buộc dùng ngữ cảnh theo thread, cấu trúc stack có push/pop cân bằng và `finally` có thể đại diện cho nested scopes; nhưng làm thế tăng độ phức tạp và vẫn phải giải quyết chuyển thread. Nếu chỉ cần lưu thông tin cho đoạn advice đang chạy, dùng local variables vẫn tốt hơn.

## 12. Cảnh báo khi lưu context vào map dùng chung

Một số hệ thống lưu:

```java
// Mã minh họa: cần policy vòng đời và giới hạn trước khi dùng thật.
private final Map<String, RequestContext> contexts =
        new ConcurrentHashMap<>();
```

Cách này **không mặc nhiên sai** nếu thực sự cần tra cứu context theo ID qua nhiều thành phần, nhưng khác hẳn việc dùng `currentContext`. Để an toàn:

1. Dùng key không va chạm trong phạm vi cần bảo đảm và xác nhận quyền truy cập trước khi trả context.
2. Xóa entry khi request hoàn tất, bị lỗi, hủy hoặc hết hạn.
3. Có giới hạn capacity và giám sát số entry, TTL, eviction, tỷ lệ miss.
4. Không chứa trực tiếp token, mật khẩu hoặc request body nếu không cần.
5. Không giả định mọi thao tác nhiều bước trên concurrent map là một giao dịch nguyên tử; dùng API atomic thích hợp hoặc thiết kế trạng thái rõ ràng.
6. Kiểm tra tình huống ID được tái sử dụng, retry và nhiều request đồng thời.
7. Phân biệt completion của lời gọi đồng bộ với completion thực sự của tác vụ bất đồng bộ.

Một `WeakHashMap` cũng không thay thế ownership: key có thể được giữ sống ở nơi khác, value có thể tham chiếu ngược key, và behavior/đồng bộ có thể không đáp ứng yêu cầu. Chính sách giải phóng theo lifecycle thường rõ ràng và đáng kiểm chứng hơn.

## 13. Hậu quả bảo mật của việc lẫn context giữa request

Đặt dữ liệu nhạy cảm trong field chung của aspect có thể làm lỗi phân quyền dễ xuất hiện:

- Request A thuộc tenant X, nhưng advice đọc tenant Y từ request B.
- Log hoặc trace của người dùng A mang ID người dùng B.
- Bộ điều tiết/throttle ghi nhận sai chủ thể, làm một người dùng ảnh hưởng người khác.
- Một permission decision nhận identity không tương ứng với lần gọi gốc.
- Một request đã kết thúc vẫn để lại reference tới credential, token hoặc payload trong instance dài hạn.

Khi thiết kế aspect liên quan bảo mật, **lấy thông tin từ nguồn đã xác thực trong đúng invocation** và không dùng shared mutable field làm nguồn chân lý. Context bất biến hoặc truyền tường minh giúp việc kiểm tra dễ hơn, nhưng bản thân đối tượng bất biến không chứng minh dữ liệu là đáng tin: cần kiểm soát nguồn, phạm vi, quyền và thời điểm hợp lệ.

Ngoài ra, hãy tránh log toàn bộ context “để dễ debug”: có thể vô tình tiết lộ giá trị nhạy cảm. Chỉ chọn những trường an toàn được cho phép và kiểm soát thời gian lưu trữ.

## 14. Kiểm thử phát hiện lỗi đồng thời và rò rỉ state

### 14.1. Tạo lịch xen kẽ có kiểm soát

Một test chạy hai thread nhưng không có phối hợp có thể không gặp race trong hàng nghìn lần. Với lỗi đã biết, sử dụng `CountDownLatch`, barrier hoặc các điểm dừng test để cố ý tạo thứ tự:

```text
A: ghi state của A → chờ
B: chờ A ghi → ghi state của B → cho phép A tiếp tục
A: đọc state
Test: A phải đọc A; nếu đọc B thì FAIL.
```

Bài demo trước sử dụng đúng chiến lược này. Trong test thực tế, thêm timeout cho chờ latch/future để tránh test treo khi code thay đổi, đồng thời xác nhận mọi task hoàn tất hoặc được hủy theo chính sách của test.

### 14.2. Kiểm thử isolation dưới concurrency

Chạy nhiều lời gọi độc lập có định danh khác nhau và bảo đảm:

- Mỗi bản ghi audit/metric/trace chứa identity của **chính invocation đó**.
- Không có request kết quả A bị ghép tham số hoặc exception của request B.
- Kết quả vẫn đúng khi thứ tự hoàn thành khác thứ tự bắt đầu.
- Không có lỗi khi nhiều thread gọi cùng aspect instance hoặc cùng target object.
- Advice lồng nhau phục hồi đúng context của scope bên ngoài.
- Aspect không bỏ qua cleanup trên đường exception, timeout, cancellation.

### 14.3. Kiểm thử thread pool và bất đồng bộ

Với executor có ít thread tái sử dụng:

1. Task 1 đặt context rồi kết thúc cả theo success/failure.
2. Task 2 chạy trên cùng worker và không được nhìn thấy context cũ.
3. Nếu task 2 có context mới, phải thấy đúng context mới.
4. Nếu code truyền task sang thread khác, context cần được truyền/chỉ định tại đúng boundary.
5. Sau khi chuỗi task kết thúc, kiểm tra không còn resource hoặc object lớn bị giữ qua `ThreadLocal`/queue.

Đặc biệt test callback chạy **sau khi around advice đồng bộ đã thoát**; đây là nơi mô hình vòng đời không đúng thường lộ ra.

### 14.4. Theo dõi bộ nhớ và hiệu năng

Sau kiểm thử tải dài hơn, quan sát live heap sau GC, allocation rate, số task tồn đọng, thread pool, queue depth và kích thước registry/context map. Nếu nghi leak, phân tích heap dump theo GC roots và đường retained references: tìm aspect instance, static field, `ThreadLocalMap`, lambda/callback và map giữ `RequestContext`.

Việc sử dụng heap dump, profiling hoặc logging nặng trên hệ thống đang phục vụ yêu cầu có thể có chi phí đáng kể và tạo dữ liệu chứa thông tin nhạy cảm. Chọn quy trình phù hợp và không dựa vào một ảnh chụp bộ nhớ để kết luận leak.

### 14.5. Không dừng ở việc test trả về đúng kết quả

Một aspect logging có thể ghi sai ID nhưng **không thay đổi return value**, giống ví dụ `SharedAspectStateDemo`. Vì vậy test cần kiểm tra **observable side effects** do advice tạo ra, không chỉ hàm nghiệp vụ vẫn trả đúng dữ liệu.

## 15. Danh sách sai lầm phổ biến và cách thay thế

| Sai lầm | Vì sao sai | Hướng xử lý |
| --- | --- | --- |
| Trường `currentRequest` trong aspect dùng chung | Lẫn state giữa invocation, giữ tham chiếu lâu | Local variable hoặc context theo invocation |
| Trường `startTime` để đo mọi lời gọi | Bị lời gọi khác ghi đè | `long startNanos` cục bộ |
| Thêm `volatile` hoặc `AtomicReference` vào field request | Visibility/atomicity không sửa ownership | Tách state cho từng invocation |
| `synchronized` bao quanh toàn bộ `proceed()` | Tuần tự hóa công việc, contention lớn | Không chia sẻ request state; chỉ lock trạng thái tổng hợp thật cần |
| Dùng `ThreadLocal` nhưng không cleanup | Thread pool giữ dữ liệu qua request khác | `try/finally`, restore previous hoặc remove |
| Coi `ThreadLocal` là context bất đồng bộ | Logical request có thể đổi thread | Truyền context theo task hoặc cơ chế scope phù hợp |
| Ghi end-time ở `finally` khi nhận `CompletionStage` | Chỉ đo thời điểm trả stage | Theo dõi completion/cancel theo lifecycle thật |
| Lưu vô hạn `requestId → Context` | Heap tăng và lưu dữ liệu quá hạn | Dùng giới hạn, TTL và xóa theo completion |
| Dùng state aspect làm căn cứ phân quyền | Dữ liệu có thể bị lẫn request | Lấy identity đã xác thực của invocation hiện tại |
| Chỉ test single-thread | Race hoặc nesting không xuất hiện | Deterministic concurrency test và test reentrancy |
| Ghi toàn bộ args/context để debug | Giữ reference, lộ bí mật, tốn tài nguyên | Bản tóm tắt an toàn, không giữ object gốc |

## 16. Checklist khi review một aspect dùng chung

- [ ] Đã xác minh mô hình khởi tạo aspect và khả năng nhiều invocation dùng chung một instance?
- [ ] Field có thuộc một request/invocation hay thuộc cấu hình/aggregate được phép chia sẻ?
- [ ] Nếu bỏ một request, field của aspect có còn giữ reference đến object của request đó?
- [ ] `requestId`, user/tenant identity, start time, result, exception đã là local hoặc context scope phù hợp?
- [ ] Có data race, reentrancy hoặc việc lời gọi khác ghi đè field không?
- [ ] Có dùng `volatile`/atomic/lock để che lỗi state bị đặt sai vòng đời không?
- [ ] Nếu dùng `ThreadLocal`, mọi đường success/failure/nested đều phục hồi hoặc dọn đúng không?
- [ ] Nếu công việc bất đồng bộ, context/cleanup theo đúng logical completion chưa?
- [ ] Nếu dùng map/queue, capacity, TTL, cancellation cleanup và retained references được quản lý chưa?
- [ ] Event quan sát có đúng ID của invocation và không lẫn bí mật giữa các người dùng?
- [ ] Kiểm thử có trường hợp nhiều thread, nested advice và thứ tự hoàn tất đảo ngược?
- [ ] Việc sửa lỗi bảo toàn kết quả và ngoại lệ nghiệp vụ?

## Kết luận

**Aspect được chia sẻ không đồng nghĩa trạng thái của từng yêu cầu có thể chia sẻ.** Một field như `currentRequestId`, `currentUser` hoặc `startNanos` là nơi lưu không phù hợp cho nhiều invocation đồng thời, kể cả khi dùng `volatile` hoặc atomic reference. Lỗi có thể xuất hiện cả với lời gọi lồng nhau trên cùng thread.

Với lời gọi đồng bộ, **biến cục bộ của advice** là phương án ưu tiên. Khi phải truyền context qua nhiều lớp hoặc nhiều thread, cần một cơ chế có **identity, owner, phạm vi sống và cleanup rõ ràng**. Kiểm thử nên cố ý tạo interleaving, đo cả side effects của advice và kiểm tra rằng request đã kết thúc không tiếp tục bị giữ trong state lâu sống.

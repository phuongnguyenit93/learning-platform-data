# Lưu trạng thái theo lời gọi thay vì trạng thái dùng chung trong Aspect

## 1. Vấn đề: trạng thái của advice thuộc về ai?

Trong **lập trình hướng khía cạnh (Aspect-Oriented Programming – AOP)**, aspect đóng gói các **pointcut** và **advice** cho mối quan tâm cắt ngang như logging, tracing, đo thời gian, kiểm soát truy cập hoặc audit. Nhiều advice cần ghi nhớ dữ liệu ngắn hạn: thời điểm bắt đầu, mã tương quan, giá trị đối số ban đầu, kết quả trung gian hoặc một cờ cho biết đã thực hiện cleanup.

Câu hỏi quan trọng là: **dữ liệu ấy thuộc về một lần thực thi join point, một target object, một request, một thread, hay thuộc toàn bộ aspect?**

Nếu một aspect instance được dùng chung cho nhiều lượt gọi, việc lưu dữ liệu **riêng của từng lần gọi** trong **field của aspect** có thể gây sai ngay cả khi không có lỗi cú pháp:

```java
// Minh họa vấn đề, không phải chương trình độc lập.
final class IncorrectTimingAspect {
    private long startNanos;

    void before() {
        startNanos = System.nanoTime();
    }

    void after() {
        long elapsed = System.nanoTime() - startNanos;
        record(elapsed);
    }
}
```

Với hai lượt gọi chồng lấn, lần gọi thứ hai có thể ghi đè `startNanos` trước khi lần thứ nhất chạy `after`. Thời gian của lần đầu bị đo từ mốc của lần sau. Dùng `volatile long` không sửa được lỗi gắn sai **một mốc chung** cho **hai lượt invocation**.

**Nguyên tắc:** *Dữ liệu chỉ có ý nghĩa trong một lần thực thi advice/join point nên được giữ trong phạm vi riêng của lần ấy; dữ liệu thực sự thuộc phạm vi dùng chung mới được giữ trong shared aspect state, với quy tắc concurrency tương ứng.*

> **Phạm vi:** Bài này nói về AOP cơ bản và nâng cao nói chung, không phụ thuộc một công cụ cụ thể. “Shared aspect”, “around advice”, “before/after advice”, “join point context”, “control flow” hay “proxy” được dùng theo nghĩa khái niệm. Mỗi hệ thống AOP có thể có API và chính sách instantiation riêng; những ví dụ Java 17+ bên dưới minh họa nguyên tắc quản lý trạng thái, không phải cú pháp pointcut phổ quát.

## 2. Ba trục phải phân biệt

Một phân tích đúng cần tách:

1. **Vòng đời aspect instance:** dùng chung, theo target, theo flow, theo invocation, hoặc scope khác.
2. **Vòng đời dữ liệu:** mốc thời gian riêng một lời gọi, metadata có thể dùng chung, trạng thái của target, request context, session hoặc cache.
3. **Phạm vi interception/weaving:** lời gọi nào thực sự qua advice, chẳng hạn proxy invocation hoặc method execution đã được dệt.

```text
Aspect instance: shared
    |
    +--> Invocation A  -> InvocationState[A]
    |
    +--> Invocation B  -> InvocationState[B]
    |
    +--> Invocation C  -> InvocationState[C]

MetadataCache: shared, immutable/thread-safe
```

**Một shared aspect không buộc phải dùng shared invocation state.** Instance advice có thể tồn tại lâu nhưng mỗi lần method được gọi vẫn có **stack frame và local variables riêng**.

Ngược lại, **một aspect instance mới theo từng invocation** chưa chắc giải quyết mọi vấn đề nếu nó dùng một `static` mutable field hoặc một singleton dependency không thread-safe.

### Scope là ý nghĩa, không chỉ nơi lưu kỹ thuật

| Loại dữ liệu | Scope hợp lý thường gặp | Không nên mặc định |
| --- | --- | --- |
| Thời điểm bắt đầu một method | Một invocation | Field shared `start` |
| Đối số/kết quả tạm cho một advice | Local/invocation context | Field `currentArguments` |
| Tổng lượt gọi toàn dịch vụ | Shared metric recorder thread-safe | Mỗi invocation có bộ đếm riêng và quên tổng hợp |
| Metadata cố định của method | Shared immutable cache có key đúng | Lấy lại Reflection phức tạp vô ích mọi lần |
| Trạng thái riêng target | Per-target hoặc khóa theo identity | Theo request nếu target được chia sẻ |
| Trace/correlation ID | Request/task context được truyền phù hợp | Một field shared hoặc giả định ThreadLocal luôn đi theo task |
| Một retry attempt count | Invocation local của thao tác retry | `currentAttempt` của aspect singleton |
| Session/user context | Scope được xác thực và làm sạch | Thread hoặc aspect singleton mặc định |

Không phải concern nào cũng cần state. Một advice kiểm tra giá trị đối số trực tiếp có thể hoàn toàn stateless.

## 3. Vì sao shared field sai: hai loại chồng lấn

### 3.1. Concurrency giữa hai thread

Giả sử shared aspect có field `currentId`:

```text
Thread A                         Thread B
-----------------------------------------------
before(A):
  currentId = "A"
                                 before(B):
                                   currentId = "B"
after(A):
  log(currentId)   // Ghi "B": sai
                                 after(B):
                                   log(currentId)
```

Các thao tác đọc/ghi cùng một field có thể bị **data race** nếu không đồng bộ. Dù dùng synchronization để giải quyết memory visibility, ý nghĩa “ID nào thuộc invocation nào” vẫn đòi state riêng. Nếu lock chỉ bảo vệ từng phép set/get, sau khi nhả lock thread khác vẫn có thể ghi đè.

### 3.2. Reentrancy ngay trên một thread

**Reentrancy** xảy ra khi một advice/target làm phát sinh thêm join point được advice xử lý **trước khi lượt bên ngoài kết thúc**. Không nhất thiết cần nhiều thread.

```text
before(outer): currentId = outer
  target.outer()
    -> before(inner): currentId = inner
       target.inner()
       after(inner): currentId = inner
after(outer): currentId = inner   // Sai dù chỉ một thread
```

Nếu giữ một field `currentId` chung, outer mất thông tin ngay trong một chuỗi gọi đồng bộ. Thêm `synchronized` quanh mỗi phép đọc/ghi không khôi phục được ID outer. Ngay cả khóa reentrant quanh cả chuỗi vẫn cho phép cùng thread đi vào lần gọi inner; nếu dữ liệu chỉ có một slot, nó vẫn bị ghi đè.

**Cần scope theo lượt vào/ra, không chỉ cơ chế khóa.**

### 3.3. Tại sao `volatile` và atomic không giải quyết correlation?

`volatile` hỗ trợ tính hiển thị của giá trị giữa thread, không biến một field thành nhiều slot cho nhiều invocation. `AtomicReference<String>` cho phép cập nhật atomic một reference, nhưng vẫn chỉ giữ **một reference chung**. Cả hai không tự biết after của invocation A phải đọc snapshot A chứ không phải snapshot B.

Đây là **lỗi mô hình dữ liệu**, không đơn thuần là một phép ghi chưa atomic.

## 4. Giải pháp ưu tiên: local state trong around advice

Khi một **around advice** bao trọn lần gọi và API hỗ trợ `proceed` hoặc cơ chế tương đương, state nên được khai báo **bên trong invocation của advice**:

```java
// Pseudocode Java của around advice, không phải tệp biên dịch độc lập.
Object around(ProceedingJoinPoint joinPoint) throws Throwable {
    long start = System.nanoTime();       // Local riêng lần gọi.
    String operation = joinPoint.name();   // Local riêng lần gọi.
    try {
        return joinPoint.proceed();
    } finally {
        recordDuration(operation, System.nanoTime() - start);
    }
}
```

`ProceedingJoinPoint` ở đây là **tên interface giả định để diễn đạt nguyên tắc**, không phải API tiêu chuẩn của Java SE. Trong công cụ thật, hãy thay bằng API invocation/proceed tương ứng.

Mỗi lần advice được gọi có stack frame riêng:

```text
around(A):
  start_A, operation_A
  proceed(A)

around(B):
  start_B, operation_B
  proceed(B)
```

Hai lời gọi có thể chạy đồng thời hoặc lồng nhau nhưng `start_A` và `start_B` **không phải cùng một biến**.

### Vì sao `finally`?

Nếu mục tiêu là **đóng scope hoặc ghi duration dù thành công hay lỗi**, `finally` thường diễn đạt đúng ý định: phần cleanup chạy ở cả đường return và throw theo semantics Java/AOP tương ứng.

Tuy vậy, **exception từ chính cleanup** có thể che exception của target. Với logging/metric phụ trợ, cần chính sách cô lập lỗi ghi metric. Với audit bắt buộc, lỗi ghi nhận có thể phải thay outcome. Không áp dụng `catch(Throwable) {}` nuốt mọi lỗi làm cách giải quyết mặc định.

### `start` phải được tạo ở đâu?

Đặt `start` trước `proceed` nếu muốn đo **thời gian mà around bao phủ**. Nếu đặt sau `proceed`, bạn chỉ đo thời gian hậu xử lý, không đo thời gian target. Nếu advice bên ngoài có retry, duration đo cả retry; nếu advice nằm bên trong retry, duration của từng attempt có thể khác. Vị trí nesting và ordering tác động tới nghĩa của metric.

## 5. Chọn dữ liệu nào được phép dùng chung

Không phải mọi mutable field đều sai. Một shared aspect có thể chứa **shared state hợp lệ**:

- `LongAdder` đếm tổng lời gọi.
- Một immutable policy snapshot hoặc reference publish an toàn tới cấu hình mới.
- Cache metadata theo method/type, có key chuẩn và synchronization phù hợp.
- Logger hoặc audit sink đã được thiết kế thread-safe.
- Bộ giới hạn tốc độ có state dùng chung đúng theo policy.
- Circuit state chung nếu đó là contract của cơ chế điều khiển lỗi.

Nhưng các field như `currentUser`, `currentRequestId`, `currentResult`, `startTime`, `lastThrowable` hoặc `retryAttempts` thường **không phù hợp** nếu chỉ phục vụ một invocation.

### Ví dụ tổng metric đúng scope

```java
// Một helper Java đơn giản; có thể nằm trong class phù hợp.
final class InvocationCounter {
    private final java.util.concurrent.atomic.LongAdder total =
            new java.util.concurrent.atomic.LongAdder();

    void increment() {
        total.increment();
    }

    long count() {
        return total.sum();
    }
}
```

`LongAdder` hữu ích cho bộ đếm tranh chấp cao; `sum()` không nhất thiết là snapshot nguyên tử tuyệt đối khi concurrent updates vẫn đang diễn ra. Điều này hợp lý cho metric gần đúng tại thời điểm đọc, nhưng không tự phù hợp nếu yêu cầu một bộ đếm transaction chính xác với strong consistency.

**Dùng local state cho dữ liệu riêng và shared concurrency-safe component cho dữ liệu tổng** thường là cách tách trách nhiệm tốt.

## 6. Ví dụ Java 17+ chạy được: field dùng chung sai ngay khi lời gọi lồng nhau

Ví dụ này dùng **Java Dynamic Proxy** làm interceptor AOP nhỏ, không cần thư viện AOP bên ngoài. Nó tạo hai proxy trên cùng một target:

1. **Shared-field proxy** cố giữ `currentId` vào field handler dùng chung; lời gọi outer và inner lồng nhau làm field bị ghi đè.
2. **Invocation-local proxy** giữ `id` trong local variable của từng lần handler được gọi; outer và inner có state riêng.
3. **Nhánh lỗi** minh họa state local vẫn dùng được khi target ném ngoại lệ và `finally` luôn chạy.

Để tạo nested intercepted calls một cách rõ ràng, target được cấp **self reference trỏ tới proxy** và chủ động gọi `self.execute("inner")`. Đây là một lựa chọn **cố ý của demo**. Trong mô hình wrapper proxy phổ biến, `this.execute("inner")` bên trong raw target thường **không** quay lại proxy; nếu không qua proxy thì inner advice cũng không chạy. Hai hiện tượng phải được phân biệt.

### 6.1. Tệp `InvocationStateDemo.java`

```java
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;

public class InvocationStateDemo {

    interface Service {
        String execute(String id);
    }

    static final class Target implements Service {
        private Service self;

        void setSelf(Service self) {
            this.self = self;
        }

        @Override
        public String execute(String id) {
            System.out.println("target.enter " + id);

            if ("outer".equals(id)) {
                self.execute("inner");
            }

            if ("fail".equals(id)) {
                throw new IllegalArgumentException("rejected");
            }

            System.out.println("target.exit " + id);
            return "result:" + id;
        }
    }

    static Object proceed(Method method, Object target, Object[] args)
            throws Throwable {
        try {
            return method.invoke(target, args);
        } catch (InvocationTargetException wrapped) {
            throw wrapped.getCause();
        }
    }

    // Cố tình SAI: dùng chung một slot trạng thái cho mọi invocation.
    static final class SharedFieldHandler implements InvocationHandler {
        private final Service target;
        private String currentId;

        SharedFieldHandler(Service target) {
            this.target = target;
        }

        @Override
        public Object invoke(Object proxy, Method method, Object[] args)
                throws Throwable {
            currentId = (String) args[0];
            System.out.println("shared.before " + currentId);

            try {
                Object result = proceed(method, target, args);
                System.out.println("shared.after " + currentId);
                return result;
            } catch (Throwable error) {
                System.out.println("shared.error " + currentId);
                throw error;
            } finally {
                System.out.println("shared.finally " + currentId);
            }
        }
    }

    // ĐÚNG: local variable tách riêng cho mỗi lần handler chạy.
    static final class InvocationLocalHandler
            implements InvocationHandler {
        private final Service target;

        InvocationLocalHandler(Service target) {
            this.target = target;
        }

        @Override
        public Object invoke(Object proxy, Method method, Object[] args)
                throws Throwable {
            String id = (String) args[0];
            System.out.println("local.before " + id);

            try {
                Object result = proceed(method, target, args);
                System.out.println("local.after " + id);
                return result;
            } catch (Throwable error) {
                System.out.println(
                        "local.error " + id + " "
                        + error.getClass().getSimpleName());
                throw error;
            } finally {
                System.out.println("local.finally " + id);
            }
        }
    }

    static Service proxy(Service target, InvocationHandler handler) {
        return (Service) Proxy.newProxyInstance(
                Service.class.getClassLoader(),
                new Class<?>[] { Service.class },
                handler);
    }

    public static void main(String[] args) {
        System.out.println("== shared field ==");
        Target badTarget = new Target();
        Service bad = proxy(
                badTarget, new SharedFieldHandler(badTarget));
        badTarget.setSelf(bad);
        System.out.println("caller " + bad.execute("outer"));

        System.out.println("== invocation local ==");
        Target goodTarget = new Target();
        Service good = proxy(
                goodTarget, new InvocationLocalHandler(goodTarget));
        goodTarget.setSelf(good);
        System.out.println("caller " + good.execute("outer"));

        System.out.println("== exception ==");
        try {
            good.execute("fail");
        } catch (IllegalArgumentException error) {
            System.out.println("caller caught " + error.getMessage());
        }
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac -encoding UTF-8 InvocationStateDemo.java
java InvocationStateDemo
```

**Standard output dự kiến chính xác:**

```text
== shared field ==
shared.before outer
target.enter outer
shared.before inner
target.enter inner
target.exit inner
shared.after inner
shared.finally inner
target.exit outer
shared.after inner
shared.finally inner
caller result:outer
== invocation local ==
local.before outer
target.enter outer
local.before inner
target.enter inner
target.exit inner
local.after inner
local.finally inner
target.exit outer
local.after outer
local.finally outer
caller result:outer
== exception ==
local.before fail
target.enter fail
local.error fail IllegalArgumentException
local.finally fail
caller caught rejected
```

### 6.2. Vì sao shared-field proxy sai?

Khi gọi `bad.execute("outer")`, handler đặt `currentId = "outer"`. Target nhận outer rồi gọi `self.execute("inner")` — reference self đã được đặt thành **proxy**. Handler được gọi lần nữa và ghi `currentId = "inner"`. Khi inner kết thúc, field vẫn là `"inner"`.

Sau khi quay ra outer, `SharedFieldHandler` đọc lại **cùng field** và in:

```text
shared.after inner
shared.finally inner
```

Trong khi hai dòng cuối ấy thực chất thuộc **lượt outer**. Đây là lỗi correlation do **reentrancy**, không cần tạo thread thứ hai.

### 6.3. Vì sao local proxy đúng?

Trong `InvocationLocalHandler.invoke`, mỗi lời gọi tạo **biến local `id` riêng** từ argument của lần ấy. Outer giữ `"outer"` và inner giữ `"inner"`. Khi inner trả về, local variable của outer **không bị ghi đè**.

Do đó:

```text
local.after inner
local.finally inner
...
local.after outer
local.finally outer
```

phản ánh đúng hai invocation. Handler vẫn là **một instance chung** cho hai lời gọi, nhưng state cần correlation nằm trên từng stack frame.

### 6.4. Nhánh lỗi có mất state không?

`good.execute("fail")` ném `IllegalArgumentException("rejected")`. Reflection có thể bọc lỗi trong `InvocationTargetException`, nên hàm `proceed` mở lớp bọc để truyền Throwable gốc. Handler in `local.error fail IllegalArgumentException` rồi `local.finally fail`. Caller cuối cùng thấy đúng `rejected`.

Đoạn ví dụ không nuốt lỗi, không thay return value, và không dùng shared field để quyết định lỗi thuộc invocation nào.

### 6.5. Ý nghĩa của `target.setSelf(proxy)`

Chúng ta **cố ý** để target tự gọi một reference trỏ về proxy nhằm tạo **hai invocation advice lồng nhau**. Nếu thay `self.execute("inner")` bằng `this.execute("inner")` trong target và chỉ dùng proxy wrapper, lời gọi inner thường bypass handler. Khi đó demo không tạo nested advice, nhưng đây là vấn đề **interception coverage**, khác với tính đúng của shared field.

Một bytecode weaver hỗ trợ execution join point có thể can thiệp vào nested execution theo phạm vi khác. Không quy tắc hóa rằng mọi mô hình AOP đều có self-invocation giống Java Dynamic Proxy.

### 6.6. Giới hạn của ví dụ

- Một file Java SE với proxy interface, **không phải AOP engine/pointcut DSL hoàn chỉnh**.
- Handler shared-field cố ý sai để minh họa reentrancy; không dùng nó trong sản xuất.
- Ví dụ sử dụng một thread để có đầu ra xác định; shared-field cũng có lỗi trong đa luồng.
- Logger chỉ dùng `System.out.println`; metric/audit thật cần sink, redaction và error policy thích hợp.
- `id` và kết quả dạng chuỗi rất đơn giản; state mutable phức tạp còn cần ownership/synchronization.
- Không có retry, context propagation hoặc timer được triển khai trong demo chính.
- Không nên biến `self` proxy thành dependency vòng tròn mặc định chỉ để có nested advice; demo dùng nó có chủ đích để phơi bày lỗi.

## 7. Before và after tách rời: local state của hai advice có tự chia sẻ không?

Around advice lý tưởng cho phép giữ state giữa “trước” và “sau” bằng **cùng một stack frame**. Nhưng trong một số hệ thống AOP, người học có thể chỉ có **before advice** và **after advice** là hai phương thức Java riêng.

```text
before(joinPoint) -> tạo start
target(...)
after(joinPoint)  -> cần đọc lại start
```

Một biến local được khai báo **trong before** không tự chuyển thành biến local **của after**. Hai lần gọi advice là hai stack frames khác nhau. Cần một **cơ chế correlation** nếu thực sự phải truyền state từ before sang after.

### Những lựa chọn có thể dùng

1. **Around advice:** giữ state trong một invocation bao trọn target, nếu công cụ hỗ trợ.
2. **Invocation context object:** engine cung cấp một container gắn riêng với lượt gọi; before đặt value, after lấy đúng container ấy.
3. **Explicit scoped state:** một wrapper hoặc pipeline tự tạo object state rồi truyền giữa các hook theo invocation ID.
4. **Flow stack theo thread:** có thể dùng nếu toàn bộ scope đồng bộ cùng thread, và push/pop đúng thứ tự.
5. **Per-request/task context:** phù hợp nếu state cần được chia sẻ qua nhiều join point thuộc cùng request, không chỉ một method.

**Không nên mặc định có thể ghép đúng before và after chỉ bằng tên method, target object hoặc thread ID.** Một method có thể được gọi đệ quy, lồng nhau, chạy đồng thời hoặc cùng thread chạy nhiều request nối tiếp.

### Correlation key phải định danh đúng lượt gọi

Một key `(target,method)` có thể bị trùng giữa hai invocation cùng method trên cùng target. Một key `threadId` không phân biệt hai invocation lồng nhau trên cùng thread. Một key `requestId` có thể gộp nhiều method execution trong cùng request.

Nếu cần lưu “mốc thời gian của lần gọi X”, tốt nhất là có **invocation identity** hoặc một stack/scope bảo toàn cấu trúc lồng nhau. Không dùng identifier có phạm vi rộng hơn để giả làm identifier của từng lượt method.

## 8. Scoped stack cho lời gọi lồng nhau

Nếu một runtime chỉ có before/after và toàn bộ chuỗi chạy đồng bộ trên cùng thread, một cấu trúc stack theo thread có thể tương quan đúng hơn một field đơn:

```text
before outer  -> push State(outer)
before inner  -> push State(inner)
after inner   -> pop State(inner)
after outer   -> pop State(outer)
```

**Thứ tự LIFO** quan trọng. Nếu after chạy không theo thứ tự lồng, hoặc đã có async callback, stack thread có thể không phù hợp.

### Pseudocode minh họa

```java
// Mô tả ý tưởng, không phải chương trình độc lập.
ThreadLocal<Deque<InvocationState>> stack = ...;

void before(JoinPoint point) {
    stack.get().push(new InvocationState(point.id()));
}

void afterFinally(JoinPoint point) {
    InvocationState state = stack.get().pop();
    verifyMatch(state, point);
    if (stack.get().isEmpty()) {
        stack.remove();
    }
}
```

Các type `JoinPoint` và `InvocationState` được dùng như **khái niệm**. Với engine thật, phải xét:

- Advice before có chắc được gọi trước cùng một after-finally không?
- Một exception phát sinh ngay trong before có làm mất pop không?
- Advice có thể bị skip bởi around ở ngoài không?
- Recursive calls/nested join points có tuân theo LIFO không?
- Nếu target chuyển qua async, after chạy ở thread nào?
- Nếu cleanup ném lỗi, stack có vẫn được khôi phục không?

**Nếu không chứng minh được các điều kiện, không coi ThreadLocal stack là cơ chế universal để mô phỏng per-invocation.**

## 9. `ThreadLocal` là storage theo thread, không phải tự động theo lời gọi

`ThreadLocal<T>` cho mỗi thread một giá trị riêng theo object `ThreadLocal`. Nó giúp tránh một phần giao thoa giữa thread, nhưng không tự cung cấp invocation ID hoặc request lifecycle.

```java
// Mã minh họa, có thể nằm trong class.
private static final ThreadLocal<String> CURRENT =
        new ThreadLocal<>();
```

Nếu before đặt `CURRENT.set("A")`, inner advice cùng thread đặt `"B"`, thì sau khi inner kết thúc outer có thể thấy `"B"` nếu không restore. Đây chính là lỗi reentrancy dưới một hình thức khác.

### Scoped restore phải xử lý cả giá trị cũ

Một pattern an toàn hơn khi chỉ cần một slot theo thread:

```java
// Mã minh họa khi đã có Runnable work và ThreadLocal<String> CURRENT.
String previous = CURRENT.get();
try {
    CURRENT.set("current");
    work.run();
} finally {
    if (previous == null) {
        CURRENT.remove();
    } else {
        CURRENT.set(previous);
    }
}
```

Điều này bảo vệ giá trị scope bên ngoài khi flow lồng nhau **trên cùng thread**, nhưng nó chưa tự phân biệt các invocation khi caller cố tình giữ scope song song/bất đồng bộ. Nếu `null` là một giá trị có ý nghĩa khác với “chưa set”, cần một cấu trúc biểu diễn presence riêng.

### Vì sao `remove()` quan trọng trong thread pool?

Thread pool tái sử dụng worker. Nếu một request R1 đặt context vào `ThreadLocal` nhưng quên clear, request R2 trên cùng worker có thể vô tình đọc lại state của R1. Điều này có thể gây **rò dữ liệu** và sai audit/authorization context.

`remove()` giúp tránh giữ reference không cần thiết và tránh contamination, nhưng khi nested scope có giá trị trước đó, phải **restore** chứ không luôn remove vô điều kiện.

## 10. Async và executor: một invocation có thể vượt khỏi stack hiện tại

Một method có thể trả `CompletableFuture<T>` ngay, còn công việc thực chạy trên thread khác:

```java
// Java minh họa, không phải tệp độc lập.
CompletableFuture<String> future =
        CompletableFuture.supplyAsync(() -> compute());
```

Nếu around advice đo từ `before` tới thời điểm **method trả future object**, nó đo **thời gian khởi tạo/schedule**, không nhất thiết đo tới khi computation hoàn tất. `System.nanoTime()` local vẫn đúng cho phạm vi sync của method return, nhưng có thể **không đúng metric nghiệp vụ muốn đo**.

### Tách return của method và completion của task

```text
Caller invokes asyncMethod()
    |
    +-- Method returns CompletableFuture<T> --------> around ends?
              |
              +-- Worker executes later
                          |
                          +-- Future completes with T / error
```

Muốn đo **độ trễ đến completion**, có thể cần gắn callback/stage được cung cấp rõ theo contract. Việc tạo callback mới và trả một future mapped/observed có thể thay một số semantics liên quan identity/cancellation; phải chọn API phù hợp và kiểm thử.

### Capturing local state cho callback

Một callback có thể giữ một **immutable invocation context** được capture:

```java
// Minh họa trong nơi có CompletableFuture<T> future.
long start = System.nanoTime();
String operation = "fetch";
return future.whenComplete((value, error) -> {
    recordCompletion(operation, System.nanoTime() - start, error);
});
```

Đây là đoạn biểu diễn logic, **không phải chương trình độc lập**; kiểu trả về và behavior phụ thuộc declared method contract. `whenComplete` tạo một stage phụ có semantics riêng; nó không có nghĩa mọi failure/cancellation đều xuất hiện giống một return đồng bộ. Code đo còn phải tránh để lỗi của `recordCompletion` làm thay completion ngoài dự kiến.

**Capturing local trong callback** giúp tránh một shared `currentOperation`; nhưng context capture vẫn phải được kiểm soát về lifetime, bảo mật và kích thước dữ liệu.

## 11. Propagation: state nào nên truyền qua thread/task?

Một **invocation-local timer** có thể cần được dùng chỉ trong stack đồng bộ. Nhưng **trace ID của request** có thể cần đi qua nhiều method và task. Hai loại state không cùng scope.

| State | Thường nên nằm ở đâu? | Khi sang worker? |
| --- | --- | --- |
| Mốc đo một method đồng bộ | Local trong around | Không cần truyền nếu metric kết thúc tại return |
| Mốc đo một operation async | Immutable context/callback state | Capture/propagate có chủ đích |
| Trace ID của request | Request/task context | Phải truyền theo cơ chế hỗ trợ |
| Current transaction/resource scope | Boundary do resource owner quản lý | Không tự chuyển; cần contract cụ thể |
| Bộ đếm tổng service | Metric component shared | Dùng shared thread-safe component |
| Retry attempt của một call | Local trong retry around | Theo flow của retry |
| Authorization context | Context đã xác thực, giới hạn thời gian | Truyền và kiểm tra quyền đúng boundary |

**Không cố truyền toàn bộ aspect instance** chỉ để mang một trace ID. Điều này có thể giữ lại object graph, resource và state mutable không thuộc task mới. Nên truyền một **context tối thiểu, bất biến hoặc snapshot có ownership rõ**.

### Một request có nhiều nested calls

Một request R có thể gọi method A, rồi B, rồi C. Cùng trace ID là hợp lý cho cả ba; nhưng **mốc thời gian của A, B, C phải khác nhau**. Dùng một request-level field `startTime` để đo cả ba có thể sai vì chúng chồng lấn.

## 12. Per-invocation state và per-target state khác nhau

Một aspect có thể được tạo theo target: Target X dùng Aspect[X], Target Y dùng Aspect[Y]. Điều đó cô lập state **giữa target**, nhưng hai invocation trên cùng X vẫn có thể cùng dùng Aspect[X].

```text
Target X
   |
   +--> Invocation X1
   +--> Invocation X2
           |
        Aspect[X] (state dùng chung của target)
```

Nếu Aspect[X] có `currentId`, X1 và X2 vẫn có thể ghi đè nhau. **Per-target không thay cho invocation-local state.**

Ngược lại, tạo aspect mới cho mỗi invocation có thể cô lập state instance, nhưng phải xét chi phí tạo object, static fields và dependency dùng chung. Trong nhiều trường hợp, shared aspect + local variables **đơn giản hơn** mà vẫn đúng semantics.

### Khi nào per-target phù hợp?

Một bộ đếm tổng số thao tác của **riêng target X**, cache metadata per-target hoặc cấu hình gắn với identity X có thể phù hợp per-target. Nhưng thông tin “lượt chạy nào đang ở giai đoạn after” thường vẫn cần local/correlated invocation state.

## 13. Static field và singleton dependency phá cô lập nếu dùng sai

```java
// Ví dụ minh họa:
final class PerInvocationAspect {
    private static String LAST_ID;

    void before(String id) {
        LAST_ID = id;
    }
}
```

Dù tạo một `PerInvocationAspect` mới mỗi lần, `LAST_ID` vẫn là **static field** trong phạm vi class identity, được chia sẻ giữa các instance. Vì vậy lỗi correlation vẫn tồn tại.

Tương tự, một aspect instance mới có thể giữ reference đến **cùng một shared mutable helper**. Nếu helper có field `currentRequest`, chuyển scope của aspect không loại bỏ được lỗi ở helper.

### Kiểm tra toàn bộ object graph

Cần hỏi:

- Field trên aspect thuộc scope nào?
- Dependency được tạo mới hay được share?
- Static/global cache có chứa dữ liệu riêng request không?
- Closure/lambda có capture object mutable sống quá scope không?
- Có map lưu invocation context nhưng không remove khi hoàn tất không?
- Có một data structure được chia sẻ ngoài chủ đích ở phía target không?

**Isolation là đặc tính của đường tham chiếu và ownership**, không chỉ cách đặt tên lớp aspect.

## 14. Tính bất biến và snapshot cho per-call state

Một state có thể được biểu diễn bằng record Java 17+:

```java
// Minh họa một record dùng làm dữ liệu per invocation.
record InvocationContext(
        String operation,
        String traceId,
        long startedAtNanos
) { }
```

Một record như vậy là **shallowly immutable** nếu các component không thể bị thay bằng setter. Nhưng nếu component là `List` mutable, record vẫn có thể tham chiếu tới collection bị sửa; **record không tự deep-copy dữ liệu**.

Một immutable invocation context giúp:

- Giảm nguy cơ advice sửa ngầm thông tin của lời gọi khác.
- Truyền/capture context qua callback rõ ràng.
- Viết test với input xác định.
- Tránh một field mutable “current invocation” trên singleton.

Nhưng nó không tự tạo transaction, bảo đảm authorization hay context propagation qua mọi executor.

### Context tối thiểu

Không cần copy toàn bộ argument list hoặc user object cho mọi invocation. Chỉ giữ các trường thật sự cần: operation name, correlation ID không nhạy cảm, mốc thời gian, flags policy. Nếu lưu return object/Throwable vào context sống lâu, có thể kéo dài lifetime của dữ liệu lớn và thông tin nhạy cảm.

## 15. Đo thời gian đúng: đơn vị và đồng hồ

Đối với duration bên trong một JVM, `System.nanoTime()` thường thích hợp vì dùng để đo **elapsed time**, không phải biểu diễn thời gian lịch. Giá trị tuyệt đối `nanoTime` không phải UNIX timestamp và không nên lưu nó như ngày giờ.

```java
// Minh họa trong một around advice.
long start = System.nanoTime();
try {
    return proceed();
} finally {
    long elapsedNanos = System.nanoTime() - start;
    timer.record(elapsedNanos);
}
```

Nếu một invocation khác ghi `start` vào shared field giữa chừng, con số `elapsedNanos` có thể sai dù phép trừ dùng đúng API.

### Những câu hỏi về semantics duration

- Đo từ trước validation hay chỉ phần business method?
- Đo mỗi attempt hay cả tổng retry?
- Bao gồm logging/audit advice khác không?
- Method trả future: đo tới return hay completion?
- Có đo khi target ném exception không?
- Đơn vị output là nanos, microseconds hay milliseconds?
- Có đo cả thời gian chờ lock/IO không?
- Metric sink có overhead ảnh hưởng timing không?

**Local state bảo đảm mốc thuộc đúng invocation; vị trí advice và contract mới quyết định metric đo cái gì.**

## 16. State cho retry không được dùng chung

Một around advice có khả năng gọi `proceed` nhiều lần có thể retry. Bộ đếm số lần thử nên thuộc **lượt gọi bên ngoài đang retry**:

```java
// Pseudocode, không phải chương trình độc lập.
int attempt = 0;
while (true) {
    attempt++;
    try {
        return proceed();
    } catch (TransientFailure error) {
        if (attempt >= maxAttempts) {
            throw error;
        }
    }
}
```

Nếu `attempt` nằm trong field shared, hai invocation retry đồng thời sẽ can thiệp lẫn nhau; caller A có thể bị dừng do số attempt của caller B.

**Điều kiện thêm:** Retry chỉ an toàn với policy lỗi/timeout/idempotency phù hợp. Đối tượng target có thể đã gây side effect trước khi ném timeout; trạng thái per-invocation đúng chưa làm phép retry an toàn nghiệp vụ.

## 17. State cho audit/tracing: correlation phải có ngữ nghĩa

Một audit event có thể cần:

- Loại thao tác.
- ID của target hoặc entity.
- Trạng thái success/failure.
- Trace/correlation ID.
- Thời gian bắt đầu/kết thúc.
- Một số trường dữ liệu được phép ghi.

Từng trường có scope riêng. Ví dụ **trace ID** có thể dùng chung cho request, còn **span ID** gắn một operation cụ thể. Không nên dùng một field `lastTraceId` trên aspect singleton để kết nối mọi callback.

### Lỗi dễ gây rò thông tin

`System.out.println(args)` trong một advice có thể vô tình ghi credential, token hoặc PII. Việc chuyển từ shared field sang per-call context **không giải quyết tự động chính sách bảo vệ dữ liệu**. Cần redaction, giới hạn retention và sink được phép nhận thông tin tương ứng.

Một per-call context capture lớn giữ request object trong callback sống lâu có thể khiến dữ liệu nhạy cảm tồn tại lâu hơn dự tính. Context càng nhỏ, bất biến và có TTL/cleanup rõ càng dễ kiểm soát.

## 18. Cùng một thread nhưng nhiều flow: stack và cleanup

Một thread trong server có thể lần lượt xử lý R1, R2; hoặc một request có thể gọi nested flow:

```text
Thread T:
  enter R1
     enter nested operation
     exit nested operation
  exit R1

  enter R2
  exit R2
```

Nếu dùng một ThreadLocal slot nhưng quên restore trong nested operation, R1 có thể thấy giá trị của nested operation. Nếu quên `remove()` sau R1, R2 có thể nhận dữ liệu R1.

Vì vậy một scoped context cần cân nhắc:

1. **Push/replace** khi bắt đầu.
2. **Restore previous** khi kết thúc.
3. **Remove** khi không còn scope.
4. **Cleanup trong finally** dù target ném lỗi.
5. **Không propagate ngầm** qua ranh giới task nếu chưa có chính sách.
6. **Không dùng lại** context đã kết thúc.

**Một biến local của around** không cần những thao tác quản lý thread này nếu chỉ dùng trong cùng advice invocation. Hãy ưu tiên giải pháp đơn giản nhất phù hợp phạm vi.

## 19. Không tự coi mọi advice chạy trên cùng thread

Một số AOP model quan sát method execution đồng bộ ngay trên thread target; nhưng các hệ thống callback/event/interceptor có thể chuyển xử lý qua thread khác hoặc hẹn sau khi method trả.

Nếu before chạy ở thread A và cleanup callback ở thread B, `ThreadLocal` của A sẽ không tự cho B truy cập đúng state. Cần carrier tường minh hoặc correlation do engine bảo đảm.

**Đừng thiết kế một câu “before luôn đặt ThreadLocal, after luôn lấy được” như chân lý chung** mà không biết chính xác runtime AOP/hook đang sử dụng.

### CompletableFuture completion

Một future có thể hoàn tất thành công, thất bại hoặc bị cancel. Completion callback có thể chạy ở thread hoàn tất hoặc thread do API/executor chọn. Advice đo operation async phải xử lý outcome tương ứng và tránh giữ scope sau completion.

Nếu callback được gắn nhiều lần hoặc retry tái sử dụng state, cần định nghĩa **completion được ghi đúng một lần** theo event semantics mong muốn. Đừng lạm dụng một shared `finished` boolean cho mọi invocation; nếu cần cờ, nó thuộc context cụ thể hoặc một state machine theo operation ID.

## 20. Exception: không để cleanup đổi outcome ngoài chủ đích

Giả sử target ném `IllegalArgumentException`, nhưng advice cố ghi metric rồi sink cũng ném lỗi:

```text
Target throws OriginalError
   |
Advice.finally -> MetricSink throws SinkError
   |
Caller may see SinkError instead of OriginalError
```

Nếu metric chỉ là quan sát phụ trợ, lỗi sink có thể cần được cô lập theo policy phù hợp. Nếu audit bắt buộc, có thể cần fail operation. Không có quy tắc duy nhất cho mọi concern; phải chọn theo yêu cầu.

### Local state vẫn đúng khi exception xảy ra

Với around advice:

```java
// Pseudocode cho một around advice.
String id = currentInvocationId();
try {
    return proceed();
} catch (Throwable error) {
    recordFailure(id, error);
    throw error;
} finally {
    closeScope(id);
}
```

Local `id` vẫn là của invocation đó trên đường throw. Nếu thay bằng shared field, một advice lồng nhau có thể làm `recordFailure` gắn lỗi của outer sang ID inner.

**Không bắt Throwable rồi nuốt mọi lỗi** chỉ để tránh làm hỏng business flow; chú ý cả những lỗi nghiêm trọng không nên bị biến thành success giả.

## 21. Trạng thái theo target không tự giải quyết concurrency

Một target instance X được dùng bởi hai thread:

```text
Thread A --> Target X --> Aspect[X]
Thread B --> Target X --> Aspect[X]
```

Nếu aspect theo target có field `start` hoặc `currentId`, cả hai thread vẫn tranh chấp. Per-target chỉ cô lập **giữa X và Y**, không cô lập **giữa các lần gọi X**.

Một aspect per-control-flow cũng có ngữ nghĩa khác: nó cô lập theo một flow động được engine định nghĩa, thường liên quan call stack. Một flow async không tự nối qua executor.

**Quy tắc:** Scope của state phải khớp **đối tượng logic mà state mô tả**, không phải chỉ khớp một điểm có vẻ gần đúng như target hoặc thread.

## 22. Shared aspect + local state có những lợi ích gì?

1. **Ít state dùng chung để đồng bộ:** mỗi invocation có local variables.
2. **Tránh contamination:** invocation A không đọc nhầm context invocation B.
3. **Giảm chi phí lifecycle:** không cần tạo một aspect object mới chỉ để lưu mốc thời gian.
4. **Dễ kiểm thử:** invocation có input/outcome độc lập.
5. **Hỗ trợ reentrancy:** nested calls có stack frames riêng.
6. **Tương thích nhiều mô hình weaving:** nếu engine gọi cùng một method advice trên shared instance, Java locals vẫn là riêng từng lần gọi.
7. **Dễ reason về failure:** `try/catch/finally` trong cùng invocation thể hiện ranh giới.
8. **Giảm rủi ro memory retention:** không lưu request object trong field sống dài.

Những lợi ích này không có nghĩa shared aspect **luôn đúng**. Nếu concern thật sự cần state per-target/per-flow, hãy dùng scope tương ứng. Nhưng nếu dữ liệu chỉ tồn tại một lời gọi thì local state là lựa chọn mặc định mạnh.

## 23. Trường hợp local state vẫn chưa đủ

### 23.1. Before/after là hai method tách biệt

Local của before không hiện diện trong after. Cần invocation context hoặc scope manager.

### 23.2. Async callback cần dữ liệu sau khi method return

Local có thể được lambda capture, nhưng lifecycle/lifetime của closure cần tương ứng operation async, không chỉ stack đồng bộ.

### 23.3. Nhiều join point thuộc cùng request

Trace ID của request dùng chung cho nhiều invocation; mỗi advice có thể đọc từ request context. Không cần copy mutable state vào singleton field.

### 23.4. State cần giữ qua nhiều lần gọi target

Một counter mỗi target phải sống lâu hơn một invocation; local sẽ reset. Dùng per-target hoặc shared map với key đúng và cleanup.

### 23.5. Kết quả cần aggregate đa luồng

Một local counter riêng không thay cho tổng metric đa thread. Cần component tổng hợp an toàn.

**Không biến “trạng thái theo lời gọi” thành yêu cầu mọi dữ liệu phải local.** Đúng nghĩa là phân loại và gắn vòng đời đúng cho từng dữ liệu.

## 24. Đặt state vào đối tượng context tường minh

Khi có nhiều biến per-invocation hoặc cần truyền qua các helper, tạo context object có thể dễ đọc hơn:

```java
// Java 17+ minh họa data holder bất biến.
record CallInfo(
        String operation,
        String correlationId,
        long startedAtNanos
) { }
```

Một around advice có thể tạo một `CallInfo` rồi truyền tới các hàm đo/ghi log. Với dữ liệu mutable chỉ nằm trong một invocation, có thể dùng một state object riêng nhưng phải bảo đảm **không publish object ấy cho invocation khác**.

### Chú ý ownership

- Ai tạo context?
- Ai được phép sửa?
- Context có thread-safe nếu truyền vào nhiều tasks không?
- Có cần snapshot/copy để tránh bị mutate?
- Khi nào context không còn hợp lệ?
- Có chứa secrets không?
- Có giữ reference tới target/return value lớn hơn cần thiết không?

**Context object không tự biến thành per-invocation chỉ vì được đặt tên `InvocationContext`.** Nếu bạn lưu một instance context duy nhất vào field shared và tái dùng, nó vẫn là shared state.

## 25. Key correlation: identity của join point không đủ

Hai lượt gọi `Service.save("A")` và `Service.save("B")` có thể có:

- Cùng method signature.
- Cùng target object.
- Cùng thread (lồng nhau hoặc chạy nối tiếp).
- Cùng request ID.
- Cùng pointcut match.

Nhưng chúng là **hai invocation khác nhau**. Nếu muốn lưu start time của từng lượt, key phải phân biệt được chúng. Một method metadata key phù hợp **cache reflection metadata**, không phù hợp **lưu timer đang chạy của một lời gọi**.

### Identity và memory

Nếu tạo một map `Map<InvocationId,State>` dùng chung để nối before/after, phải có:

- ID duy nhất trong phạm vi cần thiết.
- Map/thread safety.
- Cleanup trong mọi đường return/throw/cancel.
- Timeout xử lý orphaned state.
- Giới hạn bộ nhớ và số lượng in-flight calls.
- Không tái sử dụng ID quá sớm gây collision.

Trong một lời gọi đồng bộ có around, **local state thường giảm đáng kể những phức tạp này**.

## 26. Kiểm thử concurrency bằng điều khiển thứ tự, không dựa vào may rủi

Một test kiểu “tạo 100 thread và hy vọng lộ race” không đủ chắc. Nên dùng các primitive như `CountDownLatch` hoặc `CyclicBarrier` để buộc thứ tự xen kẽ.

Ví dụ kịch bản kiểm lỗi field dùng chung:

```text
Task A: before(A) -> báo ready -> chờ B
Task B: chờ A ready -> before(B) -> báo done
Task A: sau B done -> after(A) -> kiểm ID có phải A?
```

Nếu aspect dùng một field `currentId`, test có thể quan sát giá trị B ở after(A). Khi chuyển sang local/invocation context, after(A) vẫn có A.

Đừng đưa `Thread.sleep(...)` với thời gian cố định làm cách duy nhất chứng minh race; scheduler khác nhau khiến test flaky.

### Kiểm thử reentrancy còn rẻ hơn

Ví dụ `InvocationStateDemo.java` đã tái hiện lỗi **tất định trên một thread**. Đây là một bài test quan trọng ngay cả khi ứng dụng tưởng chỉ xử lý đồng bộ.

## 27. Ma trận test state theo invocation

| Ca kiểm thử | Điều cần chứng minh |
| --- | --- |
| Hai lời gọi tuần tự | State không bị giữ sai qua lần sau |
| Hai lời gọi concurrent | ID/start/result của từng invocation độc lập |
| Nested call trên cùng thread | Outer state được bảo toàn sau inner |
| Recursion nhiều mức | Mỗi mức có state riêng và unwind đúng |
| Target thành công | Advice dùng đúng state và truyền return đúng contract |
| Target ném lỗi | Error log gắn đúng invocation, cleanup chạy |
| Advice tự ném lỗi | Không để context lẫn sang lượt khác |
| After/cleanup ném lỗi | Outcome được xử lý đúng policy |
| Around không proceed | State vẫn được cleanup khi skip target |
| Around proceed nhiều lần | Đếm attempt khác số invocation bên ngoài |
| Before/after riêng | Correlation key/stack đúng scope |
| ThreadLocal nested | Restore giá trị trước đúng thứ tự |
| Thread pool tái sử dụng worker | Không còn context từ request trước |
| Async future | Đo tới method return hay completion đúng mong muốn |
| Callback bị cancel | Context được giải phóng và outcome được ghi hợp lệ |
| Một target nhiều proxy | Aspect state thuộc proxy, target hay invocation? |
| Per-target aspect | Hai calls cùng target vẫn tách invocation state |
| Raw target bypass proxy | Không nhầm thiếu advice với lỗi state |
| Shared metric counter | Tổng metric đúng, không dùng field per-call |
| Class loader/plugin reload | Cache/context không giữ resource/loader cũ |
| Sensitive arguments | Log không lộ dữ liệu dù per-call state đúng |

Test nên so sánh **state trước và sau**, **số lần advice chạy**, **số lần target thực thi**, **caller thấy kết quả/exception gì**, và **còn reference không mong muốn sau completion không**.

## 28. Chẩn đoán lỗi: state sai hay advice không chạy?

Khi log có ID sai hoặc thiếu dòng, cần phân loại:

**Trường hợp A — Advice chạy nhưng state sai.** Ví dụ field `currentId` bị inner invocation ghi đè. Cần sửa ownership/scope của state.

**Trường hợp B — Advice không chạy.** Có thể lời gọi bypass proxy, pointcut không match, aspect không được weave, hoặc around ngoài không `proceed`. Local state không thể giúp một advice chưa được gọi.

**Trường hợp C — Advice chạy, state đúng nhưng sink không xuất log.** Logging/metric có thể được disable, sampled hoặc thất bại. Cần tách “đã vào advice” khỏi “đã xuất event”.

**Trường hợp D — Advice chạy trên thread khác.** Context propagation chưa đúng, dù proxy/weaving coverage vẫn ổn.

Cách debug:

1. Xác định invocation path và target.
2. Xác định aspect instance identity/lifecycle.
3. Xác định vị trí lưu state, owner và key.
4. Kiểm tra reentrancy/concurrency.
5. Kiểm tra return/throw/finally và cleanup.
6. Kiểm tra async handoff, context carrier.
7. Kiểm tra output sink và masking dữ liệu.
8. Kiểm tra scope manager/cache và memory retention.

Không vội dùng `synchronized` quanh toàn bộ business logic để chữa một lỗi đáng ra giải quyết bằng local variable.

## 29. Những hiểu lầm phổ biến

1. **“Singleton aspect phải dùng singleton state cho mọi thứ.”** Instance dùng chung vẫn có local state riêng mỗi invocation.
2. **“Chỉ có một thread thì không thể sai.”** Nested/reentrant advice vẫn có thể ghi đè field.
3. **“`volatile` làm currentId trở thành per-call.”** Volatile không tạo slot theo invocation.
4. **“`AtomicReference` sửa được log lẫn request.”** Atomic không giải quyết correlation.
5. **“Per-target aspect là per-invocation.”** Một target có thể được gọi nhiều lần đồng thời.
6. **“ThreadLocal là cùng một thứ với request scope.”** Thread pool và async làm hai scope khác nhau.
7. **“ThreadLocal không cần remove vì thread sẽ kết thúc.”** Worker thread có thể sống rất lâu.
8. **“Chỉ remove là đủ với nested flow.”** Phải restore previous context thích hợp.
9. **“Before local variable tự tồn tại ở after.”** Hai advice method có stack frame khác.
10. **“Method name là invocation ID.”** Nhiều lời gọi trùng method và target.
11. **“Aspect per-invocation làm static field riêng từng lần.”** Static theo class identity.
12. **“Capture cả request object vào callback là vô hại.”** Có thể kéo dài lifetime và lộ dữ liệu.
13. **“Method trả future nghĩa là công việc xong.”** Method return khác future completion.
14. **“Local timer chắc chắn đo end-to-end.”** Còn phụ thuộc advice nesting và async boundary.
15. **“Shared aspect không thể giữ cache.”** Cache chung hợp lệ nếu key và concurrency đúng.
16. **“Thêm lock sửa mọi lỗi state.”** Lock không sửa scope gắn sai.
17. **“Lỗi audit chỉ là lỗi log.”** Với audit bắt buộc, policy có thể đòi fail-closed.
18. **“Một proxy là một aspect invocation.”** Một proxy có thể được gọi nhiều lần; handler có state dùng chung.
19. **“Có scope context là tự có security.”** Context có thể stale/giả mạo; quyền cần kiểm tra ở boundary tin cậy.
20. **“Dùng per-call state luôn tiết kiệm bộ nhớ hơn.”** Captured context hoặc map không cleanup có thể giữ dữ liệu rất lâu.
21. **“Một lời gọi ngoài qua proxy thì mọi lời gọi nội bộ cũng qua proxy.”** Với wrapper proxy, `this.inner()` thường bypass.
22. **“Mọi AOP engine đều cung cấp invocation context map.”** Phải kiểm tra API thực tế hoặc tự quản lý scope.
23. **“Một record bảo đảm deep immutability.”** Component có thể tham chiếu object mutable.
24. **“Đúng correlation ID là metric chính xác.”** Còn phải chọn đúng điểm bắt đầu/kết thúc, retry và completion.

## 30. Bài tập thực hành

1. Chạy `InvocationStateDemo.java` và đối chiếu từng dòng stdout.
2. Giải thích tại sao `shared.after inner` xuất hiện **hai lần** dù lần outer đã kết thúc.
3. Đổi `self.execute("inner")` thành `this.execute("inner")` và giải thích vì sao mất nested proxy advice; kết luận này có áp dụng cho mọi bytecode weaving engine không?
4. Thêm một lượt `good.execute("single")`. Dự đoán log local và outcome.
5. Thêm recursion `level3 → level2 → level1`. So sánh shared field và local state.
6. Chuyển `SharedFieldHandler.currentId` thành `volatile String`. Vì sao lỗi logic không đổi?
7. Chuyển sang `AtomicReference<String>`. Kiểm thử lại reentrancy và giải thích vì sao vẫn sai.
8. Viết một around advice đo `System.nanoTime` bằng local variable trong `try/finally`; đo riêng success và throw.
9. Mô phỏng before và after riêng bằng một `ThreadLocal<Deque<State>>`. Thêm test nested + exception + cleanup.
10. Dùng một executor một thread chạy hai request nối tiếp; cố ý để lại ThreadLocal từ request đầu rồi quan sát request sau, sau đó sửa bằng restore/remove.
11. Tạo hai worker thread dùng cùng shared aspect. Điều khiển interleaving bằng latch để chứng minh shared `currentId` sai, local `id` đúng.
12. Tạo một `LongAdder` tổng số advice invocations trong shared component; so sánh với local attempt counter.
13. Thiết kế invocation context chứa operation, trace ID và timestamp, nhưng không chứa password/token.
14. Một method trả `CompletableFuture<String>`. So sánh timer đo tới return của future và timer đo tới completion.
15. Thêm callback error path, xác định cách không để metric sink exception che business exception.
16. Thiết kế một retry around advice có attempt count local, giới hạn lần thử, deadline và idempotency key.
17. Với target X có aspect per-target, cho hai thread gọi X đồng thời; state nào vẫn phải là per-invocation?
18. Thêm static field `lastId` vào một aspect được tạo per-invocation và giải thích vì sao nó làm mất isolation.
19. Xây map `InvocationId → State` cho before/after tương quan. Nêu cleanup trong return, throw, timeout, cancellation và memory bounds.
20. Vẽ flow của request R đi qua executor và callback. Phân biệt context per-request với state per-method invocation.
21. Viết test phân biệt lời gọi không match pointcut, lời gọi bypass proxy và advice đã chạy nhưng logger bị tắt.
22. Đề xuất một phương án audit an toàn khi dữ liệu kết quả chứa thông tin nhạy cảm mà nhiều invocation chạy đồng thời.
23. So sánh dùng biến local `long start` với shared `Map<Thread,Long>` cho một around advice đồng bộ; vì sao biến local đơn giản và chính xác hơn?
24. Thay một shared mutable field `lastThrowable` bằng việc truyền Throwable của invocation hiện tại vào hàm record failure; xem ảnh hưởng tới reentrancy.
25. Thiết kế test ba tầng: **đúng instance/lifecycle**, **đúng correlation state**, **đúng kết quả caller**.

**Tự kiểm tra:** Vì sao một aspect singleton vẫn có thể dùng biến local? Có thể sai trên một thread không? Vì sao `ThreadLocal` không tự thành per-invocation khi có recursion? Trong before/after riêng cần cơ chế nào để nối state đúng? Vì sao `CompletableFuture` làm thay đổi ý nghĩa mốc kết thúc? Nếu per-target aspect có nhiều thread cùng gọi một target, liệu state theo lời gọi đã được cô lập chưa?

## Kết luận

**Lưu trạng thái theo lời gọi thay vì trong field dùng chung là nguyên tắc then chốt để aspect hoạt động đúng khi có concurrency, recursion và reentrancy.** Với một around advice đồng bộ, **local variables cộng `try/finally`** thường là giải pháp đơn giản và tin cậy nhất cho timer, correlation ID tạm và retry attempt. Nếu before/after bị tách rời hoặc xử lý băng qua async/task, phải dùng **invocation context, scope stack hoặc propagation có contract rõ**, cùng cơ chế restore/cleanup đầy đủ.

Không phải mọi state đều thuộc invocation: metric tổng, cấu hình bất biến hoặc cache metadata có thể dùng chung nếu thread-safe; state gắn target hoặc request cần lifecycle tương ứng. Thiết kế tốt phải **xác định rõ owner của mỗi dữ liệu, phạm vi tồn tại, quan hệ với các invocation lồng nhau, khả năng đồng thời và đường cleanup**, rồi kiểm thử bằng các luồng thực thi có cả success, exception và async handoff. Điều này giúp AOP vừa giữ được lợi ích cắt ngang, vừa tránh lẫn dữ liệu giữa những công việc độc lập.
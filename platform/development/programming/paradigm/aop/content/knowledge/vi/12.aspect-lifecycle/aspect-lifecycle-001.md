# Aspect dùng chung và aspect được tạo theo ngữ cảnh

## 1. Vì sao vòng đời của aspect quan trọng?

Trong **lập trình hướng khía cạnh (Aspect-Oriented Programming – AOP)**, một *aspect* đóng gói các **pointcut** và **advice** cho một mối quan tâm cắt ngang: ghi log, audit, đo thời gian, tracing, kiểm soát truy cập hoặc quan sát lỗi. Khi một join point được chọn và advice thực thi, ta thường quan tâm advice *làm gì*. Nhưng còn một câu hỏi quyết định thiết kế:

**Đoạn advice này đang chạy trên instance aspect nào? Instance ấy tồn tại trong bao lâu, và những lượt thực thi nào chia sẻ trạng thái của nó?**

Một aspect có thể được dùng chung trong toàn bộ một phạm vi AOP, hoặc có nhiều instance được gắn với **đối tượng, luồng điều khiển, phiên xử lý hay từng lượt can thiệp**. Sự lựa chọn ảnh hưởng trực tiếp tới:

- **Trạng thái:** counter, cache, correlation ID, dữ liệu tạm được lưu ở đâu?
- **Concurrency:** bao nhiêu thread hoặc task có thể truy cập một instance cùng lúc?
- **Isolation:** thông tin của một đối tượng/yêu cầu có lọt sang đối tượng/yêu cầu khác không?
- **Lifecycle:** instance được tạo lúc nào, tái sử dụng bao lâu và được giải phóng ra sao?
- **Hiệu năng:** chi phí tạo instance, tra cứu association, đồng bộ hóa, GC và retention.
- **Semantics:** hai join point giống nhau có sử dụng cùng trạng thái advice hay không?

**Nguyên tắc cốt lõi:** *vòng đời của aspect instance không nhất thiết trùng với vòng đời target, proxy, thread, request hoặc một lần gọi phương thức*. Muốn biết đúng, phải xác định **mô hình instantiation** mà công cụ AOP và kiến trúc ứng dụng thực sự hỗ trợ.

> **Phạm vi:** Bài này giải thích AOP cơ bản và nâng cao nói chung. Những tên thường gặp như *singleton aspect*, *per-object*, *per-target*, *per-control-flow*, *per-invocation* được dùng làm mô hình phân tích. Một số công cụ cung cấp các chính sách instantiation có tên/cú pháp riêng; những công cụ khác chỉ có aspect dùng chung hoặc yêu cầu tự xây scope. Không có một cú pháp pointcut hoặc một cách tạo aspect bắt buộc cho mọi AOP engine.

## 2. Phân biệt aspect type, aspect instance và advice invocation

Ba khái niệm rất dễ bị nhầm:

1. **Aspect type:** định nghĩa chứa advice, pointcut và các field/method hỗ trợ. Nó giống một blueprint về hành vi.
2. **Aspect instance:** một object cụ thể chứa **trạng thái instance** của aspect type. Có thể có một hoặc nhiều object như vậy.
3. **Advice invocation:** một lần chạy advice tại join point đã khớp. **Nhiều lần chạy** có thể dùng **cùng một aspect instance**, hoặc mỗi lần dùng một instance khác theo mô hình được chọn.

```text
Aspect type: AuditAspect
       |
       +------ instance #A ------> advice chạy lần 1
       |                       \--> advice chạy lần 2
       |
       +------ instance #B ------> advice chạy lần 3
```

Vì vậy, việc log xuất hiện ba lần **không chứng minh** đã tạo ba aspect instance. Ngược lại, một aspect instance có thể tồn tại từ lâu mà chưa chạy advice nào vì chưa có join point khớp.

### Field nằm ở đâu?

```java
// Minh họa ý tưởng; không phải chương trình Java độc lập.
final class CounterAspect {
    private int count;

    void before() {
        count++;
    }
}
```

`count` là **instance field**. Nếu dùng chung một `CounterAspect` thì tất cả lời gọi vào object đó cùng tác động lên một field. Nếu mỗi target có aspect riêng, mỗi object có field riêng. Nhưng **`static` field** vẫn là trạng thái cấp class trong phạm vi class identity/class loader tương ứng, không tự tách theo từng aspect instance.

Do đó, đổi từ singleton sang per-target **không cô lập một static mutable field** mà mọi instance cùng truy cập.

## 3. Bảng tổng quan các mô hình vòng đời

| Mô hình | Đơn vị chia sẻ state | Thời gian sống điển hình | Điều cần chú ý |
| --- | --- | --- | --- |
| **Aspect dùng chung** | Nhiều join point/target trong phạm vi một instance chung | Bằng phạm vi manager/weaver/runtime đã xác định | Concurrency, state leakage, phạm vi “chung” thực tế |
| **Per target object** | Mỗi target có aspect instance riêng | Theo association với target hoặc registry | Nhiều caller/thread vẫn có thể dùng một target |
| **Per object bound at join point** | Mỗi object được binding theo semantics của engine | Theo object và tập join point phù hợp | `this`/`target` có thể khác nhau |
| **Per control flow** | Mỗi flow động bắt đầu ở một join point gốc | Từ lúc vào flow đến lúc thoát flow | Reentrancy, recursion, async/thread boundary |
| **Per invocation/join point occurrence** | Mỗi lần can thiệp một aspect/state riêng | Khoảng một lần thực thi advice/chain | Chi phí cấp phát, không tích lũy state giữa lần gọi |
| **Per task/request/session** | Một scope nghiệp vụ do ứng dụng/runtime định nghĩa | Theo task/request/session | Phải có carrier, propagation và cleanup rõ |
| **Per type/class** | Một aspect instance cho type được chọn | Theo runtime class/loader và association | Type identity, inheritance, class loader/reload |

Đây là những **khả năng thiết kế**, không phải danh sách chắc chắn xuất hiện trong mọi công cụ. Một engine hỗ trợ per-object mà không hỗ trợ per-flow vẫn là AOP hợp lệ. Một proxy handler cũng có thể dùng một field tham chiếu tới aspect singleton hoặc một nhà cung cấp aspect theo target.

### Một lời gọi có thể liên quan nhiều state scope

Ví dụ request R gọi target T trong thread W, trong đó target được gọi qua proxy P. Hệ thống có thể đồng thời có:

- Một aspect singleton ghi metric tổng thể.
- Một aspect instance gắn với T.
- Một trace context gắn với R.
- Một temporary timing state tạo cho lượt gọi hiện tại.

**Không cần chọn một kiểu lifecycle duy nhất cho toàn bộ ứng dụng.** Quan trọng là xác định dữ liệu nào thuộc scope nào và tránh gộp state khác bản chất.

## 4. Aspect dùng chung: một instance cho nhiều điểm can thiệp

Một **shared aspect** dùng cùng một instance để xử lý nhiều join point trong một phạm vi được quản lý. Trường hợp đơn giản:

```text
                   Aspect: SharedAudit #1
                   /         |         \
                  v          v          v
Target A.save()    Target B.save()    Target C.delete()
```

Những lần advice chạy ở cả A, B, C có thể cùng gọi method trên instance `SharedAudit #1`. Loại vòng đời này phù hợp khi advice:

- **Không giữ dữ liệu request mutable** trong field instance.
- Dùng hàm gần như thuần: nhận metadata/argument/context rồi xuất kết quả.
- Có cache/metric **được thiết kế dùng chung** và được đồng bộ hóa đúng.
- Giữ dependency bất biến tới một logger, metrics sink hoặc policy provider thread-safe.
- Không cần nhớ “lượt gọi trước của chính target này” qua instance fields.

### “Dùng chung” không nhất thiết là một instance cho cả JVM

Một chương trình có thể có nhiều:

- Class loader định nghĩa cùng một aspect type ở các domain khác nhau.
- Weaver hoặc proxy provider độc lập.
- Module layer/plugin thế hệ khác nhau.
- Runtime scope riêng của một test/application/plugin.
- Instance do người viết tự tạo bằng `new` ngoài cơ chế cung cấp aspect.

Vì thế, “singleton aspect” cần gắn với **phạm vi singleton nào**. Không nên lấy “trên toàn bộ tiến trình chắc chỉ có một aspect object” làm tiên đề khi kiến trúc có nhiều loader/manager.

### Ví dụ đúng khi stateless

```java
// Mã minh họa: ví dụ một advice stateless.
final class LoggingAspect {
    void before(String operationName) {
        System.out.println("begin " + operationName);
    }
}
```

Nếu instance chỉ có logic và các dependency an toàn, nó có thể dùng chung mà ít rủi ro. Bản thân `operationName` là **biến local của mỗi lần gọi**, không nằm trong field chia sẻ.

## 5. Shared aspect có state: nguy cơ race và lẫn dữ liệu

Xét:

```java
// KHÔNG an toàn nếu một instance dùng đồng thời mà thiếu đồng bộ.
final class UnsafeAspect {
    private String currentRequestId;
    private int count;

    void before(String requestId) {
        currentRequestId = requestId;
        count++;
    }

    void after() {
        System.out.println(currentRequestId);
    }
}
```

Hai thread có thể xen kẽ:

```text
Thread A: before("REQ-A") -> currentRequestId = REQ-A
Thread B: before("REQ-B") -> currentRequestId = REQ-B
Thread A: after()         -> đọc REQ-B  [SAI]
```

Không nhất thiết gặp lỗi ngay; đây là **data race** và **logical cross-request contamination**. `count++` cũng là thao tác đọc–tăng–ghi, không phải phép tăng atomic cho shared mutable state.

**Một aspect dùng chung không phù hợp để giữ dữ liệu riêng của một lời gọi trong instance field không được quản lý scope.** Để giữ dữ liệu tạm thời, ưu tiên:

- Biến local trong một around advice bao trọn lượt gọi.
- Parameter của advice hoặc một immutable context được truyền rõ.
- State gắn với invocation nếu công cụ hỗ trợ.
- Thread/task context có carrier và cleanup rõ nếu thực sự cần truyền ngầm.
- Concurrency primitives phù hợp cho **state dùng chung thật**, ví dụ `AtomicLong` hoặc `LongAdder` cho một số loại đếm.

### Atomic counter không sửa được lỗi nhầm request

Đổi `count` thành `AtomicInteger` có thể giải quyết lost update của counter, nhưng **không** giải quyết việc `currentRequestId` bị ghi đè giữa các lời gọi. Thread safety cần xét **toàn bộ bất biến dữ liệu**, không chỉ một phép tăng.

### Scope đúng đôi khi đơn giản là local variable

Nếu concern đo thời gian:

```java
// Minh họa logic around; proceed() là API giả định của công cụ.
long startNanos = System.nanoTime();
try {
    return proceed();
} finally {
    recordDuration(System.nanoTime() - startNanos);
}
```

`startNanos` là biến local theo invocation, vì vậy ngay cả khi một instance aspect dùng chung, từng lần chạy riêng biệt có local state của nó. Đây thường là thiết kế đơn giản hơn so với tạo một aspect instance mới chỉ để lưu thời điểm bắt đầu.

## 6. Aspect theo target: một instance gắn với một object đích

Một mô hình khác tạo hoặc chọn một **aspect instance riêng cho mỗi target object** phù hợp.

```text
Target A ------> Aspect[A] ---- calls của A
Target B ------> Aspect[B] ---- calls của B
Target C ------> Aspect[C] ---- calls của C
```

Với mỗi target, aspect có thể giữ:

- Counter số lần target được gọi.
- Cache cục bộ cho **chính target ấy**.
- Metadata đã tính trước từ cấu hình/type của target.
- Trạng thái quan sát riêng cho target.
- Resource phụ thuộc vòng đời target, nếu cách cleanup được thiết kế đúng.

### State được cô lập theo đối tượng, không theo request

Nếu hai thread cùng gọi **Target A**, chúng **vẫn chia sẻ Aspect[A]**. Per-target **không làm state tự thread-safe**.

Nếu một request xử lý nhiều target A và B, nó **không tự có một aspect instance chung theo request**. Ngược lại, nếu một target được dùng lại qua nhiều request, aspect gắn với target cũng sống qua nhiều request. **Per-target ≠ per-request**.

### Association: dùng identity hay equals?

Hai target object có thể trả `true` trong `equals()` nhưng vẫn là hai instance khác nhau. Nếu mục tiêu là **mỗi object identity có aspect riêng**, một `HashMap<Target,Aspect>` dựa trên `equals/hashCode` có thể vô tình gộp hai instance.

Một mô hình gắn theo **object identity** cần sử dụng semantics identity, ví dụ `IdentityHashMap` trong một demo tuần tự; trong hệ thống đa luồng cần giải pháp identity-aware và thread-safe phù hợp.

**Không tự coi object “có cùng mã khách hàng” là cùng target instance.** Business identity và object identity là hai khái niệm khác nhau.

## 7. “Per this” và “per target”: không được đánh đồng

Một số mô hình AOP cho phép gắn aspect instance với **đối tượng được binding là `this`** hoặc **đối tượng được binding là `target`** tại những join point khớp.

Hai biến ngữ cảnh này phụ thuộc loại join point và engine:

- **`this`:** thường liên quan tới object mà join point đang xảy ra *trong ngữ cảnh của nó*.
- **`target`:** thường liên quan tới receiver/đối tượng đích của lời gọi hoặc execution.

Trong một số tình huống method call, **caller object** và **callee receiver** là hai object khác nhau; ở một số execution join point, chúng có thể là cùng đối tượng thực thi. Với static context, constructor, reflective invocation hoặc proxy, semantics còn phụ thuộc mô hình join point của engine.

Ví dụ khái niệm:

```text
OrderWorkflow.submit()
     |
     +---- call ----> PaymentService.charge()
          caller object: OrderWorkflow
          target object: PaymentService
```

Nếu cơ chế AOP diễn giải `this` theo caller context của **method call join point**, còn `target` theo receiver `PaymentService`, “per-this” và “per-target” có thể tạo **hai hệ association khác nhau**.

**Đừng suy đoán một câu cú pháp per-object luôn gắn vào target class.** Đọc đúng semantics binding mà engine hỗ trợ cho từng loại join point.

### Có phải cứ tạo object là tạo aspect tương ứng ngay?

Không nhất thiết. Một số mô hình tạo aspect **khi join point đầu tiên thỏa điều kiện**, không phải ngay lúc constructor target chạy. Một object chưa từng đi qua pointcut có thể **không có aspect instance được tạo**. Điều này liên quan trực tiếp tới memory footprint và semantics “lần đầu”.

## 8. Aspect theo luồng điều khiển: per-control-flow

**Dynamic control flow** là chuỗi thực thi đang diễn ra, ví dụ lời gọi `Checkout.placeOrder()` và những method được gọi đồng bộ bên trong nó. Một số engine cung cấp kiểu tạo aspect instance **cho từng lượt vào một luồng điều khiển được chọn**.

```text
Flow #1: checkout(orderA)
  AspectFlow #1
     -> validate()
     -> reserve()
     -> charge()

Flow #2: checkout(orderB)
  AspectFlow #2
     -> validate()
     -> reserve()
     -> charge()
```

AspectFlow #1 và #2 tách state theo **lượt vào flow**, không phải theo target hay theo tên thread tự thân. Ý nghĩa “bắt đầu” và “kết thúc” của flow do điều kiện pointcut và engine xác định.

### Flow nằm trong stack đồng bộ

Một luồng điều khiển động thường dựa trên stack/quan hệ gọi đang hoạt động. Nếu `checkout` gửi `Runnable` sang một executor, stack worker **khác** stack caller. Không thể mặc định aspect instance của flow caller **tự chuyển** sang worker.

Muốn giữ state theo tác vụ/request qua async, cần thiết kế **context propagation** hoặc API scope riêng. Điều đó khác việc engine tự hỗ trợ per-control-flow tại join point đồng bộ.

### Nested flow và recursion

Nếu một flow gốc gọi lại chính nó hoặc mở một flow con:

```text
checkout(A)            -> Aspect flow A
   |
   +-- checkout(B)     -> Aspect flow B ? hay vẫn A ?
   |
   +-- return
```

Câu trả lời phụ thuộc **chính xác quy tắc instantiation** của công cụ (ví dụ phân biệt điều kiện bao gồm hay loại trừ chính join point mở flow) và cách scope lồng nhau được quản lý. Không tự giả định mỗi lời gọi cùng tên đều tạo một aspect mới, cũng không giả định chỉ có một aspect cho toàn bộ recursion.

Thiết kế đúng cần mô tả:

1. Join point nào **khởi tạo** flow?
2. Các join point **bên trong** sử dụng instance nào?
3. Khi flow lồng nhau, stack aspect instance có tách lớp không?
4. Exit bình thường, throw hoặc cancel xử lý cleanup ra sao?
5. Có propagate qua thread/task hay không?

### `per-control-flow` không đồng nghĩa `ThreadLocal`

Một engine có thể sử dụng cấu trúc gắn theo thread để quản lý stack flow, nhưng **ngữ nghĩa** là *scope theo lượt vào flow*. `ThreadLocal` là một API lưu giá trị **theo thread**; thread pool có thể chạy nhiều flow nối tiếp và một thread có thể chứa nhiều scope lồng nhau. Chỉ `ThreadLocal.set(new Aspect())` mà không push/pop/restore theo flow không đủ để tạo mô hình per-control-flow đúng.

## 9. Mô hình mỗi lượt gọi: per-invocation

Một số hệ thống cho phép **state riêng cho từng advice invocation**; nếu muốn, ta có thể tạo một object xử lý mới cho mỗi lần interception.

```text
Service.process("A") -> Aspect #1 -> state #1
Service.process("B") -> Aspect #2 -> state #2
Service.process("C") -> Aspect #3 -> state #3
```

Lợi điểm:

- Dữ liệu mutable của mỗi lượt gọi không bị chia sẻ với lượt khác nếu không trỏ tới resource chung.
- Lifetime đơn giản trong một advice synchronous: tạo → dùng → bỏ reference.
- Thích hợp cho work state nhỏ, chain state hoặc điều kiện chỉ tồn tại trong một lần proceed.

Đánh đổi:

- Tốn cấp phát và khởi tạo nếu làm rất thường xuyên.
- Cache không tích lũy giữa lần gọi.
- Có thể tạo nhiều instance vô ích nếu stateless aspect vốn có thể dùng chung.
- Một object per-invocation **không tự cô lập shared dependencies** hay target object mutable.

**Không cần luôn tạo aspect mới để có local state mới.** Một shared around advice với biến local thường đạt cùng sự cô lập invocation mà không phát sinh toàn bộ một instance aspect mỗi lần.

## 10. Aspect theo request, session hoặc tác vụ: context-managed scope

Trong ứng dụng nhiều tầng, người viết đôi khi muốn “một aspect instance cho mỗi request”. Đây là **một mô hình scope nghiệp vụ**, nhưng không nhất thiết trùng với một kiểu instantiation được AOP engine cung cấp.

```text
Request R1
   -> Task A (thread #1)
   -> Task B (thread #3)
   -> callback (thread #2)

Request R2
   -> Task C (thread #1)
```

Một request có thể chuyển qua nhiều thread; một thread có thể xử lý nhiều request nối tiếp. Do đó:

**Per request ≠ per thread; per task ≠ per thread; per flow theo stack ≠ per request bất đồng bộ.**

Nếu muốn aspect state theo request, cần:

- Xác định **request identity** và lifecycle bắt đầu/kết thúc.
- Tạo/đăng ký aspect state vào một **context carrier** hoặc scope manager.
- Truyền context rõ qua executor/callback/message nếu cần.
- Khôi phục previous context ở worker và cleanup bằng `finally`.
- Xử lý cancellation, exception, timeout và retry.
- Không cho thread pool giữ state request cũ sang task mới.

### Một warning về bảo mật

Không đưa toàn bộ session hay credential vào aspect field dùng chung để “tiện access”. Một aspect đọc identity từ context đã xác thực tại boundary cần thiết **không có nghĩa** context ấy tự bảo đảm authorization. Phải tránh rò metadata giữa yêu cầu và thực thi kiểm soát quyền tại ranh giới đáng tin.

## 11. Ví dụ Java 17+ chạy được: shared, per-target và per-invocation

Ví dụ này dùng **Java Dynamic Proxy** để mô phỏng một cơ chế AOP nhỏ, chỉ sử dụng Java SE. Mỗi proxy nhận một **`Supplier<AspectState>`** để quyết định aspect instance nào được dùng **tại thời điểm interception**.

Chúng ta lần lượt triển khai:

1. **Shared:** hai proxy cho hai target dùng **cùng một `AspectState`**.
2. **Per-target:** mỗi target có **một state riêng**, được tra cứu theo object identity.
3. **Per-invocation:** mỗi lần handler được gọi sẽ tạo **một state mới**.
4. **Raw target và self-invocation:** minh họa nơi proxy advice **không có cơ hội chạy**.

Không có DSL pointcut đầy đủ trong demo; handler mô phỏng before advice cho những method đi qua proxy. Demo **không khẳng định mọi công cụ AOP tự hỗ trợ đúng ba chính sách này**. Đây là cách tách rõ **lifecycle của aspect state** khỏi **lifecycle target/proxy**.

### 11.1. File `AspectScopeDemo.java`

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.IdentityHashMap;
import java.util.Map;
import java.util.function.Supplier;

public class AspectScopeDemo {

    interface Service {
        String process(String value);
        String outer(String value);
    }

    static final class Target implements Service {
        private final String id;

        Target(String id) {
            this.id = id;
        }

        @Override
        public String process(String value) {
            System.out.println("target[" + id + "].process " + value);
            return "ok:" + id + ":" + value;
        }

        @Override
        public String outer(String value) {
            System.out.println("target[" + id + "].outer " + value);
            // this trỏ tới Target: lời gọi nội bộ bỏ qua wrapper proxy.
            return this.process(value + "!");
        }
    }

    static final class AspectState {
        private final String name;
        private int count;

        AspectState(String name) {
            this.name = name;
        }

        void before(String event) {
            count++;
            System.out.println(
                    "advice[" + name + "] #" + count + " " + event);
        }
    }

    static Service wrap(
            Service target,
            Supplier<AspectState> aspectProvider) {
        return (Service) Proxy.newProxyInstance(
                Service.class.getClassLoader(),
                new Class<?>[] { Service.class },
                (proxy, method, arguments) -> {
                    AspectState aspect = aspectProvider.get();
                    aspect.before(
                            method.getName() + ":" + arguments[0]);
                    return callTarget(method, target, arguments);
                }
        );
    }

    static Object callTarget(
            Method method, Service target, Object[] arguments)
            throws Throwable {
        try {
            return method.invoke(target, arguments);
        } catch (InvocationTargetException wrapped) {
            throw wrapped.getCause();
        }
    }

    public static void main(String[] args) {

        Target a = new Target("A");
        Target b = new Target("B");

        System.out.println("== shared ==");
        AspectState shared = new AspectState("shared");
        Service sharedA = wrap(a, () -> shared);
        Service sharedB = wrap(b, () -> shared);

        System.out.println("caller " + sharedA.process("a1"));
        System.out.println("caller " + sharedB.process("b1"));
        System.out.println("caller " + sharedA.outer("a2"));

        System.out.println("== per-target ==");
        // Demo chạy tuần tự, nên IdentityHashMap đủ để minh họa
        // phân biệt hai instance target. Không dùng như map đa luồng.
        Map<Service, AspectState> perTarget = new IdentityHashMap<>();

        Service scopedA = wrap(a, () -> perTarget.computeIfAbsent(
                a, ignored -> new AspectState("target-A")));
        Service scopedB = wrap(b, () -> perTarget.computeIfAbsent(
                b, ignored -> new AspectState("target-B")));

        System.out.println("caller " + scopedA.process("a3"));
        System.out.println("caller " + scopedA.process("a4"));
        System.out.println("caller " + scopedB.process("b2"));

        System.out.println("== per-invocation ==");
        Service eachCall = wrap(
                a, () -> new AspectState("invocation"));

        System.out.println("caller " + eachCall.process("a5"));
        System.out.println("caller " + eachCall.process("a6"));

        System.out.println("== raw ==");
        System.out.println("caller " + a.process("a7"));
    }
}
```

Chạy với **JDK 17 trở lên**:

```bash
javac -encoding UTF-8 AspectScopeDemo.java
java AspectScopeDemo
```

**Standard output dự kiến:**

```text
== shared ==
advice[shared] #1 process:a1
target[A].process a1
caller ok:A:a1
advice[shared] #2 process:b1
target[B].process b1
caller ok:B:b1
advice[shared] #3 outer:a2
target[A].outer a2
target[A].process a2!
caller ok:A:a2!
== per-target ==
advice[target-A] #1 process:a3
target[A].process a3
caller ok:A:a3
advice[target-A] #2 process:a4
target[A].process a4
caller ok:A:a4
advice[target-B] #1 process:b2
target[B].process b2
caller ok:B:b2
== per-invocation ==
advice[invocation] #1 process:a5
target[A].process a5
caller ok:A:a5
advice[invocation] #1 process:a6
target[A].process a6
caller ok:A:a6
== raw ==
target[A].process a7
caller ok:A:a7
```

### 11.2. Đọc nhánh shared

`sharedA` và `sharedB` wrap **hai target khác nhau** nhưng `aspectProvider.get()` luôn trả **cùng `shared`**. Vì vậy count lần lượt là **#1, #2, #3** — không reset khi đổi target.

Tuy nhiên, ở `sharedA.outer("a2")`:

- Handler thấy `outer` và tăng shared count tới #3.
- Target A thực thi `outer`.
- Target gọi `this.process("a2!")` nội bộ.
- Lời gọi nội bộ **không qua wrapper proxy** nên **không thêm** dòng `advice[shared] ... process:a2!`.

Vì thế **vòng đời aspect** và **proxy coverage** là hai trục độc lập. Dùng chung một aspect không làm proxy quan sát được mọi method execution bên trong target.

### 11.3. Đọc nhánh per-target

`perTarget` là `IdentityHashMap` để mô phỏng association theo **object identity**. Lần đầu lời gọi qua `scopedA`, `computeIfAbsent` tạo `AspectState("target-A")`. Lần kế tiếp trên target A dùng lại instance đó, count thành **#2**. Target B được tạo instance riêng nên count bắt đầu **#1**.

Demo dùng map này **ở một luồng tuần tự**. `IdentityHashMap` **không thread-safe** và không phải gợi ý triển khai trực tiếp cho một AOP runtime đa luồng. Trong production, cần một scope manager có lifecycle, synchronization và chiến lược tránh memory retention thích hợp.

### 11.4. Đọc nhánh per-invocation

Supplier tạo `new AspectState("invocation")` **mỗi khi handler chạy**. Vì mỗi state vừa được tạo có count ban đầu bằng 0, hai lời gọi đều in **#1**. Không có trạng thái tích lũy giữa hai lần `process`.

### 11.5. Đọc nhánh raw

`a.process("a7")` đi trực tiếp vào target, không qua bất kỳ proxy nào. Vì vậy dù target A từng có proxy shared, per-target và per-invocation, **lời gọi raw không dùng một aspect state nào trong ba proxy**.

Wrap một target **không thay đổi chính target** thành proxy và không thu hồi các raw references đã tồn tại.

### 11.6. Mô hình per-target được minh họa, không phải tự động AOP

`IdentityHashMap` trong ví dụ là một **scope registry do người viết tự tạo**, không phải một cơ chế instantiation chuẩn bắt buộc. Một engine AOP có hỗ trợ per-object có thể quản lý association, GC và cleanup theo cách khác, hoặc chỉ tạo instance khi một pointcut khớp lần đầu. Ví dụ chỉ minh họa **hệ quả của việc cùng target dùng cùng aspect state**.

## 12. Kiểm thử vòng đời: số lượt advice không phải số aspect instance

Có thể thêm log vào constructor `AspectState` để đếm số object được tạo. Nhưng nên tách hai metric:

1. **Aspect instance created:** một object aspect được tạo.
2. **Advice invocation count:** bao nhiêu lượt advice đã chạy.

Với chương trình trên:

| Scope | Số instance phục vụ lượt gọi minh họa | Số lượt advice |
| --- | ---: | ---: |
| Shared | 1 | 3 |
| Per-target | 2 | 3 |
| Per-invocation | 2 | 2 |
| Raw call | 0 instance aspect mới được sử dụng | 0 |

Bảng chỉ tính những hành vi ở đúng phần demo tương ứng. Bản thân object `AspectState` có thể được khởi tạo trước, lúc lookup hoặc lúc interception tùy cách provider được viết. **Không đồng nhất “có log 3 lần” với “tạo 3 aspect”.**

### State lifecycle và target lifecycle khác nhau

Target A được tạo **trước** cả proxy per-target và per-invocation. Aspect per-target của A chỉ được tạo **khi Supplier được gọi lần đầu**. Một engine hỗ trợ per-target native có thể có semantics tạo ở điểm khác; phải đọc contract công cụ chứ không suy từ ví dụ.

## 13. Aspect instance được tạo lúc nào?

Các khả năng thường gặp:

- **Eager:** aspect instance được tạo lúc hệ thống AOP khởi tạo.
- **Lazy first-match:** instance được tạo khi join point đầu tiên phù hợp xảy ra.
- **On object association:** instance được gắn vào target khi object được đăng ký/khởi tạo hoặc ở lần match đầu tiên.
- **On flow entry:** tạo khi một luồng điều khiển động bắt đầu.
- **On invocation:** tạo mỗi lượt advice.
- **On explicit scope begin:** ứng dụng mở request/task scope và tạo state.

Điểm cần phân biệt là:

**Thời điểm object đích được tạo ≠ thời điểm pointcut match ≠ thời điểm aspect được tạo ≠ thời điểm advice chạy.**

Nếu khởi tạo aspect có side effect — mở connection, đăng ký listener, đọc cấu hình — lựa chọn eager/lazy có ảnh hưởng. Một aspect được tạo khi first match nhưng target không bao giờ được gọi sẽ không có side effect khởi tạo đó. Ngược lại, việc khởi tạo eager có thể xảy ra dù pointcut chưa bao giờ khớp.

### Tránh side effect nặng trong constructor aspect

Một aspect dùng chung có thể tồn tại dài hạn, nhưng không nên dựa vào constructor để tự động mở resource mà không có cơ chế đóng. Một aspect per-invocation có thể tạo rất nhiều instance, nên constructor đắt đỏ gây overhead lớn.

Tốt hơn là thiết kế các dependency/resource với ownership và lifecycle riêng: **ai cấp, ai dùng, ai đóng**, thay vì suy luận tất cả resource sống cùng aspect.

## 14. Khi nào aspect instance bị hủy?

Java dùng garbage collection dựa trên khả năng còn được tham chiếu. **Không có callback hủy aspect instance chuẩn bắt buộc cho mọi mô hình AOP**. Một aspect gắn với target có thể bị giữ lâu nếu registry giữ reference mạnh tới target hoặc aspect.

Các trường hợp:

- Shared aspect thường sống tới khi scope manager/provider không còn giữ nó.
- Per-target aspect có thể sống cùng target nếu association cho phép GC cùng nhau.
- Per-invocation aspect có thể được GC sau khi lời gọi và mọi reference liên quan kết thúc.
- Per-control-flow aspect có thể trở nên không còn được tham chiếu khi flow kết thúc và scope stack được dọn.
- Per-request aspect có thể bị giữ lại nếu context lưu trong thread pool hoặc callback chưa được cleanup.

**Kết thúc logic của scope không đồng nghĩa object đã được GC ngay.** GC không phải một cơ chế đảm bảo cleanup tức thì của file handle, transaction hoặc connection.

### Weak references và memory leak

Một per-target registry dùng `HashMap<Target,Aspect>` mạnh có thể giữ cả target và aspect sống vô thời hạn khi ứng dụng không còn dùng target. `WeakHashMap` có thể hữu ích trong một số trường hợp, nhưng:

- Nó sử dụng semantics `equals/hashCode` chứ không tự trở thành weak identity map.
- Nếu **value aspect tham chiếu mạnh ngược về target**, key yếu có thể vẫn không được thu gom như mong muốn do đường tham chiếu qua map value.
- Concurrency và tính nhất quán của scope vẫn cần thiết kế riêng.
- Một engine AOP có thể có cách quản lý association/GC không dựa trên map thông thường.

Không chọn `WeakHashMap` chỉ vì “weak sẽ hết leak”. Phải kiểm tra **reference graph** và lifetime toàn hệ thống.

## 15. Reentrancy: cùng aspect được gọi lồng nhau

**Reentrancy** xảy ra khi một lời gọi advice/target khiến cùng aspect tham gia một join point khác **trước khi lượt trước kết thúc**. Đây không nhất thiết là concurrency đa luồng.

```text
Thread A:
  Aspect.before(method A)
      |
      +--> call method B
              |
          Aspect.before(method B)
      |
  Aspect.after(method A)
```

Với shared aspect, mọi lời gọi lồng nhau có thể cùng truy cập một instance. Nếu advice dùng field `currentOperation` để giữ trạng thái tạm, lời gọi B ghi đè nó ngay trong **cùng thread** — lỗi vẫn xảy ra dù không có thread race.

### Một giải pháp: state theo invocation stack

- Biến local của advice nếu code bao trọn invocation.
- Stack state theo flow với push/pop và `finally`.
- Context object gắn rõ vào join point chain nếu engine hỗ trợ.
- Tránh một field toàn cục “current advice call” trên singleton.

**Thread-safety không đồng nghĩa reentrancy-safety.** Một `synchronized` method có thể giữ lock trong lời gọi đệ quy cùng thread, nhưng state “current operation” vẫn có thể bị ghi đè về mặt logic. Khóa không thay thế mô hình scope đúng.

## 16. Concurrency: per-target vẫn có thể bị truy cập song song

Một target singleton được sử dụng bởi nhiều thread:

```text
Thread 1 --> Target X --> Aspect[X]
Thread 2 --> Target X --> Aspect[X]
Thread 3 --> Target X --> Aspect[X]
```

Dù Aspect[X] **không chia sẻ với Target Y**, nó **vẫn được chia sẻ giữa ba thread** nếu cùng xử lý X. Nếu giữ một mutable counter không atomic, vẫn có lost updates.

Ngược lại, per-invocation state tự tạo cho mỗi lượt handler có thể cô lập các field của nó, nhưng target X vẫn có thể có race. **Vòng đời aspect không làm target thread-safe.**

### Chọn concurrency primitive theo ý nghĩa dữ liệu

| State cần quản lý | Phương án phù hợp thường gặp | Giới hạn |
| --- | --- | --- |
| Metric tổng số lượt gọi | `LongAdder` hoặc atomic counter | Không giải quyết tương quan giữa nhiều field |
| Cấu hình dùng chung | Immutable snapshot; publish an toàn | Reload phải có semantics nhất quán |
| Cache chung | Concurrent map/cache chuyên dụng | Loader, eviction, TTL và initialization có thể race |
| Dữ liệu mỗi invocation | Local variable / invocation context | Không tự đi qua async boundary |
| Dữ liệu mỗi target | Association theo object + synchronization phù hợp | Nhiều thread vẫn có thể cùng target |
| Dữ liệu mỗi request | Explicit context + propagation | Cần cleanup, quyền truy cập và lifetime rõ |

**Không dùng `volatile int count` để mong `count++` atomic**: volatile bảo đảm một số thuộc tính visibility/order, nhưng phép tăng vẫn là read–modify–write có thể tranh chấp.

## 17. Một shared aspect có thể chứa cache không?

Có, nếu cache **thực sự thuộc scope dùng chung**, key đủ phân biệt ngữ cảnh và việc truy cập an toàn.

Ví dụ, metadata cache theo method signature/type thường dùng lại được qua nhiều invocation. Nhưng **kết quả nghiệp vụ phụ thuộc request** không nên được cache chỉ theo tên method.

### Cache key là một phần của scope

Nếu per-target aspect cache theo field `lastResult`, hai lượt gọi trên cùng target nhưng argument khác có thể trả dữ liệu sai. Nếu shared aspect cache theo `methodName`, nhiều target có method cùng tên bị gộp.

Một cache đúng cần xem:

- **Object identity hay business identity?**
- Method overload và signature.
- Argument/value ảnh hưởng tới kết quả.
- Request/tenant/permission context nếu có.
- Version config, type loader/module, class generation.
- TTL, invalidation, memory bounds và concurrency.

**Lifecycle aspect là một chiều của cache lifetime, không thay thế cache correctness.**

## 18. State tĩnh và dependency chia sẻ làm scope bị “thủng”

Giả sử mỗi target có aspect instance riêng:

```java
// Mã minh họa:
final class PerTargetAspect {
    private static final java.util.List<String> GLOBAL_EVENTS =
            new java.util.ArrayList<>();

    void before(String name) {
        GLOBAL_EVENTS.add(name);
    }
}
```

Các instance khác nhau vẫn dùng **cùng `GLOBAL_EVENTS`** trong cùng một class identity. `ArrayList` lại không thread-safe cho nhiều thao tác đồng thời. Vì vậy “per-target aspect” không ngăn cross-target data mixing nếu state được giữ trong field static hoặc dependency singleton mutable.

Một aspect mới cũng có thể chia sẻ cùng `Logger`, `AuditSink`, `CacheService` hay `PolicyProvider`. Điều này có thể là chủ đích tốt, nhưng **cần phân biệt identity của aspect và identity của dependency**.

### Quy tắc thiết kế

- State **đặc trưng cho aspect instance** → instance field trong scope tương ứng.
- State **đặc trưng cho mỗi lượt gọi** → local/invocation context.
- State **đặc trưng cho target** → per-target scope hoặc key theo target.
- State **toàn cục/thống kê** → shared component được đồng bộ đúng.
- Secret/identity request → context rõ, không cất vào shared mutable field.

## 19. Gắn aspect với proxy hay với target?

Một proxy và target có thể là hai Java object khác nhau. Nếu scope manager dùng **proxy identity** làm key, tạo hai proxy cho cùng một target có thể sinh hai aspect instance. Nếu dùng **target identity** làm key, cả hai proxy có thể chia sẻ một aspect.

```text
           Proxy P1 ----+
                        |
                        v
                      Target T
                        ^
                        |
           Proxy P2 ----+
```

**Per-proxy:** `Aspect[P1]` khác `Aspect[P2]`.

**Per-target:** cả hai đường dùng `Aspect[T]` theo cùng identity target.

**Shared:** tất cả dùng một instance chung, kể cả target khác.

Ba cách này đều có thể có trong một thiết kế proxy custom. Không nên dùng từ “per-target” nhưng lại key bằng proxy trừ khi contract định nghĩa proxy chính là target được binding trong join point đó.

### Nested proxies

Nếu proxy B wrap proxy A, B có thể có aspect riêng của nó; A có aspect khác. Một lời gọi qua B có thể kích hoạt cả hai. Vòng đời hai aspect có thể khác, ví dụ tracing shared ở ngoài và audit per-target ở trong. Cần xác định precedence để biết điều gì chạy trước/sau và có bypass nào không.

## 20. Vòng đời aspect và loại advice

**Before/after/around** mô tả **thời điểm và quyền can thiệp**, không tự quyết định **aspect instantiation model**.

Một before advice có thể chạy trên shared aspect, per-target aspect hoặc một aspect per-flow. Một around advice có thể là singleton nhưng dùng local state cho mỗi invocation. Vì vậy:

- **“Around advice” ≠ “aspect mới mỗi lần gọi”.**
- **“After advice” ≠ “aspect bị hủy sau khi method kết thúc”.**
- **“Before advice được chạy lần đầu” ≠ “aspect chắc chắn vừa được tạo”.**
- **“Aspect singleton” ≠ “mọi target đều dùng một proxy duy nhất”.**

Một cách phân tích đầy đủ đặt các lựa chọn trên **hai trục**:

| Trục | Câu hỏi |
| --- | --- |
| **Advice kind** | Before, after-return, after-throw, finally, around? |
| **Aspect lifecycle** | Shared, per-object, per-flow, per-invocation hoặc scope khác? |

Ngoài ra còn trục thứ ba: **weaving/interception coverage**. Aspect được tạo đúng scope nhưng join point không được can thiệp thì advice vẫn không chạy.

## 21. Pointcut động và thời điểm chọn instance

Một pointcut có thể phụ thuộc:

- Method/type metadata tĩnh.
- Receiver/target object.
- Runtime argument values.
- Control-flow context.
- Annotation hoặc cấu hình.
- Trạng thái do engine/hook hỗ trợ.

Nếu aspect được tạo **trước** khi dynamic condition được đánh giá, số instance có thể khác so với một engine chỉ tạo instance **sau khi match**. Nếu pointcut condition thay đổi theo thời gian, association có thể tồn tại dù lượt gọi sau không còn thỏa điều kiện.

Ví dụ: “tạo aspect cho target T sau lần đầu target đi qua pointcut P”. Sau đó:

- Một số lần gọi T không khớp P nên không dùng advice.
- Association với T có thể vẫn còn.
- Những lần gọi T khớp P về sau có thể dùng lại aspect cũ.

**Không coi “có association rồi” là mọi lời gọi của target đều kích hoạt advice**. Matching và aspect instantiation là hai cơ chế cần phân tích riêng.

## 22. Per-control-flow: cleanup phải theo đúng stack

Một cách minh họa phạm vi flow:

```text
enter Flow A
  push Aspect[A]
  |
  +-- enter Flow B
  |      push Aspect[B]
  |      execute B
  |      pop Aspect[B] in finally
  |
  execute A
  pop Aspect[A] in finally
```

Khi exception thoát khỏi Flow B, cleanup vẫn phải pop đúng scope để Flow A lấy lại aspect instance của nó. Nếu chỉ đặt một biến thread-local đơn và quên restore, Flow A có thể đọc nhầm Aspect[B].

### Pseudocode quản lý scope

```java
// Minh họa logic; không phải chương trình độc lập.
AspectState previous = CURRENT.get();
AspectState current = new AspectState("flow");
try {
    CURRENT.set(current);
    proceed();
} finally {
    if (previous == null) {
        CURRENT.remove();
    } else {
        CURRENT.set(previous);
    }
}
```

Đây chỉ là hình thức lưu/khôi phục **một context slot** cho flow đồng bộ. Một per-flow engine thực tế có thể dùng stack riêng và khác nhau về join point nào tạo instance. Không tự kết luận đoạn này triển khai đầy đủ mọi semantics per-control-flow.

## 23. Async/task handoff: không thể đồng nhất flow với request

Giả sử:

```text
Thread A:
  request R starts
  Aspect[flow-A] created
  submit(task)
  request R returns

Thread B:
  run(task)
    -> target.method()
```

Trong mô hình dựa trên **đường gọi đồng bộ**, worker B không còn nằm trong stack A. Dù về nghiệp vụ task thuộc request R, nó không tự được dùng Aspect[flow-A]. Nếu cần một aspect/state **theo request xuyên thread**, phải thiết kế carrier có thể truyền context từ A sang B.

Cũng cần quyết định **task sống lâu hơn request** thì aspect state còn hợp lệ không. Nếu callback chạy sau khi request kết thúc, việc giữ reference tới toàn bộ request object/aspect có thể gây memory retention hoặc truy cập resource đã đóng.

### Propagation không đồng nghĩa authorization

Một request ID hoặc actor ID được truyền tới worker chỉ là dữ liệu. Các kiểm tra quyền thực tế phải dựa trên dữ liệu đã được xác minh ở boundary phù hợp. Không coi “worker nhận được cùng aspect instance” là một bằng chứng đủ rằng quyền bảo mật còn hiệu lực.

## 24. Aspect theo type/class và class loader identity

Một số engine hoặc thiết kế custom có thể tạo aspect instance **mỗi runtime type** được chọn. Điều này khác với:

- **Per-target:** mỗi object instance.
- **Shared singleton:** một object cho toàn bộ scope manager.
- **Per-type:** mỗi `Class<?>` hoặc type association.

Nếu class `Service` được định nghĩa bởi hai class loader khác nhau, JVM có thể coi đó là **hai runtime types khác nhau** dù tên binary giống nhau. Tương tự, các module layer/plugin có thể có vòng đời khác nhau.

Một per-type registry cần quan tâm:

- Class identity chứ không chỉ chuỗi tên class.
- Loader/module layer.
- Inheritance/override và class được chọn bởi pointcut.
- Cache invalidation khi class loader unload/reload.
- Reference mạnh từ registry tới `Class<?>` và loader gây memory leak.

**“Một aspect mỗi tên class”** không nhất thiết tương đương **“một aspect mỗi runtime type”** trong hệ thống modular/plugin.

## 25. Nếu aspect tự tạo thêm aspect thì sao?

Một shared aspect có thể gọi `new SomeAspect()` trực tiếp hoặc khởi tạo helper tạo instance phụ. Nhưng instance mới ấy **không mặc nhiên được AOP engine đăng ký** như aspect instance được dùng cho những join point đã weave.

Tương tự, target có thể được tạo ngoài proxy manager. **Object existence ≠ registration/association với join point runtime**.

Nếu công cụ AOP quản lý instance riêng, cần dùng contract chính thức để xác định:

- Ai tạo aspect?
- Ai chọn instance tại join point?
- Có được tự khởi tạo thủ công không?
- Tự tạo một object cùng class aspect có làm advice được gọi trên object ấy không?
- Instance đó được cleanup thế nào?

Không tự sửa lỗi “aspect sai vòng đời” bằng cách gọi `new Aspect()` rải rác trong business code, vì có thể tạo state không được dùng hoặc làm lệch semantics.

## 26. Memory and performance: shared không luôn tốt hơn

| Tiêu chí | Shared | Per-target | Per-invocation |
| --- | --- | --- | --- |
| Số instance aspect | Thường ít | Tỷ lệ với số target có association | Tỷ lệ với số invocation |
| Chi phí tạo | Thấp sau khởi tạo | Theo target/first match | Mỗi lần gọi |
| Khả năng cache theo target | Cần key | Thuận tiện | Thường kém |
| Concurrency state | Có thể nhiều thread cùng instance | Nhiều thread cùng target vẫn chia sẻ | State instance riêng mỗi invocation |
| Nguy cơ giữ state quá lâu | Cao với field request | Cao với registry giữ target | Thấp nếu không escape |
| Nguy cơ cấp phát/GC | Thường thấp | Theo số target | Cao hơn trên hot path |
| Cleanup | Theo scope chung | Theo association/lifetime target | Theo invocation/lifecycle phụ |
| Debug scope | Cần phân biệt target/request trong log | Dễ theo từng target | Dễ theo mỗi call |

Không nên tối ưu chỉ theo số object:

- Một shared aspect giữ một map lớn không giới hạn có thể tiêu thụ nhiều bộ nhớ hơn nhiều aspect nhỏ được giải phóng đúng.
- Per-invocation allocation có thể rẻ trong một số trường hợp nhưng tốn trên hot path.
- Per-target association cần bảo đảm không giữ references sau khi target ngừng sử dụng.
- Advice chạy ở mọi lượt method thường nhạy cảm với overhead nhỏ lặp lại.

**Đo thực tế** với tốc độ gọi, số target và lifetime của hệ thống, không chọn scope chỉ vì tên nghe “nhẹ”.

## 27. Chọn scope theo concern

### 27.1. Logging không giữ request state

Nếu chỉ cần ghi tên method và vài metadata, **shared/stateless aspect** thường hợp lý. Dữ liệu mỗi request truyền vào advice dưới dạng argument/context, không nằm trong field mutable.

### 27.2. Metric tổng lượt gọi

Một shared aspect với **concurrency-safe metric recorder** có thể phù hợp. Nhưng mỗi metric label cần tránh cardinality quá lớn. Nếu metric theo target instance, không nên dùng mỗi `System.identityHashCode` làm label công khai không giới hạn.

### 27.3. State giám sát riêng từng target

Một aspect per-target có thể giữ các giá trị liên quan target. Cần xem target dùng qua nhiều thread/request không, và có cơ chế cleanup association không.

### 27.4. Tracing và correlation

Một aspect shared có thể đọc trace context theo invocation/task; không cần lưu trace ID trong instance field shared. Nếu có per-flow model, nó chỉ phản ánh đúng **flow semantics** mà engine định nghĩa, không tự xuyên async.

### 27.5. Retry/fallback

Around advice có thể dùng state retry riêng cho **mỗi invocation** (số lần thử, deadline) ngay trong local variables. Không nên giữ `currentRetryAttempt` trong shared aspect field vì nhiều caller có thể đang retry cùng lúc.

### 27.6. Audit bắt buộc

Scope của aspect **không bảo đảm coverage**. Audit cần ranh giới có thể kiểm chứng rằng các entry point phù hợp đều được can thiệp; shared/per-target chỉ quyết định nơi state nằm sau khi advice chạy. Không coi “một aspect instance cho mỗi request” là biện pháp bảo mật thay cho kiểm soát quyền.

## 28. Thiết kế cấu hình và dependency cho lifecycle rõ ràng

Một hệ thống AOP có thể tách:

```text
Aspect definition
       |
       v
Aspect instance provider
       |
       +-- shared instance
       +-- instance by target identity
       +-- instance by invocation
       +-- instance by context key
       |
       v
Advice dispatcher
       |
       v
Join point / Target
```

**Instance provider** quyết định vòng đời. **Advice dispatcher** quyết định dùng instance nào khi join point khớp. **Pointcut matcher** quyết định join point có được chọn. **Target manager** quản lý object nghiệp vụ. Bốn thành phần có thể gộp trong một công cụ, nhưng tách chúng về mặt khái niệm giúp debug rõ ràng.

### Dependency bất biến hay mutable?

Một aspect instance có thể giữ các dependency như logger, policy snapshot hoặc metrics sink. Nếu dependency mutable được share nhiều scope, phải có contract thread safety. Ngược lại, nếu mỗi aspect instance mở một resource nặng, per-invocation có thể tạo quá nhiều resource. Tối ưu bằng cách **tách resource dùng chung khỏi state riêng**, không cưỡng ép cả aspect theo cùng lifecycle của resource.

## 29. Khi aspect dùng chung vẫn cần scope tại lời gọi

Với một shared around advice, có thể truyền invocation context tường minh qua chain:

```text
caller
  -> shared around advice
       create InvocationContext #1
       proceed(context #1)
       cleanup #1

caller khác
  -> shared around advice
       create InvocationContext #2
       proceed(context #2)
       cleanup #2
```

Mô hình này đạt cả hai:

- **Tái sử dụng code/dependency** của shared aspect.
- **Cô lập mutable state** của từng lượt gọi.

Một số công cụ có API join point/context object, số khác yêu cầu lập trình viên tự tạo immutable record hoặc local variables. Không nhất thiết phải chuyển toàn bộ aspect thành per-invocation để đạt isolation.

### Không phải mọi concern cần lưu state

Một advice xác thực input thuần có thể nhận argument rồi ném lỗi hoặc tiếp tục mà không cần field. Nếu mọi dữ liệu đều là input/output của từng lần gọi, **stateless shared aspect thường dễ reasoning, dễ test và ít lỗi concurrency**.

## 30. Vòng đời aspect và exception/finally

Một aspect instance per-flow hoặc per-invocation có thể sở hữu temporary scope. Khi target ném lỗi:

- Advice around/after-throwing có thể quan sát exception nếu cơ chế hỗ trợ.
- Cleanup phải chạy trong `finally` ở boundary phù hợp.
- Scope manager phải restore instance trước đó nếu nested.
- Exception từ cleanup cần có chính sách, tránh vô tình che lỗi target.
- Không giữ reference tới Throwable/request lớn sau khi scope kết thúc.

Nếu aspect instance vẫn tồn tại sau khi scope logic kết thúc vì bị cache hoặc ThreadLocal giữ reference, có thể gây retention. Điều này không tự có nghĩa advice tiếp tục được gọi; **lifetime tham chiếu và thời gian được phép sử dụng là hai khái niệm khác nhau**.

## 31. Vòng đời aspect trong proxy và bytecode weaving

Mô hình proxy có thể giữ một aspect instance trong invocation handler. Khi tạo proxy, ta có thể quyết định instance cố định hay `Supplier` động. Nhưng bytecode weaving trực tiếp tại method execution có thể sử dụng **một cơ chế instantiation/association khác**.

| Câu hỏi | Proxy/interceptor | Bytecode weaving |
| --- | --- | --- |
| Instance aspect lấy từ đâu? | Handler/provider hoặc dependency của proxy | Runtime của weaver/association được engine tạo |
| Có thể chia sẻ một instance qua nhiều target? | Có, nếu handler dùng cùng instance | Phụ thuộc cơ chế instantiation |
| Có thể gắn instance theo target? | Có nếu tự có registry/scope | Có thể nếu engine hỗ trợ per-object |
| Đường raw target có advice không? | Thường không qua wrapper proxy | Có thể nếu execution bytes đã weave |
| Self-invocation có được quan sát không? | Wrapper proxy thường bỏ qua | Có thể ở execution/call join point được weave |
| `new Aspect()` có tự đăng ký không? | Không tự | Không tự |
| Vòng đời có gắn chặt thread không? | Chỉ khi provider tự định nghĩa như vậy | Tùy engine/context policy |

**Không đồng nhất khái niệm “aspect instance” với “InvocationHandler object”.** Một handler có thể chứa một aspect, nhiều aspect hoặc chọn aspect động. Một aspect có thể được gọi qua nhiều handler.

## 32. Thứ tự advice và việc chọn aspect instance

Khi nhiều aspect cùng khớp, thứ tự advice có thể quyết định **khi nào một provider được yêu cầu**. Ví dụ:

```text
OuterAround
   |
   +-- nếu skip proceed: InnerAdvice không chạy
   |
   +-- nếu proceed: InnerAdvice chọn instance và chạy
```

Nếu inner aspect được tạo **lazy khi advice của nó được gọi**, việc outer quanh lời gọi không proceed khiến inner không được tạo trong tình huống đó. Nhưng nếu inner aspect được tạo **eager**, instance có thể đã tồn tại dù không chạy advice.

Vì thế không thể dùng một kết luận “advice không chạy nên aspect chắc chưa được tạo” nếu chưa biết initialization model.

### Ordering khác association

- **Precedence:** aspect/advice nào bao ngoài, chạy trước/sau?
- **Instantiation:** instance nào được dùng?
- **Pointcut matching:** join point có được chọn không?
- **Proceed behavior:** target/inner advice có thực sự được gọi không?

Chúng tương tác nhưng cần kiểm thử riêng.

## 33. Kiểm thử lifecycle: ma trận cần có

| Tình huống | Điều phải xác minh |
| --- | --- |
| Hai method cùng target, shared aspect | State được dùng chung đúng scope |
| Hai target khác nhau, shared aspect | State tổng có tăng qua cả hai target không? |
| Hai target khác nhau, per-target | Instance/state có tách đúng object identity? |
| Hai proxy cho một target | Scope per-proxy hay per-target đúng contract? |
| Hai object `equals() == true` nhưng khác identity | Registry có gộp sai instance không? |
| Một target được gọi từ hai thread | State per-target có thread-safe không? |
| Hai request trên cùng worker | Có rò context từ request trước không? |
| Một request đi qua hai thread | State theo request có được truyền hoặc tạo lại đúng không? |
| Hai flow lồng nhau | Stack aspect có restore scope ngoài đúng không? |
| Flow kết thúc bằng exception | Có cleanup association/context không? |
| Lời gọi recursive/reentrant | State “current invocation” có bị ghi đè không? |
| Around bỏ qua proceed | Inner aspect/advice có được tạo/chạy đúng semantics không? |
| Raw target gọi trực tiếp | Proxy advice có bị bypass như dự kiến? |
| Self-invocation trong wrapper proxy | Advice inner có thực sự chạy không? |
| Target được GC/unregister | Per-target registry có giữ target không cần thiết? |
| Plugin/class loader reload | Per-type/per-target cache có giữ loader cũ không? |
| Aspect bị tạo eager/lazy | Constructor có chạy đúng thời điểm? |
| Config/reload | Instance cũ dùng policy mới hay snapshot cũ? |
| Retry quanh target | Instance nào đếm lần thử và lần gọi của caller? |
| Exception từ advice | Cleanup và outcome caller đúng contract? |

Một bài test nên quan sát **instance identity**, **state value**, **advice invocation count** và **target execution count** riêng. Nếu chỉ nhìn thấy một dòng log, khó xác định đó là instance cũ hay mới.

### Một số cách kiểm tra trong Java

Có thể gắn một **monotonic test ID** cho mỗi `AspectState` trong phạm vi test để phân biệt object; hoặc so sánh `==` giữa những reference aspect nếu provider công bố hợp lệ. Không nên dùng `hashCode()` hay `System.identityHashCode` làm bằng chứng **duy nhất** về sự duy nhất của instance, vì hash có thể trùng.

## 34. Các lỗi phổ biến khi chọn vòng đời aspect

1. **“Aspect khai báo một lần thì JVM chỉ có một instance.”** Không chắc; phụ thuộc manager, loader và instantiation policy.
2. **“Một lần advice chạy là một aspect được tạo.”** Advice invocation khác aspect creation.
3. **“Per-target là per-request.”** Một target có thể phục vụ nhiều request.
4. **“Per-target an toàn trong đa luồng.”** Hai thread cùng dùng target vẫn có thể cùng vào một aspect.
5. **“Per-flow là ThreadLocal.”** Scope flow cần lifecycle/stack; ThreadLocal chỉ là một carrier gắn với thread.
6. **“Per-flow tự đi theo executor.”** Call stack đồng bộ không tự chuyển sang worker.
7. **“Một singleton aspect không thể dùng local state.”** Local variables là state theo lời gọi, tách biệt field dùng chung.
8. **“Dùng AtomicInteger bảo vệ mọi state.”** Nó chỉ giải quyết một số thao tác trên counter.
9. **“Đổi aspect thành per-invocation là sửa được target race.”** Target/dependency mutable vẫn có thể được chia sẻ.
10. **“Static field được cô lập theo aspect instance.”** Static thuộc class identity, không thuộc object instance.
11. **“Map per-target key theo equals luôn đúng.”** Nếu scope là object identity thì equals-based map có thể gộp sai.
12. **“WeakHashMap luôn tránh leak.”** Strong reference qua value hoặc cấu trúc khác có thể giữ key.
13. **“Aspect theo target sẽ được tạo ngay lúc new Target.”** Có thể chỉ tạo ở lần join point match đầu tiên.
14. **“Một proxy có một aspect instance.”** Handler có thể dùng provider động hoặc nhiều aspects.
15. **“Có aspect shared là mọi lời gọi raw target đều có advice.”** Proxy coverage là một vấn đề khác.
16. **“Aspect instance kết thúc thì resource tự đóng ngay.”** GC không thay cho cleanup rõ ràng.
17. **“Scope request là một thread.”** Thread pool, async và callback phá giả định ấy.
18. **“Đủ counter metric là đủ kiểm chứng lifecycle.”** Cần cả creation count, instance identity và invocation count.
19. **“Thay lifecycle không ảnh hưởng logic.”** Các field/cache/ordering có thể làm outcome khác.
20. **“Cứ dùng scope hẹp nhất là tối ưu.”** Cấp phát, resource và association overhead có thể tăng lớn.
21. **“Shared state sai vì luôn nguy hiểm.”** Shared immutable/stateless hoặc concurrency-safe state có thể là lựa chọn tốt.
22. **“Một aspect theo context chắc được engine hỗ trợ.”** Phải kiểm tra loại scope native hoặc tự xây lifecycle rõ.
23. **“Một class loader mới vẫn dùng singleton instance của class loader cũ.”** Class identity/scope provider có thể khác nhau.
24. **“Một instance per-target tự xóa khi target không còn dùng.”** Registry/reference graph quyết định retention.

## 35. Bài tập tự luyện

1. Chạy `AspectScopeDemo.java` và giải thích tại sao shared count tăng #1 → #2 → #3 dù lời gọi đi qua hai target A/B.
2. Trong nhánh shared, đổi thứ tự gọi B trước A. Dự đoán thứ tự count mà không thay đổi number of instances.
3. Thêm `scopedA.outer("x")` trong nhánh per-target. Có tăng count cho method `process("x!")` nội bộ không? Vì sao?
4. Bỏ proxy và gọi trực tiếp `a.process("z")`; so sánh số target execution và advice invocation.
5. Tạo một proxy thứ hai cho target A nhưng dùng cùng `perTarget` map. State target-A còn được dùng chung không? Khi nào việc key bằng proxy thay đổi kết quả?
6. Thay `IdentityHashMap` bằng `HashMap`, đồng thời cho hai target có `equals/hashCode` bằng nhau. Phân tích nguy cơ gộp association.
7. Đổi `AspectState.count` thành `AtomicInteger`. Biện pháp này sửa vấn đề gì và còn vấn đề nào không được sửa?
8. Thiết kế shared aspect ghi trace ID của mỗi invocation: dùng local/context thay vì mutable field `currentTraceId`.
9. Vẽ timeline hai lời gọi lồng nhau trên cùng thread, minh họa lý do một field `currentOperation` có thể sai dù không có concurrency.
10. Tạo một per-flow scope stack bằng `ThreadLocal<Deque<AspectState>>` và `try/finally`; kiểm thử nested flow và exception.
11. Chuyển một công việc thuộc flow caller sang `ExecutorService`. Giải thích dữ liệu nào không tự có trên worker và trách nhiệm của context carrier.
12. Xây một per-request provider cho nhiều callback trên nhiều thread. Xác định rõ begin/end, cancellation và cleanup.
13. Tạo registry per-target với weak references. Vẽ reference graph có value quay về target và chỉ ra vì sao có thể leak.
14. Thêm một aspect dùng chung chứa cache method metadata. Chọn cache key phù hợp trong hệ thống có overload và nhiều class loader.
15. So sánh metric “số aspect instance tạo ra” với “số lượt target method được gọi”; trường hợp nào hai số này có thể rất khác?
16. Thiết kế một integration test cho hai target được dùng song song. Xác minh per-target aspect cô lập state giữa target nhưng vẫn concurrency-safe trên cùng target.
17. Phân tích một ứng dụng plugin reload nhiều lần: aspect per-type và cache phải quản lý class loader lifecycle ra sao?
18. Đổi provider trong demo thành `() -> new AspectState("new")` cho cả hai proxy. Scope thật là per-target hay per-invocation? Giải thích theo thời điểm provider được gọi.
19. Thêm outer around advice có thể không `proceed`. Aspect inner tạo lazy có được khởi tạo ở đường skip không?
20. Nêu một tình huống nên dùng shared/stateless aspect thay vì per-invocation dù cần đo thời gian chính xác từng lời gọi.
21. Lập bảng thiết kế cho ba concern: logging, audit theo target, tracing theo request; chọn scope của aspect, scope của state và cơ chế cleanup.
22. Thiết kế policy khi target được dispose nhưng proxy còn sống; tìm những reference có thể giữ aspect không giải phóng.
23. Giải thích vì sao một aspect per-target **không tự** ngăn lời gọi `this.inner()` bypass wrapper proxy.
24. Đề xuất test phân biệt (a) advice không match, (b) instance aspect đã có nhưng advice không chạy, (c) lazy aspect chưa được tạo.

**Tự kiểm tra:** Aspect type, aspect instance và advice invocation khác nhau thế nào? Khi nào shared aspect có thể stateless mà vẫn giữ local state mỗi lượt? Per-target có bảo đảm an toàn đa luồng không? Vì sao per-flow không tự xuyên qua executor? Tại sao `static` field không được cô lập bởi per-invocation? Một target có hai proxy có thể dùng một hay hai aspect instance tùy điều gì? Khi nào weak key vẫn dẫn tới memory leak? Làm sao kiểm tra lifecycle mà không nhầm với số log?

## Kết luận

**Aspect dùng chung và aspect được tạo theo ngữ cảnh khác nhau ở phạm vi gắn state và thời gian sống của instance, không chỉ ở số lần advice được gọi.** Aspect shared phù hợp khi stateless, immutable hoặc dùng state được thiết kế chia sẻ đúng; aspect per-target/per-object gắn state với object tương ứng nhưng vẫn cần concurrency control; aspect per-flow/per-invocation cô lập state ở phạm vi động hẹp hơn nhưng cần quản lý nested scope, cleanup và ranh giới bất đồng bộ. Không có lựa chọn “luôn tốt nhất” cho mọi concern.

Khi thiết kế AOP, hãy quyết định tường minh **instance được tạo khi nào, key association là gì, những join point nào được dùng cùng instance, ai giữ reference, ai cleanup, và có bao nhiêu thread/task có thể cùng truy cập**. Sau đó kiểm thử **creation count, instance identity, advice invocations, target executions, raw/proxy bypass và exception paths**. Tách biệt lifecycle với pointcut matching và weaving/interception coverage là chìa khóa để Aspect thực thi đúng, không rò ngữ cảnh và có thể mở rộng an toàn.
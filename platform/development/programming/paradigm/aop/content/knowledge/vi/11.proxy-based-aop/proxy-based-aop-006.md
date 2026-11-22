# Đối tượng được tạo ngoài cơ chế quản lý proxy trong AOP

Trong **lập trình hướng khía cạnh (Aspect-Oriented Programming – AOP)**, một cách triển khai phổ biến là đặt **proxy (đối tượng trung gian)** trước đối tượng nghiệp vụ. Proxy nhận lời gọi, áp dụng advice phù hợp rồi chuyển tiếp đến target. Cách này có thể bổ sung logging, audit, tracing, đo thời gian hay các hành vi xuyên suốt khác **mà không phải sửa thân phương thức nghiệp vụ**.

Tuy nhiên, một giới hạn rất quan trọng xuất hiện khi chương trình **tự tạo đối tượng đích ngoài cơ chế tạo, đăng ký hoặc cung cấp proxy**, ví dụ:

```java
DocumentService service = new DocumentService();
service.save("DOC-17");
```

Nếu `service` ở đây là **đối tượng gốc (raw target)** và không có interception khác, lời gọi đi **thẳng vào target**, không qua proxy. Một pointcut dù mô tả đúng `save(String)` cũng **không làm advice tự xuất hiện trên đường gọi ấy**.

**Ý chính:** Proxy AOP kiểm soát **đường đi của lời gọi qua proxy**, không tự kiểm soát toàn bộ các instance của một class. Điều quyết định là **reference mà caller thật sự dùng**, **ai tạo và phân phối reference đó**, và **lời gọi có đi qua interceptor không** — chứ không đơn thuần là tên class hay annotation trên method.

> Bài này nói về **AOP nói chung**, từ cơ bản đến nâng cao. Các thuật ngữ “managed”, “unmanaged”, “factory”, “registry”, “proxy provider” được dùng ở nghĩa kiến trúc tổng quát, **không gắn với một framework cụ thể**. Giới hạn ở đây là của **proxy-based interception**; một hệ thống AOP dệt bytecode tại compile time hoặc load time có thể có phạm vi khác nếu những join point tương ứng thực sự đã được weave.

## 1. Bản chất của cơ chế AOP qua proxy

Một proxy có thể triển khai cùng giao diện với target và ủy quyền lời gọi sau khi chạy advice:

```text
                  Đường có interception

Caller --> Proxy --> Before advice --> Target.method(...)
              ^                            |
              |                            v
              +---- After / around <--- Result / Exception
              |
         Caller nhận outcome
```

Nếu caller giữ reference trực tiếp:

```text
                  Đường không đi qua proxy

Caller -----------------------> Target.method(...)
                                        |
                                        v
                                Result / Exception
```

Điều này **không đồng nghĩa method thiếu annotation** hay **pointcut không hợp lệ**. Thông thường, điểm khác nằm ở **object được gọi**: caller gọi `proxy.method(...)` hay `rawTarget.method(...)`.

### Tách ba điều kiện độc lập

Để advice của mô hình proxy chạy, cần đồng thời:

1. **Có interception boundary:** proxy/interceptor thật sự tồn tại, có cơ chế chuyển tiếp hợp lệ.
2. **Caller đi qua boundary:** reference nhận lời gọi là proxy hoặc một adapter/hook tương đương.
3. **Advice được chọn:** quy tắc type, method, signature, annotation, ngữ cảnh hoặc predicate động khớp theo semantics của interceptor.

Một method khớp pointcut nhưng bị gọi trực tiếp có thể bỏ qua advice. Ngược lại, caller đi qua proxy nhưng method không khớp pointcut thì proxy vẫn có thể chuyển tiếp mà **không áp dụng concern đó**. Phải chẩn đoán hai tình huống khác nhau.

## 2. “Đối tượng được quản lý” nghĩa là gì?

Trong phạm vi kiến thức này, một **cơ chế quản lý proxy** có thể là:

- Factory chuyên tạo **target rồi wrap thành proxy**.
- Registry/service locator chỉ công bố **reference proxy** tới client.
- Một thành phần dựng object graph rồi đưa **proxy** vào những điểm phụ thuộc.
- Một pipeline interceptor cho phép đăng ký target/handler.
- Một API wrapper chính thức để caller yêu cầu object đã được can thiệp.

Không nhất thiết có một container hay framework. Ví dụ rất đơn giản:

```java
// Đoạn minh họa ý tưởng, không phải chương trình độc lập.
Operations service = ProxyFactory.create();
service.process("A");
```

Nếu `create()` trả proxy, caller gọi qua proxy. Nhưng:

```java
Operations service = new OperationsImpl();
service.process("A");
```

thì caller trực tiếp giữ target, **trừ khi bytecode của target/call site còn được instrument bằng cơ chế khác**.

**Không nên định nghĩa “managed” chỉ là “object được lưu trong một map”.** Một registry giữ raw target vẫn cung cấp đường bypass. Giá trị của cơ chế quản lý là nó **bảo đảm reference mà consumer cần dùng đi qua interception boundary** theo một contract rõ ràng.

### Chỉ tạo proxy thôi chưa đủ

```text
factory:
    target = new Service()
    proxy = wrap(target)
    return proxy
```

Nếu code khác vẫn được trả `target`, hoặc biết cách tự gọi `new Service()` rồi sử dụng, phạm vi proxy chưa toàn diện. Kiến trúc cần quản lý cả **quyền sở hữu target** và **cách phân phối reference**.

## 3. Các đường tạo đối tượng dễ đi ngoài cơ chế proxy

| Đường tạo/lấy object | Ví dụ | Nguy cơ với proxy AOP |
| --- | --- | --- |
| Tạo trực tiếp | `new Service()` | Caller nhận raw instance |
| Static factory không wrap | `Service.createDefault()` | Factory trả raw instance |
| Factory do client tự viết | `() -> new Service()` | Không đi qua factory cấp proxy |
| Reflection | `constructor.newInstance(...)` | Tạo raw instance nếu không wrap |
| Deserialization | Object được tái tạo từ dữ liệu | Instance có thể không đi qua proxy provider |
| Clone/copy | `clone()`, copy constructor | Instance khác raw hoặc metadata/interception bị mất |
| Callback/plugin tự tạo | Plugin tạo instance rồi đăng ký | Provider không kiểm soát reference ban đầu |
| Test tạo fixture | `new Service()` trong unit test | Test có thể bỏ qua advice khi integration cần kiểm |
| Một thư viện tự tạo dependency | Nội bộ thư viện dùng constructor/factory riêng | Interception boundary bên ngoài có thể không thấy |
| Object do native/runtime code sinh | Đường khởi tạo đặc thù | Phải xác nhận integration thực tế |

Bảng là **danh sách rủi ro**, không phải kết luận mọi đường này luôn bypass **mọi** mô hình AOP. Nếu bytecode execution của class đã được weave, một instance mới vẫn có thể đi vào advice tại execution tương ứng. **Giới hạn đang phân tích là cơ chế AOP dựa trên proxy reference**.

### `new` không phải “chỉ báo lỗi” tự thân

Việc gọi `new` hoàn toàn hợp lệ trong Java. Nó chỉ gây thiếu advice **nếu object đó đáng ra phải được truy cập qua proxy nhưng lại được dùng trực tiếp như target**. Một object thuần dữ liệu không cần advice vẫn có thể được tạo bằng `new` mà không có vấn đề gì.

## 4. Tách object identity khỏi loại nghiệp vụ

Giả sử có hai reference:

```java
Operations raw = new OperationsImpl();
Operations wrapped = ProxyFactory.wrap(raw);
```

Chúng có thể cùng biểu diễn **một dịch vụ nghiệp vụ** ở tầng API, nhưng **không nhất thiết là cùng object Java**:

- `raw` trỏ tới implementation object.
- `wrapped` trỏ tới proxy object khác, vốn giữ hoặc truy cập `raw`.
- Cả hai có thể cùng implement `Operations`.
- `raw == wrapped` thường là `false` với dynamic proxy dạng wrapper.
- Gọi qua `raw` và gọi qua `wrapped` có thể có advice khác nhau dù target method cuối cùng giống nhau.

**Cùng target nghiệp vụ không đồng nghĩa cùng interception path.** Chính sự tồn tại đồng thời của hai reference này tạo nguy cơ gọi vòng qua proxy.

### Sơ đồ rò reference

```text
               Factory tạo dịch vụ
                      |
                 +----+----+
                 |         |
                raw       proxy ----> raw
                 |         |
             Caller B   Caller A
                 |         |
             no advice  advice
```

Một factory tốt có thể trả về **chỉ proxy qua public API**, giữ raw reference nội bộ để tránh caller sử dụng nhầm. Tuy nhiên, raw vẫn có thể thoát qua một API phụ, callback hoặc getter nếu thiết kế không cẩn thận.

## 5. Ví dụ Java 17+ chạy được: cùng target nhưng hai đường gọi

Ví dụ sau dùng **Java Dynamic Proxy** từ Java SE, không phụ thuộc thư viện AOP. Proxy áp dụng before/after/error advice trên những lời gọi đi qua nó. Chương trình còn chủ động tạo object ngoài factory bằng `new` và reflection để cho thấy các object đó không tự mang interceptor.

Một trường hợp đặc biệt được minh họa: `proxy.outer(...)` **đã đi qua proxy** nhưng bên trong target, `this.process(...)` vẫn **không** quay lại proxy. Đây là giới hạn self-invocation gắn với proxy đứng ngoài target.

### Tệp `UnmanagedProxyDemo.java`

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;

public class UnmanagedProxyDemo {

    interface Operations {
        String process(String value);
        String outer(String value);
    }

    static final class Service implements Operations {
        private final String id;

        Service(String id) {
            this.id = id;
            System.out.println("create " + id);
        }

        @Override
        public String process(String value) {
            System.out.println("target[" + id + "].process " + value);
            if ("fail".equals(value)) {
                throw new IllegalArgumentException("invalid");
            }
            return "OK:" + value;
        }

        @Override
        public String outer(String value) {
            System.out.println("target[" + id + "].outer " + value);
            // Lời gọi nội bộ đi tới this, không quay về proxy.
            return this.process(value + "-inner");
        }
    }

    static final class ProxyFactory {
        private ProxyFactory() { }

        static Operations wrap(Operations target) {
            return (Operations) Proxy.newProxyInstance(
                    Operations.class.getClassLoader(),
                    new Class<?>[] { Operations.class },
                    (proxy, method, arguments) -> {
                        System.out.println(
                                "advice.before " + method.getName());
                        try {
                            Object result = invoke(method, target, arguments);
                            System.out.println(
                                    "advice.after " + method.getName());
                            return result;
                        } catch (Throwable error) {
                            System.out.println(
                                    "advice.error "
                                    + method.getName() + " "
                                    + error.getClass().getSimpleName());
                            throw error;
                        }
                    });
        }

        static Operations create(String id) {
            return wrap(new Service(id));
        }
    }

    static Object invoke(
            Method method, Operations target, Object[] arguments)
            throws Throwable {
        try {
            return method.invoke(target, arguments);
        } catch (InvocationTargetException wrapped) {
            throw wrapped.getCause();
        }
    }

    public static void main(String[] args) throws Exception {

        // Đường được quản lý: factory trả proxy.
        Operations managed = ProxyFactory.create("managed");
        System.out.println("isProxy "
                + Proxy.isProxyClass(managed.getClass()));
        System.out.println("caller "
                + managed.process("A"));

        // Đường không quản lý: new trả raw object.
        Operations raw = new Service("raw");
        System.out.println("caller "
                + raw.process("B"));

        // Lời gọi ngoài đi qua proxy, nhưng lời gọi nội bộ thì không.
        System.out.println("caller "
                + managed.outer("C"));

        // Một instance được tạo ngoài factory bằng reflection.
        Operations reflective = Service.class
                .getDeclaredConstructor(String.class)
                .newInstance("reflective");
        System.out.println("caller "
                + reflective.process("D"));

        // Raw target cũng có thể được wrap sau khi tạo.
        Operations wrappedRaw = ProxyFactory.wrap(raw);
        System.out.println("caller "
                + wrappedRaw.process("E"));

        // Reference gốc vẫn là đường bypass ngay cả sau khi wrap.
        System.out.println("caller "
                + raw.process("F"));

        // So sánh đường báo lỗi qua proxy và đường trực tiếp.
        try {
            managed.process("fail");
        } catch (IllegalArgumentException error) {
            System.out.println("caller managed error "
                    + error.getMessage());
        }

        try {
            raw.process("fail");
        } catch (IllegalArgumentException error) {
            System.out.println("caller raw error "
                    + error.getMessage());
        }
    }
}
```

Chạy với JDK 17 trở lên:

```bash
javac -encoding UTF-8 UnmanagedProxyDemo.java
java UnmanagedProxyDemo
```

**Standard output:**

```text
create managed
isProxy true
advice.before process
target[managed].process A
advice.after process
caller OK:A
create raw
target[raw].process B
caller OK:B
advice.before outer
target[managed].outer C
target[managed].process C-inner
advice.after outer
caller OK:C-inner
create reflective
target[reflective].process D
caller OK:D
advice.before process
target[raw].process E
advice.after process
caller OK:E
target[raw].process F
caller OK:F
advice.before process
target[managed].process fail
advice.error process IllegalArgumentException
caller managed error invalid
target[raw].process fail
caller raw error invalid
```

### 5.1. Tại sao `managed.process("A")` có advice?

`ProxyFactory.create("managed")` tạo `Service` rồi **trả proxy**, không trả reference `Service` gốc. Caller dùng proxy nên handler in `advice.before`, chuyển tiếp bằng reflection đến target và sau khi thành công in `advice.after`.

Phương thức `process` ở target **không cần tự biết advice**. Điều kiện đủ của ví dụ là lời gọi được gửi tới proxy và handler được thiết kế chạy logic cho method tương ứng.

### 5.2. Vì sao `raw.process("B")` không có advice?

`new Service("raw")` trả đối tượng `Service` thực. Caller dùng trực tiếp reference đó; chưa có cơ chế interception nào đi giữa caller và method. Vì vậy chỉ có `target[raw].process B` rồi kết quả caller.

Đây là **thiếu proxy path**, không phải method `process` không tồn tại hay interface thiếu khả năng được proxy.

### 5.3. Vì sao `managed.outer("C")` chỉ có một cặp advice?

Caller gọi `outer` qua proxy nên có `advice.before outer` và `advice.after outer`. Nhưng trong thân `Service.outer`, `this.process("C-inner")` dùng **`this` là target object**, không phải proxy. Vì vậy không có cặp `advice.before process` / `advice.after process` cho lời gọi nội bộ.

Việc target tự gọi method trong cùng class **khác** với client tự tạo một target mới, nhưng cả hai đều minh họa giới hạn quan sát của proxy: **đường gọi bỏ qua boundary**.

### 5.4. Vì sao reflection cũng có thể tạo instance raw?

`Service.class.getDeclaredConstructor(String.class).newInstance("reflective")` gọi constructor để tạo `Service`. Kết quả là raw object, **không tự được wrap** chỉ vì nó được tạo qua reflection.

Reflection còn có những quy tắc về visibility/module access và exception riêng. Demo giữ constructor truy cập được trong cùng compilation unit để tập trung vào semantics của proxy.

### 5.5. Wrap sau khi object đã được tạo có giải quyết không?

`ProxyFactory.wrap(raw)` tạo proxy **trỏ tới cùng raw target đã tồn tại**, vì vậy `wrappedRaw.process("E")` có advice. Nhưng `raw` không biến thành proxy và vẫn có thể được dùng tiếp. `raw.process("F")` không có advice.

**Wrap thành công chỉ tạo thêm một đường có interception**, không tự xóa mọi đường gọi trực tiếp vào instance gốc.

### 5.6. Còn trường hợp target ném ngoại lệ?

Khi caller gọi `managed.process("fail")` qua proxy, handler thấy exception, in `advice.error` rồi truyền lỗi gốc từ `InvocationTargetException.getCause()`. Còn `raw.process("fail")` ném trực tiếp mà không có dòng advice.

Cả hai caller đều bắt được `IllegalArgumentException("invalid")`: **outcome nghiệp vụ giống nhau không chứng minh advice đều đã chạy**. Cần test trực tiếp số lần advice hoặc sự kiện audit/metric, không chỉ return/exception.

### 5.7. Giới hạn của demo

- Dynamic proxy chỉ intercept **method của interface được proxy công bố**.
- Nó không dệt bytecode `Service`.
- Tên/kiểu method trong handler được dùng để minh họa, chưa có pointcut DSL tổng quát.
- Không có cơ chế tự phát hiện/đăng ký mọi instance `Service`.
- Không thể suy rộng hành vi này sang mọi subclass proxy hay bytecode weaving engine.
- `advice.after` trong demo chỉ chạy trên nhánh thành công; nhánh lỗi dùng `advice.error`, không phải after/finally.
- Proxy giữ reference tới target nhưng **không kiểm soát các reference raw khác**.
- Trong ứng dụng thực, không nên thay audit bền vững bằng `System.out.println`.

## 6. Tạo trong một factory có nhất thiết là “managed” không?

Không. Một **factory method** chỉ là hàm tạo/cung cấp object. Nếu factory trả raw target, caller vẫn không qua interception. Ví dụ:

```java
// Minh họa:
static Operations createService() {
    return new Service("raw");
}
```

Ngược lại, một factory trả `ProxyFactory.wrap(new Service(...))` tạo đường đã được can thiệp.

**Không phân loại chỉ bằng cú pháp `new` xuất hiện ở đâu.** Một factory có thể dùng `new` **bên trong**, nhưng trả proxy ra bên ngoài. Vấn đề là **reference được cung cấp cho consumer**, không phải hoàn toàn tránh từ khóa `new`.

### Hai kiểu factory khác nhau

```text
Factory không bảo đảm proxy:
  create() -> new Target()
                  |
               raw target

Factory bảo đảm proxy:
  create() -> new Target() -> wrap(Target)
                                    |
                                   proxy
```

API nên thể hiện contract: `createProxiedService`, `openInterceptedSession` hoặc một cách đặt tên/tài liệu rõ ràng phù hợp dự án. Quan trọng hơn tên là **test rằng mọi đường dùng trong phạm vi chính sách đều nhận reference qua interception boundary**.

## 7. Reference escape: đối tượng raw bị lộ ra ngoài

Một trong những nguyên nhân phổ biến làm mất advice là **raw target escape**. Chẳng hạn:

```java
// Mã giả về thiết kế, không phải chương trình Java hoàn chỉnh.
class ServiceProvider {
    private final Operations raw = new OperationsImpl();
    private final Operations proxy = wrap(raw);

    Operations getService() {
        return proxy;
    }

    Operations getRawForDiagnostics() {
        return raw;  // Mở đường bypass cho bất kỳ caller nào lấy được.
    }
}
```

Nếu client được cấp cả proxy lẫn raw, nó có thể vô tình hoặc cố ý chọn đường không có advice.

**Thiết kế tốt:** hạn chế quyền truy cập vào raw target, chỉ công bố contract đã được can thiệp cho những thao tác nằm trong phạm vi AOP. Tuy nhiên, không nên làm raw target “không thể sử dụng” bằng cách phá thiết kế type hay nhúng check lạ trong mỗi method; cần giải quyết ở **object ownership và wiring**.

### Tham chiếu raw đã được lưu trước khi wrap

```text
t0: target = new Service()
t1: Client A nhận target
t2: proxy = wrap(target)
t3: Client B nhận proxy

A vẫn có raw target từ t1.
B có proxy từ t3.
```

Wrap ở `t2` không tự cập nhật reference trong `Client A`. Java reference thông thường không phải một handle “tự nâng cấp thành proxy” khi có ai đó tạo wrapper mới.

Nếu muốn không có đường bypass, phải giải quyết **từ thời điểm phân phối dependency**, hoặc thay những reference đã phát tán trong phạm vi kiểm soát được.

## 8. Tại sao annotation trên class không tự tạo proxy?

Giả sử method được đánh dấu:

```java
// Khai báo minh họa:
@Audited
void transfer(String accountId);
```

Một annotation có thể cung cấp metadata cho pointcut hoặc advice. Nhưng annotation **không phải một cơ chế khởi tạo object, không tạo proxy, không weave bytecode** chỉ vì nó có mặt trên source.

Để advice chạy qua mô hình proxy, cần một thành phần thực sự:

1. Đọc/nhận diện metadata tương ứng khi phù hợp.
2. Tạo hoặc cung cấp proxy có interceptor.
3. Bảo đảm caller dùng proxy.
4. Chọn và áp dụng advice khi method được gọi.

Khi một đoạn mã vẫn gọi `new TransferService().transfer(...)` trực tiếp, chỉ có annotation trong class không đủ để “can thiệp từ xa”.

### Metadata có thể ở interface hay implementation

Nếu interface method có annotation nhưng implementation method không có, một resolver chỉ đọc annotation trực tiếp trên implementation có thể không thấy nó. Điều này là **vấn đề tìm metadata**, khác với **đường gọi bypass proxy**.

Khi debug, xác minh từng lớp: **đúng reference? đúng method metadata? đúng pointcut? đúng advice?** Không quy mọi triệu chứng thiếu log về một nguyên nhân.

## 9. Cách tổ chức dependency để caller luôn dùng proxy

Một kiến trúc đơn giản:

```text
                   Object composition root
                            |
                   Tạo raw target
                            |
                       Wrap thành proxy
                            |
             +--------------+--------------+
             |                             |
         Consumer A                    Consumer B
             |                             |
             +---------- Proxy ------------+
                            |
                          Target
```

**Composition root** là nơi chương trình tập trung việc tạo và nối các object quan trọng. Khái niệm này không yêu cầu framework. Có thể là `main`, factory của module, bootstrap code hoặc một thành phần riêng.

Các nguyên tắc:

- Consumer khai báo phụ thuộc qua **interface/contract** nếu thuận tiện cho proxy.
- Tập trung nơi tạo/wrap object.
- Không để consumer tự ý `new` lại service mà policy yêu cầu đi qua proxy.
- Không cấp public getter trả raw target trừ khi đó là quyết định kiến trúc có kiểm soát.
- Nếu cần nhiều scope/lifetime, factory phải tạo đúng proxy theo từng scope.
- Test công khai cần gọi **API cung cấp reference đã can thiệp**, không tự tạo raw rồi kết luận advice sai.

### Dependency injection tự viết cũng có thể đúng

```java
// Minh họa, không phải chương trình độc lập.
final class Consumer {
    private final Operations service;

    Consumer(Operations service) {
        this.service = service;
    }

    void run() {
        service.process("job");
    }
}
```

Nếu composition root truyền **proxy**, `Consumer` gọi qua proxy. Nếu truyền raw target, cùng class `Consumer` không có advice. Vì vậy dependency injection là **cách cung cấp reference**, không tự bảo đảm interception trừ khi object graph được cấu hình và kiểm chứng đúng.

## 10. Một instance có thể được wrap nhiều lần không?

Có thể:

```text
target
  ^
  |
proxy A (audit)
  ^
  |
proxy B (tracing)
  ^
  |
caller
```

Ở đây caller gọi qua proxy B, proxy B chuyển sang proxy A, proxy A chuyển sang target. Hai proxy có thể tạo hai lớp interceptor có thứ tự khác nhau.

Nhưng cũng có nguy cơ:

- **Double wrapping** cùng concern gây log/audit trùng.
- Hai proxy cùng giữ state nhưng không thống nhất lifetime.
- Method `equals`, `hashCode`, `toString` được chuyển tiếp khác nhau, làm identity semantics khó hiểu.
- Các phép cast sang concrete implementation không còn hợp lệ với interface proxy.
- Client vô tình trộn reference từ hai phiên bản proxy khác nhau.

**“Object đã có proxy” không tự nghĩa “object được bảo vệ đúng một lần”.** Nên có chính sách ownership rõ về ai được wrap, thứ tự concern và cách ngăn duplicate interception ngoài ý muốn.

## 11. Object identity, `equals` và `getClass`

Một Java dynamic proxy là một object do runtime tạo; nó có thể implement interface giống target, nhưng class thực tế khác. Vì thế:

```java
// Mã ý tưởng:
raw.getClass() == proxy.getClass()  // thường false
raw == proxy                       // false với wrapper proxy khác instance
```

Đừng coi hai reference là cùng object chỉ vì chúng dẫn đến cùng hành vi nghiệp vụ.

Các hệ quả:

- Một client yêu cầu cast sang concrete class có thể không cast được interface proxy.
- Logic dựa vào `getClass()` hoặc reflection có thể thấy proxy class thay vì implementation.
- `equals`/`hashCode` cần semantics rõ nếu proxy và raw target làm khóa map/set.
- Identity-based cache có thể xem raw và proxy là hai khóa khác nhau.
- Annotation trực tiếp trên proxy class không nhất thiết chứa metadata được khai báo trên target.

**Đừng “sửa” bằng cách coi proxy luôn bằng raw**: nếu equality không được thiết kế nhất quán, hash-based collections và so sánh hai phía có thể sai. Với AOP proxy, thường nên cho client phụ thuộc vào **contract nghiệp vụ**, tránh dùng class identity làm phần cốt lõi của logic.

## 12. Chọn kiểu proxy không tự sửa được đường tạo object

**Interface proxy** triển khai contract giao diện và thường giữ target riêng; caller có thể bỏ qua wrapper nếu còn tham chiếu raw. **Subclass proxy** có quan hệ subtype với implementation, nhưng chỉ intercept các method theo khả năng kế thừa, override và cơ chế dispatch cụ thể. Class/method `final`, method `private`, `static`, constructor và module access có giới hạn khác nhau.

Trong bài toán **đối tượng tạo ngoài cơ chế quản lý**, dù chọn kiểu nào vẫn phải hỏi: ai tạo object, ai giữ object gốc, caller nhận reference nào và một instance mới có đi qua cơ chế cung cấp proxy không? Đổi từ interface proxy sang subclass proxy **không tự cập nhật các reference đã phát tán**.

Nếu consumer phụ thuộc trực tiếp vào concrete implementation class, có thể không truyền được một JDK interface proxy thay cho object ấy. Thiết kế theo interface hoặc facade thích hợp giúp quản lý boundary, nhưng ranh giới phải xuất phát từ hợp đồng của ứng dụng, không chỉ để tiện tạo proxy.

## 13. Self-invocation khác unmanaged instance, nhưng cùng dẫn tới bypass

Hai tình huống cần phân biệt:

**A. Unmanaged instance:**

```text
caller -> new Service() -> raw.method()
```

Không có proxy trên đường gọi ngay từ đầu.

**B. Self-invocation qua target:**

```text
caller -> proxy.outer() -> target.outer()
                             |
                             +--> this.inner()
```

Lời gọi **ngoài** đã qua proxy; lời gọi **trong** sử dụng `this` của target. Một proxy dạng **wrapper** thường chỉ thấy `outer`, không thấy `inner`.

Chúng có triệu chứng giống nhau (“advice cho `inner` không chạy”) nhưng cách xử lý khác:

- Unmanaged instance: sửa **đường khởi tạo, wiring và phân phối reference**.
- Self-invocation: cân nhắc **tách component, đi qua boundary có chủ đích, hoặc dùng execution weaving nếu công cụ hỗ trợ**.
- Không tự chèn “tìm proxy toàn cục của chính mình” vào mọi target method nếu điều đó tạo dependency vòng tròn và làm logic khó hiểu.

## 14. Reflection, factory bên thứ ba và plugin

Một chương trình có thể tạo object qua reflection:

```java
// Minh họa:
Class<?> type = Class.forName("com.example.Service");
Object instance = type.getDeclaredConstructor().newInstance();
```

Đây là một đường khởi tạo object thông thường. Nếu không có thành phần wrap kết quả, `instance` vẫn là target object. Tên class được resolve đúng không đồng nghĩa runtime tự đăng ký nó với proxy provider.

Đối với plugin hoặc thư viện:

- Plugin có thể tự tạo object rồi gửi về application host.
- Host có thể wrap ở ranh giới plugin API nếu contract cho phép.
- Plugin có thể giữ raw reference riêng và gọi nội bộ.
- Host không nên kết luận đã intercept toàn bộ plugin chỉ vì những lời gọi từ host đi qua một adapter.
- Nếu plugin reload, object/proxy cũ có thể còn sống và trỏ tới class loader thế hệ trước.

**Host có thể kiểm soát reference mà nó sử dụng, nhưng không mặc nhiên kiểm soát mọi lời gọi do plugin phát sinh nội bộ.** Nếu yêu cầu coverage rộng hơn, cần cơ chế weaving/instrumentation hoặc hook được thiết kế ở đúng boundary.

### Reflection vào proxy và Reflection vào raw

Nếu `Method.invoke` được gọi với receiver là **proxy** cho một interface method phù hợp, invocation có thể đi qua handler của proxy. Nếu receiver là **raw target**, Reflection gọi trực tiếp target method.

Reflection **không phải ngoại lệ toàn cục** khiến AOP luôn bị bỏ qua hay luôn được áp dụng. Quan trọng là object receiver, method được gọi và cách engine định nghĩa điểm can thiệp.

## 15. Serialization, deserialization, copy và clone

Một object được tái tạo từ dữ liệu hoặc copy có thể không đi qua factory ban đầu. Vì vậy:

- Không mặc định deserialization của một target class sẽ trả object đã được wrap.
- Không mặc định serialization của một proxy sẽ bảo toàn handler, target reference, context và các điều kiện tương thích phiên bản.
- Không mặc định clone/copy constructor sẽ giữ cấu trúc proxy.
- Các cơ chế Java serialization, custom serializer, record constructor hay thư viện mapping có **quy tắc khởi tạo khác nhau**; không khẳng định mọi cơ chế đều gọi constructor theo cùng cách.

**Chiến lược an toàn hơn:** tách **dữ liệu** cần lưu/truyền ra khỏi **service object có aspect**, rồi cho service được tạo/cung cấp qua provider chuẩn. Ví dụ lưu `OrderData`, không tìm cách serialize toàn bộ graph gồm proxy, runtime handler và resource.

Nếu domain thật sự cần clone một service object, phải xác định rõ bản sao có cần được intercept không, ai wrap nó và liệu raw references còn tồn tại hay không.

## 16. Executor, callback và tác vụ bất đồng bộ

Đối tượng unmanaged không chỉ xuất hiện trong luồng chính. Một callback hoặc task có thể tự tạo service:

```java
// Mã minh họa, không phải chương trình độc lập.
executor.submit(() -> {
    Operations local = new OperationsImpl();
    local.process("async");
});
```

Ở đây task tạo raw target mới. Nếu hệ thống dùng proxy interception ngoài object này, method có thể bypass advice **dù tác vụ chạy trong cùng JVM**.

Một hướng khác:

```java
// Ý tưởng: sharedService được cung cấp từ proxy provider.
executor.submit(() -> sharedService.process("async"));
```

Nếu `sharedService` trỏ tới proxy, lời gọi vẫn có thể đi qua proxy trong worker. Nhưng **ngữ cảnh gắn với ThreadLocal của caller không tự truyền sang worker**. Cần tách hai vấn đề:

1. **Proxy coverage:** task gọi qua proxy hay raw instance?
2. **Context propagation:** advice trên worker có thấy trace ID, authorization context hoặc deadline cần thiết không?

Có proxy mà thiếu context vẫn có thể làm advice áp dụng chính sách sai; có context đúng nhưng task gọi raw target thì advice proxy vẫn có thể không chạy.

## 17. Scope và lifetime của target/proxy

Một proxy provider có thể quản lý object theo những vòng đời khác nhau:

- **Một instance dùng chung** cho nhiều caller.
- **Một instance mỗi phiên yêu cầu**.
- **Một instance mỗi tác vụ/transaction**.
- **Một instance mỗi lần factory được gọi**.
- **Một instance riêng cho plugin/module layer**.

Với mỗi scope, phải xác định quan hệ:

```text
scope -> proxy instance -> target instance -> owned resources
```

Nếu target được tạo ngoài scope rồi cắm vào proxy, nó có thể giữ state từ một request khác. Nếu proxy được chia sẻ nhưng target mutable không thread-safe, interception không tự làm target thread-safe. Nếu target được dispose nhưng proxy vẫn giữ reference, những lời gọi sau có thể chạm resource đã đóng.

**Quản lý proxy và quản lý lifetime là hai trách nhiệm liên quan nhưng khác nhau.** Một registry cung cấp proxy cần có chính sách tạo/dọn target hợp lý, không chỉ wrap một lần rồi coi mọi object tồn tại mãi mãi.

### Proxy và constructor side effect

Việc wrap một raw target **không chạy ngược constructor** và không hoàn tác những tác dụng phụ đã xảy ra trong constructor. Nếu logic quan trọng chỉ nằm trong advice ở method execution, nó không tự bao phủ hành vi constructor trước thời điểm wrap.

Nếu ứng dụng cần can thiệp vào object construction, phải dùng loại join point/hook tương ứng mà engine hỗ trợ, hoặc thiết kế factory có bước khởi tạo kiểm soát được.

## 18. Interception của method không có nghĩa interception của toàn bộ object

Ngay cả một managed proxy cũng thường chỉ can thiệp vào **một tập method/join point**. Ví dụ:

- Interface proxy nhìn thấy các method trong những interface được proxy implement.
- Các method riêng của implementation không nằm trong interface có thể không được gọi qua interface proxy.
- Static call không được gửi tới một instance proxy.
- Private method không được gọi từ bên ngoài như một public proxy method.
- Direct field access không tự trở thành method invocation qua proxy.
- Constructor/initialization có thể diễn ra **trước** khi proxy được tạo.
- Method final có giới hạn nếu dùng subclass override interception.

Do vậy **“object được quản lý” không có nghĩa “mọi hoạt động bên trong object đều được advice”**. Thiết kế policy phải ghi rõ tập join point được yêu cầu, và cơ chế proxy có thực sự quan sát được chúng không.

### Call join point và execution join point

Một **method call** là vị trí phát lời gọi; một **method execution** là ranh giới thân method bắt đầu chạy. Proxy đứng ngoài target thường là **một ranh giới invocation cụ thể**, không nhất thiết đồng nghĩa công cụ có thể observe mọi call site hoặc execution body trong JVM.

Nếu một engine dệt **execution** vào bytecode target, việc caller tạo target mới ngoài factory chưa chắc làm advice biến mất: method body mới tạo vẫn có thể chứa code đã được weave nếu class tương ứng đã được instrument. Đây là lý do phải nói **giới hạn này thuộc proxy-based AOP**, không khái quát sai cho mọi AOP.

## 19. Proxy bypass và security: phân biệt yêu cầu bắt buộc với quan sát

Nếu concern chỉ là log thông tin không bắt buộc, đường bypass có thể làm mất dữ liệu quan sát. Nếu concern là **kiểm soát truy cập** hoặc **bất biến giao dịch**, đường bypass có thể nguy hiểm hơn.

Ví dụ một hệ thống dựa hoàn toàn vào proxy để kiểm tra quyền trước `transfer(...)`. Nếu caller được phép tạo raw `TransferService` rồi gọi thẳng, lớp kiểm tra có thể bị bỏ qua.

**Chính sách bảo vệ bắt buộc phải có boundary đáng tin cậy không bị bypass bởi các đường thao tác được hỗ trợ.** Có thể dùng AOP để thực thi chính sách khi coverage được bảo đảm và kiểm thử đầy đủ, nhưng không được coi “đã tạo proxy đâu đó” là bằng chứng tất cả các entry point an toàn.

Những biện pháp kiến trúc thường hữu ích:

- Không công bố raw implementation như một API được consumer tự do khởi tạo nếu policy yêu cầu interception.
- Đặt invariant quan trọng ở tầng/thao tác không thể bỏ qua trong phạm vi tin cậy.
- Thiết kế module/API làm giảm các lối gọi trực tiếp ngoài dự kiến.
- Kiểm thử các entry point từ batch, CLI, plugin, test, worker và callback.
- Định nghĩa ứng xử khi proxy provider/instrumentation không khả dụng.
- Không log toàn bộ argument nhạy cảm chỉ vì muốn kiểm tra advice có chạy.

**Đừng sử dụng giới hạn này như một biện pháp “tự cho phép bypass security” trong test/production.** Khi cần bypass để đo hoặc debug, phải hiểu rõ tác động và có quyền kiểm soát.

## 20. Thế nào là “bắt buộc dùng proxy” trong kiến trúc?

Không có câu lệnh Java chung biến mọi instance của một class thành proxy. Ta có thể đưa ra **hợp đồng ở API và cách wiring**:

1. Consumer chỉ phụ thuộc interface hoặc loại trừ khả năng truy cập constructor khi hợp lý.
2. Tất cả object chính thức được cấp qua một provider kiểm soát.
3. Provider trả reference đã được can thiệp, không tiết lộ raw target tùy tiện.
4. Các dependency khác truyền chính reference proxy cho consumer tiếp theo.
5. Factory phụ trợ không tự tạo bản raw “giống hệt” rồi sử dụng cho nghiệp vụ yêu cầu aspect.
6. Integration test phát hiện khi một đường gọi không đi qua interceptor.

Những giải pháp này **giảm rủi ro vô tình bypass**. Tuy vậy, không nhất thiết ngăn được một thành phần có đủ quyền tạo hoặc gọi implementation trực tiếp. Nếu yêu cầu là ranh giới bảo mật chống tác nhân không tin cậy, **kiến trúc type/proxy nội bộ không được thay cho kiểm soát quyền ở boundary bảo mật thật sự**.

### Hạn chế constructor visibility

Làm constructor package-private hoặc private có thể buộc caller sử dụng factory từ những vị trí Java thông thường. Nhưng:

- Không phải mọi API đều cho phép hạn chế constructor như vậy.
- Reflection và module access có quy tắc riêng; không dùng “private” như bảo đảm tuyệt đối chống mọi tác nhân có đặc quyền.
- Một số serializer hoặc runtime infrastructure cần cơ chế xây dựng object khác.
- Hạn chế construction không tự tạo advice; factory vẫn phải trả đúng reference proxy.

Nên dùng visibility để hỗ trợ hợp đồng API, không coi đó là tất cả bảo đảm coverage.

## 21. Kiểm tra một reference có phải proxy hay không

Đối với Java Dynamic Proxy, có thể kiểm tra:

```java
boolean dynamicProxy =
        java.lang.reflect.Proxy.isProxyClass(value.getClass());
```

Nhưng đây chỉ là kiểm tra **đối tượng có class được tạo bằng cơ chế Java Dynamic Proxy hay không**. Nó **không chứng minh**:

- Handler có áp dụng advice mong muốn.
- Pointcut có chọn method cụ thể.
- Proxy có wrap đúng target/version.
- Mọi lời gọi nghiệp vụ đều dùng object đó.
- Cơ chế subclass proxy hoặc bytecode weaving có được bao phủ hay không.
- Proxy có đáp ứng policy bảo mật hoặc audit hay không.

**Không kiểm tra AOP bằng `Proxy.isProxyClass` duy nhất.** Cách chắc hơn là **test hành vi advice trên đường gọi thật**, so sánh số lần target thực thi và số lần concern được ghi nhận.

### Unwrap để debug có thể tạo bypass mới

Một số provider cho phép lấy raw target để chẩn đoán. Chức năng đó có ích nhưng cần kiểm soát. Nếu caller lấy target rồi cất nó vào field, những lời gọi sau có thể bypass proxy ngay cả khi provider được cấu hình chính xác.

Khi debug, nên ưu tiên công cụ quan sát metadata/handler hay diagnostics mà **không công bố reference raw rộng rãi**.

## 22. Xử lý ngoại lệ và return value qua hai đường

Đối với cùng một target method, proxy có thể:

- Ghi log trước khi chuyển tiếp.
- Đo thời gian.
- Biến đổi argument ở ranh giới proceed nếu API hỗ trợ.
- Quan sát kết quả và exception.
- Trả fallback hoặc retry nếu around advice cho phép.

Raw target gọi trực tiếp sẽ **không có những lớp biến đổi đó**.

Do đó, bypass không chỉ là thiếu log. Nó có thể khiến **giá trị caller nhận khác**, **lỗi được truyền khác** hoặc **target chạy số lần khác**.

Ví dụ, nếu proxy áp dụng retry 2 lần còn raw method không retry, cùng một hành vi thất bại tạm thời có thể tạo outcome khác. Nhưng phải nhớ retry có side effect và yêu cầu idempotency. Vì thế:

**Đừng “sửa” tình trạng thiếu proxy bằng cách thêm call advice thủ công vào target một cách không nhất quán.** Hoặc thiết kế một abstraction có contract rõ, hoặc chuyển sang cơ chế weaving/instrumentation khác khi thực sự cần coverage execution rộng hơn.

## 23. Transaction, resource scope và đối tượng unmanaged

Một số concern AOP dùng scope quanh một invocation, ví dụ mở một đơn vị công việc, tạo context, hoặc dọn tài nguyên. Nếu target unmanaged được gọi trực tiếp:

- Before advice không chạy để tạo scope.
- Around advice không bao quanh method.
- After/finally advice không chạy để cleanup.
- Caller có thể nhận behavior khác, kể cả resource thiếu được chuẩn bị.

Tuy vậy, **transaction không tự tồn tại chỉ nhờ proxy**. Các API/resource thật phải có contract và quản lý độc lập. Một phương thức tự quản lý tài nguyên đúng vẫn có thể chạy hợp lệ không có proxy nếu nó được thiết kế như vậy.

Quan trọng là **tránh kỳ vọng ẩn** rằng mọi execution sẽ đi qua một proxy, trong khi hệ thống cho phép tạo raw instance ngoài cơ chế quản lý.

## 24. Test thường che khuất lỗi unmanaged instance thế nào?

Một unit test có thể viết:

```java
// Đoạn test ý tưởng.
Operations service = new Service("test");
assertEquals("OK:A", service.process("A"));
```

Test này xác nhận **business logic của raw target**, nhưng **không xác nhận proxy advice**. Nếu concern cần audit, một integration test riêng phải tạo service qua provider chính thức rồi assert sự kiện audit.

Ngược lại, nếu test chỉ dùng mock/proxy mà không kiểm tra target behavior, có thể bỏ qua bug trong implementation.

### Ba lớp kiểm thử

**Unit test raw target:** kiểm logic method độc lập, chủ động không xem đây là bằng chứng advice hoạt động.

**Integration test proxy:** tạo service qua đúng provider/entry point, assert số lần interceptor chạy, target chạy, kết quả/ngoại lệ đúng.

**Architecture/coverage test:** xác minh những consumer quan trọng **không tạo raw target ngoài composition root**, factory không rò target, plugin/batch/async có đường đi phù hợp. Có thể kết hợp code review, rule kiểm tra cấu trúc và test runtime.

### Ma trận đường gọi

| Đường gọi | Proxy wrapper có thể thấy? | Điều cần test |
| --- | --- | --- |
| Consumer gọi reference provider trả về | Có, nếu provider trả đúng proxy | Advice và target chạy theo contract |
| Consumer tự `new` target | Không, nếu không có hook khác | Nhận diện bypass |
| Consumer gọi raw lấy từ getter | Không | Kiểm tra leak reference |
| Consumer gọi proxy cho một raw đã tồn tại | Có trên **đường proxy** | Raw reference cũ vẫn bypass |
| Target tự gọi `this.inner()` | Thường bypass với wrapper proxy | Method inner có cần coverage không? |
| Callback giữ proxy | Có trên lời gọi callback dùng proxy | Context propagation và lifecycle |
| Callback tự tạo raw | Không | Wiring ở task factory |
| Reflection gọi method trên proxy | Có nếu method/cách invoke phù hợp | Tách receiver proxy và target |
| Reflection gọi method trên raw | Không | Không nhầm reflection với AOP |
| Plugin tạo riêng target | Có thể không | Boundary giữa host và plugin |
| Bytecode execution đã weave | Có thể, kể cả raw instance | Phân biệt với cơ chế proxy |

Bảng cố ý dùng “có thể” ở những trường hợp phụ thuộc engine. Muốn có kết luận sản xuất, phải chạy test với implementation thực tế.

## 25. Chẩn đoán khi advice không chạy

Hãy kiểm tra theo thứ tự để tránh sửa nhầm:

### Bước 1 — Có đúng instance không?

Caller đang giữ reference nào? `System.identityHashCode` có thể hỗ trợ theo dõi identity trong debug, nhưng không biến nó thành ID ổn định hay bằng chứng bảo mật. Có thể in tên runtime class hoặc kiểm tra wrapper ở đường dẫn cụ thể khi cần.

### Bước 2 — Reference ấy có qua proxy không?

Kiểm tra cách object được tạo: `new`, static factory, registry, reflection, deserialization hay callback? Có code nào lấy raw target từ một nơi khác không?

### Bước 3 — Provider có thật sự wrap không?

Một config có thể chỉ tạo raw khi thiếu điều kiện. Đừng suy đoán factory tên `createManaged` luôn trả proxy; xem contract và runtime test.

### Bước 4 — Method có nằm trong tập interceptor hỗ trợ không?

Interface proxy chỉ nhìn thấy method của interface được proxied. Với subclass proxy, final/private/static có ràng buộc khác. Không tự áp dụng một kết luận cho mọi cơ chế.

### Bước 5 — Pointcut có match không?

Kiểu, tên method, chữ ký, overload, annotation ở interface/implementation, context và dynamic argument đều có thể ảnh hưởng.

### Bước 6 — Có self-invocation hay direct-call nào không?

Từ client có đi qua proxy, nhưng bên trong target có `this.otherMethod()` hoặc lấy một raw reference khác không?

### Bước 7 — Advice có chạy nhưng không tạo log không?

Một guard trong advice, cờ cấu hình, sampling hoặc sink lỗi có thể khiến không thấy stdout. Phân biệt **advice entered**, **predicate true** và **event exported**.

### Bước 8 — Có nhiều proxy hoặc nhiều target không?

Tham chiếu giữa cache, singleton/per-request instance, class loader/plugin generation có thể trộn object cũ và mới. Kiểm tra ownership/lifecycle, không chỉ method name.

### Bước 9 — Có async hoặc module boundary không?

Worker có dùng đúng proxy không? Trace context có được truyền không? Caller/target ở các module/process khác nhau có chung interception boundary không?

### Bước 10 — Có weaving bytecode song song không?

Nếu execution đã được weave, lời gọi raw có thể vẫn chạy advice ở method body. Chẩn đoán dựa trên **cơ chế thực tế** thay vì gán mọi thiếu log cho proxy.

## 26. Chọn giải pháp phù hợp với mục tiêu coverage

**Giải pháp 1 — Tập trung tạo và phân phối proxy.** Phù hợp khi mọi consumer thuộc phạm vi tin cậy và có thể kiểm soát wiring. Thường đơn giản, rõ ràng, ít phụ thuộc vào bytecode manipulation.

**Giải pháp 2 — Thiết kế boundary API không bị consumer bỏ qua.** Cung cấp facade/service interface qua module public, giữ implementation internals không phải API public. Hữu ích để quản lý object lifecycle và giảm leak reference.

**Giải pháp 3 — Dùng hook/interceptor ngay tại boundary bắt buộc.** Ví dụ một pipeline xử lý lệnh mà mọi tác vụ đều phải đi qua. Phù hợp khi có một điểm kiểm soát thực sự.

**Giải pháp 4 — Dệt execution bytecode khi phạm vi yêu cầu rộng hơn proxy.** Có thể phù hợp nếu cần quan sát các instance do nhiều bên tạo, self-invocation hoặc private execution (khi công cụ hỗ trợ). Đòi hỏi kiểm chứng weaving scope, class loading, module access và artifact deployment.

Không có phương án nào đúng cho mọi trường hợp. **Chọn theo join point cần bao phủ**, giới hạn ngôn ngữ/runtime và yêu cầu audit/bảo mật thực tế.

## 27. So sánh proxy với bytecode weaving khi object unmanaged

| Câu hỏi | Proxy bên ngoài target | Dệt bytecode vào execution của target |
| --- | --- | --- |
| Caller tự `new Target()` rồi gọi method | Thường bypass | Có thể vẫn chạy advice nếu class được weave và pointcut khớp |
| Caller dùng provider trả proxy | Có thể chạy advice | Có thể chạy advice ở execution, ngoài interceptor nếu cả hai cùng có |
| `this.inner()` trong target | Wrapper proxy thường không quan sát | Có thể áp dụng ở inner execution nếu hỗ trợ |
| Target class có cần biến đổi bytecode không? | Không nhất thiết | Có |
| Coverage có dựa vào reference caller dùng không? | Rất nhiều | Có thể ít hơn đối với execution đã weave |
| Có hỗ trợ mọi private/static/final method không? | Không | Phụ thuộc loại join point và weaver |
| Có cần quản lý class loading/artifact không? | Chủ yếu là quản lý proxy/lifetime | Có, tùy compile/load/post-compile weaving |
| Có tự mang ThreadLocal qua async không? | Không | Cũng không |
| Có tự bảo đảm mọi đường chính sách bắt buộc không? | Không | Cũng không nếu weaving scope thiếu |

**Không đồng nhất “weave trong class” với “mọi thứ đều được chặn”.** Bytecode weaving vẫn cần pointcut đúng, class thuộc scope, helper nạp được và runtime dùng bản đã weave.

## 28. Các lỗi phổ biến

1. **“Method được gắn annotation thì mọi `new` đều có advice.”** Annotation không tự tạo proxy.
2. **“Đã tạo một proxy thì raw target cũng biến thành proxy.”** Proxy là reference/object khác.
3. **“Factory luôn trả proxy.”** Chỉ khi factory thực sự wrap.
4. **“Đăng ký object vào một map là nó được quản lý AOP.”** Registry có thể giữ raw instance.
5. **“Thay mọi `new` bằng static factory là đủ.”** Factory không wrap vẫn bypass.
6. **“Caller có interface là tự có proxy.”** Interface chỉ là contract; object runtime có thể là raw.
7. **“`Proxy.isProxyClass` chứng minh advice chạy.”** Nó không xác nhận pointcut/handler behavior.
8. **“Một lời gọi ngoài đã qua proxy thì mọi lời gọi nội bộ cũng qua proxy.”** Wrapper proxy không tự nhận self-invocation.
9. **“Không có log nghĩa là instance unmanaged.”** Có thể pointcut không khớp hoặc sink bị tắt.
10. **“Reflection luôn bypass AOP.”** Method được invoke trên receiver proxy có thể qua handler.
11. **“Serialization luôn giữ proxy.”** Phụ thuộc cơ chế và contract; không suy luận.
12. **“Proxy quanh instance làm các raw reference cũ không còn hợp lệ.”** Chúng vẫn có thể gọi trực tiếp.
13. **“Một proxy chung làm target mutable thread-safe.”** Không tự có bảo đảm đồng bộ.
14. **“Proxy bao mọi phương thức của object.”** Tập method phụ thuộc interface/subclass/hook.
15. **“Subclass proxy có cùng self-invocation semantics với interface wrapper proxy.”** Còn phụ thuộc implementation.
16. **“Dệt bytecode cũng phải quản lý từng instance proxy.”** Execution weaving có thể áp dụng theo class bytes.
17. **“Test business logic raw đủ chứng minh audit.”** Cần integration/coverage test.
18. **“Có advice là security invariant tự an toàn.”** Phải bảo đảm mọi đường bắt buộc được kiểm soát.
19. **“Raw instance trong task tự nhận context của caller.”** Cả proxy reference lẫn context cần được xem riêng.
20. **“Một module chứa aspect là mọi module đều nhận advice.”** Đường gọi và weaving scope mới quyết định.

## 29. Bài tập thực hành

1. Chạy `UnmanagedProxyDemo.java`. Đếm số lần in `advice.before` và `target[...].process`; giải thích vì sao không bằng nhau.
2. Xóa dòng `ProxyFactory.wrap(raw)` nhưng giữ các lời gọi đến `raw`; đầu ra nào mất và vì sao?
3. Đổi `managed.outer("C")` thành `raw.outer("C")`. So sánh advice trên `outer` và `process` bên trong.
4. Tạo một factory `createRaw` trả `new Service(...)`, sau đó gọi qua factory đó. Vì sao gọi “factory” không bảo đảm proxy?
5. Đổi `ProxyFactory.create(...)` để trả raw reference thay vì proxy. Viết test phát hiện thay đổi contract.
6. Tạo một `Consumer` nhận `Operations` qua constructor. Truyền proxy trong một test và raw trong test khác; so sánh log.
7. Tạo hai proxy nối tiếp trên cùng raw target. So sánh thứ tự before/after của hai handler và số lần target được gọi.
8. Thử ép interface proxy về concrete `Service`. Vì sao `ClassCastException` có thể xảy ra dù service implements `Operations`?
9. Bổ sung một method chỉ có trên implementation, không có trên interface. Java dynamic proxy có cho gọi method ấy qua `Operations` không?
10. Thêm một `ExecutorService`, gửi hai task: task thứ nhất giữ proxy, task thứ hai tự `new` raw. So sánh số lần advice và giải thích vấn đề ThreadLocal riêng biệt.
11. Dùng Reflection gọi method interface trên `proxy` rồi trên `raw`. Receiver khác nhau có ảnh hưởng interception ra sao?
12. Thêm method `outer` gọi `this.process("fail")`, rồi so sánh dòng `advice.error` cho `outer` và `process`.
13. Thiết kế một composition root chỉ trả proxy ra ngoài. Nêu mọi API có thể vô tình làm rò raw target.
14. Tạo một class test `AuditRecorder` đếm advice. Kiểm các đường new, factory, reflection, wrapping, self-invocation, callback.
15. So sánh bằng sơ đồ: proxy interface vs execution bytecode weaving cho trường hợp khách hàng tự tạo instance target.
16. Đề xuất cách bảo vệ một invariant bắt buộc khi ứng dụng có entry point qua CLI, HTTP handler, background job và plugin.
17. Phân loại ba tình huống “advice không chạy” thành **unmanaged instance**, **pointcut mismatch**, **advice đã chạy nhưng logging bị tắt**; đề xuất bằng chứng runtime cho từng loại.

**Tự kiểm tra:** Vì sao `raw == proxy` thường false? Nếu factory wrap một target đã được tạo trước đó, các reference raw cũ có tự đi qua proxy không? Lời gọi `this.inner()` có quay ra wrapper proxy không? Annotation trên method có tự đăng ký instance vào provider không? Với bytecode execution weaving, tạo đối tượng bằng `new` có luôn khiến advice biến mất không? Một unit test trực tiếp target có chứng minh concern audit được áp dụng không?

## Kết luận

Trong **AOP qua proxy**, đối tượng được tạo ngoài cơ chế quản lý proxy có thể **không nhận advice**, không phải vì điểm can thiệp sai, mà vì **caller đang giữ và gọi một raw target reference**. Việc tạo proxy sau đó không tự chuyển đổi những reference đã phát tán; self-invocation trong target cũng có thể bypass wrapper. Để áp dụng AOP nhất quán, cần quản lý **composition root, factory, registry, object lifetime và phân phối reference**, kiểm tra cả đường `new`, reflection, plugin, callback, serialization và lời gọi nội bộ, rồi test trên cơ chế interception thật. Khi yêu cầu vượt ngoài phạm vi proxy, có thể cân nhắc bytecode weaving hoặc boundary khác được hỗ trợ, nhưng vẫn phải xác minh **join point, phạm vi dệt và đường thực thi** thay vì mặc định mọi object trong hệ thống đã được bảo vệ.
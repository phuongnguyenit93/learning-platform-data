# Phân biệt cắt ngang hành vi với cắt ngang cấu trúc

## 1. Vấn đề: aspect có thể tác động lên **cách code chạy** hoặc **hình dạng kiểu**

**Aspect-Oriented Programming (AOP)** tổ chức các mối quan tâm cắt ngang (cross-cutting concerns) tách khỏi mã nghiệp vụ chính. Khi học AOP, nhiều người chỉ hình dung một aspect ghi log trước và sau method. Đó là **cắt ngang hành vi (behavioral crosscutting)**: bổ sung việc xảy ra **trong quá trình thực thi**. Tuy nhiên, một số mô hình AOP còn cho phép **cắt ngang cấu trúc (structural crosscutting)**: biểu đạt hoặc bổ sung quan hệ kiểu, interface, thành viên, ràng buộc khai báo hoặc metadata của chương trình.

Hai khái niệm khác nhau ở **đối tượng chịu thay đổi**:

- **Cắt ngang hành vi:** can thiệp *khi một join point xảy ra* — thực hiện before/after/around, quan sát exception, quyết định gọi tiếp, biến đổi result hoặc áp đặt chính sách cho lời gọi.
- **Cắt ngang cấu trúc:** can thiệp vào *những gì một type/module biểu hiện* — chẳng hạn một type có thêm interface, một hợp đồng thành viên được giới thiệu, hoặc một quan hệ khai báo được áp dụng cho nhiều class mà không phải chỉnh sửa thủ công từng class.

Ví dụ khái niệm:

~~~text
                      AOP crosscutting
                       /             \
                      /               \
          BEHAVIORAL                     STRUCTURAL
         "Khi run() chạy?"              "Type này có thể có gì?"
           |                                  |
   before / after / around           interface / method / field
   logging, timing, policy           type relationship / declaration
           |                                  |
   Thay đổi luồng thực thi           Thay đổi cấu trúc hoặc contract
   của join point được chọn          mà công cụ cho phép bổ sung
~~~

**Không có bảo đảm rằng mọi AOP engine hỗ trợ cả hai dạng.** Một implementation chỉ dùng dynamic proxy có thể can thiệp vào các lời gọi đi qua proxy và tạo wrapper hiện thực thêm interface, nhưng **không biến đổi cấu trúc của class target gốc**. Ngược lại, một hệ thống weaving có hỗ trợ *inter-type declarations* có thể thêm hành vi thành viên hoặc quan hệ kiểu ở mức class đã dệt; chi tiết phụ thuộc thời điểm weaving, khả năng công cụ và ràng buộc JVM.

Bài này học **Aspect/AOP tổng quát**: cách phân biệt, tình huống sử dụng, giới hạn công nghệ, ví dụ Java 17, kiểm thử, rủi ro tương thích và thiết kế bảo trì.

## 2. Nền tảng: join point, pointcut và advice là phía hành vi

**Join point** là một điểm/sự kiện chương trình được mô hình AOP hỗ trợ, ví dụ method call hoặc method execution. **Pointcut** là quy tắc chọn các join point. **Advice** là hành vi được thực hiện tại những điểm được chọn.

Ví dụ về ý định hành vi:

~~~text
Khi execution của AccountService.transfer(...) xảy ra:
  BEFORE: bắt đầu trace
  AROUND: đo duration, gọi hoạt động gốc
  AFTER RETURNING: ghi outcome thành công
  AFTER THROWING: ghi thông tin lỗi thích hợp
  FINALLY: giải phóng context
~~~

Những hành vi này có thể thay đổi **runtime semantics**: số lần target thực thi, thứ tự side effects, kết quả và exception. Một cache around advice có thể không gọi target; một retry around advice có thể gọi target nhiều lần. Vì vậy “cắt ngang hành vi” không chỉ là “thêm log” — nó có thể điều khiển cả **luồng thực thi**.

Tuy nhiên, ngay cả khi advice biến đổi result `"ok"` thành `"[ok]"`, sự thay đổi đó **không tự chứng minh class của target có thêm public method hay interface**. Đó vẫn là một can thiệp vào behavior của invocation.

### 2.1. Tại sao khái niệm "join point" không đủ mô tả cấu trúc?

Một method có thể **không bao giờ được gọi** trong một lần chạy mà class vẫn có một interface hoặc field khai báo. Đặc tính cấu trúc được xem xét ở mức type definition, compilation, class loading hoặc reflection. Nó không chỉ tồn tại trong khoảng thời gian một invocation đang active.

Do đó, không mô tả introduction bằng câu “advice before chạy lúc object được tạo”, trừ khi một cơ chế cụ thể có lifecycle như vậy. **Mở rộng hợp đồng kiểu** và **khởi chạy code khi constructor thực thi** là hai vấn đề khác nhau.

## 3. So sánh trực tiếp hai dạng cắt ngang

| Tiêu chí | Cắt ngang hành vi | Cắt ngang cấu trúc |
| --- | --- | --- |
| Câu hỏi trung tâm | Khi join point xảy ra, ta làm gì? | Type/module có những member hoặc quan hệ nào? |
| Đối tượng thay đổi | Execution, call, event, outcome | Type shape, interface membership, declarations |
| Khái niệm điển hình | Pointcut, before/after/around advice | Introduction, inter-type declaration, type relationship |
| Thời điểm có hiệu lực | Khi lời gọi/event được can thiệp | Tùy công cụ: build/weave/load/proxy creation |
| Có cần target thực thi để quan sát? | Thường cần một join point thực sự xảy ra | Không nhất thiết: reflection/type checking có thể thấy khi class/proxy tồn tại |
| Ví dụ | Đo duration cho mọi `pay()` | Làm một nhóm types đáp ứng interface `Auditable` |
| Có thêm method vào class gốc? | Không phải mục tiêu định nghĩa | Có thể nếu engine thực sự hỗ trợ structural weaving |
| Có thể đổi giá trị trả về? | Có, nhất là around advice nếu API cho phép | Một introduction method cũng có body riêng, nhưng ý chính là thêm contract |
| Compiler thấy API mới? | Thường không có API mới để thấy | Tùy thời điểm weaving, compiler/plugin và kiểu tĩnh tham chiếu |
| Reflection trên target gốc đổi không? | Thường không do interceptor đơn thuần | Phụ thuộc structural weaving; proxy wrapper không làm target gốc đổi |
| Rủi ro chính | Thứ tự advice, side effects, exceptions, performance | Collisions, binary compatibility, type identity, initialization, tooling |

**Một giải pháp có thể kết hợp cả hai.** Ví dụ, một introduction cho type `Auditable` bổ sung phương thức `auditId()`, rồi một behavioral advice ghi audit mỗi khi method `save()` được gọi. Introduction định nghĩa **khả năng mới của type**; advice định nghĩa **khi nào khả năng đó được sử dụng**.

## 4. Behavioral crosscutting: điểm mạnh và phạm vi

Các concern thường phù hợp với behavioral advice:

- Ghi log, đo latency, tracing, audit theo invocation.
- Kiểm tra quyền hoặc quota tại method boundary.
- Retry có kiểm soát hoặc fallback với các operation idempotent.
- Caching khi kết quả phụ thuộc input và policy.
- Validation đầu vào, chuẩn hóa result theo hợp đồng.
- Quan sát exception hoặc đóng scope.
- Mở hoặc đóng tài nguyên theo invocation, nếu ownership rõ.

Ví dụ pseudo-API tổng quát:

~~~java
// Pseudocode: Proceed và Metrics do hệ thống cung cấp.
Object around(Proceed next, Metrics metrics) throws Throwable {
    long started = System.nanoTime();
    try {
        return next.proceed();
    } finally {
        metrics.observe(System.nanoTime() - started);
    }
}
~~~

Đây là **minh họa không độc lập**, không phải API phổ quát của mọi engine. Nó cho thấy “cắt ngang hành vi” xoay quanh một lần `proceed()` tại join point.

### 4.1. Hành vi không đồng nghĩa không có trạng thái

Behavioral aspect có thể dùng fields, counters, context objects và cả external resources. Nó có thể **làm thay đổi state runtime** hoặc side effects nghiệp vụ. Điều phân biệt với structural crosscutting không phải “có state hay không”, mà là **có thêm thành viên/hợp đồng vào type hay chỉ xử lý invocation theo contract đã có**.

Một field nội bộ của handler dùng để đếm số lời gọi **không tự biến thành field mới của target class**. Nếu reflection trên target gốc vẫn không có field đó, đừng gọi nó là “structural introduction vào target”.

### 4.2. Hành vi vẫn có thể làm sai hợp đồng

Advice có thể ném exception sau khi target đã commit, retry gây side effects trùng, hoặc thay result. Cần test:

- Giá trị caller nhìn thấy.
- Ngoại lệ gốc và causal chain.
- Số lần target chạy.
- Thứ tự và số lượng side effects.
- Những join points không được chọn.
- Concurrent requests/async completion.

**Không vì “chỉ thêm advice” mà coi tính đúng đắn của chương trình là bất biến.**

## 5. Structural crosscutting: introduction và inter-type declaration

Trong những mô hình AOP có hỗ trợ **structural crosscutting**, một aspect có thể mô tả rằng các type đã có thêm khả năng hay khai báo ở mức cấu trúc.

Những loại tính năng thường được gọi là **introductions** hoặc **inter-type declarations**:

1. **Giới thiệu interface/type relationship:** một tập classes được khai báo đáp ứng một contract mới.
2. **Giới thiệu method:** thêm member method với signature/implementation được xác định.
3. **Giới thiệu field/property:** thêm trạng thái có lifecycle và visibility phù hợp.
4. **Giới thiệu constructor hoặc member khác:** tùy đúng khả năng của công cụ và ngôn ngữ.
5. **Thay đổi kiểu cha hoặc quan hệ khai báo:** có thể có công cụ hỗ trợ, nhưng thường chịu giới hạn nghiêm ngặt về type hierarchy.
6. **Áp quy tắc khai báo/checking:** ví dụ quy tắc lỗi/cảnh báo cho những quan hệ thiết kế không hợp lệ; đây là đặc tính declarative có thể đi cùng mô hình AOP.

**Đây là danh sách khả năng theo mô hình, không phải lời khẳng định mọi tool đều thêm được từng loại thành viên.** Trong Java, type hierarchy, final classes, interface compatibility, access rules, visibility, classloader và verifier đều ảnh hưởng tính khả thi.

### 5.1. Ví dụ khái niệm một introduction

Một codebase có nhiều đối tượng:

~~~text
Order
Invoice
Shipment
~~~

Ứng dụng muốn chúng có thể cung cấp cùng contract:

~~~java
interface Trackable {
    String trackingId();
}
~~~

Đây chỉ là **declaration Java** để minh họa hợp đồng.

Một structural weaving tool có thể cho phép diễn đạt ở cấp aspect:

~~~text
INTRODUCE: Order, Invoice, Shipment IMPLEMENT Trackable
INTRODUCE METHOD trackingId(): return a type-specific identifier
~~~

Hai dòng trên là **pseudocode AOP**, không phải cú pháp Java hay cú pháp bảo đảm của bất kỳ engine cụ thể nào. Nếu công cụ hỗ trợ và weaving đúng, các types đã được dệt có thể đáp ứng contract mới.

**Một behavioral advice đo `trackingId()` khi nó được gọi là chuyện khác.** Nó không tự làm ba classes có thêm method.

### 5.2. Introduction có thể có body nhưng vẫn là cấu trúc

Khi introduction thêm một method `trackingId()` có implementation, method ấy tất nhiên có hành vi khi được gọi. Nhưng tính năng **giới thiệu method vào contract của type** được xếp vào structural crosscutting, trong khi việc advice chạy trước/sau execution của method đó thuộc behavioral crosscutting.

Hai trục có thể giao nhau mà không đồng nhất.

## 6. Một ví dụ đối chiếu đơn giản

Giả sử trước can thiệp:

~~~java
interface Operation {
    String process(String input);
}
~~~

Có hai yêu cầu:

**Yêu cầu A — hành vi:** mọi invocation `process()` qua một đường can thiệp phải ghi `before` và `after`, nhưng caller vẫn dùng `Operation`.

**Yêu cầu B — cấu trúc:** một object quan sát được cần có thêm contract `Tagged` với method `tag()`.

~~~java
interface Tagged {
    String tag();
}
~~~

Các kết quả có thể:

~~~text
BEHAVIORAL WRAPPER:
  Operation proxy -> intercept process(input)
  -> CoreOperation vẫn chỉ implements Operation

STRUCTURAL-LIKE WRAPPER INTRODUCTION:
  Proxy object implements Operation + Tagged
  -> caller có thể cast proxy sang Tagged
  -> CoreOperation gốc vẫn KHÔNG implements Tagged

TRUE TARGET-CLASS INTRODUCTION (chỉ nếu engine hỗ trợ):
  Woven CoreOperation implements Operation + Tagged
  -> cấu trúc class đã dệt có thể thay đổi
  -> cần điều kiện weaving, type-checking và binary compatibility
~~~

**Bẫy quan trọng:** proxy implementing additional interface **không chứng minh target class có thêm interface**. Nó đổi **type của wrapper**, không đổi type của object đang được wrapper bao.

## 7. Java 17 chạy được: so sánh advice hành vi và interface trên wrapper

Chương trình sau dùng **JDK dynamic proxy**. Mục đích của nó là kiểm thử:

- Một proxy `Operation` ghi trước/sau `process` nhưng **không bổ sung contract `Tagged`**.
- Một proxy khác triển khai **hai interfaces `Operation` và `Tagged`**, cho phép gọi `tag()` trên proxy.
- Type `CoreOperation` gốc vẫn **không implements `Tagged`** trước và sau khi tạo cả hai proxies.
- Hai lượt gọi `process` đi đến cùng core và tăng `calls` đúng hai lần.
- Reflection/runtime type checks phân biệt thành viên trên wrapper với thành viên trên target.

**Điểm giới hạn:** ví dụ không dùng một structural weaver và không giới thiệu method vào bytecode của `CoreOperation`. Đây là mô phỏng bằng **adapter/proxy**, đủ để học sự khác biệt giữa **behavior at invocation boundary** và **new interface contract exposed by another object**. Một engine inter-type declaration thật có semantics riêng phải kiểm bằng integration test trên woven class.

Tạo file `AspectStructureDemo.java`:

~~~java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;

public final class AspectStructureDemo {
    interface Operation { String process(String input); }
    interface Tagged { String tag(); }

    static final class CoreOperation implements Operation {
        int calls;
        public String process(String input) {
            calls++;
            System.out.println("CORE process " + input);
            return "ok:" + input;
        }
    }

    static Object invoke(Object target, Method method, Object[] args) throws Throwable {
        try { return method.invoke(target, args); }
        catch (InvocationTargetException error) { throw error.getCause(); }
    }

    static Operation addBehavior(Operation target) {
        return (Operation) Proxy.newProxyInstance(
                Operation.class.getClassLoader(), new Class<?>[]{Operation.class},
                (proxy, method, args) -> {
                    if (method.getDeclaringClass() == Object.class)
                        return invoke(target, method, args);
                    System.out.println("BEHAVIOR before " + args[0]);
                    Object value = invoke(target, method, args);
                    System.out.println("BEHAVIOR after " + value);
                    return value;
                });
    }

    static Object addProxyInterface(Operation target, String assignedTag) {
        return Proxy.newProxyInstance(
                Operation.class.getClassLoader(),
                new Class<?>[]{Operation.class, Tagged.class},
                (proxy, method, args) -> {
                    if (method.getDeclaringClass() == Tagged.class)
                        return assignedTag;
                    if (method.getDeclaringClass() == Object.class)
                        return invoke(target, method, args);
                    System.out.println("INTRO_PROXY before " + args[0]);
                    Object value = invoke(target, method, args);
                    System.out.println("INTRO_PROXY after " + value);
                    return value;
                });
    }

    static void check(boolean condition) {
        if (!condition) throw new AssertionError("assertion failed");
    }

    public static void main(String[] args) {
        CoreOperation core = new CoreOperation();
        Operation behavior = addBehavior(core);
        check(core instanceof Operation);
        check(!Tagged.class.isInstance(core));
        check(!(behavior instanceof Tagged));
        System.out.println("CORE Operation=true Tagged=false");
        System.out.println("BEHAVIOR proxy Tagged=false");
        System.out.println("RESULT behavior=" + behavior.process("A"));

        Object introduced = addProxyInterface(core, "region:eu");
        check(introduced instanceof Operation);
        check(introduced instanceof Tagged);
        check(!Tagged.class.isAssignableFrom(CoreOperation.class));
        System.out.println("INTRO_PROXY Tagged=true");
        System.out.println("INTRO tag=" + ((Tagged) introduced).tag());
        System.out.println("RESULT introduced="
                + ((Operation) introduced).process("B"));

        check(!Tagged.class.isInstance(core));
        check(core.calls == 2);
        System.out.println("CORE after Tagged=false");
        System.out.println("CORE calls=" + core.calls);
        System.out.println("ALL ASSERTIONS PASSED");
    }
}
~~~

Biên dịch và chạy (JDK 17 trở lên):

~~~bash
javac --release 17 -encoding UTF-8 AspectStructureDemo.java
java AspectStructureDemo
~~~

Đầu ra **đã được xác minh bằng biên dịch/chạy thực**:

~~~text
CORE Operation=true Tagged=false
BEHAVIOR proxy Tagged=false
BEHAVIOR before A
CORE process A
BEHAVIOR after ok:A
RESULT behavior=ok:A
INTRO_PROXY Tagged=true
INTRO tag=region:eu
INTRO_PROXY before B
CORE process B
INTRO_PROXY after ok:B
RESULT introduced=ok:B
CORE after Tagged=false
CORE calls=2
ALL ASSERTIONS PASSED
~~~

### 7.1. Tại sao `behavior instanceof Tagged` là false?

`addBehavior()` tạo proxy chỉ với `new Class<?>[]{Operation.class}`. Invocation handler biết thêm before/after cho `process`, nhưng không có interface mới được đăng ký. Caller có thể dùng nó như `Operation`; không thể dùng như `Tagged`.

**Logic trước/sau là behavioral crosscutting ở ranh giới proxy**, không phải structural modification của target.

### 7.2. Tại sao `introduced instanceof Tagged` là true?

`addProxyInterface()` tạo proxy với **hai interfaces**: `Operation` và `Tagged`. JVM tạo một proxy object hiện thực cả hai, handler cung cấp kết quả khi method `tag` được gọi.

Do đó cast `(Tagged)introduced` hợp lệ. Đây là **mở rộng contract của proxy object**. Tuy nhiên `CoreOperation` ban đầu không hề implements `Tagged`, vì vậy `Tagged.class.isAssignableFrom(CoreOperation.class)` vẫn false.

### 7.3. Tại sao phải kiểm riêng proxy và target?

Hai objects có thể triển khai hai contracts khác nhau:

~~~text
introduced: proxy class implements Operation, Tagged
core:       CoreOperation implements Operation only
~~~

Một test chỉ kiểm `introduced instanceof Tagged` có thể tạo **ảo giác class gốc được weave**. Ta cần kiểm `CoreOperation.class` riêng để biết chính xác đâu là ranh giới cấu trúc.

### 7.4. Hai lượt `process` có làm thay đổi class không?

Không. `CoreOperation.calls` bằng 2 chỉ chứng minh hai lần target thực thi; việc invocation handler ghi before/after không khiến `CoreOperation` nhận thêm public method hoặc interface. Đó là thay đổi **hành vi trên đường gọi proxy**.

### 7.5. Vì sao dùng `Tagged.class.isInstance(core)` thay vì `core instanceof Tagged`?

`CoreOperation` trong ví dụ là một class **`final`** đã biết chắc không implement `Tagged`. Với compile-time type `CoreOperation` cụ thể ấy, biểu thức `core instanceof Tagged` bị Java compiler từ chối vì không có khả năng chuyển đổi kiểu. `Tagged.class.isInstance(core)` là runtime reflective check trả false, tiện để demo điều kiện này mà chương trình vẫn biên dịch.

Điểm này cũng cho thấy **type compatibility là một hợp đồng compile-time**, không chỉ một chuỗi log runtime.

### 7.6. Giới hạn kỹ thuật khác của JDK dynamic proxy

- Nó được tạo để hiện thực **interfaces**, không sửa classfile `CoreOperation`.
- Lời gọi qua **raw target** sẽ bỏ qua behavior của proxy.
- Nó không tự can thiệp vào field access, private methods, constructors hay toàn bộ self-invocation.
- Caller giữ biến tĩnh kiểu `Operation` không thể gọi `tag()` trực tiếp nếu không cast sang `Tagged` hoặc dùng API trả đúng type.
- Proxy method dispatch, Object methods, checked exceptions và method name collisions cần được xử lý theo hợp đồng khi triển khai đầy đủ.
- Handler ở demo chỉ phục vụ `process`, `tag` và những `Object` methods được chuyển tiếp; nó không phải một interception framework tổng quát.

## 8. Introduction thực sự ở mức class khác adapter wrapper như thế nào?

### 8.1. Adapter/composition (wrapper)

~~~text
Caller -> Wrapper implements NewInterface
             |
             +-> delegates to OriginalTarget
OriginalTarget class unchanged
~~~

Caller chỉ thấy new contract **khi có wrapper instance đúng loại**. Nếu một thành phần giữ original target reference, nó không thấy interface bổ sung. Hai references có thể chỉ vào hai objects khác nhau, làm ảnh hưởng identity, `equals`, serialization và lifecycle.

### 8.2. Structural weaving vào class

~~~text
Source definition: OriginalTarget
          |
          +-- Weaving / transformation (nếu engine hỗ trợ)
          |
Woven class: OriginalTarget + introduced relationship/member
          |
New instances / type reflection on woven artifact
~~~

Nếu weaving thêm interface/member vào bytecode của **chính class được load**, những instance của **woven class** có thể hiện thực contract mới, không cần một wrapper riêng. Nhưng khả năng đó phụ thuộc bytecode verifier, classloader, thứ tự load và thời điểm transformation.

Không khẳng định mọi structural introduction đều xuất hiện như một method Java public thường trong mọi kiểu inspection. Có mô hình xây proxy contract, có mô hình thay đổi class, có mô hình chỉ thêm declaration trong compiler. Phải chỉ ra **công nghệ nào** và **điểm quan sát nào** đang nói đến.

### 8.3. Hành vi có thể được thêm qua code weaving mà không phải structural introduction

Một weaver có thể chèn instructions before/after vào thân method đã có, **không thêm một public interface mới**. Đây vẫn là thay đổi runtime behavior của method, dù class bytes bị biến đổi về mặt vật lý.

Do vậy:

> **“Bytecode bị thay đổi” không tự đồng nghĩa “structural crosscutting”.**

Tiêu chí là **contract/type shape và loại biến đổi có thể quan sát**, không chỉ việc bytes được patch.

## 9. Compile-time type checking và khả năng gọi member mới

Nếu một introduction làm một class có thêm method `tag()`, liệu source code khác có gọi `obj.tag()` được không? Câu trả lời không chỉ phụ thuộc JVM runtime mà còn **compiler đã thấy type bổ sung ở thời điểm compile hay chưa**.

Ba trường hợp:

1. **Source compile với structural information:** compiler/extension có thể biết introduction và cho phép compile lời gọi theo contract mới.
2. **Source compile trước introduction:** compiler Java thông thường chỉ thấy type declaration trước khi weave, có thể không chấp nhận `obj.tag()`.
3. **Proxy object với interface mới:** nếu API trả kiểu `Tagged` hoặc caller cast runtime thành `Tagged`, source compile theo contract của interface đó; `CoreOperation` gốc vẫn không có method.

Một quy trình build dùng weaving có thể yêu cầu **compiler/IDE hỗ trợ phù hợp**, generated sources/stubs, hoặc dependency ordering. Đừng viết code rồi mong javac tự hiểu một method dự kiến được thêm bởi một bước xử lý xảy ra sau javac.

### 9.1. Một ví dụ compile-time không hợp lệ cần nhận diện

~~~java
final class Core {}

// Không thể tự mặc định:
Core core = new Core();
// core.tag(); // javac không biết tag() nếu class không khai báo nó.
~~~

Đây là **đoạn minh họa**, không phải standalone demo hoàn chỉnh. Với code Java thông thường, `Core` không có member `tag()`. Nếu một công cụ external transformation về sau thêm method, caller được biên dịch trước đó vẫn cần có một **hợp đồng compile-time rõ ràng** hoặc gọi qua reflection/dynamic interface phù hợp.

### 9.2. Binary compatibility

Thay đổi type hierarchy hoặc thêm interface có thể ảnh hưởng:

- Method resolution và overload selection.
- Serialization metadata và reflective frameworks.
- Casting, `instanceof`, generic bounds.
- Conflicting default methods của interfaces.
- Return type/throws contract của method được giới thiệu.
- Những thư viện đã compile dựa trên class shape cũ.
- Access control giữa package/module/classloader.
- Incremental builds hoặc cached woven artifacts.

Không thể coi introduction chỉ là “thêm một method nhỏ”: nó có thể trở thành **thay đổi công khai về API** của nhiều types.

## 10. Thời điểm weaving và trạng thái class đang được nạp

Structural transformation phải phù hợp với lifecycle của class trong JVM:

~~~text
Source files / binaries
       |
       +-> Compile-time / post-compile weaving
       |
       +-> Load-time transformation (trước class definition)
       |
       v
JVM defines class + verifier checks
       |
       v
Runtime type identity and instances
~~~

**Weaving trước khi JVM định nghĩa class** thường có không gian biến đổi cấu trúc rộng hơn hot replacement của class đã được định nghĩa. Trong Java thông thường, **class redefinition/retransformation của JVM instrumentation API bị giới hạn với những thay đổi schema**, không thể mặc định thêm/bớt fields/methods, đổi signature hay inheritance sau khi class đã load. Khả năng công cụ mở rộng hoặc cơ chế JVM đặc biệt nếu có phải được xem xét riêng, không suy ra từ ngôn ngữ AOP tổng quát.

### 10.1. Classloading và class initialization khác nhau

- **Class definition/loading:** JVM tiếp nhận và định nghĩa type.
- **Class initialization:** chạy initialization logic theo quy tắc JVM vào những thời điểm sử dụng thích hợp.
- **Aspect instantiation:** tạo object chứa advice/state nếu mô hình cần.
- **Advice invocation:** thực thi hành vi tại join point.

Cắt ngang cấu trúc vào lúc load **không nhất thiết** gọi constructor của aspect, cũng không có nghĩa advice đã được kích hoạt. Đừng trộn bốn mốc này.

### 10.2. Nhiều classloaders

Class identity trong JVM được phân biệt bằng binary name và defining classloader. Một công cụ weaving chỉ áp dụng trong một loader có thể làm hai phiên bản “cùng tên” có class shapes khác nhau giữa các loader.

Với plugin/module runtime, kiểm đúng loader là điều thiết yếu. Một `ClassCastException` giữa hai types cùng tên có thể đến từ classloader mismatch, không nhất thiết do introduction viết sai.

## 11. Khả năng structural introduction và những giới hạn Java

Một engine có thể hỗ trợ một số phép thay đổi nhưng không phải tất cả. Cần cân nhắc:

### 11.1. `final` class hoặc `final` method

Một Java class `final` không thể có subclass Java thông thường. Điều đó ảnh hưởng subclass-proxy và một số cơ chế mixin. Nhưng không tự kết luận “một class final không thể được bytecode-transform bởi mọi cơ chế”: khả năng thực còn phụ thuộc loại thay đổi, verifier và công cụ.

Một `final` method không override được theo quy tắc Java, nhưng một weaver có thể thực hiện insertion bên trong method body đã tồn tại nếu engine và runtime cho phép. **Override** khác **bytecode weaving**.

### 11.2. Private members

Một JDK interface proxy không thêm private method vào target. Một structural weaver có thể có các quy tắc riêng cho introduced private members, nhưng không được ngụ ý mọi member mới có cùng access như method public. Module/access checks vẫn có hiệu lực.

### 11.3. Interface method conflicts

Giả sử class đã có method `tag()` với chữ ký/return không tương thích hoặc hai interfaces đưa ra default methods xung đột. Introduction không thể lờ đi contract của Java language và JVM verification. Cần xác định quy tắc precedence, conflict resolution hoặc từ chối transformation.

### 11.4. Tên field và state

Giới thiệu field vào nhiều objects tạo câu hỏi:

- Field có scope **per-instance** hay static?
- Giá trị mặc định, initialization, visibility là gì?
- Thứ tự initialization tương quan constructor và weaving ra sao?
- Thread safety nếu advice truy cập state mới từ nhiều threads?
- Serialization/copy/deserialization xử lý field mới thế nào?
- Reflection hay một ORM có hiểu field đó không?

Một field trên **wrapper** không phải field trên **target**, dù hai objects có thể chia sẻ reference.

### 11.5. Visibility và module boundary

Với Java modules, package access, exported/open packages, reflection và classloader có thể hạn chế khả năng thao tác. Không cố “cứ thêm interface” mà bỏ qua yêu cầu access và legal type relationships.

## 12. Phân biệt structural AOP với các kỹ thuật OOP quen thuộc

Không phải mọi hành động “thêm hành vi chung” đều là structural AOP.

| Kỹ thuật | Cách hoạt động | Tính chất cần phân biệt |
| --- | --- | --- |
| **Interface + implements trong source** | Tác giả sửa type trực tiếp | Cấu trúc đổi nhưng không nhất thiết dùng aspect |
| **Inheritance** | Subclass nhận/override members | Thay class hierarchy theo OOP thông thường |
| **Decorator / adapter** | Wrapper delegate sang object khác | Wrapper có contract khác target |
| **Dynamic proxy** | Object proxy hiện thực interfaces và dispatch invocation | Can thiệp lời gọi qua proxy; không sửa target class |
| **Mixin/trait composition** | Tổ hợp behaviors/contracts theo ngôn ngữ/công cụ | Có thể là static composition, không tự đồng nghĩa AOP |
| **Bytecode advice weaving** | Thêm hành vi vào một số join points | Có thể không thêm API mới |
| **Structural introduction/weaving** | Bổ sung declarations/type relationship theo capability engine | Thay contract type của artifact được dệt |
| **Source generator** | Sinh code/class/interface trước compile | Có thể tạo cấu trúc mới mà không dùng AOP |
| **Reflection/dynamic dispatch** | Gọi members tồn tại hoặc dispatch theo runtime | Không tự tạo member mới trong original class |

**Structural crosscutting là về mục đích modular hóa những thay đổi cấu trúc theo concern**, không đơn thuần là có code được sinh hoặc một adapter được tạo.

### 12.1. Khi nào adapter đủ thay cho introduction?

Nếu chỉ một subsystem cần `Tagged` trên một service instance, wrapper/adapter có thể đơn giản, tường minh và dễ test hơn thay đổi class thật. Nếu rất nhiều types trong cả codebase cần một contract chung ở cả compile time và reflection, structural introduction có thể giảm lặp lại — **nếu toolchain chịu được việc contract bị dệt**.

### 12.2. Không nhầm “mixin” với subclassing tự do

Một mixin có thể được hiện thực bằng delegation, generated subclass hoặc structural weaving. Mỗi phương án có type identity và lifecycle riêng. Muốn giải thích chính xác, phải nói **đối tượng nào** thêm interface và **đối tượng nào** giữ state.

## 13. Kết hợp behavioral và structural crosscutting đúng cách

Một kịch bản phối hợp:

~~~text
STRUCTURAL CONCERN:
  Nhóm domain objects đáp ứng Auditable
  Có contract auditId(): String

BEHAVIORAL CONCERN:
  Mỗi lần operation save() thực thi thành công
  ghi event dùng auditId() của object
~~~

Ưu điểm:

- Contract `Auditable` nói lên khả năng **một type có thể cung cấp gì**.
- Advice nói rõ **lúc nào audit phải xảy ra**.
- Không cần nhét logic audit vào tất cả method nghiệp vụ.

Nhưng vẫn cần kiểm:

1. `Auditable` được giới thiệu vào **đúng type** chưa?
2. Advice có can thiệp vào đúng `save` join point chưa?
3. Nếu object không có contract ở runtime, việc advice cast có lỗi không?
4. Khi `save()` thất bại sau partial commit, event phải mang trạng thái gì?
5. Nếu cache/short-circuit bỏ qua target, audit theo request hay target execution?
6. Nếu có hai aspects cùng introduce cùng tên method, precedence/collision xử lý ra sao?
7. State của introduced member có thread-safe và lifecycle đúng không?

**Không dùng việc “đã thêm Auditable” làm bằng chứng mọi thao tác save đều được audit.** Contract và runtime interception là hai bài test độc lập.

## 14. Pointcut matching không phải một structural declaration

Một pointcut theo method signature, annotation hoặc enclosing type có thể nhận diện nhiều join points, nhưng **việc chọn join point không bổ sung member vào class**.

Ví dụ ý niệm:

~~~text
SELECT Q = execution of all service methods matching a signature
RUN advice before Q
~~~

Đây là behavioral selection. Dù Q match hàng nghìn methods và module hóa concern rất tốt, type shapes không phải đã được biến đổi bởi chính rule Q.

Ngược lại:

~~~text
DECLARE all matching classes implement Trackable
INTRODUCE trackingId() implementation
~~~

Đây là structural intent. Nó không yêu cầu một method execution đã xảy ra để mô tả contract.

### 14.1. “Pointcut theo cấu trúc” là cụm dễ gây nhầm

Một pointcut có thể match dựa trên **cấu trúc tĩnh** (method/annotation/type) nhưng tác động của nó vẫn là **behavioral advice**. “Static matching criterion” không đồng nghĩa “structural crosscutting”.

Hãy hỏi rõ:

> Rule đang **chọn điểm thực thi để chạy advice**, hay **thay đổi khai báo/type relationship**?

Đây là phép phân biệt hữu ích nhất.

## 15. Crosscutting structure có ảnh hưởng runtime behavior không?

Có. Một introduced interface có thể:

- Thay điều kiện `instanceof` và đường dispatch.
- Khiến reflection nhìn thấy một method/member mới.
- Mở một overload/adapter path khác.
- Tạo state mới cần initialization và concurrent protection.
- Được một library khác phát hiện rồi kích hoạt workflow mới.

Vì vậy “structural” không có nghĩa “không ảnh hưởng hành vi”. Nó nghĩa **điểm tác động chủ đích là contract/hình dạng type**, sau đó runtime behavior có thể thay đổi như hệ quả.

Ngược lại, behavioral advice có thể được dệt bằng cách chèn instructions vào bytecode — bytes vật lý của class thay đổi — nhưng không nhất thiết thêm public API. **Phân loại theo semantics, không theo thao tác công cụ trên file bytes.**

## 16. Interface introduction: thiết kế API cẩn thận

Nếu thêm một interface vào nhiều types, tránh đặt contract quá lớn. Ví dụ `Auditable` có 15 methods vừa về security, logging, lifecycle và database sẽ buộc nhiều objects phải đáp ứng những trách nhiệm không đồng nhất.

Hướng tốt:

- Chỉ giới thiệu một contract có **ý nghĩa miền rõ ràng**.
- Ưu tiên interface nhỏ, không buộc target expose internals.
- Không giới thiệu mutators nếu concern chỉ cần read-only identity.
- Định nghĩa type-safe return values và failure semantics.
- Xác định có state per-instance không và ai sở hữu.
- Tránh đặt tên member dễ collision với target hiện có.
- Bảo toàn contract của interface trên tất cả types được chọn.
- Không làm lộ dữ liệu nhạy cảm qua method mới hoặc reflective access.
- Viết tài liệu type visibility: thấy từ compiler, reflection, wrapper hay woven class?

Nếu introduction có ý nghĩa công khai lâu dài, cần versioning và compatibility strategy như một API bình thường.

## 17. Rủi ro khi áp một structural aspect trên diện rộng

Một advice match nhiều methods có thể tạo overhead runtime; một structural introduction match nhiều classes có thể tác động **compile/runtime compatibility trên diện rộng**, kể cả những type không trực tiếp gọi method mới.

Một số hệ quả:

- **Name collision:** nhiều types có method trùng signature nhưng semantic khác.
- **Conflicting implementations:** hai introductions cung cấp cùng method.
- **Type ambiguity:** một overload mới được chọn khác sau compile.
- **Serialization change:** object graph khác khi thêm state.
- **Reflective behavior:** tool khám phá methods/annotations có thể chọn thêm thành viên.
- **ORM mapping:** một ORM có thể đọc field/property mới theo convention, gây mapping ngoài ý định.
- **Classloader identity:** woven và raw versions cùng tên nhưng từ loaders khác nhau.
- **Incremental build drift:** module này thấy intro, module khác dùng raw dependency.
- **Security surface:** interface mới mở capabilities trên một object vốn chỉ lộ API hẹp.
- **Rollback difficulty:** khôi phục code cũ có thể không giải được persisted data/schema đã tạo bởi contract mới.

**Đừng dùng structural introduction chỉ để tránh sửa một dòng khai báo interface**, nếu chi phí tooling và compatibility lớn hơn lợi ích modular hóa.

## 18. Runtime reflection: phải quan sát đúng đối tượng

Để kiểm tra có một contract mới, cần phân biệt:

1. **Type của target gốc** (`CoreOperation.class`).
2. **Class của proxy/wrapper** (`proxy.getClass()`).
3. **Type của class đã được weave** sau transformation.
4. **Type tĩnh mà code caller được compile dựa vào**.

Kết quả các kiểm tra có thể khác nhau.

Bảng đọc ví dụ Java:

| Đối tượng/kiểu | `Operation`? | `Tagged`? | Ý nghĩa |
| --- | --- | --- | --- |
| `CoreOperation` raw | Có | Không | Source class gốc |
| `behavior` proxy | Có | Không | Behavioral invocation interceptor |
| `introduced` proxy | Có | Có | Wrapper hiện thực thêm interface |
| `CoreOperation.class` sau tạo proxy | Có | Không | Tạo wrapper không sửa target class |

Một `instanceof` trên proxy không đủ để kết luận class gốc đã biến đổi. Một `getDeclaredMethods()` trên class gốc cũng không đủ để nói wrapper không có capability, vì đó là **hai objects/types khác nhau**.

### 18.1. Kiểm phương thức mới qua `getMethods()` hay `getDeclaredMethods()`?

- `getMethods()` thường trả public methods có thể truy cập theo quy tắc reflection, gồm inherited public methods.
- `getDeclaredMethods()` chỉ trả methods khai báo trực tiếp bởi class đó, bất kể visibility, không gồm inherited ones.

Nếu một method đến từ interface hoặc được giới thiệu theo kỹ thuật đặc biệt, vị trí quan sát có thể khác. Trước khi assert, cần biết contract reflection cụ thể của sản phẩm weaving/proxy.

## 19. Tests nên tách thành hai nhóm và một nhóm phối hợp

### 19.1. Behavior tests

| Test | Kỳ vọng |
| --- | --- |
| Join point match | Advice chạy tại đúng call/execution |
| Join point không match | Không có advice event |
| Normal return | Result bảo toàn hoặc transform đúng hợp đồng |
| Target throws | Lỗi gốc được ném lại hoặc chuyển đổi có chủ đích |
| Around short-circuit | Target không chạy nếu policy cho phép |
| Retry | Số lần target chạy đúng |
| Concurrency | Per-invocation state không bị ghi đè |
| Proxy bypass | Test đường gọi raw target và self-invocation |
| Async completion | Không nhầm method return với task completion |
| Performance | Latency/overhead phù hợp workload |

### 19.2. Structural tests

| Test | Kỳ vọng |
| --- | --- |
| Target được giới thiệu đúng type | Type thực sự có interface/member cần thiết |
| Target không được chọn | Không thêm interface/member ngoài ý định |
| Member signature | Name, parameters, return type, access đúng |
| Conflict detection | Collision bị từ chối hoặc giải quyết theo policy rõ |
| State initialization | Introduced fields/behavior có lifecycle đúng |
| Reflection | Reflection nhìn thấy contract theo khả năng engine |
| Compile-time use | Downstream sources compile theo API đã được expose |
| Binary compatibility | Client binaries tương thích theo contract |
| Serialization | Schema/serialVersion và backward compatibility được xét |
| Multiple classloaders | Đúng defining classloader và woven artifact |
| Incremental build | Không chạy nhầm raw/woven outputs |
| Unweave/redeploy | Không rò state/metadata/cached class assumptions |

### 19.3. Composition/integration tests

Khi structural `Auditable` và behavioral audit advice phối hợp:

1. Khởi tạo object qua **artifact thật** (proxy/weaver đúng).
2. Khẳng định object cung cấp `auditId()` qua contract cần dùng.
3. Gọi method nghiệp vụ được chọn và assert advice chạy đúng số lần.
4. Xác minh advice đọc đúng `auditId()` và ghi đúng event.
5. Gọi một method không được chọn và assert không bị audit nhầm.
6. Ép target throw để kiểm exception/audit policy.
7. Kiểm short-circuit, retry, async nếu có.
8. Kiểm raw target/direct calls khi dùng proxy.
9. Kiểm không có type được thêm không mong muốn.
10. Test trên chính classloader/build artifact sẽ release.

Một **unit test trực tiếp gọi hàm handler** không đủ chứng minh weaving hay introduction thực tế có hiệu lực.

## 20. Khi nào lựa chọn behavioral, structural hay mô hình khác?

### Chọn behavioral advice khi

- Mục tiêu là theo dõi/thay đổi **thời điểm thực thi**.
- Không cần thêm type contract mới.
- Caller API nên giữ nguyên.
- Concern liên quan logging, metrics, authorization tại boundary rõ.
- Có thể giải quyết bằng interceptor/proxy hoặc code weaving với phạm vi kiểm soát được.

### Cân nhắc structural introduction khi

- Nhiều types độc lập cần cùng một **interface/member contract** có ý nghĩa rõ.
- Đã có engine hỗ trợ đúng loại introduction, build/compiler tích hợp tốt.
- Cần contract xuất hiện ở **type level**, không chỉ wrapper riêng.
- Có kế hoạch xử lý collisions, versioning, reflection, serialization và classloaders.
- Mục tiêu modular hóa cấu trúc mang lợi ích đủ lớn so với chi phí tooling.

### Cân nhắc adapter, decorator hoặc sửa source trực tiếp khi

- Chỉ vài types cần mở rộng.
- Contract mới chỉ cần tại một API boundary.
- Tooling structural weaving làm type checking khó dự đoán.
- Cần type behavior tường minh, dễ IDE navigation và debugging.
- Module có public API ổn định không nên bị thay đổi ngầm.
- Cần wrapper per-instance mà không muốn rewrite class gốc.

**Không có quy tắc “structural AOP luôn hiện đại hơn”**. Giá trị của nó tùy nhu cầu và khả năng vận hành an toàn.

## 21. Những nhầm lẫn phổ biến

1. **“Aspect nào cũng chỉ có advice.”** Không nhất thiết; một số mô hình hỗ trợ introductions.
2. **“Thêm logging là structural vì bytecode thay đổi.”** Phân loại theo contract: logging là behavioral.
3. **“Behavioral advice không có state.”** Có thể có state/counters; không vì thế thành structural introduction.
4. **“Proxy mới implements Tagged thì CoreOperation cũng implements Tagged.”** Sai: hai objects có types khác nhau.
5. **“`instanceof` trên wrapper chứng minh target đã được weave.”** Không.
6. **“Giới thiệu method nghĩa chỉ chèn before advice.”** Không: thêm declaration/member là khác với interception.
7. **“Điều kiện pointcut dựa trên class là structural crosscutting.”** Không: đó có thể là static matching cho behavioral advice.
8. **“Structural introduction tự chạy mỗi khi method bị gọi.”** Type contract không phải một advice invocation.
9. **“Runtime classloader thấy method mới thì compiler mọi module tự biết.”** Không nếu compilation không có thông tin intro.
10. **“Cứ hot reload là thêm field/interface mới được.”** Java redefinition thường có giới hạn schema.
11. **“`final` method không bao giờ bị woven behavior.”** Override và bytecode instrumentation là hai cơ chế khác nhau.
12. **“Một intro interface không có breaking changes.”** Nó có thể ảnh hưởng overloads, reflection, serialization.
13. **“Structural weaving và adapter luôn tương đương.”** Không: object identity/type contract và coverage khác.
14. **“Aspect instantiation xảy ra ở lúc weave.”** Không có quy tắc chung.
15. **“Một class name xác định duy nhất type trong JVM.”** Còn defining classloader.
16. **“Method được thêm ở wrapper cũng thuộc original class reflection.”** Không.
17. **“Giới thiệu field không ảnh hưởng concurrency.”** Introduced state vẫn cần thread safety nếu dùng chung.
18. **“Mọi bytecode weaving tool hỗ trợ inter-type declarations.”** Không.
19. **“Behavioral và structural không thể kết hợp.”** Chúng có thể bổ sung cho nhau.
20. **“Có Auditable contract nghĩa mọi save đã được audit.”** Cần behavioral interception riêng.
21. **“Test mỗi advice đủ chứng minh structural member tồn tại.”** Không; cần type/reflective/build tests.
22. **“Chỉ cần test proxy, không cần test raw target.”** Khi phân biệt introduction, cả hai cực kỳ quan trọng.
23. **“Mọi structural declaration đều visible như Java source member.”** Phụ thuộc engine/build/classloader.
24. **“Cứ thêm interface là auto an toàn.”** Contract có thể mở capability trái policy.
25. **“Mọi class loader đều thấy cùng woven class.”** Không nếu instrumentation scope khác.
26. **“Structural introduction thay cả database schema.”** Không tự động; đây là type/program structure, không phải migration dữ liệu.
27. **“Một method `tag()` được gọi tức là aspect đang hoạt động.”** Có thể chỉ là method thường của proxy/target; phải phân biệt.
28. **“Thay đổi type contract không cần versioning.”** Đặc biệt nguy hiểm với public APIs.

## 22. Câu hỏi tự kiểm tra

**Câu 1.** Advice ghi `before/after` cho `process()` có phải structural crosscutting không?  
**Đáp án:** Không; đó là behavioral crosscutting tại join point.

**Câu 2.** Một introduction khiến nhiều classes implements `Trackable` thuộc dạng nào?  
**Đáp án:** Structural crosscutting, nếu nó thật sự thay type contract của classes được chọn.

**Câu 3.** `Operation` proxy cũng implements `Tagged` thì `CoreOperation` gốc có tự implements `Tagged` không?  
**Đáp án:** Không. Proxy và core có runtime classes riêng.

**Câu 4.** Bytecode được instrument before/after làm class file khác đi; có tự là structural AOP không?  
**Đáp án:** Không. Việc sửa instructions để can thiệp hành vi không nhất thiết thêm member/type relationship.

**Câu 5.** Có thể dùng chỉ tên method signature để quyết định advice chạy; đó là structural pointcut hay behavioral?  
**Đáp án:** Matching có thể dựa trên đặc tính tĩnh, nhưng nếu kết quả chỉ chọn join point để chạy advice thì tác động là behavioral.

**Câu 6.** Vì sao compiler có thể từ chối `core.tag()` dù tool dự kiến weave `tag()` về sau?  
**Đáp án:** Compiler không có contract method ở thời điểm compile; cần tooling/type information hoặc gọi qua interface/API đã biết.

**Câu 7.** `Tagged.class.isInstance(core)` trả false trong ví dụ vì sao?  
**Đáp án:** Class `CoreOperation` gốc không implements `Tagged`; proxy introduction không sửa target.

**Câu 8.** Một structural introduction tạo field mutable per-object, có phải nghĩ đến thread safety không?  
**Đáp án:** Có; nếu nhiều threads truy cập cùng instance/state, vẫn có race như field thông thường.

**Câu 9.** `final` class có thể được subclass proxy bình thường không?  
**Đáp án:** Không; nhưng giới hạn đó không tự mô tả mọi kiểu bytecode weaving.

**Câu 10.** Structural introduction có thể ảnh hưởng overload resolution không?  
**Đáp án:** Có, nếu compile-time type/member set thay đổi; cần kiểm compilation compatibility.

**Câu 11.** Chỉ test `getMethods()` trên proxy có chứng minh woven target type đã đổi không?  
**Đáp án:** Không. Cần test woven target class hoặc loại artifact đang được giới thiệu.

**Câu 12.** Khi nào một wrapper/adapter có thể phù hợp hơn introduction?  
**Đáp án:** Khi chỉ cần interface mới trên một object boundary và muốn tránh thay type gốc/toolchain phức tạp.

**Câu 13.** Một aspect giới thiệu `Auditable` và advice thực hiện audit khi `save()` thành công. Cần mấy nhóm test?  
**Đáp án:** Test structural contract, behavioral join points, và integration test sự phối hợp.

**Câu 14.** Load-time transformation có nghĩa mọi aspect instance đã được tạo ở class load không?  
**Đáp án:** Không. Class transformation, class initialization, aspect instantiation và advice invocation là các mốc khác nhau.

## 23. Checklist thiết kế và QA

### Trước khi chọn cơ chế

- [ ] Mục tiêu là can thiệp **invocation** hay thêm **type contract**?
- [ ] Thêm interface cho **wrapper** có đủ hay phải bổ sung vào **woven target class**?
- [ ] Source/compiler/caller cần nhìn thấy API mới tại thời điểm nào?
- [ ] Engine thực tế hỗ trợ đúng loại introduction nào?
- [ ] Điểm matching có đủ hẹp, không mở rộng thay đổi ngoài ý định?
- [ ] Cần thay đổi type thật hay decorator/composition rõ ràng đã đủ?

### Khi triển khai

- [ ] Xác định runtime type và classloader thực tế của target và proxy.
- [ ] Tránh name/signature collisions và conflicting interface defaults.
- [ ] Xử lý member visibility, module access và method dispatch.
- [ ] Định nghĩa state initialization, lifecycle và thread safety của introduced members.
- [ ] Định nghĩa pointcut/advice precedence riêng cho behavioral logic.
- [ ] Kiểm thử raw target path và self-invocation nếu dùng proxy.
- [ ] Tài liệu hóa public API/versioning của contract mới.
- [ ] Không giả định class đã định nghĩa có thể hot-redefine schema tự do.

### Khi kiểm thử/phát hành

- [ ] Unit test behavior before/after/around và exception path.
- [ ] Test interface membership đúng **đối tượng/kiểu**.
- [ ] Test member signature và reflective visibility.
- [ ] Test classes không được chọn không bị thêm member.
- [ ] Test build/compile consumers trước và sau introduction theo contract.
- [ ] Test correct woven artifact hoặc proxy factory ở môi trường phát hành.
- [ ] Kiểm type identity ở nhiều classloaders khi ứng dụng có plugins.
- [ ] Kiểm serialization/ORM discovery nếu dựa trên reflection.
- [ ] Test quan hệ structural + behavioral bằng workflow end-to-end.
- [ ] Quan sát hiệu năng runtime và tác động tương thích của structural changes.

## 24. Tổng kết

**Cắt ngang hành vi** mô tả **điều gì xảy ra khi join point thực thi**: before, after, around, tracing, policy, retry, caching, result và exception handling. **Cắt ngang cấu trúc** mô tả **type/module có thể mang thêm những khai báo hoặc quan hệ nào**: interface, member hoặc loại introduction khác mà engine thực sự hỗ trợ.

Sự phân biệt không nằm ở việc có sửa bytecode hay không, vì một behavioral weaver cũng có thể sửa classfile để chèn instructions. Nó nằm ở **tác động chủ đích lên execution flow hay type contract**. Một proxy có thể cung cấp interface bổ sung cho **wrapper**, nhưng điều đó không làm class target gốc tự biến thành một woven type mới. Structural weaving thật cần kiểm timing, compiler visibility, classloader, API compatibility, access rules và reflective shape.

Trong thực hành, hãy **xác định đúng đối tượng được bổ sung khả năng, ranh giới can thiệp và công nghệ đang dùng**, rồi viết test riêng cho behavior, riêng cho structure và test tích hợp khi hai kiểu crosscutting phối hợp. Đây là cơ sở để dùng AOP như một công cụ modular hóa có chủ đích thay vì lẫn lộn giữa “gọi thêm code” và “thay đổi hình dạng chương trình”.
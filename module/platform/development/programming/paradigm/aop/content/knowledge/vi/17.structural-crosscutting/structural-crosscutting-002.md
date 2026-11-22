# Bổ sung phương thức, thuộc tính hoặc giao diện khi công cụ hỗ trợ

## 1. Từ can thiệp hành vi đến thay đổi cấu trúc

Trong **Aspect-Oriented Programming (AOP)**, người học thường bắt đầu với pointcut và advice: chọn các join point, sau đó thực hiện logic trước, sau hoặc bao quanh một hoạt động vốn đã tồn tại. Đó là **can thiệp vào hành vi thực thi**. Tuy nhiên, một số mô hình/công cụ AOP còn hỗ trợ **bổ sung cấu trúc** cho chương trình: giới thiệu phương thức mới, thuộc tính/trạng thái mới hoặc giao diện/supertypes mới cho những kiểu được chọn.

Nhóm khả năng này thường được gọi là **introduction**, **inter-type declaration (ITD)**, **mixin**, **type/member introduction** hoặc **structural crosscutting** tùy ngữ cảnh công cụ. Các thuật ngữ liên hệ với nhau nhưng **không đồng nghĩa tuyệt đối**: một interface proxy có thể “introduce” một giao diện chỉ trên object proxy; một code generator có thể tạo subclass với methods/fields bổ sung; một source/bytecode weaver có thể thực sự thay đổi định nghĩa class nếu engine và giai đoạn xử lý hỗ trợ. Không được gộp các mô hình này thành cùng một cơ chế.

### Câu hỏi trung tâm

> Một aspect có thể khiến đối tượng “có thêm khả năng” theo nghĩa nào: **caller nhìn thấy một giao diện mới trên wrapper**, **runtime tạo một lớp con mới**, hay **kiểu đích thật sự có thêm khai báo trong chương trình đã được weave**?

Đây là câu hỏi về **structural capability**, không phải chỉ đổi thứ tự advice. Việc “công cụ hỗ trợ” là điều kiện then chốt: nhiều cơ chế AOP chỉ intercept method có sẵn và **không cung cấp** cách bổ sung field, method hay interface vào class gốc.

### Mục tiêu bài học

Sau bài học, bạn có thể:

1. Phân biệt **behavioral crosscutting** với **structural crosscutting**.
2. Giải thích interface introduction, mixin, inter-type method, inter-type field và thêm quan hệ implements/extends theo khả năng engine.
3. Phân biệt thay đổi **type gốc**, **subclass**, **proxy**, **decorator**, **metadata registry** và **mã generated**.
4. Hiểu tác động lên Java type system, compile-time visibility, runtime casts, reflection, generics, serialization và binary compatibility.
5. Đánh giá các giới hạn của final classes/methods, records, sealed hierarchies, constructors, visibility và JVM class loading.
6. Thiết kế state/lifecycle cho những thuộc tính được bổ sung, nhất là shared/per-object state và thread safety.
7. Giải quyết conflict khi nhiều aspects cùng khai báo method hoặc field, trùng signature/erasure và vấn đề thứ tự.
8. Chọn lúc nào nên introduction, lúc nào nên composition/decorator hoặc mở rộng API theo cách thông thường.
9. Chạy một ví dụ **Java 17 hoàn chỉnh** chứng minh JDK dynamic proxy triển khai thêm interface và methods trên proxy, **không sửa bytecode hay field của target**.
10. Xây dựng ma trận test xác nhận cả **hình dạng kiểu** và **hợp đồng hành vi** sau áp dụng aspect.

**Phạm vi:** Đây là kiến thức Aspect/AOP cơ bản và nâng cao **nói chung**. Không suy hành vi hoặc cú pháp của một AOP engine thành quy tắc chung cho mọi công cụ.

## 2. Structural crosscutting là gì?

Nếu một advice ghi log tại mọi lần gọi `save()`, nó bổ sung **hành vi quan sát** nhưng không nhất thiết làm public API của class thay đổi. Nếu một công cụ làm cho những object thuộc loại `Document` có thêm `getVersion()`, `setTag(...)` hoặc implements `Auditable`, ta đang nói tới một **thay đổi về cấu trúc** ở cấp thích hợp.

Ví dụ mong muốn:

~~~text
Trước:
    Document
       + title()
       + save()

Sau khi có một phép introduction phù hợp:
    Document hoặc một kiểu thay thế được công cụ sinh
       + title()
       + save()
       + tag()          <-- thành viên mới
       + setTag(value)  <-- thành viên mới
       + state tag      <-- trạng thái được cung cấp bởi intro
       implements Tagged
~~~

Sơ đồ là **mục tiêu khái niệm**, không phải lời khẳng định class `Document` trong mọi cách triển khai sẽ thực sự nhận field hay thay đổi `Class` object. Muốn kết luận cần kiểm tra **đối tượng mà caller sử dụng**, **binary thực sự được nạp**, và **metadata mà reflection nhìn thấy**.

### 2.1. Các phép thay đổi cấu trúc thường gặp

| Khả năng | Nghĩa | Điều kiện quan trọng |
| --- | --- | --- |
| **Introduce method** | Thêm callable operation cho một kiểu/đối tượng được chọn. | Visibility, name/signature, implementation, bytecode/API compatibility. |
| **Introduce field/property** | Thêm state hoặc accessor được liên kết với đối tượng. | Owner, khởi tạo, thread safety, lifecycle, reflection. |
| **Introduce interface** | Làm đối tượng/kiểu thỏa một protocol bổ sung. | Phải có implementations cho những abstract methods cần thiết. |
| **Introduce superclass/parent relation** | Thay đổi quan hệ kiểu theo khả năng tool. | Java inheritance restrictions, constructors, verifier, conflicts. |
| **Introduce implementation/mixin** | Cung cấp hành vi và đôi khi state từ một component khác. | Delegation vs weaving, per-instance vs shared state. |
| **Introduce metadata/annotation** | Thay đổi metadata mà tool có thể đọc. | Retention, runtime visibility, compile/load time, lookup site. |

Không phải mọi công cụ hỗ trợ mọi dòng. Có công cụ hỗ trợ chỉ intercept existing methods; có công cụ hỗ trợ chỉ interface introductions; có công cụ hỗ trợ nhiều dạng inter-type declarations.

### 2.2. Thêm một interface khác thêm các phương thức vào target gốc

Một proxy có thể implement `Tagged` và cung cấp `tag()` ngay trong handler dù `Target.class` không có method đó. Caller cast **proxy** sang `Tagged` thành công; cast **target gốc** sang `Tagged` vẫn thất bại.

Ngược lại, nếu source/bytecode weaving thực sự đưa interface vào class target và thêm method implementations, caller sử dụng class đã weave có thể thấy những thành viên đó tùy compile/runtime visibility. Đây là hai semantics khác nhau.

### 2.3. Field thật khác “property” bên ngoài

Một `Map<Target,State>` hoặc một field trong proxy handler có thể tạo cảm giác “target có thuộc tính tag”. Nhưng reflection trên `Target.class.getDeclaredFields()` sẽ **không** hiện một field mới chỉ nhờ map/handler tồn tại. Đừng gọi proxy-side association là **field được chèn vào class target**.

## 3. Cơ chế 1 — Interface proxy và delegation

Với JDK dynamic proxy, Java có thể tạo một proxy class runtime implements **một hoặc nhiều interfaces** được cung cấp cho `Proxy.newProxyInstance`. `InvocationHandler` quyết định cách xử lý invocation của từng method.

~~~text
Caller có Reader + Tagged
            |
            v
Proxy implements Reader, Tagged
            |
            +--> read(key)   -> delegate tới Reader target
            |
            +--> tag()       -> đọc state của handler
            +--> setTag(...) -> ghi state của handler
            |
            v
Original Reader target
   + read(key)
   (không tự có Tagged, tag/setTag)
~~~

Khả năng này thường được dùng để minh họa **interface introduction qua proxy**. Tuy nhiên phải phát biểu chính xác:

- Object proxy có thêm **interface và callable methods của interface**.
- Object target gốc không bị thay class và không được chèn field.
- Implementation cho method mới nằm ở handler/delegate của proxy.
- Source code của client muốn gọi `tag()` phải biết kiểu `Tagged` hoặc kiểm tra/cast động.
- Invocation đi thẳng vào target, không qua proxy, không thấy introduced behavior của wrapper.
- Interface method selection và equality semantics cần được test.

### 3.1. Điều JDK dynamic proxy không làm

JDK interface proxy **không** tạo một subclass tùy ý của concrete target class. Nó không thay class definition của target đã tồn tại, không thêm một public method trực tiếp vào `Target.class`, và không khiến phép `(ConcreteTarget)proxy` luôn hợp lệ.

Nó cũng không tự expose **một method mới không thuộc interfaces được khai báo** như một callable typed Java method cho client. Muốn giới thiệu operation cho proxy theo cách này, cần interface mang method signature tương ứng.

### 3.2. Handler phải thực thi được cả hai nhóm methods

Một handler delegate mọi method tới target bằng `method.invoke(target,args)` sẽ lỗi khi method thuộc interface mới nhưng target **không implement** interface đó. Phải phân nhánh:
- Methods thuộc interface gốc → gọi target.
- Methods thuộc interface mới → gọi implementation/mixin state thích hợp.
- `equals/hashCode/toString` → quyết định semantics rõ.
- Nếu trùng chữ ký giữa interfaces → hiểu cách proxy lựa chọn `Method` và dispatch; không dựa mù vào `getDeclaringClass()` khi signature overlap.

Nếu không xử lý, giới thiệu interface trên giấy nhưng methods không chạy đúng là một **lỗi contract**, không phải introduction thành công.

## 4. Cơ chế 2 — Decorator hoặc adapter hiện thực tường minh

Một class thông thường có thể implements nhiều interfaces rồi chuyển tiếp operations:

~~~java
interface Reader {
    String read(String key);
}

interface Tagged {
    String tag();
}

final class TaggedReader implements Reader, Tagged {
    private final Reader target;
    private final String tag;

    TaggedReader(Reader target, String tag) {
        this.target = target;
        this.tag = tag;
    }

    public String read(String key) {
        return target.read(key);
    }

    public String tag() {
        return tag;
    }
}
~~~

Đây là **đoạn minh họa**, không phải chương trình độc lập. Nó **không đòi engine AOP có introduction primitive**. Điểm mạnh:
- Type relationship thấy rõ lúc compile.
- Implementation dễ kiểm thử và debug.
- State ownership theo instance rõ.
- Có thể dùng IDE/refactoring/lint bình thường.
- Không có runtime weave/dependency đặc biệt.

Điểm đánh đổi:
- Phải tự viết/wire wrapper và forwarding logic.
- Caller phải nhận đúng decorator thay vì target.
- Target class gốc vẫn không có interface mới.
- Constructor/decorator chain và resource ownership cần thiết kế rõ.
- Nếu số loại wrapper lớn có thể tăng boilerplate.

**Khi nào ưu tiên?** Khi chỉ có vài loại, yêu cầu API rất rõ, không cần crosscutting scope lớn và lợi ích kiểm soát compile time cao hơn tự động introduction.

## 5. Cơ chế 3 — Subclass hoặc generated subclass

Một code generator/runtime library có thể tạo subclass:

~~~text
BaseTarget
    ^
    |
GeneratedTargetProxy
   + methods override/intercept
   + methods mới nếu generator hỗ trợ
   + fields bổ sung trong subclass
~~~

Nếu subclass hợp lệ, proxy có thể assignable tới base class. Nhưng phải phân biệt:
- Một **field mới trong subclass** không phải field được đưa vào định nghĩa **base class**.
- Một method mới trong subclass có thể cần caller biết generated subtype hoặc một interface.
- Method `private`, `final` và constructor không có override semantics giống virtual methods.
- Một class `final` không thể được subclass.
- Object state đã tồn tại và quá trình constructor/delegation có thể khác nhau giữa các generator.

### 5.1. `final`, records và sealed hierarchy

- **Final class:** không thể tạo subclass Java hợp lệ của final class. Nhưng vẫn có thể bọc qua interface proxy/decorator nếu abstraction cho phép.
- **Final method:** subclass không thể override final method. Bổ sung một method **khác tên/chữ ký** là câu chuyện riêng nhưng vẫn bị các ràng buộc class.
- **Record:** record class ngầm định final; không thể tự nhiên tạo subclass của record như một base class bình thường.
- **Sealed class/interface:** quan hệ subtype/implementation bị kiểm soát bởi permitted subtypes. Một proxy không thể giả định được phép implement mọi sealed interface hoặc subclass sealed type ngoài danh sách/quy tắc hợp lệ.
- **Private members:** reflection có thể tìm thấy declarations theo quyền truy cập nhưng điều đó không biến private method thành một điểm override bình thường.

Với source/bytecode weaving, các giới hạn, cách công cụ xử lý và giai đoạn thay đổi có thể khác; không tự suy “final luôn cấm mọi dạng AOP”.

### 5.2. Constructor và object initialization

Một generated subtype phải có chiến lược khởi tạo superclass state hợp lệ. Không thể giả định constructor của target luôn được chạy đúng một lần trên cùng object theo mọi loại proxy. Những invariant được thiết lập trong constructor, side effects khi tạo object và `this` escaping trong constructor cần được test ở engine thật.

Không nên dùng introduction chỉ để tránh thiết kế constructor/resource lifecycle có hợp đồng rõ.

## 6. Cơ chế 4 — Source hoặc bytecode weaving cấu trúc

Một số engine AOP hỗ trợ **structural introductions thật sự**: tại quá trình source transformation, compile-time weaving, post-compile processing hoặc load-time weaving, nó có thể thay đổi class artifact để có:
- Method implementations.
- Fields mới.
- Interface declarations.
- Một số metadata/quan hệ type khác theo khả năng công cụ.

Trường hợp này khác JDK interface proxy: thay đổi có thể được phản ánh trong **binary class definition được nạp**, không chỉ wrapper object.

### 6.1. Bài toán compile-time visibility

Có ít nhất ba góc nhìn cần kiểm:

1. **Source gốc:** `Target.java` có khai báo member đó không?
2. **Compiler của client:** compiler có biết member/interface được introduced nhờ toolchain không?
3. **Runtime:** class được nạp có binary chứa introduced member không?

Một class artifact đã weave có thể chứa method mà source ban đầu không có, nhưng một file client compile bằng javac theo class path/compile pipeline khác có thể không nhìn thấy member như mong muốn. Ngược lại, client compile với một artifact đã weave nhưng runtime lại nạp **bản chưa weave** có thể gặp lỗi linkage hoặc cast.

Không nói “runtime đã introduce nên mọi source đang compile tự động biết method mới”. Hãy kiểm build inputs, compile order, classpath/module path và artifact deployment.

### 6.2. Class loading và class identity

Một `Class` object phản ánh **class đã được JVM định nghĩa** bởi loader. Nếu biến đổi xảy ra trước khi class được define, structure mới có thể trở thành một phần của định nghĩa ấy. Nếu class đã được load, những khả năng thay đổi cấu trúc qua instrumentation/redefinition bị giới hạn bởi JVM và công cụ; không được tự suy có thể thêm trường/phương thức/interface vào một class đã load tùy ý.

Cùng tên class nhưng được nạp bởi hai classloaders khác nhau vẫn là **hai runtime types khác nhau**. Weaving/configuration theo classloader có thể dẫn đến một module nhìn thấy introduced members còn module khác thì không.

### 6.3. Build consistency

Đảm bảo:
- Đúng công cụ biến đổi được chạy trong build.
- Sources và generated artifacts khớp phiên bản.
- Compiler của client dùng đúng binary/API view.
- Production nạp cùng artifact (hoặc được biến đổi tương đương ở load time).
- Cache incremental build được invalidated đúng khi introduction thay đổi.
- Có integration tests chạy với artifact cuối, không chỉ class trong IDE.

### 6.4. Vì sao weaving không tự làm đúng mọi thứ?

Thêm member ở binary level chỉ là **type/structure capability**. Nó chưa bảo đảm:
- Giá trị trả về đúng domain contract.
- Field có owner/scope phù hợp.
- Thread safety.
- Initialization xảy ra đúng thời điểm.
- Serialization/binary compatibility.
- Không có conflict với các aspect khác.
- Security/lifecycle không bị bypass.

## 7. Giới thiệu giao diện: chỉ “implements” là chưa đủ

Giả sử muốn `Invoice` có thêm khả năng:

~~~java
interface Auditable {
    String auditId();
}
~~~

Một công cụ đưa `implements Auditable` vào kiểu mà không có implementation cho `auditId()` sẽ phải giải quyết nghĩa của một abstract method còn thiếu. Tùy công cụ, phải introduce implementation, trỏ sang một delegate/mixin hoặc có một default implementation hợp lệ.

### 7.1. Interface method mặc định

Java interfaces có thể có `default` methods. Nhưng chúng không tự giải quyết mọi conflict:
- Hai interfaces có default methods cùng signature có thể cần phân giải tường minh.
- Một class method hợp lệ có thể ưu tiên hơn default implementation theo luật Java.
- Với JDK dynamic proxy, invocation của default method vẫn có thể đi qua handler; việc gọi default implementation là một thao tác có API/semantics riêng, không tự xảy ra nếu handler chỉ trả null.
- Nếu method introduced có logic dựa vào field target mà target không có, phải tạo state/bridge phù hợp.

### 7.2. Client phải có typing phù hợp

Nếu chỉ một runtime proxy implements `Auditable`, biến:

~~~java
Reader reader = ...;
~~~

không tự có method `auditId()` trong compile-time type `Reader`. Client cần:
- Nhận reference typed as `Auditable`.
- Kiểm tra `instanceof Auditable` rồi dùng pattern variable/cast.
- Hoặc có API/factory trả type thể hiện cả hai capabilities.

Một số weaving toolchains có thể tích hợp type model để compiler thấy introduced declarations, nhưng phải dùng đúng toolchain và artifacts.

### 7.3. Một subtype mới có ý nghĩa nghiệp vụ?

“Đối tượng hỗ trợ `Auditable`” là một lời hứa hành vi. Nếu method `auditId()` luôn trả null hay một ID không ổn định trong khi contract hứa ID bền vững, chỉ thêm interface chưa tạo substitutability. Introduction phải có **behavioral contract tests** tương tự implementation bình thường.

## 8. Giới thiệu phương thức: tên, chữ ký và overload

Một inter-type method có thể thêm operation như `tag()`, `setTag()`, `validate()` hoặc `snapshot()` theo loại target được chọn. Những điểm phải xử lý:

1. **Tên method** có thể đã tồn tại trong target.
2. **Parameter signature** có thể trùng method hiện hữu hoặc method từ aspect khác.
3. **Return type** có thể không tương thích khi override/implement.
4. **Generic erasure** có thể khiến hai declarations tưởng khác nhau ở source thành **name clash** ở JVM.
5. **Visibility** có thể làm một member không thể expose theo mong muốn.
6. **Exception declaration** có thể không phù hợp hợp đồng của interface.
7. **Bridge methods** và covariant returns có thể ảnh hưởng reflection/dispatch.
8. **Default methods** có thể xung đột trong multiple-interface composition.
9. **Varargs và overloaded methods** cần matching/call-site resolution chính xác.
10. **Method name mang nghĩa domain:** adding `validate()` không nên vô tình đổi cách một existing API gọi validation.

### 8.1. Trùng chữ ký phải có chính sách xung đột

Ví dụ target đã có:

~~~java
String tag();
~~~

Một aspect lại muốn introduce `String tag()`. Không thể chỉ nói “introduction thắng method cũ” cho mọi engine. Cần xem công cụ:
- Từ chối do duplicate/conflict.
- Cho phép implementation override theo precedence nếu có hợp đồng cụ thể.
- Chọn implementation khác theo binding rule.
- Buộc đổi tên/đổi interface hoặc tái cấu trúc.

Nếu hai aspects cùng introduce method, cần quyết định ai sở hữu, ai override, hoặc fail fast. Đừng dựa vào classpath scan/weaving order không được công bố.

### 8.2. Không dựa vào return type để phân biệt overload

Trong Java source, overload không thể chỉ khác return type. Một introduction có `String status()` và existing `int status()` không phải hai methods có thể cùng tồn tại như hai lựa chọn overload source bình thường. Có thể xuất hiện những vấn đề JVM descriptors/bridge phức tạp, nhưng công cụ phải giải quyết chúng theo luật verifier/compiler và API contract, không tự “thêm cả hai” một cách vô điều kiện.

### 8.3. Generics và erasure

Hai declarations:

~~~java
void process(java.util.List<String> items);
void process(java.util.List<Integer> items);
~~~

Đây là **mã minh họa xung đột**, không phải mã Java hợp lệ trong cùng class: sau type erasure, cả hai có cùng erasure `process(List)`. Introduction phải được kiểm tra sau erasure chứ không chỉ so text của generic arguments.

### 8.4. Phương thức introduced cần được test như API thực

Gọi `tag()` không chỉ kiểm “có callable”. Cần test:
- Giá trị khởi tạo hợp lệ.
- Input null/invalid.
- Hợp đồng exception.
- State isolation giữa objects.
- Thread safety khi set/get đồng thời.
- Visibility với clients biên dịch theo artifact cuối.
- Behavior sau serialization/deserialization khi hỗ trợ.

## 9. Giới thiệu thuộc tính hoặc field: state thuộc về ai?

Thêm một field được dệt vào target có semantics khác việc tạo một field trong handler hoặc registry.

### 9.1. Trạng thái có thể gắn theo ba nơi

~~~text
(A) Woven target field
      Target+introducedField

(B) Proxy/decorator field
      Proxy(tag) -> Target(no field)

(C) External association
      Registry[Target identity] -> tagState
~~~

Cả ba có thể hỗ trợ operations `tag()`/`setTag()` ở một API phù hợp nhưng có đặc tính khác:

| Thuộc tính | Field dệt trong target | State của proxy | State trong registry |
| --- | --- | --- | --- |
| Owner trực tiếp | Woven target instance. | Proxy/handler instance. | Registry/association. |
| Hai proxies cùng target | Có thể cùng state khi đọc field trên target. | Có thể tách state theo proxy. | Tùy key theo target hay proxy. |
| Reflection trên target class | Có thể thấy field nếu thực sự dệt. | Không thấy field của proxy. | Không thấy registry state như field. |
| Cleanup | Theo target + resource lifecycle. | Theo proxy lifetime. | Cần remove/eviction. |
| Risk | Initialization, binary/schema changes. | Nhiều wrappers, ownership. | Retention, keys, concurrency. |

Không có lựa chọn luôn tốt nhất. Điều quan trọng là **đơn vị identity/lifetime của dữ liệu được introduction**.

### 9.2. Per-instance hay shared?

Một introduced field **instance** thường tách dữ liệu giữa các target instances khi đúng model; một field **static** là state cấp class/runtime type, có thể dùng chung nhiều objects. Nhưng classloader và weaving scope có thể khiến cùng tên class tạo nhiều bản riêng.

Nếu muốn mỗi target có ID độc lập, một static mutable field `currentAuditId` là sai. Nếu muốn shared immutable policy, lặp policy vào mỗi target có thể không cần thiết.

### 9.3. Field mới cần initialization

Một field kiểu `String tag` có default JVM là null nếu không được khởi tạo tường minh; với primitive `int`, default 0. Nhưng **default JVM không nhất thiết là business default đúng**. Nếu interface hứa `tag()` luôn non-null, phải thiết kế initializer/constructor hook/lazy-safe initialization hoặc accessor logic có contract phù hợp.

### 9.4. Thread safety

Nếu target singleton được nhiều threads dùng, introduced instance field vẫn shared bởi nhiều calls. Một `int updates++` không atomic; một `StringBuilder` được chia sẻ không an toàn concurrent; `volatile` hỗ trợ visibility cho một field nhưng không tự biến compound operation thành atomic.

Dùng `AtomicInteger`, synchronization, immutable snapshots hoặc state riêng mỗi invocation theo yêu cầu. Per-target không đồng nghĩa per-thread.

### 9.5. Lifecycle/resource

Nếu introduced field giữ `InputStream`, listener, thread, cache hoặc lock, cần owner/close/unregister rõ. Khi field thật gắn với target, nó có thể giữ resources đến khi target không còn reachable; GC không phải một lifecycle hook xác định để đóng tài nguyên ngoài heap.

Nếu registry giữ strong keys từ target tới state, registry có thể giữ target sống vô hạn. Nếu proxy có trường giữ target, proxy lifetime có thể kéo dài target lifetime. Đừng coi introduction là miễn phí về memory.

## 10. Ví dụ Java 17 runnable: một proxy giới thiệu interface Tagged

Ví dụ sau cố ý **không dùng weaver đặc biệt**, chỉ sử dụng API Java 17. Nó minh họa **giới thiệu giao diện trên proxy**:
- Target `BasicReader` chỉ implements `Reader`.
- Proxy được tạo implements cả `Reader` và `Tagged`.
- `read` đi tới target; `tag`/`setTag` được xử lý trong invocation handler.
- Hai proxies bọc **cùng target** nhưng mỗi handler có state `tag` riêng.
- Object methods `equals`, `hashCode`, `toString` được xử lý với semantics **identity của proxy**, không cố làm proxy và target có cùng identity.
- Lỗi từ target được gỡ khỏi `InvocationTargetException`, giữ exception gốc cho caller.
- Reflection trên `BasicReader` không tự xuất hiện method `tag`; introduction chỉ có trên proxy.

Tạo file **`InterfaceIntroductionDemo.java`**:

~~~java
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.Arrays;

public class InterfaceIntroductionDemo {
    interface Reader {
        String read(String key);
    }

    interface Tagged {
        String tag();
        void setTag(String value);
    }

    static final class BasicReader implements Reader {
        @Override
        public String read(String key) {
            System.out.println("TARGET read " + key);
            if ("BAD".equals(key)) {
                throw new IllegalArgumentException("bad key");
            }
            return "DATA:" + key;
        }
    }

    static final class IntroductionHandler implements InvocationHandler {
        private final Reader target;
        private String tag = "unset";

        IntroductionHandler(Reader target) {
            this.target = target;
        }

        @Override
        public Object invoke(Object proxy, Method method, Object[] args)
                throws Throwable {
            if (method.getDeclaringClass() == Object.class) {
                return switch (method.getName()) {
                    case "equals" -> proxy == args[0];
                    case "hashCode" -> System.identityHashCode(proxy);
                    case "toString" -> "TaggedReaderProxy";
                    default -> throw new UnsupportedOperationException(
                            method.getName());
                };
            }

            if (method.getDeclaringClass() == Tagged.class) {
                return switch (method.getName()) {
                    case "tag" -> tag;
                    case "setTag" -> {
                        tag = (String) args[0];
                        System.out.println("INTRO setTag " + tag);
                        yield null;
                    }
                    default -> throw new UnsupportedOperationException(
                            method.getName());
                };
            }

            try {
                return method.invoke(target, args);
            } catch (InvocationTargetException wrapped) {
                throw wrapped.getCause();
            }
        }
    }

    static Reader attachTag(Reader target) {
        return (Reader) Proxy.newProxyInstance(
                Reader.class.getClassLoader(),
                new Class<?>[] { Reader.class, Tagged.class },
                new IntroductionHandler(target)
        );
    }

    public static void main(String[] args) {
        Reader target = new BasicReader();
        Reader first = attachTag(target);
        Reader second = attachTag(target);

        System.out.println("FIRST Reader=" + (first instanceof Reader));
        System.out.println("FIRST Tagged=" + (first instanceof Tagged));
        System.out.println("TARGET Tagged=" + (target instanceof Tagged));
        System.out.println("SAME class="
                + (first.getClass() == target.getClass()));
        System.out.println("SAME object=" + (first == target));

        Tagged a = (Tagged) first;
        Tagged b = (Tagged) second;
        a.setTag("alpha");
        b.setTag("beta");
        System.out.println("TAGS first=" + a.tag()
                + " second=" + b.tag());

        System.out.println("CLIENT " + first.read("A"));
        System.out.println("CLIENT " + target.read("B"));

        System.out.println("PROXY self-equal=" + first.equals(first));
        System.out.println("PROXY target-equal=" + first.equals(target));
        System.out.println("PROXY text=" + first);

        boolean targetHasTagMethod = Arrays.stream(
                target.getClass().getDeclaredMethods()
        ).anyMatch(method -> method.getName().equals("tag"));
        System.out.println("TARGET method tag=" + targetHasTagMethod);

        try {
            first.read("BAD");
        } catch (IllegalArgumentException error) {
            System.out.println("CLIENT error=" + error.getMessage());
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac InterfaceIntroductionDemo.java
java InterfaceIntroductionDemo
~~~

**Stdout kỳ vọng, đúng thứ tự:**

~~~text
FIRST Reader=true
FIRST Tagged=true
TARGET Tagged=false
SAME class=false
SAME object=false
INTRO setTag alpha
INTRO setTag beta
TAGS first=alpha second=beta
TARGET read A
CLIENT DATA:A
TARGET read B
CLIENT DATA:B
PROXY self-equal=true
PROXY target-equal=false
PROXY text=TaggedReaderProxy
TARGET method tag=false
TARGET read BAD
CLIENT error=bad key
~~~

### 10.1. Vì sao `FIRST Tagged=true` nhưng `TARGET Tagged=false`?

`Proxy.newProxyInstance` tạo object proxy implements hai interfaces được cung cấp. `BasicReader` gốc chỉ implements `Reader` và không bị sửa cấu trúc, nên khi `target` là reference kiểu `Reader`, `target instanceof Tagged` trả false.

Đây là bằng chứng trực tiếp về **interface introduction trên wrapper**, không phải interface được dệt vào target class.

### 10.2. Vì sao hai proxies có tags khác nhau?

Mỗi lời gọi `attachTag(target)` tạo **một `IntroductionHandler` mới**, có field `tag` riêng. Cho dù hai handlers giữ cùng target, `a.tag()` và `b.tag()` vẫn là `alpha` và `beta`.

Đây là **per-proxy state**, không phải per-target state. Nếu yêu cầu “mỗi Reader target chỉ có một tag, mọi wrappers cùng thấy”, cần owner/map/field khác và test identity association.

### 10.3. Vì sao `read()` còn hành vi target gốc?

Handler chuyển tiếp `Reader` methods qua `method.invoke(target,args)`. `read("A")` in `TARGET read A` rồi trả `DATA:A`. Lỗi khi `read("BAD")` được gỡ khỏi `InvocationTargetException`, caller tiếp tục nhận `IllegalArgumentException("bad key")`.

Giới thiệu interface mới không bắt buộc làm thay đổi semantics của những operations cũ — nhưng điều đó phải được **hiện thực và kiểm thử**, không tự động đúng với mọi handler.

### 10.4. Vì sao không có `tag` trong target reflection?

`Arrays.stream(target.getClass().getDeclaredMethods())` phản ánh methods được khai báo trong `BasicReader` class đã load. Chúng không có `tag` vì handler chỉ cài method cho proxy. Dữ liệu tag cũng là field của `IntroductionHandler`, không phải field mới của `BasicReader`.

Nếu một engine weaving thật sự thêm `tag` vào class artifact, kết quả reflection có thể khác; phải test artifact đó thay vì suy từ demo.

### 10.5. Identity và equals là hợp đồng phải chọn

`first != target` vì là hai objects. Handler định nghĩa `equals` là so identity của proxy, vì vậy `first.equals(first)` true và `first.equals(target)` false. `hashCode` tương thích với identity semantics ấy. `toString` có giá trị riêng của proxy.

Nếu API trước kia hứa object identity của target, giao diện mới không khiến proxy trở nên “trong suốt hoàn toàn”. Đây là khác biệt cần giải quyết tại abstraction boundary.

### 10.6. Demo cố ý không đảm bảo điều gì?

- Không chèn một field mới vào target class.
- Không thêm một Java method declaration mới vào source/bytecode của `BasicReader`.
- Không dùng syntax của một ITD/weaving engine chuyên biệt.
- Không tạo subclass của `BasicReader` (lớp này còn được khai báo `final`).
- Không làm `Reader` interface gốc tự kế thừa `Tagged`.
- Không xử lý nhiều interfaces có methods trùng signature; `getDeclaringClass` phân nhánh đúng nhờ các methods **không trùng** ở demo.
- Handler lưu mutable String `tag` và chạy tuần tự; nếu nhiều threads set/read cùng proxy, cần memory-visibility/atomicity contract phù hợp.
- Không xử lý serialization, module access phức tạp, async stream hoặc production-grade resource lifecycle.

### 10.7. Mở rộng bài thực hành

Bạn có thể thêm method `clearTag()` vào `Tagged`, rồi sửa handler tương ứng. Để giữ contract, hãy kiểm:
- `clearTag()` trả về trạng thái được định nghĩa.
- Hai proxy có state độc lập.
- Target reflection vẫn không thấy added method.
- Nếu dùng chung một handler cho hai proxies, state **có thể** trở thành shared và cần được công bố.
- Nếu muốn thread-safe semantics, chỉ rõ linearization/visibility của get/set/clear.

Đây là bài tập thiết kế interface extension **qua proxy**, vẫn không phải field introduction bằng weaving.

## 11. Khi phương thức introduced gọi lại target

Một introduced method có thể triển khai bằng:
- Đọc state của handler.
- Gọi một method có sẵn trên target.
- Delegate sang helper/mixin object.
- Thực thi behavior mới hoàn toàn.
- Kết hợp nhiều operations của target.

Ví dụ một `snapshot()` introduced có thể gọi `read()` nhiều lần. Nhưng nên quyết định **gọi qua proxy hay target**:
- Gọi `target.read()` trực tiếp có thể bypass advice được đặt trên proxy `read()`.
- Gọi `proxy.read()` có thể đi qua advice nhưng dễ tạo recursion nếu chính `read()` lại gọi `snapshot()`.
- Nếu introduced method chạy trong class đã weave, self-invocation semantics phụ thuộc join-point model.

Đây là vấn đề **interception path**, độc lập với việc field/method mới có tồn tại. Thêm cấu trúc không tự sửa lỗi self-invocation hoặc recursive advice.

### 11.1. Không lặp side effect ngoài ý định

Một introduced method `saveAndTag()` gọi `save()` rồi cập nhật tag. Nếu aspect retry bên ngoài và `save()` không idempotent, lặp toàn bộ operation có thể tạo duplicate changes. Cần define atomicity, failure/rollback và retry boundary.

### 11.2. Chú ý transaction/resource scope

Nếu introduced method mở một stream/lock hoặc gắn state bên cạnh thao tác nghiệp vụ, ai đóng chúng? Một method trả stream không thể bị wrapper `finally` đóng resource ngay khi return nếu caller còn đọc. Với async, `CompletionStage` completion có thể xảy ra sau method return.

### 11.3. Thực thi field access vs accessor method

Một tool AOP có thể hỗ trợ field-get/set join points; tool khác chỉ thấy method calls. Nếu policy dựa vào việc can thiệp mọi lần đọc/ghi field introduced, phải kiểm nó có thực sự observe field access không. Một direct field access không tự trở thành method invocation trên proxy.

## 12. Các xung đột khi nhiều aspects cùng thay đổi cấu trúc

Một chương trình lớn có thể có:
- Aspect A introduce `getTag()`.
- Aspect B cũng introduce `getTag()` nhưng khác nghĩa.
- Một base class đã có `getTag()`.
- Một mixin yêu cầu property `tag` còn một mixin khác dùng cùng tên.
- Một interface mới có default method cùng signature.
- Một generated bridge method trùng descriptor.

### 12.1. Những chiến lược giải quyết

| Tình huống | Chiến lược cần cân nhắc |
| --- | --- |
| Method đã tồn tại | Từ chối, đổi tên/API hoặc precedence nếu tool có semantics rõ. |
| Hai introductions trùng method | Fail fast hoặc khai override rule tường minh. |
| Field trùng tên | Đặt owner/namespace rõ hoặc đổi mô hình state. |
| Interface methods không được implement | Cung cấp delegate/default implementation hợp lệ. |
| Generic erasure name clash | Đổi signature/API; không kỳ vọng runtime phân biệt generics đã erasure. |
| Hai advice dùng state khác owner | Tách per-target/per-proxy/per-flow semantics. |
| Initialization đan xen | Chọn lifecycle owner và xác nhận thứ tự tạo state. |
| Build artifact lệch version | Rebuild/weave đồng bộ và test binary. |

Không nên coi source order, alphabetical class name hay registry insertion order là **hợp đồng ưu tiên cấu trúc** nếu công cụ không công bố.

### 12.2. Precedence của advice khác conflict resolution của members

Advice order quyết định wrapper nesting cho **một execution join point**. Member introduction conflict liên quan **hình dạng type** và lựa chọn implementation; nó có thể được giải quyết trong compiler/weaver trước runtime. Đảo order advice không tự loại duplicate methods.

### 12.3. Giao diện được introduce có thể thay đổi method overload resolution

Nếu compile-time view của một type có thêm overload, compiler của client có thể chọn method khác ở những lời gọi ambiguous hoặc overload-dependent. Đây là hệ quả về **source compatibility**, không chỉ runtime dispatch. Cần kiểm trên consumer source code và artifact build cuối.

## 13. Source compatibility, binary compatibility và behavioral compatibility

Ba trục này không thay thế nhau:

### 13.1. Source compatibility

Client source đang compile có còn compile sau khi introduce method/interface không?
- Một method mới có thể tạo overload ambiguity.
- Một interface mới có thể mang abstract methods mà implementation cần đáp ứng.
- Một type đã được giới thiệu có thể ảnh hưởng generic bounds.
- Client javac thông thường có thể chưa biết introduced member nếu build pipeline không đưa declaration vào compile-time view.

### 13.2. Binary compatibility

Class files đã compile trước đó có tiếp tục link/run được với transformed artifacts không?
- Class/method/field descriptors có khớp không?
- Có nạp nhầm artifact chưa weave không?
- Runtime có gặp `NoSuchMethodError`, `NoSuchFieldError`, `AbstractMethodError` hoặc linkage errors khác không?
- Classloader/module boundaries có đúng không?

Không khẳng định mỗi introduction đều gây các lỗi ấy; đó là **những failure modes cần test** khi build/runtime artifacts không đồng bộ.

### 13.3. Behavioral compatibility

Dù code compile và link:
- Return values có đúng contract?
- Exception types/cause và nullability có giữ?
- Đối tượng được gắn state mới có đúng identity/lifetime?
- Existing methods có bị advice hoặc mixin thay behavior ngoài ý định?
- Concurrency/serialization/lazy streams/async outcomes có đúng?
- Các clients dựa vào reflection/equality có còn hoạt động?

Một introduction thành công ở structural level vẫn có thể thất bại ở behavioral level.

### 13.4. Compatibility nên được phát biểu theo client boundary

Một JDK interface proxy implements `Reader,Tagged` có thể thay target tốt ở `Reader` contract nhưng không thay được concrete target type về `getClass`, serialization hoặc casts. Không hứa hoàn toàn trong suốt cho mọi Java observation.

## 14. Reflection, annotations và tooling sau introduction

### 14.1. Reflection hỏi object nào?

- `target.getClass()`: class của target gốc.
- `proxy.getClass()`: generated proxy class.
- `wovenTarget.getClass()`: class definition thực sự được nạp sau transformation.

Nếu introduction chỉ nằm trên proxy, reflection trên target không thấy field của handler. Nếu bytecode đã weave vào target, reflection có thể thấy thành viên theo visibility và loại truy vấn `getMethods`/`getDeclaredMethods` tương ứng.

### 14.2. Annotation lookup

Một annotation có thể nằm ở:
- Interface mới.
- Method introduced.
- Target implementation.
- Mixin/delegate implementation.
- Proxy-generated method.
- Bytecode artifact đã weave.

Java reflection không tự hợp nhất annotations từ mọi chỗ thành một cái nhìn duy nhất. Một advice matching metadata phải xác định nơi lookup, retention và inheritance semantics. Nếu matcher chỉ đọc method của interface gốc, annotation trên mixin có thể không được nhìn thấy.

### 14.3. IDE, debugger, stack trace

Generated methods hoặc code dệt có thể khiến:
- IDE navigation không mở tới source như một method bình thường.
- Stack trace thêm frames từ proxy/interceptor/bridge.
- Source-level breakpoint không khớp vị trí transformed bytecode.
- Incremental compilation cache sai khi cấu trúc đã thay nhưng artifact chưa cập nhật.

Những giới hạn này là vấn đề **toolchain observability**; không chứng minh introduction không đúng, nhưng cần hướng dẫn debug/build rõ.

## 15. Serialization, state migration và phiên bản

Nếu class đã weave có thêm instance field, serialized form hoặc reflection-based mapper có thể thay đổi — **tùy serialization mechanism**. Với Java native serialization, default field serialization và serialVersionUID cần cân nhắc; với JSON mapper, các getters/fields mới có thể xuất hiện trong schema khi được tool discover.

Một proxy giữ field ở handler lại có object graph/serializability khác target. Không tự giả định target `Serializable` nghĩa là mọi handler/delegate và proxy setup đều serialize/deserialize như mong đợi.

### 15.1. Tương thích dữ liệu cũ

Khi cấu trúc mới được triển khai:
- Dữ liệu đã lưu trước introduction có field mới mặc định gì?
- Khi deserialize object cũ, introduced member có invariant nào phải thỏa?
- Có cần migration/backfill?
- Một target chưa weave nhưng đọc dữ liệu có field mới sẽ xử lý thế nào?
- Phiên bản client cũ khi gọi API mới có fail hay bỏ qua fields hợp lệ?

### 15.2. Object identity sau deserialization

Nếu introduced state nằm trong proxy handler, deserialize hoặc tạo wrapper mới có thể tạo state mới. Nếu state nằm trong woven target field, nó có thể theo serialized field tùy cơ chế. Cần xác định **source of truth** và persistence contract, không đồng nhất hai mô hình.

### 15.3. Không đưa toàn bộ target vào registry để “giữ thuộc tính”

Nếu dùng external association, một global strong-key map có thể giữ tất cả targets không còn dùng. Nếu value chứa back-reference tới key, weak-key mapping cũng cần được xem xét retained paths. Có thể cần explicit removal, per-request/per-target owner hoặc ID-based store bounded theo nghiệp vụ.

## 16. Security và quyền truy cập khi bổ sung API

Introduction có thể tăng **attack surface**. Một method `resetAudit()` vốn không tồn tại trên API cũ nay trở thành public method ở wrapper hoặc transformed class có thể bị caller dùng nếu giữ reference phù hợp.

Cần hỏi:
1. Method mới có nên public không?
2. Có authorization và validation phù hợp không?
3. Nếu mixin truy cập state target, đó có phải quyền truy cập được phép?
4. Interface mới có vô tình làm object được các serializers/routers/discoverers nhận thành capability nhạy cảm không?
5. Có đường gọi trực tiếp target bỏ qua proxy enforcement không?
6. Các pointcuts security có khớp methods mới không?
7. Một introduced method có thể bypass invariant của domain API cũ không?
8. Có cần negative tests cho untrusted callers?

### 16.1. “Implements interface” không phải bằng chứng caller có quyền

Một marker interface hoặc `Auditable` chỉ mô tả capability/contract ở type level. Nó không xác thực identity người dùng. Nếu có method nhạy cảm, policy phải được bảo vệ ở trusted boundary và trong implementation khi cần.

### 16.2. Reflection không phải ranh giới bảo mật duy nhất

Một method public introduced có thể được gọi bằng typed API hoặc reflection. Dựa vào việc “người dùng không biết tên method generated” không phải security policy. Cần thiết kế access modifiers và enforcement thật.

### 16.3. Không log toàn bộ state introduced

Một field như `tenantContext` có thể chứa dữ liệu nhạy cảm. Advice tự động ghi mọi field bằng reflection để debug có thể lộ secrets hoặc gây recursion. Chỉ log những fields được allowlist, sanitize và giới hạn dung lượng.

## 17. Khởi tạo state, lifecycle và chạy song song

### 17.1. Một introduction có thể phục vụ nhiều objects

Nếu cùng aspect giới thiệu interface cho nhiều targets:
- Một instance aspect có thể phục vụ nhiều targets.
- State có thể nằm trong từng proxy/handler.
- State có thể nằm trong từng target đã weave.
- State có thể nằm trong registry shared.
- Một mixin object có thể là singleton hoặc tạo per target tùy cấu hình.

Phải nêu association key và owner. Không mặc định một aspect declaration sinh đúng một object cho mỗi target.

### 17.2. Trường hợp tạo hai proxies cho cùng target

Trong demo Java, tag được gắn với **handler**, nên hai wrappers có hai tag riêng. Nếu nghiệp vụ yêu cầu một tag duy nhất trên target, cách đó không đủ. Hãy chọn:
- Một proxy duy nhất có owner ổn định.
- State gắn vào target qua weaving phù hợp.
- Per-target identity registry có cleanup.
- Một adapter quản lý canonical identity.

Mỗi lựa chọn có rủi ro khác nhau với equality, references và memory.

### 17.3. Đồng thời

Nếu `setTag()` được gọi trên cùng proxy từ nhiều threads, field `String tag` mutable trong demo không có explicit synchronization/volatile. Reference assignment có atomicity theo Java, nhưng thread đọc có thể gặp visibility/ordering không đúng mong muốn. Dùng `volatile`, `AtomicReference` hoặc lock khi hợp đồng yêu cầu; nếu thao tác gồm nhiều fields, cần synchronization cho toàn invariant.

### 17.4. Lazy initialization

Một introduced member có thể được tạo state khi lần đầu gọi. Với nhiều threads, nếu logic kiểu `if (state==null) state = new State()`, có thể race, tạo nhiều instances hoặc unsafe publication. Chọn một chiến lược safe publication/lazy initialization được kiểm chứng, không chỉ hy vọng first call sẽ tuần tự.

### 17.5. Cleanup

Một introduced field giữ connection, stream, listener hoặc executor cần explicit close/unregister. Một proxy wrapper không tự đóng target đúng lúc chỉ vì wrapper được GC. Với hot reload/classloader unload, registries phải xóa references tới class/method/proxy của module cũ.

## 18. Khi nào nên dùng introduction, khi nào không?

### 18.1. Những trường hợp có giá trị

- Một capability nhỏ, độc lập, áp dụng nhất quán cho nhiều types không cùng hierarchy.
- Tích hợp interface protocol `Tagged`, `Auditable`, `Identifiable` cho nhiều objects khi tool hỗ trợ và contract rõ.
- Code generation hoặc weaving làm giảm boilerplate cấu trúc lặp lại có ý nghĩa crosscutting.
- Một mô hình domain/legacy có nhiều targets mà extension thông qua composition hiện hành khó làm gọn.
- Test/debug tooling cần một capability phụ, nhưng không làm thay đổi nghiệp vụ cốt lõi.

### 18.2. Những trường hợp nên cân nhắc composition trước

- Chỉ mở rộng một hoặc hai classes.
- Có thể sửa trực tiếp source và API một cách rõ ràng.
- Field introduced giữ state phức tạp hoặc tài nguyên có vòng đời quan trọng.
- Method mới có logic nghiệp vụ lớn cần riêng dependency/service.
- Security policy mới đòi trusted boundary rõ.
- Build/weaving toolchain phức tạp hơn lợi ích tránh boilerplate.
- Runtime có nhiều classloaders/AOT/native constraints khiến generated structure khó ổn định.
- Consumers cần compile-time discoverability/refactoring thông thường.

### 18.3. Một quyết định thực dụng

Nếu mục tiêu là “mọi đối tượng của các loại này có thêm method để trả tag”:
1. Có thể định nghĩa interface `Tagged` và decorator không?
2. Có cần **target class thật** implements `Tagged`, hay caller dùng wrapper là đủ?
3. Caller đang dùng concrete classes hay interfaces?
4. State nằm ở target/proxy/registry và bao lâu?
5. Có cần thay đổi hàng nghìn class artifacts hay chỉ vài object wrappers?
6. Runtime/build tool thật sự hỗ trợ method/field/interface introduction mức nào?
7. Các tests về reflection, serialization, concurrency, security có đủ không?

Chỉ khi câu trả lời cho thấy lợi ích rõ, hãy chọn structural AOP introduction thay vì API/composition bình thường.

## 19. Ma trận kiểm thử sau khi introduce cấu trúc

| Ca kiểm thử | Điều phải xác nhận |
| --- | --- |
| **Interface visibility** | `instanceof IntroducedInterface` đúng trên object kỳ vọng. |
| **Original target** | Target gốc có hoặc không thay type theo cơ chế thực tế, không đoán. |
| **Callable methods** | Tất cả introduced abstract methods có implementation hợp lệ. |
| **Member reflection** | `getMethods/getDeclaredMethods/getDeclaredFields` khớp binary artifact. |
| **Compile-time client** | Consumer code compile với đúng toolchain và type view. |
| **Runtime binary** | Đúng transformed/generated class được nạp; không linkage failure. |
| **Target methods** | Existing return/exception/side effects giữ contract. |
| **Introduced state** | Defaults, nullability, persistence và mutations đúng. |
| **Two proxies one target** | Per-proxy vs per-target state rõ và test được. |
| **Multiple targets** | State không rò giữa instances không liên hệ. |
| **Method collision** | Duplicate declarations được xử lý rõ hoặc fail fast. |
| **Erasure** | Không có generic name clash, bridge/override đúng. |
| **Final/sealed/record** | Không giả định unsupported subtype generation. |
| **Object methods** | Equals/hashCode/toString có semantics hợp lệ. |
| **Self-invocation** | Introduced behavior và interception coverage không bị suy sai. |
| **Concurrency** | Safe initialization, reads/writes, per-target state. |
| **Error** | Exceptions được bảo toàn, cleanup thực hiện đúng. |
| **Serialization** | Round-trip/schema/state migration theo hợp đồng. |
| **Security** | API mới không bypass authorization hoặc lộ data. |
| **Hot reload** | Registry/classloader references được cleanup. |
| **Version upgrade** | Source/binary/behavioral contracts tiếp tục được test. |

### 19.1. So sánh reflection ở đúng nơi

Đừng test chỉ trên proxy rồi kết luận target class được weave. Với JDK proxy, test:
- `proxy instanceof Tagged` → true.
- `target instanceof Tagged` → false.
- `target.getClass().getDeclaredMethods()` không có `tag`.
- `proxy.getClass()` khác `target.getClass()`.

Với structural weaving engine, phải **test binary target thực sau weaving** theo cơ chế đó.

### 19.2. Negative test quan trọng

Cố gắng gọi method introduced khi:
- Không dùng đúng wrapper.
- Mixin thiếu initialization.
- Input null/invalid.
- Có hai aspects cùng trùng signature.
- Runtime nạp artifact sai version.
- Caller cast concrete subtype không tương thích.
- Concurrent threads cùng set state.
- Một advice khác short-circuit hoặc retry method introduced.

Đây là các đường dễ lỗi hơn happy path “getter trả đúng”.

### 19.3. Test theo hợp đồng, không theo mẹo runtime

Nếu tool hứa interface introduction, assert capability mà caller được công bố nhìn thấy. Không cố assert class name generated phải là một chuỗi cụ thể (proxy class names không phải API bền vững). Nếu binary weaving hứa field introduced, kiểm field/behavior trên artifact cuối thay vì chỉ xem source cũ.

## 20. Những hiểu lầm thường gặp

**“AOP nào cũng thêm field/method/interface được.”** Không. Nhiều engines chỉ có interception; structural introduction tùy tool.

**“Một JDK proxy implement interface mới nghĩa là class target đã đổi implements.”** Không. Chỉ proxy object có giao diện mới.

**“Có `tag()` qua proxy nghĩa là `Target.class` có declared method `tag`.”** Không nếu method được handler cung cấp.

**“Field trong handler là field introduced vào target.”** Không. Nó thuộc proxy handler.

**“Tạo subclass mới nghĩa là sửa field của base class.”** Không. Field mới thuộc subclass, không thay declaration base class.

**“Final class không thể tham gia bất kỳ AOP nào.”** Sai. Nó có thể được bọc qua interface hoặc được biến đổi theo khả năng công cụ thích hợp; chỉ không subclass bằng Java thông thường.

**“Records và sealed hierarchy không có ràng buộc khi introduce interfaces.”** Sai. Java type rules vẫn phải được tôn trọng.

**“Chỉ cần thêm implements thì mọi abstract method tự có logic.”** Không. Cần implementation/delegate/default method hợp lệ.

**“Hai generic method khác `List<String>` và `List<Integer>` chắc chắn không trùng.”** Sai do erasure.

**“Đặt aspect A trước B trong source là conflict resolver.”** Không có quy tắc chung ấy.

**“Một source client luôn nhìn thấy introduced method nếu runtime class đã weave.”** Không. Compile-time view/toolchain phải tương thích.

**“`equals` sẽ tự khiến proxy và target có identity giống nhau.”** Không. Toán tử `==` chỉ so references; equality policy phải được thiết kế.

**“State per-target mặc nhiên thread-safe.”** Không. Cùng target có thể nhận nhiều concurrent calls.

**“Introduction không ảnh hưởng serialization.”** Không được giả định. New fields/getters và proxy graph có thể đổi schema hoặc serialization behavior.

**“Không có read/write mới của field nên privacy không đổi.”** Sai. Public introduced API có thể làm lộ capabilities hoặc dữ liệu trước đó không truy cập được.

**“Thêm cấu trúc giúp mọi self-call đi qua advice.”** Không. Interception path vẫn tùy proxy/weaving semantics.

**“Tool biến đổi class đã load tùy ý.”** Không. Class redefinition/structural changes chịu giới hạn JVM và tool.

**“Một test proxy demo chứng minh mọi weaving engine giống vậy.”** Không. Chỉ kết luận trong mô hình được test.

## 21. Bài tập vận dụng và đáp án

### Câu 1 — Proxy hay target được thay?

`Reader target` không implements `Tagged`, `Reader proxy` được tạo với cả `Reader` và `Tagged`. Kết quả `proxy instanceof Tagged` true cho biết gì?

**Đáp án:** Proxy object có capability `Tagged`. Không thể kết luận target class đã có interface đó.

### Câu 2 — Hai proxies cùng target

P1 và P2 cùng delegate vào T, mỗi handler có field `tag` riêng. P1 set `"A"`, P2 set `"B"`. Tag nào thuộc T?

**Đáp án:** Theo mô hình ấy không có field tag trên T; P1/P2 giữ state riêng. Muốn per-target tag phải đổi owner/association.

### Câu 3 — Final target

`final class ReadOnlyStore implements Store`. Có thể tạo JDK interface proxy implements `Store` và `Tagged` không?

**Đáp án:** Có thể nếu các interfaces bình thường hợp lệ cho proxy và loader/visibility phù hợp. Final ngăn subclass của `ReadOnlyStore`, không ngăn object wrapper implement interfaces độc lập.

### Câu 4 — Method conflict

Target đã có `status()`; một aspect introduce method cùng signature nhưng nghĩa khác. Có được tự chọn implementation theo alphabet không?

**Đáp án:** Không nên. Cần conflict rule được công cụ hỗ trợ, ưu tiên fail fast/đổi API khi không thể xác định ngữ nghĩa.

### Câu 5 — Field location

`target.getClass().getDeclaredFields()` không thấy `tag` nhưng `((Tagged)proxy).tag()` trả được. Có mâu thuẫn không?

**Đáp án:** Không. Handler/registry có thể giữ tag mà target class không có field mới.

### Câu 6 — Compile-time vs runtime

Client `new Target().tag()` không compile trong javac thông thường, nhưng bản binary được weave ở runtime có `tag`. Vì sao?

**Đáp án:** Compiler không có declaration trong compile-time type view. Cần toolchain/artifact compile tương thích nếu muốn gọi method bằng static typing.

### Câu 7 — Generic name clash

Một class có hai methods `process(List<String>)` và `process(List<Integer>)`. Vì sao introduction đó không hợp lệ trong cùng Java class?

**Đáp án:** Hai signatures có cùng erasure `process(List)`, tạo name clash.

### Câu 8 — State concurrency

Một introduced field đếm updates bằng `count++`, cùng target được 100 threads gọi. Có đảm bảo count tăng 100 không?

**Đáp án:** Không; cần atomic/synchronization phù hợp. Introduction không tự đem lại thread safety.

### Câu 9 — Security

Một aspect introduce public method `resetState()` cho mọi domain object. Rủi ro?

**Đáp án:** Tăng attack surface; caller có capability có thể phá invariant nếu method không có authorization/validation. Phải xác định trusted boundary.

### Câu 10 — Binary mismatch

Client compile với class artifact đã weave có method `tag`, production lại load bản chưa weave. Điều gì có thể xảy ra?

**Đáp án:** Tùy call site, có thể lỗi linkage như `NoSuchMethodError` hoặc lỗi khác. Cần đồng bộ compile/runtime artifacts.

### Câu 11 — Serialization

Sau khi introduce field `lastAuditId` vào binary target, dữ liệu serialized cũ có thể cần xử lý gì?

**Đáp án:** Cần kiểm default/migration/schema/compatibility theo serialization mechanism, không giả định mọi round-trip giữ contract.

### Câu 12 — Mixin với async

Một introduced method `fetchAsync()` dùng future, advice quanh nó đóng resource ngay khi method return handle. Có đúng không?

**Đáp án:** Chưa chắc. Task có thể còn pending; resource lifecycle phải theo hợp đồng completion/ownership, không chỉ method return.

### Câu 13 — API hay introduction

Chỉ có một class cần thêm method `tag()` đơn giản, source có thể sửa. Nên nhất thiết dùng structural AOP?

**Đáp án:** Không. Mở rộng trực tiếp class hoặc dùng decorator có thể đơn giản, rõ type hơn và ít ràng buộc toolchain.

### Câu 14 — Reflection metadata

Một proxy implements interface `Tagged` có annotation trên method `tag`, nhưng matcher chỉ đọc annotations từ target implementation class. Có chắc matcher thấy không?

**Đáp án:** Không. Metadata lookup site và annotation retention/merging policy phải được xác định rõ.

## 22. Checklist trước khi bật một structural introduction

1. **Mục tiêu:** Thêm behavior tại join point hay thực sự cần thay đổi type shape?
2. **Nơi áp dụng:** Proxy, subclass generated, decorator, source hay bytecode weaving?
3. **Capability của tool:** Có hỗ trợ thêm method, field, interface hoặc parent relation đúng yêu cầu?
4. **Target identity:** Object nào có capability, wrapper hay target gốc?
5. **Compile view:** Compiler client có thấy introduced members không?
6. **Runtime artifact:** Production nạp đúng transformed class không?
7. **Type rules:** Final, record, sealed, visibility, constructors, generics/erasure?
8. **Conflict:** Duplicate methods/fields, default methods, bridge/overload resolution?
9. **Implementation:** Tất cả abstract interface methods được implement/delegate đúng?
10. **State owner:** Field/state nằm ở target, proxy, mixin hay registry?
11. **Initialization:** Giá trị mặc định/invariant đúng từ trước invocation đầu?
12. **Thread safety:** Per-target/per-proxy state có concurrent reads/writes không?
13. **Lifecycle:** Ai close/unregister/remove, khi nào target/proxy/module shutdown?
14. **Security:** New methods có làm lộ operation/dữ liệu không?
15. **Existing contract:** Original return/error/side effects có giữ?
16. **New contract:** Introduced API có tài liệu, nullability, failure semantics?
17. **Equality:** Identity, equals/hashCode/toString có chính sách?
18. **Reflection:** Annotations, declared methods/fields và classloader đúng?
19. **Serialization:** Schema, version, round-trip/migration?
20. **AOP coverage:** New methods có được những advice khác quan sát nếu cần?
21. **Ordering:** Structural conflicts và advice precedence có chính sách riêng?
22. **Async:** Introduced API trả futures/streams có giữ lifecycle?
23. **Testing:** Có build+runtime integration tests, positive và negative paths?
24. **Rollback:** Có thể tắt introduction mà không làm client binary phụ thuộc member mới lỗi?
25. **Maintainability:** Lợi ích crosscutting có lớn hơn complexity toolchain/debug không?

## Kết luận

**Bổ sung phương thức, thuộc tính hoặc giao diện** là một hình thức **thay đổi cấu trúc** trong những mô hình AOP có hỗ trợ introduction/inter-type declarations. Nhưng “có thêm khả năng” có nhiều mức: **proxy implement interface mới**, **subclass/generated wrapper có members mới**, hoặc **class artifact thật sự được biến đổi bằng weaving**. Các mức ấy không tương đương về `getClass()`, reflection, casts, binary compatibility, initialization và ownership.

Một thiết kế tốt xác định rõ **công cụ hỗ trợ loại thay đổi nào**, đối tượng nào sở hữu members/state mới, compiler và runtime có nhìn cùng type definition không, cách xử lý conflict/erasure/inheritance ra sao, và liệu các methods mới có bảo toàn hợp đồng, bảo mật, thread safety và lifecycle không. Ví dụ Java 17 cho thấy interface introduction bằng JDK proxy rất hữu ích khi chỉ cần mở rộng capability của wrapper, nhưng **không được gọi nhầm thành field/method được chèn vào target gốc**. Khi nhu cầu chỉ là một extension nhỏ, class/interface bình thường hoặc composition có thể đơn giản hơn; khi nhiều types thật sự cần một structural concern chung, introduction là công cụ mạnh nếu **được hỗ trợ, khai báo rõ và kiểm thử trên artifact cuối cùng**.

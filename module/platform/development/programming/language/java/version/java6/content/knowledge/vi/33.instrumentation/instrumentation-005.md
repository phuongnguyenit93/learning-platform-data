# isModifiableClass và kiểm tra khả năng JVM

## 1. Bài toán: class có thể sửa không đồng nghĩa JVM được phép sửa

Java Instrumentation là API chính thức trong module `java.instrument` để một **Java agent** quan sát hoặc biến đổi bytecode của classes khi được load hoặc khi đã load. Một công cụ profiler, coverage tool, monitoring agent, hot-reload tool hay framework có thể cần kiểm tra xem **class cụ thể** có đủ điều kiện retransform/redefine không. Nếu chỉ thử thao tác rồi xử lý lỗi tùy tiện, agent có thể làm hỏng startup, bỏ sót instrumented classes hoặc báo “thành công” dù JVM từ chối.

`java.lang.instrument.Instrumentation.isModifiableClass(Class<?>)` được giới thiệu từ **Java 6** và **vẫn hiện hành trong Java SE 26**. Phương thức hỏi một điều rất cụ thể: **JVM coi class này có thể được sửa định nghĩa thông qua retransformation hoặc redefinition không?** Nó **không** trả lời toàn bộ những câu hỏi sau:

- Agent có capability gọi `retransformClasses` không?
- Agent có capability gọi `redefineClasses` không?
- Bytecode biến đổi có hợp lệ hoặc vượt giới hạn structural changes không?
- Agent có thể mở package trong JPMS hoặc vượt mọi security boundary không?
- Một lần transformer chạy có thực sự làm thay đổi behavior không?
- Lớp đó có cần hoặc có nên sửa trong môi trường production không?

**Điểm cốt lõi theo Javadoc Oracle Java SE 26:** kết quả `isModifiableClass(c)` **độc lập** với kết quả `isRetransformClassesSupported()` và `isRedefineClassesSupported()`. Một JVM có thể trả **`isModifiableClass(MyClass.class)==true`** trong khi agent đang chạy **không được cấp quyền retransform hoặc redefine**. Trường hợp này được chứng minh bằng một demo dùng **hai agent JAR có manifest khác nhau**, cùng chạy trên OpenJDK 24, compile target Java 17.

### Mục tiêu học tập

Sau bài, bạn sẽ:

1. Hiểu `Instrumentation` được JVM cấp cho agent qua `premain` / `agentmain`, không phải tạo tùy ý bằng constructor.
2. Hiểu chính xác `isModifiableClass(Class<?>)` và các trường hợp **primitive**, **array**, **hidden class**, cùng `null`.
3. Phân biệt **class-level eligibility**, **JVM capability**, **agent manifest permission** và **valid bytecode transformation**.
4. Dùng `isRetransformClassesSupported()`, `isRedefineClassesSupported()`, `isNativeMethodPrefixSupported()` đúng ngữ cảnh.
5. Biết manifest `Can-Retransform-Classes` và `Can-Redefine-Classes` là những flags **được agent yêu cầu** và JVM có thể không hỗ trợ.
6. Hiểu `ClassFileTransformer`, `addTransformer(transformer,true)`, `retransformClasses`, `redefineClasses`, `ClassDefinition` và `removeTransformer`.
7. Tạo **startup Java agent** với `-javaagent`, compile/run bằng JDK 17+ và hai manifest profiles.
8. Biết lý do kiểm tra `isModifiableClass` chỉ là **preflight**, không thay xử lý `UnmodifiableClassException`, `UnsupportedOperationException` và các lỗi classfile khác.
9. Phân biệt `isModifiableModule` với `isModifiableClass` và phân biệt class visibility/module access với eligibility.
10. Hiểu `getAllLoadedClasses()` có thể chứa **hidden classes** và array classes nhưng **không có nghĩa tất cả modifiable**.
11. Thiết kế capability matrix, behavior tests, fail-closed / graceful degrade và cleanup an toàn cho agent hiện đại.
12. Không tự động nạp agent động hay biến đổi JDK/system classes trong production để “thử cho biết”.

~~~text
                       JVM chạy Java agent
                              |
                      premain(args, inst)
                              |
                              v
                      Instrumentation inst
                              |
          +-------------------+------------------+
          |                   |                  |
          v                   v                  v
 isModifiableClass(c)  isRetransform...   isRedefine...
    (class-level)       (capability)       (capability)
          |                   |                  |
          |          Manifest + JVM       Manifest + JVM
          |                   |                  |
          +-------------------+------------------+
                              |
                  Chọn đường phù hợp:
                              |
           +------------------+-------------------+
           |                                      |
  retransformClasses(c)                  redefineClasses(...)
   + transformer có                      + ClassDefinition
   quyền retransform
           |                                      |
           +------------------+-------------------+
                              |
               Bytecode/schema/verification
                   vẫn có thể thất bại
                              |
                 ghi nhận outcome thực tế
~~~

## 2. Instrumentation có từ đâu?

### 2.1. API thuộc module java.instrument

`Instrumentation` là interface `java.lang.instrument.Instrumentation` trong **module `java.instrument`**. Với ứng dụng chạy trên module path và cần tham chiếu API này từ một named module, có thể khai báo:

~~~java
module com.example.instrumentation.lab {
    requires java.instrument;
}
~~~

Đây là **đoạn trích `module-info.java`**, không phải một module runnable hoàn chỉnh. Với ví dụ classpath ở phần thực hành, không cần tự tạo module-info.java.

### 2.2. JVM truyền Instrumentation vào Java agent

~~~java
import java.lang.instrument.Instrumentation;

public final class MyAgent {
    public static void premain(String agentArgs, Instrumentation inst) {
        // JVM đã cấp Instrumentation cho agent ở startup.
    }
}
~~~

Đoạn trích. Khi JVM khởi chạy với `-javaagent:agent.jar` và manifest có `Premain-Class: MyAgent`, JVM tìm và gọi `premain` trước `main` của ứng dụng. Nếu agent startup sai nghiêm trọng, JVM có thể **không khởi chạy ứng dụng**.

`Instrumentation` **không có public constructor** để ứng dụng tạo bằng `new Instrumentation()`. Không sử dụng reflection, internal APIs hoặc giả lập Instrumentation ngoài module để vượt cơ chế cung cấp của JVM.

### 2.3. Startup agent và dynamic agent

Hai đường được package specification mô tả:

- **Startup:** `Premain-Class` + `-javaagent:agent.jar`; dễ audit/deploy và khuyến nghị cho ví dụ.
- **Attach khi JVM đang chạy (nếu implementation cho phép):** `Agent-Class` + `agentmain`; phụ thuộc chính sách runtime/Attach API, quyền và phiên bản JDK.

Từ JDK 21/JEP 451, tải agent động bị siết chặt để hướng tới **integrity by default**. Theo package specification Java SE 26, HotSpot sử dụng `-XX:+EnableDynamicAgentLoading` để opt-in cho dynamic loading trong running JVM. **Không lấy khả năng attach thành một giả định luôn đúng**; ví dụ bài này hoàn toàn chạy startup `-javaagent`, **không tự attach** vào process khác.

### 2.4. Manifest là một phần bắt buộc của ví dụ

~~~text
Manifest-Version: 1.0
Premain-Class: DemoAgent
Can-Retransform-Classes: true
Can-Redefine-Classes: true
~~~

Đây là **nội dung manifest mẫu**, không phải Java code. Hai dòng `Can-...` là yêu cầu capability cho agent; chỉ có `Premain-Class` vẫn có thể khởi chạy agent, nhưng **không tự cấp quyền retransform/redefine**. JVM còn phải thực sự hỗ trợ capability đó.

### 2.5. Java agents có quyền nhạy cảm

Một agent có thể nhìn thấy nhiều classes và classfile bytes, thay đổi logic và đo runtime. Do đó:
- Chỉ deploy agent JAR được kiểm soát nguồn gốc, chữ ký/hash và code review.
- Không tải arbitrary agent từ request input.
- Không nhúng bí mật vào manifest/agentArgs một cách vô ý.
- Không dùng agent để tắt kiểm tra chứng chỉ, sửa sandbox hoặc can thiệp integrity.
- Nếu dùng monitoring agent, giữ scope transformations và sampling có giới hạn.
- Tách code demo khỏi production runtime.

## 3. isModifiableClass(Class<?>) nói gì — và không nói gì?

### 3.1. Hợp đồng API

~~~java
boolean eligible = instrumentation.isModifiableClass(MyService.class);
~~~

Đây là **đoạn trích**, `instrumentation` được JVM cấp và `MyService` là class ứng dụng. `true` nghĩa là JVM coi class đó là **modifiable bằng redefinition hoặc retransformation về mặt class**. Kết quả **không phụ thuộc** vào hai booleans `isRetransformClassesSupported` / `isRedefineClassesSupported`.

Javadoc quy định:
- `isModifiableClass(null)` ném **`NullPointerException`**.
- Primitive classes (ví dụ `int.class` / `Integer.TYPE`) **không modifiable**.
- Array classes (ví dụ `String[].class`, `int[].class`) **không modifiable**.
- Một số classes khác có thể bị JVM/provider coi là nonmodifiable; đừng giả định mọi named class đều true.

### 3.2. Cùng một class, hai agent có thể có quyền khác nhau

Giả sử trên JVM đang chạy:

~~~text
isModifiableClass(Target.class)        = true
isRetransformClassesSupported()         = false
isRedefineClassesSupported()            = false
~~~

Đây là **tổ hợp hợp lệ**. Nó không mâu thuẫn: class có thể được sửa về mặt loại class, nhưng agent **chưa được capability** thực hiện operation. Demo thực tế cuối bài ghi đúng ba giá trị này với manifest tắt capabilities.

### 3.3. Vì sao tên method dễ gây hiểu nhầm?

Tên `isModifiableClass` nghe giống “có thể sửa ngay”, nhưng thực chất nên đọc như:

> “Class `C` có đủ điều kiện về bản thân class để retransform/redefine hay không?”

Để thực hiện một operation thực tế, cần **ít nhất bốn điều kiện**:

1. Agent đã có `Instrumentation` từ JVM.
2. JVM + agent configuration có capability operation tương ứng.
3. Class cụ thể `isModifiableClass(C)==true`.
4. Bytecode transformation hợp lệ trong giới hạn JVM TI, không gây format/linkage/schema problem.

Ngoài ra còn security/operational controls và sự an toàn của transformation. Chỉ đạt 1–3 vẫn **không** là “sửa chắc chắn thành công”.

### 3.4. Giá trị true không đồng nghĩa “có thể sửa mọi thứ”

Một ordinary class `Target` trả true **không bảo đảm** có thể:
- thêm/xóa fields/methods tùy tiện;
- thay đổi superclass hoặc implemented interfaces;
- đổi tên field/method, descriptors hay modifier không được VM cho phép;
- thay một classfile bằng bytes không hợp lệ;
- biến application classes thành members của module khác;
- sửa finality/identity ngoài các ràng buộc JVM TI;
- phá classloader linkage hoặc signature constraints;
- có ngay behavior mới trên những active stack frames đang thực thi version cũ.

Các thay đổi hỗ trợ phụ thuộc giới hạn retransform/redefine của JVM và JVM TI. Demo chỉ **retransform không thay bytes** và **redefine bằng class bytes gốc**, nhằm minh họa capability mà không rủi ro đổi behavior.

## 4. Ba kiểm tra phải được đặt cạnh nhau

Một agent thường kiểm tra:

~~~java
boolean classEligible = inst.isModifiableClass(targetClass);
boolean canRetransform = inst.isRetransformClassesSupported();
boolean canRedefine = inst.isRedefineClassesSupported();
~~~

Đây là đoạn trích. Mỗi kết quả có **một phạm vi** riêng:

| Kiểm tra | Phạm vi | Điều kiện chính | Không có nghĩa |
| --- | --- | --- | --- |
| `isModifiableClass(c)` | Class cụ thể | VM cho phép class được sửa loại này | Agent có quyền gọi operation |
| `isRetransformClassesSupported()` | JVM + agent config | Manifest yêu cầu + VM supports retransform | Mọi class đều modifiable |
| `isRedefineClassesSupported()` | JVM + agent config | Manifest yêu cầu + VM supports redefine | Bytecode nào cũng hợp lệ |
| `isNativeMethodPrefixSupported()` | JVM + agent config | Capability native prefix được bật và supported | Có quyền retransform/redefine |
| `isModifiableModule(module)` | Module cụ thể | Module có thể thay đổi qua `redefineModule` | Class trong module luôn modifiable |

### 4.1. Quy tắc cho retransformation

~~~java
if (!inst.isRetransformClassesSupported()) {
    // Báo thiếu capability; không gọi addTransformer(t, true).
} else if (!inst.isModifiableClass(Target.class)) {
    // Class không đủ điều kiện, không thử retransform.
} else {
    inst.retransformClasses(Target.class);
}
~~~

**Đoạn trích**, `Target`/`inst` đã được khai báo. Khi thực hiện **phải tiếp tục xử lý exceptions** vì checks không guarantee success. Không viết `if(inst.isModifiableClass(c)) inst.retransformClasses(c)` mà bỏ qua retransform capability.

### 4.2. Quy tắc cho redefinition

~~~java
if (inst.isRedefineClassesSupported()
        && inst.isModifiableClass(Target.class)) {
    inst.redefineClasses(new ClassDefinition(Target.class, replacementBytes));
}
~~~

**Đoạn trích**, `replacementBytes` là classfile bytes đã chuẩn bị/validate, cùng binary name với Target, và `ClassDefinition` thuộc `java.lang.instrument`. Đừng dùng `redefineClasses` khi chỉ có bytes tùy ý từ external requests. Nếu muốn xử lý thay đổi có cấu trúc (new fields/methods), cần hiểu **giới hạn JVM TI** thay vì giả định hot swap bất kỳ.

### 4.3. Capability và eligibility độc lập

| Class eligible? | Agent retransformation supported? | Có thể gọi retransform? | Kết luận |
| --- | --- | --- | --- |
| false | false | Không | Hai lớp điều kiện đều thiếu |
| false | true | Không | Class không được sửa dù agent có capability |
| true | false | Không | **Class eligible, agent chưa có capability** |
| true | true | Có thể thử, vẫn phải xử lý lỗi | Bytecode/VM constraints có thể từ chối |

Tương tự với redefinition: ghép `isModifiableClass` với `isRedefineClassesSupported`. **Không có logic “true OR true”**: muốn sử dụng một operation phải đạt cả capability và class eligibility của operation đó.

### 4.4. Có quyền redefine không suy ra có quyền retransform

Manifest `Can-Redefine-Classes: true` và `Can-Retransform-Classes: false` có thể tạo ra agent chỉ dùng được redefinition, không đăng ký transformer retransformation-capable. Hai capabilities là hai lựa chọn **riêng**, có thể bật một hoặc cả hai hoặc không cái nào.

### 4.5. Test agent flags trên JVM thực tế

Những booleans capability thường ổn định trong một lần JVM instantiation theo Javadoc, nên có thể kiểm tra và lập capability report ở `premain` hoặc startup. Nhưng không hardcode expected result trên mọi vendor, JVM mode, image jlink, managed runtime hay agent configuration. Test manifest + JVM đang chạy và chỉ sử dụng functionality thực sự supported.

## 5. Các class không thể sửa: primitive, array và hidden

### 5.1. Primitive và array: quy tắc xác định

~~~java
boolean a = inst.isModifiableClass(int.class);       // false
boolean b = inst.isModifiableClass(String[].class);  // false
boolean c = inst.isModifiableClass(int[][].class);   // false
~~~

**Đoạn trích**. Primitive và array classes **không modifiable**, bất kể manifest hoặc JVM retransform/redefine flags. Không thể “đổi array layout” hay “instrument primitive class” qua Java Instrumentation API.

### 5.2. Hidden classes từ Java hiện đại

Java có **hidden classes**, ví dụ từ `MethodHandles.Lookup.defineHiddenClass` (API chính thức từ Java 15). Chúng thường dùng cho runtime-generated implementation artifacts và không có binary name có thể discover/resolve như ordinary classes. Theo JVM TI rules, **hidden classes không retransform/redefine được**; trên OpenJDK 24 đã kiểm thử, `inst.isModifiableClass(hiddenClass)` trả false.

~~~java
Class<?> hidden = MethodHandles.lookup()
    .defineHiddenClass(templateBytes, true)
    .lookupClass();

boolean hiddenClassFlag = hidden.isHidden();
boolean modifiable = inst.isModifiableClass(hidden);
~~~

**Đoạn trích**, `templateBytes` phải là bytes của class hợp lệ cùng package với lookup class, và các biến/permissions phải sẵn. Demo có file `HiddenTemplate.class` làm byte source để không cần bytecode-generation library.

### 5.3. Vì sao getAllLoadedClasses có hidden nhưng không modifiable?

`Instrumentation.getAllLoadedClasses()` trả cả **hidden classes/interfaces** và **array classes** theo Javadoc, nhưng `isModifiableClass` vẫn có thể trả false cho chúng. **“Đang loaded” khác “eligible để sửa”.** Đừng làm vòng lặp `for (Class<?> c : inst.getAllLoadedClasses()) inst.retransformClasses(c)`: nhiều phần tử không modifiable, có thể bao gồm platform internals.

~~~java
for (Class<?> c : inst.getAllLoadedClasses()) {
    if (!c.isPrimitive() && !c.isArray()
            && !c.isHidden()
            && inst.isModifiableClass(c)) {
        // Vẫn phải chọn allowlisted target và capability phù hợp.
    }
}
~~~

**Đoạn trích**, không nên dùng vòng lặp này để tự động transform mọi eligible class. Nó chỉ cho thấy một số checks; còn phải lọc scope theo package/classloader/module và tránh agents/JDK/system classes không thuộc mục tiêu.

### 5.4. getInitiatedClasses khác getAllLoadedClasses

`getInitiatedClasses(loader)` trả những classes mà loader có thể tìm bằng class name/linkage; **không bao gồm hidden classes** và array có hidden element type theo Javadoc Java 26. Một agent không được suy rằng class vắng khỏi `getInitiatedClasses` thì nó chưa loaded. Điều này quan trọng khi debug tooling của frameworks dùng dynamic generated/hidden classes.

### 5.5. Null argument có contract rõ

~~~java
try {
    inst.isModifiableClass(null);
    throw new AssertionError("Expected NullPointerException");
} catch (NullPointerException expected) {
    // Đúng theo API contract.
}
~~~

**Đoạn trích**. Nếu đầu vào từ dynamic class discovery, kiểm tra null trước và quyết định lý do skip; đừng catch NPE toàn bộ pipeline khiến lỗi lập trình khó tìm.

## 6. Retransform khác redefine thế nào?

### 6.1. Retransformation: chạy lại chuỗi transformers

`retransformClasses(Class<?>... classes)` yêu cầu JVM lấy lại class definition/bytes gốc theo contract và áp các transformers theo quy tắc:

1. Bắt đầu từ classfile bytes ban đầu hoặc bytes từ definition có sẵn phù hợp.
2. Transformers **đã đăng ký nhưng không capable retransformation** có những kết quả transformations trước được **tái sử dụng**, không nhất thiết gọi transform method lại.
3. Transformers đã đăng ký với `canRetransform=true` được JVM gọi lại khi retransform.
4. JVM kiểm tra/verify/install bytes kết quả theo giới hạn class transformations.

~~~java
inst.addTransformer(transformer, true);
try {
    inst.retransformClasses(Target.class);
} finally {
    inst.removeTransformer(transformer);
}
~~~

**Đoạn trích**. Cần kiểm tra `isRetransformClassesSupported` và `isModifiableClass(Target.class)` trước. `transformer` phải trả bytes hợp lệ hoặc **`null`** để không đổi classfile. Cleanup transformer là yêu cầu lifecycle tốt; dù đã remove, có thể còn transform invocations đang chạy do concurrent class loading, nên transformer phải thread-safe/defensive.

### 6.2. Redefinition: truyền classfile bytes thay thế

`redefineClasses(new ClassDefinition(Target.class, bytes))` dùng một definition byte array cụ thể, phù hợp khi muốn thay class definition có kiểm soát. Nếu bytes gốc đã có sẵn và bạn chỉ muốn quan sát pipeline, retransform thường phù hợp hơn. Trong demo, redefinition bằng **chính bytes gốc được compile** để kiểm tra capability mà không thực hiện thay đổi hành vi.

### 6.3. Structural changes bị giới hạn

Những giới hạn có thể gồm cấm thay đổi:
- tên/descriptor methods và fields;
- modifiers;
- inheritance hierarchy;
- thêm/xóa fields hoặc methods;
- một số class attributes hoặc references.

Chi tiết phụ thuộc JVM TI và JDK implementation; đừng viết một hot reload tool cho schema changes mà giả định Java Instrumentation hỗ trợ mọi thay đổi. `isModifiableClass==true` **không bảo đảm** `redefineClasses` với bytes thay đổi cấu trúc sẽ thành công.

### 6.4. Behavior của active stack frames

Nếu một method có frames đang chạy vào lúc retransform/redefine, những frames đó có thể tiếp tục dùng **bytecodes phiên bản cũ**, còn invocations mới thấy method mới. Không nên mong thay đổi atomically business semantics trên tất cả đang chạy requests.

### 6.5. Static state và object instances

Redefinition/retransformation **không tự chạy lại class initializers** và không reset giá trị static variables theo ý muốn. Existing objects vẫn là instances của class đó. Vì thế hot-swap code không thay một migration dữ liệu, object state hoặc database schema migration.

### 6.6. Nếu một batch lỗi

Javadoc mô tả khi retransform/redefine thất bại, operation theo batch không install phần thành công ở nửa chừng như một kiểu “best effort”. Tuy nhiên một agent có nhiều transformers/side effects khác (logging, metrics, external writes) vẫn phải quản lý chúng; không coi mọi hành động application-level là rollback tự động.

## 7. ClassFileTransformer: cách viết đúng trong Java 17+

`ClassFileTransformer` có các method signatures liên quan Java modules. Java 9+ cung cấp overload có `Module module`; overload năm tham số cũ vẫn dùng được và nhận callbacks qua default forwarding. Bài demo override **bản năm tham số** tương thích Java 17:

~~~java
ClassFileTransformer transformer = new ClassFileTransformer() {
    @Override
    public byte[] transform(ClassLoader loader, String className,
            Class<?> classBeingRedefined, ProtectionDomain domain,
            byte[] classfileBuffer) {
        if ("CapabilityProbeApp$Target".equals(className)
                && classBeingRedefined == Target.class) {
            calls.incrementAndGet();
        }
        return null; // Không sửa bytes.
    }
};
~~~

Đây là **đoạn trích**, cần imports `java.lang.instrument.ClassFileTransformer`, `java.security.ProtectionDomain` và `java.util.concurrent.atomic.AtomicInteger`; `calls` và `Target` được định nghĩa trong chương trình hoàn chỉnh.

### 7.1. Vì sao trả null?

Theo contract, transformer trả `null` để báo **không thực hiện thay đổi**. Nó không có nghĩa class bị từ chối load hoặc callback thất bại. Trong bài, ta chỉ đếm callback khi retransform class mục tiêu, không tạo/patched bytecode nguy hiểm.

### 7.2. classBeingRedefined dùng làm gì?

Trong class load lần đầu, `classBeingRedefined` thường là `null`. Trong retransform/redefine của class đã có, JVM có thể đưa reference class cụ thể. Demo lọc cả binary/internal class name `CapabilityProbeApp$Target` và reference `Target.class` để tránh count những classes khác.

### 7.3. Method có Module từ Java 9

~~~java
@Override
public byte[] transform(Module module, ClassLoader loader,
        String className, Class<?> classBeingRedefined,
        ProtectionDomain domain, byte[] classfileBuffer) {
    return null;
}
~~~

Đây là **đoạn trích**, để override version sáu tham số trong custom transformer. Nó giúp agent có module context, nhưng **không tự mở private packages**. Trong Java 17+, class transformer interface cung cấp default implementations, vì vậy không nên mặc định nó là một functional interface và viết lambda mà chưa kiểm tra API thực tế. Demo dùng anonymous classes, đã biên dịch và chạy thành công.

### 7.4. canRetransform flag được phân biệt tại registration

~~~java
inst.addTransformer(transformer);        // Không capable retransformation.
inst.addTransformer(transformer2, true); // Yêu cầu capable retransformation.
~~~

Hai đoạn chỉ minh họa. Dòng thứ hai có thể ném **`UnsupportedOperationException`** khi agent/JVM không có capability, bất kể `isModifiableClass(Target.class)` là true. Với transformer không cần retransform, đừng yêu cầu true chỉ để “cho chắc”.

### 7.5. Thực tế callback có thể xảy ra đồng thời

JVM class loading/retransformation có thể gọi transformer trên nhiều threads. Những callback nên nhanh, thread-safe, tránh recursion/classloading cycles và tránh gọi APIs gây deadlock trong transform. Một agent đo class transformations có thể dùng `AtomicInteger` hoặc bounded counters, không log mọi class ở production.

## 8. Lab Java 17+: hai agent JAR, hai chế độ capability

Bài lab không cần thư viện ngoài JDK. Nó gồm ba file Java:
1. **`DemoAgent.java`**: agent startup nhận `Instrumentation` qua `premain`.
2. **`HiddenTemplate.java`**: class nhỏ dùng để tạo hidden class trong test.
3. **`CapabilityProbeApp.java`**: kiểm thử capability matrix, class eligibility, hidden/array/primitive, transformer callback và thao tác retransform/redefine.

Ta tạo **hai agent JAR từ cùng DemoAgent.class**, chỉ khác **manifest**:
- `agent-enabled.jar` yêu cầu `Can-Retransform-Classes: true` và `Can-Redefine-Classes: true`.
- `agent-disabled.jar` đặt cả hai về false.

Cả hai đều khởi chạy bằng **`-javaagent`**, không dynamic attach. Trên **OpenJDK 24** đã kiểm thử, ứng dụng `Target` **modifiable trong cả hai run**, nhưng run disabled **không được thực hiện retransform/redefine**. Đây là khác biệt quan trọng nhất của bài.

**Giới hạn môi trường:** mã compile theo `--release 17`; kết quả exact stdout được xác nhận trên OpenJDK 24. Với JDK/vendor không hỗ trợ một capability, chương trình assert có thể báo FAIL theo chủ ý; đó là **phát hiện sự khác nhau của môi trường**, không phải lý do tự bật các JVM internals hay sửa manifest mà không đánh giá.

### 8.1. File DemoAgent.java

~~~java
import java.lang.instrument.Instrumentation;

public final class DemoAgent {
    private static volatile Instrumentation instrumentation;

    public static void premain(String args, Instrumentation inst) {
        instrumentation = inst;
        System.out.println("agent-premain=true");
    }

    public static Instrumentation requireInstrumentation() {
        Instrumentation result = instrumentation;
        if (result == null) {
            throw new IllegalStateException("Run with -javaagent");
        }
        return result;
    }
}
~~~

**Giải thích:** JVM gọi `premain` trước application `main`, lưu reference đã được cấp vào static volatile field. `volatile` thể hiện publication semantics nếu reference được dùng giữa threads. Ví dụ đặt reference để học tập; production agents thường có lifecycle/config design riêng và không expose Instrumentation tùy tiện cho untrusted code.

### 8.2. File HiddenTemplate.java

~~~java
public final class HiddenTemplate {
    public static int number() {
        return 7;
    }
}
~~~

**Giải thích:** Đây là bytecode nguồn cho `MethodHandles.lookup().defineHiddenClass`. Nó không chứa logic instrumentation và không cần classfile-generation tools; `getResourceAsStream("/HiddenTemplate.class")` sẽ đọc bytes compile từ classpath. Hidden class tạo ra chỉ để kiểm tra `Class.isHidden` và `isModifiableClass`.

### 8.3. File CapabilityProbeApp.java

~~~java
import java.io.InputStream;
import java.lang.instrument.*;
import java.lang.invoke.MethodHandles;
import java.security.ProtectionDomain;
import java.util.Arrays;
import java.util.concurrent.atomic.AtomicInteger;

public final class CapabilityProbeApp {
    static final class Target {
        static String message() {
            return "unchanged";
        }
    }

    static void check(boolean okay, String reason) {
        if (!okay) throw new AssertionError(reason);
    }

    static byte[] originalBytes(String resource) throws Exception {
        try (InputStream in = CapabilityProbeApp.class.getResourceAsStream(resource)) {
            if (in == null) throw new IllegalStateException("Missing: " + resource);
            return in.readAllBytes();
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1 || !Arrays.asList("enabled", "disabled").contains(args[0])) {
            throw new IllegalArgumentException("Usage: CapabilityProbeApp enabled|disabled");
        }
        boolean expectedEnabled = args[0].equals("enabled");
        Instrumentation inst = DemoAgent.requireInstrumentation();
        boolean retransformation = inst.isRetransformClassesSupported();
        boolean redefinition = inst.isRedefineClassesSupported();
        boolean targetModifiable = inst.isModifiableClass(Target.class);
        boolean primitiveModifiable = inst.isModifiableClass(int.class);
        boolean arrayModifiable = inst.isModifiableClass(String[].class);
        Class<?> hidden = MethodHandles.lookup()
                .defineHiddenClass(originalBytes("/HiddenTemplate.class"), true)
                .lookupClass();
        boolean hiddenModifiable = inst.isModifiableClass(hidden);
        boolean loadedHidden = Arrays.asList(inst.getAllLoadedClasses()).contains(hidden);
        boolean nullRejected = false;
        try {
            inst.isModifiableClass(null);
        } catch (NullPointerException expected) {
            nullRejected = true;
        }

        check(retransformation == expectedEnabled, "manifest retransformation");
        check(redefinition == expectedEnabled, "manifest redefinition");
        check(targetModifiable, "ordinary class should be modifiable on this JVM");
        check(!primitiveModifiable && !arrayModifiable, "primitives/arrays");
        check(hidden.isHidden() && !hiddenModifiable, "hidden class");
        check(loadedHidden, "all-loaded should include hidden");
        check(nullRejected, "null must fail");

        System.out.println("mode=" + args[0]);
        System.out.println("can-retransform=" + retransformation);
        System.out.println("can-redefine=" + redefinition);
        System.out.println("target-modifiable=" + targetModifiable);
        System.out.println("primitive-modifiable=" + primitiveModifiable);
        System.out.println("array-modifiable=" + arrayModifiable);
        System.out.println("hidden-is-hidden=" + hidden.isHidden());
        System.out.println("hidden-modifiable=" + hiddenModifiable);
        System.out.println("all-loaded-includes-hidden=" + loadedHidden);
        System.out.println("null-class-rejected=" + nullRejected);

        byte[] bytes = originalBytes("/CapabilityProbeApp$Target.class");
        if (retransformation && redefinition && targetModifiable) {
            AtomicInteger calls = new AtomicInteger();
            ClassFileTransformer transformer = new ClassFileTransformer() {
                @Override
                public byte[] transform(ClassLoader loader, String className,
                        Class<?> classBeingRedefined, ProtectionDomain domain,
                        byte[] classfileBuffer) {
                    if ("CapabilityProbeApp$Target".equals(className)
                            && classBeingRedefined == Target.class) {
                        calls.incrementAndGet();
                    }
                    return null;
                }
            };
            inst.addTransformer(transformer, true);
            try {
                inst.retransformClasses(Target.class);
            } finally {
                check(inst.removeTransformer(transformer), "remove transformer");
            }
            check(calls.get() >= 1, "transform callback not invoked");
            inst.redefineClasses(new ClassDefinition(Target.class, bytes));
            check("unchanged".equals(Target.message()), "unexpected method change");
            System.out.println("retransform-callback-observed=true");
            System.out.println("retransform-done=true");
            System.out.println("redefine-done=true");
            System.out.println("target-method-preserved=true");
        } else {
            boolean addRejected = false;
            try {
                inst.addTransformer(new ClassFileTransformer() { }, true);
            } catch (UnsupportedOperationException expected) {
                addRejected = true;
            }
            boolean retransformRejected = false;
            try {
                inst.retransformClasses(Target.class);
            } catch (UnsupportedOperationException expected) {
                retransformRejected = true;
            }
            boolean redefineRejected = false;
            try {
                inst.redefineClasses(new ClassDefinition(Target.class, bytes));
            } catch (UnsupportedOperationException expected) {
                redefineRejected = true;
            }
            check(addRejected && retransformRejected && redefineRejected,
                    "missing capability must reject operations");
            check("unchanged".equals(Target.message()), "method should not change");
            System.out.println("add-retransform-transformer-rejected=" + addRejected);
            System.out.println("retransform-rejected=" + retransformRejected);
            System.out.println("redefine-rejected=" + redefineRejected);
            System.out.println("target-method-preserved=true");
        }
        System.out.println("tests=PASS");
    }
}
~~~

**Giải thích code:** `Target.message()` trả `"unchanged"`. Nhánh enabled đăng ký transformer capable retransform, callback đếm đúng class mục tiêu và trả `null` (không đổi bytes); sau đó redefine bằng original bytes. Nhánh disabled **cố tình thử ba thao tác không được cấp** trong test isolated để assert `UnsupportedOperationException`. Trong production, **không cần cố ném exception để dò capability**: dùng capability checks và xử lý lỗi theo policy.

### 8.4. Hai manifest files

**enabled.mf:**

~~~text
Manifest-Version: 1.0
Premain-Class: DemoAgent
Can-Retransform-Classes: true
Can-Redefine-Classes: true
~~~

**disabled.mf:**

~~~text
Manifest-Version: 1.0
Premain-Class: DemoAgent
Can-Retransform-Classes: false
Can-Redefine-Classes: false
~~~

Lưu các tệp manifest với **một dòng trống kết thúc** để bảo đảm JAR parser đọc đủ main attributes. `Can-...` là agent requests; nếu JVM không hỗ trợ capability thì `is...Supported()` vẫn có thể false dù manifest là true.

### 8.5. Compile và đóng gói bằng JDK tools

Trên terminal bash/Linux/macOS, trong thư mục chứa ba file Java và hai manifests:

~~~bash
mkdir -p classes
javac -encoding UTF-8 --release 17 -d classes DemoAgent.java HiddenTemplate.java CapabilityProbeApp.java
jar --create --file agent-enabled.jar --manifest enabled.mf -C classes DemoAgent.class
jar --create --file agent-disabled.jar --manifest disabled.mf -C classes DemoAgent.class
java -javaagent:agent-enabled.jar -cp classes CapabilityProbeApp enabled
java -javaagent:agent-disabled.jar -cp classes CapabilityProbeApp disabled
~~~

Trên **PowerShell**:

~~~powershell
New-Item -ItemType Directory -Force -Path classes | Out-Null
javac -encoding UTF-8 --release 17 -d classes DemoAgent.java HiddenTemplate.java CapabilityProbeApp.java
jar --create --file agent-enabled.jar --manifest enabled.mf -C classes DemoAgent.class
jar --create --file agent-disabled.jar --manifest disabled.mf -C classes DemoAgent.class
java "-javaagent:agent-enabled.jar" -cp classes CapabilityProbeApp enabled
java "-javaagent:agent-disabled.jar" -cp classes CapabilityProbeApp disabled
~~~

**Kỹ thuật lưu ý:** JVM nạp agent class từ JAR khi startup. Application có thể tham chiếu `DemoAgent` vì compiled `DemoAgent.class` có trong `-cp classes` của ví dụ. Hai JAR đóng gói **chỉ** agent class, không chứa application business classes. Dùng `jar --create --manifest` (JDK 17+) và kiểm tra file manifest đúng path. Trên cả hai môi trường cần tạo manifests **trước khi chạy lệnh đóng JAR**. Không cần external network hay third-party dependencies.

### 8.6. Stdout chính xác — capability enabled

Đã chạy trên **OpenJDK 24**, compile target **Java 17**:

~~~text
agent-premain=true
mode=enabled
can-retransform=true
can-redefine=true
target-modifiable=true
primitive-modifiable=false
array-modifiable=false
hidden-is-hidden=true
hidden-modifiable=false
all-loaded-includes-hidden=true
null-class-rejected=true
retransform-callback-observed=true
retransform-done=true
redefine-done=true
target-method-preserved=true
tests=PASS
~~~

Đây là một **run test thực tế**; không diễn giải nó thành bảo đảm các vendor/JVM tương lai phải trả đúng tất cả flags, nhất là `target-modifiable`, `Can-...Supported` của runtime khác.

### 8.7. Stdout chính xác — capability disabled

~~~text
agent-premain=true
mode=disabled
can-retransform=false
can-redefine=false
target-modifiable=true
primitive-modifiable=false
array-modifiable=false
hidden-is-hidden=true
hidden-modifiable=false
all-loaded-includes-hidden=true
null-class-rejected=true
add-retransform-transformer-rejected=true
retransform-rejected=true
redefine-rejected=true
target-method-preserved=true
tests=PASS
~~~

**Kết quả then chốt:** **`target-modifiable=true` ở cả hai runs**, nhưng với manifest disabled thì `retransformClasses`, `redefineClasses` và `addTransformer(t,true)` đều bị từ chối. Điều này khớp trực tiếp với Javadoc: class-level eligibility **không** bị quyết định bởi quyền agent.

### 8.8. Đọc ý nghĩa từng nhóm output

| Output | Điều được chứng minh |
| --- | --- |
| `agent-premain=true` | Agent đã được JVM gọi ở startup |
| `can-retransform/can-redefine` | Capability thực tại trên JVM + manifest profile |
| `target-modifiable=true` | Ordinary Target eligible trên OpenJDK 24 trong cả hai runs |
| `primitive-modifiable=false` | `int.class` không sửa được |
| `array-modifiable=false` | `String[].class` không sửa được |
| `hidden-is-hidden=true` | Class được tạo qua defineHiddenClass thật sự hidden |
| `hidden-modifiable=false` | Hidden class không retransform/redefine được trong JVM test |
| `all-loaded-includes-hidden=true` | getAllLoadedClasses có thể liệt kê hidden, không đồng nghĩa modifiable |
| `null-class-rejected=true` | isModifiableClass(null) ném NPE |
| `retransform-callback-observed=true` | Có transformer capable nhận callback trên Target |
| `redefine-done=true` | redefineClasses original bytes thành công khi có capability |
| `target-method-preserved=true` | Demo không làm thay đổi behavior method |
| `...-rejected=true` | Agent không có capability bị từ chối chính xác |
| `tests=PASS` | Mọi assertions trong fixture này đạt |

### 8.9. Bài không thay bytecode nghiệp vụ

Mục đích là **kiểm tra khả năng**. Transformer trả null, redefinition dùng đúng bytes compiled, không cài bytecode injected. Không dùng file này như một mẫu production agent để thay đổi hệ thống trong lúc có requests; chỉ dùng để hiểu contracts và các check cần thiết.

### 8.10. Tại sao test cần hai agent JAR?

Nếu chỉ chạy một manifest enabled, bạn sẽ thấy `modifiable=true` và `canRetransform=true` rồi dễ suy sai rằng chúng liên quan nguyên nhân trực tiếp. Đổi **duy nhất capability manifest** mà giữ nguyên class, JVM và source chứng minh tính độc lập: `modifiable` vẫn true trong disabled profile, còn operation permissions thay đổi. Đây là một **controlled experiment**, không phải lý thuyết suy diễn.

## 9. Những trường hợp false và exception phải phân biệt

### 9.1. isModifiableClass returns false

Đây là class-level result, ví dụ primitive/array/hidden hoặc JVM-specific class. Không nên thử retransform/redefine để “kiểm tra lại bằng may rủi” trên production. Nếu class bắt buộc cho tính năng, báo unsupported target; nếu optional, skip với reason.

### 9.2. isRetransformClassesSupported returns false

Đây là capability của JVM configuration **cho agent**. `addTransformer(t,true)` và `retransformClasses(...)` có thể ném `UnsupportedOperationException`. Việc đổi `isModifiableClass` không thể tạo lại capability. Cần sửa manifest/deployment (nếu được duyệt) hoặc chọn chế độ instrumentation khác.

### 9.3. isRedefineClassesSupported returns false

`redefineClasses(...)` bị `UnsupportedOperationException` dù class có thể eligible. Muốn redefinition, JVM phải hỗ trợ và agent manifest phải yêu cầu `Can-Redefine-Classes: true`, cùng giới hạn classfile.

### 9.4. UnmodifiableClassException

`retransformClasses` và `redefineClasses` có thể ném `UnmodifiableClassException` khi class cụ thể **không thể sửa**. Một preflight `isModifiableClass(c)==false` đủ để không thử với known unsupported targets, nhưng một operation thực tế vẫn phải xử lý exceptions; state/runtime support có thể phụ thuộc JVM và từng class.

### 9.5. UnsupportedOperationException

Có thể xuất hiện vì:
- Agent/JVM không cho retransform/redefine.
- `addTransformer(transformer,true)` được gọi khi unsupported.
- Transformation cố thay đổi những cấu trúc classfile bị VM cấm.

Cùng một exception class có thể phản ánh nguyên nhân khác nhau; log operation name, manifest profile, capability booleans, class identity và error context thay vì chỉ in `"not supported"` chung chung.

### 9.6. ClassFormatError và LinkageError

Ngay cả khi capabilities true, classfile bytes mới có thể:
- sai định dạng;
- không khớp binary class name;
- dùng classfile version không được JVM hỗ trợ;
- có circularities/linkage errors;
- vi phạm verification/constraints.

Đừng catch hết `Throwable` rồi coi như đã instrument. Với startup agent, lỗi ở transformation paths cần được xử lý có kiểm soát: tùy ứng dụng, **fail startup** nếu instrumentation bảo mật bắt buộc, hoặc **degrade/log rõ** nếu profiling chỉ optional. Không sửa bytecode một cách tùy tiện để bỏ qua verifier.

### 9.7. NullPointerException khi truyền null

`isModifiableClass(null)` ném NPE, điều này nói về caller bug/input validation. Không nên dùng null như sentinel “class không modifiable”; giữ trạng thái **class chưa resolve** khác với **class đã resolve nhưng không modifiable**.

## 10. Bốn tầng kiểm tra nên đưa vào thiết kế agent

Một pipeline production thường cần tách:

**Tầng 1 — Agent environment:**
- JDK version/vendor/protocol module options;
- agent được load qua `premain`;
- JAR manifest chứa đúng capabilities;
- có `Instrumentation` instance;
- trusted agent policy được triển khai.

**Tầng 2 — Operation capability:**
- `isRetransformClassesSupported`;
- `isRedefineClassesSupported`;
- `isNativeMethodPrefixSupported` chỉ nếu agent thực sự dùng native prefix;
- `isModifiableModule` nếu cần thay module relationships.

**Tầng 3 — Target class eligibility:**
- class đã loaded hoặc được load ở thời điểm có thể transform;
- không phải primitive/array/hidden;
- `isModifiableClass(c)` true;
- module/package/classloader allowlist;
- không instrument agent classes hoặc JDK internals nếu không được duyệt.

**Tầng 4 — Operation and validation:**
- classfile transformation đúng;
- callbacks thực sự chạy khi cần;
- verification/linkage/installation thành công;
- no unintended behavior changes;
- performance/baseline comparison sau triển khai.

Không nên viết một method `supportsInstrumentation()` boolean rồi dùng nó thay cho từng điều kiện. Có thể một agent **load-time transform** classes dù không có retransformation capability, và có thể **modifiable class** nhưng operation đang chọn không được cho phép.

### 10.1. Mẫu kết quả capability report

~~~text
agentLoaded=true
javaRuntimeVersion=...
jvmVendor=...
retransformSupported=true|false
redefineSupported=true|false
nativeMethodPrefixSupported=true|false
targetClass=com.example.service.Worker
targetClassLoader=...
targetModule=...
targetModifiable=true|false
targetIsHidden=false
targetIsArray=false
operation=retransform|redefine|load-time-only
decision=allow|skip|reject
reason=...
~~~

Đây là **mẫu dữ liệu báo cáo**, không phải stdout của demo. Không bịa các giá trị runtime thực tế hoặc log user/classpath secrets; thông tin classloader/module có thể nhạy cảm.

### 10.2. Không lấy `getAllLoadedClasses` làm target allowlist

Một agent kiểm tra loaded classes nên có **target packages/classes rõ ràng**; `getAllLoadedClasses` có thể trả hàng nghìn classes, hidden/array/platform classes. Không iterate và retransform tất cả. Nếu muốn instrument app classes, dùng classloader/module/class name filters, tránh recursion và bootstrap internals.

### 10.3. Class đã loaded so với class load mới

Nếu thiếu retransform capability nhưng agent vẫn có thể đăng ký non-retransform transformer với `addTransformer(t)`, agent có thể xử lý **future class definitions**. Nhưng đã loaded class sẽ không được “chạy lại transformation” chỉ bằng việc đăng ký transformer mới. Nếu feature bắt buộc instrument classes đã loaded, phải yêu cầu capability tương ứng hoặc nêu hạn chế.

### 10.4. Mỗi operation có cách degrade khác nhau

- Profiling optional: có thể skip class và đánh dấu coverage gap rõ.
- Security agent bắt buộc: nếu missing capability/target class, startup nên fail closed theo policy.
- Hot reload developer tool: báo unsupported method/class changes thay vì giả vờ cập nhật code.
- Observability: lựa chọn JFR/metrics/tracing thay vì cố instrument JDK internals nếu capability thiếu.

## 11. Named modules và isModifiableModule

### 11.1. isModifiableModule là kiểm tra khác

`Instrumentation.isModifiableModule(Module module)` nói về khả năng thay đổi **module graph** bằng `redefineModule(...)`, ví dụ mở/export packages hoặc thêm reads theo quy tắc API. Nó **không** cho biết các classes trong module đó đều modifiable.

~~~java
Module module = Target.class.getModule();
boolean moduleEditable = inst.isModifiableModule(module);
boolean classEditable = inst.isModifiableClass(Target.class);
~~~

**Đoạn trích**. Hai kết quả có phạm vi khác nhau. Một module có thể cho phép mở package nhưng class cụ thể vẫn không sửa được; hoặc class modifiable mà module access của instrumentation helper chưa đầy đủ.

### 11.2. Không dùng redefineModule để phá encapsulation tùy tiện

`redefineModule` có thể mở thêm module reads/exports/opens; nó không phải nút tắt mọi bảo vệ của JVM. Việc mở internal packages có thể làm tăng quyền truy cập; chỉ làm trong agent được tin cậy, có security review. Không khuyến nghị dùng `--add-opens=ALL-UNNAMED` hàng loạt chỉ để một lab compile.

### 11.3. ClassLoader identity cũng quan trọng

Hai classes có cùng binary name nhưng do **hai ClassLoaders khác nhau** định nghĩa là hai runtime classes khác nhau. Agent lọc chỉ theo `className` dễ transform nhầm implementation của plugin, test sandbox hoặc application tenant. Để an toàn, kết hợp package/classloader/module/`ProtectionDomain` và chỉ target classes có ownership rõ ràng.

### 11.4. Hidden classes và framework-generated code

Một framework có thể tạo hidden classes/lambdas/runtime implementation. `getAllLoadedClasses` có thể thấy chúng nhưng không sửa được. Khi muốn instrument framework-generated behavior, nên chọn **ordinary parent/entry classes** hoặc load-time hooks có contract chính thức, không cố biến hidden class thành modifiable.

## 12. Hạn chế và rủi ro khi ghi bytecode mới

### 12.1. “Class modifiable” không chứng minh biến đổi hợp lệ

Một phương thức code instrumentation có thể thêm bytecodes để đo latency, nhưng có thể gây:
- verifier failures;
- stack map frames sai;
- method size tăng quá giới hạn;
- performance overhead;
- deadlocks khi instrumentation gọi ngược vào code bị instrument;
- classloading circularities;
- mất tương thích với agent khác;
- thay đổi timing và gây heisenbugs.

Vì vậy test với no-op transformer trước như demo, sau đó mới thêm transformer thực dưới test isolation và regression suite.

### 12.2. Không gắn instrumentation vào mọi lớp thư viện

Một agent có thể làm ứng dụng chậm đáng kể hoặc crash nếu instrument:
- class loading infrastructure;
- agent/helper classes chính nó;
- concurrency primitives/GC-sensitive paths;
- JVM classes có hạn chế, module/package access phức tạp;
- classes khác đã bị agent bên thứ ba instrument.

Không coi `isModifiableClass(String.class)==true` (nếu JVM trả thế) là lời khuyên “sửa java.lang.String”. Chỉ dùng allowlist đã được thiết kế.

### 12.3. Thứ tự transformers và việc loại bỏ

Nhiều transformers có thể cùng hoạt động; retransform có quy tắc reapply/re-execute khác nhau cho những transformers capable/non-capable. `removeTransformer(t)` **không** bảo đảm callback đã đang chạy được hủy tức khắc: tài liệu cho phép concurrent calls đến sau khi remove. Đảm bảo transformer thread-safe và không giữ references làm classloader leak.

### 12.4. Timing của redefinition và active frames

Một method đang được thread thực hiện có thể tiếp tục chạy old bytecodes sau redefinition; method mới được dùng trong lần gọi sau. Do vậy không triển khai một hotfix bảo mật với giả định active requests đổi ngay lập tức. Kết hợp controlled deployment, synchronization, rollback và service-level validation.

## 13. Troubleshooting theo từng tín hiệu

| Tín hiệu/lỗi | Giải thích khả dĩ | Cách xử lý |
| --- | --- | --- |
| Agent không có `Instrumentation` | Không chạy bằng `-javaagent`, manifest sai | Kiểm tra JAR manifest/startup command |
| `premain` không được gọi | JVM chưa load agent hoặc startup thất bại | Kiểm tra Premain-Class, classpath, stderr |
| `isModifiableClass(int.class)==false` | Primitive không modifiable | Không thử sửa primitive |
| `isModifiableClass(String[].class)==false` | Arrays không modifiable | Không biến array class thành target |
| Hidden class modifiable=false | Hidden classes không retransform/redefine | Instrument host/ordinary classes hoặc load-time path |
| Target modifiable=true, retransform=false | Class eligible nhưng thiếu capability | Manifest + JVM support; không thử retransform |
| `addTransformer(t,true)` UOE | Can-Retransform-Classes thiếu/VM không hỗ trợ | Check capability; dùng non-retransform transformer nếu đủ |
| `retransformClasses` UOE | Operation unsupported hoặc thay đổi không được phép | Check supported flag và transformer output |
| `redefineClasses` UOE | Operation unsupported hoặc schema update unsupported | Kiểm tra manifest/VM bytecode restrictions |
| `UnmodifiableClassException` | Target class không modifiable | Skip/reject class, không retry mù |
| `ClassFormatError` | Transformer xuất bytes hỏng | Validate instrumentation bytecode |
| `NoClassDefFoundError` | New bytes sai class binary name | Dùng đúng compiled class definition |
| `UnsupportedClassVersionError` | Classfile vượt JVM target | Compile đúng `--release` |
| `ClassCircularityError` | Class-loading cycle | Sửa transformer dependencies/ordering |
| `LinkageError` | Linkage/verification issue | Tái tạo trong isolated JVM, kiểm tra affected classloader |
| `NullPointerException` ở isModifiableClass | Passed null class | Validate resolved target |
| `isModifiableModule` true nhưng class false | Module and class are different concepts | Check cả hai riêng |
| Hidden class có trong getAllLoadedClasses | Loaded != modifiable | Lọc `Class.isHidden` và capability |
| Transformer callback không được gọi khi retransform | Registered non-capable transformer, sai class filter | Kiểm tra addTransformer(t,true), support và target |
| Callback đếm nhiều hơn dự kiến | Concurrency/other events/classloads | Dùng stable counters, filter đúng identity |
| JVM chạy nhưng code không đổi sau redefine | Redefine dùng original bytes hoặc active frames cũ | Kiểm tra expected classfile bytes và scope |
| Java agent động cảnh báo/bị cấm | Integrity-by-default/Attach policy | Ưu tiên startup -javaagent, cấu hình bởi admin |
| Nhiều agents gây conflict | Competing transformers, order/race | Scope, transformer ownership, regression tests |
| Module access failure | Named module encapsulation | Chỉ mở chính xác packages khi được phê duyệt |

### 13.1. Không dùng exception như capability discovery chính

Một helper có thể gọi `isModifiableClass`, `isRetransformClassesSupported` và `isRedefineClassesSupported` trước. Tuy nhiên vẫn phải catch/propagate lỗi thực tế ở `retransformClasses`/`redefineClasses`. **Preflight giúp tránh lỗi đoán trước; exceptions là final operational evidence**, không nên đảo ngược thành “cứ gọi thử để xem có được không”.

### 13.2. Startup fail-fast hay skip?

Nếu instrumentation là điều kiện bắt buộc để thực thi security/trace contract, missing capability phải làm **startup thất bại có thông báo rõ**. Nếu instrumentation chỉ bổ sung profiling, có thể degrade bằng cách skip có metrics/health signal. Không gán “success=true” khi công cụ bị thiếu target coverage.

### 13.3. Khi class modifiable=false và không có alternative

Không cố bypass JVM bằng reflection/private native access. Báo class name/module/classloader, loại class (primitive/array/hidden), capabilities và lý do; nếu nghiệp vụ cần quan sát behavior, xem JFR/management APIs hoặc instrumentation tại điểm vào khác có support.

## 14. Checklist QA cho agent trước production

| Kiểm tra | Kết quả kỳ vọng |
| --- | --- |
| Manifest có Premain-Class | JVM gọi premain ở startup |
| Agent startup được tin cậy | Source/JAR hash/permissions kiểm soát |
| Can-Retransform-Classes true + JVM support | `isRetransformClassesSupported()==true` |
| Can-Retransform-Classes false | Capability có thể false mặc dù Target modifiable |
| Can-Redefine-Classes true + JVM support | `isRedefineClassesSupported()==true` |
| Can-Redefine-Classes false | redefine operation bị từ chối |
| Ordinary Target trên JVM test | isModifiableClass được đo, không suy từ flag |
| Primitive class | false |
| Array class | false |
| Hidden class | false trên JVM test và theo JVMTI constraints |
| null argument | NPE |
| getAllLoadedClasses | Có thể chứa hidden/arrays |
| getInitiatedClasses | Không chứa hidden classes |
| addTransformer(t,true) khi unsupported | UOE |
| retransformClasses when unsupported | UOE |
| redefineClasses when unsupported | UOE |
| addTransformer(t,true) khi supported | Có thể đăng ký transformer |
| retransformClasses valid target | Callback observed |
| Transformer trả null | Class bytes giữ nguyên |
| removeTransformer | Chấm dứt registration, handles late callbacks |
| redefineClasses với original bytes | Operation thành công khi support |
| Method behavior sau demo | Không đổi |
| Class changed schema | Unsupported errors được xử lý, không gây deploy surprise |
| Module/package access | Không mở rộng tùy tiện |
| ClassLoader filtering | Tránh classes sai module/loader |
| Enabled vs disabled manifests | In ra capability matrix khác nhau |
| JDK 17/21/26 vendor variations | Test trong target JVM thực |
| Build reproducibility | Agent JAR/manifest và classfile source traceable |
| CI startup errors | Fail rõ, không nuốt stderr |
| Dynamic attach policy | Không giả định luôn bật |
| Security review | Agent không tiết lộ secrets, không remote arbitrary code injection |
| Performance | Transformer overhead, classloading latency được đo |
| Cleanup | Transformers/resources không leak |
| Observability | Capability report và skip reasons đầy đủ |
| Rollback | Có cách disable agent/roll back version |
| Production scope | Chỉ allowlisted classes được instrument |

### 14.1. Test negative không chỉ test positive

Một test chỉ chạy `agent-enabled.jar` và assert retransform thành công **không chứng minh** code xử lý thiếu quyền đúng. Vì vậy bài còn chạy `agent-disabled.jar` và assert:
- target vẫn modifiable;
- capability booleans false;
- `addTransformer(t,true)` bị từ chối;
- retransform bị từ chối;
- redefine bị từ chối.

Đây là cách kiểm tra chính xác tính **độc lập** của `isModifiableClass` với configuration-level capabilities.

### 14.2. Không dùng production app làm test harness

Bài demo build/run trong một thư mục tạm và JAR agent riêng, không sửa repository. Production instrumentation có thể ảnh hưởng toàn JVM, nên phải có integration test, separate staging, feature/rollback control, performance baseline và chỉ bật sau khi security review.

## 15. Câu hỏi tự đánh giá

**1.** `Instrumentation.isModifiableClass(Class<?>)` có từ Java nào và còn được dùng không?

**Đáp án:** Từ Java 6, vẫn có trong Java SE 26; hỏi class eligibility cho retransform/redefine.

**2.** `isModifiableClass(Target.class)==true` có bảo đảm `retransformClasses(Target.class)` thành công không?

**Đáp án:** Không. Còn cần retransformation capability, valid target, hợp lệ về bytecode/JVM restrictions.

**3.** Kết quả `isModifiableClass` có bị quyết định bởi `isRetransformClassesSupported` không?

**Đáp án:** Không; Javadoc khẳng định độc lập.

**4.** Vì sao agent disabled có target-modifiable=true?

**Đáp án:** Target class eligible theo JVM nhưng agent thiếu retransform/redefine capability do manifest false.

**5.** Primitive classes có modifiable không?

**Đáp án:** Không, ví dụ `int.class`.

**6.** Array classes có modifiable không?

**Đáp án:** Không, ví dụ `String[].class`.

**7.** Hidden class có thể xuất hiện trong `getAllLoadedClasses` dù không modifiable không?

**Đáp án:** Có. Loaded class enumeration và modifiability là hai khái niệm khác nhau.

**8.** `getInitiatedClasses` có bao gồm hidden classes không?

**Đáp án:** Không theo Javadoc, vì hidden classes không được discover by name qua classloader.

**9.** `isModifiableClass(null)` trả false hay ném exception?

**Đáp án:** Ném `NullPointerException`.

**10.** Agent yêu cầu retransformation capability ở đâu?

**Đáp án:** Manifest `Can-Retransform-Classes: true`, và JVM phải hỗ trợ.

**11.** Nếu manifest true nhưng JVM không hỗ trợ capability?

**Đáp án:** `isRetransformClassesSupported()` vẫn false; không được gọi operation.

**12.** Có thể gọi `addTransformer(t,true)` khi retransform capability false không?

**Đáp án:** Không; có thể ném `UnsupportedOperationException`.

**13.** `return null` từ transformer nghĩa là gì?

**Đáp án:** Không thay đổi classfile bytes trong callback đó, không phải lỗi load.

**14.** Retransform và redefine khác nhau ở điểm nào?

**Đáp án:** Retransform chạy/reapply transformer pipeline trên existing definition; redefine đưa classfile bytes thay thế qua ClassDefinition.

**15.** Vì sao demo redefine bằng original bytes?

**Đáp án:** Để kiểm tra quyền redefinition mà không thay đổi business behavior.

**16.** `isModifiableModule` có thể thay `isModifiableClass` không?

**Đáp án:** Không; module-level graph change khác với class bytecode eligibility.

**17.** Có nên retransform tất cả classes trong `getAllLoadedClasses()`?

**Đáp án:** Không. Có primitive/arrays/hidden/platform classes, security/performance risks và targets ngoài allowlist.

**18.** Vì sao loaded Target.class trong hai classloaders cần xử lý khác nhau?

**Đáp án:** Cùng binary name không đồng nghĩa cùng runtime class; phải lọc loader/module.

**19.** Agent nào nên chạy bằng `-javaagent`?

**Đáp án:** Startup agent được kiểm soát; bài demo dùng cách này, không yêu cầu dynamic attach.

**20.** Agent có quyền retransform có được phép thêm method tùy ý vào loaded class không?

**Đáp án:** Không bảo đảm. JVM TI/hot swap có structural limitations.

**21.** Khi preflight true nhưng runtime ném `UnmodifiableClassException`, có nên catch rồi coi success không?

**Đáp án:** Không. Ghi fail reason, skip/reject theo policy; không che lỗi.

**22.** Vì sao cần dọn `removeTransformer`?

**Đáp án:** Để ngừng đăng ký callback khi không cần, giảm overhead/leaks; vẫn phải thiết kế defensive trước callbacks concurrent.

**23.** Trong Java 17, có nên luôn viết `ClassFileTransformer` như lambda không?

**Đáp án:** Không mặc định functional interface; ví dụ đã dùng anonymous class với override method để compile/run đúng.

**24.** Production agent có thể làm lộ bí mật không?

**Đáp án:** Có; nó chạy với quyền nhạy cảm, cần trust, code review, kiểm soát target, logging và deploy.

### Bài tập thực hành

1. Chạy hai manifests enabled/disabled, giải thích tại sao Target.modifiable không đổi.
2. Thay `Target.class` thành `int.class` và xác nhận modifiable=false.
3. Thay bằng `String[].class`, assert false.
4. Tạo hidden class từ HiddenTemplate.class rồi kiểm tra `isHidden()` và `isModifiableClass`.
5. Gọi `isModifiableClass(null)` trong test isolated, xác nhận NPE.
6. Thử manifest chỉ `Can-Retransform-Classes:true`, `Can-Redefine-Classes:false`; đánh giá capability matrix.
7. Thử manifest chỉ redefine true, retransform false; không gọi `addTransformer(t,true)`.
8. Bỏ `Premain-Class` trong một JAR test, quan sát startup error (không dùng production JVM).
9. Đăng ký transformer capable retransformation, đếm callbacks trên đúng Target class.
10. Đổi transformer trả null thành transformer kiểm tra SHA-256 bytes và vẫn trả null; không sửa bytes.
11. Dùng `removeTransformer` trong finally và test lifecycle.
12. Thử `getAllLoadedClasses()`, thống kê primitive/array/hidden/nonmodifiable theo target JVM, không transform các classes đó.
13. So `getInitiatedClasses(ClassLoader)` với `getAllLoadedClasses` khi có hidden class.
14. Đổi Target class sang một class của JDK (chỉ **đọc check**) và giải thích vì sao không nên instrument ngẫu nhiên.
15. Dùng `isModifiableModule(Target.class.getModule())` và `isModifiableClass(Target.class)`, so scopes.
16. Thử một class target ở named module rồi thiết kế module access rules đúng, không mở toàn bộ packages.
17. Viết wrapper `CapabilityDecision` record ghi supported/eligible/operation/skip reason.
18. Viết integration test khi missing capability thì agent báo unsupported thay vì gọi operation.
19. Viết test disabled agent `addTransformer(t,true)` ném UnsupportedOperationException.
20. Test redefinition original bytes và bảo đảm method output không đổi.
21. Đọc JVM TI restrictions rồi liệt kê vì sao adding/removing methods không phải một supported hot swap bình thường.
22. Chạy trên JDK 17 và JDK 21/26 nếu có, so output theo vendor/config thực, không hardcode booleans.
23. Đo startup cost agent khi transformer theo package allowlist so với no-op.
24. Thiết kế JAR trust/signature/hash review và canary rollout cho production agent.
25. Viết runbook khi một instrumentation agent gây ClassFormatError hoặc LinkageError: disable/rollback, điều tra transformer, không chấp nhận partial coverage mù.
26. Chỉ ra một use case nên dùng JFR/JMX thay vì sửa bytecode đã loaded.
27. Giải thích lý do dynamic attach cần policy riêng, và vì sao startup -javaagent thuận tiện cho kiểm thử.
28. Viết negative test cố gắng redefining một class array trong process test riêng; xử lý UnmodifiableClassException mà không crash CI.
29. Tạo two custom classloaders cùng load binary name và ghi nhận class identity khác nhau.
30. Thử test transformer callback multi-threaded classloading với bounded counters và không log mọi class.

## 16. Nguồn tham khảo chính thức, vẫn áp dụng

- [Oracle Java SE 26 — Instrumentation](https://docs.oracle.com/en/java/javase/26/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): **isModifiableClass** và độc lập capability; retransform/redefine/addTransformer; getAllLoadedClasses, isModifiableModule.
- [Oracle Java SE 26 — java.lang.instrument package](https://docs.oracle.com/en/java/javase/26/docs/api/java.instrument/java/lang/instrument/package-summary.html): `Premain-Class`, agent startup/dynamic loading, `Can-Retransform-Classes` và `Can-Redefine-Classes` manifest.
- [Oracle Java SE 26 — ClassFileTransformer](https://docs.oracle.com/en/java/javase/26/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): callback methods, order, null-return semantics, Java module overload.
- [Oracle Java SE 26 — ClassDefinition](https://docs.oracle.com/en/java/javase/26/docs/api/java.instrument/java/lang/instrument/ClassDefinition.html): class + replacement byte array.
- [Oracle Java SE 26 — UnmodifiableClassException](https://docs.oracle.com/en/java/javase/26/docs/api/java.instrument/java/lang/instrument/UnmodifiableClassException.html): unavailable target class.
- [Oracle Java SE 26 — MethodHandles.Lookup](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): defineHiddenClass Java 15+.
- [Oracle Java SE 26 — Class.isHidden](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Class.html#isHidden()): hidden class marker.
- [Oracle Java SE 26 — Module](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Module.html): Java platform module behavior.
- [Oracle Java SE 26 — ClassLoader](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/ClassLoader.html): class identity/loader behavior.
- [Oracle Java SE 26 — ProtectionDomain](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/ProtectionDomain.html): code source/security context.
- [Oracle Java SE 26 — Jar Tool](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jar.html): tạo agent JAR/manifest.
- [Oracle Java SE 26 — Java Launcher](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html): `-javaagent` JVM startup option.
- [Oracle Java SE 26 — java.base Module](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/module-summary.html): module system, classes runtime.
- [Oracle Java SE 17 — Instrumentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): Java17 source/target API availability.
- [Oracle Java SE 17 — ClassFileTransformer](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): Java17 transformer API.
- [Oracle Java SE 17 — MethodHandles.Lookup](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): hidden-class API in JDK17.
- [OpenJDK — JEP 451: Prepare to Disallow the Dynamic Loading of Agents](https://openjdk.org/jeps/451): integrity-by-default and dynamic agent-loading policy.
- [JVM Tool Interface — RedefineClasses / RetransformClasses](https://docs.oracle.com/javase/8/docs/platform/jvmti/jvmti.html): historical API name/contracts còn được tham chiếu; dùng **JDK hiện hành/JVMTI runtime specification** cho giới hạn chi tiết khi triển khai, không làm theo các workaround legacy.

**Ghi nhớ:** `isModifiableClass(Class<?>)` là **kiểm tra điều kiện của một class**, không phải quyền thực hiện mọi modification. Muốn `retransformClasses`, **đồng thời** cần `isRetransformClassesSupported()==true` và class eligible; muốn `redefineClasses` cần `isRedefineClassesSupported()==true` và class eligible. Primitive/array classes không modifiable, hidden classes cũng không retransform/redefine trên JVM hiện đại. Manifest và JVM hỗ trợ quyết định operation capabilities; bytecode/structural constraints quyết định thao tác thực tế có thành công không. Hai JAR agent đã kiểm chứng trường hợp rất quan trọng: **class modifiable=true ngay cả khi cả hai capabilities=false**. Đừng bỏ qua bước này khi viết Java instrumentation agents còn được dùng hiện nay.

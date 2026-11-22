# Kiểm thử bridge, synthetic, lambda, record, sealed class và nhiều class loader

Trong Java Instrumentation, một `ClassFileTransformer` không chỉ gặp các class và method “bình thường” do lập trình viên viết. Compiler và JVM có thể sinh **bridge methods**, **synthetic members**, các cấu trúc hỗ trợ **lambda**, **record classes**, **sealed hierarchies** và những class **trùng binary name nhưng do các class loader khác nhau định nghĩa**. Nếu transformer chỉ được thử trên một POJO đơn giản, nó có thể vô tình đo trùng method, bỏ sót lambda body, làm hỏng metadata của record/sealed class, hoặc gộp sai danh tính class trong nhiều loader.

Bài này thuộc chủ đề **Kiểm thử và chẩn đoán** của Java Advance — Instrumentation. Mục tiêu là lập **bộ kiểm thử có thể tái lập**, quan sát cả bytecode và hành vi runtime, rồi xác nhận agent xử lý đúng các trường hợp đặc biệt. Ta sẽ biên dịch **Java 17+**, dùng reflection, `javap -v`, một **Java agent thật** và hai **class loader tùy biến**. Bộ ví dụ đã được biên dịch bằng `javac --release 17` và chạy thành công trên JDK 24.

**Nguyên tắc bao trùm:** kiểm thử cả ba lớp thông tin — **source/compile-time structure**, **class-file metadata**, và **runtime identity/behavior**. Không suy luận rằng tên method do compiler tạo ra luôn cố định; không suy luận hai class cùng tên là một class; không coi callback của transformer là bằng chứng bytecode đã bị chỉnh sửa nếu transformer chỉ trả `null`.

## 1. Ma trận rủi ro cần được bao phủ

| Kiểu đặc biệt | Dấu hiệu cần phát hiện | Rủi ro khi instrument | Điều cần kiểm chứng |
| --- | --- | --- | --- |
| **Bridge method** | `Method.isBridge()`; `ACC_BRIDGE`, thường kèm `ACC_SYNTHETIC` | Đo cả bridge lẫn method thật gây double-count; đổi nhầm descriptor | Erased call và typed call vẫn dispatch đúng |
| **Synthetic method/member** | `Member.isSynthetic()`; `ACC_SYNTHETIC` | Loại hết synthetic có thể bỏ sót compiler-generated code cần thiết | Chính sách include/exclude có chủ đích |
| **Lambda expression** | `invokedynamic`, method `lambda$...` ở một số trình biên dịch, runtime lambda class | Giả định proxy lambda luôn là class bình thường và modifiable | Behavior đúng; nếu hidden thì xử lý theo khả năng JVM |
| **Record** | `Class.isRecord()`, `Record` attribute, record components | Đổi cấu trúc component/constructor hoặc metadata bị verifier/JVM từ chối | Reflection components và accessor/result không đổi ngoài thay đổi có chủ ý |
| **Sealed class/interface** | `Class.isSealed()`, `PermittedSubclasses` attribute | Xóa/sửa permitted hierarchy không hợp lệ khi retransform/redefine | Permits list và subtype dispatch chính xác |
| **Nhiều class loader** | Cùng `Class.getName()` nhưng khác `Class<?>`/loader identity | Cache theo tên làm gộp nhầm classes, transformer chọn sai target | Hai definitions được phân biệt và nhận callbacks riêng |
| **Retransform đặc biệt** | `classBeingRedefined != null`, capability/modify checks | Cố retransform class không modifiable hoặc thêm schema | Class được chọn vẫn hoạt động, callback xuất hiện đúng phạm vi |

Bộ test cần có **negative-path checks** (những class buộc bỏ qua), không chỉ happy path. Mỗi dòng trong ma trận gắn với một kỹ thuật quan sát: reflection, `javap`, `Instrumentation.isModifiableClass`, callback log, identity comparison hoặc phép gọi method thật.

## 2. Phân biệt “do compiler sinh” và “do runtime sinh”

Java có hai thời điểm tạo cấu trúc đặc biệt:

1. **Khi biên dịch:** `javac` có thể sinh bridge method cho generic overriding, sinh synthetic method làm implementation body của lambda, và xuất record/sealed metadata vào class file.
2. **Khi chạy:** JVM/`LambdaMetafactory` có thể tạo lớp hiện thực một functional interface; class loader có thể define cùng binary name nhiều lần dưới các defining loaders khác nhau; agent có thể retransform các class đã load.

Không phải mọi compiler/JVM đều dùng cùng tên synthetic methods hoặc cùng cơ chế lambda proxy. Ví dụ `lambda$supplier$0` là một **mẫu tên javac thường dùng**, không phải một phương thức Java source có hợp đồng tên công khai cho mọi compiler. Khi kiểm thử tính đúng của instrumentation, ưu tiên flags/descriptors/semantics; chỉ assert một mẫu tên cụ thể nếu build **đã cố định compiler và version**.

### Ba mức assert

| Mức | Ví dụ | Mức độ portable |
| --- | --- | --- |
| **Behavior** | `((Base<String>) service).convert("hi")` trả `"HI"` | Gắn với ngữ nghĩa Java mà test định nghĩa |
| **Reflection metadata** | `bridge.isBridge()`, `Event.class.isRecord()`, `Shape.class.isSealed()` | API Java tiêu chuẩn, áp dụng theo class đã biên dịch |
| **Compiler/JVM detail** | Method mang tên `lambda$...`, proxy lambda có `isHidden()==true` | Phụ thuộc compiler/runtime, cần test theo matrix |

Trong bộ demo, chúng ta cố định `javac --release 17` và một runtime JDK 24, vì vậy có thể ghi **stdout chính xác** của lần chạy đó. Ở JVM/Java compiler khác, phần test về tên và hidden lambda proxy nên được kiểm tra bằng chính kết quả runtime, không gán bừa một giá trị chắc chắn.

## 3. Bridge method: generic override cần kiểm thử hai đường gọi

Xét một lớp generic:

~~~java
abstract class Base<T> {
    public abstract T convert(T input);
}

final class StringService extends Base<String> {
    @Override
    public String convert(String input) {
        return input.toUpperCase(java.util.Locale.ROOT);
    }
}
~~~

Đây là **mảnh source minh họa**, cũng là một phần của `Cases.java` trong demo hoàn chỉnh. Khi `T` bị **type erasure**, method trong `Base<T>` có JVM descriptor tương đương:

~~~text
convert(Ljava/lang/Object;)Ljava/lang/Object;
~~~

Còn implementation có chữ ký:

~~~text
convert(Ljava/lang/String;)Ljava/lang/String;
~~~

Để giữ overriding/polymorphism qua erased signature, `javac` sinh một **bridge method** tương đương logic:

~~~java
// Pseudocode: compiler-generated bridge, KHÔNG khai báo trong Java source.
public Object convert(Object input) {
    return convert((String) input);
}
~~~

Bridge có descriptor erased `(Object)Object`, trong khi method do lập trình viên viết nhận/trả `String`. Ở class file do `javac` sinh, bridge thường có cả `ACC_BRIDGE` và `ACC_SYNTHETIC`.

### Trường hợp gây double counting

Giả sử instrumentation chèn một counter ở **đầu mọi method** tên `convert` mà không xét descriptor/flags:

~~~text
((Base<String>) service).convert("hi")
        |
        v
StringService.convert(Object) [bridge] -> counter +1
        |
        v
StringService.convert(String) [implementation] -> counter +1
        |
        v
"HI"
~~~

Với **một lời gọi nghiệp vụ**, counter có thể thành 2. Đây không phải lỗi `LongAdder` hay lỗi JVM; đây là lỗi **chính sách chọn methods**.

Phương án có thể hợp lệ:

- **Method-level business metrics:** chỉ instrument implementation, bỏ bridge; ghi rõ lý do.
- **Bytecode-call metrics:** đo cả bridge và implementation nếu thực sự muốn biết số lần vào mỗi method body riêng.
- **Boundary tracing:** instrument entrypoint với quy tắc dedup theo một logical invocation.
- **Validation:** assert `Method.isBridge()`/descriptor, số probe được tạo và hành vi call qua generic reference.

**Không bỏ mọi synthetic method một cách mù quáng**: bridge thường synthetic, nhưng synthetic khác có vai trò khác (ví dụ lambda implementation). Bộ lọc cần kết hợp `ACC_BRIDGE`, `ACC_SYNTHETIC`, method descriptor và mục tiêu đo.

### Phép kiểm phản chiếu

~~~java
Method bridge = java.util.Arrays.stream(
        StringService.class.getDeclaredMethods())
        .filter(Method::isBridge)
        .findFirst()
        .orElseThrow();

System.out.println(bridge.isSynthetic());
~~~

Đây là **mảnh minh họa đặt trong chương trình có import `java.lang.reflect.Method`**. Với class trong demo được javac biên dịch, kết quả là `true`. Khi muốn kiểm chứng flags ở cấp bytecode, chạy:

~~~bash
javap -p -v -classpath app-bin tutorial.app.StringService
~~~

Tìm dòng:

~~~text
flags: (0x1041) ACC_PUBLIC, ACC_BRIDGE, ACC_SYNTHETIC
~~~

Đừng nhầm `ACC_BRIDGE` với Java source modifier; compiler dùng nó để biểu thị method bridge. Khi transformer viết lại method, **không xóa flags/chữ ký bridge** nếu không có chủ đích và không hiểu rõ verifier/linkage constraints.

## 4. Synthetic members: không phải mọi thứ synthetic đều là bridge

`Synthetic` nghĩa là một class/member được đánh dấu do compiler hoặc tool sinh ra, không trực tiếp biểu diễn một khai báo source thông thường. API phản chiếu tương ứng:

- `Class.isSynthetic()` cho class.
- `Method.isSynthetic()` cho method.
- `Field.isSynthetic()` cho field.
- `Method.isBridge()` **chỉ** cho method bridge.

Có những synthetic methods **không phải bridge**. Trong demo, `LambdaCase` chứa lambda expression, và `javac` tạo một synthetic method để chứa phần body. Vì vậy cách phân loại:

~~~text
method.isBridge() == true   -> nhánh chính sách BRIDGE
method.isSynthetic() == true && !method.isBridge()
                            -> nhánh chính sách SYNTHETIC_NON_BRIDGE
method thường                -> nhánh NORMAL
~~~

Đây là cách phân loại **của agent**, không phải ba nhóm chính thức của API. Nó giúp audit “vì sao method bị skip/được đo”. Một codebase có annotation processing, Kotlin/Scala/other JVM languages có thể tạo nhiều synthetic members hơn Java thuần; ma trận thử nghiệm nên bao gồm compiler thực tế của dự án.

### Descriptor quan trọng hơn tên method

Đối với một JVM class, tính định danh method trong bytecode được hiểu bởi **tên và method descriptor**, không chỉ tên. Hai method `convert` có parameter types khác nhau là hai method khác nhau. Khi tìm method để instrument, phải so sánh cả descriptor nếu muốn chính xác; ví dụ của ASM:

~~~java
if (name.equals("convert")
        && descriptor.equals("(Ljava/lang/String;)Ljava/lang/String;")) {
    // Chỉ method implementation, không phải bridge (Object)Object.
}
~~~

Đây là **mảnh code minh họa bên trong ASM MethodVisitor/ClassVisitor context**, không tự biên dịch khi chưa có `name`, `descriptor` và dependency ASM. Với bytecode weaving production, nên giữ thông tin access flags và signature của method để phân loại đúng.

## 5. Lambda: phân biệt invokedynamic, synthetic body và runtime class

Một biểu thức lambda Java:

~~~java
final class LambdaCase {
    public java.util.function.Supplier<String> supplier(String suffix) {
        return () -> "x-" + suffix;
    }
}
~~~

Ở class file do `javac` biên dịch, lambda call site thường dùng **`invokedynamic`** và bootstrap linkage liên quan `LambdaMetafactory`. Compiler có thể sinh một method như `lambda$supplier$0` mang `ACC_SYNTHETIC` để chứa body. Nhưng object hiện thực `Supplier<String>` khi chạy có runtime class riêng, có thể là **hidden class** tùy JDK/JVM.

Điểm cần nhớ:

- **Synthetic lambda body method** có thể tồn tại **trong host class** `LambdaCase`.
- **Lambda implementation object** có `getClass()` khác `LambdaCase.class`.
- **Không phải mọi lambda phải tạo một method `lambda$...`**. Một số method reference hoặc compiler strategy có thể khác.
- **Không bảo đảm transformer sẽ nhận callback class definition cho mọi hidden lambda proxy** theo cùng cách như named application classes. Dùng tool đúng cho mức quan sát cần thiết.
- Khi một `Class<?>` là hidden class, phải kiểm tra `isModifiableClass`: không được mặc định gọi `retransformClasses` trên nó.
- Không dùng `lambdaProxy.getClass().getName()` rồi `Class.forName(...)` để cố tải “bản sao” runtime lambda class: tên hidden class không phải binary name để tìm bằng cách thông thường.

Trong lần chạy JDK 24 đã kiểm chứng:

~~~text
lambdaSyntheticMethods=1
lambdaResult=x-lambda
lambdaProxyHidden=true
lambdaProxyModifiable=false
~~~

**Diễn giải chính xác:** Đây là output của **một `javac --release 17` và một JVM cụ thể**. Nó chứng minh host class có một method `lambda$...` synthetic trong ví dụ; lambda proxy runtime là hidden và không modifiable trong môi trường thử nghiệm. Không quy nạp thành “mọi lambda trên mọi JVM có đúng một synthetic method/hidden class”.

### Chọn điểm đo lambda hợp lý

| Mục tiêu đo | Điểm chèn nên cân nhắc | Cần test thêm |
| --- | --- | --- |
| Số lần code trong lambda body chạy | Host class method thực thi body, nếu compiler sinh method như vậy | Synthetic method detection; exception/return value |
| Thời gian gọi functional API | Method gọi `Supplier.get()` hoặc API boundary do ứng dụng kiểm soát | Không biến mọi lần gọi thành double-count |
| Những lambda expressions được tạo | Call site `invokedynamic`/factory invocation ở host class | Capture semantics, allocation, classloader |
| Runtime behavior proxy | Quan sát object qua API/application code | Hidden class, class identity, modifiability và JVM-specific implementation |

Với những cơ chế bytecode rewrite, giữ nguyên bootstrap method arguments, invokedynamic descriptor và captured values. Tự thay descriptor của lambda call site mà không tái tính stack frames/bootstrap linkage có thể gây `VerifyError` hoặc `BootstrapMethodError`.

## 6. Record: cấu trúc có ý nghĩa ngữ nghĩa, không chỉ một class final

Một record Java 17:

~~~java
record Event(String label, int count) { }
~~~

Từ Java source có vẻ ngắn, nhưng compiler tạo các thành phần runtime cần thiết: private final fields cho components, public component accessors, canonical constructor, và implementation của `equals`, `hashCode`, `toString`. Class file có **`Record` attribute**; reflection có:

~~~java
Event.class.isRecord();               // true
Event.class.getRecordComponents();   // hai components: label, count
~~~

**Đừng dùng số lượng methods như tiêu chí duy nhất** để nhận diện record. Record components có API/attribute riêng. Với `javap -v`, một record hợp lệ do `javac` tạo sẽ hiện phần:

~~~text
Record:
  ...
~~~

Dấu `...` ở đây biểu thị **phần output `javap` được rút gọn cho minh họa**, không phải nội dung cần copy vào source; bộ demo chạy có thể dùng `javap -v` để xem chi tiết.

### Instrument record mà không phá cấu trúc

Một transformer có thể thêm logging/metrics vào **method body** hợp lệ, nhưng đối với class đã load phải tuân thủ giới hạn retransformation/redefinition. Không tự do thêm field mới cho probe, xóa record component, đổi component descriptor, đổi superclass `java.lang.Record` hoặc làm hỏng `Record` attribute.

Nên có các assertions:

1. `Event.class.isRecord() == true` trước và sau.
2. `getRecordComponents()` có số lượng, tên, kiểu đúng.
3. Record accessor `label()` và `count()` trả đúng giá trị.
4. `equals/hashCode/toString` vẫn có behavior như yêu cầu khi transformer chèn code.
5. Canonical constructor vẫn duy trì các invariants của ứng dụng.
6. Không nhầm record field final với trạng thái có thể cập nhật tùy ý.
7. Nếu có serialization, reflection frameworks hoặc record-based DTO mapping, test cùng framework để phát hiện regression.

**Giới hạn của demo:** nó quan sát/retransform nhưng trả `null`, nên chưa thực sự chèn instructions. Với bytecode patcher thật, bổ sung test so sánh kết quả sau patch và test JVM verifier.

## 7. Sealed class/interface: giữ đúng danh sách lớp được phép

Một sealed interface Java 17:

~~~java
sealed interface Shape permits Circle, Rectangle {
    String kind();
}

final class Circle implements Shape {
    @Override
    public String kind() { return "circle"; }
}

non-sealed class Rectangle implements Shape {
    @Override
    public String kind() { return "rectangle"; }
}
~~~

Khái niệm quan trọng:

- `sealed` giới hạn những lớp trực tiếp được phép `extends`/`implements`.
- Các subtype trực tiếp của sealed type phải tuyên bố một trong `final`, `sealed` hoặc `non-sealed`, theo quy tắc Java.
- `non-sealed Rectangle` cho phép các lớp con tiếp tục kế thừa theo quy tắc class loading thông thường; điều này **không** có nghĩa mọi class có thể trở thành direct subtype của `Shape`.
- Class file của sealed type chứa **`PermittedSubclasses` attribute**.
- Reflection API `Class.isSealed()` và `getPermittedSubclasses()` có thể xác nhận metadata.

Trong demo:

~~~text
shapeIsSealed=true
permitted=Circle,Rectangle
shapeDispatch=circle
~~~

`permitted=...` được sắp xếp theo tên trong code test để output ổn định; **không giả định thứ tự trả về của reflection là một hợp đồng tùy ý mà test nên phụ thuộc**.

### Rủi ro cho redefinition/retransformation

Với class đã load, không tự sửa `PermittedSubclasses`, đổi trực tiếp `extends/implements` hoặc thêm/sửa superclass/fields/method descriptors theo ý muốn. JVMTI có các giới hạn đối với class schema. Ngay cả nếu một byte array vẫn parse được, nó có thể bị JVM từ chối khi apply.

Nếu agent cần patch method body của `Shape.kind()` hoặc subtype, hãy kiểm tra:

- Target có thực sự modifiable không.
- Bytecode output giữ class identity và structural attributes hợp lệ.
- Những method dispatch mới vẫn hoạt động qua reference kiểu `Shape`.
- Tập permitted subclasses không bị thay ngoài ý muốn.
- Không có `IncompatibleClassChangeError` hoặc lỗi verifier/linkage sau update.

Một test cố tình vi phạm `PermittedSubclasses` nên chạy trong **JVM test riêng**, tránh làm hỏng pipeline kiểm thử chính. Không coi một thử nghiệm thay đổi schema bị JVM từ chối là thiếu năng lực của API; đó là enforcement đúng.

## 8. Hai class loader: cùng tên không đồng nghĩa cùng Class

Với JVM, danh tính runtime của một lớp phụ thuộc **binary name và defining class loader**. Hai loader có thể dùng cùng class bytes để define hai class có tên `tutorial.fixture.Twin`:

~~~text
binary name = tutorial.fixture.Twin
          |
          +-- IsolatedLoader("A") --> Class<?> A
          |
          +-- IsolatedLoader("B") --> Class<?> B

A.getName().equals(B.getName()) == true
A == B                            == false
A.getClassLoader() == B.getClassLoader() == false
~~~

Đây là trường hợp đặc biệt quan trọng với application servers, plugin systems, hot-reload containers và nhiều bản class loader song song.

**Một transformer không nên chỉ lưu cache theo `className`** nếu dữ liệu transformation phụ thuộc loader/module. Key tối thiểu thường phải xét **class loader identity + internal name**; nếu có module boundaries thì xét thêm module, protection domain/policy khi thực sự liên quan.

### Tại sao không được ép cast instance A sang kiểu B?

Hai classes khác nhau về runtime type, dù cùng tên và có cùng methods. Instance do `Class<?> A` tạo không tự nhiên là instance của `Class<?> B`. Nếu ép cast qua boundary không phù hợp có thể xảy ra `ClassCastException`/loader constraint error. Bộ demo không cast chúng; thay vào đó nó gọi public method bằng reflection trên từng `Class<?>` tương ứng.

### Không vô tình dùng parent-first cho fixture

Nếu class `tutorial.fixture.Twin` cũng có mặt trên application classpath, một `ClassLoader.loadClass(name)` theo parent delegation có thể trả class do parent định nghĩa, làm test sai. Bộ demo **không đưa `fixture-bin` vào runtime `-cp`**; hai `IsolatedLoader` tự gọi `defineClass(...)` với bytes từ file fixture đã biên dịch. Nhờ vậy hai runtime definitions thực sự có loaders khác nhau.

### Với ClassFileTransformer

Ở load-time, callback có `className="tutorial/fixture/Twin"` cho cả hai definitions, nhưng `loader` khác nhau. Sau retransform, chính những `Class<?>` đã tồn tại được truyền để JVM gọi lại capable transformer (nếu capability/target modifiability cho phép).

Một log có ý nghĩa phải bao gồm cả loader:

~~~text
fixtureCallback=load loader=isolated-A
fixtureCallback=load loader=isolated-B
fixtureCallback=retransform loader=isolated-A
fixtureCallback=retransform loader=isolated-B
~~~

Không cần gọi `loader.loadClass("tutorial.fixture.Twin")` từ callback. Khi định nghĩa lớp, việc đó có thể gây class-loading reentrancy; **tham số `className` và `classfileBuffer` đã đủ** để lọc/transform.

## 9. Test strategy nhiều lớp: metadata, behavior, callback và isolation

Một bộ kiểm thử tốt nên tách các giai đoạn:

1. **Compile test:** sinh bytecode bằng compiler/version cố định.
2. **Class-file inspection:** dùng `javap -v -p` hoặc thư viện parse để kiểm tra flags/attributes/descriptors.
3. **Reflection metadata:** kiểm tra `isBridge`, `isSynthetic`, `isRecord`, `isSealed`, `isHidden` và loaders.
4. **Behavior test:** gọi generic bridge, lambda, record accessor, sealed subtype dispatch, fixture instances.
5. **Agent callback test:** in/đếm callbacks của targets đã lọc, không log toàn JVM.
6. **Retransform capability test:** kiểm tra `isRetransformClassesSupported()`, manifest `Can-Retransform-Classes` và `isModifiableClass`.
7. **Identity test:** hai class cùng binary name nhưng khác loader không bị gộp.
8. **Negative test:** không cố sửa array/primitive/hidden class không modifiable.
9. **Post-transform test:** chạy lại behavior/metadata sau khi đã retransform.
10. **Production patcher test:** nếu thực sự sửa bytes, kiểm chứng probe count, stack frames, verifier, startup và runtime trên JDK mục tiêu.

Chú ý hai cấp thành công:

- **“Observer transformer đã được gọi”**: callback chạy và `return null`. Đây là điều demo trực tiếp chứng minh.
- **“Bytecode transformation thành công”**: phải trả mảng bytes mới, JVM chấp nhận class và test đúng behavior. Không suy luận cấp thứ hai từ cấp thứ nhất.

## 10. Demo hoàn chỉnh JDK 17+: một agent, sáu kiểu class được kiểm tra

Demo gồm ba mảng:

- **Agent `EdgeCaseAgent`:** đăng ký `ClassFileTransformer` capable nếu JVM hỗ trợ, log hai loader riêng của fixture và cung cấp API khảo sát/retransform.
- **Ứng dụng:** chứa generic override, lambda, record, sealed hierarchy và driver kiểm tra reflection/behavior.
- **Fixture `Twin`:** được biên dịch riêng, **không nằm trên runtime classpath**, chỉ được hai loader dùng bytes để định nghĩa.

Các câu lệnh trong ví dụ là runnable dưới JDK 17+ trên JVM có Java Instrumentation. Kết quả dưới đây là stdout đã xác minh trên **JDK 24**, không phải một output suy đoán. Trường hợp JVM không hỗ trợ retransformation được agent báo rõ là skipped thay vì khẳng định thành công.

### 10.1. Bố trí files

~~~text
special-types-agent-demo/
├── agent-src/
│   └── tutorial/agent/EdgeCaseAgent.java
├── app-src/
│   └── tutorial/app/
│       ├── Cases.java
│       └── Driver.java
├── fixture-src/
│   └── tutorial/fixture/Twin.java
└── agent.mf
~~~

Sau compile, các thư mục output gồm:

~~~text
agent-bin/
app-bin/
fixture-bin/
dist/
└── edge-agent.jar
~~~

Tệp `Cases.java` chứa một số **package-private top-level declarations** (class/record/interface). Điều này hợp lệ trong Java khi chúng cùng package, không phải mỗi declaration đều phải nằm trong file cùng tên nếu không public.

### 10.2. File agent-src/tutorial/agent/EdgeCaseAgent.java

~~~java
package tutorial.agent;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;

public final class EdgeCaseAgent {
    private static volatile Instrumentation instrumentation;

    public static void premain(String args, Instrumentation inst) {
        instrumentation = inst;
        inst.addTransformer(new Observer(), inst.isRetransformClassesSupported());
        System.out.println("agentReady=true");
    }

    public static boolean modifiable(Class<?> type) {
        return instrumentation.isModifiableClass(type);
    }

    public static boolean retransformSupported() {
        return instrumentation.isRetransformClassesSupported();
    }

    public static long countLoaded(String binaryName) {
        long count = 0;
        for (Class<?> type : instrumentation.getAllLoadedClasses()) {
            if (type.getName().equals(binaryName)) count++;
        }
        return count;
    }

    public static void verifyRetransformation(Class<?>... types) throws Exception {
        if (!instrumentation.isRetransformClassesSupported()) {
            System.out.println("retransformSkipped=unsupported");
            return;
        }
        for (Class<?> type : types) {
            if (!instrumentation.isModifiableClass(type)) {
                System.out.println("retransformSkipped=unmodifiable:" + type.getName());
                return;
            }
        }
        instrumentation.retransformClasses(types);
        System.out.println("retransformCount=" + types.length);
    }

    private static final class Observer implements ClassFileTransformer {
        @Override
        public byte[] transform(Module module, ClassLoader loader,
                String className, Class<?> classBeingRedefined,
                ProtectionDomain domain, byte[] classfileBuffer) {
            if ("tutorial/fixture/Twin".equals(className)) {
                String loaderId = loader == null ? "bootstrap" : loader.toString();
                String phase = classBeingRedefined == null ? "load" : "retransform";
                System.out.println("fixtureCallback=" + phase + " loader=" + loaderId);
            }
            return null;
        }
    }
}
~~~

**Giải thích:**

- `premain` có `Instrumentation` được JVM cấp khi chạy `-javaagent`; code ứng dụng không tự tạo instrumentation.
- `addTransformer(new Observer(), inst.isRetransformClassesSupported())` đăng ký capable khi runtime có capability, ngược lại đăng ký non-capable để quan sát load-time.
- Observer chỉ lọc `tutorial/fixture/Twin` bằng internal name và ghi loader/phase, **không gọi loader nạp target**.
- Vì test không sử dụng `redefineClasses`, label `"retransform"` khi `classBeingRedefined != null` là đúng **trong kịch bản demo**. Trong agent tổng quát, tham số khác null **cũng xuất hiện ở redefine**, nên không dùng riêng điều kiện đó để phân biệt mọi sự kiện.
- `countLoaded(...)` đếm class đang hiện diện trong **một snapshot** của `getAllLoadedClasses()`; kết quả có thể thay đổi ở môi trường khác.
- `isModifiableClass` và `isRetransformClassesSupported` là hai điều kiện độc lập; `isModifiableClass==true` chưa bảo đảm mọi bytecode patch đều hợp lệ.
- `return null` nghĩa là **không sửa bytes** trong observer. Việc gọi retransform vẫn là thao tác JVM thực, có thể tác động tới các transformers khác nếu tồn tại.

### 10.3. File app-src/tutorial/app/Cases.java

~~~java
package tutorial.app;

import java.util.function.Supplier;
import java.util.Locale;

abstract class Base<T> {
    public abstract T convert(T input);
}

final class StringService extends Base<String> {
    @Override
    public String convert(String input) {
        return input.toUpperCase(Locale.ROOT);
    }
}

final class LambdaCase {
    public Supplier<String> supplier(String suffix) {
        return () -> "x-" + suffix;
    }
}

record Event(String label, int count) { }

sealed interface Shape permits Circle, Rectangle {
    String kind();
}

final class Circle implements Shape {
    @Override public String kind() { return "circle"; }
}

non-sealed class Rectangle implements Shape {
    @Override public String kind() { return "rectangle"; }
}
~~~

Một file này có thể sinh nhiều `.class` files: `Base.class`, `StringService.class`, `LambdaCase.class`, `Event.class`, `Shape.class`, `Circle.class` và `Rectangle.class`.

- `Base<T>` + `StringService` tạo ra bridge khi `javac` xử lý erasure.
- `LambdaCase` có lambda có captured parameter `suffix`.
- `Event` là record, có hai components.
- `Shape` là sealed interface; `Circle` là final permitted subtype; `Rectangle` là non-sealed permitted subtype.

Code này chỉ biên dịch trên JDK có các tính năng Java tương ứng (Java 17+ là mốc an toàn cho toàn bộ demo). Không có thư viện third-party.

### 10.4. File fixture-src/tutorial/fixture/Twin.java

~~~java
package tutorial.fixture;

public final class Twin {
    public Twin() {}

    public String value() {
        return "twin";
    }
}
~~~

Fixture sẽ được biên dịch vào `fixture-bin/tutorial/fixture/Twin.class`. **Không thêm `fixture-bin` vào `-cp` lúc chạy**. Driver đọc bytes và yêu cầu **hai IsolatedLoader khác nhau** define chính class này.

### 10.5. File app-src/tutorial/app/Driver.java

~~~java
package tutorial.app;

import tutorial.agent.EdgeCaseAgent;
import java.lang.reflect.Method;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.Comparator;
import java.util.function.Supplier;
import java.util.stream.Collectors;

public final class Driver {
    private static final String TWIN = "tutorial.fixture.Twin";

    private static final class IsolatedLoader extends ClassLoader {
        private final String id;

        IsolatedLoader(String id) {
            super(Driver.class.getClassLoader());
            this.id = id;
        }

        Class<?> defineTwin(byte[] bytes) {
            return defineClass(TWIN, bytes, 0, bytes.length);
        }

        @Override
        public String toString() {
            return "isolated-" + id;
        }
    }

    public static void main(String[] args) throws Exception {
        StringService service = new StringService();
        Method bridge = Arrays.stream(StringService.class.getDeclaredMethods())
                .filter(Method::isBridge)
                .findFirst()
                .orElseThrow();

        System.out.println("bridgeCount="
                + Arrays.stream(StringService.class.getDeclaredMethods())
                        .filter(Method::isBridge).count());
        System.out.println("bridgeIsSynthetic=" + bridge.isSynthetic());
        System.out.println("bridgeDispatch="
                + ((Base<String>) service).convert("hi"));

        LambdaCase lambdaCase = new LambdaCase();
        Supplier<String> supplier = lambdaCase.supplier("lambda");
        System.out.println("lambdaSyntheticMethods="
                + Arrays.stream(LambdaCase.class.getDeclaredMethods())
                        .filter(m -> m.isSynthetic()
                                && m.getName().startsWith("lambda$"))
                        .count());
        System.out.println("lambdaResult=" + supplier.get());
        System.out.println("lambdaProxyHidden="
                + supplier.getClass().isHidden());
        System.out.println("lambdaProxyModifiable="
                + EdgeCaseAgent.modifiable(supplier.getClass()));

        Event event = new Event("E", 4);
        System.out.println("recordIsRecord=" + Event.class.isRecord());
        System.out.println("recordComponents="
                + Event.class.getRecordComponents().length);
        System.out.println("recordValue="
                + event.label() + ":" + event.count());

        String permitted = Arrays.stream(Shape.class.getPermittedSubclasses())
                .map(Class::getSimpleName)
                .sorted()
                .collect(Collectors.joining(","));
        System.out.println("shapeIsSealed=" + Shape.class.isSealed());
        System.out.println("permitted=" + permitted);
        System.out.println("shapeDispatch="
                + ((Shape) new Circle()).kind());

        byte[] bytes = Files.readAllBytes(
                Path.of("fixture-bin", "tutorial", "fixture", "Twin.class"));
        Class<?> first = new IsolatedLoader("A").defineTwin(bytes);
        Class<?> second = new IsolatedLoader("B").defineTwin(bytes);

        System.out.println("sameBinaryName="
                + first.getName().equals(second.getName()));
        System.out.println("sameClassObject=" + (first == second));
        System.out.println("sameLoader="
                + (first.getClassLoader() == second.getClassLoader()));

        Object a = first.getDeclaredConstructor().newInstance();
        Object b = second.getDeclaredConstructor().newInstance();
        System.out.println("fixtureValues="
                + first.getMethod("value").invoke(a) + ","
                + second.getMethod("value").invoke(b));
        System.out.println("loadedTwinCount=" + EdgeCaseAgent.countLoaded(TWIN));

        System.out.println("arrayModifiable="
                + EdgeCaseAgent.modifiable(int[].class));
        System.out.println("primitiveModifiable="
                + EdgeCaseAgent.modifiable(int.class));
        System.out.println("retransformSupported="
                + EdgeCaseAgent.retransformSupported());

        EdgeCaseAgent.verifyRetransformation(StringService.class,
                LambdaCase.class, Event.class, Shape.class, first, second);

        System.out.println("afterBridge="
                + ((Base<String>) service).convert("hi"));
        System.out.println("afterRecord="
                + event.label() + ":" + event.count());
    }
}
~~~

**Vì sao cách test loader này đáng tin hơn chỉ so sánh class name?**

- `IsolatedLoader.defineTwin(bytes)` gọi protected `ClassLoader.defineClass` qua subclass của loader.
- Hai đối tượng loader có cùng implementation nhưng **instance khác nhau**, name in log rõ ràng `isolated-A` và `isolated-B`.
- `first == second` kiểm tra **Class object identity**, chính xác hơn so sánh `getName()`.
- Mỗi class có thể tạo một instance và trả `"twin"` bằng reflection; hai class có cùng behavior mà vẫn khác runtime identity.
- Vì `fixture-bin` không nằm trên application classpath, driver không vô tình dùng parent-provided `Twin`.
- `countLoaded(TWIN)` xác nhận snapshot JVM chứa hai definitions cùng binary name trong môi trường kiểm thử.

Một điểm thiết kế khác: `EdgeCaseAgent.verifyRetransformation(...)` nhận **Class<?> objects thật** của hai definitions, chứ không chỉ tên lớp. Điều này giúp JVM nhắm chính xác vào cả hai target khác nhau.

### 10.6. Manifest của agent: agent.mf

~~~text
Manifest-Version: 1.0
Premain-Class: tutorial.agent.EdgeCaseAgent
Can-Retransform-Classes: true
~~~

Manifest cần có **dòng trống cuối**. `Can-Retransform-Classes: true` cho phép agent yêu cầu capability, nhưng vẫn phải kiểm tra `isRetransformClassesSupported()` vì JVM có thể không hỗ trợ.

Không nhầm `Can-Retransform-Classes` với `Can-Redefine-Classes`. Demo gọi `retransformClasses(...)`, nên capability đầu là đúng. Nó không dùng `redefineClasses(new ClassDefinition(...))`.

### 10.7. Biên dịch và chạy

**Bash/Linux/macOS/Git Bash**, chạy từ thư mục `special-types-agent-demo/`:

~~~bash
mkdir -p agent-bin app-bin fixture-bin dist

javac --release 17 -d agent-bin \
  agent-src/tutorial/agent/EdgeCaseAgent.java

javac --release 17 -cp agent-bin -d app-bin \
  app-src/tutorial/app/Cases.java \
  app-src/tutorial/app/Driver.java

javac --release 17 -d fixture-bin \
  fixture-src/tutorial/fixture/Twin.java

jar --create --file dist/edge-agent.jar \
  --manifest agent.mf -C agent-bin .

java -javaagent:dist/edge-agent.jar \
  -cp app-bin tutorial.app.Driver
~~~

**Windows PowerShell**, cùng lệnh nhưng viết một dòng cho mỗi command:

~~~powershell
New-Item -ItemType Directory -Force -Path agent-bin, app-bin, fixture-bin, dist | Out-Null
javac --release 17 -d agent-bin agent-src/tutorial/agent/EdgeCaseAgent.java
javac --release 17 -cp agent-bin -d app-bin app-src/tutorial/app/Cases.java app-src/tutorial/app/Driver.java
javac --release 17 -d fixture-bin fixture-src/tutorial/fixture/Twin.java
jar --create --file dist/edge-agent.jar --manifest agent.mf -C agent-bin .
java -javaagent:dist/edge-agent.jar -cp app-bin tutorial.app.Driver
~~~

**Quan trọng về runtime class path:** `app-bin` là classpath ứng dụng; agent được JVM tìm qua `-javaagent`, còn `fixture-bin` phải ở trên **filesystem để driver đọc bytes**, **không** đưa vào `-cp`. Khi chạy ở thư mục khác, cần điều chỉnh đường dẫn tương đối tới `fixture-bin` trong chương trình hoặc working directory.

`jar -C agent-bin .` đóng toàn bộ agent classes, bao gồm `EdgeCaseAgent$Observer.class`. Nếu thiếu class lồng, agent có thể lỗi ngay trong `premain` trước khi app bắt đầu.

### 10.8. Stdout chính xác đã kiểm chứng trên JDK 24

~~~text
agentReady=true
bridgeCount=1
bridgeIsSynthetic=true
bridgeDispatch=HI
lambdaSyntheticMethods=1
lambdaResult=x-lambda
lambdaProxyHidden=true
lambdaProxyModifiable=false
recordIsRecord=true
recordComponents=2
recordValue=E:4
shapeIsSealed=true
permitted=Circle,Rectangle
shapeDispatch=circle
fixtureCallback=load loader=isolated-A
fixtureCallback=load loader=isolated-B
sameBinaryName=true
sameClassObject=false
sameLoader=false
fixtureValues=twin,twin
loadedTwinCount=2
arrayModifiable=false
primitiveModifiable=false
retransformSupported=true
fixtureCallback=retransform loader=isolated-A
fixtureCallback=retransform loader=isolated-B
retransformCount=6
afterBridge=HI
afterRecord=E:4
~~~

**Giải thích theo từng nhóm:**

| Dấu hiệu | Bằng chứng |
| --- | --- |
| `bridgeCount=1`, `bridgeIsSynthetic=true` | Trong class của `javac`, có một bridge đồng thời synthetic |
| `bridgeDispatch=HI` | Lời gọi qua generic base reference vẫn dispatch đúng |
| `lambdaSyntheticMethods=1` | Host `LambdaCase` có một synthetic lambda implementation method theo compiler này |
| `lambdaResult=x-lambda` | Lambda giữ captured suffix và trả kết quả đúng |
| `lambdaProxyHidden=true` | Runtime JDK 24 tạo hidden lambda proxy cho tình huống này |
| `lambdaProxyModifiable=false` | Proxy lambda cụ thể không thể retransform trên JVM thử nghiệm; agent không cố ép sửa |
| `recordIsRecord=true`, `recordComponents=2` | Reflection thấy record và hai components |
| `recordValue=E:4` | Component accessors còn hoạt động |
| `shapeIsSealed=true`, `permitted=Circle,Rectangle` | Sealed metadata tồn tại đúng |
| `shapeDispatch=circle` | Interface dispatch qua sealed hierarchy hoạt động |
| Hai dòng `fixtureCallback=load` với A/B | JVM nhận hai class definitions cùng tên nhưng khác loaders |
| `sameBinaryName=true`, `sameClassObject=false`, `sameLoader=false` | Class identity phải tính loader, không thể dùng tên làm khóa duy nhất |
| `loadedTwinCount=2` | Snapshot chứa cả hai definitions được tạo |
| `arrayModifiable=false`, `primitiveModifiable=false` | API quy định array/primitive classes không thể sửa |
| `retransformSupported=true` | Agent/JVM thử nghiệm hỗ trợ retransformation |
| Hai callbacks `retransform`, `retransformCount=6` | Hai fixture classes được retransform cùng bốn class mẫu |
| `afterBridge=HI`, `afterRecord=E:4` | Các behavior vẫn đúng sau observer-only retransform |

**Cảnh báo về interpretation:** `retransformCount=6` là số `Class<?>` được truyền cho một lời gọi retransform thành công, **không phải số method đã chèn probe**. Observer trả `null`, nên không tạo bytecode mới. Các giá trị `lambdaProxyHidden=true` và `lambdaProxyModifiable=false` là **kết quả quan sát trên runtime này**, không phải lời hứa cho mọi JVM.

### 10.9. Kiểm tra class-file flags/attributes với javap

Chạy:

~~~bash
javap -p -v -classpath app-bin tutorial.app.StringService
javap -v -classpath app-bin tutorial.app.Event
javap -v -classpath app-bin tutorial.app.Shape
~~~

Trong lần kiểm chứng JDK 24, trích xuất hiện diện:

~~~text
StringService:
    flags: (0x1041) ACC_PUBLIC, ACC_BRIDGE, ACC_SYNTHETIC

Event:
    Record:

Shape:
    PermittedSubclasses:
~~~

Đây là **các dòng trích liên quan**, không phải toàn bộ stdout của lệnh `javap -v`. Với record/sealed, dùng bản `javap` đầy đủ để đối chiếu field descriptors và danh sách permitted subclasses. Nếu muốn xem lambda call site, thử:

~~~bash
javap -p -c -v -classpath app-bin tutorial.app.LambdaCase
~~~

Tìm `invokedynamic` và các mục `BootstrapMethods` liên quan. Đừng khẳng định class file của host luôn chứa cùng một `lambda$...` symbol trong mọi compiler.

## 11. Làm sao biến demo thành regression test có assert?

Bản demo in log để dễ đọc. Trong unit/integration test thực, dùng assertions thay vì chỉ nhìn stdout thủ công.

Ví dụ assertion cho bridge:

~~~java
long bridges = java.util.Arrays.stream(
        StringService.class.getDeclaredMethods())
        .filter(java.lang.reflect.Method::isBridge).count();

if (bridges != 1) throw new AssertionError("Bridge count changed");

StringService service = new StringService();
if (!"HI".equals(((Base<String>) service).convert("hi"))) {
    throw new AssertionError("Generic dispatch was changed");
}
~~~

Đây là **mảnh code đặt trong cùng package `tutorial.app`**, không phải một chương trình độc lập. Với compiler đã được cố định trong pipeline, assert bridge count có ý nghĩa. Với multi-compiler support, test có thể cần đánh giá flags/behavior linh hoạt theo compiler khác.

Assertion cho record/sealed:

~~~java
if (!Event.class.isRecord()
        || Event.class.getRecordComponents().length != 2) {
    throw new AssertionError("Record metadata changed");
}

if (!Shape.class.isSealed()
        || Shape.class.getPermittedSubclasses().length != 2) {
    throw new AssertionError("Sealed metadata changed");
}
~~~

Assertion cho loader identity:

~~~java
if (!first.getName().equals(second.getName())
        || first == second
        || first.getClassLoader() == second.getClassLoader()) {
    throw new AssertionError("Loader isolation was lost");
}
~~~

Đoạn này cần hai biến `Class<?> first, second` từ fixture loader như ở driver, và chỉ kiểm tra đúng điều test đặt ra. Nếu một framework cache kết quả instrument theo `className` mà không theo loader, hãy bổ sung metrics hoặc marker riêng để assert **hai definitions có kết quả độc lập**, thay vì chỉ assert hai callback hiện diện.

### Test sự kiện cần có hai đầu ra riêng

Trong một agent thực sự thay bytecode, nên ghi đồng thời:

~~~text
Transform decision:
  class internal name, loader identity, method name + descriptor,
  flags (bridge/synthetic), include/skip reason

Execution outcome:
  callback count, bytes returned? null/non-null,
  retransform call succeeded?, behavior assertions passed?
~~~

**Không ghi “PATCHED” chỉ vì `ClassFileTransformer.transform` được gọi.** Với `return null`, nghĩa chính xác là “observer đã nhận callback; không sửa bytes ở bước đó”.

## 12. Ma trận âm tính và ranh giới JVM

Đối với môi trường test isolation, cần xác nhận các thao tác sau **không được thực hiện vô điều kiện**:

| Trường hợp | Điều kiện/rủi ro | Kết quả kiểm thử mong muốn |
| --- | --- | --- |
| `int.class` | Primitive class không modifiable | `isModifiableClass==false`, không gọi retransform |
| `int[].class` | Array class không modifiable | `isModifiableClass==false`, không gọi retransform |
| Lambda proxy là hidden/unmodifiable | Có thể không thể retransform | Báo skip theo API, không ném lỗi vào production |
| Record với thay đổi component fields | Schema change có thể bị JVM từ chối | Test lỗi riêng, không cố sửa class đang chạy |
| Sealed type với danh sách permitted khác | Đổi structural metadata/hierarchy không portable | Không thay đổi tùy ý trong retransform |
| Bridge bị đổi descriptor | Vỡ erased dispatch/overriding | Verify descriptor + typed/generic calls |
| Synthetic lambda body bị bỏ qua | Mất measurement dù business code vẫn chạy | Chính sách include/skip được kiểm thử |
| Hai loader cùng class name | Cache theo tên đè metadata | Class/loader identity được giữ riêng |
| Fixture vô tình nằm trên app classpath | Parent loader có thể định nghĩa trước | Chạy classpath chỉ gồm `app-bin` |
| Transformer ném exception | JVM vẫn có thể chạy transformer sau | Không xem exception như atomic “abort pipeline” |

Một negative test chủ động trả class bytes sai định dạng, đổi field schema hoặc sửa PermittedSubclasses nên chạy ở **process JVM riêng** với timeout và exit-code checks. Nó có thể làm class loading thất bại hoặc agent startup hỏng; không lồng các tình huống phá hỏng này vào cùng JVM đang chạy bộ happy-path.

### Những exception cần phân biệt

- `UnsupportedOperationException`: capability hoặc thay đổi class không được hỗ trợ.
- `UnmodifiableClassException`: target JVM cho là không modifiable.
- `ClassFormatError`: output không phải class file hợp lệ.
- `VerifyError`: bytecode vi phạm các quy tắc verifier.
- `LinkageError` hoặc `ClassCircularityError`: vấn đề liên kết, định nghĩa class/hierarchy.
- `ClassCastException`: cố dùng instance do một loader định nghĩa như kiểu không tương thích của loader khác.
- `BootstrapMethodError`: invokedynamic/lambda bootstrap linkage lỗi trong trường hợp patch call site không đúng.

Một lỗi không nhất thiết có đúng một nguyên nhân; cần giữ class name, loader identity, JVM version, transform stage, exception chain, bytes hash và reproduction command.

## 13. Một chính sách instrumentation có thể kiểm thử được

Đối với một agent production, không nên chọn methods bằng một chuỗi điều kiện rải rác mà không ghi lý do. Ví dụ policy:

~~~text
Nếu class là array/primitive/hidden-unmodifiable:
    SKIP_UNMODIFIABLE

Nếu class không thuộc allowlist hoặc loader không được phép:
    SKIP_SCOPE_OR_LOADER

Nếu method.isBridge():
    SKIP_BRIDGE_BY_POLICY   (nếu đo logical business call)

Nếu method.isSynthetic() nhưng không bridge:
    INCLUDE_LAMBDA_BODY / SKIP_SYNTHETIC_BY_POLICY
    (tùy mục tiêu đo, không blanket skip)

Nếu class.isRecord():
    chỉ instrument method bodies hợp lệ; giữ Record metadata

Nếu class.isSealed():
    giữ PermittedSubclasses/hierarchy

Nếu transform:
    không sửa input classfileBuffer tại chỗ;
    trả byte[] mới; verify post-transform behavior
~~~

Đây là **giả mã policy**, không phải lệnh Java. Điểm cần test: **cùng một class/method ở cùng policy phải có quyết định tái lập**, và mỗi lý do skip cần được phân loại theo policy hoặc giới hạn JVM.

Một bản ghi chẩn đoán nên có:

- Internal class name (ví dụ `tutorial/fixture/Twin`).
- Loader identity hoặc stable ID của agent (không chỉ `ClassLoader.toString()`).
- Module và protection domain khi cần.
- Method name, descriptor, access flags.
- Phase load/redefine/retransform (phải xác định từ trạng thái điều phối, không chỉ `classBeingRedefined != null`).
- Decision (include/skip), reason code.
- Callback outcome (null/new bytes/exception).
- Kết quả verifier/apply và behavior test tương ứng.

**Không giữ strong references tới class loaders vô thời hạn** chỉ để audit. Nếu dùng map keyed theo `ClassLoader`/`Class<?>` trong agent sống lâu, có thể ngăn class unloading ở plugin containers; cần weak references hoặc chiến lược cleanup/bounded cache thích hợp.

## 14. Lưu ý chuyên sâu khi dùng ASM hoặc Byte Buddy

Với ASM, một `MethodVisitor` nhận access flags để phân biệt `ACC_BRIDGE` và `ACC_SYNTHETIC`. Với Byte Buddy, các matchers có thể lựa chọn bridge/synthetic theo mục tiêu. Cả hai đều cần test với **bytecode thực** từ compiler dự kiến, không chỉ reflection.

Một đoạn lọc ASM minh họa:

~~~java
boolean bridge = (access & org.objectweb.asm.Opcodes.ACC_BRIDGE) != 0;
boolean synthetic = (access & org.objectweb.asm.Opcodes.ACC_SYNTHETIC) != 0;

if (bridge) {
    // Policy: skip bridge when counting logical method execution.
}
~~~

Đây là **mảnh code cần dependency ASM**, không phải phần của demo runnable chỉ dùng JDK. Nếu instrument lambda host synthetic body, xác định bằng descriptor và bytecode semantics; không chỉ matching `name.startsWith("lambda$")` ở production nơi có nhiều compiler.

### Stack maps, frames và invokedynamic

Đặc biệt khi chèn probes vào bridge hoặc lambda method:

1. Giữ đúng operand stack và local variable layout.
2. Khi cần, tính lại StackMapTable/maxStack/maxLocals bằng công cụ phù hợp.
3. Không phá invoke bridge target hoặc cast bắt buộc.
4. Không sửa descriptor/BootstrapMethods của invokedynamic mà không kiểm tra linkage.
5. Giữ record/sealed structural attributes.
6. Không thêm field/method tùy ý khi retransform class đã load.
7. Kiểm tra return values, thrown exception identity và không tạo double probe.
8. Kiểm thử cả load-time instrumentation và retransform-time trên JDK mục tiêu.

Ví dụ matcher “tất cả methods” có thể chèn vào generated accessors, bridge, lambda body, constructor và ObjectMethods-related methods của record. Tùy use case, **một số trong đó phải được loại**, một số khác **phải giữ**. Không có quy tắc luôn đúng rằng “synthetic là noise”.

## 15. Những sai lầm thường gặp khi viết test

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Dùng một plain class để kết luận agent chạy tốt | Bỏ sót bridge, lambda, record, sealed metadata | Có class fixtures chuyên biệt |
| Bỏ tất cả synthetic methods | Mất lambda body instrumentation | Tách bridge và synthetic non-bridge |
| Instrument cả bridge và implementation vô điều kiện | Counter double-count ở erased dispatch | Quy định logical-method policy và test count |
| Giả định mọi lambda proxy là class thường | Cố retransform hidden/unmodifiable class | `isHidden`/`isModifiableClass` và skip reason |
| Test một tên cố định `lambda$...` trên mọi compiler | Test giòn khi đổi javac/compiler | Assert behavior/metadata hoặc cố định toolchain |
| Chỉ kiểm tra `Class.getName()` | Gộp hai class từ loader khác nhau | So sánh `Class<?>` và defining loader |
| Đưa fixture JAR vào runtime classpath | Parent có thể định nghĩa fixture, hỏng test multi-loader | Dùng bytes riêng ngoài classpath |
| Đọc file class trên đĩa thay `classfileBuffer` trong transformer | Có thể bỏ qua biến đổi trước hoặc dynamic generation | Parse đúng bytes JVM cấp |
| Chèn thêm fields vào loaded record | Schema change bị từ chối | Patch body theo giới hạn JVM |
| Sửa permitted hierarchy sau khi load | Linkage/unsupported changes | Giữ `PermittedSubclasses` metadata |
| Coi callback logged là bytes patched | False positive | Phân biệt observer/null và byte[] thay thế |
| Dùng `classBeingRedefined!=null` để phân biệt tuyệt đối retransform/redefine | Gắn sai phase | Theo dõi caller/operation context nếu cần |
| Không kiểm tra `isRetransformClassesSupported` | Runtime lỗi capability | Manifest đúng + check API |
| Quên kiểm tra `isModifiableClass` | Cố sửa class không được phép | Skip rõ ràng |
| Coi `LongAdder.sum` là unique loaded-class count | Callback count khác class identity | Định nghĩa metric đúng |
| Thiếu Java17 target trong CI | Record/sealed class bytes có thể khác | Cố định `--release 17`, matrix runtime |
| Không test multi-loader plugin | Instrument nhầm type cùng tên | Cấu hình loader-aware policy |
| Không test sau retransform | Regression về behavior/metadata | Pre/post tests và verifier |

## 16. Checklist tích hợp vào CI

- [ ] Biên dịch fixture bằng **đúng compiler/target release** production cần hỗ trợ.
- [ ] Chạy `javap -v -p` hoặc bytecode inspection để xác nhận flags và attributes quan trọng.
- [ ] Kiểm tra bridge method ở cả đường gọi erased và typed.
- [ ] Kiểm tra synthetic lambda implementation method theo compiler sử dụng.
- [ ] Không dựa vào hidden lambda proxy luôn modifiable.
- [ ] Kiểm tra record components, accessors, equals/hashCode/toString nếu được instrument.
- [ ] Kiểm tra sealed permitted subclasses và interface dispatch.
- [ ] Tạo hai class loader độc lập define cùng binary name.
- [ ] Kiểm tra callbacks và cache keys phân biệt loader identity.
- [ ] Không tự dùng class loader nạp lại chính lớp đang được transform.
- [ ] Kiểm tra capability, modifiability trước retransform.
- [ ] Không cố retransform array/primitive/unmodifiable hidden class.
- [ ] Test behavior cả trước và sau retransform/patch.
- [ ] Chạy negative tests trong JVM riêng nếu có class bytes sai hoặc schema change.
- [ ] Quan sát error types, exit codes, timeout và class-loading latency.
- [ ] Không để agent logging/loader references làm chương trình treo hoặc leak.
- [ ] Phân biệt được **callback observed**, **bytecode patched** và **behavior verified** trong báo cáo.

## 17. Bài tập tự kiểm tra

**Câu 1.** `StringService.convert(String)` override `Base<T>.convert(T)`. Vì sao class file có thể có thêm `convert(Object)`, và cờ nào giúp nhận diện nó?

**Câu 2.** Nếu agent chèn counter ở đầu cả bridge và implementation `convert`, một lời gọi thông qua `Base<String>` có thể tăng counter bao nhiêu lần? Đây là lỗi concurrency không?

**Câu 3.** `Method.isSynthetic()==true` có đồng nghĩa `Method.isBridge()==true` không?

**Câu 4.** Lambda body method tên `lambda$supplier$0` có được chuẩn Java bảo đảm xuất hiện đúng tên đó trên mọi compiler không?

**Câu 5.** JDK 24 thử nghiệm báo `lambdaProxyHidden=true` và `lambdaProxyModifiable=false`. Có được ép `retransformClasses(lambdaProxy.getClass())` trên tất cả JVM không?

**Câu 6.** Có thể nhận diện record chỉ từ việc class là `final` không? Nên dùng API nào?

**Câu 7.** Một transformer retransform `Event` nhưng sửa Record components hoặc thêm field mới. Điều gì có thể xảy ra?

**Câu 8.** `Shape.class.isSealed()==true`; `getPermittedSubclasses()` trả hai subclasses. Có thể đổi danh sách permitted tùy ý trong retransformation không?

**Câu 9.** Hai `Class<?>` có cùng `getName()` nhưng khác `getClassLoader()`. Chúng là một class hay hai class?

**Câu 10.** Nếu fixture `Twin.class` được để trên application classpath và code gọi `loadClass` parent-first, điều gì có thể làm test “hai loaders” không còn đúng?

**Câu 11.** Agent gọi `Instrumentation.retransformClasses(...)` trên sáu class, callback trả `null`, sau đó in `retransformCount=6`. Có thể khẳng định sáu class đã nhận code mới không?

**Câu 12.** `classBeingRedefined != null` trong callback chứng minh chắc chắn đang retransform chứ không phải redefine?

**Câu 13.** Vì sao nên đo both `bridgeDispatch=HI` và `afterBridge=HI` trong một test retransform?

**Câu 14.** Mục tiêu là “mỗi logical business call đếm đúng một lần”. Nếu method bridge chuyển tiếp vào implementation, nên chọn policy nào?

**Câu 15.** Vì sao classloader-aware cache có thể gây memory leak, và cách giảm thiểu?

**Câu 16.** Khi `getAllLoadedClasses()` chứa một hidden class, điều đó có nghĩa nó modifiable để retransform không?

### Đáp án

1. Do **type erasure** và polymorphic overriding; bridge thường có `ACC_BRIDGE`, thường kèm `ACC_SYNTHETIC`.
2. Có thể **2 lần**: bridge và implementation. Không phải lỗi concurrency, mà là lỗi chọn điểm đo.
3. **Không**. Bridge thường synthetic, nhưng synthetic method cũng có thể là lambda implementation hoặc compiler-generated helper khác.
4. **Không**. Tên và cách triển khai là compiler detail; cần inspect compiler cụ thể.
5. **Không**. Phải hỏi `isModifiableClass` và capability trên runtime thực tế; hidden lambda proxy có thể không sửa được.
6. **Không**. Dùng `Class.isRecord()` và `getRecordComponents()`, đối chiếu `Record` attribute.
7. JVM có thể từ chối vì class schema/metadata không hợp lệ; phải giữ cấu trúc được phép và chỉ patch body hợp lệ.
8. **Không**. Sealed hierarchy có `PermittedSubclasses` và JVMTI restrictions; không coi retransformation là cách tùy ý đổi hierarchy.
9. **Hai runtime classes**, vì defining class loader identity khác nhau.
10. Parent có thể cung cấp cùng class thay vì hai definitions độc lập. Tránh đưa fixture-bin vào `-cp` và dùng `defineClass` có chủ đích.
11. **Không**. Callback trả `null` là observer-only; retransform thành công không đồng nghĩa probe được chèn.
12. **Không**. Cả redefine và retransform đều có thể truyền class object non-null.
13. Để đảm bảo generic dispatch đúng **trước và sau** thao tác, phát hiện regression do bytecode update.
14. Có thể **bỏ bridge và instrument implementation**, hoặc deduplicate logical invocation theo thiết kế; test cả erased dispatch và typed call.
15. Strong reference tới `Class<?>`/ClassLoader có thể ngăn unloading; dùng lifecycle/bounded cache hoặc weak-key/reference đúng chỗ.
16. **Không**. `getAllLoadedClasses` là discovery; modifiability là API riêng và tùy loại class/JVM.

## 18. Kết luận

**Bridge, synthetic, lambda, record, sealed và nhiều class loader** không phải các trường hợp phụ ít gặp: chúng xuất hiện trong ứng dụng Java hiện đại và hệ thống dùng generics, functional APIs, immutable data models, sealed hierarchies và plugin loading. Một agent đáng tin phải biết **đâu là cấu trúc do compiler/JVM sinh ra, đâu là giới hạn thay đổi class, và đâu là danh tính runtime của target**.

Bộ kiểm thử nên kết hợp **reflection + javap + observer Java agent + retransform capability/modifiability + behavior assertions**. Khi tiến tới một bytecode patcher thật, bổ sung verifier, test probe count tránh double instrumentation, và chạy matrix trên compiler/JVM thực tế. **Đừng suy luận bytes đã được thay chỉ vì transformer callback chạy; đừng suy luận hai class cùng tên là cùng một class; đừng suy luận mọi synthetic/hidden class đều có thể instrument theo một cách.**

## 19. Tài liệu kỹ thuật chính thức

- [Java SE 21 — ClassFileTransformer](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): callback khi load/redefine/retransform, vai trò `className`/`loader`/`classfileBuffer`, `return null` và chuỗi bytecode.
- [Java SE 21 — Instrumentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `getAllLoadedClasses`, `isRetransformClassesSupported`, `isModifiableClass`, `retransformClasses`.
- [Java SE 21 — Method](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Method.html): `isBridge()` và `isSynthetic()`.
- [Java SE 21 — Class](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html): `isRecord()`, `getRecordComponents()`, `isSealed()`, `getPermittedSubclasses()`, `isHidden()` và class loader identity.
- [Java SE 21 — RecordComponent](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/RecordComponent.html): record component metadata.
- [Java SE 21 — ClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): `defineClass`, defining class loader và runtime class identity.
- [Java Language Specification 21 — §8.10 Record Classes](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.10): cấu trúc/semantics của record.
- [Java Language Specification 21 — §8.1.1.2 Sealed Classes](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.1.1.2): permitted subtypes và sealed hierarchy.
- [JVM Specification 21 — §4 The class File Format](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html): `ACC_BRIDGE`, `ACC_SYNTHETIC`, `Record` và `PermittedSubclasses` attributes.
- [JVM Tool Interface — RedefineClasses/RetransformClasses](https://docs.oracle.com/en/java/javase/21/docs/specs/jvmti.html): giới hạn thay đổi class schema, danh tính, active frames và class-file transform.

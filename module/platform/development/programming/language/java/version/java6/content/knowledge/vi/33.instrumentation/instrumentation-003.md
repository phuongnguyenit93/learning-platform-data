# ClassFileTransformer và biến đổi bytecode trong Java Instrumentation

## 1. Tổng quan: can thiệp vào class trước khi JVM định nghĩa hoặc tái định nghĩa

Một Java class không được JVM chạy trực tiếp từ source `.java`. Trình biên dịch tạo class file `.class` chứa **bytecode**, constant pool, metadata, methods, fields và các attributes. Trong nhiều tình huống thực tế — tracing, profiler, coverage, APM, kiểm thử, quan sát các thư viện — ta cần thêm hoặc thay hành vi của một class **mà không sửa source gốc**.

Java Instrumentation cung cấp giao diện:

~~~java
public interface ClassFileTransformer
~~~

trong module `java.instrument`, package `java.lang.instrument`. Một Java agent có thể đăng ký transformer bằng `Instrumentation.addTransformer(...)`. Khi JVM chuẩn bị định nghĩa, redefine hoặc retransform một class, transformer nhận **mảng byte chứa class file** và có quyền:

- Trả `null`: **không thay đổi** class ở bước này.
- Trả một `byte[]` **mới và hợp lệ**: dùng bytecode đã biến đổi ở bước tiếp theo.
- Báo lỗi định dạng bằng `IllegalClassFormatException` hoặc exception khác; tuy nhiên **không được dựa vào việc ném exception để chặn class loading**, vì JVM vẫn tiếp tục gọi các transformers còn lại và thử quá trình load/redefine/retransform.

**Điểm cốt lõi:** `ClassFileTransformer` là một cơ chế **biến đổi class-file bytes trước khi áp dụng vào JVM**, không phải reflection, không phải Java source rewrite, không phải proxy cho từng method call, và cũng không tự tạo mới một class loader.

### Khi nào nên học và dùng cơ chế này?

- Instrumentation phục vụ APM: thêm hooks ghi thời gian xử lý/telemetry vào một tập methods.
- Coverage tools: thêm counters trước khi chương trình thực thi.
- Profiling/debugging: quan sát hoặc thay đổi một số code paths trong môi trường được phép.
- Bytecode-level observability: gắn thông tin ở class load/retransform mà không sửa source.
- Testing/mocking frameworks: tùy khả năng runtime, định nghĩa lại implementation trong test.
- Runtime patching có kiểm soát để chẩn đoán, nhưng cần chú ý giới hạn cấu trúc class và bảo mật.

**Không nên** dùng agent để thay business logic một cách tùy tiện trong production nếu sửa source/build bình thường đã đủ. Transformer có thể ảnh hưởng toàn JVM và gây lỗi linkage/verification rất khó truy vết.

### Phạm vi hiện hành theo Special Note

- `ClassFileTransformer` và `Instrumentation` **vẫn là API chính thức** trong Java SE 17 đến 26.
- Method `transform(Module, ClassLoader, String, Class<?>, ProtectionDomain, byte[])` là overload nhận thông tin module, có từ Java 9 và dùng tốt với JPMS.
- **Class-File API chuẩn** `java.lang.classfile` đã hoàn thiện thành API chính thức ở **Java 24** (JEP 484); ví dụ biến đổi thật trong bài dùng Java 24+ để không phụ thuộc thư viện bytecode bên ngoài.
- Đối với Java 17–23, vẫn có thể viết transformer và dùng **ASM/Byte Buddy phiên bản được bảo trì** khi cần thay bytecode; một ví dụ Java 17 độc lập ở cuối bài minh họa vòng đời agent/transformer và ý nghĩa `null`.
- Không dùng các API nội bộ như `jdk.internal.org.objectweb.asm`, cờ `--add-exports` cho JDK internals hoặc những thủ thuật classfile lỗi thời làm giải pháp chính.

## 2. Từ `-javaagent` đến `transform`: toàn bộ đường đi

~~~text
java -javaagent:agent-demo.jar -cp agent-demo.jar DemoApp
                 |
                 v
         JVM loads Java agent
                 |
                 v
      BytecodeAgent.premain(args, inst)
                 |
                 +-- inst.addTransformer(transformer, canRetransform)
                 |
                 v
    Application requests DemoTarget class
                 |
                 v
     JVM has original class-file bytes
                 |
                 +-- transform(Module, ClassLoader, internalName,
                 |             classBeingRedefined, ProtectionDomain,
                 |             byte[] classfileBuffer)
                 |
                 +-- return null       -> leave unchanged at this step
                 |
                 +-- return new bytes  -> feed next transformer / JVM
                 |
                 v
          JVM verifies/defines class
                 |
                 v
           DemoTarget.message()
~~~

Agent được khởi tạo qua `premain` **trước khi ứng dụng chạy `main`**. Một transformer đăng ký đủ sớm sẽ nhìn thấy các class loads phù hợp, trừ các trường hợp đặc biệt do Instrumentation API hoặc JVM áp dụng.

### 2.1. Các vai trò cần phân biệt

| Thành phần | Vai trò |
| --- | --- |
| `javaagent` JAR | Gói agent với manifest chứa entry point |
| `premain(String, Instrumentation)` | Entry point agent ở JVM startup |
| `agentmain(String, Instrumentation)` | Entry point agent được load động vào JVM đang chạy, phụ thuộc policy |
| `Instrumentation` | API quản lý transformers, retransform, redefine, kích thước object... |
| `ClassFileTransformer` | Hàm xử lý một classfile byte array |
| `ClassLoader` | Loader định nghĩa class |
| `Module` | Module của class trong môi trường JPMS |
| `ProtectionDomain` | Ngữ cảnh bảo vệ class theo JVM/security runtime |
| `ClassFile` / `ClassTransform` | Java 24+ API chuẩn để parse, transform và build classfile |
| `Instrumentation.retransformClasses` | Yêu cầu JVM xử lý lại definitions của classes đang load |
| `Instrumentation.removeTransformer` | Gỡ đăng ký transformer khỏi các callback tương lai |
| `Class<?> classBeingRedefined` | Non-null khi callback liên quan redefinition/retransformation; null trong class load bình thường |

**Transformer** không chạy thay class và không tự quản lý vòng đời deployment. Agent cài callback, rồi JVM gọi khi có sự kiện class definition/redefinition phù hợp.

## 3. API chính xác của `ClassFileTransformer`

Trong Java SE 26 có **hai overloads default**.

### 3.1. Overload có module — nên dùng cho code mới

~~~java
@Override
public byte[] transform(
        Module module,
        ClassLoader loader,
        String className,
        Class<?> classBeingRedefined,
        ProtectionDomain protectionDomain,
        byte[] classfileBuffer) {
    // Decide whether to transform and return bytes.
    return null;
}
~~~

Đây là method **snippet**; nó chỉ biên dịch khi đặt trong implementation của `ClassFileTransformer` và import `java.security.ProtectionDomain`.

| Tham số | Ý nghĩa |
| --- | --- |
| `module` | Module của class; dùng để biết module context khi cần |
| `loader` | Defining class loader, có thể `null` với bootstrap class loader |
| `className` | Internal class name (ví dụ `com/example/Service`, không phải `com.example.Service`); có thể cần null-safe handling |
| `classBeingRedefined` | `Class<?>` đang được redefine/retransform; thường null trong load đầu |
| `protectionDomain` | ProtectionDomain gắn với class definition |
| `classfileBuffer` | **Bytes đầu vào không được chỉnh sửa tại chỗ** |

**Lưu ý về tên:** `className` dùng internal form với ký tự `/` cho package. Ví dụ `org/acme/OrderService`, không phải `org.acme.OrderService`. Trong bài chạy độc lập, `DemoTarget` ở default package nên tên internal là `"DemoTarget"`.

### 3.2. Overload năm tham số vẫn được hỗ trợ

~~~java
@Override
public byte[] transform(
        ClassLoader loader,
        String className,
        Class<?> classBeingRedefined,
        ProtectionDomain protectionDomain,
        byte[] classfileBuffer) {
    return null;
}
~~~

Đây là snippet của overload năm tham số. JavaDoc hiện hành cho biết default implementation của overload có `Module` sẽ gọi overload năm tham số nếu người viết không override overload sáu tham số. Cả hai được hỗ trợ; không gán nhãn “đã bị xóa” cho năm tham số.

Tuy nhiên, overload sáu tham số giúp code mới quan sát module và thể hiện rõ môi trường Java module system. Một implementation có thể override **một** overload phù hợp; tránh override cả hai theo cách gây xử lý hai lần không mong muốn.

### 3.3. Interface không nhất thiết là functional interface

Do cả hai overload đều là `default` trên Java hiện hành, không nên giả định:

~~~java
ClassFileTransformer transform = (loader, name, cls, domain, bytes) -> null;
~~~

sẽ hợp lệ. Trong ví dụ chạy, chúng ta dùng **anonymous implementation** hoặc một class implements interface có `@Override transform(...)`. Cần xác minh có single abstract method trước khi dùng lambda; ở đây transformer interface hiện hành **không có abstract method như functional interface**.

## 4. Ba kiểu kết quả của callback

| Hành vi | Ý nghĩa | Khi nào dùng |
| --- | --- | --- |
| `return null` | Không thực hiện thay đổi ở bước của transformer | Không đúng class mục tiêu; no-op, capability gating |
| `return newBytes` | Giao bản classfile thay thế cho transformer/JVM | Chỉ sau khi parse/transform/build thành công |
| Ném exception | Bị ghi nhận/đối xử như không biến đổi đối với callback đó; JVM có thể tiếp tục | Lỗi không mong muốn; nên log có kiểm soát và fail theo policy app |

Đừng sửa nội dung của `classfileBuffer`:

~~~java
// KHÔNG LÀM
classfileBuffer[0] = 0;
return classfileBuffer;
~~~

Đây là **anti-pattern không an toàn** (không phải đoạn mã để chạy). JavaDoc yêu cầu input buffer **không được sửa**. JVM/những transformers tiếp theo có thể dựa vào dữ liệu ban đầu/chuỗi transform, và classfile bị hỏng thường dẫn tới `ClassFormatError` hoặc lỗi khác.

Khi biến đổi:

~~~java
byte[] transformed = transformUsingClassFileApi(classfileBuffer);
return transformed;
~~~

Đây là **snippet**; method `transformUsingClassFileApi` đại diện cho implementation có kiểm tra ở mục 11. `transformed` phải là bytes của một **well-formed class file** hợp lệ, không phải text của source Java hay serialization tùy ý.

### 4.1. Thứ tự và tác động khi transformer ném exception

JavaDoc nêu: nếu transformer ném exception không được bắt, những transformers tiếp theo vẫn có thể được gọi và class load/retransform vẫn được thử, tương tự tình huống trả `null` ở bước này. Vì vậy:

- Không dùng `throw new SecurityException(...)` bên trong transformer như một access-control mechanism chống class loading.
- Không mong exception đơn lẻ làm JVM rollback những transforms khác.
- Trong công cụ production, log nguyên nhân có kiểm soát, giới hạn thông tin, và có cơ chế disable/rollback agent theo runbook.
- Nếu classfile malformed, có thể ném `IllegalClassFormatException` để biểu thị lỗi định dạng; nhưng điều đó **không phải cam kết chặn JVM loading**.

### 4.2. Một transformer nên null-safe và narrowly scoped

~~~java
if (!"com/example/Target".equals(className)) {
    return null;
}
~~~

Viết theo chiều `"constant".equals(className)` tránh `NullPointerException` khi name không sẵn có. Trong service lớn, bộ lọc nên xét cả **loader/module/protection domain** khi có các class cùng internal name ở nhiều class loaders. Không biến đổi mọi `java/*` hay classes của agent nếu không có thiết kế bootstrap instrumentation chuyên biệt.

## 5. Instrumentation.addTransformer và hai chế độ đăng ký

~~~java
instrumentation.addTransformer(transformer);
~~~

tương đương:

~~~java
instrumentation.addTransformer(transformer, false);
~~~

Lựa chọn `false` là **không có khả năng retransformation callback** khi lớp đã được định nghĩa. Transformer vẫn có thể được gọi trong **initial loads** và **redefinitions**.

Nếu muốn transformer tham gia retransformation:

~~~java
if (instrumentation.isRetransformClassesSupported()) {
    instrumentation.addTransformer(transformer, true);
} else {
    instrumentation.addTransformer(transformer, false);
}
~~~

Đây là snippet. Điều kiện JVM hỗ trợ retransformation phải **được kiểm tra**; truyền `true` khi unsupported làm `addTransformer` ném `UnsupportedOperationException`.

### 5.1. Manifest cũng phải cho phép

Java agent JAR cần manifest có:

~~~text
Manifest-Version: 1.0
Premain-Class: BytecodeAgent
Can-Retransform-Classes: true
~~~

JavaDoc `Instrumentation.isRetransformClassesSupported()` cho biết capability cần cả manifest `Can-Retransform-Classes: true` **và** hỗ trợ từ JVM. Chỉ bật flag trong source code hoặc chỉ thêm manifest **chưa đủ** nếu cấu hình JVM không cho phép.

Các manifest attributes đáng biết:

| Attribute | Vai trò |
| --- | --- |
| `Premain-Class` | Agent entry point cho startup `-javaagent` |
| `Agent-Class` | Entry point cho dynamic attach `agentmain`, nếu workflow cho phép |
| `Can-Retransform-Classes` | Xin quyền dùng `retransformClasses` |
| `Can-Redefine-Classes` | Xin quyền `redefineClasses` |
| `Can-Set-Native-Method-Prefix` | Capability chuyên biệt cho native method prefix; không cần trong ví dụ |

Không ghi capabilities không cần thiết. Quyền Instrumentation có thể thay đổi behavior của mọi code trong process; nên dùng nguyên tắc **least privilege** và ưu tiên startup agent được kiểm soát.

### 5.2. Trật tự các transformer khi có nhiều agent

Theo JavaDoc, transformations được áp theo bốn nhóm:

1. Java transformers **không retransform-capable**.
2. Native transformers **không retransform-capable**.
3. Java transformers **retransform-capable**.
4. Native transformers **retransform-capable**.

Trong cùng mỗi nhóm, theo thứ tự đăng ký. Kết quả `byte[]` của transformer trước trở thành `classfileBuffer` của transformer tiếp theo. Nếu một transformer trả `null`, bytes hiện tại được giữ.

**Đừng giả định kết quả của hai transformers luôn giao hoán.** Nếu A thay method rồi B cần một bytecode pattern cũ, B có thể không tìm được chỗ chèn. Khi sử dụng nhiều agents (coverage + APM + test mocking), cần kiểm **tính tương thích của chuỗi** và thứ tự.

## 6. Load-time transformation, redefine và retransform khác nhau ra sao?

| Kiểu thay đổi | Cơ chế kích hoạt | Input cơ bản | Điều cần nhớ |
| --- | --- | --- | --- |
| **Initial class load** | JVM định nghĩa class lần đầu | Bytes từ class loader/VM | Transformer được đăng ký trước mới thấy |
| **Redefinition** | `Instrumentation.redefineClasses(definitions)` | Bytes do caller truyền trong `ClassDefinition` | Cần capability redefine riêng |
| **Retransformation** | `Instrumentation.retransformClasses(loadedClass)` | Baseline bytes của class theo JVM, kèm transforms từ non-capable transformers đã được lưu | Không đơn giản là sửa `byte[]` hiện đang active rồi nối chồng |
| **Remove transformer** | `removeTransformer(transformer)` | Không tự có classfile mới | Ngừng callback tương lai, không lập tức rollback những class đã biến đổi |

### 6.1. Lớp đã load trước khi đăng ký agent?

Nếu transformer được đăng ký sau khi `DemoTarget` đã load, **nó không retroactively tác động** lên class chỉ vì `addTransformer` được gọi. Cần dùng `retransformClasses` nếu được hỗ trợ, class modifiable, và transformer được đăng ký `canRetransform=true`. Đây là lý do startup `-javaagent` thường dễ dự đoán hơn dynamic attach trong production.

### 6.2. `isModifiableClass(type)` là kiểm tra cần thiết

~~~java
if (inst.isRetransformClassesSupported()
        && inst.isModifiableClass(Target.class)) {
    inst.retransformClasses(Target.class);
}
~~~

Đây là snippet, `inst` từ `premain` và `Target` là class ứng dụng. Có class không thể sửa tại runtime; đừng chỉ dựa vào tên class hoặc việc method đang chạy để suy luận có thể retransform.

### 6.3. Retransformation không phải “lấy bytes mới nhất rồi vá tiếp”

JavaDoc `retransformClasses` mô tả:

1. Bắt đầu từ **initial class file bytes** của class (hoặc bytes của lần redefine gần nhất), có thể không byte-for-byte giống input do JVM constant pool normalization.
2. **Không gọi lại** những transformers được đăng ký với `canRetransform=false`; thay vào đó JVM **tự áp lại kết quả đã lưu** của các transformers không capable.
3. Gọi lại những transformers `canRetransform=true`.
4. Ghép kết quả và xác minh/áp dụng định nghĩa mới.

Vì vậy một transformer should work **deterministically with baseline semantics**, không mặc định `classfileBuffer` chứa chính bytes do lần invocation của mình vừa xuất ra.

### 6.4. Active stack frames và static fields

Khi một method đang chạy được retransform:

- Các stack frames đang active có thể tiếp tục dùng phiên bản bytecode cũ đến khi method returns; **lời gọi mới** dùng phiên bản mới.
- Field values (kể cả static fields) **không tự reset**.
- Class initializer `<clinit>` **không tự chạy lại**.
- Instances hiện có vẫn là instances của class đó; không tự recreate.

Đừng dùng retransformation để “reset state” hay hứa rằng mọi thread đang thực thi lập tức chuyển code path mới.

### 6.5. Giới hạn cấu trúc class khi retransform/redefine

Khả năng retransform không đồng nghĩa có thể tùy tiện:

- Thêm/xóa fields.
- Thêm/xóa methods.
- Đổi method/field signatures.
- Đổi inheritance/hierarchy.
- Thay cấu trúc class vượt giới hạn JVMTI.

Những thay đổi như vậy có thể bị `UnsupportedOperationException`, `UnmodifiableClassException`, `ClassFormatError` hoặc verification/linkage errors tùy cách thực hiện và đường API. Thông thường chỉ thay **method bodies** với cấu trúc ngoài tương thích. Ví dụ ở mục 11 chỉ thay một `ldc` string trong method đã tồn tại, đáp ứng nguyên tắc này.

## 7. Class-File API: cách chuẩn để biến đổi bytecode từ Java 24

Trước Java 24, ứng dụng thường dùng ASM, Byte Buddy, BCEL hoặc thư viện tương tự để hiểu ClassFile format. Java 24 đưa một API chuẩn chính thức:

~~~java
import java.lang.classfile.ClassFile;
import java.lang.classfile.ClassTransform;
import java.lang.classfile.instruction.ConstantInstruction;
~~~

**Không cần `--enable-preview`** khi dùng Java 24 final Class-File API, và không cần package nội bộ `jdk.internal.*`. API biểu diễn classfile thành các models/elements và builders.

Một transformation điển hình:

~~~text
classfileBuffer (input bytes)
        |
        v
ClassFile.of().parse(bytes)
        |
        v
ClassModel
        |
        v
ClassTransform.transformingMethodBodies(...)
        |
        v
CodeTransform on each CodeElement
        |
        v
ClassFile.of().transformClass(...)
        |
        v
new byte[] (valid classfile bytes)
~~~

### 7.1. Target một method cụ thể

~~~java
ClassTransform.transformingMethodBodies(
        method -> method.methodName().equalsString("message"),
        (builder, element) -> {
            if (element instanceof
                    ConstantInstruction.LoadConstantInstruction c
                    && "ORIGINAL".equals(c.constantValue())) {
                builder.ldc("PATCHED-1");
            } else {
                builder.with(element);
            }
        })
~~~

Đây là snippet của Class-File API Java 24+.

- Predicate kiểm **tên method** `message`.
- `ConstantInstruction.LoadConstantInstruction` đại diện các instructions lấy constant từ pool, như `ldc`.
- `constantValue()` trả constant value; với chuỗi literal trong demo ta so `"ORIGINAL"`.
- `builder.ldc("PATCHED-1")` tạo instruction mới load literal khác.
- `builder.with(element)` giữ nguyên phần còn lại của method body.

Điểm mạnh là không tự viết offset bytes, không giả định vị trí constant pool index và không chỉnh buffer input tại chỗ. API xây lại class file phù hợp Java classfile rules.

### 7.2. Đây là biến đổi bytecode thật, không sửa source text

Nếu source code là:

~~~java
public static String message() {
    return "ORIGINAL";
}
~~~

JVM biên dịch thành bytecode đại ý:

~~~text
ldc "ORIGINAL"
areturn
~~~

Class-File API thay `ldc` sang chuỗi mới. Không thay `DemoTarget.java`, không thay method signature `()Ljava/lang/String;` và không thay `.class` đang nằm trong JAR trên ổ đĩa. Hiệu ứng nằm ở **class definition của JVM đang chạy**.

### 7.3. Vì sao phải sửa đúng “Code” thay vì tìm/replace bytes tùy ý?

Một chuỗi UTF-8 như `ORIGINAL` có thể xuất hiện ở constant pool, attributes hoặc metadata, có thể có nhiều references khác nhau. Tìm và thay mảng byte thô:

- Dễ sửa nhầm constant được dùng ở nhiều methods.
- Có thể phá length prefix và encoding.
- Có thể làm classfile invalid nếu độ dài literal khác nhau.
- Không xử lý constant pool, labels, StackMapTable, exception tables, frame metadata.
- Không bền vững khi compiler/JDK đổi layout.

Class-File API xử lý cấu trúc có kiểu. Với thay đổi sâu hơn (insert control flow, try/finally, method calls), cần nắm stack maps, type safety, exception handling và side effects; không chỉ tìm vài bytes rồi patch.

## 8. Ví dụ #1 — **Java agent biến đổi thật** trên Java 24+

Bài chạy đầy đủ gồm:

- `BytecodeAgent.java` — agent premain, transformer và API điều khiển thử nghiệm.
- `DemoTarget.java` — class ứng dụng, trả chuỗi `"ORIGINAL"`.
- `DemoApp.java` — app quan sát trước/sau retransformation.
- `manifest.mf` — khai báo entry point/capability.
- `agent-demo.jar` — JAR build từ ba source files.

**Thiết kế kiểm thử:**

1. Agent được đăng ký từ `premain` trước khi class `DemoTarget` được load.
2. Transformer chỉ xử lý `"DemoTarget"`; mọi class khác `return null`.
3. Lần load đầu, transformer thấy literal `"ORIGINAL"` và thay thành `"PATCHED-1"`.
4. App gọi `DemoTarget.message()` và xác nhận kết quả mới.
5. App kiểm `isRetransformClassesSupported()` rồi gọi `retransformClasses(DemoTarget.class)`.
6. JVM gọi transformer lại với baseline classfile; literal gốc là `"ORIGINAL"`, nên lần này nó tạo `"PATCHED-2"`.
7. App gỡ transformer bằng `removeTransformer`; hành vi hiện hành **chưa tự trở về ORIGINAL**.
8. App yêu cầu một lần `retransformClasses` nữa **sau khi transformer đã bị gỡ**; trong demo cô lập không còn transformers khác, JVM đưa method về bản gốc `"ORIGINAL"`.
9. Mọi bước đều dùng assertions; thất bại sẽ làm tiến trình lỗi, không chỉ in kết quả “true” giả.

### 8.1. `BytecodeAgent.java` — source đầy đủ

~~~java
import java.lang.classfile.ClassFile;
import java.lang.classfile.ClassTransform;
import java.lang.classfile.instruction.ConstantInstruction;
import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;
import java.util.concurrent.atomic.AtomicInteger;

public final class BytecodeAgent {
    private static volatile Instrumentation instrumentation;
    private static volatile ClassFileTransformer installedTransformer;
    private static final AtomicInteger TRANSFORM_COUNT =
            new AtomicInteger();

    public static void premain(
            String options, Instrumentation inst) {
        instrumentation = inst;
        boolean retransform =
                inst.isRetransformClassesSupported();

        ClassFileTransformer transformer =
                new ClassFileTransformer() {
            @Override
            public byte[] transform(
                    Module module,
                    ClassLoader loader,
                    String internalName,
                    Class<?> redefining,
                    ProtectionDomain domain,
                    byte[] bytes) {
                if (!"DemoTarget".equals(internalName)) {
                    return null;
                }

                int generation =
                        TRANSFORM_COUNT.incrementAndGet();
                ClassFile classFile = ClassFile.of();

                return classFile.transformClass(
                        classFile.parse(bytes),
                        ClassTransform.transformingMethodBodies(
                                method -> method.methodName()
                                        .equalsString("message"),
                                (builder, element) -> {
                                    if (element instanceof
                                            ConstantInstruction
                                                    .LoadConstantInstruction c
                                            && "ORIGINAL".equals(
                                                    c.constantValue())) {
                                        builder.ldc(
                                                "PATCHED-" + generation);
                                    } else {
                                        builder.with(element);
                                    }
                                }));
            }
        };

        inst.addTransformer(transformer, retransform);
        installedTransformer = transformer;
    }

    public static boolean installed() {
        return instrumentation != null
                && installedTransformer != null;
    }

    public static boolean canRetransform() {
        return instrumentation
                .isRetransformClassesSupported();
    }

    public static void retransform(Class<?> type)
            throws Exception {
        if (!canRetransform()
                || !instrumentation.isModifiableClass(type)) {
            throw new IllegalStateException(
                    "Not retransformable");
        }
        instrumentation.retransformClasses(type);
    }

    public static boolean remove() {
        return instrumentation.removeTransformer(
                installedTransformer);
    }

    public static int transformations() {
        return TRANSFORM_COUNT.get();
    }
}
~~~

**Lưu ý:**

- `ClassFile.of()`, `ClassTransform` và `ConstantInstruction` yêu cầu **Java 24+**; không copy vào project đang biên dịch `--release 17`.
- `TRANSFORM_COUNT` là shared state chỉ dành cho demo; production transformer nên tránh dựa vào thứ tự load/retransform giữa các classes/threads để quyết định business policy.
- Filter chỉ chọn tên `"DemoTarget"` để demo đơn giản. Trong ứng dụng có nhiều classloaders, nên xác minh loader/module/PD và contract.
- `classBeingRedefined` / `redefining` có thể cho biết load đầu hay retransform; demo không dựa vào nó, vì đổi chuỗi dựa trên baseline.
- Code không thực hiện I/O, gọi network hoặc tải chính `DemoTarget` từ transformer, giúp tránh class loading recursion.
- Nếu JVM không hỗ trợ retransformation, callback được add dưới chế độ false nhưng `DemoApp` sẽ fail ở bước assertion; đó là chủ ý của test, không phải crash ngẫu nhiên.

### 8.2. `DemoTarget.java` — class bị biến đổi

~~~java
public final class DemoTarget {
    public static String message() {
        return "ORIGINAL";
    }
}
~~~

Source và `.class` trên disk vẫn có literal `ORIGINAL`. Chỉ definition trong JVM khi agent tham gia mới thay.

### 8.3. `DemoApp.java` — ứng dụng kiểm chứng

~~~java
public final class DemoApp {
    private static void check(boolean ok, String detail) {
        if (!ok) {
            throw new AssertionError(detail);
        }
    }

    public static void main(String[] args)
            throws Exception {
        check(BytecodeAgent.installed(),
                "premain not installed");
        System.out.println(
                "Startup premain installed: true");

        String first = DemoTarget.message();
        check("PATCHED-1".equals(first),
                "load-time patch failed: " + first);
        System.out.println(
                "First class load message: " + first);

        check(BytecodeAgent.canRetransform(),
                "retransform unavailable");
        System.out.println(
                "Retransformation supported: true");

        BytecodeAgent.retransform(DemoTarget.class);
        String second = DemoTarget.message();
        check("PATCHED-2".equals(second),
                "retransform failed: " + second);
        System.out.println(
                "After retransform message: " + second);

        check(BytecodeAgent.transformations() == 2,
                "wrong transform count");
        System.out.println(
                "Target transformer invocations: 2");

        check(BytecodeAgent.remove(),
                "removeTransformer failed");
        check("PATCHED-2".equals(DemoTarget.message()),
                "removal must not reverse current definition");
        System.out.println(
                "removeTransformer keeps active bytecode: true");

        BytecodeAgent.retransform(DemoTarget.class);
        check("ORIGINAL".equals(DemoTarget.message()),
                "retransform without agent should restore original");
        System.out.println(
                "Retransform without transformer restores original: true");

        System.out.println(
                "Only class DemoTarget was transformed: true");
    }
}
~~~

### 8.4. Manifest `manifest.mf`

~~~text
Manifest-Version: 1.0
Premain-Class: BytecodeAgent
Can-Retransform-Classes: true
~~~

Để một **dòng trống ở cuối manifest** theo định dạng JAR Manifest. `Premain-Class` phải chỉ tới class có `premain` static hợp lệ. `Can-Retransform-Classes: true` xin capability; JVM vẫn có thể không hỗ trợ tùy environment.

### 8.5. Build và chạy (PowerShell/macOS/Linux shell)

Đặt bốn file `BytecodeAgent.java`, `DemoTarget.java`, `DemoApp.java` và `manifest.mf` trong cùng thư mục. Các lệnh sau chạy từ thư mục chứa chúng:

~~~sh
javac --release 24 BytecodeAgent.java DemoTarget.java DemoApp.java

jar cfm agent-demo.jar manifest.mf \
  BytecodeAgent.class 'BytecodeAgent$1.class' \
  DemoTarget.class DemoApp.class

java -javaagent:agent-demo.jar -cp agent-demo.jar DemoApp
~~~

Lệnh `jar` ở trên viết trên nhiều dòng kiểu shell POSIX. Nếu dùng **Windows PowerShell**, dùng **một dòng** tương đương để không cần backslash continuation:

~~~powershell
jar cfm agent-demo.jar manifest.mf BytecodeAgent.class 'BytecodeAgent$1.class' DemoTarget.class DemoApp.class
java -javaagent:agent-demo.jar -cp agent-demo.jar DemoApp
~~~

Với command prompt Windows `cmd.exe`, dùng quoting thích hợp thay vì giữ nguyên single quotes dành cho shell/PowerShell. File `BytecodeAgent$1.class` là compiled anonymous transformer class; cần đóng gói nó trong JAR cùng `BytecodeAgent.class`.

**Đã chạy thử trên JDK 24 thực tế:** compile `javac --release 24`, `jar cfm` và launch `-javaagent` đều thành công.

### 8.6. Stdout chính xác — 8 dòng

~~~text
Startup premain installed: true
First class load message: PATCHED-1
Retransformation supported: true
After retransform message: PATCHED-2
Target transformer invocations: 2
removeTransformer keeps active bytecode: true
Retransform without transformer restores original: true
Only class DemoTarget was transformed: true
~~~

Các kết quả này đã **được xác minh khi chạy** với JVM hỗ trợ retransformation. Không mở JMX remote, không attach vào process ngoài, không sửa repository. Thử nghiệm build trong thư mục tạm và dọn tài nguyên sau kiểm tra.

### 8.7. Vì sao `PATCHED-2` không phải `PATCHED-1` bị vá thêm?

Trong `transform(...)`, đoạn kiểm literal luôn tìm `"ORIGINAL"`. Nếu JVM đưa input đang chứa `PATCHED-1` rồi transformer chỉ thay `ORIGINAL`, lần thứ hai sẽ không tìm được literal và app không thể nhận `PATCHED-2`.

Thực tế test nhận `PATCHED-2`; điều đó phù hợp với JavaDoc `retransformClasses`: callback capable được gọi trên baseline bytes (cộng các non-capable transforms có thể có), **không phải cứ nối biến đổi lên output lần trước**. `generation` là bộ đếm phụ để phân biệt những invocation; không phải cách patch class an toàn trong production.

### 8.8. Vì sao `removeTransformer` không hoàn nguyên ngay?

`Instrumentation.removeTransformer(...)` gỡ đăng ký callback cho class definitions/retransformations tương lai. Nó **không tự kích hoạt** một retransformation và không lập tức thay bytes của class đã được JVM định nghĩa.

Trong demo:

~~~text
INITIAL class bytes      : ORIGINAL
After transformer call 1 : PATCHED-1
After transformer call 2 : PATCHED-2
After removeTransformer  : PATCHED-2 (current class remains active)
After explicit retransform without active transformer : ORIGINAL
~~~

**Giới hạn của ví dụ:** Bước cuối quay về ORIGINAL bởi vì JAR thử nghiệm chỉ có **một** transformer capable và không có transformer khác can thiệp. Trong hệ thống thật có thể còn các transformers non-capable, native hooks, redefine events và baseline khác. Không hứa `retransformClasses` sau khi remove sẽ luôn khôi phục đúng original disk bytes trong mọi runtime.

### 8.9. Bài học về class-file validity

Class-File API chuyển một instruction load String literal nhưng **giữ method signature, số fields/methods và inheritance**. Đó là một dạng instrumentation thường tương thích với retransformation constraints.

Nếu sửa tùy tiện method descriptor hoặc thay class hierarchy trong `retransformClasses`, JVM có thể từ chối. Nếu input bytes không hợp lệ, có thể gặp `ClassFormatError`, `VerifyError` hoặc class loading failures. Đừng đem code transformer chưa kiểm chứng trên mọi target version vào production.

## 9. Ví dụ #2 — vòng đời agent/transformer chỉ với Java 17

Trong dự án chưa lên Java 24, `ClassFileTransformer` vẫn hoạt động; khác biệt là **không có Class-File API chuẩn**. Phần này dùng Java 17 để minh họa:

- Agent đăng ký một transformer nhận Module/Loader/ClassName.
- Filter đúng class `ObservedTarget`.
- Đặt một flag khi JVM load class.
- **Trả null** để giữ nguyên bytecode.
- App xác nhận phương thức thật của class không bị thay.

Điều này **không phải demo bytecode patching**; nó là **smoke test Agent lifecycle và return-null contract**. Muốn thực sự patch bytecode trên Java 17, dùng ASM/Byte Buddy tương thích với JDK/bytecode version và kiểm class verification; không lấy API nội bộ JDK.

### 9.1. `ObserveAgent.java`

~~~java
import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;

public final class ObserveAgent {
    private static volatile boolean observed;

    public static void premain(
            String args, Instrumentation inst) {
        inst.addTransformer(new ClassFileTransformer() {
            @Override
            public byte[] transform(
                    Module module,
                    ClassLoader loader,
                    String className,
                    Class<?> classBeingRedefined,
                    ProtectionDomain domain,
                    byte[] classfileBuffer) {
                if ("ObservedTarget".equals(className)) {
                    observed = true;
                }
                return null;
            }
        });
        System.out.println(
                "Observation agent installed: true");
    }

    public static boolean observed() {
        return observed;
    }
}
~~~

`observed` là `volatile` vì class loads có thể xảy ra qua nhiều threads. Trong demo chỉ một target được load có kiểm soát, nhưng shared data của transformer vẫn phải xét thread visibility.

### 9.2. `ObservedTarget.java`

~~~java
public final class ObservedTarget {
    public static String greet() {
        return "HELLO";
    }
}
~~~

### 9.3. `ObserveApp.java`

~~~java
public final class ObserveApp {
    public static void main(String[] args) {
        String value = ObservedTarget.greet();
        if (!"HELLO".equals(value)) {
            throw new AssertionError(
                    "Unexpected class transformation");
        }
        System.out.println(
                "Original target result: " + value);

        if (!ObserveAgent.observed()) {
            throw new AssertionError(
                    "Class load was not observed");
        }
        System.out.println(
                "Transformer saw target and returned null: true");
    }
}
~~~

### 9.4. Manifest và lệnh chạy

`manifest.mf` cho ví dụ Java 17:

~~~text
Manifest-Version: 1.0
Premain-Class: ObserveAgent
~~~

Biên dịch:

~~~sh
javac --release 17 ObserveAgent.java ObservedTarget.java ObserveApp.java
~~~

Đóng gói trên shell POSIX:

~~~sh
jar cfm observe.jar manifest.mf \
  ObserveAgent.class 'ObserveAgent$1.class' \
  ObservedTarget.class ObserveApp.class

java -javaagent:observe.jar -cp observe.jar ObserveApp
~~~

Trong PowerShell, một dòng để tạo JAR:

~~~powershell
jar cfm observe.jar manifest.mf ObserveAgent.class 'ObserveAgent$1.class' ObservedTarget.class ObserveApp.class
java -javaagent:observe.jar -cp observe.jar ObserveApp
~~~

**Stdout đã chạy thật trên JDK24 với Java 17 source compatibility — 3 dòng:**

~~~text
Observation agent installed: true
Original target result: HELLO
Transformer saw target and returned null: true
~~~

Bài thử chứng minh transformer **nhìn thấy class load** nhưng không biến đổi bytes, vì `return null`. Nó không cần `Can-Retransform-Classes` vì không gọi `retransformClasses`.

## 10. Java 17–23: khi nào nên chọn ASM hoặc Byte Buddy?

Nếu ứng dụng chạy trên Java 17 và cần biến đổi bytecode thực sự, những hướng phổ biến vẫn hợp lệ:

| Hướng | Ưu điểm | Giới hạn |
| --- | --- | --- |
| **ASM** (phiên bản đang được bảo trì) | Kiểm soát instructions, visitors, class file versions | Cần hiểu JVMS, stack maps, frames và constant pools |
| **Byte Buddy** (phiên bản phù hợp runtime) | Abstraction mức cao cho method interception/delegation | Có dependency, integration rules và version compatibility |
| **Class-File API chuẩn** | Không cần thư viện ngoài, mô hình typed/class transforms | Yêu cầu **Java 24+** |
| Tự sửa `byte[]` thô | Không có lợi ích bền vững | Không khuyến nghị; dễ phá classfile |
| Internal `jdk.internal.org.objectweb.asm` | Có sẵn trong một số JDK | **Không phải public supported API**, không khuyến nghị |

Các thư viện bytecode ngoài cần chọn phiên bản mới phù hợp classfile major version. Ví dụ JDK 26 có những classfile version mới; ASM/Byte Buddy cũ có thể không parse được. Trong ứng dụng production, pin và test dependency versions; **không** lấy phiên bản cụ thể từ một bài blog lỗi thời rồi coi là luôn tương thích.

### 10.1. Class-File API không tự thay mọi vấn đề verification

Dù là API chuẩn, người viết vẫn phải hiểu:

- JVM operand stack và local variables.
- Method descriptors và return types.
- Exception tables/try-catch/finally behavior.
- Control-flow branches và StackMapTable frames.
- Constant pool references; classfile version compatibility.
- Class initialization vs loading.
- Class loader, module readability, bootstrap classes.
- Java memory model và thread-safety nếu agent thêm hooks/counters.

API mới giúp biểu diễn/generate classfile đúng cấu trúc, nhưng không đảm bảo **logic nghiệp vụ** của transformation là an toàn.

## 11. Nhiều transformers, state và idempotence

### 11.1. Chain có thể làm thay đổi đầu vào của transformer phía sau

Giả sử hai transformers:

~~~text
Original bytes
     |
     v
Transformer A: wraps method call with timing
     |
     v
Transformer B: searches for original method pattern
     |
     v
Final bytes installed
~~~

Nếu B giả định method body vẫn y hệt source gốc, nó có thể không tìm thấy pattern nữa. Các libs như APM, coverage, mocking nên được test cùng nhau với các thứ tự/capabilities đã dự định.

### 11.2. Tránh biến đổi lặp không kiểm soát

Với retransform callback có thể chạy lại, logic phải bảo đảm **valid output** cho mỗi invocation. Một transformer chèn code ở mỗi lần có thể làm method dài ra hoặc duplicate instrumentation nếu input/call semantics bị hiểu sai.

Hướng an toàn:

- Bắt đầu từ classfile model đúng baseline.
- Chỉ transform methods/classes đã được allowlist.
- Nhận diện rõ version của instrumentation nếu cần.
- Không dựa vào global mutable counters để quyết định production behavior.
- Kiểm classfile sau mỗi lần (load, retransform, redefine) với regression tests.
- Không chèn duplicate hooks nếu cùng instrumentation layer có thể chạy lặp.

Trong demo Java24, `TRANSFORM_COUNT` chỉ giúp thấy **hai lần callback**; không phải cơ chế đánh version classfile cho hệ thống thật.

### 11.3. Transformer có thể được gọi đồng thời

Nhiều threads load classes cùng lúc; implementation phải xem `transform(...)` là code có thể bị gọi **concurrently**. Tránh state mutable không synchronized. Dùng immutable configuration, concurrent collections hoặc atomic primitives nếu cần counters, và không giữ global locks lâu trong callback.

Đừng làm blocking I/O hoặc network calls trong transformer vì class loading thường nằm trên đường khởi động quan trọng; side effects có thể gây deadlock/timeout.

### 11.4. `removeTransformer` không phải synchronization barrier tuyệt đối

JavaDoc nêu có thể còn callbacks “in flight” **sau khi removeTransformer trả về** do class loading đồng thời. Transformer cần tolerate callbacks late, nhất là khi resources đã được release. Không lập logic “remove thành công nghĩa là không invocation nào còn chạy” nếu không có synchronization ngoài.

## 12. Bảo vệ JVM khỏi class loading recursion và LinkageError

Một transformer chạy **trong lúc JVM đang định nghĩa class**. Nếu callback cho class `C` lại vô tình load/resolve chính `C` trước khi C sẵn sàng, JVM có thể ném `LinkageError`. Lỗi xảy ra trong quá trình resolution còn có thể khiến dependent class `D` rơi vào trạng thái lỗi resolution lâu dài.

**Các nguyên tắc an toàn:**

1. Giữ agent code đơn giản, có dependencies tối thiểu.
2. Không gọi `Class.forName(className)` với chính target trong `transform(...)`.
3. Không invoke target class methods/reflection của target khi đang transform class đó.
4. Tránh instrument chính classes của Class-File API, agent, logging hoặc core JVM trừ khi cần và biết chính xác thứ tự bootstrap.
5. Không chạy network requests/database calls trong callback.
6. Sử dụng filter theo internal name, loader, module để hạn chế scope.
7. Có fail-safe logging không tạo vòng load thêm classes của target.
8. Tránh instrumentation các classes trong package `java.*` khi không thật sự cần; core JDK transformers rất dễ gây circularity/linkage failure.
9. Kiểm initialization order của agent dependencies; nếu dùng thư viện bên ngoài, đảm bảo chúng được đóng gói và class-loaded đúng cách.
10. Giám sát class load latency và overhead dưới tải thực tế.

Trong bài chạy Java24, transformer chỉ parse/build `DemoTarget`, không tự gọi `DemoTarget.message()` từ callback, giảm nguy cơ recursion.

## 13. Redefinition/transform verification và các lỗi khó phân biệt

| Lỗi | Khi có thể xảy ra | Cách xử lý |
| --- | --- | --- |
| `IllegalClassFormatException` | Transformer phát hiện classfile malformed | Log/capture, không tự tin exception chặn load |
| `ClassFormatError` | JVM nhận class file format không hợp lệ | Kiểm builder/constant pool/classfile version |
| `VerifyError` | Bytecode không qua verifier, stack/type flows sai | Sửa frame/control-flow/operand types |
| `UnsupportedClassVersionError` | Sinh major version cao hơn runtime cho phép | Build đúng target runtime |
| `UnmodifiableClassException` | Class không thể redefine/retransform | Kiểm `isModifiableClass` |
| `UnsupportedOperationException` | JVM không hỗ trợ capability được yêu cầu | Kiểm `isRetransformClassesSupported` |
| `NoClassDefFoundError` | Agent/transformed code tham chiếu class không có | Kiểm class loaders/module dependencies |
| `ClassCircularityError` / `LinkageError` | Recursion/circular resolution trong transform | Giảm agent dependencies, tránh target self-load |
| `IllegalAccessError` | Bytecode mới truy cập member/module không được phép | Kiểm access/module rules |
| `NoSuchMethodError` | Sinh call site sai descriptor/version | Đồng bộ class/member versions |
| Agent `premain` không chạy | Manifest sai, `-javaagent` không được đặt | Kiểm JAR manifest, startup flags |
| Không thấy target biến đổi | Target load trước, filter sai, transformer chưa add | Kiểm internal name/loader, capability |
| Transformer trả `null` | Không chọn target hoặc intentionally no-op | Đúng nếu không cần thay |
| Retransform không đổi behavior | Capability không có, new bytes tương đương, active frames cũ | Kiểm semantics, test invocation mới |
| Sau remove vẫn thấy bytes đã vá | remove không tự rollback | Có kế hoạch retransform/rollout/restart |
| Startup lâu | Transformer quá nặng hoặc load quá nhiều classes | Scope filter, cache hợp lý, profiler |

### 13.1. Vì sao exception từ transformer không dùng làm fail-closed policy?

ClassFileTransformer JavaDoc nói rõ transformer exception được xử lý tương tự return `null` và các transformers sau vẫn được gọi. Nếu yêu cầu policy “JVM tuyệt đối không được chạy class chưa instrument” trong môi trường nhạy cảm, cần thiết kế **cơ chế xác minh ở startup/build/runtime boundary khác**, thay vì trông chờ exception từ callback chặn class definition.

### 13.2. Test bytes, không chỉ test log

Một log như `"transform called"` chỉ chứng minh JVM **gọi callback**, không chứng minh bytes được chấp nhận hoặc behavior đã thay. Nên:

- Kiểm output class bytes có well-formed magic/version/metadata.
- Chạy thực tế method behavior trước/sau.
- Kiểm class verification và expected exceptions.
- Test retransform/redefine nếu agent hỗ trợ.
- Test nhiều transformers và classloaders.
- Test classes không nằm trong filter không bị ảnh hưởng.
- Test class load latency và memory under load.

Ví dụ `DemoApp` kiểm đúng `"PATCHED-1"` và `"PATCHED-2"`, không chỉ in callback count.

## 14. Startup agent so với dynamic attach sau Java 21

JDK 21 có **JEP 451 — Prepare to Disallow Dynamic Loading of Agents**. Mục tiêu là cải thiện “integrity by default” và phát cảnh báo khi nạp agent động vào JVM đang chạy. Khả năng cho phép dynamic loading chịu ảnh hưởng JVM release và flags/policy; không suy luận phiên bản tương lai sẽ tự cho phép mã attach.

**Cách bài này dùng:** `-javaagent:agent-demo.jar` tại startup, tức agent được phê duyệt **trước khi JVM chạy ứng dụng chính**, tránh tự attach vào tiến trình ngoài.

| Cách triển khai | Đặc điểm |
| --- | --- |
| `java -javaagent:agent.jar ...` | Startup agent, dễ kiểm soát quyền/deployment và các class loads sau premain |
| Dynamic attach + `agentmain` | Đòi quyền attach/process policy; Java21+ có cảnh báo/integrity constraints; JDK tương lai có thể thay default |
| Agent code chạy như app class bình thường | Không tự có `Instrumentation` chỉ vì class nằm trong classpath |
| `-Djdk.instrument.traceUsage` | Hỗ trợ trace Instrumentation API usage khi chẩn đoán, tùy JVM |

Không hướng dẫn dùng `-XX:+EnableDynamicAgentLoading` để âm thầm vượt một cơ chế bảo vệ của ứng dụng khác. Khi thật sự cần dynamic attach, phải là JVM do bạn **được phép vận hành**, với chính sách bảo mật/observability được phê duyệt.

### 14.1. Agent là privileged code

Một Java agent có thể xem/chỉnh class definitions của ứng dụng, đọc metadata, can thiệp framework internals. Không cài agent JAR từ nguồn không đáng tin. Bảo vệ artifacts/signatures/checksums, startup args và quyền ghi vào JAR. Đừng cho user input chọn arbitrary transformer class hay regex instrument toàn bộ classes.

## 15. JPMS module boundaries và class loader identity

Trong Java 9+, một class được xác định không chỉ bởi **tên**, mà còn bởi **defining loader** (và context module). Vì vậy hai classes có cùng internalName nhưng được load bởi hai classloaders khác nhau vẫn là **hai runtime classes** riêng.

Trong `transform`:

~~~java
if (!"com/example/Service".equals(className)) {
    return null;
}
~~~

là filter cơ bản. Production tooling còn nên kiểm:

- `loader` là classloader mục tiêu hay classloader được phép.
- `module` có tên/đọc modules mong đợi.
- `ProtectionDomain` phù hợp deployment boundary.
- Class đã được define/redefine hay chưa (đọc `classBeingRedefined`).
- Tên package có khả năng trùng ở plugin class loaders hay không.

### 15.1. Module readability khi bytecode gọi helper của agent

Một method được instrument có thể phát sinh `invokestatic AgentHelper.record()`. Nhưng target class loader/module có thể **không nhìn thấy** `AgentHelper` hoặc package không được exported/readable. Khi đó code transformed có thể ném `NoClassDefFoundError`/`IllegalAccessError` dù classfile hợp lệ.

Các hệ thống instrumentation chuyên nghiệp thường:

- Bố trí helpers ở bootstrap/system loader hoặc target loader khi thích hợp.
- Tương thích JPMS exports/reads/opens theo nhu cầu.
- Dùng `Instrumentation.redefineModule(...)` khi thực sự cần và được phê duyệt.
- Tránh thay module descriptors ngoài yêu cầu.
- Test mỗi class loader layout (application server, plugin sandbox, container, modular app).

Ví dụ trong bài chỉ thay **string literal**, không gọi helper mới, nên không phát sinh dependency classloader ngoài.

### 15.2. Đừng nhầm module-aware callback với quyền bypass modules

Transformer nhận `Module` để biết ngữ cảnh; điều đó **không tự cấp quyền reflection/invoke qua module boundaries**. Quy tắc JVM access vẫn áp dụng cho bytecode đầu ra, và agent cần quản lý dependencies/permissions đúng.

## 16. Hiệu năng, memory và quan sát trong production

Biến đổi bytecode có chi phí ở **thời điểm class load/retransform**, nhưng code mới có thể tạo overhead ở mỗi method call.

Những vấn đề cần đo:

- Thời gian parse/build classfile mỗi class.
- Số classes transform thực sự thay vì số callback tổng.
- Tổng bytes allocated; GC pressure trong startup.
- Khả năng cache transform results theo class version/loader (đừng cache sai global).
- Số method hooks thêm vào và CPU cost của mỗi hook.
- Effects lên JIT optimizations/inlining/deoptimization khi retransform.
- Startup latency, p95/p99 request latency khi có agent.
- Memory lifecycle của transformer/counters/strong references to classloaders.
- Thread safety/concurrent class loading.
- Compatibility qua nhiều JDK releases.

### 16.1. Hạn chế overhead bằng early return

~~~java
if (!TARGET_INTERNAL_NAME.equals(className)) {
    return null;
}
~~~

Tránh gọi `ClassFile.of().parse(...)` cho **mọi** class trong JVM nếu chỉ cần instrument một vài packages. Regex/object allocations trong callback cũng có giá; prefer allowlists/cheap string checks.

### 16.2. Agent không được giữ mọi ClassLoader bằng strong references mãi

Trong app có hot deployment, plugin isolation hoặc application-server classloaders, cache keyed bởi loader trong static map có thể gây **classloader leak**, ngăn GC và tăng metaspace. Dùng weak-keyed structures hoặc cleanup explicit phù hợp; kiểm monitoring khi unload/reload modules.

### 16.3. Tránh log class bytes hoặc sensitive constants

Bytecode có thể chứa string literals, endpoint URLs, internal names, tokens bị hardcode sai cách hoặc business details. Không in toàn bộ `classfileBuffer` vào logs hoặc upload tới server ngoài. Chỉ ghi metrics/IDs cần thiết và redact theo privacy/security policy.

## 17. Kiểm thử agent đúng cách

### 17.1. Unit-test Class-File API transformation logic

Một hàm pure transform `byte[] -> byte[]` có thể được test độc lập với JVM agent:

- Build classfile fixture với Java compiler.
- Parse/transform bằng Class-File API.
- Parse output và kiểm các elements cần thay.
- Chạy verifier/class-loading trong classloader tách biệt nếu cần.
- Kiểm method signature/fields không đổi.
- Kiểm không biến đổi class không match filter.

Tuy nhiên, unit test pure transform **không thay** integration test `-javaagent` thực tế vì còn lifecycle/callback/JVM constraints.

### 17.2. Integration-test trong JVM con

Agent ảnh hưởng process-wide class loading, nên test trong **JVM riêng**. Nếu chạy trong cùng JVM với test runner, có thể tác động framework, logging, threads, JIT hoặc mocks ngoài ý muốn.

Test đủ:

1. Startup với `-javaagent`.
2. Target load **sau premain**.
3. Return `null` với class ngoài scope.
4. Return new bytes với target.
5. Gọi method và kiểm behavior.
6. Kiểm capability before retransformation.
7. Retransform class already loaded.
8. Remove transformer và xác nhận không có automatic rollback.
9. Nếu có kế hoạch restore, kiểm nó trong setup cô lập và không hứa nó đúng với multiple agents.
10. Thử `-javaagent` invalid/missing manifest, expected startup failure.
11. Thử classfile versions khác nhau nếu agent multi-JDK.
12. Test cùng APM/coverage/mocking agents khác.
13. Test dưới concurrent class loading.
14. Kiểm cleanup và tài nguyên, không tạo process/thread leak.

### 17.3. Vì sao không dùng synthetic “transformer called” là test chính?

Nhiều agents có thể được gọi nhưng trả `null`. Vì vậy:

~~~text
Agent registered        ≠ bytecode transformed
transform callback hit  ≠ JVM installed transformed bytes
class verification pass ≠ business behavior correct
removeTransformer done  ≠ existing class automatically restored
~~~

Ba lớp kiểm thử: **callback**, **classfile validity/installation**, **observable behavior**.

## 18. Bảng đối chiếu các API quan trọng

| API | Mục đích | Điểm cần nhớ |
| --- | --- | --- |
| `Instrumentation.addTransformer(t)` | Đăng ký callback | Mặc định `canRetransform=false` |
| `Instrumentation.addTransformer(t,true)` | Callback capable với retransformation | Chỉ nếu JVM capability hỗ trợ |
| `Instrumentation.removeTransformer(t)` | Gỡ callback | Không tự revert bytes; callbacks in-flight có thể tiếp tục |
| `Instrumentation.isRetransformClassesSupported()` | Kiểm capability | Manifest + JVM hỗ trợ |
| `Instrumentation.isModifiableClass(type)` | Kiểm class sửa được | Không phải class nào cũng modifiable |
| `Instrumentation.retransformClasses(type...)` | Trigger bytes mới cho loaded classes | Baseline semantics, schema limits |
| `Instrumentation.redefineClasses(...)` | Redefine bằng ClassDefinition bytes | Capability riêng |
| `ClassFileTransformer.transform(...)` | Chọn/biến đổi bytes | Không sửa input buffer; null = no change |
| `ClassFile.of()` | Tạo ClassFile helper | Chuẩn từ Java 24 |
| `ClassFile.parse(byte[])` | Parse model của classfile | Có thể phát hiện malformed bytes |
| `ClassFile.transformClass(model, xform)` | Build bytes đã biến đổi | Dùng ClassTransform |
| `ClassTransform.transformingMethodBodies(...)` | Áp CodeTransform cho methods được chọn | Giữ các elements khác |
| `ConstantInstruction.LoadConstantInstruction` | Mô hình `ldc`/constant-load instruction | Không đoán offsets |
| `CodeBuilder.ldc(...)` | Sinh instruction load constant mới | Tạo constant pool entry hợp lệ |
| `ClassFileVerifier` / JVM verification | Kiểm tính hợp lệ của bytecode | Kiểm runtime và test class loading |
| `Module`, `ClassLoader`, `ProtectionDomain` | Context của class | Filter theo security/deployment scope |

Không coi `ClassFile` API là có mặt trên **Java 17**; ví dụ `ObserveAgent` chứng minh Java17 có Instrumentation mà không cần API ClassFile mới.

## 19. Checklist chống lỗi trước khi dùng production agent

- [ ] Agent JAR được xây từ source/đối tác đáng tin, có provenance/kiểm chữ ký phù hợp.
- [ ] Startup `-javaagent` khai báo `Premain-Class` đúng.
- [ ] Chỉ yêu cầu `Can-Retransform-Classes` nếu cần.
- [ ] Kiểm `isRetransformClassesSupported()` và `isModifiableClass()` trước khi gọi.
- [ ] Transformer filter exact internal names; xét module/loader khi app modular.
- [ ] Không mutate `classfileBuffer`; luôn trả bytes mới hoặc null.
- [ ] Dùng Java24+ Class-File API hoặc thư viện bytecode tương thích version.
- [ ] Không dùng `jdk.internal.*` internal APIs trong solution chính.
- [ ] Method signatures, fields, inheritance không đổi khi retransformation.
- [ ] Classfile được verifier chấp nhận; test behavior sau load/retransform.
- [ ] Không gọi network/DB/reflection vào target class từ transformer.
- [ ] Transformer thread-safe, tránh global lock contention và recursive class loading.
- [ ] Không dùng exception từ transformer làm cách chặn class execution.
- [ ] Gỡ transformer không bị hiểu thành rollback ngay.
- [ ] Có strategy rollback/restart rõ ràng.
- [ ] Test với APM/coverage/mocking frameworks khác.
- [ ] Không leak ClassLoader references; memory/performance được đo.
- [ ] Không log secrets/bytecode nội bộ.
- [ ] Không tự attach vào JVM khác mà không có quyền.
- [ ] Rollout theo canary/metrics, không instrument mọi class ngay.
- [ ] Có tài liệu JDK versions đã verify, không dựa vào hành vi ngẫu nhiên của môi trường test.

## 20. Câu hỏi tự kiểm tra và đáp án

**Câu 1.** `ClassFileTransformer` có vai trò gì?

**Trả lời:** Cung cấp callback để Java agent nhận classfile bytes trước JVM define/redefine/retransform và tùy chọn trả bytes thay thế.

**Câu 2.** `transform(...)` trả `null` có làm JVM bỏ class không?

**Trả lời:** Không. Nó biểu thị **không có transformation** tại bước này.

**Câu 3.** Có được sửa trực tiếp `classfileBuffer` không?

**Trả lời:** Không. JavaDoc yêu cầu không thay input; nếu biến đổi, tạo một mảng bytes mới và trả về.

**Câu 4.** Khi nào agent `premain` chạy?

**Trả lời:** Trước application main khi khởi động JVM với `-javaagent` và manifest đúng.

**Câu 5.** `className` có dạng `com.example.Service` không?

**Trả lời:** Không theo internal class name convention; thường là `com/example/Service`.

**Câu 6.** Vì sao nên override overload sáu tham số?

**Trả lời:** Để nhận thêm `Module` context, phù hợp code Java module system hiện hành.

**Câu 7.** Overload năm tham số còn được hỗ trợ không?

**Trả lời:** Có. JavaDoc SE26 vẫn có default method năm tham số; overload sáu tham số mặc định chuyển tới nó nếu không override sáu tham số.

**Câu 8.** `ClassFileTransformer` có phải functional interface cho lambda không?

**Trả lời:** Không nên giả định; overloads là default methods, bài dùng anonymous implementation rõ ràng.

**Câu 9.** `addTransformer(t)` mặc định có retransform-capable không?

**Trả lời:** Không. Tương đương `addTransformer(t,false)`.

**Câu 10.** Muốn gọi `retransformClasses` cần gì?

**Trả lời:** Manifest capability/JVM support, transformer đăng ký capable nếu muốn callback được gọi lại, class có thể sửa, và quyền vận hành phù hợp.

**Câu 11.** Transformer không capable có chạy lại trong retransformation không?

**Trả lời:** Callback không được gọi lại; JVM tự áp lại kết quả đã lưu từ lần load/redefine trước theo documented steps.

**Câu 12.** Sau retransform, method đang chạy có chuyển tức thời sang code mới không?

**Trả lời:** Không nhất thiết. Active frames có thể dùng bytecode cũ, invocations mới dùng định nghĩa mới.

**Câu 13.** `removeTransformer` có revert active class không?

**Trả lời:** Không tự động. Nó gỡ callback; class đã thay tiếp tục theo definition hiện hành.

**Câu 14.** Trong demo, vì sao sau remove + explicit retransform lại được ORIGINAL?

**Trả lời:** Vì đó là JVM test cô lập với một capable transformer duy nhất, không còn transforms khác; retransform bắt đầu từ baseline classfile. Không phải guarantee chung nếu nhiều agents.

**Câu 15.** Có thể thêm method mới bằng `retransformClasses` không?

**Trả lời:** Thông thường bị giới hạn bởi JVMTI redefinition constraints; ví dụ an toàn chỉ sửa method body, giữ cấu trúc class.

**Câu 16.** Có cần `--enable-preview` cho Class-File API trong Java 24 không?

**Trả lời:** Không. Java 24 hoàn thiện standard Class-File API.

**Câu 17.** Có thể compile source Class-File API bằng `javac --release 17` không?

**Trả lời:** Không. `java.lang.classfile` chuẩn có từ Java 24; Java17 dùng thư viện bytecode được hỗ trợ nếu cần patch.

**Câu 18.** Tại sao không tìm chuỗi trong raw `.class` rồi replace mảng bytes?

**Trả lời:** Dễ hỏng constant pool, encoding/length, offsets, instruction sharing và class verification. Dùng Class-File API hoặc thư viện bytecode chuyên dụng.

**Câu 19.** Vì sao transformer phải filter early?

**Trả lời:** Callback có thể nhận rất nhiều class definitions; filter giảm overhead và tránh chạm core JDK/agent classes không mong muốn.

**Câu 20.** Vì sao không chạy `Class.forName(target)` bên trong transform target?

**Trả lời:** Có thể gây circular class resolution và `LinkageError` ngay trong lúc JVM đang định nghĩa target.

**Câu 21.** Nếu transformer throw exception, JVM chắc chắn không load class không?

**Trả lời:** Không. JavaDoc quy định exception tương tự null ở bước đó và transformers khác vẫn được thử.

**Câu 22.** Java agent có tự có quyền remote attach JVM bất kỳ không?

**Trả lời:** Không. Dynamic attach chịu security/OS/JVM policy và JEP451 warnings/restrictions. Ví dụ dùng startup agent trong JVM thử nghiệm.

**Câu 23.** `ClassFile.of().transformClass(...)` thay source file `.java` có sẵn không?

**Trả lời:** Không. Nó tạo classfile bytes để JVM dùng tại một definition/retransform, không ghi source file trên disk.

**Câu 24.** Vì sao source demo dùng `AtomicInteger`?

**Trả lời:** Đếm callback một cách thread-safe để chứng minh load và retransform đều xảy ra; không dùng counter đó làm production transformation policy.

**Câu 25.** Vì sao client app không tự nhìn thấy Instrumentation object nếu không chạy agent?

**Trả lời:** `Instrumentation` được JVM đưa cho entry point `premain`/`agentmain`; có class trong classpath không tự cấp object này.

**Câu 26.** Nếu hai agents cùng biến đổi một class, ai chạy trước?

**Trả lời:** Có thứ tự theo nhóm retransform capability/native vs Java, rồi registration order trong nhóm; transformations tạo thành chuỗi.

**Câu 27.** Vì sao một agent mới có thể không thấy target đang chạy?

**Trả lời:** Target có thể đã load trước khi addTransformer; cần retransformation capability/explicit request hoặc khởi động lại với startup agent.

**Câu 28.** `loader==null` có nghĩa gì?

**Trả lời:** Có thể là bootstrap class loader, không tự coi là lỗi; tránh instrument JDK core classes khi không có thiết kế tương ứng.

**Câu 29.** Vì sao phải quản lý dependencies/module access của helper code được chèn?

**Trả lời:** Transformed bytecode chạy trong visibility/access của target class; helper không visible có thể gây class loading/access errors.

**Câu 30.** Một lớp đã biến đổi có trở thành class khác không?

**Trả lời:** Không. Đây vẫn là class runtime cùng identity, theo giới hạn redefine/retransform; current definitions và future invocations có thể thay đổi method code.

**Câu 31.** Bytecode patch có tự cải thiện hiệu năng không?

**Trả lời:** Không. Instrumentation tăng overhead và có thể ảnh hưởng JIT; cần benchmark thực tế.

**Câu 32.** Test agent tốt nhất là gì?

**Trả lời:** Chạy JVM con với `-javaagent` thật, kiểm method behavior và retransform, không chỉ dựa vào log “callback called”.

**Câu 33.** Trong ví dụ Java17, transformer có sửa class không?

**Trả lời:** Không; nó ghi nhận callback và trả null, bảo toàn kết quả HELLO. Đây là smoke test lifecycle, không phải biến đổi bytecode.

**Câu 34.** Trong ví dụ Java24, transformer có sửa class thật không?

**Trả lời:** Có. Output cho thấy literal đổi `ORIGINAL → PATCHED-1 → PATCHED-2` khi JVM gọi class đã transform.

**Câu 35.** Nguyên tắc quan trọng nhất khi viết ClassFileTransformer production?

**Trả lời:** **Filter hẹp; không sửa input; sinh bytes hợp lệ; tôn trọng retransform schema; không phụ thuộc class loading recursion; kiểm tra bằng JVM thực và bảo vệ quyền agent.**

## 21. Kết luận

`ClassFileTransformer` là thành phần cốt lõi của **Java Instrumentation**: nhận classfile bytes trong JVM load/redefine/retransform và tùy chọn tạo bytes thay thế. `null` nghĩa là không thay đổi; **không sửa input byte array tại chỗ**. Khác nhau giữa **class load**, **redefinition** và **retransformation** quyết định lúc callback chạy, thứ tự transforms, baseline bytes và tính hợp lệ của method modifications.

Để triển khai mới trên **Java 24+**, Class-File API `java.lang.classfile` là lựa chọn chuẩn, không phải internal API. Ví dụ trong bài tạo Java agent thật, thay một string literal ở bytecode khi load, làm retransform rồi khôi phục trong JVM cô lập và kiểm stdout. Với **Java 17–23**, Instrumentation vẫn hợp lệ, nhưng cần ASM/Byte Buddy hiện hành nếu muốn patch bytes thực sự. Đối với mọi JDK: tránh dynamic attach không được phép, class loading recursion, classfile verification errors, indiscriminate transformations và global agent state không kiểm soát.

### Tài liệu chính thức còn áp dụng

- [Oracle Java SE 26 — ClassFileTransformer](https://docs.oracle.com/en/java/javase/26/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): callback, hai overloads, return null/new bytes, thứ tự và exception handling.
- [Oracle Java SE 26 — Instrumentation](https://docs.oracle.com/en/java/javase/26/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): add/remove transformers, capability flags, redefine/retransform semantics và schema constraints.
- [Oracle Java SE 26 — java.lang.instrument package](https://docs.oracle.com/en/java/javase/26/docs/api/java.instrument/java/lang/instrument/package-summary.html): Java agent entry points và manifest.
- [Oracle Java SE 24 — ClassFile](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/ClassFile.html): parse/build/transformClass.
- [Oracle Java SE 24 — ClassTransform](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/ClassTransform.html): transformingMethodBodies và reusable transforms.
- [Oracle Java SE 24 — CodeBuilder](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/CodeBuilder.html): `ldc` và các instruction factories.
- [Oracle Java SE 24 — ConstantInstruction](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/instruction/ConstantInstruction.html): constantValue và load instructions.
- [Oracle Java SE 24 — Class-File API package guide](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/package-summary.html): API architecture, examples và transform composition.
- [OpenJDK JEP 484 — Class-File API](https://openjdk.org/jeps/484): API chuẩn được final ở JDK 24.
- [OpenJDK JEP 451 — Prepare to Disallow Dynamic Loading of Agents](https://openjdk.org/jeps/451): integrity/default dynamic attach warnings.
- [Oracle Java SE 17 — ClassFileTransformer](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): xác nhận API vẫn tồn tại trên Java17.
- [Oracle Java SE 26 — JVM Class File Format](https://docs.oracle.com/javase/specs/jvms/se26/html/jvms-4.html): JVMS chapter 4, well-formed classfile structure.

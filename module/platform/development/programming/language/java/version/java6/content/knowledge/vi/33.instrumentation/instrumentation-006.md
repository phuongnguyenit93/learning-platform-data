# Transformer hỗ trợ retransformation và quy tắc gọi lại trong Java Instrumentation

## 1. Bài toán và kết quả cần nắm

Một Java agent có thể can thiệp vào **bytes của class file trước khi JVM áp dụng định nghĩa lớp**. Đây là nền tảng của instrumentation: tracing, code coverage, performance profiling, observability và các công cụ can thiệp bytecode được phê duyệt.

Nhưng khi lớp **đã được nạp**, việc gọi `Instrumentation.retransformClasses(...)` không đồng nghĩa với “JVM chạy lại mọi transformer y hệt lúc load” hoặc “lấy bytecode vừa biến đổi xong rồi áp tiếp phép biến đổi”.

**Quy tắc hiện hành của Java SE 26:**
- Transformer được đăng ký với `canRetransform=false` chạy khi class **load/redefine**, **không được gọi lại** lúc retransform. Đầu ra biến đổi trước đó của nó được JVM **tái sử dụng tự động**.
- Transformer được đăng ký với `canRetransform=true` chạy lúc class **load/redefine** và được **gọi lại** khi retransform.
- JVM xếp transformer theo **nhóm capability** trước, rồi mới theo thứ tự đăng ký trong từng nhóm.
- Khi retransform, JVM bắt đầu từ dữ liệu class definition ban đầu hoặc bản redefine gần nhất (có thể khác byte-for-byte do JVM chuẩn hóa constant pool), **không cộng dồn đầu ra lần retransform-capable trước**.
- Khả năng retransform là **optional JVM capability**, chỉ dùng được khi agent manifest khai báo `Can-Retransform-Classes: true` và JVM cho phép.

Bài **“Transformer hỗ trợ retransformation và quy tắc gọi lại”**, thuộc chủ đề **Instrumentation**, hướng dẫn từ contract, callback parameters đến Java agent chạy thật.

Sau khi học, bạn có thể:
1. Phân biệt `premain`/`agentmain` và lớp nhận `Instrumentation`.
2. Hiểu `addTransformer(transformer)`, `addTransformer(transformer,false/true)`, `isRetransformClassesSupported()` và `isModifiableClass()`.
3. Phân biệt **load**, **redefinition**, **retransformation**.
4. Dự đoán callback nào được gọi và thứ tự thực tế, kể cả khi thứ tự đăng ký bị đảo.
5. Biết rằng transformer không hỗ trợ retransform **không chạy lần nữa**, nhưng ảnh hưởng trước đó của nó có thể tiếp tục.
6. Không nhầm input của transformer retransform-capable với bytecode **đã qua capable pass trước đó**.
7. Hiểu contract của cả `transform(Module,...)` sáu đối số và `transform(...)` năm đối số.
8. Xử lý `null`, `IllegalClassFormatException`, transformer exceptions, class schema restrictions và concurrent class loading.
9. Biên dịch một **Java 17+ agent JAR** thật, chứng minh chain transformations bằng các string constants có cùng độ dài.
10. Chạy thử **hai manifest khác nhau**: có capability (31 assertions) và không có capability (9 assertions), đã xác minh tổng cộng **40/40 PASS trên OpenJDK 24**.
11. Thiết kế instrumentation an toàn, ít overhead, không tự gây class loading cycle hoặc làm hỏng JVM production.

**Special Note về tính hiện hành:** Bài dựa trên Java SE 26/JDK26 và JVM TI 26.0.0; code dùng `javac --release 17`, chạy trên OpenJDK24. Không sao chép tài liệu Java 6 cũ như thể đó là runtime hiện tại. Những API lâu đời nhưng **vẫn được hỗ trợ** như Java instrumentation `premain` và overload `transform` năm tham số được đề cập đúng phạm vi compatibility hiện hành; ví dụ chính chủ động sử dụng overload sáu tham số có `Module`.

## 2. Instrumentation agent là gì?

`java.lang.instrument` thuộc module **`java.instrument`**. Một agent là code có quyền intercept class file bytes và tùy trường hợp áp dụng thay đổi bytecode khi lớp được định nghĩa hoặc nạp lại. Agent thường được đóng gói trong một JAR và có một entrypoint được JVM gọi với một instance `Instrumentation`.

Cách chạy lúc startup:

```text
java -javaagent:agent.jar -cp application-classes MainClass
                   |
                   v
    manifest Premain-Class -> Agent.premain(args, instrumentation)
                   |
                   v
    register ClassFileTransformer(s)
                   |
                   v
    JVM loads classes / redefines / retransforms
                   |
                   v
    transform(...) callbacks
```

**Agent JAR không phải một classpath library thông thường.** Chỉ có JAR chứa Agent class nhưng không dùng cơ chế kích hoạt phù hợp thì `premain` không tự chạy. `-javaagent` chạy agent **trước** ứng dụng `main`, giúp agent có thể đăng ký transformers trước khi target classes được load.

### 2.1. Hai entrypoints chính

| Cách khởi chạy | Manifest attribute | Entry method | Mốc thời gian |
| --- | --- | --- | --- |
| `-javaagent:agent.jar` khi JVM start | `Premain-Class` | `public static void premain(String, Instrumentation)` | Trước application main |
| Attach vào JVM đang chạy nếu JVM/triển khai cho phép | `Agent-Class` | `public static void agentmain(String, Instrumentation)` | Sau JVM startup |
| Agent đóng trong executable JAR hỗ trợ launcher-agent | `Launcher-Agent-Class` | `agentmain` | Trước application main |

Oracle Java SE26 `java.lang.instrument` package spec vẫn hỗ trợ các cơ chế này. Nhưng **dynamic agent loading** còn bị ràng buộc bởi chính sách runtime; ở HotSpot hiện hành việc opt-in liên quan `-XX:+EnableDynamicAgentLoading`. Bài không dùng dynamic attach để tránh đòi hỏi quyền hoặc thao tác lên JVM khác, mà chọn `-javaagent` trong **JVM test riêng**.

### 2.2. Minimal agent interface

```java
public final class ExampleAgent {
    public static void premain(
            String args, Instrumentation instrumentation) {
        // Validate capability, register transformers.
    }
}
```

Đây là snippet: cần import `java.lang.instrument.Instrumentation`, manifest `Premain-Class: ExampleAgent` và build JAR. Không có một lệnh `new Instrumentation()` bình thường để tự tạo implementation; JVM cung cấp đối tượng này khi khởi động agent.

## 3. Hai nhóm transformer xác định bằng thời điểm đăng ký

Interface `java.lang.instrument.ClassFileTransformer` định nghĩa callback `transform(...)`. Transformer phải được **đăng ký** qua `Instrumentation.addTransformer` trước khi được JVM sử dụng.

### 3.1. Đăng ký không hỗ trợ retransformation

```java
inst.addTransformer(transformer);
inst.addTransformer(transformer, false);
```

Về capability, hai lệnh trên tương đương: transformer là **retransformation-incapable**. Nó có thể được gọi khi class mới load và khi class **redefine**, nhưng **không** được gọi trong một `retransformClasses`. Không nói nó “chỉ chạy một lần toàn JVM”: nó vẫn nhận callbacks của nhiều classes load/redefine theo filter, và một class có thể bị redefine nhiều lần.

### 3.2. Đăng ký có hỗ trợ retransformation

```java
if (inst.isRetransformClassesSupported()) {
    inst.addTransformer(transformer, true);
}
```

Đây là snippet, `inst` do `premain`/`agentmain` nhận. `canRetransform=true` làm transformer thuộc nhóm có thể gọi lại khi retransform. Nhưng nếu JVM configuration **không có** capability, lời gọi `addTransformer(...,true)` ném `UnsupportedOperationException`.

**Không nhầm hai ý:**
- `canRetransform=true` **không tự kích hoạt** một lần retransform.
- `retransformClasses(SomeClass.class)` mới là yêu cầu retransform class đã load.

### 3.3. Capability cần cả manifest và VM

Agent manifest cho ví dụ có hỗ trợ:

```text
Manifest-Version: 1.0
Premain-Class: RtAgent
Can-Retransform-Classes: true
```

Agent manifest cho ví dụ **không** hỗ trợ:

```text
Manifest-Version: 1.0
Premain-Class: RtNoCapAgent
Can-Retransform-Classes: false
```

Theo `java.lang.instrument` package spec, giá trị mặc định khi không có attribute là **false**. Không được suy từ JVM “có thể hỗ trợ hotswap” rằng agent đang được cấp quyền `retransformClasses`: **manifest** và **VM support** đều cần thỏa.

`isRetransformClassesSupported()` trả kết quả ổn định trong cùng một JVM instance, nhưng nó không có nghĩa mọi class trong JVM đều có thể retransform.

### 3.4. Phân biệt capability retransform và redefine

| Capability | Check | Manifest |
| --- | --- | --- |
| Retransformation | `isRetransformClassesSupported()` | `Can-Retransform-Classes: true` |
| Redefinition | `isRedefineClassesSupported()` | `Can-Redefine-Classes: true` |
| Native method prefix | `isNativeMethodPrefixSupported()` | `Can-Set-Native-Method-Prefix: true` |

Đây là **các capabilities độc lập**, không bật chung qua một attribute. Agent có khả năng retransform không tự suy ra có khả năng redefine. Trong hai manifest của fixture, chúng ta chỉ điều khiển `Can-Retransform-Classes`.

## 4. Load, redefine, retransform: ba tình huống khác nhau

| Sự kiện | Kích hoạt | Callback retransformation-incapable | Callback retransformation-capable |
| --- | --- | --- | --- |
| **Initial load/define** | `ClassLoader.defineClass` hoặc cơ chế JVM tương đương | **Có** | **Có** |
| **Redefinition** | `Instrumentation.redefineClasses` / JVM TI | **Có** | **Có** |
| **Retransformation** | `Instrumentation.retransformClasses` / JVM TI | **Không gọi lại**; output cũ được tái dùng | **Có** |

Thứ tự trên không thay đổi nếu một transformer được đăng ký trước hay sau một transformer ở **nhóm khác**. Trong từng nhóm cùng capability, thứ tự đăng ký mới được áp dụng.

### 4.1. Redefinition chủ động cung cấp class bytes mới

`redefineClasses(new ClassDefinition(...))` nhận toàn bộ classfile bytes do caller cung cấp. Nó thích hợp khi cần thay bản định nghĩa bằng file đã biên dịch khác, ví dụ công cụ debugger hỗ trợ fix-and-continue. Nó phụ thuộc capability `Can-Redefine-Classes` riêng. Transformer cả hai nhóm được gọi trong quá trình redefinition.

**Retransformation** khác: application chỉ đưa `Class<?>...`, JVM lấy bytes gốc/lần redefine gần nhất và chạy lại pipeline theo quy tắc. Nó không yêu cầu caller đưa một `ClassDefinition`.

### 4.2. Đừng dùng retransform để “reload source Java”

`retransformClasses` không recompile file `.java`, không tự đọc JAR mới từ ổ đĩa và không thay đổi mã nguồn. JVM chạy lại pipeline **classfile bytes** đang có trong hệ thống quản lý lớp, theo các quy tắc của `Instrumentation`/JVMTI. Nếu muốn apply code mới, transformer phải chủ động tạo valid bytes theo contract.

## 5. Thứ tự callback theo nhóm — không chỉ theo thời điểm đăng ký

`ClassFileTransformer` Javadoc Java SE 26 đặc tả **bốn nhóm** (nếu có cả Java và native JVMTI transformers):

1. Retransformation-**incapable Java** transformers.
2. Retransformation-**incapable native** transformers.
3. Retransformation-**capable Java** transformers.
4. Retransformation-**capable native** transformers.

Trong **mỗi nhóm**, transformers được gọi theo thứ tự add. Với nhiều transformers, output `byte[]` của callback trước trở thành input `classfileBuffer` của callback sau (nếu callback trước trả non-null). Nếu callback trả null, bytes giữ nguyên để tiếp tục.

Một ví dụ cố ý đảo thời điểm đăng ký:

```java
instrumentation.addTransformer(capable, true);   // Đăng ký đầu tiên.
instrumentation.addTransformer(incapable, false); // Đăng ký thứ hai.
```

**Khi target load**, callback vẫn chạy **incapable trước capable** vì grouping rules, không chạy capable trước. Fixture kiểm tra chính xác điều này bằng event list.

### 5.1. Minh họa chuỗi biến đổi

Giả sử class file ban đầu chứa một `CONSTANT_Utf8`:

```text
ORIGIN01
```

Transformer incapable sửa `ORIGIN01` → `STAGE101`. Transformer capable sửa `STAGE101` → `RESULT01`.

```text
Initial load
  RtTarget.class raw constant: ORIGIN01
             |
             v
  incapable (canRetransform=false)
  ORIGIN01 -> STAGE101                 [called once]
             |
             v
  capable (canRetransform=true)
  STAGE101 -> RESULT01                 [called once]
             |
             v
  RtTarget.result() returns RESULT01
```

Khi gọi `retransformClasses(RtTarget.class)`:

```text
First retransformation
  JVM starts from initial class definition
             |
             v
  incap output STAGE101 is REUSED      [callback NOT invoked]
             |
             v
  capable sees STAGE101 again           [callback invoked]
  STAGE101 -> RESULT02
             |
             v
  RtTarget.result() returns RESULT02
```

Gọi tiếp:

```text
Second retransformation
  JVM again supplies STAGE101 from reused incapable output
             |
             v
  capable sees STAGE101 (NOT RESULT02)
  STAGE101 -> RESULT03
             |
             v
  RtTarget.result() returns RESULT03
```

Đây chính là điểm quan trọng nhất: **capable transformer không tự nhận RESULT01/RESULT02 từ lần capable pass trước**, và incapable transformer không tự chạy lại. Việc dùng cùng input STAGE101 ở mỗi lần retransform trong fixture xác nhận spec bằng một chương trình chạy thật.

## 6. Quy tắc dùng bytes: đừng sửa mảng đầu vào

Callback nhận `classfileBuffer` ở dạng `byte[]`.

Theo `ClassFileTransformer` Javadoc:
- Nếu không thay đổi, **return `null`**.
- Nếu thay đổi, tạo **một mảng `byte[]` mới**, copy dữ liệu đầu vào, sửa trên copy rồi return copy.
- **Không được mutate `classfileBuffer` input** do JVM cung cấp.
- Output phải là classfile hợp lệ (format, constant pool, references và restrictions của reload).
- Không được thay class name thành một class khác trong payload.
- Không dùng code transformer gây recursive loading của class đang transform, nhất là core JDK classes.

Ví dụ chuẩn mực:

```java
@Override
public byte[] transform(Module module, ClassLoader loader,
        String className, Class<?> beingRedefined,
        ProtectionDomain domain, byte[] classfileBuffer)
        throws IllegalClassFormatException {
    if (!"demo/Target".equals(className)) {
        return null;                  // Bỏ qua mọi class khác.
    }
    byte[] copy = classfileBuffer.clone();
    // Chỉ sửa copy theo class-file parser đã kiểm chứng.
    return copy;
}
```

Đây là **snippet**, cần imports cho `Module`? `Module` thuộc java.lang, cần `ClassLoader`, `ProtectionDomain` và `IllegalClassFormatException`, cùng method trong implementation `ClassFileTransformer`. Trong project production, dùng bytecode transformation library có khả năng tạo classfile hợp lệ và verify được; **đừng coi việc thay một chuỗi bytes ngẫu nhiên trong file là phương pháp instrument tổng quát**.

### 6.1. Vì sao fixture chỉ sửa một UTF8 constant cùng độ dài?

Để bài có ví dụ thuần JDK, không kéo dependency ASM/Byte Buddy, fixture dùng một **constant-pool parser nhỏ** chỉ tìm entry `CONSTANT_Utf8` đúng tên và thay **8 byte ASCII bằng 8 byte ASCII**. Nó:
- Không sửa magic/header/class name.
- Không đổi constant-pool sizes hoặc indices.
- Không đổi methods, fields hay method signatures.
- Clone input trước khi thay.
- Chỉ xử lý một target class `RtTarget` do bài kiểm soát.
- Reject nếu marker không tồn tại/không duy nhất.
- Không là thư viện parser/rewriter classfile production đầy đủ.

Đây là **thiết kế bài test**, không phải lời khuyên copy parser tự chế sang production agents. Với production, kiểm chứng bytecode bằng JDK/ASM/Byte Buddy tương thích JDK mục tiêu và có test cho class file version, StackMapTable, modules, class loaders.

## 7. Hai overload `transform` còn áp dụng trên Java SE26

`ClassFileTransformer` có:

**Overload có `Module` (Java 9+, khuyến nghị khi cần module awareness):**

```java
byte[] transform(Module module, ClassLoader loader, String className,
        Class<?> classBeingRedefined, ProtectionDomain protectionDomain,
        byte[] classfileBuffer);
```

**Overload không có `Module` (năm tham số, vẫn được hỗ trợ):**

```java
byte[] transform(ClassLoader loader, String className,
        Class<?> classBeingRedefined, ProtectionDomain protectionDomain,
        byte[] classfileBuffer);
```

Hai snippets là signatures rút gọn, không phải một Java interface bạn có thể compile riêng. Quan trọng về Java SE26:
- Method sáu tham số là `default`; nếu implementation không override, nó **gọi tới overload năm tham số**.
- Method năm tham số cũng là `default`; nếu không override, mặc định trả `null`.
- Một transformer nên override **ít nhất một** overload.
- Fixture cố ý dùng overload **năm tham số** cho incapable để kiểm thử compatibility forwarding, và overload **sáu tham số** cho capable để xác minh `Module` có mặt.

### 7.1. Callback parameters

| Parameter | Lúc initial load | Lúc redefine/retransform | Lưu ý |
| --- | --- | --- | --- |
| `module` | Module chứa lớp được define | Module tương ứng lớp đó | Overload 6 args |
| `loader` | Defining loader (có thể null cho bootstrap) | Defining loader | Đừng mặc định luôn là system loader |
| `className` | Internal binary name, thường slash-separated | Tương tự | Ví dụ `java/util/List`; có thể null trong vài trường hợp đặc biệt |
| `classBeingRedefined` | **null** | `Class<?>` target non-null | Phân biệt callback phase |
| `protectionDomain` | Protection domain của class | Domain liên quan | Không lạm dụng cấp quyền |
| `classfileBuffer` | Bytes tại phase đó | Bytes theo pipeline retransform/redefine | Không mutate |

Với default-package class `RtTarget`, `className` truyền vào là `"RtTarget"`. Với package `com.example.Target`, tên internal dùng slash `"com/example/Target"`. Nếu transformer lọc sai tên, nó sẽ không sửa được target hoặc tệ hơn sửa nhầm class.

### 7.2. `classBeingRedefined` không null không nghĩa chỉ retransform

Khi ban đầu load, field này null. Khi **redefine hoặc retransform**, field này là `Class<?>` của lớp đang xử lý. Muốn biết thao tác nào đang diễn ra cần quản lý pipeline/trigger của agent, không suy từ `classBeingRedefined!=null` rằng chắc chắn là retransform.

## 8. Retransformation gọi lại những gì?

Quá trình `Instrumentation.retransformClasses(Class<?>... classes)` theo Java SE26:
1. JVM bắt đầu từ bytes dùng cho định nghĩa class đầu tiên hoặc bản **redefine gần nhất**.
2. Với mỗi **incapable transformer**, JVM dùng lại kết quả lần transform trước ở load/redefine **mà không gọi callback**.
3. Với mỗi **capable transformer**, JVM gọi lại callback theo thứ tự trong group.
4. JVM xác minh kết quả class file sau pipeline và áp dụng định nghĩa mới nếu hợp lệ.

Những điều rất dễ hiểu sai:
- Không lấy `classfileBuffer` cũ từ “lần retransform gần nhất” như một mảng đã hoàn toàn được biến đổi bởi capable transformers.
- Không đảm bảo bytes JVM cung cấp sau retransform **giống hệt byte-for-byte** bản class file trên đĩa: constant pool order/entries, attributes và member order có thể đã được VM thay đổi trong giới hạn spec.
- Không thể dựa vào offsets/hashes của raw input từ lần đầu như identifier bất biến qua mọi lượt retransform.
- Cần bảo đảm output **hợp lệ khi apply lặp lại** và không làm quá giới hạn schema.

### 8.1. Khai báo transformer mới sau khi class đã load

Một transformer được đăng ký **sau khi một class đã được define** sẽ không tự được gọi ngược thời gian. Nếu chỉ gọi `retransformClasses`:
- Transformer **mới thuộc nhóm incapable** không nhận callback retransform; không có transformation cũ của nó để “tái dùng”.
- Transformer **mới thuộc nhóm capable** có thể được gọi trong pass retransform tiếp theo.

Vì vậy nếu agent được attach sau application startup mà muốn thay classes đã load, nó cần capability retransform và transformer compatible, hoặc phương án redefine rõ ràng. Không dùng `addTransformer(...false)` rồi nghĩ `retransformClasses` sẽ gọi mọi transformer kể cả incapable.

### 8.2. “Idempotent” có hai cấp độ

Một transformer tốt nên:
- Tạo cùng output khi nhận **cùng input và cùng configuration**.
- Không tự nhét thêm lời gọi logging, fields hoặc instructions không kiểm soát ở mỗi pass.
- Nhận diện khi bytes đã được đánh dấu instrumented và tránh duplicate instrumentation.
- Chịu được việc incapable output được reused nhưng capable callback chạy nhiều lần.

Fixture thay STAGE101 thành RESULT01/02/03 **cố ý phụ thuộc callback count** để quan sát thay đổi. Production agent làm metrics/tracing không nên phụ thuộc số lần callback theo cách này; output cần xác định theo explicit configuration và bytecode schema.

## 9. Giới hạn của class redefinition/retransformation

JVM TI `RetransformClasses` hiện hành cho phép thay method bodies, constant pool và một số attributes trong giới hạn; nó **không** cho phép tùy tiện:
- Thêm/bớt/đổi tên fields hoặc methods.
- Thay method signatures.
- Thay class modifiers.
- Thay superclass hoặc interfaces/inheritance.
- Thay các attributes `NestHost`, `NestMembers`, `Record`, `PermittedSubclasses`.

Các restrictions có thể được mở rộng ở Java version tương lai, nhưng tại Java SE26/JVMTI 26 là giới hạn đang áp dụng. Nếu transformer tạo schema không hợp lệ, JVM có thể ném `UnsupportedOperationException` hoặc error phù hợp; đừng thiết kế agent “hot add field” bằng retransformation trừ khi version/spec cụ thể cho phép.

### 9.1. `isModifiableClass` không trùng capability check

`inst.isModifiableClass(target)` cho biết JVM có thể thay định nghĩa class đó theo class kind/capabilities, nhưng vẫn cần `inst.isRetransformClassesSupported()` nếu bạn dùng `retransformClasses`.

- Primitive classes như `int.class` **không modifiable**.
- Array classes như `String[].class` **không modifiable**.
- Một ordinary class như `RtTarget` **có thể modifiable**, như fixture đã xác minh trên OpenJDK24.
- Một số JVM classes, hidden/non-modifiable classes có hạn chế riêng; không blind retransform toàn bộ `getAllLoadedClasses`.
- Với unmodifiable target, `retransformClasses` có thể ném `UnmodifiableClassException`.

### 9.2. Không chạy lại static initializer và không reset fields

Khi retransform thành công:
- Static field values giữ nguyên.
- JVM **không chạy lại class initializers**.
- Instances hiện tại giữ field values trước đó.
- Những lần gọi method **mới** có thể chạy method body mới.
- Nếu method đang có active stack frame, frame cũ tiếp tục theo bytecode cũ; invocation sau mới dùng bytecode đã được cập nhật.

Fixture kiểm thử `RtTarget.initializeCount==1` và `instance.number()==7` xuyên suốt hai retransform; cùng instance trả lần lượt RESULT01, RESULT02, RESULT03 qua method code mới.

### 9.3. Atomicity khi retransform nhiều classes

`retransformClasses(A.class,B.class)` cho JVM cơ hội áp dụng các thay đổi liên quan trong một operation. Theo Java SE26 `Instrumentation` docs, nếu có exception trong operation thì **không class nào được retransformed**. Không suy từ đây rằng agent có thể làm transactional rollback mọi side effect mà callbacks đã tự gây ra (logging, counters, external state). Cần giữ callbacks ít side effects và quản lý fail behavior có kiểm soát.

## 10. Callback trả `null`, trả bytes hoặc ném exception

Theo Javadoc `ClassFileTransformer`:
- `return null`: không thay đổi bytes, chain tiếp tục.
- `return newByteArray`: chain dùng bytes mới.
- Ném exception chưa catch (kể cả `IllegalClassFormatException`): JVM vẫn cố gọi các transformers tiếp theo; về hiệu ứng biến đổi callback đó tương tự `return null`.
- `IllegalClassFormatException` giúp báo rõ class file input invalid nhưng **không phải nút “stop all transformers”**.
- Nếu output của pipeline cuối là class file không hợp lệ, class load/redefine/retransform có thể fail khi JVM verify/install.
- `premain` **khác callback**: nếu `premain` ném uncaught exception khi startup, JVM có thể abort trước application main.

### 10.1. Fixture mô phỏng lỗi trong transformer

Sau lần retransform đầu tiên, fixture đăng ký thêm hai **capable** transformers:
1. `failing`: nhận RESULT03, cố ý ném `IllegalClassFormatException`.
2. `noChange`: vẫn được gọi và thấy RESULT03, rồi `return null`.

Kết quả:
- `failingHits==1`.
- `nullHits==1`.
- `nullSawThirdResult==true`.
- `RtTarget.result()==RESULT03`.

Điều này chứng minh **một transformer ném exception không tự ngăn callback kế tiếp**, và `return null` không xóa transformation hợp lệ của transformer trước.

### 10.2. Không dùng exception như control flow bình thường

Trong agent production:
- Dùng `return null` khi class không match hoặc không cần rewrite.
- Bắt đúng exception liên quan class format/bytecode library; log có giới hạn và tránh log classfile bytes.
- Dùng `IllegalClassFormatException` khi xác định input invalid thay vì dùng để skip mọi class.
- Không che giấu lỗi instrumentation đã làm class invalid.
- Không phụ thuộc agent exception để “tắt” một class hay bỏ qua policy kiểm soát.
- Thiết kế callback có khả năng concurrent execution và không gây recursive class loading.

## 11. Lifecycle transformer và khả năng đồng thời

### 11.1. removeTransformer

`Instrumentation.removeTransformer(transformer)`:
- Trả `true` nếu tìm và gỡ một registration matching.
- Trả `false` nếu không có instance matching để gỡ.
- Nếu đăng ký cùng instance nhiều lần, method loại registration matching **mới nhất**, vì vậy không nên add trùng một instance.
- Trong JVM đa luồng, một callback **vẫn có thể đến sau khi removeTransformer trả về** vì concurrent class loading.

**Không suy** removeTransformer sẽ tự khôi phục bytecode các classes đã loaded. Nếu muốn bỏ instrumentation khỏi classes hiện tại, cần một chiến lược retransform/redefine hợp lệ, xử lý đúng thứ tự capable/incapable và khả năng unsupported.

### 11.2. Không giữ global lock trong callback

Class loading có locks và class initialization phases nhạy cảm. Một transformer tạo class loading đệ quy (đặc biệt core JDK classes) có thể gây `LinkageError` hoặc class circularity. Không gọi application business logic tùy tiện bên trong `transform`. Một pattern an toàn:
- Filter `className` rất sớm.
- Return null ngay nếu không phải target.
- Không làm network/disk I/O trong callback.
- Không gọi code cần loading class đang transform.
- Tối thiểu hóa allocation và synchronization.
- Có sampling và error counters an toàn không phụ thuộc full application stack.
- Tránh thay JDK classes trừ khi có thật sự cần và có test rigorous.

### 11.3. Module/classloader awareness

Một class name có thể xuất hiện ở nhiều class loaders. Với môi trường ứng dụng có plugins/frameworks, cùng `"com/example/Service"` từ hai loaders có thể là hai classes khác nhau.

Filter tốt xem:
- `className` (internal slash form).
- `loader`, có thể null cho bootstrap loader.
- `module` ở overload hiện đại.
- `protectionDomain` khi security policy yêu cầu.
- `classBeingRedefined` và trạng thái method support.
- Những lớp core đang cần cho chính transformer.

Đừng sửa toàn bộ classes theo substring match như `name.contains("Service")`.

## 12. Test harness — một Java agent chạy thật (Java 17+)

### 12.1. Tại sao chọn hai transformers và một constant pool patch?

Mục tiêu là chứng minh **callback rules**, không giấu các kết quả sau framework instrumentation. Fixture chỉ dùng JDK standard tooling:
- `RtAgent.java`: giữ `Instrumentation`; tạo incapable/capable/failing/null transformers và một parser thay UTF8 constant.
- `RtTarget.java`: class nạp sau `premain`, method `result()` ban đầu trả ORIGIN01, có static initializer và instance field.
- `RtDriver.java`: chủ động gọi `RtAgent.retransform(RtTarget.class)` hai lần, đối chiếu 31 assertions.
- `rt-agent.mf`: cấp capability true.
- `jar` từ JDK để đóng gói agent JAR.

Code chạy trong **một JVM test tách biệt**. Agent chỉ sửa `RtTarget` do test sở hữu và không có network/file I/O trong transform. Mọi string marker đều **8 byte ASCII**, tránh đổi constant pool length/schema.

### 12.2. File `RtAgent.java` — toàn bộ source


```java
import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.IllegalClassFormatException;
import java.lang.instrument.Instrumentation;
import java.nio.charset.StandardCharsets;
import java.security.ProtectionDomain;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicInteger;

public final class RtAgent {
    private static Instrumentation instrument;
    static final AtomicInteger incapableHits = new AtomicInteger();
    static final AtomicInteger capableHits = new AtomicInteger();
    static final AtomicInteger failingHits = new AtomicInteger();
    static final AtomicInteger nullHits = new AtomicInteger();
    static final List<String> events = new CopyOnWriteArrayList<>();
    static volatile boolean initialClassWasNull;
    static volatile boolean everyRetransformClassWasTarget = true;
    static volatile boolean modernModuleCallbackSeen;
    static volatile boolean nullSawThirdResult;

    private static final ClassFileTransformer incapable =
            new ClassFileTransformer() {
                // The five-argument transform is still supported in Java 17+.
                // The default six-argument overload forwards to it.
                @Override
                public byte[] transform(
                        ClassLoader loader, String name, Class<?> previous,
                        ProtectionDomain protectionDomain, byte[] bytes)
                        throws IllegalClassFormatException {
                    if (!"RtTarget".equals(name)) return null;
                    int n = incapableHits.incrementAndGet();
                    events.add("incap:" + (previous == null ? "load" : "again")
                            + ":ORIGIN01");
                    initialClassWasNull = previous == null;
                    if (n != 1)
                        throw new IllegalClassFormatException(
                                "incapable transformer should not run again");
                    return ClassPatch.replaceUtf8(
                            bytes, "ORIGIN01", "STAGE101");
                }
            };

    private static final ClassFileTransformer capable =
            new ClassFileTransformer() {
                @Override
                public byte[] transform(
                        Module module, ClassLoader loader, String name,
                        Class<?> previous, ProtectionDomain domain, byte[] bytes)
                        throws IllegalClassFormatException {
                    if (!"RtTarget".equals(name)) return null;
                    modernModuleCallbackSeen = module != null;
                    int n = capableHits.incrementAndGet();
                    if (previous == null && n != 1)
                        throw new IllegalClassFormatException("unexpected load");
                    if (previous != null && !"RtTarget".equals(
                            previous.getSimpleName()))
                        everyRetransformClassWasTarget = false;
                    events.add("cap:" + (previous == null ? "load" : "retransform")
                            + ":STAGE101");
                    String result = switch (n) {
                        case 1 -> "RESULT01";
                        case 2 -> "RESULT02";
                        case 3 -> "RESULT03";
                        default -> throw new IllegalClassFormatException(
                                "unexpected extra callback: " + n);
                    };
                    return ClassPatch.replaceUtf8(
                            bytes, "STAGE101", result);
                }
            };

    private static final ClassFileTransformer failing =
            new ClassFileTransformer() {
                @Override
                public byte[] transform(
                        Module module, ClassLoader loader, String name,
                        Class<?> previous, ProtectionDomain domain, byte[] bytes)
                        throws IllegalClassFormatException {
                    if (!"RtTarget".equals(name)) return null;
                    failingHits.incrementAndGet();
                    events.add("throw:RESULT03");
                    if (!ClassPatch.hasUtf8(bytes, "RESULT03"))
                        throw new AssertionError("unexpected input");
                    throw new IllegalClassFormatException(
                            "deliberate exception, test only");
                }
            };

    private static final ClassFileTransformer noChange =
            new ClassFileTransformer() {
                @Override
                public byte[] transform(
                        Module module, ClassLoader loader, String name,
                        Class<?> previous, ProtectionDomain domain, byte[] bytes) {
                    if (!"RtTarget".equals(name)) return null;
                    nullHits.incrementAndGet();
                    nullSawThirdResult = ClassPatch.hasUtf8(bytes, "RESULT03");
                    events.add("null:RESULT03");
                    return null;
                }
            };

    public static void premain(String options, Instrumentation inst) {
        instrument = inst;
        if (!inst.isRetransformClassesSupported())
            throw new IllegalStateException(
                    "Use an agent manifest with Can-Retransform-Classes: true");
        // Deliberately register capable BEFORE incapable.
        // Java transform GROUP order must still place incapable first.
        inst.addTransformer(capable, true);
        inst.addTransformer(incapable, false);
    }

    public static boolean supported() {
        return instrument.isRetransformClassesSupported();
    }

    public static boolean isModifiable(Class<?> type) {
        return instrument.isModifiableClass(type);
    }

    public static boolean targetLoaded(Class<?> type) {
        for (Class<?> loaded : instrument.getAllLoadedClasses())
            if (loaded == type) return true;
        return false;
    }

    public static void installPostLoadFailureAndNull() {
        instrument.addTransformer(failing, true);
        instrument.addTransformer(noChange, true);
    }

    public static void retransform(Class<?> type) throws Exception {
        instrument.retransformClasses(type);
    }

    public static boolean cleanup() {
        return instrument.removeTransformer(noChange)
                && instrument.removeTransformer(failing)
                && instrument.removeTransformer(capable)
                && instrument.removeTransformer(incapable);
    }

    public static boolean noDuplicateToRemove() {
        return !instrument.removeTransformer(capable);
    }
}

final class ClassPatch {
    private ClassPatch() {}

    private static int unsignedTwo(byte[] bytes, int pos) {
        return ((bytes[pos] & 0xff) << 8) | (bytes[pos + 1] & 0xff);
    }

    static boolean hasUtf8(byte[] source, String expected) {
        return locateUtf8(source, expected) >= 0;
    }

    static byte[] replaceUtf8(byte[] source, String oldText, String newText) {
        byte[] from = oldText.getBytes(StandardCharsets.US_ASCII);
        byte[] to = newText.getBytes(StandardCharsets.US_ASCII);
        if (from.length != to.length)
            throw new IllegalArgumentException(
                    "fixture requires equal-length UTF8 constant");
        int start = locateUtf8(source, oldText);
        if (start < 0)
            throw new IllegalArgumentException(
                    "fixture constant not found: " + oldText);
        byte[] copy = source.clone(); // NEVER mutate JVM-owned input!
        System.arraycopy(to, 0, copy, start, to.length);
        return copy;
    }

    private static int locateUtf8(byte[] data, String sought) {
        byte[] expected = sought.getBytes(StandardCharsets.US_ASCII);
        if (data.length < 10) throw new IllegalArgumentException("class too short");
        int magic = ((data[0] & 0xff) << 24) | ((data[1] & 0xff) << 16)
                | ((data[2] & 0xff) << 8) | (data[3] & 0xff);
        if (magic != 0xCAFEBABE)
            throw new IllegalArgumentException("not a class file");
        int count = unsignedTwo(data, 8);
        int at = 10;
        int found = -1;
        for (int i = 1; i < count; ++i) {
            int tag = data[at++] & 0xff;
            switch (tag) {
                case 1 -> {
                    int length = unsignedTwo(data, at);
                    at += 2;
                    if (length == expected.length) {
                        boolean equal = true;
                        for (int b = 0; b < length; b++) {
                            if (data[at + b] != expected[b]) {
                                equal = false;
                                break;
                            }
                        }
                        if (equal) {
                            if (found != -1)
                                throw new IllegalArgumentException(
                                        "duplicate constant not expected");
                            found = at;
                        }
                    }
                    at += length;
                }
                case 3, 4, 9, 10, 11, 12, 17, 18 -> at += 4;
                case 5, 6 -> {
                    at += 8;
                    i++; // long and double occupy two constant-pool indices
                }
                case 7, 8, 16, 19, 20 -> at += 2;
                case 15 -> at += 3;
                default -> throw new IllegalArgumentException(
                        "unsupported constant-pool tag " + tag);
            }
        }
        return found;
    }
}
```

### 12.3. File `RtTarget.java`

Lớp test được nạp **sau khi agent đã đăng ký**. Mọi method và field name giữ nguyên qua các lần retransform.


```java
public final class RtTarget {
    public static int initializeCount;
    static {
        initializeCount++;
    }
    private int number = 7;

    public String result() {
        return "ORIGIN01";
    }

    public int number() {
        return number;
    }
}
```

### 12.4. File `RtDriver.java`

Driver chứng minh hai callback groups, non-cumulative inputs, return null/exception, static state và cleanup. Assertions tự in PASS, không cần các giá trị log không xác định từ JVM.


```java
import java.util.List;

public final class RtDriver {
    private static int passed;

    static void check(String label, boolean ok) {
        if (!ok) throw new AssertionError("FAIL " + label);
        System.out.println("PASS " + label);
        passed++;
    }

    public static void main(String[] args) throws Exception {
        check("manifest-and-vm-retransform-supported", RtAgent.supported());
        check("primitive-is-not-modifiable", !RtAgent.isModifiable(int.class));
        check("array-is-not-modifiable",
                !RtAgent.isModifiable(String[].class));

        RtTarget instance = new RtTarget();
        check("target-loaded-from-app-classpath",
                RtAgent.targetLoaded(RtTarget.class));
        check("target-class-is-modifiable",
                RtAgent.isModifiable(RtTarget.class));
        check("initial-load-rewrote-to-result01",
                "RESULT01".equals(instance.result()));
        check("target-initialized-once", RtTarget.initializeCount == 1);
        check("existing-instance-state-seven", instance.number() == 7);
        check("incapable-called-once-on-load",
                RtAgent.incapableHits.get() == 1);
        check("capable-called-once-on-load",
                RtAgent.capableHits.get() == 1);
        check("class-being-redefined-null-on-load",
                RtAgent.initialClassWasNull);
        check("new-module-aware-callback-invoked",
                RtAgent.modernModuleCallbackSeen);
        check("noncap-before-cap-despite-reversed-registration",
                RtAgent.events.equals(List.of(
                        "incap:load:ORIGIN01",
                        "cap:load:STAGE101")));

        RtAgent.retransform(RtTarget.class);
        check("result02-after-first-retransform",
                "RESULT02".equals(instance.result()));
        check("incapable-not-called-on-retransform",
                RtAgent.incapableHits.get() == 1);
        check("capable-called-again-on-retransform",
                RtAgent.capableHits.get() == 2);
        check("retransform-received-nonnull-class",
                RtAgent.everyRetransformClassWasTarget);
        check("incapable-previous-output-reused",
                RtAgent.events.equals(List.of(
                        "incap:load:ORIGIN01",
                        "cap:load:STAGE101",
                        "cap:retransform:STAGE101")));
        check("static-initializer-not-rerun",
                RtTarget.initializeCount == 1);
        check("same-instance-keeps-existing-field",
                instance.number() == 7);

        RtAgent.installPostLoadFailureAndNull();
        RtAgent.retransform(RtTarget.class);
        check("result03-after-second-retransform",
                "RESULT03".equals(instance.result()));
        check("incapable-still-called-only-once",
                RtAgent.incapableHits.get() == 1);
        check("capable-called-exactly-three",
                RtAgent.capableHits.get() == 3);
        check("throwing-transformer-was-called",
                RtAgent.failingHits.get() == 1);
        check("later-null-return-transformer-was-called",
                RtAgent.nullHits.get() == 1);
        check("later-transformer-saw-result03",
                RtAgent.nullSawThirdResult);
        check("all-callbacks-in-expected-order",
                RtAgent.events.equals(List.of(
                        "incap:load:ORIGIN01",
                        "cap:load:STAGE101",
                        "cap:retransform:STAGE101",
                        "cap:retransform:STAGE101",
                        "throw:RESULT03",
                        "null:RESULT03")));
        check("second-retransform-not-cumulative",
                "RESULT03".equals(new RtTarget().result()));
        check("static-state-remains-once",
                RtTarget.initializeCount == 1);
        check("remove-transformers-succeeds", RtAgent.cleanup());
        check("remove-again-returns-false",
                RtAgent.noDuplicateToRemove());
        System.out.println("passed=" + passed);
    }
}
```

### 12.5. Manifest của agent true-capability

Lưu `rt-agent.mf` (có dòng trống cuối file):

```text
Manifest-Version: 1.0
Premain-Class: RtAgent
Can-Retransform-Classes: true

```

**Không đặt attribute này ở một file text bất kỳ rồi chỉ chạy java -cp.** Nó phải nằm trong **main manifest của JAR dùng với -javaagent**.

### 12.6. Build và chạy trong Windows PowerShell

Đặt ba file `.java` và `rt-agent.mf` trong một folder test riêng. PowerShell (không dùng Maven):

```powershell
New-Item -ItemType Directory -Force agent-classes,app-classes | Out-Null

javac --release 17 -encoding UTF-8 -d agent-classes RtAgent.java
javac --release 17 -encoding UTF-8 -cp agent-classes -d app-classes RtTarget.java RtDriver.java

jar cfm rt-agent.jar rt-agent.mf -C agent-classes .

java "-javaagent:rt-agent.jar" -cp "rt-agent.jar;app-classes" RtDriver
```

Trên Windows, separator của classpath là **dấu chấm phẩy** `;`. Lệnh `jar` sẽ đóng các class generated của agent, bao gồm anonymous transformer classes và `ClassPatch`, vào JAR. Source `RtTarget`/`RtDriver` ở thư mục app-classes.

### 12.7. Build và chạy trong Linux/macOS

```bash
mkdir -p agent-classes app-classes

javac --release 17 -encoding UTF-8 -d agent-classes RtAgent.java
javac --release 17 -encoding UTF-8 -cp agent-classes -d app-classes RtTarget.java RtDriver.java

jar cfm rt-agent.jar rt-agent.mf -C agent-classes .

java -javaagent:rt-agent.jar -cp "rt-agent.jar:app-classes" RtDriver
```

Trên Linux/macOS, classpath separator là **dấu hai chấm** `:`. Agent JAR nằm trên classpath để `RtDriver` có thể tham chiếu `RtAgent` trong bài test; ở production thường tách rõ API chia sẻ giữa agent và application.

### 12.8. Stdout đã kiểm chứng với OpenJDK 24

```text
PASS manifest-and-vm-retransform-supported
PASS primitive-is-not-modifiable
PASS array-is-not-modifiable
PASS target-loaded-from-app-classpath
PASS target-class-is-modifiable
PASS initial-load-rewrote-to-result01
PASS target-initialized-once
PASS existing-instance-state-seven
PASS incapable-called-once-on-load
PASS capable-called-once-on-load
PASS class-being-redefined-null-on-load
PASS new-module-aware-callback-invoked
PASS noncap-before-cap-despite-reversed-registration
PASS result02-after-first-retransform
PASS incapable-not-called-on-retransform
PASS capable-called-again-on-retransform
PASS retransform-received-nonnull-class
PASS incapable-previous-output-reused
PASS static-initializer-not-rerun
PASS same-instance-keeps-existing-field
PASS result03-after-second-retransform
PASS incapable-still-called-only-once
PASS capable-called-exactly-three
PASS throwing-transformer-was-called
PASS later-null-return-transformer-was-called
PASS later-transformer-saw-result03
PASS all-callbacks-in-expected-order
PASS second-retransform-not-cumulative
PASS static-state-remains-once
PASS remove-transformers-succeeds
PASS remove-again-returns-false
passed=31
```

**Kết quả:** Biên dịch `javac --release 17` và chạy `java -javaagent` thành công; toàn bộ **31/31 assertions PASS**.

### 12.9. Giải thích timeline callback đã test

| Thời điểm | Incapable callback | Capable callback | Method `result()` |
| --- | --- | --- | --- |
| Load lần đầu | Gọi 1: ORIGIN01 → STAGE101 | Gọi 1: STAGE101 → RESULT01 | `RESULT01` |
| Retransform lần 1 | **Không gọi**; reuse STAGE101 | Gọi 2: STAGE101 → RESULT02 | `RESULT02` |
| Thêm 2 capable transformers | Không được retroactive callback | Chờ lượt retransform sau | `RESULT02` |
| Retransform lần 2 | **Không gọi**; reuse STAGE101 | Gọi 3: STAGE101 → RESULT03; sau đó failure và null handlers | `RESULT03` |
| removeTransformer | Không tự undo bytes | Không tự undo bytes | Kết quả hiện tại chưa tự trở về ban đầu |

Danh sách events chính xác:
```text
incap:load:ORIGIN01
cap:load:STAGE101
cap:retransform:STAGE101
cap:retransform:STAGE101
throw:RESULT03
null:RESULT03
```

Events trên được kiểm tra bằng `List.equals` trong driver chứ không phải bản dump phỏng đoán. Test cũng xác minh:
- Incapable count cuối cùng là 1.
- Capable count cuối cùng là 3.
- Failure count là 1 và null-return transformer count là 1.
- `classBeingRedefined==null` lúc load, nonnull lúc retransform.
- `Module` callback sáu tham số được nhận.
- Static initializer không chạy lại.
- Instance field giá trị 7 được giữ.
- Primitive và array classes không modifiable.
- `removeTransformer` thành công rồi lời gọi lặp trả false.

## 13. Test negative — JAR không bật retransformation

Không nên chỉ viết code giả định `isRetransformClassesSupported()==true`. Java SE26 vẫn coi đây là **optional capability**. Để kiểm tra, fixture thứ hai dùng manifest:

```text
Manifest-Version: 1.0
Premain-Class: RtNoCapAgent
Can-Retransform-Classes: false

```

Với manifest này trên runtime đã test:
- `isRetransformClassesSupported()==false`.
- `addTransformer(transformer,false)` vẫn hợp lệ.
- `addTransformer(transformer,true)` ném `UnsupportedOperationException`.
- `retransformClasses(RtNoCapAgent.class)` ném `UnsupportedOperationException`.
- `removeTransformer` vẫn hoạt động.
- `isRedefineClassesSupported()==false` vì không cấp capability đó.
- Mọi kiểm tra không làm thay đổi lớp ứng dụng.

### 13.1. File `RtNoCapAgent.java`


```java
import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;

public final class RtNoCapAgent {
    private static int passed;
    private static boolean executed;

    private static void check(String name, boolean ok) {
        if (!ok) throw new AssertionError("FAIL " + name);
        System.out.println("PASS " + name);
        passed++;
    }

    public static void premain(String args, Instrumentation inst)
            throws Exception {
        check("manifest-without-capability-reports-false",
                !inst.isRetransformClassesSupported());
        check("no-redefine-capability-without-manifest",
                !inst.isRedefineClassesSupported());
        ClassFileTransformer transformer = new ClassFileTransformer() {};
        inst.addTransformer(transformer, false);
        check("incapable-registration-works", true);
        boolean failedCapable = false;
        try {
            inst.addTransformer(transformer, true);
        } catch (UnsupportedOperationException expected) {
            failedCapable = true;
        }
        check("capable-registration-rejected",
                failedCapable);
        boolean rejectedRetransform = false;
        try {
            inst.retransformClasses(RtNoCapAgent.class);
        } catch (UnsupportedOperationException expected) {
            rejectedRetransform = true;
        }
        check("retransform-call-rejected",
                rejectedRetransform);
        check("incapable-transformer-can-be-removed",
                inst.removeTransformer(transformer));
        check("second-removal-returns-false",
                !inst.removeTransformer(transformer));
        check("capability-answer-is-stable",
                !inst.isRetransformClassesSupported());
        executed = true;
        System.out.println("agentPassed=" + passed);
    }

    public static boolean completed() {
        return executed && passed == 8;
    }
}
```

### 13.2. File `RtNoCapMain.java`


```java
public final class RtNoCapMain {
    public static void main(String[] args) {
        if (!RtNoCapAgent.completed())
            throw new AssertionError("agent checks were not executed");
        System.out.println("PASS no-capability-main-confirmed");
        System.out.println("totalPassed=9");
    }
}
```

### 13.3. Build/run negative test

Windows PowerShell, chạy trong folder có hai file `.java` và manifest `rt-nocap.mf`:

```powershell
New-Item -ItemType Directory -Force nocap-classes | Out-Null

javac --release 17 -encoding UTF-8 -d nocap-classes RtNoCapAgent.java RtNoCapMain.java
jar cfm rt-nocap.jar rt-nocap.mf -C nocap-classes .

java "-javaagent:rt-nocap.jar" -cp "rt-nocap.jar" RtNoCapMain
```

Linux/macOS:

```bash
mkdir -p nocap-classes
javac --release 17 -encoding UTF-8 -d nocap-classes RtNoCapAgent.java RtNoCapMain.java
jar cfm rt-nocap.jar rt-nocap.mf -C nocap-classes .
java -javaagent:rt-nocap.jar -cp "rt-nocap.jar" RtNoCapMain
```

### 13.4. Stdout verified

```text
PASS manifest-without-capability-reports-false
PASS no-redefine-capability-without-manifest
PASS incapable-registration-works
PASS capable-registration-rejected
PASS retransform-call-rejected
PASS incapable-transformer-can-be-removed
PASS second-removal-returns-false
PASS capability-answer-is-stable
agentPassed=8
PASS no-capability-main-confirmed
totalPassed=9
```

**Kết quả:** **9/9 assertions PASS**, Java 17 source trên OpenJDK24. Hai chương trình tổng cộng **40/40 PASS**. Lưu ý Java SE26 không bắt buộc mọi JVM hỗ trợ retransformation; kịch bản manifest `true` sẽ cần một VM có capability, còn kịch bản `false` có thể chạy để kiểm tra nhánh không hỗ trợ.

## 14. Bảng callback cho những kiểu đăng ký thường gặp

| Transformer | Cách đăng ký | Class load | Redefine | Retransform |
| --- | --- | --- | --- | --- |
| `A` | `addTransformer(A)` | Callback | Callback | **Không callback**, output trước có thể reused |
| `B` | `addTransformer(B,false)` | Callback | Callback | **Không callback**, output trước có thể reused |
| `C` | `addTransformer(C,true)` | Callback | Callback | **Callback** |
| `D` | Chưa đăng ký | Không callback | Không callback | Không callback |
| `E` | Thêm `true` sau khi target đã load | Không retroactive load callback | Nếu future redefine | Khi retransform tiếp theo |
| `F` | Thêm `false` sau khi target đã load | Không retroactive load callback | Nếu future redefine | **Không callback** |
| `G` | Đã `removeTransformer` | Có thể có in-flight callback do race | Không được kỳ vọng cho new events | Không được kỳ vọng cho new events |

Trong cột retransform của A/B, “output trước có thể reused” áp dụng khi chúng đã tham gia **last load/redefine** của class. Không bịa output nếu transformer được add sau khi class đã load và chưa từng được gọi cho class đó.

### 14.1. Thứ tự không phải thứ tự “register chung” toàn bộ

`capable` được add trước `incapable` nhưng lúc load:
```text
incapable -> capable
```

Nếu có 2 incapable `I1,I2` và 2 capable `C1,C2` thì:
```text
I1 -> I2 -> C1 -> C2
```

với giả định đăng ký theo thứ tự từng group trên và không có native transformers; nếu có native JVMTI transformers phải chèn đúng hai nhóm native theo Java SE26 spec. Lúc retransform, `I1/I2` không được gọi mà cached results được tái sử dụng, sau đó `C1/C2` được gọi.

## 15. Khác biệt giữa callback “đã được gọi” và “đã thay đổi bytes”

Một transformer có thể được gọi nhưng không thực hiện transform:
- Không match `className`, trả null.
- Class đã có instrumentation tương ứng, trả null.
- Input bất thường, ném `IllegalClassFormatException`.
- Policy cho phép nhưng không cần thêm instrumentation cho phase này.
- Transformer được gọi với `classBeingRedefined` non-null và từ chối rewrite để giữ trạng thái.

Do đó **callback count không đồng nghĩa số classes đã được biến đổi**, và số request retransform không bằng số method body thay đổi.

Telemetry agent cần ít nhất hai counters:
- `transform_callbacks_total`: callback đã được gọi, phân loại phase/class group.
- `transform_changes_total`: callback thực sự trả bytes hợp lệ khác với input.

Đây là tên metrics minh họa, không phải counters được JVM tự tạo. Không đếm các case `return null` như “class modified”.

## 16. Lỗi và exception cần xử lý

| Lỗi/tình huống | Nguồn | Cách hiểu/khắc phục |
| --- | --- | --- |
| `UnsupportedOperationException` khi add true | VM/agent không có retransform capability | Kiểm tra manifest + JVM capability |
| `UnsupportedOperationException` khi retransform | Capability false hoặc unsupported change | Kiểm tra support/schema |
| `UnmodifiableClassException` | Class không thể sửa | `isModifiableClass` và hạn chế class kind |
| `ClassFormatError` | Output classfile không hợp lệ | Verify bytes/parser/frame/constant pool |
| `NoClassDefFoundError` | Class name trong bytes không đúng | Kiểm tra classfile internal name |
| `UnsupportedClassVersionError` | Output bytecode version không tương thích JDK | Compile/generate đúng class file version |
| `ClassCircularityError` | Loading cycle | Giảm dependencies trong transform |
| `LinkageError` | Class linking/resolution sai | Kiểm tra classloader/module/bytecode |
| `IllegalClassFormatException` từ callback | Callback báo input không hợp lệ | Không tự stop toàn pipeline; cần log root cause |
| `NullPointerException` | Null class/class array/transformer | Validate caller input |
| Transformer exception khi load | Callback code lỗi | JVM vẫn gọi tiếp transforms; cuối cùng may load fail |
| Agent `premain` exception | Entrypoint startup lỗi | JVM abort trước application main |

### 16.1. Unmodifiable ≠ incapability of a transformer

- `isModifiableClass(A.class)==false`: bản thân class A không thể retransform/redefine.
- `isRetransformClassesSupported()==false`: VM/agent configuration không cấp operation.
- `addTransformer(T,false)`: transformer T **không được gọi** trong retransform callbacks.

Ba khái niệm trên **không thay thế lẫn nhau**. Một class modifiable vẫn không thể retransform nếu agent không có capability. Một transformer incapable vẫn có thể biến đổi một class modifiable khi **load/redefine**.

### 16.2. Không bắt lỗi rồi bỏ qua mọi thất bại

Một agent production nên:
- Log gọn class name, phase, transformer version, exception type; không dump bytecode thô.
- Có circuit breaker/bypass có thể kiểm soát nếu một transformer gặp lỗi liên tiếp.
- Kiểm tra schema và test trên **cùng JDK/provider** với môi trường chạy.
- Phân biệt lỗi agent startup, lỗi callback, lỗi JVM verify và lỗi application code.
- Không cố gắng sửa core classes trong lúc callback cần chính các core classes đó.
- Dùng fail-safe policy rõ ràng: có những instrumentation chỉ để quan sát có thể bỏ qua, nhưng security-critical policy không được âm thầm bỏ lỗi rồi báo thành công.

## 17. Đặt transformer đúng phạm vi an toàn

### 17.1. Match chính xác target classes

Ví dụ filter có chủ đích:

```java
if (!"com/example/Target".equals(className)) {
    return null;
}
```

Nếu một runtime có nhiều versions của cùng class ở những `ClassLoader` khác nhau, cần bổ sung filter loader/module. Không dùng generic match `name.contains("Target")` rồi áp instrumentation lên cả thư viện, JDK, agents khác.

### 17.2. Giữ callback nhỏ, thread-safe và không tái nhập

- Transformer được gọi trong class-loading pipeline nhạy cảm.
- Callback có thể đến từ nhiều threads; mutable shared counters/config cần thread-safe.
- Có thể có in-flight callbacks sau remove.
- Không cố ý load class đang được transform bằng reflection trong callback.
- Không chạy Java app request logic/network calls trong transform.
- Không dùng một global lock gây deadlock với class loader locks.
- Không instrument bootstrap/JDK classes nếu chưa đánh giá cẩn thận.
- Dùng `Module`/`ClassLoader`/`ProtectionDomain` theo các ranh giới của sản phẩm.

### 17.3. Kiểm tra thứ tự nhiều agents

Lệnh Java có thể có nhiều `-javaagent:...`; `premain` thường được khởi động theo thứ tự command line. Nhưng transformer chaining tiếp tục tuân thủ **capability grouping và per-group registration order**, không đơn giản dựa vào thứ tự tên agent. Nếu nhiều agents cùng sửa một method, phải test chain của **toàn bộ agents**, xác định instrumentation nào được apply trước và tránh duplicate probes.

### 17.4. Không coi retransform là free operation

Retransformation có JVM coordination, class parsing/verification và chi phí CPU. Gọi retransform cho hàng nghìn classes liên tục có thể làm tăng latency hoặc CPU. Thiết kế:
- Chọn chính xác target classes.
- Kiểm tra `isRetransformClassesSupported()`/`isModifiableClass()`.
- Debounce config changes.
- Batch classes khi cần logic interdependent, tránh repeated large scans.
- Có rate limits, health metrics và rollback strategy.
- Canh chừng JIT deoptimization hoặc các chi phí runtime khác tùy VM.
- Không gọi retransform từ callback trên chính class đang transform.

## 18. Quy trình kiểm tra một agent không chạy như mong đợi

### Tình huống A — capable transformer không có callback retransform

1. Kiểm tra JVM khởi động với đúng agent JAR.
2. Kiểm tra main manifest của JAR có `Premain-Class` và `Can-Retransform-Classes: true` không.
3. Log/đo `inst.isRetransformClassesSupported()`.
4. Xác minh đã gọi `addTransformer(t,true)` thay vì overload một tham số.
5. Xác minh `retransformClasses(targetClass)` thật sự được gọi.
6. Xác minh `isModifiableClass(targetClass)`.
7. Kiểm tra `className` nội bộ slash-separated và classloader identity.
8. Tìm lỗi/return null/bypass sớm trong filter.
9. Kiểm tra class chưa bị kết thúc/unloaded, hoặc VM không hỗ trợ loại class.
10. Test trên đúng JDK và classpath/modular setup.

### Tình huống B — incapable transformer chỉ được gọi một lần

Nếu bạn chỉ thấy callback khi initial load mà không thấy lúc `retransformClasses`, đó **là behavior đúng** cho `canRetransform=false`. Không tự “fix” bằng cách register trùng cùng instance; hãy xác định liệu agent có thực sự cần capable transformer, và bật capability có chủ đích khi đủ điều kiện.

### Tình huống C — transformation bị nhân đôi sau nhiều lượt

Xem bạn có:
- Lấy bytes đang chứa output của capable pass cũ và add probes lần nữa không?
- Không kiểm tra marker instrumented trong class?
- Register cùng transformer instance nhiều lần?
- Có nhiều Java agents và native transformers?
- Không phân biệt last redefinition bytes với initial bytes?

Thiết kế idempotent theo classfile input/config và kiểm thử nhiều lượt load/retransform/redefine.

### Tình huống D — class không chạy sau retransform

Kiểm tra:
- JVM TI schema limits, method/field signatures/attributes.
- Parser/ASM/bytecode generator compatibility với classfile major version.
- `StackMapTable`, constant pool indexes, invocation descriptors.
- Lỗi `UnsupportedOperationException`, `ClassFormatError` hoặc `LinkageError`.
- Những method frames cũ đang chạy (chỉ invokes mới dùng implementation mới).

Không blindly retry same invalid bytes trên production mà không sửa root cause.

## 19. Những lỗi phổ biến

**1. Gọi `addTransformer(t)` rồi nghĩ t có retransformation capability.**  
Sai: mặc định là false.

**2. Chỉ thêm `Can-Retransform-Classes: true` nhưng quên kiểm tra JVM support.**  
Capability vẫn optional.

**3. Không thêm manifest capability rồi gọi `addTransformer(t,true)`.**  
Bị `UnsupportedOperationException` như fixture negative.

**4. Nghĩ mọi transformer chạy lại khi `retransformClasses`.**  
Chỉ capable callbacks được gọi; incapable outputs cũ reused.

**5. Nghĩ incapable transformer chạy đúng một lần trong đời JVM.**  
Nó vẫn được gọi mỗi class load và redefine liên quan.

**6. Đảo registration order rồi nghĩ capable luôn chạy trước.**  
Grouping khiến incapable group chạy trước capable group.

**7. Nghĩ capable retransform nhận output của capable pass ngay trước.**  
Theo spec nó bắt đầu từ initial/redefinition bytes cộng reused incapable outputs, không cumulative như vậy.

**8. Coi `classBeingRedefined!=null` chỉ áp dụng cho retransform.**  
Nó cũng xảy ra khi redefine.

**9. Tìm className bằng Java dot notation.**  
Callback nhận internal slash form cho classes có package.

**10. Không xử lý `loader==null` cho bootstrap classes.**  
Dễ gây NullPointerException trong class loading.

**11. Chỉ override overload 5 tham số rồi cho rằng JDK9+ không gọi nữa.**  
Overload 6 tham số default forwards, 5 tham số vẫn supported.

**12. Không override overload nào và mong có transform.**  
Default implementation trả null.

**13. Mutate trực tiếp `classfileBuffer`.**  
Trái contract; phải copy rồi return new bytes.

**14. Return null để “xóa class”.**  
Null nghĩa **không thay đổi class bytes** ở callback đó.

**15. Ném IllegalClassFormatException rồi mong callback chain dừng.**  
JVM vẫn gọi callbacks tiếp theo.

**16. Suy transformer exception luôn làm startup abort.**  
Callback exception khác với uncaught `premain` exception.

**17. Thêm field/method mới qua retransformation.**  
Không hợp lệ theo JVM TI restrictions hiện hành.

**18. Tự động reset static fields/constructor state khi retransform.**  
JVM không rerun `<clinit>`.

**19. Nghĩ existing instances bị recreate khi retransform.**  
Fields/instances cũ được giữ, new method invocation dùng code mới.

**20. Không nghĩ tới active stack frames.**  
Frames đang chạy tiếp tục old bytecodes; only future invocations new code.

**21. Nghĩ `isModifiableClass==true` thay thế capability check.**  
Cần cả support và target modifiable.

**22. Thử retransform primitives/array classes.**  
Primitive/array classes không modifiable.

**23. Thêm incapable transformer sau class load rồi mong nó chạy nhờ retransform.**  
Incapable không có retransform callback.

**24. Gỡ transformer và nghĩ mọi lớp tự khôi phục original bytecode.**  
Remove không hồi phục class definitions đã áp dụng.

**25. Không phòng concurrent callback sau remove.**  
Javadoc cho phép callbacks in-flight.

**26. Đăng ký cùng transformer instance nhiều lần.**  
Không nên; remove chỉ gỡ registration mới nhất.

**27. Instrument core JDK classes mà chính agent cần để chạy.**  
Dễ class circularity/linkage error.

**28. Dùng classfile parser tự viết cho mọi class trong production.**  
Fixture parser chỉ chứng minh callback; production cần tools được validate.

**29. Không test manifest capability false.**  
Hệ thống hỏng khi agent không có optional capability.

**30. Chạy experimental retransform agent trên JVM production chưa được phép.**  
Agent có thể can thiệp vào bytecode và ảnh hưởng bảo mật/hiệu năng; cần quy trình phê duyệt.

## 20. Checklist áp dụng và kiểm thử

- [ ] Xác định agent khởi động qua `-javaagent` hay runtime attach policy được cho phép.
- [ ] Đảm bảo manifest `Premain-Class`/`Agent-Class` chính xác.
- [ ] Khi cần retransform, manifest có `Can-Retransform-Classes: true`.
- [ ] Kiểm tra `isRetransformClassesSupported` trước khi register capable/call retransform.
- [ ] Kiểm tra `isModifiableClass` với từng target cụ thể.
- [ ] Không gọi retransform cho primitive/array classes.
- [ ] Phân loại transformers: incapable và capable.
- [ ] Nắm thứ tự groups có cả native transformers.
- [ ] Ghi rõ callback behavior cho load/redefine/retransform.
- [ ] Dùng `transform(Module,...)` khi cần module awareness.
- [ ] Filter className/classLoader/module chính xác, tránh broad match.
- [ ] Return null cho no-op, clone byte[] trước khi sửa.
- [ ] Kiểm tra classfile verifier và schema restrictions.
- [ ] Không add fields/methods/change signatures/inheritance qua retransformation.
- [ ] Giữ callback thread-safe, nonblocking, tránh recursive class loads.
- [ ] Test initial transform và ít nhất hai lượt retransform.
- [ ] Test incapable callback không chạy lại, output cũ reused.
- [ ] Test capable input không tích lũy output pass trước.
- [ ] Test exception/return null không tự cắt chain.
- [ ] Test static initializer và instance state không bị reset.
- [ ] Test registration removal và race assumptions.
- [ ] Test capability disabled trong một JAR manifest riêng.
- [ ] Không tin classes toàn JVM đều modifiable.
- [ ] Chạy tất cả tests trong JVM cô lập, không trên prod service.
- [ ] Có logging, rollback/rate limit/incident response cho agent deployments.
- [ ] Chỉ dùng JDK26/JVM TI26 và các API còn áp dụng theo Special Note.

## 21. Câu hỏi tự kiểm tra

**1. Transformer được xem là retransformation-capable lúc nào?**  
Khi được add bằng `addTransformer(t,true)` và agent/VM có capability hỗ trợ.

**2. `addTransformer(t)` có tương đương `true` không?**  
Không, tương đương `false`.

**3. Manifest cần gì để retransform?**  
`Can-Retransform-Classes: true`, cộng JVM hỗ trợ.

**4. `isRetransformClassesSupported` có thay theo từng call trong cùng JVM không?**  
Không; spec nói kết quả ổn định trong JVM instance.

**5. Incapable transformer có chạy lúc initial load?**  
Có, nếu registered và class không bị loại bởi filter.

**6. Incapable transformer có chạy lại khi retransform?**  
Không, JVM reuse output cũ của nó nếu đã có trong pipeline.

**7. Capable transformer có chạy khi retransform?**  
Có, khi `retransformClasses` thành công tới callback và registered/capability phù hợp.

**8. Incapable và capable cùng tồn tại thì nhóm nào chạy trước?**  
Incapable trước capable, với native groups theo spec.

**9. Tại sao capable được add đầu tiên vẫn chạy sau incapable?**  
Vì callback grouping dựa vào capability trước, không chỉ registration chronology.

**10. `classBeingRedefined==null` khi nào?**  
Khi callback do class load/definition; không null khi redefine/retransform.

**11. Class names trong transform dùng dấu slash hay dot?**  
Internal slash form, ví dụ `java/util/List`.

**12. Callback 6arg mặc định làm gì nếu chỉ override 5arg?**  
Forward sang method 5arg.

**13. Callback trả null nghĩa gì?**  
Không sửa bytecode trong callback đó.

**14. Một callback ném exception có dừng mọi transformer không?**  
Không; JVM vẫn tiếp tục gọi callbacks còn lại.

**15. Retransformation có được thêm method mới không?**  
Không theo JVM TI restrictions hiện hành.

**16. Retransformation có rerun static initializer không?**  
Không.

**17. Existing instances có mất field values khi retransform không?**  
Không.

**18. Active frame có chạy method bytes mới ngay khi retransform không?**  
Không, frame đã hoạt động tiếp tục old code; invocation mới dùng code mới.

**19. `removeTransformer` có undo biến đổi trước không?**  
Không tự động.

**20. Những class nào luôn không modifiable?**  
Primitive và array classes.

**21. Trong fixture, incumbent incapable callback chạy bao nhiêu lần?**  
Một lần initial load; không chạy trong hai retransform.

**22. Capable callback chạy bao nhiêu lần?**  
Ba lần: load, retransform 1, retransform 2.

**23. Vì sao input của capable là STAGE101 trong cả ba lần?**  
Do output incapable STAGE101 được JVM tái sử dụng; capable pass trước không tích lũy.

**24. Trong fixture, giá trị method trả về lần lượt là gì?**  
`RESULT01`, `RESULT02`, `RESULT03`.

**25. Khi manifest false, addTransformer(true) ném gì?**  
`UnsupportedOperationException`.

**26. Tổng bao nhiêu assertions được thực thi ở hai JAR?**  
**31 + 9 = 40**, tất cả PASS trên OpenJDK 24 trong test đã chạy.

## 22. Tài liệu chính thức Java SE26 / JVM TI26

- [Oracle Java SE 26 — `ClassFileTransformer`](https://docs.oracle.com/en/java/javase/26/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): hai kinds transformer, thứ tự callback bốn groups, chaining, null/exception và hai overload.
- [Oracle Java SE 26 — `Instrumentation`](https://docs.oracle.com/en/java/javase/26/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `addTransformer`, `isRetransformClassesSupported`, `retransformClasses`, `isModifiableClass`, `removeTransformer`, lifecycle.
- [Oracle Java SE 26 — `java.lang.instrument` package spec](https://docs.oracle.com/en/java/javase/26/docs/api/java.instrument/java/lang/instrument/package-summary.html): `-javaagent`, `premain`/`agentmain`, agent manifest attributes, security.
- [Oracle JDK 26 — JAR File Specification](https://docs.oracle.com/en/java/javase/26/docs/specs/jar/jar.html): manifest syntax/attributes.
- [JVM Tool Interface 26.0.0 — `RetransformClasses`](https://download.java.net/java/early_access/jdk26/docs/specs/jvmti.html): classfile update restrictions, active stack frames, atomic multi-class retransform và class file load hook.
- [Oracle Java SE 26 — `ClassDefinition`](https://docs.oracle.com/en/java/javase/26/docs/api/java.instrument/java/lang/instrument/ClassDefinition.html): payload cho `redefineClasses`.
- [Oracle Java SE 26 — `IllegalClassFormatException`](https://docs.oracle.com/en/java/javase/26/docs/api/java.instrument/java/lang/instrument/IllegalClassFormatException.html): callback-reported class file issues.
- [Oracle Java SE 26 — `UnmodifiableClassException`](https://docs.oracle.com/en/java/javase/26/docs/api/java.instrument/java/lang/instrument/UnmodifiableClassException.html): class không thể modify.
- [Oracle Java SE 26 — `Module`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Module.html): module information được callback overload sáu tham số cung cấp.

**Kết luận:** Capability retransform được chọn **khi đăng ký transformer** và cần agent manifest + JVM support. Lúc load/redefine, cả capable và incapable có thể được gọi; lúc retransform, JVM **tái dùng output của incapable mà không gọi callback**, đồng thời **gọi lại capable** trên dữ liệu bắt đầu từ original/redefined class (không cộng dồn capable passes cũ). Thứ tự callback theo capability groups, không chỉ theo thứ tự add. Viết transformer an toàn nghĩa là giữ bytes hợp lệ, không mutate input, tránh schema changes, kiểm tra capabilities/target classes và kiểm thử lặp lại trong JVM riêng trước khi triển khai.

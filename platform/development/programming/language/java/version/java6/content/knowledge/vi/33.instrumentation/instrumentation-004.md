# Instrumentation: retransformClasses và khác biệt với redefineClasses

## Mục tiêu học tập

Trong Java hiện đại, **Java Instrumentation API** thuộc package `java.lang.instrument` cho phép Java agent quan sát và biến đổi bytecode của class khi class được nạp, hoặc cập nhật phương thức của class **đã được nạp vào JVM**. Hai API dễ nhầm là **`Instrumentation.retransformClasses(Class<?>...)`** và **`Instrumentation.redefineClasses(ClassDefinition...)`**. Cả hai có thể làm thay đổi phần code sẽ chạy trong các lần gọi method tiếp theo, nhưng **điểm xuất phát bytecode, cách gọi transformer và trách nhiệm cung cấp classfile mới là khác nhau**.

Bài này tập trung đúng đề tài **“retransformClasses và khác biệt với redefineClasses”** và chỉ sử dụng những hợp đồng API còn được hỗ trợ trên Java 17/Java SE 26. Sau bài, bạn có thể:

1. Hiểu `Instrumentation`, `ClassFileTransformer`, `ClassDefinition`, Java agent `premain` và manifest capabilities.
2. Giải thích tại sao **retransformClasses** là cơ chế **chạy lại pipeline biến đổi** dựa trên bytecode xuất phát của class, chứ **không tự đọc `.class` mới từ ổ đĩa**.
3. Giải thích **redefineClasses** nhận **byte[] classfile thay thế do caller đưa vào**, thường phục vụ hot code replacement khi code đã được biên dịch lại.
4. Biết sự khác biệt giữa `addTransformer(transformer,false)` và `addTransformer(transformer,true)`.
5. Mô tả cách **transformer không hỗ trợ retransformation được reuse kết quả cũ nhưng không bị gọi lại**, trong khi retransformation-capable transformers được gọi lại.
6. Hiểu rằng **redefineClasses có thể gọi lại cả hai nhóm transformer**, với input đầu vào là classfile mới.
7. Dùng đúng `isRetransformClassesSupported`, `isRedefineClassesSupported` và `isModifiableClass`, đồng thời hiểu manifest là **điều kiện cần nhưng chưa đủ**.
8. Phân biệt **biến đổi body/constant pool** với **thay schema** (fields, methods, method signatures, hierarchy) vốn thường không được HotSwap chuẩn chấp nhận.
9. Hiểu **static fields/instances không bị reset**, **class initializers không chạy lại**, và **active stack frames tiếp tục bytecode cũ**.
10. Chạy một demo thật bằng `-javaagent`, hai transformers, một class gốc, một class cùng tên được biên dịch riêng và một chương trình điều phối.
11. Đọc đúng **9 dòng stdout đã kiểm chứng**: callback counts, nội dung method thay đổi và static state giữ nguyên.
12. Xử lý transform ordering, re-entrancy, class loader identity, compatibility, lifecycle, concurrency, security và rollback trong ứng dụng thực.

**Mốc phiên bản:** `retransformClasses` là API từ Java 6 và vẫn đang được hỗ trợ. Các interfaces/methods trong bài là Java SE hiện hành. Demo được biên dịch bằng **`javac --release 17`** và chạy trên **OpenJDK 24.0.2**; Javadoc Java SE 26 được dùng để đối chiếu contract mới nhất. Không dùng các cách can thiệp lỗi thời hoặc dựa vào internal JDK APIs chưa được hỗ trợ.

---

## 1. Bối cảnh: Java agent tác động lên bytecode khi nào?

Một JVM có thể nạp một class từ JAR, module hoặc class loader tùy biến. Agent cần quan sát/điều chỉnh bytecode trong một số trường hợp:

- Gắn instrumentation để thống kê lời gọi, timing và coverage.
- Thêm tracing/logging logic vào method body mà không cần sửa mã nguồn ứng dụng.
- Thay một implementation bằng classfile được biên dịch lại trong debugging/hot patch hợp lệ.
- Cập nhật instrumentation rules cho những classes đang chạy.
- Dừng áp dụng một số probes hoặc thay thế bằng probes khác, với điều kiện tương thích.
- Phân tích performance/security trong môi trường được cho phép.

**Agent là mã đặc quyền chạy trong JVM mục tiêu.** Một transformer có thể làm thay đổi behavior, gây `VerifyError`, `LinkageError` hoặc ảnh hưởng security/performance. Chỉ dùng agent đáng tin và kiểm thử trước khi triển khai.

### 1.1. Luồng khởi động agent bằng `-javaagent`

~~~text
java -javaagent:agent.jar -cp out App
                  │
                  ▼
       JVM đọc agent JAR manifest
       Premain-Class: DemoAgent
                  │
                  ▼
    DemoAgent.premain(args, Instrumentation)
                  │
                  ▼
        inst.addTransformer(...)
                  │
                  ▼
          JVM nạp class Target
                  │
                  ▼
           transform callbacks
                  │
                  ▼
       Bytecode đã biến đổi được định nghĩa
                  │
                  ▼
            App gọi Target.message()
~~~

Đây là **startup agent**, không cần dynamic attach vào một JVM đang chạy. `premain` nhận `Instrumentation` từ JVM và đăng ký các transformers trước khi `Target` được nạp.

### 1.2. Cách lấy Instrumentation instance

Hai cách chính theo package specification:

- **Startup agent:** JVM gọi `public static void premain(String args, Instrumentation inst)` khi được cấu hình qua `-javaagent` hoặc cơ chế launcher-agent tương ứng.
- **Runtime/dynamic agent** nếu implementation hỗ trợ: JVM gọi `agentmain(String args, Instrumentation inst)`.

Một ứng dụng thông thường không có API hợp lệ để tự tạo `new Instrumentation()`; đó là một interface có implementation do JVM/agent mechanism cấp. Trên các JDK hiện đại, việc tải agent động cần có **chính sách bảo mật/opt-in** tương ứng. Demo chọn **startup `-javaagent`**, không cần attach vào tiến trình ngoài.

### 1.3. Instrumentation không phải một class loader

Agent không thay thế `ClassLoader` và không tự “reload cả JVM”. Nó tham gia pipeline **trước khi class definition được áp dụng**, hoặc điều chỉnh method bodies của một class đã được nạp khi JVM hỗ trợ.

Class identity vẫn phụ thuộc **binary name + defining class loader**. Có hai class cùng tên `com.example.Foo` trong hai class loaders thì đó có thể là hai `Class<?>` khác nhau. Muốn retransform/redefine phải chọn **đúng Class object** cần xử lý.

---

## 2. So sánh retransformClasses và redefineClasses

| Tiêu chí | `retransformClasses` | `redefineClasses` |
| --- | --- | --- |
| Mục đích chính | Chạy lại transformations cho class đã load | Thay class definition bằng classfile mới đã cung cấp |
| API | `retransformClasses(Class<?>... classes)` | `redefineClasses(ClassDefinition... definitions)` |
| Đầu vào caller cung cấp | Các `Class<?>` targets | Các cặp `Class<?>` và `byte[]` replacement |
| Nguồn bytecode khởi đầu | Original classfile bytes hoặc bytes từ lần redefine gần nhất, có thể khác layout lúc đầu | New classfile bytes từ `ClassDefinition` |
| Transformer `canRetransform=false` | Không callback lại; reuse kết quả của lần load/redefine gần nhất | Callback được gọi lại |
| Transformer `canRetransform=true` | Callback được gọi lại | Callback được gọi |
| Khi không đăng ký transformer | Thường không tạo code changes mới từ classfile trên ổ đĩa | Có thể thay method code bằng replacement classfile |
| Capability gate | `isRetransformClassesSupported()` | `isRedefineClassesSupported()` |
| Manifest capability | `Can-Retransform-Classes: true` | `Can-Redefine-Classes: true` |
| Kiểm tra class | `isModifiableClass(clazz)` | `isModifiableClass(clazz)` |
| Thay class schema | Không tự do, chịu giới hạn VM/JVMTI | Không tự do, chịu giới hạn VM/JVMTI |
| Chạy lại class initializer | Không | Không |
| Reset static/instance state | Không | Không |
| Active frames | Tiếp tục code cũ đến khi hoàn tất frame | Tiếp tục code cũ đến khi hoàn tất frame |
| Nếu toàn bộ batch thất bại | Không áp dụng retransformation nào trong batch | Không áp dụng redefinition nào trong batch |
| Use cases phổ biến | Reconfigure tracing/profiling/counters | Hot-replace compiled method implementation |

**Điểm ghi nhớ:** `retransformClasses` làm việc với **pipeline transformers** và bytecode nền do JVM quản lý; `redefineClasses` bắt đầu từ **classfile bytes thay thế**. Gọi `retransformClasses(Target.class)` **không phải “đọc lại Target.class từ thư mục classpath”**.

### 2.1. Bản chất của retransform

~~~text
Target original BASE
        │
        ▼
[transformer incapable]   BASE → A001   (chạy khi load)
        │
        ▼
[transformer capable]     A001 → T001   (chạy khi load)
        │
        ▼
    class Target đang hoạt động
        │
        ▼
retransformClasses(Target.class)
        │
        ▼
JVM xây lại input dựa trên original BASE
        │
        ▼
[incapable result REUSED] A001          (không gọi lại)
        │
        ▼
[capable RUN AGAIN]      A001 → T002
        │
        ▼
  code mới cho những method invocations tiếp theo
~~~

JVM không lấy `T001` vừa install làm input rồi bồi thêm một lớp `T002` lên trên theo ý nghĩa xếp chồng vô hạn. **Kết quả không có khả năng retransform được áp lại theo contract; transformer capable chạy trên input đã tái tạo.**

### 2.2. Bản chất của redefine

~~~text
App đọc replacement/Target.class
             │
             ▼
        ClassDefinition(
            Target.class,
            replacementBytes
        )
             │
             ▼
inst.redefineClasses(...)
             │
             ▼
New classfile input RDEF
             │
             ▼
[incapable RUN AGAIN] RDEF → A101
             │
             ▼
[capable RUN AGAIN]   A101 → T101
             │
             ▼
   class Target tiếp tục chạy code mới
~~~

Khác với retransform, **caller chịu trách nhiệm chuẩn bị valid replacement classfile bytes**, bao gồm binary name giống class target, bytecode version được hỗ trợ và schema hợp lệ theo VM.

### 2.3. Retransform sau một lần redefine

Khi class đã từng được redefine, **lần retransform sau đó dùng điểm xuất phát là bytes của lần redefine gần nhất**, không tự quay về bản classfile gốc BASE từ ban đầu.

~~~text
Ban đầu:  BASE → A001 → T001
Retrans:  BASE → [reuse A001] → T002
Redefine: RDEF → A101 → T101
Retrans:  RDEF → [reuse A101] → T102
~~~

Ví dụ dưới đây xác nhận bốn giai đoạn với các giá trị String khác nhau để người học không phải đoán.

---

## 3. Transformer có thể và không thể retransform

### 3.1. Đăng ký transformer

~~~java
// MẢNH MINH HỌA trong premain có Instrumentation inst.
inst.addTransformer(transformerA, false);
inst.addTransformer(transformerB, true);
~~~

- `false`: transformer **không có capability retransformation**, nhưng vẫn được gọi khi **class load** và **class redefine**.
- `true`: transformer được gọi khi **class load, class redefine và class retransform**.
- `inst.addTransformer(transformer)` tương đương `inst.addTransformer(transformer,false)`.

**Cần kiểm tra `isRetransformClassesSupported()` trước khi đăng ký với true.** Nếu JVM config không hỗ trợ và bạn cố đăng ký với `true`, API có thể ném `UnsupportedOperationException`.

### 3.2. Quy tắc thứ tự

Theo Javadoc Java SE 26, các nhóm được áp dụng theo thứ tự:

1. Java transformers **retransformation-incapable**.
2. Native JVMTI transformers **retransformation-incapable**.
3. Java transformers **retransformation-capable**.
4. Native JVMTI transformers **retransformation-capable**.

Trong mỗi nhóm, các transformers được gọi theo **thứ tự đăng ký**. Đừng nghĩ thứ tự hoàn toàn chỉ là global registration time giữa mọi nhóm.

### 3.3. `canRetransform=false` không phải “chỉ chạy một lần mãi mãi”

Đây là ngộ nhận phổ biến. Transformer không có retransformation capability **vẫn chạy lại trong lần redefine**, vì `redefineClasses` là một sự kiện khác. Chỉ riêng lần **retransform**, JVM reuse kết quả biến đổi cũ mà không gọi lại callback cho nhóm này.

### 3.4. `canRetransform=true` không hứa JVM luôn hỗ trợ

Capability tùy theo JVM configuration và manifest. Cờ `Can-Retransform-Classes: true` trong JAR **không buộc** mọi VM phải hỗ trợ. Ngay cả khi JVM có thể retransform, một class cụ thể có thể không modifiable.

### 3.5. `ClassFileTransformer` hiện nay không phải functional interface

Java SE 26 khai báo **hai overload `transform` đều có default implementation**:

~~~java
// MẢNH MINH HỌA method signatures:
default byte[] transform(
        ClassLoader loader,
        String className,
        Class<?> classBeingRedefined,
        ProtectionDomain protectionDomain,
        byte[] classfileBuffer);

default byte[] transform(
        Module module,
        ClassLoader loader,
        String className,
        Class<?> classBeingRedefined,
        ProtectionDomain protectionDomain,
        byte[] classfileBuffer);
~~~

Vì không có abstract method nào, **không thể dùng lambda** `ClassFileTransformer t = (args) -> ...` như một functional interface trên Java 17/24. Hãy dùng **anonymous class** hoặc class implements ClassFileTransformer và **override một overload**. Demo override overload 6 tham số có `Module`.

Đây là điểm dễ bị nhầm khi dựa vào bài hướng dẫn cũ hoặc suy diễn tên interface. Trong Java agent production, nên có test biên dịch với đúng `--release` mà ứng dụng triển khai.

### 3.6. Transformer return null và byte array ownership

- Trả **`null`**: không thay đổi classfile bytes ở bước này.
- Trả **`byte[]` mới**: JVM dùng nó làm input cho transformer kế tiếp.
- **Không được sửa trực tiếp `classfileBuffer` đầu vào**.
- Output phải là **classfile hợp lệ**.
- Với retransform/redefine, output phải tuân thủ **legal redefinition schema restrictions**.

Javadoc cũng nói nếu transformer ném exception chưa được bắt, **JVM vẫn gọi transformers tiếp theo và vẫn tiếp tục thử load/redefine/retransform**, tương tự một biến đổi trả null. Vì thế **không thể dùng `throw` từ transform như một cơ chế bảo đảm hủy operation**. Trong production nên chủ động kiểm soát validation, logging và kết quả tại caller, và dùng bytecode library đáng tin cậy.

### 3.7. `classBeingRedefined`

Trong callback:

- Khi class được **load lần đầu**, `classBeingRedefined` thường là **null**.
- Khi **retransform hoặc redefine**, `classBeingRedefined` là `Class<?>` tương ứng.

Chỉ dựa vào field này **không phân biệt được retransform và redefine**, vì cả hai đều có class object. Nếu agent phải biết mode, có thể phối hợp từ caller/agent state với concurrency control hoặc thiết kế transformer theo **input bytes/capability** thay vì suy đoán event type.

---

## 4. Capability checks và manifest

### 4.1. Khai báo trong agent JAR

~~~text
Manifest-Version: 1.0
Premain-Class: DemoAgent
Can-Retransform-Classes: true
Can-Redefine-Classes: true
~~~

Mỗi thuộc tính ở trên là một entry trong **main manifest**. `Premain-Class` là binary name của agent entrypoint. Hai cờ Can-* tuyên bố agent muốn hai capabilities. Nếu thiếu hoặc đặt false, việc gọi capability tương ứng có thể không được JVM cho phép ngay cả khi nền tảng có hỗ trợ cơ bản.

### 4.2. Hỏi JVM configuration

~~~java
// MẢNH MINH HỌA.
boolean canRetransform = inst.isRetransformClassesSupported();
boolean canRedefine = inst.isRedefineClassesSupported();
boolean targetModifiable = inst.isModifiableClass(Target.class);
~~~

**Cả ba điều kiện** nên được kiểm tra trước một demo yêu cầu cả hai actions. Nhưng cần phân biệt:

- `isRetransformClassesSupported()` là capability **toàn JVM/agent configuration**.
- `isRedefineClassesSupported()` là capability **toàn JVM/agent configuration**, độc lập với cờ retransform.
- `isModifiableClass(Target.class)` là property của **một class cụ thể**.

Cả hai method is*Supported trả ổn định trong một JVM instance theo Java SE 26. `isModifiableClass` **không tự phụ thuộc** hai flags kia; có thể trả true dù một method retransform/redefine đang disabled ở JVM config.

### 4.3. Class nào không modifiable?

Theo Instrumentation Javadoc, **primitive classes và array classes không bao giờ modifiable**. Một số JVM-special, hidden hoặc internal classes cũng có thể không hợp lệ hoặc bị giới hạn. Đừng khẳng định chỉ cần `Class<?>` tồn tại là có thể thay.

~~~java
// MẢNH MINH HỌA.
boolean modifiableArray = inst.isModifiableClass(String[].class);
boolean modifiablePrimitive = inst.isModifiableClass(int.class);
// Hai classes này không modifiable theo API contract.
~~~

Không nên chạy thử redefinition lên core JDK classes tùy ý trong production. Class loader/JPMS/security implications rất lớn.

### 4.4. `isModifiableClass=true` không chứng minh mọi bytecode đổi đều hợp lệ

Kể cả có đầy đủ flags và target modifiable, JVM vẫn có thể từ chối **unsupported structural changes**, invalid classfile hoặc linker/verifier errors. `isModifiableClass` chỉ là một check đầu; **không đảm bảo replacement bytes hợp lệ**.

---

## 5. Hạn chế HotSwap và state sau khi thay bytecode

### 5.1. Không tùy ý thay schema

Theo JVM TI RedefineClasses/RetransformClasses contract đang dùng, các thay đổi sau **thường không được hỗ trợ** trong HotSwap chuẩn:

- Thêm, xóa hoặc đổi tên fields.
- Thêm, xóa hoặc đổi tên methods.
- Đổi method descriptor/signature.
- Đổi superclass hoặc interfaces/inheritance.
- Đổi những ràng buộc classfile cấu trúc nhạy cảm như nest/record/permitted-subclass metadata trái với VM restrictions.
- Thay binary name của class được redefine.

**Thay method body** với cùng methods/fields/hierarchy là use case điển hình. Khi yêu cầu thay schema, cách an toàn hơn thường là **deploy bản ứng dụng mới** hoặc thiết kế extension/load isolation rõ ràng. Không coi hot redefinition là “reload bất kỳ version Java class nào”.

### 5.2. Active stack frames tiếp tục chạy bytecode cũ

Nếu một method đang chạy trong một stack frame tại thời điểm retransform/redefine, **frame hiện tại tiếp tục bytecode cũ**. Những invocation mới sẽ dùng method version mới đã được install.

~~~text
Thread A vào method xử lý dài (old bytecode)
                 │
JVM redefine/retransform class
                 │
Thread A vẫn chạy frame cũ đến khi return
Thread B gọi method mới → dùng new bytecode
~~~

Không nên dùng HotSwap như một guarantee mọi thread lập tức đồng bộ sang behavior mới. Điều này đặc biệt quan trọng khi instrumentation cần đảm bảo tracing/security policy nhất quán trên mọi active requests.

### 5.3. Không chạy lại static initializer

`<clinit>` không bị chạy lại vì retransform/redefine. Các **static fields hiện có giữ giá trị**, và object instances đang tồn tại cũng không tự được xây dựng lại.

Trong demo:

- Target gốc có `private static int state = 5`.
- Target replacement có dòng `private static int state = 999`.
- Sau khi đã chạy Target, redefinition **không chạy lại `<clinit>`**, nên state giữ đếm 6 → 7 → 8 → 9, **không nhảy sang 999**.

Đó là một cách kiểm chứng thực nghiệm trực quan rằng redefine khác với load một class mới từ đầu.

### 5.4. Object identity và state vẫn giữ

Các references tới objects đã có tiếp tục trỏ cùng objects. Static fields không bị reset. Nếu một thay đổi method body giả định state mới, migration logic không tự xảy ra.

Muốn thay behavior an toàn, replacement code phải tương thích với state hiện tồn tại. Những thay đổi về business invariants có thể đòi version migration/restart thay vì HotSwap.

### 5.5. Atomicity theo batch

Cả hai API đều nhận nhiều classes trong một call:

~~~java
// MẢNH MINH HỌA:
inst.retransformClasses(A.class, B.class);

// Hoặc:
inst.redefineClasses(
        new ClassDefinition(A.class, aBytes),
        new ClassDefinition(B.class, bBytes));
~~~

Theo API, nếu operation thất bại, **không class nào trong batch bị cập nhật**. Điều này quan trọng khi A và B phụ thuộc API bên nhau.

Nhưng **atomicity khi install class definitions không có nghĩa business transactions đang chạy được tự rollback**. Nếu các thread đang chạy code cũ, in-flight state vẫn phải xử lý theo semantics ứng dụng.

---

## 6. Ví dụ chạy được: cả hai thao tác trong một agent

Demo thực nghiệm tạo **bốn file nguồn/nội dung chính**:

~~~text
instrumentation-demo/
├── src/
│   ├── DemoAgent.java
│   ├── Target.java
│   └── App.java
├── replacement-src/
│   └── Target.java         # Class cùng binary name, body khác
├── agent-manifest.mf
├── out/                    # javac tạo
├── replacement/            # javac tạo
└── agent.jar               # jar tạo
~~~

**Lưu ý:** Có hai file tên `Target.java`, nhưng nằm ở **hai source roots khác nhau** và được biên dịch **riêng**. Chúng cùng định nghĩa `public final class Target` có fields/methods giống schema; chỉ khác **chuỗi literal** và giá trị static initializer.

Mục tiêu của instrumentation:

- `Target` gốc trả `"BASE"`.
- Transformer **incapable** đổi `"BASE"` thành `"A001"`.
- Transformer **capable** tiếp tục đổi `"A001"` thành `"T001"` trong load đầu.
- Lần retransform đầu, incapable không callback lại, capable đổi kết quả reused thành `"T002"`.
- Replacement classfile trả `"RDEF"`; redefine gọi incapable đổi thành `"A101"`, capable đổi thành `"T101"`.
- Retransform sau redefine, reuse `"A101"` và capable đổi thành `"T102"`.

**Cảnh báo kỹ thuật:** Để ví dụ thuần JDK và dễ thấy, transformer dùng một **phép thay 4 byte ASCII** trong `.class` đã được biên dịch, với yêu cầu token tồn tại duy nhất và độ dài không đổi. Đây là **kỹ thuật test fixture chuyên biệt**, không phải một parser/classfile rewriter tổng quát. Với production cần **bytecode parser/transformer có kiểm chứng** (ví dụ thư viện ASM/Byte Buddy tương thích với JDK đang dùng hoặc Class-File API hiện hành theo phiên bản) để xử lý constant pool, attributes, offsets, frames và classfile versions đúng cách. Không dùng find-and-replace bytes tùy ý cho classes thật.

### 6.1. File `src/Target.java` gốc

~~~java
public final class Target {
    private static int state = 5;

    public static String message() {
        return "BASE";
    }

    public static int increment() {
        return ++state;
    }
}
~~~

**Schema:** một field static int `state`, hai methods static `message()` và `increment()`. Body trả String `"BASE"`.

### 6.2. File `replacement-src/Target.java`

~~~java
public final class Target {
    private static int state = 999;

    public static String message() {
        return "RDEF";
    }

    public static int increment() {
        return ++state;
    }
}
~~~

Tên class, field và method signatures **giữ nguyên**. Phương thức message có literal khác. Giá trị 999 giúp chứng minh `<clinit>` không được chạy lại: method sau redefine vẫn thấy counter tăng tiếp, không reset về 999.

### 6.3. File `src/DemoAgent.java` — startup agent và hai transformers

~~~java
import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.nio.charset.StandardCharsets;
import java.security.ProtectionDomain;

public final class DemoAgent {
    private static Instrumentation instrumentation;
    private static int incapableCalls;
    private static int capableCalls;

    public static void premain(String arguments, Instrumentation inst) {
        instrumentation = inst;
        ClassFileTransformer incapable = new ClassFileTransformer() {
            @Override
            public byte[] transform(Module module, ClassLoader loader,
                    String name, Class<?> type, ProtectionDomain domain,
                    byte[] bytes) {
                if (!"Target".equals(name)) return null;
                incapableCalls++;
                byte[] original = replaceExact(bytes, "BASE", "A001");
                if (original != null) return original;
                byte[] replacement = replaceExact(bytes, "RDEF", "A101");
                if (replacement != null) return replacement;
                throw new IllegalStateException("unexpected original/replacement bytes");
            }
        };
        ClassFileTransformer capable = new ClassFileTransformer() {
            @Override
            public byte[] transform(Module module, ClassLoader loader,
                    String name, Class<?> type, ProtectionDomain domain,
                    byte[] bytes) {
                if (!"Target".equals(name)) return null;
                capableCalls++;
                if (capableCalls <= 2) {
                    return replaceRequired(bytes, "A001",
                            capableCalls == 1 ? "T001" : "T002");
                }
                return replaceRequired(bytes, "A101",
                        capableCalls == 3 ? "T101" : "T102");
            }
        };
        inst.addTransformer(incapable, false);
        inst.addTransformer(capable, true);
    }

    private static byte[] replaceRequired(byte[] bytes, String from, String to) {
        byte[] result = replaceExact(bytes, from, to);
        if (result == null) throw new IllegalArgumentException("missing constant");
        return result;
    }

    private static byte[] replaceExact(byte[] bytes, String from, String to) {
        byte[] left = from.getBytes(StandardCharsets.US_ASCII);
        byte[] right = to.getBytes(StandardCharsets.US_ASCII);
        if (left.length != right.length) throw new IllegalArgumentException("length mismatch");
        int position = -1;
        for (int i = 0; i <= bytes.length - left.length; i++) {
            boolean found = true;
            for (int j = 0; j < left.length; j++) {
                if (bytes[i + j] != left[j]) {found = false; break;}
            }
            if (found) {
                if (position != -1) throw new IllegalStateException("duplicate constant");
                position = i;
            }
        }
        if (position == -1) return null;
        byte[] copy = bytes.clone();
        System.arraycopy(right, 0, copy, position, right.length);
        return copy;
    }

    public static Instrumentation instrumentation() {
        return instrumentation;
    }

    public static String counts() {
        return incapableCalls + "/" + capableCalls;
    }
}
~~~

**Điều cần phân biệt:**

- Đây là implementation tường minh, **không dùng lambda** cho `ClassFileTransformer` vì interface hiện hành không có abstract method để làm functional interface.
- `premain` chạy trước App.main và đăng ký hai transformers.
- Cả hai transformers chỉ xử lý đúng binary/internal name `"Target"`, không sửa JDK classes.
- Incapable có `canRetransform=false`; capable có `true`.
- `replaceExact` tạo một **byte[] copy**, không sửa `classfileBuffer` đầu vào.
- Mỗi token phải xuất hiện **đúng một lần**, độ dài replacement bằng token cũ; nếu không, fixture có lỗi.
- Return `null` với những classes khác — không làm thay đổi chúng.
- `incapableCalls` và `capableCalls` là **counters chỉ phục vụ demo tuần tự**, không thiết kế cho concurrent class loading production. Transformer thật cần thread safety và tránh giữ global mutable sequence numbers để quyết định output.
- Nếu token bị thiếu và transformer throw exception, JDK có thể coi như không transform; do đó test kiểm tra **kết quả class behavior + callback counts**, không nghĩ exception là một lệnh rollback đảm bảo.

### 6.4. File `src/App.java` — gọi hai APIs

~~~java
import java.lang.instrument.ClassDefinition;
import java.lang.instrument.Instrumentation;
import java.nio.file.Files;
import java.nio.file.Path;

public final class App {
    public static void main(String[] args) throws Exception {
        Instrumentation inst = DemoAgent.instrumentation();
        if (inst == null) throw new IllegalStateException("run with -javaagent");
        System.out.println("capabilities=retransform:"
                + inst.isRetransformClassesSupported()
                + ",redefine:" + inst.isRedefineClassesSupported()
                + ",modifiable:" + inst.isModifiableClass(Target.class));
        if (!inst.isRetransformClassesSupported()
                || !inst.isRedefineClassesSupported()
                || !inst.isModifiableClass(Target.class)) {
            throw new UnsupportedOperationException(
                    "This demo requires both optional capabilities");
        }

        System.out.println("initial=" + Target.message()
                + ",state=" + Target.increment());
        System.out.println("callbacks=" + DemoAgent.counts());

        inst.retransformClasses(Target.class);
        System.out.println("retransform=" + Target.message()
                + ",state=" + Target.increment());
        System.out.println("callbacks=" + DemoAgent.counts());

        byte[] replacementBytes = Files.readAllBytes(
                Path.of("replacement", "Target.class"));
        inst.redefineClasses(new ClassDefinition(Target.class, replacementBytes));
        System.out.println("redefine=" + Target.message()
                + ",state=" + Target.increment());
        System.out.println("callbacks=" + DemoAgent.counts());

        inst.retransformClasses(Target.class);
        System.out.println("afterRedefineRetransform=" + Target.message()
                + ",state=" + Target.increment());
        System.out.println("callbacks=" + DemoAgent.counts());
    }
}
~~~

**App** đọc bytes từ `replacement/Target.class` chỉ cho redefine; retransform không nhận file path hay byte[] replacement. `ClassDefinition(Target.class, replacementBytes)` gắn đúng class đang chạy với classfile bytes mới.

### 6.5. File `agent-manifest.mf`

~~~text
Manifest-Version: 1.0
Premain-Class: DemoAgent
Can-Retransform-Classes: true
Can-Redefine-Classes: true
~~~

Manifest phải có newline cuối file. Khi đóng agent JAR, công cụ `jar cfm` đưa file manifest vào JAR theo chuẩn. **Không nhầm `Can-Retransform-Classes` với `Can-Redefine-Classes`**; đây là hai capabilities độc lập.

### 6.6. Tạo thư mục và build trên Linux/macOS

Ở root `instrumentation-demo`, đã có các file trong vị trí như sơ đồ:

~~~bash
mkdir -p out replacement

# Biên dịch original Target, App và agent cho Java 17.
javac -encoding UTF-8 --release 17 -d out \
      src/DemoAgent.java src/Target.java src/App.java

# Biên dịch một binary name Target RIÊNG, giữ nguyên cấu trúc.
javac -encoding UTF-8 --release 17 -d replacement \
      replacement-src/Target.java

# Đóng agent.jar có manifest và class agent.
jar cfm agent.jar agent-manifest.mf -C out .

# Chạy classpath app, khởi động agent qua JVM option.
java -javaagent:agent.jar -cp out App
~~~

**Lưu ý:** Ở shell, bạn chỉ cần tạo file nguồn và manifest như các mục trên; các lệnh không tự viết nội dung source. Không biên dịch hai file `Target.java` cùng một lời gọi `javac`/một output folder vì sẽ xung đột binary name. Thư mục **replacement** phải chứa classfile được biên dịch riêng, không phải đổi tên bytecode của một class khác.

### 6.7. Build trên Windows PowerShell

~~~powershell
New-Item -ItemType Directory -Force out,replacement | Out-Null
javac -encoding UTF-8 --release 17 -d out src/DemoAgent.java src/Target.java src/App.java
javac -encoding UTF-8 --release 17 -d replacement replacement-src/Target.java
jar cfm agent.jar agent-manifest.mf -C out .
java -javaagent:agent.jar -cp out App
~~~

Đây là demo startup `-javaagent`. Không dùng Attach API, không cần bật quyền dynamic agent loading, không mở JMX remote port. Chạy trên **JVM test** có quyền kiểm soát; không gắn agent chưa kiểm thử vào ứng dụng production.

### 6.8. Stdout chính xác đã kiểm chứng

~~~text
capabilities=retransform:true,redefine:true,modifiable:true
initial=T001,state=6
callbacks=1/1
retransform=T002,state=7
callbacks=1/2
redefine=T101,state=8
callbacks=2/3
afterRedefineRetransform=T102,state=9
callbacks=2/4
~~~

**Kiểm thử thực tế:** Source gốc và replacement được biên dịch **riêng** với `javac --release 17` trên **OpenJDK 24.0.2**, agent JAR được tạo với manifest trên, chương trình chạy qua `java -javaagent:agent.jar -cp out App`, và cả **9 dòng stdout khớp chính xác**. Test sử dụng thư mục tạm, không thay đổi code repo; file và JAR dùng trong test đã được xóa sau khi kiểm chứng.

**Với JVM không hỗ trợ hai capabilities**, chương trình sẽ dừng với UnsupportedOperationException được chủ động ném và không tạo output chín dòng. Đó là một **giới hạn phù hợp**; không hứa mọi JVM đều cho phép HotSwap. Muốn dùng production, cần có fallback khi runtime không hỗ trợ.

---

## 7. Giải mã 9 dòng output: nguyên nhân chính xác

### 7.1. Capability line

~~~text
capabilities=retransform:true,redefine:true,modifiable:true
~~~

Cả hai capabilities đều được JVM demo hỗ trợ, và class Target đã load có thể modifiable. Đây là tình trạng của **runtime kiểm thử**, không phải giả định universal.

### 7.2. Initial load

~~~text
initial=T001,state=6
callbacks=1/1
~~~

- Bytecode compiler chứa literal BASE.
- In-capable transformer nhận BASE → A001 và tăng count=1.
- Capable transformer nhận A001 → T001 và tăng count=1.
- Target.message() trả T001.
- Lần đầu Target.increment() chạy static state ban đầu 5 → 6.
- Vì lần load gọi cả hai transformers, counts là 1/1.

### 7.3. Retransform đầu tiên

~~~text
retransform=T002,state=7
callbacks=1/2
~~~

- App gọi **`inst.retransformClasses(Target.class)`**.
- JVM áp lại kết quả incapable từ lần load trước **mà không gọi callback**, nên incapable count vẫn **1**.
- Capable callback được gọi lại, nhận A001 → T002; count lên **2**.
- Method mới trả T002.
- Static state vẫn 6, increment tiếp thành 7.

Đây là chứng cứ trực tiếp cho quy tắc **retransform không gọi lại incapable transformers**.

### 7.4. Redefine với replacement classfile

~~~text
redefine=T101,state=8
callbacks=2/3
~~~

- App đọc `replacement/Target.class` có literal RDEF.
- `ClassDefinition` đưa bytes mới vào `redefineClasses`.
- Incapable callback **được gọi lại** và đổi RDEF → A101; count lên **2**.
- Capable callback cũng được gọi, đổi A101 → T101; count lên **3**.
- Method trả T101.
- Mặc dù replacement source có initializer `state = 999`, class đã tồn tại nên `<clinit>` **không chạy lại**; counter tiếp tục từ 7 → 8.

### 7.5. Retransform sau redefine

~~~text
afterRedefineRetransform=T102,state=9
callbacks=2/4
~~~

- Class đã được redefine, nên **baseline bytes** cho retransformation là replacement RDEF (cùng ảnh hưởng của lần redefine theo contract), không phải BASE.
- Incapable effect A101 được **reuse**, count giữ **2**.
- Capable callback chạy lại A101 → T102, count lên **4**.
- Static state tiếp tục 8 → 9.

**Không có bước nào tự đọc lại Target.class từ out hoặc replacement folder khi gọi retransform.** Chỉ redefine trước đó đã đưa replacement bytes vào VM.

### 7.6. Callback count matrix

| Giai đoạn | Incapable callbacks lũy kế | Capable callbacks lũy kế | Method result | Static state sau increment |
| --- | ---: | ---: | --- | ---: |
| Load gốc | 1 | 1 | T001 | 6 |
| Retransform | 1 | 2 | T002 | 7 |
| Redefine | 2 | 3 | T101 | 8 |
| Retransform sau redefine | 2 | 4 | T102 | 9 |

Thứ tự này được tạo **có chủ đích bằng một JVM duy nhất và Target đơn lẻ**. Một agent production xử lý hàng nghìn classes/threads không được sử dụng `capableCalls` toàn cục để suy stage hoặc tạo output; đây chỉ là fixture minh họa.

---

## 8. Classfile source và transformer lifecycle

### 8.1. “Initial bytes” không đảm bảo giống hệt bytes trên ổ đĩa

Javadoc retransform chỉ rõ initial classfile bytes có thể **khác về layout/constant pool ordering** so với byte[] ban đầu, dù ý nghĩa program tương ứng. Một số attributes có thể không tồn tại. Vì vậy:

- Không hash binary input trong transform rồi mặc định nó phải bằng bytes của file trên disk.
- Không dựa vào index constant pool cố định.
- Không dùng byte offsets hardcoded giữa các JDKs/biên dịch khác nhau.
- Không dùng `classfileBuffer` của lần transform như một permanent immutable original class snapshot.
- Cần parser/bytecode library phù hợp nếu muốn sửa arbitrary classes.

### 8.2. Re-entrant class loading và LinkageError

Transformer code chạy trong một bối cảnh nhạy cảm: JVM đang định nghĩa hoặc sửa class. Nếu trong callback bạn gọi code yêu cầu load lại chính class đang transform hoặc dependencies đan xen, có thể gặp `ClassCircularityError`/`LinkageError`.

**Best practice:**

- Filter nhanh theo className/loader/module trước khi làm việc.
- Tránh khởi tạo quá nhiều dependencies trong callback.
- Không gọi chính business code của class đang transform.
- Dùng logging tối thiểu, không gây recursive class loading.
- Preload agent dependencies cần thiết nếu thích hợp.
- Không transform core JDK classes trừ khi agent đã được review đầy đủ.
- Có fail-safe để bỏ qua classes không nằm trong scope.

### 8.3. Chỉ cần thay code, không phải thêm fields

Một profiler muốn thêm timing trước/sau method thường nên **biến đổi method bytecodes** nhưng không thêm field/cấu trúc mới vào class đã load. Khi đưa helper calls vào bytecode, cần tránh recursive instrumentation và bảo đảm helper class availability trên class loader/module paths.

Nếu transform cần thêm field để lưu trạng thái, HotSwap chuẩn có thể từ chối. Hãy dùng **external per-class/per-method registry** hoặc cấu trúc đã được chuẩn bị từ lúc class load ban đầu; vẫn phải kiểm thử memory/resource management.

### 8.4. Transformer được đăng ký nhiều lần

`addTransformer` cho phép về mặt API đăng ký cùng object nhiều lần nhưng **Javadoc không khuyến khích mạnh**. Nếu đăng ký trùng, cùng transform logic có thể bị áp dụng lặp, làm bytecode không hợp lệ hoặc tăng overhead.

Theo dõi lifecycle và **removeTransformer(transformer)** khi không còn cần. Tuy vậy, do concurrent class loading, có thể **callback vẫn đến sau remove**. Agent production phải idempotent và thread-safe trong shutdown.

### 8.5. RemoveTransformer không tự “undo” mọi class đã biến đổi

Xóa transformer ngăn các class definitions tương lai đi qua nó, nhưng **không lập tức khôi phục bytecode của những classes đã được biến đổi**. Muốn rollback những thay đổi đang có, cần phương án retransformation/redefinition đã thiết kế, tương thích các transformers đang đăng ký và có original/replacement bytes hợp lệ.

Đặc biệt, các **incapable transformations có thể đã được áp lên class**; việc đơn giản unregister không tương đương hoàn tác output đã install.

### 8.6. Multiple agents và xung đột

Trong cùng JVM, có thể có nhiều Java agents:

~~~bash
java -javaagent:tracing-agent.jar -javaagent:coverage-agent.jar -cp app Main
~~~

Các transformers được kết hợp theo nhóm/thứ tự, có thể biến đổi bytecode do agent trước tạo ra. Nếu hai agents cùng sửa method theo assumption khác nhau, output có thể phá `StackMapTable`, frames, exception tables hoặc semantics.

Không mặc định `"agent A chạy trước agent B"` theo CLI đồng nghĩa mọi transform luôn theo đúng một thứ tự giữa capability groups. Javadoc quy định **grouping by canRetransform** trước, rồi registration ordering trong từng nhóm.

---

## 9. Exceptions và giới hạn class format

### 9.1. Các lỗi cần phân biệt

| Exception/Error | Tình huống |
| --- | --- |
| `UnmodifiableClassException` | Một target class không thể sửa |
| `UnsupportedOperationException` | JVM config không hỗ trợ method hoặc thay đổi cấu trúc không được hỗ trợ |
| `ClassFormatError` | Bytes không tạo thành classfile hợp lệ |
| `NoClassDefFoundError` | Internal binary name trong replacement không khớp class |
| `UnsupportedClassVersionError` | Classfile version không được VM hỗ trợ |
| `ClassCircularityError` | Circularity trong class/linkage |
| `LinkageError` | Linkage failure khác |
| `NullPointerException` | Argument array hoặc phần tử bắt buộc là null |
| `ClassNotFoundException` | Có trong throws của redefine vì compatibility; Javadoc nói không thể ném từ method theo contract hiện hành |

**Không nên bắt và che toàn bộ `Throwable` ngoài cùng rồi nói “đã hot patch thành công”.** Nếu một transformation thất bại, report phải giữ nguyên target, operation, cause và trạng thái batch.

### 9.2. Transformer throws không bảo đảm operation thất bại

Javadoc ClassFileTransformer: nếu transform callback throw exception, các callbacks tiếp theo vẫn có thể được gọi và JVM vẫn **thử** thực hiện class load/redefine/retransform. Vì vậy một transformer không thể bảo đảm toàn bộ request abort chỉ bằng cách throw trong callback.

Nếu cần kiểm soát failure cứng, hãy validate classfile/replacement trước, có policy cho callback exceptions và kiểm tra kết quả sau operation.

### 9.3. Nhiều classes trong một request

~~~java
// MẢNH MINH HỌA:
inst.retransformClasses(ServiceA.class, ServiceB.class);
~~~

JVM cố cập nhật một set class definitions để hỗ trợ thay đổi liên quan nhiều classes. Nếu có class không modifiable hoặc một replacement không hợp lệ, theo API **không có class nào được thay**. Nhưng caller vẫn phải kiểm tra kết quả/exception; không rollback business state mà methods đã tác động trước đó.

### 9.4. Không thay arbitrary binary names

`ClassDefinition(Target.class, bytesForOtherClass)` là input không hợp lệ: classfile phải có **binary name đúng với target**. Nếu replacement có fields/methods mới hoặc version không hỗ trợ, JVM có thể từ chối.

Vì thế trong demo có **hai Target.java cùng tên**, compile output khác nhau, nhưng không đổi binary name hoặc schema.

---

## 10. Lựa chọn API trong thực tế

### 10.1. Dùng retransformClasses khi

- Agent đã có transformer capable và muốn **tái áp dụng instrumentation** trên classes đã được load.
- Cần bật/tắt logic logging/tracing/metrics **trong cách transformer sinh bytecode**, với thread safety và config rõ ràng.
- Đã có baseline classfile VM quản lý, không muốn caller tự cung cấp new classfile bytes.
- Muốn cùng transformer code phục vụ class load và retransform.
- Chấp nhận những giới hạn class schema và active frames.

Ví dụ: một metrics agent ban đầu không chèn probe trên một method; sau khi operator thay allowlist, nó retransform class để **chèn probe vào những invocation mới**.

### 10.2. Dùng redefineClasses khi

- Đã có **replacement `.class` bytes** từ một bản compile/build được kiểm chứng.
- Cần thay implementation method đã tồn tại mà không muốn tự tạo bytecode từ original transform pipeline.
- Một debugger/hot patch tool đã kiểm tra binary compatibility giữa các phiên bản.
- Muốn thao tác **trên một set classes** liên quan trong một call.
- Chấp nhận không chạy lại class initializer và không migrate state.

Ví dụ: một debugging tool compile lại body của `calculate()` nhưng giữ nguyên fields/method descriptors; JVM redefines class từ bytes mới.

### 10.3. Khi nào nên restart/redeploy thay vì HotSwap?

- Thay fields, methods, hierarchy, record components hoặc public contract lớn.
- Thay state invariants và cần migration.
- Cần bảo đảm toàn bộ active requests dùng behavior mới cùng lúc.
- Nhiều JVM instances cần rollout/rollback theo version.
- Bytecode verifier/module/class-loader compatibility khó bảo đảm.
- Changes có rủi ro cao hoặc không có test/observability đủ.
- Không có operator approval/agent trust controls.

Trong đa số hệ thống production, **rolling deployment có versioning và health checks** thường là lựa chọn bảo trì an toàn hơn thay vì cố dùng instrumentation để thay toàn bộ application.

### 10.4. So sánh với class loader reload

Một class loader mới có thể định nghĩa **một class cùng binary name nhưng Class identity khác**. Đây không phải `redefineClasses` của Class object cũ; các references, reflection, services và static state có thể thuộc class definitions khác nhau.

Chỉ thêm JAR mới vào classpath hoặc tạo ClassLoader mới **không tự cập nhật những references đã trỏ tới class cũ**. Nếu cần plugin hot reload, cần kiến trúc class loader và lifecycle riêng, không phải chỉ retransform.

---

## 11. Một số lưu ý hiện hành trong Java 17–26

### 11.1. Không mặc định dynamic attach luôn khả dụng

Package spec mới mô tả startup `-javaagent`, agent packaged cùng executable JAR và agent chạy trong JVM đang hoạt động. **Runtime agent loading là capability phụ thuộc implementation và security policy**. Với HotSpot hiện đại, dynamic loading có warnings và cơ chế opt-in liên quan `-XX:+EnableDynamicAgentLoading`; không nên chọn cách này nếu không có nhu cầu và quyền vận hành.

Demo dùng **startup agent** nên không yêu cầu dynamic attach, không cố bypass warnings/policy.

### 11.2. `java.instrument` là standard module

Khi dùng JPMS:

~~~java
// MẢNH MINH HỌA module-info.java cho app/module có import java.lang.instrument.
module demo.instrumentation {
    requires java.instrument;
}
~~~

Các source demo compile bằng classpath/unnamed module; không có `module-info.java` nên không cần cấu hình module descriptor. Nếu target thuộc named module và transformer cần truy cập helper classes, phải xét **exports/opens/reads/access** hợp lệ. HotSwap không tự bypass toàn bộ JPMS restrictions.

### 11.3. ClassFileTransformer 5-arg và 6-arg overload

Kể từ Java 9, có overload nhận **Module**. Để hoạt động với các callbacks hiện hành:

~~~java
new ClassFileTransformer() {
    @Override
    public byte[] transform(
            Module module,
            ClassLoader loader,
            String className,
            Class<?> classBeingRedefined,
            java.security.ProtectionDomain domain,
            byte[] bytes) {
        return null;
    }
};
~~~

Override overload 6-arg như ví dụ hoặc overload 5-arg theo delegation contract. Không dựa vào `ClassFileTransformer` như functional interface.

### 11.4. Lựa chọn thư viện bytecode

Trên Java 17+, các thư viện như ASM/Byte Buddy thường được dùng để quản lý classfile transforms. Khi chọn thư viện:

- Khớp phiên bản thư viện với **classfile major version** của JDK mục tiêu.
- Kiểm tra StackMapTable/frames, constant pool, method descriptors và module metadata.
- Có negative tests cho invalid class/redefinition restrictions.
- Tránh transform tất cả JDK classes nếu không cần.
- Đo overhead, GC allocations và throughput.
- Có rollback/troubleshooting workflow.

Không dùng replace substring trong byte[] ở production chỉ vì demo thành công cho một literal đã được kiểm soát.

### 11.5. Không ngầm đồng nhất `premain` với `agentmain`

`premain` chạy lúc startup nên có thể đăng ký transformer trước nhiều application classes. `agentmain` của runtime agent thường được gọi **sau khi một số classes đã được load**; nếu muốn tác động lên classes đã tồn tại, phải lựa chọn retransform/redefine theo capability và target modifiability.

Đây là lý do `retransformClasses` hữu ích cho dynamic instrumentation — nhưng bản thân class load transformation vẫn là bước trước đó khi agent đã có mặt.

---

## 12. Test strategy cho Java agent

### 12.1. Unit tests cho bytecode transformer

Test transformer nhận bytes hợp lệ của fixture, trả:

- `null` với class không nằm trong scope.
- `byte[]` mới khi match target.
- Input buffer **không bị sửa**.
- Output vẫn là valid classfile.
- Biến đổi chỉ thay điều được phép; không đổi schema.
- Gọi nhiều lần không tạo unintended cumulative effects.
- Có behavior hợp lý khi constant/token không tồn tại.
- Có behavior khi className null/loader null (bootstrap) nếu phạm vi bao gồm.
- Không recursive load/self-transform.
- Không giữ global state race-prone trong production.

**Một classfile parser** phù hợp sẽ làm các tests đáng tin hơn nhiều so với fixture replace bytes.

### 12.2. Integration test `-javaagent`

Kiểm tra:

1. Manifest agent có `Premain-Class`.
2. Hai Can-* attributes đúng.
3. JVM support flags được đọc, không hardcode.
4. Target class thực sự modifiable.
5. Transformer incapable + capable chạy lúc load.
6. Retransform không callback lại incapable nhưng callback lại capable.
7. Redefine dùng replacement `.class` bytes mới, callback cả hai groups.
8. Retransform sau redefine dùng baseline của lần redefine mới nhất.
9. Static state không reset, instance không tự tạo lại.
10. Active-frame behavior được kiểm tra trong sandbox riêng nếu relevant.
11. Không thay đổi class schema.
12. Không transform các classes ngoài allowlist.
13. Không làm JVM crash hoặc treo khi target class loader khác nhau.

Ví dụ runnable đã kiểm chứng các điểm 1–9 trong **một JVM test thực**; các tests còn lại nên bổ sung khi dùng trong sản phẩm.

### 12.3. Test class schema invalid

Trong một test JVM cô lập, có thể tạo replacement version:

~~~java
// MẢNH MINH HỌA thay đổi schema, KHÔNG đưa vào demo chính.
public final class Target {
    private static int state = 999;
    private static long newField = 1L; // Trái giới hạn HotSwap chuẩn.
    public static String message() { return "RDEF"; }
    public static int increment() { return ++state; }
}
~~~

Cố redefine với field mới có thể bị từ chối bằng UnsupportedOperationException hoặc lỗi tương ứng theo VM. **Không cần chạy negative test này trên production JVM.** Kiểm tra exception, batch atomicity và startup behavior trong test process riêng.

### 12.4. Test replacement sai binary name

~~~text
ClassDefinition(Target.class, bytesOfOtherName.class)
           │
           ▼
  NoClassDefFoundError hoặc lỗi classfile-name mismatch
~~~

Đây là trường hợp thuộc Javadoc. Dự án production nên validate binary name và classfile bytes trước khi gọi JVM. Một file tên Target.class trên filesystem **không đảm bảo nội dung bytes khai báo class Target**.

### 12.5. Test absence of capability

Có hai gates độc lập:

~~~java
// MẢNH MINH HỌA policy.
if (!inst.isRetransformClassesSupported()) {
    // Không gọi retransform.
}
if (!inst.isRedefineClassesSupported()) {
    // Không gọi redefine.
}
~~~

Nếu một capability unavailable, không có lý do để ép demo gọi method rồi mong exception có thể “bật” feature. Dùng một JVM/test configuration khác hoặc disable feature có kiểm soát.

### 12.6. Bytecode correctness và verifier

Test thêm:

- Lỗi classfile version mới hơn runtime.
- Invalid StackMapTable frames.
- Try/catch table được biến đổi không hợp lệ.
- Circularity ở referenced classes.
- Modules/exports/opens thiếu.
- Class loader duplicate names.
- Multiple agents transform cùng methods.
- Concurrent class loads/retransforms.
- Thread đang chạy method cũ trong lúc HotSwap.
- JIT deoptimization/performance sau redefinition.
- Failure rollback và restart fallback.
- Resource leaks từ transformer registrations/caches.

Không kết luận một transform an toàn chỉ vì `javac` compile agent thành công; **classfile output** phải được JVM verify và logic behavior phải đúng.

---

## 13. Production: rủi ro và biện pháp an toàn

### 13.1. Agent là thành phần đặc quyền

Agent có thể đọc/ghi class bytecode, thay logging hoặc security checks, vì thế cần:

- Binary provenance và artifact integrity.
- Code review và allowlist classes/methods mục tiêu.
- Signatures/checksums/controlled distribution theo chính sách tổ chức.
- Quyền triển khai/khởi động agent hạn chế.
- Không cho untrusted users upload agent JAR.
- Không tự động gắn agent vào JVM khác ngoài scope được phê duyệt.
- Audit ai yêu cầu, vì sao, lúc nào, version nào, class targets nào.
- Rollout canary/test JVM trước production.

Ngay cả khi mục đích là profiling, transformer lỗi có thể làm ứng dụng không khởi động hoặc chạy sai. Với agents tải lúc startup, `premain` ném uncaught exception có thể khiến JVM abort trước `main`.

### 13.2. Concurrency và consistent behavior

`ClassFileTransformer.transform` có thể được gọi song song do class loading/retransformation. Không dùng static mutable counter như demo để quyết định stage/behavior trong agent thực.

Khi có nhiều classes cần cập nhật, thực hiện theo batch hợp lý, tránh deadlocks trong callbacks, giữ cấu hình biến đổi thread-safe và xử lý active frames cũ.

### 13.3. Performance

Instrumentation có thể thêm CPU/allocations cho mỗi lời gọi method. Tính toán:

- Số methods được instrument.
- Hot path vs cold path.
- Độ sâu tracing và cardinality.
- Allocation overhead và GC.
- Latency tail (p95/p99).
- Cơ chế sampling, throttling.
- Rollback khi overhead vượt budget.

Đừng retransform toàn bộ lớp JDK hoặc toàn bộ loaded classes mỗi vài milliseconds. Cần exact target selection và vận hành có giới hạn.

### 13.4. Observation, error reporting và audit

Ghi dữ liệu đã hạn chế:

~~~text
event=instrumentation_retransform
targetClass=com.example.Target
classLoaderId=app-loader
agentVersion=1.2.0
capability=retransform
result=success
durationMs=...
correlationId=...
~~~

Đây là mẫu log minh họa, không phải output demo. Không log raw classfile bytes, secrets, token, customer data hoặc internal code tới public endpoint. Khi error, giữ cause ở internal diagnostics có kiểm soát.

### 13.5. Rollback không phải removeTransformer

Muốn rollback:

1. Xác định baseline classfile bytes **đúng với classloader/module/version**.
2. Biết transformers đang đăng ký và thứ tự, kể cả incapability group.
3. Chọn redefine/retransform phù hợp với mục đích rollback.
4. Xác minh output bytes được install và method behavior sau rollback.
5. Xử lý active frames cũ vẫn còn cho tới khi hoàn tất.
6. Nếu không thể bảo đảm consistency, restart/rolling redeploy.

**Không hứa bỏ agent JAR khỏi classpath hay gọi removeTransformer sẽ lập tức phục hồi mọi code đang chạy.**

### 13.6. Security policy của dynamic attach hiện đại

JDK 26 package specification nhấn mạnh dynamic agent loading là **implementation-specific** và có warnings; HotSpot có opt-in option liên quan `EnableDynamicAgentLoading`. Một tổ chức nên tôn trọng policy của JVM/process, không thử workaround để gắn agent trái phép. Với demo và nhiều ứng dụng hợp pháp, **startup `-javaagent`** dễ quản lý quyền và reproducibility hơn.

---

## 14. Lỗi thường gặp và cách khắc phục

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| Tưởng retransform đọc classfile mới từ disk | Không áp dụng patch như mong muốn | Dùng redefine với ClassDefinition bytes |
| Tưởng redefine dùng original bytes + transformer pipeline | Sai baseline | Redefine bắt đầu từ supplied replacement |
| Quên Can-Retransform-Classes manifest | Capability false | Khai báo và kiểm tra VM support |
| Quên Can-Redefine-Classes manifest | Redefine unavailable | Khai báo riêng |
| Gọi addTransformer(t,true) khi không hỗ trợ | UnsupportedOperationException | Check isRetransformClassesSupported |
| Tưởng isModifiableClass là đủ | Unsupported structural change | Check capability + bytes/schema |
| Coi canRetransform=false là không bao giờ callback lại | Sai với redefine | Nhớ redefine callback cả hai groups |
| Tưởng incapable transform chạy lại khi retransform | Count/behavior sai | JVM reuse prior output |
| Coi classBeingRedefined != null là chắc redefine | Nhầm với retransform | Không suy event type chỉ từ field |
| Xem ClassFileTransformer là functional interface | javac báo không abstract method | Anonymous class/implements |
| Sửa trực tiếp classfileBuffer | Vi phạm contract | Tạo byte[] copy |
| Transformer throws để “abort” | JVM vẫn thử load/transform | Validate/handle đúng boundary |
| Hardcode constant pool byte offsets | Sai trên JDK khác | Classfile parser/library |
| Đổi binary name trong ClassDefinition | Name mismatch | Compiled replacement cùng class name |
| Thêm field/method mới | HotSwap có thể bị từ chối | Giữ schema/redeploy |
| Đổi superclass/interfaces | Không hợp lệ | Redeploy |
| Mong static initializer chạy lại | State vẫn giữ | Explicit migration/restart |
| Mong static counters reset | Static values giữ nguyên | Lifecycle-aware state handling |
| Mong active frames dùng code mới ngay | Frames vẫn chạy old code | Thiết kế transition/rollout |
| Coi thread-safe vì test single-thread pass | Race ở agent production | Thread-safe transformer/config |
| Đăng ký transformer trùng | Transform bị áp dụng nhiều lần | Quản lý registration |
| removeTransformer = rollback | Code cũ vẫn installed | Re-transform/redefine/redeploy |
| Transform JDK core classes tùy ý | Circularity/LinkageError | Strict allowlist |
| Dùng nhiều agents mà bỏ qua grouping | Ordering sai | Theo spec incapable/capable groups |
| Chạy test JVM thiếu capability rồi coi là code bug | Optional VM feature | Conditional skip/fallback |
| Dynamic attach bỏ qua security warnings | Operational risk | Startup agent hoặc approved opt-in |
| Không kiểm tra classloader | Nhầm class cùng tên | Dùng đúng Class<?> target |
| Không kiểm tra runtime classfile version | UnsupportedClassVersionError | Build --release tương thích |
| Không kiểm tra callback output | Invalid code có thể install fail | Integration verification |
| Hot patch production không audit | Không trace thay đổi | Change control và logs |

---

## 15. Bài tập tự luyện

1. Chạy demo và giải thích toàn bộ 9 dòng stdout.
2. Vì sao callback incapable giữ 1 sau retransform nhưng tăng lên 2 sau redefine?
3. Đổi literal original BASE thành BASE2 mà không sửa transformer; dự đoán failure và kiểm chứng trong sandbox.
4. Đổi capable output T001/T002 thành một cặp token khác cùng độ dài; kiểm chứng method behavior.
5. Thử bỏ Can-Retransform-Classes khỏi manifest, quan sát capability và kiểm tra handler.
6. Thử bỏ Can-Redefine-Classes, quan sát independent capability.
7. Đọc isModifiableClass của String[].class và int.class, giải thích false.
8. Gọi retransformClasses với zero-length array, kiểm tra no-op.
9. Gọi redefineClasses với zero-length definitions, kiểm tra no-op.
10. Tạo một transformer thứ ba trong incapable group; kiểm tra thứ tự và reuse.
11. Tạo một transformer thứ ba trong capable group; kiểm tra callback order.
12. Thử override 5-arg transform thay vì 6-arg; giải thích default delegation.
13. Thử tạo lambda ClassFileTransformer trong Java 17 và đọc compile error; sửa bằng anonymous class.
14. Ghi classBeingRedefined == null ở initial load và != null sau thay đổi.
15. Tạo replacement classfile có binary name khác, kiểm tra lỗi trong test JVM riêng.
16. Tạo replacement thêm một field mới, quan sát structural restriction trên runtime đang thử.
17. Tạo replacement đổi signature của message(), quan sát unsupported change.
18. Thay method body nhưng giữ schema và dùng redefine.
19. Giải thích vì sao source replacement `state=999` không reset static state sau redefine.
20. Thêm field instance vào original Target và kiểm tra object state giữ nguyên qua retransform/redefine.
21. Dựng một active frame đang đợi CountDownLatch, thực hiện retransform, rồi so old/new invocation.
22. Tạo hai class A/B phụ thuộc nhau, thử batch redefinition hợp lệ.
23. Cho class B invalid trong batch, kiểm tra API báo failure không class nào được cập nhật.
24. Viết unit test transformer không mutate byte[] input.
25. Dùng classfile parser kiểm tra transformed classfile valid và bytecode version hợp lệ.
26. Tạo một module có module-info.java với requires java.instrument, build bằng JPMS.
27. Thử target class ở một ClassLoader khác và xác định đúng Class object.
28. Thử removeTransformer và lý giải vì sao code đã install không tự phục hồi.
29. Tạo hai agents và quan sát thứ tự transformers theo capability groups.
30. Thử attach agent bằng công cụ có quyền trong test VM, tôn trọng security/opt-in policy.
31. Đo overhead của instrumentation trên hot path trước/sau.
32. Viết audit event cho retransform/redefine với target, version và outcome.
33. Thiết kế rollback plan nếu một hot patch không hợp lệ.
34. Kiểm thử agent callback trong concurrent class loads; tránh global state như demo.
35. Viết checklist canary trước khi chạy instrumentation production.
36. Giải thích vì sao retransformClasses không phải classloader reload.
37. Lập ma trận JDK 17, JDK 21 và JDK 26 với optional capabilities của VM được triển khai.
38. Thiết kế retransform transformer deterministic chỉ dựa trên input bytes và cấu hình đã snapshot.
39. Xem ClassDefinition constructor không clone byte[] input; suy ra caller cần giữ buffer nhất quán đến khi dùng.
40. Viết tài liệu phân biệt classfile bytes baseline, transformer output và installed method version.

---

## 16. Checklist triển khai

- [ ] Agent JAR và Premain-Class đúng chuẩn.
- [ ] Agent provenance được xác minh, source review và quyền triển khai phù hợp.
- [ ] isRetransformClassesSupported kiểm tra trước retransform.
- [ ] isRedefineClassesSupported kiểm tra trước redefine.
- [ ] Can-Retransform-Classes và Can-Redefine-Classes khai báo đúng, độc lập.
- [ ] isModifiableClass kiểm tra cho từng target.
- [ ] Phân biệt `Class<?>` target với classfile bytes replacement.
- [ ] Không coi retransform là reload classfile từ disk.
- [ ] Không coi redefine là tự generate bytecode từ original.
- [ ] Transformer capable/incapable có lifecycle đúng.
- [ ] Biết thứ tự nhóm incapable trước capable.
- [ ] Incapable không callback retransform nhưng output cũ được reuse.
- [ ] Redefine callback cả hai nhóm transformers.
- [ ] Lần retransform sau redefine dùng baseline của lần redefine mới nhất.
- [ ] Không dùng lambda cho ClassFileTransformer trong Java17+.
- [ ] Transformer trả null hoặc byte[] mới; không mutate input.
- [ ] Bytecode transformation dùng parser/library đáng tin khi production.
- [ ] Không thêm/xóa/đổi tên fields/methods hoặc hierarchy trái restriction.
- [ ] Replacement classfile có cùng binary name và compatible version/schema.
- [ ] Không giả định static initializer chạy lại.
- [ ] Không giả định static/instance fields reset.
- [ ] Active stack frames và behavior chuyển tiếp được cân nhắc.
- [ ] Tests cho invalid schema, class versions, class loaders và classfile structure.
- [ ] Unit tests cho transformer output và ordering.
- [ ] Integration test thực bằng -javaagent và demo behavior.
- [ ] Thao tác đa class có failure handling, rollback/restart plan.
- [ ] Agent chỉ target allowlisted classes; hạn chế JDK core classes.
- [ ] Không recursive load trong callbacks, xử lý concurrent invocations.
- [ ] Không đăng ký cùng transformer nhiều lần vô ý.
- [ ] removeTransformer không được nhầm là undo bytecode đã install.
- [ ] Dynamic agent loading tuân thủ VM policy, không bypass security.
- [ ] Có change-control, audit, canary và quan sát overhead.
- [ ] Không log classfile bytes, token/secrets/PII.
- [ ] Khi schema/behavior changes quá lớn, dùng deploy/restart thay vì cố HotSwap.
- [ ] Build/test trên phiên bản Java đang dùng và các classfile versions cần hỗ trợ.

## Kết luận

**`retransformClasses` và `redefineClasses` đều có thể thay đổi code của class đã được nạp, nhưng chúng không đồng nghĩa.** Retransform yêu cầu JVM chạy lại **retransformation-capable transformers** từ baseline bytes (và reuse output của incapable transformers), trong khi redefine nhận **replacement classfile bytes** trực tiếp từ caller và gọi lại các transformers theo pipeline.

Điểm quan trọng hơn cả là **không có cách nào tự do đổi class schema, reset static state hay buộc active method frames ngay lập tức dùng code mới** chỉ bằng các APIs này. Capability checks, manifest flags, class modifiability, binary compatibility, bytecode validation và agent security là các điều kiện bắt buộc để vận hành an toàn.

Ví dụ Java 17+ đã kiểm chứng đúng bằng một startup agent, hai transformers và bốn giai đoạn: **T001 → T002 → T101 → T102**, callback counts **1/1 → 1/2 → 2/3 → 2/4**, static state **6 → 7 → 8 → 9**. Đó là chứng cứ thực nghiệm rõ ràng cho sự khác biệt giữa retransform và redefine theo Javadoc hiện hành.

**Tài liệu tham khảo chính thức (API hiện hành):**

- [Instrumentation — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.instrument/java/lang/instrument/Instrumentation.html)
- [Instrumentation — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html)
- [ClassFileTransformer — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html)
- [ClassFileTransformer — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html)
- [ClassDefinition — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.instrument/java/lang/instrument/ClassDefinition.html)
- [UnmodifiableClassException — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.instrument/java/lang/instrument/UnmodifiableClassException.html)
- [java.lang.instrument package specification / Java agents — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.instrument/java/lang/instrument/package-summary.html)
- [JVM TI specification — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/jvmti.html)
- [Java Virtual Machine Specification — Class File Format, Java SE 26](https://docs.oracle.com/javase/specs/jvms/se26/html/jvms-4.html)
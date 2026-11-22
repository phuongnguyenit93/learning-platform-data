# Constant pool, thứ tự phương thức và thuộc tính có thể khác bản byte đã lưu

**Ngữ cảnh:** Java Advance → instrumentation → **Retransformation**.

Khi gọi `Instrumentation.retransformClasses(...)`, JVM có thể cung cấp cho `ClassFileTransformer` một biểu diễn class file **khác từng byte** với tệp `.class` từng được biên dịch, lưu vào JAR hoặc ghi lại ở lần load trước. Khác biệt có thể nằm ở **constant pool**, **thứ tự khai báo methods** hoặc **sự hiện diện của một số attributes**. Đây không mặc nhiên là lỗi, không nhất thiết có nghĩa method đã bị sửa về ngữ nghĩa, và không phải bằng chứng agent bị chạy lặp.

Tài liệu chính thức của `Instrumentation.retransformClasses` nêu rõ: *initial class file bytes* đại diện cho bytes trước các transformers tại lần `defineClass` hoặc `redefineClasses` gần nhất, **nhưng không nhất thiết trùng khít với byte array lúc đầu**. Constant pool có thể khác bố cục/số lượng/thứ tự entry; một số attributes có thể không có; và thứ tự methods, nơi thứ tự không có ý nghĩa, có thể không được giữ nguyên. Các chỉ số constant pool dùng bởi bytecode vẫn phải tham chiếu phù hợp với pool của bản class tương ứng.

Mục tiêu bài này là biết **tại sao có chênh lệch**, **thứ gì phải giữ hợp lệ**, **đọc đúng pipeline retransform**, và **so sánh đúng cấp độ (bytes → cấu trúc → ngữ nghĩa → hành vi)**.

> **Yêu cầu lab:** JDK 17+ với HotSpot hỗ trợ retransformation. Ví dụ chính dùng **agent khởi động bằng `-javaagent`**, không dùng dynamic attach; do đó có thể quan sát `ClassFileTransformer` mà không phụ thuộc quy trình self-attach hay quyền attach vào JVM khác.

## 1. Phân biệt bốn loại “bản class”

Cùng tên `demo/Target` nhưng có nhiều dạng bytes theo thời điểm:

| Nhãn | Bản class | Thu được ở đâu? | Có chắc trùng bản khác? |
| --- | --- | --- | --- |
| **D — disk** | `.class` biên dịch hoặc entry trong JAR | `Files.readAllBytes`, `jar`, `javap -classpath ...` | Không |
| **L — initial load input** | `classfileBuffer` của transformer được gọi khi load/define | Bắt trong callback với `classBeingRedefined == null` | Có thể là bytes D hoặc output transformer đứng trước |
| **R — retransformation input** | `classfileBuffer` khi JVM chạy `retransformClasses` | Bắt trong callback với `classBeingRedefined != null` | Không bảo đảm giống D hoặc L |
| **T — transformer output** | Mảng mới một transformer trả về | Bắt tại `return transformedBytes` / lưu snapshot riêng | Phụ thuộc thuật toán transform và các bước đứng trước |

Ngoài ra còn **định nghĩa class đang được JVM thực thi** sau khi pipeline hoàn thành. Không nên suy ra rằng VM đang giữ nguyên một bản copy từng byte của tệp D trong heap; **`javap` trên disk chỉ đọc D**, không tự đọc T hoặc mã đã cài trong JVM.

Với một agent quan sát trả `null`, output của agent *được hiểu là không thay đổi input* trong lần callback đó. Nhưng R vẫn có thể khác L vì JVM đã tái tạo bytes nền, hoặc vì transformer khác trong pipeline, hoặc vì có redefinition giữa các lần quan sát.

### 1.1. Các từ khóa phải dùng chính xác

- **`retransformClasses(Class<?>...)`**: yêu cầu JVM chạy lại quá trình chuyển đổi cho các lớp đã load, trong phạm vi capability VM hỗ trợ.
- **`redefineClasses(ClassDefinition...)`**: chủ động cung cấp bộ class file **mới** để thay định nghĩa hiện tại; không phải thao tác giống `retransformClasses`.
- **`classfileBuffer`**: bytes **đầu vào của chính callback hiện tại**; có thể đã chứa kết quả của transformer đứng trước.
- **`canRetransform=false`**: transformer nhận callback khi load/redefine nhưng **không gọi lại** khi retransform; tác động đã tạo trước đó được tái áp dụng theo đặc tả.
- **`canRetransform=true`**: transformer được gọi trong lượt retransformation (và các sự kiện load/redefine tương ứng).
- **Binary equality**: hai mảng có các byte giống hệt và cùng độ dài.
- **Structural/semantic equivalence**: nội dung lớp tương đương theo tiêu chí đã định, có thể **không binary-equal**.

Không có một phép `Arrays.equals(before, after)` nào tự giải thích khác biệt bắt nguồn từ đâu.

## 2. Hợp đồng JVM về sự khác biệt của bytes ban đầu

Javadoc `java.lang.instrument.Instrumentation` tại `retransformClasses` mô tả các khả năng:

1. **Constant pool layout/content khác:** số entries có thể nhiều/ít hơn và thứ tự có thể thay đổi.
2. **Chỉ số trong bytecode vẫn nhất quán:** các operand của `ldc`, `getfield`, `invokevirtual`, `invokestatic` ... phải trỏ tới **entry đúng trong constant pool của chính bản class đó**.
3. **Một số attributes có thể vắng mặt:** không được giả định mọi attribute từ class gốc còn hiện diện khi JVM cung cấp lại bytes.
4. **Thứ tự methods có thể đổi:** thứ tự khai báo methods vốn không phải khóa định danh phương thức theo class-file semantics.
5. **Không phải lúc nào cũng khác:** đặc tả nói **có thể** khác, không tuyên bố mọi lần retransform đều chắc chắn đảo pool, xóa attribute hay sắp xếp lại method.

Như vậy, hai trường hợp sau **đều phù hợp** với hợp đồng, nếu mọi ràng buộc khác được đáp ứng:

```text
Case A: D == L == R                  [byte-for-byte equal]
Case B: D != R, nhưng cấu trúc/hành vi tương ứng vẫn đúng
```

Kết luận an toàn là **“byte identity không được bảo đảm”**, không phải “JVM chắc chắn viết lại constant pool trong mỗi lượt”.

### 2.1. Ranh giới của sự khác nhau

JVM được phép khác ở những phần không làm mất tính hợp lệ của class representation; điều đó **không** có nghĩa có thể bỏ qua kiểm tra định dạng hay ngữ nghĩa. `classfileBuffer` nhận được phải được hiểu theo **JVMS ClassFile format**, trong đó mỗi field/method/attribute có cấu trúc rõ ràng. Các reference constant pool phải hợp lệ; instructions cần tương thích descriptor/stack; class file cuối pipeline phải vượt qua validation trước khi được cài.

Đối với một biến đổi thực sự, JVM còn áp đặt các **giới hạn retransformation**: không thể tùy tiện thêm/xóa/đổi tên fields hoặc methods, đổi inheritance hay signatures nếu capability hiện tại không hỗ trợ. Lỗi như `UnsupportedOperationException`, `UnmodifiableClassException` hoặc validation error cần được phân tích riêng, không quy tất cả về “pool bị đảo”.

## 3. Vì sao constant pool có thể khác mà opcode vẫn có cùng ý nghĩa?

Trong class file, **constant pool** là bảng lưu chuỗi UTF-8, tên classes, names/types, references đến fields/methods, hằng số nguyên/chuỗi, method handles, bootstrap-linked entries và các kiểu `CONSTANT_*` khác. Nhiều bytecode instruction trỏ vào bảng này bằng **chỉ số số học**.

Giả sử trong một bản class file, câu lệnh Java:

```java
System.out.println("hello");
```

được mô hình hóa qua các symbol sau:

```text
GETSTATIC  java/lang/System.out:Ljava/io/PrintStream;
LDC        "hello"
INVOKEVIRTUAL java/io/PrintStream.println:(Ljava/lang/String;)V
```

Ở bytes thực, những instruction như `getstatic` và `invokevirtual` mang **constant-pool index**. Một cách minh họa:

```text
Snapshot A
  #7  = Fieldref java/lang/System.out:Ljava/io/PrintStream;
  #11 = String "hello"
  #17 = Methodref java/io/PrintStream.println:(Ljava/lang/String;)V

  getstatic #7
  ldc #11
  invokevirtual #17

Snapshot B (minh họa một bố cục khác, KHÔNG phải output javap thật)
  #21 = Fieldref java/lang/System.out:Ljava/io/PrintStream;
  #9  = String "hello"
  #33 = Methodref java/io/PrintStream.println:(Ljava/lang/String;)V

  getstatic #21
  ldc #9
  invokevirtual #33
```

Cả hai có thể gọi **đúng cùng target symbol**. Điều quan trọng là `#17` của snapshot A **và `#33` của snapshot B** giải ra cùng owner/name/descriptor; không phải các số `#n` bằng nhau.

### 3.1. Những hệ quả khi pool layout thay đổi

- **Raw bytes khác:** `constant_pool_count`, thứ tự entry và các operand index có thể khác, nên SHA-256 có thể khác dù method logic vẫn tương đương.
- **Instruction size có thể khác:** `ldc` dùng operand `u1`, còn `ldc_w` dùng `u2` cho chỉ số lớn; một writer có thể chọn biến thể phù hợp. Khi kích thước mã đổi, branch offsets và metadata liên quan cũng phải hợp lệ.
- **Có entries không được dùng:** sự tồn tại một entry thêm trong pool không tự chứng minh một lệnh mới đã được chèn.
- **`long`/`double` chiếm hai slot:** số index không bằng số entries hữu ích; index 0 không phải một entry thông thường.
- **`invokedynamic`, `condy`, bootstrap metadata:** cần so symbol/arguments và bootstrap methods liên quan, không chỉ text `#n`.

**Cẩn thận:** một constant pool reference thực sự chuyển từ `Math.abs(I)I` sang `Math.max(II)I`, từ field cũ sang field khác hoặc từ chuỗi `"hello"` sang `"goodbye"` **là thay đổi ý nghĩa**. Không dùng “pool có thể đảo” như lý do bỏ qua mọi chênh lệch.

### 3.2. Những gì phải giữ nhất quán trong từng bản

Trong một snapshot riêng, `getstatic #k` cần trỏ tới loại entry phù hợp, `invoke* #m` phải trỏ tới method reference đúng kiểu, field/method descriptors phải hợp lệ và `ldc` phải dùng hằng hợp lệ. Khi các chỉ số pool được thay, writer có trách nhiệm cập nhật **toàn bộ references trong class file**, không chỉ các opcode thấy bằng mắt.

Vì vậy, **tuyệt đối không tự sắp xếp lại constant pool bằng `Arrays.sort(...)` trên một vùng byte**: format là các cấu trúc biến độ dài, số index nằm ở nhiều nơi, có entries chiếm hai slots và metadata phụ thuộc chéo. Dùng parser/writer class file phù hợp như ASM hoặc JDK Class-File API (JDK 24+).

## 4. Thứ tự phương thức có thể thay đổi

Theo JVMS, một `method_info` gắn với **tên và method descriptor**. Không thể có hai methods có cùng cặp **name + descriptor** trong cùng class file; nhưng JVM không cần coi **vị trí thứ N trong `methods[]`** là định danh của một method.

Ví dụ một snapshot có:

```text
methods[] của Snapshot A
  0. <init>()V
  1. alpha(I)I
  2. beta(Ljava/lang/String;)V
```

Một snapshot khác có thể dùng thứ tự:

```text
methods[] của Snapshot B
  0. beta(Ljava/lang/String;)V
  1. <init>()V
  2. alpha(I)I
```

Nếu mỗi method vẫn có đúng name/descriptor/flags/code/metadata phù hợp, phép so **dựa vào index** sẽ báo hàng loạt “method bị thay”, dù thực ra chỉ **thứ tự các `method_info`** khác.

### 4.1. Khóa so sánh đúng

Trong một class, khóa cơ bản của một method là:

```text
classInternalName + definingLoaderIdentity (khi so runtime class)
+ methodName + methodDescriptor
```

Ví dụ:

```text
demo/Service#save(Ljava/lang/String;)V
demo/Service#save(I)V
demo/Service#<init>()V
```

Hai overload `save` có cùng **name** nhưng khác **descriptor**. Còn khi cùng binary name có thể được **hai class loaders** định nghĩa, nên logging/caching ở runtime còn phải ghi nhận **loader/module identity** theo ngữ cảnh.

**Không** sắp xếp lại **thứ tự lệnh trong method Code** để “chuẩn hóa”. Thứ tự các instruction, branch, handlers, monitor operations và side effects **có ý nghĩa**. Chỉ những danh sách mà thứ tự được xác định không có ý nghĩa theo spec mới có thể được so như tập hợp/map.

## 5. “Một số thuộc tính có thể không có” phải hiểu thế nào?

Class-file **attributes** xuất hiện ở mức class, field, method hoặc `Code`. Ví dụ:

| Attribute | Vị trí thường gặp | Có thể dùng để làm gì? | Có được bỏ qua khi QA không? |
| --- | --- | --- | --- |
| `SourceFile` | Class | Tên tệp nguồn phục vụ chẩn đoán | Có thể khác/thiếu trong một số snapshot; cần ghi chú |
| `LineNumberTable` | Code | Mapping bytecode ↔ dòng source | Thiếu có thể ảnh hưởng stack trace/debug |
| `LocalVariableTable` | Code | Tên và phạm vi local debug | Thường là debug metadata; thiếu không tự đổi tính toán |
| `LocalVariableTypeTable` | Code | Generic type debug info | Có thể ảnh hưởng trải nghiệm debugger |
| `Signature` | Class/field/method | Generic signatures | **Có thể ảnh hưởng reflection generic metadata** |
| `RuntimeVisibleAnnotations` | Class/field/method... | Annotations thấy ở runtime | Không thể tự động bỏ qua |
| `Exceptions` | Method | Declared checked exceptions metadata | Có thể ảnh hưởng reflection/tooling |
| `Code` | Method không abstract/native | Bytecode và exception table | Thiếu/sai tại method có body là nghiêm trọng |
| `StackMapTable` | Code | Verification type frames | Sai có thể gây `VerifyError` |
| `Record`, `NestHost`, `NestMembers`, `PermittedSubclasses` | Class | Record/nest/sealed semantics | Cần so theo ngữ nghĩa tương ứng |
| `BootstrapMethods` | Class | Bootstrap information cho dynamic linkage | Tham chiếu sai làm hỏng `invokedynamic`/`condy` |

Javadoc về retransformation **không bảo đảm một danh sách cố định các attribute sẽ bị lược**. Vì vậy không tuyên bố “retransform luôn xóa `LineNumberTable`” hay “JVM chắc chắn giữ mọi annotation”. Trường hợp cụ thể cần xem **bản byte thực nhận được** và tài liệu JVM đang chạy.

Một attribute “không bắt buộc theo cú pháp class file” cũng **không đồng nghĩa an toàn để bỏ** trong mọi ứng dụng. Nhiều frameworks đọc annotations, generic signatures, records hoặc module metadata. Hãy đặt chính sách so sánh rõ ràng:

- **Debug-oriented comparison:** cho phép khác về `SourceFile`, line/local tables nếu mục tiêu chỉ là semantics thực thi và việc mất debug info được chấp nhận.
- **Reflection/API compatibility:** so `Signature`, annotations, method parameters, exceptions, records, nest/permits/module metadata theo nhu cầu.
- **Verifier/runtime correctness:** bắt buộc đảm bảo `Code`, `StackMapTable`, handlers, type relationships và class-file validity đúng.
- **Reproducible build/forensics:** đòi hỏi giữ nguyên các bytes hoặc metadata khi thật sự là một yêu cầu; không dùng retransform snapshot làm “bằng chứng” về byte identity với artifact phát hành.

## 6. Pipeline retransformation: hiểu bước nào đang tạo bytes

`Instrumentation.retransformClasses(Target.class)` không có nghĩa gọi tất cả transformers lại giống hệt lúc class được load. Javadoc định nghĩa quy trình:

```text
Class ban đầu: bytes từ defineClass hoặc redefineClasses (logical initial)
     │
     │  JVM có thể tái biểu diễn bytes hợp lệ
     ▼
[T0]  non-retransform-capable transformers:
      KHÔNG gọi lại; kết quả trước được tự động tái áp dụng
     ▼
[T1]  retransform-capable transformers:
      callback transform(...) được GỌI LẠI theo thứ tự nhóm
     ▼
[T2]  bytecode definitions sau transform
     ▼
VM kiểm tra, xác minh và cài định nghĩa lớp mới
```

Trong thực tế còn có **native transformers** (JVMTI `ClassFileLoadHook`) theo nhóm thứ tự API quy định:

1. Java transformer không hỗ trợ retransformation.
2. Native transformer không hỗ trợ retransformation.
3. Java transformer hỗ trợ retransformation.
4. Native transformer hỗ trợ retransformation.

Trong mỗi nhóm, thứ tự đăng ký vẫn được giữ. Với nhóm không hỗ trợ retransformation, VM **tái áp dụng kết quả cũ** mà **không gọi lại** callback đó. Vì vậy R mà một transformer `canRetransform=true` nhận có thể đã bao gồm kết quả của các transformer trước.

### 6.1. Hai ngộ nhận nguy hiểm

**Ngộ nhận A: “Lượt sau bắt đầu bằng output của chính transformer ở lượt trước.”**  
Không được giả định. Retransformation bắt đầu từ *initial class file bytes* theo mô hình API, tái áp dụng kết quả transformer không hỗ trợ retransform và gọi lại các transformer có hỗ trợ. Nếu mã bạn chèn ở lượt trước thuộc transformer `canRetransform=true`, lượt sau không nhất thiết đã có chúng trong buffer đầu vào.

**Ngộ nhận B: “Vì R khác D nên có agent lạ đã instrument.”**  
Không đúng. Chính đặc tả cho phép R không byte-identical với D. Cần xem cấu trúc, semantic method bodies, chain of transformers và output cuối, thay vì suy diễn chỉ từ hash.

### 6.2. Quan hệ với redefinition và runtime state

- `redefineClasses` đưa bộ bytes mới vào VM theo yêu cầu; về sau *initial* cho retransformation có thể dựa trên **lần redefine gần nhất**, không phải file JAR ban đầu.
- `retransformClasses` không chạy lại static initializers và không tự reset static fields; các đối tượng đã tạo vẫn tồn tại.
- Nếu một method đang có **active stack frames**, frames đó tiếp tục chạy bytecode định nghĩa cũ theo quy định; **các lời gọi mới** sử dụng định nghĩa mới.
- Retransformation là capability có thể không tồn tại trong mọi VM/configuration. `Instrumentation.isRetransformClassesSupported()`, manifest `Can-Retransform-Classes: true` và `isModifiableClass(target)` đều cần kiểm tra.

Nội dung khác byte của một snapshot **không cho biết trực tiếp** frame đang thực thi version nào ở một thời điểm cụ thể.

## 7. Lab đầy đủ Java 17+: bắt snapshots trong lúc load và retransform

Mục đích lab là **quan sát đúng hai thời điểm** và **lưu snapshots độc lập**, không cố ép JVM phải đổi constant pool. Observer không biến đổi bytecode: nó chỉ clone buffer, ghi nhận callback và **`return null`**. Trên một số VM cả hai snapshots có thể binary-equal; trên VM khác có thể khác. **Cả hai đều đúng** và đây là bài học cốt lõi.

### 7.1. Cấu trúc dự án

Tạo thư mục `retransform-snapshots`:

```text
retransform-snapshots/
├── agent.mf
└── src/
    └── demo/
        ├── Target.java
        ├── ObserverAgent.java
        ├── AppMain.java
        └── CompareSnapshots.java
```

Khi biên dịch sẽ có `out/demo/*.class` và JAR agent. Runtime tạo hai file dưới `snapshots/load/demo/Target.class` và `snapshots/retransform/demo/Target.class`. Không đụng vào `out/demo/Target.class`.

### 7.2. `src/demo/Target.java`

```java
package demo;

public final class Target {
    private Target() {}

    public static String message() {
        return "hello";
    }
}
```

### 7.3. `src/demo/ObserverAgent.java`

```java
package demo;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.ProtectionDomain;

public final class ObserverAgent {
    private static volatile Instrumentation instrumentation;
    private static volatile byte[] loadBytes;
    private static volatile byte[] retransformedBytes;

    private ObserverAgent() {}

    public static void premain(String arguments, Instrumentation inst) {
        instrumentation = inst;

        if (!inst.isRetransformClassesSupported()) {
            throw new IllegalStateException(
                    "This VM does not support retransformation");
        }

        inst.addTransformer(new Observer(), true);
    }

    private static final class Observer implements ClassFileTransformer {
        @Override
        public byte[] transform(
                Module module,
                ClassLoader loader,
                String className,
                Class<?> classBeingRedefined,
                ProtectionDomain protectionDomain,
                byte[] classfileBuffer) {

            if (!"demo/Target".equals(className)) {
                return null;
            }

            if (classBeingRedefined == null) {
                loadBytes = classfileBuffer.clone();
                System.out.println("OBSERVED=load");
            } else {
                retransformedBytes = classfileBuffer.clone();
                System.out.println("OBSERVED=retransform");
            }

            // Observer không hề sửa classfileBuffer.
            return null;
        }
    }

    public static void retransformAndSave(Class<?> target)
            throws Exception {
        Instrumentation inst = instrumentation;
        if (inst == null) {
            throw new IllegalStateException("Start with -javaagent");
        }
        if (!inst.isModifiableClass(target)) {
            throw new IllegalStateException("Target cannot be modified");
        }

        inst.retransformClasses(target);

        byte[] load = loadBytes;
        byte[] again = retransformedBytes;
        if (load == null || again == null) {
            throw new IllegalStateException("Missing callback snapshot");
        }

        Path first = Path.of(
                "snapshots", "load", "demo", "Target.class");
        Path second = Path.of(
                "snapshots", "retransform", "demo", "Target.class");

        Files.createDirectories(first.getParent());
        Files.createDirectories(second.getParent());
        Files.write(first, load);
        Files.write(second, again);
        System.out.println("SNAPSHOTS=2");
    }
}
```

**Vì sao code này đáp ứng hợp đồng?**

- `premain` đăng ký một transformer **`canRetransform=true`** trước khi `AppMain` gọi `Target.message()`.
- Filter chính xác `demo/Target` bằng **internal class name**. Không instrument mọi lớp JDK hoặc class của agent.
- `classBeingRedefined == null` trong callback đầu khi load; ở lần retransform của `Target`, giá trị này không `null`.
- `clone()` tạo snapshots riêng; không giữ reference tới `classfileBuffer` và tuyệt đối không ghi vào buffer JVM cấp.
- `return null` có nghĩa observer không yêu cầu thay đổi class.
- Dùng `volatile` giúp publish snapshot khi callback và code chạy ở các thread khác nhau; lab vẫn cố ý chỉ có một lần load và một lần retransform.
- I/O ghi snapshots thực hiện **sau callback**, không ghi file trong đường tải class nóng. Khi dùng agent production, cần tránh giữ mọi class bytes vô hạn và phải có chính sách riêng cho nhiều loader/lần retransform.

### 7.4. `src/demo/AppMain.java`

```java
package demo;

public final class AppMain {
    private AppMain() {}

    public static void main(String[] args) throws Exception {
        System.out.println("BEFORE=" + Target.message());
        ObserverAgent.retransformAndSave(Target.class);
        System.out.println("AFTER=" + Target.message());
    }
}
```

### 7.5. `agent.mf`

Tạo file text **`agent.mf`**, mỗi entry một dòng và **có newline kết thúc file**:

```text
Manifest-Version: 1.0
Premain-Class: demo.ObserverAgent
Can-Retransform-Classes: true
```

`Premain-Class` xác định entrypoint cho `-javaagent`. `Can-Retransform-Classes: true` là yêu cầu capability của agent; nó không bảo đảm mọi JVM đều hỗ trợ, do đó code vẫn kiểm tra `isRetransformClassesSupported()`.

### 7.6. Lệnh biên dịch và chạy

Trên JDK 17+ tại thư mục `retransform-snapshots`, chạy:

```bash
javac -d out src/demo/Target.java src/demo/ObserverAgent.java src/demo/AppMain.java
jar --create --file observer-agent.jar --manifest agent.mf -C out .
java -javaagent:observer-agent.jar -cp out demo.AppMain
```

Ba lệnh `javac`/`jar`/`java` dùng syntax chuẩn JDK. Thư mục `out` được tạo bởi `javac -d` khi cần. Trên môi trường HotSpot/JDK hỗ trợ retransform và target modifiable, stdout **xác định từ demo**:

```text
OBSERVED=load
BEFORE=hello
OBSERVED=retransform
SNAPSHOTS=2
AFTER=hello
```

Đây là stdout ứng dụng/agent của ví dụ trên, không tính các dòng ngoài do shell/tool có thể thêm. Trong lab này, cả trước và sau retransform đều trả `hello` vì transformer **không thay bytecode**. Nếu VM không hỗ trợ capability, khởi động agent sẽ dừng với lỗi nêu rõ ở `premain`; đó là điều kiện môi trường, không phải output thành công.

**Không có dòng `BYTES_EQUAL=true` cố định** trong output vì **tính bằng nhau của hai snapshots không được đặc tả bảo đảm**. Chúng ta sẽ dùng chương trình comparator riêng để xem kết quả thực tế thay vì bịa ra một giá trị cho mọi máy.

### 7.7. Đọc ba snapshots: disk, load, retransform

Sau khi chạy, có ba đối tượng so sánh:

```text
out/demo/Target.class
snapshots/load/demo/Target.class
snapshots/retransform/demo/Target.class
```

Dùng `javap`:

```bash
javap -classpath out -p -s -c -v demo.Target
javap -classpath snapshots/load -p -s -c -v demo.Target
javap -classpath snapshots/retransform -p -s -c -v demo.Target
```

Để tạo bản dump văn bản phục vụ diff:

```bash
javap -classpath out -p -s -c -v demo.Target > disk.javap.txt
javap -classpath snapshots/load -p -s -c -v demo.Target > load.javap.txt
javap -classpath snapshots/retransform -p -s -c -v demo.Target > retransform.javap.txt
```

`javap` chỉ đọc class file trên đường bạn đưa. Output của `-v` gồm header, CP indexes, method listings, attributes; raw textual diff có thể rất dài và chứa những khác biệt không phải bug. Trên Windows PowerShell có thể dùng:

```powershell
Compare-Object (Get-Content load.javap.txt) (Get-Content retransform.javap.txt)
```

Trên Linux/macOS:

```bash
diff -u load.javap.txt retransform.javap.txt
```

Nếu output không khác, **đừng ép thử nghiệm tạo ra khác biệt bằng cách sửa classfileBuffer**. Mục đích chính của lab là quan sát rằng hợp đồng JVM **cho phép khác**, chứ không hứa mọi VM phải tạo khác.

### 7.8. Comparator Java 17+ để thấy kết quả thật (không suy đoán)

Tạo **`src/demo/CompareSnapshots.java`**:

```java
package demo;

import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.Arrays;
import java.util.HexFormat;

public final class CompareSnapshots {
    private CompareSnapshots() {}

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "Usage: CompareSnapshots <file-a> <file-b>");
        }

        byte[] left = Files.readAllBytes(Path.of(args[0]));
        byte[] right = Files.readAllBytes(Path.of(args[1]));

        MessageDigest sha = MessageDigest.getInstance("SHA-256");
        System.out.println("BYTE_EQUAL=" + Arrays.equals(left, right));
        System.out.println("LEFT_SHA256="
                + HexFormat.of().formatHex(sha.digest(left)));
        System.out.println("RIGHT_SHA256="
                + HexFormat.of().formatHex(sha.digest(right)));
    }
}
```

Biên dịch/run:

```bash
javac -d out src/demo/CompareSnapshots.java
java -cp out demo.CompareSnapshots snapshots/load/demo/Target.class snapshots/retransform/demo/Target.class
```

Ví dụ các khóa sẽ xuất hiện trong stdout:

```text
BYTE_EQUAL=<true hoặc false theo JVM thực tế>
LEFT_SHA256=<64 ký tự hex của file thứ nhất>
RIGHT_SHA256=<64 ký tự hex của file thứ hai>
```

**Đây là mẫu định dạng output, không phải stdout cố định.** Chương trình tính dữ liệu thật ở runtime; hash ở hai dòng cuối không thể biết trước từ đề bài. Với `BYTE_EQUAL=false`, xem `javap` và so cấu trúc, không kết luận app đã bị biến đổi về ngữ nghĩa. Với `BYTE_EQUAL=true`, đừng kết luận JVM bắt buộc giữ identity cho các lần sau hoặc class khác.

## 8. Bài thực hành bổ trợ: tự tạo hai class file khác bytes nhưng cùng behavior

Để quan sát **một cách có kiểm soát** hiện tượng class files khác bytes, có thể biên dịch cùng một class với hai cấu hình debug metadata khác nhau. Đây là **thử nghiệm javac**, **không phải bằng chứng JVM đã làm điều đó khi retransform**.

Lưu **`DebugSample.java`**:

```java
public final class DebugSample {
    public static int doubleOf(int value) {
        int result = value * 2;
        return result;
    }

    public static void main(String[] args) {
        System.out.println(doubleOf(4));
    }
}
```

Trên máy có JDK 17+ (tạo hai thư mục output theo ý muốn, `javac -d` yêu cầu thư mục đích đã tồn tại trên một số môi trường):

```bash
mkdir with-debug
mkdir no-debug
javac -g -d with-debug DebugSample.java
javac -g:none -d no-debug DebugSample.java
java -cp with-debug DebugSample
java -cp no-debug DebugSample
javap -classpath with-debug -p -c -v DebugSample > with-debug.txt
javap -classpath no-debug -p -c -v DebugSample > no-debug.txt
```

Hai lần chạy `java` đều in **chính xác**:

```text
8
```

Nhưng file `with-debug/DebugSample.class` và `no-debug/DebugSample.class` thường khác về các debug attributes như `LineNumberTable`, `LocalVariableTable` hoặc `SourceFile` theo options `javac`. `javac -g` yêu cầu debug info đầy đủ; `-g:none` không phát debug info. Dùng `javap -v` để xác nhận tên attribute thật sự có/không có; không suy từ hash ra loại attribute thay đổi.

Thí nghiệm này minh họa rõ: **hai class file có behavior giống nhau vẫn có thể không binary-identical**. Nó không chứng minh mọi attribute có thể bị xóa trong retransformation, và không thể thay thế kiểm tra ràng buộc riêng của `Instrumentation`.

## 9. Cách so sánh “đúng tầng”, từ thô đến sâu

| Cấp so sánh | So sánh gì? | Ưu điểm | Giới hạn |
| --- | --- | --- | --- |
| **L0. Raw bytes/hash** | `Arrays.equals`, SHA-256 | Xác minh tệp hoàn toàn giống nhau | Báo khác ngay cả khi chỉ pool/order/debug attrs đổi |
| **L1. Header/schema** | Class name, version, superclass, interfaces, access flags, fields/methods theo key | Phát hiện thay đổi schema có thể vi phạm redefine rules | Chưa chứng minh method behavior |
| **L2. Constant symbols** | Resolve CP refs thành owner/name/descriptor/constant values | Bỏ nhiễu số `#n` | Cần giải mã đúng bootstrap/dynamic constants |
| **L3. Code logic** | Instruction kinds, symbolic operands, branch flow, handlers, return semantics | Nhìn được thay đổi logic thực thi | Offset, `ldc`/`ldc_w`, frame có thể khác nhưng vẫn hợp lệ |
| **L4. Metadata policy** | `Code`/`StackMapTable` và attributes được chọn | Nhận biết thay đổi ảnh hưởng verifier, reflection, debug | Cần phân biệt bắt buộc/optional/semantic |
| **L5. Verification và hành vi** | Load class, chạy tests, lỗi/return/side effects/concurrency | Bắt lỗi thực tế khi chạy | Không chứng minh hai chương trình hoàn toàn tương đương cho mọi input |

**Luồng QA đề xuất:**

```text
(1) Ghi rõ snapshot nguồn + thời điểm + JVM vendor/version
                         │
                         ▼
(2) Nếu bytes bằng nhau ─────► Kết luận binary-equal (trong cặp này)
    Nếu bytes khác:
                         │
                         ▼
(3) Parse ClassFile, đối chiếu class name / superclass / interfaces
                         │
                         ▼
(4) So fields và methods bằng name + descriptor, KHÔNG theo index
                         │
                         ▼
(5) Resolve constant-pool references, so nội dung symbolic của code
                         │
                         ▼
(6) So attributes theo policy, validate branch/handler/stack maps
                         │
                         ▼
(7) Chạy verifier/ứng dụng/tests và kiểm tra side effects
```

### 9.1. Tạo fingerprint phục vụ debug, không đánh tráo định nghĩa

Một fingerprint logic có thể gồm:

```text
Class name + class major version + flags
Superclass + interfaces theo ý nghĩa cấu trúc
Fields: sorted by (name, descriptor) với flags và metadata được chọn
Methods: sorted by (name, descriptor) với flags và metadata được chọn
Code: opcodes và symbolic operands đã resolve
Control flow: normalized branch targets và exception handlers
Attributes: normalized values của những attributes phải so
```

Đây là **pseudocode mô tả bản tóm tắt cấu trúc**, không phải chương trình Java chạy độc lập. Muốn hiện thực, dùng ASM hoặc JDK Class-File API (JDK 24+) để phân tích định dạng; đừng tự cắt bytes theo offsets đoán. “Normalize” chỉ được thực hiện ở các vị trí có quan hệ tương đương mà bạn đã xác minh. Chẳng hạn thứ tự **methods** có thể xem như map theo key, nhưng thứ tự **instructions** và thứ tự **exception handlers** có thể ảnh hưởng ngữ nghĩa nên không được tùy tiện sort.

Đừng sử dụng fingerprint logic thay thế SHA-256 nếu yêu cầu là **chứng minh artifact bất biến từng byte** (compliance, supply-chain verification). Hai mục tiêu khác nhau nên cần hai loại phép kiểm tra khác nhau.

## 10. Những vị trí diff dễ gây báo động giả

### 10.1. Constant pool index khác

`javap -v` có thể cho thấy:

```text
#12 = Methodref ... java/lang/Object."<init>":()V
#28 = Methodref ... java/lang/Object."<init>":()V
```

Hai dòng trên chỉ là **minh họa chỉ số**, không phải output từ một file cụ thể. Nếu hai snapshot cùng gọi `java/lang/Object.<init>()V`, chỉ số `#12` và `#28` khác không đủ để báo hành vi khác.

**Đúng:** so owner/name/descriptor sau resolve.  
**Sai:** so raw text `#12 != #28` rồi kết luận class đã gọi method khác.

### 10.2. Thứ tự methods khác

Nếu dump `javap` của A in `alpha` trước `beta`, còn B in `beta` trước `alpha`, raw text diff sẽ báo cả đoạn thay đổi. Map từng method theo `name+descriptor` và so nội dung tương ứng.

### 10.3. Debug attributes vắng mặt

`LineNumberTable` thay đổi có thể làm stack trace thiếu line numbers, nhưng chưa chứng minh logic tính toán khác. Đừng coi nó là vô hại nếu debugging là yêu cầu; hãy báo **metadata difference** tách biệt với **code behavior difference**.

### 10.4. “Hash khác” ngay cả khi transformer trả `null`

Ngay cả khi observer của bài lab chỉ trả `null`, JVM có thể cấp input R không giống input L theo đặc tả. Chênh lệch cũng có thể do **transformers khác**, redefinition đã xảy ra, hoặc snapshot không lấy đúng thời điểm. Vì thế phải ghi lại **snapshot stage** thay vì gắn nhãn “original” mơ hồ.

### 10.5. Đã thay code nhưng SHA không đổi?

Nếu đối chiếu đúng **cùng hai files** bằng SHA-256 và hash thật sự bằng nhau, về thực hành gần như chắc chắn bytes giống nhau; nhưng sự kiện đó không đảm bảo instrumentation trong memory chưa từng chạy. Bạn có thể đang băm **file disk trước/sau** mà không lấy bytes output của transformer; hoặc class đã được transform trong JVM mà artifact trên đĩa vẫn nguyên.

## 11. Idempotency: đừng dựa vào so bytes gốc

Một transformer có thể cần tránh chèn hook hai lần khi load, redefine hoặc retransform. Hai cách làm dễ sai:

- `Arrays.equals(classfileBuffer, originalDiskBytes)` để quyết định “chưa instrument”: JVM có thể tái biểu diễn bytes khiến phép bằng thất bại dù không có hook.
- Kiểm tra một offset cụ thể, ví dụ byte ở vị trí 123 hoặc constant-pool index `#15`, để nhận diện marker: offset/index có thể đổi khi build/pipeline/CP thay đổi.

**Cách bền vững hơn:** kiểm tra **cấu trúc code** và đặc điểm hook thật sự, ví dụ invocation tới `agent/TraceHooks.enter(Ljava/lang/String;)V` tại đúng vị trí; hoặc dùng metadata/marker hợp lệ mà pipeline hỗ trợ, kết hợp với policy của JVM về các thay đổi được phép trong retransform.

Chú ý **không** dùng chiến lược “thêm một field marker mới” trong retransformation nếu JVM không cho thay schema class. Một cách làm đúng ở lần load có thể không hợp lệ ở lần retransform. Đối với transformer retransform-capable, có thể thiết kế transform theo hướng **deterministic trên input chưa có hook thuộc giai đoạn hiện tại**, và ghi nhận test cho việc retransform lặp lại. Nếu có transformer khác đứng trước, cần biết hook của họ có thể đã được tái áp dụng.

## 12. Các lỗi thường gặp và hướng khắc phục

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| SHA-256 file disk khác snapshot retransform | JVM có thể tái biểu diễn, transformer pipeline, redefinition | So đúng stage và semantic diff, không kết luận ngay |
| `javap -v` cho CP count hoặc `#n` khác | CP layout/contents thay, writer/VM tái cấu trúc | Resolve symbolic references; kiểm tra các operand vẫn hợp lệ |
| Methods cùng tên nhưng diff báo lệch hết | So theo vị trí `methods[]` thay vì key | Map theo `name + descriptor` |
| `SourceFile`, `LineNumberTable` thiếu | Snapshot có thể khác attributes hoặc dùng `javac -g:none` | Phân loại debug metadata, ghi ảnh hưởng debugger |
| Runtime annotations biến mất | Có thể là biến đổi không mong muốn | Không bỏ qua; kiểm tra reflection behavior và pipeline |
| `VerifyError` sau transform | Stack maps, branch offsets, CP refs, method descriptors sai | Dùng verifier, ASM check, `javap -v`; sửa writer/transform logic |
| `UnmodifiableClassException` | JVM không cho sửa class đó | `isModifiableClass`, loại target khác |
| `UnsupportedOperationException` khi đăng ký retransform | Agent/VM không hỗ trợ capability | Manifest `Can-Retransform-Classes` và `isRetransformClassesSupported` |
| Callback transformer “không chạy lại” | Đăng ký `canRetransform=false` | Đúng theo hợp đồng; kết quả cũ tái áp dụng |
| Hook bị ghi đôi | Transformer không idempotent hoặc pipeline trùng | Nhận diện hook theo code symbols; kiểm thử retransform nhiều lượt |
| Diff stdout `javap` có nhiều thay đổi | Constant pool indexes, methods order, attributes khác | Tách diff code logic khỏi metadata/layout |
| `ClassFormatError` hoặc `VerifyError` | Output class invalid | Không chỉ so hash; validate class file và stack/frames |
| Output mất sau gọi `retransformClasses` | Có thể đang chỉ instrument lúc load, không retransform-capable | Phân tích nhóm transformer và phép tái áp dụng tự động |
| JVM dùng định nghĩa cũ trong frame đang chạy | Active frames giữ bytecode cũ | Kiểm tra semantics về active frames vs new invokes |
| Trên máy A bytes bằng, máy B khác | Vendor, VM, version, tools khác | Không hardcode expectation về byte identity |

Một bug thật sự cần chứng minh bằng **thay đổi symbols/behavior**, invalid class format, metadata quan trọng bị mất trái yêu cầu hoặc độ bao phủ transform sai; không phải chỉ bởi một hash mới.

## 13. Checklist kiểm chứng trong dự án instrumentation

- [ ] Ghi đủ **vendor, `java.vm.name`, JDK version, loader/module identity**, thời điểm và hành động `load`/`redefine`/`retransform`.
- [ ] Ghi rõ snapshot là **disk**, **input callback** hay **output callback**; tránh tên `original.class` gây hiểu nhầm.
- [ ] Không sửa trực tiếp `classfileBuffer`; cần transform thì trả mảng mới hợp lệ, không đổi thì trả `null`.
- [ ] Bật capability bằng manifest và `addTransformer(..., true)` khi cần retransform, đồng thời kiểm tra `isRetransformClassesSupported()`/`isModifiableClass`.
- [ ] Không kỳ vọng transformer `canRetransform=false` được gọi lại; hiểu cơ chế tái áp dụng kết quả.
- [ ] So hash nếu mục tiêu là byte identity; không kết luận semantic difference chỉ từ hash.
- [ ] Map methods theo **name + descriptor**, không theo index/khối text.
- [ ] Resolve constant-pool indices thành **symbolic references** trước khi so lệnh.
- [ ] So attributes theo mục đích: debug, reflection, verifier, module hoặc API compatibility.
- [ ] Khi so code, giữ ngữ nghĩa thứ tự instructions/exception handlers/control flow; không sort tùy tiện.
- [ ] Chạy verifier và kiểm thử hành vi sau biến đổi, gồm normal returns/exceptions/constructor/overloads.
- [ ] Kiểm thử retransform **hai lần liên tiếp** để phát hiện hook trùng và state không nhất quán.
- [ ] Nếu thấy khác bytes nhưng cùng behavior, ghi kết luận đúng mức: **không binary-equal, chưa thấy semantic regression theo các phép kiểm hiện có**.
- [ ] Không tuyên bố “mọi JVM đều đảo pool” hoặc “mọi attribute có thể vứt bỏ”; dùng docs của bản VM thực tế.

## 14. Câu hỏi tự kiểm tra

1. **Vì sao SHA-256 của class file trên disk có thể khác snapshot callback ở retransform?**  
   Vì VM được phép dùng biểu diễn class file không byte-identical với input define/redefine gốc; thêm nữa pipeline transformers và redefinition có thể tác động.

2. **Constant pool entry `println:(I)V` ở `#18` trong bản A và `#41` trong bản B. Có chắc hành vi đổi?**  
   Không. Cần kiểm tra bytecode của mỗi bản tham chiếu đúng symbol; số `#n` chỉ có nghĩa trong pool của bản đó.

3. **Hai snapshot có cùng ba methods nhưng thứ tự khác. Làm sao so?**  
   Dùng key `class + methodName + descriptor`, sau đó so flags, code và metadata của cặp tương ứng.

4. **Một số attributes vắng ở callback retransform có phải lỗi JVM?**  
   Không tự động. Javadoc cho phép một số attributes không hiện diện. Nhưng metadata ảnh hưởng runtime/reflection/verification phải được đánh giá theo yêu cầu, không bỏ qua vô điều kiện.

5. **`canRetransform=false` có được gọi lại khi `retransformClasses` không?**  
   Không theo cơ chế chuẩn; VM tái áp dụng kết quả biến đổi trước đó mà không gọi callback ấy.

6. **Nếu observer trả `null`, snapshot R luôn giống snapshot L từng byte?**  
   Không bảo đảm. `null` chỉ khẳng định observer không tạo biến đổi tại callback; VM/pipeline có thể cấp input khác.

7. **Một transformer `canRetransform=true` có thể giả định input R chứa hook nó từng chèn ở lần đầu không?**  
   Không. Quy trình retransform bắt đầu từ initial bytes và tái áp dụng nhóm không hỗ trợ retransform; cần thiết kế transform không phụ thuộc giả định sai này.

8. **Có được bỏ `StackMapTable` vì Java có thể tự suy stack?**  
   Không được suy vậy. Class file hợp lệ và verifier constraints phải được thỏa; metadata verification có thể là bắt buộc trong hoàn cảnh tương ứng.

9. **Method `save(String)` và `save(int)` có cùng name. Dùng mỗi tên `save` làm key được không?**  
   Không. Phải thêm descriptor, chẳng hạn `(Ljava/lang/String;)V` và `(I)V`.

10. **Trường hợp `byte[]` khác nhưng program output giống, đã chứng minh tương đương cho mọi input chưa?**  
    Chưa. Mới chỉ có một số kiểm tra hành vi; cần code/metadata analysis, test coverage và ràng buộc nghiệp vụ.

11. **`javap -classpath out demo.Target` có tự thấy mã mà transformer chỉ cài trong JVM không?**  
    Không. Nó đọc bytes từ classpath đã chỉ định; cần dump output transformer riêng nếu muốn xem biến đổi runtime.

12. **Tại sao chạy một lần retransform có thể giữ trạng thái static fields và objects cũ?**  
    Vì `retransformClasses` thay class definition theo các quy tắc VM, không chạy lại static initialization hoặc reset object state.

## 15. Nguồn chính thức

1. Oracle JDK 17 — **`Instrumentation.retransformClasses`**: khác biệt constant pool/order/attributes, pipeline, active frames và schema restrictions: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html#retransformClasses(java.lang.Class...)
2. Oracle JDK 25 — **`Instrumentation`** (đối chiếu hợp đồng ở bản mới): https://docs.oracle.com/en/java/javase/25/docs/api/java.instrument/java/lang/instrument/Instrumentation.html
3. Oracle JDK 17 — **`ClassFileTransformer`**, thứ tự transformers, `classfileBuffer`, `null` và mảng output: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html
4. Oracle JDK 17 — **Agent package**, `Premain-Class` và `Can-Retransform-Classes`: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html
5. JVMS 17 — **Class-file format `4`**, constant pool, methods, attributes và Code: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html
6. Oracle JDK 17 — **`javap`**, `-c`, `-v`, `-p`, `-s`: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html
7. JVMTI — **RetransformClasses** và ràng buộc VM Tool Interface: https://docs.oracle.com/javase/8/docs/platform/jvmti/jvmti.html#RetransformClasses

**Kết luận:** `retransformClasses` làm việc với một **định nghĩa class file hợp lệ** chứ không hứa cung cấp lại từng byte chính xác của artifact đã lưu. Constant-pool entries, method ordering và attributes có thể khác. Khi xây công cụ instrumentation, hãy bảo vệ byte buffer đầu vào, xác định stage/snapshot, so cấu trúc bằng symbols/descriptors, chỉ bỏ qua metadata khi có chính sách rõ ràng, và cuối cùng xác minh bằng verifier cùng hành vi runtime.

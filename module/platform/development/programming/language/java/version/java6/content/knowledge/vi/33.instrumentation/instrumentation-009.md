# Giới hạn sửa cấu trúc lớp và tương tác nhiều ClassFileTransformer trong Java

## 1. Mục tiêu: hiểu đúng “đổi bytecode” và “đổi cấu trúc”

Trong Java agent, một `ClassFileTransformer` có thể can thiệp vào class bytes trước khi JVM định nghĩa lớp, hoặc vào chuỗi transformation khi một class đã loaded được yêu cầu `retransformClasses` / `redefineClasses`. Cơ chế này là nền tảng của những công cụ quan sát, tracing, coverage và profiling. Tuy nhiên, **không phải mọi bytecode hợp lệ đều được JVM chấp nhận để thay một lớp đang chạy**.

Hai vấn đề học cùng nhau vì có liên hệ chặt chẽ:

1. **Giới hạn cấu trúc khi sửa class đã loaded**: đâu là thay đổi được phép đối với method bodies/constant pool, đâu là thay đổi bị cấm đối với fields/methods/inheritance và metadata của record/sealed/nest?
2. **Tương tác giữa nhiều transformers**: khi 2–4 agents cùng instrument một class, thứ tự áp bytes là gì, transformer nào được gọi lại lúc retransform, khi gỡ transformer thì bytecode có khôi phục không, và làm sao chứng minh chain đã chạy đúng?

Đây là kiến thức **còn áp dụng trong Java 17+**, đối chiếu API Java SE 25 và đặc tả **JVM Tool Interface (JVMTI) 25**. Hai bài thực hành đều **runnable**, không dùng Attach API hoặc thư viện ngoài: ví dụ 1 dùng **Java 17+** để chứng minh thứ tự callback; ví dụ 2 dùng **Java 24+** với **Class-File API chuẩn** để chứng minh bốn transformation tạo ra kết quả thực, thử vi phạm cấu trúc qua cả retransform và redefine, rồi quan sát trạng thái còn nguyên sau thất bại.

**Điều cần nhớ ngay:** JVM có thể chấp nhận một classfile được instrument **trước lần define đầu tiên**, dù nó thêm fields/methods; nhưng khi **retransform/redefine một class đã loaded**, những thay đổi làm **khác cấu trúc class** chịu giới hạn nghiêm ngặt. Không được nghĩ “class bytes hợp lệ” tức là “hot swap thành công”.

~~~text
                     JVM start với -javaagent
                                |
                         premain(agent, inst)
                                |
                Đăng ký ClassFileTransformer(s)
                                |
            +-------------------+-------------------+
            |                                       |
         Class load                         Class đã loaded
            |                                       |
       transform chain                         retransform
            |                                hoặc redefine
            |                                       |
       byte[] -> verify                      transform chain
            |                                       |
        define class                      verify + structural rules
            |                                       |
     Runtime method calls                  nếu hợp lệ -> install
                                                  |
                                        nếu vi phạm -> reject,
                                        class đang chạy vẫn nguyên
~~~

Bài phân biệt ba cách:
- **Class load**: JVM định nghĩa class từ bytes sau khi transformers đã chạy.
- **Retransform**: JVM tái thực hiện cơ chế transform để cập nhật class đang loaded.
- **Redefine**: caller cung cấp `ClassDefinition(clazz, newBytes)` để thay implementation hiện tại; transformer chain vẫn có thể tham gia.

## 2. Các API hiện hành và khả năng cần xin

| API | Vai trò | Lưu ý quan trọng |
| --- | --- | --- |
| `Instrumentation.addTransformer(t)` | Đăng ký transformer **không capable retransform** | Tương đương `addTransformer(t,false)` |
| `Instrumentation.addTransformer(t,true)` | Đăng ký transformer **capable retransform** | Runtime phải cho phép, manifest cần capability |
| `Instrumentation.removeTransformer(t)` | Gỡ một đăng ký transformer | Không tự hoàn tác class bytes |
| `Instrumentation.isRetransformClassesSupported()` | Kiểm capability retransform | Phụ thuộc manifest **Can-Retransform-Classes** và JVM |
| `Instrumentation.retransformClasses(classes...)` | Cập nhật class definitions đang loaded qua transformation chain | Không được đổi cấu trúc lớp vượt contract |
| `Instrumentation.isRedefineClassesSupported()` | Kiểm capability redefine | Phụ thuộc manifest **Can-Redefine-Classes** và JVM |
| `Instrumentation.redefineClasses(definitions...)` | Thay class definitions bằng bytes do caller cấp | Không cho arbitrary schema changes |
| `Instrumentation.isModifiableClass(clazz)` | Kiểm class cụ thể có thể bị đổi | Không đảm bảo mọi bộ bytes mới đều hợp lệ |
| `ClassDefinition` | Class object + replacement classfile bytes | Dành cho `redefineClasses` |
| `ClassFileTransformer.transform(...)` | Nhận bytes đầu vào, trả bytes mới hoặc `null` | Có thể được gọi trên nhiều threads |
| `java.lang.classfile.ClassFile` | Parse và tái dựng bytecode với type-safe API | **Java 24+**, chuẩn từ JEP 484 |
| `ClassTransform`, `CodeTransform` | Thành phần chọn class methods và viết lại code elements | Java 24+ |
| `UnmodifiableClassException` | Class không có quyền/capability sửa | Khác với một structure change bị từ chối |
| `UnsupportedOperationException` | Có thể phát sinh khi không hỗ trợ retransform/redefine hoặc thay đổi cấu trúc không hợp lệ | Xem cause/JDK semantics |

**Module:** `java.lang.instrument` thuộc `java.instrument`; `java.lang.classfile` thuộc `java.base` từ Java 24. Trên Java 17 và Java 21, bytecode editing thực sự thường dùng một thư viện đã được review như ASM/Byte Buddy; các rules JVM về retransform/redefine **vẫn áp dụng**. Không lấy ví dụ Class-File API Java 24 đem compile bằng `--release 17`.

### Manifest và capability

Agent startup chạy với `Premain-Class`. Nếu cần retransform hay redefine:

~~~text
Manifest-Version: 1.0
Premain-Class: ChainAgent
Can-Retransform-Classes: true
Can-Redefine-Classes: true

~~~

Đây là manifest của **chương trình số 2**, không phải manifest duy nhất có thể dùng. Một agent chỉ quan sát class loads và không cần redefine thì **không nên xin thêm quyền**. `Can-Retransform-Classes: true` là yêu cầu capability; JVM vẫn có thể không hỗ trợ, vì thế luôn kiểm `isRetransformClassesSupported()` trước khi đăng ký với flag true hoặc gọi retransform.

Với startup agent:

~~~bash
java -javaagent:chain-agent.jar -cp chain-agent.jar ChainApp alternative/StructureTarget.class
~~~

Lệnh là ví dụ chạy trong thư mục có JAR và class bytes thay thế của bài, **không phải câu lệnh tự tải agent từ Internet**. Java agent phải là artifact đáng tin, được chủ sở hữu JVM chủ động khai báo.

## 3. Cấu trúc class và bytecode method là hai tầng khác nhau

Một classfile chứa nhiều nhóm thông tin:

~~~text
.class bytes
  magic, version, constant pool
  access flags
  this_class / super_class
  interfaces
  fields: tên, descriptor, modifiers, attributes
  methods: tên, descriptor, modifiers, Code attribute...
  class-level attributes: InnerClasses, NestHost/NestMembers,
                          Record, PermittedSubclasses, ...
~~~

**Đổi method body** thường có thể hợp lệ khi retransform/redefine, ví dụ:
- Thêm lời gọi counter/tracing span vào một method đã tồn tại.
- Đổi các bytecode instructions trong method, giữ nguyên descriptor/signature.
- Điều chỉnh constant pool, stack map information và Code attributes hợp lệ.

Tuy nhiên, một method body đã thay phải vẫn qua **classfile parsing, verifier, linkage và structural rules**. Không thể thêm một field rồi gọi field mới từ method mà cho rằng JVM đang chạy sẽ chấp nhận vì bytecode parser không lỗi.

### Các thay đổi cấu trúc bị hạn chế trong JVMTI 25

Đối với **class đã loaded** theo JVMTI RetransformClasses/RedefineClasses hiện hành, không được:
- Thêm, xóa hoặc đổi tên fields;
- Thêm, xóa hoặc đổi tên methods;
- Thay đổi method signatures/descriptors;
- Đổi method/field/class modifiers theo những giới hạn JVMTI;
- Đổi inheritance, superclass hoặc danh sách interfaces;
- Đổi `NestHost` và `NestMembers` attributes;
- Đổi `Record` attribute của records;
- Đổi `PermittedSubclasses` attribute của sealed classes.

Các hạn chế này được đặc tả ở **JVMTI 25**; không giả định mọi runtime đều mở rộng chúng hoặc một tương lai khác sẽ giữ nguyên từng câu chữ. Một class được JVM hỗ trợ chỉnh không có nghĩa có thể thêm field/new method bằng `retransformClasses`. <https://docs.oracle.com/en/java/javase/25/docs/specs/jvmti.html>

| Đổi gì ở class đang loaded? | Kỳ vọng chung khi retransform/redefine |
| --- | --- |
| Đổi literal trong body của method đã tồn tại | **Có thể hợp lệ** nếu bytecode hợp lệ |
| Thêm tracing ở đầu/cuối method có sẵn | Có thể hợp lệ, cần verifier và exception paths đúng |
| Thay cấu trúc constant pool | Có thể hợp lệ, giới hạn compatibility |
| Thêm instance field `long callCount` | **Bị từ chối** |
| Thêm static field `Counter METRICS` | **Bị từ chối** |
| Xóa/đổi tên field | **Bị từ chối** |
| Thêm method mới `getMetrics()` | **Bị từ chối** |
| Đổi descriptor `foo(I)I` thành `foo(J)I` | **Bị từ chối** |
| Đổi superclass hoặc implement interface khác | **Bị từ chối** |
| Đổi public/private/final modifiers thuộc structural restriction | **Bị từ chối** |
| Đổi NestHost/NestMembers | **Bị từ chối** |
| Đổi Record/PermittedSubclasses metadata | **Bị từ chối** |
| Trả class name khác target | `NoClassDefFoundError` hoặc linkage failure |
| Classfile version không được JVM hỗ trợ | `UnsupportedClassVersionError` |
| Thay structure **trước định nghĩa lần đầu** | Có thể hợp lệ nếu toàn bộ class bytes và dependencies hợp lệ |

### Vì sao Java cần những giới hạn này?

Class đã loaded có:
- `Class<?>` identity và vtables/interface dispatch đã được JVM thiết lập;
- Instance objects đang sống với field layout/offsets được quản lý;
- Static fields đã được khởi tạo, class initialization state;
- References từ JIT compiled code, stack frames đang active, method metadata;
- Reflection, method handles, invoke dynamics, nest/access control và module linking.

Việc cho phép thêm/xóa field hoặc đổi inheritance giữa chừng có thể làm object layout, references, dispatch và stack frames không nhất quán. Vì vậy **retransform/redefine không phải hot schema migration**. Nếu muốn đổi data model hoặc class hierarchy, giải pháp triển khai đúng thường là **build/redeploy phiên bản mới** (và quản lý data migration) thay vì cố sửa class đang chạy.

### Một ví dụ rất nhỏ

~~~java
// Định nghĩa đang loaded:
final class StructureTarget {
    private int original = 7;
    int read() { return original; }
}
~~~

Đoạn minh họa là class không public, có thể đặt trong file Java cùng package. Khi đã loaded, một replacement class có cùng binary name nhưng **thêm**:

~~~java
// Replacement bytes định dùng sau khi class đã loaded:
final class StructureTarget {
    private int original = 7;
    private int added = 9; // Thêm field: không hợp lệ cho redefine/retransform.
    int read() { return original; }
}
~~~

Hai định nghĩa cùng tên này phải được compile ở **hai output directories tách biệt**, không nằm chung một compilation unit. Ví dụ hoàn chỉnh ở phần 9 biên dịch riêng alternative class file rồi thử áp nó lên class đã loaded. Kết quả trên OpenJDK 24 là **bị từ chối**, object cũ và class structure cũ vẫn tồn tại.

## 4. Tương tác nhiều transformer: bốn nhóm, không phải một hàng đợi FIFO toàn cục

Theo Javadoc Java SE 25 của `ClassFileTransformer`, JVM áp transformations theo **bốn nhóm**:

1. **Java transformers không capable retransform** (`addTransformer(t,false)`).
2. **Native transformers không capable retransform** (JVMTI `ClassFileLoadHook`).
3. **Java transformers capable retransform** (`addTransformer(t,true)`).
4. **Native transformers capable retransform** (JVMTI `ClassFileLoadHook`).

**Trong từng nhóm**, transformers được gọi theo **thứ tự đăng ký**. Nhưng nếu đăng ký một transformer capable rồi một incapable, không có nghĩa capable chắc chắn chạy trước incapable.

### Ví dụ cố ý đăng ký xen kẽ

~~~java
inst.addTransformer(capable1, true);     // C1 đăng ký đầu.
inst.addTransformer(incapable1, false);  // I1 đăng ký thứ hai.
inst.addTransformer(capable2, true);     // C2 đăng ký thứ ba.
inst.addTransformer(incapable2, false);  // I2 đăng ký cuối.
~~~

Đây là snippet bên trong `premain` với `inst` và bốn callback objects. Nếu chỉ có **Java transformers** thì khi định nghĩa một class mới, thứ tự thực thi là:

~~~text
Đăng ký: C1, I1, C2, I2
Thực thi lúc load: I1 -> I2 -> C1 -> C2
~~~

Không phải `C1 -> I1 -> C2 -> I2`. Ví dụ 1 dưới đây ghi lại chính xác thứ tự để tránh lý thuyết suông.

### Chuỗi byte[] được truyền như thế nào?

~~~text
Original classfile bytes
          |
          v
    transformer I1
          | return new byte[] hoặc null
          v
    transformer I2
          | thấy kết quả đã qua I1
          v
    transformer C1
          | thấy kết quả đã qua I1 + I2
          v
    transformer C2
          | thấy kết quả đã qua I1 + I2 + C1
          v
    JVM verify + define class
~~~

Khi một transformer trả `byte[]` mới, bytes đó thành **`classfileBuffer` đầu vào của transformer kế tiếp**. Khi trả `null`, transformer không thực hiện sửa đổi, và chain tiếp tục với bytes đang có. Không mutate input `classfileBuffer` tại chỗ; tạo bytes mới bằng API phù hợp.

**Transformer sau nhìn thấy effects của transformer trước**, nên pipeline không đơn giản là bốn phép “chạy độc lập” rồi JVM tự merge results. Hai transformers cùng sửa một method có thể phụ thuộc nhau, ghi đè nhau hoặc tạo bytes sai khi phối hợp.

## 5. Khi retransform: nhóm incapable không được gọi lại

Đây là điểm kỹ thuật quan trọng nhất cần nhớ.

Khi gọi:

~~~java
instrumentation.retransformClasses(ChainTarget.class);
~~~

JVM bắt đầu từ representation của initial classfile bytes (hoặc bytes của **lần redefine gần nhất**). Theo Javadoc, với mỗi transformer **không capable retransform**, JVM **tái sử dụng kết quả** của transformation ở lần load/redefine trước, **không gọi lại `transform(...)`**. Những transformers capable sẽ được **gọi lại** theo nhóm và registration order.

~~~text
Lúc define class:
   BASE -> I1 -> ONE -> I2 -> TWO -> C1 -> THREE -> C2 -> FOUR
   callbacks: load:I1, load:I2, load:C1, load:C2

Lúc retransform:
   source bytes -> (reapply I1/I2 đã lưu, KHÔNG callback)
                -> TWO -> C1 -> THREE -> C2 -> FOUR
   callbacks: redo:C1, redo:C2
~~~

**Lưu ý tinh tế:** các bytes “ban đầu” dùng trong retransformation **không được bảo đảm giống từng byte với file .class gốc trên đĩa**. JVM có thể thay đổi constant pool layout và một số attributes/ordering. Instrumentation code phải parse theo classfile specification, không so byte-for-byte với artifact gốc để kết luận bytes đã bị thay lén.

### Không nhầm ba cách “áp lại”

| Sự kiện | Incapable Java transformers | Capable Java transformers |
| --- | --- | --- |
| Class load mới | `transform(...)` được gọi | `transform(...)` được gọi |
| `redefineClasses(...)` | `transform(...)` được gọi | `transform(...)` được gọi |
| `retransformClasses(...)` | **Không gọi**; JVM tái sử dụng kết quả cũ | **Gọi lại `transform(...)`** |

Native transformer groups tuân theo thứ tự nhóm như Javadoc, nhưng các ví dụ thuần Java ở đây không cài native JVMTI agent. Đừng khẳng định ví dụ Java đã kiểm native ordering khi nó chỉ có Java transformers.

### Transformer chain không được tự ý phá structural rules

Nếu transformer I1 thêm field trong lúc **lần define đầu tiên**, JVM có thể định nghĩa class có field mới nếu bytes đúng. Nhưng sau đó C1/C2 và mọi lần retransform/redefine phải tạo **schema tương thích với class đã loaded**. Không được trả classfile thiếu field hoặc đổi descriptors rồi kỳ vọng JVM tự sửa object layout.

## 6. Java 17+ runnable demo số 1: kiểm callback order với bốn transformers

Demo đầu tiên sử dụng **chỉ Java standard library**, không dùng thư viện viết bytecode, không thay đổi class behavior. Mỗi transformer lọc đúng `ObservedClass`, lưu tên gọi vào `CopyOnWriteArrayList` và trả `null`. Vì nó không sửa bytes, output đặc biệt rõ ràng:

- Lúc load, dù đăng ký `C1,I1,C2,I2`, callbacks là `I1,I2,C1,C2`.
- Lúc retransform, chỉ capable `C1,C2` được callback.
- Method `value()` vẫn trả `5` trước và sau.
- Yêu cầu JDK 17+, manifest `Can-Retransform-Classes: true`, runtime thực tế phải có capability.

### File OrderOnlyAgent.java

~~~java
import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

public final class OrderOnlyAgent {
    private static Instrumentation instrumentation;
    private static final List<String> calls = new CopyOnWriteArrayList<>();

    static ClassFileTransformer observer(String id) {
        return new ClassFileTransformer() {
            @Override public byte[] transform(Module module, ClassLoader loader,
                    String name, Class<?> redefining, ProtectionDomain domain,
                    byte[] originalBytes) {
                if ("ObservedClass".equals(name)) {
                    calls.add((redefining == null ? "load:" : "redo:") + id);
                }
                return null; // Observe only, preserve bytecode.
            }
        };
    }

    public static void premain(String options, Instrumentation inst) {
        instrumentation = inst;
        if (!inst.isRetransformClassesSupported()) {
            throw new IllegalStateException("Retransform unavailable");
        }
        // Deliberately interleaved registration order.
        inst.addTransformer(observer("C1"), true);
        inst.addTransformer(observer("I1"), false);
        inst.addTransformer(observer("C2"), true);
        inst.addTransformer(observer("I2"), false);
    }

    public static String calls() {
        return String.join(",", calls);
    }

    public static void clear() {
        calls.clear();
    }

    public static void retransform(Class<?> target) throws Exception {
        if (!instrumentation.isModifiableClass(target)) {
            throw new IllegalStateException("Target not modifiable");
        }
        instrumentation.retransformClasses(target);
    }
}
~~~

### File OrderOnlyApp.java

~~~java
public final class OrderOnlyApp {
    public static void main(String[] args) throws Exception {
        ObservedClass observed = new ObservedClass();
        System.out.println("class method before: " + observed.value());
        System.out.println("load calls: " + OrderOnlyAgent.calls());
        OrderOnlyAgent.clear();
        OrderOnlyAgent.retransform(ObservedClass.class);
        System.out.println("class method after: " + observed.value());
        System.out.println("retransform calls: " + OrderOnlyAgent.calls());
    }
}

final class ObservedClass {
    int value() {
        return 5;
    }
}
~~~

### File ORDER.MF

~~~text
Manifest-Version: 1.0
Premain-Class: OrderOnlyAgent
Can-Retransform-Classes: true

~~~

### Compile và chạy

~~~bash
mkdir out17
javac --release 17 -d out17 OrderOnlyAgent.java OrderOnlyApp.java
jar --create --file order-only-agent.jar --manifest ORDER.MF -C out17 .
java -javaagent:order-only-agent.jar -cp order-only-agent.jar OrderOnlyApp
~~~

Các lệnh chạy trong một thư mục mới với JDK 17+ (PowerShell cũng dùng được). `-javaagent` giúp JVM gọi `premain` trước `OrderOnlyApp.main`. Với một VM không hỗ trợ retransform, ví dụ chủ động **fail với thông báo capability**, không diễn giải output đó như một bug về order.

**Stdout chính xác** đã kiểm thử trên **OpenJDK 24.0.2** với `javac --release 17`:

~~~text
class method before: 5
load calls: load:I1,load:I2,load:C1,load:C2
class method after: 5
retransform calls: redo:C1,redo:C2
~~~

### Đọc kết quả

`load:I1,I2,C1,C2` chứng minh **group priority** thắng registration interleaving. `redo:C1,C2` chứng minh chỉ retransform-capable transformers được chạy lại, còn incapable nhóm I1/I2 không callback. `class method after: 5` chứng minh **return null** không sửa bytecode, ngay cả khi `retransformClasses` chạy thành công.

**Đừng nhầm số callback với số method calls.** `ClassFileTransformer.transform` được gọi khi classfile được define/redefined/retransformed, **không phải mỗi khi `ObservedClass.value()` được gọi**. Muốn đo độ trễ của method trong production, phải cấy runtime telemetry instructions hoặc dùng thư viện instrumentation đã kiểm chứng.

## 7. Dùng Class-File API Java 24+ để thay bytecode thật

Từ **Java 24**, JEP 484 đưa `java.lang.classfile` thành **API chuẩn** (không còn preview). Nó cho phép parse/rebuild classfile với `ClassFile`, `ClassTransform`, `CodeTransform` và `ConstantInstruction.LoadConstantInstruction`.

Để chứng minh bytes thật sự được chuyển qua transformer chain, bài số 2 dùng bốn stages chỉ thay một string literal trong **method đã tồn tại**:

~~~text
Target code ban đầu trả "BASE".

I1: "BASE"  -> "ONE"
I2: "ONE"   -> "TWO"
C1: "TWO"   -> "THREE"
C2: "THREE" -> "FOUR"

Result cuối khi class load: "FOUR".
Result sau retransform với C1/C2: "FOUR".
Remove C2 KHÔNG đổi class ngay: vẫn "FOUR".
Retransform lần tiếp sau khi remove C2: "THREE".
~~~

**Không thêm field/method** trong chain cho `ChainTarget`, nên đây là body-only transform có thể hợp lệ với retransform. Từng transformer tạo **một byte[] mới** bằng Class-File API, không sửa input bytes, không dùng regex trên classfile binary.

### Tại sao lại thay string literal thay vì thêm telemetry hook?

Đây là **phép thử chức năng ngắn, xác định** để nhìn thấy việc áp thứ tự biến đổi; không phải mẫu production được khuyến nghị. Trong công cụ observability, transformer nên thêm counters, span/timer hooks và xử lý exceptions **mà không đổi business return value**. Việc demo thay `"BASE"` thành `"FOUR"` chỉ để kiểm tra rằng chain có thực sự thay bytecode.

### Giới hạn ví dụ

- Cần **JDK 24+** để compile agent dùng Class-File API.
- Target là một class cụ thể `ChainTarget` trong **unnamed module**, không đụng JDK internal classes.
- Filter theo internal name để code đơn giản; production còn cần kiểm classloader/module/descriptor để tránh áp nhầm class name ở classloader khác.
- JVM trong phép kiểm cần hỗ trợ cả retransform và redefine như manifest.
- Kết quả cụ thể `UnsupportedOperationException` khi thêm field đã được test trên HotSpot OpenJDK 24.0.2; providers khác có thể có cách trả lỗi khác, nhưng structural restriction trong JVMTI vẫn phải được tôn trọng.

## 8. Java 24+ runnable demo số 2: chain, gỡ transformer và vi phạm cấu trúc

Ba source files cần ở ba đường dẫn tương ứng:
- `ChainAgent.java` và `ChainApp.java` tại thư mục chính;
- `AlternativeStructureTarget.java` tại cùng thư mục chính, **compile riêng** vào `alternative/`.

Trong `ChainApp.java` đã có **định nghĩa ban đầu** của `StructureTarget`; `AlternativeStructureTarget.java` chứa **một định nghĩa thứ hai cùng binary name** nhưng **thêm field**. Không compile cả hai vào một output directory cùng lúc.

### File ChainAgent.java

~~~java
import java.lang.classfile.ClassFile;
import java.lang.classfile.ClassTransform;
import java.lang.classfile.instruction.ConstantInstruction;
import java.lang.instrument.ClassDefinition;
import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.ProtectionDomain;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicInteger;

public final class ChainAgent {
    private static Instrumentation instrumentation;
    private static final List<String> events = new CopyOnWriteArrayList<>();
    private static ClassFileTransformer secondCapable;
    private static volatile byte[] attemptedNewStructure;

    static ClassFileTransformer stage(String id, String oldText, String newText) {
        return new ClassFileTransformer() {
            @Override
            public byte[] transform(Module module, ClassLoader loader, String name,
                    Class<?> redefining, ProtectionDomain domain, byte[] input) {
                if (!"ChainTarget".equals(name)) return null;
                events.add((redefining == null ? "load:" : "redo:") + id);
                AtomicInteger changes = new AtomicInteger();
                ClassFile classFile = ClassFile.of();
                byte[] output = classFile.transformClass(classFile.parse(input),
                        ClassTransform.transformingMethodBodies(
                                m -> m.methodName().equalsString("value"),
                                (builder, element) -> {
                                    if (element instanceof
                                            ConstantInstruction.LoadConstantInstruction ins
                                            && oldText.equals(ins.constantValue())) {
                                        builder.ldc(newText);
                                        changes.incrementAndGet();
                                    } else {
                                        builder.with(element);
                                    }
                                }));
                if (changes.get() != 1) {
                    throw new IllegalStateException(id + " expected exactly one literal");
                }
                return output;
            }
        };
    }

    private static final ClassFileTransformer STRUCTURAL =
            new ClassFileTransformer() {
                @Override
                public byte[] transform(Module module, ClassLoader loader,
                        String name, Class<?> redefining,
                        ProtectionDomain domain, byte[] original) {
                    if ("StructureTarget".equals(name)
                            && redefining != null && attemptedNewStructure != null) {
                        return attemptedNewStructure.clone();
                    }
                    return null;
                }
            };

    public static void premain(String args, Instrumentation inst) {
        instrumentation = inst;
        if (!inst.isRetransformClassesSupported()
                || !inst.isRedefineClassesSupported()) {
            throw new IllegalStateException("Both capabilities required for demonstration");
        }
        inst.addTransformer(stage("C1", "TWO", "THREE"), true);
        inst.addTransformer(stage("I1", "BASE", "ONE"), false);
        secondCapable = stage("C2", "THREE", "FOUR");
        inst.addTransformer(secondCapable, true);
        inst.addTransformer(stage("I2", "ONE", "TWO"), false);
        inst.addTransformer(STRUCTURAL, true);
    }

    public static String calls() {
        return String.join(",", events);
    }

    public static void clearCalls() {
        events.clear();
    }

    public static boolean removeC2() {
        return instrumentation.removeTransformer(secondCapable);
    }

    public static void retransform(Class<?> clazz) throws Exception {
        instrumentation.retransformClasses(clazz);
    }

    public static boolean isModifiable(Class<?> clazz) {
        return instrumentation.isModifiableClass(clazz);
    }

    public static boolean rejectedStructuralRetransform(Class<?> clazz, Path alt)
            throws Exception {
        attemptedNewStructure = Files.readAllBytes(alt);
        try {
            instrumentation.retransformClasses(clazz);
            return false;
        } catch (UnsupportedOperationException expected) {
            return true;
        } finally {
            attemptedNewStructure = null;
        }
    }

    public static boolean rejectedStructuralRedefine(Class<?> clazz, Path alt)
            throws Exception {
        byte[] replacement = Files.readAllBytes(alt);
        try {
            instrumentation.redefineClasses(new ClassDefinition(clazz, replacement));
            return false;
        } catch (UnsupportedOperationException expected) {
            return true;
        }
    }

    public static boolean removeStructural() {
        return instrumentation.removeTransformer(STRUCTURAL);
    }
}
~~~

### File ChainApp.java

~~~java
public final class ChainApp {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException("Usage: ChainApp alternative/StructureTarget.class");
        }
        ChainTarget chain = new ChainTarget();
        System.out.println("value after load: " + chain.value());
        System.out.println("load order: " + ChainAgent.calls());

        ChainAgent.clearCalls();
        ChainAgent.retransform(ChainTarget.class);
        System.out.println("value after retransform: " + chain.value());
        System.out.println("retransform callbacks: " + ChainAgent.calls());

        System.out.println("remove C2: " + ChainAgent.removeC2());
        System.out.println("value before another retransform: " + chain.value());
        ChainAgent.clearCalls();
        ChainAgent.retransform(ChainTarget.class);
        System.out.println("value after removing C2 and retransforming: " + chain.value());
        System.out.println("callbacks after C2 removed: " + ChainAgent.calls());

        StructureTarget shape = new StructureTarget();
        System.out.println("structure target modifiable: "
                + ChainAgent.isModifiable(StructureTarget.class));
        java.nio.file.Path alt = java.nio.file.Path.of(args[0]);
        System.out.println("extra field retransform rejected: "
                + ChainAgent.rejectedStructuralRetransform(StructureTarget.class, alt));
        System.out.println("extra field redefine rejected: "
                + ChainAgent.rejectedStructuralRedefine(StructureTarget.class, alt));
        System.out.println("original field count retained: "
                + (StructureTarget.class.getDeclaredFields().length == 1));
        System.out.println("original instance still works: " + (shape.read() == 7));
        System.out.println("structural transformer removed: "
                + ChainAgent.removeStructural());
    }
}

final class ChainTarget {
    String value() {
        return "BASE";
    }
}

final class StructureTarget {
    private int original = 7;

    int read() {
        return original;
    }
}
~~~

### File AlternativeStructureTarget.java — bản thay thế bị JVM từ chối

~~~java
final class StructureTarget {
    private int original = 7;
    private int added = 9; // Schema change rejected by retransform/redefine.

    int read() {
        return original;
    }
}
~~~

Chú ý: `AlternativeStructureTarget.java` chỉ là tên **source file** để phân biệt; trong file, top-level class `StructureTarget` là package-private nên Java cho phép source filename khác class name. Kết quả biên dịch nằm ở `alternative/StructureTarget.class`, **không** nằm trong JAR của application/agent.

### File CHAIN.MF

~~~text
Manifest-Version: 1.0
Premain-Class: ChainAgent
Can-Retransform-Classes: true
Can-Redefine-Classes: true

~~~

### Biên dịch và chạy

~~~bash
mkdir out24
mkdir alternative
javac --release 24 -d out24 ChainAgent.java ChainApp.java
javac --release 24 -d alternative AlternativeStructureTarget.java
jar --create --file chain-agent.jar --manifest CHAIN.MF -C out24 .
java -javaagent:chain-agent.jar -cp chain-agent.jar ChainApp alternative/StructureTarget.class
~~~

**Đặc biệt:** chỉ đưa `out24` vào agent JAR, **không** đặt `alternative/` vào classpath; nếu JVM tự load replacement `StructureTarget.class` trước phép thử thì không còn so được structural redefine của bản đã loaded. Đường dẫn variant được app dùng **để đọc bytes** qua `Files.readAllBytes`.

**Stdout chính xác** đã kiểm thử bằng OpenJDK 24.0.2, `javac --release 24`:

~~~text
value after load: FOUR
load order: load:I1,load:I2,load:C1,load:C2
value after retransform: FOUR
retransform callbacks: redo:C1,redo:C2
remove C2: true
value before another retransform: FOUR
value after removing C2 and retransforming: THREE
callbacks after C2 removed: redo:C1
structure target modifiable: true
extra field retransform rejected: true
extra field redefine rejected: true
original field count retained: true
original instance still works: true
structural transformer removed: true
~~~

### Diễn giải từng nhóm kết quả

**1. `value after load: FOUR`:** chứng minh class bytes **đã thực sự thay đổi** theo chain. Nếu chỉ ghi log callback nhưng tất cả transformers return null, method sẽ vẫn trả BASE. Ở đây Class-File API đã viết lại literal thành FOUR.

**2. `load order: load:I1,load:I2,load:C1,load:C2`:** JVM ưu tiên nhóm incapable trước capable, dù agent đăng ký C1 trước I1. Những native transformers (nếu có) nằm trong hai nhóm native theo Javadoc, nhưng demo không có native agent.

**3. `retransform callbacks: redo:C1,redo:C2`:** I1/I2 không được gọi lại. Tuy nhiên output vẫn FOUR, chứng tỏ kết quả TWO của các incapable transformations được JVM tái sử dụng, rồi C1/C2 áp tiếp.

**4. `remove C2: true` + `value before another retransform: FOUR`:** gỡ callback **không thay tức thì bytecode đang installed**. Nếu một monitoring agent đã cấy runtime hooks, chỉ remove transformer sẽ không tự xóa hooks đó.

**5. `value after removing C2 and retransforming: THREE`:** một lần retransform tiếp theo không còn C2, nên chain chỉ I1/I2 (reused) + C1. Đây là **rollback có chủ đích qua retransformation**, không phải automatic undo bởi removeTransformer.

**6. `structure target modifiable: true`:** target bình thường có thể được retransform/redefine nếu đổi method body hợp lệ. **Không** có nghĩa JVM cho phép thêm instance field.

**7. `extra field retransform rejected: true`:** capable transformer STRUCTURAL trả alternate classfile có thêm field `added` cho class đã loaded. OpenJDK từ chối structural change qua `UnsupportedOperationException`.

**8. `extra field redefine rejected: true`:** cùng alternate bytes được đưa trực tiếp vào `Instrumentation.redefineClasses(new ClassDefinition(...))` và lại bị từ chối. Capability redefine không bỏ schema restriction.

**9. `original field count retained: true` và `original instance still works: true`:** không có class schema mới được cài, reflection vẫn thấy một field, instance vẫn trả 7. JVM documentation quy định nếu operation trả lỗi, các class trong batch không bị redefine/retransform.

**10. `structural transformer removed: true`:** demo dọn transformer dùng để kiểm rejection, không đụng lớp khác hoặc làm application restart.

### Vì sao caught exception không phải bằng chứng lỗi ngẫu nhiên?

Code đã:
- Kiểm capability retransform/redefine ở `premain`;
- Kiểm `isModifiableClass(StructureTarget.class)` và nhận true;
- Cung cấp replacement class bytes được `javac` biên dịch từ class **cùng binary name**;
- Chỉ khác structure vì thêm **một instance field**;
- Catch `UnsupportedOperationException` theo API trong một phép thử có chủ đích;
- Xác nhận class/instance gốc **vẫn đúng** sau khi call bị reject.

Điều này khác với ném `ClassFormatError` vì corrupt bytes hoặc `NoClassDefFoundError` do rename class. Những lỗi đó cũng đáng kiểm trong hệ thống tooling, nhưng không nên gộp vào assertion “schema change rejected” khi nguyên nhân là bytes sai định dạng.

## 9. ClassFileTransformer.transform trả null, bytes hoặc exception

### Return null

`return null` nghĩa là transformer **không thay input class bytes**; các transformers phía sau vẫn có cơ hội xử lý. Null không có nghĩa:
- Hủy bỏ class definition;
- Từ chối nạp một class;
- Vô hiệu hóa các transformers khác;
- Tự động rollback previous transformation.

### Return byte[]

Nếu thật sự transform, tạo **một mảng bytes mới** và trả lại. Trong ví dụ 2, Class-File API parse/transform/rebuild class bytes; `builder.with(element)` giữ các elements không cần sửa. Mọi output vẫn phải có cấu trúc classfile hợp lệ và tương thích với loại operation (new load vs retransform/redefine).

### Exception từ transformer

Theo Java SE 25 `ClassFileTransformer`, nếu một transformer ném một exception không bắt, các transformers phía sau **vẫn được gọi**, và JVM vẫn thử hoàn tất load/redefine/retransform. Đối với chaining, exception đó được xử lý **tương tự return null** ở cấp callback. `IllegalClassFormatException` có tác dụng báo classfile không hợp lệ cho logging/debugging, **không phải cơ chế buộc JVM cancel mọi class load**.

**Tuy nhiên**, output bytes bị invalid bởi các transforms khác có thể làm verification/installation thất bại. Đừng dựa vào throw unchecked exception để “chặn” class vì class quá nhạy cảm. Một agent observability thường nên:
- Lọc tên class/module/loader **trước khi parse**;
- Catch/ghi lỗi nội bộ có kiểm soát và trả null nếu phải giữ an toàn application;
- Có metric `transform_failed` / `transform_skipped` với cardinality giới hạn;
- Kiểm transformed class behavior bằng tests, không tự tuyên bố thành công khi bytecode pipeline đã ném exception.

Nếu policy bắt buộc **fail closed** thì thiết kế gate ở deployment hoặc application authorization, không giả định `throw` trong transformer là enforcement.

### Same transformer instance được add nhiều lần

`Instrumentation.addTransformer` cho phép đăng ký **cùng một object transformer** nhiều lần, nhưng **được khuyến cáo không làm**. `removeTransformer(t)` loại bỏ **đăng ký matching gần nhất**, không nhất thiết “xóa toàn bộ mọi registration” nếu object đã được add lặp. Để quản lý rõ:
- Tạo các instances riêng có ID;
- Mỗi registration có lifecycle owner rõ;
- Giữ reference để remove;
- Chỉ remove khi shutdown hoặc có kế hoạch retransform/uninstrument đúng.

## 10. Remove transformer không đồng nghĩa uninstrument

~~~text
T0: TransformTarget method đang trả "FOUR" vì I1,I2,C1,C2
T1: inst.removeTransformer(C2) -> true
T2: Method gọi lại ngay vẫn trả "FOUR"
T3: inst.retransformClasses(TransformTarget.class)
T4: Method lần gọi mới trả "THREE"
~~~

Ví dụ 2 chứng minh trình tự này. Có hai điểm riêng:

**Một là bytecode đã installed không đổi khi chỉ gỡ callback.** Không có API magic `removeTransformer` tự hoàn tác mọi sự thay đổi class.

**Hai là ngay cả khi retransform, incapables có thể được JVM tái áp**. Nếu I1/I2 đã instrument một class ở lần load, retransform class với C1/C2 bị remove vẫn có thể giữ effects của I1/I2. Muốn uninstrument hoàn toàn, phải có **thiết kế biến đổi có thể đảo ngược** hoặc triển khai phiên bản mới/restart, không chỉ remove arbitrary transformers.

Javadoc còn lưu ý do concurrency của class loading, transformer có thể vẫn nhận callbacks đã in-flight **sau khi bị remove**. Nếu cleanup data structures quá sớm, callback có thể gặp state đã đóng. Thiết kế bằng reference counting/closed flags/handoff phù hợp và tránh memory leaks.

## 11. Agent thứ nhất và thứ hai có thể va chạm thế nào?

Trong thực tế ứng dụng có thể có:
- Một OpenTelemetry Java agent;
- Một coverage/test agent;
- Một profiler/monitor;
- Một agent của APM hoặc framework;
- Native JVMTI agent ngoài các Java transformers.

`-javaagent` có thể xuất hiện nhiều lần. Theo `java.lang.instrument` package specification, **`premain` được gọi theo thứ tự các agent options trên command line**. Nhưng khi các agents đăng ký transformers capable/incapable, **thứ tự transform khi class load** vẫn tuân theo **bốn nhóm**, không phải đơn giản thứ tự `-javaagent`.

### Ví dụ va chạm

Agent A:
- Chèn lời gọi `TraceHooks.begin()` ở method entry;
- Không đảm bảo loader/module thấy `TraceHooks`.

Agent B:
- Cấy metric counter vào cùng method;
- Vô tình rewrite method body bằng cách chỉ giữ các original instructions, không giữ output từ Agent A.

Khi đó output thực tế có thể:
- Mất tracing hooks của A;
- Có `NoClassDefFoundError` với helper không nhìn thấy;
- Có verifier errors nếu bytecode stacks/frames bị sai;
- Tăng allocations và CPU đáng kể;
- Ghi double spans nếu cùng một thư viện được instrument bởi hai agents.

**Không có “merge instrumentation semantics” tự động**. JVM chỉ nối byte arrays theo thứ tự. Mỗi agent phải biết bản thân có thể thấy output do agent trước, không được viết transformer như đang luôn nhận pristine classfile.

### Kỹ thuật phối hợp

- Xác định rõ **agent ordering** trong deployment, cùng capable flags.
- Định nghĩa allowlist/denylist theo classloader/module/package và tool scopes.
- Kiểm tra **class loader visibility** của helper classes.
- Tránh instrument lớp của chính exporter/logger/tracer để không recursion.
- Đảm bảo biến đổi **idempotent** và có marker/recognition phù hợp.
- Test startup mới, retransform, redefine và remove/rollback.
- Khi định nghĩa body changes, preserve instructions/exception tables/stack maps đúng.
- Dùng các bytecode APIs có mô hình toàn vẹn như Java24 `ClassFile` hoặc thư viện được hỗ trợ cho JDK mục tiêu.
- Đừng giả single-threaded transform: JVM có thể load nhiều classes đồng thời.

Nếu nhiều Java agents cùng dùng `addTransformer(...,true)`, **thứ tự đăng ký trong nhóm capable** xác định thứ tự callback; nếu một agent register capable trước nhưng agent khác register incapable sau, nhóm incapable vẫn chạy trước.

## 12. Tương tác retransformation khi class đã được một agent sửa ở lần load

### Baseline không nhất thiết là .class bytes trên disk

Javadoc mô tả retransform bắt đầu từ “initial class file bytes”, hoặc last redefine, nhưng representation có thể khác từng byte so với bytes đã nạp: constant pool entries/order, attributes hay method ordering có thể được JVM chuẩn hóa. Do đó:
- Parse bằng classfile parser tuân thủ spec, không so offset thủ công.
- Match theo **binary name + module + loader + method descriptor**, không theo constant pool index tuyệt đối.
- Không assume literal ở cùng byte offset qua lần retransform.
- Tránh copy `classfileBuffer` sang static cache rồi giữ vô thời hạn theo classloader; dễ memory leak.

### Non-capable transformer effect được giữ lại

I1/I2 có thể thêm một phép đo ở lần class load. Khi retransform, JVM tái áp effect của họ **mà không gọi callback**, rồi capable C1/C2 mới được gọi. Nếu muốn thay cấu hình của I1/I2 khi app đang chạy, chỉ đổi một biến nội bộ của incapables **không** làm effects cũ tự cập nhật qua retransform; cần thiết kế capability/lifecycle phù hợp.

### Retransform có thể fail nếu các stages không tương thích

Giả sử:
- Lần load: I1/I2 thêm một field marker để nhận diện instrumentation, class được define với field đó.
- Lần retransform: capable C1 tạo classfile **không còn field marker**.
- JVM thấy cấu trúc mới khác schema đã loaded; operation có thể bị reject.

**Cấu trúc phải ổn định trong toàn bộ pipeline retransform**, kể cả khi một transformer đơn lẻ nghĩ nó chỉ làm sạch output của transformer khác.

## 13. Redefinition: không phải compilation-and-swap vô hạn

`redefineClasses` nhận các `ClassDefinition` cung cấp classfile bytes thay thế:

~~~java
ClassDefinition replacement = new ClassDefinition(
        existingClass, newClassFileBytes);
inst.redefineClasses(replacement);
~~~

Đây là snippet trong một agent đã có `Instrumentation inst` và bytes **được tạo/kiểm chứng riêng**; không phải code độc lập. Khi định nghĩa thay thế, classfile mới phải có **cùng binary name** với target và qua verifier/JVMTI structural restrictions. Nó không được thêm field chỉ vì source Java recompilation đã thành công.

**Khác biệt quan trọng:**
- `redefineClasses` bắt đầu từ replacement bytes caller cung cấp, không chỉ từ original bytes.
- `retransformClasses` bắt đầu từ initial/last redefine bytes và pipeline transform.
- Những transformers đã đăng ký có thể tham gia define/redefine; nhóm incapable **vẫn được callback** khi redefine.
- Một class có thể có **active stack frames** đang chạy old bytecodes trong khi new method invocations dùng bytes mới.
- Class initialization **không được chạy lại**, static field values không tự reset và existing instances không tự “di trú schema”.

**Atomicity của batch:** API mô tả khi operation có lỗi, **không có class nào trong batch được retransform/redefine**. Nhưng điều này không phải transaction với toàn bộ side effects của agent callbacks/telemetry: các transformer callbacks có thể đã ghi logs/counters hoặc kích hoạt side effects trước khi JVM reject installation. Đừng dùng side effects bên trong transformer để đại diện “commit thành công” của một class change.

### Một điểm về modifiers

Đừng tuyên bố một JVM nhất định chấp nhận đổi `final` hoặc visibility của một method đang loaded. JVMTI 25 có structural constraints cả modifiers. Cần xét đặc tả đúng version và method/field modifiers, không đoán vì classfile vẫn parse được.

## 14. Active stack frames, existing instances và JIT

Khi `redefineClasses` hoặc `retransformClasses` thành công, **một method đang chạy trên stack** có thể tiếp tục chạy **old bytecodes** trong active frame, còn các calls mới sẽ chạy method version đã transform. Như vậy có thể có một khoảng chuyển tiếp nơi hai versions được thực thi đồng thời.

~~~text
t0 Thread A đang ở method work() version V1
t1 Agent retransform class, install V2
t2 Thread A tiếp tục frame work() V1
t3 Thread B gọi work() mới -> V2
t4 Thread A ra khỏi V1, future invocations -> V2
~~~

Do vậy:
- Không coi retransform thành barrier thay semantics đồng thời.
- Không dùng hot bytecode transform để thay đổi quy tắc tính tiền/authorization trong request đang chạy mà không có rollout policy.
- Không mong static fields chạy initializer mới hoặc instance fields tự được thêm.
- Tính đến JIT deoptimization, performance spikes và threads đang chạy.
- Đo lường latency/CPU/GC/tracing correctness sau transform.

Nếu cần thay đổi business class schema, hãy triển khai app version mới. Agent observability nên ưu tiên transformations **additive trong method body** và không sửa behavior của app.

## 15. Concurrency và lifecycle của transformers

### Class loading có thể xảy ra song song

Một `ClassFileTransformer` có thể được gọi trên nhiều threads và class loaders. Class `ChainAgent` demo dùng `CopyOnWriteArrayList` cho event log và `AtomicInteger` cho biến đếm cục bộ; ở production không nên log vô hạn mọi class vì memory/cardinality, và nên có bounded buffers.

### Không nạp lại chính lớp đang được instrument trong callback

Nếu code transformer làm:
- Gọi HTTP exporter;
- Khởi tạo logging framework;
- Tải class đang được transform;
- Gọi reflection lên chính class chưa define xong;

có thể sinh class circularity/`LinkageError` hoặc deadlock. Theo Javadoc ClassFileTransformer, lỗi khi resolve class có thể bị cache và gây lỗi ở những vị trí sau đó, rất khó truy hồi.

**Trong callback** nên:
- Làm quick scope check;
- Parse/transform có deterministic bounded cost;
- Không synchronous network calls;
- Không giữ lock toàn cục kéo dài;
- Không log raw class bytes/method arguments bí mật;
- Tách telemetry export ra runtime hooks với queue có giới hạn.

### Khi có nhiều ClassLoaders

Cùng một internal name `com/example/Service` có thể được define bởi nhiều loaders. Nếu filter chỉ tên, cả hai đều nhận transform dù ý định chỉ một service. Ngoài tên, kiểm:
- `ClassLoader loader` và identity/lifecycle;
- `Module module` và class domain;
- `ProtectionDomain` nếu cần policy;
- Binary name + method descriptor;
- Version classfile/JDK hỗ trợ.

Nếu agent static cache giữ strong references tới `ClassLoader` và `Class<?>`, class unloading/plugin redeploy có thể bị ngăn, gây memory leak. Dùng weak caches hoặc explicit lifecycle/cleanup.

## 16. Class-File API Java 24+ và lưu ý thiết kế composable transform

Class-File API chuẩn giúp:
- Đọc `ClassModel` và `MethodModel` có kiểu;
- Áp `ClassTransform.transformingMethodBodies(...)` chọn methods;
- Áp `CodeTransform` biến đổi `CodeElement`;
- Dùng `ClassFile.of().transformClass(...)` dựng classfile bytes mới.

Trong demo, callback thay **LoadConstantInstruction** có string value mong muốn, đồng thời pass-through những elements khác:

~~~java
ClassFile cf = ClassFile.of();
byte[] output = cf.transformClass(cf.parse(input),
        ClassTransform.transformingMethodBodies(
                m -> m.methodName().equalsString("value"),
                (builder, element) -> {
                    if (element instanceof
                            ConstantInstruction.LoadConstantInstruction literal
                            && "BASE".equals(literal.constantValue())) {
                        builder.ldc("ONE");
                    } else {
                        builder.with(element);
                    }
                }));
~~~

Đây là **snippet ở trong transformer** có imports Java24 `ClassFile`, `ClassTransform`, `ConstantInstruction` và biến `input`. Ở một chain nhiều stages, mỗi stage phải nhận output của stage trước, không cố tái parse một classfile cũ khác. Phần 8 có code runnable chính xác.

**Production correctness** đòi thêm:
- Method matching theo **descriptor**, không chỉ tên `value` (demo không có overload).
- Verify constructors, synchronized/native/abstract methods, exceptions, control-flow, stack maps và debug attributes.
- Preserve invariants: không đổi methods/fields ngoài mục đích.
- Test load và retransform sau nhiều lần apply, cả classes đã loaded trước.
- Check `ClassFile` API/bytecode target theo JDK version của application.
- Khi dùng third-party ASM/Byte Buddy trên Java 17/21, test với classfile versions mới và framework agents khác.

Class-File API không phải giấy phép để bỏ qua JVMTI constraints. `ClassFile` có thể xây một classfile có thêm field (hợp lệ khi initial load); **JVMTI vẫn có quyền từ chối** nếu muốn hot swap class đã loaded.

## 17. Testing strategy: đơn lẻ, chain, retransform, redefine và rollback

### Một matrix kiểm thử có giá trị thực tế

| Case | Kết quả mong muốn |
| --- | --- |
| Startup `-javaagent` | `premain` chạy trước app main |
| JAR thiếu `Premain-Class` | Startup fail có lỗi manifest |
| Agent chỉ quan sát, return null | Class behavior giữ nguyên |
| Add transformer false | Callback lúc load/redefine, không gọi lại lúc retransform |
| Add transformer true | Callback lúc load/redefine/retransform khi capability có |
| Đăng ký capable trước incapable | Khi load vẫn incapable trước capable |
| Hai incapables | Theo registration order trong nhóm |
| Hai capables | Theo registration order trong nhóm |
| Java vs native transformers | Theo bốn nhóm Javadoc (cần JVMTI fixture riêng) |
| I1: BASE→ONE | Stage 1 nhận original bytes |
| I2: ONE→TWO | Stage 2 thấy output I1 |
| C1: TWO→THREE | Stage 3 thấy output I2 |
| C2: THREE→FOUR | Stage 4 thấy output C1 |
| Output method sau load | FOUR |
| Retransform method | FOUR, chỉ C1/C2 callbacks |
| I1/I2 trong retransform | Không callback; effects được tái sử dụng |
| Remove C2 | Class bytes hiện tại vẫn FOUR |
| Retransform sau remove C2 | Method mới trả THREE |
| Capability false | Không gọi retransform/redefine |
| Class target not modifiable | Không thử sửa; báo unsupported |
| Redefine body-only hợp lệ | Có thể áp theo contract |
| Retransform body-only hợp lệ | Có thể áp theo contract |
| Thêm instance field vào class đã loaded | Rejected |
| Thêm static field vào class đã loaded | Rejected |
| Thêm method vào class đã loaded | Rejected |
| Đổi method signature | Rejected |
| Đổi superclass/interface hierarchy | Rejected |
| Đổi NestHost/NestMembers/Record/PermittedSubclasses | Rejected theo JVMTI 25 |
| Thay class name thành tên khác | JVM reject |
| Replacement bytes corrupt | JVM reject, không partial install |
| Redefine batch có một class invalid | Không install một phần batch |
| Existing instance sau failed structural redefinition | Giữ fields/behavior cũ |
| Existing instance sau body-only retransform | Cùng schema, body mới dùng cho call mới |
| Active stack frames khi transform | Có thể tiếp tục old bytecodes |
| Remove transformer callback đang in-flight | Không assume đã hoàn toàn ngừng |
| Same transformer object add nhiều lần | Cần quản lý registrations, tránh |
| Transformer throw exception | Các transformers sau vẫn được gọi theo Javadoc |
| Invalid bytes từ transformer giữa chain | JVM verify/redefine fail |
| ClassLoader khác nhau cùng internal name | Không instrument nhầm |
| Agent + profiler + OTel cùng JVM | Kết quả hợp lệ, không duplicate hooks |
| Runtime có virtual threads | Runtime hooks và context propagation vẫn đúng |
| Async telemetry exporter tạm hỏng | Không block class-loading thread vô hạn |
| Module access bị hạn chế | Không mở packages quá rộng |
| Agent shutdown/restart | Không leak ClassLoaders/exporters/caches |
| Performance overhead | Trong ngân sách CPU/GC/p95/p99 |

**Đừng dựa chỉ vào exit code 0.** Một transformer bị exception có thể bị xử lý như return null, ứng dụng vẫn chạy. Hãy kiểm **hành vi class method** và **callback chain** cùng nhau. Với structural failure, kiểm cả exception **và** reflection/class behavior không đổi.

### Triển khai thận trọng

- Chạy integration tests trên JDK versions và providers mục tiêu;
- Pin agent versions/checksums;
- Kiểm tương tác với framework/classloader, đặc biệt class generated/proxies;
- Đo startup time, code cache, heap, allocation, GC và request latency;
- Canary một nhóm nhỏ instances;
- Có kill switch/feature flag cho telemetry hooks, nhưng đừng coi removeTransformer là rollback toàn bộ;
- Dự phòng rollback **bằng restart với artifact/flag phù hợp**.

## 18. Lỗi thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| Callback order khác thứ tự addTransformer | Bốn nhóm group priority | Đọc ClassFileTransformer Javadoc |
| Incapable callback không được gọi lại | Retransform tái dùng result cũ | Đúng contract, không phải bug |
| Return null nhưng class không đổi | Null nghĩa no transformation | Trả bytes hợp lệ nếu muốn thay |
| Repeated callback tạo double metrics/hooks | Transform không idempotent | Marker/version guard, regression tests |
| Remove transformer nhưng method vẫn instrumented | Installed bytes không tự revert | Re-transform có kiểm chứng hoặc restart |
| Remove cùng instance add lặp chỉ gỡ một | Chỉ gỡ most recent matching registration | Dùng mỗi registration một instance |
| Transform ghi đè output của agent trước | Vi phạm composability | Transform trên input hiện tại, pass-through elements |
| Cố thêm field khi retransform | JVM schema restrictions | Chuyển dữ liệu sang external map/helper hoặc redeploy |
| Cố thêm method khi redefine | Method schema change | Không hot swap, build/redeploy |
| Class redefinition kết thúc với VerifyError | Stack map/bytecode invalid | Dùng parser/builder chuẩn và tests |
| Classfile version quá mới | JVM không hỗ trợ target | Build đúng `--release` và runtime |
| Class name mismatch | Replacement bytes của binary name khác | Compile đúng cùng binary name |
| `isModifiableClass` true nhưng redefine fail | Structural change không hợp lệ | Kiểm schema restrictions |
| `isRetransformClassesSupported` false | Manifest/runtime chưa có capability | Kiểm yêu cầu và provider |
| `ClassFormatError` | Bytes invalid | Không patch raw class bytes |
| `NoClassDefFoundError` sau instrument | Agent helper không visible | Kiểm loader/module/bootstrap helpers |
| `LinkageError` trong transformer | Recursive class loading hoặc duplicate definitions | Scope filtering và tránh side effects |
| Thay class đã loaded nhưng object cũ “thiếu field mới” | JVM đã reject schema, không migrate object | New deployment/data migration |
| Không thấy new method effect ở active frame | Old frame có thể tiếp tục old bytecodes | Chờ boundary/rollout policy |
| Class vẫn cũ sau gỡ flag mà chưa restart | JVM vẫn đang chạy old installed bytes | Restart theo deployment |
| Một instrumentation test pass, kết hợp OTel fail | Transform order/loader/proxy conflict | Multi-agent integration matrix |
| Static cache giữ classloader cũ | Strong references | Weak/lifecycle-aware cache |
| Transform callback gửi HTTP | Blocking/recursion khi class load | Bounded runtime telemetry queue |
| Agent ghi source bytes vào logs | Có thể lộ implementation/secrets | Chỉ logs tối thiểu và policy redaction |
| Native transformer khác Java | Native JVMTI grouping và ordering khác | Test riêng nếu có native agent |
| Live attach bị giới hạn | JEP 451/integrity policy | Ưu tiên startup agent được phê duyệt |
| Java17 không thấy `java.lang.classfile` | API chuẩn từ Java24 | Chọn library tương thích hoặc JDK24+ |
| Compiler báo class duplicate | Compile original và alternate cùng một directory | Compile separate outputs |
| Target alternate tình cờ nằm trong classpath | JVM load sai version từ đầu | Để variant ngoài classpath, chỉ đọc bytes |

## 19. Quy tắc thiết kế an toàn khi nhiều công cụ cùng instrument

Một pipeline observability production cần tuân thủ một số invariant:

**Tính hợp lệ classfile:** mọi stage trả well-formed classfile. Nếu stage không có thay đổi, return null. Không mutate input buffer; không copy offsets/constant pool entries bằng cách cắt chuỗi.

**Tính toàn vẹn class schema:** các stages chỉ thay method code khi retransform/redefine; giữ nguyên field/method names, descriptors, inheritance, nest/record/sealed metadata và class identity. Vi phạm sẽ fail install.

**Tính kết hợp được:** stage B luôn chấp nhận bytes sau stage A, kể cả A thêm instrumentation hooks. Không rebase ngầm về file .class trên disk rồi xóa tác động của A.

**Tính lặp lại có kiểm soát:** capable transformer có thể chạy nhiều lần. Không chèn duplicate probes, không đếm callback như request throughput, không tăng classfile size vô hạn.

**Tính khôi phục:** gỡ transformer chỉ dừng future callbacks (có thể còn in-flight), không tự undo old bytes. Muốn rollback phải biết thứ tự chain, có bản classfile phù hợp, hoặc restart an toàn.

**Không lạm dụng quyền agent:** JAR/Attach/Module Opens chạy với quyền process JVM; chỉ dùng agent đã được phê duyệt, cấu hình ít quyền, kiểm provenance, quét dependencies và telemetry egress. Không coi instrumentation là cách vượt security boundary.

**Chỉ instrumentation cần thiết:** đừng parse và instrument mọi JDK class khi target chỉ là vài framework classes. Scope filtering, sampling và bounded queues giúp giảm startup/latency overhead.

## 20. Câu hỏi tự kiểm tra

1. **ClassFileTransformer được gọi lúc nào?** Class define/load, redefine và nếu capable thì retransform.
2. **Return null làm gì?** Giữ bytes đang có, không hủy class.
3. **Return byte[] làm gì?** Đưa bytes mới vào transformer chain.
4. **Có được sửa trực tiếp classfileBuffer không?** Không.
5. **Có bao nhiêu nhóm transformer order trong Javadoc?** Bốn.
6. **Nhóm incapable Java và capable Java, nhóm nào trước khi load?** Incapable.
7. **Trong một nhóm, order dựa vào gì?** Thứ tự đăng ký.
8. **Đăng ký C1,I1,C2,I2 thì khi load có order gì?** I1,I2,C1,C2.
9. **Khi retransform, I1/I2 có được callback không?** Không nếu incapable.
10. **Effects của I1/I2 trong retransform đi đâu?** JVM tái áp kết quả trước.
11. **C1/C2 nhận bytes nào?** Output sau stages đứng trước.
12. **Nếu C2 removed, method có đổi ngay không?** Không.
13. **Khi retransform sau remove C2 trong demo, method trả gì?** THREE.
14. **Trong demo, trước khi remove C2 method trả gì?** FOUR.
15. **Có thể thêm field qua retransform class đã loaded không?** Không theo JVMTI25.
16. **Có thể thêm method qua redefine class đang chạy không?** Không theo JVMTI25.
17. **Có thể sửa method body không?** Có thể, nếu bytes/schema hợp lệ.
18. **Đổi superclass được không?** Không.
19. **Đổi method descriptor được không?** Không.
20. **Đổi NestHost/NestMembers được không?** Không.
21. **Đổi Record attribute khi hot redefine được không?** Không.
22. **Đổi PermittedSubclasses attribute được không?** Không.
23. **Classload lần đầu có thể thêm field không?** Có thể nếu classfile cuối hợp lệ.
24. **isModifiableClass true đảm bảo đổi mọi schema không?** Không.
25. **Can-Retransform-Classes xin ở đâu?** Agent JAR manifest.
26. **Can-Redefine-Classes xin ở đâu?** Manifest tương ứng.
27. **redefineClasses dùng dữ liệu gì?** ClassDefinition với replacement bytes.
28. **retransformClasses bắt đầu từ bytes nào?** Initial/last redefine representation, JVM có thể thay constant pool layout.
29. **Một batch retransform fail có partial-install không?** API quy định không.
30. **Callbacks trước failure có thể đã ghi side effects không?** Có.
31. **Static fields có tự chạy lại initializer không?** Không.
32. **Existing objects có tự được thêm field không?** Không.
33. **Active stack frames có thể chạy old code không?** Có.
34. **Cùng transformer instance đăng ký nhiều lần có nên không?** Không nên.
35. **removeTransformer gỡ registration nào nếu trùng?** Most recently added matching.
36. **Exception trong transformer có dừng chain không?** Không, theo Javadoc tiếp tục và như null.
37. **Verifier có thể reject chain output dù callback không lỗi không?** Có.
38. **ClassFile API ổn định từ Java nào?** Java24.
39. **Java17 runnable example dùng lib ngoài không?** Không.
40. **Java24 demo dùng gì để sửa constant?** ClassFile/ClassTransform/CodeTransform và ldc.
41. **Native JVMTI transformers có cùng group như Java không?** Có hai nhóm native riêng trong bốn nhóm.
42. **Thứ tự premain nhiều -javaagent có giống transformation groups không?** Không hoàn toàn.
43. **Có nên instrument bootstrap classes tùy tiện không?** Không.
44. **Có thể dùng agent để bypass quyền truy cập module tùy ý không?** Không được làm vậy.
45. **Instrument class loaders khác nhau cùng tên cần gì?** Kiểm loader/module và origin.
46. **Công cụ observability cần log raw class bytes không?** Thường không, nhạy cảm.
47. **Có thể rollback mọi instrumentation bằng removeTransformer không?** Không.
48. **Muốn thay data model thì làm thế nào?** Build/redeploy và data migration.
49. **Các agent cùng sửa method có thể va chạm không?** Có, test integration bắt buộc.
50. **Biện pháp an toàn nhất để cập nhật instrumentation trên production?** Canary, verified agent, scoped transforms, performance tests, rollback via deployment/restart.

## 21. Tài liệu chính thức, hiện hành

- [Java SE 25 — ClassFileTransformer](https://docs.oracle.com/en/java/javase/25/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): nhóm thứ tự, transform chaining, incapable/capable behavior, exception semantics.
- [Java SE 25 — Instrumentation](https://docs.oracle.com/en/java/javase/25/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): add/removeTransformer, capability checks, retransform/redefine contract, atomicity, active frames.
- [Java SE 25 — java.lang.instrument package](https://docs.oracle.com/en/java/javase/25/docs/api/java.instrument/java/lang/instrument/package-summary.html): startup agent, multi-agent manifest, premain và trách nhiệm bảo mật.
- [Java SE 25 — ClassDefinition](https://docs.oracle.com/en/java/javase/25/docs/api/java.instrument/java/lang/instrument/ClassDefinition.html): class object và replacement bytes.
- [Java SE 25 — UnmodifiableClassException](https://docs.oracle.com/en/java/javase/25/docs/api/java.instrument/java/lang/instrument/UnmodifiableClassException.html): unmodifiable class.
- [Java SE 25 — JVMTI Specification](https://docs.oracle.com/en/java/javase/25/docs/specs/jvmti.html): RedefineClasses/RetransformClasses, schema restrictions và structural changes.
- [Java SE 25 — ClassFile](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/classfile/ClassFile.html): type-safe parse/transform/serialize.
- [Java SE 25 — ClassTransform](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/classfile/ClassTransform.html): transformingMethodBodies filter/predicate.
- [Java SE 25 — CodeTransform](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/classfile/CodeTransform.html): code element processing và transform composition.
- [Java SE 25 — ConstantInstruction.LoadConstantInstruction](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/classfile/instruction/ConstantInstruction.LoadConstantInstruction.html): load constants trong method bytecode.
- [OpenJDK — JEP 484 Class-File API](https://openjdk.org/jeps/484): API chuẩn từ Java 24.
- [OpenJDK — JEP 451 Dynamic Agent Loading](https://openjdk.org/jeps/451): integrity by default và quyền dynamic attach.
- [OpenTelemetry — Java zero-code instrumentation](https://opentelemetry.io/docs/zero-code/java/agent/): ví dụ hệ sinh thái agent sử dụng transformation cho observability thực tế.

**Kết luận:** `ClassFileTransformer` có **thứ tự bốn nhóm**, và bytes từ transformer trước được truyền sang transformer sau. Khi `retransformClasses`, những transformers **không capable retransform** **không chạy callback**, nhưng hiệu ứng từ lần define/redefine trước vẫn được JVM tái sử dụng. `redefineClasses` và `retransformClasses` đều bị **giới hạn cấu trúc class**: không thêm/bớt/đổi field hoặc method, không đổi inheritance và metadata đặc biệt bị cấm, mặc dù method body transformations có thể hợp lệ. Gỡ transformer **không tự trả về bytes cũ**. Do đó một observability agent hiện đại phải chú trọng tính đúng của bytecode, composition, idempotency, capability checks, classloader isolation, performance, bảo mật và rollback qua deployment có kiểm soát.
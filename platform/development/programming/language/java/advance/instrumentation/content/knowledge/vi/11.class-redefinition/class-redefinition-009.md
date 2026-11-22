# Khôi phục mã bằng Redefinition: định nghĩa phải tương thích và vẫn chịu ảnh hưởng chuỗi transformer

## 1. Vấn đề: tại sao “nạp lại class gốc” chưa chắc là rollback?

Giả sử một Java agent đã thay method body của một class đang chạy bằng `Instrumentation.redefineClasses(...)`. Khi muốn quay về phiên bản trước, ta thường nghĩ chỉ cần lấy lại file `.class` cũ rồi gọi `redefineClasses` lần nữa. Ý tưởng này **có thể đúng**, nhưng **không đủ để bảo đảm khôi phục bytecode đang thực thi**.

Có **hai ràng buộc độc lập**:

1. **Định nghĩa thay thế phải tương thích với class đã được JVM nạp.** Redefinition thông thường cho phép sửa method bodies, constant pool và một số attributes, nhưng không cho phép thay đổi tùy tiện tên lớp, field/method schema, chữ ký, modifiers, hierarchy hoặc cấu trúc khác bị JVM/JVMTI cấm.
2. **Bytes cung cấp cho `ClassDefinition` vẫn đi qua các `ClassFileTransformer` đang được đăng ký.** Transformer có thể chèn lại tracing, thay literal hoặc biến đổi kết quả. Vì vậy **bytes đầu vào của rollback** có thể khác **bytes cuối cùng được JVM cài đặt**.

Bài học tập trung vào khả năng **khôi phục mã đã bị instrumentation/redefinition** theo cách có thể kiểm chứng: xác định chính xác bản định nghĩa cần khôi phục, kiểm tra class identity và schema, kiểm soát các transformer, quan sát kết quả runtime và có kế hoạch xử lý lỗi.

**Phạm vi phiên bản:** mã ví dụ dùng Java 17+, `java.lang.instrument` và manifest `Can-Redefine-Classes`. Redefinition là khả năng **tùy chọn của JVM**; output minh họa giả định runtime phổ biến như HotSpot có hỗ trợ capability.

## 2. Những API liên quan

### 2.1. `ClassDefinition` chứa cặp class và toàn bộ class file bytes

```java
byte[] bytes = Files.readAllBytes(pathToOldClass);
ClassDefinition definition =
        new ClassDefinition(Target.class, bytes);
```

Đoạn trên **minh họa**, chưa độc lập: cần import `java.nio.file.Files`, `java.lang.instrument.ClassDefinition` và có `Target.class` đúng class đích.

- `Target.class` là đối tượng `Class<?>` **đã được nạp**, không phải tên file.
- `bytes` là **toàn bộ nội dung class file hợp lệ** (không phải source Java, bytecode của một method hay bytes của JAR/ZIP).
- Constructor `ClassDefinition` **giữ tham chiếu mảng**; nó không copy bytes. Không sửa mảng sau khi tạo định nghĩa hoặc trong khi `redefineClasses` đang sử dụng.
- Hai class có cùng binary name nhưng được định nghĩa bởi hai loader khác nhau là **hai class identity khác nhau**. Dùng đúng `Class<?>` đích để tránh khôi phục nhầm.

### 2.2. `Instrumentation.redefineClasses` yêu cầu JVM thay định nghĩa

```java
instrumentation.redefineClasses(definition);
```

`redefineClasses(ClassDefinition...)` nhận một hoặc nhiều cặp class/bytes và thay định nghĩa của các class đang nạp, **không tự tìm file gốc**. Lời gọi cần capability đúng:

```text
Agent JAR manifest:
Can-Redefine-Classes: true

JVM:
instrumentation.isRedefineClassesSupported() == true

Class cụ thể:
instrumentation.isModifiableClass(Target.class) == true
```

Điều kiện cuối chỉ cho biết **class có thể được sửa**, không bảo đảm mọi replacement bytes đều hợp lệ.

Khi lỗi xảy ra trong một lời gọi có nhiều `ClassDefinition`, Javadoc quy định **không class nào trong tập được redefine**. Đây là atomicity của thao tác class redefinition khi thất bại, **không phải** transaction cho dữ liệu ứng dụng, cache, DB hoặc mọi frame đang chạy.

### 2.3. `removeTransformer` chỉ hủy đăng ký, không gỡ bytecode đã cài

```java
boolean removed = instrumentation.removeTransformer(transformer);
```

Lệnh này làm những yêu cầu class definition/redefinition trong tương lai không còn chuyển qua registration tương ứng. Nó **không** tự trả những class đã biến đổi về mã gốc. Một số callback vẫn có thể diễn ra sau khi remove do quá trình class loading song song.

Với nhiều agent hoặc nhiều registration, bỏ một transformer không có nghĩa mọi transformer khác cũng bị bỏ. Trong production, agent nên **chỉ quản lý transformer do chính nó sở hữu**, không tự tìm cách vô hiệu hóa agent khác.

## 3. Ba bản bytes khác nhau cần phân biệt

Để khôi phục đúng, trước tiên phải hiểu “mã gốc” mà người vận hành muốn nói là gì:

| Tầng | Ký hiệu | Ý nghĩa |
| --- | --- | --- |
| **Bản artifact gốc** | `B0` | Class file từ build/JAR chính xác trước khi instrument, chưa đi qua transformer |
| **Bản đầu vào redefine** | `Br` | Full class-file bytes được agent truyền vào `ClassDefinition` |
| **Bản JVM cài đặt** | `Beffective` | Kết quả sau khi xử lý chuỗi transformer, verify và apply |

Sơ đồ:

```text
File gốc B0
    |
    +--- agent muốn rollback, tạo Br = B0
                  |
                  v
       new ClassDefinition(Target.class, Br)
                  |
                  v
        JVM thực hiện redefineClasses
                  |
                  v
       Transformer T1 -> T2 -> ... -> Tn
                  |
                  v
       Verification / JVM restrictions
                  |
                  v
          Beffective trong JVM
```

Nếu các transformer đều trả `null` (no-op) cho lần rollback, `Beffective` có thể tương ứng `B0`. Nếu transformer còn hoạt động và cố ý chỉnh bytes, thì `Beffective = Tn(...T2(T1(B0)))` **không nhất thiết bằng** `B0`.

**Kết luận quan trọng:** “Rollback thành công” theo nghĩa `redefineClasses` **không ném exception** chỉ chứng minh JVM chấp nhận **kết quả cuối cùng sau transformations**. Nó không chứng minh đã cài chính xác artifact gốc về mặt byte-for-byte hoặc hành vi.

Ngay cả khi ngữ nghĩa đã về đúng, JVMTI/JVM có thể chuẩn hóa constant pool, attributes hoặc biểu diễn nội bộ. Để xác nhận hành vi, hãy test **observable behavior** cùng cấu hình class loader/JVM và, khi cần, kiểm tra bytes tại đúng giai đoạn transformer hoặc bằng cơ chế dump phù hợp. Không coi hash của file gốc trên đĩa là đủ chứng minh bytes đang được JVM thực thi.

## 4. Transformer chain vẫn chạy khi redefine

Theo Java SE 17 `ClassFileTransformer`:

- Khi **class load** hoặc **class redefine**, các transformer đã đăng ký được gọi trong chuỗi, trừ những trường hợp được đặc tả loại trừ như phụ thuộc của transformer.
- Với `redefineClasses`, **đầu vào của transformer đầu tiên** là `ClassDefinition.getDefinitionClassFile()`, tức bytes mà caller cung cấp.
- Transformer nào trả `null` thì không thay đổi bytes ở bước đó; transformer trả `byte[]` thì bytes mới trở thành đầu vào của transformer sau.
- Thứ tự nhóm: **Java transformers không có capability retransform**, **native không có capability**, **Java có capability**, **native có capability**; trong từng nhóm, thứ tự đăng ký được giữ.
- Tham số `canRetransform=false` **không** có nghĩa “không tham gia redefinition”. Nó chỉ ảnh hưởng cơ chế **retransformation**: ở đó kết quả cũ của nhóm không có capability được JVM tái áp mà không gọi callback.
- Với đường **redefinition**, cả transformer đã đăng ký kiểu `false` và `true` đều có thể được gọi lại.

Ví dụ hai agent:

```text
ClassDefinition chứa bytes gốc B0
                  |
                  v
T_trace (canRetransform=false)
    + thêm probe / helper call
                  |
                  v
T_security (canRetransform=true)
    + kiểm tra/sửa method body
                  |
                  v
JVM cài đặt output đã qua hai transformer
```

Nếu mục tiêu là “loại toàn bộ probe”, truyền `B0` **chưa đủ** khi `T_trace` vẫn thêm probe. Nếu muốn giữ security transform nhưng bỏ tracing, phải biết chính xác policy/ownership của hai công cụ và ảnh hưởng của thứ tự transformer.

### “Không có transformer trả bytes” khác với “không có transformer”

Một transformer có thể được gọi nhưng trả `null`. Lúc đó kết quả không đổi ở bước của nó. Vì vậy test “có callback trong rollback” chưa đủ; cần test **output và behavior**. Ngược lại, nếu vẫn có callback từ một agent khác, đó không mặc nhiên là lỗi: có thể chính sách của hệ thống yêu cầu instrumentation đó luôn tồn tại.

### Trường hợp transformer có side effects

Một transformer có thể ghi metrics, increment counters hoặc log khi redefinition chạy. Phần output bytecode có thể là no-op trong khi side effects vẫn xảy ra. Thiết kế rollback tốt phải phân biệt:

- **Trạng thái bytecode đang được cài**;
- **Trạng thái registration** của transformer;
- **Telemetry/agent state** (cache, counters, thread, helper objects, native hooks).

`redefineClasses` chỉ xử lý class definition; nó không tự hoàn tác những side effects này.

## 5. Thế nào là định nghĩa tương thích?

### 5.1. Giữ đúng class identity

`ClassDefinition(Target.class, oldBytes)` phải cung cấp class file mang **đúng tên của `Target`**. Không đưa bytes của `OtherTarget.class` vào chỉ vì cùng method signature. JVM có thể ném `NoClassDefFoundError` khi tên class file không khớp.

Nếu ứng dụng dùng hai loader cùng định nghĩa `com.example.Service`, phải ghi rõ **defining loader** của `Class<?>` đích. File `.class` được lấy từ system classpath không đương nhiên là bản gốc của class do plugin/custom loader định nghĩa.

### 5.2. Schema không được thay đổi tùy tiện

Trong JVM phổ biến, redefinition của class đã nạp chỉ chấp nhận một tập thay đổi hẹp. Những thứ cần giữ tương thích gồm:

- Tên binary và phạm vi định nghĩa class;
- Superclass và interfaces;
- Tập field, tên và descriptors;
- Tập method, tên và descriptors;
- Những modifiers/schema mà JVM TI không cho đổi;
- Các ràng buộc cấu trúc như nestmate, record, permitted subclasses, nếu có;
- Class-file version và định dạng mà JVM mục tiêu hỗ trợ;
- Bytecode hợp lệ, constant pool/stack map frames đúng và references có thể link.

Thay body method từ `return "patched";` về `return "original";` với **cùng tên/descriptor/schema** thường phù hợp. Nhưng một “bản gốc” cũ khác schema hiện tại vẫn có thể bị từ chối.

**Tình huống khó:** Một transformer **đã thêm field** ở lần class load đầu tiên. Khi gọi rollback với bytes từ JAR **không chứa field đó**, nếu transformer không thêm field trở lại ở đường redefine, kết quả cuối cùng khác schema của class JVM đã cài và có thể bị từ chối. Đây là lý do không nên nhìn riêng file gốc mà bỏ qua output transformer.

### 5.3. Không tự thêm/xóa method để “gỡ advice”

Instrument một method có Code không cho phép tự xóa method, đổi chữ ký, chuyển native/abstract thành concrete hay đổi hierarchy khi redefine. Khi muốn gỡ lời gọi tới helper, phải tạo body mới hợp lệ **trong cùng schema**; không dựa vào việc sửa danh sách method/field.

### 5.4. Định nghĩa tương thích còn phụ thuộc runtime

Một class file hợp lệ khi build có thể không hợp lệ trong JVM đang chạy nếu:

- Major version cao hơn JVM;
- Frames/control flow không được verify;
- Tên được resolve qua loader/module khác với dự kiến;
- Bootstrap/platform/module visibility khác môi trường build;
- Một agent khác thay đổi bytes theo cách làm kết quả schema không tương thích.

JVM kiểm tra **sau khi transformer chain đã chạy**. Chạy `javac` thành công là cần nhưng chưa đủ; phải kiểm tra **kết quả class file cuối cùng** và thử trên runtime mục tiêu.

## 6. Khôi phục không hoàn tác runtime state

### 6.1. Static fields và object state vẫn còn

`redefineClasses` **không tự reset static fields**, không rerun class initializer và không tạo lại instances. Nếu code đã instrument trước đó làm tăng counter hoặc ghi dữ liệu, hành vi rollback không đảo ngược những side effects đó.

```text
Version gốc:  counter = 5
Version mới:  counter tăng lên 9
Rollback body về gốc: counter vẫn = 9
```

Trong demo ở phần sau, counter tiếp tục tăng xuyên qua nhiều lượt redefine để chứng minh điều này.

### 6.2. Active stack frames có thể tiếp tục body cũ

Nếu method phiên bản trước đã có active frame trước khi JVM cài definition mới, frame đó **tiếp tục dùng bytecode cũ**. Những invocation mới dùng method body sau redefine.

Vì vậy rollback không phải “pause thế giới rồi chuyển mọi frame đang hoạt động về bản cũ”. Các long-running operations, deadlocks, worker threads hoặc lời gọi callback đang chạy có thể vẫn thực thi logic phiên bản trước một thời gian.

### 6.3. Không tạo transaction nghiệp vụ

Redefinition batch có tính all-or-nothing **nếu lời gọi thất bại**, nhưng không hoàn tác thao tác mạng, file, DB, events, cache hay side effects của các method trước khi rollback. Nếu logic mới đã làm thay đổi dữ liệu, cần cơ chế data rollback hoặc forward fix riêng.

## 7. Ví dụ Java 17: rollback bytes gốc vẫn bị transformer thay đổi

Thực nghiệm sau chứng minh **ba kết quả khác nhau**:

1. Đang chạy bản gốc: method trả `"original"`.
2. Redefine sang bản cập nhật: method trả `"updated!"`.
3. Redefine trở lại bằng **chính file gốc**, nhưng transformer còn đăng ký nên literal `"original"` bị thay thành `"filtered"`. Sau khi **gỡ transformer**, method vẫn trả `"filtered"` cho đến khi **redefine bản gốc một lần nữa**.

Để dễ kiểm tra mà không cần dependency ngoài JDK, transformer mẫu chỉ sửa **một entry `CONSTANT_Utf8`** trong constant pool của **class `Target`**. Hai literal `"original"` và `"filtered"` đều gồm **8 byte ASCII**, nên thay chúng không đổi độ dài constant pool hoặc offsets. Đây là **demo có giới hạn**, không phải thuật toán bytecode editor tổng quát; trong production nên dùng ASM/Byte Buddy hoặc Class-File API phù hợp.

### 7.1. Cấu trúc thư mục

```text
rollback-demo/
├── src/
│   ├── v1/
│   │   └── Target.java
│   ├── v2/
│   │   └── Target.java
│   ├── LiteralTransformer.java
│   ├── RollbackAgent.java
│   └── DemoApp.java
└── agent.mf
```

Hai `Target.java` có cùng binary name ở **default package**, nhưng được build vào **thư mục riêng**. Đây là chủ đích để một bản được JVM nạp, bản kia chỉ cung cấp replacement bytes.

### 7.2. `src/v1/Target.java`

```java
public final class Target {
    private static int calls;

    private Target() {
    }

    public static String value() {
        calls++;
        return "original";
    }

    public static int calls() {
        return calls;
    }
}
```

Method `value()` tăng field static rồi trả literal `original`.

### 7.3. `src/v2/Target.java`

```java
public final class Target {
    private static int calls;

    private Target() {
    }

    public static String value() {
        calls++;
        return "updated!";
    }

    public static int calls() {
        return calls;
    }
}
```

v2 giữ **nguyên tên class, field, constructor, methods, descriptors và modifiers**. Chỉ body của `value()` thay literal trả về. Cả hai phiên bản biên dịch với target Java 17.

### 7.4. `src/LiteralTransformer.java`

```java
import java.lang.instrument.ClassFileTransformer;
import java.nio.charset.StandardCharsets;
import java.security.ProtectionDomain;

public final class LiteralTransformer implements ClassFileTransformer {
    private static final byte[] FROM =
            "original".getBytes(StandardCharsets.US_ASCII);
    private static final byte[] TO =
            "filtered".getBytes(StandardCharsets.US_ASCII);

    @Override
    public byte[] transform(
            ClassLoader loader,
            String className,
            Class<?> classBeingRedefined,
            ProtectionDomain protectionDomain,
            byte[] classfileBuffer) {

        // Không sửa class khác và không sửa lần load ban đầu.
        if (!"Target".equals(className)
                || classBeingRedefined == null) {
            return null;
        }

        byte[] changed = patchConstantPool(classfileBuffer);
        if (changed != null) {
            System.out.println("[transformer] original -> filtered");
        }
        return changed;
    }

    private static byte[] patchConstantPool(byte[] source) {
        // Chỉ chấp nhận class file do javac tạo cho demo.
        if (source.length < 10
                || (source[0] & 255) != 0xCA
                || (source[1] & 255) != 0xFE
                || (source[2] & 255) != 0xBA
                || (source[3] & 255) != 0xBE) {
            throw new IllegalArgumentException("Not a class file");
        }

        int constantPoolCount = u2(source, 8);
        int offset = 10;
        byte[] output = null;

        for (int i = 1; i < constantPoolCount; i++) {
            int tag = source[offset++] & 255;

            switch (tag) {
                case 1 -> { // CONSTANT_Utf8
                    int length = u2(source, offset);
                    offset += 2;
                    if (length == FROM.length
                            && matches(source, offset, FROM)) {
                        if (output == null) {
                            output = source.clone();
                        }
                        System.arraycopy(
                                TO, 0, output, offset, TO.length);
                    }
                    offset += length;
                }
                case 3, 4, 9, 10, 11, 12, 17, 18 -> offset += 4;
                case 5, 6 -> { // Long/Double: hai index.
                    offset += 8;
                    i++;
                }
                case 7, 8, 16, 19, 20 -> offset += 2;
                case 15 -> offset += 3;
                default -> throw new IllegalArgumentException(
                        "Unsupported constant pool tag=" + tag);
            }
        }
        return output; // null nghĩa là không có thay đổi.
    }

    private static int u2(byte[] bytes, int at) {
        return ((bytes[at] & 255) << 8)
                | (bytes[at + 1] & 255);
    }

    private static boolean matches(
            byte[] bytes, int at, byte[] pattern) {
        for (int i = 0; i < pattern.length; i++) {
            if (bytes[at + i] != pattern[i]) {
                return false;
            }
        }
        return true;
    }
}
```

**Vì sao logic đúng cho demo này?**

- Transformer lọc đúng `className = "Target"` và **`classBeingRedefined != null`**: chỉ xử lý redefinition, không thay bản gốc ở lần class load đầu.
- Transformer mới được đăng ký trong `premain`, trước khi ứng dụng chạy, và được gọi trên các lượt `redefineClasses`.
- `patchConstantPool` duyệt **constant pool** có cấu trúc, chỉ thay một `CONSTANT_Utf8` chính xác bằng byte ASCII cùng độ dài. Nếu không thấy `original`, trả `null`.
- Không sửa `classfileBuffer` tại chỗ; output được `clone` trước khi thay.
- Parser chỉ phục vụ classfile hợp lệ từ `javac --release 17`, không có bounds-check tổng quát; không dùng trực tiếp cho class file không tin cậy hoặc classfile version tương lai.
- Đối với file v2 chỉ có literal `updated!`, transformer không thấy `original` nên trả `null`: body v2 giữ nguyên.
- Đối với file v1 được đưa vào rollback, transformer nhìn thấy `original` trong bytes đầu vào và trả bytes mới chứa `filtered`.

**Không dùng lambda cho `ClassFileTransformer`** trên Java 17: interface có hai overload default và không phải functional interface.

### 7.5. `src/RollbackAgent.java`

```java
import java.lang.instrument.ClassDefinition;
import java.lang.instrument.Instrumentation;
import java.nio.file.Files;
import java.nio.file.Path;

public final class RollbackAgent {
    private static final LiteralTransformer TRANSFORMER =
            new LiteralTransformer();
    private static volatile Instrumentation inst;

    private RollbackAgent() {
    }

    public static void premain(
            String agentArgs, Instrumentation instrumentation) {
        inst = instrumentation;
        instrumentation.addTransformer(TRANSFORMER, false);

        System.out.println("[agent] supported="
                + instrumentation.isRedefineClassesSupported());
    }

    public static boolean ready() {
        Instrumentation instrumentation = inst;
        return instrumentation != null
                && instrumentation.isRedefineClassesSupported()
                && instrumentation.isModifiableClass(Target.class);
    }

    public static void redefine(Path file, String label)
            throws Exception {
        Instrumentation instrumentation = inst;
        if (instrumentation == null) {
            throw new IllegalStateException("Agent not initialized");
        }

        byte[] bytes = Files.readAllBytes(file);
        ClassDefinition definition =
                new ClassDefinition(Target.class, bytes);
        instrumentation.redefineClasses(definition);

        System.out.println("[agent] applied=" + label);
    }

    public static void removeOwnTransformer() {
        boolean removed = inst.removeTransformer(TRANSFORMER);
        System.out.println("[agent] removed=" + removed);
    }
}
```

`Can-Redefine-Classes` là capability cần thiết, còn transformer được đăng ký với `canRetransform=false`. **Vẫn nhận callback khi redefine**: đây chính là phần trọng tâm của ví dụ.

### 7.6. `src/DemoApp.java`

```java
import java.nio.file.Path;

public final class DemoApp {
    private DemoApp() {
    }

    private static void show(String label) {
        System.out.println("[main] " + label + "="
                + Target.value()
                + " calls=" + Target.calls());
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "Usage: DemoApp <baseline.class> <updated.class>");
        }

        // Target được nạp từ app.jar và chưa bị transformer sửa.
        show("initial");

        if (!RollbackAgent.ready()) {
            System.out.println("[main] skipped: unsupported");
            return;
        }

        // Cài bản có literal updated!.
        RollbackAgent.redefine(Path.of(args[1]), "update");
        show("updated");

        // Đưa file gốc vào, nhưng transformer vẫn hoạt động.
        RollbackAgent.redefine(Path.of(args[0]), "rollback");
        show("afterRollback");

        // Bỏ registration không đổi code đã cài.
        RollbackAgent.removeOwnTransformer();
        show("afterRemove");

        // Đưa file gốc lần nữa, lần này không qua transformer.
        RollbackAgent.redefine(Path.of(args[0]), "clean");
        show("restored");
    }
}
```

`show` vừa gọi method `Target.value()` vừa đọc static counter. Counter làm rõ rằng redefinition **không reset state**.

### 7.7. `agent.mf`

```text
Manifest-Version: 1.0
Premain-Class: RollbackAgent
Can-Redefine-Classes: true

```

Manifest phải nằm trong **agent JAR** do `-javaagent` nạp, thuộc tính `Can-Redefine-Classes` phải ở **main section**, kết thúc bằng dòng trống. Không cần `Can-Retransform-Classes` trong ví dụ này vì ta chỉ dùng **redefine**, không gọi `retransformClasses`.

### 7.8. Biên dịch, đóng gói, chạy (Linux/macOS/WSL)

Mở terminal tại thư mục `rollback-demo/`:

```bash
mkdir -p build/v1 build/v2

# Biên dịch hai class cùng tên theo hai artifact tách biệt.
javac --release 17 -d build/v1 src/v1/Target.java
javac --release 17 -d build/v2 src/v2/Target.java

# App và agent được compile chỉ với class v1 trên classpath.
javac --release 17 -cp build/v1 -d build/v1 \
  src/LiteralTransformer.java src/RollbackAgent.java src/DemoApp.java

# Agent JAR chỉ chứa code agent + manifest.
jar --create --file agent.jar --manifest agent.mf \
  -C build/v1 RollbackAgent.class -C build/v1 LiteralTransformer.class

# App JAR chỉ có Target v1 và DemoApp, KHÔNG có Target v2.
jar --create --file app.jar \
  -C build/v1 Target.class -C build/v1 DemoApp.class

java -javaagent:agent.jar -cp "agent.jar:app.jar" \
  DemoApp build/v1/Target.class build/v2/Target.class
```

**Stdout kỳ vọng khi JVM cấp redefinition capability:**

```text
[agent] supported=true
[main] initial=original calls=1
[agent] applied=update
[main] updated=updated! calls=2
[transformer] original -> filtered
[agent] applied=rollback
[main] afterRollback=filtered calls=3
[agent] removed=true
[main] afterRemove=filtered calls=4
[agent] applied=clean
[main] restored=original calls=5
```

Diễn giải:

1. Lúc load ban đầu, transformer nhận callback với `classBeingRedefined == null` và không sửa bytes, nên nhận `original`.
2. Đưa bản v2 vào `ClassDefinition` làm method trả `updated!`. Transformer được gọi nhưng không sửa vì không gặp literal `original`.
3. Đưa **chính v1 bytes** để rollback. Transformer **vẫn chạy trên đường redefine** dù `canRetransform=false` và thay literal thành `filtered`. JVM cài kết quả này, không phải giá trị nguyên trạng của v1.
4. `removeTransformer` trả `true` nhưng method vẫn trả `filtered`; registration thay đổi, không phải definition hiện tại.
5. Redefine thêm một lần bằng v1 bytes **sau khi remove** thì method trả `original` trở lại. Counter vẫn tăng tới 5, không bị reset.

Với JVM không hỗ trợ, `ready()` trả `false`, chương trình in `[main] skipped: unsupported` rồi kết thúc sau dòng `initial`. **Không khẳng định rollback đã chạy** trong tình huống đó.

### 7.9. Windows PowerShell

Dùng `;` thay dấu `:` trong classpath:

```powershell
New-Item -ItemType Directory -Force build/v1, build/v2 | Out-Null

javac --release 17 -d build/v1 src/v1/Target.java
javac --release 17 -d build/v2 src/v2/Target.java
javac --release 17 -cp build/v1 -d build/v1 src/LiteralTransformer.java src/RollbackAgent.java src/DemoApp.java

jar --create --file agent.jar --manifest agent.mf -C build/v1 RollbackAgent.class -C build/v1 LiteralTransformer.class
jar --create --file app.jar -C build/v1 Target.class -C build/v1 DemoApp.class

java -javaagent:agent.jar -cp "agent.jar;app.jar" DemoApp build/v1/Target.class build/v2/Target.class
```

Chạy ở đúng thư mục chứa manifest và các JAR để đường dẫn tương đối khớp.

### 7.10. Phạm vi kỹ thuật của ví dụ

- Không có custom class loader hoặc agent khác, nên sau khi `removeTransformer`, redefinition cuối không đi qua một transformer **khác**. Ở production, điều này không thể giả định.
- Bộ sửa literal chỉ dành cho constant-pool UTF8 ASCII cùng độ dài; không thích hợp cho instrument method phức tạp, constant-pool UTF8 độ dài khác hoặc class file malformed.
- Các class v1/v2 giữ nguyên **schema**; nếu tự thêm field/method trong v2 rồi thử, JVM có thể từ chối ngay lúc `redefineClasses`.
- `ClassDefinition` chứa bytes bản v1/v2 trên đĩa. Bytes trong callback của transformer trước khi JVM cài có thể bị biến đổi, nên ý nghĩa của checksum cần gắn với **giai đoạn**.
- Không gọi `getAllLoadedClasses()` hay redefine tất cả class; ví dụ chủ động nhắm một class của ứng dụng.

## 8. Phân biệt restore bằng redefine và retransform

| Tiêu chí | `redefineClasses` để restore | `retransformClasses` sau khi thay cấu hình transformer |
| --- | --- | --- |
| Đầu vào | Caller **cung cấp full class-file bytes** qua `ClassDefinition` | JVM lấy bytes nền của lần define/redefine gần nhất |
| Capability | `Can-Redefine-Classes` và `isRedefineClassesSupported` | `Can-Retransform-Classes` và `isRetransformClassesSupported` |
| Transformer `canRetransform=false` | **Được gọi khi redefine** nếu còn đăng ký | **Không gọi lại**, JVM áp dụng kết quả đã ghi từ lần load/redefine trước |
| Transformer `canRetransform=true` | Được gọi khi redefine | Được gọi lại |
| Dễ chọn chính xác bản artifact cũ? | Có, nếu caller lưu bytes hợp lệ và biết target identity | Không tự quyết định file gốc nào dùng; dựa trên bytes nền JVM lưu |
| Có tự động reset object/static state? | Không | Không |
| Có tự động gỡ instrumentation khi remove transformer? | Không | Không; cần gọi API thích hợp và hiểu pipeline |
| Vấn đề lớn nhất | Schema compatibility và transformer chain vẫn chạy | Bytes nền có thể đã qua redefine, kết quả transformer không hỗ trợ retransform còn được áp lại |

**Bẫy khi đổi từ redefine sang retransform để “rollback nhanh”:** Nếu class từng được redefine bằng bản v2, **bytes nền cho lần retransform sau đó gắn với lần redefine gần nhất**, không tự quay về artifact ban đầu. Và biến đổi của các transformer `canRetransform=false` từ lần trước có thể được reuse. Không nên dùng `retransformClasses(Target.class)` như một “undo” tổng quát.

## 9. Quy trình khôi phục có kiểm soát trong hệ thống thật

### Bước 1 — Xác định mục tiêu rollback

Trước khi thay đổi, định nghĩa rõ cần khôi phục cái gì:

- **Behavior:** method trả kết quả/ghi event giống bản trước.
- **Bytecode policy:** gỡ probe của agent A nhưng giữ policy bảo mật của agent B.
- **Full effective definition:** trở về trạng thái code thực thi cũ, bao gồm các biến đổi có chủ đích.
- **Runtime/data state:** cần migration hoặc compensation ngoài class redefinition.

Các mục tiêu này **không hoàn toàn tương đương**. Trả lại body cũ không tự dọn thread-local, metrics, static caches hoặc data trong DB.

### Bước 2 — Lưu “bản phục hồi” trước khi can thiệp

Lưu ít nhất:

- **Exact artifact/version** với checksum và đường dẫn đáng tin.
- Binary name và **defining class loader identity**, module/layer nếu liên quan.
- Class-file major version, schema fingerprint của field/method descriptors và hierarchy.
- Transformer ownership và danh sách **cấu hình** có ảnh hưởng output.
- Thời điểm build và những điều kiện JVM/JDK liên quan.

Nếu muốn phục hồi một **effective definition** đã instrument, chỉ lưu file `.class` từ JAR nguồn **có thể chưa đủ**. Cần thiết kế cách tái dựng output của pipeline hoặc bảo đảm transformer sẽ sinh ra đúng output mục tiêu.

### Bước 3 — Kiểm tra capability và target

```java
if (!inst.isRedefineClassesSupported()
        || !inst.isModifiableClass(targetClass)) {
    throw new IllegalStateException(
            "Redefinition is not available for target");
}
```

Đây là **helper minh họa**; `inst` và `targetClass` do agent thực tế cung cấp. Nếu thiếu capability, **không** cố thay bằng tải một class cùng tên trong loader mới rồi tuyên bố đã khôi phục class cũ.

### Bước 4 — Verify replacement trước khi cài

Kiểm tra:

1. Bytes có đúng format `CAFEBABE`, class name và major version không?
2. Fields/methods/hierarchy và modifiers có giữ schema phù hợp runtime không?
3. Class references có resolve được từ **đúng loader/module** không?
4. Khi đưa qua transformer chain, output cuối có còn tương thích không?
5. Bytecode/frame/exception handlers có hợp lệ không?
6. Nếu thay nhiều class cùng lượt, các class tương tác nhau thế nào?

Trong môi trường phức tạp, thực hiện thử trên JVM staging có cùng agent chain và class-loader topology; **verify bytes tại build time thôi là chưa đủ**.

### Bước 5 — Quản lý transformer theo chính sách

Lựa chọn phù hợp có thể là:

- **Giữ transformer** và chấp nhận rằng bản khôi phục vẫn có tracing/security instrumentation.
- **Chỉnh cấu hình transformer do mình sở hữu** để nó no-op đối với class mục tiêu, rồi chạy redefine.
- **Remove transformer do mình sở hữu** nếu có thể, nhưng hiểu rõ nó **không gỡ những biến đổi đã cài**.
- **Phối hợp với agent khác** theo API/lifecycle chính thức thay vì tự sửa registration không thuộc quyền kiểm soát.

Không giả định có thể “tháo hết mọi transformer”: JVM không cung cấp một API công khai đơn giản để liệt kê/vô hiệu hóa tùy tiện transformer thuộc mọi agent. Mọi thay đổi lifecycle cần kiểm tra thread-safety và thời gian callback còn đang chạy.

### Bước 6 — Thực hiện redefine trong phạm vi nhỏ

Dùng `ClassDefinition` cho từng class chính xác. Với những class phụ thuộc chặt, có thể dùng **một batch** để tránh tình huống một lời gọi thất bại sau khi các lời gọi trước đó đã cài một phần.

Cần hiểu: một batch đảm bảo **không có redefine thành công một phần nếu lời gọi đó ném exception**, nhưng không tự tạo barrier cho tất cả application threads hoặc transaction cho hiệu ứng nghiệp vụ.

### Bước 7 — Xác minh kết quả thực thi

Sau khi thành công, kiểm tra các hành vi có thể quan sát:

- Invocation **mới** dùng behavior mục tiêu;
- Các object đã tồn tại vẫn hợp lệ;
- Static fields/state không bị reset ngoài ý muốn;
- Tracing/profiling/security hooks được giữ hoặc bỏ đúng policy;
- Không có `VerifyError`, `LinkageError`, class loader leak hoặc deadlock;
- Threads có active frames cũ được xử lý an toàn.

Tùy hệ thống, có thể cần readiness probe, synthetic transaction hoặc môi trường canary trước khi bật traffic lại.

### Bước 8 — Có đường phục hồi nếu thất bại

Nếu rollback thất bại, đừng tiếp tục ghi chồng nhiều lần theo suy đoán. Lưu stack trace, class identity, artifact checksums và transformer configuration. Có thể:

- Dừng rollout và giữ nguyên version đang chạy;
- Thử bản bytes đã được test trong đúng environment;
- Chuyển sang **forward fix** nếu khôi phục schema cũ không được JVM chấp nhận;
- Khởi động lại JVM/rollout lại artifact cũ nếu cần reset trạng thái và cô lập agent chain.

Restart cũng không tự rollback dữ liệu bên ngoài JVM, nên cần kế hoạch state/data riêng.

## 10. Những lỗi dễ gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Gọi `removeTransformer` rồi method vẫn chạy code instrumented | Remove chỉ dừng callback tương lai, không thay definition hiện tại | Redefine/retransform có kiểm soát hoặc restart tùy mục tiêu |
| Gọi `redefineClasses` với file gốc nhưng vẫn thấy hook | Transformer còn đăng ký, lại biến đổi bytes rollback | Kiểm tra chuỗi transformer, ownership và policy của mỗi bước |
| Transformer `canRetransform=false` vẫn được gọi lúc rollback | Tham số này chi phối **retransformation**, không loại trừ **redefinition** | Phân biệt rõ hai API |
| `isRedefineClassesSupported() == false` | Agent thiếu manifest `Can-Redefine-Classes: true` hoặc JVM không hỗ trợ | Kiểm tra agent JAR thật và runtime |
| `UnmodifiableClassException` | Target không modifiable | Kiểm tra `isModifiableClass` từng class |
| `UnsupportedOperationException` | Capability thiếu hoặc replacement đổi schema/modifier không được hỗ trợ | Giữ schema, đối chiếu JVMTI và runtime |
| `NoClassDefFoundError` ngay lúc redefine | Tên class trong bytes khác class identity đích | Đọc đúng classfile, đúng binary name và loader |
| `ClassFormatError`/`VerifyError` | Bytes lỗi, frames/stack/constant pool không hợp lệ sau transformer | Verify output cuối, sử dụng bytecode library phù hợp |
| `UnsupportedClassVersionError` | Replacement build cho JDK quá mới | Build bằng target phù hợp, ví dụ `--release 17` |
| Method còn dùng logic cũ dù restore thành công | Có active frames từ trước lần redefine | Kiểm tra invocation mới; không suy từ frame đang chạy |
| Static state không trở về bản cũ | Redefinition không rerun `<clinit>` hay reset fields | Data/state migration hoặc restart có kế hoạch |
| Plugin bị ảnh hưởng nhầm | Có cùng class name ở nhiều loader | Dùng đúng `Class<?>`/defining loader/module |
| Rollback thất bại sau một load-time transformer thêm field | Bytes gốc không tương thích schema effective hiện tại | Bảo đảm transformer tái tạo schema tương thích hoặc cần cách phục hồi khác |
| Gỡ một agent nhưng hiệu ứng vẫn tồn tại | Nhiều transformer/native hooks hoặc helper state còn hoạt động | Xác định chính xác ownership và thứ tự pipeline |
| Gọi retransform rồi tưởng đã quay về artifact ban đầu | JVM dùng bytes nền của load/redefine gần nhất, reuse output transformer `false` | Dùng đúng cơ chế/bytes muốn restore; test kết quả |

## 11. Bộ kiểm thử nên có cho rollback

### 11.1. Kiểm thử schema

- Cùng class name và class loader target;
- Cùng field/method descriptors, modifiers, superclass và interfaces trong giới hạn JVM;
- Không chèn/xóa field hoặc method khi JVM không cho phép;
- Replacement class-file version tương thích;
- Classfile cuối sau transformer được verify.

### 11.2. Kiểm thử pipeline

- Không có transformer khác;
- Một transformer của mình còn đăng ký;
- Hai transformer cùng sửa một method theo thứ tự khác nhau;
- Một transformer trả `null`, một transformer tạo bytecode mới;
- Transformer `canRetransform=false` trong đường **redefine**;
- Sau `removeTransformer`, code cũ vẫn còn cho tới lần cập nhật definition tiếp theo;
- Nếu dùng `retransformClasses`, kiểm tra reuse của transformer `false` và bytes nền gần nhất.

### 11.3. Kiểm thử runtime

- Method invocation mới nhận đúng behavior cũ;
- Static counter/object state không reset ngoài ý muốn;
- Method đang có active frame hoàn thành theo semantics tương ứng;
- Exception paths, lock/synchronization và interface dispatch không bị phá;
- Callback của agent có tính repeat-safe, không nhân đôi hook không chủ đích;
- Khi batch redefine thất bại, kiểm tra không class nào trong batch đã đổi;
- Xác nhận rollback ở production-like JVM, đúng agent JAR và cấu hình.

### 11.4. Hạn chế điều có thể kết luận

Một test `redefineClasses` trả về bình thường chứng minh **lời gọi thành công**, nhưng không chứng minh runtime data được hoàn tác. Một test method trả chuỗi mong đợi chứng minh behavior ở đường thử, nhưng không chứng minh mọi method khác hoặc active frames đều đã dùng phiên bản mong muốn. Nên viết điều kiện thành công theo **mục tiêu rollback cụ thể**, không chỉ một boolean.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Lấy lại byte array của file gốc rồi `redefineClasses` có luôn khôi phục bytecode nguyên trạng không?

**Đáp án:** Không. Bytes đầu vào tiếp tục đi qua transformer chain; kết quả cuối có thể khác. Replacement còn phải tương thích schema/class identity và được VM chấp nhận.

**Câu 2.** Transformer đăng ký `addTransformer(transformer, false)` có được gọi khi `redefineClasses` chạy không?

**Đáp án:** Có. `false` chỉ liên quan capability **retransformation**; transformer vẫn có thể được gọi lúc load/redefine.

**Câu 3.** `removeTransformer` trả `true` có xóa probe đã chèn trước đó không?

**Đáp án:** Không. Nó hủy registration, không tự cài lại class definition khác.

**Câu 4.** Nếu bytes bản gốc thiếu một field đã được transformer thêm trong class definition hiện tại, rollback chắc chắn thành công không?

**Đáp án:** Không. Nếu output sau tất cả transformer làm schema khác definition JVM đang chấp nhận, redefine có thể bị từ chối.

**Câu 5.** Lời gọi redefine lại body cũ có tự reset các instance và static fields không?

**Đáp án:** Không. Các object/state hiện có tiếp tục tồn tại; active frames có thể còn chạy bytecode của definition trước.

**Câu 6.** Tại sao `retransformClasses(Target.class)` không phải lệnh “undo” tổng quát?

**Đáp án:** Nó chạy từ bytes nền của lần load hoặc redefine gần nhất, tái áp kết quả của transformer `false` và gọi lại transformer `true`; không tự lấy artifact cũ trước mọi lần redefine.

**Câu 7.** Khi rollback batch A và B ném exception, A có bị thay một nửa không?

**Đáp án:** Theo hợp đồng `redefineClasses`, không class nào trong batch được redefine nếu lời gọi ném exception. Nhưng side effects đã xảy ra trước đó và dữ liệu ứng dụng không được transaction hóa bởi API.

## 13. Tài liệu chính thức

- [Oracle Java SE 17 — `Instrumentation`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `redefineClasses`, `retransformClasses`, `removeTransformer`, capability, class state và active frames.
- [Oracle Java SE 17 — `ClassDefinition`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassDefinition.html): cặp `Class<?>` và full class-file bytes; constructor không copy buffer.
- [Oracle Java SE 17 — `ClassFileTransformer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): transformer luôn tham gia redefinition nếu đăng ký, thứ tự chuỗi, `return null`, giới hạn schema.
- [Oracle Java SE 17 — `java.lang.instrument` package](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html): manifest `Premain-Class`, `Can-Redefine-Classes` và cách khởi động agent.
- [Oracle Java SE 17 — JVM TI `RedefineClasses`/`RetransformClasses`](https://docs.oracle.com/en/java/javase/17/docs/specs/jvmti.html): giới hạn class file và semantics JVM.
- [Java Virtual Machine Specification SE 17 — Class File Format](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html): cấu trúc constant pool và binary classfile cần cho phép biến đổi.

**Ghi nhớ:** Khôi phục mã bằng `redefineClasses` cần **(1) bytes cũ tương thích chính xác với class đang nạp** và **(2) kiểm soát hoặc hiểu đầy đủ transformer chain**. `ClassDefinition` cung cấp input, **không bảo đảm output cuối vẫn nguyên trạng**. Gỡ transformer không tự undo, static state và active frames không reset, và một rollback đáng tin phải được kiểm thử ở cả bytecode, behavior lẫn runtime lifecycle.

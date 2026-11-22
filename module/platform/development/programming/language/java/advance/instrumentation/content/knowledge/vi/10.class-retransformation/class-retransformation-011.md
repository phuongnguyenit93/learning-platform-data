# Trường static, đối tượng hiện hữu và class initializer không được khởi tạo lại

**Khi dùng `Instrumentation.retransformClasses(...)`, JVM có thể thay đổi bytecode của một lớp đã nạp nhưng không tự khởi động lại lớp đó.** Những trường `static` đã có giá trị giữ nguyên giá trị hiện tại; những instance đang tồn tại không bị tạo lại hoặc chạy lại constructor; và class initializer `<clinit>` của lớp đã initialized **không được gọi lần nữa chỉ vì retransformation**.

Ngược lại, **các lần gọi method mới có thể chạy bytecode mới ngay trên object cũ**. Hai sự thật này phải được hiểu cùng nhau: retransformation chủ yếu cập nhật **định nghĩa code**, không tự migrate **dữ liệu runtime**. Nếu một method V2 giả định các static caches và instance fields đã được initializer V2 thiết lập, method đó có thể hoạt động sai trên dữ liệu được tạo bởi V1 dù JVM đã chấp nhận bytecode.

Bài Knowledge thuộc chủ đề **Retransformation** trong Java Instrumentation, giải thích sự khác biệt giữa thay code và reset state, ngữ nghĩa static/constructor/`<clinit>`, active stack frames, giới hạn class schema và một chương trình Java 17+ để kiểm chứng các nhận định bằng output.

## 1. Quy tắc theo Java Instrumentation API

Javadoc của `java.lang.instrument.Instrumentation.retransformClasses` nêu rõ:

- Retransformation xử lý lại class bytes qua chuỗi transformer phù hợp và thử cài định nghĩa hợp lệ mới.
- **Initializers không được chạy chỉ vì định nghĩa được thay**. Ngoại lệ duy nhất là quá trình khởi tạo thông thường mà ngữ nghĩa JVM vốn yêu cầu; bản thân `retransformClasses` không phải trigger “reset class”.
- **Giá trị static variables được giữ như trước lời gọi**, nếu không có code khác chủ động thay đổi trong lúc đó.
- **Existing instances không được dựng lại và không tự reset fields**.
- Khi một method đang có **active stack frame**, frame ấy tiếp tục thực thi bytecode cũ; **new invokes** sẽ dùng định nghĩa method mới.
- Nếu `retransformClasses` ném exception, không class nào trong nhóm classes được yêu cầu được cài lại theo hợp đồng API.

Đừng diễn giải câu “instances of the retransformed class are not affected” thành “instance cũ vĩnh viễn chỉ chạy code cũ”. Nó nói đến **object identity và dữ liệu của object**; lời gọi mới trên chính object ấy có thể thực thi body đã cập nhật.

### Bảng kết quả trước và sau

| Thành phần | Sau retransformation thành công | Ý nghĩa |
|---|---|---|
| Identity của class, defining class loader | Không tự sinh một class khác với identity mới | Vẫn là class được nạp đó |
| `static int counter` | Giữ giá trị hiện tại | Không chạy lại assignment trong `<clinit>` |
| `static final Config CONFIG` | Tham chiếu tới object đã có không tự đổi | Không xây lại singleton/cache |
| `static final String VERSION = "V1"` | Không reset/reinitialize theo source V2 | Còn có thể bị inline trong caller |
| `<clinit>` của class đã initialized | Không chạy lại | Static initializer V2 không được thực thi chỉ nhờ retransform |
| Instance hiện hữu | Cùng object và instance-field values | Không cấp phát/khởi tạo lại |
| Constructor/instance initializer của object cũ | Không chạy lại | Không có migration tự động |
| Object **tạo mới** sau retransform | Chạy constructor của định nghĩa class hiện hành | Có thể mang instance values theo V2 |
| Method call **mới** | Có thể chạy body V2 | Object cũ vẫn nhận behavior mới |
| Method đang chạy dở | Active frame tiếp tục body V1 | Các request giao thời có thể thấy V1 và V2 |

**Giới hạn:** Bảng nói về tác dụng tự động của **thao tác retransformation**. Một thread ứng dụng vẫn có thể thay field bình thường; method V2 sau này có thể chủ động cập nhật static state hoặc object fields. Không có cam kết “đóng băng dữ liệu mãi mãi”.

## 2. Đừng nhầm loading, linking, initialization và retransformation

JVM có các bước liên quan nhưng khác nhau:

```text
Class bytes --> Loading / defining class
                    |
                    v
             Linking (verify, prepare, resolve theo quy tắc)
                    |
                    v
              Initialization khi có trigger bình thường
              - static field initializers
              - static initializer blocks
              - class initialization routine / <clinit>
                    |
                    v
             Class đã initialized và đang hoạt động
             static fields + object graph + active threads
                    |
                    v
        Instrumentation.retransformClasses(...)
              chạy lại các bước transformer phù hợp
              JVM kiểm tra và cài định nghĩa class mới
                    |
                    v
       Method mới có thể dùng body mới
       static state + object cũ + <clinit> cũ: KHÔNG RESET
```

Theo Java Language Specification, class initialization xảy ra khi có trigger như tạo instance, gọi static method, gán static field hoặc đọc một static field không phải constant variable; còn có một số thao tác reflection. Việc tải một class không nhất thiết khởi tạo nó ngay. `Class.forName(name, false, loader)` minh họa trường hợp có thể load mà chưa initialize.

### `<clinit>` thực hiện việc gì?

Ví dụ:

```java
public final class Registry {
    static int starts = 0;
    static String label;

    static {
        starts++;
        label = "INITIAL";
    }
}
```

Đối với class initialized theo source này, `starts == 1` và `label == "INITIAL"`. Compiler biểu diễn static initialization theo cơ chế class initialization của JVM (thường bằng method đặc biệt `<clinit>()V`). Một bản class V2 có static block mới không khiến `starts` tăng lần nữa chỉ vì class cũ được retransform.

**Trường hợp class mới chỉ load nhưng chưa initialize:** Retransformation không tự gọi initializer thay cho trigger thông thường. Khi class được sử dụng theo cách bắt buộc initialize về sau, JVM thực hiện initialization theo ngữ nghĩa bình thường. Vì thế không đồng nhất “không *khởi tạo lại* class đã initialized” với “mọi class từng load đều đã initialized”.

### Constructor `<init>` khác `<clinit>`

- `<clinit>` liên quan class initialization và static variables.
- `<init>` là constructor path khi tạo instance; instance field initializers/instance initializer blocks thường được compiler đưa vào constructor code.
- Retransformation không làm `new` đối với các object cũ, không chạy lại `<init>` trên chúng.
- Object **mới** tạo sau khi cài body V2 có thể chạy constructor body V2 và nhận instance data mới.

Một initializer không chạy lại **không** có nghĩa nội dung của method đã được giữ nguyên: body mới có thể được cài vào định nghĩa nhưng không được JVM tự invoke tại thời điểm retransform.

## 3. Ví dụ suy luận: code V2, dữ liệu V1

Giả sử V1 khởi tạo một cache và một session:

```text
static CACHE -> map#A { "user-1": profileV1 }
static SEQUENCE = 91

session#S:
  attempts = 4
  status = "READY"
  client -> client#C
```

Sau retransform `SessionService` để thêm tracing vào `handle()`:

```text
static CACHE -> vẫn là map#A
static SEQUENCE -> vẫn 91 nếu không thread nào cập nhật
session#S -> vẫn là object đó
  attempts = 4
  status = "READY"
  client -> client#C

handle() method body -> V2 cho lời gọi mới
```

Nếu `handle()` V2 chỉ bổ sung probe và dùng lại fields V1, thay đổi có thể an toàn. Nhưng nếu `handle()` V2 mong `CACHE` có schema V2 do một static initializer mới tạo, giả định đó sai.

**Không có thao tác tự động nào trong `retransformClasses` làm:**
- gọi `CACHE.clear()`;
- tạo lại singleton, worker pool hoặc DB connection;
- chạy constructor trên tất cả instances đã tồn tại;
- viết lại fields của object cũ;
- biên dịch lại những class khác đã inline hằng số.

Nếu muốn làm các việc đó, cần một đường quản lý state/triển khai riêng và xem xét concurrency/rollback.

## 4. Giữ nguyên static fields: hai trường hợp đặc biệt

### 4.1. Mutable static và shared references

```java
// Snippet minh họa, không phải chương trình độc lập:
static long requests = 12_345L;
static final java.util.Map<String, Integer> CACHE =
        new java.util.concurrent.ConcurrentHashMap<>();
```

Giả sử class đã initialized và cache có dữ liệu. Retransform đổi body method truy cập `requests`/`CACHE` không tự khiến `requests` trở về 12_345 nếu nó đã tăng lên 20_000; cũng không tự tạo `ConcurrentHashMap` mới. **`static final` ở đây ngăn gán lại biến theo luật Java thông thường, không ngăn object map bên trong bị thay đổi qua method calls.**

Trên ứng dụng nhiều thread, field có thể thay đổi ngay trong thời gian retransform bởi thread khác. Hai snapshot trước/sau không bằng nhau chưa phải bằng chứng JVM chạy lại `<clinit>`. Muốn chứng minh invariant, dùng test tuần tự với counters và state được cô lập.

### 4.2. Compile-time constants và inlining

```java
public static final String MODE = "V1"; // constant variable
public static final int LIMIT = 10;     // constant variable
```

Đây là constant variables theo luật Java nếu thỏa kiểu và constant-expression initializer. `javac` có thể nhúng literal `"V1"` hoặc `10` trực tiếp vào bytecode của **caller**, nên caller không nhất thiết còn đọc field tại runtime. Retransform class khai báo `MODE` không tự cập nhật literal trong mọi client đã biên dịch.

Hơn nữa, việc thay code initializer không tự đổi static values đang sống. Vì vậy muốn hot-update một cấu hình, **đừng** thiết kế nó như một compile-time constant rồi kỳ vọng retransform class khai báo sẽ cập nhật toàn hệ thống. Hãy dùng accessor/cấu hình runtime rõ ràng, với memory visibility và chính sách thay đổi phù hợp.

### 4.3. Static final object không được khởi tạo lại

```java
// Ví dụ ngữ nghĩa, Config và load() chưa được định nghĩa:
static final Config CONFIG = Config.load();
```

Nếu `CONFIG` đang trỏ tới object cấu hình V1, retransform class sử dụng nó không làm `Config.load()` chạy lại. Đổi body method từ V1 sang V2 mà không chú ý `CONFIG` có thể tạo mismatch về dữ liệu hoặc endpoint. Đây là vấn đề thiết kế lifecycle, không phải lỗi bytecode verifier.

## 5. Giới hạn schema: không tự thêm fields để migrate object

`Instrumentation.retransformClasses` cho phép biến đổi method bodies, constant pool và attributes theo ràng buộc JVM TI. Trong cơ chế tiêu chuẩn, không thể tùy tiện thêm/xóa/đổi tên fields/methods, đổi method signature hoặc đổi inheritance rồi mong retransform thành công.

| Mong muốn | Có phải một retransform thông thường? | Ghi chú |
|---|---|---|
| Chèn bytecode đo thời gian vào method | Có thể | Phải giữ bytecode hợp lệ và giữ semantics |
| Thay method body nhưng giữ tên/descriptor | Có thể | Method mới phải tương thích state V1 |
| Đổi logic constructor (cùng descriptor) | Có thể theo giới hạn body hợp lệ | Chỉ ảnh hưởng constructor invocation về sau |
| Thay code `<clinit>` | Không làm initializer của class cũ chạy lại | Không dùng để reset static state |
| Thêm instance field mới | Không phải thay đổi schema được hỗ trợ thông thường | Không có cơ chế tạo field cho objects cũ |
| Đổi superclass/interfaces | Không | Phá giới hạn class schema |
| Đổi signature hoặc xoá method | Không | Có thể bị `UnsupportedOperationException` |
| Migrate toàn bộ instances bằng retransform | Không | Cần thiết kế state riêng |

Một Java agent dùng `ClassFileTransformer` cũng cần tương thích với các transformer khác. Việc trả một mảng class bytes mới từ bản biên dịch độc lập có thể thành công trong demo kiểm soát, nhưng không phải công thức production nếu nhiều agent đang chèn probe hoặc class loading/loader context phức tạp.

## 6. Ví dụ chạy được trên Java 17+: retransform V1 thành V2

Ta dùng một **startup Java agent** qua `-javaagent` để lấy đối tượng `Instrumentation`; chương trình thử nghiệm tự gọi `retransformClasses`. Cách này bỏ qua yêu cầu Attach API/PID, nhưng vẫn sử dụng chính **retransformation** cần học.

Kế hoạch:

1. Biên dịch **V1** và **V2** của cùng binary class `StateTarget` vào hai thư mục khác nhau.
2. V1 static block tăng `initRuns` một lần và gán `label="INIT_V1"`; V2 static block cố tình khác (`+100` và `"INIT_V2"`).
3. Tạo một object cũ với `value=7`.
4. Agent đăng ký transformer **canRetransform=true**; khi `StateTarget` được retransform, nó trả class bytes V2 có cùng schema.
5. In object cũ sau retransform: method body là V2, field vẫn 7 và static label vẫn INIT_V1.
6. Tạo object mới sau retransform: constructor V2 gán `value=107`, static initializer V2 vẫn **không chạy lại**.

### 6.1. Thư mục

```text
demo/
  v1/
    StateTarget.java
  v2/
    StateTarget.java
  SwapAgent.java
  StateDemo.java
  agent.mf
```

Hai nguồn `StateTarget.java` trùng tên class nhưng **không biên dịch vào cùng output directory**. Điều này rất quan trọng: mục tiêu là có class bytes V2 để transformer dùng, chứ không tạo hai class trùng tên trên runtime classpath.

### 6.2. `v1/StateTarget.java`

```java
public final class StateTarget {
    public static int initRuns;
    public static String label;
    public int value;

    static {
        initRuns++;
        label = "INIT_V1";
    }

    public StateTarget(int input) {
        value = input;
    }

    public String describe() {
        return "V1:" + value + ":" + label;
    }
}
```

V1 có đúng ba fields (hai static, một instance), một constructor `(I)V` và method `describe()Ljava/lang/String;`. Lệnh `new StateTarget(7)` sẽ initialize class trước khi tạo instance: `initRuns=1`, `label="INIT_V1"`, instance field `value=7`.

### 6.3. `v2/StateTarget.java`

```java
public final class StateTarget {
    public static int initRuns;
    public static String label;
    public int value;

    static {
        initRuns += 100;
        label = "INIT_V2";
    }

    public StateTarget(int input) {
        value = input + 100;
    }

    public String describe() {
        return "V2:" + value + ":" + label;
    }
}
```

V2 cố ý **giữ nguyên tên class, field names/types, constructor/method descriptors, superclass và access modifiers**. Thay đổi nằm trong method bodies và constant pool liên quan. Nếu V2 được load như một class mới trong JVM mới, static block của nó sẽ khác V1; nhưng khi được dùng làm định nghĩa mới cho **class V1 đã initialized**, static block V2 **không tự được gọi**.

### 6.4. `SwapAgent.java`

```java
import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.lang.instrument.UnmodifiableClassException;
import java.security.ProtectionDomain;

public final class SwapAgent {
    private static volatile Instrumentation instrumentation;

    private SwapAgent() {
    }

    public static void premain(String options, Instrumentation inst) {
        instrumentation = inst;
    }

    public static boolean apply(byte[] replacement)
            throws UnmodifiableClassException {
        Instrumentation inst = instrumentation;
        if (inst == null) {
            throw new IllegalStateException("Agent unavailable");
        }

        if (!inst.isRetransformClassesSupported()) {
            System.out.println("SKIPPED: RETRANSFORM_UNSUPPORTED");
            return false;
        }
        if (!inst.isModifiableClass(StateTarget.class)) {
            System.out.println("SKIPPED: CLASS_UNMODIFIABLE");
            return false;
        }

        ClassFileTransformer transformer =
                new ReplacementTransformer(replacement);
        inst.addTransformer(transformer, true);
        try {
            inst.retransformClasses(StateTarget.class);
        } finally {
            inst.removeTransformer(transformer);
        }
        return true;
    }
}

final class ReplacementTransformer implements ClassFileTransformer {
    private final byte[] replacement;

    ReplacementTransformer(byte[] bytes) {
        this.replacement = bytes.clone();
    }

    @Override
    public byte[] transform(
            ClassLoader loader,
            String className,
            Class<?> classBeingRedefined,
            ProtectionDomain domain,
            byte[] input) {

        if ("StateTarget".equals(className)
                && classBeingRedefined == StateTarget.class) {
            return replacement.clone();
        }
        return null;
    }
}
```

`SwapAgent` và `ReplacementTransformer` cùng một source file là hợp lệ vì chỉ `SwapAgent` là `public`. JDK sinh `SwapAgent.class` và `ReplacementTransformer.class`. Transformer chỉ trả bytes V2 khi có đúng class target trong một retransform/redefine callback, không sửa `input` trực tiếp.

Với Java 9+ overload có thêm tham số `Module`, nếu bạn không override phiên bản sáu tham số, implementation mặc định chuyển sang overload năm tham số đã viết ở đây. Vì vậy mã trên vẫn áp dụng được ở Java 17+.

Trong sản phẩm thật, thay thế toàn bộ classfile bytes bằng artifact build khác cần xác minh compiler version, schema, transformers đang hoạt động và nguồn bytes tương ứng class loader. Demo chọn một target và dữ liệu xác định để làm rõ semantics, không đề xuất copy nguyên class file tùy tiện vào ứng dụng production.

### 6.5. `StateDemo.java`

```java
import java.nio.file.Files;
import java.nio.file.Path;

public final class StateDemo {
    private static void show(String stage, StateTarget target) {
        System.out.println(
                stage
                + " body=" + target.describe()
                + " initRuns=" + StateTarget.initRuns
                + " field=" + target.value);
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.err.println(
                    "Usage: StateDemo <v2-class-file-path>");
            System.exit(2);
        }

        StateTarget existing = new StateTarget(7);
        show("BEFORE", existing);

        byte[] v2 = Files.readAllBytes(Path.of(args[0]));
        if (!SwapAgent.apply(v2)) {
            return; // Không giả báo thành công khi capability không có.
        }

        System.out.println("SWAP_OK");
        show("AFTER", existing);

        StateTarget newer = new StateTarget(7);
        show("NEW", newer);
    }
}
```

Vòng đời:

- `existing` được dựng bởi V1 trước retransform.
- `show("AFTER", existing)` **không** tạo lại instance, nhưng `target.describe()` là một **lời gọi method mới**, nên có thể dùng V2.
- `newer` được dựng sau khi V2 đã được cài; constructor body V2 đặt `value=107`.
- Static `label` vẫn ở `INIT_V1` và `initRuns` vẫn là `1`; chính thao tác retransform không chạy static initializer V2.

### 6.6. `agent.mf`

```text
Manifest-Version: 1.0
Premain-Class: SwapAgent
Can-Retransform-Classes: true

```

Manifest cần dòng trống kết thúc. `Can-Retransform-Classes: true` yêu cầu capability của agent, không ép mọi JVM cung cấp capability đó. Mã vẫn kiểm tra `inst.isRetransformClassesSupported()` và `inst.isModifiableClass(StateTarget.class)` trước khi thử.

Đây là agent khởi động bằng `-javaagent`, không phải agent nạp động bằng `VirtualMachine.loadAgent`. Không cần `Agent-Class` hay `agentmain` trong manifest của ví dụ.

### 6.7. Lệnh build và chạy

Dùng **JDK 17 trở lên**. Ở Bash/macOS/Linux, từ thư mục `demo`:

```shell
mkdir -p build/v1 build/v2
javac -d build/v1 v1/StateTarget.java
javac -d build/v2 v2/StateTarget.java
javac -cp build/v1 -d build/v1 SwapAgent.java StateDemo.java

jar cfm swap-agent.jar agent.mf \
  -C build/v1 SwapAgent.class \
  -C build/v1 ReplacementTransformer.class

java -Xverify:all -javaagent:swap-agent.jar \
  -cp build/v1 StateDemo build/v2/StateTarget.class
```

Với **PowerShell Windows** có thể tạo thư mục như sau, rồi dùng các lệnh không nối dòng bằng `\`:

```powershell
New-Item -ItemType Directory -Force build/v1, build/v2 | Out-Null
javac -d build/v1 v1/StateTarget.java
javac -d build/v2 v2/StateTarget.java
javac -cp build/v1 -d build/v1 SwapAgent.java StateDemo.java
jar cfm swap-agent.jar agent.mf -C build/v1 SwapAgent.class -C build/v1 ReplacementTransformer.class
java -Xverify:all -javaagent:swap-agent.jar -cp build/v1 StateDemo build/v2/StateTarget.class
```

**Chú ý classpath:** chỉ `build/v1` ở runtime `-cp`. File V2 phải được truyền như một **tệp bytes** qua tham số `StateDemo`, không đưa `build/v2` vào classpath để JVM chọn V2 ngay từ đầu. Nếu làm vậy, kết quả không còn chứng minh retransformation.

### 6.8. Stdout dự kiến khi JVM hỗ trợ retransform

```text
BEFORE body=V1:7:INIT_V1 initRuns=1 field=7
SWAP_OK
AFTER body=V2:7:INIT_V1 initRuns=1 field=7
NEW body=V2:107:INIT_V1 initRuns=1 field=107
```

- Dòng **BEFORE** xác nhận V1, một lần static initialization và object cũ lưu 7.
- **SWAP_OK** chỉ in sau khi `retransformClasses` trả về thành công.
- Dòng **AFTER**: method mới trả tiền tố V2, **cùng object cũ** vẫn value=7 và static state vẫn INIT_V1.
- Dòng **NEW**: constructor mới làm value=107; `<clinit>` V2 không được gọi lại, nên static vẫn như cũ.

Đây là stdout dự kiến với HotSpot JDK 17/21 hỗ trợ capability, không phải output được khẳng định cho mọi JVM implementation/cấu hình. Với JVM không hỗ trợ, code in `SKIPPED: RETRANSFORM_UNSUPPORTED`; nếu class không modifiable, in `SKIPPED: CLASS_UNMODIFIABLE`. Nếu bytes V2 không hợp lệ theo HotSwap restrictions, API ném exception và không in `SWAP_OK`. Đừng bỏ các nhánh kiểm tra để ép kết quả.

### 6.9. Kiểm tra schema bằng `javap`

```shell
javap -p -s -classpath build/v1 StateTarget
javap -p -s -classpath build/v2 StateTarget
javap -c -p -classpath build/v1 StateTarget
javap -c -p -classpath build/v2 StateTarget
```

Hai bản phải có field/method descriptors tương ứng, dù instructions của `<init>`, `<clinit>` và `describe` khác nhau. `javap` giúp xác nhận compiler đã sinh bytecode như mong đợi; test chạy ứng dụng với `-Xverify:all` chứng minh JVM chấp nhận class bytes và các lời gọi mới hoạt động theo scenario.

## 7. Active stack frames: V1 và V2 có thể cùng tồn tại

Giả sử thread A đã **vào** `calculate()` V1 và đang xử lý một request lâu, trong lúc thread B retransform class để thay `calculate()` bằng V2:

```text
Thread A                                Thread B
--------                                --------
enter calculate() V1
  frame F(V1) đang chạy                retransformClasses(Target.class)
                                        install body V2
continue F(V1)                         new invoke calculate() -> V2
return kết quả theo code V1
```

Javadoc quy định active frame **tiếp tục bytecode cũ**. Nó không tự nhảy sang đầu method V2, không đổi program counter thành offset mới và không tự chạy lại code. Chỉ khi có **new invocation** thì body V2 được dùng theo hợp đồng.

Hệ quả:

- Trong một giai đoạn ngắn, có thể đồng thời có request đi qua V1 và request mới đi qua V2.
- Cả hai có thể truy cập **cùng static fields** và cùng object graph. Không có bản snapshot state riêng cho từng phiên bản method.
- Retransform không cung cấp cơ chế transaction đồng bộ tất cả request, reset cache hay chuyển các operation đang dở sang code mới.
- Nếu yêu cầu hotfix cần boundary nhất quán mạnh, cần quiesce/drain traffic hoặc chiến lược versioned routing ở tầng ứng dụng.

**Không suy sai:** Active frame dùng bytecode V1 không có nghĩa object cũ “bị gắn chết” với V1. Cùng object ấy ở một lần gọi mới sau retransform vẫn dùng V2.

## 8. Retransformation, redefinition, new class loader và restart khác nhau

| Cơ chế | Thay body class đã nạp? | Chạy lại `<clinit>` của class đã initialized? | Reset static/instances cũ? |
|---|---|---|---|
| `retransformClasses` | Có thể, qua transformer phù hợp | Không | Không |
| `redefineClasses` | Có thể, bằng `ClassDefinition` do caller cung cấp | Không | Không |
| `addTransformer(t)` cho lần load tương lai | Không tự sửa class đã nạp | Không áp dụng cho class cũ | Không |
| Cố ý gọi `reset`/`refreshConfig` của ứng dụng | Không nhất thiết đổi bytecode | Không | **Có thể** chủ động đổi state |
| Định nghĩa class cùng tên bằng class loader **khác** | Tạo một class khác theo identity JVM | Class mới initialize theo luật riêng | Class cũ và objects cũ không reset |
| Restart JVM hoặc redeploy fresh instance | Nạp lại class ở runtime mới | Class mới initialize theo luật bình thường | Không có phép migration tự động từ JVM cũ |

`redefineClasses` và `retransformClasses` có nhiều điểm giống về state preservation nhưng **hợp đồng đầu vào khác nhau**: redefine nhận bytes thay thế trong `ClassDefinition`; retransform chạy lại transformation process từ class bytes nền theo các quy tắc của JVM. Không coi chúng là API tương đương hoàn toàn.

Một class cùng binary name ở loader khác là class **khác**. Nếu class đó chạy `<clinit>`, không thể lấy làm bằng chứng rằng class cũ đã được retransform và initialized lại.

## 9. Những lỗi thiết kế thường gặp

### 9.1. Đổi method nhưng giả định static cache đã có schema V2

V1 cache lưu key `"user:123"`, V2 method lookup cần `"tenant/user:123"`. Retransform thay code không tự chuyển dữ liệu cache V1. JVM có thể verify được bytecode V2 nhưng ứng dụng vẫn trả sai hoặc gặp exception.

**Giải pháp:** V2 đọc được cả state cũ và mới, hoặc có migration chuyên biệt với lock/version/rollback, hoặc restart/redeploy. Không ép serializer/transformer trực tiếp duyệt mọi object khi JVM đang xử lý class definition.

### 9.2. Thay constructor V2 nhưng mong object cũ có default mới

V2 constructor đặt `timeout=30`, còn object V1 đã tồn tại chứa `timeout=0`. Method mới giả định tất cả objects đều có timeout dương sẽ lỗi với objects cũ. Retransformation không gọi lại constructor để “vá” field.

### 9.3. Tưởng `static final` là cấu hình hot-reload

`static final Config CONFIG = Config.load()` không tự chạy lại `Config.load()`. Compile-time primitive/String constants còn có khả năng bị inlined ở callers. Cần runtime accessor/config service nếu muốn đổi cấu hình động.

### 9.4. Rollback code nhưng quên rollback dữ liệu

V2 method ghi một phiên bản dữ liệu mới vào cache/database. Sau đó agent retransform về V1. Method body V1 quay lại, nhưng dữ liệu do V2 đã sửa **không tự được hoàn tác**. Plan rollback phải xử lý riêng state transition và compatibility.

### 9.5. Đọc static counter trước/sau rồi suy `<clinit>` chạy lại

Thread khác có thể tăng counter bình thường. Hãy dùng test tuần tự, nhận diện rõ thao tác của ứng dụng và đọc log/counter có kiểm soát. Không coi mọi thay đổi state quanh thời điểm retransform là do VM reset.

### 9.6. Không kiểm tra class loader/capability

Hai class cùng tên do hai defining loaders khác nhau là **hai target khác nhau**. Cần dùng đúng đối tượng `Class<?>`, kiểm tra `isRetransformClassesSupported()` và `isModifiableClass(target)` trước khi gọi API.

## 10. Diagnostic checklist và lỗi API

### 10.1. Kiểm tra trước retransform

```java
// Đoạn mẫu trong agent; inst và target phải do agent lấy hợp lệ:
if (!inst.isRetransformClassesSupported()) {
    // báo SKIPPED: capability không hỗ trợ
} else if (!inst.isModifiableClass(target)) {
    // báo SKIPPED: target unmodifiable
} else {
    inst.retransformClasses(target);
}
```

Đoạn trên **chỉ minh họa**, chưa là chương trình Java độc lập vì `inst` và `target` chưa khai báo. Thí nghiệm ở phần 6 đã cung cấp chương trình hoàn chỉnh.

Lỗi có thể gặp dù precheck đã thành công:

- `UnmodifiableClassException`: target không thể sửa.
- `UnsupportedOperationException`: capability hoặc dạng thay đổi không được hỗ trợ.
- `ClassFormatError`, `UnsupportedClassVersionError`: class bytes không hợp lệ/không tương thích.
- `NoClassDefFoundError`, `ClassCircularityError`, `LinkageError`: lỗi định nghĩa, dependency hoặc linkage.
- Transformer có thể trả `null` (không đổi) hoặc ném exception bị JVM xử lý như `null` ở bước transform; `retransformClasses` không ném chưa chắc chứng minh probe cụ thể đã được chèn.

Không dùng `catch(Throwable)` để nuốt mọi lỗi JVM rồi báo success. Phân biệt trạng thái **OPERATION_COMPLETED** (API đã trả) với **EFFECT_VERIFIED** (method thực sự thay đổi đúng mục tiêu) và **STATE_MIGRATED** (nếu có migration độc lập).

### 10.2. Bảng triệu chứng

| Triệu chứng | Giải thích | Kiểm tra |
|---|---|---|
| `static` sau retransform vẫn là giá trị V1 | Hành vi được mong đợi | Không có initializer reset |
| V2 `<clinit>` không log gì | Hành vi được mong đợi cho class đã initialized | Không có lần class init mới |
| Object cũ vẫn mang field V1 | Hành vi được mong đợi | Object không tạo lại |
| Object cũ gọi method ra kết quả V2 | New method invocation dùng body mới | Xem callback và bytes đã cài |
| Object mới dùng constructor V2 | New `<init>` được gọi lúc tạo object mới | Kiểm tra output của constructor |
| Method đang chạy vẫn có kết quả V1 | Active frame tiếp tục bytecode cũ | Thử new invocation sau retransform |
| JVM từ chối bytes V2 | Class schema/version/verification có vấn đề | `javap`, manifest, exception |
| Compile-time constant ở caller không đổi | Literal đã inline | Kiểm tra caller bytecode |
| Cache/singleton không được refresh | Không có state migration tự động | Kiểm tra đường refresh rõ ràng |
| Đã gỡ transformer mà method vẫn là V2 | Remove không rollback định nghĩa đã cài | Muốn đổi lại phải có thao tác hợp lệ khác |

## 11. Migration và kiểm thử an toàn khi hot instrumentation

Nếu code V2 bắt buộc state schema mới, bạn phải giải quyết điều đó ở **tầng thiết kế ứng dụng**:

1. **Viết V2 backward-compatible:** đọc được object/static state V1, chuyển sang state mới có kiểm soát.
2. **Tách cấu hình runtime khỏi `<clinit>`:** cung cấp refresh API/immutable config snapshot có memory visibility thích hợp.
3. **Version hóa dữ liệu:** phân biệt state V1/V2 thay vì suy từ version code.
4. **Quiesce traffic khi cần:** drain in-flight requests trước migration để giảm đồng thời V1/V2.
5. **Tách rollback code và rollback state:** không hy vọng retransform ngược sẽ khôi phục cache/database.
6. **Theo dõi metric theo version:** một counter tồn tại từ V1 sang V2 có thể pha trộn semantics; cần nhãn/version policy phù hợp.
7. **Kiểm chứng bằng JVM thực:** bytecode hợp lệ không đồng nghĩa business invariants đúng với objects được tạo trước retransform.

Một bộ test đáng có:

- [ ] Static counter giữ giá trị trước retransform khi không thread nào khác sửa.
- [ ] Static initializer class đã initialized không chạy lại.
- [ ] Reference đến object cũ vẫn là cùng reference và instance fields cũ được giữ.
- [ ] Object cũ invoke method mới cho behavior V2 đã định nghĩa.
- [ ] Object mới chạy constructor/instance initialization theo bytecode hiện hành.
- [ ] Active frames đang chạy tiếp tục behavior V1 theo hợp đồng.
- [ ] Compile-time constants đã inline được xử lý đúng trong kế hoạch đổi code.
- [ ] Schema changes vượt khả năng được báo lỗi, không ghi đè.
- [ ] Có kế hoạch migration/rollback nếu data schema cũng đổi.
- [ ] Transformer không làm mất instrumentation của transformer khác.

## 12. Câu hỏi tự kiểm tra

1. **Retransform một class đã initialized có tự chạy lại `<clinit>` không?** Không.
2. **Sau retransform, static counter có về giá trị khai báo trong V2 không?** Không chỉ vì thao tác retransform; giữ giá trị hiện tại nếu không ai khác sửa.
3. **Object cũ có bị chạy lại constructor không?** Không.
4. **Object cũ có thể chạy method body mới không?** Có, với lần invoke mới sau khi V2 được cài thành công.
5. **Object mới tạo sau retransform chạy constructor nào?** Constructor body trong định nghĩa hiện hành.
6. **Active method frame có chuyển giữa chừng sang V2 không?** Không, frame đang hoạt động tiếp tục bytecode cũ.
7. **Đổi static initializer V2 gán label mới có cập nhật singleton V1 không?** Không.
8. **Vì sao final String constant có thể giữ ở caller?** Compiler có thể inline constant-expression value.
9. **Có được thêm field mới bằng retransform thông thường rồi tự động điền cho objects cũ không?** Không, thay schema như thế không được hỗ trợ.
10. **Nếu class chưa initialized, retransform có tương đương khởi tạo class không?** Không. Initialization vẫn theo trigger JVM bình thường.
11. **Rollback method V2 về V1 có rollback dữ liệu V2 đã viết không?** Không.
12. **Vì sao trong demo AFTER là `V2:7:INIT_V1`?** Method dùng body V2 nhưng object cũ còn value=7 và static label INIT_V1.
13. **Vì sao NEW là `V2:107:INIT_V1`?** Constructor V2 chạy trên instance mới, nhưng class initializer V2 không tự chạy lại.
14. **`retransformClasses` và `redefineClasses` có giống hoàn toàn không?** Không, đầu vào và chuỗi xử lý khác; cả hai đều giữ state/initializer theo quy tắc API.
15. **Nếu JVM chấp nhận bytes mà V2 method vẫn lỗi, nguyên nhân có thể là gì?** Code V2 không tương thích state V1 dù bytecode type-correct.
16. **Điều kiện nào cần kiểm tra trước khi retransform?** Capability toàn JVM và modifiability của đúng Class object.
17. **Tại sao class cùng tên ở class loader khác có `<clinit>` riêng?** Vì class identity gồm tên và defining loader; đó là class khác.
18. **Có phải removeTransformer sẽ khôi phục body V1 không?** Không. Nó không tự rollback định nghĩa đã được cài.

## 13. Tài liệu tham khảo chính thức

- [Java SE 17 — Instrumentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `retransformClasses`, active frames, static values, instances và initializer không chạy lại.
- [Java SE 21 — Instrumentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): capability, `isModifiableClass`, `redefineClasses`, giới hạn và ngoại lệ.
- [Java SE 21 — ClassFileTransformer](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): chuỗi transform, cách trả `byte[]` hoặc `null`, retransformation-capable transformers.
- [Java SE 21 — java.lang.instrument package](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): `premain`, `-javaagent`, manifest `Can-Retransform-Classes`.
- [Java Language Specification SE 21 — Initialization, `12.4](https://docs.oracle.com/javase/specs/jls/se21/html/jls-12.html#jls-12.4): trigger và quy trình khởi tạo lớp.
- [Java Language Specification SE 21 — Field Initialization, `8.3.2](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.3.2): static field initializers và constant variables.
- [JVM TI — RetransformClasses](https://docs.oracle.com/en/java/javase/21/docs/specs/jvmti.html#RetransformClasses): giới hạn thay đổi cấu trúc và cập nhật class definition.

**Kết luận:** `retransformClasses` thay **code**, không tự reset **state**. Static fields, singleton references và existing objects được giữ; `<clinit>` không khởi chạy lại cho class đã initialized; active method frames tiếp tục bytecode cũ. Vì method V2 có thể chạy trên dữ liệu V1, hãy thiết kế backward compatibility hoặc migration có kiểm soát thay vì dựa vào việc “khởi tạo lại” tự động.
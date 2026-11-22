# Phương thức abstract, native, synchronized và các trường hợp không có Code

## 1. Vì sao thiết kế điểm đo phải phân biệt loại phương thức?

Trong Java Instrumentation, một Java agent thường chèn hook vào **đầu** và **cuối** phương thức (*method-entry/method-exit advice*) để đo latency, trace, coverage hoặc metrics. Cách làm này chỉ phù hợp khi phương thức có **bytecode Java** trong thuộc tính **`Code`** của class file.

Ba trường hợp rất dễ bị nhầm:

- **`abstract`**: chỉ khai báo hợp đồng; **không có `Code`** để chèn instruction. Phải đo implementation thật hoặc một boundary khác.
- **`native`**: implementation không nằm trong bytecode Java; **không có `Code`**. Có thể đo ở Java wrapper/call site hoặc dùng cơ chế native/JVMTI chuyên biệt.
- **`synchronized`**: là cờ quản lý monitor của JVM; nếu method có thân Java, nó **vẫn có `Code`**. Tuy nhiên phương thức **`synchronized native`** có cả hai cờ synchronized và native, nên vẫn **không có `Code`**.

Vì thế không thể dựa vào tên, source declaration hay một cờ riêng lẻ để quyết định chèn advice. Hãy kiểm tra **sự tồn tại của `Code` trong method_info thực tế**, rồi áp dụng chính sách điểm đo phù hợp.

Mục tiêu bài học:

1. Nhận diện những method hợp lệ **không có Code** theo JVM Specification.
2. Hiểu cơ chế synchronized method và synchronized block ở tầng JVM.
3. Chọn đúng điểm đo cho abstract, native, synchronized, constructors, class initializers và methods do compiler sinh.
4. Dùng `javap` trên Java 17 và Java Class-File API trên JDK 24+ để xác nhận thực tế.

## 2. `method_info`, access flags và quy tắc của `Code`

Trong class file, một method được biểu diễn bởi:

```text
method_info {
    u2 access_flags;
    u2 name_index;
    u2 descriptor_index;
    u2 attributes_count;
    attribute_info attributes[attributes_count];
}
```

`Code` là một thuộc tính của `method_info`. Nó chứa JVM instructions cùng `max_stack`, `max_locals`, exception table và các thuộc tính con như `StackMapTable`.

Theo **JVMS `4.7.3**:

- Nếu method là **`ACC_ABSTRACT` hoặc `ACC_NATIVE`**, method đó **không được có thuộc tính `Code`**.
- Với method còn lại, một `method_info` hợp lệ **phải có đúng một `Code`**.

Các cờ phổ biến:

| Cờ trong class file | Giá trị | Ý nghĩa | Có `Code`? |
| --- | --- | --- | --- |
| `ACC_ABSTRACT` | `0x0400` | Chưa cung cấp implementation | **Không** |
| `ACC_NATIVE` | `0x0100` | Implementation ở ngoài bytecode Java | **Không** |
| `ACC_SYNCHRONIZED` | `0x0020` | Invocation dùng JVM monitor | **Có nếu không abstract/native** |
| `ACC_STATIC` | `0x0008` | Method thuộc class | Có nếu không abstract/native |
| `ACC_FINAL` | `0x0010` | Không override theo quy tắc JVM | Có nếu không abstract/native |
| `ACC_BRIDGE` | `0x0040` | Bridge do compiler sinh | Thường có; kiểm tra thực tế |
| `ACC_SYNTHETIC` | `0x1000` | Không có method nguồn trực tiếp | Tùy method; không quyết định riêng |
| `ACC_VARARGS` | `0x0080` | Có tham số varargs | Có nếu không abstract/native |

Quy tắc phối hợp cờ cũng quan trọng:

- Method `abstract` **không được** đồng thời `private`, `static`, `final`, `synchronized` hoặc `native`.
- Method **`native synchronized` là hợp lệ** trong class. `ACC_SYNCHRONIZED` không làm xuất hiện `Code` nếu `ACC_NATIVE` đã đặt.
- Các phương thức của interface không được mang `ACC_NATIVE` hoặc `ACC_SYNCHRONIZED`; interface method không có thân là abstract, còn `default` hoặc method private có thân thì có Code.

**Một method có body rỗng vẫn có `Code`**: ví dụ `void f() {}` thường có instruction `return`. Đừng nhầm “không làm gì” với “không có `Code`”.

## 3. `abstract`: declaration không phải implementation

Xét ví dụ:

```java
abstract class Job {
    public abstract String execute();
}

final class Worker extends Job {
    @Override
    public String execute() {
        return "done";
    }
}
```

Trong `Job.class`, method `execute` được đánh dấu `ACC_ABSTRACT` và không có `Code`. Trong `Worker.class`, method override `execute` có code Java.

**Hệ quả khi instrument:**

- Không thể chèn instruction vào **abstract declaration**; không có instruction stream, label, return instruction hoặc exception handler.
- Nếu muốn đo **logic thực thi**, chọn **concrete implementation** mà lời gọi thực tế dispatch tới.
- Nếu muốn đo **mọi lần gọi một hợp đồng API**, có thể instrument **call site**, Java proxy, decorator, hoặc gateway được kiểm soát. Nhưng một call-site transformer chỉ bao phủ những caller đã được biến đổi.
- Với interface, kiểm tra từng method. **`default` method có body** và **interface private method có body** có `Code`; đừng bỏ qua cả interface chỉ vì có các abstract declarations.

### Inherited method và method không được override

Một class con có thể kế thừa một concrete method mà không tạo thêm `method_info` cho method đó. Nếu chỉ đọc `ClassModel.methods()` của class con, bạn **không thấy method kế thừa**, nhưng lời gọi tới method vẫn thực thi body được định nghĩa ở superclass.

Do đó cần xác định rõ phạm vi:

- **Declared methods** của một class file;
- **Methods kế thừa** có implementation ở ancestor;
- **Override thực tế** khi JVM dispatch;
- **Proxy/bridge** có thể thêm lớp trung gian.

Nhầm lẫn các phạm vi này có thể dẫn tới đo thiếu hoặc ghi metric trùng.

## 4. `native`: method có chữ ký nhưng không có bytecode Java

Ví dụ:

```java
class NativeService {
    public native int readValue();

    public synchronized native int readLocked();
}
```

Cả hai method **không có `Code`** vì phần thực thi không được viết thành JVM instructions trong method này. `readLocked` mang đồng thời `ACC_NATIVE` và `ACC_SYNCHRONIZED`, nhưng phần đồng bộ của JVM **không tạo ra Code attribute**.

**Lưu ý chạy thử:** nếu chưa nạp hoặc đăng ký implementation native tương ứng, không gọi hai method này; lời gọi có thể ném `UnsatisfiedLinkError`. Việc class chứa native declaration không đồng nghĩa JVM không thể tải class.

### Cần đo native thì đặt hook ở đâu?

| Mục tiêu | Điểm đo khả thi | Giới hạn cần nêu rõ |
| --- | --- | --- |
| Latency của Java API gọi native | Java **wrapper** hoặc service boundary trước/sau native call | Chỉ bao phủ đường gọi qua wrapper |
| Số lần gọi một native API từ bytecode Java | Các **call sites** `invoke...` | Không bảo đảm bao phủ reflection/JNI/những call sites chưa instrument |
| Thời gian xử lý bên trong thư viện native | Native profiler hoặc **JVMTI/JNI** phù hợp | Công cụ, quyền và capability phụ thuộc VM/OS |
| Thay đổi cơ chế liên kết native | Các API chuyên biệt như native method prefix (nếu được hỗ trợ) | Không phải phép chèn `Code` thông thường; cần thiết kế và kiểm tra capability |

**Không tự sửa `ACC_NATIVE` để thêm body Java khi retransform** rồi nghĩ rằng đó là một method-entry advice hợp lệ. Redefinition/retransformation của class đã nạp chịu các ràng buộc về modifiers và cấu trúc; việc chuyển native thành non-native có thể không được JVM chấp nhận. Hãy chọn boundary đo khác thay vì làm hỏng class file.

## 5. `synchronized`: có `Code` nhưng locking thường nằm ngoài instruction stream

Ví dụ:

```java
public synchronized int increase() {
    return ++counter;
}
```

Method này có **`ACC_SYNCHRONIZED`** và **`Code`**. JVM sử dụng cờ method để tự acquire/release monitor ở lúc invocation/return, **không cần** các instruction `monitorenter` và `monitorexit` trong body của synchronized method.

- **Instance synchronized method:** monitor của object receiver (`this`).
- **Static synchronized method:** monitor của đối tượng `Class` đại diện cho class.
- JVM release monitor khi method hoàn thành bình thường **hoặc** thoát do exception.
- **Synchronized native method:** vẫn có semantics monitor, nhưng **không có Code**, vì native.

### Khác với synchronized block

```java
public int getValue() {
    synchronized (lock) {
        return value;
    }
}
```

Ở đây method không nhất thiết có cờ `ACC_SYNCHRONIZED`. `javac` tạo `monitorenter`/`monitorexit` ngay **trong `Code`**, cùng exception handling cần thiết để cân bằng monitor trên đường thoát bất thường.

| Source code | `ACC_SYNCHRONIZED` | `Code` | Quản lý monitor |
| --- | --- | --- | --- |
| `synchronized void work() { ... }` | Có | Có | JVM invocation/return ngầm |
| `static synchronized void work() { ... }` | Có | Có | JVM, khóa trên `Class` |
| `void work() { synchronized (lock) { ... } }` | Thường không | Có | `monitorenter`/`monitorexit` trong code |
| `synchronized native void work();` | Có | Không | JVM/native invocation path |
| `abstract void work();` | Không | Không | Chưa có implementation |

### Cẩn thận với thời gian đo được

Với synchronized method, advice cài vào **đầu body** chỉ chạy **sau khi JVM đã acquire monitor**:

```text
Caller
  |
  |  chờ monitor khi có contention
  v
JVM acquire monitor
  |
  v
[entry advice]  -> start timer
  |
  |  business logic + instrumentation dưới monitor
  v
[exit advice]   -> stop timer
  |
JVM release monitor
  |
  v
Caller
```

Nếu mục tiêu là đo **thời gian chờ lấy khóa**, method-entry advice **không đo được phần chờ trước acquire**. Hãy cân nhắc caller-side timing hoặc event/profile monitor ở JVM (ví dụ JFR) với ngữ nghĩa đo đã được xác định.

Advice trong synchronized method làm tăng **thời gian giữ monitor**; log blocking I/O, lock khác hoặc code reentrant có thể gây contention, overhead và deadlock. Ưu tiên fast path, giới hạn side effects, phân tách collection và export dữ liệu.

## 6. Normal return, exception và bảo toàn semantics

Một Java method có Code có thể có nhiều `return` hoặc ném exception. Nếu chỉ chèn hook trước instruction return, bạn sẽ bỏ sót exceptional exits. Nếu chèn `try/finally` hoặc handler, phải giữ đúng semantics điều khiển, exception handlers, stack/locals và frames.

Minh họa bằng mã Java nguồn (không phải thuật toán bytecode rewrite tự động):

```java
public synchronized String process() {
    long started = System.nanoTime();
    try {
        return businessLogic();
    } finally {
        long duration = System.nanoTime() - started;
        metrics.record(duration);
    }
}
```

Vì method synchronized, cả `metrics.record` cũng chạy **khi monitor còn bị giữ**. Nếu recorder lỗi, nó có thể che lấp exception gốc; thiết kế production phải có chính sách chống lỗi đo đạc.

Khi instrument cần kiểm tra:

- Mọi đường normal/abrupt exit được bao phủ theo contract.
- Đã bảo toàn return values, thrown exceptions và exception table.
- Không phá `monitorenter`/`monitorexit` của synchronized blocks.
- Không vô ý thay/bỏ `ACC_SYNCHRONIZED` của method.
- Sinh lại hoặc duy trì đúng stack map frames theo class-file version/JVM.
- Không làm thay đổi modifier/schema mà retransform/redefine không hỗ trợ.

Nếu constructor `<init>` hoặc class initializer `<clinit>` được instrument, càng cần bảo toàn thứ tự initialization và tránh truy cập `this` trước khi constructor chain/super initialization hợp lệ.

## 7. Những trường hợp “không có Code” và các ngoại lệ dễ nhầm

| Trường hợp | Trạng thái `Code` | Điều cần nhớ |
| --- | --- | --- |
| Abstract method trong class | **Không có** | Body nằm ở implementation khác |
| Interface abstract method | **Không có** | Implementation có thể ở class implement |
| Native method | **Không có** | Implementation bên ngoài bytecode Java |
| Synchronized native | **Không có** | Cờ synchronized không tạo Code |
| Concrete synchronized | **Có** | JVM lock ngầm, Code vẫn tồn tại |
| Method chứa synchronized block | **Có** | Monitor instructions ở trong Code |
| Interface `default` method | **Có** | Có phần thân Java |
| Interface private/static method có thân | **Có** | Không mặc định là abstract |
| Constructor `<init>` nếu xuất hiện | **Có** | Method đặc biệt nhạy cảm với verifier |
| Class initializer `<clinit>` nếu xuất hiện | **Có** | Không phải class nào cũng có `<clinit>` |
| Class không có `<clinit>` | **Không có method_info tương ứng** | Khác với có method_info nhưng thiếu Code |
| Bridge/synthetic concrete method | Thường **có** | Có thể chỉ forward tới method khác |
| Body rỗng `void f() {}` | **Có** | Thường gồm instruction `return` |

Đừng nhầm **“class không khai báo method đó”** với **“method tồn tại nhưng không có Code”**. Đừng xem class file thiếu `Code` ở một ordinary concrete, non-native method là trường hợp hợp lệ: đó là dấu hiệu class file không tuân thủ JVMS.

## 8. Thực hành Java 17: quan sát bytecode và flags bằng `javap`

Tạo tệp **`MethodKinds.java`**:

```java
public abstract class MethodKinds {
    private static int counter = 7;

    public abstract String abstractWork();

    // Hai native method được khai báo nhưng không được gọi.
    public native int nativeWork();
    public synchronized native int nativeSync();

    public synchronized String synchronizedWork() {
        return "synchronized";
    }

    public String blockWork() {
        synchronized (this) {
            return "block";
        }
    }

    public String plainWork() {
        return "plain";
    }

    public static synchronized int staticSync() {
        return counter;
    }

    public static void main(String[] args) {
        MethodKinds target = new Concrete();

        System.out.println("[main] abstract="
                + target.abstractWork());
        System.out.println("[main] synchronized="
                + target.synchronizedWork());
        System.out.println("[main] block="
                + target.blockWork());
        System.out.println("[main] plain="
                + target.plainWork());
        System.out.println("[main] static="
                + staticSync());
    }

    static final class Concrete extends MethodKinds {
        @Override
        public String abstractWork() {
            return "implemented";
        }
    }
}

interface Contract {
    String required();

    default String defaultWork() {
        return "default";
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac --release 17 MethodKinds.java
java MethodKinds
```

**Stdout chính xác của `java MethodKinds`:**

```text
[main] abstract=implemented
[main] synchronized=synchronized
[main] block=block
[main] plain=plain
[main] static=7
```

Các declaration `native` không gây lỗi khi chỉ nạp class; demo không gọi chúng. JVM dispatch `abstractWork` tới `Concrete.abstractWork` có thân Java.

### Dùng `javap`

```bash
javap -v -p MethodKinds
javap -c -p MethodKinds
javap -v -p Contract
javap -v -p 'MethodKinds$Concrete'
```

Lệnh có `-v` hiển thị flags và header `Code:`; `-c` hiển thị instructions. Dòng cuối dùng dấu nháy đơn để bảo toàn ký tự `$` trong tên class lồng trên POSIX shell/PowerShell.

Các dấu hiệu cần tìm, không phải toàn bộ output cố định (constant-pool indexes/offset có thể khác):

- `abstractWork` trong `MethodKinds`: `ACC_ABSTRACT`, **không có `Code:`**.
- `nativeWork`: `ACC_NATIVE`, **không có `Code:`**.
- `nativeSync`: đồng thời `ACC_NATIVE` và `ACC_SYNCHRONIZED`, **không có `Code:`**.
- `synchronizedWork`: `ACC_SYNCHRONIZED`, **có `Code:`**.
- `staticSync`: `ACC_STATIC` và `ACC_SYNCHRONIZED`, **có `Code:`**.
- `blockWork`: không mang cờ synchronized, nhưng `javap -c` hiển thị `monitorenter` và `monitorexit`.
- `Contract.required`: abstract, không Code. `Contract.defaultWork`: concrete/default, có Code.
- `MethodKinds$Concrete.abstractWork`: có Code; là implementation của contract abstract.

Quan sát `<init>` constructor và `<clinit>` class initializer trong output nếu muốn phân biệt method có Code và method không tồn tại; `counter = 7` không phải hằng `static final` nên class mẫu có code khởi tạo static field.

## 9. Thực hành Class-File API trên JDK 24+: `MethodModel.code()`

**`java.lang.classfile` được chuẩn hóa từ JDK 24**. Nếu chỉ có JDK 17, không dùng được API này: hãy dùng `javap` hoặc thư viện ASM/Byte Buddy phù hợp.

Tạo tệp **`CodeAudit.java`** trong thư mục có `MethodKinds.class` và `Contract.class`:

```java
import java.io.IOException;
import java.lang.classfile.ClassFile;
import java.lang.classfile.ClassModel;
import java.lang.classfile.MethodModel;
import java.lang.reflect.AccessFlag;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public final class CodeAudit {
    private CodeAudit() {
    }

    private static void inspect(Path path) throws IOException {
        ClassModel model = ClassFile.of().parse(path);
        List<String> rows = new ArrayList<>();

        for (MethodModel method : model.methods()) {
            String name = method.methodName().stringValue();

            // Tập trung vào các method đang so sánh.
            if (name.equals("<init>")
                    || name.equals("<clinit>")
                    || name.equals("main")) {
                continue;
            }

            boolean isAbstract =
                    method.flags().has(AccessFlag.ABSTRACT);
            boolean isNative =
                    method.flags().has(AccessFlag.NATIVE);
            boolean isSynchronized =
                    method.flags().has(AccessFlag.SYNCHRONIZED);
            boolean hasCode = method.code().isPresent();

            rows.add(name
                    + " abstract=" + isAbstract
                    + " native=" + isNative
                    + " synchronized=" + isSynchronized
                    + " code=" + hasCode);
        }

        Collections.sort(rows);
        System.out.println("[" + path.getFileName() + "]");
        rows.forEach(System.out::println);
    }

    public static void main(String[] args) throws IOException {
        for (String arg : args) {
            inspect(Path.of(arg));
        }
    }
}
```

Lệnh dùng **JDK 24+**:

```bash
javac --release 24 CodeAudit.java
java CodeAudit MethodKinds.class Contract.class
```

**Stdout kỳ vọng:**

```text
[MethodKinds.class]
abstractWork abstract=true native=false synchronized=false code=false
blockWork abstract=false native=false synchronized=false code=true
nativeSync abstract=false native=true synchronized=true code=false
nativeWork abstract=false native=true synchronized=false code=false
plainWork abstract=false native=false synchronized=false code=true
staticSync abstract=false native=false synchronized=true code=true
synchronizedWork abstract=false native=false synchronized=true code=true
[Contract.class]
defaultWork abstract=false native=false synchronized=false code=true
required abstract=true native=false synchronized=false code=false
```

`method.code()` trả về `Optional<CodeModel>`; `isPresent()` kiểm tra trực tiếp **Code attribute**, còn `method.flags().has(AccessFlag...)` cho biết metadata. Đây là cách rõ ràng hơn suy diễn từ modifier hoặc tên phương thức.

**Giới hạn ví dụ:** chương trình đọc class file trên đĩa, không rewrite bytecode và không nạp `MethodKinds` thông qua reflection. Trong agent thực, phải dùng **đúng classfileBuffer** do callback nhận được thay vì giả định file trên đĩa giống bản class JVM đang định nghĩa.

## 10. Viết bộ lọc method-body instrumentation

Ở JDK 24+, một helper có thể xác định method có phần thân để xem xét advice:

```java
static boolean hasInstrumentableBody(MethodModel method) {
    return method.code().isPresent()
            && !method.flags().has(AccessFlag.ABSTRACT)
            && !method.flags().has(AccessFlag.NATIVE);
}
```

**Đoạn này là helper minh họa, không phải file Java độc lập**; dùng các import `MethodModel` và `AccessFlag` như chương trình `CodeAudit`. `code().isPresent()` đã thể hiện điều kiện chính, hai kiểm tra flags giúp thể hiện chủ đích và phát hiện metadata bất thường.

Với ASM trên Java 17, logic sơ bộ tương đương (đoạn dùng constant của **ASM Opcodes**, không phải Java SE độc lập):

```java
boolean hasJavaBody =
        (access & (ACC_ABSTRACT | ACC_NATIVE)) == 0;
```

Trong cả hai cách, **eligible for method-body instrumentation** chỉ là bước đầu. Sau đó cần policy cho:

- `<init>`: chọn điểm vào sau giai đoạn constructor initialization hợp lệ; không truy cập `this` quá sớm.
- `<clinit>`: code chạy trong quá trình class initialization, nguy cơ recursion và class-initialization failure.
- Bridge/synthetic methods: nếu đo cả bridge và implementation, một lần gọi có thể phát sinh nhiều event.
- Synchronized methods: advice được thực thi khi monitor đã acquire; rất nhạy với overhead và deadlock.
- Method do proxy hoặc framework sinh: class loader và thời điểm define có thể khác code nguồn.
- Methods thuộc Java core, agent helpers hoặc recorder: tránh tự instrument cơ chế ghi log/tracing của chính agent gây recursion.

## 11. Quy trình chọn điểm đo trong một transformer

```text
MethodModel / method_info
         |
         v
Code có tồn tại không?
    |
    +-- KHÔNG
    |     |
    |     +-- ACC_ABSTRACT -> tìm concrete override,
    |     |                    proxy/API boundary hoặc call site
    |     |
    |     +-- ACC_NATIVE   -> đo Java wrapper/call site,
    |     |                    JVMTI/native profiler
    |     |
    |     +-- còn lại      -> class file không hợp lệ?
    |
    +-- CÓ
          |
          +-- <init>/<clinit>/bridge/synthetic?
          |          -> áp dụng policy riêng
          |
          +-- ACC_SYNCHRONIZED?
          |          -> giảm overhead vì đang giữ monitor
          |
          +-- có monitorenter/monitorexit?
          |          -> bảo toàn synchronized block/handlers
          |
          v
    Instrument entry / normal + exceptional exits
          |
          v
    Kiểm tra frames / exception / monitor
          |
          v
    Verify class file + integration tests
```

Các yêu cầu kiểm thử quan trọng:

1. **Abstract and native:** không sinh `Code` tùy tiện; có chiến lược đo khác thay vì im lặng “đã instrument”.
2. **Synchronized:** test bình thường, exception, cạnh tranh monitor, tracing recursion và overhead. So sánh trong/ngoài monitor để hiểu đúng latency.
3. **Constructor/initializer:** kiểm tra lúc class khởi tạo, exception và circular initialization.
4. **Bridge/synthetic:** kiểm tra double-counting khi gọi qua generics/interface.
5. **Bytecode integrity:** dùng verifier, kiểm tra `StackMapTable`, try/catch, return/throw paths và class-file version.
6. **Retransform:** không giả định được quyền đổi method flags/schema của class đã nạp. Chỉ làm các thay đổi mà JVM mục tiêu hỗ trợ.
7. **Class-loader scope:** hai loader có thể định nghĩa cùng tên class; không chỉ filter theo tên khi agent có phạm vi đặc biệt.

## 12. Những lỗi thường gặp và cách sửa

| Triệu chứng | Nguyên nhân hay gặp | Cách xử lý |
| --- | --- | --- |
| `MethodModel.code()` rỗng trên abstract method | Abstract không có implementation bytecode | Bỏ qua body và instrument concrete implementation |
| Native method không có body | `ACC_NATIVE` cấm Code attribute | Dùng wrapper/call site/native instrumentation |
| Synchronized Java method bị skip | Nhầm `ACC_SYNCHRONIZED` với “no Code” | Kiểm tra Code thực tế; vẫn có thể instrument method body |
| `synchronized native` bị chèn Code | Xét cờ synchronized nhưng không xét native | Ưu tiên kiểm tra Code và `ACC_NATIVE` |
| `javap -c` không hiện monitorenter trong synchronized method | JVM áp dụng monitor ngầm dựa vào flag | Dùng `javap -v` để xem `ACC_SYNCHRONIZED` |
| Method có monitorenter nhưng không synchronized flag | Code chứa synchronized block | Phân tích instructions và exception handlers |
| Tracing đo ít hơn lock contention | Method-entry advice chạy sau khi lấy monitor | Đặt caller-side timer hoặc đo JVM monitor events |
| Metric đếm đôi | Hook cả bridge và implementation | Quy định rõ ownership và method filtering |
| `VerifyError` sau rewrite | Sai frames, schema, exception hoặc monitor pairing | Verify bytecode, dùng công cụ đúng class version |
| Constructor crash khi instrument | Hook dùng `this` trước constructor chain hợp lệ | Dời hook tới điểm an toàn |
| `UnsatisfiedLinkError` khi thử native demo | Không có native implementation | Không gọi native declaration nếu chưa liên kết JNI |
| Class initialization thất bại do hook | Recursion/exception trong `<clinit>` | Giảm phụ thuộc, chống recursion, có policy lỗi |
| Java 17 không biết `java.lang.classfile` | Class-File API chính thức từ JDK 24 | Dùng JDK 24+ hoặc ASM/Byte Buddy cho JDK 17 |

## 13. Checklist trước khi phát hành

1. Đọc flags **và** `Code` trong artifact thực tế, không chỉ nhìn source.
2. **Skip no-Code** cho method-body advice; quyết định riêng cách đo abstract/native.
3. Không loại đồng loạt synchronized methods: nhiều method synchronized **có Code**.
4. Phân biệt synchronized method (monitor ngầm) với synchronized block (explicit monitor instructions).
5. Xác định latency mục tiêu: **execution under lock** khác **wait-to-acquire lock**.
6. Bảo toàn normal/exception exit, stack maps, monitor balance và return values.
7. Xác định policy cho constructor, initializer, bridge và synthetic methods.
8. Hạn chế blocking work trong synchronized advice; tránh recursion/deadlock.
9. Kiểm thử trên JVM và class loader đích, bao gồm retransform nếu có.
10. Đảm bảo metric phản ánh đúng phương thức/thời điểm thực sự được instrument.

## 14. Tự kiểm tra

**Câu 1:** Có thể chèn bytecode vào chính method `abstract void run();` không?

**Đáp án:** Không. Method abstract không có Code. Chọn concrete override hoặc call boundary.

**Câu 2:** `public synchronized void run() { ... }` có Code không?

**Đáp án:** Có, vì synchronized chỉ là cờ monitor, body Java vẫn có bytecode.

**Câu 3:** `public synchronized native void run();` có Code không?

**Đáp án:** Không, do method native; synchronized không làm xuất hiện Code.

**Câu 4:** `void run() { synchronized(lock) { action(); } }` có bắt buộc cờ `ACC_SYNCHRONIZED` không?

**Đáp án:** Không. Code chứa `monitorenter`/`monitorexit` cho synchronized block.

**Câu 5:** Method-entry advice trong synchronized method có đo cả thời gian chờ monitor không?

**Đáp án:** Không. Advice bắt đầu sau khi monitor đã được JVM acquire.

**Câu 6:** Reflection cung cấp modifiers có đủ để biết một method có Code không?

**Đáp án:** Không. Để xác nhận thuộc tính Code, cần đọc class file bằng `javap`, Class-File API hoặc một bytecode parser.

## 15. Tài liệu chính thức

- [JVMS `4.6 — Methods](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-4.html#jvms-4.6): các method flags và quy tắc hợp lệ.
- [JVMS `4.7.3 — Code Attribute](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-4.html#jvms-4.7.3): abstract/native không có Code, ordinary method phải có một Code.
- [JVMS `2.11.10 — Synchronization](https://docs.oracle.com/javase/specs/jvms/se26/html/jvms-2.html#jvms-2.11.10): synchronized method monitor ngầm và synchronized block instructions.
- [Java SE 24 — `MethodModel`](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/MethodModel.html): `flags()` và `code()`.
- [Java SE 24 — `AccessFlags`](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/AccessFlags.html): `has(AccessFlag)` và `flagsMask()`.
- [Java SE 24 — `ClassFile`](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/ClassFile.html): `parse(Path)`, `ClassModel` và verification.
- [Java SE 17 — `javap`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html): kiểm tra bytecode, flags và Code attributes.

**Ghi nhớ:** **`abstract` và `native` không có `Code`; `synchronized` có thể có `Code` và JVM quản lý monitor ngầm.** Kiểm tra phương thức thực tế trước khi chèn advice, sau đó chọn điểm đo phù hợp để giữ nguyên semantics và đo đúng mục tiêu.

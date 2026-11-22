# 15.9 Phân biệt định nghĩa lớp mới với thay thế bytecode của lớp đã được nạp

Khi ứng dụng Java đã chạy, việc có một file `.class` mới **không đồng nghĩa** mã đang thực thi sẽ tự đổi. JVM phân biệt rõ hai hành động:

1. **Định nghĩa một lớp mới** (*define a new class*): đưa bytecode vào một **không gian định danh lớp** và tạo một `Class<?>` mới. Các API như `ClassLoader.defineClass`, `MethodHandles.Lookup.defineClass` hoặc `Lookup.defineHiddenClass` thuộc nhóm này.
2. **Thay thế định nghĩa/bytecode của lớp đã nạp** (*redefine/retransform an already loaded class*): thay đổi phần mã và metadata được hỗ trợ của **chính lớp runtime đang tồn tại**, thường qua `java.lang.instrument.Instrumentation` hay JVM Tool Interface (JVMTI). Không tạo một định danh class thứ hai cho lớp được thay.

Điểm cốt lõi: **có class mới** khác hoàn toàn với **cập nhật hành vi method của class hiện tại**. Hai thao tác không thay thế cho nhau, vì cơ chế định danh kiểu, vòng đời instance, giới hạn cấu trúc và quyền thực hiện đều khác.

Bài này dùng Java 17+, phân biệt ba thao tác dễ nhầm: **định nghĩa class**, **redefine class**, và **retransform class**. Hai ví dụ chạy độc lập ở phần 6–8 dùng bytecode biên dịch bằng `javac --release 17`. Demo Java agent cần một JVM có hỗ trợ quyền redefinition và được khởi chạy với cấu hình agent phù hợp.

## 1. Class file, runtime class và class loader là ba thứ khác nhau

File `DemoService.class` là một **chuỗi byte chứa cấu trúc class file**, chưa phải chính đối tượng kiểu Java. Khi một loader dùng dữ liệu đó để **define**, JVM tạo một class runtime; Java biểu diễn class này bởi một object `Class<?>`.

~~~text
Nguồn .java ── javac ──> bytes .class
                               │
                               │ ClassLoader.defineClass(...)
                               ▼
                    runtime class / Class<?>
                               │
                  liên kết + khởi tạo khi cần
                               │
                               ▼
                object instance và method calls
~~~

**Định danh kiểu class thường** được xác định bởi *binary name* cùng **defining class loader**. Hai file bytecode có cùng binary name nhưng do hai loader độc lập định nghĩa có thể tạo **hai kiểu runtime khác nhau**. Vì vậy:

~~~text
Loader A định nghĩa pkg.Service -> Class A
Loader B định nghĩa pkg.Service -> Class B

Class A.getName() == Class B.getName() theo chuỗi: true
Class A == Class B:                             false
Một instance Class B cast sang Class A:         không hợp lệ
~~~

Đây là **sơ đồ**, không phải stdout. Với Java, kiểm tra type identity bằng `==` trên `Class<?>` hoặc `instanceof`/`isInstance`, không chỉ dùng `Class.getName()`.

**Khởi tạo không phải định nghĩa.** `defineClass` tạo/liên kết class nhưng không tự bảo đảm static initializer `<clinit>` đã chạy. Việc khởi tạo theo quy tắc JLS (ví dụ trước lần tạo instance hoặc truy cập static field không phải constant variable) là giai đoạn riêng. Và việc **định nghĩa thêm class khác** không có nghĩa đã thay mã của class cũ.

## 2. Bảng so sánh: define / redefine / retransform

| Thuộc tính | Định nghĩa lớp mới | `Instrumentation.redefineClasses` | `Instrumentation.retransformClasses` |
| --- | --- | --- | --- |
| Mục tiêu | **Class mới** từ bytecode | **Class hiện hữu** được chỉ định bởi `Class<?>` | **Class hiện hữu** chạy lại pipeline transformer |
| Entry point Java 17 | `ClassLoader.defineClass`, `Lookup.defineClass` | `Instrumentation.redefineClasses(new ClassDefinition(...))` | `Instrumentation.retransformClasses(clazz)` |
| Cần Java agent/JVMTI? | Thường không, nhưng cần quyền define/load phù hợp | **Có** khả năng redefinition của JVM và `Instrumentation` | **Có** khả năng retransformation và transformer tương thích |
| Kết quả `Class<?>` | **Object class mới** nếu define thành công | **Vẫn là cùng runtime Class** | **Vẫn là cùng runtime Class** |
| Đối tượng đã tạo từ class cũ | Không tự chuyển sang class mới | Vẫn là instance class đó; có thể chạy method đã thay | Tương tự redefinition |
| Static fields | Class mới có static state **riêng** | Giữ các giá trị static đã có; không chạy lại class initializer | Giữ các giá trị static đã có |
| Bắt đầu từ bytecode nào? | Bytecode được truyền khi định nghĩa | Bytecode class file **thay thế** bạn đưa vào | Bytecode đầu vào của lần load/redefine trước, qua các transformer theo quy tắc |
| Có được đổi schema tùy ý? | Class mới được định nghĩa với cấu trúc bytecode hợp lệ | **Không**; chịu hạn chế JVMTI | **Không**; chịu hạn chế tương tự JVMTI |
| Tiêu chí chọn | Plugin/lớp phiên bản mới/namespace tách biệt | Hot fix method body hoặc sửa class đang dùng | Instrumentation/coverage/profiling/biến đổi lặp lại |
| Nguy cơ thường thấy | `LinkageError` do trùng class cùng loader; cast không tương thích giữa loader | Unsupported change, agent capability, lỗi verify/link | Transformer sai kiểu, capability hoặc lỗi bytecode sau transform |

**Khác biệt cốt lõi giữa redefine và retransform:** cả hai đều cập nhật class đã tồn tại. `redefineClasses` nhận **byte array thay thế trực tiếp** từ caller; `retransformClasses` dùng **chuỗi `ClassFileTransformer`**, không nhận byte array mới trong lời gọi `retransformClasses`. Không được dùng từ “retransform” để ám chỉ tạo một class mới.

## 3. Định nghĩa class mới: `ClassLoader#defineClass` và `Lookup#defineClass`

### 3.1. `ClassLoader.defineClass` tạo thêm một định danh kiểu

Ví dụ trong subclass `ClassLoader`:

~~~java
final class ByteArrayLoader extends ClassLoader {
    ByteArrayLoader(ClassLoader parent) {
        super(parent);
    }

    Class<?> define(String name, byte[] bytes) {
        return defineClass(name, bytes, 0, bytes.length);
    }
}
~~~

Đây là **đoạn minh họa**, không phải ứng dụng chạy riêng. `defineClass` là method protected nên thường gọi thông qua một subclass. Nó tạo class dựa vào bytecode, dùng loader **đang định nghĩa** làm một phần của type identity. `name` phải phù hợp với binary name bên trong bytes (nếu truyền tên rõ ràng).

Một loader bình thường dùng **parent delegation** khi gọi `loadClass`: nó hỏi loader cha trước, do đó nếu cha đã có class cùng tên thì `loadClass` có thể trả lại class cũ của cha. Nhưng khi subclass gọi trực tiếp method `defineClass` (như ở ví dụ trên), nó đang yêu cầu **định nghĩa class trong loader con**, không phải một thao tác “thay bytes của cha”.

Các điểm quan trọng:

- **Một defining loader không được define hai normal class cùng binary name.** Gọi `defineClass` lần thứ hai với chính tên ấy trong cùng loader dẫn tới `LinkageError`. Cần **loader khác** cho version/class identity khác, hoặc dùng instrumentation cho class đã có.
- **Hai loader có thể định nghĩa cùng tên** (trong các điều kiện load/constraints phù hợp). Khi đó hai `Class<?>` khác nhau, có thể không cast được cho nhau.
- Class mới có **static fields riêng** và chạy `<clinit>` theo vòng đời của riêng nó; class cũ không thay đổi vì class mới được define.
- Chỉ thay file `.class` trên ổ đĩa không khiến loader tự define phiên bản mới hoặc khiến JVM cập nhật class đã nạp. Một process JVM đang chạy có thể không bao giờ đọc lại file đó.
- Tham số bytes phải là class file hợp lệ và tuân thủ package, access, sealing/certificates, verification và các giới hạn phiên bản class file.

### 3.2. `MethodHandles.Lookup.defineClass`

Java 9+ hỗ trợ:

~~~java
Class<?> newClass = MethodHandles.lookup().defineClass(bytes);
~~~

Đây là đoạn minh họa, giả sử `bytes` mô tả class mới hợp lệ. `Lookup.defineClass` định nghĩa class **trong cùng class loader và runtime package** với lookup class, có cùng protection domain; cần quyền `PACKAGE` trong `Lookup`. Nó cũng tạo **normal class mới**, không thay một class đang tồn tại.

Đặc biệt, dùng `Lookup.defineClass` không thể thêm “bản mới” có **cùng binary name** vào cùng loader nếu class đã được định nghĩa ở đó. Một lời gọi `defineClass` bị trùng không phải một hot reload tự động.

`Lookup.defineHiddenClass` thì tạo **hidden class** với quy tắc định danh và vòng đời khác normal class: không thể tìm theo tên thông thường qua `Class.forName`; hữu ích cho runtime tạo implementation riêng. Đây vẫn là **định nghĩa class mới**, không phải `Instrumentation.redefineClasses`. Hidden class cũng không phải target mà java agent/JVMTI có thể tùy ý redefine/retransform như normal class.

### 3.3. Vì sao “hai class cùng tên” vẫn không thay được class cũ?

Nếu class cha có `api.Service` và loader con định nghĩa **một `api.Service` khác**, các tham chiếu đã link tới class cha không tự đổi qua bản con. Một caller đã biên dịch để dùng `api.Service` từ loader A sẽ tiếp tục có **loại tham số và liên kết method** của A, không xem class B là cùng kiểu chỉ vì tên giống nhau.

Đây là nguyên nhân thường gặp của lỗi kiểu:

~~~text
java.lang.ClassCastException:
  api.Service cannot be cast to api.Service
~~~

Thông báo có thể bổ sung tên loader/module. Chuỗi class name giống nhau không phải nghịch lý: hai `Class<?>` khác identity. Cách giải quyết là thiết kế **shared API loader**, versioned namespaces hay ranh giới giao tiếp không phụ thuộc cast trực tiếp; không chỉ ép kiểu thêm lần nữa.

## 4. Thay bytecode class đã nạp: `Instrumentation.redefineClasses`

API Java 17:

~~~java
instrumentation.redefineClasses(
    new ClassDefinition(AlreadyLoaded.class, replacementClassBytes)
);
~~~

Đây là đoạn minh họa với `instrumentation` và bytes đã được chuẩn bị. Nó không tạo một `AlreadyLoadedV2.class` hay gán object `Class<?>` mới cho tên cũ. JVM nhận chính đối tượng `AlreadyLoaded.class` để biết **class runtime nào** cần cập nhật.

Cách có được `Instrumentation` thông thường là **Java agent** được khởi chạy bằng `-javaagent:/path/agent.jar` (method `premain`), hoặc agent nạp động qua cơ chế được JVM cho phép (`agentmain`). `Instrumentation` không phải một singleton public tùy ý lấy được từ mọi application code. Cần agent có capability:

~~~text
Premain-Class: HotSwapAgent
Can-Redefine-Classes: true
~~~

Và JVM phải thật sự hỗ trợ. Không suy “chỉ có manifest là đủ”; trước khi làm hãy kiểm tra:

~~~java
instrumentation.isRedefineClassesSupported();
instrumentation.isModifiableClass(AlreadyLoaded.class);
~~~

Hai snippet trên nằm trong ngữ cảnh code đã có object `instrumentation`. Nếu capability không được hỗ trợ hoặc class không thể sửa, không chạy quy trình viết lại.

### 4.1. Kết quả quan sát được

Sau khi `redefineClasses` thành công:

- `oldInstance.getClass() == AlreadyLoaded.class` vẫn **`true`**; object `Class<?>` và defining loader **không bị thay**.
- Những object đã được tạo trước đó vẫn là instance của **chính class đó**; trường instance trước đó giữ giá trị của mình.
- **Các lời gọi method mới** sử dụng bytecode method đã định nghĩa lại. Do vậy một object cũ có thể gọi `message()` và nhận hành vi mới.
- **Static fields giữ nguyên các giá trị runtime hiện tại**. Không chạy lại `<clinit>`; đưa `static int counter=999` vào bytecode thay thế **không đặt lại** field đã được dùng thành 999.
- **Stack frame đang thực thi method cũ** tiếp tục chạy bytecode **của phiên bản cũ** cho đến khi frame ấy kết thúc; những lần invoke mới dùng phiên bản mới. Vì vậy trong hệ thống đa luồng, có thể có khoảng thời gian phương thức cũ và mới cùng hiện diện trên các stack frame khác nhau.
- Nếu JVM đã JIT-compile hoặc inline các method liên quan, JVM có trách nhiệm giữ hành vi tương thích sau redefinition; không xây logic nghiệp vụ dựa trên giả thiết chi tiết máy về deoptimization.

Sơ đồ:

~~~text
Trước redefine:
  Class<?> DemoService [loader app] ── method message() -> "old"
       ├─ instance #1
       └─ instance #2

Instrumentation.redefineClasses(DemoService.class, bytes-v2)
       │
       ▼
Sau redefine:
  CÙNG Class<?> DemoService [loader app] ── NEW invokes -> "new"
       ├─ CÙNG instance #1
       └─ CÙNG instance #2

  Static field giữ nguyên giá trị đã tồn tại.
  Stack frame đang chạy mã cũ hoàn tất theo bytecode cũ.
~~~

Đừng nhầm câu “instances are not affected” trong tài liệu với “instance cũ vẫn mãi dùng method cũ”. **Dữ liệu/identity instance không bị thay**, nhưng các method calls mới trên instance ấy có thể sử dụng bytecode mới.

### 4.2. JVM không cho đổi mọi thứ ở class đã load

Theo JVMTI Java 17, redefinition có thể thay **method bodies**, constant pool và một số attributes được cho phép. Nhưng **không được**:

- Thêm, xóa hoặc đổi tên fields/methods.
- Thay đổi method signatures, modifiers hoặc quan hệ inheritance.
- Tùy tiện thay class hierarchy, superclass/interface list.
- Đổi các attributes có ràng buộc như `NestHost`, `NestMembers`, `Record` hoặc `PermittedSubclasses`.

Ví dụ, bản v2 muốn thêm `public int newMethod()` hay thêm `private long newField` là một **thay đổi schema** không thuộc khả năng redefinition tiêu chuẩn trên JVM Java 17. Một JVM đặc thù có thể có phần mở rộng, nhưng không nên giả định “HotSwap” IDE đồng nghĩa với thay cấu trúc tùy ý trên mọi JDK.

Ngay cả khi cùng tên/methods/fields, bytes thay thế phải là class file đúng phiên bản, đúng binary name và hợp lệ với JVM. Không được dùng bytes của class khác tên để cố “đổi tên” class đang chạy.

## 5. `retransformClasses` khác `redefineClasses` ở đâu?

`Instrumentation.retransformClasses(Class<?>... classes)` cũng làm việc với **class đã nạp**, nhưng không yêu cầu caller truyền một bộ bytes v2 vào chính method này.

Pipeline khái quát:

~~~text
Đã có Class<?> C được load
       │
       ▼
Instrumentation.retransformClasses(C)
       │
       ▼
Lấy base class-file bytes theo quy tắc API:
  - bytes đầu vào của load / redefine gần nhất
  - áp lại kết quả transform trước của transformer không hỗ trợ retransform
  - chạy lại transformer có canRetransform = true
       │
       ▼
Kiểm tra và cài định nghĩa mới cho C
       │
       ▼
CÙNG Class<?> và các instance đang tồn tại
~~~

Với transformer, bạn đăng ký:

~~~java
instrumentation.addTransformer(transformer, true);
instrumentation.retransformClasses(SomeLoadedClass.class);
~~~

Snippet trên giả sử agent đã tạo `transformer` thực thi `ClassFileTransformer`. Muốn dùng `true` ở `addTransformer`, agent phải được cấp quyền retransformation (`Can-Retransform-Classes: true` trong manifest, đồng thời JVM hỗ trợ). Một transformer có thể được gọi trong quá trình load, redefine, retransform tùy cấu hình; chỉ transformer đủ quyền retransform mới được gọi lại khi retransformation được yêu cầu.

**Đừng nhầm:** cả `redefineClasses` và `retransformClasses` đều có thể đi qua các transformer đã đăng ký theo thứ tự API quy định. Điểm khác là **nơi phát sinh bộ byte ban đầu**: `redefineClasses` nhận replacement bytes; `retransformClasses` lấy base bytes theo quy tắc pipeline rồi chạy lại biến đổi thích hợp. Không phải “redefine không hề có transformer”.

Cả hai phải tuân theo giới hạn schema của JVM, khả năng modifiable class và quy tắc lỗi. `retransformClasses` hữu ích cho coverage, tracing, profiling hoặc instrumentation mà transformer quyết định thêm mã. `redefineClasses` thường tiện cho replacement bytecode được biên dịch sẵn bởi debugger hoặc công cụ phát triển.

## 6. Ví dụ hoàn chỉnh A — định nghĩa cùng tên dưới loader khác

Bài thực hành này chỉ dùng **Java core** (không cần javaagent), nhằm chứng minh **class mới** khác **class đang tồn tại**, ngay cả khi tên và bytecode giống nhau.

Tạo thư mục:

~~~text
example/
  v1/
    DemoService.java
    DefineClassDemo.java
    HotSwapAgent.java
    RedefineDemo.java
  v2/
    DemoService.java
  manifest.mf
~~~

Hai file `HotSwapAgent.java` và `RedefineDemo.java` sẽ dùng ở ví dụ B; ở ví dụ A bạn chỉ cần biên dịch `DemoService.java` và `DefineClassDemo.java`.

**`v1/DemoService.java`:**

~~~java
public class DemoService {
    public static int counter = 1;
    public String message() {
        return "old";
    }
}
~~~

**`v1/DefineClassDemo.java`:**

~~~java
import java.nio.file.Files;
import java.nio.file.Path;

public class DefineClassDemo {
    static class MyLoader extends ClassLoader {
        MyLoader(ClassLoader parent) { super(parent); }

        Class<?> define(byte[] bytes) {
            return defineClass("DemoService", bytes, 0, bytes.length);
        }
    }

    public static void main(String[] args) throws Exception {
        // Chạy từ thư mục v1, nơi có DemoService.class.
        byte[] bytes = Files.readAllBytes(Path.of("DemoService.class"));
        Class<?> existing = DemoService.class;
        MyLoader loader = new MyLoader(existing.getClassLoader());
        Class<?> copy = loader.define(bytes);

        Object childObject = copy.getDeclaredConstructor().newInstance();
        DemoService original = new DemoService();

        System.out.println("same name: " +
                existing.getName().equals(copy.getName()));
        System.out.println("same Class object: " + (existing == copy));
        System.out.println("different defining loader: " +
                (existing.getClassLoader() != copy.getClassLoader()));
        System.out.println("original message: " + original.message());
        System.out.println("child message: " +
                copy.getMethod("message").invoke(childObject));
        System.out.println("cast compatible: " +
                (childObject instanceof DemoService));

        try {
            loader.define(bytes);
            throw new AssertionError("duplicate must fail");
        } catch (LinkageError expected) {
            System.out.println("second definition: " +
                    expected.getClass().getSimpleName());
        }
    }
}
~~~

Chạy trên class path, không phải module path. Từ thư mục `example`:

~~~bash
javac --release 17 -d v1 v1/DemoService.java v1/DefineClassDemo.java
cd v1
java DefineClassDemo
~~~

**Stdout đã kiểm chứng**:

~~~text
same name: true
same Class object: false
different defining loader: true
original message: old
child message: old
cast compatible: false
second definition: LinkageError
~~~

Giải thích:

1. `existing` và `copy` đều có binary name `DemoService`, cùng bytes v1 nên cả hai trả `"old"`. Nhưng **khác `Class<?>`** và **khác defining loader**.
2. `childObject instanceof DemoService` là `false` vì mã nguồn `DemoService` trong caller liên kết tới class do loader ứng dụng định nghĩa, không phải class do `MyLoader` tạo.
3. Lần `loader.define(bytes)` thứ hai thất bại bằng `LinkageError` vì **một loader đã định nghĩa normal class tên đó**.
4. Class mới **không** thay `existing`; dòng `original message: old` vẫn giữ hành vi gốc.

**Cẩn thận với delegation:** ví dụ dùng **lời gọi trực tiếp `defineClass` trong subclass**, chứ không gọi `loader.loadClass("DemoService")`. Nếu dùng `loadClass` mặc định với parent là application loader, nó thường trả class parent đã load, **không tạo bản mới**.

Cũng đừng bắt `LinkageError` để tùy tiện bỏ qua trong production: ở đây chỉ bắt có chủ ý để chứng minh quy tắc trùng tên trong một loader.

## 7. Ví dụ hoàn chỉnh B — Java agent thay method của chính class đã load

Tiếp tục **cùng cây thư mục `example`**, nhưng dùng **hai bản bytecode của cùng binary name**:

- `v1/DemoService.java` có `message() -> "old"`, static field `counter = 1`.
- `v2/DemoService.java` có `message() -> "new"`, static field **cùng tên/cùng kiểu** `counter = 999`.

**`v2/DemoService.java`:**

~~~java
public class DemoService {
    public static int counter = 999;
    public String message() {
        return "new";
    }
}
~~~

Bản v2 cố ý **không thêm field, không đổi method signature**, nên phù hợp với phạm vi redefinition Java 17. Giá trị initializer `999` giúp kiểm tra rằng static state **không được khởi tạo lại** khi redefine.

**`v1/HotSwapAgent.java`:**

~~~java
import java.lang.instrument.Instrumentation;

public final class HotSwapAgent {
    static Instrumentation inst;

    public static void premain(String args, Instrumentation instrumentation) {
        inst = instrumentation;
    }
}
~~~

Đây là Java agent tối giản: JVM gọi `premain` trước `RedefineDemo.main` khi chạy với `-javaagent`. Nó lưu `Instrumentation` vào biến static để demo sử dụng. Mã thực tế phải thiết kế quản lý capability, quyền truy cập và bảo mật cho agent cẩn thận hơn.

**`v1/RedefineDemo.java`:**

~~~java
import java.lang.instrument.ClassDefinition;
import java.lang.instrument.Instrumentation;
import java.nio.file.Files;
import java.nio.file.Path;

public final class RedefineDemo {
    public static void main(String[] args) throws Exception {
        Instrumentation inst = HotSwapAgent.inst;
        DemoService instance = new DemoService();
        Class<?> originalClass = instance.getClass();
        DemoService.counter = 42;

        System.out.println("redefine supported: " +
                inst.isRedefineClassesSupported());
        System.out.println("before: " + instance.message());
        System.out.println("before static: " + DemoService.counter);

        byte[] replacement = Files.readAllBytes(Path.of(args[0]));
        inst.redefineClasses(
                new ClassDefinition(DemoService.class, replacement));

        System.out.println("same Class object: " +
                (instance.getClass() == originalClass));
        System.out.println("same instance still valid: " +
                (instance instanceof DemoService));
        System.out.println("after old instance: " + instance.message());
        System.out.println("after new instance: " +
                new DemoService().message());
        System.out.println("after static: " + DemoService.counter);
    }
}
~~~

**`manifest.mf`** (lưu dưới dạng văn bản UTF-8 không BOM hoặc ASCII, kết thúc bằng dòng trống):

~~~text
Manifest-Version: 1.0
Premain-Class: HotSwapAgent
Can-Redefine-Classes: true

~~~

Bây giờ từ **thư mục `example`** biên dịch hai phiên bản riêng và đóng JAR:

~~~bash
javac --release 17 -d v1 v1/DemoService.java v1/DefineClassDemo.java v1/HotSwapAgent.java v1/RedefineDemo.java
javac --release 17 -d v2 v2/DemoService.java
jar cfm hotswap-agent.jar manifest.mf -C v1 HotSwapAgent.class

cd v1
java -javaagent:../hotswap-agent.jar RedefineDemo ../v2/DemoService.class
~~~

Trên PowerShell/CMD, có thể dùng dấu `\` thay cho `/` trong các đường dẫn; các lệnh `javac` và `jar` vẫn nhận đường dẫn tương đối như trên. Khi khởi chạy từ `v1`, ứng dụng lấy `DemoService.class` v1 từ class path hiện hành; agent tải bytes v2 từ đường dẫn do caller đưa vào.

**Stdout đã kiểm chứng trên JVM có hỗ trợ redefinition** (Zulu OpenJDK 24, bytecode biên dịch ở mức Java 17):

~~~text
redefine supported: true
before: old
before static: 42
same Class object: true
same instance still valid: true
after old instance: new
after new instance: new
after static: 42
~~~

**Cách đọc:**

1. `redefine supported: true` có được vì **JVM chạy thử và agent manifest** đều cho phép. Đây là **capability cần kiểm tra**, không phải một kết quả bảo đảm trên mọi JVM.
2. `before: old`: instance đã có đang dùng method v1.
3. `before static: 42`: chương trình đã gán giá trị runtime cho field trước redefinition.
4. `redefineClasses(...)` truyền **bytes biên dịch từ cùng binary name `DemoService`** nhưng method body trả `"new"`. Nó tác động đến **cùng class đã nạp**.
5. `same Class object: true`, `same instance still valid: true`: không tạo Class identity mới, không mất instance cũ.
6. `after old instance: new` và `after new instance: new`: những lần invoke mới dùng body method v2 trên **cả instance cũ và mới**.
7. `after static: 42`: initializer v2 có `counter = 999` **không chạy lại**. Giá trị static đang có vẫn là 42.

Lưu ý về hành vi ở JVM khác: nếu `isRedefineClassesSupported()` trả `false` hoặc `isModifiableClass(DemoService.class)` trả `false`, lời gọi có thể bị từ chối. Trong công cụ thực, hãy kiểm tra cả hai, báo lỗi rõ ràng và không cố hot patch khi không hỗ trợ.

### 7.1. Tránh các cách “thay class” không có tác dụng

Các hành động dưới đây **không** tương đương với redefinition trên JVM đang chạy:

- Copy đè `v2/DemoService.class` lên file `v1/DemoService.class` khi `DemoService` đã load: không buộc JVM đang chạy cập nhật method.
- Gọi `Class.forName("DemoService")` lần nữa dưới cùng initiating loader: thường trả class đang có.
- Tạo loader con khác rồi load phiên bản v2: có thể tạo **class khác identity**, không cập nhật những instance do loader cũ tạo.
- Gọi `Lookup.defineClass(v2Bytes)` trong loader đã define cùng binary name: gặp lỗi trùng định nghĩa, không thay code.
- Gọi `ClassLoader.resolveClass(existing)`: liên kết/verifier class chưa link khi cần, **không** nhận replacement bytecode.

## 8. Method đang chạy và thread khác: hai phiên bản có thể chồng lấn tạm thời

Giả sử thread T1 đã vào `service.longOperation()` trước thời điểm redefinition. Trong lúc T1 chưa return, thread T2 thực thi `redefineClasses`. Khi redefinition hoàn tất:

~~~text
T1: ── enter longOperation() v1 ───── [đang chạy v1] ─── return
                         │
T2: ─────────────────── redefineClasses(v2) ──────── done
                                                   │
T3: ────────────────────────────────────────── enter longOperation() v2 ─ return
~~~

Theo API Java instrumentation, **active stack frames vẫn tiếp tục chạy bytecode cũ**; **new invokes** dùng bản mới. Vì vậy một “hot fix” không có nghĩa mọi thao tác đang dở dang **đổi code giữa method**. Nếu method v1 đã nắm tài nguyên, tạo transaction hoặc cập nhật state, nó có thể hoàn thành với giả định cũ sau khi T2 đã cập nhật class.

Hệ quả cho vận hành:

- Xác định vùng dữ liệu/state mà method v1/v2 cùng sử dụng; tránh sửa body theo cách làm hai phiên bản chạy đồng thời gây bất nhất.
- Không mong redefinition chạy lại constructor, `static {}` hoặc migrate object state; schema vẫn bị giới hạn.
- Với thay đổi protocol/data model nghiêm trọng, việc khởi chạy process phiên bản mới hoặc tách class loader/version cùng cầu nối tương thích có thể an toàn hơn.
- Đừng giả định mọi object method handle, reflection cache hoặc thư viện third-party có thể được thay thế/mở rộng schema theo cách công cụ debugger “tưởng như” làm được. Kiểm thử cụ thể trên JVM/container đích.

## 9. Khi nào dùng lớp mới, khi nào dùng hot swap?

**Dùng class mới hoặc loader mới** nếu bạn cần:

- Plugin phiên bản mới tồn tại song song với bản cũ.
- Thêm field/method, thay superclass hoặc đổi public API không thuộc hỗ trợ redefinition chuẩn.
- Tạo implementation runtime khác nhau theo tenant/workload.
- Quản lý vòng đời plugin độc lập, chuyển request mới sang phiên bản mới trong khi request cũ hoàn tất.

Khi reload plugin, thường cần **đổi sang class loader mới** và tạo các instance mới. Để loader cũ được GC và class unload, phải giải phóng các tham chiếu còn sống đến class/object/loader (thread, static registry, thread context loader, caches, listener, `ThreadLocal`...). Đóng `URLClassLoader` giải phóng tài nguyên mở nhưng **không tự bảo đảm** toàn bộ class của nó được unload ngay. Không có nút “force unload class” độc lập đáng tin cậy trong Java SE.

**Dùng `redefineClasses`** nếu bạn cần:

- Hot fix body của một method trong một JVM đang hoạt động, với schema giữ nguyên.
- Sửa code khi debug mà không restart state đang có.
- Cập nhật logic tracing/diagnostic ở class đã load khi JVM và agent hỗ trợ.

**Dùng `retransformClasses`** nếu bạn cần:

- Chạy/áp lại bytecode transformer cho class đã load.
- Cài instrumentation chuyên dụng (coverage, profiler, monitoring) từ transformer có thể retransform.
- Giữ một pipeline biến đổi class có thể được kích hoạt lại có kiểm soát thay vì tự tạo một class file v2 riêng.

Trong production, quyền thay code của agent là quyền rất nhạy cảm: bytecode replacement phải từ nguồn tin cậy, có kiểm tra chữ ký/nguồn gốc, giới hạn tác động và kiểm thử trên phiên bản JVM thực tế.

## 10. Bảng lỗi và cách xác định nhầm thao tác

| Hiện tượng | Cơ chế liên quan | Nguyên nhân & hướng xử lý |
| --- | --- | --- |
| `LinkageError` khi define lần hai | `ClassLoader.defineClass` | Cùng binary name đã được loader đó định nghĩa. Dùng loader khác cho class mới; muốn cập nhật class cũ phải dùng công cụ redefine hợp lệ |
| `NoClassDefFoundError` khi define với tên/bytecode không khớp | `defineClass(name,bytes,...)` | Binary name trong bytes khác `name` yêu cầu; kiểm tra build output |
| `ClassCastException` dù class name giống hệt | Định nghĩa cùng tên ở hai loader | Khác `Class<?>` identity; kiểm tra defining loader và thiết kế shared contract |
| `ClassFormatError`, `UnsupportedClassVersionError` | Define hoặc redefine | Bytes không hợp lệ hoặc class-file version không được JVM đích hỗ trợ |
| `IllegalAccessException` từ `Lookup.defineClass` | Định nghĩa class mới | Lookup thiếu quyền `PACKAGE` hoặc bytes vi phạm điều kiện cùng package |
| `isRedefineClassesSupported() == false` | Instrumentation | Thiếu agent manifest capability hoặc JVM không hỗ trợ |
| `UnmodifiableClassException` | Redefine/retransform | Class đích không thể sửa; kiểm tra `isModifiableClass(clazz)` |
| `UnsupportedOperationException` tại redefinition | Instrumentation/JVMTI | JVM không cho capability hoặc bytes cố đổi schema/đặc tính không được hỗ trợ |
| Class đã redefine nhưng static counter không đổi | Redefine | **Đúng thiết kế**: static fields giữ giá trị, initializer không chạy lại |
| Instance cũ gọi method nhận body mới | Redefine | **Đúng thiết kế**: Class identity giữ nguyên, new invoke dùng code mới |
| Một thread vẫn chạy v1 sau redefinition | Redefine | Active stack frame cũ vẫn chạy bytecode cũ |
| Thay file `.class` trên disk nhưng process vẫn chạy bản cũ | Không phải hot swap | File change không tự kích hoạt redefinition hay class definition mới |
| `retransformClasses` không chạy transformer như mong đợi | Retransform | Agent thiếu `Can-Retransform-Classes: true` hoặc transformer đăng ký không có `canRetransform` |

**Phân loại đúng lỗi:** `LinkageError` do define trùng trong một loader **khác** `UnsupportedOperationException` vì redefinition vượt giới hạn schema. Không sửa lỗi trước bằng cách bật Java agent ngẫu nhiên, và không sửa lỗi sau bằng cách gọi lại `defineClass`.

## 11. Checklist chẩn đoán trước khi thay đổi runtime

1. **Bạn muốn identity mới hay giữ identity cũ?** Nếu cần class mới với API mới, chọn loader/namespace khác. Nếu cần method cũ của instance hiện hữu đổi body, nghĩ đến instrumentation.
2. **Đang có `Class<?>` nào?** In `clazz.getName()`, `clazz.getClassLoader()` và `clazz.getModule()`; so đối tượng `Class<?>` bằng `==`, không chỉ so tên.
3. **Bytes định nghĩa là loại gì?** Kiểm tra binary name, class-file version, bytecode verification, package, superclass và interface constraints.
4. **Có đang gọi `loadClass` hay `defineClass`?** `loadClass` có parent delegation và có thể trả class cũ; `defineClass` mới tạo kiểu nếu loader chưa có binary name đó.
5. **Nếu redefine:** đã có `Instrumentation` từ agent chưa? Manifest `Can-Redefine-Classes: true`? `isRedefineClassesSupported()` và `isModifiableClass` đều được kiểm tra?
6. **Bản replacement có cùng schema không?** So fields, method names/descriptors/modifiers, superclass, interfaces, nest/record/sealed attributes. Không nhầm body change với thêm method.
7. **Có state cần migrate?** Static field/instance field và active frames không được reset. Xem nguy cơ dữ liệu do code v1 và v2 cùng truy cập.
8. **Nếu retransform:** transformer nào được đăng ký và khả năng `canRetransform` ra sao? Bytecode “base” trong pipeline đến từ đâu?
9. **Mục tiêu rollback?** Giữ bản classfile v1 đáng tin cậy nếu định nghĩa lại theo hướng ngược, nhưng rollback không hoàn tác side effects đã xảy ra trong method v2.
10. **Kiểm tra trên JVM đích:** các tính năng instrumentation là optional; khả năng và thông báo lỗi phụ thuộc cấu hình JVM, agent và class đích.

## 12. Câu hỏi tự kiểm tra

**1.** File `Service.class` đã được load; bạn copy đè file mới lên cùng đường dẫn. Các instance đang chạy có tự đổi body method không?  
**Đáp:** Không. Thay file trên đĩa không tự thực hiện `Instrumentation.redefineClasses` và không tự thay class runtime đã được define.

**2.** Bạn gọi `defineClass("api.Service", bytesV2)` trong một **loader khác** khi loader A đang có `api.Service`. Những instance do A tạo sẽ tự chuyển thành class B chứ?  
**Đáp:** Không. Loader B có thể định nghĩa class B cùng tên nhưng **khác `Class<?>`**; instance A vẫn là instance của class A.

**3.** Bạn gọi `defineClass` hai lần với cùng binary name trong cùng defining loader. Kết quả thường là gì?  
**Đáp:** `LinkageError` do duplicate class definition. Không phải hot reload.

**4.** Bạn redefine thành công một class có `static int counter=42`, trong bytes mới initializer ghi `counter=999`. Giá trị runtime tự đổi thành 999 không?  
**Đáp:** Không. Re-definition không chạy lại `<clinit>`; field vẫn giữ giá trị 42 trừ khi code tự thay nó.

**5.** Một instance đã được tạo trước redefinition; gọi method sau khi thành công thì chạy body nào?  
**Đáp:** **Lời gọi mới** chạy body mới. Instance vẫn là instance của cùng `Class<?>`.

**6.** Thread đang nằm giữa `longOperation()` lúc redefine. Nó có chuyển sang body mới ở giữa stack frame không?  
**Đáp:** Không. Active stack frame tiếp tục bytecode cũ; invoke mới dùng code mới.

**7.** Bạn muốn thêm field `newField` mà không restart và chỉ có Java SE 17 instrumentation tiêu chuẩn. `redefineClasses` có hỗ trợ không?  
**Đáp:** Không theo hạn chế cấu trúc của JVMTI Java 17; cần cách triển khai mới như class/loader mới hoặc triển khai mở rộng không thuộc bảo đảm chuẩn.

**8.** `retransformClasses(clazz)` có nhận bytes v2 trong chính lời gọi không?  
**Đáp:** Không. Nó kích hoạt lại pipeline transformer theo quy tắc API. `redefineClasses(new ClassDefinition(clazz,bytesV2))` mới là lời gọi đưa replacement bytes trực tiếp.

**9.** `Lookup.defineHiddenClass` có phải công cụ sửa body của một normal class đã load không?  
**Đáp:** Không. Nó tạo hidden class mới; không redefine class cũ.

**10.** Bạn cần triển khai plugin v2 song song với plugin v1, và v2 thay đổi cấu trúc nhiều class. Nên ưu tiên cơ chế nào?  
**Đáp:** Hai namespace/loader class phù hợp hoặc hai process/service độc lập có contract tương thích, không cố ép mọi thay đổi qua redefinition tiêu chuẩn.

## Tài liệu chuẩn Java 17

- [`ClassLoader.defineClass` (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html)
- [`MethodHandles.Lookup.defineClass` / `defineHiddenClass`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html)
- [`Instrumentation.redefineClasses`, `retransformClasses` và capability checks](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html)
- [`ClassDefinition`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassDefinition.html)
- [`ClassFileTransformer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html)
- [`java.lang.instrument` agent manifest: `Premain-Class`, `Can-Redefine-Classes`, `Can-Retransform-Classes`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html)
- [JVM TI Specification 17: `RedefineClasses` / `RetransformClasses`](https://docs.oracle.com/en/java/javase/17/docs/specs/jvmti.html)
- [JVMS 17 `5.3: Creation and Loading; `5.4: Linking](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html)
- [JLS 17 `12: Execution, class initialization and unloading](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html)
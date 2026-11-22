# Phân biệt sửa mã khi chạy với nạp một phiên bản lớp bằng class loader mới

**Ngữ cảnh:** Java Advance → instrumentation → **Redefinition**.

“Cập nhật mã Java mà không restart JVM” có ít nhất hai cơ chế dễ bị nhầm:

1. **Sửa định nghĩa lớp hiện tại:** `Instrumentation.redefineClasses(...)` thay bytecode của **một runtime class đã được định nghĩa**, trong phạm vi JVM cho phép. Runtime class identity không đổi; instance cũ tiếp tục tồn tại và các lời gọi method mới sử dụng method body đã thay.
2. **Nạp một phiên bản lớp mới bằng `ClassLoader` khác:** VM tạo **một runtime class identity khác** dù hai class files có cùng binary name. Object V1 tiếp tục thuộc class V1; để dùng V2, phải tạo object V2 và chuyển lời gọi/references sang nó.

Hai cách khác nhau ở **class identity, static state, khả năng thay đổi schema, active calls, class unloading, type compatibility và phương án rollback**. Bài viết bao gồm hai lab độc lập với Java 17+, không yêu cầu thư viện bên ngoài: một Java agent redefine cùng lớp đang chạy, và hai `URLClassLoader` nạp đồng thời hai phiên bản cùng tên.

## 1. Hai cơ chế trên cùng một sơ đồ

**Redefinition:**

```text
Một JVM, một defining loader A
  Class<?> C = demo.Service @ A
          │
          ├─ V1: message() trả "v1"
          │     object old = new Service()
          │
          ▼
  redefineClasses(C, bytesV2)
          │
          ▼
  Vẫn Class<?> C = demo.Service @ A
  object old vẫn có getClass() == C
  old.message() trên lần gọi mới trả "v2"
```

**Loader mới:**

```text
Một JVM
  Loader A                          Loader B
     │                                │
  demo.Service V1                  demo.Service V2
  Class<?> C1                     Class<?> C2
     │                                │
  Object old                      Object fresh
  old.message() -> "v1"           fresh.message() -> "v2"

C1.getName().equals(C2.getName()) == true
C1 == C2                             == false
```

**Không có thao tác “đổi class” của object V1** khi chỉ tạo loader B. Những references đang trỏ tới V1 vẫn như cũ. Ngược lại, khi `redefineClasses` thành công, một instance V1 được tạo trước đó có thể thực thi method body mới trong những lời gọi **sau** redefinition.

## 2. Bảng quyết định nhanh

| Khía cạnh | `Instrumentation.redefineClasses` | Nạp cùng tên qua loader mới |
| --- | --- | --- |
| Runtime class identity | Giữ **cùng** `Class<?>` và defining loader | Tạo class identity **khác** nếu defining loader thật sự khác |
| Đối tượng đang tồn tại | Giữ nguyên identity/fields; lời gọi mới có thể thấy code mới | Tiếp tục thuộc V1 và chạy code V1 |
| Có cần tạo object V2? | Không bắt buộc để chạy method V2 | Thông thường **có** |
| Static state | Giá trị static được **giữ nguyên**; không chạy lại `<clinit>` | Mỗi class identity có static fields và class initialization riêng |
| Method body | Thay được trong phạm vi JVM hỗ trợ | Version V2 có code mới độc lập |
| Field/method schema | Bị giới hạn: không tùy ý thêm/xóa/đổi tên fields/methods | Class mới có thể khác schema, nhưng phải tương thích clients |
| Superclass/interfaces | Không tùy ý đổi inheritance | Class mới có thể đổi trong ràng buộc linkage/ABI |
| Code đang chạy trong stack frames | Active frames có thể tiếp tục bytecode cũ | Calls đã bắt đầu ở V1 vẫn tiếp tục V1 |
| Chạy hai versions song song lâu dài | Không phải cơ chế per-request versioning của cùng class identity | Có thể giữ V1/V2 song song và route theo tenant/request |
| Cần Java agent/JVMTI capability | Có, qua `Instrumentation` hoặc tooling tương ứng | Không bắt buộc |
| Cast V1 ↔ V2 | Không sinh ra type mới chỉ vì redefine | Hai classes cùng tên nhưng khác loader **không cast được** mặc định |
| Thu hồi bản cũ | Không tạo class identity mới chỉ để thay body | V1 có thể unload khi loader và references đủ điều kiện GC |
| Độ phức tạp vận hành | Schema restrictions, runtime verification, active frames | Delegation, SPI, routing, cleanup, metaspace và state migration |

Đừng suy từ “hot reload” rằng một cơ chế làm được tất cả. **Sửa một method** và **thay một module/plugin phiên bản mới** là hai bài toán vận hành khác nhau.

## 3. Vì sao cùng tên lớp vẫn là hai kiểu Java khác nhau?

Theo **JVMS `5.3**, danh tính class/interface ở runtime được xác định bởi:

```text
(binary name, defining class loader)
```

Tên `demo.VersionedService` chỉ là một thành phần. Nếu `LoaderA` định nghĩa `demo.VersionedService` và `LoaderB` cũng định nghĩa class file với cùng tên, JVM có hai class identities.

### 3.1. Defining loader khác initiating loader

- **Defining loader** thực sự định nghĩa class từ bytes; đó là loader tham gia runtime type identity.
- **Initiating loader** nhận yêu cầu tải class và có thể ủy quyền cho một loader khác.
- Với chiến lược **parent-first** thông thường, child loader có thể nhận lại class V1 **do parent định nghĩa**, thay vì tự định nghĩa V2.

Vì thế **hai đối tượng ClassLoader riêng** không tự bảo đảm hai class identities. Muốn biết đã nạp phiên bản mới hay chưa, kiểm tra **`Class<?>` object và defining loader thực tế**, không chỉ tên hoặc đường URL được cấu hình.

Ví dụ fragment:

```java
// Giả định twoObjects được tạo ở những class loaders đã xác định.
Class<?> a = firstObject.getClass();
Class<?> b = secondObject.getClass();

System.out.println(a.getName().equals(b.getName()));
System.out.println(a == b);
System.out.println(a.getClassLoader() == b.getClassLoader());
System.out.println(b.isInstance(firstObject));
```

Đây **không phải chương trình độc lập** vì `firstObject` và `secondObject` chưa khai báo. Nếu hai class identities khác nhau nhưng cùng binary name, các dòng thường tương ứng `true`, `false`, `false`, `false`.

### 3.2. Package và module boundaries

Một **run-time package** được nhận diện bởi package name **và defining loader**. Hai class cùng `package demo` nhưng khác loader không tự có cùng package-private access. Khi dùng JPMS, còn cần kiểm tra module reads, exports/opens và module layers.

Class-loader separation nhằm quản lý **namespace/dependencies và version**, không mặc nhiên là một sandbox có quyền bảo mật riêng đối với hệ điều hành hay tài nguyên JVM.

## 4. Redefinition thực sự thay gì?

API chuẩn trong `java.lang.instrument.Instrumentation`:

```java
// Fragment: instrumentation có kiểu java.lang.instrument.Instrumentation.
Class<?> target = Service.class;
byte[] candidateBytes = Files.readAllBytes(candidatePath);
instrumentation.redefineClasses(
        new ClassDefinition(target, candidateBytes));
```

Đây **chỉ là fragment**; cần import `ClassDefinition`, `Files` và khai báo `Service`, `candidatePath`. `ClassDefinition` gắn **đúng runtime Class target** với **class-file bytes** thay thế. Không dùng `ClassLoader.defineClass` để ghi đè lại định nghĩa cũ trong cùng namespace.

### 4.1. Những hành vi được Javadoc nêu rõ

1. **Lời gọi method mới** sau thành công dùng bytecode mới của method được redefine.
2. **Active stack frames** (đã bước vào method trước redefinition) tiếp tục chạy bytecode **cũ** cho lượt gọi đó. Không tự chuyển program counter ở giữa method sang bản mới.
3. **Instances hiện có** không bị hủy, không đổi class identity và không bị reset fields.
4. **Static fields** giữ giá trị đang có. Replacing `<clinit>` bytecode không làm JVM **chạy lại class initializer** chỉ vì redefine.
5. **Constructors** không được gọi lại trên objects hiện có. Nếu body constructor đổi trong khuôn khổ hợp lệ, những lần tạo object mới sau đó có thể chịu ảnh hưởng.
6. Redefinition **không tự rollback** side effects đã xảy ra: thay code không khôi phục DB, external messages, static caches hoặc dữ liệu object.
7. `redefineClasses` có thể xử lý **một tập các ClassDefinitions** cho thay đổi phụ thuộc lẫn nhau; cần đọc lỗi/hợp đồng transaction của JVM, không suy đoán hỗ trợ mọi schema.

### 4.2. Schema restrictions

Trên các JVM/JVMTI triển khai thông dụng, bạn có thể đổi method bodies, một số constant-pool/attributes phù hợp, nhưng **không tự do**:

- Thêm, xóa hoặc đổi tên fields/methods.
- Thay descriptors/signatures và cấu trúc superclass/interfaces.
- Thay các cấu trúc metadata/hierarchy bị ràng buộc, ví dụ nest relationships.
- Đưa class-file version hoặc bytecode verification không được VM hỗ trợ.

Các hạn chế phải được kiểm tra theo **VM/vendor/version**. Những phép đổi schema phức tạp thường nên nạp class mới bằng loader mới hoặc restart process. Không coi thành công trên một môi trường debug là bảo đảm tương thích mọi JVM.

Kiểm tra capability:

```java
// Fragment: inst, clazz phải được khai báo trong chương trình.
boolean supported = inst.isRedefineClassesSupported();
boolean modifiable = inst.isModifiableClass(clazz);
```

Một Java agent yêu cầu `Can-Redefine-Classes: true` trong manifest; **cờ này không đủ** nếu VM không cung cấp capability. Các lỗi có thể là `UnmodifiableClassException`, `UnsupportedOperationException`, `ClassFormatError`, `NoClassDefFoundError` hoặc `UnsupportedClassVersionError`, tùy nguyên nhân.

### 4.3. Redefinition khác retransformation

`redefineClasses` được cung cấp **bytes hoàn chỉnh mới** cho class đã load. `retransformClasses` yêu cầu VM chạy lại **pipeline transformer** xuất phát từ initial class bytes theo quy tắc của `ClassFileTransformer`. Hai đường có cơ chế riêng, nhưng cùng hướng vào **class identity hiện tại**. Nếu mục tiêu là duy trì hai versions cùng tên chạy song song cho những calls mới khác nhau, một lượt redefine trên cùng runtime class không cung cấp điều đó.

## 5. Class loader mới thực sự tạo gì?

`URLClassLoader` có thể nạp `demo.VersionedService` V2 từ một thư mục mới, ngay khi V1 đang chạy ở loader khác. Nó định nghĩa một **class mới**, không “patch” V1.

Hệ quả:

- **Object V1 vẫn V1**; các lời gọi qua object đó không đổi chỉ vì tạo V2.
- **Object V2 mới** chạy code V2 và có class identity V2.
- Mỗi class có **static state và class initialization riêng**.
- Một object từ V1 không thể cast sang V2 chỉ vì hai `Class.getName()` giống nhau.
- V2 có thể bổ sung schema khác, nhưng callers bên ngoài phải dùng shared interface/protocol tương thích.
- Phải **chuyển references hoặc route** sang V2. Không switch thì client vẫn dùng V1.
- Class V1 và loader V1 có thể bị giữ sống bởi callbacks, threads, `ThreadLocal`, static registries, reflection caches và object graph.

### 5.1. Vì sao tạo loader mới vẫn nhận lại V1?

Ví dụ minh họa:

```java
// Fragment, URL object và classpath cần được thiết lập trước.
URLClassLoader child = new URLClassLoader(
        new URL[] {newVersionUrl});
Class<?> type = child.loadClass("demo.VersionedService");
```

Constructor này mặc định dùng system loader làm parent. Nếu parent đã biết `demo.VersionedService` V1 thì `child.loadClass` có thể **ủy quyền** và trả chính V1. Vì vậy tên “new loader” không đủ; kiểm tra:

```java
// Fragment.
System.out.println(type.getClassLoader() == child);
```

Nếu `false`, runtime class được defining loader khác tạo (thường là parent). Không nên bật child-first một cách tùy tiện cho toàn bộ JDK/framework: cấu hình class loading không phù hợp có thể gây `LinkageError` và các lỗi type compatibility.

## 6. Lab Java 17+: cùng class V1/V2, hai kỹ thuật độc lập

Cấu trúc thư mục:

```text
hot-reload-lab/
├── agent.mf
├── src/
│   └── demo/
│       ├── VersionedService.java       (V1)
│       ├── RedefineAgent.java
│       ├── MainRedefine.java
│       └── MainLoaders.java
├── next-src/
│   └── demo/
│       └── VersionedService.java       (V2)
├── out/                                (tạo khi build)
└── replacement/                        (tạo khi build)
```

Điểm quan trọng là **hai tệp nguồn trùng package/name phải biên dịch riêng**, không đưa cùng lúc vào một lệnh `javac`. Cần JDK 17+ chứa `javac`, `java` và `jar`. Không cần ASM/Maven.

### 6.1. V1 — `src/demo/VersionedService.java`

```java
package demo;

public final class VersionedService {
    public static int counter = 1;

    public String message() {
        return "v1";
    }
}
```

### 6.2. V2 — `next-src/demo/VersionedService.java`

```java
package demo;

public final class VersionedService {
    public static int counter = 100;

    public String message() {
        return "v2";
    }
}
```

Hai class files giữ nguyên **tên, fields, constructor mặc định và method descriptor**, chỉ đổi method body và giá trị viết bởi static initializer. Điều này cho phép chứng minh:

- Với **redefine**, static value đã có được giữ nguyên thay vì khởi tạo lại thành 100.
- Với **loader mới**, V1 và V2 được initialize riêng; V2 có thể bắt đầu bằng `counter=100`.

## 7. Thí nghiệm A: thay body trên class đang chạy

### 7.1. Agent — `src/demo/RedefineAgent.java`

```java
package demo;

import java.lang.instrument.ClassDefinition;
import java.lang.instrument.Instrumentation;
import java.nio.file.Files;
import java.nio.file.Path;

public final class RedefineAgent {
    private static volatile Instrumentation instrumentation;

    private RedefineAgent() {}

    public static void premain(String args, Instrumentation inst) {
        instrumentation = inst;
    }

    public static void replace(Class<?> clazz, Path classFile)
            throws Exception {
        Instrumentation inst = instrumentation;
        if (inst == null) {
            throw new IllegalStateException("Start with -javaagent");
        }
        if (!inst.isRedefineClassesSupported()) {
            throw new IllegalStateException("Redefinition not supported");
        }
        if (!inst.isModifiableClass(clazz)) {
            throw new IllegalStateException("Class not modifiable");
        }

        byte[] replacement = Files.readAllBytes(classFile);
        inst.redefineClasses(new ClassDefinition(clazz, replacement));
    }
}
```

Agent nhận `Instrumentation` qua `premain` khi JVM khởi động. Ta dùng **startup `-javaagent`**, không dùng dynamic attach, nên ví dụ không phụ thuộc quyền attach/self-attach hoặc chính sách tải agent sau startup. Đường `classFile` phải trỏ tới bytes hợp lệ của **chính `demo.VersionedService`**, không được nhầm với một class name khác.

### 7.2. Main — `src/demo/MainRedefine.java`

```java
package demo;

import java.nio.file.Path;

public final class MainRedefine {
    private MainRedefine() {}

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: MainRedefine <replacement-class-file>");
        }

        VersionedService original = new VersionedService();
        Class<?> before = original.getClass();

        System.out.println("BEFORE=" + original.message());

        VersionedService.counter = 7;
        System.out.println("STATE_BEFORE="
                + VersionedService.counter);

        RedefineAgent.replace(before, Path.of(args[0]));

        System.out.println("SAME_CLASS="
                + (before == original.getClass()));
        System.out.println("AFTER=" + original.message());
        System.out.println("STATE_AFTER="
                + VersionedService.counter);
    }
}
```

`original` được tạo **một lần trước** khi redefinition diễn ra. Method `message` được gọi lần thứ hai **trên chính object ấy**. `Class<?> before` là một reference tới identity của loaded class, không phải một snapshot của method body.

### 7.3. Agent manifest — `agent.mf`

```text
Manifest-Version: 1.0
Premain-Class: demo.RedefineAgent
Can-Redefine-Classes: true
```

File manifest phải có newline cuối. `Can-Redefine-Classes: true` yêu cầu capability; nếu VM không hỗ trợ, code báo lỗi thông qua `isRedefineClassesSupported()` thay vì lặng lẽ khẳng định thành công.

### 7.4. Lệnh build

Tại thư mục `hot-reload-lab`, tạo hai thư mục output nếu chưa có (trên PowerShell có thể dùng `New-Item -ItemType Directory -Force out,replacement`; trên Linux/macOS có thể dùng `mkdir -p out replacement`).

```bash
javac --release 17 -d out src/demo/VersionedService.java src/demo/RedefineAgent.java src/demo/MainRedefine.java
javac --release 17 -d replacement next-src/demo/VersionedService.java
jar --create --file redefine-agent.jar --manifest agent.mf -C out demo/RedefineAgent.class
```

Hai compiler invocations tạo ra:

```text
out/demo/VersionedService.class          (V1)
replacement/demo/VersionedService.class  (V2)
redefine-agent.jar                       (startup agent)
```

Dùng `--release 17` ở cả hai để giảm khả năng thất bại do candidate class file vượt class-file version của JVM. Build **không** ghi đè V1 bằng V2.

### 7.5. Chạy redefinition

```bash
java -javaagent:redefine-agent.jar -cp out demo.MainRedefine replacement/demo/VersionedService.class
```

Trên HotSpot/JDK hỗ trợ redefinition, với project và source y hệt trên, stdout **kỳ vọng chính xác**:

```text
BEFORE=v1
STATE_BEFORE=7
SAME_CLASS=true
AFTER=v2
STATE_AFTER=7
```

- `BEFORE=v1`: object chạy method V1.
- `STATE_BEFORE=7`: code chỉnh static counter.
- `SAME_CLASS=true`: `Class<?>` identity **không bị thay**.
- `AFTER=v2`: **cùng object cũ** nhận method body mới trong lời gọi tiếp theo.
- `STATE_AFTER=7`: JVM **không chạy lại `<clinit>`** dù source V2 khai báo `counter=100`.

Nếu VM không hỗ trợ redefinition, kết quả thành công này không xuất hiện; cần kiểm tra lỗi thật sự thay vì đổi kỳ vọng thành “mọi VM chạy được”. Bài lab cố ý không đổi field/method schema và không thêm classloader mới.

### 7.6. Vì sao active frames là một ngoại lệ quan trọng?

Nếu thread A vào `service.longTask()` phiên bản V1 và chưa thoát, thread B redefine thành công, frame của thread A tiếp tục body **V1** cho lời gọi đang chạy, còn lời gọi mới sau redefine dùng body **V2**. Vì vậy redefinition không tự bảo đảm “mọi thread dùng V2 ngay tại cùng một thời điểm”.

Timeline:

```text
T0: Thread-A enter method V1
T1: Thread-B redefine target to V2
T2: redefineClasses returns successfully
T3: Thread-C invokes method -> V2
T4: Thread-A leaves its existing frame -> V1
```

Đây là **sơ đồ tình huống**, không phải output của lab. Đừng chạy migration field/lock protocol thiếu tương thích trong lúc V1 active frames vẫn có thể hoạt động.

## 8. Thí nghiệm B: nạp V1 và V2 bằng hai loaders

Lần này **không chạy `-javaagent` và không gọi `redefineClasses`**. Chúng ta giữ cùng hai class files đã biên dịch, nhưng yêu cầu hai loaders khác nhau tự định nghĩa `demo.VersionedService`. Dùng **platform loader** làm parent để tránh system/app loader trên classpath `out` nạp sẵn V1 rồi trả nó cho cả hai child loaders.

### 8.1. `src/demo/MainLoaders.java`

```java
package demo;

import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class MainLoaders {
    private MainLoaders() {}

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "Usage: MainLoaders <v1-dir> <v2-dir>");
        }

        URL[] firstPath = {
                Path.of(args[0]).toAbsolutePath().toUri().toURL()
        };
        URL[] secondPath = {
                Path.of(args[1]).toAbsolutePath().toUri().toURL()
        };
        ClassLoader parent = ClassLoader.getPlatformClassLoader();

        try (URLClassLoader first = new URLClassLoader(firstPath, parent);
             URLClassLoader second = new URLClassLoader(secondPath, parent)) {

            Class<?> typeV1 = Class.forName(
                    "demo.VersionedService", true, first);
            Class<?> typeV2 = Class.forName(
                    "demo.VersionedService", true, second);

            Object objectV1 =
                    typeV1.getDeclaredConstructor().newInstance();
            Object objectV2 =
                    typeV2.getDeclaredConstructor().newInstance();

            System.out.println("SAME_NAME="
                    + typeV1.getName().equals(typeV2.getName()));
            System.out.println("SAME_CLASS=" + (typeV1 == typeV2));
            System.out.println("DIFFERENT_LOADERS="
                    + (typeV1.getClassLoader()
                            != typeV2.getClassLoader()));

            System.out.println("OLD="
                    + typeV1.getMethod("message").invoke(objectV1));
            System.out.println("NEW="
                    + typeV2.getMethod("message").invoke(objectV2));
            System.out.println("OLD_AFTER_NEW="
                    + typeV1.getMethod("message").invoke(objectV1));

            typeV1.getField("counter").setInt(null, 7);
            System.out.println("V1_COUNTER="
                    + typeV1.getField("counter").getInt(null));
            System.out.println("V2_COUNTER="
                    + typeV2.getField("counter").getInt(null));

            System.out.println("NEW_IS_OLD="
                    + typeV2.isInstance(objectV1));
            try {
                typeV2.cast(objectV1);
            } catch (ClassCastException failure) {
                System.out.println("CAST=ClassCastException");
            }
        }
    }
}
```

Bài lab dùng reflection để không buộc compiler liên kết trực tiếp với đúng một `VersionedService` từ classpath của app. `Class.forName(name,true,loader)` yêu cầu nạp **và initialize class** do loader đã chọn cung cấp. `getPlatformClassLoader()` là parent phù hợp cho bài lab vì nó không nhìn thấy các application classes ở thư mục `out`.

Trong hệ thống plugin thực, parent thường cần thấy **shared API/SPI** chứ không phải chỉ platform classes; loader arrangement ở đây là để quan sát class identity rõ ràng.

### 8.2. Biên dịch, chạy

Biên dịch `MainLoaders` sau khi có `out` và hai versions:

```bash
javac --release 17 -d out src/demo/MainLoaders.java
java -cp out demo.MainLoaders out replacement
```

Stdout **chính xác với hai bản class ở mục 6**:

```text
SAME_NAME=true
SAME_CLASS=false
DIFFERENT_LOADERS=true
OLD=v1
NEW=v2
OLD_AFTER_NEW=v1
V1_COUNTER=7
V2_COUNTER=100
NEW_IS_OLD=false
CAST=ClassCastException
```

Các dòng này chứng minh nhiều điều:

- `SAME_NAME=true` nhưng `SAME_CLASS=false`: cùng tên **không có nghĩa** cùng kiểu runtime.
- `DIFFERENT_LOADERS=true`: defining loaders khác nhau.
- `OLD_AFTER_NEW=v1`: tạo class/object V2 không làm object V1 thay behavior.
- `V1_COUNTER=7` và `V2_COUNTER=100`: static fields độc lập theo mỗi runtime class.
- `NEW_IS_OLD=false`: object V1 không phải instance của type V2.
- `CAST=ClassCastException`: V2 không tự chấp nhận object V1 dù có cùng name và method structure.

Khi rời `try`, hai `URLClassLoader` được `close()` để giải phóng những tài nguyên tải class phù hợp. **Đóng loader không đồng nghĩa JVM unload class ngay**; class/object references còn sống có thể giữ loader lại.

### 8.3. Nhìn lại sự khác nhau giữa hai stdout

| Thí nghiệm A | Thí nghiệm B |
| --- | --- |
| `SAME_CLASS=true` | `SAME_CLASS=false` |
| `AFTER=v2` trên **object cũ** | `OLD_AFTER_NEW=v1` trên **object cũ** |
| `STATE_AFTER=7` dù V2 khai báo 100 | `V2_COUNTER=100` do class V2 initialize riêng |
| Không thấy lỗi ép kiểu vì vẫn một identity | `CAST=ClassCastException` do hai identities khác nhau |
| Cần capability redefine | Không cần instrumentation capability |

Chính đối chiếu này là cách kiểm tra tốt hơn việc chỉ băm hai file `.class` hoặc chỉ xem `Class.getName()`.

## 9. Giữ API chung khi nạp version mới

Một hệ thống plugin muốn cho V1 và V2 cùng giao tiếp với ứng dụng nên xác định rõ **ranh giới class loaders**. Pattern phổ biến:

```text
Parent/shared loader:
    interface Handler {
        Response handle(Request request);
    }
    Handler active;

Child loader V1:
    class HandlerV1 implements Handler

Child loader V2:
    class HandlerV2 implements Handler
```

Đây là **pseudocode kiến trúc**, chưa phải Java source runnable: `Handler`, `Response` và `Request` cần định nghĩa đầy đủ. Điều kiện quan trọng là cả hai implementations thực sự implement **cùng `Handler` runtime interface do parent định nghĩa**, không phải mỗi plugin định nghĩa một bản cùng tên trong child loader.

Nếu method signatures nhắc tới DTO do mỗi child định nghĩa riêng, **loading constraints** và kiểu runtime có thể trở nên không tương thích. Hệ thống có thể phát sinh `ClassCastException` hoặc `LinkageError: loader constraint violation`. Không xử lý bằng cách ép kiểu bừa hoặc copy bytes vào đúng tên package; phải thiết kế shared API ownership.

### 9.1. Chuyển route bằng một reference chung

Một thiết kế thích hợp cho request boundary:

```text
AtomicReference<Handler> active
       │
  Request 1 lấy HandlerV1 ──► xử lý trọn trên V1
       │
  Deploy V2 / health-check / active.set(V2)
       │
  Request 2 lấy HandlerV2 ──► xử lý trọn trên V2
```

Fragment Java:

```java
// Fragment: active, Handler, Request/Response đã khai báo.
Handler selected = active.get();
Response response = selected.handle(request);

// Sau khi V2 đã khởi tạo và qua kiểm tra:
active.set(newHandlerV2);
```

`AtomicReference.set` publish binding mới nhưng không tự migrate state, đóng resources V1, chờ các requests cũ, hay bảo đảm một transaction được xử lý ở đúng một version. Quy trình thực tế cần graceful draining và theo dõi version đang xử lý request.

### 9.2. Khi nào chọn loader mới?

- Muốn chạy **V1 và V2 song song** trong cùng JVM (canary, multi-tenant, blue/green plugin).
- Cần **thêm fields/methods hoặc đổi cấu trúc class** mà redefinition thông thường cấm.
- Cần tách dependency versions giữa modules/plugin instances.
- Có shared SPI ổn định cùng quy trình tạo object mới, chuyển route và cleanup.

Đánh đổi: phải quản lý nhiều object graphs, classloaders, static caches, resources, compatibility và bộ nhớ.

## 10. Lifecycle và memory leak khi reload class loader

Không có một lệnh Java SE bảo đảm “unload lớp V1 ngay lập tức”. Một class chỉ có thể được thu hồi khi loader và những references liên quan đủ điều kiện GC, phụ thuộc VM.

Các nguồn giữ loader V1 thường gặp:

- Static registry trong parent loader còn chứa V1 instance hoặc `Class<?>`.
- Thread, `ThreadLocal` hoặc executor task vẫn giữ V1 object/TCCL.
- Timers, listeners, callbacks, schedulers và shutdown hooks chưa unregister.
- Framework/DI caches lưu `Class`, `Method`, `MethodHandle`, constructors, annotations.
- JDBC driver/logging/metrics/tracing libraries giữ references hoặc threads do plugin tạo.
- ClassLoader-to-class references, JNI/native global refs, resource URLs hoặc unmanaged file handles.

`URLClassLoader.close()` giúp đóng file handles/JAR access, **không xóa mọi Java references** và không bảo đảm GC. Một plugin reload liên tục có thể làm tăng metaspace/heap nếu loaders cũ còn reachable.

Một handover an toàn thường:

1. Tạo và verify V2.
2. Khởi tạo dependencies/health checks.
3. Chuyển route có kiểm soát.
4. Chặn requests mới vào V1 và cho requests cũ hoàn thành.
5. Unregister callbacks/listeners, stop threads, đóng resources.
6. Xóa strong references/caches trong parent và TCCL.
7. Đóng loader cũ khi phù hợp, quan sát class unloading/metaspace.
8. Giữ rollback policy cho state và external side effects.

**New loader không phải quyền thực thi hạn chế**: cùng JVM vẫn chia sẻ process memory, OS credentials, filesystem và nhiều tài nguyên nền. Đừng dùng nó thay sandbox bảo mật.

## 11. Sửa code khi đang có nhiều threads

Redefinition và loader switching đều có **chồng lấn thời gian**:

### 11.1. Với redefinition

```text
T0: Thread A vào Service.longTask V1
T1: Thread B redefine Service thành V2
T2: redefineClasses thành công
T3: Thread C gọi Service.longTask => V2
T4: Thread A hoàn tất frame đã chạy => V1
```

Javadoc của `Instrumentation` quy định active stack frames tiếp tục dùng bytecode cũ. Vì vậy V1/V2 code có thể cùng tồn tại về thực thi trong khoảng chuyển tiếp, dù runtime Class identity là một.

### 11.2. Với loader mới

```text
T0: Request A lấy handler V1
T1: Load V2, tạo object V2
T2: Router chuyển active reference sang V2
T3: Request B lấy V2
T4: Request A hoàn thành bằng V1
```

Ở đây bạn có thể **chủ động** kiểm soát routing/draining theo request. Tuy nhiên vẫn cần xử lý shared state và side effects khi V1/V2 cùng hoạt động.

### 11.3. Static state khác dữ liệu bên ngoài

Redefinition giữ giá trị static fields **trong cùng class**. New loader có static fields riêng. Nhưng cả hai vẫn có thể cùng ghi **một database table**, message topic hoặc static registry nằm trong **class của loader cha**. Tách class identity không tự tách side effects hay external state.

## 12. Rollback và lựa chọn vận hành

**Rollback redefinition:** nếu giữ bytes V1 và JVM vẫn hỗ trợ, có thể redefine cùng class về method body V1. Nhưng **state fields và thay đổi ngoài process** không tự trở lại. Frames V2 đã active trước rollback có thể tiếp tục code V2.

**Rollback loader mới:** nếu V1 instance/loader còn sống, có thể chuyển route lại V1; hoặc tạo loader mới từ V1 artifacts. Nhưng không undo data/side effects của V2 đã thực thi, và không tự dừng V2 đang xử lý requests.

**Rolling restart/process replacement** thường thích hợp hơn nếu thay đổi lớn đụng schema, native libraries, global singletons, JPMS module boundaries hay không quản lý được lifecycle của code cũ. “Không restart” không đồng nghĩa “ít rủi ro”.

### Ma trận lựa chọn thực tế

| Nhu cầu | Hướng ưu tiên |
| --- | --- |
| Sửa nhỏ một method phục vụ debug/instrumentation | Redefinition (nếu VM hỗ trợ) |
| Thêm field/method mới hoặc đổi public API | Loader mới hoặc rolling restart |
| Chạy V1/V2 cùng lúc cho tenant A/B | Loader mới với version routing |
| Giữ lại cùng object và state cũ | Redefinition; nhưng phải đảm bảo V2 hiểu state hiện tại |
| Cô lập hai versions của dependency/plugin | Class-loader isolation có kiểm soát |
| Đổi ứng dụng với shared state và native resources phức tạp | Process restart/rolling deployment |
| Rollback an toàn với database migrations | Cần migration/rollback độc lập, không kỹ thuật Java nào tự giải quyết |

## 13. Lỗi điển hình và hướng chẩn đoán

| Hiện tượng | Nguyên nhân khả dĩ | Cách kiểm tra |
| --- | --- | --- |
| `isRedefineClassesSupported() == false` | VM/manifest không cấp capability | Đọc agent manifest, runtime vendor, VM flags |
| `UnmodifiableClassException` | Target class không modifiable | `isModifiableClass(clazz)` và loại target |
| `UnsupportedOperationException` | Unsupported schema/capability | So fields/method names/descriptors, hierarchy |
| `ClassFormatError` | Replacement file không hợp lệ | `javap -v`, compiler output, kiểm tra class bytes |
| `NoClassDefFoundError` ở redefine | Binary name candidate khác target | So `this_class` của class file |
| `UnsupportedClassVersionError` | Candidate build bằng JDK quá mới | `javac --release` phù hợp target |
| V2 method không được gọi | Chưa redefine thành công, nhầm target class/loader, hoặc đang ở active frame V1 | Log đúng Class identity và thời điểm |
| Static value không thành 100 sau redefine | Đúng ngữ nghĩa: `<clinit>` không chạy lại | Thiết kế state migration riêng |
| Loader mới nhưng class vẫn là V1 | Parent delegation đã nhận V1 | So `getClassLoader()` với loader mong đợi |
| `ClassCastException` với cùng class name | Khác defining loaders | Thiết kế shared SPI/DTO |
| `LinkageError` / loader constraint | Dependency type names trỏ tới identities khác | So owner loader của interface/DTO/dependencies |
| Loader cũ không unload | Strong refs, threads, TCCL, listeners, caches | Cleanup, heap dump, class loading diagnostics |
| App vẫn gọi object V1 sau load V2 | Router/reference chưa được switch | Kiểm tra binding và request-scoped selection |
| V2 cần field mới mà redefine bị từ chối | Thay schema ngoài khả năng RedefineClasses | Loader mới hoặc deploy process |
| Hot swap làm kết quả không nhất quán | V1 frames và V2 calls chồng lấn, state không compatible | Test concurrent transition, draining/quiescence |

Đừng nhầm `ClassNotFoundException` (loader không tìm class), `NoClassDefFoundError` (link/definition error), `ClassCastException` (type identity incompatibility) và `UnsupportedOperationException` (đổi không được JVM hỗ trợ). Mỗi loại yêu cầu cách xử lý khác.

## 14. Checklist kiểm thử

- [ ] Đã xác định **đúng mục tiêu**: same runtime class hay new runtime class identity?
- [ ] Với redefine: có `Can-Redefine-Classes: true`, `isRedefineClassesSupported()` và `isModifiableClass()`.
- [ ] Candidate V2 bytes có cùng binary name, classfile version và schema được VM cho phép.
- [ ] So behavior trên **same existing instance trước và sau** redefinition.
- [ ] Xác nhận static state không bị reset và `<clinit>` không tự chạy lại.
- [ ] Kiểm thử active frames, locking và state compatibility khi V1/V2 code có thể chồng lấn.
- [ ] Với loader mới: kiểm tra **defining loader**, không chỉ tên loader hay binary class name.
- [ ] Thử `classV1 == classV2` và `classV2.isInstance(objectV1)`.
- [ ] Test interface/DTO types dùng chung từ parent, class-loader constraints và JPMS access.
- [ ] Nếu switch plugin, tạo V2 object và đổi route rõ ràng, không giả định object V1 tự chuyển kiểu.
- [ ] Dọn thread/TCCL, callbacks, caches, listeners và resources của V1.
- [ ] Quan sát metaspace/classloading sau nhiều lần reload để phát hiện leaks.
- [ ] Có rollback policy cho **code và dữ liệu**; rollback code không rollback database.
- [ ] So kết quả và ngoại lệ trên nhiều inputs; không chỉ so SHA-256 của .class files.
- [ ] Với thay đổi cấu trúc lớn, cân nhắc rolling restart thay vì ép redefinition.

## 15. Tự kiểm tra

1. **Hai `Class<?>` có cùng `getName()` nhưng khác `getClassLoader()`. Chắc chắn là cùng runtime type?**  
   Không. Tên không đủ; defining loader là một phần class identity.

2. **Sửa `message()` bằng redefinition thành công, object V1 cũ có cần tạo lại để trả V2 không?**  
   Không. Lời gọi mới tới method body V2 có thể thực hiện trên object cũ.

3. **V1 static counter đã là 7, V2 source gán 100. Sau redefine vẫn 7 nghĩa là lỗi?**  
   Không. Replacing class definition không chạy lại `<clinit>`.

4. **Nạp V2 bằng loader B rồi gọi method trên object V1. Tại sao vẫn V1?**  
   Vì object V1 vẫn thuộc class V1 của loader A; không bị chuyển identity.

5. **Hai URLClassLoaders khác nhau luôn trả hai Class objects khác nhau?**  
   Không. Cả hai có thể ủy quyền cho cùng parent loader; cần kiểm tra defining loader.

6. **V2 bổ sung method hoặc field. Redefinition có chắc cho phép không?**  
   Không. Những structural changes thường ngoài phạm vi hỗ trợ. Loader mới tạo runtime type mới nếu ABI thiết kế phù hợp.

7. **Active stack frame V1 có được tự chuyển sang body V2 sau redefine?**  
   Không. Javadoc cho biết frames đã chạy tiếp tục bytes cũ; new invocations dùng bản mới.

8. **Tại sao `typeV2.cast(objectV1)` có thể ném `ClassCastException` dù getName giống nhau?**  
   Vì hai runtime class identities khác nhau.

9. **Đóng `URLClassLoader` có unload class ngay lập tức?**  
   Không. Còn references và hành vi GC; `close()` không buộc unload.

10. **Muốn cả V1 và V2 implement cùng `Handler`, phải đặt interface ở đâu?**  
    Ở shared parent loader để cùng một runtime interface được sử dụng, không tạo duplicate types trong child.

11. **Cần canary theo tenant A/B, chỉ redefine một class có tạo per-tenant version không?**  
    Không. New loader identities và routing thích hợp hơn.

12. **Rollback V2 body về V1 có tự đảo mọi writes DB của V2 không?**  
    Không. Cần kế hoạch data migration/compensation riêng.

13. **Redefinition và retransformation có giống nạp lớp bằng loader mới không?**  
    Không. Cả redefine và retransform nhắm definition của class đã load; new loader tạo identity mới khi định nghĩa class độc lập.

14. **Vì sao phải kiểm tra state đồng thời khi active V1 frames và V2 calls chồng lấn?**  
    Vì có thể khác kỳ vọng lock, field invariants và external protocol trong cùng process.

## 16. Tài liệu chính thức

- Oracle JDK 17 — **`Instrumentation`, `redefineClasses`, capability, state và active frames**: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html
- Oracle JDK 17 — **`ClassDefinition`**: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassDefinition.html
- Oracle JDK 17 — **`java.lang.instrument` package**, `Premain-Class` và `Can-Redefine-Classes`: https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html
- JVMS 17 — **Chapter 5: Loading, Linking, and Initializing**, identity theo binary name + defining loader: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html
- Oracle JDK 17 — **`ClassLoader`**, parent delegation và platform loader: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- Oracle JDK 17 — **`URLClassLoader`**, URL classpaths và `close()`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html
- Oracle JDK 17 — **`Class`**, `getName()`, `getClassLoader()`, `isInstance` và `cast`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
- JVM TI — **`RedefineClasses`** schema restrictions và method activation behavior: https://docs.oracle.com/javase/8/docs/platform/jvmti/jvmti.html#RedefineClasses

**Chốt kiến thức:** Khi cần giữ objects/class identity và chỉ thay method implementation trong khuôn khổ VM cho phép, hãy cân nhắc **`redefineClasses`**. Khi cần chạy nhiều versions song song, thay schema hoặc thay cả plugin lifecycle, cần **một defining class loader mới + instance V2 + cơ chế route rõ ràng**. Trong cả hai phương án, kiểm tra active calls, state và khả năng rollback thay vì chỉ xác nhận class file V2 đã được đọc.

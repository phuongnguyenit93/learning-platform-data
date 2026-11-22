# Kiểm tra khả năng redefine và khả năng sửa của từng lớp

**Redefinition** là cơ chế thay class-file bytes của một lớp **đã được JVM nạp** bằng lời gọi `Instrumentation.redefineClasses(ClassDefinition...)`. Một Java agent không được mặc định gọi thao tác này chỉ vì lớp đang tồn tại hoặc vì JVM có hỗ trợ instrumentation. Trước tiên phải kiểm tra **hai điều kiện khác nhau**:

- `Instrumentation.isRedefineClassesSupported()`: JVM **trong cấu hình của agent hiện tại** có cấp capability redefine hay không. Điều này đòi hỏi JAR agent khai báo `Can-Redefine-Classes: true` **và** JVM thực sự hỗ trợ.
- `Instrumentation.isModifiableClass(targetClass)`: **lớp cụ thể** có được phép sửa định nghĩa không. Kết quả này **không phụ thuộc** vào việc agent có được cấp quyền redefine hay không.

Chỉ khi cả hai trả `true`, agent mới nên chuẩn bị bytes mới và gọi `redefineClasses(...)`. Ngay cả lúc ấy, class-file bytes thay thế vẫn phải đúng tên lớp, đúng phiên bản và tuân giới hạn thay đổi cấu trúc. Hai boolean là **điều kiện cần, không phải bảo đảm thành công**.

Bài này trình bày hợp đồng Java SE 17, manifest, cách chọn đúng `Class<?>`, giới hạn thay bytecode, kiểm tra lỗi, và một chương trình Java 17+ được biên dịch/chạy với **hai agent JAR có cùng code nhưng khác manifest**.

## 1. Đừng gộp hai lớp kiểm tra làm một

| Điều muốn biết | Lời gọi | Câu trả lời thực sự |
| --- | --- | --- |
| Agent này có thể redefine lớp đã nạp không? | `inst.isRedefineClassesSupported()` | `true` nếu manifest agent yêu cầu redefine và VM hiện tại hỗ trợ. |
| Class X có thuộc nhóm JVM có thể sửa không? | `inst.isModifiableClass(X.class)` | `true` nếu class X modifiable về nguyên tắc; **không** nói agent đã có capability. |
| Có thể chạy lại transformer cho lớp đã nạp không? | `inst.isRetransformClassesSupported()` | Khả năng **retransform**, độc lập redefine. |
| Module có thể thay reads/exports/opens? | `inst.isModifiableModule(module)` | Điều kiện sửa module, **không thay thế** kiểm tra class. |

Xét bốn trạng thái:

| Redefine supported | Class modifiable | Cách xử lý |
| --- | --- | --- |
| `false` | `false` | Không gọi redefine; kiểm tra cả manifest/VM và class. |
| `false` | `true` | **Không gọi redefine**: class có thể sửa về nguyên tắc nhưng agent chưa có quyền. |
| `true` | `false` | **Không gọi redefine**: capability chung có nhưng class bị từ chối. |
| `true` | `true` | Có thể chuẩn bị `ClassDefinition` **hợp lệ** rồi thử redefine; vẫn phải xử lý lỗi. |

Mô hình quyết định:

```text
JVM khởi chạy/nạp agent
        |
        v
Agent nhận Instrumentation
        |
        v
isRedefineClassesSupported() ?
        |
        +-- false --> Không redefine; kiểm tra manifest và JVM
        |
        +-- true
              |
              v
        Xác định đúng Class<?> đã nạp
              |
              v
        isModifiableClass(clazz) ?
              |
              +-- false --> Bỏ qua class cụ thể này
              |
              +-- true
                    |
                    v
            Xác thực class-file bytes thay thế
                    |
                    v
            redefineClasses(new ClassDefinition(clazz, bytes))
                    |
                    v
            Xử lý thành công/ngoại lệ, kiểm chứng runtime
```

**Không suy ngược:** `isModifiableClass(clazz) == true` không bao hàm `isRedefineClassesSupported() == true`. Java SE 17 API ghi rõ kết quả của `isModifiableClass` không bị ảnh hưởng bởi hai capability `isRedefineClassesSupported` và `isRetransformClassesSupported`. Đây chính là tình huống mà ví dụ chạy được ở phần sau sẽ thể hiện.

## 2. Manifest `Can-Redefine-Classes`: điều kiện cấp agent

Nếu dùng startup agent với `-javaagent`, manifest **bên trong JAR** cần:

```text
Manifest-Version: 1.0
Premain-Class: demo.redefine.ProbeAgent
Can-Redefine-Classes: true

```

`Premain-Class` xác định class có `public static void premain(String, Instrumentation)` (hoặc overload một tham số) để JVM gọi **trước application `main`**. `Can-Redefine-Classes: true` yêu cầu capability redefine. JVM chỉ có thể báo supported khi **cả manifest lẫn VM hỗ trợ**; nó không chỉ căn cứ vào version Java.

Những trường hợp khác:

| Nội dung manifest | Ý nghĩa |
| --- | --- |
| `Can-Redefine-Classes: true` | Yêu cầu quyền redefine. |
| `Can-Redefine-Classes: TRUE` | Giá trị boolean không phân biệt hoa/thường; tương đương `true`. |
| `Can-Redefine-Classes: false` | Không yêu cầu quyền. |
| **Không có** `Can-Redefine-Classes` | Mặc định `false`. |
| `Can-Redefine-Classes: yes` | Không phải `true` nên được hiểu là `false`. |

Chỉ file `agent.mf` trên đĩa có dòng `true` **không đủ**. Lúc chạy JVM xem `META-INF/MANIFEST.MF` của **đúng JAR agent được truyền vào `-javaagent`**. Quá trình shading, repackaging hoặc CI/CD có thể thay manifest. Nếu runtime trả `false`, kiểm tra artifact thực tế thay vì chỉ đọc file manifest nguồn.

### 2.1. Nếu attach agent vào JVM đã chạy

Với agent được nạp động bằng Attach API (khi JVM và môi trường cho phép), entry point là `Agent-Class` và `agentmain(...)`:

```text
Manifest-Version: 1.0
Agent-Class: demo.redefine.DynamicAgent
Can-Redefine-Classes: true

```

Đây là **manifest minh họa cơ chế**, không phải file dùng trong ví dụ chạy ở dưới; bài thực hành dùng `ProbeAgent` với `Premain-Class`. Các quyền attach process và chính sách dynamic loading là chuyện riêng: **attach thành công không chứng minh có quyền redefine**. Dù nạp bằng `premain` hay `agentmain`, agent phải kiểm tra capability từ đối tượng `Instrumentation` được cấp.

### 2.2. Redefine khác retransform

Hai manifest capability không tương đương:

| Cơ chế | Manifest | API hỏi quyền | API thực thi |
| --- | --- | --- | --- |
| Redefinition | `Can-Redefine-Classes: true` | `isRedefineClassesSupported()` | `redefineClasses(new ClassDefinition(clazz, bytes))` |
| Retransformation | `Can-Retransform-Classes: true` | `isRetransformClassesSupported()` | `retransformClasses(clazz)` |

**Redefine dùng bytes mới do caller cấp**, thường để hot-patch/fix-and-continue. **Retransform chạy lại quá trình biến đổi** dựa trên bytes nền theo quy tắc instrumentation; transformer muốn được gọi lại lúc retransformation phải đăng ký `canRetransform=true`. Agent cần tính năng nào thì phải khai báo và kiểm tra tính năng đó, không dùng cờ của tính năng kia thay thế.

## 3. Kiểm tra `isRedefineClassesSupported()` tại runtime

Trong `premain`/`agentmain`, agent nhận đối tượng `Instrumentation`:

```java
// Mã minh họa bên trong agent, inst đã được JVM truyền vào.
boolean canRedefine = inst.isRedefineClassesSupported();
if (!canRedefine) {
    System.out.println("Redefinition unavailable");
    // Chọn degraded mode hoặc báo lỗi chức năng theo thiết kế.
}
```

Theo tài liệu Java SE 17, `isRedefineClassesSupported()` trả cùng kết quả trong **một lần khởi tạo JVM**. Không có lý do kỳ vọng nó tự bật từ `false` sang `true` chỉ do ứng dụng nạp thêm class hoặc sửa file manifest ở ngoài tiến trình.

Khi `false`, nếu cố gọi `redefineClasses(...)`, JVM có thể ném `UnsupportedOperationException`. Một agent có thể xử lý mềm bằng cách vẫn ghi metric/tracing cho **class load tương lai** bằng transformer bình thường, nhưng **không được báo sai rằng đã hot-redefine lớp đang chạy**.

Đừng xem `java -version` là câu trả lời cho capability. Version cho biết API có tồn tại trong bộ JDK nhưng capability là thuộc tính **tùy chọn** của VM và cấu hình cụ thể của agent.

## 4. Kiểm tra `isModifiableClass(clazz)` cho mỗi class

API:

```java
// Mã minh họa; clazz là Class<?> đã xác định đúng.
boolean modifiable = inst.isModifiableClass(clazz);
```

Nó kiểm tra xem JVM có thể sửa định nghĩa của **class cụ thể**, không thử một bản patch và không kiểm tra manifest quyền redefine. Java SE 17 ghi rõ:

- **Primitive classes** như `int.class`, `boolean.class` và `void.class` **không** modifiable.
- **Array classes** như `String[].class`, `int[][].class` **không** modifiable.
- Các class khác còn phụ thuộc JVM. Không khẳng định mọi class trong `java.*` đều không modifiable hoặc mọi class của ứng dụng đều modifiable.

Ví dụ:

```java
System.out.println(inst.isModifiableClass(int.class));      // false
System.out.println(inst.isModifiableClass(String[].class)); // false
```

Ngay cả khi `isRedefineClassesSupported()==true`, hai class trên vẫn cho `false`. Ngược lại, một class Java thường có thể cho `modifiable=true` ngay cả khi agent **không** có capability redefine. Hai phép kiểm tra phải được dùng **cùng lúc**.

### 4.1. Chọn đúng `Class<?>` và class loader

Trong JVM, danh tính lớp không chỉ là chuỗi tên: còn có **defining class loader**. Hai class loader khác nhau có thể định nghĩa hai lớp cùng tên `com.example.Service` từ bytes khác nhau.

Đoạn minh họa:

```java
// Đoạn mã trong công cụ, không phải chương trình Java độc lập.
// applicationLoader là class loader đã được xác định đúng.
Class<?> target = Class.forName(
        "com.example.Service", false, applicationLoader);
if (inst.isRedefineClassesSupported()
        && inst.isModifiableClass(target)) {
    // Tiếp theo phải kiểm tra bytes mới trước redefine.
}
```

Dùng `Class.forName(name, false, loader)` để tránh buộc class khởi tạo chỉ vì lookup (khi có thể). `getAllLoadedClasses()` cũng có thể cung cấp các `Class<?>` đã nạp, nhưng cần lọc theo tên, loader, module và phạm vi sản phẩm. Không lấy class đầu tiên trùng tên rồi tự gán bytes từ một JAR khác.

**Lưu ý:** `isModifiableModule(module)` phục vụ thay opens/exports/reads của module; nó không thay cho `isModifiableClass(clazz)` và không chứng minh class-file bytes mới được chấp nhận.

### 4.2. Nhiều class đã nạp

Với danh sách lớp lớn, cần lọc theo mục tiêu nghiệp vụ trước khi thử đổi định nghĩa. Mẫu khái niệm:

```java
// Mã minh họa bên trong agent, inst đã có.
// Chỉ tạo danh sách ứng viên; CHƯA redefine class nào.
java.util.List<Class<?>> candidates = new java.util.ArrayList<>();
if (inst.isRedefineClassesSupported()) {
    for (Class<?> c : inst.getAllLoadedClasses()) {
        if (c.getName().startsWith("com.example.")
                && inst.isModifiableClass(c)) {
            candidates.add(c);
        }
    }
}
```

Đoạn này **chưa đủ để gọi `redefineClasses`**: cần một cặp `Class<?>` + `byte[]` thay thế riêng cho **từng** class và kiểm tra chúng tương thích. Quét toàn JVM rồi redefine bừa mọi class modifiable là nguy hiểm, có thể tốn tài nguyên và va chạm với các agent khác.

## 5. Chuẩn bị `ClassDefinition`: class đúng và bytes hợp lệ

Đối tượng `ClassDefinition` buộc một `Class<?>` đã nạp với bytes mới:

```java
// Mã minh họa trong một phương thức đã có targetClass, path và inst.
byte[] bytes = java.nio.file.Files.readAllBytes(path);
java.lang.instrument.ClassDefinition definition =
        new java.lang.instrument.ClassDefinition(targetClass, bytes);
inst.redefineClasses(definition);
```

Ở đây, `bytes` là **JVM class-file bytes**, không phải văn bản Java hoặc URL. Constructor `ClassDefinition(Class<?>, byte[])` **không clone mảng đầu vào**; nó chỉ giữ tham chiếu. Chuẩn bị và xác thực mảng hoàn chỉnh trước lời gọi, không mutate mảng sau khi đã tạo `ClassDefinition` — đặc biệt khi có nhiều thread.

Những yêu cầu đối với bytes thay thế:

1. **Đúng binary name của class** mà `Class<?>` đang đại diện. Nếu file chứa tên khác, `NoClassDefFoundError` có thể được ném.
2. **Version được hỗ trợ** bởi JVM đang chạy; version vượt quá VM có thể gây `UnsupportedClassVersionError`.
3. **Không thay đổi schema bị cấm**, chẳng hạn thêm/xóa/đổi tên field hoặc method, đổi descriptor, modifiers hoặc hierarchy trái quy tắc redefinition hiện hành.
4. **Classfile hợp lệ**, constant pool, stack map frames, branch offsets, exception handlers và các attribute cần thiết vẫn nhất quán.
5. **Tương thích với transformer khác**: những `ClassFileTransformer` đang đăng ký có thể nhận sự kiện redefine và tác động tiếp đến bytes; không mặc định class bytes cuối cùng giống y hệt bản patch đưa vào.

`isModifiableClass(clazz)==true` **không** kiểm tra năm điều kiện trên. Một bản patch thêm field mới có thể bị JVM từ chối dù bạn đã qua preflight hai boolean.

### 5.1. Redefine không phải tự tìm file trên disk

`redefineClasses` dùng chính bytes truyền qua `ClassDefinition`. Nó **không** tự biên dịch lại source, đọc lại file class theo tên hoặc nạp lại JAR đã deploy. Công cụ thực tế phải biết bytes đến từ đâu, đảm bảo provenance, release, checksum và độ tin cậy; không chấp nhận patch không xác thực từ đường dẫn ngoài do người lạ kiểm soát.

## 6. Ví dụ Java 17+: so sánh JAR agent có và không có quyền redefine

Thí nghiệm có hai bản `Greeting.java` cùng package và cùng thành phần class, nhưng method `message()` trả chuỗi khác nhau. Agent sẽ kiểm tra hai điều kiện và **nếu được phép** đổi method body **trên class đã nạp** bằng bytes của bản patch.

Cấu trúc thư mục:

```text
redefine-demo/
├── src/
│   ├── main/demo/redefine/
│   │   ├── Greeting.java
│   │   ├── ProbeAgent.java
│   │   └── App.java
│   └── patch/demo/redefine/
│       └── Greeting.java
├── agent-on.mf
└── agent-off.mf
```

Hai file `Greeting.java` nằm ở hai thư mục khác nhau, nhưng cùng package. Bản base được biên dịch vào `out/`, bản patch biên dịch vào `patch/`. **Chỉ `out/` nằm trong runtime classpath**; `patch/` là nguồn bytes cho redefinition, không phải một class loader khác.

### 6.1. `src/main/demo/redefine/Greeting.java` — bản gốc

```java
package demo.redefine;

public class Greeting {
    private final int id;
    private static int initializationCount;

    static {
        initializationCount++;
    }

    public Greeting(int id) {
        this.id = id;
    }

    public String message() {
        return "original-" + id;
    }

    public static int initializationCount() {
        return initializationCount;
    }
}
```

Field `id` giúp nhận biết đối tượng đang tồn tại; biến `initializationCount` kiểm tra việc `<clinit>` có bị gọi lại sau redefine hay không.

### 6.2. `src/patch/demo/redefine/Greeting.java` — bản patch

```java
package demo.redefine;

public class Greeting {
    private final int id;
    private static int initializationCount;

    static {
        initializationCount++;
    }

    public Greeting(int id) {
        this.id = id;
    }

    public String message() {
        return "updated-" + id;
    }

    public static int initializationCount() {
        return initializationCount;
    }
}
```

Hai bản giữ **cùng tên class, field, constructor, method descriptors và superclass**. Chúng chỉ khác **thân method `message()`**, không thêm cấu trúc mới. Nếu đổi tên method hay thêm field, bạn đã thay đổi schema và có thể bị từ chối.

### 6.3. `src/main/demo/redefine/ProbeAgent.java` — kiểm tra trước khi redefine

```java
package demo.redefine;

import java.io.IOException;
import java.lang.instrument.ClassDefinition;
import java.lang.instrument.Instrumentation;
import java.lang.instrument.UnmodifiableClassException;
import java.nio.file.Files;
import java.nio.file.Path;

public final class ProbeAgent {
    private static Instrumentation instrumentation;

    private ProbeAgent() {}

    public static void premain(String options, Instrumentation inst) {
        instrumentation = inst;
        System.out.println("[agent] redefineSupported="
                + inst.isRedefineClassesSupported());
        System.out.println("[agent] primitiveModifiable="
                + inst.isModifiableClass(int.class));
        System.out.println("[agent] arrayModifiable="
                + inst.isModifiableClass(String[].class));
    }

    public static void redefineIfPossible(Class<?> target, Path replacement)
            throws IOException, ClassNotFoundException, UnmodifiableClassException {
        Instrumentation inst = instrumentation;
        if (inst == null) {
            throw new IllegalStateException("Start with -javaagent");
        }
        boolean modifiable = inst.isModifiableClass(target);
        System.out.println("[agent] targetModifiable=" + modifiable);
        if (!inst.isRedefineClassesSupported() || !modifiable) {
            System.out.println("[agent] skip redefine");
            return;
        }

        byte[] classBytes = Files.readAllBytes(replacement);
        inst.redefineClasses(new ClassDefinition(target, classBytes));
        System.out.println("[agent] redefine complete");
    }
}
```

Agent lưu `Instrumentation` nhận trong `premain`. Nó in capability và modifiability của primitive/array, sau đó expose hàm nhỏ để ứng dụng minh họa gọi. Với agent production, thao tác redefine nên được điều khiển từ một management interface của agent thay vì buộc ứng dụng business gọi trực tiếp.

Lời gọi `redefineIfPossible` chỉ đọc bytes **sau khi cả hai điều kiện đạt**. Dòng log `redefine complete` chỉ xuất hiện **sau khi `redefineClasses` trả về bình thường**. Bài thực hành chạy tuần tự trên main thread; trong thiết kế đa luồng cần quản lý an toàn việc publication đối tượng `Instrumentation` và vòng đời của agent.

### 6.4. `src/main/demo/redefine/App.java`

```java
package demo.redefine;

import java.nio.file.Path;

public final class App {
    private App() {}

    public static void main(String[] args) throws Exception {
        Greeting existing = new Greeting(7);
        System.out.println("[app] before=" + existing.message());
        System.out.println("[app] initCountBefore="
                + Greeting.initializationCount());

        ProbeAgent.redefineIfPossible(Greeting.class,
                Path.of("patch", "demo", "redefine", "Greeting.class"));

        System.out.println("[app] after=" + existing.message());
        System.out.println("[app] newObject=" + new Greeting(9).message());
        System.out.println("[app] initCountAfter="
                + Greeting.initializationCount());
    }
}
```

Chúng ta **giữ nguyên instance `existing`** trước và sau redefine. Nếu thành công, các lần gọi method mới trên instance cũ có thể dùng code mới, trong khi `id` không tự thay. Biến static `initializationCount` sẽ cho thấy JVM không tự chạy lại static initializer.

### 6.5. Hai manifest

Nội dung `agent-on.mf`:

```text
Manifest-Version: 1.0
Premain-Class: demo.redefine.ProbeAgent
Can-Redefine-Classes: true

```

Nội dung `agent-off.mf`:

```text
Manifest-Version: 1.0
Premain-Class: demo.redefine.ProbeAgent

```

Hai JAR chứa **cùng code** của `ProbeAgent`; chỉ khác manifest. Giữ ký tự xuống dòng cuối file manifest.

### 6.6. Biên dịch và tạo agent JAR

Tại thư mục `redefine-demo/`, với Bash:

```bash
mkdir -p out patch

javac --release 17 -d out \
  src/main/demo/redefine/Greeting.java \
  src/main/demo/redefine/ProbeAgent.java \
  src/main/demo/redefine/App.java

javac --release 17 -d patch \
  src/patch/demo/redefine/Greeting.java

jar --create --file agent-on.jar --manifest agent-on.mf \
  -C out demo/redefine/ProbeAgent.class

jar --create --file agent-off.jar --manifest agent-off.mf \
  -C out demo/redefine/ProbeAgent.class
```

Với Windows PowerShell (mỗi lệnh một dòng):

```powershell
New-Item -ItemType Directory -Force -Path out,patch | Out-Null
javac --release 17 -d out src/main/demo/redefine/Greeting.java src/main/demo/redefine/ProbeAgent.java src/main/demo/redefine/App.java
javac --release 17 -d patch src/patch/demo/redefine/Greeting.java
jar --create --file agent-on.jar --manifest agent-on.mf -C out demo/redefine/ProbeAgent.class
jar --create --file agent-off.jar --manifest agent-off.mf -C out demo/redefine/ProbeAgent.class
```

`--release 17` tạo mã nguồn/classfile phù hợp Java 17. Không có thư viện ngoài nào cần thêm. Sau build:

```text
out/demo/redefine/Greeting.class     định nghĩa ban đầu
out/demo/redefine/ProbeAgent.class   entry point của agent
out/demo/redefine/App.class          main class
patch/demo/redefine/Greeting.class   bytes định nghĩa thay thế
agent-on.jar                          JAR khai báo capability
agent-off.jar                         JAR không khai báo capability
```

**Không thêm `patch/` vào `-cp`**. Chương trình đọc file patch bằng `Files.readAllBytes` từ working directory. Nếu chạy `java` ở thư mục khác, đường dẫn `patch/...` có thể không tồn tại.

### 6.7. Chạy agent có quyền redefine

```bash
java -javaagent:agent-on.jar -cp out demo.redefine.App
```

Stdout **đã kiểm chứng trên Zulu/OpenJDK 24.0.2**, với mã biên dịch `--release 17`:

```text
[agent] redefineSupported=true
[agent] primitiveModifiable=false
[agent] arrayModifiable=false
[app] before=original-7
[app] initCountBefore=1
[agent] targetModifiable=true
[agent] redefine complete
[app] after=updated-7
[app] newObject=updated-9
[app] initCountAfter=1
```

Phân tích:

1. Agent yêu cầu `Can-Redefine-Classes: true`, và JVM thử nghiệm cấp capability.
2. Primitive `int.class` và array `String[].class` không modifiable dù agent có quyền.
3. Lớp `Greeting.class` có `modifiable=true` trong JVM này.
4. Agent dùng bytes từ `patch/.../Greeting.class` trong `ClassDefinition`, redefine thành công.
5. **Chính đối tượng `existing` cũ** gọi `message()` lần nữa và trả `updated-7`. Đối tượng mới trả `updated-9`.
6. `initializationCount` vẫn bằng `1`, vì redefinition không tự chạy lại `<clinit>`.

### 6.8. Chạy agent không khai báo quyền redefine

```bash
java -javaagent:agent-off.jar -cp out demo.redefine.App
```

Stdout trên cùng Zulu/OpenJDK 24.0.2:

```text
[agent] redefineSupported=false
[agent] primitiveModifiable=false
[agent] arrayModifiable=false
[app] before=original-7
[app] initCountBefore=1
[agent] targetModifiable=true
[agent] skip redefine
[app] after=original-7
[app] newObject=original-9
[app] initCountAfter=1
```

Kết quả `targetModifiable=true` **vẫn xuất hiện**, dù `redefineSupported=false` do thiếu manifest capability. Agent đã kiểm tra điều kiện và **không gọi `redefineClasses`**, nên mã phương thức của bản gốc không đổi.

Hai lệnh chạy được thực hiện trên **hai JVM mới riêng biệt**. Trên JVM vendor/cấu hình khác, `isRedefineClassesSupported` và `isModifiableClass` có thể khác; chỉ các trường hợp primitive/array không modifiable là điều kiện được đặc tả nhất quán.

### 6.9. Kiểm tra JAR và hai class file

```bash
jar --list --file agent-on.jar
jar --list --file agent-off.jar
javap -p -s -classpath out demo.redefine.Greeting
javap -p -s -classpath patch demo.redefine.Greeting
```

Hai lệnh `javap` cho phép đối chiếu **field/method descriptors và tên class** giữa bản gốc và patch. Có thể dùng thêm `javap -v` để xem classfile version, constant pool, thuộc tính. Chúng đọc artifact trên đĩa, **không phải bytecode đã được redefine trong JVM**.

Đọc mục `META-INF/MANIFEST.MF` **bên trong từng JAR** bằng công cụ xem ZIP/JAR: `agent-on.jar` phải có `Can-Redefine-Classes: true`, `agent-off.jar` không có. Chỉ nhìn tên file JAR chưa chứng minh manifest đúng.

## 7. Ý nghĩa của “redefine thành công” đối với JVM đang chạy

Redefinition không có nghĩa JVM “load lại class từ đầu” hoặc tự tạo đối tượng mới. Một số hệ quả quan trọng:

- **Instance cũ vẫn tồn tại**, các field giữ giá trị ban đầu. Bài thực hành minh họa instance `existing` giữ `id=7` nhưng method `message()` ở lần invoke mới chạy code mới.
- **Static state giữ nguyên**; `<clinit>` không được tự chạy lại. Do đó `initializationCount` vẫn `1`, kể cả khi class file patch vẫn khai báo static initializer.
- **Active stack frames**: nếu thread đang thực thi method cũ khi redefine, frame đang chạy có thể tiếp tục dùng bytecode cũ; các lần invoke mới dùng định nghĩa mới. Không giả định mọi luồng lập tức đổi opcode ngay giữa method.
- **Class identity không đổi**: bạn thay định nghĩa của một `Class<?>` đã nạp, không định nghĩa class khác cùng tên bằng loader khác.
- **Các transformer khác có thể tham gia** trong quá trình redefine, vì vậy bytes đã cài vào JVM có thể khác bytes ban đầu do caller cấp.
- **Không có rollback tự động** chỉ từ việc bỏ agent hoặc đóng kết nối điều khiển. Muốn trở về logic cũ, cần chuẩn bị bytes hợp lệ của định nghĩa cũ và áp dụng lại (nếu JVM cho phép), cùng kiểm tra trạng thái runtime.

Vì vậy một hot-patch có thể thay code method thành công nhưng vẫn làm business logic sai nếu code mới không tương thích với **giá trị static và trạng thái instance đã tồn tại**.

## 8. Hạn chế class schema và lỗi sau hai phép kiểm tra

Dù cả hai boolean trả `true`, JVM vẫn có thể từ chối bytes mới. Trong redefinition thông thường, có thể thay method bodies và metadata phù hợp nhưng **không tự ý thay class schema**:

- Thêm, xóa hoặc đổi tên field/method.
- Đổi method descriptor, modifiers hoặc interface/superclass hierarchy bị cấm.
- Đổi các structural attributes như `NestHost`, `NestMembers`, `Record` hoặc `PermittedSubclasses` trái quy tắc JVMTI.
- Trả bytes không hợp lệ hoặc chứa opcode/stack-map/constant-pool references sai.
- Dùng classfile version mới hơn runtime hỗ trợ.

Một bản patch chỉ thay chuỗi trong `message()` như ví dụ là trường hợp tối giản. Nếu muốn biến đổi method body phức tạp, sử dụng bytecode library hoặc Class-File API thích hợp và chạy verifier/test trên JVM đích.

| Lỗi / tình huống | Nguyên nhân và hướng xử lý |
| --- | --- |
| `isRedefineClassesSupported()==false` | Kiểm tra `Can-Redefine-Classes` trong manifest thực tế hoặc JVM không cấp quyền. |
| `isModifiableClass(clazz)==false` | Class này không thể sửa; primitive/array luôn false, lớp khác phụ thuộc VM. |
| `modifiable=true` nhưng `supported=false` | Không gọi redefine: quyền cấp agent không đủ. |
| `UnsupportedOperationException` | VM không cho phép redefine **hoặc** thay đổi cấu trúc class vượt giới hạn. |
| `UnmodifiableClassException` | Có class được yêu cầu redefine không modifiable. |
| `ClassFormatError` / `VerifyError` | Bytes class file sai cấu trúc hoặc bytecode verification thất bại. |
| `NoClassDefFoundError` | Tên class trong bytes thay thế không khớp class đích. |
| `UnsupportedClassVersionError` | JVM không hiểu classfile version của bytes mới. |
| `ClassCircularityError` / `LinkageError` | Các lỗi về cấu trúc phụ thuộc hoặc liên kết sau biến đổi. |
| `NullPointerException` | Đưa null vào `ClassDefinition` hoặc mảng `ClassDefinition...`. |
| `IOException` đọc patch | Đường dẫn sai, thiếu quyền hoặc tệp không tồn tại — xảy ra trước bước redefine. |

Lời gọi API `redefineClasses(ClassDefinition...)` khai báo `throws ClassNotFoundException, UnmodifiableClassException`. Tài liệu Java SE 17 ghi `ClassNotFoundException` có mặt **chỉ để tương thích** và không được phương thức này phát sinh thực tế. Chương trình mẫu vẫn khai báo nó vì compiler yêu cầu theo method signature.

**Tính nguyên tử đối với một tập class:** Nếu `redefineClasses(...)` ném exception cho một mảng `ClassDefinition`, theo hợp đồng **không class nào trong tập được redefined**. Điều này hữu ích khi nhiều class có phụ thuộc nhau, nhưng không có nghĩa cách chọn bytes/build artifact bên ngoài tự được rollback; bạn phải chuẩn bị hết dữ liệu trước khi gọi.

## 9. Quy trình chẩn đoán theo thứ tự

Nếu công cụ báo “redefine không hoạt động”, nên kiểm tra theo luồng sau, tránh đoán mò theo tên JVM:

1. **Đúng agent JAR?** Dò `-javaagent:path.jar` hoặc đường dẫn Attach thực tế; kiểm tra `META-INF/MANIFEST.MF` của file đó.
2. **Entry point đúng?** Với startup cần `Premain-Class` và `premain`; với attach cần `Agent-Class` và `agentmain` (nếu hỗ trợ).
3. **Có cờ capability?** `Can-Redefine-Classes: true` trong manifest agent đúng; `Can-Retransform-Classes` không thay thế.
4. **Runtime báo gì?** In `isRedefineClassesSupported()` ngay sau khi nhận `Instrumentation`; nếu false, không thử redefine.
5. **Class mục tiêu là ai?** Xác nhận binary name, defining loader, module và `Class<?>` đã chọn. Đừng dùng resource `Foo.class` của loader khác làm bytes patch mà không kiểm tra.
6. **Class có modifiable không?** Hỏi `isModifiableClass(target)` cho **từng** class, không suy luận từ capability chung.
7. **Patch có hợp lệ không?** Đối chiếu hai bản bằng `javap -p -s`, classfile version và kiểm tra bytecode output; bảo đảm method/field schema còn tương thích.
8. **Có transformer khác không?** Nếu có, xem thứ tự transform và bytes sau mỗi bước; lỗi có thể phát sinh sau khi bytes patch được đưa vào.
9. **Báo lỗi nào?** Phân biệt `UnsupportedOperationException`, `UnmodifiableClassException`, class format/linkage và IOException khi đọc file.
10. **Hậu kiểm runtime:** Chạy lại method trên instance cũ/mới, xác nhận state và luồng đang chạy. Không kết luận toàn bộ ứng dụng ổn chỉ vì lời gọi API không ném exception.

Đối với production, dùng patch có nguồn tin cậy, checksum/chữ ký phù hợp, audit log, staging test và kế hoạch phục hồi. Redefinition có thể thay hành vi ứng dụng với quyền cao; không để đường dẫn patch không được xác thực điều khiển.

## 10. Một số ngộ nhận cần tránh

| Ngộ nhận | Hiểu đúng |
| --- | --- |
| “Java agent có thể redefine mọi class.” | JVM capability tùy chọn, và từng class còn phải modifiable. |
| “`isModifiableClass==true` nghĩa là quyền redefine đã bật.” | Sai: kiểm tra này không phụ thuộc capability. |
| “Chỉ cần manifest khai báo true thì JVM chắc chắn hỗ trợ.” | Sai: còn cần JVM cho phép. |
| “Có `Can-Retransform-Classes` là đủ để gọi redefine.” | Sai: hai quyền riêng. |
| “Class `String[].class` là class bình thường nên sửa được.” | Sai: array/primitive classes luôn không modifiable. |
| “Đã pass hai boolean thì có thể thêm field mới.” | Sai: giới hạn thay đổi schema vẫn áp dụng. |
| “`ClassDefinition` tự lấy bytes từ disk.” | Sai: caller phải cung cấp `byte[]` mới. |
| “`ClassDefinition` tự clone bytes nên có thể sửa mảng ở thread khác.” | Sai: nó giữ tham chiếu mảng đầu vào. |
| “Redefine chạy lại constructor của instance cũ.” | Sai: instance giữ field values cũ. |
| “Redefine chạy lại `<clinit>` để reset static.” | Sai: static state còn nguyên. |
| “Mọi stack frame cũ lập tức chuyển sang method body mới.” | Sai: active frames có thể tiếp tục dùng code cũ. |
| “Đổi JAR trên disk tự đổi class đã nạp.” | Sai: cần lời gọi redefine với bytes hợp lệ hoặc cơ chế khác. |

## 11. Bài tập tự kiểm tra

**Câu 1.** Agent có `isModifiableClass(Greeting.class)==true`, nhưng `isRedefineClassesSupported()==false`. Có nên gọi `redefineClasses`?

**Đáp án:** Không. Class có thể sửa về nguyên tắc, nhưng agent thiếu capability. Kiểm tra manifest/JVM và không gọi API.

**Câu 2.** Nếu `Can-Redefine-Classes: true` nhưng `isModifiableClass(int.class)==false` thì sao?

**Đáp án:** Bỏ qua primitive class. Capability chung không làm primitive/array trở thành modifiable.

**Câu 3.** Tại sao hai JAR trong ví dụ chứa cùng `ProbeAgent.class` mà output capability khác?

**Đáp án:** `agent-on.jar` khai báo `Can-Redefine-Classes: true`, còn `agent-off.jar` thiếu cờ (mặc định false). JVM trong ví dụ có hỗ trợ khi agent yêu cầu.

**Câu 4.** Vì sao `existing.message()` trả `updated-7` sau redefine nhưng `initializationCount` vẫn `1`?

**Đáp án:** Lần gọi method **mới** dùng code mới, trong khi instance và static state không bị khởi tạo lại. JVM không tự gọi `<clinit>` khi redefine.

**Câu 5.** Một bản patch thêm field `extra`, dù class modifiable và VM supported. Có chắc thành công?

**Đáp án:** Không. Hai phép kiểm tra không xác nhận schema của bytes mới; JVM có thể ném `UnsupportedOperationException` vì thay đổi cấu trúc bị cấm.

**Câu 6.** `ClassDefinition(clazz, bytes)` có an toàn nếu thread khác sửa mảng `bytes` sau đó không?

**Đáp án:** Không. Constructor không copy buffer; hãy hoàn thiện và xác minh bytes rồi không mutate nó trong khi sử dụng.

**Câu 7.** Có thể nhận ra đúng class chỉ bằng `clazz.getName()` không?

**Đáp án:** Chưa đủ trong môi trường nhiều loader: cùng tên có thể là class runtime khác nhau. Cần quan tâm defining loader và chính đối tượng `Class<?>`.

**Câu 8.** Nếu gọi redefine cho nhiều class và một class lỗi định dạng, có nên coi các class còn lại đã đổi không?

**Đáp án:** Không. Theo hợp đồng, nếu `redefineClasses` ném exception thì **không class nào trong tập đó được redefined**.

**Câu 9.** `isModifiableModule(module)==true` có đủ chứng minh `isModifiableClass(clazz)==true`?

**Đáp án:** Không. Sửa module và sửa class có API/hợp đồng khác nhau.

## 12. Tóm tắt và tài liệu chuẩn

**Quy tắc trước khi redefine:**

```text
Manifest agent yêu cầu Can-Redefine-Classes: true
          +
JVM cung cấp capability
          |
          v
isRedefineClassesSupported() == true
          +
Xác định đúng Class<?> và isModifiableClass(clazz) == true
          +
Class-file bytes mới hợp lệ và không vi phạm schema
          |
          v
redefineClasses(new ClassDefinition(clazz, bytes))
          |
          v
Xử lý exception, kiểm tra method invocation/state
```

Ghi nhớ:

1. `isRedefineClassesSupported` là kiểm tra **capability của agent/JVM**, còn `isModifiableClass` là kiểm tra **từng class cụ thể**; cần cả hai.
2. Primitive/array class luôn unmodifiable. Một class thường có thể `modifiable=true` dù agent chưa có capability redefine.
3. Hai boolean cùng true **không** bảo đảm một `ClassDefinition` hợp lệ; phải đối chiếu tên, schema, classfile version và bytecode.
4. Redefinition có thể đổi method body ở lời gọi mới trên **instance cũ**, nhưng không tự chạy lại static/instance initialization và không xóa field values.
5. Trong production, xác minh JAR manifest đúng artifact, bytes patch đáng tin cậy, và hành vi runtime sau khi đổi.

**Nguồn chuẩn:**

- [Java SE 17 — `Instrumentation`: isRedefineClassesSupported, isModifiableClass, redefineClasses](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html)
- [Java SE 17 — `java.lang.instrument`: Premain-Class, Agent-Class, Can-Redefine-Classes](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html)
- [Java SE 17 — `ClassDefinition`: binding class + bytes, không copy mảng](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassDefinition.html)
- [Java SE 17 — `ClassFileTransformer`: callback với redefinition](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html)
- [JVMTI — `RedefineClasses`: phạm vi thay schema, stack frames và trạng thái runtime](https://docs.oracle.com/en/java/javase/17/docs/specs/jvmti.html#RedefineClasses)
- [Java SE 17 — `java` launcher: `-javaagent`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html)
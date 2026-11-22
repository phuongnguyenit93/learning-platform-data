# Đối số `Module` trong `ClassFileTransformer`: xác định đúng module của lớp đang được biến đổi

## 1. Vấn đề và mục tiêu

Từ Java 9, Java Platform Module System (JPMS) bổ sung khái niệm **module** vào runtime. Với Java agent, một class không chỉ được nhận diện bằng tên và class loader: nó còn **thuộc một module cụ thể**. Hai lớp có cùng package, thậm chí cùng tên binary trong những không gian loader/layer khác nhau, có thể chịu những chính sách module và khả năng truy cập khác nhau.

`ClassFileTransformer` cung cấp overload có tham số `Module` để agent biết module của **lớp hiện đang được xử lý**, ngay cả ở thời điểm JVM **chưa hoàn tất định nghĩa lớp**:

```java
byte[] transform(
        Module module,
        ClassLoader loader,
        String className,
        Class<?> classBeingRedefined,
        java.security.ProtectionDomain protectionDomain,
        byte[] classfileBuffer);
```

Trong đó:

- **`module`:** đối tượng `java.lang.Module` đại diện cho module **chứa class đang biến đổi**.
- **`loader`:** defining class loader của class; có thể `null` nếu bootstrap loader định nghĩa class.
- **`className`:** tên class/interface dạng JVM internal name, ví dụ `com/example/Service`.
- **`classBeingRedefined`:** `null` khi định nghĩa class mới; có đối tượng `Class<?>` trong đường redefine/retransform.
- **`protectionDomain`:** protection domain liên quan đến việc định nghĩa class.
- **`classfileBuffer`:** full class-file bytes của lượt biến đổi; **không được sửa mảng đầu vào trực tiếp**.

Điểm cần nhớ: **module và class loader là hai thông tin khác nhau**. Một loader có thể định nghĩa class thuộc named modules và unnamed module của chính nó. `module` giúp phân loại chính xác hơn là suy từ prefix package hoặc TCCL (thread context class loader).

Bài này thuộc phần **Instrumentation và module**. Ta sẽ đọc hợp đồng callback, phân biệt named/unnamed modules, chạy Java agent trên Java 17 với cả classpath và module path, rồi xem cách dùng `module` trong thiết kế transformer production.

## 2. API nào cung cấp tham số `Module`?

### 2.1. Hai overload `transform`

`ClassFileTransformer` có hai dạng callback:

**Dạng lịch sử, không nhận Module:**

```java
default byte[] transform(
        ClassLoader loader,
        String className,
        Class<?> classBeingRedefined,
        ProtectionDomain protectionDomain,
        byte[] classfileBuffer);
```

**Dạng từ Java 9, có Module:**

```java
default byte[] transform(
        Module module,
        ClassLoader loader,
        String className,
        Class<?> classBeingRedefined,
        ProtectionDomain protectionDomain,
        byte[] classfileBuffer);
```

Các chữ ký trên **minh họa**, cần import `java.security.ProtectionDomain`. Trong Java 17, **cả hai phương thức đều là default methods** của interface; không dùng `ClassFileTransformer` như functional interface/lambda.

Quy tắc tương thích ngược rất quan trọng:

- Nếu một implementation **chỉ override dạng 5 tham số**, implementation mặc định của dạng 6 tham số sẽ **gọi về dạng 5 tham số**. Agent cũ tiếp tục hoạt động, nhưng không nhận trực tiếp metadata module trong callback của mình.
- Nếu implementation **override dạng 6 tham số**, bạn có `Module` ngay trong callback. Không cần override cả hai chỉ để lấy thông tin module.
- Nếu không override phương thức nào, default của dạng 5 trả `null`; dạng 6 chuyển tiếp tới đó, nên không có biến đổi bytecode.
- Nếu override cả hai, hãy xác định rõ logic áp dụng ở mỗi dạng; tránh tự gọi lẫn nhau vô hạn.

Agent Java 17 cần lấy module trực tiếp **nên override 6 tham số**, ví dụ:

```java
new ClassFileTransformer() {
    @Override
    public byte[] transform(
            Module module,
            ClassLoader loader,
            String className,
            Class<?> classBeingRedefined,
            ProtectionDomain protectionDomain,
            byte[] classfileBuffer) {

        // module là module của class đang được biến đổi.
        return null; // Không sửa bytecode.
    }
}
```

Đây là đoạn **minh họa** đặt trong `Instrumentation.addTransformer(...)`, chưa phải một chương trình độc lập.

### 2.2. Callback diễn ra ở những giai đoạn nào?

Khi đăng ký qua:

```java
inst.addTransformer(transformer, false);
```

transformer được gọi trong các **lần định nghĩa class mới** và **class redefinition** phù hợp hợp đồng. Với `canRetransform=true`, nó còn được gọi ở **retransformation** nếu VM/agent hỗ trợ capability.

Phân biệt:

| Trường hợp | `module` | `classBeingRedefined` | Ghi chú |
| --- | --- | --- | --- |
| JVM đang định nghĩa một class mới | Module đích | `null` | Không cần có `Class<?>` của class đích tại callback |
| `redefineClasses` | Module của class đã nạp | `Class<?>` đích | Bytes từ `ClassDefinition` tiếp tục qua transformer chain |
| `retransformClasses` và transformer `canRetransform=true` | Module của class đã nạp | `Class<?>` đích | Callback được gọi lại |
| `retransformClasses` và transformer `canRetransform=false` | Không có callback mới cho transformer này | Không áp dụng | JVM tái sử dụng kết quả transform cũ theo đặc tả |

**Không hiểu sai:** `classBeingRedefined == null` cho thấy đường **initial class definition**; nó không có nghĩa class không thuộc module nào.

Trong mọi đường gọi, module giúp nhận biết đối tượng chứa class. Đừng dùng `className` để đoán tên module, đặc biệt khi hệ thống có nhiều module layers hoặc custom loaders.

## 3. `Module` là đối tượng gì?

`java.lang.Module` mô tả một **runtime module**, có thể là **named module** hoặc **unnamed module**. Các method hữu ích:

```java
module.isNamed();
module.getName();
module.getClassLoader();
module.getLayer();
module.getDescriptor();
module.getPackages();
```

Các ý nghĩa:

- `isNamed()`: `true` nếu là named module, `false` nếu unnamed.
- `getName()`: tên module nếu named, **`null` nếu unnamed**.
- `getClassLoader()`: loader của module, có thể là bootstrap (`null`) tùy module.
- `getLayer()`: layer chứa module hoặc `null` nếu module không nằm trong một layer.
- `getDescriptor()`: `ModuleDescriptor` của named module hoặc `null` với unnamed.
- `getPackages()`: các tên package thuộc module, **không phải** danh sách mọi class/method.

**Quan trọng:** `module.getName() == null` có nghĩa **unnamed module** theo `Module` API; điều đó **khác** với `loader == null` (bootstrap class loader). Đừng quy đổi hai điều kiện.

### 3.1. Named module

Named module có **tên**, ví dụ:

```java
module demo.named {
}
```

Nếu class `demo.named.NamedTarget` được định nghĩa trong module này, callback có thể thấy:

```text
module.isNamed() -> true
module.getName() -> "demo.named"
```

Module có thể là **explicit** (có `module-info.class`) hoặc **automatic** (JAR trên module path được coi là automatic module theo các quy tắc JPMS). Trong cả hai trường hợp, `isNamed()` trả `true`.

Ví dụ `String.class.getModule().getName()` trên Java 17 trả `java.base`. Đây là **named module**; lớp `java.lang.String` điển hình do bootstrap loader định nghĩa. Như vậy **named module hoàn toàn có thể đi cùng `loader == null`**.

### 3.2. Unnamed module

Class chạy trên **classpath** thông thường là thành viên của **unnamed module** tương ứng defining class loader. Dù module không có tên, nó **vẫn là một đối tượng `Module`**.

```java
Module m = MyApp.class.getModule();
System.out.println(m.isNamed()); // false cho classpath app thông thường.
System.out.println(m.getName());  // null
```

Đây là đoạn minh họa trong ứng dụng `MyApp` chạy trên classpath. Không được hiểu **`module == null` tương đương unnamed**. Đặc tả `ClassFileTransformer` mô tả tham số `module` là module của class; với class thông thường trong unnamed module, sẽ có **unnamed Module**.

JDK có một unnamed module **cho mỗi class loader**, lấy bằng `loader.getUnnamedModule()` khi `loader` là object Java không null. Vì vậy hai custom loaders có thể có **hai unnamed modules khác nhau** dù cả hai đều có `getName() == null`.

Nếu code cần chạy phòng thủ với tình huống `module == null` không mong đợi, hãy gắn nhãn **unknown/unavailable**, không tự xem đó là unnamed.

### 3.3. Bảng phân biệt module và loader

| Class / hoàn cảnh | `module.isNamed()` | `module.getName()` | `loader` trong callback |
| --- | --- | --- | --- |
| `java.lang.String` trong JDK 17 thông thường | `true` | `java.base` | `null`, bootstrap |
| Class ứng dụng thông thường trên classpath | `false` | `null` | Object application loader |
| Class trong explicit named module trên module path | `true` | Tên khai báo trong `module-info.java` | Loader mà module được gán, thường application/platform |
| Class trong automatic module | `true` | Tên automatic module | Loader mà module được gán |
| Class thuộc unnamed module của custom loader | `false` | `null` | Object custom loader |

Đây là mô tả **mẫu điển hình**, không phải định luật “một module = một loader”. Loader có thể chứa nhiều named modules và unnamed module của nó; classloader topology phụ thuộc Java runtime và module layers.

## 4. Tại sao tên lớp/package/loader riêng lẻ không đủ?

Giả sử transformer nhận:

```text
className = "com/example/Service"
loader = appLoader
```

Thông tin trên **không tự khẳng định** class thuộc module nào:

- Trong một ứng dụng classpath, class có thể thuộc **unnamed module** của `appLoader`.
- Trong một ứng dụng module path, class cùng package có thể thuộc **named module**.
- Nếu có nhiều `ModuleLayer`, những module cùng tên ở các layer khác nhau là **các đối tượng Module khác nhau**.
- Nhiều classloader có thể định nghĩa cùng binary name nhưng class identity khác nhau.

Ngay cả quan hệ `parent/child` của loader cũng không nói module class được định nghĩa thuộc về.

**Kết luận:** hãy dùng **`module` của callback** khi chọn policy cho class đang transform. Khi cần nhận diện một module **cụ thể** trong hệ thống có nhiều layers, có thể phải dựa trên **identity của đối tượng `Module`** cùng loader/layer, không chỉ `module.getName()`.

### Đừng dùng `Thread.currentThread().getContextClassLoader()` thay thế

TCCL là ngữ cảnh do framework/thread có thể đặt để tra cứu tài nguyên hoặc services. TCCL có thể khác loader **định nghĩa class đang transform**. Vì vậy đoạn này là sai về ý tưởng:

```java
ClassLoader guess =
        Thread.currentThread().getContextClassLoader();
// Không suy module của class đang transform từ guess.
```

Dùng module callback và defining loader callback làm nguồn chân lý; TCCL có thể phục vụ nghiệp vụ khác nhưng không chứng minh ownership của class.

## 5. Tại sao `module` hữu ích ngay tại thời điểm class loading?

Transformer được JVM gọi **trước khi class được định nghĩa hoàn chỉnh**. Trong lần load mới, `classBeingRedefined == null`, nên không có đối tượng `Class<?>` tương ứng để gọi `getModule()`.

Một sai lầm nguy hiểm là tự nạp class ngay trong `transform` để tìm module:

```java
// Không làm như thế trong transformer load-time:
Class<?> c = Class.forName(
        className.replace('/', '.'),
        false,
        loader);
Module m = c.getModule();
```

Ví dụ này chỉ để **minh họa lỗi thiết kế**; `className` có thể không có hoặc có dạng đặc biệt, và `loader` có thể `null`. Lời gọi còn có khả năng:

- Kích hoạt class loading đệ quy cho chính class JVM đang định nghĩa;
- Gây `ClassCircularityError`, deadlock hoặc thay đổi thứ tự tải;
- Kích hoạt custom loader và side effects không mong muốn;
- Tìm lớp khác loader/module mà không khớp bytes callback hiện tại.

Thay vì làm vậy:

```java
// Đúng: nhận Module đã do JVM cung cấp.
boolean named = module != null && module.isNamed();
String name = module == null ? "<unknown>"
        : (named ? module.getName() : "<unnamed>");
```

Đây là kiểm tra **không cần load class mới**. Dữ liệu module chính xác theo callback và không phải suy diễn từ đường dẫn JAR hoặc package prefix.

Trong đường redefine/retransform, `classBeingRedefined` là object `Class<?>` có sẵn, nên `classBeingRedefined.getModule()` là phép đối chiếu hữu ích. Nhưng **không dùng kỹ thuật đó cho đường initial load**, vì tham số này `null`.

## 6. Thực hành Java 17: một agent quan sát named và unnamed modules

Mục tiêu của demo:

1. Tạo **một Java agent** override overload `transform(Module,...)` 6 tham số.
2. Chạy một ứng dụng **classpath**: target thuộc unnamed module.
3. Chạy một ứng dụng **explicit named module**: target thuộc module `demo.named`.
4. So sánh module trong callback với `Target.class.getModule()` ở ứng dụng **sau khi lớp được nạp**.
5. Không sửa bytecode: transformer luôn trả `null`.

Hai ứng dụng được chạy trong **hai lần khởi động JVM riêng biệt**, nhưng sử dụng **cùng agent JAR**. Điều này giúp kết quả dễ kiểm chứng và không bị ảnh hưởng bởi module graph tùy biến.

### 6.1. Cấu trúc thư mục

```text
module-context-demo/
├── agent.mf
└── src/
    ├── agent/
    │   └── ModuleProbeAgent.java
    ├── plain/
    │   └── demo/
    │       └── plain/
    │           ├── PlainTarget.java
    │           └── PlainMain.java
    └── named/
        ├── module-info.java
        └── demo/
            └── named/
                ├── NamedTarget.java
                └── ModuleMain.java
```

Các file trong ví dụ đều dùng API Java 17. Tệp `module-info.java` **chỉ thuộc ứng dụng named**; classpath app không có module descriptor.

### 6.2. File `src/agent/ModuleProbeAgent.java`

```java
import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;

public final class ModuleProbeAgent {
    private ModuleProbeAgent() {
    }

    public static void premain(String agentArgs, Instrumentation inst) {
        inst.addTransformer(new ClassFileTransformer() {
            @Override
            public byte[] transform(
                    Module module,
                    ClassLoader loader,
                    String className,
                    Class<?> classBeingRedefined,
                    ProtectionDomain protectionDomain,
                    byte[] classfileBuffer) {

                // Chỉ log hai class mục tiêu; tránh log toàn bộ JVM.
                boolean selected =
                        "demo/plain/PlainTarget".equals(className)
                        || "demo/named/NamedTarget".equals(className);

                if (!selected) {
                    return null;
                }

                boolean named =
                        module != null && module.isNamed();
                String moduleName =
                        module == null ? "<unknown>"
                        : named ? module.getName() : "<unnamed>";

                System.out.println("[transform] "
                        + className
                        + " module=" + moduleName
                        + " named=" + named
                        + " bootstrapLoader=" + (loader == null));

                return null; // Giữ nguyên classfileBuffer.
            }
        }, false);
    }
}
```

Những điểm quan trọng:

- `@Override` **đúng overload 6 tham số**. Nếu bỏ tham số `Module`, thông tin module sẽ không còn là tham số callback trực tiếp.
- Bộ lọc dùng `"literal".equals(className)`, nên an toàn nếu tên class không khả dụng trong tình huống đặc biệt.
- `module == null` được ghi thành `<unknown>`, không gán nhầm thành unnamed. Trong hai trường hợp demo, module được JVM cung cấp.
- `bootstrapLoader` chỉ minh họa **defining loader**, không được dùng thay module name.
- `classBeingRedefined` không được dùng vì demo chỉ quan sát định nghĩa class mới.
- `false` trong `addTransformer(..., false)` nghĩa không cần khả năng retransformation; vẫn nhận load-time callbacks.
- `return null` nghĩa **không thay đổi bytecode**, không phải lỗi.
- Demo in một dòng ngắn trong callback. Agent production thường cần recorder tối giản thay cho I/O dài hoặc log hàng nghìn class.

### 6.3. File `agent.mf`

```text
Manifest-Version: 1.0
Premain-Class: ModuleProbeAgent

```

Đây là manifest của **agent JAR**, cần có dòng trống kết thúc main section. Không yêu cầu `Can-Retransform-Classes` hay `Can-Redefine-Classes` vì chỉ quan sát class loading.

### 6.4. File `src/plain/demo/plain/PlainTarget.java`

```java
package demo.plain;

public final class PlainTarget {
    private PlainTarget() {
    }

    public static String text() {
        return "plain";
    }
}
```

Class này được đóng vào `plain.jar` và đặt **trên classpath**, nên thuộc unnamed module của application class loader.

### 6.5. File `src/plain/demo/plain/PlainMain.java`

```java
package demo.plain;

public final class PlainMain {
    private PlainMain() {
    }

    public static void main(String[] args) {
        // Gọi target sau premain để callback xảy ra rõ ràng.
        String value = PlainTarget.text();
        Module module = PlainTarget.class.getModule();

        String name = module.isNamed()
                ? module.getName()
                : "<unnamed>";

        System.out.println("[main] module=" + name);
        System.out.println("[main] value=" + value);
    }
}
```

Chương trình chỉ gọi `PlainTarget.class.getModule()` **sau khi** target đã được load. Đây là phép đối chiếu runtime độc lập với callback; không cần làm vậy ở bên trong transformer.

### 6.6. File `src/named/module-info.java`

```java
module demo.named {
}
```

Module có tên `demo.named`. Ví dụ không cần `requires` hoặc `exports` vì chỉ sử dụng API từ `java.base` và application launcher gọi entry point của chính module.

### 6.7. File `src/named/demo/named/NamedTarget.java`

```java
package demo.named;

public final class NamedTarget {
    private NamedTarget() {
    }

    public static String text() {
        return "named";
    }
}
```

Class này nằm trong module explicit `demo.named` thay vì unnamed module.

### 6.8. File `src/named/demo/named/ModuleMain.java`

```java
package demo.named;

public final class ModuleMain {
    private ModuleMain() {
    }

    public static void main(String[] args) {
        String value = NamedTarget.text();
        Module module = NamedTarget.class.getModule();

        String name = module.isNamed()
                ? module.getName()
                : "<unnamed>";

        System.out.println("[main] module=" + name);
        System.out.println("[main] value=" + value);
    }
}
```

`NamedTarget.class.getModule()` phản ánh module sau khi class đã được định nghĩa. Kết quả phải khớp tên module từ callback của `ModuleProbeAgent` trong cùng JVM.

### 6.9. Biên dịch và đóng gói (POSIX shell)

Mở terminal trong thư mục `module-context-demo/`. Cần JDK 17+:

```bash
mkdir -p out/agent out/plain out/named

javac --release 17 -d out/agent \
  src/agent/ModuleProbeAgent.java

javac --release 17 -d out/plain \
  src/plain/demo/plain/PlainTarget.java \
  src/plain/demo/plain/PlainMain.java

javac --release 17 -d out/named \
  src/named/module-info.java \
  src/named/demo/named/NamedTarget.java \
  src/named/demo/named/ModuleMain.java

jar --create --file module-agent.jar --manifest agent.mf \
  -C out/agent .

jar --create --file plain.jar \
  -C out/plain .

jar --create --file named.jar \
  -C out/named .
```

Giải thích:

- `module-agent.jar` chứa `ModuleProbeAgent.class` **và `ModuleProbeAgent$1.class`** từ anonymous transformer; dùng `-C out/agent .` để không bỏ sót class.
- `plain.jar` chỉ chứa `demo/plain/...`, không có `module-info.class`.
- `named.jar` chứa `module-info.class` cùng `demo/named/...`.
- Cả hai chương trình dùng đúng **cùng agent** để chứng minh thông tin `Module` thay đổi theo module thực của class.

### 6.10. Chạy trường hợp classpath / unnamed module

```bash
java -javaagent:module-agent.jar \
  -cp plain.jar demo.plain.PlainMain
```

**Stdout dự kiến** trên runtime JDK 17+ thông thường:

```text
[transform] demo/plain/PlainTarget module=<unnamed> named=false bootstrapLoader=false
[main] module=<unnamed>
[main] value=plain
```

`module.isNamed() == false`, dù `loader != null`. Điều này chứng minh **unnamed module không phải “không có module”**; nó có object `Module` nhưng không có tên.

### 6.11. Chạy trường hợp module path / named module

```bash
java -javaagent:module-agent.jar \
  --module-path named.jar \
  --module demo.named/demo.named.ModuleMain
```

**Stdout dự kiến:**

```text
[transform] demo/named/NamedTarget module=demo.named named=true bootstrapLoader=false
[main] module=demo.named
[main] value=named
```

`module.isNamed() == true` và `module.getName()` bằng `demo.named`. Dù loader không phải bootstrap trong demo, việc module có tên **không suy ra** một loader riêng đặc biệt.

Với JVM nhiều agent, tùy chọn class loading logging, hoặc cấu hình riêng, có thể có log khác trên stderr/stdout. Các dòng trên là **những dòng do mã ví dụ chủ động phát ra**, không phải cam kết không có bất kỳ thông báo từ runtime khác.

### 6.12. Windows PowerShell

Tạo thư mục và biên dịch:

```powershell
New-Item -ItemType Directory -Force out/agent, out/plain, out/named | Out-Null

javac --release 17 -d out/agent src/agent/ModuleProbeAgent.java
javac --release 17 -d out/plain src/plain/demo/plain/PlainTarget.java src/plain/demo/plain/PlainMain.java
javac --release 17 -d out/named src/named/module-info.java src/named/demo/named/NamedTarget.java src/named/demo/named/ModuleMain.java

jar --create --file module-agent.jar --manifest agent.mf -C out/agent .
jar --create --file plain.jar -C out/plain .
jar --create --file named.jar -C out/named .
```

Hai lệnh chạy giống POSIX nhưng nằm trên một dòng:

```powershell
java -javaagent:module-agent.jar -cp plain.jar demo.plain.PlainMain
java -javaagent:module-agent.jar --module-path named.jar --module demo.named/demo.named.ModuleMain
```

Không dùng `-cp` cho `named.jar` nếu muốn thử named module thật. Đưa JAR có `module-info.class` lên classpath sẽ khiến các class được nạp theo quy tắc **unnamed module** của class loader, không phải explicit named module `demo.named`.

### 6.13. Kiểm tra artifact để tránh sai ngữ cảnh

```bash
jar --list --file module-agent.jar
jar --list --file plain.jar
jar --list --file named.jar

jar --describe-module --file named.jar
```

Trong `named.jar` phải có `module-info.class` và descriptor khai báo `demo.named`. Nếu thiếu, test có thể trở thành automatic module hoặc một artifact không như mong đợi. Nếu `ModuleProbeAgent$1.class` thiếu trong agent JAR, JVM có thể không load được anonymous transformer.

## 7. Chọn policy dựa trên `Module`

Với agent sản xuất, ta thường chỉ instrument một hoặc một nhóm modules nhất định.

Ví dụ **bộ lọc minh họa**:

```java
private static boolean shouldTransform(
        Module module, String internalName) {

    return module != null
            && module.isNamed()
            && "com.acme.orders".equals(module.getName())
            && "com/acme/orders/OrderService".equals(internalName);
}
```

Đoạn code này là helper trong agent, **không phải file Java chạy độc lập**. Nó tránh chèn hook vào modules không phải mục tiêu. So sánh tên module và class name tách biệt — **không** lấy package prefix làm module name.

### Nếu cần phân biệt nhiều layers

Một hệ thống plugin có thể tạo nhiều `ModuleLayer` và cho phép các module **cùng tên** ở những layer khác nhau. Nếu policy thực sự nhắm một **module runtime instance**, chỉ so tên là chưa đủ:

```java
private static boolean isExactTarget(
        Module current, Module approved) {
    return current != null && current == approved;
}
```

Ở đây `approved` là object `Module` đã được hạ tầng của ứng dụng/agent xác định đáng tin cậy. Không làm `Class.forName` từ trong callback để tìm module chỉ vì muốn có object so sánh. Có thể kết hợp `module.getLayer()`, `module.getClassLoader()` và defining loader theo chính sách, nhưng **identity của Module** là yếu tố trực tiếp hơn nếu bạn quản lý được object chính xác.

### Với unnamed module

Nếu bạn instrument ứng dụng classpath:

```java
if (module != null && !module.isNamed()
        && "demo/plain/PlainTarget".equals(className)) {
    // Lớp thuộc unnamed module.
}
```

Nhưng ở JVM chứa nhiều custom loaders, tất cả chúng có thể có unnamed module riêng. Khi đó hãy giới hạn thêm theo defining loader, nguồn artifact hoặc đối tượng unnamed module mong đợi.

**Không dùng `module == null` để tìm unnamed module.** Nếu module không có sẵn trong một tình huống đặc biệt, hãy xử lý như “không đủ metadata”, bỏ qua hoặc log theo policy, không suy đoán.

## 8. Module identity có thay thế class identity không?

**Không.** Một class cụ thể vẫn được xác định bởi **binary name và defining loader**, trong khi module mô tả membership và access boundaries của runtime.

Các khái niệm:

| Dữ kiện | Trả lời câu hỏi nào? | Điều không thể suy ra |
| --- | --- | --- |
| `className` | JVM internal name nào đang biến đổi? | Không cho biết module, layer, loader duy nhất |
| `loader` | Loader nào định nghĩa class? | Không cho biết named/unnamed module nếu chỉ có loader |
| `module` | Class thuộc runtime module nào? | Không cho biết bytes đã được verify hay quyền sửa class |
| `module.getName()` | Tên của named module | Không phân biệt module cùng tên ở các layers khác nhau |
| `module.getLayer()` | Layer chứa module, nếu có | Không chỉ ra source file/JAR chính xác của từng class |
| `protectionDomain` | Thông tin domain/bảo vệ khi define | Không thay module membership |
| `classBeingRedefined` | Đối tượng class cũ trong redefine/retransform | `null` trong initial load bình thường |
| `classfileBuffer` | Bytes đang được transformer xử lý | Không tự biết class có thể resolve/link được sau rewrite |

**Tên module không phải tên package.** Module `com.acme.orders` có thể chứa `com.acme.orders.internal` hoặc nhiều package khác. Tên module không được suy ra từ `className.substring(...)`.

**Một loader không tương đương một module.** System/application loader có thể định nghĩa các class của named modules trong boot layer và các class của unnamed module trên classpath. Vì vậy kiểm tra đơn giản `loader == ClassLoader.getSystemClassLoader()` không có nghĩa class đang ở unnamed module.

## 9. Module metadata không tự cấp quyền truy cập

Biết `module` không giống việc agent được tùy ý reflection hay gọi method private của mọi lớp trong module đó.

JPMS có nhiều quan hệ:

- **Readability:** một module có đọc một module khác không (`module.canRead(otherModule)`).
- **Exports:** package có được export cho module khác để truy cập public types theo quy tắc module không (`module.isExported(packageName, otherModule)`).
- **Opens:** package có mở cho deep reflection phù hợp không (`module.isOpen(packageName, otherModule)`).
- **Class loader visibility:** code/helper có thể tìm hoặc link đúng class qua loader/module tương ứng không.

Transformer nhận module chỉ để **biết class thuộc module nào**; callback không tự mở package, không thêm reads hoặc thay đổi module descriptor.

### 9.1. Hỗ trợ đọc module của agent và giới hạn của nó

Tài liệu `java.lang.instrument` cho biết JVM bố trí để module của class được transform có quan hệ **read** tới unnamed module của bootstrap loader và của loader nạp agent chính. Điều này hỗ trợ những helper do agent đưa vào class-search paths thích hợp.

Tuy nhiên **readability không thay thế exports/opens hoặc class visibility**. Nếu code được chèn cố gọi helper trong package/module không thể truy cập, hoặc reflection truy cập thành viên không được mở, JVM vẫn có thể ném `IllegalAccessError` hoặc `InaccessibleObjectException`.

Ví dụ, muốn gọi helper từ named module đã instrument còn phải bảo đảm helper được đặt ở class loader phù hợp, có package/public access phù hợp và không vướng module access. Đừng thấy `module.isNamed()` rồi tự động chèn mọi lời gọi đến một class trong application classpath.

### 9.2. `Instrumentation.redefineModule` để sửa module graph khi thực sự cần

API Java 9+ có:

```java
inst.isModifiableModule(targetModule);
inst.redefineModule(
        targetModule,
        extraReads,
        extraExports,
        extraOpens,
        extraUses,
        extraProvides);
```

Đoạn này **minh họa chữ ký**, biến `inst`, `targetModule` và các tập/map chưa được định nghĩa. `redefineModule` chỉ **bổ sung** quan hệ đọc, exports, opens hoặc service use/provider theo điều kiện và capability; **không rút bớt** các quan hệ hiện có, **không** đổi một class từ module này sang module khác và **không** cần dùng chỉ để log module name.

Với unnamed module, `redefineModule` là no-op; `isModifiableModule` luôn trả `true` cho unnamed module theo Javadoc. Không nên gọi API vì thói quen: chỉ chỉnh module graph nếu thật sự có quyền truy cập hợp lệ cần thêm.

### 9.3. Chỉ so module name có thể tạo lỗi bảo mật

Nếu agent dựa vào `module.getName().startsWith("com.mycompany")` để quyết định chèn một hook an ninh, một module trong plugin layer hoặc nguồn không tin cậy có thể có tên tương tự. Trong bài toán nhạy cảm, phải kiểm tra **module identity**, loader, nguồn triển khai hoặc chính sách chữ ký/artifact nếu liên quan, không chỉ tên do hệ thống bên ngoài có thể tác động.

## 10. Phân biệt callback với `Class.getModule()` và reflective APIs

Một số API dễ gây nhầm:

### `Class.getModule()`

```java
Module module = SomeClass.class.getModule();
```

Dùng **sau khi có `Class<?>`**. Với class đã được load, nó trả module của class. Trong demo, `PlainTarget.class.getModule()` và `NamedTarget.class.getModule()` khớp thông tin in từ callback.

Trong **initial transform**, không có `Class<?>` đích trong `classBeingRedefined`, vì vậy `module` callback là đường đúng và không cần load lại class.

### `ClassLoader.getUnnamedModule()`

```java
Module unnamed =
        ClassLoader.getSystemClassLoader().getUnnamedModule();
```

Đây là unnamed module của **system loader**, không phải module của **mọi class trong JVM**. Nếu class nằm trong explicit named module được system loader định nghĩa, `getUnnamedModule()` vẫn trả một đối tượng **khác module của class đó**.

### `ModuleLayer.boot()` và `ModuleLayer.findModule(...)`

Đây là cơ chế quản lý/tìm modules trong layer. Chúng không đồng nghĩa “module của class đang transform”, đặc biệt khi có custom layers. Có thể hữu ích để resolve module object được hạ tầng tin cậy quản lý, nhưng không cần gọi trong callback cho phân loại thông thường.

### `Module.getName() == null` và `loader == null`

Hai điều kiện này trả lời **hai câu hỏi độc lập**:

- `module.getName() == null`: class ở **unnamed module**.
- `loader == null`: class được **bootstrap loader** định nghĩa.

Một class ở `java.base` có module name không null và loader null; class classpath có module name null và loader thường không null.

## 11. Sai lầm phổ biến và cách chẩn đoán

| Biểu hiện / phát biểu | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| “`module == null` nghĩa classpath class” | Đồng nhất null với unnamed | Dùng `module.isNamed()`; `getName() == null` với unnamed |
| `NullPointerException` ở `module.getName()` hoặc `module.isNamed()` | Không có null-check trong trường hợp module không khả dụng | Nếu cần phòng thủ, nhận diện `module == null` thành unknown, không thành unnamed |
| Agent chỉ nhận overload 5 tham số | Override nhầm method legacy | Override overload 6 tham số để nhận Module trực tiếp |
| Đổi sang lambda báo compiler error | `ClassFileTransformer` không phải functional interface trên Java 17 | Dùng class/anonymous class và `@Override` |
| Filter bằng `className.startsWith("java/")` để xác định module `java.base` | Package prefix không phải module identity | Dùng `module.getName()` và identity theo yêu cầu |
| TCCL là system nhưng class thuộc named module | TCCL không phải defining loader/module | Dùng tham số callback, không suy từ TCCL |
| Classpath JAR có `module-info.class` nhưng log vẫn unnamed | Đưa JAR lên **classpath** nên class được định nghĩa trong unnamed module | Chạy module bằng `--module-path` và `--module` |
| Automatic module bị phân loại unnamed | Tưởng chỉ explicit module mới là named | Kiểm tra `module.isNamed()`; automatic module cũng named |
| Hai plugin đều có tên module giống nhau và bị trộn policy | Chỉ dùng `module.getName()` làm key | Phân biệt `Module` object/layer/loader/artifact |
| `IllegalAccessError` sau khi instrument named module | Hook gọi helper không thấy hoặc không được truy cập | Kiểm tra loader visibility, module reads/exports và code linkage |
| `InaccessibleObjectException` khi reflection | Package không mở cho deep reflection | Kiểm tra `isOpen`; điều chỉnh access có kiểm soát nếu thật sự cần |
| Log không xuất hiện cho một class JDK | Class có thể đã load trước khi `premain` đăng ký transformer | Không suy ra module sai; kiểm tra thời điểm load/retransform capability |
| Transformer trả `new byte[0]` để no-op | Không hiểu hợp đồng callback | Trả `null` khi không sửa class |
| `VerifyError` sau biến đổi | Bytecode/frames/schema không hợp lệ | Verify bytes và xét module/class loader dependency |
| `classBeingRedefined == null` nhưng `module` có tên | Initial load của một named-module class | Đây là trạng thái hợp lệ |

Khi debug, log tối thiểu **internal class name + module name + isNamed + loader identity/kind**. Nhưng không log toàn bộ class loading ở production nếu không có bộ lọc vì quá nhiều overhead và nguy cơ reentrancy.

## 12. Kiểm thử thực tế và vận hành

### 12.1. Các ca cần kiểm tra

- **Unnamed classpath:** `module.isNamed() == false`, `module.getName() == null`.
- **Named module:** `module.isNamed() == true`, `getName()` trả tên thật.
- **Automatic module:** JAR trên module path, không có explicit descriptor, nhưng vẫn named.
- **Bootstrap class:** `loader == null` và module vẫn có thể named (ví dụ `java.base`).
- **Plugin loader:** phân biệt các unnamed modules của hai loader; tránh gộp cache theo `getName()`.
- **Two layers:** nếu có hai named modules cùng tên ở các layers khác nhau, test module identity khi policy nhắm chính xác một layer.
- **Redefine/retransform:** module của class được giữ, callback nhận đúng phase; với transformer `canRetransform=false`, retransform có thể không gọi callback.
- **Code injected helpers:** kiểm tra class loader visibility, reads, exports, opens, verifier và hiệu năng sau khi thêm instrumentation.

### 12.2. Checklist cho transformer module-aware

1. Override **`transform(Module, ClassLoader, String, Class<?>, ProtectionDomain, byte[])`** khi cần module metadata trực tiếp.
2. Không xem unnamed module là `null`; dùng `isNamed()` và `getName()` đúng ngữ nghĩa.
3. Dùng **`module` callback** khi initial load, không tự `Class.forName` để tạo `Class<?>`.
4. Tách module name khỏi package name và defining loader; không suy từ TCCL.
5. Nếu cần chọn một module chính xác, cân nhắc `Module` identity và `ModuleLayer`, không chỉ tên.
6. Đừng coi module metadata là quyền truy cập; kiểm tra reads/exports/opens và helper linkage.
7. Dùng `redefineModule` chỉ khi cần và chỉ bổ sung quan hệ được phép; không dùng để chuyển class sang module khác.
8. Giữ transformer ngắn, null-safe, lọc class cụ thể, tránh I/O phức tạp và classloading đệ quy.
9. Trả `null` khi không sửa bytes; nếu sửa, tạo byte array mới hợp lệ, không mutate input.
10. Test classpath và module path trên JVM mục tiêu, cùng thời điểm đăng ký và các agent khác.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** `module == null` có nghĩa lớp ở unnamed module không?

**Đáp án:** Không. Unnamed module vẫn là đối tượng `Module`. Dùng `!module.isNamed()` hoặc `module.getName() == null` sau khi bảo đảm `module` có giá trị.

**Câu 2.** `loader == null` có nghĩa class không ở named module không?

**Đáp án:** Không. Ví dụ class `java.lang.String` ở `java.base` (named) và do bootstrap loader định nghĩa.

**Câu 3.** Có thể lấy đúng module bằng cách tự gọi `Class.forName` từ trong initial transform không?

**Đáp án:** Không nên. Lớp có thể chưa định nghĩa xong; thao tác có nguy cơ class loading đệ quy, deadlock hoặc nạp sai. Callback đã cung cấp module trực tiếp.

**Câu 4.** Vì sao Java 17 agent cũ override 5 tham số vẫn chạy?

**Đáp án:** Default implementation của overload 6 tham số sẽ chuyển tiếp vào overload 5. Muốn nhận `Module` trực tiếp thì override overload 6.

**Câu 5.** Hai modules cùng tên ở hai module layers khác nhau có cùng identity không?

**Đáp án:** Không. Chúng là hai runtime `Module` objects khác nhau. Policy chỉ so tên có thể gộp nhầm.

**Câu 6.** `module.isNamed() == true` có tự cấp quyền reflection vào private members không?

**Đáp án:** Không. Readability, exports, opens và visibility là cơ chế riêng; tham số `Module` không tự điều chỉnh chúng.

**Câu 7.** Chạy `named.jar` trên classpath thay vì module path có còn ở explicit named module không?

**Đáp án:** Không. Classpath classes được định nghĩa trong unnamed module của loader tương ứng dù archive có `module-info.class`. Muốn thử explicit named module phải dùng module launcher.

## 14. Tài liệu chính thức

- [Oracle Java SE 17 — `ClassFileTransformer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): overload 5/6 tham số, `Module` callback, loader, class name, redefine/retransform và `return null`.
- [Oracle Java SE 17 — `Module`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html): named/unnamed modules, `isNamed`, `getName`, `getLayer`, readability, exports và opens.
- [Oracle Java SE 17 — `ClassLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): defining loader, `getUnnamedModule` và delegation.
- [Oracle Java SE 17 — `Class.getModule()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getModule()): module của class đã được định nghĩa.
- [Oracle Java SE 17 — `Instrumentation`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `addTransformer`, `isModifiableModule`, `redefineModule`, retransform/redefine.
- [Oracle Java SE 17 — `java.lang.instrument` package](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html): `-javaagent`, manifest, agent classes và hỗ trợ module reads khi instrumentation.
- [Java Platform Module System — JEP 261](https://openjdk.org/jeps/261): module path, unnamed/automatic modules, module layers và những lựa chọn launcher.

**Ghi nhớ:** `Module module` trong overload 6 tham số của `ClassFileTransformer.transform` cho biết **runtime module chứa class đang được biến đổi**, kể cả khi class chưa có `Class<?>` để truy vấn. **Named/unnamed module**, **defining class loader** và **internal class name** là ba trục nhận diện khác nhau. Dùng module callback để phân loại đúng, nhưng không xem nó là quyền truy cập hoặc thay thế việc verify bytecode và quản lý module graph.

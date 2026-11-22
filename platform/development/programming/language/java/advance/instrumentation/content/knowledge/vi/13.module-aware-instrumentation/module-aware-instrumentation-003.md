# Quan hệ đọc bổ sung mà JVM thiết lập cho module chứa lớp được biến đổi

Khi một Java agent biến đổi bytecode của lớp thuộc **named module**, bytecode mới có thể gọi một helper nằm trong agent JAR hoặc trong JAR được thêm vào bootstrap class loader. Thông thường, named module không mặc nhiên đọc unnamed module chứa helper trên classpath. Để mã instrumentation có cơ hội liên kết hợp lệ, JVM có một cơ chế đặc biệt: **module của lớp được biến đổi được sắp xếp để đọc unnamed module của bootstrap class loader và unnamed module của class loader đã nạp lớp agent chính**.

Đây là quy tắc được mô tả trực tiếp trong đặc tả gói [`java.lang.instrument` của Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html), mục **Instrumenting code in modules**. Bài này giải thích **đọc module (readability)** có nghĩa gì, JVM thêm quan hệ trong trường hợp nào, cách quan sát bằng chương trình Java 17+ và giới hạn của cơ chế khi helper nằm ở vị trí khác hoặc không thể truy cập.

## 1. Vấn đề trước khi JVM bổ sung quan hệ đọc

Java Platform Module System (JPMS) phân biệt:

- **Named module**: module có tên như `demo.app`, được xác định bởi `module-info.java` và đồ thị module khi chạy.
- **Unnamed module**: mỗi class loader có một unnamed module để chứa các lớp không thuộc named module, ví dụ lớp trên classpath. Các unnamed module đọc tất cả module; nhưng một named module thông thường **không tự đọc unnamed module**.
- **Read edge** `M → N`: module `M` đọc module `N`. Runtime API `M.canRead(N)` cho biết quan hệ này.
- **Exports**: module sở hữu package cho phép các module khác truy cập kiểu public trong package đó; đây là điều kiện khác với readability.
- **Class loading**: class loader có thực sự tìm/định nghĩa được class khi JVM giải tham chiếu bytecode hay không; read edge không tự tạo đường tra cứu lớp.

Giả sử một transformer chèn lời gọi sau vào `demo.Service.execute()` trong named module `demo.app`:

```text
invokestatic agent/ProbeHooks.hit:()V
```

Ở đây `agent.ProbeHooks` nằm trên classpath của agent, thuộc **unnamed module của system class loader**. Nếu chỉ nhìn vào `module-info.java` của `demo.app`, không có `requires` nào tới unnamed module ấy; cú pháp `requires` cũng không thể chỉ định một unnamed module như một module có tên.

JVM giúp agent bằng cách điều chỉnh quan hệ đọc khi lớp được transform. Vì thế, lời gọi helper do agent chèn **có thể** hợp lệ ở mức JPMS mà không cần sửa `module-info.java` của ứng dụng.

Điều kiện vẫn phải kiểm tra riêng: helper phải được loader thích hợp tìm thấy, package có thể truy cập, tên lớp và descriptor chính xác, và phương thức có mức truy cập đúng.

## 2. Chính xác JVM tạo thêm những quan hệ nào?

Đặc tả `java.lang.instrument` nêu rằng, để hỗ trợ lớp trợ giúp của agent, **module chứa lớp được biến đổi** sẽ đọc hai unnamed module:

1. **Unnamed module của bootstrap class loader**: thường là nơi agent chủ động đặt bridge/helper tối giản bằng `Instrumentation.appendToBootstrapClassLoaderSearch(...)` hoặc khai báo `Boot-Class-Path` hợp lệ.
2. **Unnamed module của class loader nạp lớp agent chính**: với startup agent thông thường, lớp từ agent JAR được nạp bằng **system class loader**, nên đây thường là unnamed module của system loader.

Có thể biểu diễn quan hệ được bổ sung như sau:

```text
                       Java agent
                    agent.ReadAgent
                    system class loader
                           |
                           v
            unnamed module của agent loader
                          ^  READS (bổ sung)
                          |
named module demo.app ----+
        |
        +----------------------> unnamed module của bootstrap loader
                           READS (bổ sung)
```

Mũi tên `READS` đi **từ module có lớp được instrument tới unnamed module chứa helper**. JVM không vì thế thêm một quan hệ ngược `agent → demo.app` và không tự động mở private package của ứng dụng cho reflection.

Quan hệ được thêm vào **module runtime**: nếu một lớp trong `demo.app` được biến đổi và JVM thêm cạnh đọc thì đó là quan hệ của `Module` tương ứng, không phải một thuộc tính riêng của một phương thức. Những lớp khác cùng module có thể quan sát cạnh đọc ấy sau khi nó được thiết lập.

### Điểm cần hiểu đúng

- Đây là hỗ trợ **đặc thù của Java Instrumentation** dành cho các unnamed module nêu trên, không phải quy tắc chung rằng mọi named module tự động đọc classpath.
- Cơ chế làm thay đổi **runtime module graph**; nó không thêm `requires` vào mã nguồn hoặc `module-info.class`, cũng không sửa kết quả biên dịch ban đầu.
- `Module.canRead(...)` kiểm tra trạng thái ở runtime; trước khi lớp liên quan được biến đổi, quan hệ có thể chưa xuất hiện.
- Agent có thể chạy ở system loader tùy cấu hình JVM; điều được đặc tả nhấn mạnh là **loader thực sự nạp lớp agent chính**, không phải một custom loader tùy ý do ứng dụng tạo ra.
- Việc thêm read edge không có nghĩa mọi module của JVM đều được sửa. Nó gắn với module của **lớp đã được biến đổi**.

## 3. Phân biệt bốn lớp điều kiện: read, load, export và access

Một read edge giải quyết đúng một phần của bài toán liên kết. Để bytecode target gọi được `agent.ProbeHooks.hit()`, thường cần:

| Lớp kiểm tra | Câu hỏi | API hoặc tín hiệu |
| --- | --- | --- |
| **Module readability** | Module của lớp target có đọc module chứa helper không? | `targetModule.canRead(helperModule)` |
| **Class-loader visibility** | Defining loader của target có thể tìm `agent.ProbeHooks` khi giải symbolic reference không? | `Class.forName(name, false, targetLoader)`, phân tích loader chain |
| **Package accessibility** | Package của helper có export sang module target không? | `helperModule.isExported("agent", targetModule)` |
| **Member accessibility** | Lớp/method `hit()V` có public và signature đúng không? | Bytecode, modifiers, `IllegalAccessError`/`NoSuchMethodError` |

Với helper thuộc **unnamed module**, các package của unnamed module được export ở runtime. Do đó bước exports thông thường thuận lợi; nhưng class/method vẫn phải truy cập được và loader vẫn phải tìm thấy class.

Ví dụ một plugin loader bị cô lập hoàn toàn với system loader có thể vẫn không resolve được `agent.ProbeHooks`. Khi đó `targetModule.canRead(agentUnnamed)` có thể là `true` nhưng lời gọi đã chèn vẫn gây `NoClassDefFoundError`.

Ngược lại, nếu helper nằm trong **một named module khác**, hai read edge đặc biệt nêu trên **không tự động tạo read edge tới named module ấy**. Có thể cần chỉnh quan hệ qua `Instrumentation.redefineModule(...)` cùng exports phù hợp.

## 4. Thí nghiệm Java 17+: quan sát `Module.canRead` trước và sau biến đổi

Thí nghiệm này có thể chạy bằng JDK 17 trở lên, **không cần thư viện ngoài**. Ta tạo named module `demo.app` và một startup agent. Agent đăng ký transformer chỉ xử lý `demo.Target`; transformer trả về một bản sao hợp lệ của bytecode ban đầu. Mã lớp không đổi chức năng nhưng callback trả một `byte[]` khác `null`, đủ để quan sát đường xử lý class transformation và quan hệ đọc tại runtime.

**Lưu ý phạm vi:** thí nghiệm chứng minh read edge mà JVM sắp xếp. Nó không chèn lời gọi hook thật; muốn chèn instruction `invokestatic` vào method thực tế, agent cần một bộ biến đổi bytecode phù hợp như ASM, Byte Buddy hoặc kỹ thuật tương đương.

### 4.1. Cấu trúc dự án

```text
module-read-demo/
├── agent.mf
├── agent-src/
│   └── agent/
│       └── ReadAgent.java
├── app-src/
│   └── demo.app/
│       ├── module-info.java
│       └── demo/
│           ├── Main.java
│           └── Target.java
└── out/                         # tạo khi biên dịch
    ├── agent/
    ├── mods/
    └── read-agent.jar
```

### 4.2. Startup agent và transformer

Tệp `agent-src/agent/ReadAgent.java`:

```java
package agent;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;

public final class ReadAgent {
    public static void premain(String args, Instrumentation inst) {
        inst.addTransformer(new ClassFileTransformer() {
            @Override
            public byte[] transform(
                    Module module,
                    ClassLoader loader,
                    String className,
                    Class<?> classBeingRedefined,
                    ProtectionDomain protectionDomain,
                    byte[] bytes) {

                // Một target duy nhất, thuộc named module demo.app.
                if ("demo/Target".equals(className)
                        && "demo.app".equals(module.getName())) {
                    System.out.println("transform: " + className);
                    // Không sửa logic; trả byte[] khác null để áp dụng
                    // đường xử lý transformation lên class này.
                    return bytes.clone();
                }
                return null;
            }
        });
    }
}
```

- Callback phiên bản Java 9+ có tham số `Module module`, chính là runtime module của lớp đang transform.
- `className` dùng dạng internal name `demo/Target`, không phải `demo.Target`.
- Trả `null` cho lớp ngoài phạm vi nghĩa là agent không biến đổi lớp đó.
- Dùng `bytes.clone()` vì buffer vào không được sửa trực tiếp; trong thí nghiệm, mảng byte trả về hợp lệ và có cùng nội dung. Khi instrument thật, trả một mảng chứa bytecode đã biến đổi hợp lệ.
- `addTransformer(...)` mặc định đăng ký transformer load-time; thí nghiệm không gọi `retransformClasses` nên **không cần** manifest `Can-Retransform-Classes: true`.

Tệp manifest `agent.mf` (có một dòng trống sau dòng cuối):

```text
Manifest-Version: 1.0
Premain-Class: agent.ReadAgent

```

### 4.3. Named module mục tiêu

Tệp `app-src/demo.app/module-info.java`:

```java
module demo.app {
}
```

Module này không khai báo `requires` tới bất kỳ thư viện agent nào. Lớp `Main` và `Target` nằm trong cùng module nên không cần `exports demo`.

Tệp `app-src/demo.app/demo/Target.java`:

```java
package demo;

public final class Target {
    static {
        System.out.println("Target initialized");
    }
}
```

Tệp `app-src/demo.app/demo/Main.java`:

```java
package demo;

public final class Main {
    public static void main(String[] args) throws Exception {
        Module named = Main.class.getModule();
        Module agentUnnamed =
                ClassLoader.getSystemClassLoader().getUnnamedModule();

        System.out.println("module=" + named.getName());
        System.out.println("before=" + named.canRead(agentUnnamed));

        // Không tham chiếu trực tiếp Target.class trong constant pool:
        // nạp bằng tên sau khi đã in trạng thái "before".
        Class.forName("demo.Target", true, Main.class.getClassLoader());

        System.out.println("after=" + named.canRead(agentUnnamed));
    }
}
```

Đây là lý do ví dụ dùng `Class.forName("demo.Target", ...)` thay vì nhắc trực tiếp `Target.class`: giúp trì hoãn việc nạp target tới sau dòng kiểm tra `before`, làm mốc quan sát rõ ràng hơn.

### 4.4. Biên dịch, đóng gói và chạy

Từ thư mục `module-read-demo`, tạo hai thư mục output. Trên Linux/macOS:

```bash
mkdir -p out/agent out/mods
```

Trên Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force out/agent, out/mods | Out-Null
```

Các lệnh còn lại dùng giống nhau trên hệ điều hành có JDK 17+:

```bash
javac --release 17 -d out/agent agent-src/agent/ReadAgent.java

jar --create --file out/read-agent.jar --manifest agent.mf -C out/agent .

javac --release 17 -d out/mods --module-source-path app-src \
  app-src/demo.app/module-info.java \
  app-src/demo.app/demo/Main.java \
  app-src/demo.app/demo/Target.java
```

Dòng lệnh `javac` trên được xuống dòng bằng dấu `\\` theo cú pháp shell POSIX; trên Windows PowerShell, dùng **một dòng** để tránh nhầm ký tự tiếp dòng:

```powershell
javac --release 17 -d out/mods --module-source-path app-src app-src/demo.app/module-info.java app-src/demo.app/demo/Main.java app-src/demo.app/demo/Target.java
```

**Chạy không có agent:**

```bash
java --module-path out/mods --module demo.app/demo.Main
```

Đầu ra:

```text
module=demo.app
before=false
Target initialized
after=false
```

**Chạy với startup agent:**

```bash
java -javaagent:out/read-agent.jar --module-path out/mods --module demo.app/demo.Main
```

Đầu ra:

```text
module=demo.app
before=false
transform: demo/Target
Target initialized
after=true
```

Hai kết quả trên đã được kiểm tra với OpenJDK 21 và mã `--release 17`. Ở trường hợp có agent, `ReadAgent` thuộc unnamed module của system loader; ban đầu `demo.app` không đọc unnamed module ấy. Khi `demo.Target` được transformer xử lý, JVM bổ sung quan hệ đọc vào module `demo.app`; sau đó `canRead` trả `true`.

**Điều quan sát được chính xác:** `after=true` cho biết runtime module graph có quan hệ đọc; nó **không chứng minh** bytecode của `Target` đã gọi helper hay mọi helper có thể nạp được. Ví dụ giữ nguyên bytecode cố ý để tách bạch cơ chế JPMS khỏi thao tác chèn method call.

Nếu áp dụng ví dụ vào JVM có thêm các agent khác hoặc các tùy chọn `--add-reads` đã mở sẵn cạnh đọc, `before` có thể là `true` từ đầu. Khi chẩn đoán nên kiểm tra cấu hình module graph đang chạy, không xem `false → true` là quy luật bất biến của mọi môi trường.

## 5. Khi chèn helper thật, automatic read edge giải quyết phần nào?

Giả sử transformer sửa `demo.Target.handle()` để chèn:

```text
invokestatic agent/ProbeHooks.hit:()V
```

Mã `agent.ProbeHooks` thuộc unnamed module của class loader nạp agent chính. Khi `demo.Target` được biến đổi, cơ chế bổ sung read edge giúp module `demo.app` đọc unnamed module đó, nên có thể vượt qua điều kiện **readability** của JPMS.

Tuy nhiên, JVM vẫn phải giải symbolic reference `agent/ProbeHooks` trong ngữ cảnh class loader của `demo.Target`. Nếu đó là một class loader biệt lập không tìm được helper qua parent hay class path của chính nó, có thể xảy ra `NoClassDefFoundError` dù read edge đã có. Nếu helper không có `public static void hit()`, có thể gặp `IllegalAccessError` hoặc `NoSuchMethodError` tùy lỗi.

Một cách thiết kế thường dùng:

```text
named module của lớp mục tiêu
          |
          +-- read edge tự động --> unnamed module của agent loader
          |
          +-- read edge tự động --> unnamed module của bootstrap loader
                                                    |
                                               public hook API
                                                    |
                                           lightweight dispatch
```

Agent triển khai hook bằng một **bootstrap helper nhỏ, ít phụ thuộc** khi cần phục vụ nhiều loader hoặc các lớp JDK. JAR helper có thể được đưa vào bootstrap search bằng `Instrumentation.appendToBootstrapClassLoaderSearch(JarFile)`. Cần chuẩn bị trước thời điểm sử dụng; thêm JAR sau khi một symbolic reference đã resolve thất bại không bảo đảm phục hồi được tham chiếu đó.

Read edge tự động **không tự đưa helper vào bootstrap**, không chép class giữa loader, không sửa bytecode để dùng đường nạp khác và không bảo đảm tương thích giữa các class có cùng tên do loader khác nhau định nghĩa.

## 6. Readability không đồng nghĩa với quyền reflection vào named module

Cơ chế tự động bổ sung cạnh đọc theo chiều **module mục tiêu → unnamed module chứa helper**. Trong khi đó, nhiều agent cần đi chiều khác: agent muốn đọc private field, gọi private method hoặc định nghĩa helper trong package của một lớp thuộc named module.

Phân biệt những câu hỏi sau:

| Tình huống | Cần kiểm tra |
| --- | --- |
| Bytecode trong target gọi public helper thuộc unnamed module | Read edge từ target đến unnamed module; helper loadable; public class/method và descriptor đúng |
| Agent reflection vào public API của package trong named module | Package có export phù hợp, class loader/module nhận diện chính xác |
| Agent dùng reflection sâu vào private member của target | Package phải `opens` thích hợp; read edge tự động không thay thế `opens` |
| Agent gọi helper thuộc một **named module khác** | Có read edge tới helper named module **và** package được export sang target |
| Agent định nghĩa class mới vào một package/module có kiểm soát | Cần cơ chế define class được cho phép, class loader/module/lookup chính xác; không suy ra từ automatic read edge |

Đặc biệt, `--add-opens` phục vụ deep reflection, khác với `--add-reads` cho readability. Một module có thể đọc module khác nhưng vẫn không truy cập được package không export.

## 7. Khi nào cần `Instrumentation.redefineModule`?

Nếu instrumentation muốn thêm quan hệ tới **named module khác**, hoặc cần export/open bổ sung, API `Instrumentation.redefineModule` là công cụ phù hợp trong những trường hợp module cho phép sửa đổi.

Ví dụ **đoạn mã minh họa, không phải chương trình độc lập**: bạn đã có `Instrumentation inst`, `Module targetModule` (module chứa lớp được biến đổi), và `Module helperModule` (named module chứa `com.example.probe.ProbeHooks`):

```java
import java.lang.instrument.Instrumentation;
import java.util.Map;
import java.util.Set;

// Đã xác định inst, targetModule, helperModule từ runtime.
if (!inst.isModifiableModule(targetModule)
        || !inst.isModifiableModule(helperModule)) {
    throw new IllegalStateException("Module cannot be modified");
}

inst.redefineModule(
        targetModule,
        Set.of(helperModule), // extraReads: target đọc helper named module
        Map.of(),             // extraExports
        Map.of(),             // extraOpens
        Set.of(),             // extraUses
        Map.of());            // extraProvides

inst.redefineModule(
        helperModule,
        Set.of(),
        Map.of("com.example.probe", Set.of(targetModule)),
        Map.of(),
        Set.of(),
        Map.of());
```

Đoạn minh họa cho thấy hai việc **khác nhau**: thêm read edge của target và export package của helper về phía target. Package `com.example.probe` phải thật sự thuộc `helperModule`, và các module/class liên quan đã phải tồn tại.

**Không cần tự gọi đoạn mã này chỉ để thêm hai read edge tới unnamed module mà JVM đã hứa thiết lập trong Java Instrumentation.** Chỉ dùng khi có yêu cầu bổ sung thật và khi đã xác minh điều kiện hệ thống.

Đối với `redefineModule`, các điều chỉnh là mở rộng: API không cung cấp cách loại bỏ read edge/export/open hiện có. Vì vậy thay đổi module graph trong JVM sống lâu cần có phạm vi và lý do rõ ràng; không nên thử nhiều điều chỉnh rồi cho rằng có thể hoàn tác hoàn toàn như sửa một biến cấu hình.

## 8. Cách chẩn đoán tại runtime

Trong agent, sau khi lớp mục tiêu đã được transform và `Class<?> targetClass` có sẵn, có thể kiểm tra quan hệ với module agent:

```java
// Snippet dùng trong agent; targetClass là Class<?> thực tế.
Module targetModule = targetClass.getModule();
Module agentModule = ReadAgent.class.getModule();

System.out.println("target module=" + targetModule.getName());
System.out.println("agent module named=" + agentModule.isNamed());
System.out.println("target reads agent=" + targetModule.canRead(agentModule));
System.out.println("target loader=" + targetClass.getClassLoader());
System.out.println("agent loader=" + ReadAgent.class.getClassLoader());
```

Snippet trên là đoạn chẩn đoán trong class `agent.ReadAgent` sau khi `targetClass` đã được cung cấp; không chép nó vào `Main` của named module để import trực tiếp `agent.ReadAgent`, vì `Main` ban đầu không có phụ thuộc compile-time ấy.

Nếu đã có `Class<?> helperClass`, xem package exports và danh tính loader:

```java
// helperClass là Class<?> thực sự được dùng cho helper.
Module helperModule = helperClass.getModule();
System.out.println("read=" + targetClass.getModule().canRead(helperModule));
System.out.println("exported=" + helperModule.isExported(
        helperClass.getPackageName(), targetClass.getModule()));
System.out.println("helper loader=" + helperClass.getClassLoader());
```

`Module.canRead` không bảo đảm chắc chắn JVM sẽ resolve được helper bằng target loader; có thể kiểm thử riêng khả năng tìm class:

```java
try {
    Class<?> seen = Class.forName(
            "agent.ProbeHooks", false, targetClass.getClassLoader());
    System.out.println("resolved helper loader=" + seen.getClassLoader());
} catch (ClassNotFoundException e) {
    System.out.println("Target loader cannot find helper: " + e);
}
```

Một lần `Class.forName` chỉ kiểm tra tên class qua loader đã chọn, **không** chứng minh tất cả đường gọi, chữ ký, access hay dependencies sâu đều đúng.

### Bảng phân tích kết quả

| Quan sát | Kết luận phù hợp |
| --- | --- |
| `canRead=false` trước lần transform đầu tiên | Bình thường với named module thông thường, nếu chưa có cạnh đọc khác |
| `canRead=true` sau khi một class trong module được transform | Phù hợp cơ chế bổ sung read edge |
| `canRead=true` ngay từ đầu | Có thể module đã có cạnh đọc do config/agent trước đó hoặc là automatic module; chưa chứng minh agent của bạn thực sự transform target |
| `canRead=true` nhưng `ClassNotFoundException` / `NoClassDefFoundError` | Tập trung vào loader visibility, nơi chứa helper, dependency và lỗi khởi tạo |
| `canRead=true` nhưng `IllegalAccessError` | Kiểm tra package exports, mức truy cập class/method và định danh module |
| Có lỗi `InaccessibleObjectException` khi reflective access | Xem `opens` cho reflection, không nhầm với read edge |
| `canRead=false` sau khi chỉ đăng ký transformer | Chưa chắc có lỗi: chưa có class phù hợp được transform hoặc transformer trả `null` |
| Helper nằm trong named module khác | Automatic reads tới unnamed module không đủ; cân nhắc `redefineModule` nếu cần |

**Thứ tự chẩn đoán hiệu quả:** (1) ghi đúng `Class<?>/Module/ClassLoader` của target, (2) chứng minh transformer đã được gọi và trả bytes cho class mong muốn, (3) kiểm tra `canRead`, (4) kiểm tra helper loadable, (5) kiểm tra exports, members, descriptor và dependencies.

## 9. Những hiểu nhầm cần tránh

1. **“Lớp agent nhìn thấy helper nên target chắc chắn nhìn thấy.”** Transformer chạy bằng loader của agent; bytecode đã chèn được liên kết trong ngữ cảnh của lớp mục tiêu. Đây là hai môi trường cần kiểm tra riêng.
2. **“`--add-reads` tự sửa classpath.”** Không. Readability và classloader delegation/search path là hai cơ chế khác nhau.
3. **“Bổ sung quan hệ đọc là mở toàn bộ module.”** Không. Nó không tự `opens` các package private, không trao quyền deep reflection và không thay thế kiểm tra Java access.
4. **“Quan hệ đọc tới unnamed module của agent áp dụng cho mọi named module.”** Không. Đặc tả gắn quy tắc với module của lớp được transform. Đừng suy rộng ra module không tham gia instrumentation.
5. **“Agent JAR là một named module vì dùng `-javaagent`.”** Theo đặc tả, lớp từ agent JAR được system loader nạp và thuộc unnamed module của loader ấy, trừ các bố trí đặc biệt của mã phụ trợ mà agent tự triển khai.
6. **“Read edge giúp target truy cập bất kỳ helper named module nào.”** Không. Hai đích đặc biệt là unnamed module của bootstrap và loader nạp lớp agent chính.
7. **“Phải sửa `module-info.java` rồi build lại ứng dụng để instrument.”** JVM có cơ chế runtime đặc thù cho trường hợp này; source descriptor không cần thay đổi để quan sát read edge do instrumentation.
8. **“`Module.canRead=true` chứng minh phép đo đã hoạt động.”** Chưa. Cần kiểm tra bytecode thực sự được chèn, helper được gọi và dữ liệu probe xuất hiện.
9. **“Có thể gỡ read edge khi tắt probe.”** `redefineModule` chỉ mở rộng module graph, không cung cấp thao tác loại bỏ các quan hệ đã thêm. Hãy tách việc bật/tắt instrumentation khỏi suy nghĩ rằng module graph sẽ quay về nguyên trạng.
10. **“Mọi class đều chuyển `false → true` giống ví dụ.”** Unnamed/automatic module hoặc cấu hình có `--add-reads` có thể đã đọc unnamed module từ trước; quan sát cần đặt trong bối cảnh.

## 10. Câu hỏi tự kiểm tra

1. JVM bổ sung quan hệ đọc tới những **hai unnamed module** nào khi một lớp được biến đổi bởi Java Instrumentation?
2. Chiều `targetModule → agentUnnamed` giải quyết điều kiện nào khi bytecode gọi `agent.ProbeHooks.hit()`?
3. Vì sao thêm read edge không giúp một class loader cô lập tìm được helper chỉ nằm trong classpath của system loader?
4. Vì sao chương trình thử nghiệm in `before=false` khi không có agent, còn `after=true` khi agent trả `bytes.clone()` cho `demo.Target`?
5. Trường hợp nào cần dùng `Instrumentation.redefineModule` dù JVM đã tự thiết lập hai read edge đặc biệt?
6. Khác nhau giữa `canRead`, `isExported` và `isOpen` là gì? Lỗi ở từng tầng sẽ biểu hiện ra sao?
7. Nếu `canRead` của module target đã `true` ngay từ đầu, bạn kiểm tra gì trước khi kết luận transformer có tác dụng?
8. Vì sao không thể dùng kết quả `canRead=true` làm điều kiện duy nhất để công bố một probe hoạt động thành công?

## 11. Tài liệu chính thức

- [Java 17 — `java.lang.instrument` package, phần *Instrumenting code in modules*](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html): quy tắc JVM cho module của lớp được biến đổi đọc hai unnamed module.
- [Java 21 — `java.lang.Module`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Module.html): `canRead`, `isExported`, `isOpen` và khác biệt giữa named/unnamed module.
- [Java 21 — `java.lang.instrument.Instrumentation`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `addTransformer`, `redefineModule`, bootstrap/system class-loader search.
- [Java 21 — `ClassFileTransformer`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): callback nhận `Module`, `ClassLoader`, input bytes và giá trị trả về.
- [Java 21 — Java Virtual Machine Specification, Chương 5](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html): nạp lớp, liên kết và giải symbolic reference.

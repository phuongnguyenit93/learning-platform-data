# Tách helper tối thiểu khỏi phần agent có nhiều phụ thuộc

> **Mục tiêu:** Thiết kế Java instrumentation sao cho mã được chèn vào ứng dụng chỉ phải gọi một **helper nhỏ và ổn định**, trong khi `premain`, bytecode transformer, logging, exporter, serialization và những thư viện phức tạp vẫn nằm trong **agent runtime**. Hiểu ranh giới class loader, phụ thuộc bắc cầu, `appendToBootstrapClassLoaderSearch`, JPMS, giới hạn của bootstrap helper và cách kiểm tra bằng một thí nghiệm Java 17+ xây hai JAR riêng.

Bài thuộc nhóm **Class loader và helper**. Nó tập trung vào **linkage của lời gọi helper** sau khi JVM đã instrument class, không giả định mọi class được nạp bởi system class loader. Một transformer có thể tạo class file hợp lệ nhưng ứng dụng vẫn thất bại khi chạy vì class loader của **class được biến đổi** không tìm thấy helper mà transformer đặt vào bytecode.

## 1. Tại sao phải tách?

Trong một Java agent thực tế thường có:

- `Agent.premain(...)` hoặc `agentmain(...)` để khởi tạo agent.
- `ClassFileTransformer`, thư viện ASM/Byte Buddy hoặc Class-File API để biến đổi bytes.
- Bộ lọc class/method, policy, cấu hình và feature flags.
- Exporter HTTP/gRPC, batching, metrics/tracing SDK, serializer JSON.
- Worker threads, loggers, cache, retry và shutdown hooks.
- Một đoạn **helper** mà method đã được instrument sẽ gọi rất thường xuyên.

Giả sử transformer chèn instruction tương đương:

```text
invokestatic example/agent/HeavyTracer.onEnter:()V
```

Đây là cách **ghi chú symbolic method reference**, không phải Java source hoặc assembler chạy độc lập. Khi class ứng dụng chạy, JVM phải giải quyết `example.agent.HeavyTracer` và method `onEnter()V` qua hệ class loader/module của class ấy. Dù agent thấy `HeavyTracer` trên classpath riêng, ứng dụng có thể không thấy được. Nếu `HeavyTracer` lại cần `com.vendor.HttpExporter`, `org.slf4j.*` hoặc thư viện bytecode, loader của helper còn phải resolve toàn bộ dependency graph đó.

Một thiết kế đáng tin cậy hơn:

```text
    Rich Java Agent Runtime              Minimal Bridge/Helper
  ┌──────────────────────────┐         ┌────────────────────────────┐
  │ premain / transformer    │         │ tiny public static API     │
  │ config, Byte Buddy/ASM   │         │ bootstrap-visible deps    │
  │ exporter / SDK / logging │         │ low overhead / no network  │
  │ batching / error policy  │         │ stable method descriptors  │
  └───────────┬──────────────┘         └──────────────▲─────────────┘
              │ setup/consume                     │
              └───────────────────────────────────┘
                                                  │ invokestatic
                                 ┌────────────────┴──────────────┐
                                 │ Instrumented application     │
                                 │ methods, custom class loader │
                                 └───────────────────────────────┘
```

Tư duy chính là **đảo hướng phụ thuộc**: rich agent có thể biết helper, nhưng helper **không import** rich agent. Nếu cần chuyển dữ liệu, dùng counter, bounded buffer hoặc interface rất nhỏ được định nghĩa ở phía bridge; không kéo exporter/network trực tiếp vào đường chạy ứng dụng.

## 2. So sánh hai phần

| Tiêu chí | Helper tối thiểu | Phần agent có nhiều phụ thuộc |
| --- | --- | --- |
| Caller | Method trong ứng dụng đã instrument | JVM gọi `premain`, agent tự tổ chức |
| Vai trò | Ghi nhận nhanh, giữ API cho callsite | Tạo bytecode, điều phối, xuất dữ liệu |
| Loader | Nơi target chắc chắn resolve được; đôi khi bootstrap | System/agent-specific loader |
| Phụ thuộc | Ưu tiên `java.base`, không phụ thuộc agent | Bytecode SDK, JSON, HTTP, metrics, log |
| Tần suất | Có thể hàng triệu lần/giây | Theo cấu hình/batch/đợt transform |
| API | Nhỏ, rõ phiên bản, ổn định descriptor | Có thể thay đổi nội bộ |
| Tài nguyên | Ít allocation, không block, không network | Thread, queue, file/network tùy nhu cầu |
| Trạng thái | Counter hoặc trạng thái tối giản | Config, exporter, caches, retry policy |
| Rủi ro | Loader mismatch, ABI, initialization | Dependency conflict, lifecycle |
| Test chính | JVM có resolve helper đúng không? | Transformer và exporter làm đúng không? |

**Một JAR ít byte không đồng nghĩa helper thực sự tối thiểu.** Một class có static initializer mở HTTP connection vẫn là helper nặng. Một helper gồm vài method và một `LongAdder` của `java.base` dễ kiểm tra hơn.

## 3. Runtime class identity: tên giống nhau chưa chắc cùng class

Trong JVM, class identity phụ thuộc **binary name và defining class loader**. Hai loader khác nhau có thể định nghĩa cùng tên `example.bridge.ProbeBridge` nhưng tạo hai runtime types độc lập:

```text
Loader L1: example.bridge.ProbeBridge → static counter A
Loader L2: example.bridge.ProbeBridge → static counter B
```

Khi đó counter A không chia sẻ state với counter B. Một interface trong agent loader và một interface cùng tên từ plugin loader có thể không tương thích; cast giữa các đối tượng có thể ném `ClassCastException` dù tên class y hệt. Loader constraints còn có thể tạo linkage errors.

### Các loader thường gặp

- **Bootstrap class loader:** định nghĩa các lớp cốt lõi và những class agent cố ý thêm vào bootstrap search. Với `Class.getClassLoader()`, giá trị `null` biểu thị bootstrap loader.
- **Platform class loader:** xử lý một phần platform modules; không có nghĩa nó là con của system loader.
- **System/application class loader:** thường nạp application classpath và main Java agent class.
- **Custom loaders:** plugin/app-server/servlet/OSGi/framework; có thể parent-first, child-first hoặc có quy tắc riêng.

Một custom loader có parent là **bootstrap** hoặc **platform** có thể không thấy class chỉ nằm trong system loader của agent. Tương tự, class được bootstrap định nghĩa không tự “nhìn xuống” system loader để giải quyết một thư viện agent.

Đây là lý do việc `javac` compile được transformer và helper với một classpath lớn **không chứng minh** lớp ứng dụng đã instrument sẽ link được helper tại runtime.

## 4. Vì sao bootstrap helper phải chỉ phụ thuộc bootstrap-visible classes?

Javadoc `java.lang.instrument` quy định các supporting classes agent bố trí để **bootstrap loader** định nghĩa qua `appendToBootstrapClassLoaderSearch` hoặc `Boot-Class-Path` phải chỉ **liên kết** tới các class cũng được bootstrap định nghĩa. Không có bảo đảm tất cả platform classes có thể được bootstrap định nghĩa.

Ví dụ sai về dependency boundary:

```java
// MÃ MINH HỌA KHÔNG NÊN DÙNG.
package example.bridge;

import example.agent.runtime.RichExporter;
import com.vendor.json.JsonWriter;

public final class ProbeBridge {
    public static void hit() {
        RichExporter.send(JsonWriter.encode("hit"));
    }
}
```

Kể cả khi compile nhờ library trên classpath, bootstrap loader có thể không thấy `RichExporter` và `JsonWriter` khi method được liên kết/thực thi. Một lỗi thường gặp là `NoClassDefFoundError`, nhưng nguyên nhân cụ thể và thời điểm JVM phát hiện còn tùy bytecode/loader. Không giải quyết bằng cách append toàn bộ agent-fat.jar vào bootstrap.

Ví dụ tốt hơn:

```java
package example.bridge;

import java.util.concurrent.atomic.LongAdder;

public final class ProbeBridge {
    private static final LongAdder HITS = new LongAdder();

    private ProbeBridge() {}

    public static void hit() {
        HITS.increment();
    }

    public static long total() {
        return HITS.sum();
    }
}
```

`LongAdder` thuộc `java.base`, thích hợp để cung cấp bộ đếm nội bộ tối giản. `sum()` **không phải snapshot nguyên tử** trong lúc các thread khác còn ghi; điều đó bình thường đối với telemetry tổng hợp, không phải sổ cái giao dịch.

**Phân biệt loader và module:** Class `ProbeBridge` do bootstrap loader định nghĩa sẽ thuộc **unnamed module của bootstrap loader**; nó **không** tự trở thành class trong `java.base`. Không đặt helper ở package `java.*` hoặc dùng tên dễ xung đột với package ứng dụng/thư viện.

## 5. Những gì nên và không nên có trong helper

Một API bridge tốt thường có những thuộc tính:

1. `public` class và những method `public static` với tên/descriptor ổn định nếu bytecode gọi trực tiếp qua `invokestatic`.
2. Tham số đơn giản (`int`, `long`, `boolean`, đôi khi `String` đã chuẩn hóa), tránh object của plugin/tenant loader.
3. Không import `demo.agent.*`, SDK observability, thư viện bytecode, JSON serializer, logging framework.
4. Không tạo network connection, ghi file hoặc chờ lock có thể kéo dài trong method được chèn vào hot path.
5. Không `Thread.sleep`, `BlockingQueue.put` hay serialize request trên mỗi invocation.
6. Không giữ raw `ClassLoader`, `Class<?>`, `Throwable`, request object trong static map không giới hạn.
7. Tạo object tối thiểu; nếu cần queue thì bounded, có drop/backpressure policy.
8. Không instrument lại package helper hoặc thư viện agent để tránh recursion.
9. Không thực hiện classpath scanning hoặc dependency injection trong `<clinit>` của bridge.
10. Có hành vi xác định khi agent exporter không sẵn sàng: no-op, count hoặc drop có thống kê.
11. Có chiến lược versioning cho phương thức đã được bytecode cũ tham chiếu.
12. Bảo đảm lỗi telemetry thông thường không thay đổi exception/return nghiệp vụ theo chính sách vận hành.

Ví dụ descriptor cho callsite:

```text
ProbeBridge.hit()           → ()V
ProbeBridge.record(long)    → (J)V
ProbeBridge.record(int,long)→ (IJ)V
```

Đây là **bảng chữ ký**, không phải source runnable. Khi transformer chèn lời gọi, JVM cần chính xác owner internal name, method name và method descriptor. Đổi `hit:()V` thành `hit:(I)V` mà không cập nhật class cũ sẽ gây `NoSuchMethodError` dù helper JAR được nạp thành công.

## 6. Cách chọn nơi chứa helper

| Cách triển khai | Khi nào nên dùng | Giới hạn cần thử |
| --- | --- | --- |
| `appendToBootstrapClassLoaderSearch(JarFile)` | Helper cần được nhiều loader nhìn thấy, kể cả bootstrap | Chỉ phụ thuộc bootstrap classes; append sớm; package riêng |
| `Boot-Class-Path` trong agent manifest | Startup agent biết đường dẫn helper JAR | Đúng URI/path tương đối với agent JAR; cùng hạn chế bootstrap |
| `appendToSystemClassLoaderSearch(JarFile)` | Class target thật sự thấy system loader | Custom loader không delegate system có thể không thấy |
| Inject helper vào target loader | Framework/plugin có loader riêng và muốn hạn chế phạm vi | Class identity, duplicate definitions, loader lifecycle |
| Bundle helper vào ứng dụng | Ứng dụng chủ động tích hợp API | Độ tương thích/version do app và agent cùng quản lý |

**Không có lựa chọn tốt tuyệt đối.** Bootstrap phù hợp khi helper thật sự nhỏ và lớp instrumented chạy trong nhiều loader; nó cũng mở rộng bề mặt class loading của toàn JVM. Với ứng dụng chỉ dùng một loader cố định, đóng gói helper ngay nơi loader đó thấy được có thể đơn giản hơn.

### `Boot-Class-Path` khác `Class-Path`

Một agent manifest có thể cấu hình:

```text
Manifest-Version: 1.0
Premain-Class: demo.agent.SplitAgent
Boot-Class-Path: bridge.jar

```

Đây là **cấu hình thay thế**, không dùng trong lab chính bên dưới. Đường dẫn tương đối của `Boot-Class-Path` được resolve theo vị trí agent JAR theo đặc tả. Khi agent được nạp muộn, những path không phải JAR có quy tắc riêng; bài này dùng startup agent để giảm sự phức tạp.

## 7. Hiểu `appendToBootstrapClassLoaderSearch`

`Instrumentation.appendToBootstrapClassLoaderSearch(JarFile)` thêm một JAR vào **đường tìm kiếm khi bootstrap loader không tìm thấy class theo các cơ chế mặc định**. Nếu gọi nhiều lần, JAR mới được xét theo thứ tự append. Nó **không**:

- Thay một class đã được định nghĩa bằng cùng tên.
- Bắt mọi class-loader search hiện tại tự nạp lại các references thất bại.
- Tự khiến bootstrap helper nhìn thấy các class chỉ có ở system/custom loader.
- Tự kiểm chứng helper JAR có class đáng tin cậy hay không.
- Cung cấp API remove/rollback các JAR đã append.
- Cho phép đưa cả một fat agent JAR với mọi library vào bootstrap an toàn.

Javadoc cảnh báo rất cụ thể: một JAR append vô tình chứa private/package-access class của ứng dụng có thể khiến bootstrap định nghĩa class đó trong quá trình parent delegation, gây `IllegalAccessError` khó tìm. **Đặt package helper duy nhất** và chỉ chứa resource/class thực sự dành cho bootstrap.

Một cảnh báo nữa là **negative resolution caching** theo JVM specification: sau một lần resolve symbolic reference thất bại, một số tham chiếu có thể tiếp tục thất bại với cùng lỗi dù JAR được append về sau. Vì vậy `premain` nên append helper **trước khi ứng dụng sử dụng hoặc JVM resolve callsite mới**. Đừng đợi đến khi thấy `NoClassDefFoundError` rồi hy vọng append JAR sẽ sửa được toàn bộ trạng thái class đã nạp.

Mẫu kiểm chứng chủ động:

```java
// Trong agent đã có Instrumentation inst và JarFile helperJar:
inst.appendToBootstrapClassLoaderSearch(helperJar);

Class<?> bridge = Class.forName(
        "demo.bootstrap.ProbeBridge", false, null);

if (bridge.getClassLoader() != null) {
    throw new IllegalStateException(
            "Bridge was not defined by bootstrap loader");
}
```

`null` ở tham số thứ ba của `Class.forName` yêu cầu **bootstrap loader**. Tham số `false` có nghĩa không cố tình initialize class ở bước kiểm tra này. Khi class vẫn không được tìm thấy, `ClassNotFoundException` cần được xử lý ở startup, không âm thầm cho ứng dụng chạy rồi gặp lỗi khó chẩn đoán.

## 8. Lab Java 17+: build bridge.jar và agent.jar riêng

Mục tiêu là **chứng minh runtime class loading**, không phải giới thiệu thư viện sửa bytecode. Lab sử dụng một app gọi `ProbeBridge.hit()` trực tiếp từ source: lời gọi ấy có semantics tương đương callsite `invokestatic` mà một transformer có thể chèn. `ClassFileTransformer` trong agent được đăng ký nhưng **trả `null`**, vì chúng ta không muốn phụ thuộc ASM/Byte Buddy để kiểm chứng helper visibility.

### 8.1. Layout

```text
split-helper-demo/
├── agent.mf
├── bridge-src/
│   └── demo/bootstrap/ProbeBridge.java
├── agent-src/
│   └── demo/agent/
│       ├── SplitAgent.java
│       └── runtime/RichReporter.java
└── app-src/
    └── demo/app/DemoApp.java
```

Sản phẩm build sẽ nằm tại `out/bridge.jar`, `out/agent.jar` và `out/app`. Không đặt `ProbeBridge.class` trong `agent.jar`.

### 8.2. File `bridge-src/demo/bootstrap/ProbeBridge.java`

```java
package demo.bootstrap;

import java.util.concurrent.atomic.LongAdder;

// Lớp này chỉ có dependency bootstrap-visible thuộc java.base.
public final class ProbeBridge {
    private static final LongAdder HITS = new LongAdder();

    private ProbeBridge() {
    }

    public static void hit() {
        HITS.increment();
    }

    public static long total() {
        return HITS.sum();
    }
}
```

Trong lab, chỉ có một thread tăng counter ba lần; vì vậy `total()` cho kết quả xác định. Trong ứng dụng thật, `LongAdder.sum()` có thể không là snapshot nguyên tử khi producer còn cập nhật, nên dùng làm metric tổng hợp chứ không làm sổ cái.

### 8.3. File `agent-src/demo/agent/runtime/RichReporter.java`

```java
package demo.agent.runtime;

// Đại diện phần agent nhiều phụ thuộc; lab không cần network hoặc SDK ngoài.
public final class RichReporter {
    private RichReporter() {
    }

    public static String ready() {
        return "agent: rich-side=ready";
    }
}
```

Trong production, package này có thể chứa exporter, SDK, config và retry. **Không được** để `ProbeBridge` import `RichReporter`: một class bootstrap không thể giả định nó link được class trong system loader. Ví dụ cố ý không cần thư viện ngoài để người học chỉ phải dùng JDK 17+.

### 8.4. File `agent-src/demo/agent/SplitAgent.java`

```java
package demo.agent;

import demo.agent.runtime.RichReporter;
import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.nio.file.Path;
import java.security.ProtectionDomain;
import java.util.jar.JarFile;

public final class SplitAgent {
    // Giữ JarFile còn sống trong vòng đời demo.
    private static JarFile bootstrapJar;

    public static void premain(String options, Instrumentation inst)
            throws Exception {
        if (options == null || options.isBlank()) {
            throw new IllegalArgumentException(
                    "Expected bootstrap helper JAR path");
        }

        bootstrapJar = new JarFile(Path.of(options).toFile());
        inst.appendToBootstrapClassLoaderSearch(bootstrapJar);

        // Kiểm tra ngay bootstrap loader có tìm được helper hay không.
        Class<?> bridge = Class.forName(
                "demo.bootstrap.ProbeBridge", false, null);
        if (bridge.getClassLoader() != null) {
            throw new IllegalStateException(
                    "Helper was not defined by bootstrap loader");
        }
        System.out.println("agent: helper-loader=bootstrap");

        // Rich side không nằm trong helper JAR.
        System.out.println(RichReporter.ready());

        inst.addTransformer(new ClassFileTransformer() {
            @Override
            public byte[] transform(
                    Module module,
                    ClassLoader loader,
                    String className,
                    Class<?> classBeingRedefined,
                    ProtectionDomain domain,
                    byte[] classfileBuffer) {
                // Lab chỉ đăng ký hook; không sửa bytecode.
                // Trong agent thật: filter class, rồi chèn call
                // demo/bootstrap/ProbeBridge.hit:()V.
                return null;
            }
        }, false);
        System.out.println("agent: transformer=registered");
    }
}
```

**Phân tích:**

- `premain` chạy trước application `main` khi dùng `-javaagent`.
- `bootstrapJar` được giữ bằng static reference và không đóng sớm trong demo.
- Path helper từ `agentArgs` được dùng để mở `JarFile`, append vào bootstrap search.
- `Class.forName(..., false, null)` chỉ kiểm tra bootstrap search; không nhờ system loader.
- `RichReporter` chỉ thuộc `agent.jar`, không bị helper tham chiếu.
- Transformer Java 17 override `transform(Module,...)`; trả `null` là giữ nguyên bytes. Lab không khẳng định có probe bytecode mới được chèn.
- Không cần manifest capability `Can-Retransform-Classes`/`Can-Redefine-Classes` vì lab không gọi hai API này.
- Trong production, **không nhận JAR path không đáng tin** để append. Xác minh checksum/signature, package và quyền triển khai vì Java agent có khả năng can thiệp sâu vào JVM.

### 8.5. File `app-src/demo/app/DemoApp.java`

```java
package demo.app;

import demo.bootstrap.ProbeBridge;

public final class DemoApp {
    public static void main(String[] args) {
        ClassLoader loader = ProbeBridge.class.getClassLoader();
        System.out.println("app: helper-loader=" +
                (loader == null ? "bootstrap" : "other"));

        ProbeBridge.hit();
        ProbeBridge.hit();
        ProbeBridge.hit();

        System.out.println("app: hits=" + ProbeBridge.total());
    }
}
```

Đây là **app đã chứa sẵn các callsite**. Đối với output transformer thực tế, bytecode sẽ chứa symbolic methodref tới `demo/bootstrap/ProbeBridge.hit:()V` khi chèn instruction tương đương. App chỉ cần class file bridge **lúc compile**, còn **lúc chạy** nó phải resolve helper qua bootstrap search đã được agent cấu hình.

### 8.6. File `agent.mf`

```text
Manifest-Version: 1.0
Premain-Class: demo.agent.SplitAgent

```

Giữ một newline và dòng trống cuối manifest. Không cấu hình `Boot-Class-Path` trong lab này, vì `premain` tự gọi append với path từ options.

### 8.7. Lệnh Bash

Tại thư mục `split-helper-demo`:

```bash
mkdir -p out/bridge out/agent out/app

javac -encoding UTF-8 -d out/bridge \
    bridge-src/demo/bootstrap/ProbeBridge.java
jar --create --file out/bridge.jar -C out/bridge .

javac -encoding UTF-8 -d out/agent \
    agent-src/demo/agent/runtime/RichReporter.java \
    agent-src/demo/agent/SplitAgent.java
jar --create --file out/agent.jar \
    --manifest agent.mf -C out/agent .

javac -encoding UTF-8 -cp out/bridge.jar -d out/app \
    app-src/demo/app/DemoApp.java

java -javaagent:out/agent.jar=out/bridge.jar \
    -cp out/app demo.app.DemoApp
```

Điểm then chốt: lệnh compile app dùng `-cp out/bridge.jar`, nhưng runtime chỉ `-cp out/app`. `out/bridge.jar` đi vào **bootstrap search** qua `-javaagent:out/agent.jar=out/bridge.jar`; phần sau dấu `=` chính là chuỗi options truyền vào `premain`, không phải classpath. `agent.jar` được JVM tìm theo cơ chế `-javaagent`, không cần đặt nó vào runtime `-cp` của app.

### 8.8. Lệnh PowerShell

```powershell
New-Item -ItemType Directory -Force `
    -Path out/bridge, out/agent, out/app | Out-Null

javac -encoding UTF-8 -d out/bridge `
    bridge-src/demo/bootstrap/ProbeBridge.java
jar --create --file out/bridge.jar -C out/bridge .

javac -encoding UTF-8 -d out/agent `
    agent-src/demo/agent/runtime/RichReporter.java `
    agent-src/demo/agent/SplitAgent.java
jar --create --file out/agent.jar `
    --manifest agent.mf -C out/agent .

javac -encoding UTF-8 -cp out/bridge.jar -d out/app `
    app-src/demo/app/DemoApp.java

java -javaagent:out/agent.jar=out/bridge.jar `
    -cp out/app demo.app.DemoApp
```

Dùng JDK 17+ (`java`, `javac`, `jar` cùng bộ JDK). PowerShell sử dụng backtick làm dấu nối dòng; Bash sử dụng backslash. Trong lệnh compile của bài này chỉ có một JAR làm compile classpath, nên không cần ghép nhiều entry bằng `:` hoặc `;`.

### 8.9. Stdout dự kiến

Trong môi trường HotSpot/OpenJDK phổ biến, khi JAR đúng và không có agent khác in thêm log:

```text
agent: helper-loader=bootstrap
agent: rich-side=ready
agent: transformer=registered
app: helper-loader=bootstrap
app: hits=3
```

Thứ tự có ý nghĩa: agent thêm bootstrap search và kiểm tra loader **trước** khi app bắt đầu. App nhìn thấy **cùng helper do bootstrap định nghĩa**. Ba lần `hit` liên tiếp trong cùng thread tạo counter 3.

Đầu ra `agent: transformer=registered` chỉ xác nhận đã gọi `addTransformer`; **không** chứng minh transformer tạo bytes mới vì method `transform` trả `null`. Ví dụ dùng source callsite để kiểm tra loader boundary một cách cô lập.

### 8.10. Kiểm tra nội dung JAR và dependency

```bash
jar --list --file out/bridge.jar
jar --list --file out/agent.jar
jdeps -verbose:class out/bridge.jar
javap -classpath out/bridge.jar -p demo.bootstrap.ProbeBridge
```

Kết quả `bridge.jar` phải có `demo/bootstrap/ProbeBridge.class` và metadata JAR thông thường, **không có** `demo/agent/SplitAgent.class`, `net/bytebuddy/...`, `org/objectweb/asm/...` hay exporter. `agent.jar` cần có `demo/agent/SplitAgent.class`, class ẩn danh của transformer, `RichReporter.class` và manifest, **không có `ProbeBridge.class`**.

`jdeps` giúp phát hiện **static dependencies** ở bytecode, nhưng không chứng minh mọi reflection hoặc dynamic class lookup đều an toàn. Kết hợp inspection JAR, `getClassLoader` runtime và smoke test.

## 9. Những thí nghiệm đối chứng

### A. Không append helper vào bootstrap

Nếu bỏ lời gọi `appendToBootstrapClassLoaderSearch`, nhưng giữ `Class.forName(binaryName, false, null)`, agent sẽ không tìm được helper qua bootstrap search và startup thất bại sớm. Nếu bỏ cả phép kiểm, rồi chạy app không có helper trên runtime classpath, một lỗi thường gặp là `NoClassDefFoundError` khi giải quyết callsite.

Điều rút ra: **compile-time classpath không phải runtime loader visibility**.

### B. Vô tình đóng gói helper vào cả agent.jar và bridge.jar

Nếu một build plugin sao chép `ProbeBridge.class` sang agent.jar, JVM có thể gặp class trùng trong nhiều đường search. Parent delegation và thời điểm define quyết định instance runtime; một số class có thể đã được nạp từ nơi khác trước khi bootstrap append. Đừng dựa vào việc “trong lab vẫn chạy” để coi đây là packaging đúng.

Giải pháp: tạo **hai artifacts với nội dung không trùng** và test `jar --list`. Version mismatch giữa helper JAR và class đã instrument còn có thể gây `NoSuchMethodError`.

### C. Helper import exporter chỉ có ở agent

Nếu `ProbeBridge.hit()` gọi `RichReporter.ready()` hoặc SDK không bootstrap-visible, helper không còn đáp ứng ràng buộc. Trong một JVM, lỗi có thể chỉ xuất hiện khi method đó lần đầu link hoặc chạy. Không cố sửa bằng cách đưa cả dependency tree vào bootstrap; hãy đảo dependency và để exporter ở rich agent side.

### D. Custom class loader chỉ delegate tới bootstrap

Một plugin loader có thể thấy bridge bootstrap mà không thấy một class chỉ đặt trên system loader. Thử trên runtime/container thực, vì một số framework dùng loader child-first hoặc module layers. Không suy luận từ việc `Class.forName(name)` theo system loader chạy thành công.

### E. Append sau khi symbolic reference đã resolve thất bại

Javadoc cảnh báo những resolution failures trước đó có thể được giữ theo JVM specification. Không dùng append muộn như cơ chế sửa lỗi tự động sau `NoClassDefFoundError`. Ưu tiên startup `premain`, hoặc có trình tự attach/nạp class đã được thiết kế và thử riêng.

## 10. Nếu helper cần gửi sự kiện sang phần agent nặng

Một giải pháp là định nghĩa interface trong bridge JAR, rồi để implementation ở rich agent:

```java
// MÃ MINH HỌA: bridge-src/demo/bootstrap/BridgeSink.java
package demo.bootstrap;

public interface BridgeSink {
    void record(int code, long elapsedNanos);
}
```

```java
// MÃ MINH HỌA: agent runtime, không phải chương trình độc lập.
package demo.agent.runtime;

import demo.bootstrap.BridgeSink;

public final class QueueSink implements BridgeSink {
    @Override
    public void record(int code, long elapsedNanos) {
        // Ở đây chỉ nonblocking offer vào bounded queue.
        // Export HTTP và serialization trên worker riêng.
    }
}
```

Đây là **thiết kế mẫu**, chưa có code cài sink, queue, shutdown hay delivery guarantee. Nó thể hiện hướng đúng: **bootstrap định nghĩa interface**, agent loader định nghĩa implementation. Không để bootstrap helper import `QueueSink`. Muốn cài implementation qua một `static volatile BridgeSink sink`, phải xử lý đúng JMM, fallback khi `sink==null`, guard recursion và classloader retention. Một callback trực tiếp vẫn chạy **trong business thread**; nếu implementation thực hiện HTTP đồng bộ, việc tách JAR không làm giảm latency.

Nếu chỉ cần thống kê tổng số, cách cập nhật `LongAdder` trong lab **ít phức tạp hơn** callback interface. Nếu cần từng event, một bounded queue với `offer`, drop counter và worker/exporter tách biệt có thể phù hợp. **Queue trong RAM không phải audit log bền vững**: `offer` thành công không bảo đảm backend đã nhận, crash có thể làm mất event, retry có thể tạo duplicate.

### Helper là cầu nối, không phải kho state vô hạn

Không lưu `ClassLoader`, `Class<?>`, `Thread`, request object hoặc object của plugin vào static map trong helper mà không có cleanup. Vì bootstrap helper sống lâu, nó có thể giữ class loader của webapp/plugin đã redeploy, gây memory leak. Nếu cần per-loader config, dùng weak references/eviction/lifecycle đã được test, thay vì static map tăng vô hạn.

## 11. Quan hệ với JPMS khi target là named module

Từ Java 9, **module graph** và **class-loader graph** là hai điều kiện riêng. `ProbeBridge` bootstrap-defined thuộc **unnamed module của bootstrap loader**. Trong JDK 17, `java.lang.instrument` nói JVM bố trí read edges hỗ trợ từ **module của class đã được transform** tới unnamed modules của bootstrap loader và loader chứa main agent class, để hỗ trợ instrumentation.

Điều này không có nghĩa mọi named module bất kỳ luôn có quyền truy cập mọi class của bootstrap helper. Cần kiểm tra:

- Class cần gọi đã thực sự được transformer xử lý?
- Module của target có đọc được module chứa helper theo cấu hình thực?
- Helper type và method là `public`?
- Có cần deep reflection vào non-public member của một package khác không? Nếu có, đó là chuyện **opens**, không chỉ class-loader visibility.
- Một `redefineModule` bổ sung read/opens/exports (nếu thực sự cần) phải xét đúng chiều, đúng package và phạm vi quyền tối thiểu.

Lab cố ý dùng **classpath unnamed module** cho app để kiểm tra riêng bài toán loader. Với named module, hãy viết integration test trên cùng module graph và class loader như production.

## 12. Versioning và vòng đời bootstrap helper

Một method sau instrumentation có thể chứa callsite cố định:

```text
invokestatic demo/bootstrap/ProbeBridge.hit:()V
```

Nếu helper phiên bản mới xóa `hit()` và chỉ giữ `record(int)`, class đã được instrument có thể gặp `NoSuchMethodError` khi runtime resolve callsite. Vì bootstrap JAR được append vào search, nó không phải một **hot-swap mechanism** để thay class đã định nghĩa. Nhiều JAR cùng binary name không tạo ra phép thay class tự động.

Cách thiết kế:

1. Giữ ABI của bridge ổn định suốt thời gian class đã instrument có thể tồn tại.
2. Ưu tiên thêm API mới tương thích ngược thay vì đổi descriptor đang được dùng.
3. Nếu cần phá vỡ tương thích, version hóa package/helper và kiểm soát migration.
4. Không đóng gói hai bản helper cùng binary name rồi chờ JVM chọn bản mới.
5. Nếu một class được instrument bởi agent version A, test nó với bridge version tương ứng khi agent B được deploy.
6. Không mặc định `removeTransformer` hoặc xóa JAR trên disk sẽ khôi phục class đã instrument.
7. Thiết kế cách disable probe và restart JVM khi cần dọn loader search hoặc cập nhật bootstrap definitions.

### Cẩn thận với static initializer

Một helper bootstrap nên có khởi tạo rất nhỏ, chẳng hạn tạo `LongAdder`, không load SDK, không gọi exporter, không đọc cấu hình lớn hoặc tạo worker. Một `ExceptionInInitializerError` từ helper khi class ứng dụng đang chạy có thể gây lỗi hàng loạt; về sau việc tham chiếu class có initialization failure có thể báo `NoClassDefFoundError`.

## 13. Bảng chẩn đoán lỗi

| Triệu chứng | Nguyên nhân có thể | Kiểm tra |
| --- | --- | --- |
| `ClassNotFoundException` ở `Class.forName(..., null)` | Bootstrap không thấy bridge JAR | Đúng agentArgs, JAR entry, append trước lookup |
| `NoClassDefFoundError` ở callsite | Helper chưa có tại runtime hoặc symbolic reference resolve thất bại | Loader của target, tên package, thời điểm append |
| `NoClassDefFoundError` cho exporter của agent | Bridge liên kết ngược dependency chỉ có ở system loader | `jdeps bridge.jar`, bỏ import/field/call nặng |
| `IllegalAccessError` | Package/module/loader access không phù hợp | In `Class.getModule` và `getClassLoader` |
| `NoSuchMethodError` | Callsite method descriptor khác bridge version hiện tại | `javap -p`, kiểm tra ABI |
| `ClassCastException` giữa cùng tên type | Hai loader đã định nghĩa class khác nhau | So `Class<?>` identity và defining loader |
| `ExceptionInInitializerError` | `<clinit>` của bridge phụ thuộc config/I/O/lỗi khác | Giữ initialization tối thiểu |
| `StackOverflowError` khi agent bật | Instrument helper/exporter, reentrant recursion | Exclude package agent/bridge, guard |
| Đếm metric không nhất quán | Nhiều helper identities hoặc nhiều callsites | Check bootstrap loader và số lần probe |
| OutOfMemoryError sau redeploy | Bridge static field giữ object/class loader của plugin cũ | Heap dump và cleanup/weak reference |
| App chạy local nhưng lỗi trong server | Custom loader/module khác classpath lab | Tái hiện đúng loader tree, JPMS, parent delegation |
| Agent startup abort | `premain` ném exception do path/JAR sai | Kiểm tra manifest, path và quyền file |

**Phân biệt bốn bước:** (1) loader **tìm thấy class**, (2) JVM **cho phép truy cập/link** theo module/visibility, (3) static initialization **thành công**, (4) code helper **hoạt động đúng** và không làm chậm ứng dụng. Một bước đúng không chứng minh những bước còn lại đúng.

## 14. Checklist triển khai

1. Xác định class loader/module thực sự của target đã instrument.
2. Chọn nơi đặt helper phù hợp, không mặc định bootstrap trong mọi dự án.
3. Có **bridge JAR riêng** chỉ gồm class/resource cần thiết.
4. Đặt package riêng, tránh va chạm third-party/JDK/application classes.
5. Dùng `jdeps`, `jar --list`, code review để xác nhận dependency graph.
6. Giữ API helper public, nhỏ, descriptor ổn định, dễ versioning.
7. Loại mọi static reference từ helper tới agent runtime hoặc thư viện ngoài.
8. Append bootstrap search **sớm**, trước khi target tham chiếu helper.
9. Xác nhận `Class.forName(name,false,null)` và loader identity khi chọn bootstrap.
10. Kiểm tra JPMS read/opens nếu target thuộc named module.
11. Filter transformer để không xử lý bridge/agent/exporter.
12. Trả bytes mới hợp lệ khi thật sự transform, `return null` nếu không đổi.
13. Không block network/disk từ helper trong hot path.
14. Kiểm soát bounded queue/drop nếu cần sự kiện chi tiết.
15. Không giữ class loader/plugin objects trong helper static state vô hạn.
16. Có startup-failure policy nếu JAR helper sai/thiếu, không âm thầm chạy thiếu chức năng.
17. Test cả classpath và custom-loader/module-path tình huống thực.
18. Thử helper ABI tương thích với bytecode instrumented cũ.
19. Đo latency, CPU, allocation, GC và số lượng probe có/không agent.
20. Có phương án shutdown, disable probe, restart khi cập nhật bootstrap JAR.

## 15. Bài tập tự kiểm tra

**Câu 1.** Agent class có thể import `RichExporter` nên mọi class ứng dụng đã instrument cũng import được?  
**Đáp:** Không. Target class loader có thể không thấy system/agent loader hoặc dependency graph của nó.

**Câu 2.** Vì sao `bridge.jar` nên chỉ có `ProbeBridge.class` và ít bootstrap dependencies?  
**Đáp:** Tránh bootstrap định nghĩa nhầm các thư viện không dành cho nó, giảm lỗi linkage và xung đột package/version.

**Câu 3.** `ProbeBridge.class.getClassLoader()==null` nghĩa là gì?  
**Đáp:** Class được bootstrap loader định nghĩa. Không có nghĩa class thuộc module `java.base`.

**Câu 4.** Compile app với `-cp bridge.jar`, sau đó runtime chỉ `-cp out/app`, vẫn chạy được khi nào?  
**Đáp:** Khi agent append đúng bridge JAR vào bootstrap search trước lúc app resolve helper, như lab.

**Câu 5.** Bootstrap helper có thể trực tiếp gọi class chỉ được system loader định nghĩa không?  
**Đáp:** Không được giả định. Quy tắc supporting classes bootstrap của JDK yêu cầu chúng chỉ liên kết bootstrap-defined classes.

**Câu 6.** Nếu bỏ append, lỗi ở `Class.forName(..., false, null)` là gì?  
**Đáp:** Khi bootstrap search không thấy helper, `ClassNotFoundException`; callsite trong app có thể gặp `NoClassDefFoundError`.

**Câu 7.** Hai class cùng tên ở hai defining loaders có share static counter?  
**Đáp:** Không nhất thiết: chúng có thể là hai class runtime độc lập với static state riêng.

**Câu 8.** `appendToSystemClassLoaderSearch` có làm helper thấy được từ mọi plugin loader?  
**Đáp:** Không. Plugin loader có thể không delegate tới system loader.

**Câu 9.** Dùng `Boot-Class-Path` manifest và `appendToBootstrapClassLoaderSearch` có phải một cú pháp không?  
**Đáp:** Không. Chúng là hai cơ chế cung cấp đường search bootstrap, có packaging/timing khác nhau.

**Câu 10.** Vì sao callsite `hit:()V` có thể lỗi sau khi upgrade helper?  
**Đáp:** Nếu method bị xóa hoặc đổi descriptor, symbolic reference cũ có thể gây `NoSuchMethodError`.

**Câu 11.** Vì sao app của lab gọi helper trực tiếp thay vì transformer chèn instruction?  
**Đáp:** Để kiểm chứng tách JAR, bootstrap loader và runtime linkage mà không cần thư viện tạo bytecode. Transformer trong lab trả `null` và không chèn mã.

**Câu 12.** Có nên giữ `ClassLoader` của webapp trong static bridge map để tiện tra cứu không?  
**Đáp:** Không nếu không có lifecycle/eviction; nó có thể giữ loader cũ sống mãi sau redeploy.

**Câu 13.** Với named module, chỉ bootstrap-load helper có chắc mọi access/opens đều hợp lệ?  
**Đáp:** Không. Cần kiểm tra module graph và visibility riêng; JDK có trợ giúp read edges cho module của class đã transform, không phải mọi module bất kỳ.

**Câu 14.** Gọi `removeTransformer` có xóa các lời gọi helper đã chèn vào class không?  
**Đáp:** Không. Nó không tự rollback class bytes đã định nghĩa.

**Câu 15.** Vì sao helper bootstrap không nên dùng `java.util.logging.Logger` theo mặc định?  
**Đáp:** Không có bảo đảm mọi platform class được bootstrap định nghĩa; giữ helper chỉ phụ thuộc những class bootstrap-visible, ưu tiên `java.base`.

## 16. Tài liệu tham khảo chính thức

- [JDK 17 — `Instrumentation.appendToBootstrapClassLoaderSearch`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): bootstrap search, JAR contents warning, package collision, negative resolution và system loader search.
- [JDK 17 — package `java.lang.instrument`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html): `premain`, load agent JAR, bootstrap supporting classes, `Boot-Class-Path`, JPMS read edges.
- [JDK 17 — `ClassFileTransformer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): lifecycle callback và yêu cầu trả bytes/`null`.
- [JDK 17 — `ClassLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): bootstrap/parent delegation, class visibility.
- [JDK 17 — `LongAdder`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html): counter và giới hạn snapshot khi concurrent.
- [JVMS 17 — Loading, Linking, and Initializing](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html): class identity, loader constraints và symbolic references.

**Ghi nhớ:** Helper là **API tối thiểu** cho bytecode đã instrument; rich agent mới mang bytecode SDK, exporter và các dependency phức tạp. Khi dùng bootstrap search, chỉ append **helper JAR nhỏ**, trước thời điểm target cần resolve nó, và kiểm tra loader thực tế. Tách dependency đúng hướng giúp tránh lỗi linkage, giảm overhead và giữ khả năng deploy/diagnose dài hạn.
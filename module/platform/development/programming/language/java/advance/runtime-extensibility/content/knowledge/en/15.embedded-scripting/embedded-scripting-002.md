# Tìm ScriptEngineFactory qua ScriptEngineManager và class loader phù hợp

## 1. Vì sao hệ thống nhúng script cần chọn class loader đúng?

Java Scripting API (JSR 223, package `javax.script`) cho phép một host tìm và sử dụng các script engine được cung cấp dưới dạng plugin. Host thường dùng `ScriptEngineManager` để duyệt `ScriptEngineFactory`, sau đó tạo `ScriptEngine` và đánh giá kịch bản. Mấu chốt là **engine implementation phải nhìn thấy được từ class loader mà manager dùng để khám phá provider**.

Trong hệ thống plugin có loader riêng, engine JAR có thể tồn tại trên đĩa nhưng vẫn không xuất hiện nếu manager được tạo với loader khác. Điều này không nhất thiết là lỗi trong engine: danh sách factory được phát hiện phụ thuộc runtime class path, module graph/layer, metadata SPI và loader.

**Lưu ý phiên bản:** Java 17+ cung cấp API `javax.script` trong module `java.scripting`, nhưng không bảo đảm có engine ngôn ngữ nào mặc định. Nashorn từng có trong các JDK cũ đã bị loại khỏi JDK kể từ Java 15. Ví dụ gọi `getEngineByName("JavaScript")` trên JDK 17 thuần thường trả `null`, trừ khi đã cài một JSR 223 engine tương thích.

## 2. Các đối tượng chính

| API | Công dụng |
|---|---|
| `ScriptEngineManager` | Khám phá, đăng ký và tra cứu engine factory; duy trì global bindings dùng cho engine được tạo qua manager |
| `ScriptEngineFactory` | Mô tả ngôn ngữ/engine và tạo instance qua `getScriptEngine()` |
| `ScriptEngine` | Đánh giá script, quản lý bindings/context theo hợp đồng engine |
| `ScriptEngineManager.getEngineFactories()` | Trả danh sách factory đã phát hiện và đăng ký |
| `getEngineByName(name)` | Tìm engine qua tên/alias được factory công bố |
| `getEngineByExtension(extension)` | Tìm engine qua phần mở rộng được factory công bố |
| `getEngineByMimeType(mimeType)` | Tìm engine qua MIME type được factory công bố |
| `registerEngineName/Extension/MimeType` | Đăng ký thủ công ánh xạ từ định danh đến factory |

Factory có metadata để host kiểm tra trước khi tạo engine: `getEngineName()`, `getEngineVersion()`, `getLanguageName()`, `getLanguageVersion()`, `getNames()`, `getExtensions()`, `getMimeTypes()` và `getParameter(...)`. Các metadata này hữu ích để chọn engine theo khả năng hoặc chính sách. Cần nhớ ngay cả việc tìm factory có thể tải class và tạo factory instance; bước khám phá **không phải hoàn toàn không có chi phí/hiệu ứng phụ**.

## 3. Manager mặc định và manager có loader tường minh

```java
ScriptEngineManager defaultManager = new ScriptEngineManager();
ScriptEngineManager pluginManager = new ScriptEngineManager(pluginLoader);
```

Đây là **đoạn mã minh họa** cần có import `javax.script.ScriptEngineManager` và biến `pluginLoader` kiểu `ClassLoader`.

Constructor không tham số thường sử dụng thread context class loader (TCCL) để khám phá provider. Nếu ứng dụng server thay đổi TCCL theo request/thread, việc dùng constructor mặc định có thể cho kết quả khác nhau giữa các ngữ cảnh.

Constructor nhận `ClassLoader` giúp host **chỉ rõ loader để thực hiện khám phá**. Trong mô hình module path/layer, cách service discovery còn liên quan module graph và những module đã được resolve; truyền loader không biến các JAR ngoài module graph thành provider một cách tự động.

Không nên thay TCCL toàn cục rồi giả định mọi engine sẽ được tìm thấy. Khi cần dùng TCCL cho một thư viện legacy, phải lưu giá trị cũ, đặt loader tạm thời và khôi phục trong `finally`; nhưng nếu API cho phép truyền loader trực tiếp, dùng constructor tường minh dễ kiểm soát hơn.

## 4. Điều kiện để JAR engine được phát hiện

Với class path hoặc custom `URLClassLoader`, nhà cung cấp engine thường triển khai `javax.script.ScriptEngineFactory` và đưa file SPI vào JAR:

```text
META-INF/services/javax.script.ScriptEngineFactory
```

Nội dung file là tên đầy đủ của factory implementation, ví dụ:

```text
demo.engine.EchoEngineFactory
```

Service descriptor chỉ liệt kê provider class; không tự khai báo alias ngôn ngữ. Alias như `echo` do `ScriptEngineFactory.getNames()` cung cấp. Factory cần công khai và có cách khởi tạo hợp lệ theo cơ chế `ServiceLoader` của môi trường tương ứng.

Nếu engine là explicit named module, module descriptor thường khai báo:

```java
module demo.engine {
    requires java.scripting;
    provides javax.script.ScriptEngineFactory
        with demo.engine.EchoEngineFactory;
}
```

Đây là **module descriptor minh họa**; source implementation phải tồn tại. Named module dùng `provides` và resolution/layer phù hợp; chỉ có descriptor `META-INF/services` chưa đủ cho một explicit named module được khám phá theo quy tắc module service binding.

## 5. Thực hành hoàn chỉnh: một JSR 223 engine tối giản

Ví dụ tạo engine `echo`, trả lại nguyên văn script được đánh giá. Engine dùng cho kiểm chứng discovery, **không phải JavaScript engine**; không thực thi ngôn ngữ tùy ý và không nên sử dụng như bộ thông dịch production.

Cấu trúc source:

```text
script-demo/
├── host/
│   └── Host.java
└── engine/
    ├── demo/engine/EchoEngine.java
    ├── demo/engine/EchoEngineFactory.java
    └── META-INF/services/javax.script.ScriptEngineFactory
```

### 5.1. Engine implementation

`engine/demo/engine/EchoEngine.java`:

```java
package demo.engine;

import java.io.IOException;
import java.io.Reader;
import java.util.Objects;
import javax.script.AbstractScriptEngine;
import javax.script.Bindings;
import javax.script.ScriptContext;
import javax.script.ScriptEngineFactory;
import javax.script.ScriptException;
import javax.script.SimpleBindings;

public final class EchoEngine extends AbstractScriptEngine {
    private final ScriptEngineFactory factory;

    public EchoEngine(ScriptEngineFactory factory) {
        this.factory = Objects.requireNonNull(factory);
    }

    @Override
    public Object eval(String script, ScriptContext context) {
        return script;
    }

    @Override
    public Object eval(Reader reader, ScriptContext context) throws ScriptException {
        try {
            StringBuilder output = new StringBuilder();
            char[] buffer = new char[1024];
            int n;
            while ((n = reader.read(buffer)) != -1) {
                output.append(buffer, 0, n);
            }
            return output.toString();
        } catch (IOException ex) {
            throw new ScriptException(ex);
        }
    }

    @Override
    public Bindings createBindings() {
        return new SimpleBindings();
    }

    @Override
    public ScriptEngineFactory getFactory() {
        return factory;
    }
}
```

Chú ý: `AbstractScriptEngine` cung cấp các overload còn lại của `eval` sử dụng `ScriptContext`/`Bindings`. Để làm ví dụ tối giản, engine này không diễn giải biến hay lệnh, nên `eval("hello")` đơn giản trả chuỗi `hello`.

### 5.2. Factory và metadata

`engine/demo/engine/EchoEngineFactory.java`:

```java
package demo.engine;

import java.util.List;
import javax.script.ScriptEngine;
import javax.script.ScriptEngineFactory;

public final class EchoEngineFactory implements ScriptEngineFactory {
    @Override public String getEngineName() { return "Echo Engine"; }
    @Override public String getEngineVersion() { return "1.0"; }
    @Override public List<String> getExtensions() { return List.of("echo"); }
    @Override public List<String> getMimeTypes() { return List.of("text/x-echo"); }
    @Override public List<String> getNames() { return List.of("echo", "EchoEngine"); }
    @Override public String getLanguageName() { return "Echo"; }
    @Override public String getLanguageVersion() { return "1.0"; }

    @Override
    public Object getParameter(String key) {
        return switch (key) {
            case ScriptEngine.NAME -> "echo";
            case ScriptEngine.ENGINE -> getEngineName();
            case ScriptEngine.ENGINE_VERSION -> getEngineVersion();
            case ScriptEngine.LANGUAGE -> getLanguageName();
            case ScriptEngine.LANGUAGE_VERSION -> getLanguageVersion();
            case "THREADING" -> null;
            default -> null;
        };
    }

    @Override
    public String getMethodCallSyntax(String obj, String method, String... args) {
        return obj + "." + method + "(" + String.join(", ", args) + ")";
    }

    @Override
    public String getOutputStatement(String toDisplay) {
        return toDisplay;
    }

    @Override
    public String getProgram(String... statements) {
        return String.join("\n", statements);
    }

    @Override
    public ScriptEngine getScriptEngine() {
        return new EchoEngine(this);
    }
}
```

Factory có các trường metadata bắt buộc của `ScriptEngineFactory`. Giá trị `THREADING = null` không cam kết engine an toàn cho truy cập đa luồng. Không nên suy diễn từ nó rằng host được dùng chung một `ScriptEngine` trên nhiều thread.

### 5.3. Descriptor SPI

Tạo file văn bản `engine/META-INF/services/javax.script.ScriptEngineFactory` với đúng một dòng:

```text
demo.engine.EchoEngineFactory
```

Đảm bảo file này nằm ở root tài nguyên của JAR, không phải dưới package `demo.engine`. Dấu xuống dòng cuối file được khuyến nghị để thuận tiện khi đóng gói và đọc.

### 5.4. Host tạo loader riêng và tra cứu factory

`host/Host.java`:

```java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import javax.script.ScriptEngine;
import javax.script.ScriptEngineFactory;
import javax.script.ScriptEngineManager;

public final class Host {
    public static void main(String[] args) throws Exception {
        URL jar = Path.of("build/echo-engine.jar").toUri().toURL();
        try (URLClassLoader pluginLoader = new URLClassLoader(
                new URL[] {jar}, ClassLoader.getPlatformClassLoader())) {
            ScriptEngineManager manager = new ScriptEngineManager(pluginLoader);
            ScriptEngineFactory chosen = manager.getEngineFactories().stream()
                    .filter(factory -> factory.getNames().contains("echo"))
                    .findFirst()
                    .orElseThrow(() -> new IllegalStateException("Missing echo engine"));

            System.out.println("factory: " + chosen.getEngineName());
            System.out.println("language: " + chosen.getLanguageName());
            System.out.println("aliases: " + chosen.getNames());

            ScriptEngine engine = manager.getEngineByName("echo");
            if (engine == null) {
                throw new IllegalStateException("Factory exists but engine not found");
            }
            System.out.println("result: " + engine.eval("hello plugin"));
        }
    }
}
```

Ở ví dụ này, `ClassLoader.getPlatformClassLoader()` là parent của plugin loader. `javax.script` thuộc module nền tảng `java.scripting`, nên loader vẫn có thể nhìn thấy SPI interface. Không đặt `echo-engine.jar` trên class path của host; để JAR được định nghĩa từ `pluginLoader` nhằm quan sát rõ sự khác biệt.

**Lưu ý về `URLClassLoader.close()`:** Đóng loader giải phóng tài nguyên do loader quản lý (chẳng hạn handle JAR). Nó không ép các class đã nạp bị unload và cũng không tự dừng thread hoặc đóng tài nguyên của engine. Trong hệ thống thực, cần đóng các tài nguyên của engine theo API/provider contract trước khi đóng loader.

### 5.5. Biên dịch, đóng gói và chạy

Chạy các lệnh sau từ thư mục `script-demo/` bằng POSIX shell với JDK 17+:

```bash
mkdir -p build/engine-classes build/host-classes
javac -encoding UTF-8 -d build/engine-classes \
  engine/demo/engine/EchoEngine.java \
  engine/demo/engine/EchoEngineFactory.java
jar --create --file build/echo-engine.jar \
  -C build/engine-classes . \
  -C engine META-INF/services
javac -encoding UTF-8 -d build/host-classes host/Host.java
java -cp build/host-classes Host
```

Output dự kiến đúng khi chạy trên JDK 17 với một JAR engine demo:

```text
factory: Echo Engine
language: Echo
aliases: [echo, EchoEngine]
result: hello plugin
```

Đây là ví dụ có thể chạy độc lập trên JDK 17+ và không đòi hỏi engine JavaScript bên thứ ba. Không cần thêm `--module-path` vì cả host và engine demo dùng cơ chế class path/custom loader. Lệnh `jar` đưa cả class và descriptor SPI vào cùng một artifact.

## 6. Chẩn đoán manager không thấy factory

Trước tiên kiểm tra artifact:

```bash
jar --list --file build/echo-engine.jar
```

Cần có cả `demo/engine/EchoEngineFactory.class`, `demo/engine/EchoEngine.class` và `META-INF/services/javax.script.ScriptEngineFactory`. Kiểm tra chính xác tên file descriptor và binary name trong đó; `ServiceLoader` không tự tìm provider class nếu descriptor thiếu.

Nếu vẫn không thấy, chẩn đoán bằng:

```java
System.out.println("TCCL: " + Thread.currentThread().getContextClassLoader());
System.out.println("plugin loader: " + pluginLoader);
System.out.println("factory count: " + manager.getEngineFactories().size());
```

Đây là đoạn minh họa cần đặt bên trong `Host.main` sau khi tạo manager. Cần xác nhận `new ScriptEngineManager(pluginLoader)` thật sự sử dụng loader có thể truy cập JAR; constructor mặc định có thể dùng TCCL khác.

Có thể gặp các trường hợp:

| Hiện tượng | Nguyên nhân phổ biến | Hướng xử lý |
|---|---|---|
| `getEngineFactories()` rỗng | Không có JSR 223 provider được phát hiện | Kiểm tra JAR, SPI descriptor và class loader |
| `getEngineByName("JavaScript") == null` | JDK 17 không có sẵn JavaScript engine | Cài engine JSR 223 tương thích hoặc chọn ngôn ngữ khác |
| Factory thấy nhưng `getScriptEngine()` thất bại | Dependency của engine thiếu, constructor lỗi hoặc cấu hình sai | Kiểm tra exception và runtime dependencies |
| `ServiceConfigurationError` | Provider class không hợp lệ/không load được | Kiểm tra descriptor, visibility, constructor và class loader |
| `ClassCastException` hoặc provider không assignable | SPI/API bị nạp trùng qua loader khác nhau | Chia sẻ `javax.script` và contract chung qua parent |
| Engine đã có JAR nhưng chưa hiện trong manager cũ | Manager đã snapshot danh sách factory lúc khởi tạo hoặc module chưa resolve | Tạo manager mới sau khi thiết lập loader/module graph |

Không nên thay cả class path toàn ứng dụng để sửa một plugin. Hãy xác định loader nào đang quản lý engine đó và dùng manager tương ứng.

## 7. Chọn factory theo metadata trước khi tạo engine

Khi hệ thống có nhiều engine cùng alias, `getEngineByName` không phải luôn đủ để thực thi chính sách nghiệp vụ. Host có thể duyệt `getEngineFactories()` và chọn theo tên ngôn ngữ, phiên bản, alias, MIME type hoặc danh sách cho phép.

Ví dụ đoạn minh họa:

```java
ScriptEngineFactory factory = manager.getEngineFactories().stream()
    .filter(f -> f.getLanguageName().equalsIgnoreCase("Echo"))
    .filter(f -> f.getNames().contains("echo"))
    .findFirst()
    .orElseThrow();
ScriptEngine engine = factory.getScriptEngine();
```

Đoạn này chỉ chạy trong ngữ cảnh có `manager` và các import tương ứng. Nó cho phép lựa chọn bằng metadata trước khi gọi `getScriptEngine()`, tránh khởi tạo mọi engine không cần thiết. Tuy vậy việc khám phá factory vẫn có thể khởi tạo factory class, nên code constructor của factory nên nhẹ, không thực hiện network I/O, cấp phát thread hoặc chạy script.

Muốn chính sách ổn định, có thể thêm tie-breaker và kiểm soát version; không nên coi thứ tự factory được ServiceLoader phát hiện là thứ tự ưu tiên nghiệp vụ. Metadata do plugin công bố phải được kiểm tra tính hợp lệ và độ tin cậy nếu plugin do bên thứ ba cung cấp.

## 8. Quan hệ giữa class loader, JPMS và ModuleLayer

Trong ứng dụng JPMS, `ScriptEngineFactory` thuộc module `java.scripting`. Named engine module dùng `provides javax.script.ScriptEngineFactory with ...` và được resolve trong module graph thích hợp. `ScriptEngineManager` có thể làm việc với các provider nhìn thấy qua cơ chế dịch vụ/module, nhưng loader truyền vào manager không phải một lời gọi để resolve module mới trong layer chưa có.

Nếu host tạo một `ModuleLayer` plugin riêng sau khi khởi động, cần thiết kế discovery rõ ràng. `ServiceLoader.load(layer, ScriptEngineFactory.class)` là API cho phép khám phá provider trong layer; host có thể dùng factory nhận được và gọi `getScriptEngine()` trực tiếp, thay vì mặc định manager sẽ tự quét mọi layer con.

Ví dụ minh họa **không độc lập**, đòi hỏi `pluginLayer` đã được tạo và `java.scripting` là module dùng chung:

```java
var factories = java.util.ServiceLoader.load(
        pluginLayer, javax.script.ScriptEngineFactory.class);
for (var factory : factories) {
    System.out.println(factory.getEngineName());
}
```

Không tự suy ra việc đóng module layer sẽ unload class; Java không có `ModuleLayer.close()`. Quản lý loader, engine và tài nguyên plugin phải được thiết kế rõ ràng. Việc dùng custom class loader đồng thời với JPMS cần lưu ý split package, module readability, `exports`/`opens` và type identity.

## 9. An toàn khi chạy script nhúng

Script engine là mã chạy trong process Java. `ScriptEngine.eval(...)` có thể thực thi tác vụ mà engine cho phép, bao gồm truy cập Java objects, I/O hoặc các khả năng mạnh khác tùy ngôn ngữ/engine. Việc đặt engine trong JAR riêng hoặc class loader riêng **không tạo sandbox bảo mật**.

Với script không tin cậy, host nên kiểm soát ngôn ngữ và engine được chấp nhận, giới hạn execution time, memory và I/O bằng cơ chế process/OS phù hợp; hạn chế đối tượng Java đưa vào bindings và xác định cách dừng engine khi timeout. Không giả định `ScriptEngine` thread-safe: xem đặc tả `THREADING`, tài liệu provider và thực hiện kiểm thử trước khi chia sẻ instance giữa nhiều request.

**Kết luận:** `ScriptEngineManager` khám phá các `ScriptEngineFactory` qua SPI trong phạm vi class loader/module graph có thể nhìn thấy. Với hệ thống plugin, hãy chỉ rõ loader khi tạo manager, kiểm tra descriptor/module registration, chọn factory bằng metadata và chỉ khởi tạo engine được chọn. Đối với các module layer được tạo động, sử dụng `ServiceLoader.load(layer, ScriptEngineFactory.class)` để kiểm soát phạm vi khám phá.

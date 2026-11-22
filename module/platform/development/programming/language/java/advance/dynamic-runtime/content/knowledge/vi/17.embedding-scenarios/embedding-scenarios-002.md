# 17.2. Khám phá engine qua `ScriptEngineManager` và xử lý kết quả không tìm thấy

## 1. Vấn đề cốt lõi: có JSR-223 API không có nghĩa có script engine

Trong Java, **JSR-223 / Scripting for the Java Platform** cung cấp API chuẩn để nhúng các ngôn ngữ kịch bản vào ứng dụng. API nằm trong module **`java.scripting`**, package **`javax.script`**. Bạn có thể import `ScriptEngineManager`, `ScriptEngine`, `ScriptEngineFactory` và `ScriptException` bằng JDK 17 mà **không cần thêm thư viện**. Tuy nhiên, thư viện JDK cung cấp **API discovery**, không cam kết có sẵn implementation cho JavaScript, Python, Groovy hay bất kỳ ngôn ngữ nào.

Vấn đề thực tế:

```java
ScriptEngine engine = new ScriptEngineManager()
        .getEngineByName("javascript");
engine.eval("1 + 2");
```

Đây là **đoạn phản ví dụ**, không phải chương trình độc lập. Trên môi trường không có JavaScript `ScriptEngineFactory`, `getEngineByName("javascript")` trả về **`null`**; gọi `engine.eval(...)` tiếp theo làm ứng dụng ném **`NullPointerException`** trước khi chạy kịch bản nào. Lỗi này không có nghĩa cú pháp JavaScript sai, mà là **bước khám phá engine thất bại**.

Từ JDK 15, **Nashorn JavaScript engine và công cụ `jjs` đã bị gỡ bỏ** (JEP 372). Java 17 vẫn có **`javax.script`** và **`ScriptEngineManager`**, nhưng một JDK 17 sạch thường **không có JavaScript engine được cài sẵn**. Nếu dự án thêm một provider tương thích (ví dụ một implementation JSR-223 từ bên ngoài), máy đó vẫn có thể trả engine cho một tên JavaScript được provider công bố. Vì vậy:

> **Đừng đồng nhất “API hiện diện” với “engine hiện diện”; luôn kiểm tra factory và kết quả lookup trong đúng môi trường triển khai.**

Bài này đưa ra quy trình khám phá chính xác, cách xử lý `null` an toàn, chiến lược chẩn đoán class loader và Service Provider Interface (SPI), rồi xây một **engine thử nghiệm hoàn toàn self-contained** để chứng minh lookup theo tên/extension/MIME trên Java 17+.

## 2. Mô hình các đối tượng trong JSR-223

Hãy tách bốn vai trò:

| Thành phần | Vai trò | Ví dụ sử dụng |
| --- | --- | --- |
| **`ScriptEngineManager`** | Khám phá và tạo `ScriptEngine` thông qua `ScriptEngineFactory`; giữ global bindings dùng chung cho các engines do manager tạo | `new ScriptEngineManager()` |
| **`ScriptEngineFactory`** | Cung cấp metadata về implementation, tên ngôn ngữ, aliases, extensions, MIME types; tạo engine instance | `factory.getScriptEngine()` |
| **`ScriptEngine`** | Engine thật thực hiện `eval`, giữ `ScriptContext`/bindings, có thể hỗ trợ thêm interfaces tùy provider | `engine.eval(script)` |
| **`ScriptException`** | Báo lỗi thực thi/biên dịch kịch bản theo API JSR-223 | `catch (ScriptException ex)` |

Luồng điển hình:

```text
Application
    |
    | new ScriptEngineManager()
    v
ScriptEngineManager
    |
    | ServiceLoader<ScriptEngineFactory>
    | (provider classes/resources/modules thấy được)
    v
Factories discovered
    |
    | getEngineByName("mini")
    | getEngineByExtension("mini")
    | getEngineByMimeType("text/x-mini")
    v
Matched ScriptEngineFactory?
    |
    +---- NO ----> null ----> diagnostics / fail-fast / graceful fallback
    |
    +---- YES ---> factory.getScriptEngine()
                           |
                           v
                     ScriptEngine
                           |
                     eval(script)
                           |
                   Object result hoặc ScriptException
```

**`ScriptEngineManager` không tự phân tích hay chạy code của ngôn ngữ nào.** Nó dùng cơ chế **`ServiceLoader`** để khám phá các implementations của `ScriptEngineFactory`; mỗi factory chịu trách nhiệm cung cấp engine.

`getEngineByName`, `getEngineByExtension` và `getEngineByMimeType` đều **trả `ScriptEngine` hoặc `null`** khi không tìm được implementation thích hợp. Các phương thức không yêu cầu JVM có builtin engine cho ngôn ngữ tương ứng.

## 3. Ba phép lookup phải hiểu đúng

### 3.1. Theo tên hoặc alias — `getEngineByName`

```java
ScriptEngine engine = manager.getEngineByName("javascript");
```

Đây là **mã minh họa** với `manager` đã được khởi tạo. API so khớp với các tên được đăng ký bằng `registerEngineName` hoặc do `ScriptEngineFactory.getNames()` của các providers khám phá được công bố.

- `ScriptEngineFactory.getNames()` thường trả nhiều aliases, ví dụ một provider có thể công bố `"js"` và `"javascript"`. **Đó là thông tin do provider quyết định**, không có alias phổ quát phải tồn tại ở mọi máy.
- `getEngineName()` là **tên engine implementation**, không nhất thiết là một alias lookup hợp lệ.
- `getLanguageName()` là **tên ngôn ngữ**, không mặc định là key cho `getEngineByName` trừ khi factory cũng đưa tên đó vào `getNames()`.
- Đừng suy tên alias từ ví dụ trên Internet mà không liệt kê metadata factory thực tế.
- Truyền tên `null` gây `NullPointerException` theo Java SE 17; **không** tương đương “không tìm thấy”.

Về thứ tự, manager tìm **registration thủ công** cho tên đó trước, rồi tìm các factories đã được khám phá qua SPI. Vì thế `registerEngineName("alias", someFactory)` có thể ghi đè association dùng cho lookup alias ấy trong manager hiện tại.

### 3.2. Theo phần mở rộng — `getEngineByExtension`

```java
ScriptEngine engine = manager.getEngineByExtension("mini");
```

Giả định `manager` đã tồn tại. `"mini"` là **extension token** do factory khai báo trong `getExtensions()`, không phải cả đường dẫn, tên tệp hay glob.

Nếu factory công bố `getExtensions() == List.of("mini")`, hãy lookup bằng `"mini"`, không tự suy rằng API sẽ loại dấu `.` từ `".mini"` hoặc trích extension từ `"report.mini"` cho bạn. Nếu ứng dụng nhận một file path, hãy **tách extension rồi xác nhận giá trị** trước khi lookup.

### 3.3. Theo MIME type — `getEngineByMimeType`

```java
ScriptEngine engine = manager.getEngineByMimeType("text/x-mini");
```

Factory phải công bố MIME type tương ứng trong `getMimeTypes()` hoặc ứng dụng đã đăng ký association bằng `registerEngineMimeType`.

MIME type **không được tự suy ra** từ phần mở rộng. Ngược lại, việc có extension `"mini"` không chứng minh `"application/x-mini"` hay `"text/x-mini"` là alias hợp lệ nếu provider không công bố.

### Bảng so sánh

| API | Metadata factory cần xem | Giá trị đầu vào | Không tìm được |
| --- | --- | --- | --- |
| `getEngineByName(name)` | `getNames()` | Alias/short name, ví dụ `"mini"` | `null` |
| `getEngineByExtension(ext)` | `getExtensions()` | Extension token, ví dụ `"mini"` | `null` |
| `getEngineByMimeType(mime)` | `getMimeTypes()` | MIME type, ví dụ `"text/x-mini"` | `null` |
| `getEngineFactories()` | Các providers khám phá được | Không có key | Danh sách rỗng nếu không có factory được tìm thấy |

Đừng gọi `engine.getFactory()` khi `engine == null`; trước tiên phải phân nhánh.

## 4. `getEngineFactories()` là công cụ chẩn đoán đầu tiên

```java
ScriptEngineManager manager = new ScriptEngineManager();

for (ScriptEngineFactory f : manager.getEngineFactories()) {
    System.out.println(f.getEngineName());
    System.out.println(f.getEngineVersion());
    System.out.println(f.getLanguageName());
    System.out.println(f.getNames());
    System.out.println(f.getExtensions());
    System.out.println(f.getMimeTypes());
}
```

Đây là đoạn Java minh họa; cần import `javax.script.ScriptEngineFactory` và `javax.script.ScriptEngineManager`.

Metadata hữu ích:

| API của `ScriptEngineFactory` | Câu hỏi được trả lời |
| --- | --- |
| `getEngineName()` | Đang dùng implementation nào? |
| `getEngineVersion()` | Version của chính engine implementation? |
| `getLanguageName()` | Ngôn ngữ mà engine hỗ trợ là gì? |
| `getLanguageVersion()` | Version ngôn ngữ mà engine hỗ trợ? |
| `getNames()` | Những aliases nào có thể đưa vào `getEngineByName`? |
| `getExtensions()` | Những file extensions nào có thể lookup? |
| `getMimeTypes()` | Những MIME types nào có thể lookup? |
| `getScriptEngine()` | Factory tạo một engine instance thực sự như thế nào? |
| `getParameter(key)` | Metadata hoặc khả năng bổ sung, ví dụ `"THREADING"` khi provider hỗ trợ? |

**Danh sách rỗng** chứng minh **manager hiện tại không khám phá được factory nào**, không chứng minh Java 17 không hỗ trợ JSR-223. Nguyên nhân có thể là không cài provider, provider không visible trong class loader/layer, service file thiếu hoặc sai, hoặc cấu hình triển khai không đúng.

**Danh sách không rỗng nhưng lookup vẫn `null`** thường nghĩa là alias/extension/MIME không khớp với factory nào; cần nhìn `getNames()` thay vì thử các tên tùy ý.

`getEngineFactories()` cung cấp các factories mà manager đã khám phá qua cơ chế của constructor; nó **không phải live registry của mọi alias đăng ký thủ công về sau**. Xem thêm mục 12.

## 5. Quy tắc xử lý kết quả `null` trước khi gọi `eval`

Trên hệ thống thực tế có hai chính sách hợp lệ, tùy vai trò scripting:

### 5.1. Engine là tính năng tùy chọn — degrade gracefully

Nếu script chỉ phục vụ một tính năng tùy chọn, có thể thông báo không hỗ trợ thay vì làm cả ứng dụng sập:

```java
ScriptEngine engine = manager.getEngineByName(requiredName);
if (engine == null) {
    System.err.println("Scripting engine unavailable: " + requiredName);
    return;
}
// Chỉ gọi eval sau khi đã xác minh engine != null.
```

Đây là **đoạn mã trong một method trả `void`** với `manager` và `requiredName` đã khai báo; không phải file độc lập.

Điều quan trọng: “fallback” cần có **ngữ nghĩa nghiệp vụ hợp lệ**. Nếu engine dùng để chạy **quy tắc phân quyền**, việc thiếu engine mà tự coi điều kiện là `true` có thể làm mất an toàn. Trường hợp ấy nên **fail closed** theo chính sách hệ thống.

### 5.2. Engine là phụ thuộc bắt buộc — fail fast với thông báo rõ

```java
ScriptEngine engine = manager.getEngineByName(requiredName);
if (engine == null) {
    throw new IllegalStateException(
            "No JSR-223 ScriptEngine for: " + requiredName);
}
```

Đây là đoạn minh họa cho code cấu hình/startup. Nếu thiếu engine, ứng dụng thất bại sớm **với lý do đã xác định** thay vì gặp `NullPointerException` ở một đoạn `eval` chạy muộn hơn.

Nên đưa vào thông báo lỗi hoặc telemetry: tên yêu cầu, aliases/engine names đang visible, classloader/mode triển khai và dependency cấu hình mong đợi. **Không** đưa script source nhạy cảm, tokens hoặc credentials vào log.

### 5.3. `Optional<ScriptEngine>` không tự sửa việc thiếu provider

Bọc `manager.getEngineByName(...)` bằng `Optional.ofNullable(...)` có thể làm API caller dễ diễn đạt, nhưng vẫn cần chính sách rõ khi `Optional.empty()`: hiển thị disabled status, fail fast, hoặc fallback đã được thiết kế. `Optional` không cài đặt engine và không thay đổi ServiceLoader.

### 5.4. Vì sao không bắt `NullPointerException` quanh `eval`?

Cách sai:

```java
try {
    manager.getEngineByName("javascript").eval(script);
} catch (NullPointerException e) {
    // Tự đoán rằng engine không tồn tại?
}
```

Đây là **phản ví dụ**: `NullPointerException` cũng có thể do chính provider, bindings hoặc script evaluation path; bắt quá rộng làm mất nguyên nhân lỗi. Hãy kiểm tra **`engine == null` trước**, sau đó xử lý `ScriptException` và runtime exceptions theo ngữ cảnh.

## 6. Ví dụ Java 17+ độc lập: liệt kê engines và chẩn đoán thiếu engine

Lưu file **`EngineProbe.java`**:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import javax.script.ScriptEngine;
import javax.script.ScriptEngineFactory;
import javax.script.ScriptEngineManager;

public final class EngineProbe {
    public static void main(String[] args) {
        String requested = args.length == 0 ? "javascript" : args[0];
        ScriptEngineManager manager = new ScriptEngineManager();

        List<ScriptEngineFactory> factories =
                new ArrayList<>(manager.getEngineFactories());
        factories.sort(Comparator.comparing(
                ScriptEngineFactory::getEngineName));
        System.out.println("factories=" + factories.size());

        for (ScriptEngineFactory f : factories) {
            System.out.println("engine=" + f.getEngineName()
                    + ";language=" + f.getLanguageName()
                    + ";names=" + f.getNames()
                    + ";extensions=" + f.getExtensions()
                    + ";mime=" + f.getMimeTypes());
        }

        ScriptEngine engine = manager.getEngineByName(requested);
        if (engine == null) {
            System.out.println("NOT_FOUND: " + requested);
            System.out.println(
                    "hint=Install a compatible JSR-223 provider and check classloader visibility");
            return;
        }
        System.out.println("FOUND: " + engine.getFactory().getEngineName());
    }
}
```

Biên dịch/chạy:

```bash
javac --release 17 EngineProbe.java
java EngineProbe
java EngineProbe __missing_language_for_demo__
```

Trong thí nghiệm trên **JDK 17 không cài script-engine provider ngoài**, hai lượt chạy đã cho:

```text
factories=0
NOT_FOUND: javascript
hint=Install a compatible JSR-223 provider and check classloader visibility
```

và:

```text
factories=0
NOT_FOUND: __missing_language_for_demo__
hint=Install a compatible JSR-223 provider and check classloader visibility
```

**Đây là output của môi trường thử nghiệm sạch, không phải output bảo đảm cho mọi JDK 17.** Nếu classpath/module path có providers, `factories` có thể lớn hơn 0, các dòng `engine=...` sẽ xuất hiện, và `"javascript"` có thể được hỗ trợ tùy implementation.

Điểm QA của ví dụ:

- Code **không gọi `eval` khi engine vắng mặt**.
- In danh sách factories theo thứ tự engine name bằng cách copy sang `ArrayList`; không phụ thuộc thứ tự của ServiceLoader.
- Có nhánh xử lý rõ ràng cho `NOT_FOUND`.
- Không giả định Nashorn là engine mặc định.
- Trong nhánh thành công, lấy tên implementation từ **factory thực** đã tạo engine.

**Một nhánh báo không tìm thấy không phải lỗi biên dịch.** JDK vẫn compile/import package `javax.script` bình thường vì `java.scripting` có trong JDK; vấn đề xảy ra ở **runtime service discovery**.

## 7. Vì sao Java 17 thường không tìm được `"javascript"`?

Nashorn từng được phát hành cùng một số bản JDK và expose JavaScript through JSR-223. Nhưng lịch sử thay đổi:

| Giai đoạn | Tác động |
| --- | --- |
| Java 6 trở đi | API scripting `javax.script` tồn tại |
| JDK 11 | Nashorn được đánh dấu deprecated for removal |
| **JDK 15** | **Nashorn JavaScript engine/API và `jjs` tool bị loại khỏi JDK** |
| **JDK 17** | `java.scripting` API vẫn tồn tại; muốn JavaScript engine phải có provider thích hợp từ môi trường ngoài |
| Các JDK/môi trường sau | Danh sách engines phụ thuộc providers và classloader/module configuration, không được suy từ JDK version một mình |

JDK 17 **không tự động thay Nashorn bằng một engine JavaScript khác** chỉ vì bạn gọi `"javascript"`. Bạn phải chủ động lựa chọn implementation phù hợp, khai báo dependency, đảm bảo provider tương thích Java/JVM/JSR-223 và kiểm tra aliases được đăng ký.

Không nên hướng dẫn người học `import jdk.nashorn.api.scripting.NashornScriptEngineFactory` trong ứng dụng Java 17 thông thường: API của Nashorn bundled cũ đã bị gỡ. Khi chọn engine thay thế, đánh giá phiên bản, khả năng tương thích script, host interop, sandbox/security và threading; **không giả định mọi API Nashorn tương thích với mọi engine mới**.

**Dấu hiệu đặc trưng:** `ScriptEngineManager` khởi tạo thành công, `getEngineFactories()` trả empty list, `getEngineByName("javascript")` trả `null`. Đây là kịch bản hợp lệ và phổ biến trên JDK 17 không có provider.

## 8. SPI: điều kiện để manager khám phá được engine

`ScriptEngineManager` sử dụng service-provider mechanism tương ứng với **`java.util.ServiceLoader<javax.script.ScriptEngineFactory>`**.

### 8.1. Triển khai trên classpath

Một provider chạy qua classpath cần:

1. Một class **public** triển khai `ScriptEngineFactory`, có đường khởi tạo mà ServiceLoader có thể dùng.
2. Class ấy cùng dependencies thật sự có mặt trong **runtime classpath**.
3. Resource file chính xác:

```text
META-INF/services/javax.script.ScriptEngineFactory
```

4. Nội dung resource file ghi **fully qualified class name** của factory, mỗi provider một dòng, chẳng hạn:

```text
demo.scripting.MiniEngineFactory
```

5. Resource và class phải **visible** đối với class loader mà manager dùng để discover.

Service resource được đóng gói trong JAR/directory trên classpath, **không phải** `META-INF/services/javax.script.ScriptEngine`, vì cơ chế discovery tìm **`ScriptEngineFactory`**.

Nội dung file service dùng UTF-8; vì tên ví dụ chỉ có ASCII, file ASCII cũng là UTF-8 hợp lệ. Không thêm JSON/XML hay package name rút gọn.

### 8.2. Triển khai bằng named modules (JPMS)

Một provider dưới dạng named module có thể khai báo:

```java
module demo.mini.engine {
    requires java.scripting;
    provides javax.script.ScriptEngineFactory
        with demo.scripting.MiniEngineFactory;
}
```

Đây là **đoạn `module-info.java` minh họa**; không phải một trong các file dùng cho demo classpath ở mục 9–11. Module phải được build/resolve trong layer mà cơ chế service loading nhìn thấy. Nếu provider ở module path nhưng module chưa được resolve/bind đúng, chỉ đặt JAR đó trong một thư mục chưa đủ để `ScriptEngineManager` nhìn thấy.

`java.scripting` khai báo **`uses javax.script.ScriptEngineFactory`** để ServiceLoader lấy providers. Với provider là named module, `provides ... with ...` là cơ chế khai báo chuẩn; không dùng service file trên classpath như phương án duy nhất cho mọi hình thức deployment.

### 8.3. Engine implementation là dependency ngoài API

Thêm dependency `java.scripting` trong module Java của ứng dụng **chỉ để dùng API**, không tự thêm một `ScriptEngineFactory`. Tương tự, đưa một JAR bất kỳ vào project mà JAR không có provider registration thích hợp sẽ không làm engine được discover tự động.

Nếu bạn dùng một scripting implementation qua constructor trực tiếp thay vì SPI, code có thể hoạt động nhưng **`new ScriptEngineManager().getEngineByName(...)` chưa chắc biết tới nó**. Cần đăng ký factory hoặc đóng gói SPI đúng cách.

## 9. Tạo engine nhỏ để kiểm chứng cả nhánh thành công lẫn nhánh thất bại

Ta sẽ làm một **engine thử nghiệm tên `Mini Demo Engine`**, chỉ hiểu hai lệnh văn bản:

```text
upper:hello   -> HELLO
echo:hello    -> hello
```

Mục tiêu **không phải tạo một ngôn ngữ script production**, mà là kiểm chứng rõ:

- Discovery của `ScriptEngineFactory` qua `META-INF/services`.
- Lookup theo short name, extension và MIME.
- Nhánh missing name.
- `registerEngineName` thêm alias có chủ đích.
- Khác biệt giữa class loader của ứng dụng và platform class loader.

Cấu trúc thư mục:

```text
project/
├── src/
│   ├── EngineDiscoveryDemo.java
│   └── demo/
│       └── scripting/
│           └── MiniEngineFactory.java
└── classes/
    └── META-INF/
        └── services/
            └── javax.script.ScriptEngineFactory
```

`classes/` là **output directory** chứa `.class` và resource SPI; không sửa `java.scripting` trong JDK.

### 9.1. File `src/demo/scripting/MiniEngineFactory.java`

```java
package demo.scripting;

import java.io.IOException;
import java.io.Reader;
import java.util.List;
import java.util.Locale;
import javax.script.AbstractScriptEngine;
import javax.script.Bindings;
import javax.script.ScriptContext;
import javax.script.ScriptEngine;
import javax.script.ScriptEngineFactory;
import javax.script.ScriptException;
import javax.script.SimpleBindings;

public final class MiniEngineFactory implements ScriptEngineFactory {
    @Override public String getEngineName() { return "Mini Demo Engine"; }
    @Override public String getEngineVersion() { return "1.0"; }

    @Override public List<String> getExtensions() {
        return List.of("mini");
    }

    @Override public List<String> getMimeTypes() {
        return List.of("text/x-mini");
    }

    @Override public List<String> getNames() {
        return List.of("mini", "mini-demo");
    }

    @Override public String getLanguageName() {
        return "MiniDemo";
    }

    @Override public String getLanguageVersion() {
        return "1.0";
    }

    @Override public Object getParameter(String key) {
        if (ScriptEngine.ENGINE.equals(key)) return getEngineName();
        if (ScriptEngine.ENGINE_VERSION.equals(key)) return getEngineVersion();
        if (ScriptEngine.LANGUAGE.equals(key)) return getLanguageName();
        if (ScriptEngine.LANGUAGE_VERSION.equals(key)) return getLanguageVersion();
        if (ScriptEngine.NAME.equals(key)) return "mini";
        return null;
    }

    // Chỉ là demo toy language; không hỗ trợ gọi Java methods bằng cú pháp script.
    @Override public String getMethodCallSyntax(
            String obj, String method, String... args) {
        return null;
    }

    @Override public String getOutputStatement(String text) {
        return "echo:" + text;
    }

    @Override public String getProgram(String... statements) {
        return String.join("\n", statements);
    }

    @Override public ScriptEngine getScriptEngine() {
        return new MiniEngine(this);
    }

    private static final class MiniEngine extends AbstractScriptEngine {
        private final ScriptEngineFactory factory;

        MiniEngine(ScriptEngineFactory factory) {
            this.factory = factory;
        }

        @Override public Object eval(String script, ScriptContext context)
                throws ScriptException {
            if (script == null) throw new NullPointerException("script");

            if (script.startsWith("upper:")) {
                return script.substring(6).toUpperCase(Locale.ROOT);
            }
            if (script.startsWith("echo:")) {
                return script.substring(5);
            }
            throw new ScriptException("Unsupported mini command");
        }

        @Override public Object eval(Reader reader, ScriptContext context)
                throws ScriptException {
            try {
                StringBuilder text = new StringBuilder();
                char[] buffer = new char[1024];
                int n;

                while ((n = reader.read(buffer)) != -1) {
                    text.append(buffer, 0, n);
                }
                return eval(text.toString(), context);
            } catch (IOException ex) {
                throw new ScriptException(ex);
            }
        }

        @Override public Bindings createBindings() {
            return new SimpleBindings();
        }

        @Override public ScriptEngineFactory getFactory() {
            return factory;
        }
    }
}
```

Đây là **file Java độc lập và có thể biên dịch**, nhưng cần bước đóng gói resource SPI và file client ở bên dưới để kiểm thử manager.

Tại sao factory phải triển khai nhiều methods? Vì `ScriptEngineFactory` là một interface mô tả metadata và cách tạo engine; `ScriptEngineManager` không thể tự suy `getNames()` hoặc `getMimeTypes()` chỉ bằng tên class.

`AbstractScriptEngine` giảm phần code boilerplate cho `ScriptEngine`, nhưng vẫn yêu cầu thực hiện `eval(String,ScriptContext)`, `eval(Reader,ScriptContext)`, `createBindings` và `getFactory`. Toy engine dùng `Locale.ROOT` để uppercase ổn định hơn trước khác biệt locale máy chạy.

**Giới hạn có chủ đích của demo:** `getMethodCallSyntax` trả `null` vì không hỗ trợ Java method-call syntax, `getProgram` nối các statements nhưng evaluator chỉ hiểu **một lệnh `upper:` hoặc `echo:` cho mỗi lần eval**. Không dùng provider demo này làm scripting runtime cho ứng dụng thật, đặc biệt không hỗ trợ sandbox, parser đa câu lệnh hoặc kiểm soát thực thi.

### 9.2. File service provider — không phải Java source

Tạo file:

```text
classes/META-INF/services/javax.script.ScriptEngineFactory
```

Nội dung **đúng một dòng**:

```text
demo.scripting.MiniEngineFactory
```

File cần tồn tại tại **runtime**, cùng classpath root `classes/` chứa `demo/scripting/MiniEngineFactory.class`. Nó không được đặt trong `src/META-INF` rồi quên copy vào output; `javac` biên dịch Java source **không tự copy tùy ý mọi resource**.

### 9.3. File `src/EngineDiscoveryDemo.java`

```java
import java.util.Comparator;
import javax.script.ScriptEngine;
import javax.script.ScriptEngineFactory;
import javax.script.ScriptEngineManager;
import javax.script.ScriptException;
import demo.scripting.MiniEngineFactory;

public final class EngineDiscoveryDemo {
    public static void main(String[] args) throws ScriptException {
        ScriptEngineManager manager = new ScriptEngineManager();

        boolean factoryVisible = manager.getEngineFactories().stream()
                .map(ScriptEngineFactory::getEngineName)
                .anyMatch("Mini Demo Engine"::equals);
        System.out.println("providerVisible=" + factoryVisible);

        ScriptEngine byName = manager.getEngineByName("mini");
        System.out.println("byName=" + (byName != null));
        System.out.println("byExtension=" +
                (manager.getEngineByExtension("mini") != null));
        System.out.println("byMime=" +
                (manager.getEngineByMimeType("text/x-mini") != null));
        System.out.println("unknown=" +
                (manager.getEngineByName("__definitely_missing_engine__") == null));

        if (byName == null) {
            throw new IllegalStateException("Mini provider not visible");
        }

        System.out.println("result=" + byName.eval("upper:hello"));
        System.out.println("language=" + byName.getFactory().getLanguageName());

        manager.registerEngineName("mini-alias", new MiniEngineFactory());
        System.out.println("alias=" +
                (manager.getEngineByName("mini-alias") != null));

        ScriptEngineManager platformOnly =
                new ScriptEngineManager(ClassLoader.getPlatformClassLoader());
        System.out.println("platformCanSeeMini=" +
                (platformOnly.getEngineByName("mini") != null));

        System.out.println("javascriptAvailable=" +
                (manager.getEngineByName("javascript") != null));
    }
}
```

Ở ví dụ này `import java.util.Comparator;` không được sử dụng, nên **có thể bỏ import đó mà không đổi hành vi**. Nó không gây lỗi `javac` vì Java cho phép imports không sử dụng. Phần quan trọng là các `javax.script` imports và `demo.scripting.MiniEngineFactory`.

### 9.4. Biên dịch và chạy

Trên Bash (Linux/macOS hoặc shell tương thích), từ thư mục `project/`:

```bash
mkdir -p classes/META-INF/services
printf 'demo.scripting.MiniEngineFactory\n' > classes/META-INF/services/javax.script.ScriptEngineFactory

javac --release 17 -d classes \
    src/demo/scripting/MiniEngineFactory.java \
    src/EngineDiscoveryDemo.java

java -cp classes EngineDiscoveryDemo
```

Trên **Windows PowerShell**, tạo đúng service file và chạy cùng ví dụ:

```powershell
New-Item -ItemType Directory -Force -Path "classes/META-INF/services"

Set-Content -Encoding Ascii `
    -Path "classes/META-INF/services/javax.script.ScriptEngineFactory" `
    -Value "demo.scripting.MiniEngineFactory"

javac --release 17 -d classes `
    src/demo/scripting/MiniEngineFactory.java `
    src/EngineDiscoveryDemo.java

java -cp classes EngineDiscoveryDemo
```

Vì provider class name là chuỗi ASCII nên lựa chọn `-Encoding Ascii` tạo file có bytes tương thích UTF-8, tránh BOM phát sinh từ một số phiên bản PowerShell khi dùng tùy chọn UTF-8.

**Lệnh phải chạy với classpath root `classes`**. Nếu gọi `java EngineDiscoveryDemo` từ thư mục dự án mà không dùng `-cp classes`, JVM có thể không tìm được main class hoặc provider resource. `-cp classes` cho classloader thấy cả `.class` lẫn `META-INF/services`.

## 10. Stdout từ demo SPI đã được kiểm chứng trên Java 17

Với provider demo trên classpath và JDK chạy không có JavaScript provider khác, output:

```text
providerVisible=true
byName=true
byExtension=true
byMime=true
unknown=true
result=HELLO
language=MiniDemo
alias=true
platformCanSeeMini=false
javascriptAvailable=false
```

**Những dòng đầu xác minh chính xác cấu hình demo.** Dòng cuối `javascriptAvailable=false` là **kết quả của môi trường thử nghiệm**; nếu classpath/JDK bạn có JavaScript provider khác, dòng cuối có thể là `true`. Mục tiêu của demo là chứng minh việc có `mini` không tự tạo engine `javascript`.

### Phân tích lần lượt

1. **`providerVisible=true`**: Manager đã tìm thấy `MiniEngineFactory` qua `ServiceLoader`, nên factory xuất hiện trong `getEngineFactories()`.
2. **`byName=true`**: `"mini"` tồn tại trong `MiniEngineFactory.getNames()`.
3. **`byExtension=true`**: `"mini"` tồn tại trong `getExtensions()`.
4. **`byMime=true`**: `"text/x-mini"` tồn tại trong `getMimeTypes()`.
5. **`unknown=true`**: Một tên không được công bố bởi factory nhận kết quả `null` và ứng dụng xử lý được, không chạy script.
6. **`result=HELLO`**: `MiniEngine.eval("upper:hello")` chạy **ngôn ngữ demo**, không phải JavaScript.
7. **`language=MiniDemo`**: Tên ngôn ngữ là metadata từ `getLanguageName`; không phải alias `"mini"` buộc phải trùng.
8. **`alias=true`**: Một association được đăng ký thủ công bằng `registerEngineName("mini-alias", ...)` làm alias này hoạt động ở manager hiện tại.
9. **`platformCanSeeMini=false`**: `ScriptEngineManager(ClassLoader.getPlatformClassLoader())` dùng một loader **không nhìn thấy** provider classpath của ứng dụng, nên không tìm được `"mini"`. Điều đó cho thấy discovery phụ thuộc loader.
10. **`javascriptAvailable=false`**: Provider demo không cung cấp JavaScript; JDK thử nghiệm không có JavaScript engine nào khác. **Không suy thành tuyên bố mọi Java 17 đều trả false**.

Chú ý: `getEngineByName`, `getEngineByExtension` và `getEngineByMimeType` **có thể tạo các engine instances khác nhau** khi gọi ba lần. Việc cả ba phép so sánh đều `true` **không chứng minh chúng trả cùng một object**. Factory có quyền tạo engine instance mới cho mỗi lượt lookup.

## 11. Class loader: nguyên nhân thường gặp khi JAR đã có mà vẫn `null`

`ScriptEngineManager` có hai constructor quan trọng:

```java
new ScriptEngineManager();
new ScriptEngineManager(loader);
```

- **Constructor không tham số** có tác dụng tương đương `new ScriptEngineManager(Thread.currentThread().getContextClassLoader())`. Đây là **thread context class loader (TCCL)** tại thời điểm tạo manager.
- **Constructor nhận `ClassLoader`** dùng loader được chỉ định để tìm implementations của `ScriptEngineFactory` theo service-provider mechanism.
- **Truyền `loader == null`** theo API Java SE 17 chỉ tìm factories **bundled with platform**, không mang nghĩa tự sử dụng app classpath loader.

Đoạn code minh họa:

```java
ClassLoader context = Thread.currentThread().getContextClassLoader();

ScriptEngineManager byContext = new ScriptEngineManager();
ScriptEngineManager explicit = new ScriptEngineManager(context);
ScriptEngineManager byPlatform =
        new ScriptEngineManager(ClassLoader.getPlatformClassLoader());
```

Ba manager không bắt buộc nhìn thấy cùng factories nếu loader visibility khác nhau. Trong application server/plugin framework, các threads có thể có TCCL khác nhau; tạo manager ở thread bootstrap và dùng ở thread plugin có thể đưa đến kết quả khác với tạo manager ngay trong plugin.

### Chẩn đoán classloader an toàn

Khi lookup thất bại, hãy xác định:

```java
ClassLoader tccl = Thread.currentThread().getContextClassLoader();
ClassLoader owner = YourApplication.class.getClassLoader();
```

Đây là **mã minh họa**, thay `YourApplication` bằng class có thật. `tccl` có thể khác `owner`; không phải lúc nào `owner` cũng là loader cần dùng (tùy kiến trúc module/plugin).

Trong Java 17, demo đã kiểm chứng rằng app classpath manager nhìn thấy provider `mini`, còn platform loader manager không thấy. Điều này giúp giải thích trường hợp “JAR nằm trong dependency nhưng `getEngineByName` vẫn null”:

- Factory resource không được đóng gói vào JAR runtime.
- JAR provider không nằm ở runtime classpath/module path của classloader thực tế.
- Provider class hoặc dependencies của nó không load được.
- Context class loader khác loader chứa provider.
- Provider nằm trong named module nhưng module chưa được resolve/service-bound trong layer phù hợp.
- Factory được tìm thấy nhưng **alias muốn tìm không nằm trong `getNames()`**.

### TCCL và quản lý thread

Không nên đổi TCCL toàn cục chỉ để chữa một lookup null mà không hiểu giới hạn classloader. Nếu bắt buộc đặt TCCL quanh một thao tác khởi tạo, hãy khôi phục trong `finally`:

```java
Thread thread = Thread.currentThread();
ClassLoader old = thread.getContextClassLoader();
try {
    thread.setContextClassLoader(providerLoader);
    ScriptEngineManager manager = new ScriptEngineManager();
    // Dùng manager trong phạm vi được thiết kế.
} finally {
    thread.setContextClassLoader(old);
}
```

Đây là **mã minh họa**; `providerLoader` phải là loader hợp lệ có sẵn. Nếu code có `SecurityManager`/permission constraints cũ hoặc môi trường hạn chế thread context access, việc thay đổi loader có thể không được cho phép. Trong thread pools, quên khôi phục TCCL có thể làm rò state giữa requests và giữ plugin classloader lâu hơn mong muốn.

Ưu tiên `new ScriptEngineManager(providerLoader)` khi muốn chủ động xác định loader mà không thay đổi ambient thread state.

## 12. `registerEngineName`, `registerEngineExtension`, `registerEngineMimeType` dùng để làm gì?

Ngoài SPI discovery, manager cho phép đăng ký association **trên một manager instance**:

```java
manager.registerEngineName("alias", existingFactory);
manager.registerEngineExtension("mylang", existingFactory);
manager.registerEngineMimeType("text/x-mylang", existingFactory);
```

Đây là **đoạn minh họa** với `manager` và `existingFactory` đã tồn tại.

Điểm cần nhớ:

- Các API này **đăng ký mapping từ key sang factory**, không tải/download/cài đặt thư viện engine.
- Chúng là lựa chọn phù hợp nếu bạn có một `ScriptEngineFactory` hợp lệ và muốn thêm alias do ứng dụng kiểm soát hoặc thay association.
- Manager **ưu tiên registered association** cho key tương ứng trước khi tìm factories từ service discovery.
- Registration có phạm vi **manager instance**, không tự sửa registry toàn JVM, không sửa META-INF/services hoặc module descriptor.
- Factory được đăng ký thủ công không nhất thiết trở thành một phần của **danh sách factories phát hiện từ SPI** mà `getEngineFactories()` trả về; không dùng list đó làm danh sách tất cả alias thủ công.
- `registerEngineName` không nên là cách “gắn nhãn javascript” cho một engine **không hiểu JavaScript**: đổi alias không biến ngôn ngữ hoặc semantics của provider.

Nếu `getEngineByName("javascript")` null, đừng nghĩ `registerEngineName("javascript", null)` có thể sửa lỗi: factory argument null không hợp lệ và ném `NullPointerException`. Bạn phải **có implementation thực sự**.

### Factory list khác với registration table

Hai nguồn lookup có vai trò khác nhau:

```text
ServiceLoader factory inventory: getEngineFactories()
        |
        +--> metadata getNames(), getExtensions(), getMimeTypes()

Explicit per-manager associations:
        |
        +--> registerEngineName/Extension/MimeType(...)
```

Lookup method thử explicit mapping trước, rồi tìm discovered factories. Vì vậy khi debug **alias** do ứng dụng tự đăng ký, `getEngineFactories()` có thể không phản ánh alias đó như một entry độc lập.

## 13. Global bindings, engine scope và tại sao không chia sẻ tùy tiện

`ScriptEngineManager` còn giữ **`GLOBAL_SCOPE` Bindings**. Khi manager tạo một `ScriptEngine`, nó đặt global bindings này vào script context của engine. Ví dụ API:

```java
ScriptEngineManager manager = new ScriptEngineManager();
manager.put("environment", "development");

ScriptEngine engine = manager.getEngineByName("mini");
if (engine != null) {
    // Engine có GLOBAL_SCOPE bindings do manager cung cấp.
}
```

Đây là **mã minh họa trong một chương trình**, không mặc định toy engine `MiniEngine` sẽ tự sử dụng biến `"environment"` khi tính lệnh.

Phân biệt:

- **`ENGINE_SCOPE`**: bindings ở mức script engine/context, thường ưu tiên khi tìm attribute.
- **`GLOBAL_SCOPE`**: bindings do manager cung cấp và có thể được các engine instances của manager ấy nhìn thấy.

**Chia sẻ manager không phải sandbox.** Nếu bạn đặt credentials, Java objects đặc quyền hoặc dữ liệu tenant A vào global bindings, rồi dùng cùng manager để chạy script của tenant B, cần xem xét rủi ro dữ liệu và quyền thực thi.

Đặc biệt với engine có host interop, một script có thể gọi Java APIs hoặc tác động vào object được truyền qua bindings tùy khả năng provider. `ScriptEngineManager` chỉ giúp tìm engine; **nó không tự giới hạn hệ thống tệp, network hoặc quyền thực thi của script**.

Khi cho phép script từ nguồn không tin cậy, cần đánh giá chính sách host access, cách cô lập process/container, resource limits, timeouts, audit và engine-specific sandbox. Đừng coi việc dùng `javax.script` là một security boundary mặc định.

## 14. Có engine chưa chắc đã chạy được mọi script

`getEngineByName("javascript") != null` chỉ chứng minh một implementation tương ứng đang visible và tạo được engine. Nó **không** cam kết:

- Ngôn ngữ/phiên bản tương thích code bạn đang có.
- Các API đặc thù của Nashorn vẫn tồn tại.
- `eval` luôn trả `String`; return type là `Object` và có thể là `null`.
- `Invocable` hoặc `Compilable` luôn được hỗ trợ; đó là các interfaces tùy implementation.
- Engine an toàn để dùng đồng thời từ nhiều threads.
- Script từ người dùng không tin cậy có thể chạy an toàn.
- Engine xử lý charset/encoding hoặc resource resolution như một implementation khác.

Với engine thật:

```java
ScriptEngine engine = manager.getEngineByName(configuredName);
if (engine == null) {
    throw new IllegalStateException("Engine unavailable: " + configuredName);
}
try {
    Object result = engine.eval(scriptSource);
    // Xác minh kiểu kết quả theo hợp đồng ứng dụng.
} catch (ScriptException ex) {
    // Xử lý lỗi do engine báo khi phân tích/thực thi script.
    throw new IllegalStateException("Script execution failed", ex);
}
```

Đây là **đoạn minh họa** với `manager`, `configuredName` và `scriptSource` đã tồn tại. Tránh log trực tiếp `scriptSource` hoặc những arguments nhạy cảm nếu script có dữ liệu bí mật.

Tách ba lớp lỗi:

| Thời điểm | Dấu hiệu | Nguyên nhân thường gặp |
| --- | --- | --- |
| **Khởi tạo/discovery** | Không có factory, `getEngineByName` trả `null` | Provider/alias/loader/module chưa phù hợp |
| **Tạo engine / cấu hình** | Provider khởi tạo lỗi, dependency missing, runtime exception | Engine implementation/deployment |
| **Thực thi script** | `ScriptException` hoặc lỗi do engine báo | Cú pháp/ngữ nghĩa runtime của ngôn ngữ |

Nếu đang không có engine, **đừng gọi `eval` để thử**: không có object nào để thực thi; cần xử lý discovery trước.

## 15. Vấn đề thứ tự và sự không chắc chắn của kết quả khám phá

Trong môi trường chứa nhiều providers:

- `getEngineFactories()` không nên được coi là một danh sách có thứ tự cố định theo tên nhà cung cấp.
- Các factories có thể công bố aliases trùng nhau, ví dụ nhiều engines cùng nhận `"javascript"`.
- Một `ScriptEngineManager` có thể chọn factory theo cơ chế discovery/association, nhưng **đừng dựa trên một thứ tự ngẫu nhiên để lựa chọn implementation quan trọng**.
- Nếu ứng dụng cần một engine cụ thể, hãy cấu hình **tên implementation + version policy** và xác minh `engine.getFactory().getEngineName()/getEngineVersion()` sau lookup.
- Khi ứng dụng sở hữu factory tin cậy, có thể trực tiếp tạo từ factory hoặc đăng ký association rõ ràng thay vì hy vọng engine “đầu tiên” đúng.
- Tạo manager mới có thể nhận danh sách khác nếu runtime class loader/module layer đã thay đổi; manager không tự trở thành công cụ quan sát liên tục mọi JAR được tải thêm về sau.

Giữ những giá trị kỳ vọng trong cấu hình và kiểm thử integration trong cùng môi trường triển khai. Không nên chỉ có test unit chạy trên máy developer khi production dùng một container image hoặc class loader khác.

## 16. JAR, classpath, module path: kiểm tra gì khi “cài rồi vẫn không thấy”?

Nếu có một provider JSR-223 từ thư viện ngoài, thứ tự chẩn đoán nên là:

1. **Xác nhận dependency đã ở runtime**, không chỉ compile-time/test scope.
2. Với JAR ở **classpath**, kiểm tra đường dẫn `META-INF/services/javax.script.ScriptEngineFactory` thực sự nằm trong JAR output.
3. Mở service file và kiểm tra provider class name đầy đủ chính xác; package/class phải có trên cùng classloader hoặc parent visibility path.
4. Factory phải implement `javax.script.ScriptEngineFactory` và class/dependencies tương thích với JDK đang chạy.
5. Với **named module**, xem `module-info.class` có `provides javax.script.ScriptEngineFactory with ...` và module đã được resolve trong runtime layer.
6. Tạo `ScriptEngineManager` với loader phù hợp; kiểm tra thread context loader nếu dùng constructor mặc định.
7. **In `getEngineFactories()`** và metadata của từng factory để phân biệt “không nhìn thấy provider” với “sai alias”.
8. Nếu thấy đúng factory nhưng `getEngineByName` trả `null`, so aliases; thử extension/MIME **chỉ khi provider công bố chúng**.
9. Nếu ứng dụng dùng shaded/fat JAR, kiểm tra quá trình đóng gói **không làm mất/ghi đè nhiều service files** từ dependencies khác nhau.
10. Nếu engine instance tạo thất bại, kiểm tra dependency conflicts, class loading errors, service configuration và logs; không suy tất cả là lỗi cú pháp script.
11. Khi deploy containers, so sánh **JDK image** và classpath/runtime module path giữa dev và production.
12. Nếu có nhiều classloader, xác nhận provider nằm trong đúng loader/layer mà manager thực sự dùng.

Một vài lệnh kiểm tra thông dụng:

```bash
jar tf engine-provider.jar
java --describe-module java.scripting
```

Lệnh `jar tf` cho thấy nội dung JAR để bạn tìm service file/class; `java --describe-module java.scripting` giúp xác nhận module có `exports javax.script` và `uses javax.script.ScriptEngineFactory`.

Trong môi trường Linux có thể lọc:

```bash
jar tf engine-provider.jar | grep 'META-INF/services/javax.script.ScriptEngineFactory'
```

Còn ở PowerShell:

```powershell
jar tf engine-provider.jar | Select-String 'META-INF/services/javax.script.ScriptEngineFactory'
```

Những lệnh này **không cài provider**; chúng giúp xác định đường dẫn packaging. Nếu JAR không nằm ở runtime classpath/module path, chỉ thấy service file trong JAR cũng chưa đủ.

## 17. Thiết kế một quy trình startup tin cậy

Một ứng dụng dùng scripting như một dependency có thể triển khai quy trình:

```text
Application startup
    |
    v
Load configuration (required engine alias, version policy)
    |
    v
Create ScriptEngineManager with intended ClassLoader
    |
    v
Log/inspect safe metadata from getEngineFactories()
    |
    v
Lookup required engine by exact alias/extension/MIME
    |
    +--- null ---> Disable feature or fail startup with actionable message
    |
    +--- found --> Inspect factory identity and supported capabilities
                       |
                       v
                 Run a controlled smoke test
                       |
                       v
                 Ready to accept scripts
```

**Không cần chạy script của người dùng làm smoke test.** Dùng một biểu thức nhỏ, không có side effect, đã được chuẩn hóa cho ngôn ngữ/provider cụ thể. Nếu engine không hỗ trợ `eval` cho smoke test bạn tưởng tượng, hãy kiểm tra lại hợp đồng implementation thay vì coi nó là engine lỗi.

Với hệ thống cần engine cho chính sách bảo mật hoặc tính toán tài chính quan trọng, ưu tiên **fail fast** và không tự động chuyển sang một engine khác có semantics khác. Với tính năng tùy chọn, có thể ghi rõ trạng thái `DISABLED` và hướng dẫn cài provider.

### Thiết kế thông báo lỗi hữu ích

Ví dụ thông báo cho người vận hành:

```text
Required JSR-223 engine 'javascript' was not found.
Check runtime dependencies, META-INF/services or module provides,
ScriptEngineManager class loader, and factory aliases.
```

Tốt hơn nhiều so với:

```text
java.lang.NullPointerException: Cannot invoke ScriptEngine.eval(...)
```

Thông báo nên đủ chi tiết để sửa cấu hình, nhưng không cần in toàn bộ environment variables, script source hoặc secrets.

## 18. Kiểm thử: khi không có provider và khi có provider

Các trường hợp cần kiểm thử trong integration pipeline:

| Test | Thiết lập | Kỳ vọng |
| --- | --- | --- |
| No provider | JDK 17/test runtime sạch | `getEngineFactories()` có thể rỗng, `getEngineByName` là `null` |
| Unknown alias | Bất kể có provider demo | `getEngineByName("__definitely_missing_engine__")` là `null` |
| Provider visible | Có class + đúng META-INF/services | Factory xuất hiện trong `getEngineFactories()` |
| Name lookup | Provider công bố `"mini"` | Engine khác `null` |
| Extension lookup | `getExtensions()` chứa `"mini"` | Engine khác `null` |
| MIME lookup | `getMimeTypes()` chứa `"text/x-mini"` | Engine khác `null` |
| Custom alias | `registerEngineName("mini-alias", factory)` | Alias hoạt động ở manager đó |
| Loader isolation | Provider chỉ nằm trong app loader | Platform-only manager không thấy provider demo |
| Script smoke test | Engine demo `eval("upper:hello")` | Trả `"HELLO"` |
| Unsupported syntax | Engine demo `eval("not-supported")` | Ném `ScriptException` |
| Engine missing | Engine null | Không gọi eval, rõ thông báo hoặc fail fast |

Thử cả **tên có trong `getNames()`** và tên *gần giống* nhưng không được hỗ trợ. Đừng dùng giả định viết hoa/thường được chuẩn hóa tự động; hãy kiểm tra chính xác aliases và các biến thể mà provider đăng ký.

### Test tính độc lập của manager

Hai `ScriptEngineManager` không chia sẻ một bảng associations thủ công toàn JVM. Nếu test A đăng ký một alias bằng `registerEngineName`, đừng kỳ vọng test B tạo manager mới sẽ tự thấy alias ấy nếu factory không được SPI công bố hoặc test B không đăng ký lại.

### Test đóng gói

Chạy jar/fat-jar thật, không chỉ chạy unit tests trong IDE. Khi đóng gói, Java class và service descriptor phải được copy/merge chính xác. Một provider hoạt động khi chạy `java -cp classes ...` nhưng mất sau khi đóng gói là tín hiệu packaging hoặc classloader vấn đề.

## 19. Rủi ro bảo mật: discovery không phải sandbox

`ScriptEngineManager` chỉ phân giải **ai có khả năng chạy script**. Nó không bảo đảm:

- Engine không thực hiện file/network I/O.
- Engine không nhìn thấy object Java nhạy cảm từ bindings.
- Script không truy cập tài nguyên ngoài policy.
- Engine thực thi có time limit/CPU quota.
- Một `eval` do thread khác gọi an toàn.
- Provider class đáng tin hoặc không có side effect trong constructor.

Cần xem scripting engine như **một thành phần thực thi code** có thể có host access mạnh. Chỉ dùng providers được chấp thuận và khai báo dependency rõ. Với code không tin cậy, cân nhắc phân vùng process/container/permission model của engine, timeout ở cấp worker process, input validation và logging an toàn.

Một provider không mong muốn xuất hiện trong classpath có thể thay đổi kết quả lookup theo aliases. Vì vậy ứng dụng quan trọng nên kiểm tra identity/version của factory và kiểm soát runtime dependency graph.

Không bao giờ cố làm hệ thống “chạy cho bằng được” bằng cách gọi một factory không rõ nguồn hoặc chuyển kịch bản sang engine khác mà chưa kiểm chứng semantics và security policy.

## 20. Những lỗi phổ biến và cách sửa

| Lỗi | Vì sao xảy ra | Cách xử lý |
| --- | --- | --- |
| `NullPointerException` tại `engine.eval(...)` | Engine có thể `null` sau lookup | Kiểm tra null trước, fail fast/degrade đúng contract |
| `getEngineFactories()` rỗng trên JDK 17 | Không có JSR-223 provider visible | Cài/chạy đúng provider hoặc vô hiệu hóa tính năng |
| JavaScript lookup null | Nashorn không còn bundled; không có provider thay thế hoặc sai alias | Kiểm tra `getNames()`, dependency, loader |
| `.getEngineByName("JavaScript")` khác với alias thực | Provider không công bố tên ấy | Dùng một tên đúng trong `getNames()` |
| `getEngineByExtension("file.mini")` null | API cần extension token | Trích và truyền `"mini"` |
| Dùng MIME không do factory công bố | Không có mapping | Xem `getMimeTypes()` |
| IDE chạy được, JAR chạy không tìm engine | Service file/dep thiếu trong artifact | Kiểm tra packaging/merge service resources |
| Module JAR trên module path nhưng không discover | Provider module chưa được resolve/bind phù hợp | Xem `provides`, module layer và service binding |
| App loader thấy provider, platform loader không thấy | Classloader visibility khác nhau | Tạo manager với intended loader |
| Tự `new Factory()` được nhưng manager không thấy | Chưa khai SPI/register | Thêm `META-INF/services`/`provides` hoặc đăng ký factory |
| `registerEngineName` xong mà app khác vẫn null | Registration chỉ thuộc manager instance | Đăng ký đúng nơi hoặc cung cấp SPI toàn hệ thống |
| `eval` ném `ScriptException` | Provider có thật, script có lỗi | Kiểm tra script syntax/runtime và exception |
| Sử dụng `engine` đồng thời gây lỗi | Provider không bảo đảm thread safety | Kiểm tra `THREADING` metadata, cách tạo engines/contexts |
| Tưởng `getEngineName()` là short alias | Metadata implementation khác `getNames()` | Dùng `getNames()` để lookup |
| In factory list thấy engine A, nhưng alias chọn engine B | Nhiều providers/registrations trùng alias | Pin provider/config, kiểm tra factory của engine tạo ra |
| Java 17 compile được `javax.script` nên chắc có JS | API vẫn còn, implementation có thể vắng | Test runtime trong deployment thật |

## 21. Bài tập tự kiểm tra (có đáp án)

1. **`new ScriptEngineManager()` dùng gì để tìm engine?** Service provider mechanism cho `ScriptEngineFactory`, với TCCL của thread khởi tạo.
2. **`getEngineByName` trả gì khi không có factory phù hợp?** `null`.
3. **Tại sao gọi `.eval()` ngay có thể ném NPE?** Vì reference engine được trả về là `null`.
4. **`getEngineFactories()` rỗng có nghĩa module `java.scripting` không tồn tại không?** Không. API có thể tồn tại nhưng không có implementation.
5. **Nashorn bị loại khỏi JDK từ phiên bản nào?** JDK 15.
6. **Java 17 có còn `javax.script.ScriptEngineManager` không?** Có, trong module `java.scripting`.
7. **Ba cách lookup chính là gì?** Tên/alias, phần mở rộng, MIME type.
8. **`getEngineByName` dựa vào `getEngineName()` hay `getNames()`?** Dựa trên aliases được đăng ký hoặc `getNames()`.
9. **Factory công bố `"mini"` và `"mini-demo"` có bảo đảm `"MiniDemo"` là alias không?** Không, trừ khi factory cũng đưa `"MiniDemo"` vào `getNames()`.
10. **Đường dẫn resource SPI cho classpath là gì?** `META-INF/services/javax.script.ScriptEngineFactory`.
11. **Nội dung resource SPI chứa gì?** Fully qualified binary class names của factories, mỗi dòng một tên.
12. **Ở named module, cách khai provider đúng?** `provides javax.script.ScriptEngineFactory with ...` trong `module-info.java`, module được resolve và service visible.
13. **`new ScriptEngineManager(null)` có giống constructor không tham số không?** Không. `null` chỉ tìm factories bundled with platform; constructor không tham số dùng TCCL.
14. **Đổi TCCL có thể thay kết quả discovery không?** Có, vì loader visibility khác; nên dùng constructor nhận loader rõ ràng khi phù hợp.
15. **`registerEngineName` có cài đặt language engine mới không?** Không; nó chỉ mapping một key tới factory đã có.
16. **Một factory được đăng ký thủ công có nhất thiết xuất hiện trong `getEngineFactories()` không?** Không; danh sách đó phản ánh SPI-discovered factories.
17. **`getEngineByName("mini")`, `getEngineByExtension("mini")` có trả cùng object không?** Không bảo đảm; factory có thể tạo mới mỗi lần.
18. **Nếu ứng dụng thiếu engine cần để xác minh quyền, nên tự động bỏ qua kiểm tra không?** Không; phải fail closed/fail fast theo policy.
19. **`ScriptException` có giống engine-not-found không?** Không. `ScriptException` là lỗi khi script được xử lý bởi engine; thiếu engine là lỗi discovery.
20. **Có `ScriptEngine` có nghĩa script an toàn với mọi Java API không?** Không. JSR-223 không phải sandbox.
21. **Tại sao `java -cp classes EngineDiscoveryDemo` quan trọng?** Loader phải nhìn thấy cả factory classes và service resource trong `classes`.
22. **Demo `providerVisible=true` nhưng `platformCanSeeMini=false` dạy gì?** Discovery phụ thuộc class loader, không chỉ sự hiện diện của Java API.
23. **Khi nhiều engines cùng alias, cần kiểm tra gì?** Identity/version của factory thực sự được chọn, chính sách lựa chọn và classloader/registration.
24. **Có cần ghi đè JDK module để thêm language engine không?** Không; JSR-223 providers bên ngoài được phát hiện bằng SPI trên classpath/module path phù hợp.
25. **Khi không có provider trong production, thông báo lỗi hữu ích nên chứa gì?** Tên yêu cầu, aliases/providers visible, dependency/module/classloader gợi ý; không rò bí mật.

## 22. Tài liệu chính thức Java SE 17 và lịch sử Nashorn

- [Java SE 17 — `ScriptEngineManager`](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptEngineManager.html): constructors, ServiceLoader, `getEngineFactories`, ba lookup methods, null return và registrations.
- [Java SE 17 — `ScriptEngineFactory`](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptEngineFactory.html): aliases, extensions, MIME types, versions và factory metadata.
- [Java SE 17 — `ScriptEngine`](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptEngine.html): `eval`, context, bindings và contract kết quả.
- [Java SE 17 — `AbstractScriptEngine`](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/AbstractScriptEngine.html): superclass hỗ trợ triển khai toy engine và overloads `eval`.
- [Java SE 17 — `ServiceLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html): SPI deployment qua `META-INF/services`, named module `provides` và visibility.
- [Java SE 17 — `javax.script` package](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/package-summary.html): API và những interfaces liên quan.
- [JEP 372 — Remove the Nashorn JavaScript Engine](https://openjdk.org/jeps/372): Nashorn bị loại khỏi JDK 15; không đồng nghĩa xóa JSR-223 API.
- [Oracle JDK 17 Migration Guide — Removed Tools and Components](https://docs.oracle.com/en/java/javase/17/migrate/removed-tools-and-components.html): xác nhận Nashorn/JJS đã bị loại và tác động migration.

**Kết luận:** `ScriptEngineManager` là **cơ chế khám phá factories**, không phải một script engine. Hãy kiểm tra `getEngineFactories()` và metadata, lookup theo **alias/extension/MIME do provider thật công bố**, và **xử lý `null` trước khi `eval`**. Trên Java 17, việc không tìm được `"javascript"` là kịch bản hợp lệ do Nashorn đã rời JDK; giải pháp là triển khai **provider JSR-223 phù hợp, đúng class loader/module**, hoặc xử lý feature unavailable có chủ đích — không che lỗi bằng NPE catch hay suy đoán engine phải có sẵn.
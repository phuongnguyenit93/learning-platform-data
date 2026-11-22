# Khám phá tên, phần mở rộng tệp, MIME type và phiên bản ScriptEngine trong Java

## 1. Bài toán khi nhúng ngôn ngữ kịch bản

Ứng dụng Java có thể cho phép thực thi một ngôn ngữ kịch bản thông qua **JSR-223 (Scripting for the Java Platform)**, API thuộc module `java.scripting` và package `javax.script`. Thay vì hard-code một engine duy nhất, host thường cần biết **những scripting engine nào hiện diện** và **mỗi engine nhận dạng loại script nào**.

Các thông tin thường dùng khi khám phá:

- **Tên triển khai engine**: `ScriptEngineFactory.getEngineName()`, ví dụ một tên sản phẩm/implementation.
- **Các tên ngắn hoặc bí danh để tìm engine**: `getNames()`, tương ứng `ScriptEngineManager.getEngineByName(...)`.
- **Phần mở rộng tệp kịch bản**: `getExtensions()`, tương ứng `getEngineByExtension(...)`.
- **MIME types của nội dung kịch bản**: `getMimeTypes()`, tương ứng `getEngineByMimeType(...)`.
- **Phiên bản triển khai engine**: `getEngineVersion()`, khác với **phiên bản ngôn ngữ** từ `getLanguageVersion()`.

Đây là **khám phá khả năng runtime**, không phải việc đọc tên file JAR hoặc hỏi phiên bản JDK. Một runtime có thể không chứa engine nào, hoặc chứa nhiều implementation cùng hỗ trợ một ngôn ngữ, nhưng có phiên bản/alias/MIME khác nhau.

### Hai đối tượng có vai trò khác nhau

```text
JAR scripting engine
  └─ META-INF/services/javax.script.ScriptEngineFactory
                     │
                     ▼
         ScriptEngineManager
         phát hiện factories
                     │
       getEngineFactories()             ┌──────────────────────────────┐
                     │                  │ ScriptEngineFactory           │
                     ├─────────────────►│ getEngineName()/Version()    │
                     │                  │ getNames()/Extensions()      │
                     │                  │ getMimeTypes()               │
                     │                  │ getLanguageName()/Version()  │
                     │                  └──────────────────────────────┘
                     │
       getEngineByName / Extension / MimeType
                     │
                     ▼
          factory.getScriptEngine()
                     │
                     ▼
             ScriptEngine
             eval / bindings / context
```

**`ScriptEngineFactory`** mô tả engine và biết cách tạo engine; **`ScriptEngine`** là đối tượng thực thi script. **`ScriptEngineManager`** dùng cơ chế Java service provider để phát hiện `ScriptEngineFactory` và cung cấp các phương thức tìm theo tên/đuôi tệp/MIME. Chỉ đọc metadata qua factory thường là bước hợp lý trước khi thực sự tạo engine và đánh giá script.

## 2. API chuẩn của `ScriptEngineFactory`

| Dữ liệu cần khám phá | Phương thức | Kiểu trả về | Dùng để làm gì? |
| --- | --- | --- | --- |
| Tên implementation | `getEngineName()` | `String` | Hiển thị engine đang cài |
| Phiên bản implementation | `getEngineVersion()` | `String` | Chẩn đoán tương thích/hiển thị version |
| Tên ngắn/bí danh | `getNames()` | `List<String>` | Tìm bằng `getEngineByName(name)` |
| Phần mở rộng | `getExtensions()` | `List<String>` | Tìm bằng `getEngineByExtension(ext)` |
| MIME types | `getMimeTypes()` | `List<String>` | Tìm bằng `getEngineByMimeType(mime)` |
| Tên ngôn ngữ | `getLanguageName()` | `String` | Biết engine chạy loại ngôn ngữ nào |
| Phiên bản ngôn ngữ | `getLanguageVersion()` | `String` | Xem mức phiên bản ngôn ngữ engine hỗ trợ |
| Tham số khác | `getParameter(key)` | `Object` | Lấy metadata chuẩn hoặc dành riêng cho engine |
| Tạo engine | `getScriptEngine()` | `ScriptEngine` | Tạo/lấy instance có khả năng chạy script |

**Tên engine** không nhất thiết giống **tên ngôn ngữ**. Chẳng hạn hai implementation khác nhau có thể cùng xử lý một ngôn ngữ, nhưng có phiên bản, tính năng và độ tương thích khác nhau. `getEngineVersion()` là phiên bản **engine**, không phải `Runtime.version()`, không phải phiên bản Java, và cũng không tự bằng `getLanguageVersion()`.

Ví dụ mã **minh họa** sau khi đã có một `ScriptEngineFactory factory`:

```java
System.out.println(factory.getEngineName());
System.out.println(factory.getEngineVersion());
System.out.println(factory.getNames());
System.out.println(factory.getExtensions());
System.out.println(factory.getMimeTypes());
System.out.println(factory.getLanguageName());
System.out.println(factory.getLanguageVersion());
```

### 2.1. Các tên ngắn khác với tên đầy đủ

`getEngineName()` trả **tên đầy đủ của implementation**, còn `getNames()` trả danh sách **tên ngắn dùng để lookup**. Ví dụ một engine giả định:

```text
Engine name: Caps Demo Engine
Names: [caps, caps-demo]
```

Khi đó tên lookup được công bố là `"caps"` hoặc `"caps-demo"`. Đừng mặc định `getEngineByName(factory.getEngineName())` luôn được hỗ trợ chỉ vì tên đầy đủ xuất hiện trong metadata; hãy dùng các bí danh từ `getNames()` hoặc đăng ký alias tường minh.

Danh sách bí danh có thể chứa nhiều tên, ví dụ tên ngôn ngữ, tên sản phẩm hoặc alias tương thích. Mỗi provider tự định nghĩa danh sách; host không nên suy đoán tên như `javascript`, `python` hay `js` chắc chắn tồn tại ở mọi máy.

### 2.2. Phần mở rộng tệp được khai báo ra sao?

`getExtensions()` cung cấp danh sách extension nhận diện script mà engine hỗ trợ. Một factory có thể trả:

```text
[caps, capstxt]
```

API lookup sử dụng **phần mở rộng**, ví dụ:

```java
ScriptEngine engine = manager.getEngineByExtension("caps");
```

Đây là đoạn minh họa cần biến `manager`. Thông thường chuỗi lookup là `"caps"` **không có dấu chấm đầu**. Nếu lấy tên file `example.caps`, host phải tách extension trước; đừng truyền nguyên tên file và trông đợi manager tự phân tích.

Ví dụ với `Path filename` là path được host kiểm soát:

```java
String file = filename.getFileName().toString();
int dot = file.lastIndexOf('.');
String ext = (dot > 0 && dot < file.length() - 1)
        ? file.substring(dot + 1)
        : "";
ScriptEngine engine = ext.isEmpty()
        ? null
        : manager.getEngineByExtension(ext);
```

Đây là **mã minh họa**, chưa bao gồm import và cách xử lý file bắt đầu bằng dấu chấm, nhiều extension ghép như `tar.gz`, chữ hoa/chữ thường hoặc những quy ước tên đặc biệt. Với yêu cầu production, nên có chính sách normalization cụ thể (ví dụ cho phép alias nào, có lower-case bằng `Locale.ROOT` hay không). Đừng giả định `getEngineByExtension` luôn tự chuẩn hóa tên đầu vào.

Phần mở rộng **chỉ là một gợi ý định tuyến**. Một file mang extension `.caps` không chứng minh nội dung hợp lệ, an toàn hoặc thật sự thuộc ngôn ngữ đó.

### 2.3. MIME type nhận diện định dạng nội dung

`getMimeTypes()` trả các media types mà factory công bố, ví dụ:

```text
[text/x-caps]
```

Host có thể tra cứu:

```java
ScriptEngine engine = manager.getEngineByMimeType("text/x-caps");
```

Không tự gắn tham số `"; charset=UTF-8"` vào lookup và trông đợi API loại bỏ tham số. Nếu nhận HTTP `Content-Type` có tham số, host nên parse media type theo chuẩn rồi tra cứu phần type/subtype đã được chuẩn hóa, đồng thời vẫn kiểm tra policy nội dung.

**MIME type không phải cơ chế phát hiện ngôn ngữ bằng cách kiểm tra bytes**, cũng không phải chữ ký số của engine. API dựa vào metadata mà factory/host đăng ký. Nhiều engine có thể cùng công bố một MIME; vì vậy nên áp dụng chính sách lựa chọn xác định nếu yêu cầu tương thích hoặc bảo mật cao.

### 2.4. Engine version và language version: không dùng thay nhau

Một factory có thể công bố:

```text
Engine: Caps Demo Engine
Engine version: 1.2.3
Language: CapsLang
Language version: 1.0
```

- `getEngineVersion()`: version của implementation cụ thể, phục vụ log, compatibility matrix, chẩn đoán lỗi.
- `getLanguageVersion()`: version ngôn ngữ mà engine hỗ trợ, phục vụ lựa chọn syntax/features.
- `getLanguageName()`: tên ngôn ngữ, **không nhất thiết giống engine name**.

Version là `String` do provider định nghĩa, không có bảo đảm luôn theo SemVer. Nếu chính sách cần so version, đừng chỉ sắp thứ tự chuỗi từ điển (`"10"` so với `"2"`); cần quy tắc parse/version cụ thể theo hệ sinh thái engine đó.

### 2.5. `getParameter` và khả năng chạy đồng thời

`ScriptEngineFactory.getParameter(String key)` hỗ trợ một số khóa tiêu chuẩn:

| Key | Giá trị ý nghĩa |
| --- | --- |
| `ScriptEngine.ENGINE` | Tên engine, tương ứng `getEngineName()` |
| `ScriptEngine.ENGINE_VERSION` | Phiên bản engine |
| `ScriptEngine.NAME` | Một trong các tên ngắn từ `getNames()` |
| `ScriptEngine.LANGUAGE` | Tên ngôn ngữ |
| `ScriptEngine.LANGUAGE_VERSION` | Phiên bản ngôn ngữ |
| `"THREADING"` | Thông tin về khả năng thread safety được engine công bố |

Ví dụ:

```java
Object engineVersion = factory.getParameter(ScriptEngine.ENGINE_VERSION);
Object threading = factory.getParameter("THREADING");
```

`getParameter("THREADING")` có thể trả `null` (engine không hỗ trợ chạy script đồng thời một cách an toàn), `"MULTITHREADED"`, `"THREAD-ISOLATED"` hoặc `"STATELESS"` với các cam kết tăng dần theo JSR-223. Host không nên mặc định dùng chung `ScriptEngine` giữa nhiều request/thread khi chưa xác minh chính sách threading, cách quản lý `Bindings` và thực tế của provider. Metadata là thông tin tự khai báo; cần kiểm thử và giới hạn sử dụng khi đưa engine bên ngoài vào hệ thống.

## 3. Khám phá bằng `ScriptEngineManager`

### 3.1. Liệt kê tất cả factories hiện có

Mã minh họa cho ứng dụng Java 17+:

```java
import javax.script.ScriptEngineFactory;
import javax.script.ScriptEngineManager;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

ScriptEngineManager manager = new ScriptEngineManager();
List<ScriptEngineFactory> factories =
        new ArrayList<>(manager.getEngineFactories());

factories.sort(
    Comparator.comparing(ScriptEngineFactory::getEngineName)
              .thenComparing(ScriptEngineFactory::getEngineVersion));

for (ScriptEngineFactory f : factories) {
    System.out.println("Engine: " + f.getEngineName());
    System.out.println("Version: " + f.getEngineVersion());
    System.out.println("Aliases: " + f.getNames());
    System.out.println("Extensions: " + f.getExtensions());
    System.out.println("MIME: " + f.getMimeTypes());
    System.out.println("Language: " + f.getLanguageName()
            + " " + f.getLanguageVersion());
}
```

**Đây là đoạn minh họa đặt trong phương thức hoặc khối hợp lệ**, không phải file `.java` độc lập; ví dụ đầy đủ ở mục 6. Đoạn mã cố ý copy danh sách trước khi sort, vì danh sách do manager cung cấp không nên bị giả định là có thể sửa.

`manager.getEngineFactories()` có thể trả danh sách **trống**. Điều đó không đồng nghĩa JDK hỏng: JSR-223 là **API**, còn engine cụ thể đến từ một implementation/provider.

**Lưu ý với Java 17:** Nashorn JavaScript engine đã bị loại khỏi JDK kể từ **JDK 15**. Vì thế một chương trình Java 17 không nên mặc định rằng `new ScriptEngineManager().getEngineByName("JavaScript")` luôn khác `null`. Nếu cần JavaScript hoặc ngôn ngữ khác, phải cài một engine/provider hỗ trợ tương ứng.

### 3.2. Ba cách lấy engine dựa trên metadata

```java
ScriptEngine byName = manager.getEngineByName("caps");
ScriptEngine byExt = manager.getEngineByExtension("caps");
ScriptEngine byMime = manager.getEngineByMimeType("text/x-caps");
```

Tất cả trả về `ScriptEngine` **hoặc `null` nếu không tìm thấy engine tương ứng**. Không dùng `Optional` trực tiếp ở chữ ký API này; nếu muốn idiom rõ ràng:

```java
ScriptEngine engine = java.util.Optional.ofNullable(
        manager.getEngineByName("caps"))
    .orElseThrow(() -> new IllegalStateException(
        "Chưa cài engine có alias caps"));
```

**Đây là snippet**, chưa có `manager` và import đầy đủ. Thông báo khi thiếu engine nên nêu alias, loại script và hướng cấu hình cần thiết, thay vì ném `NullPointerException` khi gọi `eval` trên `null`.

Sự khác nhau giữa **khám phá factory** và **khởi tạo engine** rất quan trọng:

- `getEngineFactories()` liệt kê các `ScriptEngineFactory` đã được manager phát hiện. Mục tiêu là đọc metadata; không chủ động gọi `ScriptEngineFactory.getScriptEngine()`.
- `getEngineByName`/`getEngineByExtension`/`getEngineByMimeType` tìm factory theo metadata hoặc registration, rồi yêu cầu **tạo `ScriptEngine`**. Bước này có thể tốn chi phí hoặc thất bại vì implementation/dependency.
- `engine.getFactory()` trả factory của một engine đã có để truy xuất metadata; không cần tạo engine mới nếu chỉ muốn liệt kê metadata.

### 3.3. Factory được phát hiện như thế nào?

`ScriptEngineManager` sử dụng cơ chế **Java SPI/`ServiceLoader`** để tìm các class triển khai `javax.script.ScriptEngineFactory` từ nơi runtime có thể quan sát. Khi dùng **classpath JAR**, provider thường đăng ký bằng tệp:

```text
META-INF/services/javax.script.ScriptEngineFactory
```

Nội dung là một hoặc nhiều *fully qualified names* của các implementation factory, mỗi dòng một tên, ví dụ:

```text
example.engine.CapsEngineFactory
```

Tệp phải nằm **bên trong JAR/provider artifact** đúng đường dẫn. `ScriptEngineFactory` cần class implementation hợp lệ và có thể khởi tạo theo quy tắc service provider. Không đặt tên file service là `javax.script.ScriptEngine`: manager tìm **factory**, không phải engine.

`new ScriptEngineManager()` tương đương việc xây manager từ **thread context class loader (TCCL)** hiện tại. `new ScriptEngineManager(loader)` cho phép host chỉ rõ loader để khám phá. Vì vậy nếu JAR engine chỉ hiện diện trong một plugin class loader riêng mà TCCL không nhìn thấy, manager mặc định có thể không thấy factory. Host có thể truyền đúng loader hoặc quản lý discovery/registration cho layer của mình.

**Trong hệ thống module JPMS:** engine cung cấp `ScriptEngineFactory` bằng `provides javax.script.ScriptEngineFactory with ...` và dùng các quy tắc module visibility, module layer tương ứng. Không giả định một child `ModuleLayer` mới tạo tự động xuất hiện trong một `ScriptEngineManager` đã được khởi tạo từ trước. Nếu host chủ động tạo layer và cần đăng ký factories của nó, có thể khám phá qua `ServiceLoader.load(layer, ScriptEngineFactory.class)` rồi đăng ký tên, extension và MIME vào manager do host sở hữu theo chính sách. Kiểm soát class loader/API identity và vòng đời JAR/engine khi dùng lớp plugin động.

### 3.4. Đăng ký tường minh nếu cần chính sách ưu tiên

`ScriptEngineManager` có các phương thức:

```java
manager.registerEngineName("my-dsl", factory);
manager.registerEngineExtension("mydsl", factory);
manager.registerEngineMimeType("text/x-my-dsl", factory);
```

Đây là đoạn minh họa có `factory` đã được host chọn. Các đăng ký trong manager được ưu tiên khi lookup theo key tương ứng, hữu ích nếu nhiều provider công bố cùng alias/extension/MIME. Chúng là **mapping của manager cụ thể**, không ghi lại SPI descriptor và không cấu hình hệ thống toàn cục.

Điểm cần nhớ: `getEngineFactories()` là danh sách factories lấy từ **discovery mechanism**. Một factory chỉ được thêm thông qua `registerEngineName/Extension/MimeType` không nhất thiết xuất hiện trong danh sách ấy; lookup và enumeration không có nghĩa phải cùng một tập sau khi đăng ký tường minh.

## 4. Chọn engine khi nhiều provider trùng metadata

Giả sử có hai factories cùng công bố alias `"script"` và extension `"sc"`. `getEngineByName("script")` có thể tìm được một engine, nhưng **không đủ thông tin** để chứng minh engine đó có đúng version hoặc tính năng host yêu cầu. Không dựa vào thứ tự `getEngineFactories()` hay `findFirst()` trong trường hợp cần lựa chọn xác định.

Quy trình robust:

1. **Liệt kê và ghi metadata** của từng factory, cùng nguồn artifact/loader nếu host quản lý được.
2. **Lọc theo ngôn ngữ, tên engine, version/capability** và yêu cầu dự án; không dùng một alias mơ hồ làm tiêu chí duy nhất.
3. **Kiểm tra trùng tên và xung đột** alias, MIME, extension. Chọn hoặc từ chối theo policy có chủ ý.
4. **Kiểm tra dependency, mức độ tin cậy và compatibility** trước khi gọi factory tạo engine.
5. **Tạo engine từ factory đã chọn** bằng `selectedFactory.getScriptEngine()` hoặc đăng ký mapping tường minh cho manager.
6. **Validate script đầu vào, tài nguyên và giới hạn thực thi**; metadata không chứng minh mã script an toàn.

Snippet minh họa lựa chọn tường minh theo tên và version:

```java
ScriptEngineFactory chosen = manager.getEngineFactories().stream()
    .filter(f -> f.getEngineName().equals("Caps Demo Engine"))
    .filter(f -> f.getEngineVersion().equals("1.2.3"))
    .findFirst()
    .orElseThrow(() -> new IllegalStateException(
        "Không tìm thấy engine/version yêu cầu"));

ScriptEngine engine = chosen.getScriptEngine();
```

Đây là **mã minh họa**, không phải chương trình độc lập. So sánh version bằng bằng-chuỗi ở đây phù hợp vì yêu cầu **đúng version cụ thể**; nếu muốn version range, dùng bộ so version được định nghĩa riêng, không so sánh lexicographic.

### Ma trận ý nghĩa của lookup

| Đầu vào đang có | Lựa chọn API | Lưu ý |
| --- | --- | --- |
| Alias đã quy ước trong cấu hình | `getEngineByName(alias)` | Dùng tên từ `getNames()`/registration |
| Tệp `job.caps` | `getEngineByExtension("caps")` | Tách và chuẩn hóa extension trước; không dùng nguyên `job.caps` |
| MIME `text/x-caps` | `getEngineByMimeType("text/x-caps")` | Đừng nhầm MIME với kiểm tra nội dung |
| Cần ghi danh mục engine/version | `getEngineFactories()` | Đọc metadata, không buộc tạo engine |
| Cần một implementation/version xác định | Lọc `ScriptEngineFactory` rồi `getScriptEngine()` | Chính sách lựa chọn do host quyết định |
| Cần override xung đột alias | `registerEngineName/Extension/MimeType` | Mapping riêng trong manager |

## 5. Ví dụ Java 17+ chạy được, không phụ thuộc vào engine có sẵn của JDK

Để thấy chính xác các trường metadata trong một môi trường có thể tái lập, ta viết một **engine minh họa rất nhỏ** cho ngôn ngữ giả lập `CapsLang`. Nó chỉ hiểu lệnh `upper <text>` (trả về chữ hoa) và `print <text>` (ghi ra `ScriptContext.getWriter()`). Mục đích là học **discovery/metadata qua JSR-223**, không phải xây ngôn ngữ lập trình hoàn chỉnh.

Có ba file Java và một SPI descriptor. Host không import implementation engine; nó chỉ dùng `javax.script`. Engine được đóng thành một JAR riêng và xuất hiện khi đưa JAR đó vào classpath runtime.

### 5.1. Cấu trúc thư mục

```text
demo/
├── src/
│   ├── host/
│   │   └── EngineProbe.java
│   └── example/
│       └── engine/
│           ├── CapsEngineFactory.java
│           └── CapsEngine.java
├── resources/
│   └── META-INF/
│       └── services/
│           └── javax.script.ScriptEngineFactory
└── build/                    # sẽ tạo khi biên dịch
```

### 5.2. Factory công bố tên, phần mở rộng, MIME và version

**`src/example/engine/CapsEngineFactory.java`**

```java
package example.engine;

import java.util.List;
import javax.script.ScriptEngine;
import javax.script.ScriptEngineFactory;

public final class CapsEngineFactory implements ScriptEngineFactory {
    @Override
    public String getEngineName() {
        return "Caps Demo Engine";
    }

    @Override
    public String getEngineVersion() {
        return "1.2.3";
    }

    @Override
    public List<String> getExtensions() {
        return List.of("caps");
    }

    @Override
    public List<String> getMimeTypes() {
        return List.of("text/x-caps");
    }

    @Override
    public List<String> getNames() {
        return List.of("caps", "caps-demo");
    }

    @Override
    public String getLanguageName() {
        return "CapsLang";
    }

    @Override
    public String getLanguageVersion() {
        return "1.0";
    }

    @Override
    public Object getParameter(String key) {
        return switch (key) {
            case ScriptEngine.ENGINE -> getEngineName();
            case ScriptEngine.ENGINE_VERSION -> getEngineVersion();
            case ScriptEngine.NAME -> getNames().get(0);
            case ScriptEngine.LANGUAGE -> getLanguageName();
            case ScriptEngine.LANGUAGE_VERSION -> getLanguageVersion();
            case "THREADING" -> null; // Không tuyên bố thread-safe.
            default -> null;
        };
    }

    @Override
    public String getMethodCallSyntax(
            String obj, String method, String... args) {
        throw new UnsupportedOperationException(
            "CapsLang does not support Java method calls");
    }

    @Override
    public String getOutputStatement(String toDisplay) {
        return "print " + toDisplay;
    }

    @Override
    public String getProgram(String... statements) {
        return String.join("\n", statements);
    }

    @Override
    public ScriptEngine getScriptEngine() {
        return new CapsEngine(this);
    }
}
```

Các trường quan trọng là `getEngineName()`, `getNames()`, `getExtensions()`, `getMimeTypes()`, `getEngineVersion()`. Với API JSR-223, factory cũng phải triển khai các phương thức còn lại, kể cả `getLanguageName()`, `getLanguageVersion()`, `getParameter()` và `getScriptEngine()`.

`List.of(...)` trả danh sách không thể thay đổi; phù hợp hợp đồng metadata. `getParameter("THREADING") == null` thể hiện engine này **không cam kết thread-safe**. `getMethodCallSyntax` từ chối một khả năng mà DSL đơn giản này không hỗ trợ; đây là **giới hạn rõ ràng của engine mô phỏng**, không phải một cú pháp Java method call đầy đủ.

### 5.3. Engine demo với `eval` tối thiểu

**`src/example/engine/CapsEngine.java`**

```java
package example.engine;

import java.io.IOException;
import java.io.Reader;
import java.io.StringWriter;
import java.util.Locale;
import javax.script.AbstractScriptEngine;
import javax.script.Bindings;
import javax.script.ScriptContext;
import javax.script.ScriptEngineFactory;
import javax.script.ScriptException;
import javax.script.SimpleBindings;

final class CapsEngine extends AbstractScriptEngine {
    private final CapsEngineFactory factory;

    CapsEngine(CapsEngineFactory factory) {
        this.factory = factory;
    }

    @Override
    public Object eval(String script, ScriptContext context)
            throws ScriptException {
        Object result = null;

        for (String line : script.split("\\R")) {
            if (line.isBlank()) {
                continue;
            }
            if (line.startsWith("upper ")) {
                result = line.substring(6).toUpperCase(Locale.ROOT);
            } else if (line.startsWith("print ")) {
                try {
                    context.getWriter().write(line.substring(6));
                    context.getWriter().write(System.lineSeparator());
                    context.getWriter().flush();
                } catch (IOException error) {
                    throw new ScriptException(error);
                }
                result = null;
            } else {
                throw new ScriptException(
                    "Unsupported statement: " + line);
            }
        }
        return result;
    }

    @Override
    public Object eval(Reader reader, ScriptContext context)
            throws ScriptException {
        try {
            StringWriter buffer = new StringWriter();
            reader.transferTo(buffer);
            return eval(buffer.toString(), context);
        } catch (IOException error) {
            throw new ScriptException(error);
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

`AbstractScriptEngine` đã cài đặt nhiều overload của `eval` và quản lý `ScriptContext`/`Bindings` thông thường. Ví dụ chỉ cần thực hiện các abstract methods yêu cầu. `Reader.transferTo` và switch expression được hỗ trợ bởi JDK 17.

Chương trình này **không** phân tích cú pháp phức tạp, không thực thi JavaScript và không cung cấp sandbox. Nó chỉ đủ để chứng minh factory tạo ra một `ScriptEngine` dùng được, sau khi được khám phá.

### 5.4. Ứng dụng host: liệt kê và lookup theo ba metadata

**`src/host/EngineProbe.java`**

```java
package host;

import java.util.List;
import javax.script.ScriptEngine;
import javax.script.ScriptEngineFactory;
import javax.script.ScriptEngineManager;
import javax.script.ScriptException;

public final class EngineProbe {
    public static void main(String[] args) throws ScriptException {
        ScriptEngineManager manager = new ScriptEngineManager();

        // Discovery: chưa cần chạy script để đọc metadata.
        List<ScriptEngineFactory> factories =
            manager.getEngineFactories();

        ScriptEngineFactory factory = factories.stream()
            .filter(f -> f.getNames().contains("caps"))
            .findFirst()
            .orElseThrow(() -> new IllegalStateException(
                "Caps engine factory not discovered"));

        System.out.println("Engine: " + factory.getEngineName());
        System.out.println("Engine version: " + factory.getEngineVersion());
        System.out.println("Names: " + factory.getNames());
        System.out.println("Extensions: " + factory.getExtensions());
        System.out.println("MIME: " + factory.getMimeTypes());
        System.out.println("Language: " + factory.getLanguageName());
        System.out.println("Language version: "
                + factory.getLanguageVersion());
        System.out.println("THREADING: "
                + factory.getParameter("THREADING"));

        ScriptEngine byName = manager.getEngineByName("caps");
        ScriptEngine byExt = manager.getEngineByExtension("caps");
        ScriptEngine byMime =
            manager.getEngineByMimeType("text/x-caps");

        System.out.println("By name: " + (byName != null));
        System.out.println("By extension: " + (byExt != null));
        System.out.println("By MIME: " + (byMime != null));

        if (byName == null) {
            throw new IllegalStateException(
                "Provider found but engine not created");
        }
        System.out.println("Eval: " + byName.eval("upper Java Script"));
    }
}
```

Mã này không import bất cứ class nào từ package `example.engine`. Nó dùng đúng API chuẩn của host; factory được tìm thông qua SPI và các phương thức lookup dựa trên metadata mà factory công bố.

Vì `getEngineFactories()` có thể có factory khác khi runtime bổ sung JAR, `EngineProbe` lọc theo tên ngắn `caps` thay vì giả định số lượng factory luôn bằng 1. Trong môi trường demo theo lệnh classpath bên dưới, chỉ cần engine JAR được cung cấp đủ để chạy.

### 5.5. SPI descriptor cho factory

**`resources/META-INF/services/javax.script.ScriptEngineFactory`**

```text
example.engine.CapsEngineFactory
```

Tên file phải khớp **`javax.script.ScriptEngineFactory`**, không phải `javax.script.ScriptEngine`. Nội dung phải là fully qualified class name của factory public và có constructor không tham số được `ServiceLoader` tạo được. Trong ví dụ `CapsEngineFactory` không khai báo constructor, nên Java tạo default public no-arg constructor cho public class.

### 5.6. Biên dịch và chạy với Windows PowerShell

Từ thư mục `demo`, bảo đảm `java`, `javac` và `jar` thuộc JDK 17+ đang nằm trong `PATH`:

```powershell
New-Item -ItemType Directory -Force build/host, build/engine | Out-Null

# Host biên dịch độc lập, chỉ phụ thuộc javax.script.
javac -encoding UTF-8 -d build/host src/host/EngineProbe.java

# Provider được biên dịch riêng, dựa trên API JDK.
javac -encoding UTF-8 -d build/engine src/example/engine/CapsEngineFactory.java src/example/engine/CapsEngine.java

# Đưa descriptor SPI vào JAR provider.
New-Item -ItemType Directory -Force build/engine/META-INF/services | Out-Null
Copy-Item resources/META-INF/services/javax.script.ScriptEngineFactory build/engine/META-INF/services/javax.script.ScriptEngineFactory

jar --create --file build/caps-engine.jar -C build/engine .

# Trên Windows, dấu ; ngăn cách các phần tử classpath.
java -cp 'build/host;build/caps-engine.jar' host.EngineProbe
```

**Stdout chính xác của demo với JDK 17+ và classpath vừa tạo:**

```text
Engine: Caps Demo Engine
Engine version: 1.2.3
Names: [caps, caps-demo]
Extensions: [caps]
MIME: [text/x-caps]
Language: CapsLang
Language version: 1.0
THREADING: null
By name: true
By extension: true
By MIME: true
Eval: JAVA SCRIPT
```

Những dòng từ `Engine:` đến `THREADING:` là dữ liệu do factory công bố. Ba kết quả `true` cho thấy manager đã ánh xạ alias, extension và MIME đúng tới một `ScriptEngine`. Dòng `Eval: JAVA SCRIPT` là kết quả thực thi DSL tối thiểu, không phải một JavaScript engine.

**Nếu bỏ JAR engine khỏi classpath** rồi chạy `java -cp build/host host.EngineProbe`, trong môi trường chỉ có JDK 17 chuẩn và không cài engine khác, chương trình ném `IllegalStateException` với thông điệp `Caps engine factory not discovered`. Đó là hành vi host cố ý thiết kế khi không tìm thấy provider; JSR-223 không tự cài engine giúp bạn.

Trên Linux/macOS, dùng `mkdir -p` thay `New-Item`, `cp` thay `Copy-Item`, và dấu `:` để ghép classpath, chẳng hạn:

```bash
java -cp 'build/host:build/caps-engine.jar' host.EngineProbe
```

Lệnh trên chạy sau khi đã biên dịch và đóng JAR theo cách tương đương trên hệ điều hành của bạn.

### 5.7. Thử API `getParameter` và bí danh khác

Trong `EngineProbe`, có thể thử thêm các dòng sau (đoạn **minh họa** đặt sau khi lấy `factory`):

```java
System.out.println(factory.getParameter(ScriptEngine.ENGINE));
System.out.println(factory.getParameter(ScriptEngine.ENGINE_VERSION));
System.out.println(factory.getParameter(ScriptEngine.LANGUAGE_VERSION));

ScriptEngine sameFamily = manager.getEngineByName("caps-demo");
System.out.println(sameFamily != null);
```

Kết quả lần lượt là `Caps Demo Engine`, `1.2.3`, `1.0` và `true`. Đây là **các lookup/đối tượng engine mới được tạo** theo metadata; `sameFamily` không nhất thiết là cùng instance với `byName`. Không mặc định `getEngineByName` trả singleton hoặc engine mới luôn được chia sẻ trạng thái với engine trước.

## 6. Đưa ví dụ vào hệ thống plugin và module runtime

### 6.1. Classpath discovery không phải dependency resolver

Ví dụ demo chạy nhờ JAR provider có descriptor SPI. Host vẫn cần:

- Cung cấp JAR và các dependency hợp lệ trong runtime classpath/module environment.
- Giữ API `javax.script`/provider version tương thích.
- Chỉ định class loader phù hợp nếu plugin được nạp động.
- Kiểm soát lifecycle engine, script context, bindings, thời gian chạy, tài nguyên và quyền truy cập.

`ScriptEngineManager` tìm factory; nó **không tải thiếu dependency từ Maven**, không khởi động mọi module/plugin theo dependency graph và không giới hạn quyền của script.

### 6.2. JPMS và `ModuleLayer`

Nếu provider được triển khai thành named module, descriptor có thể là (chỉ là **đoạn minh họa**):

```java
module caps.engine {
    requires java.scripting;
    provides javax.script.ScriptEngineFactory
        with example.engine.CapsEngineFactory;
}
```

Khi host tạo child `ModuleLayer` lúc chạy, cần xác định rõ factory được tìm qua layer nào. Một hướng tiếp cận là:

```java
ServiceLoader<ScriptEngineFactory> factories =
        ServiceLoader.load(layer, ScriptEngineFactory.class);

for (ScriptEngineFactory f : factories) {
    for (String name : f.getNames()) {
        manager.registerEngineName(name, f);
    }
    for (String ext : f.getExtensions()) {
        manager.registerEngineExtension(ext, f);
    }
    for (String mime : f.getMimeTypes()) {
        manager.registerEngineMimeType(mime, f);
    }
}
```

Đây là **mã minh họa không độc lập**: host phải có `layer` đã được định nghĩa hợp lệ, `manager` do mình quản lý và import tương ứng. Cần quy tắc xử lý trùng metadata và version; không đăng ký mù quáng mọi factory nếu có engine không tin cậy. Việc tạo/làm mới layer không tự thay đổi manager cũ.

### 6.3. Engine metadata khác với kiểm tra khả năng thật

Việc factory công bố `getExtensions()=[caps]` chưa chứng minh engine xử lý tất cả file `.caps`, hỗ trợ mọi phiên bản syntax hoặc phù hợp với chính sách sandbox. Host nên thử một tập script chuẩn, xử lý `ScriptException`, kiểm tra timeout/memory và đo kết quả thực tế.

Đặc biệt, **engine chạy script có thể thực thi mã với quyền của tiến trình**. Metadata MIME/name/version **không cấp bảo mật**. Không nhận file đính kèm hay script của người dùng không tin cậy rồi cho `engine.eval(...)` với toàn quyền trên host mà không có mô hình cô lập chặt chẽ (thường là process riêng với quyền OS hạn chế, giới hạn tài nguyên và network).

### 6.4. Cấu hình version và tương thích

Khi host có yêu cầu cụ thể, hãy lưu đầy đủ “engine implementation + engine version + language version + source artifact” trong log/diagnostics. Xây compatibility matrix theo tính năng thực tế, thay vì chỉ dựa trên tên ngôn ngữ. Khi nâng cấp JDK, engine provider có thể được thêm/bớt độc lập với API `java.scripting`.

Với Java 17, việc không còn Nashorn trong JDK là ví dụ điển hình: `javax.script` vẫn tồn tại, nhưng `getEngineFactories()` có thể rỗng nếu không cài engine. Sự hiện diện của package `javax.script` **không đồng nghĩa** JavaScript engine đã được phân phối cùng JDK.

## 7. Những nhầm lẫn thường gặp và cách sửa

| Triệu chứng | Nguyên nhân dễ gặp | Cách kiểm tra/sửa |
| --- | --- | --- |
| `getEngineFactories()` rỗng | Runtime không có ScriptEngineFactory provider, thiếu JAR hoặc không đúng loader | Xem runtime classpath/module path, SPI descriptor và TCCL |
| `getEngineByName("JavaScript")` trả `null` trên Java 17 | JDK không còn tích hợp Nashorn | Cài engine JS tương thích, không dựa vào JDK mặc định |
| Engine có tên đầy đủ nhưng `getEngineByName(fullName)` không thấy | Lookup dùng alias `getNames()`, không nhất thiết engine name đầy đủ | In `getNames()` và lookup bằng tên được công bố |
| `getEngineByExtension(".caps")` không thấy | Factory khai báo `caps` không có dấu chấm | Tách extension từ filename, dùng `caps` |
| `getEngineByMimeType("text/x-caps; charset=UTF-8")` không thấy | Lookup dựa trên MIME được đăng ký, không hứa tự parse tham số | Parse/chuẩn hóa media type trước |
| ScriptEngineFactory xuất hiện nhưng lookup không tạo engine được | `getScriptEngine()` lỗi hoặc dependency thiếu | Chẩn đoán tạo engine và nguyên nhân gốc |
| `getEngineVersion()` không bằng version ngôn ngữ | Hai API mô tả hai hệ version khác nhau | In cả engine version và language version |
| Môi trường A thấy engine, B không thấy | Class loader/module layer/classpath khác nhau | Chỉ rõ loader cho `ScriptEngineManager`, kiểm tra SPI |
| Có nhiều engine cùng alias và chọn sai | Không có chính sách chọn implementation/version | Lọc factory, đăng ký mapping tường minh, kiểm tra xung đột |
| Đã thay JAR nhưng manager vẫn dùng engine cũ | Factory/loader/engine instance cũ còn tồn tại | Quản lý class loader và instance mới, refresh manager theo lifecycle |
| Dùng chung một engine giữa threads rồi sai trạng thái | Bỏ qua metadata `THREADING` và ràng buộc `Bindings` | Kiểm tra tài liệu engine, cô lập instance/context, đồng bộ nếu cần |
| Chọn engine bằng extension của file tải lên rồi eval ngay | Tin nhầm tên file/MIME là chứng nhận an toàn | Kiểm tra nội dung, nguồn, quyền, giới hạn thời gian/tài nguyên |

### Ba lỗi tư duy cần tránh

**1. Tên, extension và MIME không phải cùng một thứ.** Chúng là ba *khóa tra cứu* khác nhau, do factory công bố. Một engine có thể hỗ trợ nhiều bí danh, nhiều extensions, nhiều MIME types.

**2. “Engine được tìm thấy” khác “engine được tạo/chạy thành công”.** Liệt kê `ScriptEngineFactory` là bước khám phá; tạo `ScriptEngine` và thực thi `eval` là những bước có thể phát sinh lỗi hoặc side effects riêng.

**3. Engine version không phải JDK version.** Phiên bản `java.scripting` API theo nền tảng Java, nhưng implementation JSR-223 có vòng đời và version riêng.

## 8. Checklist trước khi dùng engine nhúng trong production

- [ ] Liệt kê các `ScriptEngineFactory` hiện có và ghi rõ engine name/version, names, extensions, MIME types, language name/version.
- [ ] Tách lookup theo alias, extension hoặc MIME đúng nguồn dữ liệu; chuẩn hóa input theo policy của ứng dụng.
- [ ] Không giả định Java 17 có sẵn JavaScript/Nashorn engine.
- [ ] Đảm bảo provider JAR được đóng đúng `META-INF/services/javax.script.ScriptEngineFactory` hoặc descriptor JPMS.
- [ ] Xác định đúng class loader/module layer để khám phá provider động.
- [ ] Khi trùng alias/MIME/extension, lựa chọn implementation/version tường minh; không dựa vào thứ tự factories.
- [ ] Phân biệt `null` do không tìm thấy với lỗi khi factory tạo engine và lỗi `ScriptException` lúc chạy.
- [ ] Kiểm tra version/capabilities thật, chứ không chỉ tin metadata.
- [ ] Không đánh giá script không tin cậy trong cùng tiến trình không được cô lập; giới hạn quyền, tài nguyên, network và thời gian thực thi.
- [ ] Dùng `Bindings`/`ScriptContext` phù hợp, chú ý trạng thái chia sẻ và metadata `THREADING`.
- [ ] Có chính sách lifecycle khi cập nhật engine/provider JAR: reload discovery, chuyển instance và cleanup đúng cách.

**Kết luận:** `ScriptEngineManager` giúp host **khám phá và chọn** engine; `ScriptEngineFactory` cung cấp **tên/alias, phần mở rộng, MIME, engine version và language version**; `ScriptEngine` dùng để **thực thi script** sau khi đã chọn. Dựa vào metadata để khám phá, nhưng dựa vào kiểm tra tương thích và chính sách bảo mật để quyết định engine nào được chạy.

**Tài liệu chính thức:**

- [`ScriptEngineFactory` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptEngineFactory.html).
- [`ScriptEngineManager` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptEngineManager.html).
- [`AbstractScriptEngine` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/AbstractScriptEngine.html).
- [Oracle JDK 17 Migration Guide — Nashorn removed in JDK 15](https://docs.oracle.com/en/java/javase/17/migrate/removed-tools-and-components.html).

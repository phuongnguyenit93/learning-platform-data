# 17.1. Vai trò của `javax.script` và quan hệ giữa API với script engine

Trong Java, **`javax.script` là giao diện lập trình để nhúng ngôn ngữ kịch bản vào ứng dụng Java**, không phải bản thân một trình thông dịch JavaScript, Python hoặc Groovy. Bộ API này thuộc **module chuẩn `java.scripting`** và được biết đến với tên **Scripting API / JSR 223**. Nó chuẩn hóa cách ứng dụng *tìm engine, gửi script, truyền biến, nhận kết quả và xử lý lỗi* mà không cần gắn chặt toàn bộ mã gọi với API riêng của từng ngôn ngữ.

Để **thực thi** một script cụ thể, ứng dụng còn cần **script engine implementation** tương thích: engine hiểu cú pháp/ngữ nghĩa của ngôn ngữ và thực sự chạy mã. `ScriptEngineManager` có thể tìm hoặc nhận đăng ký engine qua `ScriptEngineFactory`, nhưng **không tự thông dịch mọi ngôn ngữ**.

Điểm thực tế khi học với **Java 17+**: Nashorn JavaScript engine đã bị **loại khỏi JDK từ Java 15 (JEP 372)**. Vì vậy dù `import javax.script.*` biên dịch bình thường, `new ScriptEngineManager().getEngineByName("JavaScript")` **có thể trả `null`** nếu ứng dụng không cung cấp engine ngoài. Không thể dùng `eval` trên một engine không tồn tại.

Sau bài này, bạn có thể phân biệt chính xác API, manager, factory, engine; biết hai cách đăng ký/tìm engine; hiểu `Bindings` và `ScriptContext`; thực thi ví dụ **Java 17 chạy được không cần thêm thư viện**; nhận biết vì sao môi trường không có JavaScript engine và cách bổ sung provider phù hợp.

## 1. Bức tranh toàn cảnh: API là hợp đồng, engine là implementation

```text
                      Ứng dụng Java
                           |
                           | gọi API trung lập ngôn ngữ
                           v
                     javax.script
       +-------------------+------------------+
       | ScriptEngineManager                   |
       | - tìm/đăng ký ScriptEngineFactory     |
       | - cấp Global Bindings cho engine      |
       +-------------------+------------------+
                           |
                           | chọn factory qua tên/extension/MIME
                           v
       +--------------------------------------+
       | ScriptEngineFactory                   |
       | - metadata: language, version, names  |
       | - tạo ScriptEngine instance           |
       +-------------------+------------------+
                           |
                           v
       +--------------------------------------+
       | ScriptEngine implementation           |
       | - parse/interpret/compile script      |
       | - thực thi, trả Object/ScriptException |
       | - sử dụng Bindings và ScriptContext   |
       +-------------------+------------------+
                           |
                           v
               Ngữ nghĩa ngôn ngữ thực tế
         (MiniDSL, JavaScript, Groovy, ...)
```

Hãy phân chia **trách nhiệm**, không chỉ học tên class:

| Thành phần | Ai cung cấp? | Làm gì? | Không tự đảm bảo điều gì? |
| --- | --- | --- | --- |
| `javax.script` | JDK, module `java.scripting` | Interface/base classes chung cho script engine | Không đi kèm sẵn parser/runtime cho mọi ngôn ngữ |
| `ScriptEngineManager` | API chuẩn JDK | Discovery, factory lookup, tạo engine, quản lý global bindings | Không biên dịch hoặc chạy script thay engine |
| `ScriptEngineFactory` | **Nhà cung cấp engine** | Cho biết tên ngôn ngữ, MIME/extension, phiên bản, tạo engine | Không nhất thiết tự thực thi script |
| `ScriptEngine` | **Nhà cung cấp engine** | `eval` source, biến, context, error | Không nhất thiết hỗ trợ compile/invoke, isolation hay thread safety |
| `Bindings` | API chuẩn, caller/engine | Map tên biến → object Java | Không ép mọi ngôn ngữ ánh xạ biến giống nhau |
| `ScriptContext` | API chuẩn, caller/engine | Quản lý scopes và reader/writer/errorWriter | Không phải sandbox bảo mật |
| `ScriptException` | API chuẩn, engine ném khi xử lý script | Chuyển lỗi script qua biên giới Java | Không đồng nghĩa mọi lỗi runtime đều được chuyển thành cùng kiểu |

**Ví dụ tương tự:** `java.sql` định nghĩa API JDBC, nhưng để giao tiếp với một DB cụ thể thường cần JDBC driver. `javax.script` định nghĩa khả năng nhúng script, nhưng để chạy một ngôn ngữ cụ thể cần engine tương thích. Tương tự không có nghĩa hai API dùng cùng kiểu discovery hoặc mô hình transaction.

### 1.1. `javax.script` nằm ở đâu?

Trong JDK 17, các kiểu như `ScriptEngine`, `ScriptEngineManager`, `ScriptEngineFactory`, `Bindings`, `ScriptContext` và `ScriptException` nằm trong **package `javax.script`**, thuộc **module `java.scripting`**.

Tên package bắt đầu bằng `javax` là **tên chuẩn của Java SE**, không có nghĩa đây là một engine bên thứ ba cần tải. Nó cũng không phải `jakarta.script`. Với ứng dụng chạy trên classpath truyền thống, module chuẩn thường được resolve để sử dụng. Với **named module**, khai báo rõ dependency:

```java
module my.scripting.app {
    requires java.scripting;
}
```

Đoạn `module-info.java` này là minh họa: tên module ứng dụng do dự án tự chọn. Việc thêm `requires java.scripting` cho phép **gọi API**, nhưng vẫn **không tạo ra một JavaScript engine provider**.

### 1.2. `eval` là giao ước, không phải một cú pháp thống nhất

Lệnh Java:

```java
Object value = engine.eval(scriptSource);
```

có cấu trúc chung bất kể engine. Nhưng ý nghĩa của `scriptSource` phụ thuộc **ngôn ngữ mà engine hỗ trợ**. Với engine JavaScript, một biểu thức có thể dùng cú pháp JavaScript; với engine Groovy, đó là cú pháp Groovy; với MiniDSL trong ví dụ dưới đây, đó là lệnh `upper:name`. Không có cam kết rằng `eval("1 + 2")` luôn hợp lệ hoặc có cùng kiểu/kết quả ở mọi `ScriptEngine`.

Phần giao tiếp bằng `Object` cũng không nói rõ liệu một giá trị script được trả về là `Integer`, `Double`, `BigDecimal`, một object đặc trưng của engine hay `null`. Hãy xác định contract của **engine thực tế** và chuyển đổi kết quả có kiểm tra.

## 2. `ScriptEngineManager`: tìm engine hoặc đăng ký factory

Khởi tạo phổ biến:

```java
import javax.script.ScriptEngineManager;

ScriptEngineManager manager = new ScriptEngineManager();
```

Constructor mặc định dựa trên **thread context class loader** để tìm các triển khai `ScriptEngineFactory` bằng cơ chế service provider. Nó có thể tìm engine do JDK/vendor, ứng dụng, thư viện hoặc module cung cấp tùy classpath/module path và loader visibility.

Các phương thức quan trọng:

| API | Ý nghĩa |
| --- | --- |
| `getEngineFactories()` | Liệt kê **các factories được khám phá qua discovery** |
| `getEngineByName("...")` | Tìm theo tên/alias engine, rồi dùng factory tạo `ScriptEngine` |
| `getEngineByExtension("...")` | Tìm theo extension tên file, ví dụ `"mini"` |
| `getEngineByMimeType("...")` | Tìm theo MIME type, ví dụ `"text/x-mini"` |
| `registerEngineName(name, factory)` | Đăng ký mapping name → factory trên manager cụ thể |
| `registerEngineExtension(ext, factory)` | Đăng ký extension → factory |
| `registerEngineMimeType(mime, factory)` | Đăng ký MIME → factory |
| `put(key, value)` / `get(key)` | Quản lý map biến trong **global scope** của manager |
| `getBindings()` / `setBindings(bindings)` | Đọc hoặc thay map global scope |

Lưu ý: **`getEngineFactories()` là danh sách factories được discovery**, không nhất thiết liệt kê những factory bạn chỉ **đăng ký bằng `registerEngineName`** sau khi tạo manager. Registration là một **bảng ánh xạ lookup**, không biến factory thành một provider JAR đã được ServiceLoader tự tìm.

### 2.1. Không tìm thấy engine thì trả `null`

```java
ScriptEngineManager manager = new ScriptEngineManager();
ScriptEngine js = manager.getEngineByName("JavaScript");

if (js == null) {
    System.out.println("Không có JavaScript ScriptEngine provider khả dụng.");
} else {
    System.out.println("Đã tìm được: " + js.getFactory().getEngineName());
}
```

Đây là **đoạn ví dụ phụ thuộc môi trường**, không có stdout cố định: việc tìm thấy engine phụ thuộc dependencies/provider/class loader. `getEngineByName` **không tải tự động một thư viện từ Internet**, không có fallback tự động sang một ngôn ngữ khác, và `null` có nghĩa không có factory phù hợp hoặc không tạo được engine theo cơ chế hiện tại. Không nên lập tức gọi `js.eval(...)` trước khi kiểm tra `js != null`.

Nếu không có provider, `manager.getEngineFactories()` có thể là danh sách rỗng. Đây là trạng thái hoàn toàn hợp lệ của API và không chứng minh module `java.scripting` bị thiếu.

### 2.2. Java 17: Nashorn không còn được bundle

Lịch sử liên quan trực tiếp:

- **Java 6:** Scripting API (JSR 223) có sẵn trong Java SE.
- **Java 8:** Oracle/OpenJDK tích hợp Nashorn JavaScript engine, thường cho phép tìm `"JavaScript"`/`"nashorn"` trong môi trường tương ứng.
- **Java 11:** Nashorn bị đánh dấu *deprecated for removal*.
- **Java 15:** JEP 372 **loại bỏ Nashorn JavaScript engine và `jjs`**, nhưng **không loại bỏ `javax.script`/`java.scripting`**.
- **Java 17+:** `javax.script` vẫn là API chuẩn; để chạy JavaScript, cần thêm một engine tương thích được cài và đăng ký/khám phá đúng cách. Không đảm bảo mọi engine JavaScript ngoài đều dùng alias `"JavaScript"`.

Như vậy, câu “Java 17 không còn `javax.script`” **sai**; câu đúng là “Java 17 không còn Nashorn mặc định trong JDK chuẩn”. Một ứng dụng dùng thư viện bên thứ ba vẫn có thể tìm `ScriptEngine` cho JavaScript, Groovy hoặc ngôn ngữ khác.

**Chú ý:** CLI `jrunscript` và các ví dụ cũ chạy Nashorn không chứng minh có engine JavaScript được cung cấp ở runtime hiện tại. Công cụ gọi qua Scripting API cũng cần provider.

## 3. Engine được khám phá như thế nào? `ScriptEngineFactory` và SPI

Factory đóng vai trò **cầu nối** giữa tên ngôn ngữ/cơ chế khám phá và đối tượng engine thật. Nó cung cấp metadata:

- `getEngineName()`, `getEngineVersion()` — tên và phiên bản implementation.
- `getLanguageName()`, `getLanguageVersion()` — ngôn ngữ mà engine xử lý.
- `getNames()` — những alias mà manager có thể dùng để tìm.
- `getExtensions()` / `getMimeTypes()` — các mapping khác cho scripts.
- `getScriptEngine()` — tạo engine instance.
- `getParameter(key)`, `getMethodCallSyntax`, `getOutputStatement`, `getProgram` — metadata/cú pháp tùy năng lực engine.

Một class **chỉ** implements `ScriptEngine` mà không có factory/provider phù hợp **không tự xuất hiện** trong `new ScriptEngineManager().getEngineFactories()`. Có hai đường phổ biến:

**Đường A — đăng ký trong chương trình:** Bạn đã có một `ScriptEngineFactory` và chủ động gọi `manager.registerEngineName(...)`. Đây là cách ví dụ độc lập ở mục 6 hoạt động; không cần tạo JAR provider.

**Đường B — service provider discovery:** Đóng gói factory trong JAR/module và khai báo nó cho `ServiceLoader`. Manager mới có thể tự khám phá factory nếu provider ở classpath/module path và class loader/module resolution phù hợp.

### 3.1. Classpath: file `META-INF/services`

Trong một JAR classpath, tên file service descriptor là:

```text
META-INF/services/javax.script.ScriptEngineFactory
```

Nội dung file là **tên binary của class** implements `ScriptEngineFactory`, mỗi provider một dòng, ví dụ:

```text
com.example.scripting.MyLanguageEngineFactory
```

Provider class cần đáp ứng quy tắc của `ServiceLoader`, bao gồm khả năng khởi tạo theo cơ chế provider class thích hợp, visibility và dependencies hợp lệ. **Chỉ thêm tên file** mà không có bytecode factory và runtime implementation sẽ không giúp manager tạo engine.

### 3.2. Named module: `provides ... with ...`

Trong Java modules, provider có thể khai báo:

```java
module my.mini.engine {
    requires java.scripting;
    provides javax.script.ScriptEngineFactory
        with com.example.scripting.MyLanguageEngineFactory;
}
```

Đây là **mẫu `module-info.java`**, không phải một project runnable vì cần tạo class provider thật và cấu hình module resolution. Ứng dụng có module riêng cần `requires java.scripting` để dùng API; provider cần được đặt trên module path/resolve phù hợp để service mechanism nhìn thấy. Không nên vừa ghi sai tên provider vừa kỳ vọng `ServiceLoader` tự tìm class.

### 3.3. Những yếu tố khiến discovery thất bại

Khi JAR đã có nhưng `getEngineByName` vẫn null, kiểm tra:

1. File `META-INF/services/javax.script.ScriptEngineFactory` có tồn tại trong đúng JAR không? Nội dung có phải **binary class name** chính xác không?
2. `ScriptEngineFactory` có thể được class loader thấy và khởi tạo không? Dependency runtime có thiếu không?
3. Factory trả đúng alias từ `getNames()` không? `"tiny"` khác `"javascript"`; không đoán alias từ tên JAR.
4. `ScriptEngineManager()` đã được tạo **trước khi** thay đổi classpath/class loader chưa? Manager discovery thực hiện khi xây manager; thêm provider về sau không tự thay đổi tất cả managers hiện có.
5. Nếu dùng module path, module provider có được resolve và khai báo `provides` đúng không?
6. `getEngineByName` có tìm được factory nhưng `getScriptEngine()` trả `null`/thất bại không? Đây là lỗi **factory/implementation**, không chỉ lỗi alias.

`ScriptEngineManager(ClassLoader loader)` cho phép chọn loader phục vụ discovery; có thể hữu ích trong plugin frameworks nhưng phải tôn trọng lifecycle/class-loader isolation. Đừng tự thêm các JVM flags/module opens chỉ vì chưa tìm được tên engine.

## 4. `ScriptEngine` và vòng đời của một lần `eval`

Sau khi có engine:

```java
ScriptEngine engine = manager.getEngineByName("tiny");
if (engine == null) {
    throw new IllegalStateException("Thiếu engine: tiny");
}
Object result = engine.eval("upper:name");
```

Ở đây `tiny` là **MiniDSL tự xây** ở mục 6, không phải ngôn ngữ chuẩn do JDK cung cấp. Trong engine thực tế, `eval` nhận source `String` hoặc `Reader`; implementation có thể parse, interpret, compile hay chuyển sang runtime ngôn ngữ khác. Return type được khai báo là `Object`. `eval` thường được dùng để thực thi một đoạn script trong cùng thread gọi, nhưng ý nghĩa và resource behavior do engine quyết định.

Một implementation `ScriptEngine` phải hỗ trợ các phương thức cơ bản: `eval(String)`, `eval(Reader)` và các overload nhận `Bindings`/`ScriptContext`, `put/get`, `createBindings`, `getFactory`. Lớp `AbstractScriptEngine` cung cấp phần triển khai mặc định cho nhiều overload để người viết engine tập trung vào hai entrypoints `eval(String, ScriptContext)` và `eval(Reader, ScriptContext)`.

### 4.1. `AbstractScriptEngine` là khung, không phải một interpreter

`AbstractScriptEngine` không hiểu syntax nào. Nó triển khai một số overload `eval`, quản lý `ScriptContext` mặc định và `put/get`; **subclass** mới định nghĩa cách parse/execute source.

Đó là lý do một engine tối giản có thể xây bằng:

```java
class MyEngine extends AbstractScriptEngine {
    // Cần tự triển khai eval(String, ScriptContext),
    // eval(Reader, ScriptContext), createBindings(), getFactory().
}
```

Đây là code minh họa **chưa đủ để biên dịch**, vì subclass thực sự phải implement các abstract methods và thường cần thêm constructor/imports. Ví dụ hoàn chỉnh ở mục 6 triển khai đầy đủ.

### 4.2. `Compilable` và `Invocable` là khả năng tùy chọn

Một số engine còn implements:

- `Compilable`: `compile(script)` trả về `CompiledScript`, phù hợp khi script được biên dịch một lần và chạy lại; **không phải** mọi engine đều có tính năng này.
- `Invocable`: gọi hàm/method đã định nghĩa trong môi trường script bằng `invokeFunction`/`invokeMethod` hoặc tạo interface proxy nếu engine hỗ trợ; cũng **không bắt buộc**.

Mã client phải kiểm tra:

```java
if (engine instanceof Compilable c) {
    CompiledScript compiled = c.compile("some-engine-specific-source");
    Object output = compiled.eval();
} else {
    // Engine không hỗ trợ contract Compilable.
}
```

Đoạn trên minh họa cách **kiểm tra interface**; chuỗi source cần thay bằng ngôn ngữ thật và có thể ném `ScriptException`. Không cast `(Compilable) engine` một cách mù quáng. Trong ví dụ `MiniEngine`, cả `Compilable` và `Invocable` đều **false**.

## 5. `Bindings` và `ScriptContext`: đưa dữ liệu qua ranh giới Java–script

`Bindings` extends `Map<String, Object>`: các key thường là tên biến; value là đối tượng Java. `SimpleBindings` là implementation thông dụng. `ScriptContext` quản lý nhiều scope của bindings cùng input `Reader`, output `Writer` và error `Writer`.

Hai scope chuẩn:

| Scope | Hằng số | Mục đích |
| --- | --- | --- |
| **Engine scope** | `ScriptContext.ENGINE_SCOPE` | Trạng thái/biến gắn với engine hoặc lần eval được cấp bindings riêng |
| **Global scope** | `ScriptContext.GLOBAL_SCOPE` | Trạng thái chia sẻ từ `ScriptEngineManager` cho các engine được tạo bởi manager đó |

Ví dụ trong `ScriptEngineManager`:

```java
manager.put("city", "Hanoi");  // global scope của manager
ScriptEngine engine = manager.getEngineByName("tiny");
engine.put("name", "Lan");     // ENGINE_SCOPE của engine
```

Khi factory tạo engine qua manager, manager gán **global Bindings** của nó vào `GLOBAL_SCOPE` của engine mới. Với engine áp dụng chính sách lookup scope thông dụng, `context.getAttribute("name")` sẽ tìm ENGINE_SCOPE trước GLOBAL_SCOPE. Trong MiniDSL ở mục 6, `get:city` đọc Global nếu Engine chưa có key trùng; `upper:name` đọc Engine.

**Phân biệt `engine.get` với `context.getAttribute`:** Trong `AbstractScriptEngine`, `engine.get("name")` đọc trực tiếp `ENGINE_SCOPE`, còn `context.getAttribute("city")` có thể tra qua các scopes. Vì vậy một biến global có thể dùng từ script nhưng `engine.get("city")` không nhất thiết trả biến global đó.

### 5.1. `eval(String, Bindings)` tạo scope tạm cho lần đánh giá

```java
Bindings local = engine.createBindings();
local.put("name", "Mai");

Object result = engine.eval("upper:name", local);
```

Với `AbstractScriptEngine`, overload nhận `Bindings` tạo `ScriptContext` sử dụng `local` làm **ENGINE_SCOPE cho lần eval đó**, và giữ các scope/reader/writer còn lại từ context mặc định theo quy tắc API. Nó **không phải** phép `engine.setBindings(local, ENGINE_SCOPE)` vĩnh viễn. Sau lần eval, `engine.eval("upper:name")` có thể tiếp tục đọc `name="Lan"` từ engine context gốc.

Đây là công cụ tốt để hạn chế nhiễm dữ liệu giữa các script, nhưng không đủ để tuyên bố sandbox; script vẫn có thể truy cập objects được cung cấp hoặc API mà engine cho phép.

### 5.2. `ScriptContext` cho I/O và trạng thái rõ ràng hơn

`ScriptContext` có các API:

```java
ScriptContext context = engine.getContext();
Bindings globals = engine.getBindings(ScriptContext.GLOBAL_SCOPE);
Bindings locals = engine.getBindings(ScriptContext.ENGINE_SCOPE);

context.setWriter(new java.io.StringWriter());
context.setErrorWriter(new java.io.StringWriter());
```

Đây là snippet minh họa; `engine` cần được khởi tạo trước. Một engine có thể tôn trọng `context.getWriter()` để gửi output của script tới writer này, nhưng **ngữ nghĩa print và loại I/O còn phụ thuộc implementation**. Việc đặt một `StringWriter` không ngăn script dùng API khác để ghi file/network nếu engine cho phép. Nếu `GLOBAL_SCOPE` là null trong một engine không do manager tạo, bạn cần cấu hình context thích hợp.

### 5.3. Không coi `Bindings` là object serialization

Java objects được đặt vào `Bindings` có thể được script tham chiếu theo khả năng tương tác Java–ngôn ngữ của engine; không phải mọi engine hiểu mọi kiểu object. Khi nhận output, hãy kiểm tra `instanceof`/type adapter và xử lý `null`. Các engine khác nhau có thể khác nhau cả về coercion số, cách đặt biến, hàm global và exception types. API chung không chuẩn hóa toàn bộ ngôn ngữ.

## 6. Chương trình Java 17 hoàn chỉnh, không cần engine ngoài

Để phân biệt **framework API** với **engine implementation**, ví dụ tự xây một engine đồ chơi tên **MiniDSL**. Nó cố ý **không phải JavaScript** và chỉ hiểu ba dạng lệnh:

- `get:key`: đọc biến từ `ScriptContext`.
- `upper:key`: đọc biến kiểu `String`, trả bản uppercase.
- `set:key=value`: ghi biến vào `ENGINE_SCOPE`.
- Nhiều lệnh có thể viết trên nhiều dòng; trả về kết quả của lệnh không rỗng cuối.

Phần engine chỉ có nhiệm vụ biểu diễn ngôn ngữ tối giản. `ScriptEngineManager` vẫn quản lý việc chọn factory và global bindings qua **API chuẩn**. Mã nằm trong một file **`ScriptApiRelationshipDemo.java`**, dùng Java 17 API, không phải tải JavaScript engine:

```java
import java.io.IOException;
import java.io.Reader;
import java.io.StringReader;
import java.util.List;
import java.util.Locale;
import javax.script.*;

public class ScriptApiRelationshipDemo {
    public static void main(String[] args) throws ScriptException {
        System.out.println("api.module=" + ScriptEngine.class.getModule().getName());
        ScriptEngineManager manager = new ScriptEngineManager();
        manager.put("city", "Hanoi");
        MiniFactory factory = new MiniFactory();
        manager.registerEngineName("tiny", factory);
        manager.registerEngineExtension("mini", factory);
        manager.registerEngineMimeType("text/x-mini", factory);

        ScriptEngine engine = manager.getEngineByName("tiny");
        System.out.println("engine.found=" + (engine != null));
        System.out.println("engine.factory=" + engine.getFactory().getEngineName());
        System.out.println("engine.language=" + engine.getFactory().getLanguageName());
        System.out.println("extension.found="
                + (manager.getEngineByExtension("mini") != null));
        System.out.println("mime.found="
                + (manager.getEngineByMimeType("text/x-mini") != null));

        engine.put("name", "Lan");
        System.out.println("eval.upper=" + engine.eval("upper:name"));
        System.out.println("global.city=" + engine.eval("get:city"));
        System.out.println("engine.scope="
                + engine.getBindings(ScriptContext.ENGINE_SCOPE).get("name"));

        Bindings local = engine.createBindings();
        local.put("name", "Mai");
        System.out.println("local.upper=" + engine.eval("upper:name", local));
        System.out.println("original.upper=" + engine.eval("upper:name"));

        System.out.println("eval.set=" + engine.eval("set:greeting=Hello"));
        System.out.println("engine.get=" + engine.get("greeting"));
        System.out.println("reader="
                + engine.eval(new StringReader("get:greeting")));
        System.out.println("multi=" + engine.eval(
                factory.getProgram("set:other=hi", "upper:other")));
        try {
            engine.eval("unknown-command");
        } catch (ScriptException e) {
            System.out.println("script.error=" + e.getClass().getSimpleName());
        }
        System.out.println("compilable=" + (engine instanceof Compilable));
        System.out.println("invocable=" + (engine instanceof Invocable));
    }

    public static final class MiniFactory implements ScriptEngineFactory {
        @Override public String getEngineName() { return "EducationalMini"; }
        @Override public String getEngineVersion() { return "1.0"; }
        @Override public List<String> getExtensions() { return List.of("mini"); }
        @Override public List<String> getMimeTypes() {
            return List.of("text/x-mini");
        }
        @Override public List<String> getNames() { return List.of("tiny"); }
        @Override public String getLanguageName() { return "MiniDSL"; }
        @Override public String getLanguageVersion() { return "1"; }
        @Override public Object getParameter(String key) {
            return switch (key) {
                case ScriptEngine.NAME -> "tiny";
                case ScriptEngine.ENGINE -> getEngineName();
                case ScriptEngine.ENGINE_VERSION -> getEngineVersion();
                case ScriptEngine.LANGUAGE -> getLanguageName();
                case ScriptEngine.LANGUAGE_VERSION -> getLanguageVersion();
                default -> null;
            };
        }
        @Override public String getMethodCallSyntax(
                String obj, String method, String... args) {
            return null; // MiniDSL không hỗ trợ Java-object call syntax.
        }
        @Override public String getOutputStatement(String value) {
            return null; // MiniDSL không hỗ trợ lệnh print.
        }
        @Override public String getProgram(String... statements) {
            return String.join("\n", statements);
        }
        @Override public ScriptEngine getScriptEngine() {
            return new MiniEngine(this);
        }
    }

    public static final class MiniEngine extends AbstractScriptEngine {
        private final ScriptEngineFactory factory;

        public MiniEngine(ScriptEngineFactory factory) {
            this.factory = factory;
        }

        @Override public Object eval(String source, ScriptContext context)
                throws ScriptException {
            Object result = null;
            for (String line : source.split("\\R")) {
                if (!line.isBlank()) {
                    result = executeOne(line.trim(), context);
                }
            }
            return result;
        }

        private Object executeOne(String command, ScriptContext context)
                throws ScriptException {
            if (command.startsWith("get:")) {
                return context.getAttribute(command.substring(4).trim());
            }
            if (command.startsWith("upper:")) {
                Object value = context.getAttribute(command.substring(6).trim());
                if (!(value instanceof String text)) {
                    throw new ScriptException("Expected String variable");
                }
                return text.toUpperCase(Locale.ROOT);
            }
            if (command.startsWith("set:")) {
                String assignment = command.substring(4);
                int index = assignment.indexOf('=');
                if (index <= 0) {
                    throw new ScriptException("Expected set:name=value");
                }
                String name = assignment.substring(0, index).trim();
                String value = assignment.substring(index + 1);
                context.setAttribute(name, value, ScriptContext.ENGINE_SCOPE);
                return value;
            }
            throw new ScriptException("Unknown MiniDSL command");
        }

        @Override public Object eval(Reader reader, ScriptContext context)
                throws ScriptException {
            StringBuilder source = new StringBuilder();
            char[] chunk = new char[1024];
            try {
                int n;
                while ((n = reader.read(chunk)) != -1) {
                    source.append(chunk, 0, n);
                }
            } catch (IOException e) {
                throw new ScriptException(e);
            }
            return eval(source.toString(), context);
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

Biên dịch và chạy trong thư mục chứa file:

```bash
javac --release 17 ScriptApiRelationshipDemo.java
java ScriptApiRelationshipDemo
```

`stdout` **chính xác** trên chương trình đã kiểm thử:

```text
api.module=java.scripting
engine.found=true
engine.factory=EducationalMini
engine.language=MiniDSL
extension.found=true
mime.found=true
eval.upper=LAN
global.city=Hanoi
engine.scope=Lan
local.upper=MAI
original.upper=LAN
eval.set=Hello
engine.get=Hello
reader=Hello
multi=HI
script.error=ScriptException
compilable=false
invocable=false
```

Chương trình được biên dịch thành công bằng `javac --release 17` và chạy trên OpenJDK 24 với 18 dòng kết quả như trên. Không phụ thuộc vào việc JDK có Nashorn hay bất kỳ engine script bên ngoài nào: `MiniFactory` và `MiniEngine` được tạo trong source và đăng ký thủ công.

### 6.1. Đọc output theo lớp trách nhiệm

**`api.module=java.scripting`:** interface `ScriptEngine` thực sự thuộc module `java.scripting`, không phụ thuộc vào việc đã cài một implementation ngôn ngữ nào hay chưa.

**`engine.found=true`, `engine.factory=EducationalMini`:** manager tìm factory do chương trình đăng ký rồi gọi `getScriptEngine()`. Nếu bỏ `registerEngineName("tiny", factory)` và cũng không đóng gói SPI provider, `getEngineByName("tiny")` sẽ không được bảo đảm tìm thấy.

**`extension.found=true`, `mime.found=true`:** các alias extension và MIME được đăng ký trên **chính manager instance** này. Chúng không chứng minh hệ điều hành đã cài file association hay HTTP server tự nhận dạng `.mini`; đây chỉ là lookup mapping trong scripting API.

**`eval.upper=LAN`:** engine hiểu lệnh MiniDSL `upper:name`, không phải manager tự parse cú pháp. `MiniEngine.executeOne` là nơi xử lý phần ngôn ngữ.

**`global.city=Hanoi`:** `manager.put("city", ...)` đưa biến vào global scope, manager gắn global bindings vào engine mới; `context.getAttribute` trong engine tìm được nó.

**`engine.scope=Lan`:** `engine.put("name", "Lan")` đưa `name` vào ENGINE_SCOPE, kiểm tra bằng `getBindings(ENGINE_SCOPE)`.

**`local.upper=MAI` và `original.upper=LAN`:** `eval(String, Bindings)` sử dụng map local cho một lần đánh giá; state `name=Lan` trong default engine context vẫn giữ nguyên.

**`eval.set=Hello` / `engine.get=Hello`:** implementation tự viết xử lý `set:greeting=Hello` bằng `context.setAttribute(..., ENGINE_SCOPE)`. Ứng dụng sau đó đọc biến qua `engine.get("greeting")`.

**`reader=Hello`:** overload nhận `Reader` chuyển nội dung thành source rồi dùng cùng ngữ nghĩa MiniDSL. `reader` là source channel, không phải interface cho file system bắt buộc.

**`multi=HI`:** factory ghép hai lệnh thành multi-line script; `MiniEngine` đọc từng dòng và trả kết quả lệnh cuối. Đây là đặc tính của MiniDSL cụ thể, không phải nghĩa chung của `getProgram` ở mọi engine.

**`script.error=ScriptException`:** lệnh không hợp lệ được **MiniEngine** phát hiện và ném `ScriptException`. API định nghĩa kiểu ngoại lệ; engine quyết định khi nào cú pháp sai và nội dung thông báo.

**`compilable=false` / `invocable=false`:** khả năng `eval` cơ bản **không tự động suy ra** các interface mở rộng. MiniDSL không cung cấp compile hoặc invokeFunction.

### 6.2. Giới hạn có chủ đích của MiniDSL

MiniDSL không phải một trình thông dịch JavaScript/Groovy thực sự; nó không có AST phức tạp, class isolation, sandbox, expression grammar, debug line numbers, module loader hoặc tối ưu hóa. `getMethodCallSyntax` và `getOutputStatement` của toy factory trả `null` vì MiniDSL không hỗ trợ hai loại cú pháp đó. Đó là một hạn chế được công bố rõ trong ví dụ học tập; không lấy nó làm mẫu engine sản xuất có đầy đủ năng lực.

Thực tế một engine provider sẽ phải tự định nghĩa đầy đủ parser/evaluator, conversion giữa Java và script values, error reporting, resource management, concurrency và security policy. `javax.script` chỉ mang tới **giao diện và hạ tầng tích hợp**, không giải quyết những bài toán đó thay engine.

## 7. Đưa factory ở mục 6 vào cơ chế `ServiceLoader`

Ví dụ chính cố tình dùng đăng ký thủ công để **không phụ thuộc SPI packaging**. Khi triển khai một provider JAR, engine factory có thể tự xuất hiện sau discovery nếu được đóng gói đúng.

### 7.1. Tạo service-provider file

Với source đã khai báo:

```java
public static final class MiniFactory implements ScriptEngineFactory
```

nằm bên trong `ScriptApiRelationshipDemo`, **binary name** của provider nested class là:

```text
ScriptApiRelationshipDemo$MiniFactory
```

Vì thế file service descriptor phải có đường dẫn **chính xác**:

```text
META-INF/services/javax.script.ScriptEngineFactory
```

và nội dung một dòng:

```text
ScriptApiRelationshipDemo$MiniFactory
```

Lưu ý: `$` là ký tự **thật trong binary class name của nested class**, không phải biến shell cần được mở rộng. Nếu tạo file bằng shell, cần quote thích hợp (ví dụ single quote trong Bash). Trong ứng dụng thực, provider thường là class top-level có package, nên file chứa `com.company.MyScriptEngineFactory`.

### 7.2. Đóng gói đúng class files và service descriptor

Một JAR provider có cấu trúc khái niệm:

```text
mini-engine.jar
 ├─ ScriptApiRelationshipDemo.class
 ├─ ScriptApiRelationshipDemo$MiniFactory.class
 ├─ ScriptApiRelationshipDemo$MiniEngine.class
 └─ META-INF/
     └─ services/
         └─ javax.script.ScriptEngineFactory
```

Hãy bảo đảm những class phụ thuộc và file service thực sự nằm trong JAR. Có thể kiểm tra:

```bash
jar --list --file mini-engine.jar
```

Với `mini-engine.jar` xuất hiện trong classpath của ứng dụng **trước khi tạo manager**, manager có thể dùng `ServiceLoader` tìm factory. Một client khác có thể gọi:

```java
import javax.script.ScriptEngine;
import javax.script.ScriptEngineManager;

public class DiscoverMini {
    public static void main(String[] args) throws Exception {
        ScriptEngine engine = new ScriptEngineManager().getEngineByName("tiny");
        if (engine == null) {
            throw new IllegalStateException("MiniDSL provider chưa được tìm thấy");
        }
        engine.put("name", "An");
        System.out.println(engine.getFactory().getEngineName());
        System.out.println(engine.eval("upper:name"));
    }
}
```

Đây là **một client độc lập**, nhưng nó **đòi JAR provider nói trên** ở runtime. Nếu provider được đóng gói và class loader nhìn thấy chính xác, kết quả mong đợi là:

```text
EducationalMini
AN
```

Bạn cũng có thể dùng factory tự viết ở dạng top-level và khai báo đúng `META-INF/services`, thay vì nested class của ví dụ. `ServiceLoader` không đòi client gọi `registerEngineName` khi provider đã được khám phá và `getNames()` chứa `"tiny"`.

### 7.3. Vì sao cùng engine mà `getEngineFactories()` và `registerEngineName` có thể khác?

`registerEngineName` tạo mapping trực tiếp; nó cho manager biết **nên chọn factory nào khi tra tên cụ thể**. `getEngineFactories()` báo danh sách những factory mà manager đã discover qua service-provider mechanism. Một factory chỉ đăng ký thủ công không bắt buộc xuất hiện trong list discovery. Vì vậy đừng dùng `manager.getEngineFactories().isEmpty()` làm kết luận rằng `manager.getEngineByName("tiny")` chắc chắn null **sau khi đã registerEngineName**. Hãy kiểm tra lookup thực tế và phân biệt các đường cung cấp factory.

## 8. Những lỗi phổ biến khi dùng `javax.script`

| Biểu hiện | Khả năng nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| `import javax.script.*` compile, nhưng `getEngineByName("JavaScript") == null` | API có, engine provider không có hoặc alias không được đăng ký | Kiểm tra JDK/version, factories, dependency provider và `getNames()` |
| `NullPointerException` ở `engine.eval(...)` | `engine` là null do lookup thất bại | Kiểm tra `engine == null` trước eval; báo lỗi “missing provider” minh bạch |
| `getEngineFactories()` rỗng | Manager không discover factory nào qua ServiceLoader | Kiểm tra classpath/module path, META-INF/services, class loader, named modules |
| Có provider JAR nhưng tên tra không thấy | Alias không đúng `getNames()`, hoặc JAR chưa được class loader thấy | Dùng tên factory hỗ trợ; kiểm tra file service và class loader |
| Lookup bằng tên thành công nhưng `eval` ném `ScriptException` | Script sai cú pháp/ngữ nghĩa hoặc engine báo lỗi | Kiểm tra message/line/column/cause của `ScriptException` và source language |
| `ClassCastException` với kết quả `eval` | Ứng dụng giả định sai kiểu trả về | Kiểm tra `instanceof`, schema và conversion theo engine |
| `ClassNotFoundException`, `NoClassDefFoundError`, `ServiceConfigurationError` khi discovery | Thiếu JAR phụ thuộc, provider class name sai hoặc init thất bại | Kiểm tra dependencies runtime, đóng gói service descriptor, logs |
| `engine instanceof Compilable` false | Implementation không hỗ trợ compile | Dùng `eval` hoặc chọn engine khác có feature cần thiết |
| `engine instanceof Invocable` false | Không có khả năng invokeFunction qua JSR 223 | Không cast bừa; xem khả năng của provider |
| Biến global không xuất hiện trong script | Engine tự xây không dùng `ScriptContext` đúng hoặc manager chưa gắn global scope | Kiểm tra `manager.put` trước tạo engine, `getContext`, lookup scopes |
| Biến `name` bị thay sau một `eval` | Dùng chung default ENGINE_SCOPE hoặc engine không cô lập state | Dùng `eval(script, Bindings)` riêng, context riêng hoặc engine riêng tùy provider |
| Cùng script chạy ở engine A nhưng lỗi ở B | Ngôn ngữ/phiên bản/dialect/host interop khác | Ghi rõ engine name+version và language name+version, test tương thích |

### 8.1. Chẩn đoán engine thực tế trước khi eval

Một mẫu nên có trong ứng dụng:

```java
ScriptEngineManager manager = new ScriptEngineManager();
for (ScriptEngineFactory factory : manager.getEngineFactories()) {
    System.out.println("Engine=" + factory.getEngineName()
            + ", language=" + factory.getLanguageName()
            + ", names=" + factory.getNames());
}

ScriptEngine engine = manager.getEngineByName("your-supported-alias");
if (engine == null) {
    throw new IllegalStateException("Không tìm thấy engine provider phù hợp");
}
```

Đây là snippet **phụ thuộc môi trường**, không có stdout chuẩn, và giá trị `"your-supported-alias"` phải thay bằng alias do provider thật công bố. Nó không tải engine từ mạng. Khi debug deployment, log thêm classpath/module path, TCCL và phiên bản provider nếu cần, nhưng tránh log script chứa thông tin bí mật.

## 9. Tính an toàn, hiệu năng và thread safety thuộc về engine

### 9.1. `javax.script` không phải sandbox

`Bindings` có thể đưa Java objects vào script. Tùy engine, script có thể gọi phương thức của object, đọc/ghi tài nguyên hoặc thực hiện operations nguy hiểm. `javax.script` **không** định nghĩa cơ chế cách ly để chặn file system, network, CPU/memory abuse hoặc reflection. `eval` một chuỗi nhận từ người dùng **không tin cậy** với một runtime mạnh có thể tạo rủi ro an ninh nghiêm trọng.

Biện pháp hệ thống có thể gồm: chỉ chấp nhận script được kiểm soát, dùng DSL giới hạn thay vì tổng quát, validation, quyền thực thi tối thiểu, process isolation, giới hạn tài nguyên và timeout do host thực thi thật sự hỗ trợ. Không coi `ScriptContext.setWriter` hay bỏ một key khỏi `Bindings` là cơ chế bảo vệ chắc chắn nếu engine vẫn cho truy cập API khác.

### 9.2. API không bảo đảm mọi ScriptEngine thread-safe

Một `ScriptEngine` thường giữ state/`Bindings`; dùng cùng instance trong nhiều luồng có thể gây race tùy implementation. `ScriptEngineFactory.getParameter("THREADING")` có thể cung cấp thông tin threading model của engine theo quy ước JSR 223, nhưng behavior cụ thể vẫn cần đối chiếu tài liệu provider. Các giá trị thường gặp có thể bao gồm `"MULTITHREADED"`, `"THREAD-ISOLATED"`, `"STATELESS"` hoặc `null`, mỗi loại mang điều kiện riêng.

Không mặc định:

```java
// Ví dụ KHÔNG an toàn để mặc nhiên dùng với mọi engine:
static ScriptEngine shared = new ScriptEngineManager()
        .getEngineByName("some-language");
// Nhiều request tự do gọi shared.eval(...) cùng lúc.
```

Đây là **pseudocode cảnh báo** chứ không phải cấu hình được đề xuất: tùy provider, cần tạo engine theo request, dùng lock, pooling với contract rõ ràng hoặc cơ chế cách ly khác. `ENGINE_SCOPE` và `GLOBAL_SCOPE` còn có thể chứa objects mutable dùng chung, nên chỉ “có nhiều engine instances” chưa chắc loại bỏ mọi shared state.

### 9.3. Chi phí khởi tạo, compilation và caching

Tìm factory bằng `ScriptEngineManager` rồi tạo engine có chi phí khởi tạo tùy provider. Mỗi lần `eval` có thể parse/compile hoặc diễn dịch. Nếu `Compilable` được hỗ trợ, `CompiledScript` có thể cho phép reuse phần đã compile trong phạm vi contract engine; nhưng không phải mọi `CompiledScript` đều thread-safe hay độc lập state.

Phép tối ưu hiệu năng cần **đo bằng workload thực tế** và phải giữ nguyên semantics của `Bindings`, global scope, instance lifetime và security. Không tự cache `ScriptEngine` toàn cục nếu provider không bảo đảm khả năng dùng đồng thời.

## 10. Kịch bản ứng dụng và cách chọn giải pháp

**Kịch bản A — xử lý một công thức/DSL nhỏ trong hệ thống nội bộ:** Nếu syntax rất hạn chế, có thể viết một parser chuyên biệt an toàn hơn; không nhất thiết thêm engine JavaScript tổng quát. MiniDSL trong bài minh họa sự tách lớp, **không** đại diện một parser production.

**Kịch bản B — nhúng ngôn ngữ có sẵn:** Chọn engine JSR 223 có hỗ trợ Java version, security và features cần thiết; thêm dependencies hợp lệ và kiểm tra factory alias. Nếu thư viện ngôn ngữ chỉ có embedding API riêng mà không có adapter `ScriptEngineFactory`, `ScriptEngineManager` sẽ không tự biết cách chạy.

**Kịch bản C — plugin scripts nhiều tenant:** Thiết kế quản lý class loader/module, engine lifecycle, `Bindings` riêng, mức tin cậy script và isolation. Không tin rằng `GLOBAL_SCOPE` phù hợp để cất dữ liệu bí mật cho mọi request.

**Kịch bản D — migrate từ JDK 8/11 sang Java 17:** Đừng chỉ kiểm tra compile-time của `javax.script`. Hãy kiểm tra runtime discovery và cách xử lý khi Nashorn không còn; thay engine phải xét **khác biệt cú pháp, semantics, kiểu dữ liệu, interop và security**, không chỉ thay alias.

**Kịch bản E — viết chính một engine cho ngôn ngữ nhỏ:** Cung cấp `ScriptEngine` implementation, factory metadata chuẩn, registration hoặc SPI provider; dùng `AbstractScriptEngine` khi phù hợp và kiểm thử scopes, I/O, exception, threading.

## 11. Bài tập tự kiểm tra

**A.** Tại sao trên Java 17, `import javax.script.ScriptEngine` có thể biên dịch nhưng `getEngineByName("JavaScript")` trả `null`?

**B.** Có một class implements `ScriptEngine` nhưng bạn không đăng ký factory và không cung cấp `META-INF/services`. `new ScriptEngineManager()` có chắc tìm thấy nó không?

**C.** Trong ví dụ MiniDSL, tại sao `manager.put("city","Hanoi")` có thể được `eval("get:city")` đọc, trong khi `engine.put("name","Lan")` ở scope khác?

**D.** Sau khi tạo `Bindings local` và gọi `engine.eval("upper:name", local)`, biến trong default ENGINE_SCOPE có nhất thiết bị thay thành tên trong `local` không?

**E.** Khi `engine.eval(...)` trả `Object`, có thể ép thẳng `(Integer)` mà không kiểm tra gì không? Nếu script vô hiệu, loại ngoại lệ chuẩn nào thường được dùng?

**F.** `engine` đã hỗ trợ `eval` thì chắc chắn implements `Compilable` và `Invocable` không?

**G.** `getEngineFactories()` rỗng, nhưng ứng dụng vừa gọi `manager.registerEngineName("tiny", factory)`. Từ đó có thể kết luận `getEngineByName("tiny")` chắc chắn null không?

**H.** Tại sao một `ScriptEngine` có thể không an toàn khi dùng chung giữa các thread và `javax.script` không phải sandbox?

**I.** Trong module app dùng `javax.script`, thêm `requires java.scripting` có đủ để chạy Groovy/JavaScript chưa? Cần thêm điều gì?

**Đáp án:**

- **A:** API ở `java.scripting` vẫn tồn tại; Nashorn đã bị loại khỏi JDK từ Java 15. Không có provider phù hợp thì manager trả null.
- **B:** Không. Manager tìm **`ScriptEngineFactory`** qua SPI hoặc các mapping đã đăng ký, không dò tất cả object implementing `ScriptEngine`.
- **C:** `manager.put` ghi GLOBAL_SCOPE dùng chung, `engine.put` ghi ENGINE_SCOPE cho instance; `ScriptContext` cho phép engine đọc biến theo scope.
- **D:** Không. Với `AbstractScriptEngine`, overload `eval(String, Bindings)` dùng bindings được truyền cho lần eval, không mặc nhiên sửa bindings mặc định của engine.
- **E:** Không. Kiểu runtime do engine quyết định; cần kiểm tra và chuyển đổi. Lỗi script thường biểu diễn bằng `ScriptException`.
- **F:** Không. Hai interface đó là extension tùy chọn, phải kiểm tra `instanceof`.
- **G:** Không. `registerEngineName` cho phép lookup trực tiếp dù factory không nhất thiết nằm trong danh sách discovery.
- **H:** State/Bindings của engine có thể mutable và provider không bảo đảm thread safety; API không kiểm soát mọi capabilities, file/network/CPU của code script.
- **I:** Chưa đủ. `requires` chỉ cấp khả năng gọi API chuẩn; cần engine implementation/provider đúng ngôn ngữ được thêm, nhìn thấy qua classpath/module path và khớp alias.

## 12. Tài liệu chính thức

- [Oracle Java SE 17 — module `java.scripting`](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/module-summary.html): module định nghĩa Scripting API và sử dụng service `ScriptEngineFactory`.
- [Oracle Java SE 17 — `ScriptEngineManager`](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptEngineManager.html): constructor, discovery, registrations, null khi không tìm engine và manager GLOBAL_SCOPE.
- [Oracle Java SE 17 — `ScriptEngine`](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptEngine.html): API `eval`, bindings, context và các overload.
- [Oracle Java SE 17 — `ScriptEngineFactory`](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptEngineFactory.html): engine metadata, alias/extension/MIME, creation.
- [Oracle Java SE 17 — `AbstractScriptEngine`](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/AbstractScriptEngine.html): base implementations, default ScriptContext và `eval(..., Bindings)`.
- [Oracle Java SE 17 — `ScriptContext`](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptContext.html): ENGINE_SCOPE/GLOBAL_SCOPE, I/O và scoped attributes.
- [OpenJDK JEP 372 — Remove the Nashorn JavaScript Engine](https://openjdk.org/jeps/372): xác nhận removal ở Java 15, không loại bỏ `javax.script` API.
- [Java SE 17 — `ServiceLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html): discovery cơ chế service-provider cho classpath và modules.

**Tổng kết:** `javax.script` là **hợp đồng tích hợp** giúp Java code dùng chung các thao tác khám phá và gọi script. `ScriptEngineFactory` đưa implementation thật vào hệ thống, còn `ScriptEngine` chịu trách nhiệm ngôn ngữ và execution. `ScriptEngineManager` chỉ có thể tìm factory đã được đăng ký hoặc discover đúng cách; **có API không đồng nghĩa có JavaScript engine**, đặc biệt từ Java 15 trở đi khi Nashorn đã bị remove khỏi JDK. Hãy kiểm tra provider, lựa chọn bindings/context và đặc tính bảo mật/thread safety trước khi nhúng script vào ứng dụng.

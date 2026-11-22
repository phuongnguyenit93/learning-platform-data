# Đăng ký engine tường minh hoặc xây dựng ScriptEngineFactory, AbstractScriptEngine (JSR-223)

## 1. Bài toán: host cần chạy một ngôn ngữ kịch bản qua hợp đồng thống nhất

Trong Java, **JSR-223 Scripting API** (package `javax.script`, module chuẩn `java.scripting`) định nghĩa các interface để ứng dụng **host** giao tiếp với một **script engine**. Host có thể yêu cầu đánh giá một đoạn script, truyền dữ liệu vào engine, nhận kết quả, cung cấp đầu ra hoặc đọc metadata ngôn ngữ mà không cần mã host phụ thuộc trực tiếp vào từng implementation.

Có hai cách để đưa một engine vào hệ thống:

1. **Đăng ký tường minh:** nếu host đã có một `ScriptEngineFactory`, gọi `ScriptEngineManager.registerEngineName`, `registerEngineExtension` hoặc `registerEngineMimeType` để ánh xạ tên/đuôi file/MIME type tới factory. Cách này rất hữu ích trong runtime plugin hoặc khi muốn kiểm soát rõ engine nào được kích hoạt.
2. **Tự xây engine:** viết implementation của `ScriptEngineFactory` cùng engine kế thừa `AbstractScriptEngine`, rồi đăng ký factory tường minh hoặc đóng gói nó như một service provider để manager tự khám phá.

Đây là hai phần **bổ trợ**, không đối lập: một engine do bạn xây vẫn có thể được đăng ký tường minh; còn một engine của thư viện bên thứ ba cũng có thể được đăng ký tường minh bằng factory do thư viện cung cấp.

Một lưu ý từ JDK hiện đại: Java SE cung cấp **Scripting API**, nhưng **không bảo đảm đi kèm engine JavaScript hay engine cho bất kỳ ngôn ngữ cụ thể nào**. Nashorn không còn được đóng gói trong JDK từ JDK 15; việc `getEngineByName("JavaScript")` trả `null` ở nhiều môi trường hiện đại là bình thường. Muốn dùng một ngôn ngữ cụ thể, phải cung cấp implementation tương thích trên classpath/module path hoặc tự xây engine.

### 1.1. Vai trò của từng thành phần

| Thành phần | Chức năng | Ai sở hữu |
| --- | --- | --- |
| `ScriptEngineManager` | Tìm engine factory, quản lý ánh xạ tên/extension/MIME, cấp engine | Host/application |
| `ScriptEngineFactory` | Khai báo tên engine, phiên bản, ngôn ngữ, bí danh, định dạng file; tạo engine | Nhà cung cấp engine |
| `ScriptEngine` | Đánh giá script, quản lý context và binding | Implementation của ngôn ngữ |
| `AbstractScriptEngine` | Base class triển khai nhiều thao tác tiện ích của `ScriptEngine` | JDK, engine tự kế thừa |
| `ScriptContext` | Context thực thi: scope, writer, reader, error writer | Host hoặc engine |
| `Bindings` | Ánh xạ tên → đối tượng Java cho các biến/giá trị script | Theo từng scope/context |
| `ScriptException` | Lỗi khi đọc/đánh giá script, có thể kèm line/column | Engine ném, host xử lý |

Luồng cơ bản:

```text
Host
  |
  | new ScriptEngineManager()
  | registerEngineName("math", myFactory) [tùy chọn]
  v
ScriptEngineManager
  |
  | getEngineByName("math")
  v
ScriptEngineFactory ---- getScriptEngine() ----> ScriptEngine
                                                |
                                    eval(script, ScriptContext)
                                                |
                                  Bindings / Reader / Writer
                                                |
                                  kết quả Java hoặc ScriptException
```

## 2. Đăng ký engine tường minh với ScriptEngineManager

### 2.1. Ba kiểu đăng ký

Giả sử ứng dụng đã có biến `factory` kiểu `ScriptEngineFactory`:

```java
ScriptEngineManager manager = new ScriptEngineManager();

manager.registerEngineName("math", factory);
manager.registerEngineExtension("mcalc", factory);
manager.registerEngineMimeType("text/x-minicalc", factory);

ScriptEngine byName = manager.getEngineByName("math");
ScriptEngine byExtension = manager.getEngineByExtension("mcalc");
ScriptEngine byMime = manager.getEngineByMimeType("text/x-minicalc");
```

Đây là **đoạn minh họa tích hợp**, chưa phải một chương trình độc lập: `factory` là implementation được cung cấp từ bên ngoài. Phần 5 trình bày một chương trình tự chứa cả factory, engine và manager để chạy được.

Các điểm cần hiểu đúng:

- `registerEngineName(String name, ScriptEngineFactory factory)` đăng ký bí danh nhận diện engine.
- `registerEngineExtension(String extension, ScriptEngineFactory factory)` đăng ký tên phần mở rộng **không kèm dấu chấm**, ví dụ `mcalc` thay vì `.mcalc`.
- `registerEngineMimeType(String mimeType, ScriptEngineFactory factory)` đăng ký loại nội dung, ví dụ `text/x-minicalc`.
- Ba bảng ánh xạ **khác nhau**: đăng ký theo tên không tự động đăng ký extension/MIME tương ứng cho một factory chưa được khám phá qua SPI. Nếu host muốn hỗ trợ cả ba cách tra cứu, hãy đăng ký rõ các khóa cần thiết.
- Đăng ký có hiệu lực với **instance manager đó**, không phải một registry toàn cục của mọi `ScriptEngineManager` trong cùng JVM.
- Các phương thức `getEngineByName`, `getEngineByExtension` và `getEngineByMimeType` trả về `null` nếu không tìm hoặc không tạo được engine phù hợp; host phải kiểm tra `null` trước khi `eval`.
- Manager sử dụng factory để nhận `ScriptEngine` (thường factory tạo một instance mới cho mỗi lần yêu cầu). Không nên mặc định nhiều engine từ cùng factory chia sẻ cùng `Bindings`, interpreter state hoặc thread safety.
- Engine được đăng ký tường minh vẫn phải có class, dependency và quyền truy cập phù hợp trong class loader của host; **đăng ký** không tự động nạp mã còn thiếu từ internet, JAR không tồn tại hay module chưa giải quyết.

### 2.2. Khi nào dùng đăng ký tường minh?

Cách này phù hợp khi host:

- Có danh sách engine được phê duyệt và chủ động tạo/nhận factory.
- Nạp plugin bằng class loader/module layer riêng, rồi nhận factory thông qua API chia sẻ.
- Muốn đặt alias riêng cho tenant hoặc phiên bản ngôn ngữ, không phụ thuộc thứ tự service discovery.
- Muốn tắt một engine mà không sửa toàn bộ artifact trong JVM.
- Muốn kiểm tra compatibility, quyền sử dụng, cấu hình, quota hoặc version **trước** khi cho phép eval.

Ví dụ, có thể áp dụng `registerEngineName("rules-v2", factoryV2)` thay vì thay thế bí danh `rules` mà nhiều ứng dụng đang dùng. Khi alias trùng, đăng ký mới trên cùng manager có thể thay đổi mapping tường minh của alias; nên quản lý và ghi nhận chính sách override, tránh việc plugin không đáng tin cậy chiếm tên chung.

### 2.3. Đăng ký tường minh khác với khám phá SPI

`ScriptEngineManager` có cơ chế tìm các `ScriptEngineFactory` qua service provider. Với classpath, JAR thường chứa descriptor:

```text
META-INF/services/javax.script.ScriptEngineFactory
```

Nội dung là tên class factory đã biên dịch, ví dụ:

```text
com.example.minicalc.MiniFactory
```

Factory được khai báo cần thực sự tồn tại, implement `ScriptEngineFactory` và được service loader có khả năng khởi tạo theo quy định. Khi được khám phá, manager dùng metadata `getNames()`, `getExtensions()`, `getMimeTypes()` để tra cứu engine phù hợp. Chỉ có một tên class trong descriptor **không** bảo đảm mọi dependency, constructor hoặc implementation của engine hợp lệ.

Với **named module**, thay vì descriptor classpath, module provider có thể công bố service bằng `provides` trong `module-info.java`:

```java
module com.example.minicalc {
    requires java.scripting;
    provides javax.script.ScriptEngineFactory
        with com.example.minicalc.MiniFactory;
}
```

Đây là **mô tả đóng gói module**, không phải file hoàn chỉnh chạy được cùng demo ở phần 5. Demo dùng class mặc định `MiniScriptDemo` để giảm số tệp; muốn build named module như trên, cần tách các class vào package `com.example.minicalc`, thêm đúng module descriptor, rồi bảo đảm module được resolve/hiển thị qua cách ứng dụng khám phá.

Không nhầm những khái niệm:

- **`registerEngineName(...)`** nhận object factory có sẵn, không yêu cầu `META-INF/services`.
- **Service discovery** nhận factory từ service descriptor/module metadata và các class loader phù hợp.
- **`getEngineFactories()`** hữu ích khi xem các factory được phát hiện; không nên dùng danh sách này làm phép xác nhận duy nhất rằng một alias đã đăng ký tường minh đang hoạt động. Hãy gọi đúng `getEngineByName` hoặc kiểu lookup cần kiểm tra.
- Khi manager dùng constructor mặc định, thread context class loader có thể ảnh hưởng khám phá SPI. Có overload `new ScriptEngineManager(classLoader)` để chọn loader khám phá một cách tường minh; điều này không thay thế việc kiểm tra class identity của `ScriptEngineFactory` thuộc API chung.

## 3. Thiết kế ScriptEngineFactory

`ScriptEngineFactory` cung cấp **metadata và phương thức tạo engine**. Một implementation không thể chỉ viết `getScriptEngine()` mà bỏ các phương thức còn lại: chúng là phần của interface và giúp host cùng công cụ biết engine hỗ trợ điều gì.

| API | Ý nghĩa trong bài | Giá trị từ ví dụ |
| --- | --- | --- |
| `getEngineName()` | Tên sản phẩm/runtime engine | `MiniCalculator` |
| `getEngineVersion()` | Phiên bản implementation engine | `1.0` |
| `getLanguageName()` | Tên ngôn ngữ/script syntax | `MiniCalc` |
| `getLanguageVersion()` | Phiên bản cú pháp/ngôn ngữ | `1.0` |
| `getNames()` | Tên/bí danh để có thể được khám phá | `minicalc`, `mc` |
| `getExtensions()` | Đuôi tệp thường dùng | `mcalc` |
| `getMimeTypes()` | MIME type được công bố | `text/x-minicalc` |
| `getParameter(String)` | Metadata cho các khóa `ScriptEngine.*`, `THREADING` | Giá trị tương ứng hoặc `null` |
| `getMethodCallSyntax(...)` | Cách biểu diễn lời gọi phương thức trong ngôn ngữ | Demo không hỗ trợ, báo unsupported |
| `getOutputStatement(...)` | Câu lệnh phát sinh output theo cú pháp engine | `print ...` |
| `getProgram(String...)` | Ghép các câu lệnh thành chương trình | Nối bằng xuống dòng |
| `getScriptEngine()` | Tạo `ScriptEngine` có khả năng eval | `new MiniEngine(this)` |

Một engine thực nên thống nhất metadata với parser của mình. Ví dụ `getProgram` trả nhiều câu lệnh cách nhau bởi newline thì `eval` phải xử lý được nhiều câu lệnh; `getOutputStatement` trả `print ...` thì interpreter phải biết lệnh `print`.

### 3.1. Engine name và language name không đồng nghĩa

Một ngôn ngữ có thể có **nhiều implementation engine**. `getLanguageName()` mô tả ngôn ngữ mà script được viết, còn `getEngineName()` mô tả implementation. Tương tự, phiên bản ngôn ngữ (tập cú pháp/công năng) không nhất thiết thay đổi cùng lịch phát hành engine (bug fix, tối ưu, packaging).

Nếu các plugin cùng đăng ký một alias ngắn như `javascript` hoặc `rules`, host cần chọn implementation theo version/compatibility rõ ràng; chỉ biết name là chưa đủ để kết luận interpreter nào sẽ chạy.

### 3.2. Khóa THREADING

`ScriptEngineFactory.getParameter("THREADING")` cho biết mức độ cam kết concurrency của engine theo quy ước API. Trong demo, trả về **`null`**: engine **không cam kết** an toàn khi nhiều thread đánh giá đồng thời cùng một instance. Với engine tự viết có shared state, nên xác định policy riêng: tạo engine/context độc lập theo request, đồng bộ hóa, hoặc thiết kế interpreter không chia sẻ trạng thái mutable.

Không tự đặt `"MULTITHREADED"`, `"THREAD-ISOLATED"` hoặc `"STATELESS"` chỉ để làm đẹp metadata nếu runtime chưa thật sự đáp ứng hợp đồng đó. Cần phân biệt thread safety của interpreter với việc `Bindings` dùng chung có thể bị nhiều thread cập nhật.

### 3.3. Các phương thức sinh cú pháp không được nói quá khả năng

MiniCalc demo chỉ có lệnh `add`, `set` và `print`. Nó **không có method call syntax**, vì vậy `getMethodCallSyntax` ném `UnsupportedOperationException` thay vì tạo một chuỗi Java-looking nhưng không thể chạy. `getOutputStatement` chỉ hỗ trợ một dòng output đơn giản, còn `getProgram` nối các statement bằng newline. Với một ngôn ngữ thực, các hàm này phải escape chuỗi hợp lệ và trả code **mà parser thật có thể chấp nhận**.

## 4. Thiết kế AbstractScriptEngine

`AbstractScriptEngine` là base class giảm boilerplate cho `ScriptEngine`, nhưng nó **không chứa interpreter sẵn**. Khi kế thừa, tối thiểu phải cung cấp hành vi phù hợp cho:

- `Object eval(String script, ScriptContext context) throws ScriptException`.
- `Object eval(Reader reader, ScriptContext context) throws ScriptException`.
- `Bindings createBindings()`.
- `ScriptEngineFactory getFactory()`.

Các overload tiện dụng như `engine.eval("...")`, `engine.put("x", value)` hay `engine.get("x")` làm việc thông qua cơ chế context/bindings của `AbstractScriptEngine`. Khi override hai phương thức eval có tham số `ScriptContext`, phải dùng chính context truyền vào, không bỏ qua để luôn thao tác trên một map global bí mật.

### 4.1. Bindings và scope

`Bindings` là map tên biến → giá trị Java. `ScriptContext` có các scope thông dụng:

- **`ENGINE_SCOPE`**: trạng thái của context/engine được dùng trong lời gọi hiện tại. `engine.put(...)` thường đặt giá trị vào bindings của scope này.
- **`GLOBAL_SCOPE`**: các giá trị chung có thể do host hoặc manager cấp. Lookup của `ScriptContext.getAttribute(name)` tìm theo thứ tự scope; giá trị ở `ENGINE_SCOPE` có thể che giá trị cùng tên ở `GLOBAL_SCOPE`.

Trong demo, `engine.put("seed", 7L)` đưa biến vào engine scope. Lệnh `add $seed 5` đọc biến bằng `context.getAttribute("seed")`. Lệnh `set total 20` ghi vào `context.setAttribute("total", 20L, ScriptContext.ENGINE_SCOPE)`, sau đó `engine.get("total")` đọc lại được.

Cần nhớ: một engine có thể nhận **ScriptContext khác nhau** cho mỗi lần đánh giá. Mã engine không nên dùng `this.getContext()` thay cho `context` của overload khi caller cố ý truyền context riêng.

### 4.2. Reader và Writer

Một script có thể được cung cấp qua `String` hoặc `Reader`. Thực thi `eval(Reader, ScriptContext)` nên đọc đủ văn bản, xử lý IOException và ném `ScriptException` theo contract. Mã demo chọn đọc toàn bộ `Reader` vào `StringBuilder` rồi gọi lại parser String; cách đó đơn giản nhưng nên đặt giới hạn kích thước input khi nhận script bên ngoài.

Để viết output, interpreter dùng `context.getWriter()` chứ không in trực tiếp vào `System.out`. Nhờ đó host có thể dùng `StringWriter` trong test, ghi file/log, hoặc chuyển output tới giao diện khác. `context.getErrorWriter()` và `context.getReader()` cũng có thể được ngôn ngữ sử dụng khi cần error stream hay stdin, nhưng parser đơn giản ở đây không cần chúng.

### 4.3. Parse error thành ScriptException

Trong JSR-223, lỗi cú pháp hoặc lỗi đánh giá nên được diễn đạt bằng `ScriptException`, giữ thông tin nguyên nhân/vị trí khi có thể. Một bản parser thực có thể dùng các constructor của `ScriptException` để khai báo tên tệp, dòng/cột cụ thể. Mã demo minh họa việc thêm số dòng vào message, nên không giả vờ có parser hoàn chỉnh hoặc nguồn script đa tệp.

Phân biệt lỗi đánh giá script với lỗi xảy ra khi host cấp class loader, tạo factory, thiết lập context hoặc quản lý lifecycle. Không tùy tiện bắt mọi `Throwable` để chuyển thành `ScriptException`; điều đó có thể nuốt lỗi JVM nghiêm trọng ngoài phạm vi interpreter.

## 5. Ví dụ Java 17+ chạy được: tự tạo MiniCalc và đăng ký theo ba cách

Ví dụ **một file Java hoàn chỉnh** sử dụng Scripting API chuẩn có trong JDK 17. Ngôn ngữ MiniCalc intentionally nhỏ để việc đăng ký, factory, bindings và context có thể kiểm chứng rõ ràng:

- `add <a> <b>`: cộng hai số nguyên hoặc biến có cú pháp `$name`, trả `long`.
- `set <name> <value>`: đặt số vào `ENGINE_SCOPE` và trả số vừa đặt.
- `print <text>`: ghi text và xuống dòng vào `ScriptContext.getWriter()`, trả `null`.
- Dòng trống và dòng bắt đầu bằng `#` được bỏ qua.
- Có thể đánh giá nhiều dòng; kết quả `eval` là kết quả của lệnh đã thực hiện cuối cùng.
- Lệnh không hợp lệ hoặc phép tính sai được báo qua `ScriptException`.

**Lưu tệp đúng tên `MiniScriptDemo.java`** trong thư mục làm việc:

```java
import java.io.IOException;
import java.io.Reader;
import java.io.StringReader;
import java.io.StringWriter;
import java.util.List;
import javax.script.AbstractScriptEngine;
import javax.script.Bindings;
import javax.script.ScriptContext;
import javax.script.ScriptEngine;
import javax.script.ScriptEngineFactory;
import javax.script.ScriptEngineManager;
import javax.script.ScriptException;
import javax.script.SimpleBindings;

public class MiniScriptDemo {
    public static final class MiniFactory implements ScriptEngineFactory {
        @Override public String getEngineName() { return "MiniCalculator"; }
        @Override public String getEngineVersion() { return "1.0"; }
        @Override public List<String> getExtensions() { return List.of("mcalc"); }
        @Override public List<String> getMimeTypes() { return List.of("text/x-minicalc"); }
        @Override public List<String> getNames() { return List.of("minicalc", "mc"); }
        @Override public String getLanguageName() { return "MiniCalc"; }
        @Override public String getLanguageVersion() { return "1.0"; }

        @Override
        public Object getParameter(String key) {
            return switch (key) {
                case ScriptEngine.ENGINE -> getEngineName();
                case ScriptEngine.ENGINE_VERSION -> getEngineVersion();
                case ScriptEngine.NAME -> getNames().get(0);
                case ScriptEngine.LANGUAGE -> getLanguageName();
                case ScriptEngine.LANGUAGE_VERSION -> getLanguageVersion();
                case "THREADING" -> null;
                default -> null;
            };
        }

        @Override
        public String getMethodCallSyntax(String obj, String method, String... args) {
            throw new UnsupportedOperationException("MiniCalc has no method calls");
        }

        @Override
        public String getOutputStatement(String toDisplay) {
            if (toDisplay.contains("\n")) {
                throw new IllegalArgumentException("One line only");
            }
            return "print " + toDisplay;
        }

        @Override
        public String getProgram(String... statements) {
            return String.join("\n", statements);
        }

        @Override
        public ScriptEngine getScriptEngine() {
            return new MiniEngine(this);
        }
    }

    public static final class MiniEngine extends AbstractScriptEngine {
        private final ScriptEngineFactory factory;

        public MiniEngine(ScriptEngineFactory factory) {
            this.factory = factory;
        }

        @Override
        public Object eval(String script, ScriptContext context) throws ScriptException {
            if (script == null || context == null) {
                throw new NullPointerException("script and context must be non-null");
            }
            Object result = null;
            String[] lines = script.split("\\R", -1);
            for (int i = 0; i < lines.length; i++) {
                String line = lines[i].trim();
                if (line.isEmpty() || line.startsWith("#")) {
                    continue;
                }
                try {
                    String[] words = line.split("\\s+");
                    switch (words[0]) {
                        case "add":
                            require(words.length == 3, "add needs two operands");
                            result = Math.addExact(number(words[1], context),
                                                   number(words[2], context));
                            break;
                        case "set":
                            require(words.length == 3, "set needs name and value");
                            require(words[1].matches("[A-Za-z][A-Za-z0-9_]*"),
                                    "invalid variable name");
                            long value = number(words[2], context);
                            context.setAttribute(words[1], value, ScriptContext.ENGINE_SCOPE);
                            result = value;
                            break;
                        case "print":
                            require(line.length() > 6, "print needs text");
                            context.getWriter().write(line.substring(6) + "\n");
                            context.getWriter().flush();
                            result = null;
                            break;
                        default:
                            throw new IllegalArgumentException("unknown command: " + words[0]);
                    }
                } catch (IllegalArgumentException | ArithmeticException | IOException problem) {
                    throw new ScriptException(
                            "line " + (i + 1) + ": " + problem.getMessage());
                }
            }
            return result;
        }

        private static void require(boolean condition, String message) {
            if (!condition) {
                throw new IllegalArgumentException(message);
            }
        }

        private static long number(String token, ScriptContext context) {
            if (token.startsWith("$")) {
                Object found = context.getAttribute(token.substring(1));
                if (!(found instanceof Number n)) {
                    throw new IllegalArgumentException("not a number: " + token);
                }
                return n.longValue();
            }
            return Long.parseLong(token);
        }

        @Override
        public Object eval(Reader reader, ScriptContext context) throws ScriptException {
            try {
                StringBuilder script = new StringBuilder();
                char[] block = new char[2048];
                int n;
                while ((n = reader.read(block)) != -1) {
                    script.append(block, 0, n);
                }
                return eval(script.toString(), context);
            } catch (IOException e) {
                throw new ScriptException(e);
            }
        }

        @Override public Bindings createBindings() { return new SimpleBindings(); }
        @Override public ScriptEngineFactory getFactory() { return factory; }
    }

    public static void main(String[] args) throws Exception {
        ScriptEngineManager manager = new ScriptEngineManager();
        MiniFactory factory = new MiniFactory();

        manager.registerEngineName("math", factory);
        manager.registerEngineExtension("mcalc", factory);
        manager.registerEngineMimeType("text/x-minicalc", factory);

        ScriptEngine engine = manager.getEngineByName("math");
        engine.put("seed", 7L);
        System.out.println("factory: " + engine.getFactory().getEngineName());
        System.out.println("sum: " + engine.eval("add $seed 5"));
        System.out.println("last: " + engine.eval("set total 20\nadd $total 2"));
        System.out.println("binding: " + engine.get("total"));

        System.out.println("extension: " +
                manager.getEngineByExtension("mcalc").eval("add 1 2"));
        System.out.println("mime: " +
                manager.getEngineByMimeType("text/x-minicalc").eval("add 10 20"));

        StringWriter writer = new StringWriter();
        engine.getContext().setWriter(writer);
        Object last = engine.eval(
                new StringReader("print Hello from Reader\nadd 3 4"));
        System.out.println("reader: " + last);
        System.out.println("writer: " + writer.toString().strip());

        try {
            engine.eval("unknown");
        } catch (ScriptException expected) {
            System.out.println("invalid: " + expected.getMessage());
        }
    }
}
```

### 5.1. Biên dịch và chạy

Dùng JDK 17 trở lên, không cần thư viện ngoài:

```bash
javac --release 17 MiniScriptDemo.java
java MiniScriptDemo
```

**Stdout chính xác**, đã được kiểm tra bằng `javac --release 17` và `java`:

```text
factory: MiniCalculator
sum: 12
last: 22
binding: 20
extension: 3
mime: 30
reader: 7
writer: Hello from Reader
invalid: line 1: unknown command: unknown
```

### 5.2. Vì sao mỗi dòng ra kết quả này?

1. `factory: MiniCalculator`: manager tra alias `math`, gọi `MiniFactory.getScriptEngine()` và engine trả đúng factory qua `getFactory()`.
2. `sum: 12`: `engine.put("seed", 7L)` lưu một giá trị vào bindings; parser giải `$seed` thành `7` rồi cộng `5`.
3. `last: 22`: script nhiều dòng lưu `total = 20`, sau đó tính `add $total 2`; kết quả cuối là `22`.
4. `binding: 20`: `engine.get("total")` trả giá trị `set` lưu trong `ENGINE_SCOPE`.
5. `extension: 3` và `mime: 30`: manager tìm được factory theo hai khóa đã đăng ký riêng. Mỗi `getEngineBy...` trả một engine thích hợp và chạy phép cộng độc lập.
6. `reader: 7`: overload `eval(Reader, context)` đọc `StringReader` thành script, thực hiện lệnh `print` rồi `add`. Giá trị cuối là `7`.
7. `writer: Hello from Reader`: output của lệnh `print` được ghi vào `StringWriter` do host cấp, không tự in ra terminal ở bước interpreter.
8. `invalid: ...`: lệnh không nằm trong tập cú pháp hợp lệ bị chuyển thành `ScriptException` với số dòng và nguyên nhân.

Đầu ra không phụ thuộc engine JavaScript cài sẵn. Chương trình chủ động tạo `MiniFactory`, đăng ký ba bảng và không cần `META-INF/services`. Ngoài ra, đây là **ngôn ngữ biểu thức minh họa** chứ không phải trình thông dịch JavaScript, Python hay một DSL production hoàn chỉnh.

### 5.3. Những chi tiết triển khai cần nhìn kỹ

- `MiniFactory` là **static nested public class** của `MiniScriptDemo`, nên dễ đóng gói trong một tệp chạy thử. Nếu muốn phát hành SPI độc lập, thường tách factory/engine ra package rõ ràng.
- `getScriptEngine()` trả **engine mới**, vì factory không lưu một engine singleton dùng chung vô tình chia sẻ mutable state.
- `AbstractScriptEngine` được sử dụng để tập trung logic ở hai overload `eval(String, ScriptContext)` và `eval(Reader, ScriptContext)`. Các convenience overload đi qua logic đó.
- `createBindings()` tạo `SimpleBindings` mới, có thể thay bằng implementation có kiểm soát nếu cần nhưng phải tuân contract của `Bindings`.
- `getFactory()` trả cùng `factory` được truyền cho constructor, giữ nhất quán metadata mà host nhìn thấy.
- `Math.addExact` làm phép cộng kiểm soát tràn số `long`. Tràn gây `ArithmeticException` và được bọc thành `ScriptException` với thông tin dòng.
- `Number.longValue()` trong demo đơn giản hóa chuyển đổi, có thể cắt phần thập phân của `Double`. DSL thật nên xác định chính sách kiểu số, overflow và rounding thay vì ép bừa.
- `split("\\s+")` chấp nhận token cách nhau bằng whitespace cho lệnh `add/set`; `print` lấy phần text sau prefix, không hỗ trợ quoting/escaping đầy đủ.
- `getOutputStatement` mới xử lý newline `\n` ở mức minh họa. Nếu engine chấp nhận dữ liệu người dùng không tin cậy, cần grammar, escaping và giới hạn input hoàn chỉnh, không ghép raw string thành code.

## 6. Tạo engine và factory có thể bảo trì trong dự án thật

### 6.1. Tách các tầng theo trách nhiệm

Một kiến trúc mở rộng bền vững nên phân tách:

```text
host scripting module
  ScriptEngineManager
    - chọn engine theo policy
    - kiểm tra metadata/compatibility
    - cấp ScriptContext/Bindings
    - logging, quota, audit

provider module/JAR
  ScriptEngineFactory
    - metadata, extension/name/mime
    - khởi tạo ScriptEngine

  ScriptEngine extends AbstractScriptEngine
    - eval(String, ScriptContext)
    - eval(Reader, ScriptContext)
    - createBindings()
    - getFactory()

  Parser / Interpreter / Runtime
    - parse AST hoặc bytecode tùy ngôn ngữ
    - thực thi với context đã cấp
    - trả kết quả hoặc lỗi có vị trí
```

`AbstractScriptEngine` chỉ giúp triển khai hợp đồng Java, không thay cho parser, compiler, evaluator hay dependency isolation. Một ngôn ngữ phức tạp có thể cần AST, bộ nhớ thực thi, service libraries, scheduling, module/class loaders và adapter chuyển kiểu Java ↔ kiểu script.

### 6.2. Khi nào nên tự tạo ScriptEngine?

Tự viết `ScriptEngineFactory`/`AbstractScriptEngine` có giá trị nếu:

- Đang xây DSL có tập lệnh hẹp, cú pháp và tính tương thích do công ty quản lý.
- Muốn expose một runtime nội bộ hiện có dưới giao diện JSR-223 để host sử dụng chung.
- Cần wrapper/adaptor cho một interpreter đã tồn tại nhưng không hỗ trợ JSR-223 trực tiếp.
- Muốn tương thích với các framework chỉ nhận `ScriptEngine`/`ScriptEngineFactory`.

**Không nhất thiết nên viết interpreter mới** nếu chỉ cần chạy một ngôn ngữ phổ biến. Khi đó nên đánh giá engine uy tín phù hợp JDK, license, version và mô hình bảo mật, rồi dùng factory của engine đó. Việc viết parser đúng ngữ nghĩa, quản lý loại dữ liệu, exceptions, performance và security có thể lớn hơn rất nhiều so với code JSR-223 adapter.

### 6.3. Đăng ký khi hệ thống plugin được nạp động

Khi host nạp plugin từ JAR hoặc `ModuleLayer` riêng, một luồng hợp lý là:

1. Khám phá metadata và xác nhận nguồn plugin được cho phép.
2. Nạp/khởi tạo `ScriptEngineFactory` bằng cơ chế đã được thiết kế.
3. Kiểm tra các thuộc tính factory, đặc biệt tên, ngôn ngữ, version, API compatibility và policy threading.
4. Quyết định alias/extension/MIME nào được phép công bố trong manager của host.
5. Đăng ký factory bằng các lệnh `registerEngineName`/`Extension`/`MimeType` phù hợp.
6. Khi có yêu cầu thực thi, nhận engine/context thích hợp; cấp binding theo quyền hạn người gọi.
7. Hủy tham chiếu và tạo manager/registry mới hoặc thiết kế cơ chế thay thế phù hợp khi plugin hết hạn hoặc được nâng version.

**Không coi ScriptEngineManager là registry có đầy đủ chức năng unregister/hot-reload.** API đăng ký tường minh không cung cấp một thao tác unregister đối xứng rõ ràng cho từng mapping. Trong runtime nhiều phiên bản hoặc có chính sách tenant, có thể tốt hơn khi host duy trì bảng registry riêng, rồi tạo lại manager/route khi thay đổi engine.

Nếu plugin có class loader riêng, việc manager giữ `factory` có thể giữ cả loader/instance/class của plugin, ngăn unload. Cần quản lý vòng đời, cache, thread và tham chiếu rõ ràng; không chỉ xóa một entry trong giao diện UI rồi tưởng plugin đã được thu hồi.

## 7. ScriptContext, state và đồng thời

### 7.1. Tách state theo lần gọi

Nếu các script đến từ nhiều request/tenant, không nên chia sẻ một `ENGINE_SCOPE` mutable không có isolation. Host có thể dùng:

- Một engine mới và bindings mới cho mỗi request.
- Một engine (nếu implementation cam kết thread safety) nhưng **context/bindings tách biệt** cho từng execution.
- Pool engine có lifecycle cụ thể, giới hạn quyền và số lượng request.
- Một runtime worker bên ngoài tiến trình Java để có ranh giới bảo mật mạnh.

Chọn phương án theo **thread-safety contract thực tế**, không chỉ theo tên API. Demo trả `"THREADING" -> null` vì không chứng minh có thể sử dụng đồng thời một instance engine.

### 7.2. GLOBAL_SCOPE không phải cache tùy tiện

`ScriptEngineManager` có thể quản lý bindings chung cho các engine do manager tạo. `GLOBAL_SCOPE` phù hợp với các giá trị cấu hình dùng chung **nếu policy cho phép**, nhưng không được dùng để nhét secret, quyền admin hoặc mutable object có thể rò sang script của tenant khác. Một binding chứa object Java có thể mở ra nhiều method/quyền hơn dự kiến.

Nếu cần chia sẻ helper, có thể expose một interface hẹp thay vì truyền thẳng service object quản trị toàn hệ thống. Một khi script có tham chiếu tới object Java, các ràng buộc truy cập phụ thuộc engine và cơ chế tương tác của ngôn ngữ, không tự được JSR-223 sandbox hóa.

### 7.3. Eval không bảo đảm timeout hoặc rollback

`ScriptEngine.eval` có thể chạy lâu, chặn thread hoặc làm thay đổi state qua object được expose. Không có bảo đảm chung rằng API JSR-223 có timeout mặc định, rollback binding, checkpoint hoặc cơ chế hủy an toàn mọi engine. Timeout dựa trên `Thread.interrupt()` chỉ hữu ích nếu interpreter hợp tác kiểm tra interrupt và các tác vụ phụ cũng có khả năng dừng.

Nếu input không tin cậy, cân nhắc tiến trình riêng, quota CPU/memory, giới hạn I/O/network, loại bỏ quyền không cần thiết, kiểm thử treo/infinite loop và chính sách kill process. `ClassLoader` riêng và `ScriptContext` riêng chỉ là ranh giới tổ chức code/state, **không phải sandbox bảo mật**.

## 8. Các lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách điều tra |
| --- | --- | --- |
| `getEngineByName("JavaScript") == null` | JDK có API nhưng không có engine JavaScript được cung cấp | Kiểm tra dependency engine và cơ chế SPI/module |
| `getEngineByName("math") == null` | Chưa đăng ký trong manager đó, sai alias hoặc factory lỗi | Kiểm tra `registerEngineName` và đúng instance manager |
| `getEngineByExtension("mcalc") == null` | Chỉ đăng ký name, chưa đăng ký extension | Đăng ký `registerEngineExtension` hoặc cấu hình SPI metadata |
| `getEngineByMimeType(...) == null` | MIME khác chữ hoặc không mapping | Kiểm tra key thực tế và factory |
| Manager có factory nhưng `eval` lỗi | Parser, context hoặc engine không xử lý script | Lấy `ScriptException` và diagnostics |
| `ServiceConfigurationError` lúc khám phá | Provider class/factory cấu hình sai hoặc không thể tạo | Kiểm tra descriptor, constructor, module, dependency |
| `ClassCastException` giữa host và engine | `javax.script` hoặc API chung bị nạp với identity khác | Kiểm tra class loader/shared runtime API |
| Script đọc biến được nhưng request khác cũng thấy | Scope/bindings bị chia sẻ ngoài ý muốn | Dùng context/engine riêng theo policy |
| `ScriptException` không có vị trí hữu ích | Engine ném message chung, bỏ line/column/cause | Thiết kế lỗi parser rõ line/column và cause chain |
| Script có output nhưng host không thu được | Interpreter dùng `System.out` thay vì `context.getWriter()` | Định tuyến writer trong engine |
| Engine có hỗ trợ Reader nhưng đọc mất dữ liệu | Đọc một lần, không lặp tới EOF; quên xử lý IOException | Test `eval(Reader, ScriptContext)` với input dài |
| Không unload được plugin | Manager/engine/cache giữ factory và loader | Xác định lifecycle và tất cả tham chiếu |
| Script chạy quá lâu hoặc truy cập tài nguyên nhạy cảm | JSR-223 không có sandbox mặc định | Cách ly execution và kiểm soát quyền/quota |

### 8.1. Chẩn đoán nên log điều gì?

Khi một engine không hoạt động, nên ghi:

- Tên alias/extension/MIME host tra cứu.
- Metadata `getEngineName`/`getEngineVersion`/`getLanguageName`/`getLanguageVersion` khi factory có sẵn.
- Class tên và defining loader của factory/engine.
- Engine được tìm nhờ đăng ký tường minh hay service discovery.
- Script language/version được yêu cầu, request ID, thời gian và timeout.
- Loại lỗi, số dòng/vị trí từ `ScriptException` nếu có, và full cause chain.

Không tự động log toàn bộ script, bindings hoặc object graph trong production: script có thể chứa dữ liệu khách hàng, token và thông tin nhạy cảm.

## 9. Checklist kiểm thử trước khi cung cấp script engine cho host

1. **Factory đủ hợp đồng:** mọi phương thức `ScriptEngineFactory` có ý nghĩa nhất quán; `getScriptEngine().getFactory()` trả đúng factory.
2. **Name lookup:** đăng ký name và `getEngineByName` trả instance không null.
3. **Extension/MIME lookup:** đăng ký riêng và kiểm tra từng khóa; alias không chiếm nhầm mapping khác.
4. **No discovery dependency:** chế độ đăng ký tường minh chạy được dù không có service descriptor.
5. **SPI deployment nếu dùng:** kiểm tra `META-INF/services` hoặc `provides` trong named module, class loader, constructor và dependency.
6. **String/Reader:** `eval(String, context)` và `eval(Reader, context)` cho kết quả đồng nhất với cùng script.
7. **Bindings/scopes:** `put/get`, `ENGINE_SCOPE`, `GLOBAL_SCOPE`, thứ tự lookup và context riêng hoạt động như contract.
8. **Output:** `context.getWriter()` nhận output; errors không bị nuốt.
9. **Parser errors:** lệnh sai, toán hạng sai, overflow và lỗi đọc Reader tạo `ScriptException` phù hợp.
10. **Threading:** chính sách concurrent eval và lifecycle engine có kiểm thử; `THREADING` không công bố quá khả năng.
11. **Tương thích:** JDK version, `java.scripting`, language version và engine version phù hợp môi trường deploy.
12. **Bảo mật:** input size, CPU/quota, quyền truy cập qua exposed Java objects, annotation/module/class loader, logging nhạy cảm.
13. **Lifecycle:** registry/manager không giữ mã plugin cũ vô hạn sau update hoặc xóa engine.

**Kết luận:** `ScriptEngineManager` là điểm host chọn engine; `ScriptEngineFactory` mô tả và khởi tạo engine; còn `AbstractScriptEngine` hỗ trợ viết implementation nhưng vẫn cần parser và logic đánh giá thật. Khi host đã có factory, **đăng ký tường minh** bằng name/extension/MIME là cách đơn giản, chủ động và không cần service descriptor. Khi muốn cung cấp một DSL hoặc runtime mới, hãy triển khai đầy đủ factory + engine, tôn trọng `ScriptContext`/`Bindings`/`ScriptException`, rồi chọn cơ chế đăng ký hoặc SPI phù hợp với cách đóng gói và quản lý plugin.
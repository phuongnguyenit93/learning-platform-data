# Kiểm tra Invocable trước khi gọi hàm hoặc phương thức

## 1. Vì sao phải kiểm tra Invocable?

Một chương trình Java có thể sử dụng Java Scripting API (JSR 223) để giao tiếp với một ngôn ngữ kịch bản được cung cấp qua **ScriptEngine**. Chẳng hạn host nạp một script định nghĩa hàm tính giá, quy tắc xử lý văn bản hoặc các method trên một đối tượng script, rồi muốn gọi các hành vi ấy từ Java.

Tuy nhiên, **không phải mọi ScriptEngine đều hỗ trợ việc gọi hàm và phương thức trực tiếp theo tên**. Interface **javax.script.Invocable** là **khả năng tùy chọn** của một script engine. Vì vậy trước khi gọi **invokeFunction(...)** hay **invokeMethod(...)**, phải xác nhận engine hiện có và **implements Invocable**.

Luồng xử lý nên là:

~~~text
ScriptEngineManager
        |
        v
getEngineByName("tên-engine")
        |
        +-- null --------> không tìm thấy engine, thông báo rõ
        |
        v
ScriptEngine engine
        |
        +-- !(engine instanceof Invocable)
        |        |
        |        +-----> engine có thể eval nhưng không hỗ trợ Invocable
        |
        v
   Invocable invocable
        |
        v
  engine.eval(script)
        |
        +-- ScriptException -> lỗi đọc/chạy script
        |
        v
  invokeFunction("name", args...)
  hoặc invokeMethod(scriptObject, "name", args...)
        |
        +-- NoSuchMethodException -> không tìm thấy hàm/method phù hợp
        +-- ScriptException       -> lỗi khi gọi script
        |
        v
      Object kết quả
~~~

**Thứ tự quan trọng:**

1. Tìm engine bằng **ScriptEngineManager** (hoặc nhận một ScriptEngine đã được dependency injection cung cấp).
2. Kiểm tra **engine != null**.
3. Kiểm tra **engine instanceof Invocable** trước khi ép kiểu/gọi.
4. Thực thi script bằng **eval(...)** để các hàm/đối tượng được định nghĩa trong state của engine.
5. Gọi **invokeFunction(...)** hoặc **invokeMethod(...)** với đúng tên và đối số.
6. Xử lý kết quả **Object**, ngoại lệ, tài nguyên và vòng đời state.

Không được coi **ScriptEngine.eval(...) chạy được** là bằng chứng **Invocable chắc chắn được hỗ trợ**: đây là hai giao diện với trách nhiệm khác nhau.

## 2. Phân biệt ScriptEngine và Invocable

| Thành phần | Vai trò | Điều kiện sử dụng |
|---|---|---|
| **ScriptEngineManager** | Phát hiện/tạo ScriptEngine qua các ScriptEngineFactory hiện có | Phải có engine provider khả kiến |
| **ScriptEngine** | Đánh giá script, quản lý context/bindings, lấy và đặt dữ liệu | Interface nền tảng của engine |
| **Invocable** | Gọi hàm/method đã được định nghĩa bởi script và ánh xạ vào Java interface | Chỉ dùng khi engine **implements Invocable** |
| **ScriptEngineFactory** | Công bố tên engine, ngôn ngữ, khả năng và cách tạo engine | Dùng khi chọn/cấu hình engine |
| **ScriptContext / Bindings** | Lưu các biến và ngữ cảnh xử lý script | Cần hiểu scope khi tìm đối tượng/hàm |

**Invocable** gồm bốn nhóm thao tác:

~~~java
// Chữ ký API, mảnh minh họa.
Object invokeFunction(String name, Object... args)
        throws ScriptException, NoSuchMethodException;

Object invokeMethod(Object thiz, String name, Object... args)
        throws ScriptException, NoSuchMethodException;

<T> T getInterface(Class<T> clasz);

<T> T getInterface(Object thiz, Class<T> clasz);
~~~

- **invokeFunction** gọi một hàm/thủ tục **top-level** mà script đã định nghĩa.
- **invokeMethod** gọi một **member method** trên một đối tượng script mà engine nhận biết; đối tượng đó được truyền qua **thiz**.
- **getInterface(Class<T>)** xin một adapter Java interface được triển khai bằng các hàm script trong engine.
- **getInterface(thiz, Class<T>)** xin adapter Java interface được triển khai bằng các member method của một script object.

**getInterface(...)** có thể trả **null** nếu engine không thể tạo adapter tương ứng; engine implements Invocable **không bảo đảm mọi interface đều ánh xạ được**. Hai phương thức getInterface cũng không chứng minh hàm cụ thể tồn tại trước khi thử ánh xạ.

## 3. Kiểm tra null và khả năng Invocable đúng cách

### 3.1. Pattern dùng Java 17+

~~~java
// Mảnh code: dùng trong phương thức có xử lý ScriptException, ...
ScriptEngineManager manager = new ScriptEngineManager();
ScriptEngine engine = manager.getEngineByName("javascript");

if (engine == null) {
    throw new IllegalStateException("No JavaScript ScriptEngine installed");
}

if (!(engine instanceof Invocable invocable)) {
    throw new UnsupportedOperationException(
        "This ScriptEngine does not implement Invocable");
}

// Sau khi đã kiểm tra và đã eval script...
Object value = invocable.invokeFunction("hello", "Java");
~~~

Cú pháp **instanceof Invocable invocable** là *pattern matching for instanceof*, được hỗ trợ trong Java 17. Nó đồng thời kiểm tra runtime type và ràng buộc biến **invocable** có kiểu Invocable cho nhánh tiếp theo.

Có thể dùng cách tương thích Java 8:

~~~java
// Mảnh minh họa, engine được lấy từ trước và khác null.
if (!(engine instanceof Invocable)) {
    throw new UnsupportedOperationException("Not invocable");
}
Invocable invocable = (Invocable) engine;
~~~

Hai cách có ý nghĩa tương đương khi guard đúng. Với **engine == null**, toán tử **instanceof** luôn cho **false**, nhưng vẫn nên kiểm tra null riêng vì “không tìm thấy engine” khác với “đã tìm được engine nhưng thiếu tính năng”.

### 3.2. Tránh ClassCastException

~~~java
// SAI: không được tự suy đoán mọi ScriptEngine đều là Invocable.
ScriptEngine engine = new ScriptEngineManager()
        .getEngineByName("some-language");
Invocable inv = (Invocable) engine;
~~~

Cast trực tiếp có thể ném **ClassCastException** nếu engine không implements Invocable. Nếu không tìm thấy engine, biến **inv** còn có thể nhận null (cast null không tự ném), rồi lời gọi inv.invokeFunction(...) dẫn tới **NullPointerException**.

Cách đúng là tách ba trạng thái:

~~~text
engine == null                 -> MISSING_ENGINE
engine != null nhưng !Invocable -> UNSUPPORTED_CAPABILITY
engine instanceof Invocable    -> READY_TO_EVAL_AND_INVOKE
~~~

Trong ứng dụng lớn, ba trạng thái này nên có thông điệp chẩn đoán khác nhau và được log kèm tên engine/version provider.

## 4. Lưu ý đặc biệt về Java 17: JDK không bảo đảm có JavaScript engine

**javax.script** thuộc module chuẩn **java.scripting**, nhưng **có API không đồng nghĩa có sẵn một triển khai cho mọi ngôn ngữ**.

Nashorn JavaScript engine đi kèm các JDK cũ đã **bị loại khỏi JDK từ Java 15**. Vì thế trong nhiều cài đặt JDK 17, đoạn:

~~~java
ScriptEngine engine = new ScriptEngineManager()
        .getEngineByName("javascript");
~~~

sẽ trả **null** nếu bạn chưa cài/đăng ký JavaScript engine bên ngoài. **Không viết bài Java 17 rồi giả định engine JavaScript mặc định luôn tồn tại.**

Để chẩn đoán những engine đang được tìm thấy:

~~~java
// Mảnh minh họa chạy được khi có java.scripting.
ScriptEngineManager manager = new ScriptEngineManager();
for (ScriptEngineFactory factory : manager.getEngineFactories()) {
    System.out.println(
        factory.getEngineName() + " : " + factory.getNames());
}
~~~

Danh sách có thể rỗng hoặc chứa nhiều factory tùy runtime và thư viện cung cấp. **ScriptEngineManager.getEngineByName(name)** trả **null** nếu không có factory cho tên đó. Tên alias như "javascript", "js" hay một tên khác là tùy **ScriptEngineFactory.getNames()** của provider, không phải tất cả engine đều nhận cùng alias.

**Cách cung cấp engine:** thêm một triển khai JSR 223 có **ScriptEngineFactory** hợp lệ vào classpath/module path và giải quyết dependency theo tài liệu chính thức của thư viện ấy. Đừng giả định mọi trình thông dịch hoặc mọi bản GraalVM đều tự đăng ký JSR 223 engine và implements Invocable; phải xác minh trên phiên bản thực tế. Với explicit named module, cần chú ý module graph, module cung cấp ScriptEngineFactory và cấu hình class loader.

Trong ví dụ độc lập ở phần 7, ta cố ý tạo một **engine mô phỏng nhỏ bằng Java thuần** để chạy được trên JDK 17 mà không cần JavaScript provider; ví dụ đó minh họa chính xác cách **guard → eval → invoke** nhưng **không phải trình thông dịch JavaScript**.

## 5. invokeFunction và invokeMethod khác nhau ở đâu?

### 5.1. invokeFunction: gọi hàm top-level

Ví dụ JavaScript giả định engine đang hỗ trợ JSR 223 và Invocable:

~~~javascript
function greet(name) {
    return "Hello, " + name;
}
~~~

Sau khi chạy đoạn script trên bằng **engine.eval(...)**:

~~~java
// Mảnh code: engine đã implements Invocable và đã eval script.
Object answer = invocable.invokeFunction("greet", "Java");
System.out.println(answer);
~~~

Kết quả **trong engine JavaScript tương thích** có thể là:

~~~text
Hello, Java
~~~

**invokeFunction** không nhận đối tượng đích; tên **greet** phải trỏ đến hàm mà engine có thể gọi trong state đã thực thi.

### 5.2. invokeMethod: gọi member trên script object

Script JavaScript minh họa:

~~~javascript
var formatter = {
    prefix: "Hi, ",
    greet: function(name) {
        return this.prefix + name;
    }
};
~~~

Java:

~~~java
// Mảnh code: engine đã eval đoạn JavaScript trên.
Object scriptObject = engine.get("formatter");
Object answer = invocable.invokeMethod(
        scriptObject, "greet", "Java");
System.out.println(answer);
~~~

Kết quả khi engine hỗ trợ thao tác này:

~~~text
Hi, Java
~~~

Đối số **thiz** (tên tham số của API) là **đối tượng script được engine công nhận**, không phải tùy tiện một Object Java thông thường. Nó thường đến từ **engine.eval(...)**, **engine.get(...)** hoặc kết quả lần gọi script trước, tùy engine. Khi **thiz == null** hoặc không biểu diễn script object hợp lệ, **invokeMethod** có thể ném **IllegalArgumentException** theo hợp đồng API.

### 5.3. Bảng so sánh

| Tiêu chí | invokeFunction | invokeMethod |
|---|---|---|
| Mục tiêu | Hàm/procedure top-level | Method thuộc một script object |
| Tham số đặc thù | **name** | **thiz**, **name** |
| Cần script đã chạy? | Có, để hàm được định nghĩa trong engine | Có, để object/method đã tồn tại |
| Tên sai/chữ ký không khớp | **NoSuchMethodException** | **NoSuchMethodException** |
| Lỗi khi thực thi script | **ScriptException** | **ScriptException** |
| Kiểu kết quả | **Object** | **Object** |
| Quy tắc chuyển đổi số, chuỗi, đối tượng | Phụ thuộc triển khai engine | Phụ thuộc triển khai engine |

**Chọn API theo bản chất dữ liệu:** Hàm top-level thì invokeFunction; method của object script thì invokeMethod. Không gọi invokeMethod với object do Java tự tạo chỉ vì nó có một method trùng tên.

## 6. Phải eval trước khi gọi, nhưng kiểm tra Invocable không đủ để bảo đảm tên hàm tồn tại

**Invocable là một capability**, không phải danh sách bảo đảm các hàm cụ thể. Ví dụ:

~~~java
// Mảnh minh họa:
if (engine instanceof Invocable invocable) {
    engine.eval("function add(a, b) { return a + b; }");
    Object sum = invocable.invokeFunction("add", 2, 3);
    // Kết quả có thể được bridge về kiểu Number/Double/Integer tùy engine.
}
~~~

Nếu chưa eval mã định nghĩa hàm **add**, hoặc script chạy trong một state khác, **invokeFunction("add", ...)** có thể ném **NoSuchMethodException**. Nếu gọi hàm có lỗi ở runtime, nó có thể ném **ScriptException**.

**Thứ tự đúng:**

1. Kiểm tra engine tồn tại.
2. Kiểm tra engine có Invocable.
3. Eval script chính xác vào state bạn định gọi.
4. Kiểm tra hoặc nhận đối tượng script (nếu gọi method).
5. Invoke và xử lý kết quả/ngoại lệ.

**Lưu ý về ScriptContext:** Khi eval dùng một ScriptContext/Bindings tùy biến, các hàm và object được định nghĩa trong context đó không chắc hiện diện trong state mặc định mà một lệnh invoke tiếp theo sử dụng. Bảo đảm engine/context được giữ nhất quán. Cách engine giữ hàm giữa các lần eval và cách tìm biến còn phụ thuộc ngôn ngữ/implementation.

## 7. Ví dụ đầy đủ Java 17: kiểm tra Invocable và gọi hàm/method không cần engine bên ngoài

Để ví dụ thật sự biên dịch và chạy được trên **JDK 17 thuần**, đoạn dưới tạo một **mini engine minh họa giao thức JSR 223**, không phải trình thông dịch ngôn ngữ thật. Lệnh script duy nhất mà nó nhận là chuỗi **"install"**, có tác dụng đăng ký một hàm top-level **hello** và một script object mô phỏng có method **say**.

Mini engine vẫn tuân thủ những bước API đang học:

- **ScriptEngineManager** trả một ScriptEngine từ ScriptEngineFactory.
- Host kiểm tra **instanceof Invocable** trước khi gọi.
- **eval("install")** chuẩn bị state.
- **invokeFunction("hello", "Java")** gọi hàm.
- **invokeMethod(receiver, "say", "Java")** gọi method trên object nhận từ engine.
- Lệnh gọi tên không có ném **NoSuchMethodException**.
- **getInterface(...)** được demo trả **null** một cách cố ý: khả năng tạo Java proxy là tùy chọn, ngay cả khi Invocable được hỗ trợ.

### 7.1. Tệp InvocableGuardDemo.java

~~~java
import java.io.IOException;
import java.io.Reader;
import java.util.List;
import javax.script.AbstractScriptEngine;
import javax.script.Bindings;
import javax.script.Invocable;
import javax.script.ScriptContext;
import javax.script.ScriptEngine;
import javax.script.ScriptEngineFactory;
import javax.script.ScriptEngineManager;
import javax.script.ScriptException;
import javax.script.SimpleBindings;

public final class InvocableGuardDemo {

    private static final class ScriptObject {
        final String prefix;

        ScriptObject(String prefix) {
            this.prefix = prefix;
        }
    }

    // Engine nhỏ phục vụ việc minh họa contract; KHÔNG phải JavaScript.
    private static final class TinyEngine
            extends AbstractScriptEngine implements Invocable {

        @Override
        public Object eval(String script, ScriptContext context)
                throws ScriptException {
            if (!"install".equals(script)) {
                throw new ScriptException("Unsupported demo command");
            }
            context.setAttribute(
                    "ready", Boolean.TRUE, ScriptContext.ENGINE_SCOPE);
            context.setAttribute(
                    "receiver",
                    new ScriptObject("Hi, "),
                    ScriptContext.ENGINE_SCOPE);
            return null;
        }

        @Override
        public Object eval(Reader reader, ScriptContext context)
                throws ScriptException {
            try {
                StringBuilder source = new StringBuilder();
                char[] buf = new char[256];
                int n;
                while ((n = reader.read(buf)) != -1) {
                    source.append(buf, 0, n);
                }
                return eval(source.toString(), context);
            } catch (IOException e) {
                throw new ScriptException(e);
            }
        }

        @Override
        public Bindings createBindings() {
            return new SimpleBindings();
        }

        @Override
        public ScriptEngineFactory getFactory() {
            return new TinyFactory();
        }

        @Override
        public Object invokeFunction(String name, Object... args)
                throws ScriptException, NoSuchMethodException {
            if (!Boolean.TRUE.equals(
                    get("ready"))) {
                throw new ScriptException("Run eval before invoke");
            }
            if ("hello".equals(name) && args.length == 1) {
                return "Hello, " + args[0];
            }
            throw new NoSuchMethodException(name);
        }

        @Override
        public Object invokeMethod(Object thiz, String name, Object... args)
                throws ScriptException, NoSuchMethodException {
            if (!(thiz instanceof ScriptObject)
                    || thiz != get("receiver")) {
                throw new IllegalArgumentException(
                        "Receiver is not this engine's script object");
            }
            if ("say".equals(name) && args.length == 1) {
                return ((ScriptObject) thiz).prefix + args[0];
            }
            throw new NoSuchMethodException(name);
        }

        @Override
        public <T> T getInterface(Class<T> type) {
            if (type == null || !type.isInterface()) {
                throw new IllegalArgumentException("Not an interface");
            }
            return null; // Demo này không cung cấp Java interface adapter.
        }

        @Override
        public <T> T getInterface(Object thiz, Class<T> type) {
            if (type == null || !type.isInterface()
                    || thiz != get("receiver")) {
                throw new IllegalArgumentException(
                        "Invalid interface or script receiver");
            }
            return null;
        }
    }

    // Đăng ký bằng tay; không cần META-INF/services.
    private static final class TinyFactory implements ScriptEngineFactory {

        @Override
        public String getEngineName() {
            return "TinyDemo";
        }

        @Override
        public String getEngineVersion() {
            return "1.0";
        }

        @Override
        public List<String> getExtensions() {
            return List.of("tiny");
        }

        @Override
        public List<String> getMimeTypes() {
            return List.of("text/x-tiny");
        }

        @Override
        public List<String> getNames() {
            return List.of("tiny");
        }

        @Override
        public String getLanguageName() {
            return "TinyLanguage";
        }

        @Override
        public String getLanguageVersion() {
            return "1.0";
        }

        @Override
        public Object getParameter(String key) {
            if (ScriptEngine.NAME.equals(key)) {
                return "tiny";
            }
            if (ScriptEngine.ENGINE.equals(key)) {
                return "TinyDemo";
            }
            if (ScriptEngine.ENGINE_VERSION.equals(key)) {
                return "1.0";
            }
            if (ScriptEngine.LANGUAGE.equals(key)) {
                return "TinyLanguage";
            }
            if (ScriptEngine.LANGUAGE_VERSION.equals(key)) {
                return "1.0";
            }
            return null;
        }

        @Override
        public String getMethodCallSyntax(
                String obj, String method, String... args) {
            return obj + "." + method
                    + "(" + String.join(", ", args) + ")";
        }

        @Override
        public String getOutputStatement(String toDisplay) {
            return "print(" + toDisplay + ")";
        }

        @Override
        public String getProgram(String... statements) {
            return String.join("\n", statements);
        }

        @Override
        public ScriptEngine getScriptEngine() {
            return new TinyEngine();
        }
    }

    public static void main(String[] args) throws Exception {
        ScriptEngineManager manager = new ScriptEngineManager();

        // Tự đăng ký provider để ví dụ chạy được trên JDK 17 thuần.
        manager.registerEngineName("tiny", new TinyFactory());
        ScriptEngine engine = manager.getEngineByName("tiny");

        if (engine == null) {
            System.out.println("missing engine");
            return;
        }
        if (!(engine instanceof Invocable invocable)) {
            System.out.println("engine is not Invocable");
            return;
        }

        System.out.println("invocable=true");

        // Khai báo hàm và object vào state của TinyEngine.
        engine.eval("install");

        System.out.println(
            "function=" + invocable.invokeFunction("hello", "Java"));

        Object receiver = engine.get("receiver");
        System.out.println(
            "method=" + invocable.invokeMethod(
                receiver, "say", "Java"));

        try {
            invocable.invokeFunction("missing");
        } catch (NoSuchMethodException e) {
            System.out.println("missing=NoSuchMethodException");
        }

        Runnable adapter = invocable.getInterface(Runnable.class);
        System.out.println("adapter=" + (adapter != null));
    }
}
~~~

### 7.2. Biên dịch và chạy

Lưu file đúng tên **InvocableGuardDemo.java**. Trên JDK 17 trở lên:

~~~bash
javac --release 17 -encoding UTF-8 InvocableGuardDemo.java
java InvocableGuardDemo
~~~

**Stdout được thiết kế cố định:**

~~~text
invocable=true
function=Hello, Java
method=Hi, Java
missing=NoSuchMethodException
adapter=false
~~~

### 7.3. Giải thích kết quả

1. **TinyFactory** được đăng ký trực tiếp qua **registerEngineName("tiny", ...)**. Vì thế ví dụ không cần tìm một JavaScript engine ngoài và không phụ thuộc sự có mặt của Nashorn.
2. **getEngineByName("tiny")** trả **TinyEngine**; class này implements **Invocable**, nên guard chạy qua và in **invocable=true**.
3. **eval("install")** mô phỏng việc script đã định nghĩa hàm và object, lưu state vào ENGINE_SCOPE.
4. **invokeFunction("hello", "Java")** trả chuỗi **Hello, Java**; nó không phải cách thực thi JavaScript thật, mà là kết quả dispatcher mô phỏng.
5. **invokeMethod(receiver, "say", "Java")** cần object nhận được từ cùng engine, trả **Hi, Java**.
6. Hàm **missing** không có, nên mini engine ném **NoSuchMethodException**; chương trình xử lý tại ranh giới gọi script.
7. Mặc dù mini engine implements Invocable, **getInterface(Runnable.class)** trả null vì demo không cài Java adapter, minh họa một capability riêng không được bảo đảm.

**Giới hạn có chủ đích của ví dụ:** TinyEngine chỉ nhận lệnh **install** và dùng dispatcher Java; không parser JavaScript, không hỗ trợ ngôn ngữ script thực tế, không có kiểm soát an ninh và không nên được triển khai production. Mục đích của nó là tạo **một chương trình Java 17 hoàn chỉnh chạy độc lập** để nhìn thấy đúng kiểu dữ liệu, thứ tự API, guard, lỗi và kết quả của Invocable.

## 8. Mẫu tích hợp với JavaScript engine thật (cần cài engine JSR 223)

Khi đã cung cấp một **ScriptEngineFactory** cho ngôn ngữ JavaScript và engine hỗ trợ Invocable, có thể áp dụng pattern sau. Đây là **chương trình Java hợp lệ**, nhưng nhánh invoke chỉ chạy nếu môi trường có engine tương ứng.

**Tệp RealScriptDemo.java:**

~~~java
import javax.script.Invocable;
import javax.script.ScriptEngine;
import javax.script.ScriptEngineManager;
import javax.script.ScriptException;

public final class RealScriptDemo {
    public static void main(String[] args)
            throws ScriptException, NoSuchMethodException {

        ScriptEngineManager manager = new ScriptEngineManager();
        ScriptEngine engine = manager.getEngineByName("javascript");

        if (engine == null) {
            System.out.println("NO_ENGINE");
            return;
        }

        if (!(engine instanceof Invocable invocable)) {
            System.out.println("NOT_INVOCABLE");
            return;
        }

        engine.eval("""
            function hello(name) {
                return "Hello, " + name;
            }

            var receiver = {
                say: function(name) {
                    return "Hi, " + name;
                }
            };
            """);

        System.out.println(
                invocable.invokeFunction("hello", "Java"));

        Object receiver = engine.get("receiver");
        System.out.println(
                invocable.invokeMethod(receiver, "say", "Java"));
    }
}
~~~

Chạy:

~~~bash
javac --release 17 -encoding UTF-8 RealScriptDemo.java
java RealScriptDemo
~~~

**Các nhánh kết quả cần phân biệt:**

- Nếu **không có JavaScript ScriptEngineFactory** khả kiến (điển hình trên JDK 17 thuần), stdout là **NO_ENGINE**.
- Nếu có engine được chọn nhưng **không implements Invocable**, stdout là **NOT_INVOCABLE**.
- Nếu engine hỗ trợ JavaScript tương thích, cho phép định nghĩa function/object theo cú pháp trên, giữ state và hỗ trợ cả hai lời gọi, kết quả hai dòng có thể là:

~~~text
Hello, Java
Hi, Java
~~~

Không gắn cứng dòng output thứ ba như một cam kết cho mọi engine. Một engine có thể khác về alias, cách chuyển dữ liệu, xử lý object, phạm vi hàm, hoặc không thực thi toàn bộ cú pháp này. Chính vì vậy chương trình kiểm tra engine và capability trước; ngoài ra phải kiểm thử thực tế engine/version được lựa chọn.

**Điều không nên làm:** lấy biến **ScriptEngine engine**, đánh giá script xong rồi ép thẳng **(Invocable) engine**; dù script hợp lệ, engine có thể không hỗ trợ interface tùy chọn ấy.

## 9. Ngoại lệ và lỗi cần xử lý theo từng tầng

| Vị trí | Tình huống | Cách nhận biết/xử lý |
|---|---|---|
| **ScriptEngineManager.getEngineByName** | Không tìm thấy engine với tên/alias chỉ định | **engine == null**, xem danh sách factories |
| **Kiểm tra capability** | Engine có thể eval nhưng không hỗ trợ gọi hàm/method | **!(engine instanceof Invocable)**, chọn cơ chế khác |
| **engine.eval(...)** | Script lỗi cú pháp, runtime hoặc engine không thể thực thi | **ScriptException**, log source/line nếu có |
| **invokeFunction(name, ...)** | Không tìm thấy hàm hoặc chữ ký/đối số phù hợp | **NoSuchMethodException** |
| **invokeMethod(thiz, name, ...)** | Không tìm thấy method phù hợp trên script object | **NoSuchMethodException** |
| **invokeMethod(thiz, ...)** | thiz null hoặc không phải script object được engine công nhận | **IllegalArgumentException** |
| **invokeFunction/invokeMethod** | Lỗi xảy ra khi gọi logic script | **ScriptException** |
| **Kết quả từ script** | Kiểu Object không gán được cho kiểu Java mong đợi | Kiểm tra kiểu trước khi cast/chuyển đổi |
| **getInterface(...)** | Không tạo được adapter có các hàm tương ứng | Có thể trả **null** |
| **getInterface(...)** | Class tham số null/không phải interface; thiz không hợp lệ | Có thể ném **IllegalArgumentException** theo hợp đồng |

Ví dụ một adapter xử lý lỗi (mảnh Java minh họa, nằm trong class có import javax.script.*):

~~~java
static Object invokeSafe(
        ScriptEngine engine, String functionName, Object... arguments)
        throws ScriptException, NoSuchMethodException {

    if (engine == null) {
        throw new IllegalStateException("Script engine unavailable");
    }

    if (!(engine instanceof Invocable invocable)) {
        throw new UnsupportedOperationException(
                "Engine cannot invoke functions");
    }

    // Hàm phải đã được định nghĩa bởi script trước lời gọi này.
    return invocable.invokeFunction(functionName, arguments);
}
~~~

**Đây là mảnh phương thức, không phải ứng dụng độc lập.** Tên hàm không tồn tại là một loại lỗi khác với engine không có khả năng Invocable. Nếu code nghiệp vụ muốn trả một kết quả phân loại (success/missing function/script error), nên chuyển từng lỗi sang kiểu kết quả phù hợp, đừng gom tất cả vào catch(Exception) rồi trả null.

Phân biệt **ScriptException** với **NoSuchMethodException** giúp log và phản hồi chính xác:

~~~java
// Mảnh minh họa trong code gọi script.
try {
    Object value = invocable.invokeFunction("calculate", 10);
    System.out.println(value);
} catch (NoSuchMethodException e) {
    System.err.println("Script function not found: calculate");
} catch (ScriptException e) {
    System.err.println("Script execution failed: " + e.getMessage());
}
~~~

**Lưu ý:** Ràng buộc tên và chuyển đổi argument được định nghĩa bởi từng engine. Một số lỗi Java thông thường (NullPointerException, IllegalArgumentException, ClassCastException...) vẫn có thể xuất hiện do logic tích hợp sai; guard không biến script thành hệ thống miễn lỗi.

## 10. Kiểu dữ liệu: đầu vào Object... và đầu ra Object

**invokeFunction** và **invokeMethod** nhận danh sách đối số kiểu **Object...**. Chúng dựa vào engine để chuyển Java object sang giá trị script và ngược lại. Ví dụ một biểu thức số trong JavaScript có thể được bridge thành **Double**, **Integer**, **Long**, **BigDecimal** hoặc wrapper đặc thù của engine; không suy luận kiểu cụ thể từ cú pháp script.

Thay vì ép kiểu mù:

~~~java
// Sai nếu engine không trả đúng Integer.
Integer count = (Integer) invocable.invokeFunction("count");
~~~

hãy kiểm tra hợp đồng mong muốn:

~~~java
// Mảnh minh họa; hàm count được bảo đảm trả kết quả số.
Object raw = invocable.invokeFunction("count");

if (!(raw instanceof Number number)) {
    throw new IllegalStateException("count did not return a number");
}

int count = number.intValue();
~~~

Nếu cần bảo toàn độ chính xác hoặc giới hạn số nguyên, **intValue()** có thể làm mất phần thập phân hoặc tràn; quy ước chuyển đổi số nên là một phần của hợp đồng tích hợp.

**Varargs có thể gây nhầm khi truyền null.** Trong Java, **invokeFunction("f", (Object) null)** là lời gọi với một đối số null, trong khi **invokeFunction("f", (Object[]) null)** truyền một mảng varargs null. Không dùng hai hình thức này thay thế nhau nếu engine phân biệt số lượng đối số.

Khi trả về script object, đôi khi cần tiếp tục sử dụng chính giá trị đó làm **thiz** cho invokeMethod; đừng ép nó thành một Java type cụ thể nếu engine không công bố kiểu wrapper ấy.

## 11. getInterface là lựa chọn khác, không thay thế việc kiểm tra Invocable

Nếu script có những hàm tương ứng với một Java interface, **Invocable.getInterface** có thể trả về một adapter để gọi qua method Java thay vì tên chuỗi:

~~~java
// Interface Java, mảnh minh họa.
public interface Formatter {
    String format(String name);
}
~~~

~~~java
// Mảnh minh họa: trước đó engine đã eval script
// định nghĩa function format(name).
if (engine instanceof Invocable invocable) {
    Formatter formatter = invocable.getInterface(Formatter.class);

    if (formatter == null) {
        throw new UnsupportedOperationException(
            "No matching Formatter adapter available");
    }

    String result = formatter.format("Java");
}
~~~

Biến **Formatter** có các method được code Java biết trước; adapter có thể giúp tránh lặp tên hàm chuỗi ở những lời gọi nghiệp vụ. Tuy nhiên **getInterface** vẫn thuộc interface **Invocable**, và **kết quả có thể null**. Không phải mọi engine đều cài đặt cơ chế proxy giống nhau; các method cụ thể phải được script định nghĩa tương ứng.

Với script object có method, dùng **getInterface(scriptObject, Formatter.class)** nếu engine hỗ trợ. Đối tượng **scriptObject** phải thuộc đúng engine/state. Khi interface class không phải interface hoặc object không hợp lệ, **IllegalArgumentException** có thể xảy ra.

**Không nhầm:** **instanceof Invocable** kiểm tra engine có năng lực *gọi script*. **getInterface(...) != null** kiểm tra riêng liệu engine có thể cung cấp *adapter sang một Java interface cụ thể* trong trạng thái hiện tại.

## 12. Lỗi thiết kế và cách sửa

### 12.1. Cast thẳng mà không kiểm tra

~~~java
// Anti-pattern:
Invocable inv = (Invocable) manager.getEngineByName("javascript");
~~~

**Sửa:** nhận ScriptEngine, kiểm tra null, dùng **instanceof Invocable inv** rồi mới gọi.

### 12.2. Kiểm tra engine tồn tại nhưng bỏ qua capability

~~~java
// Anti-pattern:
if (engine != null) {
    ((Invocable) engine).invokeFunction("run");
}
~~~

**Sửa:** kiểm tra interface Invocable riêng. Một engine có thể eval thành công mà vẫn thiếu API invocation.

### 12.3. Gọi trước khi eval script

~~~java
// Anti-pattern: chưa đăng ký hàm trong state engine.
invocable.invokeFunction("greet", "Java");
engine.eval("function greet(name) { return name; }");
~~~

**Sửa:** eval trước, invoke sau. Nếu source được biên dịch/preload qua cơ chế khác, vẫn cần bảo đảm hàm đã có mặt trong context engine đang dùng.

### 12.4. Nhầm hàm top-level với method trên object

~~~java
// Không tương đương:
invocable.invokeFunction("greet", "Java");
invocable.invokeMethod(scriptObject, "greet", "Java");
~~~

Hai lời gọi tìm hàm ở hai vị trí khác nhau. Nếu script định nghĩa **formatter.greet**, cần một **formatter object** hợp lệ để invokeMethod; nếu định nghĩa **function greet**, invokeFunction phù hợp hơn.

### 12.5. Tin rằng getInterface không bao giờ null

~~~java
// Anti-pattern: có thể null.
Formatter formatter = invocable.getInterface(Formatter.class);
formatter.format("Java");
~~~

**Sửa:** kiểm tra **formatter != null** và có fallback/error rõ ràng khi adapter không khả dụng.

### 12.6. Coi Java 17 luôn có engine "javascript"

Từ Java 15, Nashorn không còn đi kèm JDK. Trên JDK 17, nếu không có JavaScript provider ngoài, **getEngineByName("javascript")** trả null. **Sửa:** khai báo dependency của engine trong runtime, dùng tên từ **getEngineFactories()**, kiểm tra trước khi sử dụng và có đường lỗi rõ.

### 12.7. Trộn object từ nhiều ScriptEngine

Một script object từ engine A không mặc nhiên có thể dùng làm **thiz** cho Invocable của engine B. Ngay cả khi hai engine cùng hỗ trợ một ngôn ngữ, wrapper/identity/state có thể khác. **Sửa:** giữ engine, ScriptContext và script object theo cùng một phiên sử dụng.

### 12.8. Dùng một engine stateful đồng thời không kiểm soát

Đối tượng engine có thể chứa biến, scope, bindings và trạng thái ngôn ngữ. Không giả định mọi ScriptEngine thread-safe. Tham số **THREADING** trong ScriptEngineFactory.getParameter(...) cung cấp thông tin theo hợp đồng provider; cần đọc tài liệu engine và dùng pooling/serialization/context isolation tương ứng. Kiểm tra **Invocable** không phải một phép kiểm tra thread safety.

## 13. Tại sao engine và hàm có thể “biến mất”?

Trong ứng dụng plugin/runtime-extensibility, lỗi Invocable thường gắn với khâu tìm provider hoặc trạng thái của engine, không chỉ cú pháp Java.

**Không tìm thấy engine:** ScriptEngineManager phát hiện factories bằng cơ chế provider (ServiceLoader). Classpath, module path, Thread Context ClassLoader và registration có thể ảnh hưởng danh sách factory. In **manager.getEngineFactories()** để biết engine nào thực sự khả kiến.

**Engine không hỗ trợ Invocable:** Một interpreter có thể thực hiện script qua **eval(...)** nhưng không cho host gọi trực tiếp hàm theo tên hoặc không có object model phù hợp để gọi member. Đây là thiết kế hợp lệ; host cần fallback như **engine.eval("...")** với bindings phù hợp (nếu engine cho phép) hoặc đổi engine.

**Đã eval nhưng không thấy hàm:** Script có thể định nghĩa hàm cục bộ, không xuất ra global scope; script chạy với context khác; hàm bị ghi đè; hoặc tên/arity/type conversion không tương thích. Kiểm tra script language semantics và đúng state, không tự cho rằng mỗi function declaration luôn top-level.

**invokeMethod không chấp nhận receiver:** Object không thuộc interpreter, là null, hoặc không còn được engine giữ/nhận diện. Tái sử dụng object trả về từ cùng engine/session thay vì tạo một POJO tùy tiện.

**Phụ thuộc engine thay đổi:** Nâng cấp JDK, di chuyển JAR hoặc thay engine provider có thể thay đổi alias, hỗ trợ Invocable và kiểu dữ liệu bridge. Cần kiểm thử lại tích hợp thay vì giả định JSR 223 bảo đảm cú pháp/semantics của từng ngôn ngữ.

## 14. Bảo mật, tài nguyên và giới hạn thực tế

**Invocable không phải sandbox.** Khi gọi **eval**, **invokeFunction** hoặc **invokeMethod**, host có thể cho chạy code script ngay trong process, tùy quyền và cơ chế của engine. Nếu script do người dùng hoặc nguồn không tin cậy cung cấp, cần thiết kế ranh giới bảo mật, cấp quyền và cô lập từ đầu. Đặc biệt:

- Không cung cấp các Java object chứa secret, database connection hoặc API nội bộ cho script qua bindings nếu không cần thiết.
- Không cho script tự do truy cập class/runtime host trong engine có Java interop mà không kiểm soát.
- Xác định thời gian tối đa, bộ nhớ và cancellation policy; API Invocable **không tự cung cấp timeout**.
- Quản lý state và resource của ScriptEngine: nhiều engine có cache, thread hoặc context riêng; vòng đời phải theo tài liệu implementation.
- Khi cần chạy mã không tin cậy, cách ly bằng process/container hoặc môi trường chuyên dụng; không mặc định classloader hay kiểm tra Invocable mang lại bảo mật.
- Không ghi log nguyên nội dung script chứa dữ liệu riêng tư; log tên engine, capability, lỗi và một định danh truy vết khi thích hợp.

Về mặt thiết kế API host, có thể bọc ScriptEngine/Invocable sau một interface nghiệp vụ **ScriptRunner** để caller không cần biết từng engine. Trong adapter, làm null guard, instanceof guard, eval và xử lý exception tại một điểm thống nhất.

## 15. Kiểm thử cần thiết

### Test 1. Không có ScriptEngine

Giả lập **getEngineByName(...)** trả null hoặc chạy trên môi trường không có provider: host phải trả trạng thái **MISSING_ENGINE**, không được ném NullPointerException do invoke trên null. Đây là trường hợp rất thực tế với JavaScript trên JDK 17 thuần.

### Test 2. Engine hỗ trợ eval nhưng không implements Invocable

Cung cấp một fake ScriptEngine chỉ implement phần eval (không implement Invocable). Guard phải trả **UNSUPPORTED_CAPABILITY** hoặc đi vào fallback thích hợp, không ném ClassCastException.

### Test 3. Engine implements Invocable và script đã định nghĩa hàm

Eval một script hợp lệ rồi gọi **invokeFunction**. Kiểm tra đối số được chuyển đúng, kết quả được xử lý theo hợp đồng và không có lỗi.

### Test 4. Gọi member method trên đúng đối tượng script

Lấy script object từ cùng engine/session; gọi **invokeMethod(scriptObject, ...)**. Kiểm tra tên method đúng và phân biệt nó với hàm top-level.

### Test 5. Hàm/method không tồn tại

Gọi một tên sai hoặc một dạng đối số không phù hợp; xác minh **NoSuchMethodException** được phân loại và báo rõ.

### Test 6. Lỗi bên trong script

Dùng script cố ý ném lỗi; xác minh **ScriptException** được xử lý, không bị nhầm với “engine missing” hay “function missing”.

### Test 7. getInterface không có adapter

Ngay cả khi Invocable tồn tại, **getInterface** có thể trả null. Kiểm thử nhánh này để không có NullPointerException khi caller dùng proxy.

### Test 8. Engine version và trạng thái

Chạy cùng bộ test trên từng engine/version mà ứng dụng thực tế hỗ trợ. Kiểm tra cách bridge Object, state khi eval nhiều lần, đóng tài nguyên và an toàn luồng.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** ScriptEngine eval được script có chắc implements Invocable không?

**Đáp án:** Không. Invocable là interface **tùy chọn**. Phải kiểm tra **engine instanceof Invocable** trước khi cast/gọi.

**Câu 2.** Vì sao cần kiểm tra engine null riêng, dù instanceof null trả false?

**Đáp án:** Null thể hiện **không có ScriptEngine**, khác với **engine tồn tại nhưng không hỗ trợ Invocable**. Phân biệt giúp chẩn đoán và chọn phương án thay thế đúng.

**Câu 3.** Khi nào dùng invokeFunction thay vì invokeMethod?

**Đáp án:** Dùng invokeFunction với hàm top-level; invokeMethod cần một script object (thiz) và tên member method trên object ấy.

**Câu 4.** instanceof Invocable có chứng minh hàm "calculate" đã tồn tại không?

**Đáp án:** Không. Nó chỉ chứng minh engine hỗ trợ API gọi script. Hàm phải được định nghĩa trong state và có tên/đối số thích hợp; nếu không có, NoSuchMethodException có thể xảy ra.

**Câu 5.** Engine implements Invocable thì getInterface(Formatter.class) chắc chắn trả Formatter chứ?

**Đáp án:** Không. Nó có thể trả null nếu các hàm/method cần thiết không có hoặc engine không cung cấp adapter cho interface đó.

**Câu 6.** Trên JDK 17, getEngineByName("javascript") luôn khác null không?

**Đáp án:** Không. Nashorn đã bị loại khỏi JDK từ Java 15; cần kiểm tra JavaScript engine provider có được cài và phát hiện hay chưa.

**Câu 7.** Có thể dùng script object từ engine A làm thiz cho engine B không?

**Đáp án:** Không có bảo đảm. Object phải do Invocable của engine được gọi nhận biết; nên sử dụng cùng engine và state.

## 17. Checklist triển khai

1. **Phát hiện engine:** kiểm tra getEngineByName(...) có kết quả, ghi nhận engine name/version/alias từ ScriptEngineFactory.
2. **Guard capability:** chỉ cast/gọi khi **engine instanceof Invocable**.
3. **Chuẩn bị state:** eval đúng script trong đúng engine/context trước khi invoke.
4. **Chọn đúng API:** invokeFunction cho top-level, invokeMethod cho member và receiver là script object thực.
5. **Xử lý kiểu:** kết quả **Object** cần validation/conversion theo hợp đồng, không cast mù.
6. **Phân loại lỗi:** thiếu engine, thiếu Invocable, ScriptException, NoSuchMethodException, receiver không hợp lệ và proxy getInterface null là các nhánh khác nhau.
7. **Kiểm soát provider:** Java 17 không mặc định đi kèm Nashorn; dependency và tên engine phải được quản lý tường minh.
8. **Quản lý state/threading:** không tái dùng engine hay script object qua nhiều context/thread mà không có hợp đồng rõ.
9. **An ninh:** không cho script không tin cậy chạy trong JVM host nếu không có cách ly phù hợp.
10. **Kiểm thử:** bao phủ nhánh engine null, engine không Invocable, gọi đúng hàm/method, tên sai, lỗi script và khác biệt giữa các engine/version.

**Điểm nhớ cuối:** **ScriptEngine** là cơ chế đánh giá script; **Invocable** là khả năng tùy chọn để Java gọi các hàm hoặc phương thức đã được script định nghĩa. Trước khi invoke, luôn xác nhận **engine tồn tại**, **implements Invocable**, **script/state đã sẵn sàng** và **đúng mục tiêu top-level hay member**. Kiểm tra capability giúp tránh lỗi ép kiểu, nhưng không thay thế việc kiểm tra tên hàm, receiver, kết quả và xử lý ngoại lệ.

### Tài liệu chính thức

- Oracle Java SE 17 API — Invocable: https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/Invocable.html
- Oracle Java SE 17 API — ScriptEngine: https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptEngine.html
- Oracle Java SE 17 API — ScriptEngineManager: https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptEngineManager.html
- Oracle Java SE 17 API — ScriptEngineFactory: https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptEngineFactory.html
- Oracle Java SE 17 Migration Guide — Nashorn JavaScript engine removal: https://docs.oracle.com/en/java/javase/17/migrate/removed-tools-and-components.html

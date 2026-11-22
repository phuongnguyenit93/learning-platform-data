# Chạy mã từ String hoặc Reader bằng ScriptEngine.eval trong Java

## 1. ScriptEngine.eval giải quyết bài toán gì?

Java cung cấp **JSR 223 (Scripting API for Java)** trong package **javax.script** và module **java.scripting**. API này giúp ứng dụng Java nhúng một ngôn ngữ kịch bản do **ScriptEngine** thực thi. Host có thể tạo script động, đọc script từ tệp hoặc nhận một nguồn dữ liệu ký tự rồi gọi **eval** để thực thi theo quy tắc của *engine được cài đặt*.

Ví dụ, một ứng dụng có thể:
- Gọi quy tắc xử lý nhỏ được cung cấp dưới dạng văn bản, thay vì viết một Java class mới cho mỗi thay đổi.
- Đọc script đã được lưu và kiểm soát phiên bản từ một file **Reader**.
- Truyền dữ liệu vào môi trường script qua **Bindings** hoặc **ScriptContext**.
- Lấy giá trị trả về, hoặc bắt **ScriptException** để báo lỗi của ngôn ngữ script.

**Điều quan trọng:** ScriptEngine là một **giao diện trừu tượng**, không phải trình thông dịch chung cho mọi cú pháp. Java 17 có API **javax.script**, nhưng **không kèm sẵn Nashorn JavaScript engine** (Nashorn bị loại khỏi JDK từ Java 15). Muốn chạy JavaScript, Groovy hoặc ngôn ngữ thực tế khác qua JSR 223, cần cài đúng **ScriptEngine provider** tương thích rồi xác minh tên được engine công bố. Không được giả định **getEngineByName("JavaScript")** luôn trả về engine khác null.

Cũng không được nhầm **eval("mã Java")** với **biên dịch mã nguồn Java**. JSR 223 chỉ chạy cú pháp của ngôn ngữ mà ScriptEngine cụ thể hiểu; muốn biên dịch .java thành .class, dùng JavaCompiler/build pipeline hoặc công cụ thích hợp khác.

## 2. Hai kiểu đầu vào của eval: String và Reader

Hai overload căn bản của **ScriptEngine**:

~~~java
Object eval(String script) throws ScriptException;
Object eval(Reader reader) throws ScriptException;
~~~

Cả hai đều thực thi nội dung script trong **default ScriptContext** của engine. Các overload khác cho phép truyền môi trường riêng:

~~~java
Object eval(String script, Bindings bindings) throws ScriptException;
Object eval(Reader reader, Bindings bindings) throws ScriptException;
Object eval(String script, ScriptContext context) throws ScriptException;
Object eval(Reader reader, ScriptContext context) throws ScriptException;
~~~

Các khai báo trên là **chữ ký API minh họa**, không phải một chương trình Java độc lập.

| Khía cạnh | **eval(String)** | **eval(Reader)** |
| --- | --- | --- |
| Dữ liệu đầu vào | Một chuỗi chứa toàn bộ script | Một nguồn ký tự do Reader cung cấp |
| Khi phù hợp | Script ngắn, template đã dựng thành chuỗi, đoạn script đã được xác minh | File script, nguồn từ stream ký tự, thư viện sinh Reader |
| Ai quyết định encoding? | Người tạo String phải decode đúng từ trước | Lớp tạo Reader, chẳng hạn Files.newBufferedReader(..., UTF_8) |
| Quản lý tài nguyên | Không có Reader riêng để đóng | Caller nên đóng Reader mà mình mở, thường với try-with-resources |
| Giá trị trả về | **Object**, có thể null tùy ngôn ngữ/câu lệnh | **Object**, cùng quy tắc kết quả của engine |
| Lỗi | **ScriptException**, và có thể có lỗi Java liên quan | **ScriptException**; lỗi đọc Reader được engine xử lý/báo theo implementation |
| Hiệu năng/bộ nhớ | Toàn bộ script đã nằm trong String | Không có cam kết engine parse streaming hoặc không buffer toàn bộ |

**Reader không mặc nhiên nhanh hơn hay tiết kiệm RAM.** Nó chỉ là giao diện lấy ký tự. Engine hoàn toàn có thể đọc hết Reader vào một String trước khi parse, giống engine minh họa trong bài. Kích thước script lớn hay nhỏ phải được đo với provider và workload thực tế.

Nếu cùng nội dung, cùng trạng thái và cùng provider, hai overload thường phục vụ cùng mục tiêu thực thi. Nhưng hành vi cụ thể—giá trị trả về, vị trí lỗi, tác dụng phụ, caching—thuộc ngôn ngữ/engine chứ không do String hay Reader tự quyết định.

## 3. Tìm ScriptEngine trước khi eval

Cách dùng thường thấy:

~~~java
// Mảnh minh họa: cần có ScriptEngineFactory tương ứng trên runtime.
javax.script.ScriptEngineManager manager =
        new javax.script.ScriptEngineManager();

javax.script.ScriptEngine engine =
        manager.getEngineByName("ten-ngon-ngu");

if (engine == null) {
    throw new IllegalStateException("Scripting engine is not installed");
}

Object result = engine.eval("cu-phap-hop-le-cua-ngon-ngu");
~~~

**"ten-ngon-ngu"** phải là một trong các tên do provider đăng ký; **"cu-phap-hop-le-cua-ngon-ngu"** phải được thay bằng script thật của ngôn ngữ đó. Đoạn trên không độc lập nếu chưa cài engine.

ScriptEngineManager thường tìm các **ScriptEngineFactory** qua cơ chế service provider. Với classpath, provider JAR có thể chứa tài nguyên **META-INF/services/javax.script.ScriptEngineFactory**; với explicit named module, khai báo provider qua **provides javax.script.ScriptEngineFactory with ...**. Chi tiết discovery và khả năng nhìn thấy module/JAR phụ thuộc class loader/module layer và cấu hình ứng dụng. Nếu không có provider, **getEngineByName() trả về null**, không có engine nào để gọi eval.

Có thể quan sát engine đang được phát hiện:

~~~java
// Mảnh minh họa trong phương thức đã có biến manager.
for (javax.script.ScriptEngineFactory factory : manager.getEngineFactories()) {
    System.out.println(factory.getEngineName() + ": " + factory.getNames());
}
~~~

**Không hardcode tên "js", "javascript", "groovy"... khi chưa đọc tên thực tế** do phiên bản provider công bố. Trong một ứng dụng có nhiều loader, factory tồn tại trong một JAR chưa chắc đã được manager tìm thấy; có thể cần cấp class loader thích hợp cho ScriptEngineManager.

**Không nhầm module java.scripting với module của một engine**: java.scripting cung cấp API; engine do nhà cung cấp thực thi. Việc thấy package javax.script trong IDE không chứng minh JavaScript engine đã được cài.

## 4. Luồng thực thi từ đầu vào đến kết quả

~~~text
String hoặc Reader
        |
        v
Validate nguồn / chọn ngôn ngữ / chọn engine
        |
        v
ScriptEngine.eval(source, Bindings hoặc ScriptContext)
        |
        v
Engine parse và thực thi cú pháp riêng
        |
        +--- trả Object (hoặc null nếu engine quy định)
        |
        +--- ném ScriptException khi engine báo lỗi script
        |
        +--- có thể gây side effect theo năng lực của script/provider
~~~

Một host không nên gọi eval chỉ vì script "parse được"; cần xác minh kết quả có đúng kiểu mong đợi, không null nếu contract cấm null, và kiểm soát mọi side effect được phép. Không nên suy luận rằng dòng **print** trong một script cũng là giá trị trả về của **eval**. Một engine có thể ghi ra Writer trong ScriptContext nhưng trả **null** hoặc một đối tượng khác.

Có ba lớp trách nhiệm:
1. **Caller Java**: xác thực input, giới hạn kích thước, quản lý Reader, chọn provider, cấp Bindings/Context, bắt lỗi và chuyển kết quả sang hợp đồng ứng dụng.
2. **Script engine**: định nghĩa ngôn ngữ, parse/evaluate, binding semantics, import/interoperability, loại result và diagnostics.
3. **Môi trường runtime**: class loader, module, quyền file/network, phiên bản dependency, tài nguyên CPU/memory và vòng đời.

Vì vậy API eval đơn giản nhưng khi đưa vào hệ thống mở rộng thực tế phải thiết kế đủ ba phần.

## 5. Ví dụ Java 17 hoàn chỉnh không cần thư viện ngoài

Để bài chạy được trên **JDK 17 chuẩn**, ví dụ tự cung cấp một **ScriptEngine nhỏ tên Mini** cùng một **ScriptEngineFactory**. Nó không phải JavaScript hay Groovy: chỉ hiểu hai lệnh:
- **greet**: lấy biến **name** từ ScriptContext và trả một chuỗi lời chào.
- **add <a> <b>**: nhận hai số nguyên và trả tổng.

Ví dụ có giá trị vì nó minh họa đúng hợp đồng **ScriptEngine.eval(String)**, **eval(Reader)**, **Bindings**, **ScriptException**. Trong ứng dụng thực, thường bạn sẽ cài provider ngôn ngữ có sẵn thay vì viết ScriptEngine của riêng mình.

### 5.1. Tạo một file Java

Tạo **src/demo/EvalDemo.java**:

~~~java
package demo;

import java.io.IOException;
import java.io.Reader;
import java.io.StringReader;
import java.util.List;
import javax.script.AbstractScriptEngine;
import javax.script.Bindings;
import javax.script.ScriptContext;
import javax.script.ScriptEngine;
import javax.script.ScriptEngineFactory;
import javax.script.ScriptEngineManager;
import javax.script.ScriptException;
import javax.script.SimpleBindings;

public final class EvalDemo {
    public static void main(String[] args) throws Exception {
        ScriptEngineManager manager = new ScriptEngineManager();
        manager.registerEngineName("mini", new MiniFactory());
        ScriptEngine engine = manager.getEngineByName("mini");

        engine.put("name", "Lan");
        System.out.println("String: " + engine.eval("greet"));

        try (Reader source = new StringReader("add 2 3")) {
            System.out.println("Reader: " + engine.eval(source));
        }

        Bindings temporary = engine.createBindings();
        temporary.put("name", "Mai");
        System.out.println("Bindings: " + engine.eval("greet", temporary));
        System.out.println("Original: " + engine.eval("greet"));

        try {
            engine.eval("invalid");
        } catch (ScriptException ex) {
            System.out.println("Error: " + ex.getClass().getSimpleName());
        }
    }

    private static final class MiniEngine extends AbstractScriptEngine {
        private final ScriptEngineFactory factory;

        private MiniEngine(ScriptEngineFactory factory) {
            this.factory = factory;
        }

        @Override
        public Object eval(String script, ScriptContext context)
                throws ScriptException {
            String command = script.strip();
            if (command.equals("greet")) {
                Object name = context.getAttribute("name");
                if (name == null) {
                    throw new ScriptException("Missing name binding");
                }
                return "Xin chao, " + name + "!";
            }

            String[] parts = command.split("\\s+");
            if (parts.length == 3 && parts[0].equals("add")) {
                try {
                    int left = Integer.parseInt(parts[1]);
                    int right = Integer.parseInt(parts[2]);
                    return Math.addExact(left, right);
                } catch (NumberFormatException | ArithmeticException ex) {
                    throw new ScriptException("Invalid integer expression");
                }
            }
            throw new ScriptException("Unsupported mini command");
        }

        @Override
        public Object eval(Reader reader, ScriptContext context)
                throws ScriptException {
            StringBuilder source = new StringBuilder();
            char[] buffer = new char[1024];
            try {
                int count;
                while ((count = reader.read(buffer)) != -1) {
                    source.append(buffer, 0, count);
                }
            } catch (IOException ex) {
                throw new ScriptException(ex);
            }
            return eval(source.toString(), context);
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

    private static final class MiniFactory implements ScriptEngineFactory {
        @Override public String getEngineName() { return "MiniEngine"; }
        @Override public String getEngineVersion() { return "1"; }
        @Override public List<String> getExtensions() { return List.of("mini"); }
        @Override public List<String> getMimeTypes() {
            return List.of("text/x-mini");
        }
        @Override public List<String> getNames() { return List.of("mini"); }
        @Override public String getLanguageName() { return "Mini"; }
        @Override public String getLanguageVersion() { return "1"; }
        @Override public Object getParameter(String key) {
            if (ScriptEngine.NAME.equals(key)) return "mini";
            if (ScriptEngine.ENGINE.equals(key)) return getEngineName();
            if (ScriptEngine.ENGINE_VERSION.equals(key)) return getEngineVersion();
            if (ScriptEngine.LANGUAGE.equals(key)) return getLanguageName();
            if (ScriptEngine.LANGUAGE_VERSION.equals(key))
                return getLanguageVersion();
            return null;
        }
        @Override public String getMethodCallSyntax(
                String obj, String method, String... args) {
            return null; // Ngon ngu Mini khong co cu phap goi method.
        }
        @Override public String getOutputStatement(String toDisplay) {
            return null; // Ngon ngu Mini khong co lenh in.
        }
        @Override public String getProgram(String... statements) {
            return statements.length == 1 ? statements[0] : null;
        }
        @Override public ScriptEngine getScriptEngine() {
            return new MiniEngine(this);
        }
    }
}
~~~

Điểm cần chú ý:

1. **manager.registerEngineName("mini", new MiniFactory())** đăng ký factory **trực tiếp trên manager này**, để chương trình không phụ thuộc engine bên ngoài. Đây **không phải** tự động discovery qua META-INF/services; thực tế có thể dùng cả hai kiểu đăng ký theo thiết kế.
2. **manager.getEngineByName("mini")** tìm factory vừa được đăng ký rồi trả ScriptEngine. Trong ví dụ này biến engine không null vì đã chủ động đăng ký đúng factory.
3. **engine.put("name", "Lan")** thiết lập biến **name** ở **ENGINE_SCOPE** của default ScriptContext.
4. **engine.eval("greet")** lấy source từ String. MiniEngine đọc biến **name** và trả "Xin chao, Lan!".
5. **engine.eval(source)** với **StringReader("add 2 3")** đi vào overload nhận Reader. MiniEngine đọc ký tự rồi gọi logic xử lý từ String.
6. **engine.eval("greet", temporary)** dùng một Bindings khác chứa **name = "Mai"**. Overload này không thay thế vĩnh viễn bindings gốc; lời gọi tiếp theo trả lời chào "Lan".
7. **engine.eval("invalid")** tạo **ScriptException** vì ngôn ngữ Mini không định nghĩa lệnh đó; ứng dụng bắt và ghi loại exception.
8. **MiniFactory** triển khai các metadata cơ bản của **ScriptEngineFactory**, gồm tên engine, ngôn ngữ, extension và cách tạo MiniEngine. Một ngôn ngữ đồ chơi không hỗ trợ cú pháp gọi method/print nên các method sinh cú pháp tương ứng trả null; đây không phải tính năng JavaScript.

MiniEngine triển khai **eval(String, ScriptContext)** và **eval(Reader, ScriptContext)** thông qua **AbstractScriptEngine**. AbstractScriptEngine hỗ trợ những overload tương ứng với default context hoặc Bindings do caller truyền, giảm công việc lặp lại so với tự viết trọn ScriptEngine interface. **createBindings()** trả SimpleBindings, còn **getFactory()** trả metadata factory đúng đối tượng.

### 5.2. Biên dịch và chạy

Từ thư mục có **src/**, tạo thư mục **out**:

~~~bash
mkdir -p out
~~~

Trên Windows PowerShell, dùng **New-Item -ItemType Directory -Force out** nếu chưa có out. Sau đó:

~~~bash
javac --release 17 -d out src/demo/EvalDemo.java
java -cp out demo.EvalDemo
~~~

**Standard output chính xác**:

~~~text
String: Xin chao, Lan!
Reader: 5
Bindings: Xin chao, Mai!
Original: Xin chao, Lan!
Error: ScriptException
~~~

Kết quả cho thấy cả hai overload thực sự chạy qua engine; eval(String) trả một String, eval(Reader) trả một Integer (nên khi nối với chuỗi thì thành "5"), Bindings tạm cho phép đổi biến của một lần thực thi, và script không hợp lệ được báo bằng ScriptException.

**Lưu ý về tính runnable:** mã dùng các API chuẩn Java và không dựa vào việc JDK có cài Nashorn hoặc GraalJS. Trình biên dịch cần hỗ trợ **--release 17**, và module **java.scripting** phải có trong runtime image nếu dùng jlink tùy chỉnh.

## 6. Ví dụ dùng Reader từ một file ngoài

Thay vì StringReader, ứng dụng thường đọc từ file theo encoding được xác định rõ:

~~~java
// Mảnh minh họa: engine là ScriptEngine hợp lệ đã lấy được,
// path là một Path trỏ đến file script có nguồn đáng tin.
try (java.io.Reader reader = java.nio.file.Files.newBufferedReader(
        path, java.nio.charset.StandardCharsets.UTF_8)) {
    Object result = engine.eval(reader);
    System.out.println(result);
}
~~~

Đây là **mảnh code minh họa**, không phải chương trình độc lập vì cần biến **engine** và **path**. Nội dung của file phải sử dụng cú pháp mà engine đã chọn chấp nhận. Nếu dùng MiniEngine ở phần 5, file chứa **add 2 3** là hợp lệ; nếu dùng JavaScript provider, cần viết cú pháp JavaScript thay thế.

Cần phân biệt hai nhóm lỗi:
- **IOException** có thể xảy ra khi mở file, và ở một số cấu hình khi đọc/đóng Reader ở phía caller.
- **ScriptException** có thể phát sinh khi engine parse/evaluate hoặc khi engine quyết định bọc lỗi Reader.

Không mặc định rằng **eval(Reader)** sẽ tự đóng Reader; theo quy ước quản lý tài nguyên, **caller mở thì caller đóng**, dùng try-with-resources kể cả khi eval ném lỗi.

**Reader khác InputStream**: Reader cung cấp ký tự đã được giải mã, còn InputStream cung cấp byte. Khi nguồn là InputStream, phải dùng InputStreamReader với Charset rõ ràng hoặc APIs tương đương. Tránh phụ thuộc vào default charset ngầm nếu script cần chạy nhất quán trên nhiều hệ điều hành.

## 7. Chọn Bindings và ScriptContext để trao đổi dữ liệu

### 7.1. ENGINE_SCOPE và GLOBAL_SCOPE

Một **ScriptContext** có các phạm vi chuẩn:

| Phạm vi | Ý nghĩa | Cách dùng |
| --- | --- | --- |
| **ScriptContext.ENGINE_SCOPE** | Variables gắn với engine/context cụ thể; được ưu tiên khi lookup | Input và state cho việc eval hiện tại |
| **ScriptContext.GLOBAL_SCOPE** | Variables chung có thể được cung cấp trong context | Cấu hình chia sẻ khi được thiết kế rõ |

Khi gọi **engine.put(key, value)**, JSR 223 đặt giá trị vào ENGINE_SCOPE của default context. Khi gọi **engine.get(key)**, API tìm giá trị trong phạm vi engine như quy ước của engine. Nếu muốn chỉ cung cấp đầu vào cho một lần eval, thường tạo **Bindings** riêng:

~~~java
// Mảnh minh họa; engine đã được tạo và script đúng cú pháp provider.
javax.script.Bindings input = engine.createBindings();
input.put("name", "Mai");
Object result = engine.eval("greet", input);
~~~

Trong ví dụ Mini, đoạn trên chạy được vì ngôn ngữ Mini hiểu lệnh **greet**. Với ngôn ngữ khác, tên variable có thể được ánh xạ sang global variables/objects theo cách khác. **Bindings là bản đồ tên → Object**, không phải bảo đảm mọi engine đều có cùng quy tắc chuyển kiểu Java/script.

Khi dùng **eval(script, bindings)**, AbstractScriptEngine tạo context tạm sử dụng bindings đó ở ENGINE_SCOPE và có thể chia sẻ GLOBAL_SCOPE từ default context. Vì thế **tách ENGINE_SCOPE không mặc nhiên cô lập toàn bộ trạng thái bên ngoài**: objects được truyền vào Bindings vẫn có thể mutable, còn engine cũng có thể giữ state riêng.

### 7.2. Dùng ScriptContext khi cần điều khiển nhiều hơn

**ScriptContext** cho phép cấu hình Reader đầu vào, Writer đầu ra, Writer lỗi và các attributes:

~~~java
// Mảnh minh họa: engine hợp lệ đã được tạo.
javax.script.SimpleScriptContext context =
        new javax.script.SimpleScriptContext();
context.setBindings(engine.createBindings(),
        javax.script.ScriptContext.ENGINE_SCOPE);
context.setAttribute("name", "An",
        javax.script.ScriptContext.ENGINE_SCOPE);
context.setWriter(new java.io.StringWriter());

Object result = engine.eval("greet", context);
~~~

Đoạn này cho thấy cách truyền context riêng. MiniEngine phần 5 lấy **name** từ context; vì vậy kết quả là **"Xin chao, An!"** khi engine đó được dùng. Nhưng writer chỉ hữu ích nếu provider/cú pháp có hành vi ghi output—đừng cho rằng mọi engine sẽ tự động in giá trị trả về của eval vào writer.

Một số engine dùng attribute chuẩn như **ScriptEngine.FILENAME** để hiển thị tên file trong diagnostics. Có thể đặt attribute trước eval, nhưng việc hỗ trợ file/line/column và định dạng lỗi là **engine-specific**. Nếu một file được nạp qua Reader, engine không tự biết đường dẫn file trừ khi caller/protocol cung cấp thông tin đó.

### 7.3. Không biến Bindings thành hộp chứa quyền hệ thống

Truyền vào Bindings một object Java giàu quyền truy cập, ví dụ **DataSource**, filesystem handler hoặc HTTP client, có thể cấp cho script khả năng thao tác tương ứng nếu engine hỗ trợ gọi method Java. Không nên truyền nguyên đối tượng ứng dụng hoặc secrets khi script chỉ cần một giá trị tính toán.

Với script không tin cậy, việc đổi scope hoặc đặt biến bằng Bindings **không đủ để sandbox**. Các cơ chế interop, class lookup và quyền tiến trình vẫn có thể mở rộng bề mặt nguy hiểm.

## 8. Kết quả trả về và ngoại lệ

### 8.1. Object result không bảo đảm là String

Cả **eval(String)** và **eval(Reader)** trả về **Object**. Ví dụ Mini trả chuỗi từ **greet** và số nguyên từ **add**. JavaScript hoặc engine khác có thể trả Number, Boolean, String, đối tượng của ngôn ngữ script, wrapper Java hoặc null, tùy cú pháp và engine.

Đừng cast thẳng:

~~~java
// Mảnh minh họa hành vi không an toàn nếu result không phải String.
String text = (String) engine.eval("add 2 3");
~~~

Với MiniEngine, dòng trên sẽ gây **ClassCastException** vì result là Integer. Cách an toàn hơn là kiểm tra kiểu hoặc dùng hợp đồng dữ liệu cụ thể:

~~~java
// Mảnh minh họa; dùng sau khi đã có engine và đã xác định contract.
Object value = engine.eval("add 2 3");
if (!(value instanceof Number number)) {
    throw new IllegalStateException("Expected numeric result");
}
int sum = number.intValue();
~~~

Khi engine trả null, phải phân biệt **null là kết quả hợp lệ** với **không có kết quả/hợp đồng bị vi phạm**. Không tự coi null là 0 hoặc chuỗi rỗng.

### 8.2. ScriptException và các loại lỗi khác

**ScriptException** là loại checked exception chính dành cho lỗi xử lý script. Nó có thể chứa message, **fileName**, **lineNumber**, **columnNumber** và cause theo thông tin mà provider có thể cung cấp; nhiều engine không có đủ dữ liệu nên không được giả định mọi field đều khác null hoặc có giá trị dương.

Ví dụ bắt lỗi:

~~~java
// Mảnh minh họa; engine đã được cấu hình.
try {
    Object result = engine.eval("invalid");
    System.out.println(result);
} catch (javax.script.ScriptException ex) {
    System.err.println("Script failed: " + ex.getMessage());
}
~~~

Đây không phải một lớp Java độc lập; trong ví dụ MiniEngine phần 5, "invalid" là lệnh không hỗ trợ nên luôn ném ScriptException. Khi báo lỗi cho người dùng, nên chuyển thành thông báo không lộ các thông tin nhạy cảm, đồng thời lưu **script version**, **engine name/version** và **correlation ID** để điều tra.

Các lỗi khác:
- **NullPointerException/IllegalArgumentException** do caller truyền đối số không hợp lệ hoặc không tuân thủ precondition.
- **IOException** khi caller tự mở/đóng Reader, hoặc lỗi I/O do provider bọc.
- **RuntimeException/Error** từ host/engine hoặc đối tượng Java được script gọi. Không coi mọi Throwable là lỗi cú pháp.
- **Không có engine**: manager trả null từ getEngineByName; khi đó chưa gọi eval được.

Nên phân loại **ENGINE_NOT_FOUND**, **INPUT_ERROR**, **SCRIPT_ERROR**, **RESULT_CONTRACT_ERROR** và **EXECUTION_FAILURE** trong log/metrics thay vì bắt mọi lỗi rồi trả chuỗi "error".

## 9. String hay Reader: lựa chọn trong hệ thống thực tế

**Chọn String** khi script đã ở sẵn dạng chuỗi—ví dụ sinh từ template đã kiểm soát, lưu trong database rồi đọc thành String, hoặc một biểu thức ngắn đã được review. Code đơn giản và dễ tính hash/ghi nhận version của source trước eval.

**Chọn Reader** khi nguồn là file, một luồng ký tự hoặc API bên ngoài đã đưa Reader. Không cần tự đọc file vào String để rồi tạo StringReader chỉ cho có Reader; với nguồn file, dùng **Files.newBufferedReader** và kiểm soát charset/close.

| Tình huống | Đầu vào phù hợp | Lý do |
| --- | --- | --- |
| Quy tắc vài dòng sinh từ cấu hình | String | Đã có đầy đủ script và dễ version |
| Một script UTF-8 ở thư mục cấu hình | Reader | Đọc trực tiếp qua file Reader, đóng đúng vòng đời |
| Nội dung đã nằm trong String | String | Tránh lớp Reader không cần thiết |
| Library bên ngoài cung cấp Reader | Reader | Dùng ngay contract của library |
| Script quá lớn | Không quyết định chỉ theo loại đầu vào | Engine có thể buffer toàn bộ, phải benchmark và áp quota |
| Chạy lại cùng script nhiều lần | Xem **Compilable** nếu provider hỗ trợ | Có thể giảm parse overhead; không phải engine nào cũng có |
| Không có provider ngôn ngữ phù hợp | Không overload nào giúp được | Cần cài engine hoặc chọn giải pháp khác |

**Không áp dụng StringReader để né validation:** việc script đi qua Reader không thay đổi quyền hay mức độ nguy hiểm của code được eval.

## 10. Tối ưu đánh giá lại script: Compilable và Invocable

Hai interface mở rộng **không phải ScriptEngine nào cũng triển khai**:

- **Compilable**: cho phép engine compile script một lần thành **CompiledScript**, rồi eval nhiều lần. Cần đo chi phí parse/compile, đồng thời kiểm soát phiên bản script và trạng thái/context.
- **Invocable**: có thể gọi function/method được xác định bởi script đã eval, thay vì eval lại toàn bộ source mỗi lần.

Mẫu kiểm tra khả năng compile:

~~~java
// Mảnh minh họa: engine và sourceScript có sẵn; cú pháp phụ thuộc engine.
if (engine instanceof javax.script.Compilable compilable) {
    javax.script.CompiledScript compiled =
            compilable.compile(sourceScript);
    Object result = compiled.eval();
}
~~~

Đừng ép kiểu nếu provider không hỗ trợ interface. Compile script không có nghĩa JavaCompiler; **Compilable** là khả năng parse/compile nội bộ của engine ngôn ngữ script, khác với tạo Java bytecode từ file .java.

**Versioning/cache:** nếu nguồn script được thay đổi, không được tái sử dụng compiled object của phiên bản cũ mà không có chính sách. Cache key nên xét source hash, engine/version, options/context và dependency khi chúng làm thay đổi ngữ nghĩa. Cần xác định xem compiled script và engine có cho phép dùng đồng thời trên nhiều thread không.

## 11. Thread safety, lifecycle và ràng buộc trạng thái

Một ScriptEngine có thể giữ trạng thái trong:
- **Default ScriptContext** và ENGINE_SCOPE Bindings.
- Global bindings được chia sẻ.
- Các biến/function đã được script tạo.
- Caches, module/script imports và objects được engine giữ lại.

**Không mặc định một ScriptEngine thread-safe.** ScriptEngineFactory có thể công bố tham số **"THREADING"** qua getParameter để mô tả hỗ trợ concurrent execution theo quy ước JSR 223. Nếu tham số null hoặc không rõ, hãy xử lý engine như **không an toàn để eval song song**, hoặc kiểm tra tài liệu provider; cách tạo một instance cho mỗi request/worker, pool có kiểm soát hoặc đồng bộ cần được thiết kế theo engine thực tế.

Tách **Bindings** cho mỗi eval giúp giảm rò rỉ variables giữa tenant, nhưng không đảm bảo cách ly khi provider có shared internals hoặc object references chung. Với môi trường multi-tenant, cần đặc biệt cẩn trọng với globalScope, Java interop và reference giữ lại sau evaluation.

Không bỏ quên lifecycle: Reader do caller mở phải đóng; engine/provider có thể quản lý resource riêng; loader giữ JAR dependency có thể cần đóng và gỡ reference khi unload plugin. Đừng hiểu rằng gọi eval xong là mọi tài nguyên hoặc thread do script tạo sẽ tự biến mất.

## 12. Bảo mật: eval là chạy mã, không phải xử lý chuỗi vô hại

**Bất kỳ đoạn script nào có khả năng chạy đều có thể có side effect** theo quyền mà engine cung cấp. Đặc biệt nếu engine cho phép tương tác với Java objects/classes, script có thể gọi method gây I/O, gửi network request hoặc truy cập dữ liệu nội bộ mà host đã cấp.

Một số nguyên tắc:
1. **Chỉ chạy nguồn đáng tin hoặc đã qua quy trình kiểm soát phù hợp.** Không đưa nguyên input từ web form vào eval nếu ngôn ngữ của engine có khả năng thực thi tổng quát.
2. **Không nội suy dữ liệu người dùng vào source tùy tiện.** Hãy truyền dữ liệu qua Bindings/parameters nếu ngôn ngữ hỗ trợ, đồng thời áp dụng validation phù hợp. Không coi Bindings là biện pháp sandbox.
3. **Giới hạn input size, execution time, CPU/memory, I/O, số lần eval**, và kiểm soát vòng đời. Timeout bằng Future.cancel không đảm bảo dừng được mọi code đang chạy trong cùng JVM.
4. **Không cấp Java object quyền cao** cho script nếu không cần thiết; giới hạn class access theo cơ chế được engine hỗ trợ, nhưng đừng nhầm cấu hình interop với cô lập tiến trình hoàn chỉnh.
5. **Với script không tin cậy**, cân nhắc DSL có năng lực hạn chế hoặc chạy trong một tiến trình/container cách ly thật sự, áp quyền và quota hệ điều hành.
6. **Ghi version/hash nguồn và engine phiên bản**, nhưng lọc diagnostics để tránh ghi bí mật hoặc toàn bộ source nhạy cảm vào log.

Java 17 không cung cấp một sandbox an toàn tự động chỉ nhờ javax.script. **SecurityManager** đã bị đánh dấu deprecated for removal từ Java 17 và không nên xem là phương án mặc định để thực thi code không tin cậy.

## 13. Những lỗi thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| manager.getEngineByName("JavaScript") trả null | JDK 17 không còn Nashorn mặc định; chưa cài JS engine | Cài provider phù hợp, kiểm tra factories/names và loader |
| eval("class X {}") không chạy Java như mong đợi | Engine đang hiểu cú pháp ngôn ngữ script, không phải javac | Dùng JavaCompiler nếu muốn biên dịch Java source |
| Script chạy với String nhưng lỗi với Reader | Reader đã bị consume/đóng, charset sai, nội dung khác | Kiểm tra Reader ownership, encoding, nội dung nguồn, version |
| eval(Reader) không tiết kiệm RAM | Provider buffer toàn bộ source | Benchmark và giới hạn size, đừng giả định streaming |
| Biến giữa các lần chạy bị lẫn | Dùng chung ENGINE_SCOPE/global objects, engine state | Bindings/context riêng, kiểm soát engine lifecycle |
| Cast result ném ClassCastException | eval trả kiểu khác dự kiến | Kiểm tra instanceof và chuẩn hóa kết quả theo contract |
| ScriptException thiếu line/column | Provider không báo location hoặc không nhận metadata file | Kiểm tra diagnostics engine; thêm filename context nếu hỗ trợ |
| Engine gặp lỗi qua class loader | Provider JAR không hiện diện/không tương thích | Kiểm tra loader dùng bởi ScriptEngineManager, dependencies và module graph |
| Nhiều request dùng chung engine gây kết quả lạ | Engine không hỗ trợ đồng thời | Xem THREADING docs, cô lập instance hoặc đồng bộ |
| Script input không đáng tin gây rủi ro | eval có quyền chạy code/Java interop | Thiết kế isolation, whitelist API và giới hạn runtime |

**Cảnh báo thực tế:** ScriptEngine.eval không được thiết kế để thay thế bộ máy xử lý dữ liệu đầu vào. Nếu yêu cầu chỉ là xác thực một số, so khớp regex hoặc ánh xạ JSON đơn giản, Java code/DSL có giới hạn thường dễ kiểm toán và an toàn hơn script engine tổng quát.

## 14. Checklist áp dụng trong hệ thống mở rộng lúc chạy

- Đã xác định **ngôn ngữ script** và provider tương ứng, không dựa vào một engine bị loại khỏi JDK.
- Đã xác minh **ScriptEngineManager** tìm được factory đúng tên và đúng class loader/module.
- Đã chọn **String** khi có sẵn chuỗi hoặc **Reader** khi nguồn ký tự đến từ file/stream, và xác định rõ encoding/ownership.
- Đã hiểu eval trả **Object**, có thể null; có chuẩn hóa và validate kết quả.
- Đã dùng **Bindings/ScriptContext** để truyền dữ liệu, không nội suy thẳng dữ liệu chưa kiểm soát vào source.
- Đã phân loại **ScriptException**, IOException khi mở Reader và lỗi runtime/type contract.
- Đã xác minh thread safety/state và khả năng **Compilable/Invocable** trước khi tối ưu/cache.
- Đã quyết định rõ script được chạy trong trust boundary nào; nếu không tin cậy, không dựa vào eval/Bindings làm sandbox.
- Đã có giới hạn tài nguyên, version/hash source, log/diagnostics đã lọc và cơ chế rollback.
- Đã thử cả **eval(String)** và **eval(Reader)** bằng nội dung tương đương với đúng provider sẽ chạy production.

**Kết luận:** **eval(String)** và **eval(Reader)** là hai cách đưa *mã của một ngôn ngữ script* vào cùng giao diện JSR 223. String thuận tiện khi đã có source dạng văn bản; Reader thuận tiện khi source là luồng ký tự. Sự khác nhau về nguồn không thay đổi yêu cầu phải có **ScriptEngine provider**, kiểm soát Bindings, xử lý lỗi và bảo vệ ranh giới thực thi.

## Tài liệu Java 17 chính thức

- ScriptEngine: https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptEngine.html
- AbstractScriptEngine: https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/AbstractScriptEngine.html
- ScriptEngineManager: https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptEngineManager.html
- ScriptContext: https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptContext.html
- ScriptException: https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptException.html
- JEP 372 (Remove the Nashorn JavaScript Engine): https://openjdk.org/jeps/372

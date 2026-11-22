# Điều khiển đầu vào, đầu ra và lỗi qua ScriptContext

Khi nhúng một ngôn ngữ script vào ứng dụng Java, host thường không muốn mọi script đọc trực tiếp bàn phím, in ra terminal chung hoặc đẩy mọi lỗi vào log của JVM. Mỗi lượt chạy script có thể đến từ một request khác nhau, cần nhận input riêng, ghi output vào vùng nhớ hoặc file riêng và trả lỗi theo một định dạng được kiểm soát.

**Java Scripting API (JSR 223), trong module java.scripting**, cung cấp **javax.script.ScriptContext** để mô tả ngữ cảnh thực thi. Đối với một ScriptEngine hỗ trợ giao diện này, host có thể cung cấp ba kênh I/O dạng ký tự:

- **Reader** từ context.getReader(): dữ liệu script có thể đọc như input.
- **Writer** từ context.getWriter(): output thông thường do engine/script gửi vào.
- **Writer** từ context.getErrorWriter(): output lỗi hoặc cảnh báo mà engine/script chủ động gửi vào.

ScriptContext còn giữ **Bindings** theo scope để script trao đổi biến với host. Tuy nhiên, **ScriptContext không tự chuyển hướng System.in/System.out/System.err của cả JVM**, không tự bắt exception thành error text và không phải sandbox bảo mật. Engine phải thực sự sử dụng các kênh đã cung cấp.

Bài này trình bày cơ chế, cách quản lý mỗi kênh, scope, lỗi, tài nguyên và một ví dụ Java 17+ **độc lập với engine JavaScript bên ngoài**.

## 1. Mô hình host → script engine → ScriptContext

Một lần thực thi có thể được hình dung như sau:

~~~text
Host Java
  |
  | chuẩn bị input, output, error, bindings
  v
SimpleScriptContext
  ├── Reader            ← dữ liệu script đọc (input)
  ├── Writer            → output bình thường
  ├── ErrorWriter       → cảnh báo/lỗi do script/engine viết
  ├── ENGINE_SCOPE      → biến ưu tiên cho lượt chạy
  └── GLOBAL_SCOPE      → biến chia sẻ/fallback tùy cấu hình
  |
  | engine.eval(scriptSource, context)
  v
ScriptEngine
  ├── có thể đọc context.getReader()
  ├── có thể ghi context.getWriter()/getErrorWriter()
  ├── có thể truy cập context.getAttribute(...) / getBindings(...)
  ├── trả về Object khi eval kết thúc
  └── có thể ném ScriptException
~~~

**ScriptEngine** là bộ thực thi cú pháp của một ngôn ngữ hay DSL. **ScriptContext** là đối tượng chứa các biến và kênh I/O dùng trong lần thực thi. **ScriptEngineManager** là cơ chế tìm những engine đã được đăng ký, nhưng không phải bản thân engine hoặc context.

Java 17+ cung cấp API **javax.script**, nhưng **không bảo đảm có sẵn một JavaScript engine**. Nashorn đã bị loại khỏi JDK kể từ JDK 15; để eval JavaScript thực sự, ứng dụng cần cài engine tương thích riêng. Vì thế, ví dụ trong bài dùng một MiniEngine thực hiện ba lệnh đơn giản để minh họa **cơ chế API**; nó không giả vờ là JavaScript interpreter.

### Ba kênh I/O là ba vai trò khác nhau

| Phương thức | Kiểu Java | Vai trò | Ví dụ host cung cấp |
| --- | --- | --- | --- |
| context.setReader(reader) | java.io.Reader | Input mà script/engine có thể đọc | StringReader, BufferedReader từ file |
| context.setWriter(writer) | java.io.Writer | Output thông thường của script | StringWriter, file writer |
| context.setErrorWriter(writer) | java.io.Writer | Kênh thông báo lỗi/cảnh báo do script/engine ghi | StringWriter tách riêng hoặc log writer |

Những API này làm việc với **ký tự**, không phải InputStream/OutputStream byte. Nếu input đến từ network hoặc file nhị phân, host phải giải mã byte bằng charset rõ ràng (thường UTF-8) để tạo Reader. Nếu output cần lưu vào file hoặc HTTP response, Writer tương ứng chịu trách nhiệm mã hóa ký tự thành byte.

**Phân biệt hai cách cấp Reader:**

- engine.eval(new StringReader("...script source..."), context) truyền **mã nguồn script** để engine đọc và thực thi.
- context.setReader(new StringReader("...input data...")) truyền **dữ liệu đầu vào mà script có thể tiêu thụ trong lúc chạy**.

Hai Reader này hoàn toàn khác mục đích. Ví dụ phía dưới sử dụng cả hai để chứng minh.

## 2. Cách điều khiển đầu vào với setReader/getReader

Host có thể thay nguồn input cho từng lượt eval:

~~~java
ScriptContext context = new SimpleScriptContext();
context.setReader(new StringReader("An\n"));

Object result = engine.eval("greet", context);
~~~

Đây là **đoạn minh họa đặt trong một method** sau khi có đối tượng engine phù hợp và import javax.script.*, java.io.StringReader; đoạn trên không phải chương trình chạy độc lập. Engine phải có logic **đọc context.getReader()** thì dữ liệu "An" mới thực sự được sử dụng.

Một engine có thể hỗ trợ script statement như readLine hoặc input; tên hàm do từng ngôn ngữ/engine quy định, không phải JSR 223 tự thêm lệnh input cho mọi script.

Các vấn đề thực tiễn:

1. **Đầu vào hữu hạn:** StringReader đọc đến cuối và trả EOF. Nếu một script cần input lần thứ hai, hãy cung cấp reader mới hoặc thiết kế luồng đầu vào được tái sử dụng có chủ đích.
2. **Không dùng chung reader cho request độc lập:** một lần đọc có thể tiêu thụ dữ liệu của request khác, hoặc có thể làm cạn dữ liệu cho lượt sau.
3. **Giới hạn kích thước và thời gian:** input do bên ngoài cung cấp có thể lớn, vô hạn hoặc chặn đọc. Thiết lập giới hạn trước khi truyền Reader vào engine.
4. **Charset:** nên dùng Files.newBufferedReader(path, StandardCharsets.UTF_8) khi đọc file để tránh phụ thuộc charset hệ thống.
5. **Quyền sở hữu:** host cần biết ai sẽ close Reader. Chỉ gọi context.setReader không có nghĩa ScriptContext sẽ tự đóng Reader sau eval.

Không nên chỉnh System.setIn(...) toàn JVM chỉ để xử lý một script, vì nó ảnh hưởng đến luồng khác đang chạy trong cùng tiến trình.

## 3. Điều khiển output bình thường với setWriter/getWriter

Để giữ output trong bộ nhớ thay vì để nó đi ra console:

~~~java
StringWriter captured = new StringWriter();
context.setWriter(captured);
Object result = engine.eval("greet", context);
String text = captured.toString();
~~~

Đây cũng là **mảnh code minh họa** với context/engine đã tồn tại và import java.io.StringWriter. Khi engine/script gọi context.getWriter().write(...), text đó được lưu vào StringWriter. Đối với BufferedWriter hoặc network writer, host/engine có thể cần flush() để dữ liệu xuất hiện bên nhận trước khi kết thúc.

**Object trả về từ eval không đồng nhất với output của Writer.** Script có thể vừa in nhiều dòng, vừa trả về một giá trị. Ví dụ một hàm trong script trả về tên người dùng nhưng cũng in câu chào; host cần giữ riêng hai kết quả.

Việc cấu hình Writer này **không tự bắt**:

- Java code trong engine gọi System.out.println(...) trực tiếp, không thông qua context.
- Một thư viện native, logger, subprocess hoặc API khác ghi ngoài kênh Writer.
- Những console API đặc thù của ngôn ngữ mà implementation engine không chuyển về ScriptContext.

Do đó, trước khi hứa rằng mọi output script đã được capture, phải **kiểm tra engine thực tế**. Nếu plugin/script sử dụng Java interop hoặc thư viện ngoài, cần chính sách logging và cách cô lập phù hợp ngoài ScriptContext.

## 4. Điều khiển kênh lỗi với setErrorWriter/getErrorWriter

Host nên dùng một Writer riêng cho lỗi:

~~~java
StringWriter normal = new StringWriter();
StringWriter errors = new StringWriter();
context.setWriter(normal);
context.setErrorWriter(errors);
~~~

Khi engine cố ý viết cảnh báo bằng context.getErrorWriter().write(...), nội dung được đưa vào errors, không lẫn với normal.

Nhưng có **hai hình thức lỗi khác nhau**:

1. **Văn bản lỗi/cảnh báo được viết ra errorWriter:** ví dụ một interpreter báo một warning. Đây là dữ liệu do engine gửi ra, có thể xảy ra cả khi eval thành công.
2. **ScriptException được ném bởi engine.eval:** ví dụ lỗi cú pháp hoặc runtime mà engine báo qua Java exception. Việc ném ScriptException **không bảo đảm** tự xuất hiện trong context.getErrorWriter(). Host phải bắt exception và tự ghi lỗi theo chính sách.

ScriptException có những thông tin chẩn đoán như **getMessage()**, **getFileName()**, **getLineNumber()**, **getColumnNumber()** (nếu engine cung cấp). Không phải engine nào cũng điền đầy đủ vị trí file/line/column; nên xử lý trường hợp giá trị không có.

Ví dụ host có thể xử lý:

~~~java
try {
    engine.eval(scriptSource, context);
} catch (ScriptException ex) {
    // Chính sách của host: ghi thông điệp đã lọc ra kênh lỗi.
    context.getErrorWriter().write("Script failed\n");
    context.getErrorWriter().flush();
}
~~~

Đây là **mảnh code minh họa** nằm trong method có khai báo/đảm bảo xử lý IOException và có các biến engine, scriptSource, context. Trong production nên log nguyên nhân kỹ thuật ở phía server nhưng trả thông báo được kiểm soát, tránh tiết lộ path, bí mật hay stack trace nội bộ của host. Không được coi việc catch toàn bộ Throwable rồi bỏ qua là xử lý lỗi an toàn.

## 5. Engine scope và global scope ảnh hưởng đến dữ liệu script

ScriptContext có hai scope chuẩn:

~~~text
ScriptContext.ENGINE_SCOPE = 100
ScriptContext.GLOBAL_SCOPE = 200
~~~

Mỗi scope chứa một **Bindings**, về bản chất là tập tên → Object. Phương thức context.getAttribute("name") tìm trong các scope theo thứ tự tăng dần số thứ tự: **ENGINE_SCOPE trước, GLOBAL_SCOPE sau**. Nếu một biến trùng tên ở hai nơi, giá trị ở ENGINE_SCOPE có ưu tiên.

Ví dụ:

~~~java
SimpleScriptContext context = new SimpleScriptContext();
context.setBindings(new SimpleBindings(), ScriptContext.GLOBAL_SCOPE);
context.setAttribute("prefix", "GLOBAL: ", ScriptContext.GLOBAL_SCOPE);
context.setAttribute("prefix", "ENGINE: ", ScriptContext.ENGINE_SCOPE);

System.out.println(context.getAttribute("prefix")); // ENGINE:
context.removeAttribute("prefix", ScriptContext.ENGINE_SCOPE);
System.out.println(context.getAttribute("prefix")); // GLOBAL:
~~~

Đoạn trên là một minh họa độc lập **đặt trong method có import javax.script.***. Có thể truy cập tường minh bằng context.getAttribute("prefix", ScriptContext.GLOBAL_SCOPE) nếu muốn bỏ qua luật ưu tiên.

**Lưu ý thường bị bỏ sót:** SimpleScriptContext mặc định đã có một Bindings cho ENGINE_SCOPE, nhưng **GLOBAL_SCOPE mặc định là null**. Nếu muốn đặt biến global, hãy gọi setBindings(new SimpleBindings(), ScriptContext.GLOBAL_SCOPE) trước. Với SimpleScriptContext, setAttribute trên GLOBAL_SCOPE khi chưa có bindings global là thao tác không có tác dụng; đừng tưởng biến đã được lưu.

Những phương thức khác:

| API | Kết quả/công dụng |
| --- | --- |
| getBindings(scope) | Lấy Map-like Bindings của scope được chỉ định |
| setBindings(bindings, scope) | Thay toàn bộ tập biến của scope |
| setAttribute(name, value, scope) | Ghi một biến vào scope cụ thể |
| getAttribute(name) | Tìm biến theo thứ tự scope |
| getAttribute(name, scope) | Chỉ đọc biến ở đúng scope |
| getAttributesScope(name) | Trả scope đầu tiên chứa tên; -1 nếu không có |
| removeAttribute(name, scope) | Xóa biến khỏi một scope cụ thể |
| getScopes() | Liệt kê các scope hợp lệ, có thứ tự tăng dần |

Đối với một request script độc lập, host có thể tạo **SimpleScriptContext mới** để giữ ENGINE_SCOPE, Reader, Writer và ErrorWriter riêng. Nếu GLOBAL_SCOPE chứa dữ liệu dùng chung, cần cân nhắc khả năng biến được chia sẻ giữa request và nguy cơ vô tình để lộ thông tin. Shared Bindings không phải cơ chế phân quyền.

## 6. Ví dụ Java 17 chạy được: input, output, error và scope trong một lần điều phối

JDK 17 không có JavaScript engine mặc định đáng tin cậy, nên ví dụ tạo một **MiniEngine** tối giản, triển khai ScriptEngine bằng cách kế thừa AbstractScriptEngine. Nó chỉ hiểu ba lệnh **greet**, **warn**, **fail**; không phải parser JavaScript hay runtime đa ngôn ngữ. Mục tiêu là kiểm chứng chính xác API Java **ScriptContext**.

MiniEngine:

- greet đọc một dòng từ context.getReader(), tìm prefix trong Bindings, ghi một dòng vào context.getWriter(), trả về String đã đọc.
- warn ghi một dòng vào context.getErrorWriter(), trả về null.
- fail ném ScriptException có số dòng 3; nó **không tự ghi** thông điệp lỗi ra errorWriter.
- eval(Reader, context) đọc **mã lệnh** từ Reader được truyền trực tiếp, không trộn lẫn với input data trong context.

### 6.1. Mã nguồn đầy đủ

Tạo duy nhất một file **ScriptContextDemo.java**:

~~~java
import java.io.BufferedReader;
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
import javax.script.ScriptException;
import javax.script.SimpleBindings;
import javax.script.SimpleScriptContext;

public final class ScriptContextDemo {
    public static void main(String[] args) throws Exception {
        ScriptEngine engine = new MiniEngine();
        SimpleScriptContext context = new SimpleScriptContext();
        context.setBindings(new SimpleBindings(), ScriptContext.GLOBAL_SCOPE);

        StringWriter output = new StringWriter();
        StringWriter errors = new StringWriter();
        context.setWriter(output);
        context.setErrorWriter(errors);

        context.setAttribute("prefix", "GLOBAL: ", ScriptContext.GLOBAL_SCOPE);
        context.setAttribute("prefix", "ENGINE: ", ScriptContext.ENGINE_SCOPE);
        context.setReader(new StringReader("An\n"));
        Object first = engine.eval("greet", context);

        context.removeAttribute("prefix", ScriptContext.ENGINE_SCOPE);
        context.setReader(new StringReader("Binh\n"));
        Object second = engine.eval(new StringReader("greet\n"), context);

        engine.eval("warn", context);
        try {
            engine.eval("fail", context);
        } catch (ScriptException ex) {
            System.out.println("caughtLine=" + ex.getLineNumber());
        }

        System.out.println("return1=" + first);
        System.out.println("return2=" + second);
        System.out.println("prefixScope=" +
                context.getAttributesScope("prefix"));
        System.out.println("capturedOut=" +
                output.toString().replace("\n", "|"));
        System.out.println("capturedErr=" +
                errors.toString().replace("\n", "|"));
    }

    private static final class MiniEngine extends AbstractScriptEngine {
        @Override
        public Object eval(String script, ScriptContext context)
                throws ScriptException {
            String command = script.strip();
            try {
                if (command.equals("greet")) {
                    String name = new BufferedReader(context.getReader())
                            .readLine();
                    if (name == null) {
                        throw new ScriptException("No input");
                    }
                    String prefix = String.valueOf(
                            context.getAttribute("prefix"));
                    context.getWriter().write(prefix + name + "\n");
                    context.getWriter().flush();
                    return name;
                }
                if (command.equals("warn")) {
                    context.getErrorWriter().write("WARN: demo\n");
                    context.getErrorWriter().flush();
                    return null;
                }
                if (command.equals("fail")) {
                    throw new ScriptException("Demo failure", "mini", 3);
                }
                throw new ScriptException("Unknown command: " + command);
            } catch (IOException ex) {
                throw new ScriptException(ex);
            }
        }

        @Override
        public Object eval(Reader script, ScriptContext context)
                throws ScriptException {
            try {
                StringBuilder source = new StringBuilder();
                char[] buffer = new char[256];
                int n;
                while ((n = script.read(buffer)) != -1) {
                    source.append(buffer, 0, n);
                }
                return eval(source.toString(), context);
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
            return new MiniFactory();
        }
    }

    private static final class MiniFactory implements ScriptEngineFactory {
        @Override public String getEngineName() { return "MiniEngine"; }
        @Override public String getEngineVersion() { return "1.0"; }
        @Override public List<String> getExtensions() { return List.of("mini"); }
        @Override public List<String> getMimeTypes() { return List.of(); }
        @Override public List<String> getNames() { return List.of("mini"); }
        @Override public String getLanguageName() { return "MiniCommands"; }
        @Override public String getLanguageVersion() { return "1.0"; }
        @Override public Object getParameter(String key) { return null; }
        @Override public String getMethodCallSyntax(
                String obj, String method, String... args) { return ""; }
        @Override public String getOutputStatement(String toDisplay) {
            return "";
        }
        @Override public String getProgram(String... statements) {
            return String.join("\n", statements);
        }
        @Override public ScriptEngine getScriptEngine() {
            return new MiniEngine();
        }
    }
}
~~~

MiniFactory chỉ là implementation tối thiểu của giao diện factory cần thiết cho ví dụ. Các phương thức trả chuỗi trống/không có tham số ngôn ngữ **không phải mô hình factory cho một engine sản xuất**. Chương trình tạo new MiniEngine() trực tiếp; nó **không đăng ký** MiniEngine với ScriptEngineManager. Trong dự án thực, factory của engine phải khai báo chính xác tên, syntax và tính năng mà runtime đó thực sự hỗ trợ.

### 6.2. Biên dịch và chạy

Ở thư mục chứa **ScriptContextDemo.java**, chạy bằng JDK 17 hoặc mới hơn:

~~~powershell
javac --release 17 -encoding UTF-8 ScriptContextDemo.java
java ScriptContextDemo
~~~

Trên Linux/macOS hai lệnh giống như vậy; cần cài JDK để có javac. Tên file phải khớp public class ScriptContextDemo.

**Stdout chính xác:**

~~~text
caughtLine=3
return1=An
return2=Binh
prefixScope=200
capturedOut=ENGINE: An|GLOBAL: Binh|
capturedErr=WARN: demo|
~~~

Ví dụ trên đã được **biên dịch bằng javac --release 17 và chạy thực tế**. Trong stdout, dấu | là ký hiệu mà code chính trong main dùng để **thay dấu xuống dòng** của output đã capture, không phải ký tự mà MiniEngine gửi vào Writer lúc đầu.

### 6.3. Giải thích chính xác từng dòng

- **caughtLine=3:** lệnh fail ném ScriptException có line number là 3 và host bắt được. Exception này **không tự đi vào errorWriter**.
- **return1=An:** đây là giá trị **Object** trả từ engine.eval("greet", context), không phải dòng output.
- **return2=Binh:** ở lượt thứ hai, source của script được cấp qua eval(new StringReader("greet\n"), context), trong khi dữ liệu người dùng được đọc qua context.getReader() riêng.
- **prefixScope=200:** sau khi xóa prefix khỏi ENGINE_SCOPE, getAttributesScope trả về GLOBAL_SCOPE. Trước khi xóa, biến trùng tên trong ENGINE_SCOPE (100) được ưu tiên.
- **capturedOut=ENGINE: An|GLOBAL: Binh|:** cả hai lời chào đi vào **StringWriter output**, lần đầu dùng biến engine, lần sau fallback sang biến global.
- **capturedErr=WARN: demo|:** lệnh warn ghi vào **StringWriter errors**. Lệnh fail không tự làm tăng nội dung của errorWriter.

Ví dụ có hai lần thực thi liên tiếp dùng cùng SimpleScriptContext để dễ nhìn thấy sự thay đổi scope. Trong dịch vụ nhiều người dùng, **không nên sử dụng lại context chứa input/output/error của user này cho user khác**. Thay vì mô phỏng các request đồng thời bằng một context dùng chung, hãy tạo context riêng cho mỗi request.

## 7. Cách dùng ScriptContext với engine thật

Nếu ứng dụng đã cài một ScriptEngine tương thích JSR 223, cách dùng API cơ bản sẽ giống ví dụ này:

~~~java
ScriptEngine engine = new ScriptEngineManager()
        .getEngineByName("language-name");

if (engine == null) {
    throw new IllegalStateException("Script engine not installed");
}

SimpleScriptContext ctx = new SimpleScriptContext();
ctx.setReader(new StringReader("input for script\n"));
ctx.setWriter(new StringWriter());
ctx.setErrorWriter(new StringWriter());

Object value = engine.eval(scriptSource, ctx);
~~~

Đây là **đoạn minh họa tích hợp, không tự chạy độc lập**: cần import javax.script.*, java.io.*, có biến scriptSource, và phải thay language-name bằng tên engine được triển khai thực sự. Tên/lệnh đọc input trong script **phụ thuộc vào ngôn ngữ**. Đừng giả định getEngineByName("JavaScript") luôn trả engine khác null trên Java 17+.

So với chỉ dùng engine.eval(scriptSource), overload **eval(scriptSource, ctx)** buộc engine nhận **ngữ cảnh do host cung cấp** thay vì phụ thuộc vào default context của engine. Cách này hữu ích khi một engine instance cần được điều phối cho nhiều lượt eval tuần tự với reader/writer và scope khác nhau, nhưng vẫn phải xem tài liệu thread safety của engine.

### ScriptContext truyền tường minh khác engine.getContext()

Có hai cách cấu hình phổ biến:

1. **engine.setContext(ctx); engine.eval(script);** thay context mặc định gắn với đối tượng engine.
2. **engine.eval(script, ctx);** đưa một context tường minh cho một lời gọi eval cụ thể.

Cách (2) thường dễ quản lý hơn trong host có nhiều request vì không cần thay trạng thái default context được giữ bên trong engine. Tuy nhiên **nó không bảo đảm engine instance an toàn để gọi đồng thời**; engine vẫn có thể giữ trạng thái bên trong ngoài ScriptContext.

Các phương thức engine.put("key", value) và engine.get("key") thường thao tác **ENGINE_SCOPE của default context gắn với engine**. Chúng không nhất thiết tác động đến **SimpleScriptContext riêng** mà ta truyền vào eval(script, ctx). Vì vậy, để điều khiển biến theo request, hãy thao tác trực tiếp với ctx.setAttribute hoặc ctx.getBindings.

## 8. Đưa input/output/error ra file thay vì StringWriter

Với một tác vụ được kiểm soát và có thư mục riêng, host có thể mở Reader/Writer qua Files:

~~~java
try (Reader input = Files.newBufferedReader(
             inputPath, StandardCharsets.UTF_8);
     Writer output = Files.newBufferedWriter(
             outputPath, StandardCharsets.UTF_8);
     Writer errors = Files.newBufferedWriter(
             errorPath, StandardCharsets.UTF_8)) {

    SimpleScriptContext ctx = new SimpleScriptContext();
    ctx.setReader(input);
    ctx.setWriter(output);
    ctx.setErrorWriter(errors);

    engine.eval(scriptSource, ctx);
    output.flush();
    errors.flush();
}
~~~

Đây là **đoạn minh họa đặt trong một method có xử lý IOException và ScriptException**, có các biến inputPath, outputPath, errorPath, engine, scriptSource và import java.nio.file.Files, java.nio.charset.StandardCharsets, java.io.Reader/Writer, javax.script.SimpleScriptContext. Nó không phải file tự biên dịch độc lập. File writer mặc định có thể tạo mới/truncate file đích tùy OpenOption; cần kiểm tra chính sách ghi đè trước khi chạy với dữ liệu thật.

**try-with-resources** là nơi host chịu trách nhiệm close những stream mà host đã mở. Bản thân ScriptContext không cam kết close tài nguyên sau eval. Nếu Writer được chia sẻ cho nhiều request hoặc do môi trường khác quản lý, chính sách close phải khác; không được đóng Writer tùy tiện khi engine đang còn sử dụng.

Nếu eval ném ScriptException, khối try-with-resources vẫn đóng stream, nhưng host nên bắt exception bên ngoài hoặc bên trong để ghi trạng thái lỗi. Nếu muốn bảo đảm flush và lưu lỗi ngay trong file trước khi đóng, phải thiết kế thứ tự catch/finally phù hợp. Khi ghi qua mạng, writer còn có thể bị chặn, đầy buffer hoặc lỗi I/O; cần timeout và giới hạn đầu ra phù hợp.

## 9. ErrorWriter, exception và logging phải được tách đúng

Trong một hệ thống thực, nên phân biệt ít nhất bốn loại thông tin:

| Kênh | Ví dụ | Cách thu thập |
| --- | --- | --- |
| Script output | Dữ liệu người dùng muốn tạo | context.getWriter() do engine hỗ trợ |
| Script diagnostic text | Cảnh báo của interpreter, lỗi không ném exception | context.getErrorWriter() do engine hỗ trợ |
| Java exception | ScriptException và nguyên nhân gốc | Host catch và xử lý trực tiếp |
| Host/framework/JVM logs | Logger, System.err, thông báo tiến trình | Hệ thống logging/observability riêng |

Không dùng context.setErrorWriter để giả định đã thu toàn bộ System.err. Không lấy output errorWriter có nội dung làm dấu hiệu biên dịch/thực thi chắc chắn thất bại; một script có thể phát warning rồi trả kết quả thành công. Ngược lại, errorWriter rỗng cũng không chứng minh eval thành công, vì exception có thể được ném trực tiếp.

Khi cần trả lỗi về client, có thể xây dựng response dạng dữ liệu có cấu trúc:

~~~text
ExecutionResult
  status: SUCCESS | SCRIPT_ERROR | ENGINE_ERROR | TIMEOUT
  returnValue: giá trị đã qua kiểm tra/chuyển đổi
  outputText: những ký tự mà Writer thường đã nhận
  diagnosticText: những ký tự mà ErrorWriter đã nhận
  errorMessage: thông điệp an toàn từ exception nếu có
  line: vị trí lỗi nếu engine cung cấp
~~~

Khối trên chỉ là **sơ đồ dữ liệu**, không phải class Java runnable. Nên tách dữ liệu raw của engine khỏi thông tin hiển thị cho người dùng; sanitize dữ liệu trước khi đưa lên UI, đặc biệt nếu output có HTML hay thông tin riêng tư.

Trong các runtime có console API riêng, nếu cần capture console.log, print hoặc stack trace, phải đọc tài liệu của **đúng ScriptEngine** để biết chúng có được chuyển về context Writer hay không. ScriptContext không ép buộc mọi đường output của ngôn ngữ đều dùng ba kênh của nó.

## 10. Mỗi request một context: tránh rò dữ liệu và lỗi cạnh tranh

Với một dịch vụ chạy script cho nhiều người dùng, một cấu hình thường hợp lý là:

~~~text
Request A → ScriptContext A → Reader A / Writer A / ErrorWriter A / Bindings A
Request B → ScriptContext B → Reader B / Writer B / ErrorWriter B / Bindings B
                                  |
                       ScriptEngine/engine pool
                       theo chính sách concurrency
~~~

Các nguyên tắc cần quyết định rõ:

- **Tạo context riêng cho mỗi tác vụ** để không trộn input/output của các request.
- **Không chia sẻ mutable Bindings chứa dữ liệu riêng tư** giữa user; GLOBAL_SCOPE không phải biên bảo mật.
- **Không thay System.out/System.err/System.in toàn JVM** để chuyển hướng một script; làm vậy sẽ gây nhiễu giữa các thread và cả host.
- **Không cho Writer phát triển vô hạn** nếu script có thể in số lượng lớn dữ liệu; dùng giới hạn số ký tự hoặc stream được kiểm soát.
- **Không dùng chung ScriptEngine một cách mặc định trong nhiều thread.** Kiểm tra hợp đồng của engine và thông tin threading nếu có, thường qua ScriptEngineFactory.getParameter("THREADING"). Những giá trị/giới hạn mà engine công bố cần được hiểu theo tài liệu của chính implementation đó.
- **Không dùng ScriptContext làm sandbox.** Một script engine có thể cho script gọi vào class Java hoặc thao tác ngoài context tùy ngôn ngữ và cấu hình.
- **Giới hạn thời gian/chạy vô hạn** không phải trách nhiệm của ScriptContext; khi chạy script không đáng tin, cần tiến trình/OS container và giới hạn CPU, RAM, I/O, network phù hợp.

Lưu ý trường hợp host muốn "đồng thời" nhiều script: việc mỗi request có context riêng **không làm engine tự nhiên thread-safe**. Một số engine giữ biến toàn cục hoặc internal runtime state; cần tạo engine mới cho mỗi request, đồng bộ hoặc quản lý engine pool theo tài liệu cụ thể.

## 11. Những lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| setWriter đã gọi nhưng console vẫn in ra System.out | Engine/library ghi trực tiếp vào System.out hoặc logger | Kiểm tra implementation engine và đường output cụ thể |
| ErrorWriter trống dù eval ném lỗi | Exception không tự chuyển thành text lỗi | Catch ScriptException và tạo diagnostic có cấu trúc |
| Input luôn EOF | Reader đã bị đọc hết ở lần eval trước | Cấp Reader mới theo tác vụ/lượt đọc |
| Eval không thấy biến prefix vừa đặt | Đặt vào default context khác context truyền vào eval | Kiểm tra đúng instance và scope |
| Biến global không tồn tại | Chưa setBindings cho GLOBAL_SCOPE của SimpleScriptContext | Khởi tạo Global Bindings rồi setAttribute |
| ENGINE_SCOPE ghi đè GLOBAL_SCOPE | Lookup tìm scope nhỏ hơn trước | Dùng getAttribute(name, scope) hoặc xóa biến engine |
| Có hai Reader nên dữ liệu bị "đọc sai" | Nhầm Reader chứa script source với context Reader chứa input | Tách hai luồng theo chức năng |
| getEngineByName trả null | Chưa cài/đăng ký engine ngôn ngữ | Kiểm tra runtime JDK, engine JAR và ScriptEngineFactory |
| Writer bị đóng quá sớm | Host đóng trước khi engine ghi hoặc flush | Quản lý ownership, wait/cancel task rồi close |
| Output/error bị trộn giữa user | Dùng chung context, writer hoặc mutable bindings | Tạo riêng từng tác vụ, theo dõi request ID |
| Script không kết thúc | Đầu vào chặn, vòng lặp vô hạn, I/O chờ | Timeout và giới hạn tiến trình/tài nguyên |
| Một ScriptException có file/line không như mong đợi | Engine không cung cấp metadata hoặc tự đặt tên file | Kiểm tra getFileName/getLineNumber và contract của engine |

Một đoạn mã thường gây lỗi là:

~~~java
engine.put("user", "An");
engine.eval(scriptSource, mySeparateContext);
~~~

Hai câu trên là **minh họa một tình huống có thể sai**, vì engine.put thao tác default ENGINE_SCOPE của engine, không nhất thiết là ENGINE_SCOPE của mySeparateContext. Muốn biến user hiện diện trong lần eval này, viết:

~~~java
mySeparateContext.setAttribute(
        "user", "An", ScriptContext.ENGINE_SCOPE);
engine.eval(scriptSource, mySeparateContext);
~~~

Các mảnh code dùng biến engine, scriptSource, mySeparateContext đã tồn tại; không phải class Java độc lập.

## 12. Quy trình QA cho một script host

Trước khi tích hợp ScriptContext vào runtime extensibility:

1. **Xác định engine:** ngôn ngữ, phiên bản, JSR 223 support, cơ chế cài/đăng ký ScriptEngineFactory.
2. **Chuẩn bị context mỗi request:** tạo ENGINE_SCOPE riêng; GLOBAL_SCOPE chỉ dùng với dữ liệu chung đã quyết định.
3. **Kiểm soát input:** setReader với Reader đã biết nguồn, charset, giới hạn kích thước và chính sách EOF.
4. **Tách output và lỗi:** setWriter/setErrorWriter sang hai đích có thể kiểm tra; flush/close đúng ownership.
5. **Truyền context tường minh:** ưu tiên engine.eval(script, ctx) khi muốn cô lập lần chạy so với default context.
6. **Kiểm tra return value:** tách giá trị Object trả từ eval khỏi những ký tự script in ra.
7. **Bắt ScriptException:** lấy thông tin file/line nếu có, không dựa hoàn toàn vào ErrorWriter.
8. **Thử tình huống xấu:** script không ghi gì, ghi rất dài, Reader rỗng, Writer lỗi, nội dung lỗi có ký tự Unicode hoặc dữ liệu nhạy cảm.
9. **Kiểm tra luồng thật của engine:** đảm bảo lệnh input/output/error của ngôn ngữ thực sự tôn trọng ScriptContext.
10. **Cô lập execution nếu cần:** ScriptContext chỉ kiểm soát API I/O được engine dùng; không thay ranh giới tiến trình hay security policy.

### Câu hỏi tự kiểm tra

**Đã setWriter rồi, có chắc mọi System.out.println bên trong plugin bị bắt không?** Không. Việc ghi trực tiếp vào System.out là cơ chế khác; chỉ được capture nếu engine/plugin chủ động dùng Writer của context hoặc host thiết lập biện pháp riêng có kiểm soát.

**eval ném ScriptException thì ErrorWriter luôn có văn bản lỗi không?** Không. Hai cơ chế độc lập; host cần catch exception.

**Tại sao getAttribute("prefix") dùng giá trị ENGINE_SCOPE dù GLOBAL_SCOPE cũng có cùng tên?** Vì scope 100 đứng trước 200 theo thứ tự lookup.

**ScriptEngine.eval(Reader, context) đọc gì?** Reader truyền trực tiếp vào eval chứa **source của script**; context.getReader chứa **input do script tiêu thụ** nếu engine hỗ trợ.

**Dùng eval(script, context) có đảm bảo đồng thời nhiều luồng không?** Không. Context riêng chỉ là một phần của thiết kế; thread safety của engine và các shared resources phải được kiểm chứng riêng.

**ScriptContext có ngăn script truy cập file/network không?** Không. Nó chỉ là đối tượng ngữ cảnh I/O/Bindings trong JSR 223, không phải cơ chế sandbox.

### Tài liệu chuẩn

- Oracle Java SE 17 **javax.script.ScriptContext**: https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptContext.html
- Oracle Java SE 17 **javax.script.SimpleScriptContext**: https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/SimpleScriptContext.html
- Oracle Java SE 17 **javax.script.ScriptEngine**: https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptEngine.html
- Oracle Java SE 17 **javax.script.AbstractScriptEngine**: https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/AbstractScriptEngine.html
- Oracle Java SE 17 **javax.script.ScriptException**: https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptException.html
- OpenJDK **JEP 372: Remove the Nashorn JavaScript Engine**: https://openjdk.org/jeps/372

**Kết luận:** ScriptContext giúp host truyền **Reader**, **Writer**, **ErrorWriter** và **Bindings** cho từng lần thực thi script mà không cần đổi luồng hệ thống toàn JVM. Để một tính năng nhúng script chạy đúng, phải phân biệt script source với input data, output text với return value, diagnostic writer với ScriptException, và ngữ cảnh API với cơ chế cô lập thực thi thực sự.

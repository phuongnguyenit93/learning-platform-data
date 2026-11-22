# 17.5 Kiểm tra khả năng `Compilable`, tái sử dụng `CompiledScript`

Khi nhúng ngôn ngữ kịch bản vào ứng dụng Java bằng **JSR-223** (`javax.script`), một chương trình thường phải chạy **cùng mã script** với **nhiều bộ dữ liệu**. Nếu mỗi lần đều gọi `ScriptEngine.eval(source, ...)`, script engine có thể phải phân tích cú pháp/biên dịch lại phần mã nguồn. Một số engine cung cấp khả năng **biên dịch trước và tái sử dụng** dưới dạng interface **`Compilable`** cùng object **`CompiledScript`**.

Tuy nhiên, `Compilable` là **khả năng tùy chọn của từng engine**, không phải hợp đồng mà mọi `ScriptEngine` đều phải thực hiện. Chương trình cần:

1. **Tìm một engine đang thực sự được cài đặt**, không giả định một ngôn ngữ có sẵn theo JDK.
2. **Kiểm tra `engine instanceof Compilable`** trước khi ép kiểu.
3. Nếu hỗ trợ, **compile một lần** cho một script ổn định, giữ `CompiledScript` để chạy nhiều lượt.
4. Mỗi lượt truyền **`Bindings` hoặc `ScriptContext` phù hợp** để thay dữ liệu, không biên dịch lại chỉ vì giá trị đầu vào thay đổi.
5. Nếu engine không hỗ trợ, **fallback sang `ScriptEngine.eval`** bằng mã nguồn.
6. Quản lý **vòng đời engine, trạng thái, thread safety, lỗi và giới hạn tin cậy** của script được chạy.

Bài sử dụng **Java 17+**. Điểm đặc biệt cần nhớ: Java SE 17 vẫn có module **`java.scripting`**, nhưng **không bảo đảm một JavaScript engine được đóng gói sẵn**. Nashorn đã bị loại khỏi JDK từ Java 15; muốn chạy JavaScript, cần một provider tương thích JSR-223 trên classpath/module path và cấu hình discovery phù hợp. Ví dụ chạy độc lập trong bài sẽ dùng **engine số học tối giản tự viết** để kiểm chứng API mà không cần tải thư viện bên ngoài.

## 1. Phân biệt bốn đối tượng thường gặp

| Đối tượng | Vai trò | Điều không được nhầm |
| --- | --- | --- |
| `ScriptEngineManager` | Tìm các `ScriptEngineFactory` đã được đăng ký bằng service-provider mechanism | Không phải chính engine; không tự tạo một JavaScript interpreter nếu thiếu provider |
| `ScriptEngine` | Chạy script, giữ default `ScriptContext` và cho phép truyền dữ liệu vào bằng `Bindings` | **Không nhất thiết** có khả năng biên dịch trước |
| `Compilable` | Interface tùy chọn với `compile(String)` và `compile(Reader)` | Có khả năng compile không đồng nghĩa có thể chia sẻ engine tự do giữa threads |
| `CompiledScript` | Object giữ kết quả của một lần compile, có thể gọi `eval()`, `eval(Bindings)`, `eval(ScriptContext)` | **Gắn với engine tạo ra nó**; không phải bytecode portable giữa nhiều engine/JVM |

Mô hình:

~~~text
ScriptEngineManager
      │ tìm provider theo name / extension / mime type
      ▼
ScriptEngine instance
      │
      ├── instanceof Compilable == false
      │        │
      │        └── engine.eval(source, bindings)  [fallback]
      │
      └── instanceof Compilable == true
               │
               ▼
          compile(source)  [chạy một lần cho script được cache]
               │
               ▼
          CompiledScript
               │
        ┌──────┼─────────────┐
        ▼      ▼             ▼
      eval(A) eval(B)       eval(C)
        │      │             │
        ▼      ▼             ▼
     dữ liệu A  dữ liệu B    dữ liệu C
~~~

Ở đây chữ "compile" là theo định nghĩa **scripting engine**: engine có thể tạo opcode, AST, mã trung gian hay class; không bắt buộc dùng `javac` hay phát sinh file `.class`. Tối ưu hiệu năng thực tế còn tùy implementation.

## 2. Tìm engine và kiểm tra `Compilable` đúng cách

`ScriptEngineManager` tìm provider tương thích JSR-223 bằng `ServiceLoader`. Không có provider phù hợp thì `getEngineByName` có thể trả về **`null`**.

~~~java
import javax.script.*;

ScriptEngineManager manager = new ScriptEngineManager();
ScriptEngine engine = manager.getEngineByName("JavaScript");

if (engine == null) {
    throw new IllegalStateException(
        "Chưa tìm thấy JavaScript JSR-223 provider; kiểm tra dependencies");
}
if (engine instanceof Compilable compiler) {
    CompiledScript prepared = compiler.compile("1 + 2");
    Object result = prepared.eval();
} else {
    Object result = engine.eval("1 + 2");
}
~~~

**Đây là đoạn minh họa** đặt trong phạm vi method với các import phù hợp, **không phải chương trình độc lập có stdout ổn định**: tên engine, cú pháp và kết quả phụ thuộc provider thực tế.

Cách kiểm tra môi trường trước khi chọn engine:

~~~java
ScriptEngineManager manager = new ScriptEngineManager();
for (ScriptEngineFactory factory : manager.getEngineFactories()) {
    System.out.println(factory.getEngineName() + " / " +
            factory.getLanguageName() + " / " + factory.getNames());
}
~~~

Đây cũng là đoạn minh họa. Danh sách có thể rỗng trên một JDK 17 cài mặc định; **không** coi đó là lỗi của `ScriptEngineManager`. Cần thêm provider của ngôn ngữ mong muốn, đúng phiên bản, class loader và module/service configuration theo tài liệu của provider.

**Vì sao nên kiểm tra bằng `instanceof` thay vì cast trực tiếp?**

~~~java
CompiledScript compiled = ((Compilable) engine).compile(source);
~~~

Đoạn trên **có thể gây `ClassCastException`** nếu engine không triển khai `Compilable`. `ScriptEngine` và `Compilable` là hai contract khác nhau; `Invocable` cũng là capability độc lập, không suy từ sự hiện diện của `Compilable`.

### 2.1. Không compile lặp ngay trong mỗi request

Cách chưa tốt khi mã script không đổi:

~~~java
Object process(ScriptEngine engine, String source, Bindings vars)
        throws ScriptException {
    if (engine instanceof Compilable c) {
        return c.compile(source).eval(vars); // mỗi lần vẫn COMPILE
    }
    return engine.eval(source, vars);
}
~~~

Đây là method minh họa. Mặc dù có `Compilable`, lời gọi `compile` vẫn nằm trong đường xử lý mỗi lượt — mất lợi ích của tái sử dụng.

Thay vào đó hãy **prepare trước khi phục vụ các request**, lưu object `CompiledScript` và gọi `eval` với `Bindings` riêng. Phần 5 có cả một mẫu `Prepared` dùng được cho cả engine hỗ trợ compile và engine không hỗ trợ.

## 3. `compile` khác `eval` về thời điểm

Cùng một source:

~~~text
"price * quantity + fee"
~~~

Giả sử:

~~~text
Order A: price=10, quantity=3, fee=2 -> 32
Order B: price= 4, quantity=5, fee=1 -> 21
~~~

Sơ đồ đường chạy **không tái sử dụng**:

~~~text
Order A
   │
   ▼
engine.eval(source, bindingsA)
   │ parse/compile theo cách của provider (có thể)
   ▼
32

Order B
   │
   ▼
engine.eval(source, bindingsB)
   │ parse/compile theo cách của provider (có thể)
   ▼
21
~~~

Sơ đồ đường chạy **có tái sử dụng**:

~~~text
Một lần chuẩn bị:
    compiled = ((Compilable) engine).compile(source)
                         │
                 giữ compiled
                         │
             ┌───────────┴──────────┐
             ▼                      ▼
       compiled.eval(A)        compiled.eval(B)
             │                      │
             ▼                      ▼
            32                     21
~~~

Theo Javadoc, `CompiledScript` có thể chạy lại mà **không cần parse lại** mã nguồn; implementation có thể giữ Java class, class file, opcode hoặc cấu trúc khác. Không nên khẳng định rằng mọi engine luôn tăng tốc đáng kể: script rất ngắn, bước thực thi nặng, chi phí binding/call hoặc cơ chế cache nội bộ của engine có thể khiến chênh lệch nhỏ.

**Compile không đồng nghĩa thực thi nghiệp vụ.** Một engine có thể giải quyết import/module, kiểm tra cú pháp hay chuẩn bị tài nguyên khi compile; side effect và thời điểm thực thi cụ thể cần theo contract của ngôn ngữ/provider. Tránh viết ứng dụng phụ thuộc vào giả định “compile hoàn toàn không thể tạo side effect” trong mọi engine.

## 4. Ba cách thực thi `CompiledScript`: context nào được dùng?

Đây là kiến thức quan trọng nhất để tránh rò dữ liệu giữa các lần chạy.

| API | `ENGINE_SCOPE` và môi trường | Khi nên dùng |
| --- | --- | --- |
| `compiled.eval()` | Dùng **default `ScriptContext`** của engine liên kết | Script test hoặc môi trường mặc định chủ động được quản lý |
| `compiled.eval(bindings)` | Dùng **Bindings truyền vào làm `ENGINE_SCOPE`** cho lượt này. Reader, Writer và `GLOBAL_SCOPE` từ default context của engine được dùng | Cùng script, nhiều bộ biến đầu vào khác nhau |
| `compiled.eval(scriptContext)` | Dùng **ScriptContext tường minh**: scope, reader/writer, error writer | Cần tùy chỉnh I/O, global scope, policy hoặc context theo request |

### 4.1. `Bindings` không phải bản sao của compiled program

~~~java
Bindings first = engine.createBindings();
first.put("price", 10);
first.put("quantity", 3);
first.put("fee", 2);

Object firstResult = compiled.eval(first);
~~~

Đây là đoạn minh họa, giả định `engine` và `compiled` đã có. `Bindings` là map khóa `String` sang giá trị Java, **không phải source code** và không phải `CompiledScript` thứ hai. Khi truyền bộ `Bindings` khác, cùng chương trình đã biên dịch nhận dữ liệu mới.

`CompiledScript.eval(Bindings)` **không cần và không tự động thay default `ENGINE_SCOPE` của engine** bằng map được truyền. Vì vậy nếu script có thể thay đổi biến, các thay đổi trong `Bindings` truyền vào có thể được nhìn thấy theo contract của engine, nhưng không nên coi map này mặc nhiên bất biến hay được copy sâu.

### 4.2. `eval()` dùng trạng thái mặc định của engine

~~~java
engine.put("price", 10);
engine.put("quantity", 3);
engine.put("fee", 2);
Object result = compiled.eval();
~~~

Đây là ví dụ minh họa. `ScriptEngine.put` đặt biến vào default `ENGINE_SCOPE`, vì `compiled.eval()` dùng default context của engine. Nếu ứng dụng web nhiều request cùng thay `engine.put("userId", ...)`, các lượt có thể thấy trạng thái xen kẽ; **đừng dùng chung default bindings theo request không được đồng bộ**.

### 4.3. `ScriptContext` cho phép quản lý scope và I/O

~~~java
SimpleScriptContext ctx = new SimpleScriptContext();
Bindings attrs = engine.createBindings();
attrs.put("price", 10);
attrs.put("quantity", 3);
attrs.put("fee", 2);
ctx.setBindings(attrs, ScriptContext.ENGINE_SCOPE);
ctx.setWriter(new java.io.StringWriter());
Object result = compiled.eval(ctx);
~~~

Đây là đoạn minh họa, với `engine`/`compiled` đã có. Dùng `ScriptContext` khi cần Writer/Reader riêng cho mỗi lượt, hoặc cần kiểm soát `GLOBAL_SCOPE` tường minh.

Theo quy tắc `ScriptContext.getAttribute(name)`, scope được tra theo thứ tự ưu tiên. Nếu một tên tồn tại ở cả `ENGINE_SCOPE` và `GLOBAL_SCOPE`, giá trị engine scope được ưu tiên. Khi dùng `eval(Bindings)`, GLOBAL_SCOPE của default context **vẫn có thể tham gia tra cứu**; nếu cần cô lập toàn bộ dữ liệu, hãy tạo context và giới hạn rõ các scope cùng đối tượng Java có thể truy cập.

### 4.4. `eval(null)` không tương đương truyền một map rỗng

Trong overload `CompiledScript.eval(Bindings)`, truyền `null` theo Javadoc có tác dụng giống `eval(getEngine().getContext())` — tức là **dùng default context**. Một `new SimpleBindings()` rỗng lại tạo **ENGINE_SCOPE rỗng** (có thể vẫn thừa hưởng GLOBAL_SCOPE), do đó kết quả có thể khác.

Đừng cố dùng `null` để “xóa các biến của lượt trước”. Khi cần dọn trạng thái, tạo `Bindings` mới hoặc context mới có chính sách rõ ràng.

## 5. Thiết kế khả năng fallback: chuẩn bị một lần, thực thi nhiều lần

Một cách an toàn hơn là xây một object chuẩn bị, giữ lại `ScriptEngine`, source và `CompiledScript` nếu có:

~~~java
record Prepared(ScriptEngine engine, String source, CompiledScript compiled) {
    Object eval(Bindings variables) throws ScriptException {
        return compiled != null
                ? compiled.eval(variables)
                : engine.eval(source, variables);
    }
}

static Prepared prepare(ScriptEngine engine, String source)
        throws ScriptException {
    CompiledScript compiled = engine instanceof Compilable compiler
            ? compiler.compile(source)
            : null;
    return new Prepared(engine, source, compiled);
}
~~~

**Đây là các đoạn phương thức/record minh họa**, không phải file Java độc lập. Mẫu hoàn chỉnh ở phần 6 chứa code tương ứng và được kiểm chứng.

Cần lưu ý:

- `prepare` gọi `compile` tối đa một lần **trên mỗi Prepared**.
- `Prepared` giữ **cùng engine** đã compile; không lấy một engine mới từ manager cho mỗi `eval` rồi dùng compiled object cũ.
- Nếu engine không hỗ trợ `Compilable`, `compiled` là `null` và mỗi lần dùng `engine.eval(source, variables)`; đây là **fallback đúng chức năng**, không phải đã compile được.
- Một `CompiledScript` **không tự độc lập với state engine**. Javadoc nói nó gắn với engine tạo ra nó; những thay đổi state khi chạy có thể hiện ra ở lần chạy khác.
- `Prepared` ở ví dụ **không tự thêm đồng bộ**; muốn dùng đa luồng phải tuân thủ contract của engine/provider.

Nếu ngôn ngữ có những biến globals hoặc side effect, chỉ truyền `Bindings` riêng không nhất thiết cô lập hoàn toàn trạng thái bên trong interpreter; xem phần 8.

## 6. Chương trình Java 17 độc lập, không cần JavaScript provider

Để minh họa có kết quả **chạy và đối chiếu stdout được trên một JDK 17 tiêu chuẩn**, ta xây một **engine dạy học** chỉ hiểu cú pháp số học rất hẹp:

~~~text
identifier * identifier + identifier
~~~

Ví dụ `price * quantity + fee`. Khi `compile`, engine phân tích nguồn và lưu ba **tên biến** vào cấu trúc `Expression`; khi `eval`, nó đọc **giá trị số thực tế** từ context. Nhờ đó có thể đếm **parse một lần, execute nhiều lần**. Một engine thứ hai dùng cùng cú pháp nhưng **không implement `Compilable`**, cho thấy nhánh fallback.

**Phạm vi demo:** `TinyEngine` không phải JavaScript engine, parser đầy đủ, sandbox hay provider dùng trong production; `TinyFactory` chỉ là metadata tối thiểu phục vụ demo, **không đăng ký vào `ScriptEngineManager`**. Demo không tải thư viện ngoài hay nhận mã bất kỳ từ Internet.

Tạo file **`CompilableReuseDemo.java`** với toàn bộ nội dung:

~~~java
import java.io.IOException;
import java.io.Reader;
import java.io.StringReader;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import javax.script.*;

public final class CompilableReuseDemo {
    private static final String SOURCE = "price * quantity + fee";
    private static final Pattern EXPRESSION = Pattern.compile(
            "\\s*([A-Za-z][A-Za-z0-9_]*)\\s*\\*\\s*" +
            "([A-Za-z][A-Za-z0-9_]*)\\s*\\+\\s*" +
            "([A-Za-z][A-Za-z0-9_]*)\\s*");

    private record Expression(String left, String right, String extra) {
        double execute(ScriptContext context) throws ScriptException {
            return number(context, left) * number(context, right)
                    + number(context, extra);
        }
    }

    private static Expression parse(String source) throws ScriptException {
        Matcher match = EXPRESSION.matcher(source);
        if (!match.matches()) {
            throw new ScriptException("Only 'a * b + c' is supported");
        }
        return new Expression(match.group(1), match.group(2), match.group(3));
    }

    private static double number(ScriptContext context, String name)
            throws ScriptException {
        Object value = context.getAttribute(name);
        if (!(value instanceof Number numeric)) {
            throw new ScriptException("Missing numeric variable: " + name);
        }
        return numeric.doubleValue();
    }

    private static String read(Reader reader) throws ScriptException {
        try {
            StringBuilder text = new StringBuilder();
            char[] buffer = new char[1024];
            for (int n; (n = reader.read(buffer)) != -1;) {
                text.append(buffer, 0, n);
            }
            return text.toString();
        } catch (IOException e) {
            throw new ScriptException(e);
        }
    }

    static class TinyEngine extends AbstractScriptEngine {
        int parses;
        int evaluations;

        Expression parseOnce(String source) throws ScriptException {
            Expression expression = parse(source);
            parses++;
            return expression;
        }

        Object execute(Expression expression, ScriptContext context)
                throws ScriptException {
            evaluations++;
            return expression.execute(context);
        }

        @Override
        public Object eval(String source, ScriptContext context)
                throws ScriptException {
            return execute(parseOnce(source), context);
        }

        @Override
        public Object eval(Reader source, ScriptContext context)
                throws ScriptException {
            return eval(read(source), context);
        }

        @Override
        public Bindings createBindings() {
            return new SimpleBindings();
        }

        @Override
        public ScriptEngineFactory getFactory() {
            return new TinyFactory();
        }
    }

    static final class CompilingTinyEngine extends TinyEngine implements Compilable {
        int compilations;

        @Override
        public CompiledScript compile(String source) throws ScriptException {
            Expression expression = parseOnce(source);
            compilations++;
            return new CompiledScript() {
                @Override
                public Object eval(ScriptContext context) throws ScriptException {
                    return execute(expression, context);
                }

                @Override
                public ScriptEngine getEngine() {
                    return CompilingTinyEngine.this;
                }
            };
        }

        @Override
        public CompiledScript compile(Reader source) throws ScriptException {
            return compile(read(source));
        }
    }

    static final class TinyFactory implements ScriptEngineFactory {
        public String getEngineName() { return "Tiny arithmetic demonstration"; }
        public String getEngineVersion() { return "1"; }
        public List<String> getExtensions() { return List.of("tiny"); }
        public List<String> getMimeTypes() { return List.of("text/x-tiny"); }
        public List<String> getNames() { return List.of("tiny"); }
        public String getLanguageName() { return "TinyArithmetic"; }
        public String getLanguageVersion() { return "1"; }
        public Object getParameter(String key) {
            return switch (key) {
                case ScriptEngine.ENGINE -> getEngineName();
                case ScriptEngine.ENGINE_VERSION -> getEngineVersion();
                case ScriptEngine.LANGUAGE -> getLanguageName();
                case ScriptEngine.LANGUAGE_VERSION -> getLanguageVersion();
                case ScriptEngine.NAME -> getNames().get(0);
                default -> null;
            };
        }
        public String getMethodCallSyntax(String obj, String name, String... args) {
            return null;
        }
        public String getOutputStatement(String text) { return null; }
        public String getProgram(String... statements) {
            return String.join("\n", statements);
        }
        public ScriptEngine getScriptEngine() { return new CompilingTinyEngine(); }
    }

    private record Prepared(ScriptEngine engine, String source,
                            CompiledScript compiled) {
        Object eval(Bindings bindings) throws ScriptException {
            return compiled != null
                    ? compiled.eval(bindings)
                    : engine.eval(source, bindings);
        }
        Object eval(ScriptContext context) throws ScriptException {
            return compiled != null
                    ? compiled.eval(context)
                    : engine.eval(source, context);
        }
    }

    private static Prepared prepare(ScriptEngine engine, String source)
            throws ScriptException {
        CompiledScript compiled = engine instanceof Compilable compiler
                ? compiler.compile(source) : null;
        return new Prepared(engine, source, compiled);
    }

    private static Bindings variables(ScriptEngine engine,
                                      double price, double quantity, double fee) {
        Bindings values = engine.createBindings();
        values.put("price", price);
        values.put("quantity", quantity);
        values.put("fee", fee);
        return values;
    }

    public static void main(String[] args) throws Exception {
        CompilingTinyEngine fast = new CompilingTinyEngine();
        Prepared cached = prepare(fast, SOURCE);
        System.out.println("compilable: " + (fast instanceof Compilable));
        System.out.println("compiled: " + (cached.compiled() != null));
        System.out.println("same engine: " + (cached.compiled().getEngine() == fast));

        Bindings orderA = variables(fast, 10, 3, 2);
        Bindings orderB = variables(fast, 4, 5, 1);
        System.out.println("compiled A: " + cached.eval(orderA));
        System.out.println("compiled B: " + cached.eval(orderB));

        fast.put("price", 2.0);
        fast.put("quantity", 3.0);
        fast.put("fee", 1.0);
        System.out.println("default context: " + cached.compiled().eval());

        SimpleScriptContext context = new SimpleScriptContext();
        context.setBindings(variables(fast, 7, 2, 1),
                ScriptContext.ENGINE_SCOPE);
        System.out.println("explicit context: " + cached.eval(context));
        System.out.println("compile calls: " + fast.compilations);
        System.out.println("parse calls: " + fast.parses);
        System.out.println("execute calls: " + fast.evaluations);

        Bindings incomplete = fast.createBindings();
        incomplete.put("price", 10);
        incomplete.put("quantity", 2);
        try {
            cached.eval(incomplete);
        } catch (ScriptException expected) {
            System.out.println("missing binding: " + expected.getMessage());
        }

        CompiledScript fromReader = ((Compilable) fast).compile(
                new StringReader(SOURCE));
        System.out.println("reader compiled: " + (fromReader.getEngine() == fast));

        TinyEngine plain = new TinyEngine();
        Prepared fallback = prepare(plain, SOURCE);
        System.out.println("fallback compilable: " + (plain instanceof Compilable));
        System.out.println("fallback A: " + fallback.eval(orderA));
        System.out.println("fallback B: " + fallback.eval(orderB));
        System.out.println("fallback parse calls: " + plain.parses);

        try {
            ((Compilable) fast).compile("price + quantity");
        } catch (ScriptException expected) {
            System.out.println("bad source: " + expected.getMessage());
        }
    }
}
~~~

Chạy:

~~~bash
javac --release 17 CompilableReuseDemo.java
java CompilableReuseDemo
~~~

**Stdout chính xác** với ví dụ engine học tập:

~~~text
compilable: true
compiled: true
same engine: true
compiled A: 32.0
compiled B: 21.0
default context: 7.0
explicit context: 15.0
compile calls: 1
parse calls: 1
execute calls: 4
missing binding: Missing numeric variable: fee
reader compiled: true
fallback compilable: false
fallback A: 32.0
fallback B: 21.0
fallback parse calls: 2
bad source: Only 'a * b + c' is supported
~~~

### 6.1. Phân tích chính xác output

- `compilable: true`: engine `CompilingTinyEngine` **implement `Compilable`**, nên `prepare` gọi `compile`.
- `compiled: true` và `same engine: true`: `CompiledScript` được tạo và giữ **chính engine đó** qua `getEngine()`.
- `compiled A: 32.0` và `compiled B: 21.0`: một `CompiledScript` chạy với hai bộ `Bindings`, cùng biểu thức nhưng giá trị khác nhau.
- `default context: 7.0`: lệnh `fast.put` thay default engine scope; `compiled.eval()` sử dụng nó để tính `2 × 3 + 1`.
- `explicit context: 15.0`: `compiled.eval(context)` đọc `7 × 2 + 1` theo `ENGINE_SCOPE` ở context do caller cung cấp.
- `compile calls: 1`, `parse calls: 1` và `execute calls: 4`: bốn lượt thành công thực thi một plan đã parse **một lần**.
- `missing binding: ...fee`: mã nguồn đã compile hợp lệ, nhưng một lượt eval thiếu biến cần thiết, nên `ScriptException` xuất hiện **khi chạy**, không phải khi compile.
- `reader compiled: true`: overload `compile(Reader)` cũng trả `CompiledScript` gắn đúng engine.
- `fallback compilable: false`: `TinyEngine` không implement `Compilable`. Hai lượt `fallback.eval(...)` gọi `engine.eval(source,bindings)`; `fallback parse calls: 2` minh họa phải parse ở mỗi lần theo **implementation demo**, không khẳng định mọi provider ngoài đời đều phải parse lặp.
- `bad source: ...`: cú pháp không hợp lệ bị từ chối bằng `ScriptException` ngay ở `compile`.

### 6.2. Vì sao đây là demo trung thực, nhưng không phải engine thực tế?

Parser chỉ nhận **ba identifier và hai toán tử `*`/`+`**, không có số literal, function call, escape, import, sandbox hay chuẩn ECMAScript. `TinyFactory` chỉ cung cấp metadata tối thiểu và không đăng ký service provider file, nên `ScriptEngineManager.getEngineByName("tiny")` không tự tìm thấy nó. `Factory.getProgram` cũng không nhằm hỗ trợ ngữ pháp nhiều câu lệnh.

Giá trị `32.0` là `Double` do `Number.doubleValue()`, không phải kết quả ECMAScript hay quy tắc tiền tệ chính xác. Trong hệ thống tiền tệ, dùng `BigDecimal` hoặc kiểu số có kiểm soát và quy tắc làm tròn phù hợp; demo dùng `double` để tập trung vào vòng đời `compile/eval`.

Điểm có thể áp dụng trực tiếp cho engine thật là **cách kiểm tra capability, cấu trúc `Prepared`, các overload `eval` và cách truyền `Bindings`**. API behavior của từng scripting language/provider còn cần đọc tài liệu riêng.

## 7. Đưa vào ứng dụng: chuẩn bị, lưu cache và tái sử dụng hợp lý

Một chu kỳ sử dụng thường gặp trong dịch vụ tính giá hoặc template:

~~~text
STARTUP / FIRST USE
  ├── tạo ScriptEngineManager
  ├── chọn ScriptEngine provider tương thích
  ├── kiểm tra Compilable
  ├── compile script X nếu hỗ trợ
  └── lưu Prepared { engine, source, compiled? }

MỖI REQUEST
  ├── tạo Bindings/ScriptContext của request
  ├── đưa dữ liệu đã kiểm tra vào scope tương ứng
  ├── prepared.eval(bindings/context)
  ├── xác thực kiểu kết quả, xử lý lỗi
  └── không compile lại X chỉ vì input đổi

KHI CẤU HÌNH / SOURCE / PROVIDER THAY ĐỔI
  ├── vô hiệu hóa mục cache phù hợp
  ├── compile lại bằng engine/config phù hợp
  └── giải phóng tham chiếu cũ khi an toàn
~~~

### 7.1. Chọn cache key đúng

Không đủ chỉ cache theo tên file `"price.js"`. Một cache hợp lý có thể xét:

- **Nội dung source chính xác** hoặc hash nguồn (gồm version được quản lý).
- **Engine instance** hoặc ít nhất identity provider/phiên bản/configuration, vì `CompiledScript` **gắn với engine đã compile**.
- Ngôn ngữ/phiên bản/ngữ pháp, class loader/module context và các options ảnh hưởng quá trình compile.
- Biên giới tenant/quyền thực thi, nếu provider có thể dùng metadata hoặc state khác nhau khi biên dịch.

Nếu script thay đổi, invalidation phải làm sao cho request mới không tiếp tục chạy plan cũ. Cache không nên giữ vô hạn mọi `CompiledScript`: object này có thể giữ reference đến engine, class loader, bytecode, closure và các cấu trúc lớn, gây giữ tài nguyên hoặc ngăn loader được thu hồi. Dùng giới hạn kích thước/vòng đời theo điều kiện hệ thống.

### 7.2. Khi nào nên *không* cache?

- Mã script hiếm khi lặp lại hoặc mỗi request tạo source hoàn toàn mới.
- Khả năng compile có chi phí chuẩn bị cao so với vài lần dùng.
- Engine hay tập config thường xuyên thay đổi.
- Script chứa state phụ thuộc vào session; không thể dùng chung compiled object theo policy.
- Cần isolation mạnh và provider chỉ cho chạy mỗi script trong một engine/sandbox riêng.

**Đánh giá hiệu năng bằng benchmark thực**, bao gồm compile time, thời gian eval, biến động dữ liệu, allocation, warmup JIT, cạnh tranh thread và memory retention. Không mặc định “compile rồi eval” luôn nhanh hơn `eval(source)` ở mọi provider.

## 8. Thread safety: `CompiledScript` có được chia sẻ giữa các thread không?

**Không suy từ `instanceof Compilable` ra thread safety.** Interface `Compilable` chỉ nói engine có thể compile. Không quy định engine state, `CompiledScript`, underlying interpreter và `Bindings` của bạn đều thread-safe.

Metadata chuẩn có thể xem:

~~~java
Object threading = engine.getFactory().getParameter("THREADING");
System.out.println(threading);
~~~

Đây là đoạn minh họa; output phụ thuộc provider. Theo Java 17 Javadoc:

| Giá trị `THREADING` | Ý nghĩa hợp đồng công bố |
| --- | --- |
| `null` | Engine **không được bảo đảm an toàn** cho concurrent execution; theo contract mô tả là không thread-safe |
| `"MULTITHREADED"` | Engine thực thi scripts đồng thời an toàn nội bộ, nhưng state có thể ảnh hưởng lẫn nhau giữa các thread |
| `"THREAD-ISOLATED"` | Như MULTITHREADED, đồng thời duy trì giá trị symbol tách theo thread |
| `"STATELESS"` | Như THREAD-ISOLATED, thêm ràng buộc script execution không làm đổi mapping của ENGINE_SCOPE `Bindings` |

Những giá trị này là **metadata do nhà cung cấp engine công bố**, không phải cơ chế khóa tự động do `ScriptEngineManager` áp đặt. Ngay cả khi engine báo MULTITHREADED, code Java nằm trong `Bindings` hoặc side effect ngoại vi vẫn phải tự bảo vệ.

Một số lựa chọn thực tế:

1. **Một engine/compiled plan trên một luồng chuyên trách**, đưa request vào queue nếu provider không thread-safe.
2. **Engine-per-thread** hoặc engine pool có ownership rõ ràng; mỗi engine cần **compiled plan riêng** (không lấy plan của engine A đưa sang engine B).
3. **Đồng bộ quanh tất cả lần sử dụng chung một engine/compiled object** nếu chính provider cho phép cách dùng đó và throughput chấp nhận được.
4. **Context/bindings riêng mỗi request** để tránh đè giá trị; đồng thời rà soát state ngoài bindings và các object mutable được đưa vào engine.

Trong chương trình phần 6, hai counter `parses`/`evaluations` cố ý là biến thường không đồng bộ. Nó là demo **đơn luồng**, không phải ví dụ cho phép dùng engine ở nhiều thread một cách an toàn.

## 9. Lỗi xảy ra ở compile hay ở eval?

| Vị trí lỗi | Triệu chứng thường thấy | Hành động |
| --- | --- | --- |
| **Discovery** | `getEngineByName(...) == null` | Kiểm tra JSR-223 provider dependency, tên engine/factory, class loader và module/service discovery |
| **Capability check** | Cast sang `Compilable` ném `ClassCastException` | Dùng `instanceof Compilable`; fallback sang `engine.eval` |
| **Compile** | `ScriptException` do lỗi cú pháp/phân tích nguồn | Báo vị trí script (line/column nếu provider có), sửa source, không cache plan thất bại |
| **Compile input** | `compile(null)` có thể ném `NullPointerException` theo API | Xác thực source/Reader trước khi compile |
| **Eval** | `ScriptException` do thiếu biến, lỗi runtime, import hoặc exception của ngôn ngữ | Phân biệt lỗi dữ liệu request với lỗi script; theo dõi nguyên nhân và context |
| **Eval** | `compiled.eval((ScriptContext) null)` gây `NullPointerException` | Cung cấp context hợp lệ hoặc gọi `eval()` dùng mặc định |
| **Result conversion** | Code Java ép kiểu kết quả sai | Kiểm tra `Object` trả về từ eval, chuyển đổi theo contract của ngôn ngữ; đừng ép kiểu bừa |
| **Concurrent usage** | Race condition, state xen kẽ, sai kết quả | Xem `THREADING` và chính sách đồng bộ/pool của engine |
| **Cache invalidation** | Script đã sửa nhưng vẫn chạy behavior cũ | Cache theo source/engine/config, invalidate theo vòng đời script |

**Đừng cố biến mọi lỗi thành `ScriptException`.** Một số lỗi đến từ Java caller (cast sai, `NullPointerException` do bạn truyền tham số null, lỗi class loading, `Error`) không phải lỗi cú pháp script. Ghi log phù hợp và không để message chứa thông tin nhạy cảm từ `Bindings`.

### 9.1. Tại sao không chia sẻ cùng một `Bindings` mọi nơi?

Giả sử request A đặt `userId="A"` và B đặt `userId="B"` vào **cùng** `engine.getBindings(ENGINE_SCOPE)`. Nếu không đồng bộ và engine dùng biến đó, request A có thể thấy `B`. Việc compile sẵn không xóa hiện tượng này.

Cách đơn giản hơn là tạo **map mới cho từng request**:

~~~java
Bindings variables = engine.createBindings();
variables.put("userId", requestUserId);
Object output = compiled.eval(variables);
~~~

Đây là đoạn minh họa, với `requestUserId`, `engine` và `compiled` có sẵn. Nó giúp tránh **ghi đè trực tiếp một map dùng chung**, nhưng chưa đủ để tuyên bố engine thread-safe hoặc cô lập mọi global object. Đặt giới hạn dữ liệu expose cho script theo security policy.

## 10. An toàn khi chạy script bên ngoài

`CompiledScript` là **tối ưu tái sử dụng**, không phải sandbox. Script engine có thể cho phép gọi Java classes, reflection, I/O, network hoặc truy cập những object được đưa vào `Bindings`. Không dùng `compile` như phép kiểm duyệt rằng script được phép làm việc gì.

Với script đến từ người dùng, nguồn không đáng tin hoặc multi-tenant:

- Chọn ngôn ngữ/provider hỗ trợ isolation và cấu hình quyền rõ ràng; xem kỹ khả năng Java-host interop.
- Giới hạn thời gian và tài nguyên ở boundary thực sự có khả năng cưỡng chế. `Future.cancel(true)` hay `Thread.interrupt()` **không phải** biện pháp bảo đảm dừng mọi interpreter/script.
- Với nguy cơ cao, chạy trong **process/container tách biệt** có quyền, CPU/memory, network và filesystem giới hạn phù hợp.
- Không truyền thẳng `DataSource`, credential, class loader hoặc object đặc quyền vào `Bindings`.
- Coi compiled cache của tenant là tài sản phải phân vùng phù hợp; không cho script của tenant khác nhìn thấy global state hoặc object cache không được phép.
- Ghi log source ID/hash và lỗi rút gọn, tránh log nguyên script hay dữ liệu nhạy cảm khi không cần.

Những vấn đề này **không được giải quyết chỉ bằng `Compilable`**.

## 11. Checklist triển khai trong ứng dụng Java 17

1. **Kiểm tra engine thực sự có trong runtime**: `ScriptEngineManager.getEngineFactories()` và `getEngineByName` trả instance hợp lệ; không suy rằng JavaScript engine đi kèm JDK 17.
2. **Chọn provider/version** và xác minh ngôn ngữ/cú pháp. `compile` của một engine không nhận cú pháp của engine khác.
3. **Kiểm tra `engine instanceof Compilable`**; nếu không hỗ trợ, vẫn có nhánh `engine.eval(source, ...)`.
4. **Compile một lần cho source ổn định**, không đặt `compile` trong mỗi request. Chú ý chi phí lúc chuẩn bị.
5. **Giữ `CompiledScript` cùng engine** đã tạo nó; kiểm tra `getEngine()` khi cần chẩn đoán.
6. **Truyền `Bindings` mới hoặc `ScriptContext` có scope rõ ràng** cho từng lượt. Nếu dùng `eval()` phải quản lý default context chủ động.
7. **Đảm bảo đúng concurrency policy**: xem `getFactory().getParameter("THREADING")` và tài liệu provider; không tự ý chia sẻ compiled object giữa threads.
8. **Xử lý `ScriptException` tách ở compile/eval**; xác thực kiểu và ý nghĩa của kết quả `Object`.
9. **Cache theo version/source/engine/config**, có invalidation và giới hạn memory. Không coi `CompiledScript` là dữ liệu portable.
10. **Bảo vệ boundary script**: quota, isolation, host access, dữ liệu bindings và auditing theo mức tin cậy.

## 12. Bài tập tự kiểm tra

**1.** `engine instanceof Compilable` là `false`. Muốn chạy script phải làm gì?  
**Đáp:** Dùng `engine.eval(source, bindings/context)`, không cast và không giả định có `CompiledScript`.

**2.** Bạn gọi `((Compilable)engine).compile(source).eval(bindings)` trong mỗi HTTP request. Đã tái sử dụng compiled program chưa?  
**Đáp:** Chưa. Vẫn compile cho mỗi request; cần chuyển `compile` ra bước chuẩn bị và giữ `CompiledScript`.

**3.** Một `CompiledScript` chạy với `Bindings A` và `Bindings B`. Có cần compile lại nếu chỉ thay `price`/`quantity`/`fee` không?  
**Đáp:** Không cần nếu **mã nguồn/script** và ngữ cảnh engine không đổi; truyền data qua `eval(Bindings)`.

**4.** `compiled.eval()` lấy biến từ đâu? `compiled.eval(bindings)` khác gì?  
**Đáp:** `eval()` dùng default `ScriptContext` của engine; `eval(bindings)` dùng map được truyền làm `ENGINE_SCOPE`, với default globals/I/O theo Javadoc.

**5.** `compiled.getEngine() == engineA`. Có thể gọi `engineB.eval(...)` để thực thi chính compiled plan ấy trên engine B không?  
**Đáp:** Không có API phổ quát chuyển `CompiledScript` qua engine khác. `CompiledScript` gắn với engine A; nếu muốn B dùng compiled plan, compile riêng trên B.

**6.** Factory trả `THREADING = null`. Bạn có thể an toàn gọi chung `compiled.eval(...)` từ 10 threads chỉ vì mỗi thread có Bindings riêng không?  
**Đáp:** Không. `Bindings` riêng không làm engine trở nên thread-safe. Cần serialize access hoặc dùng engine riêng theo contract provider.

**7.** `new ScriptEngineManager().getEngineByName("JavaScript")` trả `null` ở Java 17. Đó là bất thường?  
**Đáp:** Không nhất thiết. Nashorn đã bị loại từ JDK 15; cần cài/configure một JSR-223 JavaScript provider phù hợp.

**8.** Một script compile thành công nhưng khi eval thiếu `fee` thì xảy ra lỗi gì?  
**Đáp:** Có thể là `ScriptException` khi eval do thiếu biến hoặc vi phạm ngữ nghĩa runtime; không phải bằng chứng `compile` sai cú pháp. Demo đã kiểm chứng tình huống này.

**9.** Bạn muốn cache `CompiledScript` theo tên file duy nhất và chia sẻ toàn ứng dụng. Điều kiện gì còn thiếu?  
**Đáp:** Phải tính version/nội dung source, engine identity và configuration, quyền tenant, thread safety, vòng đời cache và invalidation.

**10.** Script chứa lệnh truy cập hệ thống nhưng compile thành công. Điều đó chứng minh nó an toàn để thực thi?  
**Đáp:** Không. Compilable không phải sandbox; phải cấu hình quyền và isolation độc lập.

## Tài liệu Java 17 chính thức

- [`javax.script` package overview — Script execution, Bindings, Compilation, Discovery](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/package-summary.html)
- [`Compilable` — optional interface, `compile(String)` và `compile(Reader)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/Compilable.html)
- [`CompiledScript` — `eval()`, `eval(Bindings)`, `eval(ScriptContext)`, `getEngine()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/CompiledScript.html)
- [`ScriptEngine`](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptEngine.html)
- [`ScriptEngineManager` và service discovery](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptEngineManager.html)
- [`ScriptEngineFactory` — metadata `THREADING`](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptEngineFactory.html)
- [`ScriptContext` và `SimpleScriptContext`](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptContext.html)
- [Oracle JDK 17 Migration Guide — Nashorn removed in JDK 15](https://docs.oracle.com/en/java/javase/17/migrate/removed-tools-and-components.html)
# Bài thực hành: Thêm quy tắc kịch bản với `Bindings` riêng và xử lý trường hợp thiếu engine

## 1. Bối cảnh và kết quả cần đạt

Giả sử một ứng dụng Java cho phép bổ sung **quy tắc xét duyệt yêu cầu** ở runtime. Mỗi lượt kiểm tra có dữ liệu riêng của một người dùng, chẳng hạn `amount`, `limit` và `verified`. Người vận hành muốn dùng một script để quyết định `ALLOW` hoặc `DENY`, thay quy tắc mà không sửa mã gọi dịch vụ; hệ thống đồng thời phải hoạt động an toàn khi **không có script engine được cài**.

Java Scripting API (JSR 223, `javax.script`, module chuẩn `java.scripting`) cung cấp các thành phần phù hợp:

- `ScriptEngineManager`: tìm hoặc đăng ký một `ScriptEngineFactory`, rồi tạo `ScriptEngine` theo tên.
- `ScriptEngine`: thực thi chuỗi script với `eval(...)`.
- `Bindings`: ánh xạ biến–giá trị được cung cấp cho script; mỗi request có thể có **một bộ riêng**.
- `ScriptContext`: cấu hình `ENGINE_SCOPE`, `GLOBAL_SCOPE` và kênh I/O.
- `ScriptException`: báo lỗi kịch bản mà caller phải phân loại và xử lý.

**Yêu cầu quan trọng của bài thực hành:** nếu không tìm thấy engine, script lỗi, hoặc kết quả không đúng hợp đồng Boolean, **không được âm thầm chấp nhận request**. Ví dụ biểu diễn kết quả bằng enum gồm `ALLOW`, `DENY`, `MISSING_ENGINE`, `SCRIPT_ERROR`, `INVALID_RESULT`; tất cả trạng thái khác `ALLOW` đều là **không cấp quyền** khi đưa vào quyết định nghiệp vụ.

Sau bài này, bạn có thể:

1. Đăng ký một engine thử nghiệm, kiểm tra khả năng tìm engine bằng tên.
2. Cấp `Bindings` riêng cho Alice và Bob, không để trạng thái phiên này ghi đè phiên kia.
3. Thêm quy tắc kiểm tra cờ `verified`, xem kết quả thay đổi từ `ALLOW` thành `DENY`.
4. Xử lý trường hợp engine vắng mặt và script không hợp lệ theo **fail closed**.
5. Phân biệt lỗi lookup, lỗi biên dịch/thực thi script, kết quả sai kiểu, và các vấn đề bảo mật hoặc chạy đồng thời.
6. Biên dịch và chạy một chương trình **Java 17** chỉ dùng JDK, với stdout có thể kiểm tra.

## 2. Lưu ý quan trọng về Java 17: có API không có nghĩa có engine

`javax.script` là **API chuẩn**. Nó không bảo đảm rằng JVM được cài sẵn engine JavaScript, Python hay ngôn ngữ bất kỳ.

Trong JDK cũ, Nashorn từng là JavaScript engine đi kèm; Nashorn đã bị loại khỏi JDK từ **Java 15**. Vì vậy, trên Java 17, lệnh:

```java
ScriptEngine engine =
        new ScriptEngineManager().getEngineByName("JavaScript");
```

**có thể trả `null`**, và trên môi trường Java 17 tiêu chuẩn không cài thêm provider, thông thường bạn không có JavaScript engine mặc định. Không viết code giả định `getEngineByName("JavaScript")` chắc chắn thành công.

Có hai cách triển khai phần thực hành:

- **Cách A (chạy độc lập, bài này sử dụng):** tự đăng ký một `ScriptEngineFactory` nhỏ mang tên `toy-rule`, hỗ trợ đúng một số biểu thức quy tắc. Nhờ đó mọi ví dụ chạy được với JDK 17, không cần tải dependency hay phụ thuộc tên engine mà máy đã cài.
- **Cách B (triển khai thực tế):** thêm JSR 223 provider của ngôn ngữ bạn chọn vào runtime, xác minh service registration/class loader và lấy engine bằng tên mà provider công bố. Cần dùng **cú pháp của engine thực tế**, không tự xem mã `toy-rule` là JavaScript.

Engine `toy-rule` bên dưới là một **bộ diễn giải tối giản dành riêng cho học tập**. Nó nhận vài chuỗi quy tắc có định nghĩa sẵn, không phải bộ thông dịch JavaScript đầy đủ, không cho chạy biểu thức tùy ý và không đại diện cho một sandbox.

## 3. Thiết kế bài toán và ranh giới dữ liệu

Ta xét mỗi request như sau:

| Thuộc tính | Java type | Ý nghĩa |
|---|---|---|
| `user` | `String` | Tên để nhận biết dữ liệu minh họa, không dùng để tự cấp quyền |
| `amount` | `int` | Giá trị yêu cầu |
| `limit` | `int` | Giới hạn cho phép |
| `verified` | `boolean` | Trạng thái đã xác minh |

Quy tắc ban đầu:

```text
amount <= limit
```

Quy tắc bổ sung yêu cầu xác minh:

```text
amount <= limit && verified
```

Dữ liệu ví dụ:

| Yêu cầu | `amount` | `limit` | `verified` | Quy tắc 1 | Quy tắc 2 |
|---|---:|---:|---|---|---|
| Alice | 80 | 100 | `false` | `ALLOW` | `DENY` |
| Bob | 150 | 100 | `true` | `DENY` | `DENY` |
| Alice sau khi xác minh | 80 | 100 | `true` | `ALLOW` | `ALLOW` |

Hai quy tắc được chọn bằng **chuỗi cấu hình** truyền cho `eval`, chứ không phải hai phương thức Java public riêng biệt của host. Trong mô hình sản phẩm thật, rule ID, version, source text và quyền thay đổi nên được lưu có kiểm soát; nội dung từ người dùng cuối không nên tự trở thành script được chạy với quyền server.

Các trạng thái của bộ gọi:

```text
                  Đọc cấu hình tên engine / rule
                              |
                              v
                  ScriptEngineManager lookup
                         /          \
                     null          có engine
                      |               |
                      v               v
              MISSING_ENGINE    Tạo Bindings riêng
                                      |
                                      v
                                 eval(rule)
                               /    |      \
                            lỗi   kết quả   Boolean
                             |      sai       |
                             v       v        v
                        SCRIPT_ERROR INVALID_RESULT
                                              |
                                       true hoặc false
                                       /           \
                                      v             v
                                    ALLOW          DENY
```

**Không có đường nào từ `MISSING_ENGINE`, `SCRIPT_ERROR` hay `INVALID_RESULT` sang `ALLOW`**. Đây là chính sách chủ động, không phải hành vi tự động của mọi script engine.

## 4. `Bindings` riêng là gì và vì sao cần?

`Bindings` về bản chất là một `Map<String,Object>` có ràng buộc về tên biến. Nếu mọi request cùng dùng `engine.put("user", ...)` trên một engine được chia sẻ, các biến trong **default `ENGINE_SCOPE`** có thể bị request này ghi đè request khác.

Ví dụ **không phù hợp** với ranh giới nhiều người dùng:

```java
// Minh họa phản ví dụ; giả định "engine" tồn tại.
engine.put("amount", 80);
engine.put("user", "Alice");
engine.eval(rule);

engine.put("amount", 150);
engine.put("user", "Bob");
engine.eval(rule);
```

Ở đây `put(...)` sửa `ENGINE_SCOPE` mặc định. Nó không tạo một phiên riêng cho từng lần chạy. Nếu host còn giữ trạng thái khác hoặc chạy nhiều thread đồng thời, hành vi càng khó dự đoán.

Cách tách dữ liệu theo lượt:

```java
Bindings alice = engine.createBindings();
alice.put("amount", 80);
alice.put("limit", 100);
alice.put("verified", false);

Object result = engine.eval("amount <= limit", alice);
```

Với `eval(script, bindings)`, các bindings được truyền vào là **`ENGINE_SCOPE` cho lần đánh giá đó**; đây không phải lệnh thay vĩnh viễn bindings mặc định của engine. Tuy nhiên, kiểu overload này có thể dùng các thành phần khác từ context mặc định của engine, bao gồm **`GLOBAL_SCOPE`**. Do đó nó không tự cách ly toàn bộ trạng thái.

Trong bài thực hành, ta dùng cách tường minh hơn:

```java
SimpleScriptContext context = new SimpleScriptContext();
context.setBindings(alice, ScriptContext.ENGINE_SCOPE);
context.setBindings(new SimpleBindings(), ScriptContext.GLOBAL_SCOPE);

Object result = engine.eval("amount <= limit", context);
```

Mỗi request có cả `ENGINE_SCOPE` riêng lẫn một `GLOBAL_SCOPE` rỗng riêng. Nhờ vậy ta không vô tình dùng chung global bindings được `ScriptEngineManager` gắn cho các engine do manager tạo. Việc cách ly `Bindings` vẫn **không** đồng nghĩa toàn bộ state nội bộ engine hoặc các đối tượng mutable bên trong map được cách ly.

## 5. Ba ranh giới phải kiểm tra trước khi chạy quy tắc

### 5.1. Tìm engine đúng tên

```java
ScriptEngine engine = manager.getEngineByName(configuredName);
if (engine == null) {
    return new Outcome(Decision.MISSING_ENGINE, null);
}
```

Đây là **trích đoạn** trong class của phần 7. `getEngineByName` có thể trả `null` khi không có factory được đăng ký/khám phá dưới tên đó. Bất kỳ bước nào cần dùng engine phải nằm **sau** kiểm tra null, nếu không có thể gặp `NullPointerException` và che mất nguyên nhân thực sự.

Đừng tự động lấy một engine **khác ngôn ngữ/cú pháp** khi thiếu engine bắt buộc. Nếu sản phẩm có fallback nghiệp vụ, fallback phải được thiết kế và phê duyệt riêng, không phải kiểu “không có engine thì cứ cho phép”.

### 5.2. Kết quả phải đúng hợp đồng

Một script engine JSR 223 có thể trả `Object`: `null`, `String`, `Number`, `Boolean` hoặc kiểu đặc thù của ngôn ngữ. Với quy tắc xét duyệt, **chỉ nhận `Boolean`**:

```java
Object raw = engine.eval(rule, context);
if (!(raw instanceof Boolean result)) {
    return new Outcome(Decision.INVALID_RESULT, bindings);
}
return new Outcome(
        result ? Decision.ALLOW : Decision.DENY, bindings);
```

Không tự ép kiểu `Boolean` bằng cast mù quáng; không hiểu chuỗi `"true"` là quyền cho phép nếu hợp đồng chưa quy định. Việc chuyển đổi kiểu thiếu kiểm soát có thể khiến script hoặc provider khác hành vi ngoài mong muốn.

### 5.3. Lỗi script không phải quyết định chấp nhận

```java
try {
    Object raw = engine.eval(rule, context);
    // Kiểm tra kết quả theo hợp đồng đã chọn.
} catch (ScriptException e) {
    return new Outcome(Decision.SCRIPT_ERROR, bindings);
}
```

Đây là **minh họa**; chương trình đầy đủ bên dưới có logic kiểm tra kiểu. `ScriptException` biểu thị lỗi script, không nên nuốt rồi trả `ALLOW`. Trong ứng dụng thật, cần log **đã làm sạch** `ruleId`, phiên bản rule và request ID, tránh ghi dữ liệu nhạy cảm của `Bindings` hay toàn bộ script vào log.

Các lỗi nghiêm trọng như `Error`, lỗi cấu hình JVM hoặc provider khởi tạo thất bại không nhất thiết là `ScriptException`; hãy quản lý chúng tại ranh giới worker/supervisor phù hợp, không `catch(Throwable)` rồi coi là quyết định nghiệp vụ hợp lệ.

## 6. Kiến trúc chương trình thực hành

Ta dùng **một file nguồn** `ScriptRuleLab.java` để giảm sai sót khi biên dịch. Các thành phần bên trong:

```text
ScriptRuleLab
  |
  +-- Decision enum: ALLOW / DENY / MISSING_ENGINE / ...
  +-- Request record: user / amount / limit / verified
  +-- Outcome record: decision / Bindings
  |
  +-- RuleFactory implements ScriptEngineFactory
  |       |
  |       +-- tên engine "toy-rule"
  |       +-- công bố THREADING = null
  |       +-- tạo RuleEngine
  |
  +-- RuleEngine extends AbstractScriptEngine
  |       |
  |       +-- eval(String, ScriptContext)
  |       +-- eval(Reader, ScriptContext)
  |       +-- createBindings()
  |
  +-- evaluate(manager, name, rule, request)
  |       |
  |       +-- lookup, null guard
  |       +-- request-local Bindings / ScriptContext
  |       +-- Boolean type check
  |       +-- fail-closed status mapping
  |
  +-- main(): các kịch bản kiểm thử
```

**Quy ước riêng của toy engine:**

- `"amount <= limit"` trả Boolean dựa trên hai biến Integer trong context.
- `"amount <= limit && verified"` trả Boolean và yêu cầu cờ `verified`.
- `"return text"` cố ý trả `String` để kiểm tra `INVALID_RESULT`.
- Bất kỳ chuỗi khác ném `ScriptException("Unsupported rule")`.
- Khi tính một quy tắc Boolean, engine ghi `lastDecision` vào **`ENGINE_SCOPE` của context truyền vào**. Đây là phép đo minh họa việc state không bị trộn giữa Alice và Bob.

Các chuỗi này **không phải cú pháp JavaScript đầy đủ**; ta dùng chúng làm một DSL nhỏ. Để hỗ trợ ngôn ngữ tổng quát, cần cài script engine thật hoặc xây parser/evaluator đầy đủ, không chỉ thêm một nhánh `switch`.

## 7. Chương trình Java 17 hoàn chỉnh

Tạo tệp `ScriptRuleLab.java` với đúng mã sau. Không có dependency bên thứ ba; sử dụng `javax.script` của JDK.

```java
import java.io.IOException;
import java.io.Reader;
import java.util.List;
import javax.script.AbstractScriptEngine;
import javax.script.Bindings;
import javax.script.ScriptContext;
import javax.script.ScriptEngine;
import javax.script.ScriptEngineFactory;
import javax.script.ScriptEngineManager;
import javax.script.ScriptException;
import javax.script.SimpleBindings;
import javax.script.SimpleScriptContext;

public final class ScriptRuleLab {
    enum Decision { ALLOW, DENY, MISSING_ENGINE, SCRIPT_ERROR, INVALID_RESULT }

    record Request(String user, int amount, int limit, boolean verified) {}
    record Outcome(Decision decision, Bindings bindings) {}

    static final class RuleFactory implements ScriptEngineFactory {
        @Override public String getEngineName() { return "Demo Rule Engine"; }
        @Override public String getEngineVersion() { return "1.0"; }
        @Override public List<String> getExtensions() { return List.of("rule"); }
        @Override public List<String> getMimeTypes() { return List.of("text/x-demo-rule"); }
        @Override public List<String> getNames() { return List.of("toy-rule"); }
        @Override public String getLanguageName() { return "DemoRule"; }
        @Override public String getLanguageVersion() { return "1.0"; }

        @Override
        public Object getParameter(String key) {
            return switch (key) {
                case "THREADING" -> null;
                case ScriptEngine.ENGINE -> getEngineName();
                case ScriptEngine.ENGINE_VERSION -> getEngineVersion();
                case ScriptEngine.LANGUAGE -> getLanguageName();
                case ScriptEngine.LANGUAGE_VERSION -> getLanguageVersion();
                case ScriptEngine.NAME -> "toy-rule";
                default -> null;
            };
        }

        @Override public String getMethodCallSyntax(
                String obj, String method, String... args) {
            throw new UnsupportedOperationException("No method calls");
        }
        @Override public String getOutputStatement(String text) {
            throw new UnsupportedOperationException("No output command");
        }
        @Override public String getProgram(String... statements) {
            return String.join("\n", statements);
        }
        @Override public ScriptEngine getScriptEngine() {
            return new RuleEngine(this);
        }
    }

    static final class RuleEngine extends AbstractScriptEngine {
        private final ScriptEngineFactory factory;
        RuleEngine(ScriptEngineFactory factory) { this.factory = factory; }

        @Override
        public Object eval(String script, ScriptContext context)
                throws ScriptException {
            return switch (script.trim()) {
                case "amount <= limit" -> compare(context, false);
                case "amount <= limit && verified" -> compare(context, true);
                case "return text" -> "not a boolean";
                default -> throw new ScriptException("Unsupported rule");
            };
        }

        private Boolean compare(ScriptContext context, boolean needVerified)
                throws ScriptException {
            Object amount = context.getAttribute("amount");
            Object limit = context.getAttribute("limit");
            Object verified = context.getAttribute("verified");
            if (!(amount instanceof Integer a) ||
                !(limit instanceof Integer max) ||
                !(verified instanceof Boolean approved)) {
                throw new ScriptException("Invalid binding types");
            }
            boolean allow = a <= max && (!needVerified || approved);
            context.setAttribute(
                    "lastDecision", allow, ScriptContext.ENGINE_SCOPE);
            return allow;
        }

        @Override
        public Object eval(Reader reader, ScriptContext context)
                throws ScriptException {
            StringBuilder source = new StringBuilder();
            char[] buffer = new char[1024];
            try {
                int n;
                while ((n = reader.read(buffer)) != -1) {
                    source.append(buffer, 0, n);
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

    static Outcome evaluate(
            ScriptEngineManager manager,
            String engineName,
            String rule,
            Request request) {
        ScriptEngine engine = manager.getEngineByName(engineName);
        if (engine == null) {
            return new Outcome(Decision.MISSING_ENGINE, null);
        }

        Bindings bindings = engine.createBindings();
        bindings.put("user", request.user());
        bindings.put("amount", request.amount());
        bindings.put("limit", request.limit());
        bindings.put("verified", request.verified());

        SimpleScriptContext context = new SimpleScriptContext();
        context.setBindings(bindings, ScriptContext.ENGINE_SCOPE);
        context.setBindings(new SimpleBindings(), ScriptContext.GLOBAL_SCOPE);

        try {
            Object raw = engine.eval(rule, context);
            if (!(raw instanceof Boolean result)) {
                return new Outcome(Decision.INVALID_RESULT, bindings);
            }
            return new Outcome(result ? Decision.ALLOW : Decision.DENY, bindings);
        } catch (ScriptException e) {
            return new Outcome(Decision.SCRIPT_ERROR, bindings);
        }
    }

    public static void main(String[] args) {
        ScriptEngineManager manager = new ScriptEngineManager();
        RuleFactory factory = new RuleFactory();
        manager.registerEngineName("toy-rule", factory);

        Request alice = new Request("Alice", 80, 100, false);
        Request bob = new Request("Bob", 150, 100, true);
        Outcome a = evaluate(manager, "toy-rule", "amount <= limit", alice);
        Outcome b = evaluate(manager, "toy-rule", "amount <= limit", bob);

        System.out.println("Rule 1 / Alice: " + a.decision());
        System.out.println("Rule 1 / Bob: " + b.decision());
        System.out.println("Bindings distinct: " + (a.bindings() != b.bindings()));
        System.out.println("Alice lastDecision: " +
                a.bindings().get("lastDecision"));
        System.out.println("Bob lastDecision: " +
                b.bindings().get("lastDecision"));

        Outcome strict = evaluate(
                manager, "toy-rule", "amount <= limit && verified", alice);
        Outcome confirmed = evaluate(
                manager, "toy-rule", "amount <= limit && verified",
                new Request("Alice", 80, 100, true));
        System.out.println("Rule 2 / Alice unverified: " + strict.decision());
        System.out.println("Rule 2 / Alice verified: " + confirmed.decision());

        Outcome missing = evaluate(
                manager, "__missing_engine_demo_229__", "amount <= limit", alice);
        System.out.println("Missing engine: " + missing.decision());

        Outcome syntax = evaluate(
                manager, "toy-rule", "amount >>> limit", alice);
        System.out.println("Invalid syntax: " + syntax.decision());

        Outcome type = evaluate(
                manager, "toy-rule", "return text", alice);
        System.out.println("Invalid result: " + type.decision());
        System.out.println("Factory THREADING: " +
                factory.getParameter("THREADING"));
    }
}
```

### Mục đích của từng phần

**`RuleFactory`** là một factory hợp lệ của JSR 223. Nó công bố tên `"toy-rule"`, những thông tin cơ bản và tạo instance của `RuleEngine`. Ta đăng ký tên engine **chủ động** qua `manager.registerEngineName(...)`, không phải trông chờ ServiceLoader tìm plugin trên một máy chưa cài provider.

**`RuleEngine`** thừa kế `AbstractScriptEngine`. Nó hiện thực `eval(String, ScriptContext)`, `eval(Reader, ScriptContext)`, `createBindings()` và `getFactory()`. Đây là những điểm cần thiết để ví dụ thể hiện đúng cách một engine thực thi qua JSR 223. `getParameter("THREADING")` trả `null` vì toy engine **không công bố khả năng chạy script đồng thời trên cùng instance**.

**`evaluate(...)`** luôn lấy một engine mới từ manager, tạo `Bindings` mới, tạo `SimpleScriptContext` mới, rồi đánh giá rule. Vì vậy ví dụ **không có hai request đồng thời dùng chung một engine instance**. `Outcome` có chứa `Bindings` **chỉ để bài thực hành có thể xác minh state và object identity**; trong service production, không đưa map mutable của request vào response cho client.

**`main()`** chạy các test theo thứ tự ổn định để chứng minh cả thành công và các nhánh lỗi. Nó không phụ thuộc JavaScript/Nashorn được cài sẵn.

## 8. Biên dịch, chạy và kiểm tra stdout

Cài JDK 17 trở lên, lưu file `ScriptRuleLab.java` ở thư mục tùy chọn, mở terminal trong thư mục đó.

### Linux/macOS

```bash
javac --release 17 -encoding UTF-8 ScriptRuleLab.java
java ScriptRuleLab
```

### Windows PowerShell

```powershell
javac --release 17 -encoding UTF-8 ScriptRuleLab.java
java ScriptRuleLab
```

Nếu `javac` không được tìm thấy, cần kiểm tra `PATH`/`JAVA_HOME` và đảm bảo đang dùng JDK có compiler. Nếu code được đặt trong named module thay vì chạy trên classpath như bài này, cần khai báo `requires java.scripting;` trong `module-info.java`.

**Stdout trên đường chạy thành công của chương trình:**

```text
Rule 1 / Alice: ALLOW
Rule 1 / Bob: DENY
Bindings distinct: true
Alice lastDecision: true
Bob lastDecision: false
Rule 2 / Alice unverified: DENY
Rule 2 / Alice verified: ALLOW
Missing engine: MISSING_ENGINE
Invalid syntax: SCRIPT_ERROR
Invalid result: INVALID_RESULT
Factory THREADING: null
```

Đầu ra không in stack trace vì demo chuyển những lỗi script đã biết thành trạng thái rõ ràng. Với runtime có provider ngoài được đăng ký trùng tên giả định `__missing_engine_demo_229__`, nhánh “missing” cần đổi sang một tên không có nhà cung cấp để kiểm thử; trên môi trường demo bình thường, tên thử nghiệm đó không tồn tại.

## 9. Đi từng bước qua kết quả

### 9.1. `Rule 1`: thêm quy tắc cơ bản

Trong `main`:

```java
Outcome a = evaluate(manager, "toy-rule", "amount <= limit", alice);
Outcome b = evaluate(manager, "toy-rule", "amount <= limit", bob);
```

Alice có `80 <= 100` nên `ALLOW`. Bob có `150 <= 100` sai nên `DENY`. Cả hai chạy **cùng một source rule**, nhưng với các giá trị trong hai `Bindings` khác nhau.

Nếu định nghĩa quy tắc như một cấu hình ứng dụng, thứ có thể đổi giữa các lần triển khai là `rule` (chuỗi), còn hàm `evaluate(manager, engineName, rule, request)` không cần đổi cách gọi. Tuy nhiên, trong toy engine, tập cú pháp được hỗ trợ là hữu hạn và đã nằm trong implementation.

### 9.2. Kiểm chứng `Bindings` riêng biệt

Hai dòng:

```text
Bindings distinct: true
Alice lastDecision: true
Bob lastDecision: false
```

cho thấy `a.bindings()` và `b.bindings()` là **hai object khác nhau**. Toy engine ghi `lastDecision` vào `ENGINE_SCOPE` của context tương ứng; Alice giữ `true`, Bob giữ `false`. Nó không ghi biến `lastDecision` vào scope mặc định của manager.

Việc có hai map riêng là điều kiện quan trọng nhưng **chưa phải cam kết cô lập tuyệt đối**:

- Nếu cả hai map cùng tham chiếu một `ArrayList` hay connection mutable, state của object đó vẫn có thể dùng chung.
- Nếu engine giữ static field hoặc global state riêng bên ngoài Bindings, tạo bindings mới không tự reset chúng.
- Nếu context dùng `GLOBAL_SCOPE` chung từ `ScriptEngineManager`, biến global vẫn có thể rò. Bài này đặt `GLOBAL_SCOPE` rỗng riêng cho mỗi lượt chạy.

### 9.3. Thêm quy tắc xác minh

Đổi source từ:

```text
amount <= limit
```

sang:

```text
amount <= limit && verified
```

Đối với Alice chưa xác minh (`verified=false`), kết quả đổi từ `ALLOW` sang `DENY`. Với cùng Alice đã xác minh (`true`), kết quả là `ALLOW`.

Đó là mục tiêu “**thêm quy tắc kịch bản**”: điều kiện xét duyệt thay đổi qua **source rule** và dữ liệu được truyền vào, còn host giữ nguyên giao diện `evaluate(...)`. Khi dùng một engine thực có parser/ngôn ngữ riêng, script có thể linh hoạt hơn nhiều; nhưng cũng phải có version, kiểm thử và kiểm soát quyền chỉnh sửa.

### 9.4. Thiếu engine được nhận diện trước `eval`

Lệnh:

```java
Outcome missing = evaluate(
        manager, "__missing_engine_demo_229__", "amount <= limit", alice);
```

thử tìm một engine dưới tên chưa đăng ký. `manager.getEngineByName(...)` trả `null`, vì thế hàm trả `MISSING_ENGINE` **trước khi tạo Bindings và trước khi thực thi script**.

Trường hợp này khác `SCRIPT_ERROR`:

- **`MISSING_ENGINE`:** không có provider/engine phù hợp với tên cấu hình.
- **`SCRIPT_ERROR`:** đã lấy được engine nhưng script không được hỗ trợ, sai cú pháp hoặc engine phát sinh `ScriptException` khi chạy.

Trong production, chúng cần thông báo và hướng chẩn đoán khác nhau. Việc phân biệt giúp người vận hành không mất thời gian sửa script khi thực tế thiếu dependency của engine.

### 9.5. Script lỗi và kết quả sai kiểu

Toy engine cố ý chỉ hiểu hai biểu thức Boolean, cộng một test trả `String`. Với source `"amount >>> limit"`, nó ném `ScriptException`, nên status là `SCRIPT_ERROR`.

Với `"return text"`, `eval()` trả `"not a boolean"`, nhưng hợp đồng xét duyệt **chỉ nhận Boolean**, nên status là `INVALID_RESULT`.

Một hệ thống thiếu kiểm tra có thể viết:

```java
// PHẢN VÍ DỤ: sai hợp đồng, có thể ClassCastException hoặc lỗi logic.
boolean allowed = (Boolean) engine.eval(rule, context);
```

Ở đây một script hợp lệ về mặt ngôn ngữ nhưng trả String làm chương trình lỗi. Kiểm tra `instanceof Boolean` bảo đảm chỉ kết quả đúng kiểu mới được xét thành `ALLOW`/`DENY`.

## 10. Luồng thực thi an toàn của một request

Đối với API thực tế, có thể tách `evaluate(...)` và **điểm áp dụng quyết định**:

```text
HTTP / Batch / Message Request
           |
           v
   Validate request fields
           |
           v
   Load allowed rule version
           |
           v
   Resolve configured engine
           |
     +-----+--------------------+
     |                          |
   missing                    exists
     |                          |
     v                          v
 MISSING_ENGINE          New Bindings/Context
                                |
                                v
                             eval(...)
                                |
             +------------------+------------------+
             |                  |                  |
          exception          wrong type         Boolean
             |                  |                  |
             v                  v                  v
        SCRIPT_ERROR      INVALID_RESULT    ALLOW / DENY
             |                  |                  |
             +----------+-------+------------------+
                        |
                        v
               Apply default-deny:
               only ALLOW authorizes
                        |
                        v
                Audit safe metadata
```

Trong một phương thức dịch vụ ngoài demo, quyết định có thể được áp bằng:

```java
boolean approved = outcome.decision() == Decision.ALLOW;
```

Đây là **trích đoạn** nằm trong scope có `outcome` và `Decision`, không phải file độc lập. Với `MISSING_ENGINE`, `SCRIPT_ERROR`, `INVALID_RESULT` và `DENY`, `approved` đều là `false`.

**Fail closed không có nghĩa mất mọi khả năng phục hồi.** Bạn có thể trả status chính xác để vận hành sửa dependency/rule; có thể cho client retry sau khi cấu hình được sửa. Nhưng cơ chế phục hồi phải không chuyển một lỗi kỹ thuật thành chấp thuận nghiệp vụ ngoài ý muốn.

## 11. Những gì `Bindings` cô lập được và không cô lập được

### 11.1. `ENGINE_SCOPE` và `GLOBAL_SCOPE`

`SimpleScriptContext` có hai scope chính:

| Scope | Dùng vào việc gì | Rủi ro khi chia sẻ |
|---|---|---|
| `ENGINE_SCOPE` | Biến theo từng lượt eval, phiên, hoặc engine context | Nếu dùng map mặc định chung giữa requests, request có thể ghi đè biến |
| `GLOBAL_SCOPE` | Các biến dùng chung ở phạm vi rộng hơn | Dữ liệu tenant A có thể hiển thị cho tenant B nếu đặt chung |

Trong ví dụ, sau khi tạo map local bằng `engine.createBindings()`, mã gắn:

```java
context.setBindings(bindings, ScriptContext.ENGINE_SCOPE);
context.setBindings(new SimpleBindings(), ScriptContext.GLOBAL_SCOPE);
```

Nhờ vậy cả hai scope đều được **quy định rõ**. Nếu chỉ dùng `engine.eval(rule, bindings)` với một engine có context mặc định, implementation có thể thừa hưởng các thành phần khác của context mặc định, bao gồm global scope; điều này phải được đánh giá với engine cụ thể.

Khi một biến cùng tên có mặt ở cả `ENGINE_SCOPE` và `GLOBAL_SCOPE`, tra cứu theo scope thông thường ưu tiên `ENGINE_SCOPE`. Vì thế việc vô tình đặt một secret trong global bindings vẫn nguy hiểm: một script có thể thấy dữ liệu đó khi không bị shadow.

### 11.2. Một map mới không phải deep copy

Ví dụ minh họa về dữ liệu mutable:

```java
List<String> shared = new java.util.ArrayList<>();

Bindings alice = new SimpleBindings();
Bindings bob = new SimpleBindings();
alice.put("items", shared);
bob.put("items", shared);
```

Mặc dù `alice != bob`, cả hai map cùng tham chiếu list `shared`. Một engine có khả năng gọi method Java trên object đó có thể làm thay đổi list mà bên còn lại thấy.

Trong hệ thống thực, nên chỉ truyền các kiểu dữ liệu đã cho phép, immutable hoặc DTO đã được kiểm soát; không đưa connection, credential, registry nội bộ hay object host có quyền cao vào script chỉ vì nó chạy trong `Bindings` khác.

### 11.3. Không giả định engine có thể dùng chung nhiều luồng

`ScriptEngineFactory.getParameter("THREADING")` mô tả cam kết concurrency của provider. Các giá trị Java Scripting API xác định gồm:

| Giá trị | Ý nghĩa |
|---|---|
| `null` | Factory không bảo đảm engine thread-safe; không được dùng một engine thực thi script đồng thời |
| `"MULTITHREADED"` | Engine hỗ trợ thực thi script đồng thời; tác động trạng thái có thể nhìn thấy qua các thread |
| `"THREAD-ISOLATED"` | Thỏa `MULTITHREADED` và bảo đảm về các symbol được cô lập theo thread |
| `"STATELESS"` | Thỏa các mức trước và script không thay đổi mapping trong `ENGINE_SCOPE` bindings |

Cần chú ý `"STATELESS"` không hứa rằng script không có side effect tới file, network hay object mutable; chỉ liên quan nghĩa đã quy định cho mapping trong scope.

Trong demo, `RuleFactory.getParameter("THREADING") == null`. Hàm `evaluate(...)` lấy engine mới cho từng lần gọi, không có hai request song song vào **cùng một** `RuleEngine` instance. Khi tối ưu bằng engine pool hoặc shared engine, cần đánh giá vòng đời, reset state, concurrency và ranh giới tenant trước khi dùng lại.

## 12. Cách phát triển từ toy rule sang engine thật

Bài thực hành này nhằm hiểu **JSR 223 và cách quản lý trạng thái**, không yêu cầu dùng ngôn ngữ JavaScript. Nếu ứng dụng chọn một engine được cài thêm, luồng kiểm tra có thể là:

```java
ScriptEngineManager manager = new ScriptEngineManager();
ScriptEngine engine = manager.getEngineByName("JavaScript");

if (engine == null) {
    // Không có provider phù hợp: fail closed / báo cấu hình thiếu.
} else {
    ScriptEngineFactory factory = engine.getFactory();
    System.out.println(factory.getEngineName());
    System.out.println(factory.getEngineVersion());
    System.out.println(factory.getParameter("THREADING"));
}
```

Đây là **đoạn code minh họa**, không phải một chương trình độc lập. `getEngineByName("JavaScript")` có thể trả `null`; tên thực tế, cú pháp và cách đăng ký phụ thuộc provider đã cài.

Muốn đưa vào sản phẩm, cần thực hiện theo thứ tự:

1. Chọn ngôn ngữ/engine có tài liệu và JSR 223 integration phù hợp phiên bản Java.
2. Cài đúng artifact cùng các dependency, đăng ký factory qua SPI hoặc cơ chế cấu hình được hỗ trợ.
3. Xác minh `getEngineByName(configuredName)` thực sự tạo được engine và ghi nhận tên/version/provider.
4. Viết một rule nhỏ theo **cú pháp thật** của ngôn ngữ và kiểm tra nó trả Boolean đúng hợp đồng.
5. Truyền dữ liệu request qua `Bindings` hoặc `ScriptContext` tách biệt; không chắp script bằng cách nối input thô.
6. Kiểm tra `THREADING`, khả năng reuse engine, cách reset state, lifetime và policy multitenancy.
7. Thiết kế allowlist quyền/capability và process isolation nếu script không tin cậy; class loader riêng không phải sandbox.
8. Kiểm thử `null`, syntax error, wrong type, timeout, side effect và rollback.

**Cảnh báo:** không phải mọi provider dùng cùng tên `"JavaScript"`, cùng kiểu giá trị Boolean hoặc cùng semantics khi xuất bản host object. Đừng sao chép trực tiếp source `"amount <= limit && verified"` sang một engine khác mà không xem đó có phải cú pháp hợp lệ và cách truy cập `Bindings` của ngôn ngữ ấy hay không.

## 13. Tình huống thiếu engine trong môi trường thật

Nguyên nhân thường gặp:

- Chạy **JDK 17 tiêu chuẩn** nhưng quên thêm script engine bên thứ ba.
- Có JAR engine trên compile classpath, nhưng runtime classpath/module path thiếu dependency.
- Provider có tên khác tên được cấu hình.
- `META-INF/services/javax.script.ScriptEngineFactory` hoặc khai báo module `provides` không được đóng gói đúng đối với kiểu triển khai tương ứng.
- Engine nằm ở class loader/module layer mà `ScriptEngineManager` hiện tại không nhìn thấy.
- Provider khởi tạo lỗi do thiếu dependency hay tương thích phiên bản; đây không nhất thiết chỉ biểu hiện bằng `null`, có thể là lỗi khi khám phá/khởi tạo.

Cách phân tích: tách **không tìm thấy factory** khỏi **factory có nhưng khởi tạo lỗi** và **engine chạy script lỗi**. Có thể kiểm tra các `ScriptEngineFactory` khám phá được bằng `manager.getEngineFactories()` khi hữu ích, nhưng lưu ý danh sách discovery không nhất thiết phản ánh cách đăng ký thủ công từng tên trong manager giống ví dụ toy.

Nếu thiếu engine trên production, đừng làm kiểu:

```java
// PHẢN VÍ DỤ: tuyệt đối tránh với rule xét duyệt.
if (engine == null) {
    return true;
}
```

Chính sách gợi ý: fail closed, báo `MISSING_ENGINE` hoặc lỗi cấu hình rõ ràng, cảnh báo người vận hành, giữ lại version rule hiện hành và không đánh dấu request là được phép.

## 14. Kiểm thử tự động và chấp nhận kết quả

Một bộ kiểm thử cho rule engine ít nhất phải xác minh:

| Test case | Engine | Script | Dữ liệu | Kết quả mong muốn |
|---|---|---|---|---|
| Basic allow | `toy-rule` | `amount <= limit` | Alice 80/100 | `ALLOW` |
| Basic deny | `toy-rule` | `amount <= limit` | Bob 150/100 | `DENY` |
| Isolation | `toy-rule` | Cùng script | Alice/Bob | Hai `Bindings` khác tham chiếu và `lastDecision` riêng |
| Rule upgrade, missing verification | `toy-rule` | `amount <= limit && verified` | Alice false | `DENY` |
| Rule upgrade, verified | `toy-rule` | `amount <= limit && verified` | Alice true | `ALLOW` |
| Missing engine | Tên không được đăng ký | Bất kỳ | Alice | `MISSING_ENGINE`, không gọi eval |
| Invalid syntax | `toy-rule` | `amount >>> limit` | Alice | `SCRIPT_ERROR` |
| Invalid return type | `toy-rule` | `return text` | Alice | `INVALID_RESULT` |
| Factory metadata | `toy-rule` | Không cần eval | — | `THREADING=null` |
| Concurrency | Provider theo version thực tế | Nhiều request | Dữ liệu khác nhau | Không truy cập chung sai và tuân thủ factory threading contract |

Có thể tăng độ khó bằng test property-based cho các giá trị sát ranh giới:

- `amount == limit` phải cho `ALLOW` theo quy tắc `<=` nếu không có điều kiện bổ sung.
- `amount > limit` phải cho `DENY`.
- Khi dùng quy tắc `&& verified`, phải có **cả hai** điều kiện đúng.
- Input âm, tràn số, limit không hợp lệ hoặc data types không đúng contract cần được **validate ở tầng request** trước khi cấp cho script. Demo dùng `int` để tập trung vào API, không thay validation nghiệp vụ.

Đối với một script engine bên thứ ba, kiểm thử cả việc biến có thể được ghi lại vào `Bindings` sau eval, biến trong global scope và các object Java được chia sẻ; đừng chỉ kiểm tra Boolean output.

## 15. Quy tắc thay đổi phiên bản và vận hành

Một quy tắc cần có **vòng đời** nếu được dùng cho quyết định quan trọng:

```text
Draft rule source
      |
      v
Validate syntax and contract
      |
      v
Test with a set of known requests
      |
      v
Review / approve rule version
      |
      v
Publish version N
      |
      v
Evaluate each request with snapshot of version N
      |
      v
Log rule ID/version + status + duration
```

Tránh sửa một chuỗi rule dùng chung “ngay giữa” một request mà không xác định version. Nếu rule được đọc từ registry động, caller nên chụp một **snapshot bất biến** gồm engine name, source text, version và policy tại đầu request. Nhờ vậy log/debug có thể tái hiện request đã dùng bản quy tắc nào.

Các biện pháp thực tế:

- **Fail fast khi startup:** kiểm tra engine bắt buộc có sẵn và script syntax hợp lệ trước khi nhận traffic, nhưng vẫn xử lý thiếu engine an toàn tại runtime.
- **Fail closed tại runtime:** không dùng default allow khi engine/service lỗi.
- **Quota và timeout:** một script không tin cậy có thể lặp vô hạn, dùng nhiều bộ nhớ hoặc I/O. `Future.cancel(true)`/`Thread.interrupt()` không buộc code không hợp tác phải dừng; dùng ranh giới process/OS nếu cần cưỡng chế.
- **Bảo mật:** hạn chế quyền đối tượng host truyền cho script; không đưa secret vào bindings chung; xem xét filesystem, network và native access.
- **Threading:** không dùng lại engine nếu factory không bảo đảm hoặc không có cơ chế sở hữu độc quyền; `Bindings` riêng không tự làm engine thread-safe.
- **Kiểm soát dữ liệu:** phân biệt lỗi rule, thiếu provider và quyết định từ chối hợp lệ; không gửi source/bindings có thể chứa PII sang log không bảo vệ.
- **Chuyển version an toàn:** mỗi request nên gắn rule version cố định để audit; có khả năng rollback rule và hiểu side effect của các request đã xử lý.

## 16. Bài tập mở rộng

1. **Thêm quy tắc mới:** mở rộng toy engine cho source `"amount < limit && verified"`; kiểm thử `amount == limit` bị từ chối, nhưng `amount < limit` với verified true được cho phép.
2. **Thêm dữ liệu user:** bổ sung key `"country"` và quy tắc chỉ áp dụng một số quốc gia. Cần quyết định chính sách khi key thiếu: `SCRIPT_ERROR`, `DENY` hay một mã chuyên biệt? Giải thích tại sao không chấp nhận tự động.
3. **Chứng minh isolation:** thêm `context.setAttribute("trace", user, ENGINE_SCOPE)` trong engine; chạy ba request xen kẽ và chứng minh mỗi binding map giữ trace của mình.
4. **Chứng minh lỗi global:** tạm dùng một `ScriptEngineManager` có global bindings chứa `"region" = "X"`, bỏ đoạn gắn `GLOBAL_SCOPE` riêng và quan sát biến global được nhìn thấy ở cả hai context; sau đó khôi phục cách cô lập an toàn.
5. **Thử thiếu engine:** thay `"toy-rule"` bằng tên không đăng ký và bảo đảm chương trình trả `MISSING_ENGINE`, không đi vào `createBindings` hay `eval`.
6. **Thử script lỗi:** sửa rule thành chuỗi không được hỗ trợ. Kiểm tra `SCRIPT_ERROR` khác `DENY` và vẫn bị từ chối trong chính sách cấp quyền.
7. **Thử kết quả không Boolean:** tạo một nhánh trả `null`, `Integer` hoặc `String`; cần trả `INVALID_RESULT`, không ép về Boolean.
8. **Dùng một engine thật:** cài provider JSR 223 phù hợp Java 17, ánh xạ `Bindings` theo cú pháp ngôn ngữ, đánh giá một rule Boolean và kiểm tra `THREADING`. Nếu provider không có mặt, luôn giữ xử lý `null`.
9. **Thay version động:** lưu record `RuleSpec(id, version, engineName, source)` bất biến; ghi version vào audit log và cho phép rollback sau khi kiểm thử.
10. **Tách trust boundary:** giả sử rule do người dùng internet nộp, thiết kế một worker process có quota CPU/RAM, network allowlist, timeout và protocol request/response thay vì thực thi cùng JVM với host.

## 17. Checklist hoàn thành bài thực hành

- [ ] Tạo được một `ScriptEngineFactory` tên `toy-rule` và đăng ký bằng `registerEngineName`.
- [ ] Tìm engine bằng `getEngineByName`, **kiểm tra `null` trước khi dùng**.
- [ ] Tạo `Bindings` mới cho từng request qua `engine.createBindings()`.
- [ ] Đưa đúng kiểu dữ liệu `amount`, `limit`, `verified` vào từng map.
- [ ] Dùng `SimpleScriptContext` với `ENGINE_SCOPE` riêng và `GLOBAL_SCOPE` không chia sẻ.
- [ ] `eval(...)` trả Boolean hợp lệ mới được đổi thành `ALLOW`/`DENY`.
- [ ] Có riêng kết quả `MISSING_ENGINE`, `SCRIPT_ERROR` và `INVALID_RESULT`.
- [ ] Rule mới `amount <= limit && verified` hoạt động và đổi kết quả theo `verified`.
- [ ] Chạy được 11 dòng stdout đúng ở phần 8 với JDK 17+.
- [ ] Không coi `Bindings` riêng là sandbox hoặc bảo đảm thread-safe.
- [ ] Quyết định nghiệp vụ **chỉ** cấp quyền khi status là `ALLOW`.

**Kết luận:** thêm quy tắc bằng JSR 223 không chỉ là gọi `ScriptEngine.eval`. Một giải pháp đúng cần **tìm engine an toàn**, **truyền `Bindings` riêng và scope rõ ràng cho mỗi lần đánh giá**, **xác minh kiểu dữ liệu trả về**, và **xử lý thiếu provider hoặc lỗi script theo chính sách fail closed**. Đó là nền tảng để chuyển từ bài thực hành nhỏ sang hệ thống quy tắc động có thể kiểm thử, quan sát và vận hành.
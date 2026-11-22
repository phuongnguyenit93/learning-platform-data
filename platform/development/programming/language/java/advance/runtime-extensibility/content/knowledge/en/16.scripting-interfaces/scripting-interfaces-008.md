# Giới hạn tính khả chuyển của cú pháp, chuyển đổi kiểu và cơ chế dừng engine

Java cung cấp API **JSR-223 / Scripting for the Java Platform** trong module `java.scripting`, chủ yếu qua `javax.script.ScriptEngineManager`, `ScriptEngine`, `Bindings`, `ScriptContext` và `ScriptEngineFactory`. API giúp một ứng dụng Java **làm việc với nhiều script engine thông qua giao diện Java chung**; nhưng nó **không chuẩn hóa ngôn ngữ script, hệ kiểu dữ liệu của ngôn ngữ, khả năng ngắt một script đang chạy hoặc mức độ cô lập của engine**.

Ba câu hỏi thiết kế cần được trả lời *riêng biệt*:

1. **Cú pháp script có chuyển sang engine khác được không?** Không có cam kết rằng cùng chuỗi script sẽ được tất cả engine hiểu và thực thi tương đương.
2. **Giá trị Java và script được chuyển kiểu như thế nào?** `eval` nhận/trả `Object`; Java không có một quy tắc chuyển đổi chung cho mọi ngôn ngữ và mọi engine.
3. **Khi script quá thời gian, ai dừng nó?** API `ScriptEngine` không có thao tác chuẩn `stop()`, `interrupt()` hoặc `close()`. Timeout, ngắt thread và hủy engine cần tách rõ theo hợp đồng implementation.

**Nguyên tắc chính:** có thể chuẩn hóa *lời gọi từ Java*, nhưng muốn khả chuyển thực sự phải có **hợp đồng cú pháp, dữ liệu, vòng đời và giới hạn thực thi** do ứng dụng thiết kế, kiểm thử trên từng engine.

## 1. JSR-223 chuẩn hóa tầng nào?

Các thành phần cơ bản:

| API | Vai trò chuẩn hóa | Không bảo đảm |
| --- | --- | --- |
| `ScriptEngineManager` | Khám phá/đăng ký engine factory; tìm engine theo name, extension, MIME type | Môi trường luôn có engine cho JavaScript/Groovy hay ngôn ngữ nào |
| `ScriptEngine` | `eval(String/Reader, ...)`, `put/get`, `createBindings`, lấy/set context | Cú pháp chung, type mapping chung, sandbox, timeout, stop |
| `ScriptEngineFactory` | Tên engine, phiên bản, ngôn ngữ, aliases, extension, MIME, metadata `THREADING` | Đặc tính engine/version đồng nhất giữa nhà cung cấp |
| `Bindings` | Một ánh xạ `String → Object` cho các thuộc tính hiển thị với script | Cách diễn giải tên biến, host object, null hoặc kiểu dữ liệu trong script |
| `ScriptContext` | `ENGINE_SCOPE`, `GLOBAL_SCOPE` và input/output/error readers/writers | Cô lập hoàn toàn state của engine hoặc request |
| `Invocable` | Gọi function/method script khi engine hỗ trợ interface này | Tất cả engine đều hỗ trợ; tên hàm, argument conversion hoặc proxy giống nhau |
| `Compilable` | Biên dịch script trước qua `compile` khi engine hỗ trợ | Caching/mã bytecode/compile artifact dùng chung giữa engine hay version |
| `ScriptException` | Kiểu lỗi API có thể báo khi evaluation thất bại | Mọi lỗi native/timeout/cancel được biểu diễn thống nhất |

`ScriptEngineManager` dựa trên cơ chế service provider của Java để khám phá `ScriptEngineFactory` có trên runtime classpath/module path. Có thể dùng `registerEngineName` để đăng ký factory **trong manager đang dùng**, nhưng đây không phải đăng ký một ngôn ngữ mới cho toàn JVM.

**Quan trọng đối với Java 17:** module `java.scripting` vẫn tồn tại, nhưng **JDK không mặc định kèm Nashorn JavaScript engine**. Nashorn đã bị loại khỏi JDK từ Java 15 (JEP 372). Vì vậy:

```java
ScriptEngineManager manager = new ScriptEngineManager();
ScriptEngine engine = manager.getEngineByName("JavaScript");
if (engine == null) {
    throw new IllegalStateException(
        "No JavaScript engine configured; add and verify a compatible provider");
}
```

Đây là **snippet**, cần import `javax.script.*`. Nó chỉ chạy tiếp khi hệ thống thực sự cài một JSR-223 JavaScript provider. Không được viết bài thực hành Java 17 mặc định với `engine.eval("1 + 2")` mà bỏ qua kiểm tra `null`. Khi sử dụng named module của ứng dụng, khai báo `requires java.scripting;` và cấu hình provider/module path theo hướng dẫn của engine được chọn.

## 2. Tính khả chuyển của cú pháp: cùng eval không có nghĩa cùng ngôn ngữ

`ScriptEngine.eval(String script)` yêu cầu một **chuỗi nội dung**, nhưng nội dung đó được parse theo **ngữ pháp và semantics của ngôn ngữ mà engine thực thi**.

Ví dụ những sự khác nhau cần cân nhắc:

- Cách khai báo biến, block, function và import/module: `let`/`const` trong JavaScript không phải cú pháp dùng chung với Groovy hoặc Python.
- Truthiness, toán tử cộng chuỗi, so sánh bằng nhau, thứ tự đánh giá, exception syntax.
- Số học: chia số nguyên hay số thực; overflow; precision; BigInt, decimal và các API số học.
- Phạm vi biến, closure, global object, async/promises/coroutines; cơ chế host interop.
- Các built-in như `Date`, `JSON`, `Math`, `print`, I/O hoặc package import có thể khác nhau.
- Dù cùng là ngôn ngữ “JavaScript”, engine/version khác nhau có thể hỗ trợ ECMAScript level, host access hoặc extension khác nhau.

Ví dụ sau **chỉ minh họa cú pháp của JavaScript**, không phải “script portable”:

```javascript
const price = 19.5;
const quantity = 2;
price * quantity;
```

Với một engine khác, phải cung cấp mã nguồn đúng ngôn ngữ của nó. JSR-223 không tự dịch `const`, operator, built-in hay control flow giữa các engine.

### Đọc metadata trước khi chạy

Một adapter có thể kiểm tra:

```java
ScriptEngineFactory f = engine.getFactory();
String engineName = f.getEngineName();
String engineVersion = f.getEngineVersion();
String language = f.getLanguageName();
String languageVersion = f.getLanguageVersion();
Object threading = f.getParameter("THREADING");
```

Đây là **snippet**; `engine` phải đã được tạo thành công. `getNames()`, `getExtensions()` và `getMimeTypes()` có thể liệt kê aliases/định danh do provider công bố. **Alias không phải định danh khả chuyển của một ngôn ngữ chuẩn**. “JavaScript” có thể trỏ tới engine khác nhau tùy dependency và class loader; luôn chốt implementation và version được hỗ trợ trong cấu hình sản phẩm.

Một cách chọn thực dụng:

1. Xác định **ngôn ngữ + engine/version** mà ứng dụng hỗ trợ (ví dụ một tập con cụ thể).
2. Chọn provider từ dependency đã kiểm soát, dùng engine name đã xác minh.
3. Kiểm tra metadata và thử một đoạn smoke test xác nhận tính năng cần thiết khi khởi động.
4. Nếu không có engine đúng yêu cầu, **fail fast**, không tự fallback sang ngôn ngữ khác.
5. Nếu phải thay engine, thực hiện migration và regression tests cho từng script, thay vì giả định “chỉ đổi engine name”.

### Invocable và Compilable là tùy chọn

`Invocable` và `Compilable` không phải capability bắt buộc của mọi `ScriptEngine`:

```java
if (engine instanceof Compilable compilable) {
    CompiledScript program = compilable.compile(scriptText);
    // Dùng program theo lifetime/version của chính engine.
} else {
    engine.eval(scriptText);
}

if (engine instanceof Invocable invocable) {
    // Chỉ khi script đã khai báo function tương thích.
    Object answer = invocable.invokeFunction("transform", input);
}
```

Đây là **snippet** với `engine`, `scriptText` và `input` đã được cung cấp; cần import `javax.script.*`. Ngay cả khi hỗ trợ `Invocable`, tên hàm, method binding, exception và conversion vẫn phụ thuộc ngôn ngữ/engine. `CompiledScript` cũng không phải định dạng artifact di động sang engine khác.

## 3. Vùng dữ liệu: Bindings, ScriptContext và state có thể rò giữa request

`Bindings` là một map có key dạng chuỗi, còn `ScriptContext` quản lý ít nhất hai scope: `ENGINE_SCOPE` và `GLOBAL_SCOPE`. Engine được phép có **ngữ cảnh nội bộ, biến toàn cục, runtime cache hoặc host object references**, tùy implementation. Do đó “mỗi lần `eval` truyền Bindings riêng” không tự khẳng định mọi state bên trong engine đều được cô lập.

Ví dụ Java caller cấp tham số:

```java
Bindings b = engine.createBindings();
b.put("customerId", "C-100");
b.put("quantity", 3);
Object raw = engine.eval(scriptText, b);
```

Đây là **snippet**; việc script nhìn thấy `customerId` với cú pháp nào phải theo engine cụ thể. Phía Java nên dựng **Bindings riêng cho từng evaluation**, không sửa map đó đồng thời trong khi engine đang đọc; một object như `List`, `Map` hay service Java đặt trong Bindings vẫn có thể có mutable state dùng chung.

### Quy tắc state ownership

- Tách **input values** khỏi **engine global state**; không dùng `engine.put("user", ...)` trên singleton engine cho nhiều người dùng đồng thời mà không có hợp đồng về threading và isolation.
- Tạo engine/context theo scope phù hợp (evaluation, worker, session hoặc app), xác định khi nào reset, dispose và có thể tái sử dụng.
- Nếu mỗi request cần độc lập tuyệt đối, một `ScriptContext` mới không nhất thiết đủ; có thể cần engine mới hoặc process mới.
- Một factory có thể công bố metadata `getParameter("THREADING")`. Ý nghĩa của các giá trị chuẩn theo JDK 17:

| `THREADING` | Hợp đồng về đồng thời do engine công bố |
| --- | --- |
| `null` | Engine không thread-safe; không gọi đồng thời trên cùng instance |
| `"MULTITHREADED"` | Engine tự đồng bộ để cho phép chạy đồng thời, nhưng tác động giữa scripts có thể nhìn thấy nhau |
| `"THREAD-ISOLATED"` | Đạt điều kiện MULTITHREADED và giữ các giá trị symbol độc lập giữa threads |
| `"STATELESS"` | Đạt THREAD-ISOLATED và chạy script không thay đổi map `Bindings` của ENGINE_SCOPE |

Metadata về threading **không phải bảo đảm sandbox/security**; host objects truyền vào vẫn có concurrency contract riêng. `getParameter("THREADING") == null` nên được xử lý theo giả định **không chia sẻ đồng thời**. Nếu muốn chạy song song, dùng pool các engine độc lập **chỉ khi nhà cung cấp cho phép**, hoặc tạo worker/process riêng theo policy.

## 4. Chuyển đổi kiểu: không có “Object portable” giữa mọi engine

Ở phía Java, `ScriptEngine.eval` trả `Object`. Ở phía script, hệ kiểu có thể khác Java. Engine sẽ dùng chiến lược riêng để biểu diễn/chuyển giá trị:

| Giá trị tại ranh giới | Rủi ro thường gặp | Nguyên tắc |
| --- | --- | --- |
| Số nguyên `int`, `long` | Engine chuyển thành double, BigInteger, wrapper khác hoặc proxy | Validate `Number` thực tế; không ép `(Integer) raw` |
| Số thực `double` | Sai số binary floating-point; NaN, ±Infinity | Hợp đồng precision/range rõ ràng, không dùng trực tiếp cho tiền |
| `BigDecimal` | Engine có thể giữ host object, đổi sang floating-point, hoặc không hỗ trợ | Encode decimal thành string/typed record rồi parse theo quy tắc |
| `boolean` | Truthiness và quy tắc chuyển sang Boolean khác nhau | Yêu cầu trả đúng Boolean, không coi 0/`""`/null là false ngầm |
| `String` | Charset, Unicode normalization, escape và interpolation | Hợp đồng string/encoding/normalization rõ |
| `null`, giá trị thiếu, “undefined” | Thiếu key khác key có value null; engine có sentinel riêng | Kiểm tra `Bindings.containsKey`, mô hình nullability riêng |
| Mảng/list | Có thể là `List` Java, script array, proxy, wrapper | Không cast mù; chuyển sang DTO/List được kiểm soát |
| Object/map | Script object có thể không phải `java.util.Map` | Adapter chuyển key/value và validate schema |
| Date/time | Các ngôn ngữ/engine khác precision, timezone, format | Dùng ISO-8601 hoặc epoch có đơn vị/time zone xác định |
| Java host object | Có thể phơi methods/reflection/quyền của host | Chỉ cấp facade được phép; không dựa vào conversion như cơ chế bảo mật |
| Function/promise/async handle | Có thể là object sống phụ thuộc runtime/engine | Không trả thẳng qua boundary ổn định; resolve thành dữ liệu chuẩn |

Ví dụ kiểm tra kiểu rõ ràng:

```java
Object raw = engine.eval(scriptText, bindings);
if (!(raw instanceof Number n)) {
    throw new IllegalArgumentException("Script must return a number");
}
double value = n.doubleValue();
if (!Double.isFinite(value)) {
    throw new IllegalArgumentException("Non-finite result");
}
```

Đây là **snippet**. Nó phù hợp khi API ứng dụng **chấp nhận số thực có sai số double**. Nó **không phù hợp** nếu kết quả là số tiền/ID nguyên lớn cần bảo toàn chính xác; `doubleValue()` có thể mất precision từ `BigDecimal`/`BigInteger`.

### Ví dụ về integer precision

Java `long` có thể biểu diễn số 9.007.199.254.740.993 (2^53 + 1). Với semantics số học kiểu IEEE-754 double như JavaScript `Number`, không phải mọi số nguyên quá 2^53 − 1 đều biểu diễn chính xác. Một JSR-223 provider có thể chuyển `Long` theo cách riêng; **không được giả định script luôn nhận chính xác toàn bộ 64-bit ID**. Với ID, dùng chuỗi decimal hoặc một kiểu BigInt được support và test rõ ràng.

### Decimal cho tiền và độ chính xác

Thay vì đẩy `double` rồi hy vọng engine giữ đúng:

```java
Bindings b = engine.createBindings();
b.put("amountText", "0.10");       // decimal theo contract
b.put("currency", "VND");
Object raw = engine.eval(scriptText, b);

// Giả sử contract yêu cầu script trả decimal dạng String:
if (!(raw instanceof String decimalText)) {
    throw new IllegalStateException("Expected decimal string result");
}
java.math.BigDecimal amount = new java.math.BigDecimal(decimalText);
```

Đây là **snippet của một giao thức ứng dụng**, không bảo đảm mọi engine sẽ tự coi `amountText` là số decimal. Adapter script phải parse/format theo ngôn ngữ của engine, nêu rõ quy tắc scale, rounding và invalid input. Dùng `BigDecimal(String)` thay vì `BigDecimal(double)` nếu cần độ chính xác biểu diễn decimal đầu vào.

### Đề xuất một output contract có thể kiểm thử

Thay vì để nghiệp vụ phụ thuộc class implementation của provider, định nghĩa output là:

- Một DTO/record rõ schema ở phía Java, với các field cơ bản như `String`, `boolean`, `List`, string decimal và thời gian ISO-8601;
- Hoặc JSON text có JSON schema/contract version rõ; các script engine phải chủ động serialize thành JSON text theo runtime của chúng; Java parse bằng thư viện đã chọn.

Các kiểu từ script cần đi qua **adapter nhận diện và validate**. Không nên ép `(Map<String,Object>) engine.eval(...)` nếu nhà cung cấp chưa bảo đảm kết quả là `Map` Java. Đặc biệt tránh leak object proxy còn phụ thuộc engine đã dispose.

## 5. Khi nào phân biệt null, missing và exception?

Một giao diện script có thể quy định:

- **Missing input**: không có key `"limit"` trong Bindings; xử lý bằng `containsKey` trước khi `get`.
- **Explicit null**: có key nhưng value `null`; biểu thị “không có giá trị” nếu schema cho phép.
- **Undefined / nil / None**: khái niệm ở một số ngôn ngữ script; conversion của engine có thể trả `null`, sentinel object hoặc ném lỗi.
- **Evaluation failure**: syntax error, runtime error, host interop error; `ScriptException` là đường báo phổ biến nhưng implementation có thể có wrapper/native exception khác.
- **Timeout/cancellation**: do ứng dụng chủ động quản lý, **không phải một biến thể bắt buộc của null hoặc ScriptException**.

Không dùng `raw == null` để kết luận “script chưa tìm thấy biến” hoặc “engine timeout”. Phải có response envelope/app-level status riêng, ví dụ `SUCCESS(value)`, `SCRIPT_ERROR`, `TIMEOUT`, `CANCELLED`, `ENGINE_UNAVAILABLE`. Với security, không đưa stack trace host hoặc bí mật vào thông báo cho caller.

## 6. Cơ chế dừng: ScriptEngine không có API stop chuẩn

`ScriptEngine` định nghĩa `eval`, `put/get`, `getContext`, `setBindings`, `createBindings`, `getFactory`. **Không có method chuẩn**:

```text
engine.stop()
engine.interrupt()
engine.terminate()
engine.close()    // không thuộc javax.script.ScriptEngine interface
```

Đây chỉ là **tên giả để minh họa API không tồn tại**; không được gọi trong mã Java thực tế. Một số nhà cung cấp cung cấp API riêng để cancel/close context, đặt instruction limit hoặc timeout; phải đọc contract/version của provider đó.

Cần phân biệt:

| Hành động | Thực tế được bảo đảm | Điều không bảo đảm |
| --- | --- | --- |
| `Future.get(timeout, unit)` | Thread caller chỉ đợi đến hạn rồi nhận `TimeoutException` | Script worker tự dừng |
| `Future.cancel(true)` | Nếu cancel thành công, đánh dấu future đã hủy và yêu cầu interrupt thread đang chạy nếu phù hợp | Engine/script tôn trọng interruption |
| `Thread.interrupt()` | Đặt interruption flag, có thể khiến các blocking method interruptible ném `InterruptedException` | Interpreter/native call/vòng CPU sẽ thoát |
| `ExecutorService.shutdownNow()` | Cố ngắt tasks, trả danh sách tasks chưa chạy | Bắt buộc kill được mọi task đang chạy |
| API cancel/close **riêng của engine** | Hành vi theo tài liệu nhà cung cấp | Phổ quát giữa các engine |
| Giới hạn bằng **process/container riêng** | Host có thể kết thúc process và thu hồi tài nguyên ở ranh giới OS | Kết quả script còn dở sẽ tự rollback external side effects |

**Không dùng `Thread.stop()` để cưỡng bức dừng script.** Nó không an toàn, có thể để locks và object ở trạng thái hỏng, và không giải quyết side effects bên ngoài. Trong JVM dùng chung, không có một phép “kill thread chạy script” bảo đảm an toàn ở mọi engine.

### Một mẫu timeout chỉ giới hạn thời gian chờ

```java
Future<Object> future = executor.submit(
    () -> engine.eval(scriptText, requestBindings));
try {
    return future.get(250, TimeUnit.MILLISECONDS);
} catch (TimeoutException timeout) {
    future.cancel(true);  // yêu cầu interrupt, KHÔNG bảo đảm script dừng
    throw new IllegalStateException("Script exceeded deadline", timeout);
}
```

Đây là **snippet bên trong một method trả `Object`**, cần `ExecutorService executor`, `ScriptEngine engine`, `String scriptText` và `Bindings requestBindings` đã được thiết lập. Cần import `java.util.concurrent.*` và xử lý `InterruptedException`/`ExecutionException` ở method bao ngoài. Nếu worker không hợp tác, `Future` có thể đã ở trạng thái canceled trong khi task vẫn chạy. Không được trả engine/thread đó về pool để tái sử dụng như thể đã sạch.

### Dừng mềm và dừng cứng

**Dừng mềm (cooperative cancellation):** script engine hoặc mã script kiểm tra `interrupt`/cancellation token định kỳ; khi cần thoát thì ném hoặc trả về trạng thái kết thúc. Tốt cho DSL tự phát triển hoặc engine có documented cancellation hooks. Cần kiểm tra thực nghiệm với CPU loop, blocking I/O, host callbacks và từng bản engine.

**Dừng cứng (isolation boundary):** đối với script không đáng tin cậy hoặc có deadline cứng, chạy engine trong **process riêng** có quota CPU/RAM/thời gian và hạn chế quyền truy cập. Khi quá hạn, host dừng process theo chính sách; thao tác này tránh phụ thuộc vào việc một Java thread có tự kết thúc hay không. Vẫn phải thiết kế idempotency/transaction cho filesystem, database, network calls nếu script từng tạo side effects.

Quyết định quan trọng: **timeout của request ≠ engine đã dừng**. Hệ thống cần quan sát task thực sự kết thúc, quản lý worker bị treo, giới hạn số worker đồng thời và cleanup theo vòng đời.

## 7. Ví dụ chạy độc lập Java 17: engine tự đăng ký, kiểm soát kiểu, cancel hợp tác

Để ví dụ chạy được trên **JDK 17 thuần**, không giả định có JavaScript engine. Chúng ta viết một **DemoDSL nhỏ** (không phải JavaScript, không phải interpreter đầy đủ), dùng đúng `javax.script`:

- `DemoFactory` công bố metadata ngôn ngữ/engine và đăng ký alias `demo-dsl` trong một `ScriptEngineManager`.
- `DemoEngine extends AbstractScriptEngine` hiểu đúng hai lệnh `add` và `wait`; `add` nhận hai `BigDecimal` từ Bindings và trả về `BigDecimal` để caller validate kiểu.
- `wait` chỉ được dùng để minh họa **cooperative interruption**: nó gọi `Thread.sleep` và ném `ScriptException` khi bị interrupt. Điều này **không phải hành vi mặc định của mọi engine**.
- `THREADING=null` tuyên bố engine demo không thread-safe. Chương trình chỉ gọi `add` trên main trước khi task `wait` bắt đầu; không chạy hai `eval` đồng thời.

### 7.1. File ScriptBoundaryDemo.java

```java
import java.io.IOException;
import java.io.Reader;
import java.math.BigDecimal;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import javax.script.AbstractScriptEngine;
import javax.script.Bindings;
import javax.script.ScriptContext;
import javax.script.ScriptEngine;
import javax.script.ScriptEngineFactory;
import javax.script.ScriptEngineManager;
import javax.script.ScriptException;
import javax.script.SimpleBindings;

public final class ScriptBoundaryDemo {
    static final class DemoFactory implements ScriptEngineFactory {
        public String getEngineName() { return "Controlled Demo DSL"; }
        public String getEngineVersion() { return "1"; }
        public List<String> getExtensions() { return List.of("demo"); }
        public List<String> getMimeTypes() { return List.of("text/x-demo"); }
        public List<String> getNames() { return List.of("demo-dsl"); }
        public String getLanguageName() { return "DemoDSL"; }
        public String getLanguageVersion() { return "1"; }

        public Object getParameter(String key) {
            return switch (key) {
                case ScriptEngine.ENGINE -> getEngineName();
                case ScriptEngine.ENGINE_VERSION -> getEngineVersion();
                case ScriptEngine.LANGUAGE -> getLanguageName();
                case ScriptEngine.LANGUAGE_VERSION -> getLanguageVersion();
                case ScriptEngine.NAME -> getNames().get(0);
                case "THREADING" -> null;
                default -> null;
            };
        }

        public String getMethodCallSyntax(String obj, String method, String... args) {
            throw new UnsupportedOperationException("No method calls in DemoDSL");
        }
        public String getOutputStatement(String text) {
            throw new UnsupportedOperationException("No print statements in DemoDSL");
        }
        public String getProgram(String... statements) {
            return String.join("\n", statements);
        }
        public ScriptEngine getScriptEngine() { return new DemoEngine(this); }
    }

    static final class DemoEngine extends AbstractScriptEngine {
        private final ScriptEngineFactory factory;

        DemoEngine(ScriptEngineFactory factory) { this.factory = factory; }

        @Override
        public Object eval(String script, ScriptContext context) throws ScriptException {
            if ("add".equals(script)) {
                Object a = context.getAttribute("a");
                Object b = context.getAttribute("b");
                if (!(a instanceof BigDecimal left)
                        || !(b instanceof BigDecimal right)) {
                    throw new ScriptException("a and b must be BigDecimal");
                }
                return left.add(right);
            }
            if ("wait".equals(script)) {
                Object value = context.getAttribute("started");
                if (!(value instanceof CountDownLatch started)) {
                    throw new ScriptException("missing started latch");
                }
                started.countDown();
                try {
                    while (true) {
                        Thread.sleep(1000);
                    }
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    throw new ScriptException("interrupted by host");
                }
            }
            throw new ScriptException("Unsupported DemoDSL command: " + script);
        }

        @Override
        public Object eval(Reader reader, ScriptContext context) throws ScriptException {
            StringBuilder text = new StringBuilder();
            char[] buffer = new char[1024];
            try {
                int n;
                while ((n = reader.read(buffer)) != -1) {
                    text.append(buffer, 0, n);
                }
            } catch (IOException ex) {
                throw new ScriptException(ex);
            }
            return eval(text.toString().trim(), context);
        }

        @Override
        public Bindings createBindings() { return new SimpleBindings(); }

        @Override
        public ScriptEngineFactory getFactory() { return factory; }
    }

    public static void main(String[] args) throws Exception {
        ScriptEngineManager manager = new ScriptEngineManager();
        manager.registerEngineName("demo-dsl", new DemoFactory());
        ScriptEngine engine = manager.getEngineByName("demo-dsl");
        if (engine == null) throw new IllegalStateException("Engine missing");

        Bindings input = engine.createBindings();
        input.put("a", new BigDecimal("0.1"));
        input.put("b", new BigDecimal("0.2"));
        Object result = engine.eval("add", input);
        if (!(result instanceof BigDecimal sum)) {
            throw new IllegalStateException("Unexpected result type");
        }
        System.out.println("engine=" + engine.getFactory().getEngineName());
        System.out.println("sum=" + sum.toPlainString());
        System.out.println("type=" + result.getClass().getSimpleName());
        System.out.println("threading=" + engine.getFactory().getParameter("THREADING"));

        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        Bindings waitInput = engine.createBindings();
        waitInput.put("started", started);
        try {
            Future<?> running = executor.submit(() -> engine.eval("wait", waitInput));
            if (!started.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Demo did not start");
            }
            System.out.println("cancelRequested=" + running.cancel(true));
        } finally {
            executor.shutdownNow();
        }
        System.out.println("workerStopped=" + executor.awaitTermination(5, TimeUnit.SECONDS));
    }
}
```

### 7.2. Biên dịch và kết quả

Từ thư mục chứa `ScriptBoundaryDemo.java`, dùng JDK 17+:

```bash
javac --release 17 ScriptBoundaryDemo.java
java ScriptBoundaryDemo
```

**Stdout đã kiểm chứng bằng `javac --release 17` và `java`:**

```text
engine=Controlled Demo DSL
sum=0.3
type=BigDecimal
threading=null
cancelRequested=true
workerStopped=true
```

### 7.3. Những gì chương trình chứng minh — và không chứng minh

**Đã chứng minh trong engine minh họa:**

1. `ScriptEngineManager.registerEngineName("demo-dsl", ...)` cung cấp factory cho alias được đăng ký **trong manager này**; chúng ta không phải cài một JavaScript engine.
2. `engine.createBindings()` và `engine.eval("add", input)` dùng API chung của JSR-223.
3. Lệnh `add` của **DemoDSL**, chứ không phải biểu thức JavaScript, trả một `BigDecimal`; Java kiểm tra `instanceof` trước khi dùng.
4. `getFactory().getParameter("THREADING")` trả `null` theo metadata do chính demo công bố: **không chia sẻ engine này cho eval đồng thời**.
5. `CountDownLatch` bảo đảm task `wait` đã bắt đầu trước khi `cancel(true)`. `DemoEngine` chủ động phản ứng với interruption ở `Thread.sleep`; sau đó worker thật sự thoát, nên `awaitTermination` trả `true`.

**Không được suy rộng:**

- Không phải mọi engine hiểu `add`, `wait`, có `BigDecimal` output, hay hỗ trợ interruption.
- `cancelRequested=true` **một mình** không phải bằng chứng script đã dừng; chính `workerStopped=true` xác nhận **worker demo** đã kết thúc.
- Demo có một tác vụ, không chứng minh engine thread-safe hoặc scale tốt khi nhiều concurrent requests.
- `DemoDSL` chỉ xử lý hai lệnh kiểm thử, không phải một ngôn ngữ production. Những method metadata không dùng trong ví dụ không xác lập grammar/semantics đầy đủ như engine thương mại.
- Không nên dùng chính ví dụ này làm sandbox cho source untrusted; nó chạy trong cùng JVM của host.

## 8. Kiến trúc adapter khi phải hỗ trợ nhiều script engine

Đề xuất tách tầng:

```text
Business API
  Input DTO / schema / deadline / tenantId
          |
          v
Script Execution Adapter
  - chọn engine/version cố định
  - validate types và permissions
  - tạo Bindings/context
  - chuyển request thành cú pháp engine-specific
  - áp dụng deadline/stop policy
          |
          v
ScriptEngine / provider runtime
  language-specific syntax & host interop
          |
          v
Adapter kiểm tra result + lỗi
  - normalize dữ liệu
  - chuẩn hóa status
  - release/retire resources
          |
          v
Business response DTO
```

Không cho business code rải khắp nơi các lệnh `eval("...")` và cast kết quả trực tiếp sang nhiều kiểu. Thay vào đó, có thể định nghĩa interface Java:

```java
public interface ScriptRunner {
    ScriptResult execute(ScriptRequest request);
}
```

Đây là **snippet contract**, `ScriptRequest` và `ScriptResult` là DTO/record do ứng dụng định nghĩa, không phải kiểu có sẵn trong JDK. Một adapter ứng với một engine/version có nhiệm vụ biên dịch template/script source, validate inputs/outputs, áp dụng policy runtime và phân biệt lỗi.

Ví dụ phân loại lỗi ở ranh giới:

| Mã ứng dụng | Điều kiện | Xử lý |
| --- | --- | --- |
| `ENGINE_UNAVAILABLE` | Không có engine mong muốn hoặc version sai | Fail fast tại startup; không chuyển sang engine khác ngầm |
| `SYNTAX_ERROR` | Parser/compile/eval trả lỗi cú pháp | Ghi nguồn script, line/column đã sanitize |
| `INPUT_TYPE_ERROR` | Bindings thiếu field hoặc sai kiểu theo schema | Trả lỗi validation trước khi eval |
| `OUTPUT_TYPE_ERROR` | `eval` trả null/sentinel/proxy/kiểu không mong đợi | Không cast mù; reject hoặc normalize theo contract |
| `EXECUTION_ERROR` | Script/runtime/host callback thất bại | Wrap error có nguyên nhân; bảo vệ secret |
| `TIMEOUT` | Caller hết deadline | Gửi cancel nếu hỗ trợ, cô lập/quản lý worker có thể còn chạy |
| `CANCELLED` | Chính sách host chủ động dừng | Phân biệt cancel request, cancel acknowledged và actual termination |
| `RESOURCE_LIMIT` | Vượt memory/CPU/IO quota trong môi trường isolation | Kết thúc worker/process theo policy |

Các trạng thái là **hợp đồng gợi ý của ứng dụng**, không phải mã enum do JSR-223 định nghĩa.

### Phân lớp thời gian sống

- **Factory/metadata**: có thể giữ ở phạm vi registry sau khi kiểm tra.
- **Engine instance**: lifetime theo docs của provider, không tự mặc định singleton thread-safe.
- **Bindings/ScriptContext**: lý tưởng là request-scoped đối với input nhạy cảm; không để host objects hoặc user state tồn tại vô hạn.
- **CompiledScript**: gắn với engine/compiler version và class loader, cache theo key có version/tenant khi phù hợp.
- **Execution task**: deadline rõ; khi cancel phải kiểm tra đã kết thúc, tránh dùng lại worker đang chạy script cũ.
- **Plugin/class loader/engine context**: thu hồi khi không còn active executions; API chuẩn không tự đóng mọi tài nguyên vendor-specific.

## 9. Tối thiểu phải kiểm thử những gì khi thay engine?

Để xác nhận một ứng dụng “hỗ trợ nhiều engine”, cần test **behavioral contract**, không chỉ test gọi `getEngineByName` thành công.

| Nhóm kiểm thử | Trường hợp quan trọng |
| --- | --- |
| Discovery | engine thiếu, alias thay đổi, dependency thiếu, class loader/TCCL khác |
| Cú pháp | biến, function, import, literal, exception, async, syntax/version không được hỗ trợ |
| Kiểu số | số âm, 0, integer rất lớn, decimal `0.1 + 0.2`, NaN/Infinity, overflow/rounding |
| Nullability | missing key, explicit null, undefined/nil/None và engine sentinel |
| Chuỗi | Unicode, escape, ký tự điều khiển, normalization, empty string |
| Collection | nested list/map, key order, mutable aliasing, proxy còn sống sau eval |
| Host interop | Java object exposure, method overload, class access, callback exceptions |
| Context | engine/global scope, reuse engine, multithreading, cross-request leakage |
| Stop | timeout khi sleep, CPU-tight loop, blocking I/O, callback host, race giữa completion/cancel |
| Cleanup | lingering thread, executor queue, memory retention, external side effects, context/loader dispose |
| Khả chuyển | cùng input DTO → cùng normalized output/error trên các engine được hỗ trợ |

**Một test timeout chỉ gọi `future.get(timeout)` rồi nhìn thấy `TimeoutException` là chưa đủ.** Phải kiểm tra worker thực sự ngừng tiêu CPU/giữ tài nguyên sau đó, nhất là với script có vòng lặp vô hạn hoặc plugin native/host callbacks.

## 10. Những lỗi dễ gây sự cố production

### Lỗi 1 — Giả định Java 17 tích hợp sẵn JavaScript

`new ScriptEngineManager().getEngineByName("javascript")` có thể là `null` nếu runtime không có provider. **Giải pháp:** declare dependency và class loader/module visibility rõ ràng; pin engine + language version; fail fast.

### Lỗi 2 — Đổi engine mà giữ nguyên chuỗi script

JSR-223 chuẩn hóa method `eval`, không chuẩn hóa ngữ pháp. **Giải pháp:** có adapter script theo language/version, test semantics và migration plan.

### Lỗi 3 — Ép kiểu thẳng sau eval

`Integer result = (Integer) engine.eval("...")` có thể thất bại nếu provider trả `Double`, `Long`, `BigDecimal` hoặc wrapper khác. **Giải pháp:** validate `Object` và normalize qua DTO. Không chuyển mọi số sang `double` khi cần ID/tiền chính xác.

### Lỗi 4 — Đồng nhất null, missing và undefined

Một giá trị `null` trả về không giúp xác định script có chạy thành công hay không. **Giải pháp:** validate input schema, dùng `containsKey` ở Bindings, response envelope rõ status/nullability.

### Lỗi 5 — Dùng singleton engine cho mọi request

Nếu `THREADING=null`, gọi `eval` đồng thời là vi phạm khả năng hỗ trợ của engine. Ngay cả `MULTITHREADED` cũng có thể cho các script nhìn thấy shared state. **Giải pháp:** quản lý engine/context per scope và chỉ chia sẻ theo documented contract.

### Lỗi 6 — Coi cancel(true) là kill

`Future.cancel(true)` chỉ phát tín hiệu interrupt; script có thể tiếp tục chạy nếu engine không hợp tác. **Giải pháp:** phân biệt “request deadline exceeded”, “cancellation requested” và “execution terminated”; dùng process isolation khi cần giới hạn cứng.

### Lỗi 7 — Xem JSR-223 là sandbox

`ScriptEngine` không đặt biên quyền filesystem, network, class loading hay host object access. **Giải pháp:** giới hạn API/host bindings, dùng nguyên tắc least privilege và chạy script chưa tin cậy ngoài process đặc quyền; kiểm soát CPU/RAM/IO.

### Lỗi 8 — Bỏ qua lifecycle, cleanup và side effects

Engine vendor-specific có thể giữ thread, context, cache, class loader hoặc native resources. **Giải pháp:** tuân theo API close/cancel của provider khi có, đóng stream/reader khi sở hữu, không reuse worker đã treo; thiết kế transaction/idempotency cho side effects script.

## 11. Checklist thiết kế trước khi triển khai

- [ ] Chỉ định một **engine implementation + version + language level** được chấp thuận; không phụ thuộc alias mơ hồ.
- [ ] Kiểm tra engine có thực sự tồn tại trên Java runtime; Java 17 không mặc định có Nashorn.
- [ ] Chỉ dùng `eval` như abstraction gọi, không coi syntax/libraries của script là portable.
- [ ] Kiểm tra `Invocable`/`Compilable` trước khi dùng; không giả định mọi engine hỗ trợ.
- [ ] Định nghĩa input/output schema: nullability, numbers, BigDecimal, dates, collections, exceptions.
- [ ] Không cast kết quả `Object` mà không validate; giữ độ chính xác cho ID và tài chính.
- [ ] Tạo Bindings theo request, kiểm tra `THREADING` và isolation, tránh rò engine state.
- [ ] Có deadline và cancellation policy rõ; biết `get(timeout)` chỉ giới hạn caller wait.
- [ ] Nếu cần dừng chắc chắn script thiếu hợp tác, chạy process/container tách biệt với quota.
- [ ] Dùng API close/cleanup của vendor theo đúng vòng đời; không coi `ScriptEngine` có `close` chuẩn.
- [ ] Tách quyền host/API khỏi dữ liệu script; không chạy source untrusted ở JVM đặc quyền.
- [ ] Test syntax/interop/timeout/cleanup với **đúng engine và version sẽ triển khai**.

### Tài liệu gốc Java 17

- [`ScriptEngine`](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptEngine.html)
- [`ScriptEngineManager`](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptEngineManager.html)
- [`ScriptEngineFactory` và metadata `THREADING`](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptEngineFactory.html)
- [`Bindings` và `ScriptContext`](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/Bindings.html)
- [JEP 372: Remove the Nashorn JavaScript Engine](https://openjdk.org/jeps/372)
- [`Future.cancel` / `Future.get(timeout)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html)

**Ghi nhớ:** `javax.script` giúp Java gọi engine qua một API chung, nhưng **script syntax, host-object conversion và stop/cancel semantics thuộc về từng engine**. Muốn hệ thống khả chuyển và an toàn, hãy khóa version, validate dữ liệu thành một giao thức riêng, và chọn chính sách dừng theo mức tin cậy của code — không dựa vào một lời gọi `eval` hay `Future.cancel(true)` để thay thế các bảo đảm đó.
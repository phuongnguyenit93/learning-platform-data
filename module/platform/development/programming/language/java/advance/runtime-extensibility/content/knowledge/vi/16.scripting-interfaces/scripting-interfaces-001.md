# Chuyển đổi kiểu giữa Java và ngôn ngữ kịch bản theo quy tắc của engine

## 1. Bản chất của ranh giới Java ↔ script

Trong ứng dụng Java nhúng kịch bản qua JSR 223 (`javax.script`), chương trình Java truyền dữ liệu vào `ScriptEngine`, cho phép kịch bản tính toán rồi nhận dữ liệu trở lại. Điều dễ nhầm là **JSR 223 không quy định một bảng chuyển đổi kiểu phổ quát cho mọi ngôn ngữ**. API chỉ trao đổi các đối tượng Java qua `Bindings`, `ScriptContext` và giá trị `Object` từ `eval`; engine cụ thể quyết định cách biểu diễn, ép kiểu, chuyển đổi và truy cập các đối tượng ấy từ phía ngôn ngữ script.

Ví dụ `java.lang.Integer` có thể được nhìn như số nguyên, số động, đối tượng Java được bọc (*host object*) hoặc một giá trị đặc biệt tùy engine. Một array, `List`, `Map`, `null` hoặc đối tượng domain cũng không có hành vi đồng nhất giữa JavaScript, Python, Groovy, Kotlin scripting và các runtime khác.

### Ba bước độc lập

1. **Marshalling vào script**: host đưa Java object vào `Bindings`/`ScriptContext`; engine ánh xạ object đó sang giá trị mà script nhìn thấy.
2. **Tính toán và gọi API**: script có thể áp dụng quy tắc numeric coercion, property lookup, overload resolution và các chuyển đổi nội bộ riêng.
3. **Marshalling về Java**: `ScriptEngine.eval(...)` trả `Object`; host phải kiểm tra class thực tế và chuyển sang kiểu domain mong muốn theo contract đã định.

Không nên suy luận kiểu của giá trị chỉ từ cú pháp script. Hãy kiểm tra tài liệu engine, version cụ thể và dùng thử nghiệm tương thích trước khi xây dựng API ổn định.

## 2. JSR 223 cung cấp những gì và không cung cấp gì?

| Thành phần | Hợp đồng JSR 223 | Không được bảo đảm chung |
|---|---|---|
| `ScriptEngine.put(name, Object)` | Đưa giá trị vào engine-scope bindings | Engine sẽ hiển thị Java object như loại script nào |
| `Bindings` | Ánh xạ key `String` sang giá trị Java | Tự động chuyển `Map`, `List`, `record` thành object native của script |
| `ScriptContext` | Quản lý scope, reader/writer/error writer, attributes | Cô lập bảo mật hoặc ngăn mọi tác dụng phụ |
| `ScriptEngine.eval(source)` | Đánh giá script, trả Java `Object` hoặc `null` | Kết quả số luôn là `Integer`/`Double` hoặc boolean luôn là `Boolean` |
| `Invocable.invokeFunction/invokeMethod` | Gọi hàm/phương thức nếu engine triển khai `Invocable` | Engine luôn hỗ trợ gọi function hoặc tự map overload chính xác |
| `getInterface(...)` | Tùy chọn ánh xạ script sang interface Java | Mọi engine đều hỗ trợ hoặc có cùng quy tắc chuyển kiểu |

JDK 17 có module `java.scripting` chứa API, nhưng **không kèm sẵn một JavaScript engine**. Nashorn đã bị loại khỏi JDK từ Java 15. Muốn dùng JavaScript, Python hoặc Groovy cần engine phù hợp được cài và nhìn thấy được qua module path/class loader. Bài này vì vậy sử dụng một engine JSR 223 tối giản để minh họa contract mà không phụ thuộc thư viện ngoài.

## 3. Những nhóm kiểu thường gặp

### 3.1. Số: Integer, Long, Double, BigDecimal

Engine có thể dùng số thực 64-bit cho mọi phép tính, phân biệt integer/float, dùng big integers hoặc trả wrapper Java. Khi trả kết quả sang Java, **không ép kiểu cứng** nếu chưa kiểm tra:

```java
Object result = engine.eval("someNumericExpression");
if (!(result instanceof Number number)) {
    throw new IllegalArgumentException("Expected numeric result");
}
double value = number.doubleValue();
```

Đây là đoạn minh họa, không chạy độc lập vì cần `engine`. `doubleValue()` có thể mất độ chính xác đối với `BigDecimal` hoặc số nguyên rất lớn; nếu là tiền hoặc dữ liệu chính xác, hãy dùng contract trả decimal string hoặc `BigDecimal` khi engine hỗ trợ.

Quy tắc chuyển kiểu nên được viết ra rõ ràng: số nguyên không âm trong khoảng nào, xử lý overflow/underflow ra sao, có cho phép `NaN`/`Infinity` không, và khi nào được làm tròn. Không coi việc `Number` tồn tại là đủ để dữ liệu hợp lệ.

### 3.2. Chuỗi và ký tự

Java `String` thường dễ truyền qua biên giới nhưng engine có thể trả kiểu string riêng. `String.valueOf(result)` chỉ là chuyển bằng Java `toString()`, **không** phải bộ chuyển ngữ nghĩa tổng quát: với `null` nó trả chuỗi ký tự `"null"`, không biểu diễn missing value; với một đối tượng phức tạp nó có thể trả mô tả thay vì dữ liệu.

Với API public, nên yêu cầu rõ `result instanceof String`, hoặc dùng hàm serializer được chỉ định (JSON/DTO) thay vì bất kỳ object nào cũng gọi `toString()`.

### 3.3. Boolean, null, missing và undefined

`null` trong Java không nhất thiết tương ứng với `null`, `nil`, `None` hay `undefined` của script. Một số ngôn ngữ phân biệt giá trị *không có property*, *property có giá trị null* và *undefined*. Ở ranh giới Java phải quyết định liệu các trạng thái này được đồng nhất hay giữ riêng.

Ví dụ với bindings:

```java
Bindings bindings = engine.createBindings();
bindings.put("presentButNull", null);
System.out.println(bindings.containsKey("presentButNull")); // true
System.out.println(bindings.containsKey("missing"));        // false
```

Đoạn minh họa cho thấy `Bindings` có thể phân biệt key tồn tại với giá trị `null` và key không tồn tại; cách ngôn ngữ script truy cập hai trạng thái đó lại tùy engine. Đừng dùng `bindings.get(name) == null` để kết luận key chắc chắn không tồn tại.

### 3.4. Collection, Map và object

Java `List`/`Map` có thể được engine đưa vào như proxy/host object, chuyển thành array/object script hoặc chỉ cung cấp một số thao tác. Truy cập `map.key` không nhất thiết tương đương `map.get("key")`; index bắt đầu 0 hay 1, iteration order, mutability và treatment of missing keys còn tùy ngôn ngữ.

Khi chuyển dữ liệu qua biên giới engine, hướng tiếp cận dễ kiểm thử là định nghĩa DTO có kiểu hạn chế (string, boolean, number trong range, list/map đã kiểm tra, null) hoặc JSON schema. Tuy nhiên JSON không tự giữ nguyên `BigDecimal`, ngày giờ, binary data, object identity hay circular reference; phải có quy ước nếu cần các dạng đó.

### 3.5. Java domain object

Nếu đặt một đối tượng Java vào bindings, script engine có thể cho phép gọi method/property theo quy tắc reflection hoặc proxy của engine. Điều này tạo coupling mạnh với API Java, overload, visibility, class loader và module accessibility.

Với nguồn script không tin cậy, tuyệt đối không truyền object có quyền hệ thống mạnh như `ClassLoader`, `Runtime`, file system handle, credential holder hoặc service quản trị. **Class loader riêng không phải sandbox bảo mật**.

## 4. Ví dụ Java 17+ có thể chạy mà không cần engine bên thứ ba

Để tập trung vào quy tắc **do engine xác định**, ta viết một JSR 223 engine rất nhỏ hiểu ba lệnh: `echo`, `number`, `text`. Nó không phải một ngôn ngữ thực tế; các luật được định nghĩa trong mã để người học có thể kiểm chứng và thay đổi.

Cây thư mục:

```text
convert-demo/
└── Demo.java
```

`Demo.java`:

```java
import java.util.Locale;
import javax.script.AbstractScriptEngine;
import javax.script.Bindings;
import javax.script.ScriptContext;
import javax.script.ScriptEngine;
import javax.script.ScriptEngineFactory;
import javax.script.ScriptException;
import javax.script.SimpleBindings;

public final class Demo {
    static final class TinyEngine extends AbstractScriptEngine {
        @Override
        public Object eval(String script, ScriptContext context)
                throws ScriptException {
            String[] parts = script.trim().split("\\s+", 2);
            if (parts.length != 2) {
                throw new ScriptException("Expected command and argument");
            }

            Object value = context.getAttribute(parts[1]);
            if (value == null && context.getAttributesScope(parts[1]) == -1) {
                throw new ScriptException("Unknown name: " + parts[1]);
            }

            return switch (parts[0]) {
                case "echo" -> value;
                case "number" -> toNumber(value);
                case "text" -> value == null ? null : String.valueOf(value);
                default -> throw new ScriptException("Unknown command: " + parts[0]);
            };
        }

        private Number toNumber(Object value) throws ScriptException {
            if (value instanceof Number n) return n;
            if (value instanceof String s) {
                try {
                    return Double.valueOf(s);
                } catch (NumberFormatException ex) {
                    throw new ScriptException("Not numeric: " + s);
                }
            }
            throw new ScriptException("Unsupported conversion");
        }

        @Override
        public Object eval(java.io.Reader reader, ScriptContext context)
                throws ScriptException {
            try {
                StringBuilder b = new StringBuilder();
                char[] buf = new char[512];
                int n;
                while ((n = reader.read(buf)) != -1) b.append(buf, 0, n);
                return eval(b.toString(), context);
            } catch (java.io.IOException ex) {
                throw new ScriptException(ex);
            }
        }

        @Override
        public Bindings createBindings() { return new SimpleBindings(); }

        @Override
        public ScriptEngineFactory getFactory() { return null; }
    }

    public static void main(String[] args) throws Exception {
        ScriptEngine engine = new TinyEngine();
        engine.put("count", Integer.valueOf(42));
        engine.put("decimal", "3.5");
        engine.put("nil", null);

        Object a = engine.eval("echo count");
        Object b = engine.eval("number decimal");
        Object c = engine.eval("text count");
        Object d = engine.eval("echo nil");

        System.out.println(a.getClass().getSimpleName() + ": " + a);
        System.out.println(b.getClass().getSimpleName() + ": " + b);
        System.out.println(c.getClass().getSimpleName() + ": " + c);
        System.out.println("nil is null: " + (d == null));

        try {
            engine.eval("echo missing");
        } catch (ScriptException ex) {
            System.out.println("missing rejected");
        }
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```bash
javac -encoding UTF-8 Demo.java
java Demo
```

Stdout chính xác:

```text
Integer: 42
Double: 3.5
String: 42
nil is null: true
missing rejected
```

**Đọc kết quả:** `echo count` giữ nguyên `Integer` đã truyền; `number decimal` dùng luật riêng của engine (`Double.valueOf`) nên chuỗi `"3.5"` trở thành `Double`; `text count` trả Java `String`; `echo nil` trả `null`; còn key `missing` không tồn tại thì báo lỗi. Đây là minh chứng JSR 223 không mặc định áp đặt các quy tắc chuyển đổi kể trên: tác giả engine đã tự viết chúng.

**Giới hạn ví dụ:** `getFactory()` trả `null` trong engine demo vì không sử dụng `ScriptEngineManager` và không xuất bản SPI provider. Một engine dùng để phân phối thực tế phải cung cấp `ScriptEngineFactory` phù hợp. Bài này chỉ nhằm khảo sát các quy tắc `Object`/`Bindings` và không nhằm mô phỏng toàn bộ JSR 223 implementation.

## 5. Giao tiếp với engine thật: kiểm tra khả năng trước khi giả định

Trong thực tế, cách viết phổ biến:

```java
ScriptEngine engine = new javax.script.ScriptEngineManager()
        .getEngineByName("some-language");
if (engine == null) {
    throw new IllegalStateException("Script engine is not installed");
}

engine.put("amount", java.math.BigDecimal.valueOf(12.50));
Object result = engine.eval("someExpression");
```

Đây là **đoạn minh họa**, không chạy độc lập: tên engine và script expression phải được thay bằng giá trị đúng cho provider thực tế. Không suy đoán rằng `BigDecimal` sẽ trở thành numeric primitive native. Với host plugin, nên kiểm tra `ScriptEngineFactory.getLanguageName()`, version, `getParameter("THREADING")` cùng tài liệu chuyển kiểu của engine.

### 5.1. Khi nào dùng Invocable?

Một số engine triển khai `javax.script.Invocable`, cho phép host gọi hàm script và chuyển các tham số Java qua cầu nối của engine:

```java
if (engine instanceof javax.script.Invocable invocable) {
    Object result = invocable.invokeFunction("calculate", 10, 20);
}
```

Đoạn này không độc lập vì hàm `calculate` phải được script định nghĩa trước; `invokeFunction` có thể ném `NoSuchMethodException` và `ScriptException`. Quy tắc ép kiểu tham số, chọn overloaded method và kiểu giá trị trả lại vẫn do engine quyết định. Không giả định mọi engine đều hỗ trợ `Invocable`.

### 5.2. Chuyển dữ liệu theo contract typed adapter

Một lớp adapter giữa Java domain và engine giúp tránh logic chuyển kiểu phân tán:

```java
static int requireInt(Object value) {
    if (!(value instanceof Number number)) {
        throw new IllegalArgumentException("Expected Number");
    }
    if (number instanceof java.math.BigInteger bi) return bi.intValueExact();
    if (number instanceof java.math.BigDecimal bd) return bd.intValueExact();
    long l = number.longValue();
    if (l < Integer.MIN_VALUE || l > Integer.MAX_VALUE
            || number.doubleValue() != l) {
        throw new IllegalArgumentException("Not an exact int");
    }
    return (int) l;
}
```

Đây là **đoạn tiện ích minh họa** để kiểm tra kiểu sau khi nhận kết quả. Với `Double.NaN`, `Infinity` và các số thực cực lớn, cách kiểm tra dựa trên `longValue()` cần xem xét thêm; hệ thống quan trọng nên đặt quy tắc chi tiết theo từng loại numeric class và kiểm tra cả `Double.isFinite(...)`. Không dùng `intValue()` âm thầm nếu dữ liệu cần chính xác.

## 6. Những rủi ro quan trọng khi chuyển kiểu

| Tình huống | Rủi ro | Cách xử lý |
|---|---|---|
| `Integer` thành `Double`/script number | Mất ý nghĩa số nguyên hoặc precision với số lớn | Quy định range, dùng decimal string/BigDecimal khi cần |
| `BigDecimal` thành floating point | Sai số tiền tệ | Dùng typed adapter, giữ decimal dạng chính xác |
| `null`/`undefined`/key missing | Đồng nhất các trạng thái khác nhau | Contract phân biệt `containsKey` và value null |
| Java `Map` thành object script | Property syntax và mutability phụ thuộc engine | Kiểm tra mapping, serialize dữ liệu đã validate |
| Date/time | Time zone và calendar semantics khác nhau | Dùng ISO-8601 với offset/instant và schema rõ ràng |
| Enum | Engine có thể dùng Java object, name hoặc ordinal | Dùng enum name và kiểm tra allowlist |
| Overloaded Java methods | Ambiguous overload resolution | Cung cấp wrapper public API không overload phức tạp |
| Class loader khác nhau | Cùng class name nhưng khác runtime identity | Dùng contract types trong loader chung |
| Script object trả về Java | Có thể là proxy/value wrapper không assignable | Adapter theo engine, kiểm tra class và lifetime |

### 6.1. Tương tác với class loader và ModuleLayer

Engine và host có thể dùng class loader khác nhau. Nếu host đưa instance của `com.example.api.Dto` vào script trong khi plugin loader có bản `Dto` khác cùng binary name, reflection/proxy/cast có thể lỗi. Dùng API JAR được định nghĩa một lần ở loader chung, tránh đóng gói trùng contract vào engine JAR.

Named modules còn chịu JPMS readability, `exports` và `opens` khi engine dùng reflection để đọc Java objects. Một public class không đồng nghĩa được engine truy cập mọi private field. Không mở toàn bộ package chỉ để chữa một lỗi chuyển kiểu; nên xây dựng DTO hoặc façade public có kiểm soát.

### 6.2. Đối tượng có mutable state và vòng đời

Truyền Java `List`, `Map` hoặc domain object vào bindings có thể trao cho script **tham chiếu thực**. Nếu script sửa đối tượng đó, host có thể nhìn thấy mutation; nếu engine copy/convert thì có thể không. Cần thử nghiệm copy-vs-reference semantics và giới hạn quyền ghi.

Script engine không nhất thiết thread-safe. Không chia sẻ một engine instance giữa các request nếu provider không cam kết mô hình đồng thời; cần quản lý bindings riêng cho mỗi lượt chạy, dữ liệu không mutable hoặc instance-per-task tùy workload.

## 7. Chiến lược thiết kế cầu nối kiểu an toàn

1. **Định nghĩa schema dữ liệu** giữa Java và script (kiểu, nullability, giới hạn số, encoding, nested objects).
2. **Chuẩn hóa đầu vào** thành DTO hoặc primitive/collection có thể kiểm chứng; không truyền trực tiếp service object có quyền cao.
3. **Chọn engine và version cụ thể**, kiểm tra tài liệu mapping và đánh dấu version trong kết quả nếu có thay đổi.
4. **Thực hiện adapter một chiều** `Java→script` và `script→Java`, không rải ép kiểu tùy tiện trong business code.
5. **Xử lý lỗi chuyển đổi** bằng exception có ngữ nghĩa, không tự ý làm tròn, cắt số hoặc stringify giá trị lạ.
6. **Kiểm thử boundary** gồm số rất lớn, số thập phân, `NaN`, `Infinity`, Unicode, null/missing, collections lồng nhau và cyclic object.
7. **Giới hạn script không tin cậy** bằng cách không phơi bày host objects nhạy cảm; dùng isolation ở process/OS khi cần.

## 8. Checklist kiểm thử theo từng engine

- [ ] Engine được tìm thấy bằng `ScriptEngineManager`/class loader đúng và phiên bản được ghi nhận.
- [ ] Có test round-trip cho `String`, `Boolean`, `Integer`, `Long`, `Double`, `BigDecimal` nếu contract hỗ trợ.
- [ ] Kiểm tra đầy đủ null, missing key, giá trị không hợp lệ và lỗi cast.
- [ ] `List`/`Map` được xác minh là copy hay reference, có mutability rõ ràng.
- [ ] Host không suy đoán `Object` trả về luôn là một class Java cụ thể.
- [ ] Module exports/opens và class identity đúng khi engine gọi Java API.
- [ ] Không có shared mutable bindings bất ngờ giữa các script executions.
- [ ] Script không có quyền truy cập những host objects không cần thiết.

**Kết luận:** Java Scripting API cung cấp cơ chế trao đổi đối tượng Java với engine chứ không định nghĩa một bảng ép kiểu chung cho mọi ngôn ngữ. Mọi chuyển đổi Java↔script cần được xem là **hợp đồng riêng của engine và phiên bản engine**. Hãy chuẩn hóa dữ liệu tại boundary, kiểm tra kiểu thực tế khi nhận kết quả, xử lý null/precision rõ ràng và kiểm thử bằng engine thật trước khi phát hành plugin.

# 17.3 `eval` từ `String` hoặc `Reader` và xử lý `ScriptException`

Trong Java, JSR 223 (Scripting API) cung cấp giao diện `javax.script.ScriptEngine` để chạy mã nguồn **của một ngôn ngữ kịch bản được engine hỗ trợ**. Hai cách truyền source thường gặp là `engine.eval(String)` và `engine.eval(Reader)`: cách thứ nhất nhận văn bản đã nằm trong bộ nhớ Java; cách thứ hai nhận nguồn ký tự thông qua `java.io.Reader`, chẳng hạn `StringReader` hoặc `Files.newBufferedReader(path, UTF_8)`. Cả hai đều trả kết quả kiểu Java `Object`, và đều có thể ném **`ScriptException`**, một checked exception của Scripting API.

Bài học này tập trung vào **cách sử dụng các overload `eval` đúng đắn, quản lý nguồn đầu vào và xử lý lỗi script**. Nó cũng giải thích vì sao trên Java 17+ không được mặc định có một JavaScript engine: **Nashorn đã bị loại khỏi JDK từ Java 15 (JEP 372)**. Các lớp `ScriptEngine`, `ScriptEngineManager` và `ScriptException` vẫn nằm trong module chuẩn `java.scripting`, nhưng việc thực thi một ngôn ngữ cụ thể phụ thuộc **engine provider thực sự có mặt**.

Những điều sẽ nắm được sau bài:

- Phân biệt sáu overload `eval` theo `String`/`Reader` và `Bindings`/`ScriptContext`.
- Hiểu nguồn script là **ngôn ngữ của engine** (JavaScript, Groovy, DSL...), không phải Java source tự động được `eval` biên dịch.
- Xử lý engine lookup trả `null`, đặc biệt khi chuyển từ JDK 8 sang JDK 17+.
- Sử dụng `StringReader` hoặc reader của tệp UTF-8, và đóng reader ở đúng boundary.
- Quản lý state qua `ENGINE_SCOPE`, `GLOBAL_SCOPE` và per-call `Bindings`.
- Bắt `ScriptException`; đọc `getMessage()`, `getFileName()`, `getLineNumber()`, `getColumnNumber()` và `getCause()` an toàn.
- Phân biệt lỗi cú pháp/đánh giá script với lỗi đọc file (`IOException`), lỗi configuration và lỗi Java unchecked.
- Thực hành bằng **một ScriptEngine tối giản chạy được trên Java 17+** mà không cài thêm thư viện, một demo engine discovery và một demo metadata của `ScriptException`.
- Tránh những sai lầm về trust boundary, isolation, thread safety và giả định kết quả `eval` luôn có kiểu nhất định.

## 1. Bức tranh chung của `javax.script`

Một luồng sử dụng thông thường:

```text
                   Java application
                         |
                         v
                  ScriptEngineManager
                         |
             find provider by name
                         |
           +-------------+-------------+
           |                           |
       engine found                engine == null
           |                           |
           v                           v
    ScriptEngine instance        report missing provider
           |
           +-- eval(String source)
           |
           +-- eval(Reader source)
           |
           +-- eval(..., Bindings)
           |
           +-- eval(..., ScriptContext)
           |
           +-- result: Object (may be null)
           |
           +-- failure: ScriptException (or other runtime errors)
```

Các lớp tiêu biểu:

| API | Vai trò |
| --- | --- |
| `ScriptEngineManager` | Phát hiện các `ScriptEngineFactory` provider qua service mechanism, tìm engine theo tên/ngôn ngữ/extension/MIME |
| `ScriptEngine` | Hợp đồng thực thi script, thao tác bindings, context và trả kết quả |
| `ScriptEngineFactory` | Metadata của engine/language và factory tạo `ScriptEngine` |
| `ScriptContext` | Chứa `Bindings` theo scope và readers/writers được engine sử dụng |
| `Bindings` | Map của các tên/giá trị Java được cấp cho script ở một scope |
| `SimpleBindings` | Triển khai `Bindings` đơn giản |
| `SimpleScriptContext` | Triển khai `ScriptContext` với scope và I/O streams |
| `AbstractScriptEngine` | Lớp cơ sở giúp người viết engine triển khai nhiều overload `eval` |
| `ScriptException` | Checked exception chung để báo lỗi xảy ra khi thực thi/diễn giải script |

Khi chương trình chạy trên **classpath**, module `java.scripting` của Java 17 được dùng khi cần. Nếu ứng dụng của bạn được biên dịch dưới dạng **named module**, cần khai báo dependency:

```java
module my.application {
    requires java.scripting;
}
```

Đây là **đoạn `module-info.java` minh họa**, không phải một chương trình độc lập.

### 1.1. Quan trọng trên Java 17+: không có JavaScript engine mặc định

Trong JDK 8 từng có Nashorn JavaScript engine. Nashorn bị deprecated ở Java 11 và được **loại bỏ khỏi JDK 15**. Vì vậy, trên một JDK 17 thuần, đoạn:

```java
ScriptEngine engine = new ScriptEngineManager()
        .getEngineByName("JavaScript");
```

có thể trả về `null`. Nếu ngay sau đó gọi `engine.eval(...)`, lỗi sẽ là **`NullPointerException`**, chưa hề có script nào được chạy. Java vẫn có Scripting API, nhưng **không cam kết cung cấp một engine cho ngôn ngữ tên "JavaScript"**.

Chỉ khi bạn đã thêm một provider tương thích (qua dependencies/module path/classpath và service registration thích hợp), `getEngineByName(...)` mới có thể tìm thấy nó. Tên engine, phiên bản ngôn ngữ và hành vi evaluate phụ thuộc provider thực tế.

**Tách bạch hai bước:** tìm/khởi tạo engine là **discovery/configuration**; `eval` là **execution**. Đừng gộp lỗi `engine == null` thành `ScriptException`.

## 2. Sáu overload `eval` và ngữ cảnh sử dụng

Giao diện `ScriptEngine` có các overload chính:

| Overload | Nguồn source | Context/bindings dùng để evaluate |
| --- | --- | --- |
| `eval(String script)` | Chuỗi Java chứa script source | **Default `ScriptContext`** của engine |
| `eval(Reader reader)` | Nguồn ký tự cung cấp script | Default `ScriptContext` |
| `eval(String script, Bindings bindings)` | Chuỗi script | Dùng `bindings` làm **`ENGINE_SCOPE`** cho lần gọi |
| `eval(Reader reader, Bindings bindings)` | Reader script | Dùng `bindings` làm `ENGINE_SCOPE` cho lần gọi |
| `eval(String script, ScriptContext context)` | Chuỗi script | Dùng `ScriptContext` được truyền riêng |
| `eval(Reader reader, ScriptContext context)` | Reader script | Dùng `ScriptContext` được truyền riêng |

Một mẫu code sử dụng từ phía application:

```java
// Đoạn minh họa: engine là ScriptEngine đã được tìm thấy.
Object a = engine.eval("add 2 3");

try (Reader source = new StringReader("add 4 5")) {
    Object b = engine.eval(source);
}

Bindings oneCall = engine.createBindings();
oneCall.put("x", 10);
Object c = engine.eval("get x", oneCall);
```

**Cần lưu ý:** `"add 2 3"` và `"get x"` là cú pháp của **MiniCalc toy engine trong ví dụ đầy đủ phía dưới**, không phải JavaScript hay cú pháp JSR 223 chuẩn. Khi dùng JavaScript provider thật, phải viết script hợp lệ theo ngôn ngữ/provider đó, ví dụ biểu thức `1 + 2`, subject to semantics của engine tương ứng.

### 2.1. `eval(String)` không có nghĩa chạy Java source

`String script = "System.out.println(1)";` là một chuỗi Java. `eval(script)` sẽ gửi **nội dung chuỗi ấy** cho interpreter/compiler của scripting engine đã chọn. Nếu engine hiểu một DSL với command `add` thì Java source có thể bị báo syntax error. Nếu engine là JavaScript, cú pháp và hệ kiểu được định nghĩa theo engine JavaScript đó, không phải theo compiler `javac`.

JSR 223 là **giao diện Java tới scripting languages**, không phải `javac` động; cũng không phải một API để Java tự hiểu mọi ngôn ngữ kịch bản.

### 2.2. `eval(Reader)` không đồng nghĩa “đọc từng dòng rồi gọi eval(String)”

`Reader` cung cấp luồng ký tự. **Cách engine parse/evaluate source** phụ thuộc implementation: một provider có thể đọc hết rồi parse; provider khác có thể thực thi incremental; một engine có thể hỗ trợ nhiều statements, engine khác chỉ một expression.

Trong demo MiniCalc, ta **cố tình** định nghĩa semantics: đọc từng dòng, xử lý câu lệnh `add`/`get`, rồi trả **kết quả của dòng không trống cuối cùng**. Đây là hợp đồng do toy engine tự đặt, không phải điều bắt buộc cho mọi `ScriptEngine`.

Không suy ra rằng `Reader` luôn tiết kiệm bộ nhớ hơn `String` trên mọi engine: dù Java caller không tự giữ toàn bộ source trong một String, engine vẫn có thể đọc vào memory khi parse. Để đánh giá streaming/memory, xem tài liệu của provider thực tế.

## 3. Khi nào chọn `String`, khi nào chọn `Reader`?

### Chọn `eval(String)` khi

- Script nhỏ/đang nằm sẵn trong biến Java hay config đã được đọc thành chuỗi.
- Cần tạo nội dung script từ template có kiểm soát, sau khi validate input.
- Muốn test nhanh một expression hoặc một đoạn DSL ngắn.
- Thích kiểm soát source và có thể log một identifier/hash thay vì log toàn bộ mã.

Ví dụ minh họa:

```java
String source = "add 8 13";
Object result = engine.eval(source);
```

Lưu ý: đây là script ngôn ngữ **MiniCalc** của bài, không phải JavaScript.

### Chọn `eval(Reader)` khi

- Script nằm trong file, stream hoặc StringReader có sẵn.
- Muốn đọc từ tệp với charset **được chỉ định rõ**.
- Muốn truyền source dưới dạng Reader theo API của caller, không buộc caller gọi `Files.readString` trước.
- Có thể quản lý resource ở boundary bằng `try-with-resources`.

Ví dụ:

```java
Path path = Path.of("rules.calc");
try (Reader reader = Files.newBufferedReader(
        path, StandardCharsets.UTF_8)) {
    Object result = engine.eval(reader);
    System.out.println(result);
}
```

Đây là **đoạn minh họa** cần các imports `java.nio.file.*`, `java.nio.charset.StandardCharsets`, `java.io.Reader` và xử lý `IOException`, `ScriptException`; nó chỉ chạy khi file và engine phù hợp tồn tại.

**Quy tắc quan trọng về Reader:** đối tượng Reader được cung cấp từ phía caller nên code caller chủ động đóng bằng `try-with-resources`. Đừng mặc định mọi engine sẽ tự đóng Reader giúp bạn, và cũng đừng dùng lại Reader đã bị tiêu thụ nếu nó không hỗ trợ reset. Ví dụ MiniCalc trong bài cố ý **không** đóng Reader do caller cung cấp.

### 3.1. Charset thuộc tầng tạo Reader

`Reader` đã là luồng **characters**, không phải bytes. Khi bạn tạo `Reader` từ file, phải chọn charset ở bước chuyển bytes → chars:

```java
Reader reader = Files.newBufferedReader(path, StandardCharsets.UTF_8);
```

Lời gọi `engine.eval(reader)` **không nhận charset**. Nếu file UTF-8 bị đọc bằng charset sai, một số ký tự có thể biến thành text lỗi, khiến engine báo syntax/identifier issues rất khó tìm.

Trong code dùng file thật, nên chỉ định UTF-8 (hoặc charset đã được quy ước), tránh `new FileReader(path)` không xét encoding cụ thể nếu portability quan trọng.

### 3.2. Tên file trong `ScriptException` không tự động lấy từ Reader

Một `Reader` không có hợp đồng chung chứa tên file. `Files.newBufferedReader(path)` cung cấp characters; engine không nhất thiết biết biến `path` của application. Nếu engine hỗ trợ metadata filename, có thể đặt:

```java
engine.put(ScriptEngine.FILENAME, "rules.calc");
```

Hằng `ScriptEngine.FILENAME` là tên một thuộc tính chuẩn, nhưng **việc dùng thuộc tính để điền `ScriptException` tùy implementation**. Đừng khẳng định mọi engine sẽ tự báo đúng filename từ `FILENAME`, vì JSR 223 không buộc mọi parser phải cung cấp line/column chính xác. MiniCalc bên dưới cố tình đọc FILENAME và gắn vào exception để minh họa.

## 4. Giá trị trả về: `Object` có thể là `null`

Các overload `eval` đều trả `Object`. Kết quả thực tế phụ thuộc **ngôn ngữ và engine**:

- Numeric result có thể được engine ánh xạ thành `Integer`, `Long`, `Double`, `BigDecimal` hoặc wrapper/class khác.
- Script có thể trả `String`, `Boolean`, list/map, đối tượng engine-specific hoặc một Java proxy.
- Script không có giá trị cuối rõ ràng có thể trả `null`.
- Một lookup biến không tồn tại cũng có thể trả `null`, phụ thuộc DSL/provider (hoặc ném `ScriptException` nếu ngôn ngữ quy định lỗi undefined variable).

Không ép kiểu mù quáng:

```java
// Đoạn minh họa dùng khi engine trả một Number:
Object result = engine.eval("add 2 5");
if (result instanceof Number number) {
    int value = number.intValue();
    System.out.println(value);
} else {
    throw new IllegalStateException("Script did not return a number");
}
```

Khi kết quả là `null`, `(String) null` không ném exception nhưng thao tác gọi instance method trên nó có thể gây `NullPointerException`. Cần phân biệt **script trả null hợp lệ** với **engine bị thiếu (reference null)**.

### 4.1. Đừng cộng dồn trạng thái ngoài ý muốn

Cùng một `ScriptEngine` có thể giữ bindings hoặc state qua các lời gọi. Nếu gọi:

```java
engine.put("base", 10);
Object first = engine.eval("get base");
Object second = engine.eval("get base");
```

cùng default `ENGINE_SCOPE` sẽ sẵn sàng cho cả hai lần gọi của **MiniCalc**. Với provider thực tế, script có thể tạo biến, sửa global object hoặc giữ state engine-specific. Đừng giả định `eval(String)` luôn là pure function.

## 5. `Bindings`, `ScriptContext` và scope

`Bindings` là key/value map. Với `ScriptContext`, hai scope chuẩn:

1. `ScriptContext.ENGINE_SCOPE` — bindings riêng của engine/context đang dùng cho execution. `engine.put(key,value)` thường cập nhật ENGINE_SCOPE của default context.
2. `ScriptContext.GLOBAL_SCOPE` — tập bindings chia sẻ nếu được cấu hình, ví dụ từ `ScriptEngineManager`. Khi resolution theo context, ENGINE_SCOPE thường có ưu tiên trước GLOBAL_SCOPE.

Chọn overload để tránh thay đổi state ngoài ý muốn:

```java
// Mã minh họa với MiniCalc:
engine.put("base", 10);
System.out.println(engine.eval("get base"));  // 10

Bindings once = engine.createBindings();
once.put("base", 77);
System.out.println(engine.eval("get base", once)); // 77
System.out.println(engine.eval("get base"));       // 10
```

Giá trị `base=77` chỉ được dùng làm ENGINE_SCOPE cho **lần eval có tham số Bindings** trong implementation theo contract của `AbstractScriptEngine`. Nó không tự thay thế default ENGINE_SCOPE của engine.

**Giới hạn:** per-call `Bindings` giúp kiểm soát một phần variables nhưng **không** phải process sandbox, và không bảo đảm mọi implementation tuyệt đối không có side effects/state riêng. Một script có thể thao tác object Java được cấp, gọi API được phép hoặc tác động nơi khác nếu provider/permissions cho phép.

### 5.1. `ScriptContext` khi cần nhiều thông tin hơn

Đôi khi bạn cần truyền ENGINE_SCOPE, GLOBAL_SCOPE, filename metadata, error writer hoặc standard writer cho một request cụ thể:

```java
SimpleScriptContext ctx = new SimpleScriptContext();
Bindings bindings = new SimpleBindings();
bindings.put("base", 99);
ctx.setBindings(bindings, ScriptContext.ENGINE_SCOPE);
ctx.setAttribute(ScriptEngine.FILENAME, "request-42.calc",
        ScriptContext.ENGINE_SCOPE);
Object result = engine.eval("get base", ctx);
```

Đây là **đoạn minh họa** với imports từ `javax.script`; MiniCalc hiểu `get base`, provider khác cần script hợp lệ theo ngôn ngữ của nó.

Nếu dùng `engine.eval(script,ctx)`, custom context đó áp dụng **cho lần gọi ấy**. Không nhầm với `engine.setContext(ctx)`, thao tác thay default context của engine và có thể ảnh hưởng những lần gọi tiếp theo.

### 5.2. Scope không thay thế kiểm tra quyền

Có một biến tên `role` trong Bindings không đảm bảo script chỉ có các quyền của role đó. Nếu cung cấp một Java object chứa khả năng đọc file/network/database cho script không đáng tin, script có thể dùng capability ấy tùy engine. Cần thiết kế trust boundary riêng.

## 6. `ScriptException` là gì?

`javax.script.ScriptException` là checked exception được dùng bởi Scripting API khi lỗi xảy ra lúc diễn giải/evaluate script. Nó extends `Exception`, do đó code gọi `eval` phải:

- `try/catch (ScriptException e)`, hoặc
- khai báo `throws ScriptException` (hay supertype thích hợp) và truyền lên caller.

Thông tin chẩn đoán sẵn có:

| Method | Ý nghĩa | Khi không có thông tin |
| --- | --- | --- |
| `getMessage()` | Mô tả lỗi, có thể đã gồm filename/line/column | Trả text của exception, engine-dependent |
| `getFileName()` | Tên nguồn script liên quan tới lỗi | Có thể trả `null` |
| `getLineNumber()` | Dòng xảy ra lỗi | `-1` nếu không xác định |
| `getColumnNumber()` | Cột xảy ra lỗi | `-1` nếu không xác định |
| `getCause()` | Exception nguyên nhân bên dưới nếu có | Có thể trả `null` |

Ví dụ xử lý an toàn:

```java
try {
    Object result = engine.eval(source);
    useResult(result);
} catch (ScriptException e) {
    String file = e.getFileName() != null
            ? e.getFileName() : "<unknown-source>";
    String line = e.getLineNumber() >= 0
            ? Integer.toString(e.getLineNumber()) : "?";
    String column = e.getColumnNumber() >= 0
            ? Integer.toString(e.getColumnNumber()) : "?";

    System.err.println(file + ":" + line + ":" + column);
    System.err.println(e.getMessage());

    Throwable cause = e.getCause();
    if (cause != null) {
        System.err.println("Cause: " + cause.getClass().getName());
    }
}
```

Đây là **đoạn minh họa**, cần có `engine`, `source`, method `useResult` và imports tương ứng; không phải chương trình độc lập.

### 6.1. Không tự động coi mọi lỗi đều là `ScriptException`

`ScriptException` là ngoại lệ chuẩn của API cho lỗi script và những checked exceptions mà engine triển khai cần bọc. Nhưng các lỗi khác vẫn có thể xuất hiện:

- `engine == null` rồi gọi `eval` → `NullPointerException` do **chưa tìm thấy provider**.
- `Files.newBufferedReader(...)` có thể ném `IOException` **trước** khi gọi `eval` do file không tồn tại hoặc thiếu quyền đọc.
- Java code dùng một result sai kiểu → `ClassCastException` **ở caller**, không phải script parse error.
- Engine hoặc các Java objects được script gọi có thể ném unchecked exceptions/errors theo đặc điểm provider và trust boundary.
- `ScriptException` có thể bọc `IOException` do Reader lỗi **trong lúc engine đọc** source, hoặc bọc checked parser/interpreter exception khác.

Nếu muốn phân loại lỗi cho user/API, hãy tách **file I/O**, **engine discovery**, **script execution** và **post-processing** thay vì bắt một `Exception` chung rồi trả `"syntax error"`.

### 6.2. `getMessage()` có thể đã kèm vị trí

Constructor `new ScriptException(message,filename,line,column)` có thể tạo text chứa cả tên file và tọa độ. Nếu log `getMessage()` rồi lại ghép vị trí nguyên văn, log có thể lặp thông tin. Điều này không nghiêm trọng, nhưng cần biết để thiết kế structured error response.

Đối với diagnostics có cấu trúc, ưu tiên các getters riêng và truyền cause chain cho logger. Đừng parse `getMessage()` để lấy line/column nếu getters đã có.

## 7. Chương trình Java 17+ chạy độc lập: một ScriptEngine dạy học

Để có ví dụ **tái lập được mà không cần cài JavaScript provider**, chúng ta tạo một engine rất nhỏ dựa trên `AbstractScriptEngine`. Nó hiểu đúng **hai lệnh của một DSL tự định nghĩa**:

- `add A B`: đọc hai số nguyên, cộng và trả một `Integer`.
- `get key`: đọc biến từ `ScriptContext` và trả object hoặc `null`.

Engine đọc từng dòng; kết quả của lần `eval` là kết quả của **dòng không trống cuối cùng**. Nếu token không phải số, nó tạo `ScriptException` với filename/line/column và gắn `NumberFormatException` làm cause. Nếu nguồn `Reader` ném `IOException` trong khi đọc, engine bọc vào `ScriptException`.

**Cảnh báo về phạm vi:** `MiniCalc` **không phải JavaScript**, không phải provider chuẩn có sẵn trong JDK, và ví dụ chỉ tạo engine **trực tiếp bằng `new MiniCalcEngine()`**. `MiniCalcFactory` ở đây giúp class minh họa đầy đủ `getFactory()`; nó **không tự đăng ký** vào `ScriptEngineManager` qua service descriptor. Không dùng ngôn ngữ toy này như production parser hoặc security sandbox.

### 7.1. File `ScriptEvalDemo.java`

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.Reader;
import java.io.StringReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import javax.script.AbstractScriptEngine;
import javax.script.Bindings;
import javax.script.ScriptContext;
import javax.script.ScriptEngine;
import javax.script.ScriptEngineFactory;
import javax.script.ScriptException;
import javax.script.SimpleBindings;

public class ScriptEvalDemo {
    public static void main(String[] args) throws Exception {
        ScriptEngine engine = new MiniCalcEngine();
        engine.put(ScriptEngine.FILENAME, "rules.calc");
        engine.put("base", 10);

        System.out.println("String: " + engine.eval("add 2 5"));
        System.out.println("Reader: " + engine.eval(
                new StringReader("add 1 2\nadd 6 4\n")));
        System.out.println("binding: " + engine.eval("get base"));
        System.out.println("missing: " + engine.eval("get missing"));

        Bindings oneCall = new SimpleBindings(Map.of("base", 77));
        System.out.println("one-call binding: " + engine.eval("get base", oneCall));
        System.out.println("default binding: " + engine.eval("get base"));

        try {
            engine.eval(new StringReader("add 1 2\nadd 4 nope\n"));
        } catch (ScriptException e) {
            System.out.println("script failure: "
                    + e.getFileName() + ":" + e.getLineNumber()
                    + ":" + e.getColumnNumber());
            System.out.println("script cause: "
                    + e.getCause().getClass().getSimpleName());
        }

        Path temporary = Files.createTempFile("minicalc-", ".calc");
        try {
            Files.writeString(temporary, "add 10 20\n", StandardCharsets.UTF_8);
            try (Reader fileReader =
                    Files.newBufferedReader(temporary, StandardCharsets.UTF_8)) {
                System.out.println("UTF-8 file: " + engine.eval(fileReader));
            }
        } finally {
            Files.deleteIfExists(temporary);
        }

        Reader broken = new Reader() {
            @Override
            public int read(char[] buffer, int offset, int length)
                    throws IOException {
                throw new IOException("read failed");
            }
            @Override
            public void close() {}
        };

        try (broken) {
            engine.eval(broken);
        } catch (ScriptException e) {
            System.out.println("Reader I/O cause: "
                    + e.getCause().getClass().getSimpleName());
        }

        System.out.println("factory: " + engine.getFactory().getEngineName());
    }

    // A deliberately tiny teaching language: "add a b" or "get key".
    // This is NOT JavaScript and is NOT registered as a JSR-223 provider.
    static final class MiniCalcEngine extends AbstractScriptEngine {
        private final ScriptEngineFactory factory = new MiniCalcFactory();

        @Override
        public Object eval(String source, ScriptContext context)
                throws ScriptException {
            Objects.requireNonNull(source, "source");
            return eval(new StringReader(source), context);
        }

        @Override
        public Object eval(Reader input, ScriptContext context)
                throws ScriptException {
            Objects.requireNonNull(input, "input");
            Objects.requireNonNull(context, "context");
            BufferedReader reader = new BufferedReader(input);
            Object result = null;
            int number = 0;

            try {
                String line;
                while ((line = reader.readLine()) != null) {
                    number++;
                    if (!line.isBlank()) {
                        result = execute(line, number, context);
                    }
                }
            } catch (IOException error) {
                throw new ScriptException(error);
            }
            return result;
        }

        private Object execute(String line, int number, ScriptContext context)
                throws ScriptException {
            String[] words = line.trim().split("\\s+");
            if (words.length == 2 && words[0].equals("get")) {
                return context.getAttribute(words[1]);
            }
            if (words.length == 3 && words[0].equals("add")) {
                try {
                    return Integer.parseInt(words[1])
                            + Integer.parseInt(words[2]);
                } catch (NumberFormatException error) {
                    int column = line.indexOf(words[2]) + 1;
                    ScriptException wrapped = failure(
                            "not an integer: " + words[2], context, number, column);
                    wrapped.initCause(error);
                    throw wrapped;
                }
            }
            throw failure("unknown command or wrong arity", context, number, 1);
        }

        private ScriptException failure(String message, ScriptContext context,
                int line, int column) {
            Object name = context.getAttribute(ScriptEngine.FILENAME);
            String filename = name == null ? "<eval>" : name.toString();
            return new ScriptException(message, filename, line, column);
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

    static final class MiniCalcFactory implements ScriptEngineFactory {
        @Override public String getEngineName() { return "MiniCalc"; }
        @Override public String getEngineVersion() { return "1.0"; }
        @Override public List<String> getExtensions() { return List.of("calc"); }
        @Override public List<String> getMimeTypes() {
            return List.of("text/x-minicalc");
        }
        @Override public List<String> getNames() { return List.of("minicalc"); }
        @Override public String getLanguageName() { return "MiniCalc"; }
        @Override public String getLanguageVersion() { return "1.0"; }
        @Override public Object getParameter(String key) {
            return switch (key) {
                case ScriptEngine.NAME -> "minicalc";
                case ScriptEngine.ENGINE -> getEngineName();
                case ScriptEngine.ENGINE_VERSION -> getEngineVersion();
                case ScriptEngine.LANGUAGE -> getLanguageName();
                case ScriptEngine.LANGUAGE_VERSION -> getLanguageVersion();
                default -> null;
            };
        }
        @Override public String getMethodCallSyntax(
                String object, String method, String... args) {
            return null; // Not supported by this two-command language.
        }
        @Override public String getOutputStatement(String value) {
            return null; // No print statement in MiniCalc.
        }
        @Override public String getProgram(String... statements) {
            return String.join("\n", statements);
        }
        @Override public ScriptEngine getScriptEngine() {
            return new MiniCalcEngine();
        }
    }
}
```

### 7.2. Lệnh biên dịch và chạy

Tạo file đúng tên `ScriptEvalDemo.java`, chạy:

```bash
javac --release 17 ScriptEvalDemo.java
java ScriptEvalDemo
```

Chương trình không phụ thuộc Nashorn, GraalJS, Groovy hay bất kỳ library bên ngoài nào; nó chỉ sử dụng **JDK 17+**.

**Stdout đã được kiểm chứng bằng biên dịch và chạy thực tế:**

```text
String: 7
Reader: 10
binding: 10
missing: null
one-call binding: 77
default binding: 10
script failure: rules.calc:2:7
script cause: NumberFormatException
UTF-8 file: 30
Reader I/O cause: IOException
factory: MiniCalc
```

### 7.3. Vì sao kết quả `String` là 7 và `Reader` là 10?

- `engine.eval("add 2 5")` gọi overload String, rồi `MiniCalcEngine.eval(String, ScriptContext)` chuyển chuỗi thành `StringReader`.
- `MiniCalcEngine.eval(Reader, ScriptContext)` đọc các dòng bằng `BufferedReader.readLine()` và giải mã DSL.
- `"add 2 5"` trả `Integer 7`.
- Reader chứa hai dòng: `"add 1 2"` trả 3 trước, `"add 6 4"` trả 10 sau; engine chủ động lưu **kết quả dòng cuối**, nên toàn bộ `eval(Reader)` trả 10.

**Đừng suy rộng** kết quả dòng cuối sang JavaScript hay mọi JSR 223 provider. Đây là semantics được viết rõ ở `MiniCalcEngine`.

### 7.4. `Bindings` theo engine và theo một lần gọi

`engine.put("base",10)` ghi một giá trị vào default ENGINE_SCOPE. `eval("get base")` dùng default context, trả 10. `SimpleBindings(Map.of("base",77))` được cấp vào `eval("get base",oneCall)` nên lần đó trả 77. Lần tiếp theo dùng default context lại đọc 10.

`eval("get missing")` gọi `ScriptContext.getAttribute("missing")`, và implementation trong demo trả `null` vì không có key. Điều đó **không** chứng minh mọi scripting language đều cho phép truy cập identifier chưa định nghĩa mà không lỗi.

### 7.5. Vị trí và cause của `ScriptException`

Lời gọi:

```java
engine.eval(new StringReader("add 1 2\nadd 4 nope\n"));
```

có lỗi ở **dòng 2**. Trong `"add 4 nope"`, token `nope` bắt đầu ở **cột 7** (đếm từ 1). Toy parser cố ý tạo:

```java
new ScriptException("not an integer: nope", "rules.calc", 2, 7);
```

sau đó dùng `initCause(numberFormatException)`. Vì `engine.put(ScriptEngine.FILENAME,"rules.calc")` đã đặt metadata vào context, output có `rules.calc:2:7`; cause là `NumberFormatException`.

**Giới hạn của parser demo:** đoạn tính column bằng `line.indexOf(words[2])+1` chỉ đủ cho các lệnh ngắn trong ví dụ; một production parser phải theo dõi token offsets chính xác, kể cả khi token xuất hiện lặp lại, có whitespace phức tạp hoặc các Unicode code points. Demo nhằm giải thích JSR 223 exception API, không phải xây lexer/parser hoàn chỉnh.

### 7.6. Tại sao I/O failure được bọc thành `ScriptException`?

`Reader broken` cố ý ném `IOException("read failed")` khi engine gọi `BufferedReader.readLine()`. Code của `MiniCalcEngine` bắt `IOException` và ném `new ScriptException(error)`. Vì vậy caller của `engine.eval(broken)` bắt được `ScriptException`, và `getCause()` là `IOException`.

Điều này khác `Files.newBufferedReader(...)` ném `IOException` ngay khi **mở file** ở phía application. Hai lỗi có thể khác chỗ catch:

```text
Files.newBufferedReader(path)
    |
    +-- IOException khi mở file    --> catch IOException ở caller
    |
    +-- Reader đã mở
            |
            v
       engine.eval(reader)
            |
            +-- checked read/parse failures theo implementation
            |      --> có thể bọc trong ScriptException
            |
            +-- script result Object
```

Nếu engine thực tế có cách xử lý IOException khác, dùng tài liệu/provider và cause chain để phân loại. JSR 223 mong đợi các engine bọc checked exceptions từ interpreter vào `ScriptException`, nhưng code application vẫn cần xử lý các lỗi ngoài giai đoạn eval riêng.

### 7.7. Ai đóng Reader?

`MiniCalcEngine.eval(Reader,ScriptContext)` tạo `BufferedReader` bao quanh `Reader` đầu vào nhưng **không** gọi `close()`, vì ownership của nguồn nằm ở caller. Với nguồn file, caller dùng:

```java
try (Reader fileReader =
        Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    engine.eval(fileReader);
}
```

Reader được đóng kể cả khi eval ném `ScriptException`. Một `StringReader` có thể không cần quan tâm external resource, nhưng dùng `try-with-resources` vẫn làm rõ cách quản lý khi thay bằng FileReader/stream reader.

Không đóng Reader trước khi gọi eval, và không tái sử dụng Reader đã tới EOF rồi kỳ vọng engine tự đọc lại source. Muốn chạy lại, **tạo Reader mới** hoặc dùng String source còn lưu được.

## 8. Ví dụ độc lập 2 — phát hiện JavaScript provider một cách an toàn

Đây là chương trình thật, chỉ dùng JDK. Nó không yêu cầu JavaScript engine để **biên dịch hoặc khởi động**. Nếu provider không có, báo thiếu và dừng có chủ đích thay vì ném `NullPointerException`.

Tạo file **`ScriptEngineDiscoveryDemo.java`**:

```java
import java.io.Reader;
import java.io.StringReader;
import javax.script.ScriptEngine;
import javax.script.ScriptEngineManager;
import javax.script.ScriptException;

public class ScriptEngineDiscoveryDemo {
    public static void main(String[] args) throws Exception {
        ScriptEngineManager manager = new ScriptEngineManager();
        ScriptEngine engine = manager.getEngineByName("JavaScript");

        if (engine == null) {
            System.out.println("JavaScript engine: not installed");
            System.out.println("Install and register a compatible JSR-223 provider.");
            return;
        }

        System.out.println("engine name: "
                + engine.getFactory().getEngineName());
        try {
            Object fromString = engine.eval("1 + 2");
            System.out.println("String result: " + fromString);
            try (Reader source = new StringReader("2 + 3")) {
                Object fromReader = engine.eval(source);
                System.out.println("Reader result: " + fromReader);
            }
        } catch (ScriptException error) {
            System.err.println("Script error: " + error.getMessage());
        }
    }
}
```

Biên dịch/chạy:

```bash
javac --release 17 ScriptEngineDiscoveryDemo.java
java ScriptEngineDiscoveryDemo
```

**Output đã quan sát trong môi trường JDK kiểm thử không cài JavaScript provider:**

```text
JavaScript engine: not installed
Install and register a compatible JSR-223 provider.
```

Nếu môi trường **có provider tương thích**, chương trình vào nhánh khác: in tên engine, chạy `1 + 2` từ String, rồi `2 + 3` từ StringReader. **Kết quả/kiểu số và tên engine cụ thể phụ thuộc provider**, nên không áp một stdout cố định cho tất cả engines. Chương trình cũng bắt `ScriptException` từ việc thực thi, thay vì giả định biểu thức luôn hợp lệ trên bất kỳ engine mang tên JavaScript.

### 8.1. Vì sao dùng `getEngineByName` có thể trả `null`?

`ScriptEngineManager` dùng các `ScriptEngineFactory` được phát hiện qua service-provider mechanism. Khi không có factory nào quảng bá tên yêu cầu hoặc provider chưa được load đúng, `getEngineByName(...)` trả `null`. Điều đó khác với một engine có mặt nhưng script bị syntax error.

Để debug discovery, có thể in danh sách các factories:

```java
ScriptEngineManager manager = new ScriptEngineManager();
for (ScriptEngineFactory factory : manager.getEngineFactories()) {
    System.out.println(factory.getEngineName()
            + ": " + factory.getNames());
}
```

Đây là đoạn minh họa với imports `ScriptEngineManager` và `ScriptEngineFactory`; danh sách **phụ thuộc môi trường và dependencies**. Không coi JDK 17 buộc phải có một factory duy nhất hay một tên provider nhất định.

### 8.2. Cài engine khác và điều kiện tương thích

JSR 223 không định nghĩa một JavaScript interpreter chuẩn đi kèm mọi JDK. Nếu ứng dụng thực sự cần JavaScript trên Java 17+, chọn provider có tài liệu rõ về:

- Tính tương thích với phiên bản JDK và module system.
- Ngôn ngữ và phiên bản ECMAScript thực sự hỗ trợ.
- Cách đặt dependencies trên classpath/module path và service registration.
- Host-access policy, sandboxing/isolation và quyền của script.
- `ScriptException`: cách báo location, cause, error writers và engine-specific types.
- Concurrency policy và whether engine instance có thể dùng nhiều threads.

Không đơn thuần thay tên `"JavaScript"` bằng `"nashorn"` rồi hy vọng JDK 17 khôi phục engine đã bị loại. Nếu chọn thư viện cung cấp Nashorn hoặc một engine khác, đó là **dependency ngoài JDK** cần kiểm thử và quản lý bảo mật riêng.

## 9. Ví dụ độc lập 3 — metadata mặc định của `ScriptException`

Vì `ScriptException` có thể không có filename/line/column, cần viết code không mặc định vị trí luôn tồn tại.

Tạo file **`ScriptExceptionMetadataDemo.java`**:

```java
import javax.script.ScriptException;

public class ScriptExceptionMetadataDemo {
    public static void main(String[] args) {
        ScriptException basic = new ScriptException("bad syntax");
        System.out.println("unknown file: " + basic.getFileName());
        System.out.println("unknown line: " + basic.getLineNumber());
        System.out.println("unknown column: " + basic.getColumnNumber());

        ScriptException positioned =
                new ScriptException("unexpected symbol", "rules.dsl", 4, 12);
        System.out.println("location: " + positioned.getFileName()
                + ":" + positioned.getLineNumber()
                + ":" + positioned.getColumnNumber());

        ScriptException wrapped =
                new ScriptException(new IllegalArgumentException("bad token"));
        System.out.println("wrapped cause: "
                + wrapped.getCause().getClass().getSimpleName());
        System.out.println("wrapped line: " + wrapped.getLineNumber());
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 ScriptExceptionMetadataDemo.java
java ScriptExceptionMetadataDemo
```

**Stdout đã kiểm chứng:**

```text
unknown file: null
unknown line: -1
unknown column: -1
location: rules.dsl:4:12
wrapped cause: IllegalArgumentException
wrapped line: -1
```

Phân tích:

- Constructor `new ScriptException("bad syntax")` không có metadata vị trí, nên `getFileName() == null`, `getLineNumber() == -1` và `getColumnNumber() == -1`.
- Constructor với `message,filename,line,column` lưu vị trí đã cấp.
- Constructor với `Exception` đặt exception đó làm cause, nhưng **không tự suy ra** line/column từ cause nếu cause không cung cấp theo hợp đồng.
- Không viết `e.getCause().getMessage()` mà bỏ null check trong code dùng `ScriptException` chung, vì constructor chỉ nhận message có thể không có cause.

## 10. Quy trình xử lý lỗi hoàn chỉnh theo từng boundary

Một ứng dụng đọc file script, nhận engine và evaluate có **ít nhất ba nơi** có thể thất bại:

```text
1. Engine discovery
   getEngineByName(...)
       |
       +-- null: thiếu provider / tên engine không đúng

2. File open/read source
   Files.newBufferedReader(path, charset)
       |
       +-- IOException: path không tồn tại, permission, I/O...
       |
       +-- Reader có được
              |
              v
3. Evaluation
   engine.eval(reader)
       |
       +-- ScriptException: syntax/runtime/checked interpreter errors
       |
       +-- Object result: parse và kiểm tra kiểu ở Java caller
```

Một **khung application logic** có thể như sau:

```java
// Pseudocode Java có thể tích hợp sau khi khai báo imports/engineName/path:
ScriptEngine engine = new ScriptEngineManager()
        .getEngineByName(engineName);
if (engine == null) {
    throw new IllegalStateException(
            "Missing JSR-223 engine provider: " + engineName);
}

engine.put(ScriptEngine.FILENAME, path.toString());

try (Reader reader = Files.newBufferedReader(
        path, StandardCharsets.UTF_8)) {
    Object raw = engine.eval(reader);
    // Validate result according to the script contract.
} catch (ScriptException e) {
    // Log engine name, safe script ID, optional filename/line/column.
    // Preserve e as the cause when propagating.
    throw new IllegalStateException("Script evaluation failed", e);
} catch (IOException e) {
    throw new IllegalStateException("Script file I/O failed", e);
}
```

Không phải chương trình độc lập: cần `engineName`, `path`, imports, policy errors và lựa chọn result handling phù hợp.

Trong code có logging production, tránh ghi toàn bộ script và biến đầu vào nếu chứa secrets. Có thể log một **script ID, version, hash** và location metadata, kèm request correlation ID.

### 10.1. Tự chọn thông báo lỗi có ích

Một thông điệp tốt cho người dùng/dev có thể gồm:

```text
Rule evaluation failed
  engine: <provider name>
  source: rule-42.dsl
  location: 7:13   (nếu có)
  category: script-evaluation
  cause: <script/parser cause, nếu có>
```

Đừng tạo giả một line/column nếu engine trả -1; hiển thị “không xác định”. Đừng nội suy một filename từ nội dung Reader nếu caller không có path. Khi engine trả lỗi không có metadata, hãy giữ thông điệp và stack/cause, không cố đoán.

### 10.2. Java file I/O error khác lỗi runtime của script

Giả sử `Path.of("missing.dsl")` không tồn tại. `Files.newBufferedReader` có thể ném `NoSuchFileException` (subtype của `IOException`) trước khi engine nhận Reader.

Ngược lại, một Reader đã mở nhưng hỏng giữa chừng có thể làm engine ném `ScriptException` bọc `IOException`. Khi bắt ScriptException, xem cause chain để phân loại reader I/O failure. Không coi mọi ScriptException là lỗi cú pháp.

### 10.3. Thực thi script gây side effect rồi ném ScriptException

Script có thể đã sửa state trước khi lỗi xảy ra:

```text
step 1: insert into database
step 2: call an HTTP endpoint
step 3: syntax/runtime failure -> ScriptException
```

JSR 223 **không** cung cấp transaction rollback mặc định. Nếu script chạy trong hệ thống có side effects, hãy cung cấp transaction boundary, idempotency, sandbox hoặc isolation theo nghiệp vụ, không dựa vào việc bắt `ScriptException` để “hoàn tác” các bước trước.

## 11. Đọc filename và số dòng đúng cách

Với một script dài, lỗi cần được liên hệ tới nguồn:

```java
catch (ScriptException e) {
    String filename = e.getFileName() != null
            ? e.getFileName() : "<inline-script>";
    int line = e.getLineNumber();
    int column = e.getColumnNumber();

    String location = filename
            + ":" + (line >= 0 ? line : "?")
            + ":" + (column >= 0 ? column : "?");
    System.err.println(location);
}
```

**Đoạn minh họa** này phải nằm trong một `try` có câu lệnh có thể ném ScriptException.

Một số engine thống nhất line/column theo cách khác nhau khi dùng:

- Dấu xuống dòng `\n` hoặc `\r\n`.
- Source String chứa newline sẵn, hoặc source Reader đọc file thật.
- Unicode ký tự ngoài BMP, tab và code points.
- Scripts được ghép từ nhiều segments hoặc được preprocess trước parse.

**Không** cắt/gộp script rồi kỳ vọng vị trí báo lỗi luôn trùng file gốc. Nếu có transpilation/template expansion, bạn cần source mapping do framework cung cấp. Line/column của `ScriptException` là thông tin engine cấp, có thể tương ứng **source đã biến đổi**, không nhất thiết tài liệu người dùng ban đầu.

### 11.1. FILENAME là metadata, không phải quyền đọc file

`engine.put(ScriptEngine.FILENAME,"rules.calc")` chỉ đặt một attribute. Nó không khiến engine tự đọc file `rules.calc` khi gọi `eval("add 2 5")`. Source vẫn là String được truyền trực tiếp.

Tương tự, `engine.eval(reader)` sẽ đọc từ **Reader được truyền**, không tự chuyển sang một file khác chỉ vì FILENAME có nội dung.

## 12. State, re-use engine và tính đồng thời

Có thể gọi một engine nhiều lần, nhưng phải hiểu state và thread-safety của provider.

### 12.1. Default context có thể giữ dữ liệu qua các lần eval

`engine.put("x", value)` cập nhật bindings của engine. Một script có thể đọc hoặc sửa các bindings này tùy ngôn ngữ. Nếu bạn dùng cùng một instance cho nhiều requests không tin cậy, rất dễ gặp data leakage khi request B thấy biến do request A đặt.

Để tránh rò rỉ state:

- Dùng `Bindings`/`ScriptContext` riêng cho từng evaluation khi semantics engine hỗ trợ đúng.
- Xem tài liệu provider về global object, shared caches và scope leakage.
- Tránh cấp những Java objects có quyền truy cập dữ liệu ngoài phạm vi request.
- Khi cần isolation thật, dùng engine/language contexts riêng hoặc **process isolation** theo threat model, chứ không chỉ tạo một `SimpleBindings` mới.

### 12.2. Không giả định ScriptEngine thread-safe

JSR 223 provider có mức độ hỗ trợ threading khác nhau. `ScriptEngineFactory.getParameter("THREADING")` trong một số provider có thể cho biết mô hình concurrency theo quy ước JSR 223, nhưng không nên coi mọi engine thread-safe hoặc singleton-safe.

Nếu không có cam kết rõ:

- Không chia sẻ **một instance ScriptEngine** để chạy đồng thời nhiều scripts trên nhiều threads mà không kiểm soát.
- Cân nhắc instance-per-request, pool có quy tắc ownership, hoặc synchronized/serialization khi phù hợp.
- Không cho nhiều threads thay default `Bindings`/`ScriptContext` cùng lúc rồi dựa vào kết quả ổn định.
- Tách source caching/precompilation khỏi state evaluation nếu provider hỗ trợ `Compilable`.

### 12.3. `Compilable` không có ở mọi engine

Một số engines cũng triển khai `javax.script.Compilable`:

```java
// Đoạn minh họa, không phải engine nào cũng là Compilable.
if (engine instanceof javax.script.Compilable compilable) {
    javax.script.CompiledScript compiled = compilable.compile(scriptSource);
    Object result = compiled.eval();
}
```

Điều này là tối ưu hóa *tùy chọn* cho script được evaluate lặp lại. Nó không làm thay đổi API cơ bản của `eval(String/Reader)`; và bản thân compiled script cũng có state/concurrency semantics riêng, cần đọc tài liệu provider.

## 13. Không coi `eval` là sandbox bảo mật

Đây là điểm quan trọng khi “nhúng script” vào ứng dụng:

- `eval` có thể thực thi mã theo quyền mà **engine và host integration** cho phép. Nếu script truy cập được Java objects có quyền I/O, network hoặc process, code script có thể gây side effects nghiêm trọng.
- `Bindings` là cách chuyển tên/giá trị vào script, **không** phải access-control layer.
- `ScriptException` giúp báo lỗi, **không** giới hạn thời gian, bộ nhớ, số vòng lặp hay quyền.
- Cắt thời gian bằng `Thread.interrupt()` không phải cách đảm bảo dừng mọi engine/provider, đặc biệt nếu interpreter/native code không hợp tác.
- Script nguồn không đáng tin cần **process isolation/container, giới hạn tài nguyên, quyền hệ điều hành và host-access policy** phù hợp threat model; không chỉ `try/catch`.

Thậm chí một script hoàn toàn hợp lệ vẫn có thể chạy vòng lặp vô hạn hoặc tiêu thụ quá nhiều bộ nhớ. Đây **không** phải `ScriptException` syntax error theo nghĩa thông thường. Nếu nhiệm vụ là chạy script của người dùng, hãy thiết kế timeout/cancellation/kill process ở boundary đáng tin cậy.

### 13.1. Đừng đưa code người dùng trực tiếp vào template không kiểm soát

Khi script chứa input ngoài ý muốn, tránh ghép chuỗi như:

```java
// Ví dụ nguy cơ: không nên chèn trực tiếp dữ liệu user vào script source.
String script = "calculate('" + userInput + "')";
```

Một chuỗi chứa dấu nháy hoặc cú pháp của ngôn ngữ script có thể thay đổi cấu trúc chương trình hoặc inject code. Ưu tiên chuyển dữ liệu qua `Bindings` hoặc API truyền arguments do provider hỗ trợ, với validation và host access restrictions. Binding không tự loại bỏ mọi rủi ro, nhưng tách code/source khỏi data là một nền tảng tốt.

## 14. Các lỗi thường gặp khi dùng `eval(String/Reader)`

### 14.1. Không kiểm tra engine có tồn tại

Sai:

```java
ScriptEngine engine = new ScriptEngineManager()
        .getEngineByName("JavaScript");
engine.eval("1 + 2"); // Có thể NullPointerException
```

Đúng: kiểm tra `engine != null` và cung cấp thông điệp thiếu provider rõ ràng.

### 14.2. Giả định Java 17 luôn cài Nashorn

Sai. JEP 372 loại bỏ Nashorn từ JDK 15. `java.scripting` vẫn tồn tại; `ScriptEngineManager` vẫn hoạt động nhưng engine cụ thể tùy dependencies.

### 14.3. Nghĩ `eval(Reader)` sẽ tự đóng Reader

Không nên dựa vào điều đó. Caller tạo Reader cần quản lý resource, thường là `try-with-resources`; chính demo MiniCalc **không** đóng Reader input. Khi reader đến từ file, quên close có thể rò rỉ file descriptors.

### 14.4. Nghĩ Reader luôn chứa tên file

Sai. `Reader` là nguồn characters; filename là metadata riêng. Gán `ScriptEngine.FILENAME` nếu provider có quy ước hỗ trợ, đồng thời lưu script ID/path phía application để báo lỗi.

### 14.5. Nhầm `IOException` lúc mở file với `ScriptException`

`Files.newBufferedReader` ném IOException ở phía Java caller. Engine đọc Reader có thể wrap IOException thành ScriptException khi evaluation đang chạy. Phân biệt boundary khi catch/log.

### 14.6. Nghĩ `ScriptException` lúc nào cũng có vị trí

Sai. `getFileName()` có thể null; line/column có thể `-1`. Hãy dùng fallback hợp lệ thay vì in `-1` như một dòng thực của script.

### 14.7. Nghĩ `getCause()` chắc chắn khác null

Sai. `new ScriptException("bad syntax")` có thể không có cause. Kiểm tra null trước khi dereference.

### 14.8. Ép `(Integer) engine.eval(...)` bất kể provider

Sai. `eval` trả `Object`, engine có thể trả `Double`, `BigDecimal`, object khác hoặc null. Kiểm tra kiểu hoặc dùng API conversion được provider mô tả.

### 14.9. Nhầm `eval(String,Bindings)` với `engine.setBindings`

Overload với Bindings cấp scope cho **lần gọi**, không có ý nghĩa mặc định thay thế engine default context. `setBindings` hoặc `setContext` có effects lâu hơn và cần kiểm soát khi share engine.

### 14.10. Dùng chung một ScriptEngine cho nhiều threads không kiểm tra

Không có cam kết thread safety chung cho mọi provider. Xem factory/provider docs và cân nhắc mỗi request một context/engine instance theo yêu cầu.

### 14.11. Nghĩ ScriptException tự rollback side effects

Sai. Script có thể đã thay đổi database, object Java, file hoặc API bên ngoài trước khi lỗi xảy ra. Exception không cung cấp transaction tự động.

### 14.12. Dùng `eval` làm sandbox cho script chưa tin cậy

Nguy hiểm. Không có memory/time/host-access isolation mặc định trong giao diện `ScriptEngine`; cần thiết kế boundary phù hợp.

### 14.13. Nghĩ `Reader` luôn nhanh hơn String

Không có bảo đảm. Provider có thể đọc hết Reader vào một String/AST; hiệu năng và memory phụ thuộc implementation và workload.

### 14.14. Nhầm lỗi script với Java checked exception bên ngoài

Một `IllegalArgumentException` khi application tạo parameter không hợp lệ, một `ClassCastException` sau khi eval thành công, hoặc một `IOException` mở file đều không mặc nhiên là `ScriptException` của script.

## 15. Bảng chẩn đoán nhanh

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| `getEngineByName("JavaScript") == null` | Không có provider đã đăng ký, sai alias, classpath/module path thiếu | Kiểm tra `getEngineFactories()`, dependencies và provider docs |
| `NullPointerException` ở `engine.eval` | Engine reference là null | Validate discovery trước khi eval |
| `ScriptException` có line/column | Parser/interpreter engine phát hiện lỗi | Log location, script ID, message và cause |
| `ScriptException` có line=-1, column=-1 | Engine không biết/không cung cấp vị trí | Không đoán vị trí; giữ message/cause |
| `ScriptException` bọc `IOException` | Đọc Reader lỗi trong quá trình eval | Kiểm tra underlying stream/source và cause |
| `NoSuchFileException` trước `eval` | Sai path/file không tồn tại | Xử lý lỗi mở file riêng |
| Script chạy nhưng kết quả là `null` | Kết quả script không có return value hoặc identifier thiếu tùy ngôn ngữ | Xác nhận contract của ngôn ngữ, không ép kiểu |
| `ClassCastException` sau eval | Caller giả định sai Java result type | Kiểm tra `Object`/`instanceof` hoặc provider conversions |
| Lần eval sau thấy giá trị lần trước | Default Bindings hoặc engine global state bị giữ | Tạo per-call Bindings/context và xem isolation semantics |
| Script lỗi charset/Unicode | Reader tạo từ file bằng encoding không đúng | Dùng `StandardCharsets.UTF_8` hoặc charset nguồn thực |
| Scripts concurrent cho kết quả bất thường | Chia sẻ engine/context không thread-safe | Cách ly instances, đồng bộ hoặc dùng documented threading model |
| Script treo vô hạn | No timeout/sandbox ở JSR 223 API | Đặt giới hạn tài nguyên/process isolation; không chỉ catch ScriptException |
| Log lặp filename/line | `getMessage()` đã chứa metadata, lại ghép một lần nữa | Dùng structured fields riêng; tránh nhân đôi |

## 16. Quy trình kiểm tra trước khi đưa vào production

**Bước 1 — Chốt provider.** Chọn ngôn ngữ, phiên bản và implementation. Kiểm tra `getEngineByName(...)` trả non-null trên đúng JDK/runtime image, container và build artifact. Tránh phụ thuộc provider chỉ có trong một máy developer.

**Bước 2 — Chốt source boundary.** Source là String, Reader, file UTF-8, database hay request body? Có size limit và encoding rõ ràng không? Reader có được đóng đúng khi evaluation kết thúc không?

**Bước 3 — Chốt execution contract.** Script cần trả kiểu gì? Có được đọc/ghi bindings nào? Cho phép side effects nào? Lỗi nào là user-facing vs internal?

**Bước 4 — Chốt ScriptContext.** Các variables thuộc ENGINE_SCOPE hoặc GLOBAL_SCOPE? Có cần context per-request? Có metadata filename hay writer/output capture không?

**Bước 5 — Chốt error mapping.** Nếu engine thiếu provider, báo config error. Nếu script parse/eval lỗi, báo ScriptException với location nếu có. Nếu mở Reader thất bại, báo I/O error. Nếu result type sai, báo contract validation error.

**Bước 6 — Chốt concurrency/security.** ScriptEngine có thread-safe không? Có script untrusted không? Có timeout/memory/CPU limits và cách hủy execution khi cần không?

**Bước 7 — Test đa môi trường.** Chạy trên JDK 17 thật, classpath/module path thực tế và các providers được đóng gói. Kiểm tra cơ chế service discovery hoạt động trong packaged JAR hoặc runtime image.

### 16.1. Một test suite tối thiểu nên có gì?

- `eval(String)` chạy script hợp lệ và trả đúng kết quả.
- `eval(Reader)` chạy cùng script với Reader, bao gồm newline, Unicode và encoding file.
- Script không hợp lệ ném `ScriptException`; kiểm tra location/cause khi provider hỗ trợ.
- Reader bị lỗi giữa chừng được báo và dọn dẹp resources đúng.
- Provider thiếu được báo **trước khi gọi `eval`**.
- Per-call bindings không làm rò dữ liệu sang default context trong scenario tương ứng.
- Script trả null hoặc result sai kiểu được xử lý rõ.
- Đồng thời nhiều requests không share context bừa bãi.
- Input script quá lớn hoặc script treo bị giới hạn theo threat model.

## 17. Câu hỏi tự kiểm tra

**Câu 1.** Sự khác nhau cơ bản giữa `eval(String)` và `eval(Reader)` là gì?

**Đáp án:** Một overload nhận script source đã có dưới dạng `String`, overload kia nhận nguồn characters qua `Reader`. Ngữ nghĩa ngôn ngữ/script result do engine quyết định; Reader không tự cho biết filename hay charset.

**Câu 2.** Trên JDK 17 không bổ sung provider, `getEngineByName("JavaScript")` có chắc chắn trả engine không?

**Đáp án:** Không. Nashorn bị loại bỏ từ JDK 15; `getEngineByName` có thể trả `null`. Cần validate và cài engine provider khi ứng dụng thực sự cần.

**Câu 3.** `ScriptEngine.eval` thực thi Java source trực tiếp hay script source của engine?

**Đáp án:** Script source theo ngôn ngữ mà engine triển khai. Scripting API không phải `javac` động để dịch mọi Java code.

**Câu 4.** `engine.eval("get base",oneCallBindings)` có tự thay default engine bindings vĩnh viễn không?

**Đáp án:** Không theo contract overload: `Bindings` được dùng làm ENGINE_SCOPE cho lần execution. Tuy nhiên provider có thể có shared side effects khác, nên per-call Bindings không phải isolation tuyệt đối.

**Câu 5.** Nếu source Reader được tạo bằng `Files.newBufferedReader(path,UTF_8)`, engine có tự lấy filename từ `path` không?

**Đáp án:** Không theo hợp đồng Reader. Đặt `ScriptEngine.FILENAME` nếu provider hỗ trợ và giữ path/script ID ở application để báo lỗi.

**Câu 6.** Ai đóng File Reader sau `eval(reader)`?

**Đáp án:** Caller nên dùng `try-with-resources`; không dựa vào engine tự đóng. Với StringReader không có tài nguyên file ngoài, việc close không quá quan trọng nhưng pattern vẫn nhất quán.

**Câu 7.** `ScriptException.getLineNumber()` trả gì khi engine không xác định được line?

**Đáp án:** `-1`. Tương tự column là `-1`, filename có thể `null`.

**Câu 8.** `getCause()` có luôn khác null không?

**Đáp án:** Không. `ScriptException` xây chỉ từ message có thể không có cause; phải null-check trước khi đọc.

**Câu 9.** File chưa tồn tại gây `NoSuchFileException` trước khi gọi eval. Đây là syntax error của script không?

**Đáp án:** Không. Đây là `IOException` ở tầng mở file; script engine chưa bắt đầu evaluate.

**Câu 10.** Reader đang đọc thì ném IOException, engine bọc thành ScriptException. Nên chẩn đoán thế nào?

**Đáp án:** Bắt ScriptException, xem `getCause()` và lỗi đọc nguồn. Không kết luận mọi ScriptException đều do sai cú pháp.

**Câu 11.** Vì sao `Object result = engine.eval(...)` có thể là `null`?

**Đáp án:** Kết quả do ngôn ngữ/provider quy định; script có thể không tạo giá trị trả về hoặc truy cập biến thiếu theo semantics đó. Kiểm tra trước khi cast/use.

**Câu 12.** Có thể dùng một `ScriptEngine` cho 100 threads cùng lúc không?

**Đáp án:** Chỉ khi provider và thiết kế ứng dụng cho phép. Không có bảo đảm thread safety chung cho mọi provider; nên đọc threading contract và cách ly contexts hoặc engines nếu cần.

**Câu 13.** Có thể dùng Bindings làm sandbox để ngăn scripts truy cập file/network không?

**Đáp án:** Không. Bindings không phải security sandbox; host-access policy và isolation phụ thuộc provider/môi trường, với scripts không tin cậy nên cân nhắc process isolation/giới hạn tài nguyên.

**Câu 14.** Vì sao `ScriptException` không rollback những thay đổi do script thực hiện trước khi lỗi?

**Đáp án:** JSR 223 chỉ quy định cơ chế báo lỗi evaluation, không cung cấp transaction manager hay undo side effects mặc định.

**Câu 15.** Engine có trả `Integer` khi chạy `1+2` trên mọi JavaScript provider không?

**Đáp án:** Không có bảo đảm đó. `eval` trả `Object`, mapping của số từ ngôn ngữ script sang Java object phụ thuộc provider.

**Câu 16.** Tại sao MiniCalc dùng `AbstractScriptEngine` và `getFactory()` nhưng không hiện ra từ `getEngineByName("minicalc")` mặc định?

**Đáp án:** Vì demo tạo engine trực tiếp và không đăng ký provider qua service mechanism hoặc `ScriptEngineManager.registerEngineName`. Việc có một factory object không đồng nghĩa manager tự khám phá được nó.

## 18. Bài tập áp dụng

### Bài tập A — so sánh String và StringReader

Dùng `MiniCalcEngine` của `ScriptEvalDemo`, evaluate `"add 11 12"` bằng `eval(String)` và `eval(new StringReader(...))`.

**Kết quả cần đạt:** hai lời gọi trả `Integer 23`. Phải giải thích rằng chỉ **nguồn source** khác, còn parser/semantics trong MiniCalc đã được viết để xử lý cả hai giống nhau.

### Bài tập B — đọc file và đóng Reader

Tạo file UTF-8 chứa:

```text
add 2 3
add 7 8
```

Mở bằng `Files.newBufferedReader(path,UTF_8)`, dùng `try-with-resources` và gọi `engine.eval(reader)`.

**Kỳ vọng với MiniCalc:** trả `15` vì nó chọn kết quả dòng cuối. Trong engine khác, phải theo semantics của engine đó.

### Bài tập C — lỗi cú pháp tại dòng 3

Gửi source MiniCalc:

```text
add 1 1
add 2 2
add 3 bad
```

Set `ScriptEngine.FILENAME` thành `"lesson.calc"`. Catch ScriptException, in filename/line/column và cause.

**Kết quả kỳ vọng với MiniCalc:** vị trí `lesson.calc:3:7`, cause `NumberFormatException`. Nhớ khác biệt giữa line/column do toy parser cung cấp và dữ liệu được một provider khác báo.

### Bài tập D — kiểm tra engine discovery

Chạy `ScriptEngineDiscoveryDemo` trên JDK 17 chưa cài provider, sau đó thêm một provider JSR 223 tương thích theo tài liệu của nó và chạy lại.

**Kết quả cần đạt:** trước đó chương trình có nhánh “not installed”; sau khi provider được tìm thấy, nó evaluate String và Reader. So sánh `getEngineFactories()`, engine name và kiểu Java result để hiểu sự khác nhau giữa runtime environments.

### Bài tập E — tách ENGINE_SCOPE và GLOBAL_SCOPE

Tạo `SimpleScriptContext`, một ENGINE_SCOPE chứa `base=3` và GLOBAL_SCOPE chứa `base=99`. Dùng MiniCalc `"get base"` để thấy ENGINE_SCOPE ưu tiên hơn. Bỏ `base` ở ENGINE_SCOPE rồi thử lại.

**Kết quả kỳ vọng:** khi cả hai scope có key, MiniCalc đọc 3; sau khi bỏ key ENGINE_SCOPE, nó tìm tới GLOBAL_SCOPE và đọc 99 theo `ScriptContext.getAttribute`.

## 19. Tài liệu chính thức

- **Java SE 17 — `ScriptEngine`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptEngine.html — sáu overload `eval`, bindings, context, reserved keys như `FILENAME`.
- **Java SE 17 — `ScriptEngineManager`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptEngineManager.html — service provider discovery, `getEngineByName`, manager global bindings.
- **Java SE 17 — `ScriptException`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptException.html — constructors, filename/line/column, cause.
- **Java SE 17 — `ScriptContext`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptContext.html — `ENGINE_SCOPE`, `GLOBAL_SCOPE`, Reader/Writers.
- **Java SE 17 — `AbstractScriptEngine`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/AbstractScriptEngine.html — cách triển khai overload eval dựa trên abstract methods.
- **Java SE 17 — `ScriptEngineFactory`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptEngineFactory.html — metadata và provider factory.
- **Java SE 17 — `Bindings` và `SimpleBindings`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/Bindings.html ; https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/SimpleBindings.html .
- **Java SE 17 — `Files.newBufferedReader`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html — Reader có charset và checked I/O.
- **JEP 372 — Remove the Nashorn JavaScript Engine:** https://openjdk.org/jeps/372 — lý do Nashorn không còn được đóng gói cùng JDK 15+.
- **Module `java.scripting`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/module-summary.html — API nền tảng của JSR 223.

**Kết luận:** `eval(String)` và `eval(Reader)` chỉ khác **cách cung cấp script source**, còn ngữ nghĩa ngôn ngữ, kiểu kết quả và mức độ lỗi do provider quyết định. Với Java 17+, hãy xác nhận **engine provider tồn tại** trước khi gọi. Khi xử lý `ScriptException`, giữ đúng filename/line/column nếu có, preserve cause và tách rõ lỗi I/O với lỗi script. Cuối cùng, quản lý Reader, Bindings, ScriptContext và trust boundary bằng những quy tắc rõ ràng để scripting nhúng không trở thành nguồn lỗi state, tài nguyên hoặc bảo mật.
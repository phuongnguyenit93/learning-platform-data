# Đọc ScriptException với tên tệp, dòng và cột khi engine cung cấp

## 1. Vai trò của ScriptException trong kịch bản nhúng

Java Scripting API (JSR 223, package `javax.script`) cho phép ứng dụng chủ gọi script engine bằng `ScriptEngine.eval(...)`. Khi parser hoặc quá trình đánh giá script báo lỗi theo cơ chế của engine, Java có thể nhận `javax.script.ScriptException`. Ngoài thông điệp, đối tượng lỗi có các thông tin vị trí **nếu engine cung cấp**:

- `getFileName()`: tên nguồn/script mà engine gán cho lỗi; có thể `null`.
- `getLineNumber()`: số dòng lỗi; giá trị `-1` biểu thị không biết vị trí.
- `getColumnNumber()`: số cột lỗi; giá trị `-1` biểu thị không biết vị trí.
- `getMessage()`: mô tả lỗi; có thể đã chứa tên tệp, dòng và cột tùy constructor/engine.
- `getCause()`: nguyên nhân gốc nếu exception được tạo với cause hoặc engine gắn cause.

Không phải mọi engine hỗ trợ chính xác cả ba trường vị trí. Không được suy ra rằng `getLineNumber()` hay `getColumnNumber()` luôn dương, rằng engine luôn dùng cột tính theo ký tự Unicode như editor, hoặc rằng `getFileName()` luôn bằng path thật trên đĩa.

## 2. Phân biệt ba loại thông tin

| Thành phần | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| Tên tệp / nguồn | Định danh script mà engine dùng khi báo lỗi | Có thể là tên logic như `rules/discount.js`, không nhất thiết là đường dẫn vật lý |
| Dòng | Vị trí trong source theo engine | Nếu engine dùng `-1` thì không biết; các source được ghép/preprocess có thể làm lệch vị trí |
| Cột | Vị trí trong dòng theo engine | `-1` là không biết; đơn vị cột, điểm bắt đầu và cách đếm phụ thuộc engine |
| Thông điệp lỗi | Mô tả cú pháp/runtime failure | Không thay thế hoàn toàn metadata có cấu trúc |
| Cause / stack trace | Lý do sâu hơn | Có thể không có; không nên mất stack trace khi wrap |

Trong nhiều engine, vị trí được báo theo 1-based line/column, nhưng API `ScriptException` **không đảm bảo mọi engine quy đổi vị trí tương ứng với cách hiển thị editor của bạn**. Khi tạo IDE hoặc hệ thống quy tắc có line mapping, cần kiểm thử với engine cụ thể, nhất là source có ký tự đa byte, tabs, CRLF hoặc Unicode supplementary characters.

## 3. Cách lấy và hiển thị metadata an toàn

Ví dụ Java 17+ tối giản, không cần engine có sẵn: tạo một `ScriptException` và hiển thị các trường:

```java
import javax.script.ScriptException;

public class ScriptErrorReport {
    static String location(ScriptException ex) {
        String source = ex.getFileName();
        if (source == null || source.isBlank()) source = "<unknown source>";
        String line = ex.getLineNumber() >= 0
                ? Integer.toString(ex.getLineNumber()) : "?";
        String column = ex.getColumnNumber() >= 0
                ? Integer.toString(ex.getColumnNumber()) : "?";
        return source + ":" + line + ":" + column;
    }

    public static void main(String[] args) {
        ScriptException ex =
                new ScriptException("Unexpected token", "rules/example.dsl", 7, 12);
        System.out.println(location(ex));
        System.out.println("Message: " + ex.getMessage());

        ScriptException unknown = new ScriptException("Evaluation failed");
        System.out.println(location(unknown));
    }
}
```

Chạy:

```bash
javac --release 17 ScriptErrorReport.java
java ScriptErrorReport
```

Output:

```text
rules/example.dsl:7:12
Message: Unexpected token in rules/example.dsl at line number 7 at column number 12
<unknown source>:?:?
```

`ScriptException(String message, String fileName, int line, int column)` có thể bổ sung vị trí vào `getMessage()`; vì vậy nếu tự ghép `location + message` để log thì tên nguồn/dòng/cột có thể bị lặp. Nên xác định format log thống nhất: metadata riêng để máy đọc, message để người dùng hiểu.

## 4. Lấy exception từ một script engine thực tế

API thông thường:

```java
ScriptEngineManager manager = new ScriptEngineManager();
ScriptEngine engine = manager.getEngineByName("engine-name");
if (engine == null) {
    throw new IllegalStateException("Required script engine not installed");
}
try {
    engine.eval(scriptText);
} catch (ScriptException ex) {
    System.err.println("Script: " + ex.getFileName());
    System.err.println("Line: " + ex.getLineNumber());
    System.err.println("Column: " + ex.getColumnNumber());
    throw ex;
}
```

Đây là đoạn code minh họa trong method có `scriptText` và imports `javax.script.*`. JDK 17 **không kèm Nashorn mặc định**; `ScriptEngineManager` có thể không phát hiện engine nào nếu không cài thêm provider qua dependency/module path. Vì vậy không nên viết ví dụ mặc định gọi `getEngineByName("JavaScript")` rồi khẳng định luôn chạy được.

### Gắn định danh nguồn bằng ScriptEngine.FILENAME

JSR 223 định nghĩa key `ScriptEngine.FILENAME` (tên đầy đủ thường là `javax.script.filename`). Một số engine dùng thuộc tính này làm tên script trong diagnostics:

```java
ScriptContext context = engine.getContext();
Object old = context.getAttribute(ScriptEngine.FILENAME,
        ScriptContext.ENGINE_SCOPE);
try {
    context.setAttribute(ScriptEngine.FILENAME,
            "rules/tax-policy.dsl", ScriptContext.ENGINE_SCOPE);
    engine.eval(scriptText, context);
} catch (ScriptException ex) {
    logScriptError(ex);
} finally {
    if (old == null) {
        context.removeAttribute(ScriptEngine.FILENAME,
                ScriptContext.ENGINE_SCOPE);
    } else {
        context.setAttribute(ScriptEngine.FILENAME, old,
                ScriptContext.ENGINE_SCOPE);
    }
}
```

Đây là đoạn minh họa, giả định `engine`, `scriptText` và `logScriptError` được khai báo. **Không engine nào bị bắt buộc phải đưa FILENAME vào mọi ScriptException**; nếu engine không hỗ trợ, `getFileName()` vẫn có thể là `null`. Ngoài ra `getContext()` có thể được chia sẻ giữa nhiều lần đánh giá: cập nhật context nên được đồng bộ hoặc tạo `SimpleScriptContext` riêng cho từng request để tránh rò rỉ tên script giữa các lần chạy.

Phương án cô lập context mỗi lần đánh giá:

```java
ScriptContext context = new SimpleScriptContext();
context.setAttribute(ScriptEngine.FILENAME, "rules/tax-policy.dsl",
        ScriptContext.ENGINE_SCOPE);
engine.eval(scriptText, context);
```

Đây là đoạn trong method có imports phù hợp. Nếu script cần bindings, readers/writers hoặc global scope, phải cấu hình context tương ứng; `SimpleScriptContext` mới không tự mang hết cấu hình từ context mặc định của engine.

## 5. Ví dụ engine giả lập để kiểm chứng đường xử lý lỗi

Khi unit-test logic báo lỗi, có thể tạo `ScriptException` theo dữ liệu đầu vào mà không phụ thuộc engine bên ngoài. Dưới đây là chương trình Java 17+ độc lập sử dụng một hàm `evaluate` giả lập để biểu diễn hai tình huống: parser cung cấp vị trí và runtime không cung cấp vị trí.

```java
import javax.script.ScriptException;

public class ScriptExceptionCases {
    static void evaluate(String sourceName, boolean hasLocation)
            throws ScriptException {
        if (hasLocation) {
            throw new ScriptException("Invalid assignment", sourceName, 3, 8);
        }
        throw new ScriptException("Execution failed");
    }

    static void print(ScriptException ex, String fallbackSource) {
        String name = ex.getFileName() == null
                ? fallbackSource : ex.getFileName();
        String line = ex.getLineNumber() < 0
                ? "unknown" : Integer.toString(ex.getLineNumber());
        String column = ex.getColumnNumber() < 0
                ? "unknown" : Integer.toString(ex.getColumnNumber());
        System.out.println("source=" + name +
                ", line=" + line + ", column=" + column);
    }

    public static void main(String[] args) {
        for (boolean loc : new boolean[] {true, false}) {
            try {
                evaluate("workflow.dsl", loc);
            } catch (ScriptException ex) {
                print(ex, "workflow.dsl");
            }
        }
    }
}
```

Chạy:

```bash
javac --release 17 ScriptExceptionCases.java
java ScriptExceptionCases
```

Output:

```text
source=workflow.dsl, line=3, column=8
source=workflow.dsl, line=unknown, column=unknown
```

Ví dụ này minh họa **xử lý** metadata và fallback; nó không tuyên bố có JavaScript engine hay parser thật. Trong ứng dụng thực, thay `evaluate` bằng engine cần hỗ trợ; unit tests cho formatter vẫn chạy ổn định không lệ thuộc môi trường.

## 6. Vị trí nguồn có thể bị lệch như thế nào?

Script engine báo vị trí dựa trên **source nó nhìn thấy**, không nhất thiết là văn bản mà người dùng mở trong editor. Các biến đổi sau dễ tạo sai lệch:

- Chèn header/helper code trước khi eval: lỗi ở dòng 20 của chuỗi kết quả có thể tương ứng dòng 17 của file gốc.
- Ghép nhiều file script thành một string: `getFileName()` có thể là file chung, line không chỉ đúng source gốc.
- Preprocessor/macros: một token source gốc có thể sinh nhiều token ở chuỗi eval.
- CRLF so với LF: engine có thể tính line/column khác công cụ hiển thị nếu normalize source.
- Tab và Unicode: khái niệm cột không nhất thiết bằng số ô hiển thị trên editor.

Muốn hiển thị underline chính xác, nên giữ **source map** hoặc bảng offset mapping từ chuỗi chạy đến nguồn gốc. Nếu không có mapping, báo vị trí theo văn bản engine thực sự nhận và nói rõ đây là generated source location. Đừng tự cộng/trừ số dòng mù khi hệ thống đã biến đổi nhiều bước.

## 7. Truyền lỗi qua các lớp kiến trúc

Một hệ thống chạy script thường có các lớp: API → script runner → JSR 223 engine. Nếu runner bắt `ScriptException` rồi ném `new RuntimeException(ex.getMessage())`, toàn bộ thông tin file/line/column và cause có thể bị mất. Có hai cách an toàn:

1. Giữ nguyên `ScriptException` và để tầng gọi xử lý.
2. Wrap lỗi trong một exception nghiệp vụ có cause và metadata riêng (source name, line, column) để API/UI có thể hiển thị.

Ví dụ đoạn code trong method:

```java
try {
    return engine.eval(script, context);
} catch (ScriptException ex) {
    throw new ScriptRunFailure(
            sourceId, ex.getLineNumber(), ex.getColumnNumber(), ex);
}
```

`ScriptRunFailure` ở đây là một class lỗi nghiệp vụ **tự định nghĩa**, không phải Java API dựng sẵn. Đừng nuốt `getCause()` hoặc chỉ ghi mỗi chuỗi message nếu cần chẩn đoán.

### Log an toàn

Với script do người dùng cung cấp, tránh log nguyên toàn bộ source hay secret trong bindings; log source ID đã chuẩn hóa, loại lỗi, line/column nếu biết, request correlation ID và stack trace ở mức được phép. Nếu `getFileName()` là path bên ngoài, cân nhắc không trả full filesystem path trong API response. UI nên escape message trước khi hiển thị để tránh script message chèn nội dung không an toàn vào HTML/log.

## 8. Lỗi thường gặp và cách khắc phục

| Tình huống | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| File name là `null` | Engine không có thông tin hoặc không dùng `FILENAME` | Dùng source ID của ứng dụng làm fallback |
| Line/column là `-1` | Engine không báo vị trí | Hiển thị `unknown`, không ép thành 0 |
| Cột không khớp editor | Tabs, Unicode, newline hoặc quy tắc engine | Kiểm tra unit/indexing, source map nếu có transform |
| `getMessage()` lặp file/line | Constructor của ScriptException đã gắn metadata vào message | Định dạng log tránh nhân đôi |
| `getEngineByName(...)` trả `null` | Chưa cài engine provider | Cài dependency thích hợp, kiểm tra classpath/module path |
| Lỗi hiển thị sai file khi chạy đồng thời | Chia sẻ mutable `ScriptContext` | Tạo context riêng hoặc đồng bộ |
| Wrap exception làm mất line/column | Chỉ giữ message string | Preserve `ScriptException` hoặc metadata + cause |
| Đổi script source trước eval | Position báo theo generated text | Duy trì source map, ghi rõ mapping |
| Runtime lỗi nhưng không có vị trí | Engine không cung cấp vị trí runtime | Báo rõ giới hạn; dùng stack trace/cause nếu có |

## 9. Checklist thực hành

- [ ] Kiểm tra `ScriptEngine` tồn tại trước khi eval.
- [ ] Gắn source identifier hợp lệ qua `ScriptEngine.FILENAME` nếu engine hỗ trợ.
- [ ] Đọc `getFileName()`, `getLineNumber()`, `getColumnNumber()` thay vì parse message.
- [ ] Xử lý `null`/`-1` như trường hợp không biết vị trí.
- [ ] Giữ cause và stack trace khi chuyển exception giữa các tầng.
- [ ] Test syntax error, runtime error và engine không báo location.
- [ ] Nếu có preprocess/ghép file, duy trì offset/line source mapping.
- [ ] Không giả định JDK 17 có sẵn Nashorn/JavaScript engine.
- [ ] Không tiết lộ đường dẫn hay source bí mật trong diagnostics gửi người dùng.
- [ ] Đảm bảo formatter lỗi chạy được ngay cả khi không cài engine.

**Kết luận:** `ScriptException` cung cấp API có cấu trúc để đọc tên nguồn, dòng và cột, nhưng **độ đầy đủ của metadata phụ thuộc script engine**. Luôn đọc và kiểm tra trực tiếp các getter, dùng fallback phù hợp, bảo toàn cause và chỉ hiển thị vị trí khi đáng tin. Điều này giúp hệ thống kịch bản nhúng báo lỗi rõ ràng mà không phụ thuộc vào việc parse chuỗi thông báo.

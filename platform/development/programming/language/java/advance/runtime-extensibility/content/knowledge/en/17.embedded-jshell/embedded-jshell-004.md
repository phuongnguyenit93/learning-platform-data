# Đọc SnippetEvent, trạng thái, kết quả và chẩn đoán của đoạn mã trong JShell nhúng

## 1. Bốn nguồn thông tin khác nhau

Java cung cấp JShell API từ Java 9 qua module `jdk.jshell`. Trong ứng dụng nhúng, gọi `JShell.eval(String)` trả về `List<SnippetEvent>`, có thể gồm nhiều sự kiện cho một lần nhập: sự kiện snippet mới và sự kiện cập nhật snippet phụ thuộc hoặc snippet cũ bị ghi đè.

Để trình bày chính xác kết quả biên dịch/đánh giá cần phân biệt:

- `SnippetEvent` mô tả **sự chuyển trạng thái** của một snippet, gồm status, value và exception.
- `Snippet` chứa định danh `id()`, nguồn `source()`, loại `kind()`.
- `Diag` chứa compiler diagnostics lấy qua `JShell.diagnostics(snippet)`, không có API `event.getDiagnostics()`.
- Output từ `System.out`/`System.err` trong snippet được gửi qua stream của JShell, không đồng nghĩa `event.value()`.

## 2. Các getter của SnippetEvent

| Getter | Ý nghĩa | Khi nào có thể thiếu? |
| --- | --- | --- |
| `snippet()` | Snippet gắn với event | Đọc để liên kết UI/session |
| `status()` | Trạng thái **sau** sự kiện | Cần đọc cho từng event |
| `previousStatus()` | Trạng thái **trước** sự kiện | Có thể `NONEXISTENT` khi là snippet mới |
| `causeSnippet()` | Snippet gây cập nhật gián tiếp | Có thể `null` nếu đánh giá trực tiếp |
| `isSignatureChange()` | Chữ ký snippet thay đổi hay không | Không phải thước đo runtime success |
| `value()` | Chuỗi biểu diễn kết quả khi có | Có thể `null` với import, method, lệnh không có value |
| `exception()` | Lỗi khi chạy snippet | Có thể `null` dù compile bị từ chối |

**`status() == VALID` không bảo đảm đoạn code chạy thành công**: một biểu thức compile được vẫn có thể ném exception khi thực thi. Tương tự, `value() == null` không đồng nghĩa compile thất bại.

## 3. Trạng thái Snippet.Status

- `VALID`: snippet được chấp nhận và có hiệu lực.
- `RECOVERABLE_DEFINED`: declaration thiếu tham chiếu nhưng còn có thể được định nghĩa/phục hồi khi bổ sung dependency.
- `RECOVERABLE_NOT_DEFINED`: declaration chưa thể định nghĩa đầy đủ vì thiếu phụ thuộc; vẫn có khả năng phục hồi.
- `REJECTED`: đoạn mã bị từ chối bởi kiểm tra cú pháp/kiểu hoặc các điều kiện compile.
- `OVERWRITTEN`: snippet cũ bị declaration mới thay thế.
- `DROPPED`: snippet bị xóa qua thao tác drop.
- `NONEXISTENT`: snippet không tồn tại trong trạng thái được đề cập.

Đây là status của **snippet theo JShell state**, không phải một boolean `success` duy nhất. Một lần eval có thể thay đổi nhiều snippet; consumer cần duyệt toàn bộ danh sách event.

## 4. Ví dụ Java 17+ chạy được

Ví dụ sau tạo JShell, đánh giá biến, biểu thức và lỗi compile. Chương trình in kind/status/value và số diagnostics lỗi. Không cần cài thêm JavaScript engine hay Nashorn; đây là **JShell Java code**, không phải JSR 223.

Tệp `EmbeddedJShellDemo.java`:

```java
import jdk.jshell.Diag;
import jdk.jshell.JShell;
import jdk.jshell.Snippet;
import jdk.jshell.SnippetEvent;
import java.util.List;

public final class EmbeddedJShellDemo {
    static void inspect(JShell shell, String code) {
        System.out.println("INPUT: " + code);
        List<SnippetEvent> events = shell.eval(code);
        for (SnippetEvent event : events) {
            Snippet snippet = event.snippet();
            System.out.println("  kind=" + snippet.kind()
                    + ", status=" + event.status());
            if (event.value() != null) {
                System.out.println("  value=" + event.value());
            }
            if (event.exception() != null) {
                System.out.println("  exception="
                        + event.exception().getClass().getSimpleName());
            }
            long errors = shell.diagnostics(snippet)
                    .filter(Diag::isError).count();
            System.out.println("  errors=" + errors);
        }
    }

    public static void main(String[] args) {
        try (JShell shell = JShell.create()) {
            inspect(shell, "int x = 10;");
            inspect(shell, "x + 5");
            inspect(shell, "int broken = missingName;");
        }
    }
}
```

Chạy trên JDK 17+ có `jdk.jshell`:

```bash
javac --add-modules jdk.jshell EmbeddedJShellDemo.java
java --add-modules jdk.jshell EmbeddedJShellDemo
```

Output điển hình với JDK 17:

```text
INPUT: int x = 10;
  kind=VAR, status=VALID
  value=10
  errors=0
INPUT: x + 5
  kind=VAR, status=VALID
  value=15
  errors=0
INPUT: int broken = missingName;
  kind=VAR, status=REJECTED
  errors=1
```

JShell có thể tạo scratch variable khi đánh giá biểu thức `x + 5`, nên kind là `VAR` trong trường hợp trên. Compiler message cụ thể có thể thay đổi theo phiên bản JDK/locale. Ví dụ chủ động đếm lỗi thay vì so sánh chuỗi thông báo.

## 5. Đọc chẩn đoán bằng Diag

API chuẩn để lấy diagnostics:

```java
shell.diagnostics(snippet).forEach(diag -> {
    System.out.println((diag.isError() ? "error" : "warning")
            + ": " + diag.getMessage(java.util.Locale.ROOT));
    System.out.println("start=" + diag.getStartPosition()
            + ", end=" + diag.getEndPosition());
});
```

Đoạn này là **snippet minh họa trong method** đã có `JShell shell` và `Snippet snippet`, không phải chương trình độc lập. `Diag.getStartPosition()`, `getEndPosition()` và `getPosition()` trả offset trong source của snippet, có thể là `-1` nếu không có vị trí. Không coi offset là số dòng.

Ví dụ helper ánh xạ offset sang dòng/cột theo UTF-16 code units của source Java (không xử lý riêng tab width, grapheme clusters hoặc source preprocessing):

```java
static String lineColumn(String source, long offset) {
    if (offset < 0 || offset > source.length()) return "unknown";
    int line = 1;
    int column = 1;
    for (int i = 0; i < offset; i++) {
        if (source.charAt(i) == '\n') {
            line++;
            column = 1;
        } else {
            column++;
        }
    }
    return line + ":" + column;
}
```

Với dữ liệu nhiều file, source transform hoặc editor đếm code points khác Java, cần source map thích hợp. Không gắn line/column của một snippet ngắn trực tiếp vào tệp gốc khi ứng dụng đã nối/preprocess code.

## 6. Lỗi compile khác lỗi runtime

**Compile failure:** một snippet như `int n = noSuchIdentifier;` thường có `REJECTED`; hãy kiểm tra `JShell.diagnostics(event.snippet())`, vì `exception()` không phải kênh báo lỗi compile.

**Runtime failure:** một snippet như `1 / 0` có thể compile thành công nhưng gây lỗi khi đánh giá. `event.exception()` khi đó có thể là `jdk.jshell.EvalException`; thông tin bổ sung gồm `getExceptionClassName()` và stack trace. Một số snippet thiếu tham chiếu có thể dẫn đến `UnresolvedReferenceException`. Không dùng `value()` đơn lẻ để quyết định thành công.

Ví dụ (trong method có biến `shell`):

```java
for (SnippetEvent event : shell.eval("1 / 0")) {
    if (event.exception() instanceof jdk.jshell.EvalException ex) {
        System.out.println(ex.getExceptionClassName());
    }
}
```

Đối với exception runtime, UI có thể hiển thị loại và message, còn hệ thống log giữ stack trace phù hợp. Không để nội dung message/stack trace chưa escape đi thẳng vào HTML.

## 7. Theo dõi event phụ, overwrite và drop

Trạng thái JShell tồn tại qua nhiều lần eval. Khi cùng một variable/method/type được khai báo lại, JShell có thể báo snippet mới và snippet cũ `OVERWRITTEN`. Khi một declaration được thêm hoặc sửa, snippets phụ thuộc có thể được cập nhật. Duyệt tất cả event:

```java
for (SnippetEvent event : events) {
    Snippet changed = event.snippet();
    Snippet cause = event.causeSnippet();
    System.out.println("id=" + changed.id()
            + " previous=" + event.previousStatus()
            + " now=" + event.status()
            + " signatureChange=" + event.isSignatureChange()
            + " cause=" + (cause == null ? "direct" : cause.id()));
}
```

Đây là đoạn minh họa trong method có `List<SnippetEvent> events`. Khi host có UI hoặc registry, key cần bao gồm **session identity** cùng snippet identity; `snippet.id()` chỉ có ý nghĩa trong một JShell session. Đừng giữ status/value cũ sau event `OVERWRITTEN` hay `DROPPED`.

## 8. Tách stdout/stderr với value

`System.out.println("hello")` do code snippet gọi xuất text qua output stream, **không biến text thành event.value()**. Khi khởi tạo JShell có thể cấu hình:

```java
try (JShell shell = JShell.builder()
        .out(System.out)
        .err(System.err)
        .build()) {
    shell.eval("System.out.println(\"hello\")");
}
```

Trong ứng dụng thật, mỗi session/request nên có stream/buffer riêng. Nếu dùng chung `System.out` giữa các session, output có thể xen kẽ. Các phần UI nên trình bày riêng: diagnostics compile, lỗi runtime, giá trị biểu thức và stdout/stderr.

## 9. Cách thiết kế kết quả API

Ví dụ contract dữ liệu có thể bao gồm:

| Field | Lấy từ | Ý nghĩa |
| --- | --- | --- |
| `sessionId` | Host tự tạo | Tránh trùng snippet ID giữa các session |
| `snippetId` | `snippet.id()` | Định danh của snippet trong session |
| `source` | `snippet.source()` | Source được JShell nhận |
| `kind` | `snippet.kind()` | Loại snippet |
| `previousStatus`, `status` | `SnippetEvent` | Sự chuyển trạng thái |
| `value` | `SnippetEvent.value()` | Result string nếu có |
| `runtimeException` | `SnippetEvent.exception()` | Lỗi khi thực thi |
| `diagnostics` | `JShell.diagnostics(snippet)` | Compiler errors/warnings |
| `stdout`, `stderr` | Stream của JShell builder | Text do code in ra |

Khi kết quả trả về ứng dụng web, escape source, message và output. Giới hạn kích thước buffer và lưu ý rằng output từ code chưa tin cậy có thể chứa thông tin nhạy cảm.

## 10. Vòng đời và bảo mật

JShell là môi trường giữ state: variables, imports, methods và classes có thể tồn tại qua nhiều snippet. Dùng `try-with-resources` hoặc `close()` khi kết thúc. Tránh chia sẻ một instance giữa nhiều người dùng nếu không có kiểm soát session và truy cập đồng thời.

JShell nhúng **không phải sandbox bảo mật tự động**. Nếu chạy code không tin cậy, phải kiểm soát execution engine, OS permissions, CPU/memory/time budgets và cô lập process/container khi phù hợp. Đừng nhận đầu vào code bất kỳ rồi thực thi trong tiến trình host có quyền rộng.

## 11. Những lỗi thường gặp

| Lỗi | Hậu quả | Giải pháp |
| --- | --- | --- |
| Chỉ đọc event đầu tiên | Bỏ sót trạng thái của snippet phụ thuộc | Duyệt toàn bộ events |
| Coi VALID là chạy thành công | Bỏ qua runtime exception | Kiểm tra exception riêng |
| Coi value() là System.out | Sai hiển thị output | Tách stream và value |
| Không đọc diagnostics | Không giải thích vì sao REJECTED | Gọi JShell.diagnostics |
| Coi offset Diag là số dòng | Highlight sai vị trí | Ánh xạ offset vào source |
| Giữ state cũ sau overwrite | UI hiển thị sai | Dựa trên event mới nhất |
| Dùng snippet.id xuyên session | Va chạm ID | Thêm session ID của host |
| Không đóng JShell | Rò rỉ tài nguyên | Close mỗi session |

## 12. Checklist

- [ ] Duyệt toàn bộ `List<SnippetEvent>` của mỗi lần eval.
- [ ] Đọc cả status trước/sau, cause và signature change.
- [ ] Phân biệt compiler diagnostics, runtime exception, value và stdout.
- [ ] Xử lý `REJECTED` và các trạng thái recoverable đúng ý nghĩa.
- [ ] Dùng `Diag` cho message và vị trí; map offsets cẩn thận.
- [ ] Dọn state sau overwrite/drop, không giữ dữ liệu cũ.
- [ ] Đóng session và dùng chính sách cô lập cho code chưa tin cậy.

**Kết luận:** `SnippetEvent` nói điều gì **đã thay đổi** trong JShell, `status()` nói snippet có trạng thái nào, `value()` là kết quả biểu thức nếu có, `exception()` báo lỗi khi đánh giá, và `Diag` cung cấp chẩn đoán của compiler. Đọc các nguồn này riêng biệt giúp ứng dụng nhúng giải thích lỗi và cập nhật giao diện một cách chính xác.

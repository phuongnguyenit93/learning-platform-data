# Phân tích đoạn mã hoàn chỉnh trước khi gọi JShell.eval

## 1. Mục tiêu: không đánh giá một mảnh Java chưa hoàn chỉnh

Khi nhúng JShell vào ứng dụng Java, host thường nhận mã theo từng dòng từ terminal, editor, giao diện web hoặc từ một chuỗi chứa nhiều khai báo. Không phải mỗi dòng là một đoạn Java có thể chạy độc lập. Ví dụ người dùng nhập một method qua ba dòng:

~~~java
int square(int x) {
    return x * x;
}
~~~

Nếu host gọi `JShell.eval("int square(int x) {")` ngay khi nhận dòng đầu tiên, nó đã gửi **mã còn dang dở** vào engine. Ngược lại, nếu host nối toàn bộ file chứa nhiều lệnh rồi gọi `eval` một lần, đó cũng không phải cách dùng đáng tin cậy: theo hợp đồng API, `eval(String)` nên nhận **đúng một snippet hoàn chỉnh** (một statement, expression, import, khai báo biến, method hoặc class).

API thiết kế cho tình huống này là:

~~~java
SourceCodeAnalysis analysis = jshell.sourceCodeAnalysis();
SourceCodeAnalysis.CompletionInfo info =
        analysis.analyzeCompletion(pendingSource);
~~~

Đây là đoạn minh họa; `jshell` và `pendingSource` phải được tạo trước. `SourceCodeAnalysis` phân tích ranh giới **snippet đầu tiên**, cho biết nó đã hoàn chỉnh hay cần nhận thêm đầu vào, và trả phần còn lại để lặp tiếp. Chỉ sau khi có một snippet đủ điều kiện, host mới chuyển nó cho `JShell.eval`.

Sau bài này, bạn có thể xây một bộ đệm REPL an toàn về mặt **phân tách cú pháp**: tích lũy mã đa dòng, nhận nhiều snippet trong cùng một lần gửi, hiểu ý nghĩa sáu trạng thái completeness, đọc `source()`/`remaining()`, xử lý lỗi eval và tránh nhầm “hoàn chỉnh cú pháp” với “đúng ngữ nghĩa hay an toàn để chạy”.

## 2. Ba đối tượng chính trong API JShell

### 2.1. JShell lưu trạng thái đánh giá

`jdk.jshell.JShell` là engine chứa các định nghĩa/giá trị từ những lần gọi trước. Một shell đã đánh giá `int n = 7;` có thể dùng `n` ở snippet tiếp theo:

~~~java
// Minh họa về hai lần gọi, không phải chương trình độc lập.
jshell.eval("int n = 7;");
jshell.eval("n * 3;");
~~~

`JShell.eval` trả về `List<SnippetEvent>`, chứ **không** trả trực tiếp giá trị biểu thức. Với mỗi event cần đọc `status()`, `value()` (nếu có), `exception()`, và diagnostics khi snippet bị từ chối. Một lời gọi `eval` có thể gây event phụ trên snippet phụ thuộc khi trạng thái thay đổi, nên không giả định danh sách luôn chỉ có một phần tử.

### 2.2. SourceCodeAnalysis phân tích mà chưa thực thi

Lấy analyzer từ đúng shell mà bạn sẽ eval:

~~~java
SourceCodeAnalysis analysis = jshell.sourceCodeAnalysis();
~~~

`analysis.analyzeCompletion(text)` tìm **snippet đầu tiên** trong `text` và phân tích mức hoàn chỉnh của nó. Phân tích này **không thực thi** lệnh Java, không định nghĩa biến/method vào JShell và không có nghĩa mọi tên kiểu/phương thức đều hợp lệ.

Các chức năng khác của `SourceCodeAnalysis` như `completionSuggestions` hoặc `sourceToSnippets` giải bài toán khác. Cụ thể, `sourceToSnippets` có thể tạo các đối tượng `Snippet` để xem trước, nhưng không thay thế vòng lặp tách đầu vào cho `eval` và không tự cài đặt các khai báo vào trạng thái shell.

### 2.3. CompletionInfo là kết quả phân tích

`SourceCodeAnalysis.CompletionInfo` có ba phương thức quan trọng:

| Phương thức | Câu hỏi cần trả lời |
| --- | --- |
| `completeness()` | Snippet đầu tiên đã hoàn chỉnh, cần thêm mã hay phân tích không quyết định được? |
| `source()` | Chuỗi của **snippet đầu tiên** sẽ được gửi vào `eval`; dấu chấm phẩy có thể đã được bổ sung khi cần |
| `remaining()` | Phần input **còn lại sau snippet đầu tiên**, cần đưa trở lại bộ phân tích |

Với chuỗi `"int a = 1; int b = 2;"`, ta không nên đưa nguyên chuỗi vào một lần `eval`. Thay vào đó, phân tích lấy snippet `int a = 1;`; giữ phần còn lại rồi phân tích `int b = 2;` ở lượt tiếp theo.

**Quan trọng:** đừng tự thay `source()` bằng phép `substring` cắt tại dấu `;` hoặc `}`. Parser biết dấu chấm phẩy trong `for (...)`, dấu ngoặc trong chuỗi/comment, text block và cấu trúc Java; phép tách thuần văn bản rất dễ phá hỏng mã.

## 3. Sáu giá trị SourceCodeAnalysis.Completeness

`Completeness` là enum trong `SourceCodeAnalysis`. Phân biệt chúng giúp host biết **khi nào chờ, khi nào eval** và khi nào phải báo lỗi đầu vào.

| Giá trị | Ý nghĩa | Hành vi thông thường |
| --- | --- | --- |
| `COMPLETE` | Đầu vào có snippet đầu tiên hoàn chỉnh như hiện có | Lấy `source()` và gọi `eval` |
| `COMPLETE_WITH_SEMI` | Snippet sẽ hoàn chỉnh nếu thêm dấu `;` ở cuối | Tùy policy giao diện: chấp nhận nguồn do `source()` cung cấp (đã bổ sung `;`) hoặc đợi người dùng xác nhận |
| `DEFINITELY_INCOMPLETE` | Bắt buộc phải có thêm source; thêm `;` chưa đủ | **Chờ** thêm input, giữ buffer |
| `CONSIDERED_INCOMPLETE` | Có tình huống câu lệnh kết thúc bằng một statement rỗng chưa được chấm dứt; việc tự thêm `;` hiếm khi đúng ý định | **Chờ** thêm input, không ép thêm `;` |
| `EMPTY` | Chỉ có whitespace/comment hoặc không có snippet | Không eval; có thể bỏ phần input trống đã xử lý |
| `UNKNOWN` | Phân tích bị cản trở bởi mã lỗi; chưa xác định chắc mức hoàn chỉnh | API **coi là complete** để `eval` có cơ hội phát diagnostics; không xem đây là bằng chứng code đúng |

Các giá trị `DEFINITELY_INCOMPLETE`, `CONSIDERED_INCOMPLETE` và `EMPTY` là **chưa hoàn chỉnh** theo `isComplete()`. Ngược lại, `UNKNOWN` được coi là hoàn chỉnh nhằm để engine báo lỗi chính xác hơn. Vì vậy:

~~~java
// Quy tắc thường dùng cho một REPL có quyền đánh giá đầu vào:
if (info.completeness().isComplete()) {
    jshell.eval(info.source());
}
~~~

Đoạn này chỉ minh họa điều kiện, **chưa xử lý phần remaining, whitespace, diagnostics hay policy bảo mật**. Ví dụ runnable ở mục 5 sẽ xử lý đầy đủ các phần ấy.

Hai trường hợp hay gặp:

- `"class Counter {"` hoặc `"int x ="`: còn thiếu cú pháp bắt buộc; cần thêm dòng.
- `"1 + 2"`: có thể hoàn chỉnh bằng cách bổ sung `;`. `source()` sẽ chứa mã hoàn chỉnh để eval nếu policy cho phép.

Phân tích completeness là một **kiểm tra ranh giới**, không phải trình biên dịch xác nhận kiểu, không phải bước xét quyền hạn và không phải “kiểm tra xem có exception khi chạy hay không”.

## 4. Thuật toán bộ đệm trước eval

Host nên giữ một bộ đệm `pending` riêng cho mỗi phiên JShell. Mỗi lần nhận thêm một dòng hoặc batch, host thực hiện:

1. **Append** phần nguồn mới vào `pending`, giữ nguyên newline nếu ghép các dòng. Không gửi riêng một dòng đầu tiên của method/class cho `eval`.
2. Gọi `analyzeCompletion(pending)`; nếu completeness là `EMPTY` thì dọn phần whitespace/comment không còn snippet; nếu chưa complete thì giữ buffer để chờ.
3. Nếu complete, lấy **`info.source()`**, không dùng toàn bộ buffer. Gửi đúng chuỗi đó vào `jshell.eval`.
4. Xử lý **tất cả** `SnippetEvent` trả về: trạng thái `VALID`, `REJECTED`, recoverable statuses, giá trị biểu thức, exception, diagnostics và các thay đổi gián tiếp cần thiết.
5. Gán `pending = info.remaining()` rồi quay về bước 2 để xử lý snippet kế tiếp **trong cùng một batch**.
6. Tránh vòng lặp vô hạn: xác minh mỗi lần tách snippet tiến lên, hạn chế kích thước buffer/số snippet; đóng JShell khi phiên kết thúc.

Các trạng thái `COMPLETE_WITH_SEMI` có thể tự bổ sung chấm phẩy. Điều này **không luôn đúng ý định người dùng** nếu họ còn định nhập toán tử hoặc nối thêm một phần biểu thức. CLI thường quyết định commit khi Enter, nhưng editor nhiều dòng có thể dùng nút Run hoặc Ctrl+Enter để làm ranh giới. Hãy quy định khi nào host cho phép auto-complete bằng `;`. Ví dụ mục 5 dùng input đã có `;` để giữ stdout ổn định.

### Không tự phân tích bằng số lượng ngoặc

Các cách như `source.endsWith(";")`, đếm dấu `{`/`}` hoặc tách bằng `String.split(";")` đều thất bại với mã Java hợp lệ:

~~~java
String s = "};";
// Dấu } và ; ở trên thuộc nội dung string.
for (int i = 0; i < 2; i++) {
    System.out.println(i);
}
~~~

Đây là **hai snippet minh họa**. Câu lệnh `for` có hai dấu `;` bên trong header và chứa method call; không thể tách đầu vào bằng dấu `;` tùy ý. Tương tự, comment, ký tự escape, annotation, generic type, lambda và text block làm việc dựa trên regex càng thiếu tin cậy.

## 5. Ví dụ Java 17 chạy được: phân tích từng dòng trước khi eval

Chương trình dưới đây biên dịch và chạy trên **JDK 17 trở lên có module `jdk.jshell`**. Nó tạo `JShell`, đưa dữ liệu đầu vào theo từng lần gọi, chờ method đủ dấu `}`, tách hai snippet trên cùng một dòng, và in trạng thái/giá trị mà engine trả về. Chỉ `source()` của một snippet hoàn chỉnh mới được eval.

### 5.1. Tạo file và cấu trúc

~~~text
jshell-completion-demo/
  src/
    CompletionGateDemo.java
  out/              (tạo khi biên dịch)
~~~

**File `src/CompletionGateDemo.java`:**

~~~java
import java.util.List;
import jdk.jshell.JShell;
import jdk.jshell.Snippet;
import jdk.jshell.SnippetEvent;
import jdk.jshell.SourceCodeAnalysis;

public final class CompletionGateDemo {
    private CompletionGateDemo() {
    }

    public static void main(String[] args) {
        try (JShell shell = JShell.create()) {
            SourceCodeAnalysis analysis = shell.sourceCodeAnalysis();
            StringBuilder pending = new StringBuilder();

            List<String> lines = List.of(
                    "int square(int x) {",
                    "    return x * x;",
                    "}",
                    "square(4); int n = 7;",
                    "n + square(2);"
            );

            for (String line : lines) {
                accept(line, pending, shell, analysis);
            }

            if (!pending.toString().isBlank()) {
                System.out.println("incomplete input at EOF");
            }
        }
    }

    private static void accept(
            String line,
            StringBuilder pending,
            JShell shell,
            SourceCodeAnalysis analysis) {

        pending.append(line).append('\n');

        while (true) {
            SourceCodeAnalysis.CompletionInfo info =
                    analysis.analyzeCompletion(pending.toString());
            SourceCodeAnalysis.Completeness state =
                    info.completeness();

            if (state == SourceCodeAnalysis.Completeness.EMPTY) {
                pending.setLength(0);
                return;
            }

            if (!state.isComplete()) {
                System.out.println("waiting");
                return;
            }

            String snippet = info.source();
            String rest = info.remaining();
            if (snippet == null || snippet.isBlank()) {
                throw new IllegalStateException(
                        "Analyzer returned an empty complete snippet");
            }
            if (rest == null) {
                rest = "";
            }
            if (rest.equals(pending.toString())) {
                throw new IllegalStateException(
                        "No progress while extracting a snippet");
            }

            pending.setLength(0);
            pending.append(rest);

            for (SnippetEvent event : shell.eval(snippet)) {
                // Các event phụ có causeSnippet != null.
                if (event.causeSnippet() != null) {
                    continue;
                }

                System.out.println("status=" + event.status());
                if (event.value() != null) {
                    System.out.println("value=" + event.value());
                }
                if (event.exception() != null) {
                    System.out.println(
                            "exception=" +
                            event.exception().getClass().getSimpleName());
                }
                if (event.status() == Snippet.Status.REJECTED) {
                    shell.diagnostics(event.snippet())
                            .forEach(d -> System.err.println(
                                    "diagnostic=" + d.getMessage(null)));
                }
            }
        }
    }
}
~~~

**Vì sao đoạn code tách đúng?**

- `pending` giữ các dòng liên tiếp của method cho đến khi `analyzeCompletion` trả một trạng thái `isComplete() == true`.
- `info.source()` là snippet **đã được parser xác định**; `eval` không nhận nguyên `pending` chứa nhiều snippet.
- `info.remaining()` được giữ và phân tích tiếp trong vòng `while`, vì dòng thứ tư chứa cả `square(4);` và `int n = 7;`.
- `EMPTY` được dùng để dọn whitespace còn sót sau khi tiêu thụ hết snippet.
- `isComplete()` cho phép `UNKNOWN` đi tới `eval` để báo lỗi. Trong hệ thống sản xuất, có thể từ chối trước khi chạy tùy chính sách nhưng không nên gọi `UNKNOWN` là “đã biên dịch hợp lệ”.
- `SnippetEvent` có thể biểu diễn thay đổi phụ thuộc; demo chỉ in event gốc (`causeSnippet() == null`). Công cụ cần hiển thị mọi thay đổi nên không bỏ các event phụ như vậy.
- `try (JShell shell = ...)` đóng phiên JShell khi hoàn tất, tránh giữ engine và execution resources vượt vòng đời ứng dụng.

### 5.2. Biên dịch và chạy

Mở terminal trong thư mục `jshell-completion-demo`, đã tạo file nguồn trên:

~~~bash
mkdir -p out
javac --release 17 -encoding UTF-8 \
  -d out src/CompletionGateDemo.java
java -cp out CompletionGateDemo
~~~

Nếu môi trường compiler/launcher tối giản không tự resolve module `jdk.jshell`, cần đảm bảo runtime image có module này và cấu hình root modules phù hợp (ví dụ cờ `--add-modules jdk.jshell` cho launcher); trên JDK 17 đầy đủ, ví dụ chạy theo lệnh trên.

**Stdout khi các snippet hoàn chỉnh và không có lỗi:**

~~~text
waiting
waiting
status=VALID
status=VALID
value=16
status=VALID
value=7
status=VALID
value=11
~~~

Hai dòng `waiting` tương ứng sau `"int square(int x) {"` và `"return x * x;"`: method còn thiếu dấu `}`. Dòng `"}"` làm method hoàn chỉnh nên engine định nghĩa method với status `VALID`. Dòng chứa hai snippet khiến vòng `while` eval chúng **tách biệt**, tạo giá trị `16` cho `square(4)` và `7` cho biến `n`. Lần cuối tính `n + square(2) = 7 + 4 = 11`.

Đây là stdout cho đúng source và input demo, **không phải** một cam kết mọi đoạn Java đều tạo một event duy nhất. Trong thực tế, cập nhật một khai báo có thể kích hoạt thêm event phụ; khi có lỗi có thể có diagnostics/exception hoặc status không phải `VALID`.

### 5.3. Trình tự phân tích theo từng lượt

| Input mới | Trạng thái kỳ vọng | Gọi eval? | Buffer còn lại |
| --- | --- | --- | --- |
| `int square(int x) {` | `DEFINITELY_INCOMPLETE` | Không | Giữ dòng đầu |
| `return x * x;` | Vẫn thiếu thân method kết thúc | Không | Giữ cả hai dòng |
| `}` | `COMPLETE` | Có: method definition | Không còn snippet |
| `square(4); int n = 7;` | Hai snippet hoàn chỉnh liên tiếp | Có: **hai lần eval** | Không còn snippet |
| `n + square(2);` | `COMPLETE` | Có: expression | Không còn snippet |

Một chi tiết quan trọng: thứ tự eval theo đúng thứ tự snippet giúp khai báo `n` đã tồn tại trước khi đánh giá `n + square(2)`. Nếu gọi `eval` trên cả block hoặc thay đổi thứ tự, kết quả khác và có thể gây lỗi.

## 6. Thêm một ví dụ riêng: kiểm tra mức hoàn chỉnh mà không eval

Khi thiết kế editor, UI có thể muốn hiển thị trạng thái “cần nhập tiếp” mà chưa chạy mã. Một chương trình nhỏ (độc lập với mục 5) có thể chỉ dùng `SourceCodeAnalysis`:

**File `src/InspectCompletion.java`:**

~~~java
import jdk.jshell.JShell;
import jdk.jshell.SourceCodeAnalysis;

public final class InspectCompletion {
    public static void main(String[] args) {
        try (JShell shell = JShell.create()) {
            SourceCodeAnalysis analysis = shell.sourceCodeAnalysis();
            for (String source : new String[] {
                    "int x =",
                    "int x = 10;",
                    "x + 2"
            }) {
                SourceCodeAnalysis.CompletionInfo info =
                        analysis.analyzeCompletion(source);
                System.out.println(
                        "complete=" + info.completeness().isComplete()
                        + ", state=" + info.completeness());
            }
        }
    }
}
~~~

Chạy trong cùng thư mục demo, sau khi tạo file:

~~~bash
javac --release 17 -encoding UTF-8 -d out src/InspectCompletion.java
java -cp out InspectCompletion
~~~

**Stdout kỳ vọng:**

~~~text
complete=false, state=DEFINITELY_INCOMPLETE
complete=true, state=COMPLETE
complete=true, state=COMPLETE_WITH_SEMI
~~~

`"int x ="` cần một biểu thức phía sau, dấu `;` không đủ. `"int x = 10;"` là khai báo hoàn chỉnh. `"x + 2"` là biểu thức có thể được hoàn tất bằng dấu chấm phẩy mà không thay đổi cú pháp bên trong; đây là kiểm tra ranh giới, **không có ý nghĩa biến x đã tồn tại**, vì chương trình này không bao giờ gọi `eval`.

Khi viết kiểm thử, nên kiểm tra thêm `source()` (ví dụ trường hợp `COMPLETE_WITH_SEMI` đã được thêm `;`) và `remaining()` cho input có hai snippet. Đừng dựa vào việc đọc status mà bỏ qua hai trường còn lại.

## 7. Phân biệt hoàn chỉnh, hợp lệ và an toàn

Ba tính chất này không tương đương:

1. **Complete:** parser nhận ra ranh giới snippet; code đã đủ cấu trúc để đưa cho JShell đánh giá.
2. **Semantically valid:** code được JShell biên dịch/chấp nhận trong trạng thái hiện tại (import, biến, classpath, method có phù hợp). `analyzeCompletion` không xác thực toàn bộ điều đó.
3. **Safe to execute:** mã được phép chạy theo chính sách ứng dụng. Code Java “đúng” vẫn có thể ghi file, mở mạng, fork thread, tiêu tốn CPU hoặc gọi mã bên ngoài.

Ví dụ:

~~~java
missingMethod(42);
~~~

Đây là **một snippet hoàn chỉnh về cấu trúc** nhưng có thể bị JShell từ chối vì `missingMethod` chưa được định nghĩa. Khi đó cần kiểm tra `SnippetEvent.status() == REJECTED` và `jshell.diagnostics(snippet)` để giải thích lỗi cho người dùng; không “chữa” bằng cách thêm dấu chấm phẩy hoặc chờ thêm input.

Ví dụ khác:

~~~java
while (true) {
    // vòng lặp không kết thúc nếu không bị dừng bởi môi trường thực thi
}
~~~

Đây cũng là mã hoàn chỉnh về mặt cú pháp, nhưng nếu thực thi có thể treo. Host cần kiểm soát timeout, giới hạn tài nguyên, cancellation và isolation phù hợp. `SourceCodeAnalysis` **không phải bộ lọc bảo mật**, JShell **không phải sandbox** cho mã không tin cậy. Đừng tự động eval mọi request HTTP chỉ vì `isComplete()` trả true.

Một số hành vi runtime cần nhớ:

- `JShell.eval` có thể ném `IllegalStateException` nếu shell đã đóng. Code trong snippet có thể ném exception được ghi qua `SnippetEvent.exception()` hoặc khiến execution engine bị reset/terminate tùy tình huống.
- Khai báo bị lỗi vẫn có thể sinh event `REJECTED` hoặc trạng thái recoverable nếu một số dependency chưa giải quyết được. Không suy luận “eval đã được gọi” nghĩa là code đã chạy thành công.
- Nếu snippet sửa một definition cũ, JShell có thể tạo event `OVERWRITTEN` hoặc thay đổi trạng thái các snippet phụ thuộc; công cụ cần cập nhật lại biểu diễn trạng thái sau tất cả event.
- Các lệnh `/exit`, `/list`, `/imports` là **command của CLI jshell**, không phải Java source snippet để đưa trực tiếp cho `JShell.eval`. Host tự thiết kế bộ xử lý lệnh riêng nếu muốn hỗ trợ cú pháp slash-command.
- JShell snippet không hoàn toàn đồng nghĩa một file `.java` có `package` và nhiều top-level declarations. Khi nhận cả file, cân nhắc Java Compiler API thay vì giả định `eval` có thể xử lý nguyên file như một compilation unit.

## 8. Trường hợp cạnh và lỗi khi tích lũy đầu vào

### 8.1. Chỉ có whitespace hoặc comment

Nếu input chỉ chứa khoảng trắng/comment, completeness có thể là `EMPTY`. Host không nên gửi `eval("")` cho một lời gọi nghiệp vụ. Có thể xóa phần input không tạo snippet theo policy hoặc giữ comment nếu editor cần tái hiện văn bản gốc. Trong ví dụ, `EMPTY` làm rỗng buffer.

### 8.2. Code còn dang dở khi kết thúc phiên

Nếu người dùng gửi:

~~~java
class Report {
    int total() {
~~~

và kết thúc input, host phải báo **snippet chưa hoàn chỉnh**, không lặng lẽ bỏ buffer và cũng không tự thêm dấu `}`. Ví dụ `CompletionGateDemo` báo `incomplete input at EOF` nếu buffer còn nội dung không phải whitespace. Trong ứng dụng thật, có thể hỏi bổ sung dòng hoặc cho người dùng lưu lại draft.

### 8.3. Semicolon tự bổ sung

Nếu input là `"1 + 2"`, trạng thái `COMPLETE_WITH_SEMI` cho biết nguồn có thể hoàn chỉnh nếu thêm dấu `;`. `info.source()` sẽ trả snippet thích hợp để eval, không nên nối thêm một dấu chấm phẩy thứ hai một cách mù quáng.

Đối với editor hỗ trợ multiline, chính sách có thể yêu cầu người dùng bấm **Run** mới cho phép auto-semi; còn Enter thông thường chỉ xuống dòng để tiếp tục viết. Tránh eval quá sớm biểu thức mà người dùng định nối thêm toán tử.

### 8.4. UNKNOWN không phải “đúng”

`UNKNOWN` được xem là complete trong `isComplete()` để `eval` có thể cung cấp lỗi. Nếu host muốn tránh thực thi code không rõ nguồn gốc, nó có thể chọn báo lỗi/gửi vào môi trường cô lập thay vì eval. Nhưng không nên giải thích trạng thái này là “đúng cú pháp”.

### 8.5. Chuỗi và text block chứa delimiter

Cú pháp Java cho phép `;`, `{`, `}` nằm trong string literal và text block. Parser biết ranh giới token, còn phép cắt dựa trên `indexOf(';')` không phân biệt được. Với text block (Java 17), dấu `"""` còn có thể trải qua nhiều dòng; bộ đệm phải giữ newline đúng nguyên bản.

### 8.6. Nhiều snippet và lỗi ở snippet giữa

Một batch có thể gồm `"int a = 1; missingMethod(); int b = 2;"`. Mỗi phần phải được tách riêng bằng `source()`/`remaining()`. Nếu snippet thứ hai bị `REJECTED`, chính sách của host quyết định **tiếp tục** đánh giá snippet thứ ba hay dừng batch tại lỗi. Đừng vô thức coi `eval` của cả batch là một transaction nguyên tử: JShell đã có thể lưu thay đổi từ snippet trước lỗi.

### 8.7. Đa phiên và đồng thời

Không chia sẻ một buffer `pending` giữa các người dùng/phiên khác nhau. Mỗi phiên sở hữu một `JShell`, analyzer và buffer riêng (hoặc có cơ chế đồng bộ/chia tách rõ ràng). Tránh hai thread đồng thời sửa cùng `StringBuilder` rồi gọi `eval` theo thứ tự không xác định. Nếu cần nhiều người dùng, hãy có hàng đợi/điều phối cho từng shell, timeout và cơ chế hủy rõ ràng.

### 8.8. Giới hạn dữ liệu đầu vào và số lần lặp

Không để `pending` tăng vô hạn khi người dùng gửi một khai báo chưa đóng ngoặc. Đặt giới hạn byte/ký tự theo chính sách, số snippet tối đa mỗi request và thời gian thực thi. Sau khi hoàn tất, `JShell.close()` để thu hồi tài nguyên engine; đừng lưu `SnippetEvent`/`ClassLoader`/context vượt vòng đời phiên nếu không có lý do.

## 9. Kiểm thử và checklist

Bộ kiểm thử cho host dùng `SourceCodeAnalysis` trước `eval` nên bao gồm:

| Input | Điều cần xác minh |
| --- | --- |
| Method/class qua nhiều dòng | Không eval khi chưa đủ đóng ngoặc; eval đúng một lần khi complete |
| Hai khai báo trên một dòng | Hai lần tách và eval đúng thứ tự, không gộp thành một snippet |
| Biểu thức không có dấu `;` cuối | Trạng thái `COMPLETE_WITH_SEMI` và chính sách auto-semi rõ ràng |
| Statement chỉ có `;` cuối nhưng còn thiếu operand | Không hiểu nhầm đã hoàn chỉnh khi parser báo chưa đủ |
| Whitespace, comment | Không đánh giá một snippet rỗng |
| Chuỗi/text block chứa `;` hoặc `}` | Không cắt nhầm token bằng phép tìm ký tự |
| Mã sai kiểu hoặc tên method không tồn tại | Completion không thay thế diagnostics từ `eval` |
| `UNKNOWN` | Không gắn nhãn “mã đúng” chỉ vì `isComplete` trả true |
| Batch nhiều snippet, snippet giữa bị lỗi | Ranh giới chính xác, chính sách tiếp tục/dừng rõ ràng |
| Đầu vào dở dang tại EOF | Báo incomplete và giữ/chuyển cho người dùng bổ sung |
| Nhiều người dùng hoặc thread | Phân tách session/buffer, thứ tự eval nhất quán |
| Mã không tin cậy hoặc vòng lặp vô hạn | Có policy/giới hạn thực thi riêng, không dựa vào parser |

Checklist áp dụng cho code production:

- [ ] Lấy `SourceCodeAnalysis` từ chính `JShell` đang dùng.
- [ ] Tích lũy source cho tới khi `completeness().isComplete()` theo policy; xử lý `EMPTY` và `UNKNOWN` đúng nghĩa.
- [ ] Dùng `info.source()` cho một lần `eval`, không tự tách bằng regex/dấu chấm phẩy.
- [ ] Lặp với `info.remaining()` để không bỏ snippet còn lại trong batch.
- [ ] Xử lý status, value, exception và diagnostics của `SnippetEvent`; không giả định tất cả đều VALID.
- [ ] Không coi completeness là type-checking hay security screening.
- [ ] Đặt giới hạn buffer, snippet count, execution time; bảo đảm ranh giới lifecycle/session.
- [ ] Đóng `JShell` và các tài nguyên kèm theo khi kết thúc.

**Kết luận:** Trong JShell nhúng, `eval` là bước **đánh giá** một snippet, không phải một bộ tích lũy các dòng source tùy ý. `SourceCodeAnalysis.analyzeCompletion` quyết định lúc nào đã có **snippet đầu tiên hoàn chỉnh**, `source()` cho đúng mã cần eval và `remaining()` cho phần phải phân tích tiếp. Dùng bộ đệm, enum completeness và event diagnostics đúng cách giúp một ứng dụng REPL chạy ổn định với input đa dòng và nhiều snippet, đồng thời giữ rõ ranh giới giữa phân tích cú pháp, biên dịch và thực thi.

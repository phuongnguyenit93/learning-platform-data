# Đóng phiên JShell và phân biệt môi trường REPL với hợp đồng plugin ổn định

**JShell nhúng** cho phép một chương trình Java tạo phiên Read–Eval–Print Loop (REPL) bằng API **jdk.jshell.JShell**, gửi vào các đoạn mã (snippet) và nhận kết quả/diagnostics theo từng lượt. Đây là công cụ rất hiệu quả để khám phá API, minh họa kiến thức, thử thuật toán hoặc xây dựng console tương tác. Tuy nhiên, vòng đời của một phiên JShell khác căn bản với vòng đời của một **plugin đã đóng gói và phát hành theo hợp đồng ổn định**.

Bài này tập trung vào hai câu hỏi thực hành: **đóng một phiên JShell như thế nào để giải phóng tài nguyên đúng lúc?** và **tại sao không nên lấy trạng thái snippet đang hoạt động trong REPL làm giao diện plugin production?** Ta sẽ thực nghiệm trên Java 17+, xây một plugin JAR với interface SPI rõ ràng để so sánh, rồi xác định những ranh giới an toàn cho host.

## 1. JShell nhúng thực sự giữ những gì?

Khi gọi JShell.create() hoặc JShell.builder().build(), host tạo một **JShell state engine**. Mỗi phiên nắm giữ:

- **Source state:** các khai báo import, biến, phương thức, kiểu dữ liệu và những snippet khác đã được đánh giá.
- **Compilation state:** liên hệ giữa các snippet, trạng thái biên dịch/khả năng phân giải tên, diagnostics và sự thay thế khai báo.
- **Execution state:** môi trường chạy biểu thức/statement và những giá trị hoặc side effect do mã đã thực thi tạo ra.
- **Tài nguyên vận hành:** bộ máy JShell, cơ chế thực thi mã, đối tượng listener/subscription và những tham chiếu liên quan. Cấu hình thực thi mặc định thường dùng môi trường riêng cho mã snippet, nhưng không được suy thành sandbox bảo mật.

Một snippet **không giống một file .java hoàn chỉnh**, và một phiên JShell **không giống JAR plugin**. JShell cho phép từng expression, statement hoặc declaration được đánh giá qua eval(String). Một lời gọi eval nên chứa **một complete snippet**. Nếu nhận văn bản tùy ý gồm nhiều snippet, hãy dùng SourceCodeAnalysis.analyzeCompletion(...) để chia ranh giới một cách có chủ đích.

Ví dụ, trong cùng một phiên:

~~~java
// Các câu lệnh minh họa, giả định shell là một JShell đang mở:
shell.eval("int width = 6;");
shell.eval("int area(int height) { return width * height; }");
shell.eval("area(7)");
~~~

Lượt gọi thứ ba dùng được width và area vì chúng đang thuộc cùng phiên. Nếu tạo **một JShell khác**, các khai báo này không tự xuất hiện ở phiên mới. Nếu khai báo width hoặc area bị ghi đè hoặc drop, các snippet phụ thuộc cũng có thể đổi trạng thái.

**REPL cho phép thử và sửa liên tục**; hợp đồng plugin ổn định cần biết rõ tên interface, kiểu tham số, kiểu trả về, phiên bản, quy tắc nạp và trách nhiệm tài nguyên ngay cả khi triển khai đã được thay bằng bản mới.

## 2. Vòng đời đúng: create → eval/query → close

Trong Java 17, **JShell implements AutoCloseable**. API hướng dẫn gọi close() khi không còn cần state engine để giải phóng tài nguyên. Cách ưu tiên là dùng **try-with-resources**, thay vì trông chờ garbage collector:

~~~java
import jdk.jshell.JShell;

try (JShell shell = JShell.create()) {
    shell.eval("int result = 2 + 3;");
    // Đọc events hoặc diagnostics trong lúc phiên còn mở.
}
// close() được gọi khi ra khỏi block.
~~~

Đây là ví dụ cấu trúc; đoạn hoàn chỉnh có class và main ở phần 4.

Vòng đời nên được hiểu như sau:

~~~text
NEW
 |
 | JShell.create() / JShell.builder().build()
 v
OPEN SESSION
 |  eval(), drop(), status(), diagnostics()
 |  khai báo/biểu thức có thể làm thay đổi state
 |  snippet có thể bị REJECTED hoặc được ghi đè
 |
 +---- close() / ra khỏi try-with-resources ----+
 |                                               |
 v                                               v
CLOSED                                     release resources
 |
 | eval() sau close()
 v
IllegalStateException
~~~

**close() không chỉ là xóa một biến Java**: nó kết thúc state engine và yêu cầu giải phóng tài nguyên. Một biến tham chiếu giữ giá trị Java của đối tượng đã đóng vẫn không khiến phiên có thể sử dụng trở lại. Ví dụ, eval(String) trên JShell đã đóng ném **IllegalStateException**.

Ngược lại, **drop(Snippet) không đóng phiên**. Nó chỉ làm một khai báo đang hoạt động không còn hoạt động và cập nhật những snippet phụ thuộc. JShell vẫn có thể nhận eval mới sau drop(). Việc đóng state engine không phải một "drop tất cả snippet rồi bắt đầu lại"; muốn có môi trường mới, hãy tạo một JShell instance mới và xây dựng lại state theo chính sách của host.

Trong thực tế, một phiên cũng có thể kết thúc **trước khi host chủ động gọi close**, chẳng hạn môi trường thực thi mã snippet từ xa bị kết thúc. Vì thế host phải xử lý trạng thái phiên bất thường, không chỉ happy path.

## 3. Những sự kiện và trạng thái không nên nhầm với plugin API

**JShell.eval(String)** trả về **List<SnippetEvent>**. Mỗi event mô tả thay đổi khi biên dịch/thực thi snippet hoặc do snippet khác phụ thuộc vào nó. Một lần eval có thể gây **nhiều event**, không nên viết code tổng quát luôn giả định list chỉ có một phần tử.

Những khái niệm cần phân biệt:

| Thành phần | Điều nó biểu diễn | Lưu ý thiết kế |
| --- | --- | --- |
| Snippet | Source snippet thuộc một JShell instance | Không phải hợp đồng Java SPI để chia sẻ giữa phiên |
| Snippet.Status.VALID | Snippet hợp lệ, định nghĩa/kết quả đang có hiệu lực theo state | Có thể thay đổi sau lần eval/drop khác |
| Snippet.Status.REJECTED | Snippet không được chấp nhận | Xem diagnostics, không coi là lỗi khởi động plugin |
| Snippet.Status.RECOVERABLE_DEFINED / RECOVERABLE_NOT_DEFINED | Một khai báo có lỗi phụ thuộc chưa giải quyết và có thể được hồi phục theo điều kiện | Không có nghĩa plugin đã deploy thành công |
| Snippet.Status.OVERWRITTEN | Khai báo cũ đã bị khai báo mới ghi đè | Cần tránh phụ thuộc ngầm vào định nghĩa cũ |
| Snippet.Status.DROPPED | Khai báo bị loại khỏi source state | Không tương đương JShell.close() |
| SnippetEvent.value() | Chuỗi hiển thị kết quả nếu event có giá trị | Có thể null; không phải DTO có kiểu và schema ổn định |
| SnippetEvent.exception() | Ngoại lệ do mã snippet ném trong execution | Khác lỗi biên dịch, cần ghi nhận riêng |
| shell.diagnostics(snippet) | Diagnostic của lần đánh giá snippet gần nhất | Không giống stdout/stderr của mã đã chạy |
| shell.status(snippet) | Trạng thái hiện tại của snippet trong phiên | Khác status ghi lại ở một event cũ |

Ví dụ một biến bị khai báo lại trong REPL có thể khiến snippet đầu mang trạng thái OVERWRITTEN, còn khai báo mới VALID. Một người dùng sửa kiểu trả về của một phương thức ngay trong phiên mà không tái phát hành interface JAR; đó là hành vi hỗ trợ **thử nghiệm**, chứ không phải cơ chế bảo đảm compatibility cho plugin consumer.

**Không truyền object Snippet hoặc SnippetEvent như một API ổn định cho plugin khác.** Chúng gắn với state engine cụ thể, chứa ngữ nghĩa của một phiên REPL, và không đại diện cho artifact có version/ABI rõ ràng.

## 4. Lab Java 17+: đóng phiên ngay cả khi có lỗi snippet

Chương trình sau dùng đúng một file Java, tạo JShell, gửi snippet đúng và sai, kiểm tra drop(), đóng phiên qua try-with-resources, xác nhận eval() bị từ chối sau close, rồi tạo phiên độc lập mới. Mục tiêu là quan sát vòng đời, **không thực thi mã Java không tin cậy**.

Tạo file **EmbeddedJshellLifecycle.java**:

~~~java
import jdk.jshell.JShell;
import jdk.jshell.SnippetEvent;

public final class EmbeddedJshellLifecycle {
    public static void main(String[] args) {
        JShell shell = JShell.create();

        // Java 9+ cho phép dùng biến effectively final trong try-with-resources.
        try (shell) {
            SnippetEvent defined = shell.eval("int factor = 7;").get(0);
            System.out.println("defined=" + defined.status());

            SnippetEvent value = shell.eval("factor * 6").get(0);
            System.out.println("value=" + value.value());

            SnippetEvent bad = shell.eval("int broken = ;").get(0);
            System.out.println("invalid=" + bad.status());
            System.out.println("diagnostic="
                    + (shell.diagnostics(bad.snippet()).count() > 0));

            // Xóa một khai báo; không kết thúc toàn bộ phiên.
            shell.drop(defined.snippet());
            System.out.println("dropped="
                    + shell.status(defined.snippet()));
        }

        boolean rejectedAfterClose = false;
        try {
            shell.eval("1 + 1");
        } catch (IllegalStateException expected) {
            rejectedAfterClose = true;
        }
        System.out.println("closed-eval-error=" + rejectedAfterClose);

        try (JShell fresh = JShell.create()) {
            System.out.println("fresh-variables="
                    + fresh.variables().count());
        }
    }
}
~~~

Biên dịch và chạy bằng **JDK 17+**:

~~~bash
javac --add-modules jdk.jshell -encoding UTF-8 EmbeddedJshellLifecycle.java
java --add-modules jdk.jshell EmbeddedJshellLifecycle
~~~

**Stdout kỳ vọng** trong môi trường JDK 17 có thể khởi tạo JShell execution engine bình thường:

~~~text
defined=VALID
value=42
invalid=REJECTED
diagnostic=true
dropped=DROPPED
closed-eval-error=true
fresh-variables=0
~~~

**Giải thích từng dòng:**

1. Định nghĩa int factor = 7; hợp lệ nên event trả trạng thái VALID.
2. Biểu thức factor * 6 dùng state phiên hiện hành và cho giá trị chuỗi **42**. Chuỗi này phục vụ hiển thị, không được coi là một object Integer đã đi qua hợp đồng plugin.
3. int broken = ; không hợp lệ về cú pháp, bị REJECTED. Đọc diagnostics trong khi shell còn mở cho thấy ít nhất một diagnostic.
4. drop(defined.snippet()) chuyển khai báo factor sang DROPPED trong phiên. Các snippet khác không nhất thiết bị xóa cùng lúc; trạng thái phụ thuộc sẽ được cập nhật theo quy tắc JShell.
5. Khi ra khỏi block try (shell), close() chạy dù các thao tác bên trong trả bình thường hay ném ngoại lệ trong điều kiện Java thực thi finally/close thông thường.
6. Thử eval sau close gặp IllegalStateException; chương trình bắt đúng loại lỗi này và in true.
7. Phiên fresh mới không có biến active của phiên cũ. Việc tạo JShell khác không "mở lại" state đã đóng.

**Điều kiện quan trọng:** nếu execution engine không khởi tạo được, process bị lỗi hoặc môi trường thực thi snippet bị kết thúc sớm, output có thể khác. Kịch bản trên là lab hợp lệ trên JDK 17 thông thường, không phải cam kết rằng mọi môi trường bị giới hạn quyền hoặc đang quá tải đều chạy được.

### 4.1. Vì sao phải đọc kết quả trước khi đóng?

Một số thao tác như shell.status(snippet), shell.diagnostics(snippet), shell.varValue(...) và shell.eval(...) cần một state engine còn mở. Sau close, các truy vấn/đánh giá phụ thuộc state có thể báo IllegalStateException. Do đó flow thực tế nên:

1. Gửi snippet;
2. Thu thập những SnippetEvent, diagnostics và giá trị cần lưu khi phiên còn mở;
3. Chuẩn hóa kết quả thành DTO thuộc API của host;
4. Đóng JShell;
5. Trả DTO đã chuẩn hóa cho caller.

Không dựa vào việc giữ Snippet object rồi khi client gọi API nhiều phút sau mới truy vấn JShell để diễn giải. Khi phiên đã đóng, hãy giữ dữ liệu kết quả cần thiết **bằng giá trị**, không giữ tham chiếu đến state engine.

### 4.2. Tách lỗi biên dịch với lỗi chạy mã

Một snippet có thể là REJECTED do lỗi cú pháp/type-check, không ném exception từ code người dùng. Ngược lại, một snippet biên dịch hợp lệ nhưng thực thi ném ngoại lệ; khi ấy **SnippetEvent.exception()** có thể cho biết exception thuộc môi trường JShell. Việc JShell.eval(...) trả danh sách event thành công **không tự động có nghĩa mỗi snippet thực thi thành công**.

Chương trình test production nên kiểm tra status, exception, diagnostics và kết quả một cách độc lập. Cũng phải xét nhiều event gián tiếp nếu khai báo mới ghi đè khai báo cũ.

## 5. Quản lý close() trong mã nhúng thật

### 5.1. try-with-resources được ưu tiên

Đối với phiên dùng trong một request hoặc một thao tác ngắn:

~~~java
// Mã minh họa: không phải chương trình độc lập.
try (JShell session = JShell.create()) {
    var events = session.eval(sourceSnippet);
    return normalize(events, session);
}
~~~

Hàm normalize cần biến dữ liệu JShell thành loại dữ liệu do host kiểm soát khi session còn mở. Khi return diễn ra, try-with-resources vẫn gọi close trước khi kết quả được giao cho caller.

Nếu framework không thể dùng try-with-resources vì phiên sống qua nhiều tương tác, host phải có owner rõ ràng và điểm kết thúc rõ ràng. Ví dụ:

~~~java
// Mã minh họa: sessionOwner có trách nhiệm đóng chính phiên này.
JShell session = JShell.create();
try {
    sessionOwner.register(session);
    sessionOwner.serveUntilFinished(session);
} finally {
    sessionOwner.unregister(session);
    session.close();
}
~~~

Mẫu trên giả định register/serveUntilFinished/unregister đã được định nghĩa. Trong hệ thống thật, nếu unregister() ném lỗi, dòng session.close() ở cùng finally có thể không chạy; nên ưu tiên owner AutoCloseable và thiết kế cleanup nhiều resource có thứ tự, cô lập lỗi đúng cách.

### 5.2. close() khác drop(), stop() và hủy request

- **drop(Snippet)**: thay đổi trạng thái khai báo, phục vụ phiên đang mở.
- **stop()**: thử dừng việc thực thi đang diễn ra. Theo JDK API, đây là nỗ lực tốt nhất; có trường hợp thất bại, ví dụ mã bị chặn I/O hoặc xử lý cách ngắt.
- **close()**: đóng state engine, giải phóng tài nguyên; nên là điểm kết thúc vòng đời khi không cần phiên.
- **Future.cancel(true)** nếu host chạy eval trên worker thread: chủ yếu yêu cầu interrupt, không phải lệnh cưỡng chế dừng mọi execution engine.
- **Hủy process/container do host sở hữu**: ranh giới mạnh hơn khi cần giới hạn thời gian hoặc memory cho mã không tin cậy; cũng cần thu dọn process tree, filesystem và IPC.

**Đừng chỉ gọi stop() hoặc drop() rồi xem như đã đóng phiên.** Đối với session pool, cần đánh dấu state không dùng lại, hủy callback/task còn hoạt động và đóng phiên thật trước khi giải phóng slot. Nếu có user code treo, một lệnh close/stop không thay thế chính sách isolation và watchdog thích hợp.

### 5.3. Subscription và callback

JShell cho phép đăng ký listener qua onSnippetEvent(...) và onShutdown(...). onShutdown báo khi một phiên chấm dứt, kể cả tình huống do execution environment kết thúc ngoài ý muốn. Các phương thức đăng ký trả về **JShell.Subscription**; host có thể unsubscribe(token) khi không cần quan sát nữa.

Mã minh họa:

~~~java
// Giả định shell đang mở và log là logger của host.
JShell.Subscription subscription =
        shell.onSnippetEvent(event -> log(event.status()));
try {
    shell.eval("int n = 1;");
} finally {
    shell.unsubscribe(subscription);
}
~~~

Đây là mã có biến log giả định, không phải ví dụ độc lập. Đăng ký callback không đồng nghĩa bắt đầu một "plugin runtime" ổn định. Callback có thể giữ tham chiếu tới object của host; hủy subscription và kết thúc phiên theo ownership giúp giảm nguy cơ lưu giữ tham chiếu không cần thiết.

### 5.4. Không chia sẻ phiên JShell giữa thread một cách tùy tiện

Tài liệu JDK 17 nói **JShell không thread-safe**, trừ những phương thức được chỉ rõ ngoại lệ. Không để hai request đồng thời gọi eval/drop/close trên cùng session rồi mong thứ tự state có thể dự đoán. Một giải pháp là gán mỗi phiên cho một worker/serial queue duy nhất; lifecycle manager chịu trách nhiệm ngăn request mới khi phiên đang đóng.

Nếu một job bất đồng bộ đang dùng session, đừng đóng nó ngay khi HTTP request timeout mà không phối hợp worker; cần có quy trình hủy, đánh dấu phiên không tái sử dụng, đợi hoặc loại bỏ worker cô lập rồi cleanup. Bộ nhớ, listener, streams và các reference của phiên phải được giải phóng theo một owner.

## 6. REPL và plugin: so sánh theo hợp đồng, không chỉ theo cách gọi mã

Hai cơ chế đều cho phép hành vi xuất hiện sau khi host khởi động, nhưng mục tiêu khác nhau:

| Khía cạnh | JShell/REPL nhúng | Plugin ổn định với SPI/JAR |
| --- | --- | --- |
| Đơn vị nguồn | Snippet (expression, statement, declaration) | Class/module và artifact đã build |
| Thời điểm thay đổi | Trong phiên, eval/drop/ghi đè declaration | Qua phát hành artifact phiên bản mới |
| Hợp đồng public | Thường là state và value được diễn giải | Interface/DTO, chữ ký method, phiên bản API |
| Định danh | Snippet ID/state gắn với một JShell instance | Plugin ID/version + implementation class/module |
| Kiểm tra tương thích | Compilation status trong phiên, dependency của snippets | Compile/runtime compatibility, API version, contract tests |
| Kết quả | SnippetEvent.value() là biểu diễn String tùy trường hợp | Java object/DTO đã định kiểu và có semantics |
| Vòng đời | create → eval/query → close | install → validate → start → serve → stop/unload |
| Phụ thuộc | import, classpath/session setup, state thứ tự lượt | dependency graph và class loader/module layer được quản lý |
| Phát hiện implementation | Gửi source theo thứ tự hoặc chọn snippet | SPI/ServiceLoader, registry hoặc manifest |
| State isolation | State theo phiên, thực thi có thể có side effect | State theo plugin instance/lifecycle được định nghĩa |
| Triển khai lại | Tạo session mới và phát lại source nếu cần | Nạp artifact mới, migrate state nếu hợp đồng yêu cầu |
| Độ tin cậy | Rất tốt cho khám phá và nguyên mẫu | Phù hợp hệ thống tích hợp dài hạn khi contract được kiểm thử |

**Nguyên tắc:** không dùng một loạt String có chứa tên biến/phương thức của JShell làm API plugin production chỉ vì "chạy được ở phiên hiện tại". Phiên phụ thuộc lịch sử eval, classpath và trạng thái runtime; caller khác hoặc phiên mới có thể không có cùng khai báo.

Một kết quả SnippetEvent.value() ví dụ "42" không mang thông tin kiểu/phiên bản cho việc trao đổi thông điệp giữa các thành phần. Nếu cần đưa kết quả ra ngoài, host phải biến thành DTO rõ schema, ví dụ **CompileResult(status, diagnostics, output)** hoặc **EvaluationResult(type, displayText, errors)**. Cần định nghĩa encoding, độ dài, lỗi và hợp đồng tương thích.

## 7. Lab đối chiếu: một plugin classpath có hợp đồng SPI cố định

Để thấy sự khác biệt, ta xây một plugin đơn giản với giao diện Java ổn định. Host không eval các chuỗi code tùy ý, mà gọi **interface MessagePlugin** đã được build trước; implementation và đăng ký service đóng trong một JAR riêng.

### 7.1. Cây file

~~~text
plugin-lab/
├── src/
│   ├── api/demo/api/MessagePlugin.java
│   ├── plugin/demo/plugins/UpperPlugin.java
│   └── host/demo/host/Host.java
├── resources/
│   └── META-INF/services/demo.api.MessagePlugin
├── build/                      (tạo khi biên dịch)
└── dist/                       (tạo khi đóng JAR)
~~~

### 7.2. Hợp đồng SPI mà host và plugin chia sẻ

File **src/api/demo/api/MessagePlugin.java**:

~~~java
package demo.api;

public interface MessagePlugin {
    String id();
    String transform(String input);
}
~~~

Chữ ký của interface là **hợp đồng compile-time và runtime**. Caller biết trước id() và transform(String) và có thể viết test chuẩn. Thay kiểu tham số hoặc kiểu trả về tùy tiện không giống việc redefine một snippet; thay đổi chữ ký có thể phá **binary compatibility** của implementation cũ.

### 7.3. Implementation phát hành dưới dạng JAR

File **src/plugin/demo/plugins/UpperPlugin.java**:

~~~java
package demo.plugins;

import demo.api.MessagePlugin;
import java.util.Locale;

public final class UpperPlugin implements MessagePlugin {
    public UpperPlugin() {}

    @Override
    public String id() {
        return "upper";
    }

    @Override
    public String transform(String input) {
        return input.toUpperCase(Locale.ROOT);
    }
}
~~~

File **resources/META-INF/services/demo.api.MessagePlugin** không có phần mở rộng, chứa đúng một dòng:

~~~text
demo.plugins.UpperPlugin
~~~

Descriptor phải nằm ở gốc JAR. Tên file là **tên đầy đủ của interface dịch vụ**, tên trong file là class provider. Đây là ví dụ SPI trên **classpath**; module path với explicit named modules có thể dùng khai báo uses/provides trong module-info.java, là cơ chế cấu hình khác.

### 7.4. Host tải plugin qua SPI và gọi giao diện ổn định

File **src/host/demo/host/Host.java**:

~~~java
package demo.host;

import demo.api.MessagePlugin;
import java.util.ServiceLoader;

public final class Host {
    public static void main(String[] args) {
        int found = 0;
        for (MessagePlugin plugin :
                ServiceLoader.load(MessagePlugin.class)) {
            if ("upper".equals(plugin.id())) {
                System.out.println("plugin=" + plugin.id());
                System.out.println("result="
                        + plugin.transform("hello"));
                found++;
            }
        }
        System.out.println("matched=" + found);
    }
}
~~~

Host không cần biết class UpperPlugin lúc biên dịch. Nó chỉ biết MessagePlugin, đồng thời công cụ phát hành đảm bảo implementation có thể được tải và tạo theo hợp đồng ServiceLoader classpath (provider public, có public constructor không tham số hợp lệ).

### 7.5. Build và chạy bằng JDK 17+

Từ thư mục gốc **plugin-lab/** dùng shell bash/POSIX:

~~~bash
mkdir -p build/api build/plugin build/host dist

javac --release 17 -encoding UTF-8 -d build/api src/api/demo/api/MessagePlugin.java
jar --create --file dist/api.jar -C build/api .

javac --release 17 -encoding UTF-8 -cp dist/api.jar -d build/plugin src/plugin/demo/plugins/UpperPlugin.java
jar --create --file dist/upper-plugin.jar -C build/plugin . -C resources .

javac --release 17 -encoding UTF-8 -cp dist/api.jar -d build/host src/host/demo/host/Host.java
java -cp "build/host:dist/api.jar:dist/upper-plugin.jar" demo.host.Host
~~~

Stdout **kỳ vọng chính xác** với đúng một descriptor/provider như trên:

~~~text
plugin=upper
result=HELLO
matched=1
~~~

Trên Windows khi gọi Java trong PowerShell/CMD, dấu phân cách classpath là **;** thay cho **:**. Lệnh mkdir -p là cú pháp bash; có thể tạo thư mục trước bằng công cụ của shell Windows nếu không dùng bash.

So sánh với ví dụ JShell ở phần 4: Host ở đây không có call eval(), không lưu SnippetEvent và không phụ thuộc lịch sử người dùng gõ khai báo. Một triển khai mới chỉ có thể thay thế an toàn nếu tuân thủ giao diện đã phát hành, tương thích API và chính sách phiên bản của host. **Runtime extensibility** vẫn có, nhưng được ràng buộc bằng artifact và contract.

**Kiểm tra artifact:** lệnh jar --list --file dist/upper-plugin.jar phải tìm thấy demo/plugins/UpperPlugin.class và META-INF/services/demo.api.MessagePlugin. Không đóng bản sao demo/api/MessagePlugin.class trong plugin JAR của lab; host và plugin dùng cùng API class identity qua classpath chung. Nếu đưa các bản SPI khác nhau vào loader khác nhau, hai type trùng tên chưa chắc tương thích.

## 8. Đường ranh giới hợp lý: JShell để khám phá, plugin để vận hành

Một sản phẩm có thể kết hợp hai cơ chế nhưng không nên nhập nhằng vai trò:

~~~text
Nguồn mã thử nghiệm
      |
      v
JShell sandboxed development environment
      |
      | eval + diagnostics + test nhanh
      v
Quyết định chức năng đã đạt yêu cầu
      |
      | chuyển thành mã nguồn .java/module-info + test
      v
Build/CI → contract tests → artifact versioned JAR
      |
      | kiểm tra chữ ký/nguồn/phụ thuộc và compatibility
      v
Plugin manager / ServiceLoader / ModuleLayer
      |
      | start → invoke public API → stop/unload
      v
Host production
~~~

Trong sơ đồ, "sandboxed development environment" là **môi trường phát triển được cách ly bởi ứng dụng/OS**, không phải một đảm bảo bảo mật được JShell API tự cung cấp. Nếu JShell được nhúng vào hệ thống cho người dùng gửi mã không tin cậy, hãy dùng process/container riêng có quota và policy rõ ràng.

Một cách tích hợp có kiểm soát:

1. Người dùng thử snippet trong một phiên JShell có **định danh phiên**, thời hạn sử dụng và ownership rõ ràng.
2. Host giới hạn input, output, concurrency và thời gian; chuẩn hóa diagnostics/result, đóng phiên khi hết hạn hoặc hoàn tất.
3. Khi prototype đã đủ ổn định, chuyển code thành source files có tên/class/package, compile và chạy test.
4. Chỉ publish bản build có interface/DTO được định nghĩa rõ, semantic versioning và checksum/signature theo chính sách.
5. Plugin manager xác minh artifact, tìm provider, kiểm tra version API rồi gọi qua contract.
6. Khi gỡ plugin, hủy request/callback/thread và tài nguyên; **đóng JShell phiên thử nghiệm** nếu còn tồn tại và xử lý riêng vòng đời loader/plugin runtime.

Nếu chỉ cần các biểu thức ngắn do ứng dụng tự kiểm soát, một JShell engine có lifecycle tốt có thể là công cụ nội bộ phù hợp. Nhưng nếu muốn mở rộng hệ thống dài hạn, nhận plugin độc lập theo phiên bản hoặc hỗ trợ upgrade/rollback, một hợp đồng Java SPI hoặc API được package là lựa chọn có tính kiểm chứng tốt hơn.

## 9. Ranh giới bảo mật và tài nguyên: close() không phải sandbox

Một hiểu nhầm nguy hiểm là: "JShell mặc định có execution engine riêng nên chạy mã bất kỳ là an toàn". Điều đó **không đúng**. JShell thực thi mã Java, và mã có thể có side effect, tải thư viện, truy cập file/network hoặc gây tiêu thụ tài nguyên trong phạm vi quyền được cấp. Hành vi execution engine và classpath được cấu hình có thể thay đổi. Việc close() giải phóng state engine **không đồng nghĩa thu hồi mọi side effect** đã gây ra.

Trong môi trường sản xuất, cần tách các biện pháp:

| Mối lo | JShell API cung cấp | Host còn phải làm |
| --- | --- | --- |
| Hết phiên hợp lệ | AutoCloseable, close() | Xác định owner, timeout, không dùng lại instance đóng |
| Lỗi syntax/compile | SnippetEvent.status() và diagnostics | Chuẩn hóa lỗi, hạn chế kích thước kết quả, log |
| Lỗi runtime snippet | SnippetEvent.exception() | Xác định trạng thái request và chính sách phục hồi |
| Snippet chạy quá lâu | stop() cố gắng dừng | Isolation và watchdog, hard deadline ở process/container |
| Giữ quá nhiều state | drop(), tạo phiên mới và close() | Quota source/snippet/output/heap, số phiên đồng thời |
| Mã không tin cậy | Không có sandbox toàn diện chỉ nhờ JShell | Quyền OS, mạng, đĩa, tài nguyên, cô lập tiến trình |
| Tích hợp plugin lâu dài | REPL không cung cấp hợp đồng plugin cố định | SPI/DTO/API version, contract tests và artifact management |

Không gộp công việc đánh giá snippets của nhiều tenant vào một JShell chia sẻ chỉ vì muốn giảm chi phí khởi tạo: dữ liệu và khai báo sẽ thuộc cùng state engine, trong khi JShell không thread-safe. Với người dùng chưa tin cậy, nên chọn worker/process riêng theo ngữ cảnh cô lập, có giới hạn vòng đời rõ ràng.

**Lưu ý Java 17:** API jdk.jshell nằm trong module JDK riêng; cần chạy trên JDK có module này. Bản Java runtime tối giản được tạo không chứa jdk.jshell sẽ không chạy được code phụ thuộc JShell API. Trong khi đó, plugin JAR chạy bằng API Java thông thường có yêu cầu module/classpath tùy hợp đồng riêng. Đây là một lý do không nên làm cho interface plugin production phụ thuộc trực tiếp vào JShell.Snippet.

## 10. Các lỗi thường gặp và chẩn đoán

| Triệu chứng | Nguyên nhân cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| eval() ném IllegalStateException | JShell đã close hoặc execution state kết thúc | Không tái sử dụng instance; tạo phiên mới theo chính sách |
| Không thấy biến của lần thử trước | Lượt gọi đang dùng JShell khác, hoặc khai báo bị drop/overwritten | Quản lý session ID, status và thứ tự eval |
| Một lần eval có nhiều event ngoài dự kiến | Thay đổi snippet ảnh hưởng khai báo phụ thuộc | Duyệt toàn bộ List<SnippetEvent>, không cố định get(0) trong handler tổng quát |
| status VALID nhưng value null | Snippet không có giá trị hiển thị, ví dụ import hoặc method declaration | Đọc status, kind, exception và value theo loại |
| Chuỗi kết quả có dấu ngoặc kép hoặc biểu diễn khác mong đợi | SnippetEvent.value() là display string chứ không phải DTO | Chuẩn hóa schema cho caller, không parse như ABI |
| Có diagnostic nhưng không có exception runtime | Lỗi biên dịch, không phải method của plugin ném exception | Xử lý diagnostic và REJECTED riêng |
| Có exception từ snippet dù compile thành công | Mã đã được thực thi và ném lỗi | Xem SnippetEvent.exception(), xử lý ở ranh giới đánh giá |
| Phiên đã hết nhưng worker/CPU còn hoạt động | stop/cancel/close không thay chính sách kết thúc tiến trình độc lập | Cô lập, watchdog và dọn vòng đời worker |
| Plugin đã update nhưng host vẫn dùng bản cũ | Instance/class loader/JAR và registry còn giữ version cũ | Stop/unregister, tạo loader/version mới, kiểm tra compatibility |
| Plugin được tìm nhưng không cast được sang API | SPI class được định nghĩa bởi loader khác | Chia sẻ API ổn định với class identity thống nhất |
| Chạy trong JShell được nhưng build source thực lại lỗi | Snippet syntax, REPL state/import mặc định khác source project | Chuyển thành file/module hoàn chỉnh, compile/test bằng pipeline chính thức |

Khi điều tra "đã đóng phiên chưa?", đừng chỉ kiểm tra biến tham chiếu JShell có khác null. Hãy kiểm tra lifecycle state ở host và xác nhận close() đã được gọi tại đúng owner; đọc lại shell bằng eval() chỉ để thử xem nó còn mở là cách kiểm tra có side effect và không nên dùng như health check production.

Khi điều tra "plugin có ổn định không?", đừng dùng trạng thái một lần thử JShell thành công làm tiêu chí duy nhất. Cần kiểm tra hợp đồng API, dependency, JDK version, đường nạp, cấu hình, hành vi khi thất bại và các test qua nhiều phiên bản.

## 11. Bài tập củng cố

**Bài tập A — mô phỏng lỗi rồi đóng:** Trong lab phần 4, thay snippet invalid bằng khai báo hợp lệ mà thực thi ném RuntimeException. Quan sát SnippetEvent.exception(), xác nhận try-with-resources vẫn đóng phiên sau khi code host xử lý. Phân biệt exception của code snippet với IllegalStateException vì JShell đã đóng.

**Bài tập B — status và redefine:** Đánh giá int factor = 7; sau đó đánh giá int factor = 9; trong cùng phiên. Quan sát trạng thái của snippet cũ và mới qua shell.status(snippet). Thử tạo JShell mới và xác nhận nó không có khai báo factor trước đó.

**Bài tập C — listener lifecycle:** Đăng ký onSnippetEvent, lưu Subscription, unsubscribe trước khi đóng. So sánh thu thập event trực tiếp từ eval() với callback. Không lưu JShell.Subscription làm API để client gọi về sau khi phiên đã kết thúc.

**Bài tập D — hợp đồng plugin:** Đổi transform(String) sang transform(Object) ở interface rồi thử biên dịch provider cũ. Giải thích vì sao đây là thay đổi API có thể phá tương thích, khác hoàn toàn redefine một method snippet trong REPL.

**Bài tập E — đóng gói SPI:** Xóa META-INF/services/demo.api.MessagePlugin khỏi plugin JAR, chạy host và quan sát matched=0. Plugin class vẫn tồn tại nhưng không được đăng ký ServiceLoader. Khắc phục bằng packaging, không phải bằng JShell.eval.

**Bài tập F — shutdown và concurrency:** Mô phỏng hai request cùng dùng một JShell. Thay vì eval song song, xây một queue dùng riêng cho phiên và cơ chế chuyển OPEN → CLOSING → CLOSED ở session manager. Đảm bảo không task mới nào được nhận sau khi bắt đầu đóng.

## 12. Checklist vận hành và tài liệu API

Trước khi đưa mã JShell nhúng vào ứng dụng, kiểm tra:

- **Ownership:** Mỗi phiên có owner, session ID, điều kiện kết thúc và chính sách giới hạn số phiên; không chia sẻ JShell giữa nhiều thread mà không có cơ chế tuần tự hóa.
- **Close:** Dùng try-with-resources khi phiên ngắn; phiên dài phải close trong cleanup/lifecycle được quản lý. Không coi drop/stop là close.
- **State/results:** Đọc List<SnippetEvent> đầy đủ, tách compile status/diagnostics khỏi runtime exception, chuẩn hóa kết quả trước khi đóng.
- **Failure:** Xử lý JShell đã closed, remote execution engine kết thúc, đánh giá bị timeout, thread/task còn sống và trường hợp close/cleanup gặp lỗi.
- **Security:** Không chạy source không tin cậy trong JVM có quyền cao chỉ vì JShell thuận tiện; dùng process isolation, quota và hạn chế quyền khi cần.
- **Plugin contract:** Interface/DTO và versions độc lập với JShell, API class identity thống nhất, artifact JAR/module có kiểm chứng, test startup và rollback.
- **Clean unload:** Stop request/callback/thread, đóng phiên JShell thử nghiệm và quản lý riêng loader/lifecycle của plugin runtime; không giả định GC sẽ thu ngay mọi class loader.

Tài liệu chuẩn JDK 17: [JShell API](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jshell/jdk/jshell/JShell.html), [package jdk.jshell](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jshell/jdk/jshell/package-summary.html), [Snippet và trạng thái](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jshell/jdk/jshell/Snippet.html), [Java Shell User's Guide](https://docs.oracle.com/en/java/javase/17/jshell/) và [ServiceLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html).

**Kết luận:** hãy xem **JShell là một phiên thử nghiệm có state và thời hạn**: tạo, đánh giá, thu kết quả, rồi đóng để giải phóng tài nguyên. Khi chức năng đã trở thành thành phần có thể tích hợp lâu dài, hãy **chuyển nó sang hợp đồng plugin ổn định** (SPI/DTO có version và artifact đã build/test), thay vì phụ thuộc lịch sử snippet hoặc các chuỗi giá trị hiển thị của REPL.
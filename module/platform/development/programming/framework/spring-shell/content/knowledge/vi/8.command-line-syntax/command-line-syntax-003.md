# Escape ký tự đặc biệt và đường dẫn chứa khoảng trắng

Spring Shell phân tích dòng lệnh theo từng từ. Khoảng trắng là dấu phân cách giữa các token, vì vậy một giá trị có khoảng trắng, chẳng hạn tên người dùng hoặc đường dẫn file, phải được đặt trong dấu nháy. Spring Shell hỗ trợ cả nháy đơn và nháy kép; dấu nháy bao quanh giá trị sẽ được loại bỏ trước khi framework truyền dữ liệu vào command.

Khi giá trị cần chứa chính dấu nháy đang dùng để bao quanh nó, đặt dấu gạch chéo ngược (**\**) trước dấu nháy đó. Khi cần giữ một dấu gạch chéo ngược thực sự bên trong giá trị đã đặt trong dấu nháy, viết thành hai dấu gạch chéo ngược (**\\**). Các quy tắc này đặc biệt quan trọng với đường dẫn Windows, vì ký tự phân cách thư mục của Windows cũng là dấu gạch chéo ngược.

Bài học sử dụng cú pháp của Spring Shell 4.x, với ví dụ dựa trên API command hiện hành. Cần phân biệt parser của Spring Shell với shell của hệ điều hành như PowerShell, Command Prompt hoặc Bash: mỗi tầng có thể có quy tắc trích dẫn và escape riêng.

## 1. Vì sao cần đặt giá trị trong dấu nháy?

Giả sử command nhận một thông điệp:

~~~java
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
class MessageCommands {

    @Command(name = "echo-message", description = "Hiển thị lại thông điệp.")
    public String echoMessage(
            @Option(longName = "message", required = true) String message) {
        return message;
    }
}
~~~

Khi gọi command, mỗi khoảng trắng thông thường phân tách các token. Nếu nhập:

~~~text
echo-message --message=Hello Spring Shell
~~~

parser có thể tách phần sau thành nhiều token. Giá trị của option không còn là một chuỗi duy nhất **Hello Spring Shell**. Đặt toàn bộ giá trị trong dấu nháy để giữ nó thành một đơn vị:

~~~text
echo-message --message="Hello Spring Shell"
echo-message --message='Hello Spring Shell'
~~~

Cả hai cách đều truyền chuỗi **Hello Spring Shell** vào tham số **message**. Dấu nháy ngoài cùng không nằm trong giá trị mà method nhận được.

## 2. Quy tắc nháy trong Spring Shell 4.x

Spring Shell 4 hỗ trợ hai loại dấu nháy:

| Cách viết | Giá trị command nhận được |
|---|---|
| **--message="Hello World"** | **Hello World** |
| **--message='Hello World'** | **Hello World** |
| **--message="I'm ready"** | **I'm ready** |
| **--message='He said "Hello"'** | **He said "Hello"** |

Khi một loại dấu nháy bao quanh toàn bộ giá trị, loại dấu nháy còn lại có thể xuất hiện bên trong mà không cần escape. Ví dụ, dùng nháy kép bên ngoài để giữ dấu nháy đơn trong câu tiếng Anh, hoặc dùng nháy đơn bên ngoài để giữ nháy kép trong nội dung.

~~~text
echo-message --message="I'm ready"
echo-message --message='He said "Hello"'
~~~

Trong cả hai trường hợp, command nhận được nội dung bên trong dấu nháy, bao gồm loại dấu nháy bên trong.

### 2.1. Escape dấu nháy cùng loại

Nếu giá trị cần chứa chính loại dấu nháy đang bao quanh nó, thêm dấu gạch chéo ngược trước dấu nháy bên trong:

~~~text
echo-message --message="He said \"Hello\""
echo-message --message='It\'s ready'
~~~

Kết quả lần lượt là:

~~~text
He said "Hello"
It's ready
~~~

Dấu gạch chéo ngược được dùng để báo rằng dấu nháy kế tiếp là nội dung của giá trị, không phải dấu kết thúc phần được trích dẫn.

### 2.2. Giữ một dấu gạch chéo ngược

Trong một giá trị đã đặt trong dấu nháy, viết hai dấu gạch chéo ngược để biểu diễn một dấu gạch chéo ngược thực sự:

~~~text
echo-message --message="C:\\temp\\new"
~~~

Giá trị command nhận được:

~~~text
C:\temp\new
~~~

Quy tắc này thường gặp khi truyền đường dẫn Windows hoặc chuỗi có ký tự gạch chéo ngược. Hãy escape từng dấu gạch chéo ngược cần giữ lại.

### 2.3. Dấu nháy phải bao quanh toàn bộ giá trị

Spring Shell chỉ loại bỏ dấu nháy khi toàn bộ giá trị được bao quanh bởi cặp dấu nháy. Dấu nháy nằm giữa một giá trị vẫn được giữ như ký tự thông thường. Ví dụ:

~~~text
value1"inside"value2
~~~

Đây là một chuỗi có dấu nháy ở giữa; dấu nháy không tự động bị xóa như trường hợp bao quanh toàn bộ giá trị. Để tránh nhầm lẫn khi truyền thông điệp hoặc đường dẫn, hãy đặt cặp dấu nháy ở đầu và cuối toàn bộ giá trị.

Nếu mở dấu nháy mà không đóng, parser từ chối dòng lệnh và báo lỗi. Hãy kiểm tra dấu nháy mở/đóng trước khi điều tra lỗi chuyển đổi kiểu hoặc lỗi xử lý file.

### 2.4. Escape chỉ được xử lý bên trong giá trị có dấu nháy

Trong cú pháp 4.x, các escape sequence được giải quyết bên trong giá trị đã đặt trong dấu nháy. Không dựa vào cách viết escape khoảng trắng khi không có dấu nháy, ví dụ:

~~~text
echo-message This\ is\ one\ value
~~~

Một số tài liệu Spring Shell 2.x cũ có ví dụ escape khoảng trắng theo cách này. Khi viết command cho Spring Shell 4.x, hãy dùng dấu nháy bao quanh toàn bộ giá trị:

~~~text
echo-message "This is one value"
~~~

## 3. Truyền option và argument có khoảng trắng

Spring Shell hỗ trợ option dạng dài và dạng ngắn. Giá trị option có thể được đặt sau dấu bằng hoặc ở token tiếp theo:

~~~text
--message="Hello World"
--message "Hello World"
-m="Hello World"
-m "Hello World"
~~~

Các dạng trên biểu diễn cùng một giá trị, miễn là command khai báo option tương ứng. Khi có khoảng trắng, hãy đặt phần giá trị trong dấu nháy, dù dùng dấu bằng hay dấu cách để ngăn cách tên option và giá trị.

Argument là giá trị theo vị trí. Với argument có khoảng trắng, đặt toàn bộ argument trong dấu nháy:

~~~java
import org.springframework.shell.core.command.annotation.Argument;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.stereotype.Component;

@Component
class GreetingCommands {

    @Command(name = "greet", description = "Chào một người.")
    public String greet(@Argument(index = 0) String name) {
        return "Xin chào " + name;
    }
}
~~~

Gọi command:

~~~text
greet "Nguyen Van An"
greet 'Nguyen Van An'
~~~

Method nhận một argument có giá trị **Nguyen Van An**. Nếu bỏ dấu nháy, parser sẽ nhìn thấy nhiều token và có thể gán chúng thành các argument riêng hoặc báo thừa đối số, tùy khai báo command.

Nếu command nhận nhiều giá trị bằng **@Arguments**, mỗi giá trị có khoảng trắng vẫn cần được trích dẫn riêng:

~~~text
greet-many "Nguyen Van An" "Tran Thi Binh"
~~~

Mỗi cặp dấu nháy giữ một tên đầy đủ thành một phần tử của collection hoặc array. Không đặt cả danh sách trong một cặp dấu nháy nếu mục tiêu là truyền nhiều phần tử riêng biệt.

## 4. Đường dẫn Windows có khoảng trắng

Đường dẫn Windows thường có dạng **C:\Users\Tên người dùng\Documents\Tên thư mục\file.csv**. Có hai vấn đề cần xử lý:

1. Khoảng trắng trong tên người dùng hoặc tên thư mục làm parser tách đường dẫn thành nhiều token.
2. Dấu gạch chéo ngược trong đường dẫn cần được escape khi nằm trong giá trị đã đặt trong dấu nháy.

Giả sử command nhận một option **path**:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
class FileCommands {

    @Command(name = "inspect-file", description = "Kiểm tra file đầu vào.")
    public String inspectFile(
            @Option(longName = "path", required = true) String path) {

        Path file = Path.of(path);
        if (!Files.isRegularFile(file)) {
            return "Không tìm thấy file: " + file;
        }

        return "File hợp lệ: " + file.toAbsolutePath();
    }
}
~~~

Gọi command với đường dẫn:

~~~text
inspect-file --path="C:\\Users\\Linh\\My Documents\\Sales Report\\report.csv"
~~~

Sau khi Spring Shell xử lý dấu nháy và escape, tham số **path** nhận được đường dẫn:

~~~text
C:\Users\Linh\My Documents\Sales Report\report.csv
~~~

Có thể dùng dạng tách option và giá trị:

~~~text
inspect-file --path "C:\\Users\\Linh\\My Documents\\Sales Report\\report.csv"
~~~

Điểm quan trọng là cặp dấu nháy bao quanh toàn bộ đường dẫn, còn mỗi dấu gạch chéo ngược cần giữ lại được viết thành hai dấu gạch chéo ngược trong dòng lệnh Spring Shell.

### 4.1. Dùng dấu gạch chéo xuôi trên Windows

Java trên Windows chấp nhận dấu gạch chéo xuôi làm dấu phân cách đường dẫn trong các API như **Path.of()**. Vì vậy, có thể viết đường dẫn theo dạng:

~~~text
inspect-file --path="C:/Users/Linh/My Documents/Sales Report/report.csv"
~~~

Cách này giúp tránh phải escape từng dấu gạch chéo ngược. Tuy nhiên, cần bảo đảm thành phần tiếp nhận đường dẫn thực sự dùng API xử lý đường dẫn của Java hoặc chấp nhận dạng phân cách này. Nếu ứng dụng truyền nguyên chuỗi cho một chương trình bên ngoài có quy tắc riêng, hãy kiểm tra yêu cầu của chương trình đó.

## 5. Đường dẫn POSIX có khoảng trắng

Trên Linux và macOS, đường dẫn thường dùng dấu gạch chéo xuôi. Chỉ cần đặt toàn bộ đường dẫn trong dấu nháy:

~~~text
inspect-file --path="/home/linh/Project Files/Sales Report/report.csv"
inspect-file --path='/home/linh/Project Files/Sales Report/report.csv'
~~~

Giá trị truyền vào Java:

~~~text
/home/linh/Project Files/Sales Report/report.csv
~~~

Nếu tên file có dấu nháy đơn, có thể dùng dấu nháy kép bên ngoài:

~~~text
inspect-file --path="/home/linh/linh's files/report.csv"
~~~

Nếu tên file có dấu nháy kép, dùng dấu nháy đơn bên ngoài:

~~~text
inspect-file --path='/home/linh/He said "final"/report.csv'
~~~

Nếu giá trị có cả hai loại dấu nháy, chọn một loại làm dấu bao ngoài và escape các dấu nháy cùng loại xuất hiện bên trong.

## 6. Ký tự đặc biệt trong giá trị

Khi truyền một chuỗi có dấu nháy, dấu gạch chéo ngược hoặc khoảng trắng, hãy áp dụng đúng quy tắc của parser:

| Nội dung cần truyền | Cách viết trong Spring Shell 4.x |
|---|---|
| Giá trị có khoảng trắng | **--message="Hello Spring Shell"** |
| Chuỗi chứa dấu nháy kép | **--message='He said "Hello"'** |
| Chuỗi chứa dấu nháy đơn | **--message="It's ready"** |
| Chuỗi chứa cả hai loại dấu nháy | **--message="He said \"I'm ready\"."** |
| Chuỗi chứa dấu gạch chéo ngược | **--message="C:\\temp\\new"** |
| Tên file có dấu ngoặc và khoảng trắng | **--path="C:\\Data\\Reports (final)\\report.csv"** |

Spring Shell không phải Bash hoặc PowerShell. Không giả định rằng biến môi trường, command substitution, pipeline, chuyển hướng hoặc wildcard của shell hệ điều hành cũng được Spring Shell thực hiện. Parser của Spring Shell xử lý cú pháp command và giá trị; nếu command tiếp tục chuyển chuỗi cho một chương trình hệ điều hành, chương trình hoặc shell được gọi có thể có thêm một tầng diễn giải.

Ví dụ, dấu **&**, **|**, **$**, **;**, **<**, **>**, **\*** hoặc **?** có thể là ký tự trong tên file hay nội dung. Khi nhập trực tiếp tại prompt Spring Shell, hãy bảo đảm chúng nằm trong giá trị được trích dẫn nếu có khoảng trắng. Khi khởi chạy ứng dụng từ PowerShell, Command Prompt hoặc Bash, hãy kiểm tra thêm quy tắc của terminal bên ngoài, vì terminal đó xử lý dòng lệnh trước khi JVM nhận tham số.

Không tự nối chuỗi đầu vào vào một lệnh hệ điều hành rồi giả định dấu nháy của Spring Shell đã bảo vệ chuỗi ở tầng tiếp theo. Nếu cần gọi chương trình ngoài, ưu tiên API nhận danh sách đối số riêng biệt như **ProcessBuilder(List<String>)** thay vì ghép một chuỗi command rồi chuyển qua shell hệ điều hành.

## 7. Phân biệt prompt Spring Shell, script và terminal hệ điều hành

Một lệnh có thể đi qua các tầng khác nhau:

~~~mermaid
flowchart TD
    A["Người dùng nhập lệnh"] --> B{"Đầu vào đến từ đâu?"}
    B --> C["Prompt Spring Shell"]
    B --> D["File script của Spring Shell"]
    B --> E["PowerShell / CMD / Bash"]
    C --> F["Spring Shell CommandParser"]
    D --> F
    E --> G["Parser của hệ điều hành"]
    G --> H["JVM nhận tham số"]
    F --> I["Option và argument đã phân tích"]
    H --> J["Ứng dụng xử lý tham số khởi động"]
    I --> K["Command method"]
    J --> K
~~~

**Tại prompt Spring Shell:** parser của Spring Shell xử lý dấu nháy và escape theo quy tắc của phiên bản framework. Ví dụ đường dẫn Windows phải đặt trong dấu nháy và escape dấu gạch chéo ngược như các ví dụ ở trên.

**Trong file script chạy bằng Spring Shell:** mỗi dòng command được shell xử lý theo cú pháp command của ứng dụng. Giữ nguyên quy tắc nháy và escape của Spring Shell. Nếu script được tạo từ một ngôn ngữ khác hoặc được sinh tự động, cần bảo đảm tầng tạo file không làm mất dấu gạch chéo ngược trước khi Spring Shell đọc file.

**Khi khởi chạy ứng dụng từ terminal hệ điều hành:** PowerShell, Command Prompt hoặc Bash xử lý dấu nháy, dấu gạch chéo ngược và ký tự đặc biệt trước khi truyền đối số cho tiến trình Java. Dấu nháy có thể đã bị terminal bên ngoài loại bỏ trước khi Spring Shell nhận dữ liệu. Hãy viết theo cú pháp của terminal đang dùng và kiểm tra giá trị thực mà ứng dụng nhận được; không áp dụng máy móc số lượng dấu gạch chéo ngược của prompt Spring Shell cho lệnh khởi chạy JVM.

Nếu ứng dụng nhận một chuỗi command rồi đưa chuỗi đó qua **CommandParser.parse(String)**, lúc này parser Spring Shell lại xử lý chuỗi theo quy tắc của nó. Cần xác định rõ dữ liệu đang là một đối số JVM đã được tách sẵn hay là một dòng command thô cần parse lần nữa.

## 8. Kiểm tra cú pháp bằng một command echo

Khi không chắc giá trị được parser giữ lại ra sao, tạo một command kiểm tra tạm thời hoặc dùng command chẩn đoán để in giá trị nhận được:

~~~java
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
class SyntaxCommands {

    @Command(name = "show-value", description = "Hiển thị giá trị sau khi parse.")
    public String showValue(
            @Option(longName = "value", required = true) String value) {
        return "[" + value + "]";
    }
}
~~~

Thử các đầu vào:

~~~text
show-value --value="Hello World"
show-value --value='He said "Hello"'
show-value --value="He said \"Hello\""
show-value --value="C:\\Users\\Linh\\My Documents\\report.csv"
~~~

Kết quả trong dấu ngoặc vuông giúp nhìn rõ khoảng trắng đầu/cuối, dấu nháy và dấu gạch chéo ngược. Khi kiểm tra đường dẫn, có thể in thêm **Path.of(value).toAbsolutePath()** để xác định Java diễn giải đường dẫn ra sao.

## 9. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Đường dẫn bị tách thành nhiều phần | Có khoảng trắng nhưng không đặt cả đường dẫn trong dấu nháy | Dùng **--path="..."** hoặc **--path "..."** |
| Đường dẫn Windows chứa dấu gạch chéo ngược sai | Chưa escape dấu gạch chéo ngược bên trong giá trị có dấu nháy | Viết **\\** cho mỗi dấu gạch chéo ngược muốn giữ |
| Dấu nháy xuất hiện trong kết quả ngoài ý muốn | Dấu nháy nằm giữa giá trị thay vì bao quanh toàn bộ giá trị | Đặt dấu nháy ở đầu và cuối toàn bộ giá trị |
| Parser báo lỗi dấu nháy | Thiếu dấu nháy đóng hoặc escape sai dấu nháy bên trong | Kiểm tra cặp dấu nháy và escape dấu nháy cùng loại |
| Chuỗi mất dấu gạch chéo ngược | Escape sequence bị xử lý trong giá trị đã trích dẫn | Viết **\\\\** để giữ một dấu gạch chéo ngược |
| Script hoạt động khác prompt | Tầng sinh script hoặc trình soạn thảo đã biến đổi ký tự escape | Kiểm tra nội dung file script thô trước khi chạy |
| Chạy từ PowerShell/CMD cho kết quả khác prompt Spring Shell | Terminal bên ngoài xử lý chuỗi trước khi JVM nhận tham số | Xác định tầng nào đang parse và viết cú pháp cho đúng tầng |
| Tên file có ký tự đặc biệt bị hiểu sai ở chương trình ngoài | Chuỗi được chuyển tiếp qua một shell khác | Truyền đối số tách biệt qua API tiến trình, tránh ghép command string |

### Lưu ý về phiên bản 4.0.4

Spring Shell 4.0.4 có bản sửa lỗi xử lý dấu nháy đã escape trong **DefaultCommandParser**. Nếu ứng dụng dùng phiên bản 4.0.x cũ và gặp kết quả không nhất quán với dấu nháy escape, hãy đối chiếu release notes và cập nhật lên bản vá phù hợp. Sau khi nâng phiên bản, kiểm tra lại các command và script có chứa dấu nháy lồng nhau.

## 10. Danh sách kiểm tra trước khi truyền đường dẫn

- Đường dẫn có khoảng trắng chưa? Nếu có, đặt toàn bộ giá trị trong dấu nháy.
- Đang dùng đường dẫn Windows với dấu gạch chéo ngược? Nếu có, escape mỗi dấu gạch chéo ngược bên trong giá trị có dấu nháy.
- Nội dung có chứa dấu nháy cùng loại với dấu bao ngoài? Nếu có, thêm dấu gạch chéo ngược trước dấu nháy đó.
- Có đang dùng cú pháp cũ escape khoảng trắng mà không có dấu nháy? Hãy chuyển sang quy tắc trích dẫn của Spring Shell 4.x.
- Lệnh được nhập ở prompt Spring Shell, trong script hay từ terminal hệ điều hành? Xác định đúng tầng parser.
- Command có chuyển chuỗi thành lệnh hệ điều hành? Nếu có, kiểm soát riêng tầng thực thi bên ngoài.
- File có thực sự tồn tại và tiến trình có quyền đọc file không? Sau khi parse đúng, vẫn cần kiểm tra filesystem và quyền truy cập.

## 11. Tài liệu tham khảo

- [Spring Shell 4.0.3 — Command Syntax](https://docs.spring.io/spring-shell/reference/commands/syntax.html) — quy tắc option, argument và cú pháp parser của Spring Shell 4.
- [Spring Shell 4.0.4 — Release Notes](https://github.com/spring-projects/spring-shell/releases/tag/v4.0.4) — bản sửa lỗi xử lý dấu nháy đã escape trong **DefaultCommandParser**.
- [Spring Shell 4.0.4 — CommandParser API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/CommandParser.html) — hợp đồng parse chuỗi đầu vào thành **ParsedInput**.
- [Spring Shell 4.0-SNAPSHOT — Quoting and Escaping](https://docs.spring.io/spring-shell/reference/4.0-SNAPSHOT/commands/syntax.html) — mô tả chi tiết dấu nháy đơn, dấu nháy kép, escape dấu nháy và dấu gạch chéo ngược. Đối chiếu với release notes của phiên bản stable đang dùng trước khi áp dụng.
- [Spring Shell 2.1.0-M3 — Quotes Handling](https://docs.spring.io/spring-shell/docs/2.1.0-M3/site/reference/htmlsingle/) — tài liệu lịch sử minh họa cách escape trong dòng 2.x; không dùng thay cho quy tắc 4.x.

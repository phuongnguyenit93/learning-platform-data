# Khoảng trắng, dấu nháy và giá trị chứa nhiều từ

Trong Spring Shell, khoảng trắng dùng để phân tách các token của dòng lệnh. Vì vậy, nếu một tên người dùng, thông điệp hoặc đường dẫn có chứa dấu cách, bạn cần chỉ rõ phần nào thuộc cùng một giá trị. Dấu nháy đơn (`'`) và dấu nháy kép (`"`) giúp giữ nhiều từ thành một token; dấu gạch chéo ngược (`\`) cho phép đưa dấu nháy cùng loại hoặc ký tự gạch chéo ngược vào giá trị.

Nắm rõ quy tắc này giúp tránh lỗi khi nhập tên đầy đủ, câu thông báo, đường dẫn file, biểu thức hoặc dữ liệu có dấu nháy. Bài học sử dụng parser mặc định của Spring Shell 4.x và minh họa cách các quy tắc áp dụng cho cả positional argument lẫn named option.

## 1. Khoảng trắng phân tách token

Spring Shell đọc dòng lệnh rồi tách input thành các từ dựa trên khoảng trắng. Ví dụ:

```text
greet Nguyen An
```

Parser nhìn thấy hai token `Nguyen` và `An` sau tên command. Nếu command chỉ nhận một argument là tên người dùng, dữ liệu đã bị tách thành hai phần.

Khi muốn coi `Nguyen An` là một giá trị duy nhất, hãy đặt toàn bộ giá trị trong một cặp dấu nháy:

```text
greet "Nguyen An"
```

Lúc này, parser giữ `Nguyen An` thành một token. Dấu nháy chỉ đánh dấu ranh giới của giá trị và được loại bỏ khi phân tích; phương thức command nhận chuỗi `Nguyen An`.

Quy tắc tương tự áp dụng cho nhiều loại dữ liệu:

| Giá trị cần truyền | Cách viết trong command |
|---|---|
| Tên đầy đủ | `greet "Nguyen Minh An"` |
| Tên dự án | `project create "Learning Platform"` |
| Thông điệp | `notify --message "Build completed successfully"` |
| Đường dẫn có dấu cách | `file show "C:/Work Reports/May report.csv"` |
| Câu tìm kiếm | `search --query "spring shell command parser"` |

Không cần đặt dấu nháy quanh giá trị chỉ có một token và không chứa ký tự đặc biệt cần bảo vệ. Dùng dấu nháy khi cần giữ nguyên khoảng trắng hoặc ký tự có ý nghĩa cú pháp.

## 2. Dấu nháy đơn và dấu nháy kép

Spring Shell hỗ trợ cả hai kiểu dấu nháy:

- Dấu nháy đơn: `'...'`
- Dấu nháy kép: `"..."`

Hai kiểu có tác dụng tương đương khi bao quanh toàn bộ giá trị. Dấu nháy mở và đóng không xuất hiện trong chuỗi mà command nhận được.

Ví dụ với argument:

```text
greet 'Nguyen Minh An'
greet "Nguyen Minh An"
```

Cả hai cách đều truyền một giá trị `Nguyen Minh An`.

Ví dụ với option:

```text
notify --message='Hello World'
notify --message="Hello World"
notify --message 'Hello World'
notify --message "Hello World"
```

Các cách trên đều thể hiện option `message` có giá trị `Hello World`. Spring Shell hỗ trợ dạng `--key=value` và `--key value`; dấu nháy giúp parser giữ phần có khoảng trắng thành một giá trị.

### Khai báo command nhận giá trị nhiều từ

Ví dụ command nhận tên người dùng dưới dạng positional argument và lời chào dưới dạng option:

```java
import org.springframework.shell.core.command.annotation.Argument;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
class GreetingCommands {

    @Command(name = "greet", description = "Chào một người dùng")
    public String greet(
            @Argument(index = 0, description = "Tên đầy đủ") String name,
            @Option(longName = "message", description = "Thông điệp bổ sung") String message) {
        return "Xin chào " + name + ". " + message;
    }
}
```

Có thể gọi command như sau:

```text
greet "Nguyen Minh An" --message "Chào mừng bạn đến với Spring Shell"
greet 'Nguyen Minh An' --message='Chào mừng bạn đến với Spring Shell'
```

`@Argument(index = 0)` nhận token vị trí đầu tiên sau command path. `@Option(longName = "message")` nhận giá trị có tên `message`. Dấu nháy giữ toàn bộ tên và thông điệp thành từng giá trị, nên method nhận đúng hai chuỗi như mong muốn.

## 3. Chọn loại dấu nháy để chứa dấu nháy bên trong

Một kiểu dấu nháy có thể xuất hiện bình thường bên trong giá trị được bao bởi kiểu dấu nháy còn lại.

Nếu thông điệp chứa dấu nháy đơn, hãy bao ngoài bằng dấu nháy kép:

```text
notify --message="I'm ready!"
```

Giá trị command nhận được:

```text
I'm ready!
```

Nếu thông điệp chứa dấu nháy kép, hãy bao ngoài bằng dấu nháy đơn:

```text
notify --message='He said "Start the deployment!"'
```

Giá trị command nhận được:

```text
He said "Start the deployment!"
```

Đây thường là cách dễ đọc nhất vì không cần escape dấu nháy bên trong. Hãy chọn kiểu dấu nháy bao ngoài sao cho ký tự xuất hiện nhiều trong nội dung được giữ nguyên.

## 4. Escape dấu nháy cùng loại bằng dấu `\`

Nếu giá trị cần chứa chính kiểu dấu nháy đang dùng để bao ngoài, hãy thêm dấu gạch chéo ngược (`\`) trước dấu nháy đó.

Ví dụ bao ngoài bằng dấu nháy kép và cần chứa dấu nháy kép bên trong:

```text
notify --message="He said \"Deploy now!\""
```

Giá trị command nhận được:

```text
He said "Deploy now!"
```

Ví dụ bao ngoài bằng dấu nháy đơn và cần chứa dấu nháy đơn bên trong:

```text
notify --message='It\'s ready for review'
```

Giá trị command nhận được:

```text
It's ready for review
```

Chỉ escape dấu nháy trùng với kiểu dấu nháy đang bao ngoài. Nếu giá trị được bao bằng dấu nháy kép, dấu nháy đơn bên trong có thể để nguyên; nếu được bao bằng dấu nháy đơn, dấu nháy kép bên trong có thể để nguyên.

## 5. Giữ dấu gạch chéo ngược trong giá trị

Trong một giá trị được bao bằng dấu nháy, dấu gạch chéo ngược có vai trò escape. Nếu muốn truyền chính ký tự `\` vào command, hãy viết hai dấu gạch chéo ngược liên tiếp (`\\`).

Ví dụ đường dẫn Windows:

```text
file show --path="C:\\Work\\Reports\\May.csv"
```

Command nhận giá trị:

```text
C:\Work\Reports\May.csv
```

Điều này đặc biệt quan trọng với đường dẫn Windows, biểu thức chính quy hoặc dữ liệu có nhiều dấu gạch chéo ngược. Nếu cần truyền một dấu `\` theo nghĩa đen bên trong giá trị được quote, hãy escape nó thành `\\`.

## 6. Dấu nháy phải bao quanh toàn bộ giá trị

Spring Shell chỉ loại bỏ dấu nháy khi toàn bộ giá trị được bao bởi cặp dấu nháy tương ứng. Dấu nháy xuất hiện ở giữa một giá trị không được tự động xem là dấu phân cách để ghép các phần lại với nhau.

Ví dụ:

```text
echo value1"inside"value2
```

Phần có dấu nháy ở giữa được giữ nguyên như nội dung:

```text
value1"inside"value2
```

Parser không biến chuỗi đó thành `value1insidevalue2`. Nếu mục tiêu là một giá trị duy nhất có khoảng trắng, hãy đặt dấu nháy ở đầu và cuối toàn bộ giá trị:

```text
echo "value1 inside value2"
```

Quy tắc này giúp parser phân biệt ranh giới của giá trị một cách rõ ràng. Đừng đặt dấu nháy tùy ý giữa token và kỳ vọng chúng sẽ được nối lại.

## 7. Dấu nháy không cân bằng sẽ gây lỗi

Mỗi dấu nháy mở cần có dấu nháy đóng cùng loại. Ví dụ sau không hợp lệ:

```text
notify --message="Deployment completed
```

Giá trị chưa có dấu nháy kép đóng nên parser từ chối input. Khi gặp lỗi này:

1. Kiểm tra dấu nháy mở và đóng có cùng loại không.
2. Kiểm tra dấu nháy bên trong đã được escape nếu trùng kiểu với dấu bao ngoài chưa.
3. Kiểm tra dấu `\` cuối giá trị có vô tình escape dấu nháy đóng không.
4. Thử nhập lại một dòng hoàn chỉnh trước khi chạy command.

Trong interactive shell, lỗi parse được báo cho người dùng để sửa dòng lệnh. Trong script, một dòng có dấu nháy không cân bằng cũng cần được sửa trong file trước khi chạy lại.

## 8. Dấu escape chỉ được xử lý bên trong giá trị có quote

Spring Shell xử lý escape sequence trong ngữ cảnh giá trị được bao bằng dấu nháy. Đừng mặc định rằng một dấu `\` bên ngoài cặp dấu nháy sẽ được diễn giải giống như bên trong.

Ví dụ nên dùng:

```text
echo "Line with a \"quoted phrase\""
```

Khi cần một chuỗi có nhiều dấu nháy hoặc dấu gạch chéo ngược, bao toàn bộ giá trị trước rồi mới escape ký tự bên trong. Cách này dễ đọc và giảm nhầm lẫn khi parser xử lý các token.

## 9. Giá trị nhiều từ với `@Arguments`

Nếu command cần nhận nhiều token còn lại thay vì một argument cố định, Spring Shell cung cấp `@Arguments` cho tham số kiểu mảng hoặc collection. Mỗi cụm được quote vẫn là một token khi đưa vào collection.

```java
import java.util.Arrays;
import org.springframework.shell.core.command.annotation.Arguments;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.stereotype.Component;

@Component
class LabelCommands {

    @Command(name = "labels", description = "Hiển thị các nhãn")
    public String labels(@Arguments String[] labels) {
        return Arrays.toString(labels);
    }
}
```

Gọi command:

```text
labels urgent "needs review" "customer request"
```

Mảng nhận được có ba phần tử:

```text
["urgent", "needs review", "customer request"]
```

`@Arguments` mặc định thu thập các argument còn lại. Thuộc tính `arity` có thể giới hạn số token được thu thập vào tham số đó. Nếu cần truyền một cụm nhiều từ như một phần tử, hãy quote cụm đó; parser sẽ giữ nó thành một token trước khi binding vào mảng hoặc collection.

## 10. Phân biệt parser Spring Shell với shell của hệ điều hành

Khi nhập lệnh tại prompt của Spring Shell, chính parser của Spring Shell xử lý dấu nháy và escape. Nhưng khi khởi động ứng dụng từ Bash, PowerShell hoặc Command Prompt, shell của hệ điều hành có thể xử lý dấu nháy trước khi JVM nhận đối số.

Vì vậy có thể có hai lớp phân tích:

```text
Lệnh người dùng nhập
        |
        v
Shell của hệ điều hành (nếu khởi chạy từ terminal ngoài)
        |
        v
Đối số JVM nhận được
        |
        v
Spring Shell parser
        |
        v
Giá trị được binding vào tham số command
```

Một ví dụ escape đúng trong prompt Spring Shell chưa chắc có thể sao chép nguyên văn vào lệnh `java -jar ...` của PowerShell hoặc Bash. Khi chạy từ script ngoài, hãy kiểm tra quy tắc quote của shell hệ điều hành đang dùng và xác nhận giá trị thực tế mà command nhận được.

Để debug, có thể viết command tạm thời hiển thị giá trị và độ dài chuỗi, hoặc ghi từng phần tử của `@Arguments`. Không chỉ nhìn cách dòng lệnh được gõ; hãy kiểm tra dữ liệu sau khi parser và parameter binding xử lý.

## 11. Quy trình xử lý lỗi khi truyền giá trị nhiều từ

Khi command nhận sai nội dung, hãy kiểm tra theo thứ tự:

1. **Xác định tham số:** dữ liệu đang bind vào `@Argument`, `@Option` hay `@Arguments`?
2. **Đếm token:** khoảng trắng có làm một giá trị bị tách thành nhiều token không?
3. **Kiểm tra quote:** dấu nháy có bao toàn bộ giá trị không?
4. **Kiểm tra escape:** dấu nháy cùng loại và dấu `\` đã được escape đúng chưa?
5. **Kiểm tra lớp terminal:** lệnh được nhập trong Spring Shell hay được truyền qua Bash/PowerShell?
6. **Kiểm tra giá trị nhận được:** log hoặc hiển thị dữ liệu sau khi binding để xác nhận parser đã tạo đúng chuỗi.

Bảng lỗi thường gặp:

| Hiện tượng | Nguyên nhân | Cách sửa |
|---|---|---|
| Tên người dùng bị tách thành nhiều phần | Không quote giá trị có khoảng trắng | Dùng `"Nguyen Minh An"` hoặc `'Nguyen Minh An'` |
| Option chỉ nhận từ đầu tiên | Giá trị option chứa khoảng trắng nhưng không được quote | Dùng `--message "Hello World"` |
| Dấu nháy xuất hiện trong chuỗi kết quả | Dấu nháy không bao toàn bộ giá trị hoặc nằm giữa chuỗi | Đặt cặp dấu nháy quanh toàn bộ giá trị |
| Parser báo quote chưa đóng | Thiếu dấu nháy kết thúc hoặc escape nhầm dấu kết thúc | Cân bằng dấu nháy và kiểm tra `\` |
| Dấu nháy kép trong câu bị mất hoặc lỗi | Dùng cùng loại quote nhưng không escape | Dùng quote ngược loại hoặc `\"` |
| Đường dẫn Windows bị mất dấu `\` | Dấu gạch chéo ngược chưa được escape trong quoted value | Dùng `\\` cho mỗi dấu `\` cần giữ |
| Kết quả khác giữa prompt và PowerShell | Hai parser xử lý quote ở hai lớp khác nhau | Kiểm tra quy tắc quote của terminal hệ điều hành |

## 12. Bài tập thực hành

Xây dựng command `message send` để nhận tên người nhận và nội dung tin nhắn. Command cần hỗ trợ tên có nhiều từ, nội dung có dấu nháy đơn hoặc dấu nháy kép, và đường dẫn file đính kèm.

Hãy thực hiện:

1. Khai báo `recipient` bằng `@Argument(index = 0)`.
2. Khai báo `text` bằng `@Option(longName = "text")`.
3. Khai báo `attachment` bằng `@Option(longName = "attachment")`.
4. Gọi command với tên `"Nguyen Minh An"` và nội dung `"I'll send the report today"`.
5. Gọi lại command với nội dung chứa câu trích dẫn `He said "approved"`.
6. Truyền đường dẫn Windows có dấu `\` và xác nhận chuỗi nhận được giữ đúng đường dẫn.
7. Tạo command thứ hai dùng `@Arguments String[]` để thu thập nhiều nhãn; thử một nhãn đơn và hai nhãn có khoảng trắng.
8. Thử một dòng lệnh thiếu dấu nháy đóng, ghi nhận lỗi parser và sửa lại.
9. Chạy cùng command trong prompt Spring Shell và từ PowerShell/Bash; so sánh dữ liệu nhận được.

**Kết quả cần nộp:** source code command, các dòng lệnh đã thử, giá trị thực tế nhận được sau binding và bảng mô tả kết quả của từng trường hợp quote/escape.

## 13. Checklist trước khi dùng giá trị nhiều từ

- [ ] Đã xác định khoảng trắng là dấu phân tách token.
- [ ] Giá trị nhiều từ được bao bằng dấu nháy đơn hoặc dấu nháy kép.
- [ ] Dấu nháy bao quanh toàn bộ giá trị.
- [ ] Đã chọn kiểu quote phù hợp để giữ dấu nháy bên trong.
- [ ] Dấu nháy cùng loại với quote bao ngoài đã được escape bằng `\`.
- [ ] Dấu gạch chéo ngược cần giữ trong quoted value đã được viết thành `\\`.
- [ ] Không còn quote mở chưa được đóng.
- [ ] Đã kiểm tra từng token khi dùng `@Arguments`.
- [ ] Đã tính đến khác biệt giữa parser Spring Shell và shell của hệ điều hành.
- [ ] Đã kiểm tra giá trị thực tế sau khi command nhận tham số.

## Tài liệu tham khảo

- [Spring Shell Reference Documentation — Command Syntax](https://docs.spring.io/spring-shell/reference/commands/syntax.html)
- [Spring Shell API — `@Argument`](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/Argument.html)
- [Spring Shell API — `@Arguments`](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/Arguments.html)
- [Spring Shell API — `@Option`](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/Option.html)
- [Spring Shell API — `DefaultCommandParser`](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/DefaultCommandParser.html)
- [Spring Shell 4.0.4 Release Notes](https://github.com/spring-projects/spring-shell/releases/tag/v4.0.4)

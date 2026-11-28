# Từ dòng người dùng nhập đến các token của parser

Một command line bắt đầu bằng một dòng ký tự mà người dùng nhập vào terminal hoặc một dòng được đọc từ script. Spring Shell phải hiểu dòng đó theo cấu trúc: tên command, các subcommand, option có tên và argument theo vị trí. Quá trình này gọi là parsing. Kết quả parsing được chuyển cho lớp thực thi để tìm command phù hợp và cung cấp các giá trị đầu vào cho command.

Trong Spring Shell, parser là ranh giới giữa văn bản người dùng nhập và cấu trúc dữ liệu mà ứng dụng có thể xử lý. Hiểu ranh giới này giúp thiết kế cú pháp CLI rõ ràng, xử lý đúng dấu cách và dấu nháy, cũng như tìm nguyên nhân khi command không nhận được giá trị mong muốn.

## 1. Vị trí của parser trong luồng nhập lệnh

Spring Shell tách việc nhận dòng lệnh khỏi việc phân tích dòng lệnh. Thành phần nhận input biết cách lấy một dòng từ terminal hoặc file; parser hiểu ý nghĩa cú pháp của dòng đó.

~~~text
Người dùng nhập lệnh hoặc script cung cấp một dòng
                 |
                 v
      Terminal / InputProvider
                 |
                 v
       InteractiveShellRunner
                 |
                 v
       CommandParser.parse(line)
                 |
                 v
         DefaultCommandParser
                 |
                 v
             ParsedInput
                 |
                 v
   Lớp thực thi tra command và xử lý tham số
~~~

Các thành phần chính:

| Thành phần | Vai trò trong luồng |
|---|---|
| Terminal và JLine | Nhận phím, hiển thị prompt, hỗ trợ sửa dòng, lịch sử và hoàn thành lệnh khi ứng dụng chạy tương tác |
| InputProvider | Cung cấp một dòng input thông qua phương thức readInput() |
| InteractiveShellRunner | Điều phối vòng lặp tương tác; kết nối input provider, parser và command registry |
| CommandParser | API nhận chuỗi input thô và phân tích thành cấu trúc ParsedInput |
| DefaultCommandParser | Bộ phân tích mặc định của Spring Shell 4.x; dùng CommandRegistry để hiểu command và subcommand đã đăng ký |
| ParsedInput | Kết quả có cấu trúc gồm tên command, subcommand, option và argument |

InputProvider là một abstraction. Với terminal JLine, JLineInputProvider lấy dòng đã được người dùng xác nhận từ LineReader. ConsoleInputProvider đọc từ Java Console, còn FileInputProvider cung cấp input từ file. Các provider này có cùng hợp đồng: trả về dòng lệnh hoặc null khi hết input. Vì thế, command có thể được đưa vào shell qua bàn phím hoặc script mà không phải viết lại parser.

InteractiveShellRunner được xây dựng với ba dependency là InputProvider, CommandParser và CommandRegistry. Trong ứng dụng Spring Boot, auto-configuration thường tạo runner và các bean cần thiết; ứng dụng thông thường không phải tự khởi tạo runner.

## 2. Hai parser có vai trò khác nhau khi dùng JLine

Khi bật tích hợp JLine, có thể gặp từ “parser” ở hai lớp khác nhau:

- Parser của JLine làm việc với buffer đang được người dùng chỉnh sửa. Nó hỗ trợ nhận biết vùng trích dẫn, trạng thái dấu nháy và thông tin cần thiết để hoàn thành lệnh hoặc chèn candidate đúng cú pháp. Spring Shell có ExtendedDefaultParser, dựa trên JLine DefaultParser và tạo CompletingParsedLine.
- CommandParser của Spring Shell nhận toàn bộ dòng lệnh sau khi người dùng nhấn Enter và tạo ParsedInput. Đây là parser của cú pháp command được xử lý ở bước thực thi.

Hai lớp này phối hợp nhưng không thay thế nhau. JLine parser giúp trải nghiệm nhập liệu và completion; CommandParser biến dòng lệnh đã nhận thành tên command, subcommand, option và argument. Khi chạy từ file, input provider có thể bỏ qua giao diện JLine nhưng dòng lệnh vẫn được CommandParser phân tích.

## 3. CommandParser và DefaultCommandParser

Spring Shell 4.x định nghĩa hợp đồng CommandParser trong package org.springframework.shell.core.command. API cốt lõi của nó rất gọn:

~~~java
public interface CommandParser {
    ParsedInput parse(String input);
}
~~~

Phương thức parse nhận chuỗi thô và trả về ParsedInput. Bộ cài đặt mặc định là DefaultCommandParser. Nó được tạo với CommandRegistry để xác định tên command và chuỗi subcommand có thể nhận diện trong ứng dụng:

~~~java
import org.springframework.shell.core.command.CommandParser;
import org.springframework.shell.core.command.CommandRegistry;
import org.springframework.shell.core.command.DefaultCommandParser;
import org.springframework.shell.core.command.ParsedInput;

class ParserDemo {
    ParsedInput parseLine(CommandRegistry commandRegistry, String inputLine) {
        CommandParser parser = new DefaultCommandParser(commandRegistry);
        return parser.parse(inputLine);
    }
}
~~~

Trong ứng dụng thực tế, parser thường được cấu hình như một bean để runner sử dụng. Đoạn mã trên minh họa hợp đồng API và cách gọi parser trực tiếp, hữu ích khi cần kiểm tra hoặc tìm hiểu kết quả parsing.

ParsedInput là một record chứa bốn phần:

| Thành phần | Kiểu dữ liệu | Ý nghĩa |
|---|---|---|
| commandName | String | Tên command gốc |
| subCommands | List<String> | Các thành phần subcommand theo thứ tự |
| options | List<CommandOption> | Các option được nhận diện cùng giá trị và metadata của chúng |
| arguments | List<CommandArgument> | Các argument theo vị trí, được đánh chỉ số từ 0 |

CommandOption mô tả option và giá trị runtime, gồm tên ngắn, tên dài, mô tả, trạng thái bắt buộc, giá trị mặc định, giá trị nhận được và kiểu dữ liệu. CommandArgument biểu diễn một argument runtime với index và value. Nhờ đó, lớp phía sau không cần tự phân tích lại chuỗi văn bản ban đầu.

## 4. Tách từ và giữ nguyên giá trị có dấu cách

Theo cú pháp Spring Shell 4.x, khoảng trắng phân tách các từ trong dòng lệnh. Nếu một argument hoặc giá trị option có chứa khoảng trắng, phải đặt toàn bộ giá trị trong dấu nháy đơn hoặc nháy kép.

Ví dụ:

~~~text
report -- "Quarterly sales"
report --message='Quarterly sales'
report --message="Quarterly sales"
~~~

Trong cả ba trường hợp, giá trị được chuyển tiếp không chứa dấu nháy bao ngoài:

~~~text
Quarterly sales
~~~

Hai loại dấu nháy có thể lồng nhau. Khi dùng dấu nháy kép bao ngoài, dấu nháy đơn bên trong là ký tự bình thường; khi dùng dấu nháy đơn bao ngoài, dấu nháy kép bên trong cũng được giữ:

~~~text
report --message="I'm ready"
report --message='He said "Run the report"'
~~~

Nếu cần đặt chính loại dấu nháy đang bao ngoài vào trong giá trị, dùng dấu gạch chéo ngược để escape. Một dấu gạch chéo ngược thực sự bên trong giá trị được trích dẫn cũng phải được escape:

~~~text
report --message="He said \"Run it!\""
report --message='It\'s ready'
report --path="C:\\reports\\Q4"
~~~

Kết quả tương ứng:

| Input | Giá trị parser giữ lại |
|---|---|
| --message="He said \"Run it!\"" | He said "Run it!" |
| --message='It\'s ready' | It's ready |
| --path="C:\\reports\\Q4" | C:\reports\Q4 |

Một số quy tắc cần nhớ:

- Dấu nháy chỉ bị bỏ khi toàn bộ giá trị được bao bởi cặp dấu nháy tương ứng.
- Dấu nháy nằm giữa một giá trị không tự động bị loại bỏ. Ví dụ value1"inside"value2 vẫn giữ nguyên các dấu nháy ở giữa.
- Escape sequence chỉ được xử lý bên trong giá trị đã được đặt trong dấu nháy.
- Dòng có dấu nháy mở nhưng không đóng sẽ bị từ chối với lỗi parsing.

Những quy tắc này áp dụng cho cú pháp Spring Shell. Không nên mặc định các cơ chế mở rộng của Bash hoặc PowerShell như biến môi trường, glob, command substitution hay pipe sẽ tự động hoạt động trong command line của Spring Shell.

## 5. Nhận diện command, subcommand, option và argument

Sau khi hiểu ranh giới giữa các từ, DefaultCommandParser phân loại chúng theo cú pháp command. Cấu trúc khái quát:

~~~text
CommandSyntax ::= CommandName [SubCommandName]* [Option | Argument]*
CommandName ::= String
SubCommandName ::= String
Option ::= ShortOption | LongOption
ShortOption ::= '-' Char ['=' | ' ']? String
LongOption ::= '--' String ['=' | ' ']? String
Argument ::= String
~~~

Command và subcommand nằm ở phần đầu của dòng. Các phần tiếp theo có thể là option hoặc argument; option và argument có thể xuất hiện xen kẽ. Argument được đánh index từ 0 theo thứ tự xuất hiện của các argument, không tính option.

Ví dụ:

~~~text
catalog product find --tag="release candidate" page-42 --limit=10
~~~

Nếu CommandRegistry có command catalog và chuỗi subcommand product find, kết quả có cấu trúc khái niệm như sau:

~~~yaml
commandName: catalog
subCommands:
  - product
  - find
options:
  - name: tag
    value: release candidate
  - name: limit
    value: "10"
arguments:
  - index: 0
    value: page-42
~~~

Đây là cách biểu diễn để đọc kết quả, không phải định dạng YAML mà parser trả về. API thật trả về một ParsedInput với danh sách CommandOption và CommandArgument.

### 5.1. Option dạng ngắn và dạng dài

Option có tên dài bắt đầu bằng hai dấu gạch ngang; option ngắn bắt đầu bằng một dấu gạch ngang và một ký tự:

~~~text
report --format=csv
report --format csv
report -f=csv
report -f csv
~~~

Các cách viết trên biểu diễn cùng ý nghĩa khi option được đăng ký với tên dài format và tên ngắn f. Có thể đặt option trước hoặc sau argument:

~~~text
report "Quarterly sales" --format=csv
report --format=csv "Quarterly sales"
~~~

Không hỗ trợ gộp nhiều option ngắn thành một chuỗi như -abc. Hãy viết từng option rõ ràng, ví dụ -a -b -c.

Để tránh mơ hồ, cú pháp tài liệu yêu cầu option có giá trị đi kèm, kể cả option kiểu boolean. Cách viết tường minh như --verbose=true giúp parser phân biệt giá trị option với argument theo vị trí.

### 5.2. Dấu phân cách -- cho argument

Khi command không khai báo option, hoặc có subcommand nhưng không dùng option, cần dùng dấu phân cách -- trước các argument để tránh parser nhầm chúng với tên subcommand:

~~~text
search -- report-final
catalog product -- report-final
~~~

Dấu -- báo rằng các từ tiếp theo là argument. Cách viết này cũng hữu ích khi argument bắt đầu bằng dấu gạch ngang:

~~~text
search -- --archived
~~~

Nếu command có nhiều argument, thứ tự của chúng quyết định index. Ví dụ:

~~~text
copy source.txt backup/source.txt --overwrite=true
~~~

Hai argument có index 0 và 1; overwrite là option có tên.

### 5.3. Nhiều argument với @Arguments

Khi command cần nhận một danh sách giá trị thay vì một argument đơn, có thể dùng annotation @Arguments trên tham số kiểu mảng hoặc collection. Mặc định, tham số này thu thập các argument còn lại. Thuộc tính arity giới hạn số argument được thu thập khi command có nhiều nhóm tham số:

~~~java
import org.springframework.shell.core.command.annotation.Arguments;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.stereotype.Component;

@Component
class GreetingCommands {

    @Command(name = "greet")
    void greet(@Arguments String[] names) {
        System.out.println(String.join(", ", names));
    }
}
~~~

Với lệnh greet -- Lan Minh An, parser tạo các argument theo thứ tự; bước binding đưa chúng vào mảng names. Nếu một phần tử chứa dấu cách, vẫn phải đặt phần tử đó trong dấu nháy, ví dụ greet -- "Lan Minh" An. Dấu nháy giữ một giá trị thành một argument; @Arguments gom nhiều argument thành một collection. Đây là hai việc khác nhau.

## 6. Ví dụ xuyên suốt: từ dòng nhập đến ParsedInput

Giả sử ứng dụng có command khai báo như sau:

~~~java
import org.springframework.shell.core.command.annotation.Argument;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
class ReportCommands {

    @Command(name = "report", description = "Tạo báo cáo")
    String generate(
            @Argument(index = 0, description = "Tên báo cáo") String title,
            @Option(longName = "format", defaultValue = "txt") String format,
            @Option(longName = "output") String output) {
        return "Đã tạo báo cáo: " + title;
    }
}
~~~

Người dùng nhập:

~~~text
report "Quarterly sales" --format=csv --output="reports/Q4 report.csv"
~~~

Có thể lần theo quá trình như sau:

1. JLine nhận các phím, cập nhật buffer và hiển thị dòng lệnh. Khi người dùng nhấn Enter, JLineInputProvider trả về dòng đã nhập.
2. InputProvider chuyển dòng đó tới vòng lặp của shell runner.
3. CommandParser nhận chuỗi thô và DefaultCommandParser phân tích cú pháp.
4. Parser nhận diện report là commandName. Không có subcommand.
5. Parser nhận diện format và output là hai option. Giá trị của chúng lần lượt là csv và reports/Q4 report.csv.
6. Parser nhận diện Quarterly sales là argument có index 0.
7. Parser trả về ParsedInput. Lớp thực thi dùng cấu trúc này cùng metadata command để tiếp tục xử lý lời gọi.

Kết quả ParsedInput được mô tả rút gọn:

~~~text
commandName = "report"
subCommands = []
options = [
  CommandOption(longName="format", value="csv", type=String),
  CommandOption(longName="output", value="reports/Q4 report.csv", type=String)
]
arguments = [
  CommandArgument(index=0, value="Quarterly sales")
]
~~~

Parser đã hoàn thành việc hiểu cấu trúc cú pháp. Việc gán argument vào tham số title, gán option vào format và output, áp dụng giá trị mặc định, chuyển kiểu, kiểm tra option bắt buộc và validation thuộc các bước xử lý tham số tiếp theo. Không nên nhầm việc tách từ với việc xác nhận dữ liệu nghiệp vụ hợp lệ.

## 7. Khi nào cần tùy biến CommandParser?

DefaultCommandParser đáp ứng cú pháp option và argument phổ biến. Spring Shell 4.x cho phép thay đổi quy tắc bằng cách triển khai CommandParser và đăng ký implementation phù hợp trong Spring application context. Framework sẽ sử dụng parser được cấu hình cho quá trình phân tích command.

Tùy biến chỉ cần thiết khi sản phẩm thực sự có ngôn ngữ lệnh riêng, chẳng hạn:

- Muốn dùng dấu phân cách hoặc quy tắc quote khác với cú pháp mặc định.
- Cần biểu diễn một cấu trúc lệnh đặc thù mà cú pháp command/subcommand/option hiện tại không thể diễn đạt.
- Phải tương thích với cú pháp của một công cụ CLI cũ.

Trước khi viết parser riêng, hãy xem có thể biểu diễn yêu cầu bằng command, subcommand, @Argument, @Option hoặc @Arguments hay không. Parser tùy chỉnh là thành phần hạ tầng: lỗi ở đây có thể ảnh hưởng đến mọi command trong ứng dụng. Cần có test cho dấu nháy, escape, option, argument, subcommand và input không hợp lệ.

## 8. Lỗi thường gặp khi phân tích dòng lệnh

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Giá trị bị tách thành nhiều argument | Giá trị có dấu cách nhưng không được đặt trong dấu nháy | Bao toàn bộ giá trị bằng dấu nháy đơn hoặc kép |
| Parser báo lỗi dù command tồn tại | Dấu nháy được mở nhưng chưa đóng | Kiểm tra cặp dấu nháy và ký tự escape |
| Option không nhận đúng giá trị | Dùng sai tên option hoặc thiếu giá trị sau option | Đối chiếu tên ngắn/dài đã đăng ký và truyền giá trị rõ ràng |
| Một chuỗi option ngắn không hoạt động | Đang viết gộp như -abc | Tách thành -a -b -c |
| Argument bị hiểu là subcommand | Command không khai báo option hoặc cú pháp có subcommand gây mơ hồ | Dùng -- trước danh sách argument |
| Dấu nháy xuất hiện trong giá trị ngoài ý muốn | Dấu nháy nằm giữa token, không bao toàn bộ giá trị | Đặt dấu nháy bao quanh toàn bộ giá trị |
| Escape không có tác dụng | Escape sequence nằm ngoài vùng được trích dẫn | Đặt giá trị trong dấu nháy và escape đúng ký tự |

Khi điều tra lỗi, hãy ghi lại chính xác dòng input mà người dùng đã gửi, sau đó kiểm tra theo thứ tự: dấu nháy và escape, ranh giới giữa command/subcommand, cú pháp option, vị trí argument, cuối cùng là metadata command. Cách này giúp xác định lỗi nằm ở cú pháp hay ở bước binding tham số.

## 9. Bài tập thực hành

Giả sử ứng dụng có command deploy, subcommand staging và option region, tag. Hãy phân tích dòng:

~~~text
deploy staging --region=ap-southeast-1 "release candidate" --tag="build 42"
~~~

Tự xác định:

1. commandName là gì?
2. subCommands chứa những giá trị nào?
3. Có bao nhiêu option và giá trị của mỗi option là gì?
4. Có bao nhiêu argument? Index và value của từng argument?
5. Vì sao release candidate chỉ là một argument?

Kết quả mong đợi:

~~~text
commandName = "deploy"
subCommands = ["staging"]
options = [
  ("region", "ap-southeast-1"),
  ("tag", "build 42")
]
arguments = [
  (index=0, value="release candidate")
]
~~~

Bài tập bổ sung: thử report --message=value1"inside"value2 và quan sát rằng dấu nháy nằm giữa token được giữ nguyên. Sau đó thử report --message="release candidate mà không có dấu nháy đóng để quan sát lỗi parsing.

## 10. Tài liệu tham khảo

- [Spring Shell – Command Syntax](https://docs.spring.io/spring-shell/reference/commands/syntax.html)
- [Spring Shell API – CommandParser](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/CommandParser.html)
- [Spring Shell API – DefaultCommandParser](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/DefaultCommandParser.html)
- [Spring Shell API – ParsedInput](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/ParsedInput.html)
- [Spring Shell API – InputProvider](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/InputProvider.html)
- [Spring Shell API – JLineInputProvider](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/jline/JLineInputProvider.html)
- [Spring Shell API – ExtendedDefaultParser](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/jline/ExtendedDefaultParser.html)

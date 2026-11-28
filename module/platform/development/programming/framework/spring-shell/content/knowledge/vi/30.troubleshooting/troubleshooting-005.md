# Tùy chọn không nhận giá trị do nháy, escape, arity hoặc tên khai báo

Một command Spring Shell có thể nhận đúng tên lệnh nhưng tham số option lại thành rỗng, bị cắt ở dấu cách, nhận nhầm một argument khác hoặc báo rằng option không có giá trị. Nguyên nhân thường nằm ở cách parser chia từ, cách đặt dấu nháy và escape, số token mà option được phép nhận hoặc tên option không khớp với khai báo.

Spring Shell 4 có parser riêng cho cú pháp command. Parser xử lý chuỗi input trước khi Spring bind option vào tham số method. Vì vậy, cần xác định lỗi xảy ra ở bước parse, bước nhận diện tên option hay bước chuyển kiểu dữ liệu. Chỉ nhìn giá trị cuối cùng trong method thường chưa đủ để phân biệt ba trường hợp này.

Bài này dùng Spring Shell 4.0.4 làm mốc. Một số khác biệt về arity và tên option là breaking change khi nâng từ Spring Shell 3.x lên 4.x.

## 1. Nhận diện triệu chứng trước khi sửa

| Triệu chứng | Nguyên nhân nên kiểm tra đầu tiên |
|---|---|
| Giá trị chỉ còn phần trước dấu cách | Chưa quote toàn bộ giá trị hoặc lớp shell bên ngoài đã xử lý dấu nháy |
| Giá trị có dấu nháy hoặc backslash sai | Escape không đúng hoặc đang dùng phiên bản có lỗi parser |
| Parser báo thiếu giá trị option | Thiếu token sau option, token kế tiếp bị nhận diện là option khác hoặc tên option không đúng |
| Option luôn nhận default value | Option không được nhận diện, không được truyền hoặc bị khai báo với tên khác |
| Giá trị thứ hai của danh sách biến thành argument | Đang dùng option đơn trị nhưng kỳ vọng option arity kiểu 3.x |
| Giá trị boolean không như mong đợi | Nhầm giữa boolean flag và option kiểu String |
| Báo lỗi chuyển đổi kiểu | Parser đã lấy được giá trị nhưng giá trị không chuyển được sang kiểu tham số |
| Option không được nhận diện | Sai short name/long name, alias cũ không còn được khai báo hoặc viết sai tên |

Hãy dùng một chuỗi đơn giản như **hello** để xác nhận option hoạt động trước. Sau đó thêm dấu cách, dấu nháy, backslash, nhiều token và kiểu dữ liệu phức tạp từng bước. Thay một yếu tố mỗi lần giúp khoanh vùng nguyên nhân.

## 2. Kiểm tra tên option trong khai báo

Trong Spring Shell 4, option được khai báo bằng **@Option** trên tham số method. **shortName** là một ký tự; **longName** là tên dài. Tên phải khớp với cú pháp người dùng nhập.

Ví dụ:

~~~java
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
public class TaskCommands {

    @Command(name = "task create", description = "Tạo một công việc.")
    public String create(
            @Option(shortName = 't', longName = "title", required = true)
            String title,
            @Option(shortName = 'p', longName = "priority", defaultValue = "normal")
            String priority,
            @Option(longName = "verbose")
            boolean verbose) {

        return "title=" + title
                + ", priority=" + priority
                + ", verbose=" + verbose;
    }
}
~~~

Với khai báo này:

| Tên nhập | Hợp lệ? | Lý do |
|---|---|---|
| **--title** | Có | Khớp longName |
| **-t** | Có | Khớp shortName |
| **--priority** | Có | Khớp longName |
| **-p** | Có | Khớp shortName |
| **--t** | Không | shortName không dùng tiền tố hai dấu gạch ngang |
| **-title** | Không | longName không dùng một dấu gạch ngang |
| **--name** | Không | Không có option tên name |
| **-tp** | Không | Short option không được ghép nhóm |

Spring Shell 4 chỉ hỗ trợ một short name và một long name cho mỗi option. Nếu code Spring Shell 3 từng khai báo nhiều alias bằng **shortNames(...)** hoặc **longNames(...)**, các alias phụ đó không tự chuyển sang phiên bản 4.

Ví dụ, khai báo cũ có các tên **--title**, **--name** và **-t**. Sau migration, nếu chỉ giữ **longName = "title"** và **shortName = 't'**, lời gọi dùng **--name** sẽ không còn được nhận diện. Hãy cập nhật script, tài liệu và completion theo tên mới.

## 3. Dùng đúng cú pháp gán giá trị

Spring Shell 4 hỗ trợ hai dạng cho option dài và hai dạng cho option ngắn:

~~~text
task create --title=Quarterly
task create --title Quarterly
task create -t=Quarterly
task create -t Quarterly
~~~

Với giá trị không có khoảng trắng, cả hai dạng đều dễ đọc. Nếu option nhận giá trị có khoảng trắng, quote toàn bộ giá trị:

~~~text
task create --title="Quarterly report"
task create --title='Quarterly report'
task create -t="Quarterly report"
task create -t 'Quarterly report'
~~~

Trong cả bốn trường hợp, giá trị method nhận được là **Quarterly report**. Dấu nháy bao ngoài không nằm trong giá trị.

Không viết option và giá trị liền nhau mà thiếu dấu bằng hoặc khoảng trắng:

~~~text
task create --titleQuarterly
~~~

Parser không thể tự đoán phần nào là tên option và phần nào là giá trị. Dùng **--title=Quarterly** hoặc **--title Quarterly**.

## 4. Quote toàn bộ giá trị có khoảng trắng

Spring Shell tách input thành các từ theo khoảng trắng. Nếu giá trị option chứa dấu cách, phải đặt dấu nháy bao quanh toàn bộ giá trị:

~~~text
task create --title="Báo cáo quý I"
~~~

Nếu bỏ dấu nháy:

~~~text
task create --title=Báo cáo quý I
~~~

parser có thể hiểu **Báo cáo** là giá trị option và **quý I** là các token tiếp theo. Kết quả là method nhận một phần giá trị, còn phần còn lại có thể bị bind thành argument hoặc làm command báo lỗi.

Dấu nháy chỉ bị loại bỏ khi chúng bao trọn giá trị. Ví dụ:

~~~text
task create --title=prefix"inside"value
~~~

Các dấu nháy ở giữa chuỗi được giữ như ký tự thông thường; chúng không có tác dụng ghép các phần thành một cụm như dấu nháy bao ngoài.

Quy tắc này áp dụng cả với positional argument:

~~~text
task search "lỗi kết nối cơ sở dữ liệu"
~~~

Nếu tham số là một giá trị duy nhất có dấu cách, hãy quote cả argument hoặc option value.

## 5. Chọn loại dấu nháy phù hợp

Spring Shell hỗ trợ cả dấu nháy đơn và dấu nháy kép. Dùng loại dấu nháy còn lại để chứa dấu nháy bên trong:

~~~text
task create --title="I'm here"
task create --title='He said "Done"'
~~~

Giá trị lần lượt là:

~~~text
I'm here
He said "Done"
~~~

Nếu nội dung cần chứa đúng loại dấu nháy đang dùng để bao ngoài, escape dấu nháy đó bằng backslash:

~~~text
task create --title="He said \"Done\""
task create --title='I\'m here'
~~~

Giá trị sau parse:

~~~text
He said "Done"
I'm here
~~~

Nếu giá trị cần chứa một backslash thật bên trong vùng được quote, escape nó thành hai backslash:

~~~text
task create --path="C:\\work\\reports\\q1.txt"
~~~

Giá trị nhận được:

~~~text
C:\work\reports\q1.txt
~~~

Escape sequence chỉ được xử lý bên trong vùng được quote. Một dấu backslash đứng ngoài dấu nháy không có cùng ý nghĩa với backslash nằm trong giá trị đã quote.

## 6. Không để dấu nháy mở

Input có dấu nháy không cân bằng bị parser từ chối:

~~~text
task create --title="Báo cáo quý I
~~~

Lệnh này thiếu dấu nháy kép đóng. Hãy kiểm tra:

- Đã có dấu nháy mở và đóng cùng loại chưa?
- Dấu nháy đóng có vô tình bị escape không?
- Có đang dùng dấu nháy cong như **“ ”** hoặc **‘ ’** thay cho dấu nháy ASCII không?
- Script có bị cắt dòng ngay giữa vùng quote không?
- Có một lớp shell bên ngoài đã loại bỏ hoặc thay đổi dấu nháy trước khi Spring Shell nhận input không?

Spring Shell chỉ nhận và phân tích chuỗi mà runner chuyển đến parser. Nếu ký tự đã bị thay đổi trước đó, sửa cú pháp bên trong Spring Shell sẽ không giải quyết được.

## 7. Phân biệt parser của Spring Shell với shell của hệ điều hành

Khi nhập command trực tiếp tại prompt Spring Shell, parser nhận dòng input do shell tương tác cung cấp. Khi khởi chạy JAR từ Bash, PowerShell, CMD hoặc một script, shell hệ điều hành xử lý quoting trước khi JVM nhận đối số.

Vì vậy có thể có hai lớp diễn giải:

1. Bash, PowerShell hoặc CMD tách command line và chuyển các argument cho JVM.
2. Spring Shell xử lý cú pháp command theo runner và parser của ứng dụng.

Không sao chép nguyên văn một dòng chạy trong REPL sang Bash hoặc PowerShell rồi mặc định kết quả giống nhau. Hãy test cả hai đường chạy nếu sản phẩm hỗ trợ cả tương tác và automation.

Khi dùng **ProcessBuilder** trong test Java, mỗi phần tử trong danh sách là một argument riêng và không có shell hệ điều hành tự động phân tích chuỗi. Không thêm dấu nháy Bash hoặc CMD quanh từng phần tử chỉ để giữ khoảng trắng. Hãy tạo test process-level với đúng runner mà ứng dụng phát hành sử dụng.

Ví dụ, nếu wrapper tự tạo chuỗi command line, cần kiểm tra cách wrapper quote giá trị có dấu cách trên từng hệ điều hành. Bash, PowerShell và CMD không có cùng quy tắc escape.

## 8. Kiểm tra option boolean

Option khai báo kiểu **boolean** hoặc **Boolean** có thể được gọi không cần giá trị:

~~~text
task create --verbose
~~~

Lời gọi này đặt **verbose = true**.

Có thể truyền giá trị tường minh:

~~~text
task create --verbose=true
task create --verbose=false
task create --verbose true
task create --verbose false
~~~

Khi dùng dạng có khoảng trắng, token tiếp theo chỉ được tiêu thụ làm giá trị boolean nếu nó là **true** hoặc **false** (không phân biệt chữ hoa/chữ thường). Nếu token tiếp theo là một từ khác, token đó vẫn được xem như argument.

Ví dụ:

~~~text
task create --verbose report
~~~

Trong trường hợp này, **report** không phải giá trị boolean nên vẫn là argument. Người dùng có thể nghĩ option đã nhận giá trị report, nhưng thực tế method nhận **verbose = true** và argument report được xử lý riêng.

Các option không phải boolean cần một giá trị. Đừng gọi option String như một flag không giá trị:

~~~text
task create --title
~~~

Hãy truyền giá trị sau dấu bằng hoặc sau khoảng trắng.

Short option không được ghép nhóm. Ví dụ **-abc** không phải cách viết gộp của ba flag **-a**, **-b**, **-c**; hãy viết từng option riêng.

## 9. Kiểm tra defaultValue và required

Khai báo option có thể quy định **required** và **defaultValue**:

~~~java
@Option(longName = "priority", defaultValue = "normal")
String priority
~~~

Nếu người dùng không truyền option, Spring Shell dùng giá trị mặc định đã khai báo. Nếu option bắt buộc:

~~~java
@Option(longName = "title", required = true)
String title
~~~

parser/binder phải báo lỗi khi thiếu option bắt buộc.

Khi method luôn nhận **normal** dù người dùng đã truyền **--priority=high**, hãy kiểm tra theo thứ tự:

1. Tên option trong lệnh có đúng longName hoặc shortName không?
2. Option có được khai báo trên đúng command method không?
3. Lệnh có thực sự gọi đúng command/subcommand không?
4. Giá trị có bị tách thành argument do thiếu quote không?
5. Có wrapper hoặc custom parser đang thay đổi input không?
6. Method có đang ghi đè giá trị đã bind bằng một default riêng không?

Không kết luận parser lỗi chỉ vì biến có giá trị mặc định. Trước tiên hãy xác nhận option có được nhận diện và truyền vào đúng tham số.

## 10. Kiểm tra thay đổi arity khi nâng từ Spring Shell 3 lên 4

Đây là nguyên nhân thường gặp khi nâng phiên bản. Spring Shell 3 hỗ trợ option nhiều giá trị qua **OptionArity**, ví dụ:

- **ZERO**
- **ZERO_OR_ONE**
- **EXACTLY_ONE**
- **ZERO_OR_MORE**
- **ONE_OR_MORE**

Spring Shell 4 đã bỏ option arity. Một option là một giá trị được đặt tên. Nếu code cũ dùng option để nhận một danh sách token, không thể giữ nguyên hành vi chỉ bằng cách đổi package hoặc đổi annotation.

Ví dụ cách nghĩ cũ:

~~~text
task delete --ids 101 102 103
~~~

Nếu option **--ids** trước đây có arity nhiều giá trị, sau khi nâng cấp các token tiếp theo không còn được gom vào option theo cơ chế cũ. Token dư có thể bị xem là positional argument hoặc gây lỗi khi bind.

Trong Spring Shell 4, dữ liệu nhiều giá trị thường được mô hình hóa thành positional arguments bằng **@Arguments** trên mảng hoặc collection:

~~~java
import java.util.List;

import org.springframework.shell.core.command.annotation.Arguments;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.stereotype.Component;

@Component
public class TaskDeleteCommands {

    @Command(name = "task delete", description = "Xóa các công việc theo mã.")
    public String delete(
            @Arguments(description = "Danh sách mã công việc", arity = 10)
            List<String> ids) {

        if (ids.isEmpty()) {
            return "Cần cung cấp ít nhất một mã công việc.";
        }
        return "Số công việc được chọn: " + ids.size();
    }
}
~~~

Lời gọi tương ứng:

~~~text
task delete 101 102 103
~~~

**@Arguments** nhận mảng hoặc collection. Nếu không đặt arity, nó thu thập các argument còn lại. Khi đặt arity, giá trị đó giới hạn số token tối đa được gom; các token còn lại được xử lý như argument hoặc option riêng. Arity ở đây không tự bảo đảm số lượng tối thiểu hoặc chính xác theo nghiệp vụ. Nếu cần đúng hai giá trị, hãy kiểm tra kích thước collection trong command.

Nếu bắt buộc phải giữ cú pháp có tên như **--ids**, hãy thiết kế option đó thành một giá trị đơn, ví dụ một chuỗi có định dạng được công bố rõ ràng, rồi parse và validate chuỗi trong service. Không giả định Spring Shell 4 sẽ tự gom nhiều token sau một option như Spring Shell 3.

## 11. Phân biệt option đơn trị với argument nhiều giá trị

Trong Spring Shell 4:

| Nhu cầu | Cách khai báo |
|---|---|
| Một chuỗi tên công việc | **@Option** hoặc **@Argument** kiểu String |
| Một số lượng | **@Option** kiểu int hoặc long |
| Một giá trị enum | **@Option** kiểu enum |
| Một đường dẫn | **@Option** kiểu Path |
| Một danh sách positional token | **@Arguments** trên List hoặc array |
| Một số lượng token giới hạn | **@Arguments(arity = n)** |

Không dùng **@Arguments** với kỳ vọng nó sẽ thu thập nhiều giá trị cho một option có tên. Nó nhận positional arguments. Nếu cú pháp nghiệp vụ cần một option nhiều giá trị, hãy cân nhắc thay đổi cú pháp hoặc dùng một định dạng đơn trị có quy tắc parse riêng.

## 12. Kiểm tra kiểu dữ liệu sau khi parser đã nhận giá trị

Một số trường hợp option đã được parse đúng nhưng method vẫn không nhận giá trị mong đợi vì conversion hoặc validation:

~~~java
@Command(name = "task limit")
public String limit(
        @Option(longName = "count", required = true) int count) {
    return "count=" + count;
}
~~~

Các lời gọi:

~~~text
task limit --count=5
task limit --count=abc
~~~

Lệnh đầu có thể chuyển thành số nguyên. Lệnh thứ hai có token giá trị nhưng không thể chuyển thành **int**. Đây là lỗi conversion, không phải lỗi quote hoặc tên option.

Khi chẩn đoán:

- Tạm dùng kiểu **String** để xác nhận parser đã lấy đúng văn bản.
- Sau khi xác nhận, đổi lại kiểu domain mong muốn.
- Kiểm tra thông báo conversion/validation riêng.
- Không chuyển mọi tham số về String trong code production chỉ để né lỗi chuyển kiểu.

Với enum, xác nhận tên giá trị có tồn tại và đúng quy tắc chuyển đổi. Với Path hoặc số, kiểm tra giá trị có đúng định dạng và nằm trong phạm vi cho phép.

## 13. Dùng help để xác minh khai báo

Trước khi thử nhiều biến thể quote, xem help của đúng command:

~~~text
help task create
task create --help
~~~

Kiểm tra:

- Tên command và subcommand.
- Short name và long name của từng option.
- Option có bắt buộc hay có default value.
- Kiểu dữ liệu hoặc mô tả giá trị.
- Positional arguments và danh sách arguments.

Nếu help không hiển thị option như mong đợi, vấn đề có thể nằm ở command registration, component scan hoặc khai báo annotation thay vì cú pháp người dùng nhập.

Trong Spring Shell 4, **@Option** có các thuộc tính **shortName**, **longName**, **description**, **required** và **defaultValue**. Hãy xác nhận method nằm trong bean Spring được quản lý và command đã được đăng ký.

## 14. Kiểm tra nhanh giá trị thực tế mà method nhận

Khi cần xác nhận parser đã bind giá trị nào, có thể tạo một command chẩn đoán tạm trong môi trường phát triển:

~~~java
@Command(name = "debug option")
public String debugOption(
        @Option(longName = "message") String message) {

    if (message == null) {
        return "message=null";
    }
    return "message-present=true, length=" + message.length();
}
~~~

Thử các input:

~~~text
debug option --message=hello
debug option --message="hello world"
debug option --message="He said \"Hi\""
debug option --message='C:\\work\\file.txt'
~~~

Chỉ in độ dài hoặc trạng thái có/không nếu giá trị có thể chứa token, mật khẩu hoặc dữ liệu nhạy cảm. Không ghi raw option value vào log production chỉ để chẩn đoán.

Sau khi xác nhận parser và binder, xóa command debug tạm hoặc giới hạn nó trong profile phát triển.

## 15. Kiểm tra phiên bản parser và lỗi escaped quote

Spring Shell 4.0.4 có bản sửa cho lỗi **#1374**, liên quan đến việc xử lý escaped quote không chính xác trong **DefaultCommandParser**.

Nếu ứng dụng đang dùng Spring Shell 4.0.3 hoặc cũ hơn và giá trị có dấu nháy escape bị cắt, bị giữ sai ký tự hoặc làm parser hiểu nhầm token, hãy:

1. Ghi lại input nhỏ nhất có thể tái hiện lỗi.
2. Chạy lại cùng input với quote đơn và quote kép.
3. Kiểm tra backslash trước dấu nháy có đúng quy tắc không.
4. Nâng lên Spring Shell 4.0.4 hoặc bản vá mới hơn tương thích.
5. Chạy lại test parser trên đúng phiên bản runtime mà ứng dụng phát hành.

Không viết workaround escape nhiều lần trước khi xác định phiên bản. Một chuỗi đã được escape để né lỗi cũ có thể trở thành dữ liệu sai khi chạy trên phiên bản đã sửa.

## 16. Khi nào cần tùy biến CommandParser?

Spring Shell 4 có **CommandParser** và implementation mặc định **DefaultCommandParser**. Parser mặc định hỗ trợ cú pháp option, argument, quote và escape đã mô tả ở trên.

Chỉ cân nhắc parser tùy chỉnh khi ứng dụng thật sự cần một grammar khác, ví dụ:

- Muốn dùng cú pháp option riêng của một hệ thống cũ.
- Cần quy tắc quote đặc thù không tương thích parser mặc định.
- Cần chuyển đổi một định dạng input chuyên biệt trước khi tạo ParsedInput.

Parser tùy chỉnh được đăng ký thành bean trong application context. Trước khi thay parser, hãy xác nhận lỗi không đến từ tên option, khai báo arity cũ, version bug hoặc lớp shell của hệ điều hành.

Một parser tự viết phải xử lý nhất quán tên command, option, argument, quote và lỗi cú pháp. Nếu chỉ cần hỗ trợ một alias cũ hoặc một định dạng danh sách, thường nên chuyển đổi ở wrapper hoặc tầng command thay vì thay toàn bộ parser.

## 17. Ma trận tái hiện lỗi

Sau khi sửa, chạy lại các ca sau trên đúng phiên bản Spring Shell và runner sẽ phát hành:

| Nhóm | Input | Kết quả cần xác nhận |
|---|---|---|
| Tên dài | **--title=hello** | Bind đúng option |
| Tên dài có khoảng trắng | **--title="hello world"** | Nhận đủ chuỗi |
| Tên ngắn | **-t=hello** | Bind đúng option |
| Tên ngắn có khoảng trắng | **-t "hello world"** | Nhận đủ chuỗi |
| Dấu nháy đơn | **--title='hello world'** | Bỏ dấu nháy bao ngoài |
| Dấu nháy kép | **--title="hello world"** | Bỏ dấu nháy bao ngoài |
| Nháy lồng khác loại | **--title='He said "Hi"'** | Giữ dấu nháy bên trong |
| Escape nháy kép | **--title="He said \"Hi\""** | Nhận dấu nháy kép literal |
| Escape backslash | **--path="C:\\work\\file.txt"** | Nhận backslash đúng |
| Quote không cân bằng | **--title="hello** | Parser báo lỗi |
| Option không tồn tại | **--name=hello** | Báo option không được khai báo |
| Boolean flag | **--verbose** | Giá trị true |
| Boolean false | **--verbose=false** | Giá trị false |
| Boolean token sau option | **--verbose false** | Giá trị false |
| Short option ghép | **-abc** | Không được coi là ba option |
| Giá trị sai kiểu | **--count=abc** cho int | Báo lỗi conversion |
| Option nhiều token kiểu 3.x | **--ids 1 2 3** | Không giả định option gom cả ba token trong v4 |
| Arguments nhiều token | **task delete 1 2 3** với @Arguments | Collection nhận các token theo arity |
| Runner bên ngoài | Gọi từ Bash/PowerShell/ProcessBuilder | Kết quả phù hợp với argv thực tế |

## 18. Quy trình xử lý sự cố theo thứ tự

Khi người dùng báo option không nhận giá trị, xử lý theo thứ tự:

1. Mở help và xác nhận tên option được khai báo.
2. Thử một giá trị đơn giản không có dấu cách: **--option=value**.
3. Thử dạng tách token: **--option value**.
4. Thêm dấu nháy bao quanh toàn bộ giá trị có khoảng trắng.
5. Thử đổi loại quote và escape đúng dấu nháy bên trong.
6. Kiểm tra có token nào bắt đầu bằng dấu gạch ngang khiến parser nhận nhầm thành option khác không.
7. Xác nhận kiểu boolean hay kiểu dữ liệu thông thường.
8. Kiểm tra option có arity nhiều giá trị từ code Spring Shell 3 cũ không.
9. Xác nhận tên short/long và alias đã chuyển đúng sang Spring Shell 4.
10. Xác nhận conversion và Bean Validation sau bước parse.
11. Kiểm tra phiên bản, đặc biệt lỗi escaped quote được sửa trong 4.0.4.
12. Nếu chỉ runner bên ngoài bị lỗi, kiểm tra lớp quoting của Bash/PowerShell/CMD và cách chuyển argv.
13. Chỉ viết CommandParser tùy chỉnh khi grammar mặc định thực sự không đáp ứng yêu cầu.

## 19. Lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Giá trị bị cắt tại khoảng trắng | Không quote toàn bộ giá trị | Dùng nháy đơn hoặc kép bao quanh |
| Dấu nháy còn trong giá trị | Quote không bao toàn bộ chuỗi | Đặt quote ở đầu và cuối value |
| Dấu nháy lồng bị mất | Chưa escape loại quote trùng với quote bao ngoài | Escape bằng backslash |
| Backslash bị mất | Chưa escape backslash bên trong vùng quote | Dùng hai backslash cho một backslash literal |
| Parser báo quote lỗi | Thiếu quote đóng hoặc escape nhầm quote đóng | Kiểm tra cặp quote và backslash |
| Option không nhận diện | Sai tên khai báo hoặc dùng alias cũ | Đối chiếu @Option shortName/longName |
| Option luôn có default | Option không được truyền hoặc tên không khớp | Kiểm tra help và tên lệnh thực tế |
| Giá trị thứ hai không thuộc option | Kỳ vọng option arity kiểu 3.x | Chuyển sang @Arguments hoặc thiết kế option đơn trị |
| Boolean nhận true ngoài dự kiến | Flag không có value hoặc token sau không phải true/false | Truyền --flag=false rõ ràng |
| Short option không hoạt động | Ghép nhiều short option | Viết từng option riêng |
| Giá trị có dấu gạch đầu dòng bị hiểu nhầm | Token trông giống option tiếp theo | Dùng dạng --key=-value để gắn giá trị cùng token |
| Lỗi chỉ xuất hiện ngoài REPL | Shell hệ điều hành đã xử lý quote trước JVM | Kiểm thử runner và wrapper theo hệ điều hành |
| Escape quote sai trên bản cũ | DefaultCommandParser có lỗi đã được sửa ở 4.0.4 | Nâng phiên bản và chạy regression test |
| Method nhận chuỗi nhưng conversion thất bại | Kiểu tham số không phù hợp giá trị | Kiểm tra converter và validation |

## 20. Checklist trước khi kết luận parser bị lỗi

- [ ] Tên option nhập vào khớp đúng shortName hoặc longName.
- [ ] Option có một short name và một long name đúng theo Spring Shell 4.
- [ ] Dạng --key=value hoặc --key value được viết đúng.
- [ ] Giá trị có khoảng trắng được quote toàn bộ.
- [ ] Dấu nháy lồng được escape đúng loại.
- [ ] Backslash literal được escape trong vùng quote.
- [ ] Không có dấu nháy mở chưa đóng.
- [ ] Boolean option được phân biệt với option cần giá trị.
- [ ] Không ghép nhóm short option.
- [ ] Không kỳ vọng option arity của Spring Shell 3 còn hoạt động ở v4.
- [ ] Danh sách positional được khai báo bằng @Arguments.
- [ ] Giá trị đã parse có thể chuyển sang kiểu tham số.
- [ ] Đã kiểm tra phiên bản Spring Shell, nhất là bản sửa escaped quote ở 4.0.4.
- [ ] Đã test riêng REPL và runner từ hệ điều hành.
- [ ] Chỉ tùy biến CommandParser khi thật sự cần grammar khác.

Khi option không nhận giá trị, hãy kiểm tra từ tên khai báo đến token mà parser thực sự nhìn thấy. Quote đúng giúp giữ một giá trị có khoảng trắng thành một token; arity xác định số token được thu thập; shortName và longName quyết định parser có nhận diện option hay không. Phân biệt rõ các bước này sẽ giúp tìm nguyên nhân nhanh và tránh sửa nhầm logic nghiệp vụ.

## Tài liệu tham khảo

- [Spring Shell 4 — Command Syntax](https://docs.spring.io/spring-shell/reference/commands/syntax.html) — cú pháp option/argument, quoting, escaping, boolean và parser.
- [Spring Shell 4 API — @Option](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/Option.html) — khai báo shortName, longName, required và defaultValue.
- [Spring Shell 4 API — @Arguments](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/Arguments.html) — gom positional arguments vào array hoặc collection và giới hạn arity.
- [Spring Shell 4 API — CommandParser](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/CommandParser.html) — hợp đồng parser để tùy biến grammar.
- [Spring Shell 4 API — CommandContext](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/CommandContext.html) — truy cập option và argument đã parse trong command.
- [Spring Shell v4 Migration Guide — Command option arity changes](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide#command-option-arity-changes) — lý do option arity của v3 được thay bằng positional arguments trong v4.
- [Spring Shell issue #1263](https://github.com/spring-projects/spring-shell/issues/1263) — thay đổi option arity và cách chuyển sang @Arguments.
- [Spring Shell release v4.0.4](https://github.com/spring-projects/spring-shell/releases/tag/v4.0.4) — bản sửa #1374 về escaped quotes trong DefaultCommandParser.
- [Spring Shell issue #1374](https://github.com/spring-projects/spring-shell/issues/1374) — lỗi xử lý escaped quotes được ghi nhận trong parser.

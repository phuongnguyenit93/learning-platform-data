# Tùy chọn dài và tùy chọn ngắn

Một command thường cần thêm thông tin để biết định dạng đầu ra, đường dẫn lưu file, phạm vi xử lý hoặc chế độ chạy. Spring Shell biểu diễn các giá trị này bằng option có tên. Người dùng có thể truyền option bằng tên dài, dễ đọc trong script và tài liệu, hoặc tên ngắn, thuận tiện khi gõ trong terminal.

Ví dụ, cùng một option định dạng có thể được gọi bằng `--format` hoặc `-f`:

~~~text
report --format=json
report -f=json
~~~

Hai cách viết trên cùng truyền giá trị `json` cho một tham số của command. Để thiết kế CLI dễ dùng, cần hiểu cách khai báo hai tên này, cú pháp truyền giá trị, quy tắc với Boolean và các giới hạn của parser Spring Shell.

## 1. Option khác argument như thế nào?

Argument là giá trị theo vị trí. Option là giá trị được nhận diện bằng tên và tiền tố:

| Loại đầu vào | Cách viết | Cách framework xác định |
|---|---|---|
| Argument | `report quarterly` | Dựa vào vị trí của `quarterly` |
| Option dài | `--format=json` | Dựa vào tên dài `format` |
| Option ngắn | `-f=json` | Dựa vào ký tự tên ngắn `f` |

Khi command có nhiều tham số, option giúp dòng lệnh tự mô tả hơn. Ví dụ `deploy production --region=ap-southeast-1` cho biết rõ giá trị `production` là argument theo vị trí, còn vùng triển khai được gắn với tên `region`.

Trong Spring Shell 4.x, option được khai báo bằng annotation `@Option` trên tham số của phương thức command. Argument được khai báo bằng `@Argument`. Option có tên, còn argument có index.

## 2. Tên dài và tên ngắn

Tên dài bắt đầu bằng hai dấu gạch ngang (`--`) và thường có nhiều ký tự. Tên ngắn bắt đầu bằng một dấu gạch ngang (`-`) và chỉ gồm một ký tự:

~~~text
--format
-f
--output
-o
--dry-run
-d
~~~

Tên dài diễn đạt mục đích của tham số nên dễ đọc trong tài liệu, lịch sử terminal và script. Tên ngắn giúp người dùng nhập nhanh khi thao tác thường xuyên. Hai tên có thể cùng trỏ đến một tham số:

~~~java
@Option(
        shortName = 'f',
        longName = "format",
        description = "Định dạng file xuất"
)
String format
~~~

Với khai báo này, `--format` và `-f` là hai cách gọi của cùng option `format`. Người dùng không phải truyền cả hai tên; chỉ chọn một cách viết trong mỗi lần gọi.

Một option cũng có thể chỉ khai báo tên dài hoặc chỉ khai báo tên ngắn. Khi không khai báo một trong hai, người dùng chỉ có thể gọi bằng tên còn lại. Nên cung cấp cả hai cho các option quan trọng nếu tên ngắn có ý nghĩa và không gây trùng lặp.

## 3. Khai báo bằng @Option trong Spring Shell 4.x

`@Option` cung cấp các thuộc tính chính sau:

| Thuộc tính | Kiểu | Ý nghĩa |
|---|---|---|
| `longName` | `String` | Tên dài của option, không gồm tiền tố `--` |
| `shortName` | `char` | Ký tự tên ngắn, không gồm tiền tố `-` |
| `description` | `String` | Mô tả ngắn hiển thị trong trợ giúp |
| `required` | `boolean` | Đánh dấu option bắt buộc |
| `defaultValue` | `String` | Giá trị mặc định khi người dùng không truyền option |

Ví dụ một command có cả option dài và ngắn:

~~~java
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
class ReportCommands {

    @Command(name = "report", description = "Xuất báo cáo")
    public String export(
            @Option(
                    shortName = 'f',
                    longName = "format",
                    description = "Định dạng csv hoặc json",
                    defaultValue = "csv"
            )
            String format,
            @Option(
                    shortName = 'o',
                    longName = "output",
                    description = "Đường dẫn file đầu ra",
                    required = true
            )
            String output) {

        return "Xuất báo cáo định dạng " + format
                + " tới " + output;
    }
}
~~~

Trong ví dụ, `format` là tùy chọn vì có `defaultValue`, còn `output` là bắt buộc. Khi người dùng không truyền `format`, command nhận giá trị mặc định `csv`. Nếu thiếu `output`, framework báo lỗi đầu vào vì option được đánh dấu `required = true`.

## 4. Các cách truyền giá trị

Spring Shell 4.x hỗ trợ hai cách viết cho mỗi dạng tên:

| Dạng option | Cách viết gắn bằng dấu `=` | Cách viết cách bằng khoảng trắng |
|---|---|---|
| Tên dài | `--format=json` | `--format json` |
| Tên ngắn | `-f=json` | `-f json` |

Vì vậy, các lệnh sau tương đương:

~~~text
report --format=json --output=reports/q1.json
report --format json --output reports/q1.json
report -f=json -o=reports/q1.json
report -f json -o reports/q1.json
~~~

Không đưa tiền tố vào thuộc tính annotation. Khai báo `longName = "format"` và `shortName = 'f'`; không khai báo `longName = "--format"` hoặc `shortName = '-f'`.

## 5. Option có thể xuất hiện ở nhiều vị trí

Option và argument có thể được viết theo thứ tự khác nhau. Parser nhận diện option bằng tên thay vì vị trí của nó:

~~~text
report quarterly --format=json --output=q1.json
report --format=json quarterly --output=q1.json
report --output=q1.json quarterly -f=json
~~~

Trong cả ba lệnh, `quarterly` vẫn là argument theo vị trí, `format` vẫn nhận `json`, và `output` vẫn nhận `q1.json`.

Đối với command có nhiều argument hoặc subcommand, nên ưu tiên option có tên cho những giá trị dễ nhầm lẫn. Điều này giúp dòng lệnh rõ nghĩa hơn khi được đọc lại trong script hoặc log.

## 6. Giá trị có khoảng trắng và dấu nháy

Nếu giá trị option chứa khoảng trắng, đặt toàn bộ giá trị trong dấu nháy đơn hoặc dấu nháy kép:

~~~text
report --output="reports/quarter one.json"
report -o 'reports/quarter one.json'
~~~

Dấu nháy bao ngoài không trở thành một phần của giá trị. Có thể dùng loại dấu nháy còn lại bên trong giá trị:

~~~text
report --label="Director's report"
report --label='Report named "Quarter One"'
~~~

Nếu cần đưa chính loại dấu nháy bao ngoài vào giá trị, escape dấu nháy đó bằng dấu gạch chéo ngược:

~~~text
report --label="The \"final\" report"
report --label='It\'s final'
~~~

Các quy tắc này thuộc parser của Spring Shell. Không mặc định rằng shell hệ điều hành sẽ mở rộng biến môi trường, wildcard hoặc command substitution trong chuỗi được truyền cho Spring Shell.

## 7. Option Boolean phải có giá trị trong cú pháp 4.x

Một điểm dễ gây nhầm là option Boolean thường được gọi là “flag” trong các công cụ CLI. Tuy nhiên, cú pháp parser mặc định của Spring Shell 4.x yêu cầu mỗi option được chỉ định phải có một giá trị, kể cả option Boolean. Cách viết rõ ràng là:

~~~text
deploy --dry-run=true
deploy --dry-run=false
deploy -d=true
deploy -d false
~~~

Ví dụ khai báo:

~~~java
@Option(
        shortName = 'd',
        longName = "dry-run",
        description = "Chạy thử, không ghi thay đổi",
        defaultValue = "false"
)
boolean dryRun
~~~

Khi người dùng bỏ qua option, giá trị mặc định là `false`. Khi cần bật chế độ chạy thử, truyền `--dry-run=true` hoặc `-d=true`.

Không viết `-abc` để gộp ba option ngắn trong parser mặc định 4.x. Short option không hỗ trợ nhóm ký tự; hãy viết từng option riêng và truyền giá trị tương ứng. Ví dụ, nếu `a`, `b`, `c` đều là option Boolean:

~~~text
tool -a=true -b=true -c=false
~~~

Một số tài liệu hoặc ví dụ cũ của Spring Shell 3.x mô tả cách dùng Boolean như flag không cần giá trị và khả năng gộp short option. Khi làm việc với Spring Shell 4.x, hãy theo cú pháp parser 4.x ở trên; đừng áp dụng hành vi của phiên bản cũ cho ứng dụng mới.

## 8. Quy ước đặt tên option dễ dùng

Nên thống nhất cách đặt tên trong toàn bộ CLI:

- Dùng tên dài mô tả rõ mục đích, chẳng hạn `--output`, `--format`, `--dry-run`, `--page-size`.
- Dùng tên ngắn dễ nhớ cho option được dùng thường xuyên, chẳng hạn `-o`, `-f`, `-d`, `-p`.
- Tránh dùng cùng một ký tự ngắn cho hai ý nghĩa trong cùng một command.
- Tránh tên quá chung như `--value` hoặc `--type` nếu có thể đặt tên cụ thể hơn.
- Giữ cùng một ý nghĩa cho option dùng chung giữa nhiều command. Ví dụ `-o` luôn có thể là output khi phù hợp.
- Mô tả option bằng câu ngắn, nói rõ đơn vị hoặc tập giá trị hợp lệ nếu điều đó quan trọng.

Tên dài nên dùng dạng kebab-case để dễ đọc, ví dụ `--output-file` hoặc `--include-headers`. Tên ngắn chỉ có một ký tự nên cần được chọn cẩn thận; không phải option nào cũng cần tên ngắn.

## 9. Giá trị mặc định, bắt buộc và validation

Option có thể được đánh dấu bắt buộc bằng `required = true`, hoặc có giá trị mặc định bằng `defaultValue`. Hai cách này phục vụ các tình huống khác nhau:

| Nhu cầu | Cách khai báo | Hành vi |
|---|---|---|
| Người dùng phải chỉ định | `required = true` | Thiếu option thì đầu vào không hợp lệ |
| Có giá trị dùng sẵn | `defaultValue = "csv"` | Bỏ qua option thì dùng `csv` |
| Giá trị cần kiểm tra | Bean Validation hoặc kiểm tra trong command/service | Từ chối giá trị ngoài quy tắc |

Ví dụ giới hạn định dạng:

~~~java
import jakarta.validation.constraints.Pattern;

@Option(
        shortName = 'f',
        longName = "format",
        defaultValue = "csv",
        description = "Định dạng csv hoặc json"
)
@Pattern(regexp = "csv|json")
String format
~~~

Bean Validation cần được cấu hình trong ứng dụng. Nếu chưa dùng validation, có thể kiểm tra trực tiếp trong command và trả về thông báo dễ hiểu. Không nên chỉ dựa vào mô tả trợ giúp để bảo vệ dữ liệu nghiệp vụ.

## 10. Trợ giúp và khả năng khám phá option

`description` giúp người dùng hiểu ý nghĩa của option khi xem trợ giúp command. Hãy viết mô tả cụ thể và giữ đồng nhất với cách dùng thực tế:

~~~java
@Option(
        shortName = 'o',
        longName = "output",
        description = "File đích để ghi báo cáo",
        required = true
)
String output
~~~

Một option có cả tên dài và ngắn vẫn chỉ đại diện cho một giá trị. Trong tài liệu sử dụng, nên trình bày cả hai dạng cạnh nhau, ví dụ `--output`, `-o`, để người dùng biết chúng có thể thay thế cho nhau.

Khi kiểm tra một command mới, hãy gọi `help` của shell hoặc trợ giúp dành cho command đó để xác nhận tên option, mô tả và trạng thái bắt buộc đã được công bố đúng. Nếu option không xuất hiện, kiểm tra command bean đã được đăng ký và annotation nằm trên đúng tham số phương thức command.

## 11. Ví dụ sử dụng và kết quả

Với `ReportCommands` ở phần trên, các lệnh sau có ý nghĩa:

~~~text
report --output=reports/monthly.csv
report -o reports/monthly.csv
report --format=json --output=reports/annual.json
report -f=json -o=reports/annual.json
~~~

Hai lệnh đầu dùng giá trị mặc định `csv`. Hai lệnh sau chọn `json`. Nếu bỏ `--output` hoặc `-o`, command không đáp ứng yêu cầu vì output là option bắt buộc.

Khi đọc một dòng lệnh, có thể phân tích theo trình tự:

1. Xác định command và subcommand.
2. Tìm option dài bắt đầu bằng `--` và option ngắn bắt đầu bằng `-`.
3. Đọc giá trị sau dấu `=` hoặc token tiếp theo.
4. Bỏ dấu nháy bao ngoài của giá trị đã trích dẫn.
5. Kiểm tra option có được khai báo hay không, có bắt buộc không và có giá trị mặc định không.
6. Chuyển kiểu và validation trước khi gọi nghiệp vụ.

## 12. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách khắc phục |
|---|---|---|
| `--format` không được nhận diện | Tên dài khai báo khác hoặc chưa khai báo | Kiểm tra `longName` và cách viết chính tả |
| `-f` không được nhận diện | Chưa khai báo `shortName` hoặc dùng sai ký tự | Kiểm tra `shortName = 'f'` |
| Giá trị bị tách thành nhiều phần | Giá trị chứa khoảng trắng nhưng thiếu dấu nháy | Bao giá trị bằng dấu nháy đơn hoặc kép |
| Option Boolean báo thiếu giá trị | Gọi option mà không truyền `true` hoặc `false` | Dùng `--dry-run=true` hoặc `-d=false` |
| `-abc` không hoạt động | Đang gộp nhiều short option | Viết từng option riêng |
| Thiếu option bắt buộc | Option được khai báo `required = true` nhưng không được truyền | Bổ sung option hoặc điều chỉnh yêu cầu command |
| Dùng nhầm tên trong annotation | Đưa cả tiền tố `--` hoặc `-` vào thuộc tính tên | Chỉ ghi tên thuần hoặc một ký tự |
| Giá trị mặc định không như mong đợi | Chưa khai báo `defaultValue` hoặc đang kiểm tra nhầm tham số | Kiểm tra metadata và giá trị thực nhận |

## 13. Bài tập thực hành

Tạo command `backup` nhận các option:

- `--source`, tên ngắn `-s`: thư mục nguồn, bắt buộc.
- `--destination`, tên ngắn `-d`: thư mục đích, mặc định là `backup`.
- `--compress`, tên ngắn `-c`: Boolean, mặc định là `false`.
- `--format`, tên ngắn `-f`: định dạng `zip` hoặc `tar`, mặc định là `zip`.

Thử các cách gọi:

~~~text
backup --source=documents
backup -s documents -d archive
backup --source=documents --compress=true --format=tar
backup -s=documents -c=false -f=zip
~~~

Sau đó tự kiểm tra:

1. Tên dài và tên ngắn có đưa về cùng tham số không?
2. Khi bỏ `--destination`, giá trị mặc định có được dùng không?
3. Khi bỏ `--source`, framework có báo thiếu option bắt buộc không?
4. `--compress` có yêu cầu truyền `true` hoặc `false` trong cú pháp 4.x không?
5. Dòng `backup -sc` có được chấp nhận không? Vì sao?

## Tài liệu tham khảo

- [Spring Shell – Command Syntax](https://docs.spring.io/spring-shell/reference/commands/syntax.html)
- [Spring Shell API – @Option](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/Option.html)
- [Spring Shell – Options](https://docs.spring.io/spring-shell/reference/options/index.html)
- [Spring Shell – Option Types](https://docs.spring.io/spring-shell/reference/options/types.html)

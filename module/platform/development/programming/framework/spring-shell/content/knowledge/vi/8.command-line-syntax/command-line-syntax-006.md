# Thứ tự giữa tên lệnh, lệnh con, tùy chọn và đối số

Một dòng lệnh Spring Shell gồm hai phần dễ nhận biết: phần đầu xác định command cần chạy, phần còn lại cung cấp dữ liệu cho command đó. Phần xác định command có thể gồm tên lệnh và nhiều cấp tên lệnh con. Sau phần này, người dùng truyền option có tên hoặc argument theo vị trí.

Hiểu đúng thứ tự giúp tránh nhầm một từ đáng lẽ là tên lệnh con thành dữ liệu đầu vào, đồng thời giúp thiết kế command dễ đọc trong terminal và script. Bài viết sử dụng cú pháp mặc định của Spring Shell 4.0.3; nếu ứng dụng đăng ký `CommandParser` tùy chỉnh, quy tắc thực tế có thể khác.

## Cấu trúc tổng quát của một dòng lệnh

Spring Shell 4 phân tích dòng lệnh theo cấu trúc khái quát:

```text
CommandSyntax  ::= CommandName [SubCommandName]* [Option | Argument]*
CommandName    ::= String
SubCommandName ::= String
Option         ::= ShortOption | LongOption
ShortOption    ::= '-' Char ['='|' ']? String
LongOption     ::= '--' String ['='|' ']? String
Argument       ::= String
```

Có thể đọc cấu trúc này theo ba bước:

1. Bắt đầu bằng tên command đã đăng ký.
2. Tiếp theo là không hoặc nhiều từ xác định các cấp command con.
3. Sau khi tên command hoàn tất, cung cấp các option và argument theo yêu cầu của command.

Ví dụ, nếu ứng dụng có command `customer order show`, dòng lệnh:

```text
customer order show --details true ORD-2026-001
```

được hiểu như sau:

| Phần | Giá trị | Ý nghĩa |
| --- | --- | --- |
| Command name | `customer` | Từ đầu của tên command |
| Subcommand | `order show` | Các từ tiếp theo hoàn thành tên command đã đăng ký |
| Option | `--details true` | Tùy chọn có tên `details`, giá trị `true` |
| Argument | `ORD-2026-001` | Đối số vị trí của command |

Tên command và các từ con phải xuất hiện ở đầu dòng lệnh, trước phần dữ liệu. Sau khi parser đã xác định được command, các token tiếp theo được phân loại thành option hoặc argument. Một từ xuất hiện sau phần option/argument không tự quay lại trở thành cấp command con.

## Tên command và tên command con

Trong Spring Shell, một command có thể có tên gồm nhiều từ. Các từ đó tạo thành một đường dẫn command mà người dùng nhập theo đúng thứ tự đã đăng ký.

Ví dụ, ứng dụng đăng ký các command:

```java
@Component
public class CustomerCommands {

    @Command(name = "customer list", description = "Liệt kê khách hàng")
    public String list() {
        return customerService.listSummary();
    }

    @Command(name = "customer show", description = "Xem khách hàng")
    public String show(@Argument(index = 0) String code) {
        return customerService.describe(code);
    }
}
```

Người dùng gọi:

```text
customer list
customer show CUS-123456
```

`customer` là từ đầu trong tên command; `list` hoặc `show` là từ tiếp theo để xác định command cụ thể. Khi ứng dụng có các cấp sâu hơn, ví dụ `customer order show`, các từ `customer order show` đều thuộc phần tên command.

Không đặt option hoặc argument xen vào giữa các từ cấu thành tên command. Ví dụ, nếu tên command đã đăng ký là `customer order show`, hãy gọi:

```text
customer order show --details true ORD-2026-001
```

Không viết:

```text
customer --details true order show ORD-2026-001
```

Trong dòng thứ hai, parser gặp option trước khi hoàn tất phần tên command. Vì vậy, `order show` không còn được đọc như các từ con theo cấu trúc tên command đã đăng ký.

## Option có tên và argument theo vị trí

Sau phần tên command, Spring Shell phân biệt hai loại dữ liệu:

- **Option** có tên, thường bắt đầu bằng `--` hoặc `-`. Tên giúp người dùng biết giá trị đang mô tả điều gì.
- **Argument** không có tên option, được gán theo vị trí trong số các argument của command.

Ví dụ một command tìm kiếm đơn hàng:

```java
@Component
public class OrderCommands {

    private final OrderService orderService;

    public OrderCommands(OrderService orderService) {
        this.orderService = orderService;
    }

    @Command(name = "order search", description = "Tìm kiếm đơn hàng")
    public String search(
            @Argument(index = 0, description = "Từ khóa tìm kiếm") String keyword,
            @Option(longName = "status", description = "Trạng thái đơn hàng") String status,
            @Option(longName = "limit", defaultValue = "20",
                    description = "Số kết quả tối đa") int limit) {

        return orderService.search(keyword, status, limit);
    }
}
```

Hai cách gọi sau đều có thể biểu diễn cùng dữ liệu:

```text
order search ORD-2026-001 --status PAID --limit 20
order search --limit=20 --status=PAID ORD-2026-001
```

Argument `keyword` vẫn là argument vị trí đầu tiên. Hai option `status` và `limit` được nhận diện theo tên, vì vậy có thể xuất hiện theo thứ tự khác nhau và có thể đứng trước hoặc sau argument. Chỉ số của `@Argument` là chỉ số 0-based trong nhóm argument, không phải vị trí token tuyệt đối tính từ đầu dòng và cũng không tính các option.

Nên ưu tiên option có tên khi command có nhiều tham số hoặc có subcommand. Tên option giúp người dùng đọc được ý nghĩa của dữ liệu mà không cần nhớ thứ tự tham số trong chữ ký phương thức. Dùng argument vị trí cho dữ liệu chính, ngắn gọn và dễ nhận biết như mã đơn hàng hoặc đường dẫn file.

## Hai cách viết option

Spring Shell hỗ trợ dạng dài và dạng ngắn. Cả hai dạng đều có thể gắn giá trị bằng dấu `=` hoặc bằng khoảng trắng.

| Kiểu | Dạng viết | Ví dụ |
| --- | --- | --- |
| Option dài | `--key=value` | `--status=PAID` |
| Option dài | `--key value` | `--status PAID` |
| Option ngắn | `-k=value` | `-s=PAID` |
| Option ngắn | `-k value` | `-s PAID` |

Ví dụ:

```text
order search ORD-2026-001 --status=PAID --limit=20
order search ORD-2026-001 --status PAID --limit 20
order search ORD-2026-001 -s=PAID -l=20
order search ORD-2026-001 -s PAID -l 20
```

Tên dài có thể dễ đọc hơn trong script; tên ngắn tiện khi nhập lệnh thủ công. Khi khai báo cả hai tên cho một option, hãy mô tả chúng trong trợ giúp để người dùng biết chúng tương đương.

### Option boolean vẫn cần giá trị

Trong parser mặc định của Spring Shell 4, mọi option khi xuất hiện đều phải có giá trị, kể cả option có kiểu `boolean` hoặc `Boolean`. Quy tắc này giúp parser phân biệt giá trị option với argument kế tiếp.

Ví dụ:

```text
customer show CUS-123456 --details true
customer show CUS-123456 --details=false
```

Không dùng dạng chỉ có tên option như:

```text
customer show CUS-123456 --details
```

Nếu muốn giá trị mặc định là `false`, khai báo `defaultValue = "false"` trên `@Option` hoặc `.defaultValue("false")` trong `CommandRegistration`. Khi người dùng không truyền option, command nhận giá trị mặc định; nếu có truyền, người dùng cần ghi rõ `true` hoặc `false`.

### Không gộp nhiều option ngắn thành một token

Parser mặc định không hỗ trợ gộp các tên option ngắn thành một chuỗi như `-abc`. Mỗi option ngắn phải được viết riêng và đi kèm giá trị của nó:

```text
tool run -a true -b 10 -c fast
```

Không viết:

```text
tool run -abc
```

Quy tắc này khác một số CLI phổ biến có thể gộp các flag boolean. Với Spring Shell, hãy giữ mỗi option ngắn thành một cặp tên và giá trị rõ ràng.

## Kết hợp option và argument theo nhiều thứ tự

Sau khi tên command đã hoàn tất, parser cho phép trộn option và argument. Ví dụ, với command nhận hai argument là `source` và `destination`, cùng option `--overwrite`:

```java
@Command(name = "file copy", description = "Sao chép file")
public String copy(
        @Argument(index = 0, description = "File nguồn") String source,
        @Argument(index = 1, description = "Đường dẫn đích") String destination,
        @Option(longName = "overwrite", defaultValue = "false") boolean overwrite) {
    return fileService.copy(source, destination, overwrite);
}
```

Các cách gọi sau đều hợp lệ về thứ tự:

```text
file copy source.txt backup/source.txt --overwrite true
file copy --overwrite true source.txt backup/source.txt
file copy source.txt --overwrite=true backup/source.txt
```

Các argument được gán theo thứ tự xuất hiện trong nhóm argument, bất kể option có xen giữa. Trong ví dụ, `source.txt` là argument thứ nhất và `backup/source.txt` là argument thứ hai.

Điều này không có nghĩa mọi chuỗi đều có thể được đặt tùy ý. Giá trị của option phải nằm cạnh option theo một trong hai cú pháp `--key=value` hoặc `--key value`. Nếu dùng dạng có khoảng trắng, token ngay sau tên option được xem là giá trị của option. Hãy viết option rõ ràng để không vô tình tiêu thụ một từ mà bạn định dùng làm argument.

## Thu thập nhiều argument với `@Arguments`

Khi command nhận số lượng argument thay đổi, dùng `@Arguments` trên tham số kiểu mảng hoặc collection. Theo mặc định, annotation này thu thập tất cả token còn lại dành cho argument:

```java
@Command(name = "label add", description = "Thêm nhiều nhãn cho một đối tượng")
public String addLabels(
        @Argument(index = 0, description = "Mã đối tượng") String code,
        @Arguments List<String> labels) {

    return labelService.add(code, labels);
}
```

Người dùng gọi:

```text
label add ITEM-42 urgent review customer-visible
```

`ITEM-42` được gán cho `code`; các argument còn lại được gom vào `labels`. Option có tên vẫn có thể xuất hiện cùng command, nhưng cần thiết kế arity rõ ràng nếu muốn phân định ranh giới giữa các nhóm token.

`@Arguments(arity = n)` giới hạn số token được gom vào tham số đó. Ví dụ:

```java
@Command(name = "math complex real-part", description = "Tính phần thực của tích hai số phức")
public double realPart(
        @Arguments(arity = 2) double[] realParts,
        @Arguments(arity = 2) double[] imaginaryParts) {
    return realParts[0] * realParts[1]
            - imaginaryParts[0] * imaginaryParts[1];
}
```

Lệnh:

```text
math complex real-part 1 2 3 4
```

Hai argument đầu được gom vào `realParts`, hai argument tiếp theo vào `imaginaryParts`. Khi dùng nhiều tham số `@Arguments`, cần khai báo `arity` để parser biết số token mỗi tham số nhận. Nếu không giới hạn, tham số có thể tiêu thụ tất cả argument còn lại và làm các tham số sau không nhận được dữ liệu.

## Chuỗi có khoảng trắng: dùng dấu nháy

Parser tách dòng lệnh thành các từ dựa trên khoảng trắng. Nếu giá trị option hoặc argument chứa khoảng trắng, hãy đặt toàn bộ giá trị trong dấu nháy đơn hoặc nháy kép.

```text
message send --text="Hello Spring Shell"
message send --text 'Hello Spring Shell'
file search "monthly sales report.csv"
```

Trong các ví dụ trên, giá trị nhận được không chứa dấu nháy bao quanh. Cả hai kiểu dấu nháy đều được hỗ trợ; có thể dùng kiểu nháy còn lại bên trong giá trị:

```text
message send --text="I'm here!"
message send --text='He said "Hi!"'
```

Nếu cần đưa chính dấu nháy đang dùng để bao quanh vào giá trị, hãy escape nó bằng dấu gạch chéo ngược (`\`). Có thể escape dấu gạch chéo ngược trong giá trị được quote bằng cách viết `\\`:

```text
message send --text="He said \"Hi!\""
message send --text='I\'m here!'
file open --path="C:\\reports\\2026"
```

Chỉ khi toàn bộ giá trị được bao bởi dấu nháy thì dấu nháy bao ngoài mới được loại bỏ. Dấu nháy nằm giữa một token không được xem là dấu bao giá trị; ví dụ `value1"inside"value2` vẫn giữ các ký tự nháy ở giữa. Escape sequence chỉ được xử lý bên trong giá trị đã quote. Dòng lệnh có dấu nháy không cân bằng sẽ bị từ chối.

## Tách cú pháp khỏi chuyển đổi và validation

Parser quyết định token nào là tên command, option hoặc argument. Sau đó, Spring Shell chuyển giá trị văn bản sang kiểu Java đã khai báo. Hai giai đoạn này không nên bị nhầm với validation nghiệp vụ.

Ví dụ command:

```java
import jakarta.validation.constraints.Min;

@Command(name = "report export", description = "Xuất báo cáo")
public String export(
        @Argument(index = 0, description = "Năm báo cáo") @Min(2000) int year,
        @Option(longName = "format", defaultValue = "CSV") ReportFormat format) {
    return reportService.export(year, format);
}
```

Khi gọi:

```text
report export 2026 --format JSON
```

parser nhận `report export` là tên command, `2026` là argument và `--format JSON` là option. Sau đó `2026` được chuyển thành `int`, `JSON` được chuyển thành `ReportFormat.JSON`. Constraint `@Min(2000)` kiểm tra giá trị năm theo cơ chế Bean Validation nếu provider validation đã được cấu hình.

Các lỗi có thể xảy ra ở những thời điểm khác nhau:

| Lỗi | Ví dụ | Giai đoạn phát hiện |
| --- | --- | --- |
| Không tìm thấy command | `customer unknown` | Tra cứu tên command đã đăng ký |
| Sai cấu trúc option | `--status` nhưng không có giá trị | Phân tích cú pháp |
| Sai kiểu dữ liệu | `--limit many` khi yêu cầu số nguyên | Chuyển đổi kiểu |
| Vi phạm constraint | Năm nhỏ hơn giới hạn `@Min` | Validation |
| Không thỏa quy tắc nghiệp vụ | Không thể xuất báo cáo do kỳ báo cáo đã khóa | Application service/domain |

Thông báo lỗi nên chỉ rõ phần cú pháp hoặc giá trị gây lỗi. Với script, hãy bảo đảm lỗi command được ánh xạ sang mã thoát phù hợp để tiến trình gọi biết thao tác thất bại.

## Khi cú pháp mặc định không phù hợp

Spring Shell 4 cung cấp interface `CommandParser` để thay thế quy tắc phân tích mặc định. Nếu ứng dụng cần một cú pháp riêng, có thể triển khai `CommandParser`, đăng ký implementation đó thành bean trong Spring ApplicationContext để Spring Shell sử dụng.

Không nên tùy chỉnh parser chỉ để đổi vị trí một vài option. Cú pháp mặc định đã cho phép option và argument xuất hiện theo nhiều thứ tự sau phần tên command. Parser tùy chỉnh làm thay đổi hợp đồng giao tiếp của toàn bộ CLI; trước khi áp dụng, hãy xác định rõ grammar mới và kiểm thử các trường hợp tên command, option, argument, quote, escape và lỗi cú pháp.

## Ví dụ tổng hợp

Giả sử CLI có command `customer order search` với các đầu vào:

- Argument thứ nhất: từ khóa tìm kiếm.
- Option `--status` hoặc `-s`: trạng thái đơn hàng.
- Option `--limit` hoặc `-l`: số kết quả tối đa, mặc định là `20`.
- Option `--include-items`: giá trị boolean, mặc định `false`.

Khai báo:

```java
@Command(name = "customer order search", description = "Tìm kiếm đơn hàng của khách hàng")
public String search(
        @Argument(index = 0, description = "Từ khóa tìm kiếm") String keyword,
        @Option(shortName = 's', longName = "status") String status,
        @Option(shortName = 'l', longName = "limit", defaultValue = "20") int limit,
        @Option(longName = "include-items", defaultValue = "false") boolean includeItems) {

    return orderService.search(keyword, status, limit, includeItems);
}
```

Các lệnh sau đều giữ nguyên phần tên command ở đầu và cung cấp dữ liệu theo cú pháp hợp lệ:

```text
customer order search ORD-2026 --status PAID --limit 10 --include-items true
customer order search --limit=10 ORD-2026 --status=PAID --include-items=false
customer order search -s=PAID -l 10 ORD-2026 --include-items true
```

Để dễ đọc trong script, nên dùng tên option dài và cú pháp `--key=value` hoặc `--key value`. Khi nhập thủ công, có thể dùng tên ngắn. Nếu giá trị chứa khoảng trắng, đặt giá trị trong dấu nháy. Với option boolean, luôn truyền rõ `true` hoặc `false` khi option xuất hiện.

## Những lỗi thường gặp

| Lỗi | Vì sao sai | Cách viết đúng |
| --- | --- | --- |
| Đặt option giữa các từ của tên command | Parser cần xác định command/subcommand trước phần dữ liệu | Viết toàn bộ tên command trước option và argument |
| Cho rằng option phải đứng trước argument | Parser cho phép trộn option và argument sau tên command | Chọn thứ tự dễ đọc, giữ đúng giá trị option |
| Dùng argument như thể có tên | Argument được gán theo vị trí | Dùng `@Option` nếu cần gọi theo tên |
| Bỏ giá trị của option boolean | Parser cần giá trị để phân biệt option và argument | Viết `--details true` hoặc `--details false` |
| Gộp `-a -b -c` thành `-abc` | Short options không hỗ trợ nhóm | Viết từng option riêng |
| Không quote giá trị có khoảng trắng | Parser tách thành nhiều token | Dùng nháy đơn hoặc nháy kép quanh toàn bộ giá trị |
| Dùng nhiều `@Arguments` không có arity | Parser không biết ranh giới token giữa các tham số | Khai báo `arity` cho từng tham số |
| Nhầm sai kiểu với lỗi nghiệp vụ | Lỗi xảy ra ở các giai đoạn khác nhau | Phân biệt parse, conversion, validation và domain error |

## Checklist khi thiết kế cú pháp command

1. Chọn tên command và các từ con ngắn, nhất quán, phản ánh đúng chức năng.
2. Đặt toàn bộ tên command/subcommand ở đầu dòng trước dữ liệu đầu vào.
3. Dùng option có tên cho dữ liệu tùy chọn hoặc khi command có nhiều tham số.
4. Dùng argument vị trí cho dữ liệu chính, ngắn gọn và dễ đoán.
5. Kiểm tra kiểu option, giá trị mặc định và quy tắc option boolean phải có giá trị.
6. Quote toàn bộ giá trị có khoảng trắng và escape dấu nháy khi cần.
7. Đặt `arity` khi thu thập nhiều argument hoặc nhiều nhóm argument.
8. Kiểm thử các cách sắp xếp option/argument, đầu vào sai và mã thoát khi chạy từ script.

Khi tuân theo cấu trúc này, người dùng có thể nhận ra command ngay từ đầu dòng, truyền option theo tên và argument theo vị trí mà không phải ghi nhớ một thứ tự cứng nhắc giữa các dữ liệu đầu vào. Cú pháp nhất quán cũng giúp trợ giúp, kiểm thử và script vận hành đáng tin cậy hơn.

## Tài liệu tham khảo

- [Command Syntax – Spring Shell 4.0.3](https://docs.spring.io/spring-shell/reference/commands/syntax.html)
- [CommandParser API – Spring Shell 4.0.3](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/CommandParser.html)
- [DefaultCommandParser API – Spring Shell 4.0.3](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/DefaultCommandParser.html)
- [Positional Options – Spring Shell 3.4.1](https://docs.spring.io/spring-shell/reference/options/positional.html)

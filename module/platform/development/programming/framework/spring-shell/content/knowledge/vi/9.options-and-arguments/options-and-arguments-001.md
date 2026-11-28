# Tùy chọn có tên khác với đối số vị trí

Khi gọi một command, người dùng có thể truyền dữ liệu bằng hai cách chính: **tùy chọn có tên** và **đối số vị trí**. Tùy chọn có tên được nhận diện bằng khóa như `--format` hoặc `-f`; đối số vị trí được nhận diện theo thứ tự xuất hiện như `copy <nguồn> <đích>`. Spring Shell hỗ trợ cả hai cách và ánh xạ chúng vào tham số của command.

Phân biệt đúng hai loại đầu vào giúp command dễ đọc, dễ dùng trong script và ít nhập nhằng khi có nhiều tham số. Với Spring Shell 4.x, annotation `@Option` khai báo tham số có tên, còn `@Argument` khai báo tham số theo vị trí.

## Hai cách truyền dữ liệu

Giả sử có command xuất báo cáo khách hàng. Người dùng cần chỉ định phạm vi dữ liệu, định dạng file và giới hạn số dòng:

```text
customer-report all --format csv --limit 50
```

Trong ví dụ này:

- `all` là đối số vị trí đầu tiên, xác định phạm vi báo cáo.
- `--format csv` là tùy chọn có tên, xác định định dạng.
- `--limit 50` là tùy chọn có tên, xác định giới hạn số dòng.

Tùy chọn có tên và đối số vị trí khác nhau ở cách parser xác định ý nghĩa của giá trị:

| Tiêu chí | Tùy chọn có tên (*named option*) | Đối số vị trí (*positional argument*) |
|---|---|---|
| Cách nhận diện | Dựa vào tên ngắn hoặc tên dài, thường có tiền tố `-` hoặc `--` | Dựa vào vị trí trong chuỗi đối số |
| Ví dụ | `--format csv`, `-f csv` | `all`, `C1024`, `report.csv` |
| Thứ tự | Có thể đổi vị trí mà vẫn giữ ý nghĩa | Thứ tự quyết định tham số nhận giá trị |
| Khả năng đọc | Tên khóa giải thích mục đích của giá trị | Người dùng cần biết thứ tự tham số |
| Phù hợp với | Thiết lập tùy chọn, bộ lọc, chế độ, giá trị cấu hình | Tên tài nguyên, mã định danh hoặc chuỗi thao tác ngắn có thứ tự tự nhiên |

Đối số vị trí thường ngắn gọn cho những giá trị chính của thao tác. Tùy chọn có tên phù hợp với tham số có thể thay đổi độc lập, đặc biệt khi command có nhiều thiết lập.

## Khai báo trong Spring Shell 4.x

Spring Shell 4.x sử dụng `@Argument` và `@Option` trên tham số của phương thức command. `@Argument` yêu cầu chỉ số `index`; chỉ số bắt đầu từ `0`. `@Option` khai báo tên dài, tên ngắn, mô tả, tính bắt buộc và giá trị mặc định.

```java
import org.springframework.shell.core.command.annotation.Argument;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
class CustomerReportCommands {

    @Command(name = "customer-report", description = "Xuất báo cáo khách hàng")
    public String export(
            @Argument(index = 0, description = "Phạm vi báo cáo",
                    defaultValue = "all") String scope,
            @Option(shortName = 'f', longName = "format",
                    description = "Định dạng đầu ra",
                    defaultValue = "table") String format,
            @Option(longName = "limit",
                    description = "Số dòng tối đa",
                    defaultValue = "100") int limit) {

        return "Xuất báo cáo: scope=" + scope
                + ", format=" + format
                + ", limit=" + limit;
    }
}
```

Trong method trên:

- `scope` là đối số vị trí số `0`. Nếu người dùng bỏ qua đối số này, giá trị mặc định là `all`.
- `format` là tùy chọn có tên dài `--format` và tên ngắn `-f`. Giá trị mặc định là `table`.
- `limit` là tùy chọn có tên `--limit`. Spring Shell chuyển đổi giá trị đầu vào thành `int`; nếu không truyền, giá trị mặc định là `100`.

Người dùng có thể gọi command theo nhiều cách:

```text
shell:>customer-report all --format csv --limit 50
Xuất báo cáo: scope=all, format=csv, limit=50

shell:>customer-report --limit=50 -f=csv all
Xuất báo cáo: scope=all, format=csv, limit=50

shell:>customer-report
Xuất báo cáo: scope=all, format=table, limit=100
```

Spring Shell 4.x cho phép đặt option và argument theo thứ tự bất kỳ. Dù `--limit` đứng trước `all`, parser vẫn nhận diện được nó là tùy chọn có tên và gán `all` vào đối số vị trí đầu tiên.

## Tên ngắn và tên dài của option

Một option có thể có tên dài và tên ngắn. Tên dài thường mô tả rõ mục đích, còn tên ngắn tiện nhập nhanh trong terminal.

```java
@Option(shortName = 'f', longName = "format") String format
```

Hai cách gọi sau tương đương:

```text
customer-report --format csv
customer-report -f csv
```

Spring Shell 4.x cũng hỗ trợ đặt dấu bằng giữa tên và giá trị:

```text
customer-report --format=csv
customer-report -f=csv
```

Tên dài thường dùng trong script hoặc tài liệu vì dễ đọc. Tên ngắn phù hợp khi người dùng thường xuyên gọi command và muốn giảm thao tác gõ. Không nên tạo các tên ngắn khó nhớ hoặc trùng lặp giữa các option.

Trong API annotation của Spring Shell 4.x, `@Option` dùng `longName` và `shortName` ở dạng số ít. Spring Shell 3.x dùng `longNames` và `shortNames` ở dạng mảng. Hãy dùng đúng package và tên thuộc tính của phiên bản dự án.

## Đối số vị trí và chỉ số index

Đối số vị trí được ánh xạ theo thứ tự xuất hiện trong phần đầu vào không gắn với option. `index` trong `@Argument` bắt đầu từ `0`:

```java
@Command(name = "copy")
public String copy(
        @Argument(index = 0, description = "Đường dẫn nguồn") String source,
        @Argument(index = 1, description = "Đường dẫn đích") String destination) {
    return "Copy " + source + " -> " + destination;
}
```

Lệnh được gọi như sau:

```text
shell:>copy ./input.csv ./backup/input.csv
Copy ./input.csv -> ./backup/input.csv
```

Đổi thứ tự hai giá trị sẽ làm thay đổi ý nghĩa của command:

```text
shell:>copy ./backup/input.csv ./input.csv
```

Parser vẫn gán đối số đầu tiên vào `source` và đối số thứ hai vào `destination`. Spring Shell không thể tự suy ra người dùng muốn đảo vai trò của chúng.

Nếu một command có nhiều đối số vị trí, hãy ghi rõ mô tả cho từng đối số và bảo đảm thứ tự có ý nghĩa tự nhiên. Khi số lượng tham số tăng hoặc một tham số thường xuyên được thay đổi độc lập, chuyển nó thành option có tên sẽ giúp giảm nhầm lẫn.

## Dùng @Arguments cho nhiều giá trị vị trí

Khi command nhận số lượng đối số không cố định, Spring Shell 4.x hỗ trợ `@Arguments` trên tham số kiểu mảng hoặc collection. Mặc định, annotation này thu thập tất cả đối số còn lại. Từ Spring Shell 4.0.2, có thể đặt `arity` để giới hạn số đối số được thu thập.

```java
import java.util.List;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Arguments;

@Command(name = "greet-many", description = "Chào nhiều người")
public String greetMany(@Arguments List<String> names) {
    return "Xin chào " + String.join(", ", names);
}
```

Ví dụ gọi:

```text
shell:>greet-many Lan Minh An
Xin chào Lan, Minh, An
```

Nếu command còn có option, parser vẫn nhận diện option theo tên và thu thập các token vị trí vào collection:

```java
import org.springframework.shell.core.command.annotation.Arguments;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;

@Command(name = "greet-many")
public String greetMany(
        @Option(shortName = 's', longName = "suffix",
                defaultValue = "!") String suffix,
        @Arguments List<String> names) {
    return "Xin chào " + String.join(", ", names) + suffix;
}
```

```text
shell:>greet-many Lan Minh --suffix=.
Xin chào Lan, Minh.
```

Khi đặt `arity`, hãy xác định rõ số lượng phần tử mà collection nhận. Nếu command có nhiều nhóm đối số, có thể dùng các collection với arity riêng để tránh thu thập nhầm dữ liệu. Không nên dùng collection vị trí cho mọi trường hợp; khi từng giá trị có ý nghĩa riêng, `@Argument(index)` sẽ dễ hiểu hơn.

## Option bắt buộc, tùy chọn và giá trị mặc định

`@Option` trong Spring Shell 4.x có `required` và `defaultValue`. Theo API 4.0.3, `required` mặc định là `false`. Hãy khai báo rõ option bắt buộc để shell có thể báo lỗi khi người dùng bỏ qua.

```java
@Command(name = "user-find")
public String find(
        @Option(longName = "id", required = true,
                description = "Mã người dùng") String id,
        @Option(longName = "detail", defaultValue = "false",
                description = "Hiển thị thông tin chi tiết") boolean detail) {
    return "id=" + id + ", detail=" + detail;
}
```

Các cách gọi:

```text
shell:>user-find --id U1024
id=U1024, detail=false

shell:>user-find --detail true --id U1024
id=U1024, detail=true
```

Nếu thiếu `--id`, Spring Shell báo lỗi vì option bắt buộc. Nếu bỏ qua `--detail`, giá trị mặc định `false` được sử dụng.

Trong cú pháp parser mặc định của Spring Shell 4.x, option luôn cần giá trị, kể cả option kiểu boolean. Vì vậy, hãy truyền `--detail true` hoặc `--detail=false`; chỉ viết `--detail` mà không có giá trị không phải cú pháp boolean flag được hỗ trợ bởi parser mặc định. Tên option được dùng để phân biệt nó với các đối số vị trí.

`@Argument` cũng có thể khai báo `defaultValue`. Tuy nhiên, đối số vị trí thường biểu diễn dữ liệu chính của thao tác. Chỉ đặt mặc định khi có một giá trị thực sự hợp lý nếu người dùng bỏ qua, ví dụ phạm vi báo cáo mặc định là `all`.

## Cách parser phân biệt option và argument

Spring Shell 4.x hỗ trợ các dạng cú pháp sau:

| Cú pháp | Ví dụ | Ý nghĩa |
|---|---|---|
| Option dài, cách nhau bằng khoảng trắng | `--format csv` | `csv` là giá trị của `format` |
| Option dài, dùng dấu bằng | `--format=csv` | `csv` là giá trị của `format` |
| Option ngắn, cách nhau bằng khoảng trắng | `-f csv` | `csv` là giá trị của option `f` |
| Option ngắn, dùng dấu bằng | `-f=csv` | `csv` là giá trị của option `f` |
| Argument vị trí | `copy source.txt target.txt` | `source.txt` là argument index 0, `target.txt` là index 1 |

Parser cho phép trộn option và argument trong cùng dòng, ví dụ:

```text
customer-report all --format csv --limit 50
customer-report --format csv all --limit 50
customer-report --limit 50 all --format csv
```

Cả ba cách đều gán `all` vào `scope`, `csv` vào `format` và `50` vào `limit`. Các argument được đánh chỉ số riêng theo thứ tự của chúng; option không chiếm một vị trí argument.

Short option không thể gộp thành một nhóm như `-abc` trong parser mặc định 4.x. Hãy viết từng option riêng, chẳng hạn `-a true -b value -c 10` nếu command khai báo các option tương ứng. Với option có giá trị bắt đầu bằng dấu gạch ngang, dùng dạng có dấu bằng hoặc đặt giá trị trong dấu nháy để tránh nhầm với một option mới.

## Khi nào nên chọn loại nào?

Chọn đối số vị trí khi giá trị là phần chính, bắt buộc và có thứ tự tự nhiên. Ví dụ:

```text
copy <source> <destination>
user-find <user-id>
```

Chọn option có tên khi giá trị là thiết lập bổ sung, có thể thay đổi độc lập hoặc cần dễ đọc trong script:

```text
copy input.csv backup.csv --overwrite true
user-find U1024 --detail true --format json
```

Trong ví dụ `copy`, `source` và `destination` là hai đối tượng chính của thao tác. `overwrite` là chính sách thực hiện, nên dùng option có tên. Với `user-find`, `user-id` là đối tượng cần tìm, còn `detail` và `format` là cách trình bày kết quả.

| Tình huống | Gợi ý |
|---|---|
| Một hoặc hai giá trị chính có thứ tự tự nhiên | Dùng `@Argument(index = ...)` |
| Nhiều thiết lập không bắt buộc | Dùng `@Option` |
| Người dùng thường cần đổi thứ tự tham số | Ưu tiên option có tên |
| Nhận danh sách giá trị không cố định | Dùng `@Arguments` |
| Có nhiều đối số vị trí dễ bị đảo | Đổi một số tham số thành option có tên |
| Cần tương thích script lâu dài | Dùng tên option rõ nghĩa và giữ thứ tự argument ổn định |

Tài liệu Spring Shell khuyến nghị ưu tiên named options khi có thể, đặc biệt khi command có subcommand, vì nhiều giá trị trần cạnh nhau dễ trở nên nhập nhằng.

## Lưu ý khi dùng Spring Shell 3.x

Spring Shell 3.x có hai mô hình annotation trong giai đoạn chuyển tiếp: mô hình mới dùng `@Command` và `@Option`, mô hình legacy dùng `@ShellMethod` và `@ShellOption`. Mô hình programmatic sử dụng `CommandRegistration`.

Trong mô hình programmatic 3.x, `CommandRegistration.Builder` có thể khai báo option với `withOption()`. Nếu cần ánh xạ token trần (không có `--name`) vào một option cụ thể, builder có `position(int)`:

```java
CommandRegistration registration = CommandRegistration.builder()
        .command("greet")
        .withOption()
            .longNames("name")
            .required()
            .position(0)
            .and()
        .withTarget()
            .function(context -> "Xin chào " + context.getOptionValue("name"))
            .and()
        .build();
```

Với registration này, token trần ở vị trí `0` có thể được ánh xạ vào option `name`. Đây là cơ chế mapping thứ cấp cho những argument chưa được nhận diện theo tên. Nếu không khai báo `position`, command có thể báo thiếu option bắt buộc khi người dùng chỉ nhập token trần:

```text
shell:>greet Lan
Xin chào Lan
```

Không nhầm `position(0)` của `CommandRegistration` 3.x với `@Argument(index = 0)` trong annotation API 4.x. `position` gán vị trí của token trần vào một option registration; `@Argument` đánh dấu rõ tham số method là positional argument. Hai cơ chế phục vụ mục đích gần nhau nhưng khác mô hình và khác cách cấu hình.

Tên thuộc tính annotation cũng khác giữa các phiên bản:

| Phiên bản | Khai báo option |
|---|---|
| Spring Shell 3.4.x annotation model mới | `@Option(longNames = "format", shortNames = 'f')` |
| Spring Shell 3.4.x programmatic | `withOption().longNames("format").shortNames('f')` |
| Spring Shell 4.0.x | `@Option(longName = "format", shortName = 'f')` |

Hãy kiểm tra package và Javadoc đúng phiên bản trước khi sao chép ví dụ. API 4.x dùng package `org.springframework.shell.core.command.annotation`; Spring Shell 3.x dùng package `org.springframework.shell.command.annotation`.

## Kiểm thử cách ánh xạ đầu vào

Khi kiểm thử một command có cả named option và positional argument, cần xác minh parser gán đúng từng giá trị trong các trường hợp:

1. Truyền đầy đủ argument và option theo thứ tự thông thường.
2. Đổi vị trí option lên trước hoặc xuống sau argument.
3. Dùng cả tên dài và tên ngắn của option.
4. Dùng dạng `--key=value` và `--key value`.
5. Bỏ qua option có giá trị mặc định.
6. Bỏ qua option bắt buộc và xác nhận thông báo lỗi rõ ràng.
7. Bỏ qua argument không có giá trị mặc định và xác nhận shell xử lý đúng.
8. Truyền quá nhiều hoặc quá ít giá trị cho `@Arguments` có arity giới hạn.
9. Truyền giá trị có khoảng trắng trong dấu nháy để xác nhận một giá trị không bị tách thành nhiều token.
10. Với Spring Shell 3.x programmatic, kiểm tra cả trường hợp có và không có `position`.

Ví dụ test case cho command báo cáo:

| Đầu vào | Kết quả mong đợi |
|---|---|
| `customer-report all --format csv --limit 50` | `scope=all`, `format=csv`, `limit=50` |
| `customer-report --limit 50 --format=csv all` | Cùng kết quả như trên |
| `customer-report` | Dùng `all`, `table`, `100` |
| `customer-report all --limit many` | Lỗi chuyển đổi vì `limit` yêu cầu số nguyên |
| `customer-report --unknown x all` | Lỗi option không được khai báo |

Nên kiểm thử cả phương thức command và tích hợp parser. Gọi trực tiếp method Java không kiểm tra được Spring Shell có phân biệt đúng option với argument từ dòng lệnh hay không.

## Lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Giá trị bị gán nhầm tham số | Dùng quá nhiều argument vị trí hoặc đặt sai index | Đặt tên rõ trong `@Option`, kiểm tra index của `@Argument` |
| Đổi thứ tự giá trị làm command chạy sai | Các giá trị là argument vị trí | Dùng option có tên cho tham số cần đổi thứ tự |
| Shell báo thiếu option dù đã nhập một token trần | Option registration chưa có mapping `position` trong mô hình programmatic 3.x | Thêm `.position(index)` nếu chủ đích ánh xạ token trần vào option |
| `--flag` bị báo thiếu giá trị | Parser 4.x mặc định yêu cầu giá trị cả với option boolean | Truyền `--flag true` hoặc `--flag=false` |
| `-abc` không hoạt động | Parser 4.x mặc định không hỗ trợ nhóm short option | Viết từng option riêng |
| Giá trị có khoảng trắng bị tách | Chưa đặt giá trị trong dấu nháy | Dùng `--message "Hello Spring Shell"` hoặc `"Tên khách hàng"` |
| Không biên dịch được `longName` hoặc `longNames` | Dùng tên thuộc tính của phiên bản khác | 3.x dùng `longNames`, 4.x dùng `longName` |

## Tài liệu tham khảo

- [Spring Shell 4.0.3 — Command Syntax](https://docs.spring.io/spring-shell/reference/commands/syntax.html): cách khai báo `@Option`, `@Argument`, `@Arguments`, quy tắc parsing và thứ tự option/argument.
- [Spring Shell 4.0.3 API — Option](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/Option.html): tên dài, tên ngắn, required và defaultValue.
- [Spring Shell 4.0.3 API — Argument](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/Argument.html): index, mô tả và giá trị mặc định của positional argument.
- [Spring Shell 4.0.3 API — Arguments](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/Arguments.html): ánh xạ nhiều argument vào array hoặc collection và arity.
- [Spring Shell 3.4.1 — Positional](https://docs.spring.io/spring-shell/reference/options/positional.html): ánh xạ token trần bằng `CommandRegistration.Builder.position(int)`.
- [Spring Shell 3.4.3 API — Option](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/command/annotation/Option.html): tên thuộc tính option của annotation model 3.x.
- [Spring Shell 3.4.3 — Programmatic Option](https://docs.spring.io/spring-shell/reference/3.4/options/basics/programmatic.html): khai báo option bằng `CommandRegistration`.

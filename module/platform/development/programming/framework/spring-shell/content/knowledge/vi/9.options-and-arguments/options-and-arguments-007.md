# `@Argument` với chỉ số vị trí trong Spring Shell 4.x

Trong Spring Shell 4.x, `@Argument` đánh dấu một tham số của command là **đối số vị trí**. Người dùng truyền giá trị theo thứ tự thay vì gắn tên như `--source` hoặc `--destination`. Thuộc tính `index` xác định vị trí của đối số trong danh sách positional arguments, bắt đầu từ `0`.

Ví dụ, command sao chép file có thể nhận đường dẫn nguồn ở index `0` và đường dẫn đích ở index `1`:

```text
copy ./report.csv ./backup/report.csv
```

Đối số vị trí phù hợp với dữ liệu ngắn, có thứ tự tự nhiên và thường bắt buộc trong tác vụ. Khi command có nhiều tham số tùy chọn hoặc thứ tự dễ gây nhầm lẫn, nên dùng `@Option` để người gọi nêu rõ ý nghĩa của từng giá trị.

## 1. Đối số vị trí là gì?

Command line có hai loại dữ liệu chính:

- **Positional argument:** giá trị được nhận diện bằng vị trí, ví dụ tên file nguồn và file đích trong `copy source.txt destination.txt`.
- **Named option:** giá trị được nhận diện bằng tên, ví dụ `--format=csv` hoặc `--force=true`.

Trong Spring Shell, `@Argument` khai báo positional argument; `@Option` khai báo named option. Đối số vị trí thường ngắn gọn và dễ gõ, còn option có tên tự mô tả nên dễ đọc khi command có nhiều tham số.

| Cách gọi | Loại tham số | Ý nghĩa |
|---|---|---|
| `copy source.txt destination.txt` | Hai positional arguments | Giá trị được gán theo vị trí 0 và 1 |
| `copy --source=source.txt --destination=destination.txt` | Hai named options | Giá trị được gán theo tên option |
| `copy source.txt destination.txt --overwrite` | Positional arguments kết hợp option | Đường dẫn được gán theo vị trí, cờ ghi đè được gán theo tên |

Spring Shell cho phép trộn options và arguments trong cùng lời gọi. Options có thể xuất hiện trước, giữa hoặc sau positional arguments mà không làm thay đổi index của các đối số vị trí.

## 2. Khai báo `@Argument(index = 0)`

`@Argument` được đặt trên tham số của method command. `index` là thuộc tính bắt buộc, dùng để xác định vị trí của giá trị. Có thể bổ sung `description` để giải thích cho người dùng và `defaultValue` nếu muốn một giá trị mặc định khi người dùng bỏ qua đối số.

Ví dụ command chào một người dùng:

```java
import org.springframework.shell.core.command.annotation.Argument;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.stereotype.Component;

@Component
public class GreetingCommands {

    @Command(name = "greet", description = "Greet a person")
    public String greet(
            @Argument(
                    index = 0,
                    description = "Name of the person",
                    defaultValue = "world"
            ) String name) {
        return "Hello " + name;
    }
}
```

Kết quả:

```text
shell:>greet Alice
Hello Alice

shell:>greet
Hello world
```

Trong ví dụ này, `Alice` là positional argument đầu tiên và được bind vào `name`. Khi không truyền đối số, Spring Shell dùng `defaultValue` là `world`.

Các thuộc tính quan trọng của `@Argument` trong Spring Shell 4.x:

| Thuộc tính | Vai trò |
|---|---|
| `index` | Chỉ số vị trí của đối số; bắt đầu từ `0` |
| `description` | Mô tả đối số trong phần trợ giúp |
| `defaultValue` | Giá trị dùng khi đối số bị bỏ qua |

`@Argument` không có thuộc tính `required` như `@Option`. Nếu command cần dữ liệu đầu vào, hãy thiết kế lời gọi và giá trị mặc định một cách rõ ràng, sau đó kiểm tra trường hợp thiếu đối số bằng help và kiểm thử command. Không dùng một default tùy tiện chỉ để tránh lỗi thiếu dữ liệu.

## 3. Khai báo nhiều positional arguments

Khi command cần nhiều giá trị có thứ tự cố định, khai báo một `@Argument` cho từng tham số và gán index tăng dần từ `0`.

Ví dụ command sao chép file:

```java
import org.springframework.shell.core.command.annotation.Argument;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
public class FileCommands {

    @Command(name = "copy", description = "Copy a file")
    public String copy(
            @Argument(index = 0, description = "Source file path") String source,
            @Argument(index = 1, description = "Destination file path") String destination,
            @Option(longName = "overwrite", description = "Replace destination if it exists")
            boolean overwrite) {

        return "Copy " + source + " to " + destination
                + "; overwrite=" + overwrite;
    }
}
```

Gọi command:

```text
shell:>copy ./report.csv ./backup/report.csv
Copy ./report.csv to ./backup/report.csv; overwrite=false

shell:>copy ./report.csv ./backup/report.csv --overwrite
Copy ./report.csv to ./backup/report.csv; overwrite=true
```

Ánh xạ positional arguments:

| Index | Giá trị người dùng truyền | Tham số Java |
|---:|---|---|
| `0` | `./report.csv` | `source` |
| `1` | `./backup/report.csv` | `destination` |

`--overwrite` là option có tên, không phải positional argument. Nó không chiếm index `0` hoặc `1`.

## 4. Index được tính trên positional arguments, không phải mọi token

Một lỗi dễ gặp là đếm tất cả token sau tên command rồi dùng con số đó làm index. Spring Shell đánh index trên các đối số vị trí, không tính tên command, subcommand hay giá trị đã được nhận diện là option.

Với command `copy` ở trên, ba cách gọi sau có thể biểu diễn cùng dữ liệu:

```text
copy source.txt destination.txt --overwrite
copy --overwrite source.txt destination.txt
copy source.txt --overwrite destination.txt
```

Trong cả ba trường hợp:

- `source.txt` vẫn là argument index `0`.
- `destination.txt` vẫn là argument index `1`.
- `--overwrite` vẫn là option `overwrite`.

Vì vậy, không gán index `1` cho `destination` chỉ vì option xuất hiện trước hoặc sau nó. Hãy xác định index theo thứ tự các giá trị positional sau khi parser đã nhận diện named options.

Spring Shell 4 hỗ trợ option dài như `--format=csv` hoặc `--format csv`, và option ngắn như `-f=csv` hoặc `-f csv`. Với option kiểu boolean, phiên bản 4.0.4 cho phép dùng dạng cờ `--overwrite` để đặt giá trị `true`, hoặc truyền tường minh `--overwrite=false`. Các option không phải boolean cần giá trị.

## 5. Kết hợp `@Argument` với `@Option`

Một command thực tế thường có một số đối số cốt lõi và nhiều tùy chọn điều chỉnh hành vi. Có thể dùng `@Argument` cho dữ liệu chính, còn `@Option` cho định dạng, chế độ, cờ hoặc giới hạn.

Ví dụ xuất báo cáo:

```java
@Component
public class ReportCommands {

    @Command(name = "export-report", description = "Export a report")
    public String export(
            @Argument(index = 0, description = "Report identifier") String reportId,
            @Option(longName = "format", defaultValue = "csv",
                    description = "Output format") String format,
            @Option(longName = "include-header", description = "Include column headers")
            boolean includeHeader) {

        return "Exporting " + reportId + " as " + format
                + "; includeHeader=" + includeHeader;
    }
}
```

Các cách gọi:

```text
export-report monthly-sales
export-report monthly-sales --format=json
export-report --include-header monthly-sales --format=csv
```

`monthly-sales` luôn được gán vào `reportId`, dù option xuất hiện trước hay sau nó. `format` có mặc định `csv`; `includeHeader` là boolean option.

Nên giữ positional arguments cho các giá trị chính mà người dùng có thể dự đoán từ tên command. Các lựa chọn thay đổi cách thực thi nên là named options vì tên option giúp lời gọi dễ đọc hơn.

## 6. Đối số có khoảng trắng và dấu nháy

Spring Shell tách input line thành các từ dựa trên khoảng trắng. Nếu một positional argument chứa khoảng trắng, hãy đặt toàn bộ giá trị trong dấu nháy đơn hoặc dấu nháy kép.

Ví dụ:

```text
shell:>greet "Nguyen Van An"
Hello Nguyen Van An

shell:>copy "./reports/final report.csv" "./backup/final report.csv"
```

Dấu nháy dùng để nhóm giá trị và không trở thành một phần của chuỗi sau khi parser xử lý. Có thể dùng loại dấu nháy này bên trong loại dấu nháy kia:

```text
shell:>greet "An 'The Builder' Nguyen"
shell:>greet 'An "The Builder" Nguyen'
```

Nếu cần đưa chính loại dấu nháy đang dùng vào nội dung giá trị, escape nó bằng backslash. Một dấu backslash literal bên trong giá trị được quote cũng cần escape theo cú pháp của Spring Shell.

Lưu ý: cú pháp quote ở prompt Spring Shell thuộc parser của Spring Shell. Khi chạy ứng dụng từ Bash, PowerShell hoặc `cmd.exe`, shell hệ điều hành có thể xử lý dấu nháy trước khi Java nhận application arguments. Hãy kiểm thử riêng chế độ interactive và non-interactive khi command nhận chuỗi phức tạp.

## 7. Dùng kiểu Java phù hợp cho positional argument

Giá trị nhập từ terminal ban đầu là văn bản. Spring Shell chuyển đổi giá trị đó sang kiểu tham số Java khi bind command. Chọn kiểu tham số theo ý nghĩa dữ liệu để phần code nghiệp vụ nhận được giá trị rõ ràng.

Ví dụ:

```java
@Command(name = "user-show", description = "Show a user")
public String showUser(
        @Argument(index = 0, description = "Numeric user identifier") long userId) {
    return "User id: " + userId;
}
```

Lời gọi:

```text
user-show 42
```

Spring Shell chuyển token `42` thành giá trị `long` trước khi gọi method. Nếu người dùng truyền `abc`, quá trình chuyển đổi thất bại và command không nhận được một `long` hợp lệ.

Một số lựa chọn kiểu thường gặp:

| Kiểu Java | Dữ liệu phù hợp | Ví dụ |
|---|---|---|
| `String` | Tên, mã hoặc văn bản tự do | `greet Alice` |
| `long`, `int` | Số nguyên hoặc identifier dạng số | `user-show 42` |
| `double`, `BigDecimal` | Số đo hoặc giá trị thập phân | `discount-set 12.5` |
| `Path` | Đường dẫn file hoặc thư mục, khi converter phù hợp có sẵn | `copy ./in.txt ./out.txt` |
| `enum` | Tập giá trị hữu hạn trong ứng dụng | `deploy staging` |

Với dữ liệu có định dạng nghiệp vụ phức tạp, có thể nhận `String` rồi parse và kiểm tra trong service hoặc dùng converter phù hợp. Không nên để command method chứa quá nhiều logic chuyển đổi và quy tắc nghiệp vụ.

## 8. Phân biệt `@Argument` và `@Arguments`

Spring Shell 4 có hai annotation tên gần nhau nhưng mục đích khác nhau:

| Annotation | Dùng cho | Kiểu tham số |
|---|---|---|
| `@Argument(index = n)` | Một positional argument tại index cụ thể | Một kiểu đơn như `String`, `long`, `Path` |
| `@Arguments` | Một tập positional arguments được thu thập vào cùng tham số | Mảng hoặc collection như `String[]`, `List<String>`, `Set<String>` |

Ví dụ dùng `@Arguments` để nhận nhiều tên:

```java
@Command(name = "greet-many", description = "Greet several people")
public String greetMany(
        @Arguments(description = "Names to greet") List<String> names) {
    return "Hello " + String.join(", ", names);
}
```

Gọi command:

```text
greet-many Alice Bob Carol
Hello Alice, Bob, Carol
```

Mặc định, `@Arguments` thu thập tất cả token positional còn lại vào mảng hoặc collection. Từ Spring Shell 4.0.2, `@Arguments` có thuộc tính `arity` để giới hạn số token tối đa được thu thập:

```java
@Command(name = "sum-pair", description = "Sum two values")
public int sumPair(@Arguments(arity = 2) int[] numbers) {
    return numbers[0] + numbers[1];
}
```

`arity = 2` giới hạn số đối số được gom vào tham số đó ở mức tối đa hai. Nó không phải thuộc tính `required` hay cam kết tự kiểm tra đủ hai giá trị trong mọi trường hợp. Nếu nghiệp vụ yêu cầu chính xác hai giá trị, hãy xác thực số phần tử trước khi truy cập chúng hoặc khai báo hai `@Argument` riêng biệt với index `0` và `1`.

Khi cần hai giá trị cố định như nguồn và đích, hai tham số `@Argument` riêng biệt thường diễn đạt ý định rõ hơn. Khi số lượng giá trị thay đổi, dùng `@Arguments`.

## 9. Khi nào nên dùng positional argument?

Positional argument giúp command gọn, nhưng người gọi phải nhớ thứ tự. Hãy dùng khi thứ tự đó tự nhiên và ít có khả năng thay đổi.

**Nên dùng `@Argument` khi:**

- Command có một hoặc hai giá trị cốt lõi, ví dụ `copy source destination`.
- Thứ tự dữ liệu rõ ràng và quen thuộc với người dùng.
- Tên command đã cung cấp ngữ cảnh đủ để hiểu ý nghĩa của từng vị trí.
- Giá trị thường xuyên được dùng trong script ngắn và không có nhiều biến thể.

**Nên dùng `@Option` khi:**

- Command có nhiều tham số hoặc các giá trị dễ bị nhầm thứ tự.
- Một giá trị là tùy chọn hoặc có thể xuất hiện ở nhiều vị trí trong lời gọi.
- Tác vụ có nhiều chế độ, định dạng, bộ lọc hoặc cờ điều khiển.
- Muốn giữ lời gọi dễ đọc khi command có subcommand.

Ví dụ, `user-update 42 Alice active` buộc người dùng nhớ ba vị trí. Lời gọi `user-update --id=42 --name=Alice --status=active` dài hơn nhưng tự mô tả hơn, dễ xem lại trong log và ít bị ảnh hưởng khi thêm option mới.

Spring Shell khuyến nghị ưu tiên named options khi có thể để giảm sự mơ hồ, đặc biệt khi command có subcommand.

## 10. Lỗi thường gặp khi dùng `@Argument`

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Hai giá trị bị gán nhầm cho tham số | Khai báo index sai hoặc người dùng nhập sai thứ tự | Bắt đầu từ index `0`, gán tăng dần và mô tả từng vị trí |
| Option làm lệch index | Nhầm option là positional argument | Nhớ rằng index chỉ tính trên positional arguments |
| Không truyền đối số nhưng command nhận giá trị không mong muốn | Đặt `defaultValue` không phù hợp hoặc không kiểm tra trường hợp thiếu | Chọn default có ý nghĩa nghiệp vụ và kiểm thử trường hợp bỏ qua |
| Giá trị có khoảng trắng bị tách thành nhiều phần | Không quote toàn bộ positional value | Dùng dấu nháy đơn hoặc kép trong input line |
| `abc` không bind được vào tham số `long` | Giá trị văn bản không chuyển đổi được sang kiểu đích | Kiểm tra định dạng và hiển thị thông báo lỗi dễ hiểu |
| Dùng `@Argument` cho danh sách dài | Một tham số được thiết kế cho một vị trí đơn | Dùng `@Arguments` với array hoặc collection |
| Dùng `@Arguments(arity = 2)` nhưng truy cập phần tử thứ hai khi chỉ nhận một giá trị | `arity` là giới hạn tối đa, không phải cam kết số lượng tối thiểu | Kiểm tra kích thước collection hoặc dùng hai `@Argument` cố định |
| Help không giải thích rõ positional input | Thiếu `description` trên `@Argument` | Bổ sung mô tả cho từng vị trí |

## 11. Kiểm thử command có positional arguments

Khi kiểm thử, không chỉ xác nhận trường hợp nhập đúng. Hãy bao phủ cách kết hợp option, thứ tự token và dữ liệu biên.

Với command `copy source destination --overwrite`, nên kiểm tra:

1. Truyền đủ hai đường dẫn và không có option.
2. Truyền option trước hai positional arguments.
3. Truyền option xen giữa hai positional arguments.
4. Truyền giá trị đường dẫn có khoảng trắng trong dấu nháy.
5. Bỏ qua một positional argument và xác nhận hành vi mặc định hoặc lỗi phù hợp.
6. Truyền giá trị sai kiểu nếu tham số không phải `String`.
7. Kiểm tra `help` hiển thị đúng mô tả cho từng vị trí.

Ví dụ ma trận lời gọi:

| Lời gọi | Điều cần xác nhận |
|---|---|
| `copy in.txt out.txt` | `source=in.txt`, `destination=out.txt`, `overwrite=false` |
| `copy --overwrite in.txt out.txt` | Option không chiếm index của argument |
| `copy in.txt --overwrite out.txt` | Option xen giữa không đổi ánh xạ index |
| `copy "final report.csv" "backup report.csv"` | Mỗi đường dẫn có khoảng trắng vẫn là một argument |
| `copy in.txt` | Xử lý thiếu argument đích theo thiết kế command |

Với kiểm thử tích hợp Spring Shell, dùng test client của đúng phiên bản để chạy command và xác nhận output hoặc trạng thái lỗi. Kiểm thử non-interactive riêng nếu command được gọi từ script hoặc process arguments; cách runner nhận `String[]` có thể khác đường parser của prompt tương tác.

## 12. Checklist khai báo `@Argument`

- [ ] Đã xác định dữ liệu nào là positional argument và dữ liệu nào là named option.
- [ ] Mỗi `@Argument` có `index` bắt buộc và bắt đầu từ `0`.
- [ ] Các index tăng dần theo thứ tự dữ liệu mà người dùng nhập.
- [ ] Index chỉ tính positional arguments, không tính option hoặc tên command.
- [ ] Mỗi đối số có `description` đủ rõ để help giải thích vị trí.
- [ ] `defaultValue` được dùng khi có fallback hợp lý.
- [ ] Đã chọn kiểu Java phù hợp và kiểm tra chuyển đổi dữ liệu.
- [ ] Giá trị chứa khoảng trắng được quote đúng cú pháp Spring Shell.
- [ ] Dùng `@Arguments` cho tập giá trị nhiều phần tử thay vì ép một `@Argument` nhận danh sách.
- [ ] Đã kiểm tra số lượng thiếu/thừa, thứ tự option và positional argument, cùng trường hợp sai kiểu.
- [ ] Đã ưu tiên `@Option` ở những vị trí có thể gây mơ hồ.

## Tài liệu tham khảo

1. [Spring Shell 4 – Command Syntax](https://docs.spring.io/spring-shell/reference/commands/syntax.html) – khai báo `@Argument`, `@Arguments`, `@Option`, index, thứ tự token, quote và escape.
2. [Spring Shell 4 – `@Argument` API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/Argument.html) – thuộc tính `index`, `description` và `defaultValue`.
3. [Spring Shell 4 – `@Arguments` API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/Arguments.html) – collection positional arguments và thuộc tính `arity`.
4. [Command Line Interface Guidelines](https://clig.dev/) – khuyến nghị dùng named options khi positional arguments có thể gây mơ hồ.

Hãy dùng `@Argument(index = n)` cho các giá trị đơn có thứ tự tự nhiên, đánh index từ `0` và mô tả từng vị trí. Khi command bắt đầu có nhiều biến thể hoặc thứ tự khó nhớ, chuyển những giá trị điều khiển sang `@Option`; khi cần nhận nhiều positional values, dùng `@Arguments` với collection hoặc array phù hợp.

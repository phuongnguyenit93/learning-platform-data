# Giữ trợ giúp và ví dụ đồng bộ với hợp đồng thực thi

Người dùng thường đọc trợ giúp trước khi chạy một command lần đầu. Họ dựa vào tên lệnh, mô tả, option, argument, giá trị mặc định và ví dụ để quyết định cú pháp cần nhập. Nếu trợ giúp nói `--customer-code` nhưng command thực tế nhận `--code`, hoặc ví dụ dùng một option đã bị xóa, người dùng sẽ gặp lỗi ngay cả khi phần nghiệp vụ vẫn hoạt động đúng.

Spring Shell cung cấp command `help` và metadata trên command, option, argument để tạo hướng dẫn ngay trong terminal. Cách tốt nhất để giữ trợ giúp chính xác là xem metadata khai báo của command như một phần hợp đồng công khai, rồi kiểm tra ví dụ bằng chính parser và command đang chạy. Bài viết sử dụng mô hình annotation Spring Shell 4.x.

## Các cách xem trợ giúp trong Spring Shell

Ứng dụng Spring Shell có command dựng sẵn `help`. Người dùng có thể dùng ba cách phổ biến:

```text
help
help customer create
customer create --help
```

`help` liệt kê các command mà shell đã đăng ký, kèm mô tả ngắn và nhóm tương ứng. `help customer create` hiển thị chi tiết command, gồm tên, cú pháp, option, kiểu dữ liệu và thông tin bắt buộc. Với command dựa trên `AbstractCommand`, `-h` và `--help` chuyển sang luồng hiển thị trợ giúp thay vì thực thi command. Các command method được Spring Shell bọc bằng `MethodInvokerCommandAdapter`, một lớp kế thừa `AbstractCommand`, nên có thể dùng cách gọi này.

Ví dụ:

```text
shell:> help
Available commands:

Built-In Commands
    clear: Clear the terminal screen
    help: Show help about available commands
    version: Show version info

Khách hàng
    customer create: Tạo hồ sơ khách hàng mới.
    customer show: Xem thông tin khách hàng.

shell:> help customer create
NAME
    customer create - Tạo hồ sơ khách hàng mới.

SYNOPSIS
    customer create --code String --name String [--note String]

OPTIONS
    --code      Mã khách hàng [Mandatory]
    --name      Tên hiển thị [Mandatory]
    --note      Ghi chú tùy chọn [Optional]
```

Đây là ví dụ minh họa cấu trúc thông tin, không phải bản output cố định cho mọi phiên bản hoặc cấu hình. Tên section, cách căn lề và cách trình bày giá trị mặc định có thể thay đổi. Khi viết kiểm thử, nên xác minh thông tin quan trọng có mặt thay vì khóa toàn bộ chuỗi output theo từng dấu cách.

## Metadata là nguồn tạo trợ giúp

Trong mô hình annotation 4.x, `@Command` mô tả command ở cấp phương thức. Các thuộc tính quan trọng gồm:

| Thuộc tính | Mục đích | Cách dùng |
| --- | --- | --- |
| `name` | Tên command người dùng nhập | Dùng tên ngắn, nhất quán và ổn định |
| `description` | Mô tả ngắn xuất hiện trong danh sách command | Viết một câu nói rõ tác dụng |
| `help` | Hướng dẫn chi tiết hơn cho command | Giải thích mục đích, điều kiện và ví dụ |
| `group` | Nhóm command trong danh sách trợ giúp | Nhóm theo năng lực nghiệp vụ |
| `alias` | Tên gọi thay thế | Chỉ thêm alias cần hỗ trợ lâu dài |
| `hidden` | Đánh dấu command không hiển thị trong danh sách trợ giúp | Dùng cho command nội bộ hoặc hỗ trợ, không dùng thay phân quyền |

Metadata của tham số cũng ảnh hưởng trực tiếp đến trợ giúp:

| Annotation | Metadata | Nội dung trợ giúp được tạo |
| --- | --- | --- |
| `@Option` | `longName`, `shortName` | Tên option dài và ngắn |
| `@Option` | `description` | Ý nghĩa của option |
| `@Option` | `required` | Option bắt buộc hay tùy chọn |
| `@Option` | `defaultValue` | Giá trị mặc định đã khai báo |
| `@Argument` | `index` | Vị trí của argument |
| `@Argument` | `description` | Ý nghĩa của argument |
| `@Argument` | `defaultValue` | Giá trị mặc định của argument |
| `@Arguments` | `description`, `arity` | Mô tả và số token được thu thập |

`description` nên ngắn vì được dùng ở danh sách command. `help` nên bổ sung thông tin người dùng cần để sử dụng command, chẳng hạn một ví dụ đầy đủ hoặc điều kiện quan trọng. Không sao chép một đoạn văn dài vào cả hai thuộc tính vì danh sách `help` sẽ trở nên khó đọc.

## Khai báo command với mô tả và ví dụ nhất quán

Ví dụ dưới đây đăng ký command tạo khách hàng. Tên option, mô tả, tính bắt buộc, constraint và ví dụ trong `help` đều dựa trên cùng chữ ký phương thức.

```java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
public class CustomerCommands {

    private final CustomerService customerService;

    public CustomerCommands(CustomerService customerService) {
        this.customerService = customerService;
    }

    @Command(
            name = "customer create",
            description = "Tạo hồ sơ khách hàng mới.",
            group = "Khách hàng",
            alias = {"customer add"},
            help = "Tạo khách hàng mới. Ví dụ: customer create "
                    + "--code CUS-123456 --name \"Nguyen Van An\" "
                    + "[--note \"Khách hàng doanh nghiệp\"]. "
                    + "Mã khách hàng dài từ 6 đến 20 ký tự; tên dài từ 2 đến 80 ký tự.")
    public String create(
            @Option(longName = "code", shortName = 'c', required = true,
                    description = "Mã khách hàng")
            @NotBlank(message = "Mã khách hàng không được để trống.")
            @Size(min = 6, max = 20,
                    message = "Mã khách hàng phải dài từ 6 đến 20 ký tự.")
            String code,

            @Option(longName = "name", shortName = 'n', required = true,
                    description = "Tên hiển thị")
            @NotBlank(message = "Tên khách hàng không được để trống.")
            @Size(min = 2, max = 80,
                    message = "Tên khách hàng phải dài từ 2 đến 80 ký tự.")
            String name,

            @Option(longName = "note",
                    description = "Ghi chú tùy chọn, tối đa 250 ký tự")
            @Size(max = 250,
                    message = "Ghi chú không được vượt quá 250 ký tự.")
            String note) {

        customerService.create(code, name, note);
        return "Đã tạo khách hàng " + code;
    }
}
```

Các cách gọi hợp lệ:

```text
customer create --code CUS-123456 --name "Nguyen Van An"
customer create -c CUS-123456 -n "Nguyen Van An" --note "Khách hàng doanh nghiệp"
customer add --code CUS-123456 --name "Nguyen Van An"
```

Ví dụ trong thuộc tính `help` dùng tên command chính `customer create`, hai option bắt buộc `--code` và `--name`, cùng option tùy chọn `--note`. Các short name `-c` và `-n` cũng khớp với khai báo. Alias `customer add` là đường gọi thay thế; nếu đưa alias vào tài liệu, phải bảo đảm nó vẫn được đăng ký và kiểm thử.

Khi người dùng chạy:

```text
help customer create
customer create --help
```

họ có thể xem hướng dẫn ngắn và metadata của các tham số. Nếu nhập chuỗi trắng cho `--name`, Bean Validation từ chối trước khi gọi service. Mô tả constraint trong `help` giúp người dùng biết trước giới hạn, còn thông báo validation chỉ ra điều kiện chưa đạt khi họ nhập sai.

## Phân biệt `description` và `help`

Hai thuộc tính phục vụ hai thời điểm khác nhau:

```java
@Command(
        name = "order cancel",
        description = "Hủy một đơn hàng.",
        help = "Hủy đơn hàng đang ở trạng thái cho phép hủy. "
                + "Ví dụ: order cancel --code ORD-2026-001. "
                + "Đơn đã giao không thể hủy.")
```

- `description` xuất hiện khi người dùng gọi `help` để duyệt danh sách command. Nó cần đủ ngắn để đọc nhanh.
- `help` cung cấp phần giải thích dài hơn, gồm ví dụ và điều kiện quan trọng.

Không dùng `description` để liệt kê tất cả option. Các option đã có `description` riêng, và Spring Shell có thể trình bày chúng trong phần chi tiết. Không dùng `help` để công bố một cú pháp mà parser không chấp nhận.

## Mô tả option và argument đúng với parser

Mỗi option nên có một mô tả trả lời câu hỏi: giá trị này dùng để làm gì? Tên option nên thể hiện dữ liệu, không chỉ lặp lại tên biến Java.

```java
@Command(name = "report export", description = "Xuất báo cáo theo định dạng chỉ định.")
public String export(
        @Option(longName = "format", shortName = 'f', required = true,
                description = "Định dạng xuất: CSV, JSON hoặc XML") ReportFormat format,
        @Option(longName = "output", shortName = 'o',
                description = "Đường dẫn file kết quả") File output,
        @Option(longName = "overwrite", defaultValue = "false",
                description = "Cho phép ghi đè file đã tồn tại") boolean overwrite) {

    return reportService.export(format, output, overwrite);
}
```

Ví dụ gọi phải phản ánh đúng kiểu và yêu cầu của tham số:

```text
report export --format CSV
report export -f JSON --output ./reports/orders.json
report export --format XML --output ./reports/orders.xml --overwrite true
```

Khi dùng enum, mô tả các giá trị hợp lệ để người dùng không phải đoán. Khi option nhận `File`, ghi rõ đó là file nguồn hay đích. Khi option có mặc định, giải thích hành vi mặc định nếu điều đó ảnh hưởng đến kết quả. Nếu option là bắt buộc, đánh dấu `required = true` để parser và trợ giúp cùng thể hiện yêu cầu.

### Argument theo vị trí

Nếu command dùng `@Argument`, hãy mô tả chính xác dữ liệu và vị trí của nó:

```java
@Command(
        name = "customer show",
        description = "Xem hồ sơ khách hàng theo mã.",
        help = "Ví dụ: customer show CUS-123456")
public String show(
        @Argument(index = 0, description = "Mã khách hàng") String code) {
    return customerService.describe(code);
}
```

Ví dụ phải đặt argument sau tên command:

```text
customer show CUS-123456
```

Không mô tả `code` như một option `--code` nếu method khai báo nó là positional argument. Nếu muốn người dùng gọi bằng tên, chuyển tham số sang `@Option` và cập nhật ví dụ tương ứng.

### Nhiều argument với `@Arguments`

Với một command nhận nhiều token, `@Arguments` có thể gom phần argument còn lại vào mảng hoặc collection. Nếu đặt `arity`, ví dụ phải truyền đúng số lượng token:

```java
import java.util.List;

import org.springframework.shell.core.command.annotation.Argument;
import org.springframework.shell.core.command.annotation.Arguments;
import org.springframework.shell.core.command.annotation.Command;

@Command(
        name = "label add",
        description = "Thêm nhiều nhãn cho một mục.",
        help = "Ví dụ: label add ITEM-42 urgent review customer-visible")
public String add(
        @Argument(index = 0, description = "Mã mục") String itemCode,
        @Arguments(description = "Danh sách nhãn") List<String> labels) {
    return labelService.add(itemCode, labels);
}
```

Nếu thay đổi từ một argument đơn sang `@Arguments`, hãy cập nhật `help`, script mẫu, tài liệu bên ngoài và kiểm thử cú pháp. Thay đổi arity cũng là thay đổi hợp đồng vì nó quyết định parser thu thập bao nhiêu token.

## Đồng bộ command builder với trợ giúp

Nếu ứng dụng đăng ký command bằng `Command.Builder`, các metadata tương ứng vẫn cần được khai báo trên đối tượng command:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.core.command.Command;
import org.springframework.shell.core.command.CommandOption;

@Configuration
public class OrderCommandConfiguration {

    @Bean
    Command orderStatusCommand(OrderService orderService) {
        CommandOption code = CommandOption.with()
                .longName("code")
                .description("Mã đơn hàng")
                .required(true)
                .type(String.class)
                .build();

        return Command.builder()
                .name("order status")
                .description("Xem trạng thái đơn hàng.")
                .group("Đơn hàng")
                .help("Ví dụ: order status --code ORD-2026-001")
                .options(code)
                .execute(context -> orderService.describe(
                        context.getOptionByLongName("code").value()))
                .build();
    }
}
```

`Command.Builder` có các phương thức tương ứng như `name`, `description`, `group`, `help`, `aliases`, `options` và `arguments`. Nếu metadata chỉ được khai báo một phần, trợ giúp cũng chỉ có thể hiển thị một phần. Vì vậy, khi tạo command bằng builder, đừng chỉ tập trung vào lambda thực thi; hãy cung cấp đủ tên, mô tả và mô tả option/argument.

Trong ví dụ, option `code` được khai báo bắt buộc và có mô tả; `help` dùng đúng tên command và tên option. Target đọc giá trị bằng tên option sau khi parser đã xử lý. Nếu đổi tên option thành `order-code`, cần sửa cả phần đọc trong target và ví dụ trong help.

## Hidden command, alias và khả năng sử dụng

`alias` cho phép một command có thêm tên gọi. Chọn alias dễ nhớ, không xung đột với command khác và giữ ổn định nếu người dùng đã đưa alias vào script. Khi alias chỉ nhằm tương thích với tên cũ, có thể ghi rõ trong help rằng tên chính là tên được khuyến nghị.

`hidden = true` đánh dấu command không hiển thị trong danh sách trợ giúp thông thường. Không dùng thuộc tính này như một cơ chế bảo mật: người biết tên command vẫn có thể thử gọi nó. Kiểm tra quyền phải nằm trong application service hoặc lớp bảo mật phù hợp. Command quan trọng đối với quy trình người dùng không nên bị ẩn nếu không có tài liệu khác hướng dẫn cách gọi.

## Giữ ví dụ sử dụng khớp với hợp đồng thực thi

Ví dụ là một phần của giao diện command. Trước khi đưa ví dụ vào `help`, kiểm tra từng thành phần:

| Thành phần ví dụ | Phải khớp với |
| --- | --- |
| Tên command | `@Command(name = ...)` hoặc `Command.Builder.name(...)` |
| Alias | `@Command(alias = ...)` hoặc `Command.Builder.aliases(...)` |
| Tên option dài/ngắn | `@Option(longName, shortName)` hoặc metadata `CommandOption` |
| Argument | `@Argument(index = ...)` hoặc `CommandArgument` |
| Giá trị bắt buộc | `required` và parser hiện tại |
| Giá trị mặc định | `defaultValue` và hành vi thực tế khi bỏ qua option |
| Kiểu dữ liệu | Kiểu Java, converter và các giá trị hợp lệ |
| Quote | Quy tắc parser với chuỗi có khoảng trắng hoặc ký tự đặc biệt |
| Validation | Constraint và thông báo lỗi thực tế |
| Kết quả | Output hoặc trạng thái thực thi mà command thực sự trả về |

Với Spring Shell 4.x, option có tên và argument vị trí có thể xuất hiện theo các thứ tự khác nhau sau phần tên command. Tuy vậy, ví dụ nên chọn một kiểu trình bày nhất quán, dễ đọc. Chuỗi có khoảng trắng phải được đặt trong dấu nháy đơn hoặc kép. Option boolean có thể được viết như flag hoặc truyền rõ `true`/`false` theo parser 4.x; nếu command dùng mặc định hoặc cần phân biệt trạng thái không truyền, hãy mô tả rõ hành vi đó.

Không sao chép ví dụ từ một phiên bản Spring Shell khác mà chưa chạy thử. Cú pháp parser, annotation và cách trình bày help có thể thay đổi giữa các major version.

## Kiểm tra trợ giúp bằng chính command đang chạy

Một quy trình đơn giản giúp phát hiện tài liệu lỗi thời:

1. Chạy `help` và xác nhận command xuất hiện dưới nhóm đúng với mô tả ngắn dễ hiểu.
2. Chạy `help <command>` và kiểm tra tên, synopsis, option, argument, kiểu, required và default value.
3. Chạy `<command> --help` hoặc `<command> -h` để xác minh luồng trợ giúp ngắn hoạt động.
4. Sao chép từng ví dụ trong thuộc tính `help` vào shell và thực thi với dữ liệu thử nghiệm.
5. Thử bỏ option bắt buộc, truyền sai kiểu và vi phạm constraint để kiểm tra thông báo lỗi.
6. Khi đổi chữ ký phương thức hoặc tên option, cập nhật metadata, ví dụ và kiểm thử trong cùng thay đổi.

Ví dụ với command tạo khách hàng:

```text
help customer create
customer create --help
customer create --code CUS-123456 --name "Nguyen Van An"
customer create --code CUS-123456 --name "Nguyen Van An" --note "Khách hàng doanh nghiệp"
```

Kiểm thử nên tập trung vào những điều người dùng cần biết, chẳng hạn:

- Danh sách help có chứa tên command và mô tả ngắn.
- Help chi tiết có tên option, mô tả, trạng thái bắt buộc và mặc định.
- Ví dụ trong help được parser chấp nhận và gọi đúng command.
- Tên option không tồn tại bị từ chối.
- Option bắt buộc bị thiếu tạo thông báo rõ ràng.
- Dữ liệu sai constraint không gọi application service.

Không nên kiểm tra toàn bộ output help bằng một chuỗi snapshot cứng nếu thứ tự hoặc căn lề có thể thay đổi theo phiên bản. Hãy kiểm tra các phần có ý nghĩa hoặc chuẩn hóa output trước khi so sánh. Nếu dự án cần giữ nguyên định dạng help cho người dùng hoặc script tự động, hãy coi đó là một giao diện cần kiểm thử tương thích khi nâng cấp.

## Ví dụ lỗi do trợ giúp không đồng bộ

Giả sử command ban đầu khai báo:

```java
@Option(longName = "customer-code", required = true)
String code
```

Sau một lần refactor, nhóm phát triển đổi tên option thành `code` nhưng quên cập nhật ví dụ trong `help`:

```text
customer create --customer-code CUS-123456 --name "Nguyen Van An"
```

Người dùng sao chép ví dụ và nhận lỗi không nhận diện option. Cách sửa phải cập nhật đồng thời ba nơi:

```java
@Option(longName = "code", required = true,
        description = "Mã khách hàng") String code
```

```text
customer create --code CUS-123456 --name "Nguyen Van An"
```

Và kiểm thử thực thi ví dụ mới. Nếu cần giữ cú pháp cũ để không làm hỏng script đã phát hành, khai báo `customer-code` như một alias option nếu API phiên bản đang dùng hỗ trợ, hoặc duy trì một command alias tương thích; không để help tiếp tục quảng bá một cú pháp mà parser không nhận.

## Checklist trước khi phát hành command

- [ ] Tên command và group phản ánh đúng chức năng.
- [ ] `description` ngắn, rõ và kết thúc bằng dấu câu nhất quán.
- [ ] `help` giải thích điều kiện quan trọng và có ví dụ đã chạy thử.
- [ ] Mỗi option có tên, mô tả và kiểu phù hợp.
- [ ] Option bắt buộc và tùy chọn được đánh dấu đúng.
- [ ] Giá trị mặc định trong help khớp với hành vi thực tế.
- [ ] Argument có index và mô tả đúng vị trí.
- [ ] `@Arguments` có arity phù hợp với ví dụ.
- [ ] Alias được kiểm thử và không xung đột.
- [ ] Hidden command không bị dùng thay cho kiểm soát quyền.
- [ ] `help`, `help <command>` và `--help` đã được kiểm tra.
- [ ] Ví dụ thành công và ví dụ lỗi đã được thực thi trên đúng phiên bản Spring Shell.

Khi metadata, trợ giúp và ví dụ cùng mô tả một hợp đồng, người dùng có thể tự khám phá command ngay trong terminal và sao chép ví dụ với kết quả dự đoán được. Mỗi thay đổi tên, kiểu, tính bắt buộc hoặc validation của tham số cũng cần được xem là thay đổi giao diện CLI, vì vậy hãy cập nhật hướng dẫn và kiểm thử đồng thời với phần thực thi.

## Tài liệu tham khảo

- [Help – Spring Shell 4.0.3](https://docs.spring.io/spring-shell/reference/commands/builtin/help.html)
- [Option Help – Spring Shell 4.0.3](https://docs.spring.io/spring-shell/reference/commands/help.html)
- [Command Syntax – Spring Shell 4.0.4](https://docs.spring.io/spring-shell/reference/commands/syntax.html)
- [@Command API – Spring Shell 4.0.3](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/Command.html)
- [@Option API – Spring Shell 4.0.3](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/Option.html)
- [@Argument API – Spring Shell 4.0.3](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/Argument.html)
- [Command API – Spring Shell 4.0.3](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/Command.html)
- [MethodInvokerCommandAdapter API – Spring Shell 4.0.3](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/adapter/MethodInvokerCommandAdapter.html)

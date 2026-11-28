# Hiển thị mặc định, tham số bắt buộc và lý do chưa khả dụng

Trợ giúp là một phần của giao diện người dùng trong ứng dụng dòng lệnh. Người dùng cần biết command nào tồn tại, command làm gì, cần truyền tham số nào, giá trị nào được mặc định và vì sao một command chưa thể chạy trong trạng thái hiện tại.

Spring Shell cung cấp command `help` cùng metadata của command và tham số để tạo nội dung trợ giúp. Với Spring Shell 3.4, danh sách trợ giúp có thể chứa cả command chưa khả dụng; trang chi tiết command cung cấp thông tin về kiểu tham số, tính bắt buộc, mô tả và giá trị mặc định. Help model cũng mang trạng thái availability và lý do chưa khả dụng để template có thể trình bày cho người dùng.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Dùng `help`, `help <command>` và `--help`/`-h` để khám phá command.
- Giải thích nội dung danh sách command và trang trợ giúp chi tiết theo template mặc định.
- Phân biệt tham số bắt buộc, tham số tùy chọn và tham số có giá trị mặc định.
- Khai báo `required` và `defaultValue` trong annotation model hoặc programmatic model.
- Giải thích vì sao giá trị mặc định không đồng nghĩa với việc input đã được kiểm tra nghiệp vụ.
- Hiểu cách help hiển thị command đã đăng ký nhưng hiện chưa khả dụng.
- Thiết kế lý do availability ngắn gọn và hữu ích.
- Tùy chỉnh template trợ giúp mà vẫn giữ đầy đủ thông tin cần thiết.
- Kiểm thử nội dung help, tham số bắt buộc, giá trị mặc định và trạng thái unavailable.

## 1. Khám phá command bằng trợ giúp tích hợp

Spring Shell cung cấp command tích hợp `help`. Trong phiên tương tác, nhập `help` rồi nhấn Enter để xem danh sách command mà shell biết. Danh sách thường được tổ chức theo nhóm và hiển thị tên cùng mô tả ngắn.

Ví dụ minh họa:

```text
support:> help

AVAILABLE COMMANDS

Customer
    customer find       Tìm khách hàng theo mã hoặc email
    customer list       Liệt kê khách hàng

Deployment
    deploy              Triển khai ứng dụng lên môi trường đã chọn
    deployment status   Xem trạng thái triển khai

Built-In Commands
    help                Hiển thị trợ giúp về các command
    history             Xem lịch sử command
    quit                Thoát shell
```

Đây là output minh họa. Tên nhóm, cách căn lề, chữ hoa và danh sách built-in command phụ thuộc ứng dụng, phiên bản và template đang dùng.

Để xem chi tiết một command, nhập `help` theo sau là tên command:

```text
support:> help deploy
```

Trang chi tiết thường cung cấp tên, mô tả, cú pháp tổng quát và các tham số cùng kiểu dữ liệu, mô tả, trạng thái bắt buộc hoặc tùy chọn. Đây là nơi người dùng kiểm tra chính xác một command cần những input nào.

Trong Spring Shell 3.4, `help` liệt kê cả command đang unavailable. Vì vậy, command chưa chạy được vẫn có thể được khám phá; người dùng có thể đọc lý do và chuẩn bị điều kiện cần thiết trước khi gọi lại. [Tài liệu Help của Spring Shell 3.4](https://docs.spring.io/spring-shell/reference/3.4/commands/builtin/help.html).

## 2. Ba cách yêu cầu trợ giúp

Có ba cách sử dụng phổ biến:

| Cách gọi | Mục đích |
|---|---|
| `help` | Liệt kê các command đã đăng ký |
| `help deploy` | Hiển thị trợ giúp chi tiết của command `deploy` |
| `deploy --help` hoặc `deploy -h` | Yêu cầu trợ giúp ngắn ngay tại command đang nhập |

Spring Shell 3.x có thể tự thêm option `--help` và `-h` vào command theo cấu hình mặc định. Khi option trợ giúp xuất hiện, luồng thực thi được chuyển sang command help thay vì gọi nghiệp vụ của command. Cấu hình này có thể bật/tắt và đổi tên option toàn cục; programmatic registration còn cho phép điều chỉnh trên từng command.

Ví dụ:

```text
support:> deploy --help
NAME
    deploy - Triển khai ứng dụng lên môi trường đã chọn

SYNOPSIS
    deploy --environment String --version String --dry-run
```

Không nên giả định mọi ứng dụng đều giữ nguyên `--help` và `-h`. Nếu nhóm dự án đã thay cấu hình help options, hãy dùng tên đã công bố trong tài liệu của ứng dụng.

## 3. Nội dung của trang trợ giúp chi tiết

Trang trợ giúp chi tiết thường có các phần:

- **NAME:** tên command và mô tả tổng quát.
- **SYNOPSIS:** hình dạng lời gọi, gồm tên command và các tham số.
- **OPTIONS hoặc PARAMETERS:** tên option/argument, kiểu dữ liệu, mô tả và trạng thái bắt buộc.
- **Availability:** thông tin command có thể chạy hay chưa và lý do nếu đang bị khóa, tùy template.

Ví dụ minh họa cho command triển khai:

```text
NAME
    deploy - Triển khai ứng dụng lên môi trường đã chọn

SYNOPSIS
    deploy --environment String --version String [--dry-run]

OPTIONS
    --environment String
        Môi trường đích để triển khai
        [Mandatory]

    --version String
        Phiên bản ứng dụng cần triển khai
        [Mandatory]

    --dry-run Boolean
        Chỉ kiểm tra kế hoạch, không thực hiện triển khai
        [Optional] Default: false
```

Đây là cách trình bày minh họa cho ý nghĩa metadata, không phải bản output cố định của mọi phiên bản hoặc template. Template quyết định nhãn, thứ tự, cách biểu diễn default và trạng thái availability.

## 4. Tham số bắt buộc và tham số tùy chọn

Một tham số **bắt buộc** phải được người dùng cung cấp để command có thể được phân tích và gọi đúng. Nếu thiếu tham số bắt buộc, Spring Shell báo lỗi usage/input trước khi chạy phần thân command.

Một tham số **tùy chọn** có thể vắng mặt. Khi không truyền option tùy chọn, giá trị mà command nhận được phụ thuộc kiểu tham số, target và cấu hình mặc định. Với kiểu tham chiếu không có default, ứng dụng thường cần xử lý trường hợp không có giá trị; hãy kiểm thử hành vi thực tế của target đang dùng.

Ví dụ:

```java
import org.springframework.shell.command.annotation.Command;
import org.springframework.shell.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
public class CustomerCommands {

    @Command(command = "customer find", description = "Tìm khách hàng")
    public String find(
            @Option(longNames = "customer-id", required = true,
                    description = "Mã khách hàng") String customerId,
            @Option(longNames = "include-disabled", required = false,
                    description = "Bao gồm khách hàng đã vô hiệu hóa") boolean includeDisabled) {
        return "Tìm khách hàng " + customerId
                + "; includeDisabled=" + includeDisabled;
    }
}
```

Trong ví dụ:

- `customer-id` là bắt buộc vì `required = true`.
- `include-disabled` là tùy chọn vì `required = false`.
- Người dùng phải truyền mã khách hàng, còn cờ boolean có thể được bỏ qua theo quy tắc binding của option.

Các cách gọi:

```text
customer find --customer-id C-100
customer find --customer-id C-100 --include-disabled true
```

Lời gọi thiếu mã khách hàng:

```text
customer find --include-disabled true
```

sẽ không thỏa hợp đồng tham số bắt buộc. Command method không nên được gọi với một `customerId` còn thiếu.

## 5. Khai báo required trong các mô hình đăng ký

Spring Shell 3.x hỗ trợ khai báo option bằng annotation model, programmatic model và legacy annotation model. Cùng một ý nghĩa required/optional được diễn đạt khác nhau theo API.

| Mô hình | Bắt buộc | Tùy chọn |
|---|---|---|
| Annotation model | `@Option(required = true)` | `@Option(required = false)` |
| Programmatic model | `.required()` | `.required(false)` |
| Legacy annotation | `@ShellOption` mặc định là bắt buộc | `@ShellOption(defaultValue = ShellOption.NULL)` |

Ví dụ programmatic model:

```java
CommandRegistration registration = CommandRegistration.builder()
        .command("customer find")
        .withOption()
            .longNames("customer-id")
            .required()
            .and()
        .withOption()
            .longNames("include-disabled")
            .required(false)
            .type(boolean.class)
            .defaultValue("false")
            .and()
        .withTarget()
            .function(context -> {
                String customerId = context.getOptionValue("customer-id");
                Boolean includeDisabled = context.getOptionValue("include-disabled");
                return "customer=" + customerId
                        + "; includeDisabled=" + includeDisabled;
            })
            .and()
        .build();
```

Ví dụ này chỉ minh họa metadata option và target. Trong ứng dụng thật, hãy kiểm tra kiểu dữ liệu mà `CommandContext` trả về và xử lý giá trị vắng mặt phù hợp với cấu hình.

Tài liệu Spring Shell 3.4 có ví dụ riêng cho option bắt buộc và tùy chọn trong cả ba mô hình. [Optional Value — Spring Shell 3.4](https://docs.spring.io/spring-shell/reference/3.4/options/optional.html).

## 6. Giá trị mặc định có ý nghĩa gì?

Giá trị mặc định được dùng khi người dùng không truyền option tương ứng. Nó giúp command có hành vi xác định mà không bắt người dùng nhập lại một giá trị thường dùng.

Ví dụ, command liệt kê báo cáo có thể mặc định trả về 50 dòng:

```java
@Command(command = "report list", description = "Liệt kê báo cáo")
public String list(
        @Option(longNames = "limit", defaultValue = "50",
                description = "Số báo cáo tối đa cần hiển thị") Integer limit) {
    return "Hiển thị tối đa " + limit + " báo cáo.";
}
```

Người dùng có thể bỏ qua `--limit`:

```text
support:> report list
Hiển thị tối đa 50 báo cáo.
```

Hoặc ghi đè default:

```text
support:> report list --limit 100
Hiển thị tối đa 100 báo cáo.
```

Trong programmatic model, khai báo bằng `.defaultValue("50")`; trong legacy annotation model, dùng `@ShellOption(defaultValue = "50")`. [Default Value — Spring Shell 3.4](https://docs.spring.io/spring-shell/reference/3.4/options/default.html).

### 6.1. Default value không giống giá trị người dùng đã nhập

Khi tham số nhận giá trị mặc định, command vẫn chạy với một giá trị cụ thể dù người dùng không nhập option. Nếu nghiệp vụ cần phân biệt người dùng có chủ động chỉ định giá trị hay không, hãy thiết kế thêm thông tin hoặc logic phù hợp; đừng suy luận sự hiện diện của option chỉ từ giá trị tham số sau binding.

Ví dụ, `--limit 50` do người dùng nhập và `50` được áp dụng làm default có thể cho cùng giá trị Java. Nếu cần phân biệt hai trường hợp, hãy kiểm tra metadata hoặc dùng một thiết kế tham số thể hiện rõ ý định đó theo API đang dùng.

### 6.2. Default value cần đúng kiểu và hợp lệ

Giá trị mặc định thường được khai báo dưới dạng chuỗi trong metadata rồi được chuyển đổi sang kiểu tham số. Vì vậy, default phải chuyển đổi được sang kiểu Java đích.

Ví dụ:

```java
@Option(longNames = "limit", defaultValue = "50") Integer limit
```

phù hợp với kiểu `Integer`. Nếu đặt default là `many`, conversion sang `Integer` sẽ thất bại.

Default cũng phải thỏa validation và quy tắc nghiệp vụ. Nếu `@Min(1)` được dùng cho `limit`, default `0` là một cấu hình không hợp lệ về mặt hợp đồng. Hãy kiểm tra các default trong test và bảo đảm chúng nằm trong miền giá trị được cho phép.

## 7. Required, default và validation là ba khái niệm riêng

Các khái niệm này có liên quan nhưng không thay thế nhau:

| Cơ chế | Câu hỏi được trả lời | Ví dụ |
|---|---|---|
| `required` | Người dùng có phải cung cấp option không? | `--customer-id` bắt buộc phải xuất hiện |
| `defaultValue` | Nếu option vắng mặt thì dùng giá trị nào? | `--limit` mặc định là `50` |
| Validation | Giá trị sau binding có thỏa điều kiện không? | `limit` phải nằm trong khoảng 1–500 |

Một option có thể được truyền đầy đủ nhưng giá trị vẫn không hợp lệ. Ví dụ:

```text
report list --limit 0
```

Option `limit` đã xuất hiện, nhưng giá trị `0` có thể vi phạm `@Min(1)`. Ngược lại, nếu người dùng bỏ qua một option bắt buộc, lỗi xảy ra do thiếu input trước khi validation nghiệp vụ có thể kiểm tra giá trị đó.

Với chuỗi bắt buộc, `required = true` bảo đảm option phải được cung cấp theo cú pháp. Nếu chuỗi chỉ chứa khoảng trắng cũng phải bị từ chối, cần thêm `@NotBlank`. Việc option xuất hiện không tự bảo đảm nội dung có ý nghĩa.

## 8. Lý do command chưa khả dụng

Một command có thể đã được đăng ký nhưng chỉ thực thi được khi trạng thái ứng dụng thỏa mãn một điều kiện. Ví dụ:

- `download` cần phiên kết nối đang hoạt động.
- `deploy` cần người dùng chọn môi trường trước.
- `report export` không thể chạy khi một tác vụ export khác đang chiếm tài nguyên.
- `user delete` cần người dùng có quyền quản trị.

Spring Shell biểu diễn điều kiện trạng thái bằng `Availability`. Provider trả `Availability.available()` khi command có thể chạy hoặc `Availability.unavailable(reason)` khi chưa thể chạy.

Ví dụ annotation model 3.x:

```java
import org.springframework.shell.Availability;
import org.springframework.shell.AvailabilityProvider;
import org.springframework.shell.command.annotation.Command;
import org.springframework.shell.command.annotation.CommandAvailability;
import org.springframework.stereotype.Component;

@Component
public class RemoteCommands {

    private boolean connected;

    @Command(command = "connect", description = "Kết nối tới máy chủ")
    public String connect() {
        connected = true;
        return "Đã kết nối.";
    }

    @Command(command = "download", description = "Tải dữ liệu từ máy chủ")
    @CommandAvailability(provider = "downloadAvailability")
    public String download() {
        return "Đang tải dữ liệu...";
    }

    @org.springframework.context.annotation.Bean
    AvailabilityProvider downloadAvailability() {
        return () -> connected
                ? Availability.available()
                : Availability.unavailable("you are not connected; run connect first");
    }
}
```

Khi chưa kết nối, `download` vẫn tồn tại trong danh sách command. Nếu người dùng gọi trực tiếp, Spring Shell có thể hiển thị thông báo dạng:

```text
Command 'download' exists but is not currently available because you are not connected; run connect first.
```

Lý do nên là một cụm ngắn nối tự nhiên sau từ “because”: bắt đầu bằng chữ thường và không kết thúc bằng dấu chấm. Không đưa password, token hoặc chi tiết nội bộ vào reason. [Command Availability — Spring Shell 3.4](https://docs.spring.io/spring-shell/reference/3.4/commands/availability.html).

## 9. Help hiển thị command unavailable như thế nào?

Danh sách `help` của Spring Shell 3.4 bao gồm các command đã đăng ký kể cả khi chúng hiện không khả dụng. Đây là chủ đích của giao diện trợ giúp: người dùng vẫn khám phá được chức năng và biết điều kiện cần thỏa mãn trước khi chạy.

Help model có trường availability gồm:

| Trường | Ý nghĩa |
|---|---|
| `available` | `true` nếu command đang khả dụng; ngược lại là `false` |
| `reason` | Lý do command chưa khả dụng, nếu có |

Ví dụ trình bày minh họa:

```text
Deployment
    connect             Kết nối tới máy chủ
    download            Tải dữ liệu từ máy chủ
                        Chưa khả dụng: you are not connected; run connect first
```

Template mặc định hoặc template tùy chỉnh quyết định cách trạng thái và reason được hiển thị. Nếu help list chỉ hiện tên và mô tả ngắn, người dùng vẫn có thể gọi `help download` để xem chi tiết, hoặc gọi command để nhận thông báo unavailable. Khi tùy chỉnh template, hãy giữ trường reason để người dùng không mất thông tin quan trọng.

### 9.1. Phân biệt unavailable với command không tồn tại

| Trạng thái | Ý nghĩa | Trải nghiệm người dùng |
|---|---|---|
| Không được đăng ký | Runtime không biết command đó | Help không liệt kê; gọi tên sẽ báo không tìm thấy |
| Đã đăng ký và available | Command tồn tại, điều kiện hiện tại cho phép chạy | Có thể thực thi |
| Đã đăng ký nhưng unavailable | Command tồn tại, điều kiện trạng thái chưa thỏa | Help vẫn có thể liệt kê; gọi command sẽ nêu reason |

Không nên ẩn một command chỉ vì nó chưa khả dụng trong trạng thái hiện tại. Người dùng cần biết chức năng tồn tại và cách mở khóa nó. Nếu command thật sự không dành cho người dùng hoặc môi trường đó, hãy dùng chính sách đăng ký/ẩn command phù hợp thay vì lạm dụng availability.

## 10. Tùy chỉnh template trợ giúp

Spring Shell 3.4 dùng template cho cả danh sách command và trang chi tiết command. Hai property chính là:

| Property | Chức năng |
|---|---|
| `spring.shell.command.help.commands-template` | Template hiển thị danh sách command và nhóm |
| `spring.shell.command.help.command-template` | Template hiển thị chi tiết một command |

Các template mặc định nằm trong classpath:

```text
classpath:template/help-commands-default.stg
classpath:template/help-command-default.stg
```

Có thể cấu hình grouping mode để hiển thị theo nhóm hoặc danh sách phẳng. Ví dụ cấu hình:

```yaml
spring:
  shell:
    command:
      help:
        enabled: true
        grouping-mode: group
        commands-template: classpath:template/custom-help-commands.stg
        command-template: classpath:template/custom-help-command.stg
```

Nếu dùng `grouping-mode: flat`, danh sách command được hiển thị không chia theo nhóm. Nếu dùng `group`, help giữ cấu trúc nhóm khi metadata có nhóm tương ứng.

Help template nhận model dữ liệu đã được Spring Shell chuẩn bị. Với trang danh sách, `GroupsInfoModel` cung cấp các trường như `showGroups`, `groups`, `commands` và `hasUnavailableCommands`. Với trang chi tiết, `CommandInfoModel` cung cấp tên, alias, mô tả, tham số và availability.

Các trường quan trọng trong `CommandParameterInfoModel`:

| Trường | Ý nghĩa |
|---|---|
| `type` | Kiểu tham số |
| `arguments` | Tên hoặc các dạng argument được mô tả |
| `required` | Tham số có bắt buộc hay không |
| `description` | Mô tả tham số |
| `defaultValue` | Giá trị mặc định nếu có |
| `hasDefaultValue` | Có default value hay không |

Với `CommandAvailabilityInfoModel`, template có thể đọc `available` và `reason`. Khi viết template riêng, hãy kiểm tra `hasDefaultValue` trước khi hiển thị `defaultValue`; tránh in `null` hoặc dòng “Default” trống cho tham số không có default.

Không cần viết lại toàn bộ help renderer chỉ để đổi một nhãn. Nếu template được tùy chỉnh, hãy giữ đầy đủ tên command, mô tả, kiểu, required, default và availability để tài liệu tự sinh không làm mất hợp đồng input.

## 11. Hai nhóm cấu hình help khác nhau

Spring Shell có cấu hình cho command help và cấu hình cho các option `--help`/`-h` tự động gắn vào command. Hai nhóm này có mục đích khác nhau.

**Cấu hình built-in help command và template:**

```yaml
spring:
  shell:
    command:
      help:
        enabled: true
        grouping-mode: group
        commands-template: classpath:template/help-commands-default.stg
        command-template: classpath:template/help-command-default.stg
```

**Cấu hình help options gắn vào command:**

```yaml
spring:
  shell:
    help:
      enabled: true
      long-names: help
      short-names: h
      command: help
```

Nhóm đầu điều khiển command `help` và cách render nội dung. Nhóm thứ hai điều khiển option trợ giúp nhanh được thêm vào command. Không nhầm `spring.shell.command.help.enabled` với `spring.shell.help.enabled`.

Trong annotation model, cấu hình help options thường được điều khiển toàn cục. Với programmatic registration, có thể cấu hình help options riêng trên từng command qua `withHelpOptions()`.

## 12. Thiết kế help rõ ràng và nhất quán

Help là hợp đồng công khai của CLI. Mỗi command nên có mô tả nêu hành động và mỗi tham số nên giải thích giá trị mà người dùng cần truyền.

Một số nguyên tắc:

- Dùng tên command và alias nhất quán với cách người dùng gọi.
- Mô tả command bằng động từ và kết quả cụ thể.
- Ghi kiểu dữ liệu khi kiểu không thể suy ra dễ dàng.
- Đánh dấu rõ tham số bắt buộc và tùy chọn.
- Hiển thị default value khi có, đặc biệt nếu default ảnh hưởng kết quả nghiệp vụ.
- Nếu command unavailable, cung cấp reason có thể hành động được.
- Không đưa stack trace hoặc dữ liệu nhạy cảm vào help.
- Không để template tùy chỉnh loại bỏ metadata quan trọng.

Ví dụ mô tả tốt:

| Mô tả yếu | Mô tả hữu ích hơn |
|---|---|
| `limit` | `Số bản ghi tối đa cần hiển thị` |
| `environment` | `Môi trường đích: dev, staging hoặc production` |
| `run command` | `Triển khai phiên bản đã chọn lên môi trường đích` |
| `not ready` | `you must select an environment first` |

## 13. Kiểm thử nội dung trợ giúp

Nên kiểm thử cả metadata và output thực tế. Unit test phương thức command không chứng minh help renderer đã hiển thị đúng required, default hoặc reason.

Một bộ kiểm thử tích hợp nên bao gồm:

1. Gọi `help` và xác nhận các command dự kiến có mặt.
2. Gọi `help <command>` và xác nhận mô tả cùng các tham số được trình bày.
3. Xác nhận option bắt buộc được đánh dấu đúng.
4. Xác nhận option tùy chọn không bị trình bày thành bắt buộc.
5. Xác nhận default value được phản ánh đúng trong help model hoặc output template.
6. Gọi command không truyền option có default và xác nhận giá trị mặc định được sử dụng.
7. Bỏ qua option bắt buộc và xác nhận command không thực thi.
8. Đặt command ở trạng thái unavailable và xác nhận help vẫn có thể liệt kê nó cùng reason theo template.
9. Thay đổi state để command available và xác nhận reason không còn được trình bày như trạng thái hiện tại.
10. Kiểm tra `--help`/`-h` nếu ứng dụng bật help options.

Ma trận kiểm thử ví dụ:

| Tình huống | Kết quả cần xác nhận |
|---|---|
| `help` | Danh sách command và mô tả ngắn |
| `help report list` | Chi tiết tham số và kiểu |
| `report list` không có `--limit` | Dùng default đã khai báo |
| `customer find` không có `--customer-id` | Báo thiếu option bắt buộc |
| `download` khi chưa kết nối | Nêu lý do unavailable |
| `help download` khi chưa kết nối | Command vẫn được khám phá; reason được template xử lý |
| `download` sau khi kết nối | Command thực thi theo điều kiện mới |
| `deploy --help` | Hiển thị trợ giúp mà không gọi nghiệp vụ deploy |

Nếu template được tùy chỉnh, hãy kiểm thử nội dung ở mức snapshot hoặc kiểm tra các trường quan trọng thay vì phụ thuộc vào khoảng trắng, màu ANSI hoặc cách căn lề không thuộc hợp đồng.

## 14. Các lỗi thường gặp

### Command không xuất hiện trong help

Kiểm tra command đã được đăng ký vào runtime chưa, help command có bị tắt không và template có lọc command theo điều kiện riêng hay không. Command không được đăng ký khác với command đã đăng ký nhưng unavailable.

### Tham số bắt buộc không được đánh dấu đúng

Kiểm tra `required` trong annotation hoặc `.required()` trong programmatic registration. Với legacy annotation, kiểm tra `@ShellOption` và giá trị mặc định vì cách khai báo optional khác mô hình mới.

### Help hiển thị default nhưng command không dùng default đó

Kiểm tra metadata `defaultValue` có được gắn đúng option, kiểu dữ liệu có chuyển đổi được và target có nhận giá trị qua binding như dự kiến. Help phản ánh metadata; test thực thi mới xác nhận hành vi.

### Default value không hợp lệ

Kiểm tra default có chuyển đổi được sang kiểu tham số và có thỏa Bean Validation hay không. Giá trị mặc định cũng phải tuân theo hợp đồng input.

### Command unavailable nhưng bị hiểu là không tồn tại

Giữ thông tin availability trong help. Reason nên giải thích điều kiện còn thiếu, ví dụ cần kết nối hoặc chọn môi trường.

### Lý do unavailable hiển thị câu không tự nhiên

Reason được nối sau “because” trong thông báo mặc định. Hãy bắt đầu bằng chữ thường và không kết thúc bằng dấu chấm; không lặp lại từ “because”.

### Template tùy chỉnh làm mất thông tin tham số

Kiểm tra template có duyệt `parameters`, `required`, `defaultValue` và `hasDefaultValue` hay không. Đừng chỉ render tên command và description nếu người dùng cần biết cách gọi.

### Nhầm hai nhóm property help

`spring.shell.command.help.*` điều khiển built-in help command và template; `spring.shell.help.*` điều khiển help options gắn vào command. Kiểm tra đúng namespace trước khi đổi cấu hình.

## 15. Lưu ý khi dùng Spring Shell 4.x

Spring Shell 4.x tổ chức lại annotation và package. `@Command` có thể chứa các thuộc tính cấu hình command như tên, mô tả và availability provider; `@Option` dùng `longName`, `shortName`, `required` và `defaultValue` theo API mới.

Ví dụ rút gọn theo annotation model 4.x:

```java
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
public class ReportCommandsV4 {

    @Command(name = "report list", description = "Liệt kê báo cáo")
    public String list(
            @Option(longName = "limit", required = false,
                    defaultValue = "50",
                    description = "Số bản ghi tối đa cần hiển thị") Integer limit) {
        return "Hiển thị tối đa " + limit + " báo cáo.";
    }
}
```

Trong 4.x, `--help`/`-h` vẫn là cách gọi trợ giúp ngắn được tài liệu hóa; help command tiếp tục cung cấp danh sách và chi tiết command. Tuy nhiên, output mặc định, package và thuộc tính annotation có thể khác giữa các major version. Đối chiếu tài liệu đúng phiên bản trước khi sao chép cấu hình 3.x sang 4.x.

## 16. Checklist trước khi phát hành CLI

- [ ] `help` liệt kê đúng các command người dùng cần khám phá.
- [ ] `help <command>` cung cấp mô tả và cú pháp đầy đủ.
- [ ] Help options `--help`/`-h` được bật và có tên nhất quán nếu sử dụng.
- [ ] Mỗi tham số có trạng thái required/optional đúng.
- [ ] Default value được hiển thị hoặc giải thích khi có ý nghĩa với người dùng.
- [ ] Default value chuyển đổi được và thỏa validation.
- [ ] Help model/template giữ trường `required`, `defaultValue`, `hasDefaultValue`.
- [ ] Command unavailable vẫn có thể được khám phá theo thiết kế help.
- [ ] Reason nêu điều kiện còn thiếu và bước tiếp theo.
- [ ] Reason không tiết lộ bí mật hoặc thông tin nội bộ.
- [ ] Hai nhóm property `spring.shell.command.help.*` và `spring.shell.help.*` được cấu hình đúng mục đích.
- [ ] Có integration test cho help, required, default và availability.
- [ ] Đã đối chiếu API với major/minor version đang dùng.

## 17. Tự kiểm tra

**Câu 1.** `help` và `help deploy` cung cấp hai loại thông tin nào?

**Gợi ý trả lời:** `help` liệt kê command và mô tả ngắn; `help deploy` hiển thị chi tiết command, cú pháp và metadata tham số.

**Câu 2.** `required = true` khác `defaultValue = "50"` như thế nào?

**Gợi ý trả lời:** `required` quy định người dùng có phải cung cấp option hay không; `defaultValue` cung cấp giá trị thay thế khi option không được truyền.

**Câu 3.** Vì sao default value vẫn cần được kiểm thử?

**Gợi ý trả lời:** Default phải chuyển đổi được sang kiểu tham số và thỏa validation/nghiệp vụ. Metadata help đúng chưa chứng minh runtime binding hoạt động đúng.

**Câu 4.** Command unavailable có nên biến mất khỏi help không?

**Gợi ý trả lời:** Không nhất thiết. Spring Shell 3.4 liệt kê cả command unavailable để người dùng khám phá chức năng và biết lý do chưa thể chạy.

**Câu 5.** Help template có thể dùng trường nào để quyết định hiển thị giá trị mặc định?

**Gợi ý trả lời:** `hasDefaultValue` cho biết có default hay không; `defaultValue` chứa giá trị để hiển thị.

**Câu 6.** Lý do availability nên được viết như thế nào?

**Gợi ý trả lời:** Ngắn gọn, cụ thể, nối tự nhiên sau “because”, bắt đầu bằng chữ thường, không có dấu chấm cuối và gợi ý bước khắc phục.

## Kết luận

Trợ giúp của Spring Shell cho người dùng biết command nào tồn tại và cách gọi chúng. `help` hiển thị danh sách command; `help <command>` cung cấp chi tiết; `--help` hoặc `-h` có thể mở trợ giúp ngắn ngay tại command. Metadata tham số cho biết kiểu, mô tả, tính bắt buộc và giá trị mặc định.

`required` quyết định người dùng có phải truyền option, `defaultValue` xác định giá trị dùng khi option vắng mặt, còn validation kiểm tra giá trị sau binding có hợp lệ hay không. Availability bổ sung thông tin trạng thái: command có thể đã đăng ký nhưng chưa chạy được và cần nêu lý do. Hãy giữ các trường này trong help template, viết reason có thể hành động được và kiểm thử cả output trợ giúp lẫn hành vi command để CLI tự mô tả chính xác.

## Tài liệu tham khảo

- [Spring Shell 3.4.3 — Help](https://docs.spring.io/spring-shell/reference/3.4/commands/builtin/help.html)
- [Spring Shell 3.4.1 — Optional Value](https://docs.spring.io/spring-shell/reference/3.4/options/optional.html)
- [Spring Shell 3.4.1 — Default Value](https://docs.spring.io/spring-shell/reference/3.4/options/default.html)
- [Spring Shell 3.4.3 — Command Availability](https://docs.spring.io/spring-shell/reference/3.4/commands/availability.html)
- [Spring Shell 3.3.4 — Help Options](https://docs.spring.io/spring-shell/reference/3.3/commands/helpoptions.html)
- [Spring Shell 4.0.4 — Help](https://docs.spring.io/spring-shell/reference/commands/builtin/help.html)
- [Spring Shell 4.x — Migration guide](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide)

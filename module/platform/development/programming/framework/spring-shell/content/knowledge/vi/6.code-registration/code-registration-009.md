# Đọc tham số từ ngữ cảnh của một lệnh khai báo bằng mã

Trong Spring Shell, một command có thể được tạo bằng annotation hoặc bằng API lập trình. Với cách khai báo bằng mã, ứng dụng tạo một bean kiểu Command, mô tả tên lệnh, argument, option và hành vi thực thi bằng Command.Builder. Khi người dùng gọi lệnh, Spring Shell truyền một CommandContext vào hàm thực thi. CommandContext chứa dữ liệu của lần gọi hiện tại, nhờ đó command có thể đọc tham số mà không cần tự phân tích chuỗi lệnh.

Bài học này tập trung vào cách khai báo argument và option cho một command bằng builder, sau đó lấy giá trị của chúng qua CommandContext. Ở mô hình annotation, Spring Shell bind tham số vào các tham số của phương thức command; ở mô hình lập trình, callback nhận một CommandContext và chủ động đọc giá trị cần dùng. Đây là kỹ năng quan trọng khi xây dựng CLI cho các thao tác triển khai, xuất báo cáo, quản trị dữ liệu hoặc các tác vụ tự động. Command có thể tiếp nhận đầu vào từ dòng lệnh, kiểm tra giá trị rồi chuyển dữ liệu đã chuẩn hóa cho service nghiệp vụ.

## 1. Luồng dữ liệu của command khai báo bằng mã

Với command khai báo bằng mã, phần định nghĩa và phần đọc tham số là hai giai đoạn liên quan nhưng khác nhau:

1. Khi ứng dụng khởi động, bean Command mô tả cấu trúc command: tên, mô tả, argument, option và hàm thực thi.
2. Spring Shell đưa command vào CommandRegistry.
3. Khi người dùng chạy command, parser phân tích dòng lệnh và tạo ParsedInput.
4. Framework tạo CommandContext cho lần gọi, chứa ParsedInput cùng các dịch vụ hỗ trợ.
5. Hàm execute nhận CommandContext, lấy argument/option và gọi nghiệp vụ.

~~~mermaid
flowchart TD
    A[Command bean] --> B[CommandRegistry]
    C[Người dùng nhập command] --> D[CommandParser]
    D --> E[ParsedInput]
    B --> F[CommandExecutor]
    E --> F
    F --> G[CommandContext]
    G --> H[Hàm execute]
    H --> I[Đọc argument và option]
    I --> J[Service nghiệp vụ]
    J --> K[Kết quả hoặc output]
~~~

Điểm cần nhớ là CommandContext đại diện cho dữ liệu của một lần thực thi. Không cần tạo context bằng tay trong command bean. Framework truyền context vào callback khi command được gọi; chỉ đọc context trong phạm vi lần gọi đó và không lưu nó làm trạng thái dùng chung của bean.

## 2. Khai báo argument và option trong Command.Builder

Trong Spring Shell 4.x, command lập trình được định nghĩa bằng Command.Builder. Hai kiểu mô tả tham số là CommandArgument và CommandOption:

- CommandArgument mô tả argument theo vị trí. Mỗi argument có index, mô tả, giá trị mặc định, kiểu dữ liệu và tùy chọn variadic.
- CommandOption mô tả option có tên. Mỗi option có thể có shortName, longName, mô tả, trạng thái required, giá trị mặc định và kiểu dữ liệu.

Có thể tạo các mô tả này bằng builder tĩnh with():

~~~java
CommandArgument period = CommandArgument.with()
        .index(0)
        .description("Kỳ báo cáo")
        .defaultValue("monthly")
        .type(String.class)
        .build();

CommandOption format = CommandOption.with()
        .shortName('f')
        .longName("format")
        .description("Định dạng báo cáo")
        .defaultValue("csv")
        .type(String.class)
        .build();
~~~

Argument index bắt đầu từ 0. Vì vậy, argument đầu tiên được đọc bằng getArgumentByIndex(0), argument thứ hai bằng getArgumentByIndex(1). Option được tìm bằng tên ngắn hoặc tên dài, không phụ thuộc vị trí mà người dùng đặt option trên dòng lệnh.

Command.Builder nhận danh sách các mô tả này qua arguments(...) và options(...). Khi command được đăng ký, các metadata này giúp Spring Shell hiểu cú pháp, trợ giúp và cách phân tích đầu vào.

Trong Spring application context, Spring Shell mặc định đưa các bean kiểu Command vào CommandRegistry. Vì vậy, command lập trình thường được tạo bằng một phương thức @Bean; registry và bộ thực thi sẽ sử dụng command đó khi người dùng gọi tên lệnh.

## 3. CommandContext cung cấp những gì?

Trong Spring Shell 4.x, CommandContext là một record chứa thông tin runtime của command hiện tại:

| Thành phần | Kiểu | Công dụng |
|---|---|---|
| parsedInput() | ParsedInput | Toàn bộ kết quả phân tích dòng lệnh |
| commandRegistry() | CommandRegistry | Tập command đã đăng ký trong ứng dụng |
| outputWriter() | PrintWriter | Ghi nội dung ra shell |
| inputReader() | InputReader | Đọc thêm dữ liệu do người dùng nhập trong lúc command chạy |

CommandContext còn có các phương thức tiện ích để tìm tham số:

| Phương thức | Cách tìm |
|---|---|
| getArgumentByIndex(int index) | Lấy argument theo index, bắt đầu từ 0 |
| getOptionByLongName(String longName) | Lấy option theo tên dài |
| getOptionByShortName(char shortName) | Lấy option theo ký tự tên ngắn |
| getOptionByName(String optionName) | Lấy option theo tên ngắn hoặc tên dài |

Các phương thức tra cứu argument và option có thể trả về null nếu không tìm thấy. Vì vậy, command cần kiểm tra kết quả trước khi đọc value().

## 4. Đọc argument theo vị trí

getArgumentByIndex() trả về một CommandArgument. Giá trị người dùng nhập được lấy qua value(); mô tả và giá trị mặc định có thể đọc qua description() và defaultValue().

~~~java
CommandArgument periodArgument = context.getArgumentByIndex(0);

String period = periodArgument == null
        ? "monthly"
        : periodArgument.value();
~~~

Đoạn mã trên minh họa cách đọc argument đầu tiên. Trong command thực tế, nên xử lý cả trường hợp value rỗng hoặc null và dùng defaultValue đã khai báo nếu cần:

~~~java
private static String argumentValue(
        CommandArgument argument,
        String fallback) {

    if (argument == null) {
        return fallback;
    }

    String value = argument.value();
    if (value != null && !value.isBlank()) {
        return value;
    }

    String defaultValue = argument.defaultValue();
    return defaultValue == null || defaultValue.isBlank()
            ? fallback
            : defaultValue;
}
~~~

Đối với argument variadic, metadata của CommandArgument có thể đánh dấu variadic=true. Khi cần nhiều giá trị, hãy khai báo rõ điều đó trong command và kiểm tra cách phân phối các argument theo index. Không nên tự giả định mọi argument còn lại đều thuộc cùng một tham số nếu command có nhiều argument được mô tả riêng.

## 5. Đọc option theo tên

Option được đọc theo tên thay vì vị trí. Ví dụ, với option có tên dài format và tên ngắn f, có thể dùng một trong ba cách:

~~~java
CommandOption byLongName = context.getOptionByLongName("format");
CommandOption byShortName = context.getOptionByShortName('f');
CommandOption byEitherName = context.getOptionByName("format");
~~~

CommandOption cung cấp value() để lấy giá trị runtime, defaultValue() để lấy giá trị mặc định được khai báo, required() để biết option có bắt buộc hay không và type() để đọc kiểu dữ liệu đã mô tả.

~~~java
private static String optionValue(
        CommandOption option,
        String fallback) {

    if (option == null) {
        return fallback;
    }

    String value = option.value();
    if (value != null && !value.isBlank()) {
        return value;
    }

    String defaultValue = option.defaultValue();
    return defaultValue == null || defaultValue.isBlank()
            ? fallback
            : defaultValue;
}
~~~

Khi lấy option, truyền tên thuần như format hoặc ký tự f. Không truyền chuỗi có tiền tố -- hoặc -. Nếu dùng getOptionByShortName(), đối số phải là một ký tự char.

## 6. Ví dụ hoàn chỉnh: command tạo báo cáo

Ví dụ sau khai báo command report bằng một bean Command. Người dùng có thể truyền kỳ báo cáo theo vị trí và chọn định dạng hoặc chế độ chạy thử bằng option:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.core.command.Command;
import org.springframework.shell.core.command.CommandArgument;
import org.springframework.shell.core.command.CommandOption;

@Configuration
class ReportCommandConfiguration {

    @Bean
    Command reportCommand(ReportService reportService) {
        return Command.builder()
                .name("report")
                .description("Tạo báo cáo theo kỳ")
                .arguments(
                        CommandArgument.with()
                                .index(0)
                                .description("Kỳ báo cáo")
                                .defaultValue("monthly")
                                .type(String.class)
                                .build()
                )
                .options(
                        CommandOption.with()
                                .shortName('f')
                                .longName("format")
                                .description("Định dạng csv hoặc json")
                                .defaultValue("csv")
                                .type(String.class)
                                .build(),
                        CommandOption.with()
                                .shortName('d')
                                .longName("dry-run")
                                .description("Chỉ mô phỏng, không ghi dữ liệu")
                                .defaultValue("false")
                                .type(Boolean.class)
                                .build()
                )
                .execute(context -> {
                    CommandArgument periodArgument =
                            context.getArgumentByIndex(0);
                    CommandOption formatOption =
                            context.getOptionByLongName("format");
                    CommandOption dryRunOption =
                            context.getOptionByShortName('d');

                    String period = argumentValue(
                            periodArgument, "monthly");
                    String format = optionValue(
                            formatOption, "csv");
                    boolean dryRun = Boolean.parseBoolean(
                            optionValue(dryRunOption, "false"));

                    if (!format.equals("csv") && !format.equals("json")) {
                        throw new IllegalArgumentException(
                                "Định dạng chỉ hỗ trợ csv hoặc json");
                    }

                    return reportService.generate(period, format, dryRun);
                });
    }

    private static String argumentValue(
            CommandArgument argument,
            String fallback) {
        if (argument == null) {
            return fallback;
        }
        String value = argument.value();
        if (value != null && !value.isBlank()) {
            return value;
        }
        String defaultValue = argument.defaultValue();
        return defaultValue == null || defaultValue.isBlank()
                ? fallback
                : defaultValue;
    }

    private static String optionValue(
            CommandOption option,
            String fallback) {
        if (option == null) {
            return fallback;
        }
        String value = option.value();
        if (value != null && !value.isBlank()) {
            return value;
        }
        String defaultValue = option.defaultValue();
        return defaultValue == null || defaultValue.isBlank()
                ? fallback
                : defaultValue;
    }
}
~~~

Giả sử ReportService là service nghiệp vụ đã được Spring quản lý. Command chỉ đọc dữ liệu đầu vào, kiểm tra định dạng rồi chuyển các giá trị cho service.

Người dùng có thể gọi:

~~~text
report quarterly --format=json --dry-run=true
report yearly -f=csv -d=false
report
~~~

Trong lệnh đầu tiên, argument index 0 là quarterly; hai option có giá trị json và true. Lệnh thứ hai dùng tên ngắn f và d. Lệnh cuối không truyền tham số nên command dùng các giá trị mặc định đã khai báo.

Hàm execute ở ví dụ trả về String. Spring Shell ghi giá trị trả về ra shell output. Nếu muốn ghi nhiều dòng hoặc điều khiển output trực tiếp, có thể dùng context.outputWriter().println(...). Khi đó callback có thể dùng dạng Consumer:

~~~java
.execute(context -> {
    context.outputWriter().println("Đang xử lý command...");
})
~~~

Command.Builder có hai overload execute: một nhận Consumer<CommandContext> và một nhận Function<CommandContext, String>. Chọn Consumer khi tự ghi output; chọn Function khi muốn trả về chuỗi để framework hiển thị.

## 7. Đọc toàn bộ ParsedInput khi cần xử lý linh hoạt

Khi chỉ cần một vài tham số đã biết trước, các phương thức getOptionByLongName(), getOptionByShortName() và getArgumentByIndex() là cách đọc ngắn gọn nhất. Khi cần kiểm tra toàn bộ dữ liệu, dùng parsedInput():

~~~java
ParsedInput input = context.parsedInput();

String commandName = input.commandName();
List<String> subCommands = input.subCommands();
List<CommandArgument> arguments = input.arguments();
List<CommandOption> options = input.options();
~~~

Ví dụ duyệt qua option:

~~~java
for (CommandOption option : context.parsedInput().options()) {
    context.outputWriter().printf(
            "Option %s có giá trị %s%n",
            option.longName(),
            option.value()
    );
}
~~~

Cách duyệt này hữu ích cho command tổng quát, command chẩn đoán hoặc công cụ cần xử lý nhiều option. Tránh in toàn bộ context hoặc mọi giá trị option trong môi trường thật nếu command có thể nhận token, mật khẩu hay dữ liệu nhạy cảm.

## 8. CommandContext còn hỗ trợ output và input tương tác

CommandContext không chỉ chứa argument và option. Hai thành phần inputReader() và outputWriter() hỗ trợ command tương tác với người dùng:

- outputWriter() trả về PrintWriter để ghi thông báo hoặc kết quả.
- inputReader() trả về InputReader để hỏi thêm một dòng dữ liệu trong lúc command đang chạy.
- readPassword() có thể dùng khi cần nhập bí mật; phương thức trả về char[].

Ví dụ đọc xác nhận bổ sung:

~~~java
String confirmation;
try {
    confirmation = context.inputReader()
            .readInput("Xác nhận triển khai? (yes/no): ");
} catch (Exception exception) {
    throw new IllegalStateException(
            "Không đọc được xác nhận từ terminal", exception);
}
~~~

InputReader phục vụ dữ liệu được nhập sau khi command đã bắt đầu. Nó khác với argument và option trên dòng lệnh. Khi chạy script hoặc chế độ không tương tác, không nên phụ thuộc vào prompt để nhận giá trị bắt buộc; hãy cung cấp chúng qua command argument hoặc option.

## 9. Kiểu dữ liệu, mặc định và validation

CommandArgument và CommandOption lưu value dưới dạng String trong API runtime. Thuộc tính type() mô tả kiểu đã khai báo cho tham số, còn code của command vẫn nên chuyển và xác thực giá trị trước khi đưa vào nghiệp vụ.

Ví dụ chuyển option limit thành số nguyên:

~~~java
CommandOption limitOption = context.getOptionByLongName("limit");
String rawLimit = optionValue(limitOption, "20");

int limit;
try {
    limit = Integer.parseInt(rawLimit);
} catch (NumberFormatException exception) {
    throw new IllegalArgumentException(
            "limit phải là số nguyên", exception);
}

if (limit < 1 || limit > 500) {
    throw new IllegalArgumentException(
            "limit phải nằm trong khoảng từ 1 đến 500");
}
~~~

Nên xử lý đầu vào theo thứ tự:

1. Tìm argument hoặc option bằng phương thức phù hợp.
2. Xử lý trường hợp không có giá trị.
3. Áp dụng defaultValue nếu command cho phép.
4. Chuyển chuỗi sang kiểu nghiệp vụ như số, boolean, ngày tháng hoặc enum.
5. Kiểm tra miền giá trị và quy tắc nghiệp vụ.
6. Chỉ chuyển dữ liệu hợp lệ cho service.

Khai báo required(true) cho option bắt buộc và defaultValue(...) cho option tùy chọn có giá trị mặc định. Dù đã mô tả required, vẫn nên giữ kiểm tra ở ranh giới command đối với những điều kiện nghiệp vụ quan trọng.

## 10. Những lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| getArgumentByIndex() trả về null | Index không tồn tại hoặc command không nhận argument đó | Kiểm tra index và metadata trong arguments(...) |
| getOptionByLongName() trả về null | Sai tên option hoặc option chưa được khai báo | Dùng tên thuần, kiểm tra longName(...) |
| Giá trị option rỗng | Người dùng bỏ qua option hoặc giá trị mặc định chưa được áp dụng theo cách mong đợi | Kiểm tra value() và defaultValue() riêng |
| Đọc nhầm argument | Dùng index bắt đầu từ 1 | Index argument bắt đầu từ 0 |
| Option không tìm thấy theo short name | Truyền chuỗi thay vì ký tự | Dùng getOptionByShortName('f') |
| Chuyển kiểu bị lỗi | Đầu vào không phải kiểu mong đợi | Parse và báo lỗi có hướng dẫn cho người dùng |
| Command chờ prompt khi chạy script | Dùng InputReader cho tham số cần có ngay từ đầu | Đưa dữ liệu vào argument hoặc option |
| Lộ thông tin nhạy cảm | In toàn bộ ParsedInput hoặc giá trị option vào log | Chỉ đọc và ghi những trường cần thiết |

Một lỗi thiết kế phổ biến là trộn phần đọc tham số với nghiệp vụ. Hãy giữ callback command ngắn: lấy dữ liệu, áp dụng mặc định, kiểm tra định dạng và gọi service. Các quy tắc nghiệp vụ lớn nên nằm trong service để có thể tái sử dụng và kiểm thử độc lập.

## 11. Kiểm thử command đọc tham số

Kiểm thử cần bao phủ ít nhất các trường hợp:

- Truyền đủ argument và option.
- Bỏ qua tham số có defaultValue.
- Truyền option bằng tên ngắn và tên dài.
- Thiếu argument hoặc option bắt buộc.
- Truyền chuỗi sai định dạng cho tham số số hoặc boolean.
- Truyền giá trị ngoài miền nghiệp vụ.

Với kiểm thử tích hợp Spring Shell, dùng ShellTestClient để gửi command và kiểm tra output. Ví dụ:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.ContextConfiguration;
import org.springframework.shell.test.ShellAssertions;
import org.springframework.shell.test.ShellScreen;
import org.springframework.shell.test.ShellTestClient;
import org.springframework.shell.test.autoconfigure.ShellTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.mockito.BDDMockito.given;

@ShellTest
@ContextConfiguration(classes = ReportCommandConfiguration.class)
class ReportCommandTests {

    @Autowired
    ShellTestClient client;

    @MockitoBean
    ReportService reportService;

    @Test
    void readsArgumentAndOptions() throws Exception {
        given(reportService.generate("quarterly", "json", true))
                .willReturn("Đã tạo báo cáo quarterly");

        ShellScreen screen = client.sendCommand(
                "report quarterly --format=json --dry-run=true");

        ShellAssertions.assertThat(screen)
                .containsText("Đã tạo báo cáo quarterly");
    }
}
~~~

Nên mock ReportService khi mục tiêu của test là xác minh việc đọc và truyền tham số. Khi cần kiểm tra nghiệp vụ, viết test riêng cho service. Cách chia này giúp xác định nhanh lỗi nằm ở đăng ký command, lấy dữ liệu từ context hay xử lý nghiệp vụ.

## 12. Bài tập thực hành

Tạo command backup bằng Command.Builder với cấu trúc:

- Argument index 0: đường dẫn thư mục nguồn, mặc định là current.
- Option --destination, short name -t: thư mục đích, mặc định là backup.
- Option --compress, short name -c: boolean, mặc định false.
- Hàm execute đọc ba giá trị qua CommandContext và trả về thông báo mô tả kế hoạch backup.

Thử các lệnh:

~~~text
backup
backup documents
backup documents --destination=archive
backup documents -t=archive --compress=true
~~~

Sau khi hoàn thành, hãy kiểm tra:

1. Argument có được lấy bằng index 0 không?
2. Option có thể được đọc bằng tên dài lẫn tên ngắn không?
3. Khi bỏ qua tham số, defaultValue có được áp dụng đúng không?
4. Khi compress nhận giá trị không hợp lệ, command có thông báo rõ ràng không?
5. Phần callback có chuyển dữ liệu đã kiểm tra sang service hay đang tự thực hiện toàn bộ nghiệp vụ?

## Tài liệu tham khảo

- [Spring Shell – Command Registration](https://docs.spring.io/spring-shell/reference/commands/registration.html)
- [Spring Shell – Command Context](https://docs.spring.io/spring-shell/reference/commands/context.html)
- [Spring Shell API – CommandContext](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/CommandContext.html)
- [Spring Shell API – CommandArgument](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/CommandArgument.html)
- [Spring Shell API – CommandOption](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/CommandOption.html)
- [Spring Shell API – Command.Builder](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/Command.Builder.html)
- [Spring Shell – Reading Input](https://docs.spring.io/spring-shell/reference/commands/reading.html)

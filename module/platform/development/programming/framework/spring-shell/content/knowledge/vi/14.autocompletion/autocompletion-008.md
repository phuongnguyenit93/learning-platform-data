# `FileNameCompletionProvider`, `EnumCompletionProvider` và bộ gộp trong 4.x

Khi người dùng nhập command trong Spring Shell, họ không phải nhớ mọi đường dẫn file hay mọi giá trị được phép của một option. Trong shell tương tác dùng JLine, nhấn `Tab` có thể hiển thị các gợi ý phù hợp với vị trí con trỏ. Spring Shell 4.x cung cấp các completion provider dựng sẵn để gợi ý tên file, giá trị enum và kết hợp nhiều nguồn gợi ý cho cùng một command.

Ba thành phần cần biết là `FileNameCompletionProvider`, `EnumCompletionProvider` và `CompositeCompletionProvider`. Provider đầu tiên tìm tên file cục bộ; provider thứ hai đưa ra các hằng enum; provider thứ ba kết hợp kết quả từ nhiều provider. Khi command có nhiều option với kiểu dữ liệu khác nhau, có thể kết hợp chúng thành một provider ở cấp command để trải nghiệm tự hoàn thành nhất quán.

Bài viết sử dụng API Spring Shell 4.0.3, thuộc package `org.springframework.shell.core.command.completion`. Trong Spring Shell 4, provider được gắn ở cấp command; cách khai báo `ValueProvider` hoặc `@ShellOption(valueProvider = ...)` của mô hình cũ 3.x không còn là API tương ứng.

## Cách hoạt động của tự hoàn thành

Trong shell tương tác dựa trên JLine, người dùng nhập một phần command rồi nhấn `Tab`. Spring Shell xem nội dung hiện tại của dòng lệnh, vị trí con trỏ và command/option đang được nhập để yêu cầu completion provider tạo các gợi ý.

```mermaid
flowchart TD
    A[Người dùng nhập một phần command] --> B[Nhấn Tab trong JLine shell]
    B --> C[Tạo CompletionContext]
    C --> D[CompletionProvider.apply(context)]
    D --> E[Danh sách CompletionProposal]
    E --> F[JLine hiển thị các lựa chọn]
    F --> G[Người dùng chọn hoặc tiếp tục nhập]
```

`CompletionProvider` là một functional interface có hợp đồng:

```java
CompletionProvider extends Function<CompletionContext, List<CompletionProposal>>
```

Nói cách khác, provider nhận `CompletionContext` và trả về danh sách `CompletionProposal`. Context cung cấp thông tin về phần buffer hiện tại, từ đang đặt con trỏ, vị trí con trỏ, command và option liên quan. Proposal mô tả nội dung được đề xuất cùng metadata hiển thị hoặc cách chèn nội dung.

Tự hoàn thành là gợi ý cho người dùng, không thay thế parsing, chuyển đổi kiểu, validation hay kiểm tra quyền. Người dùng vẫn có thể nhập thủ công một giá trị không nằm trong danh sách; command phải tiếp tục xác thực đầu vào khi thực thi.

## `FileNameCompletionProvider`: gợi ý đường dẫn cục bộ

`FileNameCompletionProvider` tạo gợi ý từ các file cục bộ. Provider có thể tìm tên theo đường dẫn tương đối với working directory hiện tại hoặc đường dẫn tuyệt đối. Nó phù hợp với option nhận `File` như file nguồn, file cấu hình, file nhập dữ liệu hoặc đường dẫn đầu ra.

Ví dụ command nhận một file đầu vào:

```java
import java.io.File;

import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
public class ImportCommands {

    private final ImportService importService;

    public ImportCommands(ImportService importService) {
        this.importService = importService;
    }

    @Command(
            name = "data import",
            description = "Nhập dữ liệu từ file",
            completionProvider = "fileNameCompletionProvider")
    public String importFile(
            @Option(longName = "file", required = true,
                    description = "Đường dẫn file cần nhập") File file) {

        return importService.importFile(file);
    }
}
```

Đăng ký provider thành bean:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.core.command.completion.CompletionProvider;
import org.springframework.shell.core.command.completion.FileNameCompletionProvider;

@Configuration
public class CompletionConfiguration {

    @Bean
    CompletionProvider fileNameCompletionProvider() {
        return new FileNameCompletionProvider();
    }
}
```

Khi người dùng nhập:

```text
data import --file ./data/
```

và nhấn `Tab`, provider có thể gợi ý tên file hoặc thư mục bên dưới đường dẫn hiện tại. Người dùng có thể tiếp tục chọn thư mục rồi nhấn `Tab` lần nữa để đi sâu hơn.

Một số điểm cần nhớ:

- Provider làm việc với filesystem cục bộ của tiến trình Spring Shell.
- Đường dẫn tương đối được hiểu từ working directory của ứng dụng.
- Có thể nhập đường dẫn tuyệt đối khi cần truy cập vị trí ngoài working directory.
- Provider chỉ gợi ý tên đường dẫn; nó không mở file, kiểm tra nội dung hay bảo đảm ứng dụng có quyền đọc file.
- Nếu ứng dụng chạy trong container, working directory và filesystem nhìn thấy từ container mới là môi trường provider sử dụng.

`FileNameCompletionProvider` không phải bộ tìm file trên máy từ xa hoặc trên object storage. Với S3, FTP, database hay một kho tài liệu riêng, hãy viết provider tùy chỉnh truy vấn nguồn dữ liệu tương ứng và chỉ trả về những lựa chọn người dùng được phép nhìn thấy.

## `EnumCompletionProvider`: gợi ý các hằng enum

Khi option chỉ nhận một tập giá trị cố định, enum giúp mô tả hợp đồng kiểu ở Java. `EnumCompletionProvider` đọc các hằng của enum và tạo proposal cho chúng.

Ví dụ enum định dạng báo cáo:

```java
public enum ReportFormat {
    CSV,
    JSON,
    XML
}
```

Command nhận một giá trị `ReportFormat`:

```java
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
public class ReportCommands {

    private final ReportService reportService;

    public ReportCommands(ReportService reportService) {
        this.reportService = reportService;
    }

    @Command(
            name = "report export",
            description = "Xuất báo cáo",
            completionProvider = "reportFormatCompletionProvider")
    public String export(
            @Option(longName = "format", required = true,
                    description = "Định dạng xuất báo cáo") ReportFormat format) {

        return reportService.export(format);
    }
}
```

Provider:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.shell.core.command.completion.CompletionProvider;
import org.springframework.shell.core.command.completion.EnumCompletionProvider;

@Bean
CompletionProvider reportFormatCompletionProvider() {
    return new EnumCompletionProvider(ReportFormat.class);
}
```

Khi người dùng nhập `report export --format ` rồi nhấn `Tab`, provider đề xuất các giá trị enum như `CSV`, `JSON` và `XML`. Sau khi chọn, Spring Shell vẫn chuyển giá trị được nhập thành `ReportFormat` theo cơ chế binding và conversion của command.

### Thêm prefix cho giá trị enum

Constructor của `EnumCompletionProvider` có thêm biến thể nhận một prefix:

```java
new EnumCompletionProvider(ReportFormat.class, "--format")
```

Prefix được thêm trước mỗi hằng enum. Cách này hữu ích khi proposal cần chứa cả tên option và giá trị theo dạng key/value. Ví dụ chính thức của Spring Shell dùng `new EnumCompletionProvider(Gender.class, "--gender")` để tạo gợi ý có prefix cho option `gender`.

Hãy kiểm tra chuỗi được chèn trong terminal với cú pháp option của command và phiên bản đang dùng. Nếu provider được dùng trong một composite cho nhiều option, cần bảo đảm prefix ứng với đúng option để tránh gợi ý enum xuất hiện ở vị trí nhập dữ liệu khác.

### `DefaultCompletionProvider` và enum

Từ Spring Shell 4.0.1, `DefaultCompletionProvider` có khả năng gợi ý giá trị cho option kiểu enum và tạo prefix cho tên option theo ngữ cảnh nhập hiện tại. Nếu chỉ cần hành vi mặc định, hãy kiểm tra xem provider mặc định đã đáp ứng nhu cầu chưa. `EnumCompletionProvider` hữu ích khi muốn tạo provider riêng, chủ động chọn enum hoặc kết hợp nó với nguồn gợi ý khác.

## `CompositeCompletionProvider`: kết hợp nhiều nguồn gợi ý

`CompositeCompletionProvider` nhận một hoặc nhiều `CompletionProvider` qua constructor dạng varargs:

```java
new CompositeCompletionProvider(provider1, provider2, provider3)
```

Composite provider thực hiện hợp đồng `CompletionProvider` và kết hợp kết quả từ các provider thành phần. Nhờ đó, command có thể cung cấp gợi ý cho nhiều loại dữ liệu qua một bean duy nhất.

Ví dụ kết hợp gợi ý tên preset và enum định dạng:

```java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.shell.core.command.completion.CompositeCompletionProvider;
import org.springframework.shell.core.command.completion.CompletionProposal;
import org.springframework.shell.core.command.completion.CompletionProvider;
import org.springframework.shell.core.command.completion.EnumCompletionProvider;

@Bean
CompletionProvider exportCompletionProvider() {
    CompletionProvider nameCompletionProvider = context -> List.of(
            new CompletionProposal("--name=nightly")
                    .displayText("nightly")
                    .description("Bản xuất chạy ban đêm"),
            new CompletionProposal("--name=release")
                    .displayText("release")
                    .description("Bản xuất phát hành")
    );

    CompletionProvider formatCompletionProvider =
            new EnumCompletionProvider(ReportFormat.class, "--format");

    return new CompositeCompletionProvider(
            nameCompletionProvider,
            formatCompletionProvider);
}
```

Gắn bean vào command:

```java
@Command(
        name = "report export",
        description = "Xuất báo cáo",
        completionProvider = "exportCompletionProvider")
public String export(
        @Option(longName = "name") String name,
        @Option(longName = "format") ReportFormat format) {
    return reportService.export(name, format);
}
```

Ví dụ này minh họa một provider cho các tên preset và một provider cho các giá trị enum. Trong ứng dụng thực tế, nên để provider thành phần kiểm tra `CompletionContext` để chỉ đề xuất khi người dùng đang hoàn thành đúng option. Điều đó tránh việc danh sách preset và enum xuất hiện lẫn nhau.

### Kết hợp file và enum theo option đang nhập

`CompletionContext` có `getCommandOption()` để nhận biết option hiện tại. `CommandOption` cung cấp `longName()` và `type()`. Có thể dùng thông tin này để định tuyến đến provider phù hợp:

```java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.shell.core.command.CommandOption;
import org.springframework.shell.core.command.completion.CompositeCompletionProvider;
import org.springframework.shell.core.command.completion.CompletionProvider;
import org.springframework.shell.core.command.completion.EnumCompletionProvider;
import org.springframework.shell.core.command.completion.FileNameCompletionProvider;

@Bean
CompletionProvider artifactCompletionProvider() {
    FileNameCompletionProvider fileNames = new FileNameCompletionProvider();
    EnumCompletionProvider formats =
            new EnumCompletionProvider(ReportFormat.class, "--format");

    CompletionProvider fileOptionProvider = context -> {
        CommandOption option = context.getCommandOption();
        if (option == null || !"file".equals(option.longName())) {
            return List.of();
        }
        return fileNames.apply(context);
    };

    CompletionProvider formatOptionProvider = context -> {
        CommandOption option = context.getCommandOption();
        if (option == null || !"format".equals(option.longName())) {
            return List.of();
        }
        return formats.apply(context);
    };

    return new CompositeCompletionProvider(
            fileOptionProvider,
            formatOptionProvider);
}
```

Command tương ứng:

```java
@Command(
        name = "artifact publish",
        description = "Phát hành artifact",
        completionProvider = "artifactCompletionProvider")
public String publish(
        @Option(longName = "file", description = "File artifact") File file,
        @Option(longName = "format", description = "Định dạng artifact") ReportFormat format) {

    return artifactService.publish(file, format);
}
```

Khi con trỏ nằm ở giá trị của `--file`, provider file được gọi. Khi con trỏ nằm ở giá trị của `--format`, provider enum được gọi. Mỗi wrapper trả danh sách rỗng khi option hiện tại không thuộc phạm vi của nó. Composite nhận các wrapper này và hợp nhất các proposal được tạo.

Đây là cách kết hợp rõ ràng cho command có nhiều option. Nếu chỉ có một option file hoặc một option enum, đăng ký provider tương ứng riêng thường đơn giản hơn.

## Đăng ký provider với command

### Command khai báo bằng annotation

Trong mô hình annotation 4.x, `@Command` có thuộc tính `completionProvider` nhận tên bean. Provider phải được đăng ký trong Spring ApplicationContext:

```java
@Bean
CompletionProvider fileNameCompletionProvider() {
    return new FileNameCompletionProvider();
}
```

Sau đó:

```java
@Command(
        name = "data import",
        completionProvider = "fileNameCompletionProvider")
public String importFile(@Option(longName = "file") File file) {
    // ...
}
```

Tên trong `completionProvider` phải khớp với tên bean. Nếu bean được khai báo bằng phương thức `@Bean`, tên mặc định là tên phương thức; nếu đặt tên khác qua `@Bean("...")`, annotation cần tham chiếu đúng tên đó.

### Command đăng ký bằng API lập trình

Với command được tạo bằng `Command.Builder`, có thể gắn provider trực tiếp:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.shell.core.command.Command;
import org.springframework.shell.core.command.CommandContext;
import org.springframework.shell.core.command.completion.CompletionProvider;

@Bean
Command reportStatusCommand(CompletionProvider reportCompletionProvider) {
    return Command.builder()
            .name("report status")
            .description("Hiển thị trạng thái báo cáo")
            .completionProvider(reportCompletionProvider)
            .execute((CommandContext context) ->
                    context.outputWriter().println("Report service is ready"));
}
```

Cách này hữu ích khi command được xây dựng bằng Java builder thay vì annotation. Có thể tái sử dụng một provider bean hoặc tạo provider chuyên biệt cho command đó.

## Tùy chỉnh `CompletionProposal`

Mỗi gợi ý được biểu diễn bằng `CompletionProposal`. Constructor nhận giá trị sẽ được chèn vào dòng lệnh:

```java
new CompletionProposal("--name=nightly")
```

Ngoài `value`, proposal có thể chứa metadata:

| Thuộc tính | Vai trò |
| --- | --- |
| `value` | Nội dung được chèn vào dòng lệnh khi chọn gợi ý |
| `displayText` | Nhãn hiển thị trong danh sách gợi ý |
| `description` | Mô tả bổ sung cho gợi ý |
| `category` | Nhóm hoặc loại gợi ý |
| `dontQuote` | Cho biết proposal không cần được quote tự động |

Ví dụ tạo gợi ý có nhãn và mô tả:

```java
CompletionProposal proposal = new CompletionProposal("--name=nightly")
        .displayText("nightly")
        .description("Bản xuất chạy ban đêm")
        .category("Preset");
```

`value` nên là cú pháp mà command thực sự chấp nhận. `displayText` có thể ngắn và dễ đọc hơn giá trị được chèn. Với đường dẫn hoặc chuỗi có khoảng trắng, hãy để parser/JLine xử lý quoting theo quy tắc; chỉ đặt `dontQuote(true)` khi chắc chắn giá trị có thể được chèn nguyên dạng mà không cần quote.

## Khi nào dùng provider dựng sẵn và khi nào viết provider riêng?

| Nhu cầu | Provider phù hợp | Lý do |
| --- | --- | --- |
| Chọn file hoặc thư mục cục bộ | `FileNameCompletionProvider` | Tìm tên đường dẫn theo working directory hoặc absolute path |
| Chọn một giá trị trong enum | `EnumCompletionProvider` | Đề xuất các hằng enum và có thể thêm prefix |
| Một command có nhiều nguồn gợi ý | `CompositeCompletionProvider` | Kết hợp nhiều provider thành một |
| Gợi ý preset tĩnh | Lambda `CompletionProvider` | Tự tạo `CompletionProposal` đơn giản |
| Gợi ý mã khách hàng từ dịch vụ | Provider tùy chỉnh | Truy vấn dữ liệu nghiệp vụ có kiểm soát |
| Gợi ý phụ thuộc option khác | Provider tùy chỉnh dùng `CompletionContext` | Có thể xét option hiện tại và phần buffer đã nhập |

Không cần viết provider riêng nếu provider dựng sẵn đã đáp ứng yêu cầu. Provider tùy chỉnh nên được dùng khi danh sách gợi ý phụ thuộc dữ liệu nghiệp vụ, người dùng hiện tại, trạng thái ứng dụng hoặc option khác.

## Viết provider tùy chỉnh theo `CompletionContext`

`CompletionContext` cung cấp các phương thức hữu ích như:

- `getWords()`: các từ trong buffer, không bao gồm phần tên command.
- `getWordIndex()`: chỉ số từ mà con trỏ đang nằm trong đó.
- `getPosition()`: vị trí con trỏ bên trong từ hiện tại.
- `currentWord()`: toàn bộ từ hiện tại, hoặc `null` nếu con trỏ ở sau từ cuối.
- `currentWordUpToCursor()`: phần từ hiện tại tính đến vị trí con trỏ.
- `getCommandOption()`: option liên quan đến vị trí hoàn thành, nếu có.
- `getCommand()`: command hiện tại, nếu đã xác định được.

Ví dụ provider gợi ý tên môi trường:

```java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.shell.core.command.completion.CompletionContext;
import org.springframework.shell.core.command.completion.CompletionProposal;
import org.springframework.shell.core.command.completion.CompletionProvider;

@Bean
CompletionProvider environmentCompletionProvider() {
    return context -> {
        String current = context.currentWordUpToCursor();

        return List.of("development", "staging", "production").stream()
                .filter(value -> current == null || value.startsWith(current))
                .map(value -> new CompletionProposal(value)
                        .description("Môi trường " + value))
                .toList();
    };
}
```

Đối với gợi ý phụ thuộc người dùng hoặc dữ liệu bên ngoài, chỉ truy vấn lượng dữ liệu nhỏ cần thiết. Không gọi API mạng chậm hoặc truy vấn toàn bộ kho dữ liệu mỗi lần người dùng nhấn `Tab`; completion cần phản hồi nhanh để không làm gián đoạn thao tác nhập.

## Lưu ý về phiên bản 3.x và 4.x

Spring Shell 4 thay đổi mô hình completion so với 3.x:

| Spring Shell 3.x | Spring Shell 4.x |
| --- | --- |
| `FileValueProvider` | `FileNameCompletionProvider` |
| `EnumValueProvider` | `EnumCompletionProvider` |
| `ValueProvider` gắn riêng trên `@ShellOption` | `CompletionProvider` gắn ở cấp command bằng `@Command(completionProvider = "...")` |
| Completion theo từng option | Completion được tập trung ở command level, có thể xét ngữ cảnh giữa các option |
| `@ShellOption(valueProvider = ...)` và `@OptionValues` trong mô hình 3.x | Completion chuyển sang provider ở cấp command; `@OptionValues` đã bị loại bỏ |

Trong 3.x, completion cho option thường được khai báo riêng theo option bằng `ValueProvider` hoặc `CompletionResolver`. Trong 4.x, provider được gắn ở cấp command để có thể kết hợp và đưa ra gợi ý phụ thuộc nhiều option. Vì vậy, khi migration, không chỉ đổi tên `FileValueProvider` thành `FileNameCompletionProvider`; cần chuyển cách đăng ký và tổ chức provider theo command.

`DefaultCompletionProvider` xuất hiện từ 4.0.1 và cung cấp gợi ý cho enum options cùng việc tạo prefix option dựa trên ngữ cảnh. Nếu command dùng provider riêng, hãy kiểm thử cả việc gợi ý giá trị lẫn việc gợi ý tên option trong phiên bản ứng dụng.

## Bảo mật và chất lượng gợi ý

Completion có thể vô tình tiết lộ dữ liệu nếu provider trả về danh sách quá rộng. Một số nguyên tắc nên áp dụng:

- Chỉ gợi ý file hoặc thư mục trong phạm vi người dùng được phép truy cập.
- Với dữ liệu nghiệp vụ, lọc theo quyền của người dùng hiện tại trước khi tạo proposal.
- Không đưa mật khẩu, token, secret hoặc dữ liệu cá nhân nhạy cảm vào proposal.
- Không xem việc một giá trị xuất hiện trong completion là bằng chứng người dùng có quyền sử dụng nó.
- Giữ provider nhanh và tránh truy vấn không giới hạn.
- Kiểm thử đường dẫn có dấu cách, ký tự đặc biệt và đường dẫn tương đối/tuyệt đối.
- Xử lý filesystem không tồn tại hoặc không truy cập được bằng cách trả danh sách rỗng hoặc lỗi phù hợp, không làm hỏng vòng lặp shell.

Đặc biệt, `FileNameCompletionProvider` gợi ý dựa trên filesystem mà tiến trình nhìn thấy. Trong môi trường server hoặc container, hãy cân nhắc xem việc liệt kê tên file có tiết lộ cấu trúc thư mục hoặc tên dữ liệu nội bộ hay không.

## Kiểm thử completion provider

Nên kiểm thử provider độc lập và sau đó kiểm thử qua shell tương tác.

| Trường hợp | Điều cần xác minh |
| --- | --- |
| File provider với đường dẫn tương đối | Gợi ý dựa trên working directory dự kiến |
| File provider với đường dẫn tuyệt đối | Đề xuất đường dẫn phù hợp |
| File không tồn tại hoặc thư mục không truy cập được | Không làm hỏng shell; kết quả xử lý theo chính sách |
| Enum provider | Tạo proposal cho tất cả giá trị enum mong đợi |
| Enum provider có prefix | Giá trị proposal có prefix đúng option |
| Composite provider | Kết quả từ các provider thành phần được kết hợp |
| Provider định tuyến theo option | File không xuất hiện khi đang hoàn thành enum và ngược lại |
| Proposal metadata | `value`, `displayText`, `description`, `category` đúng |
| Quote | Giá trị có khoảng trắng được chèn và quote đúng |
| Bean registration | Tên provider trên `@Command` khớp bean thực tế |
| Tích hợp JLine | Nhấn Tab trong shell tạo đúng gợi ý và chọn được proposal |

Ví dụ kiểm thử enum provider:

```java
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.shell.core.command.completion.CompletionContext;
import org.springframework.shell.core.command.completion.CompletionProposal;
import org.springframework.shell.core.command.completion.CompletionProvider;
import org.springframework.shell.core.command.completion.EnumCompletionProvider;

import static org.assertj.core.api.Assertions.assertThat;

@Test
void enumProviderOffersEveryReportFormat() {
    CompletionProvider provider =
            new EnumCompletionProvider(ReportFormat.class);

    CompletionContext context = new CompletionContext(
            List.of("--format"), 0, 0, null, null);

    List<CompletionProposal> proposals = provider.apply(context);

    assertThat(proposals)
            .extracting(CompletionProposal::value)
            .contains("CSV", "JSON", "XML");
}
```

Constructor của `CompletionContext` nhận danh sách từ, chỉ số từ, vị trí con trỏ, command và option. Trong unit test provider, có thể tạo context phù hợp với trường hợp đang kiểm tra. Với `FileNameCompletionProvider`, nên dùng thư mục thử nghiệm riêng có một vài file và thư mục mẫu để kết quả kiểm thử ổn định.

## Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Dùng `FileValueProvider` trong 4.x | API legacy không còn | Dùng `FileNameCompletionProvider` |
| Dùng `EnumValueProvider` trong 4.x | API legacy không còn | Dùng `EnumCompletionProvider` |
| Gắn provider vào từng `@Option` theo cách cũ | Không đúng mô hình completion command-level của 4.x | Đăng ký bean và tham chiếu qua `@Command(completionProvider = ...)` |
| Quên đăng ký provider thành bean | Spring Shell không tìm thấy tên provider | Tạo bean và kiểm tra tên tham chiếu |
| Composite không phân biệt option hiện tại | Gợi ý từ nhiều nguồn xuất hiện lẫn nhau | Dùng `CompletionContext` để định tuyến provider |
| Gợi ý dữ liệu quá lớn | Nhấn Tab bị chậm và khó chọn | Lọc theo prefix, giới hạn số kết quả |
| Gợi ý dữ liệu không theo quyền | Có thể làm lộ tên file hoặc tài nguyên | Lọc theo quyền trước khi tạo proposal |
| Tin rằng completion thay validation | Người dùng vẫn có thể nhập giá trị khác | Xác thực lại trong command/application service |
| Dùng `dontQuote(true)` tùy tiện | Giá trị có khoảng trắng có thể bị tách token | Chỉ tắt quote khi giá trị thực sự an toàn |

## Quy trình triển khai completion cho command

1. Xác định từng option cần gợi ý: file, enum, preset hay dữ liệu động.
2. Dùng `FileNameCompletionProvider` cho đường dẫn file cục bộ và `EnumCompletionProvider` cho enum.
3. Tạo provider bean và gắn tên bean vào `@Command(completionProvider = ...)`.
4. Nếu command cần nhiều nguồn, dùng `CompositeCompletionProvider`.
5. Kiểm tra `CompletionContext` để mỗi provider chỉ hoạt động với option phù hợp.
6. Tạo `CompletionProposal` với giá trị chèn và metadata dễ hiểu.
7. Kiểm thử provider độc lập, quyền truy cập, quoting và trải nghiệm nhấn Tab trong JLine.

Khi dùng đúng ba provider này, command có thể gợi ý đường dẫn file, giá trị enum và nhiều nguồn dữ liệu trong cùng một trải nghiệm. Việc đặt provider ở cấp command giúp Spring Shell hiểu toàn bộ ngữ cảnh nhập, còn `CompositeCompletionProvider` cho phép ghép các bộ gợi ý chuyên biệt mà vẫn giữ mỗi bộ tập trung vào một loại dữ liệu.

## Tài liệu tham khảo

- [Command Completion – Spring Shell 4.0.3](https://docs.spring.io/spring-shell/reference/commands/completion.html)
- [CompletionProvider API – Spring Shell 4.0.3](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/completion/CompletionProvider.html)
- [FileNameCompletionProvider API – Spring Shell 4.x](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/completion/FileNameCompletionProvider.html)
- [EnumCompletionProvider API – Spring Shell 4.0.3](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/completion/EnumCompletionProvider.html)
- [CompositeCompletionProvider API – Spring Shell 4.x](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/completion/CompositeCompletionProvider.html)
- [CompletionContext API – Spring Shell 4.x](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/completion/CompletionContext.html)
- [CompletionProposal API – Spring Shell 4.0.3](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/completion/CompletionProposal.html)
- [Spring Shell v4 Migration Guide](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide)

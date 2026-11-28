# Gợi ý giá trị phụ thuộc ngữ cảnh mà không thay thế validation

Trong một CLI thực tế, giá trị hợp lệ của một option có thể phụ thuộc vào option đã nhập trước đó hoặc trạng thái hiện tại của người dùng. Ví dụ, danh sách vùng triển khai phụ thuộc vào môi trường **development**, **staging** hay **production**; danh sách người nhận phụ thuộc vào dự án; nhánh Git phụ thuộc vào repository đang chọn.

Spring Shell 4.x cho phép xây dựng các gợi ý như vậy bằng **CompletionProvider** ở cấp command. Provider nhận **CompletionContext**, đọc trạng thái dòng lệnh hiện tại và trả về danh sách **CompletionProposal**. Nhờ đó, gợi ý có thể thay đổi theo ngữ cảnh thay vì luôn hiển thị một danh sách cố định.

Completion chỉ giúp người dùng nhập nhanh và khám phá lựa chọn. Người dùng vẫn có thể tự gõ một giá trị không được gợi ý, gọi command từ non-interactive mode hoặc gửi lại một lệnh cũ sau khi dữ liệu đã thay đổi. Vì vậy, command và service phải kiểm tra lại dữ liệu, quyền truy cập và quy tắc nghiệp vụ khi thực thi.

Bài thực hành xây dựng command **deploy**: người dùng chọn môi trường trước, sau đó nhận danh sách region phù hợp với môi trường đó. Khi thực thi, service vẫn xác minh region có được phép triển khai trong môi trường đã chọn hay không.

## 1. Hoàn cảnh bài toán

Giả sử ứng dụng quản lý triển khai có ba môi trường:

| Môi trường | Một số region được phép |
| --- | --- |
| **DEVELOPMENT** | **local**, **ap-southeast-1** |
| **STAGING** | **ap-southeast-1**, **ap-southeast-2** |
| **PRODUCTION** | **ap-southeast-1**, **eu-west-1** |

Người dùng nhập:

```text
deploy --environment=PRODUCTION --region=<Tab>
```

Shell nên gợi ý:

```text
--region=ap-southeast-1
--region=eu-west-1
```

Nếu người dùng đổi môi trường:

```text
deploy --environment=DEVELOPMENT --region=<Tab>
```

thì gợi ý chuyển thành:

```text
--region=local
--region=ap-southeast-1
```

Provider cần biết hai điều:

1. Cursor hiện đang hoàn thành giá trị của option nào?
2. Người dùng đã nhập môi trường nào trong phần command trước đó?

Đây là ví dụ về completion phụ thuộc ngữ cảnh. Danh sách region được truy vấn từ catalog theo môi trường và người dùng hiện tại; command vẫn phải xác thực lựa chọn sau khi được gọi.

## 2. CompletionProvider trong Spring Shell 4.x

Trong Spring Shell 4.x, **CompletionProvider** là một functional interface tương đương hàm nhận **CompletionContext** và trả về **List<CompletionProposal>**:

```java
@FunctionalInterface
public interface CompletionProvider
        extends Function<CompletionContext, List<CompletionProposal>> {
}
```

Các lớp thường dùng nằm trong package **org.springframework.shell.core.command.completion**:

| Thành phần | Vai trò |
| --- | --- |
| **CompletionProvider** | Hợp đồng tạo gợi ý theo ngữ cảnh |
| **CompletionContext** | Mô tả dòng lệnh và vị trí cursor khi completion được kích hoạt |
| **CompletionProposal** | Một giá trị gợi ý cùng metadata hiển thị |
| **DefaultCompletionProvider** | Gợi ý mặc định, bao gồm giá trị enum và tiền tố option |
| **EnumCompletionProvider** | Gợi ý các giá trị của một enum |
| **FileNameCompletionProvider** | Gợi ý tên file và thư mục cục bộ |
| **CompositeCompletionProvider** | Kết hợp nhiều provider |

Completion provider tùy chỉnh được khai báo thành Spring bean, sau đó gắn với method command bằng thuộc tính **completionProvider** của **@Command**. Với command khai báo bằng API lập trình, có thể gắn provider bằng **Command.Builder.completionProvider(...)**.

Tab completion được cung cấp bởi shell dùng JLine. Nó hỗ trợ phiên tương tác; một command chạy non-interactive hoặc từ script không tự dừng để người dùng nhấn Tab.

## 3. Đọc CompletionContext

**CompletionContext** cung cấp thông tin cần thiết để quyết định gợi ý:

| Phương thức | Ý nghĩa |
| --- | --- |
| **getWords()** | Các từ trong buffer, không bao gồm tên command |
| **getWordIndex()** | Chỉ số từ mà cursor đang đứng |
| **getPosition()** | Vị trí cursor bên trong từ hiện tại |
| **currentWord()** | Toàn bộ từ tại vị trí cursor; có thể là null nếu cursor ở sau từ cuối |
| **currentWordUpToCursor()** | Phần từ hiện tại nằm trước cursor |
| **upToCursor()** | Nội dung buffer tính đến cursor |
| **getCommand()** | Command đang được hoàn thành, nếu đã xác định |
| **getCommandOption()** | Option đang được hoàn thành, nếu có |

**getCommandOption()** rất hữu ích khi một provider phục vụ nhiều option. Provider có thể kiểm tra **isOptionEqual("region")** để chỉ tạo gợi ý khi người dùng đang hoàn thành region.

Ví dụ, với dòng:

```text
deploy --environment=PRODUCTION --region=ap
```

context chứa các từ đã nhập và option hiện tại. Provider có thể đọc **--environment=PRODUCTION** từ **getWords()**, nhận biết option hiện tại là **region**, rồi tạo các đề xuất region tương ứng.

Không nên giả định cursor luôn nằm ở cuối dòng. Người dùng có thể di chuyển cursor vào giữa một từ để sửa lệnh. Khi logic cần phần văn bản đang nhập, dùng **currentWordUpToCursor()** hoặc **upToCursor()** thay vì luôn đọc toàn bộ chuỗi và coi nó là phần đã hoàn chỉnh.

## 4. Định nghĩa model và command

Trước tiên, khai báo kiểu môi trường:

```java
public enum Environment {
    DEVELOPMENT,
    STAGING,
    PRODUCTION
}
```

Command nhận môi trường, region và artifact:

```java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
public class DeploymentCommands {

    private final DeploymentService deploymentService;

    public DeploymentCommands(DeploymentService deploymentService) {
        this.deploymentService = deploymentService;
    }

    @Command(
            name = "deploy",
            description = "Triển khai artifact lên một môi trường",
            completionProvider = "deployCompletionProvider"
    )
    public String deploy(
            @Option(longName = "environment", required = true)
            @NotNull Environment environment,
            @Option(longName = "region", required = true)
            @NotBlank String region,
            @Option(longName = "artifact", required = true)
            @NotBlank String artifact) {

        deploymentService.deploy(environment, region, artifact);
        return "Đã gửi yêu cầu triển khai " + artifact
                + " lên " + environment + " tại " + region;
    }
}
```

Các annotation Bean Validation kiểm tra những điều kiện cơ bản trước khi method command chạy:

- **required = true** yêu cầu người dùng cung cấp option.
- **@NotNull** yêu cầu môi trường có giá trị.
- **@NotBlank** từ chối region hoặc artifact rỗng/toàn khoảng trắng.
- Kiểu **Environment** yêu cầu giá trị chuyển đổi được thành một enum hợp lệ.

Đảm bảo dự án có implementation của Jakarta Bean Validation, thường được cung cấp qua **spring-boot-starter-validation**. Các constraint chỉ kiểm tra những gì chúng mô tả; chúng chưa xác minh region có được phép dùng cho môi trường hoặc tài khoản hiện tại.

## 5. Tạo provider gợi ý region theo environment

Giả sử ứng dụng có một catalog cung cấp các region mà người dùng hiện tại được phép chọn:

```java
public record RegionSuggestion(String code, String description) {
}

public interface RegionCatalog {

    List<RegionSuggestion> findAllowedForCurrentUser(Environment environment);
}
```

Provider dùng **CompletionContext** để xác định option đang được hoàn thành, lấy môi trường từ các từ đã nhập và truy vấn catalog:

```java
import java.util.List;
import java.util.Locale;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.core.command.CommandOption;
import org.springframework.shell.core.command.completion.CompletionContext;
import org.springframework.shell.core.command.completion.CompletionProposal;
import org.springframework.shell.core.command.completion.CompletionProvider;
import org.springframework.shell.core.command.completion.CompositeCompletionProvider;
import org.springframework.shell.core.command.completion.DefaultCompletionProvider;

@Configuration
public class DeploymentCompletionConfiguration {

    @Bean
    CompletionProvider deployCompletionProvider(RegionCatalog regionCatalog) {
        CompletionProvider regionProvider = context -> {
            CommandOption currentOption = context.getCommandOption();

            if (currentOption == null
                    || !currentOption.isOptionEqual("region")) {
                return List.of();
            }

            Environment environment = parseEnvironment(
                    optionValue(context.getWords(), "environment"));

            if (environment == null) {
                return List.of();
            }

            return regionCatalog.findAllowedForCurrentUser(environment)
                    .stream()
                    .map(region -> new CompletionProposal(
                            "--region=" + region.code())
                            .displayText(region.code())
                            .description(region.description())
                            .category("Region"))
                    .toList();
        };

        return new CompositeCompletionProvider(
                new DefaultCompletionProvider(),
                regionProvider
        );
    }

    private static Environment parseEnvironment(String value) {
        if (value == null || value.isBlank()) {
            return null;
        }
        try {
            return Environment.valueOf(
                    value.trim().toUpperCase(Locale.ROOT));
        }
        catch (IllegalArgumentException ex) {
            return null;
        }
    }

    private static String optionValue(
            List<String> words,
            String longName) {

        String option = "--" + longName;
        String prefix = option + "=";

        for (int i = 0; i < words.size(); i++) {
            String word = words.get(i);

            if (word.startsWith(prefix)) {
                return word.substring(prefix.length());
            }

            if (word.equals(option) && i + 1 < words.size()) {
                return words.get(i + 1);
            }
        }

        return null;
    }
}
```

Có ba điểm quan trọng trong provider:

1. **Kiểm tra option hiện tại.** Provider chỉ trả region khi **getCommandOption()** là option **region**. Khi người dùng hoàn thành tên option hoặc một option khác, provider trả danh sách rỗng.
2. **Đọc ngữ cảnh đã nhập.** Hàm **optionValue(...)** hỗ trợ cả hai cách viết **--environment=PRODUCTION** và **--environment PRODUCTION**.
3. **Lọc theo ngữ cảnh và người dùng.** Catalog chỉ trả những region được phép gợi ý cho môi trường và người dùng hiện tại.

**DefaultCompletionProvider** được kết hợp để giữ các gợi ý mặc định như tên option và giá trị enum. **CompositeCompletionProvider** gọi nhiều provider và kết hợp kết quả của chúng. Nếu muốn tự điều khiển toàn bộ gợi ý, có thể bỏ provider mặc định và cung cấp danh sách phù hợp với command.

**CompletionProposal** nhận giá trị sẽ được chèn vào dòng lệnh. Các thuộc tính **displayText**, **description** và **category** giúp hiển thị gợi ý dễ hiểu hơn. Trong ví dụ, giá trị chèn là **--region=ap-southeast-1**, còn nội dung hiển thị là mã region.

## 6. Quan sát hành vi khi dùng Tab

Sau khi đăng ký command và provider, người dùng có thể thử:

```text
shell:>deploy --environment=DEVELOPMENT --region=<Tab>
```

Shell đưa ra các region mà catalog cho phép trong môi trường development. Nếu người dùng nhập:

```text
shell:>deploy --environment=PRODUCTION --region=<Tab>
```

provider trả các region thuộc môi trường production.

Khi chưa nhập environment:

```text
shell:>deploy --region=<Tab>
```

provider trả danh sách rỗng vì chưa đủ ngữ cảnh để chọn region. Người dùng cần nhập environment trước.

Nếu người dùng nhập một environment không hợp lệ hoặc một region đã bị thu hồi quyền truy cập, provider cũng có thể trả danh sách rỗng. Đây là hành vi an toàn: không đoán môi trường và không đưa ra những lựa chọn mà catalog không xác nhận.

Completion là trợ giúp khi soạn lệnh. Nó không thay đổi cú pháp command và không tự điền các option bắt buộc còn thiếu.

## 7. Tách gợi ý khỏi validation nghiệp vụ

Đây là nguyên tắc quan trọng nhất của bài thực hành:

**Completion trả lời câu hỏi “Người dùng có thể muốn chọn giá trị nào?”. Validation trả lời câu hỏi “Giá trị được gửi có thực sự hợp lệ và được phép thực hiện không?”.**

Hai câu hỏi này có mục đích và thời điểm khác nhau:

| Completion | Validation |
| --- | --- |
| Chạy khi người dùng yêu cầu gợi ý, thường bằng Tab | Chạy khi command được thực thi |
| Có thể chỉ trả một danh sách rút gọn | Phải kiểm tra giá trị thực tế được gửi |
| Có thể dựa trên cache hoặc dữ liệu gần nhất | Phải dựa trên quy tắc và trạng thái hiện hành |
| Không ngăn người dùng tự gõ giá trị khác | Có quyền từ chối giá trị không hợp lệ |
| Hỗ trợ khám phá và nhập nhanh | Bảo vệ tính đúng đắn và quyền truy cập |

Ví dụ, provider có thể gợi ý **ap-southeast-1** cho production. Nhưng giữa thời điểm người dùng nhấn Tab và lúc command được thực thi, quyền truy cập hoặc chính sách triển khai có thể thay đổi. Service phải kiểm tra lại:

```java
import org.springframework.stereotype.Service;

@Service
public class DeploymentService {

    private final DeploymentPolicy deploymentPolicy;
    private final DeploymentExecutor deploymentExecutor;
    private final CurrentUser currentUser;

    public DeploymentService(
            DeploymentPolicy deploymentPolicy,
            DeploymentExecutor deploymentExecutor,
            CurrentUser currentUser) {
        this.deploymentPolicy = deploymentPolicy;
        this.deploymentExecutor = deploymentExecutor;
        this.currentUser = currentUser;
    }

    public void deploy(
            Environment environment,
            String region,
            String artifact) {

        deploymentPolicy.requireAllowed(
                currentUser.id(),
                environment,
                region
        );

        deploymentExecutor.deploy(environment, region, artifact);
    }
}
```

**DeploymentPolicy.requireAllowed(...)** phải xác minh lại các điều kiện nghiệp vụ:

- Region tồn tại.
- Region được hỗ trợ trong environment đã chọn.
- Người dùng hiện tại có quyền triển khai tới region đó.
- Môi trường đang mở cho hoạt động triển khai.
- Artifact tồn tại và đáp ứng chính sách phát hành.

Không dùng kết quả của CompletionProvider làm bằng chứng rằng command được phép chạy. Không truyền danh sách gợi ý vào service để service bỏ qua bước kiểm tra quyền hoặc trạng thái hiện tại.

## 8. Những loại kiểm tra nên đặt ở từng lớp

Một command có thể dùng nhiều lớp kiểm tra bổ sung nhau:

| Lớp | Ví dụ | Thời điểm |
| --- | --- | --- |
| Parser/converter | **PRODUCTION** chuyển thành enum **Environment** | Khi phân tích command |
| Bean Validation | **@NotNull**, **@NotBlank**, **@Size**, **@Pattern** | Trước khi method command chạy |
| Domain validation | Region thuộc environment và artifact hợp lệ | Trong service nghiệp vụ |
| Authorization | Người dùng được phép triển khai vào region | Khi thực thi nghiệp vụ |
| State validation | Environment chưa bị khóa hoặc đóng băng | Ngay trước side effect |

Ví dụ, **@NotBlank** có thể từ chối chuỗi rỗng nhưng không thể tự biết region có thuộc environment đã chọn hay không. Một constraint đơn giản trên tham số cũng không thay thế được kiểm tra quyền truy cập dựa trên người dùng hiện tại.

Nếu dùng custom Bean Validation constraint để kiểm tra quan hệ giữa nhiều trường, vẫn cần bảo vệ ở service khi có side effect quan trọng. Validation ở command boundary cải thiện thông báo lỗi; service boundary bảo vệ nghiệp vụ kể cả khi được gọi từ một luồng khác.

## 9. Kết hợp các provider có sẵn

Không phải mọi danh sách đều cần provider tùy chỉnh:

| Loại dữ liệu | Provider phù hợp | Ví dụ |
| --- | --- | --- |
| Enum cố định | **EnumCompletionProvider** | Environment, status, log level |
| Đường dẫn file | **FileNameCompletionProvider** | File cấu hình, file script |
| Gợi ý mặc định và enum option | **DefaultCompletionProvider** | Option name, enum value |
| Nhiều nguồn gợi ý | **CompositeCompletionProvider** | Enum kết hợp danh sách động |
| Dữ liệu phụ thuộc option trước | Custom **CompletionProvider** | Region theo environment, user theo project |

Ví dụ gợi ý enum độc lập:

```java
@Bean
CompletionProvider environmentCompletionProvider() {
    return new EnumCompletionProvider(
            Environment.class,
            "--environment"
    );
}
```

Ví dụ gợi ý tên file:

```java
@Bean
CompletionProvider configFileCompletionProvider() {
    return new FileNameCompletionProvider();
}
```

Nếu command cần nhiều loại gợi ý, kết hợp chúng:

```java
return new CompositeCompletionProvider(
        new EnumCompletionProvider(Environment.class, "--environment"),
        regionCompletionProvider,
        artifactCompletionProvider
);
```

Mỗi provider nên chịu trách nhiệm cho một nhóm giá trị rõ ràng. Kiểm tra **getCommandOption()** để tránh provider gợi ý nhầm option.

## 10. Gợi ý dữ liệu động từ database hoặc service

Trong thực tế, dữ liệu có thể đến từ database hoặc API nội bộ:

- Project theo workspace hiện tại.
- User được phép gán vào một project.
- Artifact đã được build và lưu trong registry.
- Region được bật cho tenant.
- Branch tồn tại trong repository đang chọn.

Một provider có thể inject service Spring như các bean khác:

```java
@Bean
CompletionProvider projectCompletionProvider(ProjectCatalog projectCatalog) {
    return context -> {
        CommandOption option = context.getCommandOption();
        if (option == null || !option.isOptionEqual("project")) {
            return List.of();
        }

        return projectCatalog.findVisibleToCurrentUser()
                .stream()
                .map(project -> new CompletionProposal(
                        "--project=" + project.id())
                        .displayText(project.name())
                        .description(project.id())
                        .category("Project"))
                .toList();
    };
}
```

Trong ứng dụng nhiều tenant, **findVisibleToCurrentUser()** cần giới hạn dữ liệu theo principal và tenant hiện tại. Không trả toàn bộ tên project, username hoặc tài nguyên nhạy cảm cho mọi người dùng chỉ vì completion được gọi.

### Hiệu năng của provider

Completion có thể được gọi nhiều lần trong lúc người dùng gõ và di chuyển cursor. Một lần nhấn Tab không nên gây ra nhiều truy vấn chậm hoặc một chuỗi request tới dịch vụ bên ngoài.

Nên áp dụng:

- Chỉ truy vấn khi cursor đang ở đúng option cần gợi ý.
- Dùng prefix hiện tại để giới hạn số kết quả khi danh sách lớn.
- Giới hạn số proposal trả về, sắp xếp kết quả theo mức liên quan.
- Cache danh mục ít thay đổi với thời hạn phù hợp.
- Đặt timeout cho truy vấn dữ liệu từ xa.
- Trả danh sách rỗng hoặc fallback rõ ràng nếu nguồn gợi ý tạm thời không khả dụng.
- Không log dữ liệu nhạy cảm hoặc toàn bộ buffer command.

Cache chỉ phục vụ gợi ý. Khi command thực thi, service vẫn kiểm tra lại trạng thái mới nhất.

## 11. Xử lý prefix và giá trị đang nhập

Completion provider có thể nhận một từ chưa hoàn chỉnh. Ví dụ:

```text
deploy --environment=PRODUCTION --region=ap
```

Người dùng mong muốn các kết quả bắt đầu bằng **ap**. Có hai cách:

1. Trả toàn bộ region hợp lệ và để completion engine lọc theo phần từ hiện tại.
2. Đọc **currentWordUpToCursor()** rồi lọc danh sách ngay trong provider.

Với danh sách nhỏ, cách thứ nhất đơn giản. Với danh sách lớn, lọc theo prefix trong service hoặc catalog sẽ giảm số proposal.

Nếu tự lọc, cần xác định phần prefix đúng với cú pháp command đang dùng. Ví dụ, khi cursor đang ở **--region=ap**, phần cần lọc là **ap**, còn phần **--region=** là tiền tố cú pháp. Không so sánh toàn bộ token với mã region.

Khi người dùng đặt cursor giữa từ, dùng phần trước cursor để tạo gợi ý. Tránh cắt chuỗi bằng một vị trí cố định vì giá trị có thể có độ dài khác nhau hoặc option có thể được viết ở dạng **--region ap**.

## 12. Kiểm thử completion và validation

Nên kiểm thử provider và service độc lập:

### Kiểm thử provider

- Đang hoàn thành **region** và đã nhập **DEVELOPMENT**: chỉ trả region thuộc development.
- Đang hoàn thành **region** và đã nhập **PRODUCTION**: chỉ trả region thuộc production.
- Chưa có environment: trả danh sách rỗng.
- Environment không hợp lệ: không ném lỗi không cần thiết; trả danh sách rỗng.
- Đang hoàn thành **environment**: provider region không trả gợi ý region.
- Đang hoàn thành option khác: provider region không can thiệp.
- Người dùng khác nhau: catalog chỉ trả dữ liệu mà người đó được phép xem.
- Prefix hiện tại: kết quả phù hợp với phần người dùng đã gõ.

### Kiểm thử validation

- Region hợp lệ với environment được chọn: command được phép đi tiếp.
- Region tồn tại nhưng không thuộc environment: service từ chối.
- Region thuộc environment nhưng người dùng không có quyền: service từ chối.
- Region từng được gợi ý nhưng đã bị thu hồi quyền trước khi thực thi: service từ chối.
- Người dùng tự gõ region không nằm trong danh sách gợi ý: service vẫn kiểm tra và từ chối nếu không hợp lệ.
- Environment hoặc artifact thiếu/không hợp lệ: Bean Validation từ chối trước khi command chạy.

### Kiểm thử command

Dùng **@ShellTest** và **ShellTestClient** để kiểm tra command được parse và thực thi:

```java
@ShellTest
@ContextConfiguration(classes = DeploymentApplication.class)
class DeploymentCommandTests {

    @Autowired
    ShellTestClient client;

    @Test
    void rejectsRegionNotAllowedForEnvironment() {
        assertThatThrownBy(() -> client.sendCommand(
                "deploy --environment=DEVELOPMENT "
                        + "--region=eu-west-1 --artifact=portal:1.0"))
                .hasMessageContaining("region");
    }
}
```

Thông điệp và loại exception chính xác phụ thuộc exception mapping của ứng dụng. Test cần xác nhận command không gọi **DeploymentExecutor** khi policy từ chối. Có thể mock service hoặc dùng fake policy để kiểm tra side effect không xảy ra.

**ShellTestClient** kiểm tra đường đi thực thi command, không thay thế kiểm thử tương tác Tab trên JLine. Với provider, nên có unit test gọi provider bằng các **CompletionContext** đại diện và một integration test chạy shell JLine trong môi trường hỗ trợ terminal.

## 13. Khác biệt với Spring Shell 3.x

Spring Shell 3.x thường khai báo completion cho từng option thông qua **ValueProvider** và **@ShellOption(valueProvider = ...)**. Cách đó phù hợp với danh sách tĩnh nhưng khó tạo gợi ý phụ thuộc chéo vào nhiều option trong cùng command.

Spring Shell 4 chuyển sang completion tập trung ở cấp command:

| Spring Shell 3.x | Spring Shell 4.x |
| --- | --- |
| **ValueProvider** | **CompletionProvider** |
| **@ShellOption(valueProvider = ...)** | **@Command(completionProvider = "beanName")** |
| Gợi ý gắn riêng vào option | Provider nhận toàn bộ **CompletionContext** của command |
| **@OptionValues** | Đã bị loại bỏ |
| Nhiều provider theo từng option | Có thể kết hợp bằng **CompositeCompletionProvider** |

Migration guide 4.x nêu rõ completion được tập trung ở cấp command để giải quyết giới hạn của mô hình cũ: provider riêng cho từng option không có đủ khả năng phối hợp thông tin giữa các option.

Khi nâng cấp, không nên chỉ đổi tên **ValueProvider** thành **CompletionProvider**. Hãy chuyển logic sang một provider nhận toàn bộ context, kiểm tra option hiện tại và đọc các từ đã nhập để xây dựng gợi ý phù hợp.

## 14. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Không thấy gợi ý khi nhấn Tab | Đang dùng runner không có JLine completion | Kiểm tra JLine shell/runner |
| Provider luôn trả danh sách rỗng | **getCommandOption()** không phải option mà provider xử lý | Kiểm tra tên option và **isOptionEqual(...)** |
| Region không đổi khi đổi environment | Provider đọc nhầm token hoặc chỉ dùng danh sách cache chung | Đọc lại **getWords()** và lọc theo environment |
| Gợi ý chỉ hoạt động với **--env=value** | Helper chỉ xử lý dạng option có dấu bằng | Hỗ trợ cả **--env value** |
| Gợi ý chứa tài nguyên người dùng khác | Catalog không lọc theo principal/tenant | Lọc ở service truy vấn gợi ý |
| Command vẫn nhận giá trị không nằm trong gợi ý | Completion không phải validation | Kiểm tra lại ở Bean Validation và service |
| Người dùng chọn gợi ý cũ nhưng command thất bại | Trạng thái đã thay đổi sau khi completion | Xác thực lại ngay trước side effect |
| Tab completion chậm | Truy vấn remote hoặc database mỗi lần nhấn Tab | Giới hạn truy vấn, cache và timeout |
| Provider gợi ý sai option | Không kiểm tra **getCommandOption()** | Chỉ trả proposal cho option phù hợp |
| Unit test pass nhưng Tab không hoạt động | Chưa kiểm tra với JLine terminal thực tế | Bổ sung integration/smoke test interactive |

## 15. Checklist triển khai

- Xác định option nào cần gợi ý phụ thuộc vào option khác.
- Dùng **CompletionContext.getCommandOption()** để nhận biết option hiện tại.
- Dùng **getWords()** hoặc phần buffer trước cursor để đọc ngữ cảnh đã nhập.
- Khai báo provider thành Spring bean.
- Gắn provider vào **@Command(completionProvider = "...")**.
- Dùng **DefaultCompletionProvider**, **EnumCompletionProvider** hoặc **FileNameCompletionProvider** cho nhu cầu phổ biến.
- Kết hợp nhiều provider bằng **CompositeCompletionProvider**.
- Tạo **CompletionProposal** với value, display text và description phù hợp.
- Lọc gợi ý theo người dùng và tenant hiện tại.
- Giới hạn độ trễ, số lượng kết quả và truy vấn từ xa.
- Dùng Bean Validation cho ràng buộc cơ bản của tham số.
- Kiểm tra domain rule và authorization trong service khi command thực thi.
- Không coi giá trị đã được gợi ý là giá trị đã được xác thực.
- Kiểm thử provider, command và policy ở các tầng riêng.
- Kiểm tra Tab completion trên JLine interactive shell.

## 16. Bài tập thực hành

Mở rộng command **deploy** để gợi ý artifact theo environment và project:

1. Thêm option **--project**.
2. Khi người dùng nhập project, chỉ gợi ý artifact thuộc project đó.
3. Khi environment là production, chỉ gợi ý artifact đã được đánh dấu release-ready.
4. Hiển thị tên artifact ở **displayText** và version ở **description**.
5. Không gợi ý artifact thuộc tenant khác.
6. Khi command thực thi, kiểm tra lại artifact vẫn tồn tại, thuộc project và được phép triển khai production.
7. Viết test xác nhận artifact cũ đã bị thu hồi vẫn bị từ chối dù trước đó từng xuất hiện trong completion.

**Tiêu chí hoàn thành:** đổi project hoặc environment làm thay đổi danh sách gợi ý; người dùng có thể tự gõ giá trị ngoài danh sách nhưng service từ chối nếu vi phạm policy; không có side effect khi validation hoặc authorization thất bại.

## Tài liệu tham khảo

- [Spring Shell 4.0.3 — Command Completion](https://docs.spring.io/spring-shell/reference/commands/completion.html)
- [Spring Shell 4.0.3 — CompletionProvider API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/completion/CompletionProvider.html)
- [Spring Shell 4.0.3 — CompletionContext API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/completion/CompletionContext.html)
- [Spring Shell 4.0.3 — CompletionProposal API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/completion/CompletionProposal.html)
- [Spring Shell 4.0.3 — CommandOption API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/CommandOption.html)
- [Spring Shell 4.0.3 — Option Validation](https://docs.spring.io/spring-shell/reference/commands/validation.html)
- [Spring Shell — v4 Migration Guide](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide)

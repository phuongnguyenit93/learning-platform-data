# Phân biệt gợi ý đầu vào với kiểm tra giá trị hợp lệ

Khi người dùng nhập một command Spring Shell, phím Tab có thể đưa ra danh sách giá trị để họ chọn. Ví dụ, khi nhập `deploy --environment st`, shell có thể gợi ý `staging`. Tuy nhiên, một giá trị xuất hiện trong danh sách gợi ý chưa chắc còn hợp lệ khi command được thực thi; ngược lại, người dùng cũng có thể tự nhập một giá trị không xuất hiện trong danh sách.

Đây là hai trách nhiệm khác nhau: **autocompletion giúp người dùng khám phá và nhập giá trị nhanh hơn**, còn **validation quyết định dữ liệu có được chấp nhận hay không**. Một ứng dụng CLI tốt cần cả hai: gợi ý hữu ích trong lúc nhập và kiểm tra chắc chắn trước khi thay đổi dữ liệu.

## 1. Completion và validation trả lời hai câu hỏi khác nhau

Giả sử ứng dụng có command triển khai một bản phát hành:

```text
deploy --environment staging --version 2.5.0
```

Completion trả lời: “Với phần văn bản người dùng đang nhập, những giá trị nào có thể gợi ý để hoàn thành?”. Validation trả lời: “Giá trị cuối cùng người dùng gửi có thỏa mãn quy tắc của command và nghiệp vụ không?”.

| Cơ chế | Thời điểm | Mục tiêu | Ví dụ |
| --- | --- | --- | --- |
| Autocompletion | Khi người dùng đang gõ và nhấn Tab | Đề xuất các lựa chọn phù hợp | Gợi ý `staging`, `production` |
| Parsing | Khi shell phân tích dòng lệnh | Tách command, option và token | Nhận diện `--environment` và `staging` |
| Type conversion | Khi bind token vào tham số Java | Chuyển văn bản sang kiểu đích | Chuyển `2` thành `Integer`, `JSON` thành enum |
| Validation | Trước khi gọi command hoặc trong tầng nghiệp vụ | Từ chối giá trị vi phạm quy tắc | Tên môi trường không đúng định dạng |
| Authorization | Khi thực hiện hành động có bảo vệ | Xác nhận người gọi có quyền | Người dùng không có quyền deploy production |

Completion không khóa tập giá trị được nhập. Người dùng có thể bỏ qua gợi ý, dán văn bản từ nơi khác hoặc gọi command từ script. Do đó, tuyệt đối không dùng danh sách completion làm cơ chế bảo vệ dữ liệu hay quyền truy cập.

## 2. Autocompletion hoạt động trong Spring Shell

Trong shell tương tác dựa trên JLine, người dùng nhấn Tab để yêu cầu các gợi ý dựa trên phần command line đã nhập. Spring Shell có thể gợi ý tên command, option, giá trị enum, file và thư mục; ứng dụng cũng có thể cung cấp các gợi ý động theo dữ liệu nghiệp vụ. <Link url="https://docs.spring.io/spring-shell/reference/commands/completion.html" title="Spring Shell 4.0.3 — Command Completion"/>.

Ví dụ trải nghiệm:

```text
shell:>deploy --environment st<Tab>
staging
```

Khi danh sách có nhiều kết quả, JLine có thể hiển thị các lựa chọn để người dùng chọn hoặc tiếp tục gõ thêm tiền tố. Completion provider nhận ngữ cảnh hiện tại và trả về các proposal. Provider không thực thi command, không triển khai ứng dụng và không ghi thay đổi vào hệ thống.

Completion bằng Tab của shell tương tác cần được phân biệt với completion của shell hệ điều hành. Một ứng dụng được gọi trực tiếp như `java -jar app.jar deploy ...` trong script không có phiên nhập lệnh tương tác để nhấn Tab. Tích hợp completion cho Bash/Zsh/PowerShell là một cơ chế riêng của từng shell; không nên giả định provider Tab trong JLine tự động tạo script completion cho mọi shell hệ điều hành.

## 3. Completion proposal chứa gì?

Một gợi ý cơ bản là chuỗi sẽ được chèn vào dòng lệnh. Spring Shell biểu diễn gợi ý bằng `CompletionProposal`; ngoài giá trị, proposal có thể mang metadata giúp người dùng phân biệt các lựa chọn.

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `value` | Nội dung được chèn vào dòng lệnh |
| `displayText` | Văn bản hiển thị trong danh sách gợi ý |
| `description` | Mô tả ngắn về lựa chọn |
| `category` | Nhóm của lựa chọn |
| `complete` | Cờ trạng thái hoàn tất của proposal |
| `dontQuote` | Điều khiển việc tự thêm dấu nháy cho giá trị |

Không cần điền mọi thuộc tính cho mọi gợi ý. Với tên môi trường, `value` có thể là `staging`, còn `description` là `Môi trường kiểm thử trước khi phát hành`. Với file path chứa dấu cách, cách quote giá trị cần phù hợp với parser và quy tắc escaping của shell.

## 4. Gợi ý tĩnh và gợi ý động

Gợi ý tĩnh phù hợp khi tập giá trị ít thay đổi và đã biết tại thời điểm biên dịch, ví dụ enum định dạng output:

```java
public enum OutputFormat {
    TABLE,
    JSON,
    YAML
}
```

Spring Shell 4 có `EnumCompletionProvider` để gợi ý các hằng enum. `FileNameCompletionProvider` gợi ý file và thư mục theo thư mục làm việc hiện tại; `CompositeCompletionProvider` kết hợp nhiều provider. `DefaultCompletionProvider` xử lý gợi ý mặc định cho option enum và prefix của option. <Link url="https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/completion/EnumCompletionProvider.html" title="EnumCompletionProvider API"/>.

Gợi ý động phù hợp khi dữ liệu đến từ cấu hình, project catalog, danh sách môi trường hoặc tài nguyên mà người dùng hiện tại được phép truy cập. Ví dụ, môi trường có thể được tạo hoặc ngừng hoạt động trong lúc ứng dụng đang chạy; vì vậy danh sách nên được lấy từ một service thay vì hard-code.

## 5. Tạo `CompletionProvider` trong Spring Shell 4.x

Trong Spring Shell 4, `CompletionProvider` là functional interface nhận `CompletionContext` và trả về `List<CompletionProposal>`. Có thể đăng ký provider thành Spring bean rồi tham chiếu tên bean từ thuộc tính `completionProvider` của `@Command`.

Giả sử ứng dụng có service cung cấp danh sách môi trường đang hoạt động:

```java
import java.util.List;

public interface EnvironmentCatalog {

    List<String> activeEnvironmentNames();

    boolean isActive(String environment);
}
```

Provider lọc các môi trường theo tiền tố người dùng đang nhập:

```java
import java.util.List;
import java.util.Optional;
import org.springframework.shell.core.command.completion.CompletionContext;
import org.springframework.shell.core.command.completion.CompletionProposal;
import org.springframework.shell.core.command.completion.CompletionProvider;
import org.springframework.stereotype.Component;

@Component("environmentCompletion")
public class EnvironmentCompletionProvider implements CompletionProvider {

    private final EnvironmentCatalog catalog;

    public EnvironmentCompletionProvider(EnvironmentCatalog catalog) {
        this.catalog = catalog;
    }

    @Override
    public List<CompletionProposal> apply(CompletionContext context) {
        String prefix = Optional.ofNullable(context.currentWordUpToCursor())
                .orElse("");
        int equalsIndex = prefix.lastIndexOf('=');
        if (equalsIndex >= 0) {
            prefix = prefix.substring(equalsIndex + 1);
        }

        return catalog.activeEnvironmentNames().stream()
                .filter(name -> name.regionMatches(
                        true, 0, prefix, 0, prefix.length()))
                .sorted()
                .map(name -> new CompletionProposal(name)
                        .description("Môi trường đang hoạt động"))
                .toList();
    }
}
```

Trong một command thực tế có nhiều option, provider nên xem thêm `context.getCommandOption()` để biết option nào đang được hoàn thành và chọn danh sách gợi ý tương ứng. Ví dụ, `--environment` cần tên môi trường, còn `--region` cần mã vùng. Nếu dùng một provider chung ở cấp command, phải phân biệt hai ngữ cảnh đó để không đưa gợi ý sai cho option.

Gắn provider vào command:

```java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
public class DeploymentCommands {

    private final DeploymentService deploymentService;

    public DeploymentCommands(DeploymentService deploymentService) {
        this.deploymentService = deploymentService;
    }

    @Command(name = "deploy", completionProvider = "environmentCompletion")
    public String deploy(
            @Option(longName = "environment")
            @NotBlank
            @Pattern(regexp = "[a-z][a-z0-9-]*") String environment) {

        deploymentService.deploy(environment);
        return "Đã gửi yêu cầu triển khai tới " + environment;
    }
}
```

`@Command` trỏ tới bean completion ở cấp command. Khi command có nhiều tham số cần gợi ý khác nhau, provider cần xét ngữ cảnh hiện tại để chỉ trả về proposal phù hợp. Các annotation validation ở ví dụ là lớp kiểm tra định dạng; `DeploymentService` vẫn phải kiểm tra môi trường còn hoạt động và người gọi có quyền triển khai.

## 6. Completion trong Spring Shell 3.x

Spring Shell 3.x có các cách cấu hình completion tùy mô hình đăng ký command.

**Programmatic registration** cho phép cấu hình completion ngay trên option:

```java
import java.util.List;
import org.springframework.shell.command.CommandRegistration;
import org.springframework.shell.CompletionProposal;
// EnvironmentCatalog và DeploymentService là các kiểu nghiệp vụ của ứng dụng.

CommandRegistration.builder()
        .command("deploy")
        .withOption()
            .longNames("environment")
            .completion(context -> catalog.activeEnvironmentNames().stream()
                    .map(CompletionProposal::new)
                    .toList())
            .and()
        .withTarget()
            .function(context -> {
                String environment = context.getOptionValue("environment");
                deploymentService.deploy(environment);
                return "Đã gửi yêu cầu triển khai tới " + environment;
            })
            .and()
        .build();
```

**Legacy annotation model** sử dụng `ValueProvider` cùng `@ShellOption(valueProvider = ...)`:

```java
import java.util.List;
import org.springframework.shell.CompletionContext;
import org.springframework.shell.CompletionProposal;
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;
import org.springframework.shell.standard.ShellOption;
import org.springframework.shell.standard.ValueProvider;
import org.springframework.stereotype.Component;

@Component
public class EnvironmentValueProvider implements ValueProvider {

    private final EnvironmentCatalog catalog;

    public EnvironmentValueProvider(EnvironmentCatalog catalog) {
        this.catalog = catalog;
    }

    @Override
    public List<CompletionProposal> complete(CompletionContext context) {
        return catalog.activeEnvironmentNames().stream()
                .map(CompletionProposal::new)
                .toList();
    }
}
```

Command legacy tham chiếu provider theo class:

```java
@ShellComponent
public class LegacyDeploymentCommands {

    private final DeploymentService deploymentService;

    public LegacyDeploymentCommands(DeploymentService deploymentService) {
        this.deploymentService = deploymentService;
    }

    @ShellMethod("Triển khai tới môi trường")
    public String deploy(
            @ShellOption(value = "--environment",
                    valueProvider = EnvironmentValueProvider.class)
            String environment) {
        deploymentService.deploy(environment);
        return "Đã gửi yêu cầu triển khai tới " + environment;
    }
}
```

**Annotation model mới** của 3.x có `@OptionValues` để tham chiếu bean `CompletionProvider` theo tên:

```java
import org.springframework.shell.command.annotation.Command;
import org.springframework.shell.command.annotation.Option;
import org.springframework.shell.command.annotation.OptionValues;
import org.springframework.stereotype.Component;

@Component
public class AnnotationDeploymentCommands {

    private final DeploymentService deploymentService;

    public AnnotationDeploymentCommands(DeploymentService deploymentService) {
        this.deploymentService = deploymentService;
    }

    @Command(command = "deploy")
    public String deploy(
            @Option(longNames = "environment")
            @OptionValues(provider = "environmentCompletion") String environment) {
        deploymentService.deploy(environment);
        return "Đã gửi yêu cầu triển khai tới " + environment;
    }
}
```

Bean cung cấp completion được khai báo trong lớp cấu hình:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.CompletionProposal;
import org.springframework.shell.completion.CompletionProvider;

@Configuration
public class CompletionConfiguration {

@Bean
CompletionProvider environmentCompletion(EnvironmentCatalog catalog) {
    return context -> catalog.activeEnvironmentNames().stream()
            .map(CompletionProposal::new)
            .toList();
}
}
```

Spring Shell 3.x cũng có `CompletionResolver` để đăng ký resolver dùng chung. Cần chọn API theo đúng model command đang dùng; không trộn `ValueProvider` của legacy model với annotation hoặc package của Spring Shell 4. <Link url="https://docs.spring.io/spring-shell/reference/completion.html" title="Spring Shell 3.4.1 — Completion"/>.

## 7. Completion không phải validation

Giả sử provider gợi ý ba môi trường:

```text
development
staging
production
```

Danh sách đó chỉ là những giá trị được đề xuất tại thời điểm người dùng nhấn Tab. Người dùng vẫn có thể nhập:

```text
deploy --environment preproduction
```

Nếu `preproduction` không hợp lệ, command phải từ chối khi validation hoặc service kiểm tra. Không được giả định rằng vì người dùng không chọn từ danh sách completion nên parser sẽ tự động chặn giá trị đó.

Các lý do khiến completion không thể bảo đảm tính hợp lệ:

- Người dùng có thể nhập hoặc dán giá trị mà không dùng Tab.
- Script và CI gọi command trực tiếp, không có thao tác completion.
- Dữ liệu có thể thay đổi sau khi provider tạo danh sách gợi ý.
- Provider có thể chỉ đưa ra một tập con để tránh danh sách quá dài.
- Completion có thể cố ý bỏ qua giá trị hiếm hoặc giá trị chỉ người dùng khác được phép thấy.

Completion nên giúp người dùng chọn nhanh; validation và nghiệp vụ phải quyết định cuối cùng.

## 8. Kiểm tra định dạng bằng Bean Validation

Spring Shell tích hợp Bean Validation để áp dụng các constraint trên tham số command trước khi gọi phương thức. Ví dụ, `@NotBlank` từ chối chuỗi rỗng hoặc chỉ có khoảng trắng; `@Pattern` giới hạn cú pháp; `@Size` giới hạn độ dài. <Link url="https://docs.spring.io/spring-shell/reference/commands/validation.html" title="Spring Shell 4.0.3 — Option Validation"/>.

Ví dụ kiểm tra tên môi trường theo định dạng:

```java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;

@Command(name = "deploy", completionProvider = "environmentCompletion")
public String deploy(
        @Option(longName = "environment")
        @NotBlank
        @Size(min = 2, max = 30)
        @Pattern(regexp = "[a-z][a-z0-9-]*") String environment) {

    deploymentService.deploy(environment);
    return "Đã gửi yêu cầu triển khai tới " + environment;
}
```

Các constraint này chỉ xác nhận hình dạng của chuỗi. Chúng không biết môi trường `staging` có đang hoạt động trong catalog hay người dùng hiện tại có được deploy tới đó hay không. Với Spring Shell, cần có implementation Bean Validation tương ứng trên classpath để constraint được thực thi.

## 9. Kiểm tra giá trị động trong service

Danh sách giá trị động thường phụ thuộc dữ liệu lưu trữ hoặc quyền hiện tại. Một môi trường được gợi ý lúc 10 giờ có thể đã bị vô hiệu hóa lúc 10 giờ 05. Vì vậy, service cần kiểm tra lại trước khi thay đổi trạng thái hệ thống.

```java
import org.springframework.stereotype.Service;

@Service
public class DeploymentService {

    private final EnvironmentCatalog catalog;
    private final DeploymentAuthorization authorization;
    private final DeploymentClient client;

    public DeploymentService(
            EnvironmentCatalog catalog,
            DeploymentAuthorization authorization,
            DeploymentClient client) {
        this.catalog = catalog;
        this.authorization = authorization;
        this.client = client;
    }

    public void deploy(String environment) {
        if (!catalog.isActive(environment)) {
            throw new IllegalArgumentException(
                    "Môi trường không tồn tại hoặc đã ngừng hoạt động: " + environment);
        }
        authorization.requireDeployPermission(environment);
        client.deploy(environment);
    }
}
```

Service kiểm tra trạng thái hiện tại và quyền truy cập ngay tại ranh giới nghiệp vụ. Nếu dữ liệu có thể thay đổi đồng thời, thao tác triển khai cũng cần xử lý lỗi phát sinh giữa lúc kiểm tra và lúc gọi hệ thống đích. Không dùng completion provider để thực hiện kiểm tra quyền thay service.

## 10. Chuyển đổi kiểu cũng là một bước riêng

Sau parsing, Spring Shell chuyển token thành kiểu tham số. Nếu option có kiểu enum, giá trị phải chuyển đổi được thành một hằng enum; nếu option có kiểu số, chuỗi phải chuyển đổi được thành số. Đây là type conversion, không phải completion.

Ví dụ:

```java
public enum OutputFormat {
    TABLE,
    JSON,
    YAML
}

@Command(name = "export")
public String export(@Option(longName = "format") OutputFormat format) {
    return "Định dạng: " + format;
}
```

`EnumCompletionProvider` có thể gợi ý `TABLE`, `JSON` và `YAML`. Converter enum sẽ từ chối một chuỗi không ánh xạ được sang hằng enum. Tuy nhiên, nếu ứng dụng chỉ cho phép `JSON` ở chế độ batch, quy tắc đó vẫn cần validation hoặc kiểm tra trong service. Một kiểu Java chuyển đổi thành công không chứng minh giá trị phù hợp với trạng thái nghiệp vụ.

## 11. Thiết kế completion hữu ích và an toàn

Một provider tốt nên:

- Lọc theo phần tiền tố đang nhập, không trả toàn bộ catalog lớn.
- Chỉ gợi ý giá trị mà người dùng hiện tại có thể sử dụng hoặc nhìn thấy.
- Sắp xếp kết quả ổn định và giới hạn số proposal khi dữ liệu nhiều.
- Trả danh sách rỗng khi không có kết quả, thay vì đưa ra giá trị không liên quan.
- Dùng mô tả để phân biệt những giá trị có tên gần giống nhau.
- Không gọi mạng chậm hoặc truy vấn nặng mỗi lần nhấn Tab; cân nhắc cache có thời hạn nếu dữ liệu phù hợp.
- Không đưa secret, token, mật khẩu hoặc tài nguyên không được phép xem vào proposal.

Nếu một provider cần trạng thái hiện tại của project, region hoặc người dùng, hãy lấy từ context/service phù hợp. Đừng dựa vào biến static toàn cục có thể trộn dữ liệu giữa các phiên. Cũng không nên ghi log toàn bộ dòng lệnh nếu trong đó có thể chứa bí mật.

## 12. Completion trong interactive và non-interactive mode

| Môi trường | Cách nhập | Vai trò của completion |
| --- | --- | --- |
| JLine interactive shell | Người dùng nhập từng dòng và nhấn Tab | Completion provider đề xuất command, option và giá trị |
| IDE console | Phụ thuộc console có chuyển tiếp phím Tab và hỗ trợ terminal hay không | Có thể bị giới hạn; cần thử trên terminal thực |
| Chạy một lệnh từ terminal | Command và tham số được truyền ngay khi khởi chạy | Không có vòng lặp nhập lệnh để nhấn Tab |
| Script/CI | Tham số được tạo từ script hoặc pipeline | Không dựa vào completion; validation phải hoạt động độc lập |

Vì vậy, command cần có thông báo lỗi rõ ràng khi chạy không tương tác. Người dùng script cần biết option nào sai, giá trị nào được chấp nhận và mã thoát nào được trả về. Completion là tiện ích cho quá trình nhập liệu trong shell tương tác.

## 13. Kiểm thử completion và validation riêng biệt

Không nên dùng một test duy nhất để khẳng định cả completion và validation đều đúng. Hai cơ chế có đầu vào, thời điểm và kết quả khác nhau.

**Unit test cho provider** kiểm tra:

- Tiền tố rỗng trả về các lựa chọn được phép.
- Tiền tố `st` chỉ trả về giá trị bắt đầu bằng `st`.
- Không có kết quả thì trả danh sách rỗng.
- Proposal có `value` và mô tả đúng.
- Người dùng không được phép không xuất hiện trong gợi ý.
- Provider không thực hiện thao tác ghi hoặc triển khai.

**Integration test cho validation** nhập trực tiếp giá trị vào command, không dùng danh sách completion. Kiểm tra chuỗi rỗng, sai pattern, giá trị không tồn tại và giá trị hợp lệ. Xác nhận command không gọi service khi Bean Validation thất bại.

**Integration test cho service** xác nhận môi trường bị vô hiệu hóa sau khi gợi ý vẫn bị từ chối, và người dùng không có quyền không thể triển khai dù họ biết tên môi trường.

**End-to-end test** dùng JLine/terminal tương tác để xác nhận phím Tab hiển thị proposal. Với script, chạy JAR bằng tham số gõ tay và xác nhận validation hoạt động mà không cần completion.

Spring Shell 4 cung cấp `ShellTestClient`, `ShellScreen` và `ShellAssertions` để mô phỏng input command và kiểm tra output. Chúng hữu ích cho hành vi thực thi; trải nghiệm phím Tab vẫn nên được kiểm tra trong môi trường terminal có JLine phù hợp. <Link url="https://docs.spring.io/spring-shell/reference/testing.html" title="Spring Shell 4.0.3 — Testing"/>.

## 14. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Tab không hiển thị gợi ý | Ứng dụng không chạy bằng JLine shell hoặc provider chưa được gắn | Kiểm tra runner/dependency và cấu hình command |
| Gợi ý không lọc theo tiền tố | Provider bỏ qua `CompletionContext` | Dùng từ hiện tại đến vị trí con trỏ để lọc |
| Người dùng nhập giá trị ngoài danh sách vẫn chạy | Chỉ triển khai completion, chưa có validation | Thêm Bean Validation và kiểm tra trong service |
| Gợi ý chứa tài nguyên người dùng không được xem | Provider lấy catalog toàn cục, không lọc quyền | Lọc theo người dùng/session hiện tại |
| Giá trị gợi ý đã cũ | Dữ liệu thay đổi sau lần completion | Kiểm tra trạng thái lại khi command thực thi |
| Provider làm shell chậm | Truy vấn mạng hoặc tải toàn bộ dữ liệu mỗi lần Tab | Lọc ở nguồn dữ liệu, giới hạn kết quả, dùng cache phù hợp |
| API completion không biên dịch sau nâng cấp | Trộn `ValueProvider` 3.x với `CompletionProvider` 4.x | Chuyển package và cách gắn provider theo phiên bản |
| Script không có gợi ý | Completion Tab chỉ dành cho shell tương tác | Viết script với giá trị rõ ràng và dựa vào validation |

## 15. Bài thực hành tổng hợp

Xây dựng command `deploy` có completion cho tên môi trường và validation độc lập:

1. Tạo `EnvironmentCatalog` trả về danh sách môi trường đang hoạt động.
2. Tạo completion provider lọc tên môi trường theo tiền tố người dùng nhập.
3. Gắn provider vào command theo API Spring Shell của phiên bản dự án.
4. Thêm `@NotBlank`, `@Size` hoặc `@Pattern` để kiểm tra định dạng tên môi trường.
5. Trong `DeploymentService`, kiểm tra môi trường vẫn hoạt động và người dùng có quyền triển khai.
6. Nhấn Tab để xem gợi ý `development`, `staging`, `production`.
7. Gõ thủ công một tên sai định dạng và một tên đúng định dạng nhưng không tồn tại; xác nhận cả hai đều bị từ chối ở lớp phù hợp.
8. Chạy command trong script với một giá trị hợp lệ và một giá trị sai, xác nhận validation vẫn hoạt động khi không có Tab.
9. Viết unit test cho provider, integration test cho validation và service, cùng end-to-end test cho shell tương tác.

Sau bài thực hành, bạn cần giải thích được vì sao gợi ý không phải danh sách cho phép, vì sao validation phải chạy dù người dùng đã chọn gợi ý, và vì sao service vẫn phải kiểm tra quyền cùng trạng thái hiện tại.

## 16. Tiêu chí hoàn thành

| Năng lực | Tiêu chí |
| --- | --- |
| Khái niệm | Phân biệt completion, parsing, conversion, validation và authorization |
| Completion provider | Đọc ngữ cảnh và trả proposal phù hợp với tiền tố |
| Phiên bản | Dùng đúng `ValueProvider`/per-option completion ở 3.x hoặc `CompletionProvider` ở 4.x |
| Gợi ý động | Lọc theo catalog và quyền của người dùng hiện tại |
| Validation | Từ chối đầu vào sai dù người dùng không dùng Tab hoặc tự nhập giá trị |
| Nghiệp vụ | Kiểm tra lại trạng thái và quyền ngay trong service |
| Chế độ chạy | Phân biệt JLine interactive với command/script non-interactive |
| Kiểm thử | Có test riêng cho provider, validation và service |

## Tài liệu tham khảo

- [Spring Shell 3.4.1 — Completion](https://docs.spring.io/spring-shell/reference/completion.html)
- [Spring Shell 3.4.3 — `ValueProvider` API](https://docs.spring.io/spring-shell/reference/3.4-SNAPSHOT/api/java/org/springframework/shell/standard/ValueProvider.html)
- [Spring Shell 3.1 — `@OptionValues` API](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/command/annotation/OptionValues.html)
- [Spring Shell 4.0.3 — Command Completion](https://docs.spring.io/spring-shell/reference/commands/completion.html)
- [Spring Shell 4.0.3 — `CompletionProvider` API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/completion/CompletionProvider.html)
- [Spring Shell 4.0.3 — Option Validation](https://docs.spring.io/spring-shell/reference/commands/validation.html)
- [Spring Shell 4.0.3 — Testing](https://docs.spring.io/spring-shell/reference/testing.html)

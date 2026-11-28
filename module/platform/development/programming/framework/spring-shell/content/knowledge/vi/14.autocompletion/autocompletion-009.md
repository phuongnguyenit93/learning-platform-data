# Gợi ý dựa trên các tùy chọn khác và trạng thái phiên

Tự hoàn thành hữu ích nhất khi gợi ý thay đổi theo những gì người dùng đã nhập. Ví dụ, khi người dùng chọn môi trường `prod`, command triển khai chỉ nên gợi ý các region thuộc môi trường production. Nếu người dùng chưa nhập option `--environment`, ứng dụng có thể dùng môi trường đang được chọn trong phiên shell.

Spring Shell 4.x cho phép xây dựng kiểu gợi ý này bằng `CompletionProvider`. Provider nhận `CompletionContext`, đọc các token đã nhập và xác định option hiện tại; đồng thời có thể được tạo thành Spring bean để inject service đọc trạng thái phiên hoặc dữ liệu nghiệp vụ.

Bài học dùng mô hình API declarative của Spring Shell 4.x. Trọng tâm là kết hợp ba nguồn thông tin: option đã nhập trước đó, từ khóa đang được hoàn thành và trạng thái hiện tại của ứng dụng.

Các ví dụ nhấn Tab trong bài áp dụng cho shell tương tác dựa trên JLine. Hoàn thành lệnh ở command line của hệ điều hành là luồng tích hợp riêng, phụ thuộc shell hệ điều hành và cơ chế completion tương ứng.

## 1. Khi nào cần gợi ý phụ thuộc ngữ cảnh?

Gợi ý tĩnh phù hợp khi tập giá trị luôn giống nhau. Ví dụ, option `--format` có thể gợi ý `json`, `csv` và `yaml` bất kể command được gọi trong hoàn cảnh nào.

Gợi ý phụ thuộc ngữ cảnh phù hợp khi giá trị hợp lệ thay đổi theo lựa chọn khác hoặc trạng thái hiện tại:

| Ngữ cảnh | Gợi ý cần thay đổi |
|---|---|
| `--environment=prod` | Chỉ gợi ý region thuộc môi trường production |
| `--project=alpha` | Chỉ gợi ý branch của project alpha |
| Đã chọn workspace trong phiên | Gợi ý resource thuộc workspace đó |
| Đã đăng nhập bằng tài khoản có quyền giới hạn | Chỉ gợi ý tài nguyên tài khoản được phép truy cập |
| Đã chọn cluster | Gợi ý namespace thuộc cluster đang chọn |
| Chưa chọn môi trường | Dùng môi trường mặc định trong phiên hoặc yêu cầu chọn môi trường trước |

Ví dụ người dùng nhập:

```text
deploy --environment=prod --region=<Tab>
```

Nếu môi trường `prod` có các region `us-east-1` và `eu-central-1`, provider có thể gợi ý đúng hai giá trị đó. Khi người dùng đổi sang `staging`, danh sách sẽ thay đổi theo.

Gợi ý chỉ hỗ trợ khám phá dữ liệu. Command vẫn phải xác thực lại giá trị khi thực thi, vì trạng thái hoặc quyền truy cập có thể thay đổi sau khi người dùng chọn một gợi ý.

## 2. CompletionContext cung cấp thông tin gì?

`CompletionProvider` nhận một đối tượng `CompletionContext`. Đối tượng này mô tả vị trí con trỏ và nội dung người dùng đang nhập khi nhấn Tab.

Các thành phần thường dùng:

| API | Công dụng |
|---|---|
| `getWords()` | Danh sách token trong buffer, không bao gồm tên command |
| `getWordIndex()` | Vị trí token hiện tại trong danh sách |
| `getPosition()` | Vị trí con trỏ bên trong token hiện tại |
| `currentWord()` | Toàn bộ token tại vị trí con trỏ; có thể là `null` nếu con trỏ ở sau token cuối |
| `currentWordUpToCursor()` | Phần token từ đầu đến vị trí con trỏ |
| `getCommandOption()` | Option đang được hoàn thành, nếu có |
| `getCommand()` | Command hiện tại, nếu có |
| `drop(int)` | Tạo context mới sau khi bỏ một số token đầu |

Điểm quan trọng là `getWords()` chứa các token người dùng đã nhập, không phải một đối tượng chứa toàn bộ tham số Java đã binding. Nếu muốn biết option `--environment` có giá trị gì, provider cần đọc các token trước vị trí con trỏ và diễn giải cú pháp option.

Ví dụ buffer:

```text
deploy --environment=prod --region=us
```

Khi con trỏ đang ở giá trị `--region=us`, provider có thể:

1. Đọc `getCommandOption()` để biết option hiện tại là `region`.
2. Đọc `getWords()` để tìm option `environment` đã nhập trước đó.
3. Đọc `currentWordUpToCursor()` để biết người dùng đã gõ tiền tố `us`.
4. Lấy danh sách region tương ứng với môi trường `prod`.
5. Chỉ trả về các gợi ý khớp với tiền tố `us`.

`CompletionContext` được thiết kế cho lần nhấn Tab hiện tại. Không nên giả định nó là một bản sao của mọi giá trị đã được binding vào phương thức command.

## 3. Khai báo CompletionProvider cho command

Trong mô hình annotation, `@Command` có thuộc tính `completionProvider`. Thuộc tính này nhận tên bean cung cấp các gợi ý.

Ví dụ:

```java
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
public class DeploymentCommands {

    private final DeploymentSession session;

    public DeploymentCommands(DeploymentSession session) {
        this.session = session;
    }

    @Command(
        name = "environment use",
        description = "Chọn môi trường triển khai"
    )
    public String useEnvironment(
            @Option(longName = "name", required = true)
            String name) {
        session.selectEnvironment(name);
        return "Đã chọn môi trường: " + name;
    }

    @Command(
        name = "deploy",
        description = "Triển khai ứng dụng",
        completionProvider = "deployCompletionProvider"
    )
    public String deploy(
            @Option(longName = "environment")
            String environment,
            @Option(longName = "region")
            String region) {

        String selectedEnvironment = environment != null
            ? environment
            : session.selectedEnvironment();

        if (selectedEnvironment == null || selectedEnvironment.isBlank()) {
            throw new IllegalStateException("Hãy chọn môi trường trước khi triển khai");
        }

        return "Triển khai lên "
            + selectedEnvironment + "/" + region;
    }
}
```

`@Command` tham chiếu bean có tên `deployCompletionProvider`. Bean đó sẽ được khai báo trong cấu hình Spring và nhận các service cần thiết qua dependency injection.

Trong ví dụ, command `environment use` cập nhật môi trường đang chọn trong phiên. Command `deploy` có thể nhận `--environment` tường minh hoặc dùng môi trường đã chọn trước đó.

## 4. Lấy giá trị của option đã nhập trước vị trí con trỏ

Provider cần tìm giá trị của `--environment` trong buffer. Spring Shell cung cấp các token qua `CompletionContext.getWords()`, vì vậy có thể viết một helper nhỏ để đọc hai dạng option phổ biến:

```text
--environment=prod
--environment prod
```

Ví dụ helper:

```java
import java.util.List;

import org.springframework.shell.core.command.completion.CompletionContext;

private static String optionValueBeforeCursor(
        CompletionContext context,
        String optionName) {

    List<String> words = context.getWords();
    int end = Math.max(
        0,
        Math.min(context.getWordIndex(), words.size())
    );

    String option = "--" + optionName;
    String equalsPrefix = option + "=";

    // Đọc từ cuối về đầu để ưu tiên giá trị được nhập gần nhất.
    for (int i = end - 1; i >= 0; i--) {
        String word = words.get(i);

        if (word.startsWith(equalsPrefix)) {
            return word.substring(equalsPrefix.length());
        }

        if (word.equals(option) && i + 1 < end) {
            return words.get(i + 1);
        }
    }

    return null;
}
```

Helper chỉ duyệt các token đứng trước token hiện tại. Nhờ đó, nếu người dùng đang nhập `--region=`, phần chưa hoàn chỉnh của option hiện tại không bị đọc nhầm thành một giá trị đã chọn.

Đoạn helper trên hỗ trợ tên option dài. Nếu command còn hỗ trợ short option như `-e`, hãy bổ sung cách nhận diện alias đó và kiểm thử cả hai dạng. Với option có thể xuất hiện nhiều lần, ví dụ cuối cùng được ưu tiên trong helper này; quy tắc lặp option của ứng dụng cần được công bố nhất quán.

## 5. Kết hợp option khác với trạng thái phiên

Giả sử ứng dụng có ba môi trường:

| Environment | Region |
|---|---|
| `dev` | `local`, `eu-west-1` |
| `staging` | `eu-west-1`, `ap-southeast-1` |
| `prod` | `us-east-1`, `eu-central-1` |

Provider sẽ chọn môi trường theo thứ tự:

1. Nếu người dùng đã nhập `--environment`, dùng giá trị đó.
2. Nếu chưa nhập option, dùng môi trường đã chọn trong phiên.
3. Nếu không có cả hai, không đưa ra gợi ý region.

Một bean lưu trạng thái phiên đơn giản:

```java
import org.springframework.stereotype.Component;

@Component
public class DeploymentSession {

    private volatile String selectedEnvironment;

    public String selectedEnvironment() {
        return selectedEnvironment;
    }

    public void selectEnvironment(String environment) {
        this.selectedEnvironment = environment;
    }
}
```

Một service cung cấp dữ liệu region:

```java
import java.util.List;
import java.util.Locale;
import java.util.Map;

import org.springframework.stereotype.Component;

@Component
public class RegionCatalog {

    private final Map<String, List<String>> regionsByEnvironment = Map.of(
        "dev", List.of("local", "eu-west-1"),
        "staging", List.of("eu-west-1", "ap-southeast-1"),
        "prod", List.of("us-east-1", "eu-central-1")
    );

    public List<String> regionsFor(String environment) {
        if (environment == null || environment.isBlank()) {
            return List.of();
        }

        String key = environment.trim().toLowerCase(Locale.ROOT);
        return regionsByEnvironment.getOrDefault(key, List.of());
    }
}
```

Trong hệ thống thật, `RegionCatalog` có thể đọc cấu hình triển khai, repository hoặc API quản lý hạ tầng. Provider chỉ nên gọi một service có trách nhiệm cung cấp danh sách phù hợp.

## 6. Viết provider lọc gợi ý theo option và tiền tố đang nhập

Đây là phần kết hợp `CompletionContext`, `DeploymentSession` và `RegionCatalog`:

```java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.core.command.CommandOption;
import org.springframework.shell.core.command.completion.CompletionContext;
import org.springframework.shell.core.command.completion.CompletionProposal;
import org.springframework.shell.core.command.completion.CompletionProvider;

@Configuration
public class DeploymentCompletionConfiguration {

    @Bean("deployCompletionProvider")
    public CompletionProvider deployCompletionProvider(
            RegionCatalog regionCatalog,
            DeploymentSession session) {

        return context -> {
            CommandOption currentOption = context.getCommandOption();

            if (currentOption == null
                    || !"region".equals(currentOption.longName())) {
                return List.of();
            }

            String explicitEnvironment =
                optionValueBeforeCursor(context, "environment");
            String effectiveEnvironment = explicitEnvironment != null
                ? explicitEnvironment
                : session.selectedEnvironment();

            if (effectiveEnvironment == null || effectiveEnvironment.isBlank()) {
                return List.of();
            }

            String currentWord = context.currentWordUpToCursor();
            String prefix = valuePrefix(currentWord);

            boolean currentWordHasOptionName =
                currentWord != null
                    && currentWord.startsWith("--region=");

            return regionCatalog.regionsFor(effectiveEnvironment).stream()
                .filter(region -> region.startsWith(prefix))
                .map(region -> {
                    String proposalValue = currentWordHasOptionName
                        ? "--region=" + region
                        : region;

                    return new CompletionProposal(proposalValue)
                        .description("Region của " + effectiveEnvironment);
                })
                .toList();
        };
    }

    private static String optionValueBeforeCursor(
            CompletionContext context,
            String optionName) {

        List<String> words = context.getWords();
        int end = Math.max(
            0,
            Math.min(context.getWordIndex(), words.size())
        );

        String option = "--" + optionName;
        String equalsPrefix = option + "=";

        for (int i = end - 1; i >= 0; i--) {
            String word = words.get(i);

            if (word.startsWith(equalsPrefix)) {
                return word.substring(equalsPrefix.length());
            }

            if (word.equals(option) && i + 1 < end) {
                return words.get(i + 1);
            }
        }

        return null;
    }

    private static String valuePrefix(String currentWord) {
        if (currentWord == null) {
            return "";
        }

        int equalsIndex = currentWord.indexOf('=');
        return equalsIndex >= 0
            ? currentWord.substring(equalsIndex + 1)
            : currentWord;
    }
}
```

Provider thực hiện bốn việc:

- Xác nhận option đang được hoàn thành là `region`.
- Đọc `environment` từ những token đã nhập trước đó; nếu không có, lấy môi trường trong `DeploymentSession`.
- Lấy tiền tố người dùng đang gõ để lọc danh sách region.
- Trả về `CompletionProposal` chứa giá trị cần chèn và mô tả ngắn.

Ví dụ khi người dùng đã chọn `prod` trong phiên:

```text
environment use --name=prod
deploy --region=<Tab>
```

Các gợi ý:

```text
--region=us-east-1
--region=eu-central-1
```

Nếu người dùng chỉ định môi trường ngay trong command:

```text
deploy --environment=staging --region=<Tab>
```

Provider dùng `staging` từ buffer, nên gợi ý:

```text
--region=eu-west-1
--region=ap-southeast-1
```

Nếu người dùng nhập tiếp tiền tố:

```text
deploy --environment=prod --region=us<Tab>
```

Provider chỉ trả về region khớp với tiền tố `us`.

Ví dụ này minh họa dạng option `--region=value`. Nếu ứng dụng cần hỗ trợ hoàn thành khi người dùng viết `--region value`, hãy kiểm tra cách JLine thay thế token hiện tại trên phiên bản đang dùng và điều chỉnh `CompletionProposal` tương ứng. Không nên giả định hai dạng nhập luôn có cùng cách chèn gợi ý nếu chưa kiểm tra trên terminal thực tế.

## 7. Dùng trạng thái phiên mà không có option tường minh

Không phải command nào cũng cần người dùng lặp lại thông tin đã chọn. CLI có thể lưu workspace, project, environment hoặc account hiện tại trong một service quản lý phiên.

Ví dụ:

```text
workspace use --name=platform
project use --name=learning-api
deploy --region=<Tab>
```

Nếu project hiện tại thuộc môi trường `staging`, provider có thể lấy môi trường từ trạng thái phiên và đưa ra các region tương ứng.

Thứ tự ưu tiên nên rõ ràng:

| Nguồn | Khi sử dụng |
|---|---|
| Option hiện tại trong buffer | Người dùng chủ động ghi đè trạng thái mặc định cho lần gọi này |
| Trạng thái phiên | Người dùng không truyền option và đã chọn giá trị trước đó |
| Giá trị mặc định cấu hình | Ứng dụng có mặc định được công bố |
| Không có giá trị | Trả danh sách rỗng hoặc gợi ý chọn giá trị cha trước |

Không nên âm thầm chọn một giá trị mặc định không được công bố. Nếu thiếu environment khiến không thể đưa ra gợi ý đúng, trả về danh sách rỗng hoặc hướng dẫn người dùng chọn environment trước.

### 7.1. Cô lập trạng thái giữa nhiều người dùng

Ví dụ `DeploymentSession` ở trên là một Spring singleton, nên trạng thái được chia sẻ trong cùng ApplicationContext. Cách này phù hợp với CLI chạy cục bộ cho một người dùng.

Nếu shell phục vụ nhiều người dùng hoặc nhiều phiên đồng thời, không lưu lựa chọn riêng của người dùng vào một singleton dùng chung. Hãy lưu theo session id, principal đã xác thực hoặc một context riêng cho từng người dùng. Nếu không, người dùng này có thể nhận gợi ý dựa trên workspace hoặc project của người dùng khác.

## 8. Kết hợp provider động với provider có sẵn

Spring Shell cung cấp một số provider có sẵn:

| Provider | Mục đích |
|---|---|
| `EnumCompletionProvider` | Gợi ý các giá trị của enum |
| `FileNameCompletionProvider` | Gợi ý tên file và thư mục |
| `CompositeCompletionProvider` | Kết hợp nhiều provider |
| `DefaultCompletionProvider` | Hỗ trợ gợi ý option và enum theo ngữ cảnh mặc định |

Nếu một command có cả giá trị enum cố định và giá trị phụ thuộc trạng thái, có thể kết hợp provider bằng `CompositeCompletionProvider`.

Ví dụ theo API của Spring Shell 4.x:

```java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.core.command.completion.CompletionProvider;
import org.springframework.shell.core.command.completion.CompletionProposal;
import org.springframework.shell.core.command.completion.CompositeCompletionProvider;
import org.springframework.shell.core.command.completion.EnumCompletionProvider;

enum ExportFormat {
    CSV, JSON, YAML
}

@Configuration
class ExportCompletionConfiguration {

    @Bean
    CompletionProvider exportCompletionProvider() {
        CompletionProvider formatProvider =
            new EnumCompletionProvider(ExportFormat.class, "--format");

        CompletionProvider destinationProvider = context ->
            List.of(
                new CompletionProposal("--destination=local"),
                new CompletionProposal("--destination=remote")
            );

        return new CompositeCompletionProvider(
            formatProvider,
            destinationProvider
        );
    }
}
```

Khi ghép nhiều provider, cần tránh để chúng trả về các gợi ý trùng hoặc xung đột. Provider động vẫn có thể được thêm vào cùng một composite nếu mỗi provider có phạm vi trách nhiệm rõ ràng.

## 9. Metadata của CompletionProposal

`CompletionProposal` không chỉ chứa chuỗi sẽ được chèn vào dòng lệnh. Nó còn hỗ trợ metadata giúp giao diện hiển thị gợi ý dễ hiểu hơn.

| Thuộc tính | Ý nghĩa |
|---|---|
| `value` | Nội dung được chèn vào command line |
| `displayText` | Nội dung hiển thị trong danh sách gợi ý |
| `description` | Mô tả ngắn về gợi ý |
| `category` | Nhóm gợi ý |
| `dontQuote` | Điều khiển việc không thêm dấu nháy cho giá trị |

Ví dụ:

```java
new CompletionProposal("--region=eu-central-1")
    .displayText("eu-central-1")
    .description("Region production tại châu Âu")
    .category("Production");
```

Giá trị được chèn vẫn là `--region=eu-central-1`, trong khi người dùng nhìn thấy tên region ngắn và phần mô tả. Metadata đặc biệt hữu ích khi danh sách có nhiều tài nguyên với tên gần giống nhau.

Nếu giá trị chứa khoảng trắng hoặc ký tự đặc biệt, hãy để parser và cơ chế quoting xử lý theo đúng quy tắc của shell. Chỉ đặt `dontQuote(true)` khi ứng dụng chắc chắn giá trị có thể được chèn nguyên dạng.

## 10. Dùng CompletionProvider với Command.Builder

Mô hình programmatic cũng hỗ trợ completion provider. Thay vì khai báo tên bean trong `@Command`, có thể truyền trực tiếp provider vào builder:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.core.command.Command;
import org.springframework.shell.core.command.CommandOption;
import org.springframework.shell.core.command.completion.CompletionProvider;

@Configuration
class DeployCommandConfiguration {

    @Bean
    Command deployCommand(CompletionProvider deployCompletionProvider) {
        CommandOption environmentOption = CommandOption.with()
            .longName("environment")
            .type(String.class)
            .build();

        CommandOption regionOption = CommandOption.with()
            .longName("region")
            .type(String.class)
            .build();

        return Command.builder()
            .name("deploy")
            .description("Triển khai ứng dụng")
            .options(environmentOption, regionOption)
            .completionProvider(deployCompletionProvider)
            .execute(context -> "Đang triển khai...");
    }
}
```

Cách này phù hợp khi command được tạo bằng Java configuration hoặc được xây dựng động. Logic tạo gợi ý vẫn nằm trong `CompletionProvider`, nên có thể tái sử dụng cùng provider cho command annotation hoặc command programmatic khi hợp đồng phù hợp.

## 11. Hiệu năng, bảo mật và tính nhất quán

Completion có thể được gọi nhiều lần khi người dùng nhấn Tab. Vì vậy, provider cần được thiết kế như một thao tác đọc nhanh:

**Tránh gọi API chậm ở mỗi lần nhấn Tab.** Nếu cần dữ liệu từ hệ thống bên ngoài, dùng service có timeout hợp lý, cache ngắn hạn hoặc dữ liệu đã được đồng bộ. Không để terminal phải chờ lâu chỉ để hiển thị gợi ý.

**Không thay đổi trạng thái trong provider.** Completion chỉ đề xuất giá trị. Việc chọn environment, project hoặc workspace phải do command hoặc thao tác rõ ràng khác thực hiện.

**Lọc theo quyền truy cập.** Chỉ đưa ra tài nguyên người dùng hiện tại được phép xem và chọn. Gợi ý cũng có thể làm lộ tên project, namespace hoặc tài nguyên nội bộ.

**Đọc trạng thái từ một nguồn thống nhất.** Nếu command dùng `DeploymentSession` để xác định môi trường mặc định, provider cũng nên dùng cùng nguồn đó. Tránh có một trạng thái trong completion và một trạng thái khác trong command handler.

**Xác thực lại khi thực thi.** Người dùng có thể chọn gợi ý rồi trạng thái thay đổi trước khi gọi command. Service nghiệp vụ phải kiểm tra lại tài nguyên có còn tồn tại, còn khả dụng và người dùng có quyền sử dụng hay không.

**Xử lý dữ liệu không khả dụng.** Nếu service tra cứu lỗi hoặc không có môi trường phù hợp, trả danh sách rỗng và ghi log ở mức phù hợp. Không biến lỗi tra cứu thành một danh sách gợi ý giả.

## 12. Kiểm thử provider theo ngữ cảnh

Nên kiểm thử riêng các quy tắc chọn môi trường và lọc region, sau đó kiểm thử tích hợp với shell để xác nhận nội dung được chèn đúng.

Một bảng tình huống cơ bản:

| Tình huống | Kết quả mong đợi |
|---|---|
| Buffer có `--environment=prod` | Gợi ý region của `prod` |
| Buffer có `--environment staging` | Gợi ý region của `staging` |
| Không có option environment nhưng phiên đã chọn `dev` | Gợi ý region của `dev` |
| Không có option và phiên chưa chọn environment | Không có gợi ý region |
| Đã gõ `--region=us` | Chỉ gợi ý giá trị bắt đầu bằng `us` |
| Đang hoàn thành option khác | Provider region trả danh sách rỗng |
| Environment không tồn tại | Không có gợi ý |
| Người dùng không có quyền với region | Region đó không xuất hiện |

Có thể tách helper đọc option thành hàm riêng và kiểm thử với các buffer:

```text
--environment=prod --region=
--environment prod --region=
--environment=staging --region=eu
--environment=prod --region=us
```

Ngoài unit test, hãy chạy shell thật và nhấn Tab tại từng vị trí. Cách này xác nhận `CompletionContext`, `getCommandOption()` và nội dung `CompletionProposal` phối hợp đúng với parser/JLine của phiên bản đang dùng.

## 13. Các lỗi thường gặp

**Dùng một danh sách tĩnh cho mọi trạng thái.** Người dùng có thể nhận region không thuộc environment đang chọn. Hãy lọc theo option đã nhập hoặc trạng thái phiên.

**Đọc nhầm token hiện tại thành option đã hoàn tất.** Khi người dùng đang gõ `--region=`, token này chưa chứa một giá trị hoàn chỉnh. Chỉ đọc các token đứng trước `getWordIndex()` khi tìm option phụ thuộc.

**Cho rằng CompletionContext chứa tham số Java đã binding.** `getWords()` cung cấp token trong buffer. Provider phải diễn giải option cần thiết từ các token đó.

**Không kiểm tra option hiện tại.** Nếu provider trả gợi ý region khi người dùng đang hoàn thành option khác, kết quả sẽ gây nhiễu. Kiểm tra `getCommandOption()` trước khi tạo đề xuất.

**Bỏ qua tiền tố người dùng đã gõ.** Khi người dùng nhập `--region=us`, nên chỉ trả về các region bắt đầu bằng `us` thay vì toàn bộ danh sách.

**Lấy trạng thái từ singleton trong ứng dụng nhiều người dùng.** Lựa chọn của người này có thể ảnh hưởng gợi ý của người khác. Lưu trạng thái theo session hoặc principal.

**Thực hiện thao tác nghiệp vụ trong provider.** Completion có thể được gọi nhiều lần. Provider nên chỉ đọc dữ liệu và tạo đề xuất.

**Không kiểm tra quyền và dữ liệu khi thực thi.** Gợi ý không phải xác thực. Command phải kiểm tra lại trước khi thao tác.

**Trả về chuỗi chèn không đúng vị trí.** Với option dạng `--region=value`, provider có thể cần trả cả option và giá trị. Với dạng `--region value`, cách chèn có thể khác. Kiểm tra trên terminal thực tế.

## 14. Checklist triển khai

- [ ] Xác định option nào quyết định danh sách gợi ý của option khác.
- [ ] Xác định trạng thái phiên có thể dùng làm giá trị mặc định hay không.
- [ ] Gắn `completionProvider` vào `@Command` hoặc `Command.Builder`.
- [ ] Đăng ký provider thành Spring bean nếu dùng annotation.
- [ ] Dùng `CompletionContext.getCommandOption()` để nhận diện option hiện tại.
- [ ] Dùng `getWords()` và `getWordIndex()` để đọc các token trước con trỏ.
- [ ] Xử lý cả `--option=value` và `--option value` nếu hợp đồng CLI hỗ trợ cả hai.
- [ ] Dùng `currentWordUpToCursor()` để lọc theo tiền tố.
- [ ] Trả `CompletionProposal` với giá trị chèn đúng cú pháp.
- [ ] Dùng trạng thái phiên theo đúng phạm vi người dùng.
- [ ] Giữ provider nhanh, chỉ đọc và không có tác dụng phụ.
- [ ] Lọc tài nguyên theo quyền truy cập.
- [ ] Xác thực lại option và quyền trong command/service khi thực thi.
- [ ] Kiểm thử nhiều thứ tự option, giá trị thiếu và trạng thái phiên khác nhau.
- [ ] Thử nhấn Tab trong terminal thật để xác nhận hành vi chèn gợi ý.

## 15. Tài liệu tham khảo chính thức

- [Spring Shell 4.x — Command Completion](https://docs.spring.io/spring-shell/reference/commands/completion.html): khai báo `CompletionProvider`, bean completion, provider dựng sẵn và `CompositeCompletionProvider`.
- [Spring Shell 4.x API — CompletionContext](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/completion/CompletionContext.html): `getWords()`, `getWordIndex()`, `getCommandOption()`, `currentWordUpToCursor()` và các thông tin buffer.
- [Spring Shell 4.x API — CompletionProvider](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/completion/CompletionProvider.html): hợp đồng nhận `CompletionContext` và trả danh sách `CompletionProposal`.
- [Spring Shell 4.x API — CompletionProposal](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/completion/CompletionProposal.html): giá trị, nhãn hiển thị, mô tả và metadata của đề xuất.
- [Spring Shell 4.x API — Command annotation](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/Command.html): thuộc tính `completionProvider` để liên kết command với bean.
- [Spring Shell 4.x API — Command.Builder](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/Command.Builder.html): phương thức `completionProvider(...)` trong mô hình programmatic.

Một completion provider tốt không chỉ biết người dùng đang gõ ký tự nào. Nó còn hiểu các lựa chọn đã nhập trước đó và trạng thái hiện tại của ứng dụng. Hãy đọc ngữ cảnh từ `CompletionContext`, lấy dữ liệu phiên qua service phù hợp, lọc gợi ý theo quyền và tiền tố, rồi để command xác thực lại trước khi thực thi.


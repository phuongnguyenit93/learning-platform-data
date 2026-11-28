# Đối chiếu trợ giúp, lịch sử, stacktrace và completion tích hợp

Khi nâng một ứng dụng Spring Shell từ 3.x lên 4.x, các command hỗ trợ người vận hành cũng thay đổi. `help` vẫn là nơi khám phá command và option; `history` phụ thuộc vào JLine; `stacktrace` được thay bằng debug mode; còn built-in command `completion bash` bị loại bỏ trong khi khả năng gợi ý bằng phím Tab vẫn được duy trì trong JLine shell.

Điểm dễ nhầm nhất là có hai loại completion: gợi ý ngay trong REPL khi người dùng nhấn Tab và tạo script để shell bên ngoài như Bash tự hoàn thành command. Spring Shell 4 vẫn hỗ trợ loại thứ nhất thông qua `CompletionProvider`, nhưng không còn built-in command `completion` để tạo script Bash như 3.x. Tương tự, việc không thấy `history` trong `help` có thể do ứng dụng không dùng JLine, chứ không nhất thiết do toàn bộ chức năng history đã bị xóa.

Bài viết đối chiếu Spring Shell 3.4.x và 4.0.x, tập trung vào bốn tính năng tích hợp: trợ giúp, lịch sử command, chẩn đoán stack trace và hoàn thành lệnh/giá trị.

## Bảng đối chiếu nhanh giữa 3.4.x và 4.0.x

| Tính năng | Spring Shell 3.4.x | Spring Shell 4.0.x |
| --- | --- | --- |
| `help` | Liệt kê command, kể cả command unavailable; `help <command>` hiển thị chi tiết; hỗ trợ template tùy chỉnh | Vẫn có `help`; `help <command>` hiển thị chi tiết; command hỗ trợ `-h`/`--help` |
| History | Built-in `history` hiển thị/xuất lịch sử; JLine history được lưu vào file theo cấu hình | History command thuộc module JLine; cần `spring-shell-jline`; không có trong core-only `SystemShellRunner` |
| Stack trace | Lỗi hiển thị thông báo ngắn; `stacktrace` in chi tiết exception gần nhất | Built-in `stacktrace` bị loại bỏ; bật `spring.shell.debug.enabled=true` để in stack trace ngay khi lỗi xảy ra trong interactive shell |
| Completion trong REPL | Tab completion qua `CompletionResolver`/`ValueProvider` và JLine | Tab completion vẫn có trong JLine; dùng `CompletionProvider` ở cấp command |
| Tạo completion cho Bash | Built-in `completion bash` tạo script completion | Built-in command `completion` bị loại bỏ; cấu hình completion cho shell bên ngoài theo công cụ triển khai |
| Phụ thuộc JLine | Thường được kéo qua starter/cấu hình 3.x | `spring-shell-core` không phụ thuộc JLine; thêm `spring-shell-jline` khi cần line editing, history và Tab completion |

Đây là khác biệt về API và module, không chỉ là đổi tên command. Khi migration, hãy kiểm tra dependency thực tế, loại shell runner đang dùng và danh sách command từ `help` trong artifact đã build.

## `help`: khám phá command và cú pháp

### Spring Shell 3.4.x

Gõ `help` để liệt kê các command đã đăng ký. Danh sách bao gồm cả command hiện không khả dụng, cùng mô tả ngắn để người dùng biết command tồn tại và điều kiện nào đang chặn nó.

```text
shell:> help

AVAILABLE COMMANDS

Built-In Commands
    help: Display help about available commands
    stacktrace: Display the full stacktrace of the last error.
    history: Display or save the history of previously run commands
    completion bash: Generate bash completion script
    version: Show version info

Artifact Commands
    artifact list: List available artifacts
    artifact publish: Publish an artifact
```

Nội dung trên chỉ minh họa cách nhóm command. Danh sách thật phụ thuộc vào bean, module và property enable trong ứng dụng.

Để xem cú pháp một command:

```text
shell:> help artifact publish

NAME
    artifact publish - Publish an artifact

SYNOPSIS
    artifact publish --name String --repository String

OPTIONS
    --name String
        Artifact name
        [Mandatory]
    --repository String
        Target repository
        [Mandatory]
```

`help <command>` cung cấp tên command, synopsis, kiểu tham số, tham số bắt buộc/tùy chọn và mô tả. Đây là cách kiểm tra nhanh contract CLI sau khi thêm hoặc đổi option.

Trong 3.4.x, output help được dựng từ template. Các cấu hình thường dùng nằm dưới `spring.shell.command.help`:

```yaml
spring:
  shell:
    command:
      help:
        enabled: true
        grouping-mode: flat
        commands-template: classpath:template/help-commands.stg
        command-template: classpath:template/help-command.stg
```

- `enabled` bật/tắt built-in command `help`.
- `grouping-mode` chọn cách nhóm command; `flat` hiển thị danh sách phẳng thay vì nhóm.
- `commands-template` tùy chỉnh output của danh sách command.
- `command-template` tùy chỉnh output chi tiết của một command.

Hai template nhận model khác nhau: danh sách command dùng `GroupsInfoModel`, còn help chi tiết dùng `CommandInfoModel`. Model chứa tên, alias, mô tả, parameters, default value và trạng thái availability. Khi viết template riêng, cần giữ lại thông tin về command unavailable để người vận hành hiểu vì sao lệnh chưa thể chạy.

### Spring Shell 4.0.x

`help` vẫn liệt kê command và mô tả ngắn. Có thể yêu cầu trợ giúp theo hai cách:

```text
shell:> help artifact publish
shell:> artifact publish --help
shell:> artifact publish -h
```

`help <command>` hiển thị nội dung chi tiết. Tùy command implementation, `-h`/`--help` được xử lý như yêu cầu trợ giúp và bỏ qua việc thực thi nghiệp vụ. Từ Spring Shell 4.0.4, `CommandHelpRenderer` dùng cùng một nội dung cho `help <command>` và option trợ giúp ngầm định của command, giúp hai đường truy cập có kết quả nhất quán.

Trong mô hình command mới, nên khai báo mô tả ngắn và phần help dài ngay trên command:

```java
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
public class ArtifactCommands {

    @Command(
            name = {"artifact", "publish"},
            description = "Publish an artifact",
            help = "Publish an artifact to a repository. "
                    + "Use --repository to select the target repository.")
    public String publish(
            @Option(longName = "name", description = "Artifact name") String name,
            @Option(longName = "repository", description = "Target repository") String repository) {
        return "Published " + name + " to " + repository;
    }
}
```

`description` là dòng ngắn dùng trong danh sách command; `help` dành cho phần giải thích dài hơn. Mô tả option giúp người dùng hiểu dữ liệu cần truyền khi xem trợ giúp.

Ở 4.x, property enable command help vẫn nằm dưới `spring.shell.command.help.enabled`. Tuy nhiên, không nên mặc định rằng các hook template `commands-template`/`command-template` của 3.x còn giữ nguyên. Help 4.x dùng command model và renderer mới; hãy kiểm tra API của đúng bản 4.x trước khi chuyển một template tùy chỉnh từ 3.x. Nếu chỉ cần hướng dẫn theo command, khai báo `description` và `help` ngay trên command là cách đơn giản và ổn định hơn.

## `history`: xem và lưu lịch sử command

### Spring Shell 3.4.x

Built-in command `history` hiển thị các command đã chạy. Có thể truyền file để lưu danh sách command ra một file có thể dùng lại với `script`:

```text
shell:> history
1  help
2  remote connect staging
3  artifact list

shell:> history --file ./session.shell
```

History được lưu vào file theo mặc định. Các thuộc tính chính:

```yaml
spring:
  application:
    name: inventory-shell
  shell:
    history:
      enabled: true
      name: inventory-history.log
    config:
      location: "{userconfig}/inventory-shell"
```

| Thuộc tính | Tác dụng |
| --- | --- |
| `spring.shell.history.enabled` | Bật/tắt lưu lịch sử xuống file |
| `spring.shell.history.name` | Tên file history; mặc định suy ra từ `spring.application.name`, hoặc `spring-shell.log` |
| `spring.shell.config.location` | Thư mục cấu hình/history; mặc định là working directory và hỗ trợ placeholder `{userconfig}` |
| `spring.shell.command.history.enabled` | Bật/tắt built-in command `history` |

Hai thuộc tính `history.enabled` và `command.history.enabled` có mục đích khác nhau. Tắt command `history` không nhất thiết tắt cơ chế lưu lịch sử; ngược lại, giữ command nhưng tắt persistence có thể khiến lệnh xem lịch sử chỉ phản ánh dữ liệu còn trong phiên hiện tại.

### Spring Shell 4.0.x

Spring Shell 4 tách JLine khỏi `spring-shell-core`. `history` là command thuộc module `spring-shell-jline`, với implementation `org.springframework.shell.jline.command.History`. `JLineShellAutoConfiguration` đăng ký history command khi classpath có JLine và `spring.shell.command.history.enabled` không bị tắt.

Điều này tạo ra hai trường hợp:

- **JLine shell:** có line editing, Tab completion và history command; JLine `History` bean có thể ghi lịch sử ra file để dùng lại ở lần chạy sau.
- **System shell/core-only:** dùng `java.io.Console`; không có JLine history command, không có line editing nâng cao và không có Tab completion.

Nếu cần history trong 4.x, thêm dependency JLine tương ứng, thường thông qua starter JLine hoặc `spring-shell-jline`:

```xml
<dependency>
    <groupId>org.springframework.shell</groupId>
    <artifactId>spring-shell-jline</artifactId>
</dependency>
```

Các thuộc tính history vẫn được biểu diễn trong `SpringShellProperties.History`, gồm `enabled` và `name`; command có cấu hình riêng `spring.shell.command.history.enabled`. Ví dụ:

```yaml
spring:
  shell:
    history:
      enabled: true
      name: inventory-history.log
    command:
      history:
        enabled: true
```

Nếu không thấy `history` trong `help` sau khi nâng cấp, kiểm tra `spring-shell-jline` có nằm trong runtime classpath hay không trước khi kết luận command đã bị xóa. Cũng kiểm tra property command có bị đặt `false` và user chạy ứng dụng có quyền ghi vào thư mục cấu hình hay không.

### Lịch sử và dữ liệu nhạy cảm

History có thể chứa toàn bộ dòng command, bao gồm tên người dùng, đường dẫn, mã định danh và option. Không truyền password, access token, private key hoặc secret trực tiếp trên command line nếu shell lưu history. Nên dùng cơ chế nhập bí mật phù hợp hoặc secret provider; nếu môi trường không được phép lưu command, tắt persistence:

```yaml
spring:
  shell:
    history:
      enabled: false
```

Tắt persistence không tự xóa file history cũ. Khi cần xóa lịch sử đã lưu, xử lý file theo chính sách vận hành và quyền truy cập của người dùng hệ điều hành.

## `stacktrace`: chẩn đoán lỗi trong 3.x và 4.x

### Cách hoạt động trong Spring Shell 3.4.x

Khi command ném exception, shell thường hiển thị một thông báo ngắn để tránh tràn terminal. Spring Shell giữ exception gần nhất; người dùng có thể chạy:

```text
shell:> artifact publish --name duplicate
Artifact already exists

shell:> stacktrace
org.example.ArtifactAlreadyExistsException: Artifact already exists
    at org.example.ArtifactService.publish(ArtifactService.java:42)
    at org.example.ArtifactCommands.publish(ArtifactCommands.java:27)
    ...
```

`stacktrace` in chi tiết exception và nested cause của lỗi gần nhất. Nó hữu ích khi người vận hành cần xem lỗi mà không phải khởi động lại shell với log framework ở mức DEBUG.

Có thể tắt built-in command bằng property:

```yaml
spring:
  shell:
    command:
      stacktrace:
        enabled: false
```

### Cách thay thế trong Spring Shell 4.0.x

Spring Shell 4 loại bỏ built-in command `stacktrace`. Lý do được migration guide nêu là command cũ phải giữ global mutable state để nhớ exception gần nhất. Thay vào đó, bật debug mode để stack trace được in ngay khi lỗi xảy ra:

```yaml
spring:
  shell:
    debug:
      enabled: true
```

Hoặc truyền property lúc khởi động:

```bash
java -jar app.jar --spring.shell.debug.enabled=true
```

Trong 4.x, debug mode giúp nhìn thấy stack trace của từng lỗi tại thời điểm phát sinh, thay vì chạy thêm `stacktrace` sau đó. Điều này phù hợp khi điều tra lỗi trong một phiên tương tác. Trong môi trường production, chỉ bật khi cần và kiểm soát log vì stack trace có thể chứa tên class, đường dẫn, cấu trúc nội bộ hoặc dữ liệu trong exception message.

Không nhầm `spring.shell.debug.enabled` với `--debug` của Spring Boot hoặc `logging.level.org.springframework.shell=DEBUG`:

| Cấu hình | Tác dụng |
| --- | --- |
| `spring.shell.debug.enabled=true` | Spring Shell 4 in stack trace lỗi command ngay khi lỗi xảy ra trong interactive shell |
| `logging.level.org.springframework.shell=DEBUG` | Bật log DEBUG cho logger Spring Shell |
| `--debug` của Spring Boot | Bật một tập logger lõi và condition evaluation report của Boot; không tự đồng nghĩa với debug mode của Spring Shell |

Trong 3.4.x, dùng `stacktrace` để xem exception gần nhất; trong 4.x, bật debug mode trước khi tái hiện lỗi. Nếu cần log framework ở cả hai thế hệ, cấu hình logger riêng.

## Completion: phân biệt Tab completion và built-in `completion bash`

Completion có hai mục đích:

1. Gợi ý command, option hoặc giá trị khi người dùng đang nhập trong REPL và nhấn Tab.
2. Tạo script tích hợp với shell hệ điều hành như Bash để hoàn thành command khi người dùng chạy ứng dụng từ command line.

Hai mục đích này có API và vòng đời khác nhau. Việc bỏ built-in command `completion` trong 4.x không có nghĩa Tab completion đã bị loại bỏ.

### Spring Shell 3.4.x: completion trong REPL

Với interactive shell, Spring Shell sử dụng `CompletionContext` để biết vị trí con trỏ, command và option đang nhập. Resolver trả về danh sách `CompletionProposal` để shell hiển thị các gợi ý.

Trong mô hình annotation legacy, có thể cung cấp `ValueProvider` cho một option:

```java
import java.util.List;

import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;
import org.springframework.shell.standard.ShellOption;
import org.springframework.shell.standard.ValueProvider;
import org.springframework.shell.CompletionContext;
import org.springframework.shell.CompletionProposal;
import org.springframework.stereotype.Component;

@Component
public class EnvironmentValueProvider implements ValueProvider {

    @Override
    public List<CompletionProposal> complete(CompletionContext context) {
        return List.of(
                new CompletionProposal("development"),
                new CompletionProposal("staging"),
                new CompletionProposal("production"));
    }
}

@ShellComponent
public class DeployCommands {

    @ShellMethod(key = "deploy", value = "Deploy an application")
    public String deploy(
            @ShellOption(valueProvider = EnvironmentValueProvider.class)
            String environment) {
        return "Deploying to " + environment;
    }
}
```

`ValueProvider` cần được Spring đăng ký như bean theo quy tắc của annotation model đang dùng. Với command khai báo bằng `CommandRegistration.Builder`, completion có thể được gắn trực tiếp vào option bằng `.completion(...)`. Cả hai cách đều cung cấp gợi ý cho phiên interactive; chúng không phải script completion cho Bash.

### Spring Shell 3.4.x: built-in command tạo Bash completion

Trong 3.4.x, built-in command:

```text
shell:> completion bash
```

tạo script có thể được nạp vào Bash để hoàn thành command khi gọi ứng dụng từ OS shell. Tài liệu 3.4.x mô tả Bash là implementation được hỗ trợ cho command này. Đây là tiện ích phục vụ command-line completion bên ngoài REPL, đặc biệt hữu ích khi ứng dụng thường chạy non-interactive.

Việc tạo script chỉ là một phần quy trình. Người dùng vẫn cần cài hoặc source script theo cơ chế completion của Bash trên máy của họ. Nếu script được sinh từ một phiên bản CLI, hãy tạo lại sau khi command, alias hoặc option thay đổi.

### Spring Shell 4.0.x: `CompletionProvider`

Trong 4.x, built-in command `completion` đã bị loại bỏ. Completion trong REPL vẫn được hỗ trợ bởi JLine shell và được cấu hình tập trung ở cấp command bằng `CompletionProvider`.

Các provider có sẵn:

| Provider | Gợi ý |
| --- | --- |
| `DefaultCompletionProvider` | Command option và giá trị enum theo ngữ cảnh |
| `EnumCompletionProvider` | Các giá trị của một enum |
| `FileNameCompletionProvider` | Tên file và thư mục |
| `CompositeCompletionProvider` | Kết hợp nhiều provider |
| `CompletionProvider` tự viết | Gợi ý dựa trên command, option và nội dung đã nhập |

Ví dụ gắn provider vào command mới:

```java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.shell.core.command.completion.CompletionProvider;
import org.springframework.shell.core.command.completion.CompletionProposal;
import org.springframework.shell.core.command.completion.CompositeCompletionProvider;
import org.springframework.shell.core.command.completion.EnumCompletionProvider;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
public class DeployCommands {

    enum Environment {
        DEVELOPMENT, STAGING, PRODUCTION
    }

    @Command(
            name = "deploy",
            description = "Deploy an application",
            completionProvider = "deployCompletionProvider")
    public String deploy(
            @Option(longName = "environment") Environment environment,
            @Option(longName = "service") String service) {
        return "Deploying " + service + " to " + environment;
    }

    @Bean
    CompletionProvider deployCompletionProvider() {
        CompletionProvider environments =
                new EnumCompletionProvider(Environment.class, "--environment");

        CompletionProvider services = context -> List.of(
                new CompletionProposal("--service=api"),
                new CompletionProposal("--service=worker"));

        return new CompositeCompletionProvider(environments, services);
    }
}
```

Provider được khai báo thành bean và tham chiếu bằng tên trong `@Command`. Với cách đăng ký programmatic, có thể đặt provider bằng `Command.Builder.completionProvider(...)`.

Khi cần gợi ý phụ thuộc vào option đã nhập trước đó, provider có thể đọc `CompletionContext` để biết command option hiện tại và các từ trong buffer. Ví dụ, danh sách service có thể thay đổi theo `--environment`. Đây là điểm cải tiến so với cách completion tách riêng theo từng option của 3.x: provider cấp command có thể xem ngữ cảnh nhiều option để tạo gợi ý liên quan.

### JLine là điều kiện cho Tab completion

Tab completion trong Spring Shell phụ thuộc JLine-based shell. `SystemShellRunner` dùng Java Console và chỉ cung cấp chức năng terminal cơ bản; nó không hỗ trợ Tab completion, history và rich text như JLine. Trong Spring Shell 4, `spring-shell-core` không tự kéo JLine vào. Nếu cần completion tương tác, thêm `spring-shell-jline` hoặc starter có tích hợp JLine và chọn JLine runner.

Với non-interactive command, không có phiên REPL để người dùng nhấn Tab. Muốn completion tại Bash/Zsh, phải dùng tích hợp shell bên ngoài. Spring Shell 4 không cung cấp built-in command `completion bash` như 3.x; cần quản lý script completion theo công cụ và quy trình phân phối của ứng dụng.

## Những thay đổi API completion khi nâng cấp

| Spring Shell 3.x | Spring Shell 4.x |
| --- | --- |
| `CompletionResolver`/`ValueProvider` trong các mô hình command 3.x | `CompletionProvider` ở cấp command |
| `@ShellOption(valueProvider = ...)` trong legacy annotation model | `@Command(completionProvider = "beanName")` |
| Completion gắn riêng theo option | Provider tập trung có thể xem ngữ cảnh nhiều option |
| `@OptionValues` không phải API chung của 3.4 | `@OptionValues` đã bị loại bỏ; dùng `CompletionProvider` |
| Built-in `completion bash` tạo Bash script | Built-in command bị loại bỏ; tích hợp shell bên ngoài do ứng dụng quản lý |

Khi nâng cấp, chuyển logic gợi ý từ từng option sang provider cấp command. Không chỉ đổi tên class: cần kiểm tra cách provider đọc `CompletionContext`, cách trả `CompletionProposal` và cách đăng ký bean. Nếu ứng dụng không dùng JLine runner, provider sẽ không tạo ra trải nghiệm Tab completion trong terminal.

## Cấu hình enable/disable và thay thế built-in command

Built-in command có property enable riêng. Trong cả hai thế hệ, có thể tắt command help/history theo property tương ứng; tuy nhiên, tên và module chứa command thay đổi giữa 3.x và 4.x.

Ví dụ tắt một số command trong 3.4.x:

```yaml
spring:
  shell:
    command:
      help:
        enabled: true
      history:
        enabled: false
      stacktrace:
        enabled: true
      completion:
        enabled: true
```

Trong 4.x, command `stacktrace` và `completion` không còn để bật lại. `history` chỉ có khi JLine được đưa vào runtime classpath; có thể tắt command bằng:

```yaml
spring:
  shell:
    command:
      help:
        enabled: true
      history:
        enabled: false
```

Nếu muốn thay built-in command bằng implementation riêng, đăng ký command/bean theo cơ chế của major version đang dùng và kiểm tra `help` để tránh trùng tên. Với 4.x, command mới dùng `@Command` hoặc `Command` bean; các annotation legacy `@ShellComponent`/`@ShellMethod` đã bị loại bỏ.

## Kiểm thử bốn tính năng sau migration

Không chỉ kiểm tra code biên dịch. Hãy xác minh command có mặt trong runtime và hành vi thực tế tương ứng với runner/dependency.

| Kiểm thử | Spring Shell 3.4.x | Spring Shell 4.0.x |
| --- | --- | --- |
| Danh sách help | `help` liệt kê built-in và command nghiệp vụ | `help` liệt kê command có trong runtime; xác minh history tùy JLine |
| Help chi tiết | `help artifact publish` | `help artifact publish` và `artifact publish --help` |
| Availability | Command unavailable vẫn được hiển thị với lý do | Kiểm tra trạng thái theo command model mới |
| History command | `history` hiển thị và xuất file | Có `spring-shell-jline`; sau đó kiểm tra `history` |
| History persistence | Kiểm tra file theo `spring.shell.history.*` | Kiểm tra JLine history, quyền ghi và `spring.shell.history.*` |
| Stack trace | Gây lỗi rồi chạy `stacktrace` | Bật `spring.shell.debug.enabled=true`, gây lỗi và kiểm tra stack trace xuất hiện ngay |
| Tab completion | Dùng JLine, nhấn Tab ở command/option/value | Dùng JLine, nhấn Tab; kiểm tra `CompletionProvider` |
| Bash completion | `completion bash` tạo script | Không còn command này; kiểm tra script completion do ứng dụng phân phối |
| Core-only/System shell | Không áp dụng cho cấu hình JLine cũ | Xác nhận không kỳ vọng history/Tab completion khi không có JLine |

Các bài test nên xác minh cả output và side effect. Ví dụ, sau khi tắt `history` command, `help` không nên liệt kê nó; sau khi tắt persistence, file history không nên được cập nhật. Với completion, kiểm tra danh sách proposal trả về từ provider bằng unit test và kiểm tra Tab trong JLine integration test.

## Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `help` không hiển thị command nghiệp vụ | Command chưa được đăng ký hoặc bị ẩn | Kiểm tra component scan, registration và thuộc tính hidden |
| Command unavailable vẫn xuất hiện trong help 3.4 | Help chủ động liệt kê command chưa khả dụng | Đọc lý do availability thay vì coi đó là lỗi đăng ký |
| `help <command>` khác với `--help` sau nâng cấp | Renderer hoặc metadata command thay đổi | Kiểm tra `description`, `help`, option metadata và API 4.0.4 |
| Template help cũ không còn tác dụng | Help rendering của 4.x đã thay đổi | Rà soát cấu hình/template; khai báo help trên command hoặc viết command trợ giúp riêng |
| Không có `history` trong 4.x | Thiếu `spring-shell-jline` hoặc command bị disable | Thêm JLine module và kiểm tra `spring.shell.command.history.enabled` |
| `history` command có nhưng không ghi file | Persistence bị tắt hoặc thư mục cấu hình không ghi được | Kiểm tra `spring.shell.history.enabled`, `name` và quyền thư mục |
| Không tìm thấy `stacktrace` trong 4.x | Command đã bị loại bỏ | Bật `spring.shell.debug.enabled=true` khi cần stack trace |
| Bật `logging.level...DEBUG` nhưng không thấy stack trace command | Nhầm logger DEBUG với debug mode của shell | Dùng `spring.shell.debug.enabled` trong 4.x |
| `completion bash` không tồn tại trong 4.x | Built-in command đã bị loại bỏ | Quản lý Bash/Zsh completion script bên ngoài |
| Nhấn Tab không có gợi ý trong 4.x | Đang dùng `SystemShellRunner` hoặc thiếu JLine | Thêm `spring-shell-jline` và chọn JLine shell |
| Completion provider không được gọi | Bean name trong `@Command` sai hoặc bean chưa đăng ký | Kiểm tra `completionProvider` và Spring context |
| Provider trả gợi ý sai option | Không xét `CompletionContext` | Dựa vào command option và buffer để chọn proposal |
| History lưu cả secret | Người dùng truyền bí mật trên command line | Không nhập secret qua argument; tắt history nếu cần |

## Quy trình migration trợ giúp, history, stacktrace và completion

1. Xác định phiên bản Spring Shell và runtime classpath; kiểm tra có `spring-shell-jline` hay không.
2. Ghi lại các built-in command hiện được sử dụng bằng `help` trong bản 3.4.x.
3. Rà soát template help tùy chỉnh và chuyển nội dung hướng dẫn sang metadata command mới.
4. Xác minh history có được yêu cầu hay không; nếu có, thêm JLine module và kiểm tra path/persistence.
5. Thay quy trình `stacktrace` bằng debug mode trong 4.x; chỉ bật khi điều tra lỗi.
6. Phân loại completion đang dùng: Tab trong REPL hay script completion cho Bash.
7. Chuyển `ValueProvider`/completion resolver sang `CompletionProvider` cấp command.
8. Thay built-in `completion bash` bằng quy trình tạo/cài script completion bên ngoài nếu cần.
9. Chạy smoke test `help`, history, lỗi có stack trace và Tab completion trên đúng JLine runner.
10. Kiểm tra lại `help` và dependency tree trên artifact phát hành.

## Tài liệu tham khảo

- [Help – Spring Shell 3.4.3](https://docs.spring.io/spring-shell/reference/3.4/commands/builtin/help.html)
- [History – Spring Shell 3.4.3](https://docs.spring.io/spring-shell/reference/3.4/commands/builtin/history.html)
- [Stacktrace – Spring Shell 3.4.3](https://docs.spring.io/spring-shell/reference/3.4/commands/builtin/stacktrace.html)
- [Completion command – Spring Shell 3.4.3](https://docs.spring.io/spring-shell/reference/3.4/commands/builtin/completion.html)
- [Completion in REPL and command line – Spring Shell 3.4.3](https://docs.spring.io/spring-shell/reference/3.4/completion.html)
- [History API – Spring Shell 3.4.x](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/standard/commands/History.html)
- [ValueProvider API – Spring Shell 3.4.x](https://docs.spring.io/spring-shell/reference/3.4-SNAPSHOT/api/java/org/springframework/shell/standard/ValueProvider.html)
- [Help – Spring Shell 4.x](https://docs.spring.io/spring-shell/reference/commands/builtin/help.html)
- [Built-in commands – Spring Shell 4.x](https://docs.spring.io/spring-shell/reference/commands/builtin/index.html)
- [Command completion – Spring Shell 4.0.4](https://docs.spring.io/spring-shell/reference/commands/completion.html)
- [History API – Spring Shell 4.x JLine module](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/jline/command/History.html)
- [JLineShellAutoConfiguration API – Spring Shell 4.x](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/autoconfigure/JLineShellAutoConfiguration.html)
- [CommandHelpRenderer API – Spring Shell 4.0.4](https://docs.spring.io/spring-shell/reference/4.0-SNAPSHOT/api/org/springframework/shell/core/command/CommandHelpRenderer.html)
- [CompletionProvider API – Spring Shell 4.x](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/completion/CompletionProvider.html)
- [Spring Shell v4 migration guide](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide)

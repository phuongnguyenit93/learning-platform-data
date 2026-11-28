# Phương án cho chạy tự động khi không có khả năng tương tác

Các thành phần tương tác của Spring Shell như `StringInput`, `PathInput`, `ConfirmationInput`, `SingleItemSelector` và `MultiItemSelector` giúp người dùng nhập dữ liệu hoặc chọn giá trị ngay trên terminal. Chúng phù hợp với phiên làm việc có người dùng, nhưng có thể làm một command bị treo khi chạy trong CI/CD, cron, script hoặc tiến trình không có pseudo-terminal (PTY).

Một command dùng được trong cả hai môi trường cần có hai đường nhập dữ liệu: hỏi người dùng khi shell thật sự tương tác được, và nhận toàn bộ giá trị qua option, file cấu hình hoặc biến môi trường khi chạy tự động. Spring Shell 3.x cung cấp `ShellContext` để kiểm tra chế độ tương tác và khả năng PTY trước khi gọi một flow.

## Vì sao không thể luôn gọi ComponentFlow?

`ComponentFlow` ghép nhiều component thành một wizard. Khi gọi `flow.run()`, mỗi component chạy vòng đọc input, tạo context, render trạng thái rồi kết thúc. `StringInput` chờ nhập văn bản; `SingleItemSelector` chờ chọn một mục; `ConfirmationInput` chờ câu trả lời xác nhận.

Trong CI hoặc khi stdin/stdout được pipe, không có người dùng để nhấn phím. Nếu command vẫn gọi flow, tiến trình có thể chờ vô hạn, nhận EOF hoặc thất bại khi JLine không có terminal tương tác.

Ví dụ một lệnh triển khai có thể hỏi:

1. Chọn môi trường `dev`, `staging` hoặc `production`.
2. Nhập phiên bản cần triển khai.
3. Xác nhận có tiếp tục hay không.

Trong phiên terminal, wizard giúp thao tác nhanh. Trong pipeline, cùng thông tin phải được truyền tường minh:

```text
java -jar deploy-cli.jar deploy \
  --environment staging \
  --version 2.7.1 \
  --yes
```

Command tự động không nên tự chọn `production`, tự xác nhận thao tác nguy hiểm hoặc chờ người dùng nhập khi không có terminal.

## Phân biệt interaction mode và PTY

Spring Shell 3.x cung cấp `ShellContext` trong package `org.springframework.shell.context`. Hai thông tin quan trọng là:

| API | Ý nghĩa |
|---|---|
| `getInteractionMode()` | Cho biết shell đang ở `INTERACTIVE` hay `NONINTERACTIVE` |
| `hasPty()` | Cho biết terminal có pseudo-terminal để hỗ trợ tương tác hay không |

`InteractionMode` phản ánh chế độ chạy của shell. `hasPty()` phản ánh khả năng terminal. Khi output được pipe vào file hoặc command chạy trong CI không có terminal thật, `hasPty()` có thể trả `false`.

Đoạn mã kiểm tra `ShellContext.hasPty()` trong bài này nhắm tới Spring Shell 3.3.x/3.4.x. Nếu ứng dụng còn ở 3.2.x, kiểm tra API của minor version đó trước khi dùng; `hasPty()` chưa có trong hợp đồng `ShellContext` của dòng 3.2.x. Khi chưa có cách kiểm tra PTY tương đương, hãy yêu cầu đầu vào tường minh cho entry point tự động và không gọi component tương tác.

Vì vậy, điều kiện an toàn để gọi component tương tác là cả hai điều kiện đều đúng:

```java
ShellContext shellContext = commandContext.getShellContext();

boolean canPrompt =
        shellContext.getInteractionMode() == InteractionMode.INTERACTIVE
        && shellContext.hasPty();
```

Không chỉ kiểm tra `InteractionMode.INTERACTIVE`: một môi trường có chế độ interactive nhưng không có PTY vẫn không thể nhận thao tác bàn phím như terminal thông thường. Ngược lại, có PTY cũng không có nghĩa command đang được yêu cầu chạy theo chế độ interactive.

## Cách lấy ShellContext trong command

Trong Spring Shell 3.x, `CommandContext` có phương thức `getShellContext()`. Có thể nhận `CommandContext` trực tiếp trong method command và dùng context đó để quyết định có hiển thị wizard hay không.

```java
import org.springframework.shell.command.CommandContext;
import org.springframework.shell.context.InteractionMode;
import org.springframework.shell.context.ShellContext;

boolean canPrompt(CommandContext commandContext) {
    ShellContext shellContext = commandContext.getShellContext();
    return shellContext.getInteractionMode() == InteractionMode.INTERACTIVE
            && shellContext.hasPty();
}
```

Đặt phép kiểm tra này ở ranh giới command hoặc một helper dùng chung. Service nghiệp vụ không nên phụ thuộc `ShellContext`, `Terminal` hoặc `ComponentFlow`; service chỉ nhận dữ liệu đã được thu thập và xác thực.

## Ánh xạ component sang đầu vào tự động

Mỗi component tương tác nên có một cách biểu diễn tương đương trong command line hoặc cấu hình:

| Component tương tác | Dữ liệu người dùng nhập/chọn | Phương án cho script/CI |
|---|---|---|
| `StringInput` | Tên, phiên bản, nhãn | Option như `--version 2.7.1` |
| `PathInput` | Đường dẫn file/thư mục | Option như `--config config/staging.yml` |
| `ConfirmationInput` | Yes/No | Cờ tường minh như `--yes` hoặc `--confirm` |
| `SingleItemSelector` | Chọn một môi trường/tài nguyên | Option như `--environment staging`; kiểm tra bằng enum/allowlist |
| `MultiItemSelector` | Chọn nhiều tính năng/tài nguyên | Option dạng danh sách hoặc file cấu hình |
| Nhập bí mật | Mật khẩu/token | Biến môi trường, secret store hoặc file secret có quyền truy cập giới hạn |

Giữ cùng một mô hình dữ liệu ở cả hai đường nhập. Sau khi thu thập giá trị, gọi cùng một validator và cùng service nghiệp vụ. Không để nhánh interactive bỏ qua validation vì component đã hiển thị danh sách lựa chọn.

## Đặt option ở trạng thái optional để có thể hỏi trong phiên tương tác

Nếu option bắt buộc ở parser, command sẽ bị từ chối trước khi method được gọi; khi đó method không có cơ hội mở wizard để hỏi giá trị còn thiếu. Với command hỗ trợ cả hai chế độ, khai báo các giá trị có thể hỏi là optional, sau đó kiểm tra và xử lý trong method.

Trong annotation legacy của Spring Shell 3.x, dùng `ShellOption.NULL` để biểu diễn giá trị mặc định là `null`:

```java
import org.springframework.shell.standard.ShellMethod;
import org.springframework.shell.standard.ShellOption;

@ShellMethod(key = "deploy")
public String deploy(
        @ShellOption(value = "environment", defaultValue = ShellOption.NULL)
        String environment,
        @ShellOption(value = "version", defaultValue = ShellOption.NULL)
        String version) {
    // Thu thập giá trị thiếu trong interactive mode hoặc báo lỗi rõ ràng.
}
```

`ShellOption.NULL` khác với việc không khai báo default: nó cho biết option có thể vắng mặt và tham số nhận `null`. Sau đó, command có thể chọn wizard hoặc yêu cầu người gọi truyền đủ option.

## Xây dựng flow chỉ khi terminal hỗ trợ tương tác

Ví dụ dưới đây dùng Spring Shell 3.3.x và `ComponentFlow.Builder`. Flow có một selector cho môi trường và một input cho phiên bản. Nếu command line đã truyền một giá trị, flow chỉ hỏi những giá trị còn thiếu.

```java
import java.util.Map;

import org.springframework.shell.component.context.ComponentContext;
import org.springframework.shell.component.flow.ComponentFlow;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;

@Component
class DeploymentPrompt {

    private final ComponentFlow.Builder componentFlowBuilder;

    DeploymentPrompt(ComponentFlow.Builder componentFlowBuilder) {
        this.componentFlowBuilder = componentFlowBuilder;
    }

    DeploymentOptions collectMissing(
            String environment,
            String version,
            boolean askConfirmation) {

        ComponentFlow.Builder builder = componentFlowBuilder.clone().reset();

        if (!StringUtils.hasText(environment)) {
            builder.withSingleItemSelector("environment")
                    .name("Môi trường")
                    .selectItems(Map.of(
                            "dev", "dev",
                            "staging", "staging",
                            "production", "production"))
                    .and();
        }

        if (!StringUtils.hasText(version)) {
            builder.withStringInput("version")
                    .name("Phiên bản")
                    .and();
        }

        if (askConfirmation) {
            builder.withConfirmationInput("confirm")
                    .name("Xác nhận triển khai?")
                    .defaultValue(false)
                    .and();
        }

        ComponentContext<?> values = builder.build().run().getContext();

        String selectedEnvironment = StringUtils.hasText(environment)
                ? environment
                : values.get("environment", String.class);

        String selectedVersion = StringUtils.hasText(version)
                ? version
                : values.get("version", String.class);

        boolean confirmed = !askConfirmation
                || Boolean.TRUE.equals(values.get("confirm", Boolean.class));

        return new DeploymentOptions(
                selectedEnvironment, selectedVersion, confirmed);
    }
}

record DeploymentOptions(
        String environment,
        String version,
        boolean confirmed) {
}
```

`ComponentFlow.Builder` được clone và reset cho mỗi lần chạy để không dùng lại cấu hình của flow trước. Kết quả `flow.run()` cung cấp `ComponentFlowResult`; `getContext()` trả về `ComponentContext`, có thể đọc giá trị theo key và kiểu dữ liệu.

Trong ví dụ, `defaultValue(false)` làm lựa chọn ban đầu của confirmation là `false`. Nó không tự bỏ qua prompt. Tương tự, `defaultSelect(...)` trên selector chỉ đặt trước lựa chọn để người dùng xác nhận trong giao diện. Muốn tự động hóa, hãy bỏ qua cả flow khi không có khả năng tương tác và dùng option đã truyền.

## Hoàn chỉnh command cho cả terminal và CI

Command sau minh họa cách kết hợp option, kiểm tra `ShellContext`, wizard và cờ `--yes`. Nhánh non-interactive không gọi `ComponentFlow.run()`.

```java
import org.springframework.shell.command.CommandContext;
import org.springframework.shell.context.InteractionMode;
import org.springframework.shell.context.ShellContext;
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;
import org.springframework.shell.standard.ShellOption;
import org.springframework.util.StringUtils;

@ShellComponent
class DeploymentCommands {

    private final DeploymentPrompt deploymentPrompt;
    private final DeploymentService deploymentService;

    DeploymentCommands(
            DeploymentPrompt deploymentPrompt,
            DeploymentService deploymentService) {
        this.deploymentPrompt = deploymentPrompt;
        this.deploymentService = deploymentService;
    }

    @ShellMethod(key = "deploy", value = "Triển khai một phiên bản dịch vụ")
    public String deploy(
            @ShellOption(value = "environment", defaultValue = ShellOption.NULL)
            String environment,
            @ShellOption(value = "version", defaultValue = ShellOption.NULL)
            String version,
            @ShellOption(value = "yes", defaultValue = "false")
            boolean yes,
            CommandContext commandContext) {

        ShellContext shellContext = commandContext.getShellContext();
        boolean canPrompt =
                shellContext.getInteractionMode() == InteractionMode.INTERACTIVE
                && shellContext.hasPty();

        boolean missingValues = !StringUtils.hasText(environment)
                || !StringUtils.hasText(version);
        boolean needsConfirmation = !yes;

        if ((missingValues || needsConfirmation) && !canPrompt) {
            throw new IllegalArgumentException(
                    "Chạy tự động cần truyền --environment, --version và --yes. "
                    + "Ví dụ: deploy --environment staging --version 2.7.1 --yes");
        }

        if (missingValues || needsConfirmation) {
            DeploymentOptions options = deploymentPrompt.collectMissing(
                    environment, version, needsConfirmation);
            environment = options.environment();
            version = options.version();

            if (!options.confirmed()) {
                return "Đã hủy triển khai theo lựa chọn của người dùng.";
            }
        }

        if (!StringUtils.hasText(environment) || !StringUtils.hasText(version)) {
            throw new IllegalArgumentException(
                    "Môi trường và phiên bản là bắt buộc.");
        }

        deploymentService.deploy(environment, version);
        return "Đã gửi yêu cầu triển khai " + version + " lên " + environment;
    }
}
```

Trong ví dụ này, người dùng interactive có thể bỏ option để được hỏi; nếu truyền sẵn một số option, flow chỉ hỏi phần còn thiếu và confirmation. Khi không có PTY hoặc shell đang ở `NONINTERACTIVE`, command yêu cầu đủ ba giá trị tường minh.

`--yes` chỉ xác nhận rằng caller muốn bỏ qua prompt xác nhận. Nó không thay thế kiểm tra quyền, validation, precondition hoặc policy bảo vệ production. `DeploymentService` vẫn phải kiểm tra người gọi có quyền triển khai môi trường đã chọn và phiên bản có hợp lệ hay không.

## Cách gọi trong script và CI/CD

Với non-interactive runner, truyền tất cả giá trị cần thiết ngay trên command line:

```bash
java -jar deploy-cli.jar deploy \
  --environment staging \
  --version 2.7.1 \
  --yes
```

Với Spring Shell 3.3.x, chỉ `NonInteractiveShellRunner` được bật mặc định. Nếu cần dùng script file dạng `@file`, bật script runner bằng property:

```yaml
spring:
  shell:
    noninteractive:
      enabled: true
    script:
      enabled: true
```

Ví dụ `release.shell`:

```text
deploy --environment staging --version 2.7.1 --yes
deployment-verify --environment staging --version 2.7.1
```

Chạy file:

```bash
java -jar deploy-cli.jar @release.shell
```

Không bật interactive runner trong profile CI nếu pipeline không cần REPL. Từ Spring Shell 3.3.x, các runner interactive và script không còn bật mặc định; các phiên bản đến 3.2.x có mặc định khác. Hãy cấu hình runner theo version và mục đích triển khai.

## Dùng file cấu hình cho nhiều tham số

Khi command cần nhiều lựa chọn, truyền từng option có thể dài và dễ sai. Có thể cung cấp `--config` trỏ tới file YAML/JSON chứa cấu hình đã được kiểm tra:

```yaml
environment: staging
version: 2.7.1
replicas: 3
region: ap-southeast-1
```

Lệnh tự động:

```text
deploy --config config/staging-release.yml --yes
```

Quy định rõ thứ tự ưu tiên khi một giá trị xuất hiện ở nhiều nơi, ví dụ: option CLI ghi đè file cấu hình, file cấu hình ghi đè giá trị mặc định an toàn. Validate toàn bộ cấu hình sau khi hợp nhất và trước khi tạo side effect.

Với thông tin bí mật, ưu tiên biến môi trường được CI secret store cấp hoặc secret manager. Không đưa token, mật khẩu hoặc private key trực tiếp vào command line vì có thể xuất hiện trong process list, shell history hoặc log pipeline.

## Chọn default an toàn

Default có thể giúp người dùng nhập nhanh, nhưng không phải default nào cũng phù hợp cho automation:

| Dữ liệu | Default phù hợp khi | Khi không nên tự chọn |
|---|---|---|
| Tên profile | Có profile mặc định được tài liệu hóa như `dev` | Tác vụ có thể tác động nhiều tenant/environment |
| Môi trường | Ứng dụng chỉ quản lý một môi trường được cố định bởi cấu hình | Có cả staging và production |
| Phiên bản | Lấy từ artifact/version metadata đã xác định | Người dùng phải chọn release cụ thể |
| Đường dẫn config | Có file mặc định rõ ràng trong package | File có thể chứa quyền hoặc cấu hình khác nhau |
| Xác nhận | Thao tác đọc hoặc không gây side effect | Xóa dữ liệu, triển khai production, rotate credential |

Với thao tác nguy hiểm, không đặt `defaultValue(true)` cho confirmation. Nếu automation cần xác nhận, yêu cầu `--yes` rõ ràng hoặc một giá trị xác nhận gắn với mục tiêu, chẳng hạn `--confirm-environment production`. Cờ này vẫn không thay thế authorization.

## Phân biệt command chỉ dành cho interactive và command hỗ trợ cả hai

`@ShellMethod` có thuộc tính `interactionMode` với các giá trị `ALL`, `INTERACTIVE` và `NONINTERACTIVE`:

- Dùng `INTERACTIVE` cho command chỉ có ý nghĩa khi có phiên REPL, ví dụ mở một màn hình chọn lựa liên tục.
- Dùng `NONINTERACTIVE` cho command chỉ nhận tham số và kết thúc, phù hợp với script/CI.
- Giữ `ALL` cho command có cả hai đường nhập như ví dụ `deploy` ở trên.

`interactionMode` điều khiển command có khả dụng trong chế độ shell nào; nó không tự biến `ComponentFlow` thành non-interactive và không tự điền các tham số còn thiếu.

## Kiểm thử cả hai đường chạy

Không chỉ kiểm tra flow hiển thị đúng trong terminal. Cần kiểm tra command không cố đọc bàn phím khi chạy non-interactive.

### Kiểm thử nhánh non-interactive

Spring Shell test support cung cấp `ShellTestClient.nonInterative(...)` để chạy command không tương tác. Tên method trong API 3.x có cách viết `nonInterative`:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.shell.test.ShellAssertions;
import org.springframework.shell.test.ShellTestClient;
import org.springframework.shell.test.autoconfigure.ShellTest;

@ShellTest
class DeploymentNonInteractiveTests {

    @Autowired
    ShellTestClient client;

    @Test
    void deployUsesExplicitArgumentsWithoutPrompting() {
        var session = client.nonInterative(
                "deploy --environment staging --version 2.7.1 --yes").run();

        ShellAssertions.assertThat(session.screen())
                .containsText("Đã gửi yêu cầu triển khai 2.7.1 lên staging");
    }

    @Test
    void deployExplainsMissingArguments() {
        var session = client.nonInterative("deploy").run();

        ShellAssertions.assertThat(session.screen())
                .containsText("Chạy tự động cần truyền");
    }
}
```

Test đầu xác nhận command chạy được khi truyền đủ tham số. Test thứ hai xác nhận thiếu tham số thì command trả thông báo có hướng dẫn, không chờ prompt.

Trong Spring Shell 3.4.2 trở lên, `nonInterative(...)` đã deprecated và được thay bằng `nonInteractive(...)`; dùng tên mới khi dự án đã nâng lên phiên bản đó.

### Kiểm thử nhánh interactive

Spring Shell test support cũng có `client.interactive().run()` và cho phép gửi phím vào session. Dùng test này để xác nhận flow xuất hiện, giá trị được chọn/nhập được chuyển về command và confirmation mặc định là từ chối.

```java
import static org.awaitility.Awaitility.await;

import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.shell.test.ShellAssertions;
import org.springframework.shell.test.ShellTestClient;
import org.springframework.shell.test.autoconfigure.ShellTest;

@ShellTest
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class DeploymentInteractiveTests {

    @Autowired
    ShellTestClient client;

    @Test
    void commandOpensItsFlowInAnInteractiveSession() {
        var session = client.interactive().run();
        session.write(session.writeSequence()
                .text("deploy")
                .carriageReturn()
                .build());

        await().atMost(2, TimeUnit.SECONDS).untilAsserted(() ->
                ShellAssertions.assertThat(session.screen()).containsText("Môi trường"));
    }
}
```

Test minh họa cách khởi động phiên interactive. Với flow cụ thể, bổ sung các chuỗi phím chọn môi trường, nhập phiên bản, xác nhận và kiểm tra kết quả command. Dùng `@DirtiesContext` nếu test tạo phiên shell có vòng đời dài để tránh ảnh hưởng test khác.

### Ma trận test cần có

| Chế độ | Đầu vào | Kết quả mong đợi |
|---|---|---|
| Interactive + PTY | Thiếu environment/version | Flow hỏi phần còn thiếu |
| Interactive + PTY | Có đủ option, chưa có `--yes` | Flow hỏi xác nhận; mặc định là không |
| Interactive + PTY | Người dùng từ chối | Không gọi service triển khai |
| Non-interactive | Đủ option và `--yes` | Command chạy mà không gọi component |
| Non-interactive | Thiếu environment | Báo option bắt buộc và ví dụ cách gọi |
| Non-interactive | Thiếu `--yes` | Báo cần xác nhận tường minh |
| Interactive mode nhưng không có PTY | Thiếu tham số | Không mở flow; trả lỗi hướng dẫn |
| Script runner | Script có đủ option | Mỗi command chạy không cần prompt |
| Giá trị không hợp lệ | Environment ngoài allowlist | Validation từ chối ở cả hai chế độ |
| Thiếu quyền | Người gọi không được triển khai production | Authorization từ chối kể cả khi có `--yes` |

## Lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| CI treo ở prompt | Command gọi `ComponentFlow.run()` dù không có PTY | Kiểm tra cả `InteractionMode` và `hasPty()` trước khi chạy flow |
| `defaultValue` được đặt nhưng CI vẫn chờ | Default chỉ là giá trị ban đầu của component | Dùng option/config để bỏ qua flow trong non-interactive mode |
| Selector có `defaultSelect` nhưng vẫn chờ Enter | Mục chỉ được chọn trước, component vẫn tương tác | Dùng option `--environment` khi tự động |
| Parser từ chối trước khi method chạy | Option được khai báo required dù muốn hỏi trong interactive mode | Khai báo optional/null, rồi kiểm tra trong command |
| CI triển khai nhầm môi trường | Command tự chọn default nguy hiểm | Yêu cầu `--environment` rõ ràng và validate allowlist |
| `--yes` làm bỏ qua cả kiểm tra quyền | Gộp xác nhận UI với authorization | Chỉ bỏ qua prompt; vẫn chạy policy và authorization |
| Script runner không nhận `@file` | `spring.shell.script.enabled` chưa bật trong 3.3.x | Bật script runner trong profile phù hợp |
| Test interactive ảnh hưởng test sau | Session shell còn chạy hoặc context được tái sử dụng | Đóng session/đánh dấu `@DirtiesContext` theo test support |
| Flow dùng lại input từ lần trước | Dùng chung builder đã có cấu hình | Clone và reset builder trước mỗi flow |

## Quy trình thiết kế command có interactive fallback

1. Liệt kê tất cả giá trị mà wizard đang hỏi hoặc cho người dùng chọn.
2. Tạo option tương ứng cho từng giá trị; dùng file cấu hình cho bộ tham số lớn.
3. Khai báo option có thể được hỏi là optional để command method nhận được quyền quyết định.
4. Đọc `CommandContext.getShellContext()` và kiểm tra `INTERACTIVE` cùng `hasPty()`.
5. Chỉ gọi `ComponentFlow.run()` khi cả hai điều kiện cho phép tương tác.
6. Nếu non-interactive, yêu cầu đủ tham số và trả lỗi có ví dụ nếu còn thiếu.
7. Dùng `--yes` hoặc cờ xác nhận rõ ràng cho thao tác có side effect; không tự xác nhận bằng default.
8. Validate dữ liệu và authorization giống nhau ở cả hai đường nhập.
9. Giữ service nghiệp vụ độc lập với component/terminal.
10. Kiểm thử interactive, non-interactive, không có PTY, script và dữ liệu không hợp lệ.

Thiết kế này giữ trải nghiệm wizard thuận tiện khi có người dùng và giúp command chạy ổn định trong pipeline. Phần nghiệp vụ nhận cùng một request đã xác thực, bất kể dữ liệu đến từ component tương tác, option CLI, file cấu hình hay biến môi trường.

## Tài liệu tham khảo

- [Spring Shell 3.3.4 — Execution](https://docs.spring.io/spring-shell/reference/3.3/execution.html): phân biệt interactive/non-interactive mode và các runner; từ 3.3.x chỉ non-interactive runner được bật mặc định.
- [Spring Shell 3.3.0 API — ShellContext](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/context/ShellContext.html): `getInteractionMode()` và `hasPty()`.
- [Spring Shell 3.3.0 API — CommandContext](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/command/CommandContext.html): lấy `ShellContext` bằng `getShellContext()`.
- [Spring Shell 3.3.4 — Flow](https://docs.spring.io/spring-shell/reference/3.3/components/flow/index.html): ghép nhiều component thành `ComponentFlow` và chạy flow.
- [Spring Shell 3.3.0 API — ComponentFlow.Builder](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/flow/ComponentFlow.Builder.html): builder cho string, path, confirmation, single selector và multi selector.
- [Spring Shell 3.3.0 API — ComponentFlowResult](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/flow/ComponentFlow.ComponentFlowResult.html): lấy context kết quả qua `getContext()`.
- [Spring Shell 3.3.0 API — ComponentContext](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/context/BaseComponentContext.html): đọc giá trị theo key và kiểu dữ liệu.
- [Spring Shell 3.3.0 API — StringInputSpec](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/flow/StringInputSpec.html): cấu hình input văn bản và default value.
- [Spring Shell 3.3.0 API — ConfirmationInputSpec](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/flow/ConfirmationInputSpec.html): cấu hình xác nhận và giá trị mặc định.
- [Spring Shell 3.3.0 API — SingleItemSelectorSpec](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/component/flow/SingleItemSelectorSpec.html): danh sách lựa chọn và `defaultSelect`.
- [Spring Shell 3.3.0 API — ShellMethod](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/standard/ShellMethod.html): thuộc tính `interactionMode` của command annotation.
- [Spring Shell 3.3.0 API — ShellTestClient](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/test/ShellTestClient.html): phiên kiểm thử interactive và non-interactive.
- [Spring Shell 3.4.1 — Optional Value](https://docs.spring.io/spring-shell/reference/3.4/options/optional.html): khai báo option optional và dùng `ShellOption.NULL` trong annotation legacy.
- [Spring Shell 3.4.1 — Testing Basics](https://docs.spring.io/spring-shell/reference/testing/basics.html): kiểm thử interactive và non-interactive bằng `ShellTestClient`.

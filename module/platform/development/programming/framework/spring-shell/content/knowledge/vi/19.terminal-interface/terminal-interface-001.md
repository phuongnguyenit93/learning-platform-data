# Prompt và thông tin ngữ cảnh nên hiển thị

## 1. Prompt giúp người dùng biết mình đang thao tác ở đâu

Prompt là phần văn bản xuất hiện trước vị trí nhập command. Nó nhắc người dùng rằng shell đang chờ lệnh và có thể hiển thị một số thông tin ngữ cảnh quan trọng của phiên làm việc.

Prompt mặc định của Spring Shell có dạng:

~~~text
shell:>
~~~

Với ứng dụng quản trị, prompt có thể hữu ích hơn nếu cho biết môi trường hiện tại và trạng thái kết nối:

~~~text
[development | connected] admin:>
~~~

Hoặc khi chuyển sang môi trường production:

~~~text
[production | connected] admin:>
~~~

Người vận hành nhìn thấy ngay môi trường đang chọn trước khi chạy một command có tác động đến dữ liệu. Prompt nên ngắn, ổn định và chỉ hiển thị những thông tin giúp tránh thao tác nhầm.

## 2. Nên hiển thị thông tin nào?

Chọn thông tin theo công việc mà CLI hỗ trợ. Một prompt quản trị thường chỉ cần một vài thành phần:

| Thông tin | Ví dụ | Khi nào hữu ích? |
|---|---|---|
| Tên ứng dụng hoặc vai trò | `admin` | Khi một terminal có thể mở nhiều công cụ CLI. |
| Môi trường đang chọn | `development`, `staging`, `production` | Khi command có thể tác động đến nhiều môi trường. |
| Workspace hoặc project | `billing`, `catalog` | Khi người dùng làm việc với nhiều project. |
| Trạng thái kết nối | `connected`, `offline` | Khi command phụ thuộc vào phiên kết nối. |
| Người dùng hoặc tenant dạng rút gọn | `operator`, `team-a` | Khi cần phân biệt ngữ cảnh thao tác và thông tin này được phép hiển thị. |

Không cần đưa mọi thông tin vào prompt. Nếu một thông tin dài, thay đổi liên tục hoặc chỉ hữu ích trong một số tình huống, hãy hiển thị nó bằng command `status`, `context` hoặc `whoami`.

Ví dụ một prompt ngắn:

~~~text
[prod | billing | connected] admin:>
~~~

Thông tin chi tiết có thể xem bằng command:

~~~text
admin:>context show
User: operator
Environment: production
Workspace: billing
Connection: connected
Last checked: 2026-11-26T14:20:00Z
~~~

Prompt và command xem ngữ cảnh bổ sung cho nhau: prompt hiển thị tín hiệu quan trọng ngay tại nơi nhập lệnh; command trạng thái cung cấp chi tiết khi người dùng cần kiểm tra.

## 3. Tùy chỉnh prompt bằng PromptProvider trong Spring Shell 4.x

Khi sử dụng shell dựa trên JLine, Spring Shell cho phép tùy chỉnh prompt bằng cách triển khai `PromptProvider` trong package `org.springframework.shell.jline`.

Interface này có phương thức:

~~~java
org.jline.utils.AttributedString getPrompt();
~~~

`getPrompt()` được gọi ở mỗi chu kỳ REPL để quyết định prompt cần hiển thị. Vì vậy, prompt có thể thay đổi theo trạng thái phiên làm việc sau mỗi command.

Ví dụ đơn giản:

~~~java
import org.jline.utils.AttributedString;
import org.jline.utils.AttributedStyle;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.jline.PromptProvider;

@Configuration
public class ShellPromptConfiguration {

    @Bean
    PromptProvider promptProvider() {
        return () -> new AttributedString(
                "admin:>",
                AttributedStyle.DEFAULT.foreground(AttributedStyle.YELLOW));
    }
}
~~~

Bean `PromptProvider` thay thế prompt mặc định do JLine auto-configuration cung cấp. Spring Shell 4.x chỉ tạo prompt provider mặc định khi application context chưa có bean `PromptProvider` nào khác.

`AttributedString` là kiểu của JLine, cho phép gắn style như màu chữ. Nên dùng API này thay vì tự nối mã ANSI vào chuỗi prompt; JLine quản lý việc hiển thị thuộc tính trên terminal.

## 4. Tạo prompt động từ ngữ cảnh phiên làm việc

Trong ứng dụng thực tế, prompt thường lấy thông tin từ một service giữ ngữ cảnh hiện tại. Ví dụ service dưới đây lưu môi trường, workspace và trạng thái kết nối bằng một snapshot bất biến:

~~~java
package com.example.cli;

import java.util.concurrent.atomic.AtomicReference;

import org.springframework.stereotype.Component;

@Component
public class ShellSessionContext {

    private final AtomicReference<Snapshot> current =
            new AtomicReference<>(new Snapshot("development", "default", false));

    public Snapshot snapshot() {
        return current.get();
    }

    public void selectEnvironment(String environment) {
        current.updateAndGet(old ->
                new Snapshot(environment, old.workspace(), old.connected()));
    }

    public void selectWorkspace(String workspace) {
        current.updateAndGet(old ->
                new Snapshot(old.environment(), workspace, old.connected()));
    }

    public void setConnected(boolean connected) {
        current.updateAndGet(old ->
                new Snapshot(old.environment(), old.workspace(), connected));
    }

    public record Snapshot(
            String environment,
            String workspace,
            boolean connected) {
    }
}
~~~

`AtomicReference` giúp việc thay thế snapshot an toàn khi trạng thái được cập nhật từ nhiều luồng. Mỗi lần thay đổi, service tạo snapshot mới thay vì sửa từng trường trên một object đang được prompt đọc.

Tạo `PromptProvider` sử dụng snapshot đó:

Ví dụ dưới đây là phiên bản mở rộng thay cho bean `promptProvider()` đơn giản ở phần trước; trong ứng dụng chỉ đăng ký một bean `PromptProvider`.

~~~java
package com.example.cli;

import org.jline.utils.AttributedString;
import org.jline.utils.AttributedStyle;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.jline.PromptProvider;

@Configuration
public class ShellPromptConfiguration {

    @Bean
    PromptProvider promptProvider(ShellSessionContext sessionContext) {
        return () -> {
            ShellSessionContext.Snapshot state = sessionContext.snapshot();

            String connection = state.connected() ? "connected" : "offline";
            String prompt = "[" + state.environment()
                    + " | " + state.workspace()
                    + " | " + connection + "] admin:> ";

            AttributedStyle style = state.connected()
                    ? AttributedStyle.DEFAULT.foreground(AttributedStyle.GREEN)
                    : AttributedStyle.DEFAULT.foreground(AttributedStyle.YELLOW);

            return new AttributedString(prompt, style);
        };
    }
}
~~~

Khi trạng thái ban đầu chưa kết nối, prompt có thể là:

~~~text
[development | default | offline] admin:>
~~~

Sau khi command kết nối thành công gọi `sessionContext.setConnected(true)`, prompt ở chu kỳ REPL tiếp theo sẽ là:

~~~text
[development | default | connected] admin:>
~~~

Trong ví dụ, màu vàng biểu thị trạng thái chưa kết nối và màu xanh biểu thị đã kết nối. Màu sắc chỉ là tín hiệu bổ sung; nội dung `connected` hoặc `offline` vẫn phải đủ rõ khi terminal không hiển thị màu.

## 5. Cập nhật ngữ cảnh khi người dùng chuyển môi trường

Prompt động chỉ hữu ích nếu các command cập nhật đúng trạng thái dùng chung. Ví dụ command chuyển môi trường:

~~~java
package com.example.cli;

import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
public class EnvironmentCommands {

    private final ShellSessionContext sessionContext;
    private final EnvironmentService environmentService;

    public EnvironmentCommands(
            ShellSessionContext sessionContext,
            EnvironmentService environmentService) {
        this.sessionContext = sessionContext;
        this.environmentService = environmentService;
    }

    @Command(name = "environment use", description = "Chọn môi trường làm việc")
    public String use(
            @Option(longName = "name", required = true) String name) {

        environmentService.validateAndSelect(name);
        sessionContext.selectEnvironment(name);
        return "Đã chuyển sang môi trường " + name;
    }
}
~~~

`EnvironmentService` là service nghiệp vụ của ứng dụng ví dụ. Chỉ cập nhật `ShellSessionContext` sau khi việc chọn môi trường thành công. Nếu command từ chối môi trường, prompt phải tiếp tục hiển thị môi trường đang hoạt động trước đó.

Ví dụ phiên làm việc:

~~~text
[development | default | connected] admin:>environment use --name=staging
Đã chuyển sang môi trường staging
[staging | default | connected] admin:>
~~~

Điều này giúp người dùng xác nhận ngữ cảnh mới ngay sau khi command hoàn tất.

## 6. PromptProvider chỉ áp dụng cho JLine-based shell

`PromptProvider` thuộc package `org.springframework.shell.jline` và trả về kiểu `AttributedString` của JLine. Nó được sử dụng bởi `JLineInputProvider` trong shell tương tác dựa trên JLine.

Vì vậy:

- Khi ứng dụng có JLine integration và chạy interactive mode, bean `PromptProvider` tùy chỉnh sẽ quyết định prompt.
- Khi ứng dụng dùng `SystemShellRunner` dựa trên `java.io.Console` mà không có JLine, `PromptProvider` không điều khiển prompt của runner đó.
- Trong non-interactive mode, runner nhận command hoặc script rồi kết thúc, không có chu kỳ REPL để hiển thị prompt.

Nếu muốn dùng `PromptProvider`, hãy bảo đảm module `spring-shell-jline` có trên classpath. Nếu starter của dự án đã đưa module này vào, không cần thêm dependency trùng lặp. Khi cần shell tương tác tối giản không dùng JLine, hãy chấp nhận prompt mặc định của `SystemShellRunner` hoặc tự tổ chức lớp nhập liệu phù hợp với kiến trúc ứng dụng.

## 7. Phân biệt prompt với output và thông tin trạng thái

Prompt chỉ là phần dẫn trước dòng nhập lệnh. Không nên dùng nó để hiển thị toàn bộ log, tiến trình dài hoặc thông báo nghiệp vụ.

| Thành phần | Nên dùng cho | Ví dụ |
|---|---|---|
| Prompt | Ngữ cảnh ngắn cần thấy trước mỗi command | `[staging | connected] admin:>` |
| Output command | Kết quả của thao tác vừa chạy | `Đã cập nhật cấu hình` |
| Command trạng thái | Thông tin chi tiết có thể thay đổi | `context show`, `system status` |
| Log | Chẩn đoán kỹ thuật và lịch sử sự kiện | Lỗi kết nối, thời gian phản hồi, stack trace |

Nếu một command cần hiển thị nhiều dòng, dùng `CommandContext.outputWriter()` để ghi output do shell quản lý. Nếu thông tin trạng thái quá dài, hãy đặt trong command riêng để người dùng chủ động yêu cầu.

## 8. Những nguyên tắc thiết kế prompt dễ sử dụng

**Giữ prompt ngắn.** Một dòng khoảng vài chục ký tự thường dễ đọc hơn một prompt dài chứa nhiều thuộc tính. Đưa thông tin ít dùng vào command `context show`.

**Đặt môi trường ở vị trí dễ thấy.** Nếu command có thể thay đổi dữ liệu production, hiển thị tên môi trường ngay đầu prompt. Có thể dùng màu cảnh báo cho production, nhưng luôn giữ chữ `production` để không phụ thuộc vào khả năng phân biệt màu.

**Dùng trạng thái có ý nghĩa.** `connected`, `offline`, `read-only` hoặc `expired` dễ hiểu hơn một ký hiệu không có giải thích.

**Cập nhật sau khi thao tác thành công.** Command chuyển môi trường hoặc kết nối cần cập nhật service ngữ cảnh sau khi xác nhận thao tác đã hoàn tất.

**Không gọi mạng trong getPrompt().** `getPrompt()` được gọi mỗi chu kỳ REPL. Hãy đọc snapshot trong bộ nhớ hoặc cache nhanh; không truy vấn server từ xa hoặc database chậm mỗi lần prompt xuất hiện.

**Không coi prompt là nguồn xác thực.** Trạng thái hiển thị có thể cũ ngay sau khi được tạo. Service vẫn phải kiểm tra lại quyền, môi trường và trạng thái kết nối trước thao tác quan trọng.

**Không hiển thị bí mật.** Không đưa mật khẩu, access token, refresh token, private key, chuỗi kết nối hoặc dữ liệu cá nhân nhạy cảm vào prompt. Prompt có thể xuất hiện trong ảnh chụp terminal, bản ghi phiên hoặc log hỗ trợ.

## 9. TerminalCustomizer có vai trò khác PromptProvider

Spring Shell 4.x còn cung cấp `TerminalCustomizer` trong package `org.springframework.shell.core.autoconfigure`. Đây là callback cho phép tùy chỉnh `TerminalBuilder` của JLine trước khi terminal được tạo.

Phân biệt hai extension point:

- `PromptProvider` quyết định nội dung và style của prompt ở mỗi chu kỳ REPL.
- `TerminalCustomizer` tùy chỉnh cấu hình tạo terminal, chẳng hạn các thuộc tính terminal builder.

Không dùng `TerminalCustomizer` chỉ để đổi chữ prompt. Với yêu cầu thay đổi prompt, `PromptProvider` là API đúng mục đích.

## 10. Kiểm thử prompt và trạng thái ngữ cảnh

Nên kiểm thử provider như một thành phần riêng và kiểm thử trải nghiệm trong terminal tương tác.

Các trường hợp cần xác nhận:

1. Prompt ban đầu hiển thị đúng môi trường và workspace mặc định.
2. Khi trạng thái kết nối đổi từ `offline` sang `connected`, prompt ở chu kỳ tiếp theo phản ánh trạng thái mới.
3. Khi người dùng chuyển môi trường thành công, prompt hiển thị môi trường mới.
4. Khi command chuyển môi trường thất bại, prompt vẫn giữ môi trường cũ.
5. Prompt không gọi service mạng hoặc truy vấn dữ liệu chậm mỗi lần `getPrompt()` chạy.
6. Prompt vẫn có ý nghĩa khi màu terminal không được hỗ trợ.
7. Không có token, mật khẩu hoặc dữ liệu nhạy cảm trong nội dung prompt.
8. Kiểm tra riêng JLine interactive, SystemShellRunner và non-interactive mode để xác nhận đúng phạm vi áp dụng.

Ví dụ kiểm thử đơn vị cho nội dung prompt:

~~~java
package com.example.cli;

import org.jline.utils.AttributedString;
import org.springframework.shell.jline.PromptProvider;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

@Test
void promptShouldShowCurrentEnvironmentAndConnection() {
    ShellSessionContext context = new ShellSessionContext();
    context.selectEnvironment("staging");
    context.setConnected(true);

    PromptProvider provider = () -> {
        ShellSessionContext.Snapshot state = context.snapshot();
        return new AttributedString("[" + state.environment()
                + " | " + (state.connected() ? "connected" : "offline")
                + "] admin:>");
    };

    assertThat(provider.getPrompt().toString())
            .contains("staging", "connected");
}
~~~

Đoạn test minh họa nguyên tắc kiểm tra nội dung không phụ thuộc mã màu. Trong project thực tế, nên đưa logic tạo prompt vào một class riêng để unit test trực tiếp và dùng đúng bean `PromptProvider` mà ứng dụng đăng ký.

## 11. Quy trình triển khai prompt có ngữ cảnh

1. Xác định thông tin nào giúp người dùng tránh thao tác nhầm.
2. Chọn một định dạng prompt ngắn, dễ đọc và có thể hiểu khi không có màu.
3. Tạo service giữ snapshot ngữ cảnh của phiên shell.
4. Đăng ký bean `PromptProvider` nếu ứng dụng dùng JLine-based shell.
5. Cập nhật snapshot sau khi command chuyển môi trường, workspace hoặc trạng thái kết nối thành công.
6. Giữ `getPrompt()` nhanh, chỉ đọc và không có tác dụng phụ.
7. Hiển thị chi tiết qua command trạng thái thay vì kéo dài prompt.
8. Kiểm thử các lần chuyển trạng thái và phạm vi runner.

## Kết luận

Prompt tốt cho người dùng biết nhanh ứng dụng đang ở môi trường, workspace và trạng thái nào. Trong Spring Shell 4.x chạy với JLine, có thể đăng ký `PromptProvider` để trả về `AttributedString` ở mỗi chu kỳ REPL, kết hợp với một service lưu snapshot ngữ cảnh để prompt thay đổi theo phiên làm việc. Hãy giữ prompt ngắn, cập nhật sau thao tác thành công, không gọi hệ thống chậm trong `getPrompt()` và không hiển thị dữ liệu bí mật. Với thông tin dài hoặc cần kiểm tra chi tiết, hãy cung cấp command trạng thái riêng.

## Tài liệu tham khảo

- [Spring Shell 4.x – Custom Prompt](https://docs.spring.io/spring-shell/reference/customization/custom-prompt.html)
- [Spring Shell 4.0.4 API – PromptProvider](https://docs.spring.io/spring-shell/docs/current/api/org/springframework/shell/jline/PromptProvider.html)
- [Spring Shell API – JLineShellAutoConfiguration](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/autoconfigure/JLineShellAutoConfiguration.html)
- [Spring Shell API – TerminalCustomizer](https://docs.spring.io/spring-shell/reference/4.0-SNAPSHOT/api/org/springframework/shell/core/autoconfigure/TerminalCustomizer.html)
- [Spring Shell 4.x – Execution](https://docs.spring.io/spring-shell/reference/execution.html)

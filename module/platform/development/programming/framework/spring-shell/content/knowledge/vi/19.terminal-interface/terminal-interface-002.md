# Tùy biến prompt bằng điểm mở rộng của phiên bản

Prompt là phần hiển thị trước vị trí người dùng nhập command, ví dụ `shell:>`. Một prompt phù hợp có thể cho biết tên ứng dụng, môi trường đang kết nối hoặc trạng thái làm việc hiện tại. Spring Shell cung cấp điểm mở rộng `PromptProvider` để ứng dụng tự quyết định nội dung và kiểu hiển thị của prompt.

Trong Spring Shell 3.4.x và 4.x, điểm mở rộng chính vẫn là interface `PromptProvider` trong package `org.springframework.shell.jline`. Interface có phương thức `getPrompt()` trả về `AttributedString` của JLine và được gọi ở mỗi chu kỳ REPL. Khác biệt giữa hai nhánh chủ yếu nằm ở cách tổ chức auto-configuration và package của một số extension point liên quan, chẳng hạn `TerminalCustomizer`.

## Prompt được tạo ở đâu trong vòng lặp shell?

Khi dùng JLine-based shell với Spring Boot, Spring Shell yêu cầu `PromptProvider` tạo prompt trước mỗi lần chờ người dùng nhập command. Vì vậy, prompt có thể được tính động từ trạng thái hiện tại của ứng dụng.

```mermaid
flowchart TD
    A[Shell hoàn tất một command] --> B[REPL chuẩn bị đọc dòng tiếp theo]
    B --> C[PromptProvider.getPrompt()]
    C --> D[Trả về JLine AttributedString]
    D --> E[JLine hiển thị prompt]
    E --> F[Người dùng nhập command]
    F --> G[Shell phân tích và thực thi]
    G --> A
```

`PromptProvider` chỉ quyết định phần prompt ở REPL tương tác. Nó không thay đổi cú pháp command, không thêm option, không xác thực quyền và không thay thế nội dung output của command. Khi ứng dụng chạy một command đơn hoặc script ở chế độ non-interactive, không có chu kỳ chờ nhập lệnh nên prompt thường không được hiển thị.

## `PromptProvider` trong Spring Shell 3.4.x

Trong nhánh 3.4.x, interface nằm tại:

```java
org.springframework.shell.jline.PromptProvider
```

Phương thức cần triển khai:

```java
AttributedString getPrompt();
```

`AttributedString` và `AttributedStyle` đến từ JLine. `AttributedString` chứa văn bản cùng thông tin style như màu foreground hoặc kiểu chữ. Ví dụ sau thay prompt mặc định bằng `inventory:>` màu xanh lá:

```java
import org.jline.utils.AttributedString;
import org.jline.utils.AttributedStyle;
import org.springframework.shell.jline.PromptProvider;
import org.springframework.stereotype.Component;

@Component
public class InventoryPromptProvider implements PromptProvider {

    @Override
    public AttributedString getPrompt() {
        return new AttributedString(
                "inventory:>",
                AttributedStyle.DEFAULT.foreground(AttributedStyle.GREEN));
    }
}
```

Spring Boot component scan phát hiện bean này. Auto-configuration của Spring Shell 3.4.x chỉ tạo `PromptProvider` mặc định khi chưa có bean cùng kiểu, nên implementation tùy chỉnh sẽ thay thế prompt mặc định.

Nếu muốn khai báo bằng Java configuration, có thể trả về một bean `PromptProvider`:

```java
import org.jline.utils.AttributedString;
import org.jline.utils.AttributedStyle;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.jline.PromptProvider;

@Configuration
public class ShellPromptConfiguration {

    @Bean
    PromptProvider inventoryPromptProvider() {
        return () -> new AttributedString(
                "inventory:>",
                AttributedStyle.DEFAULT.foreground(AttributedStyle.GREEN));
    }
}
```

Vì `PromptProvider` chỉ có một phương thức trừu tượng, có thể dùng lambda thay cho lớp triển khai riêng.

## `PromptProvider` trong Spring Shell 4.x

Trong 4.x, `PromptProvider` vẫn thuộc package `org.springframework.shell.jline`, vẫn trả về `org.jline.utils.AttributedString` qua `getPrompt()` và vẫn được gọi ở mỗi chu kỳ REPL. Ví dụ cấu hình bean:

```java
import org.jline.utils.AttributedString;
import org.jline.utils.AttributedStyle;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.jline.PromptProvider;

@Configuration
public class ShellPromptConfiguration {

    @Bean
    PromptProvider myPromptProvider() {
        return () -> new AttributedString(
                "myprompt:>",
                AttributedStyle.DEFAULT.foreground(AttributedStyle.YELLOW));
    }
}
```

Đây là cách được tài liệu Spring Shell 4.x minh họa. Khi bean tùy chỉnh được đăng ký, auto-configuration không tạo prompt provider mặc định vì phương thức mặc định có điều kiện `@ConditionalOnMissingBean(PromptProvider.class)`.

Có thể dùng lớp `@Component` triển khai `PromptProvider` như ở 3.4.x; hợp đồng interface không đổi. Dùng `@Bean` phù hợp khi muốn tập trung cấu hình shell, còn `@Component` phù hợp khi prompt có trạng thái hoặc phụ thuộc riêng và cần inject các service.

## Đối chiếu điểm mở rộng giữa 3.4.x và 4.x

| Thành phần | Spring Shell 3.4.x | Spring Shell 4.x |
| --- | --- | --- |
| Interface prompt | `org.springframework.shell.jline.PromptProvider` | `org.springframework.shell.jline.PromptProvider` |
| Phương thức | `getPrompt()` | `getPrompt()` |
| Kiểu trả về | `org.jline.utils.AttributedString` | `org.jline.utils.AttributedString` |
| Cách đăng ký | Spring bean, thường dùng `@Component` hoặc `@Bean` | Spring bean, thường dùng `@Component` hoặc `@Bean` |
| Auto-configuration JLine | `org.springframework.shell.boot.JLineShellAutoConfiguration` | `org.springframework.shell.core.autoconfigure.JLineShellAutoConfiguration` |
| `TerminalCustomizer` | `org.springframework.shell.boot.TerminalCustomizer` | `org.springframework.shell.core.autoconfigure.TerminalCustomizer` |

Điểm cần chú ý khi migration là import của auto-configuration và `TerminalCustomizer` thay đổi package. `PromptProvider` vẫn giữ package cũ. Vì vậy, code triển khai prompt thường có thể dùng lại gần như nguyên vẹn khi nâng cấp 3.4.x lên 4.x; kiểm tra lại dependency JLine và các import liên quan nếu dự án có cấu hình terminal tùy chỉnh.

## Phân biệt `PromptProvider` và `TerminalCustomizer`

Hai extension point này tác động vào hai lớp khác nhau:

- `PromptProvider` tạo nội dung và style của chuỗi prompt được hiển thị trước dòng nhập.
- `TerminalCustomizer` nhận `TerminalBuilder` để tùy chỉnh cách JLine tạo terminal, chẳng hạn cấu hình terminal ở mức builder.

Ví dụ đăng ký `TerminalCustomizer` trong Spring Shell 4.x:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.core.autoconfigure.TerminalCustomizer;

@Configuration
public class TerminalConfiguration {

    @Bean
    TerminalCustomizer terminalCustomizer() {
        return builder -> builder.system(true);
    }
}
```

Ví dụ này chỉ minh họa vị trí đăng ký callback. Hãy chọn thuộc tính của `TerminalBuilder` theo môi trường triển khai và nhu cầu thực tế. Nếu mục tiêu chỉ là đổi `shell:>` thành `myapp:>`, không cần tùy chỉnh terminal builder; hãy dùng `PromptProvider`.

Trong Spring Shell 3.4.x, `TerminalCustomizer` nằm trong package `org.springframework.shell.boot`. Trong 4.x, interface chuyển sang `org.springframework.shell.core.autoconfigure`. Đừng nhầm thay đổi package này với `PromptProvider`, vốn không đổi package giữa hai nhánh.

## Tạo prompt có tên ứng dụng và môi trường

Một prompt có thể cho người dùng biết họ đang thao tác trên môi trường nào. Ví dụ:

```text
shop[development]> 
shop[staging]> 
shop[production]> 
```

Lớp triển khai có thể đọc trạng thái từ một service đã được inject:

```java
import org.jline.utils.AttributedString;
import org.jline.utils.AttributedStyle;
import org.springframework.shell.jline.PromptProvider;
import org.springframework.stereotype.Component;

@Component
public class EnvironmentPromptProvider implements PromptProvider {

    private final EnvironmentState environmentState;

    public EnvironmentPromptProvider(EnvironmentState environmentState) {
        this.environmentState = environmentState;
    }

    @Override
    public AttributedString getPrompt() {
        String environment = environmentState.currentName();

        AttributedStyle style = "production".equalsIgnoreCase(environment)
                ? AttributedStyle.DEFAULT.foreground(AttributedStyle.RED)
                : AttributedStyle.DEFAULT.foreground(AttributedStyle.GREEN);

        return new AttributedString(
                "shop[" + environment + "]> ", style);
    }
}
```

Prompt hiển thị màu đỏ khi ứng dụng đang ở production và màu xanh lá ở môi trường còn lại. Màu sắc chỉ là dấu hiệu bổ sung; tên môi trường vẫn phải hiển thị bằng chữ để người dùng không phụ thuộc hoàn toàn vào màu terminal.

Nếu service cần gọi mạng hoặc truy vấn dữ liệu để xác định môi trường, không nên thực hiện công việc đó bên trong `getPrompt()`. Phương thức này được gọi ở mỗi chu kỳ REPL; một thao tác chậm sẽ làm prompt xuất hiện trễ sau mỗi command. Hãy đọc trạng thái đã được cache trong service hoặc cập nhật trạng thái bằng event khi kết nối thay đổi.

## Cập nhật prompt theo event

Prompt động có thể thay đổi sau khi ứng dụng kết nối đến một máy chủ hoặc chuyển môi trường. Dùng event để cập nhật trạng thái, sau đó `getPrompt()` chỉ đọc giá trị hiện tại.

```java
import java.util.concurrent.atomic.AtomicReference;

import org.jline.utils.AttributedString;
import org.jline.utils.AttributedStyle;
import org.springframework.context.event.EventListener;
import org.springframework.shell.jline.PromptProvider;
import org.springframework.stereotype.Component;

@Component
public class ConnectionPromptProvider implements PromptProvider {

    private final AtomicReference<String> host =
            new AtomicReference<>("disconnected");

    @EventListener
    public void onConnectionChanged(ConnectionChangedEvent event) {
        host.set(event.connected() ? event.host() : "disconnected");
    }

    @Override
    public AttributedString getPrompt() {
        String currentHost = host.get();
        AttributedStyle style = "disconnected".equals(currentHost)
                ? AttributedStyle.DEFAULT.foreground(AttributedStyle.RED)
                : AttributedStyle.DEFAULT.foreground(AttributedStyle.GREEN);

        return new AttributedString("shop[" + currentHost + "]> ", style);
    }
}
```

`AtomicReference` giúp việc cập nhật từ event thread và đọc ở REPL thread có tính an toàn luồng. `getPrompt()` chỉ đọc trạng thái đã có, không chờ event hoặc gọi dịch vụ bên ngoài. `ConnectionChangedEvent` là event của ứng dụng; có thể thay bằng event hoặc state holder mà dự án đang sử dụng.

Không đưa mật khẩu, access token, chuỗi kết nối hoặc dữ liệu cá nhân vào prompt. Prompt xuất hiện lặp lại trên màn hình và có thể được lưu trong bản ghi terminal hoặc ảnh chụp màn hình.

## Màu sắc và kiểu chữ với `AttributedString`

JLine `AttributedString` cho phép kết hợp nội dung và `AttributedStyle`. Một số màu cơ bản có thể dùng qua `AttributedStyle`:

```java
AttributedStyle.DEFAULT.foreground(AttributedStyle.GREEN)
AttributedStyle.DEFAULT.foreground(AttributedStyle.YELLOW)
AttributedStyle.DEFAULT.foreground(AttributedStyle.RED)
```

Ví dụ tạo prompt có phần tên ứng dụng màu xanh và môi trường màu vàng:

```java
AttributedString prompt = new AttributedString(
        "shop[staging]> ",
        AttributedStyle.DEFAULT
                .foreground(AttributedStyle.YELLOW)
                .bold());
```

Nếu muốn nhiều đoạn có style khác nhau, dùng `AttributedStringBuilder` của JLine để nối các phần đã gắn style, thay vì tự ghép mã ANSI vào chuỗi. Cách này giúp JLine quản lý thuộc tính hiển thị và độ dài văn bản tốt hơn.

Không nên dùng quá nhiều màu hoặc biểu tượng trong prompt. Prompt được lặp lại sau mỗi command; một chuỗi ngắn và dễ đọc giúp người dùng tập trung vào dữ liệu nhập.

## Prompt trong interactive và non-interactive mode

Prompt là thành phần của vòng lặp nhập lệnh tương tác. Khi shell chạy ở chế độ interactive với JLine, `PromptProvider` được hỏi ở mỗi chu kỳ để hiển thị prompt mới.

Trong chế độ non-interactive, runner đọc command hoặc script mà không chờ người dùng nhập từng dòng. Vì không có REPL prompt, không nên dựa vào `PromptProvider` để in thông tin trạng thái của một batch job. Hãy dùng logger, output của command hoặc thông báo kết quả phù hợp với chế độ chạy.

Nếu cùng một ứng dụng hỗ trợ cả hai chế độ, hãy kiểm tra prompt khi chạy JAR trong terminal thật và kiểm tra riêng output của script. Đừng coi việc không nhìn thấy prompt trong CI là lỗi của `PromptProvider` nếu ứng dụng đang chạy non-interactive.

## Kiểm thử prompt provider

Có thể kiểm thử `PromptProvider` như một bean thông thường, sau đó kiểm thử tích hợp với JLine để xác nhận Spring Shell sử dụng đúng bean.

| Trường hợp | Điều cần xác minh |
| --- | --- |
| Prompt tĩnh | Nội dung trả về đúng tên ứng dụng và dấu kết thúc |
| Prompt có style | Màu/style được tạo bằng `AttributedStyle` đúng mong muốn |
| Prompt theo môi trường | Đổi trạng thái service làm nội dung prompt thay đổi ở chu kỳ tiếp theo |
| Prompt theo event | Event kết nối/ngắt kết nối cập nhật trạng thái hiển thị |
| Nhiều bean `PromptProvider` | Chỉ có một bean được inject cho JLine hoặc có lựa chọn rõ ràng |
| Terminal không hỗ trợ màu | Nội dung vẫn đọc được khi màu không được hiển thị |
| Interactive mode | Prompt xuất hiện sau khi shell khởi động và sau mỗi command |
| Non-interactive mode | Script chạy không phụ thuộc vào prompt |
| Hiệu năng | `getPrompt()` không gọi dịch vụ mạng hoặc truy vấn chậm |
| Bảo mật | Không có mật khẩu, token hoặc dữ liệu nhạy cảm trong prompt |

Khi kiểm thử tích hợp, hãy chạy ứng dụng với terminal JLine hoặc test harness tương ứng. Unit test gọi `getPrompt()` chỉ xác minh logic tạo chuỗi; nó không chứng minh auto-configuration đã chọn đúng bean hoặc prompt được hiển thị trong REPL.

## Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Dùng `TerminalCustomizer` để đổi chữ prompt | Tùy chỉnh terminal builder không trực tiếp tạo prompt | Dùng `PromptProvider` |
| Import `PromptProvider` từ package khác | Không biên dịch hoặc không được JLine nhận diện | Dùng `org.springframework.shell.jline.PromptProvider` ở cả 3.x và 4.x |
| Dùng package `TerminalCustomizer` của 3.x trong 4.x | Không tìm thấy interface | Dùng `org.springframework.shell.core.autoconfigure.TerminalCustomizer` trong 4.x |
| Có nhiều bean `PromptProvider` | Spring có thể không chọn được bean để inject | Giữ một bean hoặc chỉ định bean chính rõ ràng |
| Truy vấn mạng trong `getPrompt()` | Mỗi vòng REPL có thể bị chậm | Đọc state đã cache và cập nhật bằng event |
| Tự ghép mã ANSI | Có thể hiển thị sai hoặc tính độ dài chuỗi không đúng | Dùng `AttributedString` và `AttributedStyle` |
| Hiển thị bí mật trong prompt | Thông tin có thể lộ qua terminal history hoặc bản ghi màn hình | Chỉ hiển thị trạng thái không nhạy cảm |
| Mong prompt xuất hiện khi chạy script | Non-interactive runner không có chu kỳ nhập REPL | In trạng thái qua output/log riêng |

## Quy trình tùy biến prompt

1. Xác định phiên bản Spring Shell và xác nhận ứng dụng đang dùng JLine-based interactive shell.
2. Tạo một bean `PromptProvider` trong package `org.springframework.shell.jline`.
3. Trả về `AttributedString` từ `getPrompt()`; dùng `AttributedStyle` để thêm màu nếu cần.
4. Nếu prompt phụ thuộc trạng thái, inject state holder hoặc cập nhật cache qua event.
5. Giữ `getPrompt()` nhanh, không gọi I/O hoặc truy vấn mạng.
6. Kiểm tra chỉ có một `PromptProvider` được chọn trong Spring context.
7. Chạy thử interactive REPL, non-interactive script và terminal không hỗ trợ màu.

Trong Spring Shell 3.4.x và 4.x, `PromptProvider` vẫn là điểm mở rộng để kiểm soát prompt. Khi nâng cấp, phần triển khai prompt thường không cần đổi; hãy chú ý package auto-configuration và `TerminalCustomizer` nếu ứng dụng có tùy biến terminal ở mức thấp hơn. Một prompt ngắn, có trạng thái hữu ích và được cập nhật nhanh giúp người dùng nhận biết môi trường làm việc mà không làm thay đổi hợp đồng command.

## Tài liệu tham khảo

- [Custom Prompt – Spring Shell 4.0.2](https://docs.spring.io/spring-shell/reference/customization/custom-prompt.html)
- [PromptProvider API – Spring Shell 4.0.2](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/jline/PromptProvider.html)
- [PromptProvider API – Spring Shell 3.4.x](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/jline/PromptProvider.html)
- [JLineShellAutoConfiguration API – Spring Shell 4.0.2](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/autoconfigure/JLineShellAutoConfiguration.html)
- [JLineShellAutoConfiguration API – Spring Shell 3.4.x](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/boot/JLineShellAutoConfiguration.html)
- [TerminalCustomizer API – Spring Shell 4.0.4](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/autoconfigure/TerminalCustomizer.html)
- [TerminalCustomizer API – Spring Shell 3.4.x](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/boot/TerminalCustomizer.html)

# Tránh đăng ký trùng tên từ nhiều nguồn cấu hình

Một ứng dụng Spring Shell có thể khai báo command bằng annotation, tạo command bằng Java hoặc nhận command từ các module cấu hình khác nhau. Khi nhiều nguồn cùng tạo một command có cùng tên, registry không còn một định nghĩa rõ ràng cho tên lệnh đó. Người dùng có thể gọi nhầm hành vi, phần trợ giúp hiển thị thông tin không như mong đợi hoặc một command bị che khuất trong quá trình đăng ký.

Bài học thuộc chương **Đăng ký bằng mã** của Spring Shell. Nội dung tập trung vào cách nhận diện nguồn đăng ký, quản lý tên command và alias, kiểm soát cấu hình theo profile/module, cũng như kiểm tra registry để tránh xung đột.

Sau bài học, bạn có thể:

- Nhận diện các nguồn có thể cùng đăng ký một command.
- Phân biệt tên command, alias và tên Spring bean.
- Thiết kế quy tắc đặt tên để tránh xung đột giữa annotation, programmatic command và command tích hợp.
- Kiểm tra trùng tên trước khi đưa command vào ứng dụng.
- Hiểu khác biệt cơ bản giữa `CommandRegistry` của Spring Shell 4.x và `CommandCatalog` ở các phiên bản 3.x.

## Tên command là định danh trong shell

Spring Shell 4.x dùng `CommandRegistry` để quản lý các command mà ứng dụng biết đến. Mỗi command được nhận diện bằng tên. Registry cung cấp các thao tác tra cứu theo tên, tra cứu theo alias, liệt kê command và đăng ký hoặc hủy đăng ký command trong thời gian chạy.

Tên command là một phần của giao diện CLI mà người dùng nhìn thấy và nhập vào terminal. Ví dụ `user list` là một tên command; `user` và `list` là các thành phần của đường dẫn lệnh. Tên bean Spring như `userCommands` hoặc `userListCommand` chỉ phục vụ container quản lý đối tượng. Hai command có bean name khác nhau vẫn có thể xung đột nếu chúng cùng khai báo tên CLI `user list`.

Vì vậy, khi rà soát trùng lặp, cần kiểm tra tên command và alias thực tế, không chỉ kiểm tra tên method hoặc tên bean.

## Những nguồn có thể tạo cùng một command

Trong Spring Shell 4.x, có hai mô hình khai báo command chính:

| Nguồn | Cách khai báo | Cách Spring Shell thu nhận |
| --- | --- | --- |
| Annotation | Method trong Spring bean được đánh dấu `@Command`. | Cơ chế command scanning tạo command từ method đã khai báo. |
| Programmatic | Bean kiểu `Command`, thường được tạo bằng `Command.builder()`. | `CommandRegistry` tự thu nhận các command bean trong application context. |
| Command tích hợp | Các command do Spring Shell hoặc module mở rộng cung cấp. | Auto-configuration của module tương ứng đăng ký command vào ứng dụng. |
| Đăng ký động | Mã ứng dụng gọi API đăng ký của registry trong thời gian chạy. | Command được thêm hoặc gỡ trực tiếp thông qua `CommandRegistry`. |

Các nguồn này có thể cùng tồn tại trong một application context. Ví dụ, một module định nghĩa `user list` bằng `@Command`, trong khi module khác tạo một bean `Command` cũng mang tên `user list`. Tên bean khác nhau không ngăn được xung đột tên command.

Với Spring Shell 4.x, Spring Boot tự bật command scanning khi dùng auto-configuration. Ứng dụng Spring Framework thuần cần kích hoạt discovery bằng `@EnableCommand`. Hãy dùng đúng cơ chế theo kiểu ứng dụng; không thêm một cấu hình discovery thứ hai cho cùng các lớp command khi không có nhu cầu rõ ràng.

### Ví dụ xung đột giữa annotation và programmatic command

Giả sử module người dùng khai báo command bằng annotation:

```java
import org.springframework.stereotype.Component;
import org.springframework.shell.core.command.annotation.Command;

@Component
class UserCommands {

    @Command(name = "user list", description = "Liệt kê người dùng")
    public String listUsers() {
        return "Danh sách người dùng";
    }
}
```

Trong khi đó, một lớp cấu hình khác cũng tạo command cùng tên:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.core.command.Command;

@Configuration
class LegacyUserCommandConfiguration {

    @Bean
    Command legacyUserListCommand() {
        return Command.builder()
            .name("user list")
            .execute(ctx -> ctx.outputWriter().println(
                "Danh sách người dùng từ handler cũ"));
    }
}
```

Hai định nghĩa có hai bean name khác nhau nhưng cùng command name `user list`. Ứng dụng đang có hai nơi sở hữu cùng một điểm vào CLI. Cần chọn một định nghĩa làm chủ sở hữu, sau đó xóa, đổi tên hoặc loại cấu hình còn lại khỏi application context.

## Tên chính và alias đều phải duy nhất

Một command có thể có nhiều alias để người dùng gọi nhanh hoặc duy trì tương thích với cú pháp cũ. Trong Spring Shell 4.x, annotation `@Command` có thuộc tính `alias`; command programmatic có thể khai báo alias qua builder.

```java
@Command(
    name = "user list",
    alias = {"users", "user ls"},
    description = "Liệt kê người dùng")
public String listUsers() {
    return "Danh sách người dùng";
}
```

Command programmatic có thể khai báo cùng ý nghĩa:

```java
@Bean
Command userListCommand() {
    return Command.builder()
        .name("user list")
        .aliases("users", "user ls")
        .execute(ctx -> ctx.outputWriter().println("Danh sách người dùng"));
}
```

Khi kiểm tra xung đột, cần rà soát cả bốn trường hợp:

1. Tên chính của command này trùng tên chính của command khác.
2. Tên chính của command này trùng alias của command khác.
3. Alias của command này trùng tên chính của command khác.
4. Alias của hai command khác nhau trùng nhau.

Ví dụ, nếu `user list` có alias `users`, command khác không nên dùng `users` làm tên chính. Tương tự, không nên để hai command khác nhau cùng khai báo alias `ls` nếu chúng nằm trong cùng phạm vi tra cứu.

Alias là tên gọi thay thế của một command hiện có. Nếu mục đích là đổi tên command, có thể giữ tên cũ làm alias trong một giai đoạn chuyển tiếp. Không cần tạo thêm một command thứ hai chỉ để gọi lại cùng hành vi.

## Quy tắc đặt tên để giảm xung đột

Hãy thống nhất một quy tắc đặt tên theo miền chức năng và hành động. Với ứng dụng có nhiều module, dùng prefix giúp tên command thể hiện chủ sở hữu:

| Miền chức năng | Command đề xuất | Ý nghĩa |
| --- | --- | --- |
| Người dùng | `user list`, `user create`, `user delete` | Các thao tác quản lý người dùng. |
| Báo cáo | `report list`, `report export` | Các thao tác báo cáo. |
| Cấu hình | `config show`, `config reload` | Các thao tác cấu hình ứng dụng. |
| Tác vụ nền | `job list`, `job run`, `job status` | Các thao tác quản lý job. |

Tên ngắn như `list`, `show`, `run` dễ bị nhiều module sử dụng cùng lúc. Đặt command theo cấu trúc `domain action` làm rõ phạm vi và giúp người dùng khám phá lệnh qua `help`.

Nên thống nhất chữ thường và cách dùng khoảng trắng trong toàn dự án. Ví dụ dùng `user list` ở mọi nguồn thay vì trộn `User List`, `user-list` và `user  list`. Không dựa vào việc các nguồn đăng ký sẽ tự chuẩn hóa những cách viết khác nhau thành cùng một tên.

Spring Shell 4.x cho phép dùng `@CommandGroup` để đặt prefix chung cho một nhóm method. Ví dụ:

```java
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.CommandGroup;

@CommandGroup(prefix = "user", name = "User Commands")
class UserCommands {

    @Command(name = "list", description = "Liệt kê người dùng")
    public String list() {
        return "Danh sách người dùng";
    }

    @Command(name = "create", description = "Tạo người dùng")
    public String create() {
        return "Đã tạo người dùng";
    }
}
```

Các command trong nhóm có tên đầy đủ như `user list` và `user create`. Khi kiểm tra trùng tên, phải xét tên đầy đủ sau khi áp dụng prefix của nhóm, không chỉ xét tên method `list` hoặc `create`.

## Tránh đăng ký lặp qua component scanning và cấu hình

Một nguyên nhân thường gặp là cùng một lớp command được đưa vào context qua nhiều cấu hình. Ví dụ, package đã nằm trong component scan nhưng một cấu hình khác lại import hoặc khai báo thêm một bean factory cho cùng lớp command.

Hãy rà soát các điểm sau:

- Package chứa command có bị scan từ nhiều cấu hình độc lập không?
- Một lớp có `@Command` có đồng thời được chuyển thành một command bean thủ công không?
- Có nhiều `@Bean` tạo cùng một command name ở các module khác nhau không?
- Một cấu hình được import nhiều lần qua các lớp `@Configuration` không?
- Cấu hình theo profile hoặc property có thể cùng được bật trong môi trường triển khai không?

### Cấu hình theo profile

Hai command cùng tên có thể được đặt trong hai cấu hình thay thế nếu ứng dụng bảo đảm chỉ một profile hoạt động trong một lần chạy:

```java
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;
import org.springframework.shell.core.command.annotation.Command;

@Component
@Profile("legacy-user-cli")
class LegacyUserCommands {

    @Command(name = "user list")
    public String list() {
        return "Danh sách theo hệ thống cũ";
    }
}

@Component
@Profile("modern-user-cli")
class ModernUserCommands {

    @Command(name = "user list")
    public String list() {
        return "Danh sách theo hệ thống mới";
    }
}
```

Thiết kế này chỉ an toàn khi hai profile loại trừ nhau trong mọi môi trường. Nếu môi trường vô tình bật cả `legacy-user-cli` và `modern-user-cli`, hai định nghĩa cùng được nạp. Hãy kiểm tra profile của integration test, môi trường staging và production, đồng thời kiểm tra cấu hình mặc định.

Nếu hai implementation là các lựa chọn thay thế của cùng một chức năng, nên dùng một bean điều phối hoặc một cấu hình có điều kiện rõ ràng để chọn implementation, trong khi command name chỉ được khai báo tại một nơi.

## Không dựa vào thứ tự đăng ký để xử lý trùng tên

`CommandRegistry` của Spring Shell 4.x mô tả command là các đối tượng được nhận diện duy nhất bằng tên. API cung cấp các phương thức `getCommandByName`, `getCommandByAlias`, `getCommands`, `registerCommand` và `unregisterCommand`.

Tài liệu API công khai không đưa ra một hợp đồng ổn định để ứng dụng dựa vào khi hai nguồn đăng ký cùng một tên, chẳng hạn luôn lấy command đầu tiên hoặc luôn ghi đè bằng command cuối cùng. Vì vậy, không thiết kế ứng dụng theo giả định thứ tự khởi tạo bean quyết định implementation nào thắng. Hãy phát hiện và xử lý xung đột trong cấu hình trước khi phát hành.

Đặc biệt, không dùng các cách sau làm chiến lược quản lý command:

- Đổi thứ tự khai báo `@Bean` với hy vọng command mong muốn được đăng ký sau cùng.
- Dựa vào thứ tự component scan giữa các package.
- Dựa vào thứ tự import các lớp `@Configuration`.
- Tạo hai command cùng tên rồi kiểm tra bằng tay command nào đang chạy ở môi trường production.

Nếu muốn thay thế command tích hợp hoặc command cũ, hãy dùng cơ chế cấu hình chính thức của phiên bản đang chạy để loại bỏ định nghĩa cũ, hoặc chọn tên command mới. Một lần thay thế cần có kiểm thử xác nhận command cuối cùng trong registry trỏ đến implementation dự kiến.

## Kiểm tra danh sách command trong Spring Shell 4.x

Sau khi application context được tạo, có thể lấy `CommandRegistry` và xem danh sách command đã được nạp:

```java
import org.springframework.shell.core.command.Command;
import org.springframework.shell.core.command.CommandRegistry;

void printRegisteredCommands(CommandRegistry registry) {
    for (Command command : registry.getCommands()) {
        System.out.printf(
            "name=%s, aliases=%s%n",
            command.getName(),
            command.getAliases());
    }
}
```

Có thể tra cứu một tên cụ thể:

```java
Command command = registry.getCommandByName("user list");
Command aliasTarget = registry.getCommandByAlias("users");
```

Nếu kết quả là `null`, tên tương ứng không có trong registry tại thời điểm kiểm tra. Nếu có kết quả, hãy xem `getName()`, `getAliases()` và mô tả của command để xác nhận implementation được nạp đúng.

Việc kiểm tra registry cho biết trạng thái cuối cùng mà shell đang sử dụng. Để phát hiện đầy đủ các định nghĩa trùng trước khi registry xử lý chúng, cần kiểm tra tập khai báo từ tất cả nguồn cấu hình trong bước kiểm thử hoặc bước xác thực cấu hình.

### Ví dụ kiểm tra tên và alias từ tập command đầu vào

Có thể dùng một hàm kiểm tra độc lập trước khi đưa các command vào registry. Hàm nhận toàn bộ command được thu thập từ các nguồn cấu hình và báo lỗi khi một chuỗi gọi lệnh được nhiều command khác nhau sở hữu:

```java
import java.util.Collection;
import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.shell.core.command.Command;

final class CommandNameValidator {

    private CommandNameValidator() {
    }

    static void verifyUniqueNames(Collection<Command> commands) {
        Map<String, Command> owners = new LinkedHashMap<>();

        for (Command command : commands) {
            claim(owners, command.getName(), command);
            for (String alias : command.getAliases()) {
                claim(owners, alias, command);
            }
        }
    }

    private static void claim(
            Map<String, Command> owners,
            String invocation,
            Command command) {

        Command previous = owners.putIfAbsent(invocation, command);
        if (previous != null && previous != command) {
            throw new IllegalStateException(
                "Command name or alias '" + invocation + "' is used by both '"
                    + previous.getName() + "' and '" + command.getName() + "'");
        }
    }
}
```

Hàm này kiểm tra cả tên chính lẫn alias. Để có giá trị, collection đầu vào phải chứa command từ mọi nguồn cần kiểm soát, bao gồm command annotation, command programmatic và command mở rộng do ứng dụng bổ sung. Không chỉ truyền một phần command của một module rồi xem kết quả đó là kiểm tra toàn hệ thống.

Có thể gọi validator trong một integration test với tập command đã được lắp ghép cho profile cần kiểm tra. Nếu ứng dụng có nhiều profile hoặc tổ hợp feature flag, hãy chạy kiểm tra cho từng tổ hợp được hỗ trợ.

## Kiểm thử để ngăn xung đột quay lại

Một kiểm thử tốt nên xác nhận cả tên và hành vi của command. Có thể tổ chức thành các lớp sau:

1. **Kiểm tra danh mục:** tập tên chính và alias không có phần tử trùng giữa các command khác nhau.
2. **Kiểm tra application context:** khởi tạo context với đúng profile và property của môi trường, sau đó xác nhận các command cần thiết đã được đăng ký.
3. **Kiểm tra registry:** dùng `getCommands()` để xem danh sách command thực tế; dùng `getCommandByName()` và `getCommandByAlias()` để kiểm tra các tên quan trọng.
4. **Kiểm tra thực thi:** gọi command có nguy cơ xung đột và xác nhận đúng handler được thực thi.
5. **Kiểm tra tổ hợp cấu hình:** khởi tạo context cho các profile/feature flag có thể xuất hiện trong triển khai.

Trong integration test đã khởi tạo application context, có thể inject toàn bộ `Command` bean để kiểm tra danh mục tên và alias:

```java
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.shell.core.command.Command;

class UserCommandTests {

    @Autowired
    List<Command> commands;

    @Test
    void allCommandNamesAndAliasesAreUnique() {
        CommandNameValidator.verifyUniqueNames(commands);
    }
}
```

Danh sách `Command` cần bao gồm command được tạo từ method `@Command`, command bean programmatic và command mở rộng do ứng dụng cung cấp. Sau khi kiểm tra danh mục, có thể dùng `ShellTestClient` để xác nhận tên lệnh thực thi đúng handler:

```java
import org.springframework.shell.test.ShellAssertions;
import org.springframework.shell.test.ShellScreen;
import org.springframework.shell.test.ShellTestClient;

ShellScreen screen = client.sendCommand("user list");
ShellAssertions.assertThat(screen).containsText("Danh sách người dùng");
```

Kiểm tra danh mục phát hiện xung đột tên và alias; kiểm tra qua shell xác nhận đường đi từ tên command đến output.

## Lưu ý khi làm việc với Spring Shell 3.x

Ở Spring Shell 3.x, API programmatic chủ yếu dùng `CommandRegistration` và `CommandCatalog`. Ứng dụng có thể khai báo `CommandRegistration` dưới dạng bean, đăng ký trực tiếp qua `CommandCatalog`, hoặc mở rộng catalog bằng `CommandCatalogCustomizer` và `CommandResolver`. Dòng 3.x cũng dùng `@EnableCommand` hoặc `@CommandScan` để bật command discovery, kể cả khi dùng Spring Boot.

`CommandCatalog` cung cấp `register(...)`, `unregister(...)` và `getRegistrations()`. Các registration được ánh xạ theo command name. Vì vậy, nguyên tắc quản lý tên vẫn giống nhau: tập hợp tất cả nguồn registration và kiểm tra trùng tên trước khi đưa vào catalog.

Spring Shell 4.x đã thay đổi mô hình programmatic sang `Command` và `CommandRegistry`. Không trộn ví dụ `CommandRegistration`/`CommandCatalog` của 3.x với API `Command`/`CommandRegistry` của 4.x trong cùng một đoạn cấu hình nếu chưa có lớp chuyển đổi được thiết kế rõ ràng.

## Các command tích hợp cũng thuộc phạm vi kiểm tra

Spring Shell có các command tích hợp như `help`, `clear`, `script` và `version`; khi dùng JLine còn có thể có command `history`. Module mở rộng cũng có thể cung cấp command riêng. Khi đặt tên command ứng dụng, hãy kiểm tra các command đã được nạp bởi dependency để tránh chiếm dụng cùng tên.

Nếu cần thay đổi hành vi của command tích hợp, trước hết kiểm tra cơ chế bật/tắt hoặc thay thế mà phiên bản Spring Shell đang sử dụng hỗ trợ. Việc thêm một command cùng tên mà không xử lý command cũ có thể tạo ra cấu hình khó dự đoán. Nếu không có nhu cầu tương thích đặc biệt, hãy chọn tên theo miền nghiệp vụ của ứng dụng.

## Checklist trước khi phát hành

- [ ] Mỗi command có một tên chính duy nhất trong toàn bộ ứng dụng.
- [ ] Không alias nào trùng tên chính hoặc alias của command khác.
- [ ] Tên command đã tính đến prefix từ `@CommandGroup` hoặc cấu hình nhóm.
- [ ] Không có cùng một chức năng được đăng ký đồng thời qua `@Command` và `Command` bean.
- [ ] Các module được import và component scan không tạo hai nguồn đăng ký cùng tên.
- [ ] Profile và feature flag không kích hoạt các implementation trùng tên cùng lúc.
- [ ] Các tên không xung đột với command tích hợp hoặc command từ dependency mở rộng.
- [ ] Integration test kiểm tra registry và thực thi đúng handler cho các command quan trọng.
- [ ] Không dựa vào thứ tự khởi tạo hoặc thứ tự đăng ký để giải quyết xung đột.

Quản lý tên command tập trung giúp giao diện CLI ổn định khi ứng dụng phát triển thành nhiều module. Mỗi tên gọi có một chủ sở hữu rõ ràng, alias được kiểm soát cùng tên chính và các nguồn cấu hình được kiểm tra trước khi triển khai.

## Tài liệu tham khảo

- [Spring Shell 4.0.4 — Command Registration](https://docs.spring.io/spring-shell/reference/commands/registration.html): hai mô hình annotation và programmatic, cùng vai trò của `CommandRegistry`.
- [Spring Shell 4.x API — CommandRegistry](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/CommandRegistry.html): tra cứu command, alias, liệt kê và đăng ký/hủy đăng ký command.
- [Spring Shell 4.x API — Command](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/Command.html): tên, alias và builder của command.
- [Spring Shell 4.x API — `@Command`](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/Command.html): khai báo tên, alias và nhóm cho command method.
- [Spring Shell v4 Migration Guide](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide): thay đổi mô hình programmatic registration giữa Spring Shell 3.x và 4.x.
- [Spring Shell 3.3.4 — Command Catalog](https://docs.spring.io/spring-shell/reference/3.3/appendices/techintro/commandcatalog.html): `CommandCatalog`, `CommandCatalogCustomizer` và `CommandResolver` trong dòng 3.x.

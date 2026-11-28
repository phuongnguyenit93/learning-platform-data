# Kiểm tra đăng ký và danh sách command hiệu lực

## 1. Vì sao cần kiểm tra danh sách command khi ứng dụng khởi động?

Một command có thể đã được viết trong source code nhưng chưa chắc đã xuất hiện trong Spring Shell. Command chỉ hoạt động khi cơ chế đăng ký nhận diện được lớp hoặc bean chứa nó, tạo được `CommandRegistration` và đưa registration vào catalog đang được shell sử dụng.

Ví dụ, một lớp `ProjectCommands` có thể chứa `@ShellMethod`, nhưng nếu package của lớp bị loại khỏi component scan thì Spring không tạo bean. Tương tự, một phương thức mang `@Command` cần được cơ chế đăng ký của annotation model nhận diện. Một `CommandRegistration` khai báo trong cấu hình cũng không có tác dụng nếu bean cấu hình đó không được nạp.

Kiểm tra danh sách command hiệu lực giúp phát hiện các lỗi này ngay trong test, trước khi người dùng mở REPL và thử từng lệnh.

## 2. Phân biệt command được khai báo, được đăng ký và có thể thực thi

Khi kiểm thử, cần phân biệt ba trạng thái:

| Trạng thái | Ý nghĩa | Cách kiểm tra |
|---|---|---|
| Được khai báo | Có method hoặc cấu hình mô tả command trong source code | Code review hoặc test cấu hình. |
| Được đăng ký | Có `CommandRegistration` trong catalog hoặc được resolver cung cấp khi shell phân giải lệnh | Đọc `CommandCatalog` và kiểm tra `CommandResolver`. |
| Có thể thực thi | Command hiện diện, không bị ẩn, đang available và target thực thi được | Kiểm tra metadata rồi gọi command qua test client. |

Một command có thể được đăng ký nhưng đang unavailable vì người dùng chưa kết nối máy chủ. Command cũng có thể được đăng ký nhưng bị đánh dấu hidden để không xuất hiện trong help và completion. Vì vậy, chỉ đếm số command trong catalog chưa đủ để kết luận người dùng nhìn thấy hoặc chạy được tất cả các lệnh đó.

## 3. Những nguồn đăng ký command trong Spring Shell 3.x

Spring Shell 3.x hỗ trợ nhiều cách tạo command registration. Dù dùng annotation hay khai báo trực tiếp, shell cuối cùng vẫn làm việc với cấu trúc đăng ký command.

### Annotation legacy: `@ShellComponent` và `@ShellMethod`

Đây là mô hình annotation quen thuộc trong các ứng dụng Spring Shell 3.x:

~~~java
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;
import org.springframework.shell.standard.ShellOption;

@ShellComponent
public class ProjectCommands {

    @ShellMethod(key = "project list", value = "Liệt kê các project")
    public String list(@ShellOption(value = "--owner", defaultValue = "all") String owner) {
        return "project-a, project-b";
    }

    @ShellMethod(key = "project create", value = "Tạo một project")
    public String create() {
        return "Đã tạo project";
    }
}
~~~

`@ShellComponent` đánh dấu bean có thể chứa shell method; `@ShellMethod` đánh dấu method được đăng ký thành command. Lớp phải được component scan tìm thấy. Nếu package chứa command bị loại bằng `excludeFilters`, bean sẽ không được tạo và các method cũng không được đăng ký.

Nếu không đặt `key`, Spring Shell suy ra tên command từ tên method. Khi test danh sách command, hãy kiểm tra tên thực tế trong registration thay vì suy ra từ tên class hoặc tên bean.

### Annotation model mới: `@Command`

Spring Shell 3.x cũng có annotation model mới trong package `org.springframework.shell.command.annotation`. Lớp hoặc method dùng `@Command` cần được đăng ký thông qua `@EnableCommand` hoặc cơ chế scan tương ứng.

~~~java
import org.springframework.shell.command.annotation.Command;
import org.springframework.shell.command.annotation.EnableCommand;
import org.springframework.context.annotation.Configuration;

@Command(command = "diagnostics")
public class DiagnosticsCommands {

    @Command(command = "ping")
    public String ping() {
        return "pong";
    }
}

@Configuration
@EnableCommand(DiagnosticsCommands.class)
class ShellCommandConfiguration {
}
~~~

Trong ứng dụng Spring Boot, auto-configuration có thể đảm nhiệm việc đăng ký các command target. Với ứng dụng không dùng Spring Boot hoặc cấu hình thủ công, cần khai báo rõ cơ chế enable/scan phù hợp. Khi test, hãy nạp đúng configuration chứa `@EnableCommand`.

### Programmatic registration bằng `CommandRegistration`

Với programmatic model, có thể định nghĩa registration thành bean:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.command.CommandRegistration;

@Configuration
public class ProjectCommandConfiguration {

    @Bean
    CommandRegistration projectPing(
            CommandRegistration.BuilderSupplier builders) {
        return builders.get()
                .command("project ping")
                .description("Kiểm tra project service")
                .group("Project")
                .withTarget()
                    .function(context -> "pong")
                    .and()
                .build();
    }
}
~~~

`CommandRegistration.BuilderSupplier` cung cấp builder đã được áp dụng các customizer mặc định của ứng dụng. Spring Shell auto-configuration sử dụng `CommandCatalogCustomizer` để đưa các `CommandRegistration` bean vào catalog.

Nếu cần đăng ký hoặc hủy đăng ký command trong lúc ứng dụng đang chạy, có thể inject `CommandCatalog` rồi gọi `register(...)` hoặc `unregister(...)`.

## 4. Đọc danh sách command hiệu lực qua CommandCatalog

Trong Spring Shell 3.x, `CommandCatalog` là API quản lý các `CommandRegistration`. Có thể inject catalog vào test hoặc một service chẩn đoán:

~~~java
import java.util.Map;

import org.springframework.shell.command.CommandCatalog;
import org.springframework.shell.command.CommandRegistration;
import org.springframework.stereotype.Component;

@Component
public class CommandInventory {

    private final CommandCatalog commandCatalog;

    public CommandInventory(CommandCatalog commandCatalog) {
        this.commandCatalog = commandCatalog;
    }

    public Map<String, CommandRegistration> registrations() {
        return commandCatalog.getRegistrations();
    }
}
~~~

`getRegistrations()` trả về map các registration được catalog quản lý, được ánh xạ theo tên command. Map trả về là bản sao; sửa map này không đăng ký hoặc hủy đăng ký command trong catalog. Muốn thay đổi catalog, hãy gọi `register(...)` hoặc `unregister(...)` trên chính `CommandCatalog`.

Có thể lấy tên command và sắp xếp để hiển thị ổn định:

~~~java
import java.util.List;

public List<String> commandNames() {
    return commandCatalog.getRegistrations().values().stream()
            .map(CommandRegistration::getCommand)
            .sorted()
            .toList();
}
~~~

`getCommand()` trả về tên command đã đăng ký, có thể gồm nhiều từ như `project list`. Không dùng tên class hoặc tên method làm khóa test khi command đã khai báo `key`/`command` tường minh.

## 5. Viết test xác nhận các command bắt buộc đã được đăng ký

Đây là test cơ bản để kiểm tra catalog sau khi Spring context được khởi tạo:

~~~java
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.shell.command.CommandCatalog;
import org.springframework.shell.command.CommandRegistration;
import org.springframework.shell.test.autoconfigure.ShellTest;
import org.springframework.test.context.ContextConfiguration;

import static org.assertj.core.api.Assertions.assertThat;

@ShellTest
@ContextConfiguration(classes = ShellApplication.class)
class CommandRegistrationTests {

    @Autowired
    private CommandCatalog commandCatalog;

    @Test
    void requiredCommandsAreRegistered() {
        Map<String, CommandRegistration> registrations =
                commandCatalog.getRegistrations();

        assertThat(registrations)
                .containsKeys("project list", "project create", "project ping");
    }
}
~~~

`ShellApplication` là configuration hoặc lớp Spring Boot chính của ứng dụng, nơi component scan và các configuration đăng ký command được kích hoạt. `@ShellTest` chuẩn bị hạ tầng test cho Spring Shell.

Các test dùng `@ShellTest` cần test support của Spring Shell: `spring-shell-test` và `spring-shell-test-autoconfigure` với test scope. Ví dụ dùng `await()` cần Awaitility trên test classpath; nếu dependency này chưa được kéo vào qua cấu hình test hiện tại, hãy khai báo thêm nó.

Nên kiểm tra những command nghiệp vụ quan trọng bằng `containsKeys(...)` thay vì khóa cứng tổng số phần tử trong catalog. Số lượng command có thể thay đổi theo built-in commands, profile, feature flag hoặc cấu hình bật/tắt một command có sẵn.

## 6. Kiểm tra metadata của từng registration

`CommandRegistration` cung cấp nhiều thuộc tính để xác nhận command được đăng ký đúng cấu hình:

| Getter | Thông tin |
|---|---|
| `getCommand()` | Tên command. |
| `getDescription()` | Mô tả command. |
| `getGroup()` | Nhóm hiển thị trong help. |
| `getOptions()` | Danh sách option. |
| `getAliases()` | Alias của command. |
| `getAvailability()` | Trạng thái availability hiện tại. |
| `getInteractionMode()` | Chế độ tương tác được khai báo. |
| `isHidden()` | Command có bị ẩn hay không. |

Ví dụ kiểm tra tên, mô tả và option:

~~~java
@Test
void projectListHasExpectedMetadata() {
    CommandRegistration registration = commandCatalog.getRegistrations()
            .get("project list");

    assertThat(registration).isNotNull();
    assertThat(registration.getCommand()).isEqualTo("project list");
    assertThat(registration.getDescription()).isEqualTo("Liệt kê các project");
    assertThat(registration.getGroup()).isEqualTo("Project");
    assertThat(registration.getOptions()).hasSize(1);
}
~~~

Đoạn test khớp với ví dụ `ProjectCommands` ở phần 3: `project list` khai báo một option `--owner`. Hãy điều chỉnh assertion theo contract thật của command. Khi chỉ cần bảo đảm option tồn tại, có thể kiểm tra số lượng hoặc tên option thay vì so sánh toàn bộ object nội bộ.

Metadata giúp phát hiện những lỗi như mô tả bị bỏ trống, command bị đưa vào sai group, option không được đăng ký hoặc key command khác với tài liệu hướng dẫn.

## 7. Phân biệt hidden với unavailable

Hai trạng thái này có ý nghĩa khác nhau:

| Trạng thái | Registration có tồn tại? | Hiển thị trong help/completion? | Có thể gọi? |
|---|---|---|---|
| Command bình thường và available | Có | Có | Có. |
| Command unavailable | Có | Có thể vẫn xuất hiện kèm lý do không khả dụng | Không thể thực thi cho đến khi điều kiện được đáp ứng. |
| Command hidden | Có | Không xuất hiện trong danh sách help và completion | Vẫn có thể gọi nếu biết tên và command không bị chặn bởi điều kiện khác. |
| Không được đăng ký | Không | Không | Không. |

Có thể đặt `hidden` trên programmatic `CommandRegistration` hoặc dùng thuộc tính `hidden` của annotation model mới `@Command`. Không nên xem việc ẩn command như cơ chế phân quyền hoặc bảo mật. Nếu command có thể thay đổi dữ liệu nhạy cảm, vẫn phải kiểm tra quyền ở tầng nghiệp vụ.

Availability có thể thay đổi theo trạng thái ứng dụng. Ví dụ, `project deploy` chỉ khả dụng sau khi người dùng kết nối môi trường đích:

Đây là phần trích từ một `@Configuration` bean; `connected` là trạng thái được cập nhật bởi luồng kết nối của ứng dụng, còn `deployProject()` đại diện cho service triển khai.

~~~java
import org.springframework.shell.Availability;

private boolean connected;

@Bean
CommandRegistration deployCommand(CommandRegistration.BuilderSupplier builders) {
    return builders.get()
            .command("project deploy")
            .description("Triển khai project")
            .availability(() -> connected
                    ? Availability.available()
                    : Availability.unavailable("Chưa kết nối môi trường đích"))
            .withTarget()
                .consumer(context -> deployProject())
                .and()
            .build();
}
~~~

Khi test availability, hãy thiết lập trạng thái ứng dụng trước khi đọc `getAvailability()`:

~~~java
@Test
void deployCommandIsUnavailableBeforeConnection() {
    CommandRegistration registration = commandCatalog.getRegistrations()
            .get("project deploy");

    assertThat(registration.getAvailability().isAvailable()).isFalse();
    assertThat(registration.getAvailability().getReason())
            .contains("Chưa kết nối");
}
~~~

Test khác nên kết nối môi trường rồi xác nhận command trở thành available. Đừng đánh dấu test thất bại chỉ vì một command được đăng ký nhưng hiện tại chưa thể thực thi; đó có thể là hành vi đúng theo nghiệp vụ.

## 8. Kiểm tra danh sách hiển thị trong help

Catalog là nơi kiểm tra registration. Lệnh `help` xác nhận điều người dùng thực sự nhìn thấy sau khi shell áp dụng quy tắc hiển thị, group và availability.

Spring Shell cung cấp `ShellTestClient` để chạy shell trong test. Với non-interactive session, có thể gọi help rồi kiểm tra màn hình:

~~~java
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.shell.test.ShellAssertions;
import org.springframework.shell.test.ShellTestClient;
import org.springframework.shell.test.ShellTestClient.NonInteractiveShellSession;
import org.springframework.shell.test.autoconfigure.ShellTest;
import org.springframework.test.context.ContextConfiguration;

import static org.awaitility.Awaitility.await;

@ShellTest
@ContextConfiguration(classes = ShellApplication.class)
class CommandHelpTests {

    @Autowired
    private ShellTestClient shellTestClient;

    @Test
    void helpListsVisibleProjectCommands() {
        NonInteractiveShellSession session = shellTestClient
                .nonInteractive("help")
                .run();

        await().atMost(2, TimeUnit.SECONDS).untilAsserted(() -> {
            ShellAssertions.assertThat(session.screen())
                    .containsText("project list")
                    .containsText("project create");
        });
    }
}
~~~

Awaitility chờ output ổn định trước khi assertion. Điều này hữu ích vì test shell mô phỏng terminal và việc cập nhật màn hình có thể diễn ra bất đồng bộ.

Nếu một command hidden, hãy xác nhận nó vẫn có registration trong catalog nhưng không xuất hiện trong output help. Nếu command unavailable, kiểm tra cả lý do hiển thị và trạng thái availability thay vì chỉ tìm chuỗi tên command.

## 9. Kiểm tra command có thực sự thực thi được

Một registration có thể có mặt trong catalog nhưng target vẫn cấu hình sai. Hãy chạy command qua `ShellTestClient` để xác nhận parser, target và output hoạt động cùng nhau.

~~~java
@Test
void projectListCanBeInvoked() {
    NonInteractiveShellSession session = shellTestClient
            .nonInteractive("project list")
            .run();

    await().atMost(2, TimeUnit.SECONDS).untilAsserted(() -> {
        ShellAssertions.assertThat(session.screen())
                .containsText("project-a");
    });
}
~~~

Test này xác nhận command không chỉ tồn tại trong catalog mà còn có thể được shell phân giải, gọi target và hiển thị kết quả. Với command nhận option, hãy chạy thêm trường hợp có và không có option, giá trị hợp lệ và không hợp lệ.

Đối với command cần nhập liệu tương tác, dùng `shellTestClient.interactive().run()` rồi gửi chuỗi phím vào session. Với command non-interactive, `nonInteractive("command name", "--option", "value")` phù hợp hơn.

## 10. Kiểm tra đăng ký động và hủy đăng ký

`CommandCatalog` cho phép đăng ký hoặc hủy đăng ký command khi ứng dụng đang chạy. Test cần dọn registration sau khi hoàn tất để không làm ảnh hưởng test khác:

~~~java
import org.springframework.shell.command.CommandRegistration;

@Test
void commandCanBeRegisteredAndUnregisteredDynamically() {
    CommandRegistration diagnostic = CommandRegistration.builder()
            .command("diagnostics ping")
            .description("Kiểm tra trạng thái diagnostics")
            .withTarget()
                .function(context -> "pong")
                .and()
            .build();

    try {
        commandCatalog.register(diagnostic);

        assertThat(commandCatalog.getRegistrations())
                .containsKey("diagnostics ping");
    }
    finally {
        commandCatalog.unregister("diagnostics ping");
    }

    assertThat(commandCatalog.getRegistrations())
            .doesNotContainKey("diagnostics ping");
}
~~~

Không cố thêm command vào map do `getRegistrations()` trả về. Map đó chỉ là bản sao. Việc đăng ký phải gọi `commandCatalog.register(...)`; việc hủy phải gọi `commandCatalog.unregister(...)`.

Trong ứng dụng thực tế, chỉ đăng ký hoặc hủy command khi trạng thái nghiệp vụ thực sự yêu cầu. Tránh để nhiều nơi cùng tự ý thay đổi catalog vì sẽ khó kiểm soát danh sách lệnh theo từng thời điểm.

## 11. Kiểm tra CommandCatalogCustomizer và CommandResolver

Hai extension point này giải quyết hai nhu cầu khác nhau.

**`CommandCatalogCustomizer`** thay đổi catalog trong giai đoạn cấu hình. Ví dụ, ứng dụng có thể đăng ký thêm command chẩn đoán dùng chung:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.shell.command.CommandCatalogCustomizer;
import org.springframework.shell.command.CommandRegistration;

@Bean
CommandCatalogCustomizer diagnosticsCustomizer(
        CommandRegistration.BuilderSupplier builders) {
    return catalog -> {
        CommandRegistration registration = builders.get()
                .command("diagnostics version")
                .description("Hiển thị phiên bản ứng dụng")
                .withTarget()
                    .function(context -> "1.0.0")
                    .and()
                .build();

        catalog.register(registration);
    };
}
~~~

Test nên xác nhận command do customizer thêm vào xuất hiện trong `getRegistrations()` sau khi context khởi tạo.

**`CommandResolver`** cung cấp registration động theo trạng thái runtime. Ví dụ, một số command chỉ tồn tại khi ứng dụng đang kết nối với một môi trường đích:

~~~java
import java.util.List;

import org.springframework.shell.command.CommandRegistration;
import org.springframework.shell.command.CommandResolver;
import org.springframework.stereotype.Component;

@Component
public class RemoteCommandResolver implements CommandResolver {

    private final ConnectionState connectionState;
    private final CommandRegistration remoteStatus;

    public RemoteCommandResolver(ConnectionState connectionState) {
        this.connectionState = connectionState;
        this.remoteStatus = CommandRegistration.builder()
                .command("remote status")
                .description("Xem trạng thái môi trường từ xa")
                .withTarget()
                    .function(context -> "connected")
                    .and()
                .build();
    }

    @Override
    public List<CommandRegistration> resolve() {
        return connectionState.isConnected()
                ? List.of(remoteStatus)
                : List.of();
    }
}
~~~

`CommandResolver.resolve()` được gọi mỗi khi shell cần phân giải command. Không thực hiện truy vấn mạng chậm hoặc thao tác nặng trong resolver vì điều đó làm việc nhập lệnh bị chậm. Nếu cần kiểm tra trạng thái từ xa, hãy cập nhật `ConnectionState` ở một luồng riêng và để resolver đọc snapshot nhanh.

Với resolver, nên có hai loại test:

1. Unit test gọi `resolve()` trực tiếp khi trạng thái kết nối bật và tắt.
2. Integration test dùng `ShellTestClient` để xác nhận `remote status` có thể được phân giải ở trạng thái phù hợp và không được phân giải khi điều kiện không còn đúng.

Không chỉ dựa vào một lần đọc `CommandCatalog.getRegistrations()` để kết luận về command do resolver cung cấp. Hãy kiểm tra cả kết quả resolver và hành vi phân giải thực tế của shell.

## 12. Những nguyên nhân thường khiến command không xuất hiện

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Lớp `@ShellComponent` không có trong catalog | Package không nằm trong component scan hoặc bị exclude | Kiểm tra package của application class và `ComponentScan`. |
| Method không thành command | Thiếu `@ShellMethod` hoặc annotation đặt sai | Kiểm tra method và lớp chứa method. |
| `@Command` không được đăng ký | Thiếu `@EnableCommand` hoặc cấu hình scan tương ứng | Kiểm tra configuration được nạp trong test. |
| Programmatic command không có | Bean `CommandRegistration` hoặc configuration không được tạo | Kiểm tra profile, condition và context configuration. |
| Command do customizer thêm không xuất hiện | `CommandCatalogCustomizer` không phải Spring bean hoặc không được nạp | Kiểm tra bean và catalog sau khi context khởi tạo. |
| Command động lúc có lúc không | `CommandResolver` trả danh sách theo trạng thái hiện tại | Test `resolve()` với từng trạng thái. |
| Command có trong catalog nhưng không thấy trong help | Registration được đánh dấu hidden | Kiểm tra `isHidden()`. |
| Command có trong help nhưng không chạy | Availability hiện tại là unavailable hoặc target lỗi | Kiểm tra `getAvailability()` và gọi command qua test client. |
| Tên command trong test khác thực tế | `key`/`command` nhiều từ hoặc tên mặc định được suy ra từ method | Đọc `getCommand()` trong registration. |

Ngoài ra, các command built-in có thể được bật hoặc tắt theo cấu hình. Không nên viết test phụ thuộc vào tổng số command cố định nếu test không kiểm soát tất cả properties và extension point.

## 13. Bộ test đề xuất cho danh sách command

Một bộ test tốt nên bao phủ nhiều lớp:

| Phạm vi | Điều cần xác nhận |
|---|---|
| Catalog | Các command nghiệp vụ bắt buộc đã được đăng ký. |
| Metadata | Tên, mô tả, group, option và alias đúng. |
| Hidden | Command nội bộ được ẩn khỏi help/completion theo yêu cầu. |
| Availability | Command chuyển trạng thái available/unavailable theo điều kiện. |
| Help | Các command người dùng cần biết xuất hiện trong danh sách help. |
| Invocation | Command được parser phân giải, gọi target và trả output đúng. |
| Dynamic registration | `register` và `unregister` cập nhật catalog như mong đợi. |
| Resolver | Danh sách động phản ánh trạng thái runtime và không gây chậm khi phân giải. |
| Configuration | Profile, property và component scan tạo đúng danh sách command ở từng cấu hình. |

Nên kiểm tra cả cấu hình mặc định và các profile/feature flag quan trọng. Với mỗi profile, chỉ assert các command thuộc contract của profile đó; không so sánh tổng số registration giữa những môi trường có built-in command khác nhau.

## 14. Checklist trước khi phát hành

- [ ] Mọi lớp chứa command annotation đều được Spring tạo bean hoặc được enable đúng cách.
- [ ] Các `CommandRegistration` bean được nạp trong application context.
- [ ] Các `CommandCatalogCustomizer` cần thiết đã chạy.
- [ ] Các `CommandResolver` trả đúng danh sách theo trạng thái runtime.
- [ ] Các command bắt buộc có mặt trong `CommandCatalog.getRegistrations()`.
- [ ] Tên command, mô tả, group và options đúng.
- [ ] Command hidden không xuất hiện ngoài ý muốn.
- [ ] Availability và lý do unavailable được kiểm tra.
- [ ] Help hiển thị đúng command người dùng cần thấy.
- [ ] Các command quan trọng thực thi thành công qua `ShellTestClient`.
- [ ] Test không phụ thuộc vào tổng số command built-in cố định.
- [ ] Các test đăng ký động luôn hủy registration sau khi hoàn tất.

## Kết luận

Trong Spring Shell 3.x, kiểm tra danh sách command hiệu lực nên bắt đầu từ `CommandCatalog.getRegistrations()`. Map này cho biết những `CommandRegistration` catalog đang quản lý và cung cấp metadata để test tên, mô tả, group, options, aliases, hidden và availability. Sau đó dùng `ShellTestClient` để xác nhận help hiển thị đúng và command thực sự chạy được. Với command động, cần kiểm tra riêng `CommandResolver.resolve()` và hành vi phân giải của shell. Kết hợp test catalog, metadata, help và invocation sẽ phát hiện sớm lỗi component scan, thiếu cấu hình enable, condition sai hoặc command không khả dụng.

## Tài liệu tham khảo

- [Spring Shell 3.4 – Command Registration](https://docs.spring.io/spring-shell/reference/3.4/appendices/techintro/registration.html)
- [Spring Shell 3.4 – Command Catalog](https://docs.spring.io/spring-shell/reference/3.4/appendices/techintro/commandcatalog.html)
- [Spring Shell 3.4 API – CommandCatalog](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/command/CommandCatalog.html)
- [Spring Shell 3.4 API – CommandRegistration](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/command/CommandRegistration.html)
- [Spring Shell 3.4 API – CommandRegistration.Builder](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/command/CommandRegistration.Builder.html)
- [Spring Shell 3.4 API – Command annotation](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/command/annotation/Command.html)
- [Spring Shell 3.4 API – EnableCommand annotation](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/command/annotation/EnableCommand.html)
- [Spring Shell 3.4 API – CommandResolver](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/command/CommandResolver.html)
- [Spring Shell 3.4 API – CommandCatalogCustomizer](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/command/CommandCatalogCustomizer.html)
- [Spring Shell 3.4 API – Availability](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/Availability.html)
- [Spring Shell 3.4 – Testing Basics](https://docs.spring.io/spring-shell/reference/3.4/testing/basics.html)

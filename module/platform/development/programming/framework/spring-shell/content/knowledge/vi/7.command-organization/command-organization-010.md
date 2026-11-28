# Phân biệt ẩn lệnh, gỡ đăng ký và không cho phép thực thi

Spring Shell có nhiều cách kiểm soát việc người dùng nhìn thấy và gọi một command. Ba cách thường bị nhầm lẫn là **ẩn command**, **đánh dấu command không khả dụng** và **gỡ command khỏi registry**. Chúng tạo ra ba kết quả khác nhau: ẩn chỉ giảm khả năng khám phá; availability ngăn command chạy khi điều kiện chưa thỏa; unregister loại command khỏi tập lệnh mà shell nhận diện.

Trong module `SPRING_SHELL`, việc chọn đúng cơ chế giúp tổ chức command theo trạng thái ứng dụng, tính năng được bật và nhu cầu vận hành. Nó cũng ảnh hưởng đến trợ giúp, tự hoàn thành, script và cách thông báo lỗi cho người dùng.

## 1. Ba cơ chế và mục đích của chúng

Hãy hình dung ứng dụng quản lý máy chủ có các command `server status`, `server connect`, `server download` và `server diagnostics`. Mỗi command có thể cần một cách kiểm soát khác nhau:

- `server diagnostics` chỉ dành cho nhóm hỗ trợ nên không cần quảng bá trong trợ giúp thông thường.
- `server download` chỉ chạy được sau khi kết nối máy chủ thành công.
- `server diagnostics` có thể bị gỡ khỏi registry khi plugin hỗ trợ được tắt trong phiên hiện tại.

| Tiêu chí | Ẩn command (`hidden`) | Không khả dụng (`availability`) | Gỡ đăng ký (`unregister`) |
| --- | --- | --- | --- |
| Command còn trong registry | Có | Có | Không |
| Hiển thị trong trợ giúp thông thường | Không | Vẫn là command đã đăng ký; không bị ẩn chỉ vì unavailable | Không |
| Có thể gọi trực tiếp bằng tên đã biết | Có | Shell từ chối thực thi khi điều kiện chưa thỏa | Không; shell không còn nhận diện command |
| Phụ thuộc trạng thái runtime | Không nhất thiết | Có, provider được đánh giá theo trạng thái hiện tại | Thường phụ thuộc vòng đời hoặc cấu hình tính năng |
| Trường hợp sử dụng | Command nội bộ, debug, thao tác ít dùng | Chưa đăng nhập, chưa kết nối, thiếu tài nguyên hoặc chưa đạt điều kiện nghiệp vụ | Tắt plugin, thu hồi command trong phiên, loại bỏ tính năng khỏi registry |

Sự khác biệt quan trọng nhất là: **ẩn không đồng nghĩa với khóa**, **không khả dụng không đồng nghĩa với gỡ đăng ký**, và **gỡ đăng ký không phải là xóa bean hay xóa mã nguồn**.

## 2. Ẩn command bằng `hidden`

Ẩn command phù hợp khi command vẫn cần tồn tại và vẫn có thể thực thi, nhưng không muốn đưa nó vào danh sách thao tác thông thường. Ví dụ là command chẩn đoán dành cho đội hỗ trợ, command debug hoặc command phục vụ kiểm tra trong môi trường phát triển.

Mô hình annotation mới của Spring Shell 3.4 hỗ trợ `@Command(hidden = true)` trong package `org.springframework.shell.command.annotation`. Spring Shell 4.x tiếp tục thuộc tính này trong package `org.springframework.shell.core.command.annotation`; ở 4.x, `@Command` được đặt trên phương thức. Ví dụ dưới đây dùng import và cách khai báo của 4.x:

```java
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.stereotype.Component;

@Component
public class DiagnosticCommands {

    @Command(
        name = "server diagnostics",
        description = "Hiển thị thông tin chẩn đoán.",
        hidden = true
    )
    public String diagnostics() {
        return "Thông tin chẩn đoán của máy chủ";
    }
}
```

Người dùng thông thường không thấy command này trong danh sách trợ giúp hoặc gợi ý hoàn thành. Người biết chính xác tên và option vẫn có thể nhập trực tiếp:

```text
shell:> server diagnostics
Thông tin chẩn đoán của máy chủ
```

Tài liệu Spring Shell mô tả hidden command bị loại khỏi danh sách trợ giúp, trang trợ giúp chi tiết và các danh sách completion tương tác/Bash; command vẫn có thể được gọi nếu người dùng biết cú pháp. Vì vậy, `hidden = true` chỉ là cơ chế giảm khả năng khám phá, không phải biện pháp bảo mật.

### Khác biệt giữa các thế hệ API

- Trong Spring Shell 3.2, tài liệu hidden command mô tả khả năng này qua programmatic `CommandRegistration.Builder.hidden(...)` và ghi rõ chưa hỗ trợ trong annotation-based configuration.
- Trong mô hình annotation mới của Spring Shell 3.4, `@Command` đã có thuộc tính `hidden` ở cấp lớp và phương thức.
- Trong Spring Shell 4.x, `@Command(hidden = true)` tiếp tục được hỗ trợ; API programmatic `Command.Builder` cũng có `hidden(boolean)`.
- Không nên giả định annotation legacy `@ShellMethod` của các ứng dụng cũ có thuộc tính `hidden`. Khi dùng legacy API, cần kiểm tra đúng phiên bản và cân nhắc đăng ký command theo mô hình programmatic nếu cần ẩn.

Với Spring Shell 4.x, một command được tạo bằng builder cũng có thể được đánh dấu ẩn:

```java
import org.springframework.shell.core.command.Command;

Command diagnostics = Command.builder()
        .name("server diagnostics")
        .description("Thông tin chẩn đoán dành cho hỗ trợ.")
        .hidden(true)
        .execute(context -> context.outputWriter()
                .println("Thông tin chẩn đoán của máy chủ"));
```

Đoạn mã trên tạo đối tượng command có metadata ẩn. Để command được shell sử dụng theo mô hình programmatic, cần đăng ký đối tượng đó với `CommandRegistry`.

## 3. Không cho phép thực thi bằng availability

Có những command phải tồn tại để người dùng biết ứng dụng hỗ trợ chức năng đó, nhưng chỉ thực thi được khi trạng thái hiện tại đáp ứng điều kiện. Ví dụ `download` chỉ chạy sau khi kết nối máy chủ, `deploy` chỉ chạy khi đã chọn môi trường hoặc `publish` chỉ chạy khi bản build đã hoàn tất.

Spring Shell dùng `Availability` và `AvailabilityProvider` để mô tả trạng thái này. Provider trả về một trong hai kết quả:

- `Availability.available()`: command có thể thực thi.
- `Availability.unavailable(reason)`: command hiện không thể thực thi; `reason` giải thích ngắn gọn nguyên nhân.

Ví dụ trong Spring Shell 4.x:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.availability.Availability;
import org.springframework.shell.core.command.availability.AvailabilityProvider;
import org.springframework.stereotype.Component;

@Component
public class RemoteCommands {

    private boolean connected;

    @Command(name = "connect", description = "Kết nối tới máy chủ.")
    public String connect() {
        connected = true;
        return "Đã kết nối máy chủ";
    }

    @Command(
        name = "download",
        description = "Tải dữ liệu từ máy chủ.",
        availabilityProvider = "downloadAvailability"
    )
    public String download() {
        return "Đã tải dữ liệu";
    }

    @Bean
    AvailabilityProvider downloadAvailability() {
        return () -> connected
                ? Availability.available()
                : Availability.unavailable("chưa kết nối tới máy chủ");
    }
}
```

Khi chưa kết nối, người dùng nhập:

```text
shell:> download
Command 'download' exists but is not currently available because you are not connected.
```

Phương thức `download()` không được thực thi. Sau khi gọi `connect`, provider trả về `available()` và command có thể chạy.

Lý do không khả dụng nên là một cụm giải thích ngắn, viết thường và không có dấu chấm cuối câu vì Spring Shell nối nó vào thông báo có từ “because”. Trong ứng dụng thực tế, trạng thái kết nối nên được quản lý bởi một service hoặc component riêng; ví dụ dùng field boolean trong command class chỉ nhằm làm rõ luồng hoạt động.

### Availability trong Spring Shell 3.x

Trong mô hình annotation mới của Spring Shell 3.4, có thể dùng `@CommandAvailability` cùng `AvailabilityProvider` để gắn điều kiện với command. Với mô hình legacy, Spring Shell hỗ trợ phương thức trả về `Availability` có tên theo quy ước `tenCommandAvailability()` hoặc dùng `@ShellMethodAvailability` để chỉ định phương thức kiểm tra.

Khi nâng lên Spring Shell 4.x, cấu hình availability được đưa trực tiếp vào `@Command(availabilityProvider = "...")`. Provider vẫn trả về `Availability.available()` hoặc `Availability.unavailable(reason)`, nhưng package và vị trí khai báo cần theo API 4.x.

Availability phù hợp với điều kiện thay đổi trong runtime. Không nên gỡ rồi đăng ký lại command mỗi lần trạng thái kết nối thay đổi; provider giúp giữ command trong registry và chỉ thay đổi khả năng thực thi.

## 4. Gỡ command khỏi registry

Khi một tính năng hoặc plugin không còn được cung cấp trong phiên hiện tại, có thể gỡ command khỏi registry. Sau khi gỡ, shell không còn tìm thấy command đó khi phân giải dòng lệnh. Người dùng nhập tên cũ sẽ nhận kết quả tương tự command không tồn tại.

### Gỡ đăng ký trong Spring Shell 4.x

Spring Shell 4.x cung cấp `CommandRegistry`, nơi lưu các command mà shell biết. Registry được Spring tự động điền từ các command trong application context và cũng hỗ trợ đăng ký/gỡ đăng ký trong runtime.

```java
import org.springframework.shell.core.command.Command;
import org.springframework.shell.core.command.CommandRegistry;
import org.springframework.stereotype.Component;

@Component
public class CommandLifecycle {

    private final CommandRegistry commandRegistry;

    public CommandLifecycle(CommandRegistry commandRegistry) {
        this.commandRegistry = commandRegistry;
    }

    public void removeDiagnosticsCommand() {
        Command command = commandRegistry.getCommandByName("server diagnostics");
        if (command != null) {
            commandRegistry.unregisterCommand(command);
        }
    }
}
```

`getCommandByName` trả về command theo tên hoặc `null` nếu không có. Chỉ gọi `unregisterCommand` khi tìm thấy đối tượng. Registry cũng cung cấp `getCommandByAlias` để tra cứu theo alias, `registerCommand` để đăng ký lại và `getCommands` để xem tập command hiện tại.

Ví dụ đăng ký lại command sau khi bật plugin:

```java
public void addDiagnosticsCommand() {
    Command command = Command.builder()
            .name("server diagnostics")
            .description("Hiển thị thông tin chẩn đoán.")
            .execute(context -> context.outputWriter()
                    .println("Thông tin chẩn đoán của máy chủ"));

    commandRegistry.registerCommand(command);
}
```

Command được tạo bằng builder là command programmatic. Nếu command ban đầu đến từ annotation, việc gỡ khỏi registry không xóa Spring bean hoặc annotation khỏi mã nguồn. Khi ứng dụng khởi động lại, registry được tự động điền từ application context; command annotation vẫn được phát hiện và đăng ký lại nếu bean vẫn nằm trong phạm vi scan.

### Gỡ đăng ký trong Spring Shell 3.x

Trong mô hình programmatic của Spring Shell 3.x, `CommandCatalog` cung cấp các thao tác `register(...)` và `unregister(...)`. Có thể gỡ theo tên command hoặc theo đối tượng `CommandRegistration`:

```java
import org.springframework.shell.command.CommandCatalog;

public class CommandLifecycle {

    private final CommandCatalog commandCatalog;

    public CommandLifecycle(CommandCatalog commandCatalog) {
        this.commandCatalog = commandCatalog;
    }

    public void removeDiagnosticsCommand() {
        commandCatalog.unregister("server diagnostics");
    }
}
```

API 3.x dùng `CommandCatalog` và `CommandRegistration`; API 4.x dùng `CommandRegistry` và `Command`. Không sao chép trực tiếp kiểu dữ liệu hoặc tên phương thức giữa hai major version.

## 5. Không đăng ký command ngay từ đầu

Nếu command không nên tồn tại trong một ứng dụng hoặc một profile triển khai, cách đơn giản nhất là không đưa command target vào quá trình đăng ký:

- Không khai báo lớp command như Spring bean trong cấu hình đó.
- Đặt command class ngoài phạm vi component scan hoặc dùng điều kiện cấu hình để chỉ tạo bean khi tính năng được bật.
- Với ứng dụng non-Boot sử dụng `@EnableCommand`, chỉ liệt kê những command target cần đăng ký.
- Với command programmatic, không tạo bean `Command` tương ứng nếu tính năng không được bật.

Đây là quyết định ở giai đoạn cấu hình ứng dụng. Nó khác với unregister runtime: unregister loại một command khỏi registry hiện tại, trong khi không đăng ký từ đầu ngăn command được thêm vào registry khi khởi động.

## 6. So sánh kết quả khi người dùng gọi command

Giả sử command tên `server diagnostics` được cấu hình theo từng cơ chế:

| Cấu hình | `help` | Nhập trực tiếp `server diagnostics` | Kết quả |
| --- | --- | --- | --- |
| Command bình thường | Có trong danh sách | Được phân giải và chạy | Thực thi bình thường |
| `hidden = true` | Không được quảng bá trong danh sách thông thường | Vẫn được phân giải và có thể chạy | Thực thi nếu người dùng biết cú pháp |
| `Availability.unavailable(...)` | Vẫn là command đã đăng ký | Được nhận diện nhưng bị từ chối thực thi | Hiển thị lý do không khả dụng |
| Đã unregister | Không còn trong danh sách | Không được phân giải | Báo command không tồn tại/không được nhận diện |
| Không đăng ký từ đầu | Không có trong danh sách | Không được phân giải | Báo command không tồn tại/không được nhận diện |

Điểm khác biệt giữa hai dòng cuối nằm ở thời điểm và cơ chế: một command đã tồn tại rồi bị loại khỏi registry trong runtime; command còn lại chưa từng được đăng ký trong cấu hình ứng dụng.

## 7. Chọn cơ chế theo tình huống

| Nhu cầu | Cơ chế phù hợp | Lý do |
| --- | --- | --- |
| Giữ command debug nhưng không muốn người dùng thông thường nhìn thấy | `hidden` | Command còn gọi được khi cần hỗ trợ |
| Chỉ cho chạy sau khi đăng nhập hoặc kết nối | `AvailabilityProvider` | Điều kiện được kiểm tra theo trạng thái hiện tại và có lý do rõ ràng |
| Tắt command khi plugin bị gỡ hoặc tính năng bị thu hồi trong phiên | `CommandRegistry.unregisterCommand` hoặc `CommandCatalog.unregister` | Loại command khỏi tập lệnh shell đang nhận diện |
| Một profile triển khai không cung cấp chức năng đó | Không đăng ký bean/command target | Command không được đưa vào registry khi khởi động |
| Người dùng không có quyền thực hiện thao tác nhạy cảm | Kiểm tra quyền ở tầng nghiệp vụ; có thể kết hợp availability để cải thiện trải nghiệm | Quyền truy cập phải được kiểm tra thực sự khi thực thi |

## 8. Lưu ý bảo mật

Ẩn command không bảo vệ chức năng khỏi người biết tên command. Availability cũng không thay thế cơ chế phân quyền. Một người dùng có thể biết cú pháp, gọi từ script hoặc gọi service bên ngoài shell nếu ứng dụng cung cấp đường truy cập khác.

Với thao tác nhạy cảm như xóa dữ liệu, thay đổi cấu hình production hoặc triển khai hệ thống, hãy kiểm tra quyền trong service hoặc tầng nghiệp vụ mỗi lần thao tác được yêu cầu. Có thể dùng availability để không quảng bá hoặc báo trước rằng người dùng chưa đủ điều kiện, nhưng service vẫn phải từ chối yêu cầu nếu người gọi không có quyền. Không đặt bí mật, token hoặc thông tin xác thực trong tên command hay metadata ẩn.

Ngoài ra, unregister command chỉ thay đổi registry của Spring Shell. Nó không thu hồi quyền truy cập vào API, service hoặc endpoint khác; những bề mặt truy cập đó cần có cơ chế kiểm soát riêng.

## 9. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể có | Cách xử lý |
| --- | --- | --- |
| Command ẩn vẫn chạy khi nhập đúng tên | `hidden` chỉ ẩn khỏi trợ giúp và completion | Nếu cần ngăn thực thi, dùng availability hoặc kiểm tra quyền ở service |
| Command không xuất hiện trong `help` dù đã khai báo | `hidden = true`, bean không được scan hoặc command target chưa được đăng ký | Kiểm tra hidden metadata, component scan và cấu hình đăng ký |
| Command luôn báo unavailable | Provider luôn trả `Availability.unavailable` hoặc đọc sai trạng thái | Kiểm tra điều kiện và trạng thái được cập nhật sau thao tác connect/login |
| Thông báo unavailable khó đọc | Reason viết hoa hoặc kết thúc bằng dấu chấm, khiến câu ghép không tự nhiên | Viết reason ngắn, bắt đầu bằng chữ thường và không có dấu chấm cuối |
| Command đã unregister nhưng xuất hiện lại sau khi khởi động | Bean annotation vẫn còn trong application context và registry tự động nạp lại | Loại bean khỏi component scan/cấu hình hoặc chỉ dùng unregister cho vòng đời runtime |
| Gọi command sau unregister vẫn được thực thi qua API khác | Chỉ registry shell đã bị thay đổi | Kiểm tra và bảo vệ service/API ở tầng nghiệp vụ |

## 10. Checklist lựa chọn và kiểm tra

- Xác định mục tiêu là giảm khả năng khám phá, chặn theo trạng thái hay loại khỏi registry.
- Nếu dùng `hidden`, thử `help`, completion và gọi trực tiếp bằng tên đầy đủ.
- Nếu dùng availability, thử cả trạng thái available và unavailable; xác nhận command không chạy khi điều kiện chưa thỏa.
- Nếu dùng unregister, kiểm tra tên command và alias không còn được phân giải; kiểm tra cả thao tác đăng ký lại nếu cần.
- Xác định command được đăng ký từ annotation, programmatic bean hay cấu hình `@EnableCommand`.
- Nếu cần loại bỏ command qua nhiều lần khởi động, cập nhật cấu hình/bean scanning thay vì chỉ unregister trong runtime.
- Với thao tác nhạy cảm, xác minh quyền tại tầng nghiệp vụ kể cả khi đã dùng hidden hoặc availability.
- Dùng đúng API `CommandCatalog` của 3.x hoặc `CommandRegistry` của 4.x.

## Tài liệu tham khảo

- [Spring Shell 4.x — Command Registration](https://docs.spring.io/spring-shell/reference/commands/registration.html)
- [Spring Shell 4.x — Command Availability](https://docs.spring.io/spring-shell/reference/commands/availability.html)
- [Spring Shell 4.0.3 — `@Command` API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/Command.html)
- [Spring Shell 4.0.3 — `CommandRegistry` API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/CommandRegistry.html)
- [Spring Shell 3.4 — Command Catalog](https://docs.spring.io/spring-shell/reference/3.4/appendices/techintro/commandcatalog.html)
- [Spring Shell 3.4 — `@Command` API](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/command/annotation/Command.html)
- [Spring Shell 3.2 — Hidden Command](https://docs.spring.io/spring-shell/reference/3.2-SNAPSHOT/commands/hidden.html)

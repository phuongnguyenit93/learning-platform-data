# Kiểm tra danh sách lệnh hiệu lực sau cấu hình Spring

Khi ứng dụng Spring Shell khởi động, command có thể đến từ nhiều nguồn: phương thức được đánh dấu annotation, bean đăng ký bằng `CommandRegistration`, command do `CommandResolver` cung cấp và những command được bổ sung qua customizer. Vì vậy, nhìn vào một lớp Java hoặc danh sách bean riêng lẻ chưa đủ để biết runtime thực sự nhận được những lệnh nào.

Muốn kiểm tra kết quả sau khi Spring cấu hình xong, cần quan sát registry/catalog mà Spring Shell dùng để phân giải command. Với Spring Shell 3.x, thành phần này là `CommandCatalog`. Từ danh sách đó, ta có thể xem tên command, mô tả, nhóm, trạng thái ẩn và khả năng sử dụng tại thời điểm kiểm tra.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích sự khác nhau giữa command được khai báo, command được đăng ký và command hiện có thể gọi.
- Xác định các nguồn tạo command trong một Spring context.
- Dùng `CommandCatalog` của Spring Shell 3.x để đọc danh sách command sau cấu hình.
- Phân biệt command đã đăng ký, command bị ẩn và command tạm thời không khả dụng.
- Kiểm tra ảnh hưởng của component scan, profile, customizer và resolver đến danh sách command.
- Viết kiểm thử xác nhận command mong đợi có mặt trong registry.
- Nhận biết API kiểm tra registry đã thay đổi khi chuyển sang Spring Shell 4.x.

## 1. Vì sao cần kiểm tra danh sách lệnh sau cấu hình?

Một command có thể tồn tại trong source code nhưng không xuất hiện trong runtime. Ví dụ, lớp chứa command không được component scan phát hiện, cấu hình enablement chưa được nạp, profile hiện tại loại bean đó hoặc dependency chứa command không có trong classpath.

Ngược lại, một ứng dụng có thể đăng ký nhiều command hơn dự kiến. Một module được thêm vào classpath, một customizer bổ sung command hoặc một resolver trả về command theo trạng thái hiện tại đều có thể làm danh sách hiệu lực thay đổi.

Hãy phân biệt bốn trạng thái:

1. **Được khai báo:** code có phương thức hoặc đối tượng mô tả command.
2. **Được Spring phát hiện:** lớp hoặc bean liên quan đã được tạo trong ApplicationContext.
3. **Được đăng ký:** Spring Shell đưa command vào catalog/registry để runtime phân giải.
4. **Có thể sử dụng tại thời điểm hiện tại:** command đã đăng ký và điều kiện khả dụng của nó đang cho phép thực thi.

Ví dụ, command `report download` có thể được đăng ký ngay khi ứng dụng khởi động, nhưng chỉ khả dụng sau khi người dùng kết nối tới máy chủ. Command vẫn tồn tại trong catalog khi chưa kết nối; trạng thái khả dụng của nó thay đổi theo trạng thái ứng dụng.

## 2. Các nguồn tạo command trong Spring Shell 3.x

Trong một ứng dụng Spring Shell 3.x, danh sách command có thể được tạo từ nhiều nguồn.

### 2.1. Command khai báo bằng annotation

Mô hình annotation cho phép đánh dấu phương thức trong một lớp Spring-managed:

```java
import org.springframework.shell.command.annotation.Command;
import org.springframework.stereotype.Component;

@Component
public class CustomerCommands {

    @Command(command = "customer list", description = "Liệt kê khách hàng")
    public String list() {
        return "Danh sách khách hàng";
    }
}
```

Lớp phải được Spring phát hiện và cơ chế đăng ký command annotation phải được kích hoạt. Với ứng dụng Spring Boot, auto-configuration của Spring Shell hỗ trợ quá trình lắp ráp này. Với context tự cấu hình, cần bật và đăng ký target theo cách mà minor version đang dùng yêu cầu, chẳng hạn qua `@EnableCommand`.

Một lỗi thường gặp là dùng `@ComponentScan` với `excludeFilters` rồi vô tình loại package chứa lớp command. Khi đó source code vẫn biên dịch, nhưng registrar không thể phát hiện target để tạo command.

### 2.2. Bean `CommandRegistration`

Mô hình programmatic cho phép định nghĩa command bằng `CommandRegistration`. Trong Spring Boot, các bean loại này được cơ chế auto-configuration đưa vào catalog thông qua customizer mặc định.

Ví dụ rút gọn về một bean đăng ký command:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.command.CommandRegistration;

@Configuration
public class ReportCommandConfiguration {

    @Bean
    CommandRegistration reportStatusCommand(
            CommandRegistration.BuilderSupplier builders) {
        return builders.get()
                .command("report status")
                .withTarget()
                    .function(context -> "Report service is ready")
                    .and()
                .build();
    }
}
```

Builder tạo metadata command và target thực thi. Trong ứng dụng thực tế, có thể khai báo thêm description, group, option, alias, validation, availability và các quy tắc khác.

### 2.3. `CommandCatalogCustomizer`

`CommandCatalogCustomizer` cho phép thay đổi catalog trong giai đoạn cấu hình. Đây là nơi phù hợp để bổ sung hoặc điều chỉnh command theo cấu hình ứng dụng.

Một customizer có thể gọi `commandCatalog.register(...)` để thêm đăng ký và `commandCatalog.unregister(...)` để gỡ đăng ký. Cần kiểm soát rõ nguồn command được thêm vào để tránh đăng ký trùng hoặc làm lộ command chỉ dành cho môi trường phát triển.

### 2.4. `CommandResolver`

`CommandResolver` cho phép tạo tập command động. Ví dụ, một công cụ quản trị có thể cung cấp command khác nhau tùy máy chủ đang kết nối hoặc tenant đang được chọn.

Với command động, danh sách có thể thay đổi theo trạng thái ứng dụng. Resolver được dùng trong quá trình phân giải command; nếu mỗi lần resolve phải gọi dịch vụ từ xa hoặc truy vấn dữ liệu chậm, trải nghiệm shell có thể bị chậm theo. Nên giữ resolver nhẹ, tránh thực hiện công việc tốn thời gian ở mỗi lần phân giải.

## 3. `CommandCatalog` là điểm kiểm tra trong Spring Shell 3.x

`CommandCatalog` định nghĩa hợp đồng quản lý các `CommandRegistration` mà shell sử dụng. Catalog hỗ trợ đọc, đăng ký và gỡ đăng ký command.

Phương thức quan trọng để kiểm tra danh sách là:

```java
Map<String, CommandRegistration> registrations =
        commandCatalog.getRegistrations();
```

Map trả về ánh xạ tên command tới `CommandRegistration`. API trả về một bản sao của map; thay đổi map này không đăng ký hoặc gỡ command khỏi catalog. Nếu muốn thay đổi danh sách, hãy gọi các phương thức `register(...)` hoặc `unregister(...)` trên `CommandCatalog` hay dùng customizer phù hợp.

Trong ứng dụng Boot, `CommandCatalog` được lắp ráp từ những thành phần đăng ký command hiện có, các resolver và customizer. Vì vậy, đọc catalog sau khi ApplicationContext đã hoàn tất khởi tạo là cách phù hợp để xem kết quả của cấu hình Spring Shell.

Không nên chỉ gọi `ApplicationContext.getBeansOfType(CommandRegistration.class)` rồi xem đó là toàn bộ danh sách. Cách đó chỉ cho thấy bean thuộc kiểu `CommandRegistration`; command tạo từ annotation hoặc các nguồn đăng ký khác có thể không xuất hiện trong danh sách bean này. Catalog là nơi tập trung phù hợp hơn để kiểm tra các đăng ký mà shell quản lý.

## 4. Viết thành phần đọc danh sách command

Ta có thể tạo một service nhỏ để đọc catalog, sắp xếp và chuẩn hóa metadata thành cấu trúc dễ kiểm tra.

```java
import java.util.Comparator;
import java.util.List;
import java.util.Objects;
import java.util.stream.Collectors;

import org.springframework.shell.Availability;
import org.springframework.shell.command.CommandCatalog;
import org.springframework.shell.command.CommandRegistration;
import org.springframework.stereotype.Component;

@Component
public class CommandCatalogInspector {

    private final CommandCatalog commandCatalog;

    public CommandCatalogInspector(CommandCatalog commandCatalog) {
        this.commandCatalog = commandCatalog;
    }

    public List<CommandInfo> snapshot() {
        return commandCatalog.getRegistrations().values().stream()
                .map(registration -> {
                    Availability availability = registration.getAvailability();
                    boolean available = availability.isAvailable();

                    return new CommandInfo(
                            registration.getCommand(),
                            Objects.toString(registration.getGroup(), ""),
                            Objects.toString(registration.getDescription(), ""),
                            registration.isHidden(),
                            available,
                            available ? "" : Objects.toString(availability.getReason(), "")
                    );
                })
                .sorted(Comparator.comparing(CommandInfo::command))
                .toList();
    }

    public String format() {
        List<CommandInfo> commands = snapshot();
        if (commands.isEmpty()) {
            return "Không có command nào được đăng ký.";
        }

        return commands.stream()
                .map(command -> {
                    String group = command.group().isBlank()
                            ? "(không có nhóm)" : command.group();
                    String visibility = command.hidden() ? "hidden" : "visible";
                    String state = command.available()
                            ? "available"
                            : "unavailable: " + command.reason();

                    return command.command()
                            + " | " + group
                            + " | " + visibility
                            + " | " + state
                            + " | " + command.description();
                })
                .collect(Collectors.joining(System.lineSeparator()));
    }

    public record CommandInfo(
            String command,
            String group,
            String description,
            boolean hidden,
            boolean available,
            String reason) {
    }
}
```

`CommandCatalogInspector` không đăng ký hoặc thay đổi command. Nó chỉ đọc snapshot hiện tại, chuyển mỗi `CommandRegistration` thành `CommandInfo` rồi sắp xếp theo tên để kết quả dễ so sánh.

Các trường được đọc có ý nghĩa như sau:

| Trường | Ý nghĩa |
|---|---|
| `getCommand()` | Tên command mà người dùng nhập |
| `getGroup()` | Nhóm dùng để tổ chức command |
| `getDescription()` | Mô tả command |
| `isHidden()` | Command được đánh dấu ẩn hay không |
| `getAvailability()` | Trạng thái khả dụng tại thời điểm đọc |
| `getAvailability().getReason()` | Lý do khi command hiện không khả dụng |

### 4.1. Đưa inspector thành command để kiểm tra trong terminal

Nếu muốn người vận hành gọi trực tiếp `commands list`, có thể đăng ký một command programmatic dùng inspector:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.command.CommandRegistration;

@Configuration
public class CommandDiagnosticsConfiguration {

    @Bean
    CommandRegistration commandList(
            CommandCatalogInspector inspector,
            CommandRegistration.BuilderSupplier builders) {
        return builders.get()
                .command("commands list")
                .withTarget()
                    .function(context -> inspector.format())
                    .and()
                .build();
    }
}
```

Trong ứng dụng Boot, bean `CommandRegistration` này được đưa vào catalog theo cơ chế auto-configuration. Sau khi ứng dụng khởi động, có thể nhập:

```text
shell:> commands list
customer list | Customer | visible | available | Liệt kê khách hàng
report status | Reports | visible | available | Xem trạng thái báo cáo
report download | Reports | visible | unavailable: you are not connected | Tải báo cáo
internal refresh | Internal | hidden | available | Làm mới cấu hình nội bộ
commands list | (không có nhóm) | visible | available |
```

Đây là output minh họa. Danh sách thực tế phụ thuộc command được đăng ký trong ứng dụng. Command `commands list` cũng xuất hiện trong chính catalog vì nó là một command đã đăng ký.

## 5. Phân biệt đã đăng ký, bị ẩn và không khả dụng

Không nên gom tất cả trạng thái thành một cờ có/không. Ba khái niệm này trả lời ba câu hỏi khác nhau.

### 5.1. Đã đăng ký

Một command có mặt trong `getRegistrations()` nghĩa là catalog có đăng ký tương ứng. Đây là điều cần xác nhận khi kiểm tra lỗi command không được phát hiện sau cấu hình Spring.

### 5.2. Bị ẩn

`isHidden()` cho biết command được đánh dấu ẩn. Thuộc tính này phục vụ cách tổ chức và hiển thị danh sách command. Một command ẩn vẫn là một đăng ký trong catalog; vì vậy khi kiểm tra toàn bộ cấu hình, không nên loại nó khỏi báo cáo kiểm toán.

Nếu mục tiêu là tạo danh sách thân thiện cho người dùng cuối, có thể lọc bỏ command ẩn. Nếu mục tiêu là chẩn đoán cấu hình, hãy giữ lại và đánh dấu rõ trạng thái `hidden`.

### 5.3. Không khả dụng tại thời điểm hiện tại

Spring Shell cho phép command cung cấp trạng thái `Availability`. Command có thể đã đăng ký nhưng tạm thời không thể chạy do trạng thái ứng dụng.

Ví dụ, `download` chỉ khả dụng khi người dùng đã kết nối:

```java
Availability availability = connected
        ? Availability.available()
        : Availability.unavailable("you are not connected");
```

Với programmatic registration, trạng thái có thể được cung cấp qua `availability(...)` bằng một `Supplier<Availability>`. Với annotation model, có thể khai báo availability provider theo cơ chế mà phiên bản đang dùng hỗ trợ.

Khi hiển thị danh sách, nên giữ command không khả dụng và giải thích lý do. Nếu loại nó khỏi báo cáo, người vận hành có thể nhầm rằng command chưa được đăng ký hoặc bị mất do component scan.

## 6. Kiểm tra ảnh hưởng của cấu hình Spring

Danh sách command là kết quả của cả cấu hình Spring và cấu hình Spring Shell. Khi một command thiếu hoặc thừa, hãy kiểm tra theo thứ tự sau.

### 6.1. Component scan và command target

Với annotation model, xác nhận lớp command được đưa vào ApplicationContext và không bị loại bởi `excludeFilters`, package scan hoặc cấu hình module. Sau đó xác nhận cơ chế đăng ký target được kích hoạt.

Một lớp có `@Component` nhưng phương thức command chưa được đăng ký vẫn có thể tồn tại như bean thông thường. Hãy kiểm tra catalog để xác nhận command thực sự có mặt.

### 6.2. Profile và điều kiện tạo bean

`@Profile`, `@ConditionalOnProperty` và các điều kiện cấu hình khác có thể làm bean command chỉ xuất hiện trong một môi trường. Vì vậy, danh sách ở máy phát triển có thể khác với danh sách trong production.

Khi kiểm tra, ghi lại profile và property đang hoạt động. Kiểm thử tích hợp nên khởi chạy context với cùng profile và cấu hình mà môi trường đích sử dụng.

### 6.3. Command registration bean và customizer

Kiểm tra những bean `CommandRegistration` có được tạo hay không và customizer nào đã bổ sung hoặc loại bỏ đăng ký. Nếu một command được tạo từ cấu hình programmatic, lỗi dependency hoặc điều kiện tạo bean có thể khiến nó không xuất hiện trong catalog.

### 6.4. Resolver động

Nếu ứng dụng dùng `CommandResolver`, command có thể phụ thuộc trạng thái runtime. Hãy kiểm tra kết quả resolver ở trạng thái tương ứng và xác nhận command resolution thực tế. Không nên coi một snapshot khởi động là danh sách bất biến cho toàn bộ phiên shell.

## 7. Kiểm thử danh sách command sau cấu hình

Kiểm thử tích hợp nên xác nhận command quan trọng có mặt trong catalog sau khi Spring tạo context. Đây là cách phát hiện sớm lỗi cấu hình scan, profile hoặc đăng ký programmatic.

```java
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.shell.command.CommandCatalog;

@SpringBootTest
class CommandRegistrationTests {

    @Autowired
    private CommandCatalog commandCatalog;

    @Test
    void registersCustomerListCommand() {
        assertTrue(commandCatalog.getRegistrations().containsKey("customer list"));
    }
}
```

Đây là ví dụ kiểm tra một command cụ thể. Dự án có thể bổ sung các kiểm tra khác:

| Trường hợp | Điều cần xác nhận |
|---|---|
| Command bắt buộc | Có key tương ứng trong catalog |
| Command chỉ dành cho profile riêng | Có hoặc không có đúng theo profile đang chạy |
| Command ẩn | Có đăng ký và `isHidden()` trả về `true` |
| Command phụ thuộc trạng thái | Availability phản ánh đúng trạng thái hiện tại |
| Command programmatic | Bean được đưa vào catalog |
| Command động | Resolver trả về command theo trạng thái đã thiết lập |
| Command trùng tên | Khởi tạo hoặc đăng ký phát hiện xung đột theo quy tắc của phiên bản |

Không chỉ kiểm tra số lượng command. Số lượng có thể vẫn đúng trong khi một command bị thay thế bằng command khác. Hãy kiểm tra các tên command quan trọng, metadata cần thiết và trạng thái khả dụng.

## 8. Vì sao `help` và `CommandCatalog` có thể cho góc nhìn khác nhau?

Lệnh `help` phục vụ người dùng cuối: nó trình bày các command theo cách giao diện shell và cấu hình hiện tại lựa chọn. Catalog phục vụ quản lý và phân giải đăng ký.

Hai góc nhìn có thể khác nhau do:

- Command được đánh dấu ẩn.
- Command hiện không khả dụng.
- Command chỉ phù hợp với một interaction mode.
- Help được tùy chỉnh bằng template hoặc cấu hình trình bày.
- Resolver tạo command động theo trạng thái tại thời điểm phân giải.

Vì vậy, khi người dùng báo một command không xuất hiện trong `help`, hãy kiểm tra catalog trước để xác định command đã được đăng ký hay chưa. Sau đó kiểm tra hidden, availability, interaction mode và cách render help.

## 9. Các lỗi thường gặp

### Command có trong source nhưng không có trong catalog

Kiểm tra lớp command có được Spring phát hiện, cấu hình enablement đã được nạp và package có bị loại khỏi component scan không. Với programmatic registration, kiểm tra bean `CommandRegistration` và điều kiện tạo bean.

### Command có trong catalog nhưng không chạy được

Kiểm tra `getAvailability()` và lý do không khả dụng. Nếu command phụ thuộc kết nối, quyền hoặc trạng thái phiên, cần đưa ứng dụng về trạng thái phù hợp trước khi gọi.

### Command có trong catalog nhưng không có trong help

Kiểm tra cờ hidden, availability, interaction mode và template help. Đừng kết luận command chưa đăng ký chỉ từ màn hình trợ giúp.

### `getBeansOfType(CommandRegistration.class)` thiếu command

Danh sách bean này không đại diện cho mọi nguồn đăng ký. Hãy đọc `CommandCatalog` để xem các registration mà shell quản lý.

### Danh sách thay đổi giữa test và production

So sánh active profiles, property, dependency và các resolver động. Bảo đảm kiểm thử tích hợp dùng cấu hình tương đương môi trường đích.

### Sửa map trả về nhưng command không thay đổi

`getRegistrations()` trả về bản sao. Dùng API `register(...)` hoặc `unregister(...)` trên catalog, hoặc cấu hình customizer phù hợp.

## 10. Lưu ý khi dùng Spring Shell 4.x

Các ví dụ `CommandCatalog` và `CommandRegistration` trong bài này dành cho dòng Spring Shell 3.x. Sang Spring Shell 4.x, API programmatic được thiết kế lại: `CommandRegistry` là điểm quản lý command và command được biểu diễn bằng kiểu `Command`.

Trong 4.x, có thể đọc tập command qua `CommandRegistry.getCommands()`. Nếu chỉ cần chuỗi danh sách command khả dụng và không bị ẩn, tiện ích `Utils.formatAvailableCommands(commandRegistry)` cung cấp cách định dạng sẵn.

Ví dụ:

```java
import org.springframework.shell.core.command.CommandRegistry;
import org.springframework.shell.core.utils.Utils;
import org.springframework.stereotype.Component;

@Component
public class CommandListReporter {

    private final CommandRegistry commandRegistry;

    public CommandListReporter(CommandRegistry commandRegistry) {
        this.commandRegistry = commandRegistry;
    }

    public String availableCommands() {
        return Utils.formatAvailableCommands(commandRegistry);
    }
}
```

Không dùng import `org.springframework.shell.command.CommandCatalog` của 3.x trong ứng dụng 4.x. Khi nâng cấp, hãy kiểm tra migration guide và API reference đúng minor version vì cả kiểu command, registry và cách khởi tạo đã thay đổi.

## 11. Checklist xác minh danh sách command

- [ ] Ứng dụng đã khởi tạo xong Spring ApplicationContext.
- [ ] Đang kiểm tra đúng `CommandCatalog` của context đang chạy trong Spring Shell 3.x.
- [ ] Các lớp command annotation được Spring phát hiện và đăng ký.
- [ ] Các bean `CommandRegistration` được tạo theo đúng profile và điều kiện.
- [ ] Customizer và resolver được kiểm tra nếu ứng dụng sử dụng chúng.
- [ ] Danh sách được sắp xếp và đối chiếu theo tên command quan trọng.
- [ ] Cờ `hidden` được phân biệt với trạng thái không khả dụng.
- [ ] Lý do `Availability` được ghi nhận khi command chưa thể chạy.
- [ ] Kiểm thử tích hợp dùng profile và property phù hợp với môi trường đích.
- [ ] Nếu dùng Spring Shell 4.x, kiểm tra bằng `CommandRegistry` và API 4.x tương ứng.

## 12. Tự kiểm tra

**Câu 1.** Vì sao không thể chỉ tìm các bean `CommandRegistration` để biết toàn bộ command hiệu lực?

**Gợi ý trả lời:** Command có thể được đăng ký từ annotation target, resolver hoặc customizer. `CommandCatalog` là điểm quản lý các registration mà Spring Shell sử dụng.

**Câu 2.** `CommandCatalog.getRegistrations()` trả về kiểu dữ liệu gì và có thể dùng map đó để đăng ký command mới không?

**Gợi ý trả lời:** Phương thức trả về `Map<String, CommandRegistration>` là bản sao. Muốn thay đổi catalog phải gọi `register(...)` hoặc `unregister(...)` trên catalog.

**Câu 3.** Command có trong catalog nhưng `getAvailability().isAvailable()` trả về `false` có nghĩa gì?

**Gợi ý trả lời:** Command đã được đăng ký nhưng điều kiện sử dụng hiện tại chưa thỏa mãn. Có thể đọc `getReason()` để biết lý do.

**Câu 4.** Vì sao danh sách command ở môi trường test có thể khác production?

**Gợi ý trả lời:** Profile, property, dependency, điều kiện tạo bean và trạng thái resolver có thể khác nhau giữa hai môi trường.

**Câu 5.** API nào được dùng để kiểm tra command registry trong Spring Shell 4.x?

**Gợi ý trả lời:** Dùng `CommandRegistry`, có thể lấy tập command qua `getCommands()`; `Utils.formatAvailableCommands(...)` định dạng danh sách command khả dụng và không bị ẩn.

## Kết luận

Muốn biết command nào thực sự được Spring Shell quản lý sau khi Spring cấu hình, hãy kiểm tra catalog/registry của runtime thay vì chỉ đọc source code hoặc danh sách bean. Trong Spring Shell 3.x, `CommandCatalog.getRegistrations()` cung cấp map các `CommandRegistration` cùng metadata để kiểm tra tên, nhóm, mô tả, trạng thái ẩn và khả năng sử dụng.

Hãy phân biệt command đã đăng ký với command đang khả dụng, kiểm tra ảnh hưởng của component scan, profile, customizer và resolver, rồi bảo vệ danh sách mong đợi bằng kiểm thử tích hợp. Khi chuyển sang Spring Shell 4.x, dùng `CommandRegistry` và API mới tương ứng để tránh trộn lẫn hai mô hình registry.

## Tài liệu tham khảo

- [Spring Shell 3.4 — Command Catalog API](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/command/CommandCatalog.html)
- [Spring Shell 3.4 — CommandRegistration API](https://docs.spring.io/spring-shell/reference/3.4/api/java/org/springframework/shell/command/CommandRegistration.html)
- [Spring Shell 3.4 — Command Catalog và resolver](https://docs.spring.io/spring-shell/reference/3.4-SNAPSHOT/appendices/techintro/commandcatalog.html)
- [Spring Shell 4.x — CommandRegistry API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/CommandRegistry.html)
- [Spring Shell 4.x — Utils API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/utils/Utils.html)
- [Spring Shell — Migration guide 4.x](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide)

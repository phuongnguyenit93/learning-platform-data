# AvailabilityProvider và thuộc tính availabilityProvider trong 4.x

Trong một CLI, command có thể đã được đăng ký nhưng chỉ thực hiện được khi ứng dụng ở đúng trạng thái. Ví dụ, người dùng phải kết nối tới máy chủ trước khi tải dữ liệu, chọn workspace trước khi chạy báo cáo hoặc đăng nhập trước khi xem thông tin tài khoản. Spring Shell cung cấp cơ chế command availability để biểu diễn những điều kiện này.

Trong Spring Shell 4.x, cơ chế này xoay quanh hai thành phần: `AvailabilityProvider` tính trạng thái hiện tại và `Availability` mô tả command đang khả dụng hay chưa. Với command khai báo bằng annotation, thuộc tính `availabilityProvider` của `@Command` chỉ tới bean cung cấp trạng thái. Với command tạo bằng code, gọi `.availabilityProvider(...)` trên `Command.Builder`.

## 1. Command được đăng ký chưa chắc đã sẵn sàng để chạy

Đăng ký command xác định những lệnh mà ứng dụng hỗ trợ. Availability mô tả liệu điều kiện để chạy một lệnh đã được đáp ứng tại thời điểm hiện tại hay chưa.

Ví dụ, ứng dụng quản lý máy chủ có hai command:

- `connect`: kết nối tới máy chủ.
- `download`: tải dữ liệu từ máy chủ đã kết nối.

`download` luôn tồn tại trong ứng dụng, nhưng trước khi kết nối thành công, người dùng chưa thể thực hiện nó. Khi đó Spring Shell có thể báo:

~~~text
shell:> download
Command 'download' exists but is not currently available because you are not connected.
~~~

Người dùng biết lệnh có tồn tại và hiểu điều kiện còn thiếu. Sau khi `connect` thành công, trạng thái thay đổi và `download` có thể được gọi.

Availability hữu ích cho những điều kiện phụ thuộc trạng thái runtime như:

- Phiên làm việc đã đăng nhập hoặc kết nối hay chưa.
- Workspace, project hoặc môi trường triển khai đã được chọn hay chưa.
- Dữ liệu nền đã được nạp hoặc một quy trình trước đó đã hoàn tất hay chưa.
- Một thao tác chỉ được phép thực hiện ở trạng thái cụ thể của ứng dụng.

Đối với dữ liệu nhập sai, dùng argument, option và validation. Availability dành cho điều kiện sẵn sàng của command tại thời điểm chạy.

## 2. Availability và AvailabilityProvider trong Spring Shell 4.x

Hai kiểu nằm trong package `org.springframework.shell.core.command.availability`:

| Kiểu | Vai trò |
|---|---|
| `Availability` | Kết quả cho biết command có khả dụng hay không; nếu không, chứa lý do |
| `AvailabilityProvider` | Hợp đồng cung cấp kết quả `Availability` theo trạng thái hiện tại |

`Availability` cung cấp hai factory method:

~~~java
Availability.available()
Availability.unavailable("you are not connected")
~~~

Khi command sẵn sàng, trả về `Availability.available()`. Khi chưa sẵn sàng, trả về `Availability.unavailable(reason)` với một lý do ngắn gọn.

`AvailabilityProvider` là functional interface, có thể triển khai bằng lambda. Provider cung cấp một `Availability` khi được gọi. Do đó, điều kiện được đánh giá dựa trên trạng thái hiện tại thay vì một giá trị cố định tại thời điểm khởi động ứng dụng.

Nếu command không khai báo availability provider, mặc định command được xem là luôn khả dụng.

## 3. Gắn AvailabilityProvider vào command khai báo bằng annotation

Với command dùng `@Command`, thuộc tính `availabilityProvider` nhận tên bean `AvailabilityProvider`. Bean có thể được khai báo bằng `@Bean` trong một lớp cấu hình Spring:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.core.command.availability.Availability;
import org.springframework.shell.core.command.availability.AvailabilityProvider;

@Configuration
class AvailabilityConfiguration {

    @Bean
    AvailabilityProvider downloadAvailability(ConnectionState connectionState) {
        return () -> connectionState.isConnected()
                ? Availability.available()
                : Availability.unavailable("you are not connected");
    }
}
~~~

Tên bean mặc định của phương thức trên là `downloadAvailability`. Command tham chiếu đúng tên đó:

~~~java
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.stereotype.Component;

@Component
class RemoteCommands {

    private final ConnectionState connectionState;
    private final RemoteClient remoteClient;

    RemoteCommands(
            ConnectionState connectionState,
            RemoteClient remoteClient) {
        this.connectionState = connectionState;
        this.remoteClient = remoteClient;
    }

    @Command(name = "connect")
    public String connect(String endpoint) {
        remoteClient.connect(endpoint);
        // Chỉ đánh dấu thành công sau khi remoteClient kết nối thành công.
        connectionState.markConnected();
        return "Đã kết nối tới " + endpoint;
    }

    @Command(name = "disconnect")
    public String disconnect() {
        remoteClient.disconnect();
        connectionState.markDisconnected();
        return "Đã ngắt kết nối.";
    }

    @Command(
            name = "download",
            description = "Tải dữ liệu từ máy chủ",
            availabilityProvider = "downloadAvailability"
    )
    public String download() {
        return "Đã tải dữ liệu.";
    }
}
~~~

Ví dụ dùng `remoteClient` như client của ứng dụng. Chỉ gọi `markConnected()` sau khi kết nối thành công; nếu kết nối thất bại, trạng thái phải tiếp tục là chưa kết nối. Khi ngắt kết nối, cập nhật state sau khi client hoàn tất thao tác.

Lớp lưu trạng thái có thể là một Spring bean dùng chung:

~~~java
import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.stereotype.Component;

@Component
class ConnectionState {

    private final AtomicBoolean connected = new AtomicBoolean(false);

    boolean isConnected() {
        return connected.get();
    }

    void markConnected() {
        connected.set(true);
    }

    void markDisconnected() {
        connected.set(false);
    }
}
~~~

Khi người dùng chạy `connect` thành công, provider đọc trạng thái mới và trả về `Availability.available()`. Trước thời điểm đó, provider trả về lý do `you are not connected`.

Điểm quan trọng là tên trong `availabilityProvider = "downloadAvailability"` phải khớp với tên bean thực tế. Nếu khai báo tên bean tường minh, ví dụ `@Bean("remoteDownloadAvailability")`, thuộc tính `@Command` cũng phải dùng `remoteDownloadAvailability`.

## 4. Gắn provider khi tạo command bằng code

Nếu ứng dụng tạo command bằng `Command.Builder`, có thể truyền provider trực tiếp qua `.availabilityProvider(...)`. Không cần tham chiếu bean bằng chuỗi tên trong trường hợp này:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.core.command.Command;
import org.springframework.shell.core.command.availability.Availability;

@Configuration
class ProgrammaticCommands {

    @Bean
    Command downloadCommand(ConnectionState connectionState) {
        return Command.builder()
                .name("download")
                .description("Tải dữ liệu từ máy chủ")
                .availabilityProvider(() -> connectionState.isConnected()
                        ? Availability.available()
                        : Availability.unavailable("you are not connected"))
                .execute(context ->
                        context.outputWriter().println("Đã tải dữ liệu."))
                .build();
    }
}
~~~

Ở đây lambda được truyền trực tiếp cho builder. Mỗi lần Spring Shell cần xác định trạng thái command, provider đọc `ConnectionState` và tạo kết quả tương ứng.

Chọn cách đăng ký phù hợp với cấu trúc command của ứng dụng:

| Cách đăng ký | Khai báo availability |
|---|---|
| Annotation `@Command` | `availabilityProvider = "beanName"` |
| Lập trình bằng `Command.Builder` | `.availabilityProvider(provider)` |

Không cần tạo hai command trùng tên. Hãy chọn một mô hình đăng ký cho command và gắn availability vào đúng command đó.

## 5. Availability thay đổi theo trạng thái ứng dụng

Một provider thường kiểm tra một hoặc nhiều điều kiện. Ví dụ, command `deploy` chỉ được phép chạy khi đã kết nối và đã chọn project:

~~~java
AvailabilityProvider deployAvailability(
        ConnectionState connectionState,
        ProjectSelection projectSelection) {

    return () -> {
        if (!connectionState.isConnected()) {
            return Availability.unavailable("you are not connected");
        }
        if (!projectSelection.hasProject()) {
            return Availability.unavailable("no project is selected");
        }
        return Availability.available();
    };
}
~~~

Kiểm tra theo thứ tự giúp thông báo chỉ ra điều kiện đầu tiên cần giải quyết. Sau khi kết nối, nếu project chưa được chọn, lý do tiếp theo sẽ là `no project is selected`.

Một số trạng thái thường dùng để quyết định availability:

| Điều kiện | Ví dụ lý do unavailable |
|---|---|
| Chưa đăng nhập | `you are not logged in` |
| Chưa kết nối máy chủ | `you are not connected` |
| Chưa chọn project | `no project is selected` |
| Chưa tải cấu hình | `configuration has not been loaded` |
| Tác vụ đang chạy | `another deployment is in progress` |
| Chưa hoàn tất bước chuẩn bị | `the workspace is not initialized` |

Provider nên đọc trạng thái đã được ứng dụng quản lý, chẳng hạn session service hoặc project context. Không nên thực hiện thao tác có tác dụng phụ trong provider.

## 6. Viết lý do unavailable rõ ràng

Spring Shell nối lý do với câu thông báo theo dạng “because ...”. Vì vậy, tài liệu khuyến nghị viết lý do sao cho đọc tự nhiên sau từ “because”:

- Bắt đầu bằng chữ thường.
- Không thêm dấu chấm ở cuối.
- Nêu điều kiện đang thiếu hoặc trạng thái đang cản trở command.
- Ưu tiên câu ngắn và chỉ dẫn rõ ràng.

Ví dụ tốt:

~~~java
Availability.unavailable("you are not connected")
Availability.unavailable("no project is selected")
Availability.unavailable("the configuration has not been loaded")
~~~

Kết quả hiển thị tự nhiên:

~~~text
Command 'deploy' exists but is not currently available because no project is selected.
~~~

Tránh lý do chung chung như `invalid state`, `not ready` hoặc `error`. Người dùng cần biết họ phải kết nối, chọn project hay chờ tác vụ nào hoàn tất.

Không đặt cả câu hoàn chỉnh bắt đầu bằng chữ hoa và dấu chấm vào `unavailable(reason)`, vì Spring Shell đã thêm phần mở đầu thông báo.

## 7. Availability khác gì với validation, authorization và hidden command?

Các cơ chế này giải quyết những vấn đề khác nhau:

| Cơ chế | Mục đích | Ví dụ |
|---|---|---|
| Availability | Command có thể chạy trong trạng thái hiện tại không? | Chỉ tải dữ liệu sau khi kết nối |
| Validation | Giá trị người dùng nhập có đúng không? | `--limit` phải là số từ 1 đến 500 |
| Authorization | Người dùng có quyền thực hiện thao tác không? | Chỉ quản trị viên được xóa tài khoản |
| Hidden command | Command có được công bố trong danh sách trợ giúp thông thường không? | Lệnh nội bộ phục vụ chẩn đoán |

Một command unavailable vẫn là command đã đăng ký. Availability không có nghĩa là xóa hoặc ẩn command khỏi registry. Khi người dùng gọi command chưa sẵn sàng, shell có thể thông báo command tồn tại nhưng hiện không khả dụng.

Availability cũng không thay thế kiểm tra quyền bảo mật. Provider chủ yếu cải thiện trải nghiệm CLI. Trạng thái có thể thay đổi giữa lúc kiểm tra và lúc thực thi, vì vậy service hoặc hệ thống từ xa vẫn phải kiểm tra quyền và điều kiện quan trọng ngay tại thao tác thực tế.

Tương tự, validation vẫn phải kiểm tra tham số ngay cả khi command đang available. Một command có thể sẵn sàng chạy nhưng nhận `--limit=abc`; đây là lỗi đầu vào, không phải lỗi availability.

## 8. Thiết kế provider ổn định và dễ kiểm thử

Provider có thể được gọi nhiều lần khi shell cần xác định trạng thái command. Hãy giữ logic kiểm tra ngắn, nhanh và không gây tác dụng phụ:

- Đọc trạng thái từ session hoặc state service trong bộ nhớ.
- Không tự kết nối hoặc ngắt kết nối trong provider.
- Tránh tải dữ liệu lớn hoặc gọi mạng chậm mỗi lần kiểm tra.
- Không thay đổi trạng thái ứng dụng khi tính availability.
- Nếu trạng thái phụ thuộc máy chủ, duy trì trạng thái kết nối hoặc health snapshot ở service chuyên trách.

Ví dụ không nên dùng:

~~~java
return () -> remoteClient.connect()
        ? Availability.available()
        : Availability.unavailable("unable to connect");
~~~

Provider này thực hiện kết nối mỗi lần đánh giá availability. Việc kiểm tra trạng thái đã biến thành một thao tác có tác dụng phụ và có thể làm shell chậm.

Nên dùng:

~~~java
return () -> connectionState.isConnected()
        ? Availability.available()
        : Availability.unavailable("you are not connected");
~~~

Khi command bắt đầu chạy, service thực hiện thao tác thật và xử lý lỗi kết nối nếu phiên đã hết hạn. Provider chỉ giúp người dùng biết trạng thái gần nhất mà ứng dụng đang theo dõi.

## 9. Kiểm thử trạng thái khả dụng

Nên kiểm thử cả provider và hành vi của shell.

### Unit test cho provider

Kiểm tra hai trạng thái cơ bản:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.shell.core.command.availability.Availability;
import org.springframework.shell.core.command.availability.AvailabilityProvider;

class DownloadAvailabilityTests {

    private AvailabilityProvider provider(ConnectionState state) {
        return () -> state.isConnected()
                ? Availability.available()
                : Availability.unavailable("you are not connected");
    }

    @Test
    void isUnavailableBeforeConnection() {
        ConnectionState state = new ConnectionState();
        Availability availability = provider(state).get();

        assertThat(availability)
                .isEqualTo(Availability.unavailable("you are not connected"));
    }

    @Test
    void isAvailableAfterConnection() {
        ConnectionState state = new ConnectionState();
        state.markConnected();

        Availability availability = provider(state).get();

        assertThat(availability).isEqualTo(Availability.available());
    }
}
~~~

Trong integration test, tiêm bean `AvailabilityProvider` đã cấu hình vào test và gọi `get()` trên bean đó. Kết hợp với kiểm thử `ShellTestClient` để xác minh cả logic provider lẫn việc command tham chiếu đúng bean name.

### Integration test cho command

Dùng `ShellTestClient` để gửi command khi chưa kết nối và kiểm tra thông báo:

~~~java
ShellScreen screen = client.sendCommand("download");

ShellAssertions.assertThat(screen)
        .containsText("Command 'download' exists")
        .containsText("not currently available")
        .containsText("you are not connected");
~~~

Sau khi chạy command `connect` thành công, gửi lại `download` và xác nhận command thực thi. Bộ test nên bao phủ:

1. Command unavailable khi trạng thái ban đầu chưa đáp ứng.
2. Lý do unavailable chứa đúng điều kiện còn thiếu.
3. Command available sau khi trạng thái thay đổi thành công.
4. Command unavailable trở lại sau khi ngắt kết nối hoặc bỏ chọn project.
5. Provider không tự thay đổi trạng thái trong lúc kiểm tra.

## 10. Khác biệt khi chuyển từ Spring Shell 3.x sang 4.x

Spring Shell 4.x đơn giản hóa cách cấu hình command. Với annotation-based command, availability được khai báo ngay trong `@Command`:

~~~java
@Command(name = "download", availabilityProvider = "downloadAvailability")
public void download() {
    // ...
}
~~~

Trong Spring Shell 3.x, ứng dụng dùng annotation riêng `@CommandAvailability` cùng provider:

~~~java
@Command(command = "download")
@CommandAvailability(provider = "downloadAvailability")
public void download() {
    // ...
}
~~~

Khi nâng lên 4.x, chuyển cấu hình provider vào thuộc tính `availabilityProvider` của `@Command` và loại bỏ annotation cũ theo hướng dẫn migration. Với command đăng ký bằng code, API builder 4.x dùng `.availabilityProvider(...)`; đừng sao chép nguyên cú pháp builder của `CommandRegistration` trong dòng 3.x.

## 11. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Command luôn unavailable | Provider luôn trả `Availability.unavailable(...)` hoặc state không được cập nhật | Kiểm tra luồng cập nhật state sau khi kết nối thành công |
| Command vẫn available dù chưa kết nối | Command chưa tham chiếu đúng provider | Kiểm tra tên bean trong `availabilityProvider` |
| Không tìm thấy provider bean | Tên bean bị sai hoặc bean không nằm trong Spring context | Dùng đúng bean name và kiểm tra cấu hình Spring |
| Thông báo lý do khó đọc | Reason là câu hoàn chỉnh, viết hoa hoặc có dấu chấm cuối | Viết phần tiếp nối tự nhiên sau từ “because” |
| Provider làm shell chậm | Provider gọi mạng hoặc thực hiện công việc nặng | Đọc trạng thái đã lưu trong state/session service |
| Command chạy dù trạng thái vừa thay đổi | Trạng thái đổi sau lần kiểm tra availability | Kiểm tra lại điều kiện trong service khi thực thi |
| Dùng availability để bảo vệ thao tác nhạy cảm | Availability bị xem như cơ chế phân quyền | Kiểm tra authorization ở service hoặc hệ thống từ xa |
| Code 3.x không biên dịch ở 4.x | Vẫn dùng `@CommandAvailability` hoặc API cũ | Chuyển sang thuộc tính `@Command(availabilityProvider = ...)` |

## 12. Bài tập thực hành

Xây dựng CLI quản lý môi trường triển khai với các command:

- `login`: đăng nhập và cập nhật trạng thái phiên.
- `select-project`: chọn project đang làm việc.
- `deploy`: chỉ khả dụng khi đã đăng nhập và có project được chọn.
- `logout`: kết thúc phiên và xóa trạng thái kết nối.

Yêu cầu:

1. Tạo state service lưu trạng thái đăng nhập và project hiện tại.
2. Khai báo bean `AvailabilityProvider` tên `deployAvailability`.
3. Gắn provider vào command `deploy` bằng thuộc tính `availabilityProvider`.
4. Trả lý do `you are not logged in` nếu chưa đăng nhập.
5. Trả lý do `no project is selected` nếu đã đăng nhập nhưng chưa chọn project.
6. Chỉ trả `Availability.available()` khi cả hai điều kiện đều đúng.
7. Viết test cho các trạng thái trước login, sau login, sau chọn project và sau logout.

Thử theo trình tự:

~~~text
deploy
login
deploy
select-project demo
deploy
logout
deploy
~~~

Quan sát lý do thay đổi theo state và xác nhận command `deploy` chỉ chạy khi điều kiện đã đáp ứng.

## Tài liệu tham khảo

- [Spring Shell – Command Availability](https://docs.spring.io/spring-shell/reference/commands/availability.html)
- [Spring Shell API – Availability](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/availability/Availability.html)
- [Spring Shell API – AvailabilityProvider](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/availability/AvailabilityProvider.html)
- [Spring Shell API – @Command](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/Command.html)
- [Spring Shell API – Command.Builder](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/Command.Builder.html)
- [Spring Shell – Migration Guide from 3.x to 4.x](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide)

# Mô phỏng kết nối rồi thay đổi availability theo trạng thái phiên

Trong một CLI quản trị, có những command chỉ hợp lệ sau khi người dùng hoàn thành một bước chuẩn bị. Ví dụ, người vận hành cần kết nối tới máy chủ trước khi xem danh sách tệp hoặc tải dữ liệu. Khi chưa kết nối, các command đó vẫn cần xuất hiện trong help để người dùng biết chúng tồn tại, nhưng Spring Shell phải giải thích vì sao chưa thể chạy.

Spring Shell 3.3 cung cấp `Availability` và `@ShellMethodAvailability` để mô tả trạng thái này. Một phương thức kiểm tra có thể đọc trạng thái kết nối hiện tại và trả về `Availability.available()` hoặc `Availability.unavailable(reason)`. Khi command `connect` thay đổi trạng thái phiên, các command phụ thuộc được đánh giá lại theo trạng thái mới.

Bài thực hành xây dựng một phiên kết nối máy chủ từ xa được mô phỏng trong bộ nhớ. Người dùng chạy `connect`, sau đó có thể chạy `remote list` và `remote download`. Khi chạy `disconnect`, các command cần kết nối trở lại trạng thái unavailable. Không có kết nối mạng thật trong bài này; mục tiêu là hiểu cách quản lý trạng thái phiên và điều khiển command availability.

Sau bài này, bạn có thể:

- Mô hình hóa trạng thái kết nối của một phiên shell.
- Tách trạng thái phiên khỏi lớp command.
- Dùng `Availability.available()` và `Availability.unavailable(reason)`.
- Gắn một phương thức availability cho một command bằng `@ShellMethodAvailability`.
- Dùng một phương thức availability chung cho nhiều command.
- Thay đổi trạng thái sau `connect` và `disconnect`.
- Chỉ chuyển sang trạng thái connected sau khi thao tác kết nối thành công.
- Bảo vệ service bằng cách kiểm tra trạng thái trước khi thực hiện nghiệp vụ.
- Kiểm thử trạng thái và hành vi command bằng unit test và `@ShellTest`.
- Phân biệt trạng thái phiên của một tiến trình CLI với session của ứng dụng web nhiều người dùng.

> Ví dụ dùng Spring Shell 3.3.4, Spring Boot 3.x và Java 17 trở lên. Phần annotation sử dụng mô hình legacy `@ShellComponent`, `@ShellMethod` và `@ShellMethodAvailability` của Spring Shell 3.x.

## 1. Bài toán: command phụ thuộc trạng thái kết nối

Giả sử ứng dụng quản trị một máy chủ lưu trữ tệp. Người dùng cần thực hiện các thao tác:

| Command | Điều kiện |
|---|---|
| `status` | Luôn khả dụng |
| `connect --host --user` | Chỉ khả dụng khi chưa có kết nối |
| `disconnect` | Chỉ khả dụng khi đang kết nối |
| `remote list` | Chỉ khả dụng khi đang kết nối |
| `remote download --file` | Chỉ khả dụng khi đang kết nối |

Nếu người dùng chạy `remote list` ngay sau khi mở shell, Spring Shell nên thông báo command hiện có nhưng chưa khả dụng vì chưa kết nối. Sau khi kết nối thành công, `remote list` và `remote download` được bật. Khi disconnect, chúng bị khóa lại.

Đây là bài toán command availability động. Command được đăng ký khi ứng dụng khởi động, còn khả năng thực thi được xác định theo trạng thái hiện tại.

## 2. Mô hình trạng thái phiên

Trong bài thực hành, phiên kết nối có hai trạng thái:

- `DISCONNECTED`: chưa có kết nối tới máy chủ.
- `CONNECTED`: đã thiết lập kết nối mô phỏng với một máy chủ và tài khoản.

Các chuyển trạng thái:

~~~mermaid
stateDiagram-v2
    [*] --> DISCONNECTED
    DISCONNECTED --> CONNECTED: connect thành công
    CONNECTED --> DISCONNECTED: disconnect
    CONNECTED --> DISCONNECTED: mất kết nối / hết hạn
    DISCONNECTED --> DISCONNECTED: connect thất bại
~~~

Trạng thái kết nối chỉ được cập nhật sau khi thao tác mô phỏng thành công. Nếu máy chủ mô phỏng không phản hồi, phiên vẫn ở `DISCONNECTED`. Khi disconnect hoặc phát hiện kết nối bị mất, thông tin kết nối phải được xóa để command phụ thuộc không còn khả dụng.

### Availability thay đổi theo trạng thái

| Trạng thái hiện tại | `connect` | `disconnect` | `remote list` | `remote download` |
|---|---|---|---|---|
| `DISCONNECTED` | Available | Unavailable | Unavailable | Unavailable |
| `CONNECTED` | Unavailable | Available | Available | Available |
| Kết nối bị mất | Available | Unavailable | Unavailable | Unavailable |

`status` luôn available để người dùng biết phiên đang ở trạng thái nào.

## 3. Availability trong Spring Shell hoạt động thế nào?

Spring Shell biểu diễn trạng thái bằng lớp `Availability`:

~~~java
Availability.available()
Availability.unavailable("you are not connected")
~~~

`available()` cho biết command có thể được gọi. `unavailable(reason)` cho biết command đang bị khóa và cung cấp lý do. Spring Shell hiển thị lý do này khi người dùng cố chạy command, đồng thời thông tin availability cũng được dùng trong help tích hợp.

Ví dụ thông báo:

~~~text
shell:>remote list
Command 'remote list' exists but is not currently available because you are not connected to a remote host.
~~~

Lý do truyền vào `unavailable(...)` được nối sau từ “because”. Vì vậy, hãy viết lý do như một cụm tiếp nối tự nhiên, bắt đầu bằng chữ thường và không có dấu chấm cuối câu. Với tiếng Việt, có thể dùng:

Với thông báo mặc định bằng tiếng Anh của Spring Shell 3.3, reason nên tiếp nối tự nhiên sau từ “because”, ví dụ:

~~~java
Availability.unavailable("you are not connected to a remote host")
~~~

Nếu ứng dụng đã tùy chỉnh thông báo availability sang tiếng Việt, hãy dịch cả phần mở đầu và reason để câu hiển thị thống nhất.

### Gắn availability cho một command

Đặt `@ShellMethodAvailability` trên method command để chỉ định tên method kiểm tra:

~~~java
@ShellMethod(key = "remote list")
@ShellMethodAvailability("remoteListAvailability")
public String list() {
    // ...
}

public Availability remoteListAvailability() {
    return connected
            ? Availability.available()
            : Availability.unavailable("bạn chưa kết nối tới máy chủ từ xa");
}
~~~

Method kiểm tra không nhận tham số và trả về `Availability`.

### Dùng một availability method cho nhiều command

Khi nhiều command phụ thuộc cùng trạng thái, đặt annotation trên method kiểm tra và liệt kê tên command:

~~~java
@ShellMethodAvailability({"disconnect", "remote list", "remote download"})
public Availability connectedCommandsAvailability() {
    return connected
            ? Availability.available()
            : Availability.unavailable("bạn chưa kết nối tới máy chủ từ xa");
}
~~~

Giá trị trong annotation là tên command hoặc alias được đăng ký. Nếu bỏ danh sách, giá trị mặc định `*` áp dụng cho mọi command trong class. Chỉ dùng wildcard khi tất cả command trong class thật sự có cùng điều kiện; nếu không, các command như `status` hoặc `connect` cũng có thể bị khóa ngoài ý muốn.

## 4. Tổ chức lớp giữ trạng thái phiên

Không nên đặt biến `connected` riêng trong từng command. Nếu `connect`, `remote list` và `disconnect` giữ các biến khác nhau, chúng có thể không đồng bộ. Tạo một bean dùng chung để lưu thông tin kết nối:

~~~java
import java.time.Instant;

import org.springframework.stereotype.Component;

@Component
public class RemoteSession {

    private ConnectionInfo connection;

    public synchronized ConnectionInfo connect(String host, String username) {
        if (connection != null) {
            throw new IllegalStateException("a connection is already active");
        }
        if (host == null || host.isBlank()) {
            throw new IllegalArgumentException("host must not be blank");
        }
        if (username == null || username.isBlank()) {
            throw new IllegalArgumentException("username must not be blank");
        }

        // Mô phỏng một máy chủ không phản hồi để kiểm tra nhánh thất bại.
        if ("offline".equalsIgnoreCase(host)) {
            throw new IllegalStateException("the simulated server is unavailable");
        }

        // Chỉ ghi trạng thái sau khi bước kết nối mô phỏng thành công.
        connection = new ConnectionInfo(host, username, Instant.now());
        return connection;
    }

    public synchronized void disconnect() {
        connection = null;
    }

    public synchronized boolean isConnected() {
        return connection != null;
    }

    public synchronized ConnectionInfo requireConnection() {
        if (connection == null) {
            throw new IllegalStateException("not connected to a remote host");
        }
        return connection;
    }

    public synchronized String describe() {
        if (connection == null) {
            return "Trạng thái: DISCONNECTED";
        }
        return "Trạng thái: CONNECTED, host=%s, user=%s, since=%s"
                .formatted(
                        connection.host(),
                        connection.username(),
                        connection.connectedAt());
    }

    public record ConnectionInfo(
            String host,
            String username,
            Instant connectedAt) {
    }
}
~~~

Một số quyết định trong lớp này:

- Thông tin kết nối được gom trong một record bất biến.
- `synchronized` giữ cho các thao tác đọc và thay đổi trạng thái nhất quán nếu có tác vụ khác truy cập đồng thời.
- `connect` từ chối kết nối thứ hai khi phiên đang hoạt động.
- Host `offline` được dành riêng để mô phỏng lỗi kết nối.
- Trạng thái chỉ được ghi sau khi các bước kiểm tra thành công.
- `requireConnection()` bảo vệ service khi thao tác cần kết nối.

Trong ứng dụng thật, phần mô phỏng `offline` sẽ được thay bằng lời gọi client hoặc gateway kết nối. Chỉ gọi `session.connect(...)` sau khi handshake thành công. Nếu handshake thất bại, không được để phiên chuyển sang `CONNECTED`.

## 5. Tạo service mô phỏng dữ liệu từ xa

Service không cần biết command nào đang available. Nó nhận thông tin kết nối đã được xác thực trạng thái và thực hiện nghiệp vụ:

~~~java
import java.util.List;

import org.springframework.stereotype.Service;

@Service
public class SimulatedRemoteCatalog {

    public List<String> listFiles(RemoteSession.ConnectionInfo connection) {
        return List.of(
                "daily-report.csv",
                "inventory.json",
                "users.csv");
    }

    public String download(
            RemoteSession.ConnectionInfo connection,
            String fileName) {

        if (!listFiles(connection).contains(fileName)) {
            throw new IllegalArgumentException("file does not exist: " + fileName);
        }

        return "Đã tải " + fileName + " từ " + connection.host();
    }
}
~~~

Trong ứng dụng thật, service có thể dùng `connection.host()` để chọn client hoặc endpoint. Không truyền password qua command line trong ví dụ này. Nếu cần credential, hãy dùng cơ chế nhập bí mật hoặc credential provider phù hợp.

## 6. Xây dựng các command điều khiển phiên

Class dưới đây gom các command có chung trạng thái phiên. `connect` chỉ khả dụng khi chưa kết nối; `disconnect`, `remote list` và `remote download` dùng chung điều kiện connected:

~~~java
import org.springframework.shell.Availability;
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;
import org.springframework.shell.standard.ShellMethodAvailability;
import org.springframework.shell.standard.ShellOption;

@ShellComponent
public class RemoteCommands {

    private final RemoteSession session;
    private final SimulatedRemoteCatalog catalog;

    public RemoteCommands(
            RemoteSession session,
            SimulatedRemoteCatalog catalog) {
        this.session = session;
        this.catalog = catalog;
    }

    @ShellMethod(
            key = "connect",
            value = "Kết nối tới máy chủ từ xa mô phỏng.")
    @ShellMethodAvailability("connectAvailability")
    public String connect(
            @ShellOption("--host") String host,
            @ShellOption("--user") String username) {

        RemoteSession.ConnectionInfo connection =
                session.connect(host, username);

        return "Đã kết nối tới " + connection.host()
                + " bằng tài khoản " + connection.username();
    }

    public Availability connectAvailability() {
        return session.isConnected()
                ? Availability.unavailable(
                        "a connection is already active; run disconnect first")
                : Availability.available();
    }

    @ShellMethod(key = "status", value = "Xem trạng thái phiên kết nối.")
    public String status() {
        return session.describe();
    }

    @ShellMethod(key = "disconnect", value = "Ngắt kết nối khỏi máy chủ.")
    public String disconnect() {
        session.disconnect();
        return "Đã ngắt kết nối";
    }

    @ShellMethodAvailability({
            "disconnect",
            "remote list",
            "remote download"
    })
    public Availability connectedCommandsAvailability() {
        return session.isConnected()
                ? Availability.available()
                : Availability.unavailable(
                        "you are not connected to a remote host");
    }

    @ShellMethod(key = "remote list", value = "Liệt kê tệp trên máy chủ.")
    public String list() {
        RemoteSession.ConnectionInfo connection = session.requireConnection();
        return "Các tệp trên " + connection.host() + ":\n"
                + String.join("\n", catalog.listFiles(connection));
    }

    @ShellMethod(
            key = "remote download",
            value = "Tải một tệp từ máy chủ mô phỏng.")
    public String download(@ShellOption("--file") String fileName) {
        RemoteSession.ConnectionInfo connection = session.requireConnection();
        return catalog.download(connection, fileName);
    }
}
~~~

### Tại sao có hai phương thức kiểm tra?

`connectAvailability()` chỉ kiểm soát command `connect`. Khi phiên đã kết nối, không cho phép gọi connect lần nữa; người dùng cần disconnect trước.

`connectedCommandsAvailability()` kiểm soát nhóm command cần kết nối. Một phương thức duy nhất giữ cho `disconnect`, `remote list` và `remote download` có cùng quy tắc. Khi session đổi trạng thái, tất cả command trong nhóm cùng thay đổi availability.

`status` không nằm trong nhóm này vì người dùng phải luôn có cách xem trạng thái. Nếu đặt `status` vào nhóm connected, người dùng sẽ không thể hỏi vì sao các command khác đang bị khóa.

## 7. Chạy thử toàn bộ luồng

Khởi động ứng dụng ở interactive mode, sau đó thực hiện các lệnh theo thứ tự:

### Bước 1: Kiểm tra trạng thái ban đầu

~~~text
shell:>status
Trạng thái: DISCONNECTED
~~~

Command `connect` khả dụng. Các command cần kết nối chưa khả dụng.

### Bước 2: Thử command trước khi kết nối

~~~text
shell:>remote list
Command 'remote list' exists but is not currently available because bạn chưa kết nối tới máy chủ từ xa.
~~~

Thông báo cho biết command đã đăng ký nhưng chưa thể thực thi.

### Bước 3: Kết nối thành công

~~~text
shell:>connect --host demo.example.test --user alice
Đã kết nối tới demo.example.test bằng tài khoản alice

shell:>status
Trạng thái: CONNECTED, host=demo.example.test, user=alice, ...
~~~

Sau khi `session.connect(...)` hoàn tất, `connectedCommandsAvailability()` trả về available. `connectAvailability()` trả về unavailable.

### Bước 4: Chạy command phụ thuộc kết nối

~~~text
shell:>remote list
Các tệp trên demo.example.test:
daily-report.csv
inventory.json
users.csv

shell:>remote download --file inventory.json
Đã tải inventory.json từ demo.example.test
~~~

### Bước 5: Ngắt kết nối

~~~text
shell:>disconnect
Đã ngắt kết nối

shell:>status
Trạng thái: DISCONNECTED
~~~

Sau bước này, `remote list`, `remote download` và `disconnect` trở lại unavailable. `connect` được bật lại.

### Bước 6: Mô phỏng kết nối thất bại

~~~text
shell:>connect --host offline --user alice
the simulated server is unavailable

shell:>status
Trạng thái: DISCONNECTED
~~~

Lớp `RemoteSession` chỉ cập nhật `connection` sau khi kiểm tra mô phỏng thành công. Vì vậy, lỗi kết nối không để lại trạng thái connected giả.

## 8. Availability không thay thế kiểm tra nghiệp vụ

Availability giúp giao diện shell hướng dẫn người dùng. Nó không phải cơ chế bảo mật và không thay thế validation ở service.

Có ba lý do:

1. Trạng thái có thể thay đổi sau khi shell kiểm tra availability nhưng trước khi command thực thi.
2. Service có thể được gọi từ một luồng khác, không thông qua command shell.
3. Một ứng dụng có nhiều người dùng hoặc nhiều tiến trình không thể dựa vào một cờ boolean toàn cục để phân quyền.

Vì vậy, command `remote list` vẫn gọi `session.requireConnection()` trước khi truy cập catalog. Service thật cũng phải kiểm tra quyền, trạng thái credential và điều kiện nghiệp vụ của thao tác.

Không dùng availability để che giấu một command nhạy cảm thay cho authorization. Nếu người dùng không có quyền tải tệp, service phải từ chối thao tác ngay cả khi command đang available.

## 9. Quản lý phạm vi và vòng đời của trạng thái phiên

Trong bài thực hành, `RemoteSession` là một Spring bean tồn tại trong một application context. Điều này phù hợp với một tiến trình shell và một người vận hành tại một thời điểm.

Hãy phân biệt ba phạm vi:

| Phạm vi | Ví dụ | Nơi lưu trạng thái phù hợp |
|---|---|---|
| Một command invocation | Giá trị option của một lần gọi | Tham số command hoặc `CommandContext` |
| Một tiến trình shell | Một người vận hành dùng REPL trong một tiến trình | Bean giữ trạng thái trong bộ nhớ |
| Nhiều người dùng/phiên đồng thời | Nhiều terminal hoặc nhiều người dùng qua một dịch vụ chung | Trạng thái được khóa theo principal hoặc session identifier |

Nếu một ứng dụng phục vụ nhiều người dùng đồng thời, không dùng một field `connection` chung cho mọi người. Một người dùng có thể connect trong khi người khác chưa connect; state singleton sẽ làm availability của hai người ảnh hưởng lẫn nhau. Khi đó, cần một kho trạng thái có khóa theo danh tính người dùng hoặc session ID do lớp tích hợp cung cấp.

Trạng thái trong bộ nhớ cũng mất khi tiến trình khởi động lại. Nếu kết nối cần được khôi phục sau restart, phải thiết kế cơ chế reconnect và kiểm tra credential riêng; không serialize một kết nối mạng đang mở rồi xem nó như phiên còn hợp lệ.

### Khi kết nối hết hạn hoặc bị mất

Trong ứng dụng thực tế, connection có thể mất do timeout, server đóng socket hoặc credential hết hạn. Khi phát hiện lỗi:

1. Đánh dấu phiên disconnected.
2. Đóng tài nguyên client cũ.
3. Xóa token hoặc thông tin tạm thời không còn hợp lệ.
4. Trả thông báo dễ hiểu.
5. Để availability provider đọc trạng thái mới ở lần kiểm tra tiếp theo.

Không giữ `CONNECTED` chỉ vì lần connect ban đầu từng thành công. Trạng thái phiên phải phản ánh khả năng thực hiện thao tác tại thời điểm hiện tại.

## 10. Kiểm thử trạng thái và availability

Nên kiểm thử hai lớp riêng:

- Unit test cho state holder và các phương thức availability.
- Shell integration test để xác nhận Spring Shell thực sự chặn hoặc cho chạy command theo trạng thái.

### Unit test cho chuyển trạng thái

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;

class RemoteSessionTest {

    @Test
    void stateChangesAfterConnectAndDisconnect() {
        RemoteSession session = new RemoteSession();

        assertThat(session.isConnected()).isFalse();

        session.connect("demo.example.test", "alice");

        assertThat(session.isConnected()).isTrue();
        assertThat(session.requireConnection().host())
                .isEqualTo("demo.example.test");

        session.disconnect();

        assertThat(session.isConnected()).isFalse();
        assertThatThrownBy(session::requireConnection)
                .isInstanceOf(IllegalStateException.class);
    }

    @Test
    void failedConnectionLeavesSessionDisconnected() {
        RemoteSession session = new RemoteSession();

        assertThatThrownBy(() -> session.connect("offline", "alice"))
                .isInstanceOf(IllegalStateException.class);

        assertThat(session.isConnected()).isFalse();
    }
}
~~~

### Unit test cho availability method

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

class RemoteCommandsAvailabilityTest {

    @Test
    void availabilityFollowsSessionState() {
        RemoteSession session = new RemoteSession();
        RemoteCommands commands =
                new RemoteCommands(session, new SimulatedRemoteCatalog());

        assertThat(commands.connectAvailability().isAvailable()).isTrue();
        assertThat(commands.connectedCommandsAvailability().isAvailable())
                .isFalse();

        session.connect("demo.example.test", "alice");

        assertThat(commands.connectAvailability().isAvailable()).isFalse();
        assertThat(commands.connectedCommandsAvailability().isAvailable())
                .isTrue();

        session.disconnect();

        assertThat(commands.connectAvailability().isAvailable()).isTrue();
        assertThat(commands.connectedCommandsAvailability().isAvailable())
                .isFalse();
    }
}
~~~

Unit test này xác nhận cả hai chiều chuyển trạng thái. Nó không thay thế test đăng ký command vì việc Spring Shell liên kết annotation với method availability cần được kiểm tra ở mức tích hợp.

### Shell integration test với @ShellTest

`ShellTestClient` có thể mở interactive session, gửi chuỗi lệnh và đọc màn hình giả lập. Ví dụ:

~~~java
import static org.awaitility.Awaitility.await;

import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.context.annotation.Import;
import org.springframework.shell.test.ShellAssertions;
import org.springframework.shell.test.ShellTestClient;
import org.springframework.shell.test.ShellTestClient.InteractiveShellSession;
import org.springframework.shell.test.autoconfigure.ShellTest;

@ShellTest
@Import({RemoteSession.class, SimulatedRemoteCatalog.class, RemoteCommands.class})
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class RemoteShellAvailabilityTest {

    @Autowired
    ShellTestClient client;

    @Test
    void commandAvailabilityChangesWithConnectionState() {
        InteractiveShellSession session = client.interactive().run();

        send(session, "remote list");
        await().atMost(2, TimeUnit.SECONDS).untilAsserted(() ->
                ShellAssertions.assertThat(session.screen())
                        .containsText("not currently available"));

        send(session, "connect --host demo.example.test --user alice");
        await().atMost(2, TimeUnit.SECONDS).untilAsserted(() ->
                ShellAssertions.assertThat(session.screen())
                        .containsText("Đã kết nối tới demo.example.test"));

        send(session, "remote list");
        await().atMost(2, TimeUnit.SECONDS).untilAsserted(() ->
                ShellAssertions.assertThat(session.screen())
                        .containsText("daily-report.csv"));

        send(session, "disconnect");
        await().atMost(2, TimeUnit.SECONDS).untilAsserted(() ->
                ShellAssertions.assertThat(session.screen())
                        .containsText("Đã ngắt kết nối"));
    }

    private static void send(
            InteractiveShellSession session,
            String command) {
        session.write(
                session.writeSequence()
                        .text(command)
                        .carriageReturn()
                        .build());
    }
}
~~~

Ví dụ dùng `@Import` để đưa ba bean của bài thực hành vào test context. Trong dự án có `@SpringBootApplication` riêng, có thể dùng cấu hình test của ứng dụng thay cho danh sách import. `@DirtiesContext` tạo context mới sau mỗi test method, tránh trạng thái phiên từ test trước ảnh hưởng test sau.

Khi mở rộng bài test, hãy kiểm tra thêm:

- `connect` bị khóa khi đã có phiên kết nối.
- `disconnect` bị khóa khi chưa kết nối.
- `remote download` bị khóa trước khi connect.
- Sau disconnect, `remote list` lại bị từ chối.
- Host `offline` làm connect thất bại và phiên vẫn disconnected.
- Help hiển thị lý do unavailable đúng với trạng thái.

## 11. Nếu dùng Spring Shell 4

Spring Shell 4 loại bỏ các annotation legacy `@ShellComponent`, `@ShellMethod`, `@ShellOption` và `@ShellMethodAvailability`. Mô hình mới dùng `@Command` cùng thuộc tính `availabilityProvider`, trỏ tới một bean `AvailabilityProvider`.

Ví dụ rút gọn:

~~~java
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.availability.Availability;
import org.springframework.shell.core.command.availability.AvailabilityProvider;
import org.springframework.context.annotation.Bean;
import org.springframework.stereotype.Component;

@Component
public class RemoteCommandsV4 {

    private final RemoteSession session;

    public RemoteCommandsV4(RemoteSession session) {
        this.session = session;
    }

    @Command(name = "remote list", availabilityProvider = "connectedAvailability")
    public String list() {
        RemoteSession.ConnectionInfo connection = session.requireConnection();
        return "Đang liệt kê tệp trên " + connection.host();
    }

    @Bean
    AvailabilityProvider connectedAvailability() {
        return () -> session.isConnected()
                ? Availability.available()
                : Availability.unavailable(
                        "you are not connected to a remote host");
    }
}
~~~

Đây chỉ là ví dụ chuyển cơ chế availability. Khi nâng cấp toàn bộ command, cần chuyển cả option, argument, package và test API theo migration guide của Spring Shell 4. Không trộn `@ShellMethodAvailability` của v3 với `@Command` của v4 trong cùng một ví dụ.

## 12. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `remote list` luôn unavailable | State holder không được chia sẻ giữa command và availability method | Inject cùng một bean `RemoteSession` |
| `remote list` luôn available | Method availability không được phát hiện hoặc annotation trỏ sai tên | Kiểm tra tên method và `@ShellMethodAvailability` |
| `connect` vẫn chạy khi đã kết nối | Chưa gắn availability riêng cho connect | Thêm `connectAvailability()` |
| `status` cũng bị khóa | Dùng wildcard `*` cho toàn bộ command trong class | Chỉ liệt kê các command thực sự cần kết nối |
| Command được bật dù kết nối thất bại | Đặt state connected trước khi handshake thành công | Chỉ cập nhật state sau khi kết nối thành công |
| Command chạy nhưng service không có connection | Chỉ kiểm tra availability ở giao diện | Gọi `requireConnection()` trong đường nghiệp vụ |
| Test lúc pass lúc fail | State bean được dùng chung giữa các test | Reset state hoặc dùng `@DirtiesContext` |
| Người dùng khác thấy trạng thái kết nối của nhau | Dùng một singleton state cho nhiều phiên/người dùng | Lưu state theo principal hoặc session ID |
| Thông báo unavailable không tự nhiên | Reason có viết hoa hoặc dấu chấm cuối | Viết reason như phần tiếp nối sau “because” |
| Kết nối cũ vẫn được xem là hợp lệ | Không cập nhật state khi timeout hoặc mất mạng | Xóa connection và đóng client khi phát hiện lỗi |

## 13. Checklist hoàn thành bài thực hành

- Có một bean riêng lưu trạng thái kết nối.
- Trạng thái ban đầu là disconnected.
- `connect` chỉ khả dụng khi chưa có kết nối.
- `disconnect`, `remote list` và `remote download` chỉ khả dụng khi đã kết nối.
- `status` luôn khả dụng.
- Kết nối thất bại không làm state chuyển sang connected.
- Disconnect xóa thông tin kết nối.
- Các command phụ thuộc gọi `requireConnection()` trước khi xử lý.
- Availability reason ngắn, dễ hiểu và đúng ngữ cảnh.
- Unit test xác nhận cả hai chiều chuyển trạng thái.
- Shell integration test xác nhận command bị chặn và được bật đúng lúc.
- Test context được reset để không rò trạng thái giữa các test.
- Phạm vi state phù hợp với số lượng người dùng/phiên thực tế.
- Có kế hoạch xử lý timeout, mất kết nối và reconnect.

## 14. Bài tập mở rộng

Mở rộng ứng dụng quản trị từ xa:

1. Thêm command `remote upload --file` chỉ khả dụng khi đã kết nối.
2. Thêm command `connect` không cho kết nối trùng khi phiên đang hoạt động.
3. Thêm command `status` hiển thị host, username và thời điểm kết nối.
4. Thêm trạng thái `EXPIRED` khi thời gian kết nối vượt quá giới hạn mô phỏng.
5. Khi phiên hết hạn, tự chuyển về disconnected và cập nhật availability.
6. Thêm command `reconnect` chỉ khả dụng khi phiên bị mất hoặc hết hạn.
7. Tạo test xác nhận command availability thay đổi sau mỗi chuyển trạng thái.
8. Thử chạy command trước khi kết nối, sau khi kết nối và sau khi disconnect.
9. Thêm test cho lỗi host `offline` và xác nhận state không bị thay đổi.
10. Thiết kế phiên bản có nhiều người dùng, lưu state theo user ID thay vì một field toàn cục.

Khi hoàn thành, hãy giải thích vì sao availability là một phần của trải nghiệm command, còn việc kiểm tra kết nối và quyền truy cập vẫn phải nằm trong service nghiệp vụ.

## Tài liệu tham khảo

- [Spring Shell 3.3 – Command Availability](https://docs.spring.io/spring-shell/reference/3.3/commands/availability.html): `Availability`, `@ShellMethodAvailability`, availability method dùng chung và thông báo unavailable.
- [Spring Shell 3.3 – Testing Basics](https://docs.spring.io/spring-shell/reference/3.3/testing/basics.html): `@ShellTest`, `ShellTestClient`, interactive session và kiểm tra màn hình.
- [Spring Shell 3.3.0 – ShellMethodAvailability API](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/standard/ShellMethodAvailability.html): cách ánh xạ availability method tới command name hoặc alias.
- [Spring Shell 3.3.0 – Availability API](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/Availability.html): trạng thái available/unavailable và lý do.
- [Spring Shell – v4 Migration Guide](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide): chuyển từ annotation legacy sang `@Command` và `availabilityProvider`.

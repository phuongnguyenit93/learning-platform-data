# Kiểm tra availability, trạng thái phiên và đường đi sau lỗi

Một command có thể được đăng ký trong Spring Shell nhưng chỉ hợp lệ khi ứng dụng đang ở đúng trạng thái. Ví dụ, người dùng phải kết nối tới máy chủ trước khi tải dữ liệu; phải chọn môi trường trước khi triển khai; hoặc phải xác thực trước khi xem thông tin riêng tư. Kiểm thử riêng phần thân command chưa đủ để chứng minh các điều kiện này được áp dụng đúng trong một phiên shell thực tế.

Spring Shell cung cấp `Availability` để biểu thị command có thể chạy hay chưa, `@ShellMethodAvailability` để nối điều kiện đó với command và các tiện ích kiểm thử terminal để mô phỏng một phiên tương tác. Khi kết hợp chúng, có thể kiểm tra toàn bộ vòng đời: command bị khóa khi chưa kết nối, mở sau khi kết nối thành công, bị khóa lại khi ngắt kết nối và vẫn xử lý đúng khi một thao tác phát sinh lỗi.

Bài viết sử dụng Spring Shell 3.4.x với mô hình annotation legacy `@ShellMethod`. Các ví dụ tập trung vào `@ShellTest`, `ShellTestClient`, `InteractiveShellSession`, `Availability` và `@ExceptionResolver`.

## Phân biệt availability với kết quả thực thi

Availability là điều kiện cho biết command có được phép bắt đầu tại thời điểm kiểm tra hay không. Nó được đánh giá trước khi Spring Shell gọi phần thân command. Nếu command chưa khả dụng, shell từ chối lời gọi và giải thích lý do.

Ví dụ, trước khi kết nối:

```text
shell:> artifact download
Command 'artifact download' exists but is not currently available because you are not connected
```

Sau khi kết nối thành công, cùng command có thể chạy:

```text
shell:> remote connect staging
Đã kết nối tới staging

shell:> artifact download
Đã tải dữ liệu
```

Hai khái niệm cần được kiểm tra riêng:

| Khái niệm | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Availability | Có được phép bắt đầu command lúc này không? | Đã có phiên kết nối chưa? |
| Kết quả thực thi | Command đã chạy và hoàn thành thế nào? | Tải dữ liệu thành công hay máy chủ đóng kết nối? |

Availability không bảo đảm thao tác chắc chắn thành công. Trạng thái có thể thay đổi giữa lúc shell kiểm tra availability và lúc service thực hiện công việc. Command vẫn phải kiểm tra điều kiện nghiệp vụ tại nơi thực thi và xử lý exception nếu kết nối bị mất.

## Khai báo điều kiện bằng `Availability`

Trong mô hình legacy 3.4.x, `Availability` thuộc package `org.springframework.shell`. Hai factory method thường dùng:

```java
Availability.available();
Availability.unavailable("you are not connected");
```

Khi command method có tên `download`, Spring Shell có thể tìm phương thức `downloadAvailability()` không tham số và trả về `Availability`. Có thể chỉ định tên phương thức rõ ràng bằng `@ShellMethodAvailability`:

```java
import org.springframework.shell.Availability;
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;
import org.springframework.shell.standard.ShellMethodAvailability;

@ShellComponent
public class RemoteCommands {

    private final RemoteSession remoteSession;

    public RemoteCommands(RemoteSession remoteSession) {
        this.remoteSession = remoteSession;
    }

    @ShellMethod(key = "remote connect", value = "Kết nối tới máy chủ")
    public String connect(String endpoint) {
        remoteSession.connect(endpoint);
        return "Đã kết nối tới " + endpoint;
    }

    @ShellMethod(key = "remote disconnect", value = "Ngắt kết nối máy chủ")
    public String disconnect() {
        remoteSession.disconnect();
        return "Đã ngắt kết nối";
    }

    @ShellMethod(key = "artifact download", value = "Tải dữ liệu từ máy chủ")
    @ShellMethodAvailability("downloadAvailability")
    public String download() {
        remoteSession.download();
        return "Đã tải dữ liệu";
    }

    public Availability downloadAvailability() {
        return remoteSession.downloadAvailability();
    }
}
```

Tên truyền vào `@ShellMethodAvailability` phải khớp với tên phương thức kiểm tra. Phương thức availability không nhận tham số và trả về `Availability`. Nếu không cần tên riêng, có thể dùng quy ước `downloadAvailability()` mà không thêm annotation.

Lý do truyền vào `Availability.unavailable(...)` nên là một mệnh đề ngắn, viết thường và không có dấu chấm cuối, vì Spring Shell ghép nó sau từ “because”. Hãy viết nội dung giải thích điều kiện cần khắc phục, chẳng hạn `you are not connected` hoặc `the active profile is read-only`.

Spring Shell 3.4.x cũng có mô hình annotation command mới. Với mô hình đó, có thể gắn `@CommandAvailability(provider = "downloadAvailability")` lên command và đăng ký một bean `AvailabilityProvider` cùng tên. Đây là cách nối provider của mô hình `@Command`; không trộn nó với `@ShellMethodAvailability` của mô hình legacy trong cùng một khai báo command.

### Một điều kiện cho nhiều command

Nếu nhiều command phụ thuộc cùng một trạng thái, có thể đặt `@ShellMethodAvailability` trên phương thức availability và liệt kê các command mà nó kiểm soát:

```java
@ShellMethodAvailability({"artifact download", "artifact list", "artifact delete"})
public Availability remoteCommandsAvailability() {
    return remoteSession.isConnected()
            ? Availability.available()
            : Availability.unavailable("you are not connected");
}
```

Trong thực tế, giá trị cần khớp với tên command/alias mà Spring Shell nhận diện trong ứng dụng. Khi thay đổi `key` hoặc alias, hãy cập nhật danh sách này và kiểm thử lại cả ba command.

## Availability không thay thế kiểm tra trong service

Availability chủ yếu giúp giao diện shell phản hồi sớm và giải thích vì sao command chưa thể chạy. Nó không phải ranh giới bảo mật. Một command có thể được gọi trong lúc trạng thái thay đổi, hoặc một service có thể được gọi từ nơi khác mà không đi qua shell.

Vì vậy, service nghiệp vụ vẫn phải kiểm tra trạng thái và quyền ngay trước thao tác:

```java
public void download() {
    if (!sessionState.isConnected()) {
        throw new RemoteUnavailableException("phiên kết nối không còn hợp lệ");
    }

    remoteGateway.download(sessionState.endpoint());
}
```

Availability nên đọc trạng thái đã có trong bộ nhớ hoặc state store nhanh. Không nên gọi mạng để ping máy chủ mỗi lần shell kiểm tra availability, vì thao tác này có thể được gọi thường xuyên, kể cả khi người dùng hiển thị `help` hoặc danh sách command.

## Mô hình hóa trạng thái phiên

Một biến boolean có thể đủ cho ví dụ nhỏ, nhưng một phiên thực tế thường có thêm endpoint, thời điểm kết nối, người dùng và trạng thái lỗi. Hãy đặt trạng thái vào một service riêng để các command và availability method cùng sử dụng.

```java
import org.springframework.shell.Availability;
import org.springframework.stereotype.Service;

@Service
public class RemoteSession {

    private final RemoteGateway gateway;

    private String endpoint;
    private boolean connected;

    public RemoteSession(RemoteGateway gateway) {
        this.gateway = gateway;
    }

    public synchronized void connect(String endpoint) {
        try {
            gateway.connect(endpoint);
            this.endpoint = endpoint;
            this.connected = true;
        }
        catch (RemoteUnavailableException exception) {
            clear();
            throw exception;
        }
    }

    public synchronized void disconnect() {
        try {
            if (connected) {
                gateway.disconnect(endpoint);
            }
        }
        finally {
            clear();
        }
    }

    public synchronized void download() {
        if (!connected) {
            throw new RemoteUnavailableException("phiên kết nối không còn hợp lệ");
        }

        try {
            gateway.download(endpoint);
        }
        catch (RemoteUnavailableException exception) {
            clear();
            throw exception;
        }
    }

    public synchronized Availability downloadAvailability() {
        return connected
                ? Availability.available()
                : Availability.unavailable("you are not connected");
    }

    public synchronized boolean isConnected() {
        return connected;
    }

    public synchronized String endpoint() {
        return endpoint;
    }

    private void clear() {
        connected = false;
        endpoint = null;
    }
}
```

Điểm quan trọng là chỉ đặt `connected = true` sau khi `gateway.connect(...)` thành công. Nếu bắt đầu kết nối nhưng handshake thất bại, phiên không được chuyển sang trạng thái đã kết nối. Khi mất kết nối trong lúc tải dữ liệu, service xóa trạng thái trước khi ném exception để lần gọi tiếp theo không dùng một phiên đã hỏng.

`synchronized` trong ví dụ giữ cho các lần đọc/cập nhật state nhất quán trong một tiến trình. Nếu ứng dụng có nhiều phiên terminal hoặc nhiều người dùng đồng thời, không dùng một cặp `connected`/`endpoint` singleton chung cho tất cả. Hãy lưu trạng thái theo session ID hoặc principal, và truyền định danh phiên vào service khi thực hiện command.

### Những trạng thái nên phân biệt

Với ứng dụng phức tạp hơn, enum giúp tránh trạng thái boolean không đủ diễn đạt:

| Trạng thái | Ý nghĩa | Availability của lệnh tải |
| --- | --- | --- |
| `DISCONNECTED` | Chưa có phiên | Unavailable |
| `CONNECTING` | Đang thiết lập kết nối | Unavailable |
| `CONNECTED` | Kết nối đã được xác nhận | Available |
| `DISCONNECTING` | Đang đóng phiên | Unavailable |
| `EXPIRED` | Phiên hết hạn | Unavailable |
| `FAILED` | Lần thao tác gần nhất thất bại và cần khôi phục | Tùy chính sách, thường unavailable |

Không cần tạo tất cả trạng thái cho một CLI nhỏ. Chỉ thêm trạng thái khi chúng làm rõ một nhánh xử lý thực sự có trong ứng dụng.

## Kiểm tra lỗi và khôi phục trạng thái

Có ít nhất ba đường đi lỗi khác nhau cần kiểm tra:

| Đường đi | Command có chạy không? | Trạng thái phiên mong đợi |
| --- | --- | --- |
| Availability từ chối | Không chạy phần thân command | Giữ trạng thái hiện tại |
| Kết nối thất bại | `connect` đã chạy nhưng không hoàn tất | Vẫn disconnected |
| Mất kết nối trong thao tác | Command đã bắt đầu nghiệp vụ | Xóa phiên hỏng và khóa command phụ thuộc phiên |

Lỗi nghiệp vụ không phải lúc nào cũng làm mất phiên. Ví dụ, máy chủ trả về “không đủ quyền” có thể cho biết kết nối vẫn hoạt động; không nên xóa session chỉ vì bất kỳ exception nào xảy ra. Chỉ chuyển về `DISCONNECTED` khi lỗi cho thấy phiên hoặc kênh kết nối không còn hợp lệ.

### Xử lý exception có kiểu rõ ràng

Tạo exception riêng cho lỗi kết nối:

```java
public class RemoteUnavailableException extends RuntimeException {

    public RemoteUnavailableException(String message) {
        super(message);
    }
}
```

Trong `@ShellComponent`, có thể dùng `@ExceptionResolver` để chuyển exception thành thông báo dễ hiểu:

```java
import org.springframework.shell.command.CommandHandlingResult;
import org.springframework.shell.command.annotation.ExceptionResolver;

@ExceptionResolver
public CommandHandlingResult handleRemoteUnavailable(
        RemoteUnavailableException exception) {
    return CommandHandlingResult.of(
            "Không thể thực hiện thao tác từ xa: "
                    + exception.getMessage() + "\n",
            5);
}
```

`@ExceptionResolver` trong mô hình annotation xử lý exception phát sinh từ các command method trong `@ShellComponent`. Trả về `CommandHandlingResult` cho phép kiểm soát cả thông báo và exit code. Mã thoát có ý nghĩa khi chạy non-interactive; trong REPL, điều cần kiểm tra chủ yếu là thông báo và trạng thái sau lỗi.

Spring Shell cũng cung cấp command `stacktrace` để hiển thị chi tiết exception gần nhất khi cần điều tra. Thông báo thông thường nên ngắn gọn; stack trace chỉ nên dùng khi phát triển hoặc khi người vận hành chủ động yêu cầu.

## Kiểm thử bằng `@ShellTest` và `ShellTestClient`

Spring Shell 3.4.x cung cấp hai module test support:

| Module | Vai trò |
| --- | --- |
| `spring-shell-test` | API client, session và assertion cho shell |
| `spring-shell-test-autoconfigure` | Annotation và auto-configuration cho test Spring Shell |

Với Maven, thêm các dependency test theo phiên bản Spring Shell mà ứng dụng đang dùng:

```xml
<dependency>
    <groupId>org.springframework.shell</groupId>
    <artifactId>spring-shell-test</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.springframework.shell</groupId>
    <artifactId>spring-shell-test-autoconfigure</artifactId>
    <scope>test</scope>
</dependency>
```

`@ShellTest` dựng test context cho command. `ShellTestClient` tạo phiên tương tác hoặc non-interactive, mô phỏng dữ liệu nhập và cho phép đọc nội dung terminal qua `ShellScreen`. `ShellAssertions` cung cấp assertion theo nội dung màn hình.

### Kiểm thử thay đổi availability trong cùng một phiên

Điểm quan trọng của kiểm thử session state là dùng cùng một `InteractiveShellSession` cho nhiều command liên tiếp. Không tạo một shell mới sau mỗi command, nếu mục tiêu là xác minh trạng thái được giữ trong suốt phiên.

```java
import static java.util.concurrent.TimeUnit.SECONDS;
import static org.awaitility.Awaitility.await;
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.shell.test.ShellAssertions;
import org.springframework.shell.test.ShellTestClient;
import org.springframework.shell.test.ShellTestClient.InteractiveShellSession;
import org.springframework.shell.test.autoconfigure.ShellTest;

@ShellTest
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class RemoteAvailabilityTests {

    @Autowired
    ShellTestClient client;

    @Autowired
    RemoteSession remoteSession;

    @Autowired
    DemoRemoteGateway gateway;

    @Test
    void downloadAvailabilityFollowsSessionState() {
        InteractiveShellSession shell = client.interactive().run();

        await().atMost(2, SECONDS).untilAsserted(() ->
                ShellAssertions.assertThat(shell.screen()).containsText("shell"));

        send(shell, "artifact download");
        await().atMost(2, SECONDS).untilAsserted(() ->
                ShellAssertions.assertThat(shell.screen())
                        .containsText("not currently available because you are not connected"));
        assertThat(gateway.downloadCalls()).isZero();

        send(shell, "remote connect local");
        await().atMost(2, SECONDS).untilAsserted(() ->
                ShellAssertions.assertThat(shell.screen()).containsText("Đã kết nối tới local"));
        assertThat(remoteSession.isConnected()).isTrue();

        send(shell, "artifact download");
        await().atMost(2, SECONDS).untilAsserted(() ->
                ShellAssertions.assertThat(shell.screen()).containsText("Đã tải dữ liệu"));
        assertThat(gateway.downloadCalls()).isEqualTo(1);

        send(shell, "remote disconnect");
        await().atMost(2, SECONDS).untilAsserted(() ->
                ShellAssertions.assertThat(shell.screen()).containsText("Đã ngắt kết nối"));
        assertThat(remoteSession.isConnected()).isFalse();

        send(shell, "artifact download");
        await().atMost(2, SECONDS).untilAsserted(() ->
                ShellAssertions.assertThat(shell.screen())
                        .containsText("not currently available because you are not connected"));
        assertThat(gateway.downloadCalls()).isEqualTo(1);
    }

    private static void send(InteractiveShellSession shell, String command) {
        shell.write(shell.writeSequence()
                .text(command)
                .carriageReturn()
                .build());
    }
}
```

Test xác minh cả output và side effect. Trước khi kết nối, command bị từ chối và `downloadCalls()` vẫn bằng 0. Sau khi kết nối, command chạy và bộ đếm tăng. Sau khi ngắt kết nối, command lại bị khóa và service không được gọi thêm.

`@DirtiesContext(AFTER_EACH_TEST_METHOD)` tạo lại Spring context sau mỗi test method. Điều này ngăn state singleton của một test ảnh hưởng test khác. Với bộ test lớn, có thể dùng fixture hoặc bean state riêng để reset rõ ràng, nhưng không nên bỏ qua việc cô lập trạng thái phiên.

### Kiểm thử kết nối thất bại

Giả sử `DemoRemoteGateway` từ chối endpoint có tên `offline` và ném `RemoteUnavailableException`:

```java
@Test
void failedConnectKeepsDownloadUnavailable() {
    InteractiveShellSession shell = client.interactive().run();

    send(shell, "remote connect offline");
    await().atMost(2, SECONDS).untilAsserted(() ->
            ShellAssertions.assertThat(shell.screen())
                    .containsText("Không thể thực hiện thao tác từ xa"));

    assertThat(remoteSession.isConnected()).isFalse();

    send(shell, "artifact download");
    await().atMost(2, SECONDS).untilAsserted(() ->
            ShellAssertions.assertThat(shell.screen())
                    .containsText("not currently available because you are not connected"));
    assertThat(gateway.downloadCalls()).isZero();
}
```

Test này chứng minh lỗi ở bước connect không làm state chuyển nhầm sang connected. Sau lỗi, command phụ thuộc phiên vẫn không khả dụng.

### Kiểm thử mất kết nối trong khi command đang chạy

Giả sử endpoint `flaky` cho phép kết nối nhưng lần tải tiếp theo ném `RemoteUnavailableException`:

```java
@Test
void lostConnectionClearsSessionAndLocksNextDownload() {
    InteractiveShellSession shell = client.interactive().run();

    send(shell, "remote connect flaky");
    await().atMost(2, SECONDS).untilAsserted(() ->
            ShellAssertions.assertThat(shell.screen()).containsText("Đã kết nối tới flaky"));

    send(shell, "artifact download");
    await().atMost(2, SECONDS).untilAsserted(() ->
            ShellAssertions.assertThat(shell.screen())
                    .containsText("Không thể thực hiện thao tác từ xa"));

    assertThat(remoteSession.isConnected()).isFalse();

    send(shell, "artifact download");
    await().atMost(2, SECONDS).untilAsserted(() ->
            ShellAssertions.assertThat(shell.screen())
                    .containsText("not currently available because you are not connected"));
}
```

Test đi qua cả hai lớp: lần tải đầu tiên được phép bắt đầu vì session đang connected, nhưng lỗi mạng làm service xóa state; lần gọi thứ hai bị availability chặn trước khi vào nghiệp vụ.

## Tạo gateway giả để kiểm soát lỗi trong test

Không cần gọi máy chủ thật để kiểm tra đường đi lỗi. Một fake gateway có thể tạo ra kết quả ổn định theo endpoint:

```java
public interface RemoteGateway {

    void connect(String endpoint);

    void download(String endpoint);

    void disconnect(String endpoint);
}
```

```java
import java.util.concurrent.atomic.AtomicInteger;

public class DemoRemoteGateway implements RemoteGateway {

    private final AtomicInteger downloadCalls = new AtomicInteger();

    @Override
    public void connect(String endpoint) {
        if ("offline".equals(endpoint)) {
            throw new RemoteUnavailableException("máy chủ không phản hồi");
        }
    }

    @Override
    public void download(String endpoint) {
        downloadCalls.incrementAndGet();
        if ("flaky".equals(endpoint)) {
            throw new RemoteUnavailableException("máy chủ đã đóng kết nối");
        }
    }

    @Override
    public void disconnect(String endpoint) {
        // Fake gateway không cần đóng tài nguyên bên ngoài.
    }

    public int downloadCalls() {
        return downloadCalls.get();
    }
}
```

`RemoteGateway` là interface của ứng dụng với ba thao tác `connect`, `download` và `disconnect`. Trong production, adapter có thể gọi HTTP client, SSH hoặc SDK của hệ thống từ xa. Trong test, fake chỉ mô phỏng lỗi theo endpoint nên test không phụ thuộc mạng hoặc trạng thái máy chủ thật.

Đăng ký fake trong test context bằng một nested `@TestConfiguration` của lớp test:

```java
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;

@TestConfiguration(proxyBeanMethods = false)
static class GatewayTestConfiguration {

    @Bean
    @Primary
    DemoRemoteGateway demoRemoteGateway() {
        return new DemoRemoteGateway();
    }
}
```

Đặt cấu hình này bên trong test class để fake chỉ được đăng ký trong test context. Nếu ứng dụng đã có một implementation production của `RemoteGateway`, `@Primary` chọn fake cho các test cần mô phỏng lỗi.

## Kiểm tra command unavailable trong `help`

Spring Shell có thể đưa thông tin availability vào danh sách `help`. Điều này giúp người dùng nhìn thấy command tồn tại nhưng chưa thể chạy. Test có thể kiểm tra:

- Command vẫn xuất hiện trong danh sách khi unavailable.
- Màn hình hoặc template có thể phân biệt command khả dụng và không khả dụng.
- Lý do hiển thị khớp điều kiện hiện tại.
- Sau khi kết nối, trạng thái availability được cập nhật trong lần hiển thị help tiếp theo.

Không nên khóa test vào toàn bộ khoảng trắng hoặc cách căn lề của output `help`. Hãy kiểm tra tên command, mô tả và dấu hiệu unavailable cần thiết. Template help có thể được tùy chỉnh và định dạng có thể thay đổi theo phiên bản.

## Kiểm thử non-interactive và interactive khác nhau

`ShellTestClient` hỗ trợ hai kiểu phiên:

| Kiểu | Cách tạo | Phù hợp để kiểm tra |
| --- | --- | --- |
| Interactive | `client.interactive().run()` | Trạng thái tồn tại qua nhiều command trong cùng REPL, prompt và chuỗi lỗi tiếp tục |
| Non-interactive | `client.nonInteractive("help").run()` | Một command chạy rồi kết thúc, output và đường đi batch |

Với non-interactive session, `nonInteractive(...)` là tên API hiện hành từ Spring Shell 3.4.2; phương thức `nonInterative(...)` cũ đã deprecated. Hãy dùng tên mới trong test.

Không dùng non-interactive test để chứng minh trạng thái tồn tại qua nhiều lệnh trong một REPL, vì runner này được thiết kế để thực hiện command rồi kết thúc. Ngược lại, interactive test không thay thế kiểm thử tiến trình đã đóng gói nếu cần xác minh exit code của JVM.

## Kiểm tra đường đi exception riêng với availability

Nên tách các trường hợp sau thành test riêng:

| Trường hợp | Điều cần xác minh |
| --- | --- |
| Command unavailable | Phần thân command không chạy; lý do được hiển thị |
| Connect thành công | State chuyển sang connected và command phụ thuộc được mở |
| Connect thất bại | State vẫn disconnected; command phụ thuộc tiếp tục bị khóa |
| Download thành công | Service được gọi và kết quả thành công hiển thị |
| Download mất kết nối | Resolver xử lý exception; state được xóa |
| Lỗi nghiệp vụ không làm mất kết nối | State vẫn connected nếu lỗi không liên quan phiên |
| Disconnect thành công | State được xóa và command phụ thuộc bị khóa |
| Lỗi parser/option | Method command không chạy; lỗi parser được hiển thị theo cơ chế của shell |
| Command không tồn tại | Shell báo command không được đăng ký |

Availability và exception resolver là hai đường xử lý khác nhau. Một command unavailable bị từ chối trước khi gọi method, nên `@ExceptionResolver` trong method component không phải nơi xử lý trường hợp đó. Resolver chỉ xử lý exception phát sinh trong command đã được gọi.

## Cô lập trạng thái phiên trong test

Một bean `@Service` hoặc `@Component` mặc định là singleton trong Spring application context. Nếu nó giữ `connected = true`, trạng thái đó có thể được nhìn thấy bởi mọi command dùng cùng bean trong tiến trình.

Điều này thường phù hợp với CLI một người dùng. Nhưng nếu ứng dụng mở nhiều terminal session hoặc phục vụ nhiều người dùng đồng thời, state singleton không phải state riêng từng phiên. Khi đó:

- Dùng session ID hoặc principal làm khóa state.
- Đưa state vào session manager thay vì giữ một boolean toàn cục.
- Kiểm tra quyền ở service mỗi khi thực hiện thao tác.
- Không dùng `@DirtiesContext` như giải pháp runtime; annotation này chỉ phục vụ cô lập test context.
- Kiểm thử hai session độc lập để bảo đảm một người dùng disconnect không làm người khác mất phiên.

Trong test đơn giản, `@DirtiesContext(AFTER_EACH_TEST_METHOD)` giúp reset singleton giữa các test. Với nhiều test chạy song song, cần đảm bảo chúng không dùng chung state mutable hoặc cấu hình test execution để tránh race.

## Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Chỉ test method command trực tiếp | Không xác minh availability có chặn lệnh hay không | Chạy command qua `ShellTestClient` |
| Tạo shell mới sau mỗi command | Không kiểm tra được state tồn tại trong cùng REPL | Dùng một `InteractiveShellSession` cho cả chuỗi |
| Đánh dấu connected trước khi handshake xong | Kết nối thất bại nhưng command phụ thuộc vẫn mở | Chỉ cập nhật state sau khi gateway thành công |
| Không xóa state khi mất kết nối | Command sau tiếp tục được đánh dấu available | Xóa session khi lỗi chứng minh kênh đã hỏng |
| Xóa session sau mọi exception | Lỗi nghiệp vụ thông thường cũng làm người dùng mất kết nối | Phân loại exception theo nguyên nhân |
| Gọi mạng trong availability provider | `help` hoặc kiểm tra command có thể chậm | Đọc state đã cache, để service xử lý lỗi thực tế |
| Dùng availability làm kiểm soát quyền | Có thể bị bỏ qua khi service được gọi từ nơi khác | Kiểm tra quyền và state trong service |
| State singleton dùng chung cho nhiều người | Phiên người này ảnh hưởng người khác | Key state theo session/principal |
| Test phụ thuộc máy chủ thật | Kết quả không ổn định và khó tái hiện | Dùng fake gateway hoặc mock có kịch bản |
| Assert toàn bộ output terminal | Test dễ hỏng do prompt, màu và định dạng | Assert các đoạn nội dung có ý nghĩa |
| Chỉ kiểm tra message sau lỗi | Không biết state có được khôi phục đúng không | Assert cả state service và lần gọi kế tiếp |
| Dùng interactive test để xác minh exit code tiến trình | Không kiểm tra được mã thoát JVM thực tế | Bổ sung end-to-end test chạy non-interactive process |

## Quy trình kiểm thử availability và đường đi sau lỗi

1. Xác định trạng thái phiên và các command phụ thuộc vào trạng thái đó.
2. Đưa trạng thái vào service có thể kiểm tra và cập nhật một cách nhất quán.
3. Khai báo `Availability` và gắn với command bằng `@ShellMethodAvailability`.
4. Giữ kiểm tra trạng thái trong service để bảo vệ thao tác khi state thay đổi sau lần kiểm tra availability.
5. Xác định exception nào làm mất phiên, exception nào chỉ là lỗi nghiệp vụ.
6. Dùng `@ExceptionResolver` để tạo thông báo lỗi phù hợp cho exception đã phân loại.
7. Viết interactive test chạy nhiều command liên tiếp trong cùng một session.
8. Kiểm tra output, state và side effect của service trước/sau từng bước.
9. Dùng fake gateway để tái hiện kết nối thất bại và mất kết nối giữa chừng.
10. Cô lập context giữa test và bổ sung non-interactive test khi cần kiểm tra batch/exit code.

Khi kiểm thử đúng cả availability, trạng thái phiên và đường đi sau lỗi, test sẽ chứng minh được command bị khóa đúng lúc, mở đúng lúc và quay về trạng thái an toàn khi kết nối hỏng. Kết hợp assertion trên terminal với assertion về state và side effect giúp phát hiện những lỗi mà kiểm tra thông báo đơn thuần không thể nhận ra.

## Tài liệu tham khảo

- [Command Availability – Spring Shell 3.4.x](https://docs.spring.io/spring-shell/reference/3.4-SNAPSHOT/commands/availability.html)
- [Basics – Spring Shell Testing 3.4.x](https://docs.spring.io/spring-shell/reference/3.4/testing/basics.html)
- [ShellTestClient API – Spring Shell 3.4.x](https://docs.spring.io/spring-shell/reference/3.4-SNAPSHOT/api/java/org/springframework/shell/test/ShellTestClient.html)
- [ShellMethodAvailability API – Spring Shell 3.4.x](https://docs.spring.io/spring-shell/reference/3.4-SNAPSHOT/api/java/org/springframework/shell/standard/ShellMethodAvailability.html)
- [@ExceptionResolver – Spring Shell 3.4.x](https://docs.spring.io/spring-shell/reference/3.4-SNAPSHOT/commands/exceptionhandling/annotation.html)
- [Exception Resolving – Spring Shell 3.4.x](https://docs.spring.io/spring-shell/reference/3.4-SNAPSHOT/commands/exceptionhandling/resolving.html)
- [Stacktrace – Spring Shell 3.4.x](https://docs.spring.io/spring-shell/reference/3.4-SNAPSHOT/commands/builtin/stacktrace.html)

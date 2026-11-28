# Kiểm tra khả dụng và trạng thái của lệnh

Một command có thể đã được đăng ký trong Spring Shell nhưng chưa thể thực thi ở một thời điểm cụ thể. Ví dụ, ứng dụng có command `download`, nhưng người dùng phải kết nối tới máy chủ trước khi tải dữ liệu. Nếu command vẫn được gọi khi chưa kết nối, ứng dụng cần giải thích điều kiện còn thiếu thay vì để người dùng gặp một lỗi khó hiểu trong lúc xử lý nghiệp vụ.

Spring Shell cung cấp cơ chế **command availability** để mô tả command hiện có thể được gọi hay không, đồng thời trả về lý do khi command chưa khả dụng. Cơ chế này đặc biệt hữu ích với các CLI có trạng thái phiên làm việc như kết nối, đăng nhập, chọn dự án, mở transaction hoặc khởi tạo tài nguyên.

Bài học này trình bày cách biểu diễn trạng thái khả dụng, cách viết availability provider trong mô hình command hiện đại, cách tổ chức trạng thái ứng dụng, cách quan sát command từ shell và cách kiểm thử các chuyển đổi trạng thái. Nội dung cũng phân biệt trạng thái khả dụng với trạng thái kết quả thực thi và lưu ý sự khác nhau giữa các thế hệ API Spring Shell.

## 1. Phân biệt command đã đăng ký và command khả dụng

Có ba câu hỏi khác nhau khi người dùng nhập một lệnh:

1. **Command có tồn tại không?** Spring Shell có biết tên lệnh và có thể ánh xạ đầu vào tới command đó không?
2. **Command có khả dụng ngay lúc này không?** Các điều kiện cần thiết để thực hiện lệnh đã được đáp ứng chưa?
3. **Command thực thi có thành công không?** Sau khi bắt đầu xử lý, nghiệp vụ có hoàn tất đúng yêu cầu không?

Ba trạng thái này không đồng nghĩa:

| Tình huống | Ý nghĩa | Phản hồi phù hợp |
|---|---|---|
| Không tìm thấy command | Tên lệnh chưa được đăng ký hoặc không khớp | Báo command không tồn tại |
| Command tồn tại nhưng unavailable | Command đã biết, điều kiện thực thi hiện chưa đáp ứng | Báo rõ điều kiện còn thiếu |
| Command available nhưng xử lý thất bại | Điều kiện ban đầu có vẻ đạt, nhưng nghiệp vụ phát sinh lỗi | Trả lỗi thực thi hoặc mã thoát phù hợp |
| Command thực thi thành công | Nghiệp vụ hoàn tất | Trả kết quả thành công |

Ví dụ, ứng dụng quản lý máy chủ từ xa có các command:

- `connect`: thiết lập kết nối.
- `disconnect`: đóng kết nối.
- `download`: tải dữ liệu từ máy chủ.
- `status`: hiển thị trạng thái phiên hiện tại.

Trước khi kết nối, `download` vẫn là một command đã đăng ký. Người dùng có thể biết command đó tồn tại, nhưng nó chưa khả dụng vì chưa có kết nối. Sau khi `connect` thành công, trạng thái khả dụng thay đổi và `download` có thể được gọi.

~~~mermaid
stateDiagram-v2
    [*] --> Disconnected
    Disconnected --> Connected: connect thành công
    Connected --> Disconnected: disconnect thành công
    Connected --> Connected: download
    state Disconnected {
        [*] --> DownloadUnavailable
    }
    state Connected {
        [*] --> DownloadAvailable
    }
~~~

Trạng thái trong sơ đồ là trạng thái phiên kết nối của ứng dụng. Availability của command được tính dựa trên trạng thái đó. Một command không cần được đăng ký lại mỗi khi trạng thái thay đổi; provider trả lời xem command hiện có thể chạy hay không.

## 2. Availability trong Spring Shell

Spring Shell biểu diễn khả dụng bằng đối tượng `Availability`. Về cơ bản, kết quả có hai dạng:

- `Availability.available()`: command hiện có thể được thực thi.
- `Availability.unavailable(reason)`: command hiện chưa thể thực thi và cần một lý do giải thích.

Trong Spring Shell 4.x, API nằm trong package:

~~~java
org.springframework.shell.core.command.availability.Availability
org.springframework.shell.core.command.availability.AvailabilityProvider
~~~

`AvailabilityProvider` là một functional interface cung cấp một giá trị `Availability`. Vì vậy, có thể triển khai bằng lambda hoặc method reference.

Một ví dụ đơn giản:

~~~java
AvailabilityProvider provider = () -> connected
        ? Availability.available()
        : Availability.unavailable("you are not connected");
~~~

Khi `connected` là `false`, provider trả về trạng thái unavailable. Khi kết nối thành công và trạng thái chuyển thành `true`, lần đánh giá tiếp theo trả về available.

Lý do unavailable sẽ được Spring Shell sử dụng để giải thích vì sao command không thể chạy. Nên viết lý do ngắn gọn, trực tiếp và phù hợp khi được nối vào câu thông báo, ví dụ `you are not connected`, `no project is selected` hoặc `the transaction is already closed`. Theo hướng dẫn Spring Shell, phần lý do nên viết thường ở đầu và không thêm dấu chấm cuối câu vì shell có thể nối nó sau cụm từ giải thích.

## 3. Xác định điều kiện khả dụng từ trạng thái nghiệp vụ

Availability nên phản ánh những điều kiện nghiệp vụ thật sự cần thiết để bắt đầu một command. Ví dụ:

| Command | Điều kiện khả dụng có thể kiểm tra |
|---|---|
| `download` | Đã kết nối tới máy chủ |
| `disconnect` | Phiên kết nối đang hoạt động |
| `deploy` | Đã chọn môi trường và có gói build |
| `commit` | Có transaction đang mở |
| `publish` | Bản nháp đã qua bước kiểm duyệt |
| `delete project` | Dự án tồn tại và người dùng có quyền thực hiện |

Không phải mọi điều kiện đều phù hợp để đặt trong availability provider. Hãy dùng provider cho các điều kiện trạng thái có thể kiểm tra trước khi chạy, đặc biệt những điều kiện giúp người dùng hiểu vì sao command đang bị khóa.

Các quy tắc phụ thuộc dữ liệu đầu vào vẫn cần được xử lý trong validation hoặc logic nghiệp vụ. Ví dụ, command `download --file report.csv` có thể khả dụng khi đã kết nối, nhưng tên file vẫn cần được kiểm tra khi người dùng truyền đối số. Availability không thay thế validation.

Tương tự, kiểm tra quyền truy cập là trách nhiệm bảo mật của service hoặc lớp nghiệp vụ. Việc ẩn command hay trả unavailable không được xem là cơ chế phân quyền duy nhất. Service phải xác thực quyền ở nơi thực hiện hành động nhạy cảm.

## 4. Khai báo AvailabilityProvider trong Spring Shell 4.x

Trong mô hình annotation-based của Spring Shell 4.x, method command được đánh dấu bằng `@Command`. Thuộc tính `availabilityProvider` trỏ tới tên bean `AvailabilityProvider` mà Spring Shell dùng để đánh giá trạng thái command.

Ví dụ dưới đây mô phỏng một ứng dụng tải dữ liệu từ máy chủ. Trạng thái kết nối được quản lý bởi một bean riêng để command và provider cùng đọc một nguồn trạng thái.

### 4.1. Bean quản lý trạng thái kết nối

~~~java
package com.example.cli.session;

import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.stereotype.Component;

@Component
public class ConnectionState {

    private final AtomicBoolean connected = new AtomicBoolean(false);

    public boolean isConnected() {
        return connected.get();
    }

    public void markConnected() {
        connected.set(true);
    }

    public void markDisconnected() {
        connected.set(false);
    }
}
~~~

`ConnectionState` giữ trạng thái hiện tại của phiên. Trong ứng dụng thực tế, trạng thái này nên được cập nhật sau khi thao tác kết nối hoặc ngắt kết nối thực sự thành công. Không nên đánh dấu connected trước khi client xác nhận kết nối.

`AtomicBoolean` giúp thao tác đọc và cập nhật giá trị boolean an toàn khi có nhiều luồng cùng truy cập. Nếu ứng dụng chỉ chạy một luồng shell, vẫn nên chọn cách quản lý trạng thái phù hợp với vòng đời thực tế của ứng dụng.

### 4.2. Command thay đổi và hiển thị trạng thái

~~~java
package com.example.cli.command;

import com.example.cli.session.ConnectionState;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.stereotype.Component;

@Component
public class RemoteCommands {

    private final ConnectionState connectionState;

    public RemoteCommands(ConnectionState connectionState) {
        this.connectionState = connectionState;
    }

    @Command(name = "connect", description = "Connect to the remote server")
    public void connect() {
        // Gọi remote client và chỉ cập nhật state khi kết nối thành công.
        connectionState.markConnected();
    }

    @Command(name = "disconnect", description = "Disconnect from the remote server")
    public void disconnect() {
        // Gọi remote client và chỉ cập nhật state khi ngắt kết nối thành công.
        connectionState.markDisconnected();
    }

    @Command(name = "status", description = "Show the current connection state")
    public String status() {
        return connectionState.isConnected()
                ? "Connected"
                : "Disconnected";
    }

    @Command(
        name = "download",
        description = "Download data from the remote server",
        availabilityProvider = "downloadAvailability"
    )
    public String download() {
        // Kiểm tra lại điều kiện trước khi thực hiện thao tác thật.
        if (!connectionState.isConnected()) {
            throw new IllegalStateException("Remote session is no longer connected");
        }

        // Gọi service tải dữ liệu trong ứng dụng thực tế.
        return "Download completed";
    }
}
~~~

Command `status` luôn có thể gọi để người dùng xem trạng thái. Command `download` tham chiếu provider có tên `downloadAvailability`. Khi kết nối thay đổi, provider sẽ đọc trạng thái mới từ cùng bean `ConnectionState`.

Phần gọi remote client trong ví dụ được giản lược. Trong ứng dụng thật, cần cập nhật trạng thái sau khi client hoàn tất thao tác thành công và xử lý riêng trường hợp kết nối bị mất ngoài dự kiến.

### 4.3. Đăng ký provider bean

~~~java
package com.example.cli.config;

import com.example.cli.session.ConnectionState;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.core.command.availability.Availability;
import org.springframework.shell.core.command.availability.AvailabilityProvider;

@Configuration
public class CommandAvailabilityConfiguration {

    @Bean
    public AvailabilityProvider downloadAvailability(
            ConnectionState connectionState) {

        return () -> connectionState.isConnected()
                ? Availability.available()
                : Availability.unavailable("you are not connected");
    }
}
~~~

Tên method `downloadAvailability` cũng là tên bean mặc định. Nó khớp với giá trị của thuộc tính `availabilityProvider` trong `@Command`.

Khi người dùng nhập `download` trước khi kết nối, Spring Shell có thể trả thông báo tương tự:

~~~text
shell:> download
Command 'download' exists but is not currently available because you are not connected.
~~~

Sau khi kết nối thành công:

~~~text
shell:> connect

shell:> status
Connected

shell:> download
Download completed
~~~

Điểm quan trọng là provider không thực hiện việc tải dữ liệu. Nó chỉ đánh giá điều kiện trước khi command được gọi. Phần nghiệp vụ vẫn nằm trong method command hoặc service được command sử dụng.

## 5. Gắn availability provider khi đăng ký command bằng code

Spring Shell 4.x cũng hỗ trợ đăng ký command theo chương trình. Khi dùng builder, có thể gắn provider bằng phương thức `availabilityProvider(...)`.

Ví dụ phần cấu hình provider trong builder:

~~~java
import com.example.cli.session.ConnectionState;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.core.command.AbstractCommand;
import org.springframework.shell.core.command.Command;
import org.springframework.shell.core.command.availability.Availability;

@Configuration
public class ProgrammaticCommandConfiguration {

    @Bean
    public AbstractCommand downloadCommand(ConnectionState connectionState) {
        return Command.builder()
            .name("download")
            .availabilityProvider(() -> connectionState.isConnected()
                    ? Availability.available()
                    : Availability.unavailable("you are not connected"))
            .execute(context -> {
                // Gọi service tải dữ liệu trong ứng dụng thực tế.
            });
    }
}
~~~

Spring đăng ký command được tạo bằng builder thông qua bean `AbstractCommand` trong application context. Mô hình programmatic cho phép cấu hình tên, tham số, completion, availability và phần thực thi tại cùng một nơi.

Nên chọn một mô hình đăng ký command nhất quán cho từng nhóm chức năng. Với command được khai báo bằng annotation, dùng thuộc tính `availabilityProvider`. Với command được tạo bằng builder, gắn provider trực tiếp vào builder. Không cần tạo hai command trùng tên chỉ để biểu diễn hai trạng thái.

## 6. Nhóm nhiều command dùng chung một trạng thái

Một trạng thái ứng dụng có thể ảnh hưởng đến nhiều command. Khi chưa kết nối, cả `download`, `upload` và `list remote files` đều không thể thực thi. Thay vì viết nhiều điều kiện khác nhau, có thể tạo các provider riêng cùng đọc một nguồn trạng thái.

~~~java
@Configuration
public class RemoteAvailabilityConfiguration {

    @Bean
    AvailabilityProvider downloadAvailability(ConnectionState state) {
        return () -> state.isConnected()
                ? Availability.available()
                : Availability.unavailable("you are not connected");
    }

    @Bean
    AvailabilityProvider uploadAvailability(ConnectionState state) {
        return () -> state.isConnected()
                ? Availability.available()
                : Availability.unavailable("you are not connected");
    }

    @Bean
    AvailabilityProvider listRemoteFilesAvailability(ConnectionState state) {
        return () -> state.isConnected()
                ? Availability.available()
                : Availability.unavailable("you are not connected");
    }
}
~~~

Cách này giúp mỗi command có thể tiến hóa độc lập khi điều kiện khác nhau. Nếu nhiều command có cùng một điều kiện và lý do, có thể trích xuất hàm dùng chung để tránh lặp logic.

Ví dụ:

~~~java
private Availability remoteConnectionAvailability(ConnectionState state) {
    return state.isConnected()
            ? Availability.available()
            : Availability.unavailable("you are not connected");
}
~~~

Sau đó các provider có thể gọi hàm này. Hãy giữ tên bean rõ ràng vì annotation `@Command` tham chiếu provider bằng tên.

## 7. Mô hình Availability trong các phiên bản annotation cũ

Các phiên bản Spring Shell sử dụng mô hình annotation cũ có API khác với `@Command` của Spring Shell 4.x.

Trong mô hình `@ShellComponent` và `@ShellMethod`, một method trả về `Availability` có thể được Spring Shell tìm theo quy ước tên. Ví dụ command method là `download`, method kiểm tra khả dụng có thể được đặt tên `downloadAvailability`.

~~~java
import org.springframework.shell.Availability;
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;
import org.springframework.shell.standard.ShellMethodAvailability;

@ShellComponent
public class LegacyRemoteCommands {

    private boolean connected;

    @ShellMethod("Connect to the remote server")
    public void connect() {
        connected = true;
    }

    @ShellMethod("Download remote data")
    public void download() {
        // Thực hiện tải dữ liệu
    }

    public Availability downloadAvailability() {
        return connected
                ? Availability.available()
                : Availability.unavailable("you are not connected");
    }
}
~~~

Nếu muốn dùng một tên method kiểm tra khác, `@ShellMethodAvailability` có thể liên kết command với method availability:

~~~java
@ShellMethod("Download remote data")
@ShellMethodAvailability("remoteDownloadCheck")
public void download() {
    // Thực hiện tải dữ liệu
}

public Availability remoteDownloadCheck() {
    return connected
            ? Availability.available()
            : Availability.unavailable("you are not connected");
}
~~~

Một method availability cũng có thể được gắn với nhiều command bằng cách truyền tên các command vào `@ShellMethodAvailability`. Giá trị mặc định `*` trong mô hình này đại diện cho tất cả command trong cùng lớp.

Đây là API của mô hình annotation cũ. Khi nâng cấp, cần đối chiếu phiên bản Spring Shell đang dùng và thay đổi import, annotation hoặc cách khai báo provider tương ứng. Không sao chép lẫn `@ShellMethodAvailability` của mô hình cũ và `availabilityProvider` trên `@Command` của Spring Shell 4.x vào cùng một ví dụ.

## 8. Theo dõi trạng thái phiên và tránh lỗi thiết kế

Availability provider chỉ có giá trị khi nó đọc đúng nguồn trạng thái. Một số lỗi thường gặp đến từ việc lưu trạng thái sai vòng đời hoặc cập nhật trạng thái không đồng bộ với thao tác thực tế.

### 8.1. Cập nhật trạng thái sau khi thao tác thành công

Ví dụ, command `connect` nên thực hiện kết nối trước rồi mới đánh dấu connected:

~~~java
public void connect() {
    remoteClient.connect();
    connectionState.markConnected();
}
~~~

Nếu `remoteClient.connect()` ném exception, trạng thái không được chuyển sang connected. Nếu cập nhật state trước khi gọi client, provider có thể cho phép `download` dù kết nối chưa tồn tại.

Tương tự, khi ngắt kết nối, chỉ nên cập nhật state theo kết quả thao tác thực tế. Ứng dụng cần có chiến lược đồng bộ khi server đóng kết nối hoặc mạng bị ngắt ngoài ý muốn.

### 8.2. Không giữ một biến trạng thái ở nhiều nơi

Nếu command giữ một biến `connected`, service giữ một biến khác và provider lại đọc một biến thứ ba, các giá trị có thể không đồng nhất. Hãy chọn một thành phần quản lý trạng thái có trách nhiệm rõ ràng và inject thành phần đó vào các command hoặc provider cần sử dụng.

Trong ứng dụng CLI đơn người dùng, một bean singleton quản lý trạng thái phiên có thể phù hợp. Nếu ứng dụng hỗ trợ nhiều phiên, nhiều tài khoản hoặc nhiều context đồng thời, trạng thái phải được gắn với đúng phiên hoặc người dùng. Một biến singleton dùng chung có thể làm lẫn trạng thái giữa các phiên.

### 8.3. Provider nên nhanh và không gây tác dụng phụ

Availability có thể được đánh giá nhiều lần trong quá trình shell hiển thị hoặc chuẩn bị thực thi command. Provider nên đọc trạng thái đã được quản lý và trả kết quả nhanh chóng.

Tránh thực hiện các tác vụ nặng hoặc có tác dụng phụ trong provider, chẳng hạn:

- Tải toàn bộ dữ liệu từ máy chủ chỉ để kiểm tra command.
- Tạo kết nối mới mỗi lần người dùng yêu cầu trợ giúp.
- Thay đổi trạng thái ứng dụng trong lúc đánh giá.
- Thực hiện thao tác ghi hoặc xóa dữ liệu.
- Chờ một tác vụ mạng không có giới hạn thời gian.

Nếu cần kiểm tra tình trạng dịch vụ bên ngoài, hãy cân nhắc dùng health state hoặc cache được cập nhật có kiểm soát. Provider chỉ đọc trạng thái đã có. Việc kết nối hoặc khôi phục dịch vụ nên là một command hoặc quy trình riêng.

### 8.4. Kiểm tra lại điều kiện trong nghiệp vụ

Giữa thời điểm provider trả về available và thời điểm command bắt đầu thao tác, trạng thái có thể thay đổi. Ví dụ, kết nối bị đóng ngay sau khi availability được đánh giá.

Do đó, provider không phải khóa tài nguyên và cũng không bảo đảm thao tác sẽ thành công. Service hoặc client vẫn cần xử lý lỗi kết nối và kiểm tra các bất biến quan trọng tại thời điểm thực thi.

~~~mermaid
sequenceDiagram
    participant Shell as Spring Shell
    participant Provider as AvailabilityProvider
    participant State as ConnectionState
    participant Command as Download command
    participant Client as Remote client

    Shell->>Provider: Kiểm tra availability
    Provider->>State: isConnected()
    State-->>Provider: true
    Provider-->>Shell: available()
    Note over State,Client: Kết nối có thể bị mất sau bước kiểm tra
    Shell->>Command: Gọi download
    Command->>Client: download()
    Client-->>Command: Lỗi kết nối
    Command-->>Shell: Báo lỗi thực thi
~~~

Ví dụ này cho thấy command available không đồng nghĩa với việc mọi thao tác sau đó chắc chắn thành công. Availability cải thiện trải nghiệm người dùng và ngăn các lời gọi rõ ràng không hợp lệ; xử lý lỗi trong nghiệp vụ vẫn cần thiết.

## 9. Hiển thị và kiểm tra trạng thái từ shell

Người dùng cần biết command nào tồn tại và cách sử dụng command đó. Spring Shell có command trợ giúp tích hợp:

- `help`: liệt kê command đã biết và mô tả ngắn.
- `help download`: xem thông tin chi tiết của command, bao gồm tham số.
- `download --help` hoặc `download -h`: xem trợ giúp ngắn nếu cấu hình command hỗ trợ tùy chọn help.

Khi người dùng gọi command chưa khả dụng, Spring Shell có thể trả thông báo command tồn tại nhưng hiện không thể gọi, kèm lý do từ availability provider. Cách hiển thị trạng thái unavailable trong danh sách trợ giúp có thể khác nhau theo thế hệ Spring Shell và cấu hình help, vì vậy nên kiểm tra hành vi trên phiên bản ứng dụng thực tế.

Ngoài trợ giúp tích hợp, ứng dụng nên cung cấp command trạng thái cho các phiên làm việc có nhiều bước. Ví dụ:

~~~text
shell:> status
Connection: disconnected
Selected project: none
Active transaction: none
~~~

Command trạng thái có thể luôn khả dụng, kể cả khi các command nghiệp vụ khác bị khóa. Nó giúp người dùng hiểu cần thực hiện bước nào tiếp theo.

Nên giữ nội dung trạng thái ngắn gọn và phân biệt:

- Trạng thái phiên: connected hoặc disconnected.
- Trạng thái tài nguyên: project đã chọn hay chưa.
- Trạng thái command: available hoặc unavailable.
- Trạng thái kết quả: thao tác vừa rồi thành công hay thất bại.

Không nên dùng một chuỗi trạng thái chung như `ERROR` cho mọi trường hợp. Người dùng cần biết lỗi nằm ở command chưa tồn tại, điều kiện chưa đạt, đầu vào không hợp lệ hay nghiệp vụ thất bại.

## 10. Phân biệt Availability với ExitStatus

Availability mô tả điều kiện trước khi thực thi. Exit status mô tả kết quả của lần thực thi command, đặc biệt hữu ích khi ứng dụng được gọi từ script hoặc tiến trình bên ngoài.

Trong Spring Shell 4.x, `ExitStatus` là một record chứa mã và mô tả. API cung cấp các giá trị chuẩn như:

- `ExitStatus.OK`: thực thi thành công.
- `ExitStatus.USAGE_ERROR`: lỗi cách sử dụng hoặc đầu vào command.
- `ExitStatus.EXECUTION_ERROR`: lỗi trong lúc thực thi.
- `ExitStatus.AVAILABILITY_ERROR`: lỗi do command hiện không khả dụng.

Không nên thay availability provider bằng cách tự trả exit status khi kiểm tra trạng thái. Hai cơ chế phục vụ hai giai đoạn khác nhau:

| Cơ chế | Thời điểm | Mục đích |
|---|---|---|
| `Availability` | Trước khi thực thi | Xác định command có thể được gọi ngay lúc này không |
| `ExitStatus` | Sau khi xử lý command | Báo kết quả thực thi cho shell hoặc tiến trình gọi |
| Exception | Khi có lỗi trong quá trình xử lý | Biểu diễn tình huống lỗi và có thể được ánh xạ sang exit status |

Trong mô hình command programmatic, method `execute(CommandContext)` trả về `ExitStatus`. Với command annotation, cách trả kết quả và xử lý exception phụ thuộc vào adapter cùng cấu hình của phiên bản đang dùng.

Ví dụ, `download` bị unavailable vì chưa kết nối là vấn đề availability. Nếu đã kết nối nhưng server từ chối yêu cầu tải, đó là lỗi thực thi. Nếu người dùng truyền sai tùy chọn `--file`, đó là vấn đề cú pháp hoặc validation đầu vào.

## 11. Kiểm thử availability và chuyển đổi trạng thái

Kiểm thử cần xác minh cả hai nhánh available và unavailable, đồng thời bảo đảm provider đọc đúng trạng thái sau khi ứng dụng thay đổi.

### 11.1. Kiểm thử provider độc lập

Có thể kiểm tra provider bằng unit test với một trạng thái kết nối giả lập:

~~~java
class DownloadAvailabilityTest {

    @Test
    void shouldBeUnavailableWhenDisconnected() {
        ConnectionState state = new ConnectionState();

        AvailabilityProvider provider = () -> state.isConnected()
                ? Availability.available()
                : Availability.unavailable("you are not connected");

        Availability result = provider.get();

        assertThat(result.isAvailable()).isFalse();
    }

    @Test
    void shouldBecomeAvailableAfterConnection() {
        ConnectionState state = new ConnectionState();

        AvailabilityProvider provider = () -> state.isConnected()
                ? Availability.available()
                : Availability.unavailable("you are not connected");

        state.markConnected();

        assertThat(provider.get().isAvailable()).isTrue();
    }
}
~~~

Ví dụ sử dụng API `Availability` và `AvailabilityProvider` của Spring Shell 4.x. `Availability` là record trong package `org.springframework.shell.core.command.availability`; phương thức `isAvailable()` cho biết trạng thái hiện tại. Các import JUnit, AssertJ và các kiểu Spring được lược bỏ để tập trung vào phần kiểm tra. Khi viết test thực tế, hãy import các kiểu từ cùng phiên bản dependency của dự án.

### 11.2. Kiểm thử chuyển trạng thái

Một bộ kiểm thử tốt nên bao gồm các tình huống:

1. Khởi động ứng dụng: trạng thái disconnected, `download` unavailable.
2. Kết nối thành công: trạng thái connected, `download` available.
3. Kết nối thất bại: trạng thái vẫn disconnected, `download` unavailable.
4. Ngắt kết nối thành công: trạng thái disconnected, `download` unavailable.
5. Kết nối bị mất ngoài dự kiến: provider phản ánh trạng thái mới sau khi thành phần quản lý phiên cập nhật.
6. Command bắt đầu khi available nhưng kết nối mất trước khi hoàn tất: nghiệp vụ xử lý lỗi kết nối và trả kết quả thất bại phù hợp.

### 11.3. Kiểm thử tích hợp Spring Shell

Unit test chỉ xác minh logic provider. Kiểm thử tích hợp cần xác nhận:

- Bean provider được đăng ký với đúng tên.
- Annotation command tham chiếu đúng provider.
- Spring Shell phát hiện command.
- Command bị từ chối khi provider trả unavailable.
- Lý do unavailable được hiển thị cho người dùng.
- Command chạy sau khi trạng thái chuyển thành available.
- Command vẫn xử lý lỗi nếu trạng thái thay đổi trong lúc thực thi.

Có thể dùng Spring Boot test và bộ công cụ kiểm thử shell của đúng phiên bản Spring Shell. Nên kiểm tra cả command trợ giúp và lời gọi thật để xác nhận người dùng nhận được thông tin hữu ích.

## 12. Các lỗi thường gặp khi triển khai

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Provider luôn trả available | Command chạy dù điều kiện nghiệp vụ chưa đạt | Đọc trạng thái thực tế và trả unavailable khi cần |
| Provider luôn trả unavailable | Command không thể chạy dù ứng dụng đã sẵn sàng | Kiểm tra nơi cập nhật trạng thái và bean provider |
| Tên provider trong annotation không khớp bean | Command không lấy được availability provider theo cấu hình | Kiểm tra tên bean và thuộc tính `availabilityProvider` |
| Cập nhật state trước khi kết nối thành công | Command được mở khóa quá sớm | Chỉ cập nhật sau khi thao tác kết nối thành công |
| Command và provider dùng hai nguồn state | Trạng thái hiển thị và trạng thái thực thi không đồng nhất | Dùng chung một thành phần quản lý trạng thái |
| Provider gọi API mạng chậm | Help hoặc thao tác shell có thể bị chậm | Đọc health state hoặc cache đã cập nhật |
| Chỉ kiểm tra availability, bỏ qua validation | Dữ liệu đầu vào không hợp lệ vẫn đi vào nghiệp vụ | Giữ validation trong command/service |
| Xem availability là phân quyền | Người dùng có thể gọi trực tiếp service ngoài shell | Kiểm tra authorization tại lớp nghiệp vụ |
| Không xử lý trạng thái thay đổi giữa kiểm tra và thực thi | Command vẫn có thể lỗi sau khi provider báo available | Kiểm tra lại điều kiện trong service/client |
| Dùng sai API giữa các phiên bản | Import hoặc annotation không biên dịch | Đối chiếu tài liệu và dependency đúng phiên bản |

Khi debug, nên quan sát theo trình tự:

1. Command đã được đăng ký chưa?
2. Bean chứa command có được tạo thành công không?
3. Provider được gắn đúng với command chưa?
4. Provider đang đọc nguồn trạng thái nào?
5. Trạng thái đó có được cập nhật đúng sau mỗi thao tác không?
6. Lý do unavailable có được hiển thị đúng không?
7. Khi available, lỗi có còn xảy ra ở service hoặc client không?

Trình tự này giúp tách lỗi đăng ký command, lỗi cấu hình provider và lỗi nghiệp vụ.

## 13. Bài thực hành: khóa và mở command download

Tạo một ứng dụng Spring Shell có ba command `connect`, `download` và `status`.

Yêu cầu:

1. Khi khởi động, trạng thái kết nối là disconnected.
2. `status` luôn gọi được và hiển thị trạng thái kết nối.
3. `download` được cấu hình availability provider.
4. Trước khi kết nối, gọi `download` phải nhận được lý do unavailable.
5. Sau khi `connect` thành công, `download` có thể thực thi.
6. Khi `disconnect` thành công, `download` lại unavailable.
7. Nếu thao tác tải gặp lỗi mạng, command phải trả lỗi thực thi phù hợp.

Kịch bản kiểm tra:

~~~text
shell:> status
Disconnected

shell:> download
Command 'download' exists but is not currently available because you are not connected.

shell:> connect

shell:> status
Connected

shell:> download
Download completed

shell:> disconnect

shell:> download
Command 'download' exists but is not currently available because you are not connected.
~~~

Sau khi hoàn thành, hãy bổ sung một tình huống kết nối thất bại và chứng minh trạng thái không bị chuyển thành connected. Tiếp đó, mô phỏng kết nối bị mất ngay trước lúc tải để xác nhận service vẫn xử lý lỗi thực thi.

## 14. Checklist khi đưa availability vào ứng dụng

- [ ] Xác định rõ điều kiện nghiệp vụ cần thiết cho từng command.
- [ ] Phân biệt command chưa đăng ký với command đã đăng ký nhưng unavailable.
- [ ] Dùng `Availability.available()` khi đủ điều kiện.
- [ ] Dùng `Availability.unavailable(reason)` với lý do dễ hiểu khi chưa đủ điều kiện.
- [ ] Đăng ký `AvailabilityProvider` thành Spring bean và tham chiếu đúng tên.
- [ ] Dùng chung một nguồn trạng thái cho command và provider.
- [ ] Chỉ cập nhật trạng thái sau khi thao tác thực tế thành công.
- [ ] Giữ provider nhanh, không có tác dụng phụ và tránh gọi dịch vụ bên ngoài tốn thời gian.
- [ ] Kiểm tra lại bất biến nghiệp vụ trong service khi thực thi.
- [ ] Không dùng availability thay cho validation hoặc authorization.
- [ ] Phân biệt availability với exit status của lần chạy command.
- [ ] Kiểm thử cả chuyển trạng thái, thông báo unavailable và lỗi phát sinh khi thực thi.
- [ ] Đối chiếu annotation và package API với phiên bản Spring Shell đang sử dụng.

## 15. Kết luận

Availability giúp Spring Shell phản ánh đúng khả năng thực thi command theo trạng thái hiện tại của ứng dụng. Một command có thể đã đăng ký nhưng chỉ khả dụng sau khi người dùng kết nối, đăng nhập, chọn tài nguyên hoặc hoàn tất một bước chuẩn bị.

Trong Spring Shell 4.x, có thể gắn `AvailabilityProvider` vào command annotation bằng thuộc tính `availabilityProvider`, hoặc cấu hình trực tiếp khi đăng ký command bằng builder. Các phiên bản annotation cũ sử dụng `@ShellMethodAvailability` và quy ước method trả về `Availability`.

Thiết kế tốt bắt đầu từ một nguồn trạng thái rõ ràng, cập nhật state theo kết quả thao tác thực tế và trả lý do unavailable ngắn gọn. Availability giúp hướng dẫn người dùng và chặn lời gọi chưa phù hợp ở lớp shell; service vẫn phải bảo vệ các quy tắc nghiệp vụ và xử lý lỗi có thể xảy ra trong lúc thực thi.

## Tài liệu tham khảo

- [Spring Shell Reference: Command Availability](https://docs.spring.io/spring-shell/reference/commands/availability.html)
- [Spring Shell API: Availability](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/availability/Availability.html)
- [Spring Shell API: AvailabilityProvider](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/availability/AvailabilityProvider.html)
- [Spring Shell API: Command annotation](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/Command.html)
- [Spring Shell Reference: Help](https://docs.spring.io/spring-shell/reference/commands/builtin/help.html)
- [Spring Shell API: ExitStatus](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/ExitStatus.html)
- [Spring Shell Reference: Exception Handling](https://docs.spring.io/spring-shell/reference/commands/exception-handling.html)


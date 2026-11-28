# @ShellMethodAvailability trong mô hình legacy 3.x

Trong một ứng dụng Spring Shell, có những command chỉ hợp lệ khi ứng dụng đang ở một trạng thái nhất định. Ví dụ, người dùng chỉ có thể tải dữ liệu sau khi kết nối tới máy chủ, chỉ có thể triển khai khi đã chọn môi trường hoặc chỉ có thể đóng phiên làm việc khi phiên đó đang mở.

Với mô hình annotation legacy của Spring Shell 3.x, `@ShellMethodAvailability` liên kết một command được khai báo bằng `@ShellMethod` với một method trả về `Availability`. Method này cho Spring Shell biết command hiện có thể được gọi hay không và cung cấp lý do khi command chưa khả dụng.

Bài học tập trung vào ba cách khai báo được hỗ trợ: dùng quy ước tên `commandNameAvailability`, chỉ định tên method kiểm tra trên command bằng `@ShellMethodAvailability`, và dùng một method chung để điều khiển nhiều command. Nội dung cũng giải thích cách tổ chức trạng thái, viết lý do unavailable, kiểm thử và phân biệt API legacy với mô hình annotation mới.

## 1. Command tồn tại nhưng chưa chắc khả dụng

Cần phân biệt hai trạng thái:

- **Command chưa được đăng ký:** Spring Shell không biết tên command đó, vì vậy không thể phân giải lời gọi.
- **Command đã đăng ký nhưng unavailable:** Spring Shell nhận diện command, nhưng điều kiện thực thi hiện tại chưa được đáp ứng.

Ví dụ, ứng dụng có command `download`. Command này luôn tồn tại trong shell, nhưng chỉ được gọi sau khi người dùng kết nối:

~~~text
shell:> download
Command 'download' exists but is not currently available because you are not connected.

shell:> connect
Connected

shell:> download
Download completed
~~~

Availability giúp người dùng hiểu bước nào cần hoàn thành trước khi thực hiện hành động. Command unavailable vẫn là một phần của giao diện shell và trạng thái này cũng được dùng trong phần trợ giúp tích hợp.

Một số điều kiện thường được biểu diễn bằng availability:

| Command | Điều kiện để khả dụng |
|---|---|
| `download` | Đã kết nối tới máy chủ |
| `disconnect` | Phiên kết nối đang hoạt động |
| `deploy` | Đã chọn môi trường triển khai |
| `commit` | Có transaction đang mở |
| `report export` | Đã chọn báo cáo cần xuất |
| `project delete` | Đã chọn dự án và phiên làm việc đáp ứng điều kiện cần thiết |

Availability phù hợp với điều kiện trạng thái có thể kiểm tra trước khi command bắt đầu. Nó không thay thế validation cho dữ liệu đầu vào hoặc kiểm tra quyền trong nghiệp vụ.

## 2. Availability và lớp API trong Spring Shell 3.x

Trong mô hình legacy, Spring Shell sử dụng hai thành phần chính:

- `@ShellMethod` đánh dấu method có thể được gọi như command.
- `Availability` biểu diễn trạng thái hiện tại của command.

`Availability` thuộc package `org.springframework.shell`:

~~~java
import org.springframework.shell.Availability;
~~~

Lớp này cung cấp hai factory method:

~~~java
Availability.available()
Availability.unavailable("you are not connected")
~~~

`Availability.available()` biểu thị command có thể thực thi. `Availability.unavailable(reason)` biểu thị command chưa thể thực thi và mang theo lý do giải thích.

Có thể kiểm tra kết quả qua:

~~~java
availability.isAvailable();
availability.getReason();
~~~

Method cung cấp availability phải không nhận tham số và trả về `Availability`. Nó thường đọc trạng thái do ứng dụng quản lý, chẳng hạn trạng thái kết nối, trạng thái dự án hoặc trạng thái transaction.

## 3. Điều kiện để Spring Shell nhận diện method availability

Mô hình legacy yêu cầu lớp command được đánh dấu bằng `@ShellComponent`, còn method command được đánh dấu bằng `@ShellMethod`.

Ví dụ cấu trúc cơ bản:

~~~java
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;

@ShellComponent
public class RemoteCommands {

    @ShellMethod("Connect to the remote server.")
    public void connect() {
        // Thiết lập kết nối.
    }

    @ShellMethod("Download data from the remote server.")
    public void download() {
        // Tải dữ liệu.
    }
}
~~~

Spring Shell đăng ký hai method thành command. Để điều khiển khả dụng cho `download`, ta bổ sung một method trả về `Availability`.

Method availability không phải command. Không đánh dấu nó bằng `@ShellMethod`; Spring Shell dùng nó như một bộ kiểm tra trạng thái cho command đã đăng ký.

Annotation `@ShellMethodAvailability` thuộc package:

~~~java
import org.springframework.shell.standard.ShellMethodAvailability;
~~~

Annotation này có thể được đặt trên method command hoặc trên method availability, tùy cách liên kết được chọn.

## 4. Cách 1: dùng quy ước tên `commandNameAvailability`

Đây là cách đơn giản nhất. Nếu command method có tên `download`, Spring Shell tự tìm method có tên `downloadAvailability` trong cùng lớp.

~~~java
@ShellComponent
public class RemoteCommands {

    private boolean connected;

    @ShellMethod("Connect to the remote server.")
    public String connect() {
        // Trong ứng dụng thật, chỉ đặt connected sau khi kết nối thành công.
        connected = true;
        return "Connected";
    }

    @ShellMethod("Download data from the remote server.")
    public String download() {
        return "Download completed";
    }

    public Availability downloadAvailability() {
        return connected
                ? Availability.available()
                : Availability.unavailable("you are not connected");
    }
}
~~~

Khi ứng dụng khởi động, Spring Shell nhận diện `download` là command và phát hiện method `downloadAvailability()` theo quy ước tên.

Trước khi kết nối:

~~~text
shell:> download
Command 'download' exists but is not currently available because you are not connected.
~~~

Sau khi `connect()` cập nhật trạng thái thành công, method `downloadAvailability()` trả về `Availability.available()` và command có thể được gọi.

### 4.1. Quy tắc đặt tên

Nếu command method là:

~~~java
@ShellMethod
public void download() {
}
~~~

thì method kiểm tra theo quy ước là:

~~~java
public Availability downloadAvailability() {
    // ...
}
~~~

Tên được ghép từ **tên method Java của command** và hậu tố `Availability`. Nếu command có `key` tùy chỉnh hoặc nhiều alias, quy ước vẫn dựa trên tên method Java. Vì vậy, khi tên command bên ngoài khác xa tên method, hãy cân nhắc dùng cách liên kết tường minh ở phần tiếp theo.

### 4.2. Khi nào nên dùng quy ước tên?

Cách này phù hợp khi:

- Mỗi command có một điều kiện khả dụng riêng.
- Tên method command và method availability dễ liên hệ.
- Lớp command không có nhiều quy tắc trạng thái phức tạp.
- Muốn giữ mã ngắn và dễ đọc.

Nếu nhiều command cùng phụ thuộc một trạng thái, có thể dùng một method chung để tránh lặp điều kiện.

## 5. Cách 2: chỉ định method availability bằng `@ShellMethodAvailability`

Nếu không muốn dùng quy ước tên mặc định, có thể đặt `@ShellMethodAvailability` ngay trên method command. Giá trị của annotation là tên method availability cần gọi.

~~~java
@ShellComponent
public class RemoteCommands {

    private boolean connected;

    @ShellMethod("Download data from the remote server.")
    @ShellMethodAvailability("remoteSessionAvailability")
    public String download() {
        return "Download completed";
    }

    public Availability remoteSessionAvailability() {
        return connected
                ? Availability.available()
                : Availability.unavailable("you are not connected");
    }
}
~~~

Ở ví dụ này:

- `download()` là method thực thi command.
- `remoteSessionAvailability()` là method kiểm tra.
- Chuỗi `"remoteSessionAvailability"` trong annotation phải khớp tên method kiểm tra.

`value` ở vị trí này là tên method availability, không phải tên command hoặc alias.

Cách khai báo tường minh giúp người đọc nhận ra ngay command đang phụ thuộc vào điều kiện nào. Nó cũng hữu ích khi một method kiểm tra có tên theo nghiệp vụ, ví dụ `isRemoteSessionReady()` hoặc `canExportCurrentReport()`.

### 5.1. Không nhầm tên method với command key

Giả sử command có key là `remote download`, nhưng method Java tên `download`:

~~~java
@ShellMethod(
    value = "Download data from the remote server.",
    key = "remote download"
)
public String download() {
    return "Download completed";
}
~~~

Theo quy ước tự động, method availability vẫn được đặt là `downloadAvailability()`, vì quy ước dựa vào tên method Java.

Nếu dùng liên kết tường minh, annotation chỉ định tên method kiểm tra:

~~~java
@ShellMethodAvailability("canDownload")
~~~

Không ghi `remote download` vào `@ShellMethodAvailability` trên command method. Chuỗi đó là tên command được người dùng gọi, còn `value` ở vị trí này yêu cầu tên method trả về `Availability`.

## 6. Cách 3: dùng một method availability cho nhiều command

Nhiều command có thể cùng phụ thuộc một trạng thái. Ví dụ, cả `download` và `disconnect` chỉ có ý nghĩa khi phiên kết nối đang hoạt động.

Thay vì đặt annotation trên từng command method, có thể đặt `@ShellMethodAvailability` trực tiếp trên method trả về `Availability` và liệt kê các command mà method đó điều khiển.

~~~java
@ShellComponent
public class RemoteCommands {

    private boolean connected;

    @ShellMethod("Connect to the remote server.")
    public String connect() {
        connected = true;
        return "Connected";
    }

    @ShellMethod("Download data from the remote server.")
    public String download() {
        return "Download completed";
    }

    @ShellMethod("Disconnect from the remote server.")
    public String disconnect() {
        connected = false;
        return "Disconnected";
    }

    @ShellMethod("Show the current connection status.")
    public String status() {
        return connected ? "Connected" : "Disconnected";
    }

    @ShellMethodAvailability({"download", "disconnect"})
    public Availability connectedSessionAvailability() {
        return connected
                ? Availability.available()
                : Availability.unavailable("you are not connected");
    }
}
~~~

Ở ví dụ này:

- `download` và `disconnect` dùng chung `connectedSessionAvailability()`.
- `status` không nằm trong danh sách nên vẫn có thể gọi để xem trạng thái.
- Khi `connected` là `false`, hai command trong danh sách unavailable.
- Khi `connected` là `true`, cả hai command trở nên available.

Giá trị của `@ShellMethodAvailability` trên method availability là tên command hoặc alias mà method đó điều khiển. Đây là cách khai báo khác với trường hợp annotation đặt trên method command.

### 6.1. Một method điều khiển tất cả command trong lớp

Nếu đặt annotation trên method availability mà không truyền giá trị:

~~~java
@ShellMethodAvailability
public Availability availabilityOnWeekdays() {
    return isWeekday()
            ? Availability.available()
            : Availability.unavailable("today is not a working day");
}
~~~

Giá trị mặc định của `@ShellMethodAvailability.value()` là `{"*"}`. Dấu `*` có nghĩa là method đó áp dụng cho tất cả command được triển khai trong cùng lớp.

Cách này hữu ích khi cả lớp command chỉ hoạt động trong một điều kiện chung. Tuy nhiên, hãy thận trọng nếu lớp còn chứa các command luôn cần dùng, chẳng hạn `status`, `help` nghiệp vụ hoặc `connect`. Một method wildcard có thể làm các command đó unavailable ngoài ý muốn.

Nếu chỉ một số command cần bị ảnh hưởng, hãy liệt kê rõ tên command hoặc tách chúng vào các lớp `@ShellComponent` khác nhau.

### 6.2. Tên command và alias trong danh sách

Nếu command được khai báo nhiều key, danh sách điều khiển có thể tham chiếu command name hoặc alias tương ứng.

~~~java
@ShellMethod(
    value = "Download data from the remote server.",
    key = {"download", "remote download"}
)
public String download() {
    return "Download completed";
}

@ShellMethodAvailability({"download", "remote download"})
public Availability remoteSessionAvailability() {
    return connected
            ? Availability.available()
            : Availability.unavailable("you are not connected");
}
~~~

Hãy dùng đúng key đã khai báo. Nếu command có nhiều alias và muốn tất cả tên gọi phản ánh cùng một trạng thái, hãy kiểm tra danh sách alias để không bỏ sót một đường dẫn.

## 7. So sánh ba cách liên kết

| Cách khai báo | Đặt ở đâu? | Giá trị liên kết | Phù hợp khi |
|---|---|---|---|
| Quy ước tên | Không cần annotation | `download` → `downloadAvailability()` | Một command có method kiểm tra riêng |
| Liên kết tường minh | Trên method `@ShellMethod` | Tên method availability | Muốn chọn tên method kiểm tra rõ ràng |
| Dùng chung cho nhiều command | Trên method trả về `Availability` | Tên command hoặc alias | Nhiều command dùng chung trạng thái |

Có thể chọn cách phù hợp với cấu trúc lớp. Tránh khai báo nhiều cơ chế cho cùng một command nếu không có lý do rõ ràng, vì khi đó người bảo trì khó biết method nào đang điều khiển availability.

## 8. Cách viết lý do unavailable

Khi command chưa khả dụng, Spring Shell cần một lý do để giải thích cho người dùng:

~~~java
return Availability.unavailable("you are not connected");
~~~

Thông báo được ghép theo cách đọc tự nhiên, ví dụ:

~~~text
Command 'download' exists but is not currently available because you are not connected.
~~~

Vì shell thêm cụm giải thích phía trước, lý do nên tuân theo các quy tắc:

- Bắt đầu bằng chữ thường.
- Không thêm dấu chấm ở cuối.
- Nêu điều kiện còn thiếu bằng ngôn ngữ người dùng hiểu.
- Tránh thông báo kỹ thuật như tên biến, exception hoặc mã nội bộ.

Ví dụ:

| Lý do nội bộ | Reason nên hiển thị |
|---|---|
| Chưa kết nối máy chủ | `you are not connected` |
| Chưa chọn dự án | `no project is selected` |
| Chưa có báo cáo | `no report is available for export` |
| Transaction đã đóng | `the transaction is already closed` |
| Chưa đăng nhập | `you are not signed in` |

Không cần đưa cả câu hoàn chỉnh vào `unavailable(reason)`, vì Spring Shell sẽ ghép reason vào thông báo của nó.

## 9. Availability được dùng trong trợ giúp và khi gọi command

Availability không chỉ được kiểm tra khi người dùng nhập lệnh. Thông tin command unavailable còn được dùng trong trợ giúp tích hợp.

Người dùng có thể xem danh sách command bằng:

~~~text
shell:> help
~~~

Nếu một command unavailable, trạng thái này được phản ánh trong phần trợ giúp theo hành vi của phiên bản Spring Shell đang dùng. Khi người dùng gọi command unavailable, shell thông báo command tồn tại nhưng hiện không thể thực thi và đưa ra reason.

Điều này giúp người dùng phân biệt:

- Gõ sai tên command hoặc command chưa đăng ký.
- Command có tồn tại nhưng điều kiện hiện tại chưa đáp ứng.
- Command đã chạy và gặp lỗi trong quá trình thực thi.

Không nên dùng availability để ẩn một command khỏi trợ giúp nếu mục tiêu thực sự là loại command khỏi giao diện. Availability biểu diễn trạng thái thực thi; việc ẩn hoặc đăng ký/gỡ command là cơ chế khác.

## 10. Quản lý trạng thái mà availability đọc

Method availability cần đọc một nguồn trạng thái đáng tin cậy. Trong ví dụ nhỏ, trạng thái có thể là một boolean. Ứng dụng thực tế thường nên tách trạng thái phiên khỏi command class để các thành phần dùng chung một quy tắc.

Ví dụ một bean quản lý phiên kết nối:

~~~java
@Component
public class RemoteSession {

    private volatile boolean connected;

    public boolean isConnected() {
        return connected;
    }

    public void markConnected() {
        connected = true;
    }

    public void markDisconnected() {
        connected = false;
    }
}
~~~

Command và method availability cùng sử dụng bean này:

~~~java
@ShellComponent
public class RemoteCommands {

    private final RemoteSession session;

    public RemoteCommands(RemoteSession session) {
        this.session = session;
    }

    @ShellMethod("Connect to the remote server.")
    public String connect() {
        // Thực hiện kết nối thật trước; chỉ cập nhật state khi thành công.
        session.markConnected();
        return "Connected";
    }

    @ShellMethod("Download data from the remote server.")
    public String download() {
        return "Download completed";
    }

    public Availability downloadAvailability() {
        return session.isConnected()
                ? Availability.available()
                : Availability.unavailable("you are not connected");
    }
}
~~~

Trong ứng dụng thật, phần `connect()` cần gọi remote client trước rồi mới đánh dấu connected. Nếu thao tác kết nối thất bại, trạng thái phải tiếp tục là disconnected.

Tương tự, chỉ đánh dấu disconnected sau khi quy trình ngắt kết nối đã hoàn tất theo quy tắc ứng dụng. Nếu kết nối bị mất ngoài dự kiến, thành phần quản lý phiên cần cập nhật trạng thái để availability phản ánh tình trạng mới.

### 10.1. Tránh thực hiện I/O nặng trong method availability

Method availability có thể được Spring Shell gọi khi cần xác định trạng thái command, kể cả trong ngữ cảnh trợ giúp. Vì vậy, method nên nhanh và không tạo tác dụng phụ.

Không nên:

- Mở kết nối mạng mới mỗi lần kiểm tra availability.
- Truy vấn database nặng chỉ để xác định command có thể gọi không.
- Thay đổi trạng thái ứng dụng trong method availability.
- Ghi dữ liệu hoặc thực hiện thao tác nghiệp vụ.
- Giữ lock lâu hoặc chờ tác vụ không có timeout.

Nên đọc trạng thái đã được quản lý trong bộ nhớ hoặc một health state được cập nhật có kiểm soát. Việc kết nối, xác thực hoặc khôi phục dịch vụ nên nằm trong command hoặc service chuyên trách.

### 10.2. Phạm vi của trạng thái

Một bean singleton chứa `connected` phù hợp với ứng dụng CLI cục bộ chỉ có một phiên làm việc. Nếu ứng dụng phục vụ nhiều người dùng hoặc nhiều phiên đồng thời, trạng thái kết nối phải được gắn với đúng session hoặc user context.

Không dùng một biến singleton chung để biểu diễn trạng thái của nhiều người dùng độc lập, vì command của người này có thể làm thay đổi availability của người khác.

## 11. Availability không thay thế validation, authorization hoặc xử lý lỗi

Availability chỉ giúp shell xác định điều kiện hiện tại trước khi gọi command. Nó không đảm bảo nghiệp vụ sẽ thành công.

Ví dụ, `download` có thể available khi kết nối đang hoạt động. Nhưng ngay sau khi shell kiểm tra availability, kết nối có thể bị ngắt. Command vẫn cần xử lý lỗi từ remote client.

Cần phân biệt:

| Cơ chế | Câu hỏi được trả lời | Ví dụ |
|---|---|---|
| Availability | Command có thể bắt đầu ngay lúc này không? | Đã kết nối chưa? |
| Validation | Giá trị đầu vào có hợp lệ không? | Tên file có đúng định dạng không? |
| Authorization | Người dùng có quyền thực hiện không? | Có quyền tải báo cáo này không? |
| Exception handling | Điều gì xảy ra khi thực thi gặp lỗi? | Máy chủ ngắt kết nối giữa lúc tải |

Không nên xem command unavailable là một lớp bảo mật. Service vẫn phải kiểm tra quyền ở nơi thực hiện hành động. Nếu một quy tắc quan trọng có thể thay đổi giữa lúc availability được đánh giá và lúc command chạy, service cần kiểm tra lại điều kiện đó.

## 12. Kiểm thử method availability

Có thể kiểm thử method availability trực tiếp bằng JUnit để xác minh hai nhánh available và unavailable.

Ví dụ với lớp command có method `downloadAvailability()`:

~~~java
class RemoteCommandsTests {

    private final RemoteSession session = new RemoteSession();
    private final RemoteCommands commands = new RemoteCommands(session);

    @Test
    void downloadIsUnavailableBeforeConnection() {
        Availability availability = commands.downloadAvailability();

        assertThat(availability.isAvailable()).isFalse();
        assertThat(availability.getReason())
                .isEqualTo("you are not connected");
    }

    @Test
    void downloadBecomesAvailableAfterConnection() {
        session.markConnected();

        Availability availability = commands.downloadAvailability();

        assertThat(availability.isAvailable()).isTrue();
    }

    @Test
    void downloadBecomesUnavailableAfterDisconnect() {
        session.markConnected();
        session.markDisconnected();

        Availability availability = commands.downloadAvailability();

        assertThat(availability.isAvailable()).isFalse();
    }
}
~~~

Các test này xác minh logic trạng thái và nội dung reason. Chúng chưa chứng minh Spring Shell đã liên kết đúng method availability với command.

### 12.1. Kiểm thử liên kết trong Spring Shell

Nên bổ sung kiểm thử tích hợp bằng test support của Spring Shell 3.x, chẳng hạn `@ShellTest` và `ShellTestClient`, để xác nhận:

1. Bean `@ShellComponent` được phát hiện.
2. Method `@ShellMethod` được đăng ký thành command.
3. Quy ước `downloadAvailability()` được nhận diện, hoặc tên được khai báo trong `@ShellMethodAvailability` được liên kết đúng.
4. Command bị từ chối khi availability trả unavailable.
5. Reason được hiển thị cho người dùng.
6. Command chạy sau khi trạng thái chuyển thành available.
7. Help phản ánh trạng thái command theo cấu hình.

Nếu dùng annotation trên method availability để điều khiển nhiều command, hãy kiểm thử cả command có trong danh sách và command không có trong danh sách. Nếu dùng wildcard `*`, hãy kiểm tra các command khác trong cùng lớp để tránh khóa nhầm.

### 12.2. Kiểm thử thủ công trong shell

Có thể chạy một kịch bản đơn giản:

~~~text
shell:> status
Disconnected

shell:> download
Command 'download' exists but is not currently available because you are not connected.

shell:> connect
Connected

shell:> download
Download completed
~~~

Sau đó kiểm tra `help` trước và sau khi kết nối để quan sát thông tin khả dụng trong trợ giúp.

## 13. Các lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Command luôn available | Method trả `Availability.available()` trong mọi trường hợp | Đọc trạng thái thực tế |
| Command luôn unavailable | State không được cập nhật sau thao tác thành công | Cập nhật state sau khi kết nối hoặc chuẩn bị hoàn tất |
| Không tìm thấy method availability | Tên không theo quy ước hoặc tên trong annotation sai | Kiểm tra tên Java method và `value` |
| Method availability có tham số | Không đáp ứng hợp đồng method kiểm tra không tham số | Dùng method không tham số trả `Availability` |
| Reason hiển thị câu khó đọc | Reason viết hoa đầu câu hoặc có dấu chấm cuối | Viết reason chữ thường, không có dấu chấm |
| Command dùng alias nhưng kiểm tra nhóm bỏ sót | Danh sách annotation chưa bao gồm alias cần điều khiển | Liệt kê đúng command key và alias |
| Command không liên quan cũng unavailable | Dùng wildcard `*` trên method chung | Chỉ định command cụ thể hoặc tách lớp |
| Help không phản ánh đúng trạng thái | Liên kết availability chưa được nhận diện hoặc state không cập nhật | Kiểm tra mapping và nguồn state |
| Kết nối mất sau khi availability trả available | Trạng thái thay đổi giữa kiểm tra và thực thi | Service/client vẫn phải xử lý lỗi |
| Dùng availability như phân quyền | Tin rằng command bị khóa là đủ bảo vệ nghiệp vụ | Kiểm tra authorization trong service |

## 14. Phân biệt legacy `@ShellMethodAvailability` với mô hình annotation mới

Spring Shell 3.1.x hỗ trợ cả mô hình annotation legacy và mô hình annotation mới. Legacy model dùng `@ShellComponent`, `@ShellMethod`, `@ShellOption`; mô hình mới dùng `@Command`, `@Option` và `@Argument`.

`@ShellMethodAvailability` thuộc mô hình legacy. Trong mô hình annotation mới, availability được cấu hình qua `AvailabilityProvider` bean và thuộc tính `availabilityProvider` của `@Command`.

Ví dụ minh họa khác biệt:

| Mô hình | Khai báo command | Cách gắn availability |
|---|---|---|
| Legacy annotation 3.x | `@ShellComponent` + `@ShellMethod` | `@ShellMethodAvailability` hoặc quy ước `methodNameAvailability()` |
| Annotation mới | `@Command` | Thuộc tính `availabilityProvider` trỏ tới bean `AvailabilityProvider` |
| Programmatic | `CommandRegistration` | Cấu hình availability provider trên registration |

Không trộn `@ShellMethodAvailability` vào ví dụ `@Command`. Khi dự án chuyển từ legacy sang mô hình mới, hãy chuyển logic kiểm tra trạng thái sang `AvailabilityProvider` và kiểm tra lại việc đăng ký command.

## 15. Checklist triển khai

- [ ] Lớp command được đánh dấu `@ShellComponent`.
- [ ] Method cần kiểm soát được đánh dấu `@ShellMethod`.
- [ ] Method availability không nhận tham số và trả về `Availability`.
- [ ] Nếu dùng quy ước tên, tên method là `<tênMethodCommand>Availability`.
- [ ] Nếu dùng annotation trên command, `value` khớp tên method availability.
- [ ] Nếu dùng annotation trên availability method, `value` liệt kê đúng command name hoặc alias.
- [ ] Đã hiểu wildcard mặc định `*` áp dụng cho tất cả command trong cùng lớp.
- [ ] Reason ngắn gọn, chữ thường và không có dấu chấm cuối.
- [ ] State được cập nhật sau khi thao tác thực tế thành công.
- [ ] Method availability nhanh, không có tác dụng phụ và không thực hiện I/O nặng.
- [ ] Service vẫn kiểm tra quyền và xử lý trạng thái thay đổi trong lúc thực thi.
- [ ] Đã kiểm thử cả available và unavailable.
- [ ] Đã kiểm thử liên kết annotation và hành vi trong help.
- [ ] Không dùng `@ShellMethodAvailability` thay cho API `AvailabilityProvider` của mô hình annotation mới.

## 16. Kết luận

Trong mô hình annotation legacy của Spring Shell 3.x, `@ShellMethodAvailability` liên kết command với một method không tham số trả về `Availability`. Có thể dùng quy ước tên `<commandMethod>Availability()`, chỉ định tên method kiểm tra ngay trên command, hoặc gắn một method chung với danh sách command cần điều khiển.

Hãy chọn cách liên kết phù hợp với số lượng command và trạng thái dùng chung. Quản lý state ở một nguồn rõ ràng, chỉ cập nhật sau khi thao tác thành công, viết reason dễ hiểu và giữ method availability nhẹ. Availability giúp shell hướng dẫn người dùng trước khi gọi lệnh; validation, authorization và xử lý lỗi vẫn phải được bảo đảm trong các lớp tương ứng.

## Tài liệu tham khảo

- [Spring Shell 3.1.1 Reference: Dynamic Command Availability](https://docs.spring.io/spring-shell/docs/3.1.1/docs/#dynamic-command-availability)
- [Spring Shell 3.1.6 Reference: Dynamic Command Availability](https://docs.spring.io/spring-shell/docs/3.1.6/docs/index.html)
- [Spring Shell 3.1 API: `@ShellMethodAvailability`](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/standard/ShellMethodAvailability.html)
- [Spring Shell 3.1 API: `Availability`](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/Availability.html)
- [Spring Shell 3.1 API: `@ShellMethod`](https://docs.spring.io/spring-shell/docs/3.1.x/api/org/springframework/shell/standard/ShellMethod.html)
- [Spring Shell 3.1.1 Reference: Testing](https://docs.spring.io/spring-shell/docs/3.1.1/docs/#testing)
- [Spring Shell Reference: Command Availability in the new annotation model](https://docs.spring.io/spring-shell/reference/commands/availability.html)


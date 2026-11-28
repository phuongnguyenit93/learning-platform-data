# Availability của command annotation hoặc builder trong 3.x

Trong Spring Shell 3.x, một command có thể đã được đăng ký nhưng chỉ thực hiện được khi ứng dụng đang ở trạng thái phù hợp. Ví dụ, người dùng chỉ được gọi `download` sau khi kết nối tới máy chủ; command `deploy` chỉ được chạy khi môi trường đã được chọn; command `publish` chỉ khả dụng khi bản dựng đã hoàn tất.

Spring Shell cung cấp cơ chế **Availability** để mô tả trạng thái đó. Ứng dụng trả về `Availability.available()` khi command có thể chạy, hoặc `Availability.unavailable(reason)` khi command tạm thời không thể chạy và cần giải thích lý do.

Với mô hình command mới của Spring Shell 3.x, có hai cách khai báo phổ biến:

- Dùng annotation `@Command` kết hợp `@CommandAvailability` và bean `AvailabilityProvider`.
- Dùng API lập trình `CommandRegistration.Builder.availability(...)` với một `Supplier<Availability>`.

Bài học dùng API Spring Shell 3.3.4 làm mốc. Cần phân biệt cơ chế này với `InteractionMode`, với việc ẩn command khỏi trợ giúp và với kiểm tra quyền nghiệp vụ.

## 1. Availability giải quyết vấn đề gì?

Một command được đăng ký nghĩa là shell biết tên command và biết cách định tuyến đến phần xử lý. Điều đó không có nghĩa command luôn có thể thực hiện.

Giả sử CLI quản lý kết nối từ xa:

| Command | Điều kiện |
|---|---|
| `connect` | Có thể gọi khi chưa kết nối |
| `disconnect` | Chỉ có thể gọi khi đã kết nối |
| `download` | Chỉ có thể gọi khi đã kết nối |
| `server status` | Có thể gọi ở cả hai trạng thái |

Nếu không có availability, người dùng có thể gọi `download` khi chưa kết nối. Command vẫn được tìm thấy, nhưng phần xử lý sẽ thất bại ở một bước sâu hơn, có thể tạo ra lỗi khó hiểu.

Availability cho phép shell kiểm tra điều kiện trước khi thực thi command. Khi điều kiện chưa đạt, shell có thể giải thích rằng command tồn tại nhưng hiện chưa thể gọi.

### 1.1. Hai trạng thái cơ bản

`Availability` là đối tượng mô tả khả dụng hiện tại:

| API | Ý nghĩa |
|---|---|
| `Availability.available()` | Command có thể thực thi |
| `Availability.unavailable(reason)` | Command tạm thời không thể thực thi; cung cấp lý do |
| `isAvailable()` | Đọc trạng thái khả dụng |
| `getReason()` | Đọc lý do khi không khả dụng |

Ví dụ:

```java
Availability.available();

Availability.unavailable("chưa kết nối tới máy chủ");
```

Lý do nên ngắn gọn, dễ hiểu và mô tả điều kiện đang thiếu. Spring Shell ghép lý do vào thông báo dạng “Command ... exists but is not currently available because ...”. Vì vậy, nên viết phần lý do như một vế câu, bắt đầu bằng chữ thường và không thêm dấu chấm cuối.

### 1.2. Availability không xóa command

Khi command không khả dụng:

- Command vẫn được đăng ký trong shell.
- Người dùng vẫn có thể biết command tồn tại qua trợ giúp.
- Shell có thể hiển thị trạng thái hoặc lý do command chưa thể chạy.
- Khi trạng thái ứng dụng thay đổi, command có thể trở nên khả dụng mà không cần đăng ký lại.

Đây là điểm khác với `hidden`. Thuộc tính ẩn điều khiển việc command có xuất hiện trong danh sách trợ giúp thông thường hay không; availability mô tả command có thể thực thi ở thời điểm hiện tại hay không.

## 2. Dùng annotation @Command và @CommandAvailability

Trong mô hình annotation mới của Spring Shell 3.x, `@Command` khai báo command trên phương thức. Có thể bổ sung `@CommandAvailability` để chỉ định bean cung cấp trạng thái khả dụng.

Thuộc tính `provider` của `@CommandAvailability` là tên bean cung cấp `Availability`. Bean đó có kiểu `AvailabilityProvider`, một functional interface kế thừa `Supplier<Availability>` nên có thể triển khai bằng lambda.

### 2.1. Ví dụ: chỉ tải dữ liệu sau khi kết nối

Trước hết, tạo một service giữ trạng thái kết nối:

```java
import org.springframework.stereotype.Component;

@Component
public class RemoteSession {

    private volatile boolean connected;

    public boolean isConnected() {
        return connected;
    }

    public void connect() {
        // Thực hiện kết nối tới máy chủ trong ứng dụng thực tế.
        connected = true;
    }

    public void disconnect() {
        connected = false;
    }

    public void download() {
        if (!connected) {
            throw new IllegalStateException("Chưa kết nối tới máy chủ");
        }

        // Thực hiện tải dữ liệu.
    }
}
```

Command sử dụng service này:

```java
import org.springframework.shell.command.annotation.Command;
import org.springframework.shell.command.annotation.CommandAvailability;
import org.springframework.stereotype.Component;

@Component
public class RemoteCommands {

    private final RemoteSession session;

    public RemoteCommands(RemoteSession session) {
        this.session = session;
    }

    @Command(command = "connect")
    public String connect() {
        session.connect();
        return "Đã kết nối tới máy chủ";
    }

    @Command(command = "disconnect")
    public String disconnect() {
        session.disconnect();
        return "Đã ngắt kết nối";
    }

    @Command(command = "download")
    @CommandAvailability(provider = "downloadAvailability")
    public String download() {
        session.download();
        return "Đã tải dữ liệu";
    }
}
```

Lớp có `@Command` cần được đăng ký làm command target. Trong ứng dụng Spring Boot, đặt `@CommandScan` trên lớp ứng dụng để quét các command trong package của lớp đó và các package con:

```java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.shell.command.annotation.CommandScan;

@SpringBootApplication
@CommandScan
public class ProjectCliApplication {

    public static void main(String[] args) {
        SpringApplication.run(ProjectCliApplication.class, args);
    }
}
```

Nếu không dùng quét package, có thể khai báo lớp command cụ thể bằng `@EnableCommand(RemoteCommands.class)` trên một lớp cấu hình. `@Component` giúp Spring tạo bean để inject dependency; `@CommandScan` hoặc `@EnableCommand` đảm nhiệm việc đăng ký target của mô hình annotation mới.

Tiếp theo, khai báo bean cung cấp availability:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.Availability;
import org.springframework.shell.AvailabilityProvider;

@Configuration
public class AvailabilityConfiguration {

    @Bean("downloadAvailability")
    public AvailabilityProvider downloadAvailability(RemoteSession session) {
        return () -> session.isConnected()
            ? Availability.available()
            : Availability.unavailable("chưa kết nối tới máy chủ");
    }
}
```

Trong ví dụ:

1. `@Command(command = "download")` đăng ký command `download`.
2. `@CommandAvailability(provider = "downloadAvailability")` liên kết command với bean availability có tên `downloadAvailability`.
3. Bean trả về một `AvailabilityProvider`.
4. Provider đọc trạng thái hiện tại từ `RemoteSession`.
5. Nếu đã kết nối, provider trả về `Availability.available()`.
6. Nếu chưa kết nối, provider trả về `Availability.unavailable(...)` cùng lý do.

Tên trong `provider` phải khớp với tên bean được Spring đăng ký. Dùng tên bean tường minh trong `@Bean` giúp tránh phụ thuộc vào quy tắc đặt tên phương thức.

### 2.2. Kết quả khi gọi command

Trước khi kết nối:

```text
shell:>download
Command 'download' exists but is not currently available because chưa kết nối tới máy chủ
```

Sau khi kết nối:

```text
shell:>connect
Đã kết nối tới máy chủ

shell:>download
Đã tải dữ liệu
```

Command `download` không cần đăng ký lại. Provider được hỏi về trạng thái hiện tại và trả về kết quả tương ứng.

## 3. AvailabilityProvider và cách tổ chức bean

`AvailabilityProvider` là interface dùng để cung cấp trạng thái khả dụng. Nó kế thừa `Supplier<Availability>`, vì vậy chỉ cần triển khai phương thức `get()`.

Một lambda có thể dùng trực tiếp:

```java
@Bean("downloadAvailability")
AvailabilityProvider downloadAvailability(RemoteSession session) {
    return () -> session.isConnected()
        ? Availability.available()
        : Availability.unavailable("chưa kết nối tới máy chủ");
}
```

Nếu điều kiện phức tạp hơn, có thể viết một lớp triển khai riêng:

```java
import org.springframework.shell.Availability;
import org.springframework.shell.AvailabilityProvider;

public class DownloadAvailabilityProvider implements AvailabilityProvider {

    private final RemoteSession session;

    public DownloadAvailabilityProvider(RemoteSession session) {
        this.session = session;
    }

    @Override
    public Availability get() {
        if (!session.isConnected()) {
            return Availability.unavailable("chưa kết nối tới máy chủ");
        }

        return Availability.available();
    }
}
```

Đăng ký provider thành bean:

```java
@Bean("downloadAvailability")
AvailabilityProvider downloadAvailability(RemoteSession session) {
    return new DownloadAvailabilityProvider(session);
}
```

Dùng lambda phù hợp với điều kiện ngắn. Dùng lớp riêng khi logic cần nhiều nhánh, phụ thuộc nhiều service hoặc cần unit test độc lập.

### 3.1. Một provider có thể được tái sử dụng

Nếu nhiều command phụ thuộc cùng một trạng thái, có thể dùng chung một provider hoặc định nghĩa provider riêng cho từng command. Chẳng hạn `download`, `upload` và `sync` đều yêu cầu kết nối.

Khi dùng chung, hãy đặt tên bean phản ánh điều kiện, ví dụ `connectedAvailability`. Khi dùng provider riêng, tên bean nên thể hiện command mà nó kiểm soát. Dù chọn cách nào, mỗi provider cần có một trách nhiệm rõ ràng và trả về lý do phù hợp với command tương ứng.

## 4. Dùng CommandRegistration.Builder trong mô hình programmatic

Khi đăng ký command bằng API lập trình, không cần đặt `@CommandAvailability`. Thay vào đó, `CommandRegistration.Builder` cung cấp phương thức `availability(...)`, nhận một `Supplier<Availability>`.

Ví dụ:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.Availability;
import org.springframework.shell.command.CommandRegistration;

@Configuration
public class DownloadCommandConfiguration {

    @Bean
    public CommandRegistration downloadCommand(
            CommandRegistration.BuilderSupplier builder,
            RemoteSession session) {

        return builder.get()
            .command("download")
            .description("Tải dữ liệu từ máy chủ")
            .availability(() -> session.isConnected()
                ? Availability.available()
                : Availability.unavailable("chưa kết nối tới máy chủ"))
            .withTarget()
                .consumer(context -> session.download())
                .and()
            .build();
    }
}
```

Các phần chính:

- `CommandRegistration.BuilderSupplier` cung cấp builder theo cấu hình Spring Shell.
- `builder.get()` lấy một builder mới.
- `command("download")` đặt tên command.
- `description(...)` cung cấp mô tả cho trợ giúp.
- `availability(...)` gắn supplier trả về trạng thái khả dụng.
- `withTarget().consumer(...)` khai báo hành vi thực thi.
- `and().build()` hoàn tất `CommandRegistration`.

Trong trường hợp này, supplier được khai báo ngay tại nơi tạo command. Nó đọc trạng thái từ `RemoteSession` mỗi lần được đánh giá.

Bean kiểu `CommandRegistration` được Spring Shell đưa vào `CommandCatalog` thông qua cơ chế auto-configuration của ứng dụng Spring Boot. Vì vậy, với command cố định, chỉ cần khai báo bean đăng ký; không cần tự gọi catalog để thêm từng command.

Có thể dùng `CommandRegistration.builder()` để tạo builder trực tiếp trong các trường hợp phù hợp. Khi làm việc trong Spring context, `BuilderSupplier` là cách được tài liệu Spring Shell 3.3.4 minh họa cho bean đăng ký command.

### 4.1. Availability được tính lại theo trạng thái

Không nên tính availability một lần khi ứng dụng khởi động rồi lưu kết quả cố định. Supplier cần đọc trạng thái hiện tại:

```java
.availability(() -> session.isConnected()
    ? Availability.available()
    : Availability.unavailable("chưa kết nối tới máy chủ"))
```

Nếu lưu kết quả vào một biến từ lúc khởi động, command có thể tiếp tục bị đánh dấu không khả dụng ngay cả sau khi người dùng đã kết nối.

## 5. So sánh hai cách khai báo trong mô hình mới

| Tiêu chí | Annotation | Programmatic builder |
|---|---|---|
| Khai báo command | `@Command` trên phương thức | `CommandRegistration.Builder` |
| Khai báo availability | `@CommandAvailability(provider = "...")` | `.availability(...)` |
| Nguồn trạng thái | Bean `AvailabilityProvider` | `Supplier<Availability>` |
| Vị trí logic | Trong provider bean | Trong supplier hoặc lớp provider |
| Tái sử dụng điều kiện | Dùng chung provider bean | Dùng chung supplier hoặc phương thức |
| Phù hợp | Command gắn với phương thức Spring bean | Command được tạo bằng cấu hình hoặc code |

Hãy chọn annotation khi command đã được biểu diễn tự nhiên bằng phương thức Java và muốn giữ metadata gần phương thức đó. Chọn builder khi command được tạo bằng code, cần cấu hình động hoặc target không phải một phương thức command annotation.

Hai cách dùng chung mô hình kết quả `Availability`, vì vậy cách diễn đạt trạng thái và lý do có thể thống nhất trong toàn ứng dụng.

## 6. Phân biệt Availability với InteractionMode

`InteractionMode` và `Availability` đều ảnh hưởng đến khả năng gọi command, nhưng kiểm tra hai loại điều kiện khác nhau.

- `InteractionMode` cho biết command phù hợp với chế độ shell nào, chẳng hạn interactive hoặc non-interactive.
- `Availability` kiểm tra trạng thái hiện tại của ứng dụng, chẳng hạn đã kết nối, đã chọn project hoặc đã hoàn tất bước khởi tạo hay chưa.

Ví dụ:

| Điều kiện | Cơ chế phù hợp |
|---|---|
| Chỉ chạy command khi shell ở chế độ tương tác | `InteractionMode.INTERACTIVE` |
| Chỉ chạy command trong chế độ không tương tác | `InteractionMode.NONINTERACTIVE` |
| Chỉ tải dữ liệu sau khi kết nối | `Availability` |
| Chỉ triển khai khi đã chọn môi trường | `Availability` |
| Chỉ cho phép thao tác sau khi khởi tạo dữ liệu | `Availability` |

Không dùng `InteractionMode` để biểu diễn trạng thái đăng nhập hoặc trạng thái kết nối. Cũng không dùng `Availability` để thay thế cấu hình chế độ chạy shell.

## 7. Phân biệt Availability với hidden và phân quyền

Ba khái niệm này cần được giữ riêng:

| Cơ chế | Câu hỏi được trả lời | Tác động |
|---|---|---|
| `Availability` | Command có thể chạy ngay lúc này không? | Tạm chặn thực thi và giải thích lý do |
| `hidden` | Command có xuất hiện trong trợ giúp thông thường không? | Điều khiển khả năng khám phá command |
| Authorization | Người dùng có quyền thực hiện thao tác không? | Bảo vệ thao tác ở lớp bảo mật/nghiệp vụ |

Availability không phải cơ chế bảo mật. Người dùng có thể gọi service từ một giao diện khác mà không đi qua Spring Shell. Hơn nữa, trạng thái có thể thay đổi giữa lúc shell kiểm tra availability và lúc command thực thi.

Vì vậy, command handler hoặc application service vẫn phải kiểm tra điều kiện quan trọng trước khi thực hiện thao tác. Nếu thao tác cần phân quyền, hãy kiểm tra quyền ở lớp bảo mật hoặc nghiệp vụ.

Ví dụ, provider có thể kiểm tra rằng người dùng đã chọn project. Nhưng service thực hiện xóa project vẫn phải xác minh người dùng có quyền xóa project đó.

## 8. Thiết kế provider an toàn và dễ bảo trì

Một availability provider có thể được shell gọi nhiều lần khi hiển thị trợ giúp hoặc trước khi thực thi command. Vì vậy, provider nên có các đặc điểm sau:

**Nhanh và không gây tác dụng phụ.** Provider nên đọc trạng thái đã có trong service hoặc session. Không nên bắt đầu kết nối, ghi dữ liệu hoặc thay đổi trạng thái trong `get()`.

**Trả lý do có thể hành động.** Thay vì thông báo chung chung như `command unavailable`, hãy nói rõ điều kiện còn thiếu: `chưa kết nối tới máy chủ`, `chưa chọn môi trường triển khai`.

**Không thực hiện kiểm tra mạng tốn kém mỗi lần được gọi.** Nếu cần kiểm tra trạng thái từ xa, hãy duy trì trạng thái kết nối hoặc dùng cache có thời hạn phù hợp. Provider nên đọc trạng thái đã được cập nhật thay vì tự gọi một API chậm mỗi lần shell cần hiển thị trợ giúp.

**Không tiết lộ thông tin nhạy cảm.** Lý do không khả dụng nên giải thích điều kiện cần thiết mà không hiển thị token, mật khẩu, địa chỉ nội bộ hoặc dữ liệu bí mật.

**Đọc trạng thái từ một nguồn có thẩm quyền.** Nên lấy trạng thái từ service quản lý phiên hoặc trạng thái ứng dụng. Tránh duy trì nhiều biến boolean ở nhiều command class vì chúng có thể không đồng bộ.

**Kiểm tra lại trong nghiệp vụ.** Availability hỗ trợ trải nghiệm người dùng; service vẫn cần xác minh điều kiện trước thao tác thực tế.

## 9. Kiểm thử availability

Có thể kiểm thử provider độc lập mà không cần chạy toàn bộ shell. Mục tiêu là xác nhận provider phản ánh đúng trạng thái của service.

Ví dụ:

```java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.shell.Availability;
import org.springframework.shell.AvailabilityProvider;

class DownloadAvailabilityTests {

    @Test
    void unavailableBeforeConnection() {
        RemoteSession session = new RemoteSession();

        AvailabilityProvider provider = () -> session.isConnected()
            ? Availability.available()
            : Availability.unavailable("chưa kết nối tới máy chủ");

        Availability availability = provider.get();

        assertFalse(availability.isAvailable());
        assertTrue(availability.getReason().contains("chưa kết nối"));
    }

    @Test
    void availableAfterConnection() {
        RemoteSession session = new RemoteSession();
        session.connect();

        AvailabilityProvider provider = () -> session.isConnected()
            ? Availability.available()
            : Availability.unavailable("chưa kết nối tới máy chủ");

        assertTrue(provider.get().isAvailable());
    }
}
```

Các trường hợp nên kiểm tra:

| Trạng thái đầu vào | Kỳ vọng |
|---|---|
| Chưa kết nối | Không khả dụng, có lý do |
| Đã kết nối | Khả dụng |
| Đã ngắt kết nối sau khi từng kết nối | Trở lại không khả dụng |
| Service trạng thái chưa khởi tạo | Xử lý theo chính sách rõ ràng |
| Nguồn trạng thái gặp lỗi | Trả trạng thái an toàn hoặc để lỗi được xử lý theo chính sách ứng dụng |

Ngoài unit test, nên kiểm tra tích hợp với shell để xác nhận command không thực thi khi unavailable, trợ giúp thể hiện trạng thái phù hợp và command trở lại hoạt động sau khi trạng thái thay đổi.

## 10. Availability trong mô hình legacy @ShellMethod

Spring Shell 3.x còn hỗ trợ mô hình annotation legacy. Với `@ShellMethod`, cách khai báo availability khác với mô hình `@Command`.

Một phương thức command có thể có phương thức availability cùng tên và hậu tố `Availability`:

```java
import org.springframework.shell.Availability;
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;

@ShellComponent
public class LegacyRemoteCommands {

    private boolean connected;

    @ShellMethod("Kết nối tới máy chủ")
    public void connect() {
        connected = true;
    }

    @ShellMethod("Tải dữ liệu từ máy chủ")
    public void download() {
        // Thực hiện tải dữ liệu.
    }

    public Availability downloadAvailability() {
        return connected
            ? Availability.available()
            : Availability.unavailable("chưa kết nối tới máy chủ");
    }
}
```

Nếu không muốn dùng quy tắc đặt tên mặc định, có thể gắn `@ShellMethodAvailability` lên command để chỉ rõ tên phương thức availability:

```java
import org.springframework.shell.Availability;
import org.springframework.shell.standard.ShellComponent;
import org.springframework.shell.standard.ShellMethod;
import org.springframework.shell.standard.ShellMethodAvailability;

@ShellComponent
public class LegacyRemoteCommands {

    private boolean connected;

    @ShellMethod("Tải dữ liệu từ máy chủ")
    @ShellMethodAvailability("checkDownload")
    public void download() {
        // Thực hiện tải dữ liệu.
    }

    public Availability checkDownload() {
        return connected
            ? Availability.available()
            : Availability.unavailable("chưa kết nối tới máy chủ");
    }
}
```

Có thể đặt `@ShellMethodAvailability` trên chính phương thức trả về `Availability` để áp dụng cho một hoặc nhiều command. Giá trị mặc định `*` có nghĩa là áp dụng cho mọi command trong lớp legacy đó.

Không trộn các annotation của hai mô hình:

| Mô hình | Cách khai báo |
|---|---|
| Annotation mới trong 3.x | `@Command` + `@CommandAvailability` |
| Programmatic trong 3.x | `CommandRegistration.Builder.availability(...)` |
| Annotation legacy | `@ShellMethod` + `@ShellMethodAvailability` |

Khi nâng cấp từ legacy sang mô hình mới, cần chuyển cả cơ chế đăng ký command và cách khai báo availability. Trong Spring Shell 4.x, cấu hình annotation availability được hợp nhất vào thuộc tính `availabilityProvider` của `@Command`; không sao chép nguyên `@CommandAvailability` của 3.x sang 4.x.

## 11. Các lỗi thường gặp

**Nhầm tên provider với tên phương thức command.** `provider` trong `@CommandAvailability` tham chiếu tên bean `AvailabilityProvider`. Hãy bảo đảm tên bean khớp với giá trị đã khai báo.

**Trả về boolean thay vì Availability.** Provider cần trả về `Availability.available()` hoặc `Availability.unavailable(reason)`, không chỉ trả `true`/`false`.

**Không cung cấp lý do khi unavailable.** `Availability.unavailable(...)` cần một lý do có thể hiển thị cho người dùng. Lý do nên ngắn, rõ và không chứa dữ liệu nhạy cảm.

**Tính trạng thái một lần rồi lưu cố định.** Điều này khiến command không cập nhật khả dụng sau khi ứng dụng thay đổi trạng thái. Hãy đọc trạng thái hiện tại trong provider.

**Đặt tác dụng phụ trong provider.** Provider có thể được gọi nhiều lần. Không dùng nó để kết nối, ghi dữ liệu hoặc thực hiện thao tác nghiệp vụ.

**Dùng availability thay cho phân quyền.** Provider không phải ranh giới bảo mật. Kiểm tra quyền vẫn cần thực hiện ở service hoặc lớp bảo mật.

**Dùng InteractionMode thay cho trạng thái nghiệp vụ.** Chế độ tương tác và trạng thái ứng dụng là hai điều kiện khác nhau.

**Dùng nhầm annotation của phiên bản khác.** Spring Shell 3.x dùng `@CommandAvailability(provider = "...")`; Spring Shell 4.x đưa provider vào thuộc tính `availabilityProvider` của `@Command`. Mô hình legacy dùng `@ShellMethodAvailability`.

## 12. Checklist triển khai

- [ ] Xác định trạng thái ứng dụng quyết định command có thể chạy hay không.
- [ ] Chọn mô hình annotation mới hoặc programmatic builder phù hợp.
- [ ] Với annotation, khai báo `@CommandAvailability(provider = "...")`.
- [ ] Đăng ký bean `AvailabilityProvider` có tên khớp với `provider`.
- [ ] Với builder, dùng `.availability(Supplier<Availability>)`.
- [ ] Trả về `Availability.available()` khi điều kiện đạt.
- [ ] Trả về `Availability.unavailable(reason)` khi điều kiện chưa đạt.
- [ ] Viết lý do ngắn gọn, dễ hiểu và không tiết lộ thông tin nhạy cảm.
- [ ] Đảm bảo provider đọc trạng thái hiện tại, không lưu kết quả cố định.
- [ ] Giữ provider nhanh, không có tác dụng phụ.
- [ ] Phân biệt Availability với `InteractionMode`, `hidden` và authorization.
- [ ] Kiểm tra điều kiện nghiệp vụ lại trong service khi thực thi.
- [ ] Kiểm thử trạng thái trước và sau khi thay đổi.
- [ ] Xác minh trợ giúp và thông báo khi người dùng gọi command chưa khả dụng.
- [ ] Không trộn API 3.x, API legacy và API 4.x.

## 13. Tài liệu tham khảo chính thức

- [Spring Shell 3.3.4 — Command Availability](https://docs.spring.io/spring-shell/reference/3.3/commands/availability.html): cách dùng `@CommandAvailability`, `AvailabilityProvider`, `CommandRegistration.Builder.availability(...)` và legacy availability.
- [Spring Shell 3.3 API — CommandAvailability](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/command/annotation/CommandAvailability.html): annotation liên kết command với provider bean.
- [Spring Shell 3.3 API — CommandRegistration.Builder](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/command/CommandRegistration.Builder.html): phương thức `availability(Supplier<Availability>)`.
- [Spring Shell 3.3 API — Availability](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/Availability.html): trạng thái và lý do không khả dụng.
- [Spring Shell 3.3 API — AvailabilityProvider](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/AvailabilityProvider.html): functional interface cung cấp `Availability`.
- [Spring Shell 3.3 API — CommandScan](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/command/annotation/CommandScan.html) và [EnableCommand](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/command/annotation/EnableCommand.html): đăng ký command target trong mô hình annotation mới.
- [Spring Shell 3.3 — Execution and Interaction Mode](https://docs.spring.io/spring-shell/reference/3.3/execution.html): phân biệt chế độ interactive và non-interactive.
- [Spring Shell v4 Migration Guide](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide): thay đổi từ `@CommandAvailability` sang thuộc tính `availabilityProvider` của `@Command` trong 4.x.

Availability giúp CLI phản ánh trạng thái hiện tại của ứng dụng và giải thích vì sao một command chưa thể chạy. Dùng `@CommandAvailability` khi command được khai báo bằng annotation; dùng `.availability(...)` khi tạo `CommandRegistration` bằng builder. Dù chọn cách nào, hãy để provider chỉ đọc trạng thái, giữ lý do dễ hiểu và bảo vệ quy tắc nghiệp vụ tại service thực thi.


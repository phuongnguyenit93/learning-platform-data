# Thông báo lỗi dễ sửa mà không làm lộ thông tin nhạy cảm

Thông báo lỗi của một ứng dụng dòng lệnh cần giúp người dùng biết điều gì đã xảy ra và cách tiếp tục. Khi nhập sai ngày, người dùng cần biết định dạng được chấp nhận; khi bỏ sót option bắt buộc, họ cần biết tên option; khi thao tác thất bại vì quy tắc nghiệp vụ, họ cần hiểu điều kiện nào chưa được đáp ứng. Một thông báo hữu ích chỉ cung cấp thông tin cần thiết để sửa lỗi.

Thông báo lỗi cũng là một phần của ranh giới bảo mật. Giá trị người dùng nhập có thể chứa mật khẩu, token, mã truy cập, thông tin cá nhân, đường dẫn nội bộ hoặc dữ liệu nghiệp vụ. Nếu in lại toàn bộ đầu vào, nội dung exception hoặc stack trace ra terminal, ứng dụng có thể làm lộ dữ liệu cho người đứng cạnh màn hình, log tập trung, lịch sử terminal hoặc hệ thống CI.

Spring Shell tích hợp Jakarta Bean Validation để kiểm tra tham số command trước khi gọi phương thức xử lý. Framework có thể hiển thị option vi phạm cùng thông điệp constraint; ứng dụng có thể tùy chỉnh nội dung bằng thuộc tính `message` và message bundle. Với lỗi nghiệp vụ phát sinh trong lúc thực thi, Spring Shell 4.x cung cấp `ExitStatusExceptionMapper` để ánh xạ exception thành trạng thái command và thông báo phù hợp.

## Một thông báo lỗi tốt cần nói điều gì?

Thông báo nên cung cấp đủ ba thông tin:

1. **Vị trí:** trường, option hoặc thao tác nào có vấn đề.
2. **Nguyên nhân có thể sửa:** giá trị đang vi phạm điều kiện nào, diễn đạt bằng ngôn ngữ người dùng hiểu.
3. **Cách khắc phục:** định dạng, khoảng giá trị hoặc hành động tiếp theo được chấp nhận.

Ví dụ:

| Thông báo kém hữu ích | Thông báo dễ sửa hơn |
| --- | --- |
| `Invalid input` | `--date: dùng định dạng yyyy-MM-dd, ví dụ 2026-11-26.` |
| `Error: size` | `--name: nhập tên dài từ 2 đến 80 ký tự.` |
| `Missing argument` | `Thiếu --customer-code. Hãy truyền mã khách hàng, ví dụ --customer-code CUS-123456.` |
| `Operation failed` | `Không thể hủy đơn hàng ở trạng thái hiện tại. Hãy kiểm tra trạng thái đơn hàng rồi thử lại.` |
| `Authentication exception` | `Không thể xác thực bằng thông tin đã cung cấp. Hãy kiểm tra lại thông tin đăng nhập.` |

Thông báo cần cụ thể vừa đủ. Không cần giải thích cấu trúc lớp Java, tên bảng cơ sở dữ liệu hoặc thuật toán nội bộ. Với lỗi có nhiều nguyên nhân, hãy nói điều người dùng có thể kiểm tra tiếp theo thay vì đoán một nguyên nhân chưa được xác nhận.

## Phân biệt lỗi đầu vào và lỗi thực thi

Không phải mọi lỗi đều nên có cùng một cách hiển thị. Xác định lỗi phát sinh ở giai đoạn nào sẽ giúp chọn thông báo phù hợp.

| Loại lỗi | Ví dụ | Thông tin nên hiển thị |
| --- | --- | --- |
| Thiếu hoặc sai cú pháp | Thiếu `--customer-code`, viết sai tên option | Tên option hoặc cú pháp đúng; gợi ý dùng `help` khi cần |
| Chuyển đổi kiểu | `--limit many` trong khi cần số nguyên | Tên option, kiểu dữ liệu mong đợi và ví dụ hợp lệ |
| Bean Validation | Tên rỗng, ghi chú quá dài, mật khẩu không đủ độ dài | Tên option và constraint đã diễn đạt thành câu dễ hiểu |
| Quy tắc nghiệp vụ | Không thể hủy đơn đã giao | Điều kiện nghiệp vụ chưa đáp ứng và hành động tiếp theo |
| Xác thực hoặc phân quyền | Thông tin đăng nhập sai, người dùng không được phép thao tác | Phản hồi an toàn, không tiết lộ dữ liệu tài khoản hoặc quyền nội bộ |
| Hạ tầng hoặc lỗi bất ngờ | Không kết nối được cơ sở dữ liệu, lỗi lập trình | Thông báo tổng quát, mã tham chiếu nếu có; chi tiết kỹ thuật nằm trong log được bảo vệ |

Ví dụ, chuỗi `abc` không chuyển được thành số nguyên là lỗi chuyển đổi. Số `-5` có thể chuyển đổi thành công nhưng vi phạm constraint số lượng dương. Số `5` có thể hợp lệ ở đầu vào nhưng thao tác vẫn thất bại vì kho chỉ còn hai sản phẩm. Không nên hiển thị cả ba trường hợp bằng một thông báo chung như `Invalid value`.

## Tùy chỉnh thông báo Bean Validation

Spring Shell kiểm tra các constraint trên tham số command trước khi phương thức command thực thi. Trong Spring Shell 4.x, ví dụ lỗi validation mặc định hiển thị tên option và thông điệp constraint, đồng thời trả trạng thái `USAGE_ERROR`.

Ví dụ:

```java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
public class CustomerCommands {

    private final CustomerService customerService;

    public CustomerCommands(CustomerService customerService) {
        this.customerService = customerService;
    }

    @Command(name = "customer register", description = "Đăng ký khách hàng")
    public String register(
            @Option(longName = "name", required = true)
            @NotBlank(message = "Vui lòng nhập tên khách hàng.")
            @Size(min = 2, max = 80,
                    message = "Tên khách hàng phải dài từ {min} đến {max} ký tự.")
            String name) {

        customerService.register(name);
        return "Đã đăng ký khách hàng.";
    }
}
```

Khi tên không hợp lệ, người dùng nhận được thông tin gắn với `--name` và thông điệp đã định nghĩa. Phương thức `register(...)` không được gọi cho đến khi tham số vượt qua validation.

Thuộc tính `message` phù hợp với một thông điệp ngắn, dùng một lần. Khi nhiều command cần cùng một quy tắc hoặc ứng dụng hỗ trợ nhiều ngôn ngữ, hãy chuyển thông điệp sang message bundle để tránh lặp nội dung trong mã nguồn.

### Dùng message key

Thay vì ghi câu trực tiếp trong annotation, có thể dùng message key:

```java
@NotBlank(message = "{customer.name.required}")
@Size(min = 2, max = 80, message = "{customer.name.size}")
String name
```

Trong Spring Boot, `MessageSource` của ứng dụng được sử dụng khi phân giải các key trong thông điệp constraint. Ví dụ file `messages.properties`:

```properties
customer.name.required=Vui lòng nhập tên khách hàng.
customer.name.size=Tên khách hàng phải dài từ {min} đến {max} ký tự.
customer.code.required=Vui lòng nhập mã khách hàng.
customer.code.format=Mã khách hàng phải có dạng CUS-123456.
```

Nếu ứng dụng có nhiều ngôn ngữ, có thể cung cấp các file như `messages_vi.properties` và `messages_en.properties`. Spring Boot chọn message bundle theo locale được cấu hình. Các placeholder constraint như `{min}` và `{max}` được Bean Validation nội suy từ thuộc tính của annotation.

Message key nên mô tả trường và điều kiện, ví dụ `customer.name.size`, thay vì dùng một key quá chung như `invalid.input`. Key rõ ràng giúp nhóm phát triển thay đổi câu chữ hoặc dịch nội dung mà không phải sửa logic command.

## Trình bày lỗi mà không echo giá trị đầu vào

Không đưa giá trị người dùng nhập vào thông báo lỗi trừ khi có lý do rõ ràng và giá trị đó đã được xác định là an toàn. Với dữ liệu nhạy cảm, không bao giờ in lại giá trị gốc.

Các loại dữ liệu cần tránh echo gồm:

- Mật khẩu, mã PIN, mã xác thực một lần, access token, refresh token và API key.
- Số thẻ, thông tin thanh toán, mã định danh cá nhân hoặc dữ liệu khách hàng nhạy cảm.
- Nội dung file có thể chứa bí mật, chuỗi kết nối, header xác thực hoặc payload.
- Đường dẫn tuyệt đối, tên máy chủ, tên schema/bảng hoặc chi tiết hạ tầng nội bộ khi không cần thiết.
- Truy vấn, câu lệnh SQL, header HTTP hoặc thông tin cấu hình có thể tiết lộ cấu trúc hệ thống.

Ví dụ, thông báo này không an toàn:

```text
Mật khẩu 'P@ssw0rd-123' không đạt độ dài tối thiểu.
```

Thông báo phù hợp hơn:

```text
--password: mật khẩu phải có từ 12 đến 64 ký tự.
```

Thông báo thứ hai nói rõ điều kiện cần sửa mà không hiển thị giá trị mật khẩu. Tương tự, với mã xác thực sai, chỉ cần báo `Mã xác thực không hợp lệ hoặc đã hết hạn.` thay vì in lại mã người dùng đã nhập.

### Chú ý khác biệt giữa phiên bản Spring Shell

Hãy kiểm tra output thực tế của phiên bản đang triển khai. Tài liệu Spring Shell 4.0.4 minh họa lỗi validation chỉ hiển thị option và constraint message, không in lại giá trị mật khẩu. Tài liệu Spring Shell 3.4.1 có ví dụ hiển thị thêm giá trị bị từ chối trong ngoặc. Điều này có nghĩa ứng dụng nâng cấp từ 3.x cần kiểm tra lại hành vi hiển thị và không giả định mọi phiên bản đều tự che dữ liệu.

Ngay cả khi phiên bản hiện tại không echo giá trị, vẫn cần giữ thông điệp tùy chỉnh an toàn. Không viết custom validator hoặc exception message bằng cách nối trực tiếp giá trị đầu vào vào chuỗi lỗi.

Ngoài output lỗi, việc truyền bí mật dưới dạng command-line argument có thể để lại dấu vết trong lịch sử terminal hoặc danh sách tham số tiến trình tùy môi trường. Với mật khẩu và token, nên dùng luồng nhập được che ký tự, secret store hoặc cơ chế cấp thông tin xác thực phù hợp thay vì yêu cầu người dùng gõ bí mật trực tiếp trong dòng lệnh.

## Ví dụ: command đổi mật khẩu an toàn

Ví dụ dưới đây kiểm tra độ dài nhưng không trả mật khẩu về terminal:

```java
import jakarta.validation.constraints.Size;

import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
public class AccountCommands {

    private final AccountService accountService;

    public AccountCommands(AccountService accountService) {
        this.accountService = accountService;
    }

    @Command(name = "account change-password", description = "Đổi mật khẩu")
    public String changePassword(
            @Option(longName = "password", required = true)
            @Size(min = 12, max = 64,
                    message = "Mật khẩu phải có từ {min} đến {max} ký tự.")
            String password) {

        accountService.changePassword(password);
        return "Đã cập nhật mật khẩu.";
    }
}
```

Không trả về `password`, không ghi nó vào log và không đưa nó vào thông báo lỗi. Trong sản phẩm thực tế, hãy cân nhắc nhận bí mật qua một phương thức nhập được che ký tự. Ví dụ trên chỉ tập trung minh họa cách thông báo validation không chứa giá trị nhạy cảm.

## Thông báo lỗi nghiệp vụ và `ExitStatusExceptionMapper`

Validation từ chối dữ liệu trước khi command method chạy. Lỗi nghiệp vụ thường phát sinh trong lúc command gọi application service, chẳng hạn tài khoản không tồn tại hoặc thao tác bị từ chối. Spring Shell 4.x cung cấp `ExitStatusExceptionMapper` để ánh xạ exception thành `ExitStatus`, bao gồm mã trạng thái của command và mô tả có thể hiển thị.

Ví dụ tạo mapper:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.core.command.ExitStatus;
import org.springframework.shell.core.command.exit.ExitStatusExceptionMapper;

@Configuration
public class CommandErrorConfiguration {

    @Bean
    ExitStatusExceptionMapper accountErrorMapper() {
        return exception -> {
            if (exception instanceof AccountNotFoundException) {
                return new ExitStatus(4, "Không tìm thấy tài khoản.");
            }
            if (exception instanceof DuplicateAccountException) {
                return new ExitStatus(3, "Tài khoản đã tồn tại.");
            }
            return new ExitStatus(1,
                    "Không thể hoàn thành thao tác. Vui lòng thử lại hoặc liên hệ hỗ trợ.");
        };
    }
}
```

Gắn mapper vào command bằng tên bean:

```java
@Command(
        name = "account create",
        description = "Tạo tài khoản",
        exitStatusExceptionMapper = "accountErrorMapper")
public String create(@Option(longName = "email", required = true) String email) {
    accountService.create(email);
    return "Đã tạo tài khoản.";
}
```

Mapper chỉ hiển thị những thông tin đã được chọn lọc. Không dùng `exception.getMessage()` làm thông báo cho người dùng một cách vô điều kiện, vì exception có thể chứa SQL, đường dẫn nội bộ, giá trị đầu vào hoặc chi tiết hạ tầng. Hãy phân loại exception đã biết và ánh xạ chúng sang câu thông báo ổn định.

Với exception không dự kiến, thông báo chung giúp người dùng biết thao tác thất bại mà không tiết lộ chi tiết triển khai. Chi tiết chẩn đoán nên được ghi ở log được bảo vệ, có mã tham chiếu để đội vận hành tra cứu.

`ExitStatusExceptionMapper` xử lý exception phát sinh trong quá trình thực thi command. Lỗi validation tham số có thể được xử lý bởi result handler validation của Spring Shell trước khi method chạy; không nên giả định mapper này thay thế mọi thông báo lỗi parser hoặc validation.

Trong Spring Shell 3.x, cơ chế ánh xạ exception dùng API legacy `CommandExceptionResolver` và `CommandHandlingResult`. Không sao chép ví dụ `ExitStatusExceptionMapper` của 4.x vào dự án 3.x; hãy dùng API tương ứng với phiên bản hoặc thực hiện migration theo hướng dẫn chính thức.

Lưu ý rằng `ExitStatus` mô tả trạng thái của command. Nó khác với mã thoát của tiến trình JVM. Cấu hình mapper không tự động quyết định mã thoát cuối cùng của tiến trình trong mọi chế độ chạy; nếu CLI được gọi từ script, hãy kiểm thử cả command status lẫn process exit code theo runner và cấu hình ứng dụng.

## Tách thông báo cho người dùng khỏi log kỹ thuật

Terminal và log phục vụ hai đối tượng khác nhau:

| Kênh | Mục tiêu | Nội dung phù hợp |
| --- | --- | --- |
| Terminal | Giúp người dùng sửa lỗi hoặc quyết định bước tiếp theo | Tên option, điều kiện hợp lệ, hướng xử lý, mã tham chiếu |
| Log ứng dụng | Giúp đội phát triển/vận hành điều tra | Loại exception, error code, correlation ID, stack trace đã được kiểm soát |
| Script/CI | Cho tiến trình gọi biết kết quả | Mã thoát ổn định và thông báo ngắn, có thể xử lý |

Không nên ghi cùng một chuỗi chi tiết cho mọi kênh. Thông báo terminal không cần stack trace. Log cũng không nên lưu mật khẩu, token hoặc toàn bộ command line nếu nó có thể chứa bí mật.

Ví dụ log an toàn hơn:

```java
log.warn("Account command rejected: code={}, referenceId={}",
        "ACCOUNT_NOT_FOUND", referenceId);
```

Với lỗi bất ngờ, có thể cần stack trace để chẩn đoán. Trước khi log toàn bộ exception, hãy bảo đảm exception message và dữ liệu đính kèm không chứa bí mật hoặc thông tin cá nhân. Nếu không thể bảo đảm, ghi loại lỗi, mã lỗi và reference ID; giữ chi tiết nhạy cảm trong hệ thống chẩn đoán có quyền truy cập được kiểm soát.

Tránh các mẫu sau:

```java
// Không an toàn: có thể ghi lộ token hoặc dữ liệu người dùng.
log.error("Command failed with input " + token, exception);

// Không an toàn: exception message có thể chứa SQL hoặc dữ liệu nhạy cảm.
return "Lỗi: " + exception.getMessage();
```

## Tránh tiết lộ thông tin qua khác biệt thông báo

Trong một số luồng xác thực hoặc tra cứu nhạy cảm, nội dung thông báo khác nhau có thể tiết lộ tài khoản hay dữ liệu có tồn tại hay không.

Ví dụ, màn hình đăng nhập không nên phản hồi:

```text
Không tìm thấy email này trong hệ thống.
```

cho một tài khoản không tồn tại và:

```text
Mật khẩu của tài khoản này không đúng.
```

cho một tài khoản có tồn tại. Hai thông báo giúp kẻ dò tìm xác định email hợp lệ. Dùng một phản hồi chung:

```text
Không thể đăng nhập bằng thông tin đã cung cấp.
```

Tương tự, khi một người dùng không có quyền truy cập tài nguyên, cân nhắc thông báo chung nếu việc xác nhận tài nguyên tồn tại cũng là thông tin nhạy cảm. Lựa chọn thông báo cần dựa vào mô hình đe dọa và yêu cầu vận hành của ứng dụng.

## Kiểm thử thông báo lỗi và bảo mật

Không chỉ kiểm tra rằng command trả về lỗi. Hãy kiểm tra nội dung output để chắc chắn thông báo hữu ích và không chứa dữ liệu nhạy cảm.

| Trường hợp | Điều cần xác minh |
| --- | --- |
| Thiếu option bắt buộc | Nêu tên option và cách gọi đúng |
| Sai định dạng | Nêu định dạng mong đợi và ví dụ hợp lệ |
| Vi phạm `@Size` | Nêu giới hạn min/max mà không echo giá trị gốc |
| Mật khẩu sai constraint | Không có mật khẩu trong output, log hoặc thông báo thành công |
| Token không hợp lệ | Không in token hoặc một phần token ra terminal |
| Tài khoản không tồn tại | Thông báo không tiết lộ thông tin ngoài chính sách cho phép |
| Exception nghiệp vụ đã biết | Mapper trả thông báo ổn định và mã trạng thái phù hợp |
| Exception bất ngờ | Terminal không hiển thị stack trace/SQL/đường dẫn nội bộ |
| Chạy bằng script | Mã thoát được kiểm tra cùng thông báo lỗi |
| Nâng cấp phiên bản Spring Shell | Kiểm tra lại output validation mặc định và hành vi echo giá trị |

Một kiểm thử bảo mật nên đưa chuỗi đánh dấu dễ tìm vào đầu vào, ví dụ `SECRET-DO-NOT-PRINT`, sau đó xác nhận chuỗi đó không xuất hiện trong output và log được thu thập. Với token hoặc mật khẩu thực, không dùng dữ liệu production trong kiểm thử.

## Những lỗi thường gặp

| Cách làm | Rủi ro | Cách điều chỉnh |
| --- | --- | --- |
| Nối giá trị đầu vào vào message validation | Có thể làm lộ mật khẩu, token hoặc PII | Chỉ nêu tên option và constraint |
| Hiển thị `exception.getMessage()` cho mọi lỗi | Exception có thể chứa SQL, đường dẫn hoặc chi tiết nội bộ | Ánh xạ exception đã biết sang thông báo an toàn |
| In stack trace ra terminal | Người dùng thấy chi tiết triển khai không cần thiết | Đưa chẩn đoán vào log được bảo vệ |
| Dùng một thông báo `Invalid input` cho mọi lỗi | Người dùng không biết cách sửa | Nêu trường, điều kiện và cách khắc phục |
| Dùng message key chung cho mọi trường | Khó hiểu và khó dịch chính xác | Đặt key theo trường và constraint |
| Cho rằng Spring Shell luôn che giá trị đầu vào | Hành vi có thể khác giữa các phiên bản | Kiểm thử output đúng phiên bản triển khai |
| Chỉ log toàn bộ command để tiện điều tra | Command có thể chứa bí mật trong option | Lọc hoặc loại bỏ option nhạy cảm trước khi log |
| Trả thông báo khác nhau cho tài khoản tồn tại và không tồn tại | Có thể hỗ trợ dò tìm tài khoản | Dùng phản hồi chung trong luồng nhạy cảm |
| Chỉ kiểm tra nội dung terminal | Bí mật vẫn có thể bị ghi vào log hoặc lịch sử shell | Kiểm thử tất cả kênh có thể lưu dữ liệu |

## Quy trình thiết kế thông báo lỗi

1. Phân loại lỗi: cú pháp, chuyển đổi, validation, nghiệp vụ, xác thực hay hạ tầng.
2. Xác định thông tin tối thiểu người dùng cần để sửa lỗi.
3. Viết message ngắn, gắn với option hoặc thao tác và nêu điều kiện hợp lệ.
4. Kiểm tra thông báo không echo mật khẩu, token, PII hoặc dữ liệu nội bộ.
5. Dùng `message` hoặc message bundle cho Bean Validation; dùng `ExitStatusExceptionMapper` cho exception thực thi đã biết.
6. Đưa chi tiết chẩn đoán sang log có kiểm soát và liên kết bằng mã tham chiếu.
7. Kiểm thử output, log, command status và process exit code trên đúng phiên bản Spring Shell.

Thông báo lỗi tốt giúp người dùng tự sửa được vấn đề mà không cần biết chi tiết triển khai. Khi tách thông tin dành cho terminal khỏi dữ liệu chẩn đoán nội bộ, ứng dụng Spring Shell vừa dễ vận hành vừa giảm nguy cơ làm lộ thông tin nhạy cảm qua output, exception và log.

## Tài liệu tham khảo

- [Option Validation – Spring Shell 4.0.4](https://docs.spring.io/spring-shell/reference/commands/validation.html)
- [Option Validation – Spring Shell 3.4.x](https://docs.spring.io/spring-shell/reference/options/validation.html)
- [Exception Handling – Spring Shell 4.0.4](https://docs.spring.io/spring-shell/reference/commands/exception-handling.html)
- [Validation – Spring Boot 4.2](https://docs.spring.io/spring-boot/reference/io/validation.html)
- [Java Bean Validation – Spring Framework 7](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [ExitStatus – Spring Shell 4.0.3 API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/ExitStatus.html)
- [ExitStatusExceptionMapper – Spring Shell 4.0.3 API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/exit/ExitStatusExceptionMapper.html)

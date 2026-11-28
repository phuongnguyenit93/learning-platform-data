# Quyền chạy tiến trình khác với quyền thực hiện nghiệp vụ

Một ứng dụng Spring Shell chạy bên trong một tiến trình Java của hệ điều hành. Người dùng có thể gọi nhiều command trong cùng tiến trình đó: đọc file, xuất báo cáo, tạo đơn hàng, hoàn tiền hoặc khởi chạy một chương trình bên ngoài. Các command này cùng chạy dưới danh tính và quyền hệ điều hành của tiến trình Java, trừ khi ứng dụng chủ động dùng một cơ chế đặc biệt để thực hiện thao tác bằng danh tính khác.

Quyền của tiến trình trả lời câu hỏi: **JVM được phép truy cập tài nguyên hệ điều hành nào?** Ví dụ, tiến trình có thể đọc một file, ghi vào thư mục, mở socket hoặc khởi chạy một executable hay không. Quyền nghiệp vụ trả lời câu hỏi khác: **người đang sử dụng ứng dụng được phép thực hiện hành động nào trên dữ liệu nào?** Ví dụ, người đó có quyền hoàn tiền cho đơn hàng này, xem dữ liệu của tenant này hoặc xuất báo cáo lương hay không.

Hai lớp quyền cần được kiểm tra độc lập. Một tiến trình có thể được hệ điều hành cho phép kết nối database, nhưng người dùng hiện tại vẫn không có quyền hoàn tiền. Ngược lại, người dùng có quyền xem báo cáo theo nghiệp vụ nhưng JVM vẫn không thể ghi file vào thư mục đích vì tài khoản hệ điều hành không có quyền ghi.

Bài này giúp bạn:

- Phân biệt danh tính và quyền của tiến trình với danh tính và quyền của người dùng ứng dụng.
- Hiểu vì sao các command trong cùng JVM thường dùng chung quyền hệ điều hành.
- Dùng Spring Security Method Security để kiểm tra quyền ở service nghiệp vụ.
- Phân biệt command availability với authorization.
- Kiểm tra quyền trên từng tài nguyên và từng bản ghi, không chỉ kiểm tra role chung.
- Khởi chạy tiến trình con bằng `ProcessBuilder` theo danh sách executable được cho phép.
- Giảm quyền, giới hạn môi trường và ghi audit log.
- Kiểm thử cả quyền hệ điều hành và quyền nghiệp vụ.

> Nội dung dùng Spring Shell 3.3.x, Spring Security 6.x và Java 21 làm mốc ví dụ. Ứng dụng CLI cục bộ không tự động có cơ chế đăng nhập nghiệp vụ chỉ vì nó chạy dưới một tài khoản Windows hoặc Unix.

## 1. Hai lớp quyền giải quyết hai câu hỏi khác nhau

Hãy xét command `report export --month 2026-10`. Để xuất báo cáo, ứng dụng cần đọc dữ liệu từ database và ghi file vào thư mục đích. Hệ điều hành kiểm tra quyền truy cập database socket, file cấu hình, thư mục và file đầu ra theo danh tính tiến trình. Ứng dụng còn phải kiểm tra người dùng hiện tại có được phép xem báo cáo của bộ phận hoặc tenant đó hay không.

| Lớp quyền | Danh tính được xét | Tài nguyên hoặc hành động | Ví dụ |
|---|---|---|---|
| Quyền hệ điều hành | Tài khoản chạy JVM | File, thư mục, socket, thiết bị, executable, process | Tài khoản `spring-shell` được ghi vào `/var/app/exports` |
| Quyền nghiệp vụ | Người dùng đã xác thực trong ứng dụng | Command nghiệp vụ, dữ liệu, tenant, bản ghi, hạn mức | Người dùng có authority `REPORT_EXPORT` cho tenant hiện tại |
| Xác thực (authentication) | Người hoặc service đang gọi | Danh tính đã được chứng minh | Đăng nhập thành công bằng tài khoản ứng dụng |
| Phân quyền (authorization) | Danh tính đã xác thực và thuộc tính liên quan | Hành động cụ thể trên tài nguyên cụ thể | Người dùng được hoàn tiền đơn hàng do mình quản lý |

Xác thực trả lời “bạn là ai?”. Phân quyền trả lời “bạn được phép làm gì?”. Quyền hệ điều hành là một lớp kiểm soát khác, do hệ điều hành áp dụng với tiến trình.

~~~mermaid
flowchart TD
    A[Người dùng gọi Spring Shell command] --> B{Đã xác thực trong ứng dụng?}
    B -->|Chưa| C[Từ chối / yêu cầu đăng nhập]
    B -->|Rồi| D[Command gọi service bean]
    D --> E{Có quyền nghiệp vụ?}
    E -->|Không| F[AccessDeniedException]
    E -->|Có| G[Service thực hiện nghiệp vụ]
    G --> H{OS cho phép truy cập tài nguyên?}
    H -->|Không| I[IOException / Access denied]
    H -->|Có| J[Hoàn tất và ghi audit]
~~~

Trong thực tế, một thao tác có thể kiểm tra quyền hệ điều hành trước hoặc sau một số bước nghiệp vụ. Điều quan trọng là không xem một lớp kiểm soát là bằng chứng thay cho lớp còn lại.

## 2. Các command trong cùng JVM dùng chung danh tính tiến trình

Spring Shell 3.x đăng ký command từ các Spring bean, ví dụ class có `@ShellComponent` và method có `@ShellMethod`. Khi người dùng gọi command, Spring Shell gọi method trong cùng tiến trình JVM. Việc command có tên `admin`, `backup` hay `orders refund` không làm thay đổi tài khoản hệ điều hành đang chạy JVM.

Ví dụ:

~~~java
@ShellComponent
public class FileCommands {

    @ShellMethod(key = "file read", value = "Đọc một file.")
    public String read(@ShellOption("--path") String path) throws IOException {
        return Files.readString(Path.of(path));
    }

    @ShellMethod(key = "file write", value = "Ghi một file.")
    public String write(
            @ShellOption("--path") String path,
            @ShellOption("--content") String content) throws IOException {
        Files.writeString(Path.of(path), content);
        return "Đã ghi file.";
    }
}
~~~

Hai command trên đều thực thi dưới danh tính hệ điều hành của tiến trình Spring Shell. Nếu JVM chạy bằng tài khoản có quyền ghi vào thư mục hệ thống, cả hai method đều có thể sử dụng quyền đó khi code cho phép. Hệ điều hành không tự hiểu rằng `file write` là thao tác cần quyền quản trị nghiệp vụ.

Đoạn code chỉ minh họa danh tính tiến trình dùng chung; không nên đưa một command ghi file tùy ý theo đường dẫn người dùng nhập vào môi trường production. Command thực tế cần giới hạn thư mục được phép, kiểm tra đường dẫn sau khi chuẩn hóa và xử lý liên kết symbolic link theo chính sách của ứng dụng. Kiểm tra chuỗi bằng `Path.normalize()` đơn thuần không loại bỏ mọi rủi ro do symlink hoặc thay đổi đường dẫn giữa lúc kiểm tra và lúc mở file.

Nếu chạy toàn bộ ứng dụng bằng Administrator hoặc `root` để giải quyết một lỗi ghi file, tất cả code trong JVM có thể được hưởng quyền rộng hơn cần thiết. Một lỗi trong parser, command, thư viện hoặc plugin khi đó có thể gây hậu quả lớn hơn.

### Quyền hệ điều hành được áp dụng ở đâu?

Tùy hệ điều hành và cách triển khai, tiến trình thường chịu ảnh hưởng bởi:

- UID/GID và permission bits trên Unix-like, ACL trên Windows.
- Quyền đọc, ghi, thực thi file và truy cập thư mục.
- Quyền kết nối socket, port, pipe hoặc thiết bị.
- Token, group, capability và chính sách sandbox của tiến trình.
- Chính sách kiểm soát ứng dụng, container hoặc môi trường triển khai.

Các quyền này thuộc về tiến trình và tài nguyên hệ điều hành. Chúng không tự biểu diễn role như `ORDER_REFUND` hoặc phạm vi dữ liệu như `tenant-42`.

## 3. Vì sao không nên dùng quyền Administrator/root để thay thế phân quyền?

Giả sử một command cần ghi file export vào `/srv/reports`. Tài khoản chạy JVM hiện không có quyền ghi. Chạy cả ứng dụng bằng `root` có thể làm lỗi biến mất, nhưng cũng trao cho toàn bộ ứng dụng quyền đọc/ghi nhiều tài nguyên hệ thống khác.

Hãy xác định tài nguyên cụ thể cần truy cập rồi cấp quyền hẹp:

- Tạo thư mục export riêng và cấp quyền ghi cho tài khoản dịch vụ chạy CLI.
- Chỉ cấp quyền đọc cho thư mục cấu hình cần thiết.
- Dùng tài khoản database có quyền tối thiểu trên schema/bảng mà ứng dụng cần.
- Dùng container, sandbox hoặc policy hệ điều hành để giới hạn filesystem và network.
- Tách thao tác cần quyền cao sang một service/helper chuyên biệt với giao diện nhỏ và kiểm tra riêng.

Nếu một thao tác thật sự cần quyền cao, hãy xác định chính xác thao tác đó, người được phép yêu cầu và tài nguyên có thể bị tác động. Không mở một shell quản trị tổng quát rồi cho phép người dùng truyền chuỗi lệnh tùy ý.

## 4. Spring Shell availability không phải authorization

Spring Shell có cơ chế command availability để biểu thị command hiện có dùng được trong trạng thái ứng dụng hay không. Ví dụ, command `download` chỉ khả dụng sau khi người dùng đã kết nối tới máy chủ; shell có thể báo command tồn tại nhưng hiện chưa khả dụng và giải thích lý do. Với annotation legacy, `@ShellMethodAvailability` liên kết command với một phương thức trả về `Availability`.

Availability giúp giao diện giải thích vì sao command chưa dùng được. Nó có thể phản ánh trạng thái kết nối, cấu hình đã nạp hoặc điều kiện trước khi thao tác. Tuy nhiên, không nên dùng availability làm ranh giới bảo mật:

- Nó chủ yếu báo trạng thái khả dụng và lý do cho người dùng shell.
- Nó không thay thế kiểm tra quyền tại service mà các caller khác có thể gọi.
- Trạng thái availability có thể thay đổi giữa lúc hiển thị và lúc thực thi.
- Ẩn một command không ngăn code khác gọi trực tiếp service nghiệp vụ.

Ví dụ: có thể đánh dấu `orders refund` là unavailable khi người dùng không có authority hoàn tiền để giao diện dễ dùng. Nhưng service vẫn phải kiểm tra authority và quyền trên đơn hàng mỗi khi method được gọi.

## 5. Thiết lập phân quyền nghiệp vụ ở service

Spring Security hỗ trợ Method Security để bảo vệ lời gọi method trên Spring-managed bean. Với Spring Security 6, bật cơ chế này bằng `@EnableMethodSecurity` trong một class cấu hình:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
~~~

Sau khi bật, có thể dùng `@PreAuthorize` để kiểm tra quyền trước khi method chạy:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {

    private final OrderRepository orderRepository;
    private final OrderAuthorization orderAuthorization;

    public OrderService(
            OrderRepository orderRepository,
            OrderAuthorization orderAuthorization) {
        this.orderRepository = orderRepository;
        this.orderAuthorization = orderAuthorization;
    }

    @PreAuthorize("hasAuthority('ORDER_REFUND')")
    @Transactional
    public void refund(long orderId) {
        Order order = orderRepository.findById(orderId)
                .orElseThrow(() -> new OrderNotFoundException(orderId));

        orderAuthorization.assertCanRefund(order);
        order.refund();
        orderRepository.save(order);
    }
}
~~~

`@PreAuthorize` kiểm tra authority trước khi gọi method. Trong method, `orderAuthorization.assertCanRefund(order)` kiểm tra thêm điều kiện theo tài nguyên, chẳng hạn đơn hàng có thuộc tenant của người dùng hay không, đã thanh toán chưa hoặc đã hoàn tiền chưa. Kiểm tra role chung không thay thế kiểm tra quyền trên từng bản ghi.

Command gọi service qua bean được inject:

~~~java
@ShellComponent
public class OrderCommands {

    private final OrderService orderService;

    public OrderCommands(OrderService orderService) {
        this.orderService = orderService;
    }

    @ShellMethod(key = "orders refund", value = "Hoàn tiền đơn hàng.")
    public String refund(@ShellOption("--id") long orderId) {
        orderService.refund(orderId);
        return "Đã gửi yêu cầu hoàn tiền cho đơn hàng " + orderId + ".";
    }
}
~~~

Spring inject bean `OrderService` từ application context. Khi Method Security tạo proxy cho bean, lời gọi từ command đi qua interceptor và quyền được kiểm tra trước khi logic hoàn tiền chạy.

### Cấu hình Spring Security không tự tạo danh tính người dùng cho CLI

Thêm dependency Spring Security hoặc bật `@EnableMethodSecurity` không tự xác định người đang ngồi trước terminal. Spring Boot Security starter cũng không tự bật method-level authorization. Ứng dụng cần một cơ chế xác thực phù hợp, ví dụ đăng nhập bằng tài khoản ứng dụng, token do identity provider cấp hoặc credential provider được quản lý.

Trong một CLI cục bộ, tài khoản hệ điều hành đang chạy JVM không tự động trở thành `Authentication` có authority nghiệp vụ trong Spring Security. Nếu ứng dụng không thiết lập authentication, method security có thể từ chối lời gọi yêu cầu quyền. Không lấy role từ option như `--role ADMIN`, biến môi trường do người dùng kiểm soát hoặc một chuỗi username tự khai báo rồi coi đó là danh tính đã xác thực.

Khi đã xác thực, Spring Security lưu thông tin caller trong `SecurityContext`. Có thể đọc principal hiện tại để ghi audit hoặc áp dụng quy tắc nghiệp vụ:

~~~java
Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();

String username = authentication.getName();
~~~

Với CLI có nhiều lần đăng nhập/đăng xuất trong cùng tiến trình, phải thiết lập và xóa `SecurityContext` đúng vòng đời phiên. Nếu một tác vụ chạy trên thread khác, không giả định context sẽ tự truyền sang thread đó; dùng cơ chế truyền context có kiểm soát hoặc xác thực lại theo thiết kế.

## 6. Bảo vệ từng tài nguyên và từng bản ghi

Authority như `ORDER_REFUND` chỉ trả lời người dùng có loại quyền nào. Nó chưa trả lời người đó được hoàn tiền đơn hàng cụ thể nào. Các quy tắc cần kiểm tra có thể gồm:

- Đơn hàng thuộc tenant hoặc tổ chức mà người dùng được phép truy cập.
- Người dùng có quan hệ phù hợp với khách hàng hoặc đơn hàng.
- Trạng thái hiện tại cho phép thực hiện hành động.
- Giá trị giao dịch nằm trong hạn mức được cấp.
- Thao tác cần phê duyệt bổ sung hoặc xác nhận của người thứ hai.

Ví dụ, người dùng có `ORDER_REFUND` nhưng chỉ được hoàn tiền đơn hàng trong tenant của họ. Service nên tải đơn hàng và xác minh phạm vi dữ liệu ở phía server/service, không tin `tenantId` do người dùng truyền lên.

~~~java
public void assertCanRefund(Order order) {
    String currentTenant = currentUser.tenantId();

    if (!order.getTenantId().equals(currentTenant)) {
        throw new AccessDeniedException(
                "Bạn không có quyền thao tác trên đơn hàng này.");
    }

    if (!order.isRefundable()) {
        throw new OrderStateException(
                "Đơn hàng hiện không ở trạng thái có thể hoàn tiền.");
    }
}
~~~

Phân biệt lỗi không có quyền với lỗi trạng thái nghiệp vụ. Người dùng có thể có quyền hoàn tiền nhưng đơn hàng đã hoàn tiền trước đó; đây là trạng thái không hợp lệ cho hành động hiện tại, không nhất thiết là thiếu authority.

## 7. Khởi chạy tiến trình con bằng ProcessBuilder

Một command có thể cần gọi chương trình hệ điều hành, ví dụ công cụ sao lưu, nén file hoặc tiện ích quản trị. `ProcessBuilder` nhận executable và từng argument dưới dạng các phần tử riêng, rồi gọi `start()` để yêu cầu hệ điều hành tạo tiến trình con.

~~~java
import java.io.IOException;
import java.nio.file.Path;
import java.util.concurrent.TimeUnit;

public int runBackup(
        String databaseName,
        Path workingDirectory,
        Path outputFile,
        Path errorFile) throws IOException, InterruptedException {

    validateDatabaseName(databaseName);

    ProcessBuilder builder = new ProcessBuilder(
            "/usr/bin/pg_dump",
            "--format=custom",
            "--dbname", databaseName);

    builder.directory(workingDirectory.toFile());
    builder.redirectOutput(outputFile.toFile());
    builder.redirectError(errorFile.toFile());

    Process process = builder.start();
    boolean finished = process.waitFor(2, TimeUnit.MINUTES);

    if (!finished) {
        process.destroy();
        if (!process.waitFor(5, TimeUnit.SECONDS)) {
            process.destroyForcibly();
            process.waitFor(5, TimeUnit.SECONDS);
        }
        throw new IllegalStateException("Tiến trình backup vượt quá thời gian cho phép.");
    }

    return process.exitValue();
}
~~~

Đây là ví dụ cho môi trường POSIX có executable `/usr/bin/pg_dump`; đường dẫn và option phải phù hợp với môi trường triển khai. Trong ứng dụng thực tế, executable nên đến từ cấu hình đáng tin cậy hoặc allowlist, thư mục làm việc và file output phải được kiểm soát, và file lỗi cần được bảo vệ vì có thể chứa thông tin nhạy cảm.

### ProcessBuilder không tự cấp quyền nghiệp vụ

`ProcessBuilder.start()` yêu cầu hệ điều hành tạo tiến trình. Nếu thành công, tiến trình con thường chạy với cùng tài khoản/token bảo mật và các quyền hệ điều hành của JVM cha, trừ khi nền tảng hoặc cơ chế khởi chạy đặc biệt thay đổi danh tính đó. `ProcessBuilder` không biết người dùng ứng dụng có quyền xuất báo cáo hay không.

Trước khi gọi `ProcessBuilder`, service vẫn phải kiểm tra người dùng có được phép yêu cầu backup hay không. Sau đó hệ điều hành tiếp tục kiểm tra tài khoản chạy JVM có quyền thực thi file chương trình, truy cập thư mục làm việc và tạo file output hay không.

### Không ghép input thành một chuỗi lệnh shell

Không làm như sau:

~~~java
String command = "pg_dump --dbname " + databaseName + " > " + outputPath;
new ProcessBuilder("sh", "-c", command).start();
~~~

Nếu `databaseName` hoặc `outputPath` chịu ảnh hưởng từ đầu vào không tin cậy, dữ liệu có thể thay đổi ý nghĩa câu lệnh khi đi qua shell. Việc dùng `sh -c`, `cmd /c` hoặc `powershell -Command` với chuỗi ghép động tạo thêm một tầng diễn giải lệnh.

Hãy truyền executable và từng argument riêng:

~~~java
new ProcessBuilder(
        "/usr/bin/pg_dump",
        "--dbname",
        validatedDatabaseName);
~~~

Tách argument giúp không ghép dữ liệu thành cú pháp của shell, nhưng chưa đủ để chống mọi dạng argument injection. Một giá trị có thể bị chương trình đích hiểu là option nguy hiểm. Vì vậy:

- Dùng executable cố định hoặc allowlist; không cho người dùng tùy ý chọn chương trình.
- Validate từng argument theo cú pháp và phạm vi mà chương trình đích cho phép.
- Với chương trình hỗ trợ, dùng `--` để kết thúc phần phân tích option trước operand do người dùng cung cấp.
- Không truyền input vào command interpreter như `sh -c`, `cmd.exe /c` hoặc `powershell -Command`.
- Ưu tiên API Java hoặc thư viện chuyên dụng nếu có thể thay thế việc gọi executable.

## 8. Môi trường và quyền của tiến trình con

Mặc định, `ProcessBuilder` khởi tạo environment của tiến trình con bằng một bản sao môi trường hiện tại của tiến trình Java. Tiến trình con có thể nhận các biến như `PATH`, proxy, cấu hình hoặc secret mà JVM đang giữ. Thư mục làm việc mặc định cũng dựa trên working directory của JVM.

Vì vậy, khi khởi chạy process:

- Chọn working directory cố định và có quyền truy cập phù hợp.
- Chỉ giữ các biến môi trường cần thiết; loại bỏ secret không liên quan nếu có thể.
- Không đưa password, token hoặc private key vào command argument vì chúng có thể bị lộ qua process inspection, log hoặc lịch sử.
- Dùng credential store, file cấu hình có permission hạn chế hoặc cơ chế secret injection được quản lý.
- Giới hạn thời gian chạy và xử lý exit code của tiến trình con.
- Redirect output/error vào vị trí có kiểm soát; không để log chứa credential.
- Dọn tiến trình con nếu command bị hủy hoặc ứng dụng đóng.

Việc xóa một biến môi trường không tự động làm sạch mọi thông tin bí mật đã được truyền qua file, argument, log hoặc bộ nhớ. Cần xác định rõ dữ liệu nào thực sự cần cho chương trình con.

## 9. Phân quyền cho command và audit log

Một command quản trị nên có chính sách rõ ràng: ai được gọi, tác động lên tài nguyên nào, cần xác nhận gì và kết quả được ghi nhận ở đâu. Không nên dựa vào việc command nằm trong group `admin` hoặc bị ẩn khỏi help để bảo vệ nghiệp vụ.

Một quy trình an toàn cho command `backup run` có thể gồm:

1. Xác thực người dùng ứng dụng.
2. Kiểm tra authority như `BACKUP_RUN`.
3. Kiểm tra phạm vi database/tenant mà người dùng được phép backup.
4. Kiểm tra cấu hình executable và thư mục đích đã được allowlist.
5. Yêu cầu xác nhận nếu thao tác có ảnh hưởng lớn hoặc tiêu tốn tài nguyên.
6. Khởi chạy process con với tài khoản hệ điều hành có quyền tối thiểu.
7. Kiểm tra timeout, exit code và kết quả file.
8. Ghi audit log.

Audit log nên ghi:

- Danh tính đã xác thực (subject/principal).
- Command hoặc hành động nghiệp vụ.
- Resource ID, tenant hoặc phạm vi liên quan.
- Thời điểm và correlation/request ID.
- Kết quả: thành công, bị từ chối, lỗi hệ điều hành hoặc process thất bại.
- Lý do từ chối ở mức có thể chẩn đoán mà không tiết lộ dữ liệu nhạy cảm.

Không ghi password, access token, private key hoặc toàn bộ nội dung nhạy cảm của argument vào audit log. Log cần được bảo vệ khỏi sửa/xóa trái phép và có chính sách lưu giữ phù hợp.

## 10. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Command chạy được khi dùng Administrator nhưng lỗi ở tài khoản thường | JVM thiếu quyền hệ điều hành cần thiết | Cấp ACL/permission hẹp cho thư mục hoặc tài nguyên cần dùng |
| Người dùng không có quyền vẫn gọi được service | Chỉ ẩn command hoặc kiểm tra ở giao diện | Bảo vệ method nghiệp vụ bằng method security và kiểm tra resource |
| `@PreAuthorize` không chặn lời gọi | Method Security chưa bật, bean không được quản lý hoặc lời gọi bỏ qua proxy | Bật `@EnableMethodSecurity`, inject bean từ context và kiểm tra call path |
| CLI chạy nhưng không có principal ứng dụng | Chưa cấu hình authentication provider hoặc login flow | Thiết lập xác thực; không suy role từ option hay environment do người dùng kiểm soát |
| Người dùng có role nhưng đọc được dữ liệu tenant khác | Chỉ kiểm tra role, thiếu object-level/tenant authorization | Kiểm tra quyền trên từng resource ở service |
| Command availability báo unavailable nhưng service vẫn thực hiện được | Availability chỉ phục vụ trạng thái command | Bảo vệ service method độc lập với availability |
| ProcessBuilder báo Access denied | Tài khoản JVM không có quyền execute/read/write cần thiết | Kiểm tra executable, thư mục, file ACL và tài khoản chạy ứng dụng |
| ProcessBuilder chạy lệnh ngoài dự kiến | Executable hoặc argument bị điều khiển từ input | Allowlist executable, truyền argument riêng và validate theo chương trình đích |
| Tiến trình con đọc được secret không cần thiết | Environment mặc định kế thừa từ JVM | Rà soát environment và loại bỏ biến không cần |
| Command ghi được file nhưng người dùng không được phép xuất dữ liệu | Chỉ dựa vào OS permission | Thêm authorization ở service trước khi xuất dữ liệu |
| Audit log không xác định được ai thực hiện | Chỉ ghi tên command hoặc PID | Ghi principal, action, resource, outcome và correlation ID |

## 11. Checklist kiểm soát quyền

- Xác định tài khoản hệ điều hành dùng để chạy JVM.
- Cấp quyền filesystem, network và executable tối thiểu cho tài khoản đó.
- Không chạy toàn bộ CLI bằng Administrator/root chỉ để sửa một lỗi quyền.
- Xác định cơ chế authentication của người dùng ứng dụng.
- Bật Method Security nếu dùng `@PreAuthorize` hoặc các annotation tương ứng.
- Kiểm tra quyền nghiệp vụ ở service được Spring quản lý.
- Kiểm tra tenant, ownership, trạng thái và hạn mức trên từng resource.
- Không xem command availability, help hoặc tên group là cơ chế bảo mật.
- Không tin role hoặc tenant do người dùng tự truyền trong option.
- Allowlist executable và validate từng argument khi dùng `ProcessBuilder`.
- Không ghép input vào `sh -c`, `cmd /c` hoặc PowerShell command string.
- Rà soát environment, working directory, output/error và timeout của process con.
- Ghi audit log đủ để truy vết nhưng không ghi secret.
- Kiểm thử cả trường hợp được phép, bị từ chối và bị hệ điều hành chặn.

## 12. Bài tập thực hành

Xây dựng command `orders refund --id <id>` và `backup run --database <name>`:

1. Chạy ứng dụng bằng một tài khoản hệ điều hành riêng, không có quyền quản trị toàn máy.
2. Tạo thư mục export riêng và chỉ cấp quyền ghi cho tài khoản dịch vụ.
3. Tạo authentication provider hoặc login flow cho người dùng CLI.
4. Bật `@EnableMethodSecurity` và đặt `@PreAuthorize("hasAuthority('ORDER_REFUND')")` trên service hoàn tiền.
5. Bổ sung kiểm tra tenant, trạng thái đơn hàng và hạn mức trước khi hoàn tiền.
6. Gọi service từ command bằng constructor injection; thử gọi trực tiếp service trong test để xác nhận method security vẫn chặn caller không đủ quyền.
7. Thử cấu hình command availability cho `orders refund`, rồi xác nhận service vẫn từ chối người dùng không có authority.
8. Tạo service backup chỉ cho phép một executable và thư mục đích được cấu hình sẵn.
9. Dùng `ProcessBuilder` với executable và argument tách riêng; thử database name chứa khoảng trắng, ký tự đặc biệt và chuỗi bắt đầu bằng dấu gạch ngang.
10. Rà soát environment của process con, timeout và exit code.
11. Kiểm tra người dùng có authority backup nhưng tài khoản hệ điều hành không có quyền ghi: thao tác phải thất bại ở lớp OS.
12. Kiểm tra tài khoản OS có quyền ghi nhưng người dùng thiếu authority nghiệp vụ: thao tác phải bị từ chối trước khi tạo file.
13. Ghi audit log cho thành công, bị từ chối và lỗi khởi chạy process; xác nhận log không chứa credential.

Khi hoàn thành, hãy giải thích vì sao quyền chạy `pg_dump` không chứng minh người dùng được phép xuất dữ liệu, và vì sao `ORDER_REFUND` không tự cấp quyền ghi file cho tiến trình JVM.

## Tài liệu tham khảo

- [Spring Shell 3.3 – Legacy Annotation](https://docs.spring.io/spring-shell/reference/3.3/commands/registration/legacyannotation.html): đăng ký command bằng `@ShellComponent` và `@ShellMethod`.
- [Spring Shell 3.3 – ShellMethodAvailability API](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/standard/ShellMethodAvailability.html): kiểm soát tính khả dụng của command.
- [Spring Security 6.3 – Method Security](https://docs.spring.io/spring-security/reference/6.3/servlet/authorization/method-security.html): bật `@EnableMethodSecurity`, dùng `@PreAuthorize` và bảo vệ lời gọi service.
- [Spring Security – Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html): `SecurityContext`, `Authentication` và cách Spring Security giữ danh tính caller.
- [Java SE 21 – ProcessBuilder API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ProcessBuilder.html): executable, argument, environment, working directory và khởi chạy tiến trình con.
- [OWASP – Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): least privilege, phân quyền theo người dùng, resource và hành động.
- [OWASP – OS Command Injection Defense Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OS_Command_Injection_Defense_Cheat_Sheet.html): allowlist executable, tách command/argument, validate input và giới hạn quyền tiến trình.

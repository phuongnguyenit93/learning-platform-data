# Kiểm tra điều kiện Spring Security nếu service nghiệp vụ được bảo vệ

Một command Spring Shell có thể gọi service để xem hóa đơn, duyệt yêu cầu, cập nhật tài khoản hoặc thực hiện thao tác quản trị. Nếu service đã được bảo vệ bằng Spring Security, command phải gọi service trong đúng ngữ cảnh xác thực và để quy tắc phân quyền của service được thực thi.

Điểm quan trọng là terminal không tự tạo ra một người dùng Spring Security. Người đang mở cửa sổ terminal chưa mặc nhiên trở thành `Authentication`. Ứng dụng CLI cần xác thực người dùng hoặc nạp danh tính từ cơ chế tin cậy, đặt `SecurityContext` trước khi gọi service, rồi xử lý trường hợp chưa đăng nhập hoặc không đủ quyền.

## 1. Phân biệt xác thực và phân quyền

Hai bước này trả lời hai câu hỏi khác nhau:

| Khái niệm | Câu hỏi | Ví dụ |
|---|---|---|
| Authentication (xác thực) | Ai đang thực hiện command? | Người dùng `linh` đã đăng nhập |
| Authorization (phân quyền) | Người đó được phép làm gì? | `linh` có quyền `invoice:read` nhưng không có `invoice:approve` |

Spring Security biểu diễn danh tính đang đăng nhập bằng `Authentication`. Đối tượng này chứa principal, credentials và các `GrantedAuthority` được cấp cho người dùng. `SecurityContext` chứa `Authentication` hiện tại và được truy cập qua `SecurityContextHolder`.

Một command chỉ là điểm vào của giao diện. Nó không thay thế quy trình xác thực và không nên tự quyết định quyền nghiệp vụ dựa trên chuỗi username hoặc role do người gọi truyền vào.

## 2. Bật method security trong ứng dụng

Để bảo vệ service bằng `@PreAuthorize`, bật method security trên một lớp cấu hình:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
class MethodSecurityConfiguration {
}
~~~

`@EnableMethodSecurity` đăng ký các interceptor dùng để kiểm tra quyền khi gọi method của Spring bean. Sau khi bật, ứng dụng có thể dùng `@PreAuthorize`, `@PostAuthorize`, `@PreFilter` và `@PostFilter`.

Không nên cho rằng chỉ thêm `spring-boot-starter-security` là đã bật method security. Spring Boot Starter Security không tự kích hoạt authorization ở cấp method; ứng dụng cần khai báo `@EnableMethodSecurity`.

Mặc định, `prePostEnabled` là `true`. Nếu muốn dùng `@Secured`, phải bật riêng:

~~~java
@Configuration
@EnableMethodSecurity(securedEnabled = true)
class MethodSecurityConfiguration {
}
~~~

Nếu dùng annotation JSR-250 như `@RolesAllowed`, bật `jsr250Enabled = true`. Với code mới, `@PreAuthorize` thường linh hoạt hơn và là lựa chọn được khuyến nghị.

## 3. Đặt quy tắc bảo vệ ở service nghiệp vụ

Service là nơi thích hợp để đặt quy tắc quyền vì nhiều loại giao diện có thể gọi cùng một nghiệp vụ: Spring Shell, REST controller, scheduler hoặc tác vụ nội bộ.

Ví dụ service quản lý hóa đơn:

~~~java
import java.util.List;

import org.springframework.security.access.prepost.PostAuthorize;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
class InvoiceService {

    private final InvoiceRepository invoiceRepository;

    InvoiceService(InvoiceRepository invoiceRepository) {
        this.invoiceRepository = invoiceRepository;
    }

    @PreAuthorize("hasAuthority('invoice:read')")
    public List<Invoice> findAll() {
        // Truy vấn hóa đơn.
        return List.of();
    }

    @PreAuthorize("hasAuthority('invoice:approve')")
    public void approve(long invoiceId) {
        // Duyệt hóa đơn.
    }

    @PostAuthorize("returnObject.owner == authentication.name")
    public Invoice findOne(long invoiceId) {
        // Tải một hóa đơn rồi chỉ trả về nếu thuộc người đang đăng nhập.
        return invoiceRepository.findById(invoiceId).orElseThrow();
    }
}
~~~

Trong ví dụ:

- `findAll()` chỉ chạy khi người dùng có authority `invoice:read`.
- `approve()` chỉ chạy khi có `invoice:approve`.
- `findOne()` kiểm tra chủ sở hữu của kết quả sau khi method trả về.

`@PostAuthorize` hữu ích cho thao tác đọc cần kiểm tra quyền sở hữu trên đối tượng trả về. Không dùng nó để bảo vệ thao tác ghi có tác dụng phụ: method đã chạy trước khi điều kiện sau method được đánh giá. Với thao tác cập nhật hoặc xóa, hãy kiểm tra quyền trước khi thay đổi dữ liệu.

## 4. Phân biệt role và authority

Spring Security hỗ trợ kiểm tra role hoặc authority:

~~~java
@PreAuthorize("hasRole('ADMIN')")
public void rebuildIndex() {
    // Chỉ dành cho ROLE_ADMIN.
}

@PreAuthorize("hasAuthority('invoice:approve')")
public void approve(long invoiceId) {
    // Chỉ dành cho authority invoice:approve.
}
~~~

`hasRole('ADMIN')` tự thêm tiền tố `ROLE_` theo mặc định, nên nó kiểm tra authority `ROLE_ADMIN`. `hasAuthority('invoice:approve')` so sánh chính xác chuỗi authority được cấp.

| Biểu thức | Authority được kiểm tra |
|---|---|
| `hasRole('ADMIN')` | `ROLE_ADMIN` |
| `hasAuthority('ROLE_ADMIN')` | `ROLE_ADMIN` |
| `hasAuthority('invoice:read')` | `invoice:read` |
| `hasAnyAuthority('invoice:read', 'invoice:admin')` | Một trong hai authority |

Nên dùng authority theo hành động nghiệp vụ như `invoice:read` và `invoice:approve` khi cần phân quyền chi tiết. Dùng role khi quyền được nhóm theo vai trò người dùng.

## 5. Command gọi service đã được bảo vệ

Command nên nhận dữ liệu từ terminal, gọi service Spring được inject và trình bày kết quả:

~~~java
import java.util.List;

import org.springframework.shell.core.command.annotation.Command;
import org.springframework.stereotype.Component;

@Component
class InvoiceCommands {

    private final InvoiceService invoiceService;

    InvoiceCommands(InvoiceService invoiceService) {
        this.invoiceService = invoiceService;
    }

    @Command(name = "invoice list", description = "List invoices")
    public List<Invoice> list() {
        return invoiceService.findAll();
    }
}
~~~

Khi `list()` gọi `invoiceService.findAll()`, Spring Security kiểm tra `invoice:read` trước khi chạy phần thân service. Command không cần tự đọc danh sách role rồi quyết định có gọi service hay không.

Ví dụ trên dùng annotation `@Command(name = ...)` của Spring Shell 4.x. Với Spring Shell 3.4, thuộc tính đặt tên command là `command` thay vì `name`; một số ứng dụng 3.4 cũng còn dùng annotation legacy `@ShellMethod`. Cơ chế method security của Spring Security không phụ thuộc vào cách đăng ký command.

## 6. Vì sao cần gọi service qua Spring bean?

Method security dựa trên Spring AOP. Spring tạo proxy cho bean được bảo vệ; lời gọi đi qua proxy mới kích hoạt interceptor kiểm tra quyền.

Vì vậy:

- Service phải là Spring-managed bean.
- Command phải inject service qua constructor hoặc cơ chế dependency injection.
- Method được bảo vệ nên là method có thể được proxy gọi, thường là public method.
- Không gọi method được bảo vệ bằng `this.otherMethod()` trong cùng object rồi kỳ vọng proxy kiểm tra quyền.

Ví dụ self-invocation không đi qua proxy:

~~~java
@Service
class ReportService {

    public void exportForCurrentUser() {
        this.exportAll(); // Lời gọi nội bộ không đi qua Spring proxy.
    }

    @PreAuthorize("hasAuthority('report:admin')")
    public void exportAll() {
        // ...
    }
}
~~~

Nếu cần bảo vệ `exportAll()`, hãy gọi nó từ một bean khác thông qua dependency được inject hoặc tách phần được bảo vệ sang service riêng. Không đặt annotation bảo mật rồi gọi method nội bộ bằng `this`.

## 7. Spring Shell không tự xác thực người dùng terminal

Với ứng dụng web, Spring Security thường lấy thông tin xác thực từ HTTP request thông qua filter chain. Một command Spring Shell không phải HTTP request, nên không có browser session hoặc form login tự động.

Nếu service yêu cầu quyền, ứng dụng CLI phải thiết lập danh tính bằng một cơ chế phù hợp:

- Xác thực username/password qua `AuthenticationManager` và `AuthenticationProvider`.
- Xác thực bằng token hoặc danh tính workload do hệ thống triển khai cung cấp.
- Dùng cơ chế đăng nhập riêng của tổ chức, chẳng hạn OIDC device flow hoặc credential store.

Không coi username, role hoặc quyền truyền qua argument của command là bằng chứng xác thực. Người dùng có thể tự sửa các giá trị đó.

## 8. Tạo Authentication bằng AuthenticationManager

Nếu ứng dụng dùng username/password, hãy gửi thông tin đăng nhập đến `AuthenticationManager`. Provider đã cấu hình sẽ kiểm tra credentials và trả về `Authentication` đã xác thực cùng authorities:

~~~java
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;

class CliLoginService {

    private final AuthenticationManager authenticationManager;

    CliLoginService(AuthenticationManager authenticationManager) {
        this.authenticationManager = authenticationManager;
    }

    public void login(String username, String password) {
        Authentication request =
                UsernamePasswordAuthenticationToken.unauthenticated(
                        username, password);

        Authentication authenticated =
                authenticationManager.authenticate(request);

        SecurityContext context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(authenticated);
        SecurityContextHolder.setContext(context);
    }

    public void logout() {
        SecurityContextHolder.clearContext();
    }
}
~~~

Luồng xử lý:

1. Tạo token chưa xác thực từ credentials vừa nhận.
2. Gọi `AuthenticationManager.authenticate(...)`.
3. Nếu xác thực thành công, nhận `Authentication` có principal và authorities do provider cấp.
4. Tạo `SecurityContext` mới, gắn authentication rồi đặt context vào `SecurityContextHolder`.
5. Khi logout, gọi `SecurityContextHolder.clearContext()`.

`AuthenticationManager` phải được cấu hình với provider phù hợp, chẳng hạn `DaoAuthenticationProvider` và `UserDetailsService`, hoặc provider xác thực token của hệ thống. Nếu không có provider xử lý loại token được gửi vào, authentication sẽ thất bại.

Không tự tạo một `UsernamePasswordAuthenticationToken` đã xác thực bằng role do người dùng nhập. Hãy để `AuthenticationManager` xác minh credentials và cấp authorities.

## 9. Thu thập bí mật an toàn trong CLI

Không nên nhận mật khẩu như một argument thông thường:

~~~text
login admin --password=secret123
~~~

Dòng lệnh có thể bị lưu trong history, log, script hoặc danh sách process tùy môi trường. Thay vào đó:

- Dùng prompt nhập mật khẩu có che ký tự.
- Dùng token hoặc credential từ kho bí mật của hệ điều hành.
- Với CI, lấy credential từ secret manager hoặc cơ chế identity của workload.
- Không in password, token hoặc toàn bộ `Authentication` ra output/log.
- Không lưu credentials trong file history.

Với command chạy non-interactive, không chờ người dùng nhập password qua prompt. Hãy nhận credential từ nguồn tin cậy đã cấu hình cho môi trường chạy.

## 10. SecurityContextHolder và vòng đời phiên CLI

Theo mặc định, `SecurityContextHolder` lưu context theo `ThreadLocal`. Các method được gọi trên cùng thread có thể đọc authentication hiện tại mà không cần truyền nó qua từng tham số.

Trong một CLI tương tác, ứng dụng có thể duy trì phiên đăng nhập giữa các command. Khi đó cần xác định rõ:

- Thời điểm login đặt context.
- Thời điểm logout xóa context.
- Điều gì xảy ra khi authentication hết hạn hoặc bị thu hồi.
- Context được đặt lại thế nào nếu command chạy trên thread khác.
- Context được xóa khi ứng dụng kết thúc.

Không nên để context của người dùng trước rò rỉ sang lần chạy command tiếp theo trong thread pool. Nếu command được thực thi qua executor hoặc tác vụ nền, cần truyền security context theo cơ chế hỗ trợ của Spring Security.

## 11. Truyền SecurityContext sang tác vụ nền

`SecurityContextHolder` dùng `ThreadLocal` mặc định, nên khi chuyển công việc sang thread mới, context thường không tự đi theo. Có thể dùng `DelegatingSecurityContextExecutor` để bọc executor:

~~~java
import java.util.concurrent.Executor;
import org.springframework.security.concurrent.DelegatingSecurityContextExecutor;

Executor securedExecutor =
        new DelegatingSecurityContextExecutor(delegateExecutor);

securedExecutor.execute(() -> invoiceService.findAll());
~~~

`DelegatingSecurityContextExecutor` lấy context hiện tại tại thời điểm submit task, gắn context đó cho task và dọn dẹp sau khi task chạy xong.

Nếu dùng Reactor với reactive security, context được quản lý trong Reactor Context và cần dùng các API reactive tương ứng như `ReactiveSecurityContextHolder`. Không giả định `ThreadLocal` sẽ tự hoạt động khi chuyển qua scheduler.

## 12. Xử lý lỗi xác thực và từ chối truy cập ở command boundary

Khi method security từ chối một lời gọi không xuất phát từ HTTP request, ứng dụng cần tự xử lý exception. `ExceptionTranslationFilter` không đứng trước một command Spring Shell như cách nó xử lý request web.

Command có thể bắt các lỗi bảo mật để hiển thị thông báo phù hợp:

~~~java
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.AuthenticationCredentialsNotFoundException;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.stereotype.Component;

@Component
class InvoiceCommands {

    private final InvoiceService invoiceService;

    InvoiceCommands(InvoiceService invoiceService) {
        this.invoiceService = invoiceService;
    }

    @Command(name = "invoice list", description = "List invoices")
    public String list() {
        try {
            return invoiceService.findAll().toString();
        }
        catch (AuthenticationCredentialsNotFoundException ex) {
            return "Bạn cần đăng nhập trước khi xem hóa đơn.";
        }
        catch (AccessDeniedException ex) {
            return "Tài khoản hiện tại không có quyền xem hóa đơn.";
        }
    }
}
~~~

Thông báo cho người dùng nên nói rõ hành động bị từ chối mà không tiết lộ dữ liệu nhạy cảm hoặc chi tiết nội bộ của hệ thống phân quyền.

Nếu command chạy trong script hoặc CI và cần báo thất bại bằng mã thoát khác `0`, đừng bắt exception rồi trả về chuỗi bình thường như thể command thành công. Hãy để lỗi đi tới cơ chế xử lý exception/exit status của ứng dụng hoặc ánh xạ lỗi phân quyền sang mã lỗi đã quy ước.

## 13. AvailabilityProvider không thay thế authorization

Spring Shell có `AvailabilityProvider` để đánh dấu command đang khả dụng hay không, kèm thông báo giải thích. Có thể dùng nó để cải thiện trải nghiệm, ví dụ command `invoice approve` hiển thị trạng thái unavailable khi chưa đăng nhập.

Tuy nhiên, availability chỉ hỗ trợ giao diện và khám phá command. Người dùng có thể gọi service từ một command khác hoặc một entry point khác. Vì vậy:

- Dùng `AvailabilityProvider` để giải thích trước rằng command chưa thể chạy.
- Dùng `@PreAuthorize` trên service để bảo vệ nghiệp vụ thực sự.
- Không dùng command ẩn hoặc unavailable như một biện pháp bảo mật.

Một command bị ẩn khỏi `help` vẫn có thể bị gọi qua entry point khác nếu service không được bảo vệ.

## 14. Kiểm thử service được bảo vệ

Nên kiểm tra cả trường hợp có quyền và không có quyền ở cấp service. Spring Security Test cung cấp `@WithMockUser` để tạo `SecurityContext` cho test.

Ví dụ:

~~~java
import static org.assertj.core.api.Assertions.assertThatCode;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;

@SpringBootTest
class InvoiceServiceSecurityTests {

    @Autowired
    InvoiceService invoiceService;

    @Test
    @WithMockUser(authorities = "invoice:read")
    void readerCanListInvoices() {
        assertThatCode(() -> invoiceService.findAll())
                .doesNotThrowAnyException();
    }

    @Test
    @WithMockUser(authorities = "invoice:read")
    void readerCannotApproveInvoice() {
        assertThatThrownBy(() -> invoiceService.approve(42L))
                .isInstanceOf(AccessDeniedException.class);
    }
}
~~~

Test này cần dependency `spring-security-test` trong scope test. `@WithMockUser(authorities = ...)` tạo principal giả với đúng authority để kiểm tra method security; nó không kiểm tra quy trình login thật.

Ngoài test service, nên có test command adapter để xác nhận:

- Người chưa đăng nhập nhận thông báo phù hợp.
- Người đã đăng nhập nhưng thiếu authority bị từ chối.
- Người có authority gọi được service.
- Command không làm lộ exception stack trace hoặc thông tin bí mật.
- Script nhận mã thoát khác `0` khi thao tác bị từ chối nếu đó là hợp đồng CLI.

## 15. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `@PreAuthorize` không có tác dụng | Chưa bật `@EnableMethodSecurity` | Thêm cấu hình method security |
| Service luôn từ chối dù command đã chạy | Chưa có `Authentication` trong `SecurityContext` | Xác thực người dùng và đặt context trước khi gọi service |
| Command tự nhận role từ option | Tin dữ liệu do người gọi kiểm soát | Lấy authorities từ authentication đã được provider xác minh |
| Web được bảo vệ nhưng CLI gọi service không bị chặn | Chỉ cấu hình URL trong `HttpSecurity` | Bảo vệ service bằng method security |
| Annotation có nhưng lời gọi nội bộ vẫn chạy | Self-invocation không đi qua Spring proxy | Gọi qua bean khác hoặc tách service |
| Tác vụ nền mất quyền của người gọi | `SecurityContext` không tự truyền sang thread khác | Dùng `DelegatingSecurityContextExecutor` hoặc cơ chế tương ứng |
| CLI không chuyển hướng sang trang login | Command không chạy trong HTTP request | Tự xử lý authentication exception và hướng dẫn login |
| `hasRole('ADMIN')` không khớp | Authority thực tế không có tiền tố `ROLE_` | Dùng đúng role hoặc kiểm tra bằng `hasAuthority` |
| `@Secured` không được kích hoạt | Chưa bật `securedEnabled` | Dùng `@EnableMethodSecurity(securedEnabled = true)` |
| Script báo thành công sau khi bị từ chối | Command bắt exception và trả kết quả bình thường | Propagate hoặc ánh xạ lỗi sang exit status khác `0` |
| Command unavailable nhưng service vẫn được gọi từ nơi khác | Nhầm availability với authorization | Giữ `@PreAuthorize` tại service |

## 16. Checklist tích hợp Spring Shell với Spring Security

Trước khi phát hành CLI có service được bảo vệ, hãy kiểm tra:

1. Ứng dụng đã bật `@EnableMethodSecurity`.
2. Quy tắc quyền nằm trên service nghiệp vụ, không chỉ trên command.
3. Command inject service qua Spring dependency injection.
4. Authentication được xác minh bởi `AuthenticationManager` hoặc cơ chế identity tin cậy.
5. `SecurityContext` được đặt trước khi gọi service và được xóa khi logout/kết thúc phiên.
6. Không nhận role hoặc authority từ argument do người dùng tự nhập.
7. Credentials không bị lộ trong command history, process arguments hoặc log.
8. Tác vụ chạy nền truyền security context đúng cách.
9. Command xử lý riêng trường hợp chưa xác thực và không đủ quyền.
10. Script/CI nhận mã thoát thất bại khi thao tác bị từ chối.
11. Test có người dùng đủ quyền, thiếu quyền và chưa xác thực.
12. Availability chỉ được dùng để cải thiện UX; service vẫn được bảo vệ độc lập.

## 17. Bài tập thực hành

Tạo command quản lý hóa đơn với ba thao tác:

- `invoice list`: yêu cầu authority `invoice:read`.
- `invoice show`: chỉ cho phép người dùng xem hóa đơn thuộc quyền của mình.
- `invoice approve`: yêu cầu authority `invoice:approve`.

Thực hiện:

1. Bật method security bằng `@EnableMethodSecurity`.
2. Đặt `@PreAuthorize` cho `findAll()` và `approve()`.
3. Dùng `@PostAuthorize` hoặc một policy bean để kiểm tra quyền sở hữu khi đọc một hóa đơn.
4. Tạo command adapter Spring Shell gọi các method service qua dependency injection.
5. Thiết lập authentication bằng `AuthenticationManager` trong luồng login của CLI.
6. Thêm logout để gọi `SecurityContextHolder.clearContext()`.
7. Hiển thị thông báo riêng khi chưa đăng nhập và khi không đủ quyền.
8. Viết test với `@WithMockUser(authorities = ...)` cho từng trường hợp.
9. Thử chạy command trong non-interactive mode và xác nhận lỗi phân quyền trả mã thoát thất bại.

Sau bài tập, hãy giải thích được vì sao quyền phải được kiểm tra ở service, vì sao command không tự tạo role từ input và vì sao `SecurityContext` cần được truyền đúng khi chạy tác vụ nền.

## Tài liệu tham khảo

- [Spring Security – Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security – Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Security – Concurrency Support](https://docs.spring.io/spring-security/reference/features/integrations/concurrency.html)
- [Spring Security – Testing Method Security](https://docs.spring.io/spring-security/reference/servlet/test/method.html)
- [Spring Security API – EnableMethodSecurity](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/annotation/method/configuration/EnableMethodSecurity.html)
- [Spring Shell 4.0.3 – Command Registration](https://docs.spring.io/spring-shell/reference/commands/registration.html)
- [Spring Shell 4.0.3 – Command Availability](https://docs.spring.io/spring-shell/reference/commands/availability.html)
- [Spring Shell 4.0.3 API – Command Annotation](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/Command.html)

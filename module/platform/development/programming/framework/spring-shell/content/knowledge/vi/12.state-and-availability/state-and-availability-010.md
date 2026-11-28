# Availability không thay thế kiểm tra quyền truy cập nghiệp vụ

Trong một ứng dụng Spring Shell, có những command chỉ hợp lý khi ứng dụng đang ở một trạng thái nhất định. Ví dụ, `download` chỉ có thể chạy sau khi kết nối đến máy chủ từ xa; `deploy` chỉ có thể chạy khi môi trường đã được chọn; hoặc `report-export` chỉ có thể chạy khi dữ liệu báo cáo đã sẵn sàng. Spring Shell cung cấp **command availability** để biểu thị trạng thái này và giải thích vì sao command hiện chưa thể chạy.

Tuy nhiên, một command khả dụng không có nghĩa người dùng hiện tại được phép thực hiện nghiệp vụ. Availability mô tả điều kiện vận hành hoặc ngữ cảnh; authorization xác định chủ thể nào được phép thực hiện hành động nào trên tài nguyên nào. Bài viết làm rõ hai khái niệm, cách khai báo `AvailabilityProvider` trong Spring Shell 4.x, cách bảo vệ service bằng Spring Security và cách kiểm thử cả hai lớp.

## 1. Phân biệt availability và authorization

Hãy xét một CLI quản lý tài liệu từ xa. Command `download` chỉ có ý nghĩa khi đã kết nối máy chủ. Sau khi kết nối, một người dùng có quyền `document:read` có thể tải tài liệu; người khác có thể không có quyền với tài liệu đó.

Hai câu hỏi cần được trả lời riêng:

- **Availability:** ứng dụng có đang ở trạng thái cho phép thực hiện command vào lúc này không? Ví dụ: đã kết nối máy chủ chưa, cấu hình đã được nạp chưa, dịch vụ từ xa có sẵn sàng không?
- **Authorization:** người dùng đã xác thực có quyền thực hiện hành động này trên tài nguyên được yêu cầu không? Ví dụ: có authority `document:download` không, tài liệu có thuộc phạm vi truy cập của người dùng không?

| Khái niệm | Câu hỏi | Ví dụ | Thành phần phù hợp |
|---|---|---|---|
| Authentication | Ai đang gọi? | Người dùng đã đăng nhập bằng tài khoản nào? | Cơ chế đăng nhập và `SecurityContext` |
| Availability | Command có thể chạy trong trạng thái hiện tại không? | Chưa kết nối máy chủ nên chưa thể tải file | Spring Shell `AvailabilityProvider` |
| Authorization | Chủ thể này có quyền làm việc đó không? | Người dùng không có quyền tải tài liệu A | Spring Security hoặc policy nghiệp vụ ở service |
| Validation | Đầu vào có hợp lệ không? | Mã tài liệu rỗng hoặc định dạng sai | Binding, Bean Validation và quy tắc nghiệp vụ |
| Feature flag | Tính năng có được bật cho bản phát hành/nhóm người dùng này không? | Chức năng export đang tắt trong đợt triển khai | Feature-flag/configuration service |

Một command có thể khả dụng nhưng người dùng vẫn bị từ chối vì thiếu quyền. Ngược lại, người dùng có quyền tải tài liệu nhưng command chưa khả dụng vì phiên kết nối chưa được thiết lập. Hai trạng thái không thay thế cho nhau.

## 2. Spring Shell biểu diễn availability như thế nào?

Spring Shell 4 dùng `Availability` để biểu diễn trạng thái của command:

- `Availability.available()` cho biết command hiện khả dụng.
- `Availability.unavailable(reason)` cho biết command hiện chưa khả dụng và cung cấp lý do.

`AvailabilityProvider` là một functional interface kế thừa `Supplier<Availability>`. Vì vậy, có thể triển khai bằng lambda hoặc method reference. Với command khai báo bằng annotation, thuộc tính `availabilityProvider` của `@Command` nhận tên bean cung cấp trạng thái.

Ví dụ tối thiểu:

```java
import org.springframework.shell.core.command.availability.Availability;
import org.springframework.shell.core.command.availability.AvailabilityProvider;

AvailabilityProvider downloadAvailability = () ->
        connected
                ? Availability.available()
                : Availability.unavailable("you are not connected to the remote server");
```

Nếu command chưa khả dụng, Spring Shell vẫn biết command tồn tại và có thể giải thích lý do. Ví dụ thông báo:

```text
shell:>download
Command 'download' exists but is not currently available because you are not connected to the remote server
```

Phần `reason` được nối sau từ “because”. Vì vậy, tài liệu Spring Shell khuyến nghị viết lý do bằng chữ thường và không thêm dấu chấm cuối câu, ví dụ `you are not connected`.

## 3. Khai báo availability cho command bằng annotation

Ví dụ ứng dụng có một trạng thái kết nối dùng chung:

```java
import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.stereotype.Component;

@Component
public class RemoteConnectionState {

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
```

Command `connect` cập nhật trạng thái; command `download` tham chiếu provider bằng tên bean:

```java
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
public class RemoteCommands {

    private final RemoteConnectionService connectionService;
    private final DocumentDownloadService downloadService;

    public RemoteCommands(
            RemoteConnectionService connectionService,
            DocumentDownloadService downloadService) {
        this.connectionService = connectionService;
        this.downloadService = downloadService;
    }

    @Command(name = "connect", description = "Connect to the remote server")
    public String connect() {
        connectionService.connect();
        return "Connected";
    }

    @Command(
            name = "download",
            description = "Download a document",
            availabilityProvider = "downloadAvailability")
    public String download(@Option(longName = "document-id") String documentId) {
        return downloadService.download(documentId);
    }
}
```

Đăng ký provider:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.shell.core.command.availability.Availability;
import org.springframework.shell.core.command.availability.AvailabilityProvider;

@Configuration
public class CommandAvailabilityConfiguration {

    @Bean
    AvailabilityProvider downloadAvailability(RemoteConnectionState state) {
        return () -> state.isConnected()
                ? Availability.available()
                : Availability.unavailable("you are not connected to the remote server");
    }
}
```

Tên bean mặc định của method `downloadAvailability` là `downloadAvailability`, khớp với thuộc tính `availabilityProvider` trên `@Command`. Khi kết nối thành công, `RemoteConnectionState` chuyển sang connected và command có thể được sử dụng. Khi disconnect, provider trả về lý do không khả dụng.

Trong ví dụ thực tế, `RemoteConnectionService.connect()` và `disconnect()` phải cập nhật cùng một nguồn trạng thái mà provider đọc. Nếu có nhiều loại kết nối hoặc nhiều tài khoản, hãy lưu trạng thái theo đúng session/connection thay vì dùng một biến Boolean toàn cục cho tất cả người dùng.

## 4. Availability provider nên kiểm tra điều gì?

Provider phù hợp để kiểm tra các điều kiện vận hành hoặc ngữ cảnh cần thiết để command có ý nghĩa tại thời điểm hiện tại.

| Điều kiện | Ví dụ lý do unavailable |
|---|---|
| Chưa kết nối | `you are not connected to the remote server` |
| Chưa chọn môi trường | `you have not selected a deployment environment` |
| Cấu hình chưa được nạp | `the application configuration has not been loaded` |
| Tác vụ nền đang chạy | `another import operation is still running` |
| Dịch vụ phụ thuộc đang bảo trì | `the reporting service is under maintenance` |
| Phiên làm việc đã hết hạn | `your remote session has expired` |

Provider thường được gọi để xác định trạng thái command trong shell. Vì vậy, nên giữ logic kiểm tra nhanh, có thể lặp lại và không tạo side effect. Tránh tải toàn bộ dữ liệu, ghi file, thay đổi trạng thái kết nối hoặc chạy một nghiệp vụ dài bên trong provider.

Lý do unavailable nên ngắn gọn, hướng tới hành động tiếp theo của người dùng. Ví dụ `you need to connect first` giúp người dùng biết phải làm gì; thông báo `state=false` không giải thích được vấn đề.

## 5. Availability không phải là kiểm soát quyền truy cập

Giả sử command `download` chỉ khả dụng sau khi kết nối. Provider có thể trả về `Availability.available()` cho mọi người dùng khi kết nối đã sẵn sàng. Điều đó chỉ nói rằng hạ tầng cho phép thử tải file; nó không xác nhận người dùng có quyền tải tài liệu được yêu cầu.

Không nên dùng các cách sau làm cơ chế bảo vệ nghiệp vụ:

- Chỉ đánh dấu command unavailable khi người dùng thiếu role.
- Đặt `hidden = true` trên `@Command` rồi coi command là được bảo vệ.
- Ẩn option hoặc không gợi ý command trong help để ngăn người dùng gọi.
- Kiểm tra quyền trong availability provider nhưng bỏ qua kiểm tra ở service.
- Dựa vào việc command không xuất hiện trong danh sách gợi ý để tin rằng người dùng không thể gọi nghiệp vụ.

`@Command(hidden = true)` điều khiển việc hiển thị command trong trợ giúp. Nó không tạo authorization policy. Availability giúp Spring Shell thông báo và ngăn gọi command khi điều kiện vận hành không đạt trong shell; nó không bảo vệ các đường gọi khác tới service hoặc dữ liệu.

Một người dùng có thể gọi cùng service từ command khác, scheduler, REST endpoint, test, hoặc một bean khác. Vì vậy, quyền phải được kiểm tra tại ranh giới thực thi nghiệp vụ, nơi mọi đường gọi đều đi qua.

## 6. Bảo vệ service bằng Spring Security Method Security

Spring Security hỗ trợ kiểm tra quyền ở cấp method. Với Spring Boot, thêm dependency Spring Security phù hợp, bật method security bằng `@EnableMethodSecurity`, rồi đặt `@PreAuthorize` trên service method.

Cấu hình:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
```

Service thực hiện nghiệp vụ:

```java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentDownloadService {

    @PreAuthorize("hasAuthority('document:download')")
    public String download(String documentId) {
        // Load the document and perform the download.
        return "Downloaded document " + documentId;
    }
}
```

Khi method security được bật, Spring Security kiểm tra authority trước khi method service được thực thi. Nếu chủ thể không có `document:download`, Spring Security từ chối invocation bằng `AccessDeniedException`.

Lưu ý: `spring-boot-starter-security` không tự bật method-level authorization. Cần khai báo `@EnableMethodSecurity` hoặc cấu hình XML tương ứng. Các annotation `@PreAuthorize`, `@PostAuthorize`, `@PreFilter` và `@PostFilter` được kích hoạt bởi cấu hình method security mặc định.

Nếu quyền phụ thuộc vào tài nguyên, kiểm tra thêm quyền trên đúng đối tượng. Ví dụ người dùng có thể có quyền tải tài liệu nói chung nhưng chỉ được tải tài liệu thuộc nhóm của mình. Có thể dùng một bean policy trong biểu thức `@PreAuthorize` hoặc gọi một `AuthorizationService` từ service trước khi đọc dữ liệu.

## 7. Authentication trong CLI và SecurityContext

Authorization cần biết chủ thể đang thực hiện lệnh. Trong ứng dụng CLI, không có HTTP request mặc định để tạo `SecurityContext` như ứng dụng web. Ứng dụng cần có quy trình xác thực phù hợp, chẳng hạn đăng nhập vào dịch vụ identity, dùng token hoặc xác thực qua một credential provider.

Sau khi xác thực thành công, Spring Security cần có `Authentication` trong `SecurityContextHolder` để `@PreAuthorize` đánh giá authority:

```java
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;

@Service
public class CliLoginService {

    private final AuthenticationManager authenticationManager;

    public CliLoginService(AuthenticationManager authenticationManager) {
        this.authenticationManager = authenticationManager;
    }

    public void login(String username, char[] password) {
        Authentication authentication = authenticationManager.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                        username, password));

        SecurityContext context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(authentication);
        SecurityContextHolder.setContext(context);
    }

    public void logout() {
        SecurityContextHolder.clearContext();
    }
}
```

Đoạn code minh họa bước đặt `Authentication` sau khi `AuthenticationManager` xác thực thành công; cấu hình `AuthenticationManager` và provider tùy thuộc hệ thống danh tính của ứng dụng. Trong ứng dụng tương tác nhiều người dùng hoặc xử lý command song song, cần quản lý context theo đúng vòng đời session và thread, tránh chia sẻ `SecurityContext` giữa các người dùng.

Không dùng một cờ `loggedIn = true` làm bằng chứng rằng người dùng có quyền. Cờ đó có thể giúp availability provider biết phiên đã đăng nhập để hiển thị command; quyền thực tế vẫn lấy từ `Authentication` và policy được thực thi ở service.

## 8. Kết hợp availability và authorization trong cùng luồng

Luồng thực thi hợp lý cho command tải tài liệu có thể diễn ra như sau:

```text
Người dùng gọi `download --document-id=...`
                 |
                 v
Spring Shell hỏi AvailabilityProvider
                 |
          +------+------+
          |             |
      unavailable     available
          |             |
    Hiển thị lý do      v
    và dừng lệnh   Gọi command method
                        |
                        v
                Gọi DocumentDownloadService
                        |
                        v
                Spring Security kiểm tra quyền
                        |
                 +------+------+
                 |             |
               denied        granted
                 |             |
           AccessDenied       v
             Exception   Thực hiện tải file
```

Hai bước có vai trò riêng:

1. Availability kiểm tra điều kiện vận hành như kết nối, môi trường hoặc trạng thái dịch vụ.
2. Authorization kiểm tra danh tính và quyền của chủ thể ngay tại lời gọi nghiệp vụ.

Ví dụ ma trận kết quả:

| Đã kết nối? | Có quyền `document:download`? | Kết quả |
|---|---|---|
| Không | Không | Command unavailable vì chưa kết nối |
| Không | Có | Command unavailable vì chưa kết nối |
| Có | Không | Command chạy đến service nhưng bị authorization từ chối |
| Có | Có | Service được phép thực hiện nghiệp vụ, nếu các điều kiện khác hợp lệ |

Nếu provider cũng kiểm tra quyền để cải thiện trải nghiệm help, vẫn phải giữ kiểm tra ở service. Provider có thể phản ánh quyền để người dùng hiểu trạng thái, nhưng kết quả đó không phải quyết định bảo mật cuối cùng.

## 9. Kiểm tra lại trạng thái khi thực thi để tránh race condition

Availability thường được đọc trước thời điểm command method chạy. Trạng thái có thể thay đổi giữa hai thời điểm: kết nối bị ngắt, token hết hạn, quyền bị thu hồi hoặc tài nguyên chuyển sang trạng thái khóa.

Ví dụ:

1. Provider kiểm tra kết nối và trả `available`.
2. Kết nối bị ngắt ngay sau đó.
3. Command bắt đầu gọi service.

Nếu service giả định kết nối vẫn còn chỉ vì provider đã trả `available`, command có thể thất bại không rõ nguyên nhân hoặc thực hiện một phần tác vụ. Vì vậy, service cần kiểm tra lại điều kiện vận hành bắt buộc tại thời điểm sử dụng tài nguyên. Với thao tác cập nhật dữ liệu, kiểm tra trạng thái và ghi dữ liệu nên được bảo vệ bằng transaction, khóa hoặc cơ chế đồng bộ phù hợp.

Authorization cũng cần được kiểm tra trong cùng luồng thực thi thực tế. Không kiểm tra quyền một lần trong availability provider rồi dùng kết quả cũ cho thao tác sau. Nếu quyền trên tài nguyên có thể thay đổi đồng thời, thiết kế policy và transaction cần bảo đảm thao tác không dựa trên quyết định đã lỗi thời.

## 10. Phân biệt availability với feature flag và trạng thái nghiệp vụ

Một số điều kiện có thể được đưa vào availability để giúp người dùng biết command hiện có dùng được hay không. Tuy nhiên, cần xác định nguồn chịu trách nhiệm cho từng quy tắc:

| Điều kiện | Nơi thể hiện phù hợp | Nơi phải kiểm tra khi thực thi |
|---|---|---|
| Chưa kết nối server | Availability provider | Service/client kiểm tra kết nối trước khi dùng |
| Chưa chọn môi trường | Availability provider | Use case xác nhận môi trường hợp lệ |
| Feature flag tắt chức năng | Availability có thể phản ánh để cải thiện UX | Service/use case kiểm tra flag nếu flag là điều kiện bắt buộc |
| Người dùng thiếu quyền | Có thể phản ánh trong UI/help nếu phù hợp | Authorization ở service hoặc policy nghiệp vụ |
| Tài liệu đã bị khóa | Availability chỉ phù hợp nếu đó là trạng thái chung của command | Kiểm tra trạng thái tài liệu ngay trước thao tác |
| Dữ liệu option sai định dạng | Parser/conversion/validation | Chặn trước khi vào nghiệp vụ |

Feature flag thường điều khiển rollout, cấu hình hoặc license của tính năng. Nó có thể ảnh hưởng availability để command không gây bất ngờ cho người dùng, nhưng nếu việc bật/tắt là ràng buộc bắt buộc thì use case cũng phải thực thi quy tắc đó. Authorization vẫn là quyết định dựa trên chủ thể và quyền, không phải một cờ tính năng.

## 11. Xử lý lỗi authorization trong ứng dụng CLI

Trong ứng dụng web, `ExceptionTranslationFilter` có thể chuyển một số `AccessDeniedException` thành HTTP 403. Khi service được gọi từ command line, thường không có HTTP request để filter này xử lý. Tài liệu Spring Security lưu ý rằng các invocation ngoài HTTP có thể cần tự xử lý `AccessDeniedException`.

Ở biên command, ứng dụng nên:

- Hiển thị thông báo ngắn gọn như `you do not have permission to download this document`.
- Không hiển thị token, mật khẩu, policy nội bộ hoặc chi tiết nhạy cảm trong thông báo.
- Chuyển lỗi sang trạng thái/mã thoát phù hợp để script và CI nhận biết thao tác bị từ chối.
- Giữ nguyên exception gốc trong log bảo mật có kiểm soát nếu cần điều tra.

Không biến `AccessDeniedException` thành kết quả thành công chỉ để tránh hiện stack trace. Một automation cần biết rõ thao tác đã bị từ chối để không tiếp tục các bước phụ thuộc.

## 12. Kiểm thử availability và authorization độc lập

Kiểm thử hai cơ chế riêng giúp phát hiện trường hợp provider hoạt động đúng nhưng service chưa được bảo vệ, hoặc service có bảo vệ nhưng trải nghiệm command không giải thích được trạng thái.

| Ca kiểm thử | Trạng thái kết nối | Authentication/authority | Kỳ vọng |
|---|---|---|---|
| 1 | Chưa kết nối | Chưa đăng nhập | `download` unavailable với lý do phù hợp |
| 2 | Đã kết nối | Có `document:download` | Service cho phép tải tài liệu được phép |
| 3 | Đã kết nối | Không có authority | Service ném `AccessDeniedException`; không tải file |
| 4 | Đã kết nối | Có authority nhưng không có quyền trên tài liệu cụ thể | Policy tài nguyên từ chối; không trả dữ liệu |
| 5 | Provider trả available, sau đó kết nối bị ngắt | Có authority | Service/client phát hiện trạng thái mới và dừng an toàn |
| 6 | Command bị ẩn khỏi help | Không có authority | Gọi trực tiếp service vẫn bị từ chối |
| 7 | Logout | SecurityContext đã được xóa | Invocation tiếp theo không còn dùng Authentication cũ |

Các kiểm tra nên bao gồm:

1. Unit test `AvailabilityProvider` cho cả `available()` và `unavailable(reason)`.
2. Test command để xác nhận lệnh unavailable không chạy method command và lý do hiển thị đúng.
3. Unit/integration test service với `@WithMockUser` hoặc thiết lập `SecurityContext` phù hợp để kiểm tra authority.
4. Test truy cập tài nguyên để bảo đảm người dùng không thể tải đối tượng ngoài phạm vi được phép.
5. Test service trực tiếp, không thông qua Spring Shell, để chứng minh authorization được đặt ở đúng ranh giới.
6. Test race condition bằng cách thay đổi trạng thái kết nối hoặc quyền giữa lúc provider trả kết quả và lúc service thực thi.

## 13. Các lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Dùng availability để kiểm tra role duy nhất | Service có thể bị gọi từ đường khác mà không qua provider | Bảo vệ service bằng authorization policy |
| Dùng `hidden = true` để che command nhạy cảm | Ẩn khỏi help nhưng không bảo vệ nghiệp vụ | Dùng method security hoặc policy ở service |
| Chỉ kiểm tra quyền trong command method | Một caller khác có thể gọi thẳng service | Đặt kiểm tra tại service/use-case boundary |
| Cho rằng `spring-boot-starter-security` tự bật `@PreAuthorize` | Method security có thể chưa được kích hoạt | Khai báo `@EnableMethodSecurity` |
| Dùng Boolean `connected` chung cho nhiều người dùng | Một session có thể ảnh hưởng availability của session khác | Lưu trạng thái theo đúng session/principal |
| Provider gọi API hoặc truy vấn nặng mỗi lần kiểm tra | Help/completion/command invocation chậm | Giữ provider nhanh, đọc trạng thái đã được quản lý |
| Không kiểm tra lại kết nối trong service | Trạng thái có thể đổi sau khi provider trả available | Kiểm tra điều kiện vận hành ngay trước thao tác |
| Xử lý `AccessDeniedException` như thành công | Script tiếp tục dù thao tác bị từ chối | Trả trạng thái lỗi và mã thoát phù hợp |
| Không xóa SecurityContext khi logout | Lệnh sau có thể giữ danh tính cũ | Gọi `SecurityContextHolder.clearContext()` |

## 14. Checklist thiết kế command an toàn

- [ ] Đã xác định điều kiện vận hành nào quyết định command availability.
- [ ] Availability provider trả `Availability.available()` hoặc `Availability.unavailable(reason)` đúng trạng thái.
- [ ] Lý do unavailable ngắn, dễ hành động và phù hợp cách Spring Shell hiển thị.
- [ ] Provider không thực hiện nghiệp vụ hoặc side effect.
- [ ] Không dùng `hidden` hoặc availability làm cơ chế authorization.
- [ ] Người dùng được xác thực và `SecurityContext` được quản lý theo session phù hợp.
- [ ] Method security đã được bật bằng `@EnableMethodSecurity` nếu dùng `@PreAuthorize`.
- [ ] Quyền được kiểm tra tại service/use-case boundary, kể cả quyền trên tài nguyên cụ thể.
- [ ] Service kiểm tra lại các điều kiện vận hành có thể thay đổi trước khi dùng tài nguyên.
- [ ] `AccessDeniedException` được xử lý phù hợp với môi trường CLI, không phụ thuộc HTTP filter.
- [ ] Có kiểm thử riêng cho unavailable, authorization denied và trường hợp thành công.
- [ ] Script/CI nhận được trạng thái thất bại khi người dùng không có quyền.

## Tài liệu tham khảo

1. [Spring Shell 4 – Command Availability](https://docs.spring.io/spring-shell/reference/commands/availability.html) – `Availability`, `AvailabilityProvider` và khai báo `availabilityProvider` cho command.
2. [Spring Shell 4 – `@Command` API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/Command.html) – thuộc tính `availabilityProvider` và `hidden`.
3. [Spring Shell 4 – `Availability` API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/availability/Availability.html) và [`AvailabilityProvider` API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/availability/AvailabilityProvider.html) – kiểu dữ liệu và functional interface.
4. [Spring Security 7 – Method Security](https://docs.spring.io/spring-security/reference/7.0/servlet/authorization/method-security.html) – `@EnableMethodSecurity`, `@PreAuthorize`, và bảo vệ method ở service layer.
5. [Spring Shell – v4 Migration Guide](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide) – cách cấu hình availability bằng thuộc tính `availabilityProvider` của `@Command` trong Spring Shell 4.

Availability giúp CLI giải thích khi nào một command có thể chạy trong trạng thái hiện tại. Authorization bảo vệ nghiệp vụ bằng cách xác minh chủ thể có quyền thực hiện hành động trên tài nguyên. Hãy dùng availability để cải thiện trải nghiệm command và đặt quyết định quyền tại service/use-case boundary để mọi đường gọi đều tuân theo cùng một chính sách.

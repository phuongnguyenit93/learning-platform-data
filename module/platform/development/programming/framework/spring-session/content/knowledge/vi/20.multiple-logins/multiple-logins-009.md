# Tra cứu, hiển thị và thu hồi một phiên cụ thể của người dùng

Trong ứng dụng Spring Session, một người dùng có thể đăng nhập trên nhiều trình duyệt hoặc thiết bị. Mỗi lần đăng nhập thường tương ứng với một session ID riêng. Khi cần hiển thị danh sách phiên đang hoạt động và cho phép người dùng thu hồi một phiên cụ thể, ứng dụng phải tìm đúng các session thuộc principal đã xác thực, chỉ hiển thị metadata cần thiết và xóa đúng session được chọn.

Spring Session cung cấp `FindByIndexNameSessionRepository` để tìm các session theo principal name. Sau khi có danh sách session của người dùng, ứng dụng có thể chọn một session ID và gọi `deleteById`. Điểm bảo mật quan trọng là phải xác minh session mục tiêu thực sự thuộc người dùng hiện tại trước khi xóa. Session ID là bearer credential; không nên đưa giá trị thô này vào giao diện, URL hoặc log chỉ để làm nút “đăng xuất thiết bị”.

## 1. Hai thao tác khác nhau: tìm theo người dùng và tìm theo session ID

Hợp đồng `SessionRepository` cung cấp thao tác theo ID:

```java
S findById(String id);
void deleteById(String id);
```

`findById` hữu ích khi đã biết ID và muốn khôi phục một session cụ thể. `deleteById` xóa session theo ID. Tuy nhiên, chỉ biết một ID không chứng minh caller có quyền xem hoặc xóa session đó.

`FindByIndexNameSessionRepository` mở rộng repository cơ bản bằng API tìm session theo index:

```java
Map<String, S> findByIndexNameAndIndexValue(
        String indexName, String indexValue);
```

Index được dùng phổ biến nhất là principal name:

```java
FindByIndexNameSessionRepository.PRINCIPAL_NAME_INDEX_NAME
```

Repository cũng cung cấp shortcut `findByPrincipalName(principalName)` trên các phiên bản API tương ứng. Kết quả là map trong đó key là session ID và value là session. Có thể dùng map này để liệt kê các phiên thuộc một người dùng và xác minh một session ID có nằm trong tập đó hay không.

Các implementation indexed phổ biến gồm `RedisIndexedSessionRepository` và `JdbcIndexedSessionRepository`. Repository Redis cơ bản không có index principal tích hợp; nếu cần chức năng này, phải dùng implementation indexed hoặc một cơ chế index riêng được quản lý nhất quán.

## 2. Principal index được tạo từ đâu?

Để tìm session theo principal, repository cần biết tên principal gắn với session. Với tích hợp Spring Security, Spring Session có thể dùng `PrincipalNameIndexResolver` để lấy principal name từ `SecurityContext` được lưu trong session.

Với cơ chế xác thực tùy chỉnh, ứng dụng phải cung cấp giá trị index bằng attribute có tên `PRINCIPAL_NAME_INDEX_NAME`:

```java
session.setAttribute(
        FindByIndexNameSessionRepository.PRINCIPAL_NAME_INDEX_NAME,
        principalName);
```

Chỉ đặt giá trị này sau khi danh tính đã được xác thực ở phía server. Không lấy `username`, `email` hoặc `userId` do client gửi lên làm principal đã xác thực. Nếu index được tạo từ dữ liệu không đáng tin, một session có thể bị gắn nhầm vào người dùng khác hoặc bị bỏ khỏi kết quả tra cứu.

Principal name phải ổn định và nhất quán giữa các instance. Nếu hệ thống có nhiều tenant, cân nhắc dùng định danh duy nhất có namespace tenant, ví dụ `tenantId:subjectId`, thay vì username có thể trùng giữa các tenant. Cách chuẩn hóa principal phải giống nhau ở login, lookup và revoke.

## 3. Truy vấn các phiên của người dùng hiện tại

Trong endpoint tự quản lý phiên của người dùng đang đăng nhập, lấy principal từ `Authentication` do Spring Security cung cấp:

```java
@RestController
@RequestMapping("/api/me/sessions")
class MySessionsController {

    private final UserSessionService sessions;

    MySessionsController(UserSessionService sessions) {
        this.sessions = sessions;
    }

    @GetMapping
    List<SessionSummary> list(Authentication authentication) {
        return this.sessions.listFor(authentication.getName());
    }
}
```

Ví dụ này dành cho ứng dụng Servlet dùng Spring MVC. Với WebFlux, lấy principal qua `Mono<Authentication>` hoặc `ReactiveSecurityContextHolder` và trả về `Mono`/`Flux`; không dùng chữ ký controller đồng bộ như trên.

Service dùng repository indexed:

```java
@Service
class UserSessionService {

    private final FindByIndexNameSessionRepository<? extends Session> repository;

    UserSessionService(
            FindByIndexNameSessionRepository<? extends Session> repository) {
        this.repository = repository;
    }

    Map<String, ? extends Session> findSessions(String principalName) {
        return this.repository.findByPrincipalName(principalName);
    }
}
```

Kiểu generic cụ thể có thể cần điều chỉnh theo bean và phiên bản Spring Session đang dùng. Điều quan trọng là repository phải thực sự triển khai `FindByIndexNameSessionRepository`; ép kiểu một repository không hỗ trợ index sẽ không tạo ra khả năng tra cứu.

## 4. Chỉ hiển thị metadata cần thiết

Không trả toàn bộ session attributes cho giao diện. Session có thể chứa `SecurityContext`, thông tin xác thực, CSRF state, dữ liệu nghiệp vụ hoặc các giá trị nội bộ khác. Endpoint quản lý phiên nên ánh xạ session thành một DTO an toàn, ví dụ:

```java
public record SessionSummary(
        String reference,
        Instant createdAt,
        Instant lastAccessedAt,
        Duration maxInactiveInterval,
        String deviceLabel,
        boolean current) {
}
```

Các phương thức của `Session` cung cấp metadata như `getCreationTime()`, `getLastAccessedTime()`, `getMaxInactiveInterval()` và `getAttributeNames()`. Ứng dụng có thể lưu thêm metadata thiết bị do chính server ghi nhận lúc đăng nhập, chẳng hạn nhãn thiết bị hoặc loại client.

Thông tin như địa chỉ IP và User-Agent không tự động trở thành metadata đáng tin của Spring Session. Nếu cần hiển thị, hãy chủ động lưu một bản đã chuẩn hóa ở thời điểm đăng nhập. User-Agent có thể bị giả mạo; IP có thể thay đổi do mạng di động, VPN hoặc proxy. Không dùng hai giá trị này làm yếu tố duy nhất để quyết định quyền truy cập.

Ví dụ tạo DTO từ session:

```java
List<SessionSummary> listFor(String principalName, String currentSessionId) {
    Map<String, ? extends Session> found =
            repository.findByPrincipalName(principalName);

    return found.values().stream()
            .filter(session -> !session.isExpired())
            .map(session -> new SessionSummary(
                    referenceService.create(principalName, session.getId()),
                    session.getCreationTime(),
                    session.getLastAccessedTime(),
                    session.getMaxInactiveInterval(),
                    safeDeviceLabel(session),
                    session.getId().equals(currentSessionId)))
            .toList();
}
```

Đoạn mã minh họa, cần điều chỉnh theo phiên bản Java và Spring Session. `referenceService` tạo tham chiếu quản lý riêng; không trả trực tiếp session ID. `safeDeviceLabel` chỉ đọc attribute do ứng dụng tự lưu và phải xử lý trường hợp thiếu hoặc sai kiểu. Nếu API phiên bản đang dùng không cung cấp `isExpired()` trên interface được inject, dựa vào kết quả repository và kiểm tra timeout theo API tương ứng.

## 5. Không để lộ session ID trong giao diện

Session ID là bearer credential: người có ID còn hiệu lực có thể thử dùng nó để khôi phục phiên. Nếu endpoint danh sách phiên trả session ID thô cho JavaScript, ứng dụng đã làm lộ một credential mà cookie có thể đang được bảo vệ bằng `HttpOnly`.

Nên dùng một `reference` riêng cho giao diện quản lý phiên. Có hai cách thường gặp:

1. Tạo một mã ngẫu nhiên độc lập, lưu ánh xạ `principal + reference -> sessionId` ở server với TTL phù hợp.
2. Tạo tham chiếu không thể đảo ngược bằng HMAC của `principal + sessionId`, dùng khóa bí mật được quản lý ngoài source code. Khi revoke, tra các session thuộc principal và so sánh tham chiếu được tính lại.

Tham chiếu quản lý vẫn cần được kiểm tra quyền và ràng buộc với principal. Không dùng nó thay cho session ID để xác thực request thông thường. Nếu reference được ký hoặc có thời hạn, cần hỗ trợ xoay khóa và từ chối reference hết hạn.

Tránh đặt session ID trong URL path hoặc query string vì URL có thể xuất hiện trong access log, browser history, Referer header, analytics và hệ thống tracing. Không log cookie, `Set-Cookie`, reference nhạy cảm hoặc payload session nguyên vẹn.

## 6. Xác minh quyền sở hữu trước khi thu hồi

Giả sử client gửi một reference để thu hồi phiên. Server phải:

1. Lấy principal hiện tại từ SecurityContext đã xác thực.
2. Tra các session được index cho principal đó.
3. Tìm session ID tương ứng với reference trong tập session vừa tra.
4. Chỉ xóa session nếu tìm thấy nó trong tập của principal hiện tại.
5. Nếu không tìm thấy, trả kết quả không tiết lộ liệu session ID đó có tồn tại thuộc người khác hay không.

Không làm như sau:

```java
// Không an toàn nếu sessionId do client gửi mà không kiểm tra quyền sở hữu
repository.deleteById(request.sessionId());
```

Việc gọi `deleteById` trực tiếp dựa trên ID do client cung cấp có thể cho phép người dùng xóa session của người khác nếu đoán hoặc lấy được ID. Ngay cả khi ID đủ ngẫu nhiên, endpoint vẫn phải thực hiện authorization ở server.

## 7. Thu hồi một session cụ thể bằng deleteById

Với repository indexed, có thể tra tập session của principal rồi xóa đúng ID đã được xác minh:

```java
boolean revoke(String principalName, String sessionId) {
    Map<String, ? extends Session> owned =
            repository.findByPrincipalName(principalName);

    if (!owned.containsKey(sessionId)) {
        return false;
    }

    repository.deleteById(sessionId);
    return true;
}
```

Đây là ví dụ ở tầng service. Controller không nên nhận raw session ID từ UI; thay vào đó, giải mã hoặc tra reference quản lý để xác định ID mục tiêu, sau đó gọi service với principal hiện tại. Nếu không muốn trả thông tin về session thuộc người khác, dùng cùng một phản hồi cho reference không tồn tại và reference không thuộc caller.

Khi dùng Spring Session Servlet, `HttpSession.invalidate()` là cách phù hợp để kết thúc session hiện tại trong request đang xử lý. `deleteById` hữu ích khi thu hồi một session từ xa, tức phiên khác với phiên hiện tại. Đối với phiên hiện tại, nên đi qua logout flow/Spring Security hoặc invalidate session được request filter quản lý, tránh xóa repository trực tiếp rồi để filter cuối request lưu lại một bản session đã tải trước đó.

## 8. Endpoint thu hồi với reference riêng

Một controller có thể cung cấp endpoint POST:

```java
@PostMapping("/{reference}/revoke")
ResponseEntity<Void> revoke(
        @PathVariable String reference,
        Authentication authentication) {

    boolean revoked = sessions.revokeByReference(
            authentication.getName(), reference);

    if (!revoked) {
        return ResponseEntity.notFound().build();
    }
    return ResponseEntity.noContent().build();
}
```

Ví dụ giả định service `revokeByReference` kiểm tra reference trong phạm vi principal hiện tại trước khi xóa session. Có thể chọn `404` cho cả reference không tồn tại và không thuộc caller để giảm khả năng dò thông tin; hoặc trả `204` cho thao tác idempotent theo hợp đồng API. Không trả thông báo phân biệt “ID thuộc người khác” với “ID không tồn tại”.

Với xác thực dựa trên cookie, endpoint POST cần CSRF protection. Không dùng GET để xóa session. Cần rate limit thao tác quản lý phiên nếu endpoint có thể bị lạm dụng để tạo tải lên repository.

## 9. Phân biệt thu hồi phiên hiện tại và phiên từ xa

| Trường hợp | Cách xử lý phù hợp |
|---|---|
| Người dùng đăng xuất khỏi trình duyệt hiện tại | Dùng Spring Security logout handler và invalidate `HttpSession` hiện tại |
| Người dùng chọn đăng xuất một thiết bị khác | Xác minh session thuộc principal rồi gọi `SessionRepository.deleteById(sessionId)` |
| Quản trị viên thu hồi phiên của người dùng khác | Kiểm tra quyền quản trị, tenant và audit trước khi xóa |
| Người dùng đăng xuất khỏi mọi thiết bị | Tra principal index rồi thu hồi từng session; xử lý kết quả một phần |
| Session đã hết hạn hoặc không còn tồn tại | Không khôi phục phiên; trả kết quả idempotent theo hợp đồng API |

Khi xóa session từ xa, browser của thiết bị đó có thể vẫn giữ cookie. Server không thể xóa cookie trên thiết bị không nhận response. Tuy nhiên, khi thiết bị gửi lại cookie cũ, repository không được khôi phục session đã bị thu hồi. Ở request tiếp theo, client có thể nhận cookie mới nếu ứng dụng tạo session mới.

## 10. Dữ liệu hiển thị về thiết bị cần được ứng dụng ghi nhận

Spring Session lưu metadata vòng đời như thời điểm tạo, lần truy cập cuối và timeout. Nó không tự xác định một nhãn thiết bị đáng tin cậy. Nếu muốn hiển thị “Chrome trên Windows”, “iPhone” hoặc “Máy tính bảng”, ứng dụng cần trích xuất thông tin phù hợp khi đăng nhập và lưu một snapshot nhỏ vào session.

Ví dụ:

```java
session.setAttribute("login.deviceLabel", normalizedDeviceLabel);
session.setAttribute("login.userAgentFamily", userAgentFamily);
session.setAttribute("login.ipPrefix", maskedIpPrefix);
```

Các giá trị trên chỉ là metadata phục vụ hiển thị và điều tra. User-Agent có thể giả mạo; IP prefix có thể thay đổi. Hạn chế lưu dữ liệu định danh cá nhân, không lưu toàn bộ header request và đặt thời gian lưu phù hợp. Khi thu hồi session, các metadata này sẽ biến mất cùng session nếu không có bản ghi quản lý thiết bị riêng.

Nếu cần lịch sử đăng nhập sau khi session đã bị xóa, hãy lưu audit record riêng trong database nghiệp vụ. Session repository là kho trạng thái đang hoạt động, không phải kho lịch sử kiểm toán.

## 11. Principal index và Spring Security SessionRegistry

Spring Security có `SessionRegistry` để theo dõi các phiên đăng nhập, đặc biệt trong chức năng kiểm soát số phiên đồng thời. Với Spring Session Servlet, `SpringSessionBackedSessionRegistry` là adapter kết nối `SessionRegistry` với `FindByIndexNameSessionRepository`.

Hai hướng API phục vụ các nhu cầu gần nhau nhưng không hoàn toàn giống nhau:

- `FindByIndexNameSessionRepository` tìm session trực tiếp theo principal index và cung cấp session ID cùng dữ liệu `Session`.
- `SessionRegistry` cung cấp mô hình `SessionInformation` mà Spring Security dùng cho concurrent session control, ví dụ xem session và đánh dấu session hết hạn.

Nếu ứng dụng đã dùng Spring Security `maximumSessions(...)`, hãy cân nhắc `SpringSessionBackedSessionRegistry` để SessionRegistry làm việc với Spring Session thay vì bộ nhớ cục bộ. Nếu tự xây trang quản lý phiên, repository indexed thường cung cấp metadata trực tiếp hơn. Tránh duy trì hai registry độc lập không đồng bộ vì có thể hiển thị phiên đã bị thu hồi hoặc bỏ sót phiên được tạo trên node khác.

## 12. Hành vi khi nhiều instance cùng quản lý session

Trong triển khai nhiều node, một session có thể được tạo ở instance A, hiển thị ở B và thu hồi ở C. Để kết quả nhất quán:

- Tất cả instance phải dùng cùng Redis/database và namespace/table.
- Principal index phải được cập nhật trên cùng kho dữ liệu.
- Serializer và class principal phải tương thích giữa các phiên bản đang chạy.
- Các instance không giữ cache session cục bộ mà không có invalidation.
- Endpoint revoke phải xóa session từ kho dùng chung và kiểm tra lại qua node khác.

Nếu dùng Redis indexed repository, index principal được lưu trong Redis. Với JDBC indexed repository, cột `PRINCIPAL_NAME` và index database phục vụ truy vấn. Cấu trúc vật lý khác nhau nhưng API tra cứu theo principal tương tự.

Không dựa vào sticky session để bảo đảm revoke toàn cụm. Sticky session chỉ ảnh hưởng định tuyến; request có thể chuyển node sau restart hoặc failover. Kiểm thử cần chủ động thực hiện revoke ở node A và xác minh ID cũ ở node B.

## 13. Race condition giữa thu hồi và request đang chạy

Một request có thể đã tải session và SecurityContext trước khi một request khác thu hồi session. Khi đó, request đang chạy vẫn có thể giữ bản context trong bộ nhớ đến khi hoàn tất. Xóa session khỏi repository ngăn request mới khôi phục ID cũ, nhưng không tự động hủy mọi request đã bắt đầu.

Một tình huống khác là request đang chạy có thể lưu session ở cuối request sau khi thao tác revoke đã xóa nó. Hành vi cụ thể phụ thuộc repository, flush mode và thời điểm lưu. Vì vậy, cần kiểm thử race này với đúng implementation đang dùng.

Với thao tác nhạy cảm, có thể bổ sung:

- Kiểm tra trạng thái/revocation version ngay trước khi commit nghiệp vụ.
- Dùng version hoặc generation của người dùng để từ chối request đã dùng context cũ.
- Đồng bộ thao tác revoke và ghi nghiệp vụ bằng transaction/locking phù hợp.
- Tránh chạy tác vụ nền dài với SecurityContext đã sao chép mà không kiểm tra lại quyền.

Không nên hứa rằng xóa session lập tức hủy mọi công việc đang chạy. Hãy xác định rõ chính sách: revoke ngăn request mới, đóng kết nối kéo dài, hay cả thao tác đã được xác thực trước đó.

## 14. Sự kiện vòng đời và dọn tài nguyên phụ trợ

Spring Session có thể phát các sự kiện như `SessionDeletedEvent` và `SessionExpiredEvent` khi repository hỗ trợ event. Ứng dụng có thể dùng chúng để đóng WebSocket, xóa dữ liệu phụ trợ hoặc ghi metric. Tuy nhiên, event delivery phụ thuộc implementation và cấu hình; Redis Pub/Sub/keyspace notifications không phải hàng đợi bền vững và listener có thể bỏ lỡ sự kiện khi mất kết nối.

Vì vậy, nguồn quyết định session còn hợp lệ phải là repository, không phải trạng thái listener. Sau khi revoke, request mới phải bị từ chối ngay cả khi một node chưa xử lý xong event đóng WebSocket. Với kết nối kéo dài, cần gắn connection với session ID và có cơ chế broadcast đến node sở hữu connection; một node không thể trực tiếp đóng object socket chỉ tồn tại trong bộ nhớ của node khác.

Listener nên idempotent để event lặp không gây lỗi. Với tác vụ quan trọng cần bảo đảm, dùng outbox hoặc message broker có cơ chế xác nhận và retry phù hợp.

## 15. Bảo vệ endpoint quản lý phiên

Endpoint tra cứu và thu hồi session là endpoint bảo mật cao vì có thể tiết lộ trạng thái đăng nhập hoặc buộc người dùng đăng xuất. Cần:

- Chỉ cho người dùng xem các session của principal hiện tại, trừ endpoint quản trị có quyền riêng.
- Lấy principal từ `Authentication` đã xác thực; không tin principal gửi từ client.
- Kiểm tra session/reference thuộc principal trước khi revoke.
- Dùng POST/DELETE với CSRF protection khi credential được gửi tự động qua cookie.
- Không trả session ID, SecurityContext, credentials hoặc toàn bộ attributes.
- Không đặt session ID trong URL, log, analytics hoặc Referer.
- Che dữ liệu IP/User-Agent và chỉ lưu metadata thật sự cần thiết.
- Audit ai đã thu hồi session nào, lúc nào và từ luồng nào, nhưng không ghi credential thô.
- Rate limit và giám sát các lần tra cứu/xóa bất thường.

Với quản trị viên có quyền thu hồi session của người khác, kiểm tra tenant boundary, quyền hỗ trợ và lý do thao tác. Ghi audit event riêng để điều tra sau này.

## 16. Kiểm thử tra cứu, hiển thị và thu hồi một phiên

Một bộ integration test nên bao phủ cả quyền sở hữu và hành vi repository:

1. Tạo hai session cho principal `alice` và một session cho `bob`.
2. Xác nhận `findByPrincipalName("alice")` chỉ trả hai session của Alice.
3. Tạo DTO hiển thị và xác nhận không có session ID thô, SecurityContext hoặc credentials.
4. Chọn reference của một session Alice và thu hồi; xác nhận service gọi `deleteById` đúng ID đã xác minh.
5. Tra lại index của Alice và xác nhận session mục tiêu không còn, session còn lại vẫn tồn tại.
6. Thử dùng reference của Bob trong request đã xác thực là Alice; xác nhận không xóa session của Bob và phản hồi không tiết lộ sự tồn tại của session đó.
7. Gửi request với cookie cũ tới endpoint được bảo vệ; xác nhận không khôi phục được phiên đã thu hồi.
8. Kiểm thử thu hồi session hiện tại qua logout/invalidate để filter không lưu lại session đã xóa.
9. Chạy revoke trên instance A và xác minh session ID cũ trên instance B.
10. Tạo race giữa request đang chạy và revoke; xác nhận hành vi phù hợp chính sách nghiệp vụ.
11. Kiểm tra event listener và WebSocket/SSE cleanup nếu ứng dụng sử dụng kết nối kéo dài.
12. Kiểm tra audit/log không chứa cookie, session ID hoặc token dạng rõ.

Nên dùng Redis hoặc database cùng loại với production trong integration test. Mock repository chỉ kiểm tra logic service; nó không chứng minh index, TTL, serialization và chia sẻ trạng thái giữa nhiều node hoạt động đúng.

## 17. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Danh sách session rỗng dù người dùng đang đăng nhập | Repository không hỗ trợ index hoặc principal index chưa được tạo | Kiểm tra implementation indexed và `PRINCIPAL_NAME_INDEX_NAME` |
| Không tìm thấy session trên node khác | Namespace, DataSource hoặc Redis/database khác nhau | So sánh cấu hình repository giữa các instance |
| Người dùng có thể revoke session của người khác | Endpoint tin ID do client gửi mà không xác minh ownership | Tra principal index trước khi delete |
| Revoke xong cookie vẫn còn trong browser khác | Server không thể xóa cookie trên thiết bị không nhận response | Xác minh ID cũ bị từ chối ở request kế tiếp |
| Session bị tạo lại sau khi revoke | Request đang chạy lưu bản session đã tải trước đó | Kiểm thử race, dùng invalidate cho current session và cơ chế revocation/version khi cần |
| DTO chứa dữ liệu nhạy cảm | Endpoint trả toàn bộ attributes hoặc dùng session object trực tiếp | Dùng DTO allowlist metadata |
| Thiết bị hiển thị sai | User-Agent/IP được xem như dữ liệu xác thực | Chuẩn hóa metadata và chỉ dùng để tham khảo |
| Event đóng socket không tới node khác | Application event chỉ local hoặc Pub/Sub bị mất | Dùng broadcast phù hợp, idempotency và reconciliation |
| SessionRegistry không đồng bộ | Dùng registry bộ nhớ cục bộ với Spring Session phân tán | Dùng `SpringSessionBackedSessionRegistry` khi cần tích hợp concurrency control |

## 18. Quy trình triển khai

1. Chọn repository hỗ trợ `FindByIndexNameSessionRepository`.
2. Bảo đảm principal name được lưu/index từ SecurityContext đã xác thực.
3. Tạo service chỉ truy vấn theo principal hiện tại hoặc principal đã được phân quyền.
4. Chuyển session thành DTO metadata tối thiểu.
5. Tạo reference quản lý riêng để UI không phải nhận session ID thô.
6. Khi revoke, tra lại các session của principal, xác minh reference/ID thuộc tập đó rồi gọi `deleteById`.
7. Dùng `HttpSession.invalidate()` hoặc Spring Security logout cho session hiện tại.
8. Kiểm tra remember-me và các kết nối kéo dài nếu ứng dụng có sử dụng.
9. Kiểm thử quyền sở hữu, nhiều node, request đồng thời và lỗi repository.
10. Audit thao tác và giám sát số session theo principal, lỗi lookup/revoke và session bị tạo lại ngoài dự kiến.

## 19. Kết luận kỹ thuật

Để quản lý một phiên cụ thể, hãy dùng principal index để xác định tập session thuộc người dùng, sau đó chọn đúng session ID trong tập đó và thu hồi qua repository. `FindByIndexNameSessionRepository` hỗ trợ truy vấn theo principal; `findById` và `deleteById` phục vụ thao tác theo ID. Với session hiện tại, dùng logout flow hoặc `HttpSession.invalidate()` để phối hợp đúng với filter lifecycle.

Giao diện chỉ nên nhận metadata và một reference quản lý riêng, không nhận session ID bearer. Server luôn lấy principal từ SecurityContext, kiểm tra quyền sở hữu trước khi xóa và xác minh request tiếp theo trên một instance khác không còn khôi phục được session cũ. Kết hợp repository dùng chung, kiểm soát quyền, xử lý race và integration test giúp chức năng tra cứu/thu hồi phiên hoạt động an toàn trong hệ thống Spring Session nhiều instance.

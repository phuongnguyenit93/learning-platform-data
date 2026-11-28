# Bảo vệ chức năng quản lý phiên và hạn chế công bố thông tin thiết bị

Chức năng “Thiết bị đang đăng nhập” hoặc “Quản lý phiên” cho phép người dùng xem các phiên còn hoạt động và thu hồi phiên mà họ không nhận ra. Đây là một chức năng nhạy cảm vì nó truy cập danh sách session, có thể kết thúc phiên xác thực và hiển thị thông tin về thiết bị hoặc hoạt động đăng nhập. Nếu endpoint nhận một session ID tùy ý rồi xóa trực tiếp, kẻ tấn công có thể khai thác lỗi IDOR để thao tác lên phiên của người khác. Nếu trả session ID, cookie, địa chỉ IP hoặc User-Agent thô, giao diện quản lý phiên có thể vô tình làm lộ dữ liệu dùng để chiếm quyền hoặc theo dõi người dùng.

Spring Session cung cấp repository dùng chung để tìm và thu hồi session trên nhiều instance Spring. Spring Security xác định principal và quyền truy cập. Ứng dụng phải kết hợp hai phần này để chỉ cho phép người dùng quản lý phiên thuộc danh tính của họ, đồng thời chỉ công bố lượng thông tin thiết bị thực sự cần thiết.

Trong phạm vi `SPRING_SESSION`, bài học này tập trung vào bảo vệ endpoint liệt kê/thu hồi session, chống truy cập chéo người dùng, giữ session ID ở phía server và giảm dữ liệu thiết bị được hiển thị. Mục tiêu là xây dựng chức năng quản lý phiên an toàn khi nhiều máy chủ cùng dùng Redis hoặc JDBC làm session store.

## 1. Mô hình đe dọa của chức năng quản lý phiên

Chức năng quản lý phiên thường có các thao tác:

- Liệt kê những phiên còn hoạt động của tài khoản hiện tại.
- Nhận diện phiên đang dùng trên trình duyệt hiện tại.
- Đổi nhãn thiết bị hoặc xem thời điểm hoạt động gần nhất.
- Thu hồi một phiên cụ thể.
- Đăng xuất khỏi tất cả thiết bị khác.
- Trong một số hệ thống, quản trị viên hỗ trợ người dùng hoặc điều tra phiên đáng ngờ.

Các rủi ro chính:

| Rủi ro | Ví dụ | Tác động |
|---|---|---|
| IDOR / Broken Object Level Authorization | User A gửi session ID thuộc User B tới endpoint revoke | A có thể đăng xuất B hoặc xem thông tin phiên B |
| Session ID disclosure | API trả `HttpSession.getId()` trong JSON | Session ID bị dùng như bearer credential nếu lộ ở log, browser storage hoặc analytics |
| Device fingerprint over-collection | Lưu IP đầy đủ, User-Agent thô, vị trí và đặc điểm trình duyệt không cần thiết | Theo dõi người dùng quá mức, tăng tác động khi dữ liệu bị lộ |
| CSRF | Trình duyệt tự gửi cookie và một trang khác kích hoạt thao tác revoke | Người dùng bị đăng xuất ngoài ý muốn |
| Session enumeration | API cho biết một handle có thuộc tài khoản khác hay không | Kẻ tấn công dò thông tin phiên hoặc tài khoản |
| Quyền quản trị quá rộng | Endpoint nhận principal tùy ý mà không kiểm tra role | Nhân viên hoặc tài khoản bị chiếm có thể thu hồi phiên hàng loạt |
| Revocation không đầy đủ | Xóa Spring Session nhưng quên refresh token hoặc remember-me token riêng | Người dùng vẫn có thể được xác thực qua cơ chế khác |
| Audit log chứa bí mật | Ghi cookie hoặc session ID đầy đủ khi revoke | Log trở thành nguồn rò rỉ credential |

Thiết kế endpoint phải giả định người gọi có thể sửa mọi ID, handle, principal và dữ liệu thiết bị gửi lên. Mọi quyền sở hữu phải được xác định ở server từ `Authentication` đáng tin cậy và repository.

## 2. Chỉ quản lý session của principal hiện tại

Với Spring Session có index theo principal, ứng dụng có thể dùng `FindByIndexNameSessionRepository` để tìm các phiên của một người dùng. Repository trả về map với session ID làm khóa và session làm giá trị.

```java
Map<String, ? extends Session> sessions =
        sessionRepository.findByPrincipalName(principalName);
```

`principalName` phải lấy từ danh tính đã xác thực ở server. Không lấy principal từ query parameter, request body hoặc header do client tự đặt rồi dùng nó để tìm session.

Ví dụ, endpoint self-service nên xác định danh tính như sau:

```java
@GetMapping("/api/me/sessions")
@PreAuthorize("isAuthenticated()")
public List<SessionView> mySessions(
        Authentication authentication,
        HttpServletRequest request) {

    String principalName = principalIdentity(authentication);
    return sessionManagementService.listSessions(
            principalName, request.getSession(false));
}
```

`principalIdentity` là hàm của ứng dụng, trả về định danh canonical đã được dùng khi lập chỉ mục. Với cấu hình đơn giản, giá trị có thể là `authentication.getName()`. Nếu hệ thống hỗ trợ nhiều issuer, tenant hoặc nhiều phương thức đăng nhập, nên ánh xạ về internal user ID ổn định thay vì dùng một username/email có thể thay đổi.

`@PreAuthorize("isAuthenticated()")` là lớp kiểm soát truy cập ban đầu. Service vẫn phải giới hạn truy vấn theo principal đã xác thực; chỉ bảo vệ URL bằng authentication không đủ nếu request có thể chỉ định một người dùng khác.

## 3. Không dùng session ID làm ID công khai

Session ID là một bearer credential: ai sở hữu giá trị hợp lệ có thể gửi nó trong cookie để yêu cầu server khôi phục session. Vì vậy, không đưa session ID vào response API, HTML, URL, log, analytics hoặc thông báo email.

API quản lý phiên nên trả về một handle công khai riêng, ngẫu nhiên và không mang ý nghĩa xác thực. Handle này chỉ dùng để chọn mục trong giao diện; server vẫn phải kiểm tra nó thuộc principal hiện tại trước khi thực hiện thao tác.

Ví dụ DTO an toàn hơn:

```java
public record SessionView(
        String handle,
        String deviceLabel,
        Instant createdAt,
        Instant lastSeenAt,
        boolean current) {
}
```

DTO không có trường `sessionId`, cookie value, CSRF token, `SecurityContext`, authorities hoặc toàn bộ session attributes. `handle` có thể được tạo bằng UUID ngẫu nhiên lúc đăng nhập và lưu trong một session attribute riêng, ví dụ `app.session.public-handle`.

Handle không phải bằng chứng quyền sở hữu. Nếu client gửi handle của phiên khác, server phải tìm trong danh sách session của principal hiện tại và chỉ thao tác nếu tìm thấy handle trong tập đó. Không tìm toàn bộ Redis keyspace theo handle do client cung cấp.

### 3.1. Ví dụ tạo handle khi đăng nhập

Sau khi authentication thành công và session đã được tạo, ứng dụng có thể đăng ký metadata tối thiểu:

```java
public void registerCurrentSession(
        HttpServletRequest request,
        String requestedDeviceLabel) {

    HttpSession session = request.getSession(true);
    if (session.getAttribute("app.session.public-handle") == null) {
        session.setAttribute(
                "app.session.public-handle",
                UUID.randomUUID().toString());
        session.setAttribute(
                "app.session.created-at",
                Instant.now());
    }

    session.setAttribute(
            "app.session.device-label",
            sanitizeDeviceLabel(requestedDeviceLabel));
}
```

Đây là ví dụ cho Servlet stack; gọi nó từ authentication success handler hoặc một bước đăng ký session sau khi danh tính đã được xác minh. Không tạo handle dựa trên session ID và không dùng một giá trị do client gửi làm handle mà không kiểm tra. `sanitizeDeviceLabel` cần giới hạn độ dài, loại bỏ ký tự điều khiển và mã hóa đầu ra khi hiển thị.

Spring Session sẽ lưu các thuộc tính qua repository theo vòng đời request. Nếu ứng dụng dùng custom authentication flow, cần bảo đảm filter order và `SecurityContextRepository` được cấu hình đúng để session, principal index và metadata được lưu trong cùng quy trình.

### 3.2. Handle ngẫu nhiên vẫn cần kiểm tra quyền

UUID khó đoán giúp giảm khả năng dò handle, nhưng không thay thế authorization. Một lỗi IDOR vẫn tồn tại nếu endpoint chỉ kiểm tra handle có hợp lệ về định dạng rồi gọi `deleteById` trên session ID được ánh xạ từ nguồn không được kiểm soát.

Quy tắc bắt buộc: **tra cứu trong phạm vi principal hiện tại, xác nhận handle thuộc một session của principal đó, rồi mới thực hiện thao tác**. Không dùng độ khó đoán của UUID làm ranh giới bảo mật.

## 4. Liệt kê session mà không làm lộ thông tin nhạy cảm

Một màn hình quản lý phiên thường chỉ cần các thông tin:

- Nhãn dễ hiểu như “Chrome trên Windows” hoặc “Điện thoại của tôi”.
- Thời điểm tạo hoặc lần hoạt động gần nhất, có thể hiển thị tương đối.
- Dấu hiệu phiên hiện tại.
- Có thể có loại client ở mức khái quát như browser hoặc mobile app.
- Hành động thu hồi phiên.

Không cần trả về:

- Session ID hoặc cookie value.
- Raw `SecurityContext`, principal object, authorities hoặc authentication details.
- Toàn bộ User-Agent header.
- Địa chỉ IP đầy đủ nếu không có nhu cầu bảo mật rõ ràng.
- Tọa độ, vị trí chính xác hoặc fingerprint trình duyệt chi tiết.
- Tất cả session attributes, CSRF token, refresh token hoặc dữ liệu nghiệp vụ.

Ví dụ service dùng principal index và chỉ tạo DTO:

```java
public List<SessionView> listSessions(
        String principalName,
        HttpSession currentHttpSession) {

    String currentId = currentHttpSession == null
            ? null : currentHttpSession.getId();

    return sessionRepository.findByPrincipalName(principalName)
            .entrySet()
            .stream()
            .map(entry -> {
                Session session = entry.getValue();
                String handle = session.getAttribute(
                        "app.session.public-handle");

                if (handle == null) {
                    return null;
                }

                String label = session.getAttribute(
                        "app.session.device-label");
                Instant createdAt = session.getAttribute(
                        "app.session.created-at");

                return new SessionView(
                        handle,
                        safeLabel(label),
                        createdAt,
                        session.getLastAccessedTime(),
                        entry.getKey().equals(currentId));
            })
            .filter(Objects::nonNull)
            .toList();
}
```

Đây là mẫu cho repository đồng bộ triển khai `FindByIndexNameSessionRepository`; kiểu generic và cách lấy attribute cần khớp phiên bản Spring Session. `entry.getKey()` là session ID chỉ được dùng nội bộ để xác định phiên hiện tại, không được đưa vào `SessionView`. Trong ứng dụng thực tế, nên xử lý session đã hết hạn hoặc metadata thiếu theo cách an toàn và không làm lộ chi tiết repository.

Nếu repository không hỗ trợ principal index, cần một registry riêng được thiết kế và đồng bộ theo lifecycle. Không thay thế index bằng cách quét toàn bộ key Redis trong mỗi request quản lý phiên.

## 5. Hạn chế dữ liệu thiết bị được thu thập

Thông tin thiết bị giúp người dùng nhận ra phiên lạ, nhưng thu thập càng nhiều càng tăng rủi ro riêng tư và hậu quả khi dữ liệu bị lộ.

### 5.1. User-Agent không phải danh tính thiết bị

User-Agent do client gửi, có thể giả mạo hoặc bị giảm chi tiết bởi trình duyệt. Nó không chứng minh một thiết bị cụ thể và không nên dùng làm yếu tố duy nhất để cho phép đăng nhập, bỏ qua MFA hoặc xác nhận phiên quen thuộc.

Nếu cần hiển thị, parse thành thông tin khái quát như:

- Họ trình duyệt: Chrome, Firefox, Safari, Edge hoặc Unknown.
- Họ hệ điều hành: Windows, macOS, Linux, Android, iOS hoặc Unknown.
- Loại thiết bị ở mức tổng quát: desktop, mobile hoặc tablet nếu thư viện nhận diện đủ tin cậy.

Không trả raw header về client. Không dùng toàn bộ User-Agent làm fingerprint ổn định; nó có thể chứa phiên bản, chi tiết thiết bị và thay đổi theo cập nhật trình duyệt.

### 5.2. Địa chỉ IP và vị trí

IP có thể hỗ trợ phát hiện đăng nhập bất thường, nhưng là dữ liệu nhạy cảm theo ngữ cảnh và không định danh chính xác một cá nhân. Người dùng có thể dùng VPN, mạng di động, NAT hoặc proxy khiến IP thay đổi thường xuyên.

Nếu nghiệp vụ thật sự cần lưu IP:

- Xác định mục đích, thời hạn lưu và ai được phép xem.
- Chỉ lấy địa chỉ từ nguồn request đã được cấu hình tin cậy; không tin `X-Forwarded-For` do client tự gửi nếu request không đi qua proxy được tin cậy.
- Cân nhắc rút gọn subnet hoặc dùng HMAC có khóa để so sánh phục vụ phát hiện bất thường, nhưng lưu ý dữ liệu đã băm vẫn có thể là dữ liệu cá nhân.
- Không hiển thị IP đầy đủ trong màn hình self-service nếu chỉ cần dấu hiệu “mạng gần đây” hoặc cảnh báo thay đổi.
- Không suy ra vị trí chính xác từ IP và không hiển thị thành phố/quốc gia nếu độ tin cậy không đủ hoặc không có nhu cầu.

### 5.3. Không xây dựng fingerprint quá mức

Kết hợp canvas, font, độ phân giải, timezone, danh sách plugin và nhiều thuộc tính trình duyệt để tạo fingerprint có thể theo dõi người dùng trên nhiều phiên. Chức năng quản lý phiên thường không cần mức thu thập này.

Ưu tiên metadata tối thiểu do server suy ra từ request lúc đăng nhập, thời điểm tạo, last access và nhãn người dùng tự đặt. Nếu cần phát hiện bất thường, dùng một hệ thống risk assessment có mục đích, retention, quyền truy cập và quy trình giải thích rõ ràng; không biến màn hình quản lý phiên thành công cụ theo dõi chi tiết.

## 6. Nhãn thiết bị do người dùng đặt

Người dùng có thể đặt tên như “Laptop công ty” hoặc “Điện thoại cá nhân”. Đây là dữ liệu đầu vào không đáng tin cậy và phải được xử lý như nội dung do người dùng kiểm soát.

Quy tắc:

1. Giới hạn độ dài, ví dụ 40–80 ký tự theo UI.
2. Loại bỏ ký tự điều khiển và khoảng trắng dư.
3. Không cho phép nhãn chứa markup hoặc script được render như HTML.
4. Mã hóa theo ngữ cảnh khi đưa vào HTML; không dựa riêng vào việc lọc ký tự lúc lưu.
5. Có giá trị mặc định trung tính nếu nhãn trống.
6. Không dùng nhãn để xác thực thiết bị hoặc quyết định quyền.

Ví dụ hàm chuẩn hóa đơn giản:

```java
public String sanitizeDeviceLabel(String input) {
    if (input == null || input.isBlank()) {
        return "Thiết bị chưa đặt tên";
    }

    String normalized = input
            .replaceAll("[\\p{Cntrl}]", "")
            .trim();

    if (normalized.length() > 60) {
        normalized = normalized.substring(0, 60);
    }

    return normalized.isBlank()
            ? "Thiết bị chưa đặt tên" : normalized;
}
```

Hàm trên chỉ chuẩn hóa độ dài và ký tự điều khiển; template/API client vẫn phải escape đầu ra. Không dùng regex này như bộ lọc HTML tổng quát.

## 7. Bảo vệ endpoint liệt kê và thu hồi session

Thiết kế API nên thể hiện rõ phạm vi “của tôi”:

| Endpoint minh họa | Phương thức | Quyền và tác động |
|---|---|---|
| `/api/me/sessions` | `GET` | Người dùng đã xác thực xem phiên của chính họ |
| `/api/me/sessions/{handle}` | `PATCH` | Đổi nhãn một phiên thuộc người dùng hiện tại |
| `/api/me/sessions/{handle}` | `DELETE` | Thu hồi một phiên thuộc người dùng hiện tại |
| `/api/me/sessions/others` | `DELETE` | Thu hồi mọi phiên khác, giữ phiên hiện tại nếu chính sách yêu cầu |
| `/api/admin/users/{userId}/sessions` | `GET`/`DELETE` | Chỉ vai trò hỗ trợ/quản trị được cấp quyền cụ thể |

Các thao tác thay đổi trạng thái không nên dùng GET. Với ứng dụng xác thực bằng cookie session, giữ CSRF protection cho `PATCH`/`DELETE`/`POST`. CORS không thay thế CSRF. Nếu API dùng bearer token không tự động gửi bởi trình duyệt, đánh giá CSRF theo cách credentials được truyền thay vì tắt theo tên gọi “REST API”.

### 7.1. Liệt kê phiên của người dùng hiện tại

Endpoint lấy principal từ `Authentication`:

```java
@GetMapping("/api/me/sessions")
@PreAuthorize("isAuthenticated()")
public List<SessionView> listMySessions(
        Authentication authentication,
        HttpServletRequest request) {
    return service.listSessions(
            principalIdentity(authentication),
            request.getSession(false));
}
```

Client không truyền `principalName`. Điều này tránh một lớp lỗi IDOR phổ biến: endpoint `/api/users/{username}/sessions` vô tình cho phép mọi người dùng đã đăng nhập thay username trong URL.

### 7.2. Thu hồi một phiên theo handle

Service tìm trong danh sách session của principal hiện tại rồi mới xóa:

```java
public boolean revokeOwnSession(
        String principalName,
        String publicHandle,
        String currentSessionId) {

    Map<String, ? extends Session> sessions =
            sessionRepository.findByPrincipalName(principalName);

    for (Map.Entry<String, ? extends Session> entry
            : sessions.entrySet()) {
        Session session = entry.getValue();
        String handle = session.getAttribute(
                "app.session.public-handle");

        if (publicHandle.equals(handle)) {
            String internalSessionId = entry.getKey();

            if (internalSessionId.equals(currentSessionId)) {
                throw new IllegalArgumentException(
                        "Dùng luồng logout hiện tại để kết thúc phiên này");
            }

            sessionRepository.deleteById(internalSessionId);
            return true;
        }
    }

    return false;
}
```

Đây là mẫu Servlet/repository đồng bộ. `internalSessionId` chỉ tồn tại trong server code và không được trả về. Trước khi gọi service, controller lấy principal từ `Authentication` và current session ID từ `request.getSession(false)`. Nếu handle không thuộc principal hiện tại, trả kết quả không tìm thấy hoặc phản hồi thống nhất theo chính sách API; không tiết lộ handle có tồn tại ở tài khoản khác hay không.

`deleteById` xóa session ở repository. Nó không thể xóa cookie khỏi trình duyệt từ xa vì server không kiểm soát response của trình duyệt đó. Cookie cũ có thể vẫn còn, nhưng session ID không còn ánh xạ tới session hợp lệ. Khi trình duyệt gửi cookie cũ, ứng dụng sẽ xử lý như session không tồn tại và có thể phát session mới theo cấu hình.

### 7.3. Thu hồi mọi phiên khác

“Đăng xuất khỏi tất cả thiết bị khác” cần xác định phiên hiện tại một cách nội bộ và giữ nó lại nếu người dùng đang yêu cầu thao tác từ phiên hiện tại:

```java
public int revokeOtherSessions(
        String principalName,
        String currentSessionId) {

    Map<String, ? extends Session> sessions =
            sessionRepository.findByPrincipalName(principalName);

    int revoked = 0;
    for (String sessionId : sessions.keySet()) {
        if (!sessionId.equals(currentSessionId)) {
            sessionRepository.deleteById(sessionId);
            revoked++;
        }
    }
    return revoked;
}
```

Ví dụ chỉ minh họa thao tác đồng bộ và có thể cần xử lý session hết hạn, lỗi repository hoặc race với request khác. Không trả danh sách session ID đã xóa về client. Có thể trả số lượng tổng quát hoặc thông báo thành công mà không tiết lộ dữ liệu thiết bị cụ thể.

Với hành động có tác động lớn như revoke all, yêu cầu xác thực lại gần đây hoặc MFA step-up là phù hợp. Nếu session hiện tại cũng cần kết thúc, dùng logout flow sau khi thao tác thu hồi hoàn tất.

## 8. IDOR và kiểm soát quyền ở server

IDOR xuất hiện khi ứng dụng nhận một định danh đối tượng từ client rồi thao tác mà không kiểm tra quyền sở hữu. Đổi tên tham số từ `sessionId` thành `deviceId` không sửa được lỗi nếu backend vẫn dùng nó để xóa bất kỳ session nào.

Kiểm soát quyền cần được thực hiện ở từng lớp:

1. Endpoint yêu cầu authentication.
2. Principal được lấy từ `SecurityContext` đã xác minh.
3. Repository query chỉ tìm session theo principal đó.
4. Handle phải khớp với một session trong kết quả.
5. Thao tác revoke dùng session ID nội bộ từ entry đã xác minh.
6. Nếu có admin flow, role/permission cụ thể và audit được kiểm tra riêng.

Không viết service dạng:

```java
// Không an toàn: client có thể chỉ định session của người khác.
sessionRepository.deleteById(request.getSessionId());
```

Ngay cả khi endpoint có `@PreAuthorize("isAuthenticated()")`, đoạn code trên vẫn có IDOR. Authentication chỉ xác nhận người gọi đã đăng nhập; nó không xác nhận người gọi sở hữu session ID được gửi lên.

Với endpoint admin, không tái sử dụng logic self-service bằng cách nhận `principalName` tùy ý. Tách rõ service method có quyền quản trị, kiểm tra role như `SESSION_ADMIN`, giới hạn tenant, ghi audit và có thể yêu cầu lý do thao tác. Không cho phép role hỗ trợ xem raw token hoặc cookie.

## 9. CSRF, xác thực lại và giới hạn tốc độ

Vì session cookie thường được trình duyệt gửi tự động, thao tác revoke có thể bị kích hoạt bởi một trang khác nếu không có CSRF protection. Giữ CSRF cho các endpoint thay đổi trạng thái trong ứng dụng browser/session-based.

Các biện pháp bổ sung:

- Yêu cầu CSRF token hợp lệ cho `DELETE`, `PATCH` và `POST`.
- Không thay đổi trạng thái qua `GET`.
- Yêu cầu nhập lại mật khẩu hoặc xác thực MFA gần đây cho “revoke all”, đổi mật khẩu, đổi email bảo mật hoặc thu hồi phiên quản trị.
- Rate-limit endpoint quản lý phiên để giảm dò handle và lạm dụng logout hàng loạt.
- Không phân biệt response quá chi tiết giữa handle không tồn tại và handle thuộc người khác.
- Ghi audit sự kiện revoke với actor, thời điểm, kết quả và lý do, nhưng không ghi session ID/cookie.
- Bảo vệ endpoint bằng HTTPS và cookie flags phù hợp.

CSRF token không thay thế authorization. Một request có CSRF token hợp lệ vẫn phải bị từ chối nếu handle không thuộc principal hiện tại.

## 10. Hạn chế công bố thông tin thiết bị trong API

Thiết kế response theo nguyên tắc dữ liệu tối thiểu. Ví dụ:

```json
{
  "sessions": [
    {
      "handle": "a3a4c8a0-opaque-example",
      "deviceLabel": "Chrome trên Windows",
      "createdAt": "2026-11-20T08:30:00Z",
      "lastSeenAt": "2026-11-26T09:15:00Z",
      "current": true
    }
  ]
}
```

Payload minh họa không chứa session ID, IP đầy đủ, raw User-Agent, cookie, principal ID nội bộ hoặc các thuộc tính session. Dùng nhãn khái quát để người dùng nhận ra thiết bị; tránh cung cấp chi tiết kỹ thuật không cần thiết.

### 10.1. Không trả toàn bộ Session object

Không serialize trực tiếp `Session`, `MapSession`, `WebSession` hoặc `Authentication` thành response JSON. Những object này có thể chứa session ID, attributes nội bộ, dữ liệu xác thực hoặc cấu trúc thay đổi theo phiên bản. Hãy ánh xạ sang DTO allowlist như `SessionView`.

Không trả `session.getAttributes()` rồi hy vọng client chỉ hiển thị vài trường. Việc trả toàn bộ map có thể vô tình làm lộ `SPRING_SECURITY_CONTEXT`, CSRF state, saved request hoặc dữ liệu nghiệp vụ.

### 10.2. Thông tin thời gian

`lastSeenAt` có thể dựa trên `Session.getLastAccessedTime()`. Đây là thời điểm repository ghi nhận lần truy cập theo semantics của nó, không nhất thiết chính xác tới từng request hoặc từng mili giây. Có thể hiển thị “Hoạt động gần đây” thay vì cung cấp timestamp quá chi tiết nếu không cần.

Không nhầm `createdAt` của session với thời điểm người dùng xác thực thành công. Session có thể được tạo trước login bởi request cache hoặc CSRF. Nếu cần thời điểm login, lưu một trường riêng sau authentication success.

## 11. Quản lý principal index và session registry

`FindByIndexNameSessionRepository` hỗ trợ tìm session theo principal name. `SpringSessionBackedSessionRegistry` có thể tích hợp với Spring Security để quản lý giới hạn phiên đăng nhập đồng thời.

Hai mục đích cần được phân biệt:

- **Session inventory:** giao diện cho người dùng xem và thu hồi các phiên của họ.
- **Concurrent session control:** chính sách giới hạn số phiên, từ chối login mới hoặc đánh dấu phiên cũ hết hiệu lực.

`maximumSessions(1)` không tự tạo giao diện thiết bị, không quyết định thông tin nào được hiển thị và không tự giải quyết IDOR ở endpoint quản lý phiên. Ngược lại, một trang session inventory cũng không tự giới hạn số phiên đăng nhập.

Để principal index hoạt động:

1. Dùng indexed repository phù hợp, ví dụ Redis indexed HTTP session hoặc JDBC indexed repository.
2. Đảm bảo `Authentication.getName()` hoặc canonical principal resolver trả cùng giá trị khi ghi và truy vấn.
3. Nếu dùng custom authentication, lưu principal name trong session theo cơ chế được repository/index resolver hỗ trợ.
4. Dùng internal user ID bất biến nếu username/email có thể đổi.
5. Kiểm thử nhiều session cùng principal và session được tạo từ nhiều instance.

Không giả định mọi repository đều hỗ trợ principal index. Nếu implementation chỉ có `SessionRepository` cơ bản, cần thiết kế registry riêng hoặc chọn indexed repository phù hợp.

## 12. Thu hồi session từ xa có giới hạn gì?

Khi ứng dụng gọi `SessionRepository.deleteById(sessionId)`, session được xóa khỏi kho chia sẻ theo semantics của repository. Request tiếp theo dùng cookie cũ sẽ không thể khôi phục session đó. Tuy nhiên, có một số giới hạn:

- Request đã tải `SecurityContext` vào bộ nhớ trước thời điểm revoke có thể tiếp tục chạy tới khi request kết thúc.
- Một giao dịch nghiệp vụ đã commit không bị rollback chỉ vì session bị xóa.
- Cookie session trong trình duyệt từ xa không thể bị server xóa ngay nếu trình duyệt không gửi request nhận header xóa cookie.
- Access token, refresh token, remember-me token hoặc session ở hệ thống identity provider có thể có vòng đời riêng và không tự bị thu hồi chỉ bằng cách xóa Spring Session.
- Cache xác thực riêng của ứng dụng có thể giữ trạng thái cũ nếu không được đồng bộ hoặc invalidated.

Vì vậy, revoke session là biện pháp thu hồi credential session-based. Nếu người dùng chọn “đăng xuất mọi nơi” và ứng dụng còn phát hành refresh token hoặc remember-me token, phải gọi thêm cơ chế thu hồi tương ứng. Với hành động nhạy cảm, kiểm tra trạng thái tài khoản và token revocation ở nguồn dữ liệu chính.

## 13. Không phụ thuộc event listener như một bảo đảm duy nhất

Spring Session có thể phát sự kiện như `SessionDeletedEvent` hoặc `SessionExpiredEvent` tùy repository và cấu hình. Listener hữu ích cho audit, metrics hoặc dọn dữ liệu phụ. Nhưng không nên dựa vào event listener đơn lẻ để bảo đảm revoke có hiệu lực tức thời trên mọi hệ thống.

Nếu cần audit bền vững cho thao tác revoke:

1. Ghi nhận yêu cầu revoke và actor vào audit store có độ bền phù hợp.
2. Thực hiện xóa session qua repository.
3. Ghi kết quả thành công/thất bại và correlation ID.
4. Nếu phải phát thông báo cho hệ thống khác, dùng outbox/queue bền vững hoặc cơ chế retry có idempotency.
5. Không ghi session ID, cookie, CSRF token hoặc serialized attributes vào audit event.

Nếu repository xóa session thành công nhưng event listener lỗi, trạng thái session đã bị thu hồi không nên bị đảo ngược. Listener cần được thiết kế để lỗi hậu kỳ không làm sống lại session.

## 14. Bảo vệ dữ liệu trong audit log và telemetry

Audit log nên trả lời ai đã làm gì, vào lúc nào và kết quả ra sao, không cần chứa credential.

Thông tin có thể ghi:

- User ID nội bộ hoặc subject đã được bảo vệ theo chính sách log.
- Actor: người dùng tự thu hồi hay admin được ủy quyền.
- Hành động: revoke one, revoke others, revoke all.
- Thời điểm, kết quả, lý do và correlation ID.
- Mã handle đã được băm hoặc mã tương quan ngắn hạn nếu cần nối sự kiện, tránh log raw handle nếu handle có thể được dùng để chọn phiên.

Không ghi:

- Session ID hoặc cookie value.
- `Authorization` header, access token hoặc refresh token.
- CSRF token.
- Raw `SecurityContext` hoặc serialized session payload.
- Raw User-Agent/IP nếu không có mục đích, quyền truy cập và retention được xác định.

Metrics nên dùng nhãn có cardinality thấp như action, outcome, repository type và error category. Không dùng session ID, device handle hoặc user ID làm metric label.

## 15. Kiểm thử bảo mật endpoint quản lý phiên

Kiểm thử cần xác minh cả quyền và dữ liệu trả về:

| Trường hợp | Cách kiểm thử | Kết quả mong đợi |
|---|---|---|
| Anonymous list | Gọi GET list khi chưa đăng nhập | Bị yêu cầu xác thực |
| User A list | Tạo session cho A và gọi list bằng A | Chỉ trả các phiên của A |
| User B list | Gọi cùng endpoint bằng B | Không thấy handle hoặc metadata của A |
| IDOR revoke | B gửi handle của A tới endpoint revoke | Không xóa session A; response không tiết lộ quyền sở hữu |
| Handle ngẫu nhiên không tồn tại | Gửi handle không khớp | Không xóa dữ liệu và không làm lộ session khác |
| Raw session ID injection | Thử gửi session ID trong field handle | Không được xem như handle hợp lệ |
| Revoke một phiên khác | A thu hồi handle thuộc một phiên A khác | Session bị xóa; request tiếp theo của phiên đó phải xác thực lại |
| Revoke current | A yêu cầu xóa phiên đang dùng | Chuyển qua logout flow hoặc từ chối theo chính sách rõ ràng |
| Revoke others | A gọi chức năng giữ phiên hiện tại | Các phiên khác bị xóa, phiên hiện tại còn hiệu lực |
| CSRF thiếu/sai | Gửi DELETE/PATCH không có token hợp lệ | Bị từ chối |
| Re-auth/MFA | Revoke all khi xác thực cũ | Yêu cầu step-up theo chính sách |
| Data minimization | Kiểm tra JSON response | Không có session ID, cookie, raw UA, IP hoặc session attributes |
| Output encoding | Đặt device label chứa HTML/script | Hiển thị như text, không thực thi |
| Rate limiting | Gửi nhiều yêu cầu handle ngẫu nhiên | Bị giới hạn và ghi nhận an toàn |
| Multi-instance | Tạo session trên A, list/revoke trên B | Cùng repository và principal index được dùng nhất quán |
| External tokens | Revoke Spring Session khi có refresh token | Token ngoài session được xử lý theo chính sách riêng |

Integration test nên dùng Redis/JDBC thật hoặc Testcontainers và hai application instance. Unit test service không đủ để xác minh principal index, session deletion, cookie và khả năng chia sẻ trạng thái. Dùng test account và dữ liệu giả; không thử revoke trên session production.

## 16. Lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| User có thể revoke session người khác | Backend dùng session ID client gửi mà không kiểm tra principal | Tra cứu theo principal hiện tại rồi xác minh handle thuộc tập kết quả |
| API trả session ID | Serialize trực tiếp Session hoặc dùng entity nội bộ làm DTO | Tạo DTO allowlist, bỏ session ID và credential |
| Màn hình hiển thị IP/UA quá chi tiết | Thu thập raw request headers và trả nguyên dữ liệu | Chỉ lưu/hiển thị metadata khái quát có mục đích |
| Thiết bị được nhận diện sai | Tin User-Agent như định danh chắc chắn | Ghi rõ đây chỉ là nhãn gợi ý, không dùng làm yếu tố xác thực |
| CSRF vẫn có thể kích hoạt revoke | Endpoint dùng cookie session nhưng thiếu CSRF | Bật CSRF cho thao tác thay đổi trạng thái |
| Revoke hiện tại làm request lỗi khó hiểu | Xóa session đang phục vụ request revoke | Dùng logout flow riêng hoặc giữ current session theo semantics rõ ràng |
| Revoke thành công nhưng thiết bị cũ vẫn còn cookie | Server không thể xóa cookie trên browser từ xa | Session server-side đã vô hiệu; xử lý cookie khi browser gửi request kế tiếp |
| Người dùng vẫn truy cập bằng refresh token | Chỉ xóa Spring Session | Thu hồi refresh/remember-me/API tokens ở hệ thống tương ứng |
| Danh sách phiên thiếu session | Principal index chưa được thiết lập hoặc resolver khác nhau | Kiểm tra canonical principal và indexed repository |
| Audit log lộ credential | Ghi request headers/session ID hoặc payload | Redact secret và ghi event tối thiểu |
| Event listener lỗi làm revoke bị báo thất bại | Gộp side effect hậu kỳ vào cùng kết quả mà không phân biệt | Tách trạng thái revoke khỏi xử lý hậu kỳ và dùng outbox khi cần |

## 17. Quy trình triển khai an toàn

Khi xây chức năng quản lý nhiều phiên đăng nhập, thực hiện theo trình tự:

1. Dùng Spring Security xác định principal đã xác thực; chọn canonical user ID ổn định.
2. Dùng indexed Spring Session repository hoặc registry riêng được kiểm thử để tìm session theo principal.
3. Tạo public handle ngẫu nhiên riêng; giữ session ID ở server và không trả ra API.
4. Lưu metadata thiết bị tối thiểu: nhãn, thời điểm tạo, last access và browser/OS family nếu thực sự cần.
5. Không lưu hoặc công bố raw cookie, raw User-Agent, IP đầy đủ hay fingerprint chi tiết nếu không có mục đích rõ ràng.
6. Tạo endpoint `/api/me/...` lấy principal từ `Authentication`, không nhận principal tùy ý từ client.
7. Khi revoke, tìm handle trong danh sách session của principal hiện tại rồi xóa bằng ID nội bộ.
8. Bảo vệ thay đổi bằng CSRF, rate limit và xác thực lại/MFA cho hành động có tác động lớn.
9. Tách self-service khỏi admin operations; kiểm tra quyền quản trị và audit riêng.
10. Thu hồi refresh token, remember-me hoặc credential ngoài Spring Session nếu nghiệp vụ yêu cầu logout mọi nơi.
11. Ghi audit không chứa credential; thiết kế listener và side effect hậu kỳ có thể retry.
12. Kiểm thử IDOR, data minimization, cookie, index, revoke và nhiều instance bằng datastore thật.

Chức năng quản lý phiên an toàn cần bảo vệ cả quyền thao tác lẫn thông tin được hiển thị. Dùng principal từ server, tra cứu session trong phạm vi người dùng đó, giữ session ID nội bộ và chỉ trả handle cùng metadata tối thiểu sẽ giảm nguy cơ IDOR và rò rỉ credential. Khi kết hợp CSRF, step-up authentication, audit có kiểm soát và kiểm thử trên nhiều instance, người dùng có thể nhận diện và thu hồi phiên đáng ngờ mà không biến giao diện thiết bị thành nguồn tiết lộ dữ liệu nhạy cảm.

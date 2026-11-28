# Đổi mật khẩu, nghi ngờ lộ phiên và chính sách thu hồi theo yêu cầu

Đổi mật khẩu và xử lý nghi ngờ lộ session là hai thao tác bảo mật có liên quan nhưng không đồng nhất. Khi mật khẩu thay đổi, ứng dụng cần quyết định những phiên đăng nhập nào tiếp tục được phép dùng. Khi session ID có thể đã bị đánh cắp, chỉ đổi mật khẩu hoặc xóa cookie trên trình duyệt hiện tại chưa đủ: bản sao session ID của kẻ tấn công vẫn có thể được gửi từ một thiết bị khác.

Spring Session giúp quản lý và thu hồi session tập trung qua repository dùng chung như Redis hoặc JDBC. Ứng dụng có thể tra cứu các phiên theo principal, xóa session theo ID và khiến mọi instance từ chối session đã bị thu hồi. Tuy nhiên, thu hồi session không tự động thu hồi mọi credential khác như remember-me token, OAuth2 refresh token, API key hoặc phiên SSO tại Identity Provider.

Bài học này trình bày cách xây dựng quy trình đổi mật khẩu, đánh giá rủi ro lộ phiên, thu hồi một phiên hoặc toàn bộ phiên của tài khoản, xử lý request đang chạy đồng thời, và kiểm thử chính sách thu hồi trong cụm nhiều instance.

## 1. Phân biệt mật khẩu, session và các credential khác

### 1.1. Mật khẩu là credential dùng để xác thực

Mật khẩu thường được dùng tại thời điểm đăng nhập hoặc khi xác minh lại danh tính cho một thao tác nhạy cảm. Máy chủ không nên lưu mật khẩu dạng rõ; chỉ lưu password hash được tạo bởi `PasswordEncoder` phù hợp, có salt và cost factor được cấu hình đúng.

Đổi mật khẩu cập nhật credential gốc của tài khoản. Nó không tự động xóa các session đã được xác thực trước đó, vì session thường lưu `SecurityContext` hoặc thông tin Authentication đã được xác minh. Nếu muốn mọi phiên cũ phải đăng nhập lại, ứng dụng cần chủ động thu hồi các session và credential liên quan.

### 1.2. Session ID là bearer credential

Spring Session thường truyền session ID qua cookie. Client gửi lại ID để repository tìm session. Ai có được session ID hợp lệ có thể thử dùng nó như credential của người dùng, vì vậy cần coi session ID như bí mật.

Session ID có thể bị lộ qua XSS, malware trên thiết bị, log ghi header/cookie, proxy không an toàn, extension trình duyệt hoặc thiết bị dùng chung. `HttpOnly` hạn chế JavaScript đọc cookie, `Secure` yêu cầu HTTPS và `SameSite` giảm một số request cross-site; các thuộc tính này không thu hồi bản sao ID đã bị lấy.

### 1.3. Các credential cần quản lý riêng

| Thành phần | Công dụng | Hành động khi đổi mật khẩu hoặc nghi lộ |
|---|---|---|
| Spring Session ID | Nạp session cục bộ từ Redis/JDBC | Xóa session theo ID hoặc theo principal |
| Remember-me cookie/token | Khôi phục Authentication sau khi session hết hạn | Xóa cookie và thu hồi token server-side nếu có |
| OAuth2 access token | Gọi API thay mặt người dùng | Xem xét revoke; token self-contained có thể còn hiệu lực tới `exp` |
| OAuth2 refresh token | Xin access token mới | Thu hồi tại provider và xóa authorized client |
| API key/personal access token | Xác thực client hoặc tích hợp | Thu hồi key bị ảnh hưởng theo chính sách |
| IdP SSO session | Đăng nhập một lần tại Identity Provider | Thực hiện provider logout/Single Logout nếu yêu cầu |
| Mã khôi phục/MFA device | Khôi phục hoặc xác minh bước hai | Thu hồi hoặc đăng ký lại khi nghi bị chiếm quyền |

Không nên giả định `HttpSession.invalidate()` đã xử lý tất cả các credential trên. Thiết kế logout và password change phải liệt kê rõ từng loại credential mà ứng dụng phát hành hoặc lưu giữ.

## 2. Chính sách thu hồi theo mức độ rủi ro

### 2.1. Đổi mật khẩu chủ động, không có dấu hiệu xâm nhập

Khi người dùng tự đổi mật khẩu sau khi xác minh mật khẩu hiện tại và có thể hoàn thành MFA, sản phẩm có thể chọn một trong các chính sách:

- Giữ session hiện tại nhưng thu hồi tất cả session trên thiết bị khác.
- Thu hồi toàn bộ session, kể cả session hiện tại, rồi yêu cầu đăng nhập lại.
- Giữ một số session tin cậy theo chính sách thiết bị, đồng thời thông báo các phiên còn lại.

Chính sách “giữ phiên hiện tại” cần xoay session ID sau khi xác minh lại danh tính để giảm nguy cơ tiếp tục dùng một ID đã bị lộ trước thao tác đổi mật khẩu. Phải kiểm tra rằng request tiếp theo dùng ID mới và ID cũ không còn nạp được.

### 2.2. Đặt lại mật khẩu bởi quản trị viên hoặc quy trình recovery

Khi quản trị viên đặt lại mật khẩu hoặc người dùng dùng email/SMS recovery, thường không thể giả định thiết bị hiện tại đáng tin cậy. Chính sách an toàn hơn là:

1. Cập nhật password hash.
2. Tăng credential/session version của tài khoản.
3. Thu hồi mọi Spring Session của principal.
4. Thu hồi remember-me token và refresh token theo khả năng của hệ thống.
5. Yêu cầu MFA hoặc xác thực lại khi đăng nhập lại.
6. Gửi thông báo bảo mật tới kênh liên hệ đã xác minh.

### 2.3. Nghi ngờ session ID bị đánh cắp

Nếu phát hiện session ID xuất hiện từ IP/thiết bị bất thường, cookie bị lộ trong log hoặc người dùng báo có hoạt động không nhận ra, nên xem session đó là đã bị xâm phạm. Tùy mức độ chắc chắn:

- Nếu xác định được session ID bị ảnh hưởng: thu hồi ID đó ngay.
- Nếu không xác định được ID nào bị lộ: thu hồi toàn bộ session của principal.
- Nếu nghi ngờ tài khoản hoặc thiết bị bị chiếm quyền: thu hồi thêm remember-me, refresh token, API key và yêu cầu xác minh MFA.
- Nếu có dấu hiệu chiếm quyền IdP: thực hiện quy trình provider logout và recovery tương ứng.

Không chờ session tự hết TTL khi đã có dấu hiệu credential bị lộ. TTL chỉ giới hạn thời gian sống thông thường; nó không thay thế thao tác thu hồi khẩn cấp.

### 2.4. Ma trận quyết định

| Sự kiện | Phạm vi session khuyến nghị | Credential khác | Yêu cầu bổ sung |
|---|---|---|---|
| Người dùng đổi mật khẩu bình thường | Thu hồi phiên khác; có thể giữ phiên hiện tại sau re-auth và đổi ID | Xóa/đổi remember-me theo chính sách | Thông báo đổi mật khẩu |
| Quản trị viên reset mật khẩu | Thu hồi mọi session | Thu hồi remember-me và refresh token nếu có | Yêu cầu MFA/re-auth |
| Một session ID bị nghi lộ | Thu hồi session ID đó ngay | Kiểm tra token gắn với session | Điều tra nguồn rò rỉ |
| Không biết session nào bị lộ | Thu hồi mọi session theo principal | Thu hồi token dài hạn liên quan | Cảnh báo bảo mật và kiểm tra hoạt động |
| Tài khoản bị chiếm quyền | Thu hồi toàn bộ session và credential do ứng dụng quản lý | Revoke refresh token/API key; xem xét IdP logout | Recovery có xác minh mạnh |

Chính sách cuối cùng phải phù hợp với mức độ rủi ro, trải nghiệm người dùng và yêu cầu tuân thủ của sản phẩm. Điều quan trọng là chính sách được định nghĩa trước và có thể kiểm thử, thay vì mỗi endpoint tự quyết định phạm vi thu hồi.

## 3. Xác minh lại danh tính trước khi đổi mật khẩu

### 3.1. Yêu cầu mật khẩu hiện tại

Một session đang đăng nhập không phải bằng chứng đủ mạnh cho mọi thao tác nhạy cảm. Với đổi mật khẩu, nên yêu cầu người dùng nhập mật khẩu hiện tại và so sánh với hash đã lưu bằng `PasswordEncoder.matches`.

```java
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;

@Service
public class PasswordVerificationService {

    private final PasswordEncoder passwordEncoder;
    private final UserRepository users;

    public PasswordVerificationService(
            PasswordEncoder passwordEncoder,
            UserRepository users) {
        this.passwordEncoder = passwordEncoder;
        this.users = users;
    }

    public void verifyCurrentPassword(String userId, String currentPassword) {
        String storedHash = this.users.findPasswordHashById(userId)
            .orElseThrow(UserNotFoundException::new);
        if (!this.passwordEncoder.matches(currentPassword, storedHash)) {
            throw new InvalidCurrentPasswordException();
        }
    }
}
```

Các repository và exception trong ví dụ là thành phần của ứng dụng. Không trả về hash hoặc chi tiết tài khoản trong response. Cần rate limit lần xác minh thất bại và ghi nhận sự kiện bảo mật mà không log mật khẩu.

### 3.2. Step-up authentication và MFA

Với thao tác có rủi ro cao, có thể yêu cầu xác thực lại gần đây hoặc MFA, ví dụ TOTP, passkey hoặc security key. Ứng dụng nên ghi thời điểm và mức assurance của lần xác thực gần nhất trong `Authentication`/session theo cách phù hợp với mô hình bảo mật.

Không chỉ kiểm tra rằng người dùng đã đăng nhập từ nhiều giờ trước. Nếu session có thể bị đánh cắp, attacker cũng có thể dùng session đó để gọi endpoint đổi mật khẩu. Step-up authentication giúp yêu cầu thêm một bằng chứng độc lập.

### 3.3. Bảo vệ endpoint đổi mật khẩu

Endpoint đổi mật khẩu thường phải:

- Yêu cầu authenticated user và kiểm tra quyền thay đổi chính tài khoản đó.
- Dùng POST/PUT và giữ CSRF protection khi xác thực dựa trên cookie.
- Kiểm tra mật khẩu hiện tại hoặc step-up authentication.
- Kiểm tra chính sách mật khẩu mới và không cho tái sử dụng mật khẩu cũ theo quy định sản phẩm.
- Rate limit và chống dò mật khẩu.
- Không nhận `userId` tùy ý để đổi mật khẩu tài khoản khác nếu caller không có quyền quản trị phù hợp.
- Ghi audit event, nhưng không ghi mật khẩu hoặc password hash.

## 4. Cập nhật password hash và credential version

### 4.1. Lưu password hash mới

Sau khi xác minh mật khẩu hiện tại, ứng dụng tạo hash mới bằng `PasswordEncoder.encode`. Không tự hash bằng SHA-256 hoặc thuật toán nhanh không có salt/cost phù hợp.

```java
String newHash = passwordEncoder.encode(newPassword);
userRepository.updatePasswordHash(userId, newHash);
```

Đây là đoạn minh họa thao tác lưu. Cần thực hiện trong transaction database và bảo đảm password policy đã được kiểm tra trước khi cập nhật.

### 4.2. Tăng `credentialVersion` hoặc `sessionVersion`

Chỉ xóa session theo danh sách hiện tại vẫn có thể bỏ sót session được tạo đồng thời hoặc request đang xử lý. Một cách tăng độ chắc chắn là lưu số phiên bản credential trên bản ghi user:

```text
USER
  id
  password_hash
  credential_version
  password_changed_at
```

Khi mật khẩu đổi hoặc có sự cố bảo mật, cập nhật password hash và tăng `credential_version` trong cùng transaction. Khi một session được tạo sau xác thực, lưu giá trị version hiện tại vào session, ví dụ `AUTH_CREDENTIAL_VERSION`.

Ở mỗi request được bảo vệ, ứng dụng so sánh version trong session với version hiện tại của tài khoản. Nếu không khớp, session phải bị từ chối và invalidate. Đây là một cơ chế thu hồi theo thế hệ credential: mọi session được tạo trước lần tăng version trở thành stale, kể cả khi việc xóa hàng loạt session chưa hoàn tất.

Ví dụ logic kiểm tra (mã giả ở mức service/filter):

```java
boolean isCredentialVersionCurrent(Session session, User user) {
    Integer sessionVersion = session.getAttribute("AUTH_CREDENTIAL_VERSION");
    return sessionVersion != null
        && sessionVersion.equals(user.getCredentialVersion());
}
```

Không dùng tên thuộc tính nội bộ của Spring Security để chứa version nếu chưa xác định rõ vòng đời và serializer. Có thể dùng một key riêng do ứng dụng quản lý. Nếu phiên bản không có hoặc không đọc được, xử lý theo hướng fail closed đối với endpoint yêu cầu xác thực.

### 4.3. Chi phí kiểm tra version

Đọc user row ở mỗi request có thể tăng tải database. Các lựa chọn gồm cache version với thời hạn ngắn, cache invalidation qua message bus hoặc kiểm tra tại gateway. Tuy nhiên, cache có thể làm thu hồi chậm nếu node chưa nhận invalidation.

Nếu yêu cầu là thu hồi gần như tức thời, phải xác định rõ độ trễ tối đa được chấp nhận và dùng nguồn version có tính nhất quán phù hợp. Không tuyên bố thu hồi tức thời nếu cache cho phép một session cũ tiếp tục được chấp nhận trong vài phút.

## 5. Tìm và thu hồi session theo principal

### 5.1. Yêu cầu repository hỗ trợ principal index

`FindByIndexNameSessionRepository` cung cấp API tra cứu session theo principal. `RedisIndexedSessionRepository` và `JdbcIndexedSessionRepository` là các repository hỗ trợ principal index. Redis repository cơ bản không cung cấp cùng khả năng indexed.

Principal phải được ghi đúng vào session, thường thông qua `PrincipalNameIndexResolver` đọc `SecurityContext` hoặc thuộc tính `FindByIndexNameSessionRepository.PRINCIPAL_NAME_INDEX_NAME`. Nếu ứng dụng dùng authentication tùy chỉnh, hãy kiểm tra rằng giá trị principal được lưu nhất quán trên mọi instance.

### 5.2. Thu hồi tất cả session của một principal

Ví dụ service thu hồi các session hiện có:

```java
import java.util.Map;

import org.springframework.session.FindByIndexNameSessionRepository;
import org.springframework.session.Session;
import org.springframework.stereotype.Service;

@Service
public class SessionRevocationService {

    private final FindByIndexNameSessionRepository<? extends Session> sessions;

    public SessionRevocationService(
            FindByIndexNameSessionRepository<? extends Session> sessions) {
        this.sessions = sessions;
    }

    public int revokeAllForPrincipal(String principalName) {
        Map<String, ? extends Session> found =
            this.sessions.findByPrincipalName(principalName);

        int revoked = 0;
        for (String sessionId : found.keySet()) {
            this.sessions.deleteById(sessionId);
            revoked++;
        }
        return revoked;
    }
}
```

Ví dụ này minh họa API và phạm vi thu hồi. Trong production, cần xử lý lỗi từng lần xóa, đo số session thực sự bị xóa và có cơ chế retry/đối soát. Không trả session ID cho client hoặc ghi ID thô vào audit log.

### 5.3. Thu hồi một session cụ thể

Khi đã xác định session ID nghi bị lộ, có thể gọi:

```java
sessionRepository.deleteById(compromisedSessionId);
```

Trước khi xóa, cần xác minh session đó thuộc principal mục tiêu và caller có quyền thu hồi. Không cho phép client gửi session ID tùy ý để xóa phiên của người khác. Với thao tác quản trị, nên dùng một session reference nội bộ thay cho raw session ID.

### 5.4. Khi repository không hỗ trợ principal lookup

Nếu repository không triển khai `FindByIndexNameSessionRepository`, không thể giả định `findByPrincipalName` có sẵn. Có thể duy trì một bảng ánh xạ principal-session riêng hoặc nâng cấp/chọn repository có principal index. Bảng ánh xạ phải được cập nhật khi session tạo, đổi principal, logout, timeout và bị thu hồi.

Không quét toàn bộ keyspace Redis hoặc toàn bộ bảng session trên mỗi lần đổi mật khẩu. Cách đó không mở rộng tốt và có thể gây tải đột biến.

## 6. Xóa session ngay hay đánh dấu hết hạn?

### 6.1. `deleteById` và invalidate

Khi cần thu hồi session bị nghi lộ, xóa trực tiếp khỏi repository là cách thể hiện rõ mục tiêu: request sau đó không thể nạp session theo ID cũ. Với session hiện tại, `HttpSession.invalidate()` đi qua tích hợp Spring Session để xóa phiên trong kho.

```java
HttpSession current = request.getSession(false);
if (current != null) {
    current.invalidate();
}
```

Cookie ở trình duyệt hiện tại cần được hết hạn trong response. Với thiết bị từ xa, server không thể trực tiếp xóa cookie trong browser của thiết bị đó; việc xóa session phía server khiến cookie cũ không còn dùng được.

### 6.2. `SessionInformation.expireNow()` khác xóa session

Trong Spring Security concurrent-session control, `SessionInformation.expireNow()` đánh dấu session là expired. `ConcurrentSessionFilter` kiểm tra marker ở request kế tiếp, gọi logout handlers và xử lý session hết hạn. Đây là cơ chế phù hợp cho giới hạn số phiên đồng thời.

Đối với nghi ngờ lộ session ID, không nên chỉ đánh dấu expired rồi chờ request tiếp theo. Nếu session bị đánh cắp và attacker không gửi request nữa, marker có thể vẫn còn trong kho. Dùng `SessionRepository.deleteById` hoặc invalidate session để thu hồi trực tiếp; nếu cần, kết hợp credential version để chặn request đang chạy.

### 6.3. SessionRegistry không phải lúc nào cũng là kho dữ liệu

`SessionRegistryImpl` mặc định giữ thông tin trong memory của một instance. Với nhiều node, nó có thể không biết session được tạo ở node khác. `SpringSessionBackedSessionRegistry` dựa vào `FindByIndexNameSessionRepository` để chia sẻ thông tin session.

Tuy vậy, `SessionRegistry.removeSessionInformation` không nên được xem là API thay thế `SessionRepository.deleteById`. Khi cần xóa dữ liệu session thực sự, thao tác trực tiếp với repository hoặc invalidate `HttpSession`.

## 7. Xử lý request đang chạy đồng thời với thu hồi

### 7.1. Vì sao xóa session chưa đủ trong mọi race condition?

Giả sử request A đã nạp session vào đầu request. Trong khi A đang chạy, quản trị viên đổi mật khẩu và xóa session khỏi Redis/JDBC. Nếu request A tiếp tục sửa thuộc tính rồi lưu session ở cuối request, tùy repository và timing, thao tác ghi có thể cạnh tranh với thao tác xóa. Một request đã được xác thực trước thời điểm thu hồi cũng có thể tiếp tục thực hiện nghiệp vụ.

Do đó, “đã gọi `deleteById`” không nhất thiết có nghĩa mọi request đang chạy đã bị dừng ngay tại thời điểm đó. Cần thiết kế thêm kiểm tra credential version hoặc kiểm tra trạng thái tài khoản ở điểm thực hiện nghiệp vụ nhạy cảm.

### 7.2. Kiểm tra version tại ranh giới nghiệp vụ

Với thao tác như chuyển tiền, đổi email, tạo API key hoặc thay đổi quyền, kiểm tra trạng thái credential gần thời điểm commit nghiệp vụ. Nếu version session khác version user hiện tại, từ chối thao tác và yêu cầu xác thực lại.

Với nghiệp vụ cần bảo đảm mạnh, đặt kiểm tra version trong cùng transaction hoặc cơ chế concurrency control với thay đổi dữ liệu nghiệp vụ. Chỉ kiểm tra ở đầu request có thể để lại khoảng trống nếu credential bị thu hồi sau bước kiểm tra.

### 7.3. Cập nhật password và version nguyên tử

Password hash và credential version nên được cập nhật trong cùng transaction:

```sql
UPDATE APP_USER
SET PASSWORD_HASH = ?,
    CREDENTIAL_VERSION = CREDENTIAL_VERSION + 1,
    PASSWORD_CHANGED_AT = CURRENT_TIMESTAMP
WHERE USER_ID = ?;
```

Sau khi transaction commit, các request mới có thể thấy version mới. Session cũ mang version trước đó sẽ bị từ chối ngay khi kiểm tra. Việc xóa hàng loạt session trong Redis/JDBC có thể chạy sau commit và retry nếu gặp lỗi.

Nếu session repository dùng Redis còn user table dùng JDBC, hai kho không nằm trong cùng một transaction ACID. Hãy coi credential version là hàng rào bảo mật chính; xóa session là bước dọn dẹp và giảm dữ liệu tồn tại. Có thể dùng transactional outbox để phát yêu cầu thu hồi sau commit, tránh mất công việc nếu tiến trình dừng giữa chừng.

### 7.4. Idempotency và retry

Xóa một session ID nhiều lần nên được xử lý an toàn. Thu hồi toàn bộ session của principal cũng cần idempotent: retry không tạo trạng thái sai. Ghi nhận số session tìm thấy, số session đã xóa, số lỗi và lần đối soát cuối.

Không retry vô hạn trên request đồng bộ. Với lượng session lớn, tạo tác vụ nền có trạng thái và tiến độ, nhưng credential version phải chặn session cũ ngay cả khi job chưa xóa hết.

## 8. Thu hồi remember-me và token dài hạn

### 8.1. Persistent remember-me

Nếu dùng `PersistentTokenBasedRememberMeServices`, token được lưu qua `PersistentTokenRepository`. Khi đổi mật khẩu hoặc nghi lộ tài khoản, có thể gọi `removeUserTokens(username)` để thu hồi token remember-me của người dùng, đồng thời xóa cookie trên trình duyệt hiện tại qua logout handler.

Nếu dùng token-based remember-me stateless, cookie có chữ ký phụ thuộc thông tin người dùng và key cấu hình. Đổi password hash có thể làm token cũ không còn hợp lệ tùy implementation, nhưng vẫn cần xóa cookie hiện tại và kiểm thử hành vi đúng với phiên bản Spring Security.

### 8.2. OAuth2 authorized client

Nếu ứng dụng lưu authorized client, xóa credential khỏi `OAuth2AuthorizedClientService` theo registration ID và principal khi chính sách yêu cầu. Việc xóa bản ghi local ngăn ứng dụng dùng lại token từ kho của nó, nhưng không tự thu hồi access token đã phát cho resource server.

Nếu provider có OAuth2 Token Revocation endpoint, gọi endpoint đó để thu hồi refresh token hoặc access token theo chính sách provider. Resource server có thể tiếp tục chấp nhận JWT self-contained cho tới `exp` nếu không có introspection hoặc denylist.

### 8.3. API key, personal token và thiết bị tin cậy

Ứng dụng nên quản lý API key/personal access token bằng ID và trạng thái revocation riêng. Khi nghi lộ tài khoản, có thể thu hồi toàn bộ token hoặc chỉ token phát hành trong khoảng thời gian bị ảnh hưởng. Thiết bị tin cậy và MFA recovery code cũng cần quy trình xoay vòng riêng.

## 9. Kiểm toán và thông báo bảo mật

### 9.1. Ghi audit event

Các sự kiện nên được ghi nhận:

- Password changed by user.
- Password reset by administrator hoặc recovery flow.
- Session revoked by user, administrator hoặc automated risk engine.
- Account marked as compromised.
- Remember-me token revoked.
- Refresh token/API key revoked.
- Failed re-authentication hoặc MFA challenge.

Audit record có thể gồm user ID nội bộ, thời điểm UTC, actor, nguồn yêu cầu, lý do, số session bị thu hồi và correlation ID. Không ghi mật khẩu, password hash, raw session ID, access token, refresh token hoặc toàn bộ cookie.

### 9.2. Thông báo người dùng

Sau đổi mật khẩu hoặc thu hồi do nghi lộ, thông báo qua kênh đã xác minh. Nội dung nên nói rõ thời điểm và loại hành động, kèm hướng dẫn nếu người dùng không thực hiện. Không gửi thông tin nhạy cảm hoặc session identifier trong email/SMS.

### 9.3. Giữ bằng chứng điều tra

Khi nghi bị xâm nhập, có thể cần giữ audit trail, IP/UA đã chuẩn hóa, device reference và mốc thời gian trước khi dọn dữ liệu phụ. Việc giữ bằng chứng không có nghĩa giữ session credential đang có nguy cơ sử dụng. Hãy tách log điều tra khỏi dữ liệu xác thực đang hoạt động.

## 10. Kiểm thử chính sách thu hồi

### 10.1. Kiểm thử thu hồi một session

1. Đăng nhập cùng một tài khoản trên hai client A và B.
2. Xác minh repository tìm thấy cả hai session theo principal.
3. Xóa session ID của A bằng `deleteById`.
4. Xác minh `findById(idA)` trả `null`.
5. Gửi request từ A với cookie cũ; ứng dụng yêu cầu xác thực lại.
6. Xác minh B vẫn hoạt động nếu chính sách chỉ thu hồi một session.

### 10.2. Kiểm thử thu hồi toàn bộ principal

1. Tạo nhiều session cho cùng principal qua nhiều instance.
2. Gọi `findByPrincipalName` và thu hồi tất cả ID tìm thấy.
3. Xác minh mọi ID cũ không còn được repository nạp.
4. Gửi request cũ tới từng instance; không request nào được xác thực bằng session cũ.
5. Xác minh session mới sau khi đăng nhập lại dùng credential version mới.

### 10.3. Kiểm thử race condition

1. Bắt đầu request A và giữ request ở một điểm sau khi session đã được nạp.
2. Từ request B, đổi mật khẩu, tăng credential version và thu hồi session.
3. Cho request A tiếp tục tới điểm cập nhật nghiệp vụ.
4. Xác minh A bị từ chối nếu version đã cũ; không được commit thao tác nhạy cảm.
5. Kiểm tra session không thể được tái sử dụng nếu request A cố lưu trạng thái cũ.
6. Lặp lại khi một instance restart và khi Redis/JDBC tạm thời lỗi.

### 10.4. Kiểm thử remember-me và token

Kiểm tra cookie remember-me bị xóa, persistent token không còn được chấp nhận, authorized client local đã bị xóa và provider revocation được gọi đúng khi cấu hình. Test riêng trường hợp provider không khả dụng để bảo đảm local session vẫn bị thu hồi.

### 10.5. Kiểm thử nhiều instance

Chạy ít nhất hai instance cùng repository:

- Đăng nhập ở A, thu hồi ở B.
- Gửi request với cookie cũ tới A và B.
- Xác minh cả hai đều từ chối session.
- Tạo session mới sau đổi mật khẩu và kiểm tra credential version.
- Ngắt một instance khỏi Redis/JDBC trong lúc revoke, khôi phục kết nối và chạy đối soát.

Không chỉ kiểm tra response logout ở node đã nhận yêu cầu. Mục tiêu là chứng minh session cũ không thể được sử dụng ở bất kỳ node nào.

## 11. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Đổi mật khẩu nhưng phiên cũ vẫn dùng được | Chỉ cập nhật password hash, chưa thu hồi session | Xóa session theo principal hoặc tăng credential version |
| Chỉ logout thiết bị hiện tại | Chỉ invalidate `HttpSession` hiện tại | Dùng principal index để tìm và thu hồi các phiên khác |
| Kẻ tấn công vẫn dùng session ID cũ | Cookie ở thiết bị attacker không bị xóa từ xa | Xóa session phía server và kiểm tra credential version |
| `findByPrincipalName` trả rỗng | Repository không hỗ trợ index hoặc principal chưa được ghi | Kiểm tra repository type và `IndexResolver` |
| Session bị đánh dấu expired nhưng vẫn còn trong kho | `SessionInformation.expireNow()` chỉ đặt marker chờ filter xử lý | Dùng `deleteById` cho thu hồi trực tiếp |
| Request đang chạy vẫn hoàn tất sau revoke | Request đã nạp Authentication/session trước khi thu hồi | Kiểm tra credential version tại ranh giới nghiệp vụ và commit |
| Session cũ xuất hiện lại sau khi xóa | Request đồng thời có thể lưu session đã nạp trước đó | Dùng version fencing, idempotent revoke và kiểm thử save/delete race |
| Remember-me đăng nhập lại sau logout | Token/cookie remember-me chưa bị thu hồi | Gọi `RememberMeServices.logout`, xóa persistent tokens |
| API token vẫn gọi được sau khi xóa session | Token độc lập với Spring Session | Thu hồi token tại kho/provider và kiểm tra thời hạn access token |
| Chỉ một node thấy trạng thái revoke | Dùng registry local hoặc namespace khác nhau | Dùng repository chung, cùng namespace và version |
| Job revoke thất bại giữa chừng | Không có retry/đối soát hoặc không lưu tiến độ | Dùng outbox/job bền vững; credential version chặn session cũ |

## 12. Quy trình xử lý sự cố nghi lộ session

Khi nhận cảnh báo hoặc báo cáo session bị lộ, thực hiện theo trình tự có kiểm soát:

1. Xác định principal và phạm vi thời gian có thể bị ảnh hưởng.
2. Thu thập session reference, thiết bị, IP và sự kiện liên quan từ audit log; không phát tán raw session ID.
3. Nếu biết chính xác ID, thu hồi session đó ngay; nếu không chắc phạm vi, thu hồi toàn bộ session của principal.
4. Tăng credential/session version để chặn session cũ và request mới dùng version lỗi thời.
5. Nếu tài khoản có nguy cơ bị chiếm quyền, buộc đổi mật khẩu hoặc recovery với MFA.
6. Thu hồi remember-me token, refresh token, API key và credential dài hạn liên quan.
7. Xem xét provider logout nếu IdP SSO session cũng có nguy cơ.
8. Kiểm tra mọi instance từ chối session cũ và không có request nhạy cảm đang tiếp tục với credential stale.
9. Ghi audit event, thông báo người dùng và giữ bằng chứng cần thiết.
10. Đối soát các session còn tồn tại sau khi job revoke hoàn tất.

## 13. Quy trình đổi mật khẩu an toàn

Một luồng đổi mật khẩu tiêu chuẩn có thể gồm:

1. Xác thực người dùng hiện tại và yêu cầu mật khẩu cũ hoặc step-up MFA.
2. Kiểm tra CSRF, rate limit và password policy.
3. Tạo password hash mới bằng `PasswordEncoder`.
4. Trong transaction, cập nhật password hash, `passwordChangedAt` và tăng `credentialVersion`.
5. Sau commit, thu hồi session theo chính sách: mọi phiên hoặc mọi phiên trừ phiên hiện tại.
6. Nếu giữ phiên hiện tại, xoay session ID và cập nhật credential version trong session.
7. Thu hồi remember-me token và refresh token theo chính sách.
8. Ghi audit event và gửi thông báo bảo mật.
9. Kiểm thử request cũ, request mới và request đồng thời trên nhiều instance.

Nếu database user và session store khác nhau, không giả định có transaction phân tán bao trùm cả hai. Tăng credential version trong transaction user là hàng rào chặn session cũ; việc xóa session có thể được retry bằng outbox hoặc job bền vững.

## Tài liệu tham khảo

- [Spring Session — Spring Security Integration](https://docs.spring.io/spring-session/reference/spring-security.html)
- [Spring Session API — FindByIndexNameSessionRepository](https://docs.spring.io/spring-session/reference/api/java/org/springframework/session/FindByIndexNameSessionRepository.html)
- [Spring Session API — SessionRepository](https://docs.spring.io/spring-session/reference/api/java/org/springframework/session/SessionRepository.html)
- [Spring Security — Password Storage](https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html)
- [Spring Security — Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html)
- [Spring Security — Remember-Me Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/rememberme.html)
- [Spring Security — Logout](https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html)
- [OAuth 2.0 Token Revocation — RFC 7009](https://www.rfc-editor.org/rfc/rfc7009)

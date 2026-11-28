# ASVS session management

## 1. Dùng ASVS để biến quản lý phiên thành yêu cầu kiểm chứng được

OWASP Application Security Verification Standard (ASVS) đưa ra các yêu cầu có thể dùng để thiết kế và kiểm tra kiểm soát bảo mật ứng dụng. Với session management, mục tiêu là duy trì liên hệ đáng tin cậy giữa những request và người dùng đã xác thực, đồng thời chấm dứt liên hệ đó đúng lúc.

Một ứng dụng không đạt mục tiêu này chỉ bằng việc đăng nhập được. Nếu token cũ còn hoạt động sau logout, phiên được gia hạn vô hạn hoặc nhân viên đã bị vô hiệu hóa vẫn gọi được API, vòng đời phiên đang có vấn đề.

Bài học lấy **ASVS 5.0.0** làm mốc. Quản lý phiên nằm tại **V7 — Session Management**; cookie liên quan đến V3, còn self-contained token liên quan đến V9. Cần ghi cả phiên bản khi dẫn mã yêu cầu, tránh nhầm với cách đánh số của ASVS 4.x. Nguồn chuẩn là [ASVS 5.0.0 — V7 Session Management](https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x16-V7-Session-Management.md).

Mức xác minh L1/L2/L3 của ASVS không phải AAL1/AAL2/AAL3 của NIST. Một bộ kiểm tra session management cũng không tự chứng minh ứng dụng đã đáp ứng toàn bộ ASVS ở một mức nhất định.

## 2. Xác định chính xác “phiên” đang được quản lý

Trong một hệ thống IAM, người dùng có thể đồng thời sở hữu nhiều đối tượng:

- Cookie tham chiếu đến phiên web tại ứng dụng.
- Phiên đăng nhập tại IdP của doanh nghiệp.
- Access token để gọi API.
- Refresh token dùng để xin access token mới.
- Phiên trên một trình duyệt hoặc thiết bị khác.

Chúng có thể liên quan nhưng không phải cùng một đối tượng. Logout một phiên web không tự động xóa phiên IdP; thu hồi refresh token không tự động làm access token đã phát hành mất hiệu lực.

Ví dụ, cổng hợp đồng dùng cookie cho giao diện web và access token cho một dịch vụ tài liệu. Khi người dùng bấm logout, nếu backend chỉ xóa cookie thì token đã sao chép trước đó vẫn có thể tiếp tục được dùng ở dịch vụ tài liệu.

Trước khi lựa chọn giải pháp, cần lập danh sách nơi tạo, lưu, xác minh và chấm dứt từng loại phiên hoặc token. Với SSO, phải bao gồm cả RP và IdP. Phạm vi này là cơ sở để hiểu logout hiện tại, logout mọi thiết bị và logout toàn hệ sinh thái có ý nghĩa gì.

## 3. Một số yêu cầu ASVS cần đối chiếu

Bảng sau chọn các điểm trọng tâm; diễn giải ngắn không thay thế yêu cầu đầy đủ trong bản chuẩn:

| ASVS 5.0.0 | Trọng tâm |
| --- | --- |
| V7.1.1–V7.1.3 | Tài liệu về timeout, phiên đồng thời và phối hợp SSO |
| V7.2.1–V7.2.2 | Backend tin cậy xác minh token; token phiên được tạo động |
| V7.2.3 | Reference token dùng CSPRNG, có ít nhất 128 bit entropy |
| V7.2.4 | Token mới khi xác thực hoặc xác thực lại; token hiện tại chấm dứt |
| V7.3.1–V7.3.2 | Thực thi inactivity timeout và absolute lifetime |
| V7.4.1–V7.4.2 | Chấm dứt phiên có hiệu lực; vô hiệu hóa tài khoản chấm dứt mọi phiên |
| V7.4.3–V7.4.5 | Quản lý phiên sau thay đổi yếu tố xác thực, logout và thu hồi bởi quản trị viên |
| V7.5.1–V7.5.3 | Xác thực lại cho thay đổi nhạy cảm và quản lý phiên |
| V7.6.1–V7.6.2 | Tái xác thực trong federation và hành động tạo phiên có chủ ý |

Các yêu cầu có mức áp dụng khác nhau. Chẳng hạn, V7.5.1 ở L2 yêu cầu xác thực lại đầy đủ trước khi sửa thuộc tính ảnh hưởng xác thực. Không nên thay yêu cầu này bằng việc người dùng chỉ đang có một cookie hợp lệ.

## 4. Tạo token phiên và chống session fixation

Với reference token, trình duyệt giữ một giá trị khó đoán; backend dùng nó để tìm bản ghi phiên. Giá trị token không nên là user ID, timestamp, email hoặc chuỗi tăng dần.

Ví dụ Java sau tạo một giá trị ngẫu nhiên 256 bit, vượt ngưỡng entropy tối thiểu nêu ở V7.2.3:

```java
import java.security.SecureRandom;
import java.util.Base64;

public final class SessionTokenGenerator {
    private static final SecureRandom RANDOM = new SecureRandom();

    private SessionTokenGenerator() {
    }

    public static String generate() {
        byte[] value = new byte[32];
        RANDOM.nextBytes(value);
        return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(value);
    }
}
```

Đoạn mã chỉ minh họa sinh reference token, chưa phải một hệ thống session management. Còn cần xử lý lưu trữ, ràng buộc tài khoản, timeout, cookie, thu hồi và kiểm tra quyền.

Session fixation xảy ra khi kẻ tấn công khiến nạn nhân dùng một token mà kẻ tấn công đã biết, rồi token đó tiếp tục được dùng sau đăng nhập. Vì vậy, không nâng một phiên tiền đăng nhập thành phiên đã xác thực bằng cách chỉ thêm `userId` mà giữ nguyên token.

Một hành trình phù hợp cần tạo token mới sau xác thực, kết thúc token cũ và chỉ chuyển tiếp dữ liệu tiền đăng nhập được phép. Xác thực lại cũng cần xử lý vòng đời token tương ứng. Khi thay token, phải tránh việc request đồng thời vô tình làm token cũ hoạt động trở lại.

## 5. Cookie bảo vệ cách truyền token, không thay thế kiểm soát backend

Một cookie phiên minh họa:

```http
Set-Cookie: __Host-session=<opaque-session-token>; Path=/; Secure; HttpOnly; SameSite=Lax
```

Trong cấu hình này:

- `Secure` giới hạn gửi cookie qua kết nối an toàn.
- `HttpOnly` ngăn JavaScript đọc trực tiếp cookie qua các API thông thường.
- `SameSite` giới hạn một số trường hợp gửi cookie trong ngữ cảnh khác site.
- Tiền tố `__Host-` đi cùng `Secure`, `Path=/` và không có thuộc tính `Domain`.

Giá trị SameSite phải phù hợp hành trình thực tế, nhất là callback SSO. Không áp dụng một giá trị duy nhất mà chưa kiểm tra luồng liên kết danh tính. Các yêu cầu cookie cụ thể nằm trong [ASVS 5.0.0 — V3.3 Cookie Setup](https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x12-V3-Web-Frontend-Security.md#v33-cookie-setup).

HttpOnly không khiến ứng dụng miễn nhiễm với XSS: mã độc vẫn có thể thực hiện thao tác bằng phiên của nạn nhân. SameSite cũng không thay thế toàn bộ cơ chế chống CSRF. Các request thay đổi trạng thái cần được bảo vệ theo kiến trúc, chẳng hạn bằng anti-CSRF token và kiểm tra nguồn phù hợp. Xem [OWASP CSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html).

Không truyền session token trong URL, log, thông báo lỗi hoặc dữ liệu analytics. Nếu một giá trị cho phép sử dụng phiên, phải coi nó là bí mật ngay cả khi nó không chứa dữ liệu cá nhân.

## 6. Phân biệt inactivity timeout và absolute lifetime

**Inactivity timeout** giới hạn khoảng thời gian không có hoạt động được chấp nhận. **Absolute lifetime** giới hạn tổng thời gian của một phiên kể cả khi người dùng liên tục hoạt động.

Ví dụ chính sách giả định cho cổng hợp đồng:

```yaml
sessionPolicy:
  idleTimeoutMinutes: 15
  absoluteLifetimeHours: 8
  maxConcurrentSessions: 3
  onConcurrentLimitReached: REJECT_NEW_SESSION
```

Các con số là minh họa, không phải thời hạn ASVS bắt buộc cho mọi ứng dụng. Doanh nghiệp cần chọn theo rủi ro, yêu cầu nghiệp vụ và tiêu chuẩn áp dụng.

Nếu người dùng đăng nhập lúc 08:00, hoạt động cuối lúc 09:00 rồi không làm gì thêm, phiên sẽ hết hạn theo idle timeout. Nếu họ vẫn làm việc liên tục, phiên vẫn phải chạm giới hạn tuyệt đối đã đặt. Việc đổi cookie hoặc làm mới access token không được vô tình xóa giới hạn này khi chưa có sự kiện xác thực lại hợp lệ theo chính sách.

Backend phải quyết định hết hạn, không dựa vào đồng hồ JavaScript hoặc việc giao diện tự chuyển trang. Mỗi request được bảo vệ cần được kiểm tra với trạng thái phiên phía tin cậy.

Cũng cần định nghĩa hoạt động nào cập nhật `lastActivityAt`. Nếu một tab tự polling mỗi phút luôn làm mới idle timer, người dùng đã rời máy có thể không bao giờ được coi là không hoạt động. Có thể tách hoạt động nền và hoạt động người dùng trong chính sách, nhưng không tin một timestamp do client tự gửi.

## 7. Logout và thu hồi phải làm credential cũ mất tác dụng

Một logout hiệu quả thường gồm hai phần: chấm dứt khả năng sử dụng phiên ở backend và xóa credential tương ứng ở client. Chỉ điều hướng về màn hình đăng nhập không hoàn thành việc này.

Với phiên stateful, backend có thể xóa hoặc đánh dấu bản ghi phiên đã thu hồi. Request tiếp theo dùng token cũ phải bị từ chối, kể cả khi người gửi tự khôi phục cookie.

Với self-contained token, dịch vụ chỉ kiểm tra chữ ký và `exp` sẽ không biết rằng người dùng vừa logout. Cần một cơ chế làm việc chấm dứt có hiệu lực, chẳng hạn tra cứu trạng thái phiên, denylist theo token/session hoặc so sánh phiên bản thu hồi của tài khoản.

Một thiết kế nội bộ có thể dùng `sessionEpoch`:

```text
Account:
    id
    state
    currentSessionEpoch

Session:
    accountId
    sessionEpoch
    createdAt
    lastActivityAt
    revokedAt
```

Khi cần kết thúc mọi phiên, backend tăng `currentSessionEpoch`; phiên mang epoch cũ không còn hợp lệ. Đây chỉ là phương án nếu mọi nơi chấp nhận credential đều kiểm tra giá trị hiện hành hoặc cơ chế thu hồi tương đương.

Nếu một API vẫn chỉ xác minh JWT độc lập và bỏ qua trạng thái thu hồi, việc tăng epoch ở nơi khác không bảo vệ API đó. Cache, độ trễ truyền sự kiện và các service trung gian cần được xét trong cùng thiết kế.

Token có thời hạn ngắn làm giảm cửa sổ rủi ro nhưng không tự thỏa mãn yêu cầu chấm dứt ngay khi một sự kiện termination đã được kích hoạt. Các kiểm tra về chữ ký, thuật toán, thời gian và audience của self-contained token còn được nêu riêng ở [ASVS 5.0.0 — V9 Self-contained Tokens](https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x18-V9-Self-contained-Tokens.md).

## 8. Quản lý nhiều phiên và thay đổi yếu tố xác thực

Một người có thể dùng laptop, điện thoại và một trình duyệt khác. Chính sách cần xác định số phiên cho phép và hành vi khi chạm giới hạn: từ chối phiên mới, yêu cầu người dùng lựa chọn phiên cần kết thúc hoặc xử lý theo quy tắc được công bố.

Không chỉ hiển thị danh sách thiết bị. Backend cần có định danh phiên riêng để thu hồi đúng mục tiêu. Nếu mọi thiết bị dùng chung một token, việc kết thúc một phiên riêng lẻ sẽ khó thực hiện đáng tin cậy.

Theo V7.4.3, ứng dụng cần cung cấp tùy chọn kết thúc các phiên khác sau khi thay đổi hoặc loại bỏ yếu tố xác thực thành công. Tổ chức có thể áp dụng chính sách nghiêm hơn cho sự kiện rủi ro cao, nhưng cần phân biệt yêu cầu tiêu chuẩn với lựa chọn nội bộ.

V7.5.2 yêu cầu người dùng có thể xem và, sau khi xác thực lại bằng ít nhất một yếu tố, kết thúc các phiên đang hoạt động. Chức năng này phải kiểm tra rằng người dùng đang thu hồi phiên của chính mình, tránh biến màn hình quản lý phiên thành một lỗi truy cập chéo tài khoản.

Khi tài khoản bị vô hiệu hóa hoặc xóa, mọi phiên đang hoạt động phải bị chấm dứt. “Không cho đăng nhập mới” nhưng cho phiên cũ tiếp tục gọi API chưa xử lý xong sự kiện nghỉ việc.

## 9. Thay đổi nhạy cảm cần xác thực lại phù hợp

Một session token bị đánh cắp có thể vẫn hợp lệ về chữ ký và thời gian. Nếu chỉ cần token đó để thay email khôi phục, số điện thoại hoặc MFA, kẻ tấn công có thể biến việc chiếm phiên tạm thời thành kiểm soát tài khoản lâu dài.

Vì vậy, cần phân biệt:

- Có một phiên đang hoạt động.
- Có bằng chứng xác thực lại đủ mới và đủ mạnh cho hành động hiện tại.
- Có quyền thực hiện hành động đó trên đúng tài nguyên.

Ví dụ, một nhà thầu đang đọc hợp đồng không nên được thay thông tin khôi phục chỉ vì cùng phiên đó vẫn truy cập được trang hồ sơ. Hành trình thay đổi cần kiểm chứng lại theo yêu cầu áp dụng, rồi mới ghi thay đổi.

Không coi việc phát hành token mới là bằng chứng người dùng vừa xác thực lại. Trường `iat` của token mới có thể chỉ phản ánh lúc refresh; nó không nhất thiết là thời điểm xác thực người dùng.

Xác thực lại cũng không thay thế phân quyền. Người vừa hoàn thành MFA vẫn không có quyền quản trị tài khoản của người khác nếu chính sách không cho phép.

## 10. Phối hợp phiên ứng dụng và phiên SSO

Trong SSO, RP và IdP có thể giữ phiên độc lập. Cần mô tả rõ quan hệ giữa chúng:

- Khi RP hết hạn, IdP có thể tái sử dụng phiên cũ trong điều kiện nào?
- Khi người dùng logout ở RP, có kết thúc phiên IdP không?
- Khi IdP vô hiệu hóa tài khoản, RP nhận biết và chấm dứt phiên ra sao?
- Khi nghiệp vụ đòi hỏi xác thực lại, RP kiểm chứng độ mới của sự kiện như thế nào?

Ví dụ, RP hết absolute lifetime sau tám giờ nhưng lập tức chuyển sang IdP rồi nhận phản hồi dựa trên phiên cũ, không có bằng chứng xác thực lại cần thiết. Nếu chính sách yêu cầu người dùng thực sự xác thực lại, chu trình redirect này chưa đáp ứng mục tiêu.

Với OIDC, RP có thể dùng các cơ chế như yêu cầu giới hạn tuổi sự kiện xác thực và kiểm tra `auth_time` cùng ngữ cảnh do IdP trả về. Cách yêu cầu và kiểm tra phải bám đặc tả, không suy ra từ một trang “đăng nhập thành công”. Xem [OIDC Core — Authentication Request và ID Token Validation](https://openid.net/specs/openid-connect-core-1_0.html#AuthRequest).

Cũng cần một hành động hoặc sự đồng ý rõ ràng để tạo phiên mới theo V7.6.2. Sau logout, không nên âm thầm tái tạo phiên ứng dụng chỉ vì trình duyệt vẫn giữ phiên SSO.

## 11. Ví dụ kiểm tra phiên tại backend

Mã giả sau minh họa reference token và epoch thu hồi. Nó không thay thế framework bảo mật hoặc một thiết kế lưu trữ hoàn chỉnh:

```text
authenticateRequest(request, now):
    rawToken = readSessionCookie(request)
    require rawToken exists

    session = sessionStore.lookupByTokenDigest(hash(rawToken))
    require session exists
    require session.revokedAt is absent

    account = accountStore.lookup(session.accountId)
    require account.state == ACTIVE
    require session.sessionEpoch == account.currentSessionEpoch

    require now < session.createdAt + policy.absoluteLifetime
    require now < session.lastActivityAt + policy.idleTimeout

    if qualifiesAsUserActivity(request):
        sessionStore.touchIfStillValid(session.id, now)

    return AuthenticatedContext(
        account.id,
        session.id,
        session.lastAuthenticatedAt
    )
```

Backend tiếp tục kiểm tra quyền trên từng thao tác. Không đưa `ALLOW_ALL` vào ngữ cảnh chỉ vì phiên hợp lệ.

Hàm `touchIfStillValid` nhấn mạnh rằng cập nhật hoạt động không được khôi phục phiên vừa bị thu hồi hoặc đã hết hạn. Với request đồng thời, cần dùng thao tác lưu trữ thích hợp để việc cập nhật timestamp không ghi đè trạng thái termination.

Lưu digest của reference token là một lựa chọn thiết kế để hạn chế việc lộ giá trị sử dụng được khi kho phiên bị đọc trái phép. Nó không thay thế entropy đủ lớn, bảo vệ kho dữ liệu hoặc kiểm soát truy cập.

Nếu kho trạng thái không truy cập được, hệ thống cần hành vi lỗi đã thiết kế. Không chuyển sang tin cookie một cách vô điều kiện để duy trì khả năng truy cập.

## 12. Chuyển yêu cầu thành tình huống nghiệm thu

Các tình huống sau là ví dụ xây dựng tiêu chí kiểm tra, không phải kết quả một cuộc đánh giá đã chạy:

| Tình huống | Cách quan sát | Kết quả mong đợi |
| --- | --- | --- |
| Đăng nhập từ phiên tiền xác thực | Ghi nhận token trước và sau, thử token cũ | Token mới được cấp; token cũ không truy cập được |
| Logout | Giữ bản sao token rồi gọi lại endpoint được bảo vệ | Backend từ chối token đã chấm dứt |
| Hết idle timeout | Không có hoạt động hợp lệ đủ lâu rồi gửi request | Không tiếp tục dùng phiên như trước |
| Chạm absolute lifetime | Duy trì hoạt động rồi vượt giới hạn | Yêu cầu xác thực lại theo chính sách |
| Vô hiệu hóa tài khoản | Dùng phiên còn mở trên nhiều thiết bị | Mọi phiên không còn được sử dụng |
| Thay yếu tố xác thực | Kiểm tra tùy chọn kết thúc phiên khác và thử lại các phiên đó | Các phiên đã chọn bị thu hồi có hiệu lực |
| Gọi qua nhiều instance | Thực hiện termination ở instance A, dùng token tại B | Không vượt qua kiểm soát nhờ đổi instance |
| Sửa email khôi phục | Thử thao tác chỉ bằng một phiên cũ | Hành trình yêu cầu xác thực lại phù hợp |
| Hết phiên RP nhưng IdP còn phiên | Kiểm tra sự kiện xác thực thực tế tại IdP | Không coi redirect hoặc refresh là xác thực lại |

Bằng chứng nên gồm yêu cầu và phiên bản chuẩn, phạm vi endpoint, cấu hình liên quan, request/response đã che bí mật và kết quả kỳ vọng. Nếu chỉ kiểm tra trang HTML nhưng bỏ qua API, chức năng tải tài liệu hoặc WebSocket, phạm vi kiểm tra có thể còn thiếu.

Hướng dẫn thực hành bổ sung có trong [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html). Tiêu chuẩn nêu điều cần kiểm chứng; đội phát triển cần xác định cơ chế và bằng chứng phù hợp với ứng dụng của mình.

## 13. Nhật ký và vận hành phiên

Nên theo dõi sự kiện tạo phiên, xoay token, xác thực lại, hết hạn, logout và thu hồi bởi quản trị viên. Mỗi sự kiện cần đủ ngữ cảnh để điều tra chủ thể, phiên và nguyên nhân, nhưng không lưu token nguyên vẹn.

Một mã tham chiếu phiên dùng trong log nên khác giá trị bearer mà client sử dụng. Hạn chế dữ liệu thiết bị và vị trí ở mức cần thiết; không thu thập thêm dữ liệu cá nhân chỉ vì màn hình quản lý phiên có thể hiển thị chúng.

Đối với các kết nối dài như WebSocket, phải xác định termination ảnh hưởng kết nối đang mở ra sao. Chỉ kiểm tra cookie lúc bắt tay rồi bỏ qua thay đổi trạng thái tài khoản có thể khiến kênh tiếp tục tồn tại ngoài vòng đời phiên mong muốn.

Cũng cần xét tác vụ đã bắt đầu trước khi thu hồi. Các thao tác nhạy cảm có thể cần kiểm tra lại tại thời điểm thực hiện hoặc commit, tránh để quyết định từ một request cũ trở thành quyền vô thời hạn.

## 14. Tình huống tự kiểm tra

Một ứng dụng có cookie Secure và HttpOnly, JWT hết hạn sau một giờ, nút logout xóa cookie và giao diện quay về trang đăng nhập. Nhân viên bảo mật giữ lại JWT trước logout và tiếp tục gọi được API tải hợp đồng.

Kiểm soát trình duyệt đang hoạt động một phần, nhưng việc chấm dứt phiên chưa có hiệu lực ở nơi chấp nhận JWT. Cần xác định toàn bộ credential của phiên và thiết kế thu hồi được thực thi tại API, đồng thời kiểm tra lại bằng token cũ sau termination.

Trong tình huống khác, backend thu hồi phiên đúng nhưng một nhân viên bị xóa khỏi dự án vẫn đọc được hợp đồng bằng một phiên khác còn hoạt động. Vấn đề lúc này còn liên quan đến vòng đời quyền và kiểm tra tài nguyên. Quản lý phiên phải phối hợp với RBAC, ABAC, tenant và trạng thái tài khoản để quyền truy cập thực tế luôn phản ánh chính sách hiện hành.

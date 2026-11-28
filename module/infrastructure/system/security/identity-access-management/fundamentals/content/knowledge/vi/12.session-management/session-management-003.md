# Session secret — Bí mật duy trì phiên xác thực

## 1. Session secret giải quyết vấn đề gì?

Sau khi người dùng xác thực, ứng dụng thường cần nhận ra họ trong các request tiếp theo mà không yêu cầu nhập lại mật khẩu hoặc thực hiện MFA cho từng lần tải dữ liệu. Session secret là bí mật giúp phần mềm của người dùng tiếp tục chứng minh rằng request thuộc một phiên đã được thiết lập.

NIST mô tả tính liên tục của phiên dựa trên việc sở hữu session secret do session host cấp khi xác thực và có thể làm mới trong phiên. Bí mật có thể được trình trực tiếp hoặc được chứng minh quyền sở hữu bằng cơ chế mật mã. [Nguồn: NIST SP 800-63B-4, Session Bindings](https://pages.nist.gov/800-63-4/sp800-63b.html#session-bindings).

Ví dụ phổ biến là cookie chứa một giá trị ngẫu nhiên mà server ánh xạ tới phiên của tài khoản. Nếu server chỉ yêu cầu đưa đúng giá trị này, nó hoạt động như một **bearer credential**: bên nào giữ được giá trị có thể sử dụng nó trong phạm vi phiên còn được chấp nhận.

Vì vậy, mất bí mật phiên có thể dẫn đến chiếm phiên ngay cả khi mật khẩu chưa bị lộ. Session secret phải được quản lý như thông tin xác thực, không như một mã theo dõi có thể thoải mái đưa vào log hoặc URL.

Sau bài học, người học cần phân biệt các loại bí mật liên quan đến phiên, giải thích cách tạo và kiểm tra bí mật phiên, đồng thời xác định những nơi phải bảo vệ nó trong vòng đời IAM.

## 2. Phân biệt bí mật phiên với khóa ký và các token khác

Tên gọi dễ gây nhầm vì một số thư viện dùng biến cấu hình như `SESSION_SECRET` để chỉ khóa phía server. Cần đọc hợp đồng của thư viện cụ thể, thay vì suy luận chỉ từ tên biến.

| Giá trị | Ai giữ hoặc sử dụng? | Vai trò |
| --- | --- | --- |
| Session secret của một phiên | Client và thành phần xác minh phiên, tùy mô hình lưu | Chứng minh quyền tiếp tục sử dụng phiên đó |
| Session ID dùng làm bearer token | Client gửi lại; server tra phiên | Trong mô hình này, chính session ID là bí mật phiên |
| Mã phiên nội bộ phục vụ quản trị | Server và công cụ được phép | Tham chiếu bản ghi; không nhất thiết đủ để đăng nhập |
| Khóa ký cookie hoặc JWT | Thành phần ký; bên xác minh giữ khóa thích hợp | Chống sửa hoặc giả mạo dữ liệu token, không phải giá trị cấp riêng cho từng phiên |
| CSRF token | Client và server theo cơ chế chống CSRF | Bảo vệ yêu cầu thay đổi trạng thái, không tự thay thế xác thực phiên |
| Refresh token | Client hoặc backend theo kiến trúc OAuth | Xin token mới theo quyền được cấp; có vòng đời và cơ chế thu hồi riêng |

Trong một phiên dùng cookie opaque, giá trị cookie không cần chứa tên người dùng hoặc quyền. Server giữ ý nghĩa của nó. Một kiến trúc khác có thể dùng cookie mang dữ liệu đã ký; khi đó toàn bộ giá trị được trình có thể vẫn là bearer credential, còn khóa ký là bí mật khác nằm ở server.

Lộ một cookie thường ảnh hưởng phiên tương ứng. Lộ khóa ký dùng chung có thể cho phép giả mạo nhiều token thuộc phạm vi khóa đó. Hai sự cố cần cách xác định phạm vi và thu hồi khác nhau.

## 3. Mô hình opaque session secret

Xét một cổng nhân sự giả định dùng session store phía server:

```text
1. Người dùng hoàn tất các bước xác thực cần thiết
                         ↓
2. Server tạo bí mật phiên ngẫu nhiên và bản ghi phiên
                         ↓
3. Trình duyệt nhận bí mật qua cookie được bảo vệ
                         ↓
4. Request tiếp theo gửi cookie về đúng dịch vụ
                         ↓
5. Server kiểm tra phiên, trạng thái tài khoản và quyền truy cập
```

Bản ghi phiên có thể giữ các dữ liệu sau:

```text
internal_session_id
secret_verifier
account_id
tenant_id
created_at
last_activity_at
absolute_expires_at
authentication_time
authentication_context
status
security_version
```

Đây là mô hình minh họa, không phải schema bắt buộc. `internal_session_id` phục vụ tham chiếu quản trị; `secret_verifier` phục vụ kiểm tra bí mật do client trình. Trong mô hình này, API không được chấp nhận mã quản trị nội bộ thay cho bí mật phiên.

Không sử dụng một biến `authenticated=true` do trình duyệt gửi để thay thế bản ghi này. Không cho request tự chọn `account_id`, `tenant_id` hoặc mức MFA của phiên chỉ bằng cách sửa một trường trong body.

## 4. Khó đoán đến từ nguồn ngẫu nhiên, không từ cách trang trí chuỗi

Bí mật phiên cần được tạo bằng nguồn ngẫu nhiên mật mã. Timestamp, số thứ tự tăng dần, email ghép ngày hoặc giá trị từ bộ sinh ngẫu nhiên không dành cho mật mã đều không thích hợp để làm phần bí mật.

Base64, hex và mã hóa URL là cách biểu diễn dữ liệu. Chúng không bổ sung entropy cho dữ liệu đầu vào. Một bộ đếm được Base64 vẫn là bộ đếm có thể dự đoán được nếu đối thủ hiểu cách tạo.

Trong ví dụ của bài, nhóm phát triển chọn sinh 32 byte ngẫu nhiên bằng CSPRNG rồi biểu diễn bằng Base64url không padding. Không gian biểu diễn tương ứng có tối đa `2^256` giá trị; độ khó dự đoán thực tế vẫn phụ thuộc chất lượng và độ an toàn của bộ sinh.

Nếu giả sử các giá trị phân bố đều, có `n` phiên hợp lệ và đối thủ thử `q` giá trị độc lập, một ước lượng xác suất đoán trúng khi xác suất còn rất nhỏ là:

```text
P ≈ q × n / 2^b

b: số bit ngẫu nhiên của phần bí mật
n: số giá trị hợp lệ mà một phép thử có thể trúng
q: số lần thử
```

Đây là mô hình minh họa tấn công đoán, không phải dự báo toàn bộ rủi ro chiếm phiên. Một bí mật có entropy cao vẫn bị sử dụng lại ngay nếu bị chụp nguyên giá trị trong log.

OWASP khuyến nghị ưu tiên cơ chế session của framework; nếu phải tự sinh session ID, dùng CSPRNG với kích thước ít nhất 128 bit và bảo đảm tính duy nhất. [Nguồn: OWASP Session Management Cheat Sheet, Session ID Content](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html#session-id-content-or-value).

## 5. Ví dụ Java: chỉ minh họa bước sinh bí mật

Java cung cấp `SecureRandom` cho việc sinh số ngẫu nhiên mật mã. Không tự seed nó bằng thời gian hiện tại hoặc một hằng số dễ đoán. [Nguồn: Java SE 21 — SecureRandom](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/SecureRandom.html).

```java
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.Base64;

public final class SessionSecretGenerator {
    private static final SecureRandom RANDOM = new SecureRandom();
    private static final Base64.Encoder ENCODER =
            Base64.getUrlEncoder().withoutPadding();

    private SessionSecretGenerator() {
    }

    public static String generate() {
        byte[] bytes = new byte[32];
        RANDOM.nextBytes(bytes);
        try {
            return ENCODER.encodeToString(bytes);
        } finally {
            Arrays.fill(bytes, (byte) 0);
        }
    }
}
```

Kết quả là chuỗi Base64url dài 43 ký tự cho 32 byte đầu vào. Không gọi `println`, không ghi log giá trị trả về và không đưa nó vào response JSON dành cho màn hình quản trị phiên.

Việc xóa mảng `bytes` chỉ xóa mảng do đoạn mã này sở hữu. Chuỗi kết quả vẫn tồn tại trong bộ nhớ và có thể có bản sao do framework tạo; không được xem `Arrays.fill(...)` là bằng chứng rằng bí mật đã biến mất hoàn toàn khỏi tiến trình.

Đoạn mã không triển khai session store, cookie, kiểm tra hết hạn hoặc thu hồi. Trong ứng dụng thực tế, ưu tiên session manager của framework với cấu hình phù hợp; không thay toàn bộ cơ chế có sẵn chỉ để dùng ví dụ sinh chuỗi này.

Mỗi phiên phải có bí mật riêng. Không lấy một khóa cấu hình dùng chung rồi phát chính khóa đó cho mọi người dùng, cũng không sinh một giá trị mới khi ứng dụng khởi động rồi dùng nó cho mọi phiên.

## 6. Bảo vệ bí mật tại session store

Nếu session store giữ nguyên bearer token, người có quyền đọc store có thể lấy token chưa hết hạn và trình nó cho ứng dụng. Mã hóa ổ đĩa không ngăn một tài khoản đã được cấp quyền đọc dữ liệu đó.

Khi cần giảm hậu quả của việc lộ bản sao chỉ đọc, một thiết kế có thể lưu verifier một chiều thay cho token thô. Với bí mật được sinh ngẫu nhiên có entropy cao, có thể sử dụng hash thích hợp; yêu cầu này khác bài toán mật khẩu do con người chọn, vốn cần hàm băm mật khẩu chuyên dụng. OWASP mô tả cách lưu verifier và giới hạn bảo vệ của nó. [Nguồn: OWASP, Server-Side Session Token Storage](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html#server-side-session-token-storage).

Ví dụ khái niệm cho toàn bộ token opaque:

```text
Khi cấp phiên:
    rawSecret = sinh ngẫu nhiên
    verifier = SHA-256(biểu diễn đã quy định của rawSecret)
    lưu verifier cùng dữ liệu phiên
    gửi rawSecret cho client qua cookie

Khi nhận request:
    nhận rawSecret từ cơ chế được chấp nhận
    kiểm tra định dạng và giới hạn độ dài
    tính lại verifier theo cùng quy tắc
    tìm bản ghi phiên tương ứng
    kiểm tra trạng thái và giới hạn phiên trước khi sử dụng
```

Không lưu cả `rawSecret` và hash của nó trong cùng bản ghi dự phòng. API cũng không được cho phép client trình hash đã lưu để đăng nhập; nếu không, hash lại trở thành bearer credential có thể sử dụng trực tiếp.

Một thiết kế khác tách public lookup ID và phần secret. Khi đó phải sinh phần secret độc lập và xác minh đầy đủ; lookup ID riêng lẻ không đủ chứng minh quyền sử dụng phiên. Nếu đối chiếu verifier trong mã ứng dụng, dùng cơ chế so sánh thích hợp với dữ liệu mật mã.

Verifier một chiều không bảo vệ khỏi người có thể sửa bản ghi phiên, sửa liên kết tài khoản hoặc chiếm ứng dụng đang chạy. Vẫn phải giới hạn quyền đọc/ghi store, bảo vệ backup và kiểm soát tài khoản vận hành.

## 7. Đưa bí mật tới trình duyệt bằng cookie được bảo vệ

Ví dụ header cho cổng nhân sự dùng cookie opaque:

```http
Set-Cookie: __Host-session=<opaque-secret>; Path=/; Secure; HttpOnly; SameSite=Lax
```

`<opaque-secret>` là placeholder, không phải token có thể sử dụng. Với trình duyệt hỗ trợ cookie prefix, `__Host-` yêu cầu HTTPS, `Secure`, `Path=/` và không có thuộc tính `Domain`. `HttpOnly` ngăn script đọc cookie qua API như `document.cookie`; `SameSite` điều khiển việc gửi cookie theo ngữ cảnh site. [Nguồn: MDN, Set-Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie).

Các thuộc tính có mục đích khác nhau. `Secure` không mã hóa nội dung tại nơi lưu trên thiết bị. `HttpOnly` không ngăn mã JavaScript độc hại cùng origin gửi request mà trình duyệt tự gắn cookie. `SameSite=Lax` không thay thế toàn bộ biện pháp chống CSRF.

Cookie ví dụ không đặt thời gian sống bền vững tại client, nhưng server vẫn phải thực thi thời hạn của phiên. Trình duyệt có thể khôi phục session cookie khi khôi phục phiên làm việc; đóng cửa sổ không phải bằng chứng server đã thu hồi token. [Nguồn: MDN, Expires](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie#expiresdate).

Chọn `SameSite` phải xét luồng thực tế, đặc biệt redirect hoặc callback SSO giữa các site. Không hạ mọi cookie thành `SameSite=None` chỉ để một callback chạy; cần hiểu cookie nào được dùng ở bước nào và bảo vệ giao dịch đăng nhập tương ứng.

Cookie của ứng dụng nên có phạm vi host phù hợp thay vì được mở rộng cho mọi subdomain để tiện chia sẻ. Nếu nhiều ứng dụng cần SSO, dùng giao thức liên kết danh tính thay vì mặc định phát chung một bearer secret cho toàn bộ hệ thống.

## 8. Những nơi không nên đưa session secret

Một token có thể bị lộ ở lớp khác dù ứng dụng không chủ động in ra nó. Cần kiểm soát cả hạ tầng và công cụ quan sát.

| Vị trí | Vấn đề | Quyết định thiết kế của cổng nhân sự |
| --- | --- | --- |
| Query string hoặc đường dẫn URL | Có thể vào lịch sử, log, bookmark hoặc dữ liệu chuyển hướng | Không chấp nhận token phiên qua URL |
| Log request/response | Header `Cookie` hoặc `Set-Cookie` có thể bị chụp | Loại hoặc che giá trị trước khi thu thập |
| Trace, exception và công cụ hỗ trợ | Dữ liệu chẩn đoán có thể sao chép credential | Chỉ ghi metadata được cho phép |
| `localStorage` của ứng dụng web | Script cùng origin có thể đọc | Với kiến trúc cookie của bài, không tạo bản sao ở đây |
| Dashboard quản lý phiên | Nhân viên hoặc người dùng có thể xem token thật | Hiển thị mã tham chiếu nội bộ, không bearer secret |
| Sự kiện phân tích hoặc hàng đợi nghiệp vụ | Tạo thêm người và dịch vụ được tiếp cận bí mật | Không gửi cookie hoặc token thô theo sự kiện |

Không dùng session secret làm correlation ID. Có thể tạo mã quan sát độc lập để liên kết request với bản ghi phiên mà không phát bí mật có quyền truy cập.

NIST khuyến nghị tránh lưu session secret ở vị trí dễ lộ như HTML5 Local Storage và yêu cầu duy trì kênh được bảo vệ sau xác thực. [Nguồn: NIST, Session Bindings](https://pages.nist.gov/800-63-4/sp800-63b.html#session-bindings).

Nếu một proxy hoặc gateway được phép kết thúc TLS và xử lý cookie, nó nằm trong ranh giới bảo vệ credential. Cần xác định quyền truy cập, chính sách log và kênh tiếp theo; không giả định bật HTTPS ở browser đã bảo vệ mọi chặng nội bộ.

## 9. Cấp mới và thay bí mật khi trạng thái bảo mật thay đổi

Một phiên trước đăng nhập có thể chỉ lưu trạng thái ẩn danh. Nếu sau xác thực ứng dụng tiếp tục dùng nguyên giá trị đã biết hoặc có thể bị đối thủ cố định trước đó, nguy cơ session fixation xuất hiện.

Trong cổng nhân sự, các mốc chuyển trạng thái phải có cơ chế session manager phù hợp:

```text
Ẩn danh
    ↓ kiểm tra bước xác thực đầu tiên
Chờ MFA, quyền giới hạn
    ↓ hoàn tất điều kiện xác thực
Phiên xác thực đầy đủ với bí mật phù hợp cho trạng thái mới
    ↓ step-up khi cần
Ngữ cảnh xác thực hoặc quyền thao tác được nâng theo chính sách
```

Không cho phiên chờ MFA sử dụng endpoint cần MFA đầy đủ. Khi làm mới hoặc thay bí mật sau chuyển mức bảo mật, phải xử lý bí mật cũ sao cho nó không tiếp tục mở được quyền mới.

Thay bí mật định kỳ cũng cần xử lý request song song, nhiều tab và response đến không đúng thứ tự. Không để một request cũ ghi lại trạng thái active sau logout, hoặc để response đến muộn phục hồi token đã bị thu hồi. Cách thực thi có thể dùng phiên bản, cập nhật có điều kiện và cơ chế session manager đã kiểm thử.

Đổi session secret của một phiên khác với xoay khóa ký toàn hệ thống. Xoay khóa ký không phải thao tác bắt buộc cho mỗi lần đăng nhập; ngược lại, thay bearer secret cho một người không xử lý được sự cố lộ khóa ký dùng chung.

## 10. Kiểm tra bí mật đúng chưa đủ để cho phép request

Backend cần đánh giá phiên ở thời điểm sử dụng, không chỉ tìm thấy một chuỗi khớp. Mã giả cho cổng nhân sự có thể là:

```text
authenticateSession(request):
    rawSecret = readOnlyFromAcceptedSessionMechanism(request)
    validateTokenRepresentationAndSize(rawSecret)
    session = lookupUsingSecretVerifier(rawSecret)

    requireSessionActive(session)
    requireBeforeAbsoluteExpiry(session)
    requireWithinIdleLimit(session)
    requireAccountActive(session.accountId)
    requireSecurityVersionAccepted(session)

    return serverManagedAuthenticationContext(session)

authorizeResource(authContext, resource, action):
    requireCorrectTenantAndResourceScope(authContext, resource)
    requireCurrentPermission(authContext, resource, action)
    requireAuthenticationStrengthAndFreshnessIfNeeded(authContext, action)
```

Hạn không hoạt động và hạn tuyệt đối cần được thực thi ở server. Hoạt động nền hoặc request do đối thủ gửi có thể giữ phiên hoạt động nếu chỉ dựa vào idle timeout, nên không được tự kéo dài vô hạn mọi giới hạn chỉ vì token vẫn xuất hiện.

Mức xác thực của phiên cũng không được tự cao hơn sự kiện đã tạo ra nó. NIST nêu rõ phiên có thể được xem ở mức AAL thấp hơn, nhưng không cao hơn sự kiện xác thực nguồn. [Nguồn: NIST, Session Bindings](https://pages.nist.gov/800-63-4/sp800-63b.html#session-bindings).

Đối với RBAC hoặc ABAC, có session hợp lệ chỉ xác định ngữ cảnh chủ thể. Nó không tự chứng minh chủ thể có quyền đọc mọi hồ sơ hoặc thay mọi vai trò. Nếu quyền thay đổi, cần chính sách cập nhật hoặc kiểm tra lại phù hợp thay vì tin mãi một bản snapshot quyền cũ.

## 11. Logout, thu hồi và hệ thống nhiều node

Xóa cookie ở trình duyệt giúp client dừng trình bí mật. Nó không tự vô hiệu hóa bản sao đã bị đối thủ lấy. Logout cần làm phiên không còn được server chấp nhận, đồng thời hướng dẫn client bỏ cookie tương ứng.

Trong cổng nhân sự, có thể phân biệt thu hồi một phiên với thu hồi mọi phiên của tài khoản. Các sự kiện như nghi lộ credential, recovery hoặc vô hiệu hóa tài khoản cần được đánh giá để chọn phạm vi thu hồi.

Nếu nhiều node cùng xác minh phiên, trạng thái thu hồi phải được thực thi nhất quán theo thiết kế. Xóa bản ghi ở một node nhưng node khác vẫn dùng cache cũ sẽ để lại một khoảng thời gian chấp nhận token. Cần xác định rõ nơi giữ trạng thái chuẩn, thời gian cache và cách xử lý khi không đọc được dữ liệu cần thiết.

Thu hồi cũng không tự hoàn tác thao tác đã được chấp nhận trước đó. Với hành động đặc biệt nhạy cảm hoặc chạy dài, có thể cần kiểm tra lại quyền và trạng thái ở thời điểm nghiệp vụ phù hợp, thay vì giả định một lần kiểm tra từ đầu request bảo vệ được mọi diễn biến sau đó.

Không phục hồi bản backup của session store rồi vô tình làm các phiên đã thu hồi hoạt động trở lại. Nếu kiến trúc cần lưu phục hồi dữ liệu phiên, phải thiết kế cách bảo toàn giới hạn thời gian và trạng thái an ninh sau restore.

## 12. Session secret trong SSO, JWT và MFA

Với SSO, ứng dụng có thể nhận kết quả xác thực từ IdP rồi tạo session secret cục bộ. Cookie phiên tại IdP và cookie phiên tại ứng dụng có phạm vi và vòng đời khác nhau. Logout ở ứng dụng không mặc nhiên kết thúc mọi phiên IdP hoặc mọi ứng dụng khác.

Một JWT được ký không tự bảo mật nội dung. Nếu JWT được dùng như bearer credential, người lấy được nguyên token có thể sử dụng nó khi các điều kiện kiểm tra vẫn thỏa mãn. Khả năng xác minh chữ ký không thay thế thiết kế hết hạn, thu hồi hoặc bảo vệ nơi lưu token.

NIST lưu ý access token có thể còn hiệu lực sau khi phiên xác thực đã kết thúc, nên không được coi việc có access token là bằng chứng người dùng vẫn hiện diện. [Nguồn: NIST SP 800-63B-4, Access Tokens](https://pages.nist.gov/800-63-4/sp800-63b.html#access-tokens).

Tương tự, đăng nhập ban đầu bằng MFA chống phishing không tự làm cookie phiên trở thành credential gắn với thiết bị. Nếu ứng dụng vẫn dùng bearer cookie, nó vẫn phải bảo vệ bí mật đó. Giao thức chứng minh quyền sở hữu khóa là một thiết kế khác, không thể suy ra chỉ từ thuộc tính `Secure` hoặc từ việc đã bật MFA.

Đối với workload, token và credential máy cần danh tính, quyền và vòng đời riêng. Không sao chép session secret của một người vào cấu hình job nền để biến job đó thành một dịch vụ hoạt động lâu dài dưới phiên của người dùng.

## 13. Tình huống kiểm chứng thiết kế

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Hai lần đăng nhập độc lập | Có bí mật riêng, không dùng chung giá trị cấu hình toàn ứng dụng |
| Client gửi mã phiên nội bộ thay cho secret | Không được xác thực |
| Token chỉ khác một ký tự | Không khớp phiên gốc |
| Token đúng nhưng phiên đã hết hạn hoặc bị thu hồi | Bị từ chối tại backend |
| Token trước đăng nhập được trình sau khi nâng mức xác thực | Không mở được quyền mới ngoài chính sách |
| Client bỏ cookie sau logout nhưng đối thủ còn bản sao | Bản sao vẫn bị server từ chối |
| Request đến node khác sau thu hồi | Áp dụng giới hạn thu hồi đã cam kết |
| Bật log chẩn đoán | Không xuất cookie, token thô hoặc header chứa bí mật |
| User bị gỡ quyền nhưng phiên chưa hết hạn | Quyền mới được thực thi theo chính sách cập nhật |
| Khôi phục trình duyệt hoặc backup | Không vượt thời hạn hoặc phục hồi trái phép phiên đã bị vô hiệu hóa |

Không đánh giá bộ sinh chỉ bằng việc tạo một số chuỗi rồi thấy “chưa trùng”. Cần kiểm tra nguồn ngẫu nhiên, cấu hình, cách dùng và toàn bộ đường đi của bí mật. Sự khó đoán không bù được việc token xuất hiện nguyên vẹn trong công cụ quan sát.

## 14. Bài tập vận dụng

Một ứng dụng dùng 32 byte ngẫu nhiên làm cookie phiên, nhưng ghi toàn bộ header vào log. Session store lưu token thô, logout chỉ xóa cookie, và node phụ giữ cache phiên đến khi tự hết hạn. Nhóm phát triển cho rằng đăng nhập bằng passkey đã loại bỏ nguy cơ chiếm phiên.

Hãy đề xuất phương án trả lời:

1. Đâu là session secret, đâu là dữ liệu tham chiếu nội bộ, và ai đang có khả năng tiếp cận bí mật?
2. Lưu verifier một chiều bảo vệ được loại sự cố nào, và không bảo vệ được điều gì?
3. Cần thay đổi logout và cơ chế nhiều node thế nào để một bản sao cookie không tiếp tục hoạt động ngoài giới hạn cho phép?
4. Vì sao passkey không tự bảo vệ bearer cookie sau đăng nhập?
5. Cần bằng chứng nào cho thấy phiên hết hạn, thay quyền và thu hồi thực sự được thực thi ở backend?

Thiết kế cần theo được bí mật từ lúc sinh, gửi, trình lại đến lúc hết giá trị. Session secret chỉ có ích trong nền tảng IAM khi nó gắn với đúng tài khoản, đúng ngữ cảnh xác thực, đúng quyền và một vòng đời mà các thành phần thực sự kiểm soát.

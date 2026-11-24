# Pre recovery session handling

## 1. Vì sao phải xử lý session trước khi khôi phục?

Người dùng quên mật khẩu nhưng ứng dụng vẫn mở trên laptop. Một người khác mất điện thoại đang đăng nhập. Trong một sự cố nghiêm trọng hơn, cả chủ tài khoản và kẻ tấn công đều có session còn hiệu lực khi yêu cầu recovery được gửi đến.

Nếu hệ thống chỉ tập trung vào token reset hoặc bước đăng ký lại MFA, các session cũ có thể tiếp tục đổi email, thêm passkey, phát hành token mới hoặc đọc dữ liệu trong lúc chủ tài khoản đang xác minh danh tính.

**Pre recovery session handling** là việc đánh giá và kiểm soát các phiên truy cập đã tồn tại trước khi một giao dịch khôi phục hoàn tất. Phạm vi gồm kiểm kê, giữ nguyên, hạn chế quyền, yêu cầu bằng chứng mới hoặc thu hồi những phiên đó theo mức độ xác minh và rủi ro.

Trong thiết kế khôi phục tài khoản khi mất mật khẩu, MFA, passkey hoặc thiết bị xác thực, có hai yêu cầu phải cùng được đáp ứng:

- Một yêu cầu chưa xác minh không được trở thành công cụ tùy ý khóa người dùng hợp pháp.
- Session còn sống không được trở thành đường giúp kẻ tấn công vượt qua quyết định bảo vệ tài khoản.

Mục tiêu của bài học là xác định **sự kiện nào đủ để thay đổi quyền của session**, thay đổi đó có hiệu lực ở đâu và làm thế nào để các đường gia hạn không khôi phục lại quyền đã bị chặn.

## 2. Những phiên truy cập nào cần được kiểm kê?

Không nên đồng nhất “session” với một cookie trong tab trình duyệt đang mở.

| Thành phần | Ví dụ | Vấn đề cần đánh giá trước recovery |
|---|---|---|
| Session web phía máy chủ | Cookie tham chiếu bản ghi session | Còn hiệu lực, có bị sao chép hoặc gia hạn không? |
| Phiên ứng dụng di động | Ứng dụng giữ bí mật phiên | Thiết bị bị mất có tiếp tục gọi API không? |
| Access token | Token gửi đến resource server | Điểm kiểm tra quyền có nhận biết trạng thái bảo vệ mới không? |
| Refresh token và chuỗi gia hạn | Token dùng để lấy access token mới | Session cũ có tiếp tục sinh quyền mới không? |
| Kết nối dài hạn | WebSocket hoặc luồng dữ liệu riêng tư | Kết nối đã mở có được kiểm tra lại không? |
| Cơ chế nhớ đăng nhập | Remember-me token hoặc trusted-browser record | Có thể tái lập phiên mà không qua bằng chứng cần thiết không? |
| Session SSO bên ngoài | Phiên tại Identity Provider | Sau khi chặn tại ứng dụng, SSO có tạo lại truy cập không phù hợp không? |

NIST lưu ý access token và refresh token có thể còn hiệu lực sau khi phiên xác thực kết thúc; có access token không tự chứng minh người dùng đang hiện diện. [Nguồn: NIST SP 800-63B-4 — Session Management](https://pages.nist.gov/800-63-4/sp800-63b/session/).

Một API key hoặc quyền cấp cho ứng dụng bên thứ ba không nhất thiết là session tương tác. Tuy nhiên, nếu nó cho phép truy cập tài khoản sau khi session bị thu hồi, cần đưa nó vào đánh giá phạm vi sự cố. Không nên tuyên bố “đã đóng mọi đường truy cập” chỉ vì đã xóa các session web.

## 3. Tách session cũ, ngữ cảnh recovery và bằng chứng mới

Ba đối tượng này phục vụ những mục đích khác nhau:

| Đối tượng | Vai trò | Điều không được tự suy ra |
|---|---|---|
| Session tồn tại trước recovery | Duy trì quyền từ một lần xác thực trước đó | Người đang giữ nó chắc chắn là chủ tài khoản |
| Ngữ cảnh recovery | Liên kết các bước trong một hồ sơ khôi phục | Người giữ ngữ cảnh được sử dụng toàn bộ tài khoản |
| Bằng chứng mới đã xác minh | Hỗ trợ quyết định cho một hành động cụ thể | Mọi phương thức hoặc session khác đều an toàn |

Người đang có session có thể đã quên một phương thức nhưng vẫn là chủ hợp pháp. Cũng có thể đó là kẻ đã đánh cắp cookie. Vì vậy, session là dữ kiện có giá trị trong ngữ cảnh, nhưng không nên là điều kiện duy nhất để thay MFA hoặc chấp nhận một yêu cầu recovery nhạy cảm.

Ví dụ, nút “Tôi vẫn đăng nhập trên thiết bị này” có thể dẫn đến xác thực lại bằng phương thức còn tin cậy. Nó không nên trực tiếp phát grant thay passkey hoặc đổi email.

Nếu người dùng không còn thực hiện được bằng chứng được yêu cầu, hệ thống cần đường recovery phù hợp. Không nên tạo vòng lặp bắt họ luôn phải dùng chính thiết bị đã mất mới được bắt đầu khôi phục.

## 4. Phân biệt yêu cầu công khai và sự kiện bảo vệ đã xác minh

### 4.1. Yêu cầu recovery chưa xác minh

Một người biết địa chỉ email gửi yêu cầu quên mật khẩu. Ở bước này, hệ thống chưa biết đó là chủ tài khoản hay kẻ đang cố làm phiền họ.

OWASP khuyến nghị phản hồi nhất quán cho tài khoản tồn tại và không tồn tại, đồng thời không thay đổi tài khoản chỉ vì có yêu cầu reset chưa được xác minh. [Nguồn: OWASP — Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html).

Theo nguyên tắc đó, một thiết kế có thể ghi nhận yêu cầu, áp dụng hạn mức và cung cấp hướng dẫn, trong khi giữ chính sách session hiện tại. Không thu hồi mọi session hoặc công khai danh sách thiết bị chỉ từ một định danh tài khoản.

### 4.2. Báo mất hoặc nghi bị chiếm đã đủ điều kiện bảo vệ

Một báo cáo có thể được xác minh đủ cho việc hạn chế thiệt hại trước khi đủ điều kiện cấp quyền khôi phục toàn bộ. Hai quyết định này cần có tiêu chí riêng.

Ví dụ, tổ chức có quy trình kiểm tra báo mất thiết bị qua authenticator dự phòng hoặc kênh hỗ trợ đã được kiểm soát. Sau khi đạt điều kiện, hệ thống có thể đình chỉ quyền truy cập liên quan hoặc đặt tài khoản vào chế độ bảo vệ. Quyết định đó không đồng thời trao quyền thêm authenticator mới.

Không có một tổ hợp bằng chứng duy nhất phù hợp cho mọi sản phẩm. Chính sách cần mô tả ai được yêu cầu, bằng chứng nào được chấp nhận, phạm vi bảo vệ và cách xử lý báo giả.

### 4.3. Recovery được chấp nhận hoặc đã hoàn tất

Khi bằng chứng đáp ứng chính sách, hệ thống có thể cho phép thay phương thức bị mất bằng một grant có phạm vi hẹp. Các session cũ vẫn phải được xử lý theo quyết định bảo vệ, thay vì tự trở lại toàn quyền chỉ vì hồ sơ chuyển trạng thái.

OWASP chỉ ra rằng reset mật khẩu không đủ để lấy lại quyền kiểm soát tài khoản bị chiếm nếu kẻ tấn công còn session hoặc đã đổi phương thức bảo mật. [Nguồn: OWASP — Account Recovery After Suspected Compromise](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html#account-recovery-after-suspected-compromise).

## 5. Thu thập trạng thái trước khi thay đổi quyền

Một bản ghi ngữ cảnh trước recovery giúp giải thích vì sao session được giữ, hạn chế hoặc thu hồi. Đây là thông tin vận hành được bảo vệ, không phải dữ liệu trả về cho mọi người biết email tài khoản.

| Dữ liệu tham khảo | Mục đích sử dụng |
|---|---|
| Tham chiếu session nội bộ | Liên kết quyết định mà không ghi bí mật phiên |
| Thời điểm tạo phiên | Xác định phiên thuộc giai đoạn nào |
| Thời điểm xác thực thực sự | Đánh giá độ mới của bằng chứng |
| Phương thức và nguồn xác thực đã ghi nhận | Biết quyền được thiết lập từ bằng chứng nào |
| Lần hoạt động gần nhất | Hỗ trợ điều tra và trải nghiệm người dùng |
| Chuỗi gia hạn liên quan | Chặn việc phát token tiếp từ quyền đã thu hồi |
| Phiên bản bảo mật của session | Đối chiếu với quyết định bảo vệ hiện tại |
| Tín hiệu môi trường cần thiết | Hỗ trợ phân tích rủi ro, có giới hạn dữ liệu |

Không nên trộn ba mốc thời gian:

```text
issuedAt   : lần cấp session hoặc token đang xét
authTime   : lần người dùng thực sự xác thực tương ứng
lastSeenAt : lần hệ thống quan sát hoạt động gần nhất
```

Một token vừa được cấp do refresh có thể có `issuedAt` mới nhưng vẫn dựa trên lần xác thực cũ. Một session hoạt động liên tục cũng có thể đang do kẻ tấn công sử dụng. Vì thế, “mới xuất hiện” và “đang hoạt động” không tự nâng mức tin cậy.

Nếu hệ thống thiếu một phần lịch sử, hãy ghi nhận điều chưa biết. Không suy diễn rằng phiên không có dữ liệu rủi ro là phiên an toàn.

Trong một sự cố đang diễn ra, việc lấy báo cáo đầy đủ không nên trì hoãn biện pháp bảo vệ cần thực hiện ngay. Có thể ghi dấu mốc quyết định cùng các tham chiếu sẵn có, sau đó bổ sung dữ liệu điều tra từ nguồn đã được kiểm soát.

## 6. Chính sách giữ, hạn chế và thu hồi

Bảng dưới là ví dụ chính sách của bài học. Nó cần được điều chỉnh theo loại tài khoản và mức thiệt hại, không phải bộ quy tắc bắt buộc cho mọi ứng dụng.

| Tình huống | Session hiện có | Thao tác bảo mật nhạy cảm |
|---|---|---|
| Chỉ có yêu cầu recovery công khai | Giữ chính sách hiện tại | Vẫn áp dụng điều kiện xác thực vốn có |
| Quên mật khẩu, còn bằng chứng tin cậy | Có thể giữ hoặc yêu cầu xác thực lại theo chính sách | Không tự cho đổi MFA hay email từ session cũ |
| Báo mất một thiết bị đã được xác minh | Hạn chế hoặc thu hồi phiên liên quan | Yêu cầu điều kiện riêng cho thay phương thức |
| Nghi bị chiếm nhưng chưa rõ phạm vi | Có thể đặt chế độ bảo vệ theo quyết định đã xác minh | Chặn các thay đổi làm củng cố quyền truy cập |
| Đã xác nhận phiên hoặc miền truy cập bị lộ | Thu hồi theo phạm vi sự cố, có thể toàn tài khoản | Không dựa vào session bị ảnh hưởng để phê duyệt |

### Không gắn quyền với phương thức HTTP

Nếu cho phép một phần truy cập trong chế độ hạn chế, hãy dùng danh sách hành động cụ thể. Không coi mọi request `GET` là an toàn: đọc dữ liệu riêng tư hoặc tải bản xuất tài khoản có thể gây thiệt hại lớn.

Ví dụ, ứng dụng học tập có thể cho đọc hướng dẫn công khai trong khi chặn thay email, thêm passkey, xuất dữ liệu và xem bí mật recovery. Khi có dấu hiệu session đã bị đánh cắp, quyền đọc dữ liệu cá nhân cũng cần bị xem xét; “chỉ đọc” không tự loại bỏ nguy cơ lộ dữ liệu.

### Không coi đóng một tab là thu hồi

OWASP nhấn mạnh phải vô hiệu session ở phía máy chủ; xóa cookie tại một trình duyệt không làm bản sao bị đánh cắp mất hiệu lực. [Nguồn: OWASP — Session Management, Session Expiration](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html#session-expiration).

Thông báo “hãy đăng xuất khỏi thiết bị cũ” không thay thế biện pháp thu hồi mà người dùng đang không thể thực hiện vì đã mất thiết bị đó.

## 7. Mô hình trạng thái có nguồn quyết định rõ ràng

Có thể tách **trạng thái hồ sơ recovery** khỏi **trạng thái bảo vệ tài khoản**:

```text
Hồ sơ recovery:
REQUESTED → EVIDENCE_PENDING → APPROVED → COMPLETED
                    └──────→ EXPIRED hoặc CANCELLED

Chế độ bảo vệ tài khoản:
NORMAL
RECOVERY_PROTECTED
INCIDENT_LOCKDOWN
```

Các tên trên là mô hình tham khảo. Điểm quan trọng là không tự đồng nhất hai luồng.

- `REQUESTED` chưa đủ để chuyển tài khoản sang khóa toàn bộ.
- `RECOVERY_PROTECTED` có thể giữ một tập quyền rất hẹp khi quyết định bảo vệ đã hợp lệ.
- `INCIDENT_LOCKDOWN` có thể yêu cầu từ chối mọi session thông thường cũ trong phạm vi sự cố.
- Hồ sơ hết hạn không tự xóa một quyết định bảo vệ do sự cố khác tạo ra.

Ví dụ, có hai hồ sơ cùng tồn tại: một yêu cầu quên mật khẩu và một báo cáo xâm phạm đã xác minh. Khi hồ sơ quên mật khẩu hết hạn, hệ thống không được đặt toàn tài khoản về `NORMAL` rồi mở lại quyền của kẻ tấn công.

Mỗi hạn chế nên có nguồn quyết định, phạm vi, phiên bản và điều kiện dỡ bỏ. Khi nhiều quyết định chồng lên nhau, cần hợp nhất theo chính sách bảo vệ, thay vì cho sự kiện cuối cùng ghi đè mọi hạn chế trước đó.

## 8. Ranh giới hiệu lực bằng phiên bản session

Một cách triển khai tham khảo là dùng số phiên bản tăng đơn điệu cho quyền phiên của tài khoản:

```text
Account.securityEpoch = 17
Session.securityEpoch = 17

Quyết định thu hồi toàn bộ session cũ:
Account.securityEpoch = 18

Session có epoch 17 không còn được chấp nhận.
```

`securityEpoch` là thiết kế của ứng dụng, không phải claim tiêu chuẩn có sẵn trong mọi giao thức. Nó chỉ có tác dụng khi các điểm kiểm tra quyền và cấp token thực sự thực thi quy tắc tương ứng.

Nên phân biệt:

| Thuộc tính | Tác dụng |
|---|---|
| `securityEpoch` | Xác định tập session nào còn được chấp nhận |
| `guardVersion` | Nhận biết thay đổi chế độ hoặc chính sách hạn chế |
| Trạng thái thu hồi của session riêng | Chặn một session hoặc chuỗi gia hạn cụ thể |
| Trạng thái hồ sơ recovery | Điều phối bằng chứng và quyền của quá trình khôi phục |

Không cần tăng epoch toàn tài khoản cho mọi thao tác công khai hoặc mọi lần ghi tiến độ recovery. Nếu chỉ thay chính sách hạn chế một nhóm hành động, có thể cập nhật guard theo thiết kế. Nếu đã quyết định thu hồi toàn bộ phiên cũ, tăng epoch cung cấp ranh giới rõ hơn việc chỉ so mốc thời gian.

Không giảm epoch để “khôi phục session” khi báo cáo được hủy. Các quyền đã thu hồi cần được thiết lập lại bằng luồng xác thực được phép. Việc mở lại bản ghi session cũ có thể mở lại cả bản sao đang nằm trong tay kẻ tấn công.

### Ghi quyết định bảo vệ như một giao dịch nghiệp vụ

Một luồng vào chế độ bảo vệ có thể:

1. Xác minh quyết định nội bộ còn hiệu lực, đúng tài khoản và chưa được áp dụng.
2. Khóa hoặc kiểm soát đồng thời bản ghi bảo mật có thẩm quyền.
3. Ghi chế độ hạn chế, phạm vi thu hồi và phiên bản mới theo chính sách.
4. Ghi dấu vết cùng sự kiện outbox trong cùng ranh giới giao dịch nếu dùng cùng kho dữ liệu.
5. Phát tín hiệu cho các thành phần liên quan và kiểm tra mức thực thi thực tế.

Sự kiện bất đồng bộ giúp lan truyền nhanh, nhưng không tự bảo đảm mọi consumer đã cập nhật. Với thao tác có thiệt hại cao, cần kiểm tra trạng thái đủ mới tại nguồn có thẩm quyền hoặc một cơ chế tương đương được thiết kế rõ.

## 9. Mã giả Java cho kiểm tra session cũ

Đoạn dưới minh họa tầng quyết định quyền cho **session ứng dụng thông thường**. Nó không phải bộ xác minh cookie, JWT hay giao thức recovery hoàn chỉnh.

`VerifiedSession` phải do backend tạo sau khi kiểm tra bí mật hoặc chữ ký, issuer, audience và các điều kiện tương ứng với loại phiên. `AccountSecurity` phải đến từ nguồn trạng thái có thẩm quyền đủ mới cho hành động đang xét.

```java
enum Decision {
    ALLOW,
    DENY,
    HOLD_DURING_RECOVERY,
    REQUIRE_FRESH_EVIDENCE
}

Decision evaluateExistingSession(
    VerifiedSession session,
    AccountSecurity security,
    Operation operation,
    Instant now
) {
    if (!session.accountId().equals(security.accountId())) {
        return Decision.DENY;
    }

    if (!session.isUsableAt(now) || session.isRevoked()) {
        return Decision.DENY;
    }

    if (session.securityEpoch() != security.securityEpoch()) {
        return Decision.DENY;
    }

    if (security.mode() == INCIDENT_LOCKDOWN) {
        return Decision.DENY;
    }

    if (security.mode() == RECOVERY_PROTECTED
            && !security.allowedDuringProtection(operation)) {
        return Decision.HOLD_DURING_RECOVERY;
    }

    if (!authorizationPolicy.permits(session, operation)) {
        return Decision.DENY;
    }

    if (!evidencePolicy.satisfies(session, operation, now)) {
        return Decision.REQUIRE_FRESH_EVIDENCE;
    }

    return Decision.ALLOW;
}
```

Các giới hạn cần giữ khi hiện thực hóa:

- Không nhận `mode`, `securityEpoch` hoặc kết quả xác minh bằng chứng từ JSON do client tự khai.
- `allowedDuringProtection` là tập hành động được định nghĩa rõ, không phải điều kiện “không phải POST”.
- `evidencePolicy` kiểm tra phương thức, độ mới và tình trạng bằng chứng; không chỉ kiểm tra session vừa được refresh.
- Quyền recovery được kiểm tra bằng ngữ cảnh và grant riêng. Không đổi `INCIDENT_LOCKDOWN` thành cho phép toàn bộ chỉ để endpoint recovery chạy được.
- Endpoint logout, hướng dẫn công khai và nộp bằng chứng có cách bảo vệ phù hợp với chức năng riêng; không nên ép chúng qua một session đầy đủ đang bị yêu cầu thu hồi.
- Kết quả `ALLOW` cần gắn với trạng thái vừa đọc. Với thay đổi nhạy cảm, phải kiểm tra lại ràng buộc bảo mật ở điểm ghi để tránh trạng thái đổi giữa chừng.

Không nên triển khai hàm này chỉ tại giao diện web rồi để API di động, GraphQL hoặc tác vụ nền đi đường khác.

## 10. Chặn race condition ở đường gia hạn và request đang chạy

### 10.1. Refresh không được hợp thức hóa quyền đã thu hồi

Giả sử refresh token thuộc epoch 17 đang được xử lý trong lúc tài khoản chuyển sang epoch 18.

Hai kết quả có thể được chấp nhận trong một thiết kế có ranh giới thu hồi rõ:

- Token được phát trước ranh giới vẫn gắn với quyền cũ và bị từ chối sau khi epoch thay đổi.
- Việc cấp token được kiểm tra đồng thời với quyết định bảo vệ, rồi bị từ chối nếu quyền gốc không còn hợp lệ.

Kết quả cần tránh:

```text
Refresh token cũ, epoch 17
  → đọc Account.securityEpoch hiện tại = 18
  → gắn epoch 18 vào token mới
  → token cũ đã sinh lại quyền sau thu hồi
```

Cấp token mới phải kiểm tra quyền gốc còn được phép và đồng bộ với ranh giới bảo vệ. Không sao chép phiên bản mới của tài khoản để che mất nguồn xác thực cũ.

RFC 9700 mô tả refresh token rotation và phát hiện tái sử dụng như những biện pháp bảo vệ refresh token. Các cơ chế đó không thay thế quyết định của ứng dụng về session nào phải bị chặn trong recovery. [Nguồn: RFC 9700 — Refresh Token Protection](https://www.rfc-editor.org/rfc/rfc9700.html#section-4.14).

### 10.2. Request đã qua middleware vẫn có thể cần kiểm tra lại

Một request đổi email có thể được cho qua trước khi chế độ bảo vệ được ghi. Nếu nó ghi dữ liệu sau ranh giới đó mà không kiểm tra lại, kẻ tấn công vẫn có thể củng cố quyền kiểm soát.

Với thao tác nhạy cảm, có thể dùng điều kiện phiên bản khi ghi, khóa theo tài khoản hoặc cơ chế phối hợp tương đương. Nếu trạng thái bảo mật đã thay đổi, request phải được đánh giá lại hoặc dừng theo chính sách.

Các tác vụ đã xếp hàng để xuất dữ liệu, phát hành khóa hay thay cấu hình cũng cần mang ngữ cảnh cấp quyền và kiểm tra lại tại thời điểm thực hiện. Thu hồi session không tự hoàn tác mọi công việc đã được chấp nhận trước đó.

### 10.3. Độ trễ phân tán phải được nhìn thấy

RFC 7009 lưu ý có thể có độ trễ lan truyền thông tin thu hồi giữa các máy chủ. Việc thu hồi token liên quan còn phụ thuộc chính sách và khả năng của authorization server. [Nguồn: RFC 7009 — Token Revocation](https://www.rfc-editor.org/rfc/rfc7009.html#section-2.1).

Vì vậy, nếu resource server chỉ kiểm tra chữ ký JWT và chưa kiểm tra thu hồi, token cũ có thể tiếp tục được chấp nhận cho đến khi có cơ chế chặn khác hoặc hết hạn. Tuyên bố “thu hồi ngay” cần phù hợp với đường thực thi thực tế.

Một thiết kế có thể dùng introspection, tra trạng thái phiên, kiểm tra epoch hoặc danh sách thu hồi, tùy kiến trúc. Với cache, cần xác định độ cũ được chấp nhận, hành vi khi nguồn trạng thái lỗi và cách xử lý thao tác nhạy cảm. Không hứa một giới hạn thời gian nếu hệ thống không thể bảo đảm giới hạn đó khi có sự cố.

Kết nối WebSocket hoặc luồng dữ liệu riêng tư cần được tái kiểm tra hoặc đóng theo sự kiện bảo vệ. Chỉ chặn request HTTP mới sẽ bỏ sót kết nối đã được mở trước đó.

## 11. Session SSO và xác thực lại qua IdP

Khi ứng dụng dùng SSO, có ít nhất hai miền trạng thái: session tại RP và session tại Identity Provider. Đóng một session RP không tự chứng minh session IdP đã bị thu hồi.

Trong OpenID Connect, `auth_time` biểu diễn thời điểm xác thực, còn `iat` biểu diễn thời điểm phát hành ID Token. Tham số `max_age` cho phép RP yêu cầu giới hạn tuổi xác thực; RP cần kiểm tra kết quả trả về phù hợp. [Nguồn: OpenID Connect Core 1.0 — Authentication Request và ID Token](https://openid.net/specs/openid-connect-core-1_0.html#AuthRequest).

Hệ quả thiết kế là không nên coi việc trình duyệt quay về từ IdP mà không yêu cầu thêm thao tác là bằng chứng mới đủ mạnh cho recovery. RP cần xác định loại bằng chứng và độ mới cần thiết, cùng cách phối hợp với IdP.

Các claim về phương thức hoặc mức xác thực cần được kiểm tra trong giao thức hợp lệ và ánh xạ theo thỏa thuận tin cậy. Không nâng quyền chỉ vì client gửi chuỗi `mfa` hoặc cờ `reauthenticated=true`.

Ngay cả khi IdP xác thực hợp lệ, RP vẫn cần thực thi trạng thái bảo vệ hiện tại của tài khoản. Nếu một session SSO cũ có thể tự tạo session RP mới để vượt khóa, đường thu hồi tại RP chưa đạt mục tiêu.

## 12. Trải nghiệm người dùng trong giai đoạn trước recovery

### 12.1. Giải thích đúng điều đang bị hạn chế

Thông báo nên gắn với hành động, chẳng hạn: “Thay đổi phương thức bảo mật đang được tạm giữ trong khi yêu cầu khôi phục được xử lý.” Người dùng cần biết bước tiếp theo mà không phải hiểu epoch hoặc refresh token.

Khi cần xác thực lại, hãy cho biết các phương thức còn được chấp nhận và đường hỗ trợ nếu họ không còn phương thức nào. Không lặp vô hạn yêu cầu OTP từ điện thoại đã báo mất.

Nếu cần thu hồi session hiện tại, nên giải thích hậu quả và nơi tiếp tục recovery qua ngữ cảnh được bảo vệ riêng. Việc thu hồi không nên khiến người dùng phải khởi tạo lại mọi hồ sơ hoặc làm bằng chứng đã nộp bị trộn với tài khoản khác.

### 12.2. Không tự thay danh tính của tab đang mở

Ví dụ, trình duyệt đang đăng nhập tài khoản B nhưng người dùng mở liên kết recovery của tài khoản A. Backend phải ràng buộc bằng chứng với tài khoản của hồ sơ recovery, không lấy tài khoản hiện tại của tab làm đích mặc định.

Tương tự, một session hợp lệ của B không phải bằng chứng sở hữu A. Việc chuyển hoặc đăng nhập tài khoản cần có bước phù hợp, thay vì tự gộp ngữ cảnh chỉ vì cùng trình duyệt.

Chỉ mở liên kết bằng GET không nên tự đăng xuất tài khoản khác, thay đổi phương thức bảo mật hoặc tiêu thụ quyền nhạy cảm. Cần xét cả việc liên kết được hệ thống email mở để quét trước khi người dùng tương tác.

### 12.3. Giữ tiến độ trong giới hạn dữ liệu an toàn

Có thể giữ tiến độ recovery bằng tham chiếu hồ sơ hoặc ngữ cảnh ngắn hạn có phạm vi rõ. Không dùng session cũ đã bị thu hồi làm cách duy nhất để tiếp tục.

Với dữ liệu đang soạn, cần cân nhắc độ nhạy cảm trước khi giữ bản nháp. Không tự chuyển mật khẩu, recovery code, giấy tờ hoặc dữ liệu riêng tư sang bộ nhớ trình duyệt chỉ để tránh mất nội dung khi đăng xuất.

## 13. Ba tình huống theo dòng thời gian

### Tình huống A — Yêu cầu recovery giả nhằm làm gián đoạn

1. Lan đang sử dụng tài khoản bình thường.
2. Một người khác nhập email của Lan vào biểu mẫu quên mật khẩu nhiều lần.
3. Hệ thống ghi nhận yêu cầu và hạn chế gửi lặp; các session của Lan không tự bị thu hồi.
4. Muốn thay bảo mật vẫn phải hoàn tất bằng chứng phù hợp.

Điểm cần học: khởi tạo hồ sơ công khai không đồng nghĩa đã xác minh quyền yêu cầu thay đổi tài khoản.

### Tình huống B — Chủ tài khoản và kẻ tấn công cùng có session

1. Hai session S1 và S2 cùng thuộc epoch 17; hệ thống chưa biết chắc ai đang giữ mỗi phiên.
2. Chủ tài khoản báo bị chiếm và hoàn tất quy trình đủ cho quyết định thu hồi toàn bộ session cũ.
3. Backend ghi epoch 18 và trạng thái bảo vệ theo chính sách. S1 và S2 không còn được dùng như session thông thường.
4. Recovery tiếp tục bằng ngữ cảnh hẹp, được xác minh riêng.
5. Refresh từ quyền epoch 17 không được tự tạo token epoch 18.
6. Sau recovery, quyền sử dụng tài khoản được thiết lập lại theo chính sách; không mở lại session cũ bằng cách giảm epoch.

Điểm cần học: khi không phân biệt được bản sao hợp pháp và bản sao bị đánh cắp, giữ “session hiện tại” chỉ vì nó gửi yêu cầu trước có thể giữ lại quyền của kẻ tấn công.

### Tình huống C — Quên mật khẩu nhưng vẫn có thiết bị tin cậy phù hợp

1. Minh quên mật khẩu nhưng còn authenticator khác được chính sách chấp nhận.
2. Session cũ giúp Minh tìm đường quản lý tài khoản; quyền thay mật khẩu dựa trên bằng chứng được yêu cầu riêng.
3. Hệ thống chỉ cho thay phương thức đúng mục đích, không tự bỏ MFA hoặc cho đổi mọi kênh recovery.
4. Chính sách xác định session nào được giữ, phải xác thực lại hoặc bị thu hồi khi thay đổi hoàn tất.

Điểm cần học: không phải mọi yêu cầu quên mật khẩu đều là sự cố chiếm tài khoản; cách xử lý cần dựa trên bằng chứng và thiệt hại có thể xảy ra.

## 14. Quan sát vận hành và giới hạn của thông báo

Một sự kiện tham khảo cho giai đoạn trước recovery:

```json
{
  "eventType": "PRE_RECOVERY_SESSION_POLICY_APPLIED",
  "accountRef": "internal-account-reference",
  "recoveryCaseRef": "internal-case-reference",
  "decisionRef": "verified-protection-decision-reference",
  "previousSecurityEpoch": 17,
  "currentSecurityEpoch": 18,
  "action": "REVOKE_EXISTING_ACCOUNT_SESSIONS",
  "reason": "VERIFIED_ACCOUNT_COMPROMISE_REPORT",
  "policyVersion": "example-v1"
}
```

Đây là bản ghi quyết định, chưa tự chứng minh mọi resource server đã ngừng chấp nhận token. Nên phân biệt thời điểm quyết định được commit với thời điểm các thành phần xác nhận áp dụng, nếu kiến trúc có theo dõi xác nhận.

Các chỉ số có thể giúp đánh giá chính sách:

| Chỉ số | Câu hỏi được giải đáp |
|---|---|
| Thu hồi do yêu cầu chưa xác minh | Có lỗ hổng khiến người khác dễ gây khóa tài khoản không? |
| Request bị chặn từ session cũ | Quy tắc bảo vệ có đang được thực thi không? |
| Refresh thành công sau ranh giới thu hồi | Có đường tái tạo quyền ngoài ý muốn không? |
| Thời gian áp dụng trạng thái bảo vệ | Độ trễ nằm ở dịch vụ hoặc cache nào? |
| Người dùng không tiếp tục được recovery | Ngữ cảnh hẹp hoặc hướng dẫn có bị đứt không? |
| Thay đổi nhạy cảm trong lúc recovery | Có hành động cần điều tra hoặc bổ sung ràng buộc không? |

Không ghi cookie, access token, refresh token hay token recovery vào log. Dùng tham chiếu nội bộ để liên kết sự kiện và bảo vệ quyền đọc dữ liệu vận hành. Thông báo cho người dùng là cơ chế phát hiện và hướng dẫn; nó không thay thế kiểm soát quyền phía máy chủ.

Nếu kênh liên lạc có thể bị chiếm, cần chọn cách thông báo theo chính sách sự cố. Không cho một session cũ vừa đổi email trở thành nguồn quyết định duy nhất về nơi nhận mọi cảnh báo.

## 15. Câu hỏi tự đánh giá thiết kế

1. Sự kiện nào đủ để giữ, hạn chế hoặc thu hồi session, và bằng chứng cho sự kiện đó nằm ở đâu?
2. Chỉ biết định danh tài khoản có thể khiến mọi phiên hợp pháp bị đóng không?
3. Session cũ đang được dùng như dữ kiện hay bị coi là bằng chứng sở hữu toàn bộ tài khoản?
4. Quy tắc có bao phủ session web, mobile, refresh, kết nối dài hạn và đường SSO không?
5. Token mới có giữ nguồn xác thực cũ hay bị nâng quyền chỉ vì có thời điểm phát hành mới?
6. Request đã qua middleware có thể ghi thay đổi bảo mật sau khi tài khoản được bảo vệ không?
7. Khi một hồ sơ hết hạn, hệ thống có vô tình dỡ hạn chế của hồ sơ hoặc sự cố khác không?
8. Nếu mọi session cũ bị thu hồi, người dùng còn đường tiếp tục recovery với quyền hẹp không?
9. Thông báo “đã thu hồi” có phản ánh đúng giới hạn và độ trễ thực thi của hệ thống không?

Xử lý session trước recovery cần giữ đúng ranh giới giữa quyền đã có, bằng chứng đang được kiểm tra và quyền được cấp lại. Tính liên tục của trải nghiệm chỉ có giá trị khi nó không giúp một phiên đã mất tin cậy tiếp tục kiểm soát tài khoản.

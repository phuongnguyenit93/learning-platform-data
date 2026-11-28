# Password change

**Password change** là thao tác thay mật khẩu của một tài khoản sau khi hệ thống xác minh người yêu cầu có quyền thực hiện thay đổi đó. Trong luồng tự phục vụ thông thường, người dùng đang đăng nhập và chứng minh lại quyền kiểm soát tài khoản, thường bằng mật khẩu hiện tại và các yếu tố bổ sung theo chính sách.

Đây là một thay đổi nhạy cảm trong vòng đời danh tính: người hoàn thành thao tác có thể làm mật khẩu cũ mất hiệu lực và ảnh hưởng đến quyền truy cập của các phiên đang mở. Vì vậy, một tính năng đổi mật khẩu cần xử lý cả xác thực, phạm vi tài khoản, lưu trữ credential, phiên đăng nhập và kiểm toán.

Trong nền tảng IAM, đổi mật khẩu thuộc quản lý thông tin xác thực. Nó không tự thay đổi vai trò RBAC, thuộc tính ABAC hay các quyền đã cấp. Sau bài này, người học có thể mô tả một luồng đổi mật khẩu an toàn, nhận ra lỗi cập nhật đồng thời và giải thích vì sao đổi mật khẩu không mặc nhiên thu hồi mọi token.

## 1. Phân biệt đổi mật khẩu với các thao tác liên quan

| Thao tác | Hoàn cảnh | Bằng chứng và phạm vi |
|---|---|---|
| Đổi mật khẩu tự phục vụ | Người dùng muốn thay mật khẩu đang sử dụng | Phiên hợp lệ và xác minh lại theo chính sách; với tài khoản mật khẩu cục bộ thường kiểm tra mật khẩu hiện tại |
| Đặt lại mật khẩu | Người dùng quên hoặc không thể dùng mật khẩu hiện tại | Bằng chứng khôi phục hợp lệ, chẳng hạn token dùng một lần; có luồng xác minh riêng |
| Buộc đổi mật khẩu | Hệ thống yêu cầu thay credential do trạng thái tài khoản hoặc sự cố | Chỉ cho phép luồng hạn chế đến khi hoàn tất; không tự coi một yêu cầu chưa xác thực là đủ |
| Nâng cấp hash | Hệ thống thay thuật toán hoặc tham số bảo vệ | Tính lại bản ghi sau khi có mật khẩu hợp lệ; mật khẩu người dùng có thể không thay đổi |
| Quản trị hỗ trợ khôi phục | Nhân sự được cấp quyền hỗ trợ người dùng | Luồng quản trị riêng, quyền riêng, bằng chứng riêng và dấu vết kiểm toán |

Không biến chức năng đổi mật khẩu thành đặt lại mật khẩu bằng cách bỏ qua trường `currentPassword` khi người dùng không nhập. Khi không còn mật khẩu hiện tại, giao diện cần chuyển sang quy trình khôi phục đúng thiết kế.

OWASP mô tả token hoặc mã khôi phục như bằng chứng có thời hạn và dùng một lần, đồng thời yêu cầu kiểm tra hợp lệ trước khi thay đổi tài khoản. Đây là lý do luồng quên mật khẩu phải có hợp đồng riêng với luồng đổi mật khẩu đang đăng nhập. [OWASP Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html)

Một người có thể đăng nhập bằng passkey hoặc qua SSO mà chưa từng có mật khẩu cục bộ. Với trường hợp đó, cần xác định đây là đổi mật khẩu tại nơi quản lý credential hay là thiết lập thêm phương thức xác thực mới. Không tự tạo một ngoại lệ bỏ kiểm tra chỉ vì tài khoản không có hash mật khẩu.

## 2. Phiên đang đăng nhập chưa đủ cho mọi thay đổi

Giả sử An đăng nhập trên máy dùng chung và quên đăng xuất. Người đến sau có thể đang cầm một phiên hợp lệ của An nhưng không biết mật khẩu. Nếu endpoint chỉ kiểm tra cookie đăng nhập, người đó có thể thay mật khẩu và làm An mất quyền kiểm soát tài khoản.

Một luồng đổi mật khẩu cục bộ cần phân biệt:

- **Tính liên tục của phiên:** yêu cầu thuộc một phiên được hệ thống công nhận.
- **Bằng chứng xác thực lại:** người đang thao tác cung cấp bằng chứng phù hợp cho hành động nhạy cảm.
- **Quyền trên tài khoản đích:** người đó được phép thay credential của đúng tài khoản này.

OWASP nêu hai điều kiện cơ bản cho chức năng đổi mật khẩu: người dùng có phiên đang hoạt động và mật khẩu hiện tại được xác minh. Tài liệu cũng đặt đổi mật khẩu trong nhóm thao tác cần xác thực lại. [OWASP Authentication Cheat Sheet — Change Password Feature](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html#change-password-feature)

Với tài khoản bật MFA hoặc tài khoản đặc quyền, chính sách có thể yêu cầu một bước xác thực bổ sung còn mới. Việc đã từng hoàn thành MFA từ nhiều giờ trước không tự chứng minh người đang cầm phiên hiện tại vẫn là chủ tài khoản.

Nếu sử dụng một bước xác thực lại tách khỏi yêu cầu đổi mật khẩu, máy chủ cần quản lý bằng chứng đó. Ví dụ thiết kế:

```text
reauthenticationGrant = {
    subjectId,
    sessionId,
    purpose: PASSWORD_CHANGE,
    authenticationEpoch,
    expiresAt,
    consumed: false
}
```

Các trường này là mô hình minh họa, không phải định dạng giao thức chuẩn. Máy chủ kiểm tra chủ thể, phiên, mục đích, thời hạn và trạng thái sử dụng. Một giá trị `mfaPassed: true` hoặc `recentlyAuthenticated: true` do trình duyệt tự gửi không thay thế bằng chứng do máy chủ xác minh.

Thời hạn xác thực lại là lựa chọn chính sách dựa trên loại tài khoản và rủi ro. Không có một số phút duy nhất phù hợp cho mọi hệ thống. Nếu bằng chứng hết hạn trước khi giao dịch thay đổi được chốt, hệ thống cần yêu cầu xác thực lại thay vì âm thầm chấp nhận.

## 3. Tài khoản đích phải đến từ ngữ cảnh đáng tin cậy

Một endpoint tự phục vụ có thể dùng đường dẫn:

```text
POST /api/me/password/change
```

Máy chủ lấy tài khoản đích từ principal đã xác minh. Không lấy tài khoản đích chỉ từ một trường `userId` trong nội dung yêu cầu.

Ví dụ nguy cơ:

```text
Principal đã xác thực: account-A
Body do khách gửi:     targetAccountId = account-B

Nếu dịch vụ cập nhật B chỉ vì body ghi B,
quyền sở hữu credential đã bị bỏ qua.
```

Trong ứng dụng nhiều tenant, ngữ cảnh tenant cũng phải được xác minh. Không coi `tenantId` tùy ý từ trình duyệt là bằng chứng người dùng được thao tác trên tenant đó. Nếu một danh tính thuộc nhiều tổ chức, phải xác định credential thuộc danh tính chung hay thuộc từng tài khoản tổ chức trước khi xây dựng endpoint.

Đối với quản trị viên hỗ trợ người khác, nên có luồng quản trị riêng. Quyền xem hồ sơ hoặc sửa thông tin liên hệ không mặc nhiên bao gồm quyền đặt lại mật khẩu. Luồng hỗ trợ cần ghi rõ người thực hiện, người bị tác động, lý do và cơ chế xác minh được áp dụng.

Đây là nơi nguyên tắc ít quyền nhất đi vào thiết kế: dịch vụ và nhân sự chỉ có quyền trên credential cần thiết cho chức năng được giao, thay vì dùng một quyền quản trị chung cho mọi thay đổi tài khoản.

## 4. Kiểm tra mật khẩu mới trước khi cập nhật

Mật khẩu mới cần đi qua cùng chính sách được áp dụng khi tạo tài khoản. Các kiểm tra có thể gồm giới hạn đầu vào, độ dài được hỗ trợ và danh sách mật khẩu phổ biến hoặc đã bị lộ. Chính sách cần được thực thi phía máy chủ; kiểm tra trên giao diện chỉ giúp phản hồi sớm.

NIST SP 800-63B-4 yêu cầu đối chiếu mật khẩu mới với blocklist và không yêu cầu đổi mật khẩu định kỳ theo lịch tùy ý; khi có bằng chứng credential bị xâm phạm thì cần buộc thay đổi. Tài liệu cũng không yêu cầu phối hợp cứng các loại ký tự như điều kiện thành phần mật khẩu. Những yêu cầu này cần được hiểu trong phạm vi áp dụng của NIST. [NIST SP 800-63B-4 — Password Verifiers](https://pages.nist.gov/800-63-4/sp800-63b.html#passwordver)

Khi xây dựng trải nghiệm nhập liệu:

- Cho phép trình quản lý mật khẩu điền mật khẩu hiện tại và sinh mật khẩu mới.
- Phân biệt rõ trường mật khẩu hiện tại với mật khẩu mới.
- Nếu có trường nhập lại, kiểm tra hai giá trị mới khớp nhau để giảm lỗi nhập.
- Không tự cắt ngắn, đổi chữ hoa/thường hoặc loại bỏ khoảng trắng theo một quy tắc không được thiết kế thống nhất.
- Nếu hỗ trợ chuẩn hóa Unicode, dùng cùng quy tắc trong tạo, đổi và xác minh mật khẩu.

Trường nhập lại không phải yếu tố xác thực thứ hai: hai bản nhập giống nhau chỉ cho thấy người dùng đã nhập cùng một giá trị hai lần.

Nếu chính sách không cho phép đặt mật khẩu mới giống mật khẩu hiện tại, hãy xác minh mật khẩu mới với **bản ghi hash hiện tại**. Không băm mới rồi so sánh hai chuỗi hash, vì salt ngẫu nhiên khiến cùng một mật khẩu có thể có nhiều chuỗi mã hóa khác nhau.

Lịch sử mật khẩu, nếu thực sự được yêu cầu, cần giới hạn và bảo vệ như dữ liệu credential. Không lưu mật khẩu cũ dưới dạng rõ hoặc có thể giải mã chỉ để kiểm tra dùng lại. Cũng không tự áp đặt việc giữ nhiều verifier cũ nếu sản phẩm không có nhu cầu hoặc chính sách tương ứng.

## 5. Thiết kế yêu cầu HTTP và bảo vệ trình duyệt

Ví dụ dưới đây mô tả một yêu cầu dùng phiên cookie. Mọi giá trị trong dấu ngoặc nhọn là placeholder:

```http
POST /api/me/password/change HTTP/1.1
Host: identity.example.test
Content-Type: application/json
Cookie: session={session-cookie}
X-CSRF-Token: {csrf-token}

{
  "currentPassword": "{current-password}",
  "newPassword": "{new-password}",
  "confirmNewPassword": "{new-password}"
}
```

Các yêu cầu và trang liên quan phải được truyền qua HTTPS. Không đưa mật khẩu vào query string: URL có thể xuất hiện trong lịch sử, log truy cập hoặc công cụ quan sát.

Với xác thực dựa trên cookie, trình duyệt có thể tự đính kèm cookie vào yêu cầu. Vì vậy, endpoint đổi mật khẩu cần cơ chế chống CSRF phù hợp với framework và mô hình triển khai. Chỉ đổi HTTP method sang `POST` không tự hoàn thành việc chống CSRF; máy chủ phải kiểm tra biện pháp đã chọn. `SameSite` có ích nhưng phạm vi bảo vệ cần được đánh giá theo cấu trúc miền và luồng sử dụng. [OWASP CSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)

Nếu ứng dụng dùng bearer token được JavaScript đính kèm qua `Authorization`, mô hình CSRF khác với cookie tự gửi. Tuy nhiên, việc dùng JSON hoặc CORS không phải bằng chứng rằng mọi đường truy cập đều an toàn. Cần kiểm kê cả cookie, endpoint phụ và loại nội dung mà máy chủ chấp nhận.

Phản hồi thành công có thể chỉ có trạng thái và hướng dẫn bước tiếp theo, ví dụ yêu cầu đăng nhập lại. Không trả mật khẩu mới, mật khẩu cũ hoặc verifier cho khách. Phản hồi chứa thông tin tài khoản nhạy cảm nên có chính sách cache phù hợp, chẳng hạn `Cache-Control: no-store`.

## 6. Một luồng xử lý hoàn chỉnh

Một thiết kế minh họa chọn chính sách **kết thúc các phiên cũ và yêu cầu đăng nhập lại sau khi đổi mật khẩu**. Các sản phẩm khác có thể giữ phiên hiện tại sau xác thực lại, nhưng cần thiết kế rõ cách làm đó.

```mermaid
sequenceDiagram
    participant U as Người dùng
    participant A as API IAM
    participant P as Bộ xác minh và chính sách
    participant D as Kho dữ liệu
    participant W as Bộ xử lý sự kiện
    U->>A: Gửi mật khẩu hiện tại và mật khẩu mới
    A->>P: Kiểm tra phiên, phạm vi và xác thực lại
    P-->>A: Bằng chứng hợp lệ
    A->>D: Đọc credential và phiên bản
    D-->>A: Bản ghi hiện tại
    A->>P: Xác minh mật khẩu cũ và kiểm tra mật khẩu mới
    P-->>A: Bản ghi mật khẩu mới
    A->>D: Giao dịch cập nhật có điều kiện và ghi sự kiện
    D-->>A: Commit thành công
    A-->>U: Đã đổi mật khẩu; cần đăng nhập lại
    D->>W: Sự kiện đã được lưu bền vững
    W->>W: Thông báo và tác vụ đồng bộ có thể retry
```

Các bước quan trọng của luồng:

1. Xác minh phiên, tài khoản đích và biện pháp bảo vệ yêu cầu.
2. Áp dụng giới hạn thử để endpoint không trở thành nơi đoán mật khẩu cũ không giới hạn.
3. Đọc bản ghi credential và phiên bản cần cho kiểm soát đồng thời.
4. Xác minh mật khẩu hiện tại bằng thư viện lưu mật khẩu.
5. Kiểm tra bằng chứng MFA hoặc xác thực lại bổ sung khi chính sách yêu cầu.
6. Kiểm tra mật khẩu mới và tạo bản ghi mới với salt mới.
7. Trong giao dịch, kiểm tra lại các điều kiện có thể thay đổi và cập nhật có điều kiện.
8. Chốt trạng thái vô hiệu hóa phiên cũ theo thiết kế và ghi sự kiện cần phát.
9. Chỉ sau commit mới báo đã thay đổi thành công.

Có thể điều chỉnh thứ tự một số kiểm tra để cân bằng trải nghiệm và chi phí, nhưng không được bỏ mất các điều kiện tại thời điểm cập nhật. Ví dụ tài khoản bị khóa sau khi bắt đầu yêu cầu vẫn phải bị chặn theo chính sách khi giao dịch chuẩn bị thay credential.

## 7. Xác minh đúng mật khẩu và tạo hash mới trong Java

Trong Spring Security, `PasswordEncoder` có hai thao tác phù hợp với bài toán: `matches` xác minh mật khẩu với bản ghi đã mã hóa một chiều và `encode` tạo bản ghi mới. Thuật toán, tham số và khả năng xác minh định dạng cũ phụ thuộc vào cấu hình encoder. [Spring Security — Password Storage](https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html)

Đoạn Java sau chỉ thể hiện cách dùng API, không phải toàn bộ endpoint hoặc giao dịch:

```java
boolean currentPasswordMatches = passwordEncoder.matches(
    currentPassword,
    storedPasswordRecord
);

boolean newPasswordMatchesCurrent = passwordEncoder.matches(
    newPassword,
    storedPasswordRecord
);

String replacementPasswordRecord = passwordEncoder.encode(newPassword);
```

Trong luồng thực tế, chỉ đi tới bước tạo bản ghi thay thế khi mật khẩu hiện tại đã khớp, các bằng chứng bổ sung hợp lệ và mật khẩu mới được chính sách chấp nhận. Chỉ cần kiểm tra `newPasswordMatchesCurrent` nếu chính sách có quy tắc tương ứng.

Không thực hiện cách sau:

```text
encode(currentPassword) == storedPasswordRecord
```

Một encoder có salt ngẫu nhiên có thể tạo chuỗi khác cho cùng mật khẩu ở mỗi lần `encode`. Thư viện xác minh phải đọc salt và tham số của bản ghi đã lưu để kiểm tra đúng.

Ứng dụng cũng cần giới hạn vòng đời dữ liệu đầu vào. Trong Java, một `String` không thể bị xóa tại chỗ theo cách thông thường; không tạo thêm nhiều bản sao hoặc giữ mật khẩu trong đối tượng sống lâu. Chuyển sang `char[]` không tự loại bỏ các bản sao đã có từ framework. Cách xử lý bộ nhớ không thay thế việc tắt log body và che dữ liệu nhạy cảm tại mọi lớp quan sát.

## 8. Giao dịch và hai yêu cầu đổi mật khẩu đồng thời

Giả sử cùng một mật khẩu cũ được dùng trong hai yêu cầu gần đồng thời:

```text
T1: Yêu cầu A đọc bản ghi version 10.
T2: Yêu cầu B cũng đọc bản ghi version 10.
T3: A xác minh mật khẩu cũ và chuẩn bị mật khẩu mới A.
T4: B xác minh mật khẩu cũ và chuẩn bị mật khẩu mới B.
T5: A cập nhật thành công.
T6: B ghi đè A nếu câu UPDATE không kiểm tra version.
```

Người dùng có thể nhìn thấy A báo thành công nhưng mật khẩu A lập tức không dùng được vì B ghi sau. Nghiêm trọng hơn, yêu cầu đã bắt đầu từ trạng thái cũ có thể ghi đè một thay đổi nhằm phục hồi quyền kiểm soát tài khoản.

Một cách xử lý là cập nhật có điều kiện theo phiên bản:

```sql
UPDATE account_credential
SET password_record = :replacement_record,
    row_version = row_version + 1,
    auth_epoch = auth_epoch + 1,
    password_changed_at = :changed_at
WHERE account_id = :trusted_account_id
  AND row_version = :expected_row_version;
```

Ví dụ SQL chỉ minh họa một mô hình dữ liệu. Cần kiểm tra số dòng bị tác động:

- Đúng một dòng: cập nhật có điều kiện đã thành công.
- Không có dòng: bản ghi không còn khớp trạng thái đã xác minh; không báo đổi thành công.
- Số lượng khác dự kiến: cần coi là lỗi toàn vẹn hoặc lỗi thiết kế truy vấn.

Không retry bằng cách đọc version mới rồi ghi mật khẩu mới mà bỏ qua xác minh lại. Làm vậy sẽ biến kiểm soát đồng thời thành hình thức.

Nên phân biệt hai phiên bản trong mô hình minh họa:

| Trường | Ý nghĩa |
|---|---|
| `row_version` | Phát hiện mọi cập nhật cạnh tranh trên bản ghi |
| `auth_epoch` | Đánh dấu thế hệ trạng thái xác thực để vô hiệu hóa bằng chứng hoặc phiên cũ khi cần |

Nâng cấp hash cho cùng một mật khẩu có thể tăng `row_version` nhưng không nhất thiết tăng `auth_epoch`. Đổi mật khẩu thật sự trong chính sách ví dụ tăng cả hai. Hai trường này là lựa chọn thiết kế ứng dụng, không phải claim chuẩn bắt buộc trong JWT hoặc OIDC.

Nếu có bằng chứng xác thực lại dùng một lần, việc kiểm tra và tiêu thụ nó phải phối hợp với giao dịch thay đổi. Bằng chứng dành cho tài khoản A không dùng được cho B; bằng chứng thuộc thế hệ xác thực cũ cũng không tự được chấp nhận sau một thay đổi credential khác.

## 9. Đổi mật khẩu ảnh hưởng gì đến session và token?

Mật khẩu được dùng để thiết lập một phiên hoặc lấy token, nhưng các bằng chứng truy cập được cấp ra thường có trạng thái và thời hạn riêng. Thay `password_record` không tự sửa các token đã phát hành.

| Loại bằng chứng | Việc cần thiết kế sau khi đổi mật khẩu |
|---|---|
| Session lưu phía máy chủ | Xóa, đánh dấu thu hồi hoặc kiểm tra thế hệ xác thực của phiên |
| Refresh token | Thu hồi các token hoặc nhóm token thuộc phạm vi chính sách |
| Access token tự chứa | Có thể còn được chấp nhận đến khi hết hạn nếu nơi kiểm tra không biết trạng thái thu hồi |
| Cookie ghi nhớ đăng nhập | Vô hiệu hóa bản ghi hoặc bí mật liên quan theo thiết kế |
| Token đặt lại mật khẩu chưa dùng | Kiểm tra còn được phép sử dụng sau thay đổi credential hay không |
| Mã/bằng chứng xác thực lại | Không để bằng chứng cũ tiếp tục cho phép thay đổi nhạy cảm ngoài phạm vi |

RFC 7009 quy định cơ chế thu hồi token OAuth và giải thích ảnh hưởng của cách triển khai token đến khả năng thu hồi. Token tự chứa được kiểm tra hoàn toàn cục bộ cần cơ chế bổ sung nếu muốn nơi nhận biết việc thu hồi trước khi token hết hạn. Không suy ra việc đổi mật khẩu sẽ tự gọi hoặc thay thế cơ chế đó. [RFC 7009, mục 2 và 3](https://www.rfc-editor.org/rfc/rfc7009.html#section-3)

Với mô hình `auth_epoch`, dịch vụ có thể lưu thế hệ tại thời điểm cấp phiên và đối chiếu với thế hệ hiện tại khi chấp nhận yêu cầu. Tăng số trong database chỉ có tác dụng thu hồi khi thành phần kiểm tra thực sự sử dụng nó. Nếu một API chỉ xác minh chữ ký JWT và `exp`, thêm số này vào database không tự thay đổi quyết định của API.

Nếu dữ liệu thế hệ được cache hoặc sự kiện thu hồi được truyền bất đồng bộ, phải tính đến khoảng thời gian trạng thái cũ còn được chấp nhận. Cần xác định độ trễ phù hợp với rủi ro và cách xử lý khi thành phần kiểm tra trạng thái không truy cập được.

Một sản phẩm có thể cho người dùng chọn kết thúc các phiên khác trong tình huống đổi mật khẩu thông thường. Với nghi ngờ bị chiếm tài khoản, cơ chế phục hồi cần xem xét cả phiên, MFA, địa chỉ khôi phục và các phương thức đã bị thay đổi; đổi một mật khẩu đơn lẻ có thể chưa đủ để lấy lại quyền kiểm soát.

## 10. Thông báo, kiểm toán và lỗi sau commit

Sau thay đổi thành công, hệ thống nên có thông báo qua kênh đã được thiết lập để chủ tài khoản phát hiện thao tác ngoài ý muốn. Thông báo có thể chứa thời điểm, cách nhận hỗ trợ và hướng xử lý khi không phải người dùng thực hiện. Không gửi mật khẩu trong thông báo.

Một sự kiện kiểm toán có thể mang dữ liệu:

```text
eventType: PASSWORD_CHANGED
actorId: chủ thể thực hiện
subjectId: tài khoản bị tác động
occurredAt: thời điểm commit
requestId: mã đối chiếu kỹ thuật
changeChannel: SELF_SERVICE
result: SUCCESS
```

Không đưa mật khẩu cũ, mật khẩu mới, toàn bộ hash, cookie hoặc token xác thực vào sự kiện. Nếu ghi địa chỉ IP hoặc thông tin thiết bị, chỉ lưu trong phạm vi cần thiết và quản lý quyền truy cập phù hợp.

Gửi email và cập nhật database không phải một thao tác nguyên tử đơn giản. Ví dụ mật khẩu đã thay đổi nhưng dịch vụ email đang lỗi. Không báo rằng mật khẩu vẫn cũ chỉ vì email chưa gửi được.

Một thiết kế có thể ghi sự kiện vào **outbox** trong cùng giao dịch với cập nhật credential. Bộ xử lý đọc sự kiện sau commit và thử lại việc gửi thông báo. Cách này cần xử lý giao hàng lặp bằng mã sự kiện; không lưu mật khẩu vào outbox để phục vụ retry.

Mã giả cho phần ghi dữ liệu:

```text
replacement = encode(newPassword) sau khi mọi kiểm tra ban đầu đạt

begin transaction
    kiểm tra lại trạng thái tài khoản và bằng chứng còn hiệu lực
    cập nhật credential với expectedRowVersion
    nếu không cập nhật đúng một bản ghi: rollback và trả xung đột
    tiêu thụ bằng chứng dùng một lần nếu có
    ghi trạng thái thu hồi/đổi thế hệ xác thực theo thiết kế
    ghi sự kiện PASSWORD_CHANGED vào outbox
commit

trả kết quả mật khẩu đã thay đổi
bộ xử lý sự kiện thực hiện các tác vụ bên ngoài và retry khi cần
```

Outbox giúp lưu ý định thực hiện tác vụ bên ngoài, không bảo đảm mọi hệ thống khác đã thu hồi phiên ngay tại thời điểm commit. Nếu sản phẩm hứa thu hồi tức thời, cơ chế chấp nhận phiên phải đáp ứng được lời hứa đó, kể cả khi bộ xử lý sự kiện chậm hoặc ngừng hoạt động.

## 11. Giới hạn thử và cách trả lỗi

Endpoint đổi mật khẩu có thể bị lạm dụng để thử đoán mật khẩu hiện tại từ một phiên bị chiếm. Chi phí băm cũng khiến yêu cầu liên tục tiêu tốn tài nguyên.

Cần phối hợp giới hạn theo tài khoản, phiên và nguồn yêu cầu với hệ thống chống lạm dụng. Một ngưỡng chặn toàn bộ tài khoản dễ bị dùng để gây khóa tài khoản của người khác; hành vi phản hồi cần cân bằng khả năng phòng vệ và khôi phục quyền truy cập.

| Kết quả | Cách xử lý về nghiệp vụ |
|---|---|
| Phiên không hợp lệ | Yêu cầu xác thực lại theo luồng được hỗ trợ |
| Bằng chứng bổ sung thiếu hoặc hết hạn | Không cập nhật credential; yêu cầu bước còn thiếu |
| Mật khẩu hiện tại không khớp | Không thay đổi dữ liệu; ghi nhận thất bại có giới hạn |
| Mật khẩu mới bị chính sách từ chối | Nêu lý do có thể hành động được mà không phản chiếu mật khẩu |
| Bản ghi đã thay đổi đồng thời | Không ghi đè; yêu cầu bắt đầu lại từ trạng thái hiện tại |
| Database rollback | Không báo đổi thành công |
| Thông báo lỗi sau commit | Giữ kết quả thay đổi đúng thực tế; xử lý retry tác vụ phụ |

Endpoint tự phục vụ không cần nhận email của một tài khoản bất kỳ để dò xem tài khoản đó có tồn tại. Thông báo lỗi cũng không nên trả stack trace, bản ghi hash hay chi tiết nội bộ.

Nếu khách bị mất kết nối sau commit, họ có thể không biết thao tác đã thành công. Hệ thống cần hướng dẫn kiểm tra hoặc đăng nhập lại; không tự động lặp thao tác với mật khẩu cũ rồi coi mọi lần thất bại là dấu hiệu rằng lần đầu chưa thành công.

## 12. SSO, tài khoản đặc quyền và danh tính workload

### Ứng dụng dùng SSO

Khi IdP là nơi quản lý mật khẩu, ứng dụng nhận kết quả OIDC không nên tự đổi một hash cục bộ không liên quan rồi báo đã đổi mật khẩu SSO. Hãy đưa người dùng đến chức năng quản lý tài khoản của IdP hoặc dùng API được IdP hỗ trợ với quyền phù hợp.

Phiên ở ứng dụng và phiên tại IdP là các trạng thái khác nhau. Đổi mật khẩu tại IdP có thể không tự kết thúc mọi phiên của mọi ứng dụng nếu không có chính sách và cơ chế đồng bộ tương ứng. Cần kiểm tra hành vi thực tế của hệ thống liên kết danh tính.

### Tài khoản đặc quyền

Với tài khoản quản trị, thiết kế có thể yêu cầu xác thực mạnh hơn, thông báo chặt chẽ hơn và khả năng truy vết rõ hơn. Nhân sự hỗ trợ không cần biết mật khẩu mới của người dùng để hoàn thành một quy trình khôi phục đúng thiết kế.

Sau sự cố, không tự xóa MFA hoặc hạ quyền kiểm tra chỉ để thao tác đổi mật khẩu chạy được. Thay đổi phương thức MFA là một hành động nhạy cảm riêng, cần bằng chứng và quyền tương ứng.

### Danh tính workload

Workload dùng khóa, chứng chỉ hoặc token ngắn hạn cần luồng cấp phát và xoay vòng credential của máy. Không sao chép mẫu giao diện đổi mật khẩu của người dùng sang mọi service account. Phải xác định đúng loại bí mật, chủ thể quản lý và thành phần phụ thuộc trước khi thay đổi.

## 13. Các tình huống cần kiểm chứng trong thiết kế

Những tình huống sau giúp người học theo dõi đầy đủ kết quả, thay vì chỉ nhìn một phản hồi HTTP thành công:

1. Người dùng hợp lệ đổi mật khẩu: mật khẩu cũ không đăng nhập được, mật khẩu mới đăng nhập được.
2. Người đang giữ phiên nhưng không biết mật khẩu hiện tại: không thể hoàn tất luồng đổi mật khẩu cục bộ thông thường.
3. Khách sửa định danh đích trong body: không thể thay credential của tài khoản khác.
4. Thiếu bằng chứng CSRF trong mô hình cookie có yêu cầu CSRF: dữ liệu không thay đổi.
5. Mật khẩu mới không đạt chính sách: verifier cũ và trạng thái phiên vẫn tuân theo kết quả thất bại đã thiết kế.
6. Hai yêu cầu cùng đọc một version: không có cập nhật ghi đè âm thầm.
7. Thông báo bên ngoài bị lỗi sau commit: mật khẩu mới vẫn là trạng thái đúng và sự kiện còn được xử lý lại.
8. Token cũ được gửi đến một API khác: hành vi phù hợp với chính sách thu hồi và khoảng trễ đã công bố.
9. Người dùng SSO chưa có mật khẩu cục bộ: hệ thống dẫn tới đúng nơi quản lý thông tin xác thực.
10. Log, trace và sự kiện kiểm toán: có đủ dữ liệu đối chiếu thao tác nhưng không chứa bí mật đăng nhập.

Một tính năng đổi mật khẩu hoàn chỉnh cần giữ được các quan hệ này: đúng chủ thể được phép thay đúng credential, thay đổi được chốt nhất quán, các bằng chứng cũ được xử lý theo chính sách và người dùng có thể nhận biết kết quả. Chỉ cập nhật một cột hash chưa thể hiện đầy đủ những điều đó.

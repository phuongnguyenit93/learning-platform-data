# Reauthentication — Xác thực lại trong vòng đời phiên

## 1. Vì sao một phiên hợp lệ vẫn có thể cần xác thực lại?

Reauthentication là việc yêu cầu người dùng cung cấp lại bằng chứng xác thực đáp ứng chính sách, dù trước đó đã có một lần đăng nhập. Mục tiêu có thể là xác nhận người dùng vẫn hiện diện, làm mới bằng chứng đã cũ hoặc đáp ứng yêu cầu trước một thao tác nhạy cảm.

Ví dụ, An đăng nhập cổng nhân sự buổi sáng rồi để máy mở. Đến buổi chiều, trình duyệt vẫn có cookie phiên. Cookie giúp server nhận ra phiên, nhưng không tự chứng minh người đang thao tác vẫn là An hoặc bằng chứng MFA ban đầu còn đủ mới để thay đổi tài khoản nhận lương.

NIST mô tả xác thực lại định kỳ nhằm xác nhận sự hiện diện tiếp tục của người dùng trong phiên, với các giới hạn tổng thể và không hoạt động được áp dụng theo chính sách assurance. [Nguồn: NIST SP 800-63B-4, Reauthentication](https://pages.nist.gov/800-63-4/sp800-63b.html#reauthentication).

Trong hệ thống IAM, reauthentication tạo thêm một sự kiện xác thực có thể kiểm chứng. Nó không tự cấp thêm vai trò, không khôi phục tài khoản đã bị vô hiệu hóa và không chứng minh mọi hành động tiếp theo đều đã được người dùng phê duyệt.

## 2. Phân biệt với refresh, step-up và recovery

| Cơ chế | Câu hỏi chính | Kết quả có thể có |
| --- | --- | --- |
| Authentication ban đầu | Chủ thể có kiểm soát authenticator của tài khoản không? | Thiết lập ngữ cảnh xác thực ban đầu |
| Reauthentication | Có bằng chứng xác thực mới đáp ứng yêu cầu hiện tại không? | Làm mới hoặc tái thiết lập ngữ cảnh phù hợp |
| Step-up authentication | Có cần mức hoặc phương thức xác thực khác để làm việc này không? | Thu thập thêm bằng chứng hoặc dùng phương thức đáp ứng chính sách cao hơn |
| Refresh token | Client còn được phép xin token mới không? | Token mới theo quyền và điều kiện được cấp |
| Authorization | Chủ thể được phép tác động tài nguyên nào? | Cho phép hoặc từ chối hành động cụ thể |
| Account recovery | Khi không dùng được authenticator hiện có, làm sao khôi phục quyền kiểm soát? | Quyền khôi phục hoặc thiết lập credential theo quy trình riêng |

Reauthentication và step-up có thể diễn ra trong cùng một luồng nhưng không đồng nghĩa. Nhập lại mật khẩu vừa mới có thể đáp ứng yêu cầu độ mới cho một thao tác, trong khi vẫn không đáp ứng yêu cầu MFA chống phishing của thao tác khác.

Một access token mới phát hành cũng chưa chứng minh người dùng vừa cung cấp bằng chứng mới. Nếu token được cấp qua refresh token hoặc từ phiên IdP đã có, thời điểm phát hành và thời điểm người dùng thực sự xác thực có thể rất khác nhau.

## 3. Khi nào nên kích hoạt reauthentication?

Các nhóm tình huống thường gặp gồm hết giới hạn thời gian, thay đổi credential, thao tác có tác động lớn và tín hiệu rủi ro. OWASP khuyến nghị xác thực lại cho chức năng nhạy cảm hoặc sau các sự kiện như recovery, thay đổi thông tin bảo mật và hành vi đáng ngờ. [Nguồn: OWASP Authentication Cheat Sheet, Reauthentication After Risk Events](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html#reauthentication-after-risk-events).

Trong cổng nhân sự giả định, nhóm IAM có thể xác định chính sách như sau:

| Tình huống | Yêu cầu cần được đánh giá |
| --- | --- |
| Phiên chạm inactivity hoặc overall timeout | Không tiếp tục dùng ngữ cảnh cũ cho tài nguyên bảo vệ |
| Đổi mật khẩu, email khôi phục hoặc phương thức MFA | Có bằng chứng phù hợp từ người được phép quản lý credential |
| Thay tài khoản nhận lương | Có xác thực đủ mới và phạm vi xác nhận đúng thao tác |
| Cấp hoặc thay vai trò quản trị | Có quyền quản trị hiện hành và mức xác thực được yêu cầu |
| Đăng nhập hoặc thao tác có tín hiệu bất thường | Đánh giá rủi ro để yêu cầu bằng chứng bổ sung hoặc từ chối |
| Sau recovery liên quan đến nghi chiếm tài khoản | Đánh giá lại credential, phiên và quyền được phép tiếp tục |

Tín hiệu mạng hoặc thiết bị hỗ trợ quyết định rủi ro, không tự trở thành bằng chứng danh tính. Ví dụ, đổi IP có thể do mạng di động; giữ nguyên IP cũng không chứng minh trình duyệt chưa bị chiếm.

Không đặt yêu cầu chỉ ở nút bấm của giao diện. Nếu backend vẫn xử lý request trực tiếp khi thiếu bằng chứng cần thiết, hộp thoại “vui lòng xác thực lại” không tạo ra kiểm soát truy cập.

## 4. Đánh giá đúng chủ thể, độ mới và phương thức

Một kết quả reauthentication chỉ có ích khi đáp ứng đồng thời các chiều mà chính sách yêu cầu.

| Chiều đánh giá | Câu hỏi phải trả lời | Ví dụ sai |
| --- | --- | --- |
| Chủ thể và ngữ cảnh | Bằng chứng thuộc đúng tài khoản, tenant và giao dịch không? | Đăng nhập tài khoản khác trong popup rồi nâng phiên hiện tại |
| Độ mới | Bằng chứng được tạo đủ gần thời điểm thực hiện hành động không? | Dùng sự kiện MFA từ hôm trước để đổi factor |
| Phương thức hoặc assurance | Loại bằng chứng có đáp ứng yêu cầu của hành động không? | Mật khẩu mới nhập nhưng hành động yêu cầu MFA chống phishing |
| Trạng thái hiện tại | Tài khoản, credential và quyền còn hợp lệ không? | Vai trò đã bị thu hồi nhưng grant xác thực lại vẫn được coi là quyền quản trị |

Ví dụ, cổng nhân sự chọn yêu cầu một sự kiện xác thực phù hợp trong 5 phút gần nhất khi thay thông tin nhận lương. Con số này là quyết định minh họa của sản phẩm, không phải mốc bắt buộc từ mọi chuẩn.

```text
đủ mới ⇔ server_now - verified_authentication_time <= allowed_age
```

Thời điểm phải đến từ sự kiện được server xác minh hoặc nguồn danh tính tin cậy, không phải đồng hồ do client tự gửi. Cần định nghĩa sai lệch đồng hồ cho phép, xử lý thời điểm bất hợp lý trong tương lai và ranh giới khi bằng chứng vừa hết hạn.

Không duy trì một timestamp chung `lastMfaAt` rồi cập nhật nó sau mọi lần nhập lại mật khẩu. Nên biết sự kiện nào thỏa chính sách nào; làm mới bằng chứng mức thấp không tự làm mới bằng chứng mức cao.

## 5. Chọn phương thức phù hợp với tài khoản và mục đích

Reauthentication có thể sử dụng mật khẩu hiện tại, authenticator MFA đã gắn, passkey hoặc một phương thức được chấp nhận khác. Lựa chọn cần dựa trên chính sách và khả năng đã đăng ký, thay vì luôn ép mọi tài khoản phải nhập mật khẩu cục bộ.

Tài khoản SSO hoặc passwordless có thể không có mật khẩu tại ứng dụng. Tạo thêm một mật khẩu cục bộ chỉ để phục vụ hộp thoại xác thực lại sẽ tạo thêm credential và đường truy cập cần quản lý.

Nếu mục tiêu là chống phiên bị lấy cắp, chỉ trình lại cookie đang có chưa cung cấp bằng chứng độc lập mới. Nếu mục tiêu yêu cầu chống phishing, một OTP nhập lại vẫn có thể không đáp ứng dù mã còn mới và thuộc đúng tài khoản.

Không có quy tắc rằng mọi lần reauthentication đều bắt buộc lặp lại toàn bộ factor. NIST cho phép một trường hợp AAL2 sử dụng mật khẩu hoặc so sánh sinh trắc cùng session secret khi inactivity timeout đã xảy ra nhưng overall timeout chưa hết; AAL3 có yêu cầu khác. Việc áp dụng phải đúng điều kiện, không khái quát thành “một factor luôn đủ”. [Nguồn: NIST SP 800-63B-4, AAL2 và AAL3 Reauthentication](https://pages.nist.gov/800-63-4/sp800-63b.html#aal2).

Khi không dùng được phương thức yêu cầu, hệ thống cần chuyển sang recovery hoặc một ngoại lệ được quản lý. Không tự thay bằng câu hỏi bảo mật hoặc một nút xác nhận đơn giản mà vẫn giữ nguyên nhãn assurance.

## 6. Ràng buộc giao dịch xác thực lại ở server

Đối với một hành động nhạy cảm, backend có thể tạo giao dịch xác thực lại độc lập với việc render hộp thoại. Ví dụ bản ghi:

```text
reauth_transaction_id
subject_id
tenant_id
session_binding
required_authentication_policy
purpose
action_reference
resource_reference
resource_version
created_at
expires_at
attempt_count
state
challenge_reference
```

Đây là mô hình minh họa, không phải schema của module hoặc của một giao thức chuẩn. Tài khoản và phiên phải được xác định từ ngữ cảnh đã được backend chấp nhận. Client không được đổi chúng để xác thực cho người khác.

Các trạng thái có thể gồm `PENDING`, `VERIFIED`, `CONSUMED`, `EXPIRED` và `CANCELLED`. Bằng chứng chỉ được sử dụng trong mục đích và thời hạn được cho phép. Một challenge đăng nhập không được dùng lại như challenge phê duyệt thay factor nếu thiết kế không có ràng buộc tương ứng.

Với WebAuthn hoặc OTP, dùng thư viện và quy trình xác minh của phương thức đó. Không dùng một trường `reauthenticated=true` hoặc kết quả “thành công” do frontend tự khai. Đối với xác thực qua IdP, kết quả cũng phải đi qua kiểm tra giao thức và chủ thể.

Nếu sau thành công server xoay session ID, giao dịch cần được chuyển liên kết có kiểm soát sang phiên mới. Không giữ một grant có thể được trình từ mọi phiên khác của cùng người dùng, trừ khi chính sách chủ động thiết kế phạm vi như vậy.

## 7. Tách sự kiện xác thực khỏi quyền thực hiện hành động

Có hai cách sử dụng kết quả thường gặp:

- Cập nhật authentication context của phiên để ghi nhận một sự kiện mới, với phương thức và thời điểm đã kiểm chứng.
- Cấp một grant ngắn hạn cho hành động hoặc nhóm hành động đã định nghĩa.

Không phải mọi sản phẩm đều cần grant riêng cho mỗi lần thao tác. Tuy nhiên, khi dùng grant, cần mô tả rõ nó cho phép việc gì, trong phiên nào, có dùng một lần hay không và điều gì làm nó mất hiệu lực.

Ví dụ, một grant cho phép thay email khôi phục không nên dùng để xóa một authenticator hoặc cấp vai trò quản trị. Nếu dữ liệu nghiệp vụ thay đổi sau khi người dùng xác nhận, phải kiểm tra lại sự tương ứng với hành động mà họ định thực hiện.

Ràng buộc grant với hành động ở server giúp ngăn nhầm mục đích, nhưng không tự biến một lần đăng nhập thành chữ ký mật mã cho toàn bộ nội dung giao dịch. Với yêu cầu phê duyệt nội dung cụ thể, cần thiết kế transaction authorization phù hợp và hiển thị dữ liệu cần xác nhận một cách tin cậy.

## 8. Luồng xử lý tham chiếu

Một luồng xác thực lại cho thao tác nhạy cảm có thể đi theo trình tự:

```text
Người dùng yêu cầu hành động
        ↓
Backend kiểm tra quyền và chính sách xác thực
        ↓ thiếu bằng chứng đủ mới hoặc phù hợp
Tạo giao dịch reauthentication có phạm vi, challenge và thời hạn
        ↓
Xác minh bằng chứng mới qua phương thức được chấp nhận
        ↓
Ghi sự kiện hoặc grant phía server
        ↓
Backend kiểm tra lại hành động và tiêu thụ grant theo chính sách
        ↓
Thực hiện thao tác và ghi audit không chứa bí mật
```

Mã giả cho hành động dùng grant một lần:

```text
executeSensitiveAction(actor, action, grantReference):
    begin transaction:
        grant = lockCurrentGrant(grantReference)
        now = trustedServerTime()

        requireGrantVerifiedUnexpiredAndUnused(grant, now)
        requireSameSubjectTenantAndSession(actor, grant)
        requireAccountAndSessionStillAllowed(actor)
        requireAuthenticationPolicyStillSatisfied(grant, action)
        requireActionAndResourceVersionMatch(grant, action)
        requireCurrentAuthorization(actor, action)

        applyActionWithConcurrencyCheck(action)
        markGrantConsumed(grant)
        appendAuditWithoutSecrets(actor, action, grant)
    commit
```

Mã giả giả định `grantReference` được xử lý như dữ liệu không tin cậy và không cho phép bỏ qua kiểm tra chủ sở hữu. Nó không triển khai xác minh mật mã hoặc mọi chi tiết repository.

Tiêu thụ grant và ghi thay đổi cần có quan hệ nguyên tử phù hợp. Nếu thao tác gọi hệ thống ngoài, không thể giả định transaction database tự bao phủ cả hệ thống đó; cần cơ chế điều phối, outbox hoặc idempotency theo nghiệp vụ.

Hai request cạnh tranh không được cùng dùng một grant một lần để thực hiện hai hành động. Nếu một request timeout sau khi đã commit, retry cần tìm được kết quả theo hợp đồng idempotency thay vì tạo tác động lặp hoặc tùy tiện mở lại grant.

## 9. Reauthentication qua SSO/OIDC

Ứng dụng và IdP quản lý phiên riêng. Redirect về IdP có thể nhận kết quả từ phiên SSO đang tồn tại mà không có tương tác xác thực mới. Vì vậy, “đã đi qua trang đăng nhập của IdP” chưa chứng minh yêu cầu reauthentication đã được đáp ứng.

OIDC cung cấp `max_age` để yêu cầu độ mới của xác thực; khi dùng tham số này, ID Token trả về phải có `auth_time`. `prompt=login` yêu cầu xác thực lại, còn `acr` mô tả authentication context. Tham số yêu cầu không thay thế việc kiểm tra kết quả thực nhận. [Nguồn: OpenID Connect Core 1.0, Authentication Request](https://openid.net/specs/openid-connect-core-1_0.html#AuthRequest).

Ví dụ chính sách cổng nhân sự: ứng dụng yêu cầu sự kiện phù hợp không quá 5 phút và một authentication context đã thống nhất với IdP. Khi callback tới, backend phải kiểm tra token và giao dịch OIDC, sau đó xác minh rằng chủ thể vẫn là tài khoản đang cần xác thực lại.

Chủ thể liên kết cần được nhận diện theo issuer và subject đã được thiết lập phù hợp, không chỉ dựa vào email hiển thị. Nếu popup IdP chuyển sang tài khoản khác, đó không phải bằng chứng xác thực lại cho tài khoản hiện tại.

Không dùng `iat` làm thời điểm người dùng xác thực: nó là thời điểm phát hành token. Cũng không coi claim chung `amr=["mfa"]` là mô tả đủ cho mọi yêu cầu, chẳng hạn phishing resistance; cần hợp đồng về ý nghĩa các giá trị với IdP.

`acr_values` chỉ yêu cầu các context theo ưu tiên trong OIDC Core, nên ứng dụng vẫn phải đánh giá `acr` thực nhận. Nếu bằng chứng thiếu, quá cũ hoặc không đáp ứng, dừng hành động nhạy cảm và xử lý theo chính sách thay vì tự hạ yêu cầu.

Sau callback, tiếp tục bảo vệ CSRF, ràng buộc giao dịch, đích điều hướng và session fixation theo thiết kế của ứng dụng. Không nhận một URL quay lại tùy ý rồi chuyển hướng kèm credential hoặc grant tới đó.

## 10. API OAuth có thể báo yêu cầu xác thực mới

Resource server có thể nhận access token hợp lệ về chữ ký, thời hạn và đối tượng nhận, nhưng sự kiện xác thực gắn với token vẫn quá cũ hoặc chưa đủ mức cho tài nguyên.

RFC 9470 định nghĩa lỗi `insufficient_user_authentication` cùng tham số challenge như `max_age` và `acr_values` để truyền đạt yêu cầu này. Ví dụ dưới minh họa yêu cầu độ mới tối đa 300 giây. [Nguồn: RFC 9470, Authentication Requirements Challenge](https://www.rfc-editor.org/rfc/rfc9470.html#section-3).

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="insufficient_user_authentication", max_age="300"
```

Header không tự thực hiện reauthentication. Client cần đi qua authorization server theo luồng thích hợp rồi trình token đáp ứng yêu cầu; resource server kiểm tra lại bằng chứng gắn với token mới. Không chỉ retry request bằng nguyên token hoặc âm thầm refresh mà không đáp ứng độ mới được yêu cầu.

Phải phân biệt thiếu mức xác thực với thiếu quyền. Nếu người dùng không có quyền sửa tài nguyên, thực hiện MFA thêm lần nữa không tự tạo quyền đó. API cần quyết định và mô tả lỗi phù hợp, đồng thời tránh vòng lặp yêu cầu xác thực vô hạn cho một thao tác vốn bị cấm.

Không mặc định mọi OAuth client đều có người dùng hiện diện. Workload dùng danh tính máy cần một chính sách credential và quyền riêng; không ép job nền mở màn hình nhập mật khẩu người dùng để giải quyết một vấn đề phân quyền của workload.

## 11. Bảo vệ endpoint xác thực lại và vòng đời phiên

Endpoint reauthentication cũng là endpoint xác thực, cần kênh được bảo vệ, giới hạn thử, kiểm tra challenge và xử lý lỗi không tiết lộ bí mật. Không log mật khẩu, OTP, assertion nguyên vẹn, session cookie hoặc grant có thể sử dụng.

Với phiên dùng cookie, cần chống CSRF cho các thay đổi trạng thái và hành động nhạy cảm. Yêu cầu nhập lại credential không thay thế toàn bộ bảo vệ CSRF hoặc XSS. Giao diện nên giúp người dùng nhận ra họ đang xác thực cho dịch vụ và mục đích nào.

Các lần thử thất bại phải được ghi nhận bền vững. Không tăng bộ đếm trong transaction rồi rollback nó mỗi khi trả lỗi. Nếu có nhiều request song song, giới hạn phải được thực thi ở server theo tài khoản, phiên hoặc giao dịch cùng các tín hiệu thích hợp.

Sau reauthentication, dùng cơ chế session manager để cập nhật ngữ cảnh và thay session identifier khi chính sách yêu cầu, đặc biệt khi chuyển mức bảo vệ. Bí mật hoặc context cũ không được tự tiếp tục mở quyền mới. Không tự nâng toàn bộ phiên trên mọi thiết bị chỉ vì một phiên vừa xác thực lại.

Đổi mật khẩu, thay factor hoặc recovery còn có thể yêu cầu thu hồi các phiên khác. Phạm vi đó là một quyết định an ninh riêng với việc cấp grant cho hành động hiện tại; cần được thực thi ở mọi node và thành phần nhận token liên quan.

Khi phát hiện dấu hiệu tài khoản hoặc authenticator đã bị xâm phạm, không coi việc đối thủ tiếp tục trình được credential là đủ để kết thúc xử lý sự cố. Cần đánh giá thu hồi, recovery và trạng thái tài khoản theo bằng chứng đang có.

## 12. Trải nghiệm người dùng và kiểm toán

Giao diện nên giải thích ngắn gọn mục đích: “Xác thực lại để thay email khôi phục” rõ ràng hơn một hộp nhập mật khẩu xuất hiện không có ngữ cảnh. Cho phép phương thức phù hợp với tài khoản, kể cả SSO hoặc passkey khi được hỗ trợ.

Nếu người dùng hủy xác thực lại cho một hành động, ứng dụng không được thực hiện hành động đó. Tùy chính sách và tình trạng phiên, họ có thể tiếp tục những chức năng ít nhạy cảm hơn; không bắt buộc mọi lần hủy đều phải đăng xuất toàn bộ hệ thống.

Khi dịch vụ xác thực tạm lỗi, thông báo và giữ thao tác chưa hoàn tất. Không tự cấp grant thành công để giảm lỗi giao diện. Các luồng ngoại lệ vận hành cần phạm vi và kiểm soát riêng.

Audit có thể ghi chủ thể, lý do yêu cầu, phương thức đã xác minh, thời điểm, phiên bản chính sách, mục đích grant và kết quả hành động. Một mã tham chiếu sự kiện giúp liên kết bằng chứng với thao tác mà không phát lại credential.

Các chỉ số có ích gồm tỷ lệ hủy, thất bại, challenge hết hạn, callback sai chủ thể, số lần lặp step-up và grant bị từ chối vì quyền đã thay đổi. Chúng giúp phân biệt lỗi tích hợp với hành vi lạm dụng mà không cần thu thập dữ liệu xác thực thô.

## 13. Tình huống kiểm chứng thiết kế

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Cookie hợp lệ nhưng bằng chứng quá cũ cho hành động | Backend yêu cầu xác thực lại, chưa thực hiện hành động |
| Token mới có `iat` mới nhưng `auth_time` cũ | Không coi bằng chứng là vừa được tạo |
| Đúng chủ thể, đủ mới nhưng phương thức không đáp ứng | Yêu cầu phương thức phù hợp hoặc từ chối |
| IdP trả tài khoản khác | Không nâng phiên của tài khoản ban đầu |
| Client sửa boolean hoặc thời điểm xác thực | Không tạo được context hay grant hợp lệ |
| Dùng grant đổi email để xóa MFA | Bị từ chối do sai mục đích |
| Quyền bị thu hồi sau khi cấp grant | Hành động vẫn bị từ chối khi kiểm tra lại quyền |
| Dữ liệu tài nguyên thay đổi sau bước xác nhận | Phát hiện phiên bản không khớp và xử lý lại theo chính sách |
| Hai request cùng dùng grant một lần | Chỉ một tác động nghiệp vụ hợp lệ |
| Người dùng hủy hoặc challenge hết hạn | Hành động không được thực hiện |
| Tắt JavaScript và gọi API trực tiếp | Yêu cầu reauthentication vẫn được thực thi |
| Bật log chẩn đoán | Không lộ credential, cookie hoặc grant sử dụng được |

Cần kiểm tra cả ranh giới thời gian, callback từ IdP và tình huống cạnh tranh. Việc hiện hộp thoại rồi quay lại trang thành công chỉ chứng minh luồng giao diện hoạt động, chưa chứng minh backend ràng buộc bằng chứng đúng cách.

## 14. Bài tập vận dụng

Một cổng quản trị yêu cầu nhập lại mật khẩu trước khi thay vai trò. Frontend lưu `reauthenticated=true` trong trình duyệt trong 30 phút; API chỉ kiểm tra cờ đó. Với tài khoản SSO, ứng dụng dùng thời điểm `iat` của ID Token làm thời điểm xác thực mới. Quyền quản trị không được kiểm tra lại sau khi popup hoàn tất.

Hãy thiết kế lại và giải thích:

1. Những dữ liệu nào phải do server quản lý để biết đúng chủ thể, phương thức và độ mới?
2. Vì sao token mới hoặc cờ frontend không đủ chứng minh reauthentication?
3. Luồng SSO phải yêu cầu và kiểm tra bằng chứng nào khi callback quay về?
4. Grant cần phạm vi và cách tiêu thụ ra sao để không dùng cho hành động khác hoặc hai lần cạnh tranh?
5. Nếu vai trò bị thu hồi giữa lúc xác thực lại và thực hiện thao tác, backend phải quyết định thế nào?

Phương án cần chỉ rõ sự kiện xác thực nào đã được kiểm chứng, nó được dùng ở đâu và trong bao lâu. Reauthentication bảo vệ vòng đời danh tính khi kết quả của nó được ràng buộc với đúng phiên và chính sách, còn quyền truy cập luôn được đánh giá tại thời điểm thực hiện hành động.

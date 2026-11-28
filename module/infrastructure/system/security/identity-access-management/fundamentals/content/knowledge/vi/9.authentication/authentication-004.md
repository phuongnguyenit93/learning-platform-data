# Step-up authentication

## 1. Khi nào cần xác thực bổ sung?

**Step-up authentication** là việc yêu cầu người dùng đáp ứng điều kiện xác thực bổ sung khi ngữ cảnh hiện tại chưa đủ cho một tài nguyên hoặc thao tác. Yêu cầu có thể liên quan đến phương thức mạnh hơn, tính chống phishing, độ mới của lần xác thực hoặc một tổ hợp điều kiện.

Ví dụ, Lan đăng nhập cổng quản trị nhân sự để xem danh sách nhân viên. Khi Lan muốn gán role quản trị cho Minh, backend yêu cầu xác thực bổ sung bằng phương thức phù hợp trước khi tiếp tục. Lan đã đăng nhập, nhưng bằng chứng hiện có chưa đủ cho thao tác đó.

OWASP đề cập việc xác thực lại cho chức năng nhạy cảm và sau các sự kiện rủi ro như khôi phục tài khoản hoặc thay đổi thông tin quan trọng. [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html#reauthentication-after-risk-events).

Lợi ích của step-up là diễn đạt yêu cầu theo ngữ cảnh sử dụng. Người dùng có thể hoàn thành công việc thông thường với chính sách cơ bản, còn các hành động cần bảo vệ thêm được đặt sau một điều kiện riêng. Cơ chế này phải được thực thi ở backend; một hộp thoại trên giao diện không tự bảo vệ API.

## 2. Phân biệt step-up với các khái niệm liên quan

| Khái niệm | Vai trò |
| --- | --- |
| Đăng nhập ban đầu | Thiết lập danh tính và ngữ cảnh xác thực ban đầu. |
| MFA | Sử dụng nhiều loại yếu tố xác thực khác nhau theo quá trình áp dụng. |
| Reauthentication | Thực hiện xác thực lại để có bằng chứng phù hợp hoặc mới hơn. |
| Step-up | Yêu cầu đáp ứng điều kiện xác thực bổ sung cho ngữ cảnh đang truy cập. |
| Authorization | Quyết định người dùng có quyền thực hiện hành động trên tài nguyên hay không. |
| Phê duyệt nghiệp vụ | Đáp ứng điều kiện như quản lý duyệt hoặc hai người cùng phê duyệt. |

Các cơ chế này có thể được kết hợp. Một lần đăng nhập ban đầu đã dùng MFA vẫn có thể cần xác thực lại vì bằng chứng quá cũ. Một yêu cầu step-up có thể được đáp ứng bằng một authenticator phù hợp mà không nhất thiết xuất hiện nhiều màn hình.

Với ví dụ của Lan, hoàn thành step-up chỉ bổ sung bằng chứng xác thực. Backend vẫn phải kiểm tra Lan có quyền gán đúng role, cho đúng người, trong đúng tenant. Nếu Lan không có quyền đó, việc nhập thêm một mã không tạo ra quyền mới.

Tương tự, xác thực lại không thay cho bước phê duyệt của quản lý nếu quy trình cấp đặc quyền yêu cầu phê duyệt. Hai điều kiện bảo vệ những ranh giới khác nhau.

## 3. Đánh giá độ mạnh, độ mới và phạm vi sử dụng

Một chính sách step-up cần trả lời ba nhóm câu hỏi:

| Chiều đánh giá | Ví dụ câu hỏi |
| --- | --- |
| Đặc tính xác thực | Phương thức đã dùng có đáp ứng lớp ngữ cảnh hoặc yêu cầu chống phishing không? |
| Độ mới | Sự kiện xác thực phù hợp xảy ra cách đây bao lâu? |
| Phạm vi sử dụng | Bằng chứng được chấp nhận cho phiên, hành động và tài nguyên nào? |

NIST xem AAL là yêu cầu đối với quá trình xác thực, đồng thời nêu rằng tín hiệu rủi ro không thay thế yếu tố xác thực hoặc tự làm thay đổi AAL. [NIST — Authentication Assurance Levels](https://pages.nist.gov/800-63-4/sp800-63b/aal/).

Vì vậy, một điểm rủi ro thấp không phải bằng chứng Lan vừa sử dụng authenticator. Ngược lại, điểm rủi ro cao có thể khiến hệ thống yêu cầu thêm bằng chứng, hoặc từ chối theo chính sách nếu tình huống không thể xử lý an toàn chỉ bằng xác thực bổ sung.

Hãy phân biệt yêu cầu “có MFA” với yêu cầu “dùng phương thức chống phishing”. Một mã được nhập vào trang giả có thể bị chuyển tiếp ngay sang phiên khác. Nhóm thiết kế phải chọn phương thức đáp ứng đúng đặc tính cần thiết thay vì chỉ đếm số bước người dùng thực hiện.

## 4. Chọn đúng điểm kích hoạt

Trong ứng dụng IAM, các thao tác sau có thể được đánh giá để đặt điều kiện bổ sung:

- Thêm hoặc thay đổi authenticator, địa chỉ khôi phục hoặc phương thức MFA.
- Gán role đặc quyền, thay đổi chính sách truy cập hoặc cấu hình federation.
- Xuất dữ liệu nhạy cảm, tạo credential có phạm vi lớn hoặc thay đổi cấu hình bảo mật.
- Tiếp tục thao tác quan trọng sau một lần khôi phục tài khoản.

Đây là những tình huống minh họa; mỗi hệ thống phải xác định yêu cầu theo hậu quả của xác thực nhầm và nhu cầu sử dụng thực tế.

Không phải mọi thao tác có tên “quản trị” đều cần cùng một điều kiện. Chẳng hạn, xem trạng thái đồng bộ danh tính có thể có hậu quả khác với thay đổi rule cấp quyền cho toàn tổ chức. Chính sách nên bám vào hành động, tài nguyên và phạm vi ảnh hưởng.

Khi dùng tín hiệu hành vi, cần mô tả cách quyết định. Một thay đổi IP có thể do người dùng chuyển mạng; nó không tự chứng minh tài khoản bị chiếm. Hệ thống cần sử dụng tín hiệu trong ngữ cảnh và có kết quả rõ ràng cho từng mức rủi ro.

## 5. Viết chính sách có thể kiểm tra

Ví dụ ứng dụng tự định nghĩa:

```yaml
policyId: grant-admin-role-v3
operation: ROLE_GRANT
acceptedAuthenticationContexts:
  - urn:example:acr:privileged-v1
maximumAuthenticationAgeSeconds: 300
evidenceScope: SINGLE_OPERATION
pendingOperationLifetimeSeconds: 120
```

Đây là schema và giá trị của bài học, không phải cấu hình chuẩn bắt buộc của NIST hoặc OIDC. Nhóm triển khai giả định lớp `privileged-v1` đã có tài liệu quy định phương thức và đặc tính được chấp nhận.

Trong ví dụ:

- Bằng chứng phải đáp ứng lớp ngữ cảnh mà backend chấp nhận.
- Sự kiện xác thực tương ứng không được cũ hơn 300 giây khi đánh giá.
- Lần cho phép tiếp tục được giới hạn vào thao tác đang chờ.
- Thao tác đang chờ tự hết hạn sau 120 giây theo đồng hồ máy chủ.

Hai thời hạn có ý nghĩa riêng. Bằng chứng xác thực có thể vẫn đủ mới nhưng một thao tác chờ đã hết hạn; ngược lại, thao tác còn hạn không có nghĩa bằng chứng hiện tại đã đáp ứng chính sách.

Backend phải xác định chính sách từ cấu hình tin cậy. Người gọi không được tự giảm `maximumAuthenticationAgeSeconds`, đổi `policyId` sang loại dễ hơn hoặc khai báo kết quả đã đạt chỉ bằng một trường trong request.

## 6. Luồng thực hiện từ request tới thay đổi nghiệp vụ

Một luồng minh họa cho việc Lan gán role quản trị:

1. Backend nhận yêu cầu và xác minh phiên hoặc access token hiện tại.
2. Backend kiểm tra quyền của Lan trên tenant, người nhận và role được yêu cầu.
3. Backend xác định chính sách xác thực cho thao tác này.
4. Nếu bằng chứng hiện có chưa đủ, backend chưa thay đổi role và tạo yêu cầu step-up.
5. Lan hoàn thành quá trình xác thực phù hợp qua thành phần tin cậy.
6. Backend xác minh kết quả, liên kết với đúng chủ thể và yêu cầu đang chờ.
7. Backend kiểm tra lại chính sách, quyền và dữ liệu nghiệp vụ tại thời điểm thực hiện.
8. Backend ghi thay đổi, đánh dấu kết quả của thao tác và phát sinh sự kiện kiểm toán thích hợp.

Nếu ngữ cảnh hiện tại đã đáp ứng chính sách, ứng dụng có thể tiếp tục theo điều kiện được thiết kế, không cần tạo một lời nhắc vô ích. Nếu người dùng hủy hoặc không hoàn thành xác thực bổ sung, thao tác nhạy cảm vẫn chưa được thực hiện.

Mấu chốt là giữ ranh giới giữa **đang chờ bằng chứng** và **đã được thực hiện**. Không gán role trước rồi mới yêu cầu xác thực, vì lúc đó hậu quả cần ngăn chặn đã xảy ra.

## 7. Liên kết kết quả với đúng người và đúng thao tác

Ví dụ backend lưu một yêu cầu chờ:

```json
{
  "pending_operation_id": "pending-81",
  "actor_subject": "user-42",
  "session_reference": "server-session-ref-7",
  "operation": "ROLE_GRANT",
  "tenant_id": "tenant-a",
  "target_subject": "user-73",
  "requested_role": "ADMIN",
  "policy_id": "grant-admin-role-v3",
  "status": "PENDING"
}
```

Đây là dữ liệu ứng dụng tự định nghĩa và được backend bảo vệ. Mã `pending_operation_id` chỉ giúp liên kết; biết mã đó không được coi là đã xác thực hoặc đã được cấp phép.

Khi nhận kết quả, cần kiểm tra ít nhất:

- Kết quả đến từ nguồn xác thực tin cậy và thuộc đúng luồng đã khởi tạo.
- Chủ thể phù hợp với người đang thực hiện thao tác; với federation cần xác định chủ thể trong đúng miền issuer.
- Liên kết phiên vẫn phù hợp với quy trình, kể cả khi định danh phiên được đổi trong lúc xác thực lại.
- Thao tác chưa hết hạn, chưa bị hủy và chưa được sử dụng theo cách trái chính sách.
- Tenant, người nhận và role vẫn trùng với nội dung được đánh giá.

Ví dụ, xác thực bổ sung cho thao tác cấp role `AUDITOR` không nên được dùng lại bằng cách thay request thành role `ADMIN`. Tương tự, kết quả của tài khoản Minh không được gắn vào thao tác đang chờ của Lan chỉ vì cả hai cùng đăng nhập trên trình duyệt đó.

OWASP Transaction Authorization nhấn mạnh kiểm soát phía máy chủ và liên kết việc cho phép với dữ liệu giao dịch. Việc chứng minh người dùng vừa xác thực và việc họ đã xác nhận chính nội dung giao dịch cần được thiết kế rõ ràng. [OWASP — Transaction Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transaction_Authorization_Cheat_Sheet.html).

Một bước WebAuthn hoặc MFA chung không tự chứng minh người dùng đã đọc và đồng ý mọi tham số nghiệp vụ. Nếu hệ thống cần xác nhận giao dịch cụ thể, phải bổ sung quy trình tương ứng.

## 8. Step-up trong OpenID Connect

OIDC cung cấp những thông tin và tham số liên quan:

| Tên | Ý nghĩa |
| --- | --- |
| `acr` | Lớp ngữ cảnh xác thực đã được đáp ứng. |
| `amr` | Các phương thức xác thực đã sử dụng. |
| `auth_time` | Thời điểm xác thực người dùng. |
| `acr_values` | Các lớp ngữ cảnh được client yêu cầu theo thứ tự ưu tiên. |
| `max_age` | Độ tuổi tối đa của lần xác thực chủ động, tính bằng giây. |

`acr_values` là yêu cầu, không phải kết quả bảo đảm. Trong OIDC Core, nó yêu cầu `acr` như một voluntary claim. Khi sử dụng `max_age`, ID Token trả về phải có `auth_time`. Các bên cần thống nhất ý nghĩa giá trị `acr`. [OpenID Connect Core — Authentication Request](https://openid.net/specs/openid-connect-core-1_0.html#AuthRequest).

Ví dụ client yêu cầu lớp `urn:example:acr:privileged-v1` và `max_age=300`. Sau khi người dùng quay lại, backend vẫn phải xác minh kết quả và đánh giá giá trị thực nhận được. Một response thành công nhưng thiếu bằng chứng cần thiết chưa đủ để thực hiện thao tác.

Không so sánh chuỗi `acr` theo thứ tự từ điển hoặc giả định mọi issuer có cùng thang mức. Ứng dụng cần ánh xạ các lớp đã thỏa thuận; nếu chưa biết ý nghĩa thì không tự diễn giải thành một mức cao.

## 9. API OAuth có thể yêu cầu step-up như thế nào?

RFC 9470 định nghĩa lỗi `insufficient_user_authentication` và các tham số `acr_values`, `max_age` trong Bearer challenge để resource server truyền yêu cầu về ngữ cảnh hoặc độ mới tới client. [RFC 9470 — Authentication Requirements Challenge](https://www.rfc-editor.org/rfc/rfc9470.html#section-3).

Ví dụ minh họa, header được viết trên một dòng:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="insufficient_user_authentication", acr_values="urn:example:acr:privileged-v1", max_age="300"
```

Client tham gia luồng hỗ trợ có thể yêu cầu authorization server thực hiện xác thực phù hợp rồi lấy access token mới và gọi lại API. Resource server phải kiểm tra token mới có thực sự đáp ứng yêu cầu.

Đây là cơ chế của profile được triển khai, không có nghĩa mọi hệ thống OAuth tự hỗ trợ step-up chỉ vì biết tham số `acr_values`. Cần thống nhất khả năng của client, authorization server và resource server.

API dùng thông tin xác thực từ access token đã được xác minh hoặc nguồn tương ứng đã thỏa thuận. RFC 9068 mô tả các claim như `auth_time`, `acr`, `amr` trong JWT access token và các quy tắc xác minh loại token này. [RFC 9068 — JWT Access Token Profile](https://www.rfc-editor.org/rfc/rfc9068.html).

Không lấy ID Token được phát hành cho một client rồi mặc định dùng nó làm access token gọi mọi API. Cũng không tin các claim chỉ vì đã giải mã được payload JWT; nguồn phát hành, loại token, audience và những điều kiện xác minh liên quan phải phù hợp.

Nếu không thể đáp ứng yêu cầu, luồng cần kết thúc với kết quả rõ ràng. Client không nên lặp vô hạn việc lấy token rồi gọi lại cùng API với bằng chứng không đổi.

## 10. Độ mới phải dựa vào sự kiện xác thực

Giả sử Lan xác thực lúc 08:00, token mới được phát hành lúc 10:00 và Lan yêu cầu cấp role lúc 10:01. Tuổi token chỉ một phút, nhưng sự kiện xác thực có thể đã cũ hơn hai giờ.

OIDC quy định `auth_time` trong ID Token được trả qua refresh, nếu có, vẫn phản ánh lần xác thực ban đầu thay vì thời điểm phát hành mới. [OpenID Connect Core — Successful Refresh Response](https://openid.net/specs/openid-connect-core-1_0.html#RefreshTokenResponse).

Với chính sách trong bài, backend đánh giá tuổi của **sự kiện xác thực đáp ứng lớp yêu cầu**. Không lấy thời điểm mở hộp thoại, thời điểm client nhận callback hoặc trường `iat` của token làm bằng chứng thay thế.

Nếu ngữ cảnh quản lý nhiều yếu tố xảy ra ở các thời điểm khác nhau, cần có quy ước rõ ràng về sự kiện nào đáp ứng chính sách và độ mới nào được sử dụng. Một trường `lastSeenAt` của phiên không đủ để mô tả những điều đó.

NIST cũng phân biệt việc duy trì phiên với xác thực lại và không cho phép coi phiên có AAL cao hơn sự kiện xác thực tạo ra nó. [NIST — Session Management](https://pages.nist.gov/800-63-4/sp800-63b/session/).

Do đó, xoay cookie hoặc refresh token không tự biến thành một lần người dùng xác thực chủ động. Ứng dụng cần quản lý cả giới hạn phiên cơ bản và cửa sổ cho phép thao tác nhạy cảm.

## 11. Hoàn tất thao tác và xử lý cạnh tranh

Trong lúc Lan đang xác thực bổ sung, các điều kiện có thể thay đổi:

- Tài khoản Lan bị vô hiệu hóa hoặc bị thu hồi quyền cấp role.
- Tenant bị khóa theo quy trình vận hành.
- Role yêu cầu đã bị xóa hoặc thay đổi điều kiện cấp.
- Một tab khác đã thực hiện hoặc hủy thao tác đang chờ.

Vì vậy, việc thực hiện cuối cùng cần kiểm tra lại trạng thái và authorization. Kết quả step-up là một đầu vào trong quyết định, không phải bản chụp quyền được chấp nhận mãi về sau.

Với bằng chứng dùng một lần, thao tác đánh dấu đã sử dụng phải phối hợp an toàn với thay đổi nghiệp vụ. Nếu hai request đồng thời cùng đọc trạng thái `PENDING` và đều thực hiện, một cờ “đã xác thực” không ngăn được tác động lặp. Ứng dụng cần cơ chế giao dịch, chuyển trạng thái có điều kiện hoặc cách phối hợp bền vững phù hợp kiến trúc.

Khi mạng lỗi sau khi ghi thay đổi, client có thể gửi lại request. Hệ thống cần phân biệt tiếp tục hỏi kết quả của cùng thao tác với tạo một thao tác mới. Thiết kế idempotency giúp xử lý trường hợp này; nó có mục đích khác với việc xác minh authenticator.

## 12. Thất bại, khôi phục và trải nghiệm người dùng

Một thiết kế đầy đủ cần quy định kết quả khi:

- Người dùng hủy yêu cầu hoặc quá thời gian.
- Không có phương thức đáp ứng chính sách.
- Dịch vụ xác thực không hoạt động hoặc trả về context không phù hợp.
- Người dùng đăng nhập thành một tài khoản khác trong quá trình SSO.
- Có dấu hiệu tấn công hoặc số lần thử vượt giới hạn.

Trong các trường hợp đó, backend chưa thực hiện thao tác đang được bảo vệ. Không âm thầm thay yêu cầu mạnh bằng một phương thức dễ hơn chỉ để đi tiếp. Nếu chính sách có phương án thay thế, phải mô tả điều kiện và bảo vệ tương ứng.

Mất authenticator là bài toán recovery. Quy trình recovery có thể cho phép người dùng lấy lại khả năng truy cập theo chính sách, nhưng không nên trở thành đường bỏ qua điều kiện của thao tác đặc quyền.

Giao diện nên giải thích ngắn gọn thao tác nào đang cần xác thực thêm, cho phép hủy và giữ lại dữ liệu nhập không nhạy cảm khi phù hợp. Tránh hiển thị bí mật nội bộ của hệ thống đánh giá rủi ro hoặc hướng người dùng qua những vòng lặp không có lối thoát.

Step-up của người dùng cũng cần được tách khỏi credential của workload. Một lời nhắc tương tác không phù hợp với mọi luồng dịch vụ tự động; các luồng đó cần chính sách xác thực và ủy quyền riêng.

## 13. Audit và tình huống kiểm tra

Audit nên giúp giải thích thao tác nào yêu cầu step-up, vì chính sách nào, bằng chứng nào đã được xác nhận và quyết định cuối là gì. Loại trừ mật khẩu, OTP, access token và session ID nguyên dạng khỏi log theo hướng dẫn phù hợp. [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html).

Ví dụ các sự kiện ứng dụng tự định nghĩa gồm `step_up_requested`, `step_up_satisfied`, `step_up_cancelled`, `step_up_expired` và `protected_operation_completed`. Phân biệt “xác thực bổ sung thành công” với “thay đổi nghiệp vụ đã hoàn tất” giúp điều tra cả trường hợp bị từ chối sau bước xác thực.

| Tình huống kiểm tra | Kết quả mong đợi trong ví dụ |
| --- | --- |
| Phiên cơ bản gọi thẳng API cấp role | API yêu cầu điều kiện bổ sung trước khi thay đổi. |
| Frontend gửi `stepUpPassed=true` | Không dùng cờ tự khai làm bằng chứng. |
| Xác thực đủ mạnh nhưng đã quá cũ | Yêu cầu bằng chứng mới theo chính sách. |
| Token vừa refresh nhưng lần xác thực cũ | Không dùng tuổi token để vượt điều kiện độ mới. |
| Callback thuộc tài khoản khác | Không gắn vào thao tác của chủ thể ban đầu. |
| Đổi tenant, người nhận hoặc role sau step-up | Không sử dụng bằng chứng ngoài phạm vi đã đánh giá. |
| `acr` không nhận biết hoặc context bị thiếu | Không mặc định coi là đáp ứng. |
| Quyền bị thu hồi khi người dùng đang step-up | Kiểm tra lại và từ chối thay đổi nếu không còn quyền. |
| Hai request cùng dùng kết quả một lần | Không tạo hai tác động ngoài thiết kế. |
| Người dùng hủy hoặc yêu cầu chờ hết hạn | Không thực hiện thao tác được bảo vệ. |
| Authorization server không đáp ứng lớp yêu cầu | Trả kết quả rõ ràng, không hạ chính sách hoặc lặp vô hạn. |

Khi thiết kế step-up, cần mô tả được chuỗi quyết định từ yêu cầu ban đầu tới lần thay đổi cuối cùng: chính sách nào được áp dụng, bằng chứng nào được tin, nó gắn với ai và được sử dụng trong phạm vi nào. Cách mô tả đó giúp nối xác thực, MFA, phiên, SSO và kiểm soát đặc quyền thành một luồng IAM có thể kiểm tra.

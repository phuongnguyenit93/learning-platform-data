# Authentication freshness — Thời điểm xác thực còn đủ mới

**Authentication freshness** là độ mới của lần xác thực người dùng gần nhất mà hệ thống có thể tin cậy cho một hành động cụ thể. Một phiên đăng nhập đang hoạt động không có nghĩa người dùng vừa xác thực. Session cookie có thể tồn tại nhiều giờ, access token có thể vừa được cấp lại, và người dùng có thể liên tục sử dụng ứng dụng mà không chứng minh lại quyền kiểm soát authenticator. Khi người dùng thực hiện hành động nhạy cảm, hệ thống cần biết lần xác thực gần nhất diễn ra khi nào, bằng phương thức nào và đạt mức bảo đảm nào.

**Step-up authentication** yêu cầu người dùng xác thực lại hoặc bổ sung yếu tố khi ngữ cảnh hiện tại chưa đủ mạnh cho hành động sắp thực hiện. Freshness là một phần của quyết định step-up: hệ thống đánh giá tuổi của lần xác thực, loại yếu tố đã dùng, mức assurance, rủi ro của request và policy của tài nguyên. Ví dụ, phiên đăng nhập từ đầu ngày có thể đủ để đọc tài liệu, nhưng đổi email khôi phục, thêm passkey mới hoặc chuyển tiền có thể cần xác thực gần đây bằng phương thức mạnh hơn.

Bài học thuộc module SECURITY_AUTHENTICATION_FUNDAMENTALS, tập trung vào credential, mật khẩu, MFA, passkey, token, session và ranh giới tin cậy. Người học cần phân biệt authentication freshness với session lifetime, token lifetime và activity timeout; biết cách áp policy theo từng hành động, xác minh bằng chứng từ identity provider và tránh làm mới freshness chỉ bằng hoạt động nền.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Định nghĩa authentication freshness và giải thích vì sao phiên còn hiệu lực chưa đủ chứng minh người dùng vừa xác thực.
2. Phân biệt thời điểm tạo session, hoạt động gần nhất, thời điểm cấp token và thời điểm xác thực người dùng.
3. Xây dựng freshness window theo mức rủi ro của hành động.
4. Thiết kế step-up flow để yêu cầu xác thực lại bằng yếu tố phù hợp.
5. Đọc và kiểm tra các tín hiệu như OIDC `auth_time`, `acr`, `amr` và `max_age` theo profile đã thống nhất.
6. Ràng buộc kết quả step-up với đúng account, session, transaction và hành động.
7. Xử lý clock skew, token refresh, session renewal, retry, replay và downgrade.
8. Thiết kế fallback an toàn khi authenticator không khả dụng mà không âm thầm hạ assurance.
9. Viết kiểm thử cho fresh/stale authentication, yếu tố không đủ mạnh, issuer không tin cậy và hành động nhạy cảm.

## 2. Freshness có nghĩa gì?

Freshness đo khoảng thời gian từ lần xác thực người dùng gần nhất tới thời điểm kiểm tra policy. Một cách biểu diễn đơn giản:

\[
\text{authentication age} = \text{current time} - \text{auth time}
\]

Nếu policy cho phép tối đa 10 phút, một lần xác thực cách đây 3 phút có thể được xem là fresh; lần xác thực cách đây 45 phút là stale đối với hành động đó. Con số chỉ là ví dụ. Mỗi dịch vụ phải chọn thời hạn theo rủi ro, loại credential, assurance cần thiết và yêu cầu pháp lý/nghiệp vụ.

Freshness không phải thuộc tính nhị phân toàn cục của tài khoản. Cùng một lần xác thực có thể đủ mới cho hành động này nhưng quá cũ cho hành động khác.

| Hành động | Ví dụ policy freshness | Lý do |
| --- | --- | --- |
| Xem trang cá nhân hoặc tài liệu thông thường | Có thể chấp nhận phiên còn hạn mà không yêu cầu xác thực mới | Rủi ro thấp hơn và cần trải nghiệm liên tục. |
| Xem dữ liệu cá nhân nhạy cảm | Yêu cầu xác thực trong một khoảng thời gian gần đây theo policy | Giảm nguy cơ người khác dùng phiên mở sẵn. |
| Đổi email hoặc số điện thoại khôi phục | Yêu cầu xác thực mới và có thể cần MFA/passkey | Thay đổi kênh khôi phục có thể chiếm quyền kiểm soát tài khoản. |
| Thêm/xóa passkey, security key hoặc TOTP | Yêu cầu step-up và xác minh ceremony | Credential mới có thể tạo đường truy cập lâu dài. |
| Tắt MFA hoặc tạo recovery code | Yêu cầu assurance cao và có thể cần kiểm tra rủi ro bổ sung | Làm giảm lớp bảo vệ tài khoản. |
| Phê duyệt thanh toán hoặc thay đổi quyền quản trị | Yêu cầu xác thực gần thời điểm giao dịch, yếu tố phù hợp và transaction binding | Hạn chế session hijacking và phê duyệt nhầm. |

Không sao chép các thời hạn ví dụ này thành tiêu chuẩn chung. Hãy ghi rõ chủ sở hữu policy, lý do, phạm vi, thời hạn, yếu tố được chấp nhận và cách xử lý khi không thể xác minh freshness.

## 3. Freshness khác session age, idle timeout và token age

Các mốc thời gian sau thường bị nhầm lẫn:

| Mốc | Ý nghĩa | Có chứng minh người dùng vừa xác thực không? |
| --- | --- | --- |
| `session_created_at` | Thời điểm server tạo session | Không. Session có thể được tạo sau một lần đăng nhập cũ hoặc được khôi phục từ cơ chế khác. |
| `last_seen_at` / idle activity | Thời điểm request gần nhất sử dụng phiên | Không. Request nền hoặc thao tác thông thường không phải xác thực. |
| `token_iat` | Thời điểm token được phát hành | Không nhất thiết. Token có thể được refresh mà không có tương tác xác thực người dùng. |
| `token_exp` | Thời điểm token hết hạn | Không. Đây là giới hạn sử dụng token. |
| `auth_time` | Thời điểm identity provider ghi nhận người dùng đã xác thực | Có thể là bằng chứng freshness nếu issuer đáng tin và semantics được hiểu đúng. |
| `step_up_completed_at` | Thời điểm hệ thống ghi nhận lần step-up hoàn tất | Có thể dùng cho policy nội bộ nếu event được xác minh, ràng buộc và audit đúng. |

Một người dùng có thể hoạt động liên tục, khiến idle timeout được gia hạn, nhưng lần xác thực ban đầu vẫn ngày càng cũ. Tương tự, refresh token có thể cấp access token mới mỗi giờ mà không xác thực lại người dùng. Nếu hệ thống lấy `iat` hoặc `last_seen_at` thay cho `auth_time`, attacker chiếm một phiên lâu dài có thể được xem nhầm là vừa xác thực.

### 3.1. Ví dụ timeline

~~~mermaid
timeline
    title Session activity không làm mới authentication freshness
    09:00 : Người dùng xác thực bằng passkey
          : auth_time = 09:00
    09:05 : Access token được cấp
          : token_iat = 09:05
    10:00 : Access token được refresh
          : token_iat mới = 10:00
          : auth_time vẫn = 09:00
    10:20 : Người dùng mở trang hồ sơ
          : last_seen_at = 10:20
          : auth_time vẫn = 09:00
    10:25 : Người dùng yêu cầu đổi email recovery
          : Policy yêu cầu auth age tối đa 5 phút
          : Phải step-up
    10:27 : Người dùng hoàn tất passkey challenge
          : Ghi nhận authentication event mới
~~~

Trong ví dụ, token mới và hoạt động gần đây không làm lần xác thực lúc 09:00 trở nên mới hơn. Chỉ một sự kiện xác thực người dùng mới được xác minh theo policy mới cập nhật freshness.

## 4. Mô hình dữ liệu cho authentication event

Để đánh giá freshness, hệ thống cần lưu một sự kiện xác thực có nguồn gốc và ngữ cảnh rõ ràng. Không nên chỉ có một trường boolean như `recently_authenticated=true`.

Một record khái niệm:

~~~text
AuthenticationEvent:
  event_id
  account_id
  session_id
  issuer
  authenticated_at
  recorded_at
  authentication_methods
  assurance_context
  authenticator_references
  transaction_id
  result
  policy_version
  source
~~~

Các trường có ý nghĩa:
- `authenticated_at`: thời điểm sự kiện xác thực thực sự hoàn tất theo nguồn đáng tin.
- `recorded_at`: thời điểm ứng dụng ghi nhận event; có thể khác do network delay hoặc queue.
- `authentication_methods`: phương thức/nhóm yếu tố đã dùng theo semantics được thống nhất.
- `assurance_context`: mức assurance hoặc context đã được issuer xác nhận.
- `authenticator_references`: tham chiếu nội bộ tới credential liên quan; không lưu secret.
- `transaction_id`: liên kết step-up với hành động đang chờ nếu có.
- `policy_version`: policy đã dùng để đánh giá.

Freshness nên được suy ra từ event được xác minh, thay vì tin timestamp do browser gửi. Client không được tự gửi `auth_time=now` hoặc tự khai `acr=high`. Timestamp và assurance phải đến từ identity provider đã tin cậy hoặc từ server-side ceremony đã xác minh.

### 4.1. Nguồn thời gian và clock skew

Hệ thống cần đồng bộ thời gian giữa identity provider, backend, database và resource server. Sai lệch đồng hồ có thể khiến token bị coi là tương lai, authentication age âm hoặc session bị đánh giá sai.

- Dùng nguồn thời gian hệ thống đáng tin và đồng bộ NTP phù hợp.
- Lưu timestamp ở dạng UTC; chỉ chuyển múi giờ khi hiển thị.
- Định nghĩa clock skew tolerance rõ ràng, giới hạn nhỏ và có lý do.
- Không chấp nhận timestamp tương lai vượt tolerance.
- Nếu issuer và relying party lệch giờ, ghi nhận sai lệch và xử lý theo policy; không tự kéo dài freshness vô hạn.
- Dùng monotonic clock cho đo thời lượng nội bộ khi thích hợp; dùng timestamp có nguồn rõ cho audit và trao đổi liên hệ thống.

## 5. Freshness policy theo hành động và rủi ro

Một policy nên mô tả tối thiểu:

| Thành phần | Câu hỏi |
| --- | --- |
| Action/resource | Hành động hoặc dữ liệu nào được bảo vệ? |
| Maximum authentication age | Lần xác thực gần nhất được phép cũ tối đa bao lâu? |
| Required assurance | Cần mức assurance hoặc context nào? |
| Allowed authenticators | Passkey, security key, MFA, password re-entry hay phương thức khác? |
| Transaction binding | Xác thực phải gắn với giao dịch cụ thể nào? |
| Risk signals | Có cần tăng cường khi thiết bị, vị trí, IP hoặc hành vi bất thường không? |
| Fallback | Nếu authenticator không khả dụng thì xử lý ra sao? |
| Audit | Ghi sự kiện, policy version và kết quả nào? |

### 5.1. Ma trận policy minh họa

| Hành động | Freshness tối đa minh họa | Assurance/điều kiện bổ sung |
| --- | --- | --- |
| Đọc nội dung học tập thông thường | 8 giờ hoặc theo session policy | Session hợp lệ và authorization đúng. |
| Xem hồ sơ cá nhân nhạy cảm | 15 phút | Có thể yêu cầu MFA tùy rủi ro. |
| Thay email recovery | 5 phút | Step-up bằng passkey/security key hoặc phương thức được policy chấp nhận; xác minh kênh mới. |
| Thêm authenticator mới | 5 phút | Reauthentication, transaction binding và enrollment verification. |
| Tắt MFA | 2 phút | Assurance cao hơn, risk review và có thể delay/notification. |
| Cấp quyền admin | Ngay trong transaction | Phương thức chống phishing, phê duyệt bổ sung và audit. |

Đây chỉ là ví dụ minh họa cách cấu trúc policy, không phải ngưỡng khuyến nghị áp dụng chung. Tài khoản có quyền cao, dữ liệu nhạy cảm và môi trường có yêu cầu tuân thủ cần đánh giá riêng.

### 5.2. Freshness và assurance là hai trục

Một lần xác thực vừa diễn ra nhưng chỉ bằng yếu tố yếu có thể không đủ cho hành động cần assurance cao. Ngược lại, một lần xác thực bằng passkey mạnh nhưng diễn ra quá lâu có thể không còn đủ fresh.

<math value="\\text{Step-up required} = (\\text{auth age} > \\text{max age}) \\lor (\\text{assurance} < \\text{required assurance})"/>

Ngoài hai điều kiện này, policy có thể yêu cầu ràng buộc thiết bị, transaction, tenant hoặc risk signals. Không cộng điểm các yếu tố theo cách tùy tiện để biến một phương thức yếu thành assurance cao.

## 6. Step-up authentication flow

Khi người dùng yêu cầu hành động nhạy cảm, backend đánh giá session, authentication event và policy. Nếu lần xác thực cũ hoặc assurance không đủ, hệ thống tạo một step-up transaction có thời hạn và gắn với hành động.

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant APP as Ứng dụng
    participant RP as Relying Party / Backend
    participant IDP as Identity Provider
    participant DB as Session + Auth Event Store
    U->>APP: Yêu cầu đổi email recovery
    APP->>RP: POST /account/recovery-email
    RP->>DB: Đọc session và auth event
    DB-->>RP: auth_time cũ hơn policy
    RP->>RP: Tạo step-up transaction + challenge
    RP-->>APP: Yêu cầu xác thực lại
    APP->>IDP: Authorization request có max_age / assurance request
    IDP->>U: Xác thực lại bằng phương thức phù hợp
    U-->>IDP: Hoàn tất authenticator challenge
    IDP-->>APP: Authorization response / token
    APP->>RP: Gửi response và transaction binding
    RP->>IDP: Xác minh issuer, signature, auth_time, acr, nonce
    IDP-->>RP: Claims đã xác minh
    RP->>DB: Ghi authentication event mới
    RP->>RP: Kiểm tra freshness + assurance + transaction
    RP-->>APP: Cho phép tiếp tục hoặc từ chối
~~~

Không cho client tự quyết định step-up đã thành công. Backend phải xác minh kết quả từ issuer hoặc tự xác minh ceremony, sau đó kiểm tra đúng account/session và transaction đang chờ.

### 6.1. Ràng buộc với đúng hành động

Step-up cho một hành động không nên tự động trở thành vé thông hành cho mọi hành động nhạy cảm khác. Transaction nên gắn:
- Account và session đang thực hiện.
- Action/resource và tham số quan trọng.
- Nonce/challenge ngẫu nhiên, thời hạn và trạng thái một lần.
- Authenticator/assurance yêu cầu.
- Kết quả và thời điểm hoàn tất.

Ví dụ, xác thực để đổi email recovery không nên được tái sử dụng để cấp quyền quản trị. Nếu transaction hết hạn, đã tiêu thụ hoặc tham số hành động thay đổi, phải tạo transaction mới.

## 7. OIDC: auth_time, max_age, acr và amr

OpenID Connect cung cấp các tín hiệu hữu ích để client đánh giá authentication event. Cần hiểu chính xác ý nghĩa và chỉ tin claim từ issuer đã được xác minh.

### 7.1. auth_time

`auth_time` là claim trong ID Token biểu thị thời điểm end-user authentication diễn ra theo OIDC. Client có thể dùng nó để tính authentication age. Claim này không giống `iat`:
- `auth_time` nói về thời điểm xác thực người dùng.
- `iat` nói về thời điểm ID Token được phát hành.

Khi token được phát hành sau một lần refresh hoặc một quy trình không xác thực lại người dùng, `iat` mới hơn không chứng minh `auth_time` mới hơn. Client phải kiểm tra chữ ký, issuer, audience, thời hạn, nonce và các claim cần thiết trước khi sử dụng `auth_time`.

Nếu ID Token không có `auth_time` trong một luồng/policy cần freshness, không tự suy ra từ `iat`. Yêu cầu issuer cung cấp claim theo profile phù hợp hoặc dùng một nguồn xác minh server-side khác.

### 7.2. max_age

OIDC Authorization Request có thể dùng `max_age` để yêu cầu authorization server bảo đảm lần xác thực người dùng gần nhất không cũ hơn khoảng thời gian chỉ định. Nếu lần xác thực trước đã quá cũ, OP cần tương tác xác thực lại theo OIDC Core; khi `max_age` được yêu cầu, ID Token cần chứa `auth_time`.

Ví dụ request minh họa:

~~~http
GET /authorize?
  response_type=code&
  client_id=studyhub-web&
  redirect_uri=https%3A%2F%2Fapp.studyhub.example%2Fcallback&
  scope=openid%20profile&
  max_age=300&
  state=<random-state>&
  nonce=<random-nonce>
~~~

`max_age=300` có nghĩa client yêu cầu authentication age tối đa 300 giây theo semantics OIDC. Đây là yêu cầu tới OP; client vẫn phải xác minh ID Token và tự kiểm tra `auth_time` theo policy của mình. Không mặc định mọi OP hỗ trợ giống nhau hoặc mọi cấu hình sẽ ép dùng yếu tố mạnh.

### 7.3. prompt=login không đồng nghĩa assurance cao

`prompt=login` yêu cầu OP hiển thị tương tác đăng nhập theo semantics OIDC. Nó không tự chứng minh người dùng đã dùng MFA, passkey hay yếu tố chống phishing. Người dùng có thể nhập lại cùng mật khẩu yếu.

Nếu hành động cần một assurance cụ thể, client phải yêu cầu và kiểm tra authentication context phù hợp, không chỉ thêm `prompt=login`.

### 7.4. acr và amr

- `acr` (Authentication Context Class Reference) biểu thị lớp/context xác thực mà OP khẳng định theo profile đã thống nhất.
- `amr` (Authentication Methods References) có thể mô tả phương thức xác thực đã sử dụng.

Không tự giả định một chuỗi như `mfa`, `pwd` hoặc `hwk` có cùng ý nghĩa giữa mọi issuer. Client và OP cần thống nhất profile, giá trị, semantics và cách ánh xạ sang policy nội bộ. Một `acr` cao chỉ có ý nghĩa khi relying party biết issuer đã định nghĩa và bảo đảm điều gì.

Yêu cầu `acr_values` có thể gợi ý context mong muốn cho OP, nhưng request không bảo đảm OP sẽ cấp đúng context. Client phải kiểm tra giá trị trả về và từ chối/step-up tiếp nếu không đạt.

## 8. SAML và các hệ thống không dùng OIDC

Không phải mọi hệ thống đều dùng OIDC. Trong SAML, assertion có thể chứa thông tin về thời điểm xác thực và context, chẳng hạn `AuthnInstant` và `AuthnContextClassRef`. Relying party cần kiểm tra issuer, chữ ký, audience, recipient, điều kiện thời gian, subject confirmation và semantics của context theo metadata/profile đã tin cậy.

Trong hệ thống nội bộ, backend có thể ghi authentication event khi đã xác minh passkey/password/MFA. Khi đó cần bảo đảm:
- Event chỉ được tạo sau khi ceremony thành công.
- Timestamp do server tạo hoặc được lấy từ nguồn đáng tin.
- Event gắn với account/session đúng.
- Phương thức và assurance được mô tả theo policy, không do client tự khai.
- Event không thể sửa bởi service hoặc user không có quyền.

Nếu identity provider không cung cấp tín hiệu freshness đáng tin cậy, ứng dụng không nên tự đoán từ thời điểm cấp token. Hãy yêu cầu reauthentication bằng một flow được hỗ trợ hoặc chuyển sang session/authentication service có khả năng ghi nhận sự kiện.

## 9. Chọn yếu tố cho step-up

Freshness trả lời “xác thực gần đây đến mức nào”; assurance trả lời “xác thực mạnh tới mức nào”. Chọn yếu tố theo threat model và hành động.

| Phương thức | Điểm mạnh | Cân nhắc khi step-up |
| --- | --- | --- |
| Mật khẩu | Dễ triển khai, người dùng quen thuộc | Có thể bị phishing/reuse; nhập lại mật khẩu không tự tạo phishing resistance. |
| TOTP | Yếu tố possession dựa trên secret chia sẻ | Có thể bị phishing real-time; cần kiểm tra mã, replay window và rate limit. |
| Push approval | Trải nghiệm thuận tiện | Push fatigue và approval nhầm; cần transaction context, number matching hoặc ràng buộc tương đương. |
| Passkey/WebAuthn | Chữ ký public-key ràng buộc RP ID/origin, có thể chống phishing | Cần kiểm tra user verification, credential policy và kết quả ceremony; thiết bị mất cần recovery an toàn. |
| Security key | Possession của authenticator phần cứng; thường có khả năng chống phishing | Quản lý mất khóa, dự phòng và chính sách authenticator. |
| Client certificate/mTLS | Ràng buộc workload/client với private key | Thường phù hợp machine identity hơn user step-up; cần phân biệt chủ thể. |

Không phải tất cả hành động đều cần cùng một yếu tố. Với hành động rủi ro cao, ưu tiên phương thức chống phishing và xác minh user verification theo policy. Không hạ xuống SMS hoặc email chỉ vì phương thức mạnh không tiện nếu policy không cho phép.

### 9.1. Step-up không nên tạo MFA fatigue

Không gửi liên tục push prompt cho tới khi người dùng chấp nhận. Hãy giới hạn số lần challenge, có rate limit, hiển thị rõ hành động đang được yêu cầu và cho phép từ chối. Với hành động tài chính hoặc quản trị, ràng buộc challenge với chi tiết transaction để tránh phê duyệt một yêu cầu khác với điều người dùng nhìn thấy.

## 10. Bảo vệ freshness khỏi replay và downgrade

Freshness có thể bị lạm dụng nếu hệ thống chỉ kiểm tra một timestamp mà không ràng buộc nguồn, transaction và assurance.

Các tình huống:
- Attacker replay một ID Token hoặc assertion cũ có chữ ký hợp lệ.
- Client thay `auth_time` trong request tự gửi.
- Backend lấy `iat` mới của access token thay cho thời điểm xác thực.
- OP không đáp ứng `max_age` nhưng client vẫn tiếp tục.
- Một phương thức yếu được chấp nhận thay cho yếu tố mạnh đã yêu cầu.
- Step-up thành công cho transaction A nhưng được tái sử dụng cho transaction B.
- Một session bị chiếm dùng lại kết quả step-up còn hiệu lực.
- Clock skew khiến assertion cũ được xem là mới.

Kiểm soát:
1. Xác minh chữ ký, issuer, audience, nonce, thời hạn và các điều kiện token/assertion.
2. Dùng transaction nonce/state một lần, có expiry và server-side binding.
3. Kiểm tra `auth_time` thay vì `iat` hoặc activity time.
4. Kiểm tra `acr`/`amr` theo mapping đã thỏa thuận; không chấp nhận downgrade âm thầm.
5. Gắn step-up event với session/account/action và giới hạn thời gian sử dụng.
6. Tiêu thụ challenge một lần; phát hiện replay và ghi audit.
7. Giới hạn clock skew và từ chối timestamp bất hợp lý.
8. Nếu issuer không đáp ứng yêu cầu, fail closed cho hành động nhạy cảm hoặc chuyển sang fallback đã được phê duyệt.

## 11. Fallback và trải nghiệm khi authenticator không khả dụng

Người dùng có thể mất security key, đổi điện thoại, không có mạng hoặc không dùng được sinh trắc. Fallback phải được thiết kế trước và có assurance phù hợp.

- Cho phép dùng authenticator dự phòng đã ghi danh và đáp ứng policy.
- Nếu dùng recovery code, kiểm tra một lần, lưu verifier an toàn và thu hồi code sau khi dùng.
- Có thể yêu cầu recovery flow với kiểm tra bổ sung và thời gian chờ cho thay đổi có rủi ro cao.
- Hỗ trợ thủ công phải có quy trình xác minh, phân tách nhiệm vụ và audit.
- Không tự hạ xuống mật khẩu hoặc SMS nếu policy yêu cầu phishing-resistant MFA.
- Không để support agent bỏ qua freshness chỉ vì người dùng thúc giục.
- Thông báo khi có recovery hoặc authenticator mới được thêm; gửi tới kênh đã xác minh trước nếu có.

Nếu không có phương thức đáp ứng policy, có thể từ chối hoặc trì hoãn hành động nhạy cảm. Trải nghiệm tốt cần giải thích cách khôi phục quyền truy cập và thời điểm có thể thử lại, không giả vờ rằng xác thực yếu tương đương xác thực mạnh.

## 12. Pseudocode đánh giá freshness

Ví dụ logic server-side:

~~~text
evaluateStepUp(account, session, action, now):
    policy = policyFor(action)

    event = latestVerifiedAuthenticationEvent(
        accountId=account.id,
        sessionId=session.id
    )

    if event is missing:
        return REQUIRE_STEP_UP

    if event.issuer not in trustedIssuers:
        return DENY_AND_AUDIT

    if event.authenticatedAt > now + allowedClockSkew:
        return DENY_AND_AUDIT

    age = now - event.authenticatedAt

    if age > policy.maxAuthenticationAge:
        return REQUIRE_STEP_UP

    if not policy.accepts(event.assuranceContext, event.methods):
        return REQUIRE_STEP_UP

    if policy.requiresTransactionBinding:
        if event.transactionId != action.pendingTransactionId:
            return REQUIRE_STEP_UP

    if event.sessionId != session.id:
        return REQUIRE_STEP_UP

    return ALLOW
~~~

Đây là pseudocode minh họa. Triển khai thật cần kiểm tra event đã được xác minh, trạng thái session, account lock, revocation, risk signals và authorization nghiệp vụ. Nếu một authentication event được dùng cho nhiều request, policy phải quy định rõ cửa sổ và phạm vi tái sử dụng.

### 12.1. Hoàn tất step-up và cập nhật event

~~~text
completeStepUp(transaction, verifiedResult):
    require transaction.status == pending
    require transaction.expiresAt > serverNow
    require verifiedResult.accountId == transaction.accountId
    require verifiedResult.sessionId == transaction.sessionId
    require verifiedResult.actionHash == transaction.actionHash
    require verifiedResult.authenticator satisfies transaction.policy

    atomically:
        mark transaction completed
        consume transaction.challenge
        append verified AuthenticationEvent
        mark transaction result as single-use or scoped

    return success
~~~

Không cập nhật event chỉ vì client gọi endpoint “step-up complete”. Kết quả phải được xác minh từ authenticator/issuer và được liên kết với transaction trước khi ghi nhận.

## 13. Bài thực hành: Authentication freshness cho StudyHub

**Bối cảnh:** StudyHub có web app, mobile app và Course API. Người dùng đăng nhập bằng passkey hoặc mật khẩu + TOTP. Họ có thể đọc tài liệu, xem hồ sơ, đổi email recovery, thêm passkey và sửa điểm nếu là giảng viên. Access token có tuổi thọ ngắn và refresh token được rotation.

### 13.1. Thiết kế policy

Hãy lập policy cho từng hành động:
1. Xác định auth age tối đa.
2. Xác định assurance/ACR cần thiết.
3. Liệt kê phương thức được chấp nhận và phương thức không đủ.
4. Xác định có cần transaction binding hay không.
5. Chọn cách yêu cầu step-up qua OIDC hoặc WebAuthn trực tiếp.
6. Xác định fallback nếu mất passkey hoặc TOTP.
7. Quy định audit, notification và thời gian hết hạn challenge.

Phân tích các tình huống:
- Người dùng đăng nhập bằng passkey lúc 08:00, refresh access token lúc 11:00 và yêu cầu đổi email lúc 11:02.
- Người dùng đăng nhập bằng mật khẩu + TOTP lúc 10:00, nhưng action yêu cầu passkey chống phishing.
- ID Token mới có `iat` hiện tại nhưng `auth_time` từ ngày hôm trước.
- OP trả `acr` thấp hơn context được yêu cầu.
- Hai tab cùng gửi step-up cho hai giao dịch khác nhau.
- Response step-up bị replay sau khi transaction đã hoàn tất.
- Đồng hồ backend nhanh hơn OP vài phút.
- Người dùng mất thiết bị và chỉ còn recovery code.

### 13.2. Bộ ca kiểm thử chấp nhận

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| Authentication event trong freshness window và đủ assurance | Cho phép tiếp tục nếu authorization và transaction checks cũng đạt. |
| Event quá cũ | Yêu cầu step-up; session vẫn có thể còn active. |
| Access token vừa refresh nhưng auth_time cũ | Không coi token mới là xác thực mới. |
| last_seen_at vừa cập nhật do background request | Không làm mới authentication freshness. |
| ID Token thiếu auth_time khi policy yêu cầu | Không suy ra từ iat; yêu cầu xác thực lại hoặc từ chối theo policy. |
| auth_time nằm trong tương lai vượt clock skew | Từ chối và audit. |
| Issuer không nằm trong trust configuration | Từ chối. |
| ID Token sai issuer/audience/nonce/chữ ký | Từ chối. |
| max_age được yêu cầu nhưng auth_time vượt ngưỡng | Step-up tiếp hoặc từ chối; không bỏ qua. |
| acr thấp hơn assurance yêu cầu | Không cho phép action; yêu cầu phương thức phù hợp. |
| amr không nằm trong mapping đã thỏa thuận | Không tự suy đoán; xử lý theo policy. |
| Step-up event gắn với session khác | Từ chối. |
| Step-up event gắn với transaction khác | Từ chối. |
| Challenge hết hạn hoặc đã dùng | Từ chối replay. |
| Hai tab đồng thời step-up | Mỗi transaction có binding riêng; không dùng nhầm kết quả. |
| User từ chối push hoặc không phản hồi | Không coi im lặng là chấp thuận; rate limit và giữ trạng thái pending/failed. |
| Passkey không khả dụng | Chỉ dùng fallback được policy cho phép; không downgrade âm thầm. |
| Clock skew trong tolerance | Xử lý theo quy tắc đã công bố, ghi nhận sai lệch nếu cần. |
| Session bị revoke sau step-up | Action bị chặn khi backend kiểm tra trạng thái. |
| Tài khoản bị khóa sau authentication event | Không cho phép action chỉ dựa vào event cũ. |
| Token/claim bị log | Kiểm thử thất bại; pipeline phải redaction. |

### 13.3. Câu hỏi tự đánh giá

1. Authentication freshness khác session age như thế nào?
2. Vì sao token_iat mới không chứng minh người dùng vừa xác thực?
3. OIDC auth_time và max_age giúp gì cho step-up?
4. prompt=login có bảo đảm MFA hoặc phishing resistance không?
5. acr và amr cần được hiểu theo cách nào trước khi map vào policy?
6. Vì sao freshness và assurance phải được đánh giá riêng?
7. Làm sao ngăn step-up cho một transaction bị tái sử dụng cho transaction khác?
8. Clock skew ảnh hưởng ra sao tới freshness check?
9. Khi authenticator mạnh không khả dụng, fallback cần đáp ứng điều kiện gì?
10. Vì sao background activity không nên tự làm mới authentication freshness?

**Tiêu chí hoàn thành:** Người học có thể thiết kế freshness policy theo hành động, xác minh auth_time và assurance context từ issuer tin cậy, ràng buộc step-up với session/transaction, xử lý clock skew/replay/downgrade và chứng minh bằng test rằng token refresh hoặc activity không giả lập được một lần xác thực mới.

## 14. Vận hành và giám sát

Các chỉ số nên theo dõi:
- Tỷ lệ action yêu cầu step-up theo loại hành động và risk band.
- Tỷ lệ step-up thành công, thất bại, timeout và người dùng hủy.
- Phân bố authentication age tại thời điểm action.
- Tỷ lệ issuer không trả auth_time hoặc trả assurance không đáp ứng.
- Tỷ lệ fallback và recovery.
- Tỷ lệ replay, nonce/state mismatch và transaction binding failure.
- Clock skew giữa issuer và relying party.
- Tỷ lệ step-up bị từ chối do session/account đã revoke hoặc lock.
- Chênh lệch trải nghiệm theo nền tảng và loại authenticator.

Audit cần lưu account/session reference, issuer, auth_time đã xác minh, assurance context, action, transaction ID, policy version, kết quả và lý do. Không ghi password, OTP, private key, cookie, refresh token hoặc toàn bộ token response. Giới hạn quyền truy cập log và thiết lập retention phù hợp.

Khi thay đổi freshness window, ACR mapping hoặc fallback, cần review tác động bảo mật và khả năng tiếp cận. Theo dõi cả false acceptance lẫn step-up quá mức. Nếu tỷ lệ step-up tăng đột ngột, điều tra issuer clock, token refresh behavior, session policy và thay đổi ứng dụng trước khi nới ngưỡng.

## 15. Tài liệu nên đọc tiếp

- **OpenID Connect Core 1.0**: ID Token, auth_time, max_age, prompt và authentication context.
- **RFC 9470 — OAuth 2.0 Step-Up Authentication Challenge Protocol**: cách resource server yêu cầu client thực hiện step-up trong một số kiến trúc OAuth.
- **NIST SP 800-63B — Authentication and Authenticator Management**: reauthentication, session management và authenticator assurance; dùng phiên bản hiện hành phù hợp.
- **W3C WebAuthn**: xác minh assertion khi dùng passkey/security key cho step-up.
- **SAML 2.0 Core / Profiles**: AuthnInstant và AuthnContext trong assertion.
- **OWASP Authentication Cheat Sheet**: reauthentication cho hành động nhạy cảm, session và credential lifecycle.
- **OWASP ASVS**: tiêu chí kiểm thử session, authentication và authorization.

Khi triển khai thật, hãy xác định issuer nào có thể cung cấp bằng chứng xác thực, semantics của claim, freshness window cho từng hành động và phương thức step-up được chấp nhận. **Một session còn hiệu lực chỉ chứng minh phiên chưa bị hệ thống chấm dứt; authentication freshness chỉ được làm mới khi một sự kiện xác thực mới đã được xác minh và đáp ứng đúng assurance cùng transaction policy.**

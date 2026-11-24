# Ứng dụng truy cập — Sử dụng ngữ cảnh xác thực để kiểm soát truy cập

## 1. Ứng dụng truy cập là gì trong authentication context?

Trong bài học **Authentication context**, “ứng dụng truy cập” là ứng dụng hoặc API nhận một yêu cầu từ người dùng đã xác thực và phải quyết định có cho phép yêu cầu đó tiếp tục hay không. Ứng dụng không chỉ cần biết người dùng là ai; nó còn cần hiểu **người dùng đã được xác thực trong hoàn cảnh nào**, bằng phương thức nào, vào thời điểm nào và với mức bảo đảm nào.

Ví dụ: nhân viên đăng nhập cổng nội bộ bằng mật khẩu và TOTP vào buổi sáng. Buổi chiều, người đó mở ứng dụng nhân sự để xem thông tin cá nhân. Phiên đăng nhập hiện tại có thể đủ cho thao tác đọc. Nhưng khi người đó yêu cầu thay đổi tài khoản nhận lương, ứng dụng cần xác thực mới hơn hoặc yếu tố mạnh hơn như passkey. Ứng dụng dùng authentication context đã được IdP xác minh, kết hợp chính sách và quyền nghiệp vụ để quyết định yêu cầu có được phép thực hiện không.

Trong module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, authentication context kết nối credential, mật khẩu, MFA, passkey, chứng chỉ, token, session, liên kết danh tính và khôi phục tài khoản. Mục tiêu là giúp người học mô hình hóa ranh giới tin cậy, hiểu thông tin xác thực được truyền tới ứng dụng và thiết kế quyết định truy cập có khả năng chống phishing, replay, lạm dụng đăng nhập và nâng quyền trái phép.

**Authentication context không đồng nghĩa với quyền truy cập.** Context mô tả bằng chứng và hoàn cảnh xác thực đã được kiểm chứng; authorization policy quyết định principal có thể thực hiện hành động nào trên tài nguyên nào. Một người có thể đã xác thực mạnh nhưng vẫn không có quyền đọc hồ sơ của người khác.

## 2. Authentication, authentication context và authorization

Ba khái niệm cần được tách biệt:

| Khái niệm | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Authentication** | Chủ thể là ai và đã chứng minh điều đó bằng cách nào? | Người dùng xác minh bằng passkey hoặc mật khẩu + TOTP. |
| **Authentication context** | Sự kiện xác thực diễn ra trong hoàn cảnh và mức bảo đảm nào? | Xác thực bằng passkey, lúc 09:15, tại IdP cụ thể, theo assurance class đã thỏa thuận. |
| **Authorization** | Chủ thể được phép làm gì trên tài nguyên nào trong ngữ cảnh hiện tại? | Nhân viên được xem hồ sơ của chính mình; chỉ HR được sửa thông tin hợp đồng. |

Ứng dụng cần xác minh authentication context trước khi sử dụng nó. Một chuỗi do client gửi như “mfa=true” hoặc “device_trusted=true” không phải bằng chứng. Context có giá trị khi đến từ issuer/nguồn đã tin cậy, được bảo vệ toàn vẹn, gắn đúng principal, client, audience và giao dịch.

### Authentication context có thể gồm những gì?

- **Principal:** subject/user/service identity đã được xác minh.
- **Issuer:** IdP hoặc authorization server đã phát hành bằng chứng.
- **Authentication time:** thời điểm người dùng thực sự xác thực gần nhất, nếu giao thức cung cấp.
- **Authentication methods:** phương thức đã dùng, ví dụ password, OTP, passkey, client certificate.
- **Assurance context:** mức hoặc lớp xác thực đã đạt theo thỏa thuận giữa IdP và ứng dụng.
- **Session context:** thời điểm tạo phiên, thời hạn, trạng thái và mức assurance được gắn với phiên.
- **Client/resource context:** ứng dụng nhận kết quả, audience, scope và tenant.
- **Risk signals:** tín hiệu rủi ro như thiết bị mới, vị trí bất thường hoặc hành vi đăng nhập; chỉ dùng khi có nguồn và cách đánh giá đáng tin.

Không phải giao thức hoặc IdP nào cũng cung cấp tất cả các trường này. Ứng dụng phải xác định rõ dữ liệu nào được yêu cầu, nguồn nào cung cấp và cách diễn giải đã được thống nhất.

## 3. Ranh giới tin cậy khi ứng dụng nhận authentication context

Một ứng dụng thường nhận context thông qua OIDC, SAML, access token hoặc một phiên cục bộ được tạo sau khi xác minh federation response:

~~~mermaid
flowchart LR
    U["Người dùng"]
    I["IdP / Authorization server<br/>xác minh credential"]
    B["Browser / native client"]
    A["Ứng dụng / relying party<br/>xác minh context"]
    P["Policy engine<br/>authentication + authorization"]
    R["Tài nguyên / API"]
    U --> B
    B <--> I
    B -->|"OIDC / SAML response"| A
    I -->|"Token/assertion đã ký"| A
    A -->|"Principal + context đã kiểm chứng"| P
    P -->|"Allow / deny / step-up"| A
    A -->|"Request được phép"| R
~~~

IdP chịu trách nhiệm xác minh credential và phát hành thông tin xác thực. Ứng dụng chịu trách nhiệm kiểm tra chữ ký hoặc giao thức, issuer, audience, thời hạn, giao dịch và các claim cần thiết. Policy engine hoặc lớp authorization của ứng dụng dùng context đã xác minh cùng dữ liệu nghiệp vụ để ra quyết định.

Browser và client không phải nguồn có thẩm quyền cho authentication context. Các header như X-User, X-Auth-Level, X-MFA hoặc X-Device-Trusted có thể bị giả mạo nếu backend nhận trực tiếp từ client. Chỉ tin header do một proxy/gateway đã xác minh tạo ra khi backend xác thực proxy, kênh nội bộ được bảo vệ và proxy loại bỏ mọi header trùng tên do client gửi.

## 4. Ứng dụng nhận context qua OIDC

Trong OpenID Connect, RP thường nhận ID token từ authorization server sau Authorization Code Flow. ID token là bằng chứng xác thực dành cho client/RP; access token dành cho resource server theo audience và scope của nó.

Các claim thường liên quan đến authentication context:

| Claim | Ý nghĩa | Cách ứng dụng sử dụng |
| --- | --- | --- |
| iss | Issuer phát hành ID token. | So khớp chính xác với IdP đã cấu hình. |
| sub | Subject duy nhất trong phạm vi issuer. | Là định danh người dùng theo cặp issuer + subject; không mặc định là email. |
| aud | Audience của token. | Kiểm tra client ID của ứng dụng có nằm trong audience hợp lệ. |
| exp / iat | Thời điểm hết hạn / phát hành token. | Kiểm tra token còn hiệu lực và thời gian phát hành hợp lý. |
| auth_time | Thời điểm người dùng được xác thực. | Đánh giá authentication age; không thay bằng thời điểm token được phát hành. |
| acr | Authentication Context Class Reference. | Ánh xạ lớp/mức xác thực theo contract với IdP. |
| amr | Authentication Methods References. | Hiểu phương thức đã dùng theo giá trị và semantics được thống nhất. |
| nonce | Giá trị ràng buộc ID token với yêu cầu OIDC. | So khớp với nonce của giao dịch để chống replay/injection. |

Ứng dụng phải xác minh chữ ký ID token bằng khóa tin cậy của issuer, kiểm tra issuer, audience, thời hạn và nonce theo OIDC. Không đọc claim từ JWT chưa xác minh rồi dùng nó để cấp quyền. Cũng không được lấy issuer hoặc URL tải khóa từ nội dung token chưa tin cậy.

### ACR và AMR không phải một quy ước tự diễn giải

ACR có thể đại diện một lớp assurance mà IdP và RP đã thống nhất. AMR mô tả phương thức xác thực được sử dụng. Một giá trị AMR như otp hoặc pwd không tự cho biết mức assurance cụ thể trong mọi hệ thống. Ứng dụng phải có mapping rõ ràng, được kiểm thử và cập nhật khi IdP thay đổi policy.

Nếu IdP không cung cấp ACR/AMR hoặc claim không đáp ứng contract, ứng dụng không nên tự suy đoán rằng người dùng đã đạt MFA. Có thể yêu cầu step-up, từ chối thao tác nhạy cảm hoặc dùng một policy thay thế đã được phê duyệt.

## 5. Ứng dụng nhận context qua SAML

Với SAML, ứng dụng (Service Provider) nhận assertion từ IdP. Authentication statement có thể mang Authentication Context, chẳng hạn AuthnContextClassRef và AuthnInstant.

Ứng dụng cần xác minh:

- Chữ ký assertion/response theo profile và trust configuration.
- Issuer, destination, recipient và audience restriction.
- Thời hạn NotBefore/NotOnOrAfter.
- InResponseTo nếu response thuộc request do SP khởi tạo.
- Assertion ID và replay cache để không chấp nhận lại assertion.
- Subject/NameID và mapping sang tài khoản nội bộ.
- AuthnInstant và AuthnContextClassRef theo contract với IdP.

AuthnContextClassRef không có ý nghĩa thống nhất tuyệt đối nếu hai bên không thống nhất profile và semantics. Không nên thấy một URI hoặc chuỗi có chữ “MFA” rồi mặc nhiên coi nó đạt policy. Cần cấu hình danh sách class được chấp nhận và mapping cụ thể.

### OIDC và SAML có cách biểu diễn khác nhau

| Nội dung | OIDC | SAML |
| --- | --- | --- |
| Thông tin xác thực | ID token | SAML assertion |
| Thời điểm xác thực | auth_time | AuthnInstant |
| Ngữ cảnh/lớp xác thực | acr | AuthnContextClassRef |
| Phương thức xác thực | amr nếu được cung cấp | AuthnContext và các thông tin liên quan theo profile |
| Ràng buộc giao dịch | state, nonce, PKCE và kiểm tra token | InResponseTo, request/response binding, assertion ID và replay checks |

Ứng dụng có thể chuẩn hóa dữ liệu từ OIDC/SAML vào một mô hình nội bộ, nhưng phải giữ lại nguồn gốc, issuer và semantics để không làm mất ý nghĩa bảo đảm.

## 6. Từ authentication context đến quyết định truy cập

Một quyết định truy cập an toàn thường kết hợp ít nhất bốn yếu tố:

1. **Identity:** principal nào đã được xác minh?
2. **Authentication context:** bằng chứng có đủ mới và đủ mạnh không?
3. **Authorization:** principal có quyền trên resource/action không?
4. **Runtime context:** yêu cầu có phù hợp tenant, trạng thái tài khoản, thiết bị và policy hiện hành không?

~~~mermaid
flowchart TD
    A["Request tới ứng dụng"] --> B["Xác minh session/token/federation"]
    B --> C{"Authentication context hợp lệ?"}
    C -->|"Không"| X["401 / yêu cầu đăng nhập"]
    C -->|"Có"| D["Đánh giá auth_time, acr, amr, session"]
    D --> E{"Context đủ cho hành động?"}
    E -->|"Chưa"| F["Yêu cầu step-up / re-auth"]
    E -->|"Đủ"| G["Kiểm tra principal, tenant, role, resource"]
    F --> H{"Step-up hoàn tất?"}
    H -->|"Không"| Y["Từ chối"]
    H -->|"Có"| G
    G --> I{"Authorization policy cho phép?"}
    I -->|"Không"| Y
    I -->|"Có"| J["Thực thi và audit"]
~~~

Kết quả có thể là:

- **Allow:** context và quyền đều đạt.
- **Deny:** bằng chứng không hợp lệ, tài khoản không hoạt động hoặc quyền không đủ.
- **Step-up required:** người dùng cần xác thực thêm hoặc xác thực lại.
- **Challenge/consent required:** cần một tương tác khác theo policy, ví dụ chọn tenant hoặc chấp thuận quyền.

Không gộp tất cả thất bại thành “MFA chưa bật”. Lỗi chữ ký token, issuer sai, audience sai, session bị thu hồi và quyền nghiệp vụ thiếu là các tình huống khác nhau, cần được xử lý và ghi audit phù hợp.

## 7. Freshness: xác thực gần đây có còn đủ không?

Một lần xác thực mạnh từ nhiều giờ hoặc nhiều ngày trước không nhất thiết đủ cho mọi thao tác hiện tại. Ứng dụng cần đánh giá **authentication age** dựa trên thời điểm xác thực thực tế, thường là auth_time hoặc AuthnInstant, chứ không dùng iat của token hoặc thời điểm refresh token.

Ví dụ policy:

| Hành động | Yêu cầu context minh họa |
| --- | --- |
| Xem nội dung công khai | Session hợp lệ, principal active. |
| Xem hồ sơ cá nhân | Session hợp lệ và quyền sở hữu tài nguyên. |
| Tải dữ liệu nội bộ | Xác thực gần đây hơn và scope/role phù hợp. |
| Thêm passkey hoặc MFA | Step-up bằng yếu tố hiện có và transaction binding. |
| Thay đổi tài khoản nhận lương | Xác thực gần đây bằng phương thức mạnh, có thể yêu cầu passkey/MFA. |
| Quản trị quyền tenant | Assurance cao, session mới, role quản trị và có thể cần phê duyệt bổ sung. |

Đây chỉ là ví dụ. Ngưỡng thời gian và phương thức phải dựa trên rủi ro, quy định và khả năng của IdP. Không nên đặt một thời hạn chung cho mọi hành động.

### OIDC max_age và prompt

RP có thể yêu cầu xác thực gần đây thông qua max_age trong authorization request. IdP trả auth_time trong ID token để RP kiểm tra thời điểm xác thực. prompt=login có thể yêu cầu IdP hiển thị tương tác đăng nhập theo semantics của OIDC, nhưng không tự thay thế đánh giá risk hoặc policy.

Ứng dụng phải xác minh response và kiểm tra auth_time so với ngưỡng riêng. Nếu thiếu auth_time khi policy yêu cầu, không được coi token issuance time là bằng chứng thay thế.

## 8. Step-up authentication từ ứng dụng

Khi context hiện tại chưa đủ, ứng dụng có thể khởi tạo step-up:

1. Ứng dụng xác định hành động cần mức assurance cao hơn.
2. Tạo một giao dịch step-up gắn với principal, session, resource/action và thời hạn.
3. Chuyển người dùng tới IdP với yêu cầu xác thực phù hợp, chẳng hạn max_age hoặc acr_values theo contract.
4. IdP đánh giá IdP session hiện tại; nếu chưa đủ, yêu cầu passkey, MFA hoặc xác thực lại.
5. IdP trả response gắn với giao dịch; ứng dụng xác minh state, nonce, issuer, audience, chữ ký và context.
6. Ứng dụng kiểm tra lại quyền và trạng thái tài nguyên trước khi thực hiện hành động.

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant A as Ứng dụng
    participant I as IdP
    U->>A: Yêu cầu thao tác nhạy cảm
    A->>A: Policy yêu cầu assurance cao hơn
    A->>A: Tạo step-up transaction
    A-->>U: Redirect tới IdP với yêu cầu phù hợp
    U->>I: Xác thực lại / passkey / MFA
    I->>I: Xác minh và ghi authentication event
    I-->>A: OIDC/SAML response
    A->>A: Verify response và context
    A->>A: Kiểm tra lại authorization
    A-->>U: Cho phép hoặc từ chối thao tác
~~~

Không nên coi việc quay lại từ IdP là đủ để cho phép thao tác. Callback có thể thuộc giao dịch khác, context có thể không đạt hoặc quyền có thể đã thay đổi. Giao dịch step-up phải có state/nonce riêng, dùng một lần và ràng buộc với hành động đang chờ.

## 9. Authentication context trong session cục bộ

Sau khi xác minh OIDC/SAML, ứng dụng thường tạo session riêng. Session record có thể giữ một bản sao có kiểm soát của context:

~~~text
ApplicationSession
  session_id_verifier: <opaque ID verifier>
  principal_id:        user-1024
  issuer:              https://id.example.org
  subject:             00u-a82f
  tenant_id:           org-27
  authenticated_at:    <auth_time đã xác minh>
  authentication_methods: [passkey]
  assurance_class:     <giá trị đã mapping>
  created_at:          <local session creation time>
  idle_expires_at:     <timestamp>
  absolute_expires_at: <timestamp>
  status:              active | revoked | expired
~~~

Không lưu toàn bộ token/assertion nếu không cần. Chỉ lưu các thuộc tính phục vụ policy, có nguồn gốc và thời hạn rõ. Nếu cần lưu token, phải bảo vệ bằng secret storage phù hợp và không ghi token thô vào log.

### Hai loại thời gian khác nhau

- **authenticated_at:** thời điểm IdP xác thực người dùng.
- **session_created_at:** thời điểm ứng dụng tạo session cục bộ.

Hai thời điểm có thể khác nhau. Nếu RP tạo session mới sau khi refresh hoặc sau một lần callback SSO im lặng, không được tự cập nhật authenticated_at thành thời điểm hiện tại nếu người dùng không thực sự xác thực lại.

### Session rotation và assurance

Sau step-up thành công, ứng dụng có thể xoay session ID để gắn trạng thái mới và chống session fixation. Cập nhật assurance phải dựa trên response đã xác minh; không nhận một cờ do client gửi. Nếu step-up thất bại hoặc bị hủy, session cũ giữ nguyên mức assurance trước đó.

## 10. Context từ thiết bị và tín hiệu rủi ro

Ứng dụng có thể xem xét thiết bị, mạng, vị trí, hành vi và trạng thái endpoint để đánh giá rủi ro. Tuy nhiên, các tín hiệu này không tự động là authentication factor.

| Tín hiệu | Có thể giúp gì? | Giới hạn |
| --- | --- | --- |
| Thiết bị đã đăng ký | Nhận biết thiết bị từng được liên kết. | Cookie/device ID có thể bị sao chép; cần bằng chứng thiết bị đáng tin. |
| Khóa phần cứng/device-bound key | Chứng minh quyền kiểm soát khóa trên thiết bị. | Runtime hoặc thiết bị bị chiếm vẫn có rủi ro. |
| IP/ASN/địa lý | Phát hiện thay đổi bất thường. | VPN, roaming, NAT và mạng di động gây sai lệch. |
| User agent/browser | Hỗ trợ phát hiện thay đổi client. | Dễ giả mạo và không phải định danh thiết bị chắc chắn. |
| Thời gian/hành vi | Phát hiện pattern bất thường. | Có false positive; cần hiệu chỉnh và bảo vệ quyền riêng tư. |
| Endpoint posture | Đánh giá thiết bị có đạt policy quản lý hay không. | Chỉ đáng tin khi nguồn posture và kênh truyền được xác minh. |

Không dùng IP hoặc user agent làm yếu tố duy nhất để cho phép hoặc từ chối truy cập. Nếu nhận device posture qua gateway, phải xác minh gateway và tính toàn vẹn của metadata. Ứng dụng cần cân bằng giữa an toàn, khả năng truy cập, quyền riêng tư và nguy cơ khóa nhầm người dùng hợp lệ.

## 11. Multi-tenant và liên kết danh tính

Trong ứng dụng nhiều tenant, cùng một subject có thể được liên kết với tổ chức hoặc vai trò khác nhau. Ứng dụng cần ràng buộc authentication context với đúng issuer, subject, tenant và client.

Các nguyên tắc:

- Dùng cặp issuer + subject làm định danh federation ổn định theo contract; email có thể thay đổi hoặc trùng.
- Xác minh tenant membership từ nguồn provisioning/authorization đáng tin cậy.
- Không lấy tenant ID do browser gửi làm bằng chứng quyền truy cập.
- Kiểm tra audience/client và resource để tránh token của ứng dụng khác được chấp nhận.
- Tách role/scope theo tenant; không kế thừa quyền giữa tenant chỉ vì cùng người dùng.
- Khi liên kết hoặc unlink tài khoản, yêu cầu xác thực phù hợp và audit rõ ràng.

Ví dụ: một chuyên gia tư vấn có tài khoản ở hai tổ chức. IdP có thể xác thực cùng một người, nhưng RP phải xác định người đó đang làm việc trong tenant nào và quyền nào được cấp ở tenant đó. Authentication thành công không tự cấp quyền đọc dữ liệu của cả hai tổ chức.

## 12. Rủi ro khi ứng dụng diễn giải context sai

| Rủi ro | Ví dụ lỗi | Kiểm soát |
| --- | --- | --- |
| **Claim spoofing** | Client gửi header mfa=true. | Chỉ dùng claim từ token/assertion đã xác minh hoặc metadata từ proxy tin cậy. |
| **Issuer confusion** | Chấp nhận token từ IdP khác. | Allowlist issuer và ràng buộc issuer với client/giao dịch. |
| **Audience confusion** | Token của API khác được dùng cho ứng dụng. | Kiểm tra audience/resource chính xác. |
| **Authentication age confusion** | Dùng iat thay auth_time. | Kiểm tra thời điểm xác thực thực tế theo semantics giao thức. |
| **ACR/AMR overclaim** | Suy ra MFA mạnh từ chuỗi AMR không được thống nhất. | Mapping có contract, kiểm thử và fail closed khi thiếu bằng chứng. |
| **Tenant confusion** | Principal của tenant A truy cập tenant B. | Ràng buộc issuer/subject/tenant và authorization ở server. |
| **Session fixation** | Giữ session ID cũ sau đăng nhập/step-up. | Regenerate ID và thu hồi ID cũ. |
| **Step-up response injection** | Dùng response từ giao dịch khác để nâng assurance. | Transaction ID, state, nonce, one-time use và action binding. |
| **Stale context** | Quyền hoặc credential đã thu hồi nhưng session vẫn giữ context cũ. | TTL, revalidation, session revocation và policy versioning. |
| **Risk signal overtrust** | Cho phép chỉ vì IP quen thuộc. | Kết hợp nhiều tín hiệu; không coi IP/UA là bằng chứng danh tính. |
| **Authorization bypass** | Người dùng có MFA nhưng thiếu quyền nghiệp vụ vẫn được truy cập. | Tách authentication decision khỏi authorization policy. |

Một token có chữ ký hợp lệ chỉ cho biết token được phát hành bởi issuer tương ứng và chưa bị sửa đổi. Ứng dụng vẫn phải kiểm tra nó có dành cho ứng dụng/resource hiện tại, còn hiệu lực và đáp ứng policy hay không.

## 13. Mã giả: đánh giá context trước khi cho phép hành động

Đây là mã giả minh họa logic policy; không thay thế thư viện OIDC/SAML hoặc hệ thống authorization đã được kiểm thử:

~~~text
authorizeSensitiveAction(request, localSession):
    session = requireActiveSession(localSession)
    require accountIsActive(session.principalId)

    context = session.verifiedAuthenticationContext
    require context exists
    require context.issuer in configuredTrustedIssuers
    require context.subject == session.federatedSubject
    require context.tenant == request.tenant

    policy = loadPolicy(request.resource, request.action)
    require policy.version is current

    if context.authenticationTime is missing:
        return requireStepUpOrDeny()

    if now - context.authenticationTime > policy.maxAuthenticationAge:
        return requireStepUp()

    if not policy.acceptedAssuranceClasses.contains(context.assuranceClass):
        return requireStepUpOrDeny()

    if not policy.requiredMethodsSatisfied(context.authenticationMethods):
        return requireStepUpOrDeny()

    if not authorizationAllows(
        principal = session.principalId,
        tenant = request.tenant,
        resource = request.resource,
        action = request.action
    ):
        return forbidden()

    return allowAndAudit(policy.version, safeContextMetadata(context))
~~~

Trong triển khai thật:

- Context phải được lấy từ token/assertion/session đã xác minh, không từ request body/header tùy ý.
- Kiểm tra auth_time bằng clock đáng tin; xử lý clock skew theo policy.
- ACR/AMR mapping phải được cấu hình từ contract của IdP, không suy luận tự do.
- Nếu step-up, tạo giao dịch mới gắn với principal, session, action và resource; chỉ cập nhật context sau khi response mới được xác minh.
- Kiểm tra authorization ngay trước khi thực hiện thao tác nhạy cảm, tránh TOCTOU khi quyền hoặc tài nguyên thay đổi.
- Audit chỉ lưu metadata cần thiết; không lưu token, cookie hoặc assertion thô.

## 14. Tình huống thực tế: thay đổi thông tin nhận lương

Một nhân viên đã đăng nhập ứng dụng HR qua OIDC. Session cục bộ có context từ IdP: xác thực bằng mật khẩu và TOTP lúc 08:30. Vào lúc 14:00, nhân viên muốn thay đổi tài khoản nhận lương.

Ứng dụng có policy yêu cầu xác thực trong vòng 5 phút bằng phương thức chống phishing, cùng quyền HR self-service phù hợp. Context hiện tại không đáp ứng vì đã cũ và phương thức không đạt assurance policy.

### Quyết định

| Kiểm tra | Context hiện tại | Kết quả |
| --- | --- | --- |
| Principal/tenant | Đúng nhân viên và tổ chức | Đạt |
| Session | Active | Đạt |
| Authentication age | 5 giờ 30 phút | Không đạt |
| Assurance/method | Password + TOTP | Không đạt policy của hành động |
| Authorization | Nhân viên được sửa thông tin của chính mình | Đạt |
| Quyết định | Cần step-up | Chưa cho phép cập nhật |

Ứng dụng chuyển người dùng tới IdP yêu cầu xác thực lại bằng passkey. Sau khi nhận callback, ứng dụng xác minh state, nonce, issuer, audience, chữ ký, auth_time và ACR theo contract. Ứng dụng cập nhật context của session sau khi xoay session ID, rồi kiểm tra lại quyền sở hữu hồ sơ và trạng thái yêu cầu trước khi commit thay đổi.

Nếu passkey bị hủy hoặc IdP trả context không đủ, ứng dụng không cập nhật tài khoản nhận lương. Người dùng có thể thử lại hoặc đi theo recovery flow đã được phê duyệt; không tự động fallback về mật khẩu đơn lẻ.

## 15. Kiểm thử ứng dụng sử dụng authentication context

| Tình huống | Kết quả mong đợi |
| --- | --- |
| ID token có chữ ký hợp lệ, issuer/audience đúng | Có thể tiếp tục kiểm tra context và authorization. |
| Issuer không nằm trong trust configuration | Từ chối. |
| Audience không chứa client/resource mong đợi | Từ chối. |
| Token hết hạn hoặc nonce sai | Từ chối callback; không tạo session. |
| auth_time cũ hơn policy max age | Yêu cầu step-up hoặc từ chối hành động. |
| auth_time thiếu khi policy yêu cầu | Không suy ra từ iat; step-up hoặc từ chối. |
| ACR không nằm trong mapping được chấp nhận | Không coi là assurance đủ. |
| AMR chứa giá trị không được contract định nghĩa | Không tự suy ra MFA; xử lý theo policy. |
| Client gửi header mfa=true | Bỏ qua hoặc từ chối; chỉ tin context đã xác minh. |
| Tenant ID không khớp principal membership | Từ chối. |
| Step-up response thuộc giao dịch khác | Từ chối; không nâng assurance. |
| Session bị revoke sau khi context được tạo | Từ chối request tiếp theo theo trạng thái authoritative. |
| Quyền bị thu hồi trong lúc chờ step-up | Kiểm tra lại authorization trước commit; từ chối nếu không còn quyền. |
| IP/UA thay đổi nhưng credential/context hợp lệ | Đánh giá theo risk policy; không tự động coi là danh tính khác. |
| IdP hoặc session store không sẵn sàng | Xử lý theo availability/risk policy; không mặc định tin context chưa kiểm tra. |

### Kiểm thử vận hành và quyền riêng tư

- Log sự kiện xác minh và quyết định allow/deny/step-up với mã policy version.
- Không log access token, ID token, refresh token, assertion, cookie hoặc secret.
- Hạn chế lưu IP, vị trí, fingerprint và device metadata; có retention và quyền truy cập rõ.
- Kiểm thử thay đổi mapping ACR/AMR khi IdP cập nhật policy.
- Kiểm thử rotation signing key/JWKS và thời gian cache.
- Đo tỷ lệ step-up, từ chối, false positive và lỗi tích hợp.

## 16. Checklist thiết kế ứng dụng truy cập theo authentication context

- [ ] Phân biệt authentication, authentication context và authorization.
- [ ] Chỉ nhận context từ IdP/issuer đã tin cậy và response đã xác minh.
- [ ] Kiểm tra issuer, audience, chữ ký, thời hạn, nonce/state và ràng buộc giao dịch.
- [ ] Dùng subject ổn định theo issuer; không dùng email làm định danh duy nhất nếu chưa có contract.
- [ ] Xác định semantics và mapping cho ACR/AMR hoặc AuthnContextClassRef.
- [ ] Dùng auth_time/AuthnInstant để đánh giá freshness; không thay bằng token iat.
- [ ] Có policy riêng theo resource/action, assurance và authentication age.
- [ ] Step-up transaction gắn với principal, session, action, resource và expiry.
- [ ] Sau step-up, xác minh response rồi mới cập nhật context/session; xoay session ID khi phù hợp.
- [ ] Kiểm tra tenant membership và authorization độc lập với authentication.
- [ ] Không tin header/context do client tự gửi; bảo vệ proxy-to-backend nếu dùng header đã xác minh.
- [ ] Đánh giá device/risk signals như tín hiệu bổ sung, không coi IP/UA là yếu tố xác thực.
- [ ] Có TTL, revalidation và revocation khi credential/session/account thay đổi.
- [ ] Kiểm tra lại quyền ngay trước thao tác nhạy cảm.
- [ ] Audit quyết định mà không lưu token, cookie hoặc credential thô.
- [ ] Kiểm thử issuer/audience confusion, replay, stale context, tenant confusion và step-up injection.

## 17. Câu hỏi tự kiểm tra

**Câu 1.** Authentication context khác authorization như thế nào?

**Gợi ý:** Context mô tả bằng chứng và hoàn cảnh xác thực đã được kiểm chứng; authorization quyết định principal được làm gì trên tài nguyên cụ thể.

**Câu 2.** Vì sao ứng dụng không nên tin header mfa=true do browser gửi?

**Gợi ý:** Client có thể tự sửa header. Chỉ dùng context từ token/assertion đã xác minh hoặc metadata từ proxy tin cậy trên kênh bảo vệ.

**Câu 3.** Vì sao auth_time khác iat?

**Gợi ý:** auth_time là thời điểm người dùng được xác thực; iat là thời điểm token được phát hành. Token mới có thể được cấp từ session cũ.

**Câu 4.** ACR và AMR có thể được diễn giải tùy ý không?

**Gợi ý:** Không. Cần contract và mapping với IdP; cùng một giá trị có thể không mang cùng mức assurance giữa các hệ thống.

**Câu 5.** Nếu người dùng đã xác thực bằng passkey, ứng dụng có thể bỏ qua authorization không?

**Gợi ý:** Không. Passkey xác minh chủ thể; ứng dụng vẫn phải kiểm tra tenant, role, scope, quyền sở hữu và resource/action.

**Câu 6.** Sau khi step-up thành công, vì sao cần kiểm tra lại quyền trước khi thực hiện?

**Gợi ý:** Quyền hoặc trạng thái tài nguyên có thể đã thay đổi trong lúc người dùng xác thực lại; cần tránh TOCTOU và dùng policy hiện hành.

**Câu 7.** IP quen thuộc có chứng minh thiết bị hoặc người dùng đáng tin không?

**Gợi ý:** Không. IP là tín hiệu rủi ro có thể thay đổi hoặc dùng chung; cần kết hợp bằng chứng xác thực và tín hiệu được xác minh khác.

## 18. Ghi nhớ

**Ứng dụng dùng authentication context để hiểu một phiên hoặc token được tạo ra trong hoàn cảnh xác thực nào, rồi kết hợp thông tin đó với authorization policy.** Context đáng tin phải đến từ issuer đã xác minh, gắn đúng principal, client, audience, tenant và giao dịch; các trường như auth_time, ACR, AMR hoặc AuthnContextClassRef chỉ có ý nghĩa theo contract rõ ràng. Ứng dụng cần đánh giá freshness, yêu cầu step-up khi cần, kiểm tra lại quyền trên tài nguyên và thu hồi session khi trạng thái thay đổi. Xác thực mạnh không tự cấp quyền, và một header do client tự khai không thể thay thế bằng chứng xác thực đã được kiểm chứng.

# Replay detection (Phát hiện và ngăn chặn phát lại)

> **Chương:** Chống replay  
> **Module:** SECURITY_AUTHENTICATION_FUNDAMENTALS — tìm hiểu nguyên lý xác thực danh tính từ credential, mật khẩu, MFA, passkey và chứng chỉ đến token, phiên, liên kết danh tính và khôi phục tài khoản. Người học biết mô hình hóa ranh giới tin cậy, phòng chống phishing, replay, lạm dụng đăng nhập và thiết kế luồng xác thực an toàn.
>
> **Trọng tâm:** Nhận diện một thông điệp, bằng chứng hoặc request hợp lệ đã bị ghi lại rồi gửi lại; thiết kế cơ chế freshness, uniqueness, context binding và lưu dấu đã dùng để từ chối replay mà vẫn xử lý được retry hợp lệ, request đồng thời và lỗi hệ thống phân tán.

## Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích replay attack và phân biệt với brute force, credential stuffing, request retry và duplicate delivery.
2. Mô tả các điều kiện để một message/proof bị replay có thể được chấp nhận: tính hợp lệ mật mã, thời hạn, phạm vi và trạng thái đã dùng.
3. Thiết kế freshness bằng timestamp, nonce/challenge, sequence number, counter hoặc expiration.
4. Ràng buộc bằng chứng với đúng issuer, subject, client, session, endpoint, HTTP method, audience và transaction.
5. Giải thích vì sao jti, timestamp, nonce hoặc chữ ký riêng lẻ không tự động ngăn replay nếu không có kiểm tra trạng thái và context phù hợp.
6. Xây dựng replay cache hoặc kho trạng thái one-time có thao tác atomic, TTL và xử lý concurrency.
7. Phân biệt replay prevention với idempotency để xử lý retry và duplicate delivery an toàn.
8. Áp dụng nguyên tắc chống replay cho OIDC/OAuth, SAML, WebAuthn, OTP, DPoP, webhook và TLS 1.3.
9. Thiết kế response, monitoring và kiểm thử cho replay, clock skew, multi-region, storage outage và các tình huống race condition.

## 1. Replay attack là gì?

**Replay attack (tấn công phát lại)** xảy ra khi attacker ghi lại một thông điệp, request, assertion, mã xác thực hoặc bằng chứng hợp lệ rồi gửi lại để hệ thống thực hiện hành động lần nữa hoặc chấp nhận một phiên xác thực không được người dùng khởi tạo.

Replay thường không cần attacker biết secret ban đầu. Họ có thể chỉ cần bản sao của một thông điệp đã được ký, một OTP còn trong thời hạn, một authorization response, một bearer token hoặc một session cookie.

Ví dụ:

1. Người dùng gửi một request đã được xác thực để phê duyệt giao dịch.
2. Attacker có được bản sao request hoặc token từ một kênh bị lộ.
3. Attacker gửi lại nguyên request.
4. Nếu server chỉ kiểm tra chữ ký và thời hạn mà không kiểm tra request đã được dùng, hành động có thể bị thực hiện lần thứ hai.

Chữ ký số hoặc MAC chứng minh message được tạo bởi bên nắm khóa và chưa bị sửa theo cách bị phát hiện. Chúng **không tự chứng minh message mới**, chưa được dùng hoặc đang được gửi trong đúng transaction. Một message cũ vẫn có thể có chữ ký hoàn toàn hợp lệ.

### Replay có thể nhắm tới những gì?

- Password hoặc OTP được thu thập trong một lần đăng nhập.
- Authorization code, assertion hoặc token.
- Session cookie hoặc bearer token.
- Signed API request hoặc webhook.
- Challenge-response proof.
- Thông điệp điều khiển trong giao thức thiết bị/workload.
- Lệnh thanh toán, phê duyệt, chuyển quyền hoặc thay đổi trạng thái.

### Mục tiêu của replay protection

Hệ thống cần bảo đảm rằng bằng chứng được chấp nhận:

- Còn mới theo policy.
- Chỉ dùng được trong đúng ngữ cảnh.
- Chưa từng được sử dụng cho cùng mục đích.
- Gắn với đúng chủ thể, client, session hoặc transaction.
- Được xử lý an toàn khi nhiều request giống nhau tới đồng thời.

## 2. Phân biệt replay với retry và duplicate delivery

Không phải request giống nhau nào cũng là tấn công. Mạng có thể mất response sau khi server đã xử lý; client gửi lại request vì timeout. Message broker cũng có thể giao một event nhiều lần.

| Tình huống | Bản chất | Cách xử lý |
| --- | --- | --- |
| **Replay attack** | Attacker phát lại bằng chứng/request đã thu được để tái sử dụng quyền hoặc hành động. | Kiểm tra freshness, uniqueness, binding và trạng thái đã dùng. |
| **Network retry** | Client gửi lại vì không nhận được response hoặc không biết request đã hoàn tất chưa. | Dùng idempotency key và lưu kết quả để trả lại response phù hợp. |
| **Duplicate delivery** | Hệ thống hàng đợi giao lại cùng một event. | Consumer idempotent, deduplicate theo event ID và transaction. |
| **Brute force** | Thử nhiều secret hoặc giá trị khác nhau. | Rate limit, throttling, lockout/challenge phù hợp. |
| **Credential stuffing** | Dùng cặp credential đã lộ ở dịch vụ khác. | MFA/passkey, rate limit, breached-password screening và risk signals. |

### Ví dụ về khác biệt

Một webhook có event ID là evt-123 được nhà cung cấp gửi hai lần vì lần đầu timeout. Consumer nên chỉ thực hiện nghiệp vụ một lần và có thể trả response thành công cho lần giao lại.

Ngược lại, một authorization code đã được đổi lấy token thành công không được đổi lần thứ hai. Việc phát lại code phải bị từ chối, dù client nói rằng lần đầu không nhận được response. Client cần bắt đầu flow mới nếu kết quả lần đầu không thể xác định.

Replay prevention bảo vệ tính mới và tính duy nhất của bằng chứng. Idempotency bảo vệ nghiệp vụ khỏi side effect lặp khi một thao tác hợp lệ được gửi lại. Hai cơ chế thường cần được triển khai cùng nhau.

## 3. Điều kiện để một replay được chấp nhận

Một server dễ bị replay nếu nó chỉ kiểm tra một số thuộc tính mà bỏ qua trạng thái sử dụng.

Ví dụ, server kiểm tra:

- Chữ ký của request hợp lệ.
- Timestamp nằm trong vòng 5 phút.
- Token chưa hết hạn.

Attacker vẫn có thể gửi cùng request nhiều lần trong 5 phút đó. Mỗi lần chữ ký vẫn hợp lệ và timestamp vẫn nằm trong cửa sổ cho phép.

Một cơ chế tốt thường kết hợp ba thuộc tính:

1. **Freshness:** bằng chứng đủ mới, có thời hạn hoặc challenge đang hiệu lực.
2. **Uniqueness:** mỗi proof/event có identifier hoặc counter để nhận diện lần sử dụng.
3. **Context binding:** proof gắn với đúng subject, issuer, client, endpoint, method, session hoặc transaction.

~~~mermaid
flowchart TD
    R["Nhận message / proof"] --> C["Kiểm tra chữ ký hoặc MAC"]
    C --> V{"Bằng chứng hợp lệ?"}
    V -->|"Không"| X["Từ chối"]
    V -->|"Có"| F["Kiểm tra freshness"]
    F --> T{"Còn trong thời hạn?"}
    T -->|"Không"| X
    T -->|"Có"| B["Kiểm tra context binding"]
    B --> K{"Đúng issuer, subject,\nclient và transaction?"}
    K -->|"Không"| X
    K -->|"Có"| U["Atomically claim nonce / jti / counter"]
    U --> D{"Đã được dùng?"}
    D -->|"Có"| P["Từ chối replay hoặc trả kết quả idempotent"]
    D -->|"Không"| A["Thực hiện hành động"]
    A --> S["Ghi kết quả và audit"]
~~~

Thứ tự chi tiết phụ thuộc giao thức. Ví dụ, chỉ claim nonce sau khi chữ ký đã được xác minh để tránh attacker gửi giá trị ngẫu nhiên nhằm làm cạn replay store. Tuy nhiên, bước claim và bước thực hiện side effect cần được phối hợp để hai request đồng thời không cùng được chấp nhận.

## 4. Timestamp và cửa sổ freshness

Timestamp cho biết thời điểm message được tạo hoặc ký. Server so sánh với đồng hồ hiện tại để từ chối message quá cũ hoặc ở tương lai vượt giới hạn.

Ví dụ policy:

~~~text
accepted_time_window = 5 minutes
allowed_clock_skew = 60 seconds

accept only if:
  issued_at <= now + allowed_clock_skew
  issued_at >= now - accepted_time_window
~~~

Các con số chỉ là minh họa. Cửa sổ thực tế phải dựa trên độ trễ, độ lệch đồng hồ, mức nhạy cảm và đặc tả giao thức.

### Timestamp giúp gì?

- Giới hạn khoảng thời gian attacker có thể phát lại message.
- Phát hiện request quá cũ hoặc timestamp ở tương lai bất thường.
- Hỗ trợ điều tra và tương quan sự kiện.
- Cho phép TTL replay cache được tính theo cửa sổ chấp nhận.

### Timestamp không làm được gì?

Timestamp đơn lẻ không ngăn replay trong cửa sổ hợp lệ. Nếu request được ký lúc 10:00 và server chấp nhận đến 10:05, attacker có thể gửi lại cùng request nhiều lần trong khoảng đó nếu server không có uniqueness check.

Timestamp cũng phụ thuộc đồng hồ. Nếu server có clock skew lớn, message hợp lệ có thể bị từ chối hoặc message cũ được chấp nhận lâu hơn dự kiến.

### Khuyến nghị

- Đồng bộ thời gian bằng hạ tầng time synchronization đáng tin cậy.
- Dùng UTC và quy ước rõ đơn vị giây/millisecond.
- Đặt clock skew nhỏ, có giới hạn.
- Kiểm tra timestamp không vượt quá tương lai.
- Kết hợp timestamp với nonce, jti, sequence number hoặc idempotency record.
- Không dùng timestamp do client khai làm bằng chứng duy nhất về thời điểm.

## 5. Nonce và challenge-response

**Nonce (number used once)** là giá trị dùng một lần. Server tạo nonce khó đoán, gắn với transaction và gửi cho client. Client phải đưa nonce vào bằng chứng phản hồi; server kiểm tra nonce thuộc transaction đang chờ và chưa được sử dụng.

### Luồng cơ bản

~~~mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant S as Server
    C->>S: Yêu cầu bắt đầu xác thực
    S->>S: Tạo nonce ngẫu nhiên, lưu trạng thái pending
    S-->>C: Challenge nonce + transaction reference
    C->>C: Tạo proof có ràng buộc nonce
    C->>S: Proof + nonce
    S->>S: Xác minh proof và context
    S->>S: Atomically chuyển nonce pending -> consumed
    S-->>C: Chấp nhận hoặc từ chối
~~~

### Nonce cần có những thuộc tính nào?

- Được tạo bằng bộ sinh số ngẫu nhiên mật mã.
- Đủ entropy và không thể dự đoán thực tế.
- Có TTL ngắn, phù hợp với flow.
- Gắn với đúng client, subject/session nếu đã biết, purpose và transaction.
- Chỉ được dùng một lần.
- Được tiêu thụ bằng thao tác atomic.
- Không được tái sử dụng giữa tenant hoặc protocol context không liên quan.

### Vì sao nonce phải gắn với context?

Nếu nonce chỉ được kiểm tra là “có tồn tại”, attacker có thể cố dùng một challenge hợp lệ trong flow khác. Hãy ràng buộc challenge với mục đích cụ thể, ví dụ đăng nhập, đổi email, ký giao dịch hoặc thêm authenticator.

Không dùng cùng một nonce cho login và transaction approval. Không nhận nonce từ browser như một giá trị tự do rồi coi nó là bằng chứng server đã phát hành.

## 6. jti, message ID và replay cache

JWT có thể chứa claim jti (JWT ID) để định danh token. Signed request, webhook hoặc message cũng có thể có event ID riêng.

Tuy nhiên, **jti chỉ là identifier**. Nó không tự ngăn replay. Server phải lưu hoặc kiểm tra identifier đã xử lý trong phạm vi phù hợp.

### Replay cache

Replay cache lưu dấu những identifier đã được chấp nhận trong một cửa sổ thời gian.

Key nên được namespace theo nguồn và mục đích, ví dụ:

~~~text
replay:<issuer>:<client_id>:<purpose>:<jti>
~~~

Không dùng jti trần làm key toàn hệ thống vì các issuer/client khác nhau có thể tạo giá trị trùng nhau.

### TTL

TTL cần tồn tại ít nhất trong thời gian mà message còn có thể được chấp nhận, cộng clock skew và biên xử lý cần thiết.

Nếu TTL quá ngắn, attacker có thể phát lại sau khi entry bị xóa nhưng message vẫn còn trong cửa sổ chấp nhận. Nếu TTL quá dài, replay store tăng kích thước và có thể giữ dữ liệu lâu hơn cần thiết.

### Chỉ ghi vào cache sau khi xác minh

Không nên cho bất kỳ request chưa xác minh nào ghi hàng triệu jti vào replay cache. Quy trình thường là:

1. Kiểm tra format và giới hạn kích thước.
2. Xác minh chữ ký/MAC và nguồn phát hành.
3. Kiểm tra issuer, audience, thời gian và purpose.
4. Thực hiện thao tác atomic để claim identifier.
5. Nếu claim thành công, tiếp tục xử lý.
6. Nếu identifier đã tồn tại, từ chối replay hoặc trả kết quả idempotent theo hợp đồng.

## 7. Atomicity và concurrency

Một lỗi thường gặp là thực hiện hai bước riêng:

1. Kiểm tra jti chưa tồn tại.
2. Ghi jti vào cache.

Hai request giống nhau có thể tới đồng thời. Cả hai cùng đọc thấy chưa tồn tại rồi cùng tiếp tục.

### Race condition

~~~mermaid
sequenceDiagram
    autonumber
    participant R1 as Request A
    participant R2 as Request B
    participant DB as Replay store
    R1->>DB: Check jti-123
    DB-->>R1: Not found
    R2->>DB: Check jti-123
    DB-->>R2: Not found
    R1->>DB: Insert jti-123
    DB-->>R1: Inserted
    R2->>DB: Insert jti-123
    DB-->>R2: Conflict
    Note over R1,R2: Chỉ request thắng thao tác atomic được xử lý
~~~

Cách đúng là dùng primitive atomic như:

- Redis SET với NX và EX trong một lệnh.
- Database unique constraint trên replay key.
- Compare-and-set hoặc transaction serializable phù hợp.
- Atomic update counter/nonce state.

Không tách check và insert thành hai request không có khóa hoặc transaction.

### Khi request hợp lệ bị retry

Nếu request đầu đã claim jti nhưng server lỗi trước khi trả response, request retry sẽ bị xem là đã dùng. Điều đó an toàn cho chống replay, nhưng có thể khiến client không biết kết quả.

Với nghiệp vụ cần retry, lưu cả trạng thái xử lý và kết quả theo idempotency key. Request lặp với cùng key và cùng payload có thể nhận lại kết quả đã lưu; request cùng key nhưng payload khác phải bị từ chối.

## 8. Sequence number và counter

Một số giao thức dùng sequence number hoặc counter tăng đơn điệu thay cho nonce ngẫu nhiên.

Ví dụ, client gửi sequence 41, server lưu giá trị lớn nhất đã chấp nhận là 40 rồi chuyển lên 41. Nếu attacker phát lại sequence 41, server từ chối vì không tăng.

### Ưu điểm

- Phát hiện message cũ theo thứ tự.
- Không cần lưu mọi identifier nếu chỉ chấp nhận thứ tự nghiêm ngặt.
- Phù hợp với kết nối hoặc thiết bị có trạng thái đồng bộ.

### Giới hạn

- Mất đồng bộ khi message bị mất hoặc tới sai thứ tự.
- Nhiều node client dùng chung counter có thể tạo xung đột.
- Reset thiết bị hoặc restore backup có thể làm counter quay lùi.
- Cần bảo vệ trạng thái counter khỏi rollback.
- Xử lý concurrent request cần atomic compare-and-update.

Một số giao thức cho phép sliding window để chấp nhận message đến sai thứ tự trong giới hạn. Khi đó server phải lưu bitmap/window trạng thái đã dùng, không chỉ so sánh số lớn nhất.

## 9. OTP: chống dùng lại mã trong thời gian hợp lệ

TOTP tạo mã từ secret và time step. Một mã có thể hợp lệ trong một khoảng thời gian ngắn, thường do cấu hình step và clock drift. Nếu attacker lấy được mã, họ có thể sử dụng trước khi mã hết hạn.

Chỉ kiểm tra mã đúng trong time window không ngăn việc dùng lại cùng mã nhiều lần trong một time step.

### Ngăn TOTP replay

- Sau khi mã được xác minh, lưu time-step tương ứng đã được chấp nhận cho credential/account.
- Từ chối cùng time-step nếu đã được sử dụng.
- Cập nhật trạng thái bằng thao tác atomic để hai request đồng thời không cùng thành công.
- Giới hạn drift window và số lần thử.
- Bảo vệ secret TOTP và quy trình enrollment/recovery.

Một số hệ thống không thể xác định duy nhất mã đã nhập nếu cùng một giá trị xuất hiện ở nhiều time step trong cửa sổ drift. Thiết kế cần lưu step được khớp và ngăn sử dụng lại theo policy.

### HOTP

HOTP dựa trên counter. Server cần quản lý counter đã đồng bộ, chỉ chấp nhận counter mới trong look-ahead window giới hạn và cập nhật counter atomic sau khi xác minh. Không cho phép một counter đã dùng được chấp nhận lần nữa.

### OTP không phải phishing-resistant

OTP one-time ở góc nhìn giao thức vẫn có thể bị relay theo thời gian thực trước khi server ghi nhận nó đã dùng. Chống replay code sau khi sử dụng không đồng nghĩa chống AiTM. Passkey/WebAuthn có origin binding cung cấp bảo vệ khác và mạnh hơn trước phishing.

## 10. OIDC và OAuth: state, nonce, code và token

Các flow OIDC/OAuth có nhiều giá trị giúp ràng buộc response với transaction.

### state

RP tạo state ngẫu nhiên khi bắt đầu authorization request, lưu cùng browser transaction và kiểm tra giá trị quay về ở callback. State giúp chống login CSRF và response injection bằng cách chứng minh callback gắn với transaction do RP khởi tạo.

State cần có entropy, TTL, ràng buộc browser/session và được tiêu thụ một lần.

### nonce

Trong OIDC, RP có thể gửi nonce trong authentication request. OP đưa nonce vào ID token; RP kiểm tra giá trị khớp transaction đã lưu. Điều này ràng buộc ID token với request và giúp chống replay token giữa các authentication transaction.

### PKCE

PKCE ràng buộc authorization code với code verifier do client giữ. Nó giảm nguy cơ code bị chặn trên redirect channel có thể được đổi bởi bên khác. PKCE không thay thế state, nonce, redirect URI validation hoặc token validation.

### Authorization code

Authorization code phải ngắn hạn, gắn với client và redirect URI theo flow, và chỉ được đổi một lần. Authorization server phải đánh dấu code đã redeemed atomically. Gửi lại code đã đổi phải bị từ chối.

### ID token và access token

- Xác minh chữ ký, issuer, audience, thời hạn và claim theo loại token.
- Kiểm tra nonce trong ID token khi flow yêu cầu.
- Không coi jti là replay protection nếu không có trạng thái theo dõi.
- Access token bearer bị đánh cắp có thể bị phát lại trong thời hạn; dùng TTL phù hợp, audience/scope giới hạn và sender-constrained token khi cần.
- Refresh token rotation cần phát hiện reuse theo family và xử lý compromise theo policy.

## 11. SAML: assertion ID, InResponseTo và thời hạn

SAML assertion hoặc response có thể bị phát lại nếu Service Provider chỉ xác minh chữ ký mà không theo dõi việc đã nhận assertion.

Các kiểm tra thường cần:

- Chữ ký hợp lệ theo issuer/metadata tin cậy.
- Issuer, audience, destination và recipient đúng.
- Conditions và NotBefore/NotOnOrAfter hợp lệ.
- InResponseTo khớp AuthnRequest đang chờ nếu flow yêu cầu.
- Assertion ID hoặc response ID chưa được sử dụng.
- SubjectConfirmationData hợp lệ.
- Assertion được lưu vào replay cache trong cửa sổ có thể chấp nhận.

Không dùng assertion ID làm khóa toàn cục không namespace. Ràng buộc với issuer và SP/entity ID.

Một assertion đã được chấp nhận cần bị đánh dấu consumed để một response giống hệt không thể tạo session thứ hai. Cache phải giữ entry đủ lâu qua NotOnOrAfter và clock skew.

## 12. WebAuthn/passkey và challenge replay

WebAuthn sử dụng challenge do RP tạo để ràng buộc assertion với một lần xác thực cụ thể.

Server cần:

1. Sinh challenge ngẫu nhiên và lưu pending theo transaction.
2. Gắn challenge với đúng user/session và RP context.
3. Nhận assertion từ browser.
4. Xác minh challenge, origin, RP ID hash, credential ID và chữ ký.
5. Kiểm tra user presence/user verification theo policy.
6. Atomically đánh dấu challenge đã dùng.
7. Tạo session mới nếu tất cả điều kiện đạt.

Nếu challenge được tái sử dụng hoặc không ràng buộc đúng transaction, assertion cũ có thể bị thử lại.

### Signature counter

Authenticator có thể cung cấp signature counter để phát hiện một số trường hợp credential bị clone. Tuy nhiên, passkey đồng bộ đa thiết bị có thể không cung cấp counter tăng đơn điệu đáng tin cậy; một số authenticator luôn trả 0. Vì vậy counter không phải cơ chế chống replay duy nhất và RP cần tuân theo WebAuthn guidance khi diễn giải giá trị này.

## 13. DPoP và sender-constrained token

Bearer token có thể được bất kỳ bên nào nắm token sử dụng trong phạm vi audience/scope và thời hạn. Sender-constrained token ràng buộc token với khóa hoặc client proof, khiến token bị đánh cắp khó dùng độc lập hơn.

**DPoP (Demonstrating Proof of Possession)** dùng một proof JWT được client ký cho HTTP request. Proof có thể mang:

- jti: định danh proof.
- htm: HTTP method.
- htu: HTTP target URI.
- iat: thời điểm tạo proof.
- ath: hash access token khi áp dụng.
- nonce của server nếu server yêu cầu theo profile.

Resource server/authorization server xác minh proof, token binding và context request. Replay cache cho jti trong phạm vi phù hợp giúp ngăn cùng proof được dùng lại.

DPoP không biến token thành bất khả xâm phạm. Attacker có thể cố lấy cả private key hoặc khai thác thiết bị đã bị compromise. Phải bảo vệ khóa, kiểm tra token cnf/binding, audience, URI, method và thời gian.

mTLS-bound access token là một lựa chọn sender-constrained khác, ràng buộc token với chứng chỉ client theo cơ chế của authorization/resource server.

## 14. Webhook và signed API request

Webhook thường được gửi qua mạng và có thể bị giao lại khi timeout. HMAC hoặc chữ ký bảo vệ tính toàn vẹn nhưng không tự ngăn event cũ được gửi lại.

### Các trường nên có

- Event ID duy nhất.
- Timestamp do sender ký.
- Payload/body được ký hoặc hash theo canonicalization đã thống nhất.
- Signature version/key ID để quản lý khóa.
- Context về tenant, event type và endpoint.

### Consumer xử lý

1. Xác minh nguồn gửi và chữ ký.
2. Kiểm tra timestamp nằm trong cửa sổ chấp nhận.
3. Tạo dedup key có namespace theo sender/tenant/event.
4. Dùng atomic insert/unique constraint để claim event.
5. Nếu event mới, xử lý nghiệp vụ và lưu kết quả.
6. Nếu event trùng, trả response theo hợp đồng idempotency mà không lặp side effect.
7. Ghi audit và theo dõi event bất thường.

Timestamp đơn lẻ không ngăn replay trong cửa sổ. Event ID cần được lưu đủ lâu theo retry policy và thời gian có thể giao lại.

Với signed API request, nên ràng buộc chữ ký với method, canonical URI, body digest, timestamp, nonce và key identity. Nếu chỉ ký body mà không ký method/path, cùng body có thể bị chuyển sang endpoint hoặc thao tác khác.

## 15. TLS 1.3 và replay trong 0-RTT

TLS 1.3 hỗ trợ 0-RTT early data trong một số trường hợp để giảm độ trễ khi kết nối lại. Early data có đặc tính có thể bị replay trong một số mô hình triển khai và mạng phân tán.

Vì vậy server không nên mặc nhiên xử lý request thay đổi trạng thái hoặc không idempotent trong early data nếu không có anti-replay guarantee phù hợp.

### Biện pháp

- Tắt 0-RTT cho endpoint có side effect nhạy cảm.
- Chỉ cho phép early data đối với thao tác idempotent, an toàn theo thiết kế.
- Áp dụng anti-replay mechanism của TLS stack và deployment topology.
- Không giả định chống replay ở một node tự động bảo vệ khi có nhiều node/region.
- Kiểm thử hành vi retry/replay qua load balancer và cluster.

TLS bảo vệ kênh truyền; replay policy của ứng dụng vẫn cần được thiết kế cho các hành động nghiệp vụ.

## 16. Replay store trong Java và hệ thống phân tán

Một replay store cần cung cấp thao tác “claim nếu chưa tồn tại” một cách atomic.

### Giao diện khái niệm

~~~java
import java.time.Duration;

public interface ReplayStore {
    boolean claim(String namespace, String identifier, Duration ttl);
}
~~~

Kết quả:

- true: identifier được ghi nhận lần đầu trong namespace và TTL; caller có thể tiếp tục nếu các kiểm tra khác đều đạt.
- false: identifier đã được claim; request cần được xử lý như replay/duplicate theo policy.

Một triển khai Redis có thể dùng một lệnh atomic tương đương SET key value NX EX ttl. Không thực hiện GET rồi SET riêng biệt.

### Pseudocode xử lý

~~~java
public Result verifyRequest(SignedRequest request) {
    verifySignature(request);
    verifyIssuerAudienceAndPurpose(request);
    verifyTimestamp(request.issuedAt());

    boolean firstUse = replayStore.claim(
            request.issuer() + ":" + request.clientId() + ":" + request.purpose(),
            request.jti(),
            Duration.ofMinutes(6)
    );

    if (!firstUse) {
        return Result.replayRejected();
    }

    return processBusinessAction(request);
}
~~~

Đây là ví dụ minh họa, không phải thư viện hoàn chỉnh. Production code cần xử lý exception, clock skew, payload validation, authorization, idempotency, transaction và chính sách khi replay store không khả dụng. TTL sáu phút chỉ là giá trị ví dụ.

### Lưu trong database

Có thể dùng bảng có unique constraint trên namespace + identifier:

~~~sql
CREATE TABLE consumed_proof (
    namespace VARCHAR(300) NOT NULL,
    proof_id VARCHAR(300) NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP NOT NULL,
    PRIMARY KEY (namespace, proof_id)
);
~~~

Insert thành công nghĩa proof được claim. Unique conflict nghĩa identifier đã tồn tại. Cần job dọn entry hết hạn và bảo đảm transaction/consistency phù hợp.

### Multi-region

Nếu hai region dùng replay store độc lập và replication trễ, cùng một proof có thể được chấp nhận ở cả hai region trước khi state đồng bộ.

Các lựa chọn:

- Dùng store strongly consistent hoặc partition ownership theo namespace.
- Route cùng subject/client/transaction về một vùng có authority.
- Dùng global atomic uniqueness store cho hành động nhạy cảm.
- Thiết kế business operation idempotent ở database cuối cùng.
- Đánh giá trade-off giữa availability, latency và anti-replay guarantee.

Không tuyên bố replay protection toàn cục nếu uniqueness chỉ được bảo đảm trong từng node hoặc từng region.

## 17. Fail-open, fail-closed và khả năng sẵn sàng

Nếu replay store không khả dụng, server phải quyết định có tiếp tục hay không.

| Loại thao tác | Hướng xử lý thường phù hợp | Lý do |
| --- | --- | --- |
| Đăng nhập hoặc xác thực nhạy cảm | Fail closed hoặc chuyển sang flow dự phòng đã được phê duyệt. | Không thể chứng minh proof chưa dùng. |
| Phê duyệt giao dịch/tạo quyền | Fail closed. | Replay có thể tạo side effect nghiêm trọng. |
| Webhook có idempotency ở database nghiệp vụ | Có thể dùng dedupe store thay thế nếu bảo đảm atomic. | Cần tránh duplicate side effect. |
| Nội dung đọc công khai | Có thể không cần replay store nếu request không tạo trạng thái. | Hậu quả replay thấp hoặc không có. |
| Telemetry phụ trợ | Có thể tiếp tục nhưng đánh dấu trạng thái degraded. | Không phải bằng chứng xác thực. |

Không có một quy tắc fail-open/closed áp dụng cho mọi request. Hãy phân loại endpoint theo side effect và hậu quả, rồi ghi rõ hành vi khi storage, clock hoặc dependency lỗi.

## 18. Rủi ro và lỗi triển khai thường gặp

| Lỗi | Hậu quả | Biện pháp |
| --- | --- | --- |
| Chỉ kiểm tra chữ ký | Message cũ vẫn hợp lệ và được phát lại. | Freshness, uniqueness và context binding. |
| Chỉ kiểm tra timestamp | Cùng message được gửi nhiều lần trong cửa sổ. | Nonce/jti/counter và replay store. |
| Có jti nhưng không lưu | Không biết identifier đã được dùng. | Atomic claim trong namespace phù hợp. |
| Nonce dùng lại giữa transaction | Proof của flow này có thể bị dùng trong flow khác. | Bind nonce với client, subject, purpose và transaction. |
| Check rồi insert riêng | Hai request đồng thời cùng vượt qua. | Atomic SET NX, unique constraint hoặc CAS. |
| TTL quá ngắn | Replay sau khi entry hết hạn nhưng message còn hợp lệ. | TTL bao phủ toàn bộ acceptance window và skew. |
| Replay cache theo từng node | Request tới node khác được chấp nhận lần nữa. | Shared/partitioned consistency phù hợp. |
| Lưu replay entry trước khi verify | Attacker có thể làm đầy store bằng ID giả. | Xác minh chữ ký/context trước khi claim. |
| Không kiểm tra audience/purpose | Proof hợp lệ cho dịch vụ này bị dùng ở dịch vụ khác. | Context binding và audience validation. |
| TOTP chấp nhận lại trong cùng time step | Mã bị đánh cắp được dùng nhiều lần. | Lưu step đã chấp nhận và atomic update. |
| Dùng signature counter làm cơ chế duy nhất | False positive/false negative với authenticator đồng bộ. | Theo guidance; kết hợp challenge và state. |
| Không xử lý retry | Request hợp lệ bị timeout rồi client không biết kết quả. | Idempotency key và stored response. |
| Dùng idempotency thay nonce | Một proof xác thực bị tái sử dụng trong context khác. | Tách mục đích hai cơ chế và bind đúng scope. |
| Không bảo vệ clock | Message cũ hoặc tương lai được chấp nhận. | Time sync và skew policy có giới hạn. |
| Bỏ qua 0-RTT replay | Early data có side effect bị xử lý nhiều lần. | Disable hoặc giới hạn early data và anti-replay. |
| Fail-open khi store lỗi | Không thể kiểm tra proof đã dùng. | Policy theo rủi ro; fail closed cho thao tác nhạy cảm. |

## 19. Ví dụ thực tế: Learning Platform

Learning Platform cho phép học viên đăng nhập bằng OIDC/passkey và gửi yêu cầu phê duyệt thay đổi email khôi phục.

### Đăng nhập

1. RP tạo state và nonce ngẫu nhiên, lưu trong transaction server-side.
2. Browser chuyển tới OP với authorization request và PKCE challenge.
3. OP xác thực người học và trả authorization code.
4. RP kiểm tra state, đổi code một lần bằng PKCE verifier.
5. RP xác minh ID token, issuer, audience, signature, expiry và nonce.
6. RP atomically tiêu thụ transaction/state/nonce; nếu đã dùng thì từ chối.
7. RP tạo session mới và lưu authentication context.

### Phê duyệt đổi email

1. Server tạo challenge gắn với subject, session, action và email đích.
2. Người dùng xác thực lại bằng passkey.
3. Server xác minh challenge, origin, RP ID, chữ ký và user verification.
4. Server atomically claim challenge.
5. Server kiểm tra policy, transaction và authorization.
6. Server ghi kết quả idempotent và thực hiện thay đổi đúng một lần.
7. Hệ thống gửi thông báo qua kênh đã đăng ký trước.

Nếu attacker ghi lại assertion hoặc request phê duyệt, challenge đã consumed nên proof cũ bị từ chối. Nếu browser retry vì response timeout, client gửi idempotency key của transaction; server trả kết quả đã lưu mà không thực hiện thay đổi lần nữa.

## 20. Kiểm thử replay protection

| Kịch bản | Cách kiểm tra | Kết quả mong đợi |
| --- | --- | --- |
| Timestamp hợp lệ, message mới | Gửi signed request với timestamp hiện tại và jti mới. | Chấp nhận nếu các kiểm tra khác đạt. |
| Timestamp cũ | Gửi request ngoài freshness window. | Từ chối. |
| Timestamp tương lai | Đặt thời gian vượt clock skew. | Từ chối hoặc xử lý theo policy rõ. |
| Cùng jti gửi hai lần | Gửi lại cùng signed request. | Chỉ một lần được claim; lần sau bị từ chối/deduplicate. |
| Hai request đồng thời cùng jti | Gửi song song tới nhiều worker. | Chỉ một request claim thành công. |
| jti trùng giữa issuer khác nhau | Dùng cùng identifier ở hai namespace khác. | Không gây collision hoặc cross-issuer trust. |
| Nonce sai transaction | Dùng challenge của flow A cho flow B. | Từ chối. |
| Nonce đã consumed | Gửi lại proof đã được chấp nhận. | Từ chối replay. |
| Replay store timeout | Làm dependency không khả dụng. | Hành vi đúng fail policy; không âm thầm bỏ kiểm tra. |
| TTL boundary | Gửi lại ở sát và sau thời điểm hết hạn. | TTL bao phủ acceptance window; không mở cửa sổ replay ngoài ý muốn. |
| Multi-node replay | Gửi cùng proof tới hai node. | Shared/partitioned store ngăn chấp nhận hai lần. |
| Multi-region replay | Gửi cùng proof đồng thời tới hai region. | Consistency guarantee được kiểm chứng. |
| TOTP reuse | Dùng lại mã trong cùng time step. | Từ chối lần dùng lại theo policy. |
| HOTP counter rollback | Gửi counter đã chấp nhận. | Từ chối. |
| OIDC state replay | Gửi lại callback đã dùng. | Transaction không còn pending; callback bị từ chối. |
| OIDC nonce mismatch | Dùng ID token với nonce khác. | Từ chối token. |
| Authorization code reuse | Đổi cùng code hai lần. | Chỉ lần đầu hợp lệ; lần sau bị từ chối. |
| SAML assertion replay | Gửi lại assertion ID đã chấp nhận. | Từ chối theo replay cache. |
| WebAuthn challenge replay | Dùng assertion/challenge đã tiêu thụ. | Từ chối. |
| DPoP proof replay | Gửi lại cùng jti/proof trong thời hạn. | Replay detection từ chối. |
| Webhook duplicate | Gửi cùng event ID nhiều lần. | Side effect chỉ xảy ra một lần; response theo idempotency contract. |
| Same idempotency key, different body | Gửi cùng key với payload khác. | Từ chối conflict. |
| TLS 1.3 early data | Thử request có side effect trong 0-RTT test. | Endpoint bị hạn chế hoặc có anti-replay bảo đảm phù hợp. |
| Clock drift | Mô phỏng node lệch thời gian. | Skew policy nhất quán; không chấp nhận message cũ ngoài giới hạn. |

## 21. Checklist thiết kế

- [ ] Đã xác định message/proof/token nào có thể bị ghi lại và phát lại.
- [ ] Mỗi flow có freshness rule và acceptance window rõ ràng.
- [ ] Có nonce/challenge hoặc identifier/counter phù hợp.
- [ ] Proof được bind với issuer, subject, client, audience, method, URI, purpose và transaction khi cần.
- [ ] Chữ ký/MAC được xác minh trước khi replay identifier được claim.
- [ ] Nonce/jti/event ID được lưu bằng thao tác atomic.
- [ ] Replay store có namespace, TTL, giới hạn kích thước và cleanup.
- [ ] TTL bao phủ acceptance window và clock skew.
- [ ] Concurrency và multi-node/multi-region đã được đánh giá.
- [ ] TOTP/HOTP có chống reuse và cập nhật counter/time-step atomic.
- [ ] OIDC state, nonce, PKCE và authorization code được kiểm tra đúng vai trò.
- [ ] SAML assertion/response ID và InResponseTo được theo dõi.
- [ ] WebAuthn challenge dùng một lần; signature counter không bị coi là cơ chế duy nhất.
- [ ] DPoP proof được bind với token và HTTP request; jti có replay detection.
- [ ] Webhook/API request có event ID, timestamp và payload binding.
- [ ] TLS 1.3 0-RTT không dùng cho side effect nếu thiếu anti-replay guarantee.
- [ ] Idempotency được tách biệt với replay prevention.
- [ ] Có policy fail-open/fail-closed theo mức hậu quả khi store/dependency lỗi.
- [ ] Audit không ghi secret, raw token hoặc dữ liệu xác thực nhạy cảm.
- [ ] Có kiểm thử replay song song, retry, clock skew, TTL boundary và storage outage.

## 22. Tự kiểm tra

**Câu 1.** Replay attack là gì?

**Đáp án:** Là việc attacker ghi lại một message, proof, token hoặc request hợp lệ rồi gửi lại để tái sử dụng quyền hoặc lặp hành động.

**Câu 2.** Chữ ký hợp lệ có chứng minh message chưa từng được dùng không?

**Đáp án:** Không. Chữ ký chứng minh tính toàn vẹn và nguồn tạo theo khóa; cần freshness, uniqueness và context binding để chống replay.

**Câu 3.** Timestamp có tự ngăn replay không?

**Đáp án:** Không. Timestamp chỉ giới hạn cửa sổ thời gian. Cùng message vẫn có thể được gửi nhiều lần trong cửa sổ đó nếu không có nonce/jti/counter hoặc trạng thái đã dùng.

**Câu 4.** Vì sao jti không tự là replay protection?

**Đáp án:** jti chỉ là identifier. Server phải lưu/claim identifier một cách atomic và kiểm tra trùng trong namespace, TTL phù hợp.

**Câu 5.** Vì sao check rồi insert replay key riêng biệt không an toàn?

**Đáp án:** Hai request đồng thời có thể cùng đọc thấy key chưa tồn tại rồi cùng tiếp tục. Cần primitive atomic như SET NX hoặc unique constraint.

**Câu 6.** Replay prevention khác idempotency thế nào?

**Đáp án:** Replay prevention từ chối proof/message đã dùng; idempotency cho phép retry hợp lệ mà không lặp side effect, thường trả lại kết quả đã lưu.

**Câu 7.** TOTP đúng trong time window có thể bị dùng lại không?

**Đáp án:** Có. Nếu server chỉ kiểm tra mã đúng mà không lưu time-step đã chấp nhận, cùng mã có thể được dùng lại trong cùng step. Cần atomic tracking.

**Câu 8.** WebAuthn chống replay bằng những cơ chế nào?

**Đáp án:** RP tạo challenge ngẫu nhiên, gắn với transaction và kiểm tra challenge, origin, RP ID, chữ ký, user presence/verification; challenge được tiêu thụ một lần.

**Câu 9.** Vì sao cần replay store dùng chung hoặc nhất quán trong hệ nhiều node?

**Đáp án:** Nếu mỗi node có cache riêng, cùng proof có thể được chấp nhận ở node khác. Cần uniqueness guarantee trên phạm vi hệ thống hoặc partition có authority rõ.

**Câu 10.** Khi replay store không khả dụng, có nên luôn fail open để giữ availability không?

**Đáp án:** Không. Với login, giao dịch hoặc thao tác nhạy cảm, không chứng minh được proof chưa dùng thì thường phải fail closed hoặc dùng cơ chế dự phòng đã được phê duyệt. Quyết định phụ thuộc hậu quả và policy.

## Ghi nhớ

**Replay detection** nhận diện và từ chối việc tái sử dụng một message hoặc proof đã được chấp nhận. Một chữ ký hợp lệ hay timestamp còn mới chưa đủ: cần kết hợp freshness, uniqueness và context binding. Nonce/challenge, jti, sequence number, counter và expiration giải quyết những phần khác nhau của bài toán.

Trạng thái đã dùng phải được claim atomically trong replay store có namespace và TTL đúng; concurrency, retry, clock skew và multi-region đều ảnh hưởng tới bảo đảm thực tế. Phân biệt replay prevention với idempotency, áp dụng đúng cho OIDC/OAuth, SAML, WebAuthn, OTP, DPoP, webhook và TLS 0-RTT. **Một proof chỉ nên được chấp nhận một lần trong đúng ngữ cảnh đã phát hành; retry hợp lệ cần được xử lý bằng idempotency có kiểm soát, không bằng cách mở lại proof cũ.**

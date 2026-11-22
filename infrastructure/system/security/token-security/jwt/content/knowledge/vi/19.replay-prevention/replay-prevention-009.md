# Phân biệt JWT dùng một lần với token truy cập được phép tái sử dụng

## 1. Vì sao cần phân biệt hai loại token?

JWT là một định dạng mang claims được bảo vệ bằng chữ ký/MAC hoặc mã hóa theo profile JOSE. Bản thân JWT không tự quy định rằng một token chỉ được dùng một lần hay được phép dùng nhiều lần. Ngữ nghĩa sử dụng phụ thuộc vào loại credential, giao thức và chính sách của ứng dụng.

Hai trường hợp thường gặp có mục tiêu khác nhau:

- **JWT dùng một lần (one-time token):** được phát hành cho một hành động cụ thể, chẳng hạn đặt lại mật khẩu, xác nhận email, đăng nhập bằng magic link hoặc phê duyệt một giao dịch. Sau lần sử dụng hợp lệ đầu tiên, token phải bị đánh dấu đã tiêu thụ và không được dùng lại.
- **Access token tái sử dụng (reusable access token):** đại diện cho quyền truy cập một resource trong một khoảng thời gian. Client có thể gửi cùng access token trong nhiều request hợp lệ cho tới khi token hết hạn, bị thu hồi hoặc không còn đáp ứng policy.

Điểm khác biệt không nằm ở việc cả hai đều có thể là JWT có chữ ký. Điểm khác biệt nằm ở **chính sách tiêu thụ và trạng thái sử dụng**. Chữ ký xác minh token được phát hành bởi nguồn tin cậy và nội dung không bị sửa; chữ ký không tự ghi nhớ rằng token đã được sử dụng trước đó.

Một one-time JWT cần trạng thái phía server để ghi nhận việc tiêu thụ. Một access token thông thường được thiết kế để tái sử dụng trong thời hạn và phạm vi được cấp; resource server không được đánh dấu toàn bộ token là đã dùng chỉ vì một request thành công.

Bài học này thuộc phạm vi JWT/JOSE và bảo mật ứng dụng tổng quát, không phụ thuộc Java, Spring Security hay framework cụ thể.

## 2. Định nghĩa và ví dụ sử dụng

### One-time JWT

One-time JWT mang một quyền hoặc một hành động có thể được thực hiện tối đa một lần. Các trường hợp điển hình:

- Link đặt lại mật khẩu.
- Link xác nhận địa chỉ email.
- Magic link để hoàn tất một lần đăng nhập.
- Token xác nhận một hành động nhạy cảm đã được khởi tạo, ví dụ phê duyệt giao dịch.
- Assertion gửi tới một endpoint và chỉ được chấp nhận một lần, nếu profile yêu cầu replay detection.

Token cần được ràng buộc với đúng subject, mục đích, recipient và hành động. Sau khi xác minh chữ ký và các claim, server phải tiêu thụ token bằng thao tác nguyên tử để hai request đồng thời không thể cùng thành công.

### Reusable access token

Access token đại diện cho quyền truy cập một resource server hoặc nhóm resource được chỉ định. Ví dụ:

- Client gửi access token tới Orders API để đọc danh sách đơn hàng.
- Client tiếp tục dùng token đó cho request đọc chi tiết đơn hàng.
- Client gửi token trong nhiều request khác trong thời hạn hiệu lực, miễn là audience, scope và policy vẫn phù hợp.

Đây là hành vi bình thường. Access token không phải mã dùng một lần. Việc token có claim jti duy nhất cũng không làm nó trở thành one-time token.

### Bảng so sánh

| Tiêu chí | One-time JWT | Reusable access token |
| --- | --- | --- |
| Mục đích | Một hành động hoặc một lần đổi quyền cụ thể | Truy cập resource trong thời hạn được cấp |
| Số lần sử dụng | Tối đa một lần thành công theo policy | Nhiều request cho tới khi hết hạn/thu hồi |
| Trạng thái sử dụng | Phải ghi nhận trạng thái consumed/redeemed | Thường không ghi nhận token đã dùng sau mỗi request |
| jti | Định danh để lưu trạng thái tiêu thụ và phát hiện replay | Định danh token, hỗ trợ log/denylist; không đồng nghĩa one-time |
| exp | Giới hạn thời gian sử dụng | Giới hạn thời gian truy cập |
| Audience | Endpoint hoặc dịch vụ thực hiện hành động cụ thể | Resource server được phép nhận access token |
| Replay cùng token | Lần dùng thứ hai phải bị từ chối | Có thể là request hợp lệ nếu token còn hiệu lực và request được phép |
| Ví dụ | Password reset, email verification, magic link | OAuth access token cho API |

## 3. JWT có chữ ký không tự tạo ngữ nghĩa dùng một lần

Giả sử server phát hành một JWT có:

~~~json
{
  "iss": "https://identity.example",
  "sub": "user-4821",
  "aud": "https://identity.example/password-reset",
  "jti": "reset-7c19e3",
  "purpose": "password_reset",
  "iat": 1893450000,
  "exp": 1893450600
}
~~~

Nếu token được ký hợp lệ, server có thể xác minh:

- Token được ký bởi khóa tương ứng với issuer tin cậy.
- Payload chưa bị sửa sau khi ký.
- Token được phát hành cho endpoint đặt lại mật khẩu.
- Token có mục đích password_reset và chưa hết hạn.

Nhưng chữ ký không trả lời câu hỏi: token này đã được sử dụng thành công trước đó hay chưa?

Nếu server chỉ kiểm tra chữ ký, audience, purpose và exp, cùng một token vẫn có thể được gửi lại nhiều lần trong thời hạn hiệu lực. Muốn bảo đảm dùng một lần, server cần lưu dấu vết tiêu thụ, thường dựa trên issuer và jti.

### jti không tự động ngăn replay

RFC 7519 định nghĩa jti là JWT ID, một định danh duy nhất cho JWT. Giá trị này có thể được dùng để ngăn replay, nhưng việc đưa jti vào payload không tự tạo cơ chế chống replay.

Server cần:

1. Sinh jti đủ khó đoán và không trùng trong phạm vi cần thiết.
2. Xác minh chữ ký trước khi tin jti.
3. Lưu trạng thái sử dụng trong kho dữ liệu có thẩm quyền.
4. Đảm bảo việc chuyển trạng thái từ chưa dùng sang đã dùng là nguyên tử.
5. Từ chối mọi lần sử dụng tiếp theo trong phạm vi one-time policy.

Nếu không có bước lưu và kiểm tra trạng thái, jti chỉ là một claim định danh.

## 4. Thiết kế claim cho one-time JWT

Một one-time token nên có các claim đủ để giới hạn đúng hành động:

| Claim/thuộc tính | Mục đích |
| --- | --- |
| iss | Xác định issuer đã phát hành token |
| sub | Chủ thể mà hành động áp dụng |
| aud | Endpoint/service duy nhất hoặc profile recipient được phép xử lý |
| jti | Định danh duy nhất để lưu trạng thái tiêu thụ |
| iat | Thời điểm phát hành |
| exp | Thời điểm hết hạn |
| nbf | Thời điểm token bắt đầu có hiệu lực, nếu cần |
| purpose hoặc token_use | Claim riêng của profile để phân biệt password reset, email verification hoặc hành động khác |
| action/resource | Ràng buộc token với loại hành động hoặc resource cụ thể nếu cần |
| transaction binding | Ràng buộc với giao dịch cụ thể, ví dụ mã giao dịch hoặc digest của các thuộc tính đã chuẩn hóa |

purpose, token_use, action và transaction binding trong ví dụ là claim do profile ứng dụng định nghĩa, không phải claim JWT chuẩn bắt buộc.

Ví dụ token xác nhận email:

~~~json
{
  "iss": "https://identity.example",
  "sub": "user-4821",
  "aud": "https://identity.example/email-verification",
  "jti": "verify-4a91d2",
  "purpose": "email_verification",
  "iat": 1893450000,
  "exp": 1893453600
}
~~~

Ví dụ token phê duyệt giao dịch cần ràng buộc nội dung:

~~~json
{
  "iss": "https://identity.example",
  "sub": "user-4821",
  "aud": "https://payments.example/approve",
  "jti": "approval-91b4e2",
  "purpose": "payment_approval",
  "transaction_id": "txn-72831",
  "amount": 1250000,
  "currency": "VND",
  "iat": 1893450000,
  "exp": 1893450300
}
~~~

Nếu token dùng để phê duyệt một giao dịch, server cần kiểm tra dữ liệu giao dịch hiện tại khớp với nội dung đã được người dùng xác nhận. Không chỉ kiểm tra transaction_id nếu số tiền, người nhận hoặc loại hành động có thể thay đổi sau khi token được phát hành.

Không đưa dữ liệu cá nhân hoặc bí mật không cần thiết vào JWT. Payload có thể được đọc nếu chỉ dùng JWS; chữ ký không mã hóa nội dung.

## 5. Luồng tiêu thụ one-time token an toàn

Quy trình cơ bản:

1. Nhận token tại đúng endpoint dành cho purpose đó.
2. Kiểm tra kích thước, định dạng và parse theo profile.
3. Xác minh chữ ký/MAC, thuật toán allowlist, issuer và audience.
4. Kiểm tra exp, nbf, purpose, subject, transaction binding và các điều kiện nghiệp vụ.
5. Lấy jti từ claims đã xác minh.
6. Thực hiện thao tác consume nguyên tử: chỉ một request được chuyển jti từ unused sang consumed.
7. Thực hiện hành động nghiệp vụ gắn với việc tiêu thụ token.
8. Commit trạng thái tiêu thụ và kết quả nghiệp vụ theo một ranh giới transaction nhất quán.
9. Trả kết quả; lần gửi lại token phải bị từ chối hoặc trả lại kết quả đã lưu theo idempotency policy, không thực hiện hành động lần nữa.

~~~mermaid
flowchart TD
    A["Nhận one-time JWT"] --> B["Parse và xác minh chữ ký"]
    B --> C{"Issuer, audience, exp và purpose hợp lệ?"}
    C -- Không --> X["Từ chối"]
    C -- Có --> D["Đọc jti từ claims đã xác minh"]
    D --> E["Atomic consume jti"]
    E --> F{"Token chưa từng được tiêu thụ?"}
    F -- Không --> X
    F -- Có --> G["Thực hiện hành động nghiệp vụ"]
    G --> H{"Hành động và consume commit thành công?"}
    H -- Không --> I["Rollback hoặc xử lý trạng thái retry theo transaction policy"]
    H -- Có --> J["Trả kết quả"]
~~~

Không được đánh dấu token đã dùng chỉ dựa trên jti chưa xác minh. Kẻ tấn công có thể gửi token giả với jti của một token hợp lệ để cố tình tiêu thụ trước token thật. Luôn xác minh chữ ký và ràng buộc purpose/audience trước khi thực hiện thao tác consume.

## 6. Atomic consume: ngăn hai request dùng cùng token đồng thời

Kiểm tra kiểu read-then-write thông thường không đủ:

~~~text
if not isConsumed(jti):
    performAction()
    markConsumed(jti)
~~~

Hai request đồng thời có thể cùng đọc trạng thái chưa dùng trước khi một request ghi consumed. Cả hai đều thực hiện hành động, dẫn tới double redemption.

### Dùng unique constraint hoặc compare-and-set

Một cách là tạo bảng tiêu thụ với khóa duy nhất:

~~~sql
CREATE TABLE consumed_jwt (
    issuer       VARCHAR(512) NOT NULL,
    jti          VARCHAR(256) NOT NULL,
    purpose      VARCHAR(64) NOT NULL,
    consumed_at  TIMESTAMP NOT NULL,
    expires_at   TIMESTAMP NOT NULL,
    PRIMARY KEY (issuer, jti)
);
~~~

Trong transaction:

~~~sql
INSERT INTO consumed_jwt (issuer, jti, purpose, consumed_at, expires_at)
VALUES (:issuer, :jti, :purpose, CURRENT_TIMESTAMP, :expires_at);
~~~

Nếu insert thành công, request đã giành quyền tiêu thụ token. Nếu vi phạm unique constraint, token đã được tiêu thụ trước đó và request phải bị từ chối hoặc xử lý theo idempotency policy.

Một lựa chọn khác là atomic compare-and-set hoặc thao tác tạo key chỉ khi chưa tồn tại (ví dụ SET NX trong kho key-value có semantics phù hợp). Cần bảo đảm thao tác thực sự nguyên tử trên toàn bộ node/region liên quan.

### Khóa định danh nên có namespace

Không chỉ dùng jti làm khóa toàn cục nếu nhiều issuer hoặc nhiều loại token cùng chia sẻ kho tiêu thụ. Một khóa tra cứu an toàn thường bao gồm:

~~~text
replay_key = issuer + ":" + purpose + ":" + jti
~~~

Có thể thêm tenant hoặc recipient nếu profile yêu cầu. Dùng issuer đã xác minh và purpose đã được kiểm tra; không dùng giá trị từ token chưa xác minh để tạo quyết định tin cậy.

## 7. Gắn consume với hành động nghiệp vụ

Một vấn đề khó hơn là điều gì xảy ra nếu token đã được đánh dấu consumed nhưng hành động nghiệp vụ thất bại, hoặc hành động thành công nhưng server crash trước khi ghi consumed.

### Consume trước, hành động sau

Nếu server commit consumed trước rồi mới thực hiện hành động ở hệ thống khác, tiến trình có thể crash sau consume nhưng trước hành động. Người dùng không thể thử lại token, dù hành động chưa xảy ra.

### Hành động trước, consume sau

Nếu hành động hoàn tất trước rồi server mới ghi consumed, tiến trình có thể crash ở giữa. Request gửi lại có thể thực hiện hành động lần thứ hai.

### Transaction chung hoặc idempotent operation

Nếu trạng thái consume và hành động nghiệp vụ nằm trong cùng một database, hãy đặt chúng trong một transaction để cả hai commit hoặc rollback cùng nhau.

Nếu hành động gọi hệ thống bên ngoài:

- Ghi trạng thái consume và một outbox command trong cùng transaction.
- Worker xử lý outbox với một idempotency key ổn định.
- Downstream service phải lưu và trả lại kết quả cho cùng idempotency key thay vì thực hiện side effect lần nữa.
- Theo dõi trạng thái pending, completed và failed để phục hồi sau crash.

**Không nên hứa exactly-once chỉ vì token dùng một lần.** Hệ thống phân tán thường cần phối hợp atomic state, idempotency và recovery để đạt hiệu ứng nghiệp vụ tương đương một lần.

## 8. Hết hạn và dọn dữ liệu replay state

Record consumed cần được giữ đủ lâu để ngăn token hợp lệ bị phát lại. Thời gian lưu không được ngắn hơn khoảng thời gian token có thể còn được chấp nhận.

Thông thường:

- Lưu consumed record tới ít nhất exp cộng clock-skew leeway của verifier.
- Nếu có nhiều verifier với clock skew khác nhau, dùng giới hạn lớn nhất được policy cho phép.
- Nếu token có thể được chấp nhận sau exp do quy tắc grace riêng, record phải tồn tại hết khoảng grace đó.
- Chỉ xóa record sau khi token chắc chắn không còn được chấp nhận ở bất kỳ node/region nào.
- Dùng TTL làm cơ chế dọn dẹp, không dùng TTL thay cho kiểm tra consumed.

Nếu record bị xóa trước khi token hết hạn, token cũ có thể được dùng lại. Nếu kho replay state mất dữ liệu hoặc không nhất quán, one-time guarantee cũng có thể mất.

Đối với token có thời hạn dài hoặc yêu cầu chống replay dài hạn, có thể cần lưu audit/consumption record lâu hơn TTL thông thường theo yêu cầu nghiệp vụ và điều tra.

## 9. Access token được phép tái sử dụng

OAuth access token thường là bearer credential. Client có thể gửi cùng token trong nhiều request tới resource server được phép trong thời hạn token.

Ví dụ:

~~~http
GET /orders HTTP/1.1
Host: api.example
Authorization: Bearer <access-token>

GET /orders/123 HTTP/1.1
Host: api.example
Authorization: Bearer <same-access-token>

GET /profile HTTP/1.1
Host: api.example
Authorization: Bearer <same-access-token>
~~~

Các request trên có thể hợp lệ nếu:

- Token còn hiệu lực và chữ ký/introspection hợp lệ.
- Issuer và audience phù hợp với resource server.
- Scope/authorization đủ cho từng thao tác.
- Token chưa bị thu hồi hoặc vô hiệu hóa theo policy.
- Các ràng buộc sender-constrained, nếu có, được đáp ứng.

Resource server không nên thêm jti vào danh sách consumed sau request đầu tiên đối với access token thông thường. Làm vậy sẽ biến một credential được thiết kế để tái sử dụng thành token dùng một lần và khiến request tiếp theo bị từ chối.

### jti của access token vẫn hữu ích

jti có thể hỗ trợ:

- Tương quan log và điều tra sự cố.
- Nhận diện một token cụ thể.
- Denylist token khi cần thu hồi riêng.
- Phát hiện việc cùng token bị dùng bất thường từ nhiều vị trí.
- Ràng buộc với hệ thống quản lý phiên hoặc risk engine.

Nhưng jti không có nghĩa rằng resource server phải lưu trạng thái đã dùng cho mọi request. Chính sách replay phải dựa trên loại token và giao thức.

## 10. Bearer access token có thể bị replay như thế nào?

Reusable không có nghĩa là token an toàn trước replay. Bearer token có thể được sử dụng bởi bất kỳ bên nào sở hữu giá trị token. Nếu token bị đánh cắp, kẻ tấn công có thể gửi lại token tới đúng audience trong thời gian nó còn hiệu lực.

Nguồn rò rỉ có thể gồm:

- XSS hoặc malware đọc được token trong browser storage.
- Log, trace, analytics hoặc error report ghi nhầm Authorization header.
- URL/query string hoặc referrer làm lộ token.
- Client/device bị xâm nhập.
- Proxy, máy chủ hoặc kho lưu trữ không bảo vệ đúng cách.
- Token bị sao chép từ bộ nhớ hoặc backup.

Các biện pháp giảm tác động:

1. Access token có lifetime ngắn phù hợp với rủi ro.
2. Audience/resource hẹp và scope tối thiểu.
3. TLS cho mọi đường truyền.
4. Không log hoặc đưa token vào URL.
5. Có cơ chế revoke/introspection hoặc denylist khi cần.
6. Sender-constrained token bằng DPoP hoặc mTLS cho hệ thống cần giảm nguy cơ token bị dùng ở client khác.
7. Phát hiện bất thường và giới hạn tốc độ theo subject/client/resource.

Lifetime ngắn giảm cửa sổ replay nhưng không ngăn replay trong khoảng token còn hiệu lực. Audience và scope giới hạn nơi/hành động mà token có thể dùng, không chứng minh người gửi request hiện tại là client ban đầu.

## 11. DPoP và mTLS: giảm replay của bearer token bị đánh cắp

### DPoP

DPoP (Demonstrating Proof of Possession) ràng buộc access token với public key của client. Client gửi DPoP proof JWT cho từng request; proof có các thông tin như:

- htm: HTTP method.
- htu: HTTP URI đích theo quy tắc DPoP.
- iat: thời điểm tạo proof.
- jti: định danh duy nhất của proof.
- ath: hash của access token khi proof được dùng tại resource server.
- nonce khi server yêu cầu.

Resource server kiểm tra proof signature, key binding với access token, method/URI, thời gian và nonce theo profile. Để phát hiện replay proof, server cần lưu jti đã thấy trong một khoảng thời gian phù hợp và từ chối proof trùng lặp.

Access token vẫn có thể được tái sử dụng qua nhiều request, nhưng mỗi request cần proof mới phù hợp với request đó. Không được tái sử dụng cùng một DPoP proof cho nhiều request nếu policy yêu cầu jti duy nhất.

DPoP không tự ngăn XSS chạy trong browser gọi chức năng ký proof mà ứng dụng cung cấp. Nó giảm khả năng kẻ chỉ đánh cắp access token ở một môi trường khác có thể dùng token độc lập.

### Mutual TLS-bound access token

Với mTLS-bound access token, AS ràng buộc token với chứng thư client. Resource server kiểm tra chứng thư trong kết nối TLS có khớp thumbprint được ràng buộc trong token hay không.

Kẻ tấn công chỉ có chuỗi access token nhưng không có private key tương ứng thường không thể sử dụng token ở một kết nối TLS khác. Tuy nhiên:

- Private key và certificate phải được bảo vệ đúng cách.
- Nếu attacker kiểm soát client hoặc có quyền dùng key, sender constraint không loại bỏ mọi replay.
- Request vẫn có thể được gửi lặp lại từ client hợp lệ; mTLS không biến access token thành one-time token.

### So sánh

| Cơ chế | Token có thể dùng nhiều request? | Bằng chứng bổ sung | Replay cần phát hiện |
| --- | --- | --- | --- |
| Bearer access token | Có | Không ngoài token | Token bị đánh cắp có thể được phát lại |
| DPoP-bound access token | Có | Proof ký bằng private key của client cho từng request | Proof jti trùng, proof sai method/URI/thời gian/nonce |
| mTLS-bound access token | Có | Client certificate/private key trong TLS | Dùng token từ client không có key binding; request lặp từ client hợp lệ vẫn cần policy nghiệp vụ |
| One-time JWT | Không, sau một lần consume thành công | Server-side consumed state | jti/nonce đã tiêu thụ bị gửi lại |

## 12. Phân biệt one-time JWT với idempotency key

One-time token và idempotency key thường xuất hiện trong cùng một API nhưng giải quyết hai vấn đề khác nhau:

- One-time token kiểm soát credential/quyền được tiêu thụ tối đa một lần.
- Idempotency key giúp cùng một yêu cầu nghiệp vụ được gửi lại mà không tạo side effect trùng lặp; server có thể trả lại kết quả đã lưu.

Ví dụ, client gửi token phê duyệt giao dịch một lần cùng idempotency key. Server tiêu thụ token và xử lý giao dịch. Nếu response bị mất, client gửi lại cùng yêu cầu:

- Server nhận diện token đã consumed.
- Server tra cứu idempotency record.
- Nếu cùng request và cùng subject, server có thể trả lại kết quả đã hoàn tất mà không chạy giao dịch lần nữa.
- Nếu token được dùng với payload khác hoặc idempotency key khác, server từ chối.

Idempotency key không phải bằng chứng xác thực và không thay thế chữ ký JWT. Một kẻ tấn công không được phép tạo quyền chỉ bằng cách biết một idempotency key.

## 13. Refresh token và các assertion có quy tắc sử dụng riêng

Không nên gom mọi loại token vào một quy tắc chung:

- **Access token:** thường tái sử dụng trong lifetime và phạm vi được cấp.
- **Refresh token:** dùng để yêu cầu access token mới; với refresh token rotation, token cũ bị vô hiệu hóa sau khi đổi thành công và việc reuse có thể là dấu hiệu compromise.
- **JWT bearer assertion:** trong một số OAuth profile như RFC 7523, assertion có thể được yêu cầu chỉ chấp nhận một lần trong thời hạn ngắn; AS có thể dùng jti/replay cache để từ chối assertion đã thấy.
- **One-time action token:** token reset password hoặc transaction approval phải được consume theo state của ứng dụng.
- **DPoP proof:** proof được tạo cho từng request và có jti để phát hiện proof replay; access token gắn với proof vẫn có thể được tái sử dụng.

Refresh token rotation là chính sách sử dụng refresh credential, không có nghĩa access token phát hành từ refresh token chỉ dùng được một request.

## 14. Các lỗi triển khai thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Nghĩ chữ ký JWT tự làm token dùng một lần | Cùng token có thể được xác minh nhiều lần | Lưu trạng thái consume và kiểm tra nguyên tử |
| Nghĩ chỉ cần có jti là đã chống replay | jti chỉ là định danh nếu không có state check | Dùng jti làm khóa trong replay/consumption store |
| Đánh dấu access token consumed sau request đầu tiên | Các request hợp lệ tiếp theo bị từ chối | Phân biệt access token reusable với one-time credential |
| Dùng one-time token cho nhiều endpoint/purpose | Token có thể bị chuyển sang ngữ cảnh khác | Ràng buộc aud, purpose, subject và action |
| Consume jti trước khi xác minh chữ ký | Token giả có thể tiêu thụ jti của token thật | Xác minh token trước khi tin jti và consume |
| Kiểm tra unused rồi mới ghi consumed bằng hai thao tác rời | Hai request đồng thời cùng thành công | Unique constraint, atomic SET NX hoặc compare-and-set |
| Lưu consumed record quá ngắn | Token còn hạn có thể được replay sau khi record bị xóa | Giữ record ít nhất tới exp + leeway/grace |
| Không namespace jti theo issuer/purpose | Va chạm hoặc trộn trạng thái giữa các loại token | Dùng issuer + purpose + jti |
| Consume xong nhưng side effect thất bại không có recovery | Token bị mất dù hành động chưa hoàn tất | Transaction chung, outbox và idempotency |
| Side effect xong nhưng chưa ghi consumed | Retry có thể thực hiện hành động hai lần | Atomic transaction hoặc idempotent downstream |
| Coi idempotency key là credential | Người biết key có thể bị hiểu nhầm là có quyền | Xác thực token và subject độc lập |
| Dùng access token bearer dài hạn mà không có biện pháp replay | Token bị đánh cắp có thể dùng trong thời gian dài | Lifetime ngắn, scope/audience hẹp, revoke và sender constraint |
| Dùng lại DPoP proof cho nhiều request | Proof có thể bị replay | Tạo proof mới cho mỗi request và kiểm tra jti/nonce |
| Nghĩ mTLS biến access token thành one-time | Cùng client hợp lệ vẫn có thể gửi nhiều request | Giữ policy reusable và kiểm soát replay ở tầng request/nghiệp vụ |

## 15. Bộ ca kiểm thử

Giả sử hệ thống có endpoint reset password dùng one-time JWT và Orders API dùng reusable access token.

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| One-time JWT hợp lệ, đúng purpose/audience, chưa consumed | **Chấp nhận một lần** |
| Gửi lại cùng one-time JWT sau khi consume thành công | **Từ chối** |
| Hai request đồng thời gửi cùng one-time JWT | Chỉ một request consume thành công |
| One-time JWT có chữ ký sai nhưng jti trùng token thật | **Từ chối**, không consume jti thật |
| One-time JWT đúng chữ ký nhưng sai purpose | **Từ chối** |
| One-time JWT đúng purpose nhưng sai audience | **Từ chối** |
| One-time JWT hết hạn | **Từ chối** |
| One-time JWT bị dùng với transaction amount/recipient khác nội dung đã xác nhận | **Từ chối** |
| Consumed record hết TTL trước exp | Test phải phát hiện token có thể replay; cấu hình lưu trữ phải được sửa |
| Side effect thất bại trong transaction chung | Consume và side effect cùng rollback hoặc phục hồi theo policy |
| Response mất sau khi side effect hoàn tất, client retry cùng idempotency key | Trả kết quả đã lưu; không thực hiện side effect lần hai |
| Cùng idempotency key nhưng payload khác | **Từ chối xung đột** |
| Reusable access token hợp lệ gửi tới nhiều request đúng audience/scope | **Chấp nhận** từng request |
| Reusable access token hết hạn hoặc bị revoke | **Từ chối** |
| Access token đúng chữ ký nhưng sai audience | **Từ chối** |
| Access token bị đánh cắp và phát lại như bearer token | Có thể bị chấp nhận nếu còn hiệu lực; kiểm tra biện pháp giảm replay theo threat model |
| DPoP access token được dùng với proof mới hợp lệ cho từng request | **Chấp nhận** |
| Cùng DPoP proof jti được phát lại | **Từ chối proof replay** |
| DPoP proof sai htm/htu hoặc ath | **Từ chối** |
| mTLS-bound token được gửi từ client không có certificate/key tương ứng | **Từ chối** |
| Refresh token cũ bị dùng lại sau rotation | Áp dụng reuse detection và revoke family theo policy |

Kiểm thử concurrency cần chạy đồng thời trên nhiều worker/node dùng chung replay store. Một bài test tuần tự không chứng minh được atomic consume. Với thao tác tài chính hoặc thay đổi dữ liệu quan trọng, cần kiểm thử cả crash/retry ở các ranh giới transaction.

## 16. Ghi nhớ

- JWT không tự quy định token dùng một lần hay tái sử dụng; ngữ nghĩa đến từ token profile và giao thức.
- One-time JWT cần jti/nonce cùng trạng thái consumed ở phía server; chữ ký và exp không tự ngăn lần gửi lại.
- Xác minh chữ ký, issuer, audience, purpose và thời hạn trước khi consume.
- Consume phải nguyên tử để chỉ một request đồng thời thành công; unique constraint hoặc compare-and-set là các cách triển khai phổ biến.
- Gắn consume với hành động nghiệp vụ bằng transaction chung, outbox hoặc idempotency để xử lý crash/retry.
- Giữ consumed record ít nhất tới khi token không còn được chấp nhận.
- Access token thông thường được phép tái sử dụng cho nhiều request trong lifetime và audience/scope được cấp; không đánh dấu jti của nó consumed sau request đầu.
- Bearer access token vẫn có thể bị replay nếu bị đánh cắp; lifetime ngắn, audience hẹp, scope tối thiểu, revoke, DPoP và mTLS giúp giảm rủi ro.
- DPoP proof cần được tạo cho từng request và replay detection áp dụng cho proof; điều đó không biến access token thành one-time token.
- Refresh token rotation, JWT assertion replay prevention, one-time action token và idempotency key có ngữ nghĩa riêng, không được đánh đồng.

### Tài liệu chuẩn tham khảo

- [RFC 7519 — JSON Web Token (JWT), mục 4.1.7](https://www.rfc-editor.org/rfc/rfc7519): claim jti và khả năng dùng để ngăn replay.
- [RFC 7523 — JSON Web Token (JWT) Profile for OAuth 2.0 Client Authentication and Authorization Grants](https://www.rfc-editor.org/rfc/rfc7523): JWT bearer assertion và kiểm soát replay.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): đặc tính bearer access token và rủi ro sử dụng token bị lộ.
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705): ràng buộc access token với chứng thư client.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): proof-of-possession, jti, nonce và phát hiện replay.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): bảo vệ access/refresh token và refresh token rotation.

# Yêu cầu làm mới đồng thời và phát hiện refresh token bị tái sử dụng

## 1. Vì sao refresh token cần được kiểm thử đồng thời?

Refresh token được dùng để xin access token mới khi access token hiện tại hết hạn hoặc cần làm mới. Vì refresh token thường có thời hạn dài và cho phép tiếp tục phiên đăng nhập, nó là credential có giá trị cao. Nếu bị đánh cắp, attacker có thể dùng nó để duy trì quyền truy cập sau khi access token cũ hết hạn.

Một thiết kế phổ biến là **refresh token rotation**: mỗi lần refresh thành công, Authorization Server vô hiệu hóa refresh token cũ và phát hành refresh token mới. Nếu refresh token cũ đã được sử dụng lại, server có thể coi đó là dấu hiệu credential bị sao chép và thu hồi token family liên quan.

Thiết kế này tạo ra một bài toán đồng thời:

- Hai request refresh có thể được gửi gần như cùng lúc bằng cùng một refresh token.
- Nhiều tab hoặc nhiều request API có thể cùng phát hiện access token hết hạn.
- Client có thể timeout sau khi server đã xoay token thành công nhưng trước khi nhận response.
- Một request retry có thể bị nhầm với hành vi replay.
- Nhiều instance hoặc region có thể xử lý cùng refresh token.
- Việc phát hiện reuse có thể thu hồi cả refresh token mới vừa cấp cho phiên hợp lệ.

Vì vậy, kiểm thử chỉ với một request refresh tuần tự là chưa đủ. Cần kiểm tra cả race condition, retry sau mất response, tính nguyên tử của cập nhật trạng thái và phạm vi thu hồi token family.

**Mục tiêu:** bảo đảm một refresh token chỉ được tiêu thụ theo đúng semantics đã định nghĩa; việc cấp token kế tiếp và đánh dấu token cũ phải nhất quán; reuse được phát hiện; request đồng thời hợp lệ không tạo ra trạng thái không thể dự đoán.

## 2. Refresh token rotation và reuse detection hoạt động thế nào?

Trong rotation, mỗi refresh token chỉ được dùng một lần để lấy token kế tiếp. Server lưu quan hệ giữa các token trong cùng một phiên hoặc một **token family**.

Luồng thành công cơ bản:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant AS as Authorization Server
    C->>AS: Refresh token R1
    AS->>AS: Kiểm tra R1 đang active
    AS->>AS: Đánh dấu R1 consumed
    AS->>AS: Tạo R2 và liên kết cùng family
    AS-->>C: Access token mới + refresh token R2
    C->>AS: Refresh token R2 ở lần tiếp theo
    AS->>AS: Xác minh R2 và xoay thành R3
    AS-->>C: Access token mới + refresh token R3
~~~

Trạng thái có thể hình dung:

~~~text
Family F:
  R1: CONSUMED -> R2: CONSUMED -> R3: ACTIVE
~~~

Khi R1 đã được tiêu thụ mà lại xuất hiện trong một request mới, server phát hiện reuse:

~~~mermaid
flowchart TD
    A["Nhận refresh token R1"] --> B["Tìm token và family"]
    B --> C{"R1 còn active?"}
    C -->|"Có"| D["Consume R1 và phát hành R2"]
    C -->|"Không, đã consumed/revoked"| E["Đánh dấu reuse"]
    E --> F["Thu hồi refresh token còn active trong family"]
    F --> G["Yêu cầu xác thực lại theo policy"]
~~~

RFC 9700 khuyến nghị Authorization Server sử dụng sender-constrained refresh token hoặc rotation đối với public client để phát hiện replay. Khi rotation phát hiện refresh token cũ bị dùng lại, server không thể biết chắc request nào là attacker và request nào là client hợp lệ; cả hai bên có thể đang giữ bản sao của cùng credential. Do đó, chính sách thường thu hồi refresh token còn hiệu lực trong family và yêu cầu người dùng xác thực lại.

### Reuse detection không chỉ là kiểm tra chữ ký

Refresh token có thể là chuỗi opaque ngẫu nhiên hoặc JWT. Dù là JWT có chữ ký hợp lệ, chữ ký chỉ xác minh nguồn phát hành và tính toàn vẹn; nó không chứng minh token chưa từng được sử dụng. Rotation cần trạng thái phía server để ghi nhận token đã được tiêu thụ.

## 3. Mô hình trạng thái token family

Một mô hình lưu trữ có thể quản lý token theo family và generation:

| Trường | Ý nghĩa |
| --- | --- |
| `family_id` | Định danh phiên/token family |
| `token_id` | Định danh bản ghi refresh token |
| `token_hash` | Hash/HMAC của refresh token để tra cứu |
| `parent_token_id` | Token trước đó trong chuỗi rotation |
| `replaced_by_token_id` | Token được cấp thay thế |
| `generation` | Số thứ tự trong family |
| `status` | ACTIVE, CONSUMED, REVOKED hoặc EXPIRED |
| `issued_at` | Thời điểm phát hành |
| `consumed_at` | Thời điểm tiêu thụ |
| `expires_at` | Thời điểm hết hạn |
| `client_id` | Client được gắn với token |
| `subject_id` | Chủ thể phiên đăng nhập |
| `sender_key_thumbprint` | Key binding nếu dùng sender-constrained token |

Ví dụ:

~~~text
family_id = F-42

token_id = R1
generation = 1
status = CONSUMED
replaced_by_token_id = R2

token_id = R2
generation = 2
status = CONSUMED
replaced_by_token_id = R3

token_id = R3
generation = 3
status = ACTIVE
~~~

Không nhất thiết phải lưu raw refresh token. Với token ngẫu nhiên có entropy cao, server có thể lưu hash một chiều để tra cứu; HMAC với khóa riêng có thể bổ sung lớp bảo vệ khi database bị lộ. Nếu cần lưu response đã cấp để hỗ trợ retry idempotent, phải mã hóa và giới hạn thời gian lưu vì response chứa refresh token mới.

### Các trạng thái cần phân biệt

- **ACTIVE:** có thể được dùng để refresh nếu mọi điều kiện khác hợp lệ.
- **CONSUMED:** đã dùng để phát hành token kế tiếp.
- **REVOKED:** bị thu hồi do logout, reuse hoặc policy.
- **EXPIRED:** đã hết thời hạn.

Không chuyển một token CONSUMED trở lại ACTIVE chỉ vì client retry. Cần một cơ chế idempotency riêng nếu muốn hỗ trợ gửi lại cùng một thao tác.

## 4. Race condition khi hai request dùng cùng refresh token

Giả sử client gửi hai request đồng thời bằng R1:

~~~mermaid
sequenceDiagram
    participant C1 as Request A
    participant C2 as Request B
    participant AS as Authorization Server
    C1->>AS: Refresh R1
    C2->>AS: Refresh R1
    AS->>AS: Request A đọc R1 = ACTIVE
    AS->>AS: Request B đọc R1 = ACTIVE
    AS->>AS: A đánh dấu R1 CONSUMED
    AS->>AS: B cũng cố đánh dấu R1 CONSUMED
    Note over AS: Nếu không có cập nhật nguyên tử, cả A và B có thể cấp token mới
~~~

Nếu server chỉ thực hiện chuỗi thao tác “đọc trạng thái → kiểm tra ACTIVE → cập nhật CONSUMED” mà không có transaction hoặc compare-and-swap, cả hai request có thể cùng đọc trạng thái ACTIVE trước khi một request cập nhật. Kết quả có thể là hai refresh token con cùng được phát hành từ R1.

Điều này phá vỡ giả định một token chỉ có một successor và khiến reuse detection không còn đáng tin cậy.

### Điều kiện cần bảo đảm

1. Chỉ một request có thể chuyển token từ ACTIVE sang CONSUMED.
2. Chỉ request thắng thao tác consume mới được tạo successor.
3. Việc consume token cũ và tạo token mới phải nằm trong cùng transaction hoặc một cơ chế nhất quán tương đương.
4. Request thua phải nhận kết quả đã được định nghĩa: reuse, duplicate/idempotent retry hoặc conflict.
5. Nhiều instance và region phải tuân theo cùng một quy tắc nguyên tử.

## 5. Consume-and-issue phải nguyên tử

Một cách triển khai là transaction với row lock hoặc conditional update. Ví dụ logic:

~~~sql
BEGIN;

UPDATE refresh_tokens
SET status = 'CONSUMED',
    consumed_at = CURRENT_TIMESTAMP
WHERE token_id = :token_id
  AND status = 'ACTIVE'
  AND expires_at > CURRENT_TIMESTAMP;

-- Chỉ tiếp tục nếu đúng một row được cập nhật.
-- Tạo successor và liên kết với token cha trong cùng transaction.

INSERT INTO refresh_tokens (
    token_id,
    family_id,
    parent_token_id,
    generation,
    token_hash,
    status,
    issued_at,
    expires_at
) VALUES (
    :new_token_id,
    :family_id,
    :old_token_id,
    :next_generation,
    :new_token_hash,
    'ACTIVE',
    CURRENT_TIMESTAMP,
    :new_expires_at
);

UPDATE refresh_tokens
SET replaced_by_token_id = :new_token_id
WHERE token_id = :old_token_id;

COMMIT;
~~~

Đây là pseudocode SQL minh họa. Hệ thống thực tế phải kiểm tra số row được cập nhật và rollback nếu không đúng một row. Cần có unique constraint hoặc điều kiện tương đương bảo đảm mỗi token cha chỉ có tối đa một successor.

Nếu conditional update trả về 0 row, server phải đọc trạng thái mới nhất trong transaction phù hợp để phân biệt token đã consumed, revoked, expired hoặc không tồn tại. Không được tự động phát hành successor thứ hai.

### Vì sao transaction cần bao gồm cả successor?

Nếu server đánh dấu R1 CONSUMED rồi commit, nhưng tạo R2 thất bại ở transaction khác, client đã mất token cũ mà không có token mới. Ngược lại, nếu tạo R2 trước nhưng consume R1 thất bại, có thể tồn tại token con không có quyền sử dụng hợp lệ.

Consume R1, tạo R2, liên kết parent/child và cập nhật family phải được commit như một đơn vị logic. Nếu bất kỳ bước bắt buộc nào thất bại, rollback toàn bộ.

## 6. Kết quả của hai request đồng thời theo từng chính sách

Có nhiều chính sách xử lý request thứ hai. Hệ thống cần chọn một semantics rõ ràng và kiểm thử đúng semantics đó.

| Chính sách | Request đầu tiên | Request thứ hai | Đánh đổi |
| --- | --- | --- | --- |
| Strict rotation/reuse detection | Consume R1, phát hành R2 | R1 đã consumed nên phát hiện reuse và thu hồi family | Bảo vệ mạnh; request hợp lệ đồng thời có thể khiến phiên bị thu hồi |
| Idempotent retry | Consume R1, phát hành R2 và lưu kết quả thao tác | Cùng operation ID được nhận diện là retry và trả lại kết quả đã lưu | Cần lưu response an toàn và ràng buộc retry |
| Serialize phía client | Client chỉ gửi một refresh tại một thời điểm | Request khác chờ kết quả refresh đầu tiên | Giảm race; server vẫn phải bảo vệ nguyên tử |
| Bounded reuse grace | Phát hành R2 | Có thể chấp nhận R1 trong một cửa sổ ngắn theo policy | Giảm logout do race nhưng làm yếu tín hiệu phát hiện replay |

### Strict rotation

Đây là semantics dễ kiểm tra: chỉ một request thắng. Nếu request thứ hai dùng R1 sau khi R1 đã consumed, server coi là reuse. Nếu phát hiện reuse, family có thể bị revoke, bao gồm R2 vừa cấp. Request A có thể đã nhận response thành công nhưng token mới của nó không còn dùng được.

Hành vi này có thể gây logout cho người dùng hợp lệ khi ứng dụng gửi refresh đồng thời. Vì vậy cần tránh refresh song song ở client và cần kiểm thử race ở server.

### Bounded grace window

Một số hệ thống chọn khoảng grace ngắn để xử lý request lặp do mạng hoặc concurrency. Đây là một quyết định trade-off, không phải bảo đảm chống replay mặc định. Nếu server chấp nhận R1 nhiều lần trong grace window mà không ràng buộc request, attacker có thể tận dụng chính cửa sổ đó.

Nếu sử dụng grace window, cần giới hạn thời gian, ràng buộc client/operation, chỉ trả lại kết quả đã cấp khi có bằng chứng retry phù hợp và theo dõi việc dùng lại. Không được âm thầm phát hành nhiều successor độc lập từ cùng token cũ.

## 7. Client cần phối hợp refresh để tránh gửi song song

Server phải luôn bảo đảm tính nguyên tử vì không thể tin rằng mọi client đều gửi tuần tự. Tuy nhiên, client có thể giảm phần lớn race condition.

### Single-flight refresh

Khi nhiều request API cùng phát hiện access token hết hạn, client nên tạo một thao tác refresh duy nhất. Các request khác chờ cùng một kết quả thay vì tự gọi token endpoint bằng cùng refresh token.

~~~text
if refreshInProgress:
    await existingRefreshOperation
else:
    start one refresh operation
    publish its result to waiting requests
~~~

Sau khi refresh thành công, client thay access token và refresh token hiện tại bằng cặp mới một cách nhất quán rồi mới giải phóng các request đang chờ.

### Nhiều tab hoặc cửa sổ

Single-flight trong một tab chưa đủ nếu nhiều tab cùng chia sẻ một session và refresh token. Có thể dùng cơ chế phối hợp cross-tab phù hợp với nền tảng, ví dụ lock dùng chung, shared worker hoặc broadcast trạng thái refresh. Các tab cần biết token hiện tại đã được thay thế và không tiếp tục gửi bản cũ.

Nếu mỗi thiết bị có refresh token family riêng, không nên vô tình chia sẻ cùng một refresh token giữa các thiết bị. Tách family theo phiên/thiết bị giúp giới hạn phạm vi thu hồi và điều tra.

### Client không được là lớp bảo vệ duy nhất

Client có thể bị lỗi, bị sửa đổi hoặc bị attacker điều khiển. Server vẫn phải thực hiện atomic consume, reuse detection, binding và family revocation theo policy. Client coordination chỉ giảm lỗi đồng thời ngoài ý muốn.

## 8. Timeout sau khi server đã xoay token

Một tình huống khó là server đã commit R1 → R2 nhưng response bị mất trên đường về client:

1. Client gửi R1.
2. Server consume R1 và tạo R2.
3. Transaction commit thành công.
4. Response chứa R2 bị mất hoặc client timeout.
5. Client chỉ còn biết R1 và thử lại.

Nếu retry bằng R1 như một request mới, server sẽ thấy token đã consumed và có thể revoke family. Client hợp lệ có thể bị đăng xuất dù lần refresh đầu đã thành công.

Đây là **ambiguous outcome**: client không biết server đã commit hay chưa.

### Cách xử lý bằng idempotency key

Client có thể tạo operation ID ngẫu nhiên cho một lần refresh logic và giữ nguyên ID đó khi retry cùng thao tác. Server lưu kết quả theo khóa kết hợp như:

~~~text
idempotencyKey = hash(
    familyId
    + clientBinding
    + operationId
    + oldRefreshTokenId
)
~~~

Khi request đầu tiên thành công, server lưu trạng thái operation và response được bảo vệ. Nếu cùng operation ID, cùng token cũ và cùng client binding gửi lại trong thời hạn cho phép, server có thể trả lại chính kết quả đã lưu thay vì thực hiện rotation lần nữa.

Điều kiện quan trọng:

- Cùng operation ID không được dùng với token khác hoặc payload khác.
- Operation record phải được ghi nguyên tử cùng transaction rotation.
- Response chứa refresh token mới cần được mã hóa khi lưu và xóa sau thời hạn ngắn.
- Operation ID phải khó đoán và được ràng buộc với client/session.
- Idempotency key không tự nó chứng minh người gửi là client hợp lệ; sender constraint hoặc client authentication vẫn cần thiết khi threat model yêu cầu.
- Request dùng R1 với operation ID mới không phải retry idempotent; nó phải đi qua reuse policy.

Nếu không hỗ trợ idempotent retry, một lần timeout sau commit có thể buộc người dùng xác thực lại. Đây là lựa chọn đơn giản hơn nhưng cần được thể hiện rõ trong UX và vận hành.

## 9. Phát hiện reuse và thu hồi token family

Khi server nhận refresh token đã CONSUMED, REVOKED hoặc đã bị thay thế, đây có thể là dấu hiệu replay. Với rotation nghiêm ngặt, server cần:

1. Xác định token thuộc family nào.
2. Ghi nhận sự kiện reuse với thời gian và context an toàn.
3. Thu hồi refresh token ACTIVE hiện tại trong family.
4. Ngăn mọi token tiếp theo của family được sử dụng để refresh.
5. Trả lỗi phù hợp, thường là `invalid_grant` ở OAuth token endpoint.
6. Ghi audit event mà không lưu raw refresh token.
7. Yêu cầu client thực hiện lại authorization flow hoặc đăng nhập theo policy.

~~~text
if presentedToken.status == CONSUMED:
    mark family as REVOKED
    revoke all ACTIVE refresh tokens in family
    emit RefreshTokenReuseDetected
    return invalid_grant
~~~

Thao tác revoke family cũng phải nguyên tử hoặc có trạng thái family-level được kiểm tra trên mọi refresh request. Nếu chỉ revoke token hiện tại mà bỏ sót successor do race, attacker có thể tiếp tục dùng successor.

### Phạm vi thu hồi cần được xác định

Reuse detection thường thu hồi refresh token family liên quan, không nhất thiết tự động vô hiệu hóa mọi access token đã cấp trước đó. Access token tự chứa có thể vẫn được Resource Server chấp nhận đến `exp`, trừ khi hệ thống có introspection, denylist, session check hoặc cơ chế thu hồi access token bổ sung.

Không nên tuyên bố “revoke family” đồng nghĩa mọi access token lập tức mất hiệu lực nếu kiến trúc không thực sự kiểm tra trạng thái đó.

## 10. Token family nên được tách theo phiên hoặc thiết bị

Một người dùng có thể đăng nhập trên nhiều thiết bị. Nếu tất cả refresh token dùng chung một family, reuse trên một thiết bị có thể làm thu hồi phiên trên mọi thiết bị.

Thông thường nên cân nhắc family riêng cho mỗi phiên đăng nhập hoặc mỗi client instance:

~~~text
User U
  ├── Device A -> Family FA -> R1 -> R2 -> R3
  ├── Device B -> Family FB -> R1 -> R2
  └── Device C -> Family FC -> R1
~~~

Khi Family FA bị revoke do reuse, Family FB và FC vẫn có thể tiếp tục hoạt động nếu policy không yêu cầu thu hồi toàn tài khoản. Nếu phát hiện compromise tài khoản diện rộng, hệ thống có thể có thao tác revoke all sessions riêng.

Cần kiểm thử đúng phạm vi:

- Logout một thiết bị chỉ revoke family tương ứng.
- Reuse một family không vô tình revoke family khác.
- Disable account hoặc security incident có thể revoke tất cả family theo policy.
- Refresh token không thể chuyển sang client hoặc device binding khác.

## 11. Sender-constrained refresh token

Rotation phát hiện reuse bằng trạng thái sử dụng, nhưng nếu attacker đánh cắp refresh token trước lần sử dụng đầu tiên, attacker có thể là bên đầu tiên dùng token. Server có thể cấp successor cho attacker và sau đó phát hiện client thật dùng lại token cũ.

Một cách giảm nguy cơ là ràng buộc refresh token với client hoặc khóa của client:

- **mTLS:** token được ràng buộc với chứng thư client; request refresh phải chứng minh sở hữu private key tương ứng.
- **DPoP:** client gửi proof ký bằng private key đã được liên kết với token theo profile.
- **Client authentication:** với confidential client, xác thực client theo cấu hình OAuth phù hợp.

Sender constraint làm giảm khả năng dùng token bị đánh cắp riêng lẻ. Nó không thay thế rotation hoặc kiểm tra trạng thái token. Nếu attacker lấy được cả token lẫn private key hoặc kiểm soát endpoint hợp lệ, rủi ro vẫn tồn tại.

## 12. Refresh token dạng JWT có tự giải quyết concurrency không?

Không. JWT refresh token có thể mang `jti`, `iat`, `exp`, `sub` và các claim khác, nhưng chữ ký không tạo ra semantics một lần. Hai request cùng gửi một JWT vẫn có thể xác minh chữ ký thành công nếu server không tra cứu trạng thái.

Nếu dùng JWT làm refresh token, server vẫn cần trạng thái phía server để:

- Xác định token thuộc family nào.
- Biết token đang ACTIVE, CONSUMED hay REVOKED.
- Thực hiện atomic consume.
- Liên kết token cũ với successor.
- Phát hiện reuse và revoke family.
- Kiểm tra client/sender binding.
- Hỗ trợ logout và thu hồi.

Opaque random refresh token thường đơn giản hơn cho rotation vì client không cần đọc claims và server có thể tra cứu bằng hash. Nếu chọn JWT, đừng coi nó là stateless refresh credential khi yêu cầu rotation và reuse detection cần trạng thái.

## 13. Kiểm thử đồng thời: test matrix

Kiểm thử cần điều khiển được thời điểm request để hai luồng thực sự đua nhau, thay vì chỉ gửi hai request gần nhau rồi hy vọng tạo ra race.

| Kịch bản | Thiết lập | Kết quả cần xác nhận |
| --- | --- | --- |
| Refresh tuần tự bình thường | Dùng R1 một lần, sau đó R2 | R1 consumed, R2 active, lần sau cấp R3 |
| Reuse tuần tự | Dùng R1 thành công rồi gửi lại R1 | Phát hiện reuse và áp dụng family revocation |
| Hai request đồng thời, cùng R1 | Đồng bộ barrier để cả hai cùng bắt đầu | Chỉ một rotation được commit; request còn lại theo strict/idempotent policy |
| Hai instance cùng xử lý R1 | Gửi request đến hai node khác nhau | Không thể tạo hai successor active |
| Hai region cùng xử lý R1 | Gửi request qua hai vùng | Global/partition strategy vẫn bảo đảm một kết quả duy nhất |
| Client retry cùng operation ID | Làm mất response đầu, retry đúng ID | Trả cùng kết quả đã lưu, không rotate lần hai |
| Retry với operation ID mới | R1 đã consumed, gửi lại với ID mới | Được phân loại là reuse theo policy |
| Cùng idempotency key nhưng payload khác | Thay đổi client binding hoặc request data | Từ chối conflict, không trả response cũ |
| Lỗi trước transaction commit | Gây lỗi khi tạo successor | Rollback; R1 không bị mất trạng thái hợp lệ |
| Lỗi sau commit trước response | Drop response sau commit | Retry được xử lý đúng theo idempotency policy |
| Reuse sau khi family revoke | Dùng successor đã bị revoke | Từ chối, không cấp token mới |
| Reuse trên family khác | Dùng token cũ của thiết bị A, kiểm tra family B | Family B vẫn hoạt động nếu policy tách phiên |
| Client binding sai | Dùng refresh token từ client/device khác | Từ chối và ghi nhận sự kiện an toàn |
| Sender proof sai | Dùng token với DPoP key/certificate khác | Từ chối proof/token binding |
| Token hết hạn hoặc đã logout | Refresh token không còn active | Từ chối, không tạo successor |
| Replay store/database không khả dụng | Làm dependency lỗi khi refresh | Không chấp nhận refresh khi chưa thể kiểm tra/ghi trạng thái nguyên tử |

### Kiểm tra invariant sau mỗi test

Sau khi test hoàn tất, kiểm tra các invariant:

- Mỗi token cha có tối đa một successor.
- Một family chỉ có tối đa một refresh token ACTIVE theo mô hình rotation tuyến tính.
- Token CONSUMED không quay lại ACTIVE.
- Token REVOKED không thể cấp successor.
- Khi family REVOKED, không token ACTIVE nào trong family còn được refresh.
- Operation ID chỉ gắn với một request fingerprint và một kết quả.
- Một request timeout không tạo ra hai token successor.
- Reuse ở một family không ảnh hưởng family khác nếu policy yêu cầu cô lập.
- Audit không chứa raw refresh token hoặc response credential.

## 14. Kiểm thử race condition một cách xác định

Một bài test đồng thời tốt cần tạo ra lịch thực thi có kiểm soát:

1. Tạo family và refresh token R1.
2. Chuẩn bị hai client request độc lập dùng R1.
3. Đặt barrier ngay trước thao tác consume để cả hai request cùng đến điểm tranh chấp.
4. Cho phép cả hai tiếp tục.
5. Thu thập kết quả HTTP và trạng thái database.
6. Kiểm tra chỉ một transaction tạo successor.
7. Kiểm tra request thứ hai được xử lý đúng theo policy.
8. Nếu reuse làm revoke family, xác nhận successor đã phát hành cũng không còn refresh được.
9. Lặp test nhiều lần với nhiều instance và tải đồng thời.

Không nên chỉ assert rằng “một request 200, một request 400”. Cần kiểm tra trạng thái lưu trữ và family vì lỗi có thể khiến cả hai response trông hợp lệ nhưng database đã có hai successor.

### Kiểm tra lỗi mất response

Để mô phỏng timeout sau commit, test harness cần chặn hoặc drop response sau khi transaction thành công. Sau đó client gửi lại request theo cách thực tế của nó:

- Cùng operation ID nếu có idempotency.
- Operation ID mới nếu client không giữ được ID.
- Không có idempotency key nếu protocol hiện tại không hỗ trợ.

Kết quả cần khớp với semantics đã công bố. Không được để client vô tình tạo nhiều successor hoặc server âm thầm chấp nhận replay không giới hạn.

## 15. Observability và audit cho refresh reuse

Khi phát hiện reuse, cần có thông tin để điều tra nhưng không được ghi raw refresh token.

Các trường audit hữu ích:

- Event type: `REFRESH_TOKEN_ROTATED`, `REFRESH_TOKEN_REUSE_DETECTED`, `TOKEN_FAMILY_REVOKED`.
- Family ID và token record ID nội bộ.
- Subject/client alias theo chính sách dữ liệu.
- Device/session identifier đã được pseudonymized nếu phù hợp.
- Region/instance xử lý request.
- Generation và trạng thái trước/sau.
- Thời điểm request và thời điểm token được consume.
- Kết quả idempotency/retry classification.
- Correlation/request ID.

Không ghi raw refresh token, access token, Authorization header hoặc response chứa credential. Nếu cần tương quan token, dùng fingerprint HMAC với khóa logging riêng và bảo vệ fingerprint như dữ liệu có thể liên kết.

Theo dõi metrics:

- Số lần refresh thành công.
- Số request refresh đồng thời và conflict.
- Số reuse detection theo client/region.
- Số family bị revoke do reuse.
- Tỷ lệ refresh retry sau timeout.
- Tỷ lệ response timeout sau transaction commit.
- Số lỗi database/lock/transaction.
- Số family có nhiều hơn một token ACTIVE — invariant violation cần cảnh báo nghiêm trọng.

Không dùng subject, family ID hoặc token ID làm metric label có cardinality không kiểm soát. Dùng aggregation hoặc dimension đã giới hạn.

## 16. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Đọc trạng thái rồi cập nhật riêng rẽ | Hai request có thể cùng consume token | Conditional update/transaction nguyên tử |
| Consume token cũ và tạo successor ở hai transaction | Có thể mất token hoặc tạo token mồ côi | Commit cả chuỗi rotation trong một transaction |
| Không có unique successor constraint | Một token cha có thể tạo nhiều token con | Ràng buộc dữ liệu và invariant |
| Chỉ test refresh tuần tự | Bỏ sót race giữa tab, instance hoặc region | Test barrier đồng thời và multi-node |
| Retry token cũ sau timeout như request mới | Bị hiểu là reuse và có thể revoke family | Dùng idempotency operation ID hoặc yêu cầu xác thực lại |
| Chấp nhận token cũ trong grace window không giới hạn | Attacker có thêm thời gian replay | Giới hạn cửa sổ và ràng buộc client/operation |
| Chỉ revoke token cũ, không revoke family | Successor của attacker vẫn hoạt động | Revoke toàn family theo policy |
| Revoke family nhưng không đồng bộ giữa region | Vùng khác vẫn chấp nhận successor | Dùng family state nhất quán và propagation policy rõ |
| Cho rằng JWT signature ngăn reuse | Cùng JWT vẫn verify nhiều lần | Lưu trạng thái rotation ở server |
| Chia sẻ một family cho mọi thiết bị | Một thiết bị gây logout tất cả thiết bị | Cân nhắc family riêng cho từng session/device |
| Không phối hợp nhiều tab | Refresh hợp lệ có thể tự kích hoạt reuse detection | Single-flight và cross-tab coordination |
| Log raw refresh token để điều tra | Credential bị lộ qua log | Log ID/fingerprint an toàn, không log token |
| Coi revoke family sẽ vô hiệu hóa access token ngay | Access token tự chứa có thể còn hiệu lực đến exp | Dùng introspection/denylist/session check nếu cần thu hồi access token nhanh |

## 17. Checklist triển khai và kiểm thử

**Rotation và trạng thái**

- Mỗi refresh token có định danh và trạng thái rõ ràng.
- Mỗi lần rotation chỉ có một successor.
- Consume token cũ và phát hành token mới được commit nguyên tử.
- Token family được quản lý theo session/device phù hợp.
- Token CONSUMED/REVOKED không thể được dùng để phát hành successor mới.
- Reuse detection thu hồi toàn family theo policy.
- Raw refresh token không được lưu nếu chỉ cần hash/HMAC để tra cứu.

**Concurrency và retry**

- Client dùng single-flight để tránh refresh đồng thời trong cùng session.
- Có phối hợp giữa tab/window nếu chúng chia sẻ session.
- Server vẫn bảo vệ bằng transaction/conditional update.
- Xác định semantics cho request thứ hai: reuse, idempotent retry hoặc grace policy.
- Nếu hỗ trợ idempotency, operation ID gắn với token cũ, client binding và request fingerprint.
- Lưu response retry một cách mã hóa, giới hạn retention và quyền truy cập.
- Kiểm thử timeout trước commit và sau commit.
- Kiểm thử nhiều instance/region cùng xử lý một token.

**Reuse, thu hồi và ràng buộc client**

- Reuse được phát hiện và audit mà không ghi raw token.
- Family revocation được áp dụng nhất quán ở mọi region.
- Phân biệt refresh token revocation với access token revocation.
- Dùng sender-constrained refresh token khi threat model yêu cầu.
- Kiểm tra client/device binding và DPoP/mTLS proof nếu được sử dụng.
- Có luồng xác thực lại rõ ràng khi family bị revoke.

**Kiểm thử và vận hành**

- Test matrix bao gồm sequential reuse, simultaneous refresh, retry, lost response, rollback và region race.
- Kiểm tra invariant database, không chỉ status code.
- Theo dõi refresh success, reuse rate, family revocation và transaction conflicts.
- Có cảnh báo khi family xuất hiện nhiều token ACTIVE.
- Không log refresh token, access token hoặc response credential.
- Tài liệu hóa hành vi client khi nhận `invalid_grant` và tránh refresh loop.

**Ghi nhớ:** Rotation chỉ đáng tin khi server atomically consume refresh token cũ và phát hành đúng một successor. Hai request đồng thời bằng cùng token có thể tạo race; timeout sau commit có thể khiến client retry và bị nhận diện nhầm là replay. Hãy phối hợp single-flight ở client, bảo đảm transaction ở server và định nghĩa rõ idempotent retry hoặc strict reuse policy. Khi phát hiện reuse, revoke token family theo policy, đồng thời nhớ rằng access token tự chứa có thể còn hiệu lực đến khi hết hạn nếu không có cơ chế thu hồi riêng.

### Tài liệu chuẩn để tra cứu

- **RFC 6749 — The OAuth 2.0 Authorization Framework:** refresh token grant, token endpoint và lỗi `invalid_grant`.
- **RFC 7009 — OAuth 2.0 Token Revocation:** thu hồi token.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** bảo vệ refresh token cho public clients, rotation và phát hiện replay.
- **RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP):** sender-constrained token và proof-of-possession.
- **RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens:** xác thực client và ràng buộc token với chứng thư.
- **RFC 7519 — JSON Web Token (JWT):** JWT claims; chữ ký không cung cấp trạng thái one-time-use.

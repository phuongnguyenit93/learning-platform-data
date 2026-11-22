# Xoay vòng refresh token và phát hiện sử dụng lại

## 1. Vì sao cần xoay vòng refresh token?

Trong OAuth 2.0, access token thường có thời hạn tương đối ngắn và được gửi tới resource server để truy cập API. Khi access token hết hạn, client có thể cần một cách lấy access token mới mà không yêu cầu người dùng đăng nhập lại mỗi lần. **Refresh token** đảm nhiệm vai trò đó: client gửi refresh token tới Authorization Server để xin access token mới theo grant đã được cấp.

Refresh token thường có giá trị lâu hơn access token và có thể cấp ra nhiều access token trong suốt vòng đời của một phiên. Vì vậy, nếu refresh token bị đánh cắp, kẻ tấn công có thể tiếp tục đổi nó lấy access token mới cho tới khi token hết hạn hoặc bị thu hồi.

Ví dụ một phiên:

~~~text
Đăng nhập
   |
   v
Access token A1 + Refresh token R1
   |
   | A1 hết hạn
   v
Gửi R1 tới Authorization Server
   |
   v
Access token A2 + Refresh token R2
   |
   | A2 hết hạn
   v
Gửi R2
   |
   v
Access token A3 + Refresh token R3
~~~

Nếu R1 bị đánh cắp trước khi được dùng, attacker có thể gửi R1 và nhận token mới. Nếu hệ thống tiếp tục chấp nhận R1 nhiều lần, attacker có thể duy trì quyền truy cập trong thời gian dài mà người dùng hợp pháp khó nhận biết.

**Refresh token rotation** giải quyết một phần rủi ro này bằng cách dùng mỗi refresh token chỉ một lần: khi R1 được sử dụng thành công, Authorization Server vô hiệu hóa R1 và phát hành R2. Nếu R1 xuất hiện lần nữa sau khi đã được sử dụng, server phát hiện khả năng token bị replay và có thể thu hồi toàn bộ chuỗi refresh token liên quan.

Nguyên tắc cốt lõi:

> **Mỗi refresh token trong một chuỗi rotation chỉ được sử dụng một lần. Việc một token đã tiêu thụ xuất hiện lại là tín hiệu replay cần được xử lý theo chính sách thu hồi và ứng phó sự cố.**

Bài này thuộc phạm vi Security chung của JSON Web Token (JWT) và OAuth 2.0, áp dụng cho client, Authorization Server và hệ thống quản lý phiên. Refresh token không bắt buộc phải có định dạng JWT; nó có thể là chuỗi opaque ngẫu nhiên. Điều quan trọng là cơ chế vòng đời, ràng buộc client và trạng thái sử dụng lại.

## 2. Phân biệt access token và refresh token

| Thuộc tính | Access token | Refresh token |
| --- | --- | --- |
| Mục đích | Truy cập resource server/API. | Xin access token mới từ Authorization Server. |
| Nơi gửi | Resource server được token hướng tới. | Authorization Server/token endpoint. |
| Thời hạn | Thường ngắn. | Thường dài hơn, nhưng phải có giới hạn và cơ chế thu hồi. |
| Quyền | Scope/audience/claims phục vụ truy cập API. | Gắn với authorization grant, client và phạm vi được cấp; không dùng trực tiếp để gọi API nghiệp vụ. |
| Tần suất | Có thể được gửi trong nhiều API request cho đến khi hết hạn. | Chỉ gửi khi cần làm mới token hoặc theo quy trình quản lý phiên. |
| Rủi ro khi bị lộ | Attacker có thể gọi API trong phạm vi token cho đến khi hết hạn/thu hồi. | Attacker có thể liên tục lấy access token mới nếu token còn được chấp nhận. |

Không gửi refresh token tới resource server như một bearer access token. Resource server không nên chấp nhận refresh token để thay thế access token.

### 2.1. Refresh token có thể là opaque hoặc JWT

OAuth 2.0 không yêu cầu refresh token phải là JWT. Nhiều hệ thống dùng một chuỗi opaque có entropy cao và tra cứu trạng thái ở server:

~~~text
rt_4vR2...random-secret...
~~~

Một hệ thống khác có thể biểu diễn refresh token dưới dạng JWT đã ký. Tuy nhiên, rotation và reuse detection vẫn cần trạng thái server-side để biết token đã được sử dụng, bị thu hồi hay thuộc family nào.

Một JWT refresh token có chữ ký hợp lệ không tự cho biết nó chưa từng được sử dụng. Nếu cần one-time use, server phải duy trì trạng thái tương ứng, chẳng hạn token ID, family ID và trạng thái consumed/revoked.

## 3. Refresh token rotation là gì?

Rotation là quy trình thay refresh token hiện tại bằng một refresh token mới sau mỗi lần sử dụng thành công.

Trước khi refresh:

~~~text
Token family F-100
    R1: ACTIVE
~~~

Sau khi refresh R1 thành công:

~~~text
Token family F-100
    R1: CONSUMED
    R2: ACTIVE
~~~

Sau lần refresh tiếp theo:

~~~text
Token family F-100
    R1: CONSUMED
    R2: CONSUMED
    R3: ACTIVE
~~~

Tên **token family** là mô hình triển khai phổ biến để nhóm các refresh token kế tiếp được sinh ra từ cùng một authorization grant hoặc phiên. Đây là cách tổ chức trạng thái ở server; không phải claim bắt buộc của JWT hay một thuật ngữ giao thức mà mọi triển khai phải dùng giống nhau.

### 3.1. Token kế tiếp thay thế token trước

Khi R1 được chấp nhận:

1. Xác minh client và refresh token.
2. Kiểm tra token còn active, chưa hết hạn và chưa bị thu hồi.
3. Kiểm tra token thuộc đúng client/grant và các ràng buộc khác.
4. Đánh dấu R1 đã được sử dụng.
5. Tạo R2 mới trong cùng family.
6. Cấp access token mới theo quyền còn hiệu lực.
7. Trả R2 cho client.

Client phải thay thế R1 bằng R2 ngay khi nhận được phản hồi thành công. Không tiếp tục lưu hoặc dùng R1.

### 3.2. Vì sao phải lưu quan hệ giữa token cũ và token mới?

Nếu server chỉ xóa R1 rồi tạo R2, khi R1 xuất hiện lại server có thể chỉ biết rằng token không còn hợp lệ. Nó không nhất thiết biết R1 từng là một token hợp lệ đã được tiêu thụ hay chưa.

Để phát hiện replay, server cần giữ dấu vết tối thiểu:

- R1 đã được phát hành.
- R1 thuộc family F-100.
- R1 đã được tiêu thụ tại thời điểm nào.
- R2 là token kế tiếp trong family đó.
- Token nào hiện đang active.
- Family/grant đã bị thu hồi hay chưa.

Nhờ vậy, request dùng lại R1 có thể được phân biệt với token ngẫu nhiên hoặc token chưa từng được phát hành.

## 4. Mô hình token family và trạng thái

Một mô hình dữ liệu minh họa:

~~~text
RefreshToken
------------
token_id
token_hash
family_id
parent_token_id
subject_id
client_id
grant_id
scope
resource
issued_at
expires_at
consumed_at
revoked_at
status
sender_binding
~~~

Ý nghĩa:

| Trường | Mục đích |
| --- | --- |
| token_id | Định danh bản ghi token ở server. |
| token_hash | Giá trị băm/HMAC của refresh token để tra cứu mà không cần lưu secret dạng rõ. |
| family_id | Nhóm các token được xoay vòng trong cùng một phiên/grant. |
| parent_token_id | Token trước đó trong chuỗi, nếu lưu dạng linked chain. |
| subject_id | Người dùng hoặc principal mà grant đại diện. |
| client_id | Client được gắn với refresh token theo authorization grant. |
| grant_id | Định danh grant hoặc consent gốc. |
| scope/resource | Phạm vi quyền và resource server được phép. |
| issued_at/expires_at | Thời điểm phát hành và hết hạn. |
| consumed_at | Thời điểm token được sử dụng thành công. |
| revoked_at | Thời điểm token hoặc family bị thu hồi. |
| status | Trạng thái hiện tại như ACTIVE, CONSUMED, REVOKED, EXPIRED. |
| sender_binding | Thông tin ràng buộc token với client/key/certificate nếu áp dụng. |

Có thể lưu thêm IP, user agent hoặc thông tin thiết bị cho điều tra, nhưng chúng không nên được xem là bằng chứng danh tính mạnh. Các giá trị này có thể thay đổi hoặc bị giả mạo.

### 4.1. Các trạng thái cơ bản

| Trạng thái | Ý nghĩa | Có được refresh tiếp không? |
| --- | --- | --- |
| ACTIVE | Token đã phát hành, chưa sử dụng hoặc thu hồi. | Có, nếu các điều kiện khác đạt. |
| CONSUMED | Token đã được dùng để rotation thành công. | Không. Dùng lại là tín hiệu replay. |
| REVOKED | Token bị thu hồi trực tiếp hoặc theo family/grant. | Không. |
| EXPIRED | Đã quá thời hạn. | Không. |

Không nên đưa token đã CONSUMED trở lại ACTIVE. Rotation dựa trên tính chất một lần sử dụng.

### 4.2. Family có thể có một nhánh kế tiếp active

Trong mô hình rotation tuần tự, một family bình thường chỉ có một refresh token active tại một thời điểm:

~~~text
R1 -> R2 -> R3 -> R4
                    |
                    +-- ACTIVE
~~~

Nếu cùng một token sinh ra hai token kế tiếp độc lập:

~~~text
       +-> R2-A
R1 ----|
       +-> R2-B
~~~

thì hệ thống đã có hai nhánh quyền cùng xuất phát từ một refresh token. Đây là tình trạng cần được ngăn bằng thao tác atomic và unique constraint thích hợp.

## 5. Luồng rotation bình thường

Một lần refresh thành công có thể diễn ra như sau:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant AS as Authorization Server
    participant DB as Token Store
    C->>AS: POST /token với refresh token R1
    AS->>AS: Xác minh client và ràng buộc token
    AS->>DB: Đọc R1 và family F
    DB-->>AS: R1 ACTIVE, grant hợp lệ
    AS->>DB: Consume R1 và tạo R2 atomically
    DB-->>AS: Commit thành công
    AS->>AS: Tạo access token mới
    AS-->>C: access token A2 + refresh token R2
    C->>C: Lưu R2, loại bỏ R1
~~~

Trình tự cụ thể có thể khác nhau, nhưng server phải bảo đảm không có hai request cùng tiêu thụ R1 thành công.

### 5.1. Kiểm tra trước khi rotate

Authorization Server cần xác minh:

- Refresh token có tồn tại và thuộc issuer/store hiện tại không?
- Token có đang ACTIVE không?
- Token có hết hạn hoặc bị thu hồi không?
- Token có thuộc đúng client không?
- Client confidential có xác thực đúng không?
- Nếu token bị ràng buộc sender, request có chứng minh đúng khóa/chứng thư không?
- Authorization grant và subject có còn hợp lệ không?
- Scope/resource được yêu cầu có nằm trong phạm vi grant không?
- Family hoặc phiên có bị thu hồi không?

Không chỉ kiểm tra chuỗi token có khớp. Cần kiểm tra toàn bộ ngữ cảnh của grant và client.

### 5.2. Phát hành access token mới

Access token mới phải phản ánh quyền được phép tại thời điểm refresh theo policy của Authorization Server. Không tự động sao chép mọi claim cũ nếu role, membership, consent hoặc scope đã thay đổi.

Nếu client yêu cầu scope mới, Authorization Server chỉ được cấp trong phạm vi grant và quy tắc OAuth. Refresh token không phải cách để mở rộng consent.

### 5.3. Client thay token cũ bằng token mới

Khi nhận phản hồi thành công, client cần:

1. Lưu refresh token mới một cách an toàn.
2. Thay thế refresh token cũ trong storage.
3. Không gửi lại refresh token cũ.
4. Đồng bộ trạng thái giữa các thành phần client có thể refresh cùng phiên.
5. Chỉ sử dụng access token mới theo audience và thời hạn của nó.

Nếu client lưu R1 ở nhiều tab/process/device cùng lúc, chúng có thể vô tình gửi cùng một token. Đây là một nguyên nhân phổ biến tạo tín hiệu reuse giả.

## 6. Reuse detection: phát hiện refresh token đã bị dùng lại

**Refresh token reuse** xảy ra khi một refresh token đã được tiêu thụ trong quá trình rotation lại được gửi tới token endpoint.

Ví dụ:

~~~text
1. Client hợp pháp gửi R1.
2. Authorization Server tiêu thụ R1 và cấp R2.
3. R1 chuyển sang CONSUMED.
4. Attacker đang giữ bản sao R1 gửi lại R1.
5. Server phát hiện R1 đã CONSUMED.
6. Server coi đây là tín hiệu replay và thu hồi token family theo policy.
~~~

Nếu server chỉ từ chối R1 nhưng vẫn giữ R2 active, attacker có thể đã đổi R1 lấy R2 trước đó hoặc đang sở hữu một token kế tiếp. Thu hồi family giúp vô hiệu hóa chuỗi token kế tiếp có liên quan.

### 6.1. Vì sao phải thu hồi family?

Server không thể biết chắc ai là người gửi request thứ hai:

- Người dùng hợp pháp gửi lại token do lỗi đồng bộ.
- Attacker gửi token đã đánh cắp.
- Một request hợp pháp bị retry sau timeout.
- Hai tab/process đồng thời refresh.

Nhưng server biết một token one-time đã được sử dụng lại. Theo chính sách rotation, đây là bằng chứng có khả năng refresh token đã bị sao chép. Cách phản ứng an toàn là thu hồi token active trong family hoặc grant liên quan, rồi yêu cầu xác thực lại.

### 6.2. Server không thể luôn xác định ai là attacker

Giả sử attacker dùng R1 trước người dùng hợp pháp:

~~~text
R1 (stolen)
   |
   +-- Attacker dùng trước -> server cấp R2 cho attacker
   |
   +-- User dùng lại R1 -> server phát hiện reuse
                             |
                             v
                        revoke family
~~~

Nếu người dùng hợp pháp dùng R1 trước attacker, kết quả phát hiện tương tự khi attacker gửi R1 sau đó. Server chỉ biết có hai lần sử dụng một token one-time; nó không thể kết luận request đầu tiên là hợp pháp hay request thứ hai là attacker chỉ dựa vào token bearer.

Vì vậy, reuse detection thường ưu tiên bảo vệ grant bằng cách thu hồi chuỗi và buộc người dùng đăng nhập lại. Đây là đánh đổi có thể gây gián đoạn phiên hợp pháp nhưng ngăn chuỗi refresh tiếp tục được sử dụng.

### 6.3. Phản ứng khi phát hiện reuse

Một quy trình có thể gồm:

1. Đánh dấu token đã dùng lại và ghi nhận sự kiện.
2. Thu hồi refresh token active trong family.
3. Đánh dấu family/grant bị compromised hoặc revoked.
4. Ngăn mọi refresh tiếp theo từ family.
5. Áp dụng chính sách đối với access token đã được cấp từ grant.
6. Thông báo cho hệ thống session/account nếu cần.
7. Ghi audit và phát tín hiệu cho hệ thống phát hiện gian lận.
8. Yêu cầu người dùng xác thực lại và có thể tăng mức xác minh.

Không ghi raw refresh token vào log hoặc cảnh báo. Có thể dùng token ID, family ID, grant ID hoặc fingerprint đã bảo vệ.

## 7. Race condition: hai request refresh đồng thời

Rotation có thể phát hiện reuse, nhưng đồng thời cũng tạo ra tình huống cạnh tranh hợp pháp.

Ví dụ hai tab cùng giữ R1:

~~~text
Tab A                  Authorization Server                Tab B
  |                           |                                |
  |------ refresh R1 -------->|                                |
  |                           |<--------- refresh R1 ----------|
  |                           |                                |
  |                           | Hai request cạnh tranh         |
  |                           |                                |
  |<------ R2 ----------------|                                |
  |                           |------ reuse / reject ---------->|
~~~

Một request có thể tiêu thụ R1 thành công; request còn lại thấy R1 đã CONSUMED và bị xem là reuse. Nếu policy thu hồi family, R2 vừa cấp cũng có thể bị vô hiệu hóa.

### 7.1. Atomic consume

Server phải thực hiện việc chuyển trạng thái R1 từ ACTIVE sang CONSUMED theo thao tác atomic. Ví dụ về ý tưởng:

~~~sql
UPDATE refresh_tokens
SET status = 'CONSUMED',
    consumed_at = CURRENT_TIMESTAMP
WHERE token_id = :token_id
  AND status = 'ACTIVE'
  AND revoked_at IS NULL
  AND expires_at > CURRENT_TIMESTAMP;
~~~

Chỉ request cập nhật được đúng một bản ghi mới có quyền tiếp tục phát hành token kế tiếp. Nếu số dòng cập nhật bằng 0, server phải đọc trạng thái hiện tại để phân biệt token không tồn tại, hết hạn, bị thu hồi hay đã được dùng.

Việc consume R1 và tạo R2 phải được bảo vệ bằng transaction hoặc cơ chế tương đương. Nếu consume thành công nhưng tạo R2 thất bại, hệ thống cần có quy tắc phục hồi rõ ràng; không để token bị tiêu thụ mà không có cách xử lý.

### 7.2. Ràng buộc một successor

Có thể áp dụng unique constraint hoặc logic transaction để bảo đảm mỗi token cha chỉ có tối đa một token kế tiếp hợp lệ trong family.

~~~text
UNIQUE(parent_token_id)
~~~

Đây là minh họa ràng buộc dữ liệu; schema thực tế có thể khác. Mục tiêu là không tạo hai nhánh successor cho cùng một token.

### 7.3. Client cần single-flight refresh

Client nên bảo đảm chỉ có một thao tác refresh đang diễn ra cho mỗi session/token hiện tại:

- Các tab hoặc process dùng chung một cơ chế điều phối.
- Khi một request refresh bắt đầu, các request khác chờ kết quả.
- Khi refresh thành công, mọi thành phần sử dụng token mới.
- Không gửi đồng thời cùng một refresh token tới nhiều request.

Điều này giảm reuse giả do concurrency, nhưng không thay thế kiểm soát atomic ở Authorization Server. Client có thể lỗi hoặc bị điều khiển bởi attacker.

## 8. Mất phản hồi sau khi server đã rotate

Một trường hợp khó là:

1. Client gửi R1.
2. Server consume R1 và commit R2.
3. Server gửi response chứa R2.
4. Kết nối bị ngắt trước khi client nhận được response.
5. Client chỉ còn lưu R1 và retry.
6. Server phát hiện R1 đã CONSUMED và coi là reuse.

Đây là lỗi đồng bộ giữa server và client, nhưng nhìn từ server nó giống replay của attacker.

### 8.1. Không tự động retry vô hạn

Nếu client retry R1 nhiều lần, nó có thể liên tục kích hoạt reuse detection. Client cần phân biệt:

- Request chưa được gửi hoặc chắc chắn chưa tới server.
- Request đã tới server nhưng không biết kết quả.
- Response đã nhận đầy đủ và token mới đã được lưu.

Khi không biết server đã commit hay chưa, retry cùng refresh token có rủi ro làm family bị thu hồi. Không nên tự động lặp lại vô hạn.

### 8.2. Thiết kế idempotent recovery nếu thực sự cần

Một hệ thống có thể thiết kế cơ chế phục hồi có kiểm soát, ví dụ:

- Client gửi idempotency key cho thao tác refresh.
- Server lưu kết quả của lần refresh đã commit trong một khoảng thời gian ngắn.
- Lần retry phải chứng minh cùng client/session và cùng request context.
- Response được lưu hoặc mã hóa để chỉ có bên phù hợp lấy lại.
- Nếu dùng public client, cần cân nhắc sender-constrained proof để giảm nguy cơ attacker phát lại cùng token và key.

Đây là cơ chế mở rộng do hệ thống thiết kế, không phải hành vi tự động được bảo đảm bởi OAuth 2.0. Idempotency key đơn thuần không phải bằng chứng danh tính: nếu attacker đánh cắp cả refresh token lẫn key, họ vẫn có thể thử phát lại. Phải giới hạn thời gian, ràng buộc client và đánh giá rủi ro.

### 8.3. Grace period có đánh đổi bảo mật

Một số triển khai cho phép token cũ được dùng lại trong một khoảng grace period để giảm lỗi do retry hoặc nhiều request đồng thời. Cách này làm suy yếu thuộc tính one-time use nếu không có ràng buộc bổ sung.

Nếu áp dụng:

- Thời gian phải ngắn và được đo lường.
- Chỉ áp dụng trong một ngữ cảnh client/session xác định.
- Ưu tiên kết hợp sender-constrained token.
- Không cấp nhiều successor độc lập cho cùng token.
- Không cho phép token cũ được dùng tùy ý trong toàn bộ grace window.
- Có audit, giới hạn retry và kiểm thử race/replay.

Không nên dùng grace period dài như một cách che lỗi đồng bộ client. Giải pháp tốt hơn thường là điều phối single-flight và thiết kế recovery rõ ràng.

## 9. Ràng buộc refresh token với client

Refresh token phải được gắn với client mà nó được cấp cho. Khi token được gửi tới token endpoint, Authorization Server cần xác minh client phù hợp theo loại client và grant.

### 9.1. Confidential client

Confidential client có khả năng giữ bí mật xác thực, ví dụ một service chạy ở môi trường server được kiểm soát. Khi refresh, client phải xác thực theo phương thức đã đăng ký và server phải kiểm tra refresh token được cấp cho client đó.

Không chấp nhận refresh token của client A chỉ vì client B biết giá trị token.

### 9.2. Public client

Public client, chẳng hạn ứng dụng chạy trên thiết bị người dùng hoặc môi trường không thể giữ client secret, không thể dựa vào một secret nhúng trong ứng dụng như bằng chứng bí mật đáng tin cậy.

Theo OAuth 2.0 Security Best Current Practice (RFC 9700), với public client, Authorization Server phải dùng một trong các cơ chế để phát hiện replay của refresh token:

- **Refresh token rotation:** cấp refresh token mới mỗi lần sử dụng và phát hiện token cũ được dùng lại.
- **Sender-constrained refresh token:** ràng buộc token với khóa hoặc chứng thư của client để token bị đánh cắp riêng lẻ không đủ sử dụng.

Hai cơ chế có thể được kết hợp để tăng bảo vệ nếu kiến trúc và profile hỗ trợ.

### 9.3. Sender-constrained refresh token

Một token được ràng buộc sender yêu cầu client chứng minh đang sở hữu khóa/chứng thư tương ứng. Ví dụ cơ chế:

- OAuth 2.0 Mutual-TLS Certificate-Bound Access Tokens (RFC 8705).
- Demonstrating Proof of Possession (DPoP, RFC 9449), trong các profile và luồng áp dụng.

Sender constraint làm giảm nguy cơ attacker chỉ cần sao chép chuỗi token là dùng được. Nó không bảo vệ nếu attacker đồng thời chiếm được private key hoặc kiểm soát chính client.

### 9.4. Không dùng client_id như một bí mật

client_id thường là định danh công khai của ứng dụng. Với public client, biết client_id không chứng minh request đến từ ứng dụng hợp pháp. Cần rotation hoặc sender constraint theo yêu cầu bảo mật, cùng các biện pháp xác thực client phù hợp.

## 10. Giới hạn scope, resource và grant khi refresh

Refresh token không phải một grant mới để client tự xin thêm quyền. Nó chỉ tiếp tục một authorization grant đã được cấp, trong phạm vi chính sách và consent tương ứng.

### 10.1. Scope không được mở rộng tùy ý

Theo OAuth 2.0, khi client gửi scope trong refresh request, scope yêu cầu không được vượt quá phạm vi đã được cấp ban đầu. Authorization Server có thể cấp cùng scope hoặc scope hẹp hơn theo policy.

Ví dụ:

~~~text
Original grant:
    invoice.read
    invoice.approve

Refresh request:
    invoice.read

Allowed result:
    invoice.read
~~~

Request xin thêm invoice.delete phải bị từ chối nếu quyền đó không nằm trong grant hoặc không có một quy trình cấp quyền mới.

### 10.2. Resource/audience cũng cần được giới hạn

Nếu hệ thống dùng resource indicators hoặc nhiều resource server, refresh token phải được gắn với resource/authorization grant phù hợp. Không cho client dùng refresh token của API A để xin access token rộng cho API B nếu grant không cho phép.

### 10.3. Client binding và grant binding

Bản ghi refresh token cần gắn với:

- Client được cấp token.
- Subject/user hoặc principal được đại diện.
- Authorization grant/consent.
- Scope và resource được cấp.
- Tenant hoặc context nếu hợp đồng có.
- Sender constraint nếu áp dụng.

Mỗi lần refresh phải kiểm tra các ràng buộc này, không chỉ tìm token hash.

## 11. Expiration, idle timeout và absolute lifetime

Rotation không có nghĩa phiên được kéo dài vô hạn. Nếu mỗi lần refresh đều đặt expires_at mới mà không có giới hạn tổng, attacker hoặc client bị bỏ quên có thể duy trì family mãi mãi.

Nên phân biệt:

- **Token expiration:** thời điểm một refresh token cụ thể hết hạn.
- **Idle timeout:** family/session hết hạn nếu không hoạt động trong khoảng thời gian quy định.
- **Absolute lifetime:** giới hạn tổng thời gian tồn tại của grant/family kể từ khi được tạo.
- **Session lifetime:** thời hạn phiên theo chính sách xác thực và nghiệp vụ.

Ví dụ:

~~~text
Family created: 2026-11-01 09:00
Absolute expiry: 2026-11-08 09:00
Idle timeout: 12 hours
Current refresh token expiry: min(now + token TTL, idle deadline, absolute expiry)
~~~

Đây là ví dụ chính sách, không phải thời hạn bắt buộc của OAuth.

### 11.1. Không reset absolute expiry sau mỗi rotation

Khi phát hành R2 từ R1, server có thể đặt thời hạn token mới theo idle timeout nhưng vẫn phải giữ absolute expiry của family/grant. Rotation không được vô tình tạo ra một phiên sống vô hạn.

### 11.2. Re-authentication cho hành động nhạy cảm

Một refresh token còn hiệu lực không có nghĩa người dùng đã xác thực gần đây hoặc có mức xác thực đủ cao cho mọi hành động. Hành động nhạy cảm có thể yêu cầu:

- Xác thực lại.
- MFA hoặc step-up authentication.
- Kiểm tra mức assurance.
- Kiểm tra thiết bị hoặc risk context.

Refresh token chỉ duy trì grant theo policy; nó không thay thế mọi yêu cầu xác thực mới.

## 12. Lưu trữ refresh token và giảm tác động khi bị lộ

Refresh token có giá trị cao, vì vậy nơi lưu trữ và cách truyền token là một phần quan trọng của vòng đời.

### 12.1. Sinh token đủ ngẫu nhiên

Với opaque refresh token, dùng bộ sinh số ngẫu nhiên mật mã (CSPRNG) và entropy đủ lớn. Token không được dự đoán từ user ID, timestamp, counter hoặc dữ liệu có thể suy ra.

Ví dụ biểu diễn:

~~~text
rt_<high-entropy-random-value>
~~~

Prefix có thể giúp phân loại định dạng nhưng không phải cơ chế bảo mật. Secret ngẫu nhiên mới là phần cần được bảo vệ.

### 12.2. Không lưu raw refresh token ở server nếu không cần

Với opaque token, server có thể lưu hash hoặc HMAC digest để tra cứu:

~~~text
raw refresh token
       |
       v
HMAC-SHA-256(server-side lookup key, token)
       |
       v
stored token_hash
~~~

Khi nhận token, server tính lại digest và tìm bản ghi tương ứng. Nếu database bị đọc trái phép, attacker không lập tức có raw refresh token để sử dụng.

Lookup key/HMAC secret phải được quản lý và xoay vòng phù hợp. Không dùng hash yếu hoặc giá trị dễ đoán; không ghi raw token vào log, trace hoặc exception.

### 12.3. Lưu trữ phía client

Client cần dùng storage phù hợp với nền tảng và threat model:

- Không lưu refresh token trong URL hoặc nơi dễ bị ghi vào lịch sử/log.
- Hạn chế JavaScript có thể đọc token trong môi trường trình duyệt.
- Dùng cơ chế bảo vệ dữ liệu cục bộ của hệ điều hành/thiết bị khi có.
- Bảo vệ backup, đồng bộ và dữ liệu chẩn đoán.
- Không chia sẻ token giữa các ứng dụng hoặc thiết bị ngoài phạm vi grant.
- Xóa token khi logout, revoke hoặc phát hiện compromise.

Không có một loại storage phù hợp cho mọi client. Cần đánh giá XSS, malware, thiết bị bị root/jailbreak, backup và khả năng kiểm soát thiết bị.

### 12.4. TLS và phạm vi truyền token

Refresh token chỉ nên được gửi tới Authorization Server qua TLS. Không đưa token vào query string, URL, analytics, referrer hoặc log. Chỉ endpoint/token client có nhu cầu mới được nhận token.

## 13. Thu hồi refresh token, family và grant

Một hệ thống cần phân biệt phạm vi thu hồi:

| Phạm vi | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Token | Thu hồi một refresh token cụ thể. | R3 bị lộ nhưng chưa có bằng chứng compromise cả family. |
| Family/session | Thu hồi toàn bộ chuỗi token của một phiên hoặc thiết bị. | Reuse R1 trong family F-100. |
| Grant/consent | Thu hồi quyền cấp cho một client hoặc một lần consent. | Người dùng rút consent khỏi ứng dụng. |
| User/account | Vô hiệu hóa các phiên hoặc grant theo chính sách tài khoản. | Tài khoản bị khóa do compromise. |
| Client | Thu hồi token/grant liên quan đến một client bị xâm phạm. | Ứng dụng đối tác bị compromise. |

Khi phát hiện reuse trong một family, phản ứng thông thường là thu hồi token active của family đó. Không nhất thiết phải đăng xuất tất cả thiết bị của người dùng nếu chưa có lý do; mỗi thiết bị/phiên nên có family riêng để giới hạn phạm vi ảnh hưởng.

### 13.1. Logout

Logout nên thu hồi refresh token hoặc family tương ứng ở Authorization Server. Xóa token khỏi client là cần thiết nhưng không đủ, vì bản sao đã bị đánh cắp ở nơi khác vẫn có thể tồn tại.

### 13.2. Revocation endpoint

RFC 7009 định nghĩa OAuth 2.0 Token Revocation. Client có thể gửi token tới revocation endpoint để yêu cầu thu hồi. Authorization Server có thể hỗ trợ thu hồi refresh token và access token theo policy.

RFC 7009 nêu rằng khi token được gửi để thu hồi là refresh token, Authorization Server **SHOULD** thu hồi cả access token được cấp dựa trên cùng authorization grant. Đây là khuyến nghị ở phía Authorization Server; cách resource server nhận biết việc thu hồi và thời điểm ngừng chấp nhận access token vẫn phụ thuộc cơ chế triển khai.

Hệ thống cần định nghĩa việc thu hồi một refresh token có ảnh hưởng tới:

- Token đó.
- Các refresh token kế tiếp trong cùng family.
- Các access token được cấp từ cùng grant.
- Các phiên/consent liên quan.

Không giả định mọi resource server sẽ lập tức biết một JWT access token đã bị thu hồi.

### 13.3. Thu hồi refresh token không luôn làm access token JWT mất hiệu lực ngay

Access token JWT có thể được resource server xác minh offline bằng chữ ký, issuer, audience và thời hạn. Nếu API không tra trạng thái online, một access token đã phát hành có thể tiếp tục được chấp nhận cho đến khi hết hạn.

Muốn thu hồi access token nhanh hơn, hệ thống có thể:

- Dùng access token lifetime ngắn.
- Dùng introspection hoặc trạng thái token tập trung khi phù hợp.
- Dùng denylist/token version hoặc session version cho các trường hợp cần thiết.
- Có cơ chế phát tín hiệu thu hồi tới resource server.
- Giới hạn quyền và audience của access token.

Đây là trade-off giữa khả năng thu hồi nhanh, độ trễ và tính sẵn sàng.

## 14. Phân biệt reuse detection với các lỗi refresh thông thường

Không phải mọi request refresh thất bại đều là reuse attack.

| Trường hợp | Dấu hiệu | Hành vi thường gặp |
| --- | --- | --- |
| Token không tồn tại | Không tìm thấy digest/bản ghi. | Từ chối; không nhất thiết có thể kết luận reuse. |
| Token hết hạn | expires_at đã qua. | Từ chối và yêu cầu đăng nhập lại. |
| Token đã bị revoke | revoked_at/status cho biết đã thu hồi. | Từ chối; audit theo nguyên nhân. |
| Token đã consumed | Có consumed_at hoặc successor. | Reuse signal; đánh giá và thu hồi family theo policy. |
| Sai client binding | Token thuộc client khác. | Từ chối; ghi nhận lỗi binding. |
| Sender proof sai | DPoP/mTLS proof không phù hợp. | Từ chối; có thể là token theft hoặc lỗi client. |
| Grant bị thu hồi | Consent/session không còn hiệu lực. | Từ chối và ngừng cấp token mới. |
| Request đồng thời | Hai request cùng dùng token active. | Một request thắng atomic consume; request còn lại có thể bị xem là reuse. |
| Retry sau khi mất response | Client không biết rotation đã commit. | Có thể bị xem là reuse nếu không có recovery protocol. |

Server nên giữ reason code nội bộ để phân biệt sự kiện, nhưng response công khai không nên tiết lộ quá nhiều chi tiết giúp attacker dò trạng thái token.

## 15. Reuse detection không phải giải pháp duy nhất

Rotation là một cách phát hiện replay; nó không bảo đảm refresh token không thể bị đánh cắp hoặc sử dụng lần đầu.

### 15.1. Token theft trước lần sử dụng tiếp theo

Nếu attacker lấy được R3 khi R3 vẫn ACTIVE và dùng nó trước chủ thể hợp pháp, server có thể chấp nhận request đầu tiên. Attacker nhận R4. Chỉ khi R3 được dùng lần nữa thì reuse detection mới phát hiện có replay.

Vì vậy, cần kết hợp:

- Sender constraint khi client/profile hỗ trợ.
- Bảo vệ storage phía client.
- TLS và giảm đường rò rỉ token.
- Rotation và reuse detection.
- Giới hạn absolute/idle lifetime.
- Theo dõi hành vi bất thường.
- Thu hồi family/grant khi có tín hiệu compromise.

### 15.2. Sender constraint bổ sung cho rotation

Nếu refresh token được ràng buộc với một khóa riêng của client, attacker chỉ đánh cắp token nhưng không có khóa có thể không sử dụng được token. Rotation vẫn hữu ích để phát hiện và giới hạn replay nếu credential hoặc thiết bị bị xâm phạm sâu hơn.

### 15.3. Không dùng IP hoặc User-Agent làm bằng chứng duy nhất

IP có thể thay đổi do mạng di động, VPN, NAT hoặc proxy. User-Agent có thể bị giả mạo. Chúng hữu ích như tín hiệu risk và điều tra nhưng không nên thay thế token binding, client authentication hoặc proof-of-possession.

## 16. Pseudocode: refresh và rotation an toàn

Ví dụ dưới đây mô tả luồng server-side. Các thao tác lưu trữ và transaction là khái niệm; triển khai phải dùng cơ chế atomic của kho dữ liệu.

~~~text
function rotateRefreshToken(request):
    client = authenticateClientIfRequired(request)
    if client.failed:
        return INVALID_CLIENT

    presentedToken = request.refresh_token
    tokenDigest = secureLookupDigest(presentedToken)

    begin transaction

    record = findRefreshTokenForUpdate(tokenDigest)
    if record is null:
        rollback
        return INVALID_GRANT

    if record.client_id != client.id:
        rollback
        auditClientBindingFailure(record.family_id)
        return INVALID_GRANT

    family = loadFamilyForUpdate(record.family_id)
    if family.status != ACTIVE:
        rollback
        return INVALID_GRANT

    if record.status == CONSUMED:
        revokeActiveTokensInFamily(family.id)
        markFamilyCompromised(family.id)
        commit
        auditRefreshReuse(family.id, record.token_id)
        return INVALID_GRANT

    if record.status != ACTIVE or record.expired:
        rollback
        return INVALID_GRANT

    if not senderProofValid(request, record.sender_binding):
        rollback
        return INVALID_GRANT

    grant = loadCurrentGrant(record.grant_id)
    if not grant.active:
        revokeFamily(family.id)
        commit
        return INVALID_GRANT

    effectiveScope = calculateAllowedRefreshScope(
        originalGrant = grant.scope,
        requestedScope = request.scope,
        tokenConstraints = record.scope
    )
    if effectiveScope.invalid:
        rollback
        return INVALID_SCOPE

    markConsumed(record)
    successor = createNextRefreshToken(
        family = family,
        parent = record,
        client = client,
        subject = grant.subject,
        scope = effectiveScope,
        expiresAt = min(
            now + refreshTokenTTL,
            family.idleDeadline,
            family.absoluteExpiresAt
        ),
        senderBinding = record.sender_binding
    )
    save(successor)

    commit transaction

    accessToken = issueAccessToken(
        subject = grant.subject,
        client = client,
        scope = effectiveScope,
        resources = grant.resources
    )

    return SUCCESS(accessToken, successor.rawValue)
~~~

Pseudocode trên chỉ minh họa một mô hình. Một số hệ thống tạo access token trước khi commit hoặc lưu response theo cơ chế idempotent; điều quan trọng là không để hai request cùng consume một refresh token thành công và không trả token kế tiếp trước khi trạng thái rotation được commit an toàn.

Trong triển khai thực tế cần xử lý riêng:

- Token không tồn tại.
- Token expired/revoked.
- Client authentication failure.
- Sender proof failure.
- Grant hoặc user bị thu hồi.
- Lỗi transaction.
- Reuse detection.
- Response bị mất sau commit.
- Hai request đồng thời.

## 17. Pseudocode: xử lý reuse và thu hồi family

~~~text
function handleRefreshReuse(consumedToken):
    begin transaction

    family = loadFamilyForUpdate(consumedToken.family_id)
    if family is null:
        rollback
        return

    if family.status == ACTIVE:
        family.status = COMPROMISED
        family.revoked_at = now
        family.revoke_reason = "REFRESH_TOKEN_REUSE"

        revokeAllActiveRefreshTokens(family.id)
        revokeOrMarkRelatedGrant(family.grant_id)
        save(family)

    commit transaction

    publishSecurityEvent(
        type = "refresh_token_reuse_detected",
        familyId = family.id,
        tokenId = consumedToken.token_id,
        subjectId = family.subject_id,
        clientId = family.client_id
    )

    requireReauthenticationForFamily(family.id)
~~~

Không nhất thiết phải thu hồi mọi family của user. Nếu phát hiện compromise ở một family, phạm vi phản ứng nên theo grant/session và chính sách incident response. Có thể mở rộng sang toàn bộ tài khoản khi có bằng chứng hoặc mức rủi ro đủ cao.

## 18. Những lỗi thường gặp

| Sai lầm | Rủi ro | Cách phòng tránh |
| --- | --- | --- |
| Cho phép refresh token dùng nhiều lần | Token bị đánh cắp có thể được replay lâu dài. | Rotation one-time hoặc sender constraint theo yêu cầu. |
| Xóa token cũ mà không giữ dấu vết | Không phân biệt token chưa từng tồn tại với token đã bị dùng lại. | Lưu consumed state và family relationship. |
| Chỉ revoke token cũ khi reuse | Token successor có thể vẫn nằm trong tay attacker. | Revoke active token/family theo policy. |
| Không ràng buộc token với client | Client khác có thể thử dùng token bị lộ. | Client binding và sender constraint khi phù hợp. |
| Hai request cùng consume token | Tạo hai successor hoặc gây false-positive reuse. | Atomic update, transaction và single-flight client. |
| Retry mù sau khi mất response | Client tự kích hoạt reuse detection. | Có recovery protocol; không retry vô hạn. |
| Grace period quá dài | Token cũ có thể được replay trong thời gian cho phép. | Giới hạn rất ngắn, ràng buộc sender và đánh giá rủi ro. |
| Reset absolute expiry mỗi lần rotate | Family có thể sống vô hạn. | Giữ absolute lifetime của grant/family. |
| Cấp scope rộng hơn grant | Refresh trở thành đường privilege escalation. | Giới hạn scope/resource theo grant và token constraints. |
| Không tách family theo session/device | Một phiên bị compromise có thể làm gián đoạn mọi thiết bị hoặc ngược lại không thu hồi đủ. | Quản lý family theo session/grant và định nghĩa phạm vi revoke. |
| Coi refresh revoke làm JWT access token mất hiệu lực ngay | API offline vẫn chấp nhận access token còn hạn. | Short-lived access token hoặc cơ chế revocation online/versioning. |
| Ghi raw token vào log | Log trở thành nguồn đánh cắp credential. | Chỉ log ID/fingerprint đã bảo vệ và reason code. |
| Chỉ dựa vào IP/User-Agent | Attacker có thể giả mạo; người dùng hợp pháp có thể đổi mạng. | Dùng như risk signal, không làm bằng chứng duy nhất. |
| Không có audit reuse | Không thể điều tra token family bị replay. | Ghi event, family, subject, client và thời điểm an toàn. |

## 19. Kịch bản kiểm thử rotation và reuse detection

Kiểm thử cần bao gồm luồng bình thường, replay, concurrency, lỗi mạng và thu hồi.

### 19.1. Luồng rotation bình thường

~~~text
R1 ACTIVE
Client refresh R1
    -> A2 + R2 được cấp
    -> R1 = CONSUMED
    -> R2 = ACTIVE

Client refresh R2
    -> A3 + R3 được cấp
    -> R2 = CONSUMED
    -> R3 = ACTIVE
~~~

Xác minh R1 và R2 không thể tiếp tục được dùng sau khi đã consume.

### 19.2. Replay token cũ

~~~text
R1 -> rotation thành công -> R2 ACTIVE
Attacker gửi lại R1
    -> reuse detected
    -> family bị revoke/compromised
    -> R2 không còn refresh được
~~~

Xác minh server không chỉ từ chối R1 mà còn vô hiệu hóa successor theo policy.

### 19.3. Hai request đồng thời

- Gửi hai refresh request cùng R1 tại gần như cùng thời điểm.
- Chỉ một request được consume R1 thành công.
- Không có hai successor active.
- Request còn lại được xử lý theo reuse/concurrency policy.
- Nếu family bị revoke, successor vừa cấp cũng không thể tiếp tục refresh.

### 19.4. Mất response và retry

- Server commit R2 nhưng response bị mất.
- Client retry R1.
- Xác minh hành vi theo recovery protocol đã thiết kế.
- Không tạo thêm successor ngoài ý muốn.
- Không để idempotency key đơn lẻ trở thành bằng chứng cho phép replay.

### 19.5. Binding và scope

- Client A dùng refresh token của client B.
- Sender proof không khớp khóa/chứng thư.
- Refresh request xin scope rộng hơn grant.
- Resource/audience không thuộc grant.
- User hoặc grant bị thu hồi trước khi refresh.

Các trường hợp không hợp lệ phải bị từ chối và không phát hành successor.

### 19.6. Expiration và family lifetime

- Token đã hết hạn.
- Idle timeout đã qua.
- Absolute lifetime đã qua dù vừa có rotation.
- Family bị logout/revoke.
- Một family bị revoke không làm ảnh hưởng family khác ngoài phạm vi policy.

### 19.7. Access token sau khi family bị revoke

- Access token JWT còn hạn sau khi refresh family bị revoke.
- Resource server offline tiếp tục xác minh chữ ký.
- Kiểm tra hệ thống có áp dụng short TTL, introspection, version hoặc deny signal theo policy không.
- Xác nhận tài liệu hệ thống mô tả đúng thời gian thu hồi thực tế.

## 20. Giám sát và ứng phó sự cố

Reuse detection cần được vận hành như một tín hiệu bảo mật, không chỉ là một nhánh lỗi trong token endpoint.

### 20.1. Sự kiện nên ghi nhận

- Refresh token reuse detected.
- Client binding failure.
- Sender proof failure.
- Refresh token expired/revoked.
- Family revoked/compromised.
- Concurrent refresh conflict.
- Idempotent recovery success/failure.
- JWKS/token signing events nếu có liên quan tới hệ thống phát hành.

### 20.2. Trường audit phù hợp

~~~json
{
  "event": "refresh_token_reuse_detected",
  "family_id": "family-100",
  "token_id": "token-previous",
  "subject_id": "user-514",
  "client_id": "mobile-client",
  "grant_id": "grant-900",
  "detected_at": "2026-11-16T09:30:00Z",
  "action": "FAMILY_REVOKED",
  "reason": "CONSUMED_TOKEN_PRESENTED_AGAIN"
}
~~~

Đây là event minh họa. Không ghi raw refresh token, access token hoặc sender private key.

### 20.3. Phân biệt replay với lỗi đồng bộ client

Một reuse event có thể do attacker hoặc do client:

- Mở nhiều tab/process.
- Retry sau timeout.
- Lưu token mới không thành công.
- Đồng bộ storage lỗi.
- Thiết bị cũ vẫn giữ token đã rotate.

Điều tra có thể dùng thời điểm, family, client, sender binding, device context và request correlation. IP/User-Agent chỉ là tín hiệu bổ sung, không đủ để kết luận danh tính.

### 20.4. Phản ứng sau sự kiện

Theo policy, hệ thống có thể:

- Thu hồi family bị ảnh hưởng.
- Yêu cầu đăng nhập lại.
- Thông báo người dùng về phiên bị kết thúc.
- Thu hồi grant nếu có dấu hiệu compromise rộng.
- Tăng xác minh cho lần đăng nhập kế tiếp.
- Giữ audit để điều tra.
- Kiểm tra access token đã phát hành và phạm vi tài nguyên có thể bị truy cập.

Không tự động khóa toàn bộ tài khoản chỉ vì một lần reuse nếu chưa đánh giá phạm vi và policy; điều đó có thể tạo điều kiện gây từ chối dịch vụ với người dùng hợp pháp.

## 21. Checklist thiết kế refresh token rotation

Trước khi triển khai, hãy trả lời:

1. **Client type:** client là confidential hay public? Cơ chế xác thực/binding nào được áp dụng?
2. **Token format:** refresh token opaque hay JWT? Trạng thái one-time được lưu ở đâu?
3. **Token family:** family đại diện cho session, device, grant hay consent nào?
4. **One-time use:** mỗi token có chỉ một lần consume thành công không?
5. **Atomicity:** consume token và tạo successor được bảo vệ bằng transaction/compare-and-swap ra sao?
6. **Reuse detection:** server phân biệt ACTIVE, CONSUMED, REVOKED và EXPIRED như thế nào?
7. **Reuse response:** phát hiện token cũ thì thu hồi token, family hay grant nào?
8. **Concurrency:** client điều phối single-flight và server xử lý hai request cùng token thế nào?
9. **Lost response:** client phục hồi khi rotation commit nhưng response bị mất ra sao?
10. **Grace period:** có dùng không; thời gian và sender binding nào giới hạn rủi ro?
11. **Client binding:** token có bị gắn với client/grant và sender key/certificate không?
12. **Scope/resource:** refresh có thể duy trì hoặc thu hẹp quyền nào; có ngăn mở rộng grant không?
13. **Lifetime:** token TTL, idle timeout và absolute lifetime được quản lý riêng không?
14. **Storage:** token có entropy đủ lớn; server có tránh lưu raw secret; client storage có được bảo vệ không?
15. **Revocation:** logout, reuse, account disable và consent revoke ảnh hưởng family/access token ra sao?
16. **Access token:** API xử lý JWT access token còn hạn sau khi refresh family bị revoke như thế nào?
17. **Observability:** có audit, metric và cảnh báo reuse/concurrency không?
18. **Testing:** có kiểm thử replay, race, lost response, sender binding, expiry và family isolation không?

## 22. Ghi nhớ trọng tâm

- Refresh token có thể cấp access token mới nên cần được bảo vệ chặt hơn một access token ngắn hạn.
- Rotation thay token hiện tại bằng token mới sau mỗi lần refresh thành công; token cũ trở thành CONSUMED.
- Server phải lưu quan hệ giữa token cũ và successor để nhận diện token đã dùng lại.
- Khi token đã CONSUMED xuất hiện lần nữa, đó là tín hiệu replay; thu hồi family giúp vô hiệu hóa các token kế tiếp có liên quan.
- Server không luôn xác định được request nào là attacker; reuse detection có thể buộc phiên hợp pháp đăng nhập lại.
- Consume phải atomic; client cần single-flight để giảm race giữa tab/process.
- Mất response sau commit có thể khiến retry token cũ bị xem là reuse; recovery/idempotency phải được thiết kế có ràng buộc, không mở grace window tùy tiện.
- Với public client, RFC 9700 yêu cầu cơ chế phát hiện replay bằng rotation hoặc sender-constrained refresh token.
- Rotation không thay thế client binding, scope/resource restriction, expiration, absolute lifetime, storage protection và revocation.
- Thu hồi refresh family không nhất thiết làm JWT access token đã phát hành mất hiệu lực ngay; cần thiết kế access token lifetime hoặc revocation signal phù hợp.

**Tài liệu tham khảo kỹ thuật:** RFC 6749 (The OAuth 2.0 Authorization Framework, refresh token grant); RFC 7009 (OAuth 2.0 Token Revocation); RFC 9700 (Best Current Practice for OAuth 2.0 Security, refresh token protection and replay detection); RFC 8705 (OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens); RFC 9449 (OAuth 2.0 Demonstrating Proof of Possession); RFC 7519 (JSON Web Token). Các chuẩn xác định hành vi OAuth và cơ chế bảo vệ token; mô hình family, transaction, concurrency recovery và audit cần được triển khai theo hợp đồng cụ thể của Authorization Server.

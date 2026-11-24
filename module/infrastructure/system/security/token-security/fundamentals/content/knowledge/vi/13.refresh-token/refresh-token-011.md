# Replay token làm mới

## 1. Vấn đề: một refresh token bị dùng lại có thể kéo dài quyền truy cập

Trong chương **Refresh token** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**, chúng ta xét một tình huống rất quan trọng của vòng đời token: **refresh token replay** — một refresh token bị chiếm đoạt hoặc bị sao chép rồi được gửi lại tới Authorization Server (AS) để xin access token mới.

Giả sử ứng dụng quản lý đơn hàng có người dùng Alice:

1. Alice hoàn thành luồng OAuth 2.0/OIDC hợp lệ. Client nhận **access token** `A1` và **refresh token** `R1`.
2. `A1` có thời hạn ngắn, ví dụ 15 phút, được dùng gọi Orders API.
3. Khi `A1` gần hết hạn, client gửi `R1` đến token endpoint để xin `A2`.
4. Nếu bên khác đã lấy được `R1`, bên đó cũng có thể thử gửi `R1` để xin access token mới.

Nếu hệ thống cho phép `R1` dùng nhiều lần mà không có cơ chế ràng buộc hoặc phát hiện sử dụng lại, bên có token bị đánh cắp có thể liên tục xin access token mới trong suốt vòng đời refresh token. **Access token có TTL ngắn không đủ giải quyết vấn đề nếu refresh token bị lộ.**

**Replay** ở đây không nhất thiết là kẻ tấn công phá chữ ký JWT. Họ có thể chỉ **trình lại đúng chuỗi credential đã cấp**. Vì thế bảo vệ refresh token phải xét cả phát hành, lưu trữ, cách dùng tại token endpoint, rotation, giới hạn thời gian, thu hồi và phát hiện reuse.

### Mục tiêu bài học

Sau bài này, bạn có thể:

- Phân biệt replay refresh token với replay access token, authorization code và lỗi xác thực khác.
- Giải thích **refresh token rotation**, **token family** và lý do AS phải phát hiện việc dùng token đã được thay thế.
- Hiểu rủi ro **hai request refresh đồng thời**, retry sau timeout và các cửa sổ ân hạn không được thiết kế chặt.
- Phân biệt **rotation** với **sender-constrained refresh token** bằng DPoP/mTLS khi được hỗ trợ.
- Thiết kế endpoint làm mới với client binding, scope/audience, TTL, lưu trữ, atomic update và audit an toàn.
- Viết ma trận kiểm thử để kiểm tra reuse detection, phản ứng thu hồi và ảnh hưởng đến access token đang còn hạn.

## 2. Refresh token khác access token ở đâu?

| Loại token | Bên sử dụng | Bên nhận | Mục đích | Rủi ro khi bị lấy cắp |
|---|---|---|---|---|
| **Access token** | OAuth client | **Resource server** (API) đúng audience | Gọi API trong phạm vi quyền được cấp | Bên khác dùng API khi token còn hiệu lực |
| **Refresh token** | OAuth client | **Authorization Server/token endpoint** | Xin access token mới theo grant đã cấp | Bên khác có thể duy trì hoặc tái tạo khả năng truy cập API |
| **ID token** (OIDC) | OIDC client | Client xác minh đăng nhập | Mô tả kết quả xác thực người dùng | Lộ dữ liệu danh tính hoặc bị lạm dụng nếu client/API xử lý sai mục đích |

**JWT hay opaque** là cách biểu diễn credential, không phải mục đích của credential. Refresh token thường được tạo dưới dạng chuỗi opaque ngẫu nhiên, nhưng một triển khai có thể dùng cấu trúc khác; client **không nên giải mã hay tự suy quyền** từ refresh token. AS phải xác minh token theo đúng hợp đồng.

Một điểm về ngữ nghĩa: access token có thể mang claim `scope`, `aud`, `sub`, `iss`, `exp`; refresh token phải được AS **ràng buộc với client và grant** để nó không trở thành một credential xin quyền tùy ý.

### 2.1. Vì sao access token ngắn hạn vẫn chưa đủ?

~~~text
10:00   AS cấp A1 (15 phút) + R1 (vòng đời dài hơn)
10:05   Kẻ tấn công lấy được R1
10:15   A1 hết hạn
10:16   Kẻ tấn công dùng R1 xin A2
10:31   A2 hết hạn
10:32   Nếu R1 tiếp tục được dùng -> xin A3, A4, ...
~~~

Thời gian trong ví dụ chỉ nhằm giải thích. Mức độ lạm dụng thực tế phụ thuộc loại client, grant, chính sách hạn dùng, xác thực client, sender constraint và cơ chế chống replay.

**Giới hạn TTL access token giúp thu hẹp thời gian sử dụng của từng access token**, nhưng muốn hạn chế việc tạo thêm token phải bảo vệ refresh token và quá trình cấp mới.

### 2.2. Refresh token không dành cho resource server

Sai:

~~~http
GET /api/orders/order-721 HTTP/1.1
Host: orders.example.com
Authorization: Bearer <REFRESH_TOKEN>
~~~

Orders API phải **từ chối refresh token** vì sai loại credential/mục đích. Refresh token chỉ được trình đến token endpoint của AS qua kênh bảo vệ, không đưa vào query string, log hay API nghiệp vụ.

## 3. Cơ chế tấn công replay hoạt động thế nào?

Một bearer refresh token có thể được dùng bởi bên đang giữ đúng giá trị chuỗi, trừ khi AS còn yêu cầu bằng chứng khác. Các nguồn lộ thường gặp gồm:

- **XSS** hoặc mã bên thứ ba trên browser truy cập được kho token.
- **Malware** trên thiết bị, bản sao lưu ứng dụng hoặc thiết bị bị xâm phạm.
- Refresh token bị ghi vào **log, telemetry, crash report, file debug, CI/CD**.
- Token bị đưa vào **URL/query string**, email, chat hoặc cấu hình bị commit vào repository.
- **Client secret/private key** bị lộ ở confidential client khiến bên khác có thêm khả năng vượt qua client authentication.
- Kênh truyền hoặc secret manager được cấu hình sai.

Token bị lộ không đồng nghĩa cuộc tấn công đã thành công. Nếu refresh token được **ràng buộc với client** và client phải xác thực bằng bí mật/khóa chưa lộ, bên chỉ có refresh token có thể không đổi được token. Với public client, `client_id` là **định danh chứ không phải bằng chứng bí mật**, nên cần các cơ chế phù hợp như **rotation** hoặc **sender constraint**.

### 3.1. Ví dụ một refresh token bị dùng lại

~~~mermaid
sequenceDiagram
    actor A as Alice
    participant C as Client hợp lệ
    participant AS as Authorization Server
    participant X as Bên giữ token bị lộ
    A->>C: Đăng nhập và ủy quyền
    AS-->>C: Access token A1 + refresh token R1
    Note over X: R1 bị lộ qua một đường không an toàn
    C->>AS: Refresh bằng R1
    AS->>AS: Kiểm tra R1 và đánh dấu đã dùng
    AS-->>C: Access token A2 + refresh token R2
    X->>AS: Thử refresh bằng R1 đã dùng
    AS->>AS: Phát hiện sử dụng lại R1
    AS->>AS: Thu hồi active token family theo policy
    AS-->>X: invalid_grant, không cấp token
    C->>AS: Thử refresh bằng R2
    AS-->>C: Từ chối; yêu cầu ủy quyền lại
~~~

Trong ví dụ, **rotation và phát hiện reuse** khiến lần dùng lại `R1` trở thành tín hiệu bất thường, từ đó AS có thể chặn toàn bộ chuỗi refresh token liên quan.

### 3.2. Không thể luôn biết ai là bên tấn công

Trường hợp nguy hiểm hơn: **kẻ tấn công gửi `R1` trước**.

~~~text
T0: AS đã cấp R1 cho client.
T1: Kẻ tấn công biết R1 và gửi refresh request trước.
T2: Nếu các kiểm tra khác đều đạt, AS cấp R2 cho request đầu tiên.
T3: Client hợp lệ gửi R1, bị phát hiện là reuse.
T4: AS vô hiệu hóa refresh token family theo policy.
~~~

AS **không thể suy ra** request đầu tiên là của người hợp lệ chỉ từ việc nó đến trước. Replay detection giúp **phát hiện cạnh tranh sử dụng** và cắt khả năng tiếp tục refresh, nhưng không đảm bảo bên tấn công chưa từng nhận access token hoặc truy cập API trong khoảng trước khi bị chặn.

**Phát hiện reuse là tín hiệu nghi ngờ bị lộ credential, không phải chứng minh chắc chắn chủ thể nào đã đánh cắp.** Request trùng có thể phát sinh từ lỗi retry hoặc nhiều tab của client.

## 4. Rotation: thay refresh token sau mỗi lần sử dụng

**Refresh token rotation** là cơ chế AS **phát hành refresh token mới mỗi khi làm mới thành công và làm mất hiệu lực refresh token vừa được dùng**.

Vòng đời minh họa:

~~~text
R1 (ACTIVE)
  |
  +-- refresh thành công --> R1 (USED), R2 (ACTIVE)
                                    |
                                    +-- refresh thành công
                                         --> R2 (USED), R3 (ACTIVE)
~~~

Một request cố dùng lại `R1` hoặc `R2` sau khi chúng đã được thay thế sẽ bị từ chối và được xử lý theo chính sách phát hiện replay.

### 4.1. Token family là gì?

**Token family** là cách triển khai thường dùng để biểu diễn **chuỗi refresh token phát sinh từ cùng một grant/phiên**. Đây là **khái niệm thiết kế trong AS**, không phải một trường chuẩn bắt buộc của OAuth 2.0.

Ví dụ metadata phía AS:

~~~json
{
  "family_id": "fam-example-501",
  "grant_id": "grant-example-881",
  "client_id": "shop-web",
  "subject_id": "alice-123",
  "status": "ACTIVE",
  "absolute_expires_at": "2030-02-01T00:00:00Z",
  "current_refresh_token_id": "rt-003",
  "generation": 3
}
~~~

Đây là **metadata minh họa**, không phải payload refresh token và không phải schema bắt buộc. AS có thể lưu quan hệ parent–child, version/grant state hoặc cấu trúc khác miễn đảm bảo phát hiện token cũ đã dùng.

### 4.2. Các trạng thái hữu ích

| Trạng thái | Ý nghĩa | Có được dùng để xin token mới? |
|---|---|---|
| **ACTIVE** | Token hiện hành, chưa dùng và còn hiệu lực | Có thể, nếu các kiểm tra client/grant/policy đều đạt |
| **USED / ROTATED** | Token đã được đổi thành token kế tiếp | **Không**; request dùng lại là tín hiệu replay |
| **REVOKED** | Token hoặc family bị thu hồi theo chính sách | Không |
| **EXPIRED** | Token hết hạn theo absolute/idle lifetime | Không |
| **COMPROMISED** (nếu dùng) | Family bị đánh dấu nghi bị lộ | Không, trừ cơ chế khôi phục riêng được xác thực lại |

Nhiều thiết kế dùng **một token ACTIVE duy nhất cho mỗi family**. Khi phát hiện reuse của token đã thay thế, AS thường **vô hiệu hóa token hiện hành của family** để không bên nào tiếp tục dùng chuỗi đó.

### 4.3. Vì sao phải lưu dấu vết token cũ?

Nếu AS **xóa ngay mọi bản ghi R1** sau khi cấp R2, request dùng lại R1 có thể trông giống một token không tồn tại. AS sẽ thiếu thông tin để liên kết sự kiện đó với family đang hoạt động và **khó phát hiện replay theo family**.

Nên giữ thông tin nhận diện/verifier của token đã dùng trong khoảng thời gian cần thiết theo chính sách retention để:

- Xác định nó từng hợp lệ và thuộc family nào.
- Phân biệt **reuse của token cũ** với **giá trị token ngẫu nhiên chưa từng cấp**.
- Thu hồi family liên quan và tạo audit event.

Không cần lưu **refresh token thô**. Có thể lưu định danh lookup, hash/HMAC bảo vệ của token ngẫu nhiên đủ entropy, trạng thái, family_id và metadata cần thiết. Dữ liệu cũ phải được giữ với TTL và chính sách xóa phù hợp.

## 5. Atomicity: chống hai request refresh cùng thành công

Một sai lầm nghiêm trọng là:

~~~text
Thread A: đọc R1 -> thấy ACTIVE
Thread B: đọc R1 -> thấy ACTIVE
Thread A: cấp R2, đánh dấu R1 USED
Thread B: cấp R3, đánh dấu R1 USED
~~~

Nếu không có cơ chế đồng bộ, **hai token con khác nhau** có thể được phát hành từ một refresh token. Điều này phá vỡ giả định single-use và làm phức tạp phát hiện replay.

### 5.1. Cập nhật trạng thái phải có tính nguyên tử

Giải pháp thường dùng:

- Transaction DB kết hợp **row-level locking** cho family/grant.
- **Compare-and-swap**: chỉ chuyển trạng thái từ ACTIVE sang USED nếu trạng thái hiện tại vẫn ACTIVE.
- Unique constraint hoặc version number bảo đảm không có hai token con ACTIVE hợp lệ trong cùng family.
- Tạo token mới, ghi trạng thái và commit **như một giao dịch nhất quán**; nếu thất bại phải rollback thay vì lưu trạng thái nửa chừng.

Ví dụ SQL minh họa một điều kiện one-time:

~~~sql
UPDATE refresh_tokens
SET status = 'USED',
    used_at = CURRENT_TIMESTAMP
WHERE token_hash = :verified_token_hash
  AND status = 'ACTIVE'
  AND expires_at > CURRENT_TIMESTAMP;
~~~

Chỉ **một transaction** được phép chuyển một row từ ACTIVE sang USED. **Số hàng cập nhật** là một tín hiệu để quyết định request có thể tiếp tục; nhưng để bảo đảm cả token con và family state nhất quán, vẫn cần transaction và các ràng buộc bổ sung.

### 5.2. Đọc lại trạng thái sau khi khóa

Một triển khai sử dụng family lock cần:

1. Tìm metadata liên quan bằng token đã được xử lý an toàn.
2. Khóa row family/grant theo transaction.
3. **Đọc lại** trạng thái token và family sau khi có khóa, không tin kết quả đọc trước khóa.
4. Nếu token đã USED, ghi sự kiện replay, thu hồi family theo policy rồi trả `invalid_grant`.
5. Nếu token ACTIVE, xác minh client/grant/scope và giới hạn thời gian.
6. Đánh dấu token cũ USED và tạo token mới ACTIVE trong transaction.
7. Commit xong mới trả credential mới cho client.

Với lưu trữ phân tán, nhiều vùng hoặc replication bất đồng bộ, chỉ lock ở một node có thể không bảo đảm single-use toàn hệ thống. Cần nguồn trạng thái có tính nhất quán đủ mạnh hoặc cơ chế kiểm soát cạnh tranh tương đương.

## 6. Retry, timeout và nhiều tab: replay không luôn là xâm nhập

Giả sử client gửi `R1`; AS đã commit phát hành `R2`, nhưng HTTP response bị mất vì mạng đứt. Client **không biết R2**, nên retry bằng `R1`. Theo mô hình rotation thuần túy, lần retry là **reuse của token đã dùng** và có thể khiến toàn family bị thu hồi.

Một tình huống khác: hai tab cùng thấy access token sắp hết hạn và cùng gửi refresh request bằng R1.

~~~mermaid
sequenceDiagram
    participant T1 as Tab A
    participant T2 as Tab B
    participant AS as Authorization Server
    T1->>AS: refresh(R1)
    T2->>AS: refresh(R1)
    AS->>AS: Xử lý một request trước, R1 chuyển USED
    AS-->>T1: A2 + R2
    AS->>AS: Request còn lại thấy R1 USED
    AS-->>T2: invalid_grant hoặc phản ứng replay theo policy
~~~

Điều này cần được xử lý ngay từ thiết kế; nếu không, người dùng có thể bị đăng xuất liên tục dù không có kẻ tấn công.

### 6.1. Giảm đua tranh ở client

- Dùng **single-flight refresh**: trong một phiên, các request cùng chờ một Promise/operation refresh thay vì gửi nhiều yêu cầu.
- Với nhiều tab, cân nhắc **BroadcastChannel**, leader election, shared worker hoặc cơ chế phối hợp phù hợp; vẫn phải thiết kế an toàn trước XSS và lỗi đồng bộ.
- Trong BFF, giữ token/refresh operation ở backend để có một điểm điều phối; với nhiều instance BFF, cần lock hoặc trạng thái chia sẻ đáng tin cậy.
- Chủ động refresh trước khi access token hết hạn trong một khoảng dự phòng nhỏ, nhưng **không phát refresh song song**.
- Khi refresh bị từ chối, xóa trạng thái credential không hợp lệ và chuyển người dùng sang luồng đăng nhập/ủy quyền lại; tránh retry vô hạn.

### 6.2. Server có nên cho phép grace period?

Một số hệ thống chọn **cửa sổ ân hạn (grace period)** cho các retry do lỗi mạng. Đây là **trade-off bảo mật**, không phải cơ chế OAuth bắt buộc.

Nếu AS đơn giản "cho R1 dùng lại trong 30 giây và luôn cấp token mới", kẻ có R1 có thể khai thác khoảng đó. Thiết kế như vậy **làm yếu phát hiện replay**.

Nếu thật sự cần retry/idempotency:

1. Đặt yêu cầu rõ ràng: loại client, độ tin cậy mạng, mức rủi ro.
2. Ràng buộc retry với **bằng chứng client/sender** thích hợp; một bearer token cũ **một mình** không đủ nhận diện đây là retry hợp lệ.
3. Tránh tạo thêm các token con độc lập từ một token cũ.
4. Giới hạn thời gian retry rất hẹp, có audit và phân tích khả năng lạm dụng.
5. Không gọi mọi reuse là "retry an toàn"; khi không chứng minh được, ưu tiên từ chối và xử lý nghi lộ token.

Một idempotency key do public client tự gửi **không tự trở thành bằng chứng chống attacker** nếu attacker có thể sao chép hoặc đoán các dữ liệu đó. Phải đánh giá threat model trước khi cho phép trả lại credential trên request lặp.

## 7. Sender-constrained refresh token: chứng minh bên gửi giữ khóa

Rotation phát hiện việc refresh token bị dùng lại; **sender constraint** cố ngăn bên chỉ lấy được token sử dụng nó. Một refresh token ràng buộc với khóa/chứng chỉ có thể yêu cầu request làm mới chứng minh quyền sở hữu vật liệu mật mã tương ứng.

### 7.1. DPoP

Với **DPoP (RFC 9449)**, client dùng một khóa bất đối xứng để tạo **proof JWT** cho request tới token endpoint. Khi AS cấp refresh token được ràng buộc với khóa DPoP, các lần refresh sau phải kèm proof hợp lệ theo quy tắc của profile.

AS có thể cần kiểm tra:

- Chữ ký proof và public key tương ứng.
- HTTP method (`htm`) và URI (`htu`) theo quy tắc DPoP.
- Thời gian (`iat`), `jti` và các cơ chế chống proof replay.
- Nonce khi AS yêu cầu theo DPoP.
- Sự khớp giữa **khóa DPoP của request** và **ràng buộc đã lưu cho refresh token**.

**DPoP proof không phải access token** và cũng không thay refresh token. Nó là bằng chứng bổ sung để chứng minh bên gửi nắm khóa liên quan.

### 7.2. mTLS và ràng buộc certificate

Một AS có thể xác thực client qua mTLS và thiết kế refresh token gắn với credential/client hoặc chứng chỉ theo cơ chế được hỗ trợ. Việc ràng buộc phải được **AS thực thi ở lần refresh**, không chỉ kiểm tra có kết nối HTTPS.

Phân biệt:

- **TLS thông thường:** bảo vệ đường truyền nhưng không nhất thiết chứng minh cùng client ở các lần refresh.
- **mTLS client authentication:** client chứng minh quyền sở hữu private key của chứng chỉ khi kết nối.
- **Sender-constrained token:** AS/RS còn kiểm tra token có bị ràng buộc với khóa/chứng chỉ của bên gửi theo đúng profile hay không.

### 7.3. So sánh rotation và sender constraint

| Biện pháp | Mục tiêu chính | Giới hạn |
|---|---|---|
| **Refresh rotation** | Phát hiện token cũ bị dùng lại, cắt family khi nghi replay | Kẻ tấn công có thể dùng token trước client thật; retry hợp lệ có thể gây reuse |
| **Sender-constrained refresh token** | Cản bên chỉ có chuỗi token nhưng không có khóa/chứng chỉ dùng lại | Không bảo vệ nếu cả token và key bị lộ hoặc bị sử dụng ngay trên thiết bị bị kiểm soát |
| **Client authentication** | Xác thực confidential client ở token endpoint | Không thay thế đầy đủ bảo vệ public client; có thể bị vượt nếu client secret lộ |
| **TTL và revocation** | Giảm khoảng thời gian token tồn tại và ngừng cấp token mới | Không tự chứng minh người giữ credential là đúng bên |

Theo **OAuth 2.0 Security Best Current Practice (RFC 9700)**, với refresh token được cấp cho **public client**, AS phải dùng **sender-constrained refresh token hoặc refresh token rotation** để phát hiện/ngăn replay theo profile. Kết hợp cả hai có thể đem lại phòng thủ sâu hơn khi hệ thống hỗ trợ, nhưng không nên mặc định triển khai nào cũng có các tính năng đó.

**PKCE bảo vệ authorization code exchange**, không tự biến một refresh token đã cấp thành sender-constrained token ở các lần làm mới sau.

## 8. Bảo vệ refresh token theo loại client

### 8.1. SPA/browser

Browser chịu rủi ro XSS và script bên thứ ba; việc giữ refresh token trong JavaScript hoặc một kho như localStorage có thể tăng bề mặt lộ credential. Các lựa chọn kiến trúc:

- **Backend-for-Frontend (BFF):** browser sử dụng session cookie có cấu hình bảo vệ, backend giữ access/refresh token trong kho phía server.
- Nếu public browser client trực tiếp giữ refresh token, AS cần rotation hoặc sender constraint theo yêu cầu bảo mật; client giảm phơi lộ token, phối hợp refresh và xử lý reuse.
- Hạn chế script bên thứ ba, áp CSP phù hợp, phòng chống XSS và bảo vệ nguồn tải code.
- Không đưa refresh token vào URL, query string, fragment, WebSocket URL, frontend log hoặc telemetry.

BFF cần phòng chống **CSRF, session fixation, XSS gây hành động trái phép**, bảo vệ cookie với Secure, HttpOnly, SameSite phù hợp và kiểm tra authorization phía server. `HttpOnly` giúp giảm JavaScript đọc cookie nhưng không tự chặn mọi hành động dưới phiên người dùng.

### 8.2. Mobile/native

- Lưu refresh token trong cơ chế bảo vệ credential của hệ điều hành khi có thể, ví dụ keychain/keystore.
- Dùng **Authorization Code + PKCE** với redirect/deep link theo quy tắc native app và bảo vệ callback.
- Không nhúng client secret dài hạn rồi tự nhận là confidential client; phần mềm phát cho người dùng có thể bị phân tích.
- Cân nhắc ràng buộc khóa bằng DPoP hoặc khả năng sender constraint khác nếu AS/client hỗ trợ.
- Khi người dùng đăng xuất hoặc thiết bị bị mất, thu hồi grant/device session theo chính sách.

Một thiết bị bị root/jailbreak hoặc bị malware điều khiển có thể làm giảm hiệu quả của kho bí mật; không có giải pháp lưu trữ nào tuyệt đối chống được việc thiết bị chủ động bị xâm phạm.

### 8.3. Backend/confidential client

- Xác thực client với token endpoint theo phương thức đã đăng ký như client secret được bảo vệ, private_key_jwt hoặc mTLS.
- Ràng buộc refresh token với **đúng client và grant**, không dùng token của client A tại client B.
- Giữ secret trong secret manager/kho khóa, giới hạn theo workload/môi trường, dùng TLS và redaction.
- Phối hợp refresh qua nhiều instance để tránh request dùng lại token cũ.
- Nếu workload chỉ dùng **Client Credentials Grant**, thông thường không cần cấp refresh token; client có thể xác thực lại để xin access token mới.

## 9. Policy vòng đời và thu hồi

Refresh token thường có vòng đời dài hơn access token, nên cần kiểm soát nhiều mốc:

| Giới hạn | Ý nghĩa | Rủi ro nếu thiếu |
|---|---|---|
| **Absolute lifetime** | Hạn tối đa của grant/token family từ lúc được cấp | Rotation lặp lại có thể duy trì quyền vô thời hạn |
| **Idle timeout** | Thu hồi khi refresh token/phiên không được dùng trong một khoảng | Credential không dùng vẫn sống quá lâu |
| **Per-token expiry** | Mỗi refresh token cá thể có thể có hạn riêng | Token bị lộ còn cơ hội thử lại lâu |
| **Client/grant binding** | Token thuộc đúng client, subject và phạm vi cấp quyền | Token bị dùng sai ứng dụng hoặc nâng quyền |
| **Revocation/logout** | Dừng các lần phát hành mới khi đăng xuất, đổi mật khẩu, khóa tài khoản, hoặc phát hiện replay | Bên khác có thể tiếp tục xin access token |
| **Token family state** | Theo dõi token hiện hành/đã dùng và sự kiện reuse | Không biết token cũ bị phát lại |

Một policy tốt sẽ không cho phép rotation kéo dài **absolute lifetime** ngoài giới hạn ban đầu mà không có bước ủy quyền lại, nếu đây là yêu cầu an toàn của sản phẩm.

### 9.1. Rotation không tự mở rộng scope

Theo RFC 6749, refresh request không được xin phạm vi **rộng hơn grant đã cấp ban đầu**. Ví dụ:

~~~text
Granted: orders:read
Refresh request: orders:read orders:delete
=> AS không được cấp thêm orders:delete chỉ vì R1 hợp lệ.
~~~

AS phải áp:

- Quyền client/grant đã cấp.
- Scope được phép tại thời điểm refresh (có thể bị thu hẹp do policy).
- Audience/resource đã được cho phép; không tự chấp nhận resource khác.
- Trạng thái của user/tenant/workload và các yêu cầu ủy quyền lại khi cần.

Nếu cần scope mới, client phải đi qua quy trình cấp quyền thích hợp. **Refresh rotation là bảo vệ credential; scope migration là thay đổi quyền.**

### 9.2. Thu hồi refresh token khác thu hồi access token

Giả sử R1 bị replay và AS thu hồi family. Điều này chặn các lần **xin access token mới** bằng refresh token family đó. Nhưng access token A2 đã phát hành có thể:

- Tiếp tục được chấp nhận đến `exp` nếu là **JWT xác minh offline** và RS không kiểm tra trạng thái bổ sung.
- Bị từ chối sớm hơn nếu RS dùng **opaque token introspection**, denylist/session version hoặc cơ chế thu hồi phù hợp.

Vì vậy, phản ứng với refresh replay cần xét cả **quyền truy cập đang còn sống** ở resource server. Chỉ thu hồi R2 không có nghĩa mọi dữ liệu đã bị truy cập trước đó có thể lấy lại.

## 10. Thiết kế token endpoint để không cấp token khi replay

Một request refresh OAuth 2.0 điển hình:

~~~http
POST /oauth2/token HTTP/1.1
Host: login.example.com
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token=<REFRESH_TOKEN>&client_id=shop-web
~~~

Đây chỉ là request của **public client minh họa**. Với confidential client phải có **client authentication** đúng phương thức đã đăng ký, thường trong header hoặc bằng client assertion/certificate. `client_id` một mình không xác thực confidential client.

### 10.1. Thứ tự kiểm tra tại AS

1. Yêu cầu được gửi qua HTTPS, có body đúng định dạng; không nhận refresh token ở query string.
2. Xác thực confidential client hoặc nhận diện và ràng buộc public client theo profile.
3. Kiểm tra grant type refresh_token được phép cho client.
4. Xác minh refresh token an toàn, tìm grant/family và kiểm tra nó thuộc đúng client.
5. Với sender-constrained token, kiểm tra proof/khóa/chứng chỉ gắn với token.
6. Kiểm tra trạng thái token và family, absolute/idle expiry, revoked/compromised state.
7. Kiểm tra subject/client vẫn được phép làm mới theo chính sách; scope/audience không vượt quyền.
8. **Tiêu thụ token cũ và tạo token mới nguyên tử** nếu dùng rotation.
9. Nếu token đã được thay thế được dùng lại, ghi nhận replay, thu hồi family theo policy và không cấp credential mới.
10. Trả response an toàn qua HTTPS, header chống cache và không ghi token thô vào log.

Mọi request đều cần được giới hạn tài nguyên và giám sát phù hợp; **rate limit không thay thế rotation hoặc sender constraint**.

### 10.2. Pseudocode Java: xử lý family an toàn

Các kiểu `RefreshTokenStore`, `RefreshFamily`, `ClientContext`, `RefreshGrant` và `TokenIssuer` dưới đây là **kiểu khái niệm của ứng dụng**, không phải class của Spring Security có sẵn.

~~~java
// Pseudocode: tất cả thay đổi liên quan đến family nằm trong transaction.
TokenResponse refresh(
        ClientContext client,
        String presentedRefreshToken,
        Set<String> requestedScopes) {

    require(client.isAllowedGrant("refresh_token"));

    String verifier = tokenVerifier.secureLookupKey(presentedRefreshToken);
    RefreshMetadata metadata = refreshStore.lookup(verifier);
    if (metadata == null) {
        throw new InvalidGrantException();
    }

    RefreshOutcome outcome = transaction.run(() -> {
        RefreshFamily family = refreshStore.lockFamily(metadata.familyId());
        RefreshTokenRecord oldToken =
            refreshStore.findTokenRecordForUpdate(verifier);

        require(family.belongsTo(client));
        clientProofPolicy.verifyBinding(client, family);

        // Sau khi có lock, ĐỌC LẠI trạng thái hiện tại.
        if (oldToken.isUsedOrRotated()) {
            refreshStore.revokeFamily(family.id(), "suspected-replay");
            audit.recordRefreshReuse(family.id(), client.id());
            // Trả kết quả để transaction COMMIT việc thu hồi.
            return RefreshOutcome.replayDetected();
        }

        require(oldToken.isActive());
        require(family.isActiveAndWithinLifetime());
        require(grantPolicy.allowsRefresh(family, client, requestedScopes));

        IssuedCredentials next = tokenIssuer.issueWithinGrant(
            family.grant(), requestedScopes
        );

        refreshStore.markUsed(oldToken.id());
        refreshStore.storeNextActiveToken(
            family.id(), next.refreshTokenVerifier()
        );
        audit.recordRotation(family.id(), client.id());
        return RefreshOutcome.success(next.toOAuthResponse());
    });

    // Chỉ trả lỗi SAU khi transaction đã commit trạng thái thu hồi.
    if (outcome.isReplayDetected()) {
        throw new InvalidGrantException();
    }
    return outcome.tokenResponse();
}
~~~

**Cảnh báo khi chuyển thành mã thật:** ví dụ chỉ mô tả trách nhiệm. `RefreshOutcome` là kiểu giả định giúp commit trạng thái thu hồi **trước khi trả lỗi**; nếu ném exception ngay bên trong transaction khiến framework tự rollback, lệnh revoke/audit có thể cũng bị rollback. Một triển khai thật cần ranh giới transaction và kiểu kết quả phù hợp, không trả token khi transaction thất bại.

Cần có cơ chế bảo vệ bí mật verifier, xử lý token không tồn tại, chứng thực client, so sánh an toàn, xác định scope khi request bỏ trống, resource/audience, concurrency và phản ứng sự cố theo chính sách. **Không tự triển khai giao thức OAuth/cryptography từ đầu nếu đã có Authorization Server framework đáng tin cậy.**

### 10.3. Bảo vệ dữ liệu refresh token

Một refresh token opaque có thể được sinh bằng **CSPRNG** với entropy đủ cao. AS nên tránh lưu raw token ở cơ sở dữ liệu nếu không cần thiết. Có thể lưu:

~~~text
lookup_id / token_id không bí mật
token_verifier = HMAC hoặc hash phù hợp cho secret ngẫu nhiên entropy cao
family_id
grant_id, client_id, subject_id
status = ACTIVE | USED | REVOKED
issued_at, expires_at, used_at
sender_binding_reference (nếu có)
~~~

Khi dùng HMAC làm verifier, khóa HMAC phải được giữ riêng và bảo vệ. Khi dùng hash/HMAC, mục tiêu là tránh lộ token thô từ DB và cho phép tra cứu chính xác; việc chọn thuật toán phải dựa trên **entropy của token** và threat model, không coi mã hóa hai chiều hay một chuỗi hash tùy ý là tự an toàn.

### 10.4. SQL và constraint cho một token ACTIVE mỗi family

Ví dụ các bất biến:

~~~text
Mỗi family ACTIVE có tối đa một refresh token ACTIVE.
Mỗi token chỉ chuyển ACTIVE -> USED một lần.
Token con chỉ được tạo sau khi xác thực và tiêu thụ token cha.
Khi family bị REVOKED, mọi refresh thuộc family đều không thể phát token mới.
~~~

Có thể dùng transaction, row lock, optimistic version và unique constraint phù hợp để kiểm soát những bất biến này. Chỉ đặt unique constraint lên token value là **chưa đủ**, vì nó không ngăn hai token con khác nhau được tạo từ cùng một token cha.

## 11. Lỗi OAuth và phản ứng ở client

Khi refresh token không hợp lệ, hết hạn, không thuộc client, đã bị thu hồi hoặc bị dùng lại, token endpoint thường trả lỗi OAuth **`invalid_grant`** theo RFC 6749.

Ví dụ response:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "error": "invalid_grant"
}
~~~

Không nên trả raw token, family ID nhạy cảm, subject hoặc thông tin giúp dò credential trong response. Với **confidential client authentication** thất bại, lỗi phù hợp thường là **`invalid_client`**, có quy tắc status/header riêng theo OAuth.

### 11.1. Client cần làm gì khi nhận invalid_grant?

- Không retry vô hạn cùng refresh token.
- Dừng các request cần credential không còn hiệu lực.
- Loại bỏ access/refresh token liên quan khỏi trạng thái lưu trữ khi phù hợp.
- Đưa người dùng tới luồng đăng nhập/ủy quyền lại hoặc thông báo phiên đã hết hiệu lực.
- Nếu nhiều tab, đồng bộ trạng thái đăng xuất và không để tab khác tiếp tục dùng refresh token cũ.
- Không đưa token vào log khi báo lỗi; chỉ ghi metadata an toàn.

`invalid_grant` có thể có nhiều nguyên nhân (token hết hạn, đã dùng, sai client, thu hồi...), vì vậy client không nên phân tích chi tiết nguyên nhân bảo mật từ thông báo tùy ý. AS có thể ghi lý do chính xác vào **audit nội bộ được bảo vệ**.

## 12. Bảo vệ token response và giảm bề mặt lộ

Một refresh response OAuth minh họa:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "<NEW_ACCESS_TOKEN>",
  "token_type": "Bearer",
  "expires_in": 900,
  "refresh_token": "<NEW_REFRESH_TOKEN>",
  "scope": "orders:read"
}
~~~

Khi rotation được áp dụng, client phải **thay giá trị refresh token cũ bằng token mới theo cách nhất quán** sau response thành công. Không giữ đồng thời R1 và R2 như hai token hợp lệ để luân phiên sử dụng.

Các biện pháp:

1. Dùng TLS, không gửi refresh token vào URL hay query string.
2. Đặt header chống cache và tránh proxy lưu token response.
3. Redact `refresh_token`, `access_token`, header Authorization, client assertions và secret trong log, trace, APM.
4. Không gửi token qua analytics, crash reporting, support ticket hoặc console.
5. Khi lưu token mới, cập nhật trạng thái atomically/consistently giữa các instance của client.
6. Giữ quyền truy cập token trong client theo nguyên tắc **least privilege**.

Một cách lưu refresh token mới sai có thể khiến client mất R2 rồi retry R1, dẫn đến reuse và phiên bị thu hồi. Đó là lý do **client storage và concurrency** là một phần của thiết kế replay protection.

## 13. Reuse detection, revocation và monitoring

### 13.1. Cần quan sát gì?

| Tín hiệu | Ý nghĩa vận hành |
|---|---|
| Refresh thành công theo client/grant | Phát hành bình thường, kiểm tra lưu lượng bất thường |
| Token đã USED được dùng lại | Dấu hiệu replay hoặc client retry/concurrency |
| Nhiều invalid_grant sau rotation | Có thể do client lỗi hoặc cố gắng dùng credential bị đánh cắp |
| Cùng family được refresh từ bối cảnh bất thường | Cần điều tra, không kết luận chỉ dựa trên IP |
| Tỷ lệ refresh cao bất thường | Có thể là vòng lặp ứng dụng, lạm dụng hoặc cấu hình TTL sai |
| Thu hồi family tăng mạnh sau deploy | Có thể là lỗi đồng bộ nhiều tab hoặc ứng dụng mới |
| Token từ issuer/client khác nhau bị nhầm | Có thể là cấu hình client binding hoặc phân tách tenant sai |

Log có thể chứa **requestId, clientId, grant/family identifier đã bảo vệ, loại sự kiện, thời gian, lý do từ chối, policy version**, và thông tin thiết bị/IP được xử lý theo chính sách dữ liệu cá nhân. **Không ghi raw token hoặc HMAC key.**

### 13.2. Phản ứng khi nghi bị lộ token

1. Thu hồi family/grant liên quan để ngừng phát hành thêm access token.
2. Đánh giá các access token đã phát hành và khả năng vô hiệu hóa sớm ở resource server.
3. Yêu cầu user đăng nhập hoặc ủy quyền lại khi cần; cân nhắc xác thực bổ sung cho tài khoản nhạy cảm.
4. Tìm nguyên nhân lộ: XSS, malware, log, lưu trữ, client secret, proxy hoặc lỗi application.
5. Kiểm tra hành động API bất thường đã xảy ra trong khoảng nghi ngờ.
6. Sửa đường lộ credential và giám sát tái diễn.

**Không nên tự động khẳng định tài khoản chắc chắn bị hack** chỉ dựa trên một sự kiện USED-token replay; cần đánh giá cả nguyên nhân do retry/concurrency.

### 13.3. Multi-device và nhiều phiên

Nếu cùng một người đăng nhập trên điện thoại, trình duyệt và desktop, một thiết kế hợp lý là **tách family theo client/session/device grant**. Khi token trên một thiết bị bị replay, chính sách có thể chỉ thu hồi family đó hoặc phạm vi rộng hơn nếu rủi ro yêu cầu. Không mặc định mọi thiết bị dùng một refresh token duy nhất.

Việc thu hồi toàn bộ phiên hay chỉ một family cần được định nghĩa trước, nhất quán với chức năng đăng xuất và quản lý thiết bị.

## 14. Kiểm thử replay protection

### 14.1. Ma trận server-side

| Tình huống | Kỳ vọng |
|---|---|
| R1 ACTIVE, đúng client/grant, chưa hết hạn | Cấp A2 và R2 theo policy; R1 chuyển USED |
| Gửi lại R1 sau khi R2 được cấp | Từ chối, phát hiện reuse, xử lý family theo policy |
| Hai request đồng thời cùng R1 | Tối đa một lần chuyển ACTIVE sang USED và phát family successor |
| Kẻ tấn công dùng R1 trước client thật | Khi request khác dùng lại R1, phát hiện tranh chấp và vô hiệu hóa family; không suy request nào là hợp lệ |
| Client A gửi refresh token của client B | Từ chối, không cấp token |
| Refresh token đã hết absolute lifetime | Từ chối |
| Refresh token vượt idle timeout | Từ chối |
| Family bị REVOKED | Không cấp access token mới |
| Scope grant có `orders:read` nhưng request xin `orders:delete` | Không mở rộng quyền |
| Token dùng ở resource/audience không được cấp | Không cấp quyền vượt chính sách |
| Sender-constrained token không có proof hoặc proof sai khóa | Từ chối |
| DPoP proof dùng lại khi có kiểm tra replay | Từ chối theo policy DPoP |
| Refresh token không tồn tại/không từng cấp | `invalid_grant`, không tiết lộ thông tin family |

### 14.2. Ma trận client-side

| Tình huống | Kỳ vọng |
|---|---|
| 20 API request cùng gặp access token gần hết hạn | Chỉ một refresh operation cho cùng phiên khi có thể |
| Hai tab cùng cần refresh | Cơ chế phối hợp hoặc chính sách xử lý nhất quán; không tạo vòng lặp |
| Network timeout sau khi AS đã commit R2 | Không retry R1 vô hạn; xử lý state và đăng nhập lại khi cần |
| Client nhận R2 thành công | Lưu và sử dụng R2; ngừng dùng R1 |
| Browser reload trong lúc refresh | Không giữ trạng thái token cũ như token vẫn ACTIVE |
| Refresh trả invalid_grant | Dừng retry credential đó; xóa trạng thái phù hợp và yêu cầu authorization mới |
| Ứng dụng đăng xuất | Xóa token phía client và gọi cơ chế revoke của AS theo khả năng |
| Client gặp lỗi server tạm thời | Retry có kiểm soát theo policy, tránh tạo nhiều refresh request đồng thời |

### 14.3. Kiểm thử bảo mật ở hạ tầng

- Refresh token không xuất hiện trong **query, path, browser history, Authorization header của API nghiệp vụ**, support ticket hoặc log.
- Token response có `Cache-Control: no-store` và chính sách bảo vệ transport.
- Secret/khóa DPoP hoặc mTLS được giữ theo trust boundary.
- Hệ thống nhiều instance AS không thể phát hai token con ACTIVE từ một token cha.
- Reuse detection ghi audit event nhưng không phản hồi dữ liệu bí mật cho caller.
- Khi family bị revoke, refresh token successor bị từ chối.
- Access token JWT offline có hành vi sau revoke theo đúng policy đã công bố (có thể còn hạn).
- Metrics và alerts phân biệt client lỗi retry với mẫu lạm dụng theo dữ kiện.

## 15. Các sai lầm phổ biến

| Sai lầm | Vì sao nguy hiểm? | Cách khắc phục |
|---|---|---|
| Refresh token sống lâu và dùng được vô hạn | Kẻ giữ token có thể duy trì quyền | Rotation hoặc sender constraint, lifetime và revocation |
| Rotation nhưng xóa mọi dấu vết R1 | Không phát hiện được token cũ bị replay | Giữ verifier/status/family metadata theo retention |
| Hai request có thể đổi R1 đồng thời | Cấp hai token successor, phá single-use | Atomic transaction, lock/CAS và constraint |
| Dùng grace window rộng, cấp token lại cho R1 | Attacker có cơ hội sử dụng token cũ | Retry có ràng buộc mạnh hoặc từ chối, đánh giá threat model |
| Coi mọi reuse chắc chắn là hacker | Có thể do tab/retry hoặc timeout | Audit, điều tra và giảm race nhưng vẫn bảo vệ family |
| Chỉ giảm access-token TTL | Refresh token bị lộ vẫn có thể xin access token mới | Bảo vệ refresh token tại AS và client |
| Tin client_id của public client là xác thực mạnh | Ai cũng có thể biết client_id | Rotation/sender constraint; phân loại client đúng |
| PKCE được xem là bảo vệ mọi lần refresh | PKCE bảo vệ code exchange, không tự bảo vệ refresh token | Kiểm tra refresh grant/binding riêng |
| Gắn refresh token vào URL hoặc log | Credential bị sao chép | Dùng token endpoint qua POST/TLS, redaction |
| Dùng refresh token gọi resource server | Sai loại credential và ranh giới tin cậy | API chỉ nhận access token đúng profile/audience |
| Refresh token cấp thêm scope mới | Leo thang quyền ngoài grant | Chỉ giữ hoặc giảm scope, cấp quyền mới qua flow được phép |
| Thu hồi R2 rồi cho rằng A2 cũng vô hiệu tức thì | JWT access token offline có thể còn hạn | Thiết kế TTL và revocation tại RS |
| Rotation làm kéo dài phiên không giới hạn | Gia tăng thời gian rủi ro | Absolute lifetime/idle timeout rõ ràng |
| Không phân biệt family theo device/session | Một sự cố ảnh hưởng khó kiểm soát | Tách và quản lý phiên theo grant/policy |

## 16. Bài tập tình huống

### Tình huống A — R1 bị dùng lại

AS đã đổi `R1` thành `R2` cho Alice. Sau đó có request trình lại `R1`.

**Câu hỏi:** Chỉ cần trả invalid_grant cho R1 là đủ chưa?

**Trả lời:** Với mô hình rotation/reuse detection, cần xem đây là tín hiệu nghi bị replay và thực hiện phản ứng đã định — thường vô hiệu hóa refresh token family còn hoạt động, ghi audit và yêu cầu ủy quyền lại. Nếu chỉ từ chối R1 mà để R2 tiếp tục được dùng, bên đang giữ R2 (có thể là attacker gửi trước) vẫn có thể tiếp tục refresh.

### Tình huống B — attacker tới trước

Attacker có `R1`, gửi refresh request và nhận `R2` trước client hợp lệ. Client thật sau đó trình `R1`.

**Câu hỏi:** AS có xác định được request đầu là của attacker chỉ nhờ thứ tự không?

**Trả lời:** Không. Request đầu có thể được cấp token nếu vượt các điều kiện. Việc reuse ở lần sau báo hiệu cạnh tranh sử dụng; AS nên thu hồi family theo policy, đồng thời xem xét các access token đã được cấp.

### Tình huống C — hai tab refresh cùng lúc

Hai tab trình duyệt cùng dùng `R1`. Một tab nhận `R2`, tab còn lại nhận invalid_grant và family bị thu hồi.

**Câu hỏi:** Bảo mật bị sai hay client bị thiết kế thiếu?

**Trả lời:** Có thể client thiếu phối hợp refresh dẫn tới reuse hợp lệ về mặt vận hành. Server vẫn phải bảo vệ rotation; nên dùng single-flight, cơ chế phối hợp tab và lưu trạng thái nhất quán để giảm sự cố.

### Tình huống D — TLS đã bật

Ứng dụng truyền refresh token qua HTTPS nhưng lưu nó trong một file debug công khai.

**Câu hỏi:** TLS đã đủ phòng replay chưa?

**Trả lời:** Chưa. TLS bảo vệ đường truyền, không ngăn token bị đọc từ file/log. Phải bảo vệ lưu trữ và có rotation/sender constraint.

### Tình huống E — refresh token hết hạn nhưng access token còn hạn

AS thu hồi family vì reuse. Một JWT access token đã cấp trước đó còn 10 phút và Orders API xác minh offline.

**Câu hỏi:** Orders API tự động từ chối JWT này không?

**Trả lời:** Không nhất thiết. Nếu Orders API không có kiểm tra trạng thái bổ sung, JWT có thể còn được nhận tới `exp`. Cần thiết kế cơ chế revoke/session state hoặc rút ngắn TTL theo rủi ro.

### Tình huống F — public client có client_id

SPA gửi `client_id=shop-web` cùng refresh token. Đội phát triển nói client_id giúp bảo vệ token khỏi attacker.

**Câu hỏi:** Điều đó đủ không?

**Trả lời:** Không. Client ID là định danh công khai, không phải bí mật chứng minh ứng dụng đang chạy. Public client cần rotation hoặc sender constraint theo chính sách bảo mật hiện đại.

### Tình huống G — refresh xin quyền admin

Client có grant `orders:read`, nhưng gửi `scope=orders:read orders:admin` khi refresh.

**Câu hỏi:** AS có thể cấp vì refresh token hợp lệ không?

**Trả lời:** Không. Refresh request không được mở rộng scope ngoài grant đã cấp; muốn quyền admin phải qua quy trình authorization/phê duyệt mới.

### Tình huống H — DPoP và thiết bị bị xâm phạm

Refresh token được ràng buộc với khóa DPoP trong thiết bị. Attacker chỉ lấy được chuỗi token từ log.

**Câu hỏi:** Attacker có dễ refresh không?

**Trả lời:** Nếu AS thực thi ràng buộc đúng, attacker thiếu khóa có thể không dùng được token. Tuy nhiên, nếu mã độc chiếm được cả token lẫn khả năng sử dụng private key trên thiết bị, sender constraint không còn bảo vệ tuyệt đối; vẫn cần phòng thủ nhiều lớp.

## 17. Ghi nhớ

Hãy theo dõi **ba vòng đời** riêng nhưng liên quan:

1. **Access token:** credential ngắn hạn để gọi resource server, phải kiểm tra issuer, audience, thời gian, scope và quyền theo resource/action.
2. **Refresh token:** credential để xin token mới tại AS, phải gắn với client/grant và được bảo vệ chống chiếm đoạt/phát lại.
3. **Refresh token family/grant:** trạng thái dài hạn theo phiên/thiết bị, cần rotation hoặc sender constraint, expiry, reuse detection và thu hồi.

Quy tắc thao tác cốt lõi:

~~~text
R1 ACTIVE -> refresh hợp lệ -> R1 USED, R2 ACTIVE
R1 USED   -> bị dùng lại   -> nghi replay, chặn family theo policy
R2 ACTIVE -> family revoked -> không thể refresh tiếp
~~~

**Rotation khiến hành vi dùng lại refresh token cũ có thể được phát hiện; sender constraint giúp cản bên không sở hữu khóa sử dụng token.** Cả hai phải được triển khai trong một hệ thống có transaction nhất quán, bảo vệ client, giới hạn grant, TTL, audit và xử lý sự cố.

Token đã cấp có chữ ký đúng và còn hạn vẫn có thể bị lạm dụng nếu refresh token bị đánh cắp. Ngược lại, **thu hồi refresh token không tự thu hồi mọi JWT access token offline đã phát hành**. Phải phối hợp bảo vệ token tại client, token endpoint và resource server để ngăn duy trì quyền truy cập trái phép.

## Tài liệu tham khảo

- [RFC 6749 — The OAuth 2.0 Authorization Framework, Section 6](https://www.rfc-editor.org/rfc/rfc6749#section-6): refresh token grant, ràng buộc client và giới hạn scope.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): yêu cầu refresh token rotation hoặc sender constraint cho public client, reuse detection và bảo vệ grant.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): thu hồi refresh/access token.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): xác minh trạng thái token khi dùng introspection.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): proof-of-possession và token ràng buộc khóa.
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705): mTLS, xác thực client và token ràng buộc chứng chỉ.
- [RFC 9068 — JSON Web Token Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): claims, scope/audience và access token.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): xác minh JWT và các ranh giới tin cậy.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID token, client và refresh flow trong OIDC.
- [OWASP OAuth2 Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html): hướng dẫn bảo vệ luồng OAuth và token.
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): quản lý phiên, lưu trữ credential và bảo vệ session.

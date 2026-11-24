# Refresh token family

Giả sử một ứng dụng di động nhận **refresh token R0** sau khi người dùng đăng nhập. Đến lúc access token gần hết hạn, ứng dụng gửi R0 đến Authorization Server (AS) để nhận **access token mới** và **refresh token R1**. Nếu AS áp dụng *refresh token rotation*, R0 bị vô hiệu hóa, còn R1 trở thành refresh token hợp lệ tiếp theo. Một lúc sau, AS nhận thêm một yêu cầu dùng **R0 đã được sử dụng**. Điều này có thể cho biết R0 đã bị sao chép và đang được phát lại.

**Refresh token family** là cách một hệ thống quản lý **mối quan hệ kế thừa giữa những refresh token được phát hành và luân phiên trong cùng một grant/phiên ủy quyền**. Nhờ giữ được quan hệ R0 → R1 → R2, AS có thể phát hiện lần sử dụng lại token cũ và **thu hồi nhánh token còn hoạt động**, thay vì chỉ từ chối riêng token cũ rồi để kẻ đánh cắp tiếp tục dùng token mới.

Trong chương **Refresh token** của module **Security Token Security Fundamentals**, bài học này đặt refresh token family vào bức tranh lớn hơn: vòng đời OAuth 2.0/OIDC, access token JWT/opaque, các claims như `iss`, `aud`, `scope`, an toàn của token bearer, thu hồi, chống phát lại và xử lý đồng thời. Mục tiêu là thiết kế rotation **an toàn, có trạng thái và kiểm thử được**, không chỉ “phát chuỗi token mới sau mỗi lần refresh”.

## 1. Nhắc lại: access token và refresh token có nhiệm vụ khác nhau

| Đặc tính | Access token | Refresh token |
|---|---|---|
| **Mục đích** | Client xuất trình với **resource server** để gọi API | Client trình cho **authorization server/token endpoint** để xin access token mới |
| **Thời hạn** | Thường ngắn để hạn chế tác động khi bị lộ | Có thể dài hơn, nhưng phải giới hạn thời hạn và vòng đời theo chính sách |
| **Định dạng** | Có thể là JWT hoặc opaque/reference token | Thường là chuỗi opaque khó đoán; cũng có thể dùng định dạng khác theo AS |
| **Thẩm quyền kiểm** | Resource server kiểm chữ ký hoặc introspection, audience, scope và quyền dữ liệu | AS kiểm grant, client/binding, thời hạn, trạng thái, rotation và việc token có bị dùng lại |
| **Nếu bị mất** | Kẻ cầm bearer token có thể dùng trong phạm vi API khi còn hiệu lực | Kẻ cầm refresh token có thể cố xin **nhiều access token mới**, làm kéo dài phiên bị chiếm |
| **Thu hồi** | Theo chiến lược JWT/opaque và resource server | AS có thể ngừng cấp token mới, thu hồi token đang dùng hoặc cả family |

**Không dùng refresh token làm bearer credential tại API nghiệp vụ.** Một Invoice API nhận `Authorization: Bearer <refresh-token>` phải từ chối vì sai loại/mục đích token; chỉ biết token còn sống chưa đủ để cho phép đọc hóa đơn.

OAuth 2.0 không yêu cầu mọi grant đều cấp refresh token. Với `client_credentials`, refresh token thông thường **không nên được cấp** theo RFC 6749; service có thể xác thực lại để xin access token. Ở luồng có người dùng như Authorization Code + PKCE, việc AS có phát refresh token còn phụ thuộc client, grant, chính sách, thời gian, mức độ tin cậy và quyền được cấp.

## 2. Một refresh token family là gì?

Một **family** là tập các refresh token có **cùng nguồn gốc ủy quyền** và nối tiếp nhau qua rotation. Tên gọi và mô hình dữ liệu “token family” là cách triển khai/giải thích phổ biến; **đặc tả OAuth không bắt buộc một claim `family_id` hay một cấu trúc bảng có tên như vậy**.

Ví dụ một family hợp lệ:

~~~text
Authorization grant / session S-17
    |
    +-- R0 (USED/INVALIDATED)
         |
         +-- R1 (USED/INVALIDATED)
              |
              +-- R2 (ACTIVE)
~~~

Với chính sách chỉ có **một refresh token đang hoạt động** trong một family, R2 là token được phép đổi tiếp. R0 và R1 đã dùng **không được phép đổi lần thứ hai**. Chúng có thể vẫn được giữ dưới dạng **record/hash và trạng thái** để nhận biết hành vi sử dụng lại.

### Family không đồng nghĩa với toàn bộ tài khoản

Một người dùng có thể đăng nhập vào:

- Ứng dụng điện thoại cá nhân: **family F-mobile**.
- Trình duyệt trên máy làm việc: **family F-browser**.
- Ứng dụng khác với một OAuth client khác: **family F-partner**.

Các family này có thể độc lập nếu AS thiết kế mỗi family gắn với **một phiên/grant/client hoặc thiết bị**. Nếu F-mobile bị nghi lộ, AS có thể thu hồi **F-mobile** mà không nhất thiết đăng xuất các thiết bị còn lại. Ngược lại, khi xảy ra sự cố tài khoản nghiêm trọng, chính sách có thể thu hồi **mọi family của subject**. Phạm vi thu hồi là quyết định nghiệp vụ/bảo mật, không được suy tự động “một token bị lộ thì mọi người dùng đều bị đăng xuất”.

### Token rotation, token family và replay detection là ba việc khác nhau

1. **Rotation:** dùng refresh token một lần thành công, làm token cũ hết hiệu lực và cấp token kế tiếp.
2. **Family tracking:** lưu mối quan hệ các token kế thừa thuộc cùng grant/phiên, biết token đang hoạt động.
3. **Reuse/replay detection:** nhận một refresh token đã bị dùng trước đó và xử lý theo chính sách, thường đánh dấu family bị xâm phạm và thu hồi refresh token hiện hành.

**Chỉ phát R1 nhưng không vô hiệu R0** không phải rotation an toàn. **Vô hiệu R0 nhưng xóa ngay mọi dấu vết của nó** có thể khiến AS khó phân biệt request dùng lại R0 với một chuỗi ngẫu nhiên không tồn tại. **Từ chối R0 mà không xử lý R1** có thể bỏ sót attacker đã chiếm token kế tiếp.

## 3. Vòng đời bình thường của một family

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng Mai
    participant C as OAuth Client
    participant AS as Authorization Server
    participant DB as Grant/Family Store
    U->>C: Đăng nhập, hoàn tất grant
    C->>AS: Authorization Code + PKCE
    AS->>DB: Tạo family F1, R0=ACTIVE
    AS-->>C: Access token A0 + refresh token R0
    Note over C: A0 gần hết hạn
    C->>AS: grant_type=refresh_token, R0
    AS->>DB: Kiểm R0; R0=USED, phát R1=ACTIVE
    AS-->>C: Access token A1 + refresh token R1
    Note over C: Lưu R1 an toàn, loại bỏ R0
    C->>AS: grant_type=refresh_token, R1
    AS->>DB: R1=USED, R2=ACTIVE
    AS-->>C: Access token A2 + refresh token R2
~~~

Thông thường:

- **Access token A0/A1/A2** là các token truy cập riêng biệt, có thời hạn, audience và scope theo chính sách được AS cấp; chúng không nhất thiết có cùng `jti` hoặc cùng cấu trúc.
- **Refresh token R0/R1/R2** đều thuộc F1, nhưng **chỉ token kế tiếp được đánh dấu ACTIVE** trong mô hình single-active-token.
- Tất cả vẫn phải nằm trong **giới hạn grant ban đầu**, client binding, thời hạn family và quyền hiện hành. **Rotation không tự mở rộng scope hay audience**.
- Nếu AS không trả refresh token mới cho một flow không áp dụng rotation, client cần tuân theo chính sách của AS; không tự suy token cũ luôn dùng lại được.

### Ví dụ HTTP minh họa

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.test
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token=<R0-redacted>
~~~

~~~json
{
  "access_token": "<A1-redacted>",
  "token_type": "Bearer",
  "expires_in": 900,
  "scope": "invoice:read",
  "refresh_token": "<R1-redacted>"
}
~~~

Ví dụ **không** thể hiện phần xác thực client hoặc sender proof, vì cách thực hiện phụ thuộc loại client và AS. Confidential client có thể phải xác thực bằng client secret/private key/mTLS theo cấu hình; public client không có bí mật lưu được an toàn như server, nên cần cơ chế bảo vệ thích hợp như rotation hoặc sender-constrained refresh token.

## 4. Token bị đánh cắp: family phát hiện reuse ra sao?

Giả sử attacker đã lấy được bản sao R0. Hai tình huống cần phân biệt.

### Trường hợp A: client thật đổi R0 trước

~~~mermaid
sequenceDiagram
    autonumber
    participant C as Client hợp pháp
    participant X as Kẻ tấn công
    participant AS as Authorization Server
    participant DB as Family F1
    C->>AS: Refresh bằng R0
    AS->>DB: R0=USED, R1=ACTIVE
    AS-->>C: A1 + R1
    X->>AS: Cố refresh bằng R0 đã lấy cắp
    AS->>DB: Phát hiện R0=USED trong F1
    AS->>DB: F1=COMPROMISED; revoke R1
    AS-->>X: Từ chối, không cấp token
    C->>AS: Thử refresh bằng R1
    AS-->>C: Từ chối; cần xác thực/ủy quyền lại
~~~

Đây là cách **reuse detection** giúp phát hiện một bản sao token đã bị dùng. Vì AS không thể xác định chắc request nào từ người hợp pháp và request nào từ attacker **chỉ dựa trên cùng một bearer refresh token**, phản ứng bảo thủ thường là **thu hồi token còn hoạt động của family** và yêu cầu xác thực lại.

### Trường hợp B: attacker đổi R0 trước

~~~text
Attacker có R0 và xin được R1.
AS: R0=USED, R1=ACTIVE.
Client thật vẫn giữ R0, sau đó gửi R0.
AS: phát hiện reuse R0 -> đánh dấu family bị nghi xâm phạm,
    thu hồi R1 (đang nằm trong tay attacker).
~~~

Điều nguy hiểm ở đây là **attacker có thể nhận access token A1 ngay trong lần refresh đầu**. Thu hồi refresh token family ngăn xin thêm access token, nhưng access token A1 **có thể vẫn được chấp nhận cho đến khi hết hạn** nếu resource server không có cơ chế thu hồi tức thời. Vì vậy cần kết hợp **access-token TTL ngắn, scope/audience hẹp, introspection/denylist khi phù hợp, kiểm quyền từng API và giám sát rủi ro**.

### Một lần reuse có chắc là tấn công không?

Không nhất thiết. Nó cũng có thể do:

- Hai tab hoặc hai instance của cùng client refresh đồng thời.
- Retry sau khi response R1 bị thất lạc.
- Ứng dụng lưu R1 không thành công rồi dùng lại R0.
- Đồng hồ hoặc trạng thái phiên giữa nhiều thiết bị bị đồng bộ sai.

Tuy nhiên, vì AS **không chứng minh được** đây chỉ là lỗi vô hại, thiết kế an toàn không được mặc nhiên bỏ qua reuse. Nên giảm tình huống giả tích cực ở **phía client**, và định nghĩa chính sách xử lý nghi xâm phạm rõ ràng ở **phía AS**.

## 5. State machine: ACTIVE, USED, REVOKED, EXPIRED, COMPROMISED

Không có tập trạng thái bắt buộc chung cho mọi AS; dưới đây là mô hình **minh họa** cho refresh token family có rotation.

| Thực thể | Trạng thái | Ý nghĩa |
|---|---|---|
| **Family** | `ACTIVE` | Grant/phiên có thể tiếp tục được refresh trong chính sách |
| **Family** | `REVOKED` | Bị chủ động thu hồi (logout, admin, revoke endpoint...) |
| **Family** | `COMPROMISED` | Phát hiện reuse hoặc sự kiện rủi ro làm family không còn đáng tin |
| **Family** | `EXPIRED` | Hết absolute lifetime/inactivity timeout |
| **Refresh token record** | `ACTIVE` | Token hiện tại được phép thử refresh, nếu mọi điều kiện khác đạt |
| **Refresh token record** | `USED` | Đã đổi thành công và không được dùng thêm |
| **Refresh token record** | `REVOKED` | Bị thu hồi trước khi sử dụng |
| **Refresh token record** | `EXPIRED` | Hết thời hạn được chấp nhận |

Quy tắc chuyển trạng thái cốt lõi:

~~~text
Khi family=ACTIVE, Rn=ACTIVE và grant hợp lệ:
    consume(Rn) + issue(Rn+1)  // phải nhất quán/atomic
    Rn   -> USED
    Rn+1 -> ACTIVE

Khi family=ACTIVE nhưng nhận Rk=USED:
    family -> COMPROMISED
    revoke tất cả refresh token còn ACTIVE thuộc family
    không phát hành access/refresh token mới

Khi family=REVOKED/COMPROMISED/EXPIRED:
    mọi refresh request thuộc family -> DENY
~~~

**Không cho hai nhánh R1a và R1b cùng ACTIVE** chỉ vì hai request R0 đến cùng thời điểm. Chống race là yêu cầu quan trọng tương đương với kiểm chữ ký/token secret.

### Các bất biến cần kiểm thử

1. **Mỗi family/lineage rotation chỉ có tối đa một refresh token ACTIVE** nếu thiết kế dùng mô hình chuỗi đơn.
2. **Một refresh token chỉ được chuyển ACTIVE → USED một lần**.
3. **Token mới thuộc cùng family/grant và không được tăng quyền vượt phạm vi cho phép**.
4. **Một family không ACTIVE không được phát hành token mới**, kể cả khi chuỗi refresh token đúng.
5. **Reuse của token từng được AS phát hành và đã dùng** phải được phân biệt với “chuỗi token không tồn tại” theo dữ liệu lưu trữ và chính sách.
6. **Không được rollback cờ COMPROMISED** chỉ vì response xử lý reuse trả lỗi cho client.
7. **Trạng thái token và family phải được lưu có tính nhất quán** giữa các instance AS.

## 6. Lưu family như thế nào mà không lưu refresh token dạng rõ?

Mô hình dữ liệu tham khảo:

| Bảng/đối tượng | Trường gợi ý | Chức năng |
|---|---|---|
| `refresh_family` | `family_id`, `subject_id`, `client_id`, `grant_id`, `status`, `current_token_id`, `created_at`, `absolute_expires_at`, `idle_expires_at`, `version` | Phạm vi thu hồi, client/grant binding, thời hạn và token hiện hành |
| `refresh_token_record` | `token_id`, `family_id`, `parent_token_id`, `lookup_digest`, `status`, `issued_at`, `used_at`, `expires_at` | Dòng kế thừa, nhận dạng token được gửi, trạng thái sử dụng |
| `security_event` | `event_id`, `family_id`, `event_type`, `timestamp`, `client_id`, `correlation_id` | Ghi sự kiện rotation/reuse/revoke an toàn |

Tên bảng và cột chỉ để minh họa. `family_id` **không bắt buộc nằm trong token**; có thể hoàn toàn là metadata phía AS. Không được suy trust của family bằng một claim `family_id` chưa xác minh hoặc tự khai từ request.

### Lưu token secret dưới dạng digest

Refresh token dạng opaque nên được tạo bằng **nguồn ngẫu nhiên mật mã mạnh**, có entropy đủ cao, không thể đoán được. AS có thể lưu **digest/HMAC** của chuỗi token làm khóa tra cứu thay vì lưu nguyên token, ví dụ:

~~~text
rawRefreshToken = CSPRNG(32 bytes or more, encoded safely)
lookupDigest = HMAC-SHA256(serverPepper, rawRefreshToken)

database: lookupDigest, familyId, tokenId, state, timestamps
client:   rawRefreshToken (lưu an toàn, không gửi đến resource API)
~~~

`serverPepper` là bí mật phía AS dùng để tăng khả năng bảo vệ nếu kho dữ liệu bị lộ; cần quản trị/luân phiên cẩn thận. Vì token được tạo bằng CSPRNG đủ mạnh, digest mật mã phù hợp có thể dùng cho tra cứu; **không được áp dụng tư duy lưu mật khẩu yếu** hay cho client tự chọn token. Đừng ghi chuỗi refresh token vào log, metric label, message queue không cần thiết hoặc audit event.

**Vì sao phải lưu record của R0 sau khi đã USED?** Nếu xóa ngay R0 khỏi mọi nơi, request phát lại R0 có thể chỉ trông như `invalid_grant` của chuỗi chưa từng tồn tại. Giữ digest và liên kết family **trong thời gian cần thiết theo chính sách** giúp phát hiện reuse. Cần có cơ chế dọn dữ liệu sau khi family/retention kết thúc để không giữ vô hạn.

### JWT refresh token có cần database không?

Không thể chỉ vì refresh token là JWT có chữ ký mà kết luận rotation/reuse detection sẽ **stateless**. Nếu cần biết `R0 đã dùng`, `R1 là token hiện hành` hay `family bị thu hồi`, AS vẫn cần **trạng thái đáng tin** hoặc hệ thống tương đương. JWT tự mô tả thời gian và issuer; nó **không tự chứng minh lịch sử dùng một lần**.

## 7. Đổi token phải atomic trong môi trường nhiều instance

Giả sử AS có hai replica. Cả hai đồng thời nhận R0 và cùng đọc `status=ACTIVE`. Nếu mỗi replica xử lý riêng, chúng có thể cấp **R1a và R1b** đều hợp lệ, phá bất biến family.

Vì vậy thao tác **đánh dấu token cũ, cấp token kế tiếp và cập nhật current pointer** phải được thực hiện bằng cơ chế transaction/compare-and-set có thể xử lý race an toàn. Có thể dùng khóa hàng trong cơ sở dữ liệu, optimistic locking với `version` hoặc một primitive có tính nguyên tử tương đương.

~~~mermaid
sequenceDiagram
    autonumber
    participant C1 as Client request A (R0)
    participant C2 as Client request B (R0)
    participant AS1 as AS replica 1
    participant AS2 as AS replica 2
    participant DB as Shared family store
    C1->>AS1: Refresh R0
    C2->>AS2: Refresh R0
    AS1->>DB: Lock family/token R0
    DB-->>AS1: ACTIVE
    AS1->>DB: R0=USED, create R1=ACTIVE, commit
    AS1-->>C1: Access token A1 + R1
    AS2->>DB: Lock family/token R0
    DB-->>AS2: R0=USED
    AS2->>DB: Mark family COMPROMISED; revoke R1
    AS2-->>C2: invalid_grant
~~~

Kết quả này có thể khiến một client hợp pháp bị yêu cầu đăng nhập lại khi có race, nhưng **không cấp hai nhánh refresh token cùng hợp lệ**. Không giải quyết bằng cách “request trùng cứ cấp một token mới” — như vậy attacker có thể dùng lại refresh token cũ mà không bị phát hiện.

### Pseudocode xử lý refresh token family

~~~text
function refresh(rawRefreshToken, clientProof, requestedScope):
    client = authenticateOrVerifyClientBinding(clientProof)
    tokenRecord = findRecordBySecureDigest(rawRefreshToken)

    if tokenRecord not found:
        return OAUTH_INVALID_GRANT

    begin transaction
        family = lockFamilyForUpdate(tokenRecord.familyId)
        record = lockTokenForUpdate(tokenRecord.tokenId)

        if family.status != ACTIVE:
            decision = DENY

        else if record.status == USED:
            family.status = COMPROMISED
            revokeActiveRefreshTokens(family.id)
            recordSecurityEvent("REFRESH_REUSE", family.id)
            decision = DENY_COMPROMISED

        else if record.status != ACTIVE:
            decision = DENY

        else if not validClientGrantAndExpiry(
                client, family, record, requestedScope):
            decision = DENY

        else:
            child = generateNewHighEntropyRefreshToken()
            record.status = USED
            record.usedAt = now()
            storeChildDigest(child, parentId = record.id,
                             familyId = family.id, status = ACTIVE)
            family.currentTokenId = child.id
            updateFamilyInactivityExpiryWithinAbsoluteLimit(family)
            decision = ALLOW_NEW_TOKEN(child)
    commit transaction

    if decision == DENY or decision == DENY_COMPROMISED:
        return OAUTH_INVALID_GRANT
    return issueAccessTokenAndReturnRefreshToken(decision.child)
~~~

**Đây là mô hình giải thích bất biến, không phải code có thể copy vào production.** Ví dụ trên giản lược thứ tự kiểm bắt buộc và xử lý lỗi của các grant, việc giữ secret token mới cho tới khi response được gửi, cũng như phân tán giao dịch giữa DB và ký access token. Đặc biệt:

- Không để **exception khi trả `invalid_grant` làm rollback** transaction đã ghi `COMPROMISED`.
- Không được lộ cho caller thông tin family cụ thể nếu chưa đủ quyền; lỗi public nên nhất quán.
- Việc xác minh **client binding** và trạng thái grant là bắt buộc, không chỉ tra token theo digest.
- Nếu ký access token hoặc gửi response thất bại sau commit, family có thể đã tiến sang token mới mà client chưa nhận: cần chính sách recovery rõ ràng, không âm thầm cho phép R0 dùng lại vô hạn.
- Nếu hệ thống có các bước ngoài transaction (KMS/HSM, event bus), cần thiết kế consistency/idempotency phù hợp, không được giả vờ một transaction DB bao phủ mọi hệ thống.

### Nên lưu child refresh token thế nào giữa commit và response?

AS có thể tạo chuỗi R1 trong bộ nhớ, lưu **chỉ digest** vào DB rồi trả chuỗi cho client. Nếu process chết sau khi commit nhưng trước khi trả response, AS thường **không thể khôi phục plaintext R1 từ digest**. Đây là một đánh đổi có chủ đích vì bảo mật. Khi thiết kế vận hành, cần lựa chọn xử lý “response bị mất” bằng bước đăng nhập/ủy quyền lại hoặc một cơ chế khôi phục/idempotency **được chứng minh an toàn**, thay vì lưu refresh token plaintext bền vững không cần thiết.

## 8. Race, retry và phản hồi bị mất: lỗi khó nhất của rotation

### Hai tab dùng chung R0

~~~text
Tab A: thấy access token gần hết hạn -> refresh R0
Tab B: cùng thấy access token gần hết hạn -> refresh R0
AS: A thành công -> R1, B là reuse R0 -> revoke family
~~~

Đối với SPA, có thể dùng **single-flight refresh**, phối hợp các tab/process bằng cơ chế thích hợp (ví dụ BFF giữ refresh token phía server, lock/coordination giữa tab, hoặc một token manager duy nhất). Mục tiêu là **một refresh request đang chạy cho mỗi phiên/family**, các caller khác chờ cùng kết quả.

Trên backend, nhiều worker chia sẻ cùng refresh token cũng cần khóa/distributed coordination; khóa chỉ trong bộ nhớ một process **không đủ** nếu nhiều instance sử dụng chung token family.

### Response R1 bị mất trên mạng

~~~text
Client gửi R0 -------> AS
AS commit: R0=USED, R1=ACTIVE
AS gửi A1 + R1 --X--> response thất lạc
Client vẫn chỉ có R0, retry R0
AS thấy R0=USED -> reuse detected
~~~

Với mô hình strict reuse detection, client có thể bị yêu cầu đăng nhập lại dù không có attacker. Đây là **giới hạn của giao thức xoay token một lần khi mạng không đảm bảo**. Không thể vừa phát hiện mọi replay của R0 vừa cho phép mọi retry R0 là vô hại nếu không có **bằng chứng/định danh bổ sung**.

Các chiến lược:

| Chiến lược | Lợi ích | Nguy cơ/điều kiện |
|---|---|---|
| **Strict one-time-use + reauthentication** | Dễ hiểu, ưu tiên phát hiện replay, không cấp lại R1 từ R0 | Có thể gây đăng nhập lại khi response mất hoặc request đua nhau |
| **Single-flight ở client/BFF** | Giảm race do client tự tạo | Không sửa được response mất hoàn toàn hoặc attacker dùng token |
| **Grace period chấp nhận token cũ** | Giảm false positive vì retry gần thời điểm rotation | Nếu không ràng buộc bổ sung, attacker có R0 cũng được lợi từ cửa sổ grace; làm yếu reuse detection |
| **Bounded idempotency theo client/proof đáng tin** | Có thể trả lại **cùng một kết quả** cho retry thật trong khoảng ngắn | Cần client binding, idempotency key khó giả, bảo vệ response/cached secret, chống replay và đánh giá rủi ro |
| **Đăng nhập/ủy quyền lại khi không biết trạng thái** | Khôi phục chain sạch khi bất định | Ảnh hưởng UX, nhưng tránh cứu một family có thể đã bị sao chép |

**Không áp dụng grace period như mẹo mặc định để tránh lỗi.** Một attacker có refresh token R0 có thể khai thác cùng cửa sổ grace, trừ khi AS có bằng chứng đủ mạnh để phân biệt retry hợp lệ. Dù chọn chính sách nào cũng phải kiểm thử race/timeout và xác định cách phản ứng khi phát hiện reuse thật.

### Retry `invalid_grant` không làm token hợp lệ trở lại

Theo OAuth 2.0, token endpoint thường trả `invalid_grant` khi refresh token không hợp lệ, hết hạn, bị thu hồi hoặc không khớp với client. Client **không** nên retry vô hạn bằng cùng refresh token. Đặc biệt, khi đã xảy ra reuse, việc AS đã thu hồi family có thể yêu cầu user **xác thực lại**. `429 Too Many Requests` là chuyện quota khác với `invalid_grant`; client phải phân biệt lỗi và không dùng backoff để tiếp tục gửi token đã bị đánh dấu compromise.

## 9. Một family sống bao lâu? Absolute expiry, idle timeout và logout

Rotation không đồng nghĩa một phiên có thể kéo dài **vô hạn**. Nếu cứ đổi R0 → R1 → R2 mà mỗi token lại được cấp TTL dài mới không giới hạn, một refresh token bị chiếm có thể duy trì một grant quá lâu.

Các mốc nên thiết kế:

| Mốc hoặc sự kiện | Ý nghĩa |
|---|---|
| **Family created_at** | Thời điểm grant/phiên tạo family |
| **Absolute expiration** | Thời hạn tối đa từ lúc tạo family, không tự kéo dài bằng rotation |
| **Inactivity/idle timeout** | Ngừng cho refresh nếu không sử dụng trong một khoảng thời gian theo policy |
| **Refresh token expiration** | Mốc hạn riêng của mỗi Rn; không được vượt giới hạn family/grant |
| **Access token expiration** | Mốc hết hạn của từng access token được cấp, thường ngắn hơn refresh grant |
| **Logout / revoke event** | Chủ động vô hiệu family hoặc toàn bộ phiên liên quan |
| **Account/security policy change** | Mất membership, khóa tài khoản, thay credential hoặc sự kiện rủi ro có thể thu hồi grant |

Ví dụ minh họa (không phải TTL bắt buộc):

~~~text
Family F1 created:      ngày 01
Absolute expiry:        ngày 31
Idle timeout:           07 ngày không refresh
Access token TTL:       15 phút

Ngày 02: R0 -> R1, gia hạn idle deadline (tối đa đến ngày 31)
Ngày 05: R1 -> R2, gia hạn idle deadline (tối đa đến ngày 31)
Ngày 31: family EXPIRED, dù Rn vừa được sử dụng
~~~

Khi AS quyết định scope hoặc quyền người dùng đã bị thu hồi, **refresh tiếp không được tự phục hồi quyền cũ**. Token mới phải dựa trên grant và quyền hiện hành theo policy, không vượt scope/audience ban đầu hoặc cho phép AS cấp. Sự thay đổi `iat` của access token mới **không chứng minh người dùng vừa reauthenticate**; với hành động nhạy cảm, có thể cần xác thực lại theo chính sách OIDC/step-up.

### Logout thiết bị hay logout toàn bộ?

- **Logout một thiết bị:** tìm và revoke family gắn với phiên/thiết bị đó, đồng thời kết thúc session ứng dụng.
- **Logout tất cả thiết bị:** revoke mọi family liên quan subject theo quyền và phạm vi đã xác định.
- **Admin/security revoke:** revoke family sau nghi ngờ theft, thông báo/ghi audit an toàn, yêu cầu đăng nhập lại khi cần.

Revocation của **refresh token family** ngăn cấp access token mới. Nó **không tự bảo đảm** những access token trước đó đã bị vô hiệu ngay lập tức tại mọi resource server. Hệ thống cần chiến lược riêng cho JWT tự xác minh hoặc opaque token/introspection.

## 10. Token family gắn với client, grant, audience và scope ra sao?

Family không phải “chiếc ví” cho phép client biến refresh token thành mọi loại access token.

Khi xử lý một refresh request, AS phải kiểm:

1. **Client được phép dùng refresh token:** xác thực confidential client hoặc kiểm ràng buộc thích hợp với public client, tùy flow.
2. **Refresh token thuộc grant/phiên và client đó**, không được hoán đổi giữa hai OAuth client.
3. **Family và token còn hiệu lực**, chưa hết hạn, chưa revoke/compromise và đúng token hiện hành.
4. **Scope yêu cầu không mở rộng ngoài grant cho phép**; AS có thể cấp scope hẹp hơn theo policy hiện hành.
5. **Resource/audience được xin phù hợp**, nếu hỗ trợ Resource Indicators (RFC 8707) hoặc cơ chế tương đương; không được tự chuyển token thành quyền gọi một API hoàn toàn khác.
6. **Binding/actor nếu áp dụng:** DPoP/mTLS hoặc cơ chế sender-constraining của refresh token phải được kiểm khi dùng.

Ví dụ:

~~~text
F1:
  client = expense-web
  grant scopes = ["invoice:read", "invoice:create"]
  permitted audience = invoice-api

Refresh R2 yêu cầu:
  scope = "invoice:read"         -> có thể hợp lệ
  scope = "invoice:delete"       -> không được tự nâng quyền
  resource = "payment-api"       -> không được tự đổi ngoài grant/policy
~~~

Với **token exchange (RFC 8693)**, việc xin token downstream có audience khác là một loại grant/cơ chế riêng do AS kiểm soát, không đồng nghĩa “chỉ cần cầm refresh token của API A là được cấp token của API B”.

### Refresh token có được gửi đến API downstream không?

Không. Khi service A cần gọi B, nó có thể cần **access token dành cho B** theo cơ chế cấp phát đáng tin cậy. Refresh token dành cho AS, không được relay như bearer token ở B. Tương tự, gateway đổi host/path không đổi `aud` của access token; mỗi resource server cần xác minh audience và scope của token mà nó nhận.

## 11. Sender-constraining: rotation có phải lựa chọn duy nhất?

**Không.** Theo OAuth 2.0 Security Best Current Practice (RFC 9700), **refresh token cấp cho public client cần được sender-constrained hoặc sử dụng refresh token rotation** để phát hiện replay theo các yêu cầu áp dụng. Cả hai phương pháp có mục tiêu giảm tác động của refresh token bị sao chép, nhưng cơ chế khác nhau.

| Cơ chế | Nếu attacker chỉ lấy được chuỗi refresh token | Điều kiện |
|---|---|---|
| **Bearer refresh token không rotation/binding** | Có thể tiếp tục xin access token trong phạm vi grant nếu token còn hiệu lực | Rủi ro cao hơn khi bị lộ |
| **Rotation + family reuse detection** | Token cũ đã dùng bị từ chối và reuse có thể làm thu hồi family | AS giữ trạng thái, kiểm một lần, chống race |
| **DPoP-bound refresh token** | Kẻ có chuỗi token nhưng không có private key tương ứng thường không đổi được | AS phải kiểm DPoP proof và ràng buộc khóa đúng profile |
| **mTLS certificate-bound refresh token** | Chỉ token string không đủ nếu AS đòi chứng chỉ khớp binding | Cần hạ tầng mTLS và AS kiểm đúng certificate binding |
| **Rotation kết hợp sender-constraining** | Có cả kiểm một lần và ràng buộc người gửi | Chi phí/phức tạp cao hơn, phù hợp mức rủi ro |

DPoP và mTLS **không bảo vệ tuyệt đối** nếu attacker chiếm cả khóa/certificate, chạy mã trong chính client hoặc truy cập được cơ chế ký. Đặc biệt, mô hình BFF lưu refresh token phía server giảm khả năng mã JavaScript trong trình duyệt đọc chuỗi token trực tiếp, nhưng **session cookie, XSS, CSRF, kênh BFF và server** vẫn cần bảo vệ.

### Lưu refresh token ở đâu?

- **Backend/BFF:** kho token phía server được kiểm soát truy cập, mã hóa khi cần, không log plaintext; browser chỉ giữ session cookie `Secure`, `HttpOnly`, `SameSite` phù hợp và có chống CSRF.
- **Mobile:** dùng secure storage/keystore theo nền tảng, bảo vệ backup/log; xem xét binding khóa nếu hỗ trợ.
- **SPA chạy hoàn toàn trong trình duyệt:** mọi token JavaScript có thể đọc đều chịu rủi ro XSS; memory giảm một số kiểu tồn tại lâu nhưng không ngăn script độc hại đang chạy. Đánh giá BFF, hạn chế token và bảo vệ XSS trước khi quyết định lưu refresh token.
- **Không đặt refresh token trong URL/query, analytics, local log, crash report hoặc header gửi tới API nghiệp vụ**.

## 12. Vì sao refresh token family không bảo vệ được mọi access token bị đánh cắp?

Hãy tách hai sự cố:

**Sự cố 1 — Kẻ tấn công lấy refresh token R0:** Rotation và family tracking có thể phát hiện sử dụng lại R0 sau khi một bên đã đổi token, từ đó revoke refresh token hiện hành và hạn chế cấp access token tiếp.

**Sự cố 2 — Kẻ tấn công lấy access token A1:** Không cần gọi token endpoint, attacker có thể thử dùng A1 trực tiếp tại resource server. Family tracking ở AS **không nhìn thấy** mọi request dùng A1, vì vậy không tự chặn được request đó.

Các lớp bảo vệ cần bổ sung:

| Lớp | Vai trò |
|---|---|
| **Access token TTL ngắn** | Giảm thời gian token bị lộ còn hữu dụng |
| **Audience và scope tối thiểu** | Giới hạn API/hành động token có thể yêu cầu |
| **Resource-level authorization** | Kiểm owner, tenant, role/permission, trạng thái và field |
| **Opaque introspection / JWT revocation strategy** | Tăng khả năng vô hiệu access token khi có sự cố, có tính đến cache |
| **DPoP/mTLS sender-constrained access token** | Kẻ lấy token string mà không có khóa khó sử dụng tại RS |
| **Rate limiting, reauthentication, fraud monitoring** | Giảm lạm dụng API và tăng bảo đảm cho hành động nhạy cảm |

Nếu logout hoặc family bị revoke nhưng **JWT A1 còn hiệu lực và RS chỉ tự kiểm chữ ký/`exp`**, người dùng có thể vẫn thấy request sử dụng A1 thành công trong thời gian ngắn. Đây là một đặc tính kiến trúc cần được ghi rõ trong chính sách logout/session, không phải lỗi mà rotation tự khắc phục.

## 13. Phản hồi lỗi, audit và phản ứng sự cố

### Phản hồi ở token endpoint

Với refresh token sai/hết hạn/bị revoke hoặc không còn hợp lệ do reuse, OAuth token endpoint thường dùng **HTTP 400** với lỗi **`invalid_grant`**:

~~~http
HTTP/1.1 400 Bad Request
Cache-Control: no-store
Pragma: no-cache
Content-Type: application/json

{"error":"invalid_grant"}
~~~

Không cần trả cho caller các chi tiết như “R0 đã used, R1 hiện đang active” hoặc “family F1 có token_id N”. Những thông tin đó phục vụ audit nội bộ. Nếu client authentication sai, dùng semantics lỗi `invalid_client` phù hợp, không biến thành thông báo tiết lộ token/grant.

Khi gặp `invalid_grant`, client **không retry vô hạn bằng refresh token cũ**, mà phải xử lý phiên không còn hợp lệ và khởi tạo xác thực/ủy quyền lại khi phù hợp. `429 Too Many Requests` là lỗi quota; `invalid_grant` là lỗi grant. Hai trường hợp cần xử lý khác nhau.

### Ghi audit mà không làm lộ token

| Sự kiện | Thông tin nên ghi | Tránh ghi |
|---|---|---|
| Family được tạo | Family ID, client, subject pseudonymous, grant, thời điểm | Plaintext refresh token |
| Rotation thành công | Family ID, parent/child token ID nội bộ, version, timestamp | Token response, header Authorization |
| Reuse detected | Family ID, token ID nội bộ, sự kiện/thời điểm, correlation ID, nguồn đã xác minh | Chuỗi token gửi lại hoặc khóa người gửi |
| Family bị revoke | Phạm vi, lý do, actor thực hiện, audit reference | Secret, dữ liệu nhạy cảm không cần thiết |
| Đăng nhập/ủy quyền lại | Session/family mới được tạo theo policy | Token plaintext hoặc mật khẩu |

Metrics nên dùng nhãn **cardinality thấp** (loại sự kiện, loại client, môi trường), tránh đưa mỗi family/token ID vào nhãn metric. Các ID chi tiết để trong audit store có phân quyền và retention hợp lý.

### Khi phát hiện reuse thật

1. **Đánh dấu family bị nghi xâm phạm** và làm không thể refresh tiếp bằng token hiện hành.
2. **Ghi sự kiện bảo mật** và đánh giá có cần revoke những access token đã phát hành hoặc phiên khác không.
3. **Thông báo/điều hướng xác thực lại** bằng cơ chế tránh tiết lộ thông tin cho attacker.
4. **Kiểm tra nguồn rò rỉ** như XSS, log, storage, ứng dụng di động bị xâm nhập, proxy hoặc malware.
5. **Khắc phục và giám sát**; nếu attacker có cả client secret/private key hoặc quyền điều khiển thiết bị, chỉ tạo family mới không đủ.

Trường hợp reuse có thể là race vô hại, nhưng hệ thống cần biết **vì sao nó xảy ra** trước khi nới lỏng chính sách. Không tắt reuse detection chỉ để giảm ticket hỗ trợ.

## 14. Ma trận kiểm thử refresh token family

| Trường hợp | Đầu vào | Kỳ vọng |
|---|---|---|
| **Refresh hợp lệ** | F1=ACTIVE, R0=ACTIVE, client/grant đúng | Cấp A1/R1; R0=USED, R1=ACTIVE |
| **Refresh tiếp** | F1=ACTIVE, R1=ACTIVE | Cấp A2/R2; R1=USED, R2=ACTIVE |
| **Reuse token cũ** | Dùng R0 sau khi R1 đã cấp | Không cấp token; đánh dấu family theo policy, revoke token hiện hành |
| **Attacker đổi trước** | Attacker dùng R0, client thật dùng R0 sau | Phát hiện reuse, revoke family; có thể phải xử lý A1 đã cấp cho attacker |
| **Hai request đồng thời** | 2 AS replica nhận R0 | Không sinh hai child ACTIVE; xử lý request sau theo policy |
| **Response refresh bị mất** | AS commit R1, client retry R0 | Không âm thầm cấp nhánh mới; phản hồi/recovery theo chính sách |
| **Sai OAuth client** | R0 của client A được trình với client B | Từ chối `invalid_grant` hoặc lỗi phù hợp, không cấp token |
| **Family đã revoke** | R2 có secret đúng nhưng F1=REVOKED | Từ chối |
| **Family hết absolute lifetime** | R2 được dùng sau hạn tối đa | Từ chối dù R2 vừa được tạo gần đây |
| **Family idle timeout** | Lâu không refresh vượt thời hạn | Từ chối và cần đăng nhập lại theo policy |
| **Yêu cầu tăng scope** | Grant chỉ có `invoice:read`, xin `invoice:delete` | Không cấp quyền vượt grant |
| **Yêu cầu sai resource/audience** | Refresh xin token cho API khác không được phép | Từ chối hoặc giới hạn theo policy |
| **Sender proof sai** | DPoP/mTLS token nhưng thiếu khóa/chứng chỉ hợp lệ | Từ chối |
| **Không tìm thấy token** | Token opaque ngẫu nhiên chưa từng phát hành | Từ chối; không gán nhầm family |
| **Lưu digest** | Kiểm DB/log sau rotation | Không chứa refresh token plaintext; record USED còn phục vụ kiểm reuse theo retention |
| **Logout thiết bị** | Revoke F-mobile, F-browser vẫn còn | Chỉ family mục tiêu bị revoke, trừ khi chính sách mở rộng |
| **Logout tất cả** | Revoke mọi family của subject | Mọi refresh sau đó bị từ chối; kiểm access-token lifecycle riêng |
| **Bug rollback** | Nhánh reuse ghi COMPROMISED rồi trả lỗi | Trạng thái COMPROMISED vẫn được commit |
| **Redis/DB lỗi giữa refresh** | Hỏng một bước transaction | Không cấp hai token ACTIVE hay bỏ qua kiểm grant |
| **Token cũ gọi resource server** | Dùng A1 vẫn còn hạn sau revoke F1 | Hành vi đúng theo chính sách access-token revocation đã công bố, không giả định family tự vô hiệu A1 |

### Bài tập tình huống

Người dùng Mai đăng nhập ứng dụng trên điện thoại và laptop. AS cấp:

~~~text
Mobile:  family Fm
         Rm0 -> Rm1 (ACTIVE)

Laptop:  family Fl
         Rl0 (ACTIVE)
~~~

Một attacker đánh cắp **Rm0** từ bản log cũ và gửi request refresh. Cùng lúc, mobile vẫn còn **Rm1**. Sau khi AS kiểm reuse:

**Câu 1: AS cần làm gì với Rm0 và Rm1?**

Rm0 đã dùng không được phát token mới. Với chính sách strict rotation/reuse detection, AS đánh dấu **Fm bị nghi xâm phạm**, revoke **Rm1** và yêu cầu mobile xác thực lại. Không chỉ từ chối Rm0 rồi để Rm1 mặc nhiên tồn tại.

**Câu 2: Rl0 trên laptop có bắt buộc bị thu hồi không?**

**Không mặc nhiên.** Laptop thuộc **family Fl** riêng. Chỉ revoke Fl nếu chính sách logout toàn tài khoản hoặc điều tra cho thấy rủi ro rộng hơn.

**Câu 3: Access token đã được cấp từ Rm1 có tự hết hạn ngay khi Fm bị revoke không?**

**Không nhất thiết.** Phải xét kiến trúc RS kiểm trạng thái access token ra sao: JWT chỉ kiểm offline có thể còn hiệu lực đến `exp`; opaque/introspection hoặc denylist có thể cập nhật sớm hơn.

**Câu 4: Nếu attacker chỉ lấy access token chứ không có refresh token thì family giúp phát hiện không?**

**Không trực tiếp.** Attacker có thể dùng bearer access token tại đúng API trong hạn. Cần kiểm quyền ở RS, giảm TTL/scope/audience, cân nhắc DPoP/mTLS, giám sát và thu hồi access token.

**Câu 5: Nếu hai tab mobile cùng refresh Rm1 và gây reuse, có nên tắt strict rotation không?**

Không phải giải pháp đầu tiên. Nên sửa **single-flight refresh/đồng bộ token**, kiểm AS transaction và định nghĩa chính sách xử lý timeout/race trước khi cân nhắc grace/idempotency có ràng buộc bảo mật.

## 15. Checklist thiết kế refresh token family

1. **Định nghĩa phạm vi family:** Mỗi grant/client/session/thiết bị được tách thế nào? Có bản đồ cho logout một thiết bị và logout tất cả?
2. **Chọn cơ chế chống replay:** Public client dùng rotation hoặc sender-constraining theo BCP; có cần kết hợp cả hai không?
3. **Bảo đảm single-use:** Một refresh token chỉ có một lần đổi thành công; parent bị đánh dấu USED đồng thời child trở thành ACTIVE?
4. **Theo dõi lineage:** Lưu đủ dấu vết parent/child để phát hiện reuse, không giữ token plaintext vô thời hạn?
5. **Thu hồi theo family:** Nhận USED token có revoke active descendants, ghi COMPROMISED bền vững và không tạo grant mới?
6. **Chống race nhiều AS instance:** Có row lock/CAS/transaction/unique constraint phù hợp để không sinh hai child ACTIVE?
7. **Xử lý retry an toàn:** Client có single-flight; mất response R1 có recovery rõ, không chấp nhận grace không kiểm soát?
8. **Ràng buộc grant/client:** Token đúng client và quyền, scope/audience không tự nâng; kiểm sender proof khi áp dụng?
9. **Giới hạn vòng đời:** Có absolute expiry, inactivity expiry, logout/revoke và cleanup trạng thái sau retention?
10. **Không nhầm với access token:** API chỉ nhận access token đúng profile, audience, scope và quyền; thu hồi family không mặc nhiên hủy access token cũ?
11. **Bảo vệ secret:** CSPRNG đủ mạnh, storage/hashing an toàn, BFF/mobile/SPA theo rủi ro, không log refresh token?
12. **Có giám sát và incident response:** Sự kiện reuse, rotation race, revoke, lỗi DB và hành vi đáng ngờ được phân loại, lưu an toàn?
13. **Test nhánh thất bại:** Sai client, sai grant, token expired/used/revoked, logout, race 2 replica, retry sau timeout và rollback lỗi?

**Ghi nhớ:** Refresh token family là **lịch sử kế thừa và trạng thái của chuỗi refresh token trong một grant/phiên**. Rotation làm token cũ không thể đổi lần nữa; family tracking giúp AS phát hiện reuse và **thu hồi token hậu duệ đang hoạt động** khi nghi có bản sao bị đánh cắp. Thiết kế an toàn đòi hỏi **atomic state transitions, client/grant binding, vòng đời hữu hạn, bảo vệ token tại client và xử lý race/retry có chủ đích**. Nó bảo vệ việc cấp access token mới, nhưng **không tự bảo vệ mọi access token đã được phát hành hoặc thay thế phân quyền tại resource server**.

### Chuẩn tham khảo

- **RFC 6749 — The OAuth 2.0 Authorization Framework:** refresh token grant, binding với client, `invalid_grant` và giới hạn scope.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** rotation hoặc sender-constraining refresh token cho public clients, phát hiện replay và nguyên tắc bảo vệ token.
- **RFC 7009 — OAuth 2.0 Token Revocation:** thu hồi token/grant và chính sách thu hồi liên quan.
- **RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP):** ràng buộc token vào khóa và kiểm proof.
- **RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens:** ràng buộc token bằng certificate theo profile áp dụng.
- **RFC 8707 — Resource Indicators for OAuth 2.0:** yêu cầu token hướng tới resource dự kiến.
- **RFC 7662 — OAuth 2.0 Token Introspection:** thông tin `active` và trạng thái access token tại RS.
- **RFC 7519 — JSON Web Token (JWT):** claims như `iss`, `aud` và `exp`; JWT không tự lưu lịch sử refresh một lần.
- **OpenID Connect Core 1.0:** OAuth/OIDC grant và các yêu cầu liên quan đến xác thực, offline access theo profile.

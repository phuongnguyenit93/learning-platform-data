# Phát hiện reuse bất thường

Một **Bearer token** trao quyền cho bên đang nắm giữ nó: nếu token được cấp hợp lệ, chưa hết hạn và đúng audience/scope, resource server thường không thể biết ai là người *thực sự* gửi request chỉ từ giá trị token. Vì vậy, token bị lấy trộm qua XSS, log, cấu hình proxy sai hoặc thiết bị bị xâm nhập có thể được **phát lại (*replay*)** để thực hiện request dưới danh nghĩa chủ thể đã được cấp quyền.

Tuy nhiên, **không phải mọi lần “dùng lại token” đều là tấn công**. Một access token Bearer được thiết kế để có thể dùng trong nhiều request trong thời hạn của nó. Ngược lại, **refresh token rotation** khiến một refresh token cũ mất hiệu lực sau lần sử dụng thành công; việc giá trị cũ xuất hiện trở lại là tín hiệu đáng chú ý về rò rỉ, lỗi đồng bộ hoặc request bị retry. Bài học này giải thích cách **phát hiện reuse bất thường mà không nhầm hành vi hợp lệ với dấu hiệu xâm nhập**.

Trong chương **Bearer security** của module bảo mật token, chúng ta kết nối mô hình tin cậy OAuth 2.0/OIDC, JWT và opaque token, access/refresh token, scope, audience, lưu trữ, thu hồi, chống đánh cắp và phát lại. Trọng tâm là **tín hiệu quan sát, thuật toán phát hiện, phản ứng khi có nghi vấn và kiểm thử**.

> **Nguyên tắc cốt lõi:** Dùng lại **access token** không tự chứng minh bị tấn công; dùng lại **refresh token đã được rotation** là sự kiện bảo mật cần xử lý. Mọi kết luận đều cần ngữ cảnh, chính sách và các biện pháp giảm báo động nhầm.

## 1. Reuse là gì? Phân biệt với replay và token theft

- **Token reuse:** cùng một credential xuất hiện trong nhiều lần sử dụng. Với access token Bearer, điều này thường **bình thường**; với refresh token cũ đã bị vô hiệu hóa sau rotation, điều này có thể là bất thường.
- **Token replay:** một credential hoặc bằng chứng đã dùng bị gửi lại ở ngữ cảnh không được phép, ví dụ attacker sử dụng access token đánh cắp hoặc tái sử dụng DPoP proof có `jti` đã được xử lý.
- **Token theft:** credential bị lộ cho bên không được phép. Việc quan sát reuse **không luôn chứng minh** token theft; kẻ tấn công cũng có thể dùng token một lần hoặc dùng cùng mạng/thiết bị với user.
- **Refresh token rotation:** authorization server (AS) cấp refresh token mới khi refresh thành công và vô hiệu hóa token cũ, đồng thời duy trì quan hệ giữa các token trong cùng grant/token family.
- **Reuse detection:** nhận diện request dùng token/proof không còn được phép hoặc mẫu hành vi khó phù hợp với cách hệ thống hoạt động bình thường.

| Credential | Có thường được dùng nhiều lần? | Tín hiệu reuse cần hiểu thế nào? |
| --- | --- | --- |
| **Access token Bearer** | **Có**, cho nhiều API requests trong thời hạn | Cùng token xuất hiện nhiều lần là bình thường; chỉ ngữ cảnh bất thường mới đáng điều tra |
| **JWT access token có `jti`** | Có, nếu profile không quy định một lần | `jti` giúp định danh/correlation; **không tự biến token thành one-time token** |
| **Opaque access token** | Thường có, theo chính sách | AS/RS có thể theo dõi trạng thái và hành vi nếu có log/introspection |
| **Refresh token có rotation** | Token **hiện hành** thường chỉ đổi thành công **một lần** | Token đã dùng bị trình lại: nghi reuse, cần phản ứng theo policy |
| **Refresh token sender-constrained** | Tùy thiết kế; có thể không dùng rotation | Ràng buộc với khóa/chứng chỉ giảm giá trị của bản sao token bị lộ |
| **DPoP proof JWT** | **Không** được chấp nhận lặp lại trong cửa sổ replay | `jti` trong DPoP proof cần kiểm tra không lặp với các ràng buộc tương ứng |
| **Authorization code OAuth** | Không, code được đổi token một lần | Đổi lại code đã sử dụng cần bị từ chối; có thể là lỗi/rủi ro tùy ngữ cảnh |
| **Session cookie** | Có, trong nhiều HTTP requests | Dùng lặp là bình thường; session hijacking cần tín hiệu bổ sung |

**Điểm dễ nhầm:** `access_token.jti` khác `dpop_proof.jti`. Nếu từ chối access token chỉ vì `jti` đã xuất hiện ở một request trước, hầu hết ứng dụng sẽ ngừng hoạt động bình thường. Trong khi đó, replay protection cho **DPoP proof** yêu cầu phát hiện việc tái sử dụng proof theo cửa sổ hiệu lực.

## 2. Mô hình tin cậy: ai phát hiện được hành vi nào?

Một hệ thống điển hình có các thành phần:

~~~mermaid
flowchart LR
    U["Người dùng"] --> C["Browser / Mobile / BFF"]
    C -->|"Access token"| GW["Gateway"]
    GW --> RS["Resource server / API"]
    C -->|"Refresh token"| AS["Authorization server"]
    AS --> ST["Token store / grant family"]
    GW --> OBS["Telemetry / detection"]
    RS --> OBS
    AS --> OBS
    OBS --> RESP["Risk policy / incident response"]
    RESP --> AS
    RESP --> RS
~~~

| Thành phần | Quan sát đáng tin có thể có | Giới hạn |
| --- | --- | --- |
| **Authorization server** | Refresh token đã/đang active, token family, client/grant, thời điểm refresh, reuse token cũ | Không tự thấy mọi API request nếu access token được xác minh offline |
| **Gateway/resource server** | Token đã xác minh, API, thời gian, session/request ID, mạng và tín hiệu dùng access token | Không tự biết token đã bị lấy trộm nếu attacker sử dụng như user |
| **Client/BFF** | Số luồng refresh, tab, network retries, trạng thái token đang giữ | JavaScript client có thể bị XSS; không tự chứng minh môi trường an toàn |
| **Hệ thống phát hiện rủi ro** | Liên kết sự kiện theo grant/client/user, tốc độ, thiết bị, địa lý, hành vi | Phải quản lý false positive, quyền riêng tư và thời gian lưu dữ liệu |

Không hệ thống nào có thể kết luận “đây là chính chủ” chỉ từ `Authorization: Bearer ...`. **Bearer semantics không ràng buộc việc sở hữu token với một khóa thiết bị**. Các cơ chế *sender-constrained tokens* như DPoP hoặc mTLS có thể tạo lớp chứng minh sở hữu bổ sung, nhưng vẫn cần xác thực/kiểm tra quyền đúng.

## 3. Access token được dùng nhiều lần là hành vi chuẩn

Giả sử browser lấy access token hạn 15 phút cho API:

~~~http
GET /api/profile HTTP/1.1
Host: api.example.com
Authorization: Bearer <same-access-token>
~~~

~~~http
GET /api/orders HTTP/1.1
Host: api.example.com
Authorization: Bearer <same-access-token>
~~~

~~~http
POST /api/orders/123/notes HTTP/1.1
Host: api.example.com
Authorization: Bearer <same-access-token>
Content-Type: application/json

{"note":"đã kiểm tra"}
~~~

Ba request có thể hợp lệ nếu token đúng `iss`, `aud`, `exp`, scope và user đủ quyền với các tài nguyên. **Không bắt buộc AS cấp token mới cho từng API call**.

### 3.1. `jti` là định danh token, không mặc định là nonce sử dụng một lần

Claim `jti` trong JWT (RFC 7519) cung cấp một identifier duy nhất do issuer định nghĩa, hữu ích cho audit, tương quan sự kiện, denylist và phát hiện mẫu dùng. Nhưng **JWT access token có `jti` không tự là one-time token**.

Ví dụ payload minh họa:

~~~json
{
  "iss": "https://auth.example.com",
  "sub": "user-42",
  "aud": "https://api.example.com/orders",
  "scope": "orders.read",
  "jti": "at-4db3d2",
  "iat": 1800000000,
  "exp": 1800000900
}
~~~

Cùng `jti=at-4db3d2` trên nhiều requests **không phải bằng chứng replay nguy hiểm**. Nó chỉ giúp xác định cùng một token được dùng. Nếu token xuất hiện đồng thời trong các môi trường rất khác biệt hoặc truy cập khác thường, mới có cơ sở tăng điểm rủi ro.

### 3.2. Vì sao access token bị đánh cắp khó phát hiện?

Một bearer access token được ký hợp lệ vẫn được API chấp nhận nếu attacker gửi lại từ nơi khác **trước `exp`**, trừ khi đã bị thu hồi hoặc có kiểm soát bổ sung. JWT chữ ký hợp lệ chứng minh **issuer đã phát hành token**, không chứng minh **người cầm token hiện tại là client ban đầu**.

Vì thế biện pháp chống replay không chỉ là analytics. Cần song song:

- Hạn access token ngắn, scope/audience hẹp, kiểm tra resource ownership/tenant.
- HTTPS mọi hop, bảo vệ credential ở client, proxy và backend; không đưa token vào URL/log.
- Xem xét DPoP/mTLS sender-constrained token khi phù hợp.
- Thu hồi/denylist, introspection hoặc kiểm tra session/grant cho tài nguyên có rủi ro cao.

## 4. Refresh token rotation: nguồn tín hiệu reuse mạnh hơn

Trong OAuth 2.0, **refresh token** được client dùng với AS để xin access token mới. Với **refresh token rotation**, mỗi lần refresh thành công:

1. Client xuất trình refresh token hiện hành `RT-1`.
2. AS xác thực grant/client và kiểm tra trạng thái `RT-1`.
3. AS vô hiệu hóa `RT-1`, cấp access token và refresh token mới `RT-2`, lưu quan hệ chúng trong cùng **token family/grant**.
4. Client thay `RT-1` bằng `RT-2` một cách an toàn.
5. Nếu `RT-1` xuất hiện trở lại, AS biết có **credential đã bị rotation được sử dụng thêm**, cần phản ứng.

~~~mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant AS as Authorization server
    participant DB as Token family store
    participant X as Attacker hoặc retry lỗi
    C->>AS: refresh_token=RT-1
    AS->>DB: RT-1 có ACTIVE không?
    DB-->>AS: ACTIVE
    AS->>DB: RT-1=USED; phát RT-2=ACTIVE
    AS-->>C: AT-2 + RT-2
    X->>AS: refresh_token=RT-1 (đã dùng)
    AS->>DB: Kiểm tra family/trạng thái
    DB-->>AS: RT-1=USED, RT-2=ACTIVE
    AS->>DB: Đánh dấu nghi reuse; thu hồi family theo policy
    AS-->>X: invalid_grant (không tiết lộ chi tiết)
    C->>AS: refresh_token=RT-2
    AS-->>C: Từ chối nếu family đã bị thu hồi
~~~

**Điều không thể suy ra:** khi `RT-1` bị gửi lại, AS thường **không thể biết chắc** request đó do attacker hay client hợp lệ (retry/đua luồng). Do đó, rotation-based replay detection là **tín hiệu compromise**, không phải bằng chứng hoàn toàn chính xác về danh tính kẻ tấn công.

Theo OAuth 2.0 Security Best Current Practice (RFC 9700), **public client** cần có cơ chế phát hiện refresh token replay như **sender-constrained refresh token hoặc refresh token rotation** theo các điều kiện chuẩn áp dụng. Rotation yêu cầu AS có cách lưu thông tin liên hệ các token trong cùng family để phát hiện reuse.

### 4.1. Token family và các trạng thái

Ví dụ:

~~~text
Grant/family F-7 cho client invoice-app và user-42

RT-1  status=USED      successor=RT-2
RT-2  status=USED      successor=RT-3
RT-3  status=ACTIVE    successor=null

Một request dùng RT-1 hoặc RT-2:
  -> token đã rotation
  -> đánh dấu reuse signal
  -> theo chính sách, revoke family F-7
  -> buộc xác thực/ủy quyền lại khi cần
~~~

Một token family nên gắn với **grant, client, subject/principal, phiên thiết bị khi có và policy của AS**, không gộp tất cả thiết bị của một user vào duy nhất một family nếu không có chủ đích. Thu hồi family bị nghi compromise thường cần làm mất khả năng cấp token mới từ family đó; **không nhất thiết phải thu hồi toàn bộ session trên mọi thiết bị**.

### 4.2. Nguy cơ của refresh token không rotation

Nếu AS cấp refresh token có thể dùng lặp mãi và không ràng buộc bên gửi, attacker cầm bản sao có thể liên tục xin access token mới mà **không tạo tín hiệu “token cũ đã dùng”**. Khi đó, hệ thống phụ thuộc nhiều hơn vào telemetry, thời hạn, revocation và cơ chế sender constraint.

Không nên đánh đồng `refresh_token` với `access_token` ở API; refresh token chỉ được gửi tới **token endpoint**, không mang tới resource server.

## 5. Reuse detection phải xử lý concurrency và lỗi mạng

Một SPA có nhiều tab hoặc BFF có nhiều worker có thể cùng phát hiện access token sắp hết hạn. Nếu chúng đều dùng `RT-1`:

~~~text
Tab A: refresh(RT-1) -> thành công, nhận RT-2
Tab B: refresh(RT-1) -> RT-1 đã USED -> reuse signal
~~~

Đây có thể là **race condition hợp lệ**, nhưng nhìn từ AS nó cũng giống attacker dùng lại token cũ. Nếu client retry sau timeout khi response chứa `RT-2` đã phát hành nhưng bị mất trên mạng, `RT-1` cũng có thể bị xuất trình lần hai.

### 5.1. Giảm race ở client

- **Single-flight refresh:** một phiên/client chỉ có một refresh request đang chạy cho cùng grant; request khác chờ kết quả và dùng token mới.
- **BFF/session backend:** tập trung refresh ở server; tránh nhiều tab browser trực tiếp điều khiển cùng refresh token.
- **Cập nhật token atomically:** lưu cặp access/refresh token mới nhất theo transaction hoặc cơ chế đồng bộ của nền tảng.
- **Không retry token request một cách mù quáng:** khi request refresh mất kết nối, không tự gửi lại vô hạn token cũ.
- **Không chia sẻ refresh token giữa nhiều client/thiết bị** nếu AS thiết kế mỗi thiết bị một grant/family riêng.

### 5.2. Giảm false positive ở AS mà không mất bảo vệ

AS có thể phân biệt **phát hiện** với **đưa ra quyết định rủi ro**, nhưng không nên âm thầm chấp nhận token cũ và **cấp thêm nhiều refresh token mới** sau khi nó đã bị rotation. Một khoảng grace period nếu thật sự cần phải được thiết kế cẩn thận, tránh tạo đường cho kẻ giữ token cũ truy cập.

Cách an toàn, dễ hiểu là **từ chối token đã dùng và thu hồi family theo chính sách rõ ràng**, chấp nhận việc một số trường hợp retry hợp lệ phải đăng nhập lại. Nếu muốn cơ chế retry/idempotency tại token endpoint, nó cần **ràng buộc yêu cầu với đúng client/sender và phiên xử lý ban đầu**, có thời gian hiệu lực, chống phát lại và được đánh giá mối đe dọa riêng — không phải chỉ “cho phép dùng RT-1 thêm 30 giây”.

**Đánh đổi phải được nêu rõ:** phát hiện nhạy có thể tăng số lần đăng nhập lại; cho phép reuse quá dễ có thể khiến attacker duy trì phiên.

## 6. Thiết kế token family và rotation nguyên tử

AS cần bảo đảm **hai refresh request đồng thời không đều thành công bằng cùng một token cũ**. Khóa hàng database, compare-and-swap (CAS) hoặc transaction/constraint tương đương là những cách phổ biến.

Một schema minh họa:

~~~sql
-- Ví dụ về mặt ý tưởng; tên cột và kiểu dữ liệu tùy hệ CSDL.
CREATE TABLE refresh_grants (
    family_id        VARCHAR(100) PRIMARY KEY,
    client_id        VARCHAR(200) NOT NULL,
    subject_id       VARCHAR(200),
    status           VARCHAR(20) NOT NULL,  -- ACTIVE / REVOKED
    created_at       TIMESTAMP NOT NULL,
    revoked_at       TIMESTAMP
);

CREATE TABLE refresh_tokens (
    token_fingerprint VARCHAR(128) PRIMARY KEY,
    family_id         VARCHAR(100) NOT NULL
        REFERENCES refresh_grants(family_id),
    status            VARCHAR(20) NOT NULL,  -- ACTIVE / USED / REVOKED
    issued_at         TIMESTAMP NOT NULL,
    expires_at        TIMESTAMP NOT NULL,
    successor_fp      VARCHAR(128)
);
~~~

**Không cần lưu refresh token plaintext trong database** nếu AS có thể tra cứu bằng fingerprint/hash an toàn. Giá trị token nên được sinh bằng CSPRNG với entropy đủ lớn, ví dụ 256 bit, và được xử lý như bí mật. Fingerprint có thể là HMAC-SHA-256 sử dụng khóa giám sát riêng được bảo vệ để giảm việc lộ/đoán định danh qua log hoặc lưu trữ.

### 6.1. Giao dịch rotation được tuần tự hóa

Pseudo-SQL dưới đây làm rõ quyết định bảo mật, không phải stored procedure chạy được nguyên văn:

~~~sql
-- 1) Tìm family_id từ fingerprint của refresh token được trình.
--    Nếu không biết token: từ chối; không thể suy ra family để revoke.
SELECT family_id
FROM refresh_tokens
WHERE token_fingerprint = :presented_fp;

BEGIN;

-- 2) Khóa family trước để serialize mọi rotation trong cùng grant.
SELECT status, client_id, subject_id
FROM refresh_grants
WHERE family_id = :family_id
FOR UPDATE;

-- 3) Đọc lại token trong transaction.
SELECT status, expires_at
FROM refresh_tokens
WHERE token_fingerprint = :presented_fp
  AND family_id = :family_id
FOR UPDATE;

-- 4) Nếu family không ACTIVE: từ chối.
--    Nếu token là USED/REVOKED: ghi sự kiện reuse,
--    đặt family = REVOKED (theo policy), COMMIT, rồi từ chối.
--    Nếu token hết hạn hoặc client/grant không hợp lệ: từ chối.

-- 5) Nếu token ACTIVE và mọi điều kiện hợp lệ:
UPDATE refresh_tokens
SET status = 'USED', successor_fp = :new_fp
WHERE token_fingerprint = :presented_fp
  AND status = 'ACTIVE';

INSERT INTO refresh_tokens(
    token_fingerprint, family_id, status, issued_at, expires_at
) VALUES (
    :new_fp, :family_id, 'ACTIVE', :now, :new_expiry
);

-- 6) Ghi audit tối thiểu, COMMIT, sau đó trả access token
--    và refresh token mới đúng với rotation đã commit.
COMMIT;
~~~

Hệ thống thật cần kiểm tra **số hàng UPDATE chính xác là 1**, unique constraints và behavior rollback; không được tiếp tục nếu trạng thái bị thay đổi bất ngờ. Các request đồng thời cần đi qua **cùng ranh giới transaction**, kể cả khi AS chạy nhiều instance.

**Lưu ý quan trọng về transaction:** nếu phát hiện reuse và cần revoke family, phải **commit trạng thái revoke/audit trước khi trả lỗi**. Trong Spring `@Transactional`, ném unchecked exception ngay sau khi cập nhật DB có thể làm **rollback** việc thu hồi. Một hướng là trả về kết quả nghiệp vụ `REUSE_DETECTED` từ transaction, rồi tại lớp HTTP chuyển thành lỗi `invalid_grant` **sau commit**, hoặc dùng transaction/exception handling đã thiết kế rõ.

### 6.2. Ví dụ Java minh họa luồng bảo mật

Ví dụ gần với Java/Spring, các interface được định nghĩa theo ứng dụng để tập trung vào invariant; đây là **mẫu thiết kế**, chưa phải authorization server hoàn chỉnh:

~~~java
enum RotationStatus {
    SUCCESS, INVALID_GRANT, REUSE_DETECTED
}

record RotationResult(
    RotationStatus status,
    String accessToken,
    String refreshToken
) {
    static RotationResult invalid() {
        return new RotationResult(
            RotationStatus.INVALID_GRANT, null, null);
    }
    static RotationResult reuse() {
        return new RotationResult(
            RotationStatus.REUSE_DETECTED, null, null);
    }
}

// Pseudocode service: TokenStore phải dùng transaction và row lock
// xuyên các instance; TokenFactory dùng CSPRNG + policy phù hợp.
@Transactional
public RotationResult rotate(String presentedToken, String clientId) {
    String fingerprint = tokenFingerprinter.hmac(presentedToken);
    TokenRecord snapshot = tokenStore.findByFingerprint(fingerprint);
    if (snapshot == null) {
        return RotationResult.invalid();
    }

    TokenFamily family =
        tokenStore.lockFamilyForUpdate(snapshot.familyId());
    TokenRecord current =
        tokenStore.lockTokenForUpdate(fingerprint);

    if (!family.isActive() || !family.clientId().equals(clientId)) {
        return RotationResult.invalid();
    }

    if (current.isUsedOrRevoked()) {
        tokenStore.revokeFamily(family.id());
        audit.recordReuse(family.id(), clientId); // không log token
        return RotationResult.reuse(); // COMMIT khi method kết thúc
    }

    if (!current.isActive() || current.isExpired(clock.instant())) {
        return RotationResult.invalid();
    }

    // Kiểm tra thêm client auth/binding, grant, scope, policy...
    String nextRefresh = tokenFactory.createSecureRefreshToken();
    String nextFingerprint = tokenFingerprinter.hmac(nextRefresh);

    tokenStore.markUsed(current, nextFingerprint);
    tokenStore.insertActive(family.id(), nextFingerprint);
    String nextAccess = tokenFactory.issueApprovedAccessToken(family);
    return new RotationResult(
        RotationStatus.SUCCESS, nextAccess, nextRefresh);
}
~~~

Đây là pseudocode Java, không phải class độc lập có thể biên dịch: `TokenStore`, `TokenFactory`, `audit`, `clock` và kiểm tra OAuth client là thành phần minh họa. Token mới chỉ được trả cho client khi transaction commit thành công; ứng dụng phải xử lý lỗi commit mà **không phát lại token mồ côi**. Khi response bị mất sau commit, **token cũ vẫn đã USED**.

Ở HTTP boundary:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json
Cache-Control: no-store

{"error":"invalid_grant"}
~~~

Theo OAuth 2.0, refresh token không hợp lệ hoặc bị thu hồi thường được từ chối bằng `invalid_grant`. **Không tiết lộ cho caller** rằng chính xác token nào trong family vẫn đang active hoặc attacker đã kích hoạt cảnh báo.

## 7. Phát hiện access-token replay bằng tín hiệu rủi ro

Đối với access token Bearer, không có invariant “mỗi token chỉ dùng một lần”. Cần kết hợp các tín hiệu theo **cùng token/grant/principal** hoặc theo phiên, tùy chính sách:

| Tín hiệu | Giá trị phát hiện | Khả năng báo nhầm |
| --- | --- | --- |
| Cùng token từ **hai ASN/mạng rất khác** trong thời gian ngắn | Có thể là token bị sao chép | VPN, proxy doanh nghiệp, mạng di động, failover |
| Hai vị trí địa lý có khoảng cách di chuyển bất thường | Gợi ý token được dùng tại nhiều nơi | Geo-IP sai, VPN, roaming, CDN |
| Token dùng đồng thời ở nhiều device fingerprint | Có thể là nhân bản credential | Fingerprint không ổn định; trình duyệt thay đổi |
| Cùng token gọi endpoint có nguy cơ cao đột ngột | Gợi ý hành vi khác profile | User thực hiện thao tác hợp lệ hiếm gặp |
| Tăng mạnh số request hoặc phạm vi API bất thường | Gợi ý abuse/automation | Batch job, đồng bộ ứng dụng, retry network |
| Token dùng sau logout/thu hồi đã ghi nhận | Có tín hiệu credential cũ bị sử dụng | Cache, độ trễ đồng bộ hoặc client chưa xóa token |
| Scope/audience không phù hợp API | Yêu cầu có thể bị dùng sai resource | Cấu hình client/AS sai; phải từ chối dù nguyên nhân gì |
| Cùng refresh token đã rotation được gửi lại | **Tín hiệu mạnh** theo state machine | Race và retry mất response |

**IP address, User-Agent và device fingerprint chỉ là tín hiệu**, không phải bằng chứng mật mã về người giữ token. Nhiều người dùng cùng NAT, một user đổi IP liên tục, máy chủ reverse proxy gom địa chỉ; không nên revoke tất cả phiên chỉ dựa trên thay đổi IP.

### 7.1. Phân loại tín hiệu theo mức tin cậy

- **Cứng / định nghĩa bởi giao thức:** refresh token đã `USED` nhưng được trình lại; DPoP proof `jti` đã được dùng trong cửa sổ; sender-binding không khớp; token không đúng `aud`/`iss`/chữ ký.
- **Trung bình / bối cảnh kỹ thuật:** cùng access token xuất hiện từ hai client session độc lập trong vài giây, thay đổi đột ngột loại endpoint, mismatch với phiên thiết bị đã đăng ký.
- **Mềm / thống kê:** geo-IP “impossible travel”, thay đổi User-Agent, số lượng request tăng. Dễ chịu tác động bởi proxy, VPN, app update và workflow hợp lệ.

Một mô hình có thể chấm điểm rủi ro:

~~~text
risk = signal(refresh_reuse)        [rất cao]
     + signal(proof_replay)         [rất cao]
     + signal(device_divergence)    [trung bình]
     + signal(geo_anomaly)          [thấp / trung bình]
     + signal(unusual_privileged)   [trung bình]

Các trọng số/ngưỡng chỉ do tổ chức hiệu chỉnh bằng dữ liệu vận hành,
không phải giá trị chuẩn của OAuth 2.0 hoặc OIDC.
~~~

Không cộng điểm một cách máy móc khi các tín hiệu có cùng nguồn gốc (ví dụ IP đổi và geo-IP đổi là một sự kiện). Với tài khoản nhạy cảm, nên thiết kế chính sách **fail-closed tại thao tác rủi ro cao** nhưng vẫn hạn chế khóa tài khoản sai hàng loạt do noise.

## 8. Telemetry an toàn: quan sát mà không để lộ token

Để nhận diện “cùng token”, cần một **định danh tương quan** nhưng **không nên ghi raw token** vào logs, metrics, tracing hay hệ thống phân tích.

Một event chuẩn hóa có thể chứa:

~~~json
{
  "event_type": "access_token_observed",
  "observed_at": "2026-11-23T02:10:00Z",
  "token_fingerprint": "hmac-sha256:truncated-for-display",
  "issuer_id": "auth-primary",
  "audience_id": "orders-api",
  "principal_ref": "internal-user-ref",
  "client_id": "orders-web",
  "request_id": "req-abc",
  "route_group": "orders.read",
  "network_risk_bucket": "new-asn",
  "decision": "allow"
}
~~~

Các giá trị trên là **minh họa**, không phải dữ liệu vận hành. Thay vì chứa raw IP, user-agent và location ở mọi nơi, có thể dùng nhóm rủi ro/định danh được bảo vệ và chính sách retention tương xứng.

### 8.1. Dùng HMAC để tạo fingerprint

Nếu phải tương quan cùng token trên các request, AS/gateway có thể tính:

\[
\mathrm{fingerprint} = \operatorname{HMAC}_{K_\mathrm{audit}}
  (\mathrm{raw\ token})
\]

Khóa `K_audit` phải tách biệt với JWT signing key, client secret và khóa mã hóa dữ liệu; lưu trong secret manager, giới hạn truy cập và có kế hoạch rotation. Fingerprint cần đủ độ dài để giảm va chạm và có namespace theo hệ thống/môi trường khi cần. Đừng dùng `hashCode()`, base64 của token hoặc log vài chục ký tự token thô làm “ẩn danh”.

Với opaque token hoặc JWT chứa `jti`, hệ thống vẫn nên cân nhắc **không log `jti`/subject trực tiếp** khi có nguy cơ liên kết dữ liệu người dùng xuyên hệ thống. Hash/HMAC identifier cũng có thể là dữ liệu cá nhân giả danh hóa (*pseudonymous*), không mặc nhiên là hoàn toàn ẩn danh.

### 8.2. Log ở gateway hay resource server?

Không nên ghi Bearer token ở nhiều tầng. Hãy chọn một điểm đáng tin để xác minh/định danh token và phát **event tối thiểu**. Nếu service downstream cần truy vết, dùng correlation ID hoặc assertion được bảo vệ thay vì chuyển credential thành nhãn log. Phải kiểm soát quyền truy cập dữ liệu telemetry, retention, mã hóa lưu trữ và tránh token xuất hiện trong exception stack, tracing span, URL hoặc crash dump.

## 9. DPoP: proof replay detection và token ràng buộc khóa

**Demonstrating Proof-of-Possession (DPoP, RFC 9449)** giúp giảm nguy cơ bản sao Bearer access token bị sử dụng từ nơi khác. Client sở hữu một private key và ký **DPoP proof JWT** cho request; access token được **ràng buộc với public key** tương ứng, thường qua `cnf.jkt`.

Ví dụ khi dùng DPoP-bound token:

~~~http
GET /api/orders HTTP/1.1
Host: api.example.com
Authorization: DPoP <access-token>
DPoP: <signed-proof-jwt>
~~~

Resource server phải thực hiện **nhiều lớp kiểm tra**, không chỉ kiểm tra JWS của proof:

1. Xác minh access token đúng issuer, audience, thời gian, scope và loại token theo profile.
2. Xác nhận access token là **DPoP-bound**, kiểm tra public key thumbprint của DPoP proof khớp `cnf.jkt` hoặc metadata ràng buộc tin cậy.
3. Xác minh chữ ký DPoP proof bằng public key được khai trong proof theo yêu cầu chuẩn; **không** dùng `alg=none` hoặc thuật toán MAC đối xứng.
4. Kiểm tra `htm` (HTTP method) và `htu` (địa chỉ đích theo quy tắc chuẩn) khớp request.
5. Kiểm tra `iat` của proof còn trong cửa sổ hợp lệ và **`jti` proof chưa được dùng** trong cửa sổ replay; xử lý nonce nếu server yêu cầu.
6. Khi proof dùng với access token, kiểm tra `ath`: giá trị hash của access token đang gửi có khớp với proof hay không.

Ví dụ **payload DPoP proof minh họa**:

~~~json
{
  "htm": "GET",
  "htu": "https://api.example.com/api/orders",
  "iat": 1800000000,
  "jti": "unique-proof-id-8842",
  "ath": "<base64url-sha256-of-access-token>"
}
~~~

Khác access token:

- **Access token** thường được dùng qua nhiều requests và có thể giữ cùng `jti`.
- **DPoP proof** phải được tạo **riêng cho request**, với `jti` đáp ứng yêu cầu duy nhất; một proof cũ bị phát lại cần bị phát hiện.

### 9.1. Replay cache cho DPoP proof

Replay cache có thể dùng key kết hợp **thumbprint khóa DPoP, `jti` proof và ngữ cảnh/thời gian**, lưu trong cửa sổ đủ dài theo chính sách chấp nhận `iat`/nonce. Thao tác ghi phải **atomic** trên các instance, ví dụ `SET key value NX EX ttl` trong Redis; nếu key đã tồn tại thì từ chối proof.

~~~text
Proof mới:
  atomically insert proof-key if absent -> accept nếu các check khác đạt

Proof lặp:
  proof-key đã có -> reject

Proof hết cửa sổ:
  reject vì iat quá cũ, không phụ thuộc cache đã xóa
~~~

**Không đơn thuần xóa cache quá sớm:** nếu proof còn được coi là fresh sau khi record hết TTL, attacker có thể replay. Thiết kế cache phải phù hợp leeway, số server, đồng hồ và DPoP nonce policy. Các lỗi Redis/cache không được âm thầm biến thành “cho qua mọi proof” ở endpoint rủi ro cao.

### 9.2. Hạn chế của DPoP

DPoP bảo vệ tốt hơn trước kẻ chỉ đánh cắp **bản sao token**, nhưng **không miễn nhiễm** với XSS điều khiển JavaScript khi private key có thể bị dùng tại runtime, hoặc malware chiếm cả token và khóa. DPoP cũng đòi hỏi AS/RS/client hỗ trợ nhất quán; không thể chỉ thêm header DPoP vào một Bearer token bất kỳ rồi coi token được ràng buộc.

## 10. mTLS và sender-constrained token

OAuth 2.0 mTLS (RFC 8705) có thể ràng buộc access token với **chứng chỉ client**. Access token hoặc introspection metadata có thể chứa thông tin xác nhận (*confirmation*) như thumbprint chứng chỉ `cnf["x5t#S256"]`; resource server xác minh chứng chỉ xuất trình qua TLS phù hợp với token.

So sánh:

| Cơ chế | Replay guard chính | Cần trạng thái gì? |
| --- | --- | --- |
| Bearer access token thuần | Dựa chủ yếu vào chống lộ, hạn/thu hồi, anomaly detection | Có thể stateless cho JWT; telemetry bổ sung |
| Refresh token rotation | Dấu hiệu reuse token **đã sử dụng** | Cần theo dõi token family/đã-used |
| DPoP | Ràng buộc access token với khóa + proof theo request, chống replay `jti` | Replay cache hoặc chiến lược chống replay phù hợp |
| mTLS-bound access token | Ràng buộc token với chứng chỉ/khóa TLS client | Hạ tầng TLS và thông tin certificate binding đáng tin |

**mTLS token binding không đồng nghĩa mTLS client authentication tại token endpoint**, dù cùng hệ sinh thái có thể sử dụng cả hai. Resource server phải kiểm tra sender constraint thích hợp, không chỉ thấy `client_id` mà kết luận request đã được xác thực thiết bị.

## 11. Phát hiện reuse trong JWT và opaque token

### 11.1. JWT access token: tự chứa và thường xác minh offline

JWT có thể chứa `iss`, `sub`, `aud`, `scope`, `exp`, `jti`. RS xác minh chữ ký, thuật toán, issuer, audience, hạn và policy mà **không cần gọi AS trong mỗi request**. Điều này tốt cho hiệu năng nhưng:

- Khó biết token đã bị thu hồi ngay lập tức nếu chỉ kiểm tra offline.
- AS không thấy mỗi lần access token được dùng nếu không có telemetry từ RS/gateway.
- Reuse detection thường dựa vào correlation và risk signals, không phải việc token có `jti` xuất hiện nhiều lần.

Đối với thao tác nhạy cảm, có thể dùng thời hạn ngắn, denylist/token version, kiểm tra session/grant hiện hành hoặc introspection/hệ thống quyền tập trung theo chính sách.

### 11.2. Opaque access token: có khả năng tra trạng thái tập trung

Với opaque token, RS có thể introspect:

~~~http
POST /oauth2/introspect HTTP/1.1
Host: auth.example.com
Authorization: Basic <resource-server-credentials>
Content-Type: application/x-www-form-urlencoded

token=<opaque-access-token>
~~~

Ví dụ response:

~~~json
{
  "active": true,
  "iss": "https://auth.example.com",
  "sub": "user-42",
  "aud": "orders-api",
  "client_id": "orders-web",
  "scope": "orders.read",
  "exp": 1800000900
}
~~~

RS phải coi introspection là nguồn có thẩm quyền theo hợp đồng, xác thực/kết nối an toàn và vẫn kiểm tra audience, scope, quyền trên tài nguyên. **Opaque token không tự chống replay**: ai cầm bản sao hợp lệ vẫn có thể gửi request, trừ khi có sender constraint và các kiểm soát khác.

Caching introspection có thể tạo độ trễ phát hiện thu hồi; TTL phải theo rủi ro và trạng thái token. Đừng xem “opaque” đồng nghĩa “revoke tức thì” khi cache dài.

## 12. Phản ứng theo mức độ rủi ro

Không phải mọi signal đều cần lập tức khóa toàn bộ tài khoản. Một ma trận gợi ý:

| Phát hiện | Mức tin cậy | Phản ứng đề xuất |
| --- | --- | --- |
| Access token được dùng nhiều lần cùng client/thiết bị | Bình thường | Không cảnh báo |
| User đổi IP nhưng cùng phiên/thói quen | Thấp | Theo dõi, kết hợp tín hiệu khác |
| Cùng token được dùng đồng thời tại nhiều mạng, kèm truy cập nhạy cảm | Trung bình–cao | Cảnh báo, step-up, hạn chế thao tác, có thể revoke token/session liên quan |
| Refresh token đã rotation bị gửi lại | Cao về việc token cũ tái sử dụng | Từ chối, đánh dấu grant/family nghi compromise; revoke family theo policy, yêu cầu đăng nhập lại |
| DPoP proof `jti` bị replay | Cao theo quy tắc giao thức | Từ chối proof/request; rate limit và điều tra |
| Sender constraint không khớp | Cao | Từ chối token và theo dõi sự cố |
| Sai issuer, chữ ký hoặc audience | Token không hợp lệ | Từ chối; không cấp authority/đọc resource |
| Token bị dùng sau khi bị revoke | Tùy nguyên nhân nhưng đáng chú ý | Từ chối; xác minh cache/độ trễ và dấu hiệu đánh cắp |

Một phản ứng sự cố đầy đủ có thể gồm:

1. **Chặn hành động không hợp lệ ngay tại điểm xác minh**, trả lỗi chung phù hợp giao thức.
2. **Giới hạn phạm vi thu hồi** theo grant/token family, thiết bị, client hoặc tài khoản tùy bằng chứng và mức rủi ro.
3. **Thu hồi refresh token family** khi rotation reuse theo policy, và cân nhắc vô hiệu access token đã phát nếu cần phản ứng tức thời.
4. **Buộc reauthentication/step-up** tại OP cho thao tác tiếp theo hoặc toàn bộ phiên bị nghi ngờ.
5. **Bảo vệ tài khoản và yếu tố khôi phục**, kiểm tra session, client credentials, thiết bị và nhật ký an ninh nếu có chỉ báo xâm nhập.
6. **Thông báo user/admin** với thông tin vừa đủ, tránh tiết lộ token/chi tiết attacker, cung cấp quy trình khôi phục.
7. **Điều tra nguyên nhân** như XSS, log leak, backend retry, client concurrency và cải tiến cơ chế phòng ngừa.

### 12.1. Revoke refresh family chưa chắc revoke access token ngay

Nếu AS thu hồi `RT-2`, client/attacker không thể tiếp tục refresh bằng family đó, nhưng **access token JWT đã phát có thể vẫn hợp lệ tới `exp`** nếu API xác minh offline. Để cô lập sự cố nhanh, cần cơ chế bổ sung: denylist theo token/session/grant, introspection, token lifetime ngắn hoặc policy check liên hệ trạng thái thu hồi. Hãy tính cả độ trễ cache và các API downstream.

### 12.2. Step-up không tự giải quyết token bị đánh cắp

Yêu cầu người dùng nhập passkey/MFA lại có thể giảm rủi ro cho thao tác tương lai, nhưng **không làm bearer token bị đánh cắp biến mất**. Cần vô hiệu hóa credential nghi vấn và xử lý lỗ hổng nguồn gây rò rỉ. Với giao dịch quan trọng, thêm transaction binding, object-level authorization và chống thao tác lặp.

## 13. Ví dụ thiết kế phát hiện anomaly theo cửa sổ thời gian

Giả sử telemetry đã chuẩn hóa bằng fingerprint HMAC cho access token, không ghi raw token. Hệ thống có thể tính trong cửa sổ 5 phút:

~~~text
token_fp       = fp-abc
unique_ASN     = 3
unique_sessions= 2
request_count  = 420
privileged_ops = 7
recent_revoke  = false

Heuristic:
  - unique_ASN cao => một tín hiệu
  - nhiều sessions dùng cùng token => cần điều tra
  - privileged_ops tăng mạnh => tăng mức ưu tiên
  - request_count riêng lẻ => chưa đủ kết luận
~~~

Đây là **số liệu minh họa**, không phải ngưỡng an toàn cố định. Trong công ty có VPN tập trung, một token có thể hợp lệ khi đi qua nhiều POP/ASN; trong mobile app, IP đổi nhanh là bình thường.

### 13.1. Định nghĩa event-time và quyền riêng tư

Thiết kế detector cần:

- **Event time**: thời điểm request thực tế, không nhầm thời gian xử lý log đến muộn.
- **Deduplication**: tránh đếm lại cùng sự kiện do retry của hệ thống ghi log.
- **Correlation key**: token fingerprint, grant family, issuer, client, user/session theo mức có thể và hợp pháp.
- **Windows/TTL**: không giữ fingerprint/IP lâu hơn nhu cầu vận hành, không tạo dữ liệu định danh không giới hạn.
- **Tách môi trường**: không trộn dev/staging/prod hoặc issuer không cùng trust domain.
- **Giải thích lý do**: alert cần ghi những tín hiệu nào dẫn tới quyết định để vận hành có thể điều tra false positive.

### 13.2. Chặn trực tuyến hay phát hiện ngoại tuyến?

- **Inline checks** bắt buộc khi có quy tắc giao thức rõ: refresh token status `USED`, DPoP proof đã seen, sai sender binding, token sai chữ ký/issuer/audience/hạn.
- **Near-real-time detections** hữu ích để giảm thời gian attacker khai thác: cùng bearer token xuất hiện từ thiết bị/mạng khác lạ, nhiều quyền nhạy cảm.
- **Offline analytics** phù hợp điều tra xu hướng và cải tiến policy, không thay được chặn trực tuyến.

Nếu hệ thống phân tích sự kiện bị lỗi, API **không được bỏ qua validation token hoặc object authorization**. Với các biện pháp replay bắt buộc theo giao thức (ví dụ proof `jti`), chính sách fail-open/fail-closed phải được thiết kế tường minh và thiên về fail-closed ở thao tác nhạy cảm.

## 14. Những lỗi triển khai thường gặp

### 14.1. Từ chối mọi request có cùng access-token `jti`

**Sai:** access token Bearer bình thường được dùng nhiều lần. Coi cùng `jti` là replay ở request thứ hai sẽ gây lỗi hàng loạt.

**Đúng:** đánh giá access token theo validity và quyền mỗi lần, kết hợp anomaly detection theo ngữ cảnh; chỉ áp **one-time semantics** nếu giao thức/token type có yêu cầu cụ thể.

### 14.2. Chấp nhận refresh token cũ trong “grace period” quá dễ

**Sai:** sau RT rotation, server vẫn cấp được token mới nhiều lần chỉ từ RT cũ trong 60 giây, tạo cơ hội cho kẻ đã lấy RT cũ.

**Đúng:** giới hạn rotation một lần, xử lý retry qua cơ chế có ràng buộc an toàn hoặc yêu cầu reauthentication nếu kết quả trước bị mất; chính sách grace cần phân tích mối đe dọa rõ.

### 14.3. Chỉ so IP để quyết định token bị đánh cắp

**Sai:** địa chỉ IP thay đổi do NAT, roaming, VPN. Không dùng IP như chứng cứ cryptographic sender ownership.

**Đúng:** kết hợp issuer, client/session, token family, hành vi, DPoP/mTLS nếu có; dùng step-up hoặc cảnh báo theo rủi ro.

### 14.4. Ghi nguyên Bearer token để phát hiện trùng

**Sai:** log, tracing và metrics trở thành kho credential có thể bị đánh cắp, kéo dài rủi ro.

**Đúng:** fingerprint bằng HMAC và log sự kiện tối thiểu, bảo vệ audit key và retention.

### 14.5. Tái sử dụng kết quả introspection quá lâu

**Sai:** token đã bị thu hồi nhưng cache vẫn báo `active=true`, hoặc token mới active vẫn bị cache `false` sau giờ kích hoạt.

**Đúng:** TTL phù hợp mức rủi ro, invalidation, introspection authentication và kiểm tra scope/audience ở RS.

### 14.6. Có DPoP proof nhưng không kiểm tra `ath`/`jti`

**Sai:** chữ ký proof đúng nhưng proof có thể bị replay, hoặc không chứng minh tương ứng access token đang được trình.

**Đúng:** xác minh public-key binding, method/URL, `iat`, `jti`, `ath`, nonce khi áp dụng; replay cache atomic trong khoảng thời gian hợp lý.

### 14.7. Thu hồi family nhưng transaction rollback

**Sai:** code đánh dấu `REVOKED` rồi throw exception khiến transaction tự động rollback, token tiếp tục active.

**Đúng:** commit quyết định revoke/audit trước khi trả `invalid_grant`, có test integration cho transaction khi reuse.

### 14.8. Chỉ revoke refresh token, bỏ mặc access token đang dùng

**Sai:** bỏ qua nguy cơ access token hiện hành vẫn được attacker sử dụng tới `exp`.

**Đúng:** chọn chính sách access-token invalidation thích hợp dựa trên khả năng revoke, độ nhạy tài nguyên và các token đã cấp.

## 15. Bộ kiểm thử bắt buộc

| Ca kiểm thử | Kết quả kỳ vọng |
| --- | --- |
| Cùng access token gọi `GET` nhiều lần hợp lệ | **Không** bị coi là replay chỉ vì reuse |
| JWT access token có `jti` lặp trên hai request hợp lệ | Vẫn cho phép nếu token và policy hợp lệ |
| Access token từ hai ASN khác nhau do VPN hợp lệ | Tín hiệu rủi ro; tránh tự động khóa vô căn cứ |
| JWT sai chữ ký/issuer/audience/expired | Từ chối trước khi phân quyền |
| Scope đúng nhưng resource thuộc user/tenant khác | Từ chối object authorization |
| `RT-1` dùng một lần thành công | `RT-1=USED`, `RT-2=ACTIVE` |
| `RT-1` dùng lại sau rotation | Từ chối, ghi reuse event, revoke family theo policy |
| Hai refresh request đồng thời dùng `RT-1` | Tối đa một lần thành công, không tạo hai active successors |
| Network timeout sau khi refresh thành công nhưng response mất | Không vô tình cấp thêm RT bằng token cũ; flow phục hồi rõ |
| `RT-2` dùng sau khi family đã revoked | Từ chối |
| Token không biết fingerprint/family | Từ chối, không revoke nhầm family khác |
| Token dùng sai client/grant hoặc đã hết hạn | Từ chối |
| Reuse branch ghi `REVOKED` rồi trả lỗi HTTP | Transaction revoke thực sự **được commit** |
| Refresh token bị lộ trong log/callback | Không xuất hiện raw credential trong telemetry |
| DPoP proof dùng lại cùng `jti` trong cửa sổ | Từ chối request proof bị replay |
| DPoP proof `ath` không khớp access token | Từ chối |
| DPoP key thumbprint không khớp `cnf.jkt` | Từ chối |
| Access token DPoP-bound bị gửi như Bearer token thuần | Từ chối theo sender-binding policy |
| Replay cache phân tán bị race | Chỉ một proof được nhận nếu semantics một lần |
| Revoke refresh family nhưng JWT access token còn hạn | Test đường vô hiệu access token theo chính sách hệ thống |
| Detector/telemetry ngừng hoạt động | Token validation và resource authorization vẫn hoạt động an toàn |
| User đổi mạng/thiết bị hợp lệ | Có đường xử lý false positive, không làm rò dữ liệu khác |

### 15.1. Kiểm thử có điều khiển thời gian

Nên sử dụng `Clock` hoặc virtual time để kiểm tra:

- Access token trước/sau `exp`, refresh token expiration và family status.
- Cửa sổ replay của DPoP `iat`/`jti` và TTL cache.
- Reuse ngay sau rotation, sau network timeout hoặc nhiều worker đồng thời.
- Cache introspection sau revoke và độ trễ cập nhật giữa gateway, AS, RS.

Với test bảo mật, mock `Authentication` chỉ kiểm tra quyền ứng dụng; cần integration tests thực sự đi qua token decoder/introspection, khóa/timing/replay store để khẳng định kiểm soát hoạt động.

## 16. Tình huống thực tế

**Tình huống A — User gọi API 30 lần với một access token.** Mobile app đồng bộ lịch sử giao dịch, dùng cùng Bearer token cho 30 requests trong 2 phút.

**Phân tích:** Đây có thể là hành vi hoàn toàn hợp lệ. API phải xác minh token/quyền từng request; không từ chối vì thấy `jti` lặp.

**Tình huống B — Refresh token cũ xuất hiện trở lại.** Backend vừa đổi `RT-4` lấy `RT-5`, nhưng một request tiếp tục dùng `RT-4`.

**Phân tích:** AS phải từ chối, ghi reuse signal và thực thi chính sách family. Nguyên nhân có thể là attacker hoặc retry/race; client cần single-flight refresh, AS cần rotation atomic, và người dùng có thể phải đăng nhập lại.

**Tình huống C — JWT truy cập từ hai quốc gia trong vài giây.** Một access token xuất hiện qua IP tại hai nơi rất xa.

**Phân tích:** Đáng cảnh báo nhưng geo-IP không tuyệt đối chính xác. Cần kết hợp thiết bị, phiên, hành vi và endpoint nhạy cảm; step-up/revoke token khi rủi ro thực tế cao.

**Tình huống D — Kẻ tấn công lấy access token nhưng không có khóa DPoP.** Token bị rò rỉ vào log của một dịch vụ giám sát.

**Phân tích:** Nếu token thực sự được ràng buộc với khóa DPoP và API kiểm tra proof/binding đầy đủ, bản sao access token riêng lẻ không đủ để gọi API. Tuy nhiên cần xử lý nguồn rò rỉ, xem xét quyền riêng tư của claims và kiểm tra không có đường Bearer fallback.

**Tình huống E — Token family bị revoke nhưng API vẫn hoạt động.** AS thu hồi refresh grant sau reuse, nhưng access token JWT đã phát vẫn được API chấp nhận.

**Phân tích:** Đây là hệ quả của JWT access token được xác minh offline nếu không có denylist/version/lookup. Cần quyết định độ trễ thu hồi chấp nhận được; với thao tác nhạy cảm, phải bổ sung cơ chế vô hiệu kịp thời.

## 17. Checklist thiết kế và vận hành

1. **Định nghĩa rõ reuse theo token type:** access token có thể dùng nhiều lần; rotated refresh token và DPoP proof có điều kiện one-time riêng.
2. **Ràng buộc trust:** xác minh JWT signature/algorithm, issuer, audience, `exp`, `nbf`, loại token; hoặc introspection cho opaque token.
3. **Thiết kế refresh grant/token family:** random token đủ entropy, fingerprint lưu an toàn, trạng thái `ACTIVE/USED/REVOKED`, successor và cơ chế revoke.
4. **Bảo đảm rotation atomic:** lock/CAS, unique constraint, không cho hai active successors, commit trạng thái thu hồi trước khi trả lỗi.
5. **Giảm race hợp lệ:** client single-flight, BFF, đồng bộ nhiều tab và chính sách xử lý timeout không replay.
6. **Quan sát access-token anomaly:** correlation an toàn, phân biệt tín hiệu cứng và mềm; đánh giá VPN/NAT/roaming trước khi revoke rộng.
7. **Giới hạn telemetry:** không log token/secret; HMAC fingerprint, retention, phân quyền audit và chống lộ dữ liệu cá nhân.
8. **Xem xét sender-constrained token:** DPoP hoặc mTLS khi mô hình rủi ro cần; kiểm tra key binding và proof replay đầy đủ.
9. **Phản ứng theo scope sự cố:** revoke family/session/token liên quan, kiểm tra access token đã cấp, buộc reauthentication khi cần.
10. **Bảo vệ điểm cấp token:** TLS, xác thực client theo loại client, grant, scope, rate limiting và thông báo lỗi không lộ chi tiết.
11. **Giữ nguyên authorization tại API:** scope, tenant, quyền sở hữu tài nguyên và transaction binding không được bỏ qua.
12. **Kiểm thử âm và concurrency:** replay RT, DPoP proof, unknown family, mất response, rollback, race và cache expiration.

## 18. Tài liệu tham khảo

- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): Bearer token semantics và rủi ro token bị lộ/đánh cắp.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): refresh token rotation, sender-constrained refresh tokens, replay detection và biện pháp bảo mật OAuth.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): proof JWT, `jti`, `htm`, `htu`, `iat`, `ath`, `cnf.jkt` và chống replay.
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705): mTLS, certificate-bound access token và `cnf`.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): trạng thái `active`, metadata và introspection cho opaque token.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): claims `jti`, `exp`, `iss`, `aud` và vòng đời JWT.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): JWT access token và xác minh đúng loại/audience của resource server.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): refresh token grant, phản hồi `invalid_grant` và vai trò authorization server.
- [OWASP API Security Top 10 — Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/): không bỏ qua phân quyền trên đối tượng khi token hợp lệ.

**Ghi nhớ:** **Reuse detection phải dựa trên ngữ nghĩa của từng credential.** Access token Bearer thường được sử dụng lặp lại hợp lệ, nên cần tín hiệu ngữ cảnh để phát hiện hành vi bất thường. Refresh token rotation tạo dấu vết rõ khi token cũ được dùng lại, nhưng phải xử lý transaction/concurrency và false positive; DPoP proof có quy tắc `jti` chống replay riêng. Việc phát hiện chỉ hữu ích khi đi cùng **thu hồi đúng phạm vi, bảo vệ token, issuer/audience/scope validation và phân quyền tại resource server**.

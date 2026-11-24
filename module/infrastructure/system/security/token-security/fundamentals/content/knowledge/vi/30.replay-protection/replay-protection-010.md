# Detect reuse

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Định nghĩa **reuse** và **replay** trong hệ thống token bảo mật, phân biệt **dùng lại hợp lệ** với **phát lại trái phép**.
- Hiểu cơ chế **refresh token rotation** và việc phát hiện refresh token đã sử dụng lại (**refresh token reuse detection**) theo **token family / grant**.
- Phân biệt trạng thái **active, consumed, revoked, expired, unknown**; không coi mọi request thất bại là bằng chứng chắc chắn có kẻ tấn công.
- Thiết kế thao tác **consume-once nguyên tử** để hai request đồng thời không thể cùng đổi một refresh token hoặc authorization code.
- Nắm vai trò của **DPoP proof jti, iat, htm, htu, ath, nonce** và kho chống phát lại theo thời gian (**replay cache**).
- Phân biệt **access-token jti, refresh-token family ID, DPoP jti, authorization code ID và HTTP idempotency key**; những định danh này không có cùng ý nghĩa.
- Giải thích vì sao **chữ ký JWT, JWE encryption, TLS và expiration** không tự ngăn Bearer credential bị sao chép và sử dụng lại.
- Xử lý lỗi mạng, retry, client nhiều tab, nhiều replica, clock skew và eventual consistency mà không làm suy yếu chính sách bảo mật.
- Thiết kế data model, transaction SQL, Java pseudocode, observability, incident response, negative tests và checklist triển khai.
- Vận dụng phát hiện reuse đúng với OAuth 2.0/OIDC, access token, refresh token, DPoP/mTLS và phân quyền Resource Server.

## 1. Detect reuse nghĩa là gì?

**Reuse** nghĩa là cùng một token hoặc bằng chứng xác thực được trình lại. Nó chỉ trở thành **replay đáng ngờ** khi giao thức, trạng thái và ngữ cảnh yêu cầu credential hoặc proof đó **không được tái sử dụng như vậy**.

Hãy xét ba thao tác:

1. **Dashboard gọi GET /orders hai lần bằng cùng Bearer access token còn hạn:** có thể hoàn toàn bình thường.
2. **Client đổi refresh token RT-1 và nhận RT-2, sau đó RT-1 lại được gửi đến token endpoint:** thường là reuse đáng ngờ theo chính sách refresh token rotation.
3. **Một DPoP proof JWT có cùng jti được gửi lại trong thời gian chống replay:** cần bị phát hiện/từ chối theo quy tắc DPoP.

Vì thế không thể có một hàm chung kiểu:

~~~text
if tokenSeenBefore(token):
    rejectAndRevokeAll()
~~~

Cách trên sẽ làm hỏng OAuth Bearer access token hợp lệ và có thể gây denial-of-service.

**Detect reuse phải được định nghĩa theo loại credential, one-time semantics, trust boundary, cửa sổ thời gian và hậu quả mong muốn.**

### Bảng quyết định nhanh

| Vật liệu được trình | Dùng lại có bình thường không? | Reuse detection nên làm gì? |
| --- | --- | --- |
| **Bearer access token** | Có, nhiều HTTP requests trong thời hạn và audience hợp lệ. | Không coi chỉ việc xuất hiện lại là compromise; dùng risk signals, sender-binding và revocation khi cần. |
| **Refresh token đang ACTIVE** | Có thể dùng để refresh một lần nếu hệ thống áp rotation. | Consume nguyên tử, phát RT kế tiếp, chuyển RT cũ sang CONSUMED. |
| **Refresh token đã CONSUMED** | Không, theo rotation strict. | Từ chối; kích hoạt chính sách compromise/revoke family theo threat model. |
| **Authorization code** | Không; code được redeem tối đa một lần. | Atomic one-time redemption; từ chối code redeem lại. |
| **DPoP proof JWT** | Không được phát lại cùng jti trong validation window. | Kiểm proof và dùng dedup cache nguyên tử. |
| **OIDC nonce** | Ràng một authentication response với transaction cụ thể. | Kiểm nonce gắn state/transaction; không biến nonce thành global token one-time một cách tùy tiện. |
| **Idempotency key của HTTP business request** | Có thể được gửi lại cho cùng một operation/retry. | Trả kết quả tương ứng theo contract, tránh thực hiện side effect lần hai. |
| **mTLS-bound access token** | Có thể gọi nhiều request hợp lệ. | Kiểm certificate binding ở từng request, không yêu cầu access token single-use. |

## 2. Threat model: attacker có gì và muốn làm gì?

Giả sử hệ thống có:

- **Authorization Server (AS)** cấp access token (AT) và refresh token (RT).
- **OAuth client** là ứng dụng Dashboard hoặc service backend.
- **Resource Server (RS)** là Orders API.
- **Người dùng** có quyền orders:read, không có orders:approve.
- **Attacker** có thể lấy token từ log, browser storage, malware, request capture hoặc server bị xâm nhập.

Mục tiêu của attacker có thể là:

- Dùng AT bị đánh cắp để gọi API cho đến khi hết hạn.
- Dùng RT bị đánh cắp để liên tục đổi AT mới hoặc duy trì phiên.
- Phát lại một authorization code hoặc DPoP proof.
- Đánh lừa hệ thống bằng hai request đồng thời để cùng tiêu thụ một credential chỉ được dùng một lần.
- Tạo false-positive reuse để gây gián đoạn session của người dùng.
- Lợi dụng replay cache không nhất quán giữa các replica, cửa sổ grace quá rộng hoặc lỗi network retry.

~~~mermaid
flowchart LR
    AS["Authorization Server"] -->|"AT / RT"| C["OAuth Client"]
    C -->|"Bearer AT"| RS["Orders API"]
    C -->|"RT refresh request"| AS
    X["Attacker lấy bản sao RT"] -.->|"Trình lại RT đã dùng"| AS
    Y["Attacker lấy DPoP proof"] -.->|"Phát lại proof"| RS
    AS --> DET["Refresh reuse detector / family state"]
    RS --> PROOF["DPoP verification + replay cache"]
~~~

### Lớp bảo vệ bổ trợ

| Lớp | Bảo vệ được | Không tự bảo vệ |
| --- | --- | --- |
| **TLS** | Chống nghe lén/sửa trên transport khi cấu hình đúng. | Token bị copy từ endpoint, memory hoặc log. |
| **JWT/JWS signature** | Phát hiện claims bị sửa, chứng thực nguồn ký theo key trust. | Replay nguyên Bearer token. |
| **JWE encryption** | Giữ bí mật claims theo recipient/key trust. | Dùng lại nguyên chuỗi Bearer JWE. |
| **exp / nbf** | Giới hạn khoảng hiệu lực của token. | Dùng lại nhiều lần trong thời gian còn hiệu lực. |
| **Refresh token rotation** | Biến RT cũ thành credential đã tiêu thụ; giúp phát hiện bản sao RT. | Ngăn tuyệt đối cuộc gọi dùng RT bị đánh cắp **trước** client hợp lệ. |
| **DPoP/mTLS binding** | Ràng AT với key/certificate bên gọi theo profile. | Mọi dạng compromise khi attacker chiếm cả token và private key/client runtime. |
| **Token revocation/introspection** | Có thể chặn AT/RT/grant trước khi hết hạn theo kiến trúc. | Tự đồng bộ tức thì với mọi RS cache nếu không thiết kế propagation. |

**Không có một cơ chế đơn lẻ giải quyết toàn bộ replay risk.** Cần biết attacker có chỉ token, hay cả sender private key/secret và quyền gọi authorization server.

## 3. Reuse và replay không đồng nghĩa

**Reuse** mô tả hành vi lặp. **Replay attack** là cố ý sử dụng lại một credential, proof hoặc thông điệp đã hợp lệ để vượt mục tiêu freshness hoặc ownership của protocol.

Ví dụ Bearer AT:

~~~http
GET /api/orders/123 HTTP/1.1
Host: orders.example.test
Authorization: Bearer EXAMPLE_ACCESS_TOKEN
~~~

Một client hợp lệ có thể gửi request này nhiều lần. Nếu API gắn **used=true** lên AT và chặn request thứ hai, nó đã tự đặt semantics one-time không có trong mô hình Bearer thông thường.

Nhưng với RT rotation:

~~~http
POST /oauth/token HTTP/1.1
Host: identity.example.test
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token=EXAMPLE_RT1
~~~

Nếu RT1 đã đổi thành RT2, request trên xuất hiện lại có thể là:

- Attacker dùng bản RT1 bị đánh cắp.
- Client gửi retry sau khi mất response chứa RT2.
- Hai tab/process của cùng client vô tình cùng refresh bằng RT1.
- Proxy hoặc retry library lặp POST không kiểm soát.
- Client vẫn giữ bản RT1 vì không lưu RT2 thành công.
- Lỗi server rollback/replication khiến trạng thái RT1 không nhất quán.

**Phát hiện reuse không tự cho biết ai là attacker.** Nó là một tín hiệu để kích hoạt hành động bảo mật, audit và phục hồi hợp lý.

### Reuse signal khác compromise verdict

Một hệ thống có thể ghi:

~~~text
signal: REFRESH_TOKEN_REUSE_DETECTED
evidence: previous token state = CONSUMED
confidence: credential reuse observed
cause: unknown until investigation
action: revoke active family according to policy
~~~

Không ghi log kiểu **"user đã bị hack"** như kết luận pháp lý/kỹ thuật chắc chắn chỉ từ một request lặp.

## 4. Refresh token rotation: nền tảng detect reuse

**Refresh token** cho phép client xin access token mới tại AS mà không cần bắt người dùng đăng nhập lại mỗi lần. Nó thường có giá trị lâu hơn AT, nên RT bị lộ có thể nguy hiểm.

**Refresh token rotation** thay RT mỗi lần refresh thành công:

~~~text
RT1 --refresh thành công--> RT2
RT1: CONSUMED
RT2: ACTIVE

RT2 --refresh thành công--> RT3
RT2: CONSUMED
RT3: ACTIVE
~~~

Theo OAuth 2.0 Security Best Current Practice (RFC 9700), đối với public clients, refresh tokens cần được **sender-constrained hoặc sử dụng refresh token rotation** để phát hiện replay, khi AS phát RT.

### Luồng tuần tự

~~~mermaid
sequenceDiagram
    participant C as Legitimate Client
    participant AS as Authorization Server
    participant DB as Token/Grant State Store
    participant X as Attacker giữ bản sao RT1

    C->>AS: refresh_token=RT1
    AS->>DB: Atomic consume RT1 nếu ACTIVE
    DB-->>AS: RT1 CONSUMED, issue RT2 ACTIVE
    AS-->>C: AT2 + RT2
    X->>AS: refresh_token=RT1 (reused)
    AS->>DB: Lookup RT1 = CONSUMED
    DB-->>AS: REUSE_DETECTED
    AS->>DB: Revoke active token family/grant theo policy
    AS-->>X: invalid_grant
    C->>AS: refresh_token=RT2
    AS-->>C: invalid_grant nếu family đã revoked
~~~

Tại sao có thể phải revoke cả **active family**? Nếu attacker và client cùng sở hữu RT1, AS thường **không thể phân biệt bên nào đã đổi RT1 trước**. RT2 có thể nằm trong tay attacker. Khi phát hiện RT1 reuse, việc chỉ chặn RT1 có thể vẫn để bản RT2 đã bị attacker chiếm tiếp tục sinh token.

### Ba đặc tính quan trọng

1. **One-time transition:** RT ở trạng thái ACTIVE chỉ được tiêu thụ thành công một lần.
2. **Family lineage:** AS liên kết RT1→RT2→RT3 với một grant/token family để ứng phó khi reuse.
3. **Atomicity:** hai request đồng thời không thể đều thắng và phát hai RT successor hợp lệ từ cùng RT1.

**Rotation không có family state và revoke policy rõ thường chỉ là cấp token mới, chưa đủ để detect reuse đúng nghĩa.**

## 5. Token family / grant và liên kết chuỗi

Một **token family** biểu thị các RT được phát nối tiếp cho cùng một authorization grant hoặc session policy.

~~~mermaid
flowchart LR
    G["Grant / RT family F"] --> A["RT1: CONSUMED"]
    A --> B["RT2: CONSUMED"]
    B --> C["RT3: ACTIVE"]
    C --> D["RT4: FUTURE"]
    X["Reuse RT1 hoặc RT2"] -.-> R["Mark family F COMPROMISED/REVOKED"]
    R -.-> C
~~~

**RT4: FUTURE** chỉ minh họa successor tiềm năng, không phải một credential đã được cấp khi RT3 chưa refresh.

### Những trường nên quản lý

| Thành phần | Dữ liệu | Tác dụng |
| --- | --- | --- |
| **family_id** | ID ngẫu nhiên/không dự đoán được hoặc DB ID nội bộ. | Gom token trong cùng grant lineage. |
| **grant_id** | Authorization grant đã xác minh. | Gắn client, user, consent, scope, audience. |
| **client_id** | Client được cấp RT. | Ngăn RT dùng bởi client khác. |
| **subject/tenant** | User hoặc workload, khi profile có. | Incident scoping, account/tenant separation. |
| **RT identity/digest** | HMAC/hash lookup của RT đủ entropy. | Tra token mà không lưu raw RT trong database. |
| **parent_id / successor_id** | Liên kết token rotation. | Biết token đã tiêu thụ, xác định active descendant. |
| **status** | ACTIVE, CONSUMED, REVOKED, EXPIRED. | Thực thi one-time semantics và reuse detection. |
| **issued_at / consumed_at** | Mốc issuance/consume. | Forensics, retries, race analysis. |
| **family_expires_at** | Lifetime tối đa của grant/RT family. | Ngăn rotation kéo dài quyền vô hạn. |
| **sender binding** | DPoP/mTLS/client identity khi áp dụng. | Kiểm credential có đúng holder không. |
| **reason / incident** | REUSE_DETECTED, USER_LOGOUT, ADMIN_REVOKE... | Phân biệt nguyên nhân revoke. |

Từng JWT/RT được gắn lineage **ở AS storage**. Không để client tự gửi family_id rồi dùng làm authority để revoke family của người khác.

### Hạn chế vòng đời family

Một token mới có thể được cấp sau mỗi lần refresh, nhưng hệ thống cần chính sách:

~~~text
family.absoluteExpiry = grantStart + maximumRefreshLifetime
successorExpiry = min(now + perTokenLifetime, family.absoluteExpiry)
~~~

Đây là **ví dụ policy**, không phải một thời hạn bắt buộc của RFC. Việc cấp successor **không được tự kéo dài vô hạn thời hạn cuối** nếu chính sách có lifetime tuyệt đối.

### Family khác account session toàn cục

Một user có thể đăng nhập từ điện thoại, browser và BFF với **ba grants/token families** khác nhau. Reuse một family không nhất thiết phải logout toàn bộ thiết bị nếu risk policy không yêu cầu. Ngược lại, compromise lan rộng có thể cần account-wide response.

**Phạm vi revoke phải có quy tắc rõ:** token bị lặp, active descendant, whole family, grant hoặc account/session ở mức rộng hơn.

## 6. Tín hiệu reuse và hệ quả

| Kết quả tra RT | Diễn giải | Hành động thường phù hợp |
| --- | --- | --- |
| **ACTIVE** | Token có thể đổi nếu mọi điều kiện khác đạt. | Atomic consume + issue successor. |
| **CONSUMED** | Token đã được đổi một lần. | Reuse signal; từ chối; revoke family theo chính sách strict rotation. |
| **REVOKED** | Token/grant đã bị vô hiệu trước đó. | Từ chối; không tạo successor; audit. |
| **EXPIRED** | Credential quá thời hạn. | Từ chối; không mặc định đây là reuse compromise. |
| **UNKNOWN** | Không tìm thấy trong trusted store. | Từ chối; tránh dò token existence; không tự đoán family. |
| **WRONG_CLIENT** | Token gắn client khác. | Từ chối; security signal; không để attacker revoke family tùy ý. |
| **BINDING_MISMATCH** | Sai proof of possession/certificate. | Từ chối, audit; áp compromise policy theo threat model. |
| **FAMILY_COMPROMISED** | Family đã bị đánh dấu reuse/compromise. | Từ chối mọi descendant theo family state. |

**Không cung cấp status chi tiết cho client không tin cậy** như “token đã được dùng ở thiết bị khác”. OAuth token endpoint thường trả lỗi chung như **invalid_grant** cho invalid RT. Chi tiết được giữ trong telemetry có phân quyền.

## 7. Kỹ thuật lưu RT: bảo vệ raw token và khả năng tra cứu

Một RT nên được sinh từ CSPRNG đủ entropy. Với opaque RT, AS có thể chỉ lưu **digest tra cứu** thay vì raw token:

~~~text
rawRefreshToken <- CSPRNG(high entropy bytes)
lookupDigest = HMAC_SHA256(serverLookupSecret, rawRefreshToken)
store lookupDigest + family metadata
return rawRefreshToken only to authorized client
~~~

HMAC lookup secret là một lựa chọn vận hành hữu ích để tránh dùng raw RT trong database. Nếu token đủ entropy, SHA-256(token) cho lookup cũng có thể phù hợp tùy threat model; HMAC giúp tách fingerprint khỏi các bên không có secret.

### Điều không nên làm

- Không lưu raw RT vào access logs, metrics labels, crash reports hoặc ticket.
- Không dùng password người dùng làm RT hoặc HMAC secret.
- Không dùng một chuỗi RT ngắn, có thể dự đoán để rồi hy vọng hash sẽ cứu.
- Không tái dùng HMAC lookup secret cho JWT signing, password hashing hay webhook MAC.
- Không gửi family_id nhạy cảm làm quyền thao tác revoke nếu không đối chiếu grant/client.
- Không cho phép SQL/Redis logs chứa RT raw trong câu lệnh.
- Không chỉ xóa mọi record RT cũ: cần giữ **tombstone/used-token evidence** đủ theo security retention để nhận ra reuse trong khoảng liên quan.

### Tombstone và retention

Nếu record RT1 bị xóa ngay khi đổi thành RT2, khi attacker gửi RT1 lần nữa, AS chỉ thấy **UNKNOWN** và không biết family nào cần revoke.

Cần giữ một trong các cơ chế:

- CONSUMED record và family_id.
- Tombstone ánh xạ RT digest → family_id/status.
- Một authenticated lineage/reuse ledger tương đương.

**Retention phải bao phủ khoảng thời gian RT cũ có thể bị phát lại** theo threat model, nhưng cũng phải theo chính sách privacy/retention. Không lưu raw token chỉ vì muốn detect reuse.

## 8. Atomic consume: điều kiện bắt buộc để phát hiện reuse

Giả sử hai request **A và B** gửi RT1 gần như cùng lúc:

~~~text
T1: A đọc RT1.status = ACTIVE.
T2: B đọc RT1.status = ACTIVE.
T3: A phát RT2 và đánh dấu RT1 CONSUMED.
T4: B phát RT3 và đánh dấu RT1 CONSUMED.
~~~

Nếu transaction không được thiết kế đúng, **hai successor RT2 và RT3 có thể cùng hợp lệ**, phá semantics one-time của refresh token rotation.

### State transition mong muốn

~~~mermaid
stateDiagram-v2
    [*] --> ACTIVE: issue RT
    ACTIVE --> CONSUMED: atomic successful refresh
    ACTIVE --> REVOKED: grant revoke / logout / admin action
    ACTIVE --> EXPIRED: expiry policy
    CONSUMED --> REUSE_DETECTED: presented again
    REUSE_DETECTED --> [*]: family revocation response
    REVOKED --> [*]
    EXPIRED --> [*]
~~~

Trong mô hình này, **REUSE_DETECTED có thể chỉ là event/result**, không nhất thiết phải là trạng thái lưu riêng cho token; record token vẫn ở CONSUMED và family chuyển COMPROMISED/REVOKED.

### Nguyên tắc

- **Một RT ACTIVE có tối đa một lần chuyển thành CONSUMED thành công.**
- Việc tạo successor, ghi parent-child lineage và cập nhật family state phải có tính **atomic/transactional** phù hợp.
- Không trả RT2 cho client **trước khi** state của RT1 và RT2 được commit bền vững.
- Khi thấy RT1 đã CONSUMED, phải kích hoạt nhánh reuse một cách nhất quán giữa các replicas.
- Nếu một transaction rollback, RT1 không được chuyển CONSUMED trong khi RT2 đã có thể được sử dụng, và ngược lại.

**Một Redis GET + SET tách rời hoặc một UPDATE không có điều kiện đủ chặt có thể tạo race.** Cần atomic compare-and-set, database transaction hoặc script có semantics phù hợp.

## 9. Data model tối thiểu cho refresh token family

Schema minh họa (PostgreSQL-like) cho opaque RT lookup. Đây là **mẫu thiết kế để học**, cần điều chỉnh constraints, indexes, retention và consistency thực tế.

~~~sql
CREATE TABLE refresh_families (
    family_id          UUID PRIMARY KEY,
    grant_id           UUID NOT NULL,
    client_id          TEXT NOT NULL,
    subject_id         TEXT,
    state              TEXT NOT NULL CHECK (
        state IN ('ACTIVE', 'COMPROMISED', 'REVOKED', 'EXPIRED')
    ),
    absolute_expires_at TIMESTAMPTZ NOT NULL,
    current_token_id   UUID,
    created_at         TIMESTAMPTZ NOT NULL,
    revoked_at         TIMESTAMPTZ,
    revoke_reason      TEXT,
    generation         BIGINT NOT NULL DEFAULT 1
);

CREATE TABLE refresh_tokens (
    token_id          UUID PRIMARY KEY,
    family_id         UUID NOT NULL
                      REFERENCES refresh_families(family_id),
    parent_token_id   UUID REFERENCES refresh_tokens(token_id),
    token_lookup_hmac BYTEA NOT NULL UNIQUE,
    state             TEXT NOT NULL CHECK (
        state IN ('ACTIVE', 'CONSUMED', 'REVOKED', 'EXPIRED')
    ),
    issued_at         TIMESTAMPTZ NOT NULL,
    consumed_at       TIMESTAMPTZ,
    expires_at        TIMESTAMPTZ NOT NULL,
    successor_token_id UUID
);

-- Mỗi family có tối đa một RT ACTIVE.
CREATE UNIQUE INDEX one_active_rt_per_family
ON refresh_tokens (family_id)
WHERE state = 'ACTIVE';

-- Cùng một parent không được có hai successors.
CREATE UNIQUE INDEX one_successor_per_parent
ON refresh_tokens (parent_token_id)
WHERE parent_token_id IS NOT NULL;
~~~

### Điều gì chưa có trong schema minh họa?

- Key version cho token lookup HMAC và chiến lược rotate lookup secret.
- Partitioning/tombstone retention, indexes theo issued_at/consumed_at.
- Sender-constrained RT metadata (DPoP/mTLS, certificate thumbprint).
- Consent/scopes/resource authorization và refresh token lifetime bounds.
- Multi-region writes, fencing hoặc globally linearizable family state.
- Encryption at rest, audit event outbox và transaction isolation.
- Phân quyền DB để resource server không đọc refresh token records.

**Schema không phải “production-ready DDL”.** Nó minh họa quan hệ family/parent/status/lookup cần để detect reuse.

### Tại sao cần unique indexes?

- Unique token digest ngăn lookup ambiguity.
- Unique active RT per family ngăn tồn tại hai descendant đang hoạt động.
- Unique parent_token_id ngăn một parent sinh hai successor trong concurrent transactions.

**Constraint hỗ trợ transaction; nó không thay kiểm token client binding và family state.**

## 10. SQL transaction: consume RT1 và tạo RT2

Một cách an toàn là **khóa family row trước**, sau đó khóa token row, kiểm trạng thái và cập nhật successor cùng một transaction. Ví dụ giản lược:

~~~sql
BEGIN;

-- Ứng dụng đã tìm token row qua lookup digest và xác thực
-- các điều kiện client/grant/sender-bound context.
-- Lock family theo một thứ tự thống nhất trên mọi code paths.
SELECT family_id, state, absolute_expires_at, current_token_id
FROM refresh_families
WHERE family_id = :family_id
FOR UPDATE;

SELECT token_id, family_id, state, expires_at
FROM refresh_tokens
WHERE token_id = :presented_token_id
  AND family_id = :family_id
FOR UPDATE;

-- Branch trong application:
-- a) family != ACTIVE -> DENY
-- b) token == CONSUMED -> REUSE DETECTED
-- c) token != ACTIVE / expired / wrong current token -> DENY
-- d) token ACTIVE + valid binding -> tiếp tục

-- Sau khi kiểm (d), RT1 ngừng ACTIVE trước khi tạo RT2:
UPDATE refresh_tokens
SET state = 'CONSUMED',
    consumed_at = CURRENT_TIMESTAMP
WHERE token_id = :presented_token_id
  AND state = 'ACTIVE';

-- Bắt buộc affected_rows = 1, nếu không ROLLBACK/handle race.
-- Raw RT2 phải được sinh bằng CSPRNG ở application;
-- database chỉ lưu lookup digest, không lưu RT2 plaintext.
INSERT INTO refresh_tokens (
    token_id, family_id, parent_token_id, token_lookup_hmac,
    state, issued_at, expires_at
) VALUES (
    :rt2_id, :family_id, :presented_token_id, :rt2_lookup,
    'ACTIVE', CURRENT_TIMESTAMP, :rt2_expires
);

UPDATE refresh_tokens
SET successor_token_id = :rt2_id
WHERE token_id = :presented_token_id;

UPDATE refresh_families
SET current_token_id = :rt2_id,
    generation = generation + 1
WHERE family_id = :family_id
  AND state = 'ACTIVE';

-- Bắt buộc affected_rows = 1.
COMMIT;
~~~

Sau **COMMIT** thành công, AS mới có thể trả **AT2 và RT2** cho client. Access token có thể đã được ký ở bước trước nhưng **không được công bố** cho caller nếu transaction thất bại.

### Khi request B đến đồng thời

Request B khóa cùng family và chờ. Khi request A commit, B thấy RT1 ở trạng thái CONSUMED. B phải xử lý **reuse event** theo policy, chứ không tạo successor mới.

Nếu hệ thống muốn tách **unexpected retry** và **compromise**, cần giao thức và cơ chế nhận diện retries được thiết kế riêng; không đơn giản cho CONSUMED RT đổi thêm một lần theo thời gian grace mà không đánh giá rủi ro.

### Reuse branch và revoke family

Phần ứng dụng khi đã khóa family:

~~~sql
-- Pseudocode SQL; chỉ chạy khi xác định token thuộc family
-- và điều kiện reuse được xác thực theo policy.
UPDATE refresh_families
SET state = 'COMPROMISED',
    revoked_at = CURRENT_TIMESTAMP,
    revoke_reason = 'REFRESH_TOKEN_REUSE',
    generation = generation + 1
WHERE family_id = :family_id
  AND state = 'ACTIVE';

UPDATE refresh_tokens
SET state = 'REVOKED'
WHERE family_id = :family_id
  AND state = 'ACTIVE';

-- Ghi audit/outbox event trong cùng transaction.
-- COMMIT, sau đó response invalid_grant.
~~~

**Không cho một unknown RT string tự chỉ định family_id của nạn nhân và revoke family đó.** Phải tra digest → token record → family đã tồn tại, kiểm client/context và chống abuse. Bất kỳ ai giữ được bản RT cũ có thể cố ý gây family revoke; đó là một phần trade-off của replay detection, cần bảo vệ storage và rate-limit.

### Family lock ordering

Mọi flow thay đổi RT family (refresh, logout, admin revoke, reuse handling) phải dùng **consistent lock ordering** để giảm deadlock: thường khóa family trước rồi token. Nếu các flow khác khóa ngược, hệ thống có thể deadlock dưới tải thật.

## 11. Refresh request: HTTP và kết quả lỗi

Request (giá trị giả không dùng được):

~~~http
POST /oauth/token HTTP/1.1
Host: identity.example.test
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token=EXAMPLE_REFRESH_TOKEN
~~~

Với confidential client, còn phải **authenticate client** theo phương thức đã đăng ký. Với public client, áp sender-constraining hoặc rotation theo chính sách AS, kiểm client binding và các điều kiện refresh. Các giá trị ví dụ không phải credential thật.

### Refresh thành công

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "EXAMPLE_NEW_ACCESS_TOKEN",
  "token_type": "Bearer",
  "expires_in": 900,
  "refresh_token": "EXAMPLE_RT2"
}
~~~

Nếu AS phát rotation, client **phải thay RT cũ bằng RT mới một cách bền vững và an toàn**. Không tiếp tục dùng RT1 cho lần refresh tiếp theo.

### Refresh token đã sử dụng lại

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json
Cache-Control: no-store

{
  "error": "invalid_grant"
}
~~~

Không cần trả các thông tin như **family_id, client IP trước đó, user identity, RT successor token ID hoặc nguyên nhân security cụ thể** cho người trình token. Những dữ kiện đó thuộc audit nội bộ.

### Điều quan trọng sau invalid_grant

- Client hợp lệ nên xóa credential family bị từ chối và kích hoạt **reauthentication/recovery** phù hợp.
- Không loop retry vô hạn với RT cũ.
- Không tự chuyển sang password grant hoặc một bypass flow kém an toàn.
- Nếu server đã revoke whole family, những RT successors của family ấy phải bị chặn, dù client còn giữ RT2.

## 12. Mất response khi refresh: source của false-positive reuse

Một lỗi thực tế:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant AS as AS
    participant DB as RT family store
    C->>AS: Refresh bằng RT1
    AS->>DB: RT1 CONSUMED, RT2 ACTIVE (COMMIT)
    AS--xC: Response AT2 + RT2 bị mất trên mạng
    C->>AS: Retry POST với RT1
    AS->>DB: RT1 đã CONSUMED
    DB-->>AS: REUSE_DETECTED
    AS-->>C: invalid_grant; family có thể bị revoke
~~~

**Server không thể biết chắc đó là retry của client hợp lệ hay attacker có bản RT1** chỉ từ RT1. Đây là một ranh giới tin cậy cố hữu của bearer RT rotation.

### Biện pháp phía client

1. Dùng **single-flight refresh**: nhiều requests cần token mới cùng chờ một refresh operation.
2. Đồng bộ việc cập nhật RT giữa tabs/processes theo platform (nếu có).
3. Không để HTTP client tự động retry POST token endpoint mà không có contract.
4. Lưu RT2 an toàn và **atomic** trước khi sử dụng RT2 cho lần refresh kế tiếp.
5. Không giữ bản RT1 trong storage lâu hơn cần thiết.
6. Nếu gặp invalid_grant, dừng refresh loop và yêu cầu reauthentication khi phù hợp.
7. Kiểm vùng lỗi mobile/offline/background service cùng refresh một session.

### Grace period: lợi và hại

Một số hệ thống cân nhắc grace period ngắn để giảm false positives do network loss hoặc concurrent refresh.

**Rủi ro:** nếu cho RT1 đã tiêu thụ được dùng lại trong grace mà không có binding bảo vệ, attacker giữ RT1 cũng có thể refresh trong khoảng đó và né reuse detection.

Các phương án cần security review:

- **Không cho grace** và chấp nhận reauthentication khi retry không an toàn.
- Một **idempotent refresh retry protocol** gắn với cùng authenticated client/sender key và operation ID đáng tin, có cache response bảo vệ nghiêm ngặt.
- Dùng **sender-constrained refresh tokens** để giảm khả năng bản RT bị copy sử dụng bởi bên không giữ key.
- Thiết kế response recovery riêng thay vì phát hai successors độc lập.

**Không có một grace window “mặc định an toàn” áp dụng cho mọi OAuth client.** Nếu xây grace, phải phân tích người tấn công có thể biết cả token và idempotency key/request headers hay không.

## 13. Idempotency khác với phát hiện reuse

Trong nghiệp vụ, idempotency giúp **lặp cùng operation mà không nhân đôi side effect**. Trong bảo mật credential, một giá trị one-time thường yêu cầu **request thứ hai bị từ chối**.

| Khái niệm | Dùng để | Ví dụ |
| --- | --- | --- |
| **Refresh token rotation** | Phát RT successor mới, chặn credential cũ. | RT1 dùng lần hai → invalid_grant/reuse signal. |
| **Authorization code one-time** | Chặn code được redeem nhiều lần. | Code1 redeem lần hai → fail. |
| **DPoP proof jti** | Chống dùng lại cùng proof trong replay window. | JTI của một proof được trình lại → fail. |
| **HTTP idempotency key** | Nhận diện retry cùng một business operation. | POST /orders lặp với cùng key → không tạo order thứ hai. |

Không đơn giản dùng một **Idempotency-Key** do client tự đặt để đổi lại RT1 đã CONSUMED mà không có kiểm sender binding và một recovery contract an toàn. Nếu attacker copy được request đầy đủ, nó có thể copy cả idempotency key.

### Business POST khác token refresh

Order service có thể trả cùng kết quả tạo đơn khi client gửi lại cùng idempotency key, nhưng vẫn phải kiểm **authorization và token validity của mỗi request**.

**Idempotency không cho phép bỏ qua OAuth authentication.** Một idempotency key không phải Bearer credential, và không phải bằng chứng rằng caller hiện tại là người đã thực hiện request gốc.

## 14. Phạm vi phát hiện reuse theo từng lớp

Có ít nhất ba nơi có thể xử lý reuse:

~~~mermaid
flowchart TD
    C["Client"] --> AS["Authorization Server token endpoint"]
    C --> RS["Resource Server"]
    C --> APP["Business API operation"]
    AS --> RT["RT family state / grant revocation"]
    RS --> DPOP["DPoP proof validation / replay cache"]
    APP --> IDEMP["Business idempotency / duplicate event tracking"]
~~~

- **AS** chịu trách nhiệm refresh token family và authorization code state.
- **RS** chịu trách nhiệm sender proof/replay validation cho HTTP request nếu dùng DPoP, kiểm AT issuer/aud/scope/expiry.
- **Business API** chịu trách nhiệm idempotency của hành động nghiệp vụ, ví dụ thanh toán hoặc duyệt đơn.

Không để một **global "token reuse cache"** làm cả ba việc mà không phân biệt key, TTL, semantics và hậu quả.

### Ví dụ Orders API

Một user có AT scope orders:read gọi GET /orders ba lần: **chấp nhận** nếu mọi lần đều đúng authorization.

Cùng user gọi POST /orders với cùng idempotency key hai lần: API có thể bảo đảm tạo **một order**, nhưng vẫn kiểm AT/request permissions.

Cùng RT1 được gửi hai lần tại AS sau rotation: AS xử lý **refresh reuse**, không phải Orders API.

Cùng DPoP proof jti được gửi hai lần đến RS: RS xử lý **proof replay**, không nhất thiết revoke cả RT family ngay.

## 15. Không chỉ dựa vào địa chỉ IP hoặc User-Agent

Attacker có thể gửi từ:

- Cùng mạng NAT, VPN hoặc proxy với client hợp lệ.
- Địa chỉ IP khác vì mobile roaming.
- Browser/User-Agent giống client thật.
- Một server/extension đã bị chiếm và có thể dùng cùng session context.

Một heuristic:

~~~text
if same refresh token from new IP:
    definitely attacker
~~~

là sai. IP/UA/ASN/device signals có thể bổ trợ **risk scoring**, nhưng không thay được **cryptographic sender binding** hoặc trạng thái one-time.

### Risk signals có giá trị gì?

- Cùng RT đã CONSUMED được gửi từ nhiều địa lý/network khác nhau.
- DPoP proof bị lặp với cùng jti/htm/htu.
- Repeated invalid_grant trên nhiều client/grants.
- Refresh token dùng sai client binding hoặc từ automation không mong đợi.
- Mẫu AT sử dụng ở audience hoặc endpoint bất thường.
- User/reporting về logout đột ngột sau family revoke.

Những tín hiệu này giúp điều tra/điều chỉnh chính sách; phải cân nhắc **false positive, privacy, retention và tỷ lệ tấn công chủ động gây revoke**.

**Không xem IP như một định danh bảo mật ổn định cho OAuth session.**

## 16. DPoP proof replay: jti không phải refresh token family

**DPoP — Demonstrating Proof of Possession** (RFC 9449) là cơ chế OAuth sender-constraining sử dụng **chữ ký bất đối xứng của client** cho một request cụ thể.

Khác một Bearer token, request dùng DPoP-bound access token cần proof cho thấy caller có private key được ràng với token.

Một DPoP proof thường là JWT có header:

~~~json
{
  "typ": "dpop+jwt",
  "alg": "ES256",
  "jwk": {
    "kty": "EC",
    "crv": "P-256",
    "x": "EXAMPLE_PUBLIC_X",
    "y": "EXAMPLE_PUBLIC_Y"
  }
}
~~~

Public JWK x/y ở đây chỉ là placeholder, không tạo thành một public key hợp lệ. Private key **không được nằm trong DPoP header**.

Claims minh họa khi gọi Orders API:

~~~json
{
  "jti": "proof-id-example-9321",
  "htm": "GET",
  "htu": "https://orders.example.test/api/orders",
  "iat": 1795400000,
  "ath": "EXAMPLE_BASE64URL_SHA256_OF_ACCESS_TOKEN"
}
~~~

Giá trị **iat** chỉ minh họa; server phải dùng thời gian hiện tại của môi trường và chính sách freshness để xác minh. **ath** trong request đến Resource Server ràng proof với access token đi kèm; nó được tính theo RFC 9449, không là chuỗi tùy ý.

### Các trường quan trọng

| Thành phần | Ý nghĩa | Kiểm tra chính |
| --- | --- | --- |
| **typ=dpop+jwt** | Đánh dấu DPoP proof JWT. | Không chấp nhận JWT type khác. |
| **alg** | Thuật toán signature bất đối xứng được profile hỗ trợ. | Không chấp nhận none/HS256 và alg ngoài policy. |
| **jwk** | Public key dùng verify proof. | Dạng public key hợp lệ, không có private fields. |
| **jti** | Định danh duy nhất cho từng proof JWT. | Chặn dùng lại cùng jti trong replay window theo key/realm. |
| **htm** | HTTP method. | Khớp method của request hiện tại. |
| **htu** | HTTP target URI theo quy tắc DPoP. | Khớp URI hiện tại theo RFC normalization, không nhầm proxy host. |
| **iat** | Proof issued-at time. | Nằm trong acceptable freshness window; giới hạn skew. |
| **ath** | Access token hash trong proof gửi RS. | Phải khớp access token của request. |
| **nonce** | Server-issued challenge khi policy yêu cầu. | Phải đúng nonce, thời hạn và replay/issuance policy. |

### Token endpoint khác Resource Server

DPoP proof ở **AS token endpoint** ràng phương thức và URI của token request, và có thể có server nonce. Nó không tự bắt buộc **ath** như khi client trình access token đến Resource Server.

DPoP proof ở **RS** cần kiểm binding với **access token** thông qua ath và public key thumbprint liên kết với confirmation claim của token theo profile.

**Không gán cùng một rule về ath/nonce cho mọi DPoP endpoint mà bỏ qua những khác biệt đã được RFC định nghĩa.**

## 17. DPoP jti replay cache và atomic uniqueness

Một proof JWT có chữ ký đúng **vẫn có thể bị replay nguyên xi** nếu server không lưu trạng thái jti đã thấy trong khoảng thời gian được phép.

### Luồng verify

~~~mermaid
sequenceDiagram
    participant C as DPoP Client
    participant RS as Orders API
    participant KEY as Verified token/key context
    participant CACHE as Shared replay cache

    C->>RS: AT + DPoP proof P1
    RS->>RS: Strict parse proof, typ/alg, signature
    RS->>KEY: Check jkt/ath/htm/htu/iat/nonce binding
    KEY-->>RS: Valid current-request proof
    RS->>CACHE: Atomically insert (realm,jkt,jti) if absent
    CACHE-->>RS: Inserted, first use
    RS-->>C: Authorized result theo scope/permission
    C->>RS: Replay same AT + proof P1
    RS->>KEY: Verify proof/binding
    KEY-->>RS: Structurally valid
    RS->>CACHE: Insert same (realm,jkt,jti) if absent
    CACHE-->>RS: Already exists
    RS-->>C: Reject replayed proof
~~~

Trong thực tế, authentication/authorization cũng còn kiểm issuer, audience, token type, expiry, access token status và business permission. Sơ đồ tập trung vào điểm **detect reuse của proof**.

### Replay key gồm những gì?

Một thiết kế có thể dùng:

~~~text
replayKey = HMAC_SHA256(
    cacheIndexSecret,
    realmId || canonicalKeyThumbprint || DPoP_jti
)
~~~

Đây là **cách tạo cache key nội bộ minh họa**, không phải công thức RFC bắt buộc. Khi dùng phép nối, phải định nghĩa encoding/length-prefix hoặc domain separation để tránh ambiguity. **realmId** cần phản ánh phạm vi RS/AS có yêu cầu uniqueness chung. Nếu cùng DPoP key dùng với nhiều service, mỗi service có thể có own replay state theo trust boundary và RFC profile.

**Đừng dùng chỉ jti làm global cache key nếu không tính đến key/realm**, vì hai client có thể vô tình hoặc cố ý chọn cùng jti. Ngược lại, không ràng uniqueness quá hẹp theo full URL nếu policy yêu cầu jti không lặp trong cùng key/window; attacker có thể thử replay trên endpoint khác để né cache.

### Atomic SET-if-absent

Ví dụ khái niệm Redis:

~~~text
SET replay:<opaque_digest> seen NX PX <ttl_milliseconds>
~~~

- **NX:** thành công chỉ khi cache key chưa tồn tại.
- **PX:** expiry của replay record theo milliseconds.
- Hai request đồng thời có cùng replayKey: đúng một insert thắng nếu cả hai truy cập **cùng atomic authority**.
- Khi insert thất bại vì key đã tồn tại: từ chối proof bị phát lại.
- Khi cache unavailable: không được tự coi proof là mới.

**Không dùng GET rồi SET tách rời**:

~~~text
if redis.get(key) is null:
    redis.set(key, "seen")
    accept()
~~~

Hai requests có thể cùng đọc null trước khi cả hai ghi. Thay bằng **single atomic insert** hoặc một unique constraint/transaction tương đương.

### TTL của replay record

Không gán bừa TTL là **access token lifetime**. TTL cần dựa trên **proof acceptance window**, timestamp skew, server nonce semantics, phân phối giữa các replica và khả năng clock drift.

Ví dụ:

~~~text
proof accepted only if:
    iat within server-configured recent/future window
    AND optional nonce valid
    AND replayKey not previously committed for this window

replay record retention:
    long enough that the same proof cannot be accepted
    again while it still passes freshness/nonce checks
~~~

Nếu replay record hết hạn **trước khi proof vẫn được coi là fresh**, cùng proof có thể được chấp nhận lần nữa. Nếu TTL quá dài không giới hạn, cache có thể tiêu thụ bộ nhớ không cần thiết.

### Chỉ đánh dấu jti sau xác thực proof

Một attacker có thể gửi proof giả chứa jti mà họ đoán được. Nếu server ghi jti vào cache **trước khi verify signature/binding**, attacker có thể gây cache poisoning/DoS.

Hợp lý hơn:

1. Parse kích thước và syntax có giới hạn.
2. Verify proof signature/alg/public JWK.
3. Verify htm/htu/iat/ath/nonce và key binding.
4. **Atomic insert replay key** ngay trước khi chấp nhận proof.
5. Kiểm authorization và thực thi request theo contract.

Thứ tự có thể được tối ưu theo thư viện nhưng không được chấp nhận một proof chưa có **uniqueness decision** khi policy bắt buộc one-time jti.

## 18. DPoP nonce và replay window không thay nhau

Một Resource Server/AS có thể yêu cầu **server-provided DPoP nonce** theo RFC 9449.

Vì sao cần nonce?

- Hỗ trợ freshness được bên nhận kiểm soát.
- Giảm phụ thuộc vào đồng hồ client.
- Giúp hạn chế một số hình thức pre-generated proofs hoặc clock-skew issues.
- Cung cấp thêm context chống replay khi implementation đúng.

Nhưng **nonce không tự làm jti uniqueness không cần thiết**. Nếu nonce có thể được dùng cho nhiều requests trong một khoảng, attacker có thể phát lại chính proof chứa nonce hợp lệ.

### Nonce challenge theo profile

~~~text
1. RS/AS yêu cầu nonce.
2. Client nhận challenge và server-provided nonce.
3. Client tạo DPoP proof mới có nonce đó.
4. Server kiểm nonce validity + method/URI/time/key binding.
5. Server vẫn kiểm jti reuse trong acceptance policy.
~~~

Không nhầm server DPoP nonce với **OIDC nonce của authentication transaction**. Hai giá trị cùng tên nhưng mục đích, nơi tạo và quy tắc xác minh khác nhau.

### Một DPoP proof không được tái sử dụng cho nhiều requests

Client nên tạo **proof mới với jti mới cho mỗi HTTP request cần DPoP**, kể cả khi dùng cùng access token và cùng private key.

Client không nên cache một proof JWT rồi gắn cho nhiều API calls chỉ vì proof còn trong time window.

## 19. Sender-binding: mTLS và DPoP khác một replay list

### DPoP-bound access token

Một access token có thể mang public key thumbprint dưới **cnf.jkt** theo profile. RS cần kiểm DPoP proof key tương ứng, access-token hash, request binding và proof replay.

Khi attacker chỉ có raw access token nhưng không có DPoP private key, AT bị copy **không đủ** để gọi RS nếu sender-constraining được enforce đúng.

### mTLS certificate-bound access token

Với RFC 8705, access token có thể bị ràng với client certificate, thường qua confirmation claim như **cnf.x5t#S256**. RS kiểm TLS client certificate thực sự của request phù hợp token binding.

Không đánh dấu mTLS-bound AT **single-use**: client hợp lệ có thể gọi nhiều requests với cùng AT và certificate. mTLS giảm replay bởi attacker **chỉ lấy được token**, không ngăn attacker có cả token và private key/certificate hoặc chiếm được client runtime.

### So sánh

| Cơ chế | Dữ liệu kiểm ở request | Reuse semantics |
| --- | --- | --- |
| **Bearer AT** | Token validity, issuer/aud/scope/expiry. | Token có thể dùng nhiều lần. |
| **DPoP AT** | AT + mỗi request một proof có signature, htm/htu/ath/iat/jti và nonce nếu yêu cầu. | AT có thể dùng nhiều lần; **proof jti** cần freshness/anti-replay. |
| **mTLS-bound AT** | AT + TLS client certificate khớp binding. | AT và certificate dùng nhiều requests; cần đúng holder. |
| **Rotating RT** | RT + client/sender binding + active family state. | Mỗi RT chỉ được consume một lần. |

**Không biến sender-binding thành thay thế cho authorization.** RS vẫn kiểm đúng aud, scope, principal, tenant và permission với từng request.

## 20. Authorization code: reuse là code interception/redeem sai

Trong OAuth 2.0 Authorization Code Flow, một **authorization code** là credential ngắn hạn và **one-time**.

~~~text
AS phát authorization code CODE1
Client đổi CODE1 tại token endpoint
AS đánh dấu CODE1 consumed
Client/attacker gửi lại CODE1
AS từ chối, không cấp token lần hai
~~~

### Atomic redemption

Giống RT rotation, phải bảo đảm:

- Code chưa hết hạn.
- Code thuộc đúng client_id và redirect_uri theo protocol.
- Client authentication/PKCE verifier đúng theo authorization transaction.
- Code được **redeem tối đa một lần**.
- Code state transition và token issuance có consistency phù hợp.

Một cơ chế giả định:

~~~sql
UPDATE authorization_codes
SET status = 'CONSUMED',
    consumed_at = CURRENT_TIMESTAMP
WHERE code_lookup_digest = :digest
  AND status = 'ACTIVE'
  AND expires_at > CURRENT_TIMESTAMP
  AND client_id = :client_id;
~~~

Nếu affected_rows = 0, không phát AT/RT. Trong triển khai thật, cần lock/transaction để kiểm thêm PKCE, redirect_uri, issuer và grant trước commit; không dựa chỉ vào một UPDATE minh họa.

### PKCE không thay one-time code

PKCE buộc bên đổi code chứng minh sở hữu **code_verifier** tương ứng challenge trong authorization request. PKCE giúp chống code interception/substitution theo threat model, nhưng **AS vẫn phải ngăn code redeem hai lần**.

Ngược lại, code one-time không tự thay PKCE: attacker lấy code chưa sử dụng có thể cố redeem trước client nếu không có proof ràng buộc phù hợp.

### Code reuse vs RT reuse

| Khía cạnh | Authorization code | Rotating refresh token |
| --- | --- | --- |
| Lifetime | Rất ngắn. | Thường dài hơn. |
| Mục đích | Đổi token một lần sau authorization. | Xin token mới trong grant còn hợp lệ. |
| Replay response | Từ chối redeem lại; xử lý grant theo OAuth security policy. | Từ chối RT đã CONSUMED; thường revoke active family vì nghi cả chain bị lộ. |
| Binding | Client, redirect_uri, PKCE, issuer/transaction. | Client, family, scopes, sender proof khi có. |
| RT lineage | Chưa có RT successor history. | Có parent/child/family state. |

Đừng áp dụng cùng một “family revoke” thuật toán cho authorization code nếu code đó chưa sinh RT family hoặc semantics khác.

## 21. OIDC nonce, state và jti: các định danh không thể trộn

### OIDC nonce

**nonce** trong OpenID Connect dùng để liên kết ID token với authentication request và giảm replay/substitution của authentication response. RP kiểm nonce nhận được với transaction đã lưu theo OIDC profile.

Nếu RP có nhiều tab, nonce cần được ràng với từng authorization transaction, không dùng một global nonce có thể bị ghi đè.

### OAuth state

**state** liên kết authorization response với request được client tạo, giúp chống CSRF và response injection khi triển khai đúng. State không phải DPoP jti hay RT family ID.

### JWT jti

**jti** là một JWT ID claim có thể giúp phân biệt token và hỗ trợ denylist/telemetry, nhưng:

- **jti trong access token không tự biến AT thành single-use**.
- Không có cơ chế state/registry nào tự xuất hiện chỉ vì JWT chứa jti.
- Một attacker sở hữu signing key có thể tạo JWT giả với jti khác; denylist từng jti không khắc phục lộ key.
- **DPoP proof jti** có anti-replay semantics cụ thể theo RFC 9449, khác JWT ID thông thường.

### Bảng tổng hợp

| Giá trị | Ai tạo | Phạm vi kiểm |
| --- | --- | --- |
| **OIDC nonce** | RP/client trong authentication request. | Authentication transaction và ID token. |
| **OAuth state** | Client trước authorization request. | Authorization response correlation. |
| **Authorization code ID** | AS. | One-time code redemption. |
| **RT family ID** | AS. | Grant/refresh token lineage. |
| **RT opaque lookup digest** | AS từ random token. | Tra credential và trạng thái rotation. |
| **AT jti** | AS theo JWT profile. | Token ID; có thể dùng denylist, không mặc định one-time. |
| **DPoP jti** | Client khi ký proof. | Uniqueness trong acceptance window với key/realm. |
| **HTTP Idempotency-Key** | Caller theo API contract. | Nhận diện retry của operation; không tự là auth proof. |

## 22. Replay detection và access-token semantics

Một access token có thể là JWT, opaque token hoặc JWE. Những định dạng này không quyết định nó có one-time semantics hay không.

### JWT access token

RS có thể xác minh chữ ký offline, kiểm issuer/audience/exp/scope và grant/permission. Nếu là Bearer AT thông thường, nhiều requests dùng cùng token là hợp lệ.

Một heuristic:

~~~text
if same JWT jti seen twice within one hour:
    revoke user session
~~~

dễ gây false positives. Nếu muốn áp **single-use AT** trong một hệ thống chuyên biệt, cần profile/hợp đồng riêng và thiết kế state phân tán, retry semantics, cache/DoS risk. Đừng mặc định đó là hành vi OAuth.

### Opaque access token

RS có thể gửi opaque token tới **introspection endpoint** theo RFC 7662 để biết active/scope/audience theo AS policy. Việc introspect cùng token nhiều lần cũng là bình thường.

**Introspection active=true không chứng minh token chưa từng được dùng trước đó.** Nó chỉ trả thông tin trạng thái theo context/protocol. Muốn detect use-once cần dữ liệu nghiệp vụ hoặc policy riêng.

### Encrypted JWE token

JWE có confidentiality và authenticated decryption, nhưng nếu là Bearer, attacker có raw JWE vẫn có thể replay đến intended RS trong thời hạn hợp lệ. Không cần biết plaintext.

### High-risk transaction binding

Với những operation như chuyển tiền hoặc phê duyệt quan trọng, có thể cần thêm **transaction-specific nonce, user reauthentication, proof of possession, operation idempotency và server-side authorization**.

Điều đó **khác** với biến toàn bộ OAuth access tokens thành single-use. Hãy ràng freshness vào **hành động rủi ro cao**, không áp một luật reuse mơ hồ cho mọi GET API.

## 23. Java: mô hình trạng thái refresh reuse

Đoạn Java 17 sau minh họa **decision layer**, không tự triển khai OAuth token endpoint. Repository phải dùng transaction, row locking/compare-and-set và family lifecycle đúng như phần SQL phía trên.

~~~java
import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

public final class RefreshReuseDecisionModel {

    enum TokenState {
        ACTIVE, CONSUMED, REVOKED, EXPIRED, UNKNOWN
    }

    enum FamilyState {
        ACTIVE, COMPROMISED, REVOKED, EXPIRED
    }

    record RefreshContext(
            UUID tokenId,
            UUID familyId,
            String clientId,
            TokenState tokenState,
            FamilyState familyState,
            Instant tokenExpiresAt,
            Instant familyExpiresAt) {

        RefreshContext {
            Objects.requireNonNull(clientId);
            Objects.requireNonNull(tokenState);
            Objects.requireNonNull(familyState);
        }
    }

    enum Action {
        CONSUME_AND_ROTATE,
        REUSE_DETECTED_REVOKE_FAMILY,
        DENY_INVALID_GRANT
    }

    static Action decide(
            RefreshContext context,
            String authenticatedClientId,
            Instant now,
            boolean senderBindingVerified) {

        Objects.requireNonNull(context);
        Objects.requireNonNull(now);

        // Không tự revoke family khi caller không chứng minh
        // đúng client/binding theo protocol và risk policy.
        if (!context.clientId().equals(authenticatedClientId)
                || !senderBindingVerified) {
            return Action.DENY_INVALID_GRANT;
        }

        if (context.familyState() != FamilyState.ACTIVE
                || context.familyExpiresAt() == null
                || !now.isBefore(context.familyExpiresAt())) {
            return Action.DENY_INVALID_GRANT;
        }

        if (context.tokenState() == TokenState.CONSUMED) {
            return Action.REUSE_DETECTED_REVOKE_FAMILY;
        }

        if (context.tokenState() != TokenState.ACTIVE
                || context.tokenExpiresAt() == null
                || !now.isBefore(context.tokenExpiresAt())) {
            return Action.DENY_INVALID_GRANT;
        }

        return Action.CONSUME_AND_ROTATE;
    }
}
~~~

**Quan trọng:** kết quả CONSUME_AND_ROTATE **chưa bảo đảm** một lần consume đã thành công. Nó phải được thực thi trong **atomic transaction**. Hai threads có thể cùng nhận decision CONSUME_AND_ROTATE từ snapshots cũ; database lock/CAS/unique constraints mới là nơi quyết định ai thắng.

### Những gì phải nằm ở service/repository thật

- Digest lookup từ RT raw có đủ entropy, không lấy tokenId/familyId tự khai.
- Client authentication hoặc public-client binding theo protocol.
- DPoP/mTLS sender proof khi RT bị ràng với key.
- Row lock/CAS + family state + successor unique constraint.
- Token generation bằng CSPRNG, lưu digest/lineage cùng transaction.
- Audit/outbox event khi reuse hoặc family compromise.
- Không gửi successor/AT mới khi transaction commit không thành công.
- TTL/retention/absolute expiry và security monitoring.
- Trả invalid_grant cho client, không lộ internal status/family IDs.
- Kiểm concurrent cases và timeout/response-loss behavior.

### Một cảnh báo về invalid client context

**Đừng cho attacker gửi RT bất kỳ cùng client_id của nạn nhân rồi vô hiệu mọi family mà họ đoán được.** Phải tra credential thực sự từ token digest, kiểm grant/client binding trước khi cho operation tác động tới family. Đối với **public client**, client_id không phải một bí mật; nếu attacker có bản RT thật, họ vẫn có thể kích hoạt reuse signal. Sender-constraining, rate limiting và review policy giảm rủi ro nhưng không loại hoàn toàn khả năng gây DoS.

## 24. Java/Spring: replay cache cho DPoP jti

Ví dụ sử dụng Spring Data Redis, giả định một component khác đã **verify hoàn chỉnh proof** và cung cấp một record chỉ được tạo từ bằng chứng đáng tin:

~~~java
import java.time.Duration;
import java.util.Objects;

import org.springframework.data.redis.core.StringRedisTemplate;

public final class DpopJtiReplayGuard {

    public record VerifiedProof(
            String realm,
            String verifiedJwkThumbprint,
            String jti) {

        public VerifiedProof {
            Objects.requireNonNull(realm);
            Objects.requireNonNull(verifiedJwkThumbprint);
            Objects.requireNonNull(jti);
        }
    }

    private final StringRedisTemplate redis;
    private final Duration dedupRetention = Duration.ofMinutes(11);

    public DpopJtiReplayGuard(StringRedisTemplate redis) {
        this.redis = Objects.requireNonNull(redis);
    }

    public void requireUnused(VerifiedProof proof) {
        // Trong production, tạo opaque key bằng HMAC trên
        // length-prefixed realm | thumbprint | jti,
        // với secret dành riêng cho cache-key derivation.
        // Hàm helper phải chống ambiguity và giới hạn input size.
        String replayKey = ReplayKeyDerivation.deriveOpaqueKey(
                proof.realm(),
                proof.verifiedJwkThumbprint(),
                proof.jti()
        );

        // Redis SET key "seen" NX PX ttl tương đương.
        Boolean firstUse = redis.opsForValue().setIfAbsent(
                replayKey,
                "seen",
                dedupRetention
        );

        if (firstUse == null) {
            throw new SecurityException("Replay store unavailable");
        }
        if (!firstUse) {
            throw new SecurityException("DPoP proof replay");
        }
    }
}
~~~

**ReplayKeyDerivation là helper giả định**, không nằm trong đoạn mã; phải triển khai bằng HMAC hoặc encoding không mơ hồ và đã được kiểm thử. Vì vậy ví dụ là **khung tích hợp**, chưa phải một class compile độc lập.

### Vì sao duration 11 phút chỉ là ví dụ?

Nó minh họa một policy có acceptance window khoảng 5 phút với skew và margin, nhưng **không là thông số DPoP bắt buộc**. TTL phải được tính sao cho một proof bị chấp nhận không bao giờ được chấp nhận lại **trong suốt khoảng nó còn vượt qua freshness/nonce tests**.

Một proof có iat sai giờ hoặc nằm ngoài window phải bị từ chối **trước khi ghi cache**; cache không thay kiểm iat.

### Cần kiểm gì trước khi gọi guard?

~~~text
parse DPoP proof under size/alg/typ policy
verify proof signature with public JWK
validate public JWK is admissible
compute verified key thumbprint
validate htm/htu against current request
validate iat freshness and nonce if required
validate ath against presented AT at resource endpoint
validate AT issuer/audience/expiry/type and cnf.jkt binding
then call requireUnused(verifiedProof)
then enforce scopes/resource permission and process request
~~~

Bên nhận có thể tối ưu thứ tự để giảm CPU trước khi làm đầy cache, nhưng **không được chấp nhận proof chưa đi qua uniqueness check** khi policy yêu cầu.

### Nếu replay store lỗi

Không biến cache timeout thành:

~~~text
if redisTimeout:
    assumeProofIsFresh = true
~~~

Với sender-bound high-security endpoint, thường phải **fail closed hoặc áp fallback đã được security policy phê duyệt**; có thể trả lỗi tạm thời để client retry với **proof mới**, nhưng không tự tắt replay protection.

## 25. Client-side single-flight để tránh double refresh

Một ứng dụng client có thể có mười HTTP requests đồng thời và AT vừa hết hạn. Nếu cả mười luồng đều dùng RT1 để refresh, AS có thể thấy **reuse liên tục**.

Giải pháp là **chỉ một refresh operation cho một client session tại một thời điểm**.

Mã giả Java:

~~~java
import java.util.Objects;
import java.util.concurrent.CompletableFuture;
import java.util.function.Supplier;

public final class SingleFlightRefresh {

    private CompletableFuture<TokenPair> inFlight;

    public record TokenPair(
            String accessToken,
            String refreshToken) {}

    public synchronized CompletableFuture<TokenPair> refresh(
            Supplier<CompletableFuture<TokenPair>> startNetworkRefresh) {

        Objects.requireNonNull(startNetworkRefresh);

        if (inFlight != null && !inFlight.isDone()) {
            return inFlight;
        }

        // Giao diện minh họa: real code cần xử lý supplier
        // throwing synchronously, network failure và safe storage.
        CompletableFuture<TokenPair> started =
                startNetworkRefresh.get();

        inFlight = started;
        return started;
    }
}
~~~

### Hạn chế quan trọng

- Đây chỉ là **single-flight trong một JVM object**, không chia sẻ giữa hai browser tabs, hai app processes, hai mobile devices hoặc nhiều BFF instances.
- Thread/concurrency correctness cần được kiểm trong real client; method chỉ minh họa nguyên tắc không tạo nhiều in-flight refresh operations cùng lúc.
- Sau successful refresh, **RT mới phải được lưu bền vững/an toàn trước lần refresh kế tiếp**.
- Sau invalid_grant/reuse-trigger, không retry vô hạn.
- Nếu cùng một user có nhiều device sessions, tốt hơn là mỗi session có **grant/family riêng** thay vì chia sẻ raw RT.
- Trong browser, web storage/IPC/lock APIs phải được cân nhắc theo security threat model; không đặt RT vào storage dễ bị XSS đọc chỉ để đồng bộ.

### Vì sao không gắn một global lock ở server?

Server phải **vẫn kiểm atomic family state** dù client đã single-flight. Client có thể bị lỗi, bị chiếm, có nhiều replicas hoặc cố tình gửi concurrent requests.

**Single-flight giảm false positives; transactional consume-once bảo vệ protocol invariant.**

## 26. Nhiều AS replicas và nhiều vùng địa lý

Trong production có thể có:

~~~text
AS replica A ----\
AS replica B -----+--> Refresh token family store
AS replica C ----/

RS region X ------\
RS region Y -------+--> DPoP replay state
RS region Z ------/
~~~

### RT family cần một nguồn trạng thái có tính nhất quán mạnh

Nếu AS region X và Y cùng chấp nhận RT1 tại **hai bản sao database eventual-consistency**, cả hai có thể cho rằng RT1 ACTIVE và phát RT2, RT3.

Để bảo đảm consume-once cần một trong những thiết kế có bằng chứng về tính nhất quán:

- **Strongly consistent/serializable transaction** hoặc row lock trên authoritative primary.
- **Compare-and-swap/conditional write** có atomic guarantees thực sự trên partition owner.
- **Single-writer ownership** theo family với routing/fencing khi failover.
- **Consensus-backed state** khi cần writes multi-region.

**Không chỉ bật replication rồi mặc định đạt one-time semantics.** Một vùng bị network partition phải có chính sách fail closed/route hoặc không phát successor khi không thể xác minh state authoritative.

### DPoP replay cache cần atomicity theo realm

Nếu cùng DPoP proof có thể đến RS ở region X rồi được load balancer gửi sang Y, replay cache cục bộ của X **không đủ**.

Cần:

- Shared atomic state hoặc partitioning có routing đáng tin để cùng key/realm dùng một authority.
- Replay record TTL đủ cho proof acceptance window.
- Health/fail-closed policy khi replay cache không kết nối.
- Replication/failover behavior rõ: promotion mất recent cache writes có thể mở replay window.
- Không tin session stickiness như bảo đảm security nếu attacker có thể chọn khác region/hostname.

### Tái áp dụng stale state sau recovery

Một snapshot cũ có thể cho RT1 ACTIVE dù primary đã đánh dấu CONSUMED. Khôi phục snapshot mà không replay transaction log/tombstones sẽ khiến token cũ được đổi lần nữa.

**Disaster recovery cũng phải giữ semantics one-time** hoặc fail closed và buộc reauthentication cho các families không xác định an toàn.

## 27. Transaction ordering, crash và outbox

Một luồng refresh có thể thất bại vào nhiều thời điểm:

| Điểm lỗi | Hậu quả có thể gặp | Cách xử lý |
| --- | --- | --- |
| Trước khi consume RT1 | RT1 vẫn ACTIVE. | Cho phép request hợp lệ retry theo protocol. |
| Sau khi consume nhưng trước successor insert | Trạng thái không nhất quán nếu không có transaction. | Một transaction rollback tất cả. |
| Sau successor insert nhưng trước commit | RT2 chưa bền vững. | Không gửi RT2 cho client trước commit. |
| Commit xong, response mất | Client còn RT1; retry có thể bị coi reuse. | Client single-flight, recovery/reauth policy; không nới grace tùy tiện. |
| Commit xong, audit event publish lỗi | Reuse signal/telemetry có thể bị mất nếu publish trực tiếp. | Transactional outbox hoặc durable event mechanism. |
| Reuse detected nhưng family revoke không commit | Attacker có thể tiếp tục với RT2. | Revoke family phải commit atomic với incident state khi policy yêu cầu. |
| Family revoke commit, RS cache vẫn nhận AT cũ | AT chưa bị chặn ngay ở RS. | TTL/denylist/introspection theo revocation SLA. |

### Transactional outbox

Khi detect reuse, cần ghi trạng thái family và event **trong cùng database transaction**:

~~~text
BEGIN
  update family: COMPROMISED
  revoke active descendant
  insert outbox event REFRESH_TOKEN_REUSE_DETECTED
COMMIT

separate publisher:
  read committed outbox events
  publish to monitoring/session revocation consumers
  mark delivered idempotently
~~~

Một event được deliver nhiều lần phải được consumer xử lý idempotent. Dùng **family_id + generation + event_id** để tránh ghi đè một trạng thái revocation mới bằng event cũ.

### Không gắn quyền truy cập vào broker ACK

Broker thông báo đã nhận event không có nghĩa Resource Server đã thực sự chặn AT; phải đo **applied state**, nhất là nếu AS muốn ngăn AT cũ tiếp tục dùng sau RT family compromise.

## 28. Reuse detection sau khi refresh token bị revoke

Một câu hỏi quan trọng: **sau khi family được revoke, AS còn cần tra các token cũ không?**

Nếu hệ thống xóa toàn bộ RT rows ngay, những request gửi RT1/RT2 sau đó có thể trở thành UNKNOWN. Điều này giảm khả năng:

- Phát hiện ongoing malicious replay.
- Xác định family/incident nào đang bị tấn công.
- Đo tần suất attacker thử dùng RT cũ.
- Chặn một số cách làm sống lại token qua stale state/backup.

### Tombstone có mục đích

Có thể giữ:

~~~text
lookupDigest
family_id
finalStatus = CONSUMED / REVOKED
consumedAt / revokedAt
retentionUntil
incidentId
~~~

Tombstone nên được truy cập theo **quyền tối thiểu** và xóa sau retention policy. Không cần lưu RT raw.

### Nhưng không giữ dữ liệu mãi mãi

Reuse audit có thể liên quan subject, client_id, IP, device và user behavior. Cần data minimization, hạn quyền và retention phù hợp. Không biến token-family registry thành kho tracking cá nhân vô thời hạn.

### Reuse không có nghĩa tự động account takeover

Một RT đã dùng xuất hiện lại có thể đến từ retry, bug của app hoặc tấn công. Hệ thống có thể phải revoke family để an toàn, nhưng thông báo/incident classification nên phản ánh **credential replay observed**, không gán kết luận chắc chắn user bị chiếm đoạt.

## 29. Phản ứng sau detect reuse: scope vừa đủ

Một playbook bảo mật nên phân biệt:

1. **Từ chối credential bị dùng lại.**
2. **Chặn active descendant/family** theo strict rotation policy.
3. **Chặn AT còn hiệu lực** nếu AS/RS có state/denylist/introspection và yêu cầu.
4. **Vô hiệu grant/session hoặc yêu cầu reauthentication** theo mức rủi ro.
5. **Đánh giá nguy cơ compromise rộng hơn:** client secret, RT family khác, DPoP key, device.
6. **Thông báo và phục hồi UX** phù hợp: người dùng cần login lại, session ở thiết bị khác có thể không bị ảnh hưởng.
7. **Audit, rate limit, anomaly detection** không làm lộ raw tokens.

### Ví dụ response nội bộ

~~~json
{
  "event": "REFRESH_TOKEN_REUSE_DETECTED",
  "family_id": "example-family-uuid",
  "grant_id": "example-grant-id",
  "client_id": "dashboard-web",
  "action": "FAMILY_REVOKED",
  "correlation_id": "example-request-123",
  "reason": "CONSUMED_TOKEN_PRESENTED_AGAIN"
}
~~~

Đây là **event schema nội bộ giả định**, không phải OAuth error response. Nó không nên chứa RT raw, full AT, cookies hoặc private signing material.

### Không tạo DoS bằng auto-revoke không kiểm soát

Nếu API nhận một chuỗi RT không tồn tại mà vẫn cho caller chỉ định family_id để revoke family, attacker có thể gây logout cho nhiều người.

Dù RT cũ thật là credential khó đoán, một attacker đã lấy được RT1 có thể cố ý phát lại để làm family bị revoke. Cần bảo vệ RT ở client, giới hạn rate, kiểm context và có user recovery an toàn.

## 30. Các lớp authorization vẫn cần sau replay detection

Ngay cả khi DPoP/RT/authorization code reuse detection hoạt động đúng, hệ thống vẫn cần:

- **AS** giới hạn client, grant, scope, audience, refresh token lifetime và client authentication.
- **RS** verify JWT signature hoặc introspection, issuer, audience, token type, exp/nbf.
- **RS** kiểm exact scopes và permission trên tenant/resource/action.
- **TLS**, client storage và log redaction.
- **Token revocation** khi cần chặn Bearer AT trước exp.
- **Sender-constraining** theo threat model.
- **Business idempotency** cho hoạt động có side effects và transaction binding khi cần.

**Một request có DPoP proof chưa bị reuse không tự có quyền duyệt đơn.** Nó chỉ chứng minh freshness/possession theo protocol; quyền của caller vẫn phụ thuộc grant và policy.

### Ví dụ Orders

~~~text
DPoP proof P-new: valid signature, fresh jti
Access token AT: signature valid, aud=orders-api
Scope: orders:read
Request: POST /orders/123/approve

Outcome: DENY
Reason: thiếu orders:approve / business permission
~~~

Phát hiện replay và authorization là **hai hệ thống kiểm tra bổ sung**.

## 31. Observability: đo reuse mà không ghi raw token

Reuse detection tốt cần quan sát **tỷ lệ, phạm vi và thời gian phản ứng**. Có thể theo dõi các event nội bộ:

~~~text
RT_ROTATION_SUCCEEDED
RT_CONSUMED_PRESENTED_AGAIN
RT_FAMILY_COMPROMISED
RT_FAMILY_REVOKED
RT_CLIENT_BINDING_MISMATCH
RT_SENDER_PROOF_INVALID
RT_UNKNOWN_OR_EXPIRED
RT_REFRESH_CONCURRENT_RACE
RT_REFRESH_RESPONSE_LOSS_SUSPECTED
DPOP_PROOF_VERIFIED
DPOP_JTI_REPLAY_REJECTED
DPOP_ATH_MISMATCH
DPOP_HTM_HTU_MISMATCH
DPOP_IAT_OUTSIDE_WINDOW
DPOP_NONCE_REQUIRED_OR_INVALID
DPOP_REPLAY_STORE_UNAVAILABLE
AUTHORIZATION_CODE_REDEEMED
AUTHORIZATION_CODE_REPLAY_REJECTED
TOKEN_REVOCATION_PROPAGATION_LAG
~~~

Đây chỉ là tên event minh họa, **không phải mã lỗi OAuth chuẩn**.

### Metrics nên có

| Metric | Câu hỏi điều tra |
| --- | --- |
| **rt_rotation_success_rate** | Client refresh có hoạt động bình thường không? |
| **rt_reuse_rate** | Bao nhiêu RT đã CONSUMED bị trình lại? |
| **family_compromise_rate** | Bao nhiêu grants cần buộc reauthenticate? |
| **retry_after_response_loss** | Có dấu hiệu client retry vì mất response? |
| **concurrent_refresh_conflict** | Client single-flight hoặc row lock có vấn đề? |
| **invalid_grant_by_client_version** | Một bản client mới có tạo false positives không? |
| **dpop_replay_reject_rate** | Proof jti được dùng lại thường xuyên không? |
| **dpop_iat_skew_distribution** | Clocks/nonce policy có gây từ chối nhầm? |
| **replay_cache_insert_latency** | Shared store có làm tăng API latency? |
| **replay_cache_unavailable_rate** | Store outage có khiến fail-closed rộng? |
| **multi_region_state_lag** | State family/replay có bị trễ đồng bộ? |
| **token_revocation_enforcement_lag** | Sau family revoke, AT còn được RS nhận trong bao lâu? |

### Log mẫu an toàn

~~~json
{
  "event": "REFRESH_TOKEN_REUSE_DETECTED",
  "timestamp": "2026-11-23T03:00:00Z",
  "correlation_id": "req-example-314",
  "issuer": "https://identity.example.test",
  "client_id": "dashboard-web",
  "family_reference": "NON_BEARER_INTERNAL_FAMILY_ID",
  "previous_token_state": "CONSUMED",
  "family_action": "REVOKED",
  "client_version": "example-client-build"
}
~~~

**Không log raw RT/AT, DPoP private key, unredacted Authorization header, access-token-bearing JWE hay complete proof JWT** nếu không có mục đích bảo mật đặc biệt và kiểm soát được phê duyệt.

### Cẩn trọng với fingerprint trong log

Nếu cần liên kết các sự kiện của một token, có thể dùng:

~~~text
auditFingerprint = HMAC_SHA256(auditSecret, tokenBytes)
~~~

Fingerprint vẫn có thể liên kết hoạt động của user/client và cần privacy/retention policy. Không dùng một secret HMAC chung cho audit, JWT signing và DPoP cache derivation. Không in ra raw token trong lúc tính fingerprint.

### Giám sát false positives

Một đợt tăng invalid_grant và RT reuse ngay sau deploy thường gợi ý bug retry, multi-tab/session storage, KMS latency hoặc network outages. Không tự kết luận có một làn sóng account takeover nếu chưa điều tra.

Cần cân bằng **security containment** với **khả năng phục hồi**: việc buộc reauthenticate trên diện rộng cũng là một tác động vận hành cần đo và truyền thông rõ.

## 32. Tình huống thực tế

### Case A — Attacker dùng RT1 sau khi client đã nhận RT2

**Bối cảnh:** Dashboard đổi RT1→RT2 thành công. Sau đó attacker có bản RT1 gửi refresh.

**Hành vi đúng:** AS xác định RT1 ở trạng thái CONSUMED, trả invalid_grant, ghi reuse signal và revoke family/active RT2 theo strict rotation policy. Nếu cần, revoke các AT liên quan theo kiến trúc và yêu cầu reauthentication.

**Điểm cốt lõi:** không chỉ từ chối RT1; RT2 có thể thuộc về attacker nếu không biết ai đã thắng lần đổi trước.

### Case B — Attacker refresh trước client hợp lệ

**Bối cảnh:** Attacker copy RT1 khi token còn ACTIVE rồi sử dụng nó đầu tiên. Attacker nhận RT2. Client dùng RT1 sau đó.

**Hành vi đúng:** request đầu tiên có thể trông hợp lệ nếu RT chỉ là Bearer; request thứ hai tạo reuse signal. AS revoke family RT2 và không để attacker tiếp tục refresh.

**Giới hạn:** trước khi client trình RT1 lần hai, AS có thể chưa phát hiện copy. **Sender-constrained RT** giảm rủi ro nếu attacker không có binding key.

### Case C — Lỗi response loss tạo false-positive

**Bối cảnh:** AS đã commit RT1→RT2, nhưng response bị mất. Client tự retry RT1, làm family bị revoke.

**Hành vi đúng:** AS giữ invariant strict, không phát successor thứ hai. Client chuyển sang recovery/reauthentication. Team xem xét single-flight, HTTP retries, lưu RT mới và, nếu cần, một idempotent recovery protocol có security review.

**Điểm cốt lõi:** đừng mở cửa “RT cũ dùng lại trong 60 giây” tùy tiện mà không đánh giá attacker có thể sở hữu bản RT cũ.

### Case D — Hai tab browser cùng refresh

**Bối cảnh:** Hai tabs có cùng RT1 trong storage. Tab A và B cùng gửi refresh.

**Hành vi đúng:** AS atomic consume-once; không phát hai RT successors. Ở client nên có coordinator/single-flight và storage update tránh stale RT. Nếu strict policy đánh dấu B là reuse và revoke family, đó là trade-off UX/security phải được hiểu trước.

### Case E — Multi-region AS đều thấy RT1 ACTIVE

**Bối cảnh:** Region A và B dùng database eventual-consistency, cả hai nhận RT1 gần như đồng thời.

**Rủi ro:** mỗi bên cấp một successor; attacker có thể giữ một branch mà client không biết.

**Khắc phục:** authoritative CAS/transaction hoặc single-writer routing với fencing; mất consistency thì fail closed. Chỉ dùng Redis/DB replication thông thường không mặc định đảm bảo one-time.

### Case F — Cùng DPoP proof gửi tới hai RS replicas

**Bối cảnh:** Attacker lấy một DPoP proof hợp lệ P1 và gửi đồng thời tới replica A và B. Cả hai chỉ có local in-memory Set.

**Rủi ro:** cả hai cho P1 là mới và xử lý request.

**Khắc phục:** shared atomic replay state theo realm hoặc routing có security guarantee, một **SET NX** thắng duy nhất. Bất kỳ failover/snapshot nào cũng không được làm stale proof được nhận lại trong acceptance window.

### Case G — DPoP proof đúng chữ ký nhưng sai URL

**Bối cảnh:** Proof P1 ký cho GET /api/orders, attacker gắn nó vào POST /api/orders/123/approve.

**Hành vi đúng:** RS từ chối vì htm/htu không khớp, không cần kết luận reuse. Ngay cả với proof fresh, AT scope orders:read vẫn không đủ để approve.

### Case H — Client dùng lại DPoP jti do lỗi SDK

**Bối cảnh:** SDK tạo jti khi khởi động và dùng cùng jti cho 100 requests với proof signatures khác nhau.

**Hành vi đúng:** RS phát hiện reuse jti theo public key/realm/acceptance window, từ chối proofs về sau. SDK phải tạo **jti duy nhất cho mỗi proof**, không dùng một jti per session.

### Case I — Replay cache ở Redis bị lỗi

**Bối cảnh:** Redis không reachable; RS đã verify proof signature, nhưng không thể ghi replay marker.

**Hành vi đúng:** RS không tự bỏ qua uniqueness. Theo security policy, fail closed hoặc dùng trusted fallback có atomic guarantees. Có thể trả lỗi tạm thời; client tạo proof mới khi retry.

**Không chấp nhận mọi proof** chỉ vì cache có vấn đề trong khi endpoint yêu cầu DPoP anti-replay.

### Case J — Authorization code được đổi hai lần

**Bối cảnh:** Client đã redeem CODE1 hợp lệ bằng PKCE. Attacker gửi lại CODE1, thậm chí có được code_verifier.

**Hành vi đúng:** AS thấy code đã CONSUMED, từ chối. PKCE đúng không cấp quyền redeem lại code.

### Case K — Bearer access token gọi GET nhiều lần

**Bối cảnh:** Dashboard dùng cùng AT để tải Orders list và chi tiết 5 lần.

**Hành vi đúng:** RS có thể chấp nhận cả 5 lần nếu AT và quyền hợp lệ. **Không coi repeated AT jti là compromise** theo mô hình Bearer thông thường.

### Case L — Một IP lạ xuất hiện sau roaming

**Bối cảnh:** Mobile user chuyển từ Wi-Fi sang cellular, gửi refresh từ IP khác.

**Hành vi đúng:** IP thay đổi có thể là risk signal, không đủ kết luận reuse. RT vẫn phải được kiểm client binding, family state và proof khi áp dụng.

### Case M — Session logout nhưng RT cũ được dùng

**Bối cảnh:** User logout, AS revoke RT family. Một process background cố refresh bằng RT cũ.

**Hành vi đúng:** invalid_grant, không cấp successor. Security telemetry phân biệt **REVOKED_BY_LOGOUT** với **CONSUMED_TOKEN_REUSE** để tránh báo giả incident compromise.

### Case N — RT row bị xóa ngay sau consume

**Bối cảnh:** AS chỉ giữ active RT, xóa RT1 record khi cấp RT2. Attacker trình RT1 lần hai.

**Rủi ro:** AS chỉ thấy UNKNOWN, không biết family RT2 cần revoke.

**Khắc phục:** giữ used-token tombstone/lineage trong thời gian security policy phù hợp để nhận diện reuse.

### Case O — Compromise cả RT và DPoP private key

**Bối cảnh:** Attacker chiếm client runtime, lấy RT cùng sender private key.

**Rủi ro:** Sender-constraining không ngăn attacker nếu họ có cả token lẫn key. Rotation/replay detection, runtime protection, rate limits, monitoring và grant revocation vẫn cần.

**Điểm cốt lõi:** possession proof không chứng minh thiết bị sạch hoặc user đang hiện diện.

### Case P — Reuse event nhưng RS vẫn nhận AT cũ

**Bối cảnh:** AS revoke RT family vì reuse, nhưng Orders RS verify JWT AT offline, AT còn hạn.

**Rủi ro:** attacker vẫn có thể dùng AT cho đến khi hết hạn nếu RS không có revocation state.

**Khắc phục:** đo revocation SLA, cân nhắc AT TTL ngắn, denylist/introspection/token version và sender binding khi cần. **Revoke RT family không tự làm signed JWT access token mất hiệu lực ở mọi RS.**

### Case Q — Global dedup khóa theo jti đơn lẻ

**Bối cảnh:** Hai clients DPoP có cùng jti do random collision hoặc cố tình chọn giống nhau; server dùng global Redis key chỉ là jti.

**Rủi ro:** client A có thể làm proof của B bị từ chối.

**Khắc phục:** replay key chứa **verified key thumbprint và realm**, dùng canonical/length-prefixed encoding và atomic dedup. Không coi jti là global unique identifier đã xác thực.

### Case R — Business idempotency bị nhầm với DPoP proof reuse

**Bối cảnh:** Client gửi lại POST /orders cùng idempotency key hợp lệ nhưng tạo DPoP proof mới với jti mới.

**Hành vi đúng:** RS verify DPoP proof mới, business layer trả cùng order result theo idempotency contract mà không tạo order mới.

Nếu client gửi lại **chính proof cũ** với cùng idempotency key, RS phải xử lý proof replay theo policy trước, không cho idempotency bypass authentication.

### Case S — DPoP proof của token cũ đi cùng AT mới

**Bối cảnh:** Client refresh AT nhưng tái sử dụng DPoP proof từ request trước, có **ath** tương ứng AT cũ.

**Hành vi đúng:** RS từ chối do ath mismatch và/hoặc jti replay. Client phải tạo proof mới theo AT hiện tại.

### Case T — ID token nonce từ tab khác

**Bối cảnh:** Hai OIDC authentication flows chạy đồng thời, RP lưu một nonce global và ghi đè transaction cũ.

**Rủi ro:** RP có thể từ chối hợp lệ hoặc không phát hiện token response substitution nếu kiểm sai.

**Khắc phục:** ràng state, nonce, issuer, client và transaction context; không trộn OIDC nonce với DPoP jti hoặc RT family state.

## 33. Negative tests cho detect reuse

Các test dùng **opaque tokens/proofs giả, test signing keys và grants được phép**, không sao chép credential production. Khi test phát lại request, nên đo cả **HTTP result, database state, event log, outbox và trạng thái của successor**, không chỉ status code.

| Kiểm thử | Tình huống | Kết quả mong đợi |
| --- | --- | --- |
| **RT first use** | RT1 ACTIVE, client/binding đúng. | Một transaction consume RT1, cấp RT2 ACTIVE và AT mới. |
| **RT second use** | RT1 CONSUMED được trình lại. | invalid_grant, reuse event/family action theo policy. |
| **RT family active descendant** | Sau RT1 reuse, client thử RT2. | RT2 bị từ chối nếu family đã COMPROMISED/REVOKED. |
| **RT unknown** | Chuỗi RT không tồn tại. | invalid_grant, không tiết lộ family info. |
| **RT expired** | RT hết hạn chưa từng sử dụng. | invalid_grant; không tự coi là credential reuse. |
| **RT already revoked** | User logout rồi retry. | invalid_grant, không phát token mới. |
| **RT family expired** | RT riêng còn thời gian nhưng absolute family expiry đã qua. | Từ chối. |
| **RT wrong client** | Client B trình RT cấp cho A. | Từ chối, không cấp successor. |
| **RT wrong DPoP key** | RT bị sender-constrained nhưng proof key khác. | Từ chối binding; audit theo risk. |
| **RT wrong mTLS cert** | Client cert không khớp bound RT. | Từ chối. |
| **RT lineage** | RT1→RT2→RT3. | Mỗi parent có tối đa một successor. |
| **Concurrent RT1 from two threads** | Hai calls song song cùng RT1. | Chỉ một successful consume/commit. |
| **Concurrent RT1 across AS replicas** | A và B cùng đọc RT1. | Global authority đảm bảo chỉ một winner. |
| **Multi-region eventual writes** | Hai regions thiếu CAS/consensus. | Test phát hiện vi phạm one-time; không deploy. |
| **Transaction rollback** | Lỗi sau consume nhưng trước insert successor. | Không mất RT1 hay tạo RT2 nửa chừng. |
| **Commit then lost response** | Client không nhận RT2, retry RT1. | Strict policy không phát successor thứ hai; UX recovery được xác định. |
| **Client single-flight** | Mười requests đòi refresh cùng lúc. | Chỉ một refresh network operation từ session. |
| **Multi-tab race** | Hai tabs dùng cùng RT1. | Server atomic; client coordination giảm false-positive. |
| **HTTP auto-retry POST** | Network library tự retry refresh. | Phát hiện/kiểm soát; không âm thầm nới semantics. |
| **Grace without binding** | RT1 được dùng nhiều lần trong 30 giây. | Security review từ chối nếu attacker cũng có thể khai thác. |
| **Idempotency key copied** | Attacker copy full RT request và retry key. | Không dùng idempotency key một mình làm proof holder. |
| **RT stale replica snapshot** | Replica đọc RT1 ACTIVE sau consume. | Không được tạo RT successor mới. |
| **RT restore from backup** | Restore trước thời điểm RT1 consumed. | Recovery không làm RT1 sống lại; fail closed/reauth. |
| **RT unique digest** | Hai tokens có cùng lookup digest record. | Unique constraint ngăn ambiguity. |
| **RT parent unique successor** | Cố insert RT2 và RT3 cùng parent RT1. | Unique constraint từ chối branch thứ hai. |
| **RT active per family** | Cố có hai ACTIVE descendants trong một family. | Unique constraint hoặc transactional policy ngăn. |
| **RT raw in DB/logs** | Audit, SQL logs ghi raw RT. | Phát hiện và redact; xử lý leakage. |
| **RT tombstone missing** | Xóa RT1 ngay khi consumed rồi thử RT1. | Test phát hiện mất reuse/family lookup. |
| **RT unknown family injection** | Caller gửi family_id của nạn nhân mà không có token thật. | Không revoke family theo input chưa xác thực. |
| **RT rate-limit abuse** | Nhiều invalid_grant với RT giả. | Rate-limit/monitor, không enumeration. |
| **RT family revoke transaction fail** | Reuse event ghi nhưng active descendant chưa revoke. | Không báo family contained; rollback/retry an toàn. |
| **Outbox duplication** | Publish cùng event hai lần. | Consumer idempotent, không undo state. |
| **Out-of-order family event** | Generation cũ đến sau revoked generation. | Không chuyển family về ACTIVE. |
| **AT still valid after RT revoke** | RS verify JWT offline. | Test ghi nhận SLA; dùng denylist/introspection nếu policy yêu cầu chặn sớm. |
| **AT reused twice normally** | Bearer AT gọi GET hai lần. | Không tự chặn chỉ vì seen jti. |
| **AT wrong audience** | Orders AT gửi Payments. | Từ chối recipient validation. |
| **AT expired** | AT quá exp. | Từ chối dù token chưa từng được dùng. |
| **AT insufficient scope** | orders:read gọi approve. | Từ chối authorization. |
| **AT cross-tenant** | AT hợp lệ đọc order tenant khác. | Từ chối business permission. |
| **DPoP first proof** | Proof hợp lệ, jti mới. | Atomic cache insert thành công. |
| **DPoP identical replay** | Gửi nguyên proof lần hai. | Từ chối jti reuse. |
| **DPoP simultaneous duplicate** | Hai replicas xử lý cùng jti. | Chỉ một atomic insert thành công. |
| **DPoP jti same, different keys** | Hai clients có jti trùng nhưng key khác. | Không tạo collision sai trong cache scope. |
| **DPoP same key/jti, different URI** | Cố bypass bằng URL khác. | Không bỏ qua uniqueness trong realm; htu cũng được kiểm. |
| **DPoP wrong htm** | Proof cho GET gửi POST. | Từ chối. |
| **DPoP wrong htu** | Proof cho /orders gửi /payments. | Từ chối. |
| **DPoP incorrect ath** | Proof gắn AT1 nhưng request mang AT2. | Từ chối. |
| **DPoP expired iat** | Proof quá cũ. | Từ chối freshness, không cần chờ cache. |
| **DPoP future iat** | Proof vượt skew cho phép. | Từ chối. |
| **DPoP missing nonce** | Server policy yêu cầu nonce. | Reject/challenge theo RFC profile. |
| **DPoP reused nonce + jti** | Proof có nonce vẫn hợp lệ nhưng jti lặp. | Từ chối reuse. |
| **DPoP wrong signature** | Header/jti đúng nhưng chữ ký sai. | Từ chối, không poison cache. |
| **DPoP untrusted private JWK** | Header chứa private fields. | Từ chối proof theo profile. |
| **DPoP alg=none/HS256** | Proof không dùng asymmetric alg hợp lệ. | Từ chối. |
| **DPoP public key mismatch** | Proof key thumbprint không khớp cnf.jkt. | Từ chối token binding. |
| **DPoP cache unavailable** | Redis/DB timeout. | Fail closed hoặc approved fallback, không fail-open. |
| **DPoP cache TTL too short** | Marker hết hạn khi proof còn fresh. | Test phát hiện proof được nhận lại, sửa retention. |
| **DPoP cache poisoning** | Attacker gửi proof giả có jti dự đoán. | Không ghi marker khi signature/binding chưa đạt. |
| **DPoP replica failover** | Cache failover làm mất recent entries. | Không cho replay pass trong acceptance window. |
| **DPoP proxy path mismatch** | RS thấy internal URI khác public HTTP target. | Normalization/trust proxy config theo RFC, không nới bỏ htu. |
| **mTLS AT repeated use** | Bound AT gọi hai API requests đúng certificate. | Có thể hợp lệ cả hai; không áp single-use. |
| **mTLS wrong cert** | Bound AT gắn certificate A, request dùng B. | Từ chối. |
| **Authorization code first use** | Redeem code đúng client/PKCE. | Cấp token một lần. |
| **Authorization code second use** | Redeem lại code đã CONSUMED. | Từ chối, không phát token mới. |
| **Authorization code concurrent redeem** | Hai requests cùng code/verifier. | Chỉ một thành công nhờ atomic state. |
| **Authorization code wrong verifier** | PKCE không khớp challenge. | Từ chối. |
| **OIDC nonce mismatch** | ID token thuộc flow/tab khác. | RP từ chối theo transaction binding. |
| **OIDC state mismatch** | Authorization response không khớp stored request. | Client từ chối. |
| **Business idempotent retry** | POST /orders lặp key nhưng DPoP proof mới. | Một business side effect, mỗi request vẫn auth đầy đủ. |
| **Business idempotency bypass** | POST lặp key, proof cũ replay. | DPoP layer từ chối trước business idempotency. |
| **Metrics contain raw RT** | Label/log chứa bearer token. | Phát hiện leakage; không deploy. |
| **High reuse from client update** | New client build tăng RT reuse. | Alert/debug concurrency bug, không kết luận compromise vô chứng cứ. |

### Ma trận tối thiểu cho CI và pre-production

~~~text
1. RT1 first consume -> exactly one RT2 active.
2. RT1 repeated -> invalid_grant + family state per policy.
3. RT1 two concurrent requests -> only one commit.
4. RT family revoked -> descendant RT2 rejected.
5. DPoP proof P1 first -> accept if token/permission valid.
6. Same P1 repeated across replicas -> reject.
7. DPoP proof with wrong htm/htu/ath/jkt -> reject.
8. Bearer AT used twice for legitimate GET -> still valid.
9. Authorization code consumed twice -> only one token issuance.
10. Replay state store unavailable -> no bypass/fail-open.
~~~

## 34. Checklist production cho “Detect reuse”

1. **Token type:** Đã phân biệt access token, refresh token, authorization code và DPoP proof?
2. **Semantics:** One-time policy chỉ áp đúng credential cần one-time?
3. **Bearer AT:** Không coi AT jti xuất hiện lại là tự động compromise?
4. **Refresh rotation:** Mỗi RT chỉ có tối đa một successful consume?
5. **Family lineage:** Có liên kết parent/successor/family/grant một cách đáng tin?
6. **State:** ACTIVE, CONSUMED, REVOKED, EXPIRED và UNKNOWN được phân biệt?
7. **Atomicity:** Có DB transaction/CAS/unique constraints, không GET-then-SET race?
8. **Concurrent requests:** Hai AS replicas không thể cùng cấp hai successors?
9. **Multi-region:** Có authoritative writes hoặc fencing/consensus khi cần?
10. **Family revoke:** Reuse RT đã CONSUMED có thể revoke active descendant theo policy?
11. **Retention:** Giữ used-token tombstones đủ để detect reuse, không lưu raw RT?
12. **RT entropy:** RT sinh bằng CSPRNG, không đoán được?
13. **RT lookup:** Lưu digest/HMAC tra cứu an toàn, key separation và ACL?
14. **Client binding:** Kiểm client authentication/client_id và grants đúng?
15. **Sender binding:** Với RT/AT bị bound, có kiểm DPoP/mTLS proof theo profile?
16. **RT absolute expiry:** Rotation không kéo dài grant vô hạn ngoài chính sách?
17. **Client single-flight:** Có tránh đồng thời refresh trong cùng session?
18. **Multi-tab/process:** Có phối hợp hoặc grant separation thích hợp?
19. **Network retries:** Không tự retry POST refresh không có contract?
20. **Lost response:** Có UX/recovery an toàn khi RT1 consumed nhưng RT2 response mất?
21. **Grace policy:** Nếu có, đã review attacker replay risk và sender binding?
22. **DPoP signature:** Chỉ nhận asymmetric signature/typ/public JWK hợp lệ?
23. **DPoP jkt:** Proof key được ràng với AT confirmation/thumbprint?
24. **DPoP htm/htu:** Gắn đúng method/target URI với reverse proxy config?
25. **DPoP ath:** Ràng proof tới AT được trình ở RS?
26. **DPoP iat:** Có freshness/skew window hữu hạn?
27. **DPoP nonce:** Khi AS/RS yêu cầu, có kiểm challenge và validity?
28. **DPoP jti:** Mỗi proof có jti mới, server chặn reuse trong window?
29. **Replay cache:** SET-if-absent nguyên tử và shared đúng realm/replicas?
30. **Replay key:** Ràng verified key thumbprint + jti + realm, không tin raw header làm identity?
31. **Cache TTL:** Marker còn ít nhất tới khi proof không thể được chấp nhận?
32. **Cache failure:** Không fail-open khi replay store không hoạt động?
33. **Cache poisoning:** Chỉ insert marker sau verify signature/binding?
34. **Authorization code:** Redeem tối đa một lần, PKCE/client/redirect binding đúng?
35. **OIDC state/nonce:** Gắn với authentication transaction, không dùng global mutable nonce?
36. **Idempotency:** Business operation retries không bypass authentication hoặc reuse policy?
37. **Authorization:** RS kiểm issuer/audience/type/exp/scope/tenant/permission độc lập?
38. **Revocation:** AT/grant/RT family state có propagation/SLA khi cần?
39. **Audit:** Có family event, proof replay metrics mà không log raw credentials?
40. **Detection scope:** Không tự revoke account-wide chỉ vì một family khi policy không yêu cầu?
41. **False positives:** Có theo dõi retry/network/client bug, không gán chắc chắn attacker?
42. **Incident response:** Có logout/reauth/recovery phù hợp client và user?
43. **Privacy:** Token fingerprints, device/IP signals có retention/access controls?
44. **Security tests:** Có concurrent, stale replica, duplicate event, lost response, cache outage và rollback tests?
45. **Operational readiness:** SLO, dashboards, alerts, outbox và playbook đã được thử trong pre-production?

## 35. Bài tập vận dụng

### Bài tập 1 — Phân biệt Bearer AT reuse và RT reuse

Một client gửi cùng access token AT1 ba lần để tải danh sách Orders và chi tiết đơn hàng. Sau đó client đổi refresh token RT1 thành RT2. Một request khác gửi RT1 lại.

**Câu hỏi:** Trường hợp nào bắt buộc coi là reuse đáng ngờ?

**Phân tích:**

- Các request mang AT1 có thể hợp lệ vì AT thường là **multi-use Bearer credential**. RS kiểm issuer, audience, exp, scope và permission ở từng request.
- RT1 sau rotation đã CONSUMED, nên request mới với RT1 kích hoạt **refresh reuse** theo strict rotation policy.
- Family có thể cần revoke vì AS không chứng minh được RT2 thuộc attacker hay client nếu cả hai từng giữ RT1.
- Việc RT1 reuse xảy ra không tự chứng minh AT1 đã bị copy; cần xem risk và token revocation requirements.

### Bài tập 2 — Concurrency trong database

Hai token requests A và B gửi RT1 tại hai AS replicas. Hệ thống dùng:

~~~text
read RT1.status
if ACTIVE:
    insert new RT
    update RT1.status = CONSUMED
~~~

**Câu hỏi:** Vì sao dễ sinh hai successors và cần sửa gì?

**Phân tích:** A và B có thể cùng đọc ACTIVE trước khi transaction của bên kia commit. Cần **atomic state transition**: lock family/token hoặc conditional compare-and-set với database constraints, một authoritative write path, và update state/insert successor trong cùng transaction. Chỉ một request thắng; request kia không được phát RT successor thứ hai.

### Bài tập 3 — Có nên bật grace period?

Một team đề xuất cho phép RT1 tiếp tục refresh trong 45 giây sau khi RT2 đã được cấp để giảm lỗi khi mạng chập chờn.

**Câu hỏi:** Quyết định này có an toàn không?

**Phân tích:** Không mặc định. Attacker có RT1 có thể dùng trong 45 giây, có nguy cơ lấy AT/RT mà server không phát hiện reuse. Nếu cần phục hồi, hãy đánh giá sender-constrained RT, client single-flight và giao thức idempotent recovery gắn với authenticated holder/key/operation; không mở grace chỉ bằng một timestamp.

### Bài tập 4 — DPoP proof replay ở hai vùng

RS region A và B dùng hai Redis caches riêng. Attacker gửi cùng DPoP proof jti=J1 đến hai regions trong khoảng iat còn hợp lệ. Mỗi cache chưa thấy J1.

**Câu hỏi:** Có vi phạm mục tiêu replay protection không?

**Phân tích:** Có, nếu cùng proof được chấp nhận ở cả hai nơi trong một replay realm. Cần shared atomic dedup authority hoặc routing/fencing có bảo đảm thật; khi store không khả dụng phải fail closed hoặc theo fallback được review. DPoP signature đúng **không** chứng minh proof chưa từng được dùng.

### Bài tập 5 — DPoP proof mới cho một business retry

Client gửi POST /orders với idempotency key K và DPoP proof P1. Network mất response. Client gửi lại cùng idempotency key K nhưng tạo DPoP proof P2 với jti mới.

**Câu hỏi:** API có nên tạo order thứ hai không?

**Phân tích:** Không, nếu idempotency contract đã ràng operation K với cùng authenticated principal và request semantics. RS vẫn phải xác minh **P2** cùng AT/permission; business layer trả kết quả tương ứng mà không tạo side effect mới. Nếu client tái sử dụng chính P1, DPoP replay check phải từ chối theo policy.

### Bài tập 6 — Token family bị đánh dấu compromised, AT vẫn còn hạn

AS đã revoke RT family khi thấy RT1 reuse. Orders API vẫn chấp nhận JWT AT phát trước incident vì RS verify signature offline và exp chưa tới.

**Câu hỏi:** Có phải lỗi của chữ ký JWT không?

**Phân tích:** Không. JWT signature và expiry chỉ chứng minh claims được bảo vệ và token còn trong thời hạn. Nếu chính sách yêu cầu chặn AT trước exp, cần một **revocation/denylist/introspection/version mechanism** ở RS, cùng propagation SLO hoặc dùng AT ngắn hạn/sender-binding phù hợp. Không được mặc định revoke RT tự sửa JWT offline.

### Bài tập 7 — OIDC nonce bị lặp giữa tabs

Dashboard mở đồng thời hai luồng đăng nhập. App dùng biến toàn cục lastNonce, khiến transaction thứ nhất bị ghi đè bởi nonce của transaction thứ hai.

**Câu hỏi:** Cách thiết kế đúng?

**Phân tích:** Lưu **state-keyed authentication transaction**, mỗi transaction có nonce và issuer/client binding riêng. Khi nhận authorization response, kiểm state rồi đối chiếu nonce của ID token theo transaction tương ứng. Không dùng nonce của DPoP hoặc RT family như một giá trị thay thế.

### Bài tập 8 — Một refresh token vô danh gây logout

API cho caller gửi:

~~~json
{
  "presented_refresh_token": "UNKNOWN_TOKEN",
  "family_id": "VICTIM_FAMILY_ID"
}
~~~

và tự revoke family_id theo body khi lookup token thất bại.

**Câu hỏi:** Đây có phải reuse detection đúng không?

**Phân tích:** Không. Caller không được tự chỉ định family nạn nhân như authority. AS phải xác thực/tra RT digest để xác định family gắn với credential thật, kiểm client/binding và chỉ thực hiện hành động theo trusted state. Một chuỗi unknown token không được phép tạo broad family revoke.

### Tự đánh giá với cây quyết định

~~~mermaid
flowchart TD
    A["Nhận token / proof / request lặp"] --> B{"Loại credential là gì?"}
    B -->|Bearer AT| C["Kiểm issuer, aud, exp, scope, sender proof khi có"]
    C --> D["Không tự coi repeated AT là compromise"]
    B -->|Rotating RT| E{"RT state sau atomic lookup?"}
    E -->|ACTIVE| F["Consume once và phát successor trong transaction"]
    E -->|CONSUMED| G["Reuse signal + family response theo policy"]
    E -->|Khác| H["invalid_grant + audit phù hợp"]
    B -->|DPoP proof| I{"Chữ ký/binding/freshness đúng?"}
    I -->|Không| J["Reject proof"]
    I -->|Có| K{"Atomic jti insert lần đầu?"}
    K -->|Không| J
    K -->|Có| L["Tiếp tục API authorization"]
    B -->|Authorization code| M["Atomic one-time redeem + PKCE/client binding"]
    B -->|Business retry| N["Xác thực mới + idempotency business contract"]
~~~

## Kết luận

**Detect reuse** không có nghĩa cấm mọi token xuất hiện hai lần. Điều quan trọng là xác định **credential nào được phép dùng nhiều lần, credential nào chỉ được tiêu thụ một lần và proof nào phải mới cho từng request**.

- **Bearer access token** thường dùng được trên nhiều request hợp lệ; lặp AT hoặc jti không tự chứng minh tấn công.
- **Refresh token rotation** tạo một chuỗi RT trong cùng family. Nếu một RT đã CONSUMED được trình lại, AS ghi nhận **reuse signal**, từ chối và xử lý active descendant/family theo security policy.
- **Atomic consume-once** là bắt buộc: hai requests đồng thời không được cùng phát hai successor tokens. Transaction/unique constraints/CAS, cùng một nguồn trạng thái authoritative và recovery có kiểm soát quyết định hiệu quả thật.
- **Mất response, multi-tab, tự động HTTP retry và multi-region inconsistency** có thể tạo reuse signal hoặc phá invariant. Client single-flight giúp giảm lỗi, nhưng không thay server-side atomicity.
- **DPoP proof** dùng chữ ký gắn với key và request; RS/AS còn phải kiểm **jti freshness/replay cache, iat, htm, htu, ath, nonce và key binding** theo profile. Một proof mới cần jti mới.
- **Authorization code** có one-time redemption riêng; **OIDC state/nonce, AT jti và business idempotency key** có mục đích khác, không thể thay nhau.
- **DPoP/mTLS sender-constraining, TLS, token TTL, scope/audience restrictions và revocation** bổ trợ cho reuse detection, không tự thay chính sách authorization.
- Reuse event là **bằng chứng credential/proof được trình lại**, không tự xác nhận chính xác ai tấn công. Incident response nên kết hợp containment, audit, giới hạn dữ liệu, theo dõi false positives và đường phục hồi cho client hợp lệ.

Một hệ thống token bảo mật đáng tin phải bảo đảm **tính nguyên tử, kiểm tra đúng trust boundary, trạng thái chống replay được chia sẻ nhất quán, xử lý retry có ý thức về bảo mật và khả năng chứng minh tác động của hành động revoke tại những thành phần cần thiết**.

### Tài liệu tham khảo

- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 7636 — Proof Key for Code Exchange by OAuth Public Clients](https://www.rfc-editor.org/rfc/rfc7636)
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 8252 — OAuth 2.0 for Native Apps](https://www.rfc-editor.org/rfc/rfc8252)
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414)
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705)
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
- [OpenID Connect Core 1.0 — ID Token Validation, nonce](https://openid.net/specs/openid-connect-core-1_0.html)
- [OWASP OAuth 2.0 Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html)
- [OWASP JSON Web Token Cheat Sheet for Java](https://cheatsheetseries.owasp.org/cheatsheets/JSON_Web_Token_for_Java_Cheat_Sheet.html)
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)








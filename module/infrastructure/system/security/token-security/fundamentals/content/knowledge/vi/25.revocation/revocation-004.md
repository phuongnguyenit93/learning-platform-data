# Token family revocation

Trong **OAuth 2.0**, *refresh token* là credential mà client đưa về **Authorization Server (AS)** để xin access token mới mà không bắt người dùng thực hiện toàn bộ authorization flow lần nữa. Một biện pháp phòng chống đánh cắp refresh token là **refresh token rotation**: mỗi lần refresh thành công, AS phát hành **refresh token mới** và làm refresh token cũ **không còn sử dụng được**.

Khi triển khai rotation, nhiều hệ thống quản lý các refresh token sinh ra từ cùng một lần cấp quyền/phiên dưới tên **token family** (*họ token*). Khi phát hiện một refresh token cũ trong family bị **dùng lại**, AS có thể coi **toàn bộ family không còn đáng tin** và thu hồi **refresh token hiện hành**, buộc client hợp lệ phải xác thực/ủy quyền lại. Đây là chủ đề **“Token family revocation”**.

Bài học thuộc chương **Revocation** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**, liên hệ vòng đời token, JWT và opaque token, access/refresh token, authentication, authorization, OAuth 2.0/OIDC, claims, scope, audience, lưu trữ, thu hồi và chống token bị đánh cắp/phát lại.

> **Ý chính:** family revocation là cơ chế **ngăn một chuỗi refresh token tiếp tục tạo access token** khi có bằng chứng reuse hoặc sự cố. Nó phải dựa trên **family boundary**, **rotation nguyên tử**, **phát hiện replay**, **xử lý race/network retry** và **đường thực thi thu hồi ở AS/Resource Server (RS)**. Thu hồi family **không mặc nhiên khiến mọi JWT access token đã cấp ngừng được RS chấp nhận tức thì**.

## 1. Token family là gì?

**Token family** là mô hình triển khai để nhóm các **refresh token có quan hệ kế thừa** trong một phiên/grant cụ thể. Ví dụ:

~~~text
User chấp thuận cho client orders-mobile trên điện thoại A
     |
     +-- AS phát refresh token RT0
                |
                +-- Refresh lần 1: RT0 -> RT1 (RT0 đã dùng)
                                      |
                                      +-- Refresh lần 2: RT1 -> RT2
                                                            |
                                                            +-- Refresh lần 3:
                                                                RT2 -> RT3

Family F-A:
    generation: 0, 1, 2, 3
    active tip: RT3
    older generations: không được đổi thêm lần nữa
~~~

**`family_id`, `generation`, `active_tip` là khái niệm thiết kế, không phải trường chuẩn bắt buộc trong OAuth token response.** RFC 9700 yêu cầu cơ chế phát hiện replay thích hợp cho refresh token của public client, và rotation là một trong các cách đáp ứng. Chuẩn **không bắt mọi AS phải công bố family ID hoặc dùng cùng một schema**.

### Phân biệt các thực thể gần nhau

| Thực thể | Ý nghĩa | Có nhất thiết trùng family? |
|---|---|---|
| **Refresh token** | Credential xin access token mới tại AS | Một thành viên của family nếu dùng rotation |
| **Token family** | Quan hệ kế thừa RT0 → RT1 → RT2 của một session/grant | Là nhóm theo thiết kế AS |
| **Authorization grant** | Quyền ủy quyền từ subject/resource owner tới client | Một grant có thể liên quan một hoặc nhiều family tùy AS |
| **Client ID** | Định danh ứng dụng đã được đăng ký | Một client có thể có nhiều user/device/family |
| **User session / SSO session** | Phiên đăng nhập ở OP/AS hoặc ứng dụng | Có thể tồn tại ngoài một family |
| **Access token** | Credential gửi cho RS trong audience/scope phù hợp | Có thể được phát ra từ các lần refresh của family |
| **Device session** | Ngữ cảnh phiên trên một thiết bị | Thường là ranh giới hữu ích cho family nhưng không bắt buộc |
| **Signing key / JWKS** | Khóa AS dùng ký JWT theo profile | Không phải family; rotation khóa là bài toán khác |

**Không thiết kế “một family cho toàn bộ tài khoản” nếu sản phẩm muốn đăng xuất từng thiết bị.** Ranh giới family nên được chọn nhất quán với grant, client, tenant, device/session và chính sách an ninh của sản phẩm.

## 2. Vì sao chỉ revoke một refresh token là chưa đủ?

Giả sử **RT0** bị sao chép từ điện thoại A. Client hợp lệ dùng RT0 trước và được AS trả RT1. Attacker sau đó gửi RT0:

~~~text
10:00:00  AS phát RT0 cho điện thoại A
10:05:00  Attacker sao chép RT0
10:06:00  App hợp lệ gửi RT0 => AS cấp AT1 + RT1; RT0 thành USED
10:06:03  Attacker gửi RT0 => AS phát hiện reuse
10:06:04  AS thu hồi active RT1 (và family F-A theo policy)
10:06:05  App thử refresh bằng RT1 => invalid_grant; cần đăng nhập lại
~~~

Nếu AS chỉ từ chối **RT0** đã dùng nhưng để **RT1** tiếp tục hoạt động, AS **không thể biết chắc** ai đã sử dụng RT0 trước và ai đang giữ RT1. Trong tình huống attacker đổi RT0 **trước** client, attacker có thể giữ RT1 trong khi client hợp lệ chỉ giữ RT0 và bị từ chối. Vì vậy, **replay detection thường phải làm vô hiệu refresh token đang hoạt động của family**.

RFC 9700 mô tả khi phát hiện replay trong **refresh token rotation**, AS không thể xác định bên nào là hợp pháp chỉ từ hai lần dùng một RT, nên phải thu hồi refresh token đang hoạt động để ngăn chuỗi sử dụng tiếp. Family revocation là cách triển khai dễ hiểu cho yêu cầu đó.

**Cần phân biệt:** request có RT cũ không phải bằng chứng chắc chắn *ai* là attacker. Client hợp lệ cũng có thể vô tình gửi lặp do timeout, xử lý song song hoặc SDK bug. Quyết định bảo mật thường vẫn nghiêng về **dừng chuỗi refresh** rồi yêu cầu authentication lại, đồng thời phân loại sự kiện chính xác trong audit.

## 3. Những tiêu chuẩn liên quan

| Chuẩn | Vai trò đối với token family revocation |
|---|---|
| **RFC 9700 — OAuth 2.0 Security BCP** | Yêu cầu phát hiện replay cho refresh token public client bằng **sender-constraining hoặc rotation**, mô tả hậu quả của reuse và ràng buộc RT với client/grant |
| **RFC 6749 — OAuth 2.0** | Refresh Token grant, client authentication, `invalid_grant` và nền tảng cấp token |
| **RFC 7009 — Token Revocation** | Endpoint client yêu cầu AS vô hiệu token; có thể kéo theo token khác trong cùng grant theo chính sách AS |
| **RFC 7662 — Token Introspection** | Cho RS kiểm tra `active`/metadata của token theo quyền truy cập, hữu ích khi cần nhìn thấy revocation |
| **RFC 6750 — Bearer Token Usage** | Cách gửi access token đến RS, xử lý `invalid_token`/`insufficient_scope` |
| **RFC 9449 — DPoP** | Sender-constrained OAuth token dựa trên proof của khóa bất đối xứng, giúp giảm khả năng token bị sao chép rồi dùng từ bên khác |
| **RFC 8705 — OAuth mTLS** | Client authentication và certificate-bound access token, có thể là một phần chiến lược sender constraint |
| **RFC 9068 — JWT Access Token Profile** | JWT access token có mục đích `at+jwt` và các claims để RS xác minh |
| **OpenID Connect Core** | ID token, session/authentication tại RP; không biến ID token thành refresh/access token |

**Quan trọng về tính chuẩn:** cụm từ **“token family revocation”** là cách đặt tên phổ biến của nhiều nền tảng/kiến trúc. Các thuộc tính như `family_id`, `parent_token_ref` hay “revoke toàn bộ family khi reuse” **là mô hình triển khai**, không phải wire format/JSON field bắt buộc trong RFC 6749 hoặc RFC 7009.

## 4. Vòng đời bình thường: một active refresh token tại một thời điểm

Một family dùng rotation cơ bản có **một nhánh đang hoạt động**. Những refresh token cũ đã được consume không được dùng lại.

~~~mermaid
sequenceDiagram
    autonumber
    participant App as App hợp lệ
    participant AS as Authorization Server
    participant Store as Family store

    AS-->>App: Ban đầu AT0 + RT0
    App->>AS: POST /token grant_type=refresh_token, RT0
    AS->>Store: Lock family F; validate RT0 active tip
    Store-->>AS: RT0 ACTIVE, F ACTIVE
    AS->>Store: Atomic RT0=USED, insert RT1 ACTIVE, tip=RT1
    AS-->>App: AT1 + RT1
    App->>App: Thay RT0 bằng RT1 một cách an toàn
    App->>AS: POST /token với RT1 (sau đó)
    AS->>Store: Atomic RT1=USED, insert RT2 ACTIVE, tip=RT2
    AS-->>App: AT2 + RT2
~~~

Trong minh họa:

- **RT0, RT1, RT2 là giá trị khác nhau**, khó đoán bằng CSPRNG (hoặc được bảo vệ mật mã theo profile).
- **RT0 bị vô hiệu tại lần exchange thành công**. RT1 thay nó trong cùng family.
- Family vẫn **ACTIVE** khi rotation thành công.
- AS giữ **quan hệ lineage hoặc reference đủ để xác định reuse** của token cũ.
- Client phải **lưu RT mới an toàn trước khi loại RT cũ khỏi cơ chế quản lý credential của mình**, nhưng không được cố khôi phục RT cũ để refresh lần nữa khi RT mới đã có.
- Nếu authorization grant/session bị revoke/hết hạn, family có thể hết hiệu lực dù RT hiện hành chưa dùng.

**Một AS có thể thay đổi cách mã hóa/trả token theo policy.** Đừng xây client dựa trên việc RT là JWT, có trường `generation` hoặc độ dài cố định.

## 5. State machine cho refresh token và family

Hai state machine **khác nhau** cần tồn tại về mặt logic:

### Trạng thái của một refresh token

| Trạng thái thiết kế | Ý nghĩa | Có được dùng để refresh? |
|---|---|---|
| **ACTIVE** | Credential hiện hành, chưa consume/revoke/hết hạn | Có, nếu mọi điều kiện khác đạt |
| **USED / CONSUMED** | Đã đổi thành công thành token kế nhiệm | **Không** |
| **REVOKED** | AS chủ động vô hiệu credential | **Không** |
| **EXPIRED** | Quá absolute/inactivity deadline theo policy | **Không** |
| **UNKNOWN** | Không nhận dạng được giá trị token | **Không**, không làm lộ token tồn tại hay không |

### Trạng thái của family

| Trạng thái thiết kế | Ý nghĩa | Hệ quả |
|---|---|---|
| **ACTIVE** | Family/grant còn được phép refresh | Chỉ active tip hợp lệ mới tiếp tục |
| **REVOKED_REUSE** | Phát hiện token đã consume bị trình lại | Active tip bị chặn; yêu cầu reauthentication |
| **REVOKED_USER** | User logout/remove linked device | Không phát RT/AT mới từ family |
| **REVOKED_SECURITY** | Incident nghi lộ token/client/device | Chặn toàn bộ lineage và đánh giá access tokens |
| **EXPIRED** | Family/grant vượt absolute/inactivity TTL | Không được refresh |

~~~mermaid
stateDiagram-v2
    [*] --> F_ACTIVE: AS cấp RT0
    F_ACTIVE --> F_ACTIVE: RTn đúng -> atomic rotate RTn+1
    F_ACTIVE --> F_REUSE: Trình lại RT đã USED
    F_ACTIVE --> F_USER: Logout/remove-device
    F_ACTIVE --> F_SECURITY: Incident/AS policy
    F_ACTIVE --> F_EXPIRED: Absolute/inactivity expiry
    F_REUSE --> [*]: Deny refresh; reauthenticate
    F_USER --> [*]: Deny refresh
    F_SECURITY --> [*]: Deny refresh
    F_EXPIRED --> [*]: Deny refresh
~~~

Đây là **enum gợi ý cho ứng dụng**, không phải enum chuẩn trong OAuth response. “USED” cần được ghi nhận đủ lâu để phát hiện reuse trong khoảng nguy cơ hợp lý; nếu xóa mọi dấu vết ngay khi RT được rotate, AS có thể mất khả năng phân biệt **RT đã dùng** với **chuỗi ngẫu nhiên không tồn tại**.

## 6. Thế nào là reuse và thế nào là một request không hợp lệ?

Một AS tốt phân biệt **sự kiện bảo mật** với **lỗi input**:

| Tình huống | Có phải bằng chứng reuse của family? | Xử lý tối thiểu |
|---|---|---|
| Trình **RT0 đã USED** của family F đang ACTIVE | **Có**, nếu token reference/binding được nhận diện tin cậy | Deny và xử lý active descendant/family theo replay policy |
| Trình chuỗi ngẫu nhiên không hề được cấp | **Không đủ** để xác định family | `invalid_grant`, rate limit, không revoke family tùy tiện |
| Trình RT đã EXPIRED | Chưa đủ phân biệt reuse/tấn công; tùy audit và policy | Deny; phân tích nếu có tín hiệu bất thường |
| Trình RT thuộc **client khác** | Sai client binding, có thể là credential theft | Deny, alert; chỉ revoke đúng phạm vi có bằng chứng |
| Trình RT active nhưng **sender proof sai** | Sai PoP/binding; có thể là stolen RT | Deny; policy có thể revoke nếu có bằng chứng thích hợp |
| Trình RT khi family đã REVOKED | Không được dùng; không tạo family mới | `invalid_grant`, log hạn chế, tránh revoke nhầm sibling |
| Hai request hợp lệ **đồng thời cùng RT** | Một thắng, request sau thấy USED | Nếu AS không phân biệt, có thể kích hoạt reuse detection |
| Token response mất, client retry RT cũ | Về mặt AS, RT cũ có thể đã USED | Có thể kích hoạt family revocation; cần xử lý UX |

**Không dùng một chuỗi `invalid_grant` duy nhất để suy ra nguyên nhân bên trong.** OAuth cố ý có lỗi generic cho client; AS có thể phân biệt `EXPIRED`, `USED_REPLAY`, `UNKNOWN`, `WRONG_CLIENT`... trong **audit bảo vệ**.

## 7. Thu hồi family có phạm vi đến đâu?

Ranh giới family nên được thiết kế theo **authorization grant, client và ngữ cảnh phiên/thiết bị**, không suy ngược từ username.

~~~text
Account user-42
|
+-- Client orders-mobile
|     +-- Device A / grant GA / family FA: RT0 -> RT1 -> RT2
|     +-- Device B / grant GB / family FB: RB0 -> RB1
|
+-- Client orders-web
      +-- Browser C / grant GC / family FC: RC0 -> RC1

Reuse RT1 thuộc FA:
    Revoke family FA (và active RT2)
    FB, FC có thể tiếp tục nếu không có bằng chứng/phạm vi sự cố lớn hơn
~~~

### Những loại “thu hồi rộng” khác nhau

| Ý định | Phạm vi thường phù hợp |
|---|---|
| **Logout thiết bị A** | Session/grant/family của thiết bị A, cộng token liên quan theo policy |
| **Phát hiện reused refresh token của family A** | Active RT và family A; cân nhắc access tokens đã cấp từ A |
| **User chọn logout all devices** | Toàn bộ families/sessions trong phạm vi tài khoản được định nghĩa |
| **User revoke một app OAuth** | Grants/families của app đó theo consent/AS policy |
| **Client secret/key bị lộ** | Có thể rộng hơn một family: các grants/tokens của client liên quan |
| **AS signing key bị lộ** | Sự cố cấp hệ thống/key, **không** giải quyết bằng family revoke đơn thuần |
| **Account takeover hoặc mật khẩu bị thay** | Policy có thể revoke nhiều sessions/grants sau xác minh rủi ro |

**Đừng tùy tiện revoke mọi session của user chỉ vì một HTTP 400 từ token endpoint.** Cũng đừng giới hạn chỉ family khi dấu hiệu cho thấy **malware trên toàn thiết bị** hoặc **client credential** đã bị lộ: lúc đó incident scope có thể rộng hơn.

## 8. Tạo và lưu refresh token đủ an toàn

### Credential phải khó đoán

Với **opaque refresh token**, dùng **CSPRNG** tạo giá trị có entropy cao (ví dụ 32 random bytes Base64url), không phải counter, timestamp hay user ID. AS thường lưu reference băm/HMAC thay cho raw credential, kết hợp metadata family.

~~~text
raw_refresh_token = BASE64URL(CSPRNG_32_bytes())
token_ref = HMAC_SHA256(server_lookup_key, raw_refresh_token)

family record:
    family_id
    grant_ref, issuer, client_id, subject_ref, device/session_ref
    family_status
    active_token_ref
    created_at
    absolute_expires_at
    inactivity_expires_at (nếu áp dụng)
    revoked_at, revoke_reason

token record:
    token_ref
    family_id
    parent_token_ref
    generation
    token_status
    issued_at, expires_at, consumed_at
~~~

**32 random bytes/256-bit entropy là ví dụ thiết kế**, không phải quy định độ dài cố định trong RFC 6749. HMAC key là secret riêng của AS; nên quản lý bằng KMS/secret manager, xoay vòng có kế hoạch và tránh đưa lookup key vào log.

### JWT refresh token thì sao?

AS có thể chọn refresh token self-contained được ký/mã hóa, nhưng **family revocation vẫn cần trạng thái tin cậy** để biết:

- Token cụ thể đã được dùng chưa.
- Token hiện hành của family là token nào.
- Family/grant còn active không.
- Có reuse/tombstone cần xử lý không.

**Chữ ký hợp lệ và `exp` chưa đủ để đảm bảo single-use hoặc family-wide revoke.** Định dạng token không thay thế transaction state.

## 9. Schema PostgreSQL minh họa hai tầng family/token

Mô hình sau là **schema gợi ý**, không phải cấu trúc bắt buộc của OAuth hoặc một migration đã hoàn thiện:

~~~sql
CREATE TABLE refresh_families (
    family_id          UUID PRIMARY KEY,
    grant_ref          TEXT NOT NULL,
    issuer             TEXT NOT NULL,
    client_id          TEXT NOT NULL,
    subject_ref        TEXT,
    device_ref         TEXT,
    status             TEXT NOT NULL,
    active_token_ref   TEXT,
    created_at         TIMESTAMPTZ NOT NULL,
    expires_at         TIMESTAMPTZ NOT NULL,
    revoked_at         TIMESTAMPTZ,
    revoke_reason      TEXT,
    CHECK (status IN ('ACTIVE','REVOKED','EXPIRED'))
);

CREATE TABLE refresh_token_records (
    token_ref          TEXT PRIMARY KEY,
    family_id          UUID NOT NULL REFERENCES refresh_families(family_id),
    parent_token_ref   TEXT,
    generation         BIGINT NOT NULL,
    status             TEXT NOT NULL,
    issued_at          TIMESTAMPTZ NOT NULL,
    expires_at         TIMESTAMPTZ NOT NULL,
    consumed_at        TIMESTAMPTZ,
    CHECK (status IN ('ACTIVE','USED','REVOKED','EXPIRED')),
    UNIQUE (family_id, generation)
);

CREATE INDEX idx_refresh_family
    ON refresh_token_records (family_id);

CREATE INDEX idx_refresh_family_expiry
    ON refresh_families (expires_at);
~~~

**Tối thiểu cần những invariants:**

1. Family `ACTIVE` có **tối đa một active tip** theo rotation model đơn tuyến, ngoại trừ profile cố ý định nghĩa cơ chế khác.
2. Mỗi `token_ref` thuộc **đúng một family**.
3. Token `USED` **không quay lại ACTIVE** vì client retry.
4. Token kế nhiệm phải tham chiếu đúng **parent token** và generation.
5. Family `REVOKED` không thể nhận active tip mới qua request `refresh_token` thông thường.
6. **Không cấp token trước khi transaction cập nhật trạng thái đã commit an toàn**.
7. Khi AS nhiều nodes/regions, tất cả phải tôn trọng **một nguồn trạng thái mạnh** cho family.

Schema này chưa có FK tự tham chiếu parent, partial unique index cho active-token, grant table, RLS, encryption at rest hay row-level tenant policy. **Production phải bổ sung các ràng buộc này** và kiểm thử concurrency/backup/restore.

## 10. Refresh Token grant và rotation bình thường

Client gọi token endpoint qua TLS:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <CLIENT_CREDENTIALS_IF_CONFIDENTIAL>

grant_type=refresh_token&refresh_token=<RT_N>
~~~

Client public có cách xác định và binding theo registration; **không nhúng client secret dùng chung vào SPA/mobile/firmware** rồi coi đó là confidential authentication. Khi AS hỗ trợ DPoP/mTLS, request phải có proof tương ứng theo profile.

Sau khi kiểm tra grant, client, token, binding và policy, AS có thể trả:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache
~~~

~~~json
{
  "access_token": "<ACCESS_TOKEN_N_PLUS_1>",
  "token_type": "Bearer",
  "expires_in": 600,
  "scope": "orders:read",
  "refresh_token": "<RT_N_PLUS_1>"
}
~~~

Trong **rotation**, RT mới thay RT cũ. Client nên cập nhật credential store **nguyên tử theo khả năng của nền tảng** để không còn hai worker cùng sử dụng RT cũ.

**Không phải mọi refresh response đều bắt buộc chứa RT mới theo RFC 6749 chung.** Nhưng khi AS áp dụng **refresh token rotation**, hệ thống phải có cách phát RT kế nhiệm, đánh dấu RT cũ unusable và giữ liên kết đủ để phát hiện replay. Cách nhận biết rotation/đặt secret phụ thuộc provider contract.

## 11. Atomic rotation — tránh hai lần refresh đều thành công

Lỗi kinh điển:

~~~text
Request A: read RT0.status=ACTIVE
Request B: read RT0.status=ACTIVE
Request A: issue AT1 + RT1
Request B: issue AT2 + RT2
Request A: mark RT0 USED
Request B: mark RT0 USED
~~~

Cả hai refresh thành công từ **một credential dùng một lần**, phá hủy lineage/active-tip invariant. Cần **atomic compare-and-swap, row lock, transaction hoặc cơ chế tương đương**.

### Quy trình giao dịch an toàn

1. Tra `token_ref` từ RT được trình và xác định family bằng **dữ liệu AS tin cậy**. Không lấy `family_id` từ query do client tự đặt.
2. Xác thực client và kiểm tra sender proof/binding theo registration.
3. **Lock family record** hoặc thực hiện atomic transition trên store có consistency đủ.
4. Đọc token record đang trình, kiểm tra family/grant còn active và deadline.
5. Nếu token đã **USED**: ghi nhận reuse, chuyển family sang **REVOKED**, vô hiệu active tip, audit event rồi trả lỗi.
6. Nếu token là **ACTIVE tip** và mọi kiểm tra đạt: đánh dấu USED, tạo RT kế nhiệm ACTIVE, cập nhật family.active_tip và lưu issuance metadata **trong cùng transaction**.
7. Commit trước khi trả token response. Bảo đảm token issuance và family state nhất quán khi crash.
8. Không dùng mutex `synchronized` trong một instance Java để bảo vệ AS multi-node.

~~~mermaid
flowchart TD
    IN["POST /token với refresh token RTn"] --> B{"Client và sender binding hợp lệ?"}
    B -->|"Không"| DENY["Deny invalid_grant / invalid_client theo ngữ cảnh"]
    B -->|"Có"| L["Tìm family bằng trusted token_ref, lock transaction"]
    L --> F{"Family/grant ACTIVE và còn hạn?"}
    F -->|"Không"| DENY
    F --> S{"Token record là USED?"}
    S -->|"Có"| REVOKE["Atomic revoke family + active RT + audit REUSE"]
    REVOKE --> DENY
    S -->|"Không"| T{"RTn là ACTIVE tip, chưa hết hạn?"}
    T -->|"Không"| DENY
    T -->|"Có"| R["Atomic RTn=USED, insert RTn+1, tip=RTn+1"]
    R --> COMMIT["Commit issuance metadata + state"]
    COMMIT --> RESP["Trả access token và RTn+1"]
~~~

**Đừng tự revoke family nếu không tìm được token record**: một attacker có thể gửi chuỗi ngẫu nhiên; AS không thể biết nó thuộc family nào. Với token đã nhận dạng và trước đây USED, AS phải xử lý reuse theo replay policy và phạm vi family phù hợp.

## 12. SQL minh họa transaction rotate và phát hiện reuse

Phần này dùng **PostgreSQL pseudo-SQL** với tham số và điều kiện ứng dụng. Nó **không chạy nguyên vẹn** vì nhánh logic, xác thực client/proof và token signing phải được lập trình riêng.

~~~sql
BEGIN;

-- :presented_token_ref = HMAC tại AS từ RT nhận được,
-- KHÔNG phải giá trị do caller trực tiếp khai.
SELECT family_id, token_ref, status, expires_at
FROM refresh_token_records
WHERE token_ref = :presented_token_ref;

-- Nếu UNKNOWN: không có family để revoke; ROLLBACK + invalid_grant.
-- Nếu tìm thấy: lock family và re-read token under lock.
SELECT family_id, client_id, grant_ref, status,
       active_token_ref, expires_at
FROM refresh_families
WHERE family_id = :trusted_family_id
FOR UPDATE;

SELECT token_ref, status, expires_at, generation
FROM refresh_token_records
WHERE token_ref = :presented_token_ref
FOR UPDATE;

-- Branch A: presented token status = USED và family còn ACTIVE
-- => phát hiện reuse (sau khi xác minh context cần thiết).
-- UPDATE refresh_families SET status='REVOKED', ...
-- UPDATE refresh_token_records SET status='REVOKED'
-- WHERE family_id=:trusted_family_id AND status='ACTIVE';
-- Lưu security event cùng transaction, COMMIT, trả invalid_grant.

-- Branch B: đúng ACTIVE tip, family/grant/client/proof còn hợp lệ.
UPDATE refresh_token_records
SET status = 'USED',
    consumed_at = CURRENT_TIMESTAMP
WHERE token_ref = :presented_token_ref
  AND family_id = :trusted_family_id
  AND status = 'ACTIVE'
  AND expires_at > CURRENT_TIMESTAMP;

-- Require affected row count = 1.
-- Phát sinh RT mới bằng CSPRNG bên AS và HMAC => :new_token_ref.
INSERT INTO refresh_token_records
    (token_ref, family_id, parent_token_ref, generation,
     status, issued_at, expires_at)
VALUES
    (:new_token_ref, :trusted_family_id, :presented_token_ref,
     :old_generation_plus_one, 'ACTIVE',
     CURRENT_TIMESTAMP, :new_expires_at);

UPDATE refresh_families
SET active_token_ref = :new_token_ref
WHERE family_id = :trusted_family_id
  AND status = 'ACTIVE'
  AND active_token_ref = :presented_token_ref
  AND expires_at > CURRENT_TIMESTAMP;

-- Require family update count = 1; persist grant/token issuance
-- metadata cùng transaction. Nếu thất bại: ROLLBACK.
COMMIT;
~~~

**Cẩn thận:** đây là **các statement cho các nhánh khác nhau**, không phải bảo chạy toàn bộ tuần tự. Triển khai phải check **số dòng thay đổi**, đúng trạng thái và binding, và quản lý transaction rollback/commit theo nhánh đã quyết định.

### Vấn đề signed access token khi database rollback

Nếu AS ký JWT access token trước khi commit, sau đó transaction thất bại mà JWT đã được gửi cho client hoặc xuất hiện ở queue/log, có thể sinh token **không nhất quán với grant**. Phải bảo đảm **không trả/không phát tán token response trước khi state commit**. Với side effects bên ngoài database, dùng outbox/idempotent issuance hoặc thiết kế bù trừ chặt, không cho retry vượt single-use.

## 13. Java 17: quyết định rotate hay revoke dưới transaction

Ví dụ Java 17 dùng mô hình **policy decision** để tách ba kết quả: **ROTATE**, **REVOKE_FAMILY_REUSE**, **DENY**. Phần DB lock/CAS phải do transaction repository cung cấp; đoạn này **không tự thay database hoặc OAuth endpoint**.

~~~java
import java.time.Clock;
import java.time.Instant;
import java.util.Objects;

public final class RefreshFamilyPolicy {
    public enum FamilyStatus { ACTIVE, REVOKED, EXPIRED }
    public enum TokenStatus { ACTIVE, USED, REVOKED, EXPIRED, UNKNOWN }
    public enum Decision { ROTATE, REVOKE_FAMILY_REUSE, DENY }

    public record Snapshot(
            FamilyStatus familyStatus,
            TokenStatus presentedTokenStatus,
            boolean matchesActiveTip,
            boolean sameRegisteredClient,
            boolean senderProofVerified,
            boolean grantStillActive,
            Instant familyExpiresAt,
            Instant tokenExpiresAt
    ) {
        public Snapshot {
            Objects.requireNonNull(familyStatus);
            Objects.requireNonNull(presentedTokenStatus);
            Objects.requireNonNull(familyExpiresAt);
            Objects.requireNonNull(tokenExpiresAt);
        }
    }

    // Chỉ gọi bên trong transaction đã lock family và
    // sau khi lấy đúng token record từ trusted token_ref.
    public static Decision assess(Snapshot s, Clock clock) {
        Instant now = clock.instant();

        if (s.familyStatus() != FamilyStatus.ACTIVE) {
            return Decision.DENY;
        }

        // Sai client/proof: không được đổi token hoặc tiết lộ family.
        // Incident handler có thể áp dụng revoke theo tín hiệu riêng.
        if (!s.sameRegisteredClient()
                || !s.senderProofVerified()) {
            return Decision.DENY;
        }

        // Token cũ đã consume bị trình lại: nguy cơ replay.
        if (s.presentedTokenStatus() == TokenStatus.USED) {
            return Decision.REVOKE_FAMILY_REUSE;
        }

        if (!s.grantStillActive()
                || !now.isBefore(s.familyExpiresAt())
                || s.presentedTokenStatus() != TokenStatus.ACTIVE
                || !s.matchesActiveTip()
                || !now.isBefore(s.tokenExpiresAt())) {
            return Decision.DENY;
        }

        return Decision.ROTATE;
    }

    public static void main(String[] args) {
        Clock demoClock = Clock.fixed(
                Instant.parse("2026-11-23T10:00:00Z"),
                java.time.ZoneOffset.UTC
        );
        Instant later =
                Instant.parse("2026-11-23T11:00:00Z");

        Snapshot current = new Snapshot(
                FamilyStatus.ACTIVE,
                TokenStatus.ACTIVE,
                true, true, true, true,
                later, later
        );
        Snapshot replay = new Snapshot(
                FamilyStatus.ACTIVE,
                TokenStatus.USED,
                false, true, true, true,
                later, later
        );

        System.out.println(assess(current, demoClock));
        System.out.println(assess(replay, demoClock));
        // ROTATE
        // REVOKE_FAMILY_REUSE
    }

    private RefreshFamilyPolicy() {}
}
~~~

**Giới hạn cần nhớ:**

- `Snapshot` phải được xây từ **AS-controlled database state** trong lock/transaction; nếu đọc một bản sao cache stale, các kết quả không còn đáng tin.
- `senderProofVerified` chỉ là tín hiệu **đã kiểm tra crypto proof thật** theo DPoP/mTLS hoặc profile; không lấy boolean do client gửi.
- Logic `USED` chỉ gọi reuse sau khi binding/identity context phù hợp; wrong client/proof có thể cần **separate security incident policy**, không mặc định coi mọi request lỗi là family replay.
- `Decision.REVOKE_FAMILY_REUSE` chỉ là chỉ thị; repository phải **commit family revoke + active tip revoke atomically**, rồi phát `invalid_grant`. Không chỉ log và trả lỗi.
- Deadline trong ví dụ là mock; AS thực cần bảo vệ inactivity timeout, absolute expiry, logout/consent grant revoke và token usage.
- `ROTATE` **không** đồng nghĩa đã tạo token; còn phải tạo RT mới, ghi state và issuance đồng bộ, quản lý transaction crash.

## 14. Concurrency: hai refresh request từ cùng một client

Giả sử client có AT sắp hết hạn và **hai API requests** cùng quyết định refresh:

~~~text
App worker A: nhận 401, dùng RT7 để refresh
App worker B: cùng lúc dùng RT7 để refresh
AS: worker A thắng lock, RT7 => USED, phát RT8
AS: worker B tới sau, thấy RT7 = USED
AS: theo rotation replay detection, family có thể bị revoke
App: vừa được RT8 nhưng lại bị đăng xuất
~~~

Đây là **false positive đối với kết luận “có attacker”**, nhưng **không phải lỗi giả** ở cấp trạng thái: refresh token đã được sử dụng hai lần. AS không thể luôn phân biệt legitimate duplicate với stolen credential.

### Phòng tránh từ phía client

- Chỉ **một refresh operation tại một thời điểm cho mỗi session/family** (*single-flight*).
- Các request đồng thời **chờ cùng một Promise/Future** thay vì mỗi request gửi RT cũ.
- Lưu RT mới **nguyên tử** và đưa đến các worker/tab/process cần nó.
- Nếu nhiều tab/browser windows chia sẻ session, phối hợp bằng **backend BFF** hoặc cơ chế lock/ownership được thiết kế kỹ; JavaScript mutex của một tab **không** khóa tab khác.
- Với mobile/desktop nhiều tiến trình, dùng repository/OS synchronization phù hợp; không phát tán RT trong message/log không cần thiết.
- **Không retry một cách mù quáng** khi refresh thất bại hoặc token endpoint timeout.

### Phòng tránh từ phía AS

- Không cho hai token requests cùng RT **đều thành công**: atomic lock/compare-and-swap.
- Ghi lý do `REUSE_DETECTED` nhưng không khẳng định chính xác bên nào độc hại.
- Có chính sách rate limit, alert và UX khôi phục.
- Tránh “grace period” chấp nhận RT cũ lần hai mà không kiểm toán; nếu có provider extension phục hồi retry, phải chứng minh không cho attacker mở cửa sổ replay và được triển khai theo **protocol/policy cụ thể**.

**Mục tiêu đúng:** hạn chế duplicate refresh ở client và đảm bảo **không nới single-use** ở AS.

## 15. Mất token response sau khi AS đã commit

Tình huống khó hơn concurrency:

~~~text
10:00:00  Client gửi RT4
10:00:01  AS commit: RT4 USED, RT5 ACTIVE, phát AT5
10:00:02  TCP connection rớt, client KHÔNG nhận AT5/RT5
10:00:05  Client retry RT4
10:00:06  AS thấy RT4 USED => replay signal, có thể revoke family
~~~

**Không có kết luận chắc chắn từ phía client** rằng token request timeout nghĩa AS chưa xử lý. Đó là vấn đề *at-least-once delivery* ở kênh request/response.

Các lựa chọn:

1. **An toàn mặc định:** client coi refresh thất bại không chắc chắn, không thử lại RT cũ vô hạn, yêu cầu **authorization/login mới**.
2. **Extension do AS kiểm soát:** cơ chế deduplication/idempotency có ràng buộc client/sender proof, TTL cực ngắn, replay resistance và không cho hai bộ credentials khác nhau. Phải được thiết kế, ghi tài liệu và threat-model riêng; **không phải hành vi mặc định của RFC 6749/9700**.
3. **Giám sát:** ghi tỷ lệ network timeout, retry, reused RT và invalid_grant theo client version để phát hiện SDK bug trước khi tăng tỷ lệ logout.

**Không kéo dài family TTL hay khôi phục RT4 về ACTIVE để chữa rớt mạng.** Điều đó làm yếu thuộc tính replay detection, nhất là nếu attacker đang giữ RT4.

## 16. Sender-constrained refresh token: giải pháp thay thế hoặc bổ sung

RFC 9700 nêu **hai hướng chống refresh token replay cho public client**:

1. **Refresh token rotation:** mỗi lần dùng phát RT mới và làm token cũ không còn hợp lệ, duy trì quan hệ để phát hiện reuse.
2. **Sender-constrained refresh tokens:** ràng buộc token với **một khóa/đặc tính sender** và yêu cầu proof ở mỗi lần sử dụng.

AS có thể kết hợp **cả hai** nếu threat model/phần mềm hỗ trợ.

| Thuộc tính | Rotation | Sender constraint |
|---|---|---|
| Chống attacker chỉ copy RT | Phát hiện khi RT cũ bị dùng lại; có thể ngăn refresh sau replay | Attacker thiếu key/cert không dùng được RT |
| Cần trạng thái server-side | Cần lineage/used-state đủ để phát hiện reuse | Cần binding/proof validation; tùy token design |
| Rủi ro retry/network timeout | Có thể dẫn tới reuse detection và logout | Không tự giải quyết lost response nếu cũng rotate |
| Nếu attacker lấy cả RT và key | Vẫn có rủi ro, rotation có thể phát hiện cạnh tranh | Proof không còn phân biệt attacker/legit |
| Gắn với client/device | Thường qua grant/client/family | Qua key/certificate thumbprint và client binding |
| Tiêu chuẩn liên quan | RFC 9700, RFC 6749 | RFC 9449 (DPoP), RFC 8705 (mTLS) |

### DPoP

Khi dùng DPoP, client ký proof JWT bằng khóa riêng, bao gồm dữ liệu ràng buộc request theo RFC 9449. AS xác minh proof và token binding ở token endpoint; RS kiểm tra proof riêng cho access token có sender constraint. **Không tin một header `DPoP` chỉ vì nó tồn tại.**

### mTLS

Với mTLS, AS xác thực certificate và ràng buộc token với certificate theo profile RFC 8705. Không tự coi một mTLS connection ở gateway là đủ nếu AS/RS không được chuyển bằng chứng đáng tin qua kiến trúc.

**Sender constraint không đồng nghĩa family revocation không còn hữu ích.** Khi khóa hoặc thiết bị bị chiếm, AS có thể vẫn cần revoke grant/family. Đồng thời, không tự tuyên bố mọi refresh token public client bắt buộc rotate **và** DPoP; RFC 9700 cho phép các chiến lược chống replay theo profile.

## 17. Các sự kiện kích hoạt family revoke

| Trigger | Phạm vi đề xuất | Lưu ý |
|---|---|---|
| **RT cũ bị dùng lại** | Family hiện hành bị nghi replay | Phải xác định đúng family từ trusted token record |
| **User chọn Logout this device** | Session/grant/family của thiết bị đó | Không tự logout mọi thiết bị khác |
| **User chọn Logout all devices** | Nhiều family/sessions của account | Cần quyền xác minh và cảnh báo phù hợp |
| **Remove linked device** | Family/credentials của device association | Phân biệt tài khoản và vật lý thiết bị |
| **User revoke consent cho OAuth client** | Grants/families gắn app/consent đó | Có thể rộng hơn một family |
| **Password reset/reauthentication security event** | Theo risk policy; có thể nhiều grants | Không giả định RFC buộc reset mật khẩu revoke mọi AT |
| **Nghi ngờ malware/RT bị lộ** | Family, grants hoặc toàn bộ session theo blast radius | Lưu forensic evidence trước khi cleanup phù hợp |
| **Client credentials/keys bị lộ** | Có thể mọi grant của client | Chỉ family revoke có thể không đủ |
| **Family inactivity/absolute expiry** | Family hết hiệu lực | Không tự làm mới deadline bằng retry token cũ |
| **Account deprovision/tenant ban** | Tất cả grants/tokens liên quan theo policy | Bảo đảm RS nhìn thấy trạng thái mới |

**Phân biệt voluntary revocation và reuse detection:** cả hai có thể làm family inactive, nhưng **reason code và cách xử lý incident/UX khác nhau**. User chủ động logout không cần báo động “token bị đánh cắp”.

## 18. RFC 7009 revocation endpoint và family semantics

OAuth Token Revocation (RFC 7009) cho phép client yêu cầu AS vô hiệu token:

~~~http
POST /oauth2/revoke HTTP/1.1
Host: auth.example.test
Authorization: Basic <CLIENT_CREDENTIALS_IF_CONFIDENTIAL>
Content-Type: application/x-www-form-urlencoded

token=<REFRESH_TOKEN>&token_type_hint=refresh_token
~~~

Các điểm cần nắm:

- Endpoint dùng **HTTPS** và client authentication/authorization phù hợp.
- `token_type_hint` chỉ là **gợi ý lookup**, không xác thực loại token hoặc quyền của caller.
- Thành công thường trả **HTTP 200**, kể cả khi token được gửi không còn hợp lệ/không tồn tại, để tránh lộ token existence.
- Nếu `token_type_hint` không được hỗ trợ, AS có thể trả `unsupported_token_type` theo RFC 7009; lỗi client authentication phải xử lý riêng.
- **Nếu revoke refresh token và AS có hỗ trợ access-token revocation, RFC 7009 khuyến nghị mạnh (SHOULD) vô hiệu các access token phát từ cùng authorization grant.** Nếu revoke một access token, AS **có thể (MAY)** thu hồi refresh token liên quan. Phạm vi triển khai cụ thể và tốc độ RS nhìn thấy trạng thái vẫn cần kiểm chứng.

**RFC 7009 không định nghĩa một tham số chuẩn `revoke_family=true`.** Một AS có thể thực thi “revoke refresh token hiện hành = revoke cả family/grant” theo chính sách. Client phải biết **hợp đồng provider** thay vì suy từ HTTP 200 rằng mọi AT/RT đã bị vô hiệu tại mọi RS ngay lúc đó.

### So sánh endpoint revocation với reuse detection

| Nguồn | Ai chủ động? | Khi nào? | Kết quả |
|---|---|---|---|
| **RFC 7009 /revoke** | Client được phép | Logout, gỡ quyền, cleanup | Token/grant bị revoke theo AS policy |
| **Family revoke on reuse** | AS tự phát hiện | Trình RT USED lần nữa | Dừng active RT/family, security event |
| **Grant admin revoke** | User/admin/AS | Consent revoke, incident, deprovision | Có thể revoke nhiều families và tokens |
| **Session logout** | RP/OP/user | Kết thúc phiên login | Không đồng nghĩa mọi access token tại RS bị chặn tức thì |

## 19. Access token đã cấp sẽ ra sao khi family bị revoke?

Đây là **điểm cần phân biệt rõ nhất** giữa **refresh token family** và **access token**:

- Family revoke ngăn **tiếp tục dùng refresh token** của family để cấp AT mới.
- **Access token đã cấp trước đó** có expiry và cách xác minh riêng.
- Một AS **có thể** chọn revoke các access token liên quan tới grant/family khi xảy ra reuse/security incident.
- Nhưng với **JWT access token được RS verify offline**, đánh dấu family `REVOKED` trong AS database **không tự động khiến RS biết** token cũ cần bị chặn.

### Các cơ chế thực thi tại Resource Server

| Cơ chế | Thấy family revoke thế nào? | Trade-off |
|---|---|---|
| **Opaque AT + RFC 7662 introspection mỗi request** | AS trả `active:false` khi AT được revoke hoặc grant inactive, theo policy | Phụ thuộc AS/latency, cần fail-closed |
| **Introspection có cache** | Khi cache hết hạn hoặc nhận invalidation event | Có **revocation visibility delay** |
| **JWT AT verify offline** | Không thấy thay đổi family state tự nhiên | Có thể tiếp tục đến `exp` |
| **JWT + denylist/grant-version check** | RS tra state/denylist đã lan truyền | Thêm dependency/cache/consistency |
| **JWT thời hạn rất ngắn** | Giới hạn thời gian AT còn được dùng | Không revoke tức thì; cần cân bằng UX |
| **Push revoke events tới RS** | RS cập nhật denylist/cache khi nhận sự kiện | Cần reliable delivery, ordering và recovery |

**Đừng tuyên bố “revoke family ngay = mọi API lập tức 401”** nếu kiến trúc vẫn chấp nhận JWT offline không tra revocation. Cần đo và tài liệu hóa **max revocation propagation delay** cho từng API/scope.

### Khi nghi lộ RT

Nếu RT đã bị đánh cắp và attacker có thể đã dùng để xin AT, incident response có thể cần **revoke AT liên quan, grant và sessions** chứ không chỉ dừng refresh. Phạm vi đó là **policy/thiết kế incident riêng**, không mặc định có trong mọi RFC 7009 implementation.

## 20. Introspection và trạng thái family tại AS

Một AS có thể gắn access token với `grant_ref`/`family_ref` để trả `active:false` khi chính sách security yêu cầu. Ví dụ phản hồi RFC 7662:

~~~json
{
  "active": false
}
~~~

Với access token còn được chấp nhận:

~~~json
{
  "active": true,
  "iss": "https://auth.example.test",
  "aud": "https://orders-api.example.test",
  "scope": "orders:read",
  "exp": 1800003600,
  "client_id": "orders-mobile",
  "sub": "user-42"
}
~~~

**Trường `active` là bắt buộc**, các trường metadata khác là tùy chọn theo RFC 7662. RS vẫn phải kiểm tra đúng audience, scope, purpose, thời gian và object ACL. `active:false` không tiết lộ vì sao token inactive; một RS có thể không được phép introspect token của resource khác.

**Refresh token cũng có thể được AS introspect theo policy**, nhưng nếu RT còn active thì nó **không trở thành API access token**. `token_type_hint=access_token` không phải bảo đảm về mục đích token; RS và AS cần hợp đồng type/purpose rõ ràng.

## 21. Distributed systems: tránh family split-brain

Rotation/family revoke cần correctness trên toàn bộ AS nodes, không chỉ trong một JVM:

~~~mermaid
sequenceDiagram
    autonumber
    participant Device as Client / attacker
    participant AS1 as AS node 1
    participant AS2 as AS node 2
    participant DB as Shared family state
    participant RS as Resource Server

    Device->>AS1: Refresh RT7
    AS1->>DB: Lock F, RT7 ACTIVE -> RT8, commit
    AS1-->>Device: RT8 + AT8
    Device->>AS2: Replay RT7
    AS2->>DB: Lock F, thấy RT7 USED
    AS2->>DB: Revoke F và active RT8, commit
    AS2-->>Device: invalid_grant
    AS2-->>RS: Revocation event nếu có
    RS->>RS: Invalidate cache/denylist theo policy
~~~

### Bẫy vận hành

| Bẫy | Hậu quả | Cách xử lý |
|---|---|---|
| DB replicas eventual consistency | Hai node cùng thấy RT ACTIVE và phát RT mới | Strong consistency hoặc home-region leader/claim protocol |
| Cache family `ACTIVE` stale | Node tiếp tục cấp AT/RT sau revoke | Validate trên source of truth hoặc invalidation đảm bảo |
| Event gửi trước DB commit | RS thấy revoke mà AS transaction rollback | Outbox/durable events có ordering/idempotency |
| Event mất ở một region | Một API vẫn nhận AT bị revoke | Retry/reconciliation, watermark và monitoring |
| Đồng hồ giữa các AS lệch | RT hết hạn không nhất quán | Đồng bộ clock, check absolute deadline dưới transaction |
| Cleanup xóa ngay tombstone USED | Mất khả năng phát hiện reuse | Retention có kiểm soát cho token refs đã dùng |
| Revoke theo user_id quá rộng | Đăng xuất nhầm mọi thiết bị | Family/grant/device boundary được định nghĩa rõ |
| Cache key chỉ token prefix/kid | Sai family hoặc collision/security leaks | HMAC ref đủ entropy + issuer/client/grant partition |
| Authorization policy đổi khi RT vẫn active | Token mới bị cấp vượt grant hiện tại | Recheck grant, allowed scopes/resources trước issuance |

**Family state phải có nguồn sự thật rõ ràng.** Việc dùng Redis TTL, database shard hay token claims là lựa chọn kỹ thuật; quan trọng là **atomic, consistent, replay-detectable và test được khi failover**.

## 22. Audit, telemetry và chống rò bí mật

Các event gợi ý:

| Event | Khi phát | Dữ liệu audit an toàn |
|---|---|---|
| `refresh.family.created` | AS tạo family/grant | family_ref, client, issuer, session/device ref, policy version |
| `refresh.rotated` | RTn → RTn+1 | family_ref, old/new token_ref, generation, timestamp |
| `refresh.reuse_detected` | RT đã USED bị trình lại | family_ref, token_ref, client, reason enum, correlation ID |
| `refresh.family.revoked` | Family chuyển REVOKED | scope, reason, actor category, effective time |
| `refresh.rejected` | Lỗi client/binding/expiry | reason category, issuer/client; không xuất raw token |
| `access.tokens.revoked` | AS invalidate ATs liên quan | grant/family references, propagation status |
| `resource.revocation_seen` | RS cập nhật cache/denylist | RS, policy version, event sequence, latency |

Ví dụ **JSON event minh họa**:

~~~json
{
  "event_type": "refresh.family.revoked",
  "occurred_at": "2026-11-23T10:06:04Z",
  "issuer": "https://auth.example.test",
  "client_id": "orders-mobile",
  "family_ref": "family-pseudo-7",
  "reason": "REFRESH_REUSE_DETECTED",
  "token_generation": 1,
  "affected_active_refresh_tokens": 1,
  "access_token_policy": "REVOKE_ASSOCIATED_IF_SUPPORTED",
  "raw_token_logged": false
}
~~~

**Không log** raw refresh token, access token, client secret, DPoP private key/proof nhạy cảm, full token endpoint body, Authorization header hoặc user PII không cần. `family_ref` nên là ID nội bộ có access controls; nếu đưa ra analytics, dùng pseudonymization thích hợp.

**`raw_token_logged:false` không tự chứng minh hệ thống an toàn.** Cần kiểm tra reverse proxy, CDN, APM, tracing, exception, mobile diagnostics, crash reporting và support tooling.

### Metric hữu ích

- Rotation success/failed rate theo client version, platform và AS region.
- Reuse detection rate, phân biệt khả năng SDK duplicate/network timeout.
- Family revoke count theo reason và scope; tỷ lệ user phải login lại.
- `invalid_grant` sau deploy; tăng đột ngột có thể là bug concurrency, không chỉ tấn công.
- Access-token revocation propagation p95/p99 và SLA vi phạm.
- Failed AS client auth, sender proof mismatch, unexplained family branching.
- Multi-region lag và audit/event delivery lag.

Đừng tự động gán user làm attacker chỉ vì có reuse; audit phải thể hiện **sự kiện credential bị trình lại**, không khẳng định danh tính người gây ra.

## 23. Case study: đánh cắp RT, race và hậu quả tại API

Giả sử:

- User `user-42` đăng nhập vào `orders-mobile` trên **thiết bị A**.
- AS `https://auth.example.test` phát RT0 thuộc **family FA** và access token AT0 audience Orders API.
- AS áp dụng refresh rotation; access token JWT có TTL **10 phút** và được Orders API verify offline **nếu không có denylist**.

### Dòng thời gian

| UTC | Sự kiện | Family FA / token | Hệ quả |
|---|---|---|---|
| **10:00:00** | AS cấp AT0 + RT0 | FA ACTIVE; tip=RT0 | Client có thể gọi API |
| **10:03:00** | Attacker lấy bản sao RT0 | FA chưa biết bị lộ | Chưa thể xác định qua server state |
| **10:04:00** | App hợp lệ refresh RT0 | RT0 USED; tip=RT1; AT1 phát | Bình thường |
| **10:04:02** | Attacker gửi lại RT0 | Phát hiện RT0 USED | Replay signal |
| **10:04:03** | AS revoke FA | FA REVOKED; RT1 vô hiệu | Không cấp AT/RT mới từ FA |
| **10:04:04** | App thử refresh RT1 | `invalid_grant` | Cần login/authorization mới |
| **10:04:05** | AT1 gửi tới Orders API offline | AT1 có thể vẫn còn hạn | **Có thể được chấp nhận nếu RS không tra revoke** |
| **10:04:20** | RS nhận event denylist (nếu thiết kế có) | AT1 bị chặn tại RS | Từ chối từ mốc propagation |
| **10:14:00** | AT1 `exp` đến hạn (ví dụ, TTL 10 phút từ lúc cấp 10:04) | AT1 hết hạn | RS bắt buộc từ chối |

Các số thời gian là **giả định minh họa**. Nếu không có event/denylist/introspection, AT1 có thể được RS chấp nhận **đến `exp`**, dù FA đã revoked từ 10:04:03.

### Nếu attacker thắng cuộc đua

Attacker dùng RT0 **trước** app hợp lệ và được cấp RT1. App sau đó gửi RT0 và kích hoạt reuse detection. AS **không biết ai đang giữ RT1 là bên hợp lệ**; family revoke là biện pháp cắt đường refresh của cả hai, không phải công cụ xác định danh tính attacker.

### Nếu chỉ có hai request do client hợp lệ

Hai worker cùng refresh bằng RT0 có thể sinh cùng loại sự kiện reuse. AS vẫn cần bảo vệ single-use; đội vận hành cần điều tra concurrency và sửa SDK single-flight. Không thể “sửa” bằng cách cho cả hai refresh cùng RT0 đều thành công.

## 24. Khôi phục người dùng sau family revocation

Family revoke bảo vệ hệ thống nhưng thường dẫn đến **user cần đăng nhập lại**. UX nên trung thực và tránh tiết lộ thông tin không cần thiết.

### Phía client

- Khi AS trả `invalid_grant` cho refresh, **không retry cùng refresh token vô hạn**.
- Dọn credential/session trong đúng phạm vi account/device/family đang bị revoke.
- Bắt đầu Authorization Code + PKCE hoặc device authorization flow **mới** tùy client.
- Tạo **state/verifier mới**, không tái sử dụng authorization code hoặc PKCE verifier cũ.
- Không lấy access token/refresh token từ session của user khác để “tự chữa”.
- Nếu có session UI khác, không tự logout mọi account chỉ vì một family fail.

### Phía AS và vận hành

- Tùy risk, gửi cảnh báo “Phiên đăng nhập trên thiết bị X cần xác thực lại” chứ không nhất thiết phán đoán user bị hack.
- Khi có dấu hiệu compromise, yêu cầu step-up MFA hoặc đánh giá thiết bị.
- Cung cấp lịch sử và khả năng **remove linked devices**/revoke all sessions với kiểm tra quyền phù hợp.
- Hỗ trợ phân biệt logout tự nguyện với reuse phát hiện do concurrent requests để xử lý hỗ trợ kỹ thuật.
- Nếu token có dấu hiệu bị lộ thật, cân nhắc revoke grant/AT liên quan và điều tra logs/bindings.

**Không coi family revocation là thao tác logout UI thuần túy.** Chỉ xóa RT khỏi app mà không làm AS chặn RT bị đánh cắp **không bảo vệ được** phiên nếu attacker đã có bản sao.

## 25. Ma trận kiểm thử token family revocation

| Test | Kịch bản | Kết quả mong đợi |
|---|---|---|
| **T1 — Initial family** | Cấp refresh token RT0 | Tạo family/grant reference riêng, tip=RT0 |
| **T2 — Normal rotate** | Refresh RT0 hợp lệ | RT0 USED, RT1 ACTIVE, tip=RT1; một lần thành công |
| **T3 — Second rotate** | Refresh RT1 hợp lệ | RT1 USED, RT2 ACTIVE; lineage đúng |
| **T4 — Replay old RT** | Dùng lại RT0 sau RT1 | Deny; revoke active descendant/family theo replay policy |
| **T5 — Replay generation N-2** | Dùng lại token cũ nhiều generation | Phát hiện lineage và chặn family |
| **T6 — Unknown token** | Gửi chuỗi random | `invalid_grant`; không revoke family không nhận dạng được |
| **T7 — Wrong client** | Client B gửi RT family A | Deny, không tiết lộ family A; event policy phù hợp |
| **T8 — Wrong sender proof** | DPoP/mTLS binding sai | Deny; không tự coi possession hợp lệ |
| **T9 — Grant revoked** | Family RT active nhưng grant đã revoke | Không cấp AT/RT mới |
| **T10 — Family expired** | Absolute deadline đã qua | Deny |
| **T11 — Inactivity expired** | Không refresh đúng inactivity policy | Deny |
| **T12 — Token expired** | RT quá hạn riêng | Deny |
| **T13 — Parallel same-node** | Hai refresh RT0 đồng thời một AS node | Tối đa một request rotate thành công |
| **T14 — Parallel multi-node** | Hai refresh RT0 ở hai AS nodes | Không có hai active tips |
| **T15 — Multi-region lag** | Region B đọc trạng thái stale | Không phát RT từ family revoked/RT USED |
| **T16 — DB rollback** | Issuance transaction fail giữa chừng | Không trả token được commit sai; invariants giữ |
| **T17 — Lost token response** | AS commit RT1 nhưng client không nhận | Không cho RT0 đổi thêm lần nữa; UX phục hồi an toàn |
| **T18 — Client single-flight** | 20 API calls cùng hết AT | Một refresh operation cho session |
| **T19 — Client multi-tab** | Hai browser tabs dùng một session | Không refresh lặp thiếu phối hợp |
| **T20 — Client process restart** | App crash sau RT rotate | Không khôi phục RT USED để refresh vô hạn |
| **T21 — Logout this device** | User logout thiết bị A | Chỉ family A/grant liên quan bị revoke |
| **T22 — Logout all devices** | User xác thực lệnh revoke all | Tất cả families trong scope bị revoke |
| **T23 — Revoke app consent** | User gỡ quyền app | Grants/families thuộc app bị dừng |
| **T24 — Cross-device isolation** | Family A bị reuse, B hợp lệ | B không bị ảnh hưởng nếu policy chỉ revoke A |
| **T25 — Client compromise** | AS biết client key bị lộ | Incident scope rộng hơn family đơn, không bỏ sót |
| **T26 — RFC 7009 unknown** | /revoke token không tồn tại | HTTP 200 theo contract, không tiết lộ existence |
| **T27 — Revocation wrong client** | Client khác revoke token của A | Không được lạm quyền revoke A |
| **T28 — Opaque AT** | Family revoke + AS mark AT inactive | RFC 7662 trả `active:false` theo policy |
| **T29 — Cached introspection** | RS cache active=true trước revoke | Quan sát/trị giới hạn propagation TTL |
| **T30 — Offline JWT AT** | RS chỉ verify JWT, family revoked | Chứng minh RS có thể còn nhận đến `exp` nếu không có denylist |
| **T31 — Denylist/event** | Publish revoke event tới RS | RS chặn token sau propagation, xử lý retry/duplicate |
| **T32 — Refresh substitution** | RT được gửi như Bearer tới API | API từ chối theo token purpose |
| **T33 — ID token substitution** | ID token dùng tại API | API từ chối |
| **T34 — Scope restriction** | RT refresh xin scope rộng hơn grant | AS từ chối hoặc hạn theo grant/policy |
| **T35 — Audience restriction** | AT mới có audience ngoài grant | AS/RS không chấp nhận |
| **T36 — HMAC lookup** | Lưu token ref thay raw RT | Không có raw RT trong DB log/analytics |
| **T37 — Tombstone retention** | Dùng RT đã USED sau nhiều rotation | AS nhận diện reuse trong retention window |
| **T38 — Cache after revoke** | AS node cache family ACTIVE stale | Không rotate được vì source-of-truth check |
| **T39 — Restore backup** | Client restore RT cũ | Không cấp AT; xử lý reuse/re-auth theo policy |
| **T40 — Concurrent logout+refresh** | Logout đua với refresh | Không còn active RT sau commit logout theo ordering policy |
| **T41 — Revoked family replay** | RT cũ bị gửi lại sau khi family revoked | Deny, không tạo thêm token |
| **T42 — Audit privacy** | Canary RT trong staging qua APM/proxy | Không xuất raw RT/AT/client secret |
| **T43 — Reason logging** | Reuse do timeout vs suspected attack | Log chính xác evidence, không tự kết luận attacker |
| **T44 — Incident broader scope** | Nhiều families có cùng compromise source | Có khả năng revoke grant/user/client theo policy |
| **T45 — Recovery** | Client nhận `invalid_grant` sau family revoke | Reauthentication mới, không reuse RT/code/verifier cũ |

**Kiểm thử với AS mock/staging và credential canary giả.** Đặc biệt kiểm tra concurrency, network partitions, failover, replay và crash ở các điểm commit; không cần/không được đưa refresh token production vào HAR, CI log hay bug report.

## 26. Các hiểu lầm thường gặp

**“Mỗi lần refresh tạo RT mới là đủ.”** Chưa đủ. Nếu RT cũ vẫn sử dụng được, đó chưa phải rotation bảo vệ replay. Phải có **invalidated old token + reliable lineage/reuse detection**.

**“Token family là tính năng được RFC 6749 yêu cầu dưới đúng tên này.”** Sai. Family ID/generation là **mô hình triển khai**; chuẩn yêu cầu bảo vệ/replay semantics ở các BCP liên quan.

**“Bất kỳ `invalid_grant` nào cũng phải revoke mọi token của user.”** Sai. `invalid_grant` có nhiều nguyên nhân; scope revoke dựa vào **evidence và policy**.

**“Attacker dùng RT cũ sau client hợp lệ thì ta biết chắc attacker là request thứ hai.”** Sai. AS chỉ biết token được dùng lại. Trong trường hợp attacker dùng trước, **client hợp lệ lại là request thứ hai**.

**“Revoke family thì JWT AT hiện hữu ngừng hoạt động ngay.”** Sai nếu RS xác minh JWT offline và không tra revocation. Access token đã cấp có vòng đời riêng.

**“Làm family revoke bằng cách xóa RT khỏi localStorage là đủ.”** Sai. AS vẫn có thể chấp nhận RT bị sao chép. Cần server-side state/revoke.

**“Cho retry RT cũ trong 30 giây luôn an toàn.”** Sai. Khoảng cho phép lặp có thể tạo replay window; mọi extension retry cần threat model, sender binding và bảo đảm không double issue.

**“Mọi thiết bị của cùng user phải chung một family.”** Sai. Thường nên tách theo session/grant/device để logout/revoke có phạm vi thích hợp.

**“Một sender-constrained RT không cần bị revoke khi khóa bị lộ.”** Sai. DPoP/mTLS giúp chống **copy token không có key**, nhưng nếu attacker có cả key/proof context vẫn có rủi ro. AS có thể cần revoke grant/family.

**“Có `token_type=Bearer` thì RS nhận RT như AT được.”** Sai. API phải có token-purpose/audience/scope contract, không chỉ xem bearer presentation.

## 27. Checklist triển khai token family revocation

1. **Xác định boundary của family** theo grant, client, issuer, tenant và device/session phù hợp.
2. **Áp dụng replay protection cho refresh token public client** theo RFC 9700: rotation hoặc sender constraint; cân nhắc kết hợp khi hợp lý.
3. **Sinh RT khó đoán bằng CSPRNG** và lưu token reference HMAC/digest phù hợp, không log raw RT.
4. **Ghi parent/generation/active tip và family state** đủ để nhận diện RT đã dùng và descendant hiện hành.
5. **Chỉ một RT active tip trong rotation model đơn tuyến**; không cho RT USED quay về ACTIVE.
6. **Thực thi rotation nguyên tử**: xác thực client/proof, khóa family, consume RT, tạo successor, cập nhật tip, commit.
7. **Detect reuse** của RT đã USED và **revoke active RT/family** theo RFC 9700 và chính sách.
8. **Không revoke family tùy tiện khi presented token UNKNOWN** hoặc một request lỗi chưa đủ bằng chứng.
9. **Ngăn client duplicate refresh** bằng single-flight lock/queue tại session; phối hợp nhiều tab/process.
10. **Xử lý mất token response** bằng flow phục hồi được thiết kế, không retry RT cũ vô hạn.
11. **Tách logout device, logout all, revoke app consent và incident response** thành các phạm vi khác nhau.
12. **Áp dụng RFC 7009 revocation endpoint** cho yêu cầu của client, không tự tạo tham số family chuẩn không tồn tại.
13. **Xác định tác động lên access token**: AS revoke gì, RS xác minh opaque/introspection hay JWT offline, cache/denylist/event như thế nào.
14. **Đo propagation SLA** cho revocation ở các RS; không hứa instant revoke nếu cache/JWT offline còn sống.
15. **Bảo vệ grant/AS state trên multi-region**: consistency mạnh, atomic claim, recovery và tombstone retention.
16. **Không dùng refresh/ID/code/device token tại Resource Server**; kiểm tra audience/scope/purpose/exp và object ACL.
17. **Giới hạn refresh token lifetime** theo absolute/inactivity expiry/consent và policy, không kéo dài vô hạn chỉ vì client retry.
18. **Sender-constrained token** cần xác minh proof thật ở AS/RS, không chỉ kiểm tra presence của header.
19. **Audit an toàn**: family_ref pseudonym, reason, client/device, evidence và incident ID, không lộ raw token/secret.
20. **Kiểm thử race, replay, outage, expired token, cross-client và cross-device isolation**, không chỉ happy path.
21. **Khi revoke do reuse**, chuẩn bị UX reauthentication rõ và cảnh báo bảo mật có căn cứ.
22. **Khi nghi lộ rộng**, điều tra client credentials/signing keys và cân nhắc revoke grant/AT/sessions vượt phạm vi một family.

**Kết luận:** **token family revocation** là cách AS chặn **toàn bộ chuỗi refresh token kế thừa** khi phát hiện reuse, logout hoặc rủi ro bảo mật. Muốn cơ chế này hữu hiệu, phải xác định đúng **family boundary**, **rotate nguyên tử**, giữ **dấu vết used-token** để phát hiện replay, và quản lý **concurrency/network retry** mà không làm yếu single-use. Đồng thời, phải chủ động thiết kế **cách Resource Server nhìn thấy revocation của access token đã cấp**, nhất là JWT được xác minh offline. Chỉ khi các lớp này phối hợp, việc “thu hồi family” mới thực sự hạn chế credential bị đánh cắp và không gây logout ngoài ý muốn trên quy mô lớn.

### Tài liệu chuẩn và tham khảo

- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): refresh token replay detection, rotation, sender-constraining và bảo vệ grant.
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): Refresh Token grant, `invalid_grant`, client authentication và token issuance.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): endpoint thu hồi token, tác động grant và token liên quan.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): kiểm tra `active` và RS visibility sau revoke.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): Bearer token, transport và xử lý `invalid_token`.
- [RFC 9449 — OAuth 2.0 DPoP](https://www.rfc-editor.org/rfc/rfc9449): sender-constrained token và proof key.
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705): mTLS/certificate-bound tokens.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): JWT access token type/issuer/audience và RS validation.
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707): resource/audience targeting.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): OIDC ID token và authentication; phân biệt với API access/refresh token.
- [OWASP OAuth 2.0 Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html): bảo vệ OAuth client, token và security controls.
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): session lifecycle, logout và bảo vệ credential.

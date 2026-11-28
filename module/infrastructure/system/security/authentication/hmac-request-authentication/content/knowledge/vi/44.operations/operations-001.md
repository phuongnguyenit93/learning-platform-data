# HMAC runbook — vận hành xác thực HTTP request bằng HMAC

## 1. Mục đích và phạm vi

**HMAC runbook** thuộc chương **Operations** của module `SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION`. Tài liệu dành cho người vận hành API, chủ hệ thống client và đội bảo mật khi onboarding, triển khai, giám sát, xoay vòng khóa, khắc phục lỗi hoặc ứng phó sự cố của cơ chế **HMAC request authentication**.

Client tạo chữ ký bằng shared secret trên **canonical request** theo hợp đồng đã thống nhất: HTTP method, URI/path/query, một số header đã chọn, timestamp, nonce và digest của body. Server dùng `keyId` để tìm credential, tính lại HMAC và so sánh chữ ký. Xác thực thành công chỉ cho biết request được ký bởi bên có thể dùng secret tương ứng và dữ liệu đã ký không bị thay đổi.

Một request chỉ nên được xử lý nghiệp vụ nếu mọi lớp cần thiết đều đạt:

1. HTTP request được parse rõ ràng, canonicalization đúng phiên bản giao thức.
2. Credential đang hoạt động, algorithm nằm trong allowlist và khớp metadata của key.
3. Timestamp còn hiệu lực, chữ ký HMAC hợp lệ và nonce được đăng ký một lần.
4. Principal đã xác thực được **phân quyền** đối với resource và tenant.
5. Quy tắc nghiệp vụ, idempotency, hạn mức và các chốt kiểm soát giao dịch vẫn có hiệu lực.

**Không xem HMAC như cơ chế phân quyền; không xem timestamp/nonce như cách bảo vệ secret đã bị lộ.** Khi attacker chiếm quyền client, signer hoặc shared secret, họ có thể tạo request mới với timestamp và nonce mới cùng chữ ký hoàn toàn hợp lệ. Runbook vì thế phải bao gồm giám sát key lifecycle và thu hồi credential.

> **Phạm vi minh họa:** Header, cấu hình, ngưỡng và test vector dưới đây thuộc một hợp đồng giả định `hmac-v1`. Khi triển khai thật, phải dùng đúng hợp đồng đã được phê duyệt. Các thao tác với key và quyền không được thực hiện chỉ dựa trên lệnh mẫu.

### 1.1. Vai trò

| Vai trò | Trách nhiệm |
|---|---|
| On-call/SRE | Nhận cảnh báo, phân loại lỗi, kiểm tra rollout, theo dõi phụ thuộc và khôi phục dịch vụ |
| API security/platform | Quản lý verifier, canonicalization, algorithm allowlist, credential và nonce store |
| Client/đối tác | Bảo vệ secret, đồng bộ clock, triển khai signer và tham gia key rotation |
| Incident response | Khoanh vùng, cô lập key/client, lưu chứng cứ và điều phối hậu kiểm |
| Chủ nghiệp vụ | Quyết định quyền API, scope, hạn mức và đối soát side effect |

Mọi thay đổi policy hoặc key cần **change/incident ID**, owner, mốc UTC, bằng chứng kiểm thử và phương án quay lui. Không paste shared secret, full HMAC signature hoặc body nhạy cảm vào log, chat, ticket và ảnh chụp màn hình.

## 2. Luồng xác thực cần nắm

~~~mermaid
sequenceDiagram
    participant C as Client
    participant G as Gateway
    participant V as HMAC verifier
    participant K as Credential store
    participant N as Shared nonce store
    participant A as Authorization
    participant B as Business API

    C->>C: Canonical request + HMAC
    C->>G: HTTP request
    G->>V: Forward theo contract
    V->>K: Tra keyId, client, status, algorithm
    K-->>V: Credential policy
    V->>V: Timestamp + MAC check
    V->>N: Claim nonce atomic với TTL
    N-->>V: New hoặc replay
    alt Authentication fail
        V-->>C: Reject
    else Authentication pass
        V->>A: Authenticated principal
        A->>B: Chỉ khi đủ quyền
        B-->>C: Kết quả nghiệp vụ
    end
~~~

**Điểm nhạy cảm:** Gateway, HTTP adapter và controller không được diễn giải URI/query/header/body khác với dữ liệu đã ký. Nếu gateway rewrite, hợp đồng phải nêu rõ vị trí xác minh và cách canonical hóa. Chạy smoke test qua tuyến thực tế, không chỉ gọi trực tiếp verifier.

### 2.1. Hợp đồng mẫu `hmac-v1`

| Thành phần | Quy tắc minh họa |
|---|---|
| Version | `hmac-v1` và phải nằm trong chuỗi ký |
| Algorithm | `HMAC-SHA256`, full tag 32 byte, biểu diễn 64 lowercase hex |
| Secret | Ít nhất 32 byte ngẫu nhiên từ CSPRNG hoặc managed signer |
| Key identifier | `X-HMAC-Key-Id`; tra credential do server quản lý |
| Timestamp | `X-HMAC-Timestamp`; Unix epoch theo **giây UTC** |
| Freshness | `now - 300 s <= ts <= now + 60 s`, bao gồm hai điểm biên |
| Nonce | `X-HMAC-Nonce`; đủ ngẫu nhiên và duy nhất trong scope credential |
| Replay store | Atomic claim, dùng chung giữa mọi instance, TTL ví dụ 600 giây |
| URI | Method uppercase, path/query theo canonical contract version |
| Body | SHA-256 của **đúng byte body đã ký** |
| Signature | `X-HMAC-Signature` là output, không nằm trong input ký |

Ví dụ request:

~~~http
POST /v1/orders?currency=VND HTTP/1.1
Host: api.example.test
Content-Type: application/json
X-HMAC-Version: hmac-v1
X-HMAC-Key-Id: client-a-k2
X-HMAC-Algorithm: HMAC-SHA256
X-HMAC-Timestamp: <epoch-seconds-utc>
X-HMAC-Nonce: <unique-random-nonce>
X-HMAC-Signature: <64-lowercase-hex-characters>

{"orderId":"o-123","amount":150000}
~~~

Ví dụ canonical request UTF-8, các dòng nối bằng byte LF, không thêm newline cuối:

~~~text
REQUEST-HMAC
hmac-v1
HMAC-SHA256
client-a-k2
POST
/v1/orders?currency=VND
<epoch-seconds-utc>
<unique-random-nonce>
<lowercase-hex-sha256-of-exact-body-bytes>
~~~

Tên version, algorithm và keyId phải được ràng buộc với chữ ký hoặc một cơ chế xác thực tương đương. **Không tự đổi thứ tự trường đã ký** khi nâng cấp. Nếu header như `Content-Type` ảnh hưởng ngữ nghĩa và cần được bảo vệ, giao thức phải thêm chúng vào danh sách signed headers theo quy tắc chuẩn hóa đã định. Mẫu trên tập trung vào các trường cốt lõi, không có nghĩa mọi header mặc nhiên được bảo vệ.

### 2.2. Algorithm allowlist và credential policy

Algorithm ID từ header là input không đáng tin. Verifier ánh xạ thuật toán từ **allowlist server-side** và kiểm tra nó khớp policy của credential được tra bằng keyId; không gọi crypto provider bằng tên thuật toán trực tiếp do client gửi. Trong migration, mỗi keyId có secret và algorithm được cấp rõ ràng. Không thử mọi key hoặc thuật toán đến khi thấy tag khớp.

## 3. Preflight trước onboard hoặc rollout

| Hạng mục | Điều kiện đạt | Khi không đạt |
|---|---|---|
| Canonical contract | Golden test vector giữa client và verifier khớp | Dừng rollout, xác định khác biệt byte |
| Credential | Key active, đúng principal/tenant/scope | Không mở traffic |
| Algorithm | Allowlist đúng, không fallback ngầm | Sửa policy/signer |
| Clock | UTC/NTP đồng bộ, cùng đơn vị epoch seconds | Sửa đồng hồ, không nới window tùy tiện |
| Nonce | Shared store, atomic claim, TTL phù hợp | Không cho endpoint nhạy cảm đi tiếp |
| Gateway | Path, query, signed header và body được giữ/chuẩn hóa đúng hợp đồng | Test differential qua proxy |
| Dependencies | Secret lookup/nonce store timeout xử lý fail closed | Khôi phục phụ thuộc |
| Metrics/audit | Có auth result, reason nội bộ, request ID, policy version | Bổ sung observability trước canary |
| Authorization | Principal và resource permission kiểm tra riêng | Không coi HMAC pass là được cấp quyền |

### 3.1. Tính TTL nonce

Với `maxAge=300s` và `futureSkew=60s`, một timestamp có thể nằm trong cửa sổ chấp nhận kéo dài 360 giây. TTL phải đủ lớn để không có request dùng lại nonce được nhận khi timestamp còn hợp lệ, tính thêm sai lệch đồng hồ và dự phòng phân tán. **TTL 600 giây từ lúc claim** là một cấu hình minh họa cần được xác nhận lại cho hệ thống thực.

Ý nghĩa của một thao tác atomic Redis:

~~~text
SET hmac:nonce:<scoped-client-or-key-id>:<nonce-digest> 1 NX EX 600
~~~

Nếu tạo mới thành công, nonce chưa từng được claim trong phạm vi đang giữ. Nếu key đã tồn tại, reject replay. Nếu store timeout hoặc không xác định kết quả, **fail closed**, không chuyển sang local in-memory cache của mỗi pod. Không dùng hai thao tác `GET` rồi `SET` vì chúng có race condition giữa verifier.

Nonce store chỉ giữ trạng thái chống replay trong một khoảng thời gian; không nên dùng nó làm hệ thống audit dài hạn. Tránh dùng raw nonce chứa dữ liệu không kiểm soát trong tên key; scope phải nhất quán giữa các verifier.

### 3.2. Các kiểm tra phân tán

Xác nhận từng gateway/instance đang dùng đúng protocol version, chính sách credential và cùng miền uniqueness nonce. Kiểm tra đồng hồ từng vùng, latency của secret manager và nonce store, error handling khi dependency mất kết nối. **Control plane đã cập nhật key status không có nghĩa mọi data plane đã nhìn thấy thay đổi.**


## 4. Runbook onboarding client mới

**Điều kiện đầu vào:** client có danh tính đã được kiểm tra, owner và scope/tenant được phê duyệt. Không tạo key cho client không rõ người quản lý hoặc dùng chung secret giữa production và test.

| Bước | Thao tác | Tiêu chí hoàn tất |
|---|---|---|
| 1 | Xác định clientId, principal, tenant, route, scope và hạn mức theo least privilege | Approval và owner rõ |
| 2 | Sinh shared secret mới bằng CSPRNG/managed signer, cấp keyId duy nhất | Credential `PROVISIONED`, có audit event |
| 3 | Lưu secret trong secret manager, gắn policy algorithm, status | ACL hạn chế, không log secret |
| 4 | Cấp secret cho client qua kênh bảo mật được duyệt | Client xác nhận nhận key an toàn |
| 5 | Chạy golden vector từ signer và verifier độc lập | Canonical bytes và HMAC khớp |
| 6 | Chạy staging test qua gateway, timestamp, nonce, key policy | Positive và negative cases đúng |
| 7 | Bật credential `ACTIVE`, canary lưu lượng nhỏ | Latency, reject rate ổn định |
| 8 | Test authorization với resource hợp lệ và cross-tenant | Không vượt được quyền |
| 9 | Lưu owner, kênh liên hệ incident, thời điểm rotation | Bàn giao đầy đủ |

KeyId là mã tra credential, **không tự xác thực danh tính**. Principal để phân quyền phải đến từ credential đã được xác minh, không được tin vào `clientId` hay role do người gửi tự đặt trong header.

### 4.1. Canary cần có gì?

Dùng request mới, timestamp và nonce mới, một fixture HMAC đúng và những request âm tính đã kiểm soát từng nguyên nhân. Request bị sửa timestamp sau khi ký không kiểm chứng freshness vì chữ ký sẽ sai; request key revoked nhưng signature sai cũng không chứng minh việc thu hồi đã có hiệu lực.

Với route tạo side effect, dùng endpoint probe hoặc fixture nghiệp vụ được ủy quyền. Trong staging, nên dùng `Clock.fixed(...)` hoặc đồng hồ test điều khiển được để thử điểm biên, tránh dựa vào `sleep`.

## 5. Runbook thay đổi verifier, protocol và gateway

Phân loại thay đổi để dự đoán rủi ro:

- **Policy:** algorithm allowlist, credential status, quyền client, maxAge/futureSkew và nonce TTL.
- **Giao thức:** thứ tự trường, signed headers, canonical URI/query, body digest, encoding và version.
- **Hạ tầng:** gateway, reverse proxy, HTTP server, secret manager, nonce store, Redis failover.

Nếu đổi giao thức, tạo version riêng (ví dụ `hmac-v2`). Triển khai verifier hiểu version mới trước khi bắt client đổi signer, nhưng phải giới hạn version được phép **theo key/client policy**. Không thử liên tiếp nhiều kiểu canonicalization hoặc nhiều secret đến khi chữ ký khớp.

### 5.1. Trình tự rollout

1. Ghi change ID, mục tiêu, khách hàng ảnh hưởng, config trước/sau, owner, rủi ro và tiêu chí rollback.
2. Cập nhật golden vectors độc lập, gồm URI/query/header/body có khả năng bị biến đổi.
3. Chạy smoke suite trong staging với verifier trực tiếp và qua staging gateway.
4. Triển khai canary một nhóm instance, quan sát reject rate theo reason, latency, nonce store và authorization.
5. Chạy negative tests cho algorithm/key mismatch, timestamp expired, replay, signature sai, resource không được phép.
6. Mở dần traffic khi tiêu chí đạt; ghi version thật của từng gateway/verifier/credential cache.
7. Dừng rollout nếu signature error tăng, nonce không còn atomic, hoặc handler hiểu query khác verifier.
8. Sau deploy, lưu bằng chứng probe và tiếp tục theo dõi tăng cường.

**Rollback có giới hạn bảo mật:** Có thể trở về build gateway trước đó nếu build đó vẫn tuân thủ contract và policy hiện hành. Không tự động kích hoạt lại key đã `REVOKED`, thuật toán bị cấm, hoặc tắt nonce để giảm lỗi 401.

### 5.2. Kiểm thử proxy/gateway

| Input hoặc thao tác | Rủi ro | Test |
|---|---|---|
| `a=1&b=2` so với `b=2&a=1` | Sort query khác nhau | So canonical bytes theo contract |
| `%2F` so với `/` hoặc `%252F` | Decode một/hai lần | Test encoding path/query |
| `q=a+b` so với `q=a%20b` | `+` thành space | Test raw query và handler binding |
| Header trùng hoặc bị gộp | Verifier chọn khác handler | Reject input mơ hồ |
| `Host`, forwarded path, scheme rewrite | Signed field đổi | Chốt input ký tại trust boundary |
| Body JSON bị serialize lại | Digest body bytes khác | Hash đúng bytes được ký |
| Content compression/encoding | Các tầng hash ở byte khác nhau | Quy định tầng ký/verify |

Chẩn đoán bằng request ID và dữ liệu test không nhạy cảm; không log body production hay shared secret chỉ để so sánh canonical strings.


## 6. Monitoring và cảnh báo

Theo dõi theo route, môi trường, vùng và deployment version. Ngưỡng cụ thể nên xác định từ baseline và mức độ nhạy cảm của endpoint, không mặc định một tỷ lệ lỗi chung cho mọi API.

| Metric / sự kiện | Mục đích |
|---|---|
| `hmac_auth_requests_total{result,reason}` | Tỷ lệ pass/reject, phân loại lỗi nội bộ |
| `hmac_signature_invalid_total` | Canonical mismatch, secret sai, request bị sửa |
| `hmac_timestamp_rejected_total{kind}` | Timestamp expired/future, clock drift |
| `hmac_nonce_replay_total` | Replay, retry lỗi, duplicate delivery |
| `hmac_nonce_store_errors_total` | Dependency failure làm mất anti-replay |
| `hmac_nonce_store_duration_seconds` | Latency p95/p99, timeout |
| `hmac_inactive_credential_attempts_total` | Lưu lượng còn dùng key suspend/revoke |
| `hmac_credential_policy_version` | Phát hiện fleet dùng policy cũ |
| `hmac_verify_duration_seconds` | Chi phí HMAC, credential lookup |
| `hmac_requests_by_key_generation` | Tiến độ rotation |
| `authz_denied_total{route,reason}` | Phân biệt authN pass với thiếu quyền |
| Audit request ID → transaction ID | Đối soát side effect trong incident |

**Ưu tiên cao:** nonce store không sẵn sàng trên route giao dịch nhạy cảm; key đã revoke vẫn được chấp nhận; bằng chứng shared secret lộ; authorization bypass. **Ưu tiên trung bình:** lỗi chữ ký tăng sau deploy, clock drift kéo dài, client chưa chuyển key theo lịch.

Không đưa raw `keyId`, nonce, signature, secret hoặc giá trị cardinality lớn vào metric labels. Khi cần truy client cụ thể, dùng audit có quyền truy cập và retention phù hợp, gắn request ID/UTC.

### 6.1. Ví dụ health record nội bộ

~~~json
{
  "service": "hmac-verifier",
  "protocol_version": "hmac-v1",
  "algorithm_policy_version": "policy-24",
  "credential_snapshot_version": "rev-118",
  "nonce_store": "reachable",
  "clock_skew_health": "within_policy",
  "gateway_contract": "edge-9",
  "ready_for_sensitive_routes": true
}
~~~

`ready_for_sensitive_routes` phải phản ánh tình trạng thực của dependency và policy. Redis ping thành công **không chứng minh** atomic nonce claim; một node có snapshot mới **không chứng minh** toàn fleet đã áp dụng revocation.

## 7. Triage khi authentication error tăng

Bắt đầu bằng **phạm vi**: một client hay mọi client, một route hay nhiều route, một region hay nhiều region, sau deploy hay key rotation nào? Dùng request ID, timestamp UTC và mã lỗi nội bộ; một HTTP 401 đơn lẻ không đủ chẩn đoán.

| Reason nội bộ | Khả năng | Cách kiểm tra | Hướng xử lý |
|---|---|---|---|
| `header_invalid` | Header thiếu, trùng, bị proxy gộp | Raw headers ở edge/adapter | Reject nhập nhằng, sửa client/proxy |
| `version_unsupported` | Client chưa migrate | Credential policy và signer version | Migration có version, không fallback |
| `algorithm_disallowed` | Algorithm lạ hoặc sai per-key | Allowlist + metadata keyId | Sửa signer/policy hợp lệ |
| `credential_inactive` | KeyId sai, revoked hoặc client blocked | Store, policy trên từng verifier | Không mở key trong incident |
| `timestamp_expired` | Clock chậm, retry muộn | Server now, epoch seconds và NTP | Sửa đồng hồ/đơn vị |
| `timestamp_future` | Clock nhanh, client dùng millis | ts-now, parser và NTP | Sửa timestamp |
| `signature_invalid` | Canonical mismatch, sai secret, body thay đổi | Golden vector và gateway diff | Sửa contract/signer/proxy |
| `nonce_replay` | Duplicate retry hoặc replay | Scope, TTL, atomic semantics | Chẩn đoán retry/attack |
| `nonce_store_unavailable` | Store hoặc network timeout | Latency/error và failover | Fail closed, khôi phục phụ thuộc |
| `authorization_denied` | Principal không đủ quyền | Tenant, scope, resource owner | Xử lý ở authZ, không thay HMAC |

### 7.1. Chẩn đoán signature mismatch qua proxy

1. Chọn một request mẫu có payload test, lưu request ID ở client, gateway và verifier.
2. So sánh method, **raw path/query**, percent-encoding, dấu cộng, các signed headers và body bytes.
3. Gửi cùng fixture vào staging verifier trực tiếp và qua staging gateway.
4. So sánh digest của canonical bytes và từng trường với **dữ liệu không nhạy cảm**.
5. Sửa đúng contract hoặc cấu hình gateway, test lại HMAC positive/negative và authorization.
6. Không chữa lỗi bằng cách thử nhiều dạng canonical đến khi tag khớp.

Những bẫy phổ biến: `%2F` thành `/`, `+` thành space, query đảo thứ tự, duplicate parameters bị chọn first/last, `Host` rewrite, JSON reserialization hoặc body compression. Cần bảo đảm verifier và business handler **không diễn giải cùng request thành hai dữ liệu nghiệp vụ khác nhau**.

### 7.2. Kiểm tra timestamp và replay

Theo cửa sổ ví dụ `now - 300s <= ts <= now + 60s`:

| Timestamp thử | Freshness kỳ vọng |
|---|---|
| `now - 301s` | Reject expired |
| `now - 300s` | Accept ở biên dưới |
| `now` | Accept |
| `now + 60s` | Accept ở biên trên |
| `now + 61s` | Reject future |

Muốn test freshness, phải tạo **HMAC đúng cho timestamp được thử**. Nếu sửa timestamp trong header của request đã ký và giữ signature cũ, test chỉ chứng minh signature mismatch.

Để kiểm tra anti-replay phân tán, gửi hai request HMAC đúng cùng `keyId+nonce` đến hai verifier **đồng thời**. Kỳ vọng tối đa một request được chấp nhận. Nếu retry nghiệp vụ cần bảo đảm không tạo giao dịch hai lần, dùng cơ chế idempotency riêng; không bỏ nonce protection để request cũ được tái sử dụng.

### 7.3. Nonce store outage

- Kiểm tra DNS, network, ACL, pool connections, capacity, replication/failover, timeout, tỷ lệ lỗi theo region.
- Giữ **fail closed** ở endpoint nhạy cảm; không dùng local cache riêng của mỗi pod hay bỏ claim nonce.
- Chỉ chuyển sang cụm dự phòng khi mọi verifier vẫn dùng **một miền uniqueness**; hai cụm độc lập không tương đương.
- Sau recovery, chạy probe đồng thời cùng nonce; xác nhận chỉ một request đi tiếp.
- Đối soát các request đã nhận và log phụ thuộc trong thời gian lỗi, lưu bằng chứng phục vụ điều tra.


## 8. Planned key rotation

Rotation theo kế hoạch nhằm thay secret mà vẫn hỗ trợ client di chuyển có kiểm soát. Trong trường hợp **không có nghi ngờ compromise**, hệ thống có thể cho key cũ và key mới cùng hoạt động trong cửa sổ overlap ngắn, có thời hạn và được phê duyệt.

~~~mermaid
flowchart LR
    A["Old key ACTIVE"] --> B["Cấp keyId và secret mới"]
    B --> C["Client triển khai signer mới"]
    C --> D["Canary + kiểm tra metric"]
    D --> E["Chuyển toàn bộ traffic"]
    E --> F["Revoke key cũ"]
    F --> G["Probe key cũ bị từ chối"]
~~~

### 8.1. Thao tác

1. Xác định owner, client, route, signer instance, algorithm, protocol version và lưu lượng đang dùng key cũ.
2. Sinh **secret khác hẳn** bằng CSPRNG hoặc managed signer, cấp `keyId` mới, ràng buộc principal/scope/algorithm rõ ràng.
3. Phân phối qua kênh secret manager đã được phê duyệt; không đưa secret vào log, terminal history, CI artifact hoặc ticket.
4. Mở overlap **có thời hạn** khi được phê duyệt. Mỗi keyId chỉ trỏ tới credential/secret/algorithm theo metadata; không fallback sang key khác nếu HMAC sai.
5. Client canary với key mới qua gateway; xác minh HMAC, timestamp, nonce, authorization và idempotency.
6. Chuyển traffic theo nhóm client, kiểm tra `hmac_requests_by_key_generation` theo region/instance.
7. Revoke key cũ, invalidate credential cache; probe bằng **HMAC đúng tạo từ key cũ, timestamp hiện tại và nonce mới**.
8. Ghi lại thời điểm UTC, policy version, kết quả trên mọi data plane, owner và công việc dọn secret cũ.

| Smoke case | Kết quả |
|---|---|
| Key mới + signature đúng + timestamp/nonce mới | Pass authN, tiếp tục authZ |
| Key cũ trong overlap được duyệt | Pass theo policy có thời hạn |
| Key mới + signature tạo bằng secret cũ | Reject signature |
| Key mới + algorithm khác credential policy | Reject policy |
| Key cũ sau revoke + signature đúng | Reject credential |
| Key mới + nonce đã dùng | Reject replay |
| HMAC đúng nhưng principal thiếu quyền | Reject authorization |

### 8.2. Rollback rotation

Nếu key cũ **vẫn active hợp pháp** trong planned overlap, có thể tạm ngừng chuyển traffic và chỉnh lại signer theo quy trình đã duyệt. Nếu key cũ đã `REVOKED` hoặc có bằng chứng lộ secret, **không bật lại key cũ** để giải quyết lỗi tích hợp; cần khôi phục client và cấp key khác.

## 9. Emergency runbook: client hoặc shared secret bị compromise

**Trigger:** secret xuất hiện trong source control/artifact/log, máy client bị xâm nhập, signer bị dùng trái phép hoặc có hành vi bất thường từ những request HMAC hợp lệ.

HMAC không thể phân biệt client thật và attacker khi hai bên đều có khả năng ký bằng cùng secret. Timestamp/nonce vẫn hữu ích để chống replay request cũ, nhưng không ngăn attacker tạo request **mới** bằng secret đã lấy.

### 9.1. Cô lập

1. Mở incident, xác định `clientId`, `keyId`, tenant, owner, route, thời điểm UTC và mức độ tin cậy của bằng chứng.
2. Chặn toàn client/principal khi có thể nhiều credential trong cùng môi trường bị ảnh hưởng; suspend/revoke key nghi vấn.
3. Phát tán cập nhật đến mọi verifier, gateway, vùng và cache; áp dụng **fail closed** nếu một đường không thể xác minh chính sách mới.
4. Thu hồi quyền signer/secret manager/IAM token và kênh cấp bí mật nằm trong phạm vi compromise.
5. Kiểm soát queue, retry, long-running job và request đã qua authentication nhưng chưa commit. Với hành động nguy hiểm, cần incident hold/permission check tại **điểm commit** nếu thiết kế hỗ trợ.
6. Chạy probe từ các tuyến: key cũ, **chữ ký đúng**, timestamp mới, nonce mới. Nếu probe bị từ chối chỉ vì signature sai hoặc timestamp expired, **chưa chứng minh** revocation hoạt động.

### 9.2. Bảo toàn chứng cứ và điều tra tác động

| Nhóm dữ liệu | Dùng để xác minh |
|---|---|
| Credential audit | KeyId, trạng thái, thời điểm cấp/suspend/revoke, operator |
| Gateway/API logs | Request ID, route, UTC, auth result/reason |
| Secret access | IAM, KMS/signer invocation, nguồn secret có thể bị lộ |
| Transaction ledger | Giao dịch đã commit, pending, rollback, resource/tenant |
| Async queue | Các job/retry đã qua auth nhưng còn chờ xử lý |
| Deployment/host evidence | Image, process, quyền và hoạt động bất thường |
| Propagation audit | Thời điểm từng gateway/instance áp dụng policy mới |

Không lưu raw secret, full signature hoặc body nhạy cảm vào hồ sơ incident. Nonce store có TTL thường **không đủ** để tái dựng lịch sử; cần truy request ID và transaction/ledger ID.

Phải phân biệt **request đã xác thực** với **hành động nghiệp vụ đã commit**. Một request HMAC đúng chưa chắc giao dịch thành công; ngược lại request đã qua auth trước lúc revoke có thể tiếp tục commit nếu thiếu operation gate.

### 9.3. Khôi phục

1. Sửa nguyên nhân gốc, rebuild client từ môi trường đáng tin và thu hồi quyền cũ. Không cấp secret mới cho host vẫn có khả năng bị kiểm soát.
2. Sinh secret mới, keyId mới, policy ít quyền nhất; cấp qua kênh bảo mật sau khi xác minh client sạch.
3. Test positive/negative HMAC, timestamp, nonce, gateway, algorithm và authorization.
4. Mở lại traffic có canary, giám sát tăng cường, rà soát giao dịch trong giai đoạn có khả năng compromise.
5. Lập post-incident review, owner và thời hạn hành động phòng ngừa.

Với compromise đã xác nhận, **không áp dụng overlap planned rotation thông thường** cho key bị lộ: mỗi phút key cũ còn active là thời gian attacker có thể tạo chữ ký hợp lệ.

### 9.4. Tiêu chí kết thúc containment

- Mọi gateway/verifier/region thực sự từ chối key/client đã revoke; có số liệu propagation.
- Request ký đúng bằng key cũ với timestamp/nonce mới đều bị chặn do policy.
- Các side effect nhạy cảm, queue/retry và request in-flight đã được kiểm soát.
- Có danh sách giao dịch cần đối soát và chứng cứ được lưu an toàn.
- Môi trường client đã khôi phục; key mới và authorization được kiểm tra.
- Có owner, timeline UTC và action item cho hậu kiểm.

**Containment hoàn tất không có nghĩa điều tra tác động đã kết thúc.** Cần hoàn thành đối soát và các nghĩa vụ vận hành khác theo quy trình của tổ chức.


## 10. Smoke suite áp dụng cho on-call

Sau onboarding, verifier deploy, gateway deploy, nonce store failover, rotation hoặc recovery phải có một bộ kiểm thử có thể tái hiện. Nên dùng staging hoặc endpoint probe không phát sinh side effect thật; một request chuyển tiền thật không phù hợp làm health check.

| ID | Dữ liệu kiểm thử | Kết quả kỳ vọng |
|---|---|---|
| SM-01 | Key active, HMAC đúng, timestamp/nonce mới | Pass authentication |
| SM-02 | Sửa body sau ký, giữ signature | Reject signature |
| SM-03 | Sửa method/path/query đã ký | Reject signature |
| SM-04 | Timestamp `now - 301s`, **ký lại đúng** | Reject expired |
| SM-05 | Timestamp `now - 300s`, ký lại đúng | Pass tại biên dưới |
| SM-06 | Timestamp `now + 61s`, ký lại đúng | Reject future |
| SM-07 | Hai request đồng thời cùng keyId+nonce, hai pod | Tối đa một request pass |
| SM-08 | HMAC header thiếu/trùng, algorithm không allowlist | Reject |
| SM-09 | Key revoked + signature đúng + timestamp/nonce mới | Reject credential |
| SM-10 | Signature hợp lệ nhưng thiếu quyền trên resource | Deny authorization |
| SM-11 | Cùng request đi qua gateway và direct staging verifier | Cùng ngữ nghĩa theo contract |
| SM-12 | Nonce store timeout | Fail closed, không side effect |
| SM-13 | Planned overlap, chuyển key mới, revoke key cũ | Policy key lifecycle được thực thi |
| SM-14 | Gateway rewrite signed query hoặc header | Reject nếu làm thay canonical bytes |

### 10.1. Java 17: test oracle cho timestamp

Đoạn Java sau minh họa kiểm tra cửa sổ thời gian, **không thực hiện HMAC**. Trong smoke test end-to-end, cần signer test tạo chữ ký hợp lệ cho từng timestamp và request.

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

public final class HmacFreshnessProbe {
    private static final long MAX_AGE_SECONDS = 300;
    private static final long FUTURE_SKEW_SECONDS = 60;

    public static boolean allowed(Clock clock, Instant timestamp) {
        Instant now = clock.instant(); // Lấy now một lần.
        return !timestamp.isBefore(now.minusSeconds(MAX_AGE_SECONDS))
                && !timestamp.isAfter(now.plusSeconds(FUTURE_SKEW_SECONDS));
    }

    public static void main(String[] args) {
        Clock fixed = Clock.fixed(
                Instant.parse("2026-11-28T03:00:00Z"),
                ZoneOffset.UTC);
        Instant now = fixed.instant();

        assert !allowed(fixed, now.minusSeconds(301));
        assert allowed(fixed, now.minusSeconds(300));
        assert allowed(fixed, now);
        assert allowed(fixed, now.plusSeconds(60));
        assert !allowed(fixed, now.plusSeconds(61));
    }
}
~~~

Java `assert` chỉ hoạt động khi bật assertions (`-ea`). Dự án thực nên dùng JUnit 5 `assertTrue/assertFalse` và inject `Clock` vào verifier. Tránh dùng `sleep` trong test điểm biên vì thời gian CI làm kết quả không ổn định.

### 10.2. Ghi bằng chứng sau smoke test

Ví dụ một record **không chứa bí mật**:

~~~text
Change/incident: CHG-HMAC-2026-014
Environment: staging
Contract: hmac-v1 / HMAC-SHA256
Client fixture: sandbox-client
Verifier build: <build-id>
Gateway build: <build-id>
Credential policy version: <version-id>
Nonce store: <safe-cluster-alias>
Clock basis: 2026-11-28T03:00:00Z (fixed test clock)
Tests: SM-01..SM-14 with pass/fail and request IDs
Test owner: <approved-operator>
Evidence: <restricted-audit-reference>
~~~

Chỉ kết luận rollout đạt khi positive/negative paths, nonce và credential policy đúng trên mọi data plane, authorization còn hiệu lực, dashboard và alerts hoạt động. Khi một case fail, ghi rõ nguyên nhân, quyết định hold/rollback và người phê duyệt theo quy trình.

## 11. Những cách sửa vội cần tránh

| Cách xử lý | Rủi ro | Thay bằng |
|---|---|---|
| Tắt HMAC để giảm lỗi 401 | Cho phép request giả mạo | Khoanh vùng lỗi signer/gateway |
| Bỏ nonce khi Redis lỗi | Mở đường replay | Fail closed, khôi phục shared store |
| Nới timestamp window vô hạn | Kéo dài thời gian replay | Sửa clock/NTP và retry client |
| Chấp nhận mọi algorithm từ header | Downgrade/algorithm confusion | Server allowlist + per-key binding |
| Thử nhiều key đến khi HMAC khớp | Vượt policy và che giấu lỗi | Tra credential đúng keyId |
| Bật lại key lộ sau sự cố | Attacker tiếp tục ký hợp lệ | Cấp key mới cho client sạch |
| Log toàn bộ canonical request | Lộ body/PII và thông tin nhạy cảm | Request ID, lỗi nội bộ, digest an toàn |
| Chỉ kiểm tra direct verifier | Bỏ qua lỗi gateway rewrite | Test end-to-end |
| Cho request đã qua auth commit sau revoke | Không chặn side effect in-flight | Incident hold/commit gate tại route nhạy cảm |
| Coi HMAC pass là đã có quyền | Có thể lộ dữ liệu cross-tenant | Kiểm tra authorization riêng |

## 12. Checklist bàn giao ca trực

- [ ] Nắm contract version, algorithm allowlist, signed fields và rule canonicalization.
- [ ] Có dashboard/baseline cho HMAC reject, timestamp skew, nonce replay, dependency failure và latency.
- [ ] Biết cách tra keyId → client/principal/status theo quyền mà không lộ shared secret.
- [ ] Biết cách suspend/revoke và xác minh propagation trên mọi gateway/region.
- [ ] Nonce store có atomic claim, TTL đủ dài, fail closed và một miền uniqueness.
- [ ] Có smoke suite test HMAC đúng, signature sai, timestamp boundary, replay, revoked key và authorization.
- [ ] Gateway, adapter và handler sử dụng ngữ nghĩa path/query/header/body thống nhất.
- [ ] Có quy trình planned key rotation và emergency compromise, có owner và change/incident ID.
- [ ] Có cơ chế kiểm soát queue, retry/idempotency và side effect in-flight khi revoke.
- [ ] Audit có timeline UTC, request ID, transaction ID và không ghi secret hoặc full signature.

**Bài thực hành cuối:** Trong staging, giả lập ba sự cố: (1) gateway thay đổi query encoding làm tăng `signature_invalid`; (2) nonce store timeout khi hai verifier nhận request cùng nonce; (3) shared secret của một client xuất hiện trong artifact test. Với mỗi sự cố, lập timeline phát hiện → cô lập → kiểm chứng → khôi phục → hậu kiểm, nêu chỉ số và bằng chứng sẽ dùng. Cuối cùng, chứng minh rằng credential đã revoke **không còn được chấp nhận dù chữ ký HMAC đúng, timestamp mới và nonce mới**, còn request xác thực thành công nhưng thiếu quyền trên tenant khác vẫn bị authorization từ chối.

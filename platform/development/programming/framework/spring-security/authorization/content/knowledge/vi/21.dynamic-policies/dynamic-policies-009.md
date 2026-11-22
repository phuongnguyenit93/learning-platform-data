# Phiên bản chính sách, triển khai thử và phương án quay lui trong Spring Security

## 1. Vì sao sửa một rule phân quyền nguy hiểm hơn sửa một nút giao diện?

Giả sử hệ thống quản lý tài liệu đang thực thi **policy v1**: chủ sở hữu tài liệu có quyền SHARE nếu có authority chức năng `document:share`. Nhóm bảo mật muốn triển khai **policy v2**: cùng điều kiện đó, nhưng thao tác SHARE còn yêu cầu một bằng chứng xác thực mạnh (MFA/step-up) hợp lệ.

Nếu ngay lập tức thay toàn bộ v1 bằng v2, có thể xảy ra những tình huống:

- Một số user hợp lệ bị từ chối SHARE vì quy trình step-up chưa sẵn sàng.
- Service A dùng policy v2 nhưng service B còn dùng v1.
- Một policy có cú pháp đúng nhưng lấy sai thuộc tính tenant hoặc resource.
- Cache vẫn trả một quyết định ALLOW của v1 sau khi v2 đã hạn chế quyền.
- Một lỗi trong cấu hình làm mặc định cho phép khi không tìm thấy policy.
- Khi rollback về v1, thao tác SHARE có thể lại không cần MFA, vô tình **khôi phục một lỗ hổng bảo mật**.
- Chính sách đã đổi nhưng database schema, event consumer hoặc resource service chưa tương thích.

Vì thế, thay đổi chính sách không chỉ là sửa biểu thức trong `@PreAuthorize`. Cần quản lý **artifact bất biến, phê duyệt, phiên bản hoạt động, nhóm triển khai thử, quan sát quyết định thực tế, khả năng thu hồi và quy trình quay lui có rào chắn**.

Mục tiêu của bài:

1. Hiểu **version của policy**, version của dữ liệu phân quyền và version triển khai ứng dụng khác nhau ra sao.
2. Thiết kế lưu, xét duyệt và kích hoạt **policy release** an toàn.
3. Áp dụng **shadow/dry-run**, **canary** và **phát hành theo giai đoạn**, không nhầm preview với enforcement.
4. Tích hợp một **policy dispatcher** với Spring Security method/request authorization.
5. Thiết kế **rollback**, emergency deny, policy/data freshness, cache và audit khi có lỗi.
6. Xây bảng kiểm thử khác biệt quyền và chạy một demo Java 17+ có stdout xác định.

**Nguyên tắc tối thượng:** không đánh đổi việc kiểm tra quyền chính xác lấy tiện lợi rollout. Một bản policy cũ chỉ có thể là phương án dự phòng khi **vẫn đáp ứng các điều kiện bảo mật bắt buộc và ngân sách độ mới của dữ liệu**.

## 2. Những loại phiên bản không được đánh đồng

| Phiên bản | Đại diện cho gì? | Ví dụ | Vì sao quan trọng |
| --- | --- | --- | --- |
| **Policy revision** | Nội dung bộ rule quyết định grant/deny | `document-policy@v2` | Biết chính xác logic đang áp dụng |
| **Policy artifact digest** | Hash của nội dung artifact phát hành | SHA-256 của bundle | Phát hiện sai bản/tampering |
| **Release/activation revision** | Ai dùng policy nào, từ khi nào | `release-2026-11-A` | Cùng policy có thể active cho nhóm khác nhau |
| **Policy schema version** | Hợp đồng thuộc tính và cấu trúc đầu vào | `schemaVersion=3` | Ngăn evaluator hiểu sai fields |
| **Application version** | Bản Java service đang chạy | `app-4.9.1` | Xác định tương thích với policy |
| **Membership/ACL data version** | Trạng thái role, grant, owner, tenant | `membershipEpoch=128` | Quyền thay đổi dù policy code giữ nguyên |
| **Decision ID / audit ID** | Một lần đánh giá quyền cụ thể | `decision-7f...` | Điều tra chính xác caller, rule, kết quả |

Một Git commit ID **có thể** là một thành phần của policy revision, nhưng không chứng minh release đó đã được áp dụng trong production. Ngược lại, policy v2 có thể đã được publish nhưng chỉ 5% tenant chạy v2, còn 95% vẫn dùng v1.

**Ví dụ:**

```text
Code application:       app-4.9.1
Supported policy schema: 3
Approved artifacts:    doc-policy@v1, doc-policy@v2
Release routing:
  tenant-a -> doc-policy@v1
  tenant-b -> doc-policy@v2
  tenant-c -> doc-policy@v1
ACL data for tenant-b: membershipEpoch=128
```

Một quyết định READ cho Bob có thể chuyển từ ALLOW sang DENY khi Bob bị xóa khỏi tenant B, ngay cả khi `doc-policy@v2` **không hề đổi**. Vì vậy cần phân biệt **triển khai policy** với **thu hồi quyền trong dữ liệu động**.

### Phiên bản phải có phạm vi rõ

Không có nghĩa mọi loại tài nguyên phải dùng một version chung:

- `document-read-policy@v4`.
- `invoice-approval-policy@v7`.
- `tenant-membership-policy@v3`.
- `share-link-policy@v2`.

Nhưng cũng không nên để quá nhiều phiên bản tùy ý làm mất khả năng biết một request đã dùng chính sách nào. Một **policy bundle/release manifest** có thể pin tập phiên bản cần thiết và chỉ kích hoạt sau khi xác minh tương thích.

## 3. Policy-as-code và artifact bất biến

Thay đổi policy nên đi qua quy trình tương tự phần mềm có kiểm soát bảo mật:

```text
Tác giả đề xuất thay đổi
       |
       v
Code review + security review
       |
       v
Static/schema checks + unit tests + differential tests
       |
       v
Build artifact/bundle không thay đổi nội dung
       |
       v
Digest/chữ ký/attestation (nếu kiến trúc yêu cầu)
       |
       v
Approved release manifest
       |
       v
Shadow / canary / rollout từng giai đoạn
       |
       v
Theo dõi kết quả và xác minh trên PEP
```

**Artifact bất biến** nghĩa là `doc-policy@v2` đã được phát hành thì không sửa nội dung của nó tại chỗ. Muốn thay đổi rule, tạo `v3` hoặc một bản hotfix được duyệt. Nếu cùng tên `v2` trỏ tới hai nội dung khác nhau, logs, cache và rollback không còn tái hiện được.

Một policy release nên có ít nhất:

| Trường | Mục đích |
| --- | --- |
| `policyId` | Tên chính sách, ví dụ `document-access` |
| `revision` | Version bất biến |
| `artifactDigest` | Định danh chính xác nội dung |
| `schemaVersion` | Hợp đồng attributes/resources |
| `approvedBy` và `approvedAt` | Audit phê duyệt |
| `releaseId` | Phiên bản routing/kích hoạt |
| `baselineRevision` | Bản đã hoạt động trước khi rollout |
| `candidateRevision` | Bản muốn thử |
| `cohortDefinition` | Nhóm tenant/subject/service được thử |
| `rolloutStage` | SHADOW, CANARY, GENERAL hoặc HOLD |
| `requiredGuardrails` | Các bất biến không được bypass |
| `rollbackTarget` | Bản được phép quay lại khi có sự cố |

### Ví dụ release manifest

```json
{
  "releaseId": "doc-release-2026-11-05-r2",
  "policyId": "document-access",
  "schemaVersion": 3,
  "baselineRevision": "v1",
  "candidateRevision": "v2",
  "candidateDigest": "sha256:example-digest-from-reviewed-build",
  "stage": "CANARY",
  "cohort": {
    "type": "TENANT_ALLOWLIST",
    "tenantIds": ["tenant-canary"]
  },
  "guardrails": {
    "denyCrossTenant": true,
    "denyDeletedResource": true,
    "requireAuthenticatedSubject": true
  }
}
```

Đây là **JSON minh họa thiết kế**, không phải schema của Spring Security hoặc Open Policy Agent. Giá trị `candidateDigest` chỉ là chuỗi ví dụ, **không phải hash thật**; trong production digest phải tính từ artifact và được kiểm chứng. Danh sách tenant canary phải do hệ thống quản trị phát hành kiểm soát, **không** lấy từ một header tự khai bởi client.

**Đừng** cho request tự gửi `policyVersion=v1` để chọn một bản dễ dãi hơn. Routing policy là quyết định của **control plane đáng tin**, không phải tùy chọn phân quyền của caller.

## 4. Policy Decision Point và Policy Enforcement Point

Trong kiến trúc phân quyền:

- **PAP (Policy Administration Point):** nơi soạn, duyệt và phát hành policy.
- **PDP (Policy Decision Point):** nơi đánh giá rule và trả quyết định.
- **PIP (Policy Information Point):** nơi lấy actor, tenant membership, resource owner, ACL, context.
- **PEP (Policy Enforcement Point):** nơi thật sự cho phép hoặc chặn request/method/DB mutation.

Ở ứng dụng Spring Security:

```text
HTTP Request / Service Method
          |
          v
PEP: AuthorizationFilter hoặc method interceptor
          |
          v
Version Router (trusted release configuration)
          |
          +--> Baseline PDP: doc-policy@v1
          |
          +--> Candidate PDP: doc-policy@v2
          |
          v
Authoritative Decision: ALLOW | DENY
          |
          v
PEP thực thi kết quả, không chỉ ghi log
          |
          v
Service + repository có tenant/resource scope
```

PDP có thể là Java bean trong cùng JVM hoặc một dịch vụ bên ngoài. **Quyết định được trả về không tự thực thi**: nếu controller vẫn gọi repository và trả dữ liệu khi PDP nói DENY, toàn bộ pipeline phân quyền thất bại.

Bản shadow/candidate chỉ có giá trị dự đoán, **không** được thay đổi quyết định authoritative khi đang ở chế độ SHADOW.

## 5. Hợp đồng quyết định phải ổn định qua các phiên bản

Một lần đánh giá có đủ thành phần:

```text
subject  = authenticated principal + verified tenant role
resource = Document 42, tenant A, owner Alice, status DRAFT
action   = SHARE
context  = server time, authentication assurance, workflow state
```

Nếu v2 thêm thuộc tính `mfaConfirmed` nhưng ứng dụng cũ không gửi, evaluator có thể gặp null. Phải định nghĩa rõ:

- Field **bắt buộc** mới có schema version mới hoặc rollout tương thích.
- Field không có thì **DENY** đối với rule yêu cầu nó, không ngầm mặc định true.
- Các enum/action không biết phải bị từ chối hoặc reject theo contract; không ép unknown thành READ.
- Kết quả `null`/`abstain` của engine không được hiểu là ALLOW.
- Thông tin nguồn của thuộc tính phải được xác minh; ví dụ MFA không thể lấy từ `X-MFA: yes` do client gửi.

Kết quả nội bộ có thể chứa:

```json
{
  "effect": "DENY",
  "reasonCode": "STEP_UP_REQUIRED",
  "policyId": "document-access",
  "policyRevision": "v2",
  "releaseId": "doc-release-2026-11-05-r2",
  "evaluatedAt": "2026-11-05T09:00:00Z"
}
```

Đây là DTO ví dụ, không phải output mặc định của Spring Security. `reasonCode` hữu ích cho audit và metric; **không đưa chi tiết owner/tenant/ACL nội bộ ra response** nếu caller không có quyền biết tài nguyên tồn tại.

### Bất biến an toàn áp dụng ngoài từng version

Một số điều kiện nên tồn tại ở mọi version của policy:

```text
Authentication đáng tin
AND Tenant đã xác minh membership
AND Resource thật thuộc đúng tenant
AND Account/resource không bị khóa/xóa theo chính sách bắt buộc
AND Action hợp lệ
AND Policy artifact được phê duyệt + còn trong freshness budget
AND Rule phiên bản đang active cho phép hành động
```

Một candidate không được phép trả ALLOW khi vi phạm các ràng buộc bất biến kể cả do lỗi rule. Có thể cưỡng chế chúng tại PEP, lớp domain chung, query database/RLS hoặc nhiều lớp đồng thời.

**Rollback về bản cũ không được tắt guardrail vừa được yêu cầu bởi một quyết định khẩn cấp.** Nếu lỗi bảo mật được khắc phục ở v2, v1 có thể là rollback target **không còn an toàn**, dù v1 từng chạy ổn định.

## 6. Phân loại thay đổi trước khi rollout

Không phải mọi thay đổi đều có mức độ rủi ro như nhau.

| Thay đổi | Ví dụ | Rủi ro cần theo dõi |
| --- | --- | --- |
| **Tightening** (siết quyền) | Thêm yêu cầu MFA khi SHARE | Từ chối nhầm user hợp lệ, gián đoạn nghiệp vụ |
| **Relaxation** (nới quyền) | Cho EDITOR đọc thêm tài liệu nhạy cảm | Rò dữ liệu nếu sai scope/tenant |
| **Correction** | Sửa role mapping ở một tenant | Có thể thay đổi ALLOW và DENY |
| **Refactor** | Thay SpEL bằng bean Java nhưng giữ logic | Regression hoặc khác precedence |
| **Attribute source change** | Chuyển quyền từ JWT claim sang DB | Đồng bộ, stale cache, availability |
| **New action/resource** | Thêm `invoice:export` | Quyền mặc định và các endpoint mới |
| **Emergency revoke** | Chặn user/tenant bị xâm nhập | Cần hiệu lực nhanh, không chờ canary thông thường |

**Nguyên tắc risk-based:** nới quyền thường cần ngưỡng kiểm duyệt cao hơn và bằng chứng thử nghiệm chống privilege escalation; siết quyền cần test business impact và đường phục hồi hợp lệ. Không dùng rollout tuần tự kéo dài cho một lệnh chặn truy cập khẩn cấp nếu sự chậm trễ tạo cửa sổ xâm nhập không chấp nhận được.

## 7. Shadow evaluation (dry-run) hoạt động như thế nào?

Trong SHADOW:

1. PEP tiếp nhận request và xác minh subject/resource như bình thường.
2. **Policy v1 quyết định thật** và PEP tuân theo v1.
3. **Policy v2 được chạy thêm** trên cùng bộ attributes đã được kiểm chứng, chỉ để ghi kết quả.
4. Hệ thống so sánh hai quyết định và thống kê khác biệt.
5. Kết quả v2 **không được** cấp thêm quyền hoặc chặn user theo bản candidate khi stage là SHADOW.

```text
                       One verified request
                              |
                 +------------+-------------+
                 |                          |
                 v                          v
          Baseline policy v1          Candidate policy v2
                 |                          |
                 v                          v
       ALLOW / DENY thật           ALLOW / DENY giả lập
                 |                          |
                 v                          |
           PEP enforce                 Audit/compare only
                 |                          |
                 +------------+-------------+
                              |
                     Decision delta metrics
```

### Ma trận so sánh v1 và v2

| v1 (thực thi) | v2 (shadow) | Đọc như thế nào |
| --- | --- | --- |
| ALLOW | ALLOW | Không khác ở outcome |
| ALLOW | DENY | Candidate **siết quyền**; cần xem có từ chối nhầm không |
| DENY | ALLOW | Candidate **nới quyền**; cần ưu tiên review nguy cơ lộ dữ liệu |
| DENY | DENY | Cùng outcome nhưng có thể khác reason |
| Error/unknown | Bất kỳ | Không dùng shadow làm phương án cấp quyền |
| Bất kỳ | Error/unknown | Candidate chưa sẵn sàng, phải sửa trước canary |

**Chú ý:** một quyết định `DENY→ALLOW` trong shadow **không chứng minh** user thực sự đã được xem dữ liệu; v1 vẫn chặn. Ngược lại, một `ALLOW→DENY` cho thấy candidate có thể làm một request hợp lệ thất bại khi được kích hoạt.

### Shadow phải không có side effect

- Không ghi ACL, thay trạng thái resource hoặc gửi email.
- Không gọi workflow phê duyệt thật.
- Không tăng quota/đếm sử dụng để tính phí như một request thật.
- Không để candidate đổi đối tượng cache đang phục vụ baseline.
- Có thể lưu audit/delta metric đã loại bỏ dữ liệu nhạy cảm, nhưng cần rate limit và quyền truy cập phù hợp.

Nếu PDP gọi PIP/DB, shadow có thể tăng tải. Dùng sampling, timeout, bulk attributes hoặc dedicated test infrastructure theo yêu cầu. Đừng để lỗi trong candidate làm request thật bị fail nếu authoritative baseline vẫn khỏe, trừ khi chính điều kiện an toàn bắt buộc yêu cầu dừng.

### Điều kiện để tin kết quả shadow

Shadow chỉ có ý nghĩa nếu baseline và candidate nhận **cùng subject/resource/action/context snapshot** hoặc sự khác nhau được ghi rõ. Nếu baseline tra owner trước khi cập nhật còn candidate tra owner sau một transaction khác, chênh lệch có thể đến từ dữ liệu thay đổi, không phải từ rule.

Nên ghi policy version, input schema version, decision outcome, reason code và thời điểm; không cần log nguyên JWT hoặc nội dung tài liệu.

## 8. Canary: kích hoạt một phiên bản với nhóm ổn định

Ở stage CANARY, policy v2 thực sự được PEP dùng cho một **cohort giới hạn**, còn người ngoài cohort vẫn dùng v1.

```text
Authenticated request
       |
       v
Verified tenant + trusted release routing
       |
       +-- tenant thuộc canary cohort --> v2 (enforced)
       |
       +-- tenant khác ---------------> v1 (enforced)
```

Canary khác shadow ở điểm: **v2 có quyền tác động thực tế** lên kết quả ALLOW/DENY của nhóm được chọn.

### Chọn cohort thế nào?

Các chiến lược hợp lệ:

- **Allowlist nội bộ:** chỉ những tenant kiểm thử/khách hàng đã đồng ý.
- **Stable hash:** chọn một phần trăm tenant theo hash ổn định của tenant ID với một salt/thuật toán được quản trị.
- **Theo environment/region:** sandbox, staging, một vùng production có điều kiện.
- **Theo hành động:** chỉ thử v2 cho READ, chưa thử cho SHARE/DELETE.
- **Theo nhóm người dùng:** nhân viên nội bộ, tenant low-risk, canary opt-in được xác minh.

Điều quan trọng: cohort phải được chọn bằng **dữ liệu đã được server xác minh**. Không cho user gửi `?usePolicy=v1` hoặc `X-Canary: false` để thoát khỏi v2.

### Stable cohort thay vì random mỗi request

Sai:

```java
boolean useCandidate = Math.random() < 0.05;
```

Nếu cùng Alice gửi hai request liên tiếp mà mỗi request rơi ngẫu nhiên vào policy khác, quyền có thể lúc cho lúc chặn; với hai service trong cùng transaction, có thể còn tạo hành vi không nhất quán.

Đúng hơn:

```text
cohortId = verifiedTenantId
bucket = stableHash("release-r2", cohortId) mod 10000
useCandidate = bucket < rolloutBasisPoints
```

Đây là **thuật toán khái niệm**. Khi triển khai nhiều ngôn ngữ/microservices, phải cố định thuật toán hash, encoding, salt, version và kết quả test vector. Không mặc định `String.hashCode()` của Java tương đương hash ở một service viết bằng Go/Node.

Nếu cần tính ổn định **trong toàn bộ vòng đời release**, cách thay phần trăm phải được định nghĩa: ví dụ tăng ngưỡng 1% → 5% → 25% giữ nguyên salt/hash giúp các tenant đã được chọn tiếp tục ở cohort. Thay seed tùy tiện trong quá trình nâng tỷ lệ sẽ làm membership canary nhảy lung tung.

### Không canary theo một ID do client chọn

Khi tenant selector lấy từ URL, phải **xác minh membership trước khi routing policy**. Nếu client có thể tự đặt tenant ID khác để ép policy v1, canary sẽ trở thành cơ chế bypass.

Đối với object khác tenant, PEP vẫn chặn theo ranh giới tenant **dù** candidate vô tình trả allow.

## 9. Một kế hoạch triển khai theo giai đoạn

Một flow thực tế có thể là:

| Giai đoạn | Chính sách thực thi | Điều kiện qua bước |
| --- | --- | --- |
| **DRAFT** | v1 | Soạn v2; schema, lint, unit tests |
| **REVIEWED** | v1 | Security review, approval, digest, compatibility |
| **SHADOW** | v1; v2 so sánh | Không có delta nguy hiểm chưa được giải thích |
| **CANARY 1%** | v2 cho cohort nhỏ | Đã test negative và business impact; giám sát PEP |
| **CANARY 5%** | v2 cho cohort lớn hơn | Metrics ổn định, không cross-tenant leak |
| **RAMP 25% → 50%** | v2 cho nhiều tenant | SLO, deny-rate, latency, lỗi PDP/DB đạt ngưỡng |
| **GENERAL** | v2 gần/toàn bộ | Xác nhận tất cả PEP đã active đúng version |
| **CLEANUP** | v2 | Sau thời gian quan sát, chỉ dọn v1 khi có kế hoạch |

Các tỷ lệ trên là **ví dụ**, không phải chuẩn bắt buộc. Với emergency block hoặc chính sách có rủi ro nghiêm trọng, rollout theo giai đoạn có thể **không phù hợp**; phải áp dụng lớp deny khẩn cấp đủ nhanh, rồi đo sự lan truyền.

### Cổng phê duyệt và người chịu trách nhiệm

Cần định nghĩa:

- Ai được tạo và sửa rule.
- Ai có quyền approve release.
- Ai có quyền tăng canary percentage.
- Ai có quyền rollback hoặc emergency stop.
- Ai theo dõi dashboard và đánh giá tác động.
- Ai chịu trách nhiệm đối soát security incidents.
- Cần “four-eyes approval” hay break-glass process không.

Không để cùng một caller của application API vừa là người yêu cầu resource vừa tự chọn phiên bản policy và thay đổi rollout config. **Control plane và data plane phải tách quyền.**

## 10. Đo điều gì trong shadow/canary?

Không chỉ xem HTTP 5xx. Một policy sai có thể cho thêm quyền mà **không gây lỗi**.

Những metric hữu ích:

| Nhóm | Metric/quan sát | Lý do |
| --- | --- | --- |
| Correctness | `ALLOW→DENY` delta | Đo tác động siết quyền |
| Correctness | `DENY→ALLOW` delta | Ưu tiên phát hiện nới quyền ngoài dự tính |
| Authorization | Deny rate theo action/tenant cohort | Tìm regression, tránh gộp mọi loại request |
| Security | Số cross-tenant attempt được DENY | Kiểm tra invariant |
| Availability | PDP unavailable/timeout/invalid revision | Không để fail-open |
| Performance | Latency p50/p95/p99 của authorization | Policy mới có quá tốn I/O không |
| Data freshness | Policy/data age, activation lag | Kiểm tra SLA revocation |
| Consistency | Tỷ lệ PEP báo active đúng revision | Phát hiện rollout chưa đến mọi node |
| Business | Chức năng chia sẻ/xuất bị chặn, support tickets | Phát hiện từ chối nhầm |
| Audit | Version và reason code của quyết định | Điều tra có căn cứ |

### Đếm đúng mẫu số

Ví dụ 100 request canary, 40 DENY của v2, nhưng 39 đã là DENY ở v1 thì mức thay đổi thực tế nhỏ. Ngược lại, 1 request `DENY→ALLOW` trên chức năng xuất dữ liệu nhạy cảm có thể nghiêm trọng hơn hàng trăm `ALLOW→DENY` trên một thao tác ít rủi ro.

Nên phân nhóm theo **resource type, action, tenant, client, policy version**, với nhãn có cardinality kiểm soát. Không đưa subjectId/documentId thô làm label metrics có cardinality vô hạn hoặc lộ dữ liệu. Dùng audit bảo mật có quyền truy cập hạn chế cho điều tra chi tiết.

### Một ngưỡng dừng ví dụ

```text
STOP nếu:
  có ít nhất 1 DENY->ALLOW trên bất biến cross-tenant
  OR có quyền mới không có approval
  OR candidate version không kiểm chứng được
  OR PDP freshness vượt ngân sách
  OR tỷ lệ lỗi/độ trễ vượt ngưỡng SLO đã phê duyệt
```

Ngưỡng là **policy vận hành ví dụ**. Cần xác định ai nhận cảnh báo, ai có quyền dừng và công cụ dừng có thực thi được khi hệ thống chính gặp sự cố hay không.

## 11. Tích hợp với Spring Security: ranh giới kỹ thuật

Spring Security hỗ trợ `authorizeHttpRequests`, `@PreAuthorize` và `AuthorizationManager<T>`. Hệ thống **không tự có** một API canary/rollback chung cho mọi ứng dụng. Cơ chế version routing, kho policy và quy trình phê duyệt phải được ứng dụng hoặc nền tảng policy của tổ chức quản lý.

### AuthorizationManager và phiên bản Spring Security

Javadoc có khác biệt theo phiên bản:

- Trong Spring Security 6.5, `AuthorizationManager<T>` vẫn có `check(Supplier<Authentication>, T)` (deprecated) và `authorize(...)` default, cùng `AuthorizationDecision`/`AuthorizationResult`.
- Trong các phiên bản 7.x, `authorize(...)` là method chính; các API/annotation nullability có thay đổi.
- `AuthorizationDecision` có thể được dùng làm kết quả allow/deny trong integration tương ứng.

**Không** copy một class override `check` từ ví dụ 6.x rồi cho rằng biên dịch nguyên xi trong mọi version 7.x. Với project thật, kiểm tra Javadoc theo dependency đã lock, chạy compile tests và pin runtime compatibility trong release manifest.

### @PreAuthorize với policy bean versioned

Đây là kiểu tích hợp dễ kiểm thử khi policy đang ở trong JVM:

```java
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentService {
    private final DocumentRepository documents;

    public DocumentService(DocumentRepository documents) {
        this.documents = documents;
    }

    @PreAuthorize(
        "hasAuthority('document:share') and " +
        "@documentPolicyFacade.canShare(authentication, #id)"
    )
    public ShareResult share(
            @P("id") Long id, ShareRequest request) {
        // Chỉ chạy nếu policy đã cấp quyền.
        // Kiểm tra lại dữ liệu/ghi ở transaction boundary khi cần.
        return shareCommand.execute(id, request);
    }
}
```

Đây là **component fragment**: `DocumentRepository`, `ShareResult`, `ShareRequest`, `shareCommand` và bean `documentPolicyFacade` là những thành phần ứng dụng cần triển khai. Nó minh họa cách đặt PEP tại service, **không phải file độc lập**.

Một facade có thể hoạt động như sau:

```java
public boolean canShare(Authentication authentication, Long id) {
    VerifiedActor actor = actors.fromAuthentication(authentication);
    DocumentFacts doc = facts.findVisibleDocument(
        actor.verifiedTenantId(), id
    );
    if (doc == null) {
        return false;
    }

    ReleaseSnapshot release = releaseRegistry.currentFor(
        "document-access", actor.verifiedTenantId()
    );
    if (!release.isVerifiedAndFresh()) {
        return false;
    }

    PolicyDecision enforced = policies.evaluate(
        release.activePolicyRevision(),
        actor, doc, Action.SHARE, serverContext.now()
    );

    shadowComparison.compareAsyncWithoutEffects(
        release, actor, doc, Action.SHARE, enforced
    );

    return enforced.allowed();
}
```

Đây là **pseudocode Java-style**, không biên dịch độc lập: `VerifiedActor`, `DocumentFacts`, `ReleaseSnapshot`, `policies`, `serverContext`, `shadowComparison` là domain APIs tự thiết kế. Gọi shadow là tùy chọn, không được làm thay đổi quyết định và không được bỏ ràng buộc mandatory của PEP.

**Quan trọng:** `canShare` phải dùng tenant và chủ thể từ Authentication/membership đã xác minh, không lấy `releaseRegistry.currentFor(...)` bằng tenant ID do client tùy ý khai. `facts` phải tra đúng document thật và xác minh tenant/owner/ACL; nếu chỉ tin JSON từ client, candidate/baseline đều có thể bị khai thác.

### Data-scoped enforcement vẫn cần

Mặc dù `@PreAuthorize` chặn trước method body, một resource có thể chuyển owner/status hoặc quyền SHARE có thể bị thu hồi giữa check và hành động. Với mutation nhạy cảm, hãy dùng transaction/conditional update có tenant/resource/authorization constraints, optimistic lock hoặc giải pháp đồng bộ phù hợp.

`@PostAuthorize` **không phải** một biện pháp đủ để bảo vệ write vì side effects có thể đã commit trước khi post-check. Đừng nghĩ rollback *policy version* đồng nghĩa rollback *database transaction* hay những email/event đã gửi.

### Có cần tách bean theo phiên bản không?

Một mẫu rõ ràng:

```java
public interface DocumentPolicy {
    PolicyDecision decide(
        VerifiedActor actor,
        DocumentFacts document,
        Action action,
        VerifiedContext context
    );
}

public final class DocumentPolicyV1 implements DocumentPolicy { /* ... */ }
public final class DocumentPolicyV2 implements DocumentPolicy { /* ... */ }
```

Đây là outline cấu trúc: `PolicyDecision`, `VerifiedActor`, `DocumentFacts`, `Action` và `VerifiedContext` là types của ứng dụng. Version router chọn implementation theo release config **đã ký/xác minh**, không theo request parameter.

Duy trì hai bean phiên bản song song trong cùng JVM giúp shadow và canary dễ hơn, nhưng phải tính chi phí memory/CPU. Với external PDP, bản policy có thể nằm trong bundle riêng; yêu cầu phiên bản/nguồn tin cậy, audit và rollback vẫn giống nhau.

## 12. Policy version không được tự phá tenant, action và object scope

Ví dụ rủi ro:

```java
if (useCandidate) {
    return request.hasAuthority("document:read");
}
return oldPolicy.canRead(authentication, documentId);
```

Candidate trên bỏ kiểm tra owner, tenant, ACL và trạng thái resource: trong canary, mọi user có authority chức năng có thể đọc Document của người khác.

Phương án an toàn hơn:

```text
mandatoryBoundary(actor, document, action)
    AND
selectApprovedVersion(release, verifiedTenant)
        .decide(actor, document, action, verifiedContext)
```

Mọi version vẫn phải đi qua **điều kiện bất biến**. Nếu policy v2 là bản sửa lỗi cross-tenant, không để v1 tiếp tục xử lý request production của tenant khác với một “canary 1%”: khi đó cần một lớp mandatory deny/hotfix trước mọi policy hoặc rollout emergency toàn cục theo SLA.

**Không có nghĩa mọi điều kiện mandatory phải duplicate ở mọi lớp**, nhưng kiến trúc cần một nơi cưỡng chế đáng tin, được kiểm thử xuyên phiên bản và không bị disable bởi release router.

## 13. Atomic activation: ai đang dùng version nào?

Một nguồn release config có thể lưu:

```text
policy_id       = document-access
release_id      = release-42
baseline        = v1
candidate       = v2
stage           = CANARY
cohort_revision = allowlist-r3
activation_epoch= 105
effective_at    = 2026-11-05T10:00:00Z
```

Khi thay stage từ CANARY sang GENERAL, hệ thống phải bảo đảm:

- Update cấu hình ở control plane **có tính nhất quán phù hợp**, không để bản ghi chỉ đổi nửa phần.
- PEP dùng **một release snapshot** cho từng quyết định; không đọc stage của v2 nhưng digest của v1.
- Artifact v2 đã sẵn sàng và được kiểm chứng **trước** khi activation pointer trỏ đến nó.
- Mọi PEP có khả năng báo **revision và epoch đang hoạt động**.
- Trong giai đoạn lan truyền, có cơ chế theo dõi các node chưa đồng bộ và xử lý theo SLA.
- Policy config không thể bị ghi bởi caller application bình thường.

Một thiết kế thường dùng là tạo **immutable release object** rồi thay **pointer/epoch** có điều kiện (CAS/transaction). Điều này giúp rollback nhanh hơn việc sửa trực tiếp nhiều dòng rule. Nhưng khi nhiều service/node dùng cache, một lần ghi pointer vào DB **không bảo đảm** tất cả PEP đã dùng phiên bản mới.

### Request đang chạy khi release đổi

```text
T1: bắt đầu check với release epoch 105 (v1)
T2: kích hoạt release epoch 106 (v2)
T1: tiếp tục một thao tác write
```

Nếu nghiệp vụ yêu cầu rule mới có hiệu lực trước khi T1 commit, cần thêm cơ chế kiểm tra lại epoch/transaction hoặc điều kiện ghi; không mặc định việc pointer thay đổi sẽ dừng mọi request đang chạy.

Đối với đọc thông thường, một snapshot theo quyết định có thể chấp nhận được; đối với phê duyệt tài chính hoặc thay đổi ACL nhạy cảm, cần xác định rõ **thời điểm hiệu lực của policy** và tính nhất quán ở DB.

## 14. Rollback là chuyển về bản **được phép** chứ không phải quay bừa về v1

Giả sử candidate v2 có một lỗi khiến Alice không thể SHARE tài liệu của mình mặc dù đã MFA. Có thể muốn quay về v1 ngay. Nhưng v1 không yêu cầu MFA, trong khi MFA vừa được áp đặt để xử lý sự cố. **Rollback trực tiếp v1 có thể khôi phục lỗ hổng**, vì vậy không phải lúc nào cũng được phép.

Phân biệt:

| Loại sự cố | Cách xử lý hợp lý |
| --- | --- |
| Candidate siết nhầm quyền, baseline vẫn đáp ứng guardrails | Chuyển active pointer về baseline được duyệt |
| Candidate nới quyền làm lộ dữ liệu | Dừng candidate, áp emergency deny, đánh giá ảnh hưởng và revoke dữ liệu/token |
| Baseline cũng chứa lỗ hổng vừa được chặn | Không rollback mù về baseline; phát hành hotfix/guardrail an toàn |
| Candidate artifact không xác minh được | Không kích hoạt; giữ verified revision còn đủ freshness hoặc từ chối |
| Data schema đã migration không tương thích baseline | Chỉ rollback với compatibility plan; không tự dùng code cũ đọc schema mới |
| External PDP lỗi | Fail closed theo budget; có thể dùng last-known-good *nếu còn hợp lệ*, không mặc định ALLOW |
| Một số node chưa cập nhật | Cô lập/kiểm soát traffic hoặc từ chối request không đáp ứng minimum revision |

### Rollback playbook

1. Xác định sự cố và **phạm vi ảnh hưởng**: action, cohort, tenant, policy versions, các PEP liên quan.
2. **Stop ramp**: dừng tăng canary, tắt candidate ở các cohort chưa bị ảnh hưởng nếu có thể.
3. **Bảo vệ ngay** đường có nguy cơ nới quyền: deny overlay hoặc cách cô lập an toàn.
4. Xác định rollback target đã được phê duyệt và **vẫn thỏa guardrails mới nhất**.
5. Đổi release pointer/epoch có điều kiện; không sửa artifact bất biến.
6. Xác nhận mọi PEP báo revision/epoch mới trong ngân sách propagation.
7. Flush/invalidate decision cache và policy cache theo revision/cohort, đảm bảo không dùng ALLOW cũ.
8. Test bằng request/identity thật thuộc nhóm canary, ngoài canary và các hành động nhạy cảm.
9. Kiểm tra **side effects đã xảy ra**: tài liệu được export, quyền được share, approval đã commit; policy rollback không hoàn tác chúng.
10. Ghi audit, thông báo người có trách nhiệm và chuẩn bị bản sửa v3/guardrail mới.

### Kill switch cũng phải có quyền hạn và audit

Một nút “disable candidate” có thể làm gián đoạn nghiệp vụ nhưng thường cần trong sự cố. Người vận hành được dùng phải có quyền riêng (ví dụ `POLICY_RELEASE_ADMIN`), có bước xác minh thích hợp và audit đầy đủ. Không đưa kill switch trực tiếp vào API resource dùng bởi user thường.

**Chú ý:** một “kill switch” đặt `permitAll()` để giảm lỗi là **sai thiết kế**. Khẩn cấp nên giữ hoặc tăng deny cho đường bị ảnh hưởng, hoặc trả lỗi an toàn khi không thể quyết định.

## 15. Freshness, cache và khả năng hoạt động khi mất control plane

Có nhiều loại cache:

- **Policy artifact cache:** mã/AST/bundle của version đã được kiểm chứng.
- **Release routing cache:** tenant/cohort đang dùng revision nào.
- **Authorization data cache:** membership, ACL, owner, share grants.
- **Decision cache:** kết quả ALLOW/DENY cho subject-resource-action-context.
- **Response cache:** dữ liệu thực tế trả về sau khi được cấp quyền.

Đổi policy v1 → v2 phải xem tác động của cả năm, không chỉ clear một cache.

### Cache key tối thiểu cho decision

Một key kiểu `canRead:document42` là không an toàn vì thiếu subject. Có thể cần:

```text
subjectId
| verifiedTenantId
| resourceType
| resourceId
| action
| releaseId
| policyRevision
| membershipOrAclVersion
| relevantContextVersion
```

Không phải lúc nào nên encode đủ mọi field thô vào key; có thể dùng namespace/hash và invalidation có điều kiện. Tuy nhiên **các chiều tác động tới quyền phải được thể hiện** hoặc được kiểm tra lại ở runtime.

### Last-known-good không đồng nghĩa luôn an toàn

Ví dụ PDP còn giữ `doc-policy@v1` đã xác minh, nhưng bản v1 **cho phép** Bob đọc sau khi Bob bị revoke ở nguồn membership. Nếu PIP không thể cập nhật quyền trong 30 phút, việc tiếp tục dùng policy v1 không bảo đảm đúng.

OWASP khuyến nghị xác định **freshness budget** cho policy và security-relevant data. Khi dữ liệu/bundle quá cũ hoặc thiếu, phải từ chối **các thao tác bị ảnh hưởng** thay vì fallback thành ALLOW. “Last-known-good” chỉ hợp lệ khi artifact **được xác minh** và các điều kiện độ mới/guardrail **vẫn đáp ứng**.

Một quy tắc cơ bản:

```text
if artifact invalid / unapproved / unsupported:
    DENY affected operation

if required membership/ACL/revocation data stale beyond budget:
    DENY affected operation

if verified policy and data fresh enough:
    evaluate current approved revision
```

Đoạn trên là logic khái niệm; một hệ thống có thể trả 503 thay vì 403 khi dependency outage, nhưng **không cấp quyền** chỉ để che giấu lỗi availability.

### Invalidation và lan truyền

- Push event invalidation hoặc poll revision/epoch có giới hạn thời gian.
- Dùng compare-and-swap/monotonic epoch, không nhận stale update ghi đè release mới hơn.
- Tại startup, PEP chỉ phục vụ protected operations khi có version và dữ liệu bắt buộc hợp lệ.
- Khi control plane mất kết nối, PEP có thể dùng verified policy còn đủ freshness nếu thiết kế cho phép.
- Nếu emergency block yêu cầu hiệu lực trong vài giây, không dùng cache TTL vài chục phút.
- Đo **effective revision ở PEP**, không chỉ “publish thành công” ở PAP.

## 16. Tương thích schema và giao thức giữa Java services

Một candidate mới có thể yêu cầu thuộc tính khác:

```json
{
  "subject": {
    "id": "alice",
    "tenantId": "tenant-a",
    "strongAuthentication": true
  },
  "resource": {
    "type": "Document",
    "id": 42,
    "tenantId": "tenant-a",
    "status": "DRAFT"
  },
  "action": "SHARE",
  "context": {
    "evaluatedAt": "2026-11-05T09:00:00Z"
  }
}
```

Ví dụ attribute input này là **dữ liệu đã được PEP/PIP xác minh** trong kiến trúc mẫu, không phải JSON client có thể tự gửi đến authorization service để tạo quyền.

Nếu service cũ chỉ biết `subject.id` và `resource.id`, candidate yêu cầu `strongAuthentication` sẽ gặp thiếu dữ liệu. Cần:

1. Định nghĩa `schemaVersion` và required fields.
2. Nâng producer/PEP để gửi attributes trước khi active policy.
3. Đặt mặc định **DENY** cho thuộc tính bắt buộc không được cung cấp.
4. Test backward/forward compatibility.
5. Không loại v1 khỏi runtime đến khi rollback target được xác nhận.
6. Khi DB migration không thể rollback, chuẩn bị **forward fix** thay vì ép application/schema về trạng thái không tương thích.

### Policy version và app version phải được kiểm tra ở startup

Có thể lưu:

```text
policy-v1 compatible with schema 2..3
policy-v2 requires schema 3
app-4.9 supports schema 2
app-4.10 supports schema 3
```

Trong tình huống trên, không bật v2 cho app-4.9. Tại startup/activation, xác minh policy/schema compatibility và từ chối protected operations không đáp ứng thay vì đọc field thiếu rồi coi là true.

## 17. Java 17 chạy độc lập: shadow, canary và rollback có thể tái hiện

Chương trình sau **không sử dụng Spring Security, database hoặc server**. Nó mô phỏng chính sách v1 và v2; v2 thêm yêu cầu xác thực mạnh khi chủ sở hữu SHARE. Một danh sách tenant canary **do server cấu hình** chọn những request được thực thi bởi v2. Shadow chạy v2 nhưng **không thay đổi** quyết định thực thi của baseline. Sau cùng, router rollback cho nhóm canary.

Demo cố tình cho thấy **rollback từ v2 về v1 sẽ nới lại điều kiện MFA**; production chỉ được làm thế nếu v1 vẫn là rollback target hợp lệ theo chính sách bảo mật mới nhất.

Lưu vào file `PolicyReleaseDemo.java`:

```java
import java.util.HashSet;
import java.util.Set;

public class PolicyReleaseDemo {
    enum Action { READ, SHARE }

    record Subject(
        String id, String tenant, boolean active,
        boolean strongAuth, Set<Action> abilities) {}

    record Document(
        long id, String tenant, String owner, boolean deleted) {}

    record Decision(
        boolean allowed, String reason, String revision) {

        String label() {
            return (allowed ? "ALLOW" : "DENY")
                + "/" + reason + "@" + revision;
        }
    }

    static Decision decide(
            String revision, Subject subject,
            Document document, Action action) {

        if (!"v1".equals(revision) && !"v2".equals(revision)) {
            return new Decision(false, "UNKNOWN_POLICY", revision);
        }
        if (subject == null || document == null || action == null) {
            return new Decision(false, "INVALID_INPUT", revision);
        }
        if (!subject.active() || document.deleted()) {
            return new Decision(false, "INACTIVE", revision);
        }
        if (!subject.tenant().equals(document.tenant())) {
            return new Decision(false, "TENANT_MISMATCH", revision);
        }
        if (!subject.abilities().contains(action)) {
            return new Decision(false, "MISSING_ACTION", revision);
        }
        if (!subject.id().equals(document.owner())) {
            return new Decision(false, "NOT_OWNER", revision);
        }

        // v2 siết thêm rule cho SHARE; mọi mandatory checks giữ nguyên.
        if ("v2".equals(revision)
                && action == Action.SHARE
                && !subject.strongAuth()) {
            return new Decision(false, "STEP_UP_REQUIRED", revision);
        }

        return new Decision(true, "OWNER", revision);
    }

    static class ReleaseRouter {
        private final String baseline = "v1";
        private final String candidate = "v2";
        private final Set<String> canaryTenants;

        ReleaseRouter(Set<String> selectedTenants) {
            this.canaryTenants = new HashSet<>(selectedTenants);
        }

        String activeFor(String verifiedTenant) {
            return canaryTenants.contains(verifiedTenant)
                ? candidate : baseline;
        }

        Decision enforce(
                Subject subject, Document document, Action action) {
            return decide(
                activeFor(subject.tenant()), subject, document, action);
        }

        // Chạy thử, không bao giờ thay kết quả enforce().
        Decision shadowCandidate(
                Subject subject, Document document, Action action) {
            return decide(candidate, subject, document, action);
        }

        void rollbackCanary() {
            canaryTenants.clear();
        }
    }

    public static void main(String[] args) {
        ReleaseRouter router =
            new ReleaseRouter(Set.of("tenant-canary"));

        Subject aliceA = new Subject(
            "alice", "tenant-a", true, false,
            Set.of(Action.READ, Action.SHARE));
        Subject aliceCanary = new Subject(
            "alice", "tenant-canary", true, false,
            Set.of(Action.READ, Action.SHARE));
        Subject aliceStrong = new Subject(
            "alice", "tenant-canary", true, true,
            Set.of(Action.READ, Action.SHARE));
        Subject bobCanary = new Subject(
            "bob", "tenant-canary", true, true,
            Set.of(Action.READ, Action.SHARE));

        Document docA =
            new Document(42, "tenant-a", "alice", false);
        Document docCanary =
            new Document(43, "tenant-canary", "alice", false);

        System.out.println("A active: "
            + router.activeFor(aliceA.tenant()));
        System.out.println("A SHARE: "
            + router.enforce(aliceA, docA, Action.SHARE).label());
        System.out.println("Canary active: "
            + router.activeFor(aliceCanary.tenant()));
        System.out.println("Canary SHARE: "
            + router.enforce(
                aliceCanary, docCanary, Action.SHARE).label());
        System.out.println("Canary READ: "
            + router.enforce(
                aliceCanary, docCanary, Action.READ).label());

        // Shadow so sánh, không can thiệp vào thực thi.
        System.out.println("Shadow baseline SHARE: "
            + decide("v1", aliceCanary, docCanary,
                Action.SHARE).label());
        System.out.println("Shadow candidate SHARE: "
            + router.shadowCandidate(
                aliceCanary, docCanary, Action.SHARE).label());

        System.out.println("Canary SHARE after MFA: "
            + router.enforce(
                aliceStrong, docCanary, Action.SHARE).label());
        System.out.println("Wrong tenant: "
            + decide("v2", aliceA, docCanary,
                Action.READ).label());
        System.out.println("Not owner: "
            + router.enforce(
                bobCanary, docCanary, Action.SHARE).label());

        router.rollbackCanary();
        System.out.println("After rollback: "
            + router.enforce(
                aliceCanary, docCanary, Action.SHARE).label());
        System.out.println("Unknown revision: "
            + decide("v99", aliceCanary, docCanary,
                Action.READ).label());
    }
}
```

Biên dịch/chạy bằng JDK 17 trở lên:

```bash
javac PolicyReleaseDemo.java
java PolicyReleaseDemo
```

Stdout chính xác:

```text
A active: v1
A SHARE: ALLOW/OWNER@v1
Canary active: v2
Canary SHARE: DENY/STEP_UP_REQUIRED@v2
Canary READ: ALLOW/OWNER@v2
Shadow baseline SHARE: ALLOW/OWNER@v1
Shadow candidate SHARE: DENY/STEP_UP_REQUIRED@v2
Canary SHARE after MFA: ALLOW/OWNER@v2
Wrong tenant: DENY/TENANT_MISMATCH@v2
Not owner: DENY/NOT_OWNER@v2
After rollback: ALLOW/OWNER@v1
Unknown revision: DENY/UNKNOWN_POLICY@v99
```

**Giải thích:**

- Tenant thường tiếp tục dùng v1 và chủ sở hữu SHARE được.
- Tenant canary dùng v2 và SHARE bị từ chối nếu chưa có MFA mạnh; READ không bị ảnh hưởng.
- Shadow cho thấy v1 ALLOW nhưng v2 DENY; trong SHADOW thật chỉ v1 được thực thi.
- Có MFA → v2 cho phép SHARE; ngoài tenant hoặc không phải owner → deny.
- Sau rollback, canary trở về v1 và SHARE không MFA lại ALLOW. **Chính điều này thể hiện lý do phải phê duyệt rollback target**, không xem rollback là luôn an toàn.
- Unknown revision mặc định DENY.

**Giới hạn demo:** allowlist nằm trong bộ nhớ, `strongAuth`/tenant/abilities là fixtures tin cậy do chương trình tự tạo. Không có JWT verification, distributed rollout, digest, policy signature, database, transaction, audit event, cache invalidation hay concurrency. Trong production, release router chỉ nhận tenant đã xác minh; chính sách phải giữ guardrail đang có hiệu lực, và rollback phải được authorization control plane phê duyệt.

## 18. Kiểm thử bắt buộc trước khi rollout

### 18.1. Unit tests: chính sách không thay đổi ngoài phạm vi

Lập bảng decisions theo subject, tenant, resource, action và context:

| Trường hợp | v1 | v2 dự kiến | Ý nghĩa |
| --- | --- | --- | --- |
| Owner SHARE, chưa MFA | ALLOW | DENY | Siết quyền có chủ đích |
| Owner SHARE, có MFA hợp lệ | ALLOW | ALLOW | Không chặn người đủ điều kiện |
| Owner READ | ALLOW | ALLOW | Giữ hoạt động đọc |
| Non-owner SHARE | DENY | DENY | Không mở rộng quyền |
| Cross-tenant READ | DENY | DENY | Bất biến an toàn |
| Resource deleted | DENY | DENY | Bất biến an toàn |
| Account suspended | DENY | DENY | Bất biến an toàn |
| Unknown action/schema | DENY | DENY | Default deny |
| Chưa xác minh policy artifact | DENY | DENY | Không dùng revision không tin cậy |
| Membership đã bị revoke | DENY | DENY | Dữ liệu quyền vẫn được tôn trọng |

Đây là **decision table cho ví dụ v1/v2**, không phải mọi hệ thống đều bắt owner có READ/SHARE như vậy.

### 18.2. Differential tests: một thay đổi có chủ đích, không mười thay đổi ngẫu nhiên

Chạy v1/v2 trên cùng fixtures, tính:

```text
delta = compare(
    baselineDecision(subject, resource, action, context),
    candidateDecision(subject, resource, action, context)
)
```

Phân loại delta thành expected/unexpected. Trường hợp nới quyền bất ngờ (v1 DENY, v2 ALLOW) nên chặn release trước canary trừ khi có approval rõ và test bảo vệ IDOR/cross-tenant.

Không chỉ so sánh tổng tỉ lệ ALLOW. Cần phân chia theo action, resource class, tenant boundary, sensitive data và role. Một khác biệt 1/1000 ở lệnh `DELETE_INVOICE` có thể nguy hiểm hơn 100 khác biệt ở nút UI vô hại.

### 18.3. Integration tests: xác minh kết quả ngay tại PEP

Chỉ test `PolicyEngine.evaluate(...)` chưa đủ. Cần:

- `@EnableMethodSecurity` thực sự hoạt động.
- Lời gọi đi qua Spring bean/proxy; self-invocation không bypass.
- `SecurityFilterChain` được áp dụng ở các route đúng.
- `AuthorizationManager` trả deny đúng, response không chứa dữ liệu.
- Service/repository không gây side effect khi DENY.
- Tenant/owner/ACL lấy từ DB, không từ input khai báo.
- Shadow không thực thi kết quả candidate.
- Canary thực thi candidate **chỉ** với cohort đã xác minh.
- Rollback trả lại revision đúng và invalidate caches.
- Job/queue/batch/export cũng bị PEP/domain policy bảo vệ.
- Revoke role/share ở DB có hiệu lực ngay theo SLA.
- Application nhiều version không đọc sai schema attributes.

Một test fragment Spring MVC có thể là:

```java
mockMvc.perform(post("/api/documents/{id}/share", 42L)
        .with(user("alice").authorities(
            new SimpleGrantedAuthority("document:share"))))
    .andExpect(status().isForbidden());
```

Đoạn này là **fragment**, cần `MockMvc`, static imports, security test dependency, authentication assurance fixtures, database/share policy và mapping HTTP phù hợp. Nếu v2 yêu cầu MFA và fixture không có, 403 có thể là kỳ vọng; với OAuth2/JWT thật, phải xây principal có assurance claims đúng, không chỉ `@WithMockUser`. Điều quan trọng là assert việc tạo share grant **không xảy ra** khi policy deny.

### 18.4. Failure-injection và rollout/rollback drills

| Sự cố giả lập | Kết quả an toàn phải chứng minh |
| --- | --- |
| Candidate bundle không đúng digest | Không kích hoạt |
| Candidate schema không tương thích app | Không kích hoạt/không xử lý protected action |
| Control plane không phản hồi lúc startup | Không tự cấp quyền khi chưa có policy hợp lệ |
| PDP chết sau khi đã chạy | Dùng verified/fresh policy theo budget hoặc deny |
| Membership/ACL dữ liệu quá cũ | Deny affected operation |
| Một PEP vẫn dùng v1 sau rollout | Theo dõi/cô lập và bảo đảm mandatory guardrails |
| Revoke quyền trong lúc cache nóng | Không có stale ALLOW vượt SLA |
| Candidate v2 vô tình nới quyền READ | Stop ramp, deny, điều tra data exposure |
| Rollback pointer đổi nhưng cache còn candidate | Không lẫn revision và kết quả |
| Rollback target không tương thích schema | Chặn rollback, thực hiện forward fix |
| Request đã bắt đầu trước revoke/release | Hành vi phù hợp transaction consistency đã thiết kế |
| Release config do user sửa từ API | Bị từ chối; control-plane RBAC độc lập |
| Replay release epoch cũ | Không chấp nhận stale config vượt min revision |
| Rollback sau emergency fix | Không khôi phục lỗ hổng đã được vá |

### 18.5. Test concurrency

- Hai operator đồng thời thay release stage → CAS/version ngăn lost update.
- Hai node đọc manifest ở epoch khác nhau → đo propagation bound và hướng xử lý.
- Một request có thể gọi hai service; kiểm tra consistency theo request/release snapshot khi cần.
- Membership bị revoke giữa pre-check và DB update → thử transaction/conditional mutation.
- Candidate vừa đổi threshold từ 5% sang 25% → các tenant cũ vẫn giữ route nếu dùng stable bucket.
- Rollback khi job đang xử lý → xác định điều kiện thực thi và idempotency.
- Nhiều lần nhấn nút rollback → không tăng epoch/rơi vào trạng thái lạ mà không có policy.

## 19. Phương án ứng phó sự cố: một kịch bản cụ thể

**Tình huống:** rollout v2 bổ sung quyền READ cho một loại tài liệu nội bộ. Sau khi canary lên 5%, metric phát hiện `DENY→ALLOW` bất thường trên một tenant không phải owner.

Phản ứng nên theo thứ tự:

1. **Dừng rollout** và không nâng ngưỡng từ 5% lên 25%.
2. **Xác định phạm vi**: policy revision, release epoch, actions, cohort, PEP đang chạy.
3. **Giảm rủi ro ngay** bằng emergency deny hoặc cô lập endpoint/tenant liên quan, không đợi phân tích hoàn chỉnh mới chặn đường cấp quyền sai.
4. **Chuyển về approved safe revision** nếu baseline thật sự vẫn an toàn và tương thích; nếu không, phát hành restrictive hotfix.
5. **Xác minh ở PEP** rằng request cross-tenant/non-owner đã bị từ chối, không chỉ xem dashboard của PAP.
6. **Thu hồi grants/tokens/exports** đã phát do chính sách sai khi có thể; cân nhắc presigned URLs hoặc dữ liệu đã rời khỏi hệ thống.
7. **Đối soát audit** để xác định có ai đã thực sự đọc hoặc sửa tài nguyên trái quyền.
8. **Viết regression test** cho chính cặp actor/resource/action/context gây lỗi.
9. **Review root cause**: input thiếu tenant, rule OR sai, cache key không có tenant, version mismatch hay approval thiếu.
10. **Phát hành bản sửa mới** qua pipeline với thêm guardrail/test, không sửa v2 bất biến tại chỗ.

**Điểm thực tế quan trọng:** rollback quyết định truy cập **trong tương lai**; nó không lấy lại được một file đã bị download hoặc tự xóa một bản ghi đã được tạo bởi quyền cấp sai. Incident response phải bao gồm tác động dữ liệu, không chỉ làm dashboard xanh lại.

## 20. Những sai lầm phổ biến

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Chỉ version Java app, không version policy | Không biết rule nào đã cấp quyền | Policy revision + digest + release epoch riêng |
| Sửa v2 tại chỗ | Audit/rollback không tái lập | Immutable artifacts, tạo v3/hotfix mới |
| Để client chọn `?policy=v1` | Bypass candidate/guardrail | Trusted release router |
| Coi policy publish thành công là mọi PEP đã active | Quyết định không nhất quán | Đo effective revision tại PEP |
| Chạy candidate trong shadow rồi trả kết quả v2 | Shadow vô tình biến thành enforcement | Baseline vẫn authoritative |
| Shadow gây side effects thật | Dữ liệu/quota/notifications bị thay đổi | Pure evaluation, side-effect isolation |
| Random phiên bản mỗi request | Quyền lúc có lúc không | Stable cohort/release snapshot |
| Canary theo tenant header chưa verify | Client tự chọn đường dễ dãi | Verify tenant membership trước routing |
| So sánh tỉ lệ DENY chung | Bỏ sót lỗ hổng DENY→ALLOW nhạy cảm | Differential metrics theo action/resource |
| Không kiểm tra schema compatibility | Missing attributes bị hiểu là true | Validate schema, fail closed |
| Chỉ test policy bean | PEP/service có thể bypass | Integration tests qua Spring security/proxy/DB |
| Khi PDP lỗi trả `permitAll` | Fail-open | Deny/5xx an toàn theo budget |
| Coi last-known-good luôn an toàn | Revoked data/cache vẫn cho phép | Freshness checks cho policy và data |
| Cache decision không có version | Dùng lại ALLOW từ v1 khi v2 đã deny | Cache key/invalidation theo revision và ACL epoch |
| Canary một policy nới quyền mà bỏ mandatory tenant check | Rò dữ liệu trong cohort | Guardrail chung, test BOLA |
| Rollback về revision có lỗi đã vá | Khôi phục lỗ hổng | Approved safe rollback targets/hotfix |
| Nghĩ rollback policy đảo ngược SQL write cũ | Dữ liệu vẫn bị thay đổi | Incident response và compensating actions |
| Quyền release dùng chung với user API | Escalation vào control plane | RBAC/approval/audit tách biệt |
| Không có version ở audit event | Khó điều tra sự cố | Log policy/release/epoch/decision |
| Log raw JWT hoặc full resource | Lộ thông tin nhạy cảm | Redaction, data minimization |
| Giữ PEP cũ chạy ngoài freshness budget | Truy cập trái quyền sau revoke | Propagation SLO, quarantine/deny |
| Bỏ qua async/queue/export routes | Có đường gọi không áp policy mới | Policy ở service/data layer |
| Đặt `@PostAuthorize` sau write rồi tưởng deny rollback dữ liệu | Side effect có thể đã commit | Pre-authorization và scoped mutation |
| Chỉ quan sát availability, không quan sát correctness | ALLOW sai không tạo lỗi 5xx | Security outcome/delta metrics |

## 21. Checklist phát hành một thay đổi chính sách động

Trước khi chuyển policy candidate vào production:

1. **Policy ID/revision bất biến đã rõ chưa?** Có digest và nguồn build có thể tái tạo không?
2. **Tác động là siết hay nới quyền?** Đã phân loại rủi ro theo resource/action chưa?
3. **Subject/resource/context lấy từ nguồn nào?** Có thuộc tính client có thể giả mạo không?
4. **Bất biến tenant/owner/account status còn được bảo vệ không?**
5. **Schema version hợp lệ với tất cả app/PEP đang chạy không?**
6. **Approval và người chịu trách nhiệm đầy đủ chưa?**
7. **Shadow có thật sự chỉ quan sát không?** Không thay enforce result hoặc side effects.
8. **Các delta DENY→ALLOW đã được review chưa?** Đặc biệt READ/EXPORT/DELETE/SHARE.
9. **Canary cohort được chọn ổn định từ verified IDs chưa?**
10. **Có kế hoạch tăng 1% → 5% → ... và tiêu chí dừng không?**
11. **Metrics có policyRevision/releaseEpoch tại PEP không?**
12. **Data freshness/ACL membership/revocation budget đã đo chưa?**
13. **Cache có được invalidate khi version/ACL/role đổi không?**
14. **Rollback target vẫn đáp ứng security guardrails hiện tại không?**
15. **Control plane có CAS/audit/RBAC không?**
16. **Các request/transaction đang chạy khi switch xử lý thế nào?**
17. **Database writes đã có tenant/resource/permission constraints chưa?**
18. **Các luồng async, queue, export, storage và admin có cùng policy không?**
19. **Failure-injection đã test mất PDP, invalid bundle và data stale chưa?**
20. **Có incident playbook cho việc dữ liệu đã bị truy cập hoặc thay đổi không?**

**Kết luận:** Quản trị chính sách động tốt không chỉ có nút “bật v2”. Cần một **policy artifact bất biến và có thể kiểm chứng**, **release routing đáng tin**, **shadow không ảnh hưởng quyền thật**, **canary ổn định**, **theo dõi quyết định tại PEP**, **cache/data freshness** và **rollback chỉ về revision vẫn an toàn**. Spring Security cung cấp hạ tầng enforcement qua `AuthorizationManager` và method/HTTP security; ứng dụng phải quản trị chính sách, phiên bản, triển khai và ứng phó sự cố như một phần của kiến trúc bảo mật.

## Tài liệu tham khảo

- [Spring Security — Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html): `AuthorizationManager`, Authentication và cơ chế chặn/cho phép.
- [Spring Security API — AuthorizationManager (7.x)](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/AuthorizationManager.html): chữ ký `authorize(...)` và contract trả decision.
- [Spring Security API — AuthorizationManager (6.5)](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/AuthorizationManager.html): phân biệt `check(...)` và `authorize(...)`.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize` và policy beans.
- [Spring Security — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): PEP ở HTTP và `AuthorizationManager<RequestAuthorizationContext>`.
- [OWASP — Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): deny by default, least privilege, kiểm tra mọi request.
- [OWASP — Authorization Policy and Data Distribution Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Policy_And_Data_Distribution_Cheat_Sheet.html): versioned policies, rollout, freshness, revocation, last-known-good, fail closed.
- [OWASP — Authorization Patterns Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Patterns_Cheat_Sheet.html): PEP/PDP/PIP/PAP và trust boundaries.
- [OWASP — Insecure Direct Object Reference Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Insecure_Direct_Object_Reference_Prevention_Cheat_Sheet.html): object-level authorization cần thiết xuyên mọi phiên bản.

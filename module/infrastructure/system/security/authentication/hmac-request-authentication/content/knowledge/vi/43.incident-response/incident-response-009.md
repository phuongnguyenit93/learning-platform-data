# Thông báo sự cố trong hệ thống xác thực HTTP request bằng HMAC

## 1. Vì sao thông báo sự cố là một phần của bảo mật HMAC?

Module **SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION** thiết kế xác thực HTTP request bằng **HMAC với shared secret** và **canonical request** ràng buộc method, URI, header hoặc body theo hợp đồng ký. Để bảo vệ endpoint thực tế, verifier còn kiểm tra **timestamp và nonce chống replay**, trạng thái key trong quá trình rotation, cách gateway/proxy chuyển tiếp request và sự phân biệt giữa **authentication** với **authorization**.

Trong chương **Incident response**, bài **Thông báo sự cố** trả lời câu hỏi: khi một hoặc nhiều thành phần trên có vấn đề, tổ chức phải **thông báo cho ai, khi nào, bằng nội dung nào, qua kênh nào, và dựa trên bằng chứng nào** để người nhận hành động đúng mà không làm lộ thêm bí mật?

Một sự cố HMAC có thể là:

- Secret của đối tác bị nghi lộ hoặc đã xác nhận bị lộ; chữ ký có nguy cơ bị tạo giả.
- Kho lưu nonce/replay protection bị lỗi; request hợp lệ bị từ chối, hoặc nguy hiểm hơn, có khả năng replay được chấp nhận.
- Lỗi canonicalization sau khi cập nhật proxy/gateway: request được ký đúng theo hợp đồng nhưng server trả 401 hàng loạt.
- Key rotation thất bại: client đã chuyển sang key mới nhưng một số replica chưa nhận, hoặc key đã thu hồi vẫn được chấp nhận.
- Tăng đột biến số MAC không khớp, timestamp bị từ chối hoặc nonce trùng; chưa rõ do client sai, bot hay tấn công.
- Một route không áp dụng HMAC filter như dự kiến, hoặc tầng authorization chấp nhận thao tác dù client không đủ quyền.

Các tình huống này khác nhau về **nguy cơ dữ liệu, ảnh hưởng khách hàng và hành động khắc phục**, nên không thể dùng cùng một câu “HMAC đang lỗi” cho mọi người nhận.

**Kết quả học tập:** người học sẽ xây được quy trình thông báo theo mức độ và độ tin cậy của bằng chứng, xác định vai trò chịu trách nhiệm, sử dụng mẫu thông báo an toàn, hỗ trợ đối tác rotate key, theo dõi cập nhật/khôi phục, và kiểm thử quy trình liên lạc bằng tabletop exercise.

> Thông báo là **một hoạt động của incident response**, không thay thế cô lập, thu hồi credential, chặn replay, sửa lỗi verifier hoặc kiểm tra quyền. Mục tiêu không phải gửi càng nhiều càng tốt mà là gửi **đúng thông tin đã được xác minh, đủ để người nhận ra quyết định**, qua kênh phù hợp.

## 2. Phân biệt sự kiện, cảnh báo, sự cố và thông báo

| Khái niệm | Ý nghĩa | Ví dụ trong HMAC |
|---|---|---|
| **Security event** | Một kết quả hệ thống quan sát được | `signature_invalid` tăng tại một route |
| **Alert** | Quy tắc monitoring cho rằng sự kiện cần người xem xét | Tỷ lệ 401 sau deploy vượt baseline |
| **Incident** | Sự kiện có tác động hoặc rủi ro đáng kể cần điều phối ứng phó | Nhóm đối tác không gọi được API ký hoặc nghi lộ secret |
| **Internal notification** | Thông tin phối hợp cho người xử lý | On-call báo nguyên nhân đang điều tra, blast radius |
| **Affected-party notification** | Thông báo riêng cho đối tác/người bị tác động | Yêu cầu partner ngừng dùng key cũ, chuyển sang key mới |
| **Public status update** | Thông tin phổ biến rộng về trạng thái dịch vụ | Một số request có chữ ký đang bị từ chối tăng cao |
| **Regulatory/contractual notification** | Thông báo theo nghĩa vụ pháp lý/hợp đồng | Chỉ khi sự kiện và yêu cầu áp dụng đã được xác định |

**Không suy ra “secret đã lộ” từ một đồ thị `401`.** Request 401 có thể do key ID không tồn tại, signature sai, timestamp quá cũ hoặc canonical URI bị proxy rewrite. Ngược lại, một sự cố bypass filter có thể không tạo nhiều 401; cần điều tra bằng route audit, log có kiểm soát và thử nghiệm tái hiện.

### 2.1. Ba cấp độ độ tin cậy của thông tin

Trong mọi thông báo, phân biệt:

1. **Đã quan sát:** dữ kiện được log/metrics/trace hoặc kiểm thử xác minh. Ví dụ: “Từ 09:12 UTC, tỷ lệ request bị từ chối trên route `payments.create` tăng”.
2. **Đang điều tra:** giả thuyết chưa khẳng định. Ví dụ: “Chúng tôi đang kiểm tra thay đổi canonical path ở gateway”.
3. **Đã xác nhận:** kết luận có bằng chứng thích hợp và được incident commander/nhóm bảo mật chấp thuận. Ví dụ: “Gateway cập nhật percent-encoding không tương thích hợp đồng V2”.

Không dùng câu như **“không có dữ liệu nào bị ảnh hưởng”** khi chỉ biết hệ thống đang trả 401. Để kết luận không có truy cập trái phép hoặc không có side effect, phải kiểm tra phạm vi bằng chứng, audit, log giao dịch, hệ thống downstream và khoảng thời gian liên quan.

## 3. Phân loại sự cố trước khi chọn người nhận

Nên định nghĩa severity dựa trên **tác động thực và tiềm năng**, không dựa đơn thuần vào loại HTTP status. Bảng dưới là **khung minh họa**; các tổ chức có thể dùng tên SEV0–SEV3 hoặc P0–P3 khác nhau.

| Nhóm sự cố | Ví dụ | Ưu tiên điều tra | Nội dung thông báo trọng tâm |
|---|---|---|---|
| **Nghi lộ shared secret** | Secret xuất hiện trong log hoặc nơi truy cập không kiểm soát | Rất cao; xác minh và khoanh vùng ngay | Phạm vi credential, trạng thái thu hồi, kênh rotate an toàn |
| **Bypass xác thực** | Protected route có thể vào handler mà không qua HMAC | Rất cao; chặn đường vào trước | Nguy cơ truy cập trái phép, phạm vi route/tenant, kiểm tra side effect |
| **Replay protection không hiệu lực** | Nonce claim không atomic hoặc store bị bypass | Rất cao nếu request có thể lặp | Phạm vi giao dịch và kiểm tra trùng lặp/idempotency |
| **Key revocation chậm** | Replica vẫn chấp nhận key đã revoked | Cao; nhất là khi secret có nguy cơ lộ | Thời điểm hiệu lực, phiên bản key và trạng thái từng replica |
| **Lỗi xác thực diện rộng** | Proxy update khiến nhiều HMAC hợp lệ nhận 401 | Cao về availability; mức bảo mật tùy nguyên nhân | Tuyến dịch vụ, tỷ lệ lỗi, workaround an toàn |
| **Kho key/nonce không sẵn sàng** | Verifier fail closed, request nhận 503 | Cao theo availability | Dịch vụ bị gián đoạn, không bỏ qua xác thực, ETA chưa chắc chắn |
| **Tăng MAC invalid/timestamp failure** | Alert trên một số route | Điều tra trước khi kết luận | Dữ kiện quan sát, độ tin cậy, thay đổi gần đây |
| **Authorization sai sau HMAC** | Key đúng nhưng được vào resource không sở hữu | Cao nếu vượt quyền | Resource/tenant có thể bị ảnh hưởng, điều tra access audit |

Khi một sự cố vừa có **nguy cơ lộ bí mật** vừa có **gián đoạn dịch vụ**, thông báo phải diễn giải hai trục riêng. Ví dụ thu hồi key khẩn cấp có thể làm 401 tăng có chủ đích; đó là tác động của biện pháp giảm thiểu, không có nghĩa root cause là lỗi client.

### 3.1. Mức độ ảnh hưởng cần định lượng

Nêu rõ ở mức dữ liệu đã xác nhận:

- Dịch vụ và route nào bị ảnh hưởng: dùng **route ID/template**, không dùng raw URL chứa thông tin nhạy cảm.
- Khoảng thời gian: **bắt đầu quan sát**, **thời điểm có thể bắt đầu xảy ra** và **thời điểm kết thúc** là ba mốc khác nhau.
- Tỷ lệ/đếm request bị từ chối, latency, số hệ thống đối tác bị ảnh hưởng **chỉ khi có dữ liệu đủ tin cậy**.
- Khả năng có request trái phép hoặc side effect, gồm mức “đang điều tra”, “chưa có bằng chứng”, “đã xác nhận”.
- Hành động an toàn mà người nhận cần làm ngay và **những việc không được làm**.

Ví dụ “khoảng 14% request `payments.create` bị 401 trong 5 phút, theo metrics tại ingress” rõ ràng hơn “nhiều khách hàng lỗi”, nhưng chỉ đưa con số khi dashboard và ranh giới đo đã được xác thực.

## 4. Ai cần được thông báo và qua kênh nào?

| Người nhận | Mục tiêu | Kênh phù hợp | Mức chi tiết |
|---|---|---|---|
| On-call SRE/platform/security | Phản ứng và chặn ảnh hưởng ngay | Pager, kênh incident được bảo vệ, ticket | Kỹ thuật có kiểm soát, runbook, evidence links nội bộ |
| Incident commander (IC) | Điều phối mức độ, quyết định và nhịp cập nhật | Bridge/call, incident timeline | Tình hình, giả thuyết, quyết định, rủi ro |
| Security operations/credential owner | Đánh giá compromise, revoke, forensic | Kênh bảo mật hạn chế quyền | Key metadata đã kiểm chứng, phạm vi bí mật và hành động |
| Product/support/customer success | Trả lời nhất quán, hỗ trợ khách hàng | Internal briefing + approved FAQ | Triệu chứng, impact, workaround đã kiểm chứng |
| Đối tác/API client bị ảnh hưởng | Hành động khắc phục tích hợp và credential | Portal có xác thực, ticket xác minh identity, email công việc đã xác thực | Client/route liên quan, hướng dẫn rotate/test, hỗ trợ |
| Người dùng phổ thông/cộng đồng | Nhận biết gián đoạn và tiến độ | Status page/public channel được phê duyệt | Ảnh hưởng tổng quát, không có secret/chi tiết khai thác |
| Pháp chế, tuân thủ, quản trị rủi ro | Đánh giá nghĩa vụ hợp đồng/pháp luật | Kênh bảo mật riêng, case management | Bằng chứng, dữ liệu liên quan, phạm vi theo quyền |

**Không gửi credential, private diagnostic bundle hoặc danh sách tenant bị ảnh hưởng lên status page công khai.** Thông báo cho một đối tác phải được scoped theo quyền: đối tác A không được biết key ID/tenant ID/giao dịch của đối tác B.

### 4.1. Không phụ thuộc duy nhất vào kênh bị ảnh hưởng

Nếu sự cố là HMAC API không xác thực được request, **đừng chỉ gửi thông báo bằng chính API đang lỗi**. Chuẩn bị kênh out-of-band: portal có xác thực độc lập, hotline đã kiểm chứng, email công việc có xác minh, hệ thống support có audit.

Nếu secret HMAC bị nghi lộ, **không dùng secret đó làm yếu tố duy nhất để xác minh người yêu cầu rotate key**. Cần xác minh quyền sở hữu qua một kênh/identity độc lập (mTLS/SSO/portal MFA hoặc quy trình xác minh đã phê duyệt), tránh attacker lợi dụng sự cố để chiếm tài khoản.

## 5. RACI: ai viết, ai duyệt, ai gửi?

Các vai trò thường gặp:

- **Incident commander:** xác nhận severity, phạm vi và nhịp cập nhật; quyết định escalate.
- **Technical lead/on-call:** xác minh symptom, điều tra verifier/gateway/key/nonce, cung cấp dữ kiện.
- **Security lead:** phê duyệt các phát biểu về compromise, khai thác, revoke và chỉ dẫn tránh lộ thêm.
- **Communications lead/support:** soạn, rà soát người nhận, phát hành thông báo theo kênh được phép.
- **Credential owner/partner manager:** thực hiện liên hệ out-of-band và điều phối cấp key mới.
- **Legal/privacy/compliance:** đánh giá thời hạn và nội dung thông báo khi có nghĩa vụ áp dụng.
- **Scribe/evidence custodian:** ghi timeline, bản thông báo đã phát, danh sách người nhận, approval và sửa đổi.

| Công việc | Người chịu trách nhiệm chính | Người phải phối hợp |
|---|---|---|
| Phát hiện và tạo incident ID | On-call / security monitoring | IC |
| Xác minh phạm vi ban đầu | Technical lead | Security, platform |
| Xác nhận suspected/confirmed compromise | Security lead | IC, credential owner |
| Chốt tác động/khuyến nghị cho client | IC + technical lead | Security, support |
| Duyệt thông báo công khai/đối tác | Communications lead theo policy | IC, security, legal nếu cần |
| Revoke và cấp lại credential | Credential owner có thẩm quyền | Security, partner owner |
| Cập nhật tiến độ định kỳ | Communications lead | IC, technical lead |
| Kết thúc/đóng thông báo | IC | Owner kiểm thử, support |
| RCA/post-incident review | Technical lead + IC | Security, các nhóm liên quan |

Mỗi tổ chức nên quy định **người thay thế** nếu một owner không phản hồi. Không nên để một nhân viên tùy ý công khai nguyên nhân hoặc bằng chứng bảo mật khi chưa được duyệt; ngược lại cũng không để quy trình duyệt làm chậm cảnh báo nội bộ khẩn cấp.

## 6. Trigger và thời điểm gửi thông báo

Không phải alert nào cũng cần public notice. Một cây quyết định minh họa:

~~~mermaid
flowchart TD
    A[Alert / báo cáo sự cố HMAC] --> B[On-call xác minh và tạo incident ID]
    B --> C{Ảnh hưởng/risks đáng kể?}
    C -- Chưa rõ --> D[Điều tra có thời hạn; cập nhật nội bộ]
    C -- Có --> E[IC khai báo incident và severity]
    E --> F[Khoanh vùng; ưu tiên giảm thiểu]
    F --> G{Đối tác/người dùng cần hành động?}
    G -- Có --> H[Soạn notice riêng; xác minh người nhận]
    G -- Không --> I[Status update nếu availability bị tác động]
    H --> J[Security/IC/Legal review theo policy]
    I --> J
    J --> K[Phát hành qua kênh được phép]
    K --> L[Nhịp cập nhật và theo dõi xác nhận]
    L --> M{Đã phục hồi và xác minh?}
    M -- Chưa --> L
    M -- Có --> N[Resolved notice + postmortem follow-up]
~~~

Gửi **thông báo ban đầu** ngay khi đã đủ dữ kiện tối thiểu để người nhận hành động; không cần chờ biết root cause mới nói rằng hệ thống đang bị ảnh hưởng. Nhưng không trình bày một giả thuyết như kết luận.

### 6.1. Nhịp cập nhật minh họa

Ví dụ tổ chức có thể đặt mục tiêu nội bộ:

| Mốc | Ví dụ nhịp làm việc | Nội dung |
|---|---|---|
| Phát hiện/triage | Ngay khi alert được xác minh | Tạo incident ID, liên hệ IC/on-call |
| First notice | Theo severity và playbook, chẳng hạn trong 15–30 phút | Biết gì, chưa biết gì, ai bị ảnh hưởng, hành động |
| Ongoing update | Mỗi 30 hoặc 60 phút nếu mức độ yêu cầu | Thay đổi kể từ lần trước, mitigation, next update |
| Material change | Không đợi đến lịch | Key revoke, workaround thay đổi, phạm vi mở rộng |
| Resolved | Sau khi probe và control đã xác minh | Thời điểm phục hồi, trạng thái còn lại |
| Follow-up/RCA | Theo thời hạn cam kết/hợp đồng | Nguyên nhân, tác động đã xác minh, phòng ngừa |

**Các khoảng thời gian trên chỉ là ví dụ thiết kế runbook**, không phải yêu cầu pháp lý phổ quát. Thời hạn cụ thể do SLO, mức độ, hợp đồng, cơ quan quản lý và chính sách áp dụng quyết định; cần bộ phận pháp chế xác nhận nếu có nghĩa vụ thông báo.

Nếu đã hứa “cập nhật tiếp lúc 10:30 UTC”, phải phát bản cập nhật dù chỉ để xác nhận “chưa có phát hiện mới”. Không tự hứa thời gian khôi phục khi chưa có căn cứ kỹ thuật.

## 7. Các trường tối thiểu của một thông báo

Một notice nên có cấu trúc thống nhất:

| Trường | Ví dụ | Quy tắc an toàn |
|---|---|---|
| Incident ID | `INC-HMAC-2026-011` | Mã nội bộ sinh từ hệ thống, không chứa key/tenant bí mật |
| Severity / stage | `SEV2 / INVESTIGATING` | Không gán “confirmed breach” khi chưa xác minh |
| Timestamps | `2026-11-28T09:12:00Z` | UTC/ISO-8601; phân biệt observed/estimated |
| Affected service/route | `Signed API / payments.create` | Dùng route template, tránh raw query chứa PII |
| Symptom | “Một phần request hợp lệ trả 401” | Chỉ dữ kiện được quan sát |
| Scope | “Chưa xác định đủ số client bị ảnh hưởng” | Không đoán hoặc công khai danh sách tenant |
| Security assessment | “Đang điều tra khả năng truy cập ngoài ý muốn” | Nêu cấp độ bằng chứng |
| Mitigation | “Tạm ngừng rollout gateway; kiểm tra route mapping” | Không chỉ dẫn bypass HMAC |
| Required action | “Giữ nguyên cơ chế ký; liên hệ qua portal hỗ trợ” | Cụ thể và an toàn |
| Next update | `2026-11-28T10:30:00Z` | Cam kết thực hiện được, UTC |
| Contact/support | Kênh chính thức đã công bố | Không yêu cầu gửi secret qua email/chat |
| Owner/approval | Role và case reference nội bộ | Không đưa danh tính/bằng chứng nhạy cảm ra công khai |

Thông báo **bên ngoài** không nên có toàn bộ trường nội bộ (ví dụ điều tra forensics, test exploit, địa chỉ hệ thống lưu secret). Một công ty có thể duy trì hai bản từ cùng nguồn dữ liệu: **internal incident record** đầy đủ và **approved external notice** đã lọc.

### 7.1. Structured incident record minh họa

~~~json
{
  "schema_version": "incident-notice-v1",
  "incident_id": "INC-HMAC-2026-011",
  "stage": "INVESTIGATING",
  "severity": "SEV2",
  "observed_at_utc": "2026-11-28T09:12:00Z",
  "notice_issued_at_utc": "2026-11-28T09:30:00Z",
  "affected_service": "signed-api",
  "affected_route_id": "payments.create",
  "symptom": "Increased authentication failures for some requests",
  "security_impact": "UNDER_INVESTIGATION",
  "mitigation_status": "IN_PROGRESS",
  "client_action": "NO_CREDENTIAL_CHANGE_REQUESTED",
  "next_update_at_utc": "2026-11-28T10:00:00Z"
}
~~~

Đây là **record minh họa bằng dữ liệu giả**. Không lưu full request, secret, MAC, nonce, raw canonical, body hoặc IP của người dùng vào sự kiện thông báo. Nếu cần điều tra theo đối tác, đặt chi tiết đã được kiểm chứng trong hệ thống case/access-controlled riêng; không biến tên đối tác/ID request thành label metric high-cardinality.

## 8. Mẫu thông báo nội bộ khi mới phát hiện

Mẫu dưới nên dùng trong kênh incident có quyền truy cập phù hợp:

~~~text
[INC-HMAC-2026-011] SEV2 — INVESTIGATING

Observed: 2026-11-28 09:12 UTC
Detected by: HMAC auth failure rate alert
Affected: signed-api / route payments.create

CONFIRMED:
- Sau thay đổi gateway, tỷ lệ request trả 401 tăng so với baseline.
- Handler nghiệp vụ không được gọi trong các request 401 đã lấy mẫu.

UNDER INVESTIGATION:
- Có thể có khác biệt canonical public path/query qua gateway.
- Chưa có kết luận về ảnh hưởng dữ liệu hoặc hành vi khai thác.

IMMEDIATE ACTION:
- Tạm dừng rollout gateway theo thay đổi đã được phê duyệt.
- Kiểm tra golden vectors, signed target, key/nonce store health.
- Không tắt HMAC verification hoặc mở rộng timestamp window để chữa 401.

OWNER: Incident Commander / Auth Platform / Security
NEXT UPDATE: 2026-11-28 09:45 UTC
EVIDENCE: link tới incident record có quyền
~~~

Đối với dữ liệu thực, chỉ ghi “handler không được gọi” nếu trace/side-effect audit đã xác nhận và mô tả phạm vi lấy mẫu; không khẳng định toàn hệ thống an toàn chỉ từ một số request thử nghiệm.

### 8.1. Handoff kỹ thuật cần bổ sung gì?

Ngoài thông báo nội bộ ngắn, evidence record có thể ghi:

- Lịch sử cấu hình gateway/reverse proxy trước/sau deployment.
- Tỷ lệ 401/403/503 theo route và reason enum hữu hạn; kiểm tra freshness/signature/replay tách biệt.
- Kết quả golden vector kiểm tra canonical bytes, khác biệt public/internal URI/header/body.
- Tình trạng key store, secret manager, cache policy, key rotation và invalidation.
- Tình trạng nonce store, atomic claim, TTL, số request replay bị từ chối.
- Bằng chứng handler/DB/event downstream có hoặc không có side effect.
- Khoảng thời gian và phạm vi log/trace còn truy cập được; ai có quyền xem.

**Không đưa secret, raw signature, payload giao dịch, nonce hoặc header Authorization vào chat incident**. Nếu cần kiểm thử, dùng secret giả và request fixture cô lập. Bằng chứng nhạy cảm phải ở kho chuyên dụng, mã hóa, giới hạn người xem và thời gian lưu.

## 9. Mẫu thông báo khách hàng/đối tác về gián đoạn HMAC

Một thông báo khách hàng tốt không yêu cầu đối tác tự “chữa” bằng cách bỏ kiểm tra chữ ký.

~~~text
Tiêu đề: Cập nhật sự cố xác thực Signed API — INC-HMAC-2026-011

Chúng tôi đang điều tra tình trạng một số yêu cầu gửi tới Signed API
không được xác thực thành công từ khoảng 09:12 UTC ngày 28/11/2026.

Tác động đã quan sát:
- Một phần request tới chức năng tạo thanh toán có thể nhận HTTP 401.
- Chúng tôi đang xác minh phạm vi các tích hợp bị ảnh hưởng.

Biện pháp đang thực hiện:
- Kiểm tra thay đổi định tuyến qua gateway và độ tương thích
  của hợp đồng ký HMAC.
- Giữ nguyên kiểm soát xác thực và chống replay trong quá trình xử lý.

Hành động đề nghị:
- Tiếp tục ký request đúng hợp đồng hiện hành.
- Không gửi shared secret, chữ ký đầy đủ hay payload nhạy cảm qua hỗ trợ.
- Nếu cần hỗ trợ tích hợp, sử dụng portal hỗ trợ chính thức.

Chúng tôi chưa có kết luận đầy đủ về nguyên nhân.
Bản cập nhật tiếp theo dự kiến lúc 10:00 UTC.
~~~

Đây là mẫu **giả định**. Khi chỉ một nhóm partner chịu tác động, dùng thông báo **scoped** qua kênh đã xác thực; không đưa danh sách đối tác khác vào bản gửi. Nếu có workaround, phải được kỹ thuật và security kiểm chứng; ví dụ retry có giới hạn với **timestamp/nonce mới và chữ ký mới** có thể phù hợp với lỗi nhất thời, nhưng với request tạo giao dịch phải đi cùng **idempotency key** để tránh giao dịch trùng.

### 9.1. Những lời khuyên tuyệt đối không được đưa ra

- “Tạm thời gửi request không cần `X-Signature`.”
- “Bỏ qua lỗi 401 và ghi nhận giao dịch là thành công.”
- “Mở timestamp window lên 24 giờ cho đến khi xử lý xong” mà không đánh giá replay.
- “Tắt nonce check/Redis để tăng tỷ lệ thành công.”
- “Gửi shared secret/HMAC signature đầy đủ cho support để chúng tôi debug.”
- “Dùng key của đối tác khác hoặc endpoint không yêu cầu HMAC.”

Các biện pháp này có thể biến một sự cố availability thành **sự cố bảo mật nghiêm trọng**.

## 10. Mẫu thông báo khi nghi lộ hoặc xác nhận lộ secret

Khi secret bị nghi lộ, thông báo phải đi cùng **hành động containment**. Không nên chờ hoàn tất RCA mới xem xét thu hồi key có nguy cơ cao. Tuy nhiên mức độ khẩn cấp và thao tác revoke thực tế phải theo playbook và bằng chứng.

### 10.1. Thông báo ban đầu cho credential owner (qua kênh được xác minh)

~~~text
Chủ đề: Yêu cầu phối hợp khẩn cấp về credential Signed API
Mã sự cố: INC-HMAC-2026-012
Trạng thái: ĐANG ĐIỀU TRA NGUY CƠ CREDENTIAL BỊ LỘ

Chúng tôi phát hiện một dấu hiệu cần đánh giá an toàn của credential
đang được dùng cho tích hợp Signed API của quý đối tác.
Phạm vi và mức độ ảnh hưởng hiện đang được xác minh.

Hành động tạm thời:
1. Không chia sẻ shared secret, full HMAC signature hoặc bản ghi
   request có dữ liệu nhạy cảm qua email/chat.
2. Truy cập portal quản lý credential bằng kênh đăng nhập chính thức
   hoặc liên hệ đầu mối bảo mật đã đăng ký.
3. Chuẩn bị cập nhật client để dùng key mới theo hướng dẫn
   được gửi trong kênh đã xác thực.

Chúng tôi sẽ xác nhận riêng trạng thái key, kế hoạch chuyển đổi
và thời điểm ngừng chấp nhận key cũ sau khi xác minh quyền nhận.

Bản cập nhật tiếp theo: [thời gian UTC theo runbook].
~~~

**Đây là template, không phải thông báo đã gửi hoặc bằng chứng key thực bị lộ.** Không khẳng định “đã có lạm dụng” nếu mới phát hiện secret xuất hiện ở log test. Nếu có dấu hiệu compromise mạnh, security lead có thể yêu cầu revoke ngay và thông báo về gián đoạn dự kiến.

### 10.2. Thông báo xác nhận thu hồi/rotate key

Thông báo riêng, sau khi xác minh người nhận, cần nêu:

- Key/credential **được xác định bằng tham chiếu an toàn** trong portal đã xác thực; không gửi secret qua email.
- **Trạng thái**: key cũ đã revoke, sắp revoke hay chỉ dừng phát hành? Ghi thời điểm hiệu lực UTC.
- Cách cấp/phân phối key mới qua secret manager/portal có quyền, và cách xác nhận client đã chuyển.
- Hợp đồng ký vẫn áp dụng: method, public URI, signed headers/body, timestamp, nonce, signature profile và key ID.
- Nếu có overlap, nêu rõ **thời hạn và phạm vi được phép**; không hứa overlap cho secret đã xác nhận compromise nếu điều đó trái risk policy.
- Yêu cầu dọn key cũ khỏi configuration, CI/CD secrets, logs, backups được kiểm soát và vô hiệu hóa key ở mọi replica.
- Kênh báo lỗi khi nhận 401 do key đã revoke, và cách kiểm tra ứng dụng vẫn sử dụng key mới.

Ví dụ câu trạng thái chính xác: **“Credential cũ đã bị vô hiệu hóa tại dịch vụ xác thực lúc 10:22 UTC; từ thời điểm đó request được ký bằng key này sẽ bị từ chối theo chính sách.”** Chỉ dùng câu này sau khi kiểm tra các replica/cache thực sự đã áp dụng revoke.

### 10.3. Điều kiện phải báo sớm hơn và escalation

Nếu phát hiện có khả năng một bí mật cho phép giả mạo request, cần **escalate nhóm security/IC ngay**, đánh giá tạm khóa credential, chặn route/tenant liên quan hoặc giới hạn phạm vi hoạt động. Thông báo cho partner bị ảnh hưởng cần được ưu tiên khi họ phải đổi secret/triển khai để tránh rủi ro tiếp diễn.

Nếu có khả năng dữ liệu cá nhân hoặc tài chính bị truy cập trái phép, bổ sung privacy/legal để xác định nghĩa vụ thông báo theo **pháp luật, hợp đồng và khu vực pháp lý áp dụng**. Không tự áp một mốc thời gian pháp lý chung cho mọi thị trường.

## 11. Mẫu thông báo khi nonce store lỗi hoặc replay đáng ngờ

Hai tình huống tưởng giống nhưng **khác tác động**:

| Tình huống | Quan sát | Nội dung cần nói |
|---|---|---|
| **Nonce store unavailable, verifier fail closed** | Request đã ký hợp lệ nhận 503 hoặc lỗi xác minh | “Tạm gián đoạn xác thực”; không nói hệ thống đã nhận replay |
| **Replay control bypass/không atomic** | Có bằng chứng request có MAC và nonce trùng được chấp nhận | “Đang điều tra khả năng xử lý lặp”; kiểm tra giao dịch và side effect |

Thông báo công khai về availability có thể là:

~~~text
Một số request yêu cầu xác thực HMAC hiện không được xử lý
do thành phần chống replay chưa sẵn sàng.
Hệ thống đang từ chối những request không thể xác minh an toàn.

Chúng tôi đang khôi phục khả năng xác minh và kiểm tra
tác động đối với các giao dịch bị gián đoạn.

Không cần tắt timestamp/nonce hoặc thay đổi quy tắc ký của client.
Với thao tác ghi, sử dụng cơ chế idempotency theo hợp đồng API
khi gửi lại sau khi dịch vụ được khôi phục.
~~~

Nếu phát hiện nonce replay thực sự được chấp nhận, **không dùng mẫu trên để che giấu nguy cơ**. Security/IC phải điều tra event, idempotency records, DB writes, published messages, account/tenant scope và khả năng transaction duplication trước khi kết luận về tác động.

### 11.1. Hướng dẫn retry phải đi kèm điều kiện

- Không gửi lại **nguyên xi** request đã có nonce được chấp nhận; đó thường là replay.
- Nếu cần retry, client tính **timestamp và nonce mới**, ký lại canonical request đúng hợp đồng.
- Với endpoint ghi dữ liệu, dùng **idempotency key nghiệp vụ riêng**; anti-replay bằng nonce không thay idempotency.
- Nếu response bị mất sau khi request đã chạy, cần truy vấn trạng thái nghiệp vụ/đối soát theo API, không tự giả định 503 nghĩa là chưa có side effect.
- Giới hạn retry/backoff theo chính sách để không gây overload khi hệ thống chưa phục hồi.

Các hướng dẫn này chỉ đưa cho đối tác khi đã có contract retry/idempotency phù hợp; không khuyên retry mù với thanh toán hoặc thao tác không idempotent.

## 12. Cập nhật điều tra, mitigation, phục hồi và RCA

Một incident notification thường trải qua các **trạng thái giao tiếp**:

~~~text
INVESTIGATING
   → IDENTIFIED (nếu đã xác nhận nguyên nhân)
   → MITIGATING / MONITORING
   → RESOLVED
   → POST_INCIDENT_FOLLOW_UP
~~~

Không nhất thiết tất cả sự cố đều đi qua mọi trạng thái; ví dụ có thể khôi phục trước khi root cause được xác nhận. Trạng thái **RESOLVED** cần mô tả rõ đã phục hồi cái gì, không được tự động đồng nghĩa “không còn nguy cơ bảo mật”.

### 12.1. Mẫu thông báo đang khắc phục

~~~text
[INC-HMAC-2026-011] Update 2 — MITIGATING
Time: 2026-11-28 10:05 UTC

Đã xác nhận:
- Thay đổi xử lý public path tại gateway làm một nhóm
  request HMAC hợp lệ không khớp canonical contract.
- Triệu chứng chính là xác thực 401 đối với route payments.create.

Đã thực hiện:
- Dừng rollout và khôi phục mapping gateway về bản đã kiểm chứng.
- Kiểm tra golden vectors và request qua proxy ở các replica.

Đang thực hiện:
- Theo dõi tỷ lệ 401, kiểm tra side effect và health của nonce store.

Hành động dành cho đối tác:
- Tiếp tục ký theo hợp đồng hiện hành; chưa cần rotate secret.

Next update: 2026-11-28 10:35 UTC.
~~~

Tất cả nguyên nhân và mốc trong mẫu là **giả định**. Ở tình huống thật, “đã xác nhận” phải có bằng chứng và approval tương ứng.

### 12.2. Khi nào được đánh dấu đã phục hồi?

Tối thiểu nên có:

1. Golden vector xác thực HMAC thành công qua **đường đi thực** (ingress → gateway → service) với method/path/query/header/body đã ký.
2. Kiểm tra request đổi signed field, key revoked, timestamp sai và nonce replay vẫn bị từ chối; không tạo side effect.
3. Key store/nonce store ổn định; không còn fail-open hoặc cache stale vi phạm policy.
4. HTTP 401/503 quay về mức bình thường theo baseline hợp lý; không chỉ nhìn một instance.
5. Các route/region/replica và nhóm client quan trọng đều được xác minh, không bỏ sót một đường dẫn fallback.
6. Nếu có nghi ngờ compromise, containment/rotation/revoke và đánh giá tác động đã có kết luận riêng, hoặc công khai rằng điều tra bảo mật vẫn tiếp tục.

Chỉ khi các điều kiện khôi phục phù hợp đạt mới gửi **resolved notice**. Nếu nguyên nhân chưa rõ, viết “dịch vụ đã khôi phục; điều tra root cause tiếp tục” thay vì tự tuyên bố vấn đề đã được giải quyết hoàn toàn.

### 12.3. Mẫu thông báo kết thúc

~~~text
Tiêu đề: Signed API — đã khôi phục khả năng xác thực request
Sự cố: INC-HMAC-2026-011
Phục hồi được xác minh: 2026-11-28 10:40 UTC

Tỷ lệ lỗi xác thực của các route bị ảnh hưởng đã trở lại
mức bình thường theo các kiểm tra qua gateway và service.

Chúng tôi đã xác nhận những kiểm soát bắt buộc còn hoạt động:
signature verification, timestamp/nonce replay rejection,
key lifecycle và authorization.

Không yêu cầu thay đổi shared secret đối với sự cố này
[chỉ giữ câu này khi security lead đã xác minh].

Chúng tôi tiếp tục rà soát phạm vi và sẽ cung cấp báo cáo
sau sự cố qua kênh hỗ trợ chính thức nếu cần.
~~~

Phải kiểm tra mọi câu khẳng định trên dữ kiện thật. Không khẳng định “không có tổn thất/không lộ dữ liệu” chỉ vì 401 đã giảm. RCA được phát hành sau khi xác nhận nguyên nhân, timeline, blast radius, quyết định quan trọng và hành động phòng ngừa.

## 13. Kênh thông báo an toàn: email, portal, status page và webhook

### 13.1. Cấp quyền và xác minh người nhận

**External partner notice** phải đi tới người nhận đã xác minh quyền quản lý credential/tích hợp. Các địa chỉ và kênh liên hệ nên lấy từ registry/portal đã xác thực, không tin địa chỉ do một request HMAC chưa xác thực gửi đến.

Không đính kèm secret mới, private key, full MAC, canonical request nhạy cảm hoặc dump log giao dịch. Kể cả khi gửi email đã mã hóa, vẫn nên yêu cầu nhận secret qua **kênh phân phối credential được thiết kế chuyên dụng**.

**Public notice** dùng mức thông tin cần thiết để người dùng hiểu tình trạng và hành động; không công khai key ID thật, danh sách tài khoản/tenant, cách tái hiện bypass hoặc chi tiết có thể giúp khai thác trong thời gian containment.

### 13.2. Nếu dùng webhook để gửi thông báo

Webhook là một API và bản thân nó cũng cần bảo vệ:

~~~text
incident event (sanitized)
    → approval gate
    → durable outbox
    → recipient mapping đã xác minh
    → HTTPS + sender authentication
    → receiver verifies signature/timestamp/nonce
    → idempotent processing + audit
~~~

Những điểm đặc biệt:

- Nếu webhook được ký bằng **chính shared secret đang nghi lộ**, không được coi chữ ký webhook đó là bảo đảm duy nhất; cần dùng key/kênh độc lập hoặc tạm dừng delivery theo playbook.
- Dùng TLS, giới hạn endpoint, secret management, key rotation và signed payload theo contract webhook.
- Timestamp/nonce của webhook ngăn replay, nhưng **delivery retry** phải có event ID/idempotency semantics; receiver cần xử lý trùng event an toàn.
- Queue/outbox giúp tránh mất sự kiện khi hệ thống gửi tạm unavailable; retry có backoff và giới hạn, không gửi secret qua dead-letter logs.
- Không cho user-provided arbitrary webhook URL quyết định nơi phát dữ liệu incident; phải xác minh/allowlist endpoint và chống SSRF.
- Ghi nhận attempt, delivery result, acknowledgement và lỗi; **phát thành công không đồng nghĩa người nhận đã đọc**.

Một hệ thống gửi sự cố qua webhook phải có kênh thay thế nếu webhook hoặc xác thực HMAC của webhook bị gián đoạn.

## 14. Mẫu dữ liệu và code Java 17 cho thông báo có kiểm soát

Mục đích ví dụ là chứng minh cách **tách dữ kiện nội bộ khỏi payload được phép gửi**, không phải xây đầy đủ hệ thống pager/email/webhook. Mọi trường dùng enum hoặc dữ liệu server sở hữu; request ID/key ID/secret từ input chưa xác thực không xuất hiện.

~~~java
import java.time.Instant;

enum IncidentStage {
    INVESTIGATING, IDENTIFIED, MITIGATING, MONITORING, RESOLVED
}

enum IncidentSeverity {
    SEV1, SEV2, SEV3
}

enum HmacIncidentCategory {
    SUSPECTED_CREDENTIAL_COMPROMISE,
    AUTHENTICATION_FAILURE_SPIKE,
    REPLAY_CONTROL_UNAVAILABLE,
    REPLAY_CONTROL_BYPASS_SUSPECTED,
    KEY_REVOCATION_INCONSISTENT,
    GATEWAY_CANONICAL_MISMATCH
}

enum ExternalImpact {
    UNDER_INVESTIGATION,
    AUTHENTICATION_ERRORS,
    SERVICE_UNAVAILABLE,
    SECURITY_IMPACT_CONFIRMED
}

public record PublicHmacIncidentNotice(
        String incidentId,
        IncidentStage stage,
        IncidentSeverity severity,
        ExternalImpact impact,
        String serviceRouteId,
        Instant observedAt,
        Instant nextUpdateAt) {
    // Chỉ có field được phép ra external channel.
}
~~~

Một builder chỉ cho phép route ID thuộc allowlist **do hệ thống định nghĩa**; không đưa chuỗi `X-Key-Id`, client ID hay raw URI vào notice:

~~~java
import java.time.Instant;
import java.util.Set;

public final class PublicNoticeFactory {
    private static final Set<String> ALLOWED_ROUTES = Set.of(
            "payments.create", "payments.read", "signed-api.general");

    public PublicHmacIncidentNotice create(
            String incidentId, IncidentStage stage,
            IncidentSeverity severity, ExternalImpact impact,
            String approvedRouteId, Instant observedAt,
            Instant nextUpdateAt) {

        if (!ALLOWED_ROUTES.contains(approvedRouteId)) {
            throw new IllegalArgumentException("Route is not public-safe");
        }
        if (incidentId == null
                || !incidentId.matches("INC-HMAC-[0-9]{4}-[0-9]{3,6}")) {
            throw new IllegalArgumentException("Invalid incident ID");
        }
        if (observedAt == null || nextUpdateAt == null
                || nextUpdateAt.isBefore(observedAt)) {
            throw new IllegalArgumentException("Invalid notice timestamps");
        }
        return new PublicHmacIncidentNotice(
                incidentId, stage, severity, impact,
                approvedRouteId, observedAt, nextUpdateAt);
    }
}
~~~

**Giới hạn quan trọng:** cấu trúc data-safe **không tự phê duyệt nội dung hoặc xác minh sự thật**. Việc phát notice vẫn phải đi qua workflow review, giới hạn audience và quyền gửi. Không cho API công khai chọn `SECURITY_IMPACT_CONFIRMED` hoặc đánh dấu `RESOLVED` chỉ bằng một enum trong request; những trạng thái này do IC/security và bằng chứng quyết định.

### 14.1. Phê duyệt trước publish, không phát thẳng từ alert

~~~text
Alert -> Incident created
      -> Evidence attached (private)
      -> Draft notice (safe schema)
      -> IC/Security/Legal approval theo policy
      -> Audience selection from verified registry
      -> Outbox event + versioned notice ID
      -> Delivery + acknowledgement tracking
      -> Scheduled update / correction if facts change
~~~

Một công việc tự động có thể chuẩn bị **draft** hoặc nhắc người duyệt, nhưng không nên tự tuyên bố breach confirmed hay tự yêu cầu partner rotate key chỉ dựa trên một counter 401. Ngược lại, kênh alert nội bộ khẩn cấp có thể tự động phát theo ngưỡng được phê duyệt để kích hoạt người trực.

### 14.2. Một test cho payload không chứa dữ liệu chưa được phép

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import java.time.Instant;
import org.junit.jupiter.api.Test;

class PublicNoticeFactoryTest {
    @Test
    void acceptsOnlyApprovedRouteIds() {
        PublicNoticeFactory factory = new PublicNoticeFactory();
        Instant observed = Instant.parse("2026-11-28T09:12:00Z");
        Instant update = Instant.parse("2026-11-28T10:00:00Z");

        var safeNotice = factory.create(
                "INC-HMAC-2026-011",
                IncidentStage.INVESTIGATING,
                IncidentSeverity.SEV2,
                ExternalImpact.AUTHENTICATION_ERRORS,
                "payments.create", observed, update);

        assertEquals("payments.create", safeNotice.serviceRouteId());

        assertThrows(IllegalArgumentException.class,
                () -> factory.create(
                        "INC-HMAC-2026-011",
                        IncidentStage.INVESTIGATING,
                        IncidentSeverity.SEV2,
                        ExternalImpact.AUTHENTICATION_ERRORS,
                        "/api/payments?secret=do-not-disclose",
                        observed, update));
    }
}
~~~

Test này mới kiểm tra **một quy tắc allowlist**, không thay thế kiểm toán toàn bộ JSON serializer, email template, webhook logs và telemetry. Trong production, còn cần kiểm tra redaction, review workflow, người nhận và dữ liệu cá nhân ở mọi kênh.

## 15. Diễn tập thông báo sự cố bằng tabletop exercise

Tổ chức nên tập trước khi xảy ra compromise thật. Một bài diễn tập có thể dùng kịch bản:

~~~text
T+00  Giám sát phát hiện nhiều HMAC 401 trên signed API.
T+05  On-call phát hiện gateway vừa thay đổi normalize path.
T+10  Một nhóm khác báo secret của partner A xuất hiện trong
      log của môi trường test có quyền truy cập chưa rõ.
T+15  Security chưa biết secret trong log có phải key production.
T+20  Nonce store không hoạt động tại một region, hệ thống 503.
T+25  Một đối tác hỏi: "Chúng tôi có nên tắt chữ ký để retry?"
T+30  IC xác định cần thông báo riêng về credential, đồng thời
      status update chung về availability.
T+45  Key liên quan được thu hồi sau khi xác minh phạm vi.
T+60  Gateway được rollback và kiểm tra golden vectors qua proxy.
T+90  Recovery checks và thông báo cập nhật kết quả.
~~~

Kịch bản là **giả định hoàn toàn**. Mỗi mốc buộc người diễn tập đưa ra quyết định về:

- Phân tách **hai luồng sự cố** nếu một lỗi gateway và nghi lộ secret không có cùng root cause.
- Khi nào thông báo nội bộ, cho đối tác A, status page và pháp chế.
- Ai xác minh rằng key trong log là secret production? Ai được phép revoke?
- Làm thế nào yêu cầu partner nhận key mới **không dùng kênh/secret đã nghi lộ**?
- Cách giữ 503 fail-closed khi nonce store lỗi, không chuyển sang bỏ anti-replay.
- Nội dung câu “đang điều tra” so với “đã xác nhận” ở mỗi lần cập nhật.
- Cách kiểm tra một request cũ bị replay không tạo side effect, và một retry giao dịch dùng idempotency key đúng.
- Tính kịp thời, tính đúng người nhận, dấu vết phê duyệt và các bước sửa thông tin nếu kết luận thay đổi.

### 15.1. Tiêu chí chấm kết quả diễn tập

| Kiểm tra | PASS khi |
|---|---|
| Incident declared | Có incident ID, severity và owner chịu trách nhiệm |
| Audience scoping | Đối tác chỉ nhận dữ liệu của mình; không có secret |
| Channel resilience | Có kênh out-of-band khi HMAC API hoặc webhook lỗi |
| Fact quality | Suspected/confirmed được phân biệt và có bằng chứng |
| Notification cadence | Gửi bản đầu và bản cập nhật theo runbook, kể cả khi chưa rõ nguyên nhân |
| Secure mitigation | Không tắt HMAC/nonce, không mở quyền hoặc gửi secret qua email |
| Key rotation | Có xác minh recipient, revoke policy, test key mới và audit |
| Replay handling | Nonce atomic, fail closed, retry dùng idempotency đúng |
| Recovery verification | Có test qua gateway/replica, authorization và no side effect |
| Post-incident record | Lưu version notice, approval, delivery, timeline và follow-up |

## 16. Các sai lầm phổ biến khi thông báo HMAC incident

**Gọi mọi 401 là tấn công.** 401 có thể do SDK ký sai query/header, client clock lệch hoặc gateway rewrite. Hãy nói “tăng lỗi xác thực” trước khi có bằng chứng compromise.

**Chờ tìm root cause rồi mới thông báo gián đoạn.** Điều này khiến đối tác không biết đang có sự cố và có thể retry liên tục. Gửi first notice với dữ kiện tối thiểu, nêu rõ đang điều tra.

**Khẳng định không lộ dữ liệu khi chưa có kiểm chứng.** Không có metric truy cập trái phép không đồng nghĩa đã chứng minh không có compromise; cần audit và đánh giá ảnh hưởng thực.

**Chia sẻ raw canonical request và full MAC để debug.** Có thể lộ path/query nhạy cảm, nonce, thông tin khách hàng; shared secret tuyệt đối không đưa vào thông báo.

**Thông báo rotate key qua kênh nhận diện bằng chính secret nghi lộ.** Attacker có thể chiếm quy trình cấp mới. Bắt buộc out-of-band verification hoặc kênh identity độc lập.

**Đưa thông tin nội bộ lên status page.** Danh sách key ID, route nội bộ chưa public, chi tiết bypass, log forensics có thể tăng rủi ro bị khai thác.

**Khuyên tắt xác thực để giữ uptime.** Tắt HMAC/nonce hoặc nới cửa sổ timestamp không có kiểm soát có thể biến outage thành compromise.

**Dùng cùng một thông báo cho tất cả partner.** Có thể lộ tenant/key của đối tác khác; scope danh sách người nhận và nội dung theo quyền.

**Không nói rõ thời điểm theo UTC.** Một mốc “lúc 10 giờ” không có timezone dễ làm partner rotate sai thời điểm; phân biệt observed, mitigation effective và fully recovered.

**Không sửa thông báo sai.** Nếu kết luận đổi, gửi bản correction có version/timestamp, nói rõ phần nào thay đổi, không âm thầm ghi đè bản cũ mà mất lịch sử.

**Đánh dấu resolved chỉ vì dashboard 401 giảm.** Cần xác minh route/proxy, key lifecycle, replay, permission và side effect; nghiên cứu bảo mật có thể vẫn tiếp tục sau khi availability khôi phục.

**Đo delivery thành công thay cho nhận biết.** Một email/webhook HTTP 200 không bảo đảm người nhận đã đọc hoặc thực hiện rotate. Khi hành động là bắt buộc, phải theo dõi acknowledgement qua kênh xác thực.

## 17. Checklist vận hành trước, trong và sau sự cố

### 17.1. Trước sự cố

- [ ] Có danh sách owner, on-call, Security, IC, support, legal và người thay thế.
- [ ] Có registry kênh liên hệ đối tác đã xác minh, phân nhóm route/service và phạm vi quyền.
- [ ] Có mẫu notice nội bộ, partner, public, key compromise, mitigation và resolved.
- [ ] Có quy tắc severity, trigger thông báo, cadence và escalation được phê duyệt.
- [ ] Có nơi lưu evidence riêng, quyền truy cập và chính sách retention.
- [ ] Có kênh out-of-band không phụ thuộc vào HMAC API/webhook bị ảnh hưởng.
- [ ] Có sẵn golden vectors và test qua gateway, nonce replay, key revoke và authorization.
- [ ] Có diễn tập tabletop và quy trình xác minh quyền nhận credential mới.

### 17.2. Khi sự cố đang xảy ra

- [ ] Tạo incident ID, timestamp UTC, severity, owner và timeline.
- [ ] Phân biệt observed facts, hypothesis và confirmed impact; không đoán số khách hàng.
- [ ] Ưu tiên containment: revoke/giới hạn access theo policy, giữ fail-closed.
- [ ] Xác định người nhận và kênh có quyền; tránh phát thông tin đối tác khác.
- [ ] Không gửi secret, chữ ký đầy đủ, nonce, raw body/URI nhạy cảm.
- [ ] Nêu việc cần làm và việc **không được làm** (không tắt HMAC/nonce).
- [ ] Có phê duyệt IC/security/legal phù hợp trước external/public notice.
- [ ] Cập nhật vào mốc đã công bố; sửa notice nếu có bằng chứng mới.
- [ ] Ghi nhận version thông báo, người duyệt, người nhận, delivery/acknowledgement.
- [ ] Với credential compromised: xác minh danh tính out-of-band, cấp key mới và xác nhận revoke trên mọi replica.

### 17.3. Sau khi phục hồi

- [ ] Kiểm tra HMAC method/URI/header/body và timestamp/nonce qua proxy thực.
- [ ] Kiểm tra key rotation/revocation, không còn cache stale chấp nhận key cũ.
- [ ] Kiểm tra request bị từ chối không tạo business side effect; đối soát giao dịch nếu có rủi ro replay.
- [ ] Kiểm tra authorization, tenant/resource boundary và route filter coverage.
- [ ] Gửi resolved notice chỉ với kết luận đã xác minh; ghi rõ những điều tra còn mở.
- [ ] Phát hành RCA/follow-up theo phạm vi và nghĩa vụ được xác định.
- [ ] Xác nhận các hành động bắt buộc của đối tác đã được acknowledge, không chỉ gửi email.
- [ ] Cập nhật runbook, mẫu thông báo, kênh dự phòng và tổ chức diễn tập lại.

## 18. Tổng kết

**Thông báo sự cố HMAC** phải cân bằng ba mục tiêu: **kịp thời**, **chính xác** và **không tạo thêm rủi ro**. Một alert nhiều 401 không đủ để kết luận lộ secret; một lỗi nonce store gây 503 không tự đồng nghĩa replay đã được chấp nhận; và một trạng thái “dịch vụ đã khôi phục” không tự chứng minh mọi nguy cơ dữ liệu đã được loại trừ.

Quy trình tốt xác định **ai chịu trách nhiệm**, **ai có quyền nhận**, **điều gì đã được chứng minh**, **hành động an toàn cần làm** và **khi nào sẽ cập nhật tiếp**. Với HMAC, đặc biệt phải giữ ranh giới giữa **key/secret**, **canonical signature verification**, **timestamp/nonce chống replay**, **key rotation/revocation**, **proxy trust** và **authorization**. Thông báo chỉ thực sự có ích khi dẫn người nhận tới hành động đúng mà không yêu cầu họ gửi secret, bỏ HMAC hoặc vô hiệu hóa chống replay để khôi phục dịch vụ.

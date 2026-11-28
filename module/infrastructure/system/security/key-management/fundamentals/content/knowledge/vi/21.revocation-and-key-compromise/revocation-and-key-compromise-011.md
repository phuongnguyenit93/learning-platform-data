# Thông báo sự cố key: truyền đạt đúng rủi ro, đúng đối tượng và đúng thời điểm

> **Chương:** Revocation và compromise  
> **Module:** SECURITY_KEY_MANAGEMENT_FUNDAMENTALS

Một service phát hiện service account đã gọi KMS `Decrypt` bất thường trong đêm. Tại thời điểm đầu, đội Security chưa biết đó là một batch job hợp lệ, tài khoản bị chiếm quyền hay raw key material đã bị đánh cắp. Nếu ngay lập tức gửi email cho toàn bộ khách hàng rằng “toàn bộ khóa mã hóa đã lộ”, tổ chức có thể phát tán thông tin chưa được xác minh, gây hoảng loạn và phá hỏng điều tra. Nhưng nếu chỉ thay khóa, không báo cho các đội vận hành, đối tác nhận chữ ký và những bên phải hành động, hệ thống có thể tiếp tục tin một khóa không an toàn, bỏ lỡ nghĩa vụ thông báo hoặc để người dùng gặp lỗi giải mã mà không có hướng xử lý.

**Thông báo sự cố key** là một quy trình trong **incident response và key management** nhằm chuyển các phát hiện về **nghi ngờ lộ, lạm dụng, mất quyền kiểm soát, sử dụng sai hoặc mất khả năng dùng khóa mật mã** thành thông điệp có trách nhiệm. Quy trình phải xác định **mức độ chắc chắn, phạm vi ảnh hưởng, biện pháp khống chế, ai cần thực hiện hành động, thời hạn theo nghĩa vụ thực tế và cách cập nhật khi có bằng chứng mới**. Thông báo không phải là một email đơn lẻ; đó là chuỗi quyết định và bằng chứng được điều phối trong suốt vòng đời sự cố.

Trong phạm vi **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, bài học đặt hoạt động thông báo vào vòng đời khóa **tạo → cấp phát → lưu trữ → sử dụng → xoay vòng → thu hồi → hủy**. Nó kết nối **mật mã đối xứng, bất đối xứng, chữ ký số, KMS/HSM, envelope encryption, access control, audit và incident response** để giúp một tổ chức bảo vệ khóa và truyền đạt hậu quả khi các biện pháp bảo vệ gặp vấn đề.

Sau bài học, bạn có thể:

- Phân biệt **sự kiện bất thường**, **nghi ngờ compromise**, **compromise được xác nhận**, **mất khả năng truy cập key** và **sự cố dữ liệu**; không đánh đồng chúng.
- Xác định **blast radius** theo key material/version, mục đích Encrypt/Decrypt/Wrap/Sign/MAC/Derive, tenants, services, dữ liệu và các hệ thống phụ thuộc.
- Thiết kế **ma trận thông báo** cho SOC, Incident Commander, key custodian, service owner, ban lãnh đạo, khách hàng, đối tác, CA/PKI, nhà cung cấp và cơ quan có thẩm quyền khi pháp luật/hợp đồng thực tế yêu cầu.
- Tách **thông báo nội bộ khẩn cấp**, **thông tin vận hành**, **thông báo bên ngoài** và **cập nhật hậu sự cố**, với quyền duyệt và kênh bảo mật phù hợp.
- Viết thông điệp nói rõ **điều đã biết, điều chưa biết, tác động có thể xảy ra, biện pháp đã thực hiện, hành động cần làm và thời điểm cập nhật tiếp theo** mà không lộ raw key/secret.
- Phân biệt **rotate/revoke/disable/destroy key** với việc thu hồi DEK/plaintext đã có thể bị sao chép, hoặc xác minh chữ ký đã phát hành.
- Giữ **evidence, audit, timestamps và decision trail** khi gửi thông báo; không để hoạt động công bố phá vỡ containment hoặc chain of custody.
- Xây runbook, checklist, negative tests, tình huống thực tế và ví dụ Java 17 tạo **notification summary đã được giới hạn dữ liệu** để minh họa automation an toàn.

## 1. Thông báo sự cố key là một phần của ứng phó, không phải thao tác phụ

Một sự cố liên quan key có thể ảnh hưởng cả **confidentiality, integrity, authenticity và availability**. Vì vậy một thông điệp tốt không chỉ nói “khóa đang có vấn đề”, mà phải trả lời người nhận có cần **chặn truy cập, cập nhật trust, rotate credential, kiểm tra dữ liệu, khôi phục dịch vụ hay theo dõi một đầu mối điều phối** hay không.

Ví dụ:

| Sự kiện | Tác động tiềm năng | Người nhận cần được điều phối |
|---|---|---|
| Raw AES DEK bị nghi lộ | Có thể mở ciphertext dùng cùng DEK | Data owner, crypto/key owner, service owner, Security, bên chịu ảnh hưởng khi được xác định |
| KEK trong KMS bị lạm dụng qua `Decrypt` API | Có thể lộ các DEK được unwrap dù KEK không export | SOC, IAM/KMS custodian, app teams, data owners |
| Private signing key bị chiếm quyền sử dụng | Chữ ký giả có thể được tạo; cần xem lại trust | PKI/CA, verifier teams, partners, khách hàng chịu ảnh hưởng khi áp dụng |
| HMAC webhook secret bị lộ | Có thể giả mạo message hợp lệ | Producer, consumer, partner integration teams |
| KMS key bị disable/deleted nhầm | Dữ liệu không mở được, gây outage | SRE, DR, key owner, affected services/customers |
| Alias key bị đổi sang key khác không được phép | Decrypt/sign failures hoặc sai trust domain | KMS operator, configuration owner, affected workload |
| Một private key xuất hiện trong log/CI artifact | Có khả năng key material đã bị sao chép | SOC, repo/CI owners, key custodian, audit/incident team |

**Một key event không tự bằng một data breach đã được xác nhận.** Tuy nhiên, cũng không được phủ nhận rủi ro dữ liệu chỉ vì chưa nhìn thấy plaintext trong logs.

### 1.1. Thông báo phục vụ hai mục tiêu

1. **Điều phối kỹ thuật:** kích hoạt đúng người và hành động như containment, revoke grants, kiểm tra KMS logs, rotate, rewrap, reencrypt, thay key của verifier, restore.
2. **Trách nhiệm và niềm tin:** cung cấp thông tin có căn cứ cho các bên cần biết, thực hiện nghĩa vụ thông báo khi có, và tránh các tuyên bố chắc chắn vượt bằng chứng.

Một cuộc họp kỹ thuật có thể cần key IDs và hostnames nội bộ; thông báo cho khách hàng thường nên trình bày tác động thực tế, những gì họ cần làm và nơi nhận hỗ trợ, **không tiết lộ chi tiết làm tăng nguy cơ tấn công**.

### 1.2. Incident timeline và notification timeline là hai đường đồng bộ

```mermaid
flowchart TD
    SIGNAL["Phát hiện key signal / abnormal use"] --> TRIAGE["Triage và xác định độ tin cậy"]
    TRIAGE --> CONTAIN["Containment + bảo toàn evidence"]
    TRIAGE --> INTERNAL["Notify SOC / Incident Commander / key owner"]
    CONTAIN --> IMPACT["Key scope, data impact và affected parties"]
    INTERNAL --> IMPACT
    IMPACT --> DECISION{"Có nghĩa vụ / lý do notify external?"}
    DECISION -->|"Có"| APPROVE["Legal/privacy/security/comms approval"]
    DECISION -->|"Chưa rõ"| MONITOR["Ghi uncertainty, tiếp tục đánh giá và thời hạn review"]
    APPROVE --> EXTERNAL["Notify affected stakeholders qua kênh an toàn"]
    MONITOR --> DECISION
    EXTERNAL --> UPDATES["Cập nhật khi có bằng chứng / hành động mới"]
    UPDATES --> CLOSE["Closure, corrective actions, postmortem"]
```

**Không chờ investigation hoàn tất mới báo người cần containment ngay**, nhưng cũng không suy đoán phạm vi compromise trong thông báo bên ngoài trước khi có căn cứ và thẩm quyền phù hợp.

## 2. Phân biệt event, suspected compromise, confirmed compromise và data incident

Đây là nền tảng tránh thông báo sai mức độ.

| Trạng thái | Định nghĩa làm việc | Ví dụ | Cách diễn đạt |
|---|---|---|---|
| **Security signal** | Một log/sự kiện cần kiểm tra, chưa đủ kết luận | Decrypt volume tăng lúc 02:00 | “Đang xác minh hoạt động bất thường” |
| **Suspected key misuse** | Có chỉ báo không phù hợp policy nhưng chưa chắc key/material bị lộ | KMS principal gọi từ một IP chưa biết | “Nghi có truy cập trái phép; đã hạn chế quyền để kiểm tra” |
| **Confirmed unauthorized key use** | Bằng chứng xác nhận một operation không được phép | Audit cho thấy account bị chiếm đã gọi Unwrap | “Xác nhận một số lần sử dụng khóa trái phép”; chưa tự suy ra plaintext đã rò |
| **Confirmed raw key exposure** | Có bằng chứng raw bytes/key material đã xuất hiện ngoài boundary được phép | Private key lộ trong public artifact | “Xác nhận vật liệu khóa bị lộ”; ảnh hưởng dữ liệu cần đánh giá riêng |
| **Confirmed data exposure** | Có bằng chứng dữ liệu/DEK/plaintext đã bị truy cập/copy ngoài thẩm quyền | Logs/forensics xác nhận xuất DEK và ciphertext | “Xác nhận dữ liệu X bị truy cập” theo bằng chứng |
| **Key availability incident** | Không dùng được key hoặc key recovery path | KEK bị deleted/disabled, decrypt failures | “Gián đoạn khả năng giải mã”; không tự gọi là leak |
| **Resolved/contained** | Đường khai thác được chặn theo phạm vi xác định | Grants đã revoke, workloads cô lập | “Đã ngăn đường truy cập này”; không tự khẳng định data an toàn tuyệt đối |

### 2.1. Những tuyên bố cần tránh

- “**Không có dữ liệu nào bị ảnh hưởng**” khi mới kiểm tra được một KMS log stream.
- “**Khóa đã bị đánh cắp**” chỉ vì một lỗi `AccessDenied` hoặc `InvalidTag`.
- “**Rotation xong, dữ liệu cũ đã hoàn toàn an toàn**” khi attacker có thể giữ raw DEK/KEK/ciphertext.
- “**Không thể xảy ra data breach vì key non-exportable**” dù người tấn công có quyền gọi Decrypt API.
- “**Đã thu hồi toàn bộ dữ liệu**” sau khi revoke key access, trong khi plaintext đã được tải.

### 2.2. Tách kết luận về ba tài sản

Khi tổng hợp bằng chứng, luôn phân biệt:

1. **Key material:** raw DEK, KEK, HMAC secret hoặc private signing/decapsulation key có bị lộ không?
2. **Key usage capability:** IAM principal hoặc KMS/HSM API có bị dùng trái phép không?
3. **Protected data/artifacts:** ciphertext, wrapped DEK, plaintext, chữ ký hoặc MAC có bị tác động không?

Ba trục này có thể khác nhau. Một principal dùng KMS Unwrap trái phép là **key usage compromise** dù KEK không export; nếu principal nhận DEK, đó có thể dẫn tới **data key exposure**. Phạm vi data exposure còn phụ thuộc ciphertext, mục đích và những bản sao có thể đã truy cập.

### 2.3. Khái niệm “đã xác nhận” cần nguồn bằng chứng

Một incident severity label trong ticket không tự là chứng cứ forensic. Cần lưu **nguồn log, thời điểm UTC, request ID, principal, key ID, operations, vùng tin cậy và phương pháp xác minh**. Khi chứng cứ còn thiếu, thông báo phải ghi rõ **chưa xác định** thay vì biến thành “không bị ảnh hưởng”.

## 3. Threat model của chính hoạt động thông báo

Thông báo có thể **giảm rủi ro**, nhưng cũng có thể **tạo rủi ro mới** nếu nội dung/kênh bị sai.

| Mối đe dọa | Ví dụ | Cách giảm rủi ro |
|---|---|---|
| **Tiết lộ secret trong notice** | Gửi raw KEK/DEK để đối tác “kiểm tra” | Chỉ gửi key IDs/version, không raw material hoặc ciphertext nhạy cảm |
| **Social engineering giả thông báo** | Attacker gửi email bắt khách nhập secret để “rotate” | Kênh xác thực, domain/portal chính thức, không yêu cầu gửi key/password |
| **Thông báo sai đối tượng** | Email tenant A gửi tới tenant B | Recipient mapping đáng tin, kiểm tra tenant & distribution list |
| **Làm lộ phạm vi hệ thống** | Công bố IP, HSM partition, IAM principal, exploit path | Nội dung external được redaction theo nhu cầu hành động |
| **Tuyên bố sai mức chắc chắn** | “An toàn tuyệt đối” khi còn điều tra | Tách known, unknown, hypotheses và confidence |
| **Gửi quá muộn** | Verifier vẫn chấp nhận signing key đã nghi lộ | Notification triggers theo hành động cần thiết và nghĩa vụ |
| **Gửi quá rộng** | Broadcast thông tin incident Internal cho mọi khách | Affected-party analysis và mức thông tin tối thiểu |
| **Thông báo không cập nhật** | Khách hàng hành động trên key ID đã đổi | Versioned notices, supersession và lịch update |
| **Mất integrity của notice** | Nội dung bị sửa khi truyền | Secure portal, authenticated sender, signed artifacts khi phù hợp |
| **Lộ investigation evidence** | Đính kèm raw audit logs chứa PII/tokens | Sanitized summaries, restricted evidence store |

### 3.1. Người nhận cần biết gì để hành động?

Tập trung vào **impact và next action** thay vì toàn bộ kiến trúc nội bộ:

- Dịch vụ/tính năng nào có thể ảnh hưởng?
- Một lớp dữ liệu, tenant hoặc key purpose nào nằm trong phạm vi đã biết?
- Từ khi nào vấn đề có thể diễn ra, mức chắc chắn và giới hạn phân tích?
- Họ có phải đổi token, rotate integration credential, cập nhật JWKS/trust, xác minh giao dịch hoặc khởi động lại workload không?
- Biện pháp containment đã có tác dụng tới đâu?
- Điểm liên hệ và lần cập nhật tiếp theo là gì?

### 3.2. Bên nhận không cần raw key để xác minh thông báo

Nếu cần đối soát, dùng **key identifier, fingerprint của public key, certificate serial, KMS key resource reference**, thời điểm và ticket ID. Không đưa **private key, secret HMAC, raw DEK/KEK, access token, seed** hoặc plaintext trong email, chat, ticket, status page.

## 4. Phân loại mức độ thông báo theo tác động, không chỉ theo loại key

Một mẫu điều phối có thể dùng các mức **Critical / High / Medium / Low**, nhưng **không gắn cứng một severity duy nhất cho từng thuật toán**. Cùng một KEK event có thể nghiêm trọng hơn nếu nó bọc DEKs của hàng triệu khách hàng, hoặc ít ảnh hưởng hơn nếu chỉ dùng trong test environment.

| Đầu vào | Câu hỏi cần trả lời |
|---|---|
| **Material/control** | Raw key đã lộ, hay chỉ IAM principal bị lạm dụng? |
| **Key purpose** | Encrypt/Decrypt/Wrap/Unwrap/Sign/MAC/KEM/Derive? |
| **Blast radius** | Bao nhiêu DEKs, ciphertexts, tenants, signatures hoặc messages? |
| **Exploitability** | Attacker có ciphertext/wrapped DEKs, quyền KMS, hay chỉ public metadata? |
| **Duration** | Hoạt động bất thường diễn ra trong khoảng nào? |
| **Detectability** | Audit coverage đầy đủ hay có blind spots? |
| **Business impact** | Lộ dữ liệu, giả mạo giao dịch, outage hoặc mất khả năng restore? |
| **Dependency** | Có partners/offline verifiers/third-party consumers cần thay key/trust? |
| **Legal/contractual** | Có nghĩa vụ đánh giá và thông báo theo ngành, nơi xử lý dữ liệu hoặc hợp đồng không? |
| **Current containment** | Đã revoke quyền hoặc chặn traffic chưa? Có residual risk? |

### 4.1. Ma trận minh họa mức ưu tiên

| Tình huống | Mức ưu tiên điều phối minh họa | Lý do |
|---|---|---|
| Production private signing key public trên Internet | **Critical** | Có thể giả mạo chữ ký, cần trust/revocation coordination nhanh |
| Production KMS Decrypt được dùng bởi principal bị chiếm | **Critical/High** | Có thể lộ nhiều DEKs/dữ liệu, cần scope và containment |
| Key deletion làm mất decrypt toàn hệ thống | **Critical** | Availability/DR ảnh hưởng diện rộng |
| KEK rotation alert sai do job được phê duyệt | **Low/False positive sau xác minh** | Không cần external notice nếu không có impact/nghĩa vụ |
| Test key non-production vô tình xuất hiện trong internal log đã giới hạn | **Theo risk assessment** | Phải xét tài sản thật, quyền và môi trường |

Các nhãn trên là **ví dụ**, không thay chính sách phân loại sự cố của tổ chức. Severity phục vụ điều phối kỹ thuật; **nghĩa vụ thông báo bên ngoài không được suy chỉ từ nhãn severity**.

### 4.2. Mức độ chắc chắn độc lập với severity

Một sự cố có thể vừa **Critical** vừa **chưa xác định chính xác số records**. Việc chưa đủ data không phải lý do hạ severity mặc định; nhưng cũng không cho phép tuyên bố các con số chưa có bằng chứng.

## 5. Stakeholder map: thông báo cho ai?

**Không có một danh sách nhận email chung cho mọi key incident.** Hãy xác định người nhận theo **quyền hành động, trách nhiệm data/key ownership và phạm vi ảnh hưởng**.

| Nhóm | Mục đích nhận | Nội dung/chức năng cần thiết |
|---|---|---|
| **SOC/CSIRT** | Triage, điều tra, timeline, containment | Raw event references trong hệ thống evidence được bảo vệ |
| **Incident Commander (IC)** | Điều phối quyết định và nhịp cập nhật | Severity, owner, blockers, next decision gates |
| **KMS/HSM key custodian** | Kiểm tra material/state/grants/rotation | Exact keyRef, provider request IDs, key purpose |
| **IAM/SRE/platform** | Cắt quyền, bảo vệ availability, triển khai key cutover | Principals, operations, rollout/rollback boundaries |
| **Service/data owner** | Khoanh vùng object, decrypt/restore, xử lý nghiệp vụ | Affected services/data scope và hành động |
| **PKI/CA/trust admin** | Revocation/certificate/key distribution | Serial, chain, key IDs, trust update requirements |
| **Legal/privacy/compliance** | Đánh giá nghĩa vụ, retention/legal hold, approved language | Fact chronology, jurisdictions, data categories, impact |
| **Security leadership/management** | Phân bổ nguồn lực/risk acceptance | Business impact, residual risk, containment status |
| **Customer support/communications** | Câu trả lời nhất quán, kênh hỗ trợ | Approved external summary, FAQ, escalation rules |
| **Affected customers/tenants** | Biết tác động và hành động cần thiết | Tính năng/loại dữ liệu ảnh hưởng, steps và contact |
| **Partners/integration consumers** | Rotate secrets, cập nhật trust/public keys và replay handling | Exact integration/version/protocol action |
| **Cloud KMS/PKI providers** | Điều tra service logs, revoke/rotate theo trách nhiệm | Provider case ID, request IDs, timeline an toàn |
| **Authorities/regulators** | Thực hiện nghĩa vụ cụ thể khi có | Nội dung/quy trình do legal/compliance xác định |

### 5.1. Internal first không có nghĩa external luôn phải đợi đến closure

SOC, IC và key owners thường phải được báo **ngay khi signal đạt ngưỡng escalation nội bộ** để có containment. Thông báo khách hàng/đối tác/cơ quan quản lý cần cân nhắc **evidence, nghĩa vụ và approval**, nhưng không nên chờ hậu kiểm đầy đủ nếu hợp đồng hoặc luật yêu cầu thông báo sơ bộ sớm.

### 5.2. Người nhận là danh tính, không phải một chuỗi email tự khai

Nên lấy **tenant contacts, designated security contacts, contractual notice addresses và escalation paths** từ registry đáng tin. Không gửi incident details tới địa chỉ tự khai trong request, đặc biệt khi credential/tenant identity đã bị nghi compromise.

### 5.3. Một principal chịu hai loại trách nhiệm

Một vendor có thể vừa là **KMS provider**, vừa là bên xử lý dữ liệu theo hợp đồng. Thông báo để provider điều tra API logs **khác** thông báo về một data incident theo pháp lý. Ghi rõ **vai trò, phạm vi thông tin và kênh** của từng notice.

## 6. Khi nào cần thông báo: triggers, decision gates và nghĩa vụ thực tế

Định nghĩa **notification trigger** phải đủ sớm để kích hoạt hành động cần thiết, nhưng không biến mọi alert thành một thông cáo đại chúng.

### 6.1. Trigger nội bộ ngay khi phát hiện

Ví dụ những tín hiệu cần escalation nội bộ theo severity:

- Key material nghi xuất hiện trong **public repository, build artifact, email hoặc support ticket**.
- KMS/HSM log có **Decrypt/Unwrap/Sign/GenerateMac** ngoài khung giờ, ngoài principal/region hoặc quota dự kiến.
- Key state đổi thành **Disabled, PendingDeletion, Deleted** mà không có change được phê duyệt.
- Key registry/public signing key bị thay thế, trust anchors hoặc JWKS bị sửa bất thường.
- Nhiều yêu cầu Decrypt thất bại, AEAD tag mismatch có quy luật hoặc ransomware/compromised host đang truy cập encrypted records.
- Hệ thống đối tác báo họ nhận chữ ký/MAC không hợp lệ hoặc bị gửi package chứa sai recipient key.

Thông báo nội bộ không nhất thiết đồng nghĩa **kết luận key đã lộ**. Nội dung có thể ghi **suspected**, triage owner và hành động hạn chế quyền.

### 6.2. Trigger thông báo đối tác hoặc khách hàng

Các tình huống thường cần đánh giá bên ngoài:

- Đối tác cần **ngừng trust key/certificate**, cập nhật public key, JWKS, HMAC secret hoặc key identifier để tránh tiếp tục chấp nhận dữ liệu không đáng tin.
- Khách hàng có nguy cơ **dữ liệu bị truy cập trái phép, thất thoát hoặc không thể phục hồi**, và thông tin đó có ý nghĩa để họ hành động.
- Một KMS/crypto incident gây **gián đoạn dịch vụ** khách hàng cần kế hoạch khôi phục/cách sử dụng khác.
- Nghĩa vụ **pháp lý, hợp đồng, ngành hoặc chính sách** yêu cầu thông báo, kể cả khi điều tra còn tiếp tục.

**Không có thời hạn thông báo chung cho mọi nước, mọi loại sự cố và mọi doanh nghiệp.** Legal/privacy/compliance phải xác minh yêu cầu cụ thể theo **jurisdiction, controller/processor role, contract, data type và thời điểm bắt đầu tính hạn**. Không tự công bố “mọi key compromise phải thông báo trong 72 giờ” như một quy tắc phổ quát.

### 6.3. Ghi rõ các mốc thời gian riêng biệt

| Mốc | Ý nghĩa |
|---|---|
| `eventOccurredAt` | Sự kiện có thể đã xảy ra; có thể chỉ là khoảng ước lượng |
| `detectedAt` | Hệ thống/người đầu tiên nhận biết signal |
| `triagedAt` | Lúc đội chuyên trách xác nhận cần điều tra |
| `incidentDeclaredAt` | Thời điểm tổ chức chính thức mở incident |
| `keyMisuseConfirmedAt` | Bằng chứng xác nhận một operation không được phép |
| `containmentEffectiveAt` | Đường lạm dụng đã bị chặn theo phạm vi xác định |
| `impactAssessedAt` | Lúc có đánh giá ảnh hưởng với phạm vi đã biết |
| `noticeDecisionAt` | Lúc người có thẩm quyền quyết định đối tượng/nội dung |
| `noticeSentAt` | Lúc thông báo thực sự được gửi qua kênh đã chọn |
| `nextUpdateDueAt` | Mốc cập nhật theo cam kết/nhu cầu thực tế |

Timestamps nên có **UTC/offset rõ**, nguồn và độ tin cậy. Không dùng một trường `incidentDate` để đại diện tất cả mốc hoặc tự sửa timestamp để đạt SLA.

### 6.4. Có thể thông báo sơ bộ trước khi biết toàn bộ tác động

Thông điệp giai đoạn đầu nên nói:

> Chúng tôi đang điều tra hoạt động sử dụng khóa bất thường liên quan một thành phần của dịch vụ. Chúng tôi đã hạn chế đường truy cập đang xem xét. Hiện chưa xác định đầy đủ phạm vi dữ liệu có thể chịu ảnh hưởng; chúng tôi sẽ cung cấp thông tin cập nhật qua kênh chính thức khi có kết quả kiểm chứng.

Ví dụ trên **không khẳng định vô căn cứ** dữ liệu an toàn hay đã bị lộ. Trước khi gửi thực tế phải điều chỉnh theo bằng chứng và approval, tránh cung cấp chi tiết kỹ thuật làm tổn hại containment.

## 7. Kênh thông báo: bảo mật, xác thực và khả năng vận hành khi hệ thống bị chiếm

Một cuộc tấn công compromise key có thể đồng thời ảnh hưởng **email account, chat bot, CI runner hoặc dashboard** đang dùng để gửi thông báo. Vì vậy phải có **out-of-band channel** và xác minh danh tính người điều phối.

| Kênh | Phù hợp cho | Lưu ý |
|---|---|---|
| **Pager/on-call system** | Khẩn cấp SOC/SRE/IC | Tránh chứa raw key; có fallback nếu SSO bị ảnh hưởng |
| **Restricted incident room** | Điều phối kỹ thuật và decision log | Thành viên tối thiểu, retention và quyền đọc |
| **Secure evidence repository** | Audit logs, forensic artifacts, KMS request IDs | Không chia sẻ evidence raw qua email công khai |
| **Authenticated customer portal** | Notice chính thức tới tenant liên quan | Tenant-scoped access, lịch sử phiên bản, chống recipient mix-up |
| **Verified security contact email** | Thông báo đối tác/khách theo hợp đồng | Dùng contact registry; có cơ chế xác thực/phishing warning |
| **Status page** | Thông tin availability chung | Không đăng chi tiết secret/key architecture hay kết luận chưa rõ |
| **Provider support case** | KMS/HSM/PKI triage | Kiểm soát evidence, case ID và trách nhiệm provider |
| **Official regulator submission** | Nghĩa vụ pháp lý cụ thể | Legal/compliance xác nhận nội dung, kênh, deadline |
| **Phone/out-of-band escalation** | Khi identity infrastructure bị nghi compromise | Xác minh số/contact qua danh bạ tin cậy, ghi quyết định sau đó |

### 7.1. Không dùng chính secret nghi lộ để chứng thực thông báo

Nếu HMAC webhook key bị nghi lộ, một notification được “xác thực” chỉ bằng **cùng HMAC key đó** không phải chứng cứ đáng tin đối với recipient. Dùng **kênh hoặc trust anchor độc lập**, ví dụ portal đã được xác thực, security contact verified hoặc signing key khác chưa bị nghi compromise.

### 7.2. Chống phishing và giả mạo notice

Thông báo ngoài tổ chức nên:

- Nêu **case/notice reference** có thể xác minh trên portal chính thức.
- Không yêu cầu người nhận **gửi password, private key, secret, raw DEK/KEK** qua email/chat.
- Chỉ dẫn xác minh bằng cách **mở portal qua địa chỉ đã biết**, không đặt niềm tin tuyệt đối vào một link lạ.
- Mô tả cách kiểm tra **public key/certificate fingerprint** khi recipient cần cập nhật trust.
- Đưa ra một đầu mối support đã xác thực; tránh số điện thoại/địa chỉ được đổi tùy tiện từ request của caller.

### 7.3. Kênh và nội dung cần phân tầng

**Internal restricted notice** có thể chứa exact KMS keyRef, principal ID, pod IDs, hashes của forensic artifacts và mitigation commands để người vận hành xử lý. **Customer notice** nên thể hiện phạm vi ảnh hưởng, hành động người nhận và contact; không đưa IAM policy nội bộ, exploit path hoặc raw log nhạy cảm.

### 7.4. Không gửi một thông báo cross-tenant chứa danh sách các tenant khác

Trong SaaS multi-tenant, một notice cho tenant A không nên vô tình liệt kê tenant B, object IDs của B hoặc contact của các khách hàng khác. Chia notices theo recipient scope và kiểm thử **tenant isolation tại pipeline phát hành**.

## 8. Notification content model: một thông báo tối thiểu phải có gì?

Đối với mỗi phiên bản notice, có thể dùng cấu trúc:

| Trường | Nội dung | Lưu ý |
|---|---|---|
| **Notice ID/version** | Định danh bất biến và version thông báo | Cho phép supersede/correct nội dung |
| **Issued at** | Thời điểm phát hành có timezone | Không giả làm event time |
| **Incident reference** | Case ID hoặc reference được phép công bố | Không đưa ticket URL nội bộ cho bên ngoài |
| **Audience** | Nhóm người nhận, tenant/partner đã xác định | Không tin audience tự khai |
| **Status/confidence** | Investigating, Confirmed, Contained, Monitoring | Tách sự kiện đã xác nhận khỏi giả thuyết |
| **Affected scope** | Dịch vụ, chức năng, nhóm dữ liệu hoặc giao thức | Chỉ nói trong phạm vi đã kiểm chứng |
| **Impact** | Điều gì có thể/xác nhận đã xảy ra | Rõ confidentiality/integrity/availability |
| **Actions taken** | Revoke grants, rotate key, block service, restore | Ghi những gì thật sự hoàn tất |
| **Recipient actions** | Rotate secret, update trust, monitor activity, không hành động | Có steps, key versions và deadline khi thích hợp |
| **Unknowns** | Số records, thời gian, khả năng sao chép DEK/plaintext còn điều tra | Không thay bằng “không có” |
| **Next update** | Cửa sổ cập nhật/đầu mối được phê duyệt | Giữ cam kết hoặc cập nhật nếu thay đổi |
| **Approval/provenance** | Người phê duyệt/nội dung đã duyệt ở nội bộ | Không nhất thiết lộ danh tính nội bộ cho khách |

### 8.1. Dùng ngôn ngữ về khả năng, không đánh đồng kết luận

| Bằng chứng hiện có | Cách nói phù hợp | Tránh |
|---|---|---|
| KMS log có `Decrypt` trái phép | “Xác nhận phép sử dụng khóa trái phép qua KMS” | “Raw KEK đã bị đánh cắp” nếu chưa có chứng cứ |
| Raw private key xuất hiện trong public artifact | “Vật liệu private key đã bị lộ ngoài phạm vi kiểm soát” | “Chắc chắn attacker đã đọc mọi dữ liệu” |
| Đã revoke IAM grant | “Đã chặn quyền truy cập này tới KMS” | “Mọi bản DEK/plaintext đã bị thu hồi” |
| DEK bị lộ, có ciphertext liên quan | “Dữ liệu mã hóa liên quan có nguy cơ bị giải mã” | “Chỉ cần rotate KEK là khắc phục hoàn toàn” |
| Chưa quét xong backup | “Đang xác định các bản lưu lịch sử có thể chịu ảnh hưởng” | “Không còn bản sao nào” |

### 8.2. Không dùng chỉ số chưa kiểm chứng để trấn an

Một câu như “chỉ có 0,01% users bị ảnh hưởng” phải có nguồn dữ liệu, mẫu số, khoảng thời gian và kiểm tra cross-tenant. Nếu scope còn chưa rõ, mô tả **phạm vi đã xác minh và phần đang điều tra** thay vì đưa con số có vẻ chính xác.

### 8.3. Công bố không đồng nghĩa công khai mọi bằng chứng

Một số bằng chứng có thể chứa PII, audit identities, secret remnants hoặc chi tiết khai thác. Khách hàng và cơ quan có thẩm quyền có thể cần thông tin khác nhau theo luật/hợp đồng; việc chia sẻ raw forensic evidence phải theo **secure disclosure process**, không đính kèm toàn bộ log vào notice chung.

## 9. Chính sách phiên bản hóa notice: preliminary → confirmed → follow-up → closure

Thông báo nên có trạng thái thay đổi theo bằng chứng, tránh sửa lặng lẽ một bài viết rồi không ai biết.

```mermaid
stateDiagram-v2
    [*] --> Draft: Security incident mở
    Draft --> Reviewed: Scope và legal/comms review
    Reviewed --> Preliminary: Notice 1 gửi nếu cần
    Preliminary --> Updated: Evidence mới hoặc action thay đổi
    Updated --> Updated: Tiếp tục review và phát hành version mới
    Preliminary --> Corrected: Phát hiện thông tin cũ sai
    Updated --> Corrected: Correction/supersede
    Corrected --> Updated: Phát hành notice đúng
    Updated --> Closed: Khống chế, nghĩa vụ và follow-up đạt
    Closed --> Reopened: Có bằng chứng mới
    Reopened --> Reviewed: Reassess scope/notification
```

### 9.1. Không tự ghi đè lịch sử

Mỗi notice nên có:

- `noticeId` ổn định, `noticeVersion` tăng, `supersedesVersion` nếu cần.
- **Nội dung đã gửi, audience, kênh, issuedAt và delivery result**.
- Approval reference và **thay đổi so với bản trước**.
- Status của incident tại thời điểm gửi, không sửa retrospective không dấu vết.

Để đáp ứng integrity, có thể lưu **hash/signed digest của nội dung notice** trong hệ thống audit phù hợp. Không dùng hash của raw low-entropy secret làm evidence công khai.

### 9.2. Thông báo correction

Nếu trước đó nói “chỉ service A”, sau điều tra phát hiện thêm service B, **không chỉ sửa text trang web mà không lưu bản cũ**. Phát hành notice mới:

> Bản cập nhật này mở rộng phạm vi sự cố so với thông báo trước: chúng tôi xác nhận thêm service B có liên quan. Các biện pháp đã thực hiện với service A vẫn giữ hiệu lực; các bước kiểm tra đối với B đang được triển khai. Phạm vi dữ liệu cụ thể tiếp tục được xác minh.

Phải nói rõ **điều gì thay đổi**, nguyên nhân dựa trên bằng chứng mới và hành động người nhận cần thay đổi nếu có.

### 9.3. Closure không có nghĩa “không còn rủi ro”

Một incident có thể đóng về mặt xử lý khi containment, mitigation, notification obligations và handoff hoàn tất, nhưng vẫn có **residual risk**: attacker có thể đã sao chép plaintext/DEK, một số bản ghi không thể phục hồi hoặc trust artifacts cũ cần review. Notice closure phải phản ánh mức độ đã chứng minh.

## 10. Ai quyết định gửi và ai có quyền phát hành?

Một workflow đáng tin thường tách:

1. **Incident Commander** quyết định escalation và bảo đảm hoạt động khẩn cấp diễn ra.
2. **Security/key subject-matter experts** xác thực facts và đánh giá phạm vi cryptographic impact.
3. **Data/service owners** xác nhận objects, tenants, business impact và remediation.
4. **Legal/privacy/compliance** xác định nghĩa vụ/timing/content theo jurisdiction, contract và regulatory role.
5. **Communications/customer support** chuẩn hóa thông điệp, kênh và FAQ.
6. **Authorized publisher** phát hành đúng audience; không một engineer tự gửi bulk email từ tài khoản cá nhân.

### 10.1. Ma trận trách nhiệm minh họa

| Hoạt động | SOC/IC | Key owner | Data owner | Legal/privacy | Comms |
|---|---|---|---|---|---|
| Triage và containment | **R/A** | R | C | I | I |
| Xác minh key material/usage status | R | **R/A** | C | I | I |
| Xác định tenants/data scope | C | C | **R/A** | C | I |
| Xác định nghĩa vụ thông báo | C | I | C | **R/A** | C |
| Soạn thông báo ngoài tổ chức | C | C | C | A về tính pháp lý | **R** |
| Phát hành đúng kênh/audience | A về incident | I | C | Approve theo policy | **R** |
| Sửa/cập nhật notice | R | R | R | Review | **R** |
| Đóng hậu kiểm và evidence | **R/A** | R | R | C | C |

RACI trên **mang tính tham khảo**, không thay quy định tổ chức hoặc luật. Với sự cố nghiêm trọng, thẩm quyền emergency notice có thể cần một path đã được phê duyệt từ trước để không bỏ lỡ nghĩa vụ.

### 10.2. Approval không được làm tê liệt containment

Việc rotate, block egress, revoke KMS principal hoặc cô lập host có thể cần thực hiện **trước khi có bản public notice đã duyệt**. Ngược lại, notice external chưa có căn cứ không nên tự động được gửi chỉ vì hệ thống đã disable key.

### 10.3. SoD và tính toàn vẹn của người gửi

Người bị nghi xâm phạm hoặc operator nắm KMS credentials bị lộ **không nên là người duy nhất duyệt và phát hành** thông tin về chính sự cố của họ. Cần audit, phân tách chức năng và dùng **identity/channel độc lập** khi communications infrastructure có thể bị chiếm.

## 11. Thông báo khi DEK, KEK và envelope encryption bị ảnh hưởng

Trong **envelope encryption**, dữ liệu thường được mã hóa bằng **DEK**, còn DEK được bảo vệ bởi **KEK** trong KMS/HSM. Do đó cần xác định người nhận notice theo **đối tượng nào có thể đã mất tính bí mật hoặc khả năng truy cập**.

```mermaid
flowchart TD
    K["KEK-v1 của KMS/HSM"] --> W1["Wrapped DEK-A"]
    K --> W2["Wrapped DEK-B"]
    W1 --> C1["Ciphertext tenant A"]
    W2 --> C2["Ciphertext tenant B"]
    MISUSE["Unauthorized KMS Unwrap/Decrypt"] --> K
    MISUSE --> AUDIT["KMS event IDs + principal + context"]
    C1 --> OWNER1["Đánh giá data-owner A"]
    C2 --> OWNER2["Đánh giá data-owner B"]
    AUDIT --> OWNER1
    AUDIT --> OWNER2
    OWNER1 --> NOTICE["Notices chỉ cho affected parties"]
    OWNER2 --> NOTICE
```

### 11.1. KEK material bị lộ chưa đồng nghĩa mọi ciphertext bị đọc

Nếu raw KEK-v1 bị sao chép, attacker có thể có khả năng unwrap DEKs **nếu họ có wrapped DEK blobs và scheme/context cần thiết**. Thông báo có thể nói “những bản ghi phụ thuộc KEK-v1 có rủi ro”, nhưng câu “tất cả plaintext đã bị truy cập” cần chứng cứ riêng.

### 11.2. KMS Decrypt abuse khi KEK non-exportable

Một service account bị chiếm có thể gọi `Decrypt/Unwrap` trên wrapped DEKs và nhận raw DEKs trong memory. Thông báo nội bộ cho KMS custodian cần:

- **Immutable keyRef/logical key ID**, provider, region.
- Principal/grant/session bị ảnh hưởng và exact operations đã thấy.
- KMS request IDs, thời gian, encryption context và nguồn logs.
- Phạm vi wrapped DEKs, data owners và tenants có thể bị ảnh hưởng.
- Containment: revoke principal, disable API path, rate-limit hoặc isolate workload.

Thông báo bên ngoài không cần công bố mọi principal/role nội bộ nhưng nên phản ánh **tác động dữ liệu đã được kiểm chứng hoặc nguy cơ có cơ sở**.

### 11.3. DEK bị lộ: rewrap không đủ

Nếu raw DEK đã lộ, **rewrap cùng DEK dưới KEK mới không làm DEK cũ bí mật trở lại**. Khi trao đổi với data owners và khách hàng phải nói:

- Data ciphertext dùng DEK đó là phạm vi **có nguy cơ bị giải mã** nếu attacker có bản mã.
- Việc thay KEK là một bước giảm phụ thuộc vào key cũ, **không tự khắc phục data exposure lịch sử**.
- Có thể cần **sinh DEK mới và reencrypt** dữ liệu, đồng thời xử lý bản sao đã có.

### 11.4. Một KMS key có thể phục vụ nhiều tenants

Nếu KEK được chia sẻ giữa nhiều tenants, blast radius có thể rộng hơn một tenant. Nhưng cũng không tự suy ra mọi tenant bị ảnh hưởng: phải kiểm kê **wrapped DEKs, key usage, ACL, tenant mappings, ciphertext access**. Pipeline notice cần tách **danh sách người nhận theo scope đã xác minh**, không gửi bí mật tenant này cho tenant khác.

### 11.5. Khóa bị mất gây outage, không nhất thiết có data disclosure

Nếu KEK-v1 bị destroy sớm và dữ liệu cũ không thể unwrap, sự cố là **availability/data-loss risk**. Notice cần giải thích khả năng truy cập, phục hồi, backups, ước lượng phạm vi dựa trên chứng cứ và hỗ trợ; không gọi đó là “key leakage” khi không có bằng chứng.

## 12. Thông báo về private signing key, chứng thư và trust

Sự cố **private signing key** có tác động khác DEK: attacker có thể **ký thay chủ sở hữu** hoặc làm giảm độ tin cậy của thông điệp, phần mềm, hợp đồng hoặc token.

### 12.1. Những bên cần thông tin

- Người vận hành **private signing key/KMS Sign service**: ngừng Sign, cô lập principal.
- **PKI/CA/trust managers**: đánh giá certificate revocation và chain/trust update.
- Các **verifiers/partners/clients**: có thể cần tải public key mới, sửa trust store/JWKS, từ chối chữ ký mới bằng v1.
- **Artifact/data owners**: đánh giá chữ ký nào được tạo trong cửa sổ nghi ngờ và hồ sơ nào cần xác minh lại.
- **Legal/compliance**: xem nghĩa vụ đối với hợp đồng, giao dịch, chữ ký điện tử và hồ sơ có tính pháp lý.

### 12.2. Thông báo phải phân biệt key signing và key verification

Sau rotation, **private key v1 có thể ngừng Sign**, nhưng các chữ ký lịch sử thường vẫn được Verify bằng **public key v1**, certificates và trust evidence theo scheme/policy. Không chỉ dẫn toàn bộ verifiers “xóa mọi public key v1” nếu việc đó phá xác minh các bản ghi hợp lệ và chưa có kế hoạch thay thế.

### 12.3. Revocation của certificate không giống destroy raw key

CA có thể cập nhật trạng thái certificate qua CRL/OCSP hoặc cơ chế trust tương ứng. Hủy private key trong KMS không tự cập nhật mọi verifier cache hoặc thu hồi certificate. Notice cần mô tả **cơ chế trust cụ thể**, thời điểm áp dụng, phiên bản và hành động của recipients.

### 12.4. Khi nào thông báo “signature forgery”?

Nếu chỉ thấy một principal dùng Sign API trái phép, có thể **xác nhận hành vi ký trái phép** nếu logs đủ tin cậy, nhưng không mặc định tất cả signed artifacts là giả. Cần inventory dựa vào **request IDs, signed artifact identifiers, signer identity, time window và trusted timestamp**. Phân biệt chữ ký hợp lệ trước sự cố, chữ ký bị nghi ngờ và chữ ký được xác nhận không được phép.

### 12.5. Không dùng key bị nghi lộ để ký thông báo thay khóa

Nếu private signing key v1 bị nghi compromise, dùng **chính v1** để ký một notice “hãy chuyển sang v2” là nguồn xác thực yếu: attacker cũng có thể ký thông điệp tương tự. Hãy dùng **trust channel độc lập, ký bởi key còn đáng tin hoặc authenticated portal**.

## 13. Thông báo về HMAC, API secrets, JWT và webhook

Khác với chữ ký số, **HMAC là shared-secret**: bất kỳ ai có secret có thể tạo MAC và thường có thể Verify. Một partner integration dùng chung HMAC key sẽ cần phối hợp **cả producer lẫn consumer**.

### 13.1. Webhook secret bị lộ

Thông báo nội bộ/đối tác nên nói rõ:

1. **Integration ID và secret version** bị ảnh hưởng (không gửi raw secret).
2. Đơn vị nào cần phát hành secret mới và đơn vị nào cần cập nhật verifier.
3. Thời điểm dự kiến cắt key cũ, grace period nếu chính sách chấp nhận.
4. Cách xử lý **message replay**, duplicate events và signature validation.
5. Kênh an toàn để provisioning secret mới — **không gửi HMAC secret qua email thông thường**.
6. Hành động khi integration có message không hợp lệ trong cửa sổ nghi ngờ.

### 13.2. JWT signing key và verifier JWKS

Nếu JWT được ký bằng khóa bất đối xứng, producer cần ngừng ký bằng private key cũ; verifiers có thể cần cập nhật **JWKS/trust policy**, cache TTL và `kid` mapping. Nếu JWT dùng HMAC, shared secret phải được rotate ở **mọi verifier nhận token** và phạm vi forged token có thể khác.

Không tự cho rằng `kid` là bằng chứng tin cậy: verifier phải lấy keys từ **issuer/trust source đã cấu hình**, kiểm tra `iss/aud/exp/nbf` và algorithm allowlist.

### 13.3. Clock skew, token lifetime và revoke

Thông báo về token cần phân biệt:

- **Last issuance** bằng key v1.
- **Last valid token expiry** theo actual max lifetime và clock skew.
- **Verifier cache refresh** đã hoàn tất hay chưa.
- **Emergency revoke** có thể chặn token ngay, dù gây gián đoạn.
- Những **offline verifiers** có thể không nhận được update kịp và cần contact riêng.

Đừng hứa “mọi token cũ vô hiệu lúc 12:00” khi các verifiers offline vẫn trust v1; chỉ cam kết khi có cơ chế cưỡng chế/kiểm chứng phù hợp.

### 13.4. Secret version và key material khác nhau

Một notification “secret version v3 đã được tạo” không tự chứng minh v2 đã bị thu hồi ở cả producer lẫn verifier. Cần quan sát **effective acceptance**, không chỉ configuration change.

## 14. KMS/HSM incident và trách nhiệm của nhà cung cấp

Nhà cung cấp KMS/HSM có thể hỗ trợ logs, key state, rotation, revoke/deletion, HSM audit hoặc attestation. Nhưng **provider case opened** không tự có nghĩa provider xác nhận compromise.

### 14.1. Nội dung gửi provider support

| Trường | Vì sao cần |
|---|---|
| Account/project, region và provider case ID | Định tuyến điều tra |
| Immutable key resource ID/material version khi có | Xác định đúng đối tượng |
| UTC window, operations, error codes, KMS request IDs | Truy vết logs |
| Principal/role/session identifiers | Kiểm tra quyền và sự kiện |
| Expected policy/state vs observed behavior | Xác định drift hoặc misuse |
| Containment đã thực hiện | Tránh thao tác trùng hoặc phá evidence |
| Business impact và urgency | Ưu tiên investigation/availability |
| Khả năng cung cấp logs qua secure channel | Không phát tán secrets trong ticket |

Không gửi raw KEK/DEK/private key cho support chỉ để chứng minh nó bị lộ. Nếu cần tài liệu forensic nhạy cảm, dùng kênh và thủ tục đã phê duyệt.

### 14.2. Provider-managed rotation có thể không cho xóa material version riêng

Một logical key có nhiều material generations sau auto-rotation. Notice nội bộ cho key owners phải nêu **phạm vi operations provider thực sự hỗ trợ**. Không thông báo “đã hủy version v1” nếu API chỉ disable **toàn logical key** hoặc mới đổi alias.

### 14.3. KMS API outage có thể ảnh hưởng decrypt mà không có compromise

Thông báo cho SRE/khách hàng nên phân biệt **service outage, AccessDenied do IAM, disabled key, quota/rate limiting và AEAD tag failure**. Mọi Decrypt failure không được gộp thành “khóa bị tấn công”.

### 14.4. HSM key non-exportable vẫn có usage risk

Nếu attacker chiếm principal có quyền `Sign` hoặc `Unwrap`, material có thể chưa rời HSM nhưng **kết quả phép toán** đã bị lạm dụng. Thông báo phải tập trung vào **authorized/unauthorized operations và artifacts/dữ liệu liên quan**, không chỉ thuộc tính exportability.

## 15. Phối hợp containment và thông báo để tránh tạo thêm rủi ro

Thông báo về sự cố không thể đứng riêng với hành động kỹ thuật.

### 15.1. Một kế hoạch containment theo loại key

| Key/purpose | Hành động ban đầu thường cần đánh giá | Thông báo gắn với hành động |
|---|---|---|
| **AES DEK bị lộ** | Chặn new-use, xác định ciphertexts, thay DEK/reencrypt | Data owner/affected parties biết scope/risk và việc cần làm |
| **KEK bị lộ** | Hạn KMS/Key usage, rotate KEK, kiểm tra wrapped DEKs | Service/KMS/tenants theo dependency graph |
| **KMS access compromised** | Revoke principal/session, review IAM, KMS operation logs | IAM/SRE và data owners; không tự claim raw key leaked |
| **Private signing key** | Stop Sign, thay key, revocation/trust update | PKI/verifiers/partners và owners của signed artifacts |
| **HMAC webhook key** | Rotate shared secret, bounded acceptance, replay protections | Producers và consumers qua kênh xác thực |
| **RSA/KEM recipient private key** | Dừng new envelopes cho v1, chọn trusted v2, kiểm kê old packages | Senders, recipient owner và partners còn ciphertext lịch sử |
| **KEK deleted nhầm** | Đánh giá key recovery/backup theo provider, DR restore | Operations và affected data owners; thông báo availability |

### 15.2. Không nói “key đã revoke, mọi rủi ro chấm dứt”

Revoke grant hoặc session thường **ngăn lời gọi mới qua đường đó**, nhưng không thu hồi **DEK/plaintext đã copy**. Rewrap cùng DEK dưới KEK mới không sửa dữ liệu đã lộ. Hủy key vật lý ở HSM cũng không xóa những bản sao ngoài custody.

### 15.3. Thông báo có thể là một phần của containment

Nếu partners đang Verify chữ ký với key-v1, việc gửi thông báo xác thực để **ngừng trust v1** có thể ngăn thêm các giao dịch giả. Nhưng việc gửi qua kênh không đáng tin hoặc dùng v1 để ký notice sẽ tạo chỗ cho spoofing. Vì thế **notification security** là một biện pháp bảo vệ trong incident.

### 15.4. Tránh lộ phương án điều tra khi attacker còn hiện diện

Một notice kỹ thuật công khai nêu **toàn bộ IAM policies, điều kiện bypass, key labels hay thời điểm containment chưa áp dụng** có thể giúp attacker né kiểm soát. Nội dung chia sẻ cho công chúng nên đi qua **threat-aware redaction**, trong khi SOC và responders có secure evidence access riêng.

## 16. Mẫu thông báo nội bộ: xác thực, ngắn và hành động được

Mẫu nội bộ dành cho Security/SRE/key owners có thể cụ thể hơn external notice, nhưng **vẫn không bao gồm raw key**. Thông tin dưới đây hoàn toàn giả định:

```text
SECURITY INTERNAL — INCIDENT KEY-2026-041 — INVESTIGATING
Issued: 2026-11-28T09:00:00Z
Priority: HIGH (provisional)
Owner: Security Incident Commander

Signal:
  KMS Unwrap/Decrypt từ workload identity orders-reconciler
  vượt baseline và xuất hiện ở vùng triển khai không dự kiến.

Known:
  Các API calls bất thường đã được ghi nhận.
  Đã vô hiệu hóa phiên credential liên quan lúc 08:55Z.
  Raw KEK export chưa có bằng chứng.

Unknown:
  Chưa xác định đầy đủ số wrapped DEKs/ciphertexts đã được truy cập.
  Chưa xác nhận có plaintext customer data bị sao chép hay không.

Key scope (restricted):
  provider key reference: orders-prod-kek/resource-v4
  purpose: DATA_KEY_UNWRAP
  affected services under review: orders-reconciler

Actions:
  IAM team: kiểm tra grants trực tiếp/indirect và session tokens.
  Key custodian: bảo toàn KMS request IDs, không xóa key.
  Data owner: dựng dependency inventory và impacted records.
  SRE: giám sát khả năng decrypt, tránh reboot làm mất evidence.

Next checkpoint:
  2026-11-28T10:00:00Z, incident room đã xác thực.
```

### 16.1. Vì sao mẫu không ghi “DEK đã bị lộ”?

Tại thời điểm gửi, log mới chứng minh **operation bất thường**. Một KMS Decrypt có thể trả DEK cho caller, nhưng phạm vi DEKs, có kết quả bị lấy/ghi lại không và user thật của principal là ai còn cần điều tra. Thông điệp phân biệt **hành động đã biết** và **hậu quả đang đánh giá**.

### 16.2. Khi nào dùng incident room thay email?

Đội phản ứng có thể cần principal IDs, exact KMS grants và forensic references nhạy cảm. Chúng nên nằm trong **restricted incident room/evidence store** với chính sách truy cập và retention; email phân phối rộng chỉ nên chứa **incident ID, severity, required action và link tới hệ thống đã xác thực**.

## 17. Mẫu thông báo khách hàng: tác động, hành động và cập nhật

Một mẫu email/portal notice ngoài tổ chức nên tránh chi tiết không cần thiết về nội bộ. Ví dụ sau là **tình huống minh họa**, không phải thông báo cho sự cố có thật:

```text
Chủ đề: Cập nhật bảo mật liên quan tính năng xuất báo cáo

Mã thông báo: NOTICE-2026-114, phiên bản 1
Phát hành: 2026-11-28T11:30:00Z

Chúng tôi đang điều tra một hoạt động sử dụng khóa mã hóa
bất thường liên quan hệ thống xử lý báo cáo.

Đã xác minh:
- Một tài khoản dịch vụ đã thực hiện thao tác giải mã không
  nằm trong lịch vận hành được phê duyệt.
- Chúng tôi đã thu hồi quyền truy cập của tài khoản liên quan
  và bổ sung giám sát cho đường xử lý này.

Đang xác minh:
- Phạm vi báo cáo có thể đã bị truy cập.
- Có dữ liệu nào đã bị sao chép ra khỏi môi trường hay không.

Tác động hiện tại:
- Chúng tôi chưa có kết luận đầy đủ về ảnh hưởng tới dữ liệu.
- Tính năng xuất báo cáo có thể bị gián đoạn trong thời gian
  chúng tôi áp dụng biện pháp bảo vệ.

Hành động khách hàng cần làm:
- Theo dõi thông báo trên cổng hỗ trợ chính thức.
- Không gửi password, private key hoặc mã truy cập qua email.
- Nếu phát hiện truy cập bất thường, liên hệ kênh bảo mật
  của tổ chức theo đường dẫn đã được xác thực.

Chúng tôi sẽ đăng bản cập nhật tiếp theo theo lịch công bố
được ghi trên cổng bảo mật chính thức.
```

### 17.1. Mẫu này không được dùng nguyên văn khi chưa có facts

Nếu dữ liệu đã xác nhận bị truy cập, thông báo phải **nói rõ những gì biết được** và các bước khắc phục. Nếu chỉ là key availability outage, không dùng cụm “sử dụng khóa mã hóa bất thường” khi sai sự thật. Tất cả những câu như “đã thu hồi quyền” phải có **evidence** rằng thao tác đã có hiệu lực.

### 17.2. Nói cụ thể khi cần khách hàng hành động

Nếu yêu cầu customer rotate một integration credential, cần:

- Định danh **integration/version** bị ảnh hưởng, không tiết lộ secret.
- Cách vào portal cấu hình thông qua kênh đã biết.
- Thời hạn cutover theo kế hoạch được phê duyệt (có timezone).
- Behavior khi old credential bị từ chối.
- Kênh hỗ trợ khi migration thất bại.

Không dùng lời kêu gọi chung chung “vui lòng bảo mật tài khoản” thay cho những bước hành động thật sự cần thiết.

## 18. Mẫu thông báo đối tác về việc thay signing/HMAC key

Đối tác cần thông điệp kỹ thuật hơn customer end-user vì họ phải **đổi verifier hoặc shared secret**.

### 18.1. Public signing key replacement

```text
PARTNER SECURITY NOTICE — TRUST KEY TRANSITION
Reference: PARTNER-NOTICE-2026-022
Issuer: verified security channel for Example Payments

Affected integration:
  transaction-receipt signatures

Confirmed status:
  Private signing-key version sign-v5 is under security review.
  New signatures are issued using sign-v6 from the announced cutover.

Required partner action:
  Retrieve sign-v6 public key/certificate from the established
  authenticated key directory.
  Validate trusted fingerprint/certificate chain out-of-band
  using the documented trust procedure.
  Stop accepting new messages signed with sign-v5 as specified
  in the separately confirmed enforcement notice.
  Preserve evidence for older signed artifacts under the
  historical verification policy; do not delete all archives.

Unknowns:
  Investigation into suspicious signatures in the affected
  time window is ongoing.

Validation contact:
  Existing verified partner security contact/channel.
```

Nếu một **revocation/compromise** đã được xác nhận, thông báo cần nêu **trust policy** rõ hơn và xử lý các chữ ký đã phát hành. Đừng tạo “grace period” mặc định cho key nghi lộ nếu nó cho phép attacker tiếp tục giả mạo.

### 18.2. HMAC webhook key replacement

```text
PARTNER INTEGRATION NOTICE — HMAC SECRET ROTATION
Reference: PARTNER-NOTICE-2026-023
Integration: shipment-status-webhook
Affected secret version: webhook-hmac-v2

Required actions:
  1. Retrieve version v3 only through the authenticated
     partner configuration portal, never by replying with secrets.
  2. Validate HMAC using the documented algorithm/version
     and bounded replay window.
  3. Apply the approved cutover policy for accepting v2/v3;
     emergency revoke of v2 may supersede the grace period.
  4. Report unexpected signatures or duplicated message IDs
     through the verified incident support channel.

Important:
  Do not disclose the HMAC secret in support tickets or logs.
```

### 18.3. Fingerprint không thay thế trust

Một fingerprint gửi cùng public key qua **cùng kênh chưa xác thực** không chống được attacker thay cả key lẫn fingerprint. Cần một kênh/trust anchor độc lập hoặc certificate chain được cấu hình trước.

### 18.4. Hành động verifier cần được xác nhận

Không coi việc gửi email “vui lòng rotate” là đã hoàn tất containment. Cần quan sát **partner acknowledgment, actual trust-store/JWKS updates, accepted key versions, callback tests và cutover metrics**. Bên không phản hồi cần escalation theo hợp đồng.

## 19. Evidence, privacy và chain of custody trong quá trình thông báo

Key incident thường tạo ra **raw audit logs, host traces, secret scanning results và KMS/HSM events**. Mục tiêu là bảo toàn bằng chứng để điều tra và hậu kiểm **mà không biến thông báo thành một đường rò rỉ khác**.

### 19.1. Evidence catalog

| Loại bằng chứng | Ví dụ | Cách chia sẻ phù hợp |
|---|---|---|
| **KMS API logs** | Key ID, principal, operation, request ID, UTC time | SOC/IC và key custodian qua evidence store |
| **Key inventory** | Logical/material versions, key purpose, dependencies | Data/key owners, hạn chế theo tenant |
| **Artifact references** | Hash/ID của encrypted objects, signing requests | Forensic/data owners, không gửi raw plaintext công khai |
| **IAM change logs** | Session revocation, grant modification | SOC/IAM, signed change records |
| **Storage access logs** | Object reads/downloads, affected tenant | Data owners và privacy investigators |
| **Provider support ticket** | API errors, provider case number | Provider secure channel, không gửi raw secrets |
| **Communication evidence** | Approved notice, audience, sentAt, delivery status | Incident/legal/comms audit |
| **Public notice** | Sanitized facts và required actions | Khách hàng/đối tác đúng scope |

### 19.2. UTC chronology và time uncertainty

Một host có thể có clock drift, KMS logs có ingestion delay, audit trail có retry và timestamps không đồng nhất. Trong báo cáo:

- Phân biệt **event time** và **log ingestion time**.
- Ghi offset/timezone, clock source và độ tin cậy.
- Nếu chỉ biết khoảng 02:00–02:30, đừng bịa mốc 02:13:27 như thời điểm tấn công.
- Sử dụng **UTC timeline** để đối chiếu KMS, IAM, DB, CDN và partner systems.

### 19.3. Không đưa secrets vào ticket thông báo

Tránh gửi:

- Raw private key PEM, HMAC shared secret, raw DEK/KEK, KMS plaintext data key.
- Access token/session cookies, passwords, recovery codes.
- Plaintext customer data hoặc forensic dumps chưa redaction.
- Internal-only IAM policy chi tiết hoặc đường dẫn khai thác khi không cần thiết.

Nếu cần chứng minh key đã xuất hiện trong artifact công khai, có thể lưu **artifact reference, vị trí, timestamps, content digest và kiểm soát truy cập forensic**; không phải chép nguyên private key vào hàng trăm email.

### 19.4. Chain of custody và notice audit

Ghi lại ai đã tạo/thu thập evidence, hệ thống nguồn, thời gian, checksum/signature của artifact khi phù hợp, người truy cập và các bước xử lý. Thông báo đã phát hành cũng là **bằng chứng**: giữ bản chính xác, phê duyệt, người nhận và kết quả gửi theo retention.

### 19.5. Evidence không chứng minh phủ định tuyệt đối

“Không tìm thấy log lộ dữ liệu” khác “dữ liệu không bị lộ”, nhất là khi log retention ngắn, agent bị vô hiệu hoặc DEK có thể đã bị copy rồi dùng offline. Notice cần nêu **audit coverage và limitations** trong báo cáo kỹ thuật, không tạo độ chắc chắn giả.

## 20. Java 17: tạo thông báo đã giới hạn thông tin từ dữ liệu sự cố

Ví dụ Java 17 minh họa cách một ứng dụng **tách thông tin nội bộ và khách hàng**, biểu diễn **UNKNOWN** thay vì mặc định không ảnh hưởng, kiểm tra **approval** trước khi tạo external notice và **không chứa API gửi email, thao tác KMS hay raw secrets**.

### 20.1. Nguyên tắc của demo

1. **Input là dữ liệu đã được incident team xác nhận**, không phải raw KMS/host logs từ người dùng gửi trực tiếp.
2. **Enum/cấu trúc typed** giúp giới hạn wording và tránh đưa các chuỗi chưa redaction vào notice công khai.
3. `INTERNAL` có thể hiển thị keyRef nội bộ; `CUSTOMER` không được chứa keyRef, role name, HSM partition hoặc secret.
4. Nếu impact count chưa biết, ghi **“chưa xác định”**, không thay bằng `0`.
5. Chỉ khi notice đã **externalApproved** mới tạo nội dung gửi ra; ví dụ vẫn không tự gửi.
6. Log việc **generate preview** không phải xác nhận thông báo đã được phát hành/nhận.

```java
import java.time.Instant;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public final class KeyIncidentNoticeDemo {
    enum IncidentPhase {
        INVESTIGATING,
        CONFIRMED_UNAUTHORIZED_USE,
        CONTAINED,
        RECOVERY,
        CLOSED
    }

    enum KeyPurpose {
        DATA_KEY_UNWRAP,
        SIGNING,
        WEBHOOK_HMAC
    }

    enum Audience {
        INTERNAL_SECURITY,
        AFFECTED_CUSTOMER
    }

    // UNKNOWN != NO. Không dùng boolean false cho điều chưa biết.
    enum Finding {
        UNKNOWN,
        NOT_CONFIRMED,
        CONFIRMED
    }

    enum ServiceArea {
        ORDERS_REPORTING,
        TRANSACTION_SIGNATURES,
        WEBHOOK_DELIVERY
    }

    record IncidentFacts(
            String incidentId,
            Instant detectedAt,
            Instant confirmedAt,
            IncidentPhase phase,
            KeyPurpose keyPurpose,
            ServiceArea serviceArea,
            String internalKeyRef,
            Finding unauthorizedKeyUse,
            Finding rawMaterialExposure,
            Finding dataAccessExposure,
            Integer affectedRecords,
            boolean accessPathRevokedAndVerified,
            boolean externalNoticeApproved,
            int noticeVersion) {
        IncidentFacts {
            Objects.requireNonNull(incidentId);
            Objects.requireNonNull(detectedAt);
            Objects.requireNonNull(phase);
            Objects.requireNonNull(keyPurpose);
            Objects.requireNonNull(serviceArea);
            Objects.requireNonNull(internalKeyRef);
            Objects.requireNonNull(unauthorizedKeyUse);
            Objects.requireNonNull(rawMaterialExposure);
            Objects.requireNonNull(dataAccessExposure);
            if (!incidentId.matches("INC-[A-Z0-9-]{3,40}")) {
                throw new IllegalArgumentException("Invalid incident ID");
            }
            if (noticeVersion < 1) {
                throw new IllegalArgumentException("Invalid version");
            }
            if (affectedRecords != null && affectedRecords < 0) {
                throw new IllegalArgumentException(
                        "Negative affected record count");
            }
            if (confirmedAt != null
                    && confirmedAt.isBefore(detectedAt)) {
                // Hạn chế GIẢ ĐỊNH của demo về thời điểm confirmed.
                throw new IllegalArgumentException(
                        "Confirmation before detection");
            }
        }
    }

    record Notice(
            String noticeId,
            int version,
            Audience audience,
            Instant generatedAt,
            String text,
            boolean approvedForExternalPublication) {}

    static String knownFinding(Finding finding) {
        return switch (finding) {
            case UNKNOWN -> "chưa xác định";
            case NOT_CONFIRMED ->
                    "chưa có bằng chứng xác nhận";
            case CONFIRMED -> "đã xác nhận";
        };
    }

    static String publicService(ServiceArea area) {
        return switch (area) {
            case ORDERS_REPORTING -> "xử lý báo cáo đơn hàng";
            case TRANSACTION_SIGNATURES ->
                    "xác thực chữ ký giao dịch";
            case WEBHOOK_DELIVERY -> "giao nhận webhook";
        };
    }

    static String publicPurpose(KeyPurpose purpose) {
        return switch (purpose) {
            case DATA_KEY_UNWRAP -> "giải mã dữ liệu";
            case SIGNING -> "ký và xác minh giao dịch";
            case WEBHOOK_HMAC -> "xác thực webhook";
        };
    }

    static String publicPhase(IncidentPhase phase) {
        return switch (phase) {
            case INVESTIGATING -> "đang điều tra";
            case CONFIRMED_UNAUTHORIZED_USE ->
                    "đã xác nhận việc dùng khóa trái phép";
            case CONTAINED -> "đã khống chế đường truy cập đã biết";
            case RECOVERY -> "đang khôi phục và xác minh";
            case CLOSED -> "đã đóng quy trình xử lý sự cố";
        };
    }

    static String recordCount(Integer count) {
        return count == null
                ? "chưa xác định"
                : Integer.toString(count);
    }

    static Notice build(
            IncidentFacts f, Audience audience, Instant now) {
        Objects.requireNonNull(f);
        Objects.requireNonNull(audience);
        Objects.requireNonNull(now);

        if (audience == Audience.AFFECTED_CUSTOMER
                && !f.externalNoticeApproved()) {
            throw new SecurityException(
                    "External notification lacks approval");
        }

        StringBuilder body = new StringBuilder();
        body.append("Thông báo: ")
                .append(f.incidentId())
                .append(" / v")
                .append(f.noticeVersion())
                .append('\n');
        body.append("Phát hiện (UTC): ")
                .append(DateTimeFormatter.ISO_INSTANT
                        .format(f.detectedAt()))
                .append('\n');
        body.append("Trạng thái: ")
                .append(publicPhase(f.phase()))
                .append('\n');
        body.append("Phạm vi dịch vụ: ")
                .append(publicService(f.serviceArea()))
                .append('\n');
        body.append("Mục đích khóa: ")
                .append(publicPurpose(f.keyPurpose()))
                .append('\n');
        body.append("Sử dụng khóa trái phép: ")
                .append(knownFinding(f.unauthorizedKeyUse()))
                .append('\n');
        body.append("Lộ raw key material: ")
                .append(knownFinding(f.rawMaterialExposure()))
                .append('\n');
        body.append("Dữ liệu bị truy cập trái phép: ")
                .append(knownFinding(f.dataAccessExposure()))
                .append('\n');
        body.append("Số record đã xác định chịu ảnh hưởng: ")
                .append(recordCount(f.affectedRecords()))
                .append('\n');

        if (f.accessPathRevokedAndVerified()) {
            body.append("Đã xác minh chặn đường truy cập")
                    .append(" được điều tra.\n");
        } else {
            body.append("Biện pháp chặn đường truy cập")
                    .append(" còn đang xác minh.\n");
        }

        if (audience == Audience.INTERNAL_SECURITY) {
            // Chỉ dành cho restricted internal evidence view.
            body.append("Restricted key reference: ")
                    .append(f.internalKeyRef())
                    .append('\n');
            body.append("Cần: kiểm tra request IDs, key grants,")
                    .append(" dữ liệu liên quan và evidence.\n");
        } else {
            body.append("Hướng dẫn: kiểm tra các cập nhật")
                    .append(" qua cổng bảo mật đã xác thực;\n")
                    .append("không gửi mật khẩu hoặc private key")
                    .append(" qua email/ticket.\n");
        }

        String id = f.incidentId() + "-NOTICE";
        return new Notice(
                id,
                f.noticeVersion(),
                audience,
                now,
                body.toString(),
                f.externalNoticeApproved());
    }

    static void requireNoPrivateRefs(Notice n, String keyRef) {
        if (n.audience() == Audience.AFFECTED_CUSTOMER
                && n.text().contains(keyRef)) {
            throw new SecurityException("Internal keyRef leaked");
        }
    }

    public static void main(String[] args) {
        Instant detected = Instant.parse("2026-11-28T08:20:00Z");
        Instant now = Instant.parse("2026-11-28T09:00:00Z");

        IncidentFacts initial = new IncidentFacts(
                "INC-2026-041",
                detected,
                null,
                IncidentPhase.INVESTIGATING,
                KeyPurpose.DATA_KEY_UNWRAP,
                ServiceArea.ORDERS_REPORTING,
                "kms://internal/tenant-A/orders/KEK-v4",
                Finding.UNKNOWN,
                Finding.NOT_CONFIRMED,
                Finding.UNKNOWN,
                null,             // UNKNOWN, không phải 0.
                false,            // Chưa xác minh effective revoke.
                false,            // Chưa duyệt external notice.
                1);

        Notice internal = build(
                initial, Audience.INTERNAL_SECURITY, now);
        System.out.println("Internal generated: "
                + internal.noticeId());
        System.out.println("Internal has keyRef: "
                + internal.text().contains(initial.internalKeyRef()));

        try {
            build(initial, Audience.AFFECTED_CUSTOMER, now);
            throw new AssertionError(
                    "Unapproved notice should be denied");
        } catch (SecurityException expected) {
            System.out.println("External approval enforced");
        }

        IncidentFacts reviewed = new IncidentFacts(
                initial.incidentId(),
                initial.detectedAt(),
                Instant.parse("2026-11-28T08:45:00Z"),
                IncidentPhase.CONFIRMED_UNAUTHORIZED_USE,
                initial.keyPurpose(),
                initial.serviceArea(),
                initial.internalKeyRef(),
                Finding.CONFIRMED,
                Finding.NOT_CONFIRMED,
                Finding.UNKNOWN,
                null, true, true, 2);

        Notice customer = build(
                reviewed, Audience.AFFECTED_CUSTOMER, now);
        requireNoPrivateRefs(customer, reviewed.internalKeyRef());
        System.out.println("Customer generated: "
                + customer.noticeId() + "/v" + customer.version());
        System.out.println("Customer excludes internal keyRef: "
                + !customer.text().contains(reviewed.internalKeyRef()));
        System.out.println("Customer unknown count retained: "
                + customer.text().contains(
                        "chịu ảnh hưởng: chưa xác định"));

        // Không có network/email/SMS hoặc thao tác KMS.
        // Kết quả là preview để con người phê duyệt phát hành.
    }
}
```

### 20.2. Kết quả mong đợi

```text
Internal generated: INC-2026-041-NOTICE
Internal has keyRef: true
External approval enforced
Customer generated: INC-2026-041-NOTICE/v2
Customer excludes internal keyRef: true
Customer unknown count retained: true
```

### 20.3. Những giới hạn quan trọng

- `externalNoticeApproved=true` trong code **không phải một approval thật**; production phải xác minh danh tính, chữ ký/approval reference, version, scope, expiration và SoD.
- `internalKeyRef` có thể chứa thông tin nhạy cảm; trong production phải có **field-level access control**, không dựa chỉ vào `if (audience == ...)`.
- Hàm tạo text **không tự định nghĩa nghĩa vụ pháp lý** hoặc đánh giá đúng impact. Nó nhận `IncidentFacts` do responders xác minh, và **không nên nhận raw attacker-controlled JSON** rồi đưa thẳng vào notice.
- Việc loại trừ một chuỗi keyRef không chứng minh đã **redact mọi PII/secret**. Production cần data classification, content scanning và review của Security/Legal.
- Demo không gửi email, cập nhật status page, gọi KMS, rotate key hoặc trigger destructive actions. **Đó là chủ ý an toàn**, không phải thiếu tính năng.
- `generatedAt` chỉ là thời điểm preview được tạo, **không phải `sentAt` hoặc `deliveredAt`**.
- Demo không có data store, notification version hash/signature, durable audit, tenant recipient validation hoặc replay/deduplication.
- Các lựa chọn enum/văn bản tiếng Việt chỉ là template; ứng dụng thật phải **soạn nội dung riêng theo event, người nhận và nghĩa vụ thực tế**.

### 20.4. Vì sao dùng `Finding.UNKNOWN` thay boolean?

Với boolean `dataExposed=false`, một hệ thống có thể vô tình viết “không có dữ liệu nào lộ” chỉ vì chưa biết. Enum **UNKNOWN/NOT_CONFIRMED/CONFIRMED** cho phép nói rõ trạng thái chứng cứ. Tuy nhiên, `NOT_CONFIRMED` vẫn **không** đồng nghĩa khẳng định “không xảy ra”; nó chỉ nói chưa có chứng cứ xác nhận tại thời điểm đánh giá.

## 21. Kiểm thử hệ thống notification: correctness và tenant isolation

Kiểm thử không nên dừng ở “mẫu email hiển thị đẹp”. Pipeline cần bảo đảm **đúng người, đúng nội dung, đúng phiên bản, không rò secret và không phát notice chưa được duyệt**.

| Tình huống | Kết quả cần có |
|---|---|
| Event mới, chưa xác nhận impact | Nội dung phân biệt UNKNOWN với CONFIRMED |
| Lộ key material xác nhận nhưng data impact chưa rõ | Không tự khẳng định toàn bộ data leaked |
| KMS Decrypt bất thường nhưng raw KEK non-exportable | Thông điệp về unauthorized usage, không bịa raw exposure |
| Client tự khai affected tenant B | Audience lấy từ registry/policy đáng tin, không từ caller input |
| Notice chứa raw private key/DEK/HMAC secret | **Block publication**, quarantine và incident escalation |
| Không có external approval | **Block external publish**, vẫn cho internal response đúng quyền |
| Notice version bị gửi nhầm thứ tự | Consumer/portal nhận biết supersession; không âm thầm ghi đè |
| Incorrect recipient list có tenant khác | **Block** và báo lỗi isolation |
| Kênh email/account gửi bị nghi compromise | Dùng independently authenticated fallback |
| Đối tác cần rotate signing key | Nhận key ID/trust procedure, không nhận private key |
| Key đã revoked nhưng recipient offline vẫn dùng v1 | Có escalation và verified cutover state |
| Notice được tạo nhưng gửi thất bại | Trạng thái **GENERATED/SEND_FAILED**, không ghi DELIVERED |
| Provider chỉ schedule deletion | Không thông báo “key destroyed” |
| Impact count UNKNOWN | Không gắn 0 hoặc 100% |
| Event time khác detection time | Hiển thị và audit hai mốc độc lập |
| Legal hold áp dụng trong khi soạn notice | Workflow nhận thay đổi và review lại |
| Cập nhật scope sau notice v1 | Notice v2 nói điều gì thay đổi, bản v1 vẫn trong archive |
| Customer portal tenant A mở notice tenant B | 403/DENY và audit, không leak metadata |
| Support trả lời không đúng approved FAQ | Escalate, không tự đưa giả thuyết mới |
| Reopen incident sau closure | Notice mới có provenance; không sửa bản đã phát |

### 21.1. Kiểm thử đường gửi và đường nhận

Một thông báo được **generate** có thể chưa được **approve**, chưa được **sent**, chưa được **delivered**, chưa được **acknowledged** và chưa được **acted upon**. Theo dõi trạng thái độc lập:

```text
DRAFT -> REVIEWED -> APPROVED -> QUEUED
QUEUED -> SENT -> DELIVERED -> ACKNOWLEDGED (nếu cần)
QUEUED/SENT -> FAILED -> RETRY_OR_ESCALATE

NO automatic meaning:
  DELIVERED != READ
  READ != ACTION_COMPLETED
  SENT != TRUST_STORE_UPDATED
```

Đối với partners cần đổi HMAC/JWKS, phải theo dõi **actual integration cutover/verification result** ngoài email delivery status.

### 21.2. Automation tests cho redaction

Cần có fixtures cố tình chứa:

- `-----BEGIN PRIVATE KEY-----` và các PEM structures.
- Secrets/token formats từ nhà cung cấp, session cookies và URLs có credentials.
- Email/PII không thuộc audience, cross-tenant key references.
- Stack traces chứa request bodies hoặc decrypted payload.
- Unicode/bidirectional control characters có thể làm sai nội dung hiển thị.

Detection không hoàn hảo và có thể false positives; việc publish phải có **human review** theo risk policy, không coi regex scrub là bằng chứng không còn secret.

### 21.3. Không chạy destructive commands trong test notification

Test notification engine **không cần** disable/destroy KMS key thật. Dùng test environment, mock/synthetic incident data và giả lập trạng thái key; các thay đổi production về IAM/rotation/deletion cần quy trình authorization riêng.

## 22. Case study A: lạm dụng KMS Decrypt của hệ thống đơn hàng nhiều tenant

Một nền tảng SaaS bán hàng dùng một logical KEK của KMS để wrap DEKs cho các record của nhiều tenants. Ở một đợt giám sát, SOC thấy service account `orders-reconciliation` thực hiện các `Decrypt` operations lớn hơn baseline trong khoảng 08:10–08:30 UTC, từ một workload không thuộc deployment được phê duyệt.

### 22.1. Điều biết được ngay

| Vấn đề | Trạng thái |
|---|---|
| KMS key ID và service principal liên quan | Đã xác định bằng audit logs |
| Có các phép Decrypt ngoài plan | Đang được xác minh theo request IDs / workload identity |
| Raw KEK bị export | Chưa có bằng chứng; KEK provider-managed non-exportable |
| DEKs nào được unwrap | Chưa hoàn tất mapping KMS request → record/wrapped DEK |
| Plaintext đã bị sao chép hay chưa | Chưa xác định |
| Tenants có thể bị ảnh hưởng | Chưa chốt; cần liên kết context/data inventory |

Nếu chỉ dựa vào tính năng **non-exportable**, đội vận hành có thể thông báo sai “không có rủi ro dữ liệu”. Ngược lại, từ một spike Decrypt cũng không được tuyên bố “toàn bộ khách hàng đã bị lộ”.

### 22.2. Notification sequence đúng

1. **SOC → IC + KMS/IAM owners:** thông báo nghi vấn, request IDs, keyRef, khung UTC và yêu cầu containment.
2. **IAM/SRE:** xác minh principal, revoke session/grants, cô lập workload; ghi thời điểm hiệu lực.
3. **Data owners:** mapping các Decrypt operations về DEK/ciphertext/tenant bằng encryption context, record IDs và các nguồn logs còn nguyên.
4. **Legal/privacy:** đánh giá liệu access trái phép và data categories có tạo nghĩa vụ thông báo không; xác nhận thời hạn thực tế theo jurisdiction/contract.
5. **Customer communications:** phát notice **đúng affected tenants** nếu có nghĩa vụ/decision được phê duyệt; không gửi list tenant B cho A.
6. **Updates:** khi có evidence mới, làm rõ tenants/objects, khuyến nghị đổi integration keys nếu thật sự cần, và thông báo residual risk.
7. **Closure:** xác minh IAM revoke, KMS access pattern bình thường, remediation/key use policy, audit và customer follow-up.

### 22.3. Trường hợp người vận hành nhầm rotation với containment

Team tạo KEK-v2 và đổi alias new-wrap, rồi gửi email “mọi dữ liệu đã được bảo vệ trở lại”. Sai vì wrapped DEKs và ciphertext lịch sử dưới KEK-v1 vẫn tồn tại; **nếu DEKs đã bị unwrap và sao chép**, việc đổi lớp bọc không lấy lại được raw DEKs.

Thông điệp đúng hơn: “Chúng tôi đã dừng đường sử dụng khóa trái phép đã xác định và bắt đầu migration/đánh giá dữ liệu liên quan; ảnh hưởng dữ liệu lịch sử tiếp tục được xem xét.” Chỉ nói “đã ngăn” khi đã có bằng chứng revoke có hiệu lực.

### 22.4. Bài học

**Key usage compromise ≠ raw key material compromise ≠ confirmed data exposure**. Thông báo theo trục bằng chứng giúp vừa không xem nhẹ rủi ro, vừa không đưa kết luận thiếu căn cứ.

## 23. Case study B: private signing key của đối tác thanh toán bị nghi lộ

Một hệ thống thanh toán gửi biên nhận giao dịch có chữ ký số. Private signing key v5 được quản lý trong HSM. SOC phát hiện một principal có quyền Sign đã bị chiếm; không thấy raw private key xuất ra, nhưng có các signing requests không nằm trong luồng sản phẩm.

### 23.1. Tác động không giống sự cố DEK

Với chữ ký số, mối lo chính là **authenticity/integrity**: một đối tượng trái phép có thể tạo chữ ký khiến verifiers nghĩ biên nhận hợp lệ. Thông báo đối tác không thể chỉ nói “dữ liệu mã hóa có thể bị mở”. Phải làm rõ:

- Key/certificate versions phục vụ **Verify**.
- Khoảng thời gian những chữ ký chưa được phê duyệt có thể đã được tạo.
- Các signing request IDs và bản ghi giao dịch cần đối chiếu.
- Cách nhận **trusted public key v6**, kiểm chứng fingerprint/certificate chain.
- Khi nào và bằng cách nào **ngừng chấp nhận các chữ ký mới bằng v5** theo incident trust policy.
- Cách xử lý hồ sơ ký cũ và **trusted timestamp/revocation evidence** theo chính sách thực tế.

### 23.2. Một thông điệp sai có thể phá hệ thống xác minh

Gửi “xóa public key v5 khỏi mọi thiết bị ngay” mà không có hướng dẫn xử lý chữ ký cũ có thể khiến đối tác **không thể xác minh biên nhận hợp lệ**. Nhưng cho phép v5 mãi mãi cũng có thể để attacker tạo giao dịch giả. Cần một **trust transition plan** phân biệt **new signatures, previously issued artifacts và suspected malicious signatures**.

### 23.3. Đường thông báo được xác thực độc lập

Vì quyền Sign v5 bị nghi compromise, không dùng chỉ **chữ ký v5** để xác thực một notice chuyển sang v6. Tổ chức nên:

1. Thông báo qua **authenticated partner portal/verified security contacts**.
2. Công bố v6 public key/certificate từ trust directory đã được cấu hình.
3. Có **out-of-band fingerprint confirmation** nếu trust model yêu cầu.
4. Xác nhận các partners đã cập nhật verifier và không còn chấp nhận v5 cho new-use trái chính sách.
5. Ghi lại **notice delivery, acknowledgement và verified operational cutover**, không đồng nhất chúng.

### 23.4. Kết thúc incident vẫn còn nghĩa vụ lưu hồ sơ

Sau khi private signing key v5 được retire/destroy theo policy, public verification key, certificate chain, trust evidence và audit có thể vẫn cần giữ để đánh giá giao dịch lịch sử. Notice closure phải diễn đạt đúng chứ không yêu cầu xóa mọi metadata liên quan v5.

## 24. Runbook thông báo sự cố key từ phát hiện tới closure

Quy trình này là mô hình tham khảo. Các bước có thể diễn ra **song song** khi cần containment nhanh hoặc nghĩa vụ thông báo sớm; không biến nó thành chuỗi tuần tự làm chậm xử lý.

### Phase A — Phát hiện và mở incident

1. Nhận signal từ KMS/HSM audit, secret scanning, SOC, app telemetry hoặc partner report.
2. Gắn **incident ID, detectedAt, source, key purpose và môi trường**.
3. Phân loại trạng thái bằng chứng: signal/suspected/confirmed unauthorized use/material exposure/data exposure/availability.
4. Xác định on-call **IC, SOC, key custodian, service owner**.
5. Thông báo nội bộ qua kênh được xác thực; không gửi raw secrets vào room.
6. Bắt đầu **UTC timeline và evidence catalog**, ghi unknowns rõ ràng.

**Gate A:** Nếu key/event identity chưa rõ, **không tự khẳng định compromise đã xảy ra**. Vẫn có thể kích hoạt containment thận trọng theo risk.

### Phase B — Containment và bảo toàn chứng cứ

7. Cô lập compromised workload, revoke suspect principals/sessions/grants theo incident plan.
8. Chặn new-use key/secret bị nghi lộ nếu an toàn và cần thiết; đánh giá availability trước khi disable một shared KEK.
9. Bảo toàn KMS request IDs, IAM changes, storage/object access logs và artifacts có provenance.
10. Kiểm tra operator actions đã có **effective state**, không chỉ HTTP response.
11. Lập **key dependency graph**: KEK/DEK/ciphertexts/tenants; hoặc signing key/verifiers/artifacts.
12. Phân biệt containment completed với residual copies/data risk.

**Gate B:** Nếu đường lạm dụng còn hoạt động, tiếp tục emergency response; không gửi message “đã khắc phục hoàn toàn”.

### Phase C — Impact và notification assessment

13. Xác định data owners, tenants, partners, verifiers và services liên quan.
14. Phân loại impact: confidentiality/integrity/authenticity/availability, mức chắc chắn và khoảng thời gian.
15. Xác định raw material exposure, unauthorized key usage, DEK/plaintext exposure **riêng biệt**.
16. Legal/privacy/compliance đối chiếu **jurisdiction, role, data category, contract, deadline**.
17. Lập **recipient matrix** theo identity/contact registry đáng tin; ngăn tenant mix-up.
18. Chọn notice type: internal, partner action, customer update, regulator filing hoặc status page.
19. Định nghĩa phiên bản notice, required actions, contact và update cadence.

**Gate C:** Không công bố số records/tenants hoặc “không có ảnh hưởng” khi chưa có căn cứ.

### Phase D — Draft, review, approve

20. Dùng **approved facts** và phân biệt known/unknown, actions taken/ongoing.
21. Loại bỏ raw keys, tokens, PII không cần thiết, KMS exploitation details và tenant names sai audience.
22. Kiểm tra notice không yêu cầu khách gửi secret qua email hoặc dùng trust key nghi lộ để tự chứng thực.
23. Xác minh nội dung hành động khả thi: rotate secret, update verifier, monitor transactions, re-login, hoặc không action.
24. Legal/privacy review khi applicable; Security và key/data owners đối chiếu kỹ thuật.
25. Authorized publisher xác nhận notice ID/version/audience và kênh.

**Gate D:** Thiếu approval hoặc không chứng minh recipient list đúng → **BLOCK external publication**, nhưng vẫn tiếp tục internal response và assessment theo nghĩa vụ thực tế.

### Phase E — Phát hành và theo dõi hành động

26. Phát hành qua portal/email/provider/regulator channel **được xác thực**.
27. Ghi **sentAt, delivery status, audience, content digest, approver và operation ID**.
28. Khi gửi thất bại, retry/escalate theo policy; không đánh dấu delivered.
29. Phối hợp partner cutover: JWKS/trust updates, HMAC secret rotation, KMS grants/permissions.
30. Support team dùng approved FAQ; câu hỏi vượt facts được escalated thay vì tự đoán.
31. Theo dõi acknowledgement và **operational action completed** riêng.

**Gate E:** Email đã gửi không đồng nghĩa khách/đối tác đã thực hiện key rotation hoặc verifier update.

### Phase F — Cập nhật, closure và bài học

32. Phát hành follow-up khi phạm vi, trạng thái containment hoặc required action thay đổi.
33. Nếu notice cũ sai, phát hành **correction/supersede** có version và lý do.
34. Xác nhận migration/rotation/rewrap/reencrypt/restore đã hoàn thành theo **evidence**, không chỉ ticket status.
35. Đối chiếu compliance deadlines và các acknowledgement theo hợp đồng.
36. Đóng incident với residual risks, unknowns, lessons learned và owner của remediation.
37. Lưu **notice archive, delivery logs và evidence bundle** theo retention có phân quyền.
38. Diễn tập lại playbook và cập nhật tiêu chí escalation/communication.

**Gate F:** Closure được phép khi các nghĩa vụ và actions trong phạm vi incident đã được xử lý/handoff theo policy; **không đồng nghĩa mọi bản plaintext/DEK đã bị thu hồi khỏi bên ngoài**.

### 24.1. Sơ đồ trình tự phát hành thông báo

```mermaid
sequenceDiagram
    participant SOC as SOC / Incident Team
    participant IC as Incident Commander
    participant K as KMS/Data owners
    participant L as Legal/Privacy
    participant C as Comms Publisher
    participant R as Affected Recipient
    SOC->>IC: Report key signal, evidence refs, confidence
    IC->>K: Request key dependency/impact assessment
    K-->>IC: Facts, key scope, actions, known unknowns
    IC->>L: Determine obligations and deadline(s)
    L-->>IC: Approved scope and required communication
    IC->>C: Send approved facts + recipient matrix
    C->>C: Redact and validate notice version
    C->>R: Publish via authenticated channel
    C-->>IC: Sent/delivery evidence, not assumed read
    R-->>C: Acknowledge / execute partner key action if needed
    K-->>IC: New containment/impact findings
    IC->>C: Approve correction or follow-up
    C->>R: Versioned update
```

### 24.2. Điều kiện dừng khi thiếu dữ kiện

Không tự công bố nội dung chưa có bằng chứng nếu:

- Không biết **incident identity, affected key/resource purpose**.
- Một số tenants chỉ được đoán từ tên KMS key.
- Không thể xác minh **security contact/recipient**.
- Notice có raw key, tokens hoặc plaintext không cần thiết.
- Nội dung khẳng định “đã rotate” nhưng provider state chưa xác minh.
- Quyết định pháp lý vượt thẩm quyền của người soạn.
- Signing key bị nghi lộ lại là trust anchor duy nhất của kênh thông báo.

**Đối với nghĩa vụ thông báo có thời hạn**, việc chưa hoàn tất phân tích có thể cần **preliminary notice** với uncertainty và approval phù hợp, không phải tự ý im lặng quá hạn.

## 25. Anti-pattern trong truyền thông sự cố key

| Anti-pattern | Nguy cơ | Cách cải thiện |
|---|---|---|
| Gọi mọi KMS error là “key compromise” | Báo sai, mất uy tín và gây nhiễu | Triage theo event type/evidence |
| Nói “không có data impact” khi chưa quét logs | Kết luận vô căn cứ | Nêu unknowns và audit coverage |
| Thấy KMS principal bị chiếm nhưng bảo “KEK non-exportable nên an toàn” | Bỏ qua DEK/plaintext oracle | Đánh giá unauthorized key operations |
| Rotation KEK rồi thông báo data cũ “an toàn lại” | Raw DEK/plaintext đã copy vẫn nguy hiểm | Phân biệt rewrap, reencrypt, exposure |
| Dùng cùng signing key nghi lộ để ký notice trust update | Attacker có thể giả mạo notice | Trust channel/key độc lập |
| Gửi HMAC secret mới qua email hỗ trợ | Rò secret lần nữa | Authenticated secret provisioning |
| Đính kèm private key PEM để chứng minh leak | Tái phát tán key | Secure forensic artifact refs |
| Broadcast danh sách tenants bị ảnh hưởng cho tất cả | Cross-tenant disclosure | Recipient-scoped notices |
| Lấy địa chỉ nhận từ request không xác thực | Gửi nhầm hoặc phish | Verified contact registry |
| Dùng một mẫu không thay đổi cho mọi key purpose | Partner không biết cách thay trust/decrypt | Purpose-specific actions |
| Thông báo chỉ dùng từ “đã khắc phục” | Không biết chính xác containment/remaining risks | Ghi actions verified và residual risk |
| Không phân biệt unauthorized use với raw key exposure | Sai mức độ chắc chắn | Tách findings và confidence |
| Ghi số records = 0 khi chưa hoàn tất inventory | False reassurance | UNKNOWN riêng, gắn evidence |
| Coi notice generated là delivered | Bỏ sót người nhận | Track approve/sent/delivered/ack |
| Coi delivered là partner đã rotate | Verifier vẫn trust compromised key | Kiểm tra actual cutover metrics |
| Bỏ external review vì incident “chỉ là kỹ thuật” | Có thể bỏ nghĩa vụ thông báo | Legal/privacy/contract assessment |
| Áp thời hạn 72h phổ quát cho mọi incident | Sai nghĩa vụ thực tế | Xác minh jurisdiction/contract |
| Chờ postmortem xong mới báo nội bộ | Chậm containment | Internal escalation ngay theo trigger |
| Công bố exploit path khi chưa containment | Giúp attacker mở rộng tấn công | Threat-aware redaction và phân tầng |
| Sửa lặng lẽ notice v1 khi có facts mới | Mất audit và khách không biết thay đổi | Versioned correction/follow-up |
| Đóng incident mà không nói residual risk | Trấn an quá mức | Closure gồm limits, remediation owners |
| Cho operator bị nghi compromise tự duyệt notice | Conflict of interest | SoD, independent approval |
| Đăng raw KMS logs lên status page | Lộ principal, PII, token hoặc key refs | Sanitized external narrative |
| Không có kênh ngoài SSO đã bị chiếm | Không liên lạc được khi khẩn cấp | Out-of-band verified contacts |
| Nói đã destroy vì API trả 200 | Có thể mới schedule deletion | Verify effective provider state |
| Xóa public verifier key cùng private signing key | Không Verify được artifacts cũ | Retain trust evidence theo policy |
| Bỏ qua offline recipients | Người nhận vẫn dùng key cũ | Escalation/ack và compatibility plan |
| Chỉ mô tả confidentiality, bỏ authenticity/availability | Sai tác động key purpose | Triad + authenticity impact |
| Dùng một danh sách email cố định cho mọi case | Gửi sai người hoặc thiếu contacts | Dynamic audience từ trusted dependency map |
| Notice không có incident ID/version/update channel | Khó đối chiếu, dễ bị giả mạo | Stable reference và authenticated channel |

## 26. Checklist thông báo sự cố key

**A. Xác định sự kiện và mức chắc chắn**

- [ ] Có incident ID, event/detection timestamps với timezone/UTC rõ.
- [ ] Key ID/material version, provider/KMS/HSM, key purpose và security domain được xác minh.
- [ ] Tách **suspected/confirmed unauthorized use, raw material exposure và data exposure**.
- [ ] Không suy `UNKNOWN` thành `NONE` hoặc `0 affected records`.
- [ ] Blast radius được phân tích theo DEK/KEK, ciphertext, signed artifacts, verifiers, tenants và regions.
- [ ] Đã kiểm tra audit coverage, blind spots và khoảng thời gian không chắc chắn.
- [ ] Severity/urgency có lý do, không chỉ lấy từ tên thuật toán.

**B. Containment, key lifecycle và kỹ thuật**

- [ ] SOC/IC/key custodian/service owner được thông báo theo trigger nội bộ.
- [ ] Các grants/sessions bị nghi compromise đã được xử lý; có bằng chứng effective state.
- [ ] Không vô hiệu hóa một shared KEK gây mất Decrypt/DR mà không đánh giá availability.
- [ ] Có phương án phù hợp: rotate, rewrap DEK, replace DEK/reencrypt, revoke trust, restore.
- [ ] Với signing key, xác minh public verification material/certificate/PKI implications.
- [ ] Với HMAC/JWT, tính verifier grace period, cache, `kid`, token lifetime và replay.
- [ ] Kế hoạch containment không tuyên bố xóa được raw key/plaintext attacker đã sao chép.

**C. Đúng người và đúng kênh**

- [ ] Recipient groups lấy từ trusted tenant/partner/contact registry.
- [ ] Security/Legal/Privacy/Data owners xác nhận nội dung/đối tượng theo thẩm quyền.
- [ ] Có out-of-band channel nếu SSO/email/portal có thể đã bị chiếm.
- [ ] Partner cần rotate secret/trust nhận đúng integration ID và cách thực hiện.
- [ ] Thông báo tenant A không chứa tenants, object IDs hoặc contacts của B.
- [ ] Đã đánh giá nghĩa vụ thông báo theo **jurisdiction, contract, role, data type, timing thực tế**.
- [ ] Notice không dùng cùng một compromised key làm chứng cứ xác thực duy nhất.

**D. Nội dung thông điệp**

- [ ] Có notice ID, version, issuedAt, trạng thái và contact xác thực.
- [ ] Nêu rõ **known facts, unknowns, confirmed vs suspected**.
- [ ] Mô tả tác động theo confidentiality/integrity/authenticity/availability phù hợp.
- [ ] Các hành động đã thực hiện là **đã xác minh**, không chỉ đã request.
- [ ] Có required recipient actions hoặc nói rõ chưa cần hành động khi có căn cứ.
- [ ] Có next update/checkpoint và quy tắc correction/supersession.
- [ ] Không cam kết phục hồi/an toàn vượt quá evidence.
- [ ] Không chứa raw DEK/KEK/HMAC secret/private key, passwords, access tokens hoặc raw PII không cần thiết.
- [ ] Chi tiết exploit/KMS IAM/forensic logs nhạy cảm chỉ nằm trong restricted evidence.

**E. Phát hành và hậu kiểm**

- [ ] External notice có approval thật, không chỉ flag boolean do caller tự gán.
- [ ] Publisher được xác thực, recipient matrix được kiểm tra lần cuối.
- [ ] Generated/Approved/Sent/Delivered/Acknowledged/ActionCompleted được ghi riêng.
- [ ] Gửi thất bại có retry/escalation được phê duyệt, không tự đánh dấu success.
- [ ] Partner cutover được xác minh bằng **thực tế trust/secret acceptance**, không chỉ email.
- [ ] Có audit content/version/approver/delivery evidence, bảo vệ integrity và retention.
- [ ] Khi phát hiện facts mới, notice mới giải thích thay đổi; bản trước không bị sửa lặng lẽ.
- [ ] Closure xác nhận ownership của residual risks và remediation, không che unknowns.

## 27. Câu hỏi tự kiểm tra

**1. Thông báo sự cố key có phải lúc nào cũng là email gửi khách hàng không?**  
Không. Nó bao gồm **escalation nội bộ, điều phối KMS/HSM/IAM/PKI, thông báo đối tác, khách hàng và cơ quan có thẩm quyền khi có nghĩa vụ**, cùng cập nhật và hậu kiểm.

**2. KMS Decrypt spike có chứng minh raw KEK bị lộ không?**  
Không. Nó là signal cần kiểm tra. Có thể là job hợp lệ, principal bị chiếm hoặc misuse; raw key exposure là một finding riêng.

**3. Key non-exportable có loại bỏ rủi ro data exposure không?**  
Không. Principal bị lạm dụng có thể gọi Unwrap/Decrypt và nhận raw DEK hoặc kết quả phép toán.

**4. Vì sao phải phân biệt suspected với confirmed compromise?**  
Để vừa kích hoạt phản ứng kịp thời, vừa không đưa ra tuyên bố ngoài bằng chứng, đặc biệt khi liên quan data breach và nghĩa vụ thông báo.

**5. Raw DEK lộ và KEK rotation có làm dữ liệu cũ an toàn lại không?**  
Không. Rewrap cùng DEK không thu hồi bản raw DEK đã lộ; phải đánh giá reencrypt bằng DEK mới và các bản copy dữ liệu.

**6. Một KMS key bị Deleted có nhất thiết là sự cố rò rỉ dữ liệu không?**  
Không. Nó có thể là **availability/data loss** nếu dữ liệu cũ không còn mở được. Đánh giá evidence trước khi gọi là exposure.

**7. Ai cần biết trước tiên khi một private signing key bị nghi compromise?**  
SOC/IC, key custodian, dịch vụ ký và trust/PKI teams cần được kích hoạt; legal/comms/partners phụ thuộc tác động và hành động cần thiết.

**8. Tại sao phải dùng trust channel độc lập khi thông báo đổi signing key?**  
Nếu key cũ bị nghi lộ, attacker cũng có thể ký thông báo giả bằng key đó. Recipient cần identity/channel còn đáng tin để kiểm tra key mới.

**9. Public verification key cũ có nên bị xóa cùng private signing key không?**  
Không tự động. Có thể còn cần Verify chữ ký/token/hồ sơ lịch sử và giữ certificates/timestamp/revocation evidence.

**10. Một HMAC secret mới nên gửi cho đối tác bằng email không?**  
Không. Nên provision qua **authenticated secret-delivery channel/portal** theo policy; notice email chỉ dẫn cách thực hiện, không chứa raw secret.

**11. JWT `kid` có thể dùng để tin bất kỳ public key nào do token tự dẫn tới không?**  
Không. Verifier cần issuer/trust source đã cấu hình, algorithm allowlist và kiểm tra claims, không tin key URL tùy ý từ dữ liệu chưa xác thực.

**12. Khi nào cần thông báo khách hàng?**  
Khi tổ chức xác định có yêu cầu theo **luật/hợp đồng/chính sách/impact**, với quyết định và thẩm quyền phù hợp. Không có deadline chung áp cho mọi key incident.

**13. Có phải mọi key compromise luôn có hạn thông báo 72 giờ không?**  
Không. Thời hạn pháp lý phụ thuộc jurisdiction, vai trò, loại dữ liệu và điều kiện phát sinh nghĩa vụ; phải kiểm tra yêu cầu cụ thể.

**14. Vì sao phải lưu cả `detectedAt` và `eventOccurredAt`?**  
Vì sự kiện có thể diễn ra trước khi được phát hiện; việc dùng một timestamp gây sai chronology và đánh giá nghĩa vụ/thời hạn.

**15. `Finding.UNKNOWN` khác `Finding.NOT_CONFIRMED` thế nào?**  
UNKNOWN nghĩa chưa có kết luận; NOT_CONFIRMED nghĩa điều tra chưa có bằng chứng xác nhận tính đến thời điểm đánh giá. Cả hai không chứng minh sự kiện không xảy ra.

**16. Khi nào gửi notice sơ bộ?**  
Khi cần giúp recipients hành động sớm hoặc đáp ứng nghĩa vụ, trong khi điều tra chưa hoàn tất; phải nêu known/unknowns và dùng approval/kênh phù hợp.

**17. “Đã revoke IAM grant” có chứng minh mọi raw DEK đã bị xóa không?**  
Không. Nó có thể ngăn API calls mới qua grant ấy, không thu hồi DEKs/plaintext đã được sao chép.

**18. Tại sao không đính kèm raw KMS logs vào email khách hàng?**  
Logs có thể chứa PII, principal IDs, key references và thông tin khai thác nhạy cảm; dùng sanitized impact summary và secure evidence channel cho responders.

**19. Có nên gửi danh sách toàn bộ affected tenants cho mỗi tenant không?**  
Không. Điều đó có thể tạo **cross-tenant information leakage**. Recipient list phải dựa trên identity/scope riêng.

**20. Notification versioning có tác dụng gì?**  
Giúp kiểm tra nội dung đã phát, corrections, approvals, update history và ngăn sửa lặng lẽ bản notice mà khách đã nhận.

**21. Thông báo đã gửi thành công có nghĩa partner đã cập nhật JWKS/trust không?**  
Không. **SENT/DELIVERED/ACKNOWLEDGED/ACTION_COMPLETED** là các trạng thái khác nhau và cần đo riêng.

**22. Vì sao không dùng một kênh email đã bị nghi chiếm để phát notice quan trọng?**  
Vì attacker có thể mạo danh/sửa notice. Cần fallback **out-of-band verified contact** và trust channel độc lập.

**23. Nếu private key bị lộ, phải thông báo về các chữ ký cũ như thế nào?**  
Phân biệt artifacts hợp lệ trước sự cố, cửa sổ có nghi ngờ, chữ ký được xác nhận trái phép, cùng trust/timestamp/revocation evidence và actions cho verifier.

**24. KMS API trả 200 khi ScheduleDeletion có nghĩa key đã bị hủy?**  
Không. Có thể chỉ là **pending deletion**; notice phải phản ánh effective provider state.

**25. Vì sao severity và legal-notification trigger là hai khái niệm khác?**  
Severity đo mức ưu tiên ứng phó theo rủi ro vận hành; nghĩa vụ thông báo còn phụ thuộc điều kiện pháp lý/hợp đồng, dữ liệu và vai trò thực tế.

**26. Trước khi công bố số khách hàng bị ảnh hưởng, cần gì?**  
Phải kiểm tra key dependency graph, mapping DEK→ciphertext→tenant, log coverage, nguồn đếm và thời gian. Khi chưa đủ dữ liệu, ghi **chưa xác định**.

**27. Nếu phát hiện notice trước có số liệu sai thì làm sao?**  
Phát hành **correction với version mới**, nêu thay đổi và lý do, lưu bản trước trong audit; không sửa âm thầm.

**28. Notification engine có nên tự rotate/destroy key mỗi khi phát notice?**  
Không mặc định. Publication và cryptographic containment là workflows có quyền/rủi ro khác nhau; destructive actions phải theo IAM/change control/incident response riêng.

**29. Một incident đóng rồi có cần giữ notification evidence không?**  
Có, theo retention và nghĩa vụ audit phù hợp: notice content/version, approvals, recipient list, delivery records, corrections và linked incident evidence.

**30. Thông điệp cốt lõi khi thông báo sự cố key là gì?**  
**Đúng người nhận, đúng phạm vi đã có bằng chứng, đúng mức chắc chắn, qua kênh đáng tin, có hành động cụ thể và cập nhật khi facts thay đổi — tuyệt đối không đưa raw key/secret vào thông báo.**

## 28. Thuật ngữ nhanh và kết luận

| Thuật ngữ | Ý nghĩa |
|---|---|
| **Key incident** | Sự kiện nghi hoặc xác nhận ảnh hưởng confidentiality/integrity/authenticity/availability của khóa và key usage |
| **Key compromise** | Mất bí mật, kiểm soát hoặc khả năng sử dụng key theo mô hình threat cụ thể |
| **Unauthorized key use** | Phép toán key được thực hiện ngoài thẩm quyền |
| **Raw material exposure** | Byte khóa bí mật rời ranh giới được phép |
| **Data exposure** | Dữ liệu/DEK/plaintext bị truy cập hoặc công bố trái phép |
| **Suspected / Confirmed** | Nghi ngờ dựa trên signal / kết luận có evidence phù hợp |
| **UNKNOWN** | Chưa xác định, không tương đương “không có” |
| **Incident Commander** | Người điều phối quyết định và tiến trình ứng phó |
| **SOC/CSIRT** | Đội phát hiện, phân tích và ứng phó an ninh |
| **Key custodian** | Chủ thể quản lý vòng đời và custody của key |
| **DEK** | Data Encryption Key, mã hóa trực tiếp dữ liệu |
| **KEK** | Key Encryption Key, bảo vệ/wrap DEK |
| **Envelope encryption** | Mã hóa dữ liệu bằng DEK, bảo vệ DEK bằng KEK hoặc recipient scheme |
| **KMS/HSM** | Dịch vụ/thiết bị quản lý và thực hiện phép toán mật mã trên khóa |
| **Non-exportable** | Key material không thể xuất qua API được hỗ trợ; vẫn có thể bị lạm dụng operations |
| **Decryption oracle** | Dịch vụ bị dùng mở ciphertext/DEK ngoài quyền |
| **Rotation** | Chuyển sử dụng sang key/material version mới |
| **Rewrap** | Bọc lại cùng DEK dưới KEK hoặc recipient key khác |
| **Reencrypt** | Mã hóa lại dữ liệu, thường với DEK/nonce/tag mới |
| **Revocation** | Thu hồi permission/trust/grant theo scope và cơ chế |
| **Certificate/JWKS** | Vật liệu public key/trust phục vụ Verify theo giao thức |
| **HMAC** | MAC dùng shared secret để tạo/xác minh authentication tag |
| **Key fingerprint** | Dấu vân tay của public key cần gắn với trusted identity |
| **Notification trigger** | Điều kiện kích hoạt escalation/đánh giá phát hành thông báo |
| **Audience** | Nhóm người nhận được xác định theo key/data dependencies |
| **Preliminary notice** | Thông báo sơ bộ nêu known/unknowns và điều tra tiếp |
| **Correction/supersession** | Bản thông báo mới sửa/thay nội dung trước có version/provenance |
| **Chain of custody** | Bằng chứng ai thu thập, lưu, truy cập và xử lý forensic artifacts |
| **SoD** | Separation of Duties, phân tách người quyết định/thực hiện/phê duyệt |
| **Residual risk** | Rủi ro còn lại sau containment/remediation |
| **Delivery/acknowledgement** | Gửi/nhận/xác nhận thông báo; không tự đồng nghĩa hành động xong |
| **Evidence bundle** | Hồ sơ facts, timestamps, approvals, key/tenant scopes, notice history và audit |

**Thông báo sự cố key là một kiểm soát an ninh gắn trực tiếp với key revocation, compromise response và vận hành tin cậy.** Việc gửi thông điệp nhanh nhưng sai hoặc gửi đúng nội dung đến sai tenant có thể tạo thêm sự cố. Quy trình tốt bắt đầu bằng **evidence-backed triage**, phân biệt rõ nghi ngờ với kết luận, và liên kết key material/usage với **DEK/KEK, ciphertext, chữ ký/MAC, tenants, services và đối tác thực sự chịu ảnh hưởng**.

Trong vòng đời **tạo → cấp phát → lưu trữ → sử dụng → xoay vòng → thu hồi → hủy**, khi xảy ra sự cố phải điều phối **containment, IAM/KMS/HSM grants, rotation/rewrap/reencrypt, PKI trust updates, backup/DR và audit**. Thông báo cần tách **điều đã biết – chưa biết – đã khống chế – tác động còn lại – việc người nhận cần làm**, không nói “mọi dữ liệu an toàn” chỉ vì đổi KEK hoặc revoke một principal.

**Một thông báo đáng tin có incident ID/version, phạm vi và mức chắc chắn rõ, kênh xác thực, người có thẩm quyền duyệt, hành động khả thi, thời điểm cập nhật và bằng chứng phát hành.** Giữ raw keys/secrets ngoài email/ticket/status page; bảo vệ dữ liệu và danh tính giữa tenants; ghi lại corrections và hậu kiểm. Điều quan trọng nhất không phải số lượng thông báo đã gửi, mà là **đúng bên liên quan đã nhận được thông tin cần thiết để giảm thiểu rủi ro, không bị đưa tới kết luận vượt quá bằng chứng**.

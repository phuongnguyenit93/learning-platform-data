# Change risk: đánh giá rủi ro của thay đổi trong Security Assurance

**Change risk (rủi ro của thay đổi)** là khả năng một thay đổi đối với hệ thống, cấu hình, mã nguồn, dữ liệu, hạ tầng, quy trình hoặc phụ thuộc bên ngoài gây ra hậu quả không mong muốn, làm sai lệch các yêu cầu về bảo mật, tính toàn vẹn, khả dụng, quyền riêng tư hoặc khả năng vận hành. Trong **Change assurance**, nhiệm vụ không chỉ là phê duyệt cho phép thay đổi được thực hiện, mà là **xác định điều gì có thể sai, kiểm soát rủi ro theo mức tác động và thu thập bằng chứng sau triển khai rằng các mục tiêu an ninh vẫn được đáp ứng**.

Trong module **SECURITY_SECURITY_ASSURANCE**, Change risk kết nối risk assessment, security requirements, security controls, kiểm thử, audit và remediation với những thay đổi diễn ra liên tục trong SDLC và production. Một bản cập nhật không tạo ra finding mới trên scanner vẫn có thể làm giảm an toàn nếu vô hiệu hóa audit logging, mở rộng IAM role, làm lỗi mã hóa backup hoặc tạo một đường xuất dữ liệu không được threat model đề cập.

> Câu hỏi cốt lõi: **“Thay đổi này có thể làm sai yêu cầu bảo mật nào, phạm vi ảnh hưởng lớn đến đâu, bằng chứng trước và sau thay đổi có đủ để cho phép triển khai và xác nhận an toàn hay chưa?”**

**Change risk không đồng nghĩa change size.** Một thay đổi một dòng trong network policy có thể phơi bày toàn bộ database, trong khi một bản cập nhật nhiều nghìn dòng ở giao diện ít đặc quyền có thể có tác động an ninh thấp hơn. Phương pháp đánh giá phải dựa vào **mối đe dọa, tài sản, đường phụ thuộc, tác động nghiệp vụ và khả năng phát hiện/phục hồi**, thay vì chỉ đếm số dòng code hoặc thời gian triển khai.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Định nghĩa **change risk**, phân biệt rủi ro nội tại (*inherent risk*) và rủi ro còn lại (*residual risk*), phân biệt rủi ro của thay đổi với lỗi vận hành thông thường.
2. Nhận diện các chiều tác động: confidentiality, integrity, availability, identity, data protection, logging, resilience, compliance và phụ thuộc bên ngoài.
3. Phân tích **blast radius**, trust boundary, đường phụ thuộc và các thay đổi có khả năng tạo lỗi chung (*common-mode failure*).
4. Áp dụng quy trình đánh giá thay đổi dựa trên rủi ro từ đề nghị, impact analysis, phê duyệt, kiểm thử, rollout tới post-change verification.
5. Thiết kế checklist, các cổng kiểm soát (*change gates*) và phép kiểm tra tương xứng mức rủi ro; phân biệt standard, normal và emergency change khi tổ chức sử dụng các nhóm này.
6. Chuẩn bị rollout, canary, rollback hoặc forward fix an toàn và đánh giá những tình huống không thể rollback dữ liệu.
7. Xây dựng bộ bằng chứng có thể kiểm toán, theo dõi drift và đánh giá lại security assurance khi hệ thống thay đổi.
8. Phân tích một tình huống thay đổi IAM và một tình huống migration dữ liệu với quyết định GO/NO-GO có điều kiện.

---

## 2. Change risk là gì và những quyết định nào cần hỗ trợ?

Một **change** là bất kỳ điều chỉnh được quản lý nào làm thay đổi trạng thái hệ thống hoặc cách nó vận hành, chẳng hạn triển khai release, đổi cấu hình mạng, thay IdP, cập nhật schema, rotate key, thay nhà cung cấp, tăng quyền cho service account hay sửa quy trình xử lý sự cố.

**Change risk** được đánh giá theo các tình huống bất lợi có thể phát sinh vì thay đổi đó:

- **Tạo lỗ hổng mới:** sửa API route khiến kiểm tra tenant ownership bị bỏ qua.
- **Làm yếu control hiện có:** đổi cấu hình logging khiến một vùng production không gửi audit event.
- **Làm mất khả năng đáp ứng:** rotate khóa khiến hệ thống không giải mã được backup.
- **Tạo gián đoạn nghiệp vụ:** thay firewall rule cắt đường thanh toán hoặc backup.
- **Làm sai hoặc mất dữ liệu:** migration không tương thích ghi dữ liệu vào cột sai, rollback xóa bản ghi mới.
- **Tăng quyền quá mức:** cập nhật IAM policy từ quyền trên một bucket sang quyền trên cả account.
- **Làm thay đổi trách nhiệm:** chuyển workload sang nhà cung cấp mới nhưng thiếu điều khoản lưu giữ log, ứng phó sự cố hoặc quyền kiểm toán.

Kết quả đánh giá change risk cần giúp ra các quyết định:

| Quyết định | Câu hỏi bảo đảm |
|---|---|
| **Cho phép thiết kế thay đổi?** | Vấn đề và mục tiêu là gì, có phương án ít rủi ro hơn không? |
| **Cho phép triển khai?** | Những điều kiện kiểm soát và bằng chứng trước triển khai đã đạt chưa? |
| **Chọn chiến lược rollout?** | Canary, theo từng vùng hay toàn bộ; nếu thất bại ảnh hưởng bao nhiêu? |
| **Kích hoạt rollback hoặc containment?** | Trigger nào, ai có quyền quyết định, bước khôi phục có an toàn không? |
| **Xác nhận thay đổi hoàn tất?** | Hệ thống đang chạy đúng artifact/config và security controls còn hiệu lực? |
| **Chấp nhận rủi ro còn lại?** | Ai đủ thẩm quyền, giới hạn và thời hạn ra sao, tiếp tục giám sát thế nào? |

Đánh giá rủi ro của thay đổi khác với **risk assessment tổng thể** của hệ thống: change risk tập trung vào **mức chênh lệch** giữa trạng thái trước và sau thay đổi, cả những rủi ro mới lẫn rủi ro hiện hữu bị làm trầm trọng thêm. Tuy nhiên nó phải dựa trên risk register, yêu cầu nghiệp vụ và threat model đã có; không đánh giá một thay đổi như thể tồn tại tách rời kiến trúc.

## 3. Inherent risk, residual risk và mức độ tin cậy

Ba câu hỏi thường bị nhầm:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| **Inherent change risk** | Rủi ro của kịch bản thay đổi trước khi xét các biện pháp giảm thiểu đang được đánh giá | Đổi KMS key policy có thể làm mất quyền giải mã dữ liệu và backup |
| **Control effectiveness** | Biện pháp kiểm soát thực tế có giảm khả năng/tác động như kỳ vọng không? | Có thử giải mã bằng key version cũ/mới, có đường phục hồi khẩn cấp |
| **Residual change risk** | Rủi ro còn lại sau các biện pháp bảo vệ, với những giả định và giới hạn đã nêu | Rủi ro lỗi tương thích với một hệ thống bên thứ ba chưa test đầy đủ |
| **Assurance confidence** | Độ đáng tin của kết luận đánh giá dựa trên lập luận và bằng chứng | Test đúng release, dữ liệu đại diện, đủ đường phụ thuộc, review độc lập |

**Residual risk thấp không thể được khẳng định chỉ vì đã viết một kế hoạch rollback.** Cần xem rollback có chạy được, đủ quyền truy cập, dữ liệu tương thích và hoàn thành trong mức gián đoạn chấp nhận được hay không. Mặt khác, một kết luận có confidence cao có thể chỉ ra thay đổi **vẫn có rủi ro cao và chưa nên triển khai**.

Một hồ sơ tốt ghi cả **mức rủi ro**, **độ chắc chắn của đánh giá**, **bằng chứng hỗ trợ** và **rủi ro chưa kiểm chứng**, thay vì chỉ một nhãn “Low/Medium/High”.

## 4. Những loại thay đổi tác động mạnh đến bảo mật

Không phải mọi thay đổi đều cần cùng quy trình chuyên sâu. Phân loại ban đầu giúp chọn phép thử phù hợp.

| Loại thay đổi | Kịch bản rủi ro cần chú ý | Ví dụ evidence |
|---|---|---|
| **Application/code** | Bypass authz, injection, lỗi validation, business logic | Diff, code review, security tests, runtime smoke |
| **IAM/identity** | Privilege escalation, mất quyền dịch vụ, lỗi cấp/thu hồi | Role policy diff, access simulation, audit logs |
| **Network/ingress** | Mở cổng, thay trust boundary, vô hiệu microsegmentation | Firewall/IaC diff, flow validation, exposure checks |
| **Secrets/KMS/crypto** | Lộ khóa, mất khả năng giải mã, sai rotation | Key version mapping, decrypt test, log và rollback |
| **Data/schema** | Sai integrity, mất dữ liệu, tăng thời gian downtime | Migration rehearsal, checksum, row counts, reconciliation |
| **Infrastructure/cloud** | Thay vùng, account, control plane, image và phụ thuộc | Architecture diff, artifact integrity, configuration state |
| **CI/CD/supply chain** | Artifact không tin cậy, quyền deploy quá rộng, thiếu signing | Pipeline policy, provenance, approval, artifact verification |
| **Logging/monitoring** | Blind spot, thiếu dấu vết audit, alert không phát | Test event end-to-end, ingestion count, alert test |
| **Backup/DR** | Không restore, sai RTO/RPO, failback không an toàn | Restore drill, dependency tests, dữ liệu và IAM checks |
| **Third-party/vendor** | Mất quyền kiểm toán, API incompatibility, thiếu SLA | Vendor assessment, contracts, integration tests |
| **Process/policy** | Approval bypass, trách nhiệm không rõ, exception sai quyền | Policy version, walkthrough, operating evidence |

Cùng một change có thể ảnh hưởng **nhiều lớp**. Ví dụ đổi IdP có thể làm thay đổi MFA, trust của token, cấp quyền, hệ thống log, tài khoản dịch vụ, đường break-glass và khả năng khôi phục DR. Vì vậy đánh giá phải xét quan hệ giữa các control, không chỉ component được sửa.

## 5. Xác định phạm vi và blast radius của thay đổi

**Blast radius** là tập tài sản, chức năng, người dùng hoặc dữ liệu có thể chịu tác động khi thay đổi thất bại hoặc bị khai thác. Không chỉ cần biết “đổi service nào” mà còn phải biết **service đó có thể gây hiệu ứng gì cho nơi khác**.

### 5.1. Bản đồ đối tượng chịu ảnh hưởng

Một phạm vi change nên ghi:

- Service/business capability, owner và tác động đến các quy trình cốt lõi.
- Production/staging/DR, cloud account, region, cluster, network segment và tenant.
- Data classification, lượng dữ liệu, customer segment và các luồng chia sẻ.
- IdP, IAM roles, secrets, KMS, DNS, database, API gateway và monitoring dependency.
- Các dependency upstream/downstream, queue, cache, batch jobs, webhooks, vendor APIs.
- Cơ chế rollout/canary, bản cũ còn chạy, điểm rollback và trạng thái dữ liệu tương thích.
- Thời kỳ triển khai, lượng traffic lúc thay đổi, lịch backup/DR và các thay đổi khác đang diễn ra.

Một cấu hình trên thư viện dùng chung có thể tác động nhiều ứng dụng hơn những mục được ghi trong change ticket. Đối chiếu **inventory, IaC, runtime dependency và owner** để xác minh phạm vi.

### 5.2. Các chiều cần khảo sát

| Chiều blast radius | Câu hỏi |
|---|---|
| **Data** | Có đọc/ghi/xóa dữ liệu quan trọng? Dữ liệu có thể được phục hồi đúng điểm không? |
| **Privilege** | Principal nào có thêm hoặc mất quyền? Có quyền kế thừa và tài khoản khẩn cấp không? |
| **Exposure** | Có mở đường từ Internet/tenant khác sang nội bộ không? |
| **Availability** | Có tạo single point of failure, timeout, chậm queue hay mất kết nối? |
| **Integrity** | Có gây sai schema, xử lý lặp, split-brain hoặc mất thứ tự giao dịch? |
| **Observability** | Có khiến log/alert/trace hoặc security telemetry bị thiếu không? |
| **Recovery** | Có phá backward compatibility, backup decrypt, rollback/failback không? |
| **Shared dependency** | Có ảnh hưởng nhiều dịch vụ do IdP, KMS, DNS, CI hoặc cloud account chung? |

### 5.3. Sơ đồ minh họa

~~~mermaid
flowchart LR
    A["Change: rotate signing keys at IdP"] --> B["Token issuing"]
    B --> C["API Gateway"]
    B --> D["Backend services"]
    B --> E["Batch jobs"]
    A --> F["KMS / key distribution"]
    C --> G["Customer transactions"]
    D --> H["Authorization checks"]
    E --> I["Data processing"]
    F --> J["DR / recovery trust"]
    H --> K["Security audit logs"]
~~~

Nếu nhóm chỉ kiểm tra việc IdP ký token mới thành công mà chưa kiểm tra gateway, batch jobs và DR, phạm vi đánh giá **chưa đủ** cho một quyết định có thể ảnh hưởng toàn hệ thống.

## 6. Phân tích những thay đổi làm vượt trust boundary

Một **trust boundary** là ranh giới giữa các vùng khác nhau về mức tin cậy, quyền, dữ liệu hoặc cơ chế xác thực. Thay đổi đi qua ranh giới này thường cần scrutiny cao hơn.

Ví dụ:

- Mở một API nội bộ ra Internet hoặc cho đối tác.
- Cho phép một workload truy cập secrets của service khác.
- Chuyển database sang account khác có chính sách IAM/KMS mới.
- Cho phép admin production đăng nhập qua kênh chưa có MFA tương đương.
- Thay đổi logic xác định tenant từ token claim sang query parameter.
- Thêm cơ chế export bulk data từ một hệ thống vốn chỉ có truy vấn đơn lẻ.
- Mở trust relationship giữa hai môi trường hoặc hai nhà cung cấp.

Mô hình hóa theo dữ liệu:

~~~text
Before:
  User -> AuthN -> API policy -> Service -> DB record
  (tenant identity được lấy từ token đã xác minh)

After:
  User -> AuthN -> New gateway -> Service -> DB record
  (tenant identifier có thể truyền từ request header)

Risk question:
  Header có được chứng thực/bảo vệ tại gateway không?
  Service có tin giá trị do client tự đặt không?
  Route khác có bỏ qua new gateway được không?
  Log và audit trail có còn ghi đúng principal/tenant không?
~~~

Một thay đổi nhìn như “di chuyển trách nhiệm sang gateway” có thể tạo **bypass** nếu backend tin dữ liệu không đáng tin hoặc có đường truy cập thẳng. Cần thử luồng đầu-cuối trên đúng cấu hình.

## 7. Phương pháp đánh giá rủi ro dựa trên kịch bản

Chấm điểm rủi ro chỉ có ích sau khi xác định **sự kiện có thể xảy ra**. Một câu “deployment risk = High” không đủ để chọn cách giảm thiểu.

### 7.1. Viết risk statement

Mẫu:

> **Do [change] trong điều kiện [context/threat], [failure/abuse scenario] có thể xảy ra, dẫn tới [security/operational impact] trên [assets/business process], vì [dependency/weakness].**

Ví dụ:

> Do thay policy KMS khi chuyển vùng storage, workload DR có thể không giải mã được backup nếu vai trò khôi phục không có quyền dùng key version cũ, làm chậm phục hồi và có khả năng vượt RTO.

Hoặc:

> Do thay cấu hình ingress từ allowlist sang broad CIDR, endpoint quản trị có thể được truy cập từ ngoài mạng được duyệt, làm tăng khả năng tấn công và lạm dụng quyền.

Mỗi kịch bản cần nối với điều kiện kiểm thử hoặc biện pháp quản trị, không chỉ ghi vào bảng để đủ thủ tục.

### 7.2. Ước lượng tác động và khả năng

Một mô hình định tính ví dụ:

| Tác động | Minh họa |
|---|---|
| **Low** | Gián đoạn nhỏ, không ảnh hưởng dữ liệu nhạy cảm, có đường phục hồi đơn giản |
| **Medium** | Ảnh hưởng một dịch vụ không trọng yếu hoặc một nhóm người dùng giới hạn |
| **High** | Gián đoạn nghiệp vụ chính, mất/biến đổi dữ liệu quan trọng, lộ dữ liệu nhạy cảm |
| **Critical** | Ảnh hưởng diện rộng, quyền đặc biệt ở quy mô lớn, rủi ro nghiêm trọng đến nghĩa vụ/trust hoặc khả năng phục hồi |

Khả năng xảy ra có thể xem xét **độ phức tạp của thay đổi**, mức độ mới, phụ thuộc, kinh nghiệm triển khai, threat exposure, test coverage, lịch sử incident và khả năng cùng lỗi. Không có một thang xác suất chung chính xác cho mọi môi trường. Những nhãn này là **ví dụ**, cần dùng định nghĩa risk methodology của tổ chức.

Độ dễ phát hiện và khả năng phục hồi cũng quan trọng. Một lỗi khiến logging tắt nhưng dịch vụ vẫn trả HTTP 200 có thể khó phát hiện hơn lỗi gây crash. Rollback dễ thực hiện trong ba phút có thể giảm tác động; ngược lại schema migration không thể đảo ngược có thể làm tăng mức rủi ro đáng kể.

### 7.3. Risk register thay đổi

| Scenario | Inherent risk | Controls dự kiến | Residual risk / uncertainty |
|---|---|---|---|
| Sai policy IAM mở quyền đọc secret | High | Policy lint, diff review, access simulation, canary | Cần kiểm tra service account ngoài inventory |
| KMS rotation làm hỏng restore | High | Decrypt test trên backup cũ/mới, failback key plan | Chưa thử vendor backup connector |
| Schema migration ghi dữ liệu sai | Critical | Rehearsal trên dữ liệu đại diện, reconciliation, staged rollout | Rollback dữ liệu còn hạn chế |
| Thay logging pipeline mất sự kiện | High | Test event end-to-end và alarm khi ingestion dừng | Một legacy source chưa có đối soát đầy đủ |

**Rủi ro còn lại** phải có lý do, owner và bằng chứng. Nếu thiếu thông tin trọng yếu, kết quả có thể là **chưa đủ cơ sở đánh giá**, không nên tự hạ rủi ro vì công việc đang gấp.

## 8. Phân loại change để chọn mức kiểm soát

Một số tổ chức dùng nhóm **standard**, **normal** và **emergency change**, nhưng tên và quy tắc có thể khác. Không được suy ra một loại “standard” mặc định ít rủi ro nếu điều kiện thay đổi vượt ngoài mẫu đã chuẩn hóa.

| Loại thay đổi tham khảo | Đặc điểm | Cách kiểm soát |
|---|---|---|
| **Standard** | Lặp lại, phạm vi ổn định, thủ tục có sẵn, rủi ro và test đã được phê duyệt | Kiểm tra điều kiện đúng mẫu, giám sát, phát hiện ngoại lệ |
| **Normal** | Cần impact/risk review riêng cho phiên thay đổi | Đánh giá, approve, test, rollback, theo dõi |
| **Emergency** | Cần hành động nhanh để giảm sự cố/rủi ro trước mắt | Quy trình ủy quyền khẩn cấp, evidence tối thiểu thiết yếu, review hậu triển khai |
| **Material/high-risk** | Ảnh hưởng control trọng yếu, dữ liệu hoặc blast radius lớn | Review sâu, thử độc lập, phân giai đoạn, quyền phê duyệt cao hơn theo quy tắc tổ chức |

Một change được lặp lại nhiều lần có thể trở thành standard sau khi có **bằng chứng rủi ro và runbook đủ tốt**, nhưng nếu thay asset, control, dữ liệu hay preconditions thì cần đánh giá lại. Emergency change không phải giấy phép bỏ audit trail, không thực hiện post-change verification hoặc không khắc phục rủi ro do chính thay đổi khẩn cấp tạo ra.

## 9. Quy trình Change Assurance có thể kiểm chứng

~~~mermaid
flowchart TD
    A["Change request + business/security objective"] --> B["Scope và dependency inventory"]
    B --> C["Risk scenarios + threat/control impact"]
    C --> D["Test plan, rollout, rollback và monitoring"]
    D --> E{"Pre-change evidence đủ và approval đúng cấp?"}
    E -- "Không" --> F["NO-GO / bổ sung hoặc risk decision"]
    E -- "Có" --> G["Controlled deployment"]
    G --> H["Health, functional, security & data checks"]
    H --> I{"Meets acceptance and guardrails?"}
    I -- "Không" --> J["Containment / rollback / forward fix theo kế hoạch"]
    J --> K["Incident/change review"]
    I -- "Có" --> L["Post-change verification và evidence"]
    L --> M["Assurance update, closure và monitoring"]
    K --> M
    M --> N["Feedback vào risk register, tests và runbook"]
~~~

**Đầu vào:** thay đổi có owner, lý do, danh mục tài sản, security requirements, ảnh hưởng và người có quyền quyết định.

**Trước triển khai:** có risk assessment, risk appetite/threshold thích hợp, test plan, tiêu chí GO/NO-GO, kế hoạch thông tin, rollback/forward fix và verification.

**Trong triển khai:** ghi ai làm gì, lúc nào, vào đâu, có đúng phạm vi được phê duyệt không; giám sát guardrails và chặn mở rộng ngoài kế hoạch.

**Sau triển khai:** kiểm tra ứng dụng, dữ liệu, IAM, logging, DR, các control được đánh giá là có thể bị ảnh hưởng; lập bằng chứng có nguồn và cập nhật assurance status.

Nếu điều kiện chặn chưa đạt, kết luận phù hợp là **NO-GO hoặc chờ phê duyệt quyết định rủi ro**. Không nên báo “passed” chỉ vì thao tác triển khai không trả lỗi.

## 10. Thiết kế cổng GO/NO-GO theo mức rủi ro

Một cổng thay đổi không phải danh sách checkbox mang tính hình thức; nó phải gắn với kịch bản rủi ro và điều kiện đo được.

### 10.1. Các cổng thường gặp

| Gate | Nội dung kiểm tra | Bằng chứng phù hợp |
|---|---|---|
| **G1: Scope & impact** | Tài sản, người dùng, môi trường, dependency và trust boundary đủ rõ | Inventory, architecture diff, blast-radius review |
| **G2: Risk & ownership** | Kịch bản rủi ro, mức tác động, phương án xử lý, owner và người duyệt | Risk assessment, change approval, exception link |
| **G3: Security requirements** | Control trọng yếu có tiêu chí nghiệm thu sau thay đổi | Mapping requirement–control–test |
| **G4: Test readiness** | Positive/negative, regression, integration và security tests phù hợp | Kết quả CI, test plan, vulnerability/security review |
| **G5: Deployment integrity** | Artifact đáng tin, version, quyền triển khai và supply-chain controls | Build provenance, image digest, change authorization |
| **G6: Rollout/rollback** | Cơ chế giảm blast radius, điều kiện dừng và đường phục hồi đã được thử | Rehearsal, runbook, canary/rollback decision |
| **G7: Observability** | Có chỉ số nghiệp vụ và an ninh để phát hiện lệch mục tiêu | Synthetic tests, SIEM events, monitoring coverage |
| **G8: Post-change verification** | Bằng chứng chứng minh hệ thống thật đang đạt tiêu chí | Runtime config, tests, logs, reviewer sign-off |

Các gate có thể được tự động hóa một phần trong CI/CD và change workflow, nhưng phải có cơ chế xem xét trường hợp **tool không bao phủ đúng phạm vi**. Một cổng “SAST xanh” chưa chứng minh an toàn IAM, data migration hoặc khả năng phục hồi.

### 10.2. Điều kiện chặn trọng yếu

Với change rủi ro cao, một số điều kiện nên là **bắt buộc** theo chính sách tổ chức. Ví dụ:

- Không có phương án khôi phục dữ liệu chấp nhận được khi thay đổi có khả năng ghi đè dữ liệu không đảo ngược.
- Không chứng minh được người/role triển khai có quyền phù hợp hoặc không có phê duyệt cần thiết.
- Thiếu phép thử xác thực/phân quyền cho thay đổi đi qua trust boundary.
- Monitoring không đủ để phát hiện trạng thái lỗi vốn là tiền đề của rollback.
- Một backup hoặc đường phục hồi bắt buộc chưa từng được restore thử ở điều kiện phù hợp.

Không nên “bù điểm” bằng hàng chục test giao diện PASS khi một gate bảo vệ dữ liệu trọng yếu đang FAIL.

## 11. Threat modeling ở phạm vi thay đổi

Không nhất thiết làm lại toàn bộ threat model cho mỗi commit. Tuy nhiên change đáng kể cần **delta threat modeling**: so trạng thái trước và sau để tìm các attack path, trust boundary và security assumptions mới hoặc bị thay đổi.

Một quy trình rút gọn:

1. Vẽ data flow trước/sau cho thành phần thay đổi.
2. Nhận diện principal, role, resource, dữ liệu nhạy cảm và trust boundaries mới.
3. Tìm abuse cases: ai có thể gọi API, tạo dữ liệu, sửa tham số, lạm dụng quyền, làm sai log?
4. Xét lỗi vô tình: cấu hình trôi, timeout, retry, migration lỗi, thiếu backup.
5. Kiểm tra control gắn với từng đường: authn, authz, validation, encryption, integrity, logging, detection, DR.
6. Chuyển các threat quan trọng thành **test hoặc acceptance criteria**, có owner.
7. Ghi những threat ngoài phạm vi và quyết định residual risk.

Ví dụ đổi từ lưu file riêng theo tenant sang shared object storage:

| Câu hỏi | Trước | Sau |
|---|---|---|
| Ranh giới dữ liệu | Storage riêng theo tenant | Dùng chung bucket và path prefix |
| Authorization | Bucket/role riêng | Policy theo tenant và object prefix |
| Nguy cơ mới | Sai quyền trên một tenant | Một policy lỗi có thể lộ nhiều tenant |
| Test cần thêm | Đọc/ghi trong tenant | Cross-tenant object access, signed URL, listing, backup |
| Evidence | Config IAM và test cũ | Config diff, policy evaluation, negative tests, logs mới |

Thay đổi giúp tiết kiệm tài nguyên nhưng làm tăng blast radius có thể vẫn được chấp nhận nếu control và mức rủi ro còn lại được chứng minh phù hợp. **Đánh giá rủi ro không đồng nghĩa luôn từ chối thay đổi.**

## 12. Kiểm thử trước thay đổi: kiểm tra những gì?

Bộ test nên bắt nguồn từ **các failure scenarios đã xác định**, không chỉ từ chức năng mới.

### 12.1. Functional và regression

- Luồng nghiệp vụ chính và dữ liệu vào/ra ở điều kiện bình thường.
- Trường hợp biên, retry, timeout, idempotency, batch job và async event.
- Backward compatibility với client và service phiên bản cũ.
- Performance/load của các luồng có thể tăng đáng kể.
- Failover và phục hồi khi thay đổi dependency, network hoặc storage.

### 12.2. Security tests

- **Authentication:** token signature, expiry, audience, MFA và các kênh khẩn cấp khi liên quan.
- **Authorization:** quyền trên object/tenant, role đặc biệt, policy inheritance, đường bypass.
- **Data protection:** TLS, mã hóa at rest, key/secret access, dữ liệu trong log.
- **Supply chain:** build integrity, package source, dependency vulnerability và quyền của pipeline.
- **Logging/detection:** test event đi từ nguồn đến SIEM, alert phát khi điều kiện được giả lập an toàn.
- **Configuration drift:** policy thực tế so với baseline, security defaults có còn hiệu lực?
- **Operational security:** credential rotation, break-glass, incident response, backup/DR.

### 12.3. Negative tests và positive tests

Một security fix đổi policy IAM cần **negative tests** để xác minh tài khoản ngoài quyền không truy cập được, nhưng cũng cần **positive tests** để xác nhận service đúng quyền vẫn hoạt động. Nếu tất cả request đều bị từ chối, có thể đã giảm một nguy cơ truy cập trái quyền nhưng làm hỏng nghiệp vụ.

Đối với thay đổi production nhạy cảm, nên dùng tài khoản và dữ liệu thử được phê duyệt, môi trường đại diện và những phương pháp xác minh không gây hại. Không thực hiện thử nghiệm tấn công phá hoại hoặc migration dữ liệu thật khi chưa có phê duyệt, giới hạn và cơ chế khôi phục.

## 13. Rollout an toàn: giảm blast radius trong khi triển khai

Chiến lược rollout có thể giảm xác suất và tác động của lỗi, nhưng không loại bỏ nghĩa vụ xác minh.

| Chiến lược | Ưu điểm | Điểm cần chú ý |
|---|---|---|
| **Canary** | Thử với tỷ lệ traffic hoặc số instance nhỏ | Canary phải đại diện; không nên chỉ dùng user ít quyền nếu rủi ro ở admin |
| **Blue–green** | Có hai môi trường để chuyển traffic | State/data migration và dependency dùng chung vẫn có thể không rollback |
| **Rolling deployment** | Giảm gián đoạn, triển khai từng instance | Tương thích giữa version cũ/mới, queue, session và cache |
| **Feature flag** | Tắt chức năng mới khi có lỗi | Flag phải có chủ sở hữu, quyền, trạng thái nhất quán và không tạo đường bypass |
| **Region/account staged rollout** | Hạn chế ảnh hưởng theo vùng/tài khoản | Rủi ro lệch cấu hình hoặc failover sang vùng chưa tương thích |
| **Shadow/dry-run** | Quan sát behavior trước khi thực thi toàn bộ | Không được ghi dữ liệu nhạy cảm hoặc tạo side effect ngoài ý muốn |

Một canary báo “không lỗi HTTP” chưa đủ nếu thay đổi làm sai kết quả giao dịch, lộ dữ liệu trong log hoặc bỏ kiểm tra authorization. **Guardrails phải đo thuộc tính có thể bị ảnh hưởng**, gồm cả tín hiệu bảo mật.

### 13.1. Guardrails theo kịch bản

Ví dụ đổi authorization policy:

~~~text
Pre-change:
  - Baseline allowed/denied requests theo role và tenant.
  - Baseline login failures, privilege events, latency.
  - Xác minh log từ mọi account liên quan đến SIEM.

During canary:
  - Negative test từ tenant sai phải bị từ chối, không lộ object data.
  - Positive test của user hợp lệ phải thành công.
  - Tăng 5xx/4xx bất thường vượt ngưỡng được duyệt => điều tra/dừng.
  - IAM changes và policy denials phải được ghi log.

Before full rollout:
  - Kết quả canary phù hợp criteria, không có blocker.
  - Người được ủy quyền xác nhận tiếp tục.

After rollout:
  - Runtime policy/version ở tất cả tài sản thuộc scope được xác nhận.
  - Repeat security tests và giám sát cửa sổ đủ đại diện.
~~~

Ngưỡng, thời gian chờ và tiêu chí dừng phải được phê duyệt cho hệ thống cụ thể; không có một tỷ lệ canary hoặc một ngưỡng 5xx phù hợp với mọi dịch vụ.

## 14. Rollback có thể thất bại: phải đánh giá rủi ro của chính rollback

**Rollback** không phải luôn là đường về trạng thái an toàn. Một số thay đổi gây tác động không đảo ngược hoặc tạo trạng thái hỗn hợp.

### 14.1. Các vấn đề điển hình

- **Schema/data migration:** release cũ không đọc được schema mới; rollback code nhưng data đã biến đổi.
- **Key rotation:** backup hoặc token cũ không được giải mã/xác minh nếu key version cũ bị vô hiệu quá sớm.
- **IAM tightening:** rollback mở lại quyền không an toàn; hoặc khóa nhầm tài khoản dùng thực hiện rollback.
- **Network/DR:** chuyển primary qua lại có thể gây split-brain, trùng ghi hoặc mất dữ liệu.
- **Feature flag:** tắt UI không xóa dữ liệu đã được tạo bởi feature.
- **Third-party API:** provider đổi trạng thái, khách hàng không thể tự khôi phục endpoint cũ.

Cần thiết kế:

1. **Điểm khôi phục** và bản backup đã thử với dữ liệu đại diện.
2. **Compatibility window** giữa version cũ và mới; khi cần dùng expand–migrate–contract.
3. **Forward-fix strategy** nếu không thể quay lại an toàn.
4. **Decision authority** và điều kiện dừng/downgrade/cô lập.
5. **Data reconciliation** sau rollback/forward fix.
6. **Audit trail** của quyết định và các thao tác.

Đối với hành động ảnh hưởng dữ liệu, không nên chỉ kiểm tra “service starts” sau rollback; phải kiểm tra **tính toàn vẹn và nghiệp vụ**.

### 14.2. Rollback vs forward fix

| Tình huống | Rollback có phù hợp? | Tiêu chí cần xác minh |
|---|---|---|
| UI bug không thay data contract | Có thể dễ | Route/version/behavior cũ hoạt động |
| Network policy khiến API timeout | Có thể, nếu còn đường quản trị | Network exposure không mở quá quyền, logs và traffic ổn |
| Migration dữ liệu không đảo ngược | Có thể không | Restore/reconciliation, kết quả dữ liệu, nghiệp vụ |
| Lộ credential | Quay lại secret cũ có thể nguy hiểm | Rotation, revoke, session invalidation, monitoring |
| Security patch fix CVE | Rollback có thể mở lại lỗ hổng | Risk decision, containment, phương án forward fix |

Một kế hoạch rollback đáng tin cần **được kiểm tra** và chỉ rõ điều kiện mà rollback bị cấm hoặc cần phê duyệt riêng.

## 15. Emergency change và security assurance trong áp lực thời gian

Khi đang có incident nghiêm trọng, tổ chức có thể phải thay cấu hình nhanh để giảm thiệt hại. Tuy nhiên quy trình khẩn cấp cần giữ những yếu tố tối thiểu:

- Người có thẩm quyền kích hoạt emergency change và người làm, được ghi nhận.
- Phạm vi, mục tiêu và hành động dự kiến; giới hạn quyền khi thao tác.
- Các kịch bản rủi ro trọng yếu và biện pháp giảm thiểu nhanh.
- Test quan trọng nhất trước khi làm nếu khả thi, ví dụ xác nhận tài khoản vận hành vẫn truy cập được.
- Kế hoạch thông báo, giám sát và điều kiện rollback/containment.
- Ghi log, thời điểm, phiên bản, thao tác thực tế và người phê duyệt.
- **Post-change review** và bổ sung evidence sau khi tình huống đã ổn định.
- CAP để xử lý các sai khác tạm và quyền/cổng mở khẩn cấp.

Ví dụ emergency block một domain có dấu hiệu độc hại phải cân nhắc tính đúng của indicator, ảnh hưởng đến dependency hợp lệ và khả năng rollback. Emergency không tự nghĩa là được phép vô hiệu logging hoặc bỏ mọi phân tách nhiệm vụ.

Nếu một biện pháp khẩn cấp tạo ngoại lệ đối với security baseline, quản lý ngoại lệ theo phạm vi, thời gian, quyền phê duyệt và điều kiện kết thúc được tổ chức cho phép. **Không dùng nhãn emergency để hợp thức hóa mọi thay đổi lâu dài.**

## 16. Post-change verification: điều gì mới được tính là hoàn tất?

Quá trình triển khai thành công về mặt công cụ chỉ là một bằng chứng. Trước khi kết luận change thành công, cần xác minh:

1. **Đúng artifact/config:** đối chiếu commit, image digest, policy version, runtime instance/region/account.
2. **Đúng phạm vi:** không có instance canary hoặc vùng dự phòng còn bản không tương thích.
3. **Chức năng:** luồng nghiệp vụ chính, tích hợp và data contract hoạt động theo tiêu chí.
4. **Bảo mật:** IAM, authn/authz, network, encryption, keys, secrets, audit logging và monitoring không suy giảm ngoài các ngoại lệ được duyệt.
5. **Data integrity:** số bản ghi, checksum/đối soát, queue, transaction side effects, dữ liệu không trùng/mất.
6. **Hiệu năng/availability:** latency, error rate, throughput, backlog và khả năng phục hồi phù hợp.
7. **Regression:** negative và positive tests cho các control bị ảnh hưởng.
8. **Residual risk:** vấn đề còn tồn tại được ghi, owner và thời hạn; nếu cần approval, phải có trước khi tuyên bố chấp nhận.
9. **Sign-off:** reviewer có năng lực và quyền phù hợp kết luận theo phạm vi.
10. **Follow-up:** tiếp tục quan sát ở cửa sổ phù hợp, có trigger đánh giá lại.

Không nhất thiết tất cả change phải được thử bằng cùng số lượng phép kiểm tra; **bộ kiểm tra phải phù hợp với rủi ro và loại thay đổi**. Một điều chỉnh nhãn giao diện không cần full DR drill nếu không ảnh hưởng recovery, nhưng thay KMS hoặc backup policy có thể cần thử restore, không chỉ smoke test UI.

### 16.1. Phân biệt các trạng thái

| Trạng thái | Có thể khẳng định | Chưa thể khẳng định |
|---|---|---|
| **PLANNED / APPROVED** | Kế hoạch được xem xét/phê duyệt | Thay đổi đã chạy đúng |
| **IMPLEMENTED** | Thao tác triển khai đã thực hiện | Hệ thống đáp ứng criteria mới |
| **TECHNICALLY VALIDATED** | Kiểm thử thành phần hoặc artifact đạt | End-to-end và vận hành trong mọi scope |
| **POST-CHANGE VERIFIED** | Bộ tiêu chí đã duyệt đạt trong phạm vi và thời điểm | Mọi kịch bản chưa thử đều an toàn |
| **PARTIALLY VERIFIED** | Một phần scope/test đạt | Toàn bộ thay đổi đạt |
| **NOT DEMONSTRATED** | Chưa đủ bằng chứng | Không tự kết luận lỗi không tồn tại |
| **FAILED / ROLLED BACK** | Có tiêu chí không đạt hoặc quyết định khôi phục | Rollback đã giải quyết mọi side effect nếu chưa kiểm tra |

Một change có thể “deployment successful” nhưng “security verification failed”. Hai kết luận nên tồn tại riêng để tránh số liệu đẹp nhưng thực tế không đảm bảo.

## 17. Evidence và truy vết trong change assurance

Bộ bằng chứng tốt nối từ yêu cầu tới quyết định:

~~~text
Risk / Security objective
          ↓
Change request + impacted assets
          ↓
Requirements + baseline controls
          ↓
Risk scenarios / threat impact
          ↓
Test plan + approval / exceptions
          ↓
Code, config, IaC, artifact, deployment
          ↓
Post-change security / functional / data verification
          ↓
Risk decision / assurance conclusion
          ↓
Monitoring, incident/finding, CAP và review
~~~

Một **change assurance record** nên có:

| Trường | Ý nghĩa |
|---|---|
| Change ID, version | Mã duy nhất, lịch sử phiên bản |
| Requested goal & business owner | Tại sao cần thay đổi và ai sở hữu kết quả |
| Asset/tenant/region/role inventory | Phạm vi thực |
| Baseline | Cấu hình, controls, chỉ số và bản trước thay đổi |
| Risk scenarios | Sự kiện bất lợi, khả năng/tác động, uncertainty |
| Requirements & acceptance | Tiêu chí chức năng, bảo mật, availability/data |
| Planned controls | Tests, rollout, guardrails, rollback/forward fix |
| Approvals and exceptions | Ai phê duyệt, ngoại lệ nào, thời hạn |
| Build/deploy evidence | Commit, artifact, image digest, environment, timestamp |
| Verification | Test ID, expected/actual, kết quả, source evidence |
| Decision & reviewer | GO/NO-GO, post-change acceptance, residual risk |
| Follow-up triggers | Monitoring, audit finding, incident, thay đổi mới |

### 17.1. Mẫu YAML minh họa

Các dữ liệu và đường dẫn dưới đây là **giả định**, không phải approval hoặc test có thật.

~~~yaml
change_assurance:
  change_id: CHG-2026-EXAMPLE-042
  service: checkout-platform
  owner_role: PLATFORM_SERVICE_OWNER
  change_type: normal
  summary: "Rotate application token signing key"
  planned_window_utc:
    start: "2026-12-02T01:00:00Z"
    end: "2026-12-02T03:00:00Z"

  scope:
    environments: [production]
    regions: [region-a, region-b]
    assets_ref: "restricted/inventory/checkout"
    dependencies: [identity-provider, api-gateway, batch-workers, kms]
    excluded: ["unrelated development environments"]

  security_context:
    requirements: [AUTHN-01, IAM-KEY-02, LOG-03, DR-KEY-01]
    threat_model_ref: "restricted/threat-model/token-trust"
    baseline_evidence_ref: "restricted/evidence/prechange-baseline"

  change_risks:
    - id: R1
      scenario: "Old tokens rejected before consumers refresh keys"
      inherent_level: high
      mitigation: "Overlapping key validation and consumer compatibility tests"
      residual_level: medium
    - id: R2
      scenario: "DR workloads cannot verify or decrypt required material"
      inherent_level: high
      mitigation: "DR key retrieval and recovery-path verification"
      residual_level: pending-assessment

  pre_change_gates:
    test_plan_ref: "restricted/tests/key-rotation-plan"
    rollback_runbook_ref: "restricted/runbooks/key-rollout-recovery"
    security_review: PENDING
    change_approval: PENDING

  deployment:
    artifact_digest_ref: "restricted/builds/checkout/token-release"
    deployment_record_ref: "restricted/deployments/CHG-042"
    result: NOT_STARTED

  verification:
    positive_authn_test: PENDING
    negative_invalid_signature_test: PENDING
    batch_consumer_compatibility: PENDING
    audit_logging_test: PENDING
    dr_recovery_key_test: PENDING
    business_transaction_test: PENDING
    evidence_refs: []

  assessment:
    status: NOT_DEMONSTRATED
    decision: NO_GO_UNTIL_REQUIRED_GATES_PASS
    authorized_reviewer_role: SECURITY_ASSURANCE_LEAD
    residual_risk_owner_role: BUSINESS_SERVICE_OWNER
    next_review_trigger:
      - "new-token-consumer"
      - "identity-provider-trust-change"
      - "material-authentication-incident"
~~~

Mẫu cố ý dùng PENDING/NOT_DEMONSTRATED để minh họa rằng **chưa có bằng chứng thì không thể tự đánh dấu PASS**. Một file YAML có trường “approved” chỉ là dữ liệu được khai báo; phải có liên kết tới phê duyệt thực tế và đúng thẩm quyền.

Evidence nhạy cảm về host, quyền IAM, khóa, network hoặc dữ liệu khách hàng nên được lưu trong kho hạn chế truy cập, có version, integrity control và audit trail. Báo cáo nên tham chiếu ID thay vì sao chép secrets vào tài liệu phát hành rộng.

## 18. Case study A: thay đổi IAM policy cho dịch vụ thanh toán

Đây là **tình huống giả định để học**.

### 18.1. Đề xuất thay đổi

Dịch vụ checkout cần thêm quyền đọc một secret mới để kết nối payment processor. Đội triển khai định thay role hiện tại bằng một policy có quyền rộng hơn để kịp release:

~~~text
Before:
  checkout-service can read one named secret in payment namespace.

Proposed:
  checkout-service can read all secrets in the cloud account.

Reason given:
  "Simplifies configuration and avoids permission errors."
~~~

**Rủi ro:** nếu checkout service bị chiếm quyền hoặc workflow tạo role sai, attacker có thể đọc secrets của nhiều dịch vụ không liên quan. Thay đổi làm tăng **blast radius**, vượt least privilege và có thể không phù hợp yêu cầu kiểm soát access.

### 18.2. Risk assessment và alternative design

| Phương án | Lợi ích | Rủi ro/giới hạn |
|---|---|---|
| Policy cho toàn cloud account | Dễ triển khai ngay | Blast radius lớn; khó chấp nhận nếu không có căn cứ |
| Policy cho chính xác secret cần đọc | Least privilege, giảm tác động | Cần quản lý version/ARN và deployment cẩn thận |
| Secret broker chuyên dụng | Tách quyền và giám sát tập trung | Phức tạp thêm, cần đánh giá availability và trust |
| Tạm cấp quyền rộng với ngoại lệ | Có thể giảm delay | Vẫn phải đánh giá rủi ro, quyền duyệt, hạn và compensating controls; không mặc định hợp lệ |

Nhóm chọn phương án **giới hạn đúng secret**. Security requirements ghi: role chỉ được đọc secret thuộc phạm vi chức năng checkout và mọi thay đổi quyền được audit.

### 18.3. Gates và kiểm thử

1. Kiểm tra IAM policy diff và quyền kế thừa của role; không có quyền đọc wildcard ngoài scope.
2. Chạy policy evaluation bằng principal của checkout và secret hợp lệ.
3. **Positive test:** checkout đọc được secret được cấp quyền và thực hiện giao dịch thử.
4. **Negative test:** checkout không đọc được secret thử thuộc dịch vụ khác.
5. Xác minh log đọc secret và thay policy được thu thập.
6. Đối chiếu role policy trên account/region production sau rollout.
7. Kiểm tra rollback không tái cấp wildcard hay làm mất khả năng xử lý giao dịch.
8. Ghi evidence và người phê duyệt.

Nếu mọi kiểm tra đạt, có cơ sở đánh giá thay đổi phù hợp trong scope. Nếu chỉ có policy diff nhưng chưa có runtime test, có thể ghi **implementation reviewed; operating behavior not demonstrated**.

### 18.4. Kịch bản xảy ra sai lệch trong canary

Giả sử canary xuất hiện lỗi: dịch vụ vẫn không đọc được secret dù policy đã đổi. Đội điều tra thấy KMS policy của khóa dùng mã hóa secret chưa cấp quyền giải mã cho checkout role. Khi ấy **không nên nới quyền đọc secret lên toàn account** để chữa triệu chứng.

Cần đánh giá đúng dependency IAM–KMS, bổ sung kiểm thử quyền tối thiểu trên KMS key và cập nhật threat/risk assessment. Đây là ví dụ về việc **điều kiện tưởng nhỏ ở một lớp có thể tác động các control khác**.

## 19. Case study B: schema migration và tính toàn vẹn dữ liệu

Một nhóm cần thay đổi cấu trúc bảng đơn hàng từ cột trạng thái chuỗi sang mã chuẩn hóa, đồng thời cập nhật API. Tính toàn vẹn và khả dụng là mục tiêu trọng yếu.

### 19.1. Failure scenarios

- Migration map sai một giá trị trạng thái, khiến đơn hàng “đã hoàn tất” bị phân loại “chưa thanh toán”.
- Worker phiên bản cũ và mới ghi cùng bản ghi theo hai schema khác nhau.
- Re-run migration tạo sự kiện thanh toán trùng hoặc thay đổi dữ liệu đã đối soát.
- Rollback code nhưng dữ liệu đã được chuyển đổi không đảo ngược.
- Backup trước migration tồn tại nhưng chưa thử restore/đối chiếu.
- Audit logging của thay đổi dữ liệu không được duy trì khi chạy migration.

### 19.2. Điều kiện GO/NO-GO

| Gate | Tiêu chí |
|---|---|
| Migration design | Có mapping rõ, idempotency, giới hạn tài nguyên, thứ tự triển khai |
| Data backup/recovery | Có restore point phù hợp và đã thử recovery theo rủi ro |
| Rehearsal | Đã thử trên dữ liệu có quy mô và phân bố đại diện |
| Integrity checks | Row count, checksum/đối soát, trạng thái nghiệp vụ cốt lõi đạt |
| Compatibility | Old/new services phối hợp trong rollout hoặc có cửa sổ cắt chuyển |
| Monitoring | Có cảnh báo giao dịch trùng, backlog, DB errors và bất thường dữ liệu |
| Rollback/forward fix | Có quyết định khi không thể đảo ngược dữ liệu, owner và runbook |
| Approval | Business/data/security owners chấp nhận mức rủi ro theo thẩm quyền |

Một kế hoạch có thể chọn **expand–migrate–contract**: thêm schema mới tương thích, triển khai ứng dụng đọc được cả hai dạng, chuyển dữ liệu có đối soát, rồi mới loại bỏ dạng cũ khi chứng minh an toàn. Không phải mọi migration phù hợp chiến lược này, nhưng nó minh họa cách giảm rủi ro phiên bản hỗn hợp.

### 19.3. Kết quả giả định

Ở lần rehearsal đầu, 0,2% bản ghi trạng thái hiếm không được map đúng. Dù 99,8% bản ghi hợp lệ, nếu phần sai nằm ở trạng thái thanh toán quan trọng thì không thể dùng trung bình tỷ lệ để bỏ qua. Cần **NO-GO**, sửa mapping, bổ sung regression tests và xác minh toàn bộ tập liên quan.

Sau khi sửa, thử lại với dữ liệu đủ representative, đối soát đúng trạng thái, chứng minh idempotency và khôi phục được, nhóm mới có cơ sở trình phê duyệt. Phân tích phải lưu rõ scope và thời kỳ; một rehearsal thành công không bảo đảm mọi lỗi production đều không tồn tại.

## 20. Change risk liên hệ với audit, exception và remediation

### 20.1. Với audit và evidence

Audit có thể kiểm tra:

- Thay đổi có được phê duyệt đúng trước khi triển khai hay không.
- Security impact assessment có bao phủ control ảnh hưởng và rủi ro?
- Có bằng chứng test, rollout, post-change verification và separation of duties?
- Emergency changes có review hậu triển khai?
- Các ngoại lệ và quyết định rủi ro có hợp lệ, không hết hạn?
- Những phát hiện do thay đổi gây ra có CAP và retest?

Một “change approved” cho biết có quyết định quản trị, không tự chứng minh thực thi tuân thủ.

### 20.2. Với exception management

Nếu change buộc phải tạm không đáp ứng một security baseline, cần tách **change approval** và **security exception/risk acceptance**. Phạm vi ngoại lệ phải nêu control, tài sản, môi trường, thời gian, compensating controls, người duyệt và điều kiện kết thúc. Không dùng phê duyệt thay đổi để miễn mọi yêu cầu bảo mật khác.

### 20.3. Với remediation

Một bản vá lỗ hổng là **change**, và bản vá cũng có change risk. Cần cân bằng việc giảm rủi ro của lỗ hổng với nguy cơ regression khi triển khai. Tuy vậy “bản vá gây rủi ro triển khai” không tự là lý do bỏ vá vô thời hạn; nếu trì hoãn, phải xử lý qua quyết định rủi ro có thời hạn và bằng chứng.

Một remediation chỉ được xác minh đã sửa khi:
- Đúng bản vá/config tới đúng tài sản.
- Finding ban đầu không còn tái hiện theo phép thử phù hợp.
- Negative/positive/regression tests và những điều kiện bắt buộc đã đạt.
- Có review/evidence và residual risk được ghi rõ.

### 20.4. Với assurance case

Một thay đổi có thể làm vô hiệu một claim hoặc evidence trước đó. Ví dụ claim “mọi endpoint đều dùng authorization middleware phiên bản M” cần được đánh giá lại khi framework/router đổi phiên bản. Nên gắn **change ID → impacted controls → assurance claims → evidence → retest result** để chủ động biết phần case cần cập nhật.

## 21. Metrics và giám sát hiệu quả change assurance

Một chương trình có thể theo dõi các chỉ số:

| Chỉ số | Giá trị | Cảnh báo khi diễn giải |
|---|---|---|
| **Change failure rate** | Tỷ lệ thay đổi gây sự cố hoặc cần khắc phục sau triển khai theo định nghĩa | Cần thống nhất mẫu số và phân nhóm mức rủi ro |
| **Security regression rate** | Bao nhiêu thay đổi tạo suy giảm security control được phát hiện | Số tăng có thể do kiểm tra tốt hơn; cần xem bối cảnh |
| **Pre-change gate coverage** | Tỷ lệ change có security gates phù hợp | Không chỉ đếm đủ trường trên form |
| **Post-change verification completion** | Tỷ lệ change đã được chứng minh đáp ứng điều kiện | Cần xét chất lượng, scope và thời gian evidence |
| **Unreviewed high-risk changes** | Những change có tác động lớn thiếu đánh giá/approval | Ưu tiên xử lý thay vì che bằng tỷ lệ tổng |
| **Rollback/forward-fix effectiveness** | Khả năng khôi phục sau failure | Kết luận phải gồm dữ liệu, bảo mật và nghiệp vụ |
| **Risk exception age** | Thời gian kéo dài sai khác so với baseline | Phải xét hạn phê duyệt và biện pháp bù trừ |
| **Change-induced audit findings** | Kiểm soát bị suy yếu sau thay đổi | Kết nối root cause với kiểm soát trong pipeline |
| **Evidence freshness** | Evidence còn phù hợp release/config hiện hành | Evidence nhiều nhưng cũ không tăng assurance |

Không nên tối ưu một chỉ số theo cách làm giảm bảo mật, ví dụ giảm change failure rate bằng cách **không triển khai bản vá cấp bách** hoặc báo tất cả rollback thành “success”. Cần đọc số liệu theo loại change, độ trọng yếu và phạm vi rủi ro.

## 22. Anti-patterns: sai lầm phổ biến khi đánh giá Change risk

| Sai lầm | Vì sao nguy hiểm | Cách sửa |
|---|---|---|
| Chấm change risk chỉ theo số dòng code | Bỏ qua một dòng IAM/network có blast radius lớn | Dựa vào asset, threat, security property và impact |
| Không có dependency map | Không biết ảnh hưởng lên KMS/IdP/DR/vendor | Architecture review và dependency inventory |
| Thay policy nhưng chỉ test UI | Không xác nhận authz/identity enforcement | Negative/positive security tests |
| CI xanh là đủ để GO | CI có thể thiếu scenario hoặc sai config | Mapping risk–test và production equivalence |
| Chỉ thử staging nhưng kết luận toàn production | Khác IAM, keys, network, workload | Config diff, artifact proof, production-safe checks |
| Rollback chưa được thử | Không khôi phục được khi xảy ra lỗi | Rehearsal, backup/restore, quyết định forward fix |
| Canary không đại diện | Bỏ qua role hiếm hoặc đường export | Chọn canary và synthetic cases theo rủi ro |
| Chỉ theo dõi latency/5xx | Không phát hiện lộ dữ liệu hoặc mất logging | Security guardrails, data checks và business signals |
| Nới quyền quá rộng để chữa lỗi kết nối | Tạo lỗ hổng mới nghiêm trọng | Tìm dependency root cause, least privilege |
| Không quản lý mixed-version window | Schema/protocol mismatch và sai dữ liệu | Compatibility plan, staged deployment |
| Không đánh giá tác động lên evidence/assurance case | Dùng test/claim lỗi thời | Invalidate/retest các claim liên quan |
| Emergency change không có dấu vết | Không audit được, quyền tạm còn sót | Minimal logging, approval và post-review |
| “Phê duyệt thay đổi” được hiểu là “chấp nhận mọi rủi ro” | Sai thẩm quyền và thiếu điều kiện ngoại lệ | Tách change approval với risk acceptance |
| Đóng ticket ngay khi deploy xong | Chưa chứng minh security controls còn hiệu lực | Post-change verification và sign-off |
| Chỉ tính rủi ro từng change riêng | Hai thay đổi cùng lúc có thể tạo lỗi chung | Change calendar và cumulative-risk review |
| Không có trigger ngừng rollout | Lỗi lan rộng trước khi phản ứng | Guardrails, kill-switch và decision authority |
| Không xác minh data integrity sau migration | HTTP 200 nhưng dữ liệu sai | Reconciliation, transaction sampling và audit |
| Không quản lý secrets/log trong evidence | Tăng rủi ro lộ thông tin | Evidence references, RBAC, retention |

## 23. Bài tập thực hành

### Tình huống A — Mở rộng quyền để kịp release

Một đội dự định đổi IAM role từ quyền đọc một secret thành quyền đọc mọi secret trong production account vì phát hiện lỗi permission ở staging.

1. Viết risk statement rõ **threat, condition, asset và impact**.
2. Vẽ phạm vi ảnh hưởng tới API, KMS, các service khác và đường quản trị.
3. Đề xuất phương án ít rủi ro hơn và các negative/positive tests.
4. Định nghĩa ít nhất năm GO/NO-GO gates.
5. Nếu đội đề xuất ngoại lệ tạm thời, cần những điều kiện và quyền phê duyệt nào?
6. Viết kết luận post-change verification có hạn chế rõ ràng.

### Tình huống B — Rotate khóa xác thực

Một nền tảng chuẩn bị rotate signing key ở IdP. Gateway đã hỗ trợ khóa mới, nhưng hai batch worker cũ chỉ chấp nhận khóa trước và DR site chưa được thử.

1. Nêu ít nhất bốn failure/abuse scenarios.
2. Phân tích blast radius và dependency; giải thích vì sao gateway PASS chưa đủ.
3. Xây dựng compatibility window và rollback/forward-fix strategy.
4. Thiết kế security tests, business tests và DR tests phù hợp.
5. Khi nào phải dừng rollout, và ai ra quyết định theo thẩm quyền?
6. Cần evidence nào để xác nhận key cũ được thu hồi **đúng thời điểm** và service hợp lệ vẫn hoạt động?

### Tình huống C — Migration dữ liệu không thể rollback dễ dàng

Một migration thay định dạng trạng thái đơn hàng cho 5 triệu bản ghi. Rehearsal với 100.000 dòng cho thấy 99,9% mapping đúng; 0,1% còn lại là các trạng thái thanh toán hiếm nhưng quan trọng. Business owner muốn GO vì tỷ lệ thành công cao.

1. Vì sao tỷ lệ tổng hợp không chứng minh migration an toàn?
2. Nêu mục tiêu integrity và tiêu chí dữ liệu theo từng nhóm trạng thái.
3. Đề xuất dữ liệu rehearsal đại diện, reconciliation và kiểm thử idempotency.
4. Đề xuất cách giới hạn blast radius, compatibility và forward fix.
5. Viết một quyết định **NO-GO có bằng chứng**, gồm blocker và action.
6. Điều kiện gì cho phép đánh giá lại để GO?

### Tình huống D — Thay đổi khẩn cấp làm mất logging

Trong một sự cố, đội vận hành tạm chặn một đường API nguy hiểm và vô tình đổi network policy khiến log từ một cloud account không về SIEM trong 6 giờ. Dịch vụ phục hồi và HTTP success rate đạt mục tiêu.

1. Vì sao service availability PASS không đủ kết luận change assurance đạt?
2. Cần kiểm tra lại logging coverage, time window và security control nào?
3. Làm thế nào phân biệt evidence về **khắc phục hiện tại** với **khoảng trống 6 giờ trong quá khứ**?
4. Nêu trách nhiệm review emergency change và cập nhật risk/incident records.
5. Thiết kế CAP và tiêu chí xác minh để tránh mất log khi dùng runbook tương tự.
6. Nêu trạng thái change/finding phù hợp khi log đã phục hồi nhưng dữ liệu lịch sử không thể lấy lại.

**Gợi ý:** Trong mọi tình huống, cần giữ bốn loại kết luận tách biệt: **có được phép thay đổi không**, **thay đổi đã triển khai tới đâu**, **kiểm soát đã được kiểm chứng trong phạm vi nào**, và **rủi ro còn lại được quyết định ra sao**. Không dùng “approved”, “deployed” và “secure” như những từ đồng nghĩa.

## 24. Checklist sử dụng khi thực hiện change risk assessment

Trước khi đưa một change có tác động bảo mật đáng kể vào production, đối chiếu:

- [ ] Mục đích, owner, thời gian và yêu cầu nghiệp vụ đã rõ.
- [ ] Asset, role, account, region, dữ liệu và dependency được kiểm kê.
- [ ] Security objectives, controls và trust boundaries chịu ảnh hưởng được xác định.
- [ ] Các kịch bản xấu nhất hợp lý và common-mode failure đã được xem xét.
- [ ] Inherent risk, mitigations, uncertainty và residual risk được ghi với lý do.
- [ ] Người phê duyệt phù hợp cấp rủi ro và nghĩa vụ áp dụng.
- [ ] Tập test phản ánh các failure scenarios; có negative, positive và regression.
- [ ] Artifact, deployment provenance và environment equivalence kiểm tra được.
- [ ] Monitoring/guardrails có thể phát hiện lỗi nghiệp vụ, dữ liệu và bảo mật.
- [ ] Canary/staged rollout và điều kiện GO/NO-GO đã được chốt.
- [ ] Rollback/forward fix và phục hồi dữ liệu đã được đánh giá, thử ở mức phù hợp.
- [ ] Có người chịu trách nhiệm thực hiện, quyết định dừng và thông báo sự cố.
- [ ] Sau triển khai có evidence đúng release, đủ scope, có reviewer.
- [ ] Mọi ngoại lệ/rủi ro còn lại có owner, thời hạn và phê duyệt theo thẩm quyền.
- [ ] Assurance case, runbook, threat model và inventory được cập nhật khi thay đổi tác động.

Checklist này không thay thế đánh giá chuyên môn hoặc nghĩa vụ cụ thể của tổ chức; nó giúp đảm bảo những câu hỏi cốt lõi không bị bỏ qua.

## 25. Ghi nhớ

**Change risk** là rủi ro phát sinh khi chuyển hệ thống từ trạng thái hiện tại sang trạng thái mới. Đánh giá tốt phải bắt đầu từ **mục tiêu bảo mật và tài sản cần bảo vệ**, xác định đường thay đổi có thể làm suy yếu control, phân tích blast radius và dependency, rồi thiết kế bằng chứng để xác minh các biện pháp giảm thiểu có hiệu quả.

Trong **SECURITY_SECURITY_ASSURANCE**, chuỗi truy vết cần duy trì là:

**Security objective / Risk → Change scope và impact → Threat/failure scenarios → Control và risk decision → Test + rollout/rollback gates → Deployment evidence → Post-change verification → Residual risk / findings → Monitoring và đánh giá lại.**

Một change không được coi là “an toàn vì đã được phê duyệt” hoặc “hoàn thành vì pipeline xanh”. Kết luận change assurance đáng tin phải nói rõ **thay đổi điều gì, rủi ro tác động tới đâu, đã kiểm tra bằng những dữ liệu nào, kết quả và giới hạn ra sao, ai quyết định và điều gì sẽ kích hoạt xem xét lại**.

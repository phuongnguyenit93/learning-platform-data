# Security requirement – Xác định và kiểm chứng yêu cầu bảo mật trong phát triển phần mềm

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích **security requirement (yêu cầu bảo mật)** và phân biệt với security policy, control, implementation task, test case và acceptance criterion.
- Thu thập yêu cầu từ tài sản, mục tiêu bảo mật, risk assessment, threat modeling, nghĩa vụ áp dụng, kiến trúc, người dùng và hoạt động vận hành.
- Viết yêu cầu **cụ thể, có phạm vi, có thể kiểm chứng, có owner, có mức ưu tiên và có tiêu chí chấp nhận**.
- Chuyển một risk scenario thành chuỗi truy vết **risk → security objective → requirement → control → test → evidence → finding → remediation/retest**.
- Bao phủ các miền quan trọng: identity/access, data protection, input/output, API, cryptography, secrets, logging, privacy, supply chain, infrastructure, resilience và incident response.
- Thiết lập traceability giữa yêu cầu, thiết kế, code, cấu hình, CI/CD, test, deployment và bằng chứng runtime.
- Xử lý yêu cầu mâu thuẫn, thay đổi phạm vi, ngoại lệ, requirement chưa rõ và rủi ro còn lại.
- Tổ chức security assurance liên tục để chứng minh yêu cầu vẫn được đáp ứng khi phần mềm thay đổi và vận hành.

## 1. Security requirement là gì?

**Security requirement** là một điều kiện hoặc hành vi bảo mật mà hệ thống, thành phần, quy trình phát triển hay hoạt động vận hành **phải đáp ứng** để bảo vệ tài sản và đạt mục tiêu bảo mật trong một phạm vi xác định.

Ví dụ:

> Người dùng chỉ được xem báo cáo thuộc tenant mà họ có quyền truy cập; mọi yêu cầu thiếu danh tính hoặc không xác minh được quyền phải bị từ chối.

Yêu cầu này mô tả **kết quả bảo mật cần đạt**. Nhóm phát triển có thể triển khai bằng OIDC, Spring Security, kiểm tra ownership ở service layer, truy vấn có tenant scope và policy ở database. Những cơ chế đó là controls hoặc design decisions. Test cross-tenant là phương pháp kiểm chứng. Kết quả chạy test và cấu hình production là evidence.

Trong module **SECURITY_SECURITY_ASSURANCE**, yêu cầu bảo mật là cầu nối giữa rủi ro và bằng chứng. Mục tiêu là chứng minh hệ thống đáp ứng yêu cầu thông qua thiết kế, triển khai, kiểm thử, audit và khắc phục. Vì vậy, một câu như “hệ thống phải an toàn” không đủ để phát triển hoặc đánh giá; nhóm cần biết **tài sản nào, actor nào, hành động nào, điều kiện nào, phạm vi nào và bằng chứng nào**.

### Phân biệt các khái niệm

| Khái niệm | Trả lời câu hỏi | Ví dụ |
| --- | --- | --- |
| **Security objective** | Muốn bảo vệ điều gì? | Bảo đảm chỉ đúng khách hàng xem được dữ liệu của mình |
| **Security policy** | Nguyên tắc/quy tắc quản trị nào phải tuân thủ? | Truy cập dữ liệu nhạy cảm phải được cấp theo least privilege |
| **Security requirement** | Hệ thống phải làm gì hoặc không được làm gì? | API phải từ chối truy cập report thuộc tenant khác |
| **Security control** | Cơ chế nào giúp thực hiện yêu cầu? | Object-level authorization ở service layer |
| **Design decision** | Chọn cách tổ chức/triển khai nào? | Lấy tenant context từ authenticated principal |
| **Implementation task** | Nhóm cần thay đổi gì trong sản phẩm? | Tạo ReportAccessPolicy và áp dụng vào endpoint |
| **Test case** | Làm sao kiểm tra yêu cầu? | User tenant A gọi report tenant B phải bị từ chối |
| **Acceptance criterion** | Điều kiện nào được xem là đạt? | Không trả nội dung report, không phát sinh export job, có audit event phù hợp |
| **Evidence** | Hiện vật nào chứng minh kết quả? | Test report, deployment ID, policy snapshot, runtime verification |

Các khái niệm có quan hệ nhưng không thể thay thế nhau. Có control trong sơ đồ không chứng minh requirement đã được thực hiện. Có test case cũng chưa chứng minh test đã chạy trên đúng artifact hoặc đúng môi trường.

## 2. Vì sao cần security requirements ngay trong secure development?

Nếu yêu cầu bảo mật chỉ xuất hiện khi penetration test hoặc audit cuối dự án, nhóm có thể đã chọn sai kiến trúc, tạo API contract không an toàn hoặc lưu dữ liệu quá rộng. Chi phí sửa thường tăng vì security concern đã lan qua nhiều thành phần.

Security requirements giúp:

- **Định hướng kiến trúc:** xác định trust boundaries, identity, data flows, key management và security dependencies trước khi code.
- **Ưu tiên theo rủi ro:** tập trung vào tài sản và attack paths có impact cao.
- **Chuyển nguyên tắc thành hành vi:** “least privilege” trở thành giới hạn quyền cụ thể cho từng principal.
- **Tạo tiêu chí nghiệm thu:** developer, tester, assessor và product owner hiểu thế nào là đạt.
- **Giảm tranh luận muộn:** yêu cầu và ngoại lệ được thống nhất trước khi phát hành.
- **Duy trì traceability:** khi đổi API, role, database hoặc vendor, biết yêu cầu và test nào bị ảnh hưởng.
- **Tạo evidence:** có thể truy từ requirement tới test, runtime configuration và finding.
- **Theo dõi thay đổi:** bảo đảm yêu cầu vẫn phù hợp sau khi sản phẩm và threat landscape đổi.

### Một tình huống dễ gặp

Nhóm phát triển endpoint `GET /customers/{id}`. Product ticket chỉ nói “cho support xem thông tin khách hàng”. Developer kiểm tra user có role `SUPPORT` rồi trả entity. Sau đó audit phát hiện support agent có thể xem mọi tenant, kể cả hồ sơ không thuộc case được phân công.

Vấn đề xuất phát từ requirement chưa rõ:
- Support được xem dữ liệu nào?
- Có cần case được duyệt không?
- Ai là chủ thể của record?
- Có giới hạn tenant không?
- Có trường nào phải che?
- Truy cập có cần lý do và audit không?
- Khi case đóng hoặc quyền bị thu hồi thì sao?

Nếu các điều kiện được viết thành requirements trước khi code, nhóm có thể thiết kế đúng từ đầu và có test tương ứng.

## 3. Nguồn hình thành security requirements

Không nên chỉ lấy yêu cầu từ một checklist bảo mật. Yêu cầu cần được tổng hợp từ **nhiều nguồn có thẩm quyền**, rồi gắn với bối cảnh của hệ thống.

| Nguồn | Điều cần khai thác | Ví dụ đầu ra |
| --- | --- | --- |
| **Business objectives** | Nghiệp vụ, mức độ quan trọng, tác động khi lộ/sửa/mất dịch vụ | Availability, confidentiality, integrity objectives |
| **Asset/data inventory** | Dữ liệu, identity, secret, service, key, log, backup | Data classification và owner |
| **Risk assessment** | Likelihood, impact, exposure, residual risk | Risk-driven requirements |
| **Threat modeling** | Actor, entry point, trust boundary, attack path | Abuse-case requirements |
| **Architecture/design** | Service, protocol, dependencies, deployment topology | Boundary-specific requirements |
| **Security/privacy policy** | Nguyên tắc và quy tắc nội bộ đã phê duyệt | Access, retention, logging requirements |
| **Applicable obligations** | Luật, quy định, hợp đồng, chuẩn ngành trong phạm vi áp dụng | Requirement có source/reference |
| **Customer/partner contracts** | Điều kiện tích hợp, dữ liệu chia sẻ, SLA và audit rights | API, data handling, notification requirements |
| **Operational experience** | Incident, outage, finding, support ticket, misconfiguration | Corrective/preventive requirements |
| **Development standards** | Secure coding, CI/CD, dependency, secrets, review | Pipeline gates và coding requirements |
| **User/workflow research** | Vai trò thực tế, exceptional paths, delegated access | Role/action/resource requirements |
| **Audit and assessment** | Control gaps, recurring findings, evidence limitations | Remediation và monitoring requirements |

### Phân biệt yêu cầu pháp lý và yêu cầu kỹ thuật

Một nghĩa vụ pháp lý hoặc điều khoản hợp đồng cần được **người có thẩm quyền diễn giải trong đúng phạm vi áp dụng**. Nhóm kỹ thuật có thể chuyển kết luận đó thành requirement, nhưng không tự suy ra mọi hệ thống đều phải có cùng một thời hạn lưu, cùng căn cứ xử lý hoặc cùng biện pháp.

Mỗi requirement có nguồn nên lưu:
- Tên nguồn/điều khoản/phiên bản nếu có.
- Phạm vi áp dụng và điều kiện kích hoạt.
- Người xác nhận nghĩa vụ.
- Ngày đánh giá và ngày cần xem xét lại.
- Requirement kỹ thuật được suy ra và cách chứng minh.

Không ghi “theo luật” chung chung nếu chưa có nguồn và xác nhận phù hợp.

## 4. Từ tài sản và mục tiêu bảo mật tới yêu cầu

Trước khi viết requirement, cần biết **đang bảo vệ tài sản nào và điều gì có thể xảy ra với tài sản đó**.

### 4.1. Xác định tài sản

Ví dụ nền tảng báo cáo đa tenant:

| Asset ID | Tài sản | Owner | Mục tiêu bảo vệ |
| --- | --- | --- | --- |
| AST-01 | Báo cáo tài chính khách hàng | Data Owner | Confidentiality, integrity |
| AST-02 | User session và access token | Identity Owner | Confidentiality, authenticity |
| AST-03 | Workload identity của export worker | Platform Owner | Least privilege, accountability |
| AST-04 | File export và signed URL | Service Owner | Confidentiality, retention |
| AST-05 | Audit events | Security/Ops Owner | Integrity, availability, traceability |
| AST-06 | Encryption keys/secrets | Key/Secrets Owner | Confidentiality, integrity, lifecycle |
| AST-07 | CI/CD pipeline và build artifacts | Engineering/Platform Owner | Integrity, provenance, controlled deployment |
| AST-08 | Backup và recovery copies | Operations Owner | Availability, integrity, access isolation |

### 4.2. Xác định mục tiêu

Ví dụ:
- Chỉ principal có quyền mới truy cập report.
- Không để một tenant quan sát hoặc sửa dữ liệu tenant khác.
- Dữ liệu nhạy cảm không bị truyền hoặc lưu ở dạng trái policy.
- Hành động đặc quyền có thể truy vết.
- Thay đổi production phải có nguồn gốc và phê duyệt.
- Hệ thống giữ security invariants khi dependency lỗi.
- Khi sự cố xảy ra, tổ chức có thể cô lập và khôi phục.

### 4.3. Chuyển thành requirements

| Objective | Requirement minh họa |
| --- | --- |
| Chỉ đúng chủ thể đọc report | API phải kiểm tra quyền trên từng report theo principal và tenant được xác minh |
| Hạn chế export | Export job phải lưu scope, owner, purpose và thời hạn; worker kiểm tra lại trước khi tạo file |
| Bảo vệ credential | Access token và private key không được ghi vào application/proxy logs |
| Bảo vệ kênh | Client phải xác minh CA và hostname trên các kết nối TLS thuộc phạm vi |
| Truy vết hành động | Thao tác export phải tạo audit event có actor, resource, outcome và correlation ID |
| Giới hạn tác động khi worker bị chiếm | Worker identity chỉ có quyền trên bucket/prefix và actions cần thiết |
| Bảo đảm recovery | Restore phải kiểm tra quyền, integrity và trạng thái thu hồi trước khi mở lại service |

Một objective có thể cần nhiều requirements; một requirement có thể hỗ trợ nhiều objectives. Cần giữ mapping để đánh giá impact khi một yêu cầu đổi.

## 5. Đặc điểm của một security requirement tốt

Một requirement tốt giúp người thực hiện biết phải xây gì và người đánh giá biết phải kiểm tra gì.

### 5.1. Cụ thể và đơn nghĩa

Tránh các từ mơ hồ như:
- “An toàn”, “mạnh”, “phù hợp”, “đầy đủ”, “nhanh chóng”.
- “Chỉ người được phép” nhưng không định nghĩa ai, quyền gì và trên tài nguyên nào.
- “Mã hóa dữ liệu” nhưng không xác định data state, boundary và baseline.
- “Ghi log đầy đủ” nhưng không nói event, field, retention và access.

Thay bằng mô tả actor, action, resource, condition, boundary và expected behavior.

### 5.2. Có thể kiểm chứng

Một requirement phải có cách xác nhận đạt hoặc không đạt:
- Test tự động.
- Kiểm tra cấu hình hiệu lực.
- Review code/IaC.
- Runtime sampling.
- Access review.
- Restore/failure exercise.
- Bằng chứng từ vendor hoặc hệ thống quản trị.

Nếu không thể đo trực tiếp, cần nêu phương pháp đánh giá, giả định và limitation. Không dùng câu “đội security sẽ kiểm tra” thay cho tiêu chí.

### 5.3. Có phạm vi

Ghi rõ:
- Service/API/asset/environment.
- Actor và resource.
- Data class hoặc action.
- Region/tenant/client version nếu có liên quan.
- Những luồng được bao gồm và loại trừ.

### 5.4. Có chủ sở hữu và nguồn

Mỗi requirement nên có owner chịu trách nhiệm duy trì, nguồn hình thành, reviewer/approver cần thiết và trạng thái. Nếu không rõ ai quyết định, requirement dễ bị bỏ qua hoặc ngoại lệ không có thẩm quyền.

### 5.5. Khả thi và nhất quán

Yêu cầu cần khả thi với kiến trúc và không mâu thuẫn với nhau. Nếu một requirement đòi mọi dữ liệu bị xóa ngay, còn nghĩa vụ khác yêu cầu bảo toàn một phần evidence, cần phân tích phạm vi/ngoại lệ thay vì tự chọn một phía.

### 5.6. Được ưu tiên theo risk

Không phải mọi requirement đều có cùng mức cấp bách. Ưu tiên nên xem:
- Impact nếu thất bại.
- Khả năng khai thác và exposure.
- Population/tài sản bị ảnh hưởng.
- Khả năng phát hiện và thời gian khắc phục.
- Nghĩa vụ/contractual deadline.
- Mức độ phụ thuộc của các controls khác.

### 5.7. Có thể truy vết

Một requirement cần liên kết tới:
- Risk/objective/source.
- Design/control.
- Code/config/change.
- Test/acceptance criterion.
- Evidence/finding/exception.
- Owner và trạng thái hiện tại.

### Mẫu cấu trúc requirement

| Trường | Ý nghĩa |
| --- | --- |
| ID | Mã ổn định, duy nhất |
| Statement | Điều kiện bảo mật phải đáp ứng |
| Rationale | Rủi ro/mục tiêu được giải quyết |
| Source | Risk, policy, contract, standard hoặc decision |
| Scope | Asset, service, environment, actor, data |
| Priority | Mức ưu tiên theo risk |
| Owner | Người/nhóm chịu trách nhiệm |
| Acceptance criteria | Kết quả có thể kiểm tra |
| Verification method | Test, inspection, analysis hoặc operational review |
| Evidence reference | Nơi lưu hiện vật khi thực hiện |
| Dependencies | Control/requirement khác cần có |
| Status | Draft, Approved, Implemented, Verified, Failed, Exception, Retired |
| Version/review date | Thời điểm và phiên bản được xem xét |

## 6. Viết requirement theo cấu trúc có thể nghiệm thu

Một cấu trúc hữu ích:

> **[System/component] phải [hành vi bảo mật] đối với [actor/resource/data] khi [điều kiện], với [giới hạn/tiêu chí], và kết quả được kiểm chứng bằng [phương pháp/evidence].**

Ví dụ:

**Mơ hồ:**
> API phải bảo vệ dữ liệu khách hàng.

**Có thể kiểm chứng:**
> `report-api` phải từ chối yêu cầu đọc report khi tenant của report không khớp tenant được xác minh từ principal; response không được chứa report data và không được tạo export job. Kiểm chứng bằng integration test với hai tenant, test giả mạo tenant header và runtime verification trên deployment được đánh giá.

Requirement này đã nêu:
- Thành phần: `report-api`.
- Hành vi: từ chối.
- Resource: report.
- Context: trusted principal/tenant.
- Acceptance: không có response data và không tạo job.
- Verification: integration tests và runtime verification.

### Một ví dụ khác: token trong log

**Mơ hồ:**
> Không log thông tin nhạy cảm.

**Có thể kiểm chứng:**
> Application, gateway và tracing collector trong scope không được ghi raw access token, refresh token hoặc private key vào log/trace; synthetic marker test phải xác nhận marker không xuất hiện trong các nguồn log được kiểm kê, trong khi security event tối thiểu vẫn được ghi và source-health được xác minh.

### Acceptance criteria phải quan sát được

Không viết “phải hoạt động đúng”. Hãy chỉ rõ:
- Kết quả được phép và bị cấm.
- Điều kiện test và dữ liệu giả lập.
- Điểm quan sát.
- Mức bao phủ.
- Điều kiện pass/fail/inconclusive.
- Phiên bản/môi trường.
- Hạn chế cần ghi.

## 7. Các nhóm security requirements phổ biến

### 7.1. Identity và authentication

Yêu cầu có thể bao gồm:
- Chỉ chấp nhận token/session từ issuer và audience được phê duyệt.
- Kiểm tra signature, expiry và các claim bắt buộc.
- MFA hoặc step-up authentication cho hành động rủi ro cao theo policy.
- Session hết hạn/thu hồi theo quy tắc đã định.
- Workload identity không dùng chung credential không cần thiết.
- Quy trình reset/recovery không yếu hơn cơ chế xác thực chính.
- Không tin identity header do client tự gửi.

Ví dụ requirement:

> `report-api` chỉ chấp nhận access token có chữ ký hợp lệ, issuer/audience được cấu hình và thời hạn còn hiệu lực; token sai issuer, sai audience, hết hạn hoặc chữ ký không hợp lệ phải bị từ chối trước khi xử lý dữ liệu.

### 7.2. Authorization và least privilege

Yêu cầu nên xác định:
- Actor, role/attribute và action.
- Resource ownership/tenant scope.
- Purpose/case approval khi cần.
- Field-level disclosure.
- Workload/service permissions.
- Admin/break-glass access.
- Revoke và access review.

Ví dụ:

> Mọi thao tác `report:read` và `report:export` phải kiểm tra quyền trên resource và tenant ở server-side; client-supplied tenant ID không được dùng làm nguồn thẩm quyền. Các trường hợp cross-tenant, missing context và role-only access phải bị từ chối.

### 7.3. Data protection và privacy

Yêu cầu có thể bao gồm:
- Data minimization theo use case.
- Encryption in transit/at rest theo baseline.
- Key lifecycle và separation of duties.
- Masking/pseudonymization khi phù hợp.
- Retention/deletion cho bản sao.
- Quyền truy cập data exports và signed URLs.
- Kiểm soát data sharing với vendor.
- Không đưa dữ liệu nhạy cảm vào test fixture/log ngoài policy.

Ví dụ:

> `customer-summary` chỉ trả các trường được duyệt cho use case xem trạng thái; thay đổi schema thêm trường nhạy cảm phải qua review và contract test trước khi phát hành.

### 7.4. Input validation và output handling

Yêu cầu:
- Validate type, range, length, format và business invariants ở server.
- Reject malformed/oversized input theo giới hạn.
- Dùng parameterized query hoặc ORM binding phù hợp.
- Encode output theo context.
- Không đưa stack trace hoặc internal details ra client.
- File upload phải kiểm tra loại, kích thước, content và storage boundary.
- Không tin metadata hoặc MIME type do client khai báo.

Ví dụ:

> `report-api` phải giới hạn `pageSize` trong khoảng được phê duyệt, từ chối giá trị âm hoặc vượt ngưỡng, và áp dụng tenant/resource filter trước khi trả dữ liệu.

### 7.5. API và service-to-service

Yêu cầu:
- TLS/mTLS và peer validation trên các hop thuộc scope.
- API schema/contract, versioning và deprecation.
- Authentication và authorization cho từng route.
- Rate limiting/quota cho endpoint nhạy cảm.
- Idempotency cho action có side effect.
- Webhook signature/replay handling.
- Không fallback sang plaintext hoặc bỏ xác minh certificate.
- Internal API không mặc định trusted vì nằm trong private network.

### 7.6. Cryptography và key management

Yêu cầu cần nêu:
- Data/key nào cần bảo vệ và ở trạng thái nào.
- Baseline protocol/algorithm theo standard có phiên bản.
- Nguồn tạo, cấp, lưu, sử dụng và thu hồi key.
- Rotation/expiry và monitoring.
- Quyền truy cập key và separation of duties.
- Hành vi khi KMS/secret manager lỗi.
- Không tự phát minh thuật toán hoặc hardcode key.

### 7.7. Logging, audit và accountability

Yêu cầu:
- Event nào phải ghi.
- Trường nào được ghi và trường nào phải loại bỏ.
- Principal/action/resource/outcome/time/correlation cần thiết.
- Integrity, access, retention và source-health.
- Alert khi collector mất nguồn.
- Audit evidence cho privileged action.
- Không log raw secret hoặc payload thừa.

### 7.8. Secure configuration và infrastructure

Yêu cầu:
- Secure defaults và deny-by-default.
- Không có public storage/management endpoint trái policy.
- IAM/network policy có scope.
- Secrets không nằm trong source/image/log.
- IaC/config change được review và kiểm tra.
- Runtime drift được phát hiện.
- Environment tách biệt và non-production data được quản lý.

### 7.9. Secure development và software supply chain

Yêu cầu:
- Code review và branch protection.
- SAST/SCA/secret scanning theo scope.
- Dependency inventory và xử lý vulnerability theo risk.
- Artifact provenance/integrity khi áp dụng.
- Build/deploy identity tách quyền.
- Pipeline không tự cấp quyền production ngoài approval.
- Release evidence gắn commit, artifact và deployment.

Một requirement không nên chỉ nói “chạy SAST”. Cần chỉ rõ **scope, rule/version, severity policy, cách xử lý finding, ngoại lệ, evidence và điều kiện release**. Công cụ chạy xanh nhưng không scan đúng repository hoặc không có dependency inventory thì không chứng minh yêu cầu đạt.

### 7.10. Availability, resilience và fail secure

Yêu cầu:
- Timeout, retry, backoff và resource limits.
- Rate limiting/abuse prevention.
- Backup, restore, DR và RTO/RPO theo yêu cầu.
- Idempotency/reconciliation.
- Fail-secure khi authN/authZ/KMS/TLS/audit lỗi.
- Degraded mode có scope/owner/expiry.
- Recovery không mở lại quyền đã revoke.

## 8. Security requirement và non-functional requirement

Security thường được xem là một nhóm **quality attribute/non-functional requirement**, nhưng nhiều yêu cầu bảo mật cũng mô tả hành vi chức năng cụ thể.

| Loại | Ví dụ | Cách nghiệm thu |
| --- | --- | --- |
| Security functional requirement | User chỉ đọc report của tenant được phép | Authorization tests |
| Security non-functional requirement | Kết nối thuộc scope phải dùng TLS baseline | Handshake/config/runtime verification |
| Security operational requirement | Certificate phải được theo dõi hết hạn | Alert test, inventory và owner |
| Security process requirement | Change có trust boundary phải qua threat review | PR/approval record |
| Security assurance requirement | Claim phải có evidence gắn deployment | Evidence register/reviewer |

Ví dụ yêu cầu hiệu năng và bảo mật có thể xung đột: kiểm tra policy ở mỗi request làm tăng latency. Không được tự bỏ kiểm tra để đạt performance. Có thể tối ưu bằng cache, batching hoặc policy evaluation gần service, nhưng phải chứng minh freshness, revocation và isolation vẫn đạt.

## 9. Từ risk scenario đến requirement: phương pháp thực hiện

### Bước 1 – Mô tả risk scenario

Ví dụ:

> Attacker chiếm session của user tenant A, thay `reportId` để đọc report của tenant B. API chỉ xác thực token và không kiểm tra resource ownership.

Ghi:
- Asset: report và dữ liệu tài chính.
- Actor: user/attacker có session hợp lệ.
- Entry point: `GET /reports/{reportId}`.
- Weakness: thiếu object-level authorization.
- Impact: lộ dữ liệu giữa tenant.
- Existing controls: OIDC, gateway, TLS.
- Control gap: không có resource/tenant check.

### Bước 2 – Viết security objective

> Bảo đảm dữ liệu report chỉ được tiết lộ cho principal có quyền trên report đó trong tenant tương ứng.

### Bước 3 – Tách thành requirements

| ID | Requirement |
| --- | --- |
| **SR-REPORT-01** | Server phải xác minh principal từ token đã được kiểm chứng |
| **SR-REPORT-02** | Server phải xác định tenant/resource ownership từ nguồn dữ liệu tin cậy |
| **SR-REPORT-03** | API phải từ chối mọi yêu cầu cross-tenant hoặc thiếu context |
| **SR-REPORT-04** | Response chỉ chứa field đã được phê duyệt cho use case |
| **SR-REPORT-05** | Từ chối truy cập phải không tạo export job hoặc side effect |
| **SR-REPORT-06** | Security event phải ghi nhận outcome và correlation mà không log raw token |
| **SR-REPORT-07** | CI phải chạy positive/negative tests cho các trường hợp trên |

### Bước 4 – Chọn controls

- OIDC resource server validation.
- `ReportAccessPolicy` kiểm tra actor/resource/tenant.
- Repository query có trusted tenant scope.
- Response DTO allowlist.
- Audit event và log redaction.
- Integration/contract tests trong pipeline.

### Bước 5 – Định nghĩa acceptance criteria

- User tenant A đọc report A: cho phép.
- User tenant A đọc report B: từ chối.
- Tenant header bị giả mạo: không thay đổi tenant context tin cậy.
- Tenant context thiếu: từ chối.
- Không tạo export job khi authorization thất bại.
- Log không chứa token hoặc raw report.
- Test chạy trên đúng artifact/build.

### Bước 6 – Lưu evidence và xử lý gap

Gắn requirement với test result, commit, artifact digest, deployment, runtime policy và reviewer. Nếu một test chưa chạy hoặc không bao phủ endpoint legacy, ghi `NOT_RUN` hoặc `INCONCLUSIVE`; không suy ra PASS.

## 10. Phân loại và ưu tiên requirements

Có thể phân loại theo mức độ quan trọng và rủi ro, nhưng cần dùng **tiêu chí nhất quán và được tổ chức phê duyệt**.

### Ví dụ priority

| Priority | Cách hiểu | Ví dụ |
| --- | --- | --- |
| **Critical** | Thất bại có thể gây hậu quả nghiêm trọng hoặc vi phạm điều kiện phát hành | Ngăn cross-tenant disclosure, bảo vệ admin credentials |
| **High** | Rủi ro đáng kể, cần xử lý trước release theo policy | TLS peer validation, export authorization |
| **Medium** | Rủi ro vừa hoặc có control bù trừ được chấp nhận trong phạm vi | Hardening một endpoint nội bộ ít nhạy cảm |
| **Low** | Cải tiến có tác động thấp, vẫn cần owner và thời hạn | Cải thiện metadata phục vụ audit |

Priority không phải risk score phổ quát. Cần xét impact, likelihood, exposure, exploitability, control coverage, obligations và business context. Không hạ priority chỉ vì remediation khó.

### Must/Should/Could

Có thể dùng MoSCoW để quản lý phạm vi:
- **Must:** điều kiện bắt buộc để release/operation.
- **Should:** cần thực hiện, ngoại lệ phải có lý do và owner.
- **Could:** cải tiến có thể lên kế hoạch sau.

Không dùng **Could** để làm nhẹ một nghĩa vụ bắt buộc hoặc một rủi ro không thể chấp nhận. Phải có rule rõ ai được quyết định priority và exception.

## 11. Yêu cầu bảo mật phải kiểm tra được trong CI/CD

Một yêu cầu chỉ tồn tại trong backlog dễ bị quên. Với những yêu cầu phù hợp, cần đưa kiểm tra vào pipeline.

### Ví dụ pipeline

~~~mermaid
flowchart TD
    PR["Pull request"] --> REVIEW["Code review + requirement impact"]
    REVIEW --> STATIC["SAST / SCA / secret scan"]
    STATIC --> UNIT["Unit tests"]
    UNIT --> CONTRACT["API/schema/authorization contract tests"]
    CONTRACT --> BUILD["Build artifact + digest"]
    BUILD --> DEPLOYTEST["Deploy test environment"]
    DEPLOYTEST --> NEGATIVE["Security integration / negative tests"]
    NEGATIVE --> APPROVAL["Review evidence + release approval"]
    APPROVAL --> PROD["Production deployment"]
    PROD --> RUNTIME["Runtime config / telemetry / drift checks"]
    RUNTIME --> REVIEW2["Continuous assurance and reassessment"]
~~~

### Ví dụ quality gates

| Gate | Requirement được hỗ trợ | Điều kiện |
| --- | --- | --- |
| Secret scanning | Không đưa secret vào repository | Secret thật được xử lý theo incident/remediation policy |
| SAST | Secure coding requirements | Finding được triage theo risk, không chỉ đếm |
| SCA | Dependency/vulnerability requirements | Version, exposure, fix/exception có owner |
| Unit tests | Logic validation/policy | Positive và negative behavior |
| Contract tests | API/event schema và field allowlist | Consumer/producer không tự mở rộng data exposure |
| Integration tests | DB/IAM/TLS/authZ | Đúng dependency behavior và error path |
| IaC policy | Network/storage/IAM baseline | Effective planned config đáp ứng policy |
| Artifact verification | Provenance/integrity | Digest/signature theo quy trình |
| Runtime checks | Deployed control effectiveness | Actual config, route, role và evidence freshness |

Không phải requirement nào cũng có thể kiểm tra hoàn toàn trong CI. Ví dụ access review, vendor assurance và restore exercise cần quy trình/hoạt động riêng; CI có thể kiểm tra trigger hoặc evidence freshness, nhưng không thay được đánh giá thực tế.

## 12. Ví dụ Java/Spring Boot: chuyển requirement thành code và test

### 12.1. Requirement mẫu

**SR-REPORT-03:** `report-api` phải từ chối yêu cầu đọc report nếu tenant được xác minh của principal không trùng tenant của report. Tenant ID do client gửi không được dùng làm nguồn thẩm quyền.

Acceptance criteria:
- Principal có quyền và report cùng tenant: cho phép.
- Principal khác tenant: từ chối.
- Tenant context thiếu: từ chối.
- Header `X-Tenant-Id` giả mạo không làm thay đổi tenant tin cậy.
- Khi từ chối, không trả report content và không tạo side effect.

### 12.2. Policy logic

~~~java
import java.util.Objects;

public final class ReportAccessPolicy {

    public record Actor(String principalId, String trustedTenantId) {}

    public record Report(String reportId, String tenantId) {}

    public boolean mayRead(Actor actor, Report report) {
        Objects.requireNonNull(actor, "actor");
        Objects.requireNonNull(report, "report");

        if (actor.principalId() == null
                || actor.trustedTenantId() == null
                || report.tenantId() == null) {
            return false;
        }

        return actor.trustedTenantId().equals(report.tenantId());
    }
}
~~~

Đây là policy minh họa tối giản. Ứng dụng thật cần kiểm tra thêm quyền `REPORT_READ`, trạng thái tài nguyên, classification, delegated/support access, purpose và điều kiện nghiệp vụ. `trustedTenantId` phải đến từ authenticated context/relationship được server xác minh, không phải request header.

### 12.3. JUnit tests

~~~java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;

class ReportAccessPolicyTest {

    private final ReportAccessPolicy policy = new ReportAccessPolicy();

    @Test
    void allowsSameTenant() {
        var actor = new ReportAccessPolicy.Actor("user-01", "tenant-A");
        var report = new ReportAccessPolicy.Report("report-01", "tenant-A");

        assertTrue(policy.mayRead(actor, report));
    }

    @Test
    void deniesCrossTenant() {
        var actor = new ReportAccessPolicy.Actor("user-01", "tenant-A");
        var report = new ReportAccessPolicy.Report("report-02", "tenant-B");

        assertFalse(policy.mayRead(actor, report));
    }

    @Test
    void deniesMissingTenantContext() {
        var actor = new ReportAccessPolicy.Actor("user-01", null);
        var report = new ReportAccessPolicy.Report("report-01", "tenant-A");

        assertFalse(policy.mayRead(actor, report));
    }

    @Test
    void deniesMissingReportTenant() {
        var actor = new ReportAccessPolicy.Actor("user-01", "tenant-A");
        var report = new ReportAccessPolicy.Report("report-01", null);

        assertFalse(policy.mayRead(actor, report));
    }
}
~~~

Unit tests chứng minh logic policy với input giả. Chúng chưa chứng minh controller lấy đúng identity, repository không query ngoài scope hoặc route khác không bypass policy. Cần integration tests và runtime evidence.

### 12.4. Repository query có tenant scope

~~~sql
SELECT r.id, r.status, r.updated_at
FROM reports r
WHERE r.id = :reportId
  AND r.tenant_id = :trustedTenantId;
~~~

`trustedTenantId` phải được lấy từ authenticated principal và policy server-side. Nếu không tìm thấy record, response có thể được thiết kế đồng nhất để tránh tiết lộ record tồn tại ở tenant khác. Không dùng `tenantId` từ query string làm nguồn thẩm quyền.

### 12.5. Controller/service flow

~~~java
public ReportSummary getReport(
        AuthenticatedActor actor,
        String reportId) {

    Report report = repository.findById(reportId)
            .orElseThrow(ReportNotFoundException::new);

    if (!accessPolicy.mayRead(
            new ReportAccessPolicy.Actor(
                    actor.principalId(), actor.trustedTenantId()),
            new ReportAccessPolicy.Report(
                    report.id(), report.tenantId()))) {
        throw new AccessDeniedException("Access denied");
    }

    return new ReportSummary(
            report.id(), report.status(), report.updatedAt());
}
~~~

Đây là ví dụ minh họa luồng. Với dữ liệu nhạy cảm, có thể dùng query projection có tenant filter ngay từ database để tránh tải record trái scope trước khi kiểm tra. Cần kiểm tra consistency giữa authorization và data access để tránh TOCTOU khi ownership thay đổi.

### 12.6. Test tích hợp cần bổ sung

| Test | Kịch bản | Kết quả |
| --- | --- | --- |
| INT-01 | Token hợp lệ, cùng tenant | Trả summary đúng contract |
| INT-02 | Token hợp lệ, khác tenant | 403/404 theo policy, không trả body |
| INT-03 | Tenant header giả mạo | Không đổi trusted tenant context |
| INT-04 | Token sai issuer/audience | 401, không gọi repository |
| INT-05 | Report không tồn tại | Response không tiết lộ dữ liệu |
| INT-06 | Authorization bị từ chối | Không tạo export job |
| INT-07 | Audit collector lỗi | Hành vi theo requirement audit/degraded mode |
| INT-08 | Ownership đổi giữa các bước | Kiểm soát transaction/consistency theo thiết kế |

## 13. Requirement cho API, event và data contract

Một API có thể tuân thủ authorization nhưng vẫn trả thừa dữ liệu. Vì vậy, requirement phải xét **field-level disclosure, event consumer và bản sao**.

### Ví dụ API contract

| Field | Use case đọc trạng thái | Use case support đã duyệt | Ghi chú |
| --- | --- | --- | --- |
| reportId | Có | Có | Reference |
| status | Có | Có | Trạng thái |
| updatedAt | Có | Có | Metadata |
| customerEmail | Không | Có thể có | Chỉ khi cần và được phép |
| bankAccount | Không | Không mặc định | Sensitive data |
| internalRiskScore | Không | Không mặc định | Nội bộ/derived data |
| accessToken | Không | Không | Không bao giờ đưa vào response |

Requirement:
> Response của mỗi API version chỉ được chứa field nằm trong contract được duyệt cho use case và actor; field mới hoặc thay đổi classification phải qua review và contract test trước khi phát hành.

### Event contract

- Producer chỉ publish field cần cho consumer purpose.
- Consumer mới phải được review trước khi cấp subscription.
- Schema evolution không tự động mở rộng data disclosure.
- DLQ/replay có quyền và retention riêng.
- Event phải có version, source, event ID và metadata cần thiết; không chứa secret/raw payload thừa.

### Export contract

- Export scope gồm tenant, resource population, columns, purpose và owner.
- Job lưu approval/context cần thiết và expiry.
- Worker xác minh job trước khi chạy.
- File có storage policy, TTL và download authorization.
- URL ký có scope và thời hạn theo risk.
- Job retry/replay không mở rộng quyền hoặc tạo bản sao không kiểm soát.

## 14. Security requirement cho logging và evidence

Logging là một miền yêu cầu bảo mật riêng vì log vừa giúp điều tra vừa có thể trở thành nơi rò dữ liệu.

Một requirement tốt cần nêu:
- Sự kiện nào phải được ghi.
- Actor/resource/action/outcome nào cần lưu.
- Dữ liệu nào bị cấm ghi.
- Log được bảo vệ, truy cập, lưu giữ và xóa ra sao.
- Nguồn log mất kết nối được phát hiện thế nào.
- Ai có quyền đọc/sửa/xóa.
- Evidence của audit được gắn với version/deployment nào.

Ví dụ:
> Mỗi lần export report phải tạo security audit event có actor reference, tenant/resource reference, action, outcome, timestamp và correlation ID; event không được chứa raw access token hoặc full report payload. Nếu audit store không sẵn sàng, hành vi export phải theo degraded-mode policy đã phê duyệt.

Test có thể dùng synthetic marker, kiểm tra application logs, gateway, APM, queue và SIEM; đồng thời xác minh source-health để tránh kết luận PASS khi collector đã mất dữ liệu.

## 15. Security requirements cho secrets và cryptography

Một số requirement mẫu:

| ID | Requirement | Cách kiểm chứng |
| --- | --- | --- |
| **SR-CRYPTO-01** | Kết nối thuộc scope phải dùng TLS baseline được phê duyệt và xác minh peer | Handshake, wrong-CA/hostname tests |
| **SR-CRYPTO-02** | Private key không được commit vào source, image hoặc log | Secret scan, artifact scan, access review |
| **SR-CRYPTO-03** | Key/certificate có owner, expiry, rotation và incident process | Inventory, alert/rotation test |
| **SR-CRYPTO-04** | Khi KMS lỗi, service không dùng key mặc định hoặc fallback plaintext | KMS failure-injection |
| **SR-SECRET-01** | Secret được cấp theo workload identity và scope tối thiểu | IAM snapshot, unauthorized access test |
| **SR-SECRET-02** | Credential bị revoke không còn được dùng sau thời hạn policy | Revoke/rotation integration test |

Không ghi một thuật toán hoặc thời hạn cố định nếu chưa có baseline áp dụng. Requirement nên tham chiếu security standard có version và quy định cách kiểm chứng.

## 16. Requirement cho secure development và supply chain

Yêu cầu bảo mật không chỉ nằm trong ứng dụng runtime. Build/deploy pipeline cũng có quyền tác động production.

Ví dụ:
- Pull request thay security-sensitive code phải có review theo branch policy.
- CI phải phát hiện secret trong phạm vi repository/artifact được kiểm tra.
- Dependency vulnerability phải được triage theo risk và có owner/deadline.
- Build artifact có digest/provenance để đối chiếu với deployment.
- Build identity không được tự cấp quyền production ngoài workflow phê duyệt.
- IaC changes phải được kiểm tra policy trước khi deploy.
- Production config drift phải tạo alert/finding.
- Release evidence phải liên kết commit, artifact và deployment.

Một requirement không nên chỉ nói “chạy SAST”. Cần chỉ rõ **scope, rule/version, severity policy, cách xử lý finding, ngoại lệ, evidence và điều kiện release**. Công cụ chạy xanh nhưng không scan đúng repository hoặc không có dependency inventory thì không chứng minh yêu cầu đạt.

## 17. Xử lý yêu cầu mâu thuẫn, chưa rõ và không khả thi

Mâu thuẫn thường xuất hiện giữa security, usability, performance, availability, privacy, retention và nghĩa vụ hợp đồng.

### Ví dụ

- Product muốn support xem mọi dữ liệu để xử lý nhanh; privacy yêu cầu chỉ xem field cần cho case.
- Availability yêu cầu hệ thống tiếp tục khi IdP lỗi; security yêu cầu không cấp quyền khi không xác minh được identity.
- Retention yêu cầu xóa dữ liệu sớm; incident/legal hold có thể yêu cầu bảo toàn một phần evidence trong phạm vi hợp lệ.
- Performance yêu cầu cache authorization; revocation yêu cầu quyền bị thu hồi có hiệu lực kịp thời.

### Cách xử lý

1. Ghi rõ hai requirements và nguồn của từng yêu cầu.
2. Xác định asset, actor, action, impact và risk nếu chọn mỗi phương án.
3. Xem xét kiến trúc thay thế: field-level access, bounded cache, async workflow, durable audit hoặc degraded mode.
4. Xác định người có thẩm quyền quyết định và người chịu residual risk.
5. Lưu rationale, phạm vi, thời hạn, compensating controls và review trigger.
6. Chuyển quyết định thành requirement/design update và test mới.

Không tự giải quyết mâu thuẫn bằng cách bỏ requirement bảo mật hoặc ghi một exception vô thời hạn. Nếu chưa có quyết định có thẩm quyền, requirement cần giữ trạng thái **BLOCKED/OPEN** theo quy trình nội bộ.

## 18. Traceability: nối requirement với code, test và evidence

Traceability giúp biết **một yêu cầu được thực hiện ở đâu, kiểm tra bằng gì và hiện còn đạt hay không**.

### Traceability matrix mẫu

| Risk | Objective | Requirement | Control | Test | Evidence |
| --- | --- | --- | --- | --- | --- |
| Cross-tenant read | Confidentiality | SR-REPORT-03 | Object-level authZ | INT-02, INT-03 | CI run, deployment, policy snapshot |
| Token leakage | Secret protection | SR-LOG-01 | Redaction at source | LOG-01 | Synthetic marker scan, source-health |
| Plaintext internal hop | Transport confidentiality | SR-CRYPTO-01 | TLS/mTLS | TLS-01, TLS-02 | Handshake/config snapshot |
| Worker overprivilege | Least privilege | SR-IAM-01 | Scoped workload role | IAM-03 | Effective IAM + deny test |
| Duplicate payment | Integrity | SR-ASYNC-01 | Idempotency/outbox | ASYNC-04 | Duplicate delivery test |
| Untrusted release | Supply-chain integrity | SR-SDLC-01 | Artifact provenance/review | CI-06 | Digest, provenance, approval |

### Traceability theo hai chiều

- **Forward traceability:** từ risk/requirement tới design, code, test và evidence. Giúp phát hiện yêu cầu chưa có implementation/test.
- **Backward traceability:** từ code, endpoint, config, vendor hoặc test về requirement/risk. Giúp phát hiện thay đổi chưa được đánh giá hoặc control không còn mục đích rõ.

Một requirement không có test/evidence không tự động là vô ích, nhưng cần có verification plan và owner. Một control không truy về risk/objective nào có thể đang dư thừa, sai scope hoặc cần rationale khác.

### Khi requirement thay đổi

Thay đổi một requirement cần đánh giá:
- API/schema/consumer nào bị ảnh hưởng?
- Code/config/test nào cần sửa?
- Security controls nào phụ thuộc?
- Evidence cũ còn hợp lệ không?
- Có cần retest ở environment khác?
- Risk/residual risk và approval có thay đổi không?

Không tái sử dụng report cũ nếu artifact, config, policy, dependency hoặc scope đã đổi theo cách ảnh hưởng kết luận.

## 19. Requirement lifecycle và trạng thái

Một vòng đời đơn giản:

~~~mermaid
stateDiagram-v2
    [*] --> Draft
    Draft --> Reviewed: Source / scope / wording rõ
    Reviewed --> Approved: Owner và thẩm quyền chấp nhận
    Reviewed --> Draft: Cần làm rõ
    Approved --> Implemented: Control được triển khai
    Implemented --> Verified: Test và evidence đạt
    Implemented --> Failed: Test thất bại
    Failed --> Remediating: Có owner và kế hoạch
    Remediating --> Implemented: Fix được deploy
    Verified --> Reassess: Thay đổi/trigger
    Reassess --> Reviewed
    Approved --> Exception: Có quyết định risk hợp lệ
    Exception --> Reassess: Hết hạn hoặc trigger
    Verified --> Retired: Tài sản/use case kết thúc có kiểm soát
~~~

### Trạng thái gợi ý

| Trạng thái | Ý nghĩa |
| --- | --- |
| **DRAFT** | Đang thu thập/soạn, chưa được review |
| **REVIEWED** | Đã kiểm tra tính rõ ràng, nguồn và khả năng xác minh |
| **APPROVED** | Được owner/thẩm quyền chấp thuận |
| **IMPLEMENTED** | Control đã triển khai nhưng chưa đủ evidence verification |
| **VERIFIED** | Đã kiểm chứng đạt trong scope và version xác định |
| **FAILED** | Có bằng chứng không đáp ứng |
| **INCONCLUSIVE** | Thiếu dữ liệu/coverage để kết luận |
| **EXCEPTION** | Có chấp nhận residual risk theo thẩm quyền/thời hạn |
| **RETIRED** | Requirement không còn áp dụng sau khi asset/use case được kết thúc |

Không đồng nhất IMPLEMENTED với VERIFIED; không đồng nhất EXCEPTION với VERIFIED. Requirement có thể cần review lại khi có incident, thay đổi threat, thêm service, thay vendor, thay data flow hoặc hết hạn exception.

## 20. Security assurance: cách kiểm chứng requirement

### 20.1. Các phương pháp verification

| Phương pháp | Khi phù hợp | Giới hạn |
| --- | --- | --- |
| **Test** | Hành vi có thể tạo input và quan sát output | Chỉ bao phủ scenario đã test |
| **Inspection** | Review code, config, policy, IaC, architecture | Source có thể khác runtime |
| **Analysis** | Threat model, static analysis, dependency analysis | Phụ thuộc model/rule và coverage |
| **Demonstration** | Thực hiện workflow có quan sát | Có thể không test failure/negative path |
| **Operational review** | Access review, key rotation, backup, alert, vendor evidence | Phụ thuộc kỳ review và tính đầy đủ |
| **Runtime verification** | Effective IAM, route, TLS, deployment/config, log source | Chỉ phản ánh scope/time quan sát |

### 20.2. Acceptance criteria

Với mỗi requirement, xác định:
- **Preconditions:** identity, role, data, environment, policy version.
- **Action:** thao tác cần kiểm tra.
- **Expected allowed behavior:** trường hợp được phép.
- **Expected denied behavior:** trường hợp bị cấm.
- **Side effects:** job, event, file, database write có được tạo không.
- **Observability:** event/evidence nào cần xuất hiện.
- **Scope/coverage:** endpoints, tenants, regions, versions.
- **Result rule:** PASS, FAIL, INCONCLUSIVE, NOT_RUN.
- **Reviewer:** người xác nhận và thời điểm.

### 20.3. PASS không chỉ là test xanh

Một requirement có thể được xem là PASS khi:
- Test phù hợp đã chạy trên đúng version/scope.
- Kết quả thực tế đạt acceptance criteria.
- Runtime/config evidence phù hợp nếu requirement liên quan vận hành.
- Không có finding chưa xử lý làm vô hiệu claim.
- Nguồn evidence đầy đủ và có reviewer.
- Limitation/residual risk được ghi rõ và không vượt tiêu chí chấp nhận.

Nếu test không chạy, environment không đúng, scanner mất nguồn hoặc một route chưa được inventory, kết luận nên là NOT_RUN hoặc INCONCLUSIVE, không tự suy ra PASS.

## 21. Evidence register cho security requirements

### Mẫu YAML

Các giá trị placeholder trong mẫu cần được thay bằng tham chiếu thực tế; chúng không phải bằng chứng đã thu thập.

~~~yaml
requirement_id: SR-REPORT-03
title: "Prevent cross-tenant report access"
service: report-api
requirement_version: "2.1"
status: VERIFIED
source:
  risk_ids: [RISK-REPORT-01]
  objective_ids: [OBJ-CONFIDENTIALITY]
  policy_refs: ["<APPROVED_ACCESS_POLICY_VERSION>"]
scope:
  environments: ["production"]
  endpoints: ["GET /reports/{reportId}"]
  actors: ["authenticated-customer"]
  resources: ["tenant-scoped-report"]
statement: >
  The API denies access when the trusted tenant context of the principal
  does not match the tenant assigned to the requested report.
acceptance_criteria:
  - "Same-tenant authorized read returns only approved fields"
  - "Cross-tenant read is denied without report content"
  - "Client-supplied tenant header cannot change trusted context"
  - "Denied request creates no export job or data side effect"
verification:
  methods: ["integration-test", "runtime-review"]
  test_refs:
    - "<SAME_TENANT_POSITIVE_TEST>"
    - "<CROSS_TENANT_NEGATIVE_TEST>"
    - "<SPOOFED_TENANT_HEADER_TEST>"
  source_commit: "<COMMIT_ID>"
  artifact_digest: "<ARTIFACT_DIGEST>"
  deployment_id: "<DEPLOYMENT_ID>"
  runtime_policy_ref: "<EFFECTIVE_POLICY_VERSION>"
  assessed_at: "<ISO_8601_UTC>"
  reviewer: "<AUTHORIZED_REVIEWER>"
evidence:
  refs:
    - "<CI_TEST_REPORT>"
    - "<RUNTIME_CONFIG_SNAPSHOT>"
    - "<SANITIZED_AUDIT_SAMPLE>"
limitations: "<KNOWN_UNTESTED_PATHS_OR_REGIONS>"
findings: []
exception_ref: null
residual_risk: "<REVIEWED_RISK_STATEMENT>"
reassessment_triggers:
  - "Authorization policy or tenant model changes"
  - "New report endpoint or export path"
  - "Identity provider, database or service boundary changes"
~~~

Không lưu raw token, password, private key hoặc bản ghi khách hàng thật vào register. Evidence cần được quản lý quyền truy cập, integrity và retention; trường evidence.refs nên trỏ tới hệ thống lưu trữ được phê duyệt.

### Mẫu bảng traceability tối thiểu

| Requirement ID | Owner | Priority | Test refs | Evidence ref | Status | Review trigger |
| --- | --- | --- | --- | --- | --- | --- |
| SR-REPORT-03 | API Team | Critical | INT-02/03 | EV-REPORT-03 | Verified | AuthZ/schema change |
| SR-LOG-01 | Platform Team | High | LOG-01 | EV-LOG-01 | Inconclusive | New collector |
| SR-CRYPTO-01 | Platform Team | High | TLS-01/02 | EV-TLS-01 | Implemented | CA/client/route change |
| SR-IAM-01 | Cloud Owner | Critical | IAM-03 | EV-IAM-01 | Failed | Role/policy change |

## 22. Quản lý ngoại lệ và residual risk

Không phải mọi requirement đều có thể hoàn thành ngay. Nhưng ngoại lệ phải được quản trị rõ.

Một exception record cần:
- Requirement/risk bị ảnh hưởng.
- Lý do và bằng chứng tại sao chưa thể đáp ứng.
- Phạm vi chính xác (asset, endpoint, tenant, environment).
- Impact và residual risk.
- Compensating controls cùng cách kiểm chứng.
- Risk owner có thẩm quyền phê duyệt.
- Ngày hết hạn hoặc điều kiện xem xét lại.
- Kế hoạch remediation và mốc tiến độ.
- Trigger thu hồi ngoại lệ khi risk tăng hoặc control bù trừ thất bại.

**Exception không làm requirement tự động VERIFIED.** Có thể ghi EXCEPTION và trạng thái control thực tế riêng. Không dùng exception để che finding hoặc kéo dài một khoảng trống không có owner.

## 23. Change management và continuous assurance

Security requirements có thể mất hiệu lực khi hệ thống thay đổi.

### Trigger cần review

| Thay đổi | Requirement có thể bị ảnh hưởng | Hành động |
| --- | --- | --- |
| Thêm endpoint/API version | Authentication, authorization, rate limit, schema | Threat review, contract tests, negative tests |
| Thêm field/data class | Data minimization, classification, logging, retention | Data owner/privacy review, field tests |
| Thêm tenant hoặc thay ownership model | Tenant isolation, cache, DB policy | Cross-tenant tests và IAM review |
| Thêm worker/queue consumer | Workload identity, event scope, replay, audit | Consumer authorization và duplicate tests |
| Thay IdP/issuer/claim | Authentication, session, principal mapping | Token negative tests, rollout verification |
| Thay CA/KMS/key | TLS, encryption, key lifecycle | Rotation/invalid-key tests |
| Thêm vendor/region | Data sharing, trust boundary, residency/contract | Vendor review, DFD và evidence |
| Thay CI runner/build workflow | Supply-chain integrity, deployment privileges | CI IAM test, provenance verification |
| Thay logging/APM | Secret redaction, audit, source completeness | Synthetic marker/source-health tests |
| Thay backup/DR | Retention, recovery, access separation | Restore exercise, permission review |
| Incident/finding | Related requirements/controls | Reassess, remediation, retest |

### Continuous assurance không có nghĩa test mọi thứ mỗi phút

Tần suất và trigger nên theo:
- Mức criticality và thay đổi risk.
- Tốc độ thay đổi policy/identity/data flow.
- Thời hạn evidence và yêu cầu audit.
- Khả năng tự động hóa đáng tin.
- Chi phí và tác động của test.
- Những sự kiện cần review ngay như incident, key compromise hoặc privilege change.

Có thể dùng CI cho code/schema/config, scheduled checks cho IAM/certificate/evidence freshness và periodic exercises cho backup/incident response. Phải giữ owner và scope rõ.

## 24. Metrics để quản trị chất lượng requirements

| Metric | Đo điều gì | Giới hạn khi diễn giải |
| --- | --- | --- |
| % critical assets có requirements/owner | Độ bao phủ quản trị | Không chứng minh requirement đúng |
| % requirements có acceptance criteria | Khả năng kiểm chứng | Không chứng minh test đã chạy |
| % requirements có risk/source trace | Chất lượng nguồn và rationale | Source có thể đã lỗi thời |
| % requirements có test/evidence refs | Traceability | Link có thể trỏ tới evidence không phù hợp |
| % critical requirements VERIFIED | Mức đáp ứng đã được kiểm chứng | Phụ thuộc scope/coverage và freshness |
| Số requirement INCONCLUSIVE/NOT_RUN | Khoảng trống assurance | Không nên ép về 0 bằng cách hạ tiêu chí |
| Số exception quá hạn | Rủi ro chưa xử lý | Không phản ánh đầy đủ residual risk |
| Thời gian từ finding tới retest | Hiệu quả remediation | Ticket closed không tự chứng minh fix |
| Số thay đổi không có impact review | Change governance gap | Cần đối chiếu nguồn change completeness |
| Evidence freshness/source health | Mức tin cậy của hiện vật | Evidence mới vẫn có thể sai scope |

Tránh KPI “100% requirements Verified” nếu đội ngũ phải đổi INCONCLUSIVE thành PASS để đạt chỉ tiêu. Metric tốt phải làm lộ khoảng trống và hỗ trợ quyết định, không khuyến khích che giấu.

## 25. Vai trò và trách nhiệm

| Vai trò | Trách nhiệm | Đầu ra |
| --- | --- | --- |
| **Business/Product Owner** | Mục đích, use case, acceptance và ưu tiên nghiệp vụ | Business objectives, use-case scope |
| **System/Asset Owner** | Phân loại tài sản, impact và owner | Asset/data inventory |
| **Security Architect/AppSec** | Threat modeling, requirement review, control mapping | Security requirements, threat model |
| **Privacy/Legal/Compliance** | Xác nhận nghĩa vụ theo phạm vi áp dụng | Obligation mapping và decisions |
| **Developer/Tech Lead** | Phân tích tác động, triển khai và unit/integration tests | PR, implementation, test evidence |
| **QA/Security Tester** | Positive/negative/abuse/failure tests | Test plan, results, defects |
| **Platform/Ops/SRE** | IAM, TLS, KMS, logging, backup và runtime evidence | Effective config, operational records |
| **GRC/Control Owner** | Requirement register, review cadence, exception | Register, assessment, exception records |
| **Risk Owner** | Phê duyệt risk treatment và residual risk theo thẩm quyền | Risk decision |
| **Assessor/Audit** | Đánh giá độc lập khi cần, xác minh evidence và retest | Assessment report, findings |

Có thể gộp vai trò ở tổ chức nhỏ, nhưng cần phân định **ai đề xuất, ai review, ai phê duyệt, ai triển khai và ai chấp nhận residual risk**. Người viết requirement không mặc nhiên là người có quyền chấp nhận mọi rủi ro liên quan.

## 26. Case study: security requirements cho nền tảng báo cáo đa tenant

### Bối cảnh

Một nền tảng Java/Spring Boot có:
- `report-api` phục vụ customer và support agent.
- OIDC identity provider.
- PostgreSQL lưu report và metadata.
- Kafka phân phối export jobs.
- `export-worker` tạo file CSV.
- Object storage và signed download URLs.
- API gateway, APM/SIEM và backup/DR.
- CI/CD deploy qua Kubernetes.

Product yêu cầu: “Support agent cần xem và export report để hỗ trợ khách hàng nhanh hơn.”

### Bước phân tích

Nhóm phát hiện:
1. Support role có quyền xem report của mọi tenant.
2. API lấy tenantId từ header do client gửi.
3. ReportEntity được trả trực tiếp, gồm email và internal risk score.
4. Worker dùng IAM role có quyền đọc mọi bucket.
5. APM log raw request/response của export endpoint.
6. Job có thể retry sau khi quyền user bị revoke.
7. Signed URL chưa có expiry phù hợp.

### Chuyển thành requirements

| ID | Requirement | Priority |
| --- | --- | --- |
| **SR-01** | Support chỉ xem report thuộc case đã được phân công và phê duyệt; mọi quyết định được kiểm tra server-side | Critical |
| **SR-02** | Tenant context lấy từ identity/relationship đã xác minh; client header không thể thay đổi context | Critical |
| **SR-03** | Response chỉ chứa field được duyệt cho customer/support use case | High |
| **SR-04** | Worker chỉ truy cập bucket/prefix cần cho export job được xác minh | Critical |
| **SR-05** | Export job được kiểm tra quyền và expiry tại thời điểm thực thi theo workflow đã duyệt | High |
| **SR-06** | APM/gateway/application logs không chứa raw token hoặc report payload | High |
| **SR-07** | Signed URL giới hạn resource, thời hạn và quyền download theo policy | High |
| **SR-08** | Thay đổi API/schema/role/consumer kích hoạt review và test liên quan | High |
| **SR-09** | Finding cross-tenant/export có owner, remediation, retest và evidence | High |

### Acceptance criteria tiêu biểu

**SR-01**
- Support có case hợp lệ và đúng tenant: chỉ xem field cần thiết.
- Support không có case hoặc case không thuộc assignment: bị từ chối.
- Client tự khai case ID/tenant ID không tăng quyền.
- Case đóng/revoke trước execution: job xử lý theo policy mới hoặc snapshot đã phê duyệt có expiry.
- Denied action không tạo file hoặc signed URL.

**SR-04**
- Worker có thể ghi file vào bucket/prefix được cấp.
- Worker đọc bucket khác bị từ chối.
- Credential của report-api không thể sử dụng như worker admin.
- Runtime IAM policy khớp scope đã duyệt.

**SR-06**
- Synthetic token/payload marker không xuất hiện trong nguồn log được kiểm kê.
- Security audit event tối thiểu vẫn có actor/resource/outcome/correlation.
- Source-health xác nhận collector đang nhận dữ liệu.
- Log access/retention có owner và policy.

### Test và evidence

| Test | Kết quả mong đợi | Evidence |
| --- | --- | --- |
| Customer cùng tenant đọc report | Chỉ trả summary đã duyệt | CI test + runtime response |
| Customer khác tenant đọc report | Deny, không có content | Negative test |
| Support không có case | Deny | Policy test + audit event |
| Spoof tenant/case header | Không đổi trusted context | Integration test |
| Worker đọc bucket ngoài scope | IAM deny | Effective IAM snapshot + access test |
| Job retry sau revoke | Không tạo export ngoài policy | Async integration test |
| APM raw marker scan | Không tìm thấy marker cấm, source healthy | Sanitized scan report |
| Signed URL sau expiry | Download bị từ chối | Storage test |
| API/schema thay đổi | CI gate yêu cầu review/contract test | PR/change record |

### Assurance claim

> Trong phạm vi customer/support read và export flows của production deployment đã đánh giá, tenant và case context được xác minh server-side; support chỉ đọc report thuộc case được phân công; response và export chỉ chứa field đã duyệt; worker bị giới hạn trong bucket/prefix cần thiết; job được kiểm tra lại theo policy tại thời điểm thực thi; logs thuộc phạm vi đã kiểm tra không chứa raw token hoặc report payload. Các vendor, legacy routes và region chưa kiểm chứng được ghi rõ.

Claim chỉ được xem là đạt khi có evidence đúng commit, artifact, deployment, runtime policy, test coverage và reviewer. Việc requirement đã được đưa vào backlog hoặc ticket đã đóng không đủ.

## 27. Bài tập thực hành

**Tình huống:** một ứng dụng Spring Boot xử lý đơn hàng và hồ sơ khách hàng. Hệ thống có gateway, OIDC, PostgreSQL, Redis, Kafka, export worker, object storage, SIEM, CI/CD và backup. Yêu cầu Product ban đầu chỉ là:

> “Bảo vệ dữ liệu khách hàng và cho support xử lý nhanh.”

Trong review, nhóm phát hiện:
- API trả nguyên entity.
- Support có role chung, không kiểm tra case/tenant.
- Worker có quyền storage rộng.
- Cache authorization không gắn policy version.
- Gateway log Authorization header.
- Broker có listener plaintext.
- CI runner có quyền sửa production IAM.
- Backup chưa có restore evidence.
- Một số route legacy chưa được inventory.

### Yêu cầu

1. Xác định ít nhất **sáu assets** và security objectives.
2. Viết **năm risk scenarios** với actor, entry point, weakness và impact.
3. Chuyển yêu cầu Product thành ít nhất **10 security requirements** có ID, owner, priority, scope và source.
4. Viết acceptance criteria cho ba requirements quan trọng nhất.
5. Map mỗi requirement vào control, test và evidence.
6. Thiết kế ít nhất **10 positive/negative/integration tests**, gồm cross-tenant, case approval, cache revoke, worker IAM, token logging, TLS, CI privilege, backup restore và legacy route.
7. Xử lý mâu thuẫn giữa support convenience và least privilege.
8. Đưa ra exception record cho một legacy route chưa thể sửa ngay, gồm risk owner, expiry, compensating control và retest.
9. Xác định trigger review khi thêm field, API version, vendor hoặc consumer mới.
10. Viết một assurance claim có scope và limitations; nêu điều kiện PASS/FAIL/INCONCLUSIVE.

### Hướng giải mẫu

| Gap | Requirement nên có | Verification |
| --- | --- | --- |
| API trả nguyên entity | Response field allowlist theo use case | Contract test và runtime response |
| Support role chung | Case/resource/tenant authorization | Negative tests với case sai/thiếu |
| Worker IAM rộng | Scoped workload permission | Effective IAM và deny tests |
| Cache stale | Policy version/TTL/revocation behavior | Revoke/cache invalidation tests |
| Token trong log | Redaction tại nguồn và log source inventory | Synthetic marker test |
| Broker plaintext | TLS/peer validation cho producer/consumer | Handshake và plaintext listener test |
| CI runner quá quyền | Tách build/deploy và approval | IAM denied-change test |
| Backup thiếu restore evidence | Restore/integrity/permission requirement | Restore exercise |
| Legacy route thiếu inventory | Endpoint discovery và authorization baseline | Route/bypass test |

### Câu hỏi nâng cao

Một requirement ghi: “100% API phải có authentication.” Tất cả endpoint đều yêu cầu JWT hợp lệ, nhưng user tenant A có thể đổi ID để xem dữ liệu tenant B.

**Requirement đã đạt chưa?**

**Định hướng:** có thể requirement authentication đã đạt trong scope test, nhưng mục tiêu confidentiality/tenant isolation chưa đạt vì thiếu object-level authorization. Cần requirement riêng cho resource/action/tenant, negative tests và evidence. Không dùng một requirement đạt để suy ra toàn bộ security assurance đạt.

## 28. Những sai lầm thường gặp

| Ngộ nhận | Vì sao sai? | Thực hành phù hợp |
| --- | --- | --- |
| “Security requirement là câu ghi trong policy.” | Policy thường ở mức nguyên tắc, chưa có acceptance criteria | Chuyển thành requirement cụ thể và kiểm chứng được |
| “Có WAF là đáp ứng yêu cầu API security.” | WAF không thay object authorization/business logic | Map control theo attack path |
| “User đã login là được đọc dữ liệu.” | Authentication không thay authorization | Principal/action/resource/tenant checks |
| “Requirement càng dài càng đầy đủ.” | Nhiều điều kiện trộn khiến không thể test rõ | Tách atomic requirements và liên kết |
| “Mọi yêu cầu bảo mật đều là non-functional.” | Có yêu cầu mô tả hành vi chức năng cụ thể | Phân loại theo hành vi và quality attribute |
| “Chạy SAST xanh nghĩa là secure.” | SAST có coverage và giới hạn | Kết hợp tests, review, runtime evidence |
| “Requirement có test ref là đã verified.” | Test có thể chưa chạy hoặc sai artifact | Kiểm tra result, version, scope và reviewer |
| “Control đã triển khai thì requirement đạt.” | Control có thể sai cấu hình hoặc không có coverage | Operating effectiveness verification |
| “Một requirement có thể đại diện mọi risk.” | Risk khác nhau cần objectives/criteria khác | Traceability nhiều chiều |
| “Tenant ID từ client là đủ để phân quyền.” | Client có thể giả mạo giá trị | Trusted server-side identity/context |
| “Exception được duyệt là requirement đã đạt.” | Risk acceptance không thay trạng thái kỹ thuật | Ghi exception và residual risk riêng |
| “Ticket Done là finding đã đóng.” | Chưa chắc deploy/retest | Actual-state verification |
| “Không có finding nghĩa là không có vấn đề.” | Có thể thiếu test/source/coverage | INCONCLUSIVE khi không đủ evidence |
| “Một lần audit đủ cho vòng đời.” | Code, config, threat và vendor thay đổi | Continuous assurance và reassessment triggers |
| “Mọi requirement phải tự động hóa trong CI.” | Có review/vendor/restore cần phương pháp khác | Kết hợp CI, scheduled review và exercises |
| “Đặt KPI 100% PASS sẽ cải thiện bảo mật.” | Khuyến khích che giấu INCONCLUSIVE/FAIL | Đo coverage, freshness, gap và remediation |
| “Yêu cầu pháp lý có thể tự suy từ tên dữ liệu.” | Nghĩa vụ phụ thuộc jurisdiction và bối cảnh | Legal/privacy owner xác nhận nguồn |
| “Requirement không có owner vẫn có thể theo dõi.” | Không ai chịu trách nhiệm duy trì/ra quyết định | Gán owner và thẩm quyền |

## Ghi nhớ

- **Security requirement** mô tả điều kiện bảo mật hệ thống phải đáp ứng; cần phân biệt với objective, policy, control, implementation task, test và evidence.
- Yêu cầu phải bắt nguồn từ **assets, risk, threat model, architecture, obligations và workflow thực tế**, có nguồn và phạm vi rõ.
- Một requirement tốt có **ID ổn định, statement đơn nghĩa, rationale, owner, priority, acceptance criteria, verification method và traceability**.
- Chuyển risk thành chuỗi **risk → objective → requirement → control → test → evidence → finding → remediation/retest**; không nhảy từ risk trực tiếp sang công cụ.
- Security requirements phải bao phủ identity, authorization, data/privacy, API, cryptography, secrets, logging, supply chain, infrastructure, resilience và recovery theo bối cảnh.
- **IMPLEMENTED không đồng nghĩa VERIFIED**; test xanh không đủ nếu sai scope, artifact, environment hoặc thiếu runtime evidence.
- Exception phải có thẩm quyền, scope, residual risk, compensating controls, expiry và review trigger; không tự chuyển requirement FAIL thành PASS.
- Secure development cần quản lý requirement xuyên vòng đời và đánh giá lại khi thay đổi endpoint, data flow, identity, vendor, pipeline, cấu hình hoặc xảy ra incident.

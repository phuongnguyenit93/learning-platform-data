# Kiểm thử patch: Xác minh bản vá an toàn, tương thích và có bằng chứng

## 1. Kiểm thử patch là gì?

**Patch testing** (kiểm thử bản vá) là quá trình đánh giá có kế hoạch xem **một bản vá có thực sự khắc phục điểm yếu hoặc vấn đề được nhắm tới, có hoạt động đúng trong môi trường đích và có gây tác động ngoài ý muốn hay không**. Bằng chứng kiểm thử phải giúp người có trách nhiệm quyết định có thể triển khai, mở rộng rollout, giữ nguyên, rollback hay cần bổ sung kiểm soát rủi ro.

Trong **Patch management**, bản vá có thể là cập nhật:

- Mã ứng dụng, thư viện và dependency bắc cầu.
- Hệ điều hành, kernel, package manager và system libraries.
- Container base image, runtime và Kubernetes components.
- Network appliance, firmware, hypervisor hoặc thiết bị đầu cuối.
- Cấu hình bảo mật: IAM, authorization, firewall, TLS, WAF, admission policy.
- Database engine, schema, migration và database permissions.
- CI/CD plugin, build toolchain, artifact publishing và supply-chain controls.
- Dịch vụ managed/cloud, nơi nhà cung cấp thực hiện một phần cập nhật.
- Các cấu hình tạm thời dùng để giảm exposure trước khi có permanent fix.

**Kiểm thử patch không chỉ kiểm tra ứng dụng khởi động thành công.** Nó phải phân biệt được:

1. **Patch presence:** artifact/version/config đã thay đổi đúng như kế hoạch.
2. **Patch effectiveness:** đường lỗi hoặc điều kiện vulnerability đã được xử lý đúng.
3. **Regression safety:** các chức năng và security invariants quan trọng vẫn đúng.
4. **Operational readiness:** deployment, monitoring, rollback/recovery và support đáp ứng yêu cầu.
5. **Assurance evidence:** kết luận dựa trên test run, build, environment, version, phương pháp và giới hạn thực tế.

Trong module **SECURITY_SECURITY_ASSURANCE**, chuỗi tư duy xuyên suốt là:

**Risk/threat → Security requirement → Vulnerability/finding → Patch design → Test objectives → Execution → Evidence → Deployment validation → Finding closure hoặc residual-risk decision.**

> **Một patch đã được cài không chứng minh lỗ hổng đã được khắc phục. Một security scanner không còn cảnh báo cũng không chứng minh mọi đường khai thác bị loại bỏ.**

### 1.1. Ví dụ trực quan

Giả sử Orders API cho người dùng A đọc nhầm đơn hàng của tenant B. Engineering sửa repository query để thêm tenant filter.

Các tình huống có thể xảy ra:

- Unit test cho service PASS, nhưng API export vẫn đọc toàn bộ tenant.
- Endpoint GET đã sửa, nhưng Redis cache trả response B mà không kiểm tra quyền.
- Staging đã triển khai build mới, production vẫn chạy image digest cũ.
- Database migration sửa RLS nhưng worker sử dụng DB role có quyền bypass.
- Patch ngăn rò dữ liệu nhưng làm user hợp lệ bị từ chối.
- Canary không báo lỗi HTTP nhưng latency tăng và queue backlog vượt mục tiêu.

Một patch test plan tốt phát hiện những khả năng này **trước khi xác nhận remediation thành công**.

### 1.2. Kiểm thử bản vá nhằm phục vụ quyết định gì?

| Quyết định | Điều cần chứng minh |
| --- | --- |
| **Merge code** | Fix logic phù hợp requirement, unit/security tests và review đạt |
| **Tạo release artifact** | Dependency, toolchain, provenance và security checks phù hợp |
| **Triển khai staging** | Artifact có thể khởi động, tương thích và test được trên cấu hình đại diện |
| **Bắt đầu canary** | Rủi ro và rollback plan được phê duyệt, monitoring sẵn sàng |
| **Mở rộng rollout** | Canary behavior và metrics đáp ứng acceptance criteria |
| **Đóng finding** | Fix/mitigation được xác minh trên artifact và phạm vi cần thiết |
| **Chấp nhận rủi ro** | Có căn cứ, đúng thẩm quyền, thời hạn và controls bù trừ |

Một báo cáo “build green” chỉ là một mẩu evidence cho một hoặc nhiều bước, không tự thay cho toàn bộ quyết định.

## 2. Phân biệt patch testing với những hoạt động liên quan

| Hoạt động | Mục đích | Chưa đủ để kết luận |
| --- | --- | --- |
| **Patch identification** | Xác định vendor advisory và bản sửa có thể áp dụng | Không biết patch có tương thích |
| **Patch assessment** | Đánh giá rủi ro, tính áp dụng, ưu tiên và chiến lược | Chưa có evidence thực thi |
| **Patch development** | Tạo code/config/artifact sửa lỗi | Chưa chứng minh lỗi hết |
| **Patch testing** | Kiểm tra fix và regression trong scope xác định | Chưa chắc production đã nhận patch |
| **Patch deployment** | Đưa artifact/config mới tới môi trường | Chưa chứng minh control hiệu quả |
| **Deployment verification** | Kiểm tra runtime versions, digests và behavior | Có thể chưa bao phủ mọi edge case |
| **Vulnerability scanning** | Tìm dấu hiệu lỗ hổng theo coverage/rules | Không thể tự xác nhận mọi logic bug |
| **Penetration testing** | Đánh giá các kịch bản khai thác có phép | Là point-in-time, không bao trùm mọi path |
| **Risk acceptance** | Quyết định quản lý residual risk | Không biến lỗi tồn tại thành fixed |

### 2.1. Patch presence khác patch effectiveness

Ví dụ Linux distribution có thể **backport security fix** vào package với version string không giống upstream version được nêu trong advisory. Chỉ dựa vào số version để báo “unpatched” hoặc “patched” đều có thể sai.

Cần kết hợp:

- Vendor advisory và mapping tới distribution/release đang dùng.
- Package build metadata, changelog hoặc security notice đáng tin.
- Version/digest của artifact thực tế.
- Kiểm tra hành vi bảo mật trong điều kiện được phép.
- Các mitigations và assumptions còn lại.

Ngược lại, chỉ tăng version dependency nhưng code thực tế vẫn gọi API không an toàn thì **không đáp ứng mục tiêu bảo mật**.

### 2.2. Functional smoke test khác security regression test

Smoke test có thể kiểm tra:

- Service khởi động và health endpoint phản hồi.
- Một user hợp lệ tạo đơn hàng thành công.

Security regression cần kiểm tra:

- User A không đọc order B.
- Caller thiếu quyền không được thực hiện refund.
- Input lỗi không vượt validation boundary.
- Token đã revoke không được dùng theo policy.
- Webhook giả hoặc replay không gây side effect.
- Logs không chứa raw token hay dữ liệu nhạy cảm.

Cả hai đều cần, vì một patch có thể **vá lỗ hổng nhưng phá chức năng**, hoặc giữ chức năng nhưng **vẫn còn bypass**.

## 3. Mục tiêu bảo mật của quá trình kiểm thử patch

Những security claims tiêu biểu:

- **PATCH-OBJ-01:** artifact/config dự kiến áp vào hệ thống đúng là bản đã được phê duyệt.
- **PATCH-OBJ-02:** kịch bản vulnerability gốc không còn xảy ra trong phạm vi kiểm tra.
- **PATCH-OBJ-03:** các bypass/variant paths có liên quan cũng được kiểm tra.
- **PATCH-OBJ-04:** những security controls không liên quan trực tiếp nhưng phụ thuộc patch vẫn hoạt động.
- **PATCH-OBJ-05:** chức năng nghiệp vụ quan trọng, dữ liệu và integrations tương thích.
- **PATCH-OBJ-06:** hệ thống duy trì availability, observability và recovery mục tiêu.
- **PATCH-OBJ-07:** rollout không làm mất hoặc vô hiệu evidence/audit.
- **PATCH-OBJ-08:** rollback/roll-forward không vô tình đưa rủi ro nghiêm trọng quay lại.
- **PATCH-OBJ-09:** kết quả test có thể liên kết tới finding, code, artifact, environment và deployed version.
- **PATCH-OBJ-10:** khi một test không thể thực hiện, trạng thái **INSUFFICIENT_EVIDENCE/BLOCKED** được xử lý minh bạch.

### 3.1. Security requirements có thể kiểm chứng

**PATCH-REQ-01 — Fix verification**

> Trước khi đóng một vulnerability finding, nhóm chịu trách nhiệm phải cung cấp bằng chứng cho thấy bản vá xử lý được điều kiện lỗi đã xác nhận, trong phạm vi asset/version liên quan, bằng phương pháp kiểm tra phù hợp với security requirement.

**PATCH-REQ-02 — Security regression**

> Các security invariants liên quan tới thay đổi phải có kiểm thử âm và dương, bao gồm đường đi khác hoặc fail-safe behavior đã được threat model xác định khi áp dụng.

**PATCH-REQ-03 — Artifact identity**

> Release/deployment phải sử dụng artifact có định danh đối chiếu được với build và security test results đã được phê duyệt; sự không khớp phải tạo blocker hoặc quyết định có thẩm quyền.

**PATCH-REQ-04 — Compatibility**

> Patch không được gây sai lệch ngoài giới hạn chấp nhận đã phê duyệt đối với các chức năng, data contracts và service objectives thiết yếu.

**PATCH-REQ-05 — Rollout verification**

> Trước khi tăng tỷ lệ canary hoặc hoàn tất deployment, team phải kiểm tra tiêu chí health, error, latency, security events và các business invariants liên quan trong thời gian quan sát đã định.

**PATCH-REQ-06 — Emergency exception**

> Việc rút gọn test trong emergency change phải có scope, người có thẩm quyền, risk rationale, các checks không thể bỏ và kế hoạch bổ sung evidence sau rollout.

Các ngưỡng, kỳ review, deadline hoặc SLA cụ thể phải được lấy từ **risk appetite, policy và nghĩa vụ áp dụng** của tổ chức, không tự đặt thành quy tắc phổ quát.

## 4. Các loại patch và đặc điểm kiểm thử

| Loại patch | Vấn đề thường gặp | Kiểm thử ưu tiên |
| --- | --- | --- |
| **Application security fix** | Authorization, injection, SSRF, unsafe state transition | Reproduction/regression theo security invariant, API/business tests |
| **Direct/transitive dependency upgrade** | API/ABI breaking, CVE hoặc malicious dependency | SCA, artifact inventory, unit/integration, provenance |
| **OS/package update** | Service restart, library ABI, file permission, reboot | Package verification, service health, OS config, integration |
| **Kernel/hypervisor update** | Reboot, driver/virtualization changes | Boot, workload health, runtime isolation, performance |
| **Container base image refresh** | Runtime binaries/user/certificates thay đổi | Image scan, signature/digest, entrypoint, runtime tests |
| **Kubernetes component update** | API deprecation, admission/RBAC/network behavior | Cluster health, workload rollout, policy tests |
| **Network/WAF/IAM patch** | Rule thay đổi, overblocking/fail-open | Negative/positive access tests và effective config |
| **Database engine/schema patch** | Migration, locks, replication, compatibility | Schema/data integrity, downgrade/restore, load |
| **Cryptography/TLS update** | Handshake, trust chain, certificate và key formats | Protocol/identity validation, compatibility và fallback rejection |
| **Secret rotation/credential response** | Consumers giữ token cũ, service downtime | Credential revoke, new credential success, old rejected |
| **CI/CD plugin/build tool patch** | Build behavior, runner permissions, artifact identity | Clean build, locked graph, provenance, negative source/integrity tests |
| **Managed service update** | Thay đổi do vendor thực hiện | Vendor change evidence, consumer contracts, runtime checks |

**Một patch có thể tác động đồng thời nhiều lớp.** Ví dụ nâng Spring Boot runtime vừa đổi dependency graph, servlet behavior, TLS stack và actuator configuration; không nên chỉ chạy SCA mà bỏ qua API authorization và deployment settings.

## 5. Xác định phạm vi và risk tier trước khi test

### 5.1. Các câu hỏi đầu vào

1. **Tại sao patch được đề xuất?** CVE, pentest, incident, proactive hardening hay lỗi chức năng?
2. **Điểm yếu gốc là gì?** Exploit precondition, attacker capability và impact?
3. **Patch sẽ thay gì?** Code path, dependency, IAM, DB schema, host OS, image hoặc policy?
4. **Tài sản nào bị ảnh hưởng?** Production/staging, tenants, regions, shared services và clients?
5. **Service criticality và data classification?**
6. **Có bằng chứng khai thác thực tế hoặc suspected compromise?**
7. **Rủi ro nếu chậm patch?** Exposure hiện tại và compensating controls?
8. **Rủi ro nếu deploy patch lỗi?** Outage, mất dữ liệu, schema incompatibility, security regression?
9. **Cần kiểm thử ở environment nào?** Có thể kiểm tra an toàn những gì?
10. **Ai quyết định release, exception và rollback?**

### 5.2. Phân loại chiều sâu kiểm thử theo rủi ro

| Tình huống | Cách tiếp cận |
| --- | --- |
| Thay một thư viện ít ảnh hưởng, không có public exposure | Unit/integration + dependency verification + tests theo phạm vi |
| Fix BOLA trên public API chứa PII | Authorization matrix, data-layer tests, alternate paths, audit, rollout gates |
| Patch kernel trên cluster production | Canary nodes, compatibility/drivers, workload health, reboot/capacity plan |
| Patch DB schema với dữ liệu lớn | Migration rehearsal, backup/restore, dual-version compatibility, data checks |
| Patch CI plugin có signing rights | Build-time isolation, source/provenance, artifact integrity, pipeline permissions |
| Emergency patch cho exploit đang hoạt động | Containment ngay, minimal critical tests, progressive rollout, tăng monitoring |
| Managed platform tự áp security update | Vendor evidence + tests ở consumer boundary + post-change monitoring |

Độ sâu không chỉ phụ thuộc số dòng diff. **Một thay đổi một dòng trong authorization filter có thể có rủi ro lớn hơn hàng trăm dòng UI.**

### 5.3. Phân biệt rủi ro của lỗ hổng và rủi ro của thay đổi

Trong patch management có **hai risk dimensions**:

- **Vulnerability exposure risk nếu không patch**.
- **Change/operational risk nếu patch gây lỗi**.

Một emergency patch có thể mang change risk lớn nhưng vẫn cần triển khai nhanh nếu rủi ro khai thác đang diễn ra cao hơn. Quyết định phải kèm containment, gates và rollback/forward-fix plan, không phải chỉ nói “quá gấp để test”.

## 6. Preflight: tạo baseline đáng tin trước khi vá

### 6.1. Xác minh inventory và target versions

Ghi:

- Affected asset, service và owner.
- Package/product name, version hiện tại, source/advisory.
- CVE/CWE/finding ID nếu có.
- Current artifact digest và deployment revision.
- Target patched version/build/config revision.
- Changelog, compatibility notes và required dependencies.
- OS/architecture, runtime versions và migration prerequisites.
- Environments, tenants và rollout order.
- Effective controls đang giảm exposure.
- Restore/backup readiness và rollback constraints.
- Security requirements và acceptance criteria.

Nếu không xác định được **current state**, khó chứng minh thay đổi đã đưa hệ thống tới target state.

### 6.2. Đọc advisory một cách có phân biệt

Một vendor advisory thường cung cấp affected versions, fixed versions, preconditions, mitigations và change notes. Nhưng cần:

- Xác nhận advisory **áp dụng đúng product/release/distribution**.
- Xem fixed version và backported fixes nếu vendor dùng backport.
- Phân biệt package upstream và package do OS vendor duy trì.
- Xem patch có yêu cầu restart/reboot/migration không.
- Xem tính tương thích của configs và deprecated APIs.
- Đánh giá package integrity/provenance và trusted source.
- Ghi nguồn, phiên bản và thời điểm review advisory.

Không tự suy từ “version trông cũ” rằng patch chưa áp khi vendor có backport; ngược lại, không tin chỉ vì package manager báo update thành công.

### 6.3. Baseline chức năng và hiệu năng

Trước patch, thu các chỉ số nền thích hợp:

- Error rates, latency P95/P99, throughput và saturation.
- Tỷ lệ giao dịch business thành công.
- Queue backlog, retry và dead-letter behavior.
- Database connections, locks, replication lag.
- Memory/CPU, restart count và pod health.
- Audit event delivery, detection signals và logging completeness.
- Phiên bản artifact/image và effective configuration.
- Known existing functional defects và limitations.

Nếu chỉ quan sát sau patch mà không có baseline hoặc expected ranges, khó tách lỗi mới và lỗi tồn tại trước đó.

### 6.4. Pre-patch snapshot và khôi phục

Backup/snapshot hỗ trợ recovery, nhưng cần xác minh:

- Có đúng dữ liệu và cấu hình cần khôi phục?
- Backup đã được kiểm tra restore theo chính sách?
- Có tách quyền và chống sửa/xóa bởi cùng credential?
- Có ràng buộc retention, secret/revocation state và tenant isolation?
- Có biện pháp xử lý sự kiện phát sinh trong lúc rollout không?

**Có snapshot không đồng nghĩa rollback an toàn**, đặc biệt với database migration hoặc external side effects.

## 7. Thiết kế patch test plan

### 7.1. Mẫu một patch test case

Mỗi test case nên ghi:

- Test ID và patch/change ID.
- Security requirement, vulnerability/finding/threat ID liên quan.
- Asset, environment, version/build/digest, configuration.
- Precondition, principal, permissions và test fixture.
- Action và trust boundary cần kiểm tra.
- Expected result rõ ràng.
- Actual result và evidence reference.
- Test runner/tool version, timestamp, reviewer.
- Severity khi FAIL, status PASS/FAIL/BLOCKED/NOT_RUN.
- Limitations, excluded paths và dependencies.

Một câu “Kiểm tra chức năng hoạt động bình thường” không có **oracle** đủ rõ để reviewer độc lập xác minh.

### 7.2. Ma trận kiểm thử theo lớp

| Lớp | Mục đích | Ví dụ evidence |
| --- | --- | --- |
| **Static/diff review** | Xác định thay đổi và các đường code bị ảnh hưởng | Code review, change set, SAST |
| **Unit security tests** | Kiểm tra logic và negative cases nhỏ | JUnit results, assertions |
| **Integration tests** | Kiểm tra DB/IAM/cache/queue thực hoặc tương đương | Test run, config, fixture |
| **API/contract tests** | Kiểm tra callers và compatibility | OpenAPI/consumer test results |
| **End-to-end tests** | Kiểm tra business flow xuyên thành phần | E2E trace, state assertions |
| **Vulnerability verification** | Xác nhận điều kiện lỗi đã bị xử lý | Controlled regression, scan, vendor fix mapping |
| **Infrastructure/config tests** | Kiểm tra policy và runtime boundaries | IaC/effective IAM/network evidence |
| **Performance/resilience tests** | Phát hiện latency, resource, retry và failure changes | Baseline comparison |
| **Deployment/canary tests** | Đánh giá khả năng rollout ở môi trường đích | Deployment digest, metrics, alert |
| **Recovery tests** | Kiểm chứng backup/restore hoặc forward-fix | Restore exercise, reconciliation |
| **Operating verification** | Xác nhận control tồn tại và hoạt động sau rollout | Runtime audit, version inventory, retest |

Một patch không nhất thiết cần mọi phép thử với cùng độ sâu. Phải giải thích lựa chọn và **rủi ro chưa được kiểm thử**.

### 7.3. Test positive, negative, boundary, failure và bypass

Một security regression suite cần:

- **Positive:** hành động đúng quyền vẫn hoạt động.
- **Negative:** thao tác trái quyền hoặc input nguy hiểm bị chặn.
- **Boundary:** token gần hết hạn, kích thước file, số lượng record, tenant boundary.
- **Failure:** dependency timeout, retry, partial commit, missing policy/identity.
- **Bypass:** endpoint phụ, bulk/export, worker, cache, search, direct service route.
- **Concurrency:** two writers, duplicate events, TOCTOU nếu liên quan.
- **Rollback/upgrade skew:** clients hoặc workers cũ tương tác với service mới.

Test chỉ gồm negative cases có thể PASS khi ứng dụng từ chối tất cả request. Ngược lại, positive tests không thể phát hiện nhiều lỗi authorization.

## 8. Kiểm thử hiệu quả bản vá đối với lỗ hổng gốc

### 8.1. Xuất phát từ điều kiện khai thác, không chỉ tên CVE

Một vulnerability record nên có:

- Root cause hoặc class lỗi.
- Input/actor/resource tạo ra failure.
- Precondition và affected boundary.
- Expected secure behavior.
- Actual insecure behavior trước fix, nếu có bằng chứng hợp lệ.
- Patch change và control mới.
- Test oracle cho fix.
- Các bypass variants đáng kể.

Đối với lỗi có thể gây hại, **không bắt buộc tái hiện exploit nguy hiểm trên production**. Sử dụng fixture, sandbox, mock service hoặc controlled lab trong phạm vi được phép.

### 8.2. Ví dụ: BOLA/IDOR

**Finding:** user tenant A đọc order tenant B bằng cách thay order ID.

**Yêu cầu:** mọi request đọc order phải dùng principal và tenant context đã xác minh để kiểm tra quyền trên object.

| Test ID | Principal | Resource | Expected |
| --- | --- | --- | --- |
| PATCH-AUTHZ-01 | A, tenant A | Order A | Allow, đúng dữ liệu |
| PATCH-AUTHZ-02 | A, tenant A | Order B của tenant B | Deny/no disclosure |
| PATCH-AUTHZ-03 | Không xác thực | Order A | Unauthorized |
| PATCH-AUTHZ-04 | A tự gửi tenant B header | Order B | Không mở rộng quyền |
| PATCH-AUTHZ-05 | A gọi bulk export chứa B | Mixed orders | Không phát dữ liệu B |
| PATCH-AUTHZ-06 | A truy vấn qua search/cache | Order B | Không nhận dữ liệu B |
| PATCH-AUTHZ-07 | Worker nhận context bị giả | Order B | Deny/quarantine |
| PATCH-AUTHZ-08 | A đã bị thu hồi membership | Order A | Deny theo revocation policy |

Đọc order A thành công không chứng minh order B bị chặn; cả hai vế đều cần.

### 8.3. Ví dụ: injection

Nếu patch nhằm xử lý injection trong search endpoint:

- Review query construction và parameter binding.
- Test input hợp lệ và input có ký tự điều khiển/cấu trúc đặc biệt trong lab.
- Kiểm tra query semantics không thay đổi trái ý định.
- Kiểm tra error handling không lộ data hoặc stack trace.
- Xác nhận các nơi khác sử dụng cùng query helper.
- Theo dõi query performance và indexes sau fix.

Không nên tự chọn payload có thể gây phá hủy dữ liệu, hoặc chạy thử exploit trên production khi chưa có ủy quyền và giới hạn tác động.

### 8.4. Ví dụ: authentication/session

Nếu patch thay token validation:

- Token hợp lệ đúng issuer/audience vẫn được chấp nhận.
- Token sai signature, audience, expiry hoặc malformed bị từ chối.
- Không có algorithm confusion hoặc insecure fallback.
- Token revoke được xử lý đúng policy.
- Clock skew và key rotation được kiểm tra.
- Auth failure audit không làm lộ token.
- Downstream services không tin header tự khai bỏ qua gateway.

### 8.5. Ví dụ: dependency CVE

Nếu nâng một dependency để vá CVE:

1. Xác định artifact/version đang chạy.
2. Kiểm tra patched version theo đúng vendor/package ecosystem.
3. Đối chiếu resolved direct/transitive graph và lockfiles.
4. Đánh giá vulnerable code path còn reachable hay không.
5. Xem advisory/backport nếu version string không trực quan.
6. Chạy SCA và test phù hợp vulnerability class.
7. Kiểm tra hành vi của ứng dụng sau upgrade.
8. Đối chiếu image deployed digest với image đã test.

**Scanner hết cảnh báo** có thể do đổi rule database hoặc mất coverage; **scanner vẫn báo** có thể do version mapping/backport. Cần triage bằng chứng và phương pháp.

### 8.6. Ví dụ: misconfiguration/IAM

Nếu patch sửa quyền IAM hoặc network:

- Actor được phép vẫn thực hiện action hợp lệ.
- Actor trái quyền bị từ chối ở **effective runtime policy**.
- Không có role phụ, inherited policy hoặc bypass path.
- Audit ghi denial/success theo quy định.
- Khi policy service lỗi, hệ thống không tự fail-open.
- Recovery/admin procedure vẫn hoạt động trong scope.
- Deployment không làm quyền rộng trở lại sau controller reconcile.

## 9. Functional và compatibility regression

### 9.1. Các nhóm tương thích

- **API contracts:** fields, status codes, backward compatibility, pagination.
- **Protocol:** HTTP/TLS, gRPC, messaging schema, webhook format.
- **Binary/API/ABI:** Java method signatures, native libraries, drivers.
- **Data:** schema, serialization, field defaults và historical records.
- **Client versions:** browser/mobile/SDK cũ tương tác service mới.
- **Database:** migration, driver, pool behavior, transaction semantics.
- **Infrastructure:** container runtime, host OS, kernel, CNI, admission.
- **Security config:** default security headers, CORS, CSRF, session policy.
- **Observability:** logs, metrics, traces, correlation IDs.
- **Operations:** backup, restore, scheduled jobs, cron và monitoring agents.

Một patch security library có thể làm sai chức năng hợp lệ nếu consumer dùng API đã bị thay hoặc mặc định cũ.

### 9.2. Contract tests

Ví dụ Orders API sau patch authorization:

- GET order hợp lệ vẫn trả schema được công bố.
- Error response không lộ dữ liệu/chi tiết nhạy cảm.
- Bulk export giữ format và scope theo contract.
- Webhook contract giữ chữ ký/format đúng.
- User cũ với token hợp lệ không bị logout ngoài policy.
- Client cũ không vô tình vượt qua security boundary do fallback.

Nếu patch thay đổi intentional security behavior, có thể cần cập nhật API contract và communicating consumers; không coi mọi thay đổi security-related status code là regression sai.

### 9.3. Business invariant regression

Với refund:

- Tổng refund không vượt số tiền được phép.
- Permission và approval được kiểm tra mỗi lần.
- Duplicate retry không tạo payment lần hai.
- Transaction thất bại không tạo inconsistent ledger.
- Audit ghi actor, order, outcome.
- Concurrent requests không vượt invariant.

Một test “API trả 200” không đủ nếu side effect tài chính xảy ra hai lần.

### 9.4. Dependency graph và supply-chain regressions

Sau patch:

- Có dependency mới chưa được review không?
- Lockfile diff có phù hợp patch plan?
- Artifact provenance và checksum đã được xác minh?
- Build plugins hoặc CI actions có đổi theo upgrade?
- Package có install scripts mới hoặc yêu cầu quyền thêm?
- Có CVE mới hoặc vulnerable transitive package bị đưa vào?
- License/contract và runtime platform compatibility có thay đổi?
- SBOM phản ánh artifact cuối?

Một security patch không nên vô tình tạo đường supply-chain rủi ro khác mà không được đánh giá.

## 10. Testing data migration và database patches

### 10.1. Vì sao database patch khó rollback?

Thay đổi DB có thể:

- Đổi kiểu dữ liệu hoặc constraints.
- Rebuild indexes và khóa bảng.
- Chuyển giá trị hoặc format encryption.
- Thay access policy, triggers hoặc stored procedures.
- Thêm/đổi RLS.
- Gây replication lag.
- Làm app cũ và mới không còn tương thích.
- Tạo external side effects không thể đảo ngược khi rollback image.

Do đó rollback code **không đồng nghĩa rollback dữ liệu**.

### 10.2. Expand–migrate–contract

Một chiến lược thường dùng:

1. **Expand:** thêm schema tương thích với cả app cũ và mới.
2. **Migrate/backfill:** chuyển dữ liệu theo batch có audit/checkpoint.
3. **Validate:** đối chiếu record count, integrity, constraints, business invariants.
4. **Switch:** chuyển readers/writers theo kế hoạch.
5. **Observe:** theo dõi errors, locks, latency và replication.
6. **Contract:** loại bỏ schema cũ khi không còn consumer, theo approval.

Không phải migration nào cũng hỗ trợ chiến lược này; cần chọn theo database engine và change.

### 10.3. Migration test matrix

| Test | Expected |
| --- | --- |
| Schema migration trên bản dữ liệu đại diện | Hoàn tất trong giới hạn phê duyệt |
| Tải dữ liệu cũ với app mới | Không mất/đọc sai dữ liệu |
| App cũ cùng hoạt động trong rollout | Tương thích theo kế hoạch |
| Rollback app khi schema đã expand | Không gây crash hoặc corrupt data |
| Data backfill bị dừng giữa chừng | Resume/idempotent hoặc restore theo thiết kế |
| RLS/permission sau migration | Tenant A không đọc tenant B |
| Constraint/unique index | Không tạo duplicate illegal state |
| Encryption/key rotation transition | Không làm mất khả năng giải mã dữ liệu hợp lệ |
| Replication failover | Không mất integrity hoặc vượt RPO |
| Restore exercise | Dữ liệu và security controls phục hồi theo policy |

### 10.4. Data integrity assertions

Không chỉ dựa vào tổng số records:

- Compare hashes/checksums theo phương pháp phù hợp.
- Kiểm tra nullability, referential integrity và encoding.
- So sánh totals theo business dimensions.
- Kiểm tra tenant ownership và permissions.
- Đối chiếu các giao dịch liên kết với external provider.
- Kiểm tra dữ liệu historical/edge cases.
- Lưu kết quả đối chiếu đã được bảo vệ.

Nếu phải dùng dữ liệu gần production để mô phỏng, cần masking, approval, data minimization và cách bảo vệ phù hợp. Ưu tiên synthetic fixtures.

## 11. Kiểm thử OS/kernel, firmware và hạ tầng

### 11.1. OS/package patch

Các kiểm tra có thể gồm:

- Installed package/version/build metadata có khớp vendor fix.
- Service startup và dependencies sau package upgrade.
- Configuration file bị reset/merge ngoài dự kiến không.
- File owner/permissions và systemd service user.
- TLS trust store/certificates và crypto policy.
- Audit/EDR/monitoring agent có hoạt động.
- Scheduled jobs, log rotation và backup client.
- Disk space, reboot requirement và boot behavior.
- Runtime application compatibility và host connectivity.

Không tự coi “package update command trả exit code 0” là patch verified.

### 11.2. Kernel và hypervisor

Một kernel patch có thể cần reboot hoặc rolling node replacement.

Kiểm thử:

- Kernel version thực chạy sau reboot, không chỉ installed package.
- Boot thành công với kernel/cấu hình dự định.
- Driver/network/filesystem/virtualization compatibility.
- Container runtime, node agent, network policy enforcement.
- Security modules/hardening có còn bật.
- CPU/memory/IO/performance baseline.
- Pod eviction, rescheduling và capacity headroom.
- Node recovery và rollback/rescue procedure.

Cần lưu ý **kernel installed version ≠ running kernel version** cho đến khi thực sự boot phiên bản mới.

### 11.3. Network appliance và firmware

- Firmware identity và vendor patch applicability.
- Backup config/restore procedure.
- HA failover, routing, NAT, DNS và firewall rules.
- Management plane access.
- Protocol/TLS compatibility.
- Throughput/latency và session persistence.
- Rollback/recovery theo vendor limitations.
- Audit logging và security policy effective state.

Không chạy kiểm thử phá hoại hoặc gây outage trên thiết bị production ngoài phạm vi được phê duyệt.

### 11.4. Managed service

Với patch do cloud provider thực hiện, tổ chức có thể không quản lý bytes của underlying host. Vẫn cần:

- Vendor change notification và maintenance scope.
- Effective service version/configuration.
- Consumer contract tests.
- Network/IAM/data security checks.
- Error, latency, failover và recovery monitoring.
- Căn cứ về phần trách nhiệm thuộc provider và phần thuộc customer.

Không yêu cầu bằng chứng không thể lấy từ provider rồi mặc định FAIL; thay vào đó ghi **shared responsibility, evidence limitations và compensating checks**.

## 12. Container và Kubernetes patch testing

### 12.1. Build mới không có nghĩa deploy mới

Khi vá container image, phải kiểm tra:

- Source commit và dependency lockfile.
- Base image digest và security fixes.
- Image scan/SBOM và provenance/signature policy.
- Built image digest.
- Deployment manifest thực trỏ đúng digest.
- Pods/runtime thực chạy đúng image identity.
- SecurityContext, service account và NetworkPolicy không drift.
- Sidecar/agent và init container cũng được cập nhật khi thuộc scope.

Một tag có thể bị retarget; **digest** giúp liên kết build, scan và deployment.

### 12.2. Kubernetes rollout

Các yếu tố cần xét:

- Readiness/liveness/startup probes và semantics đúng.
- RollingUpdate maxSurge/maxUnavailable phù hợp capacity.
- PodDisruptionBudget có thực thi ý định availability không.
- Node scheduling/affinity/taints và resource quotas.
- Session affinity, long-running connections và graceful termination.
- Migration/worker compatibility khi nhiều phiên bản cùng tồn tại.
- DaemonSet/sidecar updates và version skew.
- RBAC/admission policy và network enforcement.
- Rollback commands hoặc GitOps reconciliation behavior.
- Audit/metrics để phát hiện failed rollout.

**Pod Ready chưa chứng minh security fix hiệu quả**. Readiness chỉ phản ánh những gì probe kiểm tra.

### 12.3. Ví dụ manifest minh họa

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
spec:
  replicas: 3
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app: orders-api
  template:
    metadata:
      labels:
        app: orders-api
    spec:
      containers:
        - name: orders-api
          # Dùng image digest thật được phê duyệt, không dùng placeholder khi triển khai.
          image: registry.example.org/orders-api:patched-release
          ports:
            - containerPort: 8080
          readinessProbe:
            httpGet:
              path: /ready
              port: 8080
            initialDelaySeconds: 5
            periodSeconds: 5
~~~

Manifest là **mẫu** và chưa đủ control (secret, securityContext, resource limits, policy…). Dùng tag trong ví dụ để dễ đọc; môi trường cần digest pinning thì phải thay bằng **verified digest** theo policy. Không copy mẫu thành cấu hình production mà bỏ review.

### 12.4. Verify image identity

Một quy trình kiểm tra bằng chứng có thể:

1. Lấy digest từ trusted build/promotion record.
2. Đối chiếu digest trong release approval.
3. Quan sát imageID/digest thực tế trên pods.
4. Xác minh mọi replicas/regions thuộc phạm vi đã chuyển đổi.
5. Xác minh old vulnerable replicas không còn phục vụ traffic ngoài chủ đích.
6. Kiểm tra sidecars và scheduled jobs nếu liên quan.
7. Chạy security regression test qua ingress/runtime thực.
8. Lưu report về coverage và những nodes/regions chưa cập nhật.

Với rollout từng phần, phải ghi **which pods/regions/tenants still vulnerable** để không báo complete quá sớm.

## 13. Phân tầng môi trường kiểm thử

### 13.1. Local/CI

Phù hợp với:

- Unit tests.
- SAST/SCA/dependency checks.
- Static policy checks.
- Build and artifact verification.
- Test fixtures và security invariants cục bộ.

Giới hạn: mocks có thể che lỗi tích hợp, auth provider/DB/queue không hoàn toàn giống runtime.

### 13.2. Integration

Phù hợp với:

- Database schema/RLS và connection pool.
- Redis cache scoping.
- API/authorization.
- Queue/worker/data export.
- Webhook signature/idempotency.
- Secret manager và IAM negative tests trong sandbox.

Cần test data giả và isolation phù hợp.

### 13.3. Staging/pre-production

Phù hợp với:

- End-to-end flows.
- Feature flags và routing.
- Production-like TLS/identity/network config.
- Load/resilience tests có giới hạn.
- Deployment, canary và recovery rehearsals.
- Monitoring/alert pipelines.

**Staging parity phải được đánh giá**, không mặc định tương đương production. Nếu staging dùng IdP khác, DB role khác hoặc không có WAF, evidence cần ghi giới hạn.

### 13.4. Production verification

Chỉ chạy phép thử được phê duyệt, tránh destructive probes. Có thể gồm:

- Version/image digest/config confirmation.
- Safe negative tests với synthetic identities/data.
- Health, audit, metrics và traces.
- Canary business metrics/latency/error.
- Effective IAM/network policies.
- Detection signal simulation đã đánh giá tác động.
- Rollout completeness.

Không dùng dữ liệu khách hàng hoặc exploit payload nguy hiểm khi chưa có ủy quyền, controls và đánh giá ảnh hưởng.

### 13.5. Môi trường có tính đại diện

Đánh giá những khác biệt:

| Thành phần | Cần so sánh |
| --- | --- |
| Identity provider | Issuer, audience, MFA/session/revoke semantics |
| Authorization | Policy version, tenant membership, DB role |
| Data stores | Engine/version, indexes, RLS, connection pool |
| Network | Gateway, WAF, ingress/egress, DNS, mTLS |
| Workloads | Replicas, CPU/memory, autoscaling, sidecars |
| Secrets | Distribution path, scopes, rotation behavior |
| Traffic | Volumes, concurrency, edge cases |
| External integrations | Test doubles vs provider contracts |
| CI/CD | Artifact identity và deployment pipeline |
| Monitoring | Metrics, alert, audit, data masking |

Một negative test ở staging có thể PASS vì firewall cấu hình khác, chứ không chứng minh authorization trong production.

## 14. Case study: Patch lỗi BOLA của Orders API

### 14.1. Kiến trúc giả định

Một nền tảng SaaS nhiều tenant gồm:

- Browser/mobile clients.
- API gateway và identity provider.
- Orders API viết bằng Java/Spring Boot.
- PostgreSQL với tenant_id.
- Redis cache.
- Event bus và report worker.
- Private export storage.
- Audit pipeline và observability.

**Finding:** user tenant A có token hợp lệ nhưng thay order ID để xem dữ liệu tenant B.

**Impact:** tiết lộ dữ liệu khách hàng; quyền của user hợp lệ không được giới hạn theo resource.

**Patch:** xác minh tenant context server-side, tenant-scoped repository, authorization trên export và cache/worker paths liên quan.

### 14.2. DFD và trust boundaries

~~~mermaid
flowchart LR
    A["Client user A"] -->|"Token + order ID"| GW["API Gateway"]
    GW -->|"Verified principal"| API["Orders API"]
    API --> PDP["Authorization / Membership"]
    API --> DB[("PostgreSQL")]
    API --> CACHE[("Redis Cache")]
    API --> OUT[("Event Bus")]
    OUT --> WORKER["Report Worker"]
    WORKER --> STORE[("Private Export Storage")]
    API --> AUDIT[("Audit")]
    WORKER --> AUDIT
    B["Client user B"] --> GW
~~~

Ranh giới cần test:

- **TB-01:** client → API authentication.
- **TB-02:** principal → tenant/resource authorization.
- **TB-03:** API → database/cache với service privilege.
- **TB-04:** event → worker → export artifact.
- **TB-05:** app/worker → audit delivery.

### 14.3. Patch acceptance criteria

**PATCH-ORD-001 — Object-level authorization**

> Mọi thao tác đọc order phải xác minh principal có quyền đối với resource trong trusted tenant context; nếu không có quyền hoặc thiếu quyết định thì không được tiết lộ dữ liệu order.

**PATCH-ORD-002 — Cache isolation**

> Cached responses phải được phân vùng hoặc reauthorize theo tenant và permission context; không trả dữ liệu sai tenant.

**PATCH-ORD-003 — Worker authorization**

> Report worker phải giữ verified tenant/resource scope, không tin giá trị tenant tự khai hoặc message chưa được kiểm chứng.

**PATCH-ORD-004 — Safe error behavior**

> Authorization failure không tiết lộ object existence hoặc dữ liệu nhạy cảm vượt policy; audit ghi outcome theo schema đã phê duyệt.

**PATCH-ORD-005 — No business regression**

> Principal hợp lệ vẫn xem/export order trong quyền và các API contracts quan trọng không bị phá.

### 14.4. Test matrix

| ID | Kịch bản | Expected | Verification layer |
| --- | --- | --- | --- |
| T-ORD-01 | A GET order A | Success và đúng fields | API/integration |
| T-ORD-02 | A GET order B | Deny/no B content | API/integration |
| T-ORD-03 | A gửi header tenant B | Không tăng quyền | API/security chain |
| T-ORD-04 | Không có token | Deny | API |
| T-ORD-05 | A dùng search/bulk export chứa B | Không xuất B | E2E |
| T-ORD-06 | Cache warm bởi B | Không nhận B ở A | Redis integration |
| T-ORD-07 | Worker event giả tenant | Reject/quarantine | Queue/worker |
| T-ORD-08 | User A bị revoke membership | Deny theo policy | IdP/authz integration |
| T-ORD-09 | Authorization dependency timeout | Không fail-open | Fault injection |
| T-ORD-10 | Pod mới chạy patch digest | Digest trùng approved build | Deployment |
| T-ORD-11 | User A truy cập order A dưới load | Latency và success trong guardrail | Performance |
| T-ORD-12 | Audit từ denial và export | Event có actor/outcome, không PII thừa | Operating test |

### 14.5. Test strategy theo rủi ro

1. Viết regression test tái hiện failure trong lab với dữ liệu giả.
2. Implement fix ở service/resource boundary.
3. Unit tests cho logic và positive/negative access.
4. Integration tests với repository/database thực hoặc tương đương.
5. Kiểm tra cache, search, bulk/export, worker.
6. Chạy SAST/SCA/secret scan theo pipeline.
7. Deploy staging bằng immutable image.
8. Chạy API/E2E tests qua gateway đúng config.
9. Canary có monitoring security errors và business KPIs.
10. Verify mọi production replica đang chạy approved digest.
11. Retest trên đường runtime phù hợp và cập nhật finding.
12. Theo dõi residual risk/alternate paths còn chưa kiểm tra.

Đây là kế hoạch minh họa; **không có kết quả test thật trong bài**.

## 15. Java/Spring Boot: ví dụ patch và unit security test

### 15.1. Code trước patch: anti-pattern

~~~java
// KHONG AN TOAN NEU caller khong co resource-level authorization.
public OrderDto getOrder(UUID orderId) {
    return repository.findById(orderId)
            .map(OrderDto::from)
            .orElseThrow(ResourceNotFoundException::new);
}
~~~

Với service account có quyền đọc nhiều tenants, việc đoán UUID khó hay dễ không liên quan tới quyền truy cập.

### 15.2. Code sau patch: tenant-scoped query

Ví dụ rút gọn sử dụng Java records và interface:

~~~java
public record VerifiedPrincipal(
        String subjectId,
        UUID tenantId) {
}

public record Order(
        UUID id,
        UUID tenantId,
        String status) {
}

public record OrderDto(
        UUID id,
        String status) {
    public static OrderDto from(Order order) {
        return new OrderDto(order.id(), order.status());
    }
}

public interface OrderRepository {
    Optional<Order> findByIdAndTenantId(UUID id, UUID tenantId);
}

public final class ResourceNotFoundException
        extends RuntimeException {
}

@Service
public final class OrderQueryService {
    private final OrderRepository repository;

    public OrderQueryService(OrderRepository repository) {
        this.repository = repository;
    }

    public OrderDto getOrder(
            UUID orderId,
            VerifiedPrincipal caller) {
        // caller duoc xay dung boi trusted authentication/membership layer.
        Order order = repository
                .findByIdAndTenantId(orderId, caller.tenantId())
                .orElseThrow(ResourceNotFoundException::new);
        return OrderDto.from(order);
    }
}
~~~

Đây **không phải một implementation đầy đủ**:

- VerifiedPrincipal phải được xây từ identity đã xác minh.
- Tenant membership/permission phải được kiểm tra theo policy thật.
- Repository phải thực thi tenant filter; tên method không tự bảo đảm.
- Update/delete, export, worker và cache phải tuân control.
- DB role và RLS nếu có phải được kiểm tra.
- Audit và error behavior cần định nghĩa riêng.

### 15.3. Unit tests với JUnit 5 và Mockito

~~~java
@ExtendWith(MockitoExtension.class)
class OrderQueryServicePatchTest {
    @Mock
    OrderRepository repository;

    @InjectMocks
    OrderQueryService service;

    private final UUID tenantA = UUID.randomUUID();
    private final UUID orderId = UUID.randomUUID();

    @Test
    void authorizedTenant_stillCanReadOrder() {
        VerifiedPrincipal caller = new VerifiedPrincipal("user-a", tenantA);
        Order order = new Order(orderId, tenantA, "PAID");

        when(repository.findByIdAndTenantId(orderId, tenantA))
                .thenReturn(Optional.of(order));

        OrderDto dto = service.getOrder(orderId, caller);

        assertEquals(orderId, dto.id());
        assertEquals("PAID", dto.status());
        verify(repository).findByIdAndTenantId(orderId, tenantA);
    }

    @Test
    void crossTenantOrder_isNotReturned() {
        VerifiedPrincipal caller = new VerifiedPrincipal("user-a", tenantA);

        when(repository.findByIdAndTenantId(orderId, tenantA))
                .thenReturn(Optional.empty());

        assertThrows(
                ResourceNotFoundException.class,
                () -> service.getOrder(orderId, caller));

        verify(repository).findByIdAndTenantId(orderId, tenantA);
        verifyNoMoreInteractions(repository);
    }
}
~~~

Test trên chỉ kiểm tra **service interaction với mock repository**, không chứng minh actual SQL filter, token validation, DB RLS hoặc async/export paths.

Để đóng finding BOLA cần thêm test:

- API với token/principal fixture qua security chain.
- Database có orders A/B thực.
- Cache và worker end-to-end paths.
- Negative access sau revocation/timeout.
- Artifact deployed/version evidence.

### 15.4. Gherkin acceptance criteria

~~~gherkin
Feature: Orders API tenant isolation after security patch

  Scenario: Valid tenant can read its order
    Given user A has a valid session for tenant A
    And order A belongs to tenant A
    When user A requests order A
    Then only authorized order A data is returned

  Scenario: Cross-tenant access is denied
    Given user A has a valid session for tenant A
    And order B belongs to tenant B
    When user A requests order B by its identifier
    Then no content of order B is disclosed
    And the access decision follows the approved policy

  Scenario: Policy service unavailable
    Given user A is authenticated
    And the authorization decision cannot be obtained
    When user A requests an export of Confidential orders
    Then the system does not release an export artifact
~~~

Gherkin là **test specification**, không phải PASS evidence cho đến khi được thực thi và review.

## 16. Kiểm thử patch thư viện và dependency

### 16.1. Một dependency update có nhiều rủi ro

Nâng phiên bản thư viện có thể:

- Sửa vulnerability được công bố.
- Thay public API hoặc binary compatibility.
- Đổi transitive dependencies và plugin requirements.
- Thay TLS/certificate/serialization defaults.
- Đổi error semantics hoặc request handling.
- Tăng memory/CPU, latency hoặc package size.
- Thêm install/build scripts và supply-chain surface.

Security test plan phải xét **delta của dependency graph** chứ không chỉ direct version string.

### 16.2. Quy trình đánh giá upgrade

1. Xác định finding/CVE và affected package identity.
2. Xem fixed version theo vendor và distribution chính xác.
3. Tạo PR manifest/lockfile changes có review.
4. Kiểm tra package source, integrity/provenance và install scripts.
5. Tạo SBOM/graph của patched artifact.
6. Chạy SCA và security regression suite.
7. Chạy integration tests trên các sensitive code paths.
8. Kiểm tra config/default behavior và deprecated APIs.
9. Phát hành immutable artifact có digest/provenance.
10. Xác minh production thật dùng artifact này.
11. Retest finding và lưu residual risks.

### 16.3. Gradle Java: ví dụ tham chiếu

~~~kotlin
plugins {
    java
}

dependencyLocking {
    lockAllConfigurations()
}

repositories {
    mavenCentral()
}

dependencies {
    // Toa do va versions chi la gia dinh, khong phai packages that.
    implementation("org.example:orders-policy:2.1.0")
    testImplementation("org.example:test-support:1.4.0")
}
~~~

Ví dụ trên mô tả exact direct versions và yêu cầu locking; không chứng minh build đã resolve mọi configurations hoặc có dependency verification. Cần review **effective resolved graph**, CI lock consistency, Gradle Wrapper/plugin toolchain và integrity metadata theo policy.

### 16.4. SCA vẫn báo vulnerable sau patch

Có những nguyên nhân:

- Patch thật chưa deploy.
- Transitive dependency vẫn kéo vulnerable version.
- Scanner cache/database cũ.
- Package identity/version mapping sai.
- Vendor có backported fix với version string khác upstream.
- Binary còn nằm trong artifact dù code không gọi.
- Runtime image khác artifact đã scan.

Cần **triage có căn cứ**, không tự suppress alert chỉ để làm pipeline xanh.

### 16.5. Package version đổi nhưng vulnerability vẫn exploitable

Nếu lỗi nằm ở cách ứng dụng tích hợp thư viện, nâng version không đủ. Ví dụ:

- Client vẫn bỏ qua TLS hostname verification.
- API vẫn tự tin tenant header.
- Logging vẫn ghi raw access token.
- Deserializer vẫn được cấu hình với rủi ro.
- Endpoint vẫn expose dangerous operation ngoài quyền.

Test theo **security requirement**, không chỉ sự tồn tại của package fix.

## 17. Kiểm thử nonfunctional: performance và resilience

### 17.1. Performance regression

Một patch có thể bổ sung authorization lookup trên mọi request. Đây là cải thiện bảo mật nhưng có thể ảnh hưởng latency hoặc tạo bottleneck.

Những chỉ số cần xem:

- Latency P50/P95/P99 theo endpoint.
- Throughput tại representative load.
- CPU/memory per request.
- DB query count và connection pool saturation.
- Cache hit/miss và eviction.
- Queue processing delay và dead-letter.
- External dependency call rate.
- Error/timeout/retry count.
- Security event/audit pipeline overhead.

Không so sánh staging tải thấp với production tải cao một cách cơ học. Phương pháp, traffic model, data size và cửa sổ đo phải được ghi.

### 17.2. Resilience và fault injection

Những lỗi cần thử có giới hạn:

- Policy service slow/unavailable.
- Database reconnect.
- Cache miss/unavailable.
- Worker retry/duplicate event.
- Partial rollout với old/new service versions.
- Credential/key rotation.
- Node drain hoặc pod restart.
- Provider timeout.
- Audit ingestion backlog.

Mục tiêu là kiểm tra **security invariant trong điều kiện lỗi**. Nếu policy engine không trả quyết định, hệ thống xử lý ra sao? Có admin bypass không? Có event/log/alert hỗ trợ vận hành không?

### 17.3. Data plane và control plane

Một patch ở control plane như IAM hoặc admission webhook có thể làm ứng dụng hoạt động nhưng **mất khả năng triển khai, rotate secret hoặc ghi audit**.

Do đó test cần gồm:

- Workload/ops identities hợp lệ.
- Negative privileged access.
- GitOps/CI reconciliation.
- Monitoring và emergency access theo policy.
- Rollback/recovery decision authority.

### 17.4. Security vs availability trade-off

Nếu patch làm policy engine chậm:

- Không được tự tắt authorization để đạt latency.
- Có thể tối ưu cache policy decisions với TTL/invalidation phù hợp.
- Có thể tăng capacity hoặc thiết kế local policy evaluation.
- Nếu cần degraded mode, phải có approved risk decision.
- Retest fail-safe behavior sau thay đổi.

Mục tiêu là **đáp ứng cả security requirement và availability objective**, không mặc định một loại được bỏ qua.

## 18. Canary, blue-green và progressive delivery

### 18.1. Canary là gì?

**Canary rollout** triển khai patch tới một nhóm nhỏ workloads/traffic trước, quan sát kết quả rồi tăng dần phạm vi.

Canary giúp giảm blast radius của regression nhưng **không đảm bảo tự phát hiện security defect**, vì traffic canary có thể không chạm vulnerability path.

### 18.2. Blue-green là gì?

**Blue-green deployment** dùng hai environment tương đối độc lập để chuyển traffic từ phiên bản cũ sang mới, thuận lợi cho cutover/rollback nếu state/data compatibility cho phép.

Giới hạn:

- Database migration có thể không backward compatible.
- Queue/worker có thể xử lý hai schema cùng lúc.
- External payment calls không rollback được.
- Secret revoke hoặc key rotation có tác dụng một chiều.
- Old version chứa vulnerability có thể không được phép quay lại.

### 18.3. Guardrails trước khi tăng traffic

Một canary gate có thể xét:

| Nhóm guardrail | Ví dụ |
| --- | --- |
| **Artifact** | Canary dùng đúng approved digest/build |
| **Health** | Readiness, restart, saturation phù hợp |
| **Reliability** | Error/timeout rates so baseline, request success |
| **Latency** | P95/P99 theo endpoint và traffic class |
| **Business** | Order creation/refund/export success, no duplicate effects |
| **Security** | Negative authz test, no fail-open, policy/audit hoạt động |
| **Data integrity** | Không có cross-tenant rows hoặc migration inconsistency |
| **Observability** | Audit event delivery, alerts và traces đủ |
| **Capacity** | DB pool, queue backlog, rate/quota |
| **Rollback readiness** | Traffic switch, compatible schema, safe alternative |

Các ngưỡng phải được xác nhận từ SLO, risk, traffic và baseline; không dùng “0% lỗi” cứng trong mọi hệ thống.

### 18.4. Ví dụ rollout plan minh họa

~~~yaml
rollout:
  change_id: "PATCH-ORDERS-DEMO"
  strategy: "canary"
  target_artifact_digest: "NOT_VERIFIED"
  stages:
    - traffic_percent: 5
      observation_window: "ORG_POLICY_VALUE"
      gates:
        - "artifact-identity"
        - "security-negative-tests"
        - "http-error-rate"
        - "audit-delivery"
    - traffic_percent: 25
      observation_window: "ORG_POLICY_VALUE"
      gates:
        - "p95-and-p99-latency"
        - "business-invariant-checks"
        - "queue-and-database-health"
    - traffic_percent: 100
      observation_window: "ORG_POLICY_VALUE"
      gates:
        - "all-replicas-patched"
        - "production-runtime-verification"
        - "post-deploy-security-retest"
  stop_conditions:
    - "confirmed-security-regression"
    - "material-data-integrity-failure"
    - "unacceptable-operational-impact"
  on_stop: "execute-approved-containment-and-recovery-plan"
~~~

Đây chỉ là mẫu governance, không phải manifest dùng trực tiếp trong công cụ deployment.

### 18.5. Khi canary có rủi ro bảo mật riêng

Nếu bản cũ chứa vulnerability đang bị khai thác, việc giữ phần lớn traffic ở bản cũ quá lâu có thể nguy hiểm. Cần cân bằng:

- Urgency của security fix.
- Mức phơi lộ của old pods.
- Khả năng traffic steering và isolation.
- Testing trong staging.
- Monitoring và rollback/forward-fix.
- Khả năng triển khai đồng loạt nếu exploit active.

Canary không phải một thủ tục bắt buộc cho mọi trường hợp; **chọn chiến lược dựa trên threat và change risk**.

## 19. Rollback, roll-forward và recovery

### 19.1. Rollback có thể phục hồi chức năng nhưng tái tạo vulnerability

Trước khi rollback phải biết:

- Old artifact có chứa vulnerability không?
- Mitigation nào có thể bảo vệ old artifact tạm thời?
- Có safe previously approved version khác?
- DB schema vẫn tương thích với old code không?
- External side effects có thể được đảo ngược không?
- Key/credential vừa rotate có bị dùng lại không?
- Ai có quyền quyết định dưới áp lực incident?

Không mặc định chạy lại old image là lựa chọn an toàn nhất.

### 19.2. Roll-forward

**Roll-forward** là tạo một bản sửa bổ sung để giải quyết regression của patched version mà vẫn giữ security fix.

Phù hợp khi:

- Rollback sẽ khôi phục vulnerability Critical.
- Schema/key state không cho phép backward operation.
- Có thể sửa nhanh một regression riêng với test bổ sung.
- Có deployment automation và observability đủ tin cậy.

### 19.3. Rollback matrix

| Situation | Lựa chọn cần xem |
| --- | --- |
| Patch phá health, old version không có known high-risk vulnerability | Rollback theo kế hoạch nếu dữ liệu tương thích |
| Patch phá health, old version chứa active exploit | Contain/disable feature hoặc roll-forward; không tự rollback trái policy |
| Database migration irreversible | Restore/forward correction với data reconciliation, không chỉ revert image |
| Secret rotated/revoked | Không khôi phục compromised credential, update consumers |
| Patch gây denial of service do authz lookup | Capacity/local policy optimization hoặc rollout adjustment, giữ invariant |
| Canary phát hiện data corruption | Stop rollout, isolate traffic, điều tra integrity và recovery |
| Vendor patch bị thu hồi | Assess advisory/source, thay safe build theo approval |

### 19.4. Kiểm thử recovery plan

Một rehearsal có thể kiểm tra:

- Rollback command/script và quyền thực thi.
- Khả năng switch traffic.
- Restore state/database trong môi trường an toàn.
- Queue backlog/reconciliation.
- Artifact availability và provenance.
- Monitoring khi quay về state an toàn.
- RPO/RTO thực tế khi áp dụng.
- Security invariants sau recovery.

Không cần thực hiện destructive production restore để chứng minh mọi thứ; nên dùng sandbox và drill được phê duyệt, với giới hạn ghi rõ.

## 20. Emergency patch testing

### 20.1. Khi nào có tình huống khẩn?

Ví dụ:

- Cơ quan/vendor xác nhận active exploitation của vulnerability applicable.
- Incident response thấy dấu hiệu compromise.
- Production secret có nguy cơ đang bị sử dụng trái phép.
- Lỗi authentication/authorization có khả năng lộ dữ liệu ngay.
- Một control-plane vulnerability cho phép chiếm quyền quản trị.

Những tín hiệu này có thể yêu cầu containment trước khi hoàn tất regression suite. **Security response không được trì hoãn chỉ để có bộ test hoàn hảo.**

### 20.2. Minimum viable security tests

Với emergency, phân loại các checks:

**Không nên bỏ qua nếu có thể thực hiện an toàn:**

- Verify artifact/source/signature/digest.
- Kiểm tra fix targeted security invariant.
- Smoke tests cho critical business flows.
- Test fail-safe và privileged boundaries bị ảnh hưởng.
- Verify release/config và post-deploy runtime.
- Bật monitoring/alert, có người theo dõi.
- Có phương án containment/forward-fix.

**Có thể thực hiện sau theo quyết định có thẩm quyền:**

- Full performance benchmark.
- Exhaustive long-running fuzzing.
- Extended compatibility matrix.
- Noncritical business journeys.
- Secondary environments không liên quan exposure.
- Một số manual review mở rộng.

Danh mục cụ thể phải theo **risk, policy và nghĩa vụ thực tế**. Bỏ một test cần record lý do, owner, expiry và kế hoạch bổ sung.

### 20.3. Ví dụ emergency workflow

~~~mermaid
flowchart TD
    A["Credible active exploit / urgent patch"] --> B["Incident/change commander + risk context"]
    B --> C["Contain exposure when possible"]
    C --> D["Verify patch source and artifact identity"]
    D --> E["Targeted security test + critical smoke"]
    E --> F{"Security claim verified?"}
    F -- "No" --> G["Fix, isolate, alternative mitigation"]
    G --> E
    F -- "Yes" --> H["Approved emergency deployment"]
    H --> I["Limited rollout or targeted urgent promotion"]
    I --> J["Runtime identity + security verification"]
    J --> K{"Critical regression or residual exploit?"}
    K -- "Yes" --> L["Stop, contain, rollback/forward-fix decision"]
    K -- "No" --> M["Complete deferred tests and evidence"]
    M --> N["Retest/closure + post-incident review"]
~~~

### 20.4. Phân biệt emergency patch với miễn trừ vĩnh viễn

Một bước kiểm thử bị defer do khẩn cấp phải có:

- Test ID và lý do không thực hiện.
- Owner và thời điểm dự kiến hoàn tất.
- Interim controls.
- Risk owner/authorized approval.
- Monitoring và stop conditions.
- Record update khi test hoàn tất.
- Reassessment nếu còn failure/unknown.

Không chuyển **DEFERRED** thành **PASS**.

## 21. Kiểm soát dữ liệu và tính an toàn của test

### 21.1. Dùng dữ liệu synthetic

Ưu tiên:

- User A/B và tenant A/B giả.
- Orders có dữ liệu không phải PII thật.
- Test tokens và secret canaries không có quyền production.
- Simulated webhook payload từ test provider.
- Database snapshots đã được kiểm soát/khử nhạy cảm.
- Dedicated test buckets và audit sinks.
- Tài nguyên tự dọn theo test lifecycle.

Không copy dữ liệu khách hàng vào laptop/CI artifact chỉ để chạy patch regression.

### 21.2. Test nguy hiểm cần sự cho phép

Những phép thử như exploit reproduction, fuzzing mạnh, load stress, race, malformed parsers hoặc fault injection trên production có thể gây gián đoạn. Cần:

- Scope và authorization rõ.
- Safe environment hoặc sandbox.
- Rate, concurrency và duration limits.
- Observability và stop conditions.
- Rollback/recovery readiness.
- Incident contact và người phê duyệt.
- Evidence handling an toàn.

Có thể kiểm tra vulnerability class bằng **safe assertions, code/config review, vendor fix mapping và controlled tests** thay vì thực thi exploit có tác động phá hoại.

### 21.3. Test artifacts cũng là dữ liệu nhạy cảm

Patch testing có thể tạo:

- HTTP request/response chứa token.
- Stack traces và internal URLs.
- Logs chứa tenant/user metadata.
- Database dumps và audit trails.
- Vulnerability exploit details.
- SBOM nội bộ, infrastructure topology.
- Screenshot hoặc recording của hành vi đặc quyền.

Cần phân quyền, redaction, retention, encryption và integrity protection cho evidence.

## 22. CI/CD pipeline cho patch verification

### 22.1. Pipeline nhiều gates

~~~mermaid
flowchart TD
    A["Patch proposal + advisory/finding"] --> B["Review affected scope / version / requirements"]
    B --> C["Source + dependency + artifact integrity"]
    C --> D["Static checks + unit security tests"]
    D --> E{"Quick gate passed?"}
    E -- "No" --> F["Triage / fix / authorized exception"]
    F --> C
    E -- "Yes" --> G["Build immutable artifact"]
    G --> H["Integration + targeted vulnerability tests"]
    H --> I["Contract/business + resilience tests"]
    I --> J{"Pre-release criteria met?"}
    J -- "No" --> F
    J -- "Yes" --> K["Release approval + deployment"]
    K --> L["Canary / runtime security verification"]
    L --> M{"Operational guards met?"}
    M -- "No" --> N["Stop / containment / rollback or roll-forward"]
    M -- "Yes" --> O["Full rollout + post-deploy retest"]
    O --> P["Finding closure or residual risk tracking"]
~~~

### 22.2. Ví dụ policy record cho CI

~~~yaml
pipeline_policy:
  id: "PATCH-VERIFICATION-DEMO"
  scope:
    service: "orders-api"
    environment: "release"
  required_gates:
    - "source-and-advisory-review"
    - "dependency-and-artifact-integrity"
    - "unit-security-regression"
    - "targeted-vulnerability-verification"
    - "integration-and-contract-tests"
    - "release-artifact-identity"
  production_gates:
    - "deployment-digest-verification"
    - "safe-runtime-negative-tests"
    - "observability-and-business-guardrails"
  status_semantics:
    passed: "PASS"
    failed: "FAIL"
    not_executed: "NOT_RUN"
    environment_error: "BLOCKED"
    omitted_with_approval: "DEFERRED"
  skip_is_pass: false
  required_evidence:
    - "finding-id"
    - "commit-id"
    - "artifact-digest"
    - "test-run-id"
    - "tool-and-policy-versions"
    - "environment"
    - "reviewer"
~~~

Mẫu này là **dữ liệu mô tả**, không phải cấu hình GitHub Actions/GitLab/Jenkins có thể chạy trực tiếp.

### 22.3. Build once, promote verified artifact

Một thực hành tăng traceability:

1. Build artifact một lần trong trusted pipeline.
2. Tạo digest/provenance và SBOM.
3. Chạy tests và scan trên artifact đó.
4. Promote **cùng artifact digest** giữa các môi trường khi phù hợp.
5. Verify deployment digest tại runtime.
6. Ghi những environment-specific configs đã được review.

Nếu rebuild artifact ở mỗi môi trường từ nguồn/live dependencies khác nhau, kết quả staging có thể không đại diện chính xác production.

### 22.4. CI green không chứng minh patch complete

Một pipeline có thể xanh vì:

- Security tests bị skip.
- Scanner thất bại nhưng không fail job.
- Artifact scan khác image deploy.
- Unit tests mock hết DB/policy.
- Canary job chưa chạy.
- Thư viện CVE vẫn tồn tại trong artifact phụ.
- Quy trình release dùng manual override.

Kiểm tra **test execution completeness, scope và provenance** thay vì nhìn một icon trạng thái.

## 23. Security assurance evidence cho patch testing

### 23.1. Ba lớp effectiveness

| Lớp | Câu hỏi | Evidence |
| --- | --- | --- |
| **Design effectiveness** | Patch plan và test strategy có giải quyết root cause, bypass paths và change risks? | Advisory, threat model, impact analysis, acceptance criteria |
| **Implementation effectiveness** | Code/config/artifact đã sửa và tests phù hợp đạt? | Code review, build, SAST/SCA, unit/integration tests |
| **Operating effectiveness** | Patch chạy trong môi trường/kỳ cần xét và control còn hiệu quả? | Runtime version/digest, canary metrics, audit, post-deploy retest |

Không dùng một unit test để tuyên bố cả ba lớp đều PASS.

### 23.2. Evidence chain

~~~mermaid
flowchart LR
    F["Finding + vulnerability evidence"] --> R["Security requirement / root cause"]
    R --> C["Patch commit / change record"]
    C --> B["Trusted build + artifact digest"]
    B --> T["Targeted tests + regression evidence"]
    T --> D["Deployment / canary record"]
    D --> V["Runtime version + security verification"]
    V --> A["Assurance assessment"]
    A --> X["Verified closure or residual-risk decision"]
~~~

Mỗi cạnh cần một reference có thể kiểm tra. Nếu security tests chạy trên artifact X nhưng deployment Y, chuỗi bằng chứng bị đứt.

### 23.3. Evidence metadata tối thiểu

- Patch/change/finding ID.
- Advisory/vendor/security requirement/source version.
- Asset and environment population.
- Pre-patch version/digest và post-patch version/digest.
- Patch artifact provenance, source commit và build ID.
- Test plan version, test case IDs, executed/blocked/skipped status.
- Expected/actual results và raw evidence refs được bảo vệ.
- Tool, rule/database versions và timestamp.
- Test data/identity scope và environment parity limitations.
- Reviewer/approver, risk owner và decisions.
- Canary metrics, rollout start/end, stop conditions.
- Reboot/restart/DB migration outcomes nếu áp dụng.
- Residual risk, exception, due date và retest status.

### 23.4. Evidence quality

Bằng chứng tốt cần:

- **Relevant:** đúng CVE/finding, security claim và asset.
- **Accurate:** version/digest và actual results đúng.
- **Complete within scope:** biết population và routes chưa test.
- **Fresh:** đúng deployment hiện tại.
- **Traceable:** kết nối requirement, patch, test và release.
- **Reproducible:** fixture/method đủ để thực hiện lại trong điều kiện cho phép.
- **Integrity-protected:** chống sửa trái phép phù hợp.
- **Confidential:** không lộ raw secret hoặc PII.
- **Independent:** có mức review độc lập phù hợp rủi ro.
- **Explicit limitations:** không che unknown hoặc deferred tests.

### 23.5. Các kết luận hợp lệ

- **Verified fixed in assessed scope:** có bằng chứng fix và deployment cho scope.
- **Mitigated, root cause still open:** exposure giảm bằng control bù trừ.
- **Partially patched:** một số assets đã update, assets khác còn.
- **Patch ineffective:** vulnerability vẫn tái hiện hoặc control không đúng.
- **Regression detected:** fix xử lý lỗi gốc nhưng phá function/security invariant.
- **Insufficient evidence:** thiếu test/deployment/identity proof.
- **Risk exception approved:** residual risk được chấp nhận có thời hạn.
- **Not applicable:** có căn cứ và scope được xác minh.

Không dùng “SUCCESS” chung cho mọi tình huống.

## 24. Mẫu hồ sơ patch testing YAML

Dữ liệu dưới đây **chỉ là template minh họa**; không có test run hay finding thật:

~~~yaml
assessment_id: "PATCH-TEST-DEMO-006"
module: "SECURITY_SECURITY_ASSURANCE"
chapter: "Patch management"
topic: "Kiểm thử patch"
patch:
  change_id: "PATCH-ORDERS-BOLA-DEMO"
  finding_id: "FIND-ORDERS-TENANT-ISOLATION"
  patch_type: "application-code"
  vendor_advisory_ref: null
  root_cause: "missing-object-level-authorization"
scope:
  service: "orders-api"
  environments:
    - "integration"
    - "production"
  paths:
    - "GET /api/orders/{id}"
    - "report-worker"
    - "order-cache"
  excluded:
    - "third-party-provider-internals"
versions:
  source_commit: "NOT_VERIFIED"
  old_artifact_digest: null
  patched_artifact_digest: null
  deployed_artifact_digest: null
requirements:
  - "PATCH-ORD-001"
  - "PATCH-ORD-002"
  - "PATCH-ORD-003"
test_cases:
  - id: "T-ORD-01"
    type: "positive-authorization"
    result: "NOT_RUN"
  - id: "T-ORD-02"
    type: "cross-tenant-negative"
    result: "NOT_RUN"
  - id: "T-ORD-06"
    type: "cache-isolation"
    result: "NOT_RUN"
  - id: "T-ORD-07"
    type: "worker-context"
    result: "NOT_RUN"
  - id: "T-ORD-10"
    type: "deployment-digest"
    result: "NOT_RUN"
  - id: "T-ORD-12"
    type: "audit-delivery"
    result: "NOT_RUN"
rollout:
  strategy: "PENDING_DECISION"
  canary_status: "NOT_STARTED"
  rollback_tested: false
  production_verified: false
evidence_refs: []
owners:
  control: "Orders API Engineering"
  change: "Release Engineering"
  risk: "Orders Product Risk Owner"
  assurance: "Security Assurance Reviewer"
open_findings: []
exceptions: []
design_effectiveness: "NOT_VERIFIED"
implementation_effectiveness: "NOT_VERIFIED"
operating_effectiveness: "NOT_VERIFIED"
assessment_conclusion: "INSUFFICIENT_EVIDENCE"
next_action: "Run targeted and integration tests, then validate rollout"
~~~

Khi áp dụng thật, hãy thay placeholders bằng **version, digest, timestamps, actual results, protected evidence references và người phê duyệt**. Không tự điền PASS chỉ vì test plan đã có.

## 25. Findings và remediation sau kiểm thử patch

### 25.1. Phân loại failure

| Failure | Ví dụ | Hành động |
| --- | --- | --- |
| **Patch not applied** | Pods còn image cũ | Sửa rollout/verify digest |
| **Targeted security test fails** | BOLA vẫn tái hiện | Mở lại fix, containment |
| **Security regression** | JWT invalid được chấp nhận | Block release, sửa filter |
| **Functional regression** | User hợp lệ không tạo order | Review API compatibility và logic |
| **Performance regression** | DB pool cạn sau authz lookup | Optimize/capacity, giữ security invariant |
| **Data migration failure** | Mất relation hoặc tenant scope | Stop deployment, reconcile/restore |
| **Monitoring gap** | Audit events mất sau update | Sửa instrumentation/log pipeline |
| **Environment mismatch** | Staging policy khác production | Ghi limitation, test runtime phù hợp |
| **Evidence gap** | Tests không gắn artifact digest | Re-run/trace build và deployment |
| **Rollback unsafe** | Old code không đọc schema mới | Thiết kế roll-forward/recovery |
| **Advisory mapping conflict** | Scanner vẫn báo vì backport | Vendor evidence + independent review |

### 25.2. Root cause và systemic improvement

Nếu một security fix bị bỏ qua trong report worker, cần hỏi:

- Vì sao threat model chỉ có API GET?
- Có thiếu owner cho async control?
- Có common authorization abstraction không?
- Unit/integration tests có bỏ đường bypass?
- Có policy chặn deploy khi test không chạy?
- Những services khác có cùng design pattern?
- Cần cập nhật security requirements, code review checklist hay platform controls?

**Mỗi patch failure là cơ hội cải thiện assurance program**, không chỉ sửa một testcase.

### 25.3. Closure criteria rõ ràng

Để đóng finding:

1. Affected assets và versions được inventory.
2. Patch hoặc mitigation được triển khai trong phạm vi.
3. Targeted vulnerability test/verification đạt.
4. Relevant regressions được kiểm tra hoặc ghi exceptions có thẩm quyền.
5. Artifact/runtime identity được xác minh.
6. Production rollout/operating evidence có đủ theo policy.
7. Residual risk được đánh giá.
8. Reviewer xác nhận bằng evidence references.
9. Những environment/consumers chưa patched được giữ trong child findings.

**PR merged ≠ patch deployed ≠ vulnerability verified fixed.**

## 26. Patch lifecycle, ưu tiên và SLA

### 26.1. Mức khẩn cấp phụ thuộc rủi ro

Patch testing không hoạt động độc lập với vulnerability prioritization.

Ví dụ các yếu tố:

- Active exploitation evidence.
- Asset criticality và data class.
- Public exposure và attacker prerequisites.
- Exploitability/reachability.
- CVSS, EPSS/KEV khi có và applicable.
- Existing mitigations và confidence.
- Patch change risk và thời gian cần test.
- Business continuity và maintenance constraints.
- Nghĩa vụ bắt buộc có áp dụng.

Một vulnerability không có CVE như BOLA vẫn có thể rất khẩn.

### 26.2. Phân biệt các mốc SLA

- **Detection:** finding/vulnerability được ghi.
- **Triage:** xác nhận applicability và priority.
- **Patch availability:** có candidate fix.
- **Test start/end:** test đã chạy và được review.
- **Mitigation:** exposure đã giảm có bằng chứng.
- **Deployment:** patch vào môi trường mục tiêu.
- **Verification:** fix được xác nhận trên deployment.
- **Closure:** finding được đóng theo policy.

Không trộn các mốc thành “patch completed” nếu chưa có runtime verification.

### 26.3. Test depth theo urgency

| Urgency | Cách kiểm thử |
| --- | --- |
| Emergency active exploitation | Contain, identity + targeted security tests + critical smoke + controlled rollout |
| High-priority exposed vulnerability | Full targeted security suite, key integration/contract, rollback readiness |
| Planned noncritical patch | Comprehensive compatibility/regression và rollout rehearsal phù hợp |
| Routine platform updates | Representative suite, dependency/drift checks và operational verification |

Dù urgent đến đâu, **không được giả lập trạng thái PASS cho test chưa chạy**. Nếu không thể thực hiện một bước, phải có risk decision, deferred test và monitoring.

## 27. Metrics: đo chất lượng patch, không chỉ tốc độ

| KPI/KRI | Cách sử dụng | Cảnh báo diễn giải |
| --- | --- | --- |
| **Patch test coverage** | Tỷ lệ patch có targeted/regression tests theo risk tier | Có tests không chứng minh chất lượng |
| **Targeted security test pass rate** | Fix xử lý đúng failure cases | Scope có thể thiếu bypass |
| **Regression escape rate** | Lỗi patch chỉ phát hiện sau rollout | Phụ thuộc độ bao phủ monitoring |
| **Time to verified patch** | Thời gian từ detection/decision tới retest runtime | Khác time to merge/deploy |
| **Patch-induced incident rate** | Rủi ro thay đổi | Cần gắn severity và population |
| **Rollback/roll-forward frequency** | Tính ổn định rollout | Rollback ít không luôn tốt |
| **Canary gate violations** | Độ nhạy của guardrails | Không có violation có thể do guardrails yếu |
| **Deployment completeness** | Tỷ lệ targeted assets thực nhận patch | Quên offline devices/regions có thể sai |
| **Artifact traceability coverage** | Tỷ lệ deployments nối được với tested digest | Digest trùng chưa chứng minh code an toàn |
| **Reopen rate after patch** | Fix chưa đầy đủ hoặc bypass xuất hiện | Cần root-cause grouping |
| **Deferred test age** | Những tests emergency còn thiếu | Không coi deferred như pass |
| **Patch backlog by risk tier** | Vulnerable exposure còn tồn | Priority phải được cập nhật |
| **Evidence freshness** | Kết quả còn đúng với deployed revision? | Báo cáo staging cũ có thể lỗi thời |
| **Exception expiry** | Các residual risks quá hạn | Exception không là remediation |

### 27.1. Ví dụ diễn giải coverage

Giả sử có 40 patches thuộc scope:

- 24 có targeted security tests và deployment evidence đã review.
- 8 có unit/integration tests nhưng thiếu runtime verification.
- 5 có tests bị BLOCKED.
- 3 được triển khai emergency, còn deferred tests.

**Verified patch evidence coverage = 24/40 = 60%** theo định nghĩa này.

Không được nói “hệ thống an toàn 60%”. 16 patches còn thiếu evidence có thể gồm patch rủi ro cao; cần xem **risk tier và exposure**.

### 27.2. Không tối ưu sai KPI

Đội có thể làm thời gian patch ngắn bằng cách bỏ test, rollback mọi lỗi nhưng tái đưa vulnerability, hoặc đóng findings ngay khi merge. Dashboard sẽ tốt hơn nhưng risk exposure không giảm tương ứng.

Nên kết hợp **speed + verified effectiveness + regression safety + residual risk**.

## 28. Vai trò và RACI

| Vai trò | Trách nhiệm |
| --- | --- |
| **Vulnerability Management/AppSec** | Risk, advisory applicability, security test objectives |
| **Application owner** | Code fix, unit/integration tests, business requirements |
| **QA/Security Testing** | Test strategy, positive/negative/bypass tests, execution |
| **Platform/SRE** | OS/container/cluster deployment, canary, rollback, runtime checks |
| **DBA/Data owner** | Migration, data integrity, access/RLS và restore |
| **Build/Release Engineering** | Artifact provenance, supply-chain checks, promotion |
| **Risk owner** | Exception, urgency, residual-risk decision theo thẩm quyền |
| **Security Assurance/Audit** | Traceability, evidence quality, independent conclusion |
| **Incident Response** | Containment và forensics khi exploitation/compromise |
| **Business/Product owner** | Critical business flows, acceptance và continuity needs |

RACI minh họa:

| Hoạt động | App owner | QA/AppSec | Platform/SRE | Risk owner | Assurance |
| --- | --- | --- | --- | --- | --- |
| Patch impact analysis | **A/R** | R | C | C | C |
| Targeted vulnerability tests | R | **A/R** | C | I | C |
| Functional regression | **A** | R | C | I | C |
| Migration/recovery rehearsal | C | C | **A/R** | C | C |
| Artifact/provenance verification | R | C | **A/R** | I | C |
| Canary/runtime verification | C | R | **A/R** | I | C |
| Emergency residual-risk decision | C | C | C | **A/R** | I |
| Independent closure evidence review | C | C | C | I | **A/R** |

RACI tùy tổ chức. Không mặc định một người có quyền **tự tạo patch, tự skip test, tự phê duyệt ngoại lệ và tự đóng finding** đối với hệ thống rủi ro cao.

## 29. Những sai lầm phổ biến

### 29.1. Coi cài patch thành công là đã fix

**Sai:** package manager báo upgrade complete nên đóng CVE.

**Đúng:** verify running version/build, advisory applicability và security behavior.

### 29.2. Chỉ chạy smoke tests

**Sai:** GET /health trả 200 nên patch an toàn.

**Đúng:** targeted vulnerability tests, security invariants và regression theo change impact.

### 29.3. Test không gắn artifact

**Sai:** staging test image X nhưng production deploy image Y.

**Đúng:** immutable artifact digest, promotion và runtime identity verification.

### 29.4. Chỉ test happy path

**Sai:** A đọc order A thành công nên authorization fix đúng.

**Đúng:** test wrong tenant/role, bypass, fail-safe, cache/export/worker.

### 29.5. Mock mọi dependency

**Sai:** mock repository trả empty nên kết luận RLS bảo vệ production.

**Đúng:** unit test + integration với actual DB/policy và environment evidence.

### 29.6. Không xét transitive dependency

**Sai:** direct library đã nâng, nested vulnerable package vẫn trong image.

**Đúng:** effective graph/SBOM và artifact scanning.

### 29.7. Không kiểm tra migration/rollback compatibility

**Sai:** revert image sau khi đã drop column.

**Đúng:** migration rehearsal, expand/contract và recovery planning.

### 29.8. Reboot chưa thực hiện

**Sai:** kernel package mới được installed nhưng host đang chạy kernel cũ.

**Đúng:** verify running kernel sau reboot và service health.

### 29.9. Rollback về bản dễ khai thác

**Sai:** vì availability, quay về image chứa actively exploited flaw mà không đánh giá.

**Đúng:** contain, safe rollback hoặc roll-forward với risk approval.

### 29.10. Canary chỉ nhìn CPU và HTTP 200

**Sai:** không phát hiện rò dữ liệu do traffic canary không chạm attack path.

**Đúng:** chạy safe targeted security checks và audit guardrails.

### 29.11. Skip test thành PASS

**Sai:** scanner timeout nhưng pipeline xanh.

**Đúng:** FAIL/BLOCKED/NOT_RUN/DEFERRED có semantics rõ.

### 29.12. Không ghi những paths không test

**Sai:** review một endpoint rồi tuyên bố toàn bộ service fixed.

**Đúng:** scope, exclusions, confidence và residual risk minh bạch.

### 29.13. Dùng dữ liệu production thiếu kiểm soát

**Sai:** copy database customer để chạy exploit reproduction.

**Đúng:** synthetic fixtures, controlled lab, masking và authorization.

### 29.14. Không review supply-chain integrity của patch

**Sai:** tải bản vá từ một nguồn ngẫu nhiên rồi áp vì version trông mới.

**Đúng:** trusted vendor/source, checksum/signature, provenance và change approval.

### 29.15. Không theo dõi deferred emergency tests

**Sai:** patch khẩn được triển khai nhưng những tests bỏ qua không bao giờ chạy.

**Đúng:** owner, deadline, monitoring và follow-up evidence.

### 29.16. Đóng finding khi PR merged

**Sai:** fix chưa deploy mà report control effective.

**Đúng:** runtime verification và retest theo security claim.

### 29.17. Quên phiên bản app cũ trong rolling upgrade

**Sai:** worker mới ghi message schema mà worker cũ không đọc được.

**Đúng:** version-skew tests và compatibility window.

### 29.18. Không kiểm tra audit/detection sau patch

**Sai:** đổi thư viện logging, mất security events nhưng health vẫn xanh.

**Đúng:** test protected event pipeline và alert delivery.

### 29.19. Coi vendor advisory là test result

**Sai:** vendor nói patched, nên implementation của ứng dụng chắc chắn an toàn.

**Đúng:** đối chiếu version/source và test các tích hợp/requirements đặc thù.

### 29.20. Bỏ qua risk khi không có patch chính thức

**Sai:** không có vendor update nên không có gì kiểm thử.

**Đúng:** xác minh mitigations, isolation, feature disable, monitoring và residual risk.

## 30. Checklist thực hành kiểm thử patch

- [ ] Có patch/change ID, reason, vulnerability/finding ID và owner.
- [ ] Đã xác định asset/environment/region/tenant population.
- [ ] Đã xác minh affected/fixed version theo vendor/product đúng.
- [ ] Có baseline pre-patch version/digest, business và operational metrics.
- [ ] Có threat scenario và security requirement cần bảo đảm.
- [ ] Có target patched artifact/config identity và trusted source evidence.
- [ ] Đã review patch diff, dependencies, plugins, build toolchain và provenance.
- [ ] Có test scope, risk tier, positive/negative/bypass/failure cases.
- [ ] Targeted vulnerability regression test có expected outcome rõ.
- [ ] Đã kiểm tra code paths tương tự hoặc alternate routes liên quan.
- [ ] Functional/business flows hợp lệ vẫn hoạt động.
- [ ] API/contracts và backward compatibility được đánh giá.
- [ ] Database/data migration có test integrity và recovery.
- [ ] Runtime config, IAM, RLS, network rules được xác minh effective state.
- [ ] OS/kernel patch có kiểm tra running version sau reboot nếu cần.
- [ ] Container/cluster patch có version/digest và rolling upgrade checks.
- [ ] App/worker/queue version-skew và retry semantics được kiểm thử.
- [ ] Performance, reliability, resource saturation có guardrails theo risk.
- [ ] Audit, alert, logging và detection pipeline vẫn hoạt động.
- [ ] Test environment parity và limitations đã được ghi.
- [ ] Test data synthetic, evidence được bảo vệ khỏi lộ PII/secret.
- [ ] Có rollback/roll-forward, backup/restore plan với dependencies rõ.
- [ ] Canary/blue-green/rollout strategy được đánh giá cho vulnerability urgency.
- [ ] Có stop conditions và người có quyền dừng rollout.
- [ ] Security scanner/tool failures không được coi là PASS.
- [ ] Emergency deferred tests có approval, owner, deadline và monitoring.
- [ ] CI evidence gắn build, commit, tool versions, test run, environment.
- [ ] Artifact production khớp artifact đã test, runtime replicas được xác minh.
- [ ] Có re-scan/security retest sau deployment trong scope bắt buộc.
- [ ] Findings fail/regression có owner, triage, remediation và retest.
- [ ] Exceptions/residual risk có phê duyệt đúng thẩm quyền và expiry.
- [ ] Không đóng finding khi chỉ có PR merge hoặc patch download.
- [ ] Closure report nêu scope, evidence, giới hạn và tình trạng assets chưa patch.
- [ ] Có trigger re-test khi dependency, environment, threat hoặc configuration thay đổi.

Checklist là **công cụ hỗ trợ đánh giá**, không thay cho evidence thực tế trên phiên bản và môi trường cần bảo vệ.

## 31. Bài tập thực hành

### Bài tập 1 — Xây test plan cho BOLA

Orders API có lỗi user A đọc order tenant B. Patch thêm tenant filter ở repository.

Hãy tạo ít nhất:

- Hai positive tests.
- Bốn negative/bypass tests.
- Một test cache.
- Một test report worker.
- Một test fail-safe.
- Một test post-deploy artifact identity.
- Một acceptance criterion để đóng finding.

Giải thích vì sao test repository mock chưa chứng minh DB query thật.

### Bài tập 2 — Patch kernel trên cụm Kubernetes

Một cluster cần cập nhật kernel để giải quyết vulnerability. Hãy lập kế hoạch:

- Kiểm kê nodes, workloads và disruption budget.
- Backup/recovery/rollback prerequisites.
- Canary node pool và reboot sequence.
- Verify running kernel và security modules.
- Network policy/container runtime checks.
- Capacity, latency và pod scheduling guardrails.
- Điều kiện mở rộng rollout.
- Evidence trước khi đánh dấu patch complete.

### Bài tập 3 — CVE dependency có vendor backport

Một scanner báo vulnerable version, nhưng vendor distribution nói đã backport patch.

Hãy xác minh:

- Package identity và distribution release.
- Vendor advisory và binary package build metadata.
- Runtime artifact version/digest.
- Vulnerable path hoặc safe regression test.
- Scanner mapping/VEX applicability.
- Khi nào được đóng false positive và khi nào chưa đủ evidence?

### Bài tập 4 — Emergency patch có regression

Một authentication library vừa vá lỗ hổng exploited in the wild nhưng làm một nhóm client cũ không đăng nhập được.

Hãy đề xuất:

- Containment và release decision.
- Test bắt buộc trước rollout.
- Cách xử lý backward compatibility.
- Có nên rollback về vulnerable artifact không?
- Phương án roll-forward hoặc temporary mitigation.
- Canary metrics và post-deploy follow-up.
- Người có thẩm quyền và residual risk record.

### Bài tập 5 — Data migration không thể rollback đơn giản

Patch DB sửa column type và thêm RLS. Sau deployment, worker cũ không tương thích.

Hãy thiết kế expand/migrate/contract hoặc phương án khác, test version skew, data integrity, restore và security regression. Ghi điều kiện không được phép chỉ revert image.

### Bài tập 6 — Patch assurance evidence

Với finding về exposed production database credential, lập bảng:

- Rotation/revocation actions.
- Consumers cần cập nhật.
- Test credential cũ bị từ chối, credential mới hoạt động.
- CI logs/artifacts và incident investigation.
- Deploy/config identity.
- Monitoring và audit.
- Closure vs residual risk.

Không được xem “secret mới đã được lưu vào vault” là đủ chứng minh credential cũ bị vô hiệu hóa.

## 32. Câu hỏi tự kiểm tra

1. Kiểm thử patch khác triển khai patch như thế nào?
2. Patch presence và patch effectiveness khác nhau ra sao?
3. Vì sao health endpoint 200 chưa đủ chứng minh security fix?
4. Vulnerability finding nên cung cấp những gì trước khi thiết kế test?
5. Tại sao cần cả positive và negative tests?
6. Bypass path là gì trong tình huống tenant isolation?
7. Vì sao test với mock DB chưa chứng minh RLS đúng?
8. Những metadata nào liên kết test run với released artifact?
9. Nếu SCA không còn báo CVE, có thể đóng finding ngay không?
10. Vendor backported patch gây khó khăn gì cho scanner version checks?
11. Vì sao nâng direct dependency vẫn có thể giữ transitive vulnerable package?
12. Những rủi ro nào xuất hiện khi nâng thư viện authentication?
13. Contract testing giúp phát hiện loại regression nào?
14. Khi nào cần database migration rehearsal và data integrity checks?
15. Vì sao rollback app có thể không rollback dữ liệu?
16. Expand/migrate/contract giúp giảm rủi ro gì?
17. Kernel installed version khác running kernel thế nào?
18. Container image tag và digest khác nhau ra sao?
19. Tại sao cần kiểm tra imageID/digest của pods sau rollout?
20. Pod Ready chứng minh điều gì và không chứng minh điều gì?
21. Environment parity có những yếu tố security nào?
22. Có thể thực hiện security negative test ở production an toàn thế nào?
23. Khi nào cần approval đặc biệt cho fuzz/stress/exploit reproduction?
24. Canary có thể bỏ sót vulnerability regression vì sao?
25. Trong active exploitation, vì sao canary rollout cần cân bằng urgency?
26. Blue-green deployment có giới hạn nào với database migration?
27. Khi nào roll-forward an toàn hơn rollback?
28. Secret rotation có cho phép quay lại credential cũ không?
29. Những security controls nào có thể lỗi sau OS/kernel patch?
30. Một patch làm tăng DB connection use có thể gây impact bảo mật gì?
31. Vì sao fail-safe behavior cần kiểm thử sau patch?
32. CI scanner timeout nên có trạng thái nào?
33. Emergency deferred tests cần record những trường gì?
34. Phân biệt mitigated, remediated, deployed và verified fixed.
35. Evidence design, implementation và operating khác nhau ở đâu?
36. Tại sao version/digest mismatch phá assurance chain?
37. Những yếu tố nào cần có trong finding closure decision?
38. Kiểm thử patch cho managed service có gì khác self-managed?
39. Vì sao không nên dùng dữ liệu khách hàng thật không kiểm soát?
40. Một patch rollout đạt 60% verified coverage có nghĩa hệ thống an toàn 60% không?
41. Time to patch khác time to verified remediation thế nào?
42. Những hành vi nào khiến KPI patch đẹp nhưng risk không giảm?
43. Ai có trách nhiệm approve exception và ai review evidence?
44. Khi nào cần re-test một bản vá đã triển khai?
45. Viết một câu security claim và ba test cases cho patch lỗi webhook replay.

## 33. Tổng kết

**Kiểm thử patch** không chỉ là chạy lại ứng dụng sau khi cập nhật. Một quy trình có giá trị phải chứng minh **bản vá đúng nguồn và đúng artifact, xử lý được vulnerability hoặc security requirement đã xác định, không tạo security/functional regression, tương thích với dữ liệu và các thành phần khác, đủ khả năng rollout/recovery, và thực sự hiện diện ở môi trường đích**. Các kỹ thuật trọng tâm gồm **targeted vulnerability verification, positive/negative/bypass tests, unit/integration/E2E, dependency/config review, migration rehearsal, performance/resilience tests, canary/blue-green guardrails, runtime digest verification và post-deploy retest**.

Trong **SECURITY_SECURITY_ASSURANCE**, kết luận phải dựa trên **traceability từ threat/finding → patch change → build/artifact → test run → deployed version → operating evidence → closure hoặc residual risk**. Cần phân biệt **patch installed với effective, merged với deployed, mitigated với fixed, PASS với NOT_RUN/BLOCKED/DEFERRED, design với operating effectiveness**. Mọi phương án rollback, exception hoặc emergency test reduction phải có giới hạn, người chịu trách nhiệm và bằng chứng minh bạch; khi threat, dependency, cấu hình hoặc kiến trúc thay đổi, assurance phải được đánh giá lại.

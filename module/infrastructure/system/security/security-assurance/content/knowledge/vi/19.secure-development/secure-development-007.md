# Security testing: Kiểm thử bảo mật có bằng chứng trong Secure Development

## 1. Security testing là gì?

**Security testing** (kiểm thử bảo mật) là quá trình sử dụng các kỹ thuật kiểm tra có chủ đích để tìm sai lệch giữa **yêu cầu bảo mật**, **hành vi hoặc cấu hình thực tế** và **mức rủi ro có thể chấp nhận** của một hệ thống. Nó không chỉ tìm lỗ hổng kỹ thuật mà còn xác minh rằng các security controls được thiết kế và vận hành đúng ở những trust boundaries quan trọng.

Một quy trình security testing thường có các câu hỏi:

- Những tài sản, dữ liệu, danh tính và chức năng nào cần bảo vệ?
- Threat scenario nào liên quan tới một endpoint, thư viện, cấu hình hay luồng nghiệp vụ?
- Hành vi nào **phải cho phép** và hành vi nào **phải từ chối**?
- Kiểm thử ở lớp nào có thể cung cấp bằng chứng cho yêu cầu đó?
- Kết quả thực tế khác dự kiến ở đâu và mức tác động thế nào?
- Bằng chứng có đúng build, environment, policy và phiên bản đang đánh giá không?
- Sau khi sửa, có thể chứng minh lỗ hổng không còn tái hiện và không tạo regression không?

Trong module **SECURITY_SECURITY_ASSURANCE**, mục tiêu không phải “chạy nhiều scanner nhất” mà là hình thành một chuỗi kiểm chứng:

**Risk scenario → Security objective → Requirement → Control → Test case → Evidence → Assessment → Finding → Remediation → Retest.**

Một báo cáo “không có finding” **không chứng minh hệ thống an toàn tuyệt đối**. Nó chỉ nói các phương pháp đã chạy chưa phát hiện vấn đề trong phạm vi, cấu hình, phiên bản và khả năng nhận diện tương ứng.

### 1.1. Security testing khác functional testing ra sao?

| Khía cạnh | Functional testing | Security testing |
| --- | --- | --- |
| Câu hỏi chính | Chức năng có làm đúng điều cần làm? | Hệ thống có từ chối, giới hạn hoặc phát hiện hành vi nguy hiểm đúng yêu cầu? |
| Kịch bản dương | User A xem đơn hàng A thành công | User A hợp lệ vẫn xem đơn hàng A trong đúng scope |
| Kịch bản âm | Thiếu trường bắt buộc thì nhận lỗi validation | User A gửi ID của đơn hàng B phải bị từ chối; không lộ dữ liệu B |
| Đầu vào | Business requirements, acceptance criteria | Threat model, trust boundaries, security requirements, misuse cases |
| Đầu ra | Functional correctness evidence | Security control evidence, vulnerabilities, residual risks, limitations |
| Điểm yếu nếu làm riêng | Có thể bỏ qua bypass hoặc logic abuse | Có thể gây từ chối quá mức hoặc hiểu sai nhu cầu nghiệp vụ |

Hai hoạt động **bổ sung nhau**. Một endpoint từ chối tất cả request có thể “đạt” vài negative tests nhưng thất bại chức năng. Do đó nên có cả **positive và negative assertions**.

### 1.2. Verification, validation và assurance

- **Verification:** hệ thống có thực thi đúng đặc tả và security requirements đã nêu không?
- **Validation:** những yêu cầu và control đó có giải quyết đúng nhu cầu và rủi ro thực tế không?
- **Security testing:** tạo observations và evidence cho một hoặc nhiều kiểm chứng.
- **Security assurance:** đánh giá mức độ tin cậy của toàn bộ evidence từ thiết kế, code, kiểm thử, vận hành và governance.

Ví dụ: test chứng minh API yêu cầu MFA khi thay email có thể là verification. Nhưng nếu attacker chiếm tài khoản qua helpdesk không cần MFA, mô hình bảo vệ tổng thể vẫn có vấn đề; đó là khoảng trống ở **validation và assurance scope**.

### 1.3. Một security control không phải một test

Control “người dùng chỉ đọc dữ liệu thuộc tenant mình” có thể cần kiểm tra tại nhiều điểm:

- API HTTP GET/POST/DELETE.
- Query, database RLS và cache.
- Batch export và asynchronous workers.
- Search, reporting và support tooling.
- Token, session, membership và delegated access.
- Error messages và audit.

Một test của một endpoint **không đại diện cho mọi đường thực thi**. Phải xác định population và coverage trước khi đưa kết luận.

## 2. Security testing nằm ở đâu trong Secure SDLC?

Kiểm thử bảo mật là hoạt động **liên tục**, không chỉ là pentest ngay trước ngày phát hành.

| Giai đoạn phát triển | Hoạt động bảo mật liên quan | Kết quả/evidence |
| --- | --- | --- |
| **Planning** | Phân loại dữ liệu, mục tiêu, abuse cases, risk tier | Security requirements và risk register |
| **Design** | Threat modeling, trust boundary, security architecture review | Threat scenarios và test objectives |
| **Implementation** | Secure code review, SAST, secret scanning, unit/security tests | Findings, code review và test results |
| **Build** | SCA, SBOM, artifact/image scan, provenance checks | Dependency evidence, build metadata |
| **Integration** | API tests, negative authorization, IaC tests, DAST/IAST nếu phù hợp | Integration test runs, config evidence |
| **Pre-release** | Risk-based pentest, abuse-case testing, manual verification, release gate | Assessed findings và decision record |
| **Deployment** | Runtime configuration verification, admission/policy checks | Deployment/config attestation và runtime validation |
| **Operations** | Continuous vulnerability management, log/detection verification, scheduled retest | Findings lifecycle, monitoring, incident/drill records |
| **Change/incident** | Test lại các control bị ảnh hưởng; xác minh khắc phục | Regression evidence và residual-risk update |

**Shift-left** có nghĩa đưa đánh giá và test phù hợp lên sớm để giảm chi phí sửa. **Shift-right** bổ sung kiểm tra trên cấu hình và hành vi vận hành. Không nên thay thế cái này bằng cái kia.

### 2.1. Các loại kiểm thử khác nhau phục vụ câu hỏi khác nhau

- **Unit security test:** logic kiểm tra quyền, validation, state transition, crypto wrapper ở phạm vi đơn vị.
- **Integration security test:** nhiều thành phần phối hợp như auth provider, database, cache, queue và policy engine.
- **End-to-end security test:** luồng từ client qua API đến các dịch vụ liên quan; có thể cần môi trường gần production.
- **Configuration/IaC test:** security posture của cloud, Kubernetes, network, IAM và build.
- **Manual security review:** tìm logic abuse, thiết kế hoặc exploit chain mà rules tự động dễ bỏ sót.
- **Penetration test:** đánh giá có phạm vi và sự cho phép để tìm cách khai thác xuyên các ranh giới.
- **Operational control test:** kiểm tra alert, revocation, rotation, recovery, incident response và effectiveness trong kỳ.

Một security program tốt chọn **đúng phương pháp cho claim**, không cố dùng một công cụ để kiểm tra mọi lớp.

## 3. Các nguyên tắc thiết kế security testing

### 3.1. Risk-based và threat-informed

Chọn ưu tiên dựa trên:

1. **Tài sản và mức ảnh hưởng:** dữ liệu khách hàng, tiền, identity, secret, admin control plane.
2. **Trust boundary:** từ Internet vào backend, từ tenant A sang tenant B, từ app sang database, từ dev sang prod.
3. **Attacker capability:** unauthenticated caller, authenticated user, compromised workload, malicious insider.
4. **Likelihood/exposure:** endpoint public, quyền rộng, thường xuyên thay đổi, lịch sử phát hiện.
5. **Business abuse:** thay người nhận thanh toán, hoàn tiền trái phép, export dữ liệu, đổi MFA.
6. **Control dependencies:** một policy engine hoặc identity provider dùng chung cho nhiều service.

Một endpoint “ít dòng code” nhưng có thể tạo admin token cần ưu tiên hơn một trang nội dung ít nhạy cảm.

### 3.2. Test hành vi **cho phép** và **từ chối**

Với yêu cầu “chỉ owner được sửa đơn hàng”, cần ít nhất:

- Owner sửa đơn hàng hợp lệ → thành công.
- Người không phải owner gửi cùng lệnh → từ chối.
- User chưa xác thực → từ chối.
- User role khác → hành vi theo policy.
- Owner đã bị thu hồi quyền → từ chối theo semantics.
- Cùng action qua bulk API, worker hoặc API khác → chính sách nhất quán.

Test chỉ có “403 cho người lạ” có thể PASS do request thiếu CSRF token, dữ liệu sai schema hoặc mock lỗi, **không chứng minh đúng authorization boundary**. Cần xác định chính xác nguyên nhân từ chối và có test dương.

### 3.3. Test ở điểm quyết định tin cậy

Nếu frontend ẩn nút “Delete”, test UI là chưa đủ. Backend phải từ chối hành động trái phép. Nếu gateway có rule chặn request nhưng worker nội bộ bỏ qua, phải test thêm service boundary.

Nguyên tắc:

- Không tin client-supplied role, tenant, status hoặc security flag.
- Định nghĩa **security invariant** tại server hoặc thành phần có thẩm quyền.
- Test cả những điểm vào không qua luồng UI.
- Mô phỏng trạng thái hỏng, timeout, retry, concurrency và thay đổi quyền.
- Xác minh kết quả cuối cùng, không chỉ HTTP status.

### 3.4. Có tính lặp lại, minh bạch và an toàn

Test cần ghi phương pháp, fixture, build và expected result để người khác có thể chạy lại. Security testing không được làm lộ secret, phá dữ liệu production hoặc gây gián đoạn ngoài phạm vi được phê duyệt.

Với pentest, fuzzing, load, SSRF hay scanning diện rộng, cần **authorization, scope và rule of engagement** rõ trước khi chạy. Không đưa kỹ thuật có thể gây hại vào một hệ thống không có quyền kiểm thử.

## 4. Lập kế hoạch và test strategy

### 4.1. Đầu vào thiết yếu

- System architecture, DFD và trust boundaries.
- Asset/data inventory, data classification và business criticality.
- Security objectives, policy, standards và control framework được áp dụng.
- Threat model, risk assessment, incidents và findings trước đó.
- API specification, data model, deployment topology và dependencies.
- Identity/authorization model và quyền của user/service.
- Release/change scope, technology stack, runtime environment.
- Contract hoặc nghĩa vụ đặc thù với dữ liệu và hệ thống.
- Test infrastructure, test identities, synthetic fixtures và phép thử được phê duyệt.

Không nên bắt đầu bằng một danh sách chung “quét mọi thứ” khi chưa biết phạm vi hoặc tiêu chí đạt.

### 4.2. Mapping từ threat đến test

| Threat ID | Security requirement | Control | Test objective | Evidence |
| --- | --- | --- | --- | --- |
| THR-API-01 | Không đọc dữ liệu tenant khác | Tenant-scoped authorization | GET/EXPORT bằng tenant sai bị từ chối | API test run, audit, query review |
| THR-AUTH-02 | Không bypass MFA ở thao tác nhạy cảm | Step-up policy | Không có step-up hợp lệ không thể thay authenticator | Integration test, policy/config |
| THR-INPUT-03 | Không thực thi input như query code | Parameterized SQL và validation | Input đặc biệt không đổi cấu trúc truy vấn | Code review, injection test |
| THR-SUPPLY-04 | Dependency rủi ro được quản trị | SCA và dependency policy | Build report, exposure và treatment đúng | SBOM, SCA, approved decision |
| THR-SECRET-05 | Không lộ secret trong artifacts | Secret handling và scanner | Canary secret không xuất hiện trong log/image | Scan/config review, retest |
| THR-DEPLOY-06 | Không public hóa storage nhạy cảm | IaC policy và runtime config | Bucket public trái policy bị chặn/phát hiện | Policy test, cloud config |
| THR-OPER-07 | Incident được phát hiện và phản ứng | Detection + runbook | Test signal tạo alert và được triage | SIEM event, drill evidence |

Bảng chỉ là **test plan**; chưa có kết quả thực thi.

### 4.3. Mẫu security test case

Một test case cần ghi:

- **Test ID và security claim.**
- Requirement/control/threat ID.
- Version của policy, code, cấu hình hoặc tiêu chí áp dụng.
- Chủ thể, quyền, dữ liệu/fixture và điều kiện trước.
- Hành động và trust boundary bị thử.
- **Expected outcome** gồm cả trạng thái hệ thống, dữ liệu và audit.
- Actual outcome và evidence reference.
- Environment, build, timestamp, tool/version.
- Reviewer và trạng thái PASS/FAIL/NOT RUN/BLOCKED.
- Giới hạn; nếu case không áp dụng, có căn cứ.

Test “gọi API và thấy lỗi” là mô tả quá mơ hồ nếu không biết chính xác lỗi nào và vì sao.

## 5. Các phương pháp kiểm tra phổ biến

### 5.1. Static Application Security Testing (SAST)

**SAST** phân tích source code, bytecode hoặc artifact mà không cần chạy ứng dụng theo kịch bản web, nhằm tìm pattern và dataflow có thể gây lỗi.

SAST có thể phát hiện:

- Đường dữ liệu không đáng tin vào sink nguy hiểm.
- Câu lệnh query ghép chuỗi không an toàn.
- Sử dụng crypto API hoặc deserialization rủi ro.
- Cấu hình và pattern code có thể sai.
- Một số đường bỏ qua validation hoặc output encoding.

**Điểm mạnh:** chạy sớm, tích hợp CI, chỉ vị trí code.

**Giới hạn:** false positive, false negative, thiếu runtime context, thiếu hiểu biết nghiệp vụ, khó xác định exploitability. SAST PASS không chứng minh authorization và business logic đúng.

**Assurance evidence:** rule set/version, scan scope, commit/build ID, findings, triage, kết quả suppression và code fix.

### 5.2. Dynamic Application Security Testing (DAST)

**DAST** gửi request tới ứng dụng đang chạy và quan sát phản hồi để phát hiện một số loại lỗi như injection, security header/cookie configuration, exposed endpoints hoặc các hành vi sai.

**Điểm mạnh:** quan sát hành vi runtime và một số khâu cấu hình tích hợp.

**Giới hạn:** phụ thuộc test identity, crawl coverage, dữ liệu và route được khám phá; khó hiểu authorization sâu hoặc logic nghiệp vụ; có thể gây thay đổi trạng thái.

DAST cần xác định:

- Có phép kiểm thử và môi trường an toàn?
- Có tài khoản với nhiều role/tenant?
- API specification có đầy đủ?
- Endpoint state-changing được xử lý sao?
- Scan có đi qua WAF, reverse proxy và authentication giống production?
- Có kiểm tra false positive và destructive side effects không?

Không suy từ “DAST không phát hiện gì” thành “API không có BOLA/IDOR”.

### 5.3. Interactive Application Security Testing (IAST)

**IAST** quan sát ứng dụng đang chạy có instrumentation/agent, kết hợp một số tín hiệu dataflow hoặc runtime và request test.

Ưu điểm: có thể kết nối input với execution path thực. Giới hạn: chỉ quan sát code path được chạy và phụ thuộc agent/framework, overhead và cấu hình. IAST không thay test nghiệp vụ hoặc code review.

### 5.4. Software Composition Analysis (SCA)

**SCA** phân tích dependency trực tiếp và bắc cầu, phiên bản, advisory, license hoặc metadata khác tùy công cụ.

Cần phân biệt:

- **Dependency present:** package nằm trong artifact hoặc dependency graph.
- **Known vulnerability matched:** phiên bản/điều kiện khớp advisory.
- **Exposure/reachability:** code vulnerable có thể được gọi trong hệ thống hay không.
- **Exploitability:** có thể khai thác trong điều kiện thực tế không.
- **Risk decision:** cần update, giảm thiểu, loại bỏ hay chấp nhận có điều kiện.

Một CVE có điểm severity cao không tự chứng minh ứng dụng khai thác được; nhưng một dependency được đánh giá “not reachable” bằng phương pháp yếu cũng không tự cho phép bỏ qua. Phải ghi **căn cứ, phiên bản, scope và thời hạn xem lại**.

### 5.5. Secret scanning

Tìm credential hoặc pattern secret trong repository, Git history, container layers, CI logs, artifacts và tài liệu được phép kiểm tra.

- Dùng synthetic/canary secrets để thử khả năng phát hiện.
- Xác nhận finding trước khi kết luận giá trị là secret thật.
- Nếu secret thật có thể đã lộ, ưu tiên **revoke/rotate và điều tra**, không chỉ xóa dòng code.
- Tránh đưa secret nguyên văn vào report/ticket.
- Ghi scanner coverage, false positives/negatives và trường hợp không quét được.

### 5.6. IaC, cloud và container configuration testing

Đánh giá Terraform, CloudFormation hoặc template tương đương, Kubernetes manifest, Dockerfile và cấu hình runtime.

Ví dụ:

- Cloud storage có public read trái policy.
- IAM role có wildcard permissions quá rộng.
- Security group mở database port ra Internet.
- Kubernetes pod privileged hoặc hostPath không cần thiết.
- NetworkPolicy không tạo default-deny như thiết kế.
- Image không có policy provenance/signature phù hợp.
- Audit và encryption bị tắt.

**Manifest PASS chưa chứng minh runtime PASS.** Cần kiểm tra deployment drift, effective policy, quyền thực tế và network flow.

### 5.7. Fuzz testing và property-based testing

**Fuzzing** tạo hoặc biến đổi nhiều input để tìm crash, parser lỗi, memory corruption hoặc trạng thái không dự kiến. **Property-based testing** kiểm tra invariant trên nhiều dữ liệu được sinh.

Các property hữu ích:

- Không có input nào của tenant A trả resource tenant B.
- Malformed JWT không được authenticated.
- Duplicate replay không được thực hiện chuyển tiền hai lần.
- Một token đã consume không thể được consume lại.
- Mọi state transition phải thỏa precondition được kiểm tra tại server.

Fuzzing không phải bằng chứng đầy đủ cho business rules nếu input generation không biểu diễn đúng domain. Cần seed, corpus, scope, sanitizer, hạn tài nguyên và phân loại crash/finding.

### 5.8. Manual code review và penetration testing

**Manual review** hữu ích cho:

- Authorization và business logic.
- Confused deputy, tenant context, privilege escalation.
- Session lifecycle, retry, race, workflow abuse.
- Trust assumptions, cryptography misuse và insecure design.

**Pentest** phối hợp các bước để kiểm tra khả năng khai thác thực tế trong scope đã cho phép. Nó cho biết nhiều về exploit chains nhưng vẫn là **point-in-time assessment** theo thời gian, phạm vi và quyền thử.

Một hệ thống có pentest PASS vào tháng trước vẫn có thể tạo lỗi mới sau một thay đổi API. **Continuous testing không làm pentest vô dụng, và pentest không thay continuous controls.**

## 6. Ma trận phương pháp: chọn công cụ đúng câu hỏi

| Câu hỏi | Phương pháp chủ yếu | Bổ trợ | Không nên kết luận quá mức |
| --- | --- | --- | --- |
| Code có ghép SQL không an toàn? | SAST + code review | Injection integration test | Không có finding SAST tức không có SQLi |
| User A có đọc resource B không? | Authorization negative tests | Manual review, pentest | DAST crawl đủ xác minh BOLA |
| Dependency có advisory rủi ro? | SCA/SBOM | Reachability, upgrade tests | CVE match tức exploitable |
| Secret nằm trong image/log không? | Secret scanning | Canary tests, runtime log review | Không thấy secret tức không có rò |
| Cloud bucket có public access không? | IaC policy + runtime check | Cloud config review | Template đúng tức runtime đúng |
| Token bị replay được không? | Stateful integration/concurrency tests | Protocol review | Một test tuần tự đủ bắt race |
| MFA có thể bị bypass qua helpdesk không? | Workflow review + abuse-case tests | Pentest có scope | Test UI login bao phủ recovery |
| Vulnerability scanner báo lỗi là thật? | Manual reproduction và triage | Code/runtime evidence | Mọi alert đều là vulnerability |
| Detection rule có cảnh báo đúng không? | Safe signal simulation/drill | SIEM config/log review | Có log tức incident response hiệu quả |

Không cần triển khai tất cả phương pháp ở cùng mức cho mọi service; cần **risk-based assurance coverage**.

## 7. Những nhóm yêu cầu cần security testing

### 7.1. Authentication

Kiểm tra:

- Login với credential đúng/sai, account disabled, lockout và anti-automation.
- MFA/step-up ở thao tác nhạy cảm.
- Session fixation, token expiry, logout/revocation và refresh token rotation.
- JWT issuer, signature, audience, expiry và algorithm policy.
- Recovery/reset, authenticator binding và các đường fallback.
- Brute-force protection có bị lợi dụng làm denial of service?
- IdP/federation flow, account linking và callback/redirect.

Không kết luận authentication mạnh chỉ vì website có trang MFA.

### 7.2. Authorization và tenant isolation

Kiểm tra **subject – action – object – context**:

- BOLA/IDOR: đổi object ID của tenant hoặc user khác.
- BFLA: gọi function chỉ dành cho role khác.
- Mass assignment: client gắn thêm ownerId, isAdmin hoặc state ngoài quyền.
- Authorization của bulk API, export, search, webhook và worker.
- Delegated access/impersonation và quyền của support.
- Permission revoke, cache và long-lived session.
- Negative test ở API và data layer; positive test để tránh từ chối nhầm.

**Chỉ có role check ở controller không đảm bảo data-level isolation** nếu các đường nội bộ gọi service hoặc query không giữ scope.

### 7.3. Input validation và injection

Các lớp cần xem:

- SQL/NoSQL query, ORM, shell/process invocation.
- Template/rendering, XPath/LDAP hoặc các interpreter nếu sử dụng.
- XSS và output encoding theo đúng context.
- Header, URL và redirect validation.
- Deserialization, XML parser, file parser.
- Path traversal, archive extraction, upload.
- SSRF và egress/metadata endpoints.

Giải pháp phải phù hợp sink. Ví dụ **parameterized SQL** giúp phân tách dữ liệu khỏi câu lệnh; regex chặn một vài ký tự không thay thế parameterization. **Output encoding** phải phụ thuộc context HTML, attribute, JavaScript, URL hoặc template.

### 7.4. Cryptography, transport và secret handling

Kiểm tra:

- TLS được cấu hình và dùng đúng vùng.
- Không dùng thuật toán/chế độ mã hóa bị cấm bởi baseline áp dụng.
- Key/secret không hard-code hoặc xuất hiện trong logs, artifacts.
- Mật khẩu được xử lý bằng password hashing thích hợp.
- Random/token generation dùng cơ chế mật mã phù hợp.
- Certificate validation, hostname checking và trust store.
- Key rotation, revocation và backup lifecycle.
- Signature/MAC verification xử lý đúng lỗi và không bỏ qua kiểm tra.

Không nên tự phát minh crypto primitive; dùng thư viện được thẩm định và kiểm tra cách tích hợp.

### 7.5. Data protection và privacy

Kiểm tra:

- Trường dữ liệu được trả đúng quyền và có masking/minimization.
- PII không xuất hiện ngoài mục đích trong logs, telemetry và test artifacts.
- Export/DLP rule dựa trên classification và destination.
- Retention/deletion và backup restore không tái lộ dữ liệu.
- Third-party payload chỉ có dữ liệu cần thiết.
- Privacy consent/purpose gate nếu áp dụng.
- Cross-tenant leakage qua search, cache và analytics.

Security testing hỗ trợ privacy assurance, nhưng không tự xác nhận mọi nghĩa vụ pháp lý hoặc cơ sở xử lý đã được đáp ứng.

### 7.6. Configuration và deployment

Kiểm tra:

- IAM/permission, secret management, network policy.
- Security headers, cookies, CORS/CSRF theo kiến trúc.
- Debug endpoints, actuator/management API và error verbosity.
- Cloud storage ACL, database/public ingress.
- Container capabilities, pod admission, signed artifacts.
- Logging/monitoring, secure defaults và drift detection.
- Production có đúng artifact đã kiểm thử không.

Đặc biệt, một CI pipeline PASS nhưng production triển khai image khác hoặc tắt security filter là **assurance gap**.

### 7.7. Availability và abuse resistance

Kiểm tra:

- Rate limiting theo actor/tenant/action.
- Resource quotas, connection pool, queue backlog.
- Request size, upload limit, parser timeout.
- Retry/idempotency, lockout abuse, replay.
- Graceful degradation và fail-safe behavior.
- Thao tác cạnh tranh khiến invariant bị vi phạm.

Không chạy stress test có thể gây gián đoạn ở production khi chưa có scope và phê duyệt phù hợp.

## 8. Từ threat model thành test cases có thể thực thi

### 8.1. Một kịch bản Orders API

Giả sử hệ thống đặt hàng dùng **Java/Spring Boot** với các chức năng:

- Khách hàng xem chi tiết đơn hàng.
- Nhân viên hỗ trợ xem đơn hàng trong phạm vi tenant được giao.
- Admin có thể xử lý refund theo điều kiện riêng.
- Worker gửi sự kiện và tạo báo cáo.

**Threat THR-ORDERS-01:** user A có access token hợp lệ nhưng thay order ID trong request để xem dữ liệu user B thuộc tenant khác.

**Security requirement SEC-REQ-ORDERS-01:**

> Mọi truy xuất order phải ràng buộc với tenant/principal đã được xác minh; không cho dùng ID tài nguyên tùy ý để vượt phạm vi, bất kể request qua controller, service hay batch API.

**Security claim:** “Order query chỉ trả dữ liệu thuộc tenant đáng tin của caller; với order tenant khác, dữ liệu không được tiết lộ.”

Các ca tối thiểu:

| ID | Principal | Resource | Expected | Lý do |
| --- | --- | --- | --- | --- |
| SEC-T01 | User A tenant A | Order A | Allow | Positive baseline |
| SEC-T02 | User A tenant A | Order B tenant B | Deny/no disclosure | Cross-tenant BOLA |
| SEC-T03 | User A tenant A | Không tồn tại | Not found | Phân biệt thông điệp và dữ liệu |
| SEC-T04 | Unauthenticated | Order A | Unauthorized | Authentication boundary |
| SEC-T05 | User A gửi header tenant B | Order B | Deny | Client tampering |
| SEC-T06 | User A gọi bulk export chứa B | Mixed orders | B bị loại/từ chối đúng policy | Alternate path |
| SEC-T07 | Event worker mang context tenant A, order B | Order B | Deny/quarantine | Async boundary |
| SEC-T08 | Cache chứa response của tenant B | Order B | Không nhận dữ liệu B | Cache isolation |
| SEC-T09 | Membership A vừa bị thu hồi | Order A | Deny theo revocation policy | Stale identity/permissions |

Một test plan có đường âm nhưng không có đường dương sẽ khó phát hiện tình huống app từ chối toàn bộ request do sai cấu hình.

### 8.2. Phân biệt vulnerability test và assurance test

- **Vulnerability test** thường đặt câu hỏi “có thể tạo lỗi/khai thác hay không?”.
- **Control verification test** đặt câu hỏi “control có thực thi một invariant cụ thể không?”.
- **Assurance assessment** xem bằng chứng đã đủ để kết luận cho risk objective và scope hay chưa.

Một negative authorization test có thể phục vụ cả hai mục tiêu, nhưng kết luận vẫn bị giới hạn bởi testcase, build và luồng đã bao phủ.

## 9. Java/Spring Boot: triển khai điểm kiểm tra quyền và unit test

### 9.1. Anti-pattern: tìm theo ID đơn thuần

Một endpoint nguy hiểm nếu chỉ gọi repository theo order ID, rồi trả dữ liệu mà **không kiểm tra tenant/owner**:

~~~java
// Vi du KHONG AN TOAN:
public OrderView getOrder(UUID orderId) {
    return orderRepository.findById(orderId)
        .map(OrderView::from)
        .orElseThrow(ResourceNotFoundException::new);
}
~~~

Client có thể đoán hoặc biết UUID của đơn hàng thuộc tenant khác. UUID khó đoán **không phải** authorization control.

### 9.2. Thiết kế tenant-scoped ở tầng nghiệp vụ

Giả sử service nhận một **VerifiedCaller** đã được tạo bởi tầng xác thực tin cậy, không deserialize trực tiếp từ HTTP request.

~~~java
public record VerifiedCaller(
        String subjectId,
        UUID tenantId) {
}

public interface OrderRepository {
    Optional<Order> findByIdAndTenantId(UUID orderId, UUID tenantId);
}

public record Order(UUID id, UUID tenantId, String status) {
}

public record OrderView(UUID id, String status) {
    public static OrderView from(Order order) {
        return new OrderView(order.id(), order.status());
    }
}

public final class ResourceNotFoundException
        extends RuntimeException {
}

@Service
public class OrderQueryService {
    private final OrderRepository repository;

    public OrderQueryService(OrderRepository repository) {
        this.repository = repository;
    }

    public OrderView getOrder(
            UUID orderId,
            VerifiedCaller caller) {
        Order order = repository
            .findByIdAndTenantId(orderId, caller.tenantId())
            .orElseThrow(ResourceNotFoundException::new);

        return OrderView.from(order);
    }
}
~~~

Đây là **ví dụ rút gọn** để minh họa invariant: repository phải thực sự áp filter tenant trong truy vấn. Chỉ truyền VerifiedCaller vào service **không tự đảm bảo** principal đáng tin; tầng HTTP/security phải xác thực JWT/session, membership và ánh xạ tenant context đúng. Nếu hệ thống có quyền theo owner/role sâu hơn, service cần kiểm tra các yêu cầu đó nữa.

### 9.3. Unit security tests với JUnit 5 và Mockito

~~~java
@ExtendWith(MockitoExtension.class)
class OrderQueryServiceSecurityTest {
    @Mock
    OrderRepository repository;

    @InjectMocks
    OrderQueryService service;

    private final UUID tenantA = UUID.randomUUID();
    private final UUID tenantB = UUID.randomUUID();
    private final UUID orderId = UUID.randomUUID();

    @Test
    void sameTenant_canReadOrder() {
        VerifiedCaller caller = new VerifiedCaller("user-a", tenantA);
        Order order = new Order(orderId, tenantA, "PAID");

        when(repository.findByIdAndTenantId(orderId, tenantA))
            .thenReturn(Optional.of(order));

        OrderView view = service.getOrder(orderId, caller);

        assertEquals(orderId, view.id());
        assertEquals("PAID", view.status());
        verify(repository)
            .findByIdAndTenantId(orderId, tenantA);
    }

    @Test
    void otherTenant_cannotReadOrder() {
        VerifiedCaller caller = new VerifiedCaller("user-a", tenantA);

        when(repository.findByIdAndTenantId(orderId, tenantA))
            .thenReturn(Optional.empty());

        assertThrows(
            ResourceNotFoundException.class,
            () -> service.getOrder(orderId, caller));

        verify(repository)
            .findByIdAndTenantId(orderId, tenantA);
        verifyNoMoreInteractions(repository);
    }
}
~~~

**Hạn chế của test trên:** test dùng mock repository, nên nó chứng minh service gọi phương thức tenant-scoped với tenant A trong tình huống đã mô phỏng. Nó **chưa chứng minh** truy vấn SQL/JPA thực thi đúng ở database, caller được xác minh từ token thật, hoặc các endpoint/worker khác cũng sử dụng service an toàn.

Bằng chứng đầy đủ hơn cần thêm integration tests, API authorization tests, kiểm tra dữ liệu trong DB và cache/async, tùy risk.

### 9.4. Integration test phải kiểm tra lỗi thật và kết quả dữ liệu

Một integration test có thể thiết lập:

- Hai tenant A/B và một order trong mỗi tenant.
- Token/session giả lập có xác minh context đúng tầng security.
- Database thật hoặc tương thích với policy đang được kiểm tra.
- Call GET /api/orders/{orderId}, export và các route khác.
- Assert status, response body không chứa trường của tenant B.
- Assert DB không bị sửa ngoài scope khi action là write.
- Nếu trả 404, xác nhận request đã đi qua authorization/data scope chứ không bị lỗi config.

**Không mặc định MockMvc với tất cả service mock là bằng chứng cho RLS**, vì query thực tế không chạy.

### 9.5. Security regression sau fix

Khi sửa một lỗi BOLA:

1. Giữ test tái hiện lỗi gốc.
2. Thêm negative tests cho endpoints tương tự.
3. Kiểm tra đường bulk, export, worker, cache và search.
4. Đảm bảo positive paths không bị chặn sai.
5. Chạy lại trên build có fix và cấu hình đúng.
6. Ghi evidence ID, commit, test run và reviewer.
7. Nếu finding liên quan runtime, xác nhận production rollout hoặc môi trường mục tiêu theo scope.

Một pull request được merge nhưng chưa triển khai/test lại **không đủ để đóng finding**.

## 10. Security testing các luồng nghiệp vụ phức tạp

Nhiều vấn đề nghiêm trọng không nằm ở input parser hay CVE mà ở **state machine và logic kinh doanh**.

### 10.1. Ví dụ refund

Giả sử nhân viên hỗ trợ có thể refund một đơn hàng khi:

- Order đã thanh toán.
- Số tiền refund không vượt số tiền còn lại.
- Actor có quyền trên tenant và scope.
- Refund lớn cần approval riêng.
- Cùng yêu cầu lặp lại không hoàn tiền hai lần.
- Audit ghi quyết định và giao dịch.

Test cần xét:

| Tình huống | Expected |
| --- | --- |
| Actor hợp lệ refund trong hạn mức | Thành công |
| Actor khác tenant | Từ chối |
| Refund vượt số tiền còn lại | Từ chối |
| Refund đơn chưa thanh toán | Từ chối |
| Không có approval cho số tiền yêu cầu | Từ chối |
| Request lặp với cùng idempotency key | Không refund hai lần |
| Hai request đồng thời với hạn mức còn lại thấp | Tổng refund không vượt số tiền còn lại |
| Thay amount sau approval | Approval không còn hợp lệ |
| Worker retry sau timeout | Không tạo giao dịch trùng |
| Admin role bị thu hồi trước khi xử lý | Hành vi đúng revocation policy |

Một test “refund API trả 200” chưa chứng minh business invariant nếu ledger thực tế trừ tiền hai lần khi race.

### 10.2. TOCTOU và race condition

**Time-of-check to time-of-use (TOCTOU)** xảy ra khi điều kiện được kiểm tra ở thời điểm T1 nhưng bị thay đổi trước khi hành động tại T2.

Ví dụ: hai request refund đều đọc “remaining=100”, mỗi request refund 80; nếu không có transaction/locking hoặc constraint phù hợp, cả hai có thể tạo tổng refund 160.

Cần kiểm tra:

- Atomic state transitions, transaction isolation và optimistic/pessimistic locking.
- Idempotency và unique constraints.
- Tính nhất quán giữa database, payment provider và event bus.
- Retry/rollback/compensation behavior.
- Audit và alert khi invariant bị vi phạm.

Có thể dùng concurrency tests lặp có kiểm soát; **một lần test không tái hiện race không chứng minh race không tồn tại**.

### 10.3. Replay và trạng thái đã dùng

Các giá trị dùng một lần như recovery token, coupon/transaction token hoặc password reset challenge cần test:

- Một lần dùng hợp lệ.
- Dùng lại tuần tự.
- Dùng đồng thời.
- Dùng sau TTL.
- Dùng cho account/purpose khác.
- Dùng khi server restart hoặc retry.
- Khả năng rollback làm phục hồi trạng thái consumed.

Nên lưu một lần dùng ở **server** và kiểm tra nguyên tử. Token “trông ngẫu nhiên” không thay thế one-time enforcement.

## 11. Security testing trong CI/CD

### 11.1. Thiết kế nhiều lớp gate

Một pipeline có thể gồm:

~~~mermaid
flowchart TD
    A["Pull Request"] --> B["Code review + unit security tests"]
    B --> C["SAST + secret scanning"]
    C --> D["SCA + IaC/image policy"]
    D --> E{"Fast gate đạt?"}
    E -- "Không" --> F["Triage / fix / documented exception"]
    F --> B
    E -- "Có" --> G["Build immutable artifact"]
    G --> H["Integration/API security tests"]
    H --> I["Threat-based DAST / manual review khi cần"]
    I --> J["Evidence collection + risk review"]
    J --> K{"Release criteria đạt?"}
    K -- "Không" --> L["Block release hoặc approval có thẩm quyền"]
    K -- "Có" --> M["Deploy + runtime verification"]
    M --> N["Continuous monitoring / retest"]
~~~

Các bước thực tế khác nhau theo đội và công nghệ. Không nhất thiết mọi PR phải chạy một pentest toàn diện; các bài test nhanh và có giá trị cao nên chạy thường xuyên, các bài test nặng theo thay đổi/rủi ro.

### 11.2. Ví dụ YAML kế hoạch pipeline (minh họa, không gắn runner cụ thể)

~~~yaml
pipeline: "secure-development-checks"
scope: "orders-api"
triggers:
  - "pull-request"
  - "main-merge"
  - "pre-release"
stages:
  - name: "security-unit-tests"
    required: true
    evidence: "junit-test-results"
  - name: "static-analysis"
    checks:
      - "sast"
      - "secret-scan"
    required: true
    evidence: "scanner-reports"
  - name: "composition-and-config"
    checks:
      - "sca"
      - "sbom"
      - "iac-policy"
    required: true
  - name: "integration-security"
    checks:
      - "object-level-authorization"
      - "session-and-token"
      - "critical-abuse-cases"
    required_for: "pre-release"
  - name: "runtime-validation"
    checks:
      - "deployed-policy"
      - "artifact-identity"
    required_for: "production"
release_policy:
  critical_unresolved_findings: "block-or-explicit-risk-decision"
  exceptions_require:
    - "risk-owner"
    - "justification"
    - "expiry"
    - "compensating-controls"
evidence:
  metadata:
    - "commit-id"
    - "artifact-digest"
    - "test-environment"
    - "tool-and-rule-versions"
    - "timestamp"
    - "reviewer"
~~~

Mẫu này biểu diễn **ý định kiểm soát**, chưa phải cấu hình có thể dùng ngay trên GitHub Actions, GitLab CI, Jenkins hoặc công cụ khác. Nếu tổ chức có những loại finding tuyệt đối không được phát hành, policy phải định nghĩa điều kiện cụ thể thay vì một câu “block-or-decision” chung.

### 11.3. Release gate phải dựa trên severity và policy, không chỉ số lượng

Một gate có thể xét:

- Severity/impact và khả năng khai thác.
- Loại tài sản/tenant và exposure.
- Có bằng chứng false positive hoặc not applicable hợp lệ không?
- Fix đã có và retest trên artifact mục tiêu chưa?
- Có control bù trừ và quyết định residual risk đúng thẩm quyền?
- Scanner/test có bị lỗi hoặc không hoàn tất?
- Findings cũ có quá hạn hay tái diễn?
- Artifact được deploy có đúng artifact đã test?

**Test job bị lỗi hoặc bị skip không được mặc định xem là PASS**. Phải có trạng thái **INCOMPLETE/BLOCKED** riêng.

### 11.4. Test report là dữ liệu cần bảo vệ

Scanner report và test artifacts có thể chứa:

- Source paths, query strings, credentials, stack trace.
- Tên user hoặc dữ liệu khách hàng.
- API endpoint nội bộ và network topology.
- Vulnerability details chưa được khắc phục.
- Authorization token và HTTP request dump.

Cần masking/redaction, RBAC, retention và audit. Không tự đẩy report chứa secret lên artifact công khai để chứng minh pipeline hoạt động.

## 12. Test environment và test data an toàn

### 12.1. Môi trường phải đại diện đúng

Một security test có thể PASS trong staging nhưng không đại diện production nếu:

- Identity provider khác policy.
- WAF, proxy, gateway hoặc TLS khác.
- Environment variables bật/tắt security filter.
- Database role/RLS khác.
- NetworkPolicy chưa được áp dụng.
- Build image khác artifact đã kiểm thử.
- CORS/cookie/session configuration khác.
- Production có thêm worker, queue hoặc integration.
- Rule SAST/DAST bỏ qua thư mục hoặc endpoint quan trọng.

Cần ghi rõ **environment parity** và nơi không tương đương. Khi dùng production validation, chỉ chạy những phép thử đã được đánh giá và phê duyệt với giới hạn tác động phù hợp.

### 12.2. Synthetic fixtures và phân quyền dữ liệu

Ưu tiên:

- Tạo dữ liệu giả theo schema nhưng không là dữ liệu cá nhân thật.
- User A/B, tenant A/B, role thường/admin với permissions có chủ đích.
- Canary values để kiểm tra log/data leakage.
- Test secret/credential không sử dụng cho production.
- Tự dọn dữ liệu sau test theo policy.
- Không dùng tài khoản khách hàng thật nếu chưa có điều kiện được phê duyệt.

Một test thất bại không được để lại tài khoản admin thử nghiệm, public bucket hoặc secret hoạt động lâu dài.

### 12.3. Kiểm thử chủ động có thể gây ảnh hưởng

Những kỹ thuật như fuzzing diện rộng, scanning mạnh, payload gây quá tải, account lockout test, load/race tests hoặc kiểm tra file parser cần:

1. Phạm vi và sự cho phép rõ ràng.
2. Giới hạn tốc độ, dữ liệu, giờ chạy và thời lượng.
3. Có môi trường cô lập hoặc sandbox.
4. Kế hoạch rollback/stop conditions.
5. Giám sát resource và tác động.
6. Thông báo cho owner/incident response khi cần.
7. Báo cáo minh bạch về điều không được thử do rủi ro vận hành.

**Không cần gây ra sự cố thật** để chứng minh một control. Có thể dùng mô phỏng an toàn, test doubles, fault injection có giới hạn và non-production environment.

## 13. Triage và xử lý findings

### 13.1. Phân biệt alert, finding và vulnerability đã xác minh

- **Tool alert:** tín hiệu máy quét phát hiện điều kiện đáng nghi.
- **Finding:** kết quả đánh giá có evidence, scope và mức độ đủ để ghi nhận vấn đề hoặc khoảng trống.
- **Confirmed vulnerability:** có cơ sở đủ về lỗi bảo mật và tác động/điều kiện.
- **False positive:** alert không biểu diễn lỗi theo tiêu chí đã kiểm chứng.
- **Insufficient evidence:** chưa đủ dữ kiện xác định kết luận.
- **Accepted risk/exception:** quyết định xử lý rủi ro có thẩm quyền, không xóa bản chất finding.

Triage cần không chỉ dựa vào CVSS hay tên tool, mà còn **assets, exposure, exploit preconditions, compensating controls, ảnh hưởng nghiệp vụ, quyền và bằng chứng**.

### 13.2. Mẫu finding lifecycle

~~~mermaid
stateDiagram-v2
    [*] --> DETECTED
    DETECTED --> TRIAGE
    TRIAGE --> FALSE_POSITIVE: Bằng chứng đủ
    TRIAGE --> NEEDS_EVIDENCE: Chưa đủ thông tin
    NEEDS_EVIDENCE --> TRIAGE: Có bằng chứng mới
    TRIAGE --> CONFIRMED: Lỗi được xác minh
    CONFIRMED --> ASSIGNED
    ASSIGNED --> FIX_IN_PROGRESS
    FIX_IN_PROGRESS --> RETEST_PENDING
    RETEST_PENDING --> VERIFIED_FIXED: Retest đạt
    RETEST_PENDING --> FIX_IN_PROGRESS: Retest không đạt
    CONFIRMED --> RISK_DECISION: Không thể fix ngay
    RISK_DECISION --> TIME_BOUND_EXCEPTION: Được phê duyệt
    TIME_BOUND_EXCEPTION --> RETEST_PENDING: Có fix
    VERIFIED_FIXED --> CLOSED
    FALSE_POSITIVE --> CLOSED
~~~

Nếu finding liên quan compromise hoặc phơi lộ dữ liệu đang diễn ra, phải kích hoạt **incident response/containment** theo mức rủi ro, không chờ đủ thủ tục vòng đời phát hiện.

### 13.3. Hồ sơ finding cần gì?

| Trường | Nội dung |
| --- | --- |
| Finding ID | Định danh bền vững |
| Source | Tool/test/manual review và phiên bản |
| Requirement/control | ID của security claim liên quan |
| Affected asset | Service, endpoint, environment, tenant/data class |
| Evidence | Steps, expected/actual, test run và dấu vết đã bảo vệ |
| Impact | Điều attacker có thể làm và điều kiện |
| Severity/risk | Quy tắc phân loại và căn cứ |
| Root cause | Lỗi thiết kế/code/config/process/evidence |
| Owner | Đội hoặc người chịu trách nhiệm |
| Target/remediation | Cách khắc phục và hạn |
| Retest criteria | Kịch bản lỗi gốc và regression |
| Residual risk/exception | Người phê duyệt, thời hạn, điều kiện |
| Closure | Build, deployment, reviewer và kết quả xác minh |

Không copy secret thật hoặc toàn bộ dữ liệu cá nhân vào ticket. Dùng dữ liệu giả và protected evidence references.

### 13.4. Root cause quan trọng hơn “thêm một rule”

Ví dụ lỗi BOLA:

- Không chỉ block một UUID cụ thể.
- Sửa mô hình authorization ở service/data access.
- Rà soát các endpoint tương tự, batch và async.
- Tạo regression tests chung.
- Xem tại sao design review, code review và test hiện tại bỏ sót.
- Cập nhật standards, checklist hoặc framework dùng chung khi cần.

Một lỗ hổng được sửa ở đúng một nơi nhưng pattern vẫn tái diễn nhiều service là dấu hiệu **systemic assurance gap**.

## 14. Security testing và đánh giá assurance evidence

### 14.1. Ba lớp effectiveness

| Lớp | Câu hỏi | Bằng chứng điển hình |
| --- | --- | --- |
| **Design effectiveness** | Control và test objectives có bao phủ threat đáng kể? | Threat model, security requirements, architecture review, test strategy |
| **Implementation effectiveness** | Code/config thực thi đúng invariant? | SAST, code review, unit/integration/DAST tests, IaC checks |
| **Operating effectiveness** | Control còn hoạt động với build/config thực và qua thời gian? | Runtime validation, detection drills, incident/access review, periodic retests |

Một test unit có thể chứng minh một method xử lý đúng input thử, nhưng không chứng minh security filter production bật hoặc audit pipeline thực sự nhận event.

### 14.2. Yêu cầu đối với bằng chứng

Bằng chứng tốt cần:

- **Relevant:** đúng security claim và trust boundary.
- **Accurate:** expected/actual và trạng thái test không bị hiểu sai.
- **Complete within scope:** biết population và đường chưa kiểm tra.
- **Fresh:** đúng build, artifact digest, rule set và environment.
- **Traceable:** nối test tới requirement, finding, owner và fix.
- **Reproducible:** đủ fixture/method để chạy lại trong môi trường được phép.
- **Independent:** reviewer có mức độc lập phù hợp rủi ro.
- **Integrity-protected:** report không bị sửa trái phép.
- **Confidential:** không làm lộ secret, PII hoặc exploit details không cần thiết.

**Scanner version và rule set** quan trọng: nếu hai lần scan dùng rule khác nhau, chênh lệch số findings chưa chắc phản ánh code an toàn hơn.

### 14.3. Mẫu hồ sơ assurance YAML

Dưới đây là **mẫu dữ liệu minh họa**, chưa có kết quả thực thi:

~~~yaml
assessment_id: "SECURITY-TESTING-DEMO-007"
service: "orders-api"
module: "SECURITY_SECURITY_ASSURANCE"
control_owner: "Orders API Engineering"
risk_owner: "Orders Product Owner"
scope:
  environment: "integration"
  build: "demo-build-not-verified"
  apis:
    - "GET /api/orders/{id}"
    - "POST /api/orders/{id}/refund"
  excluded:
    - "production-runtime"
    - "third-party-payment-provider"
security_claims:
  - id: "SEC-REQ-ORDERS-01"
    description: "Cross-tenant order access is denied"
  - id: "SEC-REQ-REFUND-02"
    description: "Refund cannot exceed authorized remaining amount"
test_plan:
  - id: "SEC-T01"
    category: "positive-authorization"
    status: "NOT_RUN"
  - id: "SEC-T02"
    category: "negative-authorization"
    status: "NOT_RUN"
  - id: "SEC-T03"
    category: "concurrent-business-logic"
    status: "NOT_RUN"
  - id: "SEC-T04"
    category: "dependency-and-config"
    status: "NOT_RUN"
scanners:
  sast_version: "NOT_VERIFIED"
  sca_version: "NOT_VERIFIED"
  rule_set: "NOT_VERIFIED"
evidence_refs: []
design_review: "PENDING"
implementation_review: "NOT_VERIFIED"
operating_review: "NOT_VERIFIED"
findings: []
assessment_conclusion: "INSUFFICIENT_EVIDENCE"
confidence: "LOW"
next_action: "Execute tests and review evidence"
exception:
  approved: false
  approver: null
~~~

Không điền PASS khi chỉ có test plan. Trong dự án thật phải dùng kết quả thực, commit/digest, timestamps, runner info, environment, reviewer và protected references.

### 14.4. Kết luận assurance cần giới hạn

Có thể dùng trạng thái:

- **Effective in assessed scope:** có evidence đủ cho những claims và đường thực thi đã kiểm tra.
- **Partially effective:** một số control hoặc luồng đạt nhưng còn gap.
- **Ineffective:** có bằng chứng về hành vi không đáp ứng requirement.
- **Insufficient evidence:** thiếu coverage hoặc chất lượng evidence.
- **Exception approved:** residual risk được chấp nhận theo thẩm quyền, chưa phải control hiệu quả.
- **Not applicable:** có căn cứ đã được xác nhận không áp dụng.

Cần tránh câu “application secure” không có phạm vi. Nên nói: “Các kịch bản cross-tenant GET/EXPORT được kiểm tra trên build X tại integration đạt theo test plan Y; chưa đánh giá backup/analytics và operating evidence production.”

## 15. Metrics và cách diễn giải đúng

| Metric | Cách sử dụng | Hạn chế |
| --- | --- | --- |
| **Security requirement test coverage** | Tỷ lệ claims có tests phù hợp | Có test không nghĩa tests đủ mạnh |
| **Risk-weighted coverage** | Đường rủi ro cao được ưu tiên hơn đường ít nhạy cảm | Cần phương pháp trọng số minh bạch |
| **Negative authorization test coverage** | Số route/action có test truy cập trái scope | Thiếu alternate paths có thể bỏ sót bypass |
| **High-severity open findings** | Hỗ trợ release decision và ưu tiên fix | Severity cần xét exposure và risk thật |
| **Verified fix rate** | Findings đã retest đạt | Ticket closed không đủ |
| **Time to remediate/retest** | Độ trễ giảm rủi ro | Đếm từ mốc nhất quán |
| **Recurring vulnerability patterns** | Lỗi hệ thống hoặc đào tạo | Cần phân loại nguyên nhân gốc |
| **SAST/DAST signal quality** | False positives/true positives trong scope | Khác rule set và test coverage |
| **SCA inventory/SBOM coverage** | Biết những artifact/dependency đang dùng | SBOM không tự chứng minh không có vulnerability |
| **Pipeline security gate reliability** | Tỷ lệ gate hoàn tất và fail đúng policy | PASS do skip có thể tạo ảo giác |
| **Production drift** | Khác biệt giữa artifact/config đã test và runtime | Cần runtime validation |
| **Evidence freshness** | Test result còn phù hợp với build hiện tại | Một file report không thay cho test mới |

**Ví dụ giả định:** có 50 security requirements áp dụng trong một release; 38 có tests được review, 7 chưa kiểm tra và 5 đã có bằng chứng fail. **Verified test coverage = 38/50 = 76%** nếu định nghĩa numerator là 38 yêu cầu có test bằng chứng. Con số này **không có nghĩa hệ thống an toàn 76%**; 5 fail có thể là những yêu cầu nghiêm trọng nhất.

### 15.1. Không tối ưu sai chỉ số

Một nhóm có thể giảm số finding bằng cách tắt rule scanner, hạ severity hoặc skip integration test. Dashboard đẹp hơn nhưng assurance yếu hơn. Cần xem **cả độ bao phủ, chất lượng detection, nguy cơ còn lại, tỷ lệ retest và tình trạng exceptions**.

### 15.2. Đừng trộn các mẫu số

Số test PASS, số endpoint đã scan, số vulnerabilities và số requirements đã verify **không có mẫu số chung**. Khi tổng hợp, phải định nghĩa metric, scope, kỳ, data source và cách kiểm tra duplicate.

## 16. RACI và quản trị testing

| Vai trò | Trách nhiệm | Không được mặc định |
| --- | --- | --- |
| **Security architect** | Xác định threat, control objectives và test strategy | Có thiết kế là đã triển khai |
| **Product/risk owner** | Mức rủi ro và quyết định phát hành trong thẩm quyền | Có thể bỏ qua nghĩa vụ bắt buộc |
| **Engineering/app owner** | Thực thi controls, unit/integration tests, sửa finding | Merge PR là đã verified fix |
| **Security testing/AppSec** | Phương pháp test, scanner, manual review, triage | Scanner là nguồn chân lý duy nhất |
| **QA/test engineering** | Test infrastructure, functional/security regressions | Chỉ QA chịu trách nhiệm bảo mật |
| **Platform/SRE** | Pipeline, IaC, runtime config và observability | CI PASS đại diện production |
| **Identity/data owner** | Chính sách truy cập, secret và dữ liệu | Quyền kỹ thuật tự đúng với business policy |
| **Assurance/auditor** | Review tính đủ, độc lập và giới hạn evidence | Tự động chịu trách nhiệm sửa bug |
| **Incident response** | Contain, investigate, hậu kiểm khi phát hiện sự cố | Chờ vòng release trước khi xử lý |

RACI minh họa:

| Hoạt động | App owner | AppSec | Platform/SRE | Risk owner | Assurance |
| --- | --- | --- | --- | --- | --- |
| Định nghĩa security tests từ requirements | R | **A/R** | C | C | C |
| Viết authorization tests | **A/R** | C | I | I | C |
| Chạy SAST/SCA/secret scan trong CI | R | **A** | R | I | C |
| Test network/IaC/runtime config | C | C | **A/R** | I | C |
| Fix vulnerabilities | **A/R** | C | R khi liên quan | I | C |
| Review findings và evidence độc lập | C | C | C | I | **A/R** |
| Quyết định residual risk | C | C | C | **A/R** | I |
| Retest và xác minh deployment | **A/R** | R | R | I | C |

Trách nhiệm thực phải điều chỉnh theo tổ chức. Đối với findings nghiêm trọng, nên xem yêu cầu independence và separation of duties khi cùng nhóm phát hiện, sửa và phê duyệt đóng.

## 17. Các lỗi thường gặp trong security testing

### 17.1. Chạy scanner rồi tuyên bố hoàn tất

**Sai:** tool cho báo cáo “0 critical” nên release an toàn.

**Đúng:** xác định control claims, test các trust boundaries, business logic và coverage; review findings và gaps.

### 17.2. Chỉ chạy happy path

**Sai:** chỉ test customer có quyền xem order của mình.

**Đúng:** thêm wrong tenant, wrong role, missing identity, revoked membership và alternate endpoints.

### 17.3. Test âm bị từ chối vì nguyên nhân sai

**Sai:** request trả 403 do thiếu CSRF token, nhưng báo authorization PASS.

**Đúng:** kiểm tra authentication/authorization path và dùng positive control.

### 17.4. Mock quá nhiều trong integration test

**Sai:** MockMvc với repository mock được xem là bằng chứng DB RLS.

**Đúng:** unit test kiểm tra service, integration test kiểm tra DB policy, API test kiểm tra security chain và runtime phù hợp.

### 17.5. Không kiểm tra dependency exposure

**Sai:** mọi CVE match đều được xem exploitable hoặc mọi CVE bị suppress đều không có rủi ro.

**Đúng:** xác định artifact, phiên bản, reachability, exploit conditions và risk decision có thời hạn.

### 17.6. Dùng dữ liệu production bừa bãi

**Sai:** copy dữ liệu khách hàng lên laptop để chạy pentest.

**Đúng:** synthetic fixtures, approvals, môi trường và evidence được bảo vệ.

### 17.7. Quên test worker, cache và API phụ

**Sai:** bảo vệ GET chính nhưng bulk export, search hoặc async worker bỏ qua authorization.

**Đúng:** map toàn bộ data flow và test cross-boundary.

### 17.8. Fix xong không retest

**Sai:** PR merged hoặc ticket Done được xem là control effective.

**Đúng:** xác minh lỗi gốc không tái hiện trên artifact đã sửa, regression PASS và production rollout nếu thuộc scope.

### 17.9. CI job bị skip vẫn hiện màu xanh

**Sai:** dependency failure hoặc test timeout được coi PASS.

**Đúng:** trạng thái BLOCKED/INCOMPLETE và release gate có cơ chế xử lý.

### 17.10. Dùng kết quả test cũ cho cấu hình mới

**Sai:** thay identity provider, feature flag hoặc policy nhưng dùng report trước thay đổi.

**Đúng:** trigger retest và runtime validation theo changed trust boundaries.

### 17.11. Không xử lý false positives và false negatives

**Sai:** đóng tất cả alerts là false positive không có căn cứ, hoặc tin scanner phát hiện toàn bộ lỗ hổng.

**Đúng:** triage dựa trên bằng chứng, tuning rules, kiểm tra detection coverage và blind spots.

### 17.12. Đánh đồng security testing với pentest

**Sai:** chỉ pentest mỗi năm, không có security unit/integration tests và CI gates.

**Đúng:** continuous testing và periodic risk-based manual assessments bổ trợ nhau.

### 17.13. Chỉ đo số bug, bỏ qua thời gian phơi nhiễm

**Sai:** giảm số lượng findings dù một critical mở quá lâu.

**Đúng:** theo dõi impact, age, exposure, mitigation, closure evidence và residual risk.

### 17.14. Kết luận vượt phạm vi evidence

**Sai:** 10 API tests PASS → toàn bộ hệ thống “secure”.

**Đúng:** ghi tested routes, user roles, build, environment, exclusions và confidence.

## 18. Checklist thực hành Security testing

- [ ] Đã xác định asset, risk tier, data classification và threat scenarios.
- [ ] Có architecture/DFD, trust boundaries và security requirements.
- [ ] Mỗi yêu cầu quan trọng có test objective, security claim và owner.
- [ ] Test plan phân biệt positive, negative, boundary, bypass và failure modes.
- [ ] Có tests cho authentication, session, MFA/recovery nếu thuộc phạm vi.
- [ ] Có object-level và function-level authorization tests.
- [ ] Đã kiểm tra cross-tenant, cross-user, bulk/export và delegated access.
- [ ] Đã xem input validation, injection, output encoding, upload, SSRF và redirect phù hợp.
- [ ] Có SAST và code review cho vùng code quan trọng.
- [ ] Có SCA/dependency inventory, SBOM nếu cần và vulnerability triage.
- [ ] Có secret scanning cho repo, history, image, artifact và logs theo scope.
- [ ] Có IaC/cloud/container/security configuration tests.
- [ ] DAST/IAST/fuzz/manual pentest được chọn theo threat, scope và sự cho phép.
- [ ] Có tests cho business logic, replay, state transition, retry và concurrency.
- [ ] Có thử fail-safe khi identity/policy/secret service unavailable.
- [ ] Test fixtures không lộ dữ liệu cá nhân/secret production.
- [ ] CI gate phân biệt PASS, FAIL, NOT RUN và BLOCKED.
- [ ] Phần bị skip hoặc lỗi tool không được tự tính là PASS.
- [ ] Findings có requirement, impact, evidence, owner, due date và severity/risk.
- [ ] Exception/risk acceptance có approver, điều kiện, expiry và compensating controls.
- [ ] Retest xác minh fix trên build/deployment phù hợp.
- [ ] Evidence gắn tool/rule version, commit, artifact digest và environment.
- [ ] Có runtime configuration verification và drift monitoring khi áp dụng.
- [ ] Log/test report được bảo vệ, không lưu raw PII hoặc token không cần thiết.
- [ ] Có metrics về coverage, open risks, retest và evidence freshness.
- [ ] Có trigger test lại khi đổi identity, authorization, API, dependency, data flow và config.
- [ ] Kết luận assurance ghi scope, limitations, confidence và residual risk.

Checklist giúp kiểm soát quy trình. Đánh dấu đầy đủ mục **không thay thế kết quả kiểm thử và đánh giá bằng chứng**.

## 19. Câu hỏi tự kiểm tra

1. Security testing khác security assurance ở đâu?
2. Vì sao functional test trả 200 không chứng minh authorization an toàn?
3. Khi nào chọn SAST, DAST, IAST hoặc manual review?
4. Vì sao SCA match CVE chưa đủ để khẳng định exploitable?
5. Secret scanning cần kiểm tra những nguồn dữ liệu ngoài source code?
6. Một negative test trả 403 có luôn chứng minh policy đúng không?
7. Security test case cần ghi những metadata nào để phục vụ audit?
8. Vì sao phải có positive tests đi kèm negative authorization tests?
9. Trong multi-tenant Orders API, test nào xác minh BOLA?
10. Unit test Mockito có đủ để xác nhận database RLS không? Vì sao?
11. Một worker dùng quyền service account rộng có thể tạo confused deputy như thế nào?
12. Vì sao một race condition có thể không xuất hiện trong lần thử đầu?
13. Thời điểm nào cần kiểm tra idempotency và replay protection?
14. Tại sao CI scan PASS không tự chứng minh runtime production an toàn?
15. Nếu một scanner không chạy do timeout, release gate nên xử lý trạng thái nào?
16. Mô hình threat cần được dùng thế nào để ưu tiên test?
17. Khi phát hiện một secret trong Git history, vì sao xóa dòng code là chưa đủ?
18. Khi nào pentest có thể tạo rủi ro availability và cần điều kiện gì trước khi chạy?
19. Bằng chứng nào giúp đóng finding BOLA sau khi sửa?
20. Những yếu tố nào quyết định severity/risk thay vì chỉ tên CVE?
21. Tại sao exception được phê duyệt không đồng nghĩa security control đạt?
22. Nếu test coverage 76%, có thể suy ra hệ thống an toàn 76% không? Vì sao?
23. Những thay đổi nào trong Secure SDLC nên kích hoạt retest?
24. Làm sao phân biệt evidence gap, design gap và implementation gap?
25. Hãy thiết kế ba security claims và một negative test cho mỗi claim ở luồng refund.

## 20. Tổng kết

**Security testing** là quá trình kiểm chứng có chủ đích xem hệ thống có thực thi các **security requirements và controls** trước những threat scenarios liên quan hay không. Một chương trình tốt kết hợp **security tests ở unit, integration, API, runtime với SAST, SCA, secret scanning, DAST/IAST, IaC/container checks, fuzzing và manual review** theo mức rủi ro; đồng thời bao phủ **authentication, authorization, business logic, crypto, secrets, data protection, cấu hình, dependency và supply chain**. Giá trị thực của kiểm thử nằm ở **security claims đo được, test dương/âm và bypass cases, evidence có nguồn gốc, findings được triage đúng, remediation và retest trên artifact thực tế**. Trong **SECURITY_SECURITY_ASSURANCE**, không tuyên bố “an toàn” chỉ vì tool báo xanh; kết luận phải chỉ rõ **phạm vi, thời điểm, build, environment, độ bao phủ, giới hạn và residual risk**, và được cập nhật liên tục khi hệ thống thay đổi.

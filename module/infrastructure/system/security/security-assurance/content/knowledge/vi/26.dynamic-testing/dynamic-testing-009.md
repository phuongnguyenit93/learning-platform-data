# Tích hợp pipeline: Đưa kiểm thử động vào CI/CD để tạo bằng chứng Security Assurance

## 1. Tích hợp pipeline trong Dynamic Testing là gì?

**Tích hợp kiểm thử động vào pipeline** là quá trình biến những phép kiểm tra bảo mật cần **ứng dụng hoặc dịch vụ thực sự đang chạy** thành các bước có thể lặp lại, có kiểm soát và có bằng chứng trong vòng đời **Continuous Integration/Continuous Delivery (CI/CD)**.

Những kiểm thử này có thể bao gồm:

- **Dynamic Application Security Testing (DAST):** quan sát và tương tác với ứng dụng qua giao diện thực thi như HTTP để tìm các dấu hiệu lỗi bảo mật.
- **API security testing:** kiểm tra authentication, authorization, object-level access, schema, input handling và business invariants.
- **Security regression testing:** tự động xác nhận lỗi đã sửa không tái phát.
- **Integration security testing:** xác nhận bảo vệ qua gateway, identity provider, database, cache, queue và external integrations.
- **Interactive Application Security Testing (IAST):** phối hợp dữ liệu runtime/instrumentation với các request thử nghiệm, nếu công cụ và mô hình triển khai hỗ trợ.
- **Controlled fuzzing/fault injection:** thử input bất thường và lỗi phụ thuộc trong môi trường được phép, có giới hạn nguồn lực.
- **Post-deployment verification:** kiểm tra các security properties trên artifact và cấu hình thực sự được triển khai.

Mục tiêu không chỉ là “cho một scanner chạy sau khi build”. Tích hợp đúng cần trả lời:

1. **Đang kiểm tra security requirement nào?**
2. **Ứng dụng được kiểm tra ở phiên bản và môi trường nào?**
3. **Ai hoặc điều gì được phép thực hiện những request thử nghiệm?**
4. **Những endpoints, roles, tenants và flows nào được bao phủ?**
5. **Làm sao ngăn test tạo hậu quả không mong muốn?**
6. **Kết quả PASS, FAIL, BLOCKED và NOT_RUN được hiểu thế nào?**
7. **Khi có finding, ai đánh giá và cần bằng chứng nào để đóng?**
8. **Làm sao biết production chạy đúng artifact đã kiểm thử?**

Trong module **SECURITY_SECURITY_ASSURANCE**, tích hợp dynamic testing phải nối được:

**Security objective → Threat/risk → Requirement → Test scenario → Deployed build → Actual test result → Finding/decision → Remediation/retest → Assurance conclusion.**

> **Một pipeline có trạng thái xanh không đồng nghĩa hệ thống an toàn.** Nó chỉ có giá trị bảo đảm trong phạm vi những test thật sự đã chạy, những thuộc tính được kiểm tra, các giả định và phiên bản/cấu hình được chứng minh.

### 1.1. Ví dụ mở đầu

Một ứng dụng SaaS **Orders API** viết bằng Java/Spring Boot chứa đơn hàng của nhiều tenant. Pipeline của nhóm hiện tại:

1. Compile.
2. Run unit tests.
3. Build container.
4. Deploy.
5. Run HTTP health check.
6. Báo SUCCESS.

Pipeline này có thể không phát hiện được:

- User tenant A đọc được order của tenant B.
- Export worker trả dữ liệu vượt quyền.
- Gateway từ chối request nhưng backend trực tiếp vẫn chấp nhận.
- Webhook giả mạo thay đổi trạng thái payment.
- Policy service lỗi khiến API fail-open.
- Cookie session thiếu các thuộc tính phù hợp.
- Application ghi access token vào logs.
- Một endpoint mới được deploy nhưng chưa từng được quét.

**Tích hợp dynamic security testing** cần đưa các security invariants này thành **test cases, test identities, environment requirements và release gates** thay vì chỉ thêm một dòng gọi scanner.

### 1.2. Pipeline là một cơ chế assurance liên tục

Khi làm tốt, mỗi thay đổi quan trọng đều có chuỗi:

- Pull request: biết thay đổi đã ảnh hưởng những boundaries nào.
- Build: tạo artifact có provenance và identity.
- Deploy test: chạy artifact trong môi trường phù hợp.
- Dynamic test: gửi các request được phép và kiểm tra expected behavior.
- Analyze: phân biệt finding thật, false positive và evidence gap.
- Gate: quyết định cho phép đi tiếp hay giữ lại.
- Promote: dùng artifact đã được kiểm thử.
- Runtime check: xác minh đúng image/config hiện diện.
- Monitor: phát hiện drift và khi cần chạy lại.

Điều này biến kiểm thử động từ hoạt động **thỉnh thoảng và thủ công** thành một nguồn bằng chứng có thể lặp lại cho phát triển và vận hành.

## 2. Dynamic testing khác Static Analysis, SCA và kiểm thử thông thường như thế nào?

| Hoạt động | Quan sát gì? | Strength | Blind spot |
| --- | --- | --- | --- |
| **SAST** | Source/bytecode và control/data-flow models | Phát hiện code patterns sớm, có source location | Runtime identity, network/config và business paths có thể bị bỏ sót |
| **SCA** | Software components/dependencies/advisories | Xác định vulnerable packages, supply-chain risks | Không tự chứng minh exploitability hay sửa lỗi logic ứng dụng |
| **DAST** | Behavior qua interface của ứng dụng đang chạy | Tìm dấu hiệu từ bên ngoài, thấy effective runtime config | Khó thấy code không reachable qua các requests đã gửi |
| **API security tests** | Giao thức/API contract, identity, resource access | Kiểm tra authn/authz và invariants có chủ đích | Chỉ bao phủ identities, resources và scenarios được tạo |
| **IAST** | Request runtime và instrumentation | Có thêm ngữ cảnh ứng dụng, call/trace trong scope | Phụ thuộc instrumentation, coverage và support của engine |
| **Fuzzing** | Nhiều inputs/edge conditions | Tìm parser, validation và state bugs | Tốn tài nguyên; coverage/oracle khó; có thể gây hại |
| **Manual penetration testing** | Chuyên gia kết hợp exploration/logic | Phát hiện các chain, abuse cases phức tạp | Point-in-time; khó chạy thường xuyên như CI |
| **Infrastructure/IaC scan** | Templates/configurations | Bắt lỗi khai báo trước deploy | Manifest không chứng minh effective runtime enforcement |
| **Security regression test** | Behavior cụ thể của lỗi đã xác nhận | Có oracle rõ và chống tái phát | Không phát hiện mọi lớp lỗi mới |

Dynamic testing **không thay thế** static analysis, threat modeling, code review hoặc vulnerability management. Các kỹ thuật này nên được **liên kết theo requirement và evidence**, để tận dụng điểm mạnh của từng phương pháp.

### 2.1. Sự khác biệt giữa DAST scanner và bài kiểm thử security invariant

Một DAST scanner có thể nhận ra response thiếu header, cookie flag không phù hợp hoặc biểu hiện injection theo model của nó.

Nhưng với requirement:

> User A chỉ được đọc order thuộc tenant A.

Scanner thường **không thể tự suy ra toàn bộ business semantics**, vì cần biết:

- Hai tài khoản thuộc những tenant nào.
- Order nào thuộc tenant nào.
- Quyền hợp lệ của từng role.
- API có được trả 403 hay 404 theo policy.
- Bulk export, cache và worker có ảnh hưởng resource đó không.

Vì vậy pipeline nên kết hợp **general DAST scanning** và **purpose-built authenticated API security tests**.

### 2.2. “Dynamic” không đồng nghĩa kiểm thử production

Dynamic testing có thể chạy trên:

- Local service + database giả lập phù hợp.
- Integration environment.
- Ephemeral preview environment theo pull request.
- Staging/pre-production.
- Canary environment.
- Production với phép kiểm tra **an toàn, được cho phép và không phá hoại**.

Một scanner chủ động sinh nhiều request hoặc thử payload nguy hiểm không nên tự động chạy vào production chỉ vì production là môi trường “thật”. Scope, approval và safeguards phải tương ứng.

## 3. Mô hình rủi ro khi tích hợp dynamic testing

### 3.1. Rủi ro khi thiếu kiểm thử động

| ID | Threat scenario | Hậu quả | Dynamic evidence cần |
| --- | --- | --- | --- |
| **DYN-01** | Authenticated user đọc tài nguyên tenant khác | Data disclosure | Cross-tenant API negative tests |
| **DYN-02** | Public endpoint xử lý input không an toàn | Injection/XSS/SSRF | Controlled DAST và targeted tests |
| **DYN-03** | Service chỉ xác thực ở gateway, direct route bypass | Authentication bypass | Network/API route verification |
| **DYN-04** | Session/cookie policy bị cấu hình sai tại runtime | Hijacking/session misuse | Effective HTTP/auth flow tests |
| **DYN-05** | Policy engine timeout dẫn tới allow-all | Privilege escalation | Fault-injection test trong lab |
| **DYN-06** | Webhook replay tạo side effect nhiều lần | Financial integrity | Signed/invalid/replay tests |
| **DYN-07** | Export worker tin tenant ID trong message | Cross-tenant disclosure | Worker/event integration tests |
| **DYN-08** | API release thêm endpoint mới không có test | Uncovered attack surface | Endpoint inventory và coverage gate |
| **DYN-09** | Security tests chạy build A, deploy build B | False assurance | Artifact digest/provenance verification |
| **DYN-10** | Scanner job lỗi nhưng pipeline xanh | Evidence gap bị che | Gate status completeness checks |

### 3.2. Rủi ro do chính scanner tạo ra

Một pipeline DAST có thể gây rủi ro nếu:

- Gửi active probes vào dịch vụ không được phép.
- Dùng URL target lấy trực tiếp từ untrusted pull request.
- Quét production bằng tài khoản admin không có giới hạn.
- Sinh dữ liệu giả rồi vô tình gửi email/tạo thanh toán thật.
- Kích hoạt delete/refund/provisioning endpoints với dữ liệu thật.
- Tạo lượng requests làm nghẽn API, rate limiter hoặc database.
- Ghi tokens, cookies, PII và request/response payload vào report public.
- Chạy scanner container với quyền runner/cloud không cần thiết.
- Cho code từ PR không tin cậy truy cập production secrets.
- Cho DAST report từ nguồn chưa xác minh điều khiển release gate.
- Dùng report/outbound callbacks có thể gọi ra external domains ngoài scope.

**Scanner cũng là phần mềm có quyền và network access.** Nó cần threat model, identity, least privilege, trusted image, secret isolation, egress policy, audit và cập nhật như mọi thành phần supply chain khác.

### 3.3. Security boundary của pipeline

Trong thiết kế tích hợp cần nhận diện tối thiểu:

- Developer/PR → CI runner.
- Source/metadata → build artifact.
- CI runner → test environment.
- Scanner → target HTTP/API.
- CI secrets → test accounts hoặc identity provider.
- Test service → mock/sandbox database và vendor.
- Report/artifact store → reviewer/dashboard.
- Scan result → release policy decision.
- Tested artifact → promoted/deployed artifact.

Một đường đáng lo ngại:

**Untrusted PR → modifies scan target → scanner uses internal network and privileged credentials**.

Không để untrusted change tự quyết định đích quét hoặc nhận production tokens. Tách workflows cho untrusted submissions và privileged promotion.

## 4. Mục tiêu kiểm soát và yêu cầu có thể xác minh

### 4.1. Security objectives

- **DYN-OBJ-01:** Các release thuộc scope được kiểm thử động trên artifact/config tương ứng.
- **DYN-OBJ-02:** Những abuse cases và threat scenarios quan trọng có positive/negative tests với oracle rõ.
- **DYN-OBJ-03:** Scanner và test identities chỉ hoạt động trong approved targets và permissions.
- **DYN-OBJ-04:** Pipeline phát hiện và không che giấu các test failures, missing results, tool crashes hoặc partial scans.
- **DYN-OBJ-05:** Phạm vi authenticated APIs, roles, tenants và endpoints được kiểm kê và theo dõi coverage.
- **DYN-OBJ-06:** Findings được triage, có ownership, priority và remediation/retest.
- **DYN-OBJ-07:** Test data và scan evidence được bảo vệ, không làm lộ bí mật hoặc dữ liệu khách hàng.
- **DYN-OBJ-08:** Release gate dựa trên policy, risk, confidence và exceptions được phê duyệt.
- **DYN-OBJ-09:** Deployment có thể truy vết đến artifact và security test run đã được phê duyệt.
- **DYN-OBJ-10:** Quy trình được cải tiến khi có changes, incident hoặc phát hiện coverage gap.

### 4.2. Security requirements minh họa

**DYN-REQ-01 — Scoped testing**

> Scanner chỉ được gửi requests tới allowlisted targets, routes và environments thuộc scope đã được xác minh; active tests cần authorization, rate/traffic controls và stop conditions tương ứng.

**DYN-REQ-02 — Authenticated coverage**

> Với các APIs có authorization quan trọng, pipeline phải chạy security tests dùng identities/roles/tenants khác nhau và xác minh deny khi không có quyền, không chỉ kiểm tra unauthenticated endpoints.

**DYN-REQ-03 — Result completeness**

> Một test NOT_RUN, BLOCKED, scanner timeout hoặc report thiếu không được tự chuyển thành PASS; release gate phải thể hiện trạng thái thiếu bằng chứng và quyết định có thẩm quyền.

**DYN-REQ-04 — Artifact evidence**

> Mỗi kết quả dynamic test phải liên kết tới commit, build, deployed artifact identity, environment/config revision và test suite version trong phạm vi phù hợp.

**DYN-REQ-05 — Data protection**

> Test credentials, tokens và data fixtures phải được tách production khi có thể, cấp quyền tối thiểu, kiểm soát retention/redaction của logs và artifacts.

**DYN-REQ-06 — Finding closure**

> Một finding chỉ được xem là verified fixed khi có evidence từ targeted retest trên build/environment áp dụng, cùng xác nhận các alternate paths liên quan theo acceptance criteria.

**DYN-REQ-07 — Continuous reassessment**

> Khi API, authorization model, deployment, scanner rules hoặc threat intelligence thay đổi, nhóm sở hữu phải xem lại phạm vi và các test cần chạy.

Các con số rate, SLA hoặc thời gian quan sát là **policy parameters của tổ chức**, không tự đặt một chuẩn cố định trong bài.

## 5. Thiết kế pipeline security testing theo tầng

### 5.1. Shift-left và shift-right

- **Shift-left:** unit/security integration tests sớm ở PR, giúp developer sửa nhanh.
- **Pre-release:** DAST trên ứng dụng thực được triển khai trong sandbox/staging; tập trung integration và regression.
- **Shift-right:** runtime verification, monitoring và periodic permitted scans sau release.
- **Continuous assurance:** kết nối kết quả xuyên các giai đoạn để thấy được coverage, drift và effectiveness.

Không có nghĩa cần chạy **full active DAST** trên mỗi commit. Chọn lịch và độ sâu theo risk, cost và khả năng an toàn.

### 5.2. Ma trận kiểm thử theo điểm kích hoạt

| Trigger | Test phù hợp | Đặc điểm |
| --- | --- | --- |
| Developer local / PR | Unit authorization tests, contract tests, targeted API negative tests | Nhanh, feedback cụ thể |
| Merge main | Integration security suite, baseline DAST passive, SAST/SCA | Nhiều hệ thống hơn |
| Build release | Artifact identity + full defined security regression + scoped DAST | Có release gate |
| Staging promotion | Authenticated API coverage, controlled active DAST, end-to-end | Environment gần production |
| High-risk architecture change | Focused threat-driven dynamic tests và manual review | Cần thiết kế riêng |
| Dependency/security patch | Targeted vulnerability verification và regression suite | Chống tái phát |
| Scheduled scan | Broader endpoint coverage, discovery/DAST theo authorization | Tìm drift/missed paths |
| Post-deploy / canary | Safe runtime negative tests, identity, config, audit | Không gây tác động ngoài scope |
| Incident/advisory | Targeted tests + containment/IR workflow | Không chờ full scan nếu cần phản ứng khẩn |

### 5.3. Các job logic

Một pipeline mô hình có các jobs:

1. **Policy/intake:** xác định change risk và required test matrix.
2. **Build:** tạo artifact có identity.
3. **Prepare environment:** dựng sandbox/ephemeral deployment và dependent services.
4. **Provision identities/data:** test accounts, tenant fixtures, mock providers.
5. **Preflight target:** xác minh hostname, TLS, route, artifact, health và scope.
6. **Security tests:** API regression và DAST theo mode đã duyệt.
7. **Validate results:** kiểm tra scan completion, coverage, report integrity.
8. **Triage/gate:** áp policy dựa trên findings và status.
9. **Publish evidence:** report, logs đã redacted, versions và decision.
10. **Teardown:** thu hồi tokens, xóa fixtures, hủy ephemeral resources.
11. **Promote/deploy:** chỉ artifact đã được phê duyệt.
12. **Runtime check:** đối chiếu digest, config và targeted tests/monitoring.

### 5.4. Sơ đồ luồng

~~~mermaid
flowchart TD
    A["Source change / Security finding"] --> B["Threat and test-scope selection"]
    B --> C["Build immutable artifact"]
    C --> D["Deploy isolated target"]
    D --> E["Provision synthetic data and scoped identities"]
    E --> F{"Target identity, readiness, safety preflight OK?"}
    F -- "No" --> X["BLOCKED: environment or scope issue"]
    F -- "Yes" --> G["API security regression"]
    G --> H["Approved DAST passive / active jobs"]
    H --> I["Check completion, coverage, findings"]
    I --> J{"Required evidence and gates satisfied?"}
    J -- "No" --> K["Triage / fix / exception decision"]
    K --> C
    J -- "Yes" --> L["Publish protected test evidence"]
    L --> M["Promote same approved artifact"]
    M --> N["Verify deployed digest and safe runtime tests"]
    N --> O["Continuous monitoring / reassessment"]
    E --> P["Cleanup after tests"]
    H --> P
~~~

Cần có đường cleanup **ngay cả khi test thất bại**, đồng thời giữ evidence trước khi dọn môi trường. Thực tế job dependencies và failure handling cần được thiết kế trong hệ thống CI cụ thể.

## 6. Phạm vi: biết rõ đang kiểm thử cái gì

### 6.1. Inventory endpoints và assets

Một hồ sơ scope nên gồm:

- Service name, owner, environment và risk tier.
- Canonical hostname và approved base URL.
- Exact routes/API operations.
- Protocols: HTTP, WebSocket, gRPC, GraphQL, webhooks...
- Authenticated roles và tenant boundaries.
- Data classification và side-effecting operations.
- Dependent services và external destinations.
- Current artifact digest và config revision.
- Môi trường chứa synthetic hay production data.
- Scanner allowlist và denylist.
- Rate/concurrency/time budgets.
- Contacts, stop conditions, emergency disable.
- Excluded endpoints cùng rationale/owner.

**Không lấy một URL từ comment/PR rồi cho scanner tự đi theo mọi link**. Kiểm soát scope ở cả CI config và network/runtime.

### 6.2. API specification làm input

OpenAPI hoặc tài liệu API có thể hỗ trợ:

- Endpoint discovery.
- Operation IDs.
- Authentication requirements.
- Input schemas và constraints.
- Positive/negative test generation.
- Coverage comparison giữa expected vs observed operations.

Nhưng:

- Spec có thể lỗi thời.
- Một số internal/legacy endpoints không được khai báo.
- API operation semantics không thể suy hết từ schema.
- Spec không tự tạo users/tenants và resource ownership.
- Có endpoints chỉ có khi feature flag bật.
- Untrusted spec có thể chứa external server URLs không phù hợp.

Cần **spec diff review + runtime route inventory + manual threat mapping** cho operations quan trọng.

### 6.3. Crawl/spider có giới hạn

Crawling web UI có thể tìm routes nhưng dễ bỏ sót:

- API calls cần user interaction.
- GraphQL operations.
- MFA/session-protected pages.
- Admin-only actions.
- Webhook endpoints.
- Async workflow không có link.
- Feature-flagged routes.
- Multi-step business state machines.

Do đó **crawl coverage không bằng API/security coverage**. Cần test scripts hoặc schema-aware integration để đưa scanner đến flows quan trọng.

### 6.4. Scope coverage theo nhiều chiều

| Chiều coverage | Ví dụ |
| --- | --- |
| Endpoint | 95/110 operations được exercise |
| Role | customer, tenant admin, support |
| Tenant | A/B, cross-tenant cases |
| Auth state | anonymous, valid, expired, revoked |
| Resource | owner, other-user, other-tenant, missing |
| Workflow | create, read, edit, export, refund |
| Error | timeout, malformed token, policy unavailable |
| Data class | public, internal, confidential |
| Integration | cache, DB, worker, provider |
| Deployment | staging image, production canary |
| Control | input validation, authn, authz, audit, rate limits |

Không có một tỷ lệ coverage duy nhất đại diện chính xác cho mọi chiều. Đặc biệt **90% endpoint coverage không chứng minh 90% security requirements đã được kiểm chứng**.

## 7. Chuẩn bị môi trường kiểm thử

### 7.1. Các mô hình môi trường

| Mô hình | Lợi ích | Rủi ro/giới hạn |
| --- | --- | --- |
| Local container/test stack | Nhanh, dễ tái tạo | Không đủ network/IAM parity |
| Shared integration | Có dependencies thực | Dữ liệu/test collisions, resource contention |
| Ephemeral preview per PR | Isolation, dễ trace artifact | Cost, lifecycle, secret provisioning |
| Staging/pre-production | Gần production hơn | Vẫn khác scaling, IdP, providers, data |
| Canary | Quan sát runtime thật một phần | Traffic/identity scope nhỏ, tác động production |
| Production safe verification | Đúng deployment cuối | Phải tránh destructive testing |

### 7.2. Environment parity

Các khác biệt cần ghi:

- Identity provider issuer/audience, session/MFA, membership.
- API gateway, reverse proxy, WAF và rate limits.
- NetworkPolicy, ingress/egress, DNS, mTLS.
- Database engine/role/RLS, connection pool.
- Cache, queue, worker và async retries.
- Feature flags và default configurations.
- Secrets/KMS/key scopes.
- Container image/sidecar/runtime.
- Data volume và tenancy model.
- External providers, webhook signing, callback behavior.
- Logging/metrics/audit pipeline.
- TLS certificates và domain routing.

**Cùng source commit nhưng staging khác network/IAM không đủ chứng minh production boundary**. Cần đưa parity limitations vào kết luận.

### 7.3. Dữ liệu test độc lập

Dùng test fixtures có:

- Account và tenant IDs rõ, không trùng production.
- Resources với owner relationships xác định.
- Sample confidential data **giả**, không lấy PII thật.
- Những states cần thiết cho workflow (PAID, REFUNDED...).
- Idempotency keys và cleanup paths.
- Timestamp và expiry phù hợp token/session tests.
- Dedicated S3/object storage namespace hoặc bucket sandbox.
- Mock/sandbox email, payment, webhook và notification providers.
- Transaction rollback/reset và data retention.

Đặc biệt với các tests tạo đơn hàng hoặc refund, phải chặn outbound real-world side effects để không gửi email/thanh toán thật.

### 7.4. Setup/teardown idempotent

Một test chạy lại cần:

- Có thể tái tạo fixture ở cùng semantic state.
- Không phụ thuộc thứ tự từ test khác trừ khi workflow cố ý.
- Không để dữ liệu/test tokens lâu hơn cần thiết.
- Dọn artifacts và identities sau test.
- Không xóa dữ liệu không thuộc namespace đã cấp.
- Có cleanup ngay cả khi scanner timeout.
- Không để test lỗi phá môi trường chung.
- Giữ minimal protected evidence trước khi cleanup.

Để tránh race, tạo namespace/tenant/fixture riêng theo **test run ID** và dùng cleanup theo owner/run label, không xóa wildcard quá rộng.

## 8. Test identities, authentication và authorization coverage

### 8.1. Authenticated testing là bắt buộc cho nhiều hệ thống

Không thể đánh giá BOLA/BFLA nếu scanner chỉ có quyền anonymous. Với SaaS, nên có:

- Anonymous caller.
- Customer user A thuộc tenant A.
- Customer user B thuộc tenant B.
- Tenant admin A có scoped privileges.
- Support user với case/approval scope.
- Service/workload test identity nếu cần.
- Expired/invalid/revoked identity fixtures.

Không dùng một tài khoản superadmin cho mọi scan, vì nó có thể **bypass authorization** và làm bỏ sót findings thực tế.

### 8.2. Secrets và token cấp cho scanner

- Test-only identity, least privilege.
- Không dùng production admin credentials khi có thể tránh.
- Short-lived token hoặc dynamic provisioning.
- Đưa qua CI secret mechanism được bảo vệ.
- Mask headers và cookies trong logs/report.
- Không echo environment variables nhạy cảm.
- Không upload HAR chứa Authorization header ra nơi public.
- Revoke token khi scan kết thúc hoặc lỗi.
- Không cung cấp secret cho untrusted fork/PR.
- Audit token issuer, audience, scope và usage.

Một token được cấp đúng lúc nhưng chạy với untrusted scanner image vẫn tạo risk.

### 8.3. Session handling

DAST cần xử lý:

- Login flow, refresh token và expiry.
- CSRF token/challenge và cookies.
- Session idle timeout.
- MFA hoặc step-up flows bằng cơ chế thử nghiệm được phê duyệt.
- Logout và revocation.
- Role changes trong lúc scan.
- Race giữa concurrent sessions.
- Account lockout và rate limit không được vô hiệu hóa một cách không kiểm soát.

Nếu tool mất session giữa scan, hàng loạt 401/302 có thể khiến **apparent endpoint coverage** cao nhưng thực tế không vào được protected operations.

### 8.4. Test oracle cho authorization

Cần biểu diễn chính xác:

**Subject + Action + Resource + Context → Expected access decision**.

Ví dụ:

| Caller | Operation | Resource | Expected |
| --- | --- | --- | --- |
| User A | GET order | Order A | Allow |
| User A | GET order | Order B (tenant B) | Deny/no disclosure |
| User A | Export | Tenant A selected orders | Allow theo role/policy |
| User A | Export | Contains tenant B orders | Deny/no disclosure |
| Tenant admin A | Edit tenant setting | Tenant B | Deny |
| Anonymous | GET private order | Any tenant | Deny |
| Revoked user A | GET order A | After revocation propagation | Deny theo policy |
| Support without approved case | Read tenant B data | Tenant B | Deny |

Đừng kiểm tra duy nhất HTTP status: một response 200 chứa data của tenant B là nguy hiểm, nhưng một 404 có thể vẫn tiết lộ thông tin qua body/timing hoặc logs tùy threat.

### 8.5. Phân quyền scan và business permissions

**Scanner account** không cần mọi quyền nghiệp vụ. Có thể dùng nhiều identities theo persona, với data fixtures tương ứng.

Một active scanner tự động gửi payload vào endpoint **DELETE /orders** hoặc **POST /refunds** có thể có side effects. Hãy:

- Đưa operations rủi ro vào denylist của active scan.
- Viết targeted integration tests có controlled fixtures.
- Hoặc dùng sandbox provider/data có cơ chế cleanup.
- Yêu cầu explicit approval nếu chạy dynamic checks có khả năng tạo tác động.
- Giới hạn request methods/routes phù hợp.

## 9. Các chế độ DAST và mức độ an toàn

### 9.1. Passive scanning

Passive scanning quan sát request/response và phân tích dấu hiệu mà không chủ động tạo payload tấn công riêng từ mỗi finding class.

Có thể phù hợp với:

- Security headers.
- Cookie attributes.
- Information disclosure trong response.
- Cache/control headers.
- Redirect patterns.
- Content types.
- Một số authentication/session indicators.

Nhưng **passive** vẫn cần gửi traffic để thu response nếu kết hợp spider hoặc test scripts; không nên hiểu “passive scan” đồng nghĩa hoàn toàn không có request.

### 9.2. Active scanning

Active scan có thể gửi input/requests khác thường để kiểm tra phản ứng ứng dụng.

Hữu ích để tìm:

- Injection candidates.
- Misconfiguration và unsafe endpoint behavior.
- Một số authorization/error handling issues khi có identities phù hợp.
- Input validation và exception-handling gaps.

Rủi ro:

- Thay đổi dữ liệu.
- Kích hoạt rate limits.
- Tạo logs/alerts lớn.
- Gây quá tải hoặc crash parser.
- Gọi external services.
- Quét nhầm URL không thuộc scope.
- Làm lệch test data giữa các jobs.

Do đó cần **approval, environment isolation, allowlist, exclusions, request budgets và stop conditions**.

### 9.3. Targeted security regression

Một security regression test được thiết kế với:

- Known precondition.
- Input an toàn và có kiểm soát.
- Expected behavior.
- Actual assertion về cả response và side effect.
- Cleanup.
- Evidence.

Ví dụ test user A không truy cập order B có độ giải thích cao và thường hiệu quả hơn một scanner cố tự phát hiện BOLA qua mọi UUID.

### 9.4. Fuzzing trong pipeline

Fuzzing có thể phát hiện parser/validation/state bugs, nhưng cần:

- Corpus hoặc generators an toàn.
- Schema-aware inputs khi có ích.
- Time/resource budget.
- Crash/timeout oracle.
- Sanitizers và instrumentation tương thích.
- Target không có external destructive side effects.
- Dedup/triage crash.
- Deterministic reproduction seeds khi phù hợp.

Có thể đặt fuzzing kéo dài vào **scheduled/isolated job**, còn PR job chạy smoke corpus nhỏ. Không yêu cầu mọi PR chạy không giới hạn thời gian.

### 9.5. IAST trong pipeline

IAST có thể bổ sung:

- Call stack và function/source location.
- Request-to-code correlation.
- Runtime data-flow visibility.
- Ngữ cảnh sanitizer/sink từ instrumentation.

Nhưng cần:

- Kiểm tra agent trust/provenance.
- Java/runtime support.
- Performance overhead và data capture policy.
- Không thu raw secrets/PII quá mức.
- Môi trường và versions được ghi.
- Test traffic đủ exercise paths.
- Scope không kết luận vượt coverage của instrumentation.

IAST không tự tạo business authorization oracle cho mọi use case.

## 10. Kết hợp DAST với API contract và business security testing

### 10.1. Contract testing

API contract test xem:

- Route/method/status codes.
- Request/response schema.
- Input field constraints.
- Authentication requirements.
- Backward compatibility.
- Error shapes và data exposure.
- Content type và caching behavior.

Nhưng **schema hợp lệ chưa chứng minh request được authorization**. Cần thêm tests về actor và resource ownership.

### 10.2. Object-level và function-level authorization

**BOLA:** người dùng thao tác object không thuộc quyền.

**BFLA:** người dùng gọi function/operation không được phép.

Ví dụ:

- User A đọc order B bằng UUID khác.
- User thường gọi admin endpoint **/admin/users**.
- Tenant admin A đổi policy của tenant B.
- Support nhân viên không có case vẫn export hồ sơ khách hàng.

Test matrix cần **cross-user, cross-tenant và cross-role**, không chỉ login thành công.

### 10.3. Business state machines

Một endpoint refund có thể trả mã HTTP hợp lệ nhưng gây side effect sai:

- Refund nhiều lần.
- Refund vượt số đã thanh toán.
- Xử lý duplicate event.
- Chuyển trạng thái từ canceled sang paid trái rule.
- Bỏ qua approval hoặc dual control.
- Thực hiện hành động dù policy service không trả kết quả.

Dynamic tests nên khẳng định **database/business state cuối**, không chỉ HTTP 2xx/4xx.

### 10.4. Async flows và eventual consistency

Với API tạo export qua queue:

1. User gửi request.
2. API xác thực/authorize.
3. Event được publish.
4. Worker xử lý và tạo file.
5. Link xuất hiện.
6. User tải file.

Test cần xác minh:

- Event có tenant/actor provenance.
- Worker không tin client-supplied tenant.
- Artifact chứa đúng dữ liệu được phép.
- Link có recipient/expiry/scope phù hợp.
- Retry và duplicated message không phát sai file.
- Audit có outcome đầy đủ.
- Timeout/retry được xử lý theo polling với giới hạn.

Không coi “POST export trả 202” là chứng minh export an toàn.

## 11. Case study: Tích hợp pipeline cho Orders API Java/Spring Boot

### 11.1. Bối cảnh giả định

Một nền tảng SaaS dùng:

- Java/Spring Boot Orders API.
- API Gateway và Identity Provider.
- PostgreSQL chứa đơn hàng nhiều tenant.
- Redis caching.
- Kafka/event bus và report worker.
- Private object storage cho exports.
- Payment provider sandbox với webhook signing.
- Container registry và Kubernetes.
- CI/CD pipeline build/test/promote/deploy.

Các security objectives:

- Tenant A không được xem dữ liệu tenant B.
- Refund chỉ được thực hiện đúng quyền và business rules.
- Webhook giả/duplicate không tạo payment state sai.
- Secret/token không xuất hiện trong logs hoặc report.
- Runtime configuration không fail-open.
- Audit có thể truy vết authorization và business changes.
- Release artifact có nguồn gốc và version rõ.

### 11.2. Architecture và trust boundaries

~~~mermaid
flowchart LR
    USER["Test user A/B"] --> GW["API Gateway"]
    GW --> API["Orders API"]
    API --> AUTH["Identity / Policy"]
    API --> DB[("PostgreSQL")]
    API --> CACHE[("Redis")]
    API --> QUEUE[("Event Bus")]
    QUEUE --> WORK["Report Worker"]
    WORK --> STORE[("Private Export Storage")]
    API --> AUDIT[("Audit")]
    WORK --> AUDIT
    PAY["Payment Provider Sandbox"] -->|"Signed webhook"| API
    CI["CI Runner"] -->|"Approved test traffic"| GW
    CI --> REPORT[("Protected Evidence")]
~~~

Các boundaries quan trọng:

- **TB-01:** CI scanner → target network/environment.
- **TB-02:** request identity → authentication/authorization.
- **TB-03:** subject → tenant-owned resource.
- **TB-04:** API → DB/cache dùng workload privileges.
- **TB-05:** API event → worker → export artifact.
- **TB-06:** external provider → webhook receiver.
- **TB-07:** test results → release gate/evidence store.

### 11.3. Test personas và fixtures

Giả định:

- Tenant A và tenant B là test tenants riêng.
- User A có membership ở A, không có quyền B.
- User B có membership ở B.
- Tenant admin A có quyền quản trị A, không được sửa B.
- Support user có thể được cấp case-level authorization theo policy.
- Order A và Order B có IDs/fields riêng.
- Payment provider chỉ dùng sandbox.
- Tài khoản/cookies/tokens có thời hạn ngắn và không được ghi vào report.

### 11.4. Security test matrix

| ID | Scenario | Layer | Expected |
| --- | --- | --- | --- |
| **DYN-T01** | User A đọc order A | Authenticated API | Allow đúng data |
| **DYN-T02** | User A đọc order B | Cross-tenant API | Deny/no data B |
| **DYN-T03** | User A sửa tenant header thành B | Identity/API | Không tăng quyền |
| **DYN-T04** | Anonymous gọi GET private order | Authn API | Unauthorized |
| **DYN-T05** | User A gọi admin B function | Function-level authz | Deny |
| **DYN-T06** | Cache đã được warm bởi user B | Cache integration | A không nhận B |
| **DYN-T07** | Export event chứa forged tenant context | Queue/worker | Reject/hold, không tạo file B cho A |
| **DYN-T08** | Revoked membership trước request | Session/authz | Deny sau propagation policy |
| **DYN-T09** | Policy service timeout | Failure path | Không release Confidential data |
| **DYN-T10** | Invalid webhook signature | Webhook | Không thay business state |
| **DYN-T11** | Duplicate valid webhook | Webhook/state | At-most-once business effect theo thiết kế |
| **DYN-T12** | Refund vượt amount | Business invariant | Reject, ledger không đổi trái phép |
| **DYN-T13** | Authorized refund | Positive business path | Success và audit đúng |
| **DYN-T14** | Request param unusual input | Controlled DAST | Không có unsafe parser/query behavior trong scope |
| **DYN-T15** | Response/cookies security config | Passive DAST | Phù hợp contract/policy |
| **DYN-T16** | Deployed image identity | Post-deploy | Digest bằng approved digest |
| **DYN-T17** | Secret/logging policy | Runtime/log test | Không có raw credential trong evidence |
| **DYN-T18** | New API operation added | Coverage check | Có owner, threat/test plan hoặc approved exclusion |
| **DYN-T19** | Scanner loses session | Completeness check | BLOCKED/coverage gap, không PASS |
| **DYN-T20** | DAST timeout | Gate | NOT_RUN/BLOCKED, không xem zero findings |

### 11.5. Security acceptance criteria

Không chỉ “scanner không có High alerts”, mà cần:

- Tất cả test cases bắt buộc trong scope có actual PASS hoặc approved risk disposition.
- Authenticated coverage phản ánh personas và tenant boundaries.
- Không có confirmed unresolved blocking finding theo release policy.
- Report completeness và scan success được xác minh riêng.
- Artifact/test environment identity có thể truy vết.
- Cleanup và test data không tạo side effect ngoài sandbox.
- Exclusions và limitations được ghi.
- Post-deploy identity/critical security checks hoàn tất theo policy.

Tài liệu này là **kịch bản giả định**; không có kết quả scan hoặc test thực tế nào được khẳng định đã chạy.

## 12. Java/JUnit: ví dụ API security regression chống BOLA

### 12.1. Thiết kế kiểm thử qua HTTP

Để kiểm tra ranh giới thực, có thể dùng JUnit 5 và Java HttpClient gửi request đến **test environment được phê duyệt**.

Giả định test fixture cấp:

- Base URI của Orders API trong integration/staging.
- Token ngắn hạn của user A.
- Order A thuộc tenant A.
- Order B thuộc tenant B.

Thay vì kiểm tra chỉ unit service method, test gọi **HTTP endpoint thực** và kiểm tra response + nội dung.

### 12.2. Ví dụ JUnit 5 với Java HttpClient

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.UUID;

import org.junit.jupiter.api.Test;

final class OrdersApiSecurityIT {
    private final HttpClient client = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(5))
            .followRedirects(HttpClient.Redirect.NEVER)
            .build();

    private URI requiredBaseUri() {
        // Must be an allowlisted, test-only host configured by the CI job.
        String raw = System.getenv("TEST_ORDERS_BASE_URL");
        assertNotNull(raw, "Test target is not configured");
        URI uri = URI.create(raw);
        assertEquals("https", uri.getScheme());
        assertEquals(
                "orders.test.example",
                uri.getHost(),
                "Refuse unapproved scan target");
        return uri;
    }

    private String requiredEnv(String name) {
        String value = System.getenv(name);
        assertNotNull(value, name + " is missing");
        assertFalse(value.isBlank(), name + " is blank");
        return value;
    }

    private HttpResponse<String> getOrder(
            String token, UUID orderId) throws Exception {
        URI uri = requiredBaseUri()
                .resolve("/api/orders/" + orderId);

        HttpRequest request = HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(10))
                .header("Authorization", "Bearer " + token)
                .GET()
                .build();

        return client.send(
                request, HttpResponse.BodyHandlers.ofString());
    }

    @Test
    void userA_canReadAuthorizedOrder() throws Exception {
        String token = requiredEnv("TEST_USER_A_TOKEN");
        UUID ownedOrder = UUID.fromString(
                requiredEnv("TEST_ORDER_A_ID"));

        HttpResponse<String> response = getOrder(token, ownedOrder);

        assertEquals(200, response.statusCode());
        // In production tests, parse a typed DTO and assert tenant/owner.
        assertTrue(response.body().contains(ownedOrder.toString()));
    }

    @Test
    void userA_cannotReadTenantBOrder() throws Exception {
        String token = requiredEnv("TEST_USER_A_TOKEN");
        UUID foreignOrder = UUID.fromString(
                requiredEnv("TEST_ORDER_B_ID"));

        HttpResponse<String> response = getOrder(token, foreignOrder);

        // Illustrative contract: conceal inaccessible resources with 404.
        assertEquals(404, response.statusCode());
        // Do not log the token or raw sensitive response body.
        assertFalse(response.body().contains(foreignOrder.toString()));
    }
}
~~~

**Quan trọng về ví dụ:**

- Domain **orders.test.example** là placeholder của test-only domain; phải cấu hình lại và xác minh allowlist khi triển khai. Ví dụ trên **không phải test đã chạy**, cũng không tự tạo fixtures.
- Test yêu cầu API có policy trả 404 khi user không được đọc order; nếu policy quy định 403, assertion phải điều chỉnh có rationale.
- Test dạng **body contains** mang tính minh họa; hệ thống thật nên parse typed JSON, assert ownership và bảo đảm không lộ dữ liệu tenant B. Nếu error response chứa ID resource theo thiết kế được phê duyệt, cần oracle chính xác hơn.
- Bảo đảm secret không được in vào failure logs. Công cụ CI có thể vô tình xuất request headers khi bật debug.
- Negative test chỉ có ý nghĩa nếu Order B **thực sự tồn tại**, thuộc B và user A **không** có quyền. Nếu order B không tồn tại, 404 giả có thể tạo **false PASS**.
- Test này chỉ bao phủ GET; cần export/cache/worker/support paths và positive tests để đạt assurance rộng hơn.

### 12.3. Precondition assertion chống false PASS

Ví dụ test setup cần chứng minh:

- User B đọc Order B được phép.
- User A đọc Order A được phép.
- User A không có membership B.
- Order B có dữ liệu fixture được xác thực.
- Target version/digest đúng patch.
- Role/policy/tenant fixtures không thay giữa tests.

**Không test precondition là lỗi phổ biến:** một 404 do route chưa deploy hoặc ID không tồn tại không chứng minh authorization.

### 12.4. Không chỉ HTTP status

Với security critical response, cần kiểm tra:

- Không có fields từ tenant B.
- Không có attachment/download link của B.
- Không tạo audit “allow” hoặc side effect khi deny.
- Không có data leak qua cache/search.
- Error shape không lộ private metadata theo policy.
- Retry/timeout không chuyển deny thành allow.
- Backend không phục vụ request qua direct route bypassing gateway.

## 13. Kiểm thử webhook, async flow và side effects

### 13.1. Webhook testing

Một payment webhook qua Internet có thể cần kiểm tra:

- **Valid signature + valid business mapping** → một state change hợp lệ.
- **Invalid signature** → không thay state.
- **Duplicate/replayed event** → không tạo duplicate payment effect.
- **Out-of-order event** → chỉ chuyển state theo transition rules.
- **Wrong tenant/order mapping** → reject và audit.
- **Provider timeout** → retry/reconcile, không báo success giả.

Chỉ dùng **provider sandbox** hoặc local fake provider. Không gửi payload thử nghiệm vào payment production nếu không có ủy quyền và safeguards.

### 13.2. Event queue và worker

Dynamic test cần nhìn **downstream effect**, vì API có thể trả 202 nhưng worker tạo file sai.

Ví dụ:

~~~mermaid
sequenceDiagram
    participant A as Test User A
    participant API as Orders API
    participant Q as Event Queue
    participant W as Report Worker
    participant S as Export Storage
    A->>API: Request export for tenant A
    API->>API: Authenticate and authorize
    API->>Q: Verified event context
    Q->>W: Deliver event
    W->>W: Validate source/resource binding
    W->>S: Store authorized artifact
    A->>API: Poll export state
    API-->>A: Scoped result / link
~~~

Test variants:

- Valid event được xử lý đúng.
- Forged tenant context được reject/quarantine.
- Duplicate event không phát thêm unauthorized artifact.
- User bị revoke trước khi download không lấy file trái policy.
- Failed worker không ghi nhầm status thành success.
- Link expired hoặc khác recipient không download được.
- Audit trail nối actor, order, event và export ID.

### 13.3. Eventual consistency và flaky tests

Không nên dùng fixed sleep quá ngắn rồi coi thất bại là lỗi security. Cần:

- Poll theo deadline/budget.
- Verify final state, not just event accepted.
- Phân biệt timeout test infrastructure và unauthorized data release.
- Dedicated run identifiers và stable fixtures.
- Không share mutable event state giữa parallel jobs.
- Cleanup và idempotent retry.
- Track test flakiness, **không tắt security tests vì flaky**.

## 14. Kiểm thử lỗi và resilience trong sandbox

### 14.1. Failure-mode scenarios

Những tests có ích:

| Dependency lỗi | Security requirement |
| --- | --- |
| Identity provider unavailable | Không cấp quyền mới trái policy |
| Authorization policy timeout | Không release Confidential data nếu decision unknown |
| Database retry | Không đổi tenant scope hoặc duplicate financial effects |
| Cache stale | Không trả dữ liệu người/tenant khác |
| Secret manager unavailable | Không fallback hard-coded/default secret |
| Audit pipeline blocked | Hành vi theo risk policy, có buffer/alert/block tương ứng |
| Payment provider timeout | Không coi unknown outcome là confirmed success |
| Queue replay/out-of-order | Không gây trái state machine |
| WAF/gateway misroute | Backend enforcement còn phù hợp |
| Certificate/key rotation | Không disable TLS identity validation |

### 14.2. Có nên chạy fault injection trên CI?

Có nếu:

- Môi trường được cô lập.
- Có test oracle và reset.
- Không tác động hệ thống không thuộc scope.
- Có time/concurrency budget.
- Có người/nhóm chịu trách nhiệm.
- Có cleanup/stop conditions.

Không nên random kill pod hoặc network partitions trên shared production chỉ vì muốn “thêm security test”.

### 14.3. Failure mode không phải lúc nào cũng deny mọi thứ

Một số hệ thống cần giữ service availability có điều kiện. Tuy nhiên, với **confidential export** và authorization không rõ, không được tự lấy quyền cao hoặc đưa dữ liệu ra ngoài. Mỗi degraded behavior cần được thiết kế, phê duyệt và thử theo mục tiêu bảo mật.

## 15. Cơ chế kiểm soát an toàn cho scanner job

### 15.1. Bốn lớp bảo vệ

1. **Configuration policy:** target allowlist, operations/methods allowed, scanner mode, rate/time limits.
2. **Network policy:** runner egress chỉ tới endpoints được duyệt, DNS/redirect/proxy theo scope.
3. **Identity policy:** test-only short-lived credentials, least privilege.
4. **Operational controls:** test fixtures, stop conditions, metrics và cleanup.

Một allowlist ở scanner config vẫn có thể sai khi redirect hoặc proxy không được quản lý; cần network-level defense-in-depth.

### 15.2. Preflight checklist trước active DAST

- Tên host đúng môi trường, TLS identity validated.
- Domain/IP/port thuộc approved target list.
- Scanner không thể reach production qua credential khác.
- Scanner container/image digest đã được review.
- Active mode được phép cho target này.
- Role và token thuộc test-only scope.
- Side-effecting endpoints được exclude hoặc dùng mock/sandbox.
- Rate, concurrency, request count và timeouts được cấu hình.
- Auth refresh/session script hoạt động.
- Test seed dữ liệu đã hoàn tất.
- External callbacks không ra hệ thống thật.
- Evidence/log output được redacted/protected.
- Stop/kill switch và on-call contact rõ.
- Target application artifact digest khớp expected.

Nếu preflight thất bại, **BLOCKED** là quyết định đúng; không chuyển sang scan production chỉ để có kết quả.

### 15.3. Rate limit và availability

Đặt các giới hạn theo capacity và risk:

- Maximum concurrent requests.
- Request rate và total budget.
- Per-endpoint exclusions.
- Response timeout.
- Retry budget.
- Duration window.
- Error-rate threshold để tự dừng.
- Database/queue saturation guardrails.
- Scanner CPU/memory budget.

Các con số phải được chọn theo system SLO/baseline và test scope, không copy ngẫu nhiên từ một blog.

### 15.4. Không dùng scan mode phá hoại mà thiếu phép

Một số scanners có thể thử file upload, HTTP methods, parameter injection hoặc workflow replays gây mutation. Với release pipeline thường xuyên:

- Chỉ scan active trong ephemeral/sandbox có reset.
- Dùng passive/non-destructive checks cho môi trường nhạy cảm.
- Sử dụng targeted tests với synthetic data cho business logic.
- Require explicit approval cho stress/destructive paths.
- Ghi test scope/exclusions và residual risk.

## 16. Công cụ DAST và framework hỗ trợ

### 16.1. Công cụ phổ biến

Ví dụ công cụ mà đội ngũ có thể đánh giá:

- **OWASP ZAP:** proxy và automated dynamic scanning, có cơ chế passive/active với mức hỗ trợ tùy mode/cấu hình.
- **Burp Suite:** công cụ kiểm tra web/API; automation và tính năng có thể phụ thuộc edition/version.
- **API test frameworks:** JUnit/RestAssured/HTTP client/Postman/Newman/Karate hoặc frameworks tương đương.
- **Fuzzing frameworks:** công cụ tạo inputs và đánh giá crashes/coverage theo target.
- **IAST agents:** instrumentation trong runtime hỗ trợ quan sát tương tác security-sensitive.
- **Browser automation:** Playwright/Selenium hoặc công cụ tương đương để chạy auth/business UI flows.

Không có công cụ nào tự hiểu hết **business authorization, tenant ownership và all side effects**. Chọn theo coverage, source models, protocol, integration, permissions, report format và khả năng vận hành.

### 16.2. Phân biệt baseline/passive và active

Khi dùng ZAP hoặc tool khác, cần **xác minh mode đang chạy**. Một baseline scan có thể crawl/gửi requests rồi chạy passive rules; nó không tương đương một full active scan. Ngược lại active scan có thể tạo nhiều traffic và thay đổi dữ liệu.

Nội dung bài dùng **pipeline abstraction** thay vì khẳng định chính xác một dòng lệnh của mọi tool version; khi triển khai, phải kiểm tra CLI schema/documentation của phiên bản đã pin.

### 16.3. Không hardcode scanner image latest

Với scanner container:

- Pin image digest hoặc artifact identity theo policy.
- Xác minh provenance/signature khi áp dụng.
- Scan vulnerabilities của chính scanner.
- Giới hạn network/privileges.
- Mount report directory tối thiểu.
- Bảo vệ scanner config và custom scripts.
- Theo dõi rule pack/version thay đổi.
- Tách update scanner khỏi thay đổi ứng dụng để triage drift.

Nếu scanner tự cập nhật rules, số lượng findings có thể thay đổi dù ứng dụng không đổi. Lưu **tool/rules versions và thời điểm** để giải thích.

## 17. Pipeline YAML: thiết kế job có thể chuyển sang CI provider

### 17.1. Workflow ở mức khái niệm

~~~yaml
workflow_name: "orders-dynamic-security-review"
trigger:
  - "pull-request-to-protected-branch"
  - "release-candidate"
  - "scheduled"
jobs:
  build:
    output:
      - "source-commit"
      - "artifact-digest"
      - "sbom-reference"
  deploy-test:
    needs: ["build"]
    environment: "ephemeral-integration"
    outputs:
      - "approved-test-target"
      - "deployed-artifact-digest"
  provision-fixtures:
    needs: ["deploy-test"]
    creates:
      - "tenant-a-user"
      - "tenant-b-user"
      - "scoped-test-tokens"
      - "owned-orders"
  security-api-tests:
    needs: ["provision-fixtures"]
    required:
      - "authorized-read-positive"
      - "cross-tenant-denial"
      - "wrong-role-denial"
      - "invalid-session"
      - "export-worker-scope"
  dast-passive:
    needs: ["provision-fixtures"]
    target: "approved-test-target"
    mode: "passive-with-scoped-traffic"
  dast-active:
    needs: ["provision-fixtures"]
    condition: "risk-tier-and-authorization-approve-active"
    target: "approved-test-target"
    exclusions:
      - "non-sandbox-refund"
      - "non-sandbox-email"
  evaluate:
    needs:
      - "security-api-tests"
      - "dast-passive"
      - "dast-active-if-required"
    check:
      - "artifact-identity"
      - "scan-completeness"
      - "blocking-findings"
      - "approved-exceptions"
  publish-evidence:
    needs: ["evaluate"]
    storage: "restricted-artifact-store"
  cleanup:
    run_even_on_failure: true
    action: "revoke-test-tokens-and-remove-run-owned-fixtures"
~~~

Đây là **YAML mô tả workflow**, **không phải cú pháp CI executable**. Các trường action/needs/condition/report khác nhau theo GitHub Actions, GitLab CI, Jenkins, Argo Workflows hoặc nền tảng khác.

### 17.2. Vì sao cần tách job?

- Build job không cần secrets để test authorization.
- Provision job có thể lấy test tokens nhưng không cần production deployment permissions.
- Scanner job cần network tới test target, không cần IAM admin.
- Evaluation job cần read-only reports và policy.
- Evidence job cần restricted artifact storage, không cần tác động target.
- Cleanup job cần quyền hủy **đúng** test resources đã tạo, không có quyền xóa dữ liệu khác.
- Release promotion cần quyền cao hơn và approval riêng.

**Separation of duties và least privilege** giúp tránh việc một pull request hoặc scanner bị compromise có thể trực tiếp chiếm production.

### 17.3. Dependency gates và failure semantics

Job evaluation không nên diễn ra “green” nếu jobs required đã:

- SKIPPED do conditional sai.
- TIMED_OUT.
- CANCELLED.
- CRASHED trước tạo report.
- Tạo report rỗng vì mất token.
- Chạy nhầm target.
- Scan sai artifact.
- Không đạt route/authenticated coverage.
- Bị suppress findings không có approval.

Cần phân biệt:

- **PASS:** test chạy và assertion đạt.
- **FAIL:** test chạy và expected security behavior không đạt.
- **BLOCKED:** không thể thực hiện đáng tin do environment/tool/scope.
- **NOT_RUN:** không thực thi.
- **DEFERRED:** có quyết định có thẩm quyền và follow-up.
- **PARTIAL:** chỉ một phần coverage/scan thành công.

### 17.4. Policy dựa trên test categories

Một release có thể yêu cầu:

- API authorization regression: required, fail blocks.
- Targeted vulnerability retest: required cho finding cụ thể.
- Passive DAST: required và report completeness.
- Active DAST: required cho high-risk change hoặc planned schedule theo policy.
- Fuzzing sâu: có thể schedule riêng.
- Manual penetration testing: theo risk threshold/event.
- Runtime verification: phải hoàn tất ở deploy stage.

Không coi một scheduled DAST chưa chạy hôm nay là bằng chứng PASS của release hiện tại; xem policy **evidence freshness** và source linkage.

## 18. Điều phối jobs và artifact identity

### 18.1. Build once, scan actual deployed build

Một chuỗi mạnh:

1. Build image trong trusted pipeline.
2. Tạo image digest, SBOM/provenance khi áp dụng.
3. Deploy đúng digest vào test target.
4. Xác minh runtime imageID/config matches expected.
5. Chạy dynamic tests trên endpoint đi tới deployment này.
6. Publish reports liên kết commit/build/digest.
7. Promote cùng artifact digest nếu release được phép.
8. Xác minh production/canary đang chạy digest.
9. Chạy safe post-deploy tests theo policy.

### 18.2. Tránh rebuild khác nhau giữa scan và deploy

Nếu test image A rồi build lại image B từ source với dependencies không pin, kết quả DAST của A **không xác nhận B**.

Nếu tổ chức buộc rebuild per environment, cần bằng chứng về binary equivalence hoặc lại test/verify artifact tương ứng; không tự suy ra hai builds giống nhau từ cùng branch name.

### 18.3. Runtime config là một phần của claim

Ngoài digest, security behavior còn phụ thuộc:

- Feature flags.
- Gateway/WAF policy.
- Identity and authorization policy revisions.
- Database RLS/IAM policies.
- Environment variables/secrets.
- Network routing.
- Session settings.
- External provider configuration.

Một artifact giống nhau nhưng policy khác có thể cho kết quả bảo mật khác. Cần **config identity** hoặc kiểm tra effective settings cho controls quan trọng.

### 18.4. Diagram liên kết evidence

~~~mermaid
flowchart LR
    SRC["Source commit"] --> BUILD["Trusted build"]
    BUILD --> ART["Artifact digest"]
    ART --> TESTDEPLOY["Test deployment + config"]
    TESTDEPLOY --> DYN["API / DAST test run"]
    DYN --> REPORT["Result + scope + tool version"]
    REPORT --> GATE["Risk-based release decision"]
    GATE --> PROD["Production promotion"]
    PROD --> VERIFY["Runtime digest + safe checks"]
    VERIFY --> CONCLUSION["Assurance statement with limits"]
~~~

Một chuỗi không có kiểm tra **test deployment → artifact digest** và **production → approved digest** là evidence yếu khi thay đổi phiên bản.
## 19. Quản lý kết quả DAST theo trạng thái có thể kiểm toán

### 19.1. Kết quả phải có hai lớp độc lập

Mỗi job dynamic security testing cần tách:

1. **Execution/completeness status:** công cụ có chạy đúng target, hoàn thành và có đủ coverage không?
2. **Security findings/assessment status:** những lỗ hổng hoặc violations nào được tìm thấy và đánh giá thế nào?

Ví dụ:

- Scanner chạy thành công, có finding High → **EXECUTED** + **SECURITY_GATE_FAIL/PENDING_TRIAGE**.
- Scanner bị timeout, không có finding file → **BLOCKED**, không phải PASS.
- Scanner hoàn tất trên 20/30 routes → **PARTIAL_COVERAGE** dù các routes đã quét không có alerts.
- API test user A gọi order B trả 200 và chứa B → **SECURITY_ASSERTION_FAIL**, cần triage khẩn theo impact.
- Tool phát hiện một response header không áp dụng → **finding requires applicability triage**, không tự đóng.

### 19.2. Bảng trạng thái chuẩn hóa

| Status | Khi nào | Release decision gợi ý |
| --- | --- | --- |
| **PASS** | Test đã chạy, expected security behavior đạt | Đủ một phần evidence |
| **FAIL** | Assertion/safety/security property không đạt | Block hoặc risk path theo policy |
| **BLOCKED** | Dependency/tool/environment ngăn kiểm tra | Không được coi là passed |
| **NOT_RUN** | Test không được gọi | Không có evidence thực thi |
| **PARTIAL** | Một số endpoints/roles/testcases chưa kiểm tra | Cần coverage decision |
| **DEFERRED** | Bước được hoãn với approval và follow-up | Track như residual evidence gap |
| **FALSE_POSITIVE** | Finding được triage sai với evidence | Không xem như vulnerability active |
| **VERIFIED_FIXED** | Fix đã được retest trong scope | Có thể closure theo chính sách |
| **EXCEPTION_APPROVED** | Rủi ro được chấp nhận có thời hạn | Không đồng nghĩa finding đã sửa |

### 19.3. Không dùng một số exit code thay cho toàn bộ logic

Một CLI scanner có thể:

- Exit 0 khi công cụ hoàn tất, dù vẫn có alerts.
- Exit non-zero vì findings vượt threshold.
- Exit non-zero vì network timeout, parser error hoặc invalid session.
- Sinh report dù scan fail giữa chừng.
- Không sinh report khi crash.
- Ghi số findings 0 do không crawl được path nào.

Pipeline cần **normalize results và validate required fields/completeness**, không chỉ có điều kiện “command exited zero”.

### 19.4. Test report schema tối thiểu

Một chuẩn hóa report nên có:

- Run ID, job ID, commit ID.
- Scanner/tool version và rule version.
- Target allowlisted URL, environment và deployment identity.
- Start/end timestamps.
- Execution status và exit detail.
- Authenticated identities và roles được exercise (không ghi tokens).
- Discovered/tested endpoints và excluded routes.
- Requests attempted/completed theo loại.
- Findings: rule ID, evidence location, severity, confidence, affected endpoint.
- Findings triage states và owner.
- Evidence digest/reference.
- Completeness/coverage summary.
- Gate decision và policy version.
- Report retention/classification.

**Raw HAR/HTTP dumps có thể chứa PII và tokens**; cần làm sạch hoặc lưu trong restricted evidence store với retention phù hợp thay vì đính kèm công khai vào PR.

## 20. Triage findings và false positives

### 20.1. Vì sao DAST tạo false positives?

Một scanner có thể kết luận có lỗi khi:

- Response chứa chuỗi trông giống SQL error nhưng là dữ liệu fixture.
- Application dùng một mitigation mà rule không hiểu.
- Reverse proxy trả response khác backend.
- Endpoint test không được authentication đúng.
- Content được encode/sanitize phù hợp context nhưng rule không nhận biết.
- Application intentionally không trả một header trong context không cần thiết.
- Scanner đọc nội dung từ cache hoặc replay không đúng phiên bản.

**False positive phải có evidence về scope và behavior**, không chỉ comment “đã biết, bỏ qua”.

### 20.2. False negatives và vùng mù

DAST có thể bỏ lỡ:

- Endpoint không được crawl.
- Business function cần authenticated role đặc biệt.
- Hidden API hoặc feature flag.
- Stateful workflow nhiều bước.
- Back-end queue/worker side effect.
- Async vulnerabilities không hiển thị trong HTTP response.
- Rate-limited paths scan chưa đủ.
- Biến thể input/encoding đặc biệt.
- Logic authorization chỉ xảy ra với resource ownership khác.
- SSRF chỉ có tác động ngoài mạng target.
- Runtime configuration khác test environment.
- Manual-only approval hoặc support impersonation path.

Do đó **zero alerts không có nghĩa zero security defects**.

### 20.3. Triage workflow

1. Verify result có đến từ đúng artifact/environment.
2. Kiểm tra tool completion và authentication coverage.
3. Đọc request/response đã redacted hoặc reproducer an toàn.
4. Xem affected endpoint, user role, data classification.
5. Tái hiện bằng test riêng trong sandbox nếu cần.
6. Review security requirement và threat scenario.
7. Xác minh error có thể khai thác hay là false positive/expected behavior.
8. Đánh giá exposure và compensating controls đã test.
9. Phân loại priority, chọn owner và action.
10. Link finding với source change/issue và test.
11. Sửa, chạy lại targeted test và broader regression.
12. Verify deployment/artifact trước khi closure.

### 20.4. Không đồng nhất scanner severity với business priority

Ví dụ:

- Low/default severity alert ghi raw production token trong log: có thể cần khẩn.
- High scanner alert ở demo endpoint chỉ có synthetic data: có thể lower priority sau applicability review.
- BOLA không bị scanner phát hiện: integration test lại xác nhận cross-tenant exposure.

Priority nên xem **CVSS nếu phù hợp, exploit conditions, asset criticality, data sensitivity, active exploitation và impact**, không một mình severity scanner.

### 20.5. Baseline và deduplication

Một finding có thể được các công cụ khác nhau báo hoặc xuất hiện lại sau scan rule update.

Correlation fields:

- Affected service/artifact.
- Route/method/parameter.
- Vulnerability class/rule.
- Evidence fingerprint.
- Source/config lineage.
- Environment và role context.

Không gộp hai findings trên cùng endpoint nếu **root cause và remediation khác**. Đồng thời không tạo 100 tickets cho cùng root cause nhưng quên deployment child exposures.

## 21. Quản lý gate: block, warn, triage và exception

### 21.1. Gate không chỉ là ngưỡng severity

Một gate hợp lý gồm nhiều điều kiện:

1. Required security jobs hoàn tất.
2. Deployment đúng build/digest.
3. Test identities và fixtures hợp lệ.
4. Tất cả mandatory negative tests đạt.
5. Scan coverage đạt threshold đã phê duyệt.
6. Findings blocking được xử lý theo policy.
7. Scanner/config/rule versions được ghi.
8. Exceptions hợp lệ, chưa hết hạn, đúng scope.
9. Không có blocker do missing report/scan.
10. Evidence được lưu và có thể kiểm toán.

Một test authorization thất bại có thể chặn release dù generic scanner không có High alerts.

### 21.2. Decision tree của gate

~~~mermaid
flowchart TD
    A["Collect all required job results"] --> B{"Artifact/target identity verified?"}
    B -- "No" --> BLOCK["BLOCKED: invalid evidence"]
    B -- "Yes" --> C{"Required jobs actually executed?"}
    C -- "No" --> BLOCK
    C -- "Yes" --> D{"Coverage and authenticated preconditions met?"}
    D -- "No" --> PARTIAL["PARTIAL / investigate or approved defer"]
    D -- "Yes" --> E{"Confirmed blocking security failures?"}
    E -- "Yes" --> FAIL["FAIL: remediation or authorized risk path"]
    E -- "No" --> F{"Open findings/unknowns require decision?"}
    F -- "Yes" --> TRIAGE["Triage and risk-owner review"]
    F -- "No" --> PASS["PASS within assessed scope"]
    TRIAGE --> G{"Policy decision approved and current?"}
    G -- "No" --> FAIL
    G -- "Yes" --> H["Conditional release with tracked residual risk"]
~~~

**Conditional release không đồng nghĩa vulnerability đã fixed.** Nó chỉ phản ánh một quyết định rủi ro trong phạm vi và thời hạn xác định.

### 21.3. Ví dụ policy với hard triggers

Có thể đặt hard blocking conditions cho:

- Cross-tenant unauthorized data disclosure được test xác nhận.
- Production credential hoặc secret bị expose.
- Privileged endpoint có auth bypass.
- Known actively exploited vulnerability applicable và không có mitigation hợp lệ.
- Security scanner required không chạy hoặc report không liên kết được artifact.
- Endpoint public mới không được áp required authentication test.
- Mất audit/detection ở workflow nhạy cảm nếu policy yêu cầu.
- Active scan được chạy sai scope gây incident.

Những conditions phải được quản lý trong **policy version** và có owner; không dùng rule đơn giản “findings count = 0” làm tiêu chí duy nhất.

### 21.4. Warn-only có hợp lệ không?

Có thể, với đúng maturity stage/risk tier, để:

- Thu thập baseline trước khi bật gate.
- Giảm false positives bằng triage.
- Đánh giá rule coverage.
- Hướng dẫn developer review.
- Hoàn thiện test identities và fixtures.

Nhưng nếu test phát hiện **rủi ro nghiêm trọng đã xác nhận**, tổ chức phải áp quy trình escalation theo policy; không coi warn-only mode là miễn trách nhiệm.

### 21.5. Tránh approval không có chứng cứ

Một exception cần:

- Finding/rule/test ID.
- Asset/endpoint/artifact scope.
- Evidence và lý do.
- Residual-risk owner và reviewer.
- Compensating controls đã kiểm chứng.
- Start/expiry/renewal policy.
- Required remediation/monitoring.
- Triggers để mở lại.
- Gate override audit record.

Không đặt “ignore this finding forever” làm mặc định.

## 22. Thiết kế test coverage và phát hiện giảm coverage

### 22.1. Coverage không chỉ số lượng URLs

Một route đã được gửi một request nhưng:

- 401 do token expired.
- 403 vì scanner không có role.
- 302 chuyển sang login.
- Trả mock response không dùng business path.
- Không có expected-resource fixture.
- Không thực thi worker downstream.

thì không thể coi là **security coverage đầy đủ**.

### 22.2. Tính coverage theo meaningful test pairs

Một đơn vị tốt hơn:

**(Security requirement, operation, actor role, resource class, trust boundary, expected outcome)**.

Ví dụ:

| Requirement | Operation | Actor/resource | Outcome |
| --- | --- | --- | --- |
| AUTHZ-01 | GET order | User A → order A | ALLOW |
| AUTHZ-01 | GET order | User A → order B | DENY |
| AUTHZ-02 | EXPORT orders | User A → mixed A+B | DENY/no B output |
| AUTHZ-03 | POST refund | Unauthorized user | DENY/no state change |
| AUTHZ-04 | GET support export | Support without case | DENY |
| WEBHOOK-01 | POST callback | Invalid signature | DENY/no state change |
| AUDIT-01 | Failed export | User A | Audit event emitted |

Một endpoint count có thể không thể hiện các tổ hợp này.

### 22.3. Detect coverage regression

Sau một code change:

- So sánh OpenAPI operations cũ/mới.
- Xác nhận routes mới có owner và test plan.
- Theo dõi removed tests hoặc skipped suites.
- Kiểm tra role matrix còn tương ứng policies.
- Cập nhật fixtures khi dữ liệu/schema đổi.
- So sánh crawler authenticated success rate.
- Review rule/scanner updates.
- Flag decrease in covered security invariants.
- Không tự pass khi số endpoints giảm đột ngột.

### 22.4. Không có tỷ lệ coverage tuyệt đối phổ quát

Ví dụ 100/100 public endpoints đã crawl nhưng thiếu negative authorization tests vẫn có gap lớn. Ngược lại một scanner không crawl một endpoint nội bộ có thể có exclusion hợp lệ nếu một targeted security test khác đã bao phủ và policy chấp nhận.

Cần báo cáo **risk-weighted coverage** và exemptions có căn cứ.

## 23. Kiểm soát tính ổn định và tính tái lập

### 23.1. Flaky security tests gây hậu quả gì?

- Developer mất tin vào gate.
- Đội ngũ tắt/skips suite.
- Findings bị bỏ qua vì “thường xuyên lỗi giả”.
- Release bị chặn thiếu căn cứ.
- Monitoring/KPI bị nhiễu.
- Real vulnerabilities bị che bởi infrastructure failures.

### 23.2. Các nguyên nhân thường gặp

- Shared test accounts đổi role/tokens.
- Fixtures bị xóa bởi job khác.
- Tests chạy không có cleanup.
- Eventual consistency chưa được đợi đúng.
- API rate limiter chặn scanner.
- Queue backlog hoặc worker scheduling.
- IdP session token hết hạn.
- Staging đang deploy song song.
- Non-deterministic ordering/timestamps.
- Timezone/clock skew.
- Provider sandbox có outages.
- Network egress/proxy flaky.

### 23.3. Cách giảm flakiness đúng

- Dedicated run-scoped data và identities.
- Use environment locking hoặc namespaces.
- Preflight state và test assumptions.
- Poll with deadlines cho async operations.
- Retry **chỉ** khi phù hợp test semantics.
- Không retry test bị security violation cho đến khi “may mắn PASS”.
- Lưu logs/traces theo correlation ID.
- Tách infra failure khỏi security assertion failure.
- Hạn chế shared mutable state.
- Quarantine test tạm thời chỉ bằng approval, owner, expiry và alternate evidence.
- Track flaky rate theo rule/test.

### 23.4. Retry có thể che lỗi bảo mật

Nếu một request cross-tenant trả dữ liệu B ở attempt #1 nhưng deny ở attempt #2, **không thể lấy attempt cuối PASS** để kết luận an toàn.

Mỗi security violation có thể là bằng chứng của **race hoặc inconsistent authorization**; cần giữ toàn bộ attempts và điều tra.

### 23.5. Idempotency và state reset

Các tests mutating endpoints cần:

- Run-specific order IDs.
- Transactions hoặc cleanup rõ.
- Không reuse payment idempotency keys sai.
- Test provider ở sandbox.
- Assert state transitions.
- Test retry/duplicate theo business requirement.
- Không xóa resource của test khác.
- Audited cleanup.

## 24. Parallel execution và multi-service orchestration

### 24.1. Parallel jobs không luôn độc lập

Chạy DAST và API tests đồng thời có thể:

- Dùng chung một account, làm session bị revoke.
- Dùng chung orders, làm test mất state.
- Làm rate limits bị kích hoạt.
- Tạo dữ liệu trong scanner crawling.
- Ghi alerts/audit events xen lẫn.
- Gây overload môi trường integration.

Giải pháp:

- Separate tenants/users/resources per job.
- Dedicated target namespaces hoặc isolated preview deployments.
- Configurable traffic budgets.
- Lock/exclusive phase cho destructive operations.
- Correlation ID per run.
- Quota và monitoring.
- Không leak secrets giữa jobs.

### 24.2. Scan nhiều microservices

Một platform có thể có API gateway và nhiều downstream services. Đừng chỉ scan gateway happy path rồi suy rằng:

- Service-to-service auth đúng.
- Internal admin endpoint không exposed.
- Queue/worker isolation tốt.
- DB access controls đúng.

Cần:

- Service inventory và owner.
- Trust-boundary mapping.
- Tests qua public interface và targeted internal integration tests.
- Effective network/IAM policy checks.
- Consumer/producer contract tests.
- Evidence correlation theo service/artifact.

### 24.3. Orchestrate theo dependency

Ví dụ:

~~~text
Build
  -> Deploy test target
  -> Health and identity/config verification
  -> Seed synthetic tenants and orders
  -> Create scoped user tokens
  -> Run basic positive API tests
  -> Run cross-role/tenant security tests
  -> Run scoped DAST
  -> Run async/export/webhook tests
  -> Check scanner completeness and artifacts
  -> Risk gate
  -> Publish protected evidence
  -> Cleanup scoped tokens/data/infrastructure
~~~

Thứ tự có thể được parallelize theo isolation, nhưng dependencies như “seed data trước khi BOLA test” và “verify scan target trước active scan” phải được giữ.

## 25. Bảo vệ pipeline khỏi bị lợi dụng qua pull request

### 25.1. Untrusted contribution

Một PR từ nguồn không tin cậy có thể thay:

- Workflow configuration.
- Scan target URL.
- Test scripts.
- Dockerfile hoặc scanner plugins.
- Dependency versions.
- Report normalization code.
- Script gửi dữ liệu tới attacker endpoint.
- Test data setup.
- Gate policy hoặc suppression rules.

Nếu CI cấp token production cho PR, scanner không phải rủi ro duy nhất; **mọi code trong PR có thể trở thành executable code trong runner**.

### 25.2. Tách trust levels

Một thiết kế phù hợp:

- Untrusted PR: build/static checks và unit tests không có production credentials.
- Privileged integration/security jobs: chỉ chạy với approved code/trust boundary, secrets scope thấp.
- Deployment promotion: protected environment và approval.
- Registry/signing: hạn chế identity và tách khỏi scanner.
- Reports: chỉ được dùng vào gate sau khi xác minh source/job integrity.
- Test URLs: lấy từ approved inventory, không từ input không tin cậy.
- Secrets: dynamic scoped tokens, không chia sẻ cross-job khi không cần.

### 25.3. Allowlist ở nhiều lớp

- CI configuration liệt kê target identities.
- Network policy chặn external/production destinations ngoài scope.
- DNS/redirect handling được kiểm tra.
- Scanner không có quyền truy cập metadata service hoặc internal admin network không cần.
- API test users bị giới hạn role.
- Runtime sandbox services không chứa customer data.
- Audit mọi outbound targets theo khả năng.

### 25.4. Report integrity và gate tampering

Không được để một job không đáng tin tự ghi:

~~~text
security_status = "PASS"
~~~

mà không có cách kiểm chứng. Gate nên dựa vào:

- Trusted job identity.
- Job exit/completion metadata.
- Signed/attested evidence nếu policy yêu cầu.
- Report schema validation.
- Artifact provenance/build identity.
- Independent policy configuration.
- Audit trail khi có override.

Nếu test report mất hoặc parsing lỗi, trạng thái đúng là **BLOCKED/INSUFFICIENT_EVIDENCE**, không phải PASS.

## 26. CI/CD examples: Java service và deployment assumptions

### 26.1. Các bước dùng cho Java/Spring Boot

Một pipeline mang tính minh họa có thể:

1. Chạy JUnit tests kiểm tra authorization ở unit/integration layer.
2. Build Java artifact bằng Gradle/Maven version đã kiểm soát.
3. Tạo container có digest và SBOM.
4. Deploy vào dedicated integration environment.
5. Verify target identity, TLS, app readiness và service version.
6. Seed test tenants, users và orders.
7. Run JUnit HTTP security integration suite.
8. Run approved DAST profile.
9. Parse reports và enforce policy.
10. Publish protected evidence, teardown.
11. Promote artifact đã được phê duyệt.

### 26.2. Job shell pseudocode

~~~bash
# Pseudocode: conventions and scripts need implementation by the project.
# The target must be preapproved and bound to a test deployment.
set -eu

./ci/verify-test-target
./ci/verify-deployed-artifact
./ci/seed-security-fixtures
./ci/run-api-security-tests
./ci/run-approved-dast
./ci/validate-scan-completion
./ci/evaluate-security-gates
./ci/publish-protected-evidence

# Cleanup should be configured as a finally/always-run job,
# including the case where an earlier step fails.
~~~

Đây **không phải script runnable** nếu các lệnh ci/* chưa tồn tại; nó minh họa **contract và thứ tự của pipeline**. Không tạo các scripts giả rồi coi đó là security verification thật.

### 26.3. Vì sao không gọi DAST trực tiếp vào một external URL bất kỳ?

Một lệnh scanner có target từ biến environment không được validate có thể quét nhầm:

- Production.
- Internal management host.
- Một hostname không được sở hữu.
- Một vendor service.
- Metadata endpoint.
- Other tenant environment.

Trong pipeline, target nên đến từ approved deployment record, được kiểm tra **scheme, hostname, port, environment identity và redirect policy**; network egress cũng phải enforce scope.

### 26.4. Version pinning cho workflow actions

Workflow dependencies gồm:

- Checkout/build actions.
- Java runtime/toolchain actions.
- Container build/publish actions.
- DAST scanner action/image.
- Report upload/artifact actions.

Nên quản lý immutable refs, review updates, least privileges và provenance theo supply-chain policy. Một action được pin nhưng có code độc hại trong phiên bản đó vẫn nguy hiểm; cần kiểm tra publisher/source và update advisories.

## 27. Xử lý secrets, reports và retention

### 27.1. Các loại dữ liệu nhạy cảm trong dynamic testing

- OAuth/OIDC tokens, cookies và refresh tokens.
- Account passwords và recovery factors.
- Test API keys và partner signing secrets.
- SQL/debug traces và stack traces.
- Request/response bodies có business/PII data.
- Architecture URLs và internal hostnames.
- Tenant/resource relationships.
- Vulnerability proof/correlation details.
- Scan configuration và privileged endpoints.

Ngay cả test-only tokens có thể có quyền trong môi trường integration; vẫn cần protected handling.

### 27.2. Log hygiene

- Redact Authorization, Cookie và Set-Cookie values.
- Mask credentials và secret query parameters.
- Không đưa raw response body của Confidential endpoints vào public PR comments.
- Ghi metadata/fingerprint thay vì full secret.
- Tránh bật verbose HTTP debug trong shared CI logs.
- Verify scanner report exporter có filter/masking đúng.
- Dùng dedicated protected evidence storage.
- Định nghĩa retention và access-review.

### 27.3. Test data minimization

Không dùng database snapshot chứa PII thật nếu synthetic data đáp ứng yêu cầu. Nếu phải dùng masked dataset, đánh giá nguy cơ re-identification, approval, encryption và cleanup theo policy.

### 27.4. Evidence cần được bảo vệ khỏi sửa

- Stable run ID.
- Artifact digest cho report khi cần.
- Storage ACL và audit.
- Read-only reviewer access.
- Retention tương ứng risk/compliance.
- Không cho scanner job xóa evidence đã publish.
- Khi report bị sửa hoặc mất, trạng thái assurance phải cập nhật.

Một CSV/JSON do scanner tạo và đặt trong public artifacts không tự là **trustworthy evidence**.

## 28. Hồ sơ assurance cho một lần dynamic test

### 28.1. Những trường tối thiểu

| Trường | Ví dụ nội dung |
| --- | --- |
| **Assessment ID** | DYN-TEST-RUN-043 |
| **Security requirement** | Cross-tenant read denied |
| **Finding/vulnerability ref** | VULN-AUTHZ-017 |
| **Source commit/build** | Commit, pipeline build ID |
| **Deployed artifact** | OCI image digest |
| **Target identity** | Environment ID, canonical URL |
| **Effective config** | Auth policy/gateway revision |
| **Test suite** | Version, rules, personas |
| **Execution status** | PASS/FAIL/BLOCKED/PARTIAL |
| **Test cases** | IDs, expected, actual |
| **Coverage** | Endpoints, roles, tenants, exclusions |
| **Scanner status** | Tool/version/rules, completion/timeout |
| **Findings** | IDs, severity, confidence, priority |
| **Evidence** | Protected refs, digests, correlation IDs |
| **Reviewer** | Technical/security reviewer |
| **Gate decision** | Approved/blocked/conditional |
| **Exceptions** | Owner, scope, expiry |
| **Retest** | Fix commit, deployed digest, result |
| **Limitations** | Conditions not tested |

### 28.2. Ví dụ YAML assessment record

~~~yaml
assessment_id: "DYN-PIPELINE-DEMO-009"
module: "SECURITY_SECURITY_ASSURANCE"
service: "orders-api"
chapter: "Dynamic testing"
topic: "Tích hợp pipeline"
assessment_type: "DYNAMIC_SECURITY_TEST"
status: "DRAFT"
scope:
  application: "orders-api"
  environment: "isolated-integration"
  canonical_host: "orders.test.example"
  data_classification: "SYNTHETIC_ONLY"
  permitted_modes:
    - "targeted-api-security-tests"
    - "approved-passive-dast"
  active_dast_authorized: false
  excluded_operations:
    - "real-payment-operations"
    - "production-data-mutations"
target:
  source_commit: "NOT_VERIFIED"
  build_id: "NOT_VERIFIED"
  expected_artifact_digest: null
  actual_deployed_digest: null
  gateway_config_version: null
  authorization_policy_version: null
identities:
  test_roles:
    - "customer-tenant-a"
    - "customer-tenant-b"
    - "tenant-admin-a"
  token_material_saved_in_report: false
  preconditions_verified: false
scanner:
  engine: "NOT_SELECTED"
  engine_version: "NOT_VERIFIED"
  rule_pack_version: "NOT_VERIFIED"
  run_id: null
  execution_status: "NOT_RUN"
  authenticated_coverage: "NOT_MEASURED"
  scope_verified: false
test_cases:
  - id: "DYN-T01"
    requirement: "authorized-order-read"
    expected: "ALLOW"
    actual: "NOT_RUN"
  - id: "DYN-T02"
    requirement: "cross-tenant-denial"
    expected: "DENY_NO_DATA_DISCLOSURE"
    actual: "NOT_RUN"
  - id: "DYN-T07"
    requirement: "worker-event-tenant-scope"
    expected: "REJECT_FORGED_CONTEXT"
    actual: "NOT_RUN"
  - id: "DYN-T10"
    requirement: "invalid-webhook-signature"
    expected: "NO_BUSINESS_STATE_CHANGE"
    actual: "NOT_RUN"
  - id: "DYN-T16"
    requirement: "deployment-identity"
    expected: "DIGEST_MATCH"
    actual: "NOT_RUN"
findings: []
exceptions: []
evidence_refs: []
design_effectiveness: "NOT_VERIFIED"
implementation_effectiveness: "NOT_VERIFIED"
operating_effectiveness: "NOT_VERIFIED"
gate_decision: "INSUFFICIENT_EVIDENCE"
control_owner: "Orders API Engineering"
risk_owner: "Orders Product Risk Owner"
assurance_reviewer: null
next_action: "Provision test environment and execute authorized tests"
~~~

Đây là **mẫu minh họa**, không phải một scan result thật. Mục **NOT_RUN** và **INSUFFICIENT_EVIDENCE** giúp tránh tạo cảm giác rằng pipeline đã chạy.

### 28.3. Scan evidence không đồng nghĩa exploit proof

Một scanner report có thể chứng minh:

- Một pattern/response trong quá trình scan bị gắn cảnh báo.
- Một response/endpoint đã được tool quan sát.
- Một rule đã được chạy theo configuration.

Nó **không tự chứng minh** attacker đã khai thác, exploit chạy được trong production hoặc dữ liệu đã bị xâm phạm. Nếu cần xác nhận, dùng controlled reproduction và analysis có phép.

## 29. Design, implementation và operating effectiveness

### 29.1. Design effectiveness

**Câu hỏi:** test strategy và controls của pipeline có bao phủ các rủi ro/boundaries quan trọng?

Evidence:

- Threat model và security requirements.
- Architecture DFD và trust boundary map.
- Dynamic test strategy.
- Role/tenant matrices.
- Scan mode và safety policy.
- Test environment model và risk-based trigger mapping.
- Gate/exception/ownership design.
- Coverage model và reporting schema.

Một tài liệu test plan tốt **chưa chứng minh job chạy**.

### 29.2. Implementation effectiveness

**Câu hỏi:** pipeline và test code hiện thực hóa design đúng chưa?

Evidence:

- Workflow definitions và code review.
- CI runner/scanner permissions.
- Test fixtures và token provisioning.
- Test suite execution logs.
- DAST reports và completion metadata.
- Verified artifact/target identity.
- Negative tests cho scanner timeout, missing token, wrong target.
- Gate implementation và exception controls.
- Protected evidence uploads.

### 29.3. Operating effectiveness

**Câu hỏi:** các controls hoạt động liên tục qua releases và changes?

Evidence:

- CI execution history, coverage trend.
- Findings triage/remediation/retest records.
- Runtime deployment digest verification.
- Periodic/scheduled scan reports.
- Scanner/rules upgrade controls.
- Expired exceptions và gate overrides.
- Incident-derived improvements.
- Flaky scan reduction và test-quality metrics.
- Samples được review độc lập theo kỳ.

Một lần DAST PASS trên staging không chứng minh operating effectiveness của cả năm.

### 29.4. Kết luận có trách nhiệm

Một kết luận đủ chặt:

> Trong release candidate đang xét, các bài kiểm thử authorization và DAST thuộc scope đã hoàn tất trên artifact digest được ghi. Những behaviors đã kiểm tra đáp ứng expected results; không có confirmed blocking findings còn mở trong các test được thực hiện. Kết quả không bao phủ những endpoints được loại trừ, các phụ thuộc bên ngoài không thuộc kiểm soát và các trạng thái production chưa được xác minh.

Kết luận yếu:

> DAST xanh, toàn hệ thống an toàn 100%.

## 30. Xử lý remediation và retest end-to-end

### 30.1. Finding lifecycle

~~~mermaid
stateDiagram-v2
    [*] --> DETECTED
    DETECTED --> TRIAGE
    TRIAGE --> CONFIRMED
    TRIAGE --> FALSE_POSITIVE: Evidence-based disposition
    TRIAGE --> INSUFFICIENT_EVIDENCE
    INSUFFICIENT_EVIDENCE --> TRIAGE: Additional checks
    CONFIRMED --> PRIORITIZED
    PRIORITIZED --> FIX_IN_PROGRESS
    PRIORITIZED --> MITIGATED: Verified control
    PRIORITIZED --> EXCEPTION: Authorized bounded risk
    MITIGATED --> FIX_IN_PROGRESS
    FIX_IN_PROGRESS --> READY_FOR_RETEST
    READY_FOR_RETEST --> VERIFIED_FIXED: Targeted test and correct deployment
    READY_FOR_RETEST --> FIX_IN_PROGRESS: Fail or incomplete
    EXCEPTION --> TRIAGE: Expired/new risk
    VERIFIED_FIXED --> CLOSED
    FALSE_POSITIVE --> CLOSED
~~~

### 30.2. Retest theo đúng security claim

Với finding cross-tenant read:

- Fix application authorization.
- Test user A đọc Order A cho phép.
- Test user A đọc Order B từ chối.
- Test tenant header giả không cấp quyền.
- Test export/cache/worker alternate paths.
- Confirm deployment digest.
- Re-run targeted dynamic security regression.
- Review audit/no unauthorized side effect.
- Update finding scope và residual risk.
- Close khi đạt policy.

**Scanner không báo lại** có thể do changed behavior thật hoặc scanner không reach endpoint. Cần kiểm tra preconditions và coverage.

### 30.3. Chống test overfitting

Nếu developer sửa code chỉ để input mẫu của scanner không còn trigger nhưng các biến thể vẫn khai thác được, remediation thiếu căn cứ.

Cần:

- Root cause analysis.
- Guard ở trust boundary đúng.
- Positive/negative/boundary variations.
- Code review.
- Alternative entry points.
- Contract/integration tests.
- Runtime effective config review.

### 30.4. Findings do môi trường lỗi

Ví dụ scanner báo TLS certificate warning vì staging dùng self-signed certificate. Không tự ignore một cách toàn cục vì production có thể có lỗi khác. Cần phân biệt:

- Test-only trust configuration được review.
- Production certificate/trust-chain checks.
- Scanner SSL validation thực sự bật/tắt ở đâu.
- Evidence và environmental scope.
- Exception nếu cần.

## 31. Thay đổi API, architecture và trigger chạy lại

### 31.1. Trigger theo thay đổi

- Thêm public endpoint hoặc HTTP method.
- Thay identity provider/session/token handling.
- Thay authorization policy hoặc tenant model.
- Thay resource ownership/routing.
- Thêm admin/support workflow.
- Thêm queue/worker/export/search/cache.
- Thay webhook/provider integration.
- Thay WAF/gateway/ingress/network.
- Thay DB/RLS/privileged service credentials.
- Nâng framework/runtime hoặc auth library.
- Thay security headers, CORS, CSRF.
- Thay scanner engine/rules or test fixtures.
- Incident, newly exploited vulnerability hoặc security audit finding.

### 31.2. Targeted tests vs full sweep

- **Targeted:** chạy các test liên quan change để phản hồi nhanh.
- **Full sweep:** chạy theo release/periodic khi cần đánh giá rộng, kể cả code không đổi.
- **Out-of-band:** incident hoặc advisory trigger test ngay theo risk.
- **Post-deploy:** safe verification trên environment target.

Không dùng targeted scan để tuyên bố full application coverage. Cũng không cần quét active toàn bộ production mỗi lần nâng một UI CSS nếu risk không yêu cầu.

### 31.3. API schema drift

Nếu OpenAPI mới có endpoint chưa từng được security test:

- Detect diff.
- Identify owner/risk/required authentication.
- Determine data class.
- Add positive/negative tests.
- Update scan scope.
- Record exclusions nếu chưa thể test.
- Gắn release decision với coverage result.

## 32. Release promotion, production verification và feedback loop

### 32.1. Trước promotion

Phải biết:

- Artifact đã được build và kiểm tra bằng gì?
- Test report đủ và không bị sửa trái phép?
- Remaining findings/overrides có owner không?
- Scanner logs có chứa raw secrets không?
- Security tests có đúng user/resource fixtures?
- Test environment parity hạn chế thế nào?
- Có test runtime nào bắt buộc sau deploy?
- Rollback/forward-fix plan có xét known vulnerabilities không?

### 32.2. Sau deploy

Có thể thực hiện an toàn:

- Verify image digest/commit/config policy identity.
- Request safe health và authentication checks.
- Dùng test-only synthetic account kiểm tra deny case được phê duyệt.
- Confirm audit events được ghi theo policy.
- Observe error/latency/security signals.
- Confirm WAF/route/network effective state khi test có phép.
- Verify endpoint inventory và alert coverage.
- Check no old vulnerable instances đang phục vụ ngoài scope rollout.

Không chạy active fuzzing hoặc destructive endpoint probes trên production chỉ vì muốn có confidence cao hơn.

### 32.3. Khi runtime khác staging

Nếu production có WAF, cache hoặc IAM khác:

- Ghi explicit differences.
- Xác định tests nào bị ảnh hưởng.
- Làm runtime verification thích hợp.
- Có thể nâng risk/residual uncertainty.
- Không tự tái dùng staging PASS cho cả production.

### 32.4. Feedback khi có incident hoặc bypass

Nếu một vụ việc cho thấy scanner không phát hiện lỗi:

1. Xác định threat path thực.
2. Review coverage và rule/model assumptions.
3. Viết targeted regression test an toàn.
4. Bổ sung roles/fixtures/endpoints còn thiếu.
5. Cải thiện error/timeout handling.
6. Reassess historical releases theo artifact.
7. Update triage/gate policy.
8. Đo effectiveness của cải tiến.

Mục tiêu là **giảm xác suất tái phát lỗi hệ thống**, không chỉ đóng incident ticket.

## 33. KPI/KRI cho chương trình dynamic testing trong pipeline

| Chỉ số | Ý nghĩa | Giới hạn |
| --- | --- | --- |
| **Required-job completion rate** | Jobs bắt buộc chạy và hoàn tất | Hoàn tất không đồng nghĩa secure |
| **Authenticated coverage** | Có vào được protected operations với roles đúng | Login thành công chưa chắc data-path tested |
| **Risk-weighted API coverage** | Security requirements quan trọng đã test | Phải định nghĩa denominator |
| **Cross-tenant negative test coverage** | Những boundaries nhiều tenant có tests | Có test chưa chắc fixture/oracle đúng |
| **Unreviewed new API operations** | Attack surface mới thiếu tests | Spec có thể không đầy đủ |
| **Scanner partial/timeout rate** | Reliability của testing controls | Zero timeout không chứng minh quality |
| **New confirmed findings by priority** | Risks mới được phát hiện | Phụ thuộc scan coverage |
| **False-positive/false-negative trend** | Rule/tool effectiveness | Triage phải khách quan |
| **Time to triage** | Tốc độ đánh giá findings | Cần clock definition |
| **Time to verified remediation** | Thời gian giảm risk có evidence | Merge PR chưa đủ |
| **Security regression escape rate** | Findings chỉ được thấy sau release | Runtime detection visibility có hạn |
| **Exception age/expiry** | Risks được chấp nhận còn mở | Exception không là fix |
| **Flaky test rate** | Độ tin cậy security suites | Không được chữa bằng cách tắt test |
| **Evidence lineage coverage** | Tests liên kết được với artifact/deploy | Link đủ chưa chứng minh tests đúng |
| **Production post-deploy verification** | Những releases có runtime checks | Chỉ safe probes, không full production DAST |
| **Test-data cleanup success** | Không để artifacts/tokens dư thừa | Cleanup có thể fail im lặng |
| **Security scan induced incidents** | Scanner có gây side effect/outage | Cần giới hạn scope và guardrails |

### 33.1. Diễn giải số liệu mẫu

Giả sử pipeline có 30 security requirements đã xác định cho release:

- 19 có dynamic tests **thật sự chạy và đạt**.
- 4 có tests **FAIL**.
- 3 có tests **BLOCKED** do environment.
- 2 có tests **NOT_RUN**.
- 2 có **time-bound approved exceptions**.

Theo định nghĩa **executed-and-passed requirements coverage**, kết quả là **19/30 = 63,3%**.

Không nói “63,3% hệ thống an toàn”. Trong 11 requirements còn lại, chỉ cần một BOLA ảnh hưởng nhiều tenants cũng có thể tạo rủi ro rất lớn.

### 33.2. Tránh KPI tạo hành vi sai

- Hạ risk tier để không cần active scan.
- Loại endpoints khỏi allowlist để giảm findings.
- Mark NOT_RUN thành PASS.
- Chấp nhận false positive không có evidence.
- Tạo fixtures khiến negative tests luôn 404.
- Tắt logging để che security alerts.
- Merge rồi đóng finding không retest.
- Dùng scanner chỉ chạy anonymous để báo “all green”.
- Không chạy lại khi scanner rules thay đổi.

Assurance nên đo **actual control effectiveness và risk reduction**, không chỉ số lượng green builds.

## 34. Vai trò và RACI

| Vai trò | Trách nhiệm |
| --- | --- |
| **AppSec / Dynamic Testing owner** | Test strategy, DAST rules/modes, triage, gate policy |
| **Application/Engineering owner** | API/business invariants, fixtures, code remediation, tests |
| **QA/Security Testing** | Positive/negative tests, execution/retest, quality |
| **Platform/DevEx/CI owner** | Pipeline isolation, reliable jobs, artifact identity, evidence publishing |
| **SRE/Operations** | Test/staging environment, safe rollout, runtime checks, monitoring |
| **Identity/IAM owner** | Test principals, roles, token lifecycle, auth policy |
| **Data/Privacy owner** | Test data classification, minimization, retention |
| **Risk owner** | Residual risk/exception và release authorization theo thẩm quyền |
| **Assurance/Auditor** | Evidence relevance, completeness, independent conclusion |
| **Incident Response** | Containment khi scanner phát hiện active compromise hoặc gây incident |
| **Business/Product owner** | Critical business flows, side-effect boundaries và availability requirements |

RACI minh họa:

| Hoạt động | AppSec | App Owner | QA | CI/Platform | Risk Owner | Assurance |
| --- | --- | --- | --- | --- | --- | --- |
| Threat-to-test mapping | **A/R** | R | R | C | C | C |
| Safe scan scope/policy | **A/R** | C | R | R | I | C |
| Fixtures and test identities | C | **A/R** | R | C | I | C |
| Dynamic security test implementation | R | R | **A/R** | C | I | C |
| Scanner and CI reliability | C | C | R | **A/R** | I | C |
| Finding triage | **A** | R | R | C | C | C |
| Remediation and security regression | C | **A/R** | R | C | I | C |
| Release gate implementation | R | C | R | **A/R** | C | C |
| Residual-risk exception | C | C | C | I | **A/R** | I |
| Independent evidence review | C | C | C | C | I | **A/R** |

RACI phải theo tổ chức thực. Không cho cùng một cá nhân tự tạo test, tự sửa gate, tự phê duyệt exception và tự đóng high-risk finding khi policy yêu cầu independent review.

## 35. Những sai lầm thường gặp

### 35.1. Chỉ thêm scanner vào cuối pipeline

**Sai:** scan bắt đầu sau deploy mà không có test roles/data, báo vài headers rồi kết luận secure.

**Đúng:** threat-driven scope, preconditions, authenticated tests, coverage và evidence.

### 35.2. Chạy active DAST trên production không giới hạn

**Sai:** cron job tự quét toàn bộ URLs và mọi methods.

**Đúng:** được phép, controlled target, sandbox cho active/destructive, rate/stop conditions, production safe checks khi phù hợp.

### 35.3. Dùng một admin account cho mọi scan

**Sai:** admin có quyền xem mọi dữ liệu, nên scanner không phát hiện broken object authorization.

**Đúng:** user A/B và role matrix với negative tests.

### 35.4. Tin response 404 bất kể preconditions

**Sai:** test order B “deny” nhưng order B chưa hề tồn tại.

**Đúng:** xác nhận user B đọc B thành công rồi mới kiểm tra A không đọc B.

### 35.5. Xem zero alerts là toàn hệ thống an toàn

**Sai:** quên routes không crawl, session expired và business logic.

**Đúng:** validate coverage, test results và limitations.

### 35.6. Cho scanner lỗi nhưng gate PASS

**Sai:** tool timeout không sinh report nên findings count bằng 0.

**Đúng:** BLOCKED/INSUFFICIENT_EVIDENCE, có owner và follow-up.

### 35.7. Không gắn scan với image digest

**Sai:** quét A rồi deploy B.

**Đúng:** build identity → test deployment → report → production promotion.

### 35.8. Dùng token/secret production trong untrusted PR

**Sai:** bất kỳ PR script nào cũng có thể lấy secret.

**Đúng:** trust-level workflows, short-lived test credentials, protected environments.

### 35.9. Không reset dữ liệu test

**Sai:** mỗi scan tạo thêm orders/payment callbacks gây state drift.

**Đúng:** synthetic per-run fixtures, sandbox, cleanup và idempotency.

### 35.10. Bỏ API async và worker

**Sai:** POST export 202 là PASS.

**Đúng:** kiểm tra resulting file, recipient, tenant scope và audit.

### 35.11. Không kiểm tra business state

**Sai:** refund API trả 200 là đủ.

**Đúng:** xác minh ledger/payment side effects và duplicate handling.

### 35.12. Không kiểm soát rate/concurrency

**Sai:** scanner gây outage hoặc làm EDR flood.

**Đúng:** request budget, traffic controls, monitoring và safe stop.

### 35.13. Bỏ qua external providers

**Sai:** test gọi payment/email production thật.

**Đúng:** mock/sandbox integrations, allowlisted destinations và cleanup.

### 35.14. Suppress hàng loạt findings

**Sai:** mọi alerts trong một path được ignore vô thời hạn.

**Đúng:** evidence, owner, scope, expiry và re-review trigger.

### 35.15. Chỉ đo endpoint count

**Sai:** scanner đã gửi GET tới route nên authorization được cover.

**Đúng:** requirement–role–resource–expected outcome matrix.

### 35.16. Dùng flaky test retries để che security violation

**Sai:** lần đầu cross-tenant 200, lần hai 404 nên pipeline PASS.

**Đúng:** giữ toàn bộ attempts, điều tra race/inconsistency.

### 35.17. Không bảo vệ scan reports

**Sai:** raw HAR và cookies được upload public.

**Đúng:** redaction, restricted evidence store, retention và audit.

### 35.18. Không theo dõi scanner model/rules upgrades

**Sai:** finding count thay đổi nhưng tưởng code mới tạo lỗi.

**Đúng:** version rules, correlate new findings và rebaseline có review.

### 35.19. Coi DAST thay manual security review

**Sai:** workflow nghiệp vụ phức tạp không cần con người xem.

**Đúng:** DAST + API regression + threat model + code/architecture review.

### 35.20. Không test fail-safe behavior

**Sai:** khi authorization service timeout, API fallback allow.

**Đúng:** controlled fault injection và assertions theo policy.

### 35.21. Test ở staging rồi suy đoán production

**Sai:** identity gateway/WAF khác vẫn dùng staging PASS cho tất cả.

**Đúng:** parity limitations và safe runtime verification.

### 35.22. Quên release exception governance

**Sai:** một người click “override” không có rationale.

**Đúng:** risk owner, scoped approval, expiry, tracking và audit.

## 36. Checklist tích hợp Dynamic Testing vào pipeline

- [ ] Có service/asset owner, threat model và security requirements.
- [ ] Phân biệt DAST/IAST, API security tests, SAST, SCA và pentest.
- [ ] Có risk-based test triggers cho PR, release, scheduled và incident.
- [ ] Có inventory APIs, endpoint operations, roles, tenants và trust boundaries.
- [ ] Có target allowlist, approved environment identity và stop conditions.
- [ ] Scanner mode passive/active được định nghĩa, không gọi chung là “scan”.
- [ ] Active scans chỉ chạy khi có authorization/safe environment.
- [ ] Scanner egress/network access bị giới hạn theo scope.
- [ ] Có synthetic fixtures và sandbox providers.
- [ ] Data setup/teardown có owner, idempotency và isolation.
- [ ] Có user A/B khác tenants và role-level test identities.
- [ ] Auth tokens được scoped, không lưu raw trong report/log.
- [ ] Không cấp privileged secrets cho untrusted PR.
- [ ] Có test preconditions để tránh 401/404 false PASS.
- [ ] Positive tests đảm bảo chức năng hợp lệ còn hoạt động.
- [ ] Negative tests cho cross-user, cross-tenant và privilege.
- [ ] Tests cho invalid/expired/revoked session khi áp dụng.
- [ ] Có tests cho business invariants như refund/idempotency.
- [ ] Có tests cho cache/export/worker/webhook paths phù hợp.
- [ ] Failure modes và fail-safe behavior được kiểm tra trong lab.
- [ ] DAST crawling/authenticated coverage được xác nhận.
- [ ] API contract/runtime inventory được so với scan scope.
- [ ] Test tool phiên bản, rule pack và scanner image được quản lý.
- [ ] Runner permission và artifact provenance được review.
- [ ] Build artifact digest được kiểm tra trước khi chạy tests.
- [ ] Scan runs có request/time/rate/concurrency budgets.
- [ ] Scanner execution status được tách findings status.
- [ ] FAIL/BLOCKED/NOT_RUN/PARTIAL không được auto chuyển PASS.
- [ ] Report không rỗng do scanner mất session/target bị sai.
- [ ] Results được normalized/deduped và triage theo risk context.
- [ ] Findings có owner, priority, remediation plan và retest.
- [ ] False-positive/suppression có evidence, scope và review trigger.
- [ ] Release gate có policy version, independent exception control.
- [ ] Reports/logs được redacted và lưu ở protected evidence store.
- [ ] Có CI run ID, test suite version, environment/config identity.
- [ ] Có artifact digest trace từ build/test tới deployment.
- [ ] Production verification dùng safe tests và audit/monitoring.
- [ ] Post-release monitoring và scheduled scans bổ sung coverage.
- [ ] Có trigger chạy lại khi API/IdP/tenant model/rules thay đổi.
- [ ] Metrics phản ánh actual risk reduction, không chỉ xanh pipeline.
- [ ] Assurance conclusion nêu limitations, exclusions và residual risk.

**Checklist không tự chứng minh control effective**; cần actual executed tests và evidence phù hợp để kết luận.

## 37. Bài tập thực hành

### Bài tập 1 — Lập pipeline test matrix

Một Orders API có login, GET order, refund, export, admin settings và webhook. Hãy:

1. Xác định threat scenarios.
2. Chọn test jobs cho PR/release/staging.
3. Xác định passive/active DAST scope.
4. Thiết kế user A/B và tenant fixtures.
5. Viết những hard release gates.
6. Chỉ rõ evidence phải được giữ.
7. Nêu jobs nào có thể chạy song song.

### Bài tập 2 — Phát hiện false PASS

Security test user A GET order B trả 404 và CI PASS. Sau đó phát hiện order B chưa từng được seed.

Hãy viết:

- Root cause của false PASS.
- Preconditions cần assert.
- Positive control test cho B.
- Thay đổi fixture setup và cleanup.
- Cách tránh lặp ở những security tests khác.
- Quy trình review kết quả cũ đã được báo PASS.

### Bài tập 3 — Scanner job timeout

Một DAST job timeout sau 70% endpoints. Report có 0 High findings.

Hãy thiết kế:

- Execution status.
- Coverage assessment.
- Release decision.
- Owner và investigation.
- Retry/partial scan strategy.
- Điều kiện exception/deferral.
- Evidence phải được lưu.

### Bài tập 4 — Untrusted PR

Một pull request thay scan target URL sang internal metadata endpoint, trong khi CI job có privileged token.

Hãy phân tích:

- Trust boundaries.
- Những kiểm soát phòng ngừa ở CI/network/identity.
- Target validation trước scan.
- Rủi ro supply chain.
- Logs/audit cần có.
- Quy trình triage nếu đã có traffic ra ngoài.

Không thực hiện quét thử vào endpoint thật ngoài phạm vi được phép.

### Bài tập 5 — Async export

Một POST /exports trả 202, sau đó worker tạo ZIP và cung cấp link.

Hãy thiết kế tests cho:

- Actor A/tenant A hợp lệ.
- Forged tenant B event.
- Duplicate queue delivery.
- Link expiry và recipient scope.
- Worker service privilege.
- Audit.
- Correlation run ID và cleanup.

### Bài tập 6 — Artifact mismatch

Scanner quét image digest X trên staging, nhưng production deployment đang dùng digest Y cùng tag release.

Hãy:

- Giải thích vì sao assurance chain bị đứt.
- Xác minh provenance/digest của X và Y.
- Chọn re-test/rebuild/promotion action.
- Thiết kế release gate ngăn việc lặp lại.
- Nêu cách kiểm tra runtime trên tất cả replicas.

### Bài tập 7 — Reporting và KPI

Giả sử 24 security requirements:

- 14 PASS có evidence.
- 3 FAIL.
- 4 BLOCKED.
- 2 NOT_RUN.
- 1 DEFERRED được phê duyệt.

Hãy viết report không gộp các trạng thái, tính executed-and-passed coverage, nêu priority theo risk và conditions để đánh giá lại.

### Bài tập 8 — SAST và DAST khác kết luận

SAST báo dữ liệu request đến raw SQL sink. DAST trong staging không phát hiện injection.

Hãy phân tích:

- Tool models và test coverage.
- Input/entry point có reachable không.
- Scanner có authentication/parameters đúng không.
- Có WAF hoặc SQL binding mitigation không.
- DB layer và query code cần xem thêm gì.
- Vì sao không thể đóng finding chỉ vì DAST không báo.
- Cách tạo safe regression test.

### Bài tập 9 — Emergency patch

Một lỗ hổng API đang bị khai thác thực tế cần emergency patch, nhưng full active DAST mất nhiều thời gian và có thể gây side effects.

Hãy thiết kế:

- Containment trước.
- Targeted mandatory security tests.
- Minimal critical business smoke.
- Approved deferred tests.
- Safe rollout/monitoring.
- Runtime verification.
- Decision authority, evidence và post-incident follow-up.

## 38. Câu hỏi tự kiểm tra

1. Tích hợp dynamic security testing vào pipeline có mục tiêu bảo mật nào?
2. DAST khác SAST/SCA ở điểm nào?
3. Tại sao generic DAST scanner khó tự kiểm chứng BOLA trong SaaS?
4. Passive scanning có hoàn toàn không gửi request không?
5. Active DAST có những rủi ro nào đối với production?
6. Vì sao scanner cũng là một thành phần supply-chain cần kiểm soát?
7. Pipeline cần biết canonical target identity trước khi scan vì sao?
8. Tại sao không lấy test URL trực tiếp từ untrusted PR?
9. Một test role matrix nên gồm những principal/resource contexts nào?
10. Scanner dùng superadmin duy nhất có thể bỏ lỡ loại lỗi gì?
11. Token của test user cần được bảo vệ như thế nào?
12. Vì sao 401/302 hàng loạt không thể coi là full coverage?
13. Security test trả 404 cần những preconditions nào để tránh false PASS?
14. BOLA khác BFLA ở đâu?
15. Làm sao test authorization sau khi user bị revoke?
16. Vì sao API trả 202 không chứng minh worker export đúng quyền?
17. Webhook replay tests cần kiểm tra kết quả nào ngoài HTTP status?
18. Khi nào cần test duplicate event/idempotency?
19. Failure modes của authorization policy service nên kiểm tra gì?
20. Khi nào active fuzzing phù hợp với scheduled job hơn PR?
21. IAST hỗ trợ điều gì và không chứng minh điều gì?
22. Scanner timeout và scanner không có finding phải phân biệt thế nào?
23. Report rỗng do mất session nên có status nào?
24. Vì sao CI exit code 0 không đồng nghĩa security gate PASS?
25. Scan completion khác scan coverage ra sao?
26. Endpoint count coverage có thể gây hiểu nhầm thế nào?
27. Vì sao cần role–resource–expected outcome matrix?
28. Artifact digest liên quan thế nào tới test trustworthiness?
29. Nếu production có gateway config khác staging, nên kết luận ra sao?
30. Vì sao cần build once/promote same artifact khi có thể?
31. Những secrets nào có thể rò qua HAR/DAST reports?
32. Làm sao ngăn một scanner job compromised dùng production credentials?
33. Vì sao scanner/rule versions cần nằm trong evidence?
34. Một finding DAST có phải bằng chứng exploit thành công không?
35. False positive và false negative có thể xảy ra vì sao?
36. Khi nào có thể cho finding false-positive disposition?
37. Severity scanner khác organizational risk priority thế nào?
38. Những điều kiện nào có thể chặn release dù không có High alerts?
39. Warn-only scan có thể được sử dụng hợp lý ở giai đoạn nào?
40. Risk exception phải ghi những dữ liệu gì?
41. Vì sao một test cross-tenant lỗi ở attempt đầu nhưng PASS khi retry không được bỏ qua?
42. Những nguyên nhân nào làm async security tests flaky?
43. Cleanup test data cần đảm bảo không xóa dữ liệu của job khác như thế nào?
44. Dynamic tests có thể tự tạo outage bằng cách nào?
45. Thế nào là safe production post-deploy verification?
46. Khi nào cần re-run test suite dù source code không đổi?
47. SAST tìm path nhưng DAST không tái hiện thì phải triage thế nào?
48. Security regression test khác test rule của scanner ở đâu?
49. Tại sao a security scan artifact chưa chắc đủ làm assurance evidence?
50. Design, implementation và operating effectiveness khác nhau ra sao?
51. Các thành phần nào phải có trong một evidence chain hoàn chỉnh?
52. Kết luận “pipeline green” có giới hạn quan trọng nào?
53. Một release có 60% dynamic requirements PASS có nghĩa production an toàn 60% không?
54. Vì sao business logic flaws cần test oracle được viết riêng?
55. Những trigger nào làm test scope cũ mất hiệu lực?
56. Ai có quyền approve risk exception và ai xác minh remediation?
57. CI gates nên phản ứng thế nào khi policy file bị untrusted PR thay?
58. Làm sao phân biệt test lỗi do môi trường với test phát hiện lỗ hổng?
59. Khi cần containment khẩn cấp, có nên chờ full active scan không?
60. Viết một security claim và ba negative tests cho API export nhiều tenant.

## 39. Tổng kết

**Tích hợp pipeline** trong **Dynamic testing** biến hoạt động kiểm tra một ứng dụng đang chạy thành **quy trình lặp lại, có phạm vi, có kiểm soát an toàn và có bằng chứng** trong CI/CD. Một tích hợp tốt không chỉ “chạy DAST tool”, mà phối hợp **threat-driven API tests, authenticated role/tenant fixtures, scoped passive/active scanning, environment parity, non-destructive testing, security regression, result completeness, risk-based release gates và post-deployment verification**.

Cần đặc biệt chú ý:

- **DAST finding không tự là exploit proof; không có finding không chứng minh không có vulnerability.**
- **Crawl được endpoint không có nghĩa đã kiểm chứng business authorization.**
- **Scanner job lỗi, mất session hoặc chỉ scan một phần không được báo PASS.**
- **Quét đúng ứng dụng nhưng sai artifact/config không đủ để kết luận production.**
- **Scanner có permissions/network/secrets nên bản thân nó là một attack surface.**
- **Mitigation hoặc approved exception không đồng nghĩa vulnerability đã fixed.**
- **Các test phải có expected outcome, precondition, actual result, owner và retest.**

Trong module **SECURITY_SECURITY_ASSURANCE**, giá trị cuối cùng của pipeline nằm ở **chuỗi truy vết từ security objective, threat/risk và requirement → build/deployed identity → dynamic test execution → evidence và coverage → triage/finding → remediation/retest → operating assurance**. Kết luận phải nêu rõ **phạm vi, phiên bản, môi trường, identities, tool/rule versions, exclusions, độ tin cậy và residual risk**, và được cập nhật mỗi khi API, kiến trúc, deployment hoặc threat context thay đổi.

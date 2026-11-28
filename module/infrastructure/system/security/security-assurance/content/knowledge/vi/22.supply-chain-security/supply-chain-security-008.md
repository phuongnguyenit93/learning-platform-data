# Repository trust: thiết lập và kiểm chứng độ tin cậy của kho mã nguồn

## Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích **repository trust** trong *software supply chain security* và phân biệt **độ tin cậy của nguồn mã** với **độ an toàn của nội dung mã**, **độ tin cậy của build** và **độ tin cậy của artifact được triển khai**.
2. Xác định trust boundaries từ contributor → repository → branch/commit/tag → CI/CD → artifact registry → production, bao gồm **fork, pull request, third-party workflow, dependency và submodule**.
3. Đánh giá các yếu tố tạo thành niềm tin có bằng chứng: **repository identity, ownership, provenance, change authority, branch/tag controls, reviewer independence, commit integrity, release authorization và auditability**.
4. Phân tích các kịch bản tấn công: **repository takeover, compromised maintainer, malicious pull request, workflow injection, force-push/tag replacement, dependency/submodule substitution, credential theft và giả mạo provenance**.
5. Thiết kế các kiểm soát **least privilege, branch protection/ruleset, required review, CODEOWNERS, protected release tags, ephemeral credentials và isolation cho untrusted CI jobs** theo rủi ro.
6. Hiểu giới hạn của **signed commits/tags**, checksum, SBOM và build attestations: chúng chứng minh một số thuộc tính nhất định, **không tự chứng minh mã không có lỗ hổng hoặc hành vi độc hại**.
7. Chuyển threat scenarios thành **security requirements, acceptance criteria, negative/integration tests, evidence và remediation/retest** để đưa ra assurance claim có giới hạn.
8. Vận hành chương trình repository trust liên tục qua **inventory, policy drift, access reviews, release traceability, incident response và change-triggered reassessment**.

Trong module **SECURITY_SECURITY_ASSURANCE**, nhiệm vụ là xây dựng cách đánh giá **có bằng chứng** rằng hệ thống đáp ứng mục tiêu bảo mật, từ phân tích rủi ro và yêu cầu đến security controls, kiểm thử, audit và xử lý phát hiện. Chủ đề **Repository trust** thuộc chương **Supply chain security** đặt một câu hỏi thiết yếu trước mọi hoạt động build hoặc deploy: **Đoạn mã và cấu hình này thực sự đến từ kho nào, ai có thể thay đổi nó, phiên bản nào đã được phê duyệt, và chuỗi bằng chứng từ thay đổi đến release có thể bị làm giả hoặc bị bỏ qua tại đâu?**

> **Nguyên tắc cốt lõi:** Không tin một kho mã chỉ vì nó nằm trong organization quen thuộc, có nhãn “official”, có lịch sử nhiều năm hoặc có commit được ký. **Repository trust** phải được xây dựng từ **nguồn gốc xác minh được, quyền thay đổi được giới hạn, quy trình phê duyệt thực thi được, các ranh giới CI/CD an toàn và bằng chứng liên kết chính xác commit–build–artifact–deployment**.

## 1. Repository trust là gì?

**Repository trust** là mức độ có căn cứ để tin rằng **dữ liệu và thay đổi được lấy từ một kho mã cụ thể** do các chủ thể có thẩm quyền quản lý, theo những chính sách được chấp thuận và trong một chuỗi xử lý không bị thay thế, can thiệp hoặc nâng quyền trái phép.

Kho mã có thể chứa không chỉ source code mà còn:

- Infrastructure as Code (IaC), deployment manifests và policy-as-code.
- Build scripts, CI/CD workflow definitions và container build files.
- Test code, test fixtures, dependency manifests và lockfiles.
- Git submodules, Git LFS pointers, generated code và references tới artifact bên ngoài.
- Documentation chứa lệnh cài đặt, bootstrap scripts và release instructions.
- Các cấu hình có thể ảnh hưởng đến signer, package publishing hoặc production deployment.

Vì vậy, thay đổi repository có thể **ảnh hưởng đường điều khiển production** ngay cả khi không sửa một dòng source code của ứng dụng.

### 1.1. Các khái niệm phải tách bạch

| Khái niệm | Câu hỏi cần trả lời | Điều nó **không** tự chứng minh |
|---|---|---|
| **Repository identity** | Đây có đúng kho/project/owner được phê duyệt? | Nội dung bên trong là an toàn |
| **Contributor identity** | Thay đổi do danh tính nào tạo và đưa lên? | Người đó không bị chiếm tài khoản |
| **Change authorization** | Ai được merge, sửa policy và đẩy tag? | Mã đã được test đủ rủi ro |
| **Commit identity/integrity** | Commit object nào đang được tham chiếu? | Commit đó có được phê duyệt hoặc không độc hại |
| **Signed commit/tag** | Chữ ký hợp lệ với key/identity nào và trust policy nào? | Key owner có đáng tin hay source không có lỗ hổng |
| **Protected branch** | Các thay đổi vào nhánh được kiểm soát thế nào? | Mọi admin/bot không thể bypass |
| **Verified build provenance** | Artifact này được tạo bởi builder/workflow nào từ input nào? | Source được review đúng hoặc artifact không có lỗ hổng |
| **Artifact integrity/digest** | Artifact có trùng byte với digest đã xác minh? | Digest/nguồn phân phối ban đầu có được tin không |
| **SBOM** | Tập component/dependency nào được khai báo/phát hiện? | Danh sách hoàn toàn đầy đủ hoặc component an toàn |
| **Security assurance** | Claims nào được hỗ trợ bởi controls, tests và evidence trong scope? | Mọi rủi ro chưa biết đã biến mất |

**Trust** cần gắn với **một claim cụ thể**. Ví dụ “Kho đã bảo vệ production branch không cho merge không review trong release 2.5” có thể kiểm chứng; “Kho này đáng tin tuyệt đối” thì không.

### 1.2. Đường dẫn repository không phải bằng chứng đủ

Một URL hiển thị có thể trông hợp lệ nhưng cần xem:

- Host thực, repository owner/organization ID và repository ID chính thức.
- Tên có bị **đổi, chuyển organization, xóa và tạo lại** hoặc bị typosquatting không?
- Người sở hữu URL có thẩm quyền với project nào?
- Kết nối/SSH host key/certificate có được xác minh không?
- Người dùng đang fetch từ **fork**, mirror, registry source archive hay upstream?
- Revision được ghim bằng **commit digest** hay dùng mutable branch/tag?
- Có redirects/submodules/dependencies trỏ sang nơi khác không?

Ví dụ `example-org/payment-core` và `example-0rg/payment-core` chỉ khác một ký tự nhưng có thể là hai nguồn không liên quan. Tên repository gần giống không phải bằng chứng danh tính.

### 1.3. Repository trust là thuộc tính theo thời gian

Một repo có thể đạt review hôm qua nhưng không còn đạt hôm nay:

- Maintainer mới được trao quyền admin.
- Branch protection bị tắt trong 10 phút.
- Required check bị thay bằng workflow khác.
- Một bot token không còn giới hạn scope.
- Release tag bị xóa và tạo lại.
- Một dependency source đổi owner hoặc URL.
- CI workflow bắt đầu chạy code của fork với secrets production.

Do đó phải biết **effective configuration tại thời điểm hành động**, không chỉ có screenshot cấu hình cũ.

## 2. Trust boundaries trong chuỗi repository → release

### 2.1. Sơ đồ dòng chảy mã nguồn

~~~mermaid
flowchart TD
    C["Contributor / developer"] --> PR["Pull request / proposed change"]
    F["External fork / collaborator"] --> PR
    PR --> R["Protected repository / review gate"]
    R --> COMMIT["Approved commit / immutable identifier"]
    COMMIT --> CI["Trusted CI build workflow"]
    CI --> DEP["Dependencies / package registries"]
    CI --> ACT["Actions / plugins / build tools"]
    CI --> A["Artifact + digest"]
    A --> AT["Provenance / attestation"]
    A --> REG["Artifact registry"]
    REG --> D["Deployment admission / release gate"]
    AT --> D
    D --> P["Production runtime"]
    R --> AUD["Change audit / policy evidence"]
    CI --> AUD
    D --> AUD
~~~

Sơ đồ giản lược. Mỗi bước có thể nằm ở một organization, account hoặc provider khác nhau. Chỉ vì repo và CI nằm trên cùng một nền tảng SaaS không có nghĩa **không có trust boundary**.

### 2.2. Ma trận boundary crossing

| Boundary ID | Crossing | Trust assertion cần xác minh |
|---|---|---|
| **SC-TB-01** | Contributor/fork → Pull request | Ai có thể đề xuất thay đổi? Có bị coi là untrusted code? |
| **SC-TB-02** | Pull request → Protected branch | Ai review/approve/merge? Có bypass, stale approval, self-review không? |
| **SC-TB-03** | Repository → CI runner | Workflow nào được chạy, với quyền gì và từ revision nào? |
| **SC-TB-04** | CI → Third-party action/build tool | Code/tool của bên ngoài có được pin, review và hạn chế quyền? |
| **SC-TB-05** | Build → Dependencies/submodules | Source, version, integrity và registry/mirror có được xác minh? |
| **SC-TB-06** | Commit/tag → Release artifact | Build inputs và provenance có gắn đúng commit/source? |
| **SC-TB-07** | CI/artifact → Registry | Ai có quyền publish/replace artifact và metadata? |
| **SC-TB-08** | Registry → Production | Chỉ artifact có digest/provenance hợp lệ mới được deploy? |
| **SC-TB-09** | Maintainer/admin → Repo policy | Ai có thể đổi branch rules, secret, workflow và release? |
| **SC-TB-10** | Repo/CI → Audit systems | Ai sửa/xóa được change logs và evidence? |

Tại mỗi boundary, kiểm tra **authentication, authorization, integrity, scope, audit, expiration, failure behavior và possible bypass paths**.

### 2.3. Trust graph thay vì nhãn “official”

Một claim bảo mật cần chuỗi lập luận:

1. **Repo được xác thực** là nguồn được tổ chức chỉ định.
2. **Commit được chọn** là revision cụ thể và đã đi qua policy change phù hợp.
3. **Builder được tin theo policy** chạy workflow đã được xét duyệt, trong môi trường giới hạn.
4. **Dependencies/build inputs** được quản lý và kiểm tra theo policy.
5. **Artifact được gắn digest và provenance** với commit, builder và inputs.
6. **Deployment gate xác minh** artifact/provenance và environment được phép.
7. **Audit evidence** cho phép reviewer đối chiếu những bước trên.

Chỉ cần một đường cho phép **manual upload image không kiểm tra provenance** hoặc một bot có thể **merge và deploy mà không phải qua review**, chain of trust có thể bị vượt.

### 2.4. Control plane và data plane

Repository là một phần **software delivery control plane**: người có quyền thay build/workflow có thể thay cách production được tạo ra.

Các đường cần review riêng:

- Source code → application behavior.
- CI workflow → runner quyền đọc secrets/publish artifacts.
- IaC code → cloud IAM/network/data resources.
- Policy-as-code → authorization rules.
- Release automation → production deployment.
- Incident/recovery scripts → emergency access.

Quyền sửa **CI workflow hoặc repository settings** có thể nguy hiểm hơn quyền sửa một file tài liệu, dù cả hai đều là “write access to repository”.

## 3. Threat modeling cho repository trust

### 3.1. Assets cần bảo vệ

- Source code, review history, default branch và release tags.
- Repository settings: branch/ruleset policies, integrations, webhooks và collaborators.
- CI/CD workflows, runner images, environment variables và secrets.
- Bot/service credentials, signing identity, publisher tokens và deploy keys.
- Artifact provenance, SBOM và release attestations.
- Dependency manifests/lockfiles, submodule references và external scripts.
- Build outputs, images/packages, deployment configurations.
- Audit logs, approval events và incident evidence.

### 3.2. Các attacker capabilities

Không phải attacker nào cũng có cùng quyền. Cần phân biệt:

| Kẻ tấn công/nguồn lỗi | Có thể làm gì? | Không được mặc định có thể làm gì? |
|---|---|---|
| **External PR author** | Gửi patch, test code, docs hoặc thay workflow được đề xuất | Tự merge vào branch protected hoặc đọc repo secrets |
| **Compromised developer** | Sử dụng quyền mà tài khoản developer đang có | Tự động có quyền admin nếu chính sách đúng |
| **Compromised maintainer** | Có thể approve/merge/tag theo quyền được cấp | Tự động sửa tất cả org settings nếu quyền đã tách |
| **Compromised CI dependency** | Chạy code trong bước CI gọi nó, theo quyền runner | Vượt sandbox hoặc sở hữu publisher secret nếu không được cấp |
| **Registry/package attacker** | Publish package độc hại khi chiếm tên/quyền tương ứng | Thay artifact đã bị verify digest ở mọi nơi |
| **Repo administrator insider** | Có thể sửa rules/permissions nếu được cấp | Không nhất thiết xóa được independent audit logs |
| **Malicious build script** | Gửi network requests/đọc files mà runner cho phép | Không được đọc prod secrets nếu untrusted runner tách biệt |

### 3.3. Kịch bản tấn công phổ biến

| Kịch bản | Entry point | Rủi ro | Controls cần review |
|---|---|---|---|
| **Typosquatted repo** | URL/pull upstream giả | Tải/chạy mã không thuộc publisher mong đợi | Allowlisted org/repo identity, source pinning |
| **Repository takeover** | Tài khoản/token maintainer bị lộ | Inject mã và phát hành giả | MFA/phishing-resistant auth khi phù hợp, least privilege, reviews, audit |
| **Untrusted PR workflow injection** | Code/script PR chạy với privileged token | Exfiltrate secrets hoặc sửa release | Untrusted runner, read-only token, protected environment |
| **Branch-rule bypass** | Admin/bot có đường merge trực tiếp | Mã chưa được review vào protected branch | Effective rules, restrict bypass, audit/review |
| **Force-push/tag move** | Ref có thể bị thay | Source release bị tráo sau phê duyệt | Protected refs, immutable commit/digest binding |
| **Malicious third-party action** | Workflow gọi action/plugin ngoài | Thực thi code không tin cậy trong CI | Pin exact revision, review, permission isolation |
| **Submodule substitution** | Submodule URL/SHA hoặc remote thay | Kéo code từ nguồn sai | Allowlist origin, pin SHA, verify submodule policy |
| **Dependency confusion** | Package resolver chọn namespace/public source | Thay thư viện nội bộ bằng gói độc hại | Namespace/registry mapping, lock integrity và provenance |
| **Build provenance forgery** | Attestation không có nguồn đáng tin | Artifact độc hại mang nhãn “verified” | Validate signer/builder identity, issuer, subject/digest |
| **Unsigned manual deployment** | Deployment nhận image tag mutable | Deploy artifact không phải build đã xét duyệt | Digest admission và policy gate |
| **Workflow downgrade** | Attacker sửa gate/test config | Checks hiển thị xanh nhưng bị vô hiệu | Protect workflow/rules changes, independent enforcement |
| **Audit tampering** | Người sửa repo cũng xóa evidence | Không truy được ai đã đổi rules | Independent, protected audit collection |

### 3.4. STRIDE áp vào repository

| STRIDE | Ví dụ | Câu hỏi reviewer |
|---|---|---|
| **Spoofing** | Giả repo, giả maintainer, giả builder identity | Identity nào được xác minh bởi ai và bằng gì? |
| **Tampering** | Sửa source, tag, workflow, dependency hoặc artifact | Có digest, approval và integrity controls không? |
| **Repudiation** | Không có log merge, rule bypass hoặc secret use | Có actor, time, change, approval, evidence integrity? |
| **Information disclosure** | PR test đọc secrets, runner logs chứa token | Untrusted job có credentials/egress gì? |
| **Denial of service** | Runner abuse, malicious tests, repo/registry outage | Quota, isolation, restore và recovery plan? |
| **Elevation of privilege** | Contributor biến PR job thành release deploy | Ai có thể đi từ code submission tới trusted publish? |

### 3.5. Kịch bản mẫu: contributor → production

Giả định attacker chỉ có quyền tạo PR từ một fork. Nếu workflow build sử dụng quyền publish registry và deploy token trong lúc chạy test scripts từ PR, attacker có thể sửa script mà workflow chạy.

Đường tấn công:

1. Attacker gửi PR thêm lệnh trong test/build script.
2. CI chọn chạy code PR trên runner có privileged credentials.
3. Code độc hại cố truy cập token/artifact publisher theo quyền runner.
4. Nếu thành công, attacker có thể tác động tới artifact/release dù **chưa merge PR**.

Điểm yếu cốt lõi là **untrusted code crossing sang privileged execution context**, không chỉ chuyện “PR chứa code xấu”.

## 4. Xác minh repository identity và nguồn gốc

### 4.1. Repository identity là tập thuộc tính

Một **approved repository record** nên có:

- Host/provider instance, organization/project namespace và repository ID.
- Repository URL canonical và allowed alternate origins/mirrors.
- System/service owner, business/data owner và security contact.
- Visibility, classification và repositories được phép fork/mirror.
- Default protected branch, release branch/tag policy.
- Critical integrations, CI workflows, runner environments.
- Artifact package/image publishing destinations và deployment targets.
- Source of dependencies/submodules và policy exceptions.
- Ngày inventory, reviewer, phiên bản và change triggers.

Tên hiển thị có thể đổi; **repository identity cần được xác minh từ provider và chính sách tổ chức**, không chỉ so chuỗi URL do người gửi cung cấp.

### 4.2. Cloning và remote trust

Trong một workflow Git, cần lưu ý:

- HTTPS/SSH transport phải kiểm tra server identity/host key/certificate đúng cách.
- Không vô hiệu hóa kiểm tra host key/certificate vì clone thất bại.
- Chốt **origin URL** từ approved inventory và phát hiện thay remote.
- Không chạy script kiểu “curl từ nhánh main | shell” khi không xác minh origin, digest và nội dung theo policy.
- Với automation, ghim **commit SHA hoặc digest có nguồn đáng tin** thay vì dùng mutable branch name nếu yêu cầu reproducibility/release trust.
- Không coi việc biết một commit hash là đủ: cần biết **hash đó được lấy từ nguồn/phê duyệt nào**.

Một commit SHA định danh content của Git object theo cơ chế hash Git đang dùng; **không tự cấp niềm tin rằng nội dung được phê duyệt**. Nếu attacker điều khiển nguồn cung cấp SHA, một SHA hợp lệ vẫn có thể trỏ tới mã độc.

### 4.3. Fork và mirror

Fork/mirror có thể phục vụ phát triển và disaster recovery, nhưng:

- Fork không tự kế thừa quyền và chính sách của upstream.
- Mirror có thể chậm, sai cấu hình hoặc chứa nhánh chưa được phê duyệt.
- Chuyển repo hoặc đổi namespace cần cập nhật allowlists, workflows, signing/ownership policies và artifact provenance checks.
- Webhook/CI có thể vẫn trỏ tới repository cũ.
- Một repository cũ bị xóa rồi tái sử dụng namespace có thể tạo confusion nếu hệ thống chỉ tin URL.

**Trust record phải theo dõi identity và migration**, không chỉ theo dõi tên.

### 4.4. Signed commits và signed tags

Git có cơ chế ký commit/tag bằng khóa/danh tính tương ứng tùy cấu hình. Chữ ký có thể giúp kiểm tra:

- Git object chưa bị sửa sau ký theo cơ chế signature verification.
- Chữ ký phù hợp với một identity/key mà verifier tin theo trust policy.
- Release tag được tạo/phê duyệt bởi nhóm danh tính được phép, nếu policy dùng signed tag.

**Giới hạn quan trọng:**

- Chữ ký **không bảo đảm nội dung mã an toàn**.
- Một compromised key có thể ký thay đổi độc hại.
- Verified badge của hosting provider chỉ có nghĩa theo **chính sách xác minh của provider**; không tự thay tổ chức phê duyệt release.
- Tag có thể được **di chuyển** trừ khi ref protection và immutable release policy được enforce; chữ ký hợp lệ trên một tag object không giải quyết mọi dạng ref replacement.
- Commit signing có thể là một signal trong governance, không thay code review, protected branches hay build provenance.

### 4.5. Một checklist nguồn gốc tối thiểu

Trước khi dùng repository làm nguồn production:

1. Repo có nằm trong **approved inventory** không?
2. Organization/repository identity và URL canonical đã xác minh chưa?
3. Có owner và contact chịu trách nhiệm cấp/quyền thay đổi?
4. Revision được chọn là **commit ID cụ thể** hay mutable ref?
5. Commit/tag có đi qua review/rules được yêu cầu không?
6. Dependency/submodule/scripts có thể kéo từ nguồn ngoài chưa được phê duyệt không?
7. Pipeline có lấy **chính revision đã approve** để build không?
8. Artifact digest/provenance có chứng minh chain đến revision đó không?

## 5. Governance: ai có quyền thay đổi nguồn tin cậy?

### 5.1. Nguyên tắc least privilege cho repository

Repository permissions thường có những tầng quyền như đọc, đề xuất thay đổi, viết, quản trị hoặc kiểm soát release; tên quyền cụ thể tùy host/provider. Review phải xác định **effective privileges**, không chỉ tên role:

| Chủ thể | Quyền tối thiểu cần xem xét | Không nên mặc định được phép |
|---|---|---|
| Developer | Tạo nhánh, PR, xem dữ liệu cần thiết | Bypass required review hoặc thay secrets production |
| Repository maintainer | Review/merge trong scope được giao | Xóa audit hoặc tự cấp organization admin |
| Release manager | Phê duyệt version/tag/release theo workflow | Sửa mọi branch rules không ghi nhận |
| CI build identity | Đọc revision, lấy dependencies, tạo build output | Có permanent cloud admin credentials |
| Publisher identity | Publish artifact tới registry đã định | Deploy mọi environment hoặc đọc source secrets |
| Deployment identity | Chỉ triển khai artifact đáp ứng admission policy | Tùy ý đẩy source/đổi branch protection |
| Security policy owner | Review/duyệt rule, audit exceptions | Tự thay, tự phê duyệt và tự xóa evidence |
| External contributor | Gửi PR, chạy test sandbox thích hợp | Đọc trusted secrets hoặc publish release |

**Separation of duties (SoD)** cần phù hợp criticality: người đề xuất không tự phê duyệt thay đổi nhạy cảm trong cùng một quy trình nếu chính sách yêu cầu review độc lập.

### 5.2. Protected branches và rulesets

Các khả năng cần xem xét khi platform hỗ trợ:

- Cấm push trực tiếp hoặc force-push vào branch release/protected.
- Chỉ merge qua PR có review từ người có thẩm quyền.
- Quy định required checks được tạo bởi **trusted workflow**.
- Phê duyệt lại khi có commit mới thay đổi nội dung PR, theo cấu hình phù hợp.
- Giới hạn **bypass actors** và ghi log khi override.
- Quy định CODEOWNERS/review cho security-sensitive paths.
- Cấm xóa branch/tag được bảo vệ trái policy.
- Kiểm soát ai có quyền thay rule/required checks.

**Cấu hình branch protection không tự đủ:** Một bot/admin bypass hoặc một workflow bị sửa để trả “success” giả có thể khiến gate không bảo vệ được đúng thuộc tính. Review phải kiểm tra **effective enforcement, bypass list và negative tests**.

### 5.3. CODEOWNERS và security-sensitive paths

Những nhóm file thường cần owner review nghiêm ngặt hơn:

- CI/workflow files và build scripts.
- IaC: cloud IAM, network, Kubernetes và secret mounts.
- Policy-as-code: AuthZ, WAF, release signing và admission.
- Dependency manifests và lockfiles.
- Deployment scripts, image build definitions và artifact publishing.
- Security monitoring, audit routing, retention và incident automation.
- KMS/key policy và cryptographic config.

**CODEOWNERS** trên một số nền tảng giúp xác định reviewer cho đường dẫn. Tuy nhiên:

- CODEOWNERS file cũng là **mã/cấu hình cần bảo vệ**.
- Pattern matching/owner assignment phải được kiểm tra trong thực tế.
- Không có effective branch rule yêu cầu owner review thì file CODEOWNERS có thể chỉ mang tính gợi ý.
- Reviewer được chỉ định có thể bị compromise hoặc không hiểu ngữ cảnh; cần threat-based review và SoD phù hợp.
- Bảo vệ directory **không thay kiểm soát hành vi**; thay file ít nhạy cảm vẫn có thể ảnh hưởng release qua transitive execution path.

### 5.4. Review independence

Một PR “đã được một người approve” chưa chắc thỏa:

1. Người approve có đúng team/role được phê duyệt tại thời điểm đó?
2. Người approve có phải tác giả/chủ thể cùng quyền đã bị chiếm?
3. Có thay đổi sau approval khiến nội dung không còn là bản được review?
4. Người merge có thể bypass gate không?
5. Required checks có chạy trên **commit mới nhất** và đúng environment không?
6. Có test thêm thay đổi trong submodule/lockfile/CI scripts không?
7. Có approval từ security/data owner cho thay đổi cấp quyền hoặc dữ liệu?

Đối với thay đổi rất nhạy cảm, tổ chức có thể áp hai người review độc lập hoặc release approval riêng. **Số reviewer là quyết định risk-based**, không có một số phù hợp mọi dự án.

### 5.5. Quản trị quyền bot và service integrations

Bot token và integration apps có thể:

- Merge PR, tạo branch/tag, sửa workflow.
- Đọc secrets hoặc đổi repository settings.
- Publish packages và deploy production.

Kiểm tra:

- Token scoped theo repository, action và environment; tránh organization-wide token không cần thiết.
- Ưu tiên **short-lived/ephemeral credentials** hoặc federation khi được hỗ trợ.
- Sử dụng machine identity riêng cho build, publish và deploy.
- Secrets được quản lý bằng nơi lưu phù hợp; không hard-code.
- Có rotation/revocation và review quyền sau khi thay người/project.
- Audit API actions của bots và phân biệt khỏi hành động con người.

Một bot có quyền vượt reviewer policy có thể là **critical bypass** kể cả UI branch rule vẫn bật.

## 6. Pull request từ nguồn không tin cậy

### 6.1. Không đồng nhất PR với code đáng tin

Pull request cho phép các chủ thể đề xuất code nhưng **source code trong PR chưa được phê duyệt**. Nếu runner thực thi test/build/install scripts từ PR, nghĩa là đã **chạy mã chưa tin cậy**, thường với mức đặc quyền của CI job.

Các file PR có thể thay đổi:

- Shell scripts được CI gọi.
- Unit tests có side effects.
- Dependency manifests làm tải package mới.
- Build plugins, lint plugins và code generators.
- Workflow files hoặc templates được nền tảng/runner diễn giải.
- Files chứa dữ liệu dùng trong command string, commit messages hoặc PR metadata.

Vì vậy không chỉ xem “đường source của ứng dụng”. **Tất cả input có thể được thực thi hoặc diễn giải trong workflow** phải được coi là untrusted cho tới khi vượt qua gate thích hợp.

### 6.2. Phân chia trusted/untrusted jobs

Một thiết kế kiểm soát có thể tách:

| Job class | Input | Quyền gợi ý | Kết quả được phép |
|---|---|---|---|
| **Untrusted PR validation** | Code của fork/PR chưa merge | Read-only, không secrets hoặc prod tokens, isolated runner | Test result/feedback |
| **Trusted branch CI** | Commit trên protected branch đã qua rules | Quyền build tối thiểu, kiểm soát dependency | Build artifact cần kiểm chứng |
| **Artifact publishing** | Approved source và trusted build result | Short-lived publish credential, allowlisted registry | Publish immutable artifact/digest |
| **Production deployment** | Signed/attested artifact theo policy | Environment-scoped deploy identity, approvals | Deploy artifact verified digest |
| **Admin policy changes** | Approved governance change | Scoped privileged identity, independent review | Thay rule/config có audit |

Một pipeline có thể có nhiều bước, nhưng **không được chuyển secrets sang untrusted code chỉ vì hai job cùng thuộc một workflow**.

### 6.3. Workflow injection và dữ liệu không đáng tin

Rủi ro xảy ra khi workflow:

- Nội suy PR title/branch/author/comment vào shell command không escape đúng.
- Chạy scripts trong PR bằng privileged identity.
- Tải code từ URL không ghim revision.
- Dùng artifact/cache của untrusted job làm executable input cho privileged job mà không kiểm tra provenance.
- Dựa vào một result string do PR có thể điều khiển để quyết định “approved”.

Biện pháp:

1. Phân loại mọi trường PR metadata là untrusted.
2. Không nội suy dữ liệu vào command strings; dùng API/parameterization và escape phù hợp.
3. Chỉ chạy untrusted code trong runner/job không có secrets nhạy cảm.
4. Bảo vệ quyền token/workflow permissions ở mức tối thiểu.
5. Giới hạn network egress và host filesystem khi threat model cần.
6. Đối với privileged steps, chỉ nhận **verified immutable inputs** từ trusted stage.

### 6.4. Đặc điểm của pull-request events phụ thuộc nền tảng

Một số CI provider có những event được chạy trong **ngữ cảnh nguồn** khác nhau: code của PR, workflow từ default branch, quyền token do sự kiện cấp, secrets có được đưa vào hay không. Không nên áp một mẫu tên event chung cho mọi sản phẩm.

Khi review, xác định rõ:

- Workflow file nào được diễn giải?
- Code từ revision nào được checkout và thực thi?
- Secrets/token permissions ở job nào?
- Runner có persist credentials hoặc cache giữa trusted/untrusted jobs không?
- Trigger tự động/manual approval có biến đổi trust boundary không?
- Có job có thể **commit, tag, publish hoặc deploy** sau khi đọc artifact từ PR chưa duyệt?

Một reviewer chỉ kiểm tra YAML “trông như read-only” mà không thử **effective token permissions** có thể bỏ sót quyền mặc định hoặc inherited permissions từ organization.

### 6.5. Cache và artifact poisoning giữa jobs

Một PR untrusted có thể ghi:

- Cache key chung với trusted build.
- Generated files được upload rồi trusted job tải về.
- Report hoặc test result được privileged process parse và thực thi.
- Container layer/build cache ảnh hưởng trusted release.

Cần:

- Tách cache namespace theo trust level, branch, dependency hash và policy.
- Xác minh integrity/provenance của artifacts trước khi đưa qua boundary.
- Không tái sử dụng workspace/runner persistent chưa được làm sạch từ untrusted job.
- Không coi một output file đáng tin chỉ vì nó được lưu trong CI artifact store.
- Test đường chuyển tiếp untrusted → trusted như một phần của supply-chain threat model.

## 7. Repository references, dependencies và external code

### 7.1. Mutable ref so với immutable source

| Tham chiếu | Đặc điểm | Cách giảm rủi ro |
|---|---|---|
| **Branch name** | Có thể thay đổi theo push/merge | Không dùng làm bằng chứng duy nhất của release |
| **Git tag** | Có thể bị di chuyển trừ khi bảo vệ | Protected tags + verify source commit/signature |
| **Commit hash** | Chỉ định Git object cụ thể | Verify approved origin, commit và policy |
| **Container image tag** | Thường mutable | Deploy bằng verified image digest |
| **Package version** | Có thể phụ thuộc registry guarantees; không tự bảo đảm nội dung không đổi | Lockfile, integrity hash, registry policy và provenance |
| **Third-party CI action version/tag** | Có thể trỏ revision khác theo thời gian | Pin exact verified revision và quản trị cập nhật |

Pinning giúp reproducibility/integrity, **không biến mã độc thành mã sạch**. Version/digest được pin vẫn cần review, vulnerability assessment và nguồn đáng tin.

### 7.2. Git submodules và Git LFS

Submodule trỏ tới một repo và commit khác. LFS giữ references/pointers tới objects được lưu ngoài Git history chính. Review:

- Submodule URL nằm trong approved list?
- Commit SHA trong submodule đã được review/phê duyệt hay chỉ được ghim?
- Submodule có thể bị thay URL hoặc path, kể cả nested submodules?
- LFS endpoint, object integrity và retention có phù hợp?
- Build có tự động fetch nguồn phụ mà không kiểm tra policy?
- Artifact provenance có ghi nhận những inputs này?

**Trust một repository chính không tự động truyền sang repository phụ**. Cần nhận diện các nguồn mã và build inputs xuyên qua boundary.

### 7.3. Package registries và dependency confusion

Dependency manifests/lockfiles làm kết nối tới:

- Public package registries.
- Private organization registries.
- Git URL dependencies.
- Vendor archives, release downloads.
- Build plugins và transitive dependencies.

Kiểm tra:

1. Package name/namespace có thuộc publisher được phép?
2. Resolver có ưu tiên private/public đúng chính sách hay có thể bị **dependency confusion**?
3. Version/digest/integrity được khóa ở lockfile và được enforce khi install?
4. Có nguy cơ **typosquatting** hoặc package namespace takeover?
5. Có transitive dependencies hoặc post-install scripts mang khả năng chạy code?
6. Có SBOM/provenance/vulnerability information và policy xử lý findings?
7. Registry credentials có bị gửi nhầm tới host không được phép?
8. Có mirror/proxy đáng tin và khả năng phát hiện drift?

Không nhầm **dependency vulnerability scan** với xác minh **nguồn gốc và quyền xuất bản package**. Một gói không có CVE vẫn có thể bị publisher compromise.

### 7.4. Dependency update automation

Bot tự động tạo PR cập nhật gói hoặc workflow rất hữu ích, nhưng:

- Bot PR vẫn phải đi qua review/required tests phù hợp rủi ro.
- Major release/maintainer change hoặc permission change cần review sâu hơn.
- Không cho bot có quyền vừa sửa chính sách, vừa tự approve và merge nếu governance cấm.
- Generated lockfile diff có thể chứa nhiều thay đổi; cần dependency provenance và integrity verification.
- Bot credentials có scope nhỏ và rotate được.

Một **green test** không tự chứng minh updated dependency không có hành vi độc hại hoặc lộ secret qua install scripts.

## 8. Build, artifact và provenance: repo trust kéo dài đến deploy

### 8.1. Tại sao merge đúng chưa đủ?

Giả sử commit `abc123` đã được review/merge đúng, nhưng CI build:

- Chạy trên runner bị compromise.
- Tải action từ tag mutable đã bị thay.
- Pull package mới từ registry ngoài mà không lock integrity.
- Dùng source archive từ mirror khác.
- Upload image và sau đó image tag bị đẩy lại.

Artifact triển khai có thể **khác với những gì được kỳ vọng từ commit đã approve**. Vì vậy repository trust là một phần của **delivery chain**, không phải điểm kết thúc ở merge.

### 8.2. Phân biệt các loại bằng chứng

| Evidence/technique | Có thể hỗ trợ claim | Không tự bảo đảm |
|---|---|---|
| Commit/review/merge records | Thay đổi vào branch theo quy trình đã định | CI runner không bị chiếm |
| Signed tag | Tag object được ký bằng identity/key được tin theo policy | Tag ref không đổi hoặc mã không độc hại |
| Source digest / Git object ID | Input source cụ thể đã được định danh | Input đó được phê duyệt |
| SBOM | Component inventory cho artifact/scope nhất định | Bản kê đầy đủ và không có malware |
| Build provenance attestation | Builder, source/input, command/config và artifact subject theo schema được chứng thực | Builder đáng tin nếu verifier không kiểm tra trust anchors |
| Artifact digest | Artifact không thay đổi byte so với expected digest | Expected digest không bị attacker thay |
| Package/image signature | Identity/key đã ký object/digest theo cơ chế | Signer có quyền được publish production |
| Deployment admission log | Policy gate đã kiểm tra một bộ điều kiện | Không có đường bypass hay runtime drift |

### 8.3. Liên hệ SLSA, SSDF và các công cụ

Có thể tham khảo những khung/thực hành như **SLSA** cho build provenance và supply-chain integrity, **NIST SSDF** cho quy trình phát triển phần mềm an toàn, hoặc các công cụ phân tích repo như **OpenSSF Scorecard**. Chúng đóng vai trò **nguồn tham chiếu/mẫu kiểm soát**, không phải chứng chỉ cho một repo cụ thể.

Với cơ chế ký/attestation (ví dụ hệ sinh thái **Sigstore**), verifier phải kiểm tra **identity, issuer/trust root, subject artifact digest, builder/workflow, expected repository và policy** phù hợp. Có signature hoặc attestation object được tải về **không đủ** nếu verifier không kiểm tra ràng buộc với tổ chức và artifact muốn deploy.

### 8.4. Provenance claim: những trường cần đối chiếu

Một policy kiểm tra build provenance có thể yêu cầu:

- Artifact digest/subject **trùng chính xác artifact được deploy**.
- Builder/workflow identity thuộc allowlist đã phê duyệt.
- Source repository identity và commit revision là đúng đối tượng.
- Workflow definition ở revision được phép hoặc được quản trị theo policy.
- Build input/dependencies có integrity và review thích hợp.
- Attestation signature/provenance issuer chain được xác minh.
- Không có policy exception không được chấp thuận.
- Deployment environment/target trùng scope của release.

Provenance mạnh vẫn **không sửa được source review sai**. Một commit được attacker merge hợp lệ qua compromised maintainer có thể tạo ra artifact với provenance hợp lệ. Đây là lý do **review, repository governance và build attestations** cần kết hợp.

### 8.5. Liên kết chính xác từ commit tới production

~~~mermaid
flowchart LR
  R["Approved repository ID"] --> C["Reviewed commit ID"]
  C --> B["Trusted builder + workflow"]
  D["Pinned dependencies + tools"] --> B
  B --> A["Artifact digest"]
  B --> P["Provenance attestation"]
  P --> V["Verifier / policy gate"]
  A --> V
  V --> REG["Registry / approved release"]
  REG --> DEP["Deploy exact digest"]
  DEP --> AUD["Runtime/effective deployment evidence"]
~~~

Nếu deployment chỉ dùng một **mutable image tag** mà không xác minh digest, chain có thể bị gãy ở bước cuối.

## 9. Security requirements cho repository trust

### 9.1. Từ rủi ro đến yêu cầu kiểm thử được

Một câu chung như **“Repository phải đáng tin cậy”** không cho biết kiểm tra gì. Hãy tách theo trust properties:

| Requirement ID | Phát biểu yêu cầu minh họa | Verification focus |
|---|---|---|
| **REPO-ID-01** | Source production phải đến từ repository ID/owner nằm trong approved inventory | Canonical repo identity, origin substitution tests |
| **REPO-CHG-02** | Thay đổi protected branch phải qua review/checks được phê duyệt, trừ emergency exception có thẩm quyền | Direct-push/bypass/stale-approval negative tests |
| **REPO-PR-03** | Code từ untrusted PR không được chạy với publishing/deployment secrets | CI event/runner permissions tests |
| **REPO-IAM-04** | Human/bot credentials chỉ có quyền tối thiểu theo vai trò và scope | Effective permissions/credential review |
| **REPO-SIGN-05** | Release revision phải được xác minh theo identity/signature policy nếu bắt buộc | Invalid/unknown signer tests |
| **REPO-REF-06** | Build/release dùng immutable, approved source revision; mutable refs không đủ làm evidence | Tag/ref replacement scenarios |
| **REPO-DEPS-07** | External actions/dependencies/submodules phải theo approved source/integrity policy | Malicious source substitution tests |
| **REPO-BUILD-08** | Artifact phải liên kết builder, workflow, source revision và digest qua provenance hợp lệ | Wrong source/builder/digest negative tests |
| **REPO-DEPLOY-09** | Production chỉ nhận artifacts thỏa release/admission policy, không dùng manual bypass không phê duyệt | Unauthorized manual deployment tests |
| **REPO-AUDIT-10** | Thay đổi quyền/rules, merge, publish và emergency override phải có protected audit evidence | Event completeness/SoD tests |
| **REPO-RECOVER-11** | Khi repo/CI/token compromise phải có containment, key revocation và rebuild/redeploy từ trusted source | Incident rehearsal/recovery drill |
| **REPO-DRIFT-12** | Effective repository/CI controls phải được so với approved baseline theo trigger/chu kỳ được duyệt | Drift detection và exception handling |

**Con số và ngưỡng** như số reviewers, session TTL, rotation period, attestation format, thời gian sửa findings cần xuất phát từ risk appetite, standards và quy định nội bộ. Không nên tự chọn số để requirement trông “SMART” nhưng không phù hợp kiến trúc.

### 9.2. Mẫu cấu trúc một requirement

> **[REPO-PR-03]** Đối với những workflow nhận code hoặc metadata từ pull request chưa được merge/phê duyệt, runner phải chạy trong context không chứa production secrets, publisher credentials hoặc quyền deploy và không được tự đưa executable artifacts sang trusted release job khi chưa qua verification gate. Mọi đường chạy bị cấm phải được ngăn trước hành động nhạy cảm và tạo evidence theo CI policy.

**Acceptance criteria:**

1. Untrusted PR test vẫn chạy được những checks được phép.
2. PR code không thể đọc privileged environment secrets qua standard job context.
3. PR event không thể publish package hoặc deploy production.
4. Cố đổi workflow/requested permissions trong PR không tự cấp quyền release.
5. Cố truyền artifact/cache từ untrusted job vào release job không vượt integrity/provenance gate.
6. Audit có workflow/revision/actor/job/permissions/outcome và không chứa secrets.

**Verification methods:** Effective CI configuration review, permissions matrix, negative test trên sandbox có phép, artifact lineage và production release policy review. Screenshot “permissions: read” không đủ nếu còn **environment inheritance, manual approvals hoặc runner reuse**.

### 9.3. Yêu cầu không chỉ áp vào mã nguồn

Một repository có code sạch nhưng workflow có thể:

- Deploy từ branch chưa được review.
- Truyền cloud admin secret vào test script của PR.
- Kéo external action từ tag mutable.
- Không xác minh digest sau artifact publishing.
- Cho admin tự thay branch rules mà không có independent audit.

Do đó phải viết security requirements cho **repository settings, access management, build workflows, artifact generation và deployment gates**, không chỉ coding standards.

## 10. Repository trust policy mẫu

### 10.1. YAML minh họa về yêu cầu kiểm soát

Đây là **mẫu giáo dục**, không phải schema chạy trực tiếp trên GitHub, GitLab, Bitbucket hoặc policy engine cụ thể. Khi triển khai cần ánh xạ sang provider capabilities, effective settings, enterprise policies và kiểm thử.

~~~yaml
repositoryTrustPolicy:
  id: REPO-TRUST-PAYMENTS-01
  version: "1.0"
  status: illustrative
  system: payments-platform
  environment: production

  ownerRoles:
    repository: Source Governance Owner
    security: Supply Chain Security Owner
    release: Release Authority
    risk: Payments Risk Owner
    verification: Security Assurance Team

  trustedRepository:
    providerReference: APPROVED-SCM-PROVIDER
    organizationIdReference: APPROVED-PAYMENTS-ORG-ID
    repositoryIdReference: APPROVED-PAYMENTS-REPO-ID
    canonicalOriginReference: APPROVED-ORIGIN-URL
    allowedMirrors: []
    approvedDefaultBranch: main

  sourceChanges:
    protectedRefs:
      - main
      - release-branches
      - release-tags
    approvalPolicyReference: REPO-CRITICAL-CHANGE-REVIEW
    requiredChecksReference: TRUSTED-CI-CHECK-CATALOG
    sensitivePaths:
      - ci-workflows
      - deployment-config
      - iam-policies
      - dependency-manifests
    policyOwnerReviewReference: SECURITY-OWNERSHIP-MATRIX
    bypassActorsReference: APPROVED-EMERGENCY-BYPASS-LIST
    forcePushPolicy: prohibited-on-protected-refs

  contributors:
    externalPullRequests: allowed-for-proposal-only
    untrustedCiPolicy:
      secretAccess: denied
      publishingPermission: denied
      deploymentPermission: denied
      runnerIsolationReference: UNTRUSTED-PR-ISOLATION
      cacheIsolationReference: CACHE-TRUST-BOUNDARIES

  buildInputs:
    sourceRevision: approved-immutable-commit-reference
    thirdPartyActions: approved-and-pinned
    dependencyRegistryPolicyReference: PACKAGE-SOURCE-POLICY
    submodulePolicyReference: SOURCE-ORIGIN-ALLOWLIST
    integrityVerification: required-by-input-type

  provenance:
    expectedBuilderIdentityReference: APPROVED-BUILDER-ID
    expectedWorkflowReference: TRUSTED-RELEASE-WORKFLOW
    subjectBinding: exact-artifact-digest
    sourceBinding: exact-approved-repository-and-commit
    verificationTrustRootReference: APPROVED-ATTESTATION-TRUST

  deployment:
    approvedRegistriesReference: PAYMENTS-REGISTRY-ALLOWLIST
    artifactSelection: verified-digest-only
    requireProvenanceCheck: true
    emergencyExceptionReference: SECURE-RELEASE-EXCEPTION-PROCESS

  audit:
    monitoredEvents:
      - repository-permission-change
      - branch-or-tag-policy-change
      - review-bypass
      - protected-branch-merge
      - release-tag-publish
      - workflow-secret-use
      - artifact-publish
      - deployment-admission-decision
    protectedEvidenceReference: SUPPLY-CHAIN-AUDIT-STORE

  assurance:
    acceptanceTestIds:
      - TEST-UNAUTHORIZED-DIRECT-PUSH
      - TEST-CODEOWNERS-REVIEW-REQUIRED
      - TEST-UNTRUSTED-PR-NO-PUBLISH
      - TEST-REF-REPLACEMENT-REJECTED
      - TEST-WRONG-BUILDER-PROVENANCE-REJECTED
      - TEST-WRONG-DIGEST-DEPLOY-REJECTED
      - TEST-POLICY-DRIFT-DETECTED
    evidenceReferences:
      - EV-EFFECTIVE-REPO-RULES
      - EV-PR-ISOLATION-TESTS
      - EV-PROVENANCE-ADMISSION-TESTS
    assessmentStatus: NOT_ASSESSED
    knownGaps:
      - legacy-manual-release-path-needs-review
~~~

**Cách đọc đúng:** `requiredChecksReference` hoặc `subjectBinding` mô tả ý định/requirement. Để kết luận đã đạt, cần **effective provider settings, workflow run records, signature/provenance verification và negative tests**. `assessmentStatus: NOT_ASSESSED` là có chủ ý vì YAML mẫu **không phải bằng chứng**.

### 10.2. Thông tin tối thiểu của một approved source record

~~~yaml
approvedSource:
  sourceId: SRC-PAYMENTS-CORE-01
  canonicalRepositoryId: SCM-ORG-001/REPO-042
  canonicalOriginReference: APPROVED-SCM-ORIGIN
  businessService: payments-platform
  classification: production-critical
  trustedReleaseRefs:
    - main
    - protected-release-tags
  maintainerApprovalGroup: PAYMENTS-MAINTAINERS
  securityApprovalGroup: SUPPLY-CHAIN-SECURITY
  builderIdentityReference: BUILD-PAYMENTS-APPROVED
  artifactRegistryReference: REG-PAYMENTS-PROD
  deploymentPolicyReference: POLICY-PROD-ADMISSION
  lastReviewEvidenceReference: EV-REPO-ACCESS-REVIEW-042
  currentAssessment: NEEDS_RUNTIME_VERIFICATION
~~~

Không dùng một bản record tĩnh được lưu trong Git cùng quyền sửa với source như **trust anchor duy nhất**. Cần nguồn quản trị policy/approval phù hợp và kiểm tra drift ở hiệu lực thực tế.

## 11. Thiết kế bộ kiểm thử repository trust

### 11.1. Các lớp kiểm tra

| Lớp | Cần chứng minh | Ví dụ evidence |
|---|---|---|
| **Design effectiveness** | Trust boundaries và controls được xác định đầy đủ, hợp lý theo threat model | Source inventory, threat model, approved policy, architecture review |
| **Implementation** | Repository/CI/registry settings thực thi policy trong scope | Effective rules, permissions, workflow configs, admission policy |
| **Operational effectiveness** | Thay đổi, merge, build và deploy thực trong kỳ tuân theo gates | Audit logs, PR records, provenance, build and deploy traces |
| **Failure-path assurance** | Khi signer, registry, policy engine hoặc CI lỗi, không tự chọn đường insecure | Fault injection/negative tests, runbooks, remediation |
| **Evidence integrity** | Attestations và logs có provenance, access protection, retention | Verification logs, independent audit, immutable references |

Một security review có thể xác nhận **thiết kế tốt** nhưng chưa có kết quả vận hành. Không tự suy “protected branch configured” tương đương “mọi thay đổi production đã được review”.

### 11.2. Negative tests quan trọng

- Tài khoản chỉ có quyền đọc thử **push trực tiếp** protected branch → bị chặn.
- Contributor có quyền viết nhưng không bypass thử **force-push hoặc xóa protected ref** → bị chặn.
- PR đổi một file security-sensitive sau approval → hiệu lực approval tuân theo policy.
- Tài khoản ngoài CODEOWNERS thử merge file workflow nhạy cảm → gate chặn theo rule.
- Untrusted PR chạy test thử sử dụng **publishing permission** trong sandbox → quyền không được cấp.
- PR artifact/cache bị đưa qua trusted publishing stage → provenance/integrity gate từ chối khi không hợp lệ.
- Build thử lấy third-party action từ ref chưa ghim → policy check không cho phép.
- Source từ fork/mirror chưa nằm trong inventory → release gate từ chối.
- Release tag bị di chuyển sau approval → digest/source revision mismatch được phát hiện.
- Artifact cùng tên/tag nhưng khác digest → production admission từ chối.
- Attestation có signature đúng nhưng **builder identity/repository ID** sai → từ chối.
- Deployment bằng đường thủ công không có provenance approval → từ chối/đòi approved exception.
- Admin thay branch rule không có approval → cảnh báo/finding và audit event.

Những thử nghiệm thay rule/ref hoặc đụng production secrets cần **môi trường sandbox được phép**, rollback và stop conditions. Không dùng tài khoản không được cấp quyền để thử xâm nhập hệ thống thật.

### 11.3. Positive tests

Chỉ có DENY tests có thể dẫn đến một hệ thống luôn từ chối release. Cần kiểm tra:

1. PR hợp lệ đi qua đúng reviewers và trusted checks.
2. Approved commit được build bởi builder được tin theo policy.
3. Artifact có provenance hợp lệ liên kết đúng source/digest.
4. Verified artifact được publish vào registry được phép.
5. Production admission chấp nhận **đúng artifact** đã phê duyệt.
6. Emergency workflow được thực hiện khi thật sự có phê duyệt, có time-bound access và audit.

### 11.4. Gherkin minh họa

~~~gherkin
Feature: Repository trust and software release assurance

  Scenario: A protected branch cannot be updated without approved review
    Given the production repository has an approved protected branch policy
    And developer D has no bypass authority
    When D attempts a direct protected-branch push
    Then the update must be rejected
    And an auditable enforcement result must be available

  Scenario: Security-sensitive workflow changes require the proper owners
    Given a PR modifies a protected release workflow file
    And the PR lacks the required authorized owner approval
    When a merge is requested
    Then the merge must be blocked according to the approved rules
    And no production release must originate from that unapproved change

  Scenario: New unreviewed changes invalidate approval when policy requires it
    Given a PR was approved at commit C1
    And the approved repository rule requires reapproval after new commits
    When a new commit C2 modifies the PR
    Then C1 approval must not authorize C2 automatically
    And the required review must be obtained before merging

  Scenario: An untrusted pull request cannot publish a production artifact
    Given contributor X submitted code from an external fork
    And the PR validation job runs in the approved untrusted context
    When the job attempts to use production publishing permissions
    Then privileged permissions must not be available
    And no production artifact must be published from that job

  Scenario: An unapproved source repository cannot become a release input
    Given the release policy has an approved repository identity
    And source revision C2 comes from a different unapproved repository
    When a build is submitted for trusted production release
    Then the source identity check must reject the request
    And the rejection must be recorded

  Scenario: Replacing a release tag cannot silently change the selected commit
    Given a release was approved for source commit C1
    And the release reference is later made to point to C2
    When the release gate validates the source revision
    Then it must not treat C2 as the approved commit
    And it must require a new approved decision or reject the release

  Scenario: Incorrect builder provenance prevents deployment
    Given an artifact digest matches the expected artifact identifier
    And its provenance identifies an unapproved builder identity
    When the production admission verifier checks the artifact
    Then the artifact must be rejected according to policy
    And the builder mismatch must be auditable

  Scenario: Artifact names cannot override content digest policy
    Given an image tag has previously been approved
    And the registry now resolves the tag to a different digest
    When production deployment requests the image
    Then the deployment gate must verify the exact approved digest
    And an unapproved digest must not be deployed

  Scenario: Approved revision and provenance can pass the release gate
    Given a change passed required reviews and trusted checks
    And an approved builder produced an artifact with verified provenance
    And the artifact digest matches the approved release decision
    When production admission evaluates the artifact
    Then it may be accepted according to release policy
    And the commit-to-artifact-to-deployment evidence must be traceable

  Scenario: Repository settings drift is detected
    Given production branch and repository permissions have an approved baseline
    And a controlled test changes a sensitive effective setting
    When the repository trust drift monitor evaluates the settings
    Then the unauthorized deviation must be detected
    And a finding or alert must be routed to the control owner

  Scenario: An emergency bypass is not an unlogged allow-all
    Given the approved emergency process requires scoped approval and audit
    When a privileged operator invokes an emergency repository override
    Then the operation must remain within the approved scope and duration
    And an independent audit record must be produced
~~~

**Lưu ý:** Gherkin này **chưa phải test đã chạy**. Có test description không chứng minh effective gate; phải thu được kết quả expected/actual, test environment, actor permissions, current rules, workflow revision và artifact/run identifiers.

### 11.5. Bằng chứng cần đối chiếu ở mỗi test

Một negative push test muốn kết luận “chặn đúng” cần:

1. Danh tính test principal, quyền hiệu lực và repository ID.
2. Baseline policy, version và effective rules tại lúc test.
3. Branch/ref bị kiểm tra, operation attempted.
4. Backend/server enforcement result, không chỉ UI thông báo.
5. Xác minh protected ref không bị thay đổi.
6. Audit event, timestamp và test run reference.
7. Các bypass actors khác còn tồn tại hoặc chưa kiểm tra.

Tương tự, một provenance test PASS cần kiểm tra **signature/trust root, builder, repository identity, commit, artifact digest và deployment actual digest**. Không chỉ parse JSON và tìm field `verified: true`.

## 12. Review từng quyền và đường bypass

### 12.1. Effective access matrix

Tạo ma trận với các cột:

| Actor | Create PR | Merge protected | Edit rules/secrets | Publish artifact | Deploy production |
|---|---|---|---|---|---|
| External contributor | Allowed proposal | No | No | No | No |
| Developer | Within project | Only via gate | No, trừ scope được duyệt | Usually no | Usually no |
| Maintainer | Yes | Via protected rules | Limited/approved | According to role | Separate gate |
| Build CI identity | Not required | No | No | Build output only | No |
| Publisher identity | No | No | No | Scoped registry | No |
| Deployment identity | No | No | No | No | Verified digest only |
| Repository admin | Administrative scope | Overrides only via governed process | Sensitive, logged | Not implicitly | Not implicitly |

Đây là **mô hình phân quyền minh họa**, phải thay bằng role thực của provider, group inheritance, bot integrations, environment protections và emergency permissions.

### 12.2. Tìm bypass trên đường merge

- Có thể push vào default branch trực tiếp bằng SSH token?
- Có service account được allowlist bypass?
- Có thể push qua một integration app không chịu required review?
- Có thể thay required check names cho phù hợp workflow giả?
- Có quyền đổi branch rules rồi bật lại?
- Có merge queue hoặc automerge bỏ kiểm tra “latest commit”?
- Có thể thay CODEOWNERS để tự chỉ định reviewer?
- Có thể tạo release từ một nhánh không protected?

### 12.3. Tìm bypass từ build tới production

- Có người dùng registry CLI publish package thủ công?
- Có deployment channel khác: hotfix, maintenance, emergency, rollback?
- Có thể deploy theo tag mà không so digest?
- Có thể upload artifact và dùng fake provenance JSON không được ký?
- Có thể đổi KMS/signing trust policy hoặc builder allowlist?
- Có trường hợp production nhận artifact build từ fork/PR?
- Có secrets trong runner hoặc external action có thể bị lạm dụng?
- Có artifact promotion sang environment khác mà không kiểm tra identity và scope?

**Đường đặc biệt hiếm dùng vẫn là đường cần review** nếu nó có thể thay production. Mục tiêu assurance là kiểm tra *complete mediation* của đường release.

## 13. Audit và telemetry cho repository trust

### 13.1. Những sự kiện quan trọng

Một audit trail có thể gồm:

- Repository creation/rename/transfer/archive/delete.
- Branch/tag rule changes và bypass events.
- Collaborator/team permission grants, revocations và admin privilege changes.
- PR creation, review, approval, dismissal và merge.
- Sensitive file changes (workflows, IaC, policy, lockfile, CODEOWNERS).
- CI workflow runs, actor/event, source revision, runner context và permissions.
- Secret access/grants, OIDC identity issuance và privileged credential use khi nền tảng hỗ trợ telemetry.
- Artifact publication, digest, builder/provenance references.
- Deployment approval/admission, effective artifact digest và target environment.
- Emergency actions, key/token revocation và incident response.

Không phải mọi platform cung cấp cùng fields. Cần **gap register hoặc compensating telemetry** nếu nguồn audit thiếu, thay vì khẳng định đã thu đủ.

### 13.2. Bảo vệ log và bí mật

- Audit store nên có quyền sửa/xóa tách khỏi nhóm có thể thay repository/release.
- Log phải có timestamps, actor references, scope, action, outcome và correlation IDs.
- Không lưu token, private signing key, raw secrets hoặc nội dung source nhạy cảm không cần thiết.
- Logging pipeline outage phải có monitoring và behavior theo approved policy.
- Retention/availability theo compliance và incident-investigation needs được phê duyệt.
- Truy cập evidence có role/need-to-know và integrity controls.

Một screenshot giao diện hiển thị “branch protection enabled” không chứng minh **liên tục bật trong kỳ** nếu không có history/change audit và runtime checks.

### 13.3. Correlate source, build và deploy

Một chuỗi audit minh họa:

~~~text
Source repository: SRC-PAYMENTS-CORE-01
PR record: PR-2471 (reviewed + required checks at approved revision)
Merged commit: COMMIT-ID-C2471
Trusted workflow run: RUN-9017
Builder identity: BUILD-PAYMENTS-APPROVED
Artifact subject digest: SHA256-DIGEST-ART-9017
Provenance verification: VERIFY-ART-9017 (policy version PV-3)
Release decision: REL-PAYMENTS-2026-11
Deployment admission: DEP-ADMIT-501 (accepted exact digest)
Production runtime inventory: running SHA256-DIGEST-ART-9017
Independent audit reference: AUDIT-SUPPLYCHAIN-501
~~~

Tất cả IDs là **placeholder minh họa**, không phải mã hợp lệ của một hệ thống thực tế. Cần actual digests, signatures và logs khi triển khai.

## 14. Đánh giá assurance evidence và coverage

### 14.1. Bằng chứng nào đủ mạnh cho claim nào?

| Claim | Evidence tối thiểu gợi ý | Giới hạn |
|---|---|---|
| **Kho source thuộc owner được duyệt** | Canonical provider/repo ID, approved inventory, owner review | Repo có thể chuyển quyền sau ngày review |
| **Protected branch được enforce** | Effective rules, actor permission matrix, negative push/merge tests | Admin/bot bypass có thể chưa được thử |
| **Sensitive changes được review** | CODEOWNERS/rules, sample PRs, approval timing, diff | Review có thể hình thức hoặc tài khoản bị chiếm |
| **Untrusted PR không có publish permission** | CI event config, effective token scopes, sandbox negative tests | Runner khác/cross-job artifact paths có thể chưa bao phủ |
| **Release source là approved commit** | PR/merge record, exact commit SHA, ref history, source selection log | Build input có thể chứa dependencies ngoài |
| **Artifact do trusted builder tạo** | Signed/verified provenance, builder/workflow ID, source revision và artifact subject | Builder có thể bị compromise nếu trust model không bao quát |
| **Artifact deploy đúng bản đã duyệt** | Admission result, approved digest, runtime deployment digest | Runtime mutation/side-loading ngoài đường deploy chưa đánh giá |
| **Controls hoạt động trong kỳ** | Time-window audit sampling, drift logs, incidents/overrides, test results | Sample không chứng minh toàn bộ thời điểm |
| **Repository compromise đã được khống chế** | Incident timeline, revoked credentials, impact scan, clean rebuild, deployment evidence | Chưa xác minh toàn bộ consumers/transitive artifacts |

### 14.2. Verified coverage và population completeness

Giả sử hệ thống inventory có **24 repositories liên quan production**:

- 15 repositories có access/rules review, negative tests và release lineage trong scope.
- 4 repositories có branch rules nhưng chưa test bot/admin bypass.
- 3 repositories chỉ có inventory, chưa review effective controls.
- 2 repositories có active, approved exceptions do legacy release.

Với mẫu số **24 repos đã biết**:

~~~text
Known repository population = 24
Verified coverage in defined scope = 15 / 24 = 62.5%
Configured but unverified = 4
Not assessed = 3
Exception active (not PASS) = 2
~~~

**62,5% không phải “62,5% software supply chain an toàn”**. Nó chỉ là coverage trong tập repositories đã biết và theo các kiểm soát đã nêu. Nếu build còn fetch code từ external action, submodule hoặc package source chưa inventory, *population completeness* chưa bảo đảm.

### 14.3. Metrics quan trọng

| Metric | Ý nghĩa | Điểm cần cảnh giác |
|---|---|---|
| **Approved-repo coverage** | Repo nào có owner và trusted source record | Inventory chưa đầy đủ có thể khiến số đẹp |
| **Effective branch-rule coverage** | Ref production nào có settings bảo vệ thực tế | Rules được khai báo nhưng có bypass |
| **Review enforcement coverage** | PRs vào protected branch có checks/approvals thích hợp | Chỉ kiểm tra một subset/period |
| **Privileged identities** | Số admin, bots và deploy tokens theo scope | Đếm ít không đồng nghĩa quyền đúng |
| **Untrusted CI isolation tests** | PR test environments nào xác minh không có privileged secrets | Tests ở staging không bao phủ mọi CI event |
| **Pinned external inputs** | Actions, submodules, dependencies có immutable references | Pinning nguồn độc hại vẫn không an toàn |
| **Artifact provenance verification** | Releases có verified attestation và subject digest matching | Attestation không có trust-root checks là vô nghĩa |
| **Deploy digest consistency** | Runtime đang chạy đúng verified artifact digest | Có đường manual/recovery bypass |
| **Policy drift latency** | Thời gian từ unapproved change đến detection/containment | Không phát hiện = dữ liệu đo sai |
| **High-risk repo findings** | Gap trên pipeline/IAM/policy critical | Severity theo impact, không chỉ số lượng |
| **Exception exposure** | Bypass có approval, scope, expiry và monitoring | Exception không tính PASS |
| **Evidence freshness** | Review/test khớp release/current settings | Evidence cũ không đại diện trạng thái mới |

### 14.4. Audit sampling có căn cứ

Một mẫu kiểm tra hoạt động trong kỳ có thể:

1. Chốt **population** PR merges và release deployments từ nguồn độc lập.
2. Chọn mẫu theo rủi ro: workflow/IaC/security policy, bot-initiated merges, emergency releases và routine changes.
3. Với mỗi mẫu, đối chiếu **PR approval, required checks, commit, builder, artifact digest, provenance, deployment**.
4. Kiểm tra outliers: direct push, release ngoài giờ, bypass event, policy drift, unapproved artifact.
5. Ghi số mẫu, thời kỳ, tiêu chí chọn, missing logs và limitations.

Không chỉ lấy mẫu từ các PR “đẹp” đã merge bằng UI rồi suy rằng **không có đường khác**. Cần đối chiếu với **Git ref changes, deployment logs và registry publication records**.

### 14.5. Claim–Argument–Evidence–Limitations

Ví dụ một claim được giới hạn:

> **Claim:** Trong phạm vi Payment Core production release R-42, source revision được dùng để build đã nằm trên protected branch và được phê duyệt theo rules được xác minh tại thời điểm release; artifact được triển khai trùng digest có provenance hợp lệ từ builder/workflow nằm trong allowlist.
>
> **Argument:** Repository identity được đối chiếu approved inventory, branch rules và review kiểm soát commit được merge; build trust policy ràng buộc source và builder với artifact digest; deployment gate xác minh digest/provenance.
>
> **Evidence:** Repo ID, effective rule snapshot/history, PR approvals, commit ID, CI run, signed provenance verification report, registry artifact digest và production admission log.
>
> **Limitations:** Claim không chứng minh mã không có lỗ hổng, dependency transitive hoàn toàn an toàn hoặc tất cả emergency/manual deployment paths đều được kiểm tra nếu chúng ngoài scope.

Claim **“100% các kho đều đáng tin”** đòi hỏi định nghĩa trust, population, kỳ đánh giá và evidence đủ; hiếm khi được hỗ trợ bởi một dashboard score đơn lẻ.

## 15. Case study: pipeline xanh nhưng artifact phát hành bị tráo

### 15.1. Bối cảnh

Một công ty hư cấu có **Payment Core** trên nền tảng SCM và CI/CD. Mọi thay đổi vào `main` đi qua PR review. Release pipeline build image, publish vào registry và deploy bằng image tag `payment-api:latest`.

Thiết kế ban đầu:

1. Repo có protected branch và required CI checks.
2. PR được review bởi maintainer, nhưng **workflow files và CODEOWNERS không được xem là sensitive paths**.
3. Một CI job chạy test từ PR và có thể dùng **shared runner workspace/cache**.
4. Release workflow gọi một external CI action bằng **mutable tag**.
5. Registry cho phép bot publisher **push lại cùng image tag**.
6. Production deployment chỉ kiểm tra image tag và tên repository, không kiểm tra digest hoặc provenance.
7. Logs chỉ ghi “workflow succeeded” và “deployment succeeded”, không có commit→artifact binding.

### 15.2. Threat chain giả định

Attacker có quyền đề xuất PR; đồng thời một external action version mà pipeline sử dụng có thể bị thay bởi bên có quyền quản lý upstream. Đây là **hai nguồn rủi ro khác nhau**, có thể cùng tồn tại nhưng không nên tự giả định một attacker kiểm soát cả hai.

Kịch bản kiểm thử threat model:

- Đường A: Untrusted PR thay build/test script. Nếu runner có shared privileged credentials hoặc trusted job tái dùng unverified artifact/cache, script có thể ảnh hưởng release path.
- Đường B: External action dùng tag mutable bị đổi nội dung sau khi đã được tổ chức review một lần; workflow vẫn gọi tag cũ và thực thi action mới.
- Đường C: Một principal có quyền registry push thay image dưới tag `latest`, còn production không kiểm tra digest; deployment có thể lấy artifact khác bản approved.

Mỗi đường cần kiểm tra riêng; một test chống PR injection **không chứng minh** action pinning hay registry digest policy đạt.

### 15.3. Trust boundary failure map

| Boundary | Giả định sai | Hậu quả tiềm năng | Control cần thiết |
|---|---|---|---|
| **PR → CI** | PR test code đáng tin vì đã qua scanner | Untrusted execution với quyền cao | Isolated untrusted runner, no secrets |
| **CI → External action** | Tag cố định theo tên nghĩa là source cố định | Third-party code substitution | Pin exact reviewed revision và update governance |
| **CI cache → Release job** | CI cache nội bộ tự đáng tin | Artifact/cache poisoning | Trust-level isolation, verify outputs |
| **Build → Registry** | Publisher bot không thể bị lạm dụng | Artifact push/replacement | Scoped credentials, protected immutable release policy |
| **Registry → Production** | Image tag là phiên bản được approve | Deploy sai digest | Exact digest + provenance verification |
| **Repo admin → Policy** | Chỉ developer PR mới là attacker path | Admin đổi rule/bypass audit | SoD, monitoring, separate audit |

### 15.4. Thiết kế lại

**Control 1 — Trusted source identity:** Approved repo ID/owner được quản lý trong source inventory; mọi build release ràng buộc exact commit ID.

**Control 2 — Effective branch/owner protection:** Nhánh và release refs được bảo vệ; workflow, IaC và CODEOWNERS thuộc sensitive paths. Bypass/admin changes có kiểm soát và audit.

**Control 3 — PR isolation:** PR chưa tin cậy chỉ chạy test trên context read-only không có secrets; trusted release job nhận **verified inputs**.

**Control 4 — External input policy:** External actions và build tools cần approved source, pinned revision và update review; không tải script mới chỉ dựa vào tag tùy biến.

**Control 5 — Artifact lineage:** Trusted builder phát hành attestation được verifier đánh giá theo approved trust anchors, gắn commit, workflow, builder và artifact digest.

**Control 6 — Registry/deploy:** Dùng exact digest cho production, hạn chế quyền publisher, có admission policy và audit.

**Control 7 — Monitoring:** Theo dõi repo settings drift, bypass, anomalous registry push, mismatched digests và provenance failures.

### 15.5. Kiểm thử và xác minh

| Test ID | Scenario | Expected |
|---|---|---|
| **T-01** | PR sửa sensitive workflow thiếu owner review | Merge/release bị chặn |
| **T-02** | PR test thử dùng production publisher identity | Quyền không tồn tại |
| **T-03** | Build tham chiếu unpinned external action | Policy gate phát hiện/chặn |
| **T-04** | Attestation giả có builder/repo sai | Verification reject |
| **T-05** | Tag `latest` trỏ digest khác approved release | Admission reject digest mismatch |
| **T-06** | Bot registry có quyền quá rộng | Finding/access review và giảm quyền |
| **T-07** | Bypass branch rule bằng admin không được phê duyệt | Alert/evidence và escalation |
| **T-08** | Approved commit + trusted builder + correct provenance | Accepted artifact, traceable deployment |

### 15.6. Kết luận assurance có thể hỗ trợ

Trước remediation:

> **Claim được hỗ trợ:** Các thay đổi merge vào protected branch theo luồng PR đã được kiểm tra thông thường đi qua reviewer và required checks tại thời điểm quan sát.
>
> **Evidence:** PR history, rules snapshots, CI checks.
>
> **Limitations:** Chưa đủ bằng chứng bảo vệ source→runner→external action→artifact→production; có nguy cơ privileged PR execution, mutable action/tag và missing provenance admission.
>
> **Action:** Mở findings, sửa quyền và controls, kiểm thử đường bypass/failure rồi mới mở rộng claim.

Sau remediation, chỉ kết luận release chain đạt trong **source, builder, artifact, registry, deployment và kỳ** đã xác minh. Việc một pipeline “green” không thay thế tests liên kết artifact tới đúng approved commit.

## 16. Ứng phó khi repository hoặc build pipeline bị compromise

### 16.1. Dấu hiệu cần điều tra

- Commit/tag/release không có approval hoặc xuất hiện từ actor lạ.
- Branch protection, CODEOWNERS, workflow permission hoặc registry policy thay bất thường.
- CI runner có outbound traffic, secret access hoặc action execution không dự kiến.
- Artifact digest khác expected build hoặc attestation không verify được.
- Publisher token được dùng ngoài workflow/environment dự kiến.
- Một release mới tạo hành vi không khớp source review hoặc business logic.
- Repository URL/mirror/ownership thay nhưng inventory chưa cập nhật.

Một alert đơn lẻ có thể false positive; cần triage với **evidence, scope và impact**.

### 16.2. Containment

Tùy mức độ và quyền được cấp, incident commander có thể quyết định:

1. Tạm ngừng publish/deploy từ nguồn nghi bị chiếm.
2. Thu hồi/rotate compromised human/bot credentials, OIDC trust bindings hoặc signing identities.
3. Vô hiệu hóa đường CI workflow/runner không đáng tin.
4. Bảo toàn Git refs, PR/review history, audit logs và builder/provenance evidence.
5. Đánh giá artifacts/packages đã phát hành và consumers có thể bị ảnh hưởng.
6. Cảnh báo owner của downstream systems/third-party recipients theo incident process.
7. Giới hạn truy cập audit evidence để tránh làm mất chain of custody.

Không tùy tiện xóa repository hoặc rewrite Git history trước khi **bảo toàn bằng chứng điều tra**, trừ khi cần thiết theo incident authority và kế hoạch đã phê duyệt.

### 16.3. Scoping và impact analysis

Phải xác định:

- Compromise window: từ thời điểm nào account/runner/policy có thể bị chiếm?
- Những source commits/tags/branches nào bị tác động?
- Repository settings nào thay đổi?
- Những workflow runs nào đã tiếp xúc secrets/builder identity?
- Những registry artifacts nào được publish trong khoảng nghi vấn?
- Runtime deployments nào dùng affected digests?
- Những dependency consumers hoặc mirrors có kéo artifact bị ảnh hưởng?
- Những attestations có thể được signer đã bị compromise tạo?

**Revert commit** không đủ nếu attacker đã phát hành artifact, đánh cắp credentials hoặc thay release policy. Cần rà soát toàn bộ downstream chain.

### 16.4. Recovery an toàn

1. Khôi phục source revision từ **verified clean trust anchor** (không chọn tùy ý branch “trông đúng”).
2. Review lại contributor permissions, branch rules, workflows, external actions và dependencies.
3. Revoke/rotate compromised tokens, keys và publish identities; xác định ảnh hưởng signer trước đó.
4. Rebuild bằng trusted builder/clean runner, inputs đã được kiểm chứng.
5. Phát hành **new artifact digest** với provenance phù hợp.
6. Redeploy exact verified digest theo admission policy.
7. Xác minh runtime state, audit logging, security controls và business invariants.
8. Theo dõi các consumers còn dùng affected artifacts và thông báo/thay thế theo policy.
9. Lưu timeline, actions, decisions, impact, residual risk và post-incident review.

Không “khôi phục” bằng cách bật allow-all, bỏ signature verification hoặc cài image cùng tag mà không xác minh digest.

### 16.5. Recovery drill và evidence

Một bài diễn tập có thể giả lập:

- Admin token bị thu hồi.
- Untrusted workflow bị phát hiện.
- Một artifact có provenance sai builder.
- Một image tag bị đổi digest.

Expected: unauthorized path bị chặn, incident triage nhận evidence, trusted release có thể thực hiện và production quay về đúng artifact. Bài tập phải được cấp phép và không làm mất dữ liệu/gián đoạn ngoài phạm vi.

## 17. Governance, RACI và kiểm soát thay đổi

### 17.1. Các vai trò

| Vai trò | Trách nhiệm |
|---|---|
| **Repository/system owner** | Duy trì repo inventory, ownership và source-use policy |
| **Security/supply-chain architect** | Threat modeling, trust boundaries, technical requirements |
| **Developer/maintainer** | Code review, dependency updates, secure change proposal |
| **SCM organization administrator** | Quản lý repo/team permissions, branch/rules và security settings |
| **CI platform owner** | Runners, event permissions, token scopes, workflow isolation |
| **Build/release engineer** | Approved builder, provenance, artifact generation và publishing |
| **Artifact registry owner** | Publisher identity, retention, immutability/overwrite policy, audit |
| **Deployment/platform owner** | Admission policy, verified digests, environment permissions |
| **Risk owner** | Rủi ro còn lại, thẩm quyền chấp nhận exception |
| **Security assurance/QA** | Independent verification, test plans/evidence và findings |
| **Incident commander** | Containment, forensic preservation và recovery coordination |
| **Internal audit** | Independent assessment theo scope được giao |

### 17.2. RACI mẫu

RACI: **R** thực hiện, **A** chịu trách nhiệm cuối cùng, **C** tham vấn, **I** được thông báo.

| Hoạt động | Repo owner | Security | CI/release | Platform | Assurance |
|---|---|---|---|---|---|
| Repo identity và source inventory | **A/R** | C | C | I | C |
| Branch/CODEOWNERS và role policy | **A/R** | C | C | I | C |
| Threat model untrusted PR và dependencies | C | **A/R** | R | C | C |
| Runner permissions và separation | C | C | **A/R** | C | C |
| Build/provenance verification | C | C | **A/R** | R | C |
| Deployment admission | I | C | R | **A/R** | C |
| Independent negative/failure tests | C | C | C | C | **A/R** |
| Security incident/remediation | R | R | R | R | C |

**Risk acceptance** phải theo governance và authority thực tế; ma trận RACI là ví dụ, không tự cấp quyền chấp nhận risk cho người có thể merge PR.

### 17.3. Emergency release và break-glass

Một sự cố production có thể đòi hỏi hotfix nhanh. Nhưng emergency path:

- Có identity riêng và phê duyệt trong tình huống được định nghĩa.
- Giới hạn repository, artifact, target environment, action và thời hạn.
- Không bỏ qua hoàn toàn artifact integrity/trust-chain khi có phương án an toàn.
- Có independent audit và cảnh báo kích hoạt.
- Có retrospective review, cleanup quyền tạm thời và test sau release.
- Ghi rõ điều kiện nào cho phép tạm hoãn check, compensating control và authority.

Emergency release không phải một “đường hậu” có quyền deploy mọi artifact bất kỳ mà không kiểm chứng.

### 17.4. Những trigger phải review lại repository trust

- Chuyển repository owner/organization, đổi URL hoặc provider.
- Thay permissions, teams, maintainers, CODEOWNERS và admin bots.
- Thay protected branches/tags, required checks hoặc merge strategy.
- Đổi event/runner, cache, workflow files hoặc secret configuration.
- Thêm third-party actions, submodules, package registries, language/build tools.
- Thay artifact registry, publisher identity, signing/attestation trust root.
- Thay production admission, emergency procedures hoặc deployment routes.
- Có credential compromise, dependency incident, unusual release hoặc audit finding.
- Đổi policy version, compliance scope, data classification hoặc system criticality.

Trigger nên tạo mapping **change → affected trust boundaries/requirements → tests → evidence → decision**, không chỉ một reminder chung “kiểm tra supply chain”.

## 18. Những sai lầm thường gặp

| Sai lầm | Vì sao chưa đủ hoặc nguy hiểm? | Cách cải thiện |
|---|---|---|
| “Repo nằm trong organization chính thức nên tin” | Owner có thể bị compromise; quyền thay đổi quá rộng | Approved identity, permissions và evidence |
| Tin tên/URL repo thay vì canonical identity | Typosquatting, transfer/rename và mirror confusion | Provider repository ID + allowlist + migration review |
| Tin commit hash như chứng chỉ an toàn | Hash chỉ định content, không phê duyệt nội dung | Kiểm tra approved source/review và policy |
| Signed commit = secure code | Người ký/key có thể bị compromise; mã có bug | Trust policy + code review + tests + provenance |
| Git tag không thể đổi | Ref có thể bị thay nếu không bảo vệ | Protected refs + exact commit/digest |
| Có branch protection nhưng bypass actors rộng | Admin/bot có thể push/merge trực tiếp | Effective bypass review + negative tests |
| CODEOWNERS file = enforcement | Không có required owner rule hoặc pattern sai | Test ownership enforcement thực |
| Required check xanh = code an toàn | Check có thể bị đổi/bypass hoặc scope hạn chế | Protect workflow/checks, security tests theo risk |
| Chạy untrusted PR với privileged token | Code chưa review có thể lạm dụng CI secrets | Isolate PR jobs, least privilege |
| Dùng shared runner/cache cho mọi trust level | Untrusted build có thể để lại artifact/credential | Runner/cache isolation và clean environments |
| Third-party action dùng mutable version tag | Source bị thay mà workflow không đổi tên | Pin exact revision, source review và update process |
| Chỉ scan CVEs trong dependencies | Không thấy publisher compromise hay package substitution | Source integrity, namespace controls, provenance |
| SBOM = mã sạch | SBOM là kê khai thành phần, có thể thiếu và không test hành vi | Verify SBOM provenance + vulnerability/behavior analysis |
| Có attestation file là verified | Attestation có thể không được ký/kiểm tra identity | Verify trust root, builder, repo và artifact digest |
| Deploy image tag thay vì digest | Tag có thể trỏ artifact khác | Immutable approved digest admission |
| Chỉ review merge mà bỏ publisher/registry | Build hoặc registry có thể thay artifact | End-to-end commit→build→artifact→runtime evidence |
| Bot có full organization/admin quyền | Bị compromise sẽ lan nhiều repo | Scoped short-lived credentials + SoD |
| Admin được sửa rules và xóa audit | Khó chứng minh bypass hoặc incident | Independent logging và privileged access review |
| Exception được tính PASS | Rủi ro chưa được khắc phục | Riêng trạng thái exception, owner, expiry |
| Chỉ có screenshot settings | Không chứng minh hoạt động trong kỳ | Effective config, history, negative tests |
| Mọi repository có cùng mức kiểm soát | Criticality/impact khác nhau | Risk-tiered requirements và test coverage |
| CI “green” chứng minh production đúng source | Có thể đổi artifact sau build hoặc deploy nhầm | Provenance + runtime digest verification |
| Revert commit là đủ sau compromise | Secret/publisher/artifact có thể còn bị ảnh hưởng | Incident scoping, rotation và clean rebuild |
| Báo 100% coverage khi inventory thiếu | External inputs, mirrors, legacy release không được tính | Independent discovery + limitations |

## 19. Bài tập thực hành

### Bài tập 1 — Vẽ trust boundaries của software delivery

Một dự án có 20 developers, repo SCM private, CI workers, package registry, external actions, artifact registry và production deployment. Developer có thể tạo PR; một bot vừa merge vừa deploy.

**Yêu cầu:** Vẽ DFD/trust graph, chỉ rõ **repo identity, untrusted PR, protected branch, build inputs, artifact registry và deployment gate**. Đánh dấu ít nhất tám crossings có thay đổi về authority, identity hoặc integrity.

**Tự kiểm tra:** Có đánh dấu **bot privilege** và **control-plane settings** như trust boundaries, không chỉ source code path.

### Bài tập 2 — Repository identity và tag replacement

Một release được duyệt dựa trên tag `v2.5` và repository URL hiển thị. Sau review, tag trỏ sang commit mới; repo trước đó đã chuyển organization.

**Yêu cầu:** Thiết kế trusted source record, cách resolve canonical repository identity, so exact approved commit với tag và kiểm tra branch/release policy. Viết acceptance criteria cho tag replacement và repo transfer.

**Tự kiểm tra:** Không coi chữ ký commit hay tên tag như proof rằng release đã được phê duyệt.

### Bài tập 3 — CODEOWNERS và workflow change

Một PR chỉ sửa file CI workflow, dependency lockfile và CODEOWNERS. Reviewer thông thường approve vì “không sửa code ứng dụng”.

**Yêu cầu:** Phân tích vì sao đây là supply-chain-sensitive change. Xác định role/phê duyệt cần có theo risk, những negative tests về required owner review, stale approval và bypass actors. Đề xuất evidence cho code review.

**Tự kiểm tra:** Đã chỉ ra **workflow files có thể điều khiển quyền runner/release** và CODEOWNERS có thể bị vô hiệu hóa nếu không bảo vệ.

### Bài tập 4 — Untrusted PR trong CI

Một workflow chạy unit tests từ external fork trên runner có token publish package và cache được trusted release job dùng lại.

**Yêu cầu:** Xây threat model với attacker capability chỉ là gửi PR; đề xuất **tách runners, token scopes, secrets, cache namespaces và artifact verification**. Viết ít nhất bốn negative tests được phép.

**Tự kiểm tra:** Phân biệt quyền của PR author với quyền **job đang chạy code PR**; không phải attacker đã có repo admin.

### Bài tập 5 — Kiểm tra nguồn dependencies/submodules

Ứng dụng dùng private package `payment-internal`, một Git submodule và CI action từ third-party. Nhóm chỉ có CVE scan PASS.

**Yêu cầu:** Review package namespace/registry resolution, lock integrity, post-install scripts, submodule URL/SHA, external action pinning và publisher trust. Nêu vì sao CVE scan không chứng minh provenance.

**Tự kiểm tra:** Có bao phủ cả **transitive inputs** và source policy, không chỉ dependency manifests top-level.

### Bài tập 6 — Artifact provenance validation

Một image có tag release chính xác, digest khớp bản registry hiện tại và provenance JSON kèm theo; nhưng trường builder identity không thuộc allowlist.

**Yêu cầu:** Nêu cách verifier cần đánh giá identity/trust root, signed attestation, source repo+commit, workflow và artifact subject. Viết expected behavior khi builder khác, digest khác hoặc attestation không verify.

**Tự kiểm tra:** Không chỉ đọc field `verified=true`; phải có **cryptographic verification với policy đúng**.

### Bài tập 7 — Rà soát quyền bot và admins

Một integration bot có quyền admin trên tất cả repos, cấp production deployment token và có thể disable branch protection. Audit logs lưu cùng tài khoản có quyền này.

**Yêu cầu:** Thiết kế access matrix, SoD, short-lived credentials, độc lập audit, break-glass governance. Viết finding, risk scenario và retest criteria.

**Tự kiểm tra:** Không coi MFA của developer là biện pháp đủ để bảo vệ **bot credentials**.

### Bài tập 8 — Negative tests cho deployment

Production deploy qua một Kubernetes admission controller có policy kiểm tra image tên repository nhưng chưa verify digest/provenance. Một hotfix script có thể deploy trực tiếp.

**Yêu cầu:** Viết acceptance criteria và test cho **wrong source, wrong digest, wrong builder, unsigned/invalid attestation và manual bypass**. Đề xuất audit evidence linking deployed image tới approved commit.

**Tự kiểm tra:** Có kiểm tra cả **routine và emergency deployment paths**, không chỉ đường CI chính.

### Bài tập 9 — Tính coverage và lập assurance claim

Inventory có 24 repositories: 15 verified, 4 configured but not tested, 3 not assessed và 2 có active exceptions. Một mirror và hai legacy jobs chưa được đưa vào inventory.

**Yêu cầu:** Tính verified coverage trên **24 repos đã biết** và giải thích vì sao nó không đại diện đầy đủ tất cả build inputs. Viết **Claim–Argument–Evidence–Limitations** và báo cáo riêng exceptions, gaps, unknowns và high-risk sources.

**Tự kiểm tra:** Không cộng exception vào PASS và không nói “x% supply chain an toàn”.

### Bài tập 10 — Incident response cho compromised maintainer

Một maintainer account bị compromise; attacker có thể merge thay đổi vào protected branch, tạo release tag và push package tới registry trong khoảng vài giờ.

**Yêu cầu:** Viết runbook scoping/containment, xác định affected commit/tag/workflow/artifact/digest/consumers, revoke/rotate credentials và rebuild từ clean source. Thiết kế verification evidence sau recovery.

**Tự kiểm tra:** Không kết luận xong sự cố chỉ vì revert code; phải xem **registry artifacts, downstream deployments và signing identities**.

### Bài tập 11 — Thiết kế quality gate cho thay đổi critical

Một tổ chức phát triển phần mềm phục vụ dữ liệu tài chính muốn chính sách riêng cho IaC, CI workflow và access policies. Hiện tất cả thay đổi đều cần một reviewer bất kỳ.

**Yêu cầu:** Xây tiered controls theo criticality, owner review, required checks, independent approval, emergency exception và release provenance. Chỉ rõ những tiêu chí nào cần **human review** và những tiêu chí nào có thể automated.

**Tự kiểm tra:** Tránh hard-code một số reviewer tùy tiện; ngưỡng cần có **policy/risk owner** quyết định.

### Bài tập 12 — Thiết kế continuous assurance

Tổ chức có 50 repositories trên nhiều SCM providers. Một số bị đổi owner, hai repos mới xuất hiện, một action bị thay tag upstream và một project chưa có build attestation.

**Yêu cầu:** Định nghĩa **inventory reconciliation, config drift detection, access review, attestation checks, alerts, owners, findings và revalidation triggers**. Đề xuất cadence theo risk, ghi điều kiện nào cần xử lý ngay.

**Tự kiểm tra:** Mỗi metric có mẫu số rõ và không coi source đã inventory là đã verified.

## 20. Checklist đánh giá Repository trust

### 20.1. Source identity và inventory

- **Source scope:** Đã liệt kê repos, forks, mirrors, submodules, LFS và external code inputs?
- **Canonical identity:** Repo ID/organization/host được xác minh từ nguồn có thẩm quyền?
- **Ownership:** System/service owner, maintainers và security contact có rõ?
- **Lifecycle:** Repo transfer, rename, archive, deletion và migration có trigger review?
- **Criticality:** Repo chứa application, IaC, workflow, policy hoặc secrets liên quan production?
- **Revision:** Release dùng exact approved commit/digest, không chỉ mutable ref?

### 20.2. Contributors và review gates

- **Least privilege:** Human, bot và integration permissions có theo nhu cầu?
- **Identity:** MFA/credential controls và access revocation theo approved policy?
- **Protected refs:** Branch/tag rules đang có hiệu lực và đã test direct push/force-push?
- **Required reviews:** Ai review, ai merge, có SoD và CODEOWNERS enforcement?
- **Sensitive files:** Workflows, IaC, policy, manifest, lockfile và CODEOWNERS có owner?
- **Required checks:** Checks chạy trên đúng revision và workflow không thể bị thay tùy ý?
- **Bypass:** Admin/bot/emergency actors có scope, approval và audit?
- **Review freshness:** Thay nội dung sau approval có được xử lý theo policy?

### 20.3. CI/CD và external inputs

- **Untrusted PR:** Code PR/fork có bị tách khỏi privileged secrets/publishing?
- **Runner isolation:** Workspaces, cache, network, ephemeral credentials và trust levels?
- **Workflow input:** PR metadata và file inputs không trở thành shell code tin cậy?
- **External actions:** Third-party code có approved origin và pinned revision?
- **Dependencies:** Registry priority, namespace, lock integrity và provenance được kiểm tra?
- **Submodules/LFS:** Remote URLs/object integrity và transitive source trust có được xác minh?
- **Build identity:** Builder/workflow identity có được bảo vệ và giới hạn?
- **CI audit:** Workflow event, source commit, actor và effective permissions có evidence?

### 20.4. Artifact và deployment

- **Artifact lineage:** Source commit, builder, workflow và build inputs liên kết artifact?
- **Provenance:** Signature/trust root, subject digest, builder/repo IDs và policy đều được verify?
- **Registry:** Publisher có least privilege; artifact replacement và mutable tags được kiểm soát?
- **Digest:** Production chỉ deploy exact verified digest theo approved policy?
- **Admission:** Wrong source/builder/digest và unsigned/invalid provenance có bị từ chối?
- **Release paths:** Manual, emergency, rollback và alternate deploy có kiểm soát?
- **Runtime:** Actual deployed digest được đối chiếu với approved release?

### 20.5. Evidence và continuous assurance

- **Requirements:** Mỗi risk scenario critical có testable requirements và acceptance criteria?
- **Verification:** Có positive, negative, bypass, drift và failure-path tests?
- **Scope:** Evidence có release, environment, actor, effective config và period?
- **Audit:** Repository/rules/permissions/merge/publish/deploy changes được bảo vệ?
- **Secrets:** Logs/evidence không chứa raw tokens, keys hoặc dữ liệu nhạy cảm không cần thiết?
- **Coverage:** Mẫu số repo/build inputs đủ; configured/verified/unknown/exception tách rõ?
- **Findings:** Có owner, risk impact, approval/exception expiry, remediation và retest?
- **Incident:** Có playbook compromise, provenance scoping, credential rotation và clean rebuild?
- **Change triggers:** Repo/owner/rules/workflows/dependencies/vendor/builder thay đổi có đánh giá lại?
- **Claims:** Kết luận chỉ dựa vào bằng chứng đúng version, scope và time window?

## 21. Tổng kết

Khi review độ tin cậy của một repository, hãy lần lượt hỏi:

1. **Đúng nguồn chưa?** Repo owner/ID/canonical origin và revision được xác minh bằng evidence nào?
2. **Ai có thể thay?** Human/bot/admin nào có quyền merge, sửa rules, ký release hoặc publish artifact?
3. **Code chưa tin cậy chạy ở đâu?** PR/fork, third-party action, dependency, cache và runner có crossing sang privileged context?
4. **Merge được kiểm soát ra sao?** Protected refs, review independence, CODEOWNERS, required checks và bypass actors?
5. **Build có thể tin theo claim nào?** Builder identity, workflow, source commit, dependency inputs và provenance được kiểm tra thế nào?
6. **Production có đúng artifact không?** Digest, admission, registry permissions và actual runtime evidence?
7. **Nếu một mắt xích bị chiếm**, có phát hiện, cô lập, thu hồi và rebuild từ trusted source không?
8. **Đủ bằng chứng chưa?** Có negative tests, effective settings, audit history và những giới hạn chưa xác minh?

**Điều cần ghi nhớ:** **Repository trust** không phải là niềm tin tuyệt đối vào một Git server hay một biểu tượng “verified”. Nó là tập hợp các **security properties có thể kiểm tra** về danh tính nguồn, quyền thay đổi, nội dung đã phê duyệt, ranh giới thực thi CI, integrity/provenance của build và đường triển khai. Trong **supply chain security assurance**, hãy chứng minh một chuỗi **source → authorized change → trusted build → verified artifact → controlled deployment**, kiểm tra những **đường bypass và tình huống lỗi** có thể phá chuỗi đó, rồi nêu rõ **claims, evidence, limitations, owners và remediation/retest** để duy trì niềm tin theo thời gian.

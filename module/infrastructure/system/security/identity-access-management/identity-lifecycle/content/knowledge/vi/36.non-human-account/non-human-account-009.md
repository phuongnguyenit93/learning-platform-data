# Review non-human account: rà soát tài khoản phi con người theo vòng đời IAM

## 1. Review non-human account là gì?

Trong **Identity and Access Management (IAM)**, **non-human account** là tài khoản hoặc danh tính được sử dụng chủ yếu bởi **ứng dụng, dịch vụ, máy chủ, pipeline, automation, bot hoặc thiết bị**, thay vì một người đăng nhập tương tác để thực hiện công việc cá nhân. **Review non-human account** là hoạt động **kiểm tra và tái xác nhận** các danh tính, quyền, credential, mục đích sử dụng, người chịu trách nhiệm và trạng thái vòng đời của chúng.

Ví dụ, tài khoản **svc-report-exporter** được cấp quyền đọc dữ liệu và xuất báo cáo từ hệ thống Finance. Một năm sau, nhóm phát triển đã thay pipeline cũ bằng dịch vụ khác nhưng credential và role của tài khoản cũ vẫn có hiệu lực. Một lần review đúng nghĩa phải trả lời: **dịch vụ này có còn chạy không, ai chịu trách nhiệm, quyền nào còn cần, khóa nào đang tồn tại, ứng dụng nào vẫn chấp nhận chúng và phải sửa hoặc thu hồi như thế nào?**

Review không chỉ là xem danh sách account rồi đánh dấu **ACTIVE**. Nó phải nối được ba quyết định:

1. **Nghiệp vụ:** non-human identity còn phục vụ một nhiệm vụ hợp lệ không?
2. **Bảo mật:** tập quyền, trust relationship, credential và môi trường có phù hợp nguyên tắc **least privilege** không?
3. **Kỹ thuật:** những thay đổi được quyết định đã được thực thi tại **IdP, cloud IAM, vault, SaaS, API/resource server** và kiểm chứng đầy đủ chưa?

Trong module **Identity Lifecycle** theo **Joiner–Mover–Leaver (JML)**, owner là con người có thể gia nhập, đổi vị trí hoặc nghỉ việc; còn workload vẫn có thể tồn tại độc lập. Vì vậy, review cần phân biệt **vòng đời con người sở hữu** và **vòng đời tài khoản máy**, tránh cả hai sai lầm: giữ secret của người cũ vô thời hạn hoặc vô tình xóa account production đang phục vụ nhiệm vụ hợp lệ.

### Mục tiêu học tập

Sau bài này, người học có thể:

- Phân biệt non-human account, service principal, managed/workload identity, bot, credential và session.
- Kiểm kê và liên kết account–workload–service owner–tenant–credential bằng định danh đáng tin.
- Thiết kế campaign định kỳ hoặc theo sự kiện, ưu tiên theo mức rủi ro.
- Phân tích **expected, assigned, effective và used access**, cùng độ tin cậy của telemetry.
- Đánh giá quyền cloud, OAuth, RBAC/ABAC/PBAC, secret, trust, SoD và đường quản trị gián tiếp.
- Đưa ra quyết định **KEEP, REDUCE, ROTATE, TRANSFER_OWNER, REPLACE, REVOKE hoặc EXCEPTION**.
- Thực thi thay đổi có kế hoạch để giảm gián đoạn và xác minh quyền thực sự ở target.
- Tạo audit, KPI, bài kiểm thử và quy trình xử lý account mồ côi hoặc bị xâm phạm.

## 2. Non-human account gồm những loại nào?

Không phải mọi non-human identity là một user account giống con người. Các loại phổ biến:

| Loại | Ví dụ | Đặc điểm cần review |
| --- | --- | --- |
| **Service account** | svc-billing-sync trong hệ điều hành hoặc SaaS | Account có thể sở hữu password, SSH key, token hoặc permission |
| **Service principal / application identity** | Ứng dụng gọi API tài chính | Client ID, credential/federation, application role và tenant |
| **Managed identity** | Workload nhận token từ nền tảng cloud | Không nhất thiết có secret để đội vận hành tự giữ; vẫn có role và trust |
| **Workload identity** | Kubernetes pod, VM, container, serverless job | Liên kết workload runtime với chính sách phát hành credential |
| **CI/CD identity** | Pipeline deploy production | Trust repository, branch, environment, action scope |
| **Automation/RPA bot** | Bot xử lý hóa đơn | Có thể dùng UI/API; đôi khi bị cấu hình như user con người |
| **Integration account** | Connector ERP ↔ CRM | API scopes, refresh grants, vendor ownership và thời hạn |
| **Device/machine account** | Thiết bị mạng, host, kiosk | Khóa/chứng chỉ, thiết bị vật lý, đăng ký và posture |
| **Database technical account** | app_reader, backup_operator | Quyền trên schema, data export và rotation |
| **Emergency non-human identity** | Recovery automation, break-glass service | Scope khẩn cấp, activation, audit và thời hạn riêng |

Một service account có thể là **User record trong một SaaS**, một **service principal trong directory**, hay một **machine credential tại cloud provider**. Do đó, “review non-human account” phải bắt đầu bằng **kiến trúc đích**, không áp một schema chung cho tất cả.

## 3. Phân biệt identity, account, credential, workload và owner

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Workload/service** | Ứng dụng hoặc tác vụ cần làm việc | billing-sync-job |
| **Non-human identity (NHI)** | Định danh logic đại diện cho workload | workload:billing-sync:prod |
| **Target account/principal** | Chủ thể được hệ thống đích nhận biết | saas-service-user-27 |
| **Credential** | Bằng chứng để chứng thực account | Certificate, OAuth client secret, API key |
| **Session/token** | Bằng chứng truy cập được cấp trong một thời gian | Access token cho billing API |
| **Owner/team** | Đơn vị chịu trách nhiệm cho mục đích và rủi ro | team-finance-platform |
| **Runtime** | Nơi workload chạy | Namespace production, VM, CI runner |
| **Entitlement** | Quyền cụ thể tại tài nguyên | READ billing của org-a |
| **Trust policy** | Ai được đóng vai principal hay nhận token | Repository và branch được phép assume role |

Quan hệ giữa chúng không nhất thiết là một-một. **Một workload có thể dùng nhiều principal**, một principal có thể có **nhiều credential**, còn một owner có thể chịu trách nhiệm cho hàng chục bot. Việc xóa một secret không tự xóa entitlement; đổi owner không tự rotate tất cả credential.

**Owner không đồng nghĩa người trực tiếp đăng nhập**. Owner chịu trách nhiệm về mục đích, phê duyệt và xử lý sự cố, trong khi workload dùng machine identity để gọi API.

## 4. Review non-human account khác review user thế nào?

| Tiêu chí | Human identity | Non-human identity |
| --- | --- | --- |
| Nguồn căn cứ chính | HRIS, employment/sponsor, job role | Service catalog, CMDB, workload registry, owner và deployment |
| Người có thể giải thích nhu cầu | Manager hoặc resource owner | Service owner, platform/team owner và data owner |
| Cách đăng nhập | Thường tương tác, MFA/SSO | Client credentials, certificate, managed identity, workload federation |
| Tín hiệu hoạt động | User sessions, thao tác người dùng | Jobs, API calls, tokens, cron/batch, backend dependencies |
| Khi owner nghỉ việc | Có thể khóa human access ngay | Chuyển ownership, xử lý secret, đánh giá service còn cần |
| Nguy cơ đặc thù | Privilege accumulation, account takeover | Long-lived secret, orphaned principal, trust quá rộng, machine-to-machine lateral movement |
| Xác minh thu hồi | IdP/SSO/session/ứng dụng | Principal/role/credential/token/trust/runtime/target API |
| Hậu quả thu hồi sai | Người dùng không làm việc được | Dịch vụ production, tích hợp hoặc batch quan trọng ngừng chạy |

**Không dùng quy trình “đổi mật khẩu sau 90 ngày” làm giải pháp duy nhất** cho danh tính máy. Một password được rotate nhưng pipeline vẫn giữ một PAT khác có quyền rộng thì rủi ro không được giải quyết.

Ngược lại, không miễn mọi kiểm soát vì account “không có người dùng”: vẫn cần owner có trách nhiệm, least privilege, secret lifecycle, review, audit và endpoint authorization.

## 5. Vì sao phải review?

Những rủi ro thường tích lũy âm thầm:

- **Orphaned account:** người tạo nghỉ hoặc đội sở hữu bị giải thể, không ai chịu trách nhiệm.
- **Excessive privilege:** bot chỉ đọc số liệu nhưng có quyền quản trị toàn tenant.
- **Long-lived static secrets:** mật khẩu/API key không hạn hoặc không được rotate.
- **Credential sprawl:** cùng secret nằm trong file cấu hình, CI variables, máy developer, image container và vault.
- **Privilege escalation:** service principal được phép tự cấp quyền hoặc thay chính sách IAM.
- **Overbroad trust:** một identity có thể bị sử dụng bởi mọi repository/namespace hoặc tài khoản cloud.
- **Unused but active:** integration cũ ngừng chạy, key và role vẫn còn.
- **Multi-tenant confusion:** một principal có quyền trên tài nguyên org-b dù nhiệm vụ chỉ ở org-a.
- **Weak attribution:** một account dùng chung cho nhiều ứng dụng khiến audit không xác định được workload cụ thể.
- **Residual access:** principal disabled ở một nơi nhưng API key, cached token hoặc direct ACL vẫn được chấp nhận.

Mục tiêu review là **giảm rủi ro mà vẫn giữ tính liên tục dịch vụ hợp lệ**. Một account có rủi ro cao không phải luôn phải xóa ngay; cần biết đường phụ thuộc, quyền cần thiết và cách triển khai thay thế.

## 6. Review, reconciliation và rotation khác nhau thế nào?

| Hoạt động | Câu hỏi | Kết quả |
| --- | --- | --- |
| **Discovery/inventory** | Có những non-human identities và credentials nào? | Danh mục có nguồn và mức tin cậy |
| **Recertification/review** | Identity, owner, quyền và phương thức xác thực còn hợp lệ không? | Quyết định KEEP/REDUCE/REVOKE... |
| **Reconciliation** | Quyền/credential thực tế tại target có khớp expected không? | Sai lệch và bằng chứng readback |
| **Secret rotation** | Credential cũ có được thay bằng credential mới đúng policy không? | Secret mới hoạt động, secret cũ vô hiệu |
| **Deprovisioning** | Account, role, trust và credential nào phải chấm dứt? | Các thay đổi được thực thi |
| **Effective-access verification** | Sau thay đổi, action nào thực sự ALLOW/DENY? | Bằng chứng authorization tại target |
| **Incident response** | NHI bị nghi compromised thì cần chặn thế nào? | Containment, credential revoke, investigation |

**Review chọn “REVOKE” chưa đủ** nếu target vẫn chấp nhận API key. **Rotation “SUCCESS” chưa đủ** nếu secret cũ vẫn hoạt động song song không kiểm soát. **Reconciliation khớp dữ liệu IGA chưa đủ** nếu dữ liệu mong muốn được định nghĩa quá rộng.

## 7. Ai có thẩm quyền review?

| Vai trò | Trách nhiệm |
| --- | --- |
| **Business/service owner** | Chứng minh workload vẫn cần thiết và chức năng nghiệp vụ |
| **Technical owner/SRE** | Xác nhận deployment, dependencies, credential và runbook |
| **Resource/data owner** | Duyệt quyền truy cập dữ liệu và tài nguyên nhạy cảm |
| **IAM/IGA governance** | Thiết kế policy, campaign, role mapping và audit |
| **Cloud/platform owner** | Kiểm tra trust, cloud role và quyền của runtime |
| **Security/risk owner** | Kiểm tra đặc quyền, SoD, ngoại lệ và residual risk |
| **Credential/PKI/vault owner** | Quản lý issuance, rotation, revocation và bảo vệ secret |
| **Provisioning automation/operator** | Thực thi grant/revoke được phê duyệt |
| **Independent reviewer/auditor** | Kiểm tra bằng chứng và hậu kiểm, không mặc nhiên cấp quyền |

Không giao tất cả item cho **người đã tạo account**: người này có thể đã chuyển việc hoặc chỉ có quyền kỹ thuật, không còn biết nhu cầu nghiệp vụ. Với quyền nhạy cảm, manager của team cũng chưa chắc được phép quyết định việc đọc dữ liệu của tenant khác.

**Một người có thể giữ nhiều vai trò**, nhưng SoD phải kiểm tra xem cùng identity có đang tự tạo, tự duyệt và tự cấp đặc quyền hay không. Reviewer của quyền admin nên độc lập theo chính sách.

## 8. Ownership phải có tính tiếp nối

Mỗi NHI quan trọng nên có ít nhất:

- **Owning service/team**, được quản lý trong service catalog hoặc nguồn có thẩm quyền.
- **Accountable owner** hoặc nhóm chịu trách nhiệm quyết định nghiệp vụ.
- **Technical operator**, có thể xử lý secret, deployment và sự cố.
- **Resource/data owner** khi cần quyền truy cập hệ thống khác.
- **Backup/escalation owner** khi owner chính vắng mặt.
- **Lifecycle state** của workload và business application.

Nếu owner không còn ACTIVE hoặc nhóm đã giải thể, trạng thái là **OWNER_UNVERIFIED/TRANSFER_REQUIRED**, không tự ghi **KEEP**. Nhưng cũng không tự xóa account production khi chưa biết service dependency; có thể **giới hạn quyền mới, hạn chế thay đổi và kích hoạt ownership remediation** theo risk.

Một email distribution list không đủ chứng minh responsibility nếu nhóm không có người nhận hoặc không ai có thẩm quyền. Nên đối chiếu team registry và người có quyền duyệt thực tế.

## 9. Những nguồn cần đối chiếu khi inventory

| Nguồn | Có thể thấy gì? | Giới hạn |
| --- | --- | --- |
| **IdP/directory** | Service principal, application registration, nhóm, owner | Không tự thấy mọi local API key ở SaaS |
| **Cloud IAM** | Roles, policies, service accounts, trust/assume-role | Không tự phản ánh SaaS grants ngoài cloud |
| **Vault/secret manager** | Secret/certificate metadata, owner, lease, rotation | Không chứng minh mọi bản sao secret đã mất |
| **PKI/CA** | Certificate issuance, validity, revoke | Không chứng minh runtime còn hoạt động |
| **Kubernetes/service mesh** | Service accounts, workload binding, identities, RBAC | Không tự cho biết business owner |
| **CI/CD platform** | Pipeline tokens, deploy keys, runner identities | Thường có biến secret và quyền riêng |
| **SaaS/API gateway** | Integration accounts, API tokens, scopes, logs | Có thể thiếu quyền đọc hoặc thông tin nguồn |
| **Database/OS** | Technical users, grants, SSH keys, cron accounts | Không nằm trong SCIM hoặc IdP |
| **CMDB/service catalog** | Service, deployment, owner, lifecycle status | Có thể cũ hoặc thiếu tài khoản ngoại lệ |
| **Audit/SIEM/telemetry** | Token use, job execution, access decisions | Thiếu coverage không đồng nghĩa không sử dụng |

Nên đánh dấu **sourceSystem, extractedAt, sourceVersion, coverage và confidence** cho mỗi bản ghi. Không gộp hai principal chỉ vì cùng display name hoặc email.

## 10. Identity correlation: không nối sai account giữa các hệ thống

Một workload có thể xuất hiện dưới nhiều tên:

~~~text
Service catalog:   service=billing-sync, environment=prod
Cloud principal:   cloud-principal-9a7 (org-a account)
Kubernetes SA:     namespace=finance-prod, name=billing-sync
OAuth client:      clientId=billing-sync-prod-client
SaaS account:      integration-user-872
Vault secret ref:  vault/finance/billing-sync/legacy-api-key
~~~

Đây có thể là **một chuỗi tích hợp**, nhưng không được suy một-một nếu chưa có mapping chính thức. Nên lưu **principal type, issuer/namespace, tenant, targetAccountId, workloadId và deploymentRef**.

**Client ID không phải secret** và có thể giống chuỗi tên ở nơi khác; khi correlation cần dùng **issuer/tenant + clientId** hoặc khóa phù hợp contract. Với OIDC, **issuer + subject** có ý nghĩa trong phạm vi nguồn đã xác minh. **Email, hostname hoặc service name** không đủ để gộp identity trong môi trường đa tenant.

Nếu account mapping mơ hồ, đưa vào **UNVERIFIED_IDENTITY_LINK** và điều tra. Đừng dùng một review decision trên principal A để xóa nhầm credential của principal B.

## 11. Chuẩn hóa dữ liệu review item

Một item cần đủ thông tin để reviewer hiểu tác động:

| Thuộc tính | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **identityId/principalId** | nhi-prod-billing-sync | Định danh nội bộ/target ổn định |
| **principalType** | CLOUD_SERVICE_PRINCIPAL | Phân loại kỹ thuật |
| **serviceId/workloadId** | billing-sync | Liên kết nhiệm vụ |
| **ownerTeam/backupOwner** | finance-platform / sre | Trách nhiệm xử lý |
| **environment** | production | Tác động vận hành |
| **tenant/account/project** | org-a / cloud-prod | Phạm vi pháp nhân/hệ thống |
| **resourceScope** | billing API + finance datastore | Tài nguyên thực tế |
| **role/permissionPaths** | BillingReader via role binding | Đường cấp quyền |
| **credentialRefs** | cert-12, vault-secret-22 | Kiểm tra vòng đời credential |
| **trustBindings** | OIDC subject → cloud role | Ai có thể dùng identity |
| **lastUsedAt/coverage** | Có log 30 ngày, coverage 80% | Tín hiệu, không phải kết luận |
| **deploymentStatus** | ACTIVE | Căn cứ service catalog |
| **riskTier** | HIGH | Định tuyến reviewer |
| **reviewPolicy/version** | nhi-review-v4 | Cơ sở quyết định |
| **decision/remediation** | REDUCE/PENDING | Theo dõi đến khi verified |

Các trường chứa secret chỉ nên là **reference**, tuyệt đối không đưa password, private key, access/refresh token hoặc raw API key vào campaign.

## 12. Phân loại rủi ro của non-human account

| Yếu tố | Thấp hơn | Cao hơn |
| --- | --- | --- |
| **Permission** | Read một resource | IAM admin, delete, export, grant roles |
| **Scope** | Một service/namespace | Toàn cloud account, organization, nhiều tenant |
| **Credential** | Federated/short-lived, audience-bound | Static key dài hạn, lưu nhiều bản |
| **Trust** | Một workload/branch được ràng buộc | Wildcard repository hoặc bất kỳ principal |
| **Environment** | Test cô lập, dữ liệu giả | Production, tài chính, secret hoặc dữ liệu cá nhân |
| **Owner** | Có team và backup hợp lệ | Owner nghỉ việc/không xác định |
| **Usage telemetry** | Có audit và posture đủ | Không thể quan sát, log thiếu |
| **Lifetime** | Hết hạn theo job | Standing privilege không thời hạn |
| **Connectivity** | Đường xác thực bị giới hạn | API public, credential dễ tái sử dụng |
| **Dependencies** | Dễ thay thế và thu hồi | Một identity dùng chung cho nhiều hệ thống trọng yếu |

Một account tên **read-only** vẫn có thể rủi ro cao nếu đọc được secret hoặc toàn bộ dữ liệu khách hàng. Ngược lại account production có chức năng restart hạn chế có thể cần **JIT/PAM** hơn là loại bỏ hoàn toàn.

**Risk score chỉ giúp ưu tiên**, không thay policy hard deny hoặc phê duyệt của owner có thẩm quyền.

## 13. Khi nào cần review?

**Periodic campaigns** có thể được lên lịch theo risk tier: ví dụ tổ chức có thể chọn review quyền admin hằng quý, các integration read-only có owner rõ mỗi nửa năm hoặc theo lịch phù hợp. Đây là **ví dụ nội bộ**, không phải một chu kỳ bắt buộc chung cho mọi nền tảng.

**Event-driven triggers** quan trọng không kém:

- Người tạo/owner/chủ dự án **Mover hoặc Leaver**.
- Workload bị decommission, chuyển environment hoặc đổi namespace/tenant.
- Hết hợp đồng dịch vụ, vendor integration hoặc sponsor.
- Secret/certificate gần hết hạn, bị lộ hoặc rotation thất bại.
- Role/trust policy đổi quyền hoặc mở rộng subject được phép assume.
- Xuất hiện tài khoản **không có owner, lâu không sử dụng, key duplicate**.
- Phát hiện quyền wildcard hoặc SoD conflict.
- Sự kiện security incident hoặc bất thường token.
- Chuyển từ static secret sang workload federation.
- Thay đổi classification của dữ liệu/resource.

**Incident response và Leaver critical revocation không được chờ campaign**. Review hỗ trợ tái xác nhận quyền còn tồn tại và làm rõ ownership; những quyền cần cắt khẩn phải có workflow riêng theo SLA.

## 14. Review đúng thời điểm: snapshot và freshness

Khi bắt đầu campaign, IAM/IGA cần thu thập **snapshot** của account, role, credential, owner, service deployment, usage và trust relationship.

Một snapshot chỉ có ích khi nêu:

- **CollectedAt/extractedAt** cho từng target.
- **Source authority/version** và phạm vi thu thập.
- **Completeness/coverage** của entitlement và credential.
- **Observed effective rights** nếu có thể kiểm tra.
- **Current service/owner lifecycle** tại thời điểm đó.
- **Policy version** dùng để chấm điểm hoặc xác định conflict.
- **Review deadline/overall deadline**.

**Dữ liệu có thể đổi trong khi reviewer đang xử lý**. Role được mở rộng, service tạm dừng hoặc owner Leaver sau khi xuất snapshot. Trước remediation phải **revalidate** trạng thái hiện hành, không ghi đè thay đổi mới bằng quyết định cũ.

## 15. Expected, assigned, effective và used access

Phân biệt bốn lớp dữ liệu:

| Lớp | Câu hỏi | Nguồn |
| --- | --- | --- |
| **Expected access** | Workload nên có quyền gì theo nhiệm vụ và policy? | Service catalog, access approval, owner và IGA |
| **Assigned access** | Những grant nào đã cấu hình tại target? | IAM roles, group, API account, database GRANT |
| **Effective access** | Thực tế có thể làm gì theo trust, deny, scope, token và resource policy? | PDP/PEP, IAM policy evaluation, target API tests |
| **Used access** | Quan sát thấy hoạt động nào trong cửa sổ log? | Cloud/SaaS/API/DB telemetry |

Ví dụ:

~~~text
Expected:    BillingReader trên org-a/billing-reports
Assigned:    BillingReader + OrganizationAdministrator
Effective:   READ billing + MANAGE_ACCESS toàn org-a
Used:        READ billing mỗi ngày; không thấy MANAGE_ACCESS trong log 60 ngày

Finding:     quyền MANAGE_ACCESS vượt nhu cầu đã duyệt,
             không phải chỉ vì 'unused'.
~~~

**Không thấy usage không có nghĩa quyền thừa đã được chứng minh**: backup chạy mỗi quý, DR job chỉ chạy khi sự cố hoặc log thiếu coverage. **Có usage cũng không chứng minh quyền hợp lệ** nếu hành động đó vượt nhiệm vụ hoặc do credential đã bị lạm dụng.

## 16. Review đường cấp quyền trực tiếp và gián tiếp

Một identity có thể sở hữu quyền qua:

- Role trực tiếp hoặc group membership.
- Group lồng nhau và role hierarchy.
- Cloud identity policy cùng resource policy.
- Assume-role/trust relationships.
- Service-account token hoặc workload identity binding.
- Database role/schema grants.
- Direct ACL/share ở SaaS.
- Secret vault policy có thể đọc credential khác.
- Khả năng **impersonate**, **create service-account token**, **attach role** hoặc sửa policy.
- Quyền quản trị CI/CD có thể đổi workflow để tự nhận credential production.

Ví dụ:

~~~text
Workload: service-report-worker
  -> Kubernetes service account
  -> trusted federation subject
  -> cloud role DataReader
  -> resource policy cho READ bucket reports
  -> secret manager permission: GET_SECRET for admin-key
  -> indirect ability: use admin-key outside DataReader boundary
~~~

Role nhìn như **DataReader** nhưng quyền đọc admin secret tạo một đường đặc quyền gián tiếp. Review phải xem **những gì principal có thể đạt tới**, không chỉ role display name.

Với các engine tính effective permissions, cần xét **explicit deny, condition, resource scope, session policy và trust**. Một role wildcard là tín hiệu rủi ro nhưng việc được ALLOW ở hành động cụ thể phụ thuộc nhiều lớp.

## 17. Review secret, key, certificate và token

| Credential | Trường nên đánh giá | Lưu ý |
| --- | --- | --- |
| **Password** | Owner, vault, rotation, nơi sử dụng, shared exposure | Tránh dùng human account với password cố định cho bot |
| **API key** | Target, scope, issuedAt/expiry, lastUsed, revocation | Không phải API nào cũng hỗ trợ expiry tự động |
| **OAuth client secret** | Issuer, clientId, expiration, storage và permission | Không dùng clientId như secret |
| **Private key/certificate** | Certificate profile, notAfter, CA trust, revoke và key protection | Certificate validity không tự chứng minh owner hiện hành |
| **SSH deploy key** | Repository, read/write, host, rotation | Có thể bỏ sót ngoài IdP |
| **Cloud access key** | Principal, permissions, last used, lifecycle | Khác managed identity/temporary credential |
| **PAT** | Principal, owner, scopes, repo/resource | Có thể tồn tại sau khi nhóm IdP đổi |
| **Federated workload token** | Issuer, audience, subject claim, TTL và trust config | Thường ngắn hạn nhưng trust vẫn có thể quá rộng |
| **Kubernetes token** | Service account, pod binding, lifetime, projection | Không giả định mọi token đều short-lived |

**Không thu thập raw credential để review.** Campaign chỉ cần metadata và tham chiếu đã được kiểm soát. Nếu chưa biết tất cả bản sao secret tồn tại ở đâu, ghi **UNKNOWN_COPY_COVERAGE**, không khẳng định “vault là nơi duy nhất” chỉ vì ứng dụng có vault integration.

## 18. Rotation: thay credential không đồng nghĩa thu hẹp quyền

Một vòng rotation an toàn thường gồm:

1. Xác nhận **identity và target** thuộc phạm vi nào.
2. Tạo credential mới với **purpose/scope/TTL** đúng policy.
3. Cập nhật **vault/secret reference** và deployment được phép.
4. Xác minh workload dùng credential mới bằng health check hoặc test có kiểm soát.
5. Vô hiệu credential cũ trong **overlap window được quản lý**.
6. Kiểm tra session/token và đường truy cập cũ theo mức rủi ro.
7. Cập nhật inventory và log, ghi credentialRefs mới/cũ.

**Một rotation hoàn tất về mặt triển khai có thể vẫn không làm quyền giảm** nếu account tiếp tục giữ OrganizationAdmin. Ngược lại, xóa key cũ khi chưa xác định phụ thuộc có thể làm đứt pipeline. Review nên tách **credential decision** và **entitlement decision**.

Trong tình huống compromise, không nên chờ hết overlap window thông thường; cần **incident containment** và kế hoạch khôi phục theo policy, hạn chế thời gian credential nghi lộ còn được chấp nhận.

## 19. Chuyển từ static secret sang workload federation

Khi có nền tảng phù hợp, **workload identity federation** hoặc **managed identity** giúp giảm việc lưu bí mật dài hạn. Thay vì đặt một client secret không hạn trong pipeline, workload có thể trình token/assertion ngắn hạn từ một issuer đã được tin cậy để nhận quyền có phạm vi.

Nhưng chuyển sang federation **không xóa rủi ro trust policy**:

- **Issuer** có đúng nguồn đáng tin, không bị cấu hình quá rộng?
- **Audience** có đúng relying party/token exchange endpoint?
- **Subject/claims** có ràng buộc repository, branch, environment hoặc service account cụ thể?
- Có thể **tạo một workload giả** để có cùng claims không?
- Ai được sửa pipeline và trust configuration?
- Role/permission được nhận có vượt nhu cầu không?
- Token có TTL, proof/binding và revocation strategy phù hợp không?

**OIDC có thể cung cấp signed identity assertion cho federation**, nhưng không phải cứ có OIDC token là một principal được phép truy cập mọi cloud resource. Relying party phải xác minh issuer, signature, audience, thời gian, subject và chính sách trust.

Trong review, một trust policy **repo:any/branch:any → production-admin** có thể rủi ro hơn một static secret được giới hạn chặt, dù nó không lưu secret dài hạn. Cần đánh giá **đường kiểm soát thực tế**.

## 20. OAuth 2.0 và client credentials cho non-human account

Với dịch vụ gọi API không có người dùng tương tác, **OAuth 2.0 client credentials grant** là một lựa chọn nếu authorization server và resource server hỗ trợ.

~~~text
Workload -> Authorization Server:
    authenticate client using approved method
    request token with permitted scopes / audience

Authorization Server:
    validate client and granted permissions
    issue access token subject to policy

Workload -> Resource Server:
    present access token

Resource Server:
    validate token and check action/resource/tenant authorization
~~~

Trong review cần xem **client registration, credential/federation, permitted scopes, target audience, application roles, owner và token lifetime**.

**Client credentials không tự đại diện cho một người có employment**; nếu nghiệp vụ thật sự cần delegated access của con người, không dùng service principal toàn quyền để thay user consent mà bỏ qua authorization. **OAuth scope** là điều kiện token/API, không tự chứng minh quyền đọc mọi object hoặc tenant.

Token thu hồi ở Authorization Server chưa chắc làm một **self-contained JWT access token** bị từ chối ngay tại mọi resource server nếu chỉ kiểm tra chữ ký và expiry. Cần xem introspection, denylist, policy freshness, TTL và chiến lược thu hồi của hệ thống cụ thể.

## 21. Cloud IAM role và trust relationship

Trong cloud, service account hoặc service principal có thể **assume role** hoặc nhận quyền qua liên kết workload. Review phải trả lời đồng thời:

| Lớp | Câu hỏi |
| --- | --- |
| **Principal identity** | Principal nào được định danh, thuộc account/project/tenant nào? |
| **Trust policy** | Ai có thể sử dụng/assume/impersonate principal đó? |
| **Permission policy** | Khi được xác thực thì principal làm được gì? |
| **Resource policy** | Tài nguyên đích có điều kiện hoặc cấp quyền bổ sung không? |
| **Session conditions** | TTL, audience, claim, source network hoặc context có áp đúng không? |
| **Organization/tenant guardrails** | Có explicit deny hoặc giới hạn tổ chức không? |
| **Credential evidence** | Token issuance/audit còn hợp lệ và đủ mới không? |

Ví dụ, một service principal có role hẹp nhưng **mọi developer của organization đều có thể impersonate** nó thì phạm vi actor thực tế rộng hơn team sở hữu. Ngược lại role có permission READ ở cloud account A không tự cho phép cross-account access đến account B nếu trust/resource policy không cho.

**Không chỉ review policy gắn trực tiếp**, mà phải xét trust subject, khả năng thay role, principal chaining và đường privilege escalation.

## 22. Kubernetes: service account và workload identity

Một workload chạy trên Kubernetes có thể dùng **ServiceAccount** để tương tác Kubernetes API hoặc nhận token dùng trong cơ chế federation. Review cần kiểm tra:

- Namespace, ServiceAccount name, owner workload/deployment.
- RoleBinding/ClusterRoleBinding và quyền Kubernetes API.
- Token projection, audience, expiration và automount policy.
- Những pod/deployment nào được cấu hình dùng ServiceAccount này.
- Khả năng pod/SA có quyền đọc secret, tạo workload hoặc impersonate.
- Ánh xạ OIDC/workload federation sang cloud role nếu có.
- Admission/security context/network policy theo threat model.
- Audit policy và đường kiểm chứng quyền thực tế.

Ví dụ:

~~~text
Namespace: finance-prod
ServiceAccount: billing-sync
Kubernetes RBAC: read configmaps for own namespace
Cloud federation: subject system:serviceaccount:finance-prod:billing-sync
Cloud role: billing-read-only
Owner: finance-platform
~~~

Nếu trust policy chấp nhận **mọi ServiceAccount trong mọi namespace**, một workload không liên quan có thể nhận cloud role không đúng. Nhưng **Kubernetes ServiceAccount được tạo không tự chứng minh pod nào đã dùng nó**; cần đối chiếu workload spec, runtime attestation/logs và token issuance theo khả năng quan sát.

## 23. CI/CD và non-human identities trong pipeline

CI/CD có thể thực hiện build, test, release, deploy và thay hạ tầng production. Các danh tính cần review gồm **runner, build bot, deploy key, artifact publisher, OIDC federation client và release automation**.

| Vùng review | Câu hỏi |
| --- | --- |
| **Repository trust** | Branch/tag/ref nào được phép nhận quyền production? |
| **Workflow governance** | Ai được sửa pipeline YAML/scripts có thể lấy token? |
| **Secret storage** | Có long-lived key trong variable hoặc image không? |
| **Environment protection** | Production có yêu cầu approver độc lập không? |
| **Artifact provenance** | Bản build nào đang được deploy và ai ký? |
| **Runner isolation** | Runner chia sẻ có thể đọc secret của job khác không? |
| **Cloud role** | Quyền chỉ deploy một service hay admin cả account? |
| **Token handling** | TTL và audience có ngắn/hẹp theo nhu cầu không? |

Tài khoản **deploy-bot** có thể không có login tương tác nhưng vẫn có quyền production nhạy cảm. Không coi “không ai đăng nhập vào bot” là bằng chứng ít rủi ro. Ngược lại, việc pipeline không chạy 45 ngày có thể do chu kỳ release, không đủ căn cứ xóa.

**SoD** có thể yêu cầu người sửa code không được tự phê duyệt deployment production. Review phải xét cả **human control of CI/CD configuration** và **machine privileges**, không chỉ danh sách service principal.

## 24. SaaS integration, RPA và legacy service account

Một số SaaS chỉ hỗ trợ “integration user” có username/password hoặc API token tĩnh; RPA bot có thể đăng nhập UI giống con người. Đó là **hạn chế kỹ thuật**, không phải lý do miễn review.

Kiểm tra:

1. Nền tảng có **service principal/API-only account** thay user tương tác không?
2. API key có **scope, expiry, rotate, revoke** riêng không?
3. User/bot account có bị cấp **super-admin** vì thiếu role hẹp?
4. Credential có nằm trong **vault**, hay bị hardcode trong script/screenshot?
5. Bot có dùng **MFA bypass** được phê duyệt, và đường bypass có được giám sát không?
6. Có **owner, runbook, lịch job, tenant/resource** và hậu quả khi account disable không?
7. SaaS có **local role, share/ACL** nằm ngoài IdP/SCIM không?
8. Có kế hoạch **thay thế legacy integration** khi sản phẩm hỗ trợ giao thức an toàn hơn không?

**Không gán human account của nhân viên vào automation nếu không có căn cứ và không quản lý hậu quả khi nhân viên Leaver**. Với account legacy chưa thể thay, cần ngoại lệ có thời hạn, giảm quyền, kiểm soát credential và audit.

## 25. SCIM, IdP, SSO và giới hạn đối với non-human account

| Cơ chế | Hỗ trợ gì? | Không nên hiểu sai |
| --- | --- | --- |
| **HRIS** | Nhận biết owner/worker còn làm việc | Không phải nguồn quyền của mọi workload |
| **Service catalog/CMDB** | Owner, lifecycle, dependencies | Record ACTIVE có thể cũ hoặc thiếu NHI |
| **IdP** | Directory principal, app registration, policies | Không tự quan sát mọi token/key trong SaaS |
| **SSO/OIDC** | Xác thực user; có thể làm issuer cho federation | Không tự cấp quyền nghiệp vụ cho máy |
| **OAuth 2.0** | Client authentication, access tokens và scopes | Scope không thay object authorization |
| **SCIM 2.0** | Core User/Group provisioning ở Service Provider | Không chuẩn hóa đầy đủ mọi service principal/secret/cloud role |
| **IGA** | Workflow owner, review, expected entitlements và audit | Review decision không có nghĩa target đã áp quyền |
| **PAM/JIT** | Access đặc quyền có hạn, activation và session oversight | Không tự thay cloud/workload trust review |
| **RBAC/ABAC/PBAC** | Role và điều kiện permission theo ngữ cảnh | PEP vẫn phải thực thi ở resource/action cụ thể |

Một service account có thể nằm trong **SCIM User** của SaaS, nhưng nhiều hệ thống có **API token, local bot hoặc service principal riêng** không nằm trong SCIM core. **SCIM User active=false không tự thu hồi mọi client credential, token hoặc secret**.

**IdP user SSO logout không phải biện pháp revoke NHI đầy đủ**. Cần tìm đúng **principal, credential issuer, resource server và vault/PKI**.

## 26. RBAC, ABAC và PBAC khi review NHI

**Role-Based Access Control (RBAC)** gán quyền qua role; **Attribute-Based Access Control (ABAC)** sử dụng các thuộc tính workload, tài nguyên và môi trường; **Policy-Based Access Control (PBAC)** tổ chức quy tắc quyết định theo chính sách. Một quyền được cấp trong catalog chưa chắc là quyền hiệu lực tại resource server.

Một policy minh họa:

~~~text
ALLOW READ_BILLING_REPORT(report) IF
    principal.type == WORKLOAD
    AND principal.serviceId == "billing-sync"
    AND principal.environment == "production"
    AND principal.tenantId == report.tenantId
    AND principal.hasRole("BillingReader", report.projectId)
    AND credential.issuer IN trustedIssuers
    AND credential.audience == "billing-api"
    AND credential.notExpired
    AND workload.trustBindingCurrentlyValid
    AND NOT principal.suspended
    AND noHigherPriorityDeny
~~~

Đây là **mã giả**. Resource server cần kiểm tra **đúng object/action/tenant**, không chỉ tin client gửi header serviceId. **Một token được cấp scope billing:read không tự cấp quyền đọc mọi hóa đơn của mọi tenant**.

Review phải thấy:

- **Tập role được gán** và quyền phát sinh qua hierarchy/trust.
- **Policy conditions** thực sự giới hạn môi trường, nguồn và tài nguyên.
- **Explicit deny** và ngoại lệ theo tenant.
- **Policy version/freshness** tại PDP/PEP.
- **Những endpoint** không đi qua cơ chế authorization dự kiến.

**Quyết định KEEP role vẫn không miễn trừ ràng buộc ABAC/PBAC** sau khi service chuyển owner, đổi environment hoặc tài nguyên thay classification.

## 27. Separation of Duties và quyền điều khiển gián tiếp

**SoD (Segregation of Duties)** không chỉ áp dụng cho hai role của con người. Với NHI, phải xem **ai có thể điều khiển workload**, thay code, phát hành token, approve deployment và sửa audit.

| Khả năng A | Khả năng B | Rủi ro |
| --- | --- | --- |
| Pipeline tự build artifact | Pipeline tự approve và deploy production | Bỏ qua kiểm tra độc lập |
| Bot tạo hóa đơn | Bot phê duyệt chính hóa đơn nó tạo | Tự hoàn tất giao dịch nhạy cảm |
| Service principal cấp IAM role | Cùng principal thay audit/monitoring | Leo thang quyền và che dấu |
| Developer sửa workload federation trust | Cùng người tự approve quyền production | Tự mở đường impersonation |
| NHI đọc secret admin | NHI chạy lệnh thay tài nguyên | Vượt giới hạn role trực tiếp |

Một service account có thể cần hai khả năng vì lịch vận hành; nếu policy cho phép ngoại lệ, phải có **risk owner, approval độc lập, compensating controls, phạm vi, thời hạn và giám sát**. Không dùng nhãn “bot” để miễn SoD hoặc cho phép mọi action.

Với **dynamic SoD**, kiểm soát phải ở cấp giao dịch: ví dụ **creator identity không được approve cùng invoice**, không chỉ tách tên role trên portal.

## 28. Quy trình review non-human account đầu cuối

~~~mermaid
flowchart TD
    A["Xác định risk scope & campaign"] --> B["Inventory principal / credential / trust / owner"]
    B --> C["Identity correlation, snapshot và coverage"]
    C --> D["Tính expected, assigned, effective và used access"]
    D --> E["Phân reviewer đủ thẩm quyền"]
    E --> F{"Nhiệm vụ và quyền còn hợp lệ?"}
    F -->|"Cần giữ"| G["KEEP có căn cứ / lịch review"]
    F -->|"Thừa scope"| H["REDUCE / REPLACE / ROTATE"]
    F -->|"Hết nhu cầu"| I["REVOKE / DECOMMISSION"]
    F -->|"Thiếu owner"| J["TRANSFER_OWNER / điều tra"]
    F -->|"Ngoại lệ"| K["RISK REVIEW / exception có hạn"]
    F -->|"Không rõ"| L["NEEDS_EVIDENCE / không auto Keep"]
    H --> M["Impact analysis và remediation plan"]
    I --> M
    J --> M
    K --> N["Duyệt kiểm soát bù, expiry và owner"]
    G --> O["Audit quyết định"]
    N --> O
    M --> P["Thực thi qua target, vault, CI/CD, IAM"]
    P --> Q["Readback và kiểm tra effective access"]
    Q --> R{"Đạt expected state?"}
    R -->|"Có"| O
    R -->|"Không/UNKNOWN"| S["UNVERIFIED/BLOCKED, owner và deadline"]
    S --> Q
    L --> E
    O --> T["Campaign/KPI/recertification tiếp theo"]
~~~

**Một quyết định KEEP không nhất thiết đòi thay đổi kỹ thuật**, nhưng phải có owner, scope và bằng chứng đủ tin cậy. **Một quyết định REVOKE phải qua remediation/readback**, không được đóng chỉ vì reviewer nhấn nút thu hồi.

## 29. Phân người review theo thẩm quyền, không theo convenience

Một item có thể cần nhiều quyết định:

| Nội dung cần xác nhận | Reviewer phù hợp |
| --- | --- |
| Service còn chạy và có business justification | Service/business owner |
| Credential đang được workload dùng thế nào | Technical owner, platform team |
| NHI được đọc dữ liệu tài chính nào | Finance data owner |
| Role cloud có thể cấp quyền/impersonate không | Cloud IAM/security owner |
| Trust của CI/CD có cho deployment production không | Platform/Security và release governance |
| Chấp nhận ngoại lệ static key, wildcard | Risk owner theo ngưỡng chính sách |
| Xác minh hậu kiểm quyền đã bị thu hồi | IAM/target operator hoặc reviewer độc lập theo policy |

Reviewer **không nhất thiết phải là người tạo credential**; credential có thể đã được tạo nhiều năm trước. Người duyệt phải có authority đối với **role, tenant, resource classification và risk tier**.

Nếu một account được nhiều dịch vụ dùng chung, phải **xác minh từng dependency và owner**; việc một team chọn Revoke có thể làm ứng dụng khác ngừng chạy. Tình huống này là dấu hiệu cần **tách shared identity** thành principal riêng khi có thể.

## 30. Ma trận quyết định review

| Quyết định | Khi nào hợp lý? | Hành động và bằng chứng |
| --- | --- | --- |
| **KEEP/ATTEST** | Service còn cần, quyền/credential/trust phù hợp | Ghi owner, justification, expiry/review next |
| **REDUCE** | Quyền hoặc trust scope rộng hơn nhiệm vụ | Thu hẹp role, API scope, resource/branch/tenant, kiểm thử |
| **ROTATE** | Credential cũ/rủi ro hoặc đến lịch rotation | Cấp mới, verify use, vô hiệu cũ và readback |
| **REPLACE/MIGRATE** | Static secret có thể đổi sang managed/federated identity | Migration kế hoạch, canary, đối soát và xóa đường cũ |
| **TRANSFER_OWNER** | Owner đã Mover/Leaver nhưng service còn cần | Chủ mới chấp nhận trách nhiệm, rà soát mọi key/quyền |
| **REVOKE/DECOMMISSION** | Service không còn nhiệm vụ, có đường thay thế | Phân tích dependency, revoke/trust/secret, xác minh Deny |
| **TEMPORARY_EXCEPTION** | Có nhu cầu thật và chưa thể sửa kiến trúc | Risk approval độc lập, compensating controls, hạn và follow-up |
| **NEEDS_EVIDENCE/BLOCKED** | Account mapping, owner hoặc target rights chưa chắc | Điều tra, không tự kết luận hợp lệ |

**ROTATE và REDUCE là hai quyết định khác nhau**. Account vẫn có thể bị overprivileged sau rotation; role có thể đã được giảm nhưng static key vẫn bị rò rỉ.

**KEEP không đồng nghĩa gia hạn credential vô thời hạn**. Nếu certificate hoặc grant có thời hạn, muốn kéo dài phải đáp ứng policy cấp/renewal riêng.

## 31. Tính quyền và rủi ro cho reviewer bằng ngôn ngữ nghiệp vụ

Người duyệt không nên chỉ thấy:

~~~text
principalId: cloud-sa-09
roles: RoleA, RoleB, TokenPolicy3
lastUsed: 2026-11-02
~~~

Thay vào đó, hiển thị:

~~~text
Service: Billing sync production
Owner: Finance Platform
Business purpose: Đồng bộ hóa đơn từ ERP sang hệ thống báo cáo
Environment/Tenant: production / org-a
Observed actions: READ billing, WRITE processed-status
Risk: Có khả năng MANAGE_ACCESS trên cả org-a
Credential: Static key đã tồn tại lâu, vault managed, expiry không rõ
Dependencies: ERP job 02:00, billing-api client, dashboard service
Recommended actions:
  1. Reduce cloud role: bỏ MANAGE_ACCESS
  2. Migrate static key -> workload federation
  3. Validate production smoke tests
Evidence coverage: Billing API audit 90 ngày, cloud control-plane audit đủ,
                   khả năng sử dụng credential ở third-party UNKNOWN
~~~

**Rõ business purpose giúp tránh rubber-stamping**. Nhưng reviewer vẫn cần được xem những permission kỹ thuật có rủi ro: có thể đọc secret, sửa policy hoặc impersonate principal khác.

## 32. Ví dụ JSON của một review item

Đây là **schema minh họa do tổ chức tự thiết kế**, không phải SCIM hoặc OIDC standard:

~~~json
{
  "campaignId": "nhi-recert-2026-q4",
  "reviewItemId": "nhi-item-0029",
  "principal": {
    "identityId": "nhi-billing-sync-prod",
    "principalType": "SERVICE_PRINCIPAL",
    "issuer": "org-a-cloud-identity",
    "targetPrincipalId": "cloud-sp-9a7",
    "tenantId": "org-a"
  },
  "workload": {
    "serviceId": "billing-sync",
    "environment": "production",
    "ownerTeam": "finance-platform",
    "backupOwner": "sre-oncall",
    "lifecycleState": "ACTIVE"
  },
  "access": {
    "expectedRoles": ["BillingReader", "BillingStatusWriter"],
    "assignedRoles": ["BillingReader", "BillingStatusWriter", "OrgIAMAdmin"],
    "effectiveRiskFinding": "EXCESSIVE_IAM_PRIVILEGE",
    "targetResources": ["billing-data/org-a", "billing-api/org-a"]
  },
  "credentials": [
    {
      "credentialRef": "vault/billing-sync/legacy-key",
      "type": "STATIC_API_KEY",
      "expiryStatus": "UNKNOWN"
    },
    {
      "credentialRef": "federation/billing-sync",
      "type": "OIDC_WORKLOAD_FEDERATION",
      "status": "CONFIGURED"
    }
  ],
  "evidence": {
    "snapshotVersion": "snapshot-2026-q4-v7",
    "usageWindowDays": 90,
    "usageCoverage": "PARTIAL",
    "targetReadbackAt": "2026-11-23T09:00:00+07:00"
  },
  "review": {
    "reviewerRef": "finance-service-owner",
    "decision": "REDUCE_AND_MIGRATE",
    "decisionStatus": "APPROVED",
    "remediationStatus": "PENDING",
    "effectiveAccessVerified": "UNKNOWN"
  }
}
~~~

**Từ UNKNOWN phải được giữ đúng nghĩa**. Không có proof rằng key không còn dùng được thì không thể viết revoked=true hoặc verified=true chỉ vì owner đã tick checkbox.

## 33. Reviewer timeout và account không có người chịu trách nhiệm

Khi một reviewer không phản hồi trước deadline, workflow có thể **nhắc việc, escalate, reassign** đến owner đã được ủy quyền hoặc xử lý theo terminal policy. Không mặc định:

- **KEEP** tất cả tài khoản vì không ai phản đối.
- **REVOKE** tất cả service production ngay lập tức mà không xem dependency.
- **Auto-approve** quyền admin vì manager quá hạn.

Với quyền đặc biệt nguy hiểm, một chính sách đã phê duyệt trước có thể yêu cầu **tạm đình chỉ grant hoặc credential**, kết hợp cơ chế vận hành dự phòng. Nếu không đủ bằng chứng, trạng thái đúng là **OVERDUE/NEEDS_OWNER/BLOCKED**, kèm owner/escalation và SLA.

**Người duyệt cũ đã Leaver hoặc mất quyền approver không được dùng link email cũ để phê duyệt**. Cần kiểm tra authority tại thời điểm nhận decision, chống callback muộn và race condition.

## 34. Khi owner đổi vai trò hoặc nghỉ việc

Owner lifecycle là một **trigger review**, không đồng nghĩa NHI lifecycle kết thúc.

| Sự kiện của owner | Việc cần làm với NHI |
| --- | --- |
| **Owner Joiner** | Xác minh họ được giao trách nhiệm, có training và phê duyệt đúng scope |
| **Owner Mover** | Xác định NHI nào còn theo owner mới/team cũ, chuyển owner có kiểm soát |
| **Owner Leaver** | Thu hồi quyền cá nhân, PAT, credential đã biết; tìm owner mới |
| **Team giải thể** | Chuyển service/app owner hoặc decommission service có kế hoạch |
| **Contractor sponsor hết hạn** | Xác minh integration còn căn cứ, sponsor mới nếu được phép |
| **Resource owner đổi** | Reapprove entitlement dữ liệu nhạy cảm theo policy |

Chủ sở hữu mới không nên chỉ nhận một email “đã chuyển account”. Họ cần **chấp nhận business purpose, inventory credential, privileges, dependency, incident on-call, rotation responsibilities và lịch review tiếp theo**.

Không để **những secret từng thuộc sở hữu người cũ** tiếp tục dùng mà chưa đánh giá khả năng người đó còn bản sao. Cần rotation/revocation theo risk, không chỉ đổi trường ownerTeam.

## 35. Joiner: tạo non-human account theo nhu cầu được xác minh

Non-human identity mới có thể được tạo khi một ứng dụng/service mới triển khai, do nhân viên Joiner nhận nhiệm vụ phát triển hoặc vận hành.

1. **Đăng ký service/workload** với serviceId, mục đích và environment.
2. Giao owner/team và người duyệt có thẩm quyền.
3. Xác định **target system, tenant, resource, actions, TTL và trust policy**.
4. Ưu tiên **managed/federated identity hoặc credential ngắn hạn** khi nền tảng hỗ trợ.
5. Kiểm tra **least privilege, SoD, privilege escalation và cross-tenant scope**.
6. Phê duyệt role/trust/credential theo risk tier; không để developer tự cấp OrgAdmin mặc định.
7. Provision principal và credential bằng nguồn được kiểm soát.
8. Readback quyền được gán và kiểm thử **ALLOW cho thao tác hợp lệ, DENY ngoài scope**.
9. Thiết lập monitoring, owner backup, rotation và recertification cadence.

**Joiner con người không tự làm phát sinh NHI production admin**. Một developer mới chỉ được tạo pipeline identity sau khi service owner/cloud owner đã cấp quyền trong phạm vi trách nhiệm.

## 36. Mover: chuyển service, đội sở hữu hoặc môi trường

Sự kiện Mover của người owner hoặc của chính workload có thể làm thay đổi **expected access**.

Ví dụ integration chuyển từ **LegacyERP** sang **BillingAPI v2**:

| Quyền | Trước Mover | Sau Mover mong muốn |
| --- | --- | --- |
| READ LegacyERP | Có | REVOKE sau cutover đã kiểm chứng |
| WRITE LegacyERP status | Có | REVOKE |
| READ BillingAPI v2 | Chưa có | ALLOW theo scope mới |
| WRITE BillingAPI v2 | Không | Chỉ thêm nếu nghiệp vụ yêu cầu |
| OrgIAMAdmin | Không cần | DENY |

Một kế hoạch đúng phải:

- Ghi **cutover time/rollback window** và trạng thái phiên bản deployment.
- Đối chiếu cả **role, credential, trust, token và direct ACL** ở dịch vụ cũ.
- Thực hiện migration có thể rollback trước khi cắt quyền cũ nếu nghiệp vụ cho phép.
- Không để “temporary dual access” tồn tại mãi sau cutover.
- Đọc lại quyền tại hai hệ thống và kiểm thử negative cases.

**Chuyển người owner** và **chuyển environment/tenant** là hai hoạt động khác nhau; một approval cho quyền ở dev không tự hợp lệ với production.

## 37. Leaver: thu hồi quyền người, bảo vệ continuity của workload

**Leaver** của nhân viên tạo/owner NHI đòi hỏi hai luồng song song:

### Thu hồi quyền cá nhân

- Khóa/thu hồi **user session, IdP role, PAT, SSH key, API key cá nhân và local access** theo quan hệ đã hết.
- Kiểm tra khả năng người cũ còn biết **shared secret** và rotate theo policy.
- Loại người cũ khỏi **vault ACL, cloud IAM role, CI/CD deploy permissions và approver chain**.
- Ngăn job cũ cấp lại quyền cá nhân từ event/approval trễ.

### Duy trì hoặc kết thúc NHI

- Nếu workload vẫn cần, **chuyển owner sang người/nhóm hợp lệ**, rà soát credential/trust và không dùng quyền cá nhân của Leaver.
- Nếu workload không còn nhiệm vụ, tạo **decommission plan**, xác định dependency và thu hồi principal/role/credential.
- Đối soát target rights và trạng thái token.

**Không tự xóa service account production chỉ vì người tạo đã nghỉ**, nhưng cũng **không được giữ credential do họ có thể truy cập vô thời hạn**. Review phải kết hợp continuity và risk containment.

## 38. Offboarding non-human account: an toàn hơn một nút Delete

Một service account có thể được dùng bởi nhiều job nên cần **dependency-aware decommission**:

1. Xác nhận **business owner** và quyết định ngừng service.
2. Liệt kê **deployments, jobs, API consumers, queues, SaaS integrations và secret references**.
3. Xác minh có account **thay thế** hoặc đường rollback đã phê duyệt.
4. Chặn phát sinh **credential/grant mới** từ quy trình cũ.
5. Thử **disable có kiểm soát** hoặc giới hạn scope theo policy.
6. Theo dõi health/telemetry của dịch vụ phụ thuộc.
7. Revoke **cloud roles, trust bindings, API tokens, PKI certificates, vault access và direct ACL**.
8. Xử lý **running sessions, cached tokens, long-lived credentials** theo target.
9. Đọc lại target và thử hành động ngoài quyền phải **DENY**.
10. Lưu **audit, dữ liệu cần bảo toàn và trạng thái RETIRED**, thay vì xóa mọi dấu vết lịch sử.

Nếu hệ thống không thể xác minh một đường quyền đã mất, giữ trạng thái **UNVERIFIED** và có owner. **Delete local user thành công không chứng minh remote SaaS token đã hết hiệu lực**.

## 39. Xử lý tài khoản mồ côi và không rõ mục đích

Một principal có thể:

- Không có owner trong service catalog.
- Có owner cũ đã Leaver.
- Không tìm thấy deployment hiện hoạt.
- Có secret chưa biết nơi dùng.
- Không có audit được thu thập.
- Có quyền rất rộng hoặc truy cập production.

**Không nên giải quyết mọi item bằng KEEP vì sợ hệ thống lỗi**, cũng không nên tự xóa tất cả account lạ. Có thể dùng quy trình:

~~~mermaid
flowchart TD
    A["Phát hiện NHI orphaned/unknown"] --> B["Xác minh identity, tenant, credential, role"]
    B --> C["Tra cứu service catalog, deployment, logs, owner"]
    C --> D{"Có owner và nhu cầu được xác minh?"}
    D -->|"Có"| E["Reassign / review least privilege và secret"]
    D -->|"Chưa"| F["Risk-based containment / hạn chế grant mới"]
    F --> G["Tìm dependency, đặt deadline và escalation"]
    G --> H{"Dependency hợp lệ?"}
    H -->|"Có"| E
    H -->|"Không"| I["Decommission plan / revoke có kiểm soát"]
    H -->|"UNKNOWN"| J["BLOCKED với owner, không auto Keep"]
    E --> K["Readback + audit"]
    I --> K
~~~

Với quyền nguy hiểm như **OrgIAMAdmin không có owner**, incident response có thể yêu cầu containment nhanh. Nhưng quyết định phải phù hợp risk và phương án khôi phục, không che giấu việc thiếu dữ liệu bằng nhãn “đã được review”.

## 40. Pseudocode: đánh giá điều kiện review

~~~text
reviewNonHumanPrincipal(item, reviewer, requestedDecision):
    principal = resolvePrincipal(item.issuer, item.tenant, item.principalId)
    service = loadAuthoritativeServiceRecord(item.serviceId)
    owner = verifyCurrentServiceOwner(service)

    if principal.isAmbiguous or principal.isUnknown:
        return NEEDS_IDENTITY_CORRELATION

    if not reviewer.authorizedFor(principal, item.resourceScope, item.riskTier):
        return FORBIDDEN_REVIEW_DECISION

    if reviewer.hasProhibitedSoDConflict(principal, item):
        return INDEPENDENT_REVIEW_REQUIRED

    current = readCurrentRolesTrustCredentialsAndGrants(principal)
    if current.materiallyDifferentFrom(item.snapshot):
        return REVALIDATION_REQUIRED

    expected = calculateExpectedAccess(
        service.purpose,
        owner,
        principal.environment,
        item.tenant,
        current.policyVersion
    )

    risk = evaluateRisk(
        current.permissionExpansion,
        current.trustSubjects,
        current.credentialExposure,
        current.telemetryCoverage,
        expected
    )

    if requestedDecision == KEEP:
        if not service.active or not owner.valid:
            return MISSING_BUSINESS_EVIDENCE
        if risk.hardDeny or current.hasUnapprovedPrivilege:
            return POLICY_DENIED_OR_REMEDIATION_REQUIRED
        recordAttestationWithReasonAndExpiry(item, reviewer)
        return ATTESTED_WITH_REVIEW_CADENCE

    if requestedDecision in [REDUCE, ROTATE, REPLACE, REVOKE, TRANSFER_OWNER]:
        requireImpactPlanAndCorrectApprover(item, requestedDecision)
        createScopedRemediation(item, requestedDecision, expected, current)
        return REMEDIATION_PENDING

    if requestedDecision == TEMPORARY_EXCEPTION:
        requireIndependentRiskApprovalControlsAndExpiry(item)
        return EXCEPTION_PENDING_OR_APPROVED

    return NEEDS_EVIDENCE
~~~

**Đây là mã giả nghiệp vụ**, không phải SDK chạy trực tiếp. Hệ thống thực tế phải phân biệt điều kiện được phép auto-review theo policy với trường hợp cần human attestation, và xử lý thiếu target data bằng **UNKNOWN/INDETERMINATE**, không suy ra tài khoản an toàn.

## 41. Pseudocode: remediation và readback chống cấp lại quyền cũ

~~~text
executeNhiRemediation(remediationId):
    job = loadVersionedRemediation(remediationId)
    current = loadCurrentAuthoritativeWorkloadAndPrincipalState(job)

    if job.state in [CANCELLED, VERIFIED_CLOSED]:
        return NO_ACTION

    if current.isNewerMaterialChangeThan(job.snapshot):
        return REVALIDATION_REQUIRED

    if job.isRevocation:
        disableNewCredentialIssuanceAndTrustIfNeeded(job)
        revokeTargetRoleGrantCredentialWithIdempotency(job)
        verifyNoUnauthorizedRegrantFromOldJobs(job)

    if job.isRotation:
        issueScopedCredentialUnderApprovedPolicy(job)
        verifyConsumerUsingNewCredential(job)
        revokeOldCredentialAccordingToRiskAndCutover(job)

    if job.isReduction:
        applyApprovedNarrowerScopeAtTarget(job)

    observed = readTargetPrincipalsRolesTrustAndCredentialStatus(job)
    if observed.unavailable:
        return UNVERIFIED_WITH_OWNER_AND_DEADLINE

    effective = verifyAllowedAndDeniedActionsOnAuthorizedTestResources(job)
    if not effective.matchesExpected:
        return REMEDIATION_NOT_COMPLETE

    recordEvidenceWithTargetVersionAndVerificationTime(job, observed)
    return VERIFIED_CLOSED
~~~

**Hai hệ thống độc lập không tạo transaction nguyên tử chỉ vì cùng một workflow**. Cần idempotency, retry có kiểm soát, snapshot/version, state transition và reconciliation. Nếu connector timeout, **không retry tạo key hoặc cấp role mù quáng** trước khi đọc lại target.

Không coi **effective DENY tại một endpoint** là chứng minh mọi đường quyền đã bị vô hiệu; review cần ghi phạm vi các endpoint, session, token và tài nguyên đã kiểm tra.

## 42. Audit trail của một NHI review

Một bản ghi audit nên giải thích:

- **Campaign, reviewItem và snapshot version** nào được dùng.
- **Principal/workload/target/tenant** được liên kết ra sao.
- **Service owner, reviewer và thẩm quyền phê duyệt** tại thời điểm quyết định.
- **Nhiệm vụ, expected rights, quyền đang gán, permission expansion/trust**.
- **Credential metadata** nào được review mà không lộ secret.
- **Quyết định, lý do, exception, approval chain**.
- **Remediation command, connector result, target readback và effective access test**.
- **Các điểm thiếu bằng chứng, owner, deadline và incident references**.

Ví dụ:

~~~json
{
  "eventId": "nhi-audit-2026-0029",
  "correlationId": "nhi-recert-2026-q4-item-0029",
  "eventType": "NHI_PERMISSION_REDUCED",
  "principalRef": "org-a/cloud-sp-9a7",
  "workloadRef": "billing-sync-prod",
  "ownerTeam": "finance-platform",
  "reviewerRef": "finance-service-owner",
  "targetSystem": "cloud-iam",
  "targetTenant": "org-a",
  "permissionRemoved": "OrgIAMAdmin",
  "permissionRetained": ["BillingReader", "BillingStatusWriter"],
  "decisionRef": "review-decision-029",
  "sourceSnapshotVersion": "snapshot-2026-q4-v7",
  "targetRoleReadback": "VERIFIED",
  "effectiveAccessTest": "VERIFIED_WITHIN_TEST_SCOPE",
  "occurredAt": "2026-11-23T10:15:00+07:00",
  "policyVersion": "nhi-review-v4"
}
~~~

**Audit dữ liệu nhạy cảm cần tối thiểu hóa và bảo vệ khỏi sửa/xóa trái phép**. Người có quyền quản trị chính NHI không nên đồng thời có quyền xóa toàn bộ log về các hoạt động của NHI nếu policy yêu cầu độc lập.

## 43. Monitoring và cảnh báo sau review

| Tín hiệu | Ý nghĩa | Hành động |
| --- | --- | --- |
| NHI không có owner hoặc owner Leaver | Governance drift | Transfer owner, đánh giá secrets |
| Credential đến hạn nhưng chưa rotate | Rủi ro outage/secret tồn dư | Plan renewal/rotation |
| Static secret mới được tạo ở prod | Có thể bypass federation policy | Review approval và scope |
| Role wildcard cấp thêm ngoài approved delta | Privilege creep | Reconcile role/trust |
| Principal được impersonate bởi workload lạ | Trust mở rộng hoặc compromise | Điều tra issuer, subject, token |
| Dùng key từ IP/vùng bất thường | Có thể lạm dụng | Correlate network/context, tránh kết luận chỉ từ IP |
| NHI vẫn ALLOW sau revoke | Quyền tồn dư | Chặn và điều tra target/session |
| Workload đã decommission nhưng principal ACTIVE | Account mồ côi | Revocation plan |
| API client dùng scope ngoài nhiệm vụ | Overprivilege | Reduce scope, API authorization |
| Review 100% KEEP trong vài giây | Rubber-stamping đáng nghi | Xem reviewer và chất lượng evidence |
| CI/CD trust mở rộng sang mọi branch | Risk tăng mạnh | Giới hạn ref/environment |
| Credential mới có owner không xác định | Secret inventory gap | Assign/validate owner, audit |

**Alert không có nghĩa finding đã được xác nhận**. Một workload DR có thể không sử dụng nhiều tháng nhưng vẫn cần tồn tại. Kết luận dựa trên **business purpose, trust, target effective rights, telemetry coverage và approval**.

## 44. Những anti-pattern thường gặp

| Sai lầm | Hệ quả | Cải thiện |
| --- | --- | --- |
| Chỉ review human accounts | Bỏ sót bot, keys, service principals | NHI inventory đa nguồn |
| Mọi NHI đều gán owner “IT Admin” | Không ai chịu trách nhiệm nghiệp vụ | Service owner cụ thể + backup |
| Review chỉ hỏi account ACTIVE không | Không thấy privilege/trust/secret | Phân tích quyền, credential và dependencies |
| Không thấy usage nên xóa ngay | Gián đoạn DR, batch hoặc integration chu kỳ | Kiểm tra coverage và kế hoạch cutover |
| Không thấy usage nên giữ vì “chắc vẫn cần” | Tồn dư account vô hạn | Owner attestation và review deadline |
| Giữ secret không hạn trong source code | Lộ credential và khó thu hồi | Vault/federation/short-lived |
| Rotate key nhưng giữ role OrgAdmin | Overprivilege vẫn còn | Review quyền độc lập |
| Federation có subject wildcard | Mọi workload có thể nhận role | Bound issuer/audience/subject |
| Xóa role từ IdP rồi đóng request | Local ACL/API key vẫn hoạt động | Target readback và effective checks |
| Service owner Leaver bị xóa service ngay | Production outage | Chuyển owner và xử lý secret |
| Không bao giờ decommission vì sợ outage | Account/credential mồ côi tăng | Dependency-aware revoke |
| Developer tự duyệt production admin | SoD conflict | Approval độc lập và PAM/JIT |
| Chỉ dùng screenshot làm evidence | Không có trạng thái kỹ thuật đáng tin | Structured audit + source/version + readback |
| Ghi API key vào log review | Tạo credential leakage | Metadata reference, redaction |

**Chất lượng review không đo bằng số lượng checkbox**. Kết quả tốt là giảm quyền thừa, credential rủi ro và account mồ côi mà vẫn đáp ứng dịch vụ hợp lệ.

## 45. KPI cho chương trình Review non-human account

| KPI | Mục tiêu | Lưu ý diễn giải |
| --- | --- | --- |
| **NHI inventory coverage** | Phần target/principal được phát hiện | Cần khai báo target chưa bao phủ |
| **Owner-attested NHI ratio** | Có owner hiện hành đã xác nhận | Không chỉ có một email không người nhận |
| **High-risk entitlement review completion** | Quyền nhạy cảm được review đúng hạn | Tách approved và remediation verified |
| **Orphaned identity count** | Phát hiện/giảm account thiếu owner | Phân loại shared/legacy |
| **Unbounded trust count** | Federation/assume role quá rộng | Đánh giá cả direct và indirect trust |
| **Long-lived static credential ratio** | Hướng tới short-lived/federated | Không xóa ngay khi không có giải pháp |
| **Credential rotation success** | Secret mới dùng được và secret cũ vô hiệu | Không đếm chỉ issuance |
| **Overprivileged NHI ratio** | Quyền vượt expected | Phụ thuộc completeness của expected model |
| **Time to verified revocation** | Độ trễ từ decision đến effective Deny | Có thể khác theo target/risk tier |
| **Residual access after Leaver/retirement** | Quyền còn sau khi căn cứ mất hiệu lực | Ưu tiên theo severity |
| **Review overdue rate** | Các item không có decision đúng hạn | Không tự coi timeout là Keep |
| **Unverified-remediation ratio** | Phần target không có bằng chứng readback | UNKNOWN không được tính PASS |
| **Regrant-after-revoke count** | Phát hiện event/worker cũ tái cấp quyền | Xem source version và idempotency |

### Công thức minh họa

~~~text
Verified remediation completion rate
  = Số remediation có target readback + effective checks đạt yêu cầu
    / Tổng remediation cần xác minh trong phạm vi đo

Ownerless high-risk NHI ratio
  = Số NHI HIGH/PRIVILEGED thiếu accountable owner hợp lệ
    / Tổng NHI HIGH/PRIVILEGED đã kiểm kê có dữ liệu đủ để phân loại
~~~

**Không đưa UNKNOWN vào nhóm an toàn** để làm đẹp tỷ lệ. Thời điểm snapshot, nguồn dữ liệu, cách tính “đủ để phân loại” và exclusion phải rõ ràng.

## 46. Bộ kiểm thử rà soát non-human account

| Test | Tình huống | Kết quả mong muốn |
| --- | --- | --- |
| T01 | Principal có owner, mục đích và role phù hợp | KEEP được ghi với justification và review cadence |
| T02 | Service account không có owner | NEEDS_OWNER/ESCALATE, không auto KEEP |
| T03 | Owner đã Leaver nhưng service production vẫn chạy | Transfer owner + đánh giá credential, không auto xóa service |
| T04 | Static key nằm ngoài vault | Finding credential sprawl/rotation |
| T05 | Service ReadOnly có quyền đọc admin secret | Phát hiện privilege escalation gián tiếp |
| T06 | Role cloud có wildcard ngoài scope | REDUCE/owner approval theo policy |
| T07 | Role đã thu hẹp nhưng API key cũ vẫn admin | Không VERIFIED_CLOSED |
| T08 | Credential rotate nhưng key cũ còn active | Không đánh rotation hoàn tất |
| T09 | Credential gần expiry và workload DR chạy theo quý | Lập kế hoạch, không xóa chỉ vì 90 ngày không dùng |
| T10 | OAuth client credentials có scope mọi tenant | Phát hiện cross-tenant overprivilege |
| T11 | OIDC trust cho bất kỳ repository/branch | Phát hiện overbroad federation subject |
| T12 | CI/CD role prod được sử dụng từ pipeline dev | Deny nếu sai trust/environment |
| T13 | Kubernetes SA có cluster-admin không cần thiết | Flag risk, reduce theo nhiệm vụ |
| T14 | API của SaaS chỉ cho thấy partial grants | UNKNOWN coverage, không khẳng định full review |
| T15 | Một principal dùng chung bởi ba ứng dụng | Review từng dependency trước split/revoke |
| T16 | Reviewer không có authority với target tenant | Reject decision |
| T17 | Reviewer chính là actor bị cấm tự duyệt | SoD guard chặn |
| T18 | Reviewer timeout | Reminder/escalation, không auto-approve |
| T19 | Service decommission rồi event retry cấp lại key | Current-state guard ngăn regrant |
| T20 | Target báo timeout khi revoke | Readback trước khi retry |
| T21 | Principal đã retired nhưng session JWT còn ALLOW | Không close, xử lý token/session |
| T22 | Person Leaver org-a nhưng còn employment org-b | Thu hồi đúng quan hệ và tenant |
| T23 | Account có tên giống nhau ở hai SaaS | Không merge sai identity |
| T24 | Mover đổi service owner nhưng chưa đổi vault ACL | Phát hiện quyền người cũ tồn dư |
| T25 | Workload federation migration đã xong, static key vẫn dùng | Flag incomplete migration |
| T26 | Log ghi không có lần dùng nhưng telemetry thiếu endpoint | UNKNOWN, không kết luận unused |
| T27 | Emergency NHI có quyền admin thường trực ngoài hạn | Review/contain/revoke theo policy |
| T28 | Revoke một shared principal làm job khác lỗi | Có dependency/cutover trước khi đóng |
| T29 | Role catalog thay mapping quyền khi campaign chờ | Revalidate snapshot/approval |
| T30 | Access readback không thể thực hiện | Mark UNVERIFIED và theo dõi owner/SLA |

**Unit test policy cần đi cùng integration tests** tại IAM, vault, cloud, CI/CD, Kubernetes, SaaS và resource server. Các test gây revoke/rotate phải dùng tài nguyên thử được phép hoặc kế hoạch triển khai đã được phê duyệt, không vô tình làm gián đoạn production.

## 47. Tình huống thực hành: review bot đồng bộ hóa đơn

**Bối cảnh:** Doanh nghiệp có service **billing-sync** chạy production mỗi đêm để đồng bộ hóa đơn từ ERP sang reporting API của **org-a**. Ba năm trước, đội dự án tạo một service principal và API key tĩnh. Owner ban đầu đã chuyển công tác; hệ thống vẫn chạy ổn định.

### 47.1. Inventory và phát hiện

Chiến dịch review thu thập:

| Thành phần | Trạng thái quan sát |
| --- | --- |
| Service catalog | billing-sync ACTIVE, owner là team đã giải thể |
| Deployment | Job chạy hàng đêm, có output thật |
| Cloud role | BillingReader + OrgIAMAdmin |
| SaaS API key | Static, không thấy expiresAt, nằm trong vault |
| CI/CD pipeline | Có deployment role và trusted branch chưa giới hạn đủ |
| API telemetry | READ billing hằng đêm; không ghi nhận quản trị IAM trong 90 ngày |
| Resource owner | Finance Data Owner có thể xác nhận business purpose |
| IdP | Người tạo service principal đã Mover/Leaver khỏi vai trò cũ |

**Chưa thể kết luận service không còn cần**: telemetry cho thấy tác vụ vẫn chạy. Nhưng **OrgIAMAdmin, static key, branch trust rộng và owner thiếu hiệu lực** là các finding quan trọng.

### 47.2. Reviewer và quyết định

Finance Data Owner xác nhận service cần **READ billing org-a** và ghi trạng thái xử lý đã được phê duyệt, không cần quản trị IAM. Platform owner xác nhận cách triển khai và các dependency. Security xác nhận kế hoạch:

1. **TRANSFER_OWNER** sang finance-platform, có backup owner SRE.
2. **REDUCE** cloud role từ OrgIAMAdmin xuống phạm vi ứng dụng tối thiểu.
3. **MIGRATE** static API key sang federation/credential ngắn hạn nếu target hỗ trợ; nếu không, lập kế hoạch rotation và ngoại lệ có hạn.
4. **RESTRICT TRUST** theo repository/branch/environment của pipeline thực tế.
5. **REVIEW vault ACL** và rút quyền nhân viên cũ.
6. **TEST** job thật bằng phương án canary/cutover, ghi rollback plan.

### 47.3. Thực thi có kiểm soát

Đội kỹ thuật bổ sung principal/credential thay thế, kiểm thử job trên dữ liệu được phép, cập nhật deployment, thu hẹp role và vô hiệu key cũ sau khi xác minh. Nếu có SLA cao, phải có **rollback window có hạn** và theo dõi log; không để hai principal đặc quyền tồn tại lâu dài.

### 47.4. Xác minh

~~~text
New workload READ billing org-a -> ALLOW
New workload WRITE approved status -> ALLOW nếu nghiệp vụ cần
New workload MANAGE_ACCESS org-a -> DENY
New workload READ billing org-b -> DENY
Old static API key call -> DENY sau cutover
Old owner IAM/vault permission -> DENY
Unapproved CI/CD source assume prod role -> DENY
~~~

Nếu key cũ **không thể xác minh trạng thái revoke** ở SaaS, item giữ **REMEDIATION_UNVERIFIED** với owner và deadline, không gắn VERIFIED_CLOSED chỉ vì pipeline mới hoạt động.

### 47.5. Tình huống phát sinh

Giả sử job thất bại khi thu hẹp role vì ứng dụng cũ có thao tác **LIST_ALL_TENANTS** dù chỉ xử lý org-a. Không nên cấp lại OrgIAMAdmin mà không điều tra. Cần sửa ứng dụng/target policy hoặc thiết kế quyền hẹp tương đương có owner duyệt. Nếu phải giữ ngoại lệ tạm thời để duy trì dịch vụ, cần **risk owner, compensating controls và expiresAt**.

## 48. Câu hỏi tự kiểm tra

**Câu 1: Non-human account không có login tương tác thì có cần recertification không?**

**Trả lời:** Có. Nó vẫn sở hữu quyền, credential, trust và khả năng truy cập dữ liệu; thậm chí có thể rủi ro cao vì chạy tự động và lâu dài.

**Câu 2: Owner đã Leaver thì nên xóa service principal production ngay không?**

**Trả lời:** Không mặc định. Phải xử lý quyền cá nhân, chuyển owner, rà soát secret và nhu cầu thực sự; chỉ decommission nếu không còn căn cứ hoặc theo containment khi rủi ro đòi hỏi.

**Câu 3: Một API key đã rotate thì quyền OrgIAMAdmin có tự mất không?**

**Trả lời:** Không. Credential rotation và entitlement reduction là hai hoạt động khác nhau.

**Câu 4: Không có log dùng account trong 90 ngày có đủ chứng minh account thừa?**

**Trả lời:** Không. Phải xem log coverage, chu kỳ batch/DR, business purpose, owner và các dependencies.

**Câu 5: Workload federation có nghĩa service không cần review secret/credential nữa?**

**Trả lời:** Không. Phải review issuer, subject/audience trust, role, token TTL, quyền sửa pipeline và những key legacy còn tồn tại.

**Câu 6: SCIM User active=false có đủ vô hiệu mọi token của bot không?**

**Trả lời:** Không. Các SaaS/local API key, refresh grant, access token và cloud principal có cơ chế riêng, cần kiểm chứng ở target.

**Câu 7: Vì sao phải kiểm tra chính resource server sau REVOKE?**

**Trả lời:** Để xác định authorization thực sự Deny và không còn đường role, token, cache, direct ACL hoặc impersonation đang tiếp tục Allow.

**Câu 8: Một service principal có role ReadOnly nhưng đọc được secret admin; có phù hợp least privilege không?**

**Trả lời:** Có khả năng không. Quyền đọc secret có thể tạo đường leo thang, cần đánh giá **effective capabilities** chứ không tin tên role.

## 49. Checklist cho Review non-human account

| Câu hỏi | Bằng chứng hoặc kiểm soát |
| --- | --- |
| Đã xác định đúng principal và issuer/tenant? | Stable ID, account type, namespace |
| Có serviceId, business purpose và owner? | Service catalog, owner + backup |
| Owner hiện còn thẩm quyền? | Team registry, HRIS/sponsor và authorization |
| Có phân biệt account/credential/workload? | Principal–service–secret mapping rõ |
| Đã kiểm kê đủ target? | Cloud, IdP, vault, PKI, SaaS, DB, CI/CD, Kubernetes |
| Snapshot và coverage có timestamp? | Source version, extractedAt, confidence |
| Có expected/assigned/effective/used rights? | Entitlement model, target readback, telemetry |
| Có kiểm tra đường quyền gián tiếp? | Trust, role chaining, secret read, impersonation |
| Role có theo least privilege? | Scope tenant/resource/action/environment |
| Có hard deny hoặc SoD conflict? | Risk review, approver độc lập |
| Credential có bảo vệ và hạn? | Vault, key/cert metadata, rotation, revocation |
| Có secret copy ngoài vault? | Discovery và controlled investigation |
| Có cân nhắc managed/federated identity? | Issuer/subject/audience binding và credential plan |
| OAuth client scopes có đúng API? | Audience, scope, client policy, object authorization |
| Workload trust có ràng buộc repo/namespace? | Federation/assume-role rules |
| Có kiểm tra local ACL/API key ngoài IdP? | SaaS/target-specific readback |
| Last used có coverage đủ? | Observation window, log source và UNKNOWN handling |
| Có review định kỳ và theo sự kiện? | Risk cadence, owner Mover/Leaver, decommission |
| Có phân biệt KEEP/REDUCE/ROTATE/REVOKE? | Decision và remediation semantics |
| Có impact plan cho account quan trọng? | Dependencies, canary, rollback/cutover |
| Có owner mới chấp nhận trách nhiệm? | Transfer acceptance, secret/vault access reviewed |
| Có hạn cho ngoại lệ? | Risk owner, controls, expiresAt, follow-up |
| Có quản lý reviewer timeout? | Reminder/escalation, không auto KEEP |
| Có ngăn event cũ tái cấp quyền? | State/version, idempotency, lifecycle guard |
| Có target readback và negative test? | Role/trust/credential revoked, API Deny |
| Có kiểm tra token/session tồn dư? | Issuer/resource server strategy, TTL, revoke |
| Có audit và phân quyền đọc log? | Correlation, owner, decision, verification evidence |
| Có trạng thái UNKNOWN/UNVERIFIED? | Missing evidence không bị coi PASS |
| Có KPI phản ánh giảm quyền thừa? | Overprivilege, orphaned, static keys, revoke latency |

## 50. Tổng kết

**Review non-human account** là quá trình tái xác nhận **mục đích, chủ sở hữu, quyền, trust relationship, credential và trạng thái vòng đời** của những tài khoản/danh tính được dùng bởi service, automation, bot, workload, CI/CD và tích hợp máy–máy. Khác với tài khoản con người, NHI có thể tiếp tục phục vụ nghiệp vụ sau khi người tạo hoặc owner cũ **Mover/Leaver**, nhưng mọi quyền và bí mật từng gắn với người đó vẫn phải được rà soát và xử lý.

Trong mô hình **Joiner–Mover–Leaver**, **HRIS/sponsor** xác minh con người và quan hệ làm việc của owner; **service catalog/CMDB** xác định workload và người chịu trách nhiệm; **IAM/IGA** quản lý approval, role, review và expected access; **IdP/SSO/OIDC/OAuth** hỗ trợ nhận diện, token và federation theo contract; **vault/PKI/cloud IAM** quản lý credential và trust; **SCIM** hỗ trợ User/Group nơi được triển khai; còn **RBAC/ABAC/PBAC và resource server/PEP** thực thi quyền ở tài nguyên thực.

Một quy trình hiệu quả cần **inventory đa nguồn, owner có trách nhiệm, quyền và credential tối thiểu, review theo rủi ro, quan sát đủ nguồn, quyết định độc lập, giảm quyền/rotate/decommission có kiểm soát, và readback/negative tests để xác minh quyền thực sự bị chặn**. **Không kết thúc review tại checkbox Keep hoặc nút Revoke**, cũng không coi credential ngắn hạn hay federation là miễn kiểm soát. Mục tiêu cuối cùng là duy trì workload hợp lệ trong khi giảm **orphaned accounts, đặc quyền thừa, bí mật tồn dư và đường truy cập không còn căn cứ**.

# Batch account trong IAM: định danh và kiểm soát quyền của tác vụ chạy theo lô

**Batch account** là danh tính phi con người được sử dụng để **thực thi hoặc truy cập tài nguyên thay mặt một công việc chạy theo lô (batch job)**, thường không cần người đăng nhập tương tác. Những công việc này có thể chạy theo lịch, theo sự kiện, do người vận hành kích hoạt có kiểm soát hoặc do một workflow điều phối. Ví dụ: tổng hợp báo cáo cuối ngày, đồng bộ dữ liệu, đối soát thanh toán, nhập file, chạy ETL, tính phí định kỳ, sao lưu hoặc dọn bản ghi hết hạn.

Bài **“Batch account”** thuộc chương **Non-human account** của module **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**. Module tập trung quản lý vòng đời danh tính theo **Joiner–Mover–Leaver (JML)**, từ xác minh, tạo tài khoản, cấp quyền đến rà soát/thu hồi khi thay đổi vai trò. Đối với batch account, JML tương ứng với **onboard job – thay đổi lịch, dữ liệu, người quản lý hoặc môi trường – ngừng job/decommission**. Bên cạnh đó, JML của **con người sở hữu job** cũng phải kích hoạt chuyển giao trách nhiệm, thu hồi quyền điều khiển và tránh quyền truy cập tồn dư. Bài liên hệ **IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, kiểm toán** và phương pháp chứng minh quyền đã thực sự được thu hồi.

**Tình huống dẫn nhập:** Một job tên **daily-invoice-export** chạy lúc 02:00 để đưa thống kê từ Finance API vào hệ thống báo cáo. Người viết ban đầu dùng tài khoản admin cá nhân, cất mật khẩu trong script. Sau khi người này chuyển sang bộ phận khác, job vẫn chạy bằng credential cũ và có quyền đọc toàn bộ dữ liệu khách hàng. Công việc chỉ cần đọc báo cáo tổng hợp của một tenant trong 20 phút mỗi ngày. Thiết kế đúng phải có **principal batch riêng**, owner hiện hành, quyền đọc hẹp, credential được bảo vệ/luân chuyển, giám sát thất bại, và phương án revoke khi công việc không còn cần thiết.

## 1. Bản chất của batch account

Batch account trả lời câu hỏi **“tác vụ không có người dùng trực tiếp đang chạy dưới danh tính nào và được làm những gì?”**. Không nhất thiết hệ thống nào cũng tạo một đối tượng mang tên chính xác là “BatchAccount”; danh tính có thể là:

- **Tài khoản hệ điều hành** dùng cho cron, systemd timer, Windows Task Scheduler hoặc batch runner.
- **Service account/workload identity** gắn với pod, container, job runner hay dịch vụ serverless.
- **Service principal/OAuth confidential client** để batch process xin access token và gọi API.
- **Tài khoản database** dành riêng cho ETL/đối soát, có schema/table privileges hạn chế.
- **Tài khoản kỹ thuật của ứng dụng/SaaS** dành cho import/export hoặc scheduler tích hợp.
- **Identity riêng của pipeline** được kích hoạt ở một stage, tenant, project hay môi trường.

Điểm chung là **mục đích và quyền được quản trị theo job/workload**, không dựa vào một người dùng tương tác tại thời điểm chạy.

### Vì sao batch account cần quản trị riêng?

| Đặc điểm | Hệ quả bảo mật |
| --- | --- |
| Chạy tự động ban đêm/cuối kỳ. | Có thể phát sinh truy cập nhạy cảm khi không có người quan sát trực tiếp. |
| Chạy trong nhiều phút/giờ và có retry. | Token/credential có thể hết hạn giữa chừng; lệnh ghi có thể được thực hiện lặp. |
| Đọc/ghi lượng dữ liệu lớn. | Blast radius cao dù chỉ có một principal. |
| Phụ thuộc scheduler và deployment. | Người sửa lịch, image, command hoặc input có thể thay đổi hành vi job. |
| Không có human MFA mỗi lượt chạy. | Cần workload authentication, trust và kiểm soát runtime phù hợp. |
| Có owner là con người/đội nhóm. | Owner Mover/Leaver có thể khiến principal bị bỏ quên. |
| Job có thể ngừng chạy nhưng vẫn có quyền. | Tạo orphaned credentials và quyền tồn dư lâu dài. |

**Batch account không phải ngoại lệ mặc định được dùng chung mật khẩu**, cũng không phải giấy phép bỏ audit vì job chạy tự động.

## 2. Phân biệt batch account với các loại danh tính khác

| Khái niệm | Đối tượng chính | Quan hệ với batch |
| --- | --- | --- |
| **Human identity** | Nhân viên, nhà thầu. | Có thể là owner hoặc người kích hoạt job, không nên mặc định là runtime principal. |
| **Service account** | Tài khoản phi con người của một dịch vụ. | Batch account có thể dùng service account, nhưng không phải mọi service account đều chạy batch. |
| **Application identity** | Danh tính đại diện ứng dụng khi truy cập API. | Batch job thường dùng application identity để gọi downstream service. |
| **Workload identity** | Danh tính gắn với workload/runtime. | Nên dùng khi nền tảng hỗ trợ để giảm static secrets. |
| **Scheduler identity** | Danh tính điều phối lịch, trigger hoặc job definition. | Có thể khác identity mà task dùng khi chạy. |
| **Runtime/execution principal** | Subject mà process/pod thực sự chạy dưới quyền. | Cần phân quyền OS, volume, network, cloud/API tương ứng. |
| **Target/data-source credential** | Danh tính được DB/API/SaaS chấp nhận. | Có thể riêng với runtime identity; cần bảo vệ và thu hồi độc lập. |
| **Interactive admin identity** | Người vận hành/phê duyệt thay đổi. | Không dùng làm credential dài hạn trong script job. |

**Một batch job có thể đi qua nhiều danh tính.** Ví dụ scheduler dùng tài khoản điều phối để tạo Kubernetes Job; pod chạy dưới một ServiceAccount; workload federation đổi một assertion thành cloud credential; Finance API nhận token của service principal. Việc khóa tài khoản scheduler **không nhất thiết** lập tức thu hồi mọi token mà pod đã nhận.

## 3. Ba lớp danh tính bắt buộc phải phân biệt

~~~mermaid
flowchart TD
    O["Owner / Operator<br/>Human identity + approval"] --> SCH["Scheduler / Orchestrator<br/>Identity điều phối"]
    SCH --> JOB["Batch execution runtime<br/>OS account / Kubernetes ServiceAccount"]
    JOB --> ISS["Managed identity / OAuth AS / STS<br/>Trao credential hoặc access token"]
    ISS --> API["Downstream API / Database / SaaS<br/>Identity được target chấp nhận"]
    API --> PEP["PEP: action, resource, tenant, thời gian"]
    SCH --> AUD["Audit / Monitoring"]
    JOB --> AUD
    PEP --> AUD
~~~

### Lớp 1 — Control-plane/scheduler

Ai được phép **tạo, sửa, xóa lịch, thay command, đổi image, inject environment variables hoặc kích hoạt job**? Đây là một quyền quản trị có thể gián tiếp dẫn tới đặc quyền cao, dù danh tính điều phối không trực tiếp đọc Finance API.

### Lớp 2 — Runtime/execution

Batch process thực thi dưới account nào? Account đó có đọc được file, secret, socket hoặc volume của job khác không? Có thể chạy với quyền root, mount host, truy cập API cluster, sử dụng network egress tùy ý hay không?

### Lớp 3 — Downstream/application/resource

Khi gọi API hoặc database, job xuất trình **token hoặc credential của principal nào**? Audience, scope, DB role, tenant và resource-level policies có đúng công việc hay không? Dù runtime được cô lập, target credential quá quyền vẫn gây nguy cơ.

**Một thiết kế an toàn cần đánh giá từng lớp và các đường leo thang giữa chúng**, thay vì chỉ nhìn tên tài khoản chạy cron.

## 4. Những kiểu batch job và mức độ rủi ro

| Job | Nhu cầu điển hình | Điểm rủi ro |
| --- | --- | --- |
| **Read-only reporting** | Đọc dữ liệu tổng hợp, tạo báo cáo. | Có thể xuất lượng lớn PII, cross-tenant hoặc lưu file công khai. |
| **ETL/import** | Đọc nguồn, chuyển đổi, ghi đích. | Data poisoning, ghi sai schema, quyền trên hai hệ thống. |
| **Billing/payment settlement** | Tính phí, chốt giao dịch. | Tác động tài chính, SoD, chạy lặp và hậu quả không đảo ngược. |
| **Backfill/migration** | Sửa/đọc dữ liệu lịch sử. | Quyền rộng tạm thời, cần change window và TTL. |
| **Cleanup/retention** | Xóa dữ liệu theo chính sách. | Xóa nhầm, vượt chính sách lưu trữ, khó khôi phục. |
| **Backup/restore** | Sao lưu hoặc khôi phục dữ liệu. | Truy cập toàn bộ dữ liệu; cần bảo vệ encryption keys và restore quyền cao. |
| **CI/CD automation** | Build, release, deploy. | Có thể sửa code/config để chiếm production identity. |
| **External SaaS sync** | Đồng bộ qua API. | Token tồn dư khi hợp đồng/integration ngừng. |
| **Security scan/audit export** | Đọc policy, logs, findings. | Quyền nhạy cảm và dữ liệu vận hành; không cần quyền sửa/xóa. |

Vì vậy **không xếp mọi batch account là risk LOW** chỉ vì không có người thao tác. Phân loại dựa trên **action, dữ liệu, blast radius, thời gian, cơ chế xác thực, runtime và khả năng thu hồi**.

## 5. Thiết kế danh tính theo từng job và môi trường

Mỗi batch workflow cần có **stable job ID**, owner và principal được xác định theo ranh giới trách nhiệm. Ví dụ:

~~~text
Business function: finance-daily-report
  ├─ dev:     batch-finance-report-dev
  │           read test reports only
  ├─ staging: batch-finance-report-stg
  │           read staging tenant, synthetic data
  └─ prod:    batch-finance-report-prod
              read reports tenant-vn, no export/admin
~~~

### Khi nào nên tách principal?

- **Hai jobs có owner hoặc nhiệm vụ khác nhau**, để thu hồi job A không làm hỏng job B.
- **Hai môi trường có mức tin cậy khác nhau**: dev/staging không nên dùng credential production.
- **Một job chỉ đọc và một job ghi/xóa**: có thể cần phân tách duty và blast radius.
- **Hai tenant/khách hàng có yêu cầu cách ly**.
- **Job có dữ liệu hạn chế/đặc quyền khác hẳn** với jobs dùng chung runner.
- **Những đợt migration tạm thời** nên có principal và TTL riêng, không cộng quyền vào account thường trực.

Một tổ chức có thể chọn chia sẻ principal cho vài jobs cùng vòng đời và quyền giống nhau, nhưng phải **chứng minh ranh giới trách nhiệm, phân quyền, audit attribution và khả năng thu hồi riêng**. “Ít tài khoản hơn” không phải KPI bảo mật tự thân.

## 6. Inventory tối thiểu của một batch account

| Trường | Tác dụng |
| --- | --- |
| jobId / jobName / version | Định danh tác vụ, code/image hoặc cấu hình được thực thi. |
| applicationId / serviceId | Liên kết job với ứng dụng và hệ thống nghiệp vụ. |
| ownerTeam / sponsor / contact | Phân công người duyệt, xử lý sự cố và decommission. |
| scheduler / trigger type | Cron, event, manual approval, workflow orchestrator. |
| schedule / timezone / change window | Khi nào chạy, có giới hạn thời gian/khối lượng không. |
| runtimePrincipal / executionEnvironment | OS account, ServiceAccount, pod, VM, serverless function. |
| targetPrincipal / credentialRefs | Account/token/DB role được downstream chấp nhận. |
| authenticationMethod | Managed identity, federation, mTLS, private_key_jwt, secret hoặc API key. |
| targetResources / tenant / environment | API, DB, bucket, namespace, tenant được phép. |
| approvedActions / entitlementRefs | Chỉ read/write/export/delete cần thiết; version policy. |
| effectiveFrom / expiresAt | Vòng đời quyền đặc biệt, ngày bắt đầu/ngừng job. |
| dataClassification / retention | Nhạy cảm dữ liệu đầu vào/đầu ra, bảo vệ log và file kết quả. |
| credentialRotation / revocation | Chủ sở hữu, hạn, xử lý key cũ và token đã cấp. |
| lastSuccessfulRun / observedUse | Hỗ trợ vận hành và access review, đi kèm độ tin cậy telemetry. |
| dependency / rollback / runbook | Đảm bảo ngừng/cắt quyền không phá job khác. |
| audit / targetVerification | Evidence cho grant, allow/deny, revoke, decommission. |

Inventory phải theo **stable IDs của principal**, không ghép chỉ bằng email, hostname hoặc tên cron có thể thay đổi. Không lưu nguyên **password, token, private key hoặc connection string có secret** trong catalog.

## 7. Threat model cho batch account

### Những điểm tấn công và lỗi cấu hình

1. **Hard-coded password** trong shell script, properties, image hoặc repository.
2. **Shared admin account** cho nhiều jobs không liên quan.
3. **Cron/scheduler control-plane bị sửa**, thực thi command ngoài phạm vi được duyệt.
4. **World-readable log/environment/file** chứa credential hoặc dữ liệu export.
5. **Stale secret/key** vẫn dùng được sau rotation hoặc Leaver của owner.
6. **Quyền DB/API wildcard** thay vì chỉ đọc/ghi resource cần.
7. **Cross-environment/tenant trust**: staging assume identity production.
8. **Replay/retry** gây ghi trùng hoặc lặp thanh toán.
9. **Job đã bị xóa nhưng credential/grant vẫn tồn tại**, tạo orphaned access.
10. **Job runner/root quyền rộng**, có thể đọc secret của workloads khác.
11. **Policy chặn ở UI nhưng async worker bỏ qua PEP**, xử lý dữ liệu trái quyền.
12. **Tài khoản “không dùng” bị bỏ quên** vì không có owner hoặc thiếu log.

### Security outcomes cần kiểm

Mỗi rủi ro cần một **positive test** xác nhận công việc hợp lệ vẫn chạy, và **negative test** xác nhận tác vụ ngoài phạm vi bị từ chối. Với job ghi dữ liệu, cần kiểm **không có side effects** khi policy DENY; với job chạy lại, cần kiểm **idempotency** thay vì chỉ dựa vào lịch.

## 8. Xác thực batch account: ưu tiên workload identity thay vì mật khẩu dùng chung

Một job không có người ngồi trước máy để nhập MFA tại mỗi lượt chạy. Điều đó **không có nghĩa miễn xác thực**, mà đòi hỏi một cơ chế **xác thực workload không tương tác**.

| Cơ chế | Phù hợp khi | Điểm cần kiểm |
| --- | --- | --- |
| **Managed identity** | Job chạy trên platform cung cấp identity/token cho runtime. | Quyền truy cập metadata/token endpoint, principal binding và role scope. |
| **Workload identity federation** | Kubernetes/CI/CD xuất assertion có nguồn tin cậy để exchange lấy credential ngắn hạn. | Issuer–subject–audience–environment trust chặt, không wildcard toàn repo/cluster. |
| **mTLS / client certificate** | API hoặc service mesh hỗ trợ xác thực peer bằng chứng thư. | Private key custody, certificate expiry, identity mapping và endpoint authorization. |
| **private_key_jwt** | Confidential OAuth client có key được bảo vệ và AS hỗ trợ. | Assertion validation, key rotation và không lộ private key. |
| **Client secret** | Nền tảng chưa hỗ trợ phương pháp khác. | Vault, scopes, TTL/rotation, hạn chế đọc secret và log. |
| **Database-specific credential** | Legacy DB không hỗ trợ IAM/federation. | DB role tối thiểu, TLS, secret storage, giới hạn network, rotate. |
| **Windows gMSA** | Windows/domain environment hỗ trợ Group Managed Service Account. | Máy được phép dùng gMSA, quyền logon as batch/service và ACL. |
| **Local OS service account** | Cron/systemd hoặc process runner thực thi dưới UID riêng. | Filesystem permissions, quyền sudo, isolation và credentials gọi hệ thống ngoài. |

**Credentialless theo nghĩa không phải tự lưu secret dài hạn không đồng nghĩa không có token hoặc khóa.** Runtime/issuer vẫn trao credential ngắn hạn; nếu quyền truy cập token endpoint hoặc trust sai, attacker có thể giả danh batch job.

### Khi phải dùng secret tĩnh

Secret cần được đặt trong kho bảo mật có quyền đọc hạn chế, được inject qua kênh phù hợp của platform và **không hiện trong command line, stdout/stderr, crash dumps, stack traces, CI logs hoặc git history**. Với một số nền tảng, biến môi trường có thể bị lộ qua process inspection, debug snapshots hoặc instrumentation; không mặc nhiên coi environment variable là vault.

## 9. Least privilege cho batch job: quyền theo chức năng, không theo lịch

Một batch account có thể chỉ chạy 5 phút mỗi ngày nhưng quyền của nó có thể **tồn tại 24 giờ/ngày**. Phải tách:

- **Quyền tĩnh/standing**: entitlement tồn tại liên tục, bất kể job có đang chạy.
- **Quyền kích hoạt tạm (JIT/eligible)**: có hiệu lực trong cửa sổ xác định và có quy trình thu hồi.
- **Token/credential lifetime**: thời hạn xác thực, không nhất thiết bằng thời hạn role.
- **Job runtime**: thời gian process thực tế hoạt động.
- **Authorization per request**: quyết định tại API/DB theo action, resource, tenant, trạng thái.

~~~text
Job schedule:          02:00 mỗi ngày
Expected run:          02:00–02:20
Approved capability:   finance.summary.read, tenant VN
Production admin:      không cần
Access design:         token ngắn hạn + app role hẹp
Optional JIT window:   chỉ nếu target/IAM hỗ trợ và đã kiểm revoke
~~~

**Không gán TTL một giờ trên ticket rồi coi đã hạn chế quyền** nếu ứng dụng đích vẫn giữ role vĩnh viễn hoặc JWT cũ còn dùng được nhiều giờ.

### Quyền cần đánh giá

| Lớp | Quyền ví dụ | Kiểm soát |
| --- | --- | --- |
| Scheduler | Chỉ tạo job từ định nghĩa được duyệt. | Chặn thay command/image và tự kích hoạt quyền mạnh. |
| Runtime | Đọc file cấu hình, ghi thư mục output riêng. | Không root nếu không cần, hạn chế host access. |
| Vault | Chỉ đọc secret của chính job. | Hạn chế secret paths, không đọc toàn vault. |
| Database | SELECT view báo cáo; INSERT bảng staging. | Không DROP/GRANT, không truy cập bảng khách hàng không liên quan. |
| API | reports.read trong một tenant. | Token audience/scope và ABAC tại Resource Server. |
| Storage | Ghi bucket/prefix kết quả. | Không read/delete toàn bộ bucket hoặc cross-tenant. |
| Network | Kết nối endpoint cần thiết. | Egress restrictions; không thay thế identity authorization. |
| Observability | Ghi logs/metrics của job. | Không có quyền sửa/xóa audit logs tùy tiện. |

### Quyền truy cập dữ liệu đầu ra

Một job chỉ có quyền **read** ở nguồn vẫn có thể làm lộ dữ liệu khi **ghi ra một bucket hoặc thư mục công khai**. Vì vậy threat model phải theo **đường dữ liệu đầu–cuối**, gồm classification, encryption, storage ACL, retention, forwarding và người có thể download báo cáo.

## 10. Linux cron: sử dụng tài khoản thực thi riêng

Một lựa chọn trên Linux truyền thống là tạo **system account không cho đăng nhập tương tác** và chạy job bằng user đó thông qua scheduler được quản trị.

**Ví dụ cấu hình khái niệm**:

~~~text
Job name: finance-report-export
OS identity: batch-finance
Interactive login: disabled by account/login policy
Working directory: /var/lib/finance-report
Command: /opt/finance-report/bin/run-report
Schedule: 02:00 mỗi ngày theo timezone được quản lý
Allowed output: /var/lib/finance-report/output
Secrets: referenced through approved secret manager, not crontab
~~~

Nếu dùng crontab, cấu hình lịch không nên chứa password/token trong argument, dòng lệnh hoặc environment hard-coded. Một ví dụ cú pháp trong file cron hệ thống:

~~~cron
# /etc/cron.d/finance-report — ví dụ cú pháp, không phải lệnh triển khai
# min hour day-of-month month day-of-week user command
0 2 * * * batch-finance /opt/finance-report/bin/run-report
~~~

### Những điều phải bảo vệ

1. **Người có quyền sửa file cron/script** có thể thay hành vi batch job, nên phải được review như một đường leo thang.
2. Binary/script và directory không được **writable bởi user ngoài owner được duyệt**.
3. Tài khoản batch không cần shell tương tác hoặc sudo thông thường; chính sách **nologin/lock** phải phù hợp cơ chế job runner của hệ điều hành.
4. Output files có permissions và retention riêng; không đặt file chứa PII ở thư mục công khai.
5. Cron có ngữ cảnh môi trường tối giản: dùng đường dẫn rõ, PATH kiểm soát và cấu hình timezone.
6. Job không nên đọc mọi secret của host chỉ vì nó chạy trên cùng server.
7. Phải có **exit-code monitoring, timeout, lock/concurrency và alert** khi không chạy hoặc chạy thất bại.

**Lưu ý về “nologin”:** shell nologin có thể chặn phiên đăng nhập, nhưng khả năng scheduler thực thi process dưới account đó phụ thuộc setup. Cần kiểm với nền tảng thực; không nhầm “không đăng nhập” với “account đã bị disable hoàn toàn”.

## 11. systemd timer/service: ranh giới account và sandbox

Trên Linux dùng systemd, có thể tách **timer** (lịch chạy) và **service** (cách thực thi), qua đó cấu hình identity và sandbox ở service unit.

~~~ini
# finance-report.service — minh họa, cần kiểm lại theo bản systemd thực tế
[Unit]
Description=Generate the daily finance summary

[Service]
Type=oneshot
User=batch-finance
Group=batch-finance
ExecStart=/opt/finance-report/bin/run-report
WorkingDirectory=/var/lib/finance-report
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/finance-report/output
TimeoutStartSec=30min
~~~

~~~ini
# finance-report.timer — minh họa
[Unit]
Description=Run the daily finance summary

[Timer]
OnCalendar=*-*-* 02:00:00
Persistent=true
Unit=finance-report.service

[Install]
WantedBy=timers.target
~~~

**Không coi đây là bản production-ready**. Cần kiểm quyền đọc executable/config, directory ownership, writable paths cần thiết, timezone, backfill behavior của Persistent=true, platform hardening và secret injection. Persistent=true có thể chạy bù khi máy từng tắt; nếu job không idempotent, chạy bù có thể gây hậu quả không mong đợi.

### systemd DynamicUser?

DynamicUser=true có thể cấp UID động giúp giảm nhu cầu account đứng lâu, nhưng một số workload cần persistent data, stable file ownership hoặc xác thực hệ thống khác; cần thiết kế StateDirectory/CacheDirectory và ràng buộc chính xác. **Không gợi ý bật DynamicUser cùng User cố định mà không hiểu mục tiêu triển khai**; chọn một mô hình identity phù hợp với lifecycle và quyền cần thiết.

## 12. Windows Task Scheduler và Group Managed Service Account

Trên Windows, job có thể chạy bằng **Task Scheduler**, account miền riêng hoặc **Group Managed Service Account (gMSA)** khi domain/platform hỗ trợ. Mục tiêu là tránh lưu mật khẩu một tài khoản nhân viên hoặc dùng Domain Admin.

### Những lớp kiểm soát

| Kiểm soát | Câu hỏi |
| --- | --- |
| **Task ownership** | Ai được sửa XML/task action, trigger, credential, run level? |
| **Execution identity** | Task dùng account nào, có quyền ở resource nào? |
| **Log on as a batch job** | Identity có đúng quyền logon phục vụ task và không rộng hơn? |
| **Managed credential** | gMSA có được domain quản lý, host được phép sử dụng không? |
| **Run with highest privileges** | Có thực sự cần elevated token không? |
| **Resource ACL** | Folder, share, SQL server, secrets có quyền chỉ theo nhiệm vụ không? |
| **Remote API authentication** | Dùng Kerberos/cert/OAuth đúng trust boundary, không tự mở mọi dịch vụ. |
| **Task history/monitoring** | Phát hiện task không chạy, fail, chạy nhiều lần hoặc bị sửa. |

**gMSA không tự cấp quyền vào database hoặc API**. Đây là mô hình credential/account được Windows/AD hỗ trợ; ứng dụng đích vẫn cần grant và kiểm authorization riêng.

Khi host bị loại khỏi phạm vi chạy job, cần kiểm **host eligibility, task definition, principal usage và credential/access được thu hồi**. Không để một server cũ vẫn có thể dùng gMSA để truy cập production ngoài mục đích.

## 13. Kubernetes CronJob và ServiceAccount chuyên biệt

Trong Kubernetes, **CronJob** là tài nguyên tạo Job/Pod theo lịch. Một mẫu có thể gán serviceAccountName riêng cho pod, tách identity khỏi người tạo CronJob.

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: finance-report-batch
  namespace: finance-prod
automountServiceAccountToken: false
---
apiVersion: batch/v1
kind: CronJob
metadata:
  name: finance-daily-report
  namespace: finance-prod
spec:
  schedule: "0 2 * * *"
  timeZone: "Asia/Ho_Chi_Minh"
  concurrencyPolicy: Forbid
  startingDeadlineSeconds: 900
  successfulJobsHistoryLimit: 2
  failedJobsHistoryLimit: 2
  jobTemplate:
    spec:
      backoffLimit: 2
      activeDeadlineSeconds: 1800
      template:
        spec:
          serviceAccountName: finance-report-batch
          automountServiceAccountToken: false
          restartPolicy: Never
          containers:
            - name: finance-report
              image: registry.example.internal/finance-report:1.0.0
              command: ["/app/run-report"]
              resources:
                requests:
                  cpu: "100m"
                  memory: "128Mi"
                limits:
                  cpu: "500m"
                  memory: "512Mi"
~~~

Đây là **manifest minh họa, không phải template đầy đủ để triển khai production**. timeZone yêu cầu phiên bản/năng lực Kubernetes tương ứng. Cần bổ sung image integrity/provenance, securityContext, network policy, deployment governance, data storage, telemetry và các cơ chế lấy workload token phù hợp.

### Phân biệt các cấu hình dễ nhầm

- **ServiceAccount** định danh pod trong Kubernetes; không tự được quyền Finance API.
- **Kubernetes RBAC** cấp quyền với Kubernetes API, không thay quyền OAuth/DB của ứng dụng.
- automountServiceAccountToken=false giảm mount token mặc định, nhưng nếu dùng workload federation cần **projected token riêng** có audience/TTL và trust phù hợp.
- concurrencyPolicy=Forbid hạn chế overlap **các Jobs thuộc cùng CronJob** theo cơ chế scheduler; không bảo đảm chống duplicate khi có trigger khác, rescheduling hoặc external system.
- backoffLimit tạo retry ở mức Job/Pod: **job code vẫn cần idempotency**.
- startingDeadlineSeconds có thể làm mất lần chạy quá hạn, cần monitoring và xử lý missing business runs.
- Khi CronJob được xóa, **ServiceAccount, cloud grants, tokens và application credentials** không nhất thiết bị xóa theo.

### Projected token khi cần federation

Một workload có thể mount ServiceAccount token dự kiến trao với STS/Authorization Server:

~~~yaml
# Đoạn bổ sung trong pod spec, mang tính minh họa.
volumes:
  - name: workload-token
    projected:
      sources:
        - serviceAccountToken:
            path: token
            expirationSeconds: 3600
            audience: finance-workload-exchange
~~~

Token này phải có **issuer, subject, audience, expiry** đúng trust contract. Không gửi token Kubernetes cho API ngoài như một bearer token tùy tiện; thường phải qua **token exchange/federation** nếu target yêu cầu credential khác.

## 14. Batch account truy cập database: tách DB role khỏi account điều phối

Một ETL job có thể dùng runtime principal trên máy chạy batch và một **database principal khác** để kết nối DB. Quyền DB nên dựa trên **view/schema/tables/procedures** cần thiết, không dùng tài khoản DBA chỉ để đọc dữ liệu.

### Ví dụ phân quyền dạng PostgreSQL minh họa

Giả sử job chỉ cần SELECT trên một view báo cáo đã được owner phê duyệt:

~~~sql
-- Minh họa cho PostgreSQL, không chạy nguyên trạng trong production.
-- Việc tạo role/login và cấp quyền phải đi qua change control.
CREATE ROLE batch_report_reader LOGIN;

GRANT CONNECT ON DATABASE finance_reporting TO batch_report_reader;
GRANT USAGE ON SCHEMA reporting TO batch_report_reader;
GRANT SELECT ON TABLE reporting.daily_finance_summary
    TO batch_report_reader;

-- Không cấp các vai trò quản trị như SUPERUSER, CREATEROLE,
-- CREATEDB, và không GRANT SELECT trên mọi schema theo thói quen.
~~~

**Các điều kiện cần kiểm trước triển khai:**

- View/tables và schema tồn tại, quyền USAGE/SELECT không bị thừa hưởng ngoài dự kiến.
- Principal có phương pháp xác thực DB phù hợp; CREATE ROLE ở ví dụ chưa xác lập password hay TLS configuration.
- Policy default privileges hoặc role membership không cấp quyền bổ sung.
- Role không thể tự GRANT cho principal khác hoặc đọc bảng PII ngoài nhiệm vụ.
- Network/TLS và DB host credentials không bị công khai qua command line.
- Khi job không còn dùng, gỡ membership/grants/credential và kiểm session/connection pool còn hiệu lực theo DB semantics.

**Gỡ GRANT không nhất thiết chấm dứt mọi transaction hoặc session đang chạy ngay lập tức.** Cần hiểu cách DB áp privilege checks, connection/session lifetime, transaction isolation và policy thu hồi của hệ quản trị cụ thể.

### Chú ý với ETL có quyền ghi

Nếu job phải INSERT vào staging table, nên dùng quyền ghi tại staging **thay vì quyền UPDATE/DELETE toàn hệ thống**, ràng buộc dữ liệu nguồn, validate schema, giới hạn batch size và sử dụng idempotency để tránh ghi trùng.

## 15. Batch account gọi API bằng OAuth client credentials

Khi một job không hành động thay người dùng đang đăng nhập, **OAuth client credentials** có thể là cơ chế app-only phù hợp nếu Authorization Server hỗ trợ và confidential client được xác thực.

~~~mermaid
sequenceDiagram
    participant J as Batch job
    participant AS as Authorization Server
    participant R as Report API / RS
    participant POL as Policy + Resource State
    J->>AS: Authenticate workload + request app token
    AS-->>J: Short-lived access token for report-api
    J->>R: GET /daily-summary + access token
    R->>R: Verify issuer, token, audience, expiry
    R->>POL: Can this batch principal read this tenant/report?
    POL-->>R: ALLOW / DENY
    R-->>J: Authorized result only
~~~

### API phải kiểm gì?

1. Issuer được tin cậy; JWT signature/key/algorithm và timestamps hợp lệ hoặc introspection chính xác.
2. Access token **dành cho Resource Server này**, không dùng token từ CRM cho Finance API.
3. Loại principal/application grant phù hợp luồng app-only theo contract của provider.
4. Scope hoặc app role chỉ cho **report.read**, không tự mở read-all/export/admin.
5. Tenant/resource/classification thuộc phạm vi được duyệt, lấy từ backend.
6. Token còn hiệu lực và khi cần phải kiểm trạng thái grant/account hiện hành.
7. Các đường API bổ sung như **async export, pagination, bulk download** cũng có PEP.

**OIDC ID token không thay access token để gọi API**; client_id thường là ID công khai, không phải credential. Không hard-code token dài hạn trong cron, job manifest hoặc image.

### App-only không phải delegated access

Nếu batch job được kích hoạt bởi một người để xử lý tài nguyên của chính người đó, hệ thống cần quyết định **job chạy dưới quyền ứng dụng** hay dưới quyền **được ủy nhiệm của người dùng**. Với app-only rộng, API hoặc service trung gian phải kiểm **người tạo request có quyền với resource cụ thể** trước khi thực thi; nếu không có thể phát sinh **confused deputy**.

## 16. Batch account và RBAC/ABAC: quyền theo workload, tenant và thời điểm

Một policy minh họa:

~~~yaml
ruleId: finance-daily-batch-read
subjectType: WORKLOAD
subject:
  workloadId: finance-report-prod
  environment: production
  ownerTeam: finance-platform
action: reports.summary.read
resource:
  tenantId: tenant-vn
  classificationAtMost: INTERNAL
context:
  tokenAudience: finance-report-api
  runtimeBindingVerified: true
  lifecycleStatus: ACTIVE
effect: PERMIT_IF_ALL_MATCH
default: DENY
~~~

Đây là **YAML mô tả chính sách khái niệm**, không phải cú pháp của một IdP/OPA/cloud vendor cụ thể. Các thuộc tính **workloadId, environment, tenant và classification** cần đến từ nguồn đáng tin hoặc được xác minh. Không tin header workload-name hoặc tenantId do client tự khai.

### Cửa sổ thời gian không đủ làm authorization

Quy tắc chỉ cho chạy lúc 02:00–02:30 có thể hỗ trợ giảm exposure, nhưng:

- Đồng hồ/timezone, daylight saving, lịch chạy bù hoặc retry cần được xử lý.
- Time-based gate không thay thế xác thực workload hoặc resource-level authorization.
- Job có thể chạy vượt cửa sổ do dataset lớn hoặc outage; cần thiết kế expiry/continuation.
- Quyền cần được đo ở **target**, không chỉ “scheduler dừng”.

Khi dùng **time-bound access**, nên ràng buộc với **approved job execution/lease** hoặc policy rõ ràng, có cơ chế xử lý completion/retry và revoke fail-safe.

## 17. SoD cho batch processing và các tác vụ nhạy cảm

Một job có thể gây rủi ro tương tự con người nếu nó được phép thực hiện **cả khởi tạo và phê duyệt** một giao dịch.

| Hành động A | Hành động B | Xung đột ví dụ |
| --- | --- | --- |
| Tạo payment | Phê duyệt chính payment đó | Không còn maker–checker độc lập. |
| Thay bank beneficiary | Duyệt settlement sau sửa | Có thể chuyển tiền sai người nhận. |
| Build artifact | Tự approve release production | Bỏ qua independent change control. |
| Tạo app principal | Tự grant admin cho principal đó | Tự nâng đặc quyền. |
| Sửa audit policy | Xóa dấu vết hoạt động | Khả năng che giấu lạm dụng. |
| Import record | Tự xác nhận đối soát kết quả | Che lỗi dữ liệu nếu không có kiểm soát độc lập. |

### Hai tài khoản batch chưa chắc tách nhiệm vụ

Nếu một operator hoặc pipeline có thể **điều khiển cả batch-creator và batch-approver**, tách hai username chỉ có giá trị hình thức. Cần kiểm **effective controller, IAM role assume, secret-read, repository write, deployment approval** và người có thể thay đổi logic của hai jobs.

### Quy tắc SoD tại giao dịch

Một ứng dụng thanh toán cần kiểm actor/provenance ở backend:

~~~text
DENY payment.approve IF
    creatorPrincipal == currentApproverPrincipal
 OR originatingHuman == currentHumanApprover
 OR conflict in material-change history
 OR action violates approved workflow/tenant/risk policy
~~~

Các điều kiện là **mô hình minh họa**; rule chính thức phải do process owner định nghĩa. Với automation có delegated user context, cần ghi cả **technical actor** và **business initiator** để không đánh đồng hai service principals với hai người kiểm soát độc lập.

## 18. Access request và phê duyệt batch account

Quyền của batch job phải được quản lý như access request có chủ đích, không phải DBA/DevOps tạo account rồi cấp quyền theo nhu cầu phát sinh.

### Trường đề xuất

| Trường | Ví dụ | Quyết định liên quan |
| --- | --- | --- |
| Requester/sponsor | Team Finance Platform. | Ai chịu trách nhiệm nghiệp vụ? |
| Beneficiary | workload finance-report-prod. | Identity nào được cấp? |
| Job/source | daily-finance-report v2, repo/deployment ref. | Code nào được phép sử dụng identity? |
| Schedule | 02:00 hằng ngày, tối đa 30 phút. | Khi nào cần chạy? |
| Target | Finance API production. | Môi trường và tài nguyên nào? |
| Entitlement | reports.summary.read, tenant VN. | Quyền tối thiểu nào? |
| Auth method | Workload federation. | Có trust/secret lifecycle phù hợp? |
| Expiry/review | Dự án còn hoạt động, review định kỳ. | Khi nào cần chứng nhận lại? |
| SoD/risk tier | Data exposure, export, privilege paths. | Ai phải approve? |
| Revocation capability | Disable grant/trust, target probe. | Có thể chặn quyền khi đóng job không? |

### Tuyến phê duyệt

**Business owner** xác nhận nhu cầu; **API/data owner** kiểm action/resource/tenant; **platform/IAM owner** cấp principal/trust; **security/SoD reviewer** đánh giá quyền cao/ngoại lệ theo risk. Quyền production admin hoặc xóa dữ liệu có thể yêu cầu tuyến độc lập cao hơn. **Không cho người sửa job definition tự phê duyệt mọi đặc quyền đích** nếu policy cần tách duty.

### Những quyết định có thể xảy ra

- **APPROVE** đúng scope và ownership.
- **REDUCE_SCOPE**: dùng view tổng hợp thay SELECT toàn DB.
- **TIME_BOUND/JIT**: quyền migration chỉ trong change window nếu target hỗ trợ thực thi.
- **REQUIRE_REVIEW**: target sensitive hoặc thiếu owner/trust.
- **DENY**: account dùng chung admin, cross-tenant không duyệt, SoD non-waivable.
- **INVESTIGATE**: không xác định được principal đang dùng hay cách revoke.

Approved snapshot cần gắn với **subject, target, entitlement version, tenant, TTL và job definition/version**; nếu sau duyệt script được đổi để export dữ liệu gốc thay báo cáo tổng hợp, phải xem lại risk.

## 19. Joiner của batch account: onboarding có kiểm soát

Một quy trình có thể theo:

1. **Đăng ký job**: business purpose, owner, source code, schedule, target và thời hạn.
2. **Xác minh workload provenance**: ai tạo/deploy job, repository/namespace/runner có được duyệt không.
3. **Chọn runtime principal** riêng và giới hạn quyền sửa scheduler/definition.
4. **Chọn target authentication**: managed/federated identity nếu khả thi, hoặc secret được quản lý an toàn.
5. **Thiết kế entitlement** theo action, tenant, schema, prefix, môi trường và data classification.
6. **Phân tích SoD và privilege escalation**: job có thể tự approve, grantRole, export hoặc đọc secrets ngoài scope không.
7. **Phê duyệt có thẩm quyền** và đóng băng snapshot quyền.
8. **Provision chính xác** account/role/trust, không cấp wildcard tạm “để test”.
9. **Xác minh ở target**: đọc lại grants và token/DB permissions thực tế.
10. **Positive/negative probes**: công việc hợp lệ ALLOW, truy cập tenant khác/admin/export DENY.
11. **Thiết lập vận hành**: retries, idempotency, alert, file output, retention, DLQ nếu có.
12. **Đưa vào inventory và access review**: owner, TTL, next review, rotation, decommission.

### Joiner không cần cấp role người dùng tương tác

Một batch account thường nên bị hạn chế **interactive login** hoặc không hỗ trợ user login tùy platform. Không dựa vào cấm login như một biện pháp đủ, vì job có thể vẫn được dùng để lấy API token và quyền đó phải được bảo vệ riêng.

## 20. Mover: job đổi lịch, quyền, tenant, runner hoặc owner

Mover của batch có thể xảy ra khi:

- Lịch chạy từ hằng ngày sang theo sự kiện, thời lượng xử lý tăng.
- Job chuyển từ **read-only** sang **write/export/delete**.
- Chuyển staging lên production, thêm tenant hoặc nguồn dữ liệu mới.
- Di chuyển runner từ VM sang Kubernetes/cloud.
- Đổi repository, branch, service account hoặc federation issuer/subject.
- Chuyển owner từ đội A sang đội B.
- Thay client secret bằng managed identity hoặc mTLS.

### Quy trình thay đổi

~~~mermaid
flowchart TD
    A["Change request / Mover event"] --> B["Inventory current identity, grants, trust, owner"]
    B --> C["Compute desired permissions and revoked permissions"]
    C --> D["Risk/SoD approval + change/version freeze"]
    D --> E["Prepare new identity or narrowly scoped grant"]
    E --> F["Verify new job ALLOW only authorized actions"]
    F --> G["Revoke old grants, secrets and trust bindings"]
    G --> H["Readback old target + DENY probes"]
    H --> I{"All required paths verified?"}
    I -->|Có| J["Update owner/catalog/audit"]
    I -->|Không| K["Remediation + containment"]
~~~

**Tránh grant mới chồng vô hạn lên quyền cũ.** Với một số công việc, có thể cần overlap để chuyển đổi không gián đoạn, nhưng phải có hạn, scope và thử thu hồi; với hệ thống nhạy cảm, SoD có thể yêu cầu **revoke-before-grant**.

### Owner Mover hoặc Leaver không đồng nghĩa job Leaver

Job còn nhiệm vụ hợp lệ phải được **bàn giao ownership**, kiểm người cũ còn quyền sửa scheduler, repository, secret và cloud trust không. Cân nhắc rotate credentials nếu owner cũ từng có khả năng đọc/copy. Không tự xóa job đang phục vụ khách hàng chỉ vì nhân viên owner nghỉ.

## 21. Leaver: dừng batch job và thu hồi danh tính

Khi batch job thực sự ngừng được phê duyệt, cần **decommission toàn diện**, không chỉ xóa dòng crontab.

### Danh sách cần xử lý

1. **Xác nhận dependencies và dữ liệu cần lưu**: consumer, output, schedule, legal retention.
2. **Dừng schedule/trigger và in-flight runs** theo phương án an toàn; không bỏ dở transaction ngoài kiểm soát.
3. **Thu hồi runtime principal**, host/namespace eligibility và quyền sửa definition không còn cần.
4. **Revoke target DB roles, OAuth app grants, API keys/PATs và cloud IAM bindings**.
5. **Gỡ workload federation trust/managed identity association** tương ứng.
6. **Revoke/rotate client secrets, certificates, service tokens** và credential mà job từng dùng.
7. **Dọn direct ACL, scheduler-local accounts, queues/jobs, alternate credentials** còn tồn.
8. **Đánh giá token/DB connections còn hiệu lực** dù grant hoặc secret đã bị gỡ.
9. **Test tại PEP/DB** rằng action bị thu hồi DENY, trong khi các jobs hợp lệ khác vẫn ALLOW.
10. **Lưu bằng chứng audit**, trạng thái partial failures và owner remediation; không log secrets.

### Thực thi đúng thứ tự

Nếu task là job thanh toán, phải đảm bảo **không hủy giữa lúc đã ghi một phần nghiệp vụ**, có idempotency/reconciliation và quy trình rollback/hậu xử lý. Trong sự cố lộ credential, ưu tiên **containment** theo incident policy có thể mạnh hơn yêu cầu không gián đoạn.

### Quyền tồn dư sau khi xóa CronJob

Một CronJob bị delete không có nghĩa OAuth client bị xóa, cloud role bị gỡ hoặc JWT đã phát không còn hiệu lực. Leaver hoàn tất khi **required targets** đã được readback, token/trust behavior được kiểm theo kiến trúc và **effective access bị chặn trong SLA**.

## 22. Quản lý credential: rotation, caching và secret exposure

Một batch account có thể có **nhiều credential đang hợp lệ** trong lúc migration; việc thêm credential mới không tự thu hồi credential cũ. Phải quản lý cả **issuer/grant** và **token đang được target chấp nhận**.

### Quy trình rotation thường kỳ

~~~mermaid
sequenceDiagram
    participant O as Credential Owner
    participant V as Vault / IdP / STS
    participant J as Batch Runtime
    participant T as Target API / DB
    O->>V: Tạo credential/trust mới
    O->>J: Cập nhật runtime theo kênh an toàn
    J->>V: Xác thực bằng credential mới
    V-->>J: Token/session mới hoặc kết quả auth hợp lệ
    J->>T: Positive test + negative out-of-scope test
    T-->>J: ALLOW phù hợp / DENY ngoài scope
    O->>V: Revoke old credential/trust
    O->>T: Probe old credential/token theo khả năng target
    T-->>O: Verified outcome / residual exposure
~~~

**Lưu ý:** không dùng secret production thật làm fixture. Cần phân biệt **client credential bị revoke** với **access token đã được phát trước đó**: JWT tự chứa có thể còn được chấp nhận đến expiry nếu Resource Server không kiểm trạng thái thu hồi bổ sung.

### Khi credential nghi bị lộ

Không duy trì overlap để đạt “zero downtime” bằng mọi giá. Playbook phải xác định:

- Principal, target grants, audiences, tenants và các job consumers bị ảnh hưởng.
- Khả năng chặn ở Authorization Server, Resource Server, DB và network.
- Những access tokens/sessions được cấp trước thời điểm lộ có thể còn sống.
- Incident owner và phương án phục hồi qua identity/quyền mới hẹp hơn.
- Bằng chứng API/DB từ chối credential cũ theo thời hạn chấp nhận.

**Không ghi giá trị credential vào audit/ticket khi điều tra**; dùng credential ID, token ID/correlation an toàn, timestamps và protected evidence references.

## 23. Retry, idempotency và concurrency: tính đúng đắn là một phần bảo mật

Batch thường chịu các lỗi:

- Scheduler kích hoạt hai lần.
- Pod/job thất bại sau khi đã ghi DB nhưng trước khi xác nhận thành công.
- API trả timeout nhưng downstream đã commit.
- Message queue phân phối lại một event.
- Job được chạy bù sau downtime hoặc daylight-saving adjustment.
- Một phiên bản mới chạy cùng lúc với phiên bản cũ.

Nếu job dùng quyền **ghi, chi tiền, xóa hoặc export**, việc chạy lặp có thể gây hại ngay cả khi identity/authorization hợp lệ.

### Thiết kế tối thiểu

| Biện pháp | Mục đích | Giới hạn |
| --- | --- | --- |
| **Business idempotency key** | Cùng business period/operation chỉ tạo hiệu quả đúng một lần theo contract. | Key sai phạm vi có thể bỏ sót hoặc chặn nhầm công việc. |
| **Unique constraint / upsert** | Tránh bản ghi trùng ở DB. | Không tự ngăn side effects ở hệ thống ngoài. |
| **Transaction/outbox** | Liên kết DB commit với event phát ra. | Cần consumer idempotent và retries đúng. |
| **Distributed lock/lease** | Hạn chế chạy song song một batch scope. | Lease expiry/clock drift cần thiết kế; lock không thay idempotency. |
| **Concurrency policy** | Kiểm soát overlap theo scheduler. | Không bao phủ manual trigger, runner khác hoặc job orphan. |
| **Deadline/timeout** | Tránh process treo và giữ credential ngoài dự kiến. | Hủy giữa transaction cần recovery. |
| **Reconciliation run** | Phát hiện missing/duplicate output sau retry. | Không dùng làm lý do bỏ authorization controls. |

### Ví dụ idempotency key

~~~text
jobId        = finance-daily-report
businessDate = 2026-11-23
tenant       = tenant-vn
operation    = generate-summary

idempotencyKey = stableHash(jobId, businessDate, tenant, operation)
~~~

Giá trị phải đủ ổn định để retry cùng công việc không gây ghi trùng, nhưng phân biệt được khi thực sự chạy một công việc mới có chủ đích. Đừng lấy ngẫu nhiên một key mới trên mỗi retry nếu mục tiêu là khử trùng business operation.

### Không đồng nhất exactly-once scheduling với exactly-once effect

Ngay cả khi một scheduler thường chỉ tạo một job theo lịch, **runtime có thể được retry, network có thể timeout và external systems có thể commit trước khi acknowledgement tới**. Tính đúng đắn phải được bảo đảm bằng **business transaction semantics, idempotency/reconciliation** và kiểm thử lỗi.

## 24. Rủi ro dữ liệu: input, output, logs, staging và retention

Một batch account cần được phân quyền theo **dòng dữ liệu**, không chỉ quyền đọc tại nguồn.

~~~mermaid
flowchart LR
    IN["Data source<br/>Tenant / Classification"] --> B["Batch process<br/>Validation + transforms"]
    B --> ST["Staging / Temp files"]
    B --> OUT["Output bucket / DB / API"]
    B --> LOG["Metrics + Logs"]
    IN --> P["Data Owner Policy"]
    P --> B
    P --> OUT
    P --> ST
~~~

### Kiểm soát từ đầu tới cuối

1. **Input authorization:** job không đọc dữ liệu ngoài tenant, thời gian hoặc classification được duyệt.
2. **Data validation:** không tin input file hoặc event tùy tiện, nhất là khi batch có quyền ghi production.
3. **Staging permissions:** file trung gian không world-readable; dọn sau khi xử lý theo retention.
4. **Encryption:** TLS khi truyền và cơ chế bảo vệ dữ liệu lưu theo data policy.
5. **Output ACL:** chỉ nhóm/ứng dụng được phép nhận báo cáo; tránh public bucket/share link.
6. **Logging:** tránh đẩy PII/secrets vào error stack traces, CSV debug và monitoring.
7. **Deletion authority:** một job cleanup phải kiểm retention hold/legal requirements, không xóa rộng chỉ vì có SQL DELETE.
8. **Downstream access:** nếu job chuyển data sang BI/SaaS, cần kiểm tenant/data processing policy của bên nhận.

**Quyền read-only tại nguồn không đồng nghĩa rủi ro thấp** nếu job có khả năng export hàng triệu bản ghi hoặc ghi chúng vào vùng lưu trữ kém bảo vệ.

## 25. Monitoring một batch account: “không chạy” cũng là sự kiện

IAM thường chỉ quan tâm khi một principal **sử dụng quyền**. Batch job còn cần quan sát **lịch chạy mong đợi**, vì job không chạy có thể làm bỏ sót công việc tài chính/tuân thủ và khiến owner bỏ quên account.

| Tín hiệu | Câu hỏi |
| --- | --- |
| Scheduled/expected run | Job có được kích hoạt đúng lịch và timezone không? |
| Started/completed/failed | Có đủ một lần chạy hợp lệ hay có retry bất thường? |
| Duration/timeout | Job chạy lâu bất thường hoặc treo giữ credential không? |
| Execution principal ID | Có đổi account/runtime ngoài approved deployment không? |
| Token issuance | Có xin token ngoài giờ, từ host/issuer lạ hoặc scope khác? |
| Resource access | Có API/DB actions ngoài business need, tenant hoặc dataset? |
| Output integrity | Báo cáo/record có đủ, không trùng/thiếu hoặc sai classification không? |
| Credential use | Có dùng key cũ sau rotation hoặc dùng secret trong môi trường khác không? |
| Owner review | Ai xử lý alerts, ai đang ACTIVE và biết runbook không? |
| Decommission drift | Job đã nghỉ nhưng credential vẫn được dùng không? |

### Sự khác nhau giữa “không được dùng” và “không thấy dùng”

Nếu không có log cho API key legacy, **không quan sát thấy usage** không đủ kết luận credential dormant. Với job chạy theo năm, cửa sổ 90 ngày cũng chưa đủ đại diện. Review cần ghi **cửa sổ đo, nguồn telemetry, coverage và nhiệm vụ định kỳ**.

### Sự kiện audit tối thiểu

~~~yaml
eventType: BATCH_EXECUTION_AUTHORIZATION
jobRef: finance-daily-report
runRef: run-20261123-0200
runtimePrincipalRef: batch-finance-prod
targetPrincipalRef: finance-api-client-report
action: reports.summary.read
targetRef: finance-api
tenantRef: tenant-vn
policyVersion: report-batch-v3
decision: ALLOW
observedAt: "2026-11-22T19:00:00Z"
credentialRef: workload-trust-17
tokenValueLogged: false
~~~

Đây là ví dụ **schema mô tả, không phải định dạng audit tiêu chuẩn**. Việc ghi cả runtime/target identity giúp tách quyền **người điều phối, job và API principal**, đồng thời hỗ trợ điều tra khi một credential được dùng ngoài scheduler.

## 26. Readback, effective access và kiểm chứng thu hồi

**Điều kiện kết thúc một nhiệm vụ revoke không phải chỉ là đã gửi lệnh disable/delete.**

### Ba lớp bằng chứng

| Lớp | Ví dụ evidence | Giới hạn |
| --- | --- | --- |
| **Control-plane command** | Ticket được duyệt; IdP/SCIM/API trả success. | Mới cho biết request áp thay đổi được tiếp nhận/xử lý. |
| **Target readback** | Principal/grant/role/trust/key không còn trong config. | Cache, token, session hoặc đường khác vẫn có thể ALLOW. |
| **Effective authorization proof** | API/DB từ chối action trái policy trong scope, không side effects. | Cần test trên đường PEP đủ coverage và đúng target. |

**Kết luận VERIFIED cần bằng chứng phù hợp cho các target bắt buộc**. Nếu target legacy không hỗ trợ readback, phải ghi UNVERIFIED và giải pháp bù trừ, không mặc định không còn quyền.

### Kịch bản thu hồi điển hình

~~~text
16:00  Decommission approved, desired access = none.
16:01  Scheduler disabled.
16:03  OAuth app grant removed.
16:04  Federation trust disabled.
16:05  Target configuration readback confirms grant removed.
16:10  Legacy PAT still allows export via old endpoint.
16:12  PAT revoked.
16:14  Probe old endpoint returns policy DENY, no output created.
~~~

Nếu deadline policy là 16:10, nhiệm vụ có thể đã **vi phạm SLA**, dù cuối cùng verified lúc 16:14. Lấy timestamp 16:03 để báo revoked hoàn tất là không chính xác.

### Kiểm đúng DENY

Một HTTP 503 do API down hoặc timeout không chứng minh authorization deny. Cần **positive control** chứng minh API còn hoạt động và một **negative test** trên cùng logic authorization, kiểm không tạo file, update hoặc queue message ngoài quyền.

## 27. Java pseudocode: batch job lấy token, xử lý theo scope và idempotency

Mô hình dưới thể hiện **client side** của một job dùng workload credential provider. Đây là **pseudocode**, không phải SDK có thể chạy ngay.

~~~java
import java.time.LocalDate;

record ApprovedJobContext(
    String jobId,
    String tenantId,
    LocalDate businessDate,
    String expectedAudience
) {}

interface TrustedWorkloadCredentialProvider {
    String getAccessToken(String targetAudience, String approvedScope);
}

interface ReportApi {
    ReportData getSummary(
        String accessToken,
        String tenantId,
        LocalDate businessDate
    );
}

final class DailyReportBatch {
    private final TrustedWorkloadCredentialProvider credentials;
    private final ReportApi api;
    private final RunDeduplicationLedger ledger;
    private final ReportOutput output;

    void execute(ApprovedJobContext context) {
        // Context phải được tạo từ job definition được duyệt, không
        // chấp nhận arbitrary tenantId hay target do input không tin cậy.
        String key = context.jobId() + ":"
            + context.tenantId() + ":" + context.businessDate();

        if (!ledger.tryStartAtomically(key)) {
            return; // Chạy trùng; xử lý retry theo ledger contract.
        }

        try {
            String token = credentials.getAccessToken(
                context.expectedAudience(), "reports.summary.read");
            ReportData report = api.getSummary(
                token, context.tenantId(), context.businessDate());

            output.publishAtomically(key, report);
            ledger.markCompleted(key);
        } catch (Exception error) {
            ledger.markRetryableFailure(key);
            // Ghi lỗi có kiểm soát; không log token hoặc dữ liệu nhạy cảm.
            throw error;
        }
    }
}
~~~

### Điều cần bổ sung trong hiện thực thật

- **Ledger** phải lưu trạng thái bền vững, có concurrency control và phân biệt failure sau khi output đã commit.
- **publishAtomically** cần contract idempotent với storage/API; không đồng nghĩa mọi external operation có transaction chung.
- **Credential provider** phải dùng SDK/identity platform đáng tin, không tự parse assertion và bỏ kiểm signature.
- **Token expiry** cần được xử lý trong trường hợp job dài; không cache vô hạn trong singleton.
- **Tenant/resource authorization** thuộc trách nhiệm cả client policy và API/DB target; client validation không thay PEP.
- **Exception handling** phải chống retry vô hạn và tránh log secret/PII.

**Đây là cấu trúc minh họa về các lớp trách nhiệm**, không khẳng định exactly-once side effect trong hệ phân tán chỉ nhờ phương thức ledger trên.

## 28. Java pseudocode: target API kiểm batch principal

Resource Server cần kiểm **token ở tầng framework trước**, sau đó quyết định dựa trên app principal, action, tenant và resource đã được xác minh.

~~~java
import java.util.Set;

record VerifiedAppPrincipal(
    String principalId,
    String tokenAudience,
    Set<String> grantedScopes,
    boolean trustedToken,
    boolean active
) {}

record ReportResource(String tenantId, String classification) {}

final class ReportAuthorization {
    boolean canReadSummary(
        VerifiedAppPrincipal app,
        ReportResource resource) {

        if (app == null || resource == null) {
            return false;
        }

        return app.trustedToken()
            && app.active()
            && "finance-report-prod".equals(app.principalId())
            && "finance-report-api".equals(app.tokenAudience())
            && app.grantedScopes() != null
            && app.grantedScopes().contains("reports.summary.read")
            && "tenant-vn".equals(resource.tenantId())
            && "INTERNAL".equals(resource.classification());
    }
}
~~~

**VerifiedAppPrincipal chỉ được khởi tạo sau khi middleware đã kiểm issuer, signature/key hoặc introspection, expiry, audience và token type**; không tạo từ HTTP header do client tùy ý gửi. Phạm vi resource của hàm là **minh họa**, policy thật phải xét classification levels, purpose, entitlement version và rules của ứng dụng.

## 29. Hồ sơ quản trị và các trạng thái vòng đời

Một bản ghi quản lý batch account có thể được mô tả bằng dữ liệu sau:

~~~yaml
batchIdentityId: batch-finance-report-prod
job:
  id: daily-finance-summary
  applicationId: finance-reporting
  businessPurpose: Tao bao cao tong hop tai chinh noi bo
  schedule:
    expression: "0 2 * * *"
    timeZone: Asia/Ho_Chi_Minh
    maxExpectedRuntimeMinutes: 30
  ownerTeam: finance-platform
  businessOwnerRef: finance-data-owner
  versionRef: finance-report-v3
runtime:
  environment: production
  orchestrator: kubernetes-cronjob
  namespace: finance-prod
  serviceAccountName: finance-report-batch
targetAccess:
  target: finance-report-api
  workloadPrincipalRef: finance-report-prod
  tenantId: tenant-vn
  approvedActions: [reports.summary.read]
  approvedGrantRef: ar-batch-208
authentication:
  method: WORKLOAD_IDENTITY_FEDERATION
  trustRef: finance-prod-trust-04
  noStaticSecret: true
controls:
  interactiveLoginDisabledWhereApplicable: true
  riskTier: MEDIUM
  runIdempotencyRequired: true
  nextAccessReview: "2027-02-23"
lifecycle:
  state: ACTIVE
  startedAt: "2026-11-23T00:00:00Z"
  decommissionTrigger: application-retirement
verification:
  lastPositiveTestRef: report-allow-741
  lastNegativeTestRef: report-deny-742
~~~

Đây là **schema minh họa**, không phải định dạng chung được chuẩn hóa cho mọi scheduler/IdP. Một số platform không hỗ trợ chính xác những trường cấu hình mô tả. Các trường **noStaticSecret, interactiveLoginDisabledWhereApplicable** chỉ có ý nghĩa nếu được xác minh, không phải bằng chứng tự thân.

### Trạng thái đề xuất

| Trạng thái | Ý nghĩa | Quyền hiệu lực mong đợi |
| --- | --- | --- |
| **REGISTERED** | Nhu cầu và owner đã ghi, chưa cấp grant. | Không có runtime access. |
| **APPROVED** | Trust/permission đã được business và IAM duyệt. | Chưa mặc định active nếu chưa provision. |
| **PROVISIONING** | Connector/scheduler đang tạo runtime/target account. | Chưa được tuyên bố đầy đủ. |
| **ACTIVE_VERIFIED** | Chính sách, trust, grant và API tests đạt. | ALLOW đúng scope, DENY ngoài scope. |
| **SUSPENDED** | Job tạm dừng theo policy/incident. | Truy cập nhạy cảm bị chặn theo SLA tương ứng. |
| **CHANGING** | Mover owner, environment, grant, credential hoặc schedule. | Không có quyền cũ và mới chồng lấn trái policy. |
| **DECOMMISSIONING** | Dừng run và thu hồi các quyền/trust. | Có thể còn token/credential tồn dư, cần theo dõi. |
| **DECOMMISSIONED_VERIFIED** | Các target bắt buộc đã chứng minh không còn quyền. | DENY các action đã thu hồi, trừ ngoại lệ còn được duyệt. |
| **UNVERIFIED/REMEDIATION** | Không thể xác nhận đầy đủ hoặc quyền còn tồn. | Không được báo hoàn tất an toàn. |

Một hệ thống có thể dùng trạng thái khác; nhưng cần **tách quyết định governance, việc thực thi và xác minh**. Job bị xóa trên scheduler không tự động chuyển tất cả quyền vào DECOMMISSIONED_VERIFIED.

## 30. Tình huống thực hành: batch đối soát theo ngày

### Bối cảnh

Một công ty sử dụng **Finance API, PostgreSQL reporting và object storage**. Job **finance-daily-report** chạy 02:00 hằng ngày, tổng hợp hóa đơn ở tenant VN rồi ghi báo cáo CSV nội bộ. Job được chuyển từ một VM dùng cron sang Kubernetes CronJob.

Yêu cầu nghiệp vụ:

- Chỉ đọc **summary dữ liệu đã duyệt** của tenant VN.
- Ghi kết quả vào **storage prefix finance/reports/daily/** có hạn chế download.
- Không có quyền duyệt payment, export thông tin cá nhân chưa được phép hoặc xóa dữ liệu nguồn.
- Một business date chỉ tạo **một báo cáo logic**, kể cả retry.
- Có owner/on-call chịu trách nhiệm và alert nếu mất lần chạy.

### Bước 1 — Kiểm kê rủi ro hiện trạng

| Hiện trạng | Vấn đề | Thay đổi cần làm |
| --- | --- | --- |
| Cron chạy bằng shared admin account. | Nhiều jobs dùng chung credential, không rõ attribution. | Tạo principal runtime/target riêng cho finance-daily-report. |
| Script chứa mật khẩu DB. | Secret có thể xuất hiện trong repo/backup/log. | Chuyển qua workload identity hoặc vault, rotate password đã phơi bày. |
| DB role có SELECT toàn schema và UPDATE dữ liệu nguồn. | Quyền quá rộng. | Chỉ grant view cần đọc; không UPDATE nguồn. |
| Ghi file ra share chung. | Báo cáo có thể bị người không được duyệt tải về. | Bucket/prefix riêng, ACL/encryption/retention đúng classification. |
| Không có run ID/idempotency. | Retry có thể tạo hai báo cáo hoặc cập nhật sai trạng thái. | Stable key theo job+businessDate+tenant. |
| Owner cũ đã chuyển đội. | Không còn người chịu trách nhiệm credential và incident. | Handover ownership, thu hồi quyền repo/vault cũ. |

### Bước 2 — Thiết lập desired-state

~~~text
Job               = finance-daily-report
Runtime           = Kubernetes namespace finance-prod
K8s ServiceAccount= finance-report-batch
Target principal  = finance-report-prod
Auth model        = workload federation (nếu nền tảng hỗ trợ)
Finance API       = reports.summary.read, tenant-vn
PostgreSQL        = SELECT reporting.daily_finance_summary (nếu còn dùng DB)
Output            = write-only appropriate prefix + readback/validation
Schedule          = 02:00 theo timezone đã duyệt
Business key      = tenant + businessDate + report type
Owner             = finance-platform + finance-data-owner
~~~

Thiết kế không tự động cấp quyền Finance API chỉ vì pod đã gắn Kubernetes ServiceAccount; phải có **federation trust và app/API grants** riêng.

### Bước 3 — Cấp, xác minh và bàn giao

1. IAM xác minh owner/job version/runtime mapping rồi duyệt app grants hẹp.
2. Platform tạo ServiceAccount, workload binding và CronJob với cấu hình được review.
3. Finance API chỉ chấp nhận token có issuer/audience/client phù hợp.
4. Data owner kiểm chính sách tenant và classification của nguồn.
5. Storage owner kiểm prefix/quyền tải xuống, tránh public output.
6. Job được chạy bằng dữ liệu thử: báo cáo tenant VN **ALLOW**, tenant SG **DENY**.
7. Kiểm **export/raw PII, approve payment, DB DROP/GRANT** đều bị từ chối.
8. Scheduler thử retry cùng business date: không tạo trùng báo cáo logic.
9. Hệ thống ghi audit principal, run ID, owner và policy version không chứa credential.

### Bước 4 — Mover: đổi chức năng và người sở hữu

Sau một quý, Finance muốn job gửi cả dữ liệu sang BI SaaS. Không chỉ thêm credential BI vào job cũ:

- Kiểm BI service principal có audience/permissions hẹp và tenant đúng.
- Xác định dữ liệu có PII không, consent/data processing policy nào áp dụng.
- Đánh giá tách job **extract/transform** khỏi job **publish** để hạn chế credential exposure.
- Xác minh output/encryption/retention bên BI, không chỉ đọc thành công ở nguồn.
- Đổi owner/team hoặc trust phải thu hồi quyền của owner cũ và grants không còn cần.

Nếu BI import là workload tách biệt, không mặc định nó phải có quyền trực tiếp vào Finance API hoặc PostgreSQL.

### Bước 5 — Leaver: decommission và phát hiện token tồn dư

Sau khi báo cáo bị thay bằng tính năng tích hợp trong Finance Portal, business owner chấp thuận dừng job:

~~~text
08:00  Decommission approval effective.
08:02  CronJob suspended / no new runs expected.
08:05  Finance API grant revoked.
08:07  Federation trust binding disabled.
08:08  K8s ServiceAccount and obsolete config removed after dependency check.
08:10  Target readback reports no active grant.
08:15  Legacy DB credential unexpectedly still authenticates.
08:20  DB credential revoked and session access checked.
08:23  Verified DENY at required API/DB paths.
~~~

**Không kết luận job đã hết quyền lúc 08:02 hoặc 08:05**. Cần tính cả đường legacy DB và việc API/DB thực sự từ chối. Nếu SLA đặt trước 08:20, phải ghi **SLA breach**, dù đã hoàn thành lúc 08:23.

### Kết luận tình huống

Điểm quan trọng không nằm ở việc chọn cron hay Kubernetes, mà ở **ràng buộc danh tính tới job, quyền tối thiểu xuyên các tầng, owner/JML, vận hành đáng tin và verified deprovisioning**.

## 31. Tình huống thứ hai: batch settlement có nguy cơ chạy lặp

### Bối cảnh

Batch job settlement chạy theo sự kiện để tạo các khoản thanh toán cuối ngày. Nó cần quyền **payment.settle**, khác với quyền **payment.approve** của người kiểm soát độc lập. Nếu job được restart sau timeout, một khoản có thể đã chuyển trạng thái nhưng callback thành công bị mất.

**Điều kiện an toàn:**

- Job settlement chỉ xử lý payment đã **APPROVED** và thuộc tenant/hạn mức được duyệt.
- Service principal không có quyền tạo hoặc tự approve payment.
- Transaction operation dùng **stable idempotency key** theo payment ID và operation.
- Backend kiểm trạng thái/hạn mức và version **trong transaction phù hợp**.
- Nếu downstream đã commit mà job không nhận ack, reconciliation phải phát hiện thay vì tạo giao dịch mới.
- Job owner và process owner độc lập theo SoD được duyệt.
- Audit ghi technical actor, originating payment approval và external settlement reference.

### Negative cases phải thử

| Case | Kỳ vọng |
| --- | --- |
| Settlement chưa được approve. | DENY, không có external payment. |
| Job replay cùng settlement key. | Không chuyển tiền hai lần. |
| Token từ staging gọi production settlement. | DENY. |
| Job sửa beneficiary rồi tự settlement. | DENY theo SoD/business policy. |
| AS/STS outage và token không lấy được. | Không fallback sang shared admin secret. |
| API trả timeout sau commit. | Reconcile bằng idempotency key; không tạo payment mới tùy tiện. |
| Credential bị revoke giữa run. | Tuân theo token/state checks và incident SLA; không mở bypass. |

**Authorization đúng vẫn chưa đủ nếu business effect có thể lặp gây mất tiền.** Batch account cần phối hợp kiểm soát IAM với transaction integrity và idempotency.

## 32. Ma trận kiểm thử batch account

Để kiểm tra các yêu cầu bảo mật, nên dùng **test principal, synthetic data, môi trường được ủy quyền** và kiểm cả đường thực thi thực tế. Không trích xuất secret production hoặc thực hiện transaction tài chính thật ngoài phạm vi kiểm thử.

| ID | Tình huống | Kết quả kỳ vọng |
| --- | --- | --- |
| BA01 | Job dùng workload identity được duyệt, gọi reports.summary.read đúng tenant. | ALLOW. |
| BA02 | Chỉ biết client_id, không có secret/trust tương ứng. | AS không cấp token. |
| BA03 | Token mang issuer hoặc signature không đáng tin. | Resource Server từ chối. |
| BA04 | Token dành cho CRM API được dùng ở Finance API. | DENY do audience mismatch. |
| BA05 | Access token hết hạn hoặc not-before chưa tới. | DENY theo verifier. |
| BA06 | Job chỉ có read xin export/delete. | DENY tại endpoint/PEP. |
| BA07 | Job tenant VN xin dữ liệu tenant SG. | DENY resource tenant boundary. |
| BA08 | Pod staging xin assume production role qua workload federation. | Trust policy từ chối. |
| BA09 | Runtime không thuộc approved namespace/repository. | Không được cấp production credential. |
| BA10 | K8s ServiceAccount tồn tại nhưng chưa được grant Finance API. | Không tự được đọc Finance. |
| BA11 | Người dùng có quyền sửa CronJob nhưng không được thay image/command theo policy. | Admission/approval/control-plane guard chặn thay đổi không được duyệt. |
| BA12 | Job được chạy dưới root mặc dù không cần đặc quyền. | Policy/hardening review phát hiện và yêu cầu giảm quyền. |
| BA13 | Cron script file writable bởi user không có authority. | File permission/change review FAIL. |
| BA14 | systemd service có credential lộ trong command line. | Finding bắt buộc remediation/rotation. |
| BA15 | Windows gMSA được một host ngoài allowlist sử dụng. | Host eligibility/access phải chặn. |
| BA16 | DB batch role SELECT view, cố DROP table. | Database DENY. |
| BA17 | DB batch role SELECT report, cố đọc bảng PII không được duyệt. | Database DENY đúng object. |
| BA18 | Job có quyền read nguồn nhưng output bucket public. | Data flow/security review FAIL. |
| BA19 | Token API cho app-only, người dùng yêu cầu truy cập object họ không được phép. | Backend chặn confused deputy. |
| BA20 | Log batch ghi access token/DB password khi exception. | Security regression FAIL, lọc/redact và xử lý lộ secret. |
| BA21 | Credential mới đã hoạt động, credential cũ vẫn xác thực. | Không đóng rotation; tiếp tục revoke/verify. |
| BA22 | Secret cũ đã revoke nhưng access token cũ còn ALLOW trong RS. | Ghi residual exposure và xử lý theo SLA. |
| BA23 | Owner nhân sự Leaver, batch job vẫn có business purpose. | Chuyển owner, thu hồi quyền người cũ, không tự xóa job hợp lệ. |
| BA24 | Job không còn chạy nhưng principal vẫn có cloud admin role. | Access review/decommission finding. |
| BA25 | CronJob đã xóa nhưng local PAT vẫn export được qua SaaS. | REVOKE chưa VERIFIED, xử lý PAT. |
| BA26 | Event Mover cũ đến sau decommission và tạo lại grant. | Current revision/idempotency chặn tái cấp. |
| BA27 | Hai lần chạy cùng business date xảy ra đồng thời. | Idempotency/concurrency guard ngăn double effect. |
| BA28 | DB commit thành công nhưng API trả timeout, scheduler retry. | Reconciliation không ghi trùng nghiệp vụ. |
| BA29 | Job bị chạy bù sau downtime do persistent timer. | Business date/idempotency policy xác định kết quả đúng. |
| BA30 | CronJob concurrencyPolicy Forbid nhưng manual Job cũng chạy. | Bảo vệ ở business layer ngăn duplicate. |
| BA31 | Job vượt active deadline sau khi đã ghi một phần dữ liệu. | Recovery/transaction reconciliation đảm bảo không hỏng dữ liệu. |
| BA32 | Batch có thể create và approve cùng payment. | SoD/transaction control từ chối chuỗi xung đột. |
| BA33 | Hai service accounts khác tên do một người kiểm soát để tự duyệt. | SoD review xét effective controller, không coi khác username là đủ. |
| BA34 | Reviewer tự duyệt grant của principal do chính mình quản lý khi policy cấm. | Approval API từ chối self-approval. |
| BA35 | Target API trả 503 cho negative probe. | Không tính VERIFIED DENY; phân biệt outage. |
| BA36 | Target role đã gỡ qua SCIM nhưng cache/local ACL vẫn ALLOW. | Remediation tiếp tục, không đóng revoke. |
| BA37 | Batch chưa chạy 90 ngày nhưng là annual tax/DR job hợp lệ. | Không auto-delete chỉ vì dormant; owner và runbook được xem. |
| BA38 | API policy cho DENY nhưng async export vẫn tạo file. | FAIL no-side-effect, cần PEP trên worker/async path. |
| BA39 | Scheduler trigger thất bại, không có run record. | Missed-run alert phát hiện, có owner khắc phục. |
| BA40 | Một target legacy không thể readback key/trust. | Hiển thị UNVERIFIED, có biện pháp kiểm soát/risk owner. |

### Test oracle và coverage

**Kỳ vọng PASS/FAIL phải xuất phát từ policy/approval/owner hiện hành**, không lấy chính output của production authorization engine làm chuẩn duy nhất. Mỗi suite cần:

1. Một **positive control** chứng minh endpoint/DB còn hoạt động.
2. Một **negative probe** cho action, tenant và resource ngoài quyền.
3. Kiểm **không có side effects** với job ghi/xóa/xuất dữ liệu khi bị từ chối.
4. Kiểm **principal mapping** qua scheduler, runtime, Authorization Server và target.
5. Kiểm **cả quyền hiện có và quyền sau Mover/Leaver** theo snapshot và mốc thời gian.
6. Kiểm failure/retry/idempotency khi **network timeout, process crash, duplicate trigger**.
7. Ghi **environment, version, effectiveAt, observedAt và evidence reference**, không lưu token.

### Phân loại lỗi chính xác

Một job trả **exit code 0** có thể đã đọc vượt quyền hoặc ghi nhầm tenant; một API trả **403** có thể là authorization deny hoặc bị chặn ở một gateway khác trước khi business PEP; một API trả **503** là outage, không chứng minh chính sách đã DENY. Kiểm thử cần nhìn **outcome bảo mật và hiệu ứng nghiệp vụ**, không chỉ status code.

## 33. KPI và đo lường mức kiểm soát batch accounts

| Chỉ số | Ý nghĩa | Cạm bẫy |
| --- | --- | --- |
| **Owner coverage** | Tỷ lệ batch principals có owner còn hiệu lực và contact. | Owner đã Leaver nhưng catalog chưa cập nhật. |
| **Identity separation coverage** | Tỷ lệ jobs có runtime/target identity đúng ranh giới cần. | Một shared admin principal phục vụ nhiều jobs có thể khó phát hiện. |
| **Standing privileged grants** | Quyền nhạy cảm luôn có hiệu lực ngoài cửa sổ chạy. | Chạy ít phút không có nghĩa entitlement tồn tại ít phút. |
| **Unapproved/wildcard permissions** | App/DB/cloud grants rộng hơn approved need. | So tên role không đủ; cần effective capability. |
| **Credential age/rotation compliance** | Secret/key/cert còn hợp lệ theo policy, rotation đã verify. | Tạo key mới không làm key cũ bị vô hiệu. |
| **Legacy shared-account count** | Accounts dùng chung ở nhiều jobs/owners. | Đừng cắt quyền gây downtime trước khi biết dependencies. |
| **Dormant batch principals** | Không thấy run/API usage trong cửa sổ quan sát. | Annual jobs/thiếu log không tự là excess. |
| **Scheduler drift** | Command/image/trigger khác approved job definition. | Không chỉ kiểm tên job/cron. |
| **Cross-env trust findings** | Staging/dev có thể assume/access production ngoài policy. | Phải xét identity provider và target resource. |
| **JML residual access** | Batch/job/owner Leaver nhưng grants/keys còn hoạt động. | Cần đo tại target và PEP. |
| **Verified deprovision latency** | Từ effectiveAt đến verified DENY ở target bắt buộc. | Không lấy mốc xóa CronJob hoặc HTTP success. |
| **Unverified target coverage** | Những API/DB/SaaS không kiểm được actual access. | Unknown không tương đương 0 risk. |
| **Missed-run/duplicate-run rate** | Lỗi vận hành liên quan schedule và retry. | Không trực tiếp phản ánh identity posture nhưng ảnh hưởng nghiệp vụ. |
| **Unauthorized side-effect count** | Job ngoài quyền vẫn tạo file/update/payment. | Cần phân biệt attempted DENY với completed violation. |

### Ví dụ đo revocation latency

~~~text
decommission effectiveAt = 2026-11-23 08:00:00
last required target verifiedAt = 2026-11-23 08:23:00
revocation latency = 23 phút
~~~

Nếu chỉ hai trong ba target có negative evidence, **chưa có verifiedAt cuối cùng cho toàn scope** và latency không thể được công bố như đã hoàn tất. Theo dõi riêng **verified subset, missing targets, critical grants và chủ sở hữu**.

### Công thức minh họa

\[
\text{Verified Revocation Coverage} =
\frac{\text{Số target bắt buộc đã có bằng chứng DENY}}
{\text{Tổng số target bắt buộc trong scope}}
\times 100\%
\]

Nếu 9/10 target đã được xác minh thì coverage = **90%**, không phải “revoke thành công 100%”. Một target chưa kiểm có thể là đường production admin quan trọng nhất, nên cần xem **risk-weighted coverage** bên cạnh đếm thô.

## 34. Những sai lầm thường gặp khi quản lý batch account

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Dùng nhân viên để login cho job. | Leaver/rotation làm hỏng job và mơ hồ ownership. | Runtime/target service principal riêng. |
| Dùng tài khoản admin chung cho mọi cron. | Blast radius lớn, không biết job nào dùng quyền. | Tách theo risk/task/environment, gỡ grants dư thừa. |
| Chỉ xem cron job name, không xem owner/command. | Job bị thay lệnh/script không được phát hiện. | Approval/version cho definition và quyền sửa control-plane. |
| Coi OS nologin là đã chặn API access. | Token hoặc credential vẫn dùng được. | Kiểm từng identity/credential ở target. |
| Hard-code password trong script hoặc image. | Secret bị nhân bản qua CI/backup. | Vault/workload federation và rotation. |
| Dùng môi trường dev để assume production role. | Dev compromise mở production. | Trust issuer/subject/env chặt và kiểm thử deny. |
| Cho batch account SELECT toàn DB để tiện. | Rò rỉ dữ liệu/khả năng SQL không cần. | View/table/procedure permissions tối thiểu. |
| Coi token được cấp là đã được phép mọi API call. | Không kiểm resource/tenant. | PEP xác thực token và authorization per action. |
| Đặt role có expiry nhưng target không enforce. | Quyền tồn dư ngoài cửa sổ. | Revoke capability, readback và SLA. |
| Xóa scheduler task rồi coi đã decommission. | App grants/secret/API key vẫn còn. | Revoke toàn bộ đường và negative probe. |
| Dùng shared secret xuyên nhiều jobs. | Không thể rotate/revoke riêng, khó attribution. | Principal hoặc credential separation theo scope. |
| Chỉ chú ý read nguồn, bỏ output ACL. | Lộ dữ liệu qua bucket/report. | Data-flow review từ input tới output và logs. |
| Tin concurrencyPolicy là exactly-once. | Duplicate trigger/timeout tạo double write. | Idempotency, ledger, reconciliation và transaction control. |
| Retry bằng key mới mỗi lần. | Tạo giao dịch trùng thay vì khử trùng. | Stable idempotency key theo business operation. |
| Không xử lý credential expiry giữa run. | Job fail hoặc fallback insecure. | SDK refresh/TTL handling có kiểm soát. |
| Owner nhân viên nghỉ thì xóa job ngay. | Gây gián đoạn business hợp lệ. | Chuyển owner, thu hồi quyền cá nhân, đánh giá rotate. |
| Không review batch account vì “không phải người”. | Principal orphaned và quyền admin đứng lâu. | Inventory, owner attestation, access review. |
| Chỉ đọc IdP/SCIM, bỏ API key DB/SaaS. | Quyền local không được quản trị. | Target inventory, reconciliation và revoke proof. |
| Lấy 503 làm bằng chứng DENY. | Outage bị nhầm với security enforcement. | Positive control và policy decision evidence. |
| Lưu token trong audit để dễ debug. | Tạo kho credential mới. | Safe refs/correlation ID, redaction, retention. |
| Chỉ đếm số batch accounts thay cho quyền. | Một account global admin có thể che rủi ro. | Đo quyền hiệu lực và risk-weighted blast radius. |
| Không theo dõi missed runs. | Job bỏ sót nhưng account vẫn tồn tại và có quyền. | Monitoring schedule, health và owner escalation. |

## 35. Checklist triển khai và nghiệm thu batch account

1. **Định danh job rõ:** job ID, business purpose, code/version, owner và lifecycle state.
2. **Tách ba lớp danh tính:** scheduler/control plane, runtime principal, downstream API/DB principal.
3. **Tài khoản phi con người đúng mục đích:** không dùng mật khẩu cá nhân hoặc shared admin làm giải pháp mặc định.
4. **Môi trường và tenant:** dev/staging/prod, test/production data và customer tenants được tách theo rủi ro.
5. **Owner có hiệu lực:** business owner, technical owner, on-call và escalation còn hoạt động.
6. **Change authorization:** chỉ người có thẩm quyền được sửa schedule, command, image, service account và secret refs.
7. **Workload provenance:** issuer/subject/audience/runtime binding được xác minh nếu sử dụng federation.
8. **Credential protection:** vault/KMS/managed credential, không lộ secret trong source, command line, environment snapshots/logs.
9. **Credential rotation:** có owner, expiry, cutover plan, old-key revoke evidence và xử lý incident.
10. **Least privilege:** action/resource/schema/prefix/tenant permissions đúng nhiệm vụ, không wildcard.
11. **DB permissions:** không dùng DBA nếu chỉ SELECT; TLS/connection policy, role membership và views đúng.
12. **Target API authorization:** issuer, signature/keys, audience, token type, time và resource-level policy được kiểm.
13. **Kubernetes/OS isolation:** ServiceAccount/UID riêng, permissions file/volume, runtime hardening, host/network control phù hợp.
14. **Interactive login restrictions:** vô hiệu hóa tương tác khi áp dụng được, không nhầm với chặn mọi execution.
15. **SoD và delegated control:** không tự tạo–duyệt hoặc che audit; xét người điều khiển nhiều technical principals.
16. **Lịch chạy:** timezone, trigger, deadline, retry, backfill, change window và schedule drift có theo dõi.
17. **Idempotency:** business key, transaction consistency, deduplication và xử lý timeout/duplicate runs.
18. **Data protection:** input/output classification, temporary files, output ACL, encryption, retention và audit redaction.
19. **Access request/approval:** grants và trust được duyệt theo snapshot, có risk/SoD owner.
20. **Joiner:** credential/trust/grants tạo chính xác và positive/negative probes đạt.
21. **Mover:** sau đổi job/owner/tenant/runner phải reapprove và revoke quyền/trust cũ.
22. **Owner Leaver:** chuyển ownership và thu hồi quyền người cũ nhưng không tự xóa workload còn hợp lệ.
23. **Job Leaver:** xóa lịch chạy chỉ là một bước; gỡ principals, grants, trust, API keys/PATs và sessions/tokens có liên quan.
24. **Effective revoke verification:** target readback + API/DB DENY theo phạm vi và SLA; không đánh đồng HTTP 200/204 với VERIFIED.
25. **Không phá chức năng hợp lệ:** positive controls bảo đảm các jobs khác vẫn hoạt động sau deprovision.
26. **Fault tests:** scheduler outage, token expiry, stale cache, policy timeout, retries, network partition và event replay.
27. **Monitoring:** expected run, failures, runtime, token issuance, anomalies, unauthorized grants và critical coverage gaps.
28. **Audit:** job/run IDs, trusted principals, policy version, actions, decisions, timestamps và evidence refs, không có secrets.
29. **Access review:** owner attestation, dormant/non-owner principals, credential age, privilege-hours và wildcard permissions.
30. **Closure/sign-off:** đánh dấu PARTIAL/UNVERIFIED khi chưa kiểm được target bắt buộc; không che giấu quyền tồn dư.

**Nguyên tắc nghiệm thu:** Một batch account được quản trị tốt khi **job hợp lệ có thể thực thi đúng nhiệm vụ theo lịch**, nhưng **không thể dùng danh tính đó để thực hiện những hành động ngoài quyền, ngoài tenant, ngoài môi trường hoặc sau khi quyền phải được thu hồi**.

## 36. Câu hỏi tự kiểm tra

**Câu 1.** Batch account là gì? Có phải mọi batch job đều dùng một loại account tên BatchAccount?

**Trả lời:** Batch account là khái niệm danh tính phi con người dùng cho tác vụ chạy theo lô. Hiện thực có thể là OS account, Windows gMSA, Kubernetes ServiceAccount, OAuth service principal, DB login hoặc workload identity khác; không có một đối tượng chuẩn duy nhất cho mọi nền tảng.

**Câu 2.** Vì sao cần phân biệt scheduler identity, execution identity và target principal?

**Trả lời:** Người sửa lịch/command, process chạy trong runtime và principal được API/DB chấp nhận là **ba ranh giới quyền** có thể khác nhau. Thu hồi một lớp không đảm bảo các lớp còn lại đã hết hiệu lực.

**Câu 3.** Một job chỉ chạy 15 phút mỗi ngày có mặc nhiên là time-bound access không?

**Trả lời:** Không. OAuth grant, DB role hoặc credential có thể hoạt động 24 giờ/ngày dù scheduler chỉ khởi động process 15 phút. Cần phân biệt runtime duration, token TTL và entitlement expiry.

**Câu 4.** Tại sao không dùng tài khoản admin của nhân viên để chạy job nền?

**Trả lời:** Credential có thể bị chia sẻ, tạo đặc quyền quá mức, khó audit và phụ thuộc trạng thái nhân sự. Khi người đó Leaver, job có thể hỏng hoặc tiếp tục dùng credential tồn dư ngoài kiểm soát.

**Câu 5.** gMSA giúp gì, và nó có cấp quyền Finance API không?

**Trả lời:** gMSA hỗ trợ quản trị danh tính/credential Windows trong môi trường phù hợp. Nó không tự cấp quyền API/DB; target vẫn yêu cầu grant và authorization riêng.

**Câu 6.** Một Kubernetes CronJob dùng ServiceAccount có tự truy cập cloud/Finance API được không?

**Trả lời:** Không. Kubernetes ServiceAccount là danh tính cluster. Cloud/API access đòi trust/federation hoặc credential khác, cùng grants/scopes và resource policy riêng.

**Câu 7.** Tại sao concurrencyPolicy: Forbid không đủ để bảo đảm thanh toán chỉ diễn ra một lần?

**Trả lời:** Nó chỉ tác động đến overlap theo CronJob scheduler tương ứng; manual triggers, retries, timeouts hoặc external commits vẫn có thể xảy ra. Cần idempotency key, transaction guards và reconciliation.

**Câu 8.** Một batch job có reports.read có được xuất mọi dữ liệu của mọi tenant không?

**Trả lời:** Không. Resource Server phải kiểm audience, scope/app role, tenant và resource/classification; API không được coi scope chung là quyền đọc mọi object.

**Câu 9.** Vì sao cấm interactive login chưa chứng minh account an toàn?

**Trả lời:** Credential/token app-only vẫn có thể dùng để gọi API hoặc DB. Cần bảo vệ secrets/trust và kiểm quyền thực tế tại target.

**Câu 10.** Khi owner batch account nghỉ việc, có nên xóa luôn job không?

**Trả lời:** Không nếu nghiệp vụ vẫn cần. Phải chuyển owner, gỡ quyền người cũ trên scheduler/repo/vault/trust, xem xét rotate credentials và giữ continuity của job hợp lệ.

**Câu 11.** Sau khi xóa CronJob và revoke OAuth grant, vì sao phải kiểm API key cục bộ?

**Trả lời:** API key/PAT có thể do SaaS/legacy target quản lý độc lập với scheduler hoặc OAuth AS. Nếu key còn dùng được, batch identity vẫn có một đường truy cập tồn dư.

**Câu 12.** Một HTTP 503 khi kiểm token cũ có nghĩa là đã DENY đúng chính sách không?

**Trả lời:** Không. Đây là lỗi khả dụng, cần positive control và bằng chứng authorization DENY tại target hoạt động bình thường.

**Câu 13.** Batch account có thể vi phạm SoD như thế nào?

**Trả lời:** Một bot có thể vừa tạo vừa phê duyệt payment, hoặc một người điều khiển hai service principals khác nhau để vượt bước duyệt độc lập. Cần xét business actor, effective controller và kiểm ở backend transaction.

**Câu 14.** Job không được sử dụng trong 90 ngày có chắc phải xóa không?

**Trả lời:** Không. Có thể là job cuối năm/DR hoặc log thiếu coverage. Phải xác minh owner, business calendar, approved need và rủi ro trước khi revoke; đồng thời các quyền không owner/không được duyệt cần được ưu tiên điều tra.

**Câu 15.** Khi nào được báo batch account đã decommission thành công?

**Trả lời:** Khi job/dependencies đã ngừng hoặc chuyển giao có kiểm soát, các principals/grants/trust/credentials đúng scope đã được thu hồi và các target bắt buộc có **readback + effective-access DENY evidence** trong SLA. Nếu còn unverified target, trạng thái phải phản ánh rõ.

**Câu 16.** Vì sao quyền read-only vẫn có thể gây rủi ro nghiêm trọng?

**Trả lời:** Job có thể đọc lượng lớn dữ liệu nhạy cảm rồi xuất sang bucket/share không được bảo vệ. Phải kiểm cả quyền đọc nguồn, quyền ghi đích, classification, retention và đối tượng được phép tải kết quả.

---

**Ghi nhớ:** **Batch account là danh tính phục vụ công việc tự động, không phải mật khẩu của một người dùng đặt trong cron.** Cần phân biệt **scheduler/control-plane identity, execution/runtime identity và downstream application/database principal**, kiểm quyền tối thiểu, xác thực workload, bảo vệ secrets, SoD, lịch chạy/retry/idempotency và luồng dữ liệu. Trong vòng đời **Joiner–Mover–Leaver**, batch job có **owner và danh tính độc lập với nhân viên**, cần đăng ký/cấp quyền khi onboard, rà soát và thu hồi quyền cũ khi thay đổi, rồi **decommission có bằng chứng tại API/DB/PEP**. Công việc hợp lệ tiếp tục chạy, còn **quyền dư thừa và quyền tồn dư** phải bị chặn theo đúng chính sách và SLA.

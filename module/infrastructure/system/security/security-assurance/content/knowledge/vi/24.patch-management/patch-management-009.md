# Theo dõi patch coverage – Đo lường độ bao phủ bản vá bằng bằng chứng

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Định nghĩa **patch coverage** và phân biệt với patch deployment success, vulnerability remediation, SLA compliance, scanner coverage và security assurance.
- Xây dựng **mẫu số đúng** từ asset inventory, patch applicability, phạm vi thời gian và các nghĩa vụ vá; tránh làm đẹp chỉ số bằng cách loại bỏ các tài sản chưa có dữ liệu.
- Phân biệt các trạng thái **applicable, not applicable có bằng chứng, installed, effective, pending reboot, failed, rolled back, deferred, exception và unknown**.
- Xác minh bản vá thực sự có hiệu lực trên **host, VM, container, Kubernetes workload, Java dependency, image và managed service** thay vì chỉ thấy package đã được tải về.
- Thiết kế inventory/reconciliation, freshness rule, data provenance, denominator confidence và quality gates để không đánh đồng “không thấy lỗi” với “đã vá”.
- Phân tích các chỉ số: asset coverage, asset–patch obligation coverage, deadline/SLA compliance, critical exposure, deployment success, scan coverage và thời gian khắc phục.
- Xây dashboard theo business criticality, Internet exposure, environment, vulnerability exploitability và patch cohort; tách tỷ lệ trung bình với **số lượng critical gaps thực tế**.
- Tạo mẫu evidence register, requirement/acceptance criteria, kiểm thử dữ liệu, drift detection, finding và escalation.
- Thực hành với ví dụ Java 17, JUnit 5, Linux/Windows/Kubernetes và hai case study trong chương trình **SECURITY_SECURITY_ASSURANCE**.

## 1. Patch coverage là gì?

**Patch coverage (độ bao phủ bản vá)** mô tả tỷ lệ hoặc mức độ các **tài sản/nghĩa vụ vá thuộc phạm vi** đã được triển khai và xác minh một cách phù hợp. Chỉ số này giúp tổ chức biết phần nào trong diện cần xử lý đã đạt trạng thái vá được chấp nhận, phần nào còn thiếu và mức tin cậy của kết luận.

Trong quản lý bản vá, câu “đã deploy patch” chưa đủ. Cần chứng minh:

1. Đã biết **tài sản nào** phải đánh giá.
2. Đã biết **bản vá hoặc trạng thái đích nào** áp dụng cho tài sản đó.
3. Bản vá/configuration/fixed version đã có trên **instance thực sự chạy**.
4. Các bước cần để có hiệu lực như restart, rollout, failover, rebuild hoặc migration đã hoàn thành khi cần.
5. Không có rollback, host/image cũ hoặc đường thực thi khác giữ vulnerability.
6. Có telemetry/test/evidence đủ mới và đúng scope để đưa vào tử số.
7. Việc chưa rõ, hết hạn evidence hoặc ngoại lệ vẫn được trình bày, không biến mất khỏi báo cáo.

Trong dịch vụ **SECURITY_SECURITY_ASSURANCE**, patch coverage là một **security assurance claim có điều kiện**: “Trong tập tài sản và patch requirements đã xác định, bao nhiêu nghĩa vụ có bằng chứng xác nhận bản vá hiệu lực ở thời điểm đánh giá?”. Nhóm phải truy được từ **risk và requirement → asset/patch → triển khai → xác minh → evidence → finding/remediation/retest**, không chỉ xem một tỷ lệ phần trăm.

### Ví dụ dễ nhầm

Nhóm vận hành báo: “Đã triển khai bản vá tới 98% máy chủ”. Nhưng:
- 14 VM không cài agent nên không nằm trong dashboard.
- 7 Windows servers đã cài update nhưng còn pending reboot.
- Một số Kubernetes nodes đã vá nhưng container images vẫn dùng dependency dễ bị khai thác.
- Một Java service đã nâng `pom.xml` nhưng release production vẫn chạy JAR cũ.
- Các host vừa được tạo từ golden image lỗi không có trong đợt scan.

Con số 98% có thể là **job delivery success trên các máy nhìn thấy**, không phải patch coverage hoặc vulnerability remediation coverage của toàn hệ thống. Phải xác định **mẫu số, trạng thái hoàn thành, nguồn evidence và thời điểm** trước khi công bố.

## 2. Patch coverage nằm ở đâu trong patch management?

Quy trình quản lý bản vá thường gồm:

~~~mermaid
flowchart LR
    I["Inventory assets / software"] --> A["Patch & advisory applicability"]
    A --> R["Risk-based prioritization"]
    R --> P["Approve change / rollout plan"]
    P --> D["Deploy patch or fixed build"]
    D --> V["Verify effective state"]
    V --> C["Calculate coverage and SLA"]
    C --> E["Evidence, findings, exceptions"]
    E --> M["Monitor drift and reassess"]
    M --> I
~~~

Patch coverage **không tự thay thế** các hoạt động khác:

| Thước đo/hoạt động | Câu hỏi | Không tự chứng minh |
| --- | --- | --- |
| **Inventory coverage** | Có nhận diện đủ assets thuộc scope? | Assets đã vá |
| **Scan coverage** | Scanner có kiểm tra được các assets? | Patch hiệu lực |
| **Deployment success** | Job/tool nói áp dụng thành công? | Runtime đang chạy fixed code |
| **Package installed** | Package hoặc KB đã có trong inventory? | Đã restart/load fixed binary khi cần |
| **Patch coverage** | Trong nghĩa vụ thuộc scope, bao nhiêu đã **verified effective**? | Không còn vulnerability khác |
| **Vulnerability remediation coverage** | Bao nhiêu findings/exposures được xác minh đã sửa? | Mọi bản vá baseline đều đạt |
| **SLA compliance** | Bao nhiêu nghĩa vụ đáp ứng deadline theo policy? | Toàn bộ nghĩa vụ hiện đã vá |
| **Exception coverage** | Bao nhiêu deferred findings có acceptance hợp lệ? | Findings đã fixed |
| **Security assurance** | Claim có đủ evidence đúng version/deployment/scope? | Rủi ro không thể xảy ra trong tương lai |

**Patch coverage là một chỉ số về tình trạng áp dụng**, không phải tuyên bố hệ thống “không còn lỗ hổng”.

## 3. Đơn vị đo: coverage của cái gì?

Không có một mẫu số duy nhất phù hợp mọi tình huống. Phải nêu rõ **unit of analysis**.

### 3.1. Asset coverage

Mỗi host/workload tính một lần nếu nó đạt **tất cả patch requirements bắt buộc trong baseline**.

- Phù hợp: nhìn nhanh tình trạng compliance của fleet.
- Giới hạn: một host thiếu một critical patch và một host thiếu 20 patches đều tính là một host chưa compliant.
- Phải có quy định thế nào là “fully patched” theo baseline/time window.

### 3.2. Asset–patch obligation coverage

Mỗi cặp **(asset, patch requirement)** áp dụng được tính là một nghĩa vụ.

Ví dụ:
- `vm-01` cần `OS-PATCH-A` và `OS-PATCH-B` → **2** obligations.
- `vm-02` chỉ cần `OS-PATCH-A` → **1** obligation.

Nếu cả hai bản vá đã hiệu lực trên `vm-01` nhưng `vm-02` thiếu patch A:
- Verified = 2 obligations.
- Applicable obligations = 3.
- Coverage = `2/3 ≈ 66,7%`.

Thước đo này hữu ích cho patch campaign và requirement traceability, nhưng có thể che chuyện một asset cực kỳ quan trọng chưa vá nếu gộp mọi cặp với trọng số bằng nhau.

### 3.3. Vulnerability–asset coverage

Đơn vị là **(asset, vulnerability finding)** sau khi xác minh applicability. Một bản vá có thể sửa nhiều vulnerabilities; ngược lại một vulnerability có thể cần kết hợp package update và configuration change. Không được đồng nhất số patches với số CVEs.

### 3.4. Release/image coverage

Đơn vị là **image digest, deployment hoặc workload instance**:
- Có bao nhiêu replicas chạy đúng fixed digest?
- Có image cũ còn ở node, scheduled job, CronJob hoặc rollback registry không?
- Có deployment mới từ base image cũ không?

**Docker tag mutable không đủ làm định danh patch status**. Cần digest/runtime identity. “Image đã build” không nghĩa “image đang chạy”.

### 3.5. Các phép đo phải được đặt tên

| Tên chỉ số | Đơn vị | Ví dụ câu hỏi |
| --- | --- | --- |
| Fleet patch-baseline coverage | Host/workload | Bao nhiêu assets đạt toàn bộ baseline? |
| Patch obligation coverage | Asset–patch requirement | Bao nhiêu nghĩa vụ có evidence effective? |
| Critical exposure coverage | Critical/exposed obligations | Bao nhiêu gap ở public-facing services đã được xử lý? |
| Vulnerability remediation coverage | Affected asset–finding | Có bao nhiêu exposures hết affected? |
| Deployment completion | Jobs/targets | Tool triển khai hoàn tất ở bao nhiêu target? |
| Evidence coverage | Obligations with acceptable observations | Bao nhiêu nghĩa vụ có trạng thái được chứng minh? |

Không trộn các tỷ lệ với mẫu số khác nhau rồi kết luận chung “patch coverage 95%”.

## 4. Xác định phạm vi và mẫu số đáng tin

### 4.1. Bắt đầu từ scope được phê duyệt

Các chiều cần xác định:
- Hệ thống, owner, business unit và service.
- Production/staging/dev và quy tắc bao gồm.
- Cloud account/project/subscription, datacenter, cluster và region.
- Host/VM, bare metal, VDI, laptop, appliance, container base image và managed services.
- OS, middleware, libraries, runtime, firmware, network device và patch families theo scope.
- Asset criticality, data classification và network exposure.
- Snapshot timestamp hoặc reporting window.
- Policy/baseline version và patch applicability source.

**Đừng xác định mẫu số từ “các máy agent đang gửi telemetry”** nếu tổ chức còn assets không có agent. Đó là denominator bias.

### 4.2. Nguồn để dựng inventory

| Nguồn | Điểm mạnh | Hạn chế |
| --- | --- | --- |
| CMDB/service catalog | Owner, business context, criticality | Có thể chưa cập nhật |
| Cloud/VM inventory | Running/terminated instances, tags, regions | Không tự thấy mọi software |
| Endpoint/patch agents | Installed package và job status | Unmanaged/offline assets vắng mặt |
| Vulnerability scanner | Detections, versions, exposure | Coverage và detection limitations |
| Container registry | Image manifests và digests | Image tồn tại không có nghĩa đã deploy |
| Kubernetes API | Pods, nodes, images, rollout hiện tại | Job/cluster khác có thể chưa inventory |
| CI/CD artifact records | Build/deployment identity | Release chưa chắc vào mọi runtime |
| SBOM/dependency graph | Package identity trong artifact được mô tả | SBOM có thể thiếu/bị lệch build |
| Network discovery | Phát hiện unmanaged hosts/services | Không luôn xác định owner |
| Asset ownership attestations | Xác nhận scope/ngoại lệ vận hành | Có thể không có telemetry độc lập |

### 4.3. Hợp nhất và khử trùng lặp

Một asset có thể xuất hiện với hostname, IP, cloud instance ID, VM UUID, endpoint agent ID hoặc Kubernetes UID. Phải định nghĩa **identity rule theo asset class** và không gộp sai:
- IP động không phải primary key đáng tin cho VM.
- Hostname có thể tái sử dụng.
- Một container image digest có thể chạy ở nhiều deployments.
- Một image tag có thể trỏ tới digest khác nhau theo thời gian.
- Một node có nhiều pods, patch node OS không vá application libraries.
- Một service trải nhiều regions cần kiểm tra các release/deployments tương ứng.

Lưu mapping và provenance khi reconcile. Nếu không xác định được asset identity, tạo **reconciliation gap**, không lặng lẽ xóa khỏi population.

### 4.4. Applicability phải có bằng chứng

Patch requirement chỉ áp dụng nếu thỏa điều kiện, ví dụ:
- OS version/architecture có affected build.
- Package/version và config đang affected.
- Vendor advisory áp dụng cho firmware model.
- Product feature/code path thuộc scope cần khắc phục.
- Bản vá được thay thế bởi superseding patch hoặc fixed backport tương đương theo advisory/vendor.

**Not applicable** phải có nguồn xác minh; không dùng “scan không báo” làm bằng chứng nếu scan bị thiếu nguồn. Khi applicability chưa biết, cần theo dõi trạng thái **UNKNOWN_APPLICABILITY**, thường vẫn đưa vào tập nghĩa vụ chưa xác định cho tới khi triage.

### 4.5. EOL và tài sản không còn hỗ trợ

Một host unsupported không được loại khỏi mẫu số chỉ vì vendor không còn patch. Cần:
- Ghi tình trạng unsupported/no fix.
- Xác định risk treatment (upgrade/migrate/isolate/decommission).
- Giữ gap hoặc risk exposure đúng scope.
- Chỉ loại khỏi active population khi đã **decommission được kiểm chứng**, không chỉ tạo ticket.
- Ngoại lệ/risk acceptance có thẩm quyền không tự biến host thành patched.

## 5. Patch lifecycle và trạng thái kiểm chứng

### 5.1. State model

| Trạng thái | Diễn giải | Tính vào verified numerator? |
| --- | --- | --- |
| **CANDIDATE** | Có patch requirement cần đánh giá | Chưa |
| **NOT_APPLICABLE_VERIFIED** | Không áp dụng, có evidence đúng scope | Loại khỏi mẫu số áp dụng, báo riêng |
| **UNKNOWN_APPLICABILITY** | Chưa biết có áp dụng không | Không; theo dõi như unresolved |
| **APPLICABLE_NOT_PATCHED** | Xác nhận cần vá nhưng chưa làm | Không |
| **SCHEDULED** | Đã lên lịch | Không |
| **DOWNLOADED/STAGED** | Đã tải hoặc chuẩn bị rollout | Không |
| **DEPLOYING** | Đang triển khai | Không |
| **INSTALLED_PENDING_RESTART** | Package/KB cài nhưng chưa active nếu cần restart | Không |
| **DEPLOY_FAILED** | Thất bại hoặc không xác định kết quả | Không |
| **ROLLED_BACK** | Quay lại affected build/version | Không |
| **VERIFIED_EFFECTIVE** | Đúng fixed state trên runtime, có evidence còn fresh | **Có** |
| **DEFERRED_APPROVED** | Có ngoại lệ hợp lệ hoặc approved defer | Không |
| **MITIGATED_NOT_PATCHED** | Control giảm exposure nhưng chưa vá | Không |
| **UNKNOWN/STALE_EVIDENCE** | Dữ liệu thiếu, sai scope hoặc quá cũ | Không |

Nếu một bản vá là **hotpatch và thực sự có hiệu lực không cần reboot** theo cơ chế vendor đã xác minh, có thể đánh dấu VERIFIED_EFFECTIVE. Không dùng “mọi Linux/Windows đều cần reboot” hoặc “mọi patch không cần reboot”; quyết định theo package/runtime và evidence.

### 5.2. Installed không đồng nghĩa effective

Một package có thể đã được tải/cài nhưng:
- Process vẫn giữ old library đã map trong memory.
- Kernel mới chưa boot.
- Windows update pending restart.
- Kubernetes deployment vẫn chạy image cũ.
- Replica hoặc node khác chưa rollout.
- Workload đang chạy container image khác image vừa scan.
- Job rollback sau deployment failure.
- Phần mềm có nhiều copy của cùng library, một copy vẫn vulnerable.

Tùy patch type, cần xác minh **loaded module, running kernel, process version, image digest, process restart hoặc end-to-end behavior**.

### 5.3. “Patched” phải dựa trên effective fix semantics

Một package Linux có thể dùng **security backport**: version string không giống upstream fixed version nhưng vendor package có patch. Một Windows update có thể được supersede bởi cumulative update. Vì vậy:
- Không chỉ so sánh lexical version number.
- Dùng vendor advisories/fixed build metadata thích hợp.
- Đối chiếu OS distribution release, channel, package build hoặc supersedence.
- Gắn kết luận vào advisory/patch rule version và artifact thực tế.
- Retest critical vulnerability khi cần, vì presence của KB/package không tự chứng minh mọi exploit path đã hết.

## 6. Công thức và diễn giải tỷ lệ

### 6.1. Phân loại tập hợp

Tại snapshot time `t`, định nghĩa:

- **Candidate universe U(t):** các cặp asset–patch requirement có thể liên quan theo inventory và baseline đã phê duyệt.
- **Verified not applicable N(t):** cặp được loại khỏi áp dụng **có bằng chứng đáng tin**.
- **Eligible denominator D(t):** tập `U(t) \ N(t)`, bao gồm cặp applicable và cặp chưa rõ applicability cần điều tra.
- **Verified effective V(t):** tập con `D(t)` có patch/runtime evidence hợp lệ, fresh và không bị rolled back.

Vậy:

~~~text
Patch obligation coverage (%) =
    100 × count(verified_effective obligations)
        / count(eligible obligations)

Eligible obligations =
    candidate in-scope obligations − verified_not_applicable

Unknown applicability / stale evidence / approved deferral
    vẫn thuộc denominator cho tới khi có quyết định loại trừ phù hợp.
~~~

**Denominator bằng 0** không được báo 100% theo mặc định: hiển thị `N/A (0 eligible obligations)` với inventory scope và reason rõ ràng. Nếu không biết population, kết quả là `INCONCLUSIVE`, không phải `N/A`.

### 6.2. Ví dụ tính toán

Trong một patch cohort có 132 candidate asset–patch pairs:
- 12 **NOT_APPLICABLE_VERIFIED** có evidence.
- 72 **VERIFIED_EFFECTIVE**.
- 18 **APPLICABLE_NOT_PATCHED**.
- 10 **INSTALLED_PENDING_RESTART**.
- 8 **DEPLOY_FAILED**.
- 7 **UNKNOWN/STALE**.
- 5 **DEFERRED_APPROVED** nhưng còn affected.

Tổng eligible = 132 − 12 = **120**, đúng bằng 72 + 18 + 10 + 8 + 7 + 5.

~~~text
Coverage = 72 / 120 × 100 = 60%

Not applicable verified: 12 (báo riêng)
Pending restart:        10 (chưa tính numerator)
Approved deferrals:      5 (chưa vá; giữ denominator)
Unknown/stale:           7 (không tự tính patched)
~~~

Nếu dashboard loại 5 exceptions và 7 unknown khỏi denominator rồi báo 72/108 = 66,7%, nó đang mô tả **một population khác**, không phải coverage đầy đủ ban đầu. Phải công bố chính xác exclusion criteria, lý do và risk implication. Ngoại lệ có thể ảnh hưởng **policy compliance** khi đúng thẩm quyền nhưng **không làm tăng technical patch coverage**.

### 6.3. Asset-level metric

Một asset được tính “fully patched” chỉ khi:
- Đã biết đầy đủ relevant patch baseline cho asset.
- Mọi applicable obligations đã VERIFIED_EFFECTIVE.
- Không có UNKNOWN/STALE nghĩa vụ bắt buộc.
- Evidence còn hạn theo policy.

~~~text
Fleet patch-baseline coverage (%) =
    100 × fully_verified_assets / all_in_scope_assets
~~~

Nếu một asset không có đủ applicability inventory, nó chưa phải fully verified. Đừng gộp asset không có telemetry như đã đạt.

### 6.4. SLA compliance khác coverage

Ví dụ: một patch chưa deploy nhưng remediation deadline **chưa đến**. Nó làm technical coverage thấp hơn 100%, nhưng chưa nhất thiết vi phạm SLA.

Ngược lại, một patch đã deploy **sau deadline** có thể làm current coverage tăng, nhưng không xóa lịch sử SLA breach. Hai chỉ số nên báo riêng:

- **Current verified patch coverage:** đã hiệu lực tại snapshot `t` hay chưa.
- **Deadline performance:** đã xử lý đúng hạn theo policy/vulnerability risk chưa.
- **Open overdue:** số nghĩa vụ quá hạn còn affected.
- **Historical lateness:** số nghĩa vụ đã sửa nhưng từng quá hạn.

Không reset deadline khi đổi ticket/scanner ID hoặc tạo exception trễ.

## 7. Mốc thời gian, cohort và denominator drift

### 7.1. Theo dõi một cohort cố định

Một patch campaign thường chốt một cohort: ví dụ các assets và patch requirements xác định ở thời điểm `t0`. Đo:
- Coverage tại `t0`.
- Coverage sau 24h, 7 ngày hoặc từng maintenance wave theo lịch.
- Khi kết thúc, số verified/overdue/unknown/exception.
- Assets bổ sung sau `t0` như một cohort mới hoặc được thêm theo rule minh bạch.

Cohort cố định giúp không bị “đổi mẫu số” để làm tăng %.

### 7.2. Continuous fleet snapshot

Đối với vận hành liên tục, mỗi snapshot `t` cần lấy current assets và baseline hiện hành. Nếu autoscaling làm số assets tăng/giảm, tỷ lệ có thể biến động dù không có host nào vừa patch:
- VM terminated có bằng chứng có thể rời population active.
- VM mới từ image cũ được thêm và là unpatched obligation.
- Pod được tạo lại từ digest fixed có thể tăng coverage.
- Pod cũ ở region chưa rollout vẫn làm giảm coverage.

Cần hiển thị cả **absolute counts** và denominator, không chỉ đường %.

### 7.3. So sánh lịch sử phải cùng định nghĩa

Nếu dashboard đổi từ asset-level sang obligation-level hoặc tăng scan coverage, các số trước/sau **không so sánh trực tiếp**. Lưu:
- Metric definition/version.
- Population rules và exclusion rules.
- Asset inventory snapshot.
- Patch baseline và rule version.
- Measurement timestamp.
- Evidence freshness threshold.

Nếu không thể tái hiện cách tính cũ, phải ghi limitation thay vì diễn giải chênh lệch như kết quả remediation.

## 8. Evidence freshness và confidence

### 8.1. Evidence có vòng đời

Một patch observation có thể là đúng tại lúc kiểm tra nhưng trở nên lỗi thời vì:
- Instance reimaged/rollback.
- Golden image đổi.
- Deployment chuyển region.
- Vendor patch được supersede.
- Advisory scope thay đổi.
- Agent mất kết nối.
- Container image tag được retarget.
- Application process khởi động lại từ artifact cũ.

Do đó mỗi observation nên có `observedAt`, `source`, `assetId`, `patchRequirementId`, `artifactDigest/build` và `verificationMethod`.

### 8.2. Freshness policy

Một quy tắc phải xác định:
- Dữ liệu nào cần kiểm tra trực tiếp từ runtime.
- Evidence tối đa bao nhiêu tuổi theo criticality/risk.
- Tín hiệu thay đổi nào làm evidence mất hiệu lực **ngay**, không chờ hết TTL.
- Lỗi clock/timezone hoặc future timestamp xử lý ra sao.
- Outage của scanner/agent có làm chuyển `UNKNOWN/STALE` không.
- Reviewers và runbooks khi nguồn telemetry thất bại.

Thời hạn freshness nên theo policy và risk, **không áp một con số giờ/ngày tùy ý như chuẩn phổ quát**. Với patch hot exploited ở public endpoint, dữ liệu cũ vài tuần hiển nhiên chưa đủ.

### 8.3. Data-quality dimensions

| Chiều | Cần chứng minh | Dấu hiệu vấn đề |
| --- | --- | --- |
| **Completeness** | Tất cả assets/baselines trong scope | Unmanaged hosts, unscanned regions |
| **Accuracy** | Version/effective state đúng | Agent báo installed nhưng kernel cũ |
| **Freshness** | Observation đủ gần snapshot | Lần scan cũ, offline |
| **Identity matching** | Gắn đúng asset/build/deployment | Reused hostname, wrong image tag |
| **Applicability confidence** | Not-applicable có evidence | Không có advisory mapping |
| **Integrity/provenance** | Evidence không bị sửa trái phép | Log/report không có trust controls |
| **Consistency** | Nguồn không mâu thuẫn hoặc được reconcile | Agent PASS, scanner vẫn thấy vulnerable |
| **Coverage boundaries** | Biết nguồn nào chưa kiểm tra | Thiếu queues/images/test environment |

### 8.4. Không để UNKNOWN biến thành PASS

Trạng thái nguồn nên có `HEALTHY`, `DEGRADED`, `UNAVAILABLE` và `UNKNOWN`. Khi không có observation, không dùng giá trị default `PATCHED` hoặc “last known green” vô thời hạn.

Một dashboard tốt đặt cạnh tỷ lệ coverage:
- Số assets không có agent.
- Số patch obligations chưa biết applicability.
- Tỷ lệ fresh evidence.
- Số source outages và last observed age.
- Số conflicting observations cần reconciliation.

## 9. Xác minh patch coverage trên hệ điều hành và máy chủ

### 9.1. Linux: package installed khác running state

Ví dụ đọc thông tin **chỉ để quan sát** trên một Debian/Ubuntu host:

~~~bash
# Kernel thực sự đang chạy:
uname -r

# Kernel package đã được cài có thể khác kernel đang chạy:
dpkg-query -W linux-image-amd64

# Package được cài trong hệ thống Debian/Ubuntu:
dpkg-query -W openssl
~~~

Với RPM-based distribution, có thể quan sát package bằng `rpm -q <PACKAGE_NAME>` và kernel bằng `uname -r`. Output cần được đối chiếu **theo distro, release, vendor advisory và fix semantics**; đừng coi upstream version string là quy tắc duy nhất, bởi vendor có thể backport security patches.

Cần trả lời:
1. Host có thuộc patch cohort không?
2. Advisory áp dụng cho distro/kernel/package build nào?
3. Fixed package thực sự được installed?
4. Nếu cần reboot, host đã boot vào kernel/fixed component?
5. Các process còn giữ library cũ không, cần restart?
6. Host có chạy đúng kernel/security config đã verify hay bị rollback?
7. Observation được lấy khi nào, từ nguồn/identity nào?
8. Có nhiều kernel/package copies và host nào trong fleet chưa cập nhật?

Một lệnh `dpkg-query` hoặc `rpm -q` đơn lẻ **không chứng minh** vulnerability remediation cho mọi service. Có thể cần vendor advisory mapping, package manager history, process inspection, reboot state và negative tests theo risk.

### 9.2. Windows: KB và trạng thái restart

Ví dụ kiểm tra thông tin ở host Windows:

~~~powershell
# Minh họa inspection; Get-HotFix không liệt kê đầy đủ mọi loại update.
Get-HotFix | Sort-Object InstalledOn -Descending | Select-Object -First 20

# Thông tin OS/build để đối chiếu policy/advisory:
Get-ComputerInfo | Select-Object WindowsProductName, WindowsVersion, OsBuildNumber
~~~

**Hạn chế:** `Get-HotFix` không phải nguồn đầy đủ cho mọi Windows servicing stack, Defender definition, application patch hoặc firmware. Cumulative/superseded updates khiến việc đối chiếu một KB theo kiểu “có/không” có thể sai. Cần nguồn inventory/patch management phù hợp, effective OS build, update history và required reboot state.

Khi agent báo `INSTALL_SUCCEEDED` nhưng còn pending restart, mặc định **chưa chứng minh effective state**, trừ khi patch mechanism/requirement cụ thể xác nhận hotpatch có hiệu lực không cần reboot.

### 9.3. Network appliances và firmware

Patch coverage của router/firewall/appliance cần:
- Device inventory và model/firmware family.
- Vendor advisory và affected/fixed firmware.
- Running firmware, active/standby node state.
- Maintenance window và failover integrity.
- Management-plane exposure.
- Telemetry/attestation từ device hoặc vendor.
- Rollback/recovery và support status.

Một firmware image đã upload nhưng appliance vẫn chạy version cũ không được counted patched. Với HA pair, cần xét **mọi node có thể xử lý traffic**, không chỉ active node.

### 9.4. Host agent bị offline

Nếu patch agent offline:
- Không loại host khỏi population chỉ vì không thấy.
- Dùng discovery/CMDB/cloud inventory xác minh host còn active.
- Tách trạng thái **asset offline** với **asset decommissioned**.
- Chỉ đánh dấu VERIFIED_EFFECTIVE nếu evidence hiện có vẫn còn hợp lệ theo policy và không có trigger làm stale.
- Nếu không đủ evidence, dùng UNKNOWN/STALE; mở việc điều tra source-health.

## 10. Coverage cho Java/Spring Boot, container và Kubernetes

### 10.1. Java dependency patch

Một issue có thể được sửa bằng nâng `com.example.training:report-parser`. Để gọi patch effective cần:
1. Build/dependency graph thực tế xác nhận không còn affected version theo advisory.
2. Version fixed/mitigated đúng ecosystem và configuration.
3. Release JAR/WAR/container được tạo từ source với dependency update.
4. Artifact digest gắn với CI tests và SCA/security verification.
5. Production deployment thực sự chạy đúng artifact/digest.
6. Các worker/CronJob/legacy endpoints không còn dùng old library.
7. Nếu còn affected library ở classpath khác, không đóng toàn bộ finding.
8. Nếu remediation cần config/feature disable, phải xác minh effective behavior riêng.

Ví dụ lệnh để quan sát resolved dependencies:

~~~bash
# Maven: phục vụ quan sát resolved dependency graph.
mvn -B -ntp dependency:tree

# Gradle: quan sát runtimeClasspath theo cấu hình tương ứng.
./gradlew dependencies --configuration runtimeClasspath
~~~

**Các lệnh này không tự chứng minh runtime production đã vá.** Chúng cũng có thể không bao phủ các configurations khác, plugin, native libraries hoặc dynamically loaded modules.

### 10.2. Container images

Cần phân biệt bốn trạng thái:
- Base image đã publish fixed version.
- Application image đã rebuild từ base image mới.
- Image digest đã được scan, approved và publish.
- Workloads đang chạy **đúng digest** đã approved.

Một container đang chạy không tự thay đổi bytes vì có image mới trong registry. Rollout phải thay image/pod theo deployment strategy và kiểm tra replicas.

### 10.3. Kubernetes rollout

Các câu hỏi:
- Những deployments/DaemonSets/StatefulSets/CronJobs nào thuộc scope?
- Desired image digest là gì?
- Pods thực tế đang chạy digest nào?
- Rollout đã completed và available replicas đủ theo policy?
- Old pods hoặc orphan jobs có còn chạy?
- Cluster/namespace/region khác có dùng image cũ?
- Có pod bị rollback hoặc scale-up từ image chưa vá?
- Node OS patch có hoàn tất reboot/drain và quay lại scheduling an toàn?

Lệnh quan sát có thể dùng trong môi trường **được phép**:

~~~bash
# Chỉ liệt kê và xem hiện trạng; không thực hiện rollout.
kubectl get deployments -A
kubectl get pods -A -o wide

# Đọc dữ liệu trạng thái, gồm imageID trong containerStatuses khi có.
kubectl get pods -A -o json
~~~

Output JSON chỉ là raw data. Cần ánh xạ `metadata.uid`, namespace, owner/controller, `spec.containers[].image` và `status.containerStatuses[].imageID` sang approved release digest/patch obligation. Một pod không Ready cũng chưa chắc đang phục vụ traffic; một CronJob chưa chạy vẫn là tương lai có thể tạo workload vulnerable. Cần quy định scope và cách xử lý inactive controllers.

### 10.4. Image digest và tag

Ví dụ:
- `registry.example/app:stable` có thể trỏ sang image khác theo thời gian.
- `registry.example/app@sha256:<DIGEST>` định danh immutable artifact content theo manifest digest.
- Nếu CI scan digest A nhưng production pull digest B, không được dùng evidence A để tính B patched.

**Artifact integrity là cần nhưng chưa đủ:** image A có thể đúng bytes đã build nhưng vẫn chứa vulnerable package; phải có patch baseline/advisory mapping và remediation verification.

### 10.5. Dependency và OS patch là hai cấp độc lập

Một pod có fixed Java library nhưng host/node kernel vulnerable; hoặc node fully patched nhưng container vẫn dùng affected JAR. Vì vậy:
- Node OS baseline đo trên nodes.
- Container base image dependencies đo trên image digests.
- Application dependencies đo trên built artifacts/workload releases.
- Không cộng các lớp thành một “100% patched” chung khi không nêu rõ đơn vị và quy tắc.
- Risk scenario có thể đòi **nhiều nghĩa vụ** cùng được xác minh.

## 11. Managed services, serverless và SaaS

Tổ chức có thể không có quyền truy cập package manager của managed database, PaaS hoặc SaaS. Điều này không làm mất yêu cầu quản trị patch risk.

### Cần phân định trách nhiệm

- Phần nào do cloud/vendor quản lý (managed OS, engine, control plane)?
- Phần nào do khách hàng kiểm soát (engine version, client library, plugin, config, maintenance window)?
- Provider có version/advisory/maintenance status và evidence nào?
- Có delayed maintenance, version pin hoặc upgrade window chưa hoàn thành?
- Có contractual/security obligations và cách escalation khi vendor chậm?
- Có quyền/khả năng lựa chọn fixed engine version hay phải chờ vendor?

### Cách đánh giá

| Hệ thống | Kiểu evidence | Giới hạn |
| --- | --- | --- |
| Managed database | Engine version, provider advisory/maintenance status, config | Host-level patches có thể không quan sát trực tiếp |
| Managed Kubernetes control plane | Cluster version/provider maintenance notice | Worker node/app image vẫn có trách nhiệm riêng |
| Serverless function | Published function version, runtime, layer/package digests | Provider underlying host patches không tự quan sát |
| SaaS | Vendor attestation, release notice, contract/security report | Độ chi tiết và freshness phụ thuộc vendor |
| IoT/appliance | Firmware version và vendor confirmation | Device offline hoặc OTA chưa apply |

Nếu evidence không đủ để chứng minh claim cần thiết, ghi **vendor-assurance limitation/INCONCLUSIVE** hoặc evidence-level thay thế đã được chính sách phê duyệt. Không tự ghi patched chỉ vì “vendor quản lý”.

## 12. Ưu tiên theo risk thay vì chạy theo phần trăm

Patch coverage toàn fleet có thể cao trong khi một số gap cực kỳ nguy hiểm còn tồn tại. Cần phân tầng theo:

- **Asset criticality:** core identity, payment, customer data, production admin.
- **Exposure:** Internet-facing, partner-facing, internal, restricted management.
- **Exploit intelligence:** known exploited, evidence exploitation, credible public exploit.
- **Severity:** CVSS và affected component risk.
- **Reachability:** vulnerable code path, privileges, preconditions.
- **Business impact:** dữ liệu, availability, safety, privacy.
- **Time to deadline:** remediation target và overdue days.
- **Compensating controls:** verified coverage, bypass và durability.
- **Evidence confidence:** actual deployment, version, source health và testing.

### Risk-segmented reporting

| Segment | Coverage có ích | Ngoài tỷ lệ phải hiển thị |
| --- | --- | --- |
| Internet-facing critical | Verified effective obligations / eligible critical obligations | Số affected endpoints, active exploit, overdue |
| Identity/admin services | Critical baseline per service/host | MFA/IAM/TLS dependencies, failure modes |
| Customer data workloads | Relevant OS/app/image obligations | Cross-tenant risk và actual deployment |
| Internal batch/queues | Worker/producer/library obligations | Internal bypass, unscanned jobs |
| End-user devices | Device baseline coverage | Unmanaged/offline/unsupported |
| Vendor/managed services | Verified provider/customer obligations | Evidence freshness và owner |
| Unsupported/EOL | Migration/isolation treatment progress | Số assets chưa rời production |

### Ví dụ: coverage cao nhưng vẫn cần escalation

Fleet có 1.000 nghĩa vụ, 990 verified effective: **99%**. Trong 10 còn lại, một nghĩa vụ nằm ở public API xử lý dữ liệu nhạy cảm với lỗ hổng đang bị khai thác. Chỉ số 99% **không** làm giảm tính cấp bách của risk cụ thể.

Đặt song song:
- Coverage toàn fleet.
- Coverage của critical/known exploited exposures.
- Số public/high-impact unpatched obligations.
- Số overdue critical gaps.
- Số UNKNOWN assets và confidence.
- Hành động containment và owner.

Không dùng trung bình toàn fleet làm điều kiện duy nhất cho release/admission.

## 13. Exceptions, mitigation và patch coverage

Khi không thể vá đúng hạn, vulnerability management có thể có **time-bound exception/risk acceptance** hoặc compensating controls. Nhưng trạng thái đó **không** biến bản vá thành hiệu lực.

Ví dụ:
- Một host có exception phê duyệt vì maintenance window.
- Một WAF rule giúp giảm khả năng khai thác web vulnerability.
- Một package đã được cô lập khỏi public ingress.
- Một managed device cần chờ vendor patch.

Cách báo:
- **Technical patch coverage:** nghĩa vụ còn unpatched vẫn ở denominator, không vào numerator.
- **Risk treatment status:** mitigated/exception active có record riêng.
- **SLA policy status:** có thể cho phép một deviation đúng authority theo policy, nhưng không rewrite lịch sử.
- **Residual risk:** vẫn có owner, uncertainty và các trigger.
- **Remediation backlog:** vẫn cần plan và deadline.

| Tình trạng | Patch numerator | Risk management |
| --- | --- | --- |
| Verified effective fixed state | Có | Risk scenario có thể resolved nếu test phù hợp |
| Installed, cần restart | Không | Work item còn mở |
| WAF/segmentation verified, chưa patch | Không | Mitigation với coverage/risk review |
| Approved exception, chưa patch | Không | Chấp nhận residual risk theo hạn/scope |
| False positive / not applicable có evidence | Loại khỏi eligible denominator | Lưu rationale/expiry của determination |
| Scanner silent vì thiếu source | Không | UNKNOWN/INCONCLUSIVE |
| EOL không có patch | Không | Migration/isolation/decommission; possible exception |

### Tránh lạm dụng denominator

Nếu công bố riêng `policy-compliant-or-excepted` có thể cộng các ngoại lệ hợp lệ theo định nghĩa compliance **nhưng phải đặt tên chỉ số khác**. Không trình bày kết quả này là technical patch coverage hoặc vulnerability fixed rate.

## 14. Reconcile nhiều nguồn và xử lý mâu thuẫn

Một nền tảng thường có các quan sát:
- Patch tool báo installation succeeded.
- EDR agent báo package version mới.
- Vulnerability scanner vẫn báo affected.
- Cloud inventory liệt kê instance mới chưa scan.
- CMDB ghi asset đã decommission, nhưng network discovery còn thấy service.
- CI báo fixed image, runtime vẫn chạy old image digest.

Đó không phải tình huống nên chọn nguồn “xanh nhất”.

### Quy trình reconciliation

1. Map mọi record tới **canonical asset/deployment identity** và timestamp.
2. Kiểm tra loại evidence: intent/job result hay actual-state observation?
3. Kiểm tra baseline/advisory rule version và vendor backports/supersedence.
4. So sánh deployment/build/digest đúng với thời điểm scan.
5. Xem evidence freshness, source completeness và credentials của scanner.
6. Phân loại: conflicting, stale, not applicable, unpatched hoặc verified effective.
7. Chạy kiểm tra bổ sung trên đúng asset khi kết luận ảnh hưởng critical.
8. Giữ audit trail của quyết định, không xóa record trái chiều.
9. Tạo finding nếu source/coverage có vấn đề hệ thống.
10. Recompute metrics với snapshot/rules có version.

### Mẫu reconciliation

| Observation A | Observation B | Câu hỏi | Trạng thái tạm |
| --- | --- | --- | --- |
| Job SUCCESS | Pending reboot | Fix đã active chưa? | Pending restart |
| Fixed JAR in CI | Old digest in production | Release nào đang chạy? | Unpatched production |
| Scanner affected | Vendor backport claimed | Package build/advisory mapping đúng không? | INCONCLUSIVE tới khi xác minh |
| CMDB retired | Cloud instance running | Host đã decommission thật chưa? | In scope / investigate |
| KB absent | Superseding cumulative KB installed | Windows servicing state tương đương? | Verify effective |
| No scan finding | Scanner source down | Có actual-state evidence khác không? | UNKNOWN |
| Container image scanned fixed | Old CronJob template | Job tương lai có thể chạy affected image? | Scope gap |

## 15. Rollout waves, rollback và trạng thái bền vững

Một patch campaign có thể theo waves: canary → limited production → broad production. Để theo dõi coverage chính xác:
- Gắn mỗi nghĩa vụ với `waveId`, deployment/maintenance window và owner.
- Báo trạng thái theo từng wave, không biến scheduled thành patched.
- Đặt acceptance tests cho app health, functionality và security effectiveness.
- Xác minh restart/reboot, primary/standby và workloads có khả năng tự khởi động lại.
- Theo dõi rollback events; nếu quay về affected version, **rút khỏi numerator**.
- Sau rollback cần containment/exception/reassessment nếu còn rủi ro.
- Không sửa lịch sử snapshot đã chụp; ghi snapshot mới và event trail.

### Xử lý rollback

1. Release A có fixed package, verified PASS.
2. Deployment gặp regression, rollback về Release B chứa affected package.
3. Snapshot sau rollback phải đổi applicable obligation thành **ROLLED_BACK/UNPATCHED**.
4. Patch coverage giảm và risk/finding được mở lại hoặc cập nhật.
5. Đội ngũ tìm phương án fix mới, compensating control và kế hoạch tiếp tục.

Không giữ trạng thái “Patched” vì trước đó từng đạt một lần.

## 16. Security assurance requirements cho coverage

Các ID dưới đây là **mẫu phục vụ đào tạo**, không phải mã điều khoản chuẩn.

| ID | Yêu cầu có thể kiểm chứng | Verification |
| --- | --- | --- |
| **PC-REQ-01** | Assets thuộc patch scope phải được reconcile từ inventory độc lập, có owner | Asset joins và unmanaged-host discovery tests |
| **PC-REQ-02** | Patch requirement được map theo product/version/config và advisory/baseline version | Applicability rule review |
| **PC-REQ-03** | NOT_APPLICABLE chỉ được loại khỏi denominator khi có verified evidence | Exclusion negative tests |
| **PC-REQ-04** | UNKNOWN/STALE/DEFERRED không được tính verified patched | Metric unit tests |
| **PC-REQ-05** | Installed pending restart/rollout không được counted effective nếu activation chưa chứng minh | Reboot/restart tests |
| **PC-REQ-06** | Metrics phải ghi unit, scope, cutoff, denominator/numerator và calculation version | Dashboard/evidence inspection |
| **PC-REQ-07** | CI artifact và production runtime phải được đối chiếu digest đối với app/image patch | Deployment verification |
| **PC-REQ-08** | Critical Internet-facing unpatched obligations phải được alert/escalate theo policy | Synthetic gap/alert test |
| **PC-REQ-09** | Mỗi overdue/unsupported obligation phải có owner và risk treatment | Backlog/exception review |
| **PC-REQ-10** | Coverage evidence phải có freshness/source-health và không tự PASS khi thiếu dữ liệu | Source-outage tests |
| **PC-REQ-11** | Backport, supersedence và applicable version mapping phải dùng trusted vendor rules | Vendor mapping tests |
| **PC-REQ-12** | Rollback phải cập nhật current patched status và risk | Rollback integration test |
| **PC-REQ-13** | Release phải xác minh transitive app dependencies/workers thuộc patch scope | Artifact/SBOM/test comparison |
| **PC-REQ-14** | Status/finding/exception phải tách biệt, không làm sai technical numerator | Approved-deferral negative test |
| **PC-REQ-15** | Coverage theo cohort/criticality phải công bố denominator drift và absolute gap counts | Historical comparison review |
| **PC-REQ-16** | Patch coverage findings chỉ được đóng sau actual-state verification/retest | Closure evidence test |
| **PC-REQ-17** | Managed/vendor assets phải có shared-responsibility mapping và evidence limitation | Vendor assurance review |
| **PC-REQ-18** | Changes thêm image/host/region/patch rule phải kích hoạt reassessment | Change-trigger test |

Yêu cầu cần được gắn với **risk, service owner, acceptance criteria, policy, evidence và actual deployment**. Không dùng “dashboard có số liệu” làm bằng chứng rằng các requirements đã được thỏa.

## 17. Java 17: tính coverage có kiểm soát denominator và freshness

Ví dụ này minh họa bộ tính **asset–patch obligation coverage**. Nó không thay endpoint inventory, advisory applicability engine hoặc scanner, mà bảo vệ một số invariant khi tổng hợp:

- Một cặp asset–patch chỉ xuất hiện một lần trong snapshot.
- Out-of-scope chỉ bị bỏ nếu scope đã được xác định bởi nguồn đáng tin.
- Verified not applicable **chỉ được loại** khi có fresh evidence.
- Unknown applicability, missing evidence và stale observations vẫn được giữ trong eligible denominator.
- Chỉ `APPLICABLE + VERIFIED_EFFECTIVE + fresh evidence` mới vào numerator.
- Deferred approval, installed-pending-restart, failed hoặc rolled back đều **không** tính patched.
- Eligible denominator bằng zero ⇒ coverage là **N/A**, không tự báo 100%.

### 17.1. Data model và calculator

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;

public final class PatchCoverageCalculator {

    public enum Applicability {
        APPLICABLE,
        NOT_APPLICABLE_VERIFIED,
        UNKNOWN
    }

    public enum State {
        VERIFIED_EFFECTIVE,
        INSTALLED_NOT_ACTIVE,
        MISSING,
        DEPLOY_FAILED,
        ROLLED_BACK,
        DEFERRED_APPROVED,
        UNKNOWN
    }

    public record Observation(
            String assetId,
            String requirementId,
            boolean inScope,
            Applicability applicability,
            State state,
            Instant observedAt,
            String evidenceRef) {}

    private record Key(String assetId, String requirementId) {}

    public record Report(
            int candidate,
            int notApplicableExcluded,
            int eligible,
            int verifiedEffective,
            int unresolved,
            Double coveragePercent) {}

    public Report calculate(
            List<Observation> observations,
            Clock clock,
            Duration evidenceMaxAge) {

        Objects.requireNonNull(observations);
        Objects.requireNonNull(clock);
        Objects.requireNonNull(evidenceMaxAge);
        if (evidenceMaxAge.isZero() || evidenceMaxAge.isNegative()) {
            throw new IllegalArgumentException("Positive maxAge required");
        }

        Set<Key> seen = new HashSet<>();
        int candidate = 0;
        int excluded = 0;
        int eligible = 0;
        int verified = 0;

        Instant now = clock.instant();
        Instant earliestAllowed = now.minus(evidenceMaxAge);

        for (Observation row : observations) {
            if (row == null || blank(row.assetId())
                    || blank(row.requirementId())
                    || row.applicability() == null
                    || row.state() == null) {
                throw new IllegalArgumentException(
                        "Invalid observation or identity");
            }
            if (!row.inScope()) {
                // In-scope rule phải có provenance riêng ở upstream.
                continue;
            }

            Key key = new Key(row.assetId(), row.requirementId());
            if (!seen.add(key)) {
                throw new IllegalArgumentException(
                        "Duplicate asset-patch obligation");
            }

            candidate++;

            boolean fresh = row.observedAt() != null
                    && !row.observedAt().isAfter(now)
                    && !row.observedAt().isBefore(earliestAllowed);
            boolean hasEvidence = !blank(row.evidenceRef());
            boolean trustworthyObservation = fresh && hasEvidence;

            if (row.applicability()
                    == Applicability.NOT_APPLICABLE_VERIFIED
                    && trustworthyObservation) {
                excluded++;
                continue;
            }

            // Unknown applicability hoặc N/A thiếu chứng cứ:
            // không được tự biến mất khỏi denominator.
            eligible++;

            if (row.applicability() == Applicability.APPLICABLE
                    && row.state() == State.VERIFIED_EFFECTIVE
                    && trustworthyObservation) {
                verified++;
            }
        }

        int unresolved = eligible - verified;
        Double percentage = eligible == 0
                ? null
                : (100.0 * verified / eligible);

        return new Report(candidate, excluded,
                eligible, verified, unresolved, percentage);
    }

    private static boolean blank(String value) {
        return value == null || value.isBlank();
    }
}
~~~

**Giới hạn của code học tập:**
- `evidenceRef` không được cryptographically verified trong ví dụ; production phải xác minh source, authorization, integrity và mapping tới actual asset/deployment.
- Mỗi observation có cặp `assetId + requirementId` duy nhất. Nếu hệ thống có nhiều observations theo thời gian, upstream phải chọn một current snapshot nhất quán và lưu history, không tự lấy bản “xanh nhất”.
- `NOT_APPLICABLE_VERIFIED` là classification cần nguồn có thẩm quyền. Fresh timestamp + evidenceRef chỉ là **điều kiện tối thiểu**, không phải assurance đầy đủ.
- `Duration` là một rule minh họa. Freshness phải được thiết lập theo risk/service class và trigger invalidation, không chỉ theo tuổi tuyệt đối.
- Không có input inventory không chứng minh denominator thật sự bằng 0; cần inventory completeness và baseline assessment độc lập.
- Code chưa tính exposure-weighted metrics, SLA history hoặc per-segment dashboards. Chúng có rule khác và không được gộp tùy tiện.

### 17.2. JUnit 5: kiểm tra những lỗi mẫu số phổ biến

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;
import org.junit.jupiter.api.Test;

class PatchCoverageCalculatorTest {

    private static final Instant NOW =
            Instant.parse("2026-11-28T04:00:00Z");
    private static final Clock CLOCK =
            Clock.fixed(NOW, ZoneOffset.UTC);
    private static final Duration MAX_AGE =
            Duration.ofHours(24);

    private final PatchCoverageCalculator calculator =
            new PatchCoverageCalculator();

    private PatchCoverageCalculator.Observation row(
            String asset, String requirement,
            PatchCoverageCalculator.Applicability applicability,
            PatchCoverageCalculator.State state,
            Instant observedAt, String evidenceRef) {
        return new PatchCoverageCalculator.Observation(
                asset, requirement, true,
                applicability, state, observedAt, evidenceRef);
    }

    @Test
    void excludesOnlyVerifiedNotApplicableAndKeepsUnknown() {
        var a = row("vm-01", "OS-001",
                PatchCoverageCalculator.Applicability.APPLICABLE,
                PatchCoverageCalculator.State.VERIFIED_EFFECTIVE,
                NOW, "EV-01");

        var b = row("vm-02", "OS-001",
                PatchCoverageCalculator.Applicability.APPLICABLE,
                PatchCoverageCalculator.State.INSTALLED_NOT_ACTIVE,
                NOW, "EV-02");

        var c = row("vm-03", "OS-001",
                PatchCoverageCalculator.Applicability.NOT_APPLICABLE_VERIFIED,
                PatchCoverageCalculator.State.UNKNOWN,
                NOW, "NA-EV-03");

        var d = row("vm-04", "OS-001",
                PatchCoverageCalculator.Applicability.UNKNOWN,
                PatchCoverageCalculator.State.UNKNOWN,
                NOW, null);

        var result = calculator.calculate(
                List.of(a, b, c, d), CLOCK, MAX_AGE);

        assertEquals(4, result.candidate());
        assertEquals(1, result.notApplicableExcluded());
        assertEquals(3, result.eligible());
        assertEquals(1, result.verifiedEffective());
        assertEquals(2, result.unresolved());
        assertEquals(100.0 / 3.0,
                result.coveragePercent(), 0.0001);
    }

    @Test
    void staleInstalledStateCannotRemainVerified() {
        var a = row("vm-01", "OS-001",
                PatchCoverageCalculator.Applicability.APPLICABLE,
                PatchCoverageCalculator.State.VERIFIED_EFFECTIVE,
                NOW.minus(Duration.ofDays(5)), "OLD-EVIDENCE");

        var result = calculator.calculate(
                List.of(a), CLOCK, MAX_AGE);

        assertEquals(1, result.eligible());
        assertEquals(0, result.verifiedEffective());
        assertEquals(1, result.unresolved());
    }

    @Test
    void notApplicableWithoutEvidenceStaysInDenominator() {
        var a = row("vm-01", "OS-001",
                PatchCoverageCalculator.Applicability.NOT_APPLICABLE_VERIFIED,
                PatchCoverageCalculator.State.UNKNOWN,
                NOW, null);

        var result = calculator.calculate(
                List.of(a), CLOCK, MAX_AGE);

        assertEquals(1, result.eligible());
        assertEquals(0, result.notApplicableExcluded());
    }

    @Test
    void approvedDeferralIsNotPatched() {
        var a = row("vm-01", "OS-001",
                PatchCoverageCalculator.Applicability.APPLICABLE,
                PatchCoverageCalculator.State.DEFERRED_APPROVED,
                NOW, "EXCEPTION-001");

        var result = calculator.calculate(
                List.of(a), CLOCK, MAX_AGE);

        assertEquals(0, result.verifiedEffective());
        assertEquals(1, result.unresolved());
    }

    @Test
    void duplicateObligationIsRejectedRatherThanDoubleCounted() {
        var a = row("vm-01", "OS-001",
                PatchCoverageCalculator.Applicability.APPLICABLE,
                PatchCoverageCalculator.State.VERIFIED_EFFECTIVE,
                NOW, "EV-01");

        assertThrows(IllegalArgumentException.class, () ->
                calculator.calculate(
                        List.of(a, a), CLOCK, MAX_AGE));
    }

    @Test
    void emptyUniverseDoesNotReportOneHundredPercent() {
        var result = calculator.calculate(
                List.of(), CLOCK, MAX_AGE);

        assertEquals(0, result.eligible());
        assertNull(result.coveragePercent());
    }

    @Test
    void futureTimestampDoesNotQualifyAsEvidence() {
        var a = row("vm-01", "OS-001",
                PatchCoverageCalculator.Applicability.APPLICABLE,
                PatchCoverageCalculator.State.VERIFIED_EFFECTIVE,
                NOW.plusSeconds(3600), "EV-IN-FUTURE");

        var result = calculator.calculate(
                List.of(a), CLOCK, MAX_AGE);

        assertEquals(0, result.verifiedEffective());
    }
}
~~~

Các test minh họa logic aggregation. Trong workflow thật cần kiểm thử thêm **inventory completeness, actual effective patch, supersedence/backport mapping, source outages, rollout/restart, conflicting observations, clock skew, rollback và patch cohort rules**.

## 18. Coverage evidence register

Một số đo có thể giải thích và kiểm toán phải lưu **cả kết quả lẫn định nghĩa phép tính**.

### 18.1. YAML mẫu

Các giá trị `<...>` là placeholder cần điền từ hệ thống thực, không phải bằng chứng đã thu thập.

~~~yaml
assessment_id: PATCH-COVERAGE-2026-EXAMPLE
module: SECURITY_SECURITY_ASSURANCE
topic: Theo dõi patch coverage
service: reporting-platform
metric:
  id: PATCH-OBLIGATION-COVERAGE
  definition_version: "1.0"
  unit: asset-patch-requirement
  cutoff_at: "<ISO_8601_UTC>"
  cohort_id: "<COHORT_OR_SNAPSHOT_ID>"
  denominator_rule: >
    In-scope candidate obligations excluding only
    independently verified not-applicable obligations.
  numerator_rule: >
    Applicable obligations with current,
    verified-effective runtime evidence.
  zero_denominator_rule: "N/A; do not default to 100 percent"
scope:
  environments: ["production"]
  regions: ["<REGIONS>"]
  asset_types: ["vm", "kubernetes-node", "container", "application"]
  service_owner: "<SERVICE_OWNER>"
  asset_inventory_snapshot_ref: "<CANONICAL_ASSET_INVENTORY>"
  reconciliation_report_ref: "<INVENTORY_JOIN_AND_GAP_REPORT>"
  baseline_ref: "<APPROVED_PATCH_BASELINE_VERSION>"
  advisories_ref: "<PATCH_APPLICABILITY_RULES>"
evidence_policy:
  max_age_ref: "<RISK_BASED_FRESHNESS_POLICY>"
  accepted_sources:
    - "<PATCH_AGENT>"
    - "<SIGNED_BUILD_AND_DEPLOYMENT_RECORD>"
    - "<RUNTIME_PACKAGE_OR_DIGEST_VERIFICATION>"
  source_health_ref: "<AGENT_SCAN_CONNECTIVITY_HEALTH>"
  not_applicable_approval_ref: "<APPLICABILITY_REVIEW_RECORD>"
counts:
  candidate: 132
  verified_not_applicable: 12
  eligible: 120
  verified_effective: 72
  applicable_not_patched: 18
  installed_pending_activation: 10
  failed_or_rolled_back: 8
  unknown_or_stale: 7
  deferred_approved_not_patched: 5
  coverage_percent: 60.0
segments:
  - id: "<CRITICAL_INTERNET_FACING>"
    eligible: "<SEGMENT_DENOMINATOR>"
    verified: "<SEGMENT_NUMERATOR>"
    overdue: "<OVERDUE_COUNT>"
    unknown: "<UNKNOWN_COUNT>"
  - id: "<MANAGED_SERVICE>"
    evidence_level: "<PROVIDER_ASSURANCE_METHOD>"
    limitations: "<VENDOR_EVIDENCE_LIMITATION>"
assurance:
  verification_test_refs:
    - "<INVENTORY_COMPLETENESS_TEST>"
    - "<PENDING_RESTART_NEGATIVE_TEST>"
    - "<DEPLOYED_DIGEST_MATCH_TEST>"
    - "<EXCEPTION_NOT_PATCHED_TEST>"
  actual_deployment_refs: ["<DEPLOYMENT_IDS_AND_DIGESTS>"]
  result: "<PASS_FAIL_INCONCLUSIVE>"
  assessed_at: "<ISO_8601_UTC>"
  reviewer: "<AUTHORIZED_ASSESSOR>"
findings:
  open: ["<PATCH_GAP_FINDING_IDS>"]
  exception_refs: ["<APPROVED_RISK_EXCEPTIONS_IF_ANY>"]
limitations:
  - "<UNSCANNED_OR_UNMANAGED_ASSETS>"
  - "<UNCERTAIN_BACKPORT_OR_APPLICABILITY>"
  - "<UNVERIFIED_VENDOR_SCOPE>"
reassessment_triggers:
  - "New critical advisory or known exploitation"
  - "New asset, image, service, region or baseline"
  - "Rollback, outdated process or unexpected reboot state"
  - "Scanner, inventory, CI or telemetry coverage failure"
  - "Expiry or invalidation of risk exception"
~~~

Các con số 132, 12, 120 và 72 trong mẫu **chỉ là ví dụ từ mục 6**, không phải kết quả scan hiện tại. Trường `assurance.result` không tự thành PASS vì coverage 60%; PASS/FAIL/INCONCLUSIVE phải được quyết định dựa trên **acceptance criteria đã phê duyệt cho metric quality/target và risk-specific hard stops**.

### 18.2. Traceability của một patch obligation

~~~text
RISK-PC-01:
  Internet-facing report service uses affected library version
  -> ASSET: report-api deployment and image digest
  -> REQUIREMENT: Upgrade to vendor-fixed version for advisory
  -> OBLIGATION: (report-api@deployment-17, PATCH-REPORT-PARSER)
  -> CONTROL: Dependency update + CI verification + rollout
  -> TEST: dependency graph, actual digest, exploit-path negative test
  -> EVIDENCE: source commit + build ID + image digest + rollout ID
  -> STATE: VERIFIED_EFFECTIVE or another explicit state
  -> COVERAGE: numerator only if actual-state evidence is valid
  -> FINDING: open if old image or worker still affected
  -> REMEDIATION: deploy remaining workload + retest
  -> MONITOR: new image rollout, registry/scan/source health
~~~

### 18.3. Evidence chất lượng cao phải chứng minh gì?

- **Identity:** chính xác asset/workload/service và patch requirement.
- **Applicability:** advisory/baseline version, affected/fixed semantics.
- **Implementation:** patch installed/published, change/version/commit/digest.
- **Effectiveness:** actual running kernel/process/image/fixed behavior trong scope.
- **Timing:** observedAt/cutoff, target deadline và source freshness.
- **Completeness:** inventory và expected population bao phủ đúng.
- **Consistency:** conflicting scanners/agents đã được reconcile.
- **Governance:** risk owner, exception, reviewer, finding history.
- **Integrity:** evidence storage/transport/retention được bảo vệ.

Không ghi raw credentials, token, private key hoặc dữ liệu khách hàng vào evidence. Dùng IDs, digests, sanitized logs và references tới hệ thống lưu trữ được phê duyệt.

## 19. Dashboard giúp người vận hành ra quyết định

Một dashboard cần trả lời **“tôi phải xử lý gì tiếp theo?”**, không chỉ trình bày số tổng.

### 19.1. Cấu trúc gợi ý

| Vùng hiển thị | Số liệu | Quyết định hỗ trợ |
| --- | --- | --- |
| Coverage tổng | Verified/eligible %, numerator/denominator | Xu hướng toàn scope |
| Critical public exposures | Unpatched/overdue count | Containment và ưu tiên |
| Unknown inventory | Unmanaged, stale, incomplete | Phục hồi visibility |
| Patch lifecycle | Missing, scheduled, pending restart, failed, rolled back | Hành động vận hành |
| Exceptions | Active, expiring, expired, rejected | Reassess/risk escalation |
| Deadline | Overdue, nearing due, fixed late | Remediation scheduling |
| Segment breakdown | Region, service, owner, patch cohort, image type | Tìm điểm nóng |
| Evidence quality | Freshness/source health/conflicts | Tin cậy phép đo |
| Regressions | Rollback, new affected assets, baseline drift | Reopen/contain |
| Remediation progress | Deployment waves, retest status | Close findings |

### 19.2. Không dùng một badge “green” để che risk

Ví dụ:
- Coverage = 99%.
- Critical Internet-facing unpatched = 1.
- Unknown agents = 20.
- Evidence freshness = 78%.

Mặc dù tỷ lệ coverage cao, kết luận risk **không được tự là PASS**. Phải trình bày limitations và issues có owner. Tỷ lệ 99% có thể không đáng tin nếu denominator chưa bao phủ unknown hosts.

### 19.3. Phân tích theo hướng hành động

Những câu hỏi hữu ích:
- Gap nào có risk/impact cao nhất?
- Bao nhiêu assets chỉ còn thiếu reboot?
- Cluster nào có nhiều failed deployments?
- Image digest cũ còn ở những workloads nào?
- Có new host nào được tạo từ golden image lỗi?
- Sources nào mất dữ liệu khiến UNKNOWN tăng?
- Có exception nào sắp hết hạn trước khi có patch rollout?
- Khi một patch cohort đã hoàn tất, số open findings còn liên quan là bao nhiêu?

## 20. Verification test plan cho patch coverage

| Test ID | Tình huống | Expected result |
| --- | --- | --- |
| **PC-T01** | Asset/patch verified effective, evidence fresh | Count numerator |
| **PC-T02** | Installed pending reboot | Eligible, không count numerator |
| **PC-T03** | Patch staged/downloaded chưa active | Không count numerator |
| **PC-T04** | Patch deploy FAILED | Không count numerator |
| **PC-T05** | Patch rollback về affected version | Trạng thái unpatched, coverage giảm |
| **PC-T06** | Not-applicable có evidence còn fresh | Exclude eligible, ghi riêng |
| **PC-T07** | Not-applicable không có evidence | Giữ denominator/UNKNOWN |
| **PC-T08** | Applicability unknown | Giữ denominator, không count patched |
| **PC-T09** | Agent/scanner offline, evidence stale | Không tự count patched |
| **PC-T10** | Evidence future timestamp | Không accept |
| **PC-T11** | Asset không có agent nhưng vẫn running | Có trong inventory/gap |
| **PC-T12** | CMDB retired nhưng cloud instance running | Reconcile, không tự exclude |
| **PC-T13** | Duplicate identity/obligation | Reject/dedupe có audit |
| **PC-T14** | Asset mới sinh từ old golden image | New unpatched obligation |
| **PC-T15** | Windows superseding KB chứa fix | Evaluate vendor state đúng |
| **PC-T16** | Linux distro backported patch | Verify fixed build/advisory, tránh false fail |
| **PC-T17** | Old kernel vẫn running sau package update | Không count patched khi patch cần reboot |
| **PC-T18** | Container image fixed đã build nhưng pod old digest | Không count production patched |
| **PC-T19** | New CronJob vẫn dùng vulnerable image | Detect future execution exposure |
| **PC-T20** | Node OS patched, app JAR vulnerable | App obligation vẫn unpatched |
| **PC-T21** | CI artifact fixed, production rollout incomplete | Chỉ replicas/deployments verified |
| **PC-T22** | Approved exception nhưng chưa patch | Không count technical numerator |
| **PC-T23** | No assets/obligations in verified scope | Coverage N/A, không 100% |
| **PC-T24** | Inventory population unknown/partial | Assessment INCONCLUSIVE/limitation |
| **PC-T25** | Scan agent PASS, scanner FAIL trên cùng runtime | Reconciliation finding |
| **PC-T26** | Vendor managed patch không có đủ evidence | Vendor assurance limitation/INCONCLUSIVE |
| **PC-T27** | Snapshot denominator đổi do autoscale | Report cohort/absolute counts, no misleading comparison |
| **PC-T28** | Critical unpatched asset trong fleet 99% | Escalation theo risk, không dựa % tổng |
| **PC-T29** | SLA deadline chưa tới nhưng patch chưa deploy | Unpatched; không tự overdue |
| **PC-T30** | Patch deploy sau deadline | Coverage hiện có tăng; lịch sử lateness còn |
| **PC-T31** | Source-health collector down và zero vulnerabilities | Không kết luận toàn fleet patched |
| **PC-T32** | Evidence ref không trùng asset/digest | Không accept verified effective |
| **PC-T33** | Patch rule/advisory cập nhật applicability | Recalculate affected cohort có version |
| **PC-T34** | Decommission verified, asset removed từ active scope | Document exclusion và preserve history |
| **PC-T35** | Exception expired, asset vẫn unpatched | Risk escalation; không đổi technical state |
| **PC-T36** | Effective patch verified ở staging nhưng không có prod evidence | Không tính production patched |

### Chạy test ở nhiều tầng

- **Unit:** denominator, numerator, statuses, freshness, duplicate handling, N/A.
- **Integration:** inventory joins, scanners, patch agents, cloud discovery, advisory rules.
- **System:** actual OS/kernel/application/container runtime, restart và rollback.
- **Security negative:** forged evidence, wrong deployment/digest, missing agent, unknown applicability, false exclusion.
- **Operational:** patch rollout waves, maintenance window, exception review và alert escalation.
- **Recovery:** agent/source outage, job retry, rollback, source reconciliation và retest.

Không cần gây outage hoặc reboot production trái quy trình để chứng minh controls. Sử dụng test instances, staging/canary và các phép kiểm thực tế **chỉ đọc** khi thích hợp; ghi rõ limitations của failure scenarios chưa thực hiện.

## 21. Vận hành: từ patch coverage gap tới remediation finding

Một dashboard không có người hành động thì chưa tạo thành chương trình assurance. Mỗi gap cần có **owner, next action, deadline và verification plan**.

### 21.1. Triage và phân luồng

| Gap | Primary owner gợi ý | Việc cần làm |
| --- | --- | --- |
| Asset không có inventory/agent | Platform/Asset owner | Discover, map identity, triển khai telemetry |
| Applicability UNKNOWN | Vulnerability/Patch analyst | Đối chiếu advisory, version/build, vendor evidence |
| Patch NOT_PATCHED | Service/Operations owner | Lập rollout, maintenance window, test |
| INSTALLED_PENDING_RESTART | Operations/SRE | Kiểm soát restart, xác minh running state |
| DEPLOY_FAILED | Release/Patch engineer | Root cause, retry/rollback an toàn |
| ROLLED_BACK | Change owner + Security | Đánh giá risk tái xuất hiện, treatment và replan |
| EOL/UNSUPPORTED | System/Business/Risk owner | Migration, isolation hoặc decommission plan |
| Critical exploited exposure | Security incident/risk escalation | Containment và remediation ưu tiên |
| Evidence stale/conflicting | Data/Control owner | Source-health, reconcile, verify actual state |
| Approved exception expiring | Risk owner + Remediation owner | Reassess, deploy fix hoặc revoke |

### 21.2. Một workflow thực dụng

~~~mermaid
flowchart TD
    SNAP["Inventory + patch/advisory snapshot"] --> CALC["Calculate coverage by versioned rules"]
    CALC --> GAP{"Unresolved/unknown/overdue?"}
    GAP -- "Không" --> MON["Maintain freshness and drift monitoring"]
    GAP -- "Có" --> PRI["Risk triage + owner"]
    PRI --> PATH{"Can patch within target?"}
    PATH -- "Có" --> CHANGE["Patch plan + canary + rollout"]
    PATH -- "Không" --> RISK["Mitigation/exception/escalation with evidence"]
    RISK --> CHANGE
    CHANGE --> OBS["Actual-state verification"]
    OBS --> DONE{"Requirement PASS?"}
    DONE -- "Không" --> FIND["Finding / root cause / rollback / retest"]
    FIND --> PRI
    DONE -- "Có" --> CLOSE["Close finding; update numerator with evidence"]
    CLOSE --> MON
    MON --> SNAP
~~~

### 21.3. Finding không đóng chỉ vì job success

Một finding xử lý patch chỉ được đóng khi:
- Verified target fixed state đã xuất hiện ở **actual runtime**.
- Không còn affected instances nằm trong claim scope hoặc các exceptions được theo dõi minh bạch.
- Required restart/reboot/rollout đã hoàn tất.
- Scan/advisory mapping và negative tests phù hợp.
- Evidence gắn source/artifact/deployment, timestamps, reviewer.
- Risk owner/assessor chấp nhận limitations hợp lý theo policy.

Ticket `Done`, CI `green`, installer exit code 0 hoặc change request `Closed` chỉ là **một phần** của evidence.

## 22. Case study 1 – Java/Spring Boot trên Kubernetes

### 22.1. Kiến trúc và sự cố

Ứng dụng báo cáo đa tenant có:
- `report-api` và `export-worker`.
- Java 17/Spring Boot, Maven dependency graph.
- Container registry và Kubernetes tại hai regions.
- Image base OS và một library parse report.
- CI/CD đã build image mới sau khi upgrade vulnerable dependency.
- Security scanner nói image mới không còn affected library.
- Deployment region A đã hoàn tất; region B vẫn còn một số pods cũ do rollout chưa kết thúc.
- Một CronJob tạo export workers từ template image cũ.

Tại thời điểm đánh giá, cohort của **20 running report-api pods** yêu cầu fixed application image:
- 15 pods chạy digest mới, có deployment/runtime verification.
- 3 pods đang restart/rollout.
- 2 pods vẫn dùng old digest.

Nếu coi **mỗi running pod là một obligation** trong cohort này:

~~~text
Eligible running-pod obligations = 20
Verified effective              = 15
Pending rollout/restart         = 3
Old vulnerable digest           = 2

Running-pod image patch coverage = 15 / 20 × 100 = 75%
~~~

**75% là patch coverage của 20 running-pod obligations được định nghĩa**, không phải “75% toàn bộ Kubernetes/application vulnerabilities đã được sửa”. CronJob template cũ là một **nghĩa vụ riêng cần theo dõi**; nodes cũng có baseline kernel riêng. Nếu claim bao gồm các workload có thể chạy trong tương lai, phải bổ sung CronJob và những template/controllers tương ứng vào scope.

### 22.2. Những sai lầm có thể xảy ra

- Chỉ kiểm CI scan và báo 100% production patched.
- Chỉ kiểm Deployment desired image nhưng không kiểm current pods.
- Kiểm region A rồi suy sang region B.
- Quên CronJob/import worker có dependency vulnerable.
- Dùng mutable tag `stable` thay vì image digest.
- Không kiểm tra rollback sau rollout failure.
- Không lưu evidence về actual runtime `imageID` và thời điểm.

### 22.3. Bảng kiểm theo layer

| Layer | Patch requirement | Evidence |
| --- | --- | --- |
| Java dependencies | Fixed affected library version, không còn old copy ở packaged artifact | Maven graph + artifact/SBOM + scan |
| Container base image | Fixed OS/library packages theo advisory | Immutable digest + image scan |
| Deployment | Actual running pod digest trùng approved image | Kubernetes runtime identity/status |
| CronJob | Template không tạo workload vulnerable | CronJob spec + new-job verification |
| Kubernetes node | Kernel/OS patches effective khi applicable | Node OS/running kernel + reboot |
| Worker jobs | Không có long-running worker dùng old JAR | Queue worker/process/deployment inventory |
| Rollback policy | Old image không tự được restore ngoài treatment | Rollback negative test + release approval |

### 22.4. Remediation plan

1. Gắn advisory, release digest, deployment/region và source commit vào patch obligations.
2. Hoàn thành rollout region B, kiểm tra readiness và running image IDs.
3. Sửa CronJob template; trigger controlled job để verify image nếu policy yêu cầu.
4. Kiểm tra export-worker và các runtime-loaded libraries.
5. Tái scan artifact và runtime inventory; reconcile conflicts.
6. Dừng sử dụng old image tag/digest cho rollback mặc định hoặc có controlled exception.
7. Đóng finding khi claim scope đã verify, cập nhật coverage snapshot có version.
8. Tiếp tục monitoring để phát hiện scale-up từ template cũ.

### 22.5. Assurance claim

> Trong phạm vi các report-api pods đang chạy và các controllers đã được inventory tại thời điểm đánh giá, mọi workload được đánh dấu VERIFIED_EFFECTIVE phải dùng đúng approved image digest chứa fixed parser release; observations được lấy từ actual Kubernetes status, đối chiếu với CI artifact và advisory mapping. Các chưa hoàn tất rollout, CronJobs và node/kernel obligations được báo riêng, không tự tính patched.

Claim chỉ đạt khi evidence minh chứng **từng scope**. Một tỷ lệ 75% không nói toàn hệ thống PASS về security.

## 23. Case study 2 – Hybrid VM fleet với pending reboot và EOL

### 23.1. Bối cảnh

Một tổ chức quản lý 50 VMs thuộc patch campaign, gồm Windows và Linux, với owner rõ. Kết quả từ patch platform:
- 30 VMs có effective patched state được verify trên runtime.
- 10 VMs đã cài package/update nhưng còn restart/reboot cần thiết.
- 5 VMs có deployment failures.
- 3 VMs offline và không có evidence đủ mới.
- 2 VMs dùng OS EOL, không còn patch supported.

Nếu doanh nghiệp xét một **baseline obligation cho mỗi VM trong campaign** và giữ cả EOL trong population cần xử lý, ta có:

~~~text
Eligible obligations = 50
Verified effective   = 30
Pending activation   = 10
Deploy failed        = 5
Unknown/stale        = 3
Unsupported/EOL      = 2

Coverage             = 30 / 50 × 100 = 60%
~~~

Ở đây việc giữ 2 EOL trong unresolved population nhằm tránh bỏ qua **risk obligations**. Nếu metric thuần “vendor patch applicability” không có patch tồn tại, cần trình bày EOL dưới **remediation/migration obligations riêng**, không làm sai mẫu số của patch-specific metric. Cách mô hình hóa phải được ghi rõ trong metric definition.

### 23.2. Vì sao báo “45/50 installed” sai?

Ví dụ patch platform có thể tính 30 verified + 10 pending + 5 failed job attempts là “processed”. Nhưng processed **khác** patched. 3 unknown và 2 EOL không thể biến mất khỏi báo cáo chỉ vì không có patch job.

### 23.3. Xử lý theo nhóm

| Nhóm | Tác vụ | Điều kiện đóng |
| --- | --- | --- |
| 30 verified | Duy trì evidence freshness và drift checks | Runtime còn đạt baseline |
| 10 pending reboot | Lên maintenance/restart, kiểm tra running state | Actual fixed state PASS |
| 5 failed | RCA, retry/alternative mitigation, change review | Deploy + verification |
| 3 unknown | Reconcile CMDB/cloud, khôi phục source hoặc kiểm trực tiếp | Fresh evidence/triage |
| 2 EOL | Migrate/replace/decommission/isolate theo risk | Evidence risk treatment và exit plan |

### 23.4. Critical exposure không được chờ tỷ lệ tổng

Giả sử một trong 5 failed VMs cung cấp Internet-facing authentication và có critical known exploited vulnerability. Dù coverage fleet tăng sau khi khởi động lại 10 máy khác, **critical exposure vẫn yêu cầu escalation/containment** theo chính sách.

### 23.5. Review sau thay đổi inventory

Nếu 4 VMs được decommission thật và 6 VMs mới được tạo, phải lưu:
- Asset/decommission evidence.
- VMs mới thuộc patch cohort nào.
- Baseline version và inventory cutoff.
- Tỷ lệ history cho cohort cũ và new snapshot.
- Không so sánh % nếu denominator rule hoặc asset population không đồng nhất.

## 24. Bài tập thực hành

### Bối cảnh

Bạn phụ trách một nền tảng microservices và hạ tầng cho hệ thống tài chính. Các nguồn dữ liệu:
- CMDB có 210 assets; cloud API có 218 running instances.
- Patch platform thấy 198 agents; 20 instances không có agent.
- Vulnerability scanner báo một số missing fixes, nhưng có Linux vendor backports.
- Windows update platform cho biết nhiều servers cần reboot.
- CI đã cập nhật base image nhưng hai Kubernetes namespaces vẫn chạy image cũ.
- Java service có một vulnerable transitive dependency.
- Một network appliance EOL không có fixed firmware.
- Risk owner phê duyệt exception cho một host trong phạm vi hẹp.
- Ở một region, scanner source health bị lỗi.

### Yêu cầu

1. Vẽ asset/patch evidence flow từ CMDB, cloud inventory, patch agent, scanner, artifact/CI và runtime.
2. Chọn **đơn vị đo**, baseline, scope, cutoff và freshness policy cho hai metrics: fleet OS patch coverage và application-image patch coverage.
3. Reconcile chênh lệch **210 vs 218 vs 198**, xác định nguồn authoritative cho những thuộc tính nào.
4. Định nghĩa trạng thái cho pending reboot, Linux backport, stale agent, EOL, exception và image digest mismatch.
5. Lập một bảng asset–patch obligations gồm ít nhất **15 dòng** với identity, applicability, status, evidence timestamp và source.
6. Tính numerator/denominator/coverage, nêu rõ cách xử lý UNKNOWN và NOT_APPLICABLE.
7. Đề xuất ít nhất **10 test cases** cho aggregation, actual patch effectiveness, source coverage và rollback.
8. Viết ít nhất **6 security requirements** truy về risk và controls.
9. Thiết kế dashboard có coverage %, absolute critical overdue count, unknown count, exceptions, freshness và pending-reboot.
10. Chứng minh rằng approved exception không tăng technical numerator.
11. Xác định đường khắc phục cho vulnerable Java library và Kubernetes old image.
12. Viết một evidence register theo YAML mẫu, có version/cutoff, patch baseline, actual deployment IDs và reviewer.
13. Lập kế hoạch xử lý khi một critical Internet-facing asset unpatched nhưng overall coverage lớn hơn 98%.
14. Xác định review triggers khi thêm VM, thay image, vendor phát hành backport, scanner mất nguồn hoặc rollback.
15. Viết scoped assurance claim có limitation, PASS/FAIL/INCONCLUSIVE và remediation/retest.

### Gợi ý giải

| Vấn đề | Hướng tiếp cận |
| --- | --- |
| CMDB và cloud không đồng nhất | Canonical identity, authoritative source theo field, reconcile |
| Agent thiếu | UNKNOWN/data quality gap; không bỏ denominator |
| Linux backport | Đối chiếu distro/vendor fixed build, không so lexical upstream version |
| Windows pending reboot | Installed chưa chắc effective |
| Image cũ | Verify runtime digest, không chỉ CI/build scan |
| Java transitive vulnerable | Resolved dependency graph + actual artifact/deployment |
| EOL appliance | Risk treatment/migration/unsupported metric riêng |
| Approved exception | Technical patched = false; risk/compliance view riêng |
| Scanner source down | Không có finding không nghĩa no vulnerability |
| 98% overall | Critical exposure count và risk escalation độc lập |

### Câu hỏi nâng cao

Một dashboard báo **100% patch coverage** vì tất cả 200 máy có agent đều trả “Patch installed”. Trong khi cloud inventory có thêm 18 instances không có agent, 12 Windows máy chưa reboot, và một Java service production vẫn chạy image digest cũ.

**Có thể kết luận 100% PATCHED không?**

**Định hướng:** không. Dashboard chỉ mô tả installation result từ population 200 visible agents. Nó chưa xác định đúng full asset inventory, required activation, application artifact và deployment. Cần xây lại eligible denominator, phân loại UNKNOWN và PENDING, xác minh runtime và báo coverage theo các units/scope tách biệt. Nếu inventory completeness chưa đủ thì security assurance claim **INCONCLUSIVE** dù deployment job dashboard xanh.

## 25. Những ngộ nhận thường gặp

| Ngộ nhận | Vì sao sai? | Thực hành phù hợp |
| --- | --- | --- |
| “Job success nghĩa là patched.” | Cài xong nhưng chưa active/rollback | Verify runtime |
| “Số máy có agent là toàn fleet.” | Unmanaged/unreachable assets bị loại | Inventory reconciliation |
| “Không có scan finding là đã vá.” | Missing source, rules, scan coverage | Data-quality và actual-state checks |
| “Đã download patch tức là effective.” | Chưa cài/restart | Tách lifecycle states |
| “Vá một host nghĩa là vá mọi service trên host.” | App/container deps độc lập | Layer-specific obligations |
| “CI image mới nghĩa là production dùng image mới.” | Old replicas/regions/CronJob | Actual deployed digest |
| “Kernel package mới nghĩa running kernel mới.” | Cần boot vào kernel | Runtime `uname -r` + vendor rules |
| “Thiếu Windows KB chắc chắn vulnerable.” | Cumulative update có supersedence | Effective servicing/build check |
| “Upstream version thấp luôn vulnerable trên Linux.” | Vendor security backport | Distro advisory mapping |
| “Approved exception là đã patched.” | Risk acceptance khác technical state | Tách risk/technical views |
| “EOL không có patch nên loại asset.” | Risk tồn tại, cần migration | Unsupported/migration tracking |
| “UNKNOWN thì nên xóa cho sạch mẫu số.” | Thổi phồng coverage | Giữ unresolved và confidence |
| “Denominator 0 nghĩa là 100%.” | Không có eligible không phải verified | Báo N/A hoặc INCONCLUSIVE |
| “Tỷ lệ cao nghĩa là risk thấp.” | Một critical exposure vẫn nguy hiểm | Segment theo risk/absolute gaps |
| “Patch đã từng hiệu lực thì mãi patched.” | Rollback/reimage/drift | Invalidate/refresh evidence |
| “Tính % tổng là đủ.” | Không biết owner/route/priority | Drill-down và actionable backlog |
| “Scanner và agent mâu thuẫn thì lấy nguồn xanh hơn.” | Có thể che failure | Evidence reconciliation |
| “Gộp CVE count với patch count.” | Quan hệ nhiều-nhiều | Nêu rõ metric unit |
| “Tất cả vendor services tự được patched.” | Thiếu visibility và shared responsibility | Vendor assurance/evidence limits |
| “SLA đúng hạn đồng nghĩa coverage 100%.” | Các nghĩa vụ chưa tới hạn chưa patched | Báo SLA và coverage riêng |
| “Ticket Done là finding closed.” | Chưa test runtime | Actual-state retest |
| “Dùng tag stable như digest.” | Tag mutable | Pin/verify immutable digest |
| “Fresh timestamp là evidence đủ.” | Source/digest mapping có thể sai | Provenance/identity/quality |
| “Một lần snapshot là liên tục.” | Fleet/advisory/exposure đổi | Monitoring/reassessment triggers |

## 26. Checklist dành cho patch coverage assurance

### Trước khi tính

- [ ] Đã xác nhận scope, owner, environment/region và snapshot cutoff.
- [ ] Đơn vị metric là asset, obligation, finding hay workload được ghi rõ.
- [ ] Có canonical asset inventory từ nhiều nguồn và reconciliation report.
- [ ] EOL/unmanaged/offline assets được theo dõi, không im lặng loại bỏ.
- [ ] Patch baseline, vendor advisory, applicability rules có version.
- [ ] Verified not applicable có evidence; unknown vẫn hiện diện.
- [ ] Dữ liệu có freshness policy, source-health và timestamp đáng tin.
- [ ] Không dùng installed/downloaded/assigned như effective nếu chưa đạt criteria.
- [ ] Bao phủ OS, middleware, app dependency, image, node và worker theo scope.

### Trước khi công bố

- [ ] Tử số, mẫu số, exclusion và công thức minh bạch.
- [ ] Denominator 0 hiển thị N/A; inventory unknown hiển thị INCONCLUSIVE.
- [ ] Tách technical coverage, SLA compliance, exceptions và mitigation.
- [ ] Báo absolute critical/known exploited/overdue gaps.
- [ ] Báo UNKNOWN, stale evidence và scan/source health.
- [ ] Đã reconcile conflicting observations và version mapping.
- [ ] Kết quả theo region/owner/criticality có drill-down.
- [ ] Báo metric definition/version, baseline và cutoff.

### Sau rollout và khi review

- [ ] Deployment/reboot/rollout verified trên actual runtime.
- [ ] Old images/replicas/jobs và rollback cases đã được kiểm tra.
- [ ] Risk findings/overdue gaps có owner, deadline, treatment.
- [ ] Exceptions có authority, scope, expiry và không tăng numerator.
- [ ] Findings chỉ đóng sau verified remediation và retest.
- [ ] New asset, new advisory, patch supersedence, rollback và monitoring outage kích hoạt reassessment.
- [ ] Evidence register gắn commit/digest/deployment/asset/time/reviewer.
- [ ] Báo hạn chế, gaps, false positives/backports và nguồn nào chưa kiểm.

## Ghi nhớ

- **Patch coverage chỉ có ý nghĩa khi biết đang đo trên tập tài sản/nghĩa vụ nào**, với baseline, snapshot, tử số, mẫu số và source evidence minh bạch.
- Nên phân biệt **asset coverage, asset–patch obligation coverage, vulnerability remediation coverage, deployment success và SLA compliance**; không gộp thành một tỷ lệ chung sai ngữ nghĩa.
- Một nghĩa vụ chỉ vào **verified patched numerator** khi có bằng chứng trạng thái sửa lỗi **đã hiệu lực trên đúng runtime** và còn phù hợp.
- Pending reboot, downloaded, scheduled, failed, rolled back, exception và UNKNOWN **không tự được coi là patched**.
- **Verified not applicable** có thể loại khỏi eligible denominator theo rule; unknown/stale/unmanaged không được tự loại để làm đẹp metric.
- Coverage cao không loại trừ **một critical exploited exposure**; cần phân tích theo risk segments và absolute overdue counts.
- Java dependency, container image, Kubernetes deployment, node OS, firmware và managed service có **mô hình applicability/verification khác nhau**.
- Evidence cần có identity, source, observation time, patch/baseline rule, actual artifact/deployment digest, freshness, completeness, reviewer và limitation.
- Approved exception giảm/nhận residual risk theo thẩm quyền, **không sửa technical patch coverage**; remediation vẫn cần milestone và retest.
- Trong **SECURITY_SECURITY_ASSURANCE**, quản lý liên tục **risk → requirement → patch obligation → deployment → verification → evidence → finding → remediation/retest** là điều làm coverage có giá trị kiểm toán.


# Patch hệ điều hành: quản lý bản vá OS và chứng minh mức độ khắc phục rủi ro

## Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích **patch hệ điều hành** và phân biệt cập nhật **kernel, gói hệ thống, thư viện, dịch vụ OS, driver, firmware, bản vá bảo mật và nâng cấp phiên bản** với các hình thức giảm thiểu tạm thời.
2. Xác định đúng **population tài sản** phải vá: máy vật lý, máy ảo, hệ điều hành khách, node Kubernetes, container host, máy chủ quản trị, máy trạm, hệ thống offline và các golden images.
3. Tiếp nhận thông báo bảo mật, ánh xạ bản vá tới **OS version, package/build, component và mức độ phơi nhiễm**, rồi ưu tiên theo rủi ro thay vì chỉ dựa vào điểm CVSS.
4. Thiết kế quy trình **inventory → advisory intake → applicability → risk decision → staging/test → approval → rollout → reboot/activation → verification → evidence → follow-up**.
5. Áp dụng cách triển khai khác nhau cho **Linux, Windows và macOS**, đồng thời hiểu giới hạn của package manager, management agents, live patching và các tín hiệu “update installed”.
6. Phân tích **availability, compatibility, rollback, backup, cluster quorum, workload draining, immutable replacement** và xử lý khẩn cấp khi có khai thác đang diễn ra.
7. Viết **security requirements có thể kiểm thử**, thiết kế negative/failure-path tests và kiểm chứng hệ thống **thực sự chạy bản đã vá**, không chỉ có lệnh cài đặt thành công.
8. Xây dựng **assurance evidence**, phân biệt trạng thái PASS/FAIL/UNKNOWN/EXCEPTION, đo coverage có mẫu số đúng, và tổ chức cải tiến patch management liên tục.

Trong module **SECURITY_SECURITY_ASSURANCE**, mục tiêu là xây dựng cách **đánh giá có bằng chứng** rằng hệ thống đáp ứng những mục tiêu bảo mật, từ phân tích rủi ro, yêu cầu và security controls tới kiểm thử, audit và khắc phục findings. Chủ đề **Patch hệ điều hành** thuộc chương **Patch management** đặt câu hỏi: **Với những tài sản có nguy cơ bị khai thác, bằng chứng nào chứng minh bản sửa lỗi thích hợp đã được triển khai, được kích hoạt và vẫn đang vận hành an toàn trong đúng phạm vi?**

> **Nguyên tắc cốt lõi:** “Đã chạy công cụ update” khác với “đã vá và hết phơi nhiễm”. Một máy có thể tải bản vá nhưng chưa khởi động lại, một node có thể khởi động nhưng quay lại image cũ, một thư viện có thể được cập nhật trên đĩa nhưng tiến trình vẫn giữ bản cũ, hoặc một máy ngoài inventory hoàn toàn chưa được xử lý. Assurance cần kiểm tra **applicability, trạng thái thực thi, phiên bản hiệu lực, độ bao phủ, bằng chứng và rủi ro còn lại**.

## 1. Patch hệ điều hành là gì và bảo vệ cái gì?

**Operating system patching** là việc áp dụng những thay đổi được nhà cung cấp hoặc nguồn phân phối được tổ chức tin cậy phát hành nhằm sửa lỗi bảo mật, lỗi chức năng hoặc ổn định của các thành phần OS; sau đó xác minh thay đổi đã có hiệu lực và không làm vi phạm những yêu cầu vận hành/bảo mật khác.

Trong bối cảnh security assurance, cần phân biệt:

| Loại thay đổi | Ví dụ | Điểm kiểm chứng |
|---|---|---|
| **Security patch** | Sửa lỗi leo thang đặc quyền, xử lý gói mạng hoặc service của OS | Advisory, applicability, fixed version, effective state |
| **Kernel update** | Cập nhật kernel package/build | Kernel đang chạy, trạng thái reboot/livepatch |
| **Userspace system package** | Cập nhật thư viện crypto, SSH daemon, systemd hoặc runtime OS | Package version và tiến trình/dịch vụ đang dùng thư viện |
| **Windows cumulative/security update** | Bản cập nhật Windows theo sản phẩm/build/KB | Update applicability, installed build/KB, reboot pending |
| **macOS system/security update** | Bản cập nhật hệ điều hành, cơ chế bảo vệ tích hợp | OS build/version, policy compliance, restart trạng thái |
| **Driver update** | Network/storage driver ảnh hưởng kernel | Tính tương thích, driver version có hiệu lực |
| **Firmware/UEFI/microcode** | BIOS, CPU microcode, platform firmware | Platform vendor policy, effective firmware/microcode version |
| **Major/minor OS upgrade** | Đổi nhánh hoặc release của hệ điều hành | Support lifecycle, application compatibility, migration |
| **Configuration mitigation** | Tắt dịch vụ yếu, giới hạn cổng, giảm quyền | Effective config và khả năng giảm rủi ro trong khi chờ patch |
| **Image replacement** | Tạo VM/container-host image mới rồi thay node | Running instance image/digest, kernel và config thực |

**Không gộp tất cả vào một thao tác “cập nhật hệ thống”.** Một CVE có thể được sửa ở **package backport** với số phiên bản upstream trông “cũ”; hoặc bản vá kernel được cài nhưng kernel hiện chạy vẫn chưa thay. Cần dựa vào **vendor advisory và release metadata** của distribution/OS tương ứng, không chỉ so version string chung.

### 1.1. Các mục tiêu bảo mật

Patch OS có thể giảm:

- **Confidentiality risk:** lỗ hổng cho phép đọc bộ nhớ, files hoặc credentials trái phép.
- **Integrity risk:** leo thang quyền từ user thường tới root/SYSTEM, sửa dữ liệu hoặc policy.
- **Availability risk:** kernel panic, remote crash hoặc DoS qua network stack.
- **Isolation risk:** thoát container/VM, phá namespace, hypervisor/guest boundary.
- **Supply-chain risk:** update lấy từ nguồn không đáng tin, bị thay package, mirror hoặc signing keys.
- **Assurance gap:** không biết tài sản đang chạy gì, có đúng trạng thái được tuyên bố hay không.

Patch management **không thay thế** hardening, least privilege, firewall, EDR, backup, monitoring và secure architecture. Một hệ điều hành mới vá vẫn có thể có cấu hình quản trị yếu hoặc credentials bị chiếm.

### 1.2. OS patch khác application patch

Đường trách nhiệm thường đan xen:

- Host OS kernel, libc, SSH, system services do **OS/platform team** quản lý.
- Application libraries nằm trong build artifact hoặc container image có thể do **app team** quản lý.
- Node OS của managed service có thể do **cloud provider** quản lý một phần.
- Guest OS trong VM có thể vẫn do **khách hàng** quản lý dù hypervisor do cloud provider vận hành.
- Embedded/OT devices có quy trình vendor firmware đặc thù.

Không được tự suy “cloud đã vá” nghĩa là **guest OS, container host, container base image và ứng dụng** đều đã được cập nhật. Cần có responsibility matrix từng lớp.

### 1.3. Patch, compensating control và risk acceptance

Một bản vá có thể chưa sẵn hoặc chưa an toàn để triển khai tức thì. Khi đó:

1. **Mitigation tạm thời:** chặn đường khai thác, tắt chức năng có rủi ro, isolate endpoint, giảm quyền.
2. **Detection/monitoring:** phát hiện exploitation attempts hoặc dấu hiệu compromise.
3. **Risk decision:** owner và thời hạn được phê duyệt.
4. **Remediation plan:** triển khai patch/replacement khi đáp ứng điều kiện.
5. **Retest:** xác minh bản vá và gỡ mitigation tạm theo quy trình.

**Mitigated ≠ patched.** Một exception có compensating controls không được báo cáo như thể package/kernel đã được vá.

## 2. Những đối tượng nào thuộc phạm vi patch OS?

### 2.1. Phân nhóm tài sản

| Nhóm tài sản | Điểm dễ bỏ sót | Control owner điển hình |
|---|---|---|
| **Physical servers** | Firmware, driver, out-of-band management | Infrastructure/platform |
| **Virtual machines** | Guest OS, snapshots, stopped VMs, templates | VM/platform owner |
| **Cloud VMs** | Auto scaling instances, OS images, orphaned disks | Cloud/platform owner |
| **Kubernetes workers** | Node OS, kernel, container runtime, CNI, rolling replacement | Cluster/node owner |
| **Containerized workloads** | Base image/userspace là artifact riêng, host kernel dùng chung | App image owner + cluster owner |
| **Bastions và jump hosts** | Tài sản ít nhưng có đặc quyền cao | Identity/infrastructure owner |
| **Domain controllers / identity servers** | Reboot, replication và authentication dependencies | Directory/identity owner |
| **Security infrastructure** | Vulnerability scanners, log collectors, EDR management, KMS connectors | Security operations/platform |
| **Developer laptops/workstations** | Offline devices, local privilege, device posture | Endpoint/IT owner |
| **Golden images/templates** | Máy mới tạo lại bị lỗi cũ | Image factory owner |
| **Offline/isolated nodes** | Không nhận advisory, update agent và telemetry thường xuyên | Asset/business owner |
| **Vendor/managed devices** | Không có quyền patch trực tiếp | Vendor manager + risk owner |

### 2.2. Asset inventory phải trả lời được gì?

Mỗi tài sản cần tối thiểu:

- **Asset ID ổn định**, owner và môi trường: production/staging/dev.
- OS family, edition, release, architecture, build, distribution/channel.
- Vai trò nghiệp vụ, criticality, dữ liệu, user exposure và network accessibility.
- Patch/update source, management group, agent health và quyền áp update.
- Baseline/version policy, support/end-of-support state.
- Kernel/OS build đang chạy, package versions liên quan.
- HA group, cluster, maintenance window, reboot/replacement policy.
- Image/template lineage và deployment method.
- Last scan/inventory check, last verified patch state, evidence reference.
- Reason của **excluded, unsupported, unreachable hoặc unknown** assets.

**Inventory là mẫu số của coverage.** Nếu không biết tổng số VMs, endpoints, worker nodes và stopped images, không thể kết luận “đã vá 100%”.

### 2.3. Phân biệt các trạng thái tài sản

| Trạng thái | Ý nghĩa | Có thuộc population không? |
|---|---|---|
| **Running and managed** | Đang hoạt động, agent/telemetry kết nối | Có |
| **Running but unmanaged** | Đang chạy, không có update pipeline đủ | Có và là gap |
| **Stopped but retained** | VM/tài sản có thể được bật lại | Cần policy về patch trước khi chạy |
| **Ephemeral instance** | Có thể biến mất/tạo lại trong thời gian ngắn | Cần kiểm tra image factory và running fleet |
| **Template/golden image** | Dùng tạo tài sản mới | Cần quản lý freshness và lifecycle |
| **Unsupported/EOL OS** | Không còn nhận bảo vệ như mục tiêu yêu cầu | Risk finding/migration; không mặc định N/A |
| **Isolated/offline** | Không kết nối patch service | Vẫn phải có quy trình, owner và chứng cứ |
| **Provider-managed** | Một số lớp do vendor chịu trách nhiệm | Cần boundary và provider evidence |
| **Unknown OS/build** | Không xác định được applicability | Không được coi compliant |
| **Decommissioned and verified** | Đã ngừng dùng theo bằng chứng đáng tin | Có thể loại khỏi mẫu số sau quyết định |

### 2.4. Reconcile nhiều nguồn inventory

CMDB, cloud API, hypervisor, Kubernetes control plane, MDM, vulnerability scanner, EDR và patch agents **không tự động có cùng population**.

Một quy trình hợp lý:

1. Thu thập assets từ nguồn hạ tầng/runtime.
2. So với CMDB, patch agent roster và vulnerability scans.
3. Tìm assets không có owner, không chạy agent hoặc scan đã quá cũ.
4. Phân loại host đã xóa, stopped, ephemeral hoặc không truy cập được.
5. Giao owner làm rõ phần chênh lệch; lưu đối chiếu và thời gian.

Với auto scaling và container hosts, cần tính cả **image đã dùng để tạo node**, vì vá từng node nhưng để image cũ sẽ khiến lỗi tái xuất hiện khi scale out.

## 3. Từ thông báo lỗ hổng đến xác định patch applicability

### 3.1. Các nguồn thông tin cần đối chiếu

Thông tin thường đến từ:

- **OS/vendor security advisories** và update catalogs chính thức.
- Distribution security notices và package changelogs liên quan.
- Vulnerability scanner/asset detection/EDR findings.
- CVE database và các thông tin kỹ thuật có căn cứ.
- Thông tin khai thác trong thực tế, chẳng hạn **CISA Known Exploited Vulnerabilities (KEV)** khi áp dụng.
- Các tín hiệu ưu tiên như **CVSS, EPSS**, threat intelligence và incident reports.
- Product/asset inventory, service dependency và network exposure.

Lưu ý những danh sách/tín hiệu này **không cùng chức năng**:

| Tín hiệu | Ý nghĩa | Giới hạn |
|---|---|---|
| **CVE** | ID cho một lỗ hổng được công bố | Chưa nói asset này có bị ảnh hưởng không |
| **Vendor advisory** | Product versions, affected/fixed builds, mitigations | Phải chọn đúng vendor/product/distribution |
| **CVSS** | Mức độ nghiêm trọng theo đặc tính scoring | Không tự đo xác suất khai thác ở môi trường này |
| **EPSS** | Tín hiệu dự đoán xác suất lỗ hổng bị khai thác trong khoảng dự báo của mô hình | Là ước lượng, không phải bằng chứng asset bị exploit |
| **KEV** | Danh mục những CVE được biết đã bị khai thác ngoài thực tế | Không liệt kê trong KEV không đồng nghĩa an toàn |
| **Scanner finding** | Công cụ nhận diện dấu hiệu asset chịu ảnh hưởng | Có thể sai, thiếu credential, backport không được nhận |
| **Asset exposure** | Dịch vụ có thể bị truy cập bởi attacker nào | Cần kiểm tra thực tế network và trust boundaries |
| **Compensating controls** | Đường tấn công nào tạm bị giảm? | Không đồng nghĩa lỗ hổng đã được vá |

**Không tự biến “CVSS cao” thành deadline cố định** cho mọi tài sản. Thời hạn xử lý cần tuân theo policy được phê duyệt, tình hình khai thác và business risk.

### 3.2. Applicability có ít nhất ba lớp

1. **Vulnerable product/component:** OS/package/driver có thuộc affected range theo vendor không?
2. **Vulnerable code present and active:** Thành phần bị lỗi có được cài, kích hoạt hoặc có trong runtime không? Với kernel, phải nhìn vào phiên bản đang boot và điều kiện ảnh hưởng.
3. **Attack path/exposure:** Attacker có khả năng tiếp cận những điều kiện khai thác trong môi trường này không?

Chỉ cần hai điều đầu thường đủ để **lập kế hoạch khắc phục lỗ hổng**; điều thứ ba giúp ưu tiên rủi ro, không phải lý do tự động miễn vá. Một service hiện không internet-facing vẫn có thể bị khai thác sau lateral movement hoặc qua nội bộ.

### 3.3. Distribution backport và version confusion

Trong Linux doanh nghiệp, vendor có thể **backport bản sửa lỗi** vào package vẫn giữ số upstream version trông cũ. Vì vậy:

- Không so sánh máy móc `upstream-version < fixed-version` rồi kết luận vulnerable.
- Xác minh package release/build của **distribution và patch channel đúng**.
- Dùng vendor advisory, package metadata và scanner có hỗ trợ distro backport.
- Nếu tool báo conflicting result, đánh dấu **needs investigation** và lưu tài liệu mapping.

Tương tự, Windows có các cumulative updates/supersedence; không phải lúc nào thiếu một KB cũ cũng có nghĩa máy chưa nhận **bản cumulative mới hơn có chứa fix**. Phải xét **sản phẩm/build/KB applicability và supersedence**.

### 3.4. Trường hợp không có patch

Với lỗ hổng chưa có fix:

- Lập danh sách assets và attack surfaces cụ thể.
- Áp mitigations từ nguồn đáng tin khi phù hợp.
- Giảm exposure, loại bỏ dịch vụ dễ khai thác, theo dõi IOC/detection.
- Ghi risk owner, review cadence và điều kiện chuyển sang patch ngay khi có.
- Kiểm tra hiệu quả mitigation bằng config/runtime tests.

Không đặt trạng thái **PATCHED** cho những assets chỉ giảm thiểu tạm thời.

## 4. Ưu tiên bản vá theo rủi ro

### 4.1. Các yếu tố ra quyết định

Một triage record nên xét:

- **Exploit evidence:** Đã bị khai thác rộng rãi, khai thác có xác nhận hoặc chỉ mới proof-of-concept?
- **Exploit preconditions:** Network access, authentication, user interaction, privileges, local/remote?
- **Asset criticality:** Identity infrastructure, production data, Internet-facing gateway, admin workstation?
- **Data sensitivity và impact:** Confidentiality, integrity, availability, regulatory exposure?
- **Reachability/exposure:** Public endpoint, partner-facing, internal privileged network, disconnected device?
- **Prevalence:** Bao nhiêu máy/hệ thống, có reusable image hoặc shared dependency?
- **Mitigations:** Có controls đã xác minh đủ giảm attack path không?
- **Patch availability/reliability:** Vendor fix, compatibility warnings, prerequisites, observed regressions?
- **Operational impact:** Reboot duration, failover, cluster quorum, maintenance windows, testing complexity?
- **Compromise suspicion:** Có dấu hiệu exploitation đòi hỏi incident response song song không?

### 4.2. Minh họa mô hình ưu tiên

| Trường hợp | Tín hiệu | Hướng xử lý thường hợp lý |
|---|---|---|
| Network service có exploit thực tế, exposed ra Internet | Khả năng khai thác và tác động cao | Khẩn cấp: isolate/mitigate, patch/cutover nhanh theo phê duyệt |
| Kernel local privilege escalation trên bastion dùng nhiều admin | Tác động tới quyền đặc biệt | Ưu tiên cao, kiểm tra reboot và actual kernel |
| Thư viện yếu trên tài sản offline không có đường khai thác hiện tại | Exposure thấp nhưng vẫn vulnerable | Kế hoạch theo policy, kiểm chứng isolation và reconsider khi exposure đổi |
| Bản vá có regression trên cluster critical | Availability risk đáng kể | Canary/test/rolling; mitigation và exception có hạn nếu cần |
| OS hết hỗ trợ, không còn vendor fix | Không có đường vá đáng tin | Migration/isolation và risk decision, không coi compliant |
| CVE được scanner phát hiện sai do distro backport | Công cụ thiếu release mapping | Verification bằng vendor advisory; ghi false-positive disposition có chứng cứ |

### 4.3. Không gắn nhãn “critical” là tự động “cài ngay không kiểm thử”

Rủi ro khai thác và rủi ro gián đoạn **cùng cần được quản lý**. Trong tình huống emergency:

- Rút ngắn hoặc thay phương pháp test nhưng không bỏ **preflight và safe rollout** nếu có thể.
- Cô lập/phòng ngừa exploitation ngay trong lúc chuẩn bị.
- Dùng canary hoặc blue/green nếu kiến trúc hỗ trợ.
- Có rollback/fail-forward decision và monitoring rõ.
- Chỉ sử dụng exception theo thẩm quyền.

Không duy trì một server Internet-facing đang bị khai thác chỉ vì chưa đến lịch patch định kỳ; đồng thời cũng không vô tổ chức làm sập toàn bộ cluster bằng reboot hàng loạt.

## 5. Vòng đời patch management và trạng thái

### 5.1. Luồng công việc

~~~mermaid
flowchart TD
    A["Asset inventory + OS baseline"] --> B["Vendor advisories + vulnerability intel"]
    B --> C["Applicability + exposure + risk triage"]
    C --> D{"Fix available and applicable?"}
    D -- "No" --> E["Mitigation + risk decision + monitor"]
    E --> B
    D -- "Yes" --> F["Compatibility / backup / rollback plan"]
    F --> G["Approval + staged canary tests"]
    G --> H{"Safety and acceptance gates pass?"}
    H -- "No" --> I["Finding / hold / revise rollout"]
    I --> F
    H -- "Yes" --> J["Rolling deployment / image replacement"]
    J --> K["Reboot or activation as required"]
    K --> L["Verify running version + service + security state"]
    L --> M{"Expected outcomes met?"}
    M -- "No" --> N["Investigate / rollback or fail-forward / retest"]
    N --> J
    M -- "Yes" --> O["Evidence + fleet coverage + closure review"]
    O --> P["Drift monitoring / next advisory / revalidation"]
    P --> A
~~~

### 5.2. Không nhầm trạng thái “đã cài” với “đã khắc phục”

| Trạng thái tài sản | Ý nghĩa | Có thể coi verified patched? |
|---|---|---|
| **DISCOVERED** | Đã thấy asset nhưng chưa triage | Không |
| **NOT_APPLICABLE** | Có căn cứ vendor/asset cho thấy không chịu ảnh hưởng | Không phải patched; loại khỏi mẫu affected có lý do |
| **AFFECTED_PENDING** | Bị ảnh hưởng, chưa xử lý | Không |
| **MITIGATED_ONLY** | Có biện pháp tạm, chưa cài/activate fix | Không |
| **SCHEDULED** | Đã đặt lịch và owner | Không |
| **DOWNLOAD/INSTALL_STARTED** | Đang tải/cài | Không |
| **INSTALLED_PENDING_REBOOT** | Bản vá cài nhưng chưa active đầy đủ | Không, trừ claim đặc thù được chứng minh |
| **REBOOTED_UNVERIFIED** | Có reboot nhưng chưa xác minh phiên bản/health | Không |
| **VERIFIED_PATCHED** | Fixed state đang hiệu lực, coverage và health đã kiểm tra | Có, trong scope/version/time |
| **FAILED** | Cài đặt/boot/health/test thất bại | Không |
| **EXCEPTION_ACTIVE** | Có exception còn hiệu lực và mitigations | Không |
| **UNREACHABLE/UNKNOWN** | Không đủ telemetry để xác minh | Không |
| **REPLACED/DECOMMISSIONED** | Asset không còn hoạt động sau cutover có evidence | Xử lý theo inventory policy, không gọi “patched” máy cũ |

### 5.3. Quy tắc đóng một finding

Một finding “OS có lỗ hổng X” có thể được đóng sau khi:

1. Đúng asset/product/version được xác định.
2. Fix/mitigation được chấp thuận cho tình huống này.
3. Fix **đã triển khai và active**, hoặc asset đã được loại bỏ/không còn affected theo bằng chứng phù hợp.
4. Scanner/vendor evidence và runtime state được đối chiếu; false positive được giải thích.
5. Không còn regression trái yêu cầu bảo mật/vận hành.
6. Verification result, reviewer, thời điểm và scope được ghi.

Nếu dùng exception: để **exception tracked** và ghi residual risk, không báo “bản vá PASS”. Nếu finding có nhiều tài sản, không đóng toàn bộ chỉ vì một máy đã được cài.

## 6. Preflight trước khi vá

### 6.1. Điều kiện sẵn sàng

Trước maintenance window, cần xác nhận:

1. **Asset identity:** Không thao tác nhầm máy, region, tenant, environment hoặc cluster.
2. **Package/update source:** Update repository, package signature và vendor/channel được phê duyệt.
3. **Applicability:** Build/OS edition, architecture, prerequisites và dependency được kiểm tra.
4. **Change approval:** Change ID, scope, owner, approver và emergency route nếu áp dụng.
5. **Workload impact:** Services, SLO, khả năng failover, database/queue draining, dependencies.
6. **Capacity:** CPU/RAM/disk cho download/install, backup và swap/boot partition.
7. **Backup/recovery:** Có bản backup/snapshot phù hợp và **đã biết cách restore**; có người chịu trách nhiệm.
8. **Rollback/fail-forward:** Có phương án thực sự khả thi cho từng loại update.
9. **Monitoring:** Health checks, metrics, log pipeline và người trực theo dõi sẵn sàng.
10. **Credentials:** Automation có least privilege, không ghi mật khẩu/key vào scripts hoặc log.
11. **Communication:** Thông báo downtime/rủi ro và escalation theo business requirements.
12. **Security invariants:** Sau patch phải giữ IAM, firewall, encryption, audit, attestation và policy.

### 6.2. Kiểm tra compatibility

Chính sách kiểm thử nên xét:

- Thay kernel có làm ảnh hưởng driver storage/network, eBPF, EDR/observability agents, kernel modules hoặc GPU không?
- Bản vá crypto library có thay behavior TLS, certificate, cipher policies hoặc FIPS-related constraints không?
- OS service manager thay có ảnh hưởng startup order, daemon sockets hoặc permissions?
- Update có thay defaults, config file hoặc quyền truy cập tài nguyên?
- Database/storage drivers có tương thích kernel/firmware mới?
- Application dependencies có cần restart dù package manager báo completed?
- Patch có yêu cầu **multi-step upgrade** hoặc prerequisites trước khi nhận fix?
- Với Windows, có servicing stack/build prerequisites, edition và servicing channel phù hợp?

Một bản vá có thể sửa CVE nhưng làm gãy **bảo đảm bảo mật** nếu audit agent không khởi động, disk encryption không unlock hoặc policy trở về giá trị mặc định.

### 6.3. Backup không đồng nghĩa rollback hoàn chỉnh

Một VM snapshot có thể có hạn chế:

- Consistency của ứng dụng/database không được bảo đảm chỉ nhờ snapshot.
- Rollback OS có thể làm không khớp schema, external state hoặc security keys.
- Snapshot lâu tồn tại chứa secrets/data nhạy cảm hoặc OS version vulnerable.
- Restore có thể gây duplicate transactions/old permissions.
- Không phải hệ thống nào cũng cho rollback package/kernel dễ dàng.

Vì thế cần **recovery plan theo workload**: rollback bản vá khi supported, boot vào kernel trước theo quy trình, restore VM/image, recreate node từ golden image, hoặc **fail-forward**. Mọi phương án phải xem xét **state consistency, security consequences và downtime**.

### 6.4. Đặc biệt với cụm HA

Với load-balanced services:

1. Xác nhận đủ capacity khi rút một node.
2. Drain traffic và long-running requests đúng policy.
3. Vá/cập nhật node canary.
4. Reboot/replace, kiểm tra OS version và service functionality.
5. Đưa node trở lại pool khi health/security gates PASS.
6. Tiến hành lần lượt các node còn lại theo budget đã phê duyệt.

Với các hệ thống có **quorum** (database cluster, consensus store, domain controllers), việc reboot đồng thời quá nhiều nodes có thể làm mất khả dụng hoặc dữ liệu. Cần biết **quorum threshold và replication lag**, không dùng một kịch bản rolling chung cho mọi topology.

## 7. Xây các đợt rollout và maintenance policy

### 7.1. Canary, wave và kiểm soát blast radius

Một cách triển khai theo làn:

| Wave | Mục tiêu | Điều kiện đi tiếp |
|---|---|---|
| **Lab/test image** | Xác minh bản vá, dependencies và test tự động | Build/install/boot/test PASS |
| **Canary representative** | Kiểm chứng trên một subset nhỏ đại diện production | Security + functional + telemetry gates |
| **Noncritical production** | Kiểm tra tương tác fleet và scaling | Không có regression trọng yếu, coverage đối chiếu |
| **Critical services theo HA group** | Rolling patch có draining/failover | SLO/quorum/health và OS state đạt |
| **Remote/offline/special assets** | Áp quy trình riêng cho tài sản khó tiếp cận | Approved plan/evidence, không bỏ sót |
| **Closure/reconciliation** | Đối chiếu tất cả affected assets | Verified state, findings và exceptions |

**Canary “đã cài được” chưa đủ:** Phải kiểm tra reboot/activation, runtime kernel, network, storage, authentication, monitoring, encryption và chức năng nghiệp vụ liên quan.

### 7.2. Admission gates

Chỉ tiếp tục rollout nếu:

- Bản vá đúng source và target OS/package.
- Cài đặt không gặp lỗi ảnh hưởng scope.
- Đã reboot/restart/recreate khi cần.
- Kernel/build/package **đang hiệu lực** thuộc fixed state theo vendor.
- Dịch vụ và dependencies quan trọng khỏe; security invariants còn áp dụng.
- Monitoring không phát hiện regression/incident.
- Bằng chứng canary đủ để đối chiếu cùng release/config.

Nếu gate FAIL: **dừng wave**, phân tích rollback/fail-forward và ghi finding. Không bỏ qua test chỉ vì dashboard “install success rate” đẹp.

### 7.3. Maintenance window không phải lý do bỏ deadline

Một lịch patch cố định giúp quản trị availability, nhưng:

- Lỗ hổng khai thác tích cực có thể cần xử lý ngoài lịch.
- Asset không thể reboot ngay cần approved mitigation, exception và kế hoạch rõ.
- Patch có dependency tới reboot có thể phải đặt khoảng thời gian riêng.
- Tránh “infinite defer” khiến máy luôn nằm trong `pending reboot`.

Định nghĩa **ngày bắt đầu và deadline** theo một mốc rõ: vendor disclosure, vulnerability detection, policy assignment hoặc risk decision? Đảm bảo metrics không bị thao túng bằng cách đổi mốc khi quá hạn.

### 7.4. Immutable infrastructure và image factory

Với fleet ephemeral:

1. Build **golden image** từ approved base.
2. Cài các OS patches cần thiết từ verified source.
3. Test security/functional/boot và ghi image identifier.
4. Rollout instances mới từ image đã phê duyệt.
5. Drain và thay instances chạy image cũ.
6. Xác minh **runtime fleet** không còn affected image.
7. Chặn auto scaling quay lại image cũ và cập nhật launch templates/node pools.

Điểm quan trọng: **golden image đã vá không chứng minh fleet đã vá** nếu nodes cũ chưa được thay. Ngược lại, vá nodes tại chỗ nhưng image factory chưa cập nhật sẽ khiến rủi ro tái xuất hiện khi scale/recovery.

## 8. Triển khai patch trên Linux

### 8.1. Xác định đúng distribution và package manager

Các hệ sinh thái phổ biến:

- Debian/Ubuntu thường dùng **APT/dpkg**.
- Fedora/RHEL-compatible thường dùng **DNF/RPM** (phụ thuộc release; hệ cũ có thể dùng công cụ khác).
- SUSE family thường dùng **zypper/RPM**.
- Immutable/image-based systems có thể sử dụng **rpm-ostree, transactional updates, image replacement hoặc vendor mechanism**.

Lệnh phải được chọn theo **distribution/release đang chạy và chính sách quản trị**. Không sao chép một lệnh Linux sang tất cả OS.

### 8.2. Lệnh kiểm tra minh họa

**Linux – xác định OS và kernel đang chạy:**

~~~bash
# Ví dụ thao tác đọc trên Linux; không tự chạy ngoài quy trình được phép.
cat /etc/os-release
uname -r
uname -m
date -u
~~~

**APT-based systems – kiểm tra trước khi thực hiện:**

~~~bash
# Chạy trong môi trường có quyền và lịch kiểm soát phù hợp.
sudo apt-get update
apt list --upgradable
apt-cache policy openssh-server

# Việc áp dụng update cần quyết định rõ scope.
# sudo apt-get upgrade
# sudo apt-get dist-upgrade
~~~

`apt-get update` cập nhật metadata, **không cài security patches**. `upgrade` và `dist-upgrade/full-upgrade` có phạm vi/khả năng thay dependencies khác nhau; phải xem danh sách package, package removal và vendor guidance trước khi chạy.

**DNF-based systems – kiểm tra metadata/update:**

~~~bash
# Ví dụ cho distribution có DNF và advisory metadata phù hợp.
cat /etc/os-release
uname -r
sudo dnf check-update
sudo dnf updateinfo list security

# Một số distribution hỗ trợ lọc security advisories:
# sudo dnf upgrade --security
~~~

`dnf check-update` có thể dùng **mã exit khác zero để báo có update**, nên không được đọc tất cả nonzero như thất bại. `updateinfo` / `--security` phụ thuộc advisory metadata/repository; nếu metadata thiếu, “không có security advisories” không đồng nghĩa OS đã được vá. Phải đối chiếu vendor notices và package state.

**SUSE family – ví dụ discovery:**

~~~bash
# Các tùy chọn cụ thể phụ thuộc release và repository setup.
zypper patches
zypper list-updates
~~~

Mục đích những ví dụ trên là **biết công cụ có thể quan sát điều gì**, không phải lệnh triển khai hàng loạt. Automation production cần có runbook, rollback và safety gates riêng.

### 8.3. Kiểm chứng package đã cài

Với package bị ảnh hưởng:

- Xác định package name/architecture/repository.
- Xem **installed full package version/release**.
- Đối chiếu vendor fixed version/backport advisory.
- Kiểm tra service/package thực sử dụng component đó.
- Nếu service dùng thư viện cũ đang giữ trong memory, lên kế hoạch restart phù hợp.

Để inspect:

~~~bash
# APT/dpkg-based: kiểm tra gói đã cài.
dpkg-query -W openssh-server

# RPM-based: thay tên package bằng gói có trong hệ thống.
rpm -q openssh-server

# Kernel đang chạy:
uname -r
~~~

Không áp dụng câu lệnh vô điều kiện nếu package không có mặt. Nếu dùng shell parser/tooling, cần escape values và không lấy untrusted package text làm command.

### 8.4. Kernel cài mới nhưng chưa boot

Một trạng thái rất hay gặp:

1. Package manager cài kernel mới.
2. Files trên disk đã được cập nhật.
3. Máy vẫn chạy kernel cũ.
4. Scanner có thể báo fixed package nhưng kernel vẫn còn attack surface cũ.

Assurance phải phân biệt:

- **Installed kernel package**.
- **Bootloader/default kernel**.
- **Running kernel** từ `uname -r`.
- **Reboot/activation status** và livepatch state nếu có.
- **Security feature health** sau boot: drivers, modules, EDR/audit, encryption, network.

Không coi lệnh reboot trả về thành công là bằng chứng kernel mới đang chạy; cần **kết nối trở lại, kiểm tra thực tế và xác nhận service khỏe**.

### 8.5. Userspace library restart

Một process có thể tiếp tục dùng bản thư viện đã load trước khi cập nhật. Cần xác định:

- Dịch vụ nào dùng vulnerable package?
- Có cần restart services hoặc reboot toàn máy?
- Có tooling/vendor guidance xác định processes cần restart?
- Restart có ảnh hưởng sessions, queues hoặc data consistency?
- Có phiên bản process thực đang dùng thư viện mới chưa?

**Package installed** và **process vulnerable code no longer running** là hai claim khác nhau. Đối với network daemon hoặc crypto library quan trọng, test phải quan sát **process lifecycle/health** sau restart.

### 8.6. Live patching: hữu ích nhưng có giới hạn

Kernel livepatch/hotpatch có thể sửa **một số lỗ hổng kernel khi đang chạy** mà không reboot ngay. Tuy nhiên:

- Không phải mọi CVE/kernel/component đều được livepatch hỗ trợ.
- Livepatch coverage phụ thuộc vendor, kernel build và subscription/channel.
- Có điều kiện về activation, conflicts và reboot sau này.
- Không tự xử lý userspace, firmware, bootloader và mọi driver.
- Cần kiểm tra **effective livepatch applied và CVE coverage**, không chỉ agent “installed”.

Nếu policy cho phép livepatch như một fixed state cho một CVE cụ thể, hãy lưu **vendor coverage mapping + active state evidence**. Không áp nhãn “kernel đã được cập nhật hoàn toàn” chỉ vì có livepatch client.

## 9. Triển khai patch trên Windows

### 9.1. Windows patch workflow

Windows servers/endpoints thường được quản lý qua cơ chế Windows Update, chính sách doanh nghiệp, WSUS hoặc dịch vụ quản lý thiết bị/cloud tùy hạ tầng. Quy trình cần kiểm tra:

- OS edition, build, servicing channel và supported lifecycle.
- Update source/policy, approved deployment rings và maintenance windows.
- Applicable security/cumulative updates và dependencies.
- Device compliance, disk space, servicing health và agent connectivity.
- Pending reboot, restart policies và khả năng active fix.
- Business applications, security agents, services và failover.

Không phải mọi KB phát hành đều áp cho mọi Windows build. Bản cumulative mới có thể bao gồm sửa lỗi từ bản trước; đánh giá phải dựa vào **vendor applicability/supersedence**.

### 9.2. Kiểm tra thông tin phiên bản – ví dụ đọc

~~~powershell
# Ví dụ quan sát; không thay quy trình quản lý patch doanh nghiệp.
Get-ComputerInfo |
    Select-Object WindowsProductName, WindowsVersion, OsBuildNumber

# Danh sách một số hotfix được ghi nhận qua giao diện này:
Get-HotFix | Sort-Object InstalledOn -Descending
~~~

**Giới hạn:** `Get-HotFix` có thể không phản ánh đầy đủ tất cả loại update hoặc trạng thái hiệu lực, tùy Windows/release và nguồn thông tin. Để chứng minh một CVE đã được xử lý, cần đối chiếu **Windows build, applicable KB/update history, vendor metadata và pending reboot**, không chỉ “thấy một KB trong danh sách”.

### 9.3. Restart và domain/cluster dependencies

Windows Server có thể mang nhiều vai trò nhạy cảm:

- Domain controller/identity services.
- Certificate services hoặc management server.
- File server, failover cluster, Hyper-V host.
- Database node, business critical legacy application.

Runbook phải xét **replication/quorum, service dependencies, authentication availability, backup integrity và reboot sequencing**. Cần kiểm tra sự hồi phục của service sau restart, không chỉ ping được máy.

### 9.4. Endpoint compliance và roaming devices

Với laptops/remote devices:

- MDM/reporting agents có thể báo **last seen** rất cũ.
- User có thể trì hoãn reboot, ngủ máy hoặc ở ngoài mạng.
- Device posture có thể báo “update installed” trước activation.
- Disk encryption và EDR cần tiếp tục hoạt động sau update.
- Không nên xóa assets offline khỏi mẫu số chỉ để đạt KPI.

Tách **managed**, **offline/unreachable**, **pending reboot**, **verified patched** và **exception**. Device quay lại mạng cần được đánh giá lại trước khi truy cập tài nguyên nhạy cảm nếu policy yêu cầu.

## 10. Patch trên macOS và các thiết bị quản trị tập trung

### 10.1. Các lớp cần quan sát

Với macOS, cần theo dõi:

- OS version/build và thiết bị/phần cứng tương thích.
- Update availability và trạng thái cài đặt từ công cụ/MDM.
- Những bản cập nhật bảo mật ứng với phiên bản đang dùng.
- Restart/activation hoặc điều kiện user interaction khi hệ điều hành yêu cầu.
- Policy compliance/MDM check-in freshness.
- Các bảo vệ nền tảng và security agents vẫn hoạt động.
- Trạng thái support lifecycle và khả năng nâng cấp sang OS release được hỗ trợ.

**Được MDM quản lý** không chứng minh đã cài mọi patch hoặc không còn vulnerability. MDM command có thể gửi thành công nhưng máy offline, user trì hoãn hoặc update thất bại.

### 10.2. Ví dụ lệnh quan sát

~~~bash
# macOS: phiên bản và build hiện tại.
sw_vers

# Liệt kê các bản cập nhật mà công cụ hệ thống nhìn thấy.
softwareupdate --list
~~~

Quy trình cài và bắt buộc cập nhật qua MDM có thể thay đổi theo release/hardware/policy; cần sử dụng hướng dẫn của vendor và xác minh **actual device build** sau cập nhật. Không cố áp cùng một lệnh noninteractive cho mọi thiết bị.

### 10.3. Các nhóm khó xử lý

- Thiết bị offline trong nhiều tuần.
- Thiết bị không còn được OS vendor hỗ trợ.
- Người dùng có quyền trì hoãn reboot.
- Máy có công cụ developer/security phụ thuộc phiên bản kernel/system extension.
- Máy có policy requiring cryptographic/bootstrap escrow.

Mỗi nhóm cần **owner, exception/mitigation, deadline và evidence**. Tránh coi user “đã nhận thông báo cập nhật” là proof of patch.

## 11. Cloud, Kubernetes, container và firmware

### 11.1. Shared responsibility của OS

Với cloud và managed services, hãy phân biệt:

| Lớp | Câu hỏi về patch | Evidence gợi ý |
|---|---|---|
| **Physical host / hypervisor** | Provider hay khách hàng sở hữu patch? | Responsibility agreement và provider assurance phù hợp |
| **Guest OS trong IaaS VM** | Ai update Windows/Linux VM và reboot? | Guest OS scan, running build, patch job |
| **Managed node OS** | Node image/OS channel nào, ai thay? | Node pool/image version, rollout và runtime fleet |
| **Container host kernel** | Kernel/node runtime do ai bảo trì? | Host image/kubelet/kernel evidence |
| **Container base image** | Ai rebuild image ứng dụng khi OS packages thay? | Base digest, image SBOM/scan, deployed digest |
| **Serverless/PaaS runtime** | Provider xử lý những lớp nào; app dependencies ai xử lý? | Service boundary và vendor/customer evidence |
| **Appliance/embedded OS** | Vendor phát firmware hay OS bundle nào? | Model/version, advisory và maintenance evidence |

**Một container image được cập nhật không vá kernel host**, vì containers chia sẻ host kernel theo mô hình thường gặp. Ngược lại, host đã vá vẫn không làm mới libraries cũ trong image ứng dụng. Cần phân công owner cho cả hai lớp.

### 11.2. Kubernetes worker patching

Để vá OS ở các node Kubernetes, thiết kế thường dựa trên **node/image replacement hoặc controlled in-place patch**. Những điểm cần xét:

1. Xác định node pool, OS image, node role, cluster control plane compatibility.
2. Kiểm tra workload replicas, disruption budgets, node affinity/anti-affinity và capacity.
3. Tạo node mới từ approved image hoặc cordon/drain node đang chạy theo plan.
4. Chờ workloads được schedule và readiness/liveness/functional gates ổn định.
5. Xác minh **runtime kernel/OS image, kubelet và security agents**.
6. Rút node cũ khỏi fleet; đối chiếu tất cả nodes đang serving workloads.
7. Cập nhật launch templates/node images để auto scaling không sinh node cũ.

**Lưu ý:** Cordon/drain là thao tác vận hành có thể làm gián đoạn workloads; không gọi lệnh trực tiếp lên cluster khi chưa có authority, dự phòng capacity và rollback plan.

### 11.3. Container base image và userspace

Đây là điểm thường nhầm:

- CVE trong **host kernel** → patch/replace host node.
- CVE trong **image userspace package** → rebuild và redeploy image ứng dụng từ approved base.
- CVE trong **application dependency** → application supply-chain/dependency patch, không được giải quyết chỉ bằng host patch.
- CVE trong **container runtime** → cập nhật runtime theo vendor, kiểm tra tương thích với Kubernetes/OS.

Tại thời điểm verify, cần kiểm tra **running image digest và node OS/kernel**, không chỉ tag/manifest trong repository. Một golden image hoặc container tag “latest” là nguồn không đủ mạnh nếu deployment vẫn chạy digest cũ.

### 11.4. Cloud snapshots và rollback ảnh hưởng trạng thái

Rollback VM/AMI có thể khôi phục OS nhanh nhưng chứa:

- Authentication tokens, certificates và keys đã được rotate.
- Dữ liệu ứng dụng cũ so với database/queue hiện tại.
- Policy/agent configuration phiên bản cũ.
- Security vulnerabilities mà bản vá vừa khắc phục.

Vì vậy trong runbook nên có **post-rollback security verification**: kernel/build, IAM, credentials, audit, network controls, data consistency và threat exposure. Nếu rollback tái mở một CVE đang bị khai thác, cần compensating controls và risk decision tức thời.

### 11.5. Firmware, microcode và driver

Một số lỗi nền tảng không được giải quyết chỉ bằng package manager:

- UEFI/BIOS hoặc quản lý boot.
- CPU microcode và platform mitigations.
- Storage controller/network adapter driver/firmware.
- BMC/out-of-band management.

Phải chọn **đúng phần cứng, model, revision, vendor procedure**, kiểm tra power/recovery conditions và compatibility. Evidence có thể gồm firmware version sau reboot, effective mitigations, device health và vendor bulletin mapping. Không flash firmware đại trà như chạy một lệnh OS patch chung.

### 11.6. Unsupported/EOL systems

Nếu OS không còn được hỗ trợ bởi vendor hoặc không có kênh phát fix phù hợp:

1. Ghi rõ lifecycle state và assets.
2. Đánh giá các CVE/risk, dữ liệu và exposure.
3. Phân tích nâng cấp/migration hoặc thay thế tài sản.
4. Cô lập/giảm quyền/giới hạn traffic trong thời gian chuyển tiếp.
5. Theo dõi risk owner, deadline và exception có hạn.
6. Xác minh sau migration không có asset cũ quay lại hoạt động.

Đánh dấu `NOT_APPLICABLE` vì “không còn patch” là sai: đây có thể là **rủi ro lớn hơn**, không phải được miễn kiểm soát.

## 12. Xử lý khẩn cấp khi có khai thác hoặc zero-day

### 12.1. Từ thông tin khai thác tới hành động

Khi nhận cảnh báo một lỗi OS có khả năng bị khai thác:

1. Xác thực advisory/threat signal và phạm vi ảnh hưởng.
2. Tìm assets đúng OS, package, build và exposure.
3. Kiểm tra dấu hiệu compromise hiện có, nếu có phải phối hợp incident response.
4. Quyết định **containment** ngay: lọc network, disable feature, giới hạn service, isolate host nếu phù hợp.
5. Xác định vendor patch, hotfix hoặc mitigations.
6. Điều phối emergency maintenance, test tối thiểu nhưng có mục tiêu và staged deployment.
7. Xác minh runtime patch + security/functional health, cùng detection hậu kiểm.
8. Rà soát rủi ro còn lại, assets unreachable, lessons learned và update baseline.

**Patching không tự làm sạch host đã bị compromise.** Nếu attacker đã lấy credentials hoặc cài persistence, cần điều tra, containment, credential rotation và recovery đáng tin song song.

### 12.2. Khi không có bản vá

Một **zero-day mitigation record** cần:

| Trường | Ví dụ nội dung |
|---|---|
| Affected assets | Server IDs, OS builds, exposure và business owners |
| Threat condition | Public exploit signal, required preconditions |
| Temporary controls | Tắt vulnerable feature, ACL/WAF, isolation, reduce privilege |
| Verified efficacy | Network/access negative tests và runtime config |
| Detection | SIEM/EDR rules, logs và owner theo dõi |
| Business tradeoff | Features bị giảm, availability impact |
| Exception | Risk owner, approval, duration, review cadence |
| Final remediation | Vendor fix/replacement và test plan |
| Closure | Runtime fixed state + post-mitigation review |

Một mitigation “đã viết trong ticket” không đủ: phải chứng minh rule đã **có hiệu lực trên affected attack path**.

### 12.3. Emergency change phải được quản trị

Trong emergency, có thể rút ngắn approval process theo quy định, nhưng vẫn cần:

- Identity và authority rõ.
- Scope assets và patch source xác minh.
- Impact/rollback plan phù hợp.
- Timed communication và change ID.
- Audit của lệnh/automation thực hiện.
- Post-change review và retest.

Không mặc định “khẩn cấp” cho phép dùng bản vá từ link không chính thức, tắt signature verification hoặc cho tool toàn quyền mà không có kiểm soát.

### 12.4. Tài sản không thể vá ngay

Nếu cần giữ dịch vụ thiết yếu:

- Tách service khỏi Internet hoặc giới hạn những inbound/outbound paths cụ thể.
- Hạn chế quyền tài khoản/service, giảm local attack surface.
- Sử dụng detection và access review chặt hơn.
- Ưu tiên thay node ở maintenance window ngắn được chấp thuận.
- Theo dõi exposure và điều kiện tăng mức khẩn cấp.

**Một compensating control chỉ giải quyết threat path được kiểm chứng.** Ví dụ WAF không thể bảo vệ một lỗi kernel local privilege escalation nếu attacker đã có foothold nội bộ.

## 13. Rollback, fail-forward và khôi phục sau patch lỗi

### 13.1. Phân loại lỗi hậu vá

| Lỗi | Ví dụ | Phản ứng |
|---|---|---|
| **Install failure** | Hết disk, package conflict, corrupt update metadata | Dừng, sửa prerequisite và retry có kiểm soát |
| **Boot failure** | Kernel/driver không boot | Out-of-band access, boot recovery, restore/fail-forward |
| **Service regression** | App không tương thích TLS/lib mới | Cô lập canary, triage dependency, quyết định rollback |
| **Security regression** | Audit/EDR/firewall không hoạt động | Không đánh dấu healthy, restore security control |
| **Data integrity risk** | Restart giữa transaction, stale state | Quiesce/restore/consistency checks |
| **Cluster availability risk** | Reboot đồng thời mất quorum | Dừng wave, phục hồi membership và review orchestration |
| **Rollback re-exposes CVE** | Trở về kernel vulnerable | Mitigation/exception và patch plan mới |

### 13.2. Rollback không phải luôn tốt hơn fail-forward

Quyết định phụ thuộc:

- Vendor có hỗ trợ uninstall/revert bản vá không?
- Có kernel trước và có bootloader recovery an toàn không?
- Có image/VM snapshot **app-consistent** và phù hợp business continuity?
- Các thay đổi dữ liệu/config sau patch có tương thích version cũ?
- Rủi ro phục hồi bản vulnerable state có chấp nhận được không?
- Có alternate fix/revised image nhanh hơn không?

Một **rollback decision record** phải nêu risk tradeoff và post-action checks. Nếu phải quay lại bản vulnerable, không báo hệ thống đã khắc phục CVE.

### 13.3. Tiêu chí kiểm chứng sau rollback

- OS/kernel/build đúng target recovery plan.
- Service health, replication, dữ liệu và user workflows hoạt động.
- Firewall/IAM/EDR/audit/encryption còn đúng baseline.
- Credentials/tokens không bị hồi sinh sai trạng thái.
- Vulnerability posture được đánh giá lại.
- Compensating controls và exception được bật khi cần.
- Owner quyết định thời điểm thử patch lại và test plan cập nhật.

### 13.4. Tránh retry vô hạn

Nếu install bị lỗi, automation không nên:

- Reboot liên tục làm gián đoạn sản xuất.
- Cài cùng package nhiều lần không phân tích dependencies.
- Trả trạng thái SUCCESS chỉ vì command được gọi.
- Bỏ qua disk/boot health sau update.
- Tự động rollback làm hồi sinh rủi ro mà không báo.

Thiết kế retries có **giới hạn, backoff, trạng thái FAILED/BLOCKED, escalation và idempotency** khi workflow hỗ trợ.

## 14. Security invariants phải giữ qua reboot và failover

### 14.1. Bản vá đã chạy nhưng bảo mật sau đó có thể giảm

Review sau update cần đảm bảo:

- **Identity:** AuthN/authorization và service principals hoạt động đúng.
- **Network:** Firewall, host policies, service bindings và exposure không bị mở rộng.
- **Data protection:** Disk encryption, KMS access, certificates và secrets vẫn hoạt động.
- **Logging:** Audit logs/EDR/monitoring agents khởi động và gửi event.
- **Kernel/security:** SELinux/AppArmor policies, secure boot/TPM hoặc security modules nếu được dùng.
- **Availability:** HA/quorum, service readiness và backup schedules ổn.
- **Integrity:** Không mất state hoặc tạo duplicate business events khi restart.
- **Configuration:** OS hardening baseline chưa drift sau package upgrade.

Một host `uname -r` đúng nhưng firewall bị reset hoặc audit bị tắt **không thể được đánh dấu đầy đủ về bảo đảm kiểm soát** nếu các điều kiện đó thuộc acceptance criteria.

### 14.2. Mẫu post-patch verification

~~~text
Asset identity         : Verified against inventory / change scope
OS/vendor applicability: Fixed state mapped to advisory
Installed updates      : Confirmed
Activation requirement : Reboot/restart/livepatch state checked
Running kernel/build   : Fixed version or approved effective coverage
Application health     : Passed approved smoke/integration tests
Network policy         : No unauthorized port or route change
Identity and secrets   : AuthN/authorization/KMS checks passed
Audit/EDR telemetry    : Active and recent events observed
Cluster health         : Quorum/replicas/capacity verified
Vulnerability scan     : Reconciled; disputed findings documented
Residual exceptions    : Reviewed; not counted as patched
Change evidence        : IDs, time, operator/job, approval, reviewer
~~~

Đây là **checklist kết quả** chứ không phải một bản test đã thực thi. Với asset headless hoặc provider-managed, các cách lấy evidence có thể khác nhưng phải chứng minh được claim trong phạm vi đã giao.

## 15. Viết security requirements và hồ sơ patch có cấu trúc

### 15.1. Các requirements có thể kiểm thử

| Requirement ID | Security property | Acceptance focus |
|---|---|---|
| **OS-PATCH-01** | Tài sản thuộc phạm vi phải được nhận diện và phân công owner | Cloud/CMDB/agent reconciliation, unowned assets |
| **OS-PATCH-02** | Advisory áp dụng phải được triage theo vendor OS/build và mức độ rủi ro | Fixed-version mapping và ưu tiên có căn cứ |
| **OS-PATCH-03** | Bản cập nhật phải đến từ source/channel được phê duyệt và xác minh integrity | Repo/package signing/config/integrity controls |
| **OS-PATCH-04** | High-risk affected assets phải được khắc phục/giảm thiểu theo deadline do policy xác định | Effective patch/mitigation, risk decisions |
| **OS-PATCH-05** | Patch phải qua preflight và staged rollout phù hợp criticality | Canary, rollback, approval và quality gates |
| **OS-PATCH-06** | Fix được cài phải được kích hoạt theo yêu cầu vendor | Running kernel/build, reboot/service restart |
| **OS-PATCH-07** | Security controls và business health phải đạt sau patch | Audit/EDR/IAM/KMS, service smoke tests |
| **OS-PATCH-08** | Golden image và runtime fleet phải đồng bộ trạng thái patch | Image version + running instance population |
| **OS-PATCH-09** | Exception hoặc unsupported OS phải có owner, scope, expiry và remediation | No exception counted as verified patched |
| **OS-PATCH-10** | Failures/unknown/pending reboot phải tạo findings hoặc escalation | Negative/fault tests + evidence |
| **OS-PATCH-11** | Kết quả patch phải truy vết tới asset, advisory, effective state và verification | Protected audit và test artifacts |
| **OS-PATCH-12** | Thay asset/image/OS build hoặc có advisory mới phải kích hoạt reassessment | Drift and change-triggered tests |

### 15.2. Ví dụ requirement chi tiết: kernel update

> **OS-PATCH-06 — Kích hoạt bản vá kernel:** Với các Linux hosts nằm trong population chịu ảnh hưởng của advisory đã được tổ chức phê duyệt, sau khi cài fix, hệ thống quản lý patch phải xác minh **kernel đang chạy** hoặc **effective vendor-supported livepatch coverage** đã xử lý đúng lỗ hổng, trong thời gian và điều kiện do patch policy quy định; host còn chạy kernel vulnerable hoặc không có evidence phải giữ trạng thái pending/unknown, không được ghi verified patched.

**Acceptance criteria:**

1. Host có kernel mới cài nhưng chưa reboot → không được PASS theo đường reboot.
2. Sau reboot, `uname -r`/kernel build trùng fixed state phù hợp distribution → có thể tiếp tục kiểm tra health.
3. Host restart nhưng boot vào kernel cũ → FAIL/PENDING, không đóng finding.
4. Livepatch chỉ được chấp nhận khi vendor xác nhận fix coverage cho kernel/CVE đó và trạng thái active được chứng minh.
5. EDR/audit/network và service health phải đạt acceptance gate sau activation.
6. Host offline hoặc scanner không truy được → UNKNOWN, không suy thành patched.
7. Bằng chứng gồm asset ID, OS/kernel, advisory/version mapping, reboot/livepatch logs, runtime measurement, health results, owner và reviewer.

### 15.3. Ví dụ requirement: cluster rolling patch

> **OS-PATCH-HA-01:** Với cluster sản xuất có yêu cầu high availability, hoạt động cập nhật OS phải được triển khai theo kế hoạch có giới hạn disruption/quorum đã phê duyệt; từng node chỉ được đưa trở lại phục vụ khi OS fix đã active và các health/security checks đạt; rollout phải dừng khi gate thất bại hoặc cluster không còn điều kiện quorum/capacity.

**Acceptance criteria:**

- Canary node patch/reboot và vào lại pool thành công.
- Cluster vẫn đáp ứng quorum/replica capacity đã được xác nhận.
- Không đồng thời lấy quá nhiều nodes ra khỏi service.
- Node chưa verify không được tự động đánh dấu healthy.
- Khi fault-injection health check FAIL, controller dừng wave và mở finding.

### 15.4. YAML minh họa cho một chiến dịch vá OS

Mẫu bên dưới chỉ để học cách thiết kế **evidence-backed patch campaign**, không phải cấu hình có thể chạy trực tiếp trong Ansible/SCCM/Intune hoặc một nền tảng khác:

~~~yaml
osPatchCampaign:
  id: CAMP-OS-KERNEL-042
  version: "1.0"
  status: planned
  description: "Remediate an applicable OS kernel advisory"

  ownership:
    securityRequirementOwnerRole: Security Assurance Owner
    patchExecutionOwnerRole: Linux Platform Team
    serviceOwnerRole: Invoice API Owner
    riskOwnerRole: Infrastructure Risk Owner
    verificationOwnerRole: Security QA

  source:
    advisoryReference: VENDOR-SECURITY-ADVISORY-ID
    vulnerabilityReferences:
      - CVE-EXAMPLE-ID
    vendorReference: APPROVED-OS-DISTRIBUTION
    fixedVersionReference: VENDOR-FIXED-BUILD-MAPPING
    trustedUpdateChannelReference: APPROVED-OS-PACKAGE-SOURCE

  scope:
    assetInventoryReference: INV-PROD-LINUX-2026-11
    targetAssetGroup: PROD-INVOICE-WORKERS
    operatingSystemFamily: linux
    serviceCriticality: high
    excludeOnlyWithApprovedReason: true

  triage:
    riskAssessmentReference: RISK-OS-KERNEL-042
    exploitStatusReference: THREAT-INTEL-REVIEW-042
    patchDeadlineReference: APPROVED-RISK-TIER-PATCH-SLA
    compensatingControlReference: TEMP-NETWORK-ISOLATION-042

  preparation:
    changeReference: CHANGE-OS-042
    compatibilityTestReference: TEST-APP-KERNEL-042
    backupRestorePlanReference: DR-WORKERS-042
    rollbackPlanReference: ROLLBACK-OS-042
    approvalReference: CHANGE-APPROVAL-042

  rollout:
    strategy: rolling-canary
    stages:
      - test-lab
      - production-canary
      - production-batch
    clusterQuorumPolicyReference: APPROVED-HA-QUORUM-POLICY
    maintenanceWindowReference: SCHEDULE-042
    haltOnFailedSecurityOrHealthGate: true
    rebootOrLivepatchPolicyReference: KERNEL-ACTIVATION-POLICY

  acceptanceCriteria:
    - asset-identity-matches-approved-scope
    - installed-package-maps-to-vendor-fix
    - running-kernel-or-supported-livepatch-is-verified
    - service-and-cluster-health-are-verified
    - audit-and-endpoint-protection-are-active
    - no-unresolved-unowned-or-unknown-assets-counted-as-patched

  verification:
    inventorySnapshotReference: INV-SNAPSHOT-042
    requiredTests:
      - TEST-KERNEL-PENDING-REBOOT
      - TEST-KERNEL-WRONG-BOOT-VERSION
      - TEST-SERVICE-REGRESSION-STOPS-WAVE
      - TEST-NODE-REPLACEMENT-IMAGE-FRESHNESS
      - TEST-SCANNER-BACKPORT-RECONCILIATION
    evidenceReferences:
      - EV-PATCH-JOB-042
      - EV-ACTIVE-KERNEL-042
      - EV-POST-PATCH-SECURITY-HEALTH-042
    lastVerifiedAt: null
    result: NOT_ASSESSED
    openFindingIds: []
    exceptionReferences: []

  changeTriggers:
    - new-vendor-advisory
    - new-node-or-golden-image
    - critical-service-regression
    - new-exploitation-evidence
    - change-in-exposure-or-risk-scope
~~~

**Những điểm cần hiểu đúng:**

- `status: planned` và `result: NOT_ASSESSED` cho thấy campaign **chưa chạy hoặc chưa có evidence**, không phải đã vá.
- References tới SLA/baseline/backup là **trường yêu cầu liên kết**, không chứng minh source thực tồn tại.
- Một CVE ID ở ví dụ là placeholder, không được dùng để báo cáo sự cố thật.
- Phạm vi phải được chốt bằng **asset inventory có chứng cứ**; mới có tên nhóm thì chưa đủ.
- Một host PASS sau patch vẫn cần **change-triggered reassessment** nếu bị rebuild từ image cũ hoặc OS rollback.

### 15.5. Kết quả verification record riêng

Không ghi đè `planned acceptance criteria` bằng “đã làm” nếu chưa có test results. Giữ hồ sơ run riêng:

~~~yaml
patchVerificationRecord:
  id: VERIFY-OS-042-17
  campaignId: CAMP-OS-KERNEL-042
  assetId: VM-INVOICE-017
  advisoryReference: VENDOR-SECURITY-ADVISORY-ID
  observedAtReference: RUN-2026-11-28-042

  scope:
    environment: production
    service: invoice-api
    operatingSystemReference: OS-BUILD-LINUX-017

  findings:
    fixedPackageInstalled: true
    rebootRequired: true
    rebootCompleted: false
    runningKernelMapsToFix: false
    serviceHealth: not-retested
    endpointMonitoring: not-retested

  decision:
    result: INSTALLED_PENDING_REBOOT
    verifiedPatched: false
    evidenceReference: EV-PENDING-REBOOT-017
    ownerRole: Linux Platform Team
    followUpReference: CHANGE-REBOOT-017
~~~

**Câu hỏi cho reviewer:** Với kết quả này, host đã được vá chưa? **Chưa**, vì kernel đang chạy không được chứng minh có fix. Đây là tình huống **cài đặt thành công nhưng security objective chưa đạt**.

## 16. Gherkin: kiểm thử cả đường thành công và lỗi

Các scenario được viết để xác minh **security requirements**, không phải test đã được thực thi. Fixtures phải giả lập hoặc dùng environment được cấp phép.

~~~gherkin
Feature: Evidence-based operating system patch assurance

  Scenario: A fixed OS package becomes active after the approved reboot
    Given asset A1 has an applicable security advisory
    And the approved patch has been installed correctly
    And the maintenance plan includes a reboot
    When A1 reboots and post-patch checks are executed
    Then the running OS or kernel must map to the vendor fixed state
    And service health and mandatory security controls must pass
    And the verification record must identify the asset and evidence

  Scenario: An installed kernel without a reboot is not considered remediated
    Given asset A2 has a vulnerable running kernel
    And a fixed kernel package was installed on disk
    And A2 has not activated the new kernel or a supported livepatch
    When patch compliance is evaluated
    Then A2 must not be classified as VERIFIED_PATCHED
    And it must remain pending with an owner and next action

  Scenario: A reboot to the old kernel fails verification
    Given a fixed kernel has been installed on A3
    When A3 reboots into an older vulnerable kernel
    Then A3 must not pass the kernel remediation gate
    And the mismatch must open a finding or controlled retry

  Scenario: An unreachable host is not silently counted compliant
    Given asset A4 exists in the authoritative fleet inventory
    And neither the patch agent nor verification scans can contact A4
    When the fleet coverage report is generated
    Then A4 must remain UNKNOWN or UNREACHABLE
    And it must not increase the verified patched numerator

  Scenario: Canary regression blocks the next deployment wave
    Given the canary host received the approved OS patch
    And a mandatory audit or service health check failed
    When the rollout controller evaluates the advancement gate
    Then the next production wave must not start
    And a finding and remediation decision must be recorded

  Scenario: Network isolation mitigation is not reported as a patch
    Given asset A5 has an applicable CVE and no fixed package yet
    And an approved firewall rule reduces the affected exposure
    When the remediation report is evaluated
    Then A5 may be reported as mitigated according to policy
    But A5 must not be reported as VERIFIED_PATCHED

  Scenario: A replacement node from a stale image is detected
    Given an autoscaling group has an approved patched node image
    And its launch template still refers to a vulnerable image
    When a replacement node starts
    Then image and runtime patch verification must detect the stale state
    And the node must not silently join a compliant fleet

  Scenario: A signed but unapproved update source is rejected
    Given the organization allows only approved OS update repositories
    And an update is offered from a different unapproved source
    When patch automation evaluates the package
    Then update installation must follow the trusted-source policy
    And an unapproved package must not be treated as an authorized fix

  Scenario: A Linux distribution backport is assessed using vendor evidence
    Given an installed package version looks older than the upstream fixed version
    And the distribution vendor backported the relevant security fix
    When a vulnerability finding is reviewed
    Then the reviewer must use the correct distribution advisory mapping
    And the disposition must cite evidence rather than version string guessing

  Scenario: A Windows superseded security update is not misclassified
    Given a Windows host is missing a specific older KB identifier
    And a newer applicable cumulative update contains the same security fix
    When remediation evidence is evaluated
    Then installed build and vendor supersedence must be checked
    And a false missing-patch claim must not be accepted without verification

  Scenario: A cluster rollout respects the approved disruption budget
    Given a critical cluster must maintain quorum and minimum capacity
    And one node is being patched and restarted
    When the orchestrator considers patching another node
    Then it must not violate the approved availability constraints
    And the next node must wait until the earlier node passes readiness checks

  Scenario: Vendor-supported livepatch covers only its claimed fixes
    Given a host has a livepatch client installed
    And a specific kernel advisory is being assessed
    When the patch verification process runs
    Then it must inspect active coverage for the exact affected kernel and fix
    And the mere presence of the client must not result in remediation PASS

  Scenario: A rollback that reintroduces vulnerability requires risk handling
    Given a patched server fails a critical application test
    And an approved rollback restores a previously vulnerable OS image
    When the restored server returns to operation
    Then the vulnerability status must be reassessed
    And any residual exposure must be mitigated or tracked by a risk owner

  Scenario: Patch audit evidence links to the actual asset and change
    Given an OS patch campaign covered assets A1 through A10
    When the campaign is marked ready for closure
    Then each affected asset must have a verified outcome or documented exception
    And installation, activation and security health evidence must be traceable
~~~

### 16.1. Positive tests chưa đủ

Một canary đã được cài và khởi động thành công cho thấy **một đường happy path** hoạt động. Cần thêm các tình huống:

- Một asset ngoài agent roster nhưng có trong cloud inventory.
- Kernel boot về phiên bản cũ.
- Service bị lỗi sau patch.
- KMS/EDR/audit agents không hoạt động sau reboot.
- OS update source bị thay hoặc chữ ký package không hợp lệ.
- Golden image patch nhưng fleet vẫn chạy image cũ.
- Vulnerability scanner không hiểu distro backport.
- Automation bị mất kết nối và đánh dấu SUCCESS sai.
- Exception hết hạn nhưng host chưa vá.

Mục tiêu là chứng minh **đúng kết quả bảo mật**, không phải đếm lệnh update đã chạy.

### 16.2. Test oracle phải độc lập

Một sai lầm là:

> Agent trả `install_success=true` → test mong đợi `install_success=true` → test PASS → dashboard ghi máy đã vá.

Oracle phải bắt nguồn từ **vendor fixed state + approved security requirement**:

1. Đây có phải product/OS build bị ảnh hưởng?
2. Fixed package/build cho distribution này là gì?
3. Fix đã được cài và **đang active** chưa?
4. Business/security health đã đạt chưa?
5. Evidence có đúng asset/version/time không?

Khi test điều kiện “không còn affected”, cần kiểm tra **đường runtime và exposure**, không chỉ một status do agent trả.

### 16.3. Kiểm thử fail-safe của automation

Những lỗi cần mô phỏng khi phù hợp:

| Failure injection | Expected behavior |
|---|---|
| Package source timeout | Không bỏ integrity checks; retry có giới hạn |
| Package signature invalid | Reject/untrusted, alert và không tính patched |
| Download complete nhưng install fail | Status FAILED, không gắn verified |
| Install thành công nhưng reboot chưa hoàn tất | Pending activation, có follow-up |
| Node mất kết nối sau reboot | UNKNOWN/INCIDENT cho tới khi có health/runtime evidence |
| Canary audit agent không hoạt động | Dừng rollout theo security gate |
| Quorum thấp hơn dự kiến | Không reboot thêm node trước khi phục hồi capacity |
| Scanner disagree với vendor backport | Mở investigation, không tự xóa finding |
| Patch exception quá hạn | Escalate/reassess, không tự renew vô hạn |
| Auto scaling tạo node cũ | Detect image drift và chặn/replace theo policy |

## 17. Chỉ số và cách tính patch compliance có căn cứ

### 17.1. Định nghĩa đúng mẫu số

Một báo cáo “tỷ lệ máy đã vá” chỉ có ý nghĩa khi nêu:

- **Population:** Những assets nào, production hay tất cả environments? Có laptop, stopped VM, autoscaling instance?
- **Advisory/requirement:** Đã vá cho CVE cụ thể, baseline tháng này hay mọi patch có sẵn?
- **Time window:** Ảnh chụp lúc nào, cutoff deadline nào?
- **Eligibility:** Assets nào thực sự affected, NOT_APPLICABLE có căn cứ?
- **Evidence bar:** Chỉ “installed” hay phải **active fixed state + health gates**?
- **Missing data:** Unknown, unreachable, pending reboot, EOL, exceptions được xử lý riêng?
- **Refresh cadence:** Asset được tạo mới hoặc thay đổi OS build sau snapshot có được tính lại?

Không nên dùng `patched / scanned hosts` nếu scanner bỏ qua assets không có agent. **Scanned** có thể là một population nhỏ hơn **tổng affected assets**, đặc biệt khi có máy offline và auto scaling.

### 17.2. Ví dụ tính toán

Giả sử đã xác minh **120 Linux hosts thực sự chịu ảnh hưởng** của một vendor advisory trong môi trường production:

- **86 VERIFIED_PATCHED**: kernel/binary fixed state đang hiệu lực, health gates PASS.
- **12 INSTALLED_PENDING_REBOOT**.
- **8 FAILED** do boot/service regression.
- **6 EXCEPTION_ACTIVE** với mitigation tạm.
- **8 UNREACHABLE/UNKNOWN**.

Tổng: 86 + 12 + 8 + 6 + 8 = 120.

~~~text
Affected population = 120
Verified patched = 86
Verified patch coverage = 86 / 120 = 71.67%

Installed but not active = 12
Failed = 8
Approved exception (not patched) = 6
Unreachable or unknown (not patched) = 8

Unverified or not yet patched = 34
~~~

**Không báo (86 + 12 + 6) / 120 = 86,67% compliant.** Bản vá chờ reboot và exception không đáp ứng claim **effective patch active**. Cũng không bỏ 8 assets unknown khỏi mẫu số nếu chúng đã được xác định là affected.

### 17.3. Phân biệt coverage nhiều lớp

| Metric | Tử số | Mẫu số | Ý nghĩa |
|---|---|---|---|
| **Inventory coverage** | Assets có owner + OS identity được xác minh | Assets trong independent discovery population | Nhìn thấy fleet tới đâu |
| **Applicability assessment coverage** | Assets được xác minh affected/N/A | Assets cần xét advisory | Có biết nên vá ai không |
| **Patch installation coverage** | Assets cài đúng fix trên disk | Affected assets | Đã cài trên disk tới đâu |
| **Activation coverage** | Assets đang dùng fixed state/livepatch hợp lệ | Affected assets | Security fix thực sự có hiệu lực tới đâu |
| **Verified remediation coverage** | Assets active fix + acceptance checks đạt | Affected assets | Bằng chứng đủ theo requirement |
| **On-time verified remediation** | Affected assets verified trước deadline | Affected assets đến hạn theo policy | Kịp thời hay quá hạn |
| **Pending reboot aging** | Assets pending quá ngưỡng | Assets pending reboot hoặc affected set theo định nghĩa | Debt sau install |
| **Exception exposure** | Affected assets có exception còn hiệu lực | Affected assets | Rủi ro chưa vá nhưng đã có quyết định |
| **EOL OS exposure** | Unsupported assets còn vận hành | Assets trong scope | Rủi ro không có nguồn fix đáng tin |
| **Golden image freshness** | Approved images đạt baseline và đang được dùng | Images/templates thuộc scope | Tránh tạo lại máy vulnerable |
| **Scan/evidence freshness** | Assets có evidence đủ mới | Assets cần verified | Kết luận có còn đại diện hiện tại? |

Tỷ lệ “đã cài patch” và “đã xác minh fix active” **có thể khác nhau lớn**. Nếu tổ chức chọn metric tổng hợp, phải công bố tiêu chí cấu thành, không gộp các trạng thái trái nghĩa.

### 17.4. Time-to-remediate và độ lệch của phép đo

**Time-to-remediate (TTR)** có nhiều mốc:

- Vendor công bố advisory.
- Tổ chức nhận thông báo.
- Asset bị phát hiện affected.
- Patch được phê duyệt/triển khai.
- Fix active và verification PASS.

Ví dụ metric:

~~~text
Verified remediation duration =
    timestamp_of_verified_fixed_state
    - timestamp_of_initial_applicability_detection
~~~

**Mốc phải thống nhất** giữa teams và báo cáo. Nếu lấy ngày cài package thay vì ngày fix active, TTR có thể “đẹp” giả. Nếu reset ngày phát hiện sau mỗi lần scanner chạy, deadline có thể bị kéo dài vô ý.

Nên báo thêm **oldest open findings, median/percentile TTR theo risk tier, quá hạn, pending reboot aging và active exploitation exposures**. Không chỉ dùng average vì một vài tài sản rất trễ có thể bị che.

### 17.5. Compliance score không thay risk decision

Hai teams có cùng verified coverage 90% nhưng rủi ro rất khác:

- Team A còn 10% trên lab assets isolated không có dữ liệu nhạy cảm.
- Team B còn 10% trên Internet-facing identity gateways đang có exploit thực tế.

Đánh giá cần thêm:

- Risk severity và exploit evidence.
- Internet exposure, privilege và data sensitivity.
- Asset criticality và business consequences.
- Những control bù đã có evidence.
- Deadline/overdue và owner.
- Nếu asset compromise nghi ngờ, incident status.

**Không dùng KPI để khuyến khích loại máy khó vá khỏi inventory**, chuyển trạng thái UNKNOWN thành N/A hoặc đóng finding mà không có evidence.

## 18. Assurance case: từ lệnh cập nhật tới kết luận có giới hạn

### 18.1. Các mức bằng chứng khác nhau

**Mức 1 — Đã lên kế hoạch:** Có change ticket và danh sách host.

**Mức 2 — Đã chạy lệnh:** Automation trả exit code 0.

**Mức 3 — Đã cài:** Package/update metadata cho thấy fix nằm trên disk.

**Mức 4 — Đã kích hoạt:** Runtime kernel/build, livepatch/daemon process phù hợp.

**Mức 5 — Đã xác minh security + business health:** Active fixed state, service, IAM, EDR/audit và network controls đạt.

**Mức 6 — Đã đối soát fleet:** Mọi affected asset trong inventory có kết quả phù hợp hoặc gap/exception minh bạch.

Một **exit code 0** có thể hỗ trợ khẳng định lệnh đã thành công, nhưng **không chứng minh level 6**. Bằng chứng phải đi cùng chính claim định đưa ra.

### 18.2. Evidence package

| Câu hỏi assurance | Evidence gợi ý | Giới hạn |
|---|---|---|
| Asset inventory có đầy đủ? | Cloud/CMDB/agent reconciliations, timestamp, owner | Orphaned/unreachable may remain |
| CVE/patch có áp dụng? | Vendor advisory, OS/build/package map, scanner findings | Scanner có thể sai với backport |
| Nguồn patch đáng tin? | Package repository/source settings, signature verification/audit | Source compromise vẫn cần threat model |
| Patch đã cài? | Agent/package manager/install logs, package versions | Chưa chắc active |
| Fix đã active? | Running kernel/build, service restart/livepatch coverage, post-boot evidence | Có thể có component khác chưa được vá |
| Cluster vẫn healthy? | Quorum/capacity, smoke tests, monitoring và logs | Một canary không đại diện mọi topology |
| Security controls còn hoạt động? | AuthN/IAM, EDR/audit, firewall, encryption checks | Test mới chỉ một subset |
| Patch closure đúng? | Per-asset verification result, owner, reviewer, finding dispositions | Dựa vào population đã xác định |
| Exception/risk được quản trị? | Risk approval, expiry, mitigations, review history | Không đồng nghĩa patched |
| Control hiệu quả trong kỳ? | Runtime sampling, drift alerts, patch history, incidents | Mẫu/time-window phải công bố |

### 18.3. Dạng verification record tối thiểu

Mỗi máy hoặc group cần có:

- Asset ID, hostname/instance ID, environment, owner và criticality.
- OS edition/distribution/release/architecture và observed build.
- Advisory/CVE IDs, affected/fixed mapping và source version.
- Patch job ID, operator/automation identity và change/approval ID.
- Start/install/reboot/verification timestamps.
- Installed package/KB/build và **effective running state**.
- Health/acceptance tests: expected, actual, PASS/FAIL/UNKNOWN.
- Backup/rollback decision và evidence nếu xảy ra.
- Scanner retest result hoặc mapping giải thích false positive.
- Evidence integrity/provenance, reviewer, retention và limitations.
- Exception/finding IDs và next verification trigger.

**Không lưu credentials, private keys, full endpoint tokens hoặc PII thật** vào evidence để “cho đủ chi tiết”. Log phải được bảo vệ quyền truy cập/tính toàn vẹn.

### 18.4. Claim–Argument–Evidence–Limitations

Một claim được giới hạn:

> **Claim:** Trong phạm vi 86 production Linux hosts thuộc nhóm Invoice Workers được xác minh ngày đánh giá, advisory kernel được áp dụng đã có fixed state hiệu lực; các kiểm tra service readiness và security telemetry bắt buộc sau reboot đạt.
>
> **Argument:** Danh sách affected hosts được xác định từ nguồn inventory độc lập; phiên bản được đánh giá theo distro advisory; sau update hệ thống kiểm tra running kernel hoặc effective livepatch coverage và health gates; kết quả được đối chiếu per host.
>
> **Evidence:** Inventory snapshot, vendor mapping, signed/trusted package metadata, patch job/reboot records, runtime kernel checks, service/audit/EDR tests và verified outcome records.
>
> **Limitations:** Claim chỉ nói về **86 hosts đã verify**, không kết luận 34 affected hosts còn pending/failed/exception/unknown được vá. Chưa bao phủ những assets ngoài inventory hoặc advisories khác.

Đây là ví dụ về cấu trúc assurance, **không phải kết quả thực sự** của một tổ chức cụ thể. Muốn đưa ra claim thật phải có evidence từ environment đang đánh giá.

### 18.5. Khi scanner và OS vendor không đồng ý

Một scanner báo CVE còn tồn tại dù OS package đã được backport, hoặc ngược lại.

Không giải quyết bằng cách:

- Tin scanner tuyệt đối.
- Tin team vận hành tuyệt đối.
- Tắt rule scanner để dashboard xanh.

Thay vào đó:

1. Xác định product, distro, package release/build.
2. Kiểm tra vendor advisory và fixed package/release mapping.
3. Kiểm tra **running process/kernel** nếu bản sửa yêu cầu activation.
4. Phân tích scanner detection method, credential coverage, false-positive/false-negative possibility.
5. Nếu còn bất định, ghi **UNKNOWN/INVESTIGATE** và owner.
6. Lưu evidence và quyết định reviewer để kết quả kiểm chứng lại được.

### 18.6. Bằng chứng chống “asset biến mất”

Một VM đã được patch nhưng sau đó auto scaling xóa nó; reporting chỉ thấy machines còn chạy có thể bỏ qua:

- Image factory vẫn vulnerable.
- Stopped VMs sẽ bật lại.
- Replacement nodes dùng template cũ.
- Newly created nodes chưa vào scanner roster.

Do đó ngoài per-host verification còn cần **image version, launch template, runtime fleet scan và change-triggered reconciliation**. Assurance phải chịu được tính động của cloud fleet.

## 19. Case study: vá kernel cho cụm dịch vụ hóa đơn

### 19.1. Bối cảnh hệ thống

Tổ chức giả định **InvoiceHub** có một cụm dịch vụ hóa đơn quan trọng:

- 3 availability zones phục vụ production API/Export Workers.
- Linux VM và Kubernetes workers kết hợp trong môi trường cloud.
- Autoscaling dùng golden image do Image Factory tạo.
- Một số node chỉ xử lý batch jobs, một số node chạy API nhạy cảm.
- Log collector, EDR và KMS clients phải tiếp tục vận hành sau reboot.
- Patch automation có dashboard “successfully installed”.
- Hệ thống có change/incident/risk management và maintenance policy.

Nhóm bảo mật nhận được vendor advisory về một lỗi kernel ảnh hưởng đến những bản build đang sử dụng. Không có dữ liệu thực nào được cung cấp ở bài học này; đây là **tình huống mô phỏng** để thực hành lập luận.

### 19.2. Bước 1 — Xác định đúng risk và affected assets

Nhóm rà soát:

1. Vendor affected/fixed kernel builds theo distribution release.
2. Exploit prerequisites và threat intelligence.
3. Cloud inventory, Kubernetes node list, OS/EDR/vulnerability scanner data.
4. Business criticality, Internet exposure, workload privileges, tenant data.
5. Golden images, stopped instances và auto scaling templates.
6. Maintenance and HA constraints.

Kết quả đối chiếu giả định: **120 production Linux hosts chịu ảnh hưởng** của advisory; ngoài ra Image Factory có một template cũ cần cập nhật, nhưng template là **control artifact** được theo dõi riêng để tránh đếm trùng cùng một host.

### 19.3. Bước 2 — Threat scenarios

| Risk ID | Mô tả | Security implication |
|---|---|---|
| **R-KRN-01** | Exploit lỗi kernel trên host có workload quyền cao | Local privilege escalation / isolation risk |
| **R-REBOOT-02** | Install fix không reboot; vulnerable kernel vẫn chạy | False assurance, attack path còn tồn tại |
| **R-HA-03** | Reboot quá nhiều nodes cùng lúc | Mất quorum/capacity và availability |
| **R-AGENT-04** | EDR/audit agent không tương thích kernel mới | Mất detection/accountability |
| **R-IMAGE-05** | Auto scaling tạo nodes từ template cũ | Vulnerability quay lại sau rollout |
| **R-ROLLBACK-06** | Rollback không kiểm soát làm host vulnerable trở lại | Rủi ro khai thác tái diễn |
| **R-INVENTORY-07** | Offline/orphan nodes bị bỏ khỏi agent list | Coverage sai và remediation thiếu |

### 19.4. Bước 3 — Yêu cầu kiểm thử

| Requirement | Câu trả lời bắt buộc |
|---|---|
| **CR-01** | Có inventory 120 affected hosts đủ owner và OS/build evidence? |
| **CR-02** | Patch source đúng distro và package fixed state? |
| **CR-03** | Đã kiểm tra compatibility, backup/recovery và HA/quorum gates? |
| **CR-04** | Mỗi affected host có running kernel/livepatch coverage phù hợp? |
| **CR-05** | EDR/audit/KMS/functional health còn đạt sau activation? |
| **CR-06** | Golden image và auto scaling template đã được cập nhật? |
| **CR-07** | Pending reboot, failed, exceptions và unreachable được report riêng? |
| **CR-08** | Hậu kiểm, owner, risk decision và retest có bằng chứng? |

### 19.5. Bước 4 — Kế hoạch rollout theo wave

~~~mermaid
flowchart TD
    A["Affected inventory: 120 hosts"] --> B["Vendor fix + risk/compatibility review"]
    B --> C["Test image + offline test"]
    C --> D["Canary in one availability zone"]
    D --> E{"Active fix + security/health PASS?"}
    E -- "No" --> F["Stop, triage, rollback/fail-forward"]
    E -- "Yes" --> G["Sequential rollout across HA groups"]
    G --> H["Reboot/recreate + verify each running node"]
    H --> I["Rebuild golden image + update launch templates"]
    I --> J["Fleet reconciliation + independent verification"]
    J --> K["PASS / pending reboot / failed / exception / unknown"]
    K --> L["Remediation, risk decisions, retest and continuous monitoring"]
~~~

### 19.6. Bước 5 — Phát hiện trong lần triển khai giả định

Sau các waves, dashboard ban đầu báo phần lớn nodes “installed successfully”. Nhưng reviewer tách:

| Nhóm | Số asset | Bằng chứng |
|---|---:|---|
| Verified fixed state và health PASS | 86 | Runtime kernel/advisory match và post-patch tests |
| Kernel mới trên disk, chưa reboot | 12 | Patch logs đúng nhưng running kernel cũ |
| Install/boot/health FAIL | 8 | Boot issue hoặc security agent regression |
| Exception + mitigation tạm | 6 | Approved controls/risk decision, chưa patched |
| Unknown/unreachable | 8 | Không có telemetry xác minh phù hợp |
| **Tổng affected hosts** | **120** | Đã đối chiếu inventory giả định |

Ngoài 120 hosts, Image Factory vẫn tham chiếu một image có kernel cũ; nếu không sửa, **new nodes có thể tái tạo phơi nhiễm**.

**Kết luận không được dùng:** “Cơ bản đã vá 100% vì update job hoàn tất”. Dữ liệu thực tế giả định chỉ hỗ trợ:

~~~text
Verified patched hosts = 86
Affected production hosts = 120
Verified remediation coverage = 86 / 120 = 71.67%
Remaining nonverified = 34
Golden image finding = OPEN
~~~

### 19.7. Bước 6 — Hành động theo finding

**Nhóm 12 pending reboot:**

- Lập maintenance windows theo HA group.
- Reboot tuần tự, kiểm tra active kernel và service/security health.
- Không tự xác nhận trước reboot.

**Nhóm 8 failed:**

- Cô lập affected canary/host nếu nguy cơ khai thác và regression đáng kể.
- Phân tích driver/agent/disk/boot logs.
- Sửa compatibility issue, rebuild/replace hoặc rollback có risk decision.
- Retest đúng version, không tái dùng PASS của build khác.

**Nhóm 6 exceptions:**

- Kiểm chứng mitigation, risk owner approval, scope/expiry và review trigger.
- Lập kế hoạch cố định để vá/migrate, không chuyển thành PASS.

**Nhóm 8 unknown:**

- Reconcile cloud/Kubernetes/agent inventory và tìm nguyên nhân inaccessible.
- Nếu không xác minh, giữ trạng thái unknown và escalation.
- Kiểm tra assets có thể đã bị xóa/thay, tránh đếm trùng.

**Golden image:**

- Rebuild image, test runtime kernel/agents.
- Cập nhật launch template/node pool theo approved image.
- Reconcile các nodes sinh mới từ image đó.

### 19.8. Bước 7 — Assurance claim trước và sau khắc phục

**Claim hợp lệ ở lần đánh giá đầu:**

> Trong phạm vi 120 Linux hosts thuộc production InvoiceHub được xác minh affected bởi vendor advisory, 86 hosts đã có fixed state đang chạy và đạt health/security gates; 34 hosts còn lại chưa đủ điều kiện hoặc bằng chứng để tính verified patched. Golden image có một finding riêng cần xử lý.

**Evidence:** Inventory, vendor mapping, update jobs, running kernel, security agent/health checks, exception approvals và image factory configuration.

**Limitations:** Không kết luận về các cloud resources chưa vào inventory, các lỗ hổng khác hoặc tài sản vendor-managed không nằm trong scope. Claim không có nghĩa không xảy ra compromise trước khi vá.

Sau remediation:

- Cập nhật verification run cho từng host.
- Xác nhận golden image và fleet không tái tạo vulnerable nodes.
- Đóng finding chỉ khi có **đủ runtime/effective-state evidence**.
- Lưu thời điểm, release, reviewer và các exceptions còn lại.

## 20. Những sai lầm thường gặp

| Sai lầm | Vì sao nguy hiểm? | Cách cải thiện |
|---|---|---|
| “Đã chạy `apt-get update` là đã vá” | Chỉ cập nhật package metadata | Kiểm tra installed packages và runtime |
| “Install success = fixed” | Kernel/daemon còn chạy version cũ | Kiểm tra reboot/restart/activation |
| Dựa vào `uname -r` mà không xem distro advisory | Không biết fixed build/backport | Vendor-specific applicability mapping |
| So version upstream đơn giản | Distro backport có thể không đổi upstream number | Full package release và advisory evidence |
| Windows thiếu một KB cũ = vulnerable | Cumulative newer update có thể supersede | Build/KB applicability/supersedence |
| Không vá assets offline vì scanner không thấy | Missing inventory tạo coverage giả | Reconcile independent sources |
| Đánh dấu stopped VM N/A mặc định | Khi bật lại có thể vulnerable | Policy patch-before-activation |
| Chỉ vá running VMs, không cập nhật image | Scale-out làm xuất hiện máy cũ | Image factory và runtime fleet checks |
| Patch container image thay host kernel | Containers thường dùng shared host kernel | Phân tách OS host vs image dependencies |
| Patch host thay container libraries | OS userspace trong image vẫn cũ | Rebuild/redeploy image và verify digest |
| “Cloud provider lo hết OS patch” | Guest OS thường thuộc khách hàng | Responsibility mapping từng lớp |
| Dùng livepatch client là coi kernel sạch | Coverage không đầy đủ và cần activation | Verify advisory-specific livepatch |
| Chạy update từ repo không được phê duyệt | Package integrity/supply-chain risk | Trusted source và signature verification |
| Reboot toàn cluster cùng lúc | Quorum/capacity bị mất | Rolling wave + disruption gates |
| Canary chỉ ping thành công | Audit/KMS/EDR/app có thể hỏng | Security invariants và smoke/integration tests |
| Không có rollback plan | Patch regression kéo dài outage | Preflight, backup và recovery drill |
| Rollback về vulnerable image mà vẫn ghi PASS | Rủi ro CVE quay lại | Reclassify affected + mitigation/exception |
| Bỏ qua CVE vì score thấp | Có thể exploited trong môi trường cụ thể | Threat/exposure/risk-based triage |
| Hoãn patch exploited CVE đến kỳ sau | Cửa sổ tấn công kéo dài | Emergency triage và interim controls |
| “Có WAF” = lỗi kernel được vá | WAF không chặn mọi attack path | Scope mitigation và verify efficacy |
| Scanner false positive bị xóa không có evidence | Che findings thật | Vendor mapping và reviewer disposition |
| Cộng exceptions vào verified patched | Compliance giả | Trạng thái riêng + risk owner/expiry |
| Patch job thành công là kết thúc quy trình | Chưa đối chiếu host, kernel, security health | End-to-end evidence |
| Chỉ xét OS runtime, không firmware/drivers | Một số vulnerabilities ở lớp khác | Platform vendor advisory responsibility |
| Đóng ticket khi đã tạo change request | Remediation chưa thực hiện | Closure sau verified state/retest |
| Giữ audit logs chứa secrets | Evidence thành nguồn rò rỉ | Data minimization và access controls |
| Không kiểm tra EOL OS | Có thể không còn fix | Migration/isolation và explicit risk treatment |
| Metrics chỉ đếm hosts có agent | Unmanaged/unreachable bị loại | Independent population reconciliation |

## 21. Bài tập thực hành

### Bài tập 1 — Xây asset inventory để quản lý OS patch

Một tổ chức có Linux VMs, Windows domain controllers, Kubernetes nodes, nhân viên dùng laptops, 3 golden images và 2 thiết bị vendor-managed. CMDB có 150 assets, EDR thấy 160, cloud API thấy 165 và patch agent chỉ thấy 142.

**Yêu cầu:** Thiết kế quy trình **inventory reconciliation**; nêu asset ID, OS/build, owner, criticality, environment, update channel, runtime state, last seen và source-of-truth. Phân loại những assets **unknown/unreachable/stopped/provider-managed** và định nghĩa mẫu số coverage.

**Tự kiểm tra:** Không lấy 142 agent-managed assets làm toàn bộ fleet mà bỏ qua chênh lệch giữa các nguồn.

### Bài tập 2 — Applicability và distro backport

Một scanner báo package Linux có upstream version thấp hơn bản ghi CVE fixed version. Nhưng distribution vendor cho biết package release đã có backported fix.

**Yêu cầu:** Liệt kê những thông tin cần thu thập (OS release, package full version/release, advisory, installed state, runtime state), viết verification decision record và lý do cần/không cần retest. Đưa ra cách xử lý khi scanner vẫn báo affected.

**Tự kiểm tra:** Không báo false positive chỉ vì operator nói “đã backport” mà không có vendor evidence.

### Bài tập 3 — Từ threat intelligence tới patch prioritization

Ba lỗ hổng OS:

- A: Kernel privilege escalation trên bastion production dùng bởi admin.
- B: Remote service vulnerability với exploitation evidence trên Internet-facing gateway.
- C: Vulnerability có cùng điểm severity cao nhưng nằm trên isolated offline lab host.

**Yêu cầu:** Lập bảng CVE/advisory, exploit preconditions, exposure, criticality, impact, mitigations, vendor fix và decision owner. Đề xuất thứ tự ưu tiên và phương án emergency/normal rollout **không tự bịa deadline**.

**Tự kiểm tra:** Không dùng điểm CVSS làm yếu tố duy nhất, không đánh đồng “không Internet-facing” với “không rủi ro”.

### Bài tập 4 — Kernel đã cài nhưng chưa reboot

Một host cài kernel fixed package thành công ngày thứ Hai; đến thứ Năm `uname -r` vẫn trả kernel cũ. Dashboard cài đặt báo 100% SUCCESS.

**Yêu cầu:** Xác định vì sao claim “đã vá” sai, viết một requirement cụ thể cho activation, positive/negative test và evidence. Xây follow-up plan để reboot theo HA group.

**Tự kiểm tra:** Có phân biệt installed, pending reboot, running kernel, livepatch coverage và security health.

### Bài tập 5 — Rolling patch cho cluster 5 nodes

Một dịch vụ critical có 5 nodes và các điều kiện quorum/capacity chưa được cung cấp. Một thay đổi kernel cần reboot từng node.

**Yêu cầu:** Đề xuất **những câu hỏi bắt buộc trước khi triển khai** về quorum, replicas, max unavailable, stateful traffic và recovery; sau đó thiết kế canary/rollout gates và stop conditions. Không tự quyết định an toàn khi reboot 2 nodes cùng lúc nếu không có cluster topology.

**Tự kiểm tra:** Không xem số lượng 5 nodes là đủ thông tin để kết luận quorum/safe parallelism.

### Bài tập 6 — Windows cumulative update

Một Windows Server không thấy KB cũ trong kết quả `Get-HotFix` nhưng hiển thị build mới hơn. Scanner báo missing KB.

**Yêu cầu:** Viết quy trình kiểm tra OS edition/build, vendor advisory, supersedence, update history/pending reboot và scanner evidence. Mô tả khi nào kết luận verified, false-positive hoặc UNKNOWN.

**Tự kiểm tra:** Không dựa riêng vào `Get-HotFix` hoặc một KB identifier.

### Bài tập 7 — Cloud VM và golden image

Auto scaling group có 40 VMs; 35 được update tại chỗ, 5 bị thay thế. Tuy nhiên launch template còn trỏ tới image cũ và một node mới xuất hiện sau patch window.

**Yêu cầu:** Thiết kế remediation cho **golden image → launch template → runtime fleet**. Viết negative test phát hiện node dùng image cũ, kiểm tra runtime kernel và cách tính coverage khi fleet size biến động.

**Tự kiểm tra:** Không chỉ báo image factory đã build patch hoặc 35 VM đã cài là xong.

### Bài tập 8 — KMS/EDR sau OS patch

Canary Linux node đã boot kernel mới nhưng EDR không gửi telemetry; KMS client timeout, khiến ứng dụng không decrypt được dữ liệu.

**Yêu cầu:** Định nghĩa security/functional acceptance gate, severity theo business impact, stop rollout, phương án rollback/fail-forward, cách giữ security invariants và retest. Viết một Gherkin scenario về canary gate failure.

**Tự kiểm tra:** Không đánh dấu canary PASS vì OS version đúng; kiểm tra cả end-to-end service và security monitoring.

### Bài tập 9 — Zero-day chưa có fix

Một network service trong OS có lỗ hổng bị khai thác. Vendor chưa có bản vá; service đang dùng ở production và không thể tắt ngay.

**Yêu cầu:** Viết **temporary mitigation plan** có asset scope, network reachability, detection, change owner, exception authority, review cadence và condition chuyển sang patch. Đề xuất phép kiểm chứng mitigation trên đúng attack path.

**Tự kiểm tra:** Không đổi status thành PATCHED khi chỉ có firewall mitigation; không quên incident investigation nếu có dấu hiệu compromised host.

### Bài tập 10 — Tính coverage đúng trạng thái

Một campaign có 120 affected hosts: 86 verified, 12 pending reboot, 8 failed, 6 exceptions và 8 unreachable. Một báo cáo đề xuất gộp verified + pending + exception thành “cơ bản compliant”.

**Yêu cầu:** Tính verified coverage, phân loại 34 assets còn lại, nêu risk và next action mỗi nhóm. Viết assurance claim có scope và limitations; chỉ ra vì sao cách cộng đề xuất sai.

**Tự kiểm tra:** Không biến exception thành PASS, không loại unknown khỏi mẫu số khi chúng được biết là affected.

### Bài tập 11 — Rollback và rủi ro tái phơi nhiễm

Sau bản vá kernel, driver của một storage controller gây lỗi. Nhóm vận hành định rollback toàn bộ VM về image cũ.

**Yêu cầu:** So sánh rollback, fail-forward, image replacement, vendor workaround và workload migration. Định nghĩa data consistency, downtime, credential/audit checks và cách quản lý CVE risk nếu quay về vulnerable kernel.

**Tự kiểm tra:** Không coi snapshot restore là đảm bảo khôi phục nhất quán mọi giao dịch hoặc giữ nguyên security state.

### Bài tập 12 — Thiết kế patch assurance chương trình liên tục

Tổ chức muốn một dashboard patch management cho nhiều OS/distributions, cloud accounts, endpoints và managed services. Hiện dashboard chỉ nhận “install success” từ agent.

**Yêu cầu:** Thiết kế trạng thái, inventory sources, advisory mapping, risk tiers, activation/health evidence, metric với mẫu số và change-triggered reassessment. Đề xuất cơ chế xử lý **stale scan, EOL OS, golden-image drift, exceptions và revoked patches**.

**Tự kiểm tra:** Kết quả phải hỗ trợ **quyết định có evidence**, không chỉ đưa ra tỷ lệ cài đặt thành công.

## 22. Checklist đánh giá Patch hệ điều hành

### 22.1. Phạm vi và rủi ro

- **Asset inventory:** Đã kiểm kê đủ physical, VM, cloud, cluster nodes, laptops, templates, offline và vendor-managed assets?
- **Owner:** Mỗi asset/OS layer có business/system/patch execution owner?
- **OS lifecycle:** Có xác định OS release/build, support status, architecture và patch channel?
- **Population:** Có đối chiếu CMDB/cloud/EDR/patch agent/scanner để phát hiện chênh lệch?
- **Threat intelligence:** Có vendor advisories, CVE, exploitation signals và risk triage?
- **Applicability:** Affected/fixed build được xác định đúng OS/distribution/backport/supersedence?
- **Exposure:** Network, user privileges, data, dependencies và isolation đã được xem xét?
- **Deadline:** Có SLA/priority từ policy/risk owner, không tự suy bằng điểm CVSS?
- **No fix:** Mitigations/monitoring và risk owner có rõ, không đếm là patched?
- **Unsupported:** Có migration/isolation/risk decision cho EOL OS?

### 22.2. Kiểm soát trước triển khai

- **Trusted source:** Update catalog/repo/signature/vendor channel đã được phê duyệt?
- **Preconditions:** Có kiểm tra disk, dependencies, package conflict, kernel/driver/agent compatibility?
- **Change approval:** Có change ID, scope, owner và emergency authority?
- **Backups:** Có recovery/restore plan được xác minh theo workload, không chỉ snapshot tên gọi?
- **Fail-forward/rollback:** Có lựa chọn và giới hạn, không tái mở exposure mà không quản lý?
- **HA/quorum:** Có phân tích capacity, disruption budget, replication và trình tự reboot?
- **Canary:** Có test subset đại diện production với security/functional gates?
- **Maintenance:** Có communication, incident escalation, maintenance window và stop conditions?
- **Least privilege:** Automation credentials, logging và secrets được kiểm soát?

### 22.3. Kiểm chứng triển khai và trạng thái hiệu lực

- **Installed package:** Đúng package/KB/build/advisory mapping theo vendor?
- **Reboot:** Nếu yêu cầu, đã reboot đúng và chứng minh OS/kernel đang chạy phiên bản mới?
- **Livepatch:** Đã kiểm tra coverage/cài đặt/activation cho CVE cụ thể, không chỉ client installed?
- **Service restart:** Userspace process đã load phiên bản library fixed?
- **Functional health:** API, batch, data workflows, storage, network và cluster service đạt?
- **Security health:** Firewall, IAM, EDR, audit, KMS, encryption, policy vẫn đúng?
- **Cloud/image:** Golden image, launch templates, node pools và running instances đồng bộ?
- **Container host:** Host kernel và userspace base image được xét tách biệt?
- **Firmware:** Có review những advisories cần update driver, microcode, boot/firmware?
- **Failure:** Những install failures/reboot issues/quorum violations không bị đánh dấu PASS?

### 22.4. Assurance và báo cáo

- **States:** Có phân biệt DISCOVERED, PENDING, INSTALLED, REBOOT, VERIFIED, FAILED, EXCEPTION và UNKNOWN?
- **Evidence:** Asset ID, vendor mapping, package state, running state, health và reviewer đầy đủ?
- **Negative tests:** Có test pending reboot, wrong kernel, stale image, trust source, rollback và offline host?
- **Population integrity:** Có kiểm tra assets mất agent, stopped instances, auto scaling và legacy nodes?
- **Metrics:** Đã công bố mẫu số, denominator assumptions, cutoff, coverage và evidence freshness?
- **On-time:** Đánh giá theo thời điểm **verified fixed state**, không chỉ install timestamp?
- **Exceptions:** Có risk owner, expiry, mitigation test và remediation schedule?
- **Findings:** Có root cause, owner, risk, closure criteria và retest evidence?
- **Security incident:** Khi nghi compromise đã phối hợp điều tra, containment và credentials rotation?
- **Audit:** Patch change/reboot/failure records được bảo vệ, không chứa secrets không cần thiết?
- **Continuous:** Có re-evaluate khi advisory, OS release, image, cluster, vendor hoặc exposure thay đổi?
- **Claims:** Kết luận chỉ bao gồm OS/fleet/advisory/time window đã được kiểm chứng?

## 23. Tổng kết

Với mỗi advisory ảnh hưởng đến hệ điều hành, security assurance cần trả lời tuần tự:

1. **Ai bị ảnh hưởng?** Asset identity, OS/build, package/kernel và exposure đã được đối chiếu từ inventory tin cậy chưa?
2. **Fix nào phù hợp?** Vendor advisory, fixed version/backport, dependencies và nguồn update đã được xác minh?
3. **Rủi ro và thời hạn?** Tình hình khai thác, business impact, deadline hoặc exception theo authority nào?
4. **Triển khai có an toàn?** Canary, maintenance, HA/quorum, backup và rollback/fail-forward được chuẩn bị?
5. **Bản vá có hiệu lực chưa?** Package/KB đã cài có cần reboot/restart/livepatch, và runtime thực sự đã chuyển sang fixed state?
6. **Hệ thống còn an toàn và hoạt động không?** Service health, IAM, KMS, audit, EDR và data integrity có đạt?
7. **Toàn bộ population được xử lý thế nào?** Có unknown, pending, failed, EOL, exception hoặc golden images còn vulnerable?
8. **Bằng chứng và follow-up?** Test logs, policy versions, reviewer, risk owner, finding closure và reassessment triggers đã có?

**Điều cần ghi nhớ:** **Patch hệ điều hành** không đơn thuần là chạy công cụ cập nhật. Nó là quy trình quản lý **rủi ro bảo mật và tính sẵn sàng** có thể kiểm chứng, từ **advisory → affected inventory → trusted fix → staged deployment → activation → runtime/security verification → evidence → remediation/retest**. Trong **security assurance**, chỉ được khẳng định “đã vá” khi **fixed state đã có hiệu lực trong phạm vi được xác định**, những bảo vệ bắt buộc vẫn hoạt động và **mẫu số tài sản cùng các trường hợp chưa đủ bằng chứng** được công bố trung thực.

# Bảo vệ runtime, phát hiện hành vi bất thường và phản ứng sự cố

## Mục tiêu bài học

Bảo mật workload không kết thúc khi máy ảo, container hoặc function được triển khai. Khi ứng dụng đang chạy, kẻ tấn công có thể khai thác lỗ hổng, chiếm credential, tạo tiến trình bất thường, thay đổi file, truy cập dữ liệu hoặc dùng tài nguyên compute để thực hiện hoạt động trái phép. Vì vậy, tổ chức cần bảo vệ runtime, quan sát hành vi thực tế và có quy trình phản ứng đủ nhanh để giới hạn thiệt hại.

Sau bài học này, bạn có thể:

- Áp dụng biện pháp hardening cho VM, container, Kubernetes và workload serverless.
- Phân biệt bảo vệ ở build time, deploy time và runtime.
- Chọn nguồn telemetry để theo dõi process, file, network, identity và hành vi cloud control plane.
- Xây dựng baseline và phát hiện hành vi bất thường có ngữ cảnh.
- Phân loại cảnh báo, điều tra sự cố và cô lập workload an toàn.
- Khôi phục dịch vụ từ artifact sạch, credential mới và dữ liệu đã xác minh.

## 1. Bảo mật runtime là gì?

Runtime là giai đoạn workload đang thực thi. Với máy ảo, runtime bao gồm hệ điều hành guest, process, service, kernel, agent và kết nối mạng. Với container, runtime còn gồm container engine, runtime class, namespace, cgroup, capabilities, volume mount và orchestration control plane. Với serverless, runtime do nhà cung cấp quản lý phần lớn, trong khi người dùng chịu trách nhiệm với mã ứng dụng, dependency, cấu hình, quyền truy cập và dữ liệu.

Bảo vệ runtime tập trung vào việc giữ workload trong trạng thái được phép, quan sát những gì đang xảy ra và phản ứng khi hành vi lệch khỏi thiết kế.

Một chương trình bảo mật thường có ba lớp kiểm soát:

| Giai đoạn | Câu hỏi chính | Ví dụ kiểm soát |
|---|---|---|
| Build time | Artifact có an toàn trước khi phát hành không? | Quét dependency, scan image, ký artifact, kiểm tra IaC |
| Deploy time | Workload được triển khai với quyền và cấu hình nào? | Admission policy, least privilege, network policy, image allowlist |
| Runtime | Workload đang thực hiện hành vi gì? | EDR, process/file/network telemetry, runtime detection, audit log |

Không lớp nào thay thế hoàn toàn lớp còn lại. Image sạch vẫn có thể bị khai thác khi chạy; runtime sensor có thể phát hiện hành vi bất thường nhưng không sửa được một cấu hình IAM quá rộng. Cần kết hợp preventive controls, detective controls và response controls.

~~~mermaid
flowchart LR
    A["Build: mã nguồn và artifact"] --> B["Deploy: cấu hình và quyền"]
    B --> C["Runtime: process, file, network"]
    C --> D["Telemetry và phát hiện"]
    D --> E["Phân loại cảnh báo"]
    E --> F["Cô lập và điều tra"]
    F --> G["Khôi phục và cải thiện"]
    G --> A
~~~

## 2. Xây dựng baseline an toàn cho workload

Baseline là tập cấu hình và hành vi được chấp nhận cho một workload. Baseline tốt phải gắn với vai trò của workload, môi trường và yêu cầu nghiệp vụ. Một web server, database, batch worker và bastion host có hành vi bình thường rất khác nhau.

Các thành phần baseline nên xác định:

- Hệ điều hành, kernel, runtime và phiên bản được hỗ trợ.
- Process/service được phép chạy và cách khởi động.
- User/group, service account và quyền truy cập tài nguyên.
- Thư mục có thể ghi, file cấu hình và vị trí lưu dữ liệu.
- Kết nối mạng đến/đi được phép, DNS và endpoint phụ thuộc.
- Mức CPU, memory, disk I/O và network thường gặp theo thời gian.
- Log cần thu thập, thời gian lưu và danh tính sở hữu workload.
- Cơ chế cập nhật, rollback và liên hệ chịu trách nhiệm.

Baseline không nên chỉ là một ảnh chụp tĩnh. Lưu lượng và mức sử dụng tài nguyên có thể thay đổi theo giờ, ngày, chiến dịch hoặc batch window. Hãy ghi nhận nhiều chu kỳ tải hợp lệ và gắn dữ liệu quan sát với phiên bản ứng dụng, thời điểm triển khai và thay đổi cấu hình.

Ví dụ, một worker xử lý hàng đợi có thể tăng CPU và network vào giờ cao điểm. Nếu chỉ đặt ngưỡng CPU cố định, hệ thống sẽ báo động giả. Cần kết hợp mức tải hàng đợi, số message xử lý, loại deployment và lịch hoạt động để hiểu biến động.

## 3. Hardening máy ảo

Máy ảo có ranh giới hệ điều hành riêng nhưng vẫn phụ thuộc hypervisor, image nền, network và danh tính cloud. Các biện pháp hardening nên bao gồm:

### 3.1. Hệ điều hành và dịch vụ

- Dùng image nền được phê duyệt và còn trong thời gian hỗ trợ.
- Cập nhật security patch cho OS, kernel, runtime và agent theo SLA.
- Gỡ hoặc vô hiệu hóa service, package, port và tài khoản không cần thiết.
- Bật Secure Boot hoặc cơ chế integrity phù hợp nếu instance type hỗ trợ.
- Bật host firewall và chỉ cho phép luồng mạng cần thiết.
- Dùng filesystem permission, SELinux hoặc AppArmor khi phù hợp.
- Đồng bộ thời gian để log và sự kiện từ nhiều nguồn có thể đối chiếu.
- Dùng EDR/endpoint protection tương thích với OS và workload.

### 3.2. Danh tính và quyền

- Mỗi service chạy bằng tài khoản riêng, không dùng local administrator hoặc root nếu không cần.
- Không dùng chung credential giữa các VM.
- Gán instance role hoặc managed identity với quyền tối thiểu.
- Không lưu access key dài hạn trong script, image hoặc file cấu hình.
- Giới hạn quyền đăng nhập tương tác và quản trị từ xa.
- Theo dõi thay đổi nhóm quản trị, scheduled task, service và startup item.

### 3.3. Bảo vệ dữ liệu và cấu hình

- Mã hóa volume và backup theo chính sách dữ liệu.
- Giới hạn quyền ghi vào thư mục thực thi và thư mục cấu hình.
- Đưa secret vào secret manager và lấy bằng workload identity.
- Bảo vệ log khỏi bị sửa hoặc xóa bởi tài khoản chạy ứng dụng.
- Tách volume dữ liệu khỏi hệ điều hành khi kiến trúc cần khả năng phục hồi độc lập.

Cần kiểm tra trạng thái hardening định kỳ và sau mỗi lần thay đổi image hoặc cấu hình. Một máy được cấu hình đúng hôm nay có thể lệch baseline sau thao tác hỗ trợ khẩn cấp hoặc cài thêm agent.

## 4. Hardening container và Kubernetes

Container giúp đóng gói ứng dụng nhưng không phải một ranh giới bảo mật tuyệt đối. Container chia sẻ kernel host; cấu hình quyền, namespace, runtime và volume có ảnh hưởng trực tiếp đến mức cô lập.

Các kiểm soát thường dùng:

| Kiểm soát | Mục đích |
|---|---|
| Chạy non-root | Giảm tác động khi process trong container bị chiếm |
| Read-only root filesystem | Hạn chế thay đổi file hệ thống trong container |
| Drop Linux capabilities | Loại bỏ quyền kernel không cần thiết |
| Seccomp | Giới hạn syscall được phép |
| AppArmor/SELinux | Áp dụng chính sách truy cập process và file |
| Resource requests/limits | Giới hạn CPU và memory, giảm ảnh hưởng tới workload khác |
| NetworkPolicy | Hạn chế kết nối giữa Pod và namespace |
| Image pinning và signature verification | Tránh chạy image ngoài danh sách hoặc bị thay thế |
| Admission policy | Chặn manifest vi phạm chính sách trước khi tạo workload |

Ví dụ security context trong Kubernetes:

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: orders-worker
spec:
  securityContext:
    runAsNonRoot: true
    runAsUser: 10001
    seccompProfile:
      type: RuntimeDefault
  containers:
    - name: worker
      image: registry.example.com/orders-worker:2.4.1
      securityContext:
        allowPrivilegeEscalation: false
        readOnlyRootFilesystem: true
        capabilities:
          drop:
            - ALL
      resources:
        requests:
          cpu: 250m
          memory: 256Mi
        limits:
          cpu: "1"
          memory: 512Mi
~~~

Ví dụ cần điều chỉnh theo ứng dụng. Một số process cần ghi vào thư mục tạm hoặc dùng capability cụ thể; hãy mount volume ghi riêng và chỉ thêm capability đã được chứng minh cần thiết. Không bật privileged mode, hostPID, hostNetwork hoặc mount container runtime socket nếu không có lý do được phê duyệt.

Với Kubernetes, cần bảo vệ cả control plane và node:

- RBAC theo namespace và resource; tránh quyền cluster-admin cho service account ứng dụng.
- Tắt automount service account token khi workload không cần gọi Kubernetes API.
- Bật audit policy phù hợp và chuyển audit log ra hệ thống tập trung.
- Bảo vệ kubelet, node OS, container runtime và credential truy cập cluster.
- Dùng NetworkPolicy hoặc cơ chế tương đương để giới hạn east-west traffic.
- Quản lý secret bằng encryption at rest và external secret manager.
- Kiểm tra image provenance, registry permission và quy trình admission.

## 5. Bảo vệ workload serverless

Với function hoặc dịch vụ serverless, nhà cung cấp thường quản lý host OS, hypervisor và một phần runtime infrastructure. Người dùng vẫn cần bảo vệ:

- Mã nguồn, package và dependency.
- Execution role hoặc service identity.
- Quyền truy cập event source, database, object storage và secret.
- Network egress, VPC connector và endpoint được gọi.
- Environment variable, function layer và artifact.
- Trigger, event permission, API authorization và logging.

Một số biện pháp thực hành:

1. Cấp execution role riêng cho từng function hoặc nhóm function có cùng trách nhiệm.
2. Chỉ cho phép function đọc/ghi đúng tài nguyên cần thiết.
3. Xác thực nguồn event và giới hạn ai được invoke function.
4. Không đưa secret dài hạn vào environment variable nếu có secret manager phù hợp.
5. Cập nhật runtime và dependency trước thời hạn deprecation của nhà cung cấp.
6. Đặt timeout, memory, concurrency và retry policy phù hợp để tránh vòng lặp hoặc chi phí ngoài dự kiến.
7. Theo dõi invocation bất thường, lỗi tăng đột biến và truy cập dữ liệu ngoài hành vi thông thường.

Serverless giảm trách nhiệm quản lý guest OS, nhưng không loại bỏ rủi ro từ mã ứng dụng, dependency, quyền IAM hoặc event giả mạo. Cần xem shared responsibility model của dịch vụ cụ thể để biết lớp nào do nhà cung cấp bảo vệ.

## 6. Telemetry cần thu thập ở runtime

Phát hiện hành vi bất thường cần dữ liệu đủ để trả lời ai đã làm gì, trên workload nào, vào thời điểm nào và qua đường nào.

| Nhóm telemetry | Ví dụ dữ liệu | Tín hiệu cần chú ý |
|---|---|---|
| Process | Tên, đường dẫn, parent process, user, command metadata, hash | Shell hoặc công cụ lạ xuất hiện trong service, process chain bất thường |
| File | Tạo, sửa, xóa, permission, owner, hash | Thay đổi binary, startup script, file cấu hình hoặc thư mục nhạy cảm |
| Network | Kết nối outbound/inbound, DNS, destination, port, bytes | Kết nối tới host hiếm gặp, beacon định kỳ, luồng dữ liệu tăng đột biến |
| Identity | Đăng nhập, token, role assumption, privilege change | Quyền tăng bất thường, danh tính lạ, đăng nhập từ nguồn mới |
| Resource | CPU, memory, disk, process count, network throughput | Mức sử dụng tăng không khớp với tải nghiệp vụ |
| Container/Kubernetes | Exec vào container, image, Pod create, secret access, RBAC change | Container mới ngoài pipeline, shell tương tác, privileged Pod |
| Cloud control plane | API call, resource creation, security group change, key operation | Thay đổi hạ tầng hoặc quyền ngoài change window |

Nguồn dữ liệu thường gồm:

- EDR/endpoint agent trên VM.
- Linux audit framework, journald, system logs và telemetry từ kernel.
- Windows Security log, Sysmon và Microsoft Defender for Endpoint khi được triển khai.
- Container runtime sensor hoặc eBPF-based sensor.
- Kubernetes audit log, admission events và workload metadata.
- Cloud audit trail, IAM logs, flow logs và dịch vụ threat detection.
- Application log, trace, metric và business event.

Chỉ thu thập dữ liệu cần thiết và bảo vệ log như tài sản nhạy cảm. Command line, file path, IP, username và event payload có thể chứa dữ liệu cá nhân hoặc thông tin nội bộ. Thiết lập quyền đọc, thời hạn lưu, masking và audit truy cập log.

## 7. Phát hiện hành vi bất thường

Một tín hiệu đơn lẻ thường chưa đủ để kết luận sự cố. CPU tăng có thể do batch hợp lệ; process shell có thể do script bảo trì; kết nối outbound mới có thể do bản cập nhật. Detection nên kết hợp nhiều tín hiệu và ngữ cảnh.

### 7.1. Nhóm hành vi đáng quan sát

**Thực thi process bất thường**

- Process con không thường xuất hiện dưới service account.
- Shell hoặc công cụ quản trị được gọi từ web server, database hoặc container ứng dụng.
- Binary chạy từ thư mục tạm, thư mục người dùng hoặc đường dẫn không thuộc image.
- Process có quyền cao nhưng không có change record tương ứng.

**Thay đổi persistence hoặc cấu hình**

- Scheduled task, cron job, systemd service hoặc startup item mới.
- Thay đổi file binary, SSH authorized keys, Windows service hoặc registry autorun.
- Thay đổi security policy, firewall hoặc agent bảo vệ.
- Container image hoặc deployment được thay đổi ngoài pipeline.

**Mạng và dữ liệu**

- Workload kết nối tới domain/IP hiếm gặp hoặc quốc gia/vùng không nằm trong mô hình vận hành.
- Lưu lượng outbound tăng đột ngột không giải thích được bằng số request.
- Một workload bắt đầu quét nhiều địa chỉ hoặc port nội bộ.
- Tài khoản ứng dụng đọc lượng dữ liệu lớn ngoài mẫu thông thường.

**Danh tính và quyền**

- Instance role hoặc service account được cấp thêm quyền nhạy cảm.
- Có token hoặc credential được dùng từ workload khác với dự kiến.
- Nhiều lần xác thực thất bại trước khi đăng nhập thành công.
- Quyền truy cập secret hoặc key tăng bất thường.

### 7.2. Kết hợp ngữ cảnh

Để giảm false positive, kết hợp sự kiện với:

- Owner, môi trường và business criticality của workload.
- Phiên bản image, container image digest và release ID.
- Change window, deployment event và ticket được phê duyệt.
- Service account, role và quyền kỳ vọng.
- Baseline theo giờ, ngày và mức tải.
- Topology mạng, dependency và endpoint đã cho phép.

Ví dụ: một container web phát sinh process shell, sau đó tải binary từ domain mới và mở kết nối outbound tới IP chưa từng thấy. Ba sự kiện trong một khoảng ngắn đáng ưu tiên điều tra hơn từng sự kiện riêng lẻ.

~~~mermaid
flowchart TD
    A["Telemetry: process / file / network / identity"] --> B["Chuẩn hóa và gắn workload context"]
    B --> C["So sánh baseline và policy"]
    C --> D{"Có tín hiệu bất thường?"}
    D -->|Không| E["Lưu log và tiếp tục quan sát"]
    D -->|Có| F["Tương quan nhiều tín hiệu"]
    F --> G{"Mức độ và độ tin cậy"}
    G -->|Thấp| H["Theo dõi / enrich"]
    G -->|Cao| I["Tạo incident và phản ứng"]
~~~

### 7.3. Ví dụ logic phát hiện

Một quy tắc phát hiện ở mức khái niệm:

~~~text
IF
  workload.role = "web-api"
  AND process.parent = "web-server"
  AND process.name IN ("sh", "bash", "powershell")
  AND NOT event.matches_approved_maintenance
THEN
  raise alert "Unexpected interactive shell from web workload"
  enrich with workload owner, image digest, user and network activity
~~~

Đây là logic minh họa, không phải cú pháp của một sản phẩm SIEM/EDR cụ thể. Khi triển khai, cần xác định trường dữ liệu thực tế, danh sách ngoại lệ có thời hạn và ngưỡng phù hợp. Không nên cho phép một ngoại lệ rộng như bỏ qua mọi shell trong toàn bộ namespace.

## 8. Phân loại cảnh báo và ưu tiên xử lý

Không phải mọi cảnh báo runtime đều cần cô lập ngay. Đội vận hành cần đánh giá mức độ nghiêm trọng, độ tin cậy và phạm vi ảnh hưởng.

| Mức ưu tiên | Ví dụ | Hành động ban đầu |
|---|---|---|
| Critical | Credential production bị dùng trái phép, mã độc đang thực thi, dữ liệu nhạy cảm có dấu hiệu bị lấy đi | Kích hoạt incident response, cô lập có kiểm soát và thông báo nhóm ứng cứu |
| High | Process/persistence bất thường trên workload quan trọng, privilege escalation có bằng chứng | Điều tra ngay, giới hạn network/identity và bảo toàn evidence |
| Medium | Một tín hiệu lạ chưa có bằng chứng xâm nhập, thay đổi ngoài change window | Enrich telemetry, xác minh owner và change record |
| Low | Sai cấu hình hoặc hoạt động khác baseline nhưng đã có lời giải thích hợp lệ | Ghi nhận, điều chỉnh baseline/policy nếu cần |

Khi đánh giá alert, ghi nhận:

- Workload và tài sản bị ảnh hưởng.
- Danh tính hoặc process liên quan.
- Thời điểm đầu tiên và lần cuối quan sát.
- Hành vi cụ thể, nguồn log và độ tin cậy.
- Dữ liệu hoặc hệ thống có thể bị ảnh hưởng.
- Trạng thái cô lập và người đang phụ trách.
- Bước tiếp theo và thời hạn cập nhật.

Không tự động đóng cảnh báo chỉ vì owner xác nhận có deployment. Cần đối chiếu image digest, pipeline run, commit, thời điểm và hành vi thực tế.

## 9. Quy trình phản ứng sự cố runtime

Một quy trình incident response thường gồm chuẩn bị, phát hiện/phân tích, containment, eradication, recovery và lessons learned.

~~~mermaid
flowchart TD
    A["Chuẩn bị: owner, log, runbook, quyền khẩn cấp"] --> B["Phát hiện và xác minh"]
    B --> C["Đánh giá phạm vi và mức độ"]
    C --> D["Containment: cô lập có kiểm soát"]
    D --> E["Bảo toàn evidence và điều tra"]
    E --> F["Eradication: loại bỏ nguyên nhân"]
    F --> G["Recovery từ artifact sạch"]
    G --> H["Theo dõi tái xâm nhập"]
    H --> I["Lessons learned và cập nhật baseline"]
~~~

### 9.1. Chuẩn bị trước sự cố

- Xác định incident commander, security contact, platform owner và người phê duyệt hành động khẩn cấp.
- Duy trì inventory VM, container, cluster, function, role và dependency.
- Bật log tập trung, đồng bộ thời gian và kiểm tra khả năng truy vấn.
- Chuẩn bị quy trình cô lập mạng, thu hồi credential và khôi phục workload.
- Kiểm thử runbook và quyền break-glass trong môi trường an toàn.
- Lưu sẵn image sạch, deployment manifest, backup và hướng dẫn restore.

### 9.2. Xác minh và đánh giá phạm vi

Khi nhận cảnh báo:

1. Xác minh alert có nguồn telemetry đáng tin và thời gian chính xác.
2. Xác định workload, host, container, namespace, function và danh tính liên quan.
3. Đối chiếu deployment, change record, owner và baseline.
4. Tìm process cha/con, file thay đổi, kết nối mạng và hoạt động identity liên quan.
5. Kiểm tra dấu hiệu tương tự trên workload khác dùng cùng image, role hoặc credential.
6. Xác định dữ liệu có thể đã bị đọc, sửa, mã hóa hoặc truyền ra ngoài.

Giữ lại timeline theo UTC hoặc một chuẩn thời gian thống nhất. Điều này giúp đối chiếu log giữa VM, cloud control plane, EDR và ứng dụng.

### 9.3. Containment: cô lập nhưng giữ khả năng điều tra

Mục tiêu là ngăn hoạt động gây hại tiếp tục và giới hạn lateral movement. Biện pháp phụ thuộc loại workload:

- VM: chuyển sang security group cô lập, chặn egress hoặc cách ly qua EDR theo playbook.
- Container: ngừng nhận traffic, cô lập namespace/network policy hoặc thay replica bằng workload sạch sau khi bảo toàn evidence cần thiết.
- Kubernetes: chặn service account/token bị lạm dụng, giới hạn network và ngăn rollout không được phê duyệt.
- Serverless: tạm vô hiệu hóa trigger, giới hạn invocation, thu hồi quyền hoặc chuyển function sang phiên bản an toàn.
- Identity: vô hiệu hóa token/session, xoay vòng secret và thu hồi role binding theo đánh giá tác động.

Không phải lúc nào cũng nên tắt máy hoặc xóa container ngay. Việc đó có thể làm mất dữ liệu volatile, process state hoặc evidence cần cho điều tra. Với sự cố nghiêm trọng, phối hợp security và platform team để chọn giữa network isolation, snapshot, memory capture và shutdown theo runbook. Nếu dữ liệu đang bị exfiltrate hoặc phá hoại, containment nhanh có thể được ưu tiên; ghi lại quyết định và bằng chứng còn giữ được.

### 9.4. Bảo toàn evidence

- Ghi lại alert ID, host/Pod/function ID, image digest và thời điểm.
- Xuất log liên quan từ EDR, OS, Kubernetes và cloud audit.
- Bảo toàn snapshot hoặc disk image theo quy trình pháp chứng được tổ chức phê duyệt.
- Ghi nhận người thu thập, nguồn, thời gian, hash và nơi lưu evidence.
- Giới hạn quyền truy cập evidence và duy trì chain of custody.
- Tránh phân tích trực tiếp trên bản gốc nếu có thể tạo bản sao làm việc.

Snapshot phục vụ điều tra cần được mã hóa, phân quyền và giữ theo retention pháp chứng. Không gắn snapshot chứa dữ liệu production vào máy phân tích không được cô lập.

### 9.5. Eradication và recovery

Sau khi đã xác định nguyên nhân và phạm vi:

1. Loại bỏ persistence, malware, workload hoặc cấu hình bị xâm phạm.
2. Vá lỗ hổng và sửa nguyên nhân gốc.
3. Thu hồi hoặc xoay vòng credential, token, key và certificate có khả năng bị lộ.
4. Xây dựng lại VM/container/function từ image hoặc artifact sạch đã xác minh.
5. Áp dụng quyền IAM và network policy đã được rà soát.
6. Khôi phục dữ liệu từ backup đáng tin cậy; kiểm tra tính toàn vẹn trước khi mở traffic.
7. Theo dõi process, network, identity và resource sau khi phục hồi để phát hiện tái xâm nhập.

Không sao chép nguyên trạng toàn bộ filesystem của workload bị xâm phạm sang máy mới nếu chưa biết persistence nằm ở đâu. Khôi phục dữ liệu cần thiết theo quy trình kiểm tra riêng và giữ lại evidence để điều tra.

## 10. Ví dụ playbook: container có hành vi bất thường

Giả sử EDR/runtime sensor phát hiện container của dịch vụ API khởi chạy shell. Sau đó container tạo file thực thi trong thư mục tạm và kết nối outbound tới một địa chỉ chưa có trong baseline.

Một playbook có thể thực hiện:

1. Tạo incident, gắn owner, namespace, Pod UID, node, image digest và thời điểm.
2. Kiểm tra deployment event, pipeline run, commit và ticket thay đổi gần nhất.
3. Thu thập process tree, file metadata/hash, network connection và log ứng dụng.
4. Kiểm tra các Pod khác cùng image digest hoặc service account có hành vi tương tự không.
5. Nếu xác suất xâm nhập cao, chặn egress hoặc cô lập Pod/namespace theo playbook; giữ bản sao evidence.
6. Xác định service account/token có bị dùng để truy cập Kubernetes API hoặc cloud resource không.
7. Thu hồi token/secret có khả năng bị lộ và rà soát IAM audit.
8. Triển khai lại từ image sạch đã ký, cập nhật dependency và policy admission.
9. Chạy smoke test, xác nhận network egress hợp lệ và theo dõi cảnh báo tương tự.
10. Ghi nhận nguyên nhân, phạm vi, thời gian phát hiện, thời gian containment và hành động phòng ngừa.

Nếu shell được tạo bởi một init script hợp lệ, đối chiếu nội dung script, image digest và pipeline. Chỉ thêm ngoại lệ sau khi xác minh và giới hạn ngoại lệ theo workload, process path hoặc phiên bản cụ thể.

## 11. Tích hợp detection với SIEM và hệ thống vận hành

EDR, runtime sensor, cloud audit và application telemetry thường phát ra nhiều định dạng khác nhau. SIEM hoặc nền tảng detection tập trung giúp chuẩn hóa, tương quan và điều phối cảnh báo.

Một kiến trúc tham khảo:

~~~mermaid
flowchart TD
    VM["VM: EDR / OS audit"] --> COL["Collector / telemetry pipeline"]
    K8S["Container: runtime sensor / audit"] --> COL
    SF["Serverless: function / IAM logs"] --> COL
    CLOUD["Cloud control plane / flow logs"] --> COL
    APP["Application logs / traces"] --> COL
    COL --> SIEM["SIEM / detection engine"]
    SIEM --> SOAR["Incident workflow / SOAR"]
    SOAR --> TEAM["Security + Platform + App owner"]
    SOAR --> CASE["Case, evidence và timeline"]
~~~

Khi tích hợp, cần thống nhất các trường như timestamp, cloud account/project, region, resource ID, workload name, namespace, image digest, principal, source IP và event category.

Một alert hữu ích cần có:

- Tóm tắt hành vi và lý do phát hiện.
- Workload/identity liên quan và mức độ quan trọng.
- Thời điểm, nguồn telemetry và đường dẫn truy vấn log.
- Deployment/change context.
- Gợi ý kiểm tra tiếp theo và playbook phù hợp.
- Người hoặc nhóm chịu trách nhiệm.

Tự động hóa containment chỉ nên bật với điều kiện rõ ràng, phạm vi giới hạn và có cơ chế kiểm soát tác động. Ví dụ, tự động chặn một kết nối egress có thể an toàn cho một workload stateless, nhưng cô lập database primary có thể gây gián đoạn lớn. Với hành động ảnh hưởng production, cần phê duyệt hoặc policy đã được kiểm thử trước.

## 12. Đo hiệu quả phát hiện và phản ứng

Một số chỉ số vận hành giúp đánh giá hệ thống:

| Chỉ số | Ý nghĩa | Cách dùng |
|---|---|---|
| MTTD | Mean Time to Detect, thời gian trung bình để phát hiện | Đánh giá khả năng quan sát và detection |
| MTTA | Mean Time to Acknowledge, thời gian trung bình để có người nhận xử lý | Đánh giá trực ca và phân công |
| MTTC | Mean Time to Contain, thời gian trung bình để giới hạn sự cố | Đánh giá runbook và quyền phản ứng |
| MTTR | Mean Time to Recover/Respond, cần định nghĩa rõ trong tổ chức | Theo dõi thời gian khôi phục hoặc xử lý |
| False positive rate | Tỷ lệ cảnh báo không phải sự cố thực | Đánh giá chất lượng rule và baseline |
| Coverage | Tỷ lệ workload quan trọng có telemetry và policy phù hợp | Phát hiện vùng mù giám sát |
| Restore success rate | Tỷ lệ bài kiểm thử phục hồi thành công | Đánh giá khả năng khôi phục |

Không tối ưu chỉ số bằng cách hạ mức cảnh báo hoặc tự động đóng ticket. Cần đo cả chất lượng phát hiện, mức độ bỏ sót, tác động tới vận hành và khả năng phục hồi.

## 13. Những lỗi thường gặp

**Chỉ bảo vệ image mà không giám sát runtime:** artifact sạch có thể bị khai thác sau khi triển khai. Kết hợp image scanning với runtime telemetry và response playbook.

**Thu thập quá nhiều log nhưng không có ngữ cảnh:** cảnh báo khó ưu tiên và điều tra tốn thời gian. Gắn log với workload owner, image digest, deployment và identity.

**Đặt ngưỡng tài nguyên cố định:** batch hoặc autoscaling có thể tạo cảnh báo giả. Dùng baseline theo loại workload, thời gian và tải nghiệp vụ.

**Cho rằng container là ranh giới bảo mật hoàn chỉnh:** container chia sẻ kernel và có thể được cấp quyền host quá rộng. Chạy non-root, drop capability, giới hạn mount và bảo vệ node.

**Dùng chung service account hoặc instance role:** một workload bị chiếm có thể truy cập nhiều tài nguyên không liên quan. Tách danh tính theo workload và quyền tối thiểu.

**Tự động xóa workload khi có cảnh báo:** có thể làm mất evidence hoặc gây gián đoạn. Xác định trước điều kiện cô lập, thu thập evidence và hành động tự động.

**Cô lập nhưng không thu hồi credential:** kẻ tấn công có thể dùng token bị đánh cắp từ workload khác. Rà soát identity và xoay vòng credential trong phạm vi ảnh hưởng.

**Khôi phục từ image hoặc backup chưa xác minh:** có thể đưa persistence trở lại môi trường. Dùng artifact sạch, kiểm tra provenance và xác minh dữ liệu trước khi phục hồi.

**Không kiểm thử runbook:** quyền cô lập hoặc truy vấn log có thể không hoạt động khi khẩn cấp. Diễn tập định kỳ và cập nhật theo thay đổi kiến trúc.

## 14. Checklist bảo vệ runtime và phản ứng sự cố

- [ ] Mỗi workload có owner, môi trường, mức độ quan trọng và baseline được ghi nhận.
- [ ] VM được vá, harden, giới hạn service và dùng EDR phù hợp.
- [ ] Container chạy non-root, giới hạn capability, syscall, filesystem và network.
- [ ] Kubernetes RBAC, service account, audit log và admission policy được kiểm soát.
- [ ] Serverless function dùng execution role riêng và trigger được xác thực.
- [ ] Secret được cấp qua workload identity/secret manager và có thể xoay vòng.
- [ ] Có telemetry về process, file, network, identity và cloud control plane.
- [ ] Alert được tương quan với deployment, change window và workload owner.
- [ ] Có playbook phân loại, cô lập, thu thập evidence, eradication và recovery.
- [ ] Có cách cô lập VM/container/function mà không vô tình xóa evidence quan trọng.
- [ ] Log và evidence được bảo vệ, đồng bộ thời gian và giới hạn truy cập.
- [ ] Workload được dựng lại từ artifact sạch và dữ liệu được xác minh.
- [ ] Đã diễn tập incident response và kiểm tra quyền break-glass.
- [ ] Đã đo MTTD, MTTA, MTTC, MTTR và coverage theo định nghĩa thống nhất.
- [ ] Lessons learned được chuyển thành thay đổi baseline, policy và pipeline.

Bảo vệ runtime cần kết hợp hardening, telemetry, phát hiện theo ngữ cảnh và quy trình phản ứng có thể thực thi. Hãy xác định hành vi bình thường của từng workload, theo dõi process, file, network và identity, rồi tương quan tín hiệu với thay đổi triển khai. Khi có sự cố, đánh giá phạm vi, cô lập có kiểm soát, bảo toàn evidence, thu hồi credential bị ảnh hưởng và khôi phục từ artifact sạch. Diễn tập định kỳ giúp đội ngũ phản ứng nhanh mà vẫn giữ được khả năng điều tra và tính sẵn sàng của dịch vụ.

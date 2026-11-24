# Viết runbook, timeline sự cố và hành động ngăn tái diễn

## 1. Vì sao cần runbook và timeline sự cố?

Khi workload compute gặp sự cố, đội vận hành thường phải xử lý trong điều kiện thiếu thời gian và thông tin chưa đầy đủ. VM không khởi động, container liên tục restart, function timeout, GPU job bị treo hoặc storage/network bị nghẽn đều có thể làm dịch vụ suy giảm. Nếu mỗi người xử lý theo kinh nghiệm riêng, nhóm dễ bỏ sót bước quan trọng, thực hiện thao tác rủi ro hoặc không ghi lại được diễn biến để điều tra sau đó.

**Runbook** là hướng dẫn vận hành cho một tình huống cụ thể. Nó mô tả dấu hiệu nhận biết, phạm vi ảnh hưởng, kiểm tra an toàn, các bước xử lý, điều kiện dừng, phương án khôi phục và cách xác nhận dịch vụ đã ổn định. Runbook tốt giúp người trực hành động nhất quán ngay cả khi họ không phải người xây dựng hệ thống.

**Incident timeline** là dòng thời gian ghi lại các sự kiện và quyết định trong sự cố: thời điểm bắt đầu, lúc phát hiện, lúc xác nhận ảnh hưởng, hành động giảm thiểu, thời điểm phục hồi và các thay đổi tiếp theo. Timeline cung cấp dữ liệu để hiểu sự cố đã diễn ra như thế nào, đánh giá thời gian phản ứng và xác định khoảng trống trong giám sát hoặc quy trình.

Sau khi dịch vụ phục hồi, nhóm cần xác định nguyên nhân, yếu tố góp phần và hành động ngăn tái diễn. Mục tiêu là giảm xác suất sự cố tương tự, rút ngắn thời gian phát hiện/khôi phục và giảm mức độ ảnh hưởng. Việc này cần dựa trên bằng chứng và trách nhiệm rõ ràng, không chỉ kết thúc bằng một báo cáo mô tả.

Trong module **CLOUD_CORE_SERVICES_COMPUTE**, các sự cố có thể xuất hiện ở VM, container, serverless, CPU, bộ nhớ, GPU, storage, network, IAM hoặc nền tảng cloud. Bài học này hướng dẫn cách biến kinh nghiệm xử lý thành quy trình có thể lặp lại và cải thiện.

Sau bài học, người học có thể:

- Phân biệt incident, alert, symptom, cause, mitigation và recovery.
- Thiết kế runbook có phạm vi, precondition, bước kiểm tra, hành động an toàn và tiêu chí kết thúc.
- Tạo timeline có timestamp, nguồn bằng chứng, quyết định và người thực hiện.
- Điều phối incident response, phân vai và truyền đạt trạng thái.
- Chẩn đoán sự cố compute theo lớp từ ứng dụng đến hạ tầng cloud.
- Viết post-incident review và chuyển phát hiện thành hành động ngăn tái diễn có owner, deadline và tiêu chí xác minh.

## 2. Những khái niệm cần thống nhất

### 2.1. Alert, event và incident

- **Alert:** thông báo được tạo khi một điều kiện giám sát xảy ra, chẳng hạn CPU throttling cao hoặc filesystem sắp đầy.
- **Event:** một sự kiện có thời điểm, ví dụ pod bị evict, instance reboot, deployment bắt đầu hoặc cloud API từ chối cấp quota.
- **Incident:** tình huống gây hoặc có nguy cơ gây ảnh hưởng đáng kể đến dịch vụ, người dùng, dữ liệu, bảo mật hoặc hoạt động kinh doanh và cần được điều phối xử lý.

Một alert không nhất thiết là incident. CPU có thể cao trong batch job mà không ảnh hưởng SLO. Ngược lại, một sự cố có thể không tạo alert nếu metric không được thu thập hoặc ngưỡng đặt sai. Cần đánh giá tác động dịch vụ thay vì chỉ dựa vào số lượng cảnh báo.

### 2.2. Symptom, trigger và root cause

**Symptom** là biểu hiện quan sát được, ví dụ request timeout, pod restart hoặc queue backlog tăng. **Trigger** là sự kiện trực tiếp làm sự cố bắt đầu, chẳng hạn deploy phiên bản mới hoặc quota bị chạm. **Root cause** là nguyên nhân nền tảng khiến hệ thống có thể rơi vào trạng thái lỗi, ví dụ thiếu kiểm soát memory growth hoặc thiếu capacity dự phòng.

Một sự cố có thể có nhiều yếu tố góp phần. Ví dụ, một deployment làm tăng memory usage; container limit quá thấp khiến pod bị OOMKilled; replica count không đủ và autoscaler không scale được vì quota; alert lại chỉ theo dõi memory trung bình toàn cluster. Chỉ sửa phiên bản ứng dụng có thể giảm triệu chứng nhưng chưa giải quyết quota và khoảng trống giám sát.

### 2.3. Mitigation, recovery và resolution

- **Mitigation:** hành động làm giảm ảnh hưởng ngay, ví dụ chuyển traffic, giảm concurrency, tắt một tính năng hoặc scale thêm capacity.
- **Recovery:** đưa dịch vụ và dữ liệu về trạng thái hoạt động được xác minh.
- **Resolution:** sự cố được coi là kết thúc theo tiêu chí đã thống nhất, sau khi xác nhận các chức năng chính và theo dõi đủ thời gian.

Mitigation không nhất thiết sửa root cause. Ví dụ, tăng số instance có thể khôi phục throughput tạm thời nhưng nếu retry storm vẫn tồn tại, sự cố có thể tái diễn. Timeline và post-incident review cần phân biệt rõ thời điểm giảm ảnh hưởng với thời điểm xử lý nguyên nhân.

### 2.4. Runbook, playbook và post-incident review

Runbook thường tập trung vào quy trình kỹ thuật cho một tình huống cụ thể. Playbook có thể bao quát quy trình điều phối rộng hơn, gồm vai trò, truyền thông, quyết định và nhiều runbook liên quan. Post-incident review (PIR) hoặc postmortem ghi lại tác động, diễn biến, nguyên nhân và hành động cải thiện sau sự cố.

Các tài liệu này nên liên kết với nhau. Alert dẫn đến runbook; runbook chỉ ra dashboard, log query và người cần liên hệ; incident record lưu timeline; PIR tham chiếu incident record và tạo action item.

## 3. Quy trình phản ứng sự cố compute

### 3.1. Nhận diện và xác nhận

Khi nhận alert hoặc báo cáo từ người dùng, xác minh:

1. Dịch vụ, workload, môi trường và region nào bị ảnh hưởng?
2. Ảnh hưởng là lỗi hoàn toàn, suy giảm hiệu năng hay nguy cơ sắp xảy ra?
3. Bao nhiêu người dùng, request, job hoặc tenant bị tác động?
4. Sự cố bắt đầu từ thời điểm nào và kéo dài bao lâu?
5. Có thay đổi gần đây như deploy, resize, patch, IAM policy hoặc network change không?
6. Dữ liệu có nguy cơ mất, sai lệch hoặc không nhất quán không?
7. Có dấu hiệu bảo mật hoặc truy cập trái phép cần kích hoạt quy trình riêng không?

Không chờ đủ mọi thông tin mới mở incident nếu tác động nghiêm trọng đã rõ. Có thể mở incident với thông tin ban đầu, sau đó cập nhật khi bằng chứng đầy đủ hơn.

### 3.2. Phân loại severity

Mức độ nghiêm trọng nên phản ánh tác động và tốc độ suy giảm, không chỉ loại tài nguyên bị lỗi.

| Mức | Tình trạng tham khảo | Cách điều phối |
|---|---|---|
| SEV-1 / Critical | Dịch vụ cốt lõi ngừng hoạt động, mất dữ liệu hoặc ảnh hưởng diện rộng; SLO bị vi phạm nghiêm trọng | Kích hoạt incident command, on-call chính và dự phòng, cập nhật lãnh đạo/khách hàng theo quy trình |
| SEV-2 / High | Một chức năng quan trọng suy giảm đáng kể, lỗi lan rộng hoặc headroom sắp cạn | Điều phối nhóm liên quan, cập nhật trạng thái định kỳ, ưu tiên mitigation |
| SEV-3 / Medium | Ảnh hưởng giới hạn, có workaround và chưa gây gián đoạn lớn | Giao owner xử lý, theo dõi và cập nhật theo SLA nội bộ |
| SEV-4 / Low | Lỗi nhỏ, cảnh báo dự báo hoặc vấn đề không ảnh hưởng trực tiếp người dùng | Tạo ticket/runbook improvement, xử lý theo kế hoạch |

Tên severity và ngưỡng cụ thể tùy tổ chức. Cần quy định rõ ai có quyền nâng/hạ severity và điều kiện kết thúc incident.

### 3.3. Thiết lập vai trò điều phối

Với sự cố lớn, phân vai giúp kỹ sư tập trung xử lý mà vẫn giữ được thông tin và quyết định:

- **Incident Commander (IC):** điều phối tổng thể, ưu tiên công việc, quyết định escalation và xác nhận trạng thái.
- **Technical Lead:** dẫn dắt chẩn đoán kỹ thuật, đề xuất mitigation và kiểm soát thay đổi.
- **Operations/Responders:** thực hiện kiểm tra, lệnh vận hành và khôi phục theo runbook.
- **Communications Lead:** cập nhật stakeholder, người dùng hoặc bộ phận hỗ trợ theo nhịp đã thống nhất.
- **Scribe:** ghi timeline, quyết định, bằng chứng, người thực hiện và kết quả.
- **Service Owner:** xác nhận hành vi nghiệp vụ và tiêu chí phục hồi của workload.

Trong sự cố nhỏ, một người có thể kiêm nhiều vai trò. Với SEV-1/2, nên tách người ghi timeline khỏi người thực hiện thay đổi để tránh mất thông tin.

### 3.4. Contain, mitigate và recover

Thứ tự ưu tiên thường là bảo vệ người dùng và dữ liệu, sau đó ổn định dịch vụ, rồi mới điều tra sâu. Các hành động mitigation có thể gồm:

- Chuyển traffic sang vùng hoặc backend khỏe.
- Scale thêm capacity nếu quota và dependency cho phép.
- Giảm concurrency hoặc bật backpressure để tránh quá tải dây chuyền.
- Rollback deployment hoặc chuyển về image/runtime trước đó.
- Cordon/drain node lỗi và reschedule workload.
- Failover database theo runbook, xác minh replication và consistency.
- Tạm dừng job batch hoặc consumer không thiết yếu.
- Cô lập tài nguyên có dấu hiệu bị xâm nhập theo quy trình security incident.

Không thực hiện hành động phá hủy như xóa volume, format disk, force-delete stateful workload hoặc thay đổi IAM diện rộng khi chưa hiểu tác động và chưa có phê duyệt cần thiết. Nếu dữ liệu có nguy cơ bị ghi sai, ưu tiên dừng luồng ghi theo quy trình bảo toàn dữ liệu.

### 3.5. Xác minh phục hồi

Dịch vụ chỉ được xem là phục hồi khi các kiểm tra kỹ thuật và nghiệp vụ đều đạt. Kiểm tra health endpoint, error rate, latency, throughput, queue backlog, database replication, dữ liệu mẫu và thao tác người dùng chính. Theo dõi trong observation period phù hợp để bảo đảm lỗi không quay lại khi tải tăng.

Ghi riêng thời điểm mitigation, thời điểm chức năng chính hoạt động trở lại và thời điểm incident được đóng. Ba thời điểm này có thể khác nhau đáng kể.

## 4. Thiết kế runbook có thể sử dụng trong sự cố

### 4.1. Cấu trúc tối thiểu

Một runbook nên có các phần:

1. **Tên và mục đích:** tình huống nào được xử lý, kết quả mong muốn là gì.
2. **Phạm vi:** dịch vụ, môi trường, region, loại compute và thành phần liên quan.
3. **Owner và escalation:** nhóm chịu trách nhiệm, người trực, đầu mối dự phòng.
4. **Trigger:** alert, triệu chứng hoặc event dùng để kích hoạt.
5. **Severity guidance:** điều kiện nâng cấp mức độ sự cố.
6. **Preconditions:** quyền truy cập, backup, replica, capacity và phê duyệt cần có.
7. **Diagnostic steps:** lệnh hoặc dashboard kiểm tra theo thứ tự ít rủi ro.
8. **Mitigation:** hành động giảm ảnh hưởng, kèm điều kiện được phép thực hiện.
9. **Recovery/rollback:** cách khôi phục, tiêu chí dừng và phương án thay thế.
10. **Validation:** kiểm tra kỹ thuật, nghiệp vụ và observation period.
11. **Evidence:** log, metric, trace, event và vị trí lưu incident record.
12. **Follow-up:** tài liệu liên quan và hành động sau sự cố.

### 4.2. Viết bước kiểm tra rõ ràng

Mỗi bước nên nêu mục đích, thao tác, kết quả mong đợi và cách xử lý nếu kết quả khác dự kiến. Tránh viết “kiểm tra server” hoặc “restart nếu cần” vì không chỉ ra cần xem gì và ai có quyền quyết định.

Ví dụ:

| Thành phần | Hướng dẫn mơ hồ | Hướng dẫn có thể thực hiện |
|---|---|---|
| Disk | Kiểm tra ổ đĩa | Xác định mount point bị ảnh hưởng, phần trăm và byte còn trống, inode, tốc độ tăng trong 1 giờ; đối chiếu owner và retention trước khi dọn dẹp |
| Memory | Xem RAM | Xác định process/container có RSS hoặc working set tăng, kiểm tra OOM event và giới hạn memory; đối chiếu thời điểm với deployment |
| Kubernetes | Kiểm tra pod | Lấy namespace, pod, node, restart count, last termination reason và events; kiểm tra PDB trước khi drain |
| Network | Kiểm tra kết nối | Xác định source/destination, port, DNS resolution, route, security policy, packet loss và thời điểm lỗi |
| Cloud quota | Tăng quota | Xác định quota name, account/region, usage hiện tại, nhu cầu forecast và thời gian phê duyệt; chuẩn bị fallback nếu chưa được tăng |

### 4.3. Phân biệt lệnh chỉ đọc và lệnh thay đổi trạng thái

Runbook nên đánh dấu rõ lệnh chẩn đoán chỉ đọc với lệnh có thể thay đổi hệ thống. Ví dụ, `df -h`, `free -m`, `systemctl status` và `kubectl get` thường dùng để quan sát; `systemctl restart`, `kubectl delete`, thay đổi firewall hoặc failover database có thể gây gián đoạn.

Với lệnh thay đổi trạng thái, ghi rõ:

- Điều kiện tiên quyết và quyền cần có.
- Phạm vi tác động, resource ID và môi trường.
- Người phê duyệt hoặc người xác nhận nếu cần.
- Kết quả mong đợi và thời gian chờ.
- Điều kiện dừng hoặc rollback.
- Cách xác minh sau thao tác.

Không đưa token, mật khẩu, private key hoặc dữ liệu nhạy cảm vào runbook. Dùng secret manager hoặc cơ chế cấp credential tạm thời.

### 4.4. Runbook phải được kiểm thử

Runbook chưa được thử trong môi trường tương đương chỉ là tài liệu giả định. Kiểm thử định kỳ bằng tabletop exercise, staging drill hoặc game day. Ghi lại bước không rõ, lệnh lỗi do phiên bản khác, quyền thiếu, dashboard không còn tồn tại và thời gian thực tế để cập nhật tài liệu.

Mỗi runbook cần có version, owner, ngày review gần nhất và lịch review tiếp theo. Khi kiến trúc, alert, tên resource hoặc quyền truy cập thay đổi, cập nhật runbook cùng change đó.

## 5. Quy trình chẩn đoán theo lớp compute

### 5.1. Bắt đầu từ phạm vi ảnh hưởng

Trước khi đi sâu vào một máy, xác định lỗi ảnh hưởng một instance, một node, một zone, một region hay toàn bộ dịch vụ. So sánh tài nguyên lỗi với tài nguyên khỏe cùng loại. Nếu nhiều workload khác nhau cùng lỗi ở một thời điểm, nghi ngờ dependency dùng chung như network, DNS, IAM, storage service hoặc cloud control plane.

Ghi lại các thay đổi gần nhất: deployment, image, kernel patch, driver, policy IAM, security group, route, resize volume, autoscaling config hoặc quota. Thay đổi gần thời điểm xảy ra là manh mối, nhưng không mặc định đó là nguyên nhân.

### 5.2. VM và hệ điều hành

Các câu hỏi chẩn đoán:

- Instance có ở trạng thái running hay đang pending, stopping hoặc impaired?
- Console/system log có lỗi boot, filesystem, kernel panic hoặc driver không?
- CPU, memory, swap, disk I/O và network có bão hòa không?
- Service có active, listening đúng port và bind đúng interface không?
- DNS, route, security group/firewall và IAM role có hoạt động không?
- Có thay đổi image, package, kernel hoặc metadata gần đây không?

Một số lệnh Linux chỉ đọc:

```bash
uptime
free -h
df -h
df -i
ps aux --sort=-%mem | head
ps aux --sort=-%cpu | head
systemctl --failed
systemctl status app.service
journalctl -u app.service --since "30 minutes ago"
ss -s
ip route
```

Các lệnh cần chạy với quyền phù hợp và có thể khác giữa bản phân phối. Tránh đưa output chứa secret hoặc thông tin cá nhân vào ticket công khai. Nếu cần reboot, trước tiên xác minh workload, volume, replica và khả năng khôi phục.

### 5.3. Container và Kubernetes

Kiểm tra trạng thái pod, node, event, restart count, termination reason, image pull, readiness/liveness probe, resource request/limit, PVC và network policy.

```bash
kubectl get pods -A -o wide
kubectl get nodes
kubectl get events -A --sort-by=.lastTimestamp
kubectl describe pod <pod-name> -n <namespace>
kubectl logs <pod-name> -n <namespace> --previous
kubectl top pods -A
kubectl top nodes
```

Các lệnh `get`, `describe`, `logs` và `top` chủ yếu phục vụ chẩn đoán. `kubectl top` cần Metrics Server hoặc nguồn metric tương thích. Khi pod restart, `--previous` giúp xem log của container trước đó nếu runtime còn lưu. Không xóa pod hoặc drain node trước khi kiểm tra PDB, local data và số replica khỏe.

### 5.4. Serverless

Với function hoặc managed compute, kiểm tra:

- Invocation count, error count, timeout và duration percentile.
- Throttling, concurrency limit và cold start.
- Runtime version, package/image digest và deployment timestamp.
- IAM permission, secret access và KMS decrypt error.
- VPC/subnet, endpoint, DNS và kết nối đến dependency.
- Retry count, event age, dead-letter queue và xử lý duplicate.

Nếu lỗi chỉ xảy ra ở cold start, xem thời gian khởi tạo, dependency tải lúc boot và kết nối mạng. Nếu lỗi tăng cùng concurrency, kiểm tra quota, downstream connection pool và giới hạn database. Khi rollback function version, xác minh dữ liệu hoặc event đã xử lý có tương thích với phiên bản cũ.

### 5.5. Storage

Phân biệt volume đầy, filesystem đầy, inode cạn, IOPS/throughput chạm trần và latency tăng. Kiểm tra cả metric cloud volume và metric trong guest OS. Một volume có thể được resize ở control plane nhưng filesystem chưa mở rộng; một ứng dụng có thể bị chặn do I/O latency dù dung lượng còn nhiều.

Các lệnh chẩn đoán Linux có thể gồm `df -h`, `df -i`, `lsblk`, `findmnt` và `iostat -xz 1`. Không format hoặc chạy repair filesystem khi chưa xác định trạng thái mount, backup và hướng dẫn khôi phục. Với database, ưu tiên quy trình backup/restore nhất quán của engine.

### 5.6. Network và service dependency

Kiểm tra DNS, route, security group, firewall, network ACL, NAT, load balancer health, packet drop, retransmission và connection pool. Xác định lỗi là DNS resolution, TCP connect, TLS handshake, authentication hay request timeout; mỗi lớp có cách xử lý khác nhau.

Lệnh chẩn đoán thông dụng:

```bash
getent hosts service.internal
ip route
ss -tan
curl -v --connect-timeout 3 https://service.internal/health
```

Không chạy kiểm thử tải hoặc scan cổng rộng trên production khi chưa được phê duyệt. `curl -v` có thể hiển thị header hoặc thông tin nhạy cảm; che dữ liệu trước khi chia sẻ log.

### 5.7. GPU và workload phân tán

Với GPU job, kiểm tra scheduler state, node health, GPU utilization, VRAM, ECC error, driver/runtime version, temperature/power limit và log framework. Nếu nhiều GPU hoặc node tham gia, xem collective communication, network fabric, RDMA và tình trạng từng rank.

Một job có thể trông như GPU idle vì đang chờ storage, data loader hoặc all-reduce. Không reboot node ngay khi chưa xác định job có checkpoint và khả năng restart. Với lỗi driver hoặc ECC nghiêm trọng, cô lập node theo quy trình và bảo toàn log trước khi thay thế.

## 6. Xây dựng incident timeline

### 6.1. Mốc thời gian cần ghi

Timeline nên ghi tối thiểu:

- **T0 – Start/first known symptom:** thời điểm sớm nhất có bằng chứng cho thấy sự cố bắt đầu.
- **Detected:** thời điểm monitoring hoặc người dùng phát hiện.
- **Acknowledged:** thời điểm người trực xác nhận đã nhận cảnh báo.
- **Incident declared:** thời điểm chính thức mở incident và đặt severity.
- **Scope confirmed:** thời điểm xác định phạm vi và tác động.
- **Mitigation started/completed:** thời điểm bắt đầu và hoàn tất biện pháp giảm ảnh hưởng.
- **Service restored:** thời điểm các chức năng chính hoạt động trở lại.
- **Monitoring stable:** thời điểm kết thúc observation period và xác nhận ổn định.
- **Incident resolved/closed:** thời điểm đóng incident.
- **Follow-up created:** thời điểm tạo action item sau sự cố.

Không phải sự cố nào cũng có thể xác định chính xác T0. Nếu chỉ biết một khoảng thời gian, ghi rõ khoảng đó và nguồn bằng chứng. Không suy diễn một timestamp chính xác khi dữ liệu không hỗ trợ.

### 6.2. Chuẩn hóa timestamp

Nên lưu timestamp theo ISO 8601 và thống nhất UTC trong incident record, ví dụ `2026-11-22T14:20:00Z`. Nếu người dùng hoặc hệ thống dùng múi giờ khác, ghi rõ offset và chỉ chuyển đổi khi cần trình bày. Đồng bộ NTP/chrony trên máy chủ và kiểm tra clock skew giữa các hệ thống.

Timestamp của alert, log, trace và ticket có thể khác nhau do độ trễ ingest, buffering hoặc đồng hồ lệch. Ghi nguồn timestamp và phân biệt thời điểm sự kiện xảy ra với thời điểm hệ thống nhận được sự kiện.

### 6.3. Ghi sự kiện và quyết định

Mỗi dòng timeline nên gồm:

| Trường | Nội dung |
|---|---|
| Timestamp | Thời điểm và timezone/UTC |
| Actor | Người, automation hoặc dịch vụ thực hiện |
| Event/decision | Điều gì đã xảy ra hoặc quyết định nào được đưa ra |
| Evidence | Alert ID, log query, dashboard, trace, command output hoặc ticket |
| Impact | Tác động quan sát được tại thời điểm đó |
| Result | Kết quả sau hành động và bước tiếp theo |

Ghi cả hành động không thành công và quyết định không thực hiện. Ví dụ, nhóm quyết định không reboot vì database chưa có replica khỏe là thông tin quan trọng giúp giải thích vì sao chọn phương án khác.

### 6.4. Timeline ví dụ

Ví dụ minh họa sự cố API trên Kubernetes do memory pressure sau deployment:

| Thời điểm UTC | Sự kiện | Bằng chứng/kết quả |
|---|---|---|
| 09:02 | Bắt đầu rollout phiên bản mới | Deployment event và image digest |
| 09:08 | Restart count tăng ở nhóm pod mới | Pod events, container termination reason |
| 09:10 | Alert error rate firing | Dashboard SLO và alert ID |
| 09:13 | On-call acknowledge, mở incident SEV-2 | Incident record |
| 09:17 | Xác nhận pod mới bị OOMKilled, ảnh hưởng khoảng 20% request | Pod status, memory working set, request metrics |
| 09:21 | Quyết định dừng rollout và rollback image | Change record và deployment event |
| 09:27 | Pod cũ healthy, error rate bắt đầu giảm | Readiness và error rate |
| 09:34 | Error rate trở về baseline, latency ổn định | SLO dashboard |
| 10:00 | Kết thúc observation period, đóng incident | Service owner xác nhận chức năng chính |
| 14:00 | PIR xác nhận memory limit thiếu và kiểm thử tải chưa đại diện | Báo cáo điều tra và action items |

Các thời điểm trong bảng là dữ liệu giả định để minh họa cấu trúc. Khi ghi incident thực tế, thay bằng timestamp và bằng chứng thật.

### 6.5. Phân biệt sự kiện, giả thuyết và kết luận

Timeline nên tách dữ kiện đã xác minh khỏi giả thuyết. Ví dụ:

- Dữ kiện: “Pod `api-7c...` bị OOMKilled lúc 09:08 theo Kubernetes event.”
- Giả thuyết: “Memory limit có thể thấp hơn nhu cầu của phiên bản mới.”
- Kết luận sau điều tra: “Phiên bản mới tăng working set 35% trong tải đỉnh; limit không được điều chỉnh và test chưa bao phủ tải đó.”

Ghi giả thuyết như kết luận quá sớm làm lệch điều tra và có thể dẫn đến action item sai.

## 7. Điều tra nguyên nhân và post-incident review

### 7.1. Thu thập bằng chứng trước khi thay đổi

Khi có thể, lưu các dữ liệu có thời hạn ngắn trước khi restart hoặc replace:

- Alert và metric tại thời điểm xảy ra.
- Log ứng dụng, hệ điều hành, container runtime và cloud control plane.
- Trace hoặc request ID đại diện.
- Pod/instance events, deployment history và image digest.
- Process list, memory map, thread dump hoặc heap dump khi phù hợp.
- Network connection, route và trạng thái dependency.
- Database replication status, queue backlog và checkpoint.
- Lịch sử thay đổi IAM, security group, quota và autoscaling.

Chỉ thu thập dữ liệu cần thiết, bảo vệ secret và dữ liệu cá nhân, giới hạn quyền truy cập và retention. Một số dump có thể chứa token, dữ liệu người dùng hoặc nội dung nhạy cảm; cần lưu ở vị trí kiểm soát và xử lý theo chính sách.

### 7.2. Xây dựng chuỗi nhân quả

Đặt câu hỏi theo trình tự:

1. Điều kiện nào thay đổi trước khi symptom xuất hiện?
2. Thay đổi đó ảnh hưởng đến tài nguyên hoặc dependency nào?
3. Vì sao cơ chế bảo vệ như limit, retry, autoscaling, replica hoặc circuit breaker không ngăn được tác động?
4. Vì sao monitoring không phát hiện sớm hoặc không chỉ ra đúng thành phần?
5. Vì sao quy trình vận hành không giảm được thời gian khôi phục?

Mục tiêu là tìm chuỗi nguyên nhân có bằng chứng, không chỉ dừng ở câu “máy chủ quá tải” hoặc “người vận hành thao tác sai”.

### 7.3. Five Whys và fault tree

Five Whys giúp đi sâu từ symptom bằng cách hỏi “vì sao” nhiều lần. Tuy nhiên, không nhất thiết phải đủ năm câu hỏi; dừng khi đã tìm được nguyên nhân có thể kiểm chứng và có hành động xử lý. Fault tree hữu ích khi có nhiều nhánh nguyên nhân, ví dụ request timeout có thể đến từ CPU, storage, network, DNS hoặc downstream service.

Không ép một nguyên nhân duy nhất nếu bằng chứng cho thấy nhiều yếu tố góp phần. Một sự cố thường là kết quả của tương tác giữa thay đổi, giới hạn tài nguyên, thiếu dự phòng và khoảng trống phát hiện.

### 7.4. Blameless review

Post-incident review nên tập trung vào điều kiện hệ thống và quyết định dựa trên thông tin có tại thời điểm đó. Tránh quy kết cá nhân hoặc viết nhận xét như “đội vận hành bất cẩn”. Nếu một bước thủ công gây lỗi, hãy xem vì sao bước đó không có guardrail, xác nhận, automation hoặc tài liệu đủ rõ.

Blameless không có nghĩa là bỏ qua trách nhiệm. Owner vẫn phải nhận action item, có deadline, cập nhật tiến độ và chứng minh kết quả. Trách nhiệm hướng đến cải thiện hệ thống và hoàn thành cam kết.

### 7.5. Cấu trúc post-incident review

Một báo cáo PIR có thể gồm:

1. **Summary:** một đoạn mô tả điều gì xảy ra và trạng thái hiện tại.
2. **Impact:** dịch vụ, người dùng, giao dịch, dữ liệu, vùng và thời lượng bị ảnh hưởng.
3. **Severity and SLO:** mức độ, error budget hoặc SLO bị vi phạm.
4. **Timeline:** các mốc quan trọng, quyết định và bằng chứng.
5. **Detection:** alert nào phát hiện, alert nào thiếu hoặc đến muộn.
6. **Root cause and contributing factors:** chuỗi nhân quả và bằng chứng.
7. **Mitigation and recovery:** điều gì giảm ảnh hưởng và điều gì khôi phục hoàn toàn.
8. **What went well:** cơ chế đã hoạt động tốt.
9. **What made response harder:** khoảng trống tài liệu, quyền, telemetry, capacity hoặc phối hợp.
10. **Corrective/preventive actions:** hành động có owner, priority, due date và success criteria.

## 8. Hành động ngăn tái diễn

### 8.1. Phân loại hành động

Hành động sau sự cố nên được chia theo mục tiêu:

- **Corrective action:** sửa lỗi đã gây sự cố, ví dụ tăng memory limit sau khi sizing và test xác nhận.
- **Preventive action:** giảm xác suất sự cố tương tự, ví dụ thêm load test và policy kiểm tra resource limit trước deploy.
- **Detective action:** phát hiện sớm hơn, ví dụ alert theo OOM event và memory growth.
- **Mitigative action:** giảm tác động khi sự cố xảy ra, ví dụ thêm replica, circuit breaker hoặc failover tự động.
- **Process/documentation action:** cải thiện runbook, quyền, phê duyệt, đào tạo hoặc diễn tập.

Không phải mọi action đều cần viết code. Có thể cần bổ sung quota, sửa lịch bảo trì, thay đổi retention, cải thiện alert routing hoặc huấn luyện nhóm on-call.

### 8.2. Viết action item đo được

Một action item cần có:

| Trường | Yêu cầu |
|---|---|
| Action | Mô tả hành động cụ thể, tránh “cải thiện monitoring” |
| Owner | Một cá nhân hoặc nhóm chịu trách nhiệm chính |
| Priority | Mức ưu tiên theo rủi ro và tác động |
| Due date | Ngày hoàn thành hoặc mốc kiểm tra |
| Success criteria | Kết quả có thể đo hoặc kiểm chứng |
| Verification | Test, dashboard, drill hoặc review xác nhận |
| Status | Open, in progress, blocked hoặc done |

Ví dụ tốt: “Thêm alert cho tỷ lệ OOMKilled theo namespace và gửi đến on-call `platform-api`; hoàn thành trước ngày X; kiểm thử bằng pod thử nghiệm trong staging và xác nhận alert firing/resolved.”

Ví dụ chưa đủ: “Theo dõi memory tốt hơn.” Câu này không có metric, owner, deadline hoặc cách xác minh.

### 8.3. Ưu tiên theo rủi ro

Ưu tiên hành động dựa trên mức độ nghiêm trọng, khả năng tái diễn, số workload chịu ảnh hưởng, mức giảm rủi ro và chi phí thực hiện. Một thay đổi nhỏ như bổ sung quota alert có thể giảm rủi ro cho nhiều dịch vụ; một refactor lớn có thể mất nhiều tháng và không giải quyết được nguy cơ gần nhất.

Có thể chia:

- **P0:** giảm ngay nguy cơ nghiêm trọng hoặc lỗ hổng đang bị khai thác.
- **P1:** khắc phục nguyên nhân chính hoặc khoảng trống có thể gây incident lớn.
- **P2:** tăng khả năng phát hiện, tự phục hồi hoặc giảm thời gian xử lý.
- **P3:** cải thiện dài hạn, tài liệu và tối ưu vận hành.

Tên priority và SLA cần theo chính sách tổ chức. Không để action item P0/P1 không có owner hoặc không có mốc kiểm tra.

### 8.4. Đo hiệu quả sau cải tiến

Không đánh giá action chỉ bằng trạng thái “đã đóng”. Cần kiểm tra xem rủi ro có giảm hay không:

- Tỷ lệ sự cố tương tự có giảm không?
- MTTD (Mean Time to Detect) có ngắn hơn không?
- MTTA (Mean Time to Acknowledge) có cải thiện không?
- MTTR (Mean Time to Restore/Recover) có giảm không?
- Số lần rollback, OOM, quota rejection hoặc failed deployment có thay đổi không?
- Runbook có được thực hiện thành công trong diễn tập không?
- Cảnh báo mới có đúng owner và ít false positive không?

MTTR có thể được định nghĩa khác nhau giữa các tổ chức. Hãy ghi rõ điểm bắt đầu và kết thúc đang dùng, chẳng hạn từ detection đến service restored, để so sánh nhất quán.

## 9. Ví dụ runbook: VM không phục vụ request

### 9.1. Mục tiêu và điều kiện kích hoạt

**Mục tiêu:** khôi phục một backend VM không healthy sau load balancer mà không làm gián đoạn toàn bộ dịch vụ.

**Trigger:** health check thất bại liên tục, error rate tăng hoặc backend không nhận request. Owner là nhóm vận hành dịch vụ; escalation đến cloud/network team nếu nhiều VM cùng vùng bị ảnh hưởng.

### 9.2. Kiểm tra ban đầu

1. Xác nhận load balancer báo backend unhealthy và ghi lại thời điểm.
2. Kiểm tra các backend khác có healthy và đủ capacity không.
3. Kiểm tra instance state, system log và sự kiện bảo trì cloud.
4. Kiểm tra CPU, memory, disk, network và process của VM.
5. Kiểm tra service status, listening port và log ứng dụng.
6. Kiểm tra DNS, route, security group/firewall và dependency.
7. Đối chiếu thay đổi gần đây: deployment, patch, image, IAM hoặc network rule.

### 9.3. Mitigation

Nếu chỉ một backend lỗi và các backend còn lại đủ capacity, giữ backend lỗi ngoài target group, thu thập log cần thiết rồi restart service theo runbook ứng dụng nếu nguyên nhân đã rõ. Nếu lỗi xuất hiện sau deployment và có bằng chứng liên quan, cân nhắc rollback phiên bản. Nếu nhiều backend cùng lỗi, kiểm tra dependency dùng chung trước khi thay từng VM.

Không reboot toàn bộ fleet. Không xóa hoặc thay VM stateful trước khi xác định volume và dữ liệu nằm ở đâu.

### 9.4. Recovery và tiêu chí đóng

Chờ service active, port listening và health endpoint thành công. Đưa backend trở lại pool theo từng máy; theo dõi error rate, p95/p99 latency, CPU, memory và request success. Xác nhận chức năng nghiệp vụ bằng smoke test. Đóng incident khi các backend ổn định qua observation period và owner xác nhận.

### 9.5. Hành động sau sự cố

Nếu nguyên nhân là thiếu health check chi tiết, bổ sung endpoint readiness phù hợp. Nếu thiếu capacity, điều chỉnh autoscaling và quota. Nếu patch gây lỗi, thêm kiểm thử canary cho image/OS. Mỗi action cần owner và tiêu chí kiểm chứng.

## 10. Ví dụ runbook: Pod liên tục bị OOMKilled

### 10.1. Mục tiêu và trigger

**Mục tiêu:** khôi phục workload Kubernetes bị OOMKilled và xác định vì sao memory vượt giới hạn.

**Trigger:** restart count tăng, pod state có `OOMKilled`, memory working set tiến sát limit hoặc application latency/error tăng.

### 10.2. Kiểm tra

1. Lấy namespace, deployment, pod, node và thời điểm restart.
2. Dùng `kubectl describe pod` để kiểm tra last state và events.
3. Xem `kubectl logs --previous` nếu container trước đó còn log.
4. So sánh memory limit/request với RSS hoặc working set thực tế.
5. Kiểm tra heap, GC, cache, request size và concurrency của ứng dụng.
6. Đối chiếu deployment, traffic và dependency tại thời điểm memory tăng.
7. Kiểm tra node memory pressure và các pod khác cùng node.

### 10.3. Mitigation

Nếu limit rõ ràng thấp hơn nhu cầu hợp lệ và node có headroom, có thể tăng limit theo quy trình đã phê duyệt. Nếu phiên bản mới làm memory tăng bất thường, dừng rollout hoặc rollback. Nếu nghi memory leak, giảm traffic/concurrency và thu thập profile/dump phù hợp trước khi restart nếu có thể.

Không tăng limit vô hạn. Kiểm tra tổng request/limit và capacity node để tránh đẩy node vào memory pressure. Không drain node khi chưa đánh giá PDB và các workload khác.

### 10.4. Recovery và prevention

Chờ pod ổn định, kiểm tra restart count không tăng, memory không tiếp tục tăng bất thường, request latency và error rate trở về baseline. Action có thể gồm memory profiling, load test theo tải đỉnh, alert OOM theo namespace, policy resource request/limit và capacity review.

## 11. Ví dụ runbook: Serverless timeout hoặc throttling

### 11.1. Kiểm tra

1. Xác định function/version/alias và thời điểm bắt đầu lỗi.
2. Xem invocation, duration p95/p99, timeout, error và throttle count.
3. Kiểm tra concurrency limit, account quota và downstream rate limit.
4. Kiểm tra cold start, runtime version, package/image và dependency initialization.
5. Kiểm tra IAM, secret, KMS, VPC endpoint, DNS và kết nối đến dịch vụ đích.
6. Kiểm tra event age, retry, duplicate và dead-letter queue.

### 11.2. Mitigation và recovery

Nếu một phiên bản mới gây timeout, chuyển alias/traffic về phiên bản trước khi xác minh tương thích. Nếu downstream quá tải, giảm concurrency hoặc dùng backpressure; tăng concurrency có thể làm sự cố nặng hơn. Nếu quota bị chạm, xác định giới hạn và phương án tăng quota hoặc phân phối workload.

Sau mitigation, xác nhận invocation thành công, duration trong SLO, queue age giảm và không có sự kiện bị mất hoặc xử lý trùng. Action có thể là idempotency key, timeout theo dependency, concurrency guardrail, kiểm thử cold start và alert quota.

## 12. Ví dụ timeline và action sau sự cố storage

Một worker ghi tệp kết quả vào volume. Sau một batch, filesystem đầy và worker bắt đầu thất bại.

| Thời điểm UTC | Sự kiện | Bằng chứng |
|---|---|---|
| 02:00 | Batch bắt đầu, tốc độ tạo tệp cao hơn baseline | Scheduler event và application metric |
| 02:25 | Dung lượng mount point vượt 90% | Node exporter metric |
| 02:31 | Alert warning được gửi đến owner | Alert manager event |
| 02:46 | Worker gặp lỗi ghi `No space left on device` | Application log |
| 02:50 | On-call mở incident và tạm dừng batch mới | Incident record và scheduler event |
| 03:05 | Xác định tệp tạm không được dọn sau mỗi batch | Disk usage và file inventory |
| 03:18 | Dọn tệp tạm theo retention đã xác nhận; worker phục hồi | Runbook action và application health |
| 03:40 | Batch tiếp tục, queue/backlog ổn định | Job status và queue metric |
| Ngày tiếp theo | PIR xác nhận thiếu lifecycle cleanup và alert warning đến muộn | PIR và action tracker |

Hành động ngăn tái diễn:

| Action | Owner | Priority | Tiêu chí hoàn thành |
|---|---|---|---|
| Thêm cleanup an toàn sau khi batch hoàn tất | Application team | P1 | Kiểm thử không xóa tệp đang dùng và dung lượng trở về baseline |
| Cảnh báo time-to-full theo tốc độ tăng | SRE | P1 | Alert firing trong staging trước khi còn ít hơn thời gian xử lý |
| Đặt retention và giới hạn dung lượng tệp tạm | Workload owner | P2 | Policy được triển khai và có dashboard xác nhận |
| Thêm bước kiểm tra disk capacity trước khi nhận batch | Platform team | P2 | Scheduler không nhận job khi headroom dưới ngưỡng an toàn |

## 13. Mẫu runbook và incident record

### 13.1. Mẫu runbook

```markdown
# Runbook: <Tên tình huống>

## Mục tiêu
<Kết quả cần đạt>

## Phạm vi và owner
- Service/environment/region:
- Owner/on-call:
- Escalation:

## Trigger và severity
- Alert/event:
- Điều kiện mở incident:

## Preconditions
- Quyền truy cập:
- Backup/checkpoint/replica:
- Capacity và dependency:
- Phê duyệt cần thiết:

## Chẩn đoán
1. <Kiểm tra, mục đích, kết quả mong đợi>
2. <Kiểm tra tiếp theo>

## Mitigation
1. <Hành động, phạm vi, điều kiện thực hiện>
2. <Kết quả và điều kiện dừng>

## Recovery / rollback
1. <Bước khôi phục>
2. <Điều kiện rollback>

## Validation
- Health/SLO:
- Business check:
- Observation period:

## Evidence và liên kết
- Dashboard/log/trace:
- Incident record:
- Change/ticket:

## Review
- Runbook owner:
- Last tested:
- Next review:
```

### 13.2. Mẫu incident timeline

| Timestamp UTC | Actor | Event/decision | Evidence | Impact/result |
|---|---|---|---|---|
| YYYY-MM-DDThh:mm:ssZ | Monitoring | Alert fired | Alert ID/link | Phạm vi ban đầu |
| YYYY-MM-DDThh:mm:ssZ | On-call | Acknowledge/open incident | Incident ID | Severity và owner |
| YYYY-MM-DDThh:mm:ssZ | Technical lead | Xác nhận symptom/scope | Dashboard/log/trace | Mức ảnh hưởng |
| YYYY-MM-DDThh:mm:ssZ | Responder | Mitigation started/completed | Command/change ID | Kết quả |
| YYYY-MM-DDThh:mm:ssZ | Service owner | Xác nhận recovery | Smoke test/SLO | Dịch vụ ổn định |
| YYYY-MM-DDThh:mm:ssZ | IC | Close incident | Incident record | Follow-up được giao |
```

### 13.3. Mẫu post-incident action tracker

| ID | Hành động cụ thể | Owner | Priority | Due date | Success criteria | Status |
|---|---|---|---|---|---|---|
| ACT-001 | <Việc cần làm> | <Nhóm/cá nhân> | P1 | YYYY-MM-DD | <Cách đo/xác minh> | Open |
| ACT-002 | <Việc cần làm> | <Nhóm/cá nhân> | P2 | YYYY-MM-DD | <Cách đo/xác minh> | Open |

Không đóng action chỉ vì đã tạo pull request hoặc ticket. Đóng khi thay đổi đã triển khai, được kiểm thử và đạt success criteria.

## 14. Đo lường chất lượng phản ứng sự cố

### 14.1. MTTD, MTTA và MTTR

- **MTTD (Mean Time to Detect):** thời gian trung bình từ khi sự cố bắt đầu đến khi được phát hiện.
- **MTTA (Mean Time to Acknowledge):** thời gian từ khi cảnh báo/incident được gửi đến khi có người xác nhận tiếp nhận.
- **MTTR:** có thể được định nghĩa là thời gian khôi phục hoặc sửa chữa; cần nêu rõ mốc bắt đầu và kết thúc.

Ví dụ, nếu đo MTTR từ lúc phát hiện đến lúc service restored, hãy dùng cùng định nghĩa cho mọi incident trong báo cáo. Không so sánh số liệu dùng định nghĩa khác nhau.

### 14.2. Chỉ số bổ sung

- Tỷ lệ incident có runbook được cập nhật và đã kiểm thử.
- Tỷ lệ action item hoàn thành đúng hạn.
- Tỷ lệ sự cố lặp lại cùng nguyên nhân.
- Tỷ lệ alert dẫn đến hành động có ích so với false positive.
- Thời gian từ mitigation đến recovery hoàn toàn.
- Số sự cố do quota, capacity, patch, deployment hoặc cấu hình.
- Tỷ lệ workload có owner, SLO, dashboard và escalation rõ ràng.

Không dùng một metric đơn lẻ để đánh giá hiệu quả cá nhân hoặc tạo áp lực đóng incident nhanh. Mục tiêu là cải thiện độ tin cậy của hệ thống và khả năng xử lý chung.

### 14.3. Diễn tập và kiểm tra readiness

Thực hiện tabletop exercise cho tình huống lớn, game day cho failure mode đã chọn và kiểm tra runbook theo lịch. Có thể mô phỏng disk gần đầy, pod OOM, quota bị chạm hoặc function timeout trong môi trường an toàn. Đánh giá người trực có tìm đúng dashboard, xác định đúng owner và làm theo bước an toàn hay không.

Sau diễn tập, cập nhật runbook, alert, quyền truy cập và action tracker. Một tài liệu chỉ được xem là đáng tin khi nhóm đã thử và biết các giới hạn của nó.

## 15. Những sai lầm thường gặp

- **Chỉ ghi thời điểm phát hiện:** bỏ qua thời điểm bắt đầu, mitigation, recovery và observation.
- **Dùng timestamp không có timezone:** khó đối chiếu log từ nhiều region hoặc đội vận hành.
- **Ghi giả thuyết như sự thật:** khiến điều tra và action item đi sai hướng.
- **Không ghi quyết định không thực hiện:** mất ngữ cảnh về rủi ro đã cân nhắc.
- **Runbook chỉ có lệnh:** không nêu precondition, phạm vi, kết quả mong đợi và điều kiện dừng.
- **Restart trước khi thu thập bằng chứng:** làm mất log, process state hoặc thông tin cần điều tra.
- **Mitigation bị nhầm là resolution:** dịch vụ vừa phục hồi đã đóng incident dù lỗi có thể tái diễn.
- **Chỉ kiểm tra health endpoint:** bỏ sót lỗi nghiệp vụ, dữ liệu và backlog.
- **Action item không có owner/deadline:** không ai chịu trách nhiệm hoàn tất.
- **Action item quá chung chung:** không thể xác minh đã giảm rủi ro hay chưa.
- **Quy kết cá nhân:** không tìm ra điều kiện hệ thống khiến lỗi dễ xảy ra.
- **Không diễn tập:** runbook có thể lỗi thời hoặc yêu cầu quyền mà người trực không có.
- **Đóng PIR khi chưa xác minh action:** báo cáo tồn tại nhưng rủi ro vẫn chưa được xử lý.

## 16. Checklist

### Khi mở incident

- [ ] Đã xác định service, environment, region, owner và phạm vi ảnh hưởng.
- [ ] Đã phân loại severity theo impact và SLO.
- [ ] Đã chỉ định IC, technical lead, responder và scribe khi cần.
- [ ] Đã tạo incident record và bắt đầu timeline theo UTC.
- [ ] Đã ghi symptom, bằng chứng và thay đổi gần đây.
- [ ] Đã bảo vệ dữ liệu và kiểm tra dấu hiệu security incident.

### Khi xử lý

- [ ] Đã dùng runbook phù hợp và kiểm tra precondition.
- [ ] Đã phân biệt lệnh chỉ đọc với thao tác thay đổi trạng thái.
- [ ] Đã ghi người thực hiện, quyết định, timestamp và kết quả.
- [ ] Đã chọn mitigation có phạm vi nhỏ nhất đáp ứng mục tiêu.
- [ ] Đã xác định stop condition và rollback trước thay đổi rủi ro.
- [ ] Đã cập nhật stakeholder theo nhịp thống nhất.

### Khi phục hồi và đóng incident

- [ ] Đã xác minh health, SLO và chức năng nghiệp vụ.
- [ ] Đã theo dõi đủ observation period.
- [ ] Đã ghi rõ mitigation time, service restored và incident closed.
- [ ] Đã lưu bằng chứng và bảo vệ dữ liệu nhạy cảm.
- [ ] Đã lên lịch post-incident review.

### Sau incident

- [ ] Đã xác định root cause và contributing factors bằng bằng chứng.
- [ ] Đã cập nhật runbook, dashboard hoặc alert nếu cần.
- [ ] Mỗi action có owner, priority, due date và success criteria.
- [ ] Đã theo dõi action đến khi triển khai và xác minh.
- [ ] Đã diễn tập hoặc kiểm tra lại biện pháp phòng ngừa.
- [ ] Đã đo xu hướng MTTD, MTTA, MTTR và incident lặp lại.

## 17. Kết luận

Runbook giúp đội vận hành xử lý sự cố theo các bước an toàn, có thể lặp lại; incident timeline giữ lại diễn biến, quyết định và bằng chứng theo thời gian; post-incident review biến những gì đã học thành hành động cải thiện. Ba thành phần cần liên kết với nhau để rút ngắn thời gian phát hiện và khôi phục, đồng thời giảm khả năng sự cố lặp lại.

Với workload compute, chẩn đoán nên đi từ phạm vi ảnh hưởng qua ứng dụng, VM/container/serverless, CPU, memory, storage, network và dịch vụ cloud phụ thuộc. Hãy ghi rõ đâu là dữ kiện, đâu là giả thuyết; ưu tiên bảo vệ người dùng và dữ liệu; xác minh phục hồi bằng chỉ số kỹ thuật lẫn nghiệp vụ. Mỗi hành động sau sự cố cần có owner, thời hạn và tiêu chí kiểm chứng để cải thiện độ tin cậy thực tế của hệ thống.

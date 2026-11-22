# Autohealing và thiết kế health checks cho MIG

> **Chương:** Nhóm máy ảo và tự động mở rộng  
> **Mô-đun:** CLOUD_PROVIDERS_GCP

Một ứng dụng Java chạy trên Compute Engine có thể gặp tình huống **VM vẫn RUNNING nhưng ứng dụng đã treo**: tiến trình không nhận kết nối, pool thread bị kẹt hoặc dịch vụ không còn trả lời đúng. Nếu chỉ giám sát trạng thái máy ảo, nhóm vận hành có thể không phát hiện kịp. Với **Managed Instance Group (MIG)**, Google Cloud có thể dùng **application-based health check** để đánh giá từng VM và **tự động tái tạo VM không khỏe**, đưa nhóm về số lượng và cấu hình mong muốn. Cơ chế này gọi là **autohealing**.

Trong mô-đun **CLOUD_PROVIDERS_GCP**, người học tìm hiểu Google Cloud từ project, IAM, VPC đến Compute Engine, GKE, Cloud Run, lưu trữ và cơ sở dữ liệu, qua các tình huống triển khai biết lựa chọn dịch vụ, bảo vệ tài nguyên, tự động hóa phát hành và theo dõi độ tin cậy cùng chi phí. Bài này thuộc chương **Nhóm máy ảo và tự động mở rộng**, tập trung vào thiết kế health check đáng tin cậy, cài đặt chính sách autohealing, theo dõi quá trình repair và tránh các vòng lặp recreate gây giảm tính sẵn sàng.

Sau bài học, bạn có thể:

1. Phân biệt **MIG repair**, **application-based autohealing**, **autoscaling**, **rolling update** và **load balancer health checking**.
2. Chọn health endpoint phản ánh lỗi cần **thay VM**, không nhầm với readiness để **nhận traffic**.
3. Thiết kế `check interval`, `timeout`, `healthy/unhealthy thresholds` và **initial delay** theo thời gian khởi động thực tế.
4. Cấu hình Google Cloud health check, firewall và autohealing policy cho zonal hoặc regional MIG.
5. Đọc các trạng thái `HEALTHY`, `UNHEALTHY`, `TIMEOUT`, `UNKNOWN` và các current actions của instance.
6. Phân tích các tình huống health check sai, ứng dụng chưa sẵn sàng, phụ thuộc ngoài lỗi, quá tải và repair quá nhiều VM.
7. Thiết kế runbook có quan sát, kiểm chứng, rollback và cân bằng chi phí với SLO.

## 1. Managed Instance Group và vai trò autohealing

**Managed Instance Group (MIG)** là nhóm VM do Compute Engine quản lý theo **instance template** và những cấu hình nhóm như số lượng đích, distribution, update policy, autoscaler hoặc autohealing policy. MIG có thể là **zonal** (trong một zone) hoặc **regional** (phân bổ qua nhiều zone của một region theo cấu hình).

Một MIG cung cấp hai cơ chế cần phân biệt:

- **Repair VM gặp lỗi hạ tầng hoặc bị dừng ngoài ý muốn**: MIG cố gắng duy trì target size bằng cách tái tạo VM lỗi hoặc mất. Cơ chế cơ bản này **không bắt buộc có application health check**.
- **Application-based autohealing**: người quản trị gắn **health check** vào MIG. Nếu ứng dụng trên VM bị đánh giá unhealthy theo chính sách, MIG có thể **recreate** VM đó. Đây là tín hiệu phục hồi ở tầng ứng dụng, không chỉ ở tầng hypervisor.

~~~mermaid
flowchart LR
  T["Instance template\nImage / startup / service account"] --> MIG["Managed Instance Group\nTarget size = 3"]
  MIG --> VM1["VM-1\nHealthy"]
  MIG --> VM2["VM-2\nHealthy"]
  MIG --> VM3["VM-3\nApp treo"]
  HC["Application health check"] -. "Probe đến từng VM" .-> VM1
  HC -. "Probe đến từng VM" .-> VM2
  HC -. "Probe đến từng VM" .-> VM3
  HC --> RULE{"VM-3 Unhealthy\nsau initial delay?"}
  RULE -- "Có" --> REPAIR["MIG repair / recreate VM-3"]
  REPAIR --> MIG
~~~

### 1.1. Định nghĩa đúng “recreate”

Khi autohealing sửa một VM unhealthy, MIG thường **xóa và tạo lại instance** theo cấu hình do MIG quản lý. Đây **không phải** nút “restart ứng dụng Java” và cũng không bảo đảm giữ mọi trạng thái cục bộ của VM.

Các hệ quả:

- Process và in-memory session biến mất.
- Local SSD/ephemeral data và những thay đổi thủ công không được lưu bền có thể mất.
- Đĩa, IP, metadata và trạng thái cần giữ lại chỉ có thể dựa vào chính sách **stateful MIG/preserved state** hoặc dịch vụ lưu trữ ngoài thích hợp, theo giới hạn sản phẩm.
- VM mới phải chạy startup script, tải cấu hình, đăng ký dịch vụ và vượt health check.
- Nếu lỗi nằm trong **instance template** hoặc release mới, VM thay thế có thể gặp **cùng lỗi** và tiếp tục bị thay.

**Nguyên tắc thiết kế:** Workload phù hợp autohealing nên **có thể thay thế VM** mà không làm mất dữ liệu hoặc phá giao dịch; hãy đặt trạng thái bền trong Cloud SQL, Cloud Storage, Memorystore hoặc hệ thống dữ liệu được thiết kế tương ứng. Nếu workload có trạng thái trên VM, cần hiểu khả năng và giới hạn của **stateful MIG** trước khi bật repair.

### 1.2. Zonal so với regional MIG

| Phạm vi | Năng lực | Giới hạn |
| --- | --- | --- |
| **Zonal MIG** | Repair các instance trong một zone; dễ tạo lab, giảm độ phức tạp | Không giúp tiếp tục hoạt động khi **toàn zone** không khả dụng |
| **Regional MIG** | Có thể phân tán instance qua nhiều zone trong region, giảm single-zone failure | Không thay thế kiến trúc multi-region; vẫn phụ thuộc các dịch vụ và capacity theo region |
| **MIG + Load Balancer** | Cung cấp frontend ổn định, chuyển traffic khỏi backend unhealthy | Phải cấu hình backend service/health check/firewall đúng; LB không tự lưu trạng thái ứng dụng |
| **MIG + Autoscaler** | Điều chỉnh số VM theo tải phù hợp | Tăng số VM không sửa triệt để bug/hung process; còn giới hạn quota và thời gian khởi động |

Regional MIG là yếu tố quan trọng của **high availability**, nhưng số VM tối thiểu, vị trí phân bổ, LB backend, DB và khả năng chịu lỗi của ứng dụng vẫn quyết định kết quả cuối cùng. Một regional MIG chỉ có một instance không tạo được khả năng dự phòng có ý nghĩa.

## 2. Phân biệt autohealing, autoscaling, load balancing và rolling update

Đây là điểm dễ nhầm nhất khi thiết kế một hệ thống tự phục hồi.

| Chức năng | Quyết định chính | Tác động lên VM | Mục tiêu |
| --- | --- | --- | --- |
| **Autoscaling** | Có cần thêm/bớt năng lực theo CPU, LB serving capacity, metrics hoặc schedule không? | Thay đổi **target size** của MIG | Phù hợp công suất với tải, chi phí |
| **Load balancer health check** | Backend này có nên **nhận request mới** không? | Thường loại backend không khỏe khỏi traffic, **không tự recreate VM** | Bảo vệ trải nghiệm người dùng nhanh |
| **MIG application health check + autohealing** | VM này có hỏng tới mức **cần thay thế** không? | MIG chủ động recreate VM không khỏe | Phục hồi năng lực ứng dụng |
| **MIG repair cơ bản** | VM bị lỗi hạ tầng hoặc bị dừng/mất ngoài ý muốn? | Tạo lại VM để đạt target size | Duy trì nhóm hoạt động |
| **Rolling update** | Có cần triển khai template/phiên bản mới trên các VM không? | Thay hoặc cập nhật VM theo update policy | Phát hành có kiểm soát |

**Google Cloud khuyến nghị tách health check cho load balancing và autohealing.** Một load balancer cần quyết định nhanh để **không gửi request** đến một instance chưa sẵn sàng. Autohealing lại có tác động mạnh: **recreate một VM**. Vì thế tín hiệu autohealing nên **bảo thủ, ổn định và chỉ fail khi sửa bằng cách thay VM thực sự có ích**.

~~~mermaid
flowchart TD
  USER["Client request"] --> LB["Cloud Load Balancer"]
  LBC["LB health check\nReadiness: nhanh và nhạy"] --> LB
  LB --> VM1["VM-1 phục vụ"]
  LB --> VM2["VM-2 tạm không nhận traffic"]
  AHC["MIG autohealing health check\nLiveness: bảo thủ"] --> MIG["MIG controller"]
  MIG --> VM1
  MIG --> VM2
  VM2 -. "Nếu lỗi kéo dài, không phục hồi" .-> MIG
  MIG -. "Recreate khi cần" .-> VM2
~~~

### 2.1. Ví dụ vì sao hai check khác nhau

Giả sử VM Java có thể trả lời HTTP nhưng đang khởi động connection pool để kết nối Cloud SQL.

- **Readiness cho Load Balancer:** trả **503** trong khi chưa thể xử lý giao dịch, để LB chuyển request đến VM khác.
- **Liveness cho autohealing:** vẫn trả **200** nếu tiến trình Java, HTTP server và worker nền cốt lõi vẫn hoạt động. Việc Cloud SQL bị lỗi vài giây không nhất thiết có nghĩa VM cần bị phá và tạo lại.
- Nếu event loop/thread pool bị deadlock, server không phản hồi probe hoặc process crash kéo dài, **liveness thất bại**, MIG có thể recreate sau các ngưỡng.
- Khi VM mới khởi động, **initial delay** cho ứng dụng thời gian hoàn thành startup trước khi lỗi health check kích hoạt recreate.

Nếu dùng **cùng một check phụ thuộc database** cho cả LB và autohealing, một sự cố Cloud SQL có thể khiến **tất cả VM bị recreate hàng loạt**, làm vấn đề nghiêm trọng hơn và gây tốn phí.

### 2.2. Autohealing không sửa tất cả loại lỗi

| Tình huống | Autohealing có thể giúp? | Cần thêm gì? |
| --- | --- | --- |
| Process Java ngừng hoạt động, không tự phục hồi | Thường có, nếu probe phát hiện được | Giảm MTTR, startup script đáng tin cậy |
| Deadlock khiến ứng dụng không phản hồi health endpoint | Có thể | Thiết kế probe phản ánh lỗi process |
| VM bị dừng ngoài ý muốn | MIG repair cơ bản xử lý | IAM, audit, kiểm soát thao tác bên ngoài MIG |
| Tải tăng đột ngột nhưng mỗi VM vẫn khỏe | Không giải quyết công suất | Autoscaling và tối ưu workload |
| Cloud SQL/VPC/DNS chung bị lỗi | Recreate VM thường **không giúp** | HA/DR cho dependency, timeout, retry, circuit breaker |
| Release mới có bug trên mọi VM | Thường **không giúp** | Rollback version/template, canary và rollout control |
| Toàn zone/region không khả dụng | Không tự giải quyết toàn bộ | Regional/multi-region kiến trúc HA |
| Leak bộ nhớ lặp lại sau vài giờ | Recreate có thể giảm triệu chứng | Sửa leak, metrics và rate-limit sửa chữa |
| Bản ghi DB đang được xử lý trên một VM | Recreate có thể gây mất/double processing | Idempotency, queue ack và persistent state |

## 3. Thiết kế một endpoint health check tốt

Một **health check** là tập tiêu chí mà Google Cloud probes áp dụng tới từng backend VM: giao thức, cổng, request path, thời gian kiểm tra, timeout và ngưỡng thành công/thất bại. Health check cho MIG nên phân biệt rõ **liveness** và **readiness**.

### 3.1. Liveness vs readiness vs startup

| Loại tín hiệu | Câu hỏi | Quyết định thích hợp |
| --- | --- | --- |
| **Liveness** | Tiến trình/ứng dụng còn hoạt động có ý nghĩa không? | Làm tín hiệu cho **autohealing** |
| **Readiness** | VM có thể **nhận request mới ngay lúc này** không? | Làm tín hiệu cho **load balancer** |
| **Startup/initialization** | Ứng dụng đã boot xong chưa? | Thiết lập **initial delay**, và startup logic của ứng dụng |
| **Business health/SLO** | Người dùng có hoàn thành giao dịch không? | Monitoring, alerting, SRE review, rollback |
| **Dependency health** | DB, cache, queue, Google API có hoạt động? | Readiness hoặc telemetry; liveness chỉ fail khi có căn cứ |

**Không dùng mỗi một HTTP 200 trên "/" để định nghĩa ứng dụng khỏe.** Trang chủ có thể trả 200 trong khi worker nội bộ chết; ngược lại, endpoint thực hiện kiểm thử tất cả dependencies có thể fail do sự cố chung mà recreate không cứu được.

### 3.2. Các nguyên tắc của endpoint cho autohealing

1. **Nhẹ, nhanh và deterministic:** tránh query nặng tới DB, scan đĩa, gọi dịch vụ ngoài hoặc khóa tài nguyên lâu.
2. **Không thay đổi dữ liệu:** health check không INSERT/DELETE/đẩy message vào hàng đợi.
3. **Cho biết lỗi sửa được bằng recreate:** ví dụ process treo, listener ngừng phản hồi hoặc trạng thái không thể tự phục hồi tại local instance.
4. **Không lộ secret:** không in token, cấu hình nội bộ hoặc thông tin người dùng trong response.
5. **Có đường mạng tới VM:** ứng dụng bind vào IP giao diện phù hợp (hoặc `0.0.0.0`) trên cổng probe; không chỉ lắng nghe `127.0.0.1`.
6. **Phản hồi đúng status:** HTTP success theo yêu cầu health check khi khỏe; trả 5xx/không phản hồi khi thật sự không khỏe.
7. **Có observability riêng:** ứng dụng log các chuyển trạng thái; tránh log mỗi probe tới mức gây bùng Cloud Logging.
8. **Cân nhắc graceful shutdown/idempotency:** recreate không làm hỏng giao dịch hoặc nhân đôi tác vụ.

### 3.3. Ví dụ hợp đồng endpoint cho ứng dụng Java

Giả sử ứng dụng Java Spring Boot chạy trong instance template, lắng nghe cổng **8080**, có hai endpoint:

~~~text
GET http://<VM_INTERNAL_IP>:8080/internal/health/live
  - 200: HTTP server và thành phần cốt lõi đang hoạt động
  - 503/timeout: tiến trình hoặc thành phần local không còn phục hồi

GET http://<VM_INTERNAL_IP>:8080/internal/health/ready
  - 200: ứng dụng sẵn sàng nhận request kinh doanh
  - 503: đang warm up, drain hoặc dependency quan trọng chưa sẵn sàng
~~~

Có thể dùng **Spring Boot Actuator liveness/readiness probes** khi đã thêm dependency và bật các health groups tương ứng theo phiên bản framework. Không mặc định một ứng dụng Java bất kỳ đã sẵn có các đường dẫn trên: bạn phải triển khai, thử thủ công và xác định rõ điều kiện trả về.

Một pseudo-controller minh họa ý tưởng, **không phải code production hoàn chỉnh**:

~~~java
// Minh họa contract endpoint, cần wiring Spring và dependency thực tế.
@GetMapping("/internal/health/live")
ResponseEntity<String> liveness() {
    // Không gọi DB/các dịch vụ bên ngoài trong liveness.
    return ResponseEntity.ok("live");
}

@GetMapping("/internal/health/ready")
ResponseEntity<String> readiness() {
    return applicationAcceptsNewTraffic()
        ? ResponseEntity.ok("ready")
        : ResponseEntity.status(503).body("not ready");
}
~~~

Ví dụ này chỉ kiểm tra web request thread có thể trả lời. Nếu ứng dụng có worker riêng cần phát hiện deadlock, phải thiết kế một tín hiệu **local progress** đáng tin cậy; không biến endpoint thành truy vấn tất cả dependencies gây tăng tải hoặc sinh lỗi dây chuyền.

**Cảnh báo:** Endpoint trả 200 vô điều kiện có thể che giấu process vẫn phục vụ HTTP nhưng xử lý nghiệp vụ chính đã ngừng. Endpoint fail chỉ vì DB bị trục trặc tạm thời lại quá nhạy. Chọn tín hiệu phù hợp với loại workload và làm bài thử fault injection an toàn.

### 3.4. Giao thức và port

Google Cloud hỗ trợ **non-legacy health checks** như HTTP, HTTPS, TCP và SSL/TLS theo điều kiện tương ứng, có loại global và regional.

- Với **HTTP**, thường kiểm tra `GET /internal/health/live` trên port 8080, chờ mã phản hồi thành công theo cấu hình.
- Với **HTTPS**, cần TLS handshake và cấu hình certificate/SNI nếu có; kiểm tra giới hạn sản phẩm và khả năng probe truy cập.
- Với **TCP**, chỉ xác minh kết nối TCP thành công; không đủ biết logic ứng dụng khỏe.
- Với dịch vụ không phải HTTP, cân nhắc health adapter local phản ánh trạng thái ứng dụng mà không làm hỏng business traffic.
- Tài liệu phân biệt **modern health checks** với legacy `http-health-checks`/`https-health-checks`. Cho cấu hình mới nên dùng hiện đại, trừ khi có lý do tương thích.

Không dùng health endpoint chỉ bind loopback `127.0.0.1`, vì probes từ hệ thống Google không kết nối được tới loopback trên guest OS từ bên ngoài.

## 4. Cấu hình thời gian kiểm tra và ngưỡng phục hồi

Các tham số tạo nên cân bằng giữa **phát hiện lỗi nhanh** và **tránh repair sai**:

| Tham số | Ý nghĩa | Ví dụ cho autohealing |
| --- | --- | --- |
| `check-interval` | Tần suất gửi probe tới một instance | `30s` |
| `timeout` | Tối đa chờ một probe trả lời | `10s` |
| `healthy-threshold` | Số probe thành công liên tiếp để chuyển sang healthy | `2` |
| `unhealthy-threshold` | Số probe thất bại liên tiếp để chuyển sang unhealthy | `3` |
| `initial-delay` | Cửa sổ khởi động VM, MIG bỏ qua kết quả fail ban đầu | `300s` cho app cần khoảng 4 phút boot |

Ví dụ này là **mẫu học tập**, không phải cấu hình mặc định cho tất cả ứng dụng. Google khuyến nghị autohealing health check bảo thủ; `unhealthy-threshold` **lớn hơn 1**, thường khoảng **3 hoặc hơn**, `timeout` đủ rộng so với thời gian phản hồi bình thường và không vượt `check-interval`.

### 4.1. Hiểu initial delay chính xác

**Initial delay** là thời gian MIG cho VM mới hoàn tất boot, chạy startup script và ứng dụng khởi tạo. Cơ chế có những chi tiết quan trọng:

- Giá trị có thể từ **0 đến 3600 giây**.
- Theo tài liệu, **Console** có thể đặt mặc định **300 giây**, trong khi **API/CLI khi không chỉ định** có thể mặc định **0 giây**. **Nên đặt tường minh**.
- Đồng hồ bắt đầu khi VM trong MIG chuyển `currentAction` sang **`VERIFYING`**, không đơn giản tính từ lúc người vận hành bấm Create.
- Trong cửa sổ này, MIG **bỏ qua kết quả health check thất bại**, tránh recreate VM đang warm up.
- **Nếu probe báo healthy trước khi hết initial delay**, MIG xem initialization hoàn thành và có thể kết thúc cửa sổ bảo vệ sớm.
- Đây **không phải** delay cố định luôn chờ đủ 300 giây trước khi đưa VM vào luồng xử lý. LB có health check/readiness riêng để quyết định nhận traffic.

~~~mermaid
sequenceDiagram
  participant M as MIG controller
  participant V as VM mới
  participant H as Autohealing probe
  M->>V: Create VM từ template
  V-->>M: RUNNING
  M->>V: currentAction = VERIFYING
  Note over M: Bắt đầu initial delay
  H->>V: GET /internal/health/live
  V-->>H: Timeout khi app đang boot
  H-->>M: Không khỏe
  Note over M: Tạm bỏ qua lỗi trong initial delay
  H->>V: Probe lại sau startup
  V-->>H: HTTP 200
  H-->>M: HEALTHY
  M-->>V: currentAction = NONE
~~~

### 4.2. Ước lượng thời gian phát hiện, không nhầm với SLA

Với interval 30s và unhealthy threshold 3, ba lần lỗi liên tiếp xảy ra trong khoảng **ít nhất hai chu kỳ interval** cộng thời gian probe/timeout và pha lịch; không được hứa “chính xác 90 giây”. Health checks được thực hiện bởi hệ thống phân tán và có độ trễ quan sát/điều khiển.

Một cách lập budget gần đúng:

~~~text
T_phát hiện ≈ thời gian chờ các probe liên tiếp + timeout/độ trễ quan sát
T_sửa chữa ≈ phát hiện + MIG queue + recreate VM + boot + app warmup
T_phục vụ ≈ sửa chữa + LB readiness + client retry / connection recovery
~~~

Giải pháp để rút ngắn tác động với người dùng là **load balancer chuyển traffic trước** khi autohealing bắt đầu recreate. Đừng giảm `unhealthy-threshold` xuống 1 chỉ để tìm “RTO thật thấp” nếu điều đó gây false positive và thay nhiều VM.

### 4.3. Đo thời gian warmup thay vì đoán

1. Lấy mẫu nhiều lần tạo VM từ cùng template, cùng zone/machine type.
2. Quan sát timestamp của thao tác `instances.insert` và lần đầu health check trả healthy.
3. Ghi **p95/p99** hoặc worst case thực tế có tính image pull, startup script, config, application initialization.
4. Chọn `initial-delay` cao hơn mức ổn định đã đo, có biên an toàn phù hợp.
5. Khi version mới khiến boot lâu hơn, điều chỉnh theo dữ liệu rồi mới rollout.

Ví dụ nếu p95 startup ≈ 160s và p99 ≈ 220s, `initial-delay=300s` có thể hợp lý cho bài lab. Tuy nhiên, nếu app treo ngay trong startup và **không bao giờ healthy**, MIG sẽ tiếp tục đánh giá sau thời gian này; initial delay quá dài cũng làm chậm repair của VM không thể khởi động.

### 4.4. Các giới hạn ổn định và thời gian khởi động của hệ thống monitoring

Theo tài liệu Google Cloud đang công bố, sau khi cấu hình health check, **có thể mất đến khoảng 10 phút** trước khi autohealing bắt đầu giám sát các instance trong MIG. Một VM mới ở trạng thái `UNKNOWN` hoặc `UNHEALTHY` trong giai đoạn xác minh **không nhất thiết** là lỗi cấu hình ngay lập tức.

MIG cũng bảo vệ tính ổn định khi nhiều VM cùng lỗi:

- Tại một thời điểm, MIG cố gắng repair tối đa **30% số VM trong mỗi zone**, **làm tròn lên**.
- Nếu một zonal MIG chỉ có một VM, hoặc regional MIG có một VM trong mỗi zone, VM đó vẫn có thể được repair.
- Nếu instance liên tục thất bại sau nhiều lần repair, MIG tăng dần khoảng cách giữa các lần thử, có thể tới **khoảng 60 phút**.
- Khi phần lớn instance unhealthy, MIG có thể trì hoãn các repair tiếp theo để tránh cùng lúc xóa sạch năng lực đang còn.

**Không coi repair đồng thời 30% là SLO của ứng dụng.** Đây là giới hạn phục hồi ở tầng MIG; nếu 60% VM đều lỗi vì một config chung, nhóm vẫn có thể không đủ năng lực nhận traffic.

## 5. Bố cục triển khai thử nghiệm

Chúng ta giả định **đã có instance template** chạy web app lắng nghe HTTP cổng **8080** với endpoint `/internal/health/live`. Bài học sẽ hướng dẫn gắn health check cho một **zonal MIG trong project lab**. Không gắn chính sách vào MIG production khi chưa kiểm tra firewall và health endpoint.

| Tài nguyên | Giá trị ví dụ |
| --- | --- |
| Project | `LAB_PROJECT_ID` |
| Zone | `asia-southeast1-a` |
| Region | `asia-southeast1` |
| VPC | `lab-vpc` |
| Subnet | `lab-subnet` |
| Instance template có ứng dụng | `web-v1-template` |
| MIG | `web-autoheal-mig` |
| Network tag trên template/VM | `autoheal-web` |
| Global health check | `web-autoheal-hc` |
| VPC firewall rule | `allow-web-autoheal-probes` |
| HTTP liveness endpoint | `/internal/health/live` |
| Port | `8080` |
| Health check interval / timeout | `30s` / `10s` |
| Healthy / unhealthy thresholds | `2` / `3` |
| MIG initial delay | `300s` |

**Điều kiện trước lab:**

- Compute Engine API đã bật, billing/quota cho VM, disk, network và health checks được phê duyệt.
- Có quyền tạo health checks và sửa MIG; tạo firewall và template theo IAM tối thiểu.
- `web-v1-template` **thật sự cài được ứng dụng**; startup script/image hoàn chỉnh và đã thử trên một VM riêng nếu cần.
- VPC/subnet và network tag tồn tại; các IP/CIDR không xung đột chính sách tổ chức.
- Có người chịu trách nhiệm giám sát và **một cửa sổ lab** để thử lỗi, không làm gián đoạn production.
- Có phương án rollback nếu health check bị cấu hình sai; log và chi phí được chấp nhận.

**Phạm vi quyền:** `compute.healthChecks.create`, `compute.healthChecks.use`, `compute.instanceGroupManagers.update` và quyền firewall/network tương ứng là ví dụ quyền cần xác minh. Các vai trò thường gặp gồm `roles/compute.networkAdmin`, `roles/compute.securityAdmin` và `roles/compute.instanceAdmin.v1` theo tác vụ; đừng cấp `Owner` toàn project để “sửa nhanh” lỗi thiếu IAM.

### 5.1. Vì sao lab giả định template đã có ứng dụng?

Một instance template chỉ khai báo image Debian trống **không tự có** HTTP server trên cổng 8080. Nếu tạo MIG với template đó rồi bật autohealing, mọi probe sẽ timeout và MIG liên tục recreate VM. Điều này sẽ khiến bài học kiểm thử sai vấn đề.

Có hai cách chuẩn bị:

1. Dùng **golden image** chứa ứng dụng và một quy trình khởi động đáng tin cậy.
2. Dùng **startup script** trong instance template để cài và chạy ứng dụng từ artifact/version cụ thể; cần Private Google Access, Cloud NAT hoặc mirror để tải dependency nếu VM private.

Khi ứng dụng đã được triển khai, **kiểm thử endpoint trên một VM cùng template trước** rồi mới kết nối health check với autohealing.

### 5.2. Kiểm tra ứng dụng từ bên trong VM

Trong VM test thuộc đúng VPC/subnet và có quyền truy cập ứng dụng, dùng:

~~~bash
# Lệnh chỉ đọc, chạy từ guest OS hoặc host có quyền đến IP VM
curl --connect-timeout 3 --max-time 10 \
  -i http://127.0.0.1:8080/internal/health/live

# Nếu probe mạng sẽ truy cập địa chỉ nội bộ, thử trực tiếp IP đó:
curl --connect-timeout 3 --max-time 10 \
  -i http://VM_INTERNAL_IP:8080/internal/health/live

# Kiểm tra service/listener Linux
ss -lntp | grep ':8080'
~~~

**Kết quả mong đợi:** HTTP 200 trên **internal IP**, không chỉ `127.0.0.1`. Nếu VM có health app nhưng không cho phép IP network interface nhận kết nối, health check của Google sẽ thất bại.

## 6. Tạo health check cho autohealing

### 6.1. Console

1. Mở [Google Cloud Console → Health checks](https://console.cloud.google.com/compute/healthChecks).
2. Chọn **Create health check**, đặt tên `web-autoheal-hc`.
3. Chọn scope **Global** cho ví dụ (regional health check cũng được hỗ trợ khi phù hợp thiết kế).
4. Protocol **HTTP**; port **8080**, request path **`/internal/health/live`**.
5. Đặt `check interval=30s`, `timeout=10s`, `healthy threshold=2`, `unhealthy threshold=3`.
6. Review, tạo health check. **Chưa gắn MIG** nếu firewall/probe path chưa được xác minh.

**Scope global vs regional:** Regional health check có thể giúp giảm phụ thuộc cross-region và phù hợp ràng buộc dữ liệu; global thuận tiện khi nhiều MIG ở các region cần dùng chung một health check. Hãy dựa vào kiến trúc và vùng được hỗ trợ, không cố chọn global chỉ vì tên nghe “sẵn sàng hơn”.

### 6.2. Google Cloud CLI

Lệnh sau tạo **global HTTP health check** dành cho autohealing. Đây là **lệnh thay đổi hạ tầng**, chỉ chạy trong lab được phép:

~~~bash
gcloud compute health-checks create http web-autoheal-hc \
  --port=8080 \
  --request-path=/internal/health/live \
  --check-interval=30s \
  --timeout=10s \
  --healthy-threshold=2 \
  --unhealthy-threshold=3 \
  --global \
  --project=LAB_PROJECT_ID
~~~

Kiểm tra lại, chỉ đọc:

~~~bash
gcloud compute health-checks describe web-autoheal-hc \
  --global \
  --format="yaml(name,type,checkIntervalSec,timeoutSec,healthyThreshold,unhealthyThreshold,httpHealthCheck)" \
  --project=LAB_PROJECT_ID
~~~

**Ý nghĩa:** Cấu hình này không tự sửa VM nào. Chỉ sau khi một **MIG** dùng health check trong autohealing policy và policy đặt action sửa chữa, kết quả mới có thể kích hoạt recreate instance.

### 6.3. Firewall để health check probes tiếp cận VM

Google Cloud tài liệu autohealing nêu nguồn IPv4 probes:

~~~text
130.211.0.0/22
35.191.0.0/16
~~~

Cho phép **chỉ port 8080** từ các ranges này đến VM trong MIG. Với lab VPC tùy chỉnh, dùng **network tag** để thu hẹp phạm vi:

~~~bash
gcloud compute firewall-rules create allow-web-autoheal-probes \
  --network=lab-vpc \
  --direction=INGRESS \
  --priority=1000 \
  --action=ALLOW \
  --rules=tcp:8080 \
  --source-ranges=130.211.0.0/22,35.191.0.0/16 \
  --target-tags=autoheal-web \
  --enable-logging \
  --project=LAB_PROJECT_ID
~~~

Rule này có tác động thật và có thể trùng với chính sách firewall khác. **Đặt tag `autoheal-web` trong instance template** trước khi tạo MIG; nếu template không có tag, rule sẽ **không áp dụng** cho các VM.

Nếu VPC dùng hierarchical/network firewall policies, cần kiểm tra deny có hiệu lực cao hơn. Nếu hệ thống dùng health check IPv6 hoặc loại LB với nguồn/đường probe đặc thù, tham khảo [health check probe sources](https://docs.cloud.google.com/load-balancing/docs/health-check-concepts) theo loại backend thay vì sao chép máy móc hai CIDR IPv4.

**Cảnh báo về nhầm dải IP:** `35.235.240.0/20` thường liên quan **IAP TCP forwarding**, **không phải** hai dải probe health check IPv4 ở trên. Mở nhầm dải IAP sẽ khiến health checker không tiếp cận VM.

Kiểm tra rule:

~~~bash
gcloud compute firewall-rules describe allow-web-autoheal-probes \
  --format="yaml(network,direction,allowed,sourceRanges,targetTags,priority)" \
  --project=LAB_PROJECT_ID
~~~

### 6.4. Vì sao cần cho phép probe trước khi bật repair?

Nếu firewall chặn probe, VM đang phục vụ ứng dụng bình thường cũng có thể hiện `TIMEOUT`/`UNHEALTHY`. Khi bật autohealing, MIG có thể **xóa rồi tạo lại VM khỏe**, tiếp tục nhận `TIMEOUT` và lặp vô ích. Trước khi thay đổi policy production, kiểm tra từ nguồn mạng được phép, logs và địa chỉ/port thật của health check.

### 6.5. Cách xử lý health endpoint có xác thực

MIG health check không hoạt động như một người dùng ứng dụng có JWT/IAM token tùy ý. Tránh yêu cầu login, redirect tới trang auth hoặc kiểm tra session cookie với endpoint dành cho probe.

Một thiết kế phù hợp là **endpoint liveness không chứa dữ liệu nhạy cảm**, trả mã đơn giản và được bảo vệ bằng firewall chỉ cho Google probes. Nếu hệ thống dùng mTLS/TLS bắt buộc hoặc zero trust, kiểm tra khả năng kết nối/protocol của loại health check và thiết kế adapter theo chính sách; không mở một cổng internet công khai chỉ để cho probe hoạt động.

### 6.6. Giới hạn chia sẻ health check

Theo tài liệu hiện hành, **một health check có thể áp dụng cho tối đa 50 MIGs**. Nếu tổ chức quản lý nhiều hơn, tạo nhiều health checks; thường nên tách theo loại workload, port/protocol và mức bảo thủ. Không tái sử dụng health check chung cho API/worker có thời gian bootstrap hoặc tiêu chí liveness khác nhau.

## 7. Gắn autohealing policy vào Managed Instance Group

### 7.1. Phương án an toàn: kiểm tra trước khi bật repair

Nếu MIG đang phục vụ ứng dụng, đừng gắn health check mới rồi cho autohealing thay VM ngay lập tức. Một cách rollout ít rủi ro là:

1. Kiểm thử endpoint trên VM thử nghiệm có cùng image/config.
2. Xác nhận firewall ranges, port và network tag.
3. Tạo health check riêng dành cho autohealing.
4. **Gắn health check với chế độ chỉ giám sát, không repair**, dùng `--action-on-vm-failed-health-check=do-nothing`.
5. Theo dõi `HEALTH_STATE` trên mọi VM trong một khoảng đủ dài, gồm lúc tải cao và rolling update nếu phù hợp.
6. Sửa lỗi false positive, tuning interval/timeout/initial delay.
7. Chỉ khi kết quả ổn định, bật `repair` cho ứng dụng đã sẵn sàng bị recreate.

**Khác biệt quan trọng:** Chế độ không autoheal chỉ ngừng sửa VM **do application health check**. Các quy tắc sửa **VM failed** và điều khiển group còn tùy `defaultActionOnFailure`/lifecycle policy. Không coi `do-nothing` là tắt toàn bộ chức năng quản lý MIG.

### 7.2. Tạo zonal MIG mới ở chế độ quan sát trước

Ví dụ dùng **instance template đã cài ứng dụng** `web-v1-template`, với network tag `autoheal-web` và HTTP listener 8080:

~~~bash
# Tạo tài nguyên: chạy trong project LAB đã phê duyệt
gcloud compute instance-groups managed create web-autoheal-mig \
  --base-instance-name=web-autoheal \
  --template=web-v1-template \
  --size=3 \
  --zone=asia-southeast1-a \
  --health-check=web-autoheal-hc \
  --initial-delay=300 \
  --action-on-vm-failed-health-check=do-nothing \
  --project=LAB_PROJECT_ID
~~~

**Tại sao chưa bật repair ngay?** Vì lúc đầu ta chưa quan sát được health check có phản ánh đúng ứng dụng trên tất cả các instance hay không. Chế độ này vẫn giúp lấy health states để xác minh.

Nếu `web-v1-template` là **regional template** thay vì global, dùng resource URL thích hợp theo tài liệu CLI; ví dụ trên giả định global template. Nếu VPC/subnet được cấu hình trong template thì MIG sẽ tạo VM theo template đó; lệnh MIG không tự thay mạng cho VM.

Sau khi thấy VM có health state đúng trong vài chu kỳ và thử tải thành công, bật autohealing:

~~~bash
# Thay đổi policy, có thể kích hoạt RECREATE khi VM unhealthy
gcloud compute instance-groups managed update web-autoheal-mig \
  --zone=asia-southeast1-a \
  --action-on-vm-failed-health-check=repair \
  --project=LAB_PROJECT_ID
~~~

**Không áp dụng lệnh bật `repair` trên production** khi chưa có maintenance/change approval, giám sát và rollback. Một health check sai có thể khiến nhiều VM bị thay, phá trạng thái phiên hoặc giảm năng lực ứng dụng.

### 7.3. Áp dụng với MIG đã tồn tại

Nếu MIG đã được tạo mà chưa có health check, có thể gắn health check cùng initial delay, ban đầu không repair:

~~~bash
gcloud compute instance-groups managed update MIG_NAME \
  --health-check=web-autoheal-hc \
  --initial-delay=300 \
  --action-on-vm-failed-health-check=do-nothing \
  --zone=ZONE \
  --project=LAB_PROJECT_ID
~~~

Sau khi quan sát đủ lâu và phê duyệt:

~~~bash
gcloud compute instance-groups managed update MIG_NAME \
  --action-on-vm-failed-health-check=repair \
  --zone=ZONE \
  --project=LAB_PROJECT_ID
~~~

Với **regional MIG**, thay `--zone=ZONE` bằng `--region=REGION` và xác minh health check scope. Một regional health check cũng có thể được tham chiếu bằng resource path khu vực khi cần, không tự suy rằng mọi MIG phải dùng global health check.

### 7.4. Thiết lập trong Console

1. Mở [Compute Engine → Instance groups](https://console.cloud.google.com/compute/instanceGroups/list).
2. Chọn đúng MIG, xác nhận **project**, **zone/region**, instance template và số VM.
3. Chọn **Edit** → mở mục **Instance lifecycle and autohealing**.
4. Chọn **Health check** đã tạo; nhập `Initial delay` dựa thời gian bootstrap.
5. Trong **On failed health check**, có thể chọn **No action** để quan sát trước.
6. Lưu, kiểm tra trạng thái các VM và health check.
7. Sau khi xác minh, đổi hành động sang repair theo quy trình quản lý thay đổi.

Tên từng nút trên Console có thể thay đổi. Luôn xác nhận health check target port/path và ý nghĩa hành động trước khi bấm Save.

### 7.5. Một policy cho một MIG

MIG hỗ trợ **một autohealing policy** trỏ tới **một health check**. Bạn có thể có health checks khác cho load balancer/backend services; không nên cố nhét nhiều autohealing policies vào cùng một MIG để kiểm tra DB, cache, queue và HTTP riêng lẻ.

Nếu ứng dụng có nhiều thành phần, hãy thiết kế health endpoint tổng hợp **những tín hiệu local cần thiết** cho việc recreate, đồng thời ghi metrics chi tiết ở các dashboard riêng.

## 8. Đọc trạng thái, hành động và dấu hiệu repair

### 8.1. Lệnh chỉ đọc

~~~bash
# Thông tin MIG và autohealing policy
gcloud compute instance-groups managed describe web-autoheal-mig \
  --zone=asia-southeast1-a \
  --format="yaml(name,targetSize,autoHealingPolicies,instanceLifecyclePolicy,status)" \
  --project=LAB_PROJECT_ID

# Mỗi instance và health state hiện tại
gcloud compute instance-groups managed list-instances web-autoheal-mig \
  --zone=asia-southeast1-a \
  --project=LAB_PROJECT_ID

# Danh sách MIG đang có trong project
gcloud compute instance-groups managed list \
  --project=LAB_PROJECT_ID

# Thông số health check
gcloud compute health-checks describe web-autoheal-hc \
  --global \
  --project=LAB_PROJECT_ID

# Xem các repair operations đã được ghi nhận (lọc theo loại operation)
gcloud compute operations list \
  --filter='operationType~compute.instances.repair.*' \
  --project=LAB_PROJECT_ID
~~~

Với regional MIG, dùng `--region=REGION` cho lệnh describe/list-instances. Các repair operations là dữ liệu quá khứ, không phải một danh sách luôn đủ nguyên nhân ứng dụng; kết hợp logs và metric của service để xác định vì sao health check fail.

### 8.2. Các trạng thái HEALTH_STATE

| State | Ý nghĩa được Google Cloud mô tả | Cách xử lý |
| --- | --- | --- |
| `HEALTHY` | VM reachable và health endpoint đáp ứng tiêu chí health check | Đảm bảo readiness, SLO và workload metrics cũng khỏe |
| `UNHEALTHY` | VM có thể reachable nhưng phản hồi không đạt tiêu chí | Xem HTTP status/path, app logs, phụ thuộc local |
| `TIMEOUT` | Không kết nối được hoặc endpoint không phản hồi trước timeout | Xem firewall, listener, port, VPC, CPU/thread |
| `UNKNOWN` | Hệ thống health checking chưa xác định tình trạng VM | Chờ monitoring bắt đầu, xem cấu hình và dấu hiệu mất tín hiệu |
| `DRAINING` | VM đang drain, không tiếp nhận kết nối mới theo quy trình | Xem thao tác MIG/LB, đừng coi ngay là app crash |

Các VM mới có thể xuất hiện `UNHEALTHY` **trước khi được xác minh healthy**; trạng thái đó cần đặt trong bối cảnh `initial-delay` và `currentAction`. Khi `UNKNOWN`, MIG **không repair ngay**, tránh sửa nhầm instance mà hệ thống tạm thời chưa có tín hiệu.

### 8.3. Current actions và ổn định của MIG

Một VM trong MIG có thể trải qua:

~~~text
CREATING -> VERIFYING -> NONE
                          |
                          +-- Health becomes UNHEALTHY/TIMEOUT
                          v
                       RECREATING
                          |
                          +-- New VM: CREATING -> VERIFYING -> NONE
~~~

Đây là **sơ đồ khái quát**, không phải danh sách đầy đủ các trạng thái/action API trong mọi trường hợp.

- `CREATING`: MIG đang tạo instance.
- `VERIFYING`: VM đã chạy, MIG đang xác minh health/initialization.
- `NONE`: không có tác vụ MIG đang thực hiện trên VM đó.
- Recreate do lỗi có thể xuất hiện trong danh sách **current action**, operations và audit/logs.

Ở cấp MIG có `status.isStable`. Giá trị này **không đơn thuần là “mọi health check đều trả 200”**: một MIG đang autoscale, phân phối lại VM hoặc rolling update cũng có thể chưa stable. Cần xem **target size, current actions, health states, các phiên bản template và backend health** cùng nhau.

### 8.4. Health state change logs và nhật ký điều tra

Compute Engine có thể ghi **health state change logs** mặc định khi instance đổi trạng thái health. Dùng Logs Explorer để:

1. Lọc theo project, group/instance name và khoảng thời gian sự cố.
2. So timestamp: startup, health state thay đổi, MIG repair operation và ứng dụng bắt đầu phục vụ.
3. Xác định lỗi bắt đầu sau khi đổi template, firewall, IAM/service account hoặc cấu hình health check không.
4. So số lần recreate với HTTP 5xx, p95/p99 latency và mức traffic còn lại trên LB.
5. Gắn cảnh báo cho **repair rate**, **unhealthy instances**, **MIG not stable**, chứ không chỉ VM CPU.

Logs có thể phát sinh phí Cloud Logging sau ngưỡng miễn phí, tùy retention/volume. Không đổ tất cả probe payload và bí mật ứng dụng vào log.

## 9. Quy trình kiểm chứng an toàn trước khi bật repair production

Một health check có thể **trông hợp lệ** trên Console nhưng vẫn gây nhiều false positive khi gặp tải thật. Hãy chia kiểm chứng thành ba lớp.

### 9.1. Kiểm chứng cấu hình tĩnh

- Đúng **project/VPC**, subnet/region/zone và network tags của instance template.
- Listener thực sự chạy trên port/path đã khai báo.
- VPC ingress firewall cho **hai probe IPv4 ranges** tới đúng target.
- Không có hierarchical firewall policy chặn probe.
- Health endpoint trả status như yêu cầu (không login/redirect/404).
- Health check scope global/regional phù hợp.
- Initial delay dài hơn thời gian bootstrap thực tế có biên an toàn.
- Đã tách health check autohealing và load balancing khi ứng dụng cần mức nhạy khác nhau.
- MIG có số instance/zone đủ để duy trì dịch vụ khi repair.

### 9.2. Quan sát ở chế độ do-nothing

~~~text
Bước 1: Gắn health check + action=do-nothing
     ↓
Bước 2: Xem HEALTH_STATE mọi VM
     ↓
Bước 3: Chạy traffic thử nghiệm (readiness/LB riêng)
     ↓
Bước 4: Xem log khi VM mới được tạo / app startup
     ↓
Bước 5: Xem bất kỳ TIMEOUT/UNHEALTHY nào và giải thích
     ↓
Bước 6: Nếu false positive -> sửa endpoint/threshold/firewall
     ↓
Bước 7: Đủ bằng chứng -> phê duyệt action=repair
~~~

Chỉ sau khi health signal đáng tin cậy mới bật repair. Với một nhóm lớn, có thể thử **MIG canary/nhóm lab** trước khi áp dụng chính sách tương tự cho production.

### 9.3. Controlled fault injection trong lab

**Chỉ thực hiện trên MIG thử nghiệm có owner rõ ràng. Không tạo sự cố trên production.**

| Bài thử | Kỳ vọng | Điều phải quan sát |
| --- | --- | --- |
| Ứng dụng trả 200 và lắng nghe internal IP | VM được đánh giá healthy | HEALTH_STATE, time to healthy |
| App vừa boot, trả 503 trong khoảng khởi tạo | Không bị recreate sớm khi còn initial delay | currentAction VERIFYING, thời gian |
| Dừng service ứng dụng trên **một VM lab** | Sau ngưỡng, VM bị recreate nếu repair bật | Operations, instance ID, startup log |
| Làm endpoint trả 503 trong vài giây | Không recreate nếu chưa đạt unhealthy threshold | Probe logs, threshold |
| Chặn probe bằng rule trong môi trường lab biệt lập | Có TIMEOUT và nguy cơ recreate sai | Firewall logs, repair rate |
| Một dependency bên ngoài lỗi, liveness vẫn 200 | Không recreate hàng loạt nếu app vẫn có thể tự phục hồi | LB readiness, app errors và dependency SLO |
| Template mới boot chậm hơn | Initial delay có đủ không? | p95 startup, số recreate |
| Một VM đang repair khi tải cao | LB còn đủ backend healthy không? | Error rate, backend capacity |

**Không nên chủ động chặn firewall của tất cả VM đang chạy** chỉ để chứng minh autohealing. Việc đó có thể tạo sửa chữa dây chuyền và không phản ánh lỗi ứng dụng.

### 9.4. Thử dừng một service đúng cách

Nếu trong lab có service Linux tên `demo-java.service` đã được triển khai trên VM do MIG quản lý, có thể mô phỏng lỗi **trên một VM do bạn sở hữu**, ghi lại tên instance trước khi thao tác:

~~~bash
# Chạy bên trong đúng VM lab đã chọn, chỉ khi có phê duyệt thử lỗi:
sudo systemctl stop demo-java.service
~~~

Đây là **lệnh gây gián đoạn chủ động**. Khi autohealing bật, MIG có thể recreate VM thay vì chờ bạn khởi động lại service. Nếu cần khôi phục chủ động trước khi MIG xử lý, có thể chạy `sudo systemctl start demo-java.service` trong cửa sổ kiểm thử; không bảo đảm phục hồi trước ngưỡng repair. Quan sát trạng thái instance và log thay vì đoán thời gian chính xác.

Không chọn cách `gcloud compute instances stop VM_NAME` để mô phỏng **application health failure**: hành động stop trực tiếp VM thuộc MIG còn kích hoạt **failed-VM repair** của MIG, khiến bạn kiểm thử một cơ chế khác.

## 10. Những tình huống đặc biệt và trade-off

### 10.1. Toàn nhóm unhealthy vì Cloud SQL bị lỗi

Giả sử tất cả VM Java cần gọi Cloud SQL. Nếu liveness endpoint thực hiện `SELECT 1` lên DB và fail khi DB mất kết nối, toàn MIG có thể thành unhealthy trong cùng thời điểm. Recreate hàng loạt tạo các vấn đề:

- Mất các phiên đang xử lý.
- Tăng đột biến số kết nối khi các VM cùng khởi động lại.
- Làm chậm recovery của DB.
- Đưa toàn bộ nhóm vào vòng lặp repair dù lỗi gốc không nằm trên VM.

**Thiết kế tốt hơn:** Liveness kiểm tra khả năng phục hồi local; readiness của LB có thể phản ánh khả năng xử lý request, dependency monitoring cảnh báo riêng. Nếu ứng dụng không thể phục vụ vì DB outage, **cần xử lý DB và fallback**, không mặc định phá VM.

### 10.2. CPU cao/GC stop-the-world tạm thời

Một VM Java dưới tải cao có thể phản hồi chậm hơn vài giây do GC, CPU throttling, disk I/O hoặc thread pool đầy. Nếu timeout 1s và unhealthy threshold 1, MIG có thể hiểu thành lỗi không phục hồi.

Điều chỉnh có cơ sở:

- Đo p99 response time của endpoint trong peak load.
- Tăng timeout đủ so với p99, nhưng **không lớn hơn interval**.
- Đặt unhealthy threshold ít nhất 3 như gợi ý của Google.
- Đảm bảo health endpoint **không xếp sau hàng đợi kinh doanh** quá lâu.
- Dùng CPU/autoscaler/Cloud Monitoring để xử lý thiếu năng lực; chỉ dùng autohealing khi instance không thể phục hồi.

### 10.3. Initial delay quá ngắn và vòng lặp recreate

Ứng dụng mất 4 phút để tải image/đăng ký và chuẩn bị cache, nhưng `initial-delay=60s`. Probe cứ trả 503, MIG kết luận unhealthy rồi tạo lại. Mỗi VM chưa bao giờ sống đủ lâu để ready.

Cách xử lý:

1. Tạm chuyển **health check action sang do-nothing** nếu có nguy cơ lặp repair.
2. Kiểm tra startup logs, port, HTTP status, startup time thật.
3. Điều chỉnh initial delay và startup script nếu cần.
4. Tạo VM canary từ template mới để xác minh ổn định.
5. Chỉ bật repair lại khi endpoint có thể đạt healthy trong khoảng đo được.

### 10.4. Initial delay quá dài

Cửa sổ 1800s có thể che một VM **không bao giờ boot xong** trong 30 phút. Điều này giảm nguy cơ false positive nhưng tăng thời gian lỗi được phát hiện/sửa.

Cần cân bằng: dùng phân phối startup times của workload và **không** sử dụng thời gian 3600s chỉ để “hết lỗi” khi nguyên nhân là firewall hoặc port sai.

### 10.5. Template xấu và “repair storm”

Một template mới có startup script lỗi hoặc phiên bản ứng dụng lỗi đồng nhất trên mọi VM. Autohealing có thể chỉ tạo lại những VM tiếp tục chạy template lỗi; cần **rollback template/version** theo chính sách phát hành. Khi nhiều instances bị lỗi, giới hạn repair 30%/zone và backoff giúp giảm tác động, **không làm template trở nên đúng**.

Cách điều tra:

- Kiểm tra version/template trên VM unhealthy so với healthy.
- Tìm timestamp phát hành, image digest, startup script changes.
- Tạm ngừng tự động repair do health check nếu cần để có thời gian thu thập logs.
- Rollback release hoặc sửa startup config qua **MIG-managed workflow**.
- Tránh chỉnh thủ công từng VM ngoài MIG rồi coi đó là phương án lâu dài.

### 10.6. Repair và update policy có thể tương tác

MIG quản lý những thay đổi template/phiên bản, và khi repair có thể **giữ cấu hình từng instance đã dùng** hoặc **áp dụng cấu hình mới** tùy **force update on repair** và update policy. Theo tài liệu CLI hiện hành, **update on repair mặc định tắt**; khi cần buộc cập nhật lên template hiện tại ở lần sửa, phải lựa chọn chủ động và đánh giá rủi ro.

Không dùng autohealing làm công cụ “rolling deploy” không có điều khiển. Việc phát hành nên dùng update policy, canary, max surge/max unavailable và xét health check của LB/ứng dụng đúng mục tiêu.

### 10.7. Stateful MIG, lưu trữ và giao dịch

Nếu VM lưu dữ liệu vào boot disk/local disk mà không có cơ chế preserve state, việc recreate có thể mất dữ liệu. Với **stateful MIG**, có thể cấu hình preserved disks/IPs theo tính năng và giới hạn, nhưng ứng dụng vẫn cần xử lý:

- Giao dịch đang chạy, idempotency, duplicate messages.
- Thời gian attach disk/restore filesystem.
- Khóa ứng dụng và thay đổi instance identity.
- RTO/RPO của DB/storage, quota và dependency.
- Trường hợp mất zone làm disk không khả dụng.

Cơ chế **autohealing chỉ đảm bảo cố gắng tái tạo VM**, không cung cấp backup, transaction recovery hoặc consistency của dữ liệu.

### 10.8. Liveness HTTP 200 nhưng ứng dụng thật vẫn lỗi

Một tiến trình có thể trả 200 cho health endpoint nhưng toàn bộ worker xử lý hàng đợi đã deadlock. Để không false healthy:

- Thiết kế tín hiệu **local progress** từ worker quan trọng (ví dụ cập nhật heartbeat trong bộ nhớ).
- Kiểm tra heartbeat không bị đứng quá một ngưỡng hợp lý.
- Không fail chỉ vì queue bên ngoài trống/đầy hoặc dịch vụ ngoài lỗi nhất thời.
- Ghi log và metric chi tiết để operator phân biệt local failure với dependency outage.

Health check tốt là **định nghĩa điều kiện phải repair** của ứng dụng, không phải “một đường dẫn GET luôn trả OK”.

## 11. Chẩn đoán lỗi dựa vào triệu chứng

| Triệu chứng | Nguyên nhân có thể | Cách xác minh và hướng xử lý |
| --- | --- | --- |
| VM RUNNING nhưng `TIMEOUT` | Firewall chặn probes, không listener, bind loopback, sai port, network policy | Kiểm tra IP/port từ VM khác, firewall ranges và logs |
| `UNHEALTHY` dù app đang nhận traffic | Liveness path trả 404/302/401/500; health check mong status khác | Xem HTTP response thực, config health check/path |
| Mọi VM cùng unhealthy ngay sau khi gắn policy | Shared firewall, sai template/tag, thiếu health endpoint, DB dependency lỗi | Dùng do-nothing, kiểm tra common cause trước khi bật repair |
| VM mới bị recreate liên tục trong startup | Initial delay quá ngắn hoặc startup script hỏng | So thời gian boot, chỉnh delay hoặc sửa template |
| `UNKNOWN` lâu hơn dự kiến | Monitoring mới bật, mất health signal hoặc quyền/cấu hình bất thường | Kiểm tra thời gian, health check và trạng thái MIG |
| VM unhealthy nhưng chưa repair | Do-nothing, đang initial delay, giới hạn 30%, backoff hoặc lỗi operations | Xem autohealing policy, currentAction, operations |
| Repair liên tục không cải thiện | Lỗi ở template, config, version, dependency chung | Rollback, sửa nguồn lỗi, không sửa triệu chứng |
| LB báo backend unhealthy nhưng MIG vẫn HEALTHY | LB readiness nghiêm hơn autohealing liveness | Có thể là thiết kế đúng; kiểm tra SLA/metrics |
| MIG HEALTHY nhưng khách hàng bị 5xx | Health check quá đơn giản, DB lỗi, LB config hoặc network | Quan sát request metrics, trace và dependency |
| Vừa rollout release, group `isStable=false` | Update, autoscaling, creation hoặc repair còn đang chạy | Xem MIG current actions/target size/version |
| Chỉ một zone repair nhiều lần | Zonal issue, thiếu capacity, instance template/network khác | Xem distribution, quota, underlying operations |
| Logs của health check không thấy | Logging cấu hình chưa bật, IAM thiếu hoặc trễ thu thập | Kiểm tra Logging config, health state change logs |
| Port chỉ mở cho IAP, health check luôn timeout | Dải IAP khác nguồn Google probes | Mở đúng 130.211.0.0/22 và 35.191.0.0/16 cho port probe |
| VM private không tải được artifact khi recreate | Thiếu Cloud NAT, Private Google Access/PSC hoặc IAM | Test startup dependencies từ một VM cùng template |
| Repair gây mất trạng thái | Session/đĩa không được lưu bền | Dời state ngoài VM hoặc cấu hình stateful MIG |

**Quy trình chẩn đoán ngắn:**

~~~mermaid
flowchart TD
  S["MIG có VM unhealthy"] --> A{"Có đang bật action=repair?"}
  A -- "Không" --> M["Theo dõi, sửa health endpoint/config"]
  A -- "Có" --> P{"Đang trong initial delay?"}
  P -- "Có" --> W["Đợi boot/health, đo thời gian"]
  P -- "Không" --> H{"UNHEALTHY hay TIMEOUT?"}
  H -- "TIMEOUT" --> NET["Kiểm tra firewall, IP, listener, port, timeout"]
  H -- "UNHEALTHY" --> APP["Kiểm tra HTTP response, app logs, dependencies"]
  NET --> R{"Lỗi có chung mọi VM?"}
  APP --> R
  R -- "Có" --> SYS["Kiểm tra release, VPC, DB, shared config;\ntránh repair storm"]
  R -- "Không" --> ONE["Kiểm tra instance riêng, memory, GC, disk"]
  SYS --> FIX["Đưa ra sửa cấu hình/rollback có kiểm soát"]
  ONE --> FIX
~~~

## 12. Tắt hoặc điều chỉnh autohealing an toàn

Khi health check mới gây vòng lặp recreate, **đừng xóa VM một cách thủ công** hoặc giảm target size như một phản xạ. Xác định nguyên nhân và chọn biện pháp ít tác động nhất.

### 12.1. Tạm không repair vì health check

~~~bash
# Thay đổi policy: tắt application-based autohealing repair,
# vẫn giữ health check để theo dõi (trong phạm vi được phê duyệt)
gcloud compute instance-groups managed update MIG_NAME \
  --action-on-vm-failed-health-check=do-nothing \
  --zone=ZONE \
  --project=LAB_PROJECT_ID
~~~

Sau khi sửa và quan sát lại, bật:

~~~bash
gcloud compute instance-groups managed update MIG_NAME \
  --action-on-vm-failed-health-check=repair \
  --zone=ZONE \
  --project=LAB_PROJECT_ID
~~~

Nếu chỉ muốn autohealing theo hành vi mặc định của MIG, có thể dùng `default-action` theo chính sách hiện hành. **Không nhầm** `--action-on-vm-failed-health-check` với `--default-action-on-vm-failure`: chúng có thể được điều khiển độc lập.

### 12.2. Gỡ health check khỏi autohealing policy

Khi cần hủy cấu hình health check trên MIG theo quy trình phê duyệt:

~~~bash
gcloud compute instance-groups managed update MIG_NAME \
  --clear-autohealing \
  --zone=ZONE \
  --project=LAB_PROJECT_ID
~~~

**Tác động:** Lệnh này xóa health check khỏi autohealing policy, nên không còn khả năng đánh giá application health qua cấu hình đó. Không dùng lệnh trên production mà không có thay thế monitoring phù hợp.

### 12.3. Không vô hiệu hóa MIG repair cơ bản mà thiếu lý do

Google Cloud còn có `--default-action-on-vm-failure` để quản lý việc sửa VM failed ngoài ý muốn. Nếu đổi nó sang `do-nothing`, MIG có thể không tự sửa máy lỗi hạ tầng; tùy `onFailedHealthCheck`, autohealing cũng có thể bị ảnh hưởng. Đây là lựa chọn đặc biệt cho những workload/maintenance có kiểm soát, không phải phương án rollback mặc định khi health endpoint sai.

## 13. Quan sát vận hành, SLO và chi phí

Một chiến lược autohealing tốt cần biết **vì sao** VM được thay, **người dùng chịu tác động bao lâu** và **chi phí tăng bao nhiêu**.

### 13.1. Các metric và dashboard nên có

| Tín hiệu | Mục đích |
| --- | --- |
| Số VM theo health state | Nhìn phần năng lực đang khỏe/không khỏe |
| Tỷ lệ/thời gian repair | Phát hiện repair storm và template lỗi |
| Time from create to healthy | Tuning initial delay và startup regression |
| `targetSize` so với running instances | Kiểm tra tính ổn định năng lực |
| `status.isStable` và current actions | Phân biệt đang scale/update/verify/repair |
| LB backend health và HTTP 5xx | Đo tác động trực tiếp lên người dùng |
| Request latency p95/p99 | Nhận diện CPU/GC/IO và sự cố sau repair |
| Autoscaler metrics | Phân biệt thiếu capacity với VM chết |
| Cloud Logging/audit/Compute operations | Phân tích nguyên nhân, thay đổi cấu hình |
| Số lần VM restart/recreate theo version | Phát hiện release lỗi lặp lại |
| Startup script / artifact retrieval failures | Điều tra VM mới không boot healthy |

Ví dụ cảnh báo:

- Nhiều instance `UNHEALTHY/TIMEOUT` liên tiếp trong vài phút.
- Số repair operations vượt mức bình thường.
- Tỷ lệ LB backends healthy dưới mức tối thiểu cho SLO.
- Thời gian boot to HEALTHY tăng sau release.
- MIG không stable lâu bất thường và có nhiều lỗi ops.
- Repair nhiều VM cùng lúc với error rate tăng.
- Tài nguyên/zone không còn đủ capacity để tái tạo instance.

### 13.2. Liên kết logs với sự kiện phát hành

Khi phát hiện vòng lặp repair, lập bảng theo thời gian:

| Thời điểm | Sự kiện | Bằng chứng |
| --- | --- | --- |
| T0 | Release image/template mới | Deployment log, version |
| T1 | VM được tạo hoặc update | Compute operation |
| T2 | App startup, bind port | Guest logs |
| T3 | Health check thay trạng thái | Health change logs |
| T4 | MIG trigger repair | Repair operation |
| T5 | VM mới HEALTHY hoặc tiếp tục lỗi | List-instances, LB health |
| T6 | Lỗi người dùng hoặc traffic bình thường | HTTP metrics/traces |

Mục tiêu là biết **lỗi được phát hiện trước hay sau release**, và có phải do **app thật sự chết** hay **health-check configuration sai**.

### 13.3. Kiểm soát chi phí

Autohealing và logging có tác động chi phí:

- VM mới boot có thể tải lại dependencies và làm tăng network/disk/API operations.
- Các VM được replace tạo operation logs, startup logs và volume monitoring.
- Khi MIG có autoscaler, repair và scale-out cùng lúc có thể làm số VM biến động, tác động Compute Engine bill.
- Nếu instance là stateful và boot/restore lâu, tổng downtime có thể cao hơn việc khôi phục ở tầng ứng dụng.
- Việc ghi health state change logs có chi phí Cloud Logging sau phần miễn phí tùy gói.

Tối ưu **không có nghĩa tắt autohealing** để giảm log. Cần giảm false-positive repairs, tối ưu startup, cập nhật chuẩn và chọn retention/logging level theo nhu cầu SRE, bảo mật và tài chính.

## 14. Tình huống doanh nghiệp: API đặt hàng Java trên MIG

### 14.1. Bối cảnh

Công ty chạy hệ thống đặt hàng gồm:

- **Regional MIG** ba zone trong một region.
- **Java Spring Boot** trên các VM được dựng từ instance template.
- **External Application Load Balancer** phục vụ API HTTPS.
- **Cloud SQL** quản lý dữ liệu đơn hàng.
- **Pub/Sub** cho xử lý sự kiện.
- **Cloud Monitoring/Logging** theo dõi SLO và lỗi.
- **Autoscaler** tăng/giảm số VM khi traffic biến động.

Trong đợt khuyến mãi, một VM bị deadlock thread xử lý; hai VM còn lại vẫn hoạt động. Load balancer phải ngừng gửi request tới VM lỗi sớm, trong khi MIG cần thay nó để khôi phục capacity.

~~~mermaid
flowchart TD
  CLIENT["Khách hàng"] --> LB["External Application Load Balancer"]
  LB --> AZ1["VM Zone A healthy"]
  LB --> AZ2["VM Zone B unhealthy"]
  LB --> AZ3["VM Zone C healthy"]
  LBHC["LB readiness probe\nnhanh"] -. "Tạm loại khỏi traffic" .-> AZ2
  MIG["Regional MIG\nAutohealing liveness probe"] -. "Recreate sau ngưỡng" .-> AZ2
  AZ1 --> SQL["Cloud SQL"]
  AZ3 --> SQL
  AZ1 --> PUB["Pub/Sub"]
  AZ3 --> PUB
  MIG -. "Tạo lại từ template" .-> NEW["VM Zone B replacement"]
~~~

### 14.2. Hai health endpoints được chọn

| Endpoint | Tiêu chí | Chính sách |
| --- | --- | --- |
| `/internal/health/ready` | Ứng dụng sẵn sàng nhận request mới, dependency cần thiết trong giới hạn | LB check nhanh hơn, loại backend tạm thời |
| `/internal/health/live` | Tiến trình phản hồi, local worker cốt lõi hoạt động | MIG check bảo thủ, fail kéo dài mới replace |
| `/metrics` hoặc telemetry khác | HTTP errors, GC, worker lag, DB timeouts | Monitoring/alert, không tự nối tất cả lỗi vào autohealing |

Nếu Cloud SQL tạm outage, readiness có thể fail để bảo vệ người dùng; liveness vẫn có thể healthy và không tạo thêm tải cho DB. Nếu một Java process thực sự deadlock và không trả lời endpoint, autohealing sửa VM đó.

### 14.3. Phân tích một sự cố giả định

| Dấu hiệu | Cách giải thích | Hành động |
| --- | --- | --- |
| Một VM `TIMEOUT`, VM khác healthy | Lỗi local VM/port/hệ điều hành | Xem logs, để autohealing repair nếu đáp ứng điều kiện |
| Tất cả VM cùng `UNHEALTHY` sau release | Common config/template bug | Dừng repair storm, rollback release |
| LB unhealthy nhưng MIG HEALTHY | Readiness chặt hơn liveness | Kiểm tra dependency, autoscaler và LB capacity |
| VM liên tục `VERIFYING` | Startup chưa xong, image/config quá chậm | Xem startup timeline, chỉnh delay và template |
| App lỗi 5xx nhưng health endpoints healthy | Endpoint bỏ sót lỗi nghiệp vụ | Bổ sung metrics và định nghĩa health rõ hơn |
| Nhiều VM cùng bị repair khi DB unavailable | Liveness sai khi phụ thuộc DB | Sửa health contract, giảm coupling |

### 14.4. Bài học về kết quả cần đo

Không đánh giá thành công chỉ bằng “MIG đã tạo lại VM”. Cần chứng minh:

- Người dùng có ít 5xx/timeout hơn khi một VM treo.
- Remaining backends đủ capacity.
- VM mới từ template **thực sự ready**.
- Repair không gây duplicate orders/messages.
- Time to healthy nằm trong error budget/SLO được duyệt.
- Lỗi tập trung ở dependency/release chung không tạo nhiều recreate vô ích.

## 15. Bài thực hành có hướng dẫn

**Điều kiện:** Sử dụng project lab được phân quyền và một instance template chạy HTTP endpoint thật. Nếu không được phép tạo tài nguyên, có thể thực hiện phần lý luận với bảng giả định và đáp án.

### Phần A — Thiết kế

1. Định nghĩa workload, thời gian startup trung bình/p95/p99, peak load và failure mode có thể xảy ra.
2. Viết hợp đồng `/internal/health/live` và `/internal/health/ready`, chỉ rõ điều kiện HTTP 200/503.
3. Chọn `check-interval`, `timeout`, `healthy-threshold`, `unhealthy-threshold` có lập luận.
4. Chọn `initial-delay` đủ vượt p99 startup có biên an toàn, trong phạm vi 0–3600s.
5. Quy hoạch firewall theo nguồn probes và target network tag.
6. Chọn zonal/regional MIG và tối thiểu số VM để chịu được một instance/zone failure.
7. Xác nhận stateful stateless; không lưu dữ liệu quan trọng vào nơi bị mất khi recreate.

### Phần B — Thiết lập quan sát trước khi sửa

1. Xác minh health endpoint và firewall.
2. Tạo health check.
3. Gắn MIG với `--action-on-vm-failed-health-check=do-nothing`.
4. Quan sát `list-instances` và log qua nhiều chu kỳ.
5. Chạy tải hợp pháp hoặc kiểm thử trong lab; xác định có false positives không.
6. Sau khi phê duyệt, bật `repair`.

### Phần C — Thử lỗi một instance trong lab

1. Ghi tên một VM lab và health state đang HEALTHY.
2. Dừng **dịch vụ ứng dụng trên đúng VM lab**, không dùng lệnh stop Compute Engine VM.
3. Theo dõi thời điểm health state đổi, thời điểm MIG bắt đầu repair, VM mới xuất hiện.
4. Xác minh replacement VM dùng template mong muốn và đạt HEALTHY.
5. Xác minh ứng dụng phục hồi qua LB, không mất dữ liệu quan trọng.
6. Khôi phục toàn bộ lab, tắt/xóa tài nguyên theo quyền sở hữu.

### Phần D — Báo cáo kết quả

| Chỉ số | Cần ghi |
| --- | --- |
| Thời gian tạo VM → probe healthy lần đầu | Đo từ logs/operations |
| Initial delay và lý do | Số đo startup + headroom |
| Ngưỡng/interval/timeout | Cấu hình đã áp dụng |
| Probe ports/source CIDR | Firewall và mô hình truy cập |
| Từ ứng dụng lỗi → unhealthy | Thời gian quan sát |
| Từ unhealthy → repair operation | Thời gian quan sát |
| Từ repair → replacement HEALTHY | Thời gian quan sát |
| Lỗi user-facing khi thử | HTTP errors/latency, nếu có |
| Data loss/duplicate processing | Bằng chứng về idempotency |
| Chi phí phát sinh | VM boot/logs/network, nếu có |
| Vấn đề còn lại | Remediation và người phụ trách |

**Điều kiện đạt:** Người học không chỉ chạy được lệnh; phải giải thích vì sao liveness được chọn, tại sao cần initial delay, vì sao firewall chỉ cho probe ranges và vì sao healthy trong MIG không tự đảm bảo SLO ứng dụng.

## 16. Bài tập tư duy có đáp án

### Bài 1 — Liveness phụ thuộc DB

Ba VM cùng dùng Cloud SQL. Health endpoint trên mỗi VM chạy `SELECT 1`. Cloud SQL gián đoạn 2 phút khiến cả ba health check thất bại. Nên đặt ngưỡng unhealthy 1 và recreate ngay cả ba VM không?

**Gợi ý:** Không. Đây là **shared dependency failure**; recreate thường không làm DB phục hồi. Tách readiness, liveness và monitoring của DB; áp dụng timeout/retry/circuit breaker theo kiến trúc.

### Bài 2 — Ước lượng thời gian

Giả sử `check interval=30s`, `unhealthy threshold=3`, `timeout=10s` và VM đã qua initial delay. Sau một lỗi kéo dài, autohealing có luôn bắt đầu đúng 90s không?

**Gợi ý:** Không. Phụ thuộc lịch probe, kết quả liên tiếp, thời gian timeout/aggregation và MIG controller; chưa kể queue/repair/startup. Tính **khoảng gần đúng**, đo bằng log và đừng hứa thời gian tuyệt đối.

### Bài 3 — Chu kỳ boot

VM mất 240s để khởi động. `initial-delay=60s`, health check trả fail cho tới khi app sẵn sàng. MIG recreate liên tục. Cách sửa?

**Gợi ý:** Đo startup p95/p99, nâng delay trên cơ sở số liệu, bảo đảm endpoint/port đúng và template hợp lệ, quan sát trong do-nothing trước khi bật repair.

### Bài 4 — Tín hiệu trái nhau

Load balancer health check cho VM-A là UNHEALTHY, nhưng MIG autohealing health state là HEALTHY. Có phải chắc chắn cấu hình sai?

**Gợi ý:** Không. LB readiness có thể kiểm tra khả năng nhận request mới, còn MIG liveness kiểm tra lỗi local cần thay VM. Tuy nhiên phải xác minh đây là thiết kế có chủ đích và khách hàng còn đủ capacity.

### Bài 5 — Giới hạn repair

Một zonal MIG có 10 VM, bốn VM unhealthy cùng lúc. Nếu áp giới hạn 30%/zone, MIG có thể cố gắng repair tối đa bao nhiêu VM cùng lúc?

**Gợi ý:** 30% × 10 = **3 VM** (làm tròn lên theo quy tắc; kết quả 3), không nhất thiết cả bốn ngay lập tức. Với MIG vùng có 3 VM trong mỗi zone, tối đa khoảng một VM ở zone đó trong cùng thời điểm theo ví dụ hiện hành.

### Bài 6 — Đường mạng probe

VM có web server cổng 8080 nhưng chỉ bind `127.0.0.1`. `curl localhost:8080` trả 200. Health check của MIG có healthy được không?

**Gợi ý:** Không, nếu Google probes đi đến internal IP mà server không lắng nghe tại đó. Phải sửa listener/binding và kiểm tra firewall, không chỉ sửa threshold.

### Bài 7 — Vì sao stop VM không phải thử application health check?

Người vận hành chạy `gcloud compute instances stop VM_NAME` rồi thấy VM được MIG tạo lại. Điều đó chứng minh application autohealing đã chạy?

**Gợi ý:** Không. MIG repair VM failed/stop ngoài ý muốn có thể hoạt động **không cần** application health check. Muốn thử autohealing, mô phỏng lỗi service trên VM lab và theo dõi health state/repair operation tương ứng.

## 17. Checklist production cho autohealing MIG

- [ ] Phân biệt MIG repair cơ bản với application-based autohealing.
- [ ] Quyết định có cần zonal hay regional MIG, số VM tối thiểu và kiến trúc LB.
- [ ] Instance template có app/agent/startup script có thể dựng lại từ đầu.
- [ ] Dữ liệu/session quan trọng không phụ thuộc ephemeral VM hoặc có stateful policy phù hợp.
- [ ] Health endpoint cho autohealing phản ánh **local failure cần recreate**.
- [ ] LB readiness health check tách riêng nếu cần hành vi nhạy hơn.
- [ ] Health check đủ bảo thủ, ngưỡng failure >1, timeout/interval hợp lý.
- [ ] Initial delay dựa số liệu startup p95/p99; được chỉ định tường minh.
- [ ] VPC firewall cho nguồn probes và port, target tag đúng, không mở rộng không cần thiết.
- [ ] Không có authentication/redirect khiến Google probes thất bại.
- [ ] Đã rollout health check trong chế độ do-nothing và quan sát đủ lâu.
- [ ] Có logs, dashboard, alerts cho health states, repair rate và HTTP errors.
- [ ] Autoscaler/rolling update và chính sách repair không xung đột kỳ vọng.
- [ ] Thử một lỗi instance và kiểm tra traffic khi repair.
- [ ] Có phương án rollback health check/action và xử lý repair storm.
- [ ] IAM, quota, disk, logging, network và chi phí đã được dự trù.
- [ ] Có runbook để phân biệt lỗi một VM, lỗi template và lỗi dependency chung.

## 18. Tham khảo Google Cloud chính thức

Các nguồn sau là tài liệu cập nhật cho MIG autohealing, application health checks và quản lý lifecycle. Khi triển khai thực tế, kiểm tra lại giao diện/CLI và yêu cầu IAM/region/health-check protocol:

- [Set up an application-based health check and autohealing](https://docs.cloud.google.com/compute/docs/instance-groups/autohealing-instances-in-migs) — cách tạo check, firewall, initial delay, policy, health state và điều kiện repair.
- [About repairing VMs for high availability](https://docs.cloud.google.com/compute/docs/instance-groups/about-repair) — phân biệt failed-VM repair và application-based autohealing.
- [Instance groups overview](https://docs.cloud.google.com/compute/docs/instance-groups) — zonal/regional MIG, autoscaling, load balancing và health checking.
- [Monitor managed instance health state changes](https://docs.cloud.google.com/compute/docs/instance-groups/monitoring-managed-instance-health-state-changes) — health state change logs và đo startup.
- [View information about MIGs and instances](https://docs.cloud.google.com/compute/docs/instance-groups/getting-info-about-migs) — list-instances, currentAction, isStable và policies.
- [Turn off repairs in a MIG](https://docs.cloud.google.com/compute/docs/instance-groups/turn-off-vm-repairs-in-mig) — `default-action-on-vm-failure` và `action-on-vm-failed-health-check`.
- [Apply configuration updates during repairs](https://docs.cloud.google.com/compute/docs/instance-groups/update-on-repair) — giữ hoặc cập nhật template/config khi repair.
- [Health checks overview](https://docs.cloud.google.com/load-balancing/docs/health-check-concepts) — protocols, nguồn probes, khác biệt loại load balancer/backend.
- [Firewall rules for Cloud Load Balancing](https://docs.cloud.google.com/load-balancing/docs/firewall-rules) — đường probes và backend theo loại LB.
- [gcloud compute health-checks create http](https://docs.cloud.google.com/sdk/gcloud/reference/compute/health-checks/create/http) — cú pháp cấu hình HTTP health checks.
- [gcloud compute instance-groups managed create](https://docs.cloud.google.com/sdk/gcloud/reference/compute/instance-groups/managed/create) — MIG mới và autohealing policy.
- [gcloud compute instance-groups managed update](https://docs.cloud.google.com/sdk/gcloud/reference/compute/instance-groups/managed/update) — đổi health check/action/initial delay.
- [Autoscaling managed instance groups](https://docs.cloud.google.com/compute/docs/autoscaler) — autoscaling khác với autohealing.
- [High availability architecture on Google Cloud](https://docs.cloud.google.com/architecture/framework/reliability) — thiết kế SLO, HA, redundancy và phục hồi.

**Điểm cần ghi nhớ:** Autohealing chỉ hữu ích khi **health check đo đúng lỗi có thể sửa bằng recreate**. Hãy tách **readiness của load balancer** với **liveness của MIG**, đặt **initial delay** từ số đo startup, dùng **firewall và probe ranges đúng**, quan sát trước trong **do-nothing**, sau đó mới bật repair có kiểm soát. Một MIG tự sửa VM không thay thế HA của database, thiết kế stateless, rollback release và giám sát SLO.

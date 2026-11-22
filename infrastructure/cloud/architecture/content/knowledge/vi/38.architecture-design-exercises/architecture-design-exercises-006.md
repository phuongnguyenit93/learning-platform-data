# Lập phương án phục hồi và diễn tập tình huống mất khu vực

## 1. Bối cảnh và mục tiêu

Khi một máy chủ hoặc một Availability Zone (AZ) gặp sự cố, ứng dụng có thể tiếp tục hoạt động nhờ nhiều replica và failover trong cùng region. Nhưng khi **toàn bộ region** không khả dụng, load balancer, compute, cơ sở dữ liệu, hàng đợi và các endpoint chỉ tồn tại tại region đó đều có thể ngừng phục vụ. Muốn khôi phục, đội kiến trúc phải chuẩn bị **region dự phòng**, dữ liệu có thể phục hồi, đường điều phối độc lập và quy trình chuyển quyền ghi an toàn.

Bài thực hành này thuộc chương **Thực hành thiết kế** của module **CLOUD_ARCHITECTURE**. Người học chuyển yêu cầu nghiệp vụ thành phương án mạng, compute, dữ liệu và triển khai; giải thích đánh đổi về độ tin cậy, bảo mật, khả năng mở rộng, chi phí, vận hành và đánh giá giải pháp theo tinh thần **Well-Architected**.

Kết thúc bài, bạn phải có thể:

1. Phân tích tác động của sự cố mất region theo từng hành trình nghiệp vụ.
2. Đặt mục tiêu **RTO**, **RPO**, độ suy giảm chức năng có thể chấp nhận và tiêu chí kiểm chứng.
3. So sánh backup/restore, pilot light, warm standby và active/active trước khi lựa chọn.
4. Thiết kế hai region với replication, routing, single-writer, IAM, backup, queue và observability.
5. Viết runbook **failover** và **failback**, cùng các điều kiện GO/NO-GO.
6. Tổ chức diễn tập an toàn; đo RTO/RPO, đối soát dữ liệu và chứng minh kết quả.
7. Ghi rủi ro còn lại, người chịu trách nhiệm, hạn xử lý và quyết định kiến trúc.

> Mọi số liệu trong bài là **giả định để thực hành**, không phải cam kết SLA của AWS, Azure hoặc Google Cloud. Trước khi triển khai thật, cần xác minh giới hạn, khả năng replication, quota, hỗ trợ theo region và giá của dịch vụ được chọn.

## 2. Đề bài xuyên suốt: SaaS quản lý công việc

Doanh nghiệp vận hành một SaaS cho phép người dùng đăng nhập, tạo/sửa nhiệm vụ, đính kèm tệp, theo dõi bảng công việc và nhận thông báo.

Kiến trúc hiện tại chỉ ở **region A**:

- DNS/CDN/WAF và HTTPS ingress điều hướng đến ứng dụng API stateless trong container.
- PostgreSQL managed lưu tài khoản, nhóm, nhiệm vụ, phiên bản cập nhật và lịch sử hoạt động.
- Object storage lưu tệp đính kèm; Redis cache hỗ trợ đọc.
- Queue/worker xử lý gửi thông báo, tạo bản xem trước tệp và lập chỉ mục tìm kiếm.
- IAM, KMS, secret manager, giám sát, audit log, CI/CD và hạ tầng khai báo.

Quy mô giả định: 300 request/giây bình thường, 1.200 request/giây lúc cao điểm; PostgreSQL 500 GB, object storage 6 TB. Region B được phép đặt dữ liệu dự phòng theo chính sách của doanh nghiệp.

### Mục tiêu được giả định là đã thống nhất với nghiệp vụ

| Luồng nghiệp vụ | Mục tiêu minh họa | Phạm vi |
| --- | --- | --- |
| Đăng nhập, đọc/cập nhật nhiệm vụ | **RTO ≤ 45 phút** | Từ lúc A ngừng phục vụ đến lúc chức năng cốt lõi ở B hoạt động và được xác minh |
| Dữ liệu nhiệm vụ | **RPO ≤ 5 phút** | Mức tổn thất thời gian dữ liệu tối đa được nghiệp vụ chấp thuận, kèm quy trình xác định và xử lý các thay đổi bị ảnh hưởng |
| Tệp đính kèm | Phải có mục tiêu độ bền được phê duyệt riêng | Không thể suy RPO của object storage từ replication của PostgreSQL |
| Notification, preview, search index | Được phép khôi phục chậm hơn API cốt lõi | Sự kiện không gây tác dụng phụ trùng; backlog có thể xử lý lại |
| Dữ liệu phân tích tái tạo được | RPO có thể dài hơn, ví dụ 24 giờ | Phân biệt dữ liệu gốc và dữ liệu tính toán lại |
| Quyền riêng tư và bảo mật | Không hạ mức bảo vệ ở B | Tuân thủ vùng dữ liệu, quyền tối thiểu, mã hóa và kiểm toán |

**RPO ≤ 5 phút không có nghĩa “không mất bản ghi nào”.** Nếu nghiệp vụ yêu cầu một thao tác đã báo thành công **không bao giờ được mất**, phải đặt RPO phù hợp với yêu cầu đó và chọn cơ chế ghi/nhân bản có thể chứng minh, thay vì dùng replication bất đồng bộ rồi giả định an toàn.

### Failure domain

| Sự cố | Phương án bảo vệ chính | Giới hạn |
| --- | --- | --- |
| Một VM/pod lỗi | Restart, health check, replica | Chưa xử lý lỗi database hoặc vùng |
| Một AZ lỗi | Nhiều AZ, phân tán replica, HA database trong region | Không đủ nếu cả region mất |
| Cả region A lỗi | Dữ liệu/tài nguyên ở B, định tuyến và runbook DR | Phải bảo vệ quyền ghi và dữ liệu không đồng bộ |
| Dịch vụ chung giữa A và B lỗi | Thiết kế giảm phụ thuộc, quyền thao tác độc lập, kế hoạch ứng phó | “Global” không đồng nghĩa không có failure mode |

## 3. Hiểu và tính RTO/RPO đúng cách

### 3.1. RTO: thời gian khôi phục dịch vụ có ích

**Recovery Time Objective** là thời gian mục tiêu để một luồng nghiệp vụ khôi phục trong phạm vi sự cố đã định. Không chỉ tính thời gian bấm nút đổi DNS, vì quá trình còn gồm phát hiện, đánh giá, chặn ghi nguồn cũ, promote dữ liệu, tăng công suất, chuyển định tuyến và xác minh.

~~~text
RTO thực đo = thời gian từ T0 (sự cố bắt đầu)
              đến T7 (luồng cốt lõi tại B đã PASS và mở được cho người dùng)
~~~

Ngân sách minh họa cho RTO 45 phút:

| Bước | Thời gian tối đa | Tích lũy |
| --- | ---: | ---: |
| Phát hiện lỗi và xác minh ảnh hưởng | 5 phút | T+05 |
| Incident commander quyết định kích hoạt DR | 5 phút | T+10 |
| Fencing A, xác minh trạng thái dữ liệu B | 5 phút | T+15 |
| Promote DB B và tăng công suất compute | 12 phút | T+27 |
| Đổi tuyến và kiểm tra kết nối | 7 phút | T+34 |
| Smoke test và mở các chức năng cốt lõi | 8 phút | T+42 |
| Dự phòng trễ | 3 phút | T+45 |

Bảng này là **mục tiêu điều phối**, chưa phải thành tích được chứng minh. Nếu khởi động B mất 18 phút thay vì 12, cần sửa thiết kế hoặc báo RTO không đạt; không được rút bớt kiểm chứng dữ liệu chỉ để kịp thời gian.

### 3.2. RPO: độ cũ tối đa của trạng thái dữ liệu được phục hồi

**Recovery Point Objective** giới hạn mất mát dữ liệu, thường diễn đạt bằng một khoảng thời gian. Bản sao **bất đồng bộ** có thể nhận dữ liệu trễ: một giao dịch commit tại A nhưng chưa apply bền vững tại B khi A biến mất.

Giả sử A ngừng phục vụ lúc **10:00:00**, B đã apply dữ liệu nhất quán đến mốc tương ứng **09:57:30**: độ lệch là **2 phút 30 giây**, nằm trong ngưỡng 5 phút nếu bằng chứng đúng. Tuy nhiên so timestamp hai máy **không chứng minh** tất cả giao dịch trước mốc đều đã apply; cần kiểm tra **log position/transaction sequence**, tình trạng apply và các giao dịch lỗi hoặc thiếu.

Phải ghi rõ:

- Mốc cuối đã **commit bền vững** ở A, nếu có thể quan sát.
- Mốc cuối đã **apply bền vững** tại B.
- Recovery point được chọn để mở B và tập dữ liệu liên quan.
- Tập ID thao tác đã được client xác nhận thành công gần sự cố.
- Tập ID/phiên bản và tệp thực sự được phục hồi ở B.
- Các sai lệch, biện pháp khắc phục và người có quyền chấp nhận tổn thất.

### 3.3. RTO, RPO và SLA không thay thế nhau

Dịch vụ phục hồi sau 20 phút có thể **đạt RTO** nhưng **trượt RPO** nếu mất 12 phút dữ liệu. Tương tự, DB đã bắt kịp replication nhưng API vẫn lỗi do thiếu secret hoặc cấu hình network, vậy **chưa đạt RTO**. SLA của một dịch vụ cloud riêng lẻ cũng không tự động chứng minh SLO đầu-cuối của SaaS.

## 4. Chọn phương án DR và giải thích đánh đổi

| Chiến lược | Region B trước sự cố | Thế mạnh | Rủi ro/chi phí |
| --- | --- | --- | --- |
| **Backup and restore** | Backup và IaC sẵn có, phần lớn ứng dụng chưa chạy | Chi phí vận hành dự phòng thấp | Restore khối dữ liệu lớn có thể kéo dài; RPO do chu kỳ backup quyết định |
| **Pilot light** | Giữ các thành phần dữ liệu/tối thiểu, compute bật hoặc scale sau lỗi | Ít tốn compute hơn warm standby | Thời gian triển khai/scale có thể vượt RTO |
| **Warm standby** | B chạy sẵn với công suất thấp, có DB replica và endpoint có thể kiểm tra | Có thể chuyển nhanh hơn nếu scale và replication đủ tốt | Trả phí chạy song song, cần bảo vệ consistency/failback |
| **Active/active** | A và B phục vụ bình thường | Có thể giảm thời gian đổi tuyến | Khó giải quyết writer ownership, xung đột, latency, quan hệ dữ liệu và chi phí |

**Phương án tham chiếu cho bài này:** *warm standby tại B*, vì doanh nghiệp cần khôi phục API trong 45 phút và có thể đầu tư chạy một phần compute/dữ liệu tại B. Quyết định chỉ được coi là có hiệu lực khi diễn tập chứng minh được thời gian khôi phục, độ trễ replication, khả năng scale và xử lý dữ liệu thiếu.

Không có chiến lược nào tự động bảo đảm RPO = 0 hoặc RTO dưới vài phút. Thậm chí active/active có thể bị **split-brain** nếu hai cơ sở dữ liệu độc lập cùng nhận ghi.

## 5. Sơ đồ kiến trúc DR tham chiếu

~~~mermaid
flowchart TB
    U[Người dùng và API client] --> G[Global DNS / traffic manager / CDN]
    G -->|Bình thường| IA[Ingress A]
    G -. Khi DR .-> IB[Ingress B]
    subgraph A[Region A - primary]
      IA --> AA[API containers A]
      AA --> PA[(PostgreSQL primary)]
      AA --> OA[(Object storage A)]
      PA --> XA[(Transactional outbox)]
      XA --> QA[Queue / worker A]
    end
    subgraph B[Region B - warm standby]
      IB --> AB[API containers B]
      AB --> PB[(PostgreSQL standby)]
      AB --> OB[(Object storage B)]
      AB --> QB[Queue / worker B]
    end
    PA -->|Async log replication| PB
    OA -->|Cross-region object replication| OB
    XA -. Replay theo mốc / ID .-> QB
    DR[DR control + observability độc lập với A] --> IB
    DR --> PB
    BK[Backup độc lập và đã thử restore] -. Khôi phục khi cần .-> PB
~~~

Mũi tên chỉ **vai trò logic**; cơ chế sản phẩm thực tế phải được xác minh theo hãng/cloud service. Dữ liệu outbox trên hình tượng trưng cho các bản ghi thường được ghi **trong cùng transaction và database với dữ liệu nghiệp vụ**, không phải một database riêng mặc định.

### Thành phần nào phải chuẩn bị ở B?

| Thành phần | Chuẩn bị | Kiểm chứng bắt buộc |
| --- | --- | --- |
| DNS/traffic manager/ingress | Cổng vào B, health check, TLS, WAF, routes | Quy trình chuyển tuyến, cache DNS/connection cũ, request tới origin |
| Compute/container | Image và version tương thích, autoscaling, quota, IAM | Tăng từ standby tới tải lõi trong ngân sách thời gian |
| PostgreSQL | Standby nhất quán, log replication, backup/PITR, quyền DB | Apply position, promote, đọc/ghi, schema, RTO/RPO |
| Object storage | Bản sao và lifecycle ở B, mã hóa, tệp metadata | Checksum, link từ DB, quyền đọc và độ trễ nhân bản |
| Queue/event | Outbox, cơ chế replay, DLQ, idempotency, worker B | Không mất event, không xử lý tác dụng phụ trùng |
| Cache/search | Dữ liệu tái tạo được, chỉ số ưu tiên | Cache warm-up, backpressure, thời gian rebuild |
| IAM/KMS/secrets | Workload identity và khóa hợp lệ ở B | Có thể xác thực và giải mã dù A không truy cập |
| CI/CD, IaC, registry | Artifact, state, pipeline và quyền thao tác độc lập | Có thể scale/triển khai B khi A mất |
| Metrics/logs/audit | Dashboard và hệ thống cảnh báo không phụ thuộc A | Quan sát từ ngoài A, lưu bằng chứng và liên lạc |

### Điểm then chốt: một nguồn ghi duy nhất

Trong mọi giai đoạn, **cùng một tập dữ liệu chỉ có một nguồn ghi có thẩm quyền**. Khi chuyển A → B, phải có cách chứng minh đường ghi cũ đã bị chặn (**write fencing**) trước khi B được mở cho ghi, hoặc có cơ chế cấp quyền lãnh đạo đáp ứng cùng điều kiện an toàn.

Chỉ thay DNS **không chặn được** ứng dụng cũ và worker còn chạy. Khi có phân chia mạng, một số client có thể kết nối A trong khi nhóm khác kết nối B. Nếu hai database độc lập cùng nhận ghi, trạng thái sẽ phân kỳ.

Cơ chế cụ thể tùy hệ thống: leader election có fencing token, quyền ghi ở lớp dữ liệu, lease được kiểm chứng, cô lập writer bởi control plane còn hoạt động hoặc phương thức failover do database hỗ trợ. Nếu không xác minh được quyền ghi, hướng an toàn là **chưa mở ghi tại B**, ghi nhận sự cố và kích hoạt quy trình ứng phó tương ứng.

## 6. Các quyết định kiến trúc cần ghi thành ADR

Trước khi diễn tập, cần tạo **Architecture Decision Record (ADR)** cho:

1. **Chọn warm standby** thay vì backup/restore, pilot light hay active/active, kèm lý do RTO/RPO và ước tính chi phí.
2. **Replication PostgreSQL**: bất đồng bộ hay đồng bộ, cách đo lag và chốt recovery point.
3. **Fencing và promote:** ai được nâng B thành primary, điều kiện kiểm chứng, cách chống split-brain khi A mất liên lạc.
4. **Xử lý object:** khi nào tệp được báo upload thành công; mức durability, replication/đối soát checksum.
5. **Queue và outbox:** event có thể gửi lặp; consumer phải xử lý idempotently; ai theo dõi DLQ.
6. **DR traffic routing:** DNS TTL/health check, khả năng client giữ kết nối cũ, cách vô hiệu tuyến A.
7. **Vận hành và quyền:** break-glass IAM, KMS ở B, audit, secrets và tác động data residency.
8. **Failback:** phương án re-seed A từ B hoặc đồng bộ ngược, không tự gộp hai DB đã phân kỳ.

Mỗi ADR tối thiểu ghi bối cảnh, phương án, quyết định, rủi ro chấp nhận, bằng chứng thử nghiệm và mốc xem lại.

## 7. Tài liệu đầu vào và phân công vai trò

| Tài liệu | Nội dung tối thiểu | Owner gợi ý |
| --- | --- | --- |
| **BIA (Business Impact Analysis)** | Hành trình nghiệp vụ, tác động downtime, RTO/RPO, mức dữ liệu có thể mất | Chủ nghiệp vụ |
| **Dependency map** | Các dịch vụ regional/global, đối tác, luồng ghi, queue, tệp, IAM | Kiến trúc sư |
| **DR diagram** | A/B, topology mạng, replication, backup, nguồn ghi, trust boundary | Kiến trúc sư/SRE |
| **Runbook failover/failback** | Các bước, timeout, gate, quyền, nhánh lỗi | SRE/DBA |
| **Test plan** | Cách mô phỏng region loss, data mồi, metrics, rollback test | QA/SRE |
| **Risk register** | Vấn đề, mức nghiêm trọng, owner, deadline, chấp thuận rủi ro | Chủ hệ thống |
| **Cost model** | Compute B, replication, egress, backup, log, kịch bản chạy B lâu ngày | FinOps |

**Incident commander (IC)** điều hành sự cố và quyết định chuyển đổi theo thẩm quyền; **DBA** xác minh mốc dữ liệu và quyền ghi; **SRE/platform** phụ trách định tuyến/compute/giám sát; **application lead** kiểm tra nghiệp vụ/worker; **security lead** đảm bảo bảo mật và compliance; **business owner** quyết định mức tổn thất dữ liệu có thể chấp nhận.

Không nên giao quyền duyệt mất dữ liệu cho người chỉ vận hành hạ tầng nếu tổn thất ảnh hưởng cam kết nghiệp vụ.

## 8. Gate GO/NO-GO trước khi kích hoạt

| Gate | Điều kiện GO | Điều kiện NO-GO |
| --- | --- | --- |
| Phạm vi | Người tham gia, môi trường, tenant và thời điểm thử đã thống nhất | Có nguy cơ tác động dữ liệu/người dùng ngoài phạm vi |
| Dữ liệu | B có mốc replication/apply nhất quán; biết cách tính RPO | Lag chưa biết, lỗi apply hoặc thiếu log kiểm chứng |
| Single-writer | Có cơ chế fencing A và trình tự promote B đã diễn tập | Chỉ định đổi DNS, không kiểm soát writer còn chạy |
| Bảo mật | IAM, KMS, secrets, certificates, data residency đúng tại B | Không thể giải mã, quyền quá rộng, vùng dữ liệu không được phép |
| Năng lực | B có quota và khả năng scale cho luồng thiết yếu | Không đủ tài nguyên, chưa thử kết nối DB ở tải đích |
| Observability | Có metric, log, alert, liên lạc độc lập ngoài A | Không đo được thời gian, dữ liệu hoặc chất lượng dịch vụ |
| Phục hồi sai thao tác | Backup độc lập đã thử restore, có phương án dừng | Không biết xử lý nếu promote/route lỗi |
| Failback | Có cách mang dữ liệu mới từ B về A | Dự định đưa DNS về A ngay khi A “sống lại” |

Bảng này hỗ trợ ra quyết định. Trong tai họa thật, không phải gate nào cũng đầy đủ thông tin; người có thẩm quyền phải ghi **giả định và rủi ro** khi chọn chuyển. Riêng điều kiện an toàn dữ liệu không được coi là đạt chỉ vì thiếu tín hiệu lỗi.

## 9. Runbook failover: A → B

### Pha A — Phát hiện và kích hoạt

1. Ghi **T0** từ thời điểm A ngừng phục vụ theo kịch bản. Dùng synthetic probe từ B/ngoài A và dashboard độc lập để phân biệt region outage với mất mạng của một người vận hành.
2. Kiểm tra trạng thái các luồng nghiệp vụ, dependencies và khả năng A phục hồi trong thời gian còn lại.
3. IC gọi đúng nhóm trực, xác nhận quyền thực hiện và ra quyết định **GO DR / HOLD / NO-GO**; ghi thời điểm T2 và lý do.

### Pha B — Xác minh quyền ghi và chọn mốc dữ liệu

4. Chặn hoặc fence đường ghi vào A ở các lớp có thể bảo đảm: API, DB, worker, scheduler, webhook. Nếu A không thể truy cập, sử dụng giao thức failover chống hai leader đã được thiết kế từ trước, không suy diễn từ việc A không phản hồi ping.
5. DBA chốt **recovery point W** dựa trên log/transaction sequence đã apply bền vững tại B. Ghi replication lag, lỗi apply, giao dịch chưa đến, checksum nếu có.
6. Kiểm tra RPO cho các dataset; nếu vượt mục tiêu, IC và business owner quyết định xử lý theo chính sách. Không tuyên bố “đã đạt” khi nguồn xác nhận không thể đối soát.

### Pha C — Chuyển dữ liệu và dịch vụ

7. Promote PostgreSQL B theo quy trình do công nghệ hỗ trợ; xác nhận schema, sequence, ứng dụng đọc/ghi và quyền truy cập.
8. Scale compute B; kiểm tra quota, connection pool, autoscaling signal, health check ứng dụng và dịch vụ phụ thuộc.
9. Kích hoạt worker B từ mốc outbox/event phù hợp. Dùng idempotency key và DLQ để xử lý retry/replay, không kích hoạt song song hai scheduler tạo tác dụng phụ.
10. Xác minh object storage B: checksum, metadata, link đến task và quyền giải mã. Khi tệp chưa sao chép, áp dụng chính sách khôi phục/tạm ẩn/đề nghị upload lại đã được nghiệp vụ duyệt.

### Pha D — Chuyển tuyến, mở dịch vụ và theo dõi

11. Chuyển traffic manager/ingress đến B. Kiểm tra TLS, WAF, DNS cache, truy cập từ bên ngoài và dấu hiệu request tiếp tục tới A.
12. Chạy synthetic transactions gồm đăng nhập, đọc và sửa task, upload/download tệp thử, đẩy event và quan sát worker. Đối chiếu request ID, trạng thái DB và tác dụng phụ; HTTP 200 không tự chứng minh giao dịch đúng.
13. Mở lưu lượng có kiểm soát, đo tỷ lệ lỗi, p95/p99, DB saturation, queue backlog và kết nối đối tác. Nếu thiếu capacity, kích hoạt chế độ suy giảm chức năng đã được duyệt.
14. IC xác nhận **T7**, tính RTO = T7 − T0 và ghi đánh giá RPO, sai lệch, chức năng còn hạn chế, người xử lý và tình trạng thông báo.

### Bảng mốc minh họa

| Mốc | Trách nhiệm chính | Bằng chứng cần lưu |
| --- | --- | --- |
| T+05 | SRE xác nhận mất region | Probe ngoài A, telemetry, bắt đầu incident |
| T+10 | IC kích hoạt DR | Quyết định và người duyệt |
| T+15 | DBA/SRE hoàn tất fencing, mốc W | Fencing state, replication/apply position |
| T+27 | DBA và platform đưa B sẵn sàng | DB writable, compute healthy, queue checks |
| T+34 | Network lead chuyển ingress | Kiểm thử DNS/TLS/route |
| T+42 | App lead hoàn tất smoke tests | Kết quả end-to-end, test data, metrics |
| T+45 | IC chốt đánh giá RTO | Timeline thực đo, trạng thái phục hồi |

Nếu smoke test lỗi ở T+42, vẫn phải **giữ an toàn dữ liệu**, báo chưa đạt RTO và xử lý sự cố. Không nên mở ghi sai chỉ để giữ một con số trên báo cáo.

## 10. Thiết kế diễn tập mất region

### 10.1. Cấp độ diễn tập

| Cấp độ | Thực hiện | Ý nghĩa |
| --- | --- | --- |
| **Tabletop** | Mỗi vai trò giải quyết câu hỏi và decision gate trên giấy | Tìm lỗ hổng quy trình, quyền, liên lạc |
| **Component drill** | Test restore, promote DB, start worker, đổi route trong môi trường thử | Kiểm tra từng kỹ thuật riêng lẻ |
| **End-to-end staging** | Mô phỏng mất A trong môi trường hai region, chuyển B | Kiểm tra chuỗi thao tác và phép đo thực |
| **Game day có phạm vi** | Diễn tập với workload/tenant được phê duyệt | Quan sát gần điều kiện thực, rủi ro có kiểm soát |
| **Full DR drill** | Chuyển vùng diện rộng theo change plan có quyền phê duyệt | Đo năng lực vận hành thực tế và cả failback |

Bắt đầu bằng tabletop và staging, rồi nâng dần độ sát thực khi bằng chứng đủ mạnh. Đừng tắt vùng production thật khi chưa có phạm vi, chủ sở hữu dữ liệu, thời điểm và quyền phê duyệt.

### 10.2. Bộ dữ liệu mồi

Trong staging, chuẩn bị:

- 10.000 task trên nhiều tenant, có **task ID** và **version** tăng mỗi lần sửa.
- 500 thao tác ghi gần thời điểm sự cố; client giữ danh sách request ID và những lần đã nhận ACK.
- 100 object đính kèm và checksum độc lập.
- 200 event outbox; tạo backlog để kiểm thử replay và dedup.
- Bộ request âm tính: một tenant cố đọc/sửa task của tenant khác.
- Bộ phát tải có thể tăng từ 300 lên 1.200 request/giây và ghi latency/error từ góc nhìn client.

Không dùng dữ liệu nhạy cảm thật ngoài phạm vi cho phép. Dataset cần đủ đại diện về kích thước, tỷ lệ đọc/ghi và quan hệ dữ liệu để phát hiện lỗi trong quá trình khôi phục.

### 10.3. Kịch bản phải thử

**Kịch bản 1 — A biến mất hoàn toàn.** Ngắt tuyến ứng dụng và dịch vụ A trong môi trường thử. Đội điều hành chuyển sang B theo runbook; đo T0→T7, RPO, tập task/version, object checksum, quyền truy cập và backlog.

**Kịch bản 2 — Network partition.** Một số client vẫn gọi được A, còn IC thấy A mất kết nối. Mục tiêu là chứng minh không thể tồn tại hai nguồn ghi đồng thời. Nếu fencing chưa chắc chắn, hệ thống phải **fail closed** cho thao tác ghi, thay vì mở B một cách mù quáng.

**Kịch bản 3 — Lag vượt RPO.** Tạo replication lag 7 phút ngay trước sự cố với RPO mục tiêu 5 phút. Kết quả đúng phải là **RPO FAIL/NO-GO hoặc quyết định ngoại lệ của người có thẩm quyền theo chính sách**, không “làm tròn” 7 thành 5.

**Kịch bản 4 — B thiếu công suất.** Chuyển sang B với mức compute thấp, tăng tải theo bước. Đo thời gian scale, connection pool, CPU/memory, IOPS, p95, error rate và tuổi queue. Kiểm tra chế độ giảm chức năng có bảo vệ luồng cốt lõi.

**Kịch bản 5 — Event bị phát lại.** Cho publisher/consumer nhận lại cùng event sau sự cố. Kiểm tra không tạo thông báo trùng nhờ event ID, idempotency, DLQ và trạng thái đã xử lý.

**Kịch bản 6 — KMS/secret ở B lỗi.** Gỡ một quyền trong staging để thấy ứng dụng phản ứng thế nào; kiểm tra alert, runbook và khả năng sửa mà không dựa vào region A.

### 10.4. Tiêu chí dừng diễn tập

Dừng hoặc thu hẹp phạm vi nếu thấy quyền ghi đồng thời chưa được ngăn, tệp/dữ liệu nhạy cảm bị lộ, dữ liệu bên ngoài môi trường thử bị ảnh hưởng, hoặc thiếu khả năng quan sát. Điều phối viên phải ghi thời điểm dừng, bảo toàn log và chỉ tiếp tục sau khi lỗi được sửa và được phê duyệt.

## 11. Đối soát dữ liệu để chứng minh RPO

Đừng chỉ so số hàng giữa A và B. Hai tập có cùng số lượng vẫn có thể thiếu một task và thừa một task, hoặc cùng ID nhưng khác phiên bản.

Chốt mốc so sánh:

- **W_A:** mốc commit bền vững cuối có thể biết tại A (nếu còn truy cập).
- **W_B:** mốc apply bền vững cuối tại B trước promote.
- **W:** recovery point được chọn cho quá trình phục hồi.
- **ACK set:** các request ID mà client đã nhận xác nhận thành công.
- **Recovered set:** các task/version, object và event thực sự có ở B.

Khi A không truy cập được, có thể không có W_A đáng tin. Lúc đó đối chiếu **ACK set**, log ngoài A và mốc giao dịch được chứng minh để ước lượng những gì không đến B, ghi rõ độ bất định; không tự nhận “không mất dữ liệu”.

| Lớp đối soát | Phép kiểm tra | Lý do |
| --- | --- | --- |
| Khóa | ID task đã xác nhận có ở B không | Phát hiện thiếu/dư dù tổng số dòng bằng nhau |
| Nội dung | version, owner, status, updated fields | Phát hiện bản ghi cũ hoặc sai |
| Tham chiếu | task–project–tenant–attachment | Tránh orphan hoặc đọc sai tenant |
| Object | hash/checksum, kích thước, quyền giải mã | Metadata có thể tới B nhưng tệp chưa |
| Event | ID, trạng thái outbox, DLQ, side effect | Phát hiện thiếu/nhân đôi notification |
| Tổng hợp | Đếm theo tenant/ngày/trạng thái | Tìm nhanh vùng dữ liệu có nguy cơ |

Ví dụ truy vấn trên cùng tập dữ liệu tại mốc nhất quán:

~~~sql
SELECT tenant_id, status,
       COUNT(*) AS task_count,
       MAX(version) AS highest_version
FROM tasks
GROUP BY tenant_id, status
ORDER BY tenant_id, status;
~~~

Đây là **phép sàng lọc**, không chứng minh từng bản ghi đúng. Tiếp tục so ID/version ở các nhóm có sai lệch và các giao dịch gần W. Phải đo số lượng sai lệch, tính nghiêm trọng, cách xử lý, owner và trạng thái sau khắc phục.

### Phiếu kết quả RPO

~~~text
Failure time T0:
DB apply/log position tại B:
Recovery point W:
ACK set còn thiếu hoặc có version cũ:
Độ trễ RPO đo được và độ bất định:
Số task/version cần khắc phục:
Số object chưa đồng bộ / checksum sai:
Event thiếu / bị gửi trùng:
Người chấp thuận tác động nghiệp vụ:
Quyết định PASS / FAIL / NOT_VERIFIED:
~~~

Nếu RPO thực đo 6 phút với mục tiêu 5 phút, kết luận **FAIL** dù ứng dụng đã phục vụ sau 25 phút. Nếu không có bằng chứng về mốc dữ liệu, kết luận **NOT_VERIFIED**.

## 12. Failback: đưa hệ thống trở lại A

Sau khi failover, region B là nơi nhận ghi. Nếu A quay lại, dữ liệu ở A đã lạc hậu. **Failback không chỉ là đảo DNS**: cần chuyển lại nguồn dữ liệu có thẩm quyền một cách có kiểm soát.

Quy trình:

1. Giữ **B là primary duy nhất**; A hoạt động lại trong chế độ cách ly/read-only.
2. Điều tra nguyên nhân sự cố, kiểm tra xem A có thể đã nhận những ghi độc lập do split-brain không.
3. Dùng **re-seed A từ trạng thái B** hoặc reverse replication được công nghệ hỗ trợ và đã diễn tập; không merge hai primary tự phát.
4. Chốt mốc đồng bộ mới **W2**, đối soát toàn bộ task, object, outbox và các thao tác đã được B xác nhận.
5. Chọn cửa sổ failback và chặn/fence ghi tại B. Đợi A đã apply bền vững tới W2.
6. Chuyển quyền ghi sang A, đổi route, chạy smoke test và theo dõi. Worker chỉ chạy ở nơi có quyền xử lý tương ứng.
7. Đưa B về chế độ standby, kiểm tra replication/backup hướng mới, quyền IAM, quota và runbook.

Nếu A không thể nhận dữ liệu mới an toàn, phương án đúng có thể là **tiếp tục dùng B làm primary lâu dài** đến khi xây dựng lại A.

| Trạng thái | Quyết định an toàn |
| --- | --- |
| Chưa có ghi mới ở B | Có thể quay về A sau khi xác minh trạng thái A còn thẩm quyền |
| B đã nhận 500 cập nhật mới | Không trỏ về A trực tiếp; phải chuyển đủ 500 cập nhật và đối soát |
| A và B đều đã ghi | Dừng ghi, giữ bằng chứng, xử lý split-brain theo quyết định nghiệp vụ và kỹ thuật |

## 13. Đánh giá theo Well-Architected

| Trụ cột | Câu hỏi đối với phương án DR | Bằng chứng cần có |
| --- | --- | --- |
| **Operational Excellence** | Ai kích hoạt DR, ai trực, ai dừng, quy trình có được diễn tập không? | Runbook phiên bản hóa, timeline, incident record, postmortem |
| **Security** | B có IAM/KMS, dữ liệu đúng vùng, TLS, audit và quyền tối thiểu không? | Security tests, config review, data residency approval |
| **Reliability** | Có chứng minh RTO/RPO, single-writer, replication và khả năng restore không? | Fault injection, failover/failback, đối soát ID và log position |
| **Performance Efficiency** | B phục vụ được tải đỉnh hoặc degraded mode đã duyệt không? | Load test, p95/p99, DB connections, queue backlog |
| **Cost Optimization** | Phí standby, replication, backup, logs, egress và diễn tập có hợp lý không? | TCO hai region, chi phí lúc chuyển vùng, quota và utilization |
| **Sustainability** | Có thể giảm tài nguyên nhàn rỗi mà vẫn giữ RTO/RPO không? | Quy tắc scale/right-sizing và kết quả diễn tập sau điều chỉnh |

Warm standby chạy ít compute thường rẻ hơn active/active nhưng phải chứng minh **thời gian tăng năng lực** đủ nhanh. Sao chép dữ liệu tới B và giữ backup lâu tăng chi phí nhưng giúp giảm rủi ro mất vùng hoặc xóa nhầm. Không tối ưu một trụ cột mà bỏ qua ràng buộc bắt buộc của trụ cột khác.

### Cần dự toán những khoản nào?

- Compute/managed DB ở B, HA trong region, cấu hình dự phòng và reserved capacity nếu dùng.
- Cross-region data transfer, replication log, object copy, backup độc lập và restore test.
- Load balancer/CDN/DNS, NAT, private connectivity, endpoints, egress.
- Metrics, log retention, tracing, KMS requests, audit và security tooling.
- Đội on-call, chuẩn bị/diễn tập, vận hành nhiều ngày tại B và đồng bộ ngược về A.

Đừng chỉ tính hóa đơn lúc hệ thống khỏe mạnh. Một lần failover thực sự có thể đòi hỏi cả A và B chạy song song để đối soát trước khi decommission hoặc failback.

## 14. Mẫu DR plan và báo cáo diễn tập

### 14.1. Manifest mục tiêu (minh họa, không phải cấu hình deploy)

~~~yaml
system: task-management-saas
primary_region: region-A
standby_region: region-B
strategy: warm-standby
critical_journeys:
  - name: "Đăng nhập, đọc và cập nhật task"
    rto_minutes: 45
    rpo_minutes: 5
    degraded_mode: "Có thể trì hoãn search và notification"
  - name: "Tệp đính kèm"
    rto_minutes: 45
    rpo_minutes: null
    note: "Cần phê duyệt chính sách độ bền riêng"
write_authority:
  before_dr: "PostgreSQL A"
  after_dr: "PostgreSQL B chỉ khi fencing A hoàn tất"
replication:
  database: "Async log replication, kiểm tra apply position"
  objects: "Cross-region replication + checksum"
  events: "Outbox + idempotent replay"
decision_roles:
  activate_dr: "Incident commander"
  accept_data_loss: "Business owner theo chính sách"
required_evidence:
  - "Timeline RTO"
  - "Watermark và đối soát RPO"
  - "Security / load / smoke tests"
  - "Failback và re-seed validation"
~~~

Giá trị RPO tệp là **null** vì chưa được chốt; đây là **mục chưa hoàn thành**, không có nghĩa được miễn yêu cầu. Một DR plan thực tế không nên được duyệt khi vấn đề quan trọng này chưa có chủ quyết định.

### 14.2. Phiếu kết quả buổi diễn tập

~~~text
Drill ID, ngày/giờ, múi giờ:
Môi trường / dataset / phạm vi:
Người tham gia, incident commander, business owner:
Kịch bản sự cố:
Mục tiêu RTO, RPO theo loại dữ liệu:
T0 - mất A:
T1 - alert:
T2 - quyết định DR:
T3 - fencing và chọn W:
T4 - DB B writable / compute B ready:
T5 - routing sang B:
T6 - smoke tests PASS:
T7 - mở chức năng cốt lõi:
RTO thực đo = T7 - T0:
Mốc recovery W và DB apply position:
RPO thực đo / điều chưa kiểm chứng:
Task ID/version missing hoặc stale:
Object checksum mismatch:
Event thiếu/trùng, DLQ/backlog:
p95/p99, error rate, DB utilization tại B:
Kiểm thử quyền và mã hóa ở B:
Chi phí phát sinh, thời gian failback:
Kết luận PASS / PARTIAL / FAIL / NOT_VERIFIED:
Rủi ro, owner, hạn xử lý:
Người phê duyệt kết luận:
~~~

### 14.3. Tiêu chí PASS tổng thể

Diễn tập được coi là đạt **trong phạm vi đã thử** khi RTO và RPO đều được chứng minh đúng mục tiêu, không có writer đồng thời, giao dịch được đối soát theo mốc, các quyền bảo mật còn đúng, luồng nghiệp vụ cốt lõi hoạt động dưới tải đã định, queue không tạo tác dụng phụ trùng và đội vận hành có thể xử lý failback.

**Nếu thiếu bằng chứng quan trọng, ghi NOT_VERIFIED**, không lấy trạng thái “endpoint HTTP 200” làm bằng chứng toàn hệ thống. Diễn tập staging cũng phải ghi chênh lệch so với production về dataset, traffic, quota, region và tích hợp.

## 15. Ví dụ đọc kết quả và tìm blocker

Giả sử diễn tập staging thu được:

| Kiểm chứng | Mục tiêu | Kết quả | Kết luận |
| --- | --- | --- | --- |
| RTO API cốt lõi | ≤ 45 phút | 38 phút T0→T7 | PASS trong phạm vi thử |
| RPO task | ≤ 5 phút | 3 phút 20 giây theo log apply | PASS nếu đối soát ID/phiên bản chứng thực |
| ACK giao dịch | Có danh sách tổn thất được phép và phương án xử lý | 17 cập nhật đã ACK chưa tới B | Cần phân tích liệu đúng hợp đồng RPO đã công bố |
| Object storage | Đạt cam kết độ bền tệp | 2 metadata đã có nhưng tệp chưa tới B | FAIL nếu đã báo tải lên thành công và cam kết không mất |
| Event side effect | Không gửi thông báo lặp | 4 sự kiện được gửi lặp hai lần | FAIL về idempotency |
| Bảo mật | Tenant isolation | Đọc chéo tenant bị từ chối | PASS cho bài test này |
| Khả năng tải | 1.200 req/s | Chỉ thử 600 req/s | NOT_VERIFIED |

Không kết luận **PASS tổng thể** chỉ nhờ RTO/RPO đạt về số học. Tệp thiếu, event trùng và tải đỉnh chưa được chứng minh có thể tạo vấn đề nghiêm trọng. Nếu yêu cầu nghiệp vụ là mọi thao tác đã xác nhận phải không mất dữ liệu, cả 17 ACK chưa tới B cũng là blocker, kể cả khoảng thời gian nằm trong 5 phút. Hợp đồng với người dùng và chính sách mất dữ liệu phải thống nhất.

## 16. Bài thực hành độc lập

Một ứng dụng **đặt lịch khám** chạy ở region A với API, PostgreSQL, Redis, object storage hồ sơ, queue gửi email/SMS và nhà cung cấp xác thực ngoài. Có khoảng 20.000 lịch hẹn/ngày; mức đỉnh gấp 5 bình thường. Ban điều hành yêu cầu:

- Xem và tạo lịch hẹn phục hồi trong **30 phút** sau mất region.
- **Lịch đã xác nhận thành công không được biến mất** sau failover.
- Email/SMS có thể trễ 2 giờ nhưng không được gửi trùng.
- Hồ sơ nhạy cảm chỉ nằm ở region được phê duyệt; mã hóa và kiểm toán phải tiếp tục.
- B có đủ năng lực tiếp nhận tải đỉnh.

Hãy thực hiện các nhiệm vụ sau:

1. **BIA và RTO/RPO.** Tạo ma trận theo luồng: đăng nhập, đọc/tạo lịch, hồ sơ và notification. Đặt ngưỡng, chính sách xác nhận thành công, khả năng suy giảm, chủ sở hữu. Giải thích vì sao async replication đơn thuần chưa đủ để chứng minh không mất lịch đã xác nhận.
2. **Kiến trúc hai region.** Vẽ DNS/ingress, compute, database, object, queue/outbox, IAM/KMS, backup, observability. Chọn backup/restore, pilot light, warm standby, active/active hoặc kết hợp; bảo vệ quyết định dựa trên RTO/RPO và chi phí.
3. **Quyền ghi và dữ liệu.** Mô tả cách B nhận quyền ghi sau fencing; khi nào API trả thành công cho lịch hẹn; ứng xử khi network partition; cách xử lý object chưa nhân bản.
4. **Runbook.** Viết ít nhất 10 bước, mỗi bước có vai trò, thời gian tối đa, thao tác, bằng chứng và điều kiện NO-GO. Tính xem có thật sự đáp ứng 30 phút hay không.
5. **Diễn tập.** Đưa ra ít nhất ba kịch bản: mất A hoàn toàn, A/B partition, replication lag + backlog; ghi cách giả lập an toàn, metric, dữ liệu đối soát và tiêu chí PASS/FAIL.
6. **Failback.** Giả sử B đã tạo **500 lịch hẹn mới**. Thiết kế re-seed/reverse replication, mốc W2, write fencing, đối soát và điều kiện chuyển quyền ghi về A.
7. **Well-Architected và ADR.** Phân tích Operational Excellence, Security, Reliability, Performance Efficiency, Cost Optimization và Sustainability. Viết ADR mô tả quyết định DR, phương án bị loại, rủi ro còn lại và hạn đánh giá lại.

**Sản phẩm nộp:** sơ đồ kiến trúc, BIA/RTO/RPO matrix, ADR, runbook failover/failback, kế hoạch diễn tập, bảng kết quả kiểm chứng và risk register có người chịu trách nhiệm.

### Tiêu chí tự đánh giá

Bài làm tốt phải nêu rõ **mốc thời gian** đo RTO, **mốc giao dịch và tập ID** đo RPO, cơ chế giữ **một writer**, hành vi khi mất vùng so với partition, cách xử lý tệp/queue/side effect, quyền truy cập ở vùng dự phòng, chi phí chạy song song và điều kiện failback. Mọi kết luận PASS cần bằng chứng phù hợp; phần chưa kiểm chứng phải ghi nhận là **NOT_VERIFIED**, không được suy đoán.

## 17. Phương pháp cần ghi nhớ

Thiết kế DR hiệu quả đi từ **tác động nghiệp vụ → RTO/RPO → topology hai region và dữ liệu → cơ chế quyền ghi → runbook → diễn tập → đối soát → cải tiến**. Có hai region, một database replica và một nút chuyển DNS chưa đủ để kết luận sẵn sàng phục hồi.

Câu hỏi cuối cùng của buổi review là: **Khi region A mất đúng giờ cao điểm, ai quyết định chuyển, chuyển trong bao lâu, dữ liệu nào có nguy cơ mất, bằng chứng nào cho thấy B phục vụ đúng, và làm cách nào quay về trạng thái bình thường mà không làm mất thêm dữ liệu?**

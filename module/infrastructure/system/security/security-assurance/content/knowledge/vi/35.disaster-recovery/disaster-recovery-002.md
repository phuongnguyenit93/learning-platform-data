# DR architecture: Thiết kế kiến trúc khôi phục sau thảm họa có thể kiểm chứng

## Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích **disaster recovery (DR) architecture** và phân biệt DR với high availability, backup, business continuity và incident response.
2. Chuyển yêu cầu kinh doanh và phân tích tác động (**BIA**) thành mục tiêu **RTO, RPO**, phạm vi dịch vụ, phụ thuộc và tiêu chí khôi phục có thể đo.
3. Lựa chọn giữa **backup and restore, pilot light, warm standby, hot standby và active-active**, đồng thời đánh giá chi phí, rủi ro và điều kiện bảo đảm của từng mô hình.
4. Thiết kế các lớp khôi phục gồm dữ liệu, compute, network, IAM, khóa mã hóa, DNS, secret, CI/CD, giám sát và các phụ thuộc bên ngoài.
5. Phân tích nhất quán dữ liệu, replication lag, split-brain, failover/failback, ransomware và khả năng khôi phục từ điểm sạch.
6. Lập test plan, thu thập bằng chứng và kết luận assurance dựa trên **security objective → architecture control → test → evidence → finding → retest**.

## 1. DR architecture giải quyết vấn đề gì?

**DR architecture** là cấu trúc hệ thống, vùng lỗi, dữ liệu dự phòng, năng lực tính toán, hạ tầng quản trị và các cơ chế chuyển đổi cần thiết để **phục hồi dịch vụ ở mức chấp nhận được sau sự cố nghiêm trọng**. Một kiến trúc DR đúng phải hỗ trợ cả khôi phục **tính sẵn sàng** lẫn kiểm chứng **tính toàn vẹn, bảo mật và khả năng vận hành** của hệ thống được khôi phục.

Ví dụ: cụm máy chủ ứng dụng và cơ sở dữ liệu đang ở region A. Một sự cố khiến cả region A không khả dụng. Hệ thống có một bản sao database ở region B nhưng khóa mã hóa, DNS, chứng chỉ, container image và quyền quản trị vẫn chỉ phụ thuộc region A. Dù dữ liệu có thể còn nguyên, dịch vụ chưa chắc khôi phục được. DR architecture phải bao quát **chuỗi phụ thuộc đầu-cuối**.

Trong mô-đun **SECURITY_SECURITY_ASSURANCE**, một tuyên bố như “hệ thống giao dịch có thể khôi phục trong 60 phút và mất tối đa 15 phút dữ liệu” chỉ có ý nghĩa khi phạm vi, điều kiện thử, thời gian và bằng chứng được xác định. Việc có replica hoặc backup là **bằng chứng tồn tại một cơ chế**, chưa phải bằng chứng mục tiêu phục hồi được đáp ứng.

### 1.1. Phân biệt các khái niệm

| Khái niệm | Câu hỏi trọng tâm | Ví dụ |
|---|---|---|
| **High availability (HA)** | Làm sao dịch vụ chịu được một số lỗi thường gặp mà ít gián đoạn? | Nhiều replica, load balancer, multi-AZ. |
| **Disaster recovery (DR)** | Khi một vùng lỗi lớn hoặc môi trường điều hành bị hỏng, khôi phục bằng cách nào và mất bao lâu? | Chuyển sang region/site dự phòng, phục hồi database từ điểm nhất quán. |
| **Backup** | Có bản sao dữ liệu hoặc trạng thái để phục hồi không? | Snapshot, backup định kỳ, transaction log archive. |
| **Business continuity (BC)** | Hoạt động kinh doanh thiết yếu tiếp tục thế nào khi hệ thống chưa sẵn sàng? | Quy trình thủ công tạm thời, thứ tự ưu tiên dịch vụ, truyền thông khách hàng. |
| **Incident response (IR)** | Phát hiện, điều tra, ngăn chặn và loại bỏ nguyên nhân sự cố thế nào? | Cô lập tài khoản bị xâm nhập, thu thập chứng cứ. |
| **Cyber recovery** | Làm sao khôi phục từ điểm sạch sau tấn công có thể làm hỏng cả hệ chính và bản sao? | Isolated recovery environment, immutable backup, quét và xác minh dữ liệu trước đưa vào vận hành. |

**HA không thay thế DR.** Multi-AZ có thể chống lỗi một availability zone nhưng không tự xử lý mất cả region, xóa dữ liệu logic, credential bị chiếm hoặc thao tác phá hủy được đồng bộ tới mọi replica.

**Backup không đồng nghĩa khả năng phục hồi.** Backup phải còn đọc được, có khóa giải mã, được bao phủ đủ dữ liệu, khôi phục được với phần mềm/phụ thuộc tương ứng và đạt mục tiêu thời gian đã cam kết.

### 1.2. Thuộc tính bảo mật khi khôi phục

| Thuộc tính | Câu hỏi kiểm chứng trong DR |
|---|---|
| **Availability** | Hệ thống có trở lại cung cấp chức năng thiết yếu đúng RTO? |
| **Integrity** | Dữ liệu phục hồi có nhất quán, không hỏng, không bị sửa trái phép hoặc nhân bản giao dịch? |
| **Confidentiality** | Dữ liệu backup, replica, secret và đường khôi phục có được bảo vệ khỏi truy cập trái phép? |
| **Authenticity** | Artifact, image, cấu hình và bản backup dùng để phục hồi có nguồn gốc đáng tin? |
| **Accountability** | Có chứng cứ ai kích hoạt failover, sử dụng quyền nào, thực hiện thao tác gì và khi nào? |
| **Recoverability** | Có thực sự dựng lại được các phụ thuộc và xác nhận dịch vụ hoạt động sau phục hồi? |

Kiến trúc chỉ ưu tiên thời gian phục hồi nhưng mở quyền quản trị quá rộng hoặc khôi phục từ dữ liệu đã bị tấn công có thể làm gia tăng tác động sự cố.

## 2. Bắt đầu từ BIA, risk assessment và mục tiêu phục hồi

**Business Impact Analysis (BIA)** đánh giá điều gì xảy ra khi một chức năng kinh doanh bị gián đoạn theo thời gian: doanh thu, nghĩa vụ với khách hàng, an toàn, vận hành, pháp lý, uy tín và tác động dây chuyền. Kết quả BIA giúp xác định mức phục hồi cần thiết trước khi chọn công nghệ.

### 2.1. RTO, RPO và phạm vi thời gian

- **RTO (Recovery Time Objective):** thời gian mục tiêu tối đa để khôi phục một dịch vụ hoặc chức năng đã xác định tới mức chấp nhận được sau mốc sự cố đã thống nhất.
- **RPO (Recovery Point Objective):** mức mất dữ liệu tối đa có thể chấp nhận, biểu diễn bằng khoảng thời gian dữ liệu chưa được bảo toàn tại thời điểm sự cố.
- **MTPD/MAO:** khoảng gián đoạn tối đa mà hoạt động kinh doanh còn chịu được theo định nghĩa BIA; thường dùng để kiểm tra liệu RTO có phù hợp với tác động kinh doanh.
- **Recovery validation time:** thời gian xác minh dữ liệu, chức năng, bảo mật và giao dịch trước khi tuyên bố dịch vụ phục hồi; phải tính vào RTO nếu tiêu chí RTO yêu cầu chức năng được xác nhận.
- **Actual recovery time và actual recovery point:** số đo thực từ diễn tập hoặc sự cố, dùng đối chiếu với mục tiêu.

**RTO và RPO là mục tiêu, không phải kết quả tự động có được do mua một dịch vụ cloud.** Các mốc phải có định nghĩa chính xác và đo bằng chứng từ một lần khôi phục thực tế.

Ví dụ:

| Hệ thống | RTO minh họa | RPO minh họa | Điều phải làm rõ |
|---|---:|---:|---|
| API đặt hàng | 60 phút | 15 phút | Chấp nhận mức chức năng nào khi trở lại? |
| Cơ sở dữ liệu đơn hàng | 45 phút | 5 phút | Dữ liệu đã commit, trạng thái transaction và đối soát thế nào? |
| Báo cáo phân tích ngày | 24 giờ | 24 giờ | Có thể tái xử lý từ nguồn gốc không? |
| IAM/SSO nội bộ | 30 phút | Theo tính chất dữ liệu | Nếu IdP không hoạt động, ai có quyền khởi tạo DR? |

**Các con số chỉ là ví dụ học tập**, không phải SLA áp dụng chung. Khi nhiều hệ thống nối tiếp, mục tiêu từng thành phần phải tương thích với mục tiêu của chức năng kinh doanh cuối cùng.

### 2.2. Phân tích dependency trước khi chọn DR

Một dịch vụ đặt hàng thường phụ thuộc vào:

- DNS, chứng chỉ TLS, CDN/WAF, API gateway và đường mạng đến người dùng.
- Compute, container runtime, image registry, scheduler và cấu hình.
- Database giao dịch, object storage, message broker, cache.
- IdP/IAM, service account, secret manager, KMS và quyền tạo tài nguyên.
- Thanh toán, email/SMS, hệ thống đối tác và các API bên ngoài.
- CI/CD, Infrastructure as Code (IaC), policy, artifact đã ký và registry.
- Log/metrics/traces, health checks, alerting và hệ thống điều phối sự cố.

~~~mermaid
flowchart TD
    U["Người dùng"] --> DNS["DNS / Traffic routing"]
    DNS --> EDGE["WAF / Gateway / TLS"]
    EDGE --> APP["Order API"]
    APP --> DB["Transactional database"]
    APP --> MQ["Message broker"]
    APP --> OBJ["Object storage"]
    APP --> AUTH["IAM / Secrets / KMS"]
    MQ --> WORKER["Background workers"]
    WORKER --> PAY["Payment provider"]
    APP --> MON["Logs / Metrics / Alerts"]
    IAC["IaC / Image registry / Policy"] --> APP
    IAC --> DB
~~~

Mỗi mũi tên là một **phụ thuộc cần kiểm tra trong kịch bản thảm họa**. Chỉ nhân bản APP và DB sang site B không bảo đảm site B hoạt động nếu gateway, KMS, broker hoặc quyền quản trị vẫn thuộc điểm lỗi chung.

### 2.3. Mô hình đe dọa cho DR

| Kịch bản | Ranh giới bị ảnh hưởng | Câu hỏi thiết kế |
|---|---|---|
| Mất một node hoặc AZ | Compute hoặc AZ nội vùng | HA có xử lý đủ hay phải kích hoạt DR? |
| Mất cả region/site | Hạ tầng vùng và một phần dịch vụ quản trị | Site dự phòng có đủ tài nguyên, dữ liệu, mạng, IAM và khả năng tự hoạt động không? |
| Cloud account bị chiếm | Mặt quản trị, quyền xóa/sửa trên nhiều tài nguyên | Backup và tài khoản DR có nằm ngoài phạm vi quyền của attacker không? |
| Ransomware / xóa dữ liệu logic | Nguồn dữ liệu và có thể cả replica | Có điểm phục hồi sạch, cách ly, chống sửa/xóa không? |
| Dữ liệu bị ghi sai ứng dụng | Logic nghiệp vụ, replication | Có PITR, event journal, đối soát và cơ chế quyết định điểm khôi phục? |
| Sự cố DNS / IdP / KMS | Phụ thuộc chung | Đường chuyển đổi còn khả dụng và bảo mật khi các thành phần này lỗi không? |
| Mất kết nối giữa hai site | Quorum, đồng bộ và định tuyến | Có nguy cơ hai site cùng nhận ghi gây split-brain không? |
| Sự cố nhà cung cấp ngoài | Payment, email, identity federation | Chức năng tối thiểu có thể hoạt động/degrade thế nào? |

Thiết kế phải nêu **phạm vi bảo vệ và trường hợp không được bảo vệ**. Ví dụ mô hình multi-region trong cùng cloud account có thể xử lý lỗi vùng nhưng vẫn bị ảnh hưởng nếu attacker kiểm soát toàn bộ account và xóa cả hai region.

## 3. Các mô hình kiến trúc DR phổ biến

### 3.1. So sánh các lựa chọn

| Mô hình | Trạng thái ở site dự phòng | Ưu điểm | Hạn chế/rủi ro |
|---|---|---|---|
| **Backup and restore** | Chủ yếu lưu backup, hạ tầng có thể phải dựng mới. | Chi phí chạy thường thấp, đơn giản về compute. | Thời gian dựng/restore lâu, phụ thuộc công cụ và dung lượng, RPO bị chi phối backup/log archive. |
| **Pilot light** | Giữ thành phần tối thiểu, nhất là dữ liệu và nền tảng cốt lõi; compute phần lớn tắt hoặc quy mô nhỏ. | Cân bằng chi phí và khả năng dựng nhanh hơn backup-only. | Phải scale và nối các phụ thuộc khi xảy ra sự cố; ít kiểm chứng ở tải thực. |
| **Warm standby** | Môi trường ứng dụng và dữ liệu hoạt động ở quy mô giảm. | Có thể tăng quy mô/chuyển traffic tương đối nhanh. | Tốn chi phí liên tục; capacity, state và cấu hình có thể lệch production. |
| **Hot standby / active-passive** | Site dự phòng gần sẵn sàng với năng lực có thể phục vụ nhanh, thường không nhận phần lớn traffic ghi. | Thời gian chuyển nhanh nếu mọi phụ thuộc hoạt động. | Chi phí cao; phức tạp về dữ liệu, DNS, quyền và giám sát. |
| **Active-active** | Nhiều site chủ động phục vụ traffic. | Có thể giảm thời gian chuyển khi mất site, tận dụng năng lực. | Phức tạp nhất về dữ liệu ghi, conflict, idempotency, session và split-brain. |

Đây là phổ kiến trúc, không phải các mức có **RTO/RPO cố định**. Một warm standby được thử nghiệm tốt có thể phục hồi nhanh hơn hot standby đang cấu hình sai. **RTO/RPO chỉ được xác nhận bởi thiết kế chi tiết, độ đầy đủ của dữ liệu và kết quả diễn tập**.

### 3.2. Backup and restore

~~~mermaid
flowchart LR
    P["Primary workload + DB"] --> B["Versioned backup / PITR archive"]
    B --> V["Vault tách quyền, có kiểm tra integrity"]
    V --> R["Restore sang môi trường phục hồi"]
    I["IaC + trusted artifacts"] --> R
    R --> T["Kiểm thử và mở traffic"]
~~~

Điều kiện quan trọng:

- Backup có chứa tất cả phần dữ liệu cần thiết: DB, object, config, schema, transaction log, metadata.
- Hạ tầng khôi phục được dựng từ IaC/ảnh phần mềm và cấu hình đáng tin.
- Có khóa giải mã, quyền đọc vault và quota/dung lượng phù hợp khi site chính không hoạt động.
- Đã thử restoration, consistency, ứng dụng và thời gian khôi phục với quy mô gần thực tế.
- Bản backup không cùng ranh giới xóa/sửa với môi trường có nguy cơ bị tấn công.

Phù hợp khi thời gian gián đoạn dài hơn vẫn được BIA chấp nhận hoặc dữ liệu có thể tái tạo. Nếu RTO rất ngắn, thời gian restore database nhiều terabyte từ backup có thể không phù hợp.

### 3.3. Pilot light và warm standby

**Pilot light** duy trì một lõi có khả năng mở rộng sau sự cố, ví dụ DB replica, nền tảng dữ liệu và cấu hình tối thiểu; ứng dụng được dựng hoặc scale khi kích hoạt DR.

**Warm standby** duy trì ứng dụng sẵn chạy nhưng công suất nhỏ, đồng thời cập nhật dữ liệu và cấu hình. Khi failover phải scale, kiểm tra sức chịu tải, mở traffic và giám sát backlog.

Rủi ro cần thử:

- Capacity/quota ở site B có đủ khi cả workload chính chuyển sang không?
- Node image, registry, artifact và dependencies có cùng phiên bản/phù hợp?
- Autoscaling có hoạt động khi control plane hoặc API vùng chính bị lỗi không?
- Data replica bắt kịp đến mốc nào? Có thể phục hồi nhất quán không?
- Bảo mật site dự phòng có cùng baseline RBAC, network segmentation, secrets, logging và policy không?

### 3.4. Active-active

Active-active có thể vận hành các dịch vụ độc lập ở nhiều site. Tuy nhiên, nếu cả hai site cùng nhận ghi lên **cùng dữ liệu logic**, phải thiết kế nhất quán, phân quyền writer, kiểm soát conflict và phục hồi sau network partition.

Một số lựa chọn:

- **Single writer per shard/tenant:** mỗi nhóm dữ liệu có một nơi ghi được chỉ định; tránh concurrent write cho cùng shard, song việc chuyển quyền writer cần fencing.
- **Multi-writer với conflict resolution:** yêu cầu mô hình dữ liệu, thứ tự sự kiện và quy tắc giải quyết xung đột đã định; không phải mọi dữ liệu tài chính đều phù hợp.
- **Synchronous replication/quorum:** có thể giảm khả năng mất dữ liệu được xác nhận nhưng làm tăng latency và có thể giảm availability khi partition.
- **Asynchronous replication:** thường chấp nhận độ trễ và nguy cơ thiếu dữ liệu chưa kịp đồng bộ, cần quy trình reconciliation.

Không tuyên bố “RPO = 0” chỉ vì đặt tên active-active hoặc dùng replication. Phải xác minh **acknowledgment semantics, ranh giới commit, trạng thái bền vững, vùng lỗi và quy tắc khi mạng phân mảnh**.

## 4. Thiết kế vùng lỗi và sự độc lập của recovery site

### 4.1. Phân tách lỗi thực sự

Các cấp phân tách có đặc tính khác nhau:

- **Process/node:** bảo vệ trước lỗi thành phần đơn lẻ; không giải quyết lỗi vùng hay IAM chung.
- **Availability zone:** giảm rủi ro một vùng triển khai độc lập bị lỗi; vẫn có thể chia sẻ một số dịch vụ cấp region.
- **Region/site:** giảm tương quan lỗi hạ tầng vùng; phụ thuộc dịch vụ global vẫn cần phân tích.
- **Cloud account/project/subscription:** có thể giảm phạm vi quyền quản trị và sự cố cấu hình lan rộng nếu governance/IAM được tách hợp lý.
- **Provider/địa điểm vật lý khác:** có thể giảm phụ thuộc nhà cung cấp nhưng tăng chi phí, phức tạp về dữ liệu, mạng, kỹ năng và consistency.

**Hai site chỉ độc lập đến mức các thành phần phụ thuộc chung cho phép.** Có hai database ở hai region nhưng sử dụng một secret manager, DNS, KMS hoặc pipeline deploy chỉ hoạt động từ region chính vẫn tồn tại điểm lỗi chung.

### 4.2. Recovery control plane

Cần xác định ai và bằng cách nào sẽ thực hiện DR khi một phần control plane không khả dụng:

| Thành phần | Rủi ro khi thảm họa | Thiết kế cần kiểm chứng |
|---|---|---|
| **IAM/SSO** | Người trực không đăng nhập được vì IdP hoặc federation lỗi. | Break-glass account có quản trị, MFA/phương thức dự phòng phù hợp, audit và thử đăng nhập trong phạm vi được phép. |
| **KMS/keys** | Có backup nhưng không giải mã được tại site B. | Key/permission ở site B, khả năng cấp và kiểm tra giải mã theo công nghệ cụ thể. |
| **Secret manager** | Workload DR không lấy được thông tin xác thực. | Secret/rotation/revocation độc lập đủ để khởi động an toàn. |
| **IaC/CI/CD** | Không chạy pipeline dựng hạ tầng do runner, code repo hoặc approval service lỗi. | Artifact, công cụ, quyền và quy trình dựng thay thế được kiểm thử. |
| **Container/image registry** | Image không pull được tại vùng dự phòng. | Artifact đã xác minh sẵn có ở site B, phân quyền và kiểm tra digest. |
| **DNS/traffic manager** | Route không chuyển, client còn cache IP cũ. | Zone/record/health, TTL thực tế, khả năng thay đổi routing và test client. |
| **Observability** | Không biết DR đã phục hồi đúng chưa, log bị mất. | Giám sát riêng site B, log tập trung hoặc kênh dự phòng. |
| **Network/PKI** | VPN, firewall, certificate hoặc private endpoints thiếu. | Kết nối, DNS nội bộ, CA/certificate, route và policy được kiểm tra. |

Đối với chức năng phục hồi quan trọng, **đường quản trị dự phòng phải sử dụng được trong chính kịch bản mất phụ thuộc đang được bảo vệ**. Ví dụ break-glass chỉ hoạt động qua SSO đã hỏng là một đường phục hồi giả.

### 4.3. Giảm nguy cơ lây lan sự cố bảo mật

Nếu attacker có thể xóa backup, tắt replication hoặc dùng quyền admin của primary để thay đổi DR site, kiến trúc có thể không chống được sự cố an ninh.

Các biện pháp theo rủi ro gồm:

- Tách account/project và role bảo toàn backup, hạn chế quyền xóa/đổi retention.
- Backup bất biến hoặc cơ chế khóa retention phù hợp; giữ bản sao ngoại tuyến hoặc cách ly theo yêu cầu.
- Chỉ cấp quyền tối thiểu cho automation sao chép và phục hồi; audit các thao tác nhạy cảm.
- Giữ nhiều điểm phục hồi theo thời gian để xử lý corruption/ransomware bị phát hiện trễ.
- Dựng môi trường phục hồi cách ly để kiểm tra nguồn sạch, persistence, IAM và artifact trước khi nối lại production.
- Tách credential và secret giữa môi trường chính và môi trường phục hồi khi kiến trúc cho phép.
- Giám sát cả việc tắt backup, thay replication, tăng quyền và thao tác trên recovery vault.

**Replication không phải backup chống tấn công.** Nếu ứng dụng xóa dữ liệu, khóa hàng loạt bản ghi hoặc malware mã hóa dữ liệu, trạng thái xấu có thể được đồng bộ sang replica.

## 5. Kiến trúc dữ liệu: replication, backup và consistency

Dữ liệu thường là phần khó phục hồi nhất. Cần chỉ rõ **đơn vị dữ liệu, điểm commit, nhất quán giữa hệ thống và thời gian có thể mất**.

### 5.1. Replication và recovery point

| Cơ chế | Khả năng chính | Rủi ro cần xét |
|---|---|---|
| **Synchronous replication** | Chờ xác nhận từ các bản sao theo semantics của hệ thống trước khi commit/ack. | Latency cao, phụ thuộc quorum, giảm availability khi partition; không bảo đảm tất cả lớp ứng dụng cùng atomic. |
| **Asynchronous replication** | Primary trả kết quả trước khi dữ liệu được chuyển/áp dụng đầy đủ ở DR. | Có thể mất giao dịch đã ack nhưng chưa sang site B; phải đo lag và durability. |
| **Periodic snapshot/backup** | Giữ điểm khôi phục có thời điểm. | Khoảng cách snapshot, trạng thái nhất quán, khả năng giải mã/restore. |
| **Point-in-time recovery (PITR)** | Kết hợp baseline backup với log/journal để phục hồi đến mốc hỗ trợ. | Log archive có thể thiếu/hỏng; restore lâu; phải xác minh độ nhất quán của mốc. |
| **CDC/event replication** | Chuyển thay đổi sang hệ thống khác, hỗ trợ rebuild/read model. | Event mất/trùng/đảo thứ tự; consumer và schema chưa chắc tương thích. |

**RPO thực tế** phải tính từ **điểm dữ liệu gần nhất có thể phục hồi nhất quán**, không chỉ từ con số replication lag hiển thị trên dashboard.

Ví dụ tại thời điểm gián đoạn **10:00 UTC**, điểm phục hồi nhất quán được xác nhận gần nhất là **09:53 UTC**. Mức mất dữ liệu theo thời gian quan sát là **7 phút**. Nếu RPO của dịch vụ là 5 phút, lần phục hồi đó **không đạt** dù replication monitor từng báo lag 30 giây trước sự cố.

### 5.2. Application consistency

Một ứng dụng đặt hàng có thể có ba thành phần:

- Database lưu đơn hàng và trạng thái thanh toán.
- Message broker gửi event xử lý thanh toán.
- Object storage giữ hóa đơn và tài liệu kèm theo.

Nếu DB phục hồi lúc 10:00 nhưng queue ở 09:50 và object store ở 09:57, hệ thống có thể xuất hiện đơn hàng đã xác nhận nhưng chưa gửi thanh toán, message xử lý lại hoặc chứng từ bị thiếu.

Cần thiết kế nhất quán theo nghiệp vụ:

- Gắn các thay đổi có liên quan bằng transaction ID và event ID.
- Sử dụng **transactional outbox** hoặc cơ chế thích hợp để giảm mất event giữa DB và broker.
- Consumer xử lý **idempotent**, có dedup và kế hoạch replay.
- Phân biệt giao dịch đã được khách hàng/đối tác xác nhận với giao dịch chỉ mới nằm trong queue.
- Đối soát dữ liệu giữa DB, object, ledger và dịch vụ bên ngoài sau phục hồi.
- Có quy trình xử lý giao dịch trong khoảng RPO được chấp nhận và trường hợp cần bù trừ.

**Crash-consistent snapshot** có thể tương đương một lần máy mất nguồn và cần replay journal. **Application-consistent snapshot** có thể cần phối hợp flush/quiesce hoặc cơ chế backup của DB. Cả hai khái niệm phải được kiểm chứng theo hệ thống, không suy ra từ tên snapshot.

### 5.3. Split-brain và quyền ghi duy nhất

~~~mermaid
flowchart LR
    A["Site A: primary writer"] <-->|"Replication / health"| B["Site B: standby"]
    A --> Q["Quorum / fencing decision"]
    B --> Q
    Q --> W["Chỉ một writer hợp lệ cho cùng dữ liệu"]
~~~

Khi site A không trả lời health check vì mất mạng, A có thể vẫn nhận ghi từ một nhóm client. Nếu site B tự động trở thành writer mà không có cơ chế **fencing/quorum/lease** đáng tin, cả hai site có thể phát sinh dữ liệu khác nhau.

Cần quy định:

1. Ai có quyền bầu/promote writer?
2. Trước khi promote B, có xác nhận A đã bị ngăn nhận ghi không?
3. Quyết định dựa trên tín hiệu nào khi mất liên lạc và quorum không đủ?
4. Nếu A trở lại, làm sao ngăn A tự tiếp tục ghi mà chưa được hòa giải?
5. Có thực hiện reconciliation và xử lý conflict khi failback không?

Không bật automatic failover chỉ dựa trên một health check đơn giản đối với dữ liệu không chịu được ghi song song. Chính sách có thể ưu tiên nhất quán hơn tính sẵn sàng; lựa chọn phải gắn BIA và rủi ro nghiệp vụ.

### 5.4. Backup sạch sau cyber incident

Nếu sự cố là ransomware, credential compromise hoặc phá hoại dữ liệu, một replica có dữ liệu “mới nhất” có thể cũng đã bị nhiễm. Khi đó DR cần thêm:

- Xác định **time of compromise** và thời điểm dữ liệu bắt đầu bị sửa; có thể chưa biết chính xác.
- Lựa chọn một restore point có đủ bằng chứng sạch theo phạm vi thử.
- Dựng **isolated recovery environment**, hạn chế kết nối ra/vào và quyền của credential cũ.
- Quét artifact/config, kiểm tra persistence, integrity, dữ liệu và các dấu hiệu compromise còn lại.
- Rotate/revoke các credential liên quan; xác minh trust chain của image, IaC và pipeline.
- Chỉ mở kết nối với production sau khi kết quả kiểm thử đáp ứng điều kiện go/no-go.

Một bản backup “đã restore thành công” nhưng chứa backdoor hoặc dữ liệu bị thao túng **chưa phải khôi phục an toàn**.

## 6. Thiết kế đủ lớp cho một hệ thống phục hồi được

### 6.1. Workload và infrastructure

- IaC mô tả network, compute, storage, service account, policy và các resource cần thiết.
- Artifact được ghim phiên bản/digest, có cơ chế chứng minh nguồn và kiểm tra lỗ hổng phù hợp.
- Capacity, quota, IP range và giới hạn cloud service tại site B đã được đánh giá.
- Chọn rõ cơ chế scale từ pilot light/warm standby lên tải cần phục vụ, gồm DB connection limit và broker throughput.
- Có version compatibility của ứng dụng, schema và dữ liệu khi chuyển site.
- Có lệnh rollback và cách xác nhận trạng thái sau mỗi bước.

Một bản IaC triển khai thành công chỉ chứng minh khả năng **tạo resource**; vẫn cần thử chức năng, dữ liệu và bảo mật trên môi trường đã dựng.

### 6.2. Network, DNS và traffic switching

Đường tiếp cận người dùng có thể bao gồm global traffic manager, DNS, CDN, API gateway, firewall, WAF, ingress, private endpoints, VPN và certificate. Để chuyển sang site B phải:

- Xác định health check phản ánh **chức năng ứng dụng thực**, không chỉ TCP port mở.
- Kiểm tra TTL, DNS resolver cache, connection reuse, client retry và session affinity.
- Đảm bảo TLS certificate, DNS record, domain validation, route và firewall đã sẵn sàng.
- Giới hạn chuyển đổi để tránh gửi traffic ghi vào hai site cùng lúc.
- Bảo đảm dữ liệu/identity phiên mới và session hiện hữu được xử lý theo chính sách.
- Đo thời điểm phần lớn client thực sự vào site mới, không chỉ thời điểm API trả “update DNS thành công”.

TTL nhỏ không bảo đảm mọi client đổi đích đúng TTL; một số resolver/client vẫn cache hoặc giữ kết nối lâu hơn. Do đó việc thiết lập DNS chỉ là một bước của phép đo RTO.

### 6.3. Identity, keys, secrets và security baseline

Khả năng khôi phục an toàn cần kiểm chứng:

- **Break-glass:** tài khoản khẩn cấp được bảo vệ, người có thẩm quyền biết cách dùng và việc sử dụng được audit.
- **KMS:** khóa giải mã/định danh key, policy và quyền tại nơi khôi phục; không giả định mọi khóa tự động có mặt ở region B.
- **Secrets:** bản sao cần thiết và quy trình cấp/rotate, tránh sao chép credential đã bị xâm nhập sang môi trường sạch.
- **RBAC/IAM:** role ứng dụng và người vận hành đủ quyền tối thiểu; tài khoản chạy DR không có quyền phá backup ngoài phạm vi.
- **Network isolation:** phân đoạn DR, mặc định từ chối kết nối không cần thiết; không mở mọi firewall tạm thời mà quên khôi phục.
- **Host/container hardening:** image, seccomp, admission policy, logging, anti-malware/EDR nếu áp dụng phù hợp.
- **Audit/monitoring:** thời điểm failover, login, restore và thay đổi cấu hình vẫn có log ngay cả khi nguồn tập trung bị gián đoạn.

Không đánh đổi security baseline lấy thời gian phục hồi bằng các quyền quá rộng không được kiểm soát. Nếu có ngoại lệ khẩn cấp, phải có phạm vi, owner, thời hạn và bước xóa ngoại lệ sau recovery.

### 6.4. Monitoring của chính DR

Giám sát kiến trúc DR phải phát hiện cả **lỗi thầm lặng**:

- Backup/replication job không chạy, job chạy nhưng dữ liệu không sử dụng được.
- Replication lag vượt ngưỡng RPO.
- Backup object bị xóa, sửa retention, khóa KMS không dùng được, quyền đọc vault thay đổi.
- Cluster site B thiếu dung lượng/quota, image hoặc secret cần thiết.
- DR service deployment/configuration drift so với baseline.
- DNS/certificate/traffic routing không còn hợp lệ.
- Diễn tập không chạy đúng hạn, test restore fail hoặc chưa xử lý finding.

Một trạng thái dashboard “backup success” không tự chứng minh có thể dựng ứng dụng, giải mã, đối soát dữ liệu và phục vụ người dùng.

## 7. Ví dụ kiến trúc: Order API RTO 60 phút, RPO 15 phút

### 7.1. Bối cảnh và phạm vi

Giả sử một doanh nghiệp có:

- **Order API** và worker xử lý đơn hàng trên Kubernetes.
- **Transactional DB**, message broker và object storage.
- DNS/gateway, IAM/KMS/secret manager và monitoring.
- Một tích hợp thanh toán của bên thứ ba.

Theo BIA giả định, chức năng **tạo và tra cứu đơn hàng cơ bản** phải trở lại trong 60 phút; mức mất dữ liệu đã commit tối đa được chấp nhận là 15 phút trong kịch bản mất một region. Những giao dịch thanh toán cần được **đối soát** vì một hệ thống bên ngoài có thể đã xử lý giao dịch trong khi DB nội bộ chưa kịp đồng bộ.

### 7.2. Mô hình lựa chọn: warm standby ở site B

~~~mermaid
flowchart LR
    USERS["Clients"] --> ROUTER["DNS / Global traffic manager"]
    ROUTER --> G1["Gateway A - active"]
    ROUTER -.-> G2["Gateway B - standby"]
    G1 --> APP1["Order API A"]
    G2 --> APP2["Order API B - reduced capacity"]
    APP1 --> DB1["DB A - writer"]
    APP2 --> DB2["DB B - replica"]
    DB1 -->|"Replication + monitored lag"| DB2
    DB1 -->|"Backup + log archive"| VAULT["Protected backup vault"]
    VAULT -.-> DB2
    APP1 --> Q1["Broker A"]
    APP2 --> Q2["Broker B / replay strategy"]
    IAC["Versioned IaC + trusted images"] --> APP1
    IAC --> APP2
    ID["IAM / KMS / Secrets with DR path"] --> APP2
    OBS["Monitoring + audit across sites"] --> G1
    OBS --> G2
~~~

**Sơ đồ mô tả quan hệ, không phải cấu hình có thể chạy trực tiếp.** Ở trạng thái bình thường, A là writer; B chưa nhận ghi cho cùng dữ liệu. Cơ chế bảo đảm B không promote khi A vẫn nhận ghi phải được lựa chọn và kiểm chứng phù hợp với database.

### 7.3. Bản đặc tả DR minh họa

~~~yaml
service: order-platform
scope:
  business_capability: create-and-query-orders
  primary_site: region-a
  recovery_site: region-b
objectives:
  rto_minutes: 60
  rpo_minutes: 15
strategy:
  pattern: warm-standby
  writer_mode: single-writer
  promotion: controlled-with-fencing
  data:
    transactional_db: asynchronous-replica-plus-protected-backup
    object_storage: versioned-replication-plus-restore-tests
    message_broker: durable-events-and-reconciliation
  compute:
    standby_capacity: reduced
    scale_up_required: true
  control_plane:
    independent_recovery_iam_path: required
    restore_key_access: verified
    trusted_artifacts_at_dr_site: required
  observability:
    backup_health: monitored
    replication_lag: monitored
    dr_alert_routing: tested
acceptance:
  core_endpoints: health-create-query-order
  database_consistency: verified
  external_payment_reconciliation: required
  audit_logging_at_dr_site: verified
  rto_and_rpo_evidence: required
~~~

Đây là **tài liệu thiết kế**, không phải schema của Kubernetes hoặc nhà cung cấp cloud. Những từ như **required** phải được chuyển thành control có owner, test và bằng chứng trong triển khai.

### 7.4. Ngân sách RTO đầu-cuối

Ví dụ dự kiến các giai đoạn:

| Giai đoạn | Ngân sách |
|---|---:|
| Phát hiện và đánh giá sự cố | 7 phút |
| Quyết định kích hoạt DR, liên lạc và xác nhận quyền | 5 phút |
| Fencing/promotion writer và khởi tạo tài nguyên | 7 phút |
| Hoàn tất recovery/catch-up dữ liệu | 15 phút |
| Scale ứng dụng, chuyển traffic và kiểm tra route | 6 phút |
| Xác minh chức năng, dữ liệu, an ninh và đối soát bước đầu | 10 phút |
| **Tổng thời gian dự kiến** | **50 phút** |
| **Dự phòng so với RTO 60 phút** | **10 phút** |

Đây là **ước lượng lập kế hoạch**, chưa phải kết quả được đảm bảo. Cần diễn tập với dữ liệu, tải và hạn chế quyền tương đương môi trường thật. Nếu một khâu kéo dài hoặc phát hiện sự cố muộn, RTO có thể không đạt. Một quy trình chỉ tính thời gian từ lúc người trực bấm “failover” mà bỏ thời gian phát hiện/quyết định sẽ làm báo cáo RTO sai nếu định nghĩa RTO bắt đầu từ khi dịch vụ mất khả dụng.

### 7.5. Kiểm tra RPO

Giả sử vùng A lỗi lúc **10:00 UTC**. Bản dữ liệu nhất quán cuối cùng mà B khôi phục được là **09:48 UTC**. Mức mất dữ liệu theo thời gian là **12 phút**; trường hợp này **đạt RPO 15 phút**, với điều kiện xác minh dữ liệu đã commit trong mốc 09:48 thực sự tồn tại và nhất quán sau restore.

Nếu điểm phục hồi thực là **09:42 UTC**, mất **18 phút**, kết quả **FAIL**. Dù dashboard trước sự cố từng hiển thị replication lag nhỏ, không được dùng số lag đó thay cho điểm recoverable đã kiểm chứng.

### 7.6. Các bước khôi phục và bằng chứng

1. Xác nhận sự cố, kịch bản DR được hỗ trợ, người ra quyết định và mốc bắt đầu RTO.
2. Xác minh site B, key access, backup/replica, network, capacity và đường quản trị đang đủ điều kiện.
3. Chặn nguồn ghi cũ theo cơ chế fencing phù hợp; nếu không thể xác nhận, áp dụng chính sách ưu tiên nhất quán đã định.
4. Chọn điểm dữ liệu an toàn; xác minh data integrity, khả năng đọc và phạm vi mất dữ liệu.
5. Promote DB/khởi động broker và scale application tại site B; đối chiếu image, config, IAM và schema.
6. Kiểm tra chức năng tạo/tra cứu đơn; đối soát giao dịch thanh toán và queue theo quy tắc idempotency.
7. Chuyển traffic với health checks, theo dõi response và kiểm tra endpoint từ góc nhìn client.
8. Xác nhận logging, alert, IAM, secret và policy tại site B vẫn hoạt động.
9. Ghi thời điểm phục hồi, đạt/chưa đạt RTO và RPO, gap, exception và công việc cần xử lý tiếp.

## 8. Failover, failback và vận hành trong trạng thái DR

### 8.1. Failover không chỉ là đổi DNS

Một runbook failover cần có:

- **Điều kiện kích hoạt:** tín hiệu mất chức năng, mức ảnh hưởng, loại thảm họa và tính đúng đắn của dữ liệu tại site B.
- **Quyết định:** ai có quyền kích hoạt, khi nào dừng thay đổi triển khai, liên lạc với đơn vị phụ thuộc.
- **Data control:** đóng/khóa writer cũ, chọn recovery point, bảo đảm nhất quán trước promotion.
- **Infrastructure:** xác nhận quota, node, image, runtime, DB, queue, object, secret, KMS và network.
- **Traffic:** route DNS/global traffic, health, sessions, cache và các client khó chuyển.
- **Security:** kiểm tra đặc quyền, mở/đóng quyền tạm, scan dữ liệu nếu có nghi vấn cyber incident.
- **Validation:** chức năng tối thiểu, transaction integrity, hiệu năng, giám sát, audit.
- **Rollback hoặc contingency:** xử lý khi bước khôi phục không đạt và tránh tạo thêm writer trái phép.

Nếu tự động chuyển traffic, cần kiểm chứng cả tình huống **false-positive health check**. Việc tự động promote sai có thể gây thiệt hại hơn một đợt gián đoạn có kiểm soát, nhất là với dữ liệu ghi.

### 8.2. Failback là một quá trình riêng

Khi site A phục hồi, không nên chuyển ngay traffic ngược về site A vì:

- Dữ liệu tại A có thể cũ, đã hỏng hoặc không có giao dịch mới phát sinh tại B.
- Queue/event consumer có thể đang chạy ở B.
- Cấu hình và schema có thể khác sau khi DR scale hoặc hotfix.
- Một số client vẫn truy cập B do cache/connection.
- Quyền, secrets, certificate và audit settings có thể đổi trong sự cố.

Quy trình failback nên xác nhận **nguồn chân lý mới**, đồng bộ/đối soát dữ liệu, chọn quyền writer, kiểm tra tải, chuyển traffic có giám sát, rollback và chỉ giải phóng site B khi chắc chắn không mất dữ liệu. Có thể tạm thời duy trì B làm primary lâu hơn nếu rủi ro failback lớn.

### 8.3. Hoạt động giới hạn chức năng

BIA có thể cho phép một chế độ **degraded mode** được tài liệu hóa, ví dụ chỉ tra cứu trạng thái đơn và chặn thao tác ghi trong vài phút đầu. Khi đó phải định nghĩa rõ:

- Chức năng nào cần có để tuyên bố “đã phục hồi”.
- Dữ liệu nào phải nhất quán tuyệt đối, dữ liệu nào được chấp nhận trễ.
- Ai thông báo khách hàng/đối tác về hạn chế.
- Tiêu chí chuyển từ degraded mode sang phục vụ bình thường.

Không tính một health endpoint trả 200 là đạt RTO nếu chức năng kinh doanh thiết yếu vẫn không thực hiện được.

## 9. Kiểm chứng DR architecture bằng bằng chứng assurance

### 9.1. Chuỗi truy vết

~~~mermaid
flowchart LR
    R["Threat / BIA"] --> O["RTO, RPO và security claim"]
    O --> C["DR controls & architecture"]
    C --> T["Test cases / exercise"]
    T --> E["Evidence có timestamp"]
    E --> D["PASS / FAIL / INCONCLUSIVE"]
    D --> F["Finding, owner, fix & retest"]
    F --> O
~~~

Một claim nên cụ thể, ví dụ: **“Trong kịch bản mất region A, Order API khôi phục được chức năng tạo/tra cứu đơn ở region B trong 60 phút, với điểm dữ liệu đã commit mất tối đa 15 phút, trong khi IAM, encryption, audit và network baseline vẫn đạt.”**

Không dùng tuyên bố chung “đã có DR” như tiêu chí nghiệm thu.

### 9.2. Ma trận claim → test → evidence

| Claim | Phép thử và tiêu chí chấp nhận | Bằng chứng |
|---|---|---|
| **C1 — RTO dịch vụ đạt mục tiêu.** | Diễn tập failover đủ dependency, xác minh chức năng thiết yếu và đo end-to-end theo mốc đã định. | Run timeline, timestamps, health và business transaction results. |
| **C2 — RPO của dữ liệu đạt mục tiêu.** | Chèn giao dịch kiểm tra được định danh trước sự cố giả lập; khôi phục và xác nhận điểm recoverable. | Commit log, restore metadata, record IDs, reconciliation report. |
| **C3 — Dữ liệu phục hồi nhất quán.** | Kiểm tra foreign key/constraint, ledger balance, outbox/event dedup, object references và giao dịch đối tác. | Validation queries, counts, checksums thích hợp, exception list. |
| **C4 — Backup còn dùng được khi primary không sẵn sàng.** | Restore từ vault trong tài khoản/site được phép; kiểm tra key, quyền và độ đầy đủ. | Backup manifest, restore log, hash/validation và IAM/KMS test. |
| **C5 — Không có split-brain.** | Diễn tập mất kết nối hoặc lỗi health trong sandbox, kiểm tra fencing và quyền ghi đơn nhất. | Writer lease/fencing logs, transaction audit, decision record. |
| **C6 — DR giữ security baseline.** | So chính sách IAM/network/secret/audit/runtime tại site B với baseline và negative access tests. | Policy snapshot, audit events, access denial evidence. |
| **C7 — Tài khoản recovery chịu được lỗi IdP/control plane theo phạm vi.** | Diễn tập đường đăng nhập và khởi tạo phục hồi dự phòng có kiểm soát. | Runbook execution, authentication/audit records. |
| **C8 — Recovery site có capacity thực.** | Chạy tải gần mức chức năng thiết yếu, đo latency/error/saturation và dependency limits. | Load test, autoscaling/quota records, SLO report. |
| **C9 — Failback không tạo dữ liệu mất/trùng.** | Diễn tập đưa traffic và writer trở lại, kiểm tra đồng bộ/đối soát và quy tắc rollback. | Failback log, record reconciliation, transaction verification. |
| **C10 — Kịch bản cyber recovery có điểm sạch.** | Restore isolated recovery từ điểm được chọn; kiểm tra integrity, malware/persistence và quyền trước khi nối mạng. | Artifact provenance, scan/review, clean-point decision, approval. |

**Test pass chỉ có hiệu lực trong phạm vi đã thực hiện.** Một tabletop với sơ đồ và lời mô tả không chứng minh đạt RTO; một lần restore DB không chứng minh ứng dụng, DNS, IAM, queue và external integration hoạt động.

### 9.3. Các cấp độ diễn tập

| Cấp độ | Nội dung | Bằng chứng và giới hạn |
|---|---|---|
| **Tabletop** | Nhóm phối hợp giả lập sự cố, rà soát quyết định và runbook. | Chứng minh quy trình và vai trò được hiểu; chưa chứng minh phục hồi kỹ thuật. |
| **Component restore** | Restore một backup DB/object/config trong lab. | Xác minh artifact và thao tác thành phần, chưa phải end-to-end. |
| **Service recovery** | Dựng ứng dụng, dữ liệu và các dependency chính tại site B. | Kiểm tra chức năng và thời gian cấp dịch vụ. |
| **Failover exercise** | Chuyển traffic ghi/đọc có kiểm soát và đo thực. | Gần mục tiêu RTO/RPO hơn; phải xác định tải, scope, môi trường. |
| **Full-region / cyber recovery exercise** | Mô phỏng mất toàn bộ site hoặc account compromise với các giới hạn an toàn. | Kiểm tra dependency, quyết định, bảo mật, dữ liệu và con người toàn chuỗi. |
| **Failback exercise** | Đồng bộ và chuyển writer/traffic về trạng thái dự kiến. | Xác minh reconciliation, split-brain prevention và rollback. |

Các bài thử có khả năng gây gián đoạn phải có môi trường, phạm vi và phê duyệt rõ ràng; nên sử dụng data test/sandbox hoặc canary có kiểm soát khi phù hợp. Thử nghiệm không được đánh đổi an toàn production nếu mục tiêu assurance có thể đạt bằng phương pháp ít tác động hơn.

### 9.4. Phân loại kết quả

- **PASS:** tất cả tiêu chí bắt buộc trong phạm vi bài thử đều đạt và có bằng chứng.
- **FAIL:** bài thử hợp lệ nhưng có tiêu chí quan trọng không đạt (ví dụ RPO vượt ngưỡng, không giải mã được backup).
- **INCONCLUSIVE:** không đủ dữ liệu để kết luận (ví dụ đồng hồ không đồng bộ, test runner ngừng, transaction marker không được ghi).
- **NOT RUN:** chưa thực hiện bài thử cần thiết, phải nêu lý do và thời hạn dự kiến.
- **EXCEPTION/WAIVER:** rủi ro được người có thẩm quyền chấp nhận có điều kiện; không thay bằng nhãn PASS.

Tất cả kết quả không đạt hoặc chưa đánh giá cần có **finding, severity, owner, deadline, kế hoạch khắc phục và retest**.

## 10. Thu thập evidence cho một lần diễn tập

Một gói evidence có thể gồm:

~~~text
assurance/disaster-recovery/order-platform/
  bia-and-scope.md
  dependency-inventory.csv
  architecture-decision-record.md
  dr-contract.yaml
  threat-model-and-risks.md
  exercise-2026-11-28/
    exercise-scope-and-approval.md
    architecture-and-versions.json
    backup-and-replication-health.json
    identity-kms-secret-checks.json
    source-commit-markers.jsonl
    recovery-point-validation.json
    runbook-execution-timeline.csv
    fencing-and-writer-state.json
    traffic-switch-and-client-checks.csv
    business-functional-tests.json
    data-reconciliation-report.csv
    security-baseline-results.json
    monitoring-and-audit-evidence.json
    failback-results.md
    gaps-and-exceptions.md
    reviewer-decision.md
~~~

Đây là cấu trúc **minh họa**. Chứng cứ cụ thể tùy hệ thống, công cụ và chính sách bảo vệ dữ liệu.

Mỗi phép thử cần đủ metadata để người khác truy vết:

- **Exercise ID, test case ID, phạm vi**: hệ thống, region, account, tenant, data set và loại sự cố.
- **Bản thiết kế và phiên bản**: IaC commit, image digest, DB engine, backup config, network/IAM policy, runbook.
- **Mốc thời gian**: khi dịch vụ mất chức năng, khi phát hiện/ra quyết định, từng bước failover và khi đã xác minh phục hồi; dùng UTC hoặc timestamp có offset.
- **Dữ liệu và kết quả**: transaction marker, recovery point được chứng minh, kết quả functionality, security, consistency, tải.
- **Nguồn bằng chứng**: raw log hoặc bản trích có provenance, link tới hệ thống nguồn, kết quả kiểm tra integrity và cách xử lý thông tin nhạy cảm.
- **Người chịu trách nhiệm**: operator, reviewer, người phê duyệt và người nhận finding.
- **Giới hạn**: điều kiện test khác production, phụ thuộc chưa thử, phần dữ liệu chưa đủ, giả định về đồng hồ và kết quả chưa xác minh.

Không đưa secret, token hoặc dữ liệu khách hàng chưa được bảo vệ vào báo cáo DR. Nên lưu tại kho có quyền phù hợp, integrity/audit và retention theo chính sách.

## 11. Đo lường DR và theo dõi liên tục

### 11.1. Những chỉ số nên quản lý

| Chỉ số | Định nghĩa | Điều kiện để diễn giải đúng |
|---|---|---|
| **Achieved RTO** | Thời điểm dịch vụ đạt tiêu chí phục hồi trừ mốc bắt đầu sự cố đã định. | Phải bao gồm các bước chức năng và xác nhận chất lượng cần thiết. |
| **Achieved RPO** | Thời điểm mất khả dụng/dừng ghi theo định nghĩa trừ điểm dữ liệu phục hồi nhất quán gần nhất. | Cần commit marker/restore validation; đồng hồ và semantics chính xác. |
| **Backup success & restore success** | Job chạy thành công và thử restore thành công, theo số lần hợp lệ. | Backup success không thay được restore success. |
| **Replication lag / freshness** | Độ trễ giữa nguồn và bản sao theo cơ chế lưu trữ. | Chỉ là tín hiệu, không tự bằng achieved RPO. |
| **Recovery capacity readiness** | Mức tài nguyên/quota thực có thể cấp khi failover so với nhu cầu. | Cần test tải, không chỉ inventory capacity. |
| **Dependency readiness** | Tỷ lệ dependency bắt buộc đã có đường phục hồi được kiểm chứng. | Mẫu số phải từ dependency inventory cập nhật. |
| **Security control continuity** | Số control bảo mật thiết yếu tại DR được kiểm chứng đạt / tổng control trong scope. | Phải bao gồm IAM, secrets, network, logging, hardening. |
| **Exercise coverage/freshness** | Tỷ lệ kịch bản rủi ro ưu tiên đã diễn tập trong chu kỳ đã định. | Cần phân biệt tabletop với full failover. |
| **Unresolved DR findings** | Số điểm không đạt, tuổi tồn đọng, severity và owner. | Ít finding không đồng nghĩa không có điểm mù. |

RTO/RPO ở dạng trung bình có thể che các lần thử không đạt. Cần theo dõi **từng lần thực hiện**, các giá trị vượt mục tiêu và bối cảnh hệ thống.

### 11.2. Điều kiện phải kiểm tra lại kiến trúc

- Thêm ứng dụng/dịch vụ, chuyển dữ liệu sang datastore hoặc region mới.
- Tăng đáng kể dung lượng, throughput, số tenant hoặc yêu cầu RTO/RPO.
- Đổi replication, backup policy, KMS, key rotation, IAM hoặc DNS.
- Chuyển cluster, CNI, cloud provider, container registry hoặc build pipeline.
- Sửa schema DB, message contracts, event replay/consumer logic.
- Phát hiện incident/ransomware cho thấy replica hoặc backup dễ bị lây lan.
- Thay nhân sự trực DR, nhà cung cấp dịch vụ hoặc quy trình phê duyệt.
- Diễn tập fail hoặc phát hiện khoảng trống trong kiểm toán.

Kiến trúc DR là **khả năng vận hành phải duy trì**, không phải sơ đồ được ký duyệt một lần rồi bỏ.

## 12. Trách nhiệm, thay đổi và runbook

| Vai trò | Trách nhiệm |
|---|---|
| **Business owner** | Định nghĩa dịch vụ thiết yếu, RTO/RPO chấp nhận, chức năng tối thiểu và tác động. |
| **Architecture/platform team** | Thiết kế vùng lỗi, hạ tầng, network, compute, capacity, automation và dependency. |
| **Data owner/DBA** | Chọn replication/backup, consistency, restore, reconciliation và kiểm tra điểm dữ liệu. |
| **Security/IAM team** | Đảm bảo cách ly, quyền recovery, backup vault, KMS, secrets và kiểm chứng sạch sau tấn công. |
| **Incident commander/DR lead** | Kích hoạt DR, điều phối, quyết định go/no-go và truyền thông. |
| **Service/application team** | Chức năng, schema, transactions, queue và ứng dụng hoạt động tại site mới. |
| **Security assurance/auditor** | Kiểm chứng claim, test evidence, kết quả và việc khắc phục gap. |
| **Risk owner** | Phê duyệt rủi ro còn lại, ngoại lệ và quyết định phù hợp BIA. |

Runbook phải dùng được khi áp lực, mất một số kênh liên lạc hoặc người chủ chốt không sẵn sàng. Chú ý tài liệu và credential recovery phải có **đường truy cập an toàn độc lập** với hệ thống có thể bị lỗi. Các bước nguy hiểm như promote writer, đổi routing, xóa tài nguyên hoặc revoke quyền cần chủ thể rõ, điều kiện dừng và khả năng rollback.

## 13. Những sai lầm thường gặp

1. **“Multi-AZ là DR cho mọi thảm họa.”** Nó có thể giảm lỗi một AZ nhưng không xử lý mọi lỗi region, account compromise hoặc corruption.
2. **“Có replica nghĩa là RPO bằng 0.”** Replica bất đồng bộ có lag và có thể chưa bền vững; replication cũng có thể sao chép thao tác xóa phá hoại.
3. **“Backup thành công nghĩa là khôi phục được.”** Chưa kiểm tra khóa giải mã, quyền, dữ liệu đầy đủ, restore throughput và ứng dụng.
4. **“Chỉ cần DB tại region khác.”** Ứng dụng vẫn cần IAM, DNS, gateway, broker, secret, registry, network và monitoring.
5. **“RTO chỉ là thời gian bật server B.”** Phải tính phát hiện, quyết định, data integrity, route và chức năng kinh doanh theo contract.
6. **“Healthy nghĩa là đã phục hồi.”** TCP/HTTP health có thể qua dù nghiệp vụ tạo đơn hoặc thanh toán chưa hoạt động.
7. **“Để hai site cùng ghi sẽ tăng availability mà không có giá phải trả.”** Dễ split-brain, conflict và sai lệch dữ liệu nếu không có mô hình nhất quán.
8. **“Site DR có thể dùng quyền admin chung mà không cần kiểm soát.”** Attacker có thể phá cả hai site và vault.
9. **“Tái dùng credential của môi trường bị chiếm giúp phục hồi nhanh.”** Có thể đưa attacker vào môi trường mới và tái nhiễm.
10. **“Diễn tập tabletop chứng minh đạt RTO.”** Tabletop chỉ kiểm tra phối hợp và hiểu runbook; phải đo từ thử nghiệm khôi phục thực tế.
11. **“Sau failover cứ chuyển ngay về primary cũ.”** Failback cần đồng bộ dữ liệu, kiểm tra writer và tránh rollback giao dịch.
12. **“Một lần test đạt là đủ.”** Dung lượng, code, dữ liệu, phụ thuộc, IAM và người vận hành liên tục thay đổi.

## 14. Bài tập tình huống

Một nền tảng bán hàng có RTO 30 phút, RPO 5 phút. Kiến trúc hiện tại gồm hai availability zone trong cùng region, một replica DB bất đồng bộ sang region khác, backup ngày một lần. Site dự phòng không có KMS key giải mã snapshot, secret manager nằm tại primary, DNS chuyển thủ công và image registry chỉ có ở primary. Đội dự án báo cáo “DR ready” vì dashboard của DB báo replication lag dưới 30 giây.

**Yêu cầu phân tích:**

1. Xác định ít nhất sáu điểm lỗi chung hoặc thiếu dependency khiến site dự phòng chưa thể phục hồi.
2. Chỉ ra vì sao replication lag 30 giây chưa chứng minh RPO 5 phút.
3. Đề xuất các control ưu tiên cho KMS, secret, registry, DNS, data consistency, quyền và bảo vệ backup trước corruption/ransomware.
4. Viết một test plan ngắn bao gồm restore một recovery point nhất quán, failover chức năng, đo achieved RTO/RPO, negative test IAM và kiểm tra audit tại site B.
5. Nếu lần diễn tập mất 47 phút mới phục hồi chức năng tạo đơn và điểm dữ liệu phục hồi là 8 phút trước sự cố, ghi verdict cho RTO và RPO.
6. Đề xuất ít nhất một cách tránh split-brain và cách đối soát giao dịch trước failback.

**Gợi ý đánh giá:** RTO 47 phút vượt mục tiêu 30 phút → **FAIL**; RPO 8 phút vượt 5 phút → **FAIL**. Không đổi tiêu chí để biến kết quả thành PASS; tạo finding có owner, kế hoạch sửa và chạy lại.

## 15. Checklist kiểm tra DR architecture

- [ ] BIA xác định chức năng kinh doanh, mức chấp nhận gián đoạn và mất dữ liệu.
- [ ] RTO/RPO có phạm vi, thời điểm bắt đầu/kết thúc và tiêu chí đo cụ thể.
- [ ] Có threat model gồm lỗi vùng, lỗi control plane, corruption, ransomware và quyền bị chiếm.
- [ ] Dependency inventory bao gồm app, DB, object, broker, DNS, IAM, KMS, secrets, network, registry, monitoring và bên thứ ba.
- [ ] Mô hình backup/pilot light/warm/hot/active-active phù hợp mục tiêu và có lý do lựa chọn.
- [ ] Vùng lỗi và quyền quản trị DR được tách phù hợp với mức rủi ro.
- [ ] Backup, PITR, replica, retention, key và khả năng restore đã được kiểm tra.
- [ ] Điểm dữ liệu khôi phục được chứng minh nhất quán, có phương án đối soát.
- [ ] Có cơ chế chỉ định/fence writer, xử lý split-brain và failback.
- [ ] Capacity, quotas, artifact, IaC, IAM, secret, TLS/DNS và route tại DR được kiểm chứng.
- [ ] Kênh quan sát và log/audit tiếp tục hoạt động trong và sau failover.
- [ ] Cyber recovery có phương án khôi phục từ điểm sạch và cô lập attacker nếu cần.
- [ ] Runbook có owner, quyền quyết định, tiêu chí go/no-go, rollback và liên lạc.
- [ ] Có test theo nhiều cấp, gồm thử phục hồi thực và đo end-to-end khi claim yêu cầu.
- [ ] Evidence giữ phiên bản, timestamp, scope, recovery point, kết quả nghiệp vụ, bảo mật, consistency và reviewer.
- [ ] FAIL/INCONCLUSIVE/exception được ghi nhận thành findings và kiểm tra lại sau sửa.
- [ ] Có lịch diễn tập lại khi thay đổi kiến trúc, dữ liệu, công nghệ hoặc rủi ro.

## 16. Câu hỏi tự đánh giá

1. Vì sao multi-AZ, backup và DR không phải ba tên gọi của cùng một cơ chế?
2. Một site B chứa DB replica nhưng thiếu KMS key có được coi là đủ khả năng khôi phục không? Cần test gì?
3. Tại sao achieved RPO nên dựa trên dữ liệu có thể phục hồi nhất quán thay vì chỉ nhìn replication lag?
4. Khi một network partition khiến cả hai site nghĩ mình là primary, những control nào ngăn ghi đồng thời?
5. Một hệ thống active-active có thể vẫn không đạt yêu cầu bảo toàn dữ liệu của giao dịch tài chính vì sao?
6. Vì sao dữ liệu được replicate tốt vẫn có thể không an toàn để khôi phục sau ransomware?
7. Nếu chuyển DNS chỉ mất 30 giây nhưng ứng dụng phải 20 phút mới hoàn thành xử lý giao dịch, nên đo RTO như thế nào?
8. Tại sao failback cần test và decision record riêng?
9. Những bằng chứng nào chứng minh security baseline ở site DR còn hiệu lực khi môi trường chính bị xâm nhập?
10. Hãy chọn một hệ thống quen thuộc, viết BIA ngắn, sơ đồ dependency, DR strategy và năm test case có tiêu chí PASS/FAIL.

**Điểm cốt lõi:** DR architecture là khả năng phục hồi **một dịch vụ kinh doanh hoàn chỉnh với dữ liệu nhất quán và bảo mật có thể kiểm chứng**. Sự hiện diện của backup, replica hoặc region thứ hai chỉ là bước đầu; security assurance cần các mục tiêu RTO/RPO rõ ràng, phân tách vùng lỗi và quyền quản trị, thử nghiệm failover/failback, kiểm tra dữ liệu, quan sát bảo mật và bằng chứng đủ để reviewer độc lập xác định điều gì đã đạt, điều gì chưa đạt.

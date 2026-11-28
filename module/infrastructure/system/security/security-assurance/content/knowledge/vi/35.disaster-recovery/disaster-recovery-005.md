# Failover trong Disaster Recovery: Chuyển đổi sang hệ thống dự phòng an toàn và có bằng chứng

Khi một vùng cloud, cụm cơ sở dữ liệu hoặc trung tâm dữ liệu ngừng hoạt động, dịch vụ có thể cần chuyển sang hệ thống dự phòng để tiếp tục phục vụ người dùng. Thao tác này thường được gọi là **failover**. Tuy nhiên, việc đưa lưu lượng tới một máy chủ hoặc vùng khác **không tự chứng minh hệ thống đã phục hồi an toàn**: dữ liệu dự phòng có thể chậm đồng bộ, hai phía có thể cùng nhận ghi, tài khoản quản trị bị xâm phạm có thể còn truy cập được vùng mới, hoặc hệ thống giám sát không theo kịp sau khi chuyển.

**Failover** là quá trình chuyển quyền phục vụ của một thành phần, dịch vụ hoặc hệ thống từ phía đang đảm nhận (*primary/active*) sang phía thay thế (*standby/secondary/alternate*) khi xảy ra lỗi, suy giảm nghiêm trọng hoặc theo kế hoạch. Mục tiêu là giảm thời gian gián đoạn trong phạm vi yêu cầu về năng lực, dữ liệu, bảo mật và rủi ro được phê duyệt.

Trong chương **Disaster recovery** của module **SECURITY_SECURITY_ASSURANCE**, chủ đề Failover không dừng ở thao tác cấu hình DNS hoặc nút “promote secondary”. Security assurance cần chứng minh rằng **đúng điều kiện đã kích hoạt chuyển đổi; hệ thống đích đáp ứng tiêu chí an toàn; dữ liệu, quyền và giao dịch giữ được tính toàn vẹn; kết quả RTO/RPO được đo; và quyết định quay lại hoặc tiếp tục vận hành có người chịu trách nhiệm**.

Sau bài học, người học có thể lựa chọn mô hình failover phù hợp; phân tích rủi ro dữ liệu và split-brain; thiết kế runbook chuyển đổi theo từng gate; thu thập bằng chứng phục hồi; kiểm thử trong các kịch bản mất dịch vụ và xâm nhập; đồng thời lên kế hoạch failback mà không làm mất tính nhất quán.

## 1. Vai trò của Failover trong Disaster Recovery

Trong một hệ thống phân tán, thành phần chính có thể mất khả dụng vì sự cố hạ tầng, mất nguồn điện, lỗi mạng, cấu hình sai, giới hạn tài nguyên, thao tác vận hành hoặc tấn công mạng. Failover cho phép chuyển sang thành phần có khả năng tiếp tục cung cấp dịch vụ khi thành phần chính không còn đáng tin hoặc không thể đáp ứng yêu cầu.

~~~mermaid
flowchart LR
    U["Người dùng / client"] --> R["DNS / Global LB / traffic router"]
    R -->|Trạng thái bình thường| P["Primary: ứng dụng + dữ liệu"]
    R -.->|Khi chuyển đổi| S["Secondary: ứng dụng + dữ liệu"]
    P -->|Sao chép / đồng bộ| S
    H["Health checks + DR decision"] --> R
    H --> P
    H --> S
~~~

Sơ đồ minh họa luồng tổng quát; trong thực tế, primary và secondary có thể cùng vùng, khác vùng, khác region, khác account hoặc khác trung tâm dữ liệu. Đường sao chép dữ liệu, cách xác định primary duy nhất và điều kiện truy cập thay đổi theo sản phẩm.

### Phân biệt các khái niệm

| Khái niệm | Mục tiêu | Điểm cần lưu ý |
|---|---|---|
| **High Availability (HA)** | Giảm gián đoạn khi một thành phần lỗi trong phạm vi thiết kế. | Có thể tự failover giữa node/zone; chưa chắc xử lý được mất cả region hoặc lỗi chung về danh tính. |
| **Failover** | Chuyển quyền phục vụ hoặc lưu lượng sang thành phần thay thế. | Có thể tự động hoặc thủ công, planned hoặc unplanned; cần kiểm tra dữ liệu và quyền. |
| **Disaster Recovery (DR)** | Phục hồi công nghệ, dữ liệu và năng lực vận hành sau gián đoạn lớn. | Failover là một chiến lược DR, không thay thế toàn bộ kế hoạch DR. |
| **Business Continuity (BC)** | Duy trì hoạt động nghiệp vụ tối thiểu khi điều kiện bình thường bị phá vỡ. | Có thể cần quy trình thủ công hoặc giảm mức dịch vụ khi failover kỹ thuật chưa khả thi. |
| **Failback** | Chuyển quyền phục vụ từ môi trường thay thế về primary cũ hoặc primary mới được xác minh. | Cần đồng bộ lại dữ liệu, kiểm tra an toàn và kế hoạch cắt chuyển riêng. |
| **Backup/restore** | Lưu và phục hồi bản sao dữ liệu từ một điểm theo thời gian. | Replication có thể mang lỗi/xóa dữ liệu sang secondary; bản sao lưu độc lập vẫn cần thiết. |
| **Switchover** | Chuyển đổi chủ động theo kế hoạch khi cả hai phía có thể điều phối. | Thường có điều kiện bảo đảm đồng bộ tốt hơn, nhưng vẫn cần kiểm tra toàn tuyến. |

**Failover thành công về hạ tầng không tương đương phục hồi nghiệp vụ.** Cụm database có thể promote secondary thành công nhưng ứng dụng vẫn dùng connection string cũ; DNS đã thay nhưng client còn cache; API phản hồi HTTP 200 nhưng chức năng thanh toán không ghi giao dịch.

## 2. Các mô hình triển khai Failover

### 2.1. Active–passive

Trong mô hình **active–passive**, primary xử lý lưu lượng bình thường; standby được chuẩn bị để nhận trách nhiệm khi primary lỗi hoặc có quyết định chuyển đổi.

~~~text
Bình thường:
  Client -> Primary (active) --replication--> Secondary (standby)

Khi sự cố:
  Client -> Secondary (promoted active)
            Primary (fenced / isolated)
~~~

Mức chuẩn bị của standby quyết định thời gian phục hồi: hệ thống đã chạy và đồng bộ dữ liệu thường chuyển nhanh hơn một môi trường chỉ có template và bản sao lưu. Đổi lại, hạ tầng chờ có chi phí và cần kiểm tra định kỳ để tránh trạng thái lỗi thời.

### 2.2. Active–active

Trong mô hình **active–active**, nhiều thành phần đồng thời phục vụ một phần hoặc toàn bộ lưu lượng. Khi một phía mất khả dụng, phía còn lại nhận tải.

Đây không phải mô hình tự động an toàn cho mọi ứng dụng. Với dữ liệu có ghi ở nhiều nơi, cần xác định quy tắc consistency, conflict resolution, partitioning, phiên bản giao dịch và nơi nào được phép ghi. Nếu hai vùng cùng sửa cùng một bản ghi, chiến lược “last write wins” có thể làm mất cập nhật hợp lệ. Active–active phù hợp với một số workload có phân vùng dữ liệu hoặc cơ chế đồng bộ được thiết kế, nhưng không thể giả định mọi database sẽ giải quyết xung đột đúng nghiệp vụ.

### 2.3. Hot, warm và cold standby

| Mức standby | Đặc trưng | Đánh đổi thực tế |
|---|---|---|
| **Hot** | Hạ tầng và dịch vụ đích đã vận hành, dữ liệu được cập nhật theo cơ chế đồng bộ. | Chuyển nhanh hơn nhưng chi phí cao hơn; phải duy trì patch, quyền và giám sát liên tục. |
| **Warm** | Có hạ tầng/cấu hình cơ bản, có thể cần mở rộng, deploy hoặc đồng bộ trước khi phục vụ. | Cân bằng chi phí và thời gian; nhiều bước thủ công/tự động cần diễn tập. |
| **Cold** | Chủ yếu có kế hoạch, artifact, backup hoặc khả năng dựng tài nguyên theo nhu cầu. | Chi phí thường thấp hơn, nhưng phục hồi có thể mất nhiều thời gian và phụ thuộc khả năng cấp phát/quota. |

Đây là các mô tả định tính, không phải mốc RTO/RPO cố định cho tất cả hệ thống. Một hot standby không có đủ kết nối tới nhà cung cấp thanh toán hoặc thiếu khóa giải mã vẫn có thể không đáp ứng RTO.

### 2.4. Tự động và thủ công

- **Automatic failover** thích hợp khi điều kiện lỗi xác định rõ, hệ thống có cơ chế tránh hai primary, mức ảnh hưởng của chuyển sai được kiểm soát và môi trường đích đủ tin cậy.
- **Manual/approved failover** phù hợp với sự cố phức tạp, nghi bị xâm nhập, rủi ro mất dữ liệu cao hoặc cần ưu tiên nghiệp vụ. Phải xác định ngưỡng kích hoạt, người quyết định và quy trình thay thế khi người chính không liên lạc được.
- **Semi-automatic failover** cho phép hệ thống chuẩn bị bằng chứng và đề xuất chuyển đổi, nhưng cần phê duyệt tại gate quan trọng như promote database hoặc mở lưu lượng ghi.

**Tự động hóa không nên vượt qua gate bảo mật chỉ vì health check báo primary mất kết nối.** Ví dụ, nếu sự cố có dấu hiệu ransomware, hệ thống dự phòng có thể chứa dữ liệu đã bị mã hóa hoặc cùng credential bị lộ; phải đánh giá độ tin cậy trước khi promote.

## 3. Định nghĩa mục tiêu trước khi chọn chiến lược

Bước đầu của DR là đối chiếu **Business Impact Analysis (BIA)**, yêu cầu an toàn và bản đồ phụ thuộc. Mỗi dịch vụ có thể có mục tiêu khác nhau; không nên áp một cấu hình failover cho tất cả.

| Yêu cầu | Diễn giải | Cách chứng minh |
|---|---|---|
| **RTO — Recovery Time Objective** | Thời gian mục tiêu để dịch vụ/phần chức năng đạt mức phục vụ đã định nghĩa sau gián đoạn. | Timeline từ mốc được quy định đến lúc nghiệp vụ được nghiệm thu; không lấy thời điểm VM lên làm kết quả cuối. |
| **RPO — Recovery Point Objective** | Mức mất dữ liệu theo thời gian tối đa mà tổ chức hướng tới cho dữ liệu được bảo vệ. | Vị trí/điểm khôi phục, replication lag, giao dịch đã xác nhận và kết quả đối soát. |
| **MBCO — Minimum Business Continuity Objective** | Mức dịch vụ hoặc năng lực kinh doanh tối thiểu được chấp nhận. | Tỷ lệ giao dịch, chức năng thiết yếu, độ chính xác và xác nhận của owner. |
| **Giới hạn rủi ro bảo mật** | Những điều kiện không được bỏ qua khi chuyển vùng/host. | Kiểm tra IAM, network, keys, logging, dấu hiệu xâm nhập và phê duyệt ngoại lệ. |
| **Khả năng duy trì standby** | Năng lực đích chịu tải trong thời gian phụ thuộc còn gián đoạn. | Capacity test, quota, license, nhân sự và chi phí vận hành. |

Ví dụ minh họa: hệ thống đặt hàng được phê duyệt **RTO 30 phút** và **RPO 5 phút**. Sau khi xảy ra gián đoạn vào 10:00, nhóm DR chuyển được traffic tới secondary lúc 10:12 nhưng luồng đặt hàng chính chỉ hoạt động và được xác minh lúc 10:19. Thời gian khôi phục nghiệp vụ là **19 phút** nếu mốc khởi đầu được quy định là 10:00. Không báo “12 phút” chỉ vì traffic router đã đổi.

Nếu secondary chỉ có trạng thái đồng bộ được xác nhận đến 09:56, khoảng lùi danh nghĩa so với thời điểm gián đoạn là 4 phút. Tuy nhiên, **không đủ kết luận RPO đã đạt** nếu chưa biết các ghi đã ACK cho khách hàng trong khoảng 09:56–10:00 có tồn tại ở secondary hoặc đã được đối soát qua transaction/event log. RPO phải được đánh giá trên **dữ liệu thực tế có ý nghĩa nghiệp vụ**, không chỉ một giá trị lag trên dashboard.

### Thứ tự ưu tiên và phụ thuộc

Một ứng dụng có thể phụ thuộc vào nhiều lớp:

~~~text
Client
  -> DNS / Global Load Balancer / API Gateway
    -> IdP / chứng chỉ TLS / session / secret
      -> Ứng dụng và message queue
        -> Cơ sở dữ liệu và kho object
          -> KMS / khóa mã hóa
            -> Logging, monitoring, backups và đối tác
~~~

Nếu chỉ dự phòng ứng dụng mà không có IdP hoặc khóa để giải mã dữ liệu ở vùng đích, failover không hoàn tất. Dependency map phải bao gồm các dịch vụ và đường kết nối bên ngoài, nguồn quản trị, quy trình triển khai, account/billing/quota và các vai trò ra quyết định.

## 4. Dữ liệu, replication và bài toán split-brain

**Rủi ro quan trọng nhất của failover có ghi dữ liệu là mất tính nhất quán.** Cần xem xét cả cơ chế sao chép, cách xác nhận ghi thành công và quyền primary.

### 4.1. Synchronous và asynchronous replication

| Cơ chế | Đặc trưng | Rủi ro/đánh đổi |
|---|---|---|
| **Synchronous replication** | Một thao tác ghi chỉ được xác nhận theo các điều kiện đồng bộ mà hệ thống đặt ra. | Có thể giảm nguy cơ mất dữ liệu được ACK nhưng tăng độ trễ; khả năng tiếp tục ghi khi mất liên lạc phụ thuộc consensus/quorum. |
| **Asynchronous replication** | Primary có thể ACK trước khi secondary nhận hoặc áp dụng ghi. | Giảm độ trễ ở đường ghi, nhưng khi primary lỗi có thể mất các ghi chưa kịp replicate. |
| **Snapshot/backup định kỳ** | Tạo bản sao tại những mốc thời gian, có thể dùng để restore. | Thường có khoảng dữ liệu không nằm trong snapshot và thời gian restore đáng kể. |

Đừng suy luận rằng “synchronous” luôn đồng nghĩa RPO = 0 trong mọi tình huống. Cần đọc đúng cam kết, phạm vi ACK, số bản sao, mô hình failure và trường hợp dữ liệu nằm ngoài cơ chế replication (ví dụ object, queue hoặc transaction của bên thứ ba).

**Replication không thay thế backup.** Một lệnh xóa nhầm, cấu hình sai hoặc dữ liệu bị mã hóa có thể được replicate tới secondary; backup được phân quyền/bảo vệ độc lập và kiểm tra restore vẫn cần theo mức rủi ro.

### 4.2. Split-brain là gì?

**Split-brain** xảy ra khi hai phía cùng tin mình là primary và cho phép các hành động không tương thích, thường vì mất liên lạc hoặc cơ chế bầu leader không bảo đảm an toàn. Với database, hậu quả là phát sinh hai nhánh dữ liệu khác nhau; với hệ thống khác, có thể là ghi trùng hoặc xử lý cùng công việc hai lần.

~~~text
Mất kết nối giữa hai vùng:
    Primary A  <---X--->  Secondary B

Tình huống nguy hiểm:
    Client nhóm 1 -> A ghi dữ liệu
    Client nhóm 2 -> B ghi dữ liệu
    A và B cùng nhận mình là primary

Nguyên tắc cần có:
    Fencing / lease / quorum / consensus được thiết kế phù hợp
    -> Chỉ bên được phép mới nhận ghi tại một thời điểm
~~~

**Fencing** là cơ chế ngăn một instance/node cũ tiếp tục ghi hoặc truy cập tài nguyên dùng chung sau khi quyền primary bị chuyển. Tùy hệ thống, có thể dùng fencing token tăng đơn điệu, lease được xác thực, quorum/consensus, ngăn truy cập storage hoặc tắt quyền ghi của node cũ. Cách cài đặt phải theo cơ chế hỗ trợ chính thức của nền tảng.

Không nên chỉ dựa vào health check “không ping được A” để kết luận A đã ngừng ghi. Một network partition có thể khiến B không nhìn thấy A trong khi A vẫn phục vụ một nhóm client khác. **Quorum và fencing** phải được kiểm tra bằng những kịch bản mất mạng phù hợp, không chỉ thử tắt tiến trình chính.

### 4.3. Idempotency, transaction và giao dịch giữa hệ thống

Khi chuyển đổi, client có thể gửi lại request vì timeout dù hệ thống cũ đã ghi thành công. Với thanh toán, gửi email, tạo hóa đơn và phát hàng, điều này có thể gây tác động nghiêm trọng.

Biện pháp thường dùng:

- **Idempotency key hoặc transaction ID** ổn định để cùng một yêu cầu không bị xử lý nghiệp vụ nhiều lần.
- **Transaction ledger / outbox pattern** phù hợp để ghi nhận sự kiện đã hoàn tất và những sự kiện cần phát lại.
- **Reconciliation** giữa nguồn cũ, secondary, message queue và đối tác bên ngoài trước khi mở rộng chức năng ghi.
- **Freeze hoặc hạn chế ghi có kiểm soát** khi không thể chứng minh hai phía không xung đột.
- **Điều kiện xử lý retry** và thời hạn lưu idempotency key theo tính chất nghiệp vụ.

Không áp dụng cách “replay toàn bộ queue” mà không kiểm tra liệu consumer cũ đã thực hiện hành động bên ngoài hay chưa. Bằng chứng ACK từ broker không tự chứng minh giao dịch thanh toán đã hoàn tất hoặc chưa hoàn tất ở nhà cung cấp.

### 4.4. Đo dữ liệu mất thực tế

Phân biệt:

1. **Replication lag:** độ trễ quan sát tại các thành phần sao chép.
2. **Last durable/verified commit:** giao dịch hoặc log position đã được ghi bền vững/áp dụng ở secondary theo cơ chế xác minh.
3. **Client-acknowledged writes:** các giao dịch đã được xác nhận với khách hàng nhưng có thể chưa tới secondary.
4. **Business data loss:** dữ liệu hoặc trạng thái nghiệp vụ thực sự bị mất, thiếu hoặc cần tái xử lý sau failover.

Để kết luận RPO, cần thống nhất cách đo và đối soát các nguồn theo yêu cầu nghiệp vụ. Khi còn chưa biết, ghi **INCONCLUSIVE** thay vì dùng giá trị lag làm bằng chứng duy nhất.

## 5. Nhận biết lỗi và quyết định kích hoạt

Để tránh chuyển đổi không cần thiết, phải xác định **tín hiệu phát hiện và điều kiện kích hoạt**. Một cổng HTTP không phản hồi có thể do network path cụ thể bị lỗi, trong khi database và dữ liệu vẫn phục vụ ở kênh khác.

Các tín hiệu có thể gồm: lỗi kết nối từ nhiều điểm quan sát, health check nghiệp vụ, tình trạng quorum, số replica hoạt động, độ trễ và error rate, cảnh báo của CSP, tình trạng storage, dịch vụ định danh, replication lag và kết quả kiểm tra synthetic transaction.

### Bảng điều kiện quyết định

| Tình huống | Câu hỏi trước khi failover | Quyết định hướng tới |
|---|---|---|
| Một instance ứng dụng lỗi | Tải có được chuyển tự động qua các instance khỏe trong vùng? | Có thể xử lý ở HA, chưa cần DR toàn vùng. |
| Mất một availability zone | Secondary ở zone khác có đáp ứng dữ liệu/capacity và cơ chế leader không? | Dùng failover theo topology đã thử. |
| Mất region | Router/IdP/KMS/DNS/quota ở vùng đích có sẵn không? Trạng thái replicate đến đâu? | Kích hoạt DR có kiểm tra dữ liệu và gate an toàn. |
| Mạng giữa hai vùng bị phân vùng | Primary cũ còn ghi không? Có cơ chế quorum/fencing? | Ngăn split-brain trước khi promote thứ cấp. |
| Nghi bị ransomware/chiếm quyền | Secondary có cùng tài khoản, khóa hoặc dữ liệu bị tác động không? | Có thể cần containment và clean recovery, không tự động promote. |
| Sự cố do cấu hình/triển khai | Lỗi đó đã replicate sang standby hoặc IaC dùng chung chưa? | Xác minh baseline của đích trước khi mở traffic. |

Khi tự động hóa, cần **debounce/hysteresis** hoặc logic quan sát đủ tin cậy để tránh dao động liên tục giữa hai phía (*flapping*). Tuy nhiên, thời gian xác nhận quá dài cũng ảnh hưởng RTO. Quy tắc phải xuất phát từ mức rủi ro, mô hình lỗi và phép thử thực tế.

### Khi nào cần quyết định con người?

Một số trường hợp cần approval của Incident Lead, Data Owner hoặc Business Owner trước khi chuyển: dự kiến mất dữ liệu cao hơn RPO, chưa thể xác nhận fencing, chỉ còn một bản sao dữ liệu, đích có dấu hiệu xâm nhập hoặc lưu lượng sản xuất sẽ bị xử lý ở vùng địa lý khác chưa được phê duyệt.

Trong khẩn cấp, quy trình cần nêu **quyền quyết định và người thay thế**, không yêu cầu phê duyệt mơ hồ khiến DR bị treo vì không liên lạc được ai.

## 6. Chuẩn bị sẵn sàng trước thảm họa

Failover chỉ nhanh và đáng tin khi các điều kiện chuẩn bị được duy trì thường xuyên.

### 6.1. Đồng bộ cấu hình và phiên bản

Kiểm tra primary và standby về:

- Infrastructure as Code, network, firewall, route, DNS, load balancer, private endpoint.
- Operating system, runtime, database engine, schema, extension và phiên bản ứng dụng.
- IAM/SSO, service account, secret rotation, KMS/key policy, certificate.
- Log collector, audit source, SIEM connector, alert routing và quyền truy cập bằng chứng.
- Backup, restore point, khả năng giải mã và điều kiện data residency.
- License, quota, reserved capacity, autoscaling, dependency của nhà cung cấp ngoài.
- Các ràng buộc khi chuyển: session state, cache, message queue, cron job và scheduled task.

Một standby vẫn có thể dùng code phiên bản cũ dù đã replicate database mới. Nếu schema đã thay đổi không tương thích, ứng dụng dự phòng có thể gây lỗi dữ liệu khi nhận traffic. Cần có kiểm tra tương thích trước khi deploy và cơ chế cảnh báo config drift.

### 6.2. Kiểm tra tính độc lập

Hai vùng cloud có thể vẫn dùng chung **account quản trị, DNS, IdP, network transit, certificate authority hoặc nguồn secrets**. Nếu điểm chung bị lỗi hoặc bị chiếm, dự phòng theo địa lý chưa đủ.

Bản đồ shared dependency nên nêu: thành phần chung, hậu quả khi mất, biện pháp thay thế, người sở hữu, cách kiểm thử và giới hạn thực tế. Chỉ mô tả “multi-region” không chứng minh khả năng chịu sự cố của toàn bộ chuỗi nghiệp vụ.

### 6.3. Duy trì bằng chứng về readiness

Theo lịch hoặc sau thay đổi trọng yếu, cần đo:

- Các health checks thiết yếu ở standby.
- Replication status, backlog và consistency check có ý nghĩa.
- Khả năng dùng keys và secrets tại đích theo đúng quyền.
- Capacity, quota và kết quả thử tải đại diện.
- Hiệu lực guardrail bảo mật, cấu hình IAM/network và bản vá.
- Đường log/audit và cảnh báo bảo mật tại secondary.
- Các bản runbook, liên hệ khẩn, kênh ngoài băng và quyền truy cập DR.

Một standby đã được dựng từ năm trước nhưng không có bằng chứng kiểm tra gần đây là một **giả định phục hồi**, không phải một khả năng đã được chứng minh.

## 7. Runbook Failover từng bước và điều kiện an toàn

Quy trình dưới đây là khung tổng quát; thao tác thực tế phải được chuyển thành runbook sản phẩm cụ thể, có người thực hiện và phương án dừng.

~~~mermaid
flowchart TD
    A["Sự cố / ngưỡng DR được xác nhận"] --> B["Đánh giá phạm vi, RTO/RPO và an toàn"]
    B --> C{"Đủ điều kiện kích hoạt?"}
    C -->|Chưa| D["Containment, điều tra, phương án dịch vụ hạn chế"]
    D --> B
    C -->|Có| E["Fencing / bảo đảm primary cũ không ghi"]
    E --> F["Xác minh dữ liệu + promote secondary"]
    F --> G["Xác minh IAM, secrets, network, logging"]
    G --> H{"Gate chức năng và bảo mật đạt?"}
    H -->|Không| I["Giữ hạn chế, sửa lỗi, không mở rộng traffic"]
    I --> G
    H -->|Có| J["Chuyển traffic theo giai đoạn"]
    J --> K["Đo nghiệm thu, dữ liệu, alert và tải"]
    K --> L{"Đạt RTO/RPO/MBCO và an toàn?"}
    L -->|Không| M["Ghi finding, giảm dịch vụ hoặc chuyển phương án khác"]
    M --> K
    L -->|Có| N["Bàn giao vận hành tại site dự phòng"]
~~~

### Bước 1 — Tạo bản ghi sự kiện và chốt phạm vi

Ghi Incident/DR event ID, thời điểm được quy định làm mốc bắt đầu, dịch vụ/khách hàng bị ảnh hưởng, các vùng hiện tại, nguồn dữ liệu đã kiểm tra và tiêu chí lựa chọn failover. Xác nhận BIA, RTO/RPO, phụ thuộc và người có thẩm quyền.

Nếu sự cố an ninh đang được điều tra, phối hợp bảo toàn log, snapshot và bằng chứng liên quan trước khi có hành động phá hủy. Không xóa một primary nghi nhiễm chỉ để làm nhanh recovery khi chưa tuân thủ quy trình điều tra.

### Bước 2 — Đánh giá trạng thái standby và rủi ro dữ liệu

Kiểm tra secondary thực sự có sẵn, ứng dụng tương thích, cấu hình đáp ứng baseline và các keys cần thiết dùng được. Đối chiếu replication position và xác định những giao dịch có thể thiếu. Nếu mất dữ liệu dự kiến vượt RPO hoặc chưa thể xác minh phạm vi, ghi rõ giới hạn và yêu cầu quyết định từ chủ dữ liệu/kinh doanh.

Với active–active, kiểm tra phân vùng dữ liệu và chiến lược giải quyết xung đột; không giả định tăng traffic tới một bên sẽ tự giải quyết mọi ghi đang diễn ra bên kia.

### Bước 3 — Ngăn split-brain và cô lập primary cũ

Trước khi promote secondary thành nơi có quyền ghi, bảo đảm **primary cũ không thể tiếp tục ghi xung đột**, bằng cơ chế quorum/fencing/lease/consensus do nền tảng hỗ trợ. Kiểm tra các đường truy cập còn tồn tại từ client và tiến trình nền (cron, queue consumer, worker), không chỉ cân bằng tải phía trước.

Nếu không thể chứng minh fencing, không tự động khởi động hai phía cùng ghi; chuyển sang phương án hạn chế hoặc yêu cầu quyết định rủi ro phù hợp với thiết kế, đồng thời thực hiện bước kỹ thuật kiểm soát xung đột.

### Bước 4 — Promote secondary và kích hoạt ứng dụng

Thực hiện promote/switchover theo runbook đã thử. Xác minh trạng thái leader, transaction log/replication position, schema, kết nối database, secret và application readiness. Nếu cần replay hoặc reconcile, xử lý trước chức năng ghi liên quan.

Mọi thao tác cần log: người thực hiện, công cụ, lệnh/operation ID, thời gian bắt đầu/kết thúc và kết quả; không đưa token hoặc mật khẩu vào báo cáo.

### Bước 5 — Chuyển lưu lượng và phụ thuộc

Thay đổi route/DNS/global LB hoặc endpoint service discovery theo cơ chế đã xác định. Kiểm tra:

- DNS TTL thực tế, cache resolver/client, kết nối giữ lâu và thời gian session hết hạn.
- Chứng chỉ TLS, hostname, CORS/redirect/callback URL, WAF/firewall, rate limit.
- Kết nối private network, VPN, peering, allowlist của đối tác và IP egress ở vùng mới.
- IdP/MFA, session, secret/keys và quyền dịch vụ liên quan.
- Đường truy vấn/ghi database, queue consumers, background job và storage.
- Log từ vùng đích, alert routing và công cụ giám sát có khả năng dùng được.

TTL thấp chỉ là một yếu tố; **không thể bảo đảm toàn bộ client lập tức dùng đích mới**. Một số ứng dụng có connection pool hoặc cache DNS riêng, và các tác vụ nền có thể vẫn gọi primary cũ. Cần có kiểm chứng từ nhiều điểm quan sát.

### Bước 6 — Nghiệm thu theo lớp

Chia kiểm tra thành:

1. **Infrastructure:** endpoint, route, leader, số replica, quota/capacity, health của các node.
2. **Data:** tính nhất quán, các ghi đã ACK, backlog, điểm restore và độ lệch dữ liệu thực tế.
3. **Security:** IAM, TLS, secrets, audit, logging, detection, cấu hình bảo mật và nghi vấn xâm nhập.
4. **Application:** đăng nhập, đọc/ghi, các nghiệp vụ chính, tích hợp đối tác và tính idempotent.
5. **Business:** MBCO, tác động khách hàng, thời gian nghiệm thu và tình trạng giao dịch cần đối soát.

Một HTTP 200 không chứng minh đã đạt RTO của nghiệp vụ. Nếu chỉ có chức năng đọc an toàn, có thể phục vụ read-only theo phê duyệt riêng và giữ chức năng ghi ở trạng thái **NO-GO** cho tới khi dữ liệu đáng tin.

### Bước 7 — Theo dõi và bàn giao

Sau failover, giám sát tăng cường error rate, latency, replication, security alert, sự kiện truy cập trái phép, chi phí/capacity, queue backlog và đối soát dữ liệu. Cập nhật danh mục tài sản, contact tree, runbook và trạng thái backup của primary mới. Quyết định failback phải được lên kế hoạch riêng, không mặc định ngay khi primary cũ “ping được”.

## 8. Security assurance gates trước và sau Failover

Một chương trình assurance nên định nghĩa tiêu chí có thể kiểm tra, có evidence và người xác nhận.

| Gate / Control ID ví dụ | Mục tiêu | Điều kiện và bằng chứng |
|---|---|---|
| **DR-FOV-01: Scope** | Mọi dịch vụ, asset và dependency liên quan được nhận diện. | BIA, dependency map, danh mục primary/secondary, cloud account, mạng, đối tác, giới hạn coverage. |
| **DR-FOV-02: Trigger** | Failover được kích hoạt theo dấu hiệu/điều kiện đã phê duyệt. | Health timeline, incident record, decision log và người phê duyệt. |
| **DR-FOV-03: Exclusive writer** | Tránh hai primary ghi dữ liệu xung đột. | Quorum/lease/fencing state, kết quả thử network partition, write-path test. |
| **DR-FOV-04: Data integrity** | Dữ liệu trong phạm vi được phục hồi và đối soát phù hợp RPO. | Replication positions, transaction logs, consistency checks, reconciliation, xác nhận của Data Owner. |
| **DR-FOV-05: Trusted destination** | Đích đáp ứng baseline an ninh, đúng mã và quyền. | Image/artifact version, IaC, IAM/network review, patch, secrets và findings còn mở. |
| **DR-FOV-06: Observability** | Có thể quan sát, phát hiện và điều tra hoạt động trên secondary. | Audit source config, synthetic event, SIEM ingest, alert/ticket, monitoring health. |
| **DR-FOV-07: Business readiness** | Mức dịch vụ và thời gian thực tế đáp ứng điều kiện nghiệm thu. | Smoke/integration tests, throughput, error rate, RTO/MBCO được tính có timestamp. |
| **DR-FOV-08: Controlled rollout** | Traffic chuyển an toàn, có ngưỡng dừng và kế hoạch rollback/containment. | Change/runbook, canary result, decision log, trạng thái route, owner trực. |
| **DR-FOV-09: Evidence** | Quy trình có thể tái hiện và giải trình. | Event ID, phiên bản tài liệu, danh mục bằng chứng, người ký và lịch retest. |
| **DR-FOV-10: Failback readiness** | Việc quay về primary được kiểm soát và không gây mất dữ liệu. | Kế hoạch resync, consistency check, target health, test và phê duyệt riêng. |

Đây là các control ID **minh họa**, không phải mã chính thức của một tiêu chuẩn. Tiêu chí thực tế cần dựa trên rủi ro, sản phẩm và BIA được phê duyệt.

### Phân loại trạng thái

- **PASS:** có bằng chứng đúng phạm vi, còn phù hợp tại thời điểm đánh giá, chứng minh tiêu chí đã đạt.
- **FAIL:** bằng chứng cho thấy điều kiện không đạt, như thiếu fencing, dữ liệu không nhất quán hoặc thiếu logging bắt buộc.
- **INCONCLUSIVE:** chưa đủ bằng chứng, nguồn giám sát mất tín hiệu hoặc chưa xác minh những ghi chưa replicate.
- **NOT_APPLICABLE:** kiểm soát thực sự không thuộc phạm vi và lý do đã được chấp thuận.

Nếu có ngoại lệ được chấp nhận để vận hành tạm thời, **giữ nguyên kết luận kỹ thuật** (ví dụ FAIL hoặc INCONCLUSIVE), đồng thời gắn hồ sơ risk acceptance, giới hạn sử dụng, owner và ngày hết hạn. Không dùng quyết định nghiệp vụ làm bằng chứng kỹ thuật giả.

## 9. Kiểm thử Failover: Diễn tập có kiểm soát và đo lường

Một runbook chưa được thực thi chỉ chứng minh kế hoạch tồn tại, không chứng minh failover có thể đạt mục tiêu. Kiểm thử phải bao gồm điều kiện lỗi thực tế đủ đại diện và diễn tập cách ra quyết định.

### 9.1. Mức kiểm thử

| Mức | Nội dung | Giá trị và giới hạn |
|---|---|---|
| **Walkthrough / tabletop** | Đi qua kịch bản, quyền kích hoạt, hậu quả dữ liệu, liên hệ và hành động theo runbook. | Xác định khoảng trống trách nhiệm; không đo chính xác thời gian chuyển thực tế. |
| **Component test** | Thử promote một replica, DNS routing hoặc chuyển traffic trên môi trường được phép. | Kiểm tra từng lớp; chưa đại diện toàn bộ chuỗi nghiệp vụ. |
| **Planned switchover** | Chủ động điều phối chuyển đổi khi primary còn liên lạc và có thể quiesce writes. | Kiểm tra đường chuyển có kiểm soát; thường dễ hơn sự cố mất kết nối bất ngờ. |
| **Unplanned failover simulation** | Mô phỏng sự cố primary/zone, mất đường mạng hoặc dependency trong phạm vi an toàn. | Kiểm tra phát hiện, fencing và thời gian thực tế; cần giới hạn ảnh hưởng. |
| **End-to-end DR exercise** | Kiểm tra từ kích hoạt đến nghiệm thu nghiệp vụ, dữ liệu, an ninh và bàn giao. | Gần với mục tiêu nhất nhưng đòi phối hợp nhiều nhóm và nguồn lực. |
| **Failback exercise** | Thử khôi phục tính nhất quán và chuyển lại khi đích cũ đã đáng tin. | Phát hiện rủi ro resync, rollback và split-brain mới. |

### 9.2. Thiết kế kịch bản an toàn

Một bài diễn tập tốt có:

1. **Mục tiêu đo:** RTO/RPO, mức tải, sự kiện cần quan sát, các gate an ninh.
2. **Phạm vi:** môi trường, loại dữ liệu, account/region, các hệ thống bên ngoài và điều không được động tới.
3. **Trạng thái đầu:** service topology, replication lag, backup, artifact version, quyền thực thi.
4. **Lỗi đưa vào (*inject*):** ví dụ primary API không đáp ứng, network partition có kiểm soát hoặc zone bị mô phỏng mất.
5. **Giới hạn an toàn:** người điều phối, kill switch, điều kiện dừng, rollback/containment và dữ liệu không nhạy cảm.
6. **Quan sát:** thời gian theo UTC, quorum/fencing, log, truy vấn transaction, alert, route và người ra quyết định.
7. **Kết quả:** từng tiêu chí PASS/FAIL/INCONCLUSIVE, giới hạn, findings và retest.

Thử nghiệm phải được phê duyệt theo quy trình thay đổi; không tùy ý ngắt production, tạo mất quorum hoặc xóa dữ liệu để diễn tập. Nếu dùng staging, cần ghi rõ sự khác biệt về traffic, độ trễ liên vùng, cấu hình hoặc dữ liệu với production, không suy diễn quá mức từ kết quả đó.

### 9.3. Các tình huống cần kiểm thử đặc biệt

- **Primary chết hoàn toàn:** kiểm tra detect, promote và chuyển route.
- **Network partition nhưng primary vẫn hoạt động:** kiểm tra fencing và tránh hai nguồn ghi.
- **Replication lag cao:** kiểm tra quyết định dữ liệu và điều kiện chấp nhận RPO.
- **Standby thiếu capacity/quota hoặc license:** kiểm tra scaling, giới hạn tải và thông báo.
- **DNS/IdP/KMS hoặc nhà cung cấp thứ ba không hoạt động:** kiểm tra điểm lỗi chung.
- **Failover khi secret/key bị lộ:** xác minh độ tin cậy của môi trường dự phòng, tránh lan xâm nhập.
- **Client retry giao dịch:** kiểm tra idempotency, tính nhất quán và đối soát.
- **Hệ thống logging mất tín hiệu sau chuyển:** kiểm tra pipeline và alert cho vùng mới.
- **Primary trở lại bất ngờ:** kiểm tra không tự phục vụ ghi khi secondary đang là leader.
- **Failback sau nhiều giờ chạy secondary:** kiểm tra delta dữ liệu, resync và chuyển lại có kiểm soát.

## 10. Đo hiệu quả bằng chứng và chỉ số

Một dashboard “failover successful” có thể chỉ phản ánh trạng thái của một dịch vụ cloud. Assurance cần đo từ nhiều lớp.

| Chỉ số | Cách đo | Giới hạn cần ghi |
|---|---|---|
| **Detection time** | Từ thời điểm lỗi theo định nghĩa đến khi hệ thống/người trực phát hiện. | Khác thời gian provider công bố hoặc lúc người dùng báo lỗi. |
| **Decision/activation time** | Thời gian tới quyết định kích hoạt DR được phê duyệt. | Chỉ số cần phân tích riêng nếu chậm do quyền hoặc thiếu bằng chứng. |
| **Traffic cutover time** | Thời gian đến khi router/DNS/endpoint chuyển theo kế hoạch. | Chưa chứng minh client đã chuyển hoặc nghiệp vụ hoạt động. |
| **Actual recovery time** | Từ mốc sự cố đến lúc mức dịch vụ được nghiệm thu đạt tiêu chí. | Phải dùng chính RTO scope và mốc start/end đã định nghĩa. |
| **Observed data loss / RPO achievement** | Giao dịch/trạng thái thiếu sau đối soát và độ lùi dữ liệu. | Replication lag không đủ thay cho dữ liệu được xác minh. |
| **Business capacity/MBCO** | Throughput và chức năng đang phục vụ so với ngưỡng tối thiểu. | Health xanh nhưng công suất thấp vẫn có thể FAIL. |
| **Fencing confidence** | Bằng chứng primary cũ không thể cùng ghi; kết quả các test network partition. | Không suy luận từ việc primary không ping được. |
| **Security control coverage** | Các nguồn audit, quyền, TLS, secret, guardrail hoạt động ở standby. | Cần xác minh trên vùng đang phục vụ, không chỉ template. |
| **DR test success** | Tỷ lệ mục tiêu có kiểm thử đạt trong phạm vi đã lên kế hoạch. | Không trộn bài tabletop với thử end-to-end như cùng mức bảo đảm. |
| **Open findings/recurrence** | Số vấn đề DR chưa xử lý, độ tuổi, mức rủi ro và lỗi tái phát. | Phải theo dõi owner, deadline và retest. |

Ví dụ có 12 cặp (dịch vụ, tiêu chí DR) bắt buộc; 8 cặp có bằng chứng PASS, 2 FAIL, 2 chưa thử. Khi đó **assessment coverage có kết luận = 10/12**, nhưng **số điều kiện đạt = 8/12**. Không gọi cả 12 “đạt” chỉ vì 10 điều kiện đã có kết luận.

Nếu failover diễn ra trong 15 phút nhưng 20 phút sau mới xác nhận được chức năng thanh toán, RTO nghiệp vụ phải đo theo tiêu chí thanh toán tương ứng. Tránh chỉ tính thời gian điều khiển router.

### Thời gian nào cần ghi?

~~~text
T0 = sự cố bắt đầu theo định nghĩa
T1 = cảnh báo / xác nhận lỗi
T2 = quyết định kích hoạt DR
T3 = fencing / cô lập primary cũ
T4 = promote + standby sẵn sàng
T5 = traffic chuyển, client bắt đầu truy cập
T6 = nghiệp vụ đạt tiêu chí, Security/Data/Business xác nhận

Actual recovery time = T6 - T0
~~~

Mốc T0 có thể khó xác định trong sự cố thật; cần ghi nguồn bằng chứng và mức bất định. Một báo cáo trung thực phân biệt thời gian đã quan sát, ước tính và giới hạn dữ liệu.

## 11. Failback: Quay về khi primary cũ phục hồi

**Failback không chỉ là đổi DNS ngược lại.** Khi secondary đã nhận ghi trong nhiều giờ, primary cũ có thể chứa dữ liệu thiếu hoặc mâu thuẫn. Nếu bị sự cố bảo mật, nó cũng có thể chưa đủ tin cậy.

### Điều kiện trước Failback

- Nguyên nhân lỗi trước đó được khắc phục hoặc giảm thiểu và xác minh.
- Môi trường đích đã được kiểm tra patch, cấu hình, credential, network và logging.
- Không còn đường ghi không mong muốn từ primary cũ.
- Có kế hoạch đồng bộ **từ nguồn dữ liệu đang đúng** sang đích mới, kiểm tra tính toàn vẹn và transaction.
- Đã xác định tác động schema, data migration, queue, third-party integration và cache/session.
- Có phương án dừng, rollback an toàn, phê duyệt từ người chịu trách nhiệm nghiệp vụ/dữ liệu.
- Giám sát và alert tại đích sẽ hoạt động ngay khi chuyển.

### Quy trình khái quát

1. Chốt nguồn dữ liệu authoritative đang phục vụ, xác định các delta cần đồng bộ.
2. Dựng hoặc sửa môi trường đích sạch; thiết lập replication/resync theo cơ chế hỗ trợ.
3. Kiểm tra tính nhất quán, thời gian dữ liệu và khả năng phục vụ ở đích.
4. Trong cửa sổ được duyệt, kiểm soát ghi và chuyển quyền leader bằng quorum/fencing.
5. Chuyển traffic có kiểm soát, xác minh end-to-end và các giao dịch trong khoảng chuyển.
6. Theo dõi tăng cường, thu hồi quyền tạm, cập nhật runbook và backup topology.

Nếu không có bằng chứng hai phía được đồng bộ đúng, **NO-GO** cho failback; có thể tiếp tục vận hành tại secondary với rủi ro được quản trị và kế hoạch khắc phục. Không vì “muốn sớm trở lại bình thường” mà chấp nhận hai luồng dữ liệu xung đột.

## 12. Failover trong Cloud, Database và Kubernetes

### 12.1. Cloud multi-zone/multi-region

Failover do dịch vụ cloud tự vận hành (ví dụ một số mô hình managed HA) cần được đánh giá theo cam kết dịch vụ: điều kiện trigger, phạm vi tự động, replication, phiên bản, cách kết nối lại và trách nhiệm của khách hàng. Với DR tự xây multi-region, đội kỹ thuật thường phải quản lý provisioning, dữ liệu, route, secrets, guardrails và đối tác liên quan.

Cần kiểm tra account, region, backup key, data residency và khả năng tạo tài nguyên khi một region không dùng được. Không mặc định có thể cấp phát đủ capacity tức thì nếu chỉ giữ IaC mà không có quota/reservation hoặc chiến lược thực tế.

### 12.2. Database primary/replica

Các hệ thống database có cơ chế promotion, replica và consensus khác nhau. Cần dùng hướng dẫn chính thức cho đúng sản phẩm khi chuyển leader, xử lý transaction log, synchronous/asynchronous replicas, cơ chế thay đổi endpoint và giới hạn failback. Nhiều database chỉ hỗ trợ **một writer**; việc mở nhiều writer sai cơ chế có thể làm hỏng tính nhất quán.

Kiểm tra sau promote gồm: role và quyền truy cập, schema version, log position, dữ liệu giao dịch, kết nối ứng dụng, transaction retry, backup ở vùng mới, độ trễ của các bản sao kế tiếp và mô hình fencing.

### 12.3. Kubernetes và container workload

Failover Kubernetes có thể xảy ra ở nhiều lớp: pod được lập lịch lại, service chuyển sang endpoint khỏe, node pool được thay, control plane được phục hồi hoặc một cluster/vùng khác nhận traffic. **Pod reschedule không phải DR toàn vùng**. Một cluster mới phải có namespace, policy, secrets, storage volume, ingress, log collector, network policy và cơ chế identity phù hợp.

Với stateful workloads, không được chỉ tạo lại pod ở cluster khác rồi giả định dữ liệu đã được sao chép; phải xác minh PV/storage, replication và quyền ghi theo ứng dụng. Đồng thời cần xét background jobs, queue consumers và scheduled workloads để tránh hai cluster cùng xử lý một công việc.

### 12.4. DNS, Global Load Balancing và service discovery

Routing phụ thuộc TTL, DNS cache, connection persistence, health check, chứng chỉ và khả năng phát hiện dịch vụ. Đánh giá cần nhìn **trải nghiệm của client**: có bao nhiêu client thực sự chuyển, thời gian tái kết nối, tỷ lệ lỗi và các client vẫn đi tới primary cũ. Một thay đổi DNS được xác nhận trên console không chứng minh mọi đường đi đã chuyển.

## 13. Mẫu bản ghi Failover và bằng chứng

Mẫu YAML sau là **ví dụ minh họa cho control register**, không phải cú pháp triển khai của một CSP hay công cụ DR. Mọi số liệu và tên đều giả định.

~~~yaml
dr_event:
  id: "DR-FAILOVER-EXAMPLE-005"
  service: "orders-api"
  environment: "production"
  primary: "region-a"
  secondary: "region-b"
  scenario: "primary-region-unavailable"
  baseline_version: "2026.11"

objectives:
  rto_minutes: 30
  rpo_minutes: 5
  minimum_business_service:
    - "Tra cứu đơn hàng"
    - "Tạo đơn có transaction ID không trùng"

decision:
  incident_commander: "DR Incident Lead"
  business_owner: "Orders Service Owner"
  data_owner: "Orders Data Owner"
  activated_at_utc: "2026-11-28T10:04:00Z"
  rationale: "Region chính không phục vụ, secondary đủ điều kiện thử"
  scope: "Failover có kiểm soát tại ứng dụng và database"

technical_evidence:
  primary_fencing_verified: true
  secondary_promotion_verified: true
  replication_lag_seconds_at_event: 180
  observed_last_verified_commit: "commit-marker-example-271"
  acknowledged_write_reconciliation: "PENDING"
  backup_restoration_capability_verified: true
  destination_iam_baseline_pass: true
  logging_and_alert_verified: true
  business_flow_test_pass: true

timeline:
  incident_start_utc: "2026-11-28T10:00:00Z"
  traffic_cutover_utc: "2026-11-28T10:12:00Z"
  business_ready_utc: "2026-11-28T10:19:00Z"
  actual_recovery_minutes: 19

assessment:
  rto_result: "PASS"
  rpo_result: "INCONCLUSIVE"
  overall_result: "INCONCLUSIVE"
  reason: "Chưa đối soát đủ các ghi đã ACK trước khi primary lỗi"
  current_mode: "restricted"
  next_action: "Đối soát giao dịch rồi đánh giá mở chức năng ghi"
  accountable: "Orders Service Owner"

evidence:
  - "restricted-evidence/DR-FAILOVER-EXAMPLE-005/decision-log"
  - "restricted-evidence/DR-FAILOVER-EXAMPLE-005/fencing-state"
  - "restricted-evidence/DR-FAILOVER-EXAMPLE-005/replication"
  - "restricted-evidence/DR-FAILOVER-EXAMPLE-005/transaction-reconciliation"
  - "restricted-evidence/DR-FAILOVER-EXAMPLE-005/health-and-alert"
~~~

Ở đây, thời gian phục hồi thực tế **19 phút** đáp ứng RTO 30 phút trong phạm vi kiểm thử được nêu. Nhưng lag 180 giây (3 phút) không tự chứng minh mọi ghi đã được xác nhận đều có mặt. Vì kết quả đối soát còn PENDING, đánh giá **RPO và tổng thể là INCONCLUSIVE**; không đánh dấu toàn bộ DR PASS.

### Bảo quản và truy xuất bằng chứng

Mỗi artifact nên có: event ID, asset/resource IDs, nguồn thu thập, timestamp UTC, phiên bản runbook/control, người thực hiện, giới hạn phạm vi, kết quả kiểm thử và đường dẫn đã được phân quyền. Log chứa account ID, địa chỉ, dữ liệu khách hàng hoặc secrets phải được xử lý theo chính sách bảo vệ dữ liệu. Không chép toàn bộ token, mật khẩu hay payload nhạy cảm vào báo cáo DR.

Với hệ thống do CSP/MSP vận hành, hồ sơ cần phân biệt bằng chứng khách hàng tự thu từ API với xác nhận/báo cáo mà nhà cung cấp cung cấp. Không khẳng định có thể trực tiếp kiểm tra hạ tầng mà khách hàng không có quyền quan sát.

## 14. Tình huống thực hành: Mất vùng cloud trong giờ cao điểm

Một công ty thương mại điện tử vận hành hệ thống đặt hàng gồm API, message queue, database, object storage và dịch vụ định danh. Primary ở **region A**, standby ở **region B**. Hệ thống dùng asynchronous database replication và traffic router chuyển vùng bằng một quyết định thủ công. BIA đặt RTO 30 phút, RPO 5 phút và yêu cầu giữ chức năng tạo đơn an toàn.

Trong giờ cao điểm, region A đột ngột mất kết nối với bộ phận vận hành. Region B báo database replica mới nhất có **replication lag 4 phút**. Tuy nhiên, một số khách hàng tiếp tục nhận response từ region A qua mạng của nhà cung cấp Internet khác. Hệ thống thanh toán ở cả hai vùng sử dụng cùng idempotency store đặt tại region A. Đội kỹ thuật đề nghị promote B ngay và đổi DNS để “chắc chắn đạt RTO”.

### 14.1. Câu hỏi

1. Có thể promote B thành writer ngay chỉ vì không ping được region A không?
2. Giá trị replication lag 4 phút có đủ chứng minh đạt RPO 5 phút không?
3. Khi idempotency store ở A không dùng được, rủi ro của chức năng thanh toán/tạo đơn là gì?
4. Cần những điều kiện và bằng chứng nào trước khi mở lại traffic ghi?
5. Nếu A quay trở lại sau một giờ, nên failback như thế nào?

### 14.2. Phân tích có kiểm chứng

**Bước 1 — Xác định network partition và quyền ghi.** Việc khách hàng ở một mạng khác vẫn nhận response từ A nghĩa là A có thể chưa chết hoàn toàn. Trước khi B nhận ghi, phải xác minh cơ chế leader/quorum/fencing bảo đảm A không tiếp tục xử lý ghi xung đột. Nếu không có cách làm rõ, đây là gate an toàn chưa đạt; có thể cần tạm ngừng chức năng ghi hoặc áp dụng cơ chế cô lập theo runbook.

**Bước 2 — Đánh giá dữ liệu.** Lag 4 phút là tín hiệu nguy cơ, không tự chứng minh mức mất dữ liệu thực tế. Cần xác định log/commit position được bảo toàn ở B và đối chiếu những request đã ACK cho khách hàng, bao gồm transaction đi qua queue hoặc dịch vụ đối tác. Nếu thông tin chưa đủ, kết luận RPO **INCONCLUSIVE**.

**Bước 3 — Bảo vệ thanh toán.** Khi idempotency store ở A không thể tin cậy hoặc truy cập, việc retry thanh toán ở B có nguy cơ gây trùng. Không nên mở tự động tính năng thanh toán cho đến khi có cơ chế idempotency thay thế đã được xác minh hoặc có phương án xử lý giao dịch chờ cùng quy trình reconciliation với nhà cung cấp thanh toán.

**Bước 4 — Chọn mức phục vụ tạm thời.** Nếu hệ thống read-only ở B có dữ liệu đã xác nhận phù hợp, Business Owner có thể phê duyệt chỉ cho xem trạng thái đơn theo thông báo giới hạn, trong khi chức năng ghi được dừng để bảo vệ integrity. Đây là phương án continuity có điều kiện, không phải tuyên bố đã phục hồi đầy đủ.

**Bước 5 — Đưa B vào phục vụ có kiểm soát.** Sau khi fencing, dữ liệu, identity, capacity và logging đều đạt gate liên quan, có thể promote B và chuyển traffic từng giai đoạn, đo latency/error rate, trạng thái client cache, route, các luồng tạo đơn và alert. Ghi timestamp từng gate và biên bản quyết định.

**Bước 6 — Không failback ngay khi A xuất hiện.** A có thể có những ghi không replicate sang B, còn B đã nhận ghi mới. Phải xác định nguồn authoritative, lập kế hoạch xử lý divergence, đồng bộ hoặc tái tạo A từ trạng thái được phê duyệt, xác minh consistency rồi mới thực hiện failback có kiểm soát. Tuyệt đối không để cả hai vùng cùng xử lý ghi vì “đã online”.

### 14.3. Bảng kết luận cho dữ kiện ban đầu

| Điều kiện | Tình trạng được biết | Kết quả ban đầu |
|---|---|---|
| A hoàn toàn ngừng ghi | Chưa có bằng chứng; một số client còn kết nối | **INCONCLUSIVE — NO-GO cho promote writer khi chưa có fencing an toàn**. |
| RPO 5 phút | Lag quan sát 4 phút, chưa đối soát ACK | **INCONCLUSIVE**. |
| Idempotency | Store chung tại A không khả dụng | **FAIL** đối với điều kiện thanh toán an toàn nếu không có giải pháp thay thế. |
| Secondary capacity | Chưa cung cấp số liệu | **INCONCLUSIVE**. |
| Security logging tại B | Chưa xác minh | **INCONCLUSIVE**. |
| Quyết định chuyển traffic | Chưa có phê duyệt go-live phù hợp | **Chưa thể kết luận PASS**. |

**Bài học:** Nhấn nút failover có thể làm giảm thời gian gián đoạn nhưng cũng có thể khuếch đại mất dữ liệu hoặc tạo hai primary. Cần cân bằng mục tiêu RTO với integrity, fencing, kiểm soát quyền và bằng chứng về hoạt động nghiệp vụ thực tế.

## 15. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
|---|---|---|
| Dựa vào ping/health một chiều để promote writer. | Network partition có thể gây split-brain. | Dùng fencing, quorum/lease/consensus và kiểm thử mất kết nối. |
| Coi replication lag là bằng chứng duy nhất về RPO. | Bỏ sót giao dịch đã ACK, queue, object hoặc dữ liệu đối tác. | Đối soát commit và business transactions. |
| Đồng bộ dữ liệu thay cho backup độc lập. | Xóa nhầm hoặc ransomware được replicate. | Duy trì backup bảo vệ độc lập, kiểm tra restore và vùng tin cậy. |
| Chỉ dự phòng compute mà bỏ qua IdP/DNS/KMS. | Vùng đích không khởi chạy hoặc client không thể truy cập. | Dependency map và kịch bản lỗi chung. |
| Đổi DNS rồi báo dịch vụ đã phục hồi. | Client giữ cache/connection cũ; ứng dụng/DB chưa sẵn sàng. | Kiểm tra từ nhiều điểm và các giao dịch nghiệp vụ. |
| Không dự trữ quota/capacity ở standby. | Secondary không chịu đủ tải khi chuyển. | Thử tải, kiểm tra quota, autoscaling và giới hạn. |
| Bỏ qua IAM, TLS và logging ở vùng đích. | Dịch vụ chạy nhưng không bảo mật hoặc không thể điều tra. | Security gate và synthetic audit/alert test. |
| Tự động failover trong khi nghi hệ thống bị chiếm quyền. | Dữ liệu/xâm nhập lan sang secondary. | Kích hoạt containment, xác minh độ tin cậy và quyết định rủi ro. |
| Chạy background jobs ở cả hai vùng. | Giao dịch, email, thanh toán hoặc xử lý đơn bị lặp. | Leader election, fencing, idempotency và kiểm tra consumer. |
| Quay về primary ngay khi hạ tầng có tín hiệu khỏe. | Divergent writes hoặc failback sang môi trường chưa an toàn. | Resync, data validation và failback plan riêng. |
| Chỉ chạy tabletop nhưng công bố đã đạt RTO. | Không có bằng chứng thời gian kỹ thuật/nghiệp vụ. | Thử chức năng/end-to-end trong phạm vi được phép và đo thực tế. |
| Không lưu dấu vết quyết định hoặc ngoại lệ. | Không thể giải trình mất dữ liệu, rủi ro và nguyên nhân chậm. | Incident ID, timeline, owner, approval, findings và retest. |

## 16. Checklist assurance trước khi nghiệm thu Failover

1. **BIA và phạm vi:** RTO, RPO, MBCO, primary/secondary, ứng dụng, dữ liệu và dependency đã được phê duyệt chưa?
2. **Kích hoạt:** Có bằng chứng về sự cố, nguồn health check, thời điểm và người quyết định failover không?
3. **Tính duy nhất của writer:** Có thể chứng minh primary cũ đã bị fencing hoặc quyền leader được chuyển an toàn, không split-brain không?
4. **Dữ liệu:** Có bằng chứng về replication position, những ghi đã ACK, consistency, idempotency và giao dịch cần đối soát không?
5. **Đích đáng tin:** Code, schema, image, IaC, policy, secrets, KMS, IAM và network ở standby đã được kiểm tra chưa?
6. **Phụ thuộc:** DNS, IdP, PKI, đối tác, message queue, object store và các điểm lỗi chung đã được thử trong phạm vi phù hợp chưa?
7. **Khả năng phục vụ:** Đích có quota, capacity, license, tính năng và nhân sự để duy trì mức nghiệp vụ tối thiểu không?
8. **Bảo mật:** Audit/logging, detection, quyền quản trị, TLS, monitoring và bảo vệ dữ liệu hoạt động tại vùng mới không?
9. **Chuyển lưu lượng:** Có thể xác minh từ client thực tế và các luồng nghiệp vụ, không chỉ từ màn hình điều khiển route không?
10. **Đo lường:** Mốc T0–T6, RTO/RPO thực tế và giới hạn chứng cứ đã được ghi rõ chưa?
11. **Quản trị rủi ro:** Gate FAIL/INCONCLUSIVE có owner, biện pháp bù trừ, ngoại lệ được phê duyệt có hạn và kế hoạch retest chưa?
12. **Quay về:** Failback có chiến lược resync, nguồn authoritative, fencing, cutover và nghiệm thu riêng chưa?
13. **Kiểm thử:** Runbook đã được diễn tập theo kịch bản mất node, mất vùng, mất mạng, lag dữ liệu và security incident chưa?
14. **Bàn giao:** Người vận hành, chủ dữ liệu, chủ nghiệp vụ, IR/DR lead và đối tác nhận được quyết định, bằng chứng và trạng thái hiện tại chưa?

**Failover chỉ có giá trị security assurance khi tổ chức không những chuyển được dịch vụ sang nơi dự phòng, mà còn chứng minh được dữ liệu và quyền ghi nhất quán, môi trường đích đáng tin, nghiệp vụ đạt mức phục vụ yêu cầu và mọi giới hạn hoặc rủi ro còn lại đều được ghi nhận, phê duyệt và theo dõi bằng bằng chứng.**

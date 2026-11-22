# Thiết kế failover giữa nhiều region

Một ứng dụng chạy trên Azure có thể hoạt động ổn định nhiều tháng rồi gặp sự cố mất kết nối, lỗi phụ thuộc dữ liệu hoặc gián đoạn trên phạm vi một region. Nếu toàn bộ web frontend, API và database chỉ triển khai trong một region, nhiều máy ảo hoặc nhiều instance ở cùng region vẫn không đủ để duy trì dịch vụ khi cả region không đáp ứng. **Failover giữa nhiều region** là khả năng chuyển hoạt động sang một region dự phòng hoặc một tập region còn khỏe để ứng dụng tiếp tục phục vụ trong phạm vi mục tiêu phục hồi đã thiết kế.

Bài học thuộc chương **Cân bằng tải và phân phối ứng dụng** của module **CLOUD_PROVIDERS_AZURE**. Module khám phá Microsoft Azure từ subscription, resource group và Entra ID đến mạng ảo, compute, lưu trữ, dịch vụ dữ liệu, triển khai, giám sát, bảo vệ và kiểm soát chi phí. Failover đa region kết nối tất cả các chủ đề này: phân phối lưu lượng chỉ là một phần; **dữ liệu, danh tính, cấu hình, khả năng vận hành và chi phí** mới quyết định hệ thống có phục hồi thật sự hay không.

Sau khi học, bạn có thể:

- Phân biệt high availability trong một region với disaster recovery giữa các region.
- Đặt mục tiêu **RTO** và **RPO** và đánh giá tác động của chúng lên kiến trúc.
- Lựa chọn active-passive, active-active, hot/warm/cold standby theo yêu cầu.
- So sánh **Azure Front Door**, **Azure Traffic Manager** và **cross-region Azure Load Balancer**.
- Thiết kế health probe, ưu tiên origin, định tuyến và tránh chuyển đổi qua lại liên tục.
- Xác định thứ tự failover cho ứng dụng, cơ sở dữ liệu, cache, queue và các phụ thuộc.
- Tạo runbook diễn tập, xác minh failover/failback và lập kế hoạch chi phí.

## 1. Hiểu đúng sự cố và phạm vi phục hồi

Trước khi tạo region thứ hai, hãy xác định những tình huống mà hệ thống phải chịu được:

| Tình huống | Ví dụ | Phản ứng phù hợp |
|---|---|---|
| Lỗi một instance | Một VM hoặc container không còn healthy | Load balancer nội vùng chuyển sang instance khác |
| Lỗi một Availability Zone | Một zone gặp sự cố nguồn hoặc mạng | Triển khai nhiều zone trong region nếu dịch vụ hỗ trợ |
| Lỗi một dịch vụ ứng dụng trong region | App Service hoặc backend không trả kết quả đúng | Khôi phục tại region hoặc chuyển lưu lượng khi đủ điều kiện |
| Gián đoạn rộng trong region | Nhiều thành phần mạng/compute không khả dụng | Kích hoạt region dự phòng đã chuẩn bị |
| Hỏng dữ liệu hoặc thao tác xóa nhầm | Dữ liệu bị ghi sai rồi được sao chép sang replica | Phục hồi từ backup/point-in-time, không chỉ chuyển region |
| Lỗi cấu hình triển khai trên toàn hệ thống | Bản release gây lỗi tại cả hai region | Rollback phần mềm/cấu hình; failover đơn thuần không giải quyết |
| Sự cố ở phụ thuộc toàn cục | Lỗi DNS, secret/config chung hoặc nhà cung cấp bên ngoài | Phân tích dependency và kế hoạch phục hồi riêng |

**High availability (HA)** giảm gián đoạn do các lỗi thành phần thường gặp. **Disaster recovery (DR)** tập trung khôi phục khi sự cố vượt quá khả năng HA thông thường. Triển khai nhiều Availability Zone trong một region giúp chống lỗi zone; nó không thay thế khả năng phục hồi khi region đó mất khả dụng.

Không phải mọi sự cố HTTP 500 đều là lý do chuyển region. Nếu cả hai region cùng triển khai một phiên bản lỗi, failover có thể khiến sự cố lan rộng. Một quy trình tốt phải xác định **loại sự cố**, điều kiện kích hoạt và cách quay về trạng thái ổn định.

## 2. Đặt mục tiêu RTO và RPO

Hai mục tiêu thường dùng trong thiết kế DR:

- **RTO — Recovery Time Objective:** thời gian gián đoạn tối đa mà tổ chức đặt mục tiêu cho phép trước khi dịch vụ được khôi phục.
- **RPO — Recovery Point Objective:** lượng dữ liệu tính theo thời gian mà tổ chức chấp nhận có thể mất trong một sự cố.

Ví dụ: cửa hàng trực tuyến đặt RTO **30 phút**, RPO **5 phút**. Thiết kế phải có khả năng đưa người mua trở lại đường đặt hàng trong khoảng thời gian mục tiêu và giới hạn mất dữ liệu theo ngưỡng đã chọn. Đây là mục tiêu kinh doanh, **không phải cam kết mặc định** của một dịch vụ Azure chỉ vì đã bật geo-replication.

~~~text
09:58   Bản cập nhật cuối đã đến replica dự phòng
10:00   Region chính ngừng phục vụ
10:03   Monitoring phát hiện và xác nhận sự cố
10:08   Hoàn tất chuyển quyền ghi database
10:11   Ingress chuyển traffic sang region dự phòng
10:15   Ứng dụng được xác minh phục hồi đầy đủ

RTO quan sát trong ví dụ: 10:15 - 10:00 = 15 phút
RPO quan sát trong ví dụ: 10:00 - 09:58 = 2 phút
~~~

Đây là **mốc thời gian giả định**. Trên hệ thống thật, RTO cần tính cả phát hiện, ra quyết định, chuyển dữ liệu, cập nhật đường đi, khởi động workload và kiểm tra chức năng. RPO phụ thuộc vào commit và trạng thái sao chép thực tế, có thể khác giữa các kho dữ liệu hoặc tác vụ.

### Đừng chỉ đo tốc độ đổi DNS

Một hệ thống có thể chuyển DNS trong vài phút nhưng database ở region dự phòng chưa được nâng lên primary, hoặc secret chưa được cấu hình, hoặc hàng đợi xử lý chỉ tồn tại ở region chính. Khi đó, người dùng nhìn thấy trang web nhưng không đặt hàng được: **dịch vụ chưa đạt RTO chức năng**.

Hãy định nghĩa **phục hồi hoàn toàn** bằng những kiểm tra nghiệp vụ, chẳng hạn đăng nhập, đọc giỏ hàng, tạo đơn hàng, tra cứu đơn, nhận event và gửi thông báo.

## 3. Các mô hình triển khai đa region

### Active-passive

Một region xử lý phần lớn hoặc toàn bộ traffic sản xuất; region còn lại sẵn sàng tiếp nhận khi có sự cố.

~~~text
                   Người dùng
                       |
             Global entry / routing
                       |
               Region A (active)
                 Web + API + DB
                       |
                Replication
                       |
               Region B (standby)
                 Web + API + DB
             (chưa nhận traffic chính)
~~~

Ưu điểm: đường ghi dữ liệu và điều hành đơn giản hơn, hạn chế xung đột ghi. Nhược điểm: tài nguyên dự phòng có thể nhàn rỗi và cần bảo đảm không bị thiếu năng lực xử lý trong lúc chuyển đổi.

### Active-active

Hai hoặc nhiều region phục vụ traffic đồng thời:

~~~text
                     Người dùng
                         |
                    Global routing
                    /           \
             Region A         Region B
             Web + API        Web + API
                    \           /
                  Dữ liệu và state
                 được thiết kế đa region
~~~

Ưu điểm: giảm tải theo khu vực, tận dụng hạ tầng ở nhiều region và có thể phục hồi nhanh nếu kiến trúc phù hợp. Nhược điểm: phải giải quyết **đồng bộ dữ liệu, thứ tự ghi, phân vùng khách hàng, consistency, conflict resolution** và khả năng đáp ứng tải khi mất một region.

**Active-active ứng dụng không bắt buộc đồng nghĩa active-active dữ liệu**. Bạn có thể có frontend hoạt động ở hai region nhưng một database chỉ có một primary writer, khiến một region phải truy cập dữ liệu qua mạng liên vùng.

### Cold, warm và hot standby

| Mức dự phòng | Trạng thái region phụ | Tác động thường gặp |
|---|---|---|
| **Cold standby** | Chủ yếu giữ cấu hình, image, backup và IaC; workload chưa chạy đủ | Chi phí hạ tầng thấp hơn nhưng cần nhiều bước khởi tạo, RTO dài hơn |
| **Warm standby** | Một phần dịch vụ chạy với công suất hạn chế, dữ liệu được chuẩn bị | Cân bằng chi phí và tốc độ; phải scale khi failover |
| **Hot standby** | Hạ tầng sẵn sàng nhận tải lớn, giám sát liên tục và dữ liệu đã được sao chép | RTO có thể ngắn hơn nhưng chi phí cao và cần diễn tập thường xuyên |

Tên gọi không phải SLA. Một warm standby có thể không đạt RTO nếu không đủ quota để tăng instance, còn một hot standby vẫn thất bại nếu database promotion hoặc kết nối phụ thuộc chưa được kiểm thử.

## 4. Chọn dịch vụ điều hướng traffic toàn cục

Azure có nhiều lựa chọn; **không nên coi regional load balancer là bộ chuyển region tự động**.

| Dịch vụ | Kiểu xử lý | Điểm mạnh | Giới hạn cần nhớ |
|---|---|---|---|
| **Azure Front Door Standard/Premium** | Reverse proxy HTTP/HTTPS toàn cầu tại edge, dựa trên origin group/route | Health probe, ưu tiên origin, tăng tốc và điều phối web/API; có khả năng kết hợp WAF theo tier | Phù hợp HTTP(S), không thay lớp dữ liệu hoặc phục hồi backend |
| **Azure Traffic Manager** | Định tuyến **dựa trên DNS**, các routing method như Priority, Performance, Weighted... | Thích hợp các endpoint công khai cần điều hướng DNS; giao thức của ứng dụng không bị proxy HTTP bởi Traffic Manager | Phụ thuộc TTL, cache/resolver và client; không đóng vai trò proxy trung gian |
| **Cross-region Azure Load Balancer** | Cân bằng tải Layer 4 ở phạm vi toàn cục với mô hình backend regional phù hợp | Trường hợp cần TCP/UDP theo kiến trúc LB được hỗ trợ | Không phải WAF, không áp dụng mọi backend tùy ý, cần đúng SKU/topology/region hỗ trợ |
| **Application Gateway** | Reverse proxy HTTP(S) ở cấp region | Phù hợp cân bằng tải Layer 7, TLS, WAF trong một vùng | Một Application Gateway không tự thay thế global entry cho nhiều region |
| **Regional Azure Load Balancer** | Layer 4 trong một region | Phân phối TCP/UDP cho backend thuộc topology hỗ trợ | Không tự giải quyết failover giữa hai region |

### Azure Front Door: chọn origin còn khỏe

Với Front Door, bạn cấu hình profile, endpoint, route, origin group và các origin ở region A/B. Health probes và điều kiện định tuyến giúp Front Door chọn origin đủ điều kiện. Có thể dùng **priority** để ưu tiên origin A trong thiết kế active-passive; cân nhắc **weight** và **latency** cho thiết kế phân phối tải khi các origin cùng mức ưu tiên.

Thiết kế cần lưu ý: quá trình lựa chọn origin không chỉ dựa vào một cột priority; health probe, cấu hình origin, route, latency và tùy chọn của origin group đều ảnh hưởng kết quả. Phải kiểm thử với bản cấu hình đang dùng thay vì suy luận từ biểu đồ.

~~~text
https://shop.example
        |
  Azure Front Door
        |
    Origin group
        +-- origin-a: app-region-a.example (priority 1)
        +-- origin-b: app-region-b.example (priority 2)
        |
        +-- health probe: /health/ready
~~~

**Lưu ý bảo mật:** nếu origin B là App Service hoặc API có địa chỉ Internet riêng, phải hạn chế truy cập trực tiếp để tránh bypass Front Door/WAF. Xem xét Private Link khi tier và loại origin hỗ trợ, access restrictions và kiểm tra danh tính Front Door theo hướng dẫn dịch vụ. Dùng TLS từ client tới Front Door và trên đường tới origin phù hợp yêu cầu.

### Azure Traffic Manager: DNS priority failover

Traffic Manager phản hồi DNS theo routing method và tình trạng endpoint. Trong chế độ **Priority**, endpoint có priority cao hơn và đang khỏe được ưu tiên trả về; khi không khả dụng theo health monitoring, endpoint dự phòng đủ điều kiện có thể được trả về cho truy vấn mới.

~~~text
             DNS lookup: app.example
                        |
                 Traffic Manager
                        |
            +-----------+-----------+
            |                       |
    Region A endpoint        Region B endpoint
     priority cao hơn         priority thấp hơn
~~~

Traffic Manager **không nhận và proxy mọi HTTP request** của client. Sau khi tra DNS, client kết nối tới endpoint đích. Kết quả chuyển đổi chịu ảnh hưởng TTL, DNS resolver, cache ứng dụng và các kết nối đang tồn tại; không được hứa rằng tất cả client đổi region ngay sau khi endpoint A bị đánh dấu lỗi.

Nếu một ứng dụng bắt buộc dùng TCP/UDP hoặc protocol không phù hợp với reverse proxy L7, có thể đánh giá Traffic Manager hoặc cross-region Load Balancer theo khả năng sản phẩm. Cần xem xét riêng cách kiểm tra sức khỏe của endpoint và logic tái kết nối của client.

## 5. Ví dụ kiến trúc: web/API active-passive tại hai region

Giả sử công ty cung cấp hệ thống quản lý đơn hàng. Yêu cầu: khách hàng truy cập qua một hostname, hệ thống phải tiếp tục phục vụ nếu region chính gặp sự cố; tránh thất thoát đơn hàng và hạn chế việc tạo đơn hai lần.

~~~text
                     https://orders.example
                              |
                      Azure Front Door
                        (global HTTP)
                              |
                +-------------+-------------+
                |                           |
        Region A (primary)          Region B (standby)
        +------------------+        +-------------------+
        | Web / API        |        | Web / API         |
        | Health endpoint  |        | Health endpoint   |
        +--------+---------+        +---------+---------+
                 |                            |
        +--------v---------+          +-------v----------+
        | Database primary | ~~~~~~~> | Geo secondary    |
        | Read/write       | repl.    | Promoted if DR   |
        +------------------+          +------------------+

        Các phụ thuộc khác: identity, secrets, cache,
        queue/event, object storage, external APIs, DNS.
~~~

Sơ đồ minh họa **logical architecture**. Đối với Azure SQL Database, có thể đánh giá **failover groups/active geo-replication** với listener endpoint; đối với các loại database khác, khả năng replication và chuyển primary khác nhau. Không áp đặt một giải pháp database cho mọi ứng dụng.

### Thành phần cần triển khai tại cả hai region

| Thành phần | Region A | Region B | Điều kiện để failover |
|---|---|---|---|
| Frontend/API | Phục vụ bình thường | Sẵn sàng và được kiểm thử | Đủ instance/capacity để nhận tải |
| Cấu hình ứng dụng | Bản đã được phê duyệt | Bản tương thích với A | Cùng contract, endpoint và flags phù hợp |
| Database | Primary writer | Secondary/replica | Biết cách chuyển quyền ghi và xử lý replication lag |
| DNS/certificate | Hostname đi qua global entry | Dùng cùng public hostname ở lớp điều hướng | TLS và routing đã được kiểm tra |
| Secrets/keys | Được quản lý an toàn | Có phương án sử dụng khi A lỗi | Không phụ thuộc vào một endpoint/bản sao ngoài khả năng phục hồi |
| Queue/worker | Worker xử lý tác vụ | Worker dự phòng | Tránh hai nhóm worker cùng xử lý sai |
| Logs/monitoring | Có metric/log/cảnh báo | Tương tự | Vẫn quan sát được khi A mất kết nối |
| Hệ thống bên ngoài | Payment, mail, webhook | Đường kết nối/allowlist thích hợp | Đối tác chấp nhận egress và callback từ B |

Chỉ cấu hình hai origin cho Front Door là **chưa đủ**. Nếu region B chưa có database ghi được, hàng đợi hoặc secret tương ứng, ingress có thể chuyển sang một website không thể xử lý nghiệp vụ.

## 6. Thiết kế health probe đáng tin cậy

**Health probe** quyết định traffic có được chuyển tới một origin hay không. Probe quá đơn giản có thể trả healthy khi ứng dụng thật không dùng được; probe quá sâu có thể gây chuyển region không cần thiết khi một phụ thuộc phụ gặp lỗi.

### Liveness và readiness

- **Liveness:** tiến trình còn chạy và có thể phản hồi không? Thường dùng để khởi động lại instance khi tiến trình treo.
- **Readiness:** instance/region có thể phục vụ traffic thuộc vai trò hiện tại không? Phù hợp để ingress xác định origin có được nhận request.

Ví dụ cách phân tách endpoint:

~~~text
GET /health/live
  200 nếu tiến trình còn hoạt động

GET /health/ready
  200 khi ứng dụng có thể phục vụ request theo vai trò đã phân công
  503 khi ứng dụng chưa sẵn sàng nhận traffic
~~~

**Readiness của region standby cần được thiết kế cẩn thận.** Nếu backend B chỉ có replica đọc và chưa được phép ghi, trả 200 cho mọi request ở standby có thể khiến ingress chuyển traffic trước khi database promotion, gây lỗi ghi. Có hai cách phối hợp:

1. Để readiness báo không sẵn sàng cho workload ghi cho đến khi hoàn tất promote và thay đổi role.
2. Dùng một cơ chế chuyển đổi/điều phối riêng, chỉ cho ingress coi B là primary khi các điều kiện nghiệp vụ đã sẵn sàng.

Không để một probe công khai vô tình ghi dữ liệu, tạo đơn hoặc tiết lộ secret. Probe nên nhẹ, ổn định, xác định rõ dependency **bắt buộc** và có timeout hợp lý.

### Tránh flapping

**Flapping** là trạng thái hệ thống liên tục chuyển từ A sang B rồi quay lại A do metric chập chờn. Biện pháp giảm rủi ro:

- Chỉ đánh dấu unhealthy sau số lần probe thất bại hợp lý theo khả năng cấu hình của dịch vụ.
- Dùng health check đại diện cho giao dịch thực, không dựa vào một endpoint trang chủ tĩnh.
- Xác định ngưỡng, khoảng quan sát và người/quy trình được phép chuyển quyền ghi database.
- Khi region A vừa phục hồi, tránh tự động trả toàn bộ traffic về ngay nếu chưa kiểm tra ổn định.
- Theo dõi cả lỗi WAF, TLS, DNS và backend health để tránh chẩn đoán sai nguyên nhân.

Không sao chép tần suất probe, số lần thất bại và ngưỡng từ tài liệu của sản phẩm khác: cấu hình và thuật toán health của Front Door, Traffic Manager và cross-region LB có thể khác nhau.

## 7. Dữ liệu quyết định RPO và khả năng chuyển đổi

### Azure SQL Database và failover group

Đối với Azure SQL Database, có thể cân nhắc **failover groups** để tổ chức nhóm database có geo-secondary và cung cấp listener endpoint giúp ứng dụng hạn chế đổi connection string khi primary được chuyển. Cơ chế replication giữa các region có tính chất **bất đồng bộ**, nên một failover bắt buộc trong sự cố nặng có thể gây mất những transaction chưa kịp sao chép.

Các điểm cần thiết kế:

- Phân biệt **planned failover** (khi hai phía còn hoạt động, muốn hạn chế mất dữ liệu) và **forced/unplanned failover**.
- Xác định quyền truy cập, credential, firewall/private endpoint và connection policy ở region B.
- Kiểm tra độ trễ sao chép, trạng thái replica và khả năng chuyển primary theo hướng dẫn của dịch vụ.
- Dùng listener endpoint hợp lý cho read-write/read-only thay vì hard-code tên máy chủ primary tại một region.
- Cấu hình automatic failover policy/grace period nếu được hỗ trợ và phù hợp mục tiêu; không giả định tự động chuyển traffic ứng dụng là đồng bộ với việc chuyển database.
- Bài toán nhiều database hoặc dữ liệu phân tán cần kế hoạch consistency, migration/schema và validation sau failover.

Nếu dùng **Azure SQL Managed Instance**, tính năng và điều kiện failover group có thể khác Azure SQL Database. Chọn tài liệu theo đúng loại dịch vụ.

### Azure Cosmos DB

Cosmos DB có khả năng phân phối dữ liệu nhiều region với các lựa chọn **single-write region** hoặc **multi-write region** tùy API/cấu hình hỗ trợ. Thiết kế phải chọn consistency model, cơ chế failover, conflict resolution và SDK retry/endpoint discovery phù hợp.

**Multi-write không đồng nghĩa không có xung đột dữ liệu.** Hai region có thể nhận cập nhật cùng một đối tượng; ứng dụng phải hiểu khả năng conflict và mô hình nhất quán được chọn. Trong single-write, việc chuyển region ghi có điều kiện và trình tự riêng.

### Azure Storage

Các tùy chọn như **GRS/GZRS** sao chép dữ liệu sang region phụ theo mô hình hỗ trợ của storage account. **RA-GRS/RA-GZRS** có thể cho phép đọc từ secondary endpoint trong những điều kiện nhất định. Nhưng secondary **không mặc nhiên là primary ghi**, và account failover có quy trình/ảnh hưởng riêng.

Geo-redundancy không phải backup theo phiên bản và không tự giải quyết xóa nhầm dữ liệu đã được sao chép. Cần thiết kế thêm versioning, soft delete, backup/retention nếu workload yêu cầu. Việc failover storage account, thay đổi endpoint và có thể mất dữ liệu cần được xem như quyết định DR có kiểm soát.

### Queue, event và tác vụ nền

Hệ thống thường có message queue, scheduler hoặc event consumer. Tránh giả định mọi dịch vụ messaging sao chép **message data** giữa region:

- Một số khả năng geo-disaster recovery/alias của dịch vụ messaging tập trung vào **metadata/cấu hình**, không đồng nghĩa mọi message đang nằm trong hàng đợi được nhân bản.
- Khi failover, worker có thể xử lý lại request sau retry. Thiết kế **idempotency key**, deduplication, replay và dead-letter queue khi có thể.
- Quyết định ai sở hữu quyền xử lý các công việc tuần tự và ngăn hai region phát hành cùng một giao dịch.
- Với kết nối tới dịch vụ ngoài Azure, kiểm tra IP egress, endpoint allowlist và quyền xác thực ở region dự phòng.

### Chìa khóa: mỗi hệ lưu trữ có một RPO riêng

Ứng dụng có thể có SQL với RPO vài phút, blob với điểm phục hồi khác, queue chưa được sao chép và cache có thể tái dựng. RPO nghiệp vụ của **giao dịch hoàn chỉnh** bị giới hạn bởi thành phần cần thiết nhất và cách phối hợp giữa các thành phần đó.

Nếu người dùng nhận thông báo "đặt hàng thành công" nhưng đơn chưa tới secondary, hệ thống cần có quy trình đối soát với cổng thanh toán và nhật ký giao dịch sau khi failover.

## 8. Stateless web, session và cache

Tầng frontend/API nên càng **stateless** càng tốt để request mới có thể được xử lý tại region còn khỏe:

- Không lưu trạng thái giỏ hàng hoặc bước checkout chỉ trong RAM của một instance.
- Session/token phải dùng cơ chế phù hợp với nhiều region; nếu lưu session tập trung, hệ thống lưu session cũng cần DR.
- Kiểm tra khả năng xác thực cookie, chữ ký JWT và key rotation ở cả hai region; không sao chép secret tùy tiện qua file.
- Với cache, xác định dữ liệu nào có thể xây dựng lại, dữ liệu nào thực chất là nguồn dữ liệu quan trọng không được phép mất.
- Nếu ứng dụng sử dụng sticky session/session affinity, hãy thiết kế cách khôi phục phiên khi origin mất, hoặc buộc đăng nhập lại một cách an toàn.
- Các job chạy theo lịch phải có cơ chế ngăn hai region cùng gửi email/tính phí khi được kích hoạt đồng thời.

Mục tiêu không phải giữ mọi TCP connection sống qua sự cố region. Điều quan trọng là **client có thể retry/reconnect an toàn** và ứng dụng đưa ra thông báo phù hợp khi thao tác chưa được xác nhận.

### Idempotency cho giao dịch ghi

Giả sử khách hàng bấm "Thanh toán", request được xử lý ở A nhưng response bị mất khi region A gặp sự cố. Client retry tới B. Nếu API không có idempotency key, hai region có thể tạo hai giao dịch hoặc thu tiền hai lần.

~~~text
POST /orders
Idempotency-Key: order-request-42

API:
  - Tra cứu khóa request trong kho dữ liệu nghiệp vụ có tính nhất quán phù hợp
  - Nếu đã xử lý: trả về kết quả gắn với khóa đó
  - Nếu chưa xử lý: thực hiện với ràng buộc duy nhất/giao dịch an toàn
~~~

Đây là mô hình logic. Cơ chế lưu khóa, thời hạn giữ, tính nhất quán và cách xử lý dữ liệu chưa sao chép phải được thiết kế cụ thể. Chỉ thêm header mà không có bảo đảm ở backend chưa giải quyết được retry xuyên region.

## 9. Trình tự failover: chuyển ứng dụng và dữ liệu phối hợp

Một runbook tốt phải tránh tình trạng **split-brain**: cả A và B cùng tin mình là primary writer dù không có cơ chế multi-write an toàn.

### Runbook tham khảo cho active-passive

1. **Phát hiện:** monitoring và health probes cảnh báo A mất khả dụng; đối chiếu nhiều tín hiệu, không chỉ một request lỗi.
2. **Đánh giá:** xác nhận phạm vi gián đoạn, xem đây có phải sự cố toàn cục, lỗi phần mềm mới triển khai hay lỗi dữ liệu không.
3. **Ra quyết định:** đối chiếu RTO/RPO, trạng thái replication và nguy cơ mất dữ liệu. Kích hoạt quy trình phê duyệt phù hợp.
4. **Fencing quyền ghi:** cô lập hoặc vô hiệu hóa writer A nếu có khả năng A còn sống nhưng không giao tiếp được; tránh hai writer độc lập.
5. **Chuyển dữ liệu:** promote secondary/đổi primary theo cơ chế của database và chính sách đã duyệt; ghi nhận tình trạng dữ liệu.
6. **Kích hoạt ứng dụng B:** bảo đảm cấu hình, secret, network, connection string/listener, worker và quyền ghi phù hợp.
7. **Xác nhận readiness B:** thử đọc/ghi không gây tác dụng phụ ngoài kế hoạch, kiểm tra đường kết nối bắt buộc.
8. **Điều hướng traffic:** dùng Front Door, Traffic Manager hoặc global entry được chọn để đưa người dùng tới B.
9. **Xác minh nghiệp vụ:** đăng nhập, tìm kiếm, tạo một giao dịch thử an toàn, nhận event và đối soát dữ liệu.
10. **Theo dõi và truyền thông:** ghi lại thời gian, RTO/RPO thực, tỷ lệ lỗi, độ trễ; thông báo trạng thái tới các nhóm liên quan.

Trình tự không cứng nhắc cho mọi dịch vụ. Một số dịch vụ dữ liệu hỗ trợ failover tự động; với các trường hợp khác, đổi traffic trước khi chuyển quyền ghi có thể gây lỗi. Thiết kế phải mô tả rõ **điểm chuyển quyền sở hữu dữ liệu** và các điều kiện readiness ở từng giai đoạn.

### Pseudo runbook

~~~text
if outage_confirmed
   and failover_authorized
   and region_b_capacity_sufficient
   and data_loss_risk_accepted:

    fence_primary_writes_in_region_a()
    promote_secondary_data_if_required()
    validate_region_b_read_write_paths()
    mark_region_b_ready_for_ingress()
    shift_global_traffic_to_region_b()
    run_business_smoke_tests()
    watch_errors_latency_replication_and_cost()
else:
    keep_diagnosing_and_record_decision()
~~~

Đây là giả mã hướng dẫn điều phối, không phải script Azure có thể chạy nguyên văn. Đặc biệt, **fencing phải dựa trên khả năng được dịch vụ dữ liệu hỗ trợ**; một hành động tắt VM đơn thuần chưa chắc đủ nếu kết nối hoặc transaction ở hệ thống khác còn hoạt động.

## 10. Failback: quay về region ban đầu không đơn giản là đổi route

Khi A hoạt động trở lại, A có thể chứa dữ liệu cũ và không còn là primary. Nếu chuyển ngay request về A, ứng dụng có thể đọc sai hoặc ghi đè dữ liệu mới phát sinh tại B.

Một kế hoạch **failback** an toàn gồm:

1. Xác nhận A ổn định; sửa nguyên nhân gốc và cập nhật phiên bản/config cần thiết.
2. Khôi phục topology replication từ primary hiện hành B sang A theo khả năng dịch vụ.
3. Đợi A theo kịp và kiểm tra consistency, migration, version và dữ liệu nghiệp vụ.
4. Thực hiện planned failover nếu cần thay primary trở lại A, theo quy trình hạn chế mất dữ liệu.
5. Kiểm tra readiness A và xác định một primary writer duy nhất.
6. Chuyển traffic có kiểm soát, theo dõi lỗi và kiểm tra thông lượng/chi phí.
7. Ghi lại diễn biến, RTO/RPO thực và bài học cho lần sau.

**Không bắt buộc phải failback ngay.** Nếu B đang phục vụ ổn định, chờ một cửa sổ thay đổi được phê duyệt thường an toàn hơn so với tự động quay về A khi health probe vừa phục hồi.

## 11. Thiết kế đầy đủ các phụ thuộc xuyên region

Mất region có thể ảnh hưởng đến những dịch vụ bị bỏ quên khi vẽ sơ đồ web/API. Hãy rà soát:

| Nhóm phụ thuộc | Câu hỏi thiết kế |
|---|---|
| **Identity** | Người dùng còn đăng nhập được không? Ứng dụng B có đúng app registration, quyền và callback URL không? |
| **Secrets/keys** | B có truy cập được secret/certificate/key phù hợp không? Điều gì xảy ra nếu kho hoặc endpoint ở A lỗi? |
| **Networking** | VNet/subnet, NSG, UDR, NAT, Private Endpoint, DNS private zone và firewall của B đã sẵn sàng chưa? |
| **Public ingress** | Front Door/Traffic Manager/certificate/custom domain có hoạt động độc lập với A không? |
| **Data** | Replica, backup, phục hồi, encryption, key dependencies và quyền ghi được xử lý ra sao? |
| **Files/media** | File upload hiện ở B chưa? URL tĩnh, CDN và cache invalidation có đúng không? |
| **Message processing** | Worker, queue, checkpoint, dead-letter và job scheduler được khôi phục ra sao? |
| **Third-party APIs** | Cổng thanh toán, webhook, email, allowlisted IP có chấp nhận region B không? |
| **Observability** | Khi A hỏng, dashboard, alert và runbook có còn truy cập được không? |
| **Deployment** | Terraform/Bicep/Pipeline, image registry, artifact và quota cho B có sẵn không? |

Nhiều region không tự bảo đảm độc lập nếu cùng phụ thuộc vào một endpoint, một credential hết hạn hoặc một job triển khai sai. Cần kiểm tra **blast radius** của thay đổi cấu hình chung, rotation secret, release và quyền truy cập.

### Infrastructure as Code và cấu hình tương thích

Sử dụng Terraform, Bicep hoặc công cụ IaC phù hợp để định nghĩa hạ tầng A/B nhất quán: naming, tags, network rules, app settings, monitoring và policy. Với dữ liệu, không chạy migration gây mất tương thích tại một region trước khi region còn lại có thể đọc/ghi đúng.

Thiết kế release theo nguyên tắc **backward/forward compatibility** khi cần, có feature flags và quy trình rollback. Kiến trúc DR khó thành công nếu ứng dụng B đang ở phiên bản không tương thích schema database sau failover.

### Region pairs và data residency

Azure có khái niệm region pairs ở một số vùng địa lý và các đặc tính dịch vụ liên quan, nhưng **không mặc định mọi dịch vụ đều được sao chép sang paired region hoặc có RPO/RTO nhất định**. Chọn region thứ hai theo yêu cầu residency/compliance, độ trễ, SKU/quota, khả năng dịch vụ, khoảng cách vùng lỗi và chi phí. Kiểm tra tính năng DR của từng dịch vụ, không suy luận chỉ từ việc hai region tạo thành một cặp.

## 12. Hướng dẫn triển khai routing qua Azure Portal

Phần này minh họa hướng đi với **Azure Front Door Standard/Premium** cho ứng dụng HTTP/HTTPS, không phải toàn bộ quá trình DR của database. Trước khi thao tác, cần có hai backend app/API hợp lệ và được phép cấu hình.

### Bước 1: chuẩn bị hai origin

- Triển khai ứng dụng tại region A và B bằng cùng phiên bản đã kiểm tra.
- Xác nhận mỗi backend có hostname, TLS, health endpoint và cấu hình mạng.
- Kiểm tra B có thể xử lý request theo vai trò được phân công. Nếu chưa promote dữ liệu, chưa cho B nhận các request ghi sản xuất.
- Chuẩn bị quyền truy cập, secret và cơ chế giới hạn truy cập trực tiếp vào origin.

### Bước 2: tạo Front Door profile và origin group

1. Trong [Azure Portal](https://portal.azure.com), mở Azure Front Door và chọn profile Standard/Premium theo yêu cầu.
2. Tạo endpoint và origin group đại diện cho ứng dụng đơn hàng.
3. Thêm origin A và origin B với hostname/backend thích hợp.
4. Thiết lập priority theo active-passive: A ưu tiên hơn B, nhưng chỉ để B trở thành ứng viên phục vụ khi dữ liệu và ứng dụng ở B đã sẵn sàng.
5. Cấu hình health probe (protocol/path/method/interval phù hợp tính năng hiện hành).
6. Tạo route chuyển hostname/path công khai đến origin group.
7. Cấu hình custom domain/TLS và WAF/security policy nếu được sử dụng; hạn chế đường bypass vào origin.
8. Kiểm tra request, response, access log, origin health và quy trình chuyển đổi trong môi trường thử nghiệm.

Tên các mục trên Portal có thể thay đổi. Cấu hình cụ thể phụ thuộc tier/SKU và khả năng tích hợp private origin của từng loại backend.

### Bước 3: nếu dùng Traffic Manager

Thay vì reverse proxy, có thể:

1. Tạo Traffic Manager profile với routing method **Priority**.
2. Cấu hình DNS name, TTL và endpoint monitoring phù hợp.
3. Thêm endpoint A/B được phép giám sát và truy cập; gán thứ tự ưu tiên.
4. Cấu hình DNS public để hostname ứng dụng hướng đến Traffic Manager theo mô hình được hỗ trợ.
5. Thử ngắt endpoint lab và kiểm tra response DNS từ nhiều resolver theo thời gian.
6. Xác nhận ứng dụng có reconnect/retry và dữ liệu đã sẵn sàng ở B.

Không dùng thử nghiệm thay đổi bản ghi DNS production nếu chưa có kế hoạch và cửa sổ thay đổi. Với Traffic Manager, **DNS propagation/cache** là biến số quan trọng trong RTO.

## 13. Kiểm tra cấu hình bằng Azure CLI theo hướng đọc

Các lệnh sau chỉ **liệt kê/xem**, không tạo hoặc thay đổi global routing. Chúng hữu ích khi cần xác định profile, origin group và trạng thái cấu hình đã có.

~~~bash
az login
az account set --subscription "<SUBSCRIPTION_ID>"
az account show --output table
~~~

Liệt kê Front Door profiles trong resource group:

~~~bash
az afd profile list \
  --resource-group <RESOURCE_GROUP> \
  --output table
~~~

Xem origin groups của một profile:

~~~bash
az afd origin-group list \
  --resource-group <RESOURCE_GROUP> \
  --profile-name <AFD_PROFILE_NAME> \
  --output table
~~~

Xem origins trong nhóm được chọn:

~~~bash
az afd origin list \
  --resource-group <RESOURCE_GROUP> \
  --profile-name <AFD_PROFILE_NAME> \
  --origin-group-name <ORIGIN_GROUP_NAME> \
  --output json
~~~

Với Traffic Manager:

~~~bash
az network traffic-manager profile list \
  --resource-group <RESOURCE_GROUP> \
  --output table

az network traffic-manager endpoint list \
  --resource-group <RESOURCE_GROUP> \
  --profile-name <TM_PROFILE_NAME> \
  --output table
~~~

Trong ví dụ, các ký hiệu trong dấu **< >** là placeholder, cần thay trước khi chạy. Cú pháp Azure CLI có thể thay đổi theo phiên bản và extension; dùng **az afd --help** hoặc trợ giúp lệnh tương ứng để xác nhận. Thông tin liệt kê chỉ cho thấy **cấu hình**, không đủ chứng minh end-to-end failover hoặc đạt RTO/RPO.

## 14. Giám sát và cảnh báo failover

Monitoring cần cho thấy **một region có healthy hay không, traffic đang đi đâu và nghiệp vụ có phục hồi chưa**:

| Tín hiệu | Định nghĩa cần quan sát |
|---|---|
| Synthetic availability | Kiểm tra từ nhiều vị trí, gồm đăng nhập hoặc workflow chỉ đọc an toàn |
| Front Door/Traffic Manager health | Trạng thái origin/endpoint, sự kiện chuyển origin, cấu hình probe |
| HTTP error rate | 5xx và lỗi ứng dụng theo region, origin và hostname |
| Latency | p95/p99 cho request toàn cục và riêng từng region |
| Database health | Trạng thái primary/secondary, replication lag, tình trạng failover |
| Data correctness | Số đơn thành công, đối soát payment, event bị trễ/mất/nhân đôi |
| Capacity | CPU/instance/connections/throughput và quota tại B khi A mất |
| Security/network | WAF, TLS, DNS, firewall, private network và access restrictions |
| Cost | Chi phí standby, lưu lượng liên region, monitoring, geo-replication |

Không nên tự kích hoạt failover database chỉ dựa trên một probe của ingress. Cần tín hiệu độc lập và logic loại trừ nguyên nhân như lỗi DNS, WAF hoặc deployment mới trên cả A/B.

**Alerting** phải gửi được đến người chịu trách nhiệm ngay cả khi A không khả dụng. Runbook nên được lưu ở nơi có thể truy cập từ cả hai region; danh sách liên hệ khẩn cấp và cơ chế quyết định phải được kiểm tra trước.

## 15. Diễn tập failover và kiểm thử hỗn hợp

Thử nghiệm DR nên có ít nhất ba lớp:

1. **Tabletop:** diễn giải sự cố trên giấy, xác nhận người phụ trách, dữ liệu cần có và thứ tự hành động.
2. **Staging/sandbox failover:** chạy trên hệ thống độc lập, kiểm tra origin routing, data promotion và smoke tests.
3. **Game day có kiểm soát:** khi được phê duyệt, diễn tập một phần hoặc toàn bộ trên kiến trúc đại diện production, có rollback và giám sát.

### Ma trận kiểm thử

| Kịch bản | Kỳ vọng | Bằng chứng |
|---|---|---|
| Một instance A lỗi | Load balancing/HA nội vùng xử lý nếu còn instance khỏe | Health status và synthetic test |
| Toàn bộ frontend A lỗi, B đủ điều kiện | Global entry chuyển request hợp lệ sang B | Origin logs, status, response từ B |
| Database A lỗi nhưng app A còn sống | Không trả healthy sai cho các thao tác ghi; có quy trình dữ liệu | Readiness và kiểm tra DB primary |
| B đã nhận traffic nhưng chưa có quyền ghi | Chặn/cảnh báo đúng; không làm giả thành công | Log API, trace của giao dịch thử |
| A phục hồi sau khi B trở thành primary | Không tự tạo split-brain và không failback vội | Trạng thái primary, replication |
| Một request thanh toán bị retry xuyên region | Không tạo giao dịch trùng nếu cơ chế idempotency hỗ trợ | ID giao dịch, reconciliation |
| DNS TTL chưa hết trên một số client | Client retry/kết nối cũ được xử lý theo thiết kế | Kết quả từ nhiều resolver/client |
| Region B không đủ quota/compute | Có cảnh báo và phương án scale trước khi chuyển tải | Capacity/quota và autoscale logs |
| Lỗi triển khai đồng thời A/B | Xác định đây không phải sự cố region riêng lẻ | Release/feature-flag history |
| Dependency ngoài Azure không cho phép IP B | Có đường xử lý và liên hệ đối tác | Log egress và kết quả thử nghiệm |

### Đo kết quả sau diễn tập

Ghi lại: thời điểm gây sự cố, phát hiện, quyết định, chuyển dữ liệu, chuyển traffic, hoàn tất smoke test, dữ liệu cuối cùng đã sao chép, độ trễ, số lần retry và lỗi người dùng.

~~~text
RTO thực tế = thời điểm dịch vụ đạt điều kiện phục hồi
              - thời điểm gián đoạn bắt đầu

RPO thực tế = khoảng dữ liệu/giao dịch bị mất được xác minh
              so với trạng thái trước sự cố, quy đổi theo thời gian
~~~

Nếu không thể xác minh dữ liệu đã mất hoặc mốc giao dịch cuối, ghi **RPO chưa đo được**, không mặc định bằng 0. Chỉ gọi diễn tập thành công nếu các giao dịch nghiệp vụ đã qua kiểm thử và có số liệu đáp ứng mục tiêu.

## 16. Bài thực hành thiết kế không phát sinh chi phí

Bạn có thể hoàn thành bài tập bằng sơ đồ và bảng quyết định mà **không cần tạo tài nguyên Azure**.

### Đề bài

Ứng dụng **shop.example** có:

- Web và API đang chạy tại một region, lưu giỏ hàng và đơn hàng.
- Azure SQL Database làm nguồn dữ liệu giao dịch.
- 10.000 request/phút ở giờ cao điểm, trong đó một phần là thao tác ghi.
- Yêu cầu kinh doanh giả định: **RTO tối đa 30 phút, RPO tối đa 5 phút**.
- Dữ liệu cần được quản lý trong các region được tổ chức phê duyệt.
- Khách hàng dùng một URL duy nhất, ưu tiên region A trong điều kiện bình thường.

### Bước 1: vẽ kiến trúc đề xuất

Mô tả các khối: frontend/API A, frontend/API B, Front Door, database primary/secondary, health endpoint, DNS/TLS, secrets, logging, worker/queue và external payment. Dùng mũi tên khác nhau cho **traffic web**, **đường ghi dữ liệu** và **replication**.

### Bước 2: chọn mô hình và justify

Một phương án phù hợp để phân tích là **active-passive warm/hot standby**:

| Quyết định | Phương án ban đầu | Câu hỏi còn phải kiểm thử |
|---|---|---|
| Global entry | Azure Front Door | B có nhận đúng traffic khi A unhealthy không? |
| Region chính | A, được chọn theo yêu cầu residency/latency | Có Availability Zones không? |
| Region phụ | B, đã triển khai frontend/API | Có đủ instance/quota để nhận tải từ A không? |
| Database | Azure SQL failover group theo khả năng dịch vụ | Replication lag và forced failover có đáp ứng RPO không? |
| Phiên người dùng | Stateless hoặc session có DR | Client retry sau chuyển region có an toàn không? |
| Health | Readiness phản ánh khả năng phục vụ nghiệp vụ | B báo ready khi database chưa promote có nguy hiểm không? |
| Sự cố vùng | Runbook có điều phối và người phê duyệt | Khi nào quyết định chấp nhận nguy cơ mất dữ liệu? |

Đây chỉ là **đề xuất để đánh giá**, không phải bảo đảm rằng Azure SQL failover group sẽ mặc định đạt RPO 5 phút hoặc Front Door sẽ tự đạt RTO 30 phút.

### Bước 3: thực hành tabletop

Giả lập tình huống: **10:00 region A không còn truy cập được**, database B có replication lag chưa xác nhận. Ghi:

1. Những tín hiệu nào dùng để xác minh đây là lỗi region chứ không phải deployment?
2. Ai được quyết định forced failover nếu có nguy cơ mất dữ liệu?
3. Làm sao ngăn A tiếp tục ghi nếu A phục hồi một phần trong lúc B được nâng primary?
4. Thứ tự chuyển database, readiness B và Front Door là gì?
5. Thao tác nghiệp vụ nào dùng để kiểm tra đã phục hồi?
6. Sau khi A trở lại, có cần chuyển ngay về A không?

### Bước 4: bảng kết quả

| Hạng mục | Cần nộp |
|---|---|
| Kiến trúc | Sơ đồ ingress, compute, dữ liệu ở A/B và các phụ thuộc |
| Mục tiêu | RTO/RPO đã chọn, giả định, phương pháp đo |
| Quy trình | Runbook kích hoạt, chuyển đổi và failback |
| Kiểm thử | Tối thiểu 5 ca kiểm thử trong ma trận ở mục 15 |
| Rủi ro | Ít nhất 3 rủi ro: mất dữ liệu, split-brain, thiếu capacity, DNS cache... |
| Tối ưu | Cách giảm chi phí standby mà không phá vỡ mục tiêu kinh doanh |

### Bước 5: mở rộng nếu có sandbox được phép

Nếu có hai ứng dụng mẫu không chứa dữ liệu thật, có thể cấu hình Front Door hoặc Traffic Manager với hai endpoint lab, quan sát health và chuyển hướng khi một backend dừng. **Không thực hành forced database failover trên dữ liệu quan trọng** và không thử sự cố production nếu chưa được phê duyệt.

Các dịch vụ như Front Door, Traffic Manager, App Service, lưu log và geo-replication **có thể phát sinh phí**. Xác nhận giá và budget trước khi tạo, rồi dọn toàn bộ tài nguyên lab sau khi hoàn thành.

## 17. Tối ưu chi phí và năng lực region dự phòng

DR có thể tạo chi phí cố định dù không có sự cố. Một số nguồn chi phí:

- Compute/instance, autoscale và reserved capacity ở B.
- Database replica, storage geo-redundancy, replication và backup.
- Truyền dữ liệu liên region, egress và kết nối mạng.
- Azure Front Door/Traffic Manager/cross-region LB theo mức sử dụng/SKU.
- WAF, log ingestion, retention, monitoring và synthetic tests.
- Băng thông, message processing và dịch vụ thứ ba trong quá trình failover.

Đừng tối ưu chỉ bằng cách giảm tất cả instance ở B xuống 0 nếu RTO yêu cầu có dịch vụ sẵn sàng ngay. Với warm standby, phải kiểm tra **thời gian tăng công suất và quota khả dụng**, khả năng cấp VM/SKU, thời gian warm-up và thời gian thiết lập connection đến database.

Một chỉ số quan trọng là **capacity sau mất một region**. Nếu A và B đều hoạt động 70% công suất trong active-active, một region còn lại có thể không đủ sức nhận toàn bộ lưu lượng sau sự cố. Thiết kế cần có headroom, kế hoạch scale, giới hạn request và degrade mode được phê duyệt.

### Graceful degradation

Khi B chưa đủ công suất cho mọi tính năng, có thể ưu tiên đường giao dịch thiết yếu (đăng nhập, tra cứu đơn, thanh toán) và tạm hoãn chức năng không quan trọng (báo cáo nặng, gợi ý sản phẩm, batch). Cách này chỉ hợp lý nếu được định nghĩa trước, quan sát được và không làm mất tính toàn vẹn dữ liệu.

## 18. Sự cố thường gặp và cách khoanh vùng

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Đã chuyển Front Door sang B nhưng user vẫn thấy 500 | B healthy ở probe đơn giản, nhưng database/secret/queue chưa sẵn sàng | Kiểm tra readiness thực, backend logs và quyền ghi DB |
| Traffic Manager báo B nhưng một số user vẫn đến A | Resolver/client cache, TTL hoặc kết nối tồn tại | Kiểm tra DNS từ nhiều mạng; chuẩn bị retry/reconnect |
| Failover gây mất đơn hàng gần thời điểm sự cố | Geo-replication bất đồng bộ chưa theo kịp | Đối soát transaction, đo RPO, cải thiện quy trình dữ liệu |
| Sau failover người dùng phải đăng nhập lại | Session/state không được chia sẻ hoặc key cấu hình khác | Kiểm tra session strategy, token/cookie keys và chính sách bảo mật |
| Cả hai region đều từ chối lệnh ghi | Không xác định primary, endpoint/listener sai hoặc writer chưa promote | Xác nhận role của database, listener và runbook |
| Ghi dữ liệu xung đột sau khi A hồi phục | Split-brain hoặc multi-write chưa có conflict resolution | Chặn writer cũ, đánh giá consistency và tái đồng bộ |
| Failover xong nhưng không gửi được webhook | IP egress/callback URL/credential của B chưa được đối tác cho phép | Kiểm tra cấu hình third-party và mạng |
| B không scale theo dự kiến | Thiếu quota/SKU, thiếu instance warm hoặc giới hạn cấu hình | Kiểm tra quota, capacity reservation và load tests |
| Chỉ chuyển được web, queue vẫn nằm ở A | Chưa có chiến lược DR messaging | Kiểm tra khả năng sao chép message, replay và idempotency |
| A vừa khỏe lại traffic lập tức quay về rồi lại rớt | Probe flapping, tự động failback quá sớm | Bổ sung điều kiện ổn định và quy trình failback |
| Chạy DR drill nhưng không biết dữ liệu nào mất | Thiếu audit/reconciliation và mốc replication | Bổ sung log nghiệp vụ, checkpoint và phương pháp đo RPO |

Trong điều tra, lưu thời điểm lỗi, tên region, origin/endpoint được chọn, mã HTTP, trace ID, database primary, replication lag, thay đổi gần nhất và kết quả smoke test. Không chuyển traffic nhiều lần để thử may rủi mà không ghi lại trạng thái, vì có thể tạo vòng lặp hoặc mất dữ liệu.

## 19. Câu hỏi tự kiểm tra

1. HA nhiều Availability Zones khác DR nhiều region ở điểm nào?
2. RTO và RPO đo hai điều khác nhau ra sao? Tại sao đổi DNS nhanh không bảo đảm đạt RTO?
3. Khi nào nên chọn active-passive thay cho active-active?
4. Azure Front Door khác Azure Traffic Manager như thế nào ở đường đi của một HTTP request?
5. Vì sao DNS TTL có thể ảnh hưởng thời gian người dùng chuyển sang region dự phòng?
6. Nếu frontend B trả HTTP 200 nhưng database B chỉ đọc, health endpoint nên được thiết kế ra sao?
7. Điều gì khiến chuyển database primary trong lỗi region có thể dẫn đến mất dữ liệu?
8. Vì sao không thể mặc định một queue đã được sao chép cùng database?
9. Split-brain là gì? Làm sao ngăn hai region cùng ghi khi không thiết kế multi-write?
10. Vì sao một hệ thống active-active vẫn có thể không chịu được khi mất một region?
11. Những thành phần nào ngoài web/API cần có runbook failover?
12. Sau khi A phục hồi, vì sao không nên lập tức chuyển traffic từ B về A?

## 20. Tài liệu tham khảo

- [Azure reliability documentation](https://learn.microsoft.com/azure/reliability/) — khái niệm availability, resiliency và disaster recovery trên Azure.
- [Azure Well-Architected Framework: Reliability](https://learn.microsoft.com/azure/well-architected/reliability/) — thiết kế theo mục tiêu phục hồi, failure modes và kiểm thử.
- [Azure Front Door overview](https://learn.microsoft.com/azure/frontdoor/front-door-overview) — điều phối HTTP/HTTPS toàn cầu.
- [Azure Front Door health probes](https://learn.microsoft.com/azure/frontdoor/health-probes) — kiểm tra tình trạng origin và cơ chế lựa chọn backend.
- [Azure Traffic Manager overview](https://learn.microsoft.com/azure/traffic-manager/traffic-manager-overview) — DNS routing và các phương pháp điều hướng.
- [Azure SQL Database failover groups](https://learn.microsoft.com/azure/azure-sql/database/failover-group-sql-db) — geo-replication và failover group cho SQL Database.
- [Azure Cosmos DB global distribution](https://learn.microsoft.com/azure/cosmos-db/distribute-data-globally) — dữ liệu đa region và các tùy chọn ghi.
- [Azure Storage redundancy](https://learn.microsoft.com/azure/storage/common/storage-redundancy) — LRS/ZRS/GRS/GZRS và hành vi sao chép dữ liệu.
- [Azure CLI: Azure Front Door Standard/Premium](https://learn.microsoft.com/cli/azure/afd) — nhóm lệnh đọc và quản lý Front Door.
- [Azure CLI: Traffic Manager](https://learn.microsoft.com/cli/azure/network/traffic-manager) — quản lý profile và endpoint.

**Kết luận:** Failover đa region không phải chỉ là cấu hình thêm một backend và bật health probe. Một phương án DR hoàn chỉnh phải xác định được **mục tiêu RTO/RPO, tình trạng dữ liệu, nguồn quyền ghi, đường đi người dùng, năng lực region dự phòng và quy trình vận hành**. Hãy diễn tập từng lớp, đo kết quả thật và chỉ tự động hóa những bước có điều kiện an toàn đã được hiểu rõ.

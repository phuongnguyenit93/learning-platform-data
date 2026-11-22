# Lift-and-shift mà không xem lại mạng, vận hành và chi phí

## 1. Phản mẫu là gì?

**Lift-and-shift** (*rehost*) là cách di chuyển một ứng dụng đang chạy trên máy chủ vật lý hoặc máy ảo lên hạ tầng đám mây với rất ít thay đổi về mã nguồn và cấu trúc triển khai. Ví dụ, tổ chức chuyển máy ảo web, ứng dụng và cơ sở dữ liệu (CSDL) từ trung tâm dữ liệu sang các máy ảo trên cloud, giữ nguyên hệ điều hành, tiến trình và cơ chế kết nối.

Rehost có thể là **một bước di chuyển hợp lý** khi cần rời trung tâm dữ liệu nhanh, giảm thay đổi đối với ứng dụng cũ hoặc tạo nền tảng để hiện đại hóa về sau. Phản mẫu xuất hiện khi nhóm triển khai coi việc máy ảo khởi động thành công trên cloud là bằng chứng kiến trúc đã sẵn sàng, trong khi **không đánh giá lại mạng, mô hình vận hành và tổng chi phí**. Hậu quả là hệ thống mang nguyên các điểm yếu cũ lên một môi trường có đặc tính khác: lưu lượng đi xa hơn, trách nhiệm vận hành thay đổi và tài nguyên được tính tiền theo cách mới.

Đây là chủ đề của chương **Phản mẫu kiến trúc** trong CLOUD_ARCHITECTURE: người thiết kế cần đi từ yêu cầu nghiệp vụ đến quyết định về mạng, compute, dữ liệu và triển khai; đánh giá đánh đổi giữa độ tin cậy, bảo mật, mở rộng, chi phí và vận hành theo các trụ cột **Well-Architected**.

Sau bài này, người học có thể:

- Nhận biết dấu hiệu của rehost thiếu đánh giá kiến trúc và phân biệt với rehost có kế hoạch.
- Phân tích ảnh hưởng của đường đi dữ liệu, độ trễ, khả năng kết nối, phân vùng mạng và quyền truy cập.
- Thiết kế quan sát, sao lưu, khôi phục, bảo mật và quy trình vận hành thích hợp trên cloud.
- Ước tính tổng chi phí vận hành, nhận diện các hạng mục dễ bị bỏ sót và lập kế hoạch tối ưu.
- Đề xuất một lộ trình di chuyển có tiêu chí nghiệm thu đo được, kể cả khi chưa sửa mã nguồn.

## 2. Kịch bản: di chuyển máy ảo “y nguyên” gây ra vấn đề gì?

Một công ty có ứng dụng quản lý đơn hàng ba lớp: web server nhận yêu cầu từ người dùng, application server xử lý nghiệp vụ và CSDL lưu đơn hàng, tồn kho, thanh toán.

Hệ thống đang đặt trong cùng một trung tâm dữ liệu. Đội dự án chuyển hai lớp web/app sang máy ảo cloud, giữ CSDL ở trung tâm dữ liệu trong giai đoạn đầu. Kiến trúc sau di chuyển vẫn hoạt động, nhưng mỗi yêu cầu ứng dụng cần nhiều lượt truy vấn xuyên kết nối hybrid. Trong giờ cao điểm, độ trễ tăng mạnh; đội vận hành không nhìn thấy đường đi chi tiết; hóa đơn cloud cao hơn dự kiến vì máy ảo luôn bật, ổ đĩa và lưu lượng mạng.

~~~mermaid
flowchart TB
    U[Người dùng] --> LB[Điểm vào trên cloud]
    subgraph CLOUD[Cloud]
      LB --> W[Web VM]
      W --> A[Application VM]
    end
    subgraph DC[Trung tâm dữ liệu]
      DB[(CSDL chính)]
    end
    A <-->|Nhiều round trip qua mạng hybrid| DB
    note1["Rủi ro: độ trễ, phụ thuộc kết nối,\nchi phí truyền dữ liệu, thiếu quan sát"]
    A -.-> note1
~~~

**Vấn đề nằm ở giả định kiến trúc:** trước đây các thành phần gần nhau và nhóm vận hành kiểm soát phần lớn mạng vật lý; sau khi di chuyển, ứng dụng lệ thuộc đường truyền, dịch vụ nền và mô hình tính phí của cloud. Chuyển VM không tự động biến hệ thống thành ứng dụng chịu lỗi, tự mở rộng hoặc được tối ưu chi phí.

## 3. Dấu hiệu nhận biết và nguyên nhân gốc

| Dấu hiệu | Giả định sai thường gặp | Hệ quả có thể xảy ra |
| --- | --- | --- |
| Sao chép sơ đồ IP/VLAN cũ sang cloud | VPC/VNet, subnet và định tuyến vận hành giống switch trong data center. | CIDR chồng lấn, route bất đối xứng, lỗi kết nối hoặc lộ đường truy cập ngoài ý muốn. |
| Ứng dụng lên cloud, CSDL hoặc dịch vụ phụ thuộc ở lại on-premises | Khoảng cách vật lý không ảnh hưởng tới giao thức nhiều lượt gọi. | Round trip làm chậm giao dịch; mất kết nối ảnh hưởng cả hệ thống. |
| Đưa toàn bộ VM lên một vùng sẵn sàng và gọi là “high availability” | Cloud tự bảo vệ khỏi mọi lỗi khi VM đã khởi động. | Một sự cố vùng sẵn sàng có thể làm ngừng toàn bộ ứng dụng. |
| Duy trì script thủ công, tài khoản quản trị dùng chung | Vận hành cloud chỉ là SSH/RDP tới VM. | Không kiểm soát drift, khó kiểm toán, phục hồi phụ thuộc vào cá nhân. |
| Chỉ đo CPU và RAM | Máy ảo còn chạy nghĩa là dịch vụ đáp ứng SLO. | Không phát hiện giao dịch chậm, lỗi ở LB, DB hoặc tuyến mạng. |
| Chọn cỡ VM bằng cấu hình máy vật lý cũ | Cùng số vCPU/RAM đồng nghĩa cùng hiệu năng và chi phí. | Tài nguyên dư thừa hoặc thiếu IOPS/băng thông; chi phí tăng. |
| Dự toán chỉ có tiền VM | Mạng, storage, backup, log và dịch vụ nền không đáng kể. | Hóa đơn thực tế vượt ngân sách. |
| Không xác định thời hạn chạy song song và bước tối ưu | “Đưa lên cloud” là điểm kết thúc dự án. | Hai môi trường tồn tại lâu, trả tiền tài nguyên thừa và tiếp tục mang nợ kỹ thuật. |

Nguyên nhân thường là đánh giá thành công theo số lượng VM đã chuyển, thiếu danh mục phụ thuộc và baseline trước di chuyển; phân công mờ giữa đội hạ tầng, ứng dụng, bảo mật và tài chính; hoặc đặt thời hạn di chuyển nhưng không dành thời gian thiết lập các điều kiện vận hành tối thiểu.

### Khi nào lift-and-shift vẫn là lựa chọn đúng?

Rehost phù hợp nếu có ràng buộc thời gian, giấy phép, mã nguồn hoặc yêu cầu nghiệp vụ khiến refactor ngay có rủi ro lớn; đã đo đường đi dữ liệu và chứng minh hiệu năng đáp ứng yêu cầu hoặc di chuyển các thành phần phụ thuộc cùng nhau; có landing zone, kết nối, giám sát, backup, bảo mật, sizing, dự toán chi phí và kế hoạch tối ưu sau cutover. Các khoản nợ kỹ thuật còn lại phải có chủ sở hữu và thời hạn xử lý.

Vì vậy, **lift-and-shift không tự thân là phản mẫu**; phản mẫu là *rehost như thể môi trường đích không có đặc tính và trách nhiệm khác*.

## 4. Sai lầm ở lớp mạng: sao chép topology mà không đo luồng dữ liệu

### 4.1. Bắt đầu từ luồng phụ thuộc, không bắt đầu từ danh sách VM

Một danh sách 20 máy ảo không cho biết ứng dụng cần gọi CSDL bao nhiêu lần, giao tiếp với nhà cung cấp thanh toán qua đâu hoặc có phụ thuộc DNS, LDAP/Active Directory, SMTP, license server hay dịch vụ nội bộ nào. Trước di chuyển, cần lập **dependency map** và ghi cho từng luồng:

| Thuộc tính | Ví dụ thông tin cần thu thập |
| --- | --- |
| Nguồn → đích | App → DB, app → cache, app → API thanh toán, người dùng → web |
| Giao thức và cổng | HTTPS/TLS, TCP tới DB, DNS, NTP; cả chiều phản hồi |
| Mục đích và độ nhạy | Dữ liệu khách hàng, lệnh ghi đơn, đăng nhập |
| Lưu lượng | Request/giây, byte/giây, độ lớn gói, thời điểm cao điểm |
| SLO | p95/p99 độ trễ, tỷ lệ lỗi, timeout, yêu cầu đọc sau ghi |
| Ràng buộc | IP allowlist, vùng lưu dữ liệu, mã hóa, xác thực, thời gian khôi phục |
| Chủ sở hữu | Nhóm ứng dụng, nhóm dữ liệu, nhóm mạng, bên thứ ba |

Phải đánh giá **đường đi thật của request**, gồm ingress, kết nối giữa các dịch vụ (*east–west*), traffic tới data center, Internet egress và lưu lượng đồng bộ/sao lưu. Các đường này có độ trễ, khả năng sẵn sàng và biểu phí khác nhau.

### 4.2. Độ trễ mạng bị khuếch đại bởi ứng dụng nhiều lượt gọi

Giả sử mỗi request thực hiện **25 lượt truy vấn CSDL tuần tự**. Trước di chuyển, độ trễ mạng cho một lượt là khoảng 1 ms; sau di chuyển, nếu giữ CSDL on-premises, độ trễ round trip tăng thành 18 ms. Phần chênh lệch mạng ước tính là:

\[
\Delta T \approx 25 \times (18 - 1) = 425\ \text{ms/request}
\]

Đây là **ví dụ giả định** chỉ tính phần mạng cho các lượt gọi tuần tự, chưa cộng thời gian xử lý truy vấn, đóng gói, hàng đợi hay retry. Với các lệnh chạy song song hoặc kết nối có pipeline, độ trễ thực tế có thể khác. Tuy vậy, phép tính cho thấy vì sao một mức tăng round trip nhỏ có thể làm chậm ứng dụng gọi DB nhiều lần rõ rệt.

Các cách xử lý tùy tình huống:

- **Đặt gần dữ liệu:** di chuyển ứng dụng và CSDL có quan hệ giao dịch chặt chẽ cùng khu vực hoặc giảm đường đi qua hybrid, sau khi đánh giá yêu cầu dữ liệu và tính khả thi của cutover.
- **Giảm lượt gọi:** gom truy vấn, xử lý batch, bổ sung cache có cơ chế invalidation và kiểm soát consistency.
- **Chia miền dữ liệu:** dùng API/sự kiện thích hợp nếu cần giữ hệ thống cũ, tránh cho từng request người dùng phải đọc nhiều bảng từ xa.
- **Đo thay vì đoán:** dùng trace theo request và metric tại từng hop; thử tải đại diện với latency, packet loss và failover thực tế.

Không nên dùng cache để che giấu mọi truy vấn chậm nếu giao dịch cần dữ liệu mới nhất, ví dụ kiểm soát tồn kho hoặc quyết định thanh toán.

### 4.3. Những quyết định mạng không thể “chép nguyên”

**Địa chỉ và định tuyến:** quy hoạch CIDR không chồng lấn giữa on-premises và cloud; xác định route table, đường về, NAT, VPN hoặc đường kết nối riêng, cùng các miền lỗi. Chồng lấn IP có thể ngăn routing trực tiếp và buộc dùng NAT hoặc đổi địa chỉ.

**Phân vùng bảo mật:** thiết kế subnet theo vai trò, quy tắc firewall/security group, quyền truy cập vào DB, giới hạn outbound, private endpoint cho dịch vụ quản lý phù hợp. Không thay một ACL rộng cũ bằng quy tắc **0.0.0.0/0** mở các cổng quản trị. Đường admin nên qua cơ chế được kiểm soát, ghi nhận truy cập.

**DNS và danh tính:** kiểm tra phân giải tên nội bộ, split-horizon DNS, TTL, certificate, reverse DNS nếu liên quan, cơ chế nhận dạng ứng dụng và mối phụ thuộc với hệ thống danh tính cũ. Thay IP của VM nhưng bỏ qua DNS có thể khiến dịch vụ vẫn gọi về hệ thống đã chuyển.

**Cổng vào và cổng ra:** tách Internet-facing LB/reverse proxy khỏi máy ứng dụng; đánh giá WAF, bảo vệ DDoS, TLS termination, route outbound, NAT, hạn mức kết nối và chi phí truyền Internet/liên vùng. Không phải traffic nội bộ nào cũng miễn phí.

**Độ sẵn sàng của kết nối:** một VPN hoặc một đường kết nối chuyên dụng có thể trở thành điểm lỗi đơn dù app chạy nhiều VM. Cần xét đường dự phòng độc lập, chuyển tuyến, BGP/route nếu dùng, health check và kiểm tra failover.

**Hiệu năng:** ngoài latency, cần đo throughput thực, packet loss, MTU, retransmission, timeout, connection pooling và giới hạn kết nối của thiết bị/managed service.

### 4.4. Ví dụ đường đi cần thiết kế lại

~~~mermaid
flowchart LR
    U[Client] --> EDGE[DNS / WAF / Load Balancer]
    subgraph AZ1[Availability zone A]
        APP1[App instance A]
    end
    subgraph AZ2[Availability zone B]
        APP2[App instance B]
    end
    EDGE --> APP1
    EDGE --> APP2
    APP1 --> DB[(CSDL gần ứng dụng)]
    APP2 --> DB
    APP1 --> OBS[Quan sát tập trung]
    APP2 --> OBS
    DB --> BCK[Backup độc lập & kiểm thử restore]
    ONPREM[Hệ thống còn ở data center] <-->|Kết nối hybrid kiểm soát| API[API / đồng bộ dữ liệu]
    API --> APP1
    API --> APP2
~~~

Sơ đồ chỉ thể hiện **nguyên tắc phân tách đường giao dịch chính khỏi kết nối hybrid nhiều lượt**. Thiết kế thực tế còn phải xác định khả năng chịu lỗi và phạm vi triển khai của CSDL (chẳng hạn cơ chế replication/failover giữa zone), consistency, backup, security boundary và chi phí truyền giữa các zone. Hai app instance không tự động làm CSDL trở nên sẵn sàng cao.

## 5. Sai lầm ở vận hành: đưa VM lên cloud nhưng giữ cách quản trị cũ

Cloud thay đổi ranh giới trách nhiệm. Nhà cung cấp vận hành một phần cơ sở hạ tầng, còn tổ chức vẫn phải quản lý cấu hình workload, hệ điều hành trên VM, quyền truy cập, dữ liệu, cập nhật bản vá, backup và khả năng phục hồi theo **mô hình trách nhiệm chia sẻ** của dịch vụ đang dùng.

### 5.1. Không có SLO, quan sát và chẩn đoán theo luồng

Một dashboard chỉ có CPU/RAM không giải thích được “đăng nhập mất 8 giây”. Cần quan sát theo hành vi người dùng và phụ thuộc:

- **Chỉ số nghiệp vụ và SLI:** tỷ lệ đơn tạo thành công, p95/p99 thời gian phản hồi, tỷ lệ lỗi, độ trễ của job và queue.
- **Metric hạ tầng:** CPU, RAM, dung lượng disk, IOPS/latency, network throughput, packet loss, trạng thái instance/LB, DB connection và replication lag.
- **Log tập trung:** định danh request/correlation ID, mức lỗi, cấu trúc dễ truy vấn; che/mã hóa dữ liệu nhạy cảm theo chính sách.
- **Distributed tracing:** thời gian ở edge, app, DB, cache và dịch vụ qua mạng hybrid; gắn trace ID xuyên các chặng.
- **Synthetic test và health check:** kiểm tra các luồng thiết yếu từ vị trí người dùng, không chỉ mở được cổng TCP.

Ví dụ SLO giả định cho một luồng tạo đơn: “Trong cửa sổ 30 ngày, ít nhất 99,9% request hợp lệ tạo đơn thành công và p95 độ trễ dưới 800 ms”. Hai điều kiện này cần định nghĩa cách đo, phạm vi và loại trừ được thống nhất. Alert nên bám vào lỗi có ảnh hưởng và *error budget*; không tạo hàng trăm cảnh báo chỉ vì một host chạm 70% CPU.

### 5.2. Cao sẵn sàng không đến từ nhãn “cloud”

Nếu cả ba VM và một ổ dữ liệu duy nhất nằm trong cùng miền lỗi, một sự cố vẫn có thể khiến dịch vụ dừng toàn bộ. Cần xem xét:

- Phân tán các instance qua nhiều vùng sẵn sàng khi yêu cầu và dịch vụ hỗ trợ; LB loại instance lỗi dựa trên health check đúng chức năng.
- Tránh giữ session, file upload hoặc trạng thái quan trọng trên disk cục bộ của một VM nếu muốn thay VM hoặc scale ngang.
- Thiết kế failure mode cho DB, cache, queue, DNS và kết nối hybrid; mỗi thành phần có RTO/RPO riêng.
- Có giới hạn, timeout, retry với backoff và circuit breaker phù hợp để tránh retry storm khi một phụ thuộc chậm.
- Diễn tập sự cố VM, đứt kết nối zone/hybrid, mất credential hoặc hết dung lượng, đo thời gian khôi phục thực tế.

**Backup khác với high availability.** Một replica sẵn sàng cao có thể sao chép cả thao tác xóa nhầm; backup có chính sách retention/phiên bản và bản sao độc lập giúp phục hồi từ lỗi logic. Phải **thử restore**, kiểm tra ứng dụng có chạy được từ dữ liệu khôi phục, và so với RPO (mức dữ liệu có thể mất) cùng RTO (thời gian khôi phục tối đa chấp nhận).

### 5.3. Bảo mật và vận hành theo cấu hình

Giữ nguyên tài khoản quản trị dùng chung, bí mật trong file cấu hình hoặc mở cổng SSH/RDP trực tiếp cho Internet có thể kéo lỗ hổng cũ lên một bề mặt truy cập lớn hơn. Biện pháp nền tảng gồm:

1. **Landing zone và chính sách:** phân môi trường/account/subscription/project; gán vai trò, logging/audit, policy guardrail, tags và budget từ đầu.
2. **Identity và secret:** SSO/MFA cho người quản trị, IAM tối thiểu, danh tính workload thay khóa tĩnh khi có thể, vault và quy trình xoay vòng secret.
3. **Hạ tầng như mã (IaC):** khai báo network, VM, disk, LB, IAM và cấu hình có review; kiểm soát drift, đưa bản dựng qua pipeline kiểm thử.
4. **Golden image/patch:** quản lý hệ điều hành, bảo mật endpoint, cập nhật, quét lỗ hổng, cấu hình base; có cơ chế tái tạo VM thay vì chỉnh tay.
5. **Runbook và quản lý thay đổi:** lịch deploy, rollback ứng dụng, giám sát sau deploy, trực sự cố, chủ sở hữu và diễn tập.

Không phải mọi workload rehost đều cần viết lại thành microservice hoặc Kubernetes. Đưa quản trị VM vào quy trình rõ ràng, tự động hóa các bước rủi ro và cải thiện khả năng phục hồi thường là ưu tiên cao hơn thay đổi công nghệ chỉ để “cloud-native”.

## 6. Sai lầm ở chi phí: tính tiền VM mà bỏ qua toàn bộ vòng đời

### 6.1. TCO trên cloud gồm nhiều hạng mục

Tùy nhà cung cấp và loại dịch vụ, tổng chi phí vận hành (*total cost of ownership*, TCO) có thể gồm:

| Nhóm | Thành phần cần đưa vào dự toán | Vì sao dễ bị bỏ sót? |
| --- | --- | --- |
| Compute | VM, phí bản quyền, máy chủ dự phòng, instance bật cả ngoài giờ | Chọn theo số core máy vật lý cũ, không xét thời gian sử dụng |
| Storage | Dung lượng block/object, loại ổ, IOPS/throughput bổ sung, snapshot, version/retention | Giá trên GB không phản ánh hiệu năng và số phiên bản sao lưu |
| Network | Internet egress, truyền liên vùng/liên khu vực, NAT gateway, LB, endpoint, VPN/kết nối riêng | Một request đi qua nhiều hop có thể phát sinh nhiều mục phí |
| Observability | Ingestion log, lưu trữ dài hạn, truy vấn log, metric tùy biến, trace | Bật thu thập toàn bộ debug log liên tục |
| Bảo mật và vận hành | Key management, hệ thống quản trị, quét lỗ hổng, công cụ vận hành, nhân lực trực | Chỉ tính hóa đơn hạ tầng, thiếu chi phí vận hành |
| Di chuyển và song song | Công cụ migration, thử nghiệm, đồng bộ, môi trường tạm và phí hai hệ cùng chạy | Không có mốc dừng hạ tầng cũ |
| Khôi phục | Sao lưu độc lập, replica, môi trường DR và kiểm thử restore | Xem backup/DR như tính năng có sẵn miễn phí |

Chi phí theo khu vực, loại tài nguyên, thời điểm, cam kết sử dụng và hợp đồng có thể khác nhau. Khi lập ngân sách thực, phải dùng bảng giá hiện hành và tính phí theo đường đi dữ liệu thực tế; không dựa vào một con số chung cho mọi cloud.

### 6.2. Ví dụ định lượng (đơn giá hoàn toàn giả định)

Giả sử sau rehost có 10 VM bật liên tục, 5 TiB block storage và 3 TiB dữ liệu đi Internet mỗi tháng. Để minh họa cách kiểm tra, **giả định** đơn giá VM là 0,30 USD/giờ, block storage là 0,10 USD/GiB-tháng và Internet egress là 0,08 USD/GiB. Tháng được quy đổi 730 giờ và 1 TiB = 1.024 GiB.

| Khoản | Phép tính | Ước tính/tháng |
| --- | --- | ---: |
| VM | 10 × 730 × 0,30 | 2.190,00 USD |
| Block storage | 5 × 1.024 × 0,10 | 512,00 USD |
| Internet egress | 3 × 1.024 × 0,08 | 245,76 USD |
| **Tổng minh họa chưa đầy đủ** | | **2.947,76 USD** |

Đây **không phải báo giá** của nhà cung cấp nào. Con số trên chưa có phí truyền liên zone, LB, NAT, backup, log, DB license, hỗ trợ, nhân sự, thuế hoặc phần hạ tầng on-premises còn chạy.

Chỉ riêng 10 VM luôn bật ở ví dụ này tạo khoảng 2.190 USD/tháng. Nếu sau đo tải thực có thể giảm số VM tương đương từ 10 xuống 7 (vẫn đạt SLO và HA), tiền VM giả định giảm khoảng **657 USD/tháng**, chưa xét các khoản khác. Không được cắt máy dự phòng chỉ để giảm chi phí khi nó đang bảo đảm yêu cầu sẵn sàng.

### 6.3. Các đòn bẩy tối ưu và đánh đổi

| Biện pháp | Lợi ích có thể có | Điều kiện/đánh đổi |
| --- | --- | --- |
| Rightsizing theo dữ liệu tải | Tránh overprovision CPU/RAM, disk và IOPS | Cần quan sát giờ cao điểm, headroom, thử tải; VM nhỏ hơn có thể giảm băng thông |
| Tự động scale hoặc tắt môi trường phi sản xuất | Giảm tài nguyên nhàn rỗi | Cần stateless, health check, thời gian khởi động, tránh ảnh hưởng công việc |
| Cam kết sử dụng/reservation/savings plan tùy dịch vụ | Giảm đơn giá phần tải nền ổn định | Mất linh hoạt khi cấu trúc workload đổi; nên có baseline trước khi cam kết |
| Chọn đúng storage tier và lifecycle | Tránh dùng ổ/retention đắt không cần thiết | Yêu cầu truy xuất, IOPS, backup và compliance vẫn phải đáp ứng |
| Giảm giao tiếp liên vùng/liên khu vực, cache có kiểm soát | Giảm egress và latency | Không làm giảm độ sẵn sàng hoặc phá tính nhất quán nghiệp vụ |
| Phân bổ chi phí bằng tag, budget, cảnh báo | Nhận diện service/owner gây tăng phí | Quy tắc tagging và báo cáo phải được duy trì |
| Thu hồi VM, disk, IP, LB, snapshot tạm | Cắt chi phí còn sót sau dự án | Cần kiểm tra liên kết, chính sách giữ dữ liệu và bằng chứng decommission |

Một mục tiêu quan trọng là **chi phí trên đơn vị giá trị**, ví dụ USD/1.000 đơn hàng hoàn tất hoặc USD/1 triệu API request hợp lệ, kết hợp với SLO. Tổng hóa đơn giảm nhưng tỷ lệ giao dịch lỗi tăng không phải tối ưu.

## 7. Thiết kế lại theo yêu cầu, không theo cấu hình máy chủ cũ

Thay vì hỏi “VM này dùng instance nào?”, hãy xác định:

1. **Yêu cầu nghiệp vụ:** số lượng người dùng, giao dịch/giây, thời điểm cao điểm, khu vực phục vụ, SLA hợp đồng.
2. **Yêu cầu phi chức năng:** độ trễ p95/p99, availability, RPO/RTO, data residency, bảo mật, audit, thời gian deploy, ngân sách.
3. **Thực trạng:** đồ thị phụ thuộc, lượng dữ liệu, throughput, IOPS, pattern truy cập, lỗi thường gặp, chi phí vận hành on-premises.
4. **Phương án kiến trúc:** giữ nguyên VM với guardrail, điều chỉnh topology/data placement, chuyển DB sang managed service, hoặc hiện đại hóa từng chức năng.
5. **Quyết định có bằng chứng:** kiểm thử tải và phục hồi, tổng chi phí, rủi ro di chuyển, khả năng đảo ngược, người chịu trách nhiệm.

### Một bảng quyết định minh họa

| Phương án | Tốc độ di chuyển | Thay đổi ứng dụng | Ưu điểm | Giới hạn cần kiểm chứng |
| --- | --- | --- | --- | --- |
| **A. Rehost nguyên trạng**, DB còn on-premises | Thường nhanh ở bước VM | Thấp | Giảm công sửa mã | Độ trễ hybrid, điểm lỗi mạng, hai môi trường, chi phí dài hạn |
| **B. Rehost theo nhóm phụ thuộc**, chuyển DB gần app | Trung bình | Thấp–vừa | Giảm round trip; ít phụ thuộc mạng hybrid trong đường giao dịch | Cutover dữ liệu, bản quyền, backup, HA, consistency |
| **C. Replatform một phần**, ví dụ DB managed, app vẫn trên VM | Trung bình | Vừa | Giảm một số việc vận hành DB; có thể tận dụng HA/backup tích hợp | Tương thích DB, phương thức migration, giới hạn và chi phí dịch vụ |
| **D. Refactor dần theo miền nghiệp vụ** | Dài hơn | Cao | Có cơ hội scale/triển khai độc lập và tối ưu sâu | Độ phức tạp chương trình, phân chia dữ liệu, rủi ro thay đổi nghiệp vụ |

Không có phương án mặc định thắng ở mọi trụ cột. Với ứng dụng ít thay đổi, deadline sát và lưu lượng thấp, A có thể đủ nếu SLO và vận hành được bảo đảm; với hệ thống giao dịch nhiều lượt DB, B hoặc C có thể đem lại lợi ích lớn hơn ngay cả khi chưa thay đổi kiến trúc nghiệp vụ.

### Ví dụ quyết định được ghi thành ADR

> **Bối cảnh:** Ứng dụng đơn hàng hiện gọi CSDL 25 lần tuần tự/request; đo thử trên hybrid làm tăng p95 420–500 ms. Mục tiêu p95 dưới 800 ms; thời gian chuyển đổi tối đa một đêm bảo trì.
>
> **Quyết định:** Chuyển app và CSDL cùng đợt với snapshot + CDC theo cutover đã kiểm chứng; vận hành app trên VM trước, chưa tách microservice. Dùng mạng riêng, LB, quan sát tập trung và backup có kiểm thử.
>
> **Đánh đổi:** Tăng công việc chuyển dữ liệu và diễn tập cutover; giảm phụ thuộc hybrid cho request thường ngày. Còn nợ kỹ thuật ở khả năng scale ngang; lên kế hoạch xử lý sau khi có baseline cloud.
>
> **Tiêu chí xác nhận:** p95 dưới 800 ms ở tải mục tiêu, không mất dữ liệu vượt RPO đã thống nhất, phục hồi đạt RTO đã thử, dự toán chi phí có đủ compute/storage/network/operations.

ADR là bằng chứng về **lý do chọn phương án, giới hạn và cách kiểm chứng**, không chỉ sơ đồ cuối cùng.

## 8. Quy trình gỡ phản mẫu theo từng giai đoạn

Không nhất thiết phải refactor toàn bộ trước khi lên cloud. Có thể chuyển từ một dự án “copy VM” sang di chuyển có kiểm soát theo các cổng quyết định:

| Giai đoạn | Công việc chính | Bằng chứng cần có trước khi tiếp tục |
| --- | --- | --- |
| **1. Discovery và baseline** | Kiểm kê ứng dụng, phụ thuộc, data flow, SLO, tải đỉnh, chi phí và rủi ro. | Dependency map, baseline performance/cost, owner từng hệ thống. |
| **2. Landing zone và thiết kế mạng** | Quy hoạch account, IAM, CIDR, route, DNS, ingress/egress, logging, bảo mật và kết nối hybrid. | Sơ đồ luồng, threat review, kiểm tra kết nối và dự toán egress. |
| **3. Pilot / thử tải** | Di chuyển một workload đại diện; đo latency, IOPS, failover, backup restore và chi phí dự kiến. | Kết quả so với SLO, nhật ký lỗi, quyết định sizing/topology. |
| **4. Di chuyển theo nhóm phụ thuộc** | Cutover app và dữ liệu theo wave; chuẩn bị rollback/roll forward, xác minh chức năng. | Runbook, cửa sổ chuyển đổi, giám sát và quyết định go/no-go. |
| **5. Ổn định và tối ưu** | Quan sát nhiều chu kỳ tải, rightsizing, điều chỉnh storage/network, tự động hóa. | Báo cáo KPI/SLO và unit cost, thay đổi được kiểm thử. |
| **6. Thu hồi hệ cũ** | Xác minh không còn phụ thuộc, lưu trữ theo chính sách, hủy tài nguyên và hợp đồng thừa. | Biên bản decommission, kiểm tra dữ liệu/backup và báo cáo chi phí cuối. |

### Giai đoạn 1: đo baseline trước khi mất mốc so sánh

Đo theo lưu lượng thật và các ngày cao điểm: thời gian phản hồi, throughput, lỗi, số kết nối DB, query count, độ trễ mạng, IOPS, disk queue, khối lượng log và dung lượng backup. Nếu không có baseline, khi cloud chậm hoặc đắt hơn sẽ khó phân biệt sự cố do di chuyển hay do tải nghiệp vụ tăng.

### Giai đoạn 2: dựng nền tảng an toàn

Thiết lập landing zone tối thiểu: phân môi trường, tài khoản/role, private network, subnet, firewall, audit trail, secret management, tags và ngân sách. Xác minh luồng vào/ra, DNS, CIDR và tính sẵn sàng của hybrid. Viết sơ đồ kiến trúc cả đường dữ liệu lẫn đường điều khiển (deploy, quản trị, sao lưu).

### Giai đoạn 3: pilot đúng rủi ro

Không chỉ ping hay mở giao diện web. Pilot cần mô phỏng số lượng truy vấn, dữ liệu, peak load và lỗi của workload thực. Đo ít nhất các luồng giao dịch quan trọng, thử lỗi VM/zone/kết nối, restore từ backup và quan sát hóa đơn mẫu. Điều chỉnh topology trước khi di chuyển hàng loạt.

### Giai đoạn 4: cutover có phương án phục hồi

Xác định phạm vi traffic, hệ thống ghi có thẩm quyền, phương pháp đồng bộ dữ liệu nếu chuyển DB, điểm chốt, thời gian DNS cache và đường quay lui. Nếu đã nhận dữ liệu mới trên cloud, quay về on-premises đòi cơ chế bảo toàn dữ liệu phát sinh mới; trỏ DNS ngược không giải quyết mất dữ liệu. Mở traffic theo canary khi phù hợp và theo dõi SLO ngay sau chuyển.

### Giai đoạn 5–6: tối ưu và kết thúc

Đánh giá sizing từ metric sau di chuyển, cắt tài nguyên thừa, tối ưu luồng mạng và log retention, bổ sung tự động phục hồi nếu có lợi. Có ngày kết thúc giai đoạn chạy song song. Kiểm tra các đường phụ thuộc và yêu cầu lưu trữ trước khi hủy hệ cũ.

## 9. Đánh giá với Well-Architected

| Trụ cột | Câu hỏi đánh giá rehost | Bằng chứng tốt |
| --- | --- | --- |
| **Operational Excellence** | Có runbook, IaC, phân quyền triển khai, logging/tracing và người trực sự cố không? | SLO/dashboard, pipeline, diễn tập sự cố, chủ sở hữu alert. |
| **Security** | Đường mạng, IAM, secret, mã hóa, backup và audit có đáp ứng kiểm soát mới không? | Sơ đồ trust boundary, policy/IAM review, log truy cập, kiểm tra cấu hình. |
| **Reliability** | Các thành phần còn điểm lỗi đơn nào; RPO/RTO đã được kiểm chứng chưa? | Sơ đồ failure domain, kết quả failover/restore, recovery runbook. |
| **Performance Efficiency** | Vị trí dữ liệu, round trip và giới hạn CPU/IOPS/network có hợp tải thật không? | Load test, trace, p95/p99, capacity plan và sizing dựa metric. |
| **Cost Optimization** | Có dự toán TCO và đơn vị chi phí theo giá trị, cảnh báo ngân sách và lịch tối ưu không? | Cost breakdown, tags, forecast, báo cáo unit cost và dọn tài nguyên. |
| **Sustainability** | Có lãng phí compute chạy không tải, lưu trữ dư thừa và tài nguyên tạm chưa thu hồi không? | Utilization, lifecycle policy, kế hoạch rightsizing/decommission. |

Sáu trụ cột cần được cân bằng. Ví dụ, đặt mọi VM trên một zone có thể giảm một phần phí truyền liên zone nhưng làm tăng rủi ro gián đoạn; chạy đa zone cải thiện khả năng chịu lỗi theo thiết kế phù hợp nhưng phát sinh chi phí và công vận hành. Chọn phương án theo **SLO và rủi ro nghiệp vụ**, rồi đo cả chi phí lẫn mức bảo vệ đạt được.

## 10. Những “cách chữa” sai dễ tạo phản mẫu mới

| Phản ứng vội | Vì sao chưa đủ | Cách tiếp cận thích hợp hơn |
| --- | --- | --- |
| Tăng cỡ tất cả VM khi app chậm | Chậm có thể do 25 round trip tới DB hoặc giới hạn mạng, không phải CPU. | Dùng trace, metric DB và network để định vị nút thắt trước khi scale. |
| Đưa một cache vào giữa mọi lời gọi | Cache không giải quyết write consistency; invalidation phức tạp. | Phân loại đọc/ghi, chọn TTL/invalidation và đặt dữ liệu có thẩm quyền hợp lý. |
| Bật đa zone cho app rồi tuyên bố HA | DB, kết nối hybrid hoặc session vẫn có thể là điểm lỗi đơn. | Lập failure-mode matrix cho toàn đường giao dịch và thử failover end-to-end. |
| Mua cam kết VM dài hạn ngay sau migration | Workload chưa rightsizing có thể khóa chi phí quá mức. | Đo baseline thực tế, xác định phần tải nền ổn định rồi mới cam kết. |
| Chuyển tất cả sang Kubernetes/microservice ngay | Tăng rủi ro và công sức khi chưa sửa nguyên nhân mạng, dữ liệu, vận hành. | Ưu tiên tối ưu có tác động rõ; replatform/refactor khi có lợi ích và năng lực vận hành. |
| Tắt on-premises ngay khi ứng dụng mới trả HTTP 200 | Có thể còn batch job, consumer, lịch backup hoặc DB replication chưa chuyển. | Xác minh luồng nghiệp vụ, phụ thuộc và dữ liệu trong đủ chu kỳ trước decommission. |

## 11. Bài tập tình huống: chọn phương án cho hệ thống đặt hàng

**Đề bài.** Một doanh nghiệp có 12 VM ứng dụng, CSDL 6 TiB và hệ thống quản lý người dùng ở trung tâm dữ liệu. Đội dự án cần rời cơ sở cũ trong ba tháng, không có nguồn lực viết lại ứng dụng. Giờ cao điểm ứng dụng xử lý 500 yêu cầu/giây; trung bình một yêu cầu thực hiện 20 truy vấn CSDL tuần tự. Thử nghiệm hybrid cho thấy round trip từ cloud về DB là 16 ms so với 2 ms trong data center. Mục tiêu p95 phản hồi dưới 1 giây, RPO 15 phút và RTO 1 giờ; ngân sách cloud có giới hạn.

### Phân tích vấn đề

Chênh lệch độ trễ mạng trên đường truy vấn tuần tự ước tính:

\[
20 \times (16 - 2) = 280\ \text{ms/request}
\]

Con số giả định này chưa gồm truy vấn chạy trên DB và xử lý app. Nó đủ để đặt dấu hỏi về lựa chọn **app trên cloud, DB giữ on-premises** nếu SLO đang sát 1 giây. Tăng CPU app chưa chắc cải thiện phần 280 ms này. Mặt khác, di chuyển DB 6 TiB đòi kế hoạch chuyển dữ liệu, kiểm tra tính nhất quán và cutover có kiểm soát.

### Một phương án tham khảo

1. **Discovery:** đo trace thật để xác nhận 20 truy vấn có tuần tự hay không; lập dependency map của DB, danh tính, báo cáo và batch job. Kiểm tra yêu cầu dữ liệu và cách xác thực xuyên hybrid.
2. **Thiết kế:** ưu tiên đưa app gần DB theo nhóm phụ thuộc hoặc di chuyển DB gần app khi khả thi; nếu còn phụ thuộc danh tính on-premises, dùng kết nối hybrid có đường dự phòng, timeout và quan sát. Chưa yêu cầu viết lại mã nghiệp vụ.
3. **Compute/HA:** dựng LB, VM ở nhiều zone nếu SLO yêu cầu và ứng dụng hỗ trợ; kiểm tra session state. Thiết kế DB replication, backup/restore và failure domain tương ứng với RPO/RTO.
4. **Vận hành:** chuẩn bị IaC, quyền IAM tối thiểu, giám sát end-to-end, runbook và thử phục hồi. Đo lại p95 ở tải 500 req/s, tải đỉnh đã khảo sát và khi một thành phần lỗi.
5. **Chi phí:** ước tính từng thành phần VM, DB/storage, đồng bộ, backup, hybrid, NAT/LB, log và vận hành; lập budget/tag và kế hoạch rightsizing sau cutover.
6. **Chuyển đổi:** pilot, lập lịch di chuyển dữ liệu, kiểm chứng tính nhất quán, xác định write owner và phương án quay lui/tiến tới an toàn. Chỉ decommission khi đối soát và giám sát đạt tiêu chí.

### Câu hỏi tự kiểm tra

1. Vì sao chuyển 12 VM cùng cấu hình sang cloud không đủ để khẳng định ứng dụng đáp ứng SLO?
2. Nếu app đã ở hai zone nhưng DB chỉ có một instance trong một zone, rủi ro còn lại là gì?
3. Vì sao phải tính dữ liệu truyền giữa cloud và on-premises khi so sánh hai phương án?
4. Trong ba tháng, nếu không thể refactor, những thay đổi nào vẫn có thể giảm rủi ro?
5. Nên đo chỉ số nào để nhận biết việc cắt giảm VM là tiết kiệm thật và không phá trải nghiệm người dùng?

**Gợi ý trả lời:** (1) còn độ trễ, IO/network, hiệu năng DB, phân bố tải và lỗi phụ thuộc; (2) DB vẫn là điểm lỗi đơn cho giao dịch; (3) ảnh hưởng cả latency, độ tin cậy và hóa đơn egress/kết nối; (4) cải thiện vị trí dữ liệu, routing, IAM, backup, HA, observability, IaC và runbook; (5) unit cost đi cùng tỷ lệ giao dịch thành công, p95/p99, saturation và độ sẵn sàng.

## 12. Checklist rà soát một kế hoạch rehost

### Trước khi di chuyển

- [ ] Có mục tiêu nghiệp vụ, deadline, tiêu chí thành công và SLO đo được.
- [ ] Đã lập dependency map, data flow, ingress/egress và vị trí dữ liệu có thẩm quyền.
- [ ] Có baseline hiệu năng ở tải thường, tải đỉnh, lỗi phổ biến và chi phí hiện tại.
- [ ] Đã xác minh CIDR, routing, DNS, TLS, firewall, IAM và kết nối hybrid dự phòng nếu cần.
- [ ] Đã tính rủi ro round trip với DB và các hệ thống đồng bộ trong đường giao dịch.
- [ ] Có mô hình failure domain, RPO/RTO, backup/restore và kế hoạch DR thực tế.
- [ ] Có dự toán compute, storage, data transfer, LB/NAT, log, backup và thời gian chạy song song.

### Trong cutover

- [ ] Pilot/load test chứng minh SLO, không chỉ kiểm tra máy chủ khởi động.
- [ ] Có runbook, checklist go/no-go, chủ sở hữu, đường rollback/roll forward và cách bảo vệ dữ liệu.
- [ ] Đã bật metric, log, trace và cảnh báo theo giao dịch; có người theo dõi sau chuyển.
- [ ] Đã thử các trường hợp lỗi mạng, VM, DB và khôi phục từ backup.

### Sau cutover

- [ ] Theo dõi SLO và chi phí trong đủ chu kỳ tải, so với baseline trước di chuyển.
- [ ] Rightsizing dựa trên số đo; tối ưu luồng mạng, IOPS, lưu log và tài nguyên nhàn rỗi.
- [ ] Có danh sách nợ kỹ thuật, chủ sở hữu và mốc xem xét replatform/refactor nếu cần.
- [ ] Xác nhận đã chuyển hết dependency, lưu trữ dữ liệu đúng chính sách rồi thu hồi tài nguyên cũ.

**Nguyên tắc cần nhớ:** rehost giải quyết câu hỏi *chạy ứng dụng ở đâu*; kiến trúc cloud còn phải giải quyết *dữ liệu đi qua mạng nào, hệ thống chịu lỗi ra sao, ai vận hành và trả chi phí gì*. Khi các câu hỏi sau không được kiểm chứng, một cuộc di chuyển kỹ thuật thành công vẫn có thể trở thành thất bại về hiệu năng, độ tin cậy và ngân sách.

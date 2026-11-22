# Lựa chọn vị trí theo độ trễ, khả dụng và lưu trú dữ liệu

Chọn nơi triển khai là một quyết định kiến trúc quan trọng khi xây dựng hệ thống trên Google Cloud. Region gần người dùng có thể mang lại phản hồi nhanh hơn, nhưng hệ thống còn phải chịu được sự cố, đáp ứng yêu cầu lưu trú dữ liệu và hoạt động trong giới hạn chi phí. Quyết định này ảnh hưởng tới Compute Engine, Google Kubernetes Engine (GKE), Cloud Run, dịch vụ lưu trữ, cơ sở dữ liệu, VPC, mạng và cách vận hành.

Trong chương **Hệ thống tài nguyên và vị trí**, chúng ta phân tích ba câu hỏi:

1. **Độ trễ:** Người dùng và các thành phần của ứng dụng mất bao lâu để trao đổi dữ liệu?
2. **Khả dụng:** Hệ thống tiếp tục phục vụ hoặc khôi phục trong bao lâu khi một zone hay cả region gặp sự cố?
3. **Lưu trú dữ liệu:** Dữ liệu gốc, bản sao, bản sao lưu và dữ liệu xử lý được phép nằm ở đâu?

Sau bài học, bạn có thể phân biệt phạm vi vị trí của tài nguyên Google Cloud, xây dựng danh sách region phù hợp, đo độ trễ có ý nghĩa và lập luận về giải pháp dự phòng cùng ràng buộc dữ liệu.

## 1. Vị trí tài nguyên không đồng nghĩa vị trí project

Google Cloud tổ chức tài nguyên quản trị theo **organization → folder → project → resource**. Cấu trúc này phục vụ chính sách, phân quyền IAM và quản lý chi phí. Project không tự gắn mọi tài nguyên bên trong vào một region; mỗi dịch vụ có phạm vi vị trí riêng.

| Khái niệm | Ý nghĩa khi thiết kế | Điều cần chú ý |
| --- | --- | --- |
| **Region** | Khu vực địa lý để đặt các dịch vụ theo vùng. | Dịch vụ, cấu hình, giá và quota có thể khác nhau giữa các region. |
| **Zone** | Miền triển khai bên trong region, dùng cho các tài nguyên như VM Compute Engine. | Các zone trong một region tách biệt một số dạng sự cố nhưng vẫn có rủi ro chung cấp region. |
| **Dual-region / multi-region** | Loại vị trí một số dịch vụ hỗ trợ để lưu hoặc nhân bản dữ liệu trên phạm vi rộng hơn một region. | Cơ chế nhân bản, độ trễ, cách chuyển đổi và giới hạn tùy dịch vụ. |
| **Global resource / global endpoint** | Tài nguyên hoặc điểm vào có phạm vi toàn cầu, ví dụ VPC network hoặc một số loại load balancer. | Global không bảo đảm dữ liệu khách hàng được lưu tại một nơi tùy chọn hoặc ở mọi nơi. |
| **Edge / CDN** | Điểm hiện diện gần người truy cập để nhận yêu cầu hoặc lưu đệm nội dung. | Vị trí edge khác vị trí backend, cơ sở dữ liệu và nội dung được cache. |

Ví dụ, một hệ thống có thể sử dụng VPC network toàn cục, subnet theo region, VM tại một zone, Cloud Run tại một region khác và Cloud Storage bucket với location được cấu hình riêng. IAM trên project có thể cấp quyền cho các tài nguyên này nhưng không biến chúng thành tài nguyên cùng vị trí.

| Dịch vụ | Vị trí thường phải chọn | Lưu ý |
| --- | --- | --- |
| Compute Engine | Zone cho VM; một số nhóm instance có thể trải nhiều zone | Tránh phụ thuộc một VM hoặc zone khi cần HA. |
| GKE | Zonal hoặc regional cluster; vị trí node cũng quan trọng | Regional cluster giúp chịu lỗi zone, không thay thế phục hồi sự cố cả region. |
| Cloud Run | Region để chạy dịch vụ | Cân nhắc vị trí của database và các dịch vụ được gọi nhiều. |
| Cloud SQL | Region và thiết lập zone, HA/replica theo cấu hình | HA nội region và dự phòng liên region giải quyết những rủi ro khác nhau. |
| Cloud Storage | Region, dual-region hoặc multi-region tùy loại location | Kiểm tra quy tắc sao chép, vị trí dữ liệu và phí truyền dữ liệu. |
| BigQuery | Location của dataset và những job liên quan | Không giả định mọi truy vấn hoặc di chuyển giữa các location đều được phép và thực hiện trực tiếp. |
| Cloud Spanner | Cấu hình instance regional hoặc multi-region | Cân nhắc vị trí replica, tính nhất quán, độ trễ và chi phí. |

Danh sách sản phẩm, loại máy, cấu hình và tính năng hỗ trợ theo region có thể thay đổi. Một region có Compute Engine không có nghĩa mọi dịch vụ Google Cloud đều hỗ trợ cấu hình cần dùng tại đó.

## 2. Độ trễ: đo cả đường đi của một yêu cầu

### 2.1. Region gần người dùng chưa chắc cho ứng dụng nhanh nhất

Thời gian phản hồi gồm truyền mạng từ client, load balancer/điểm biên, xử lý ứng dụng, truy vấn cơ sở dữ liệu, lời gọi dịch vụ phụ thuộc và truyền kết quả. Với các bước nối tiếp, có thể mô hình hóa gần đúng:

**T phản hồi ≈ T mạng client + T backend + tổng thời gian chờ dịch vụ phụ thuộc + T trả kết quả.**

Đây là cách tư duy để tìm nút thắt, không phải công thức cố định: lời gọi song song, cache, kích thước dữ liệu và việc tái sử dụng kết nối đều ảnh hưởng tới kết quả.

~~~mermaid
flowchart LR
    U["Người dùng"] --> E["Điểm vào / load balancer"]
    E --> A["API ở region A"]
    A --> D[("Database ở region A")]
    A -. "Lời gọi xuyên region" .-> S[("Dịch vụ ở region B")]
~~~

Chuyển API tới gần người dùng không giải quyết được nút thắt nếu API vẫn phải gọi database ở xa nhiều lần theo chuỗi. Cân bằng tải toàn cầu và CDN có thể hỗ trợ phân phối lưu lượng, nhưng không tự chuyển dữ liệu backend hoặc loại bỏ chi phí mạng giữa các region.

**Nguyên tắc:** giữ những thành phần thường xuyên trao đổi dữ liệu gần nhau, đồng thời chọn điểm vào thích hợp với nơi người dùng thực sự truy cập.

### 2.2. Chọn phép đo có ý nghĩa nghiệp vụ

Trước khi quyết định, hãy thử một bản ứng dụng đủ giống production:

1. **Định vị nguồn truy cập:** số lượng người dùng theo thành phố/quốc gia, nhà mạng di động hay cố định, giờ cao điểm và vị trí đối tác tích hợp.
2. **Lập danh sách region ứng viên:** bước đầu chỉ giữ các region có dịch vụ cần dùng và đáp ứng các điều kiện bắt buộc về dữ liệu.
3. **Triển khai thử tương đương:** cùng API, cấu hình tài nguyên, endpoint HTTPS, kích thước payload và các truy vấn database điển hình.
4. **Đo từ nhiều mạng:** lấy mẫu cả ở thời điểm cao điểm và thấp điểm; ghi thời gian phản hồi, lỗi, throughput và lời gọi xuyên region.
5. **Đánh giá phân vị:** p50 phản ánh nhóm yêu cầu thông thường; p95 và p99 bộc lộ trải nghiệm chậm mà giá trị trung bình che khuất.
6. **Kiểm tra dưới tải:** thử khi cache miss, tăng đột biến số yêu cầu, kết nối được tái sử dụng và dependency bị chậm.

Ví dụ lệnh đo thời gian một yêu cầu HTTPS:

~~~bash
curl -s -o /dev/null \
  -w 'connect=%{time_connect}s first_byte=%{time_starttransfer}s total=%{time_total}s\n' \
  https://example.test/health
~~~

Đây chỉ là một mẫu quan sát từ máy đang chạy lệnh. Endpoint health check thường không thực hiện đủ các bước xác thực, truy vấn và xử lý nghiệp vụ. Do đó cần lấy nhiều mẫu với API đại diện từ mạng người dùng thực tế; không dùng một lần ping làm kết luận.

### 2.3. Ví dụ so sánh độ trễ

Giả sử một dịch vụ bán hàng phục vụ người dùng tại Hà Nội và TP. Hồ Chí Minh, API cần đạt p95 dưới 250 ms. Nhóm chọn hai region ứng viên sau khi xác minh phạm vi dữ liệu và dịch vụ hỗ trợ. Kết quả dưới đây **hoàn toàn giả định**, không phải chỉ số hiệu năng của Google Cloud:

| Phép đo | Region A | Region B |
| --- | ---: | ---: |
| p95 phản hồi API từ mạng người dùng đại diện | 145 ms | 195 ms |
| p95 hoàn tất thao tác cần nhiều truy vấn DB | 220 ms | 310 ms |
| Thành phần gọi thường xuyên cùng region với API | Có | Không |

Với mục tiêu p95 dưới 250 ms, A phù hợp hơn trong phép đo minh họa. Tuy nhiên, nếu A không đáp ứng chính sách dữ liệu, quota, yêu cầu khả dụng hoặc tính năng của dịch vụ, A phải bị loại dù nhanh hơn.

## 3. Khả dụng: phân biệt lỗi zone và lỗi region

Khả dụng là khả năng hệ thống tiếp tục cung cấp dịch vụ. Khôi phục thảm họa là khả năng đưa hệ thống trở lại sau sự cố nghiêm trọng. Một thiết kế tốt phải xác định rõ dạng sự cố cần chịu được và mức tổn thất nghiệp vụ chấp nhận được.

- **SLO:** mục tiêu chất lượng dịch vụ, chẳng hạn tỷ lệ yêu cầu thành công hoặc độ trễ trong một khoảng đo.
- **RTO (Recovery Time Objective):** thời gian tối đa chấp nhận được để phục hồi sau khi dịch vụ gián đoạn.
- **RPO (Recovery Point Objective):** khoảng thời gian dữ liệu cập nhật tối đa có thể bị mất khi khôi phục.
- **Failure domain:** phạm vi sự cố như instance, zone, region, ứng dụng, mạng, thao tác vận hành hoặc sai dữ liệu.

| Kiến trúc | Chịu lỗi tốt hơn đối với | Hạn chế |
| --- | --- | --- |
| Một VM/database ở một zone | Ít dự phòng | Hỏng VM, zone hoặc bảo trì có thể làm dịch vụ ngừng. |
| Ứng dụng phân tán qua các zone trong một region | Hỏng một số instance hoặc một zone | Vẫn có rủi ro chung cấp region; dữ liệu cũng cần HA. |
| Triển khai tại nhiều region | Một số sự cố diện rộng mất cả region | Phải xử lý nhân bản dữ liệu, chuyển traffic, nhất quán, quota, vận hành và kiểm thử. |

Ví dụ, có thể dùng regional managed instance group cho Compute Engine hoặc regional cluster cho GKE để chịu lỗi một số zone. Với Cloud SQL, cấu hình HA nội region khác với read replica xuyên region. Tính năng chuyển vai trò, mức mất dữ liệu và thời gian khôi phục phụ thuộc dịch vụ cùng cấu hình. **Bật HA hoặc tạo replica chưa tự động hoàn thành quy trình khôi phục liên region.**

~~~mermaid
flowchart TB
    C["Người dùng / điểm vào"] --> R1
    C -. "Chuyển hướng khi gặp sự cố" .-> R2
    subgraph R1["Region chính"]
      A1["API - zone 1"] --> DB1[("Database chính")]
      A2["API - zone 2"] --> DB1
    end
    subgraph R2["Region dự phòng"]
      A3["API dự phòng"] --> DB2[("Bản sao / dữ liệu khôi phục")]
    end
    DB1 -. "Nhân bản hoặc backup theo chính sách" .-> DB2
~~~

Sơ đồ là mục tiêu thiết kế, không đại diện cho một cấu hình tự động có sẵn của mọi database. Một số cơ chế nhân bản bất đồng bộ có thể dẫn đến mất những cập nhật chưa được sao chép; chuyển hướng traffic có thể yêu cầu thao tác thủ công hoặc xác nhận tính nhất quán.

Muốn phục hồi tại region khác, phải chuẩn bị đủ container image hoặc bản phát hành, cấu hình, bí mật, IAM, network, DNS/load balancer, cơ sở dữ liệu, hạn mức tài nguyên, giám sát và quy trình chuyển đổi. Có dữ liệu dự phòng mà ứng dụng không thể khởi động tại vùng đó thì vẫn chưa đạt RTO.

**Ba tình huống cần thử riêng biệt:**

1. **Mất một zone:** các instance tại zone còn lại tiếp tục phục vụ nếu ứng dụng, cân bằng tải và dữ liệu được thiết kế HA.
2. **Mất cả region:** thiết kế chỉ phân tán nhiều zone trong một region có thể ngừng hoạt động; cần phương án ở region khác nếu nghiệp vụ yêu cầu.
3. **Xóa nhầm hoặc cập nhật sai dữ liệu:** replica có thể sao chép cả sai sót. Cần backup/khôi phục theo thời điểm, kiểm soát quyền và diễn tập restore.

Không mặc định multi-region luôn là lựa chọn tối ưu. Nó tăng chi phí, độ phức tạp vận hành, khó khăn điều phối dữ liệu và đôi khi tăng độ trễ ghi. Số region, cách nhân bản và tự động hóa failover phải xuất phát từ RTO/RPO, SLO và mức thiệt hại chấp nhận được.

## 4. Lưu trú dữ liệu: kiểm tra từng bản sao và luồng xử lý

**Data residency** là yêu cầu xác định vị trí địa lý nơi những loại dữ liệu thuộc phạm vi áp dụng được lưu trữ hoặc xử lý theo chính sách và cam kết cụ thể. Khái niệm này cần phân biệt với **data sovereignty** (yêu cầu về quyền tài phán và quyền kiểm soát), phân quyền IAM và mã hóa dữ liệu. Chọn một region hoặc bật mã hóa **không tự động chứng minh** hệ thống đáp ứng mọi yêu cầu pháp lý.

Một số sản phẩm có phạm vi cam kết khác nhau đối với dữ liệu khách hàng, metadata, backup, hỗ trợ và nơi thực hiện các bước xử lý. Vì vậy câu hỏi đúng không chỉ là “database đặt ở đâu?” mà còn là “dữ liệu xuất hiện ở những đâu trong toàn bộ vòng đời?”

| Dạng dữ liệu | Câu hỏi cần xác minh |
| --- | --- |
| Database, object storage | Instance/bucket, bản sao và vị trí khôi phục nằm ở đâu? |
| Backup, snapshot và replica | Được lưu ở location nào, có sao chép xuyên biên giới không? |
| Log, trace, metric, crash dump | Có chứa IP, email, payload hay dữ liệu cá nhân không; lưu ở đâu và bao lâu? |
| Pipeline, BI, AI, cache, file tạm | Job xử lý và dữ liệu trung gian thực thi/lưu tại location nào? |
| CDN và điểm biên | Dữ liệu gì được cache/phân phối ở edge, ở đâu, bao lâu và có được phép không? |
| Dịch vụ bên thứ ba | Webhook, cổng thanh toán, gửi email, công cụ phân tích nhận dữ liệu ở quốc gia nào? |

Ví dụ, database có thể ở một region được phép, nhưng pipeline phân tích trích dữ liệu cá nhân sang dataset BigQuery ở location khác. Chọn đúng nơi cho database vẫn chưa đảm bảo toàn bộ luồng dữ liệu hợp lệ.

### 4.1. Chính sách organization không thay thế kiểm chứng sản phẩm

Google Cloud cho phép áp chính sách thông qua cấu trúc organization/folder/project. Constraint Organization Policy **gcp.resourceLocations** có thể giới hạn nơi tạo một số loại tài nguyên mà constraint hỗ trợ. Cần kiểm tra việc áp dụng cho từng dịch vụ, tài nguyên hiện có và các đường xuất/nhân bản dữ liệu; constraint này không tự đảm bảo mọi hoạt động lưu trú dữ liệu hoặc xử lý trên toàn hệ thống.

Quy trình kiểm tra:

1. **Ghi rõ ràng buộc:** tập lãnh thổ/location được phép, loại dữ liệu áp dụng, yêu cầu đối với bản sao, backup, log và thời hạn lưu.
2. **Lập bản đồ dữ liệu:** thống kê tất cả hệ thống nhận, tạo, sao chép, cache hoặc xuất dữ liệu.
3. **Kiểm tra từng sản phẩm:** region có sẵn, phạm vi cam kết, ngoại lệ, metadata, cơ chế nhân bản và tài liệu hợp đồng hiện hành.
4. **Áp biện pháp kiểm soát:** Organization Policy ở nơi hỗ trợ, IAM tối thiểu, review thay đổi và kiểm tra cấu hình Infrastructure as Code.
5. **Kiểm chứng sau triển khai:** đối chiếu vị trí thực của tài nguyên, giám sát luồng xuất và lưu bằng chứng phục vụ kiểm toán.

Nếu dữ liệu bắt buộc ở trong một lãnh thổ mà các dịch vụ hoặc region đang có không hỗ trợ, phải loại thiết kế đó, tìm phương án kiến trúc/nhà cung cấp khác hoặc đưa ra đánh giá pháp lý chính thức. Một region “gần” về mặt địa lý không có nghĩa thuộc lãnh thổ được yêu cầu.

Với hệ thống chịu quy định riêng, đội kỹ thuật cần phối hợp pháp chế và an toàn thông tin để đánh giá quy định, hợp đồng, ngoại lệ và nghĩa vụ xử lý dữ liệu. Không thể kết luận tuân thủ chỉ bằng tên region.

## 5. Phương pháp ra quyết định: lọc điều kiện bắt buộc trước

Một lỗi thường gặp là xếp hạng region theo ping rồi mới phát hiện vùng nhanh nhất không có dịch vụ cần dùng, không được phép lưu dữ liệu hoặc không đáp ứng yêu cầu phục hồi. Cách hiệu quả hơn là tách rõ **điều kiện không thể đánh đổi** và **tiêu chí tối ưu**.

### 5.1. Vòng 1: loại ứng viên không hợp lệ

Một region chỉ nên đi tiếp khi đồng thời đáp ứng:

- **Phạm vi dữ liệu:** mọi nơi cần lưu/xử lý dữ liệu gốc, replica, backup và log nằm trong location được phép.
- **Dịch vụ và năng lực:** đúng sản phẩm, cấu hình HA, loại máy, phiên bản, quota/công suất hiện có hoặc có kế hoạch cấp.
- **Mạng và tích hợp:** kết nối đến dịch vụ nội bộ, đối tác, mạng riêng, hệ thống quản trị có thiết kế phù hợp.
- **Khôi phục:** có thiết kế khả thi cho RPO/RTO của workload và đủ tài nguyên để thực hiện.
- **Chính sách tổ chức:** có thể tạo, vận hành, giám sát tài nguyên trong phạm vi Organization Policy và phân quyền.

Ràng buộc bắt buộc không được chấm như một “điểm trừ” để vùng nhanh hơn bù lại. Giảm 50 ms độ trễ không làm hợp lệ việc lưu dữ liệu ở nơi bị cấm.

### 5.2. Vòng 2: chọn tốt nhất trong tập hợp hợp lệ

Với những ứng viên còn lại, so sánh độ trễ p95/p99 theo lượng người dùng, chi phí tổng, độ phức tạp khôi phục và vận hành. Trọng số có thể thay đổi theo hệ thống, nhưng nguồn bằng chứng cần minh bạch.

| Tiêu chí | Phép đo hoặc bằng chứng |
| --- | --- |
| Độ trễ với người dùng | Benchmark request nghiệp vụ từ mạng đại diện; so sánh p50/p95/p99, tỷ lệ timeout và throughput. |
| Độ trễ giữa các thành phần | Trace API ↔ database, queue, dịch vụ bên ngoài; thống kê số lượt gọi xuyên region. |
| Độ tin cậy | Kết quả thử mất instance/zone/region; thời gian failover, độ nguyên vẹn dữ liệu và kết quả khôi phục backup. |
| Chi phí tổng | Compute, database, storage, replica, backup, egress, chuyển dữ liệu giữa zone/region, giám sát và nhân lực vận hành. |
| Khả năng mở rộng | Hạn mức vùng, loại máy, giới hạn scale, nhu cầu tăng trưởng và khả năng phân bổ capacity. |
| Vận hành | Chất lượng runbook, cơ chế quản lý cấu hình, sự sẵn sàng của đội ngũ và tốc độ xử lý sự cố. |

Giá có thể khác giữa các region. Truy cập dữ liệu hoặc nhân bản qua các region có thể phát sinh chi phí mạng tùy dịch vụ. Chỉ so sánh đơn giá VM hoặc dung lượng lưu trữ có thể khiến tổng chi phí bị đánh giá thiếu.

### 5.3. Ví dụ thực tế: API thương mại điện tử

**Bối cảnh giả định:** phần lớn khách hàng ở Hà Nội và TP. Hồ Chí Minh. API cần p95 dưới 250 ms; dữ liệu đơn hàng cần **RPO ≤ 15 phút**, **RTO ≤ 60 phút**. Bộ phận có thẩm quyền đã xác nhận một tập location được phép lưu và xử lý dữ liệu. Các mục tiêu này là số liệu minh họa, không phải SLA mặc định của Google Cloud.

| Công việc | Bằng chứng cần có trước khi chọn |
| --- | --- |
| Xác định nơi đặt dữ liệu | Region chính, region phục hồi, location backup, log, cache và dịch vụ phân tích thuộc phạm vi được phép. |
| Kiểm tra hỗ trợ dịch vụ | Cloud Run hoặc Compute Engine/GKE, database HA, networking, image registry, observability hỗ trợ cấu hình mong muốn. |
| Thử tải | Tập API từ hai thành phố và nhiều nhà mạng; lưu p95/p99, tỷ lệ lỗi và độ trễ của truy vấn database. |
| Dự phòng zone | Nhiều instance hoặc dịch vụ managed có HA phù hợp, database đáp ứng sự cố zone. |
| Dự phòng region | Dữ liệu được sao chép hoặc có backup theo RPO; có quy trình khởi động vùng dự phòng và chuyển traffic theo RTO. |
| Thử khôi phục và lập dự toán | Diễn tập mất zone, mất region, khôi phục bản sao; tính chi phí bản sao, đường truyền, tài nguyên dự phòng. |

Nếu region A nhanh hơn B nhưng không thể phục hồi đạt RTO/RPO, cần điều chỉnh kiến trúc rồi thử lại hoặc lựa chọn một thiết kế khác. Nếu hai phương án đều đạt giới hạn nghiệp vụ, chi phí và tính đơn giản khi vận hành có thể quan trọng hơn việc giảm thêm vài mili giây.

### 5.4. Lưu lại quyết định để dễ kiểm tra và thay đổi

Một bản ghi quyết định kiến trúc nên có các trường như sau:

~~~yaml
workload: "checkout-api"
users: "Chu yeu tai Viet Nam"
data_classification: "Du lieu khach hang va don hang"
allowed_locations: "<tap location duoc phe duyet>"
primary_region: "<region duoc chon>"
recovery_region: "<region du phong neu duoc phep>"
required_p95_ms: 250
required_rpo_minutes: 15
required_rto_minutes: 60
evidence:
  - "Ket qua benchmark tu nhieu mang nguoi dung"
  - "Bang doi chieu location cua dich vu va cac ban sao"
  - "Bien ban dien tap failover va restore"
decision_owner: "<nhom chiu trach nhiem>"
~~~

Các chuỗi trong dấu ngoặc nhọn góc là chỗ điền giá trị được xác minh; ví dụ này là mẫu ghi quyết định, không phải cấu hình có thể triển khai trực tiếp.

## 6. Kiểm tra quyết định bằng công cụ và quy trình vận hành

Google Cloud Console cho phép xem/chọn trường region, zone hoặc location của nhiều tài nguyên khi khởi tạo. Với Compute Engine, có thể bắt đầu khám phá danh sách region và zone bằng hai lệnh **chỉ đọc**:

~~~bash
gcloud compute regions list
gcloud compute zones list
~~~

Danh sách trên không xác nhận vị trí hỗ trợ của tất cả sản phẩm. Đối với Cloud Run, GKE, Cloud SQL, Cloud Storage, BigQuery và các chức năng cụ thể, cần kiểm tra tài liệu location hiện hành, hạn mức, tính năng và cấu hình thực tế trong project. Kiểm tra cũng nên bao gồm khu vực dự phòng chứ không chỉ nơi chạy chính.

### Trước khi phát hành

1. **Khai báo vị trí có chủ đích:** region/zone/location cho ứng dụng, subnet, database, bucket, dataset, logging và backup trong cấu hình triển khai. Dùng Infrastructure as Code và review thay đổi khi phù hợp.
2. **Xác thực ràng buộc dữ liệu:** kiểm tra vị trí được triển khai thực tế, quy tắc xuất dữ liệu, các bản sao và hệ thống bên thứ ba; không chỉ nhìn giá trị dự kiến trong cấu hình.
3. **Quan sát hiệu năng đầu cuối:** theo dõi SLO, p95/p99, timeout, lỗi và đường đi tới database/dependency từ góc nhìn người dùng.
4. **Kiểm tra khả dụng:** diễn tập mất một instance, một zone, dependency và region; đo thời gian khôi phục cũng như mức mất dữ liệu thực tế.
5. **Kiểm tra restore và bản sao:** thử phục hồi backup, quyền truy cập, khóa mã hóa liên quan, tính toàn vẹn dữ liệu và thứ tự chuyển đổi.
6. **Kiểm tra chi phí:** theo dõi egress, truyền dữ liệu giữa các vị trí, backup, năng lực dự phòng và chênh lệch giữa dự toán với hóa đơn.

### Khi ứng dụng thay đổi

Cần đánh giá lại lựa chọn region khi mở thị trường, thêm công cụ phân tích/AI, tăng lượng truy cập, thay đổi database, xuất hiện yêu cầu dữ liệu mới hoặc sản phẩm mở rộng sang region khác. Việc chuyển vị trí không nhất thiết chỉ là đổi một tham số: tùy dịch vụ có thể phải tạo tài nguyên mới, chuyển dữ liệu, cập nhật cấu hình kết nối, lập kế hoạch dừng ghi và cutover.

Đối với hệ thống có trạng thái, kế hoạch chuyển region nên quy định rõ cách đồng bộ, thời điểm ngừng ghi, cách đối chiếu dữ liệu sau chuyển, cơ chế quay lại nếu lỗi và ai được phép phê duyệt chuyển traffic.

## 7. Tình huống áp dụng: đánh giá một phương án triển khai

Một nhóm đề xuất đặt frontend sau CDN, API trên Cloud Run, database trên Cloud SQL và file trên Cloud Storage. Họ chọn region cho API vì phép thử ping nhanh nhất; database ở region khác vì giá hấp dẫn; bucket và logging chưa được xác định location. Phương án chỉ ghi thêm “dùng dịch vụ toàn cầu để luôn sẵn sàng”.

Để đánh giá phương án, hãy lập bảng bốn cột: **thành phần**, **location thực tế**, **ràng buộc**, **bằng chứng kiểm chứng**. Có ít nhất năm việc phải giải quyết:

1. Đo p95/p99 của **nghiệp vụ đầy đủ**, trong đó có đường gọi API → Cloud SQL xuyên region và dữ liệu trả về cho người dùng.
2. Xác minh bucket, backup, log, dữ liệu cache tại CDN và mọi luồng xuất/nhập dữ liệu đều thỏa phạm vi được phép.
3. Phân biệt khả năng chịu lỗi zone của API/database với phương án khôi phục khi cả region gặp sự cố; đặt và thử RTO/RPO.
4. Tính chi phí phát sinh khi trao đổi dữ liệu giữa các region, duy trì replica, backup và năng lực dự phòng.
5. Ghi lại phép đo, ràng buộc, các giả định còn thiếu và quyết định kiến trúc để có thể kiểm tra sau này.

Thiết kế chỉ sẵn sàng để phê duyệt khi **mọi điều kiện bắt buộc đã được xác minh**, đường đi của ứng dụng đáp ứng độ trễ cần thiết và diễn tập khôi phục chứng minh hệ thống đạt mục tiêu gián đoạn/mất dữ liệu đã chọn. Việc chạy nhanh tại một region mới chỉ giải quyết một phần bài toán.

## Nguồn để kiểm chứng khi triển khai

- **Google Cloud locations:** https://cloud.google.com/about/locations — kiểm tra danh sách hạ tầng và location đang được cung cấp.
- **Tài liệu từng dịch vụ Google Cloud:** xem các mục Locations, High availability, Disaster recovery, Data residency và Pricing của sản phẩm đang dùng.
- **Resource hierarchy / Organization Policy:** tra cứu hướng dẫn Resource Manager và phạm vi hỗ trợ của constraint **gcp.resourceLocations**.
- **Google Cloud Architecture Center:** tham khảo thiết kế HA, multi-region, disaster recovery, reliability và giám sát theo SLO.

Những nguồn này cần được đối chiếu ở thời điểm triển khai vì region hỗ trợ, tính năng, hạn mức, cơ chế nhân bản, cam kết lưu trú dữ liệu và bảng giá có thể thay đổi.

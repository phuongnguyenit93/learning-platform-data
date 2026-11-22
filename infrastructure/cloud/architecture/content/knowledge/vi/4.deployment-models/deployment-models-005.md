# Một nhà cung cấp và nhiều nhà cung cấp: lợi ích, giới hạn và chi phí

## Mục tiêu học tập

Trong thiết kế **Cloud Architecture**, lựa chọn một nhà cung cấp đám mây (*single-cloud / single-provider*) hay phối hợp nhiều nhà cung cấp (*multi-cloud / multi-provider*) là quyết định ảnh hưởng trực tiếp đến độ tin cậy, bảo mật, khả năng mở rộng, chi phí và cách vận hành hệ thống. Quyết định này cần xuất phát từ yêu cầu nghiệp vụ, kịch bản sự cố và năng lực tổ chức; không thể chỉ dựa vào việc một mô hình “linh hoạt hơn” hay “an toàn hơn” trên lý thuyết.

Sau bài học, bạn có thể:

- Phân biệt **single-provider**, **multi-region**, **multi-cloud** và **hybrid cloud**.
- Phân tích lợi ích, giới hạn và rủi ro của từng mô hình triển khai.
- Nhận diện các kiểu kết hợp nhiều nhà cung cấp theo mục đích nghiệp vụ: phân chia workload, dự phòng thảm họa và phục vụ đa khu vực.
- Ước tính **tổng chi phí sở hữu (TCO)**, bao gồm hạ tầng, truyền dữ liệu, nhân lực, kiểm thử và chi phí chuyển đổi.
- Liên hệ lựa chọn nhà cung cấp với thiết kế network, compute, data, deployment và đánh giá theo nguyên tắc **Well-Architected**.
- Đưa ra quyết định có thể kiểm chứng bằng SLO, RTO, RPO, bài diễn tập và hồ sơ quyết định kiến trúc (ADR).

## 1. Hiểu đúng phạm vi của mô hình triển khai

Nhà cung cấp đám mây (*cloud provider*) cung cấp các nền tảng như máy ảo, container, mạng, cơ sở dữ liệu, lưu trữ, quản lý định danh và công cụ giám sát. Ví dụ về các nhà cung cấp public cloud là AWS, Microsoft Azure và Google Cloud. Trong thực tế, một doanh nghiệp cũng có thể vận hành hệ thống tại trung tâm dữ liệu của mình hoặc sử dụng dịch vụ SaaS từ bên thứ ba.

Các thuật ngữ cần phân biệt:

| Mô hình | Đặc điểm | Điều **chưa thể kết luận** |
| --- | --- | --- |
| **Một nhà cung cấp** (*single-provider*) | Workload chính chạy trên dịch vụ của một nhà cung cấp cloud. | Không đồng nghĩa chỉ một server, một AZ hay một region. |
| **Multi-AZ** | Workload trải trên nhiều vùng sẵn sàng thuộc một region của một nhà cung cấp. | Không loại bỏ mọi sự cố ở cấp region hoặc provider. |
| **Multi-region** | Workload hoặc dữ liệu được bố trí tại nhiều region, có thể đều thuộc cùng một nhà cung cấp. | Không tự động là multi-cloud. |
| **Multi-cloud / nhiều nhà cung cấp** | Ít nhất hai nền tảng cloud của các nhà cung cấp khác nhau phục vụ hệ thống hoặc danh mục workload. | Không có nghĩa một ứng dụng có thể chuyển ngay lập tức giữa hai cloud. |
| **Hybrid cloud** | Kết hợp môi trường on-premises/private cloud với public cloud, cần quản lý kết nối và phân chia trách nhiệm. | Không nhất thiết sử dụng nhiều public cloud provider. |

Ví dụ, hệ thống dùng hai region của cùng một nhà cung cấp vẫn là **single-provider, multi-region**. Hệ thống dùng dịch vụ thanh toán SaaS bên ngoài cũng chưa nhất thiết nên được gọi là kiến trúc multi-cloud cho ứng dụng cốt lõi; cần xác định chính xác workload, quyền kiểm soát và trách nhiệm vận hành nào nằm ở đâu.

**Điểm cần nhớ:** Đếm số tài khoản cloud, Kubernetes cluster hoặc data center không đủ để đo sự độc lập giữa các nhà cung cấp. Phải xem **những đường phụ thuộc còn dùng chung**: danh tính, DNS, CI/CD, container registry, bí mật, hệ thống thông báo, nguồn dữ liệu và đội vận hành.

## 2. Mô hình một nhà cung cấp

### 2.1. Cấu trúc điển hình

Một ứng dụng Java/Spring Boot có thể sử dụng nhiều AZ, cơ chế tự mở rộng và database có failover, dù chỉ triển khai trên một nhà cung cấp:

~~~mermaid
flowchart TB
    U[Người dùng] --> DNS[DNS / WAF / Load Balancer]
    subgraph P["Một nhà cung cấp - một region"]
        DNS --> A[Ứng dụng - AZ A]
        DNS --> B[Ứng dụng - AZ B]
        A --> DB[(Database quản lý)]
        B --> DB
        DB --> BK[Backup / Point-in-time recovery]
        A --> Q[Queue cho tác vụ bất đồng bộ]
        B --> Q
    end
    P --> OBS[Metrics / Logs / Alerts]
~~~

Trong sơ đồ này, **đa AZ** giúp giảm phụ thuộc vào một vùng sẵn sàng, **auto scaling** giúp xử lý biến động tải, còn **backup/restore** hỗ trợ khôi phục dữ liệu. Các thành phần này phục vụ những kịch bản khác nhau; không có một tính năng riêng lẻ nào bảo đảm toàn bộ mục tiêu về độ tin cậy.

### 2.2. Lợi ích thường gặp

**Tập trung chuyên môn.** Nhóm có thể dùng một bộ công cụ IAM, mạng, giám sát, chính sách tài nguyên, IaC và quy trình ứng phó sự cố. Số lượng nền tảng cần học và duy trì ít hơn.

**Tích hợp dịch vụ thuận tiện.** Những dịch vụ như managed database, load balancer, queue, secret manager, KMS và logging thường có cơ chế tích hợp sẵn. Nhờ đó đội ngũ dành nhiều thời gian hơn cho luồng nghiệp vụ.

**Quản trị nhất quán.** Kiểm soát quyền truy cập, tagging, ngân sách, kiểm toán và quy trình triển khai có thể chuẩn hóa trên một hệ sinh thái.

**Khả năng tối ưu chi phí và vận hành.** Khi quản lý một môi trường công nghệ, tổ chức có thể sử dụng năng lực nhân sự hiệu quả hơn và tận dụng các chương trình cam kết sử dụng, giảm giá hoặc công cụ tối ưu phù hợp. Mức tiết kiệm thực tế cần tính theo workload và hợp đồng cụ thể.

**Kiến trúc ít điểm tích hợp liên nhà cung cấp hơn.** Những vấn đề như đồng bộ dữ liệu, truyền mạng và định danh giữa hai nền tảng sẽ ít xuất hiện hơn.

### 2.3. Giới hạn và rủi ro

- **Rủi ro phụ thuộc nhà cung cấp:** Khi một dịch vụ hoặc phạm vi lớn của provider gặp sự cố, nhiều thành phần có thể bị ảnh hưởng cùng lúc. Dùng đa AZ không phủ mọi dạng lỗi.
- **Khóa chặt công nghệ (*vendor lock-in*):** Dịch vụ managed đặc thù, API riêng, chính sách IAM, định dạng dữ liệu và automation có thể khiến việc chuyển sang provider khác tốn thời gian.
- **Ảnh hưởng của chính sách và thương mại:** Giá, quota, phạm vi region, thay đổi điều khoản và ngừng hỗ trợ sản phẩm có thể tác động lên lộ trình hệ thống.
- **Giới hạn địa lý và quy định:** Một nhà cung cấp có thể chưa đáp ứng yêu cầu về vị trí dữ liệu, khách hàng hoặc dịch vụ tại một thị trường cụ thể.
- **Tập trung năng lực tổ chức:** Khi mọi người, quy trình và công cụ đều gắn với một nền tảng, chuyển hướng lớn sẽ cần kế hoạch đào tạo và chuyển đổi.

Rủi ro *lock-in* không nhất thiết là lý do để tránh mọi managed service. Một dịch vụ đặc thù có thể giúp tăng chất lượng và giảm chi phí vận hành đủ lớn để bù lại chi phí chuyển đổi trong tương lai. Điều cần làm là **đánh giá và ghi nhận sự phụ thuộc có chủ đích**.

### 2.4. Khi nào hợp lý?

Mô hình này thường phù hợp khi sản phẩm mới cần ra mắt sớm, nhóm vận hành còn nhỏ, ngân sách có giới hạn, các yêu cầu độ tin cậy có thể đạt bằng multi-AZ/multi-region cùng nhà cung cấp, hoặc việc chuyển đổi provider chưa mang lại lợi ích nghiệp vụ cụ thể.

Điều đó không làm nhẹ yêu cầu về dự phòng, bảo mật hay khôi phục. Một hệ thống single-provider tốt vẫn cần phân vùng mạng, nguyên tắc cấp quyền tối thiểu, backup đã diễn tập, quản lý quota, dashboard SLI, quy trình xử lý sự cố và kế hoạch thay thế công nghệ khi cần.

## 3. Mô hình nhiều nhà cung cấp: chọn đúng kiểu kết hợp

**Multi-cloud không phải một kiến trúc duy nhất.** Ít nhất bốn kiểu triển khai dưới đây có mục tiêu, mức độ phức tạp và chi phí khác nhau.

| Kiểu triển khai | Cách vận hành | Lợi ích chính | Thách thức chính |
| --- | --- | --- | --- |
| **Phân chia workload** | Dịch vụ A chạy trên provider X, dịch vụ B chạy trên provider Y; có thể giao tiếp qua API. | Chọn dịch vụ phù hợp từng nhu cầu, đáp ứng yêu cầu thị trường. | Tăng điểm tích hợp, latency, quản trị danh tính và observability. |
| **Dự phòng thảm họa active-passive** | Provider X xử lý chính; Y giữ bản sao dữ liệu và năng lực dự phòng theo mức cold/warm/hot. | Hỗ trợ khôi phục khi xảy ra sự cố nghiêm trọng tại X. | Replication, cutover, RTO/RPO, diễn tập và chi phí standby. |
| **Active-active xuyên nhà cung cấp** | Cả X và Y đồng thời phục vụ lưu lượng sản xuất. | Phân tán tải và có thể giảm phụ thuộc vào một provider. | Đồng bộ dữ liệu, định tuyến, tính nhất quán, ghi trùng và kiểm soát chi phí. |
| **Di chuyển dần / phương án thoát** | Một phần workload được chuyển sang Y theo các giai đoạn. | Giảm rủi ro của chương trình di chuyển lớn. | Vận hành hai hệ thống trong thời gian chuyển đổi, đồng bộ và rollback. |

### 3.1. Phân chia workload theo nhu cầu

Ví dụ, API giao dịch và database chạy tại provider X, trong khi một hệ thống phân tích chạy tại provider Y vì nhu cầu tích hợp với công cụ dữ liệu sẵn có. Hai nhóm workload được tách bằng hợp đồng API, luồng sự kiện hoặc pipeline dữ liệu.

Ưu điểm là tận dụng thế mạnh cụ thể, nhưng một pipeline phân tích chạy ở provider Y **không làm hệ thống đặt chỗ trên provider X tự động có khả năng chịu lỗi**. Nếu X ngừng hoạt động, đường ghi giao dịch vẫn có thể dừng. Vì vậy, cần mô tả chính xác phạm vi dự phòng thay vì tuyên bố “đã multi-cloud”.

Phần khó thường nằm ở truyền dữ liệu qua ranh giới nhà cung cấp: **latency, băng thông, egress, chính sách bảo vệ dữ liệu, retry và khả năng kiểm toán**. Kết nối mạng riêng hoặc VPN có thể tăng kiểm soát nhưng bổ sung chi phí và thành phần cần vận hành.

### 3.2. Active-passive để khôi phục thảm họa

Một hệ thống đặt chỗ có thể hoạt động chủ yếu trên provider X và giữ một môi trường dự phòng tại Y. Sơ đồ dưới đây mô tả kiến trúc **warm standby**, trong đó năng lực Y chưa nhất thiết đủ tải production cho đến khi tăng quy mô và thực hiện chuyển đổi:

~~~mermaid
flowchart LR
    Client[Người dùng] --> Traffic[DNS / Điều hướng truy cập]
    Traffic --> X[Provider X: API đang hoạt động]
    X --> DBX[(Database chính)]
    DBX -->|Sao chép / xuất và khôi phục dữ liệu| DBY[(Bản sao dữ liệu)]
    subgraph Y["Provider Y - môi trường dự phòng"]
        DBY --> YAPI[Ứng dụng standby]
    end
    Traffic -. Khi có quyết định failover .-> YAPI
    Ops[Giám sát + Runbook + Diễn tập] -.-> Traffic
    Ops -.-> YAPI
~~~

Cần hiểu và chốt **mức độ dự phòng**:

- **Cold standby:** Chủ yếu có backup, mã hạ tầng, image và hướng dẫn khởi dựng. Chi phí thường thấp hơn, thời gian khôi phục có thể dài hơn.
- **Warm standby:** Dịch vụ/dữ liệu tối thiểu đã sẵn sàng, cần tăng tài nguyên hoặc hoàn tất một số bước cutover. Chi phí trung bình, RTO tùy kết quả diễn tập.
- **Hot standby:** Phần lớn hạ tầng và dữ liệu dự phòng sẵn sàng nhận tải. Chi phí cao hơn; vẫn phải kiểm chứng chuyển hướng, dữ liệu và phụ thuộc.

Không thể tự suy ra RTO từ nhãn cold/warm/hot. **RTO** là thời gian khôi phục dịch vụ nghiệp vụ tối đa được chấp nhận; **RPO** là khoảng mất dữ liệu theo thời gian tối đa được chấp nhận. Cả hai phải được đo qua diễn tập với sự cố và luồng nghiệp vụ xác định.

Ví dụ về yêu cầu **minh họa**:

> Khi provider X không thể phục vụ API đặt chỗ trong một sự cố có phạm vi đã định nghĩa, hệ thống phải khôi phục luồng tìm phòng và đặt chỗ tại Y trong **RTO không quá 2 giờ**, với **RPO không quá 15 phút**, đồng thời không tạo đặt chỗ trùng trong bộ kiểm thử retry/failover.

Nếu cần **RPO gần 0 hoặc bằng 0**, việc đồng bộ xuyên nhà cung cấp có thể tạo ra độ trễ, giới hạn throughput và rủi ro chia tách hệ thống (*split-brain*). Không thể mặc định một bản sao bất đồng bộ sẽ đáp ứng RPO = 0. Khi xảy ra sự cố, phải xác định bên nào được phép ghi và cách xử lý những giao dịch đang chuyển tiếp.

### 3.3. Active-active và dữ liệu nhất quán

Triển khai active-active cho các chức năng **đọc ít thay đổi** thường dễ hơn cho các giao dịch cần tính nhất quán nghiêm ngặt. Với đặt chỗ, thanh toán hoặc trừ tồn kho, nếu hai provider cùng xác nhận ghi mà không có cơ chế phối hợp phù hợp, hệ thống có thể bán cùng một tài nguyên hai lần.

Để thiết kế active-active, cần trả lời:

1. Dữ liệu nào được phép ghi ở cả hai phía? Dữ liệu nào chỉ có một nguồn sự thật?
2. Tình huống mất kết nối giữa hai provider sẽ cho phép tiếp tục ghi hay tạm dừng một phần giao dịch?
3. Làm sao phát hiện và giải quyết xung đột; thao tác có **idempotent** khi client retry không?
4. Chỉ số nào xác nhận tính đúng đắn nghiệp vụ, bên cạnh p95 độ trễ và tỷ lệ lỗi?
5. Nếu phụ thuộc dùng chung như DNS, identity provider hoặc cổng thanh toán hỏng, hai cloud có thật sự độc lập không?

**Lựa chọn kiến trúc thường hợp lý là phân loại dữ liệu và luồng:** tài nguyên tĩnh có thể phục vụ từ nhiều nơi; dữ liệu giao dịch nhạy cảm thường cần quy tắc ghi nhất quán chặt hơn. Đừng thiết kế active-active toàn hệ thống chỉ vì muốn có hai nơi xử lý traffic.

## 4. So sánh những đánh đổi quan trọng

| Tiêu chí | Một nhà cung cấp | Nhiều nhà cung cấp |
| --- | --- | --- |
| **Tốc độ triển khai ban đầu** | Thường nhanh hơn nhờ tích hợp, ít bộ công cụ. | Thường chậm hơn vì cần chuẩn hóa API, mạng, IAM và pipeline. |
| **Độ tin cậy** | Có thể rất cao với multi-AZ/multi-region và DR tốt. | Có thể giảm một số rủi ro cấp provider nếu các phụ thuộc thực sự độc lập và failover đã kiểm chứng. |
| **Bảo mật** | Chính sách và giám sát dễ đồng nhất hơn. | Cần kiểm soát quyền, khóa, logging và cấu hình nhất quán trên nhiều mặt phẳng điều khiển. |
| **Hiệu năng** | Giao tiếp trong cùng hệ sinh thái thường thuận lợi hơn. | Giao tiếp liên cloud dễ có thêm latency và chi phí truyền dữ liệu; có thể thuận lợi nếu workload đặt gần người dùng/thị trường. |
| **Dữ liệu** | Dễ sử dụng dịch vụ tích hợp và failover trong cùng nền tảng. | Chuyển đổi schema, replication, tuân thủ dữ liệu và giải quyết xung đột thường khó hơn. |
| **Khả năng chuyển đổi** | Có thể phụ thuộc API và dịch vụ riêng của một provider. | Có động lực thiết kế ranh giới tách biệt hơn, nhưng vẫn có thể tạo lock-in tại hai nơi. |
| **Vận hành** | Ít công cụ và chuyên môn phải duy trì. | Nhiều control plane, quota, incident process và hệ thống quan sát cần phối hợp. |
| **Chi phí** | Thường dễ dự báo và tối ưu giai đoạn đầu hơn. | Có standby, egress, kết nối, replication, nhân sự và diễn tập bổ sung; đôi lúc có lợi nếu tối ưu theo từng workload. |
| **Đàm phán với nhà cung cấp** | Mức độ thay thế có thể hạn chế hơn. | Có thể mở rộng lựa chọn, nhưng lợi thế phụ thuộc khả năng chuyển đổi thực tế và hợp đồng. |

**Không có mô hình nào thắng ở mọi tiêu chí.** Ví dụ, single-provider có thiết kế và diễn tập khôi phục tốt có thể đạt độ tin cậy cao hơn multi-cloud nhưng chỉ có sơ đồ dự phòng trên giấy.

### 4.1. Đánh giá theo miền lỗi (*failure domain*)

Trước khi chọn multi-cloud vì độ tin cậy, lập danh sách loại sự cố mà doanh nghiệp cần chịu được:

| Loại sự cố | Biện pháp có thể đủ trong một nhà cung cấp | Trường hợp cần cân nhắc nhà cung cấp thứ hai |
| --- | --- | --- |
| Một tiến trình/node chết | Nhiều instance, health check, auto healing. | Thường không cần chỉ vì lỗi này. |
| Một AZ ngừng hoạt động | Đa AZ và các phụ thuộc có khả năng failover. | Khi có yêu cầu độc lập vượt miền lỗi AZ. |
| Một region không hoạt động | Multi-region cùng provider và khôi phục có diễn tập. | Khi yêu cầu loại trừ rủi ro tác động toàn provider hoặc region phù hợp không sẵn có. |
| Lỗi dịch vụ hoặc control plane diện rộng của provider | Thiết kế giảm phụ thuộc vào dịch vụ đó, runbook thủ công, phương án DR cùng provider nếu còn khả dụng. | Có thể cần nhà cung cấp thứ hai nếu mức thiệt hại và yêu cầu khôi phục biện minh cho chi phí. |
| Xóa nhầm hoặc dữ liệu bị ghi sai | Backup cách ly, phiên bản dữ liệu, point-in-time recovery, quyền ghi tối thiểu. | Backup ở provider khác có thể tăng mức độc lập nhưng không thay thế kiểm thử restore. |
| Lỗi ứng dụng hoặc bản phát hành sai | Rollback, canary, kiểm thử, circuit breaker. | Hai bản triển khai cùng mã lỗi có thể hỏng giống nhau; multi-cloud không tự giải quyết. |
| Lỗi DNS, danh tính, thanh toán hoặc đường kết nối dùng chung | Đa dạng hóa phụ thuộc, thiết kế degrade, phương án khôi phục cụ thể. | Cần xem xét kiến trúc toàn tuyến; hai cloud vẫn có thể cùng phụ thuộc một dịch vụ. |

Một yêu cầu “chịu được sự cố toàn nhà cung cấp” phải đi kèm định nghĩa rõ sự cố nào, ứng dụng nào còn dùng được, RTO/RPO mục tiêu và giới hạn rủi ro còn chấp nhận.

### 4.2. Rủi ro của đường phụ thuộc chung

Ngay cả khi compute chạy ở hai cloud, ứng dụng vẫn có thể ngừng phục vụ vì:

- DNS hoặc hệ thống quản lý certificate dùng chung không cập nhật được.
- Login phụ thuộc một identity provider gặp sự cố.
- Pipeline triển khai hoặc container registry chỉ nằm tại provider chính.
- Khóa giải mã, secrets hoặc quy trình cấp quyền không khả dụng ở môi trường dự phòng.
- Database chỉ có tại provider chính; phía phụ không có dữ liệu đủ mới hoặc hợp lệ.
- API thanh toán, SMS hay dịch vụ kiểm tra gian lận bên thứ ba không hoạt động.
- Cùng một bug được phát hành đồng thời ở cả hai cloud.

Để kết luận hai môi trường có độc lập hay không, phải phân tích **chuỗi yêu cầu thực tế từ người dùng tới mọi phụ thuộc bắt buộc**, thay vì chỉ nhìn vị trí của hai cụm máy chủ.

## 5. Network, compute, dữ liệu và triển khai

### 5.1. Network: kết nối xuyên cloud là một ranh giới mới

Khi có hai nhà cung cấp, cần thiết kế và vận hành:

- Phân hoạch địa chỉ mạng, tránh trùng CIDR, quy tắc routing rõ ràng.
- VPN/private connectivity hoặc kết nối an toàn tương đương, có cơ chế thay thế và giám sát.
- TLS, xác minh danh tính dịch vụ, giới hạn nguồn và đích lưu lượng.
- Chính sách ingress/egress, tường lửa, WAF, rate limit và bảo vệ khỏi lạm dụng.
- Độ trễ ứng dụng xuyên cloud; thời gian timeout, retry, circuit breaker và tránh retry storm.
- Chi phí egress cho replication, backup, đồng bộ và yêu cầu khách hàng.

Ví dụ, nếu API phải gọi đồng bộ tới database đặt ở provider khác cho mỗi yêu cầu, một lần tăng độ trễ mạng có thể ảnh hưởng trực tiếp tới p95/p99 của API. Phân tách bằng sự kiện/batch có thể phù hợp hơn, nhưng chỉ khi nghiệp vụ cho phép nhất quán cuối cùng (*eventual consistency*).

### 5.2. Compute và nền tảng chạy ứng dụng

Container và Kubernetes có thể giúp chuẩn hóa một số khía cạnh của ứng dụng Java, nhưng **cùng chạy Kubernetes không có nghĩa mọi thứ di chuyển được ngay**. Ingress controller, CSI storage class, load balancer, service mesh, autoscaler, IAM, registry, secret manager và mạng cụm khác nhau giữa các nền tảng.

Nếu hệ thống chỉ cần chạy tại một cloud trong nhiều năm, dùng managed platform phù hợp có thể tiết kiệm đáng kể. Nếu cần giảm thời gian chuyển cloud, nên tách business logic khỏi SDK riêng bằng các adapter ở ranh giới thật sự có khả năng thay đổi. Tránh tạo lớp trừu tượng rộng cho mọi dịch vụ khi chưa có yêu cầu và kiểm thử tương ứng.

### 5.3. Data: điểm khó nhất của nhiều kiến trúc multi-cloud

Dữ liệu quyết định khả năng khôi phục và chuyển đổi thực chất. Cần làm rõ:

- **Nguồn sự thật:** Bên nào có quyền ghi và xác nhận giao dịch?
- **Replication:** Đồng bộ hay bất đồng bộ? Có phát hiện chậm trễ và lỗi đồng bộ không?
- **Tính nhất quán:** Hệ thống có chịu được stale read, xung đột hay đọc sau ghi không?
- **Schema và định dạng:** Cơ sở dữ liệu, extension, cơ chế index, trigger hoặc format backup có tương thích không?
- **Lưu trữ và pháp lý:** Dữ liệu có được phép xuất sang region/provider thứ hai không? Ai giữ khóa mã hóa?
- **Thời hạn khôi phục:** Dữ liệu được khôi phục trong bao lâu; sau restore có cần kiểm tra checksum và đối soát không?

Ví dụ, dùng PostgreSQL ở hai nhà cung cấp có thể thuận lợi cho tính di động của schema SQL, nhưng vẫn cần kiểm tra phiên bản, extension, cơ chế backup/restore, replication, giới hạn mạng và dịch vụ quản lý database khác nhau. Đặc biệt, không giả định hai database quản lý khác provider có cùng tính năng failover hay RPO chỉ vì cùng tên engine.

### 5.4. Deployment và vận hành

Multi-cloud cần quy trình triển khai, cấu hình và quan sát đầy đủ tại từng phía:

| Lớp vận hành | Câu hỏi phải trả lời |
| --- | --- |
| Infrastructure as Code | Có module cấu hình riêng cho từng provider nhưng cùng quy chuẩn bảo mật, tagging, review và trạng thái không? |
| CI/CD | Pipeline, artifact, image và quyền phát hành có còn hoạt động khi provider chính ngừng hoạt động không? |
| Identity/Secrets | Tài khoản dịch vụ, khóa, rotation, phân quyền và break-glass access được quản lý thế nào? |
| Monitoring/Tracing | Có nhìn thấy một hành trình giao dịch xuyên cloud, có tương quan trace ID và chuẩn hóa cảnh báo không? |
| Incident response | Ai có quyền xác nhận failover, chặn ghi ở môi trường cũ, bật ghi ở môi trường mới và đưa lưu lượng quay về? |
| Quota/Capacity | Provider dự phòng có đủ quota và năng lực phục vụ mức tải khôi phục trong thời gian mục tiêu không? |
| Governance | Chính sách lưu dữ liệu, kiểm toán, cấu hình mạng và hợp đồng trách nhiệm có áp dụng nhất quán không? |

Công cụ chung như Terraform, OpenTelemetry, container images và các giao thức tiêu chuẩn **có thể giảm công sức** phối hợp, nhưng không loại bỏ các khác biệt về mô hình tài nguyên và vận hành.

## 6. Bảo mật và tuân thủ trong hai mô hình

Single-provider thuận tiện cho việc tập trung policy và audit, nhưng vẫn cần phân tách tài khoản/môi trường, cấp quyền tối thiểu, mã hóa, kiểm tra cấu hình và lưu trữ audit an toàn.

Multi-cloud mở rộng bề mặt bảo mật: mỗi provider có IAM, chính sách mạng, cơ chế khóa, audit format và cấu hình mặc định riêng. Một sai sót tại bất kỳ môi trường nào có thể tạo lối vào hệ thống hoặc làm lộ dữ liệu được sao chép.

Một thiết kế an toàn cần:

1. **Xác định trách nhiệm chia sẻ** tại từng nhà cung cấp: bên nào quản lý hạ tầng nền, bên nào chịu trách nhiệm cấu hình dịch vụ, ứng dụng, quyền và dữ liệu.
2. **Thiết lập chính sách danh tính nhất quán:** federation khi thích hợp, MFA, least privilege, phân quyền cho service-to-service, tài khoản khẩn cấp và quy trình thu hồi.
3. **Mã hóa và quản lý khóa** theo nhu cầu nghiệp vụ, có kế hoạch nếu key management của provider chính không khả dụng.
4. **Giới hạn dữ liệu được sao chép:** phân loại dữ liệu, data residency, bảo vệ dữ liệu cá nhân, thời gian giữ và quy trình xóa ở cả hai nơi.
5. **Tập trung quan sát bảo mật mà vẫn bảo vệ thông tin nhạy cảm:** log không nên chứa dữ liệu cá nhân vượt nhu cầu vận hành.
6. **Diễn tập sự cố và kiểm tra cấu hình** ở cả hai provider, tránh môi trường dự phòng lâu ngày không được vá hoặc kiểm thử.

Nếu tổ chức chịu ràng buộc không được đặt dữ liệu tại vùng pháp lý nhất định, multi-cloud có thể khiến việc tuân thủ khó hơn nếu replication và backup di chuyển dữ liệu xuyên biên giới. **Nhiều provider không mặc nhiên tăng mức tuân thủ**.

## 7. Tính tổng chi phí sở hữu thay vì so giá máy ảo

Giá niêm yết theo giờ của VM chỉ là một phần của bài toán. Với single-provider hoặc multi-cloud, **TCO (Total Cost of Ownership)** có thể mô hình hóa như sau:

~~~text
TCO trong kỳ
  = Compute + Database + Storage
  + Network + Egress + Kết nối
  + Security + Monitoring + Backup
  + Nhân sự vận hành và trực sự cố
  + Kiểm thử, diễn tập, hỗ trợ và đào tạo
  + Chi phí di chuyển/đổi nền tảng được phân bổ
  - Chiết khấu và khoản tiết kiệm thực tế (nếu có)
~~~

Các mục phải thống nhất **kỳ tính, quy mô workload, độ sẵn sàng mục tiêu và phạm vi tính**. Nếu so phương án có SLO khác nhau, cần ghi rõ rằng hai phương án **không tương đương về chất lượng**.

### 7.1. Các chi phí hay bị bỏ sót

- **Truyền dữ liệu ra ngoài (*egress*):** Đồng bộ bản ghi, backup, logs, object storage và truy cập xuyên nhà cung cấp có thể tạo phí đáng kể.
- **Môi trường dự phòng:** Database, compute tối thiểu, license, đường mạng, DNS, observability và key management vẫn có chi phí khi không phục vụ traffic chính.
- **Nhân sự và năng lực:** Cần kỹ năng của hai hệ sinh thái, trực sự cố, phân quyền, diễn tập, kiểm toán và cập nhật dịch vụ ở cả hai.
- **Chuyển đổi và duy trì tính di động:** Refactor mã, schema, pipelines, integration tests, công cụ giám sát và tài liệu vận hành.
- **Chi phí cơ hội:** Thời gian đội phát triển dành cho abstraction/replication thay vì tính năng sản phẩm.
- **Tối ưu theo quy mô và hợp đồng:** Cam kết tiêu thụ, chiết khấu, dự trữ tài nguyên và quy định hỗ trợ có thể thay đổi kết quả so sánh.

### 7.2. Ví dụ tính TCO minh họa

Giả sử một hệ thống xử lý cùng khối lượng giao dịch trong cả hai phương án. Nhóm đang so sánh **single-provider có multi-AZ** với **multi-cloud warm standby** cho mục tiêu phục hồi sự cố cấp provider. Dưới đây chỉ là **giả định phục vụ bài tập**, không phải giá thị trường hay báo giá của một nhà cung cấp.

Đơn vị: **triệu VND/tháng**.

| Hạng mục | Single-provider | Multi-cloud warm standby |
| --- | ---: | ---: |
| Compute, database và storage môi trường chính | 180 | 180 |
| Hạ tầng và bản sao dữ liệu dự phòng ở provider thứ hai | 0 | 60 |
| Network/egress (bao gồm replication nếu có) | 20 | 30 |
| Kết nối riêng/VPN xuyên cloud bổ sung | 0 | 15 |
| Logging, monitoring, backup, security | 20 | 30 |
| Nhân sự vận hành, đào tạo và diễn tập phân bổ hàng tháng | 100 | 170 |
| **Tổng chi phí vận hành/tháng** | **320** | **485** |

Giả sử để triển khai multi-cloud còn phát sinh **1.200 triệu VND** chi phí chuyển đổi ban đầu, phân bổ nội bộ trong 24 tháng:

~~~text
Chi phí chuyển đổi phân bổ mỗi tháng = 1.200 / 24 = 50 triệu VND
TCO multi-cloud theo tháng = 485 + 50 = 535 triệu VND
Chênh lệch mỗi tháng = 535 - 320 = 215 triệu VND
Tỷ lệ tăng so với single-provider = 215 / 320 × 100% ≈ 67,2%
~~~

Đây **không** phải kết luận “multi-cloud luôn đắt hơn 67,2%”. Số liệu thay đổi theo lưu lượng, mức standby, khoảng cách region, hợp đồng hỗ trợ, mô hình dữ liệu, chiết khấu và khả năng tự động hóa. Không nên so phương án dự phòng ở hai provider với single-provider **không có cùng mục tiêu RTO/RPO** rồi suy ra mức giá của độ tin cậy; trước hết phải so các giải pháp đáp ứng cùng kịch bản nghiệp vụ.

Câu hỏi quyết định là: **Khoản chi tăng thêm bảo vệ được rủi ro nghiệp vụ nào, mức thiệt hại hoặc nghĩa vụ nào và có bằng chứng đạt mục tiêu khôi phục hay chưa?** Khi rủi ro hiếm nhưng hậu quả cực lớn, không nên chỉ dựa vào một xác suất ước lượng thiếu dữ liệu để quyết định.

### 7.3. Công thức chi phí theo đơn vị nghiệp vụ

Ngoài TCO hàng tháng, nên theo dõi:

~~~text
Chi phí trên mỗi giao dịch thành công
    = Tổng chi phí hệ thống trong kỳ / Số giao dịch nghiệp vụ thành công trong kỳ
~~~

Ví dụ, tổng chi phí 320 triệu VND/tháng với 800.000 đơn thành công tương đương **400 VND/đơn**. Cần thống nhất “giao dịch thành công” là một booking hoàn tất, không phải từng HTTP request. Khi thêm provider thứ hai, phần chi phí dự phòng có thể được xem như **chi phí bảo hiểm cho rủi ro vận hành**, nhưng vẫn phải được trình bày minh bạch trong ngân sách.

## 8. Chọn mô hình theo yêu cầu đo lường được

Không bắt đầu bằng yêu cầu “phải multi-cloud”, hãy bắt đầu bằng **kịch bản chất lượng** có thể đo.

| Yêu cầu nghiệp vụ | Câu hỏi cần làm rõ | Chỉ số/bằng chứng cần có |
| --- | --- | --- |
| Không mất giao dịch đã xác nhận | Loại sự cố nào, thời điểm xác nhận giao dịch, mất dữ liệu cho phép là bao nhiêu? | RPO, đối soát giao dịch, thử restore/replay. |
| Duy trì dịch vụ khi sự cố cloud | Chịu lỗi instance, AZ, region hay provider? Luồng nào quan trọng? | SLI/SLO theo API/nghiệp vụ, RTO và kết quả diễn tập. |
| Hiệu năng thấp độ trễ | Người dùng ở đâu, có phụ thuộc chéo cloud không? | p95/p99 end-to-end, tỷ lệ lỗi theo tải, độ trễ mạng. |
| Dữ liệu tuân thủ khu vực | Dữ liệu nào, region/pháp lý nào, ai quản lý khóa? | Data-flow map, kiểm tra backup/replication và chính sách truy cập. |
| Có thể chuyển nhà cung cấp | Trong bao lâu, dữ liệu nào, chấp nhận đổi feature đến mức nào? | Thử export/restore, build/deploy workload mẫu ở provider thay thế. |
| Chi phí có giới hạn | Dải tải, mức standby, mức chấp nhận rủi ro? | TCO theo kịch bản, chi phí mỗi giao dịch, budget alerts. |

### 8.1. Quy trình đánh giá thực tế

1. **Chốt luồng nghiệp vụ và ưu tiên:** Ví dụ đăng nhập, đặt chỗ, thanh toán và báo cáo có mức độ quan trọng khác nhau.
2. **Viết kịch bản lỗi và mục tiêu chất lượng:** Tách mất một AZ, một region, một dịch vụ managed và toàn nhà cung cấp.
3. **Vẽ bản đồ phụ thuộc:** Từ DNS, định danh, API, dịch vụ phụ trợ, database đến thanh toán, CI/CD và quản trị khóa.
4. **Đưa ra ít nhất hai phương án đủ điều kiện:** Ví dụ multi-region cùng provider và warm standby trên provider khác. Không chỉ so phương án đơn giản thiếu dự phòng với phương án phức tạp đầy đủ dự phòng.
5. **Định lượng TCO và đánh đổi:** Gồm OPEX, CAPEX chuyển đổi, egress, nhân lực, SLO, dữ liệu, tuân thủ và khả năng hỗ trợ.
6. **Làm thử một lát cắt kiến trúc có rủi ro cao:** Ví dụ backup/restore sang provider thứ hai hoặc triển khai API cùng dữ liệu thử để đo p95.
7. **Ghi quyết định thành ADR**, kèm lý do, điều kiện xem xét lại và owner.
8. **Diễn tập theo lịch phù hợp:** Bảo đảm kiến trúc vẫn đáp ứng yêu cầu khi đội ngũ, phiên bản và tải thay đổi.

### 8.2. Ma trận ra quyết định mang tính định hướng

| Bối cảnh | Mô hình nên đánh giá trước | Lý do |
| --- | --- | --- |
| MVP, đội vận hành nhỏ, chi phí nhạy cảm | Single-provider với multi-AZ, backup và khả năng mở rộng theo tải | Giảm độ phức tạp ban đầu, vẫn có thể đáp ứng nhiều SLO thực tế. |
| Ứng dụng quan trọng, cần chịu lỗi toàn region | Multi-region cùng provider **và** phương án nhiều provider như các lựa chọn so sánh | Tập trung so RTO/RPO thực đo, phụ thuộc, vận hành và chi phí. |
| Hợp đồng yêu cầu độc lập khỏi một provider | Multi-cloud có thiết kế dữ liệu, failover, bảo mật và kiểm thử độc lập | Lý do nghiệp vụ rõ ràng; cần chứng minh mức độc lập. |
| Đơn vị kinh doanh ở nhiều quốc gia có yêu cầu dữ liệu khác nhau | Phân chia workload theo thị trường/provider hoặc region phù hợp | Thỏa yêu cầu pháp lý và độ trễ, nhưng phải kiểm soát chia sẻ dữ liệu. |
| Hợp nhất hệ thống sau sáp nhập, hiện có hai cloud | Multi-cloud chuyển tiếp hoặc lâu dài sau khi đánh giá | Cần xác định giá trị hợp nhất, chi phí di chuyển và khả năng hợp tác. |
| Ứng dụng cần khai thác một dịch vụ chuyên biệt | Tách workload sử dụng dịch vụ đó qua API/batch | Không nhất thiết phải nhân đôi toàn bộ ứng dụng và database. |

Ma trận chỉ gợi ý điểm bắt đầu. Kết luận cần dựa trên mô hình sự cố, ràng buộc, dữ liệu vận hành và kết quả thử nghiệm của hệ thống cụ thể.

## 9. Case study: kiến trúc nền tảng đặt chỗ

Một công ty triển khai nền tảng đặt chỗ trên cloud, gồm Spring Boot API, PostgreSQL, Redis/cache, queue và hệ thống thông báo. Nghiệp vụ yêu cầu:

- Đỉnh tải **1.000 yêu cầu/giây** cho luồng tìm kiếm; p95 độ trễ không quá **400 ms** trong bài thử tải 30 phút.
- Luồng đặt chỗ đạt tỷ lệ thành công ít nhất **99,95%** trên tập yêu cầu hợp lệ trong cửa sổ 30 ngày, theo định nghĩa đo được thống nhất.
- Khi **một AZ lỗi**, RTO cho đặt chỗ không quá **15 phút** và RPO không quá **1 phút**.
- Có phương án phục hồi khi lỗi toàn region; business chấp nhận **RTO 4 giờ, RPO 30 phút** cho tình huống này.
- Cần báo cáo chi phí mỗi đơn hoàn tất và giữ ngân sách theo mức đã được phê duyệt.

Các ngưỡng trên là **giả định cho tình huống học tập**, không đại diện cho SLA của một nhà cung cấp.

### Phương án A — Single-provider, multi-AZ và DR ở region thứ hai

API chạy trên ít nhất hai AZ, sau load balancer; database có cơ chế failover và backup/restore đã kiểm thử. Với rủi ro mất toàn region, triển khai DR tại region thứ hai với mức dự phòng phù hợp mục tiêu 4 giờ/30 phút. Redis/cache được xem là dữ liệu có thể tái tạo nếu nghiệp vụ cho phép; đặt chỗ đã xác nhận phải được giữ bằng dữ liệu giao dịch và cơ chế đối soát.

**Lợi ích:** Ít ranh giới vận hành hơn; pipeline, IAM và observability thuận tiện. Các kịch bản AZ, region có giải pháp và phép kiểm chứng cụ thể.

**Giới hạn:** Vẫn phụ thuộc cùng nhà cung cấp, kể cả một số control plane và dịch vụ tài khoản toàn cục. Phải đánh giá xem chiến lược khôi phục còn hoạt động khi nhiều dịch vụ của provider cùng bị ảnh hưởng.

### Phương án B — Multi-cloud warm standby

Giữ production tại X, chuẩn bị môi trường tối thiểu tại Y, đồng bộ/di chuyển dữ liệu bằng cơ chế phù hợp, duy trì container image và cách xây dựng lại hạ tầng ở Y. Runbook bao gồm phát hiện lỗi, khóa hoặc cô lập đường ghi cũ, kiểm tra điểm dữ liệu, tăng tài nguyên Y, chuyển hướng người dùng và đối soát sau failover.

**Lợi ích:** Có thể tăng tính độc lập trước một số sự cố nghiêm trọng ở X và mở ra phương án chuyển provider.

**Giới hạn:** Để phục hồi giao dịch, phải giải quyết replication, thứ tự sự kiện, khả năng ghi ở Y và tránh booking trùng. Network/egress, quản trị khóa, QA, nhân sự và diễn tập làm TCO tăng. RTO/RPO chỉ được xác nhận sau bài thử.

### Kết luận của nhóm kiến trúc trong tình huống giả định

Nếu phương án A **đạt các kịch bản chất lượng và ràng buộc** qua diễn tập, còn rủi ro cấp toàn provider chưa có yêu cầu bắt buộc phải độc lập, nhóm có thể **chọn single-provider, multi-AZ + DR multi-region** ở giai đoạn đầu. Quyết định phải ghi rõ rủi ro tồn dư và ngưỡng xem xét lại.

Nếu sau đó hợp đồng bắt buộc khôi phục ngay cả khi dịch vụ cốt lõi của provider X mất trên diện rộng, hoặc thực tế cho thấy A không đáp ứng phạm vi sự cố cần chịu, nhóm cần đánh giá và thử nghiệm phương án B. Không nên chuyển sang multi-cloud chỉ để thay tên mô hình trong tài liệu.

**Điều kiện xem xét lại** có thể là: yêu cầu RTO/RPO thay đổi, phát sinh ràng buộc khu vực dữ liệu, doanh nghiệp mở rộng thị trường, chi phí tăng vượt ngưỡng hoặc có sự cố thực tế làm lộ điểm phụ thuộc lớn.

## 10. Chứng minh khả năng phục hồi bằng diễn tập

Một bản thiết kế multi-cloud chỉ có giá trị khi thực tế **chuyển đổi được dịch vụ và dữ liệu**. Bài thử nên có mức nguy hiểm được kiểm soát, môi trường phù hợp và người chịu trách nhiệm rõ ràng.

Ví dụ quy trình diễn tập warm standby:

1. **Chuẩn bị:** Chọn luồng đặt chỗ và kịch bản giả lập mất provider X; ghi lại SLO/RTO/RPO, đường phụ thuộc, điểm đo, bộ dữ liệu thử và tiêu chí dừng.
2. **Xác nhận trạng thái nền:** Đo tỷ lệ lỗi, p95, replication lag, số lượng giao dịch, trạng thái backup và quota tại Y.
3. **Tiêm lỗi có kiểm soát:** Ngăn kết nối tới workload X trong môi trường thử phù hợp; ghi chính xác thời điểm bắt đầu sự cố.
4. **Cô lập nguồn ghi cũ:** Đảm bảo hai bên không cùng nhận giao dịch ghi xung đột; kiểm tra trạng thái dữ liệu và những request đang xử lý.
5. **Kích hoạt môi trường Y:** Hoàn tất restore/replication, mở rộng compute, chuyển hướng traffic theo runbook và xác minh phụ thuộc.
6. **Kiểm tra nghiệp vụ:** Đăng nhập, tìm kiếm, đặt chỗ, idempotency/retry, đối soát và báo cáo lỗi. Đo thời điểm người dùng thực sự có thể hoàn tất tác vụ.
7. **Đánh giá:** So RTO/RPO thực đo với mục tiêu, kiểm tra chi phí và sự kiện security, xác định thao tác thủ công gây chậm.
8. **Phục hồi trạng thái bình thường:** Có kế hoạch đưa traffic và dữ liệu trở về, tránh ghi ngược thiếu kiểm soát; cập nhật runbook và ADR.

Lưu ý: Cấu hình **DNS TTL thấp** không đảm bảo mọi client sẽ chuyển đổi tức thì vì có cache, session đang mở và lỗi ngoài DNS. Thời gian phục hồi phải được đo **end-to-end từ góc nhìn nghiệp vụ**. Có thể cần kế hoạch thao tác thủ công nếu tự động hóa hoặc control plane cũng đang gặp sự cố.

### Chỉ số nên thu thập

| Kết quả | Chỉ số | Dấu hiệu chưa đạt |
| --- | --- | --- |
| Phục hồi dịch vụ | Thời gian từ sự cố đến giao dịch hợp lệ thành công trên Y | RTO đo thực tế vượt mục tiêu, hoặc chỉ đo lúc VM/database bật. |
| Bảo toàn dữ liệu | RPO thực tế, số giao dịch mất/chưa đối soát | Không xác định được điểm phục hồi hay có đơn trùng. |
| Chất lượng trải nghiệm | p95/p99, tỷ lệ thành công, tỷ lệ timeouts sau chuyển đổi | API mở nhưng người dùng không hoàn tất đặt chỗ. |
| Năng lực dự phòng | Throughput, quota, độ trễ khi scale-out | Provider Y không phục vụ được tải cần thiết. |
| Bảo mật và kiểm toán | Kiểm soát truy cập, audit event, mã hóa và quản lý khóa | Cơ chế khẩn cấp mở quyền quá rộng hoặc không ghi vết. |
| Chi phí | Chi phí kỳ diễn tập và chi phí duy trì DR | TCO cao hơn giả định mà chưa có điều chỉnh. |

## 11. Liên hệ với nguyên tắc Well-Architected

Lựa chọn một hay nhiều nhà cung cấp nên được đánh giá qua các trụ cột **Well-Architected**, thay vì xem multi-cloud như một mục tiêu độc lập.

| Trụ cột | Câu hỏi trọng tâm |
| --- | --- |
| **Operational Excellence** | Nhóm có đủ người, công cụ, tài liệu, quy trình thay đổi và diễn tập cho số nền tảng đã chọn không? |
| **Security** | Có bảo đảm identity, network, encryption, secrets, audit và data residency trên mọi môi trường không? |
| **Reliability** | Kịch bản lỗi nào được chịu đựng; RTO/RPO và mức độc lập đã được đo như thế nào? |
| **Performance Efficiency** | Latency/throughput có đạt khi đi xuyên provider hoặc chạy tại môi trường dự phòng không? |
| **Cost Optimization** | TCO, chi phí mỗi giao dịch và giá trị của dự phòng có hợp lý so với mục tiêu nghiệp vụ không? |
| **Sustainability** | Có tránh duy trì tài nguyên dư thừa ngoài nhu cầu và giảm xử lý/truyền dữ liệu không cần thiết không? |

Đánh giá theo trụ cột là quá trình liên tục. Khi mức tải, yêu cầu tuân thủ và rủi ro thay đổi, quyết định nhà cung cấp cũng cần được xem lại.

## 12. Mẫu ADR ngắn để ghi quyết định

~~~yaml
id: ADR-007
title: Chon mo hinh nha cung cap cloud cho he thong dat cho
status: proposed
decision_owner: Architecture Review Board
business_drivers:
  - Dat cho on dinh khi mot AZ gap loi
  - Khoi phuc sau loi region trong gioi han da thong nhat
quality_scenarios:
  - QA-REL-01
  - QA-REC-01
alternatives:
  - single_provider_multi_region
  - multi_cloud_warm_standby
decision: single_provider_multi_region
rationale:
  - Dat duoc RTO va RPO trong dien tap hien tai
  - Phu hop ngan sach va nang luc van hanh
residual_risks:
  - Su co tren dien rong cua provider chinh
verification:
  - TEST-AZ-FAILOVER
  - TEST-REGION-RESTORE
review_triggers:
  - Thay doi rang buoc hop dong
  - RTO_RPO_that_bai_trong_dien_tap
  - Tang truong tai_vuot_nang_luc_du_phong
~~~

Các mã kịch bản và test trong mẫu chỉ là ví dụ về cách truy vết. ADR dùng trong dự án thật phải có **ngày quyết định, người chịu trách nhiệm, bằng chứng đo cụ thể và kế hoạch kiểm tra lại**.

## 13. Sai lầm thường gặp

| Nhận định sai | Vì sao sai | Cách tiếp cận phù hợp |
| --- | --- | --- |
| “Hai cloud sẽ không bao giờ cùng lỗi.” | Vẫn có code lỗi, DNS, identity, mạng và đối tác dùng chung. | Kiểm tra toàn bộ dependency graph và các miền lỗi chung. |
| “Có multi-AZ tức là có multi-cloud.” | AZ nằm trong phạm vi một nhà cung cấp. | Ghi rõ số provider, region, AZ và dịch vụ. |
| “Backup tại cloud thứ hai bảo đảm RPO bằng 0.” | Backup có độ trễ và có thể thiếu dữ liệu mới nhất. | Diễn tập restore, đo RPO thực tế và đối soát. |
| “Kubernetes khiến ứng dụng hoàn toàn portable.” | Network, storage, IAM, managed service và quota khác nhau. | Thử triển khai workload thực tế trên nền tảng đích. |
| “Multi-cloud luôn tăng hiệu năng.” | Gọi API xuyên cloud có thể tăng latency/egress. | Đo p95/p99 theo hành trình nghiệp vụ và tải tương ứng. |
| “Chỉ cần so giá VM theo giờ.” | Bỏ qua database, dữ liệu, mạng, vận hành, DR và chuyển đổi. | So TCO theo mục tiêu SLO tương đương. |
| “Failover chỉ là đổi DNS.” | Cần dữ liệu nhất quán, chặn ghi trùng, mở rộng tải và xác minh ứng dụng. | Xây dựng và chạy runbook end-to-end. |
| “Dịch vụ managed nào cũng gây lock-in xấu.” | Có thể giảm đáng kể rủi ro vận hành, chi phí và thời gian ra mắt. | Đánh giá giá trị hiện tại cùng chi phí thoát và điều kiện thay thế. |

## 14. Bài tập thực hành

**Bối cảnh:** Một nền tảng thương mại điện tử đang chạy trên một nhà cung cấp cloud. Đội ngũ 8 người quản lý ứng dụng Java, PostgreSQL và queue. Doanh nghiệp dự định mở thị trường mới. Yêu cầu ban đầu là hệ thống chịu được sự cố AZ trong 15 phút, sự cố region trong 4 giờ, không tạo đơn trùng khi retry và ngân sách hạ tầng giới hạn.

Hãy hoàn thành các công việc sau:

1. Viết ít nhất ba **kịch bản chất lượng sáu phần** tương ứng với lỗi AZ, lỗi region và tăng tải khuyến mãi. Đặt ngưỡng đo minh họa, ghi rõ giả định và điểm đo.
2. Thiết kế hai phương án: **A — single-provider multi-region** và **B — multi-cloud warm standby**. Mỗi phương án nêu các thành phần network, compute, data, deployment, security và monitoring.
3. Chỉ ra ít nhất năm đường phụ thuộc chung có thể khiến cả hai phương án vẫn gặp sự cố.
4. Lập bảng TCO một năm, tính cả egress, môi trường dự phòng, năng lực vận hành, diễn tập và chi phí chuyển đổi. Nếu dữ liệu chi phí chưa có, đưa ra giả định và độ nhạy theo hai mức tải.
5. Thiết kế bài diễn tập đo RTO, RPO, số đơn trùng và thời gian failover từ góc nhìn người dùng.
6. Viết ADR khoảng một trang, gồm lựa chọn, phương án bị loại, lý do, rủi ro tồn dư và điều kiện xem xét lại.

**Gợi ý tự đánh giá:** Một bài làm tốt thể hiện quan hệ rõ ràng giữa **yêu cầu → kịch bản chất lượng → kiến trúc → phép thử → bằng chứng → quyết định**. Nếu chỉ đưa ra hình vẽ hai cloud mà chưa giải thích dữ liệu, đường phụ thuộc và người chịu trách nhiệm failover thì thiết kế chưa đủ để triển khai an toàn.

## 15. Checklist trước khi quyết định

- [ ] Phân biệt đúng single-provider, multi-AZ, multi-region, multi-cloud và hybrid cloud.
- [ ] Có danh sách luồng nghiệp vụ ưu tiên và mục tiêu SLI/SLO, RTO/RPO đã thống nhất.
- [ ] Đã phân tích lỗi ở các cấp instance, AZ, region, provider, ứng dụng và dịch vụ dùng chung.
- [ ] Đã mô tả chủ thể ghi dữ liệu, consistency, replication, backup và khả năng đối soát.
- [ ] Đã xem xét data residency, IAM, secrets, encryption và audit trên từng provider.
- [ ] Đã đo hoặc dự báo latency, egress và chi phí toàn kỳ cho các phương án có mục tiêu chất lượng tương đương.
- [ ] Có kế hoạch DR và diễn tập failover/failback, gồm cả kịch bản control plane không khả dụng.
- [ ] Đã đánh giá năng lực vận hành, quota, hỗ trợ nhà cung cấp và trách nhiệm trực sự cố.
- [ ] Có ADR, bằng chứng kiểm thử, owner và điều kiện xem lại quyết định.
- [ ] Đã đối chiếu với các trụ cột Well-Architected: vận hành, bảo mật, độ tin cậy, hiệu năng, chi phí và tính bền vững.

Lựa chọn **một nhà cung cấp** có thể giúp hệ thống đơn giản, vận hành hiệu quả và đạt chất lượng rất cao khi kiến trúc dự phòng phù hợp. **Nhiều nhà cung cấp** có thể mang lại tính độc lập hoặc khả năng đáp ứng nhu cầu kinh doanh đặc thù, nhưng đòi hỏi giải quyết dữ liệu, phụ thuộc, bảo mật, vận hành và TCO ở cấp toàn hệ thống. Một quyết định kiến trúc tốt phải gắn với **rủi ro cụ thể, chỉ số đo được và bằng chứng diễn tập**, rồi được điều chỉnh khi yêu cầu thực tế thay đổi.

# Xây dựng sơ đồ bối cảnh, triển khai và luồng dữ liệu

> **Phạm vi:** Bài thực hành thiết kế thuộc **CLOUD_ARCHITECTURE**. Người học chuyển yêu cầu nghiệp vụ và phi chức năng thành ba góc nhìn kiến trúc có thể kiểm tra được: **sơ đồ bối cảnh**, **sơ đồ triển khai** và **sơ đồ luồng dữ liệu**. Trọng tâm là lý giải lựa chọn mạng, compute, dữ liệu, mô hình triển khai và các đánh đổi giữa độ tin cậy, bảo mật, khả năng mở rộng, chi phí, vận hành theo tư duy Well-Architected.

## 1. Vì sao cùng một hệ thống cần nhiều sơ đồ?

Một sơ đồ duy nhất thường không thể vừa giải thích cho chủ sản phẩm biết hệ thống giao tiếp với ai, vừa cho kỹ sư hạ tầng biết máy chạy ở vùng mạng nào, vừa cho nhóm bảo mật biết dữ liệu nhạy cảm đi qua các ranh giới tin cậy ra sao. Khi cố nhồi tất cả chi tiết vào một hình, người đọc dễ bỏ sót các giả định hoặc tưởng rằng một đường nối đã giải thích đầy đủ mọi loại tương tác.

Ba sơ đồ phục vụ ba câu hỏi khác nhau:

| Góc nhìn | Câu hỏi cần trả lời | Thành phần chính | Độc giả thường dùng |
|---|---|---|---|
| **Bối cảnh hệ thống (system context)** | Hệ thống phục vụ ai, tương tác với hệ thống nào, ranh giới trách nhiệm nằm ở đâu? | Người dùng, hệ thống cần thiết kế, hệ thống bên ngoài, quan hệ | Product owner, kiến trúc sư, bảo mật, đối tác |
| **Triển khai (deployment)** | Thành phần chạy ở đâu, trên loại tài nguyên nào, các vùng mạng/vùng lỗi kết nối thế nào? | DNS, ingress, subnet, AZ, workload, DB, queue, đường mạng, vùng lỗi | Cloud architect, platform engineer, SRE |
| **Luồng dữ liệu (data flow)** | Dữ liệu gì được tạo, đọc, ghi và chuyển qua đâu; ai có quyền nhận nó? | Tác nhân, tiến trình xử lý, kho dữ liệu, dòng dữ liệu, ranh giới tin cậy | Backend, data engineer, security, tuân thủ |

Sơ đồ bối cảnh cho thấy **hệ thống như một hộp đen**. Sơ đồ triển khai mở hộp đen theo nơi đặt và cách kết nối các thành phần chạy thật. Sơ đồ luồng dữ liệu mở hộp đen theo **đường đi và phép biến đổi dữ liệu**. Ba hình cần cùng tên hệ thống, cùng đối tác và không mâu thuẫn về hành vi.

### 1.1. Kết quả học tập

Sau bài này, người học có thể:

- Chọn đúng phạm vi, đối tượng đọc và mức chi tiết cho từng sơ đồ.
- Thu thập yêu cầu và quyết định ranh giới hệ thống trước khi chọn dịch vụ đám mây.
- Tự vẽ ba sơ đồ liên kết của một ứng dụng nhiều thành phần bằng ký pháp dễ đọc như Mermaid.
- Truy vết một hành trình nghiệp vụ qua ba sơ đồ, từ tác nhân đến workload, database, queue và đối tác.
- Đánh dấu ranh giới mạng, danh tính, dữ liệu nhạy cảm, điểm lỗi đơn, đường khôi phục và giả định cần kiểm chứng.
- Bảo vệ quyết định thiết kế theo Well-Architected, chỉ ra sự đánh đổi giữa khả năng mở rộng, bảo mật, độ tin cậy, chi phí và mức độ phức tạp vận hành.

## 2. Quy ước: vẽ cái gì, ở mức nào?

Trong bài này, **hệ thống** là một sản phẩm phần mềm có trách nhiệm nghiệp vụ xác định, chẳng hạn hệ thống đặt hàng. **Thành phần** có thể là API, worker, kho dữ liệu hoặc gateway. **Nút triển khai** là nơi chứa một hoặc nhiều thành phần khi chạy, chẳng hạn dịch vụ container trong một availability zone (AZ). **Luồng dữ liệu** là thông tin được truyền hoặc lưu, không đơn thuần là kết nối mạng.

### 2.1. Ranh giới và ký pháp

Không có một quy ước ký hiệu duy nhất phù hợp mọi tổ chức. Hãy đặt một **legend** hoặc ghi chú ngắn ngay cạnh sơ đồ, nêu:

- Hình người/hộp có nhãn **Actor**: tác nhân trực tiếp.
- Hộp **System**: hệ thống sở hữu nghiệp vụ; hộp **External System**: đối tác/hệ thống ngoài phạm vi thiết kế.
- Khung **Cloud/Region/VPC/Subnet/AZ**: vị trí hoặc ranh giới triển khai, không mặc nhiên là ranh giới phân quyền.
- Hình trụ **Data Store**: nơi dữ liệu tồn tại bền vững; hàng đợi được ghi riêng vì có ngữ nghĩa truyền thông điệp.
- Mũi tên gắn **tên giao thức** trong sơ đồ triển khai hoặc **tên dữ liệu** trong sơ đồ luồng dữ liệu.
- Khung hoặc đường chú giải **Trust Boundary**: nơi thay đổi mức tin cậy, chủ thể quản trị hoặc cơ chế xác thực.

Sơ đồ bối cảnh có thể theo phong cách C4 System Context; sơ đồ triển khai tương đương góc nhìn Deployment của C4; sơ đồ luồng dữ liệu có thể theo DFD mức 0/1. Đây là các **góc nhìn bổ sung**, không cần ép mọi ký pháp thành một chuẩn duy nhất. Tập trung vào tính nhất quán của tên gọi và ý nghĩa đường nối.

### 2.2. Những điều sơ đồ không tự chứng minh

- Vẽ hai instance trong hai AZ không chứng minh ứng dụng tự động failover hoặc database có cơ chế sao chép chính xác.
- Vẽ database trong mạng riêng không chứng minh ứng dụng không thể lộ dữ liệu qua API công khai.
- Vẽ đường TLS không chứng minh bí mật được bảo vệ ở mọi nơi lưu hoặc principal chỉ có quyền tối thiểu.
- Vẽ mũi tên một chiều không chứng minh giao thức thật không có phản hồi; nhiều giao thức yêu cầu chiều phản hồi trong cùng phiên.
- Vẽ biểu tượng backup không chứng minh có thể đạt RTO/RPO nếu chưa diễn tập phục hồi.
- Vẽ queue không tự động tạo bảo đảm exactly-once hay bảo đảm đơn hàng và sự kiện được ghi nguyên tử.

Sơ đồ là **mô hình để thảo luận và kiểm chứng**. Khả năng thật phải được xác nhận bằng cấu hình, kiểm thử, số đo và quy trình vận hành.

## 3. Đề bài xuyên suốt: hệ thống đặt hàng trực tuyến

Một doanh nghiệp giả định đang phát triển hệ thống **MâyShop Order** phục vụ khách hàng đặt hàng qua website. Hệ thống cần quản lý giỏ hàng, tạo đơn, nhận kết quả thanh toán, cập nhật trạng thái và gửi email xác nhận. Hàng tồn kho được quản lý bởi hệ thống ERP của doanh nghiệp; thanh toán và gửi email do hai nhà cung cấp bên ngoài đảm nhiệm.

> **Mọi con số trong bài là giả định giảng dạy**, dùng để thực hành quyết định kiến trúc; chúng không phải cam kết hiệu năng hay khuyến nghị mặc định cho môi trường thật.

### 3.1. Yêu cầu nghiệp vụ

| ID | Nhu cầu | Kết quả có thể quan sát |
|---|---|---|
| BR-01 | Khách duyệt sản phẩm và tạo đơn | Hệ thống tạo mã đơn duy nhất, hiển thị tổng tiền và trạng thái |
| BR-02 | Khách thanh toán qua nhà cung cấp thanh toán | Chỉ một lần ghi nhận tác động thanh toán cho một giao dịch hợp lệ |
| BR-03 | Nhận thông báo thanh toán bất đồng bộ | Callback/webhook trùng hoặc đến muộn không tạo đơn/trừ tiền lặp |
| BR-04 | Kiểm tra và giữ chỗ tồn kho qua ERP | Không xác nhận đơn vượt quy tắc tồn kho được thống nhất |
| BR-05 | Gửi email sau khi xác nhận thanh toán | Có thể theo dõi tác vụ gửi thành công, thất bại, retry và DLQ |
| BR-06 | Nhân viên hỗ trợ tra cứu trạng thái đơn | Nhân viên chỉ xem/sửa dữ liệu trong phạm vi được giao |

### 3.2. Yêu cầu phi chức năng và giả định

| ID | Yêu cầu mẫu | Hệ quả thiết kế ban đầu |
|---|---|---|
| NFR-01 | Đỉnh 300 yêu cầu API/giây, có khả năng tăng cao vào đợt khuyến mại | Tách các thành phần có thể scale; kiểm tra DB và kết nối đối tác |
| NFR-02 | p95 API tạo đơn ≤ 400 ms dưới tải đã xác định | Quan sát độ trễ đầu cuối; hạn chế phụ thuộc đồng bộ trong đường nóng |
| NFR-03 | SLO 99,9% yêu cầu hợp lệ thành công theo cửa sổ 30 ngày | Có metric theo hành trình nghiệp vụ, không chỉ health check |
| NFR-04 | Một AZ mất khả năng phục vụ không làm toàn bộ hệ thống dừng | API/worker phân bố nhiều AZ, kiểm chứng cơ chế DB/ingress failover |
| NFR-05 | RTO ≤ 60 phút, RPO ≤ 5 phút cho kịch bản thảm họa đã định | Xác định kịch bản, backup/replication và diễn tập khôi phục |
| NFR-06 | Dữ liệu khách hàng và đơn hàng cần bảo vệ; không đưa token thanh toán vào log | Phân loại dữ liệu, quyền tối thiểu, mã hóa và kiểm soát log |
| NFR-07 | Có ngân sách, phân bổ chi phí theo môi trường và khả năng đo chi phí/đơn | Monitoring/FinOps, lựa chọn dịch vụ phù hợp mức tải |

**Làm rõ phạm vi trước khi vẽ:** MâyShop Order sở hữu dữ liệu đơn hàng và điều phối thanh toán, nhưng không sở hữu sổ cái của nhà cung cấp thanh toán. ERP sở hữu số lượng tồn kho gốc. Dịch vụ email là nơi vận chuyển thông điệp; việc nhận phản hồi “accepted” từ nhà cung cấp chưa đồng nghĩa email đã tới hộp thư khách hàng.

### 3.3. Danh mục tác nhân và phụ thuộc

| Tên nhất quán | Thuộc phạm vi MâyShop Order? | Trách nhiệm |
|---|---|---|
| **Khách hàng** | Không, là người dùng | Duyệt và đặt hàng, kiểm tra trạng thái |
| **Nhân viên hỗ trợ** | Không, là người dùng | Tra cứu, xử lý yêu cầu hỗ trợ theo quyền |
| **MâyShop Order** | Có | Cung cấp ứng dụng, quản lý đơn, điều phối luồng |
| **Cổng thanh toán** | Không, đối tác | Tạo phiên thanh toán và phát trạng thái giao dịch |
| **ERP tồn kho** | Không, hệ thống doanh nghiệp khác | Kiểm tra/giữ chỗ tồn kho và trạng thái hàng |
| **Nhà cung cấp email** | Không, đối tác | Nhận yêu cầu gửi và phát trạng thái vận chuyển nếu có |

Khi cả nhóm thống nhất danh mục, **không đổi tên tùy ý** thành “Payment Service”, “PSP”, “Gateway A” ở các hình khác nhau mà không có chú giải. Tên nhất quán giúp kiểm tra tính đầy đủ giữa sơ đồ.

## 4. Bước 1: xây dựng sơ đồ bối cảnh hệ thống

Sơ đồ bối cảnh tập trung vào **quan hệ**. Nó nên có một nút chính cho MâyShop Order, các tác nhân người dùng và hệ thống khác mà sản phẩm tương tác. Không cần đặt container, VPC, database, cổng mạng, queue hoặc loại máy trong hình này.

### 4.1. Cách làm

1. Viết câu mô tả hệ thống bằng một câu: “MâyShop Order cho phép khách hàng đặt hàng trực tuyến và theo dõi đơn, phối hợp với các dịch vụ thanh toán, tồn kho và email.”
2. Đặt MâyShop Order ở giữa; vẽ rõ ranh giới hệ thống chịu trách nhiệm phát triển.
3. Liệt kê những người dùng và đối tác **trực tiếp tương tác** với hệ thống; loại bỏ các phụ thuộc không liên quan đến phạm vi phiên bản hiện tại.
4. Với mỗi kết nối, ghi **động từ nghiệp vụ** và dữ liệu/giá trị được trao đổi; tránh chỉ ghi “API”.
5. Kiểm tra từng yêu cầu BR-01 đến BR-06 có tác nhân hoặc phụ thuộc tương ứng.
6. Chỉ thêm chi tiết mới khi cần làm rõ trách nhiệm hoặc yêu cầu tuân thủ.

### 4.2. Sơ đồ bối cảnh mẫu

~~~mermaid
flowchart LR
    C["Khách hàng\nActor"]
    S["Nhân viên hỗ trợ\nActor"]
    subgraph Bound["Ranh giới hệ thống đang thiết kế"]
        O["MâyShop Order\nHệ thống đặt hàng"]
    end
    P["Cổng thanh toán\nExternal system"]
    E["ERP tồn kho\nExternal system"]
    M["Nhà cung cấp email\nExternal system"]
    C -->|"Duyệt, đặt hàng, xem trạng thái"| O
    S -->|"Tra cứu và hỗ trợ theo quyền"| O
    O <-->|"Tạo phiên, nhận kết quả thanh toán"| P
    O <-->|"Kiểm tra/giữ chỗ tồn kho"| E
    O -->|"Yêu cầu gửi email xác nhận"| M
~~~

**Cách đọc:** MâyShop Order là hệ thống duy nhất nằm trong ranh giới chịu trách nhiệm thiết kế của nhóm. Cổng thanh toán và ERP không “nằm trong ứng dụng” chỉ vì được gọi từ API của ứng dụng. Mũi tên có hai đầu mô tả sự trao đổi ở cấp nghiệp vụ, không phải khẳng định mọi giao tiếp có cùng giao thức hay độ tin cậy.

### 4.3. Câu hỏi phản biện sơ đồ bối cảnh

- ERP thuộc cùng doanh nghiệp nhưng do một nhóm khác vận hành: ai sở hữu SLA và thay đổi giao diện? Sơ đồ cần coi ERP là hệ thống ngoài phạm vi MâyShop Order.
- Cổng thanh toán gửi webhook đến ứng dụng: đây vẫn là tương tác từ hệ thống ngoài vào ranh giới ứng dụng, cần thể hiện dù dùng cùng API.
- Khách hàng được chuyển sang trang thanh toán của đối tác: có cần thể hiện quan hệ trực tiếp giữa khách và đối tác? Nếu hành trình thật có redirect hoặc iframe do đối tác sở hữu, có thể thêm đường “Khách ↔ Cổng thanh toán” và chú thích trách nhiệm khi người dùng rời hệ thống.
- Dữ liệu email có chứa mã đơn và địa chỉ email: hợp đồng xử lý dữ liệu với nhà cung cấp ở đâu? Đây là một ranh giới dữ liệu sẽ được làm rõ trong DFD.
- Nhà cung cấp đăng nhập/SSO có phải tác nhân bên ngoài không? Chỉ thêm khi ứng dụng thật sự tích hợp, không suy đoán.

Sơ đồ bối cảnh **đạt yêu cầu** khi người không biết chi tiết hạ tầng vẫn hiểu hệ thống tạo giá trị gì, giao tiếp với ai và thành phần nào nằm ngoài quyền kiểm soát trực tiếp.

## 5. Bước 2: xây dựng sơ đồ triển khai

Sơ đồ triển khai trả lời “**nó chạy ở đâu và kết nối bằng cách nào?**”. Đầu vào là hành trình nghiệp vụ và các NFR về hiệu năng, HA, phục hồi, mạng và bảo mật. Đừng chọn dịch vụ chỉ vì biểu tượng đẹp hoặc đang là xu hướng; mỗi khối nên có lý do gắn với yêu cầu.

### 5.1. Chọn các lớp cần biểu diễn

Với MâyShop Order, kiến trúc mẫu ở mức khái niệm:

- **Biên Internet:** DNS, lớp chống lạm dụng/WAF hoặc CDN khi cần, public ingress/load balancer phục vụ HTTPS.
- **Workload:** API và worker chạy trong mạng ứng dụng riêng, phân bố trên ít nhất hai AZ để tránh phụ thuộc vào một AZ.
- **Lưu trữ nghiệp vụ:** cơ sở dữ liệu quan hệ được quản lý với cơ chế sẵn sàng nhiều AZ được cấu hình và kiểm chứng, không giả định mọi mô hình triển khai DB đều có failover tự động.
- **Xử lý bất đồng bộ:** hàng đợi được quản lý, worker xử lý sự kiện có idempotency, retry và DLQ.
- **Kết nối bên ngoài:** cổng thanh toán, ERP và email cần đường ra phù hợp, cùng kiểm soát danh tính và giới hạn quyền; webhook thanh toán đi qua ingress.
- **Vận hành:** metric, log, distributed trace, audit, secret manager, backup/restore và cảnh báo.

Lựa chọn container không phải bắt buộc; VM, serverless hay PaaS đều có thể phù hợp. Trong ví dụ ta chọn **dịch vụ container** vì cần vận hành API và worker độc lập, scale theo tải và quản lý rollout. Loại compute thật phải được đánh giá theo khả năng đội ngũ, độ trễ khởi tạo, chi phí, tính di động và yêu cầu vận hành.

### 5.2. Sơ đồ triển khai mẫu

~~~mermaid
flowchart TB
    Customer["Khách hàng / Nhân viên hỗ trợ"]
    DNS["DNS + lớp biên HTTPS\nWAF/CDN nếu cần"]
    PSP["Cổng thanh toán\nngoài hệ thống"]
    ERP["ERP tồn kho\nngoài hệ thống"]
    Mail["Nhà cung cấp email\nngoài hệ thống"]
    Customer -->|"HTTPS 443"| DNS
    PSP -->|"Webhook HTTPS có xác thực"| DNS
    subgraph Region["Cloud region - môi trường Production"]
        subgraph VPC["Mạng ứng dụng / VPC"]
            LB["Public ingress / Load balancer"]
            subgraph AZ1["Availability Zone A"]
                API1["API container A\nprivate subnet"]
                W1["Worker A\nprivate subnet"]
            end
            subgraph AZ2["Availability Zone B"]
                API2["API container B\nprivate subnet"]
                W2["Worker B\nprivate subnet"]
            end
            EG["Kết nối egress có kiểm soát\nNAT / private connectivity tùy đích"]
        end
        Q["Managed queue + DLQ"]
        DB[("Managed relational DB\nHA nhiều AZ theo cấu hình")]
        Sec["Workload identity + Secret manager"]
        Obs["Log / metrics / traces / audit"]
        Backup["Backup / phương án DR"]
        LB -->|"API private"| API1
        LB -->|"API private"| API2
        API1 <-->|"Kết nối DB được giới hạn"| DB
        API2 <-->|"Kết nối DB được giới hạn"| DB
        API1 -->|"TLS + IAM / sự kiện"| Q
        API2 -->|"TLS + IAM / sự kiện"| Q
        Q -->|"Thông điệp / pull"| W1
        Q -->|"Thông điệp / pull"| W2
        W1 <-->|"Truy cập trạng thái"| DB
        W2 <-->|"Truy cập trạng thái"| DB
        DB --> Backup
        API1 -.-> Sec
        API2 -.-> Sec
        W1 -.-> Sec
        W2 -.-> Sec
        API1 -.-> Obs
        API2 -.-> Obs
        W1 -.-> Obs
        W2 -.-> Obs
        API1 --> EG
        API2 --> EG
        W1 --> EG
        W2 --> EG
    end
    DNS -->|"HTTPS / ingress được duyệt"| LB
    EG -->|"HTTPS, danh tính và timeout"| PSP
    EG -->|"Kết nối tích hợp đã duyệt"| ERP
    EG -->|"HTTPS tới email API"| Mail
~~~

**Chú giải và giới hạn:** Hình là **sơ đồ triển khai khái niệm**, không phải sơ đồ từng route table, subnet CIDR hay endpoint thật của một nhà cung cấp. Database và queue được vẽ ở cấp dịch vụ vùng (regional service) để tránh ngộ nhận rằng biểu tượng nằm trong đúng một AZ. Triển khai thực cần xác minh mô hình HA, replication, quyền truy cập và vị trí endpoint của từng dịch vụ. Đường từ worker tới queue được vẽ theo chiều nhận thông điệp về mặt logic; ở nhiều message broker, chính worker chủ động gọi/poll đến queue bằng TLS.

### 5.3. Ma trận kết nối phải đi kèm

Sơ đồ chỉ cho biết các kết nối chính; **ma trận mạng** xác nhận nơi nào cần mở cổng và ai có thể gọi:

| Nguồn | Đích | Hình thức | Điều kiện cho phép |
|---|---|---|---|
| Khách hàng Internet | DNS/ingress | HTTPS 443 | Public vì đây là sản phẩm dành cho khách; có TLS và chống lạm dụng |
| Cổng thanh toán | Endpoint webhook ở ingress | HTTPS 443 | Xác minh chữ ký/yêu cầu, chống replay, áp dụng idempotency |
| Load balancer | API A/B | Cổng ứng dụng riêng, ví dụ 8080 | Chỉ nhận từ ingress được duyệt, dùng health check |
| API A/B và worker A/B | DB | Cổng DB, ví dụ 5432 | Network policy + danh tính DB phù hợp; không mở DB công khai |
| API | Managed queue | HTTPS/TLS hoặc giao thức broker | IAM/workload identity giới hạn hành động publish |
| Worker | Managed queue | HTTPS/TLS hoặc giao thức broker | IAM/workload identity giới hạn consume/ack/DLQ |
| API/worker | ERP, thanh toán, email | Giao thức đã thỏa thuận, thường HTTPS | Egress kiểm soát, timeout, retry và thông tin xác thực |
| Workload | Secret manager / observability | Endpoint bảo vệ | Quyền tối thiểu, mã hóa, log không chứa bí mật |

**Đường phản hồi mạng** thường đi theo trạng thái kết nối, không phải mọi giao thức phải mở một rule inbound mới. Cấu hình thực tế cần kiểm tra security group, firewall, route, DNS, private endpoint/NAT và cả IPv4/IPv6.

### 5.4. Định vị các ranh giới tin cậy

Trên sơ đồ triển khai, đánh dấu tối thiểu:

1. **Internet → lớp ingress**: mọi yêu cầu đều không đáng tin mặc định; cần TLS, kiểm tra dữ liệu vào, xác thực/ủy quyền tương ứng và giới hạn lạm dụng.
2. **Ingress → workload**: chỉ công khai các route nghiệp vụ; cổng debug và quản trị không xuất hiện qua public ingress.
3. **Workload → DB/queue/secret**: không cấp quyền “mọi hành động trên mọi tài nguyên”; mỗi workload có danh tính riêng và quyền hẹp.
4. **Workload → đối tác**: dữ liệu rời miền kiểm soát của ứng dụng; cần hợp đồng, xử lý lỗi, hạn chế thông tin chia sẻ và khả năng kiểm toán.
5. **Môi trường production ↔ staging/dev**: tách danh tính, dữ liệu, secret và giới hạn mạng; không dùng chung khóa sản xuất với môi trường thử nghiệm.

Địa chỉ IP riêng **không đồng nghĩa** ứng dụng có quyền đúng, và TLS **không đồng nghĩa** đầu nhận đã được phân quyền. Cần thiết kế cả mạng và IAM/authorization.

### 5.5. Vị trí vùng lỗi, scale và DR

Một kiến trúc nhiều AZ phải trả lời cụ thể:

- API/worker có phân bố thực sự qua hai AZ hay scheduler có thể dồn hết vào một nơi?
- Tại thời điểm một AZ mất, AZ còn lại có đủ năng lực tối thiểu không? Scale cần bao lâu; connection pool và hạn mức DB có chịu nổi không?
- Load balancer và health check có nhận ra instance lỗi, ngừng gửi traffic và phục hồi phiên hợp lý không?
- Database có failover giữa AZ đúng kiểu deployment không? Các kết nối đang chạy xử lý timeout/retry ra sao?
- Queue và secret manager có SLA và cơ chế chịu lỗi phù hợp với mục tiêu ứng dụng không?
- Nếu mất **toàn region**, backup/replica ở đâu, người nào kích hoạt DR và đã đo RTO/RPO chưa?

**Multi-AZ không mặc nhiên là multi-region DR.** Nếu NFR-05 áp dụng cho thảm họa mất vùng, sơ đồ chi tiết phải bổ sung vùng DR, nơi lưu backup được bảo vệ, đường chuyển traffic và cơ chế phục hồi dữ liệu; trong sơ đồ mẫu chỉ đặt placeholder **“Backup / phương án DR”** vì phương án cụ thể chưa được chọn.

### 5.6. Kiểm tra dung lượng và các đánh đổi

Giả sử API đặt hàng cần 300 yêu cầu/giây với p95 ≤ 400 ms. Không thể suy trực tiếp số container từ số liệu này. Cần đo tốc độ xử lý một instance ở tải phù hợp, CPU, bộ nhớ, DB connections, thời gian chờ ERP và cổng thanh toán; sau đó dự phòng cho khi một AZ bị mất.

Ví dụ nếu một container xử lý ổn định **75 yêu cầu/giây** ở điều kiện thử nghiệm và target hiệu suất trên mỗi instance là **60%** mức đã đo, sức chứa dự kiến khoảng **45 yêu cầu/giây/container**. Để đáp ứng 300 yêu cầu/giây cần xấp xỉ **7 container** ở điều kiện bình thường, trước khi tính chênh lệch tải, phân phối AZ, hệ số dự phòng và giới hạn database. Đây chỉ là **ước lượng năng lực**; phải kiểm thử ở tải thật với lỗi một AZ để xác nhận.

Tăng instance làm tăng số kết nối DB. Nếu mỗi instance mở tối đa 100 kết nối, tám instance có thể đòi tới 800 kết nối đồng thời, vượt hạn mức của DB. Phải thiết kế pool, giới hạn scale, mô hình truy vấn và backpressure theo toàn tuyến.

## 6. Bước 3: xây dựng sơ đồ luồng dữ liệu (DFD)

Sơ đồ luồng dữ liệu trả lời “**dữ liệu gì đi qua ai, biến đổi thế nào và tồn tại ở đâu?**”. Trong DFD, một dòng có nhãn **dữ liệu** (ví dụ “mã đơn + trạng thái thanh toán”), không chỉ có nhãn “REST”. Cổng mạng, AZ hoặc tên loại máy thường không phải đối tượng chính của DFD.

### 6.1. Phân biệt DFD mức 0 và mức 1

- **DFD mức 0 (context-level DFD):** hệ thống là một tiến trình tổng thể, bao quanh bởi tác nhân và các luồng dữ liệu ra/vào. Trông gần giống sơ đồ bối cảnh, nhưng nhãn cạnh nhấn mạnh dữ liệu trao đổi.
- **DFD mức 1:** phân rã hệ thống thành một số tiến trình nghiệp vụ chính (P1, P2, P3...), kho dữ liệu (D1, D2...) và luồng giữa chúng. Phân rã thêm mức 2 nếu một tiến trình phức tạp cần kiểm tra chi tiết.

Đối với bài thực hành này, sơ đồ bối cảnh ở mục 4 đóng vai trò góc nhìn hệ thống; **DFD mức 1** dưới đây cung cấp chiều sâu về dữ liệu.

### 6.2. Lập danh mục dữ liệu và phân loại

| Dữ liệu | Nguồn/đích chính | Phân loại mẫu | Quy tắc xử lý |
|---|---|---|---|
| Mã đơn, danh sách hàng, tổng tiền | Khách → MâyShop Order → DB đơn hàng | Nghiệp vụ; có thể gắn định danh khách | Kiểm tra hợp lệ, truy cập theo chủ sở hữu, lưu theo chính sách |
| Thông tin khách nhận hàng | Khách → MâyShop Order | Dữ liệu cá nhân | Mã hóa khi truyền/lưu, hạn chế log và quyền đọc |
| Mã tham chiếu giao dịch, trạng thái thanh toán | Cổng thanh toán ↔ MâyShop Order | Nhạy cảm nghiệp vụ | Xác minh nguồn webhook, kiểm tra số tiền/đơn, idempotency |
| Số lượng giữ chỗ và mã SKU | MâyShop Order ↔ ERP | Dữ liệu vận hành | Kiểm soát thời hạn giữ chỗ và giải phóng khi hủy |
| Sự kiện “đơn đã thanh toán” | DB/outbox → queue → worker | Nghiệp vụ | Chấp nhận khả năng nhận trùng, có khóa idempotency |
| Email và nội dung xác nhận | MâyShop Order → nhà cung cấp email | Có dữ liệu cá nhân | Gửi tối thiểu cần thiết, không đưa token nội bộ vào nội dung |
| Log/trace | Các workload → observability | Metadata; có thể lộ thông tin nhạy cảm nếu ghi sai | Che PII/secret, giới hạn truy cập và thời gian lưu |

**Không thu thập dữ liệu thẻ thanh toán đầy đủ** khi chức năng có thể giao cho đối tác xử lý qua giao diện/tokenization phù hợp. Giảm dữ liệu đi qua hệ thống là một quyết định kiến trúc bảo mật và tuân thủ; cần kiểm tra cơ chế thanh toán, phạm vi trách nhiệm và các yêu cầu áp dụng của doanh nghiệp.

### 6.3. DFD mức 1 cho hành trình tạo đơn và gửi email

~~~mermaid
flowchart LR
    C["Khách hàng\nExternal entity"]
    P["Cổng thanh toán\nExternal entity"]
    ERP["ERP tồn kho\nExternal entity"]
    Mail["Nhà cung cấp email\nExternal entity"]
    subgraph Sys["MâyShop Order - vùng dữ liệu ứng dụng"]
        A["P1 - Tiếp nhận đơn\nvà tạo phiên thanh toán"]
        B["P2 - Kiểm chứng webhook\nvà cập nhật trạng thái"]
        D[("D1 - Order DB\nđơn hàng + outbox")]
        X["P3 - Chuyển sự kiện\noutbox sang queue"]
        Q[("D2 - Queue / DLQ\nsự kiện")]
        W["P4 - Gửi email\nvà ghi nhận kết quả"]
    end
    C -->|"Giỏ hàng, địa chỉ nhận, yêu cầu đặt"| A
    A -->|"Mã đơn, trạng thái chờ thanh toán"| C
    A <-->|"SKU, yêu cầu kiểm tra/giữ chỗ"| ERP
    A -->|"Mã đơn, số tiền, yêu cầu phiên"| P
    P -->|"Tham chiếu phiên thanh toán"| A
    P -->|"Webhook: mã giao dịch, trạng thái"| B
    A -->|"Ghi đơn PENDING và tham chiếu"| D
    B <-->|"Đối chiếu đơn, cập nhật PAID một lần"| D
    D -->|"Bản ghi outbox chưa phát"| X
    X -->|"Sự kiện đơn đã thanh toán"| Q
    Q -->|"Thông điệp cần xử lý / retry"| W
    W -->|"Mã đơn, địa chỉ, nội dung thư"| Mail
    W -->|"Trạng thái gửi / idempotency"| D
~~~

**Cách đọc:**

- P1 tạo đơn ở trạng thái chờ, trao đổi tồn kho và yêu cầu phiên thanh toán. Thứ tự giữ chỗ, thời gian hết hạn và xử lý lỗi giữa ERP/DB/cổng thanh toán cần được thiết kế rõ trong luồng thực thi.
- P2 xử lý kết quả bất đồng bộ từ cổng thanh toán; kiểm tra chữ ký, thời hạn, mã giao dịch, số tiền và trạng thái hợp lệ trước khi cập nhật. **Không tin** một đường redirect từ trình duyệt là bằng chứng đã nhận tiền.
- D1 lưu đơn và **bản ghi outbox** để khi DB chuyển trạng thái thành công, sự kiện cần gửi không bị bỏ quên do quy trình phát queue bị lỗi giữa chừng. Mô hình transactional outbox cần một giao dịch DB thích hợp và cơ chế phát lại/đánh dấu sự kiện.
- P3 đưa bản ghi outbox lên queue. Nếu publish và đánh dấu đã phát không là một thao tác nguyên tử, sự kiện có thể bị phát lặp; consumer phải idempotent.
- P4 nhận thông điệp và gửi email; retry có giới hạn, DLQ giữ tác vụ lỗi cần xử lý. Bản thân email có thể đã được nhà cung cấp nhận rồi nhưng worker mất phản hồi; cần chọn idempotency/deduplication theo khả năng nhà cung cấp và yêu cầu nghiệp vụ.

Đây là **mô hình logic dữ liệu**, không phải định nghĩa quy trình thanh toán hoàn chỉnh. Ở hệ thật có thể phải thêm tác vụ đối soát nhà cung cấp, xử lý hoàn tiền, hủy giữ chỗ, thay đổi giỏ hàng và gửi email sau khi nhận xác nhận từ hệ email.

### 6.4. Dòng dữ liệu liên quan đến bảo mật

Đối với từng mũi tên trong DFD, lập hồ sơ:

| Mũi tên | Dữ liệu nhạy cảm? | Ranh giới tin cậy | Kiểm soát cần chứng minh |
|---|---|---|---|
| Khách → P1 | Có thể chứa PII | Internet → ứng dụng | TLS, xác thực khi cần, validation, quyền truy cập đơn |
| P1 ↔ ERP | SKU, lượng giữ chỗ, mã đơn | Ứng dụng → hệ thống doanh nghiệp khác | Danh tính dịch vụ, timeout, retry có giới hạn, chống giữ chỗ lặp |
| P1 → Cổng thanh toán | Số tiền, mã đơn, metadata tối thiểu | Ứng dụng → nhà cung cấp | Bảo vệ credential, đối chiếu dữ liệu và điều kiện hợp đồng |
| Cổng thanh toán → P2 | Kết quả giao dịch | Nhà cung cấp → ingress công khai | Xác thực chữ ký/nguồn theo giao thức, chống replay, idempotency |
| P2 → D1 | Trạng thái đơn và giao dịch | Workload → dữ liệu bền vững | Phân quyền ghi, transaction, ràng buộc duy nhất, audit |
| D1 → P3 → D2 | Sự kiện đã thanh toán | DB/outbox → broker | Quyền publish giới hạn, xử lý trùng, bảo vệ thông tin cá nhân |
| D2 → P4 → email | Địa chỉ, nội dung xác nhận | Workload → nhà cung cấp email | Quyền consumer, che thông tin, chính sách lưu giữ và trạng thái gửi |

**Điểm đặc biệt:** URL webhook của đối tác thường phải công khai để đối tác gọi tới. Quyết định công khai này cần được vẽ ở sơ đồ triển khai và đánh dấu đi qua trust boundary trong DFD. Đường công khai **có mục đích** khác với mở public DB hoặc endpoint quản trị.

### 6.5. Tình huống lỗi làm DFD có giá trị hơn

Xét ba tình huống:

**Webhook được gửi hai lần:** Nếu P2 cập nhật trạng thái bằng một giao dịch có điều kiện (ví dụ chỉ cho phép chuyển PENDING → PAID một lần) và ghi outbox cùng transaction, lần gọi thứ hai có thể được trả lời an toàn mà không tạo tác động trùng. Hệ vẫn phải kiểm tra bản ghi giao dịch của đối tác và xử lý webhook khác trạng thái.

**DB cập nhật thành công nhưng broker không nhận sự kiện:** Nếu API publish trực tiếp sau khi commit DB, sự cố nằm giữa hai thao tác có thể khiến email không bao giờ được gửi. Outbox cho phép tiến trình P3 quét và phát lại những bản ghi chưa được xác nhận. Đổi lại phải vận hành thêm publisher, cơ chế retry, dọn outbox và quan sát backlog.

**Nhà cung cấp email báo timeout:** Worker không biết đối tác đã nhận yêu cầu hay chưa. Retry mù có thể gửi email hai lần. Cần idempotency key được đối tác hỗ trợ, hoặc cơ chế giảm trùng/kiểm tra trạng thái phù hợp; nếu không thể đảm bảo, tài liệu thiết kế phải ghi rõ ngữ nghĩa “at-least-once” và khả năng gửi trùng.

DFD giúp thấy nơi dữ liệu sinh ra và nơi giữ trạng thái. **Sequence diagram** có thể được bổ sung để minh họa thứ tự gọi, timeout và retry, nhưng nó không thay thế DFD khi cần xem tổng thể nơi lưu dữ liệu và các ranh giới tin cậy.

## 7. Bước 4: đối chiếu ba sơ đồ

Sau khi vẽ, dành một vòng kiểm tra **cross-view consistency**. Nếu sơ đồ bối cảnh có đối tác email nhưng sơ đồ triển khai không có egress đến email, kiến trúc đang thiếu đường kết nối. Nếu DFD có kho Order DB nhưng sơ đồ triển khai không có vị trí lưu trữ và chính sách sao lưu tương ứng, thiết kế chưa đủ thông tin để hiện thực.

### 7.1. Bảng truy vết từ yêu cầu đến thành phần và bằng chứng

| Yêu cầu | Sơ đồ bối cảnh | Sơ đồ triển khai | DFD | Phép thử/chứng cứ |
|---|---|---|---|---|
| BR-01 tạo đơn | Khách ↔ MâyShop Order | Ingress → API → DB | Khách → P1 → D1 | E2E tạo đơn, mã đơn duy nhất, đúng tổng tiền |
| BR-02, BR-03 thanh toán | Cổng thanh toán ↔ MâyShop Order | API ra cổng thanh toán; webhook qua ingress | P1 ↔ PSP, PSP → P2 → D1 | Kiểm tra chữ ký, webhook lặp, trạng thái sai và retry |
| BR-04 tồn kho | ERP ↔ MâyShop Order | Kết nối API ↔ ERP | P1 ↔ ERP | Giữ chỗ, hết hạn, lỗi đối tác, nhất quán số lượng |
| BR-05 email | MâyShop Order → email provider | Queue → worker → egress → email | D1 → P3 → D2 → P4 → email | Gửi thành công, retry, DLQ, xử lý trùng |
| NFR-02 hiệu năng | Hành trình khách hàng | Load balancer, API scale, DB, phụ thuộc ngoài | Đường nóng P1 và đường nền P4 | Load test p95 và quan sát saturation |
| NFR-04 chịu lỗi AZ | Chất lượng dịch vụ của hệ thống | API/worker đa AZ, DB HA, LB | Kiểm tra luồng khi thành phần lỗi | Diễn tập mất một AZ, kiểm tra dữ liệu và thời gian phục hồi |
| NFR-06 dữ liệu nhạy cảm | Đối tác và ranh giới trách nhiệm | IAM, TLS, DB riêng, secret, audit | PII/credential qua các tiến trình và store | Authorization test, secret scan, log review |
| NFR-07 chi phí | Phạm vi dịch vụ và phụ thuộc | Compute, DB, queue, egress, logs, backup | Tần suất/khối lượng event, retention | Tagging, báo cáo chi phí và chi phí/đơn |

**Một nguyên tắc kiểm tra hữu ích:** mỗi thành phần trong sơ đồ triển khai phải phục vụ ít nhất một yêu cầu hoặc kiểm soát rõ ràng; mỗi luồng dữ liệu nhạy cảm trong DFD phải có đường triển khai và cơ chế bảo vệ tương ứng; mỗi đối tác trên sơ đồ bối cảnh phải xuất hiện ở một đường tích hợp được thiết kế.

### 7.2. Kiểm tra theo một hành trình cụ thể

Hãy dùng hành trình **“đặt hàng thành công”** để đọc liền ba sơ đồ:

1. **Bối cảnh:** Khách đặt hàng qua MâyShop Order; hệ thống dùng ERP và cổng thanh toán rồi gửi email.
2. **Triển khai:** Yêu cầu HTTPS vào ingress, phân phối tới API một trong hai AZ; API gọi DB/ERP/PSP; webhook từ PSP vào ingress; worker tiêu thụ queue và gọi nhà cung cấp email.
3. **Dữ liệu:** P1 tạo đơn PENDING; P2 kiểm chứng thanh toán và cập nhật PAID; outbox phát sự kiện; P4 gửi thư và ghi trạng thái.
4. **Kiểm chứng:** Thử request trùng, webhook trễ, DB failover, queue backlog, mất một AZ và lỗi đối tác. Đọc metric, trace và log có correlation ID xuyên các bước.

Nếu một bước của hành trình **không tìm được trên ít nhất một sơ đồ mà nó đáng lẽ phải xuất hiện**, đó là dấu hiệu cần làm rõ. Ví dụ sơ đồ không thể hiện đường webhook vào ứng dụng thì nhóm mạng rất dễ bỏ sót route có xác thực hoặc mở nhầm cổng.

## 8. Đánh giá kiến trúc theo Well-Architected ngay trên sơ đồ

Well-Architected là cách hỏi về hậu quả của quyết định kiến trúc, không phải bộ biểu tượng để trang trí. Trong nhiều khung đánh giá đám mây có các trụ cột về vận hành, bảo mật, độ tin cậy, hiệu năng, chi phí và bền vững; tên gọi hoặc chi tiết có thể khác theo nền tảng.

| Góc nhìn | Câu hỏi để phản biện ba sơ đồ | Ví dụ hành động |
|---|---|---|
| **Vận hành xuất sắc** | Đã vẽ luồng phát hiện, theo dõi và khôi phục sự cố chưa? Ai sở hữu mỗi phụ thuộc? | Thêm observability, runbook, chủ sở hữu và kiểm thử cảnh báo |
| **Bảo mật** | Dữ liệu đi qua ranh giới nào? Workload nào đọc được DB, queue, secret? | Tách IAM theo workload, ingress riêng cho webhook, che PII trong log |
| **Độ tin cậy** | Mất một AZ, DB hoặc PSP làm hành trình nào ngừng? Có queue, retry, idempotency và DR không? | Đo failover, backlog, RTO/RPO và hoàn tác giao dịch |
| **Hiệu quả hiệu năng** | API có chờ ERP/PSP đồng bộ trên đường nóng không? Nút thắt ở DB hoặc connection pool? | Trace, caching có giới hạn, timeout và scale đúng tầng |
| **Tối ưu chi phí** | Đa AZ, DB HA, NAT, log, cross-AZ traffic và dữ liệu lưu bao nhiêu? | Phân bổ chi phí, chọn mức dự phòng theo SLO và cost per successful order |
| **Bền vững** | Có tài nguyên nhàn rỗi, lưu trữ dư thừa, log giữ quá lâu hoặc xử lý lặp không? | Điều chỉnh quy mô, chính sách retention, giảm xử lý không cần thiết |

### 8.1. Một số đánh đổi không có đáp án tuyệt đối

**Xử lý thanh toán đồng bộ hay bất đồng bộ?** Đường đồng bộ giúp ứng dụng trả lời nhanh về việc tạo phiên nhưng sẽ dễ phụ thuộc vào độ trễ đối tác; xử lý webhook bất đồng bộ giúp xác nhận trạng thái dựa trên tín hiệu tin cậy hơn nhưng cần idempotency và xử lý eventual consistency. Thường có thể kết hợp cả hai: tạo phiên đồng bộ, xác nhận trạng thái qua webhook/đối soát.

**Dùng queue hay gọi thẳng email trong API?** Queue giảm phụ thuộc thời gian phản hồi của nhà cung cấp email, cho phép retry và kiểm soát tốc độ; đổi lại thêm broker, worker, trạng thái message, backlog, DLQ và chi phí vận hành.

**Một vùng hay nhiều vùng?** Đa AZ là bước thường gặp để giảm lỗi cục bộ; DR sang region khác giúp xử lý thêm lớp sự cố nhưng phát sinh chi phí, replication, quản trị chuyển lưu lượng và rủi ro sai lệch dữ liệu. Chọn theo yêu cầu RTO/RPO và kết quả diễn tập, không theo mong muốn “càng nhiều vùng càng tốt”.

**DB dùng chung hay tách theo dịch vụ?** DB dùng chung giảm công việc ban đầu nhưng tạo liên kết giữa các nhóm, khó phân quyền và scale độc lập. Tách database giúp cô lập ranh giới dữ liệu nhưng thêm việc đồng bộ và đảm bảo nhất quán liên dịch vụ. Một hệ thống vừa bắt đầu không nhất thiết phải tách thành nhiều microservice.

**Đưa mọi dịch vụ vào private subnet?** Truy cập từ Internet vẫn cần ingress công khai dành cho khách và webhook. Cấu hình riêng tư phù hợp cho DB, worker và giao diện quản trị; nhưng bảo vệ còn cần IAM, xác thực, phân quyền và kiểm soát egress.

### 8.2. Ghi quyết định thiết kế (ADR) ngắn

Sau buổi review, ghi lại ít nhất hai quyết định lớn thay vì để “hình vẽ nói hộ”:

~~~text
ADR-01: Tách gửi email khỏi đường tạo đơn
Bối cảnh: API tạo đơn cần p95 <= 400 ms trong tải mục tiêu.
Quyết định: Ghi sự kiện qua outbox rồi đưa sang managed queue;
             worker riêng gửi email, hỗ trợ retry và DLQ.
Đánh đổi: Tăng chi phí/độ phức tạp vận hành; email không tức thời.
Bằng chứng cần có: Load test, đo backlog, thử publish lỗi,
                   kiểm chứng idempotency và trạng thái gửi.
Chủ sở hữu / ngày xem lại: ...

ADR-02: API và worker chạy ở ít nhất hai AZ
Bối cảnh: Yêu cầu giữ hệ thống hoạt động khi một AZ lỗi.
Quyết định: Phân bố workload và chọn DB HA phù hợp.
Đánh đổi: Tăng chi phí dự phòng; cần kiểm tra phân bố và failover.
Bằng chứng cần có: Thử mất AZ, thông lượng còn lại, lỗi giao dịch,
                   kết quả RTO/RPO của kịch bản đã định.
Chủ sở hữu / ngày xem lại: ...
~~~

## 9. Quy trình làm bài thực hành có thể lặp lại

### Pha A: thu thập và khóa giả định

Tạo một trang ghi phạm vi, hành trình chính, loại dữ liệu, stakeholder, ba đến năm SLO/NFR quan trọng và những thông tin chưa biết. Gắn nhãn cho giả định chưa được xác minh, ví dụ “ERP cho phép 100 yêu cầu/giây” hoặc “cổng thanh toán có webhook được ký”; đừng biến giả định thành sự thật khi vẽ.

### Pha B: vẽ bối cảnh và xác nhận trách nhiệm

Mở đầu bằng một hệ thống trung tâm và các tác nhân trực tiếp. Kiểm tra với chủ sản phẩm rằng những kết nối đã phản ánh nghiệp vụ. Nếu thay đổi ranh giới hệ thống, cập nhật lại danh mục chủ sở hữu và NFR chịu ảnh hưởng.

### Pha C: phác thảo triển khai

Chọn mô hình compute, nơi lưu dữ liệu và lớp ingress dựa trên nhu cầu. Thêm đường mạng, AZ, dịch vụ ngoài, bảo mật, observability và DR. Mọi kết nối cần giải thích cách đi qua network rule, danh tính và bảo vệ dữ liệu. Phân biệt mô hình thiết kế với sản phẩm/region cụ thể sau khi đã chọn nhà cung cấp.

### Pha D: vẽ DFD từ hành trình nghiệp vụ

Chọn đường đi quan trọng như tạo đơn và xác nhận thanh toán, chia thành tiến trình, dữ liệu đầu vào/đầu ra và nơi lưu. Đánh dấu thông tin nhạy cảm và ranh giới tin cậy. Điểm phát sinh tác vụ bất đồng bộ, thao tác không nguyên tử hoặc kiểm soát truy cập phức tạp cần được mô tả bằng ghi chú.

### Pha E: kiểm tra chéo và trình bày quyết định

Dùng bảng truy vết yêu cầu; hỏi kỹ sư hạ tầng chỉ ra nơi đặt từng tiến trình DFD, hỏi nhóm backend giải thích hành trình qua các dịch vụ triển khai, hỏi bảo mật nơi dữ liệu đi vào/ra và quyền hiệu lực. Ghi ADR, các điều chưa giải quyết, owner và kế hoạch kiểm thử.

### 9.1. Cấu trúc thư mục nộp bài gợi ý

Nếu cần quản lý tài liệu như mã nguồn, có thể tổ chức các bản vẽ ở repository kiến trúc của dự án như sau:

~~~text
architecture/
  README.md                   # phạm vi, phiên bản, bảng ký hiệu
  01-context.md               # sơ đồ bối cảnh + chú giải
  02-deployment.md            # sơ đồ triển khai + ma trận mạng
  03-data-flow.md             # DFD + danh mục dữ liệu
  requirements-traceability.md
  decisions/
    ADR-001-async-notification.md
    ADR-002-multi-az.md
~~~

Đây chỉ là **gợi ý trình bày bài nộp**, không phải chỉ thị tạo thêm tệp cho bài học hiện tại. Với phạm vi bài tập, một tài liệu Markdown chứa đủ ba sơ đồ và bảng quyết định cũng được.

## 10. Bài tập 1: tự hoàn thiện sơ đồ bối cảnh

**Tình huống:** MâyShop Order bổ sung tính năng khách tự yêu cầu hoàn hàng. Doanh nghiệp dùng một hệ vận chuyển bên ngoài để tạo vận đơn trả hàng và một bộ phận chăm sóc khách duyệt yêu cầu trong hệ thống.

**Nhiệm vụ:**

1. Xác định hai tác nhân/hệ thống liên quan mới và phạm vi sở hữu của từng bên.
2. Mở rộng sơ đồ bối cảnh bằng đường dữ liệu nghiệp vụ “yêu cầu hoàn”, “kết quả xét duyệt”, “mã vận đơn trả hàng” và “trạng thái vận chuyển”.
3. Nêu ít nhất ba câu hỏi cần hỏi product owner trước khi chốt bối cảnh, chẳng hạn ai được phép yêu cầu hoàn, ai phê duyệt và hoàn tiền qua hệ nào.
4. Giải thích vì sao không đưa trực tiếp database vận chuyển vào ranh giới của MâyShop Order nếu DB do đối tác quản lý.

**Tiêu chí tự đánh giá:** Hệ thống ngoài phạm vi được ghi rõ; không lẫn vai trò người dùng với dịch vụ; mỗi đường kết nối có tên nghiệp vụ; những quyết định chưa rõ được ghi là câu hỏi hoặc giả định.

## 11. Bài tập 2: thử thay đổi yêu cầu triển khai

**Tình huống:** Trong đợt giảm giá, lưu lượng tăng gấp bốn lần so với bài mẫu. Nhóm vận hành ghi nhận API p95 tăng, DB đạt giới hạn kết nối và queue tồn thông điệp lâu. Ngoài ra, ngân sách không cho phép duy trì tất cả thành phần ở nhiều region.

**Nhiệm vụ:**

1. Tìm ít nhất ba điểm có khả năng nghẽn trong sơ đồ triển khai. Với mỗi điểm, nêu metric để xác nhận hoặc bác bỏ giả thuyết.
2. Đề xuất một cách scale API, một cách bảo vệ DB và một cách xử lý backlog worker, đồng thời nêu nguy cơ của mỗi thay đổi.
3. Vẽ lại hoặc chú thích sơ đồ để phân biệt HA nhiều AZ với DR mất region; nêu cách đáp ứng NFR-04 và kế hoạch kiểm chứng NFR-05.
4. Đánh dấu tài nguyên cần phân bổ chi phí: ingress, compute, database, queue, NAT/egress, log, backup.
5. Nêu trường hợp mà **thêm container** làm hệ thống tệ hơn và chứng minh bằng phép đo dự kiến.

**Gợi ý:** Sức chứa của một thành phần không thể đánh giá tách rời. Nếu tăng API lên gấp đôi nhưng DB connection pool nhân lên tương ứng và DB không tăng năng lực, p95 tổng thể có thể tệ hơn. Hãy cân nhắc giới hạn concurrency, pooling, tối ưu truy vấn, backpressure và giảm việc gọi đồng bộ không cần thiết.

## 12. Bài tập 3: vẽ lại DFD khi xuất hiện yêu cầu tuân thủ

**Tình huống:** Doanh nghiệp cần xóa hoặc ẩn thông tin liên hệ khách hàng theo quy tắc lưu giữ áp dụng, nhưng vẫn phải lưu chứng từ và dữ liệu giao dịch theo thời hạn nghiệp vụ/pháp lý khác. Nhà cung cấp email có thể giữ nội dung đã nhận trong một khoảng thời gian riêng.

**Nhiệm vụ:**

1. Phân loại dữ liệu theo danh mục ở mục 6.2 và xác định nơi lưu mỗi loại: DB đơn hàng, queue/DLQ, log, backup, nhà cung cấp email.
2. Thêm luồng “yêu cầu xóa/ẩn thông tin liên hệ” vào DFD, chỉ ra tiến trình kiểm tra quyền yêu cầu, xử lý dữ liệu và lưu bằng chứng.
3. Nêu trường hợp không được xóa ngay dữ liệu vì nghĩa vụ lưu trữ hợp lệ; phân biệt xóa, ẩn, pseudonymization và giới hạn truy cập.
4. Xác định dữ liệu trong DLQ, backup và hệ thống email cần xử lý hoặc có chính sách retention tương ứng ra sao.
5. Đề xuất ba phép thử về quyền, an toàn dữ liệu và quan sát; tránh dùng dữ liệu thật của khách trong báo cáo kiểm thử.

**Lưu ý:** Bài tập yêu cầu mô hình kỹ thuật để phục vụ yêu cầu pháp lý đã được doanh nghiệp xác định; chính sách lưu và xóa thực tế phải do người có trách nhiệm tuân thủ xác nhận theo khu vực pháp lý và hợp đồng cụ thể.

## 13. Bài tập tổng hợp: bảo vệ thiết kế trong buổi review

Giả sử bạn là kiến trúc sư cần trình bày phương án triển khai MâyShop Order trước product owner, SRE, security engineer và finance. Hãy chuẩn bị **một bộ ba sơ đồ hoàn chỉnh** và bản ghi quyết định ngắn. Bản nộp tối thiểu gồm:

1. **Sơ đồ bối cảnh:** Một hệ thống chính, hai loại người dùng, ba hệ ngoài; nhãn tương tác và ranh giới trách nhiệm.
2. **Sơ đồ triển khai:** Ingress, API, worker, DB, queue, các AZ, đường mạng chính, danh tính, secret, observability và DR; có chú giải đường công khai/riêng.
3. **DFD mức 1:** Các tiến trình tạo đơn, xác minh thanh toán, phát sự kiện, gửi email; kho dữ liệu, luồng có tên và ranh giới tin cậy.
4. **Bảng truy vết:** Ít nhất sáu yêu cầu BR/NFR đi qua các khối/luồng và phép kiểm.
5. **Hai ADR:** Một quyết định về độ tin cậy và một về xử lý dữ liệu hoặc bảo mật; mỗi ADR có đánh đổi, metric và điều kiện xem lại.
6. **Ba kịch bản sự cố:** Mất một AZ, cổng thanh toán gửi webhook lặp và email provider ngừng trả lời; chỉ rõ luồng nào bị ảnh hưởng, chỉ số đo và cách phục hồi.

### 13.1. Câu hỏi người phản biện có thể đặt

**Product owner:** Khi khách nhìn thấy trang “thanh toán thành công” nhưng webhook chưa đến, hệ thống hiển thị trạng thái gì? Ai giải thích chênh lệch cho khách?

**SRE:** Nếu một AZ mất giữa giờ cao điểm, lưu lượng tăng vào AZ còn lại có vượt năng lực DB hoặc API không? Có bằng chứng thử nghiệm không?

**Security:** Vì sao webhook phải public? Cơ chế xác thực nào ngăn bên ngoài giả mạo kết quả thanh toán, và audit lưu ở đâu?

**Data engineer:** Nếu outbox publish lặp hoặc queue gửi lại sự kiện, trạng thái đơn và email có bị ghi/ gửi trùng không?

**Finance:** Tại sao dùng DB HA và worker dự phòng? Chi phí của phương án này so với mức tổn thất doanh nghiệp chấp nhận là bao nhiêu?

**Architect:** Từ một node ở sơ đồ triển khai, có thể truy ngược về yêu cầu nào và từ một dữ liệu nhạy cảm, có thể thấy đầy đủ các nơi nó đi tới không?

### 13.2. Thang chấm bài gợi ý

| Tiêu chí | Điểm tối đa | Dấu hiệu đạt |
|---|---:|---|
| Đúng phạm vi và ranh giới hệ thống | 15 | Không lẫn hệ ngoài và các module nội bộ |
| Sơ đồ bối cảnh đúng tác nhân/quan hệ | 15 | Đủ đường tương tác nghiệp vụ, tên nhất quán |
| Triển khai hợp lý về mạng, compute, dữ liệu | 20 | Nêu AZ, ingress, private workload, phụ thuộc, HA/DR và ma trận kết nối |
| DFD đủ luồng quan trọng, kho dữ liệu và lỗi | 20 | Xử lý callback, queue, dữ liệu nhạy cảm, idempotency |
| Truy vết ba góc nhìn và thiết kế phép thử | 15 | Yêu cầu → thành phần → dữ liệu → bằng chứng rõ |
| Giải thích đánh đổi Well-Architected | 10 | Đề cập độ tin cậy, bảo mật, chi phí, hiệu năng, vận hành |
| Trình bày và giả định | 5 | Dễ đọc, chú giải đủ, không coi giả định là kết luận |
| **Tổng** | **100** | |

Một bài vẽ đẹp nhưng thiếu cơ chế xử lý thanh toán lặp, quên ranh giới dữ liệu hoặc khẳng định sai về failover chưa thể xem là thiết kế sẵn sàng triển khai. Ngược lại, một bài dùng ký hiệu đơn giản vẫn có thể tốt khi ranh giới, trách nhiệm, luồng và quyết định được thể hiện rõ.

## 14. Các lỗi thường gặp khi xây dựng ba sơ đồ

| Lỗi | Hệ quả | Cách sửa |
|---|---|---|
| Vẽ luôn VM, DB và subnet trong sơ đồ bối cảnh | Người nghiệp vụ không thấy ranh giới trách nhiệm | Giữ một hộp hệ thống chính; chuyển chi tiết vào deployment |
| Sơ đồ deployment chỉ ghi tên dịch vụ, không có đường kết nối | Không biết ingress, egress, nguồn/đích và cơ chế bảo vệ | Bổ sung mũi tên, giao thức, ranh giới và ma trận kết nối |
| Ghi nhãn “API” cho mọi mũi tên trong DFD | Không thấy dữ liệu nào rời hệ thống | Đặt tên payload hoặc thông tin: mã đơn, trạng thái, email |
| Đồng nhất private subnet với bảo mật toàn diện | Bỏ sót quyền truy cập và rủi ro từ ứng dụng nội bộ | Thêm IAM, authorization, secret và kiểm thử quyền |
| Chỉ thể hiện happy path | Không phát hiện tác động retry, timeout và sự cố | Vẽ/ghi chú callback lặp, queue lỗi, DB failover, DR |
| Thể hiện nhiều AZ nhưng quên DB/queue hoặc capacity | Tưởng đã có HA dù phụ thuộc còn điểm lỗi đơn | Kiểm tra mọi thành phần và thử mất AZ |
| Đặt backup trong hình rồi tuyên bố đạt RTO/RPO | Thiếu bằng chứng restore thực tế | Thiết kế kịch bản, đo và diễn tập phục hồi |
| Không nêu đơn vị đo hoặc giả định tải | Không thể đánh giá lựa chọn compute/chi phí | Ghi profile tải, p95, SLO, thời gian, vùng và nguồn số liệu |
| Tên cùng một đối tác thay đổi qua sơ đồ | Khó review và có thể bỏ sót luồng | Dùng danh mục tên và bảng truy vết |
| Sơ đồ không được cập nhật sau khi triển khai | Hướng dẫn vận hành hoặc review bảo mật trở nên sai | Lưu diagram-as-code với version, owner và quy trình review |

## 15. Mẫu checklist trước khi nộp sơ đồ

### Trước khi vẽ

- [ ] Đã thống nhất mục tiêu nghiệp vụ, phạm vi hệ thống và chủ sở hữu.
- [ ] Đã ghi rõ yêu cầu phi chức năng, giả định và điểm còn chưa xác nhận.
- [ ] Đã xác định dữ liệu nhạy cảm, đối tác và ranh giới trách nhiệm.

### Sơ đồ bối cảnh

- [ ] Có đúng hệ thống trung tâm và các tác nhân/hệ thống ngoài cần thiết.
- [ ] Tên và nhãn đường nối là hoạt động nghiệp vụ mà người đọc hiểu được.
- [ ] Không nhồi công nghệ triển khai không cần thiết.

### Sơ đồ triển khai

- [ ] Có nơi đặt compute, lưu trữ, ingress, queue và phụ thuộc quan trọng.
- [ ] Có phân vùng mạng/vùng lỗi và chỉ ra public/private rõ ràng.
- [ ] Có IAM/secret, telemetry, backup/DR ở mức phù hợp với NFR.
- [ ] Có ma trận kết nối và phương án đo hiệu năng, HA, chi phí.

### Sơ đồ luồng dữ liệu

- [ ] Tên tiến trình bắt đầu bằng hành động xử lý, kho dữ liệu và tác nhân được phân biệt rõ.
- [ ] Mũi tên có tên dữ liệu và bên gửi/nhận; không che mất ranh giới tin cậy.
- [ ] Luồng callback, retry, idempotency, lỗi và dữ liệu nhạy cảm được phân tích.
- [ ] Đã xem xét nơi lưu tạm, log, DLQ, backup và bên thứ ba.

### Kiểm tra chéo và vận hành

- [ ] Một hành trình nghiệp vụ quan trọng truy vết được qua cả ba sơ đồ.
- [ ] Không có thành phần hoặc kết nối quan trọng “vô chủ” hay chỉ xuất hiện ở một hình.
- [ ] Quyết định chính có lý do, đánh đổi, chủ sở hữu và kiểm chứng.
- [ ] Sơ đồ có ngày cập nhật, phiên bản và quy trình sửa khi kiến trúc thay đổi.

## 16. Ghi nhớ

Thiết kế kiến trúc đám mây bắt đầu từ **nghiệp vụ và ràng buộc**, tiếp theo mới là lựa chọn mạng, compute, cơ sở dữ liệu và cách triển khai. Sơ đồ bối cảnh giúp trả lời **“ai và hệ thống nào liên quan?”**; sơ đồ triển khai trả lời **“các thành phần chạy và kết nối ở đâu?”**; DFD trả lời **“dữ liệu được xử lý, lưu trữ và trao đổi thế nào?”**.

Một bộ sơ đồ hữu ích phải nhất quán, đủ dễ đọc để cùng review và đủ chính xác để dẫn đến phép kiểm thực tế. Thước đo chất lượng là người đọc có thể **truy ngược từ yêu cầu đến quyết định thiết kế**, nhận diện rủi ro và hiểu đánh đổi Well-Architected, chứ không phải số lượng biểu tượng dịch vụ đám mây được đặt trong hình.

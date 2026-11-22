# Đánh giá kiến trúc theo bảo mật, độ tin cậy, hiệu năng và chi phí

Một kiến trúc Oracle Cloud Infrastructure (OCI) chỉ được xem là phù hợp khi đáp ứng được yêu cầu của hệ thống bằng những bằng chứng có thể kiểm tra. Sơ đồ có nhiều dịch vụ, tài nguyên cấu hình lớn hoặc dự toán thấp đều chưa đủ để kết luận rằng hệ thống an toàn, vận hành ổn định và sử dụng ngân sách hợp lý.

Trong chương **Dự án tích hợp và đánh giá**, bài này hướng dẫn cách đánh giá sản phẩm capstone OCI theo bốn góc nhìn: **bảo mật, độ tin cậy, hiệu năng và chi phí**. Phạm vi bao gồm tenancy, compartment, IAM, VCN, Compute, lưu trữ, cơ sở dữ liệu Oracle, giám sát và tự động hóa. Kết quả đánh giá phải chỉ ra kiến trúc đáp ứng yêu cầu nào, thiếu bằng chứng gì, rủi ro còn lại thuộc về ai và điều kiện nào cần hoàn thành trước khi đưa vào vận hành.

Các số liệu về tải, thời gian, ngân sách và kết quả thử nghiệm trong bài là **giả định phục vụ học tập**, không phải số đo đã thực hiện hoặc bảng giá OCI. Khả năng triển khai phải được đối chiếu với region, dịch vụ, cấu hình và quyền sử dụng thực tế của dự án.

## 1. Mục tiêu và sản phẩm của một lần đánh giá

Sau bài học, người học cần có khả năng:

- Chuyển yêu cầu nghiệp vụ thành tiêu chí đánh giá có ngưỡng đạt rõ ràng.
- Kiểm tra kiến trúc bằng cả cấu hình triển khai, luồng truy cập và dữ liệu vận hành.
- Phân biệt thiết kế dự kiến với khả năng đã được thử nghiệm.
- Phát hiện sự đánh đổi giữa bảo mật, khả năng phục hồi, tốc độ xử lý và ngân sách.
- Chấm điểm có dẫn chứng nhưng vẫn giữ những điều kiện bắt buộc không thể bù bằng điểm.
- Lập danh sách khắc phục có người chịu trách nhiệm, hạn hoàn thành và cách kiểm chứng.

Một bộ kết quả tối thiểu gồm:

| Sản phẩm | Câu hỏi cần trả lời |
|---|---|
| Phạm vi và giả định | Đang đánh giá môi trường nào, phiên bản nào, loại sự cố nào? |
| Sơ đồ và danh mục tài nguyên | Tài nguyên thực tế nằm ở đâu, thuộc compartment nào, giao tiếp thế nào? |
| Ma trận yêu cầu và bằng chứng | Mỗi yêu cầu được chứng minh bằng cấu hình hoặc thử nghiệm nào? |
| Bảng điểm và điều kiện bắt buộc | Mức trưởng thành ra sao, có điều kiện nào ngăn nghiệm thu? |
| Danh sách phát hiện | Lỗ hổng hoặc giới hạn gây tác động gì, cần sửa theo thứ tự nào? |
| Quyết định và kế hoạch xác minh lại | Có thể vận hành trong phạm vi nào, còn ai phải làm gì? |

Đánh giá kiến trúc không dừng ở việc tìm lỗi. Nó giúp lựa chọn phương án vừa đáp ứng yêu cầu vừa có thể triển khai, giám sát, khôi phục và thanh toán lâu dài.

## 2. Chốt phạm vi trước khi xem cấu hình

### 2.1. Xác định đơn vị được đánh giá

Không nên đánh giá chung chung “toàn bộ OCI” nếu dự án chỉ triển khai một ứng dụng. Cần xác định:

- Tenancy và compartment liên quan; môi trường development, staging hay production.
- Region chính, region lưu bản sao nếu có và giới hạn sự cố được cam kết xử lý.
- Các dịch vụ nằm trong phạm vi: mạng, IAM, ứng dụng, cơ sở dữ liệu, lưu trữ, giám sát.
- Các phụ thuộc ngoài phạm vi quản trị nhưng ảnh hưởng đến kết quả: DNS, nhà cung cấp danh tính, kết nối doanh nghiệp hoặc API thanh toán.
- Phiên bản ứng dụng, phiên bản cấu hình hạ tầng và thời điểm thu thập bằng chứng.
- Những thay đổi chưa triển khai hoặc chưa thử nghiệm.

Một báo cáo chỉ đúng với trạng thái được đánh giá. Sau khi thay đổi lớn về IAM, topology mạng, cơ sở dữ liệu, quy mô tải hoặc chính sách lưu giữ, cần xác định phần nào của kết luận cũ đã mất hiệu lực.

### 2.2. Kịch bản xuyên suốt: cổng tiếp nhận đơn hàng

Giả sử nhóm xây dựng một cổng tiếp nhận đơn hàng trên OCI:

- Người dùng truy cập API qua HTTPS.
- OCI Load Balancer chuyển yêu cầu đến các Compute instance chạy ứng dụng trong private subnet.
- Ứng dụng ghi giao dịch vào một dịch vụ cơ sở dữ liệu Oracle đã được lựa chọn rõ ràng.
- Object Storage lưu tệp đính kèm; thiết kế cơ sở dữ liệu có cơ chế sao lưu riêng.
- IAM phân tách nhóm quản trị, nhóm triển khai, nhóm vận hành và người đánh giá.
- Monitoring, Logging, Audit và kênh thông báo cung cấp tín hiệu vận hành.

Yêu cầu ban đầu:

| Nhóm yêu cầu | Tiêu chí giả định |
|---|---|
| Bảo mật | Cơ sở dữ liệu và cổng quản trị ứng dụng không được truy cập trực tiếp từ Internet; tài khoản có quyền quản trị phải dùng MFA |
| Sẵn sàng | Tỷ lệ yêu cầu nghiệp vụ thành công đạt ít nhất 99,9% theo cửa sổ 30 ngày |
| Hiệu năng | Trong tải kiểm thử đã thống nhất, p95 thời gian đáp ứng API dưới 400 ms, tỷ lệ lỗi dưới 0,5% |
| Tải kiểm thử | 100 yêu cầu/giây trong 15 phút sau giai đoạn làm nóng; 90% đọc, 10% tạo đơn bằng dữ liệu tổng hợp |
| Sự cố thành phần | Khi mất một Compute instance, hệ thống vẫn đạt ngưỡng tải và hiệu năng nêu trên sau thời gian phát hiện, loại backend lỗi đã thống nhất |
| Phục hồi dữ liệu | Với sự cố dữ liệu trong phạm vi cam kết: RTO không quá 30 phút, RPO không quá 5 phút |
| Sự cố toàn region | Nếu cam kết phục hồi thảm họa theo bản sao ngoài region: RTO không quá 24 giờ, RPO không quá 24 giờ |
| Ngân sách | Chi phí dự kiến trước thuế không quá 1.200 USD/tháng, theo quy tắc dự phòng biến động đã được phê duyệt |
| Đơn vị nghiệp vụ | Khoảng 100.000 đơn được tạo thành công mỗi tháng dùng làm cơ sở phân bổ chi phí |

Cần ghi rõ “sự cố dữ liệu trong phạm vi cam kết” gồm những trường hợp nào, chẳng hạn lỗi thao tác cần khôi phục đến một thời điểm. Không được dùng mục tiêu của sự cố thành phần để ngầm cam kết xử lý cả mất region.

Hồ sơ cũng phải mô tả cách tính độ trễ: ví dụ từ lúc máy phát tải gửi yêu cầu đến khi nhận đầy đủ phản hồi, từ một vị trí mạng xác định. Nếu đo từ bên ngoài OCI, kết quả có cả ảnh hưởng của đường truyền đến OCI. Số liệu này không thể so sánh trực tiếp với thời gian xử lý bên trong ứng dụng.

### 2.3. Định nghĩa SLI, SLO, RTO và RPO

**SLI** là đại lượng đo. **SLO** là mục tiêu đặt trên đại lượng đó. **RTO** là thời gian khôi phục tối đa được chấp nhận cho một kịch bản; **RPO** là lượng dữ liệu có thể mất, biểu diễn bằng khoảng thời gian.

Ví dụ SLI cho API tạo đơn:

~~~text
Tỷ lệ thành công =
    Số yêu cầu hợp lệ hoàn tất đúng nghiệp vụ
    / Tổng số yêu cầu hợp lệ được xét
~~~

Quy tắc phân loại phải được thống nhất trước khi đo:

- Tính lỗi máy chủ, timeout và lỗi kết nối làm thất bại.
- Một phản hồi HTTP 200 nhưng không ghi được đơn đúng yêu cầu vẫn là thất bại nghiệp vụ.
- Phản hồi từ chối yêu cầu sai đầu vào có thể được loại khỏi mẫu nếu quy tắc đã được công bố.
- Yêu cầu hợp lệ bị từ chối do hệ thống quá tải, kể cả một số phản hồi 429, không được tùy tiện loại để làm đẹp tỷ lệ.
- Lưu lượng dò quét, health check và yêu cầu của máy phát tải cần có quy tắc phân tách rõ.

Nếu SLO được định nghĩa theo thời gian và cửa sổ là 30 ngày:

~~~text
Tổng thời gian = 30 × 24 × 60 = 43.200 phút
Ngân sách gián đoạn tại mức 99,9% = 43.200 × 0,001 = 43,2 phút
~~~

Đây là phép tính cho SLO theo thời gian. Với SLO theo số yêu cầu, phải tính ngân sách lỗi bằng số yêu cầu; hai cách tính không đồng nhất khi lưu lượng thay đổi. Cũng không dùng SLA của một dịch vụ hạ tầng để thay thế SLO của toàn bộ ứng dụng.

## 3. Đọc kiến trúc theo luồng và ranh giới tin cậy

### 3.1. Sơ đồ cần thể hiện điều gì?

Sơ đồ kiến trúc tối thiểu nên chỉ ra:

- Điểm vào công khai và nơi kết thúc TLS.
- Public subnet, private subnet, route table, Internet Gateway, NAT Gateway hoặc Service Gateway được sử dụng.
- Network Security Group (NSG) và nhóm luồng được phép.
- Vị trí Compute, cơ sở dữ liệu, Object Storage và các phụ thuộc.
- Ranh giới compartment, quyền quản trị và danh tính của workload.
- Availability Domain (AD), Fault Domain (FD) của các thành phần khi phù hợp.
- Đường đi của bản sao lưu, log, metric và cảnh báo.

~~~mermaid
flowchart TD
    U[Người dùng] -->|HTTPS| LB[Load Balancer công khai]
    LB -->|Luồng backend được giới hạn| APP[Compute ứng dụng trong private subnet]
    APP -->|Kết nối DB được bảo vệ| DB[Cơ sở dữ liệu Oracle]
    APP -->|Truy cập bằng danh tính workload| OBJ[Object Storage]
    APP -->|Gửi log và metric| OBS[Logging và Monitoring]
    DB -->|Tín hiệu vận hành| OBS
    OBS --> ALERT[Kênh cảnh báo và người trực]
    OP[Người vận hành được phân quyền] --> ACCESS[Kênh quản trị được kiểm soát]
    ACCESS --> APP
    DB --> BACKUP[Bản sao lưu và quy trình khôi phục]
~~~

Sơ đồ này mô tả các quan hệ logic. Nó chưa chứng minh số lượng instance, sự phân bố AD/FD, cấu hình gateway hay tính sẵn sàng của cơ sở dữ liệu. Những chi tiết đó phải có trong cấu hình triển khai và danh mục bằng chứng.

### 3.2. Đi theo ba luồng độc lập

**Luồng nghiệp vụ:** người dùng → Load Balancer → ứng dụng → cơ sở dữ liệu hoặc Object Storage. Luồng này cho biết dữ liệu đi đâu, điểm nghẽn ở đâu và lớp nào phải chịu tải.

**Luồng quản trị:** người triển khai hoặc pipeline → IAM → API điều khiển và kênh quản trị. Một hệ thống không có cổng SSH công khai vẫn có thể bị thay đổi toàn bộ nếu pipeline giữ thông tin xác thực quá rộng.

**Luồng phục hồi và quan sát:** tài nguyên → log, metric, cảnh báo, bản sao lưu → người trực hoặc quy trình khôi phục. Đường này quyết định nhóm có phát hiện được sự cố và khôi phục khi luồng nghiệp vụ đang hỏng hay không.

Không mặc định rằng kênh quan sát hoặc phục hồi còn hoạt động khi hệ thống chính gặp sự cố. Ví dụ, runbook chỉ lưu trong chính máy ứng dụng sẽ khó truy cập khi máy đó mất.

## 4. Đánh giá bảo mật: kiểm tra đường truy cập và quyền thực tế

### 4.1. Tenancy, compartment và IAM

Compartment hỗ trợ tổ chức tài nguyên và áp dụng quyền. Nó không tự tạo một vùng cách ly mạng. Một policy ở phạm vi cha hoặc tenancy có thể mở rộng quyền đối với tài nguyên trong các compartment con theo cách policy đó được định nghĩa.

Những câu hỏi cần kiểm tra:

1. Ai có thể thay đổi IAM policy, cấu hình mạng, secret, khóa mã hóa và tài nguyên production?
2. Quyền đến từ policy nào, đặt ở phạm vi nào?
3. Một người dùng hoặc workload có thừa quyền quản lý tài nguyên ngoài nhu cầu không?
4. Môi trường thử nghiệm có thể sửa tài nguyên production hay đọc dữ liệu production không?
5. Pipeline có quyền triển khai ứng dụng nhưng đồng thời có quyền tự mở rộng IAM không?
6. Có quy trình cấp quyền khẩn cấp, thu hồi và kiểm tra sau sử dụng không?

Bảng phân vai minh họa:

| Chủ thể | Nhu cầu hợp lệ | Dấu hiệu cần xem lại |
|---|---|---|
| Nhóm triển khai ứng dụng | Cập nhật tài nguyên ứng dụng trong phạm vi được giao | Có thể sửa mọi policy của tenancy |
| Nhóm vận hành | Xem tín hiệu, xử lý sự cố theo runbook | Mọi người dùng chung một tài khoản quản trị |
| Ứng dụng | Đọc secret cần thiết và truy cập bucket phục vụ nghiệp vụ | Dùng API key cá nhân có quyền quản trị |
| Người đánh giá | Đọc cấu hình và bằng chứng được phép | Phải nhận mật khẩu production để xem kiến trúc |
| Pipeline hạ tầng | Thay đổi tài nguyên trong phạm vi triển khai | Có thể tự cấp quyền không giới hạn cho chính nó |

MFA cho người dùng có quyền cao là một điều kiện quan trọng, nhưng không thay thế quản lý API key, token, credential của pipeline hoặc cơ chế xác thực workload.

Ưu tiên danh tính workload như instance principal hoặc resource principal khi dịch vụ và kiểu workload hỗ trợ. Đồng thời phải kiểm tra điều kiện xác định thành viên dynamic group và policy đi kèm: một dynamic group khớp quá rộng vẫn có thể cấp quyền ngoài dự kiến.

### 4.2. VCN, subnet và NSG

Đánh giá mạng cần phân biệt ba vấn đề:

- **Khả năng định tuyến:** gói tin có đường đi đến đích hay không.
- **Quy tắc cho phép:** NSG, security list và cơ chế lọc khác có cho phép luồng đó hay không.
- **Điểm kết thúc dịch vụ:** dịch vụ có lắng nghe, yêu cầu xác thực và bảo vệ dữ liệu đúng cách hay không.

Một private subnet không tự chứng minh cơ sở dữ liệu chỉ nhận kết nối từ ứng dụng. Vẫn phải kiểm tra các đường đi nội bộ, kết nối từ on-premises, peering và quy tắc ingress thực tế.

Ví dụ ma trận luồng:

| Nguồn | Đích | Mục đích | Tiêu chí đánh giá |
|---|---|---|---|
| Internet | Load Balancer | Người dùng truy cập HTTPS | Chỉ mở listener cần thiết, cấu hình TLS phù hợp |
| Load Balancer | Backend ứng dụng | Chuyển tiếp yêu cầu | Chỉ cho phép nguồn backend cần thiết và cổng thực sự sử dụng |
| Ứng dụng | Cơ sở dữ liệu | Giao dịch nghiệp vụ | Giới hạn nguồn, đích và cổng theo dịch vụ DB được chọn |
| Ứng dụng | Object Storage | Đọc/ghi tệp | Đường truy cập và IAM chỉ cho phép tài nguyên cần thiết |
| Người vận hành | Kênh quản trị | Bảo trì có kiểm soát | Danh tính riêng, quyền có giới hạn và dấu vết truy cập |
| Ứng dụng | Internet | Gọi API bên ngoài hoặc cập nhật | Chỉ mở khi có nhu cầu, theo dõi phụ thuộc và lưu lượng ra |

Nếu dùng Service Gateway, cần xác nhận đích là dịch vụ OCI được gateway hỗ trợ trong phạm vi cấu hình tương ứng. Service Gateway không phải đường ra Internet tổng quát. NAT Gateway giải quyết một kiểu kết nối đi ra từ mạng riêng; nó không thay thế cơ chế phân quyền, mã hóa hoặc phục hồi dịch vụ.

Bằng chứng tốt gồm cấu hình route, quy tắc NSG/security list và kết quả thử kết nối từ cả nguồn được phép lẫn nguồn phải bị từ chối. Chỉ chụp ảnh một NSG là chưa đủ nếu security list hoặc đường kết nối khác vẫn mở rộng bề mặt truy cập.

### 4.3. Secret, dữ liệu và khóa mã hóa

Kiểm tra vòng đời secret từ lúc tạo đến lúc thu hồi:

- Secret có xuất hiện trong mã nguồn, file cấu hình công khai, log, script khởi tạo hoặc đầu ra pipeline không?
- Ai có thể đọc secret, ai được phép thay đổi nó?
- Ứng dụng lấy secret bằng cách nào và giữ nó trong bộ nhớ bao lâu?
- Khi xoay vòng secret, kết nối cũ và mới chuyển tiếp thế nào?
- Có thể thu hồi credential bị lộ mà không phải sửa thủ công hàng loạt máy không?

OCI Vault là một công cụ có thể dùng cho secret hoặc khóa, nhưng việc “đã dùng Vault” chưa chứng minh policy, xoay vòng và quy trình vận hành đều đúng.

Với mã hóa, tách riêng:

1. Mã hóa trên đường truyền: đoạn người dùng đến Load Balancer, Load Balancer đến backend, ứng dụng đến cơ sở dữ liệu.
2. Mã hóa khi lưu: database, volume, Object Storage và bản sao lưu.
3. Quyền sử dụng khóa và khả năng phục hồi khi khóa không khả dụng.

Nếu chọn khóa do khách hàng quản lý, phải đánh giá thêm quyền quản trị, thao tác vô hiệu hóa/xóa, phụ thuộc liên region và việc khôi phục bản sao dùng khóa đó. Không chọn cơ chế quản lý khóa phức tạp chỉ để tăng số lượng tính năng trong sơ đồ.

Dữ liệu nhạy cảm còn cần chính sách lưu giữ, ẩn thông tin trong log và kiểm soát dữ liệu thử nghiệm. Mã hóa không xử lý việc một tài khoản hợp lệ được cấp quyền đọc quá nhiều dữ liệu.

### 4.4. Audit, log và phát hiện sai lệch

Phân biệt mục đích của từng nguồn:

| Nguồn | Hỗ trợ trả lời |
|---|---|
| Audit | Ai đã gọi những API điều khiển thuộc phạm vi được ghi nhận, vào lúc nào? |
| Log ứng dụng | Yêu cầu nào thất bại, tại bước nghiệp vụ nào, với mã tương quan nào? |
| Log truy cập hoặc log mạng phù hợp | Lưu lượng đến từ đâu, đi đâu, có dấu hiệu bất thường gì? |
| Metric và alarm | Tình trạng đang vượt ngưỡng nào và có cần hành động không? |
| Cloud Guard nếu được triển khai | Có phát hiện nào về cấu hình hoặc hoạt động rủi ro trong phạm vi đã bật? |

Audit không thay thế đầy đủ nhật ký nghiệp vụ hoặc mọi truy cập dữ liệu. Một cấu hình sai không được công cụ phát hiện cũng không tự trở thành an toàn.

Cần thử việc gửi một cảnh báo có kiểm soát: phát sinh tín hiệu, kiểm tra alarm, kiểm tra kênh nhận và xác nhận người có trách nhiệm hiểu cách xử lý. Không đưa secret hay dữ liệu khách hàng thật vào gói bằng chứng.

## 5. Đánh giá độ tin cậy: đo khả năng chịu lỗi và phục hồi

### 5.1. Tìm điểm lỗi đơn theo từng lớp

Với mỗi thành phần, hỏi: “Nếu thành phần này ngừng hoạt động, chức năng nào ngừng và có cơ chế nào thay thế?”

| Lớp | Điểm lỗi đơn thường gặp | Bằng chứng cần có |
|---|---|---|
| Ứng dụng | Một instance duy nhất; session nằm trong bộ nhớ cục bộ | Số lượng backend, cách lưu trạng thái, thử mất một instance |
| Dữ liệu | Một cấu hình DB chưa có phương án phục hồi đáp ứng mục tiêu | Thiết kế HA/backup cụ thể, kết quả chuyển đổi hoặc restore |
| Mạng | Chỉ một đường kết nối quan trọng chưa có phương án dự phòng | Topology và thử nghiệm theo loại kết nối |
| Vận hành | Một người giữ mọi quyền và runbook | Danh sách người thay thế, quyền truy cập và diễn tập |
| Tự động hóa | Artifact, state hoặc pipeline không khôi phục được | Quy trình dựng lại và quản lý trạng thái triển khai |
| Quan sát | Alarm gửi vào kênh không ai theo dõi | Thử gửi cảnh báo và thời gian xác nhận |

Nhiều instance trong cùng một vị trí không xử lý mọi loại sự cố. Phân bố giữa FD giúp giảm một số rủi ro hạ tầng trong AD; nó không chứng minh khả năng chịu mất toàn AD. Phân bố giữa AD hoặc region chỉ có ý nghĩa nếu ứng dụng, dữ liệu và quy trình chuyển đổi cùng đáp ứng yêu cầu.

Số lượng AD và khả năng bố trí tài nguyên phụ thuộc region và dịch vụ. Báo cáo phải dùng bố trí thực tế, không suy từ một sơ đồ mẫu.

### 5.2. Tách HA, backup và DR

**High Availability (HA)** hướng đến tiếp tục cung cấp dịch vụ khi một thành phần gặp sự cố.

**Backup** cung cấp bản dữ liệu hoặc điểm phục hồi để khôi phục sau mất hoặc hỏng dữ liệu.

**Disaster Recovery (DR)** là kế hoạch phục hồi trước sự cố lớn trong phạm vi đã xác định, thường liên quan thêm địa điểm, bản sao dữ liệu và thủ tục chuyển hoạt động.

Ba khái niệm có quan hệ nhưng không thay thế nhau:

- Replica có thể tiếp nhận cả thao tác xóa nhầm hoặc dữ liệu lỗi.
- Backup còn nguyên chưa chắc restore đủ nhanh để đạt RTO.
- Dự phòng ở cùng region chưa chứng minh khả năng phục hồi khi mất region.
- Cơ sở dữ liệu phục hồi xong chưa có nghĩa ứng dụng, DNS, secret và kết nối người dùng đã hoạt động trở lại.

Với các dịch vụ cơ sở dữ liệu Oracle khác nhau, cơ chế HA, standby, backup và chuyển đổi có thể khác nhau. Đánh giá phải ghi rõ dịch vụ, tùy chọn và cấu hình đã triển khai. Không mặc định mọi dịch vụ database đều có cùng tính năng hoặc đã tự bật dự phòng liên region.

### 5.3. Kiểm chứng RTO và RPO bằng giao dịch đánh dấu

Một bài thử restore có ích nên có:

1. Tập dữ liệu thử với giao dịch mang mã duy nhất và thời điểm commit có thể đối chiếu.
2. Thời điểm bắt đầu sự cố hoặc điểm phục hồi mục tiêu đã xác định.
3. Thời điểm phát hiện, xác nhận, bắt đầu khôi phục và từng bước quan trọng.
4. Kiểm tra dữ liệu cuối cùng phục hồi được.
5. Kiểm tra nghiệp vụ từ điểm vào của người dùng.
6. Thời điểm kết thúc khi đủ điều kiện phục vụ đã thống nhất.

~~~text
RTO quan sát =
    Thời điểm dịch vụ được xác minh đã phục hồi
    - Mốc bắt đầu sự cố theo quy ước đánh giá

RPO quan sát =
    Khoảng dữ liệu chưa phục hồi được trước mốc sự cố,
    xác định bằng giao dịch và thời điểm commit
~~~

Nếu phát hiện sự cố sau 8 phút, chuẩn bị khôi phục 7 phút, restore 12 phút và kiểm tra nghiệp vụ 6 phút, tổng thời gian là 33 phút. Báo cáo “restore mất 12 phút nên đạt RTO 30 phút” đã bỏ sót phần lớn quá trình.

Với RPO, không chỉ dùng giờ tạo file backup để kết luận. Cần xem dữ liệu có thể khôi phục thực tế đến điểm nào, bao gồm chuỗi backup hoặc log cần thiết của giải pháp đã chọn.

Bản sao lưu phải được kiểm tra cùng quyền truy cập, khóa giải mã, dung lượng đích, phụ thuộc mạng và khả năng truy cập khi hệ thống nguồn gặp sự cố.

### 5.4. Kiểm tra chuyển đổi và tính đúng của dữ liệu

Nếu có standby hoặc cơ chế failover, không chỉ đo thời gian một địa chỉ mới bắt đầu phản hồi. Phải kiểm tra:

- Ứng dụng kết nối lại và làm mới connection pool thế nào.
- Giao dịch đang xử lý có bị lặp, mất hoặc ở trạng thái chưa xác định không.
- Cơ chế nào bảo đảm chỉ phía được phép nhận ghi tiếp tục nhận ghi.
- Độ trễ sao chép và lượng dữ liệu chưa đồng bộ tại thời điểm chuyển đổi.
- Cách quay về cấu hình vận hành bình thường và đồng bộ lại dữ liệu.

Retry phải có giới hạn, timeout phù hợp và backoff. Với tạo đơn, cần cơ chế chống tạo trùng, chẳng hạn khóa idempotency gắn với giao dịch nghiệp vụ. Retry vô hạn có thể khuếch đại tải trong đúng thời điểm cơ sở dữ liệu đang yếu nhất.

### 5.5. Tự động hóa có làm tăng khả năng phục hồi không?

Terraform hoặc OCI Resource Manager có thể hỗ trợ tái tạo hạ tầng. Tuy nhiên, “có mã hạ tầng” chưa đủ. Cần kiểm tra:

- State được bảo vệ, quản lý truy cập và kiểm soát thay đổi thế nào.
- Artifact ứng dụng và cấu hình của phiên bản cần khôi phục có còn truy cập được không.
- Secret, dữ liệu và các bước thủ công có nằm trong kế hoạch dựng lại không.
- Chạy lại có tạo thêm tài nguyên, thay thế ngoài ý muốn hoặc làm mất dữ liệu không.
- Resource limit, quota và năng lực cấp phát có cản trở dựng lại không.

Có quyền tạo tài nguyên không đồng nghĩa chắc chắn sẽ có năng lực cấp phát đúng lúc. Kế hoạch phục hồi phải xem xét giới hạn và các phương án thay thế có thể vận hành được.

## 6. Đánh giá hiệu năng: gắn số đo với tải và cấu hình

### 6.1. Mô hình tải phải mô tả hành vi

Một báo cáo “chịu được 100 người dùng” thiếu nhiều thông tin. Cùng 100 người, hệ thống có thể nhận số yêu cầu rất khác nhau tùy thời gian chờ và loại thao tác.

Mô hình kiểm thử nên ghi:

| Thành phần | Nội dung cần xác định |
|---|---|
| Tốc độ đến | Số yêu cầu được phát mỗi giây và cách giữ tốc độ đó |
| Hỗn hợp nghiệp vụ | Tỷ lệ đọc, ghi, tải tệp, tìm kiếm hoặc báo cáo |
| Dữ liệu | Quy mô bảng, phân bố khóa, kích thước tệp và dữ liệu lịch sử |
| Vòng đời bài thử | Làm nóng, tăng tải, giữ tải, hạ tải và thời gian quan sát |
| Phiên kết nối | Tỷ lệ tạo kết nối mới, tái sử dụng kết nối và xác thực |
| Vị trí phát tải | Trong OCI, từ doanh nghiệp hoặc qua Internet |
| Cấu hình | Số instance, shape, giới hạn pool, DB và mức lưu trữ |
| Điều kiện đạt | Throughput, p95, p99, lỗi và tính đúng của nghiệp vụ |

Bộ phát tải cũng phải đủ năng lực. Nếu nó chỉ gửi được 70 yêu cầu/giây trong khi mục tiêu là 100, không thể kết luận ứng dụng đã đạt bài thử 100 yêu cầu/giây.

Với kịch bản 100 yêu cầu/giây trong 15 phút, số yêu cầu dự kiến ở giai đoạn giữ tải là:

~~~text
100 × 15 × 60 = 90.000 yêu cầu

Với ngưỡng lỗi dưới 0,5%:
Số yêu cầu lỗi phải dưới 450,
đồng thời tốc độ phát và tiêu chí hợp lệ phải được xác nhận.
~~~

Đây là ngưỡng của lần kiểm thử, không phải toàn bộ bằng chứng cho SLO 30 ngày.

### 6.2. Không chỉ đọc CPU trung bình

Các số đo cần được xem cùng nhau:

- Throughput thực đạt, số yêu cầu đang chờ và số timeout.
- p50, p95, p99 độ trễ theo endpoint và theo cửa sổ thời gian.
- CPU, bộ nhớ, áp lực garbage collection nếu ứng dụng dùng JVM.
- Số kết nối, thời gian chờ pool và giới hạn kết nối cơ sở dữ liệu.
- Thời gian truy vấn, lock, I/O và chỉ số liên quan đến cấu hình database.
- Độ trễ mạng, dung lượng truyền và kích thước payload.
- Health của backend, số instance thực phục vụ và thời điểm autoscaling.

CPU thấp vẫn có thể đi cùng độ trễ cao khi luồng xử lý chờ database, chờ kết nối hoặc gọi API bên ngoài.

Không lấy trung bình các giá trị p95 của từng instance rồi gọi đó là p95 toàn hệ thống. Cần tổng hợp dữ liệu phân phối phù hợp hoặc tính trên tập yêu cầu cần đánh giá. Cũng nên xem riêng endpoint tạo đơn để lưu lượng đọc nhanh không che khuất đường ghi chậm.

### 6.3. Ước lượng tải đồng thời bằng định luật Little

Trong điều kiện ổn định, có thể dùng:

~~~text
L ≈ λ × W

L: số yêu cầu trung bình đang ở trong hệ thống
λ: throughput trung bình
W: thời gian trung bình một yêu cầu ở trong hệ thống
~~~

Ví dụ, với 100 yêu cầu/giây và thời gian trung bình 0,2 giây:

~~~text
L ≈ 100 × 0,2 = 20 yêu cầu
~~~

Con số 20 là một kiểm tra hợp lý cho tải đồng thời trung bình trong các điều kiện đã nêu. Nó không phải số thread bắt buộc hoặc số kết nối database cần cấu hình. Một yêu cầu có thể không gọi database, gọi nhiều lần hoặc chờ một phụ thuộc khác. Không thay thời gian trung bình bằng p95 trong công thức này.

### 6.4. Kiểm tra năng lực khi mất một instance

Giả sử một instance đã được đo là xử lý tối đa khoảng 70 yêu cầu/giây trong khi vẫn đạt ngưỡng độ trễ và lỗi.

Với hai instance:

~~~text
Bình thường: 100 / 2 = 50 yêu cầu/giây/instance
Mất một instance: 100 / 1 = 100 yêu cầu/giây/instance
~~~

Kiến trúc có thể đạt tải khi bình thường nhưng không đạt yêu cầu mất một instance.

Hai phương án có thể đánh giá:

- Dùng ba instance cùng cấu hình: sau khi mất một instance, hai instance còn lại dự kiến chịu khoảng 50 yêu cầu/giây mỗi instance.
- Dùng hai instance lớn hơn, với năng lực mỗi instance đã được kiểm chứng đủ xử lý tải còn lại và phần dự phòng cần thiết.

Phép chia trên là bước sàng lọc, chưa chứng minh hệ thống sẽ mở rộng tuyến tính. Database, Load Balancer, kết nối hoặc tài nguyên dùng chung có thể trở thành giới hạn mới.

Autoscaling không làm năng lực xuất hiện tức thời. Bài thử cần đo thời gian phát hiện, cấp phát, khởi động ứng dụng, làm nóng và đưa backend vào phục vụ. Nếu yêu cầu không cho phép suy giảm trong khoảng đó, phải có năng lực sẵn trước hoặc thay đổi cam kết bằng quyết định được chấp thuận.

### 6.5. Một bộ thử nghiệm vừa đủ

| Loại thử | Mục đích |
|---|---|
| Baseline | Hiểu hành vi ở tải thấp, xác nhận công cụ và dữ liệu |
| Tải mục tiêu | Xác nhận ngưỡng tại 100 yêu cầu/giây |
| Mất một backend | Kiểm tra yêu cầu chịu lỗi ứng dụng trong cùng mức tải |
| Giữ tải kéo dài | Tìm rò rỉ bộ nhớ, tăng hàng đợi, tăng kết nối hoặc tăng lưu trữ |
| Phục hồi sau quá tải | Xem hệ thống có tự ổn định khi tải giảm không |
| Tăng tải đến giới hạn có kiểm soát | Xác định điểm bão hòa và cách hệ thống từ chối yêu cầu |

Các bài thử gây lỗi cần thực hiện trong môi trường được phép, có dữ liệu phù hợp, phạm vi ảnh hưởng và điều kiện dừng rõ ràng. Trước một thử nghiệm phục hồi, phải xác nhận đường quay về trạng thái ổn định.

## 7. Đánh giá chi phí: tính đủ phạm vi và đơn vị nghiệp vụ

### 7.1. Bắt đầu từ hóa đơn tài nguyên, kết thúc ở kết quả nghiệp vụ

Chi phí không chỉ là Compute. Với kiến trúc đang xét, cần rà soát:

- Compute instance, hệ điều hành và phần mềm có điều kiện sử dụng liên quan.
- Dịch vụ cơ sở dữ liệu, mức tài nguyên, lưu trữ và lựa chọn cấp phép.
- Boot volume, block volume, hiệu năng lưu trữ và bản sao lưu.
- Object Storage, số thao tác, lớp lưu trữ và thao tác truy xuất phù hợp.
- Load Balancer và các dịch vụ mạng được dùng.
- Lưu lượng truyền dữ liệu theo nguồn, đích và đường đi.
- Log, metric hoặc các tính năng quan sát có tính phí trong cấu hình thực tế.
- Môi trường ngoài production, tài nguyên bỏ quên và dữ liệu lưu quá lâu.
- Năng lực dự phòng, standby hoặc bản sao liên region phục vụ mục tiêu phục hồi.

Không giả định mọi lưu lượng ra đều bị tính giống nhau, cũng không mặc định đường truyền nào miễn phí. Dự toán phải nêu loại lưu lượng và quy tắc giá áp dụng sau khi được đối chiếu với thông tin giá tại thời điểm lập dự toán.

Free Tier hoặc credit có thể ảnh hưởng số tiền thanh toán ở một giai đoạn. Cần tách khoản ưu đãi khỏi chi phí vận hành chuẩn để không đánh giá sai tính bền vững của kiến trúc.

### 7.2. Bảng ước tính minh họa

Giả sử đã quy đổi từng hạng mục về cùng một kỳ tháng và cùng cơ sở giá trước thuế:

| Hạng mục | Ước tính USD/tháng | Động lực chính |
|---|---:|---|
| Compute ứng dụng | 180 | Hai instance và thời gian chạy |
| Cơ sở dữ liệu Oracle | 520 | Cấu hình, mức tài nguyên và lựa chọn cấp phép |
| Load Balancer | 60 | Cấu hình và mức sử dụng giả định |
| Boot/block volume | 80 | Dung lượng và hiệu năng |
| Object Storage cho dữ liệu ứng dụng | 30 | Dung lượng, lớp lưu trữ và truy cập |
| Quan sát | 85 | Log, lưu giữ và tính năng được bật |
| Mạng | 110 | Hướng truyền và lưu lượng giả định |
| Backup | 55 | Bản sao DB/volume thuộc phạm vi dự toán |
| **Tổng** | **1.120** | Chưa cộng dự phòng biến động |

Các hạng mục phải được kiểm tra để tránh tính hai lần. Trong bảng này, Object Storage chỉ gồm dữ liệu ứng dụng; chi phí bản sao thuộc phạm vi đã tách nằm ở dòng backup. Khi lập bảng thật, phải theo cách dịch vụ và hóa đơn thực tế phân loại chi phí.

Nếu dự kiến có 100.000 đơn thành công/tháng:

~~~text
Chi phí hạ tầng phân bổ cho một đơn =
    1.120 / 100.000
    = 0,0112 USD/đơn
~~~

Đây là chi phí hạ tầng phân bổ theo một đơn vị nghiệp vụ, chưa phải toàn bộ chi phí tạo ra một đơn. Phạm vi có thể chưa bao gồm nhân sự, thuế, hỗ trợ hoặc dịch vụ bên ngoài.

Khi lưu lượng tăng, chi phí trên mỗi đơn có thể giảm do tận dụng năng lực còn trống, sau đó tăng khi phải nâng cấp database hoặc mở thêm môi trường dự phòng. Không suy tuyến tính từ một điểm đo duy nhất.

### 7.3. Kiểm tra độ nhạy và khoảng dự phòng

Ít nhất nên so sánh các tình huống:

| Tình huống | Yếu tố cần tính lại |
|---|---|
| Lưu lượng tăng gấp đôi | Số instance, DB, log, băng thông và các giới hạn |
| Dữ liệu tăng sau một năm | Database, backup, Object Storage và thời gian restore |
| Bật dự phòng liên region | Tài nguyên dự phòng, bản sao và truyền dữ liệu |
| Giữ log lâu hơn | Dung lượng, truy vấn và chính sách lưu giữ |
| Sự cố kéo dài | Tài nguyên tạm, chạy song song, thao tác khôi phục |
| Hết ưu đãi | Giá vận hành sau credit hoặc chương trình hỗ trợ |

Nếu quy tắc dự toán yêu cầu cộng 10% dự phòng trên chi phí cơ sở, mức 1.120 USD sẽ thành 1.232 USD. Kiến trúc đã vượt ngưỡng 1.200 USD theo quy tắc này dù chi phí cơ sở vẫn thấp hơn ngân sách.

Phải chốt quy tắc dự phòng trước khi kết luận đạt. Không đổi cách tính sau khi thấy kết quả để làm cho dự toán vừa ngân sách.

### 7.4. Kiểm soát chi phí trong vận hành

Các biện pháp cần đánh giá gồm:

- Defined tags hoặc cơ chế phân bổ tương đương cho chủ sở hữu, môi trường, ứng dụng và trung tâm chi phí.
- Budget và cảnh báo đến người có khả năng hành động.
- Theo dõi Cost Analysis, biến động theo dịch vụ và đơn vị nghiệp vụ.
- Lịch tắt môi trường không cần hoạt động liên tục.
- Rightsizing dựa trên số đo, có tính nhu cầu chịu lỗi và tải đỉnh.
- Lifecycle cho Object Storage hoặc log theo yêu cầu truy xuất và lưu giữ.
- Kiểm soát tài nguyên mồ côi sau thử nghiệm hoặc thay đổi triển khai.
- Quota, giới hạn và quyền tạo tài nguyên theo nhu cầu quản trị.

**Budget alert không phải trần chi tiêu tự động.** Nó phát tín hiệu theo cấu hình và cơ chế ghi nhận chi phí; không nên được dùng như bằng chứng rằng hóa đơn chắc chắn sẽ dừng ở một số tiền. Quota hoặc service limit cũng không thay thế một cơ chế quản trị ngân sách hoàn chỉnh.

Không chuyển dữ liệu sang lớp lưu trữ khác chỉ dựa trên đơn giá dung lượng. Cần xem thời gian và chi phí truy xuất, yêu cầu lưu giữ, khả năng restore và tần suất sử dụng của dữ liệu đó.

## 8. Xử lý sự đánh đổi giữa bốn tiêu chí

Một phương án có thể cải thiện một tiêu chí và làm tiêu chí khác xấu đi. Người đánh giá phải mô tả tác động thay vì mặc định “nhiều dự phòng hơn luôn tốt hơn” hoặc “chi phí thấp nhất là tối ưu”.

| Quyết định | Lợi ích có thể đạt | Tác động cần kiểm chứng |
|---|---|---|
| Thêm một backend ứng dụng | Tăng năng lực còn lại khi mất một instance | Chi phí tăng, DB có thể thành điểm nghẽn |
| Dùng cache | Giảm độ trễ và tải database | Dữ liệu cũ, invalidation, quyền truy cập và sự cố cache |
| Ghi log chi tiết hơn | Điều tra lỗi tốt hơn | Chi phí, dữ liệu nhạy cảm và độ trễ ghi log |
| Thêm standby ngoài region | Mở rộng phạm vi phục hồi | Chi phí, replication lag, failover và tính nhất quán |
| Thu hẹp egress | Giảm bề mặt kết nối ra | Có thể làm hỏng cập nhật hoặc phụ thuộc bên ngoài |
| Giảm thời gian lưu backup | Giảm chi phí | Mất khả năng quay về trước thời điểm lỗi được phát hiện |
| Tắt môi trường ngoài giờ | Giảm chi phí Compute | Thời gian khởi động và lịch chạy kiểm thử |
| Đổi sang khóa tự quản lý | Tăng quyền kiểm soát theo yêu cầu | Rủi ro vận hành khóa và phụ thuộc khôi phục |

Một quyết định cần có lý do, các phương án đã xem xét, điều kiện áp dụng và cách xác nhận. Ví dụ:

> Chọn ba backend cấu hình hiện tại để đáp ứng mất một instance ở tải mục tiêu. Chỉ chấp nhận sau khi thử tải có lỗi xác nhận database không bão hòa và dự toán đã có dự phòng nằm trong ngân sách được duyệt.

Đây là quyết định có điều kiện đo được. Câu “tăng số instance để bảo đảm hệ thống ổn định” chưa nêu được giới hạn hoặc cách chứng minh.

## 9. Xây dựng ma trận yêu cầu và bằng chứng

### 9.1. Một dòng đánh giá phải truy vết được

Mỗi dòng nên có:

- Mã yêu cầu và lý do nghiệp vụ.
- Phạm vi và điều kiện thử.
- Ngưỡng đạt.
- Bằng chứng, thời điểm và cấu hình tương ứng.
- Kết quả quan sát.
- Người đánh giá và người chịu trách nhiệm khắc phục.
- Trạng thái: đạt, không đạt, chưa đủ bằng chứng hoặc không áp dụng có lý do.

Ví dụ:

| Mã | Yêu cầu | Bằng chứng cần thu thập | Ngưỡng đạt |
|---|---|---|---|
| SEC-01 | DB không truy cập trực tiếp từ Internet | Route, endpoint, NSG/security list và thử kết nối | Không có đường truy cập trái phép trong phạm vi kiểm tra |
| SEC-02 | Workload chỉ đọc dữ liệu cần thiết | Dynamic group, policy và thử truy cập tài nguyên ngoài phạm vi | Truy cập hợp lệ thành công; truy cập ngoài phạm vi bị từ chối |
| REL-01 | Chịu mất một backend | Log kiểm thử, backend health, metric và kết quả tải | Đạt tải, độ trễ và lỗi theo yêu cầu sau thời gian chuyển tiếp đã thống nhất |
| REL-02 | Khôi phục dữ liệu | Timeline, giao dịch đánh dấu và kiểm tra nghiệp vụ | RTO ≤ 30 phút; RPO ≤ 5 phút |
| PERF-01 | Phục vụ tải mục tiêu | Kịch bản, số liệu phát tải và phân phối độ trễ | 100 yêu cầu/giây, p95 < 400 ms, lỗi < 0,5% |
| COST-01 | Nằm trong ngân sách | Danh mục tài nguyên, giả định giá và độ nhạy | Tổng theo quy tắc dự phòng ≤ 1.200 USD/tháng |
| OPS-01 | Phát hiện và nhận cảnh báo | Alarm, kênh nhận và dấu vết thử thông báo | Đúng người nhận, trong thời gian phản hồi đã thống nhất |

Ngưỡng độ trễ cần có cửa sổ đánh giá. Ví dụ, yêu cầu đạt trong từng cửa sổ 5 phút ở giai đoạn giữ tải khác với yêu cầu chỉ đạt khi tính chung toàn bộ 15 phút. Phải chọn trước và áp dụng thống nhất cho cả bài thử bình thường lẫn bài thử có lỗi.

### 9.2. Đánh giá chất lượng bằng chứng

Có thể phân biệt bốn mức:

| Mức | Ví dụ | Có thể kết luận |
|---|---|---|
| Tuyên bố | “Đã có backup” | Biết ý định, chưa chứng minh cấu hình hoặc phục hồi |
| Thiết kế | Sơ đồ và mô tả luồng backup | Biết phương án dự kiến |
| Triển khai | Cấu hình backup và lịch chạy | Biết một cơ chế đã được cấu hình |
| Kiểm chứng | Restore thành công, đo RTO/RPO và kiểm tra dữ liệu | Biết khả năng quan sát trong điều kiện đã thử |

Không phải tiêu chí nào cũng cần một thử nghiệm gây lỗi. Ví dụ policy có thể cần xem cấu hình và thử truy cập có kiểm soát; mục tiêu RTO phải có bằng chứng phục hồi phù hợp. Chọn hình thức chứng minh theo loại yêu cầu.

Mỗi bằng chứng nên gắn với phiên bản triển khai, thời điểm, môi trường và phương pháp thu thập. Nếu thử tải chạy trước khi giảm cấu hình database, kết quả đó không chứng minh cấu hình mới vẫn đạt.

“Không áp dụng” cần lý do được chấp thuận. “Chưa thử” không được đổi thành “không áp dụng”.

## 10. Dùng thang điểm nhưng giữ điều kiện bắt buộc

### 10.1. Thang điểm 0–4

| Điểm | Ý nghĩa |
|---:|---|
| 0 | Không có cơ chế đáp ứng, hoặc đã biết không đáp ứng mà chưa có phương án |
| 1 | Có ý tưởng hoặc thiết kế, chưa triển khai đủ |
| 2 | Đã triển khai một phần hoặc chỉ đạt trong điều kiện hạn chế |
| 3 | Đã triển khai và có bằng chứng kiểm chứng phù hợp cho yêu cầu chính |
| 4 | Đã kiểm chứng, có vận hành lặp lại, theo dõi sai lệch và cải tiến dựa trên số liệu |

Điểm 4 không có nghĩa hệ thống tuyệt đối an toàn hoặc không thể gián đoạn. Nó thể hiện độ trưởng thành của cơ chế và bằng chứng trong phạm vi được chốt.

Nếu thiếu bằng chứng, phải ghi rõ mức tin cậy. Không cho điểm tối đa vì nhóm trình bày tự tin hoặc sơ đồ trông đầy đủ.

### 10.2. Trọng số minh họa

| Tiêu chí | Trọng số |
|---|---:|
| Bảo mật | 30% |
| Độ tin cậy | 30% |
| Hiệu năng | 20% |
| Chi phí | 20% |
| **Tổng** | **100%** |

~~~text
Điểm tổng trên thang 100 =
    Tổng của [trọng số dạng thập phân × điểm tiêu chí / 4] × 100
~~~

Ví dụ điểm lần lượt là 3, 2, 2 và 3:

~~~text
(0,30 × 3/4 + 0,30 × 2/4 + 0,20 × 2/4 + 0,20 × 3/4) × 100
= 62,5 điểm
~~~

Trọng số cần chốt trước buổi đánh giá. Hệ thống xử lý dữ liệu nhạy cảm hoặc có yêu cầu liên tục đặc biệt có thể dùng trọng số khác. Không điều chỉnh trọng số chỉ vì một tiêu chí đang có kết quả thấp.

### 10.3. Điều kiện không được bù bằng điểm

Một số điều kiện nên được đặt thành cổng nghiệm thu bắt buộc:

| Cổng | Ví dụ điều kiện |
|---|---|
| G1 — Truy cập và dữ liệu | Không còn đường truy cập nghiêm trọng ngoài phạm vi cho phép; không phát hiện secret còn hiệu lực bị công khai |
| G2 — Phục hồi | Đã có bằng chứng phục hồi đáp ứng RTO/RPO trong các kịch bản bắt buộc |
| G3 — Tải và chịu lỗi | Đạt bài thử tải mục tiêu và bài thử mất backend theo yêu cầu |
| G4 — Tài chính | Dự toán đầy đủ theo giả định và dự phòng đã duyệt nằm trong ngân sách hoặc có quyết định cấp ngân sách mới |
| G5 — Vận hành | Có chủ sở hữu, cảnh báo hoạt động và runbook truy cập được |

Một dự án 85 điểm nhưng không đạt G1 hoặc G2 vẫn có thể chưa đủ điều kiện đưa vào production. Ngưỡng điểm tổng chỉ là một phần của quyết định.

Với kết luận cho phép vận hành có điều kiện, cần chỉ rõ điều kiện đó áp dụng trước triển khai hay trong giai đoạn giới hạn, ai chấp nhận rủi ro và phạm vi sử dụng được phép. Không dùng cụm “chấp nhận có điều kiện” để bỏ qua một cổng đã được xác định là bắt buộc trước production.

## 11. Ví dụ đánh giá hoàn chỉnh cho kiến trúc giả định

### 11.1. Trạng thái quan sát giả định

Nhóm cung cấp các bằng chứng minh họa sau:

- Quyền triển khai và vận hành đã được tách; người quản trị dùng MFA; thử truy cập ngoài phạm vi workload bị từ chối.
- Database không có đường truy cập trực tiếp từ Internet trong phạm vi đã kiểm tra.
- Hai backend ứng dụng được bố trí tách FD phù hợp trong AD đang sử dụng; chưa cam kết chịu mất toàn AD bằng bố trí này.
- Bài thử bình thường đạt 100 yêu cầu/giây, p95 310 ms, lỗi 0,2%.
- Sau thời gian loại backend lỗi đã thống nhất, bài thử mất một instance có p95 820 ms và lỗi 3,1%; instance còn lại bão hòa.
- Diễn tập khôi phục dữ liệu đo được RTO 36 phút, RPO 18 phút.
- Dự toán cơ sở là 1.120 USD/tháng; quy tắc dự phòng được duyệt là cộng 10%.
- Alarm đã gửi được đến người trực; quy trình diễn tập định kỳ còn thiếu lịch và chủ sở hữu cụ thể.

Các số liệu đều giả định. Trong dự án thật, phải gắn từng kết quả với bằng chứng của chính lần kiểm tra đó.

### 11.2. Kết quả theo bốn tiêu chí

| Tiêu chí | Điểm | Nhận định |
|---|---:|---|
| Bảo mật | 3/4 | Có kiểm tra quyền và đường truy cập chính; cần tiếp tục hoàn thiện kiểm tra lặp lại |
| Độ tin cậy | 2/4 | Có cơ chế triển khai và restore nhưng RTO/RPO chưa đạt; năng lực khi mất backend thiếu |
| Hiệu năng | 2/4 | Đạt khi bình thường; không đạt trong tình huống lỗi bắt buộc |
| Chi phí | 3/4 | Có mô hình chi phí và độ nhạy; kết quả sau dự phòng vượt ngân sách |
| **Tổng có trọng số** | **62,5/100** | **Chưa đủ điều kiện nghiệm thu production** |

Điểm chi phí 3 phản ánh việc đã có cơ chế đo và dự toán có bằng chứng; nó không làm mất đi kết quả không đạt ngân sách. Cổng nghiệm thu vẫn được xét độc lập.

| Cổng | Kết quả | Lý do |
|---|---|---|
| G1 | Đạt trong phạm vi kiểm tra | Các đường truy cập và secret được kiểm tra không có phát hiện ngăn nghiệm thu |
| G2 | Không đạt | 36 phút > 30 phút; 18 phút > 5 phút |
| G3 | Không đạt | Độ trễ và lỗi khi mất một backend vượt ngưỡng |
| G4 | Không đạt | 1.120 × 1,10 = 1.232 USD > 1.200 USD |
| G5 | Chưa đủ bằng chứng | Thiếu phân công và lịch duy trì diễn tập vận hành |

Kết luận hợp lý là tiếp tục khắc phục và kiểm chứng các cổng chưa đạt. Không thể kết luận “đạt vì bình thường chạy tốt” hoặc “chỉ cần thêm một máy là xong”.

### 11.3. Danh sách phát hiện có thể hành động

| Mã | Phát hiện | Tác động | Hướng khắc phục | Cách đóng phát hiện |
|---|---|---|---|---|
| F-01 | Năng lực còn lại không đủ khi mất một backend | Lỗi nghiệp vụ và tăng độ trễ khi một máy hỏng | So sánh thêm backend với tăng cấu hình; kiểm tra DB dùng chung | Chạy lại bài thử có lỗi, đạt toàn bộ ngưỡng và cửa sổ đã chốt |
| F-02 | Chuỗi khôi phục dữ liệu vượt RTO/RPO | Không đáp ứng mức mất dữ liệu và thời gian phục hồi được cam kết | Phân tích từng bước, điều chỉnh cơ chế phục hồi theo dịch vụ DB thực tế | Restore lại với giao dịch đánh dấu, đo đầy đủ và đạt mục tiêu |
| F-03 | Dự toán sau dự phòng vượt ngân sách | Thiếu ngân sách cho vận hành hoặc phát sinh phải cắt giảm đột xuất | Tối ưu có số đo hoặc xin phê duyệt ngân sách mới | Dự toán theo cùng quy tắc được phê duyệt và có chủ sở hữu theo dõi |
| F-04 | Diễn tập chưa có lịch và người chịu trách nhiệm | Runbook có thể lỗi thời, không ai xác nhận khả năng phục hồi | Phân công, đặt lịch và lưu kết quả từng lần | Có lịch, người thay thế và lần diễn tập được xác nhận |

Trong báo cáo thật, bổ sung người phụ trách và hạn hoàn thành cho từng dòng. Hướng khắc phục nên cho phép so sánh phương án, không mặc định một dịch vụ duy nhất là đáp án.

### 11.4. Tính lại chi phí sau khi sửa độ tin cậy

Giả sử chọn thêm một backend với chi phí tăng 90 USD/tháng. Nhóm cũng đề xuất:

- Giảm 20 USD nhờ lifecycle dữ liệu phù hợp.
- Giảm 25 USD nhờ giảm log không cần thiết, giữ đủ log bảo mật và điều tra.
- Giảm 35 USD nhờ điều chỉnh đường truyền hoặc lưu lượng sau khi đã xác minh tác động.

~~~text
Chi phí cơ sở mới = 1.120 + 90 - 20 - 25 - 35
                  = 1.130 USD/tháng

Có dự phòng 10% = 1.130 × 1,10
                = 1.243 USD/tháng
~~~

Phương án cải thiện năng lực dự kiến vẫn chưa đạt ngân sách 1.200 USD. Để giữ quy tắc dự phòng 10%, chi phí cơ sở phải không quá khoảng 1.090,91 USD/tháng; nếu cần làm tròn đến cent theo hướng bảo đảm không vượt, dùng tối đa 1.090,90 USD.

Nhóm cần tối ưu thêm hoặc xin phê duyệt ngân sách phù hợp. Không được bỏ phần dự phòng, giảm backup dưới yêu cầu hoặc ngừng thu thập log bắt buộc chỉ để thay trạng thái thành đạt.

Sau khi thêm backend, vẫn phải kiểm thử lại. Các con số chia tải và dự toán chỉ hỗ trợ lựa chọn; chúng không phải kết quả xác minh cho cấu hình mới.

## 12. Tổ chức buổi đánh giá và xác minh lại

### 12.1. Trước buổi đánh giá

Nhóm chuẩn bị một phiên bản triển khai xác định và bộ bằng chứng đã che dữ liệu nhạy cảm:

1. Tóm tắt nghiệp vụ, SLO, RTO, RPO, ngân sách và các phụ thuộc.
2. Sơ đồ hiện trạng và danh mục tài nguyên theo compartment.
3. Ma trận yêu cầu, ngưỡng đạt và các cổng nghiệm thu.
4. Cấu hình hoặc trích xuất cần thiết về IAM, mạng, lưu trữ, database và quan sát.
5. Kịch bản và kết quả kiểm thử, gồm cả giới hạn của từng bài thử.
6. Dự toán, giả định tính giá, phân bổ chi phí và phân tích độ nhạy.
7. Runbook, quyết định kiến trúc và những rủi ro đã biết.

Không đưa private key, mật khẩu, token hoặc bản dữ liệu khách hàng vào tài liệu nộp. Bằng chứng cần đủ để kiểm tra cấu hình và hành vi mà không tạo thêm bề mặt lộ thông tin.

### 12.2. Trong buổi đánh giá

Trình tự hiệu quả:

- Chốt lại phạm vi, phiên bản và điều kiện nghiệm thu.
- Đi theo luồng nghiệp vụ, luồng quản trị và luồng phục hồi.
- Kiểm tra yêu cầu quan trọng bằng bằng chứng thay vì chỉ nghe mô tả.
- So sánh kết quả bình thường với các tình huống lỗi đã cam kết.
- Xem dự toán sau khi tính các thay đổi cần thiết để đạt độ tin cậy.
- Ghi phát hiện, mức ảnh hưởng, người chịu trách nhiệm và cách xác minh lại.
- Kết luận trạng thái của từng cổng và phạm vi được phép tiếp tục.

Người đánh giá nên ghi cả giới hạn của kết luận. Chẳng hạn, thử mất một instance thành công chỉ chứng minh kịch bản đó trong cấu hình đã thử; không tự chứng minh khả năng chịu mất database, AD hoặc region.

### 12.3. Sau khi khắc phục

Không cần chạy lại mọi kiểm tra nếu thay đổi chỉ ảnh hưởng phạm vi hẹp. Tuy nhiên, phải xác định quan hệ phụ thuộc:

| Thay đổi | Các bằng chứng thường cần cập nhật |
|---|---|
| Sửa IAM policy | Quyền hợp lệ, quyền bị từ chối, hoạt động của pipeline/workload |
| Thêm backend | Tải bình thường, mất backend, DB, session và chi phí |
| Đổi cơ chế backup | Restore, RTO/RPO, quyền, khóa và chi phí lưu giữ |
| Đổi lớp lưu trữ | Truy xuất, khả năng phục hồi, lưu giữ và dự toán |
| Giảm log | Khả năng điều tra, cảnh báo, thông tin nhạy cảm và chi phí |
| Thêm region dự phòng | Mạng, dữ liệu, IAM/khóa, chuyển đổi, quay về và dự toán |

Một phát hiện chỉ được đóng khi có bằng chứng đáp ứng tiêu chí đóng. “Đã chỉnh cấu hình” là trạng thái thực hiện, chưa chắc là trạng thái đạt.

## 13. Mẫu kết luận đánh giá kiến trúc

Mẫu dưới đây là cấu trúc nội dung báo cáo, không phải lệnh hay cấu hình triển khai:

~~~text
HỆ THỐNG / MÔI TRƯỜNG:
PHIÊN BẢN TRIỂN KHAI:
THỜI ĐIỂM VÀ NGƯỜI ĐÁNH GIÁ:

PHẠM VI:
- Region, compartment, dịch vụ và phụ thuộc được xét.
- Loại sự cố được cam kết xử lý.
- Ngoại lệ đã được chấp thuận và giới hạn của bằng chứng.

YÊU CẦU:
- SLO và cách tính SLI.
- Tải, độ trễ và tỷ lệ lỗi.
- RTO/RPO theo từng kịch bản.
- Ngân sách, cơ sở giá và quy tắc dự phòng.

KẾT QUẢ:
- Điểm bốn tiêu chí và mức tin cậy.
- Trạng thái từng cổng nghiệm thu.
- Bằng chứng gắn với phiên bản được đánh giá.

PHÁT HIỆN:
- Mã, mô tả và tác động.
- Mức ưu tiên, người phụ trách và hạn hoàn thành.
- Biện pháp, rủi ro còn lại và cách xác minh.

QUYẾT ĐỊNH:
- Đủ điều kiện / chưa đủ điều kiện trong phạm vi nào.
- Điều kiện bắt buộc trước vận hành.
- Người có thẩm quyền chấp nhận rủi ro còn lại.
- Thời điểm hoặc thay đổi nào kích hoạt đánh giá lại.
~~~

Một kết luận tốt có thể viết:

> Cấu hình hiện tại đạt kiểm tra quyền truy cập chính và bài thử tải bình thường. Chưa đủ điều kiện production vì phục hồi dữ liệu, tải khi mất backend và dự toán sau dự phòng chưa đạt ngưỡng. Nhóm triển khai cần hoàn tất F-01 đến F-04, cập nhật dự toán và nộp bằng chứng xác minh tương ứng trước khi đề nghị nghiệm thu lại.

Câu này nêu kết quả, giới hạn và công việc tiếp theo. Nó không biến một danh sách tính năng OCI thành lời bảo đảm về chất lượng hệ thống.

## 14. Những sai lầm làm kết quả đánh giá mất giá trị

| Sai lầm | Vì sao kết luận không đáng tin | Cách sửa |
|---|---|---|
| Cho rằng private subnet đã đủ an toàn | Bỏ qua IAM, route, luồng nội bộ và credential | Đánh giá cả quyền, đường đi và thử truy cập |
| Dùng SLA của dịch vụ làm SLO ứng dụng | Bỏ qua phụ thuộc và lỗi nghiệp vụ | Đo SLI từ hành vi người dùng đã định nghĩa |
| Có hai instance nên coi là HA đầy đủ | Có thể cùng miền lỗi hoặc thiếu năng lực khi mất một máy | Kiểm tra placement, trạng thái và tải còn lại |
| Có backup nên coi như đạt RTO/RPO | Chưa chứng minh restore, dữ liệu và phụ thuộc | Diễn tập và đo toàn bộ chuỗi phục hồi |
| Thử tải với dữ liệu rất nhỏ rồi suy cho production | Không phản ánh truy vấn, I/O hoặc kích thước payload thật | Dùng dữ liệu và phân bố gần mục tiêu |
| CPU thấp nên giảm tài nguyên ngay | Có thể đang chờ DB hoặc cần năng lực dự phòng | Xem nút thắt, tải đỉnh và bài thử có lỗi |
| Trung bình độ trễ đẹp nên kết luận đạt | Có thể che khuất đuôi chậm và endpoint quan trọng | Xem percentile, endpoint và cửa sổ thời gian |
| Có budget alert nên coi như không thể vượt tiền | Cảnh báo không tự tạo trần chi tiêu | Có người xử lý, dự toán và kiểm soát tài nguyên |
| Dùng credit để chứng minh kiến trúc rẻ | Không phản ánh chi phí sau giai đoạn ưu đãi | Tách ưu đãi khỏi chi phí vận hành chuẩn |
| Cộng điểm để bỏ qua lỗi nghiêm trọng | Điểm cao ở mặt khác không phục hồi dữ liệu bị mất | Giữ các cổng nghiệm thu độc lập |
| Dùng kết quả cũ cho cấu hình mới | Bằng chứng không còn khớp hệ thống | Gắn phiên bản và xác minh lại phần bị ảnh hưởng |
| Chấp nhận rủi ro mà không có người chịu trách nhiệm | Không có quyết định quản trị có thể truy vết | Ghi người có thẩm quyền, thời hạn và điều kiện |

Chất lượng của một capstone OCI thể hiện ở chuỗi truy vết **yêu cầu → quyết định kiến trúc → cấu hình triển khai → bằng chứng → kết luận**. Khi chuỗi này đầy đủ, nhóm có thể giải thích không chỉ hệ thống được xây bằng dịch vụ nào, mà còn vì sao nó đáp ứng mục tiêu, ở giới hạn nào và cần thay đổi điều gì khi nhu cầu phát triển.

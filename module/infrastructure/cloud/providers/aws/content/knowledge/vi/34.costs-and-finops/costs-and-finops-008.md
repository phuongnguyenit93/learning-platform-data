# Savings Plans, Reserved Instances và lựa chọn cam kết

## Mục tiêu học tập

AWS cung cấp nhiều mô hình giá để giảm chi phí cho workload có mức sử dụng ổn định. Đổi lại, tổ chức phải cam kết chi tiêu hoặc cấu hình sử dụng trong một khoảng thời gian. Nếu chọn đúng, cam kết giúp giảm chi phí so với On-Demand. Nếu mua quá nhiều, thay đổi workload hoặc chọn sai phạm vi, tổ chức vẫn trả tiền cho phần cam kết không được sử dụng.

Trong hệ sinh thái AWS, Savings Plans và Reserved Instances (RI) là hai nhóm cơ chế thường được dùng để tối ưu compute và database. Chúng có cách cam kết, phạm vi áp dụng, mức linh hoạt, quyền lợi capacity và rủi ro tài chính khác nhau. Bài học này giúp đánh giá các lựa chọn đó dựa trên dữ liệu sử dụng, kiến trúc và kế hoạch thay đổi workload.

Sau bài học, người học có thể:

- Phân biệt On-Demand, Spot, Savings Plans, Reserved Instances và On-Demand Capacity Reservations.
- Giải thích bốn loại Savings Plans: Compute, EC2 Instance, Database và SageMaker AI.
- Phân biệt Standard/Convertible EC2 Reserved Instances và Regional/Zonal scope.
- Hiểu Reserved DB Instances của RDS và các giới hạn size flexibility.
- Tính mức cam kết theo usage ổn định, coverage, utilization và chi phí cơ hội.
- Dùng Cost Explorer Recommendations, Purchase Analyzer và reservation reports để đánh giá phương án.
- Chọn term, payment option, account scope và mức cam kết phù hợp với rủi ro.
- Thiết lập governance, theo dõi expiry và điều chỉnh danh mục cam kết theo thay đổi kiến trúc.

## 1. Vì sao cần mô hình giá cam kết?

On-Demand phù hợp khi cần linh hoạt, workload chưa ổn định hoặc chưa biết chính xác mức sử dụng. Với workload chạy đều trong thời gian dài, trả toàn bộ theo On-Demand có thể tốn hơn so với mức giá được chiết khấu khi cam kết.

AWS dùng nhiều mô hình:

| Mô hình | Cách trả tiền | Phù hợp khi |
|---|---|---|
| On-Demand | Trả theo lượng tài nguyên sử dụng, không cần cam kết dài hạn | Workload mới, biến động hoặc ngắn hạn |
| Spot | Dùng capacity AWS chưa sử dụng với giá thấp hơn, có thể bị gián đoạn | Batch, CI, xử lý nền có thể retry/checkpoint |
| Savings Plans | Cam kết mức chi tiêu đủ điều kiện tính theo USD/giờ trong term | Có usage nền ổn định nhưng muốn linh hoạt dịch vụ hoặc cấu hình |
| Reserved Instances | Cam kết thuộc tính cấu hình và term để nhận billing discount | Usage EC2/RDS hoặc dịch vụ có reservation tương đối ổn định |
| On-Demand Capacity Reservation | Giữ capacity EC2 trong một AZ, không tự tạo discount | Cần bảo đảm có capacity trong AZ cụ thể |

Savings Plans và RI không làm tài nguyên tự chạy, không thay thế Auto Scaling và không bảo đảm ứng dụng hoạt động đúng. Chúng là lựa chọn về giá và quyền lợi billing; kiến trúc vẫn cần được thiết kế theo tải, availability và recovery.

### 1.1. Cam kết là nghĩa vụ tài chính

Khi mua Savings Plan, tổ chức cam kết một mức chi tiêu mỗi giờ trong suốt term. Khi mua RI, tổ chức cam kết trả phí theo term và offering đã chọn, kể cả khi không có instance khớp đang chạy. No Upfront chỉ có nghĩa không thanh toán một khoản lớn ở đầu kỳ; nó không loại bỏ nghĩa vụ thanh toán trong thời hạn.

Trước khi mua, cần trả lời:

- Workload nào tạo ra mức sử dụng ổn định?
- Phần usage nào sẽ còn tồn tại sau right-sizing hoặc migration?
- Khi nào workload có thể giảm, chuyển Region, đổi engine hoặc đổi instance family?
- Ngân sách có thể chịu được khoản upfront hoặc phí định kỳ trong toàn term không?
- Ai chịu trách nhiệm theo dõi utilization và quyết định gia hạn?

## 2. On-Demand, Spot và cam kết: chọn đúng lớp

Không nên cố phủ mọi usage bằng cam kết. Mỗi workload có độ ổn định và yêu cầu khác nhau.

| Đặc điểm workload | Lựa chọn thường phù hợp |
|---|---|
| Production baseline chạy 24/7, ít thay đổi | Savings Plans hoặc RI |
| API có tải nền ổn định nhưng cần scale theo mùa | Cam kết phần baseline, giữ phần peak trên On-Demand |
| Batch có thể chạy lại khi bị ngắt | Spot, kết hợp On-Demand khi cần |
| Môi trường dev/test chỉ chạy giờ hành chính | Scheduling và On-Demand; chỉ cam kết nếu mức nền thực sự ổn định |
| Workload thử nghiệm, POC hoặc migration tạm thời | On-Demand |
| Cần capacity EC2 chắc chắn trong một AZ | Zonal RI hoặc On-Demand Capacity Reservation, tùy yêu cầu discount |
| Database có mức sử dụng ổn định và engine ít đổi | RDS Reserved DB Instance hoặc Database Savings Plan |
| Database có kế hoạch đổi engine/service hoặc Region | Database Savings Plan có thể linh hoạt hơn RI truyền thống |

Một chiến lược tốt thường kết hợp nhiều mô hình. Phần ổn định được bảo vệ bằng cam kết; phần biến động dùng On-Demand; phần có thể gián đoạn dùng Spot; capacity quan trọng được xử lý riêng.

## 3. Savings Plans hoạt động thế nào?

Savings Plans là mô hình giá giảm chi phí đổi lấy cam kết sử dụng một lượng dịch vụ đủ điều kiện, đo bằng USD mỗi giờ. AWS tự động áp dụng mức giá Savings Plans cho usage phù hợp. Người vận hành không phải gắn từng instance với một reservation.

Các đặc điểm chung:

- Term phổ biến là 1 năm hoặc 3 năm; một năm được tính 365 ngày và ba năm là 1.095 ngày theo định nghĩa của Savings Plans.
- Cam kết được đo bằng USD/giờ theo Savings Plans rate, không phải On-Demand spend tương đương.
- Mỗi giờ có một khoản cam kết riêng. Phần chưa sử dụng trong giờ đó không được chuyển sang giờ tiếp theo.
- Usage đủ điều kiện vượt mức cam kết sẽ được tính theo On-Demand.
- Cam kết và giá Savings Plans của plan không thể thay đổi hoặc hủy giữa term.
- Có thể mua thêm plan nếu usage ổn định tăng lên, nhưng cần phân tích tổng danh mục cam kết.
- Savings Plans không tự đặt trước capacity.

### 3.1. Hourly commitment không phải On-Demand budget

Giả sử usage EC2 đủ điều kiện có On-Demand equivalent là 100 USD/giờ. Nếu mức giá Savings Plans của cấu hình đó tương đương 60 USD/giờ, cam kết cần xét là khoảng 60 USD/giờ theo Savings Plans rate.

Không nên lấy 60 USD/giờ On-Demand rồi nhập 60 USD/giờ vào trường commitment mà không kiểm tra mức giá áp dụng. AWS hiển thị mức cam kết theo giá Savings Plans, vì vậy cùng một mức usage On-Demand có thể cần một con số commitment thấp hơn.

### 3.2. Phần cam kết không sử dụng vẫn bị tính phí

Nếu commitment là 60 USD/giờ nhưng usage đủ điều kiện trong một giờ chỉ tiêu thụ 45 USD theo Savings Plans rate, utilization của giờ đó là 75%. Khoản 15 USD còn lại không được hoàn lại hoặc chuyển sang giờ kế tiếp.

Nếu usage đủ điều kiện tăng cao hơn mức có thể được cover bởi commitment, phần còn lại vẫn được tính On-Demand. Đây là lý do phải đo usage theo giờ và tránh mua cam kết chỉ dựa trên tổng chi tiêu trung bình tháng.

## 4. Bốn loại Savings Plans

Theo tài liệu AWS hiện hành, có bốn loại Savings Plans. Mỗi loại áp dụng cho phạm vi usage khác nhau.

| Loại | Phạm vi áp dụng | Mức tiết kiệm tối đa AWS công bố và mức linh hoạt |
|---|---|---|
| Compute Savings Plans | EC2, AWS Fargate, AWS Lambda | Up to 66%; không khóa instance family, size, Region, OS hoặc tenancy đối với EC2 |
| EC2 Instance Savings Plans | Amazon EC2 | Up to 72%; khóa instance family và Region, linh hoạt size, OS và tenancy trong phạm vi đó |
| Database Savings Plans | Các dịch vụ database đủ điều kiện | Up to 35%; linh hoạt engine, family, size, AZ, Region và loại provisioned/serverless trong phạm vi hỗ trợ |
| SageMaker AI Savings Plans | Amazon SageMaker AI | Up to 64%; linh hoạt family, size, Region và component đủ điều kiện |

Mức tiết kiệm “up to” do AWS công bố là mức tối đa so với On-Demand cho một số cấu hình và điều kiện nhất định. Không được dùng mức tối đa đó làm giả định savings mặc định cho mọi Region, engine hoặc workload.

### 4.1. Compute Savings Plans

Compute Savings Plans có phạm vi rộng nhất trong nhóm compute:

- Áp dụng cho EC2 bất kể instance family, size, Region, OS hoặc tenancy.
- Áp dụng cho AWS Fargate, bao gồm Fargate dùng với ECS và EKS.
- Áp dụng cho AWS Lambda usage đủ điều kiện.
- Phù hợp khi workload có thể đổi instance family, Region hoặc compute platform.

Ví dụ: workload chuyển từ EC2 m7i sang c8g, chuyển Region hoặc chuyển một phần container sang Fargate vẫn có thể tiếp tục hưởng mức giá của Compute Savings Plans nếu usage mới thuộc phạm vi đủ điều kiện.

Compute Savings Plans không trả thay mọi khoản phí liên quan đến ECS/EKS. Với cluster chạy trên EC2, phần EC2 instance có thể được cover; phí control plane, orchestration, load balancer, storage, data transfer và các thành phần khác có quy tắc tính giá riêng. Với EKS trên Fargate, cần phân biệt phí compute Fargate với phí EKS control plane.

### 4.2. EC2 Instance Savings Plans

EC2 Instance Savings Plans yêu cầu chọn:

- Một AWS Region.
- Một EC2 instance family, ví dụ m7i hoặc c8g.
- Mức commitment USD/giờ.
- Term và payment option.

Trong family và Region đã chọn, plan có thể áp dụng cho các size khác nhau, OS khác nhau và tenancy khác nhau theo quy tắc hỗ trợ. Nó phù hợp khi tổ chức chắc chắn duy trì một family trong một Region nhưng vẫn muốn thay đổi kích thước instance.

Ví dụ: m7i.large có thể được đổi thành m7i.2xlarge mà vẫn nằm trong phạm vi EC2 Instance Savings Plan của family m7i ở Region đã cam kết. Nếu chuyển sang c8g hoặc Region khác, usage đó không còn nằm trong phạm vi của plan này.

### 4.3. Database Savings Plans

Database Savings Plans được AWS giới thiệu cho nhóm dịch vụ dữ liệu. Chúng có thể áp dụng cho usage đủ điều kiện của:

- Amazon Aurora và Amazon RDS.
- Amazon DynamoDB.
- Amazon ElastiCache.
- Amazon DocumentDB.
- Amazon Timestream.
- Amazon Neptune.
- Amazon Keyspaces for Apache Cassandra.
- AWS Database Migration Service (DMS).
- Amazon OpenSearch Service.

Database Savings Plans có thể cover usage provisioned và serverless theo phạm vi dịch vụ hỗ trợ. Đối với provisioned instance thế hệ mới nhất, mức giá ưu đãi tự động áp dụng linh hoạt theo engine, instance family, size, Availability Zone và Region. Điều này hữu ích khi tổ chức đang hiện đại hóa database hoặc thay đổi mô hình triển khai.

Ví dụ:

- Chuyển Aurora từ db.r7g sang db.r8g.
- Chuyển workload từ Ireland sang London.
- Hiện đại hóa RDS for Oracle sang Aurora PostgreSQL-Compatible Edition.
- Chuyển một access pattern phù hợp từ RDS sang DynamoDB.
- Chuyển workload từ provisioned sang serverless trong phạm vi được hỗ trợ.

Database Savings Plans hiện có term 1 năm và offering No Upfront. AWS Billing có tính năng Advance Pay riêng nếu tổ chức muốn thanh toán trước. Mức giảm tối đa được công bố lên tới 35%, nhưng mức thực tế phụ thuộc service và usage type.

Không suy luận rằng mọi database feature, storage, backup, I/O hoặc data transfer đều được cover. Kiểm tra usage type cụ thể trong bảng giá Database Savings Plans.

### 4.4. SageMaker AI Savings Plans

SageMaker AI Savings Plans áp dụng cho usage instance đủ điều kiện của Amazon SageMaker AI. Phạm vi linh hoạt theo instance family, size, Region và component như Notebook, Training hoặc Inference theo tài liệu giá hiện hành.

Loại plan này phù hợp với tổ chức có mức sử dụng SageMaker ổn định nhưng có thể thay đổi instance family hoặc chuyển workload giữa các component. Không dùng nó để cover EC2 thông thường hoặc dịch vụ AI khác ngoài phạm vi được liệt kê.

## 5. Term và payment option của Savings Plans

Với Compute, EC2 Instance và SageMaker AI Savings Plans, người mua thường chọn term 1 năm hoặc 3 năm và một trong ba payment option:

| Payment option | Cách thanh toán | Tác động dòng tiền |
|---|---|---|
| No Upfront | Không trả trước; cam kết được tính phí định kỳ | Giảm khoản thanh toán ban đầu, vẫn có nghĩa vụ theo term |
| Partial Upfront | Trả một phần đầu kỳ và phần còn lại theo định kỳ | Cân bằng upfront và recurring |
| All Upfront | Trả toàn bộ cam kết đầu kỳ | Dòng tiền ban đầu lớn, không có recurring payment cho plan đó |

Payment option ảnh hưởng cách phân bổ tiền, không thay đổi phạm vi usage của plan. Một khoản commitment không được sử dụng vẫn là nghĩa vụ thanh toán.

Database Savings Plans có điều kiện term/payment riêng như phần trước; không áp dụng máy móc các lựa chọn của Compute Savings Plans cho Database Savings Plans.

## 6. Reserved Instances là gì?

Reserved Instance là một billing discount gắn với một cấu hình hoặc loại usage trong một thời hạn. Với EC2, cấu hình RI có thể bao gồm instance type/family, platform, scope và tenancy. Với RDS, discount gắn với engine, Region, class, edition và license type theo loại database.

RI không phải là một máy chủ vật lý được AWS cất riêng cho khách hàng. Người dùng vẫn tạo hoặc chạy instance như bình thường. Khi usage khớp với thuộc tính RI, billing engine áp dụng mức giá ưu đãi.

Đặc điểm chung:

- EC2 RI có term 1 năm hoặc 3 năm.
- RDS Reserved DB Instance có term 1 năm hoặc 3 năm, tùy offering.
- Có các lựa chọn No Upfront, Partial Upfront và All Upfront đối với phần lớn RI; availability phụ thuộc dịch vụ và loại instance.
- Billing benefit có thể tiếp tục được tính trong term dù instance tạm dừng hoặc không chạy, theo quy tắc dịch vụ.
- Khi hết term, usage quay về giá On-Demand nếu không có cam kết khác.

Không mua RI chỉ vì console hiển thị số lượng instance đang chạy. Cần xem cả thuộc tính và mức sử dụng theo giờ, account, Region và kế hoạch thay đổi.

## 7. EC2 Reserved Instances: Standard và Convertible

EC2 có hai offering class chính:

| Đặc điểm | Standard RI | Convertible RI |
|---|---|---|
| Mức discount | Thường cao hơn | Thường thấp hơn Standard |
| Exchange sang cấu hình RI khác | Không | Có, theo quy tắc exchange |
| Modify một số thuộc tính | Có, trong phạm vi cho phép | Có |
| Bán trên Reserved Instance Marketplace | Có thể, nếu đáp ứng điều kiện | Không |
| Phù hợp khi | Cấu hình ổn định, ít thay đổi | Cần linh hoạt đổi cấu hình trong cùng Region |

Standard RI không thể exchange sang loại RI khác. Convertible RI có thể exchange sang Convertible RI khác với cấu hình mới như instance family, type, platform hoặc tenancy theo điều kiện AWS. Việc exchange có thể yêu cầu thanh toán true-up nếu giá trị reservation mới cao hơn giá trị còn lại của reservation cũ.

Convertible RI không phải một hợp đồng có thể đổi tự do sang mọi dịch vụ hoặc Region. Region của Convertible RI cố định trong suốt term. Trước khi exchange, kiểm tra giá trị còn lại, term còn lại, số lượng instance nhận được và chi phí phát sinh.

### 7.1. Modify và exchange khác nhau

- **Modify:** thay đổi một số thuộc tính được phép của reservation hiện có, ví dụ scope hoặc Availability Zone, hoặc phân chia/ghép reservation trong trường hợp được hỗ trợ.
- **Exchange:** đổi Convertible RI sang một Convertible RI khác có cấu hình khác, có thể gồm family hoặc platform.

Đừng nhầm việc modify một Standard RI với quyền exchange. Standard RI có thể modify một số thuộc tính nhưng không thể exchange.

### 7.2. Reserved Instance Marketplace

EC2 Standard Regional hoặc Zonal RI đủ điều kiện có thể được bán trên Reserved Instance Marketplace. Convertible RI không thể bán tại Marketplace. Việc bán phụ thuộc thời gian còn lại, lịch sử reservation, payment option và các điều kiện của AWS.

Marketplace không phải lối thoát được bảo đảm khi mua thừa. Giá bán do thị trường quyết định, có thể thấp hơn giá trị kỳ vọng và giao dịch có thể không tìm được người mua.

## 8. EC2 RI scope: Regional và Zonal

EC2 RI có hai scope:

| Thuộc tính | Regional RI | Zonal RI |
|---|---|---|
| Phạm vi | Một Region | Một Availability Zone |
| Billing discount | Có thể áp dụng ở mọi AZ trong Region, nếu usage khớp | Chỉ usage ở AZ đã chọn |
| Capacity reservation | Không | Có, trong AZ chỉ định |
| Instance size flexibility | Có điều kiện | Không |
| Phù hợp khi | Muốn discount linh hoạt giữa AZ | Cần discount và capacity trong một AZ cụ thể |

Giá mua Regional và Zonal RI không khác nhau chỉ vì scope. Khác biệt chính là capacity reservation và flexibility.

### 8.1. Instance size flexibility

Regional RI có thể cung cấp size flexibility trong cùng instance family nếu đáp ứng điều kiện, phổ biến là Linux/Unix với default tenancy. Billing engine dùng normalized units để phân bổ discount giữa các size.

Ví dụ minh họa: nếu một size lớn tương đương hai size nhỏ theo normalization factor, RI của size lớn có thể cover tổng usage tương đương của hai instance nhỏ trong cùng family và Region. Phải kiểm tra platform, tenancy, family và bảng normalization factor hiện hành.

Zonal RI không có AZ flexibility hoặc instance size flexibility. Nó gắn với AZ và instance configuration cụ thể, đồng thời cung cấp capacity reservation trong AZ đó.

### 8.2. RI không thay thế mọi nhu cầu capacity

Regional RI chỉ cung cấp billing discount, không giữ capacity. Nếu tổ chức cần chắc chắn có EC2 capacity trong một AZ, hãy đánh giá Zonal RI hoặc On-Demand Capacity Reservation (ODCR).

ODCR giữ capacity theo cấu hình và AZ cụ thể nhưng không tự tạo discount. Khi instance sử dụng capacity đã reserve, RI hoặc Savings Plans đủ điều kiện vẫn có thể áp dụng discount. Nếu capacity không được sử dụng, ODCR vẫn có thể phát sinh phí theo On-Demand rate.

## 9. Reserved DB Instances của Amazon RDS

RDS Reserved DB Instance là billing discount cho DB instance usage phù hợp, không phải một DB instance vật lý được cấp trước.

Khi mua RDS RI, cần đối chiếu:

- AWS Region.
- Database engine.
- DB instance type/class.
- DB instance size nếu engine không hỗ trợ size flexibility.
- Edition và license type đối với engine có nhiều lựa chọn license.
- Single-AZ hoặc Multi-AZ offering.
- Term và payment option.

Engine version number thường không cần trùng chính xác, nhưng engine, Region và các thuộc tính được yêu cầu phải khớp.

### 9.1. Size flexibility của RDS RI

Một số RDS Reserved DB Instances có thể cover size khác trong cùng instance class type và Region bằng normalized units. Các engine được AWS liệt kê cho size flexibility gồm:

- RDS for Db2.
- RDS for MariaDB.
- RDS for MySQL.
- RDS for Oracle Bring Your Own License.
- RDS for PostgreSQL.

Size flexibility không áp dụng cho RDS for SQL Server và RDS for Oracle License Included theo quy tắc được tài liệu hóa. Aurora có tài liệu reservation riêng; cần kiểm tra engine và offering cụ thể trước khi mua.

Size flexibility không có nghĩa có thể chuyển từ db.r6i sang db.r7g hoặc db.r6id. Phải giữ đúng instance class type mà RI hỗ trợ.

### 9.2. Multi-AZ và normalized units

RDS RI có thể áp dụng theo Single-AZ hoặc Multi-AZ configuration. Khi chuyển giữa các deployment option trong phạm vi size flexibility, số normalized units của các instance/standby phải được tính đúng.

Với Multi-AZ DB cluster có ba instance, không được mặc định một RI Single-AZ cover toàn bộ cluster. Cần xem số lượng reservation và normalized units tương đương theo tài liệu RDS.

### 9.3. Phần chi phí RDS RI không cover

RDS RI chủ yếu giảm phần hourly DB instance usage đủ điều kiện. Nó không tự giảm mọi khoản như:

- Provisioned database storage.
- Backup storage vượt mức miễn phí.
- I/O hoặc IOPS được tính riêng.
- Data transfer.
- Các tính năng hoặc thành phần không thuộc usage type được reservation cover.

Do đó, khi so sánh tổng chi phí, không lấy mức discount của instance hours rồi áp dụng cho toàn bộ hóa đơn database.

### 9.4. Payment option của RDS RI

RDS có No Upfront, Partial Upfront và All Upfront tùy loại offering. No Upfront chỉ có sẵn cho term 1 năm theo tài liệu RDS hiện hành; không phải mọi DB instance class đều cung cấp mọi payment option.

Trước khi mua, kiểm tra offering thực tế trong Region và engine bằng console hoặc lệnh describe-reserved-db-instances-offerings.

## 10. Reservation cho dịch vụ AWS khác

Trong hệ sinh thái AWS, thuật ngữ reservation có thể khác nhau theo dịch vụ:

- ElastiCache có Reserved Nodes.
- Redshift có Reserved Nodes.
- OpenSearch Service có Reserved Instances.
- MemoryDB có reserved node offerings.
- DynamoDB có reserved capacity cho một số mô hình provisioned capacity.

Các offering này có thuộc tính, term, discount, payment option và phạm vi khác nhau. Không áp dụng quy tắc EC2 Standard/Convertible hoặc Regional/Zonal cho chúng nếu tài liệu dịch vụ không định nghĩa như vậy.

Database Savings Plans bao gồm ElastiCache và OpenSearch Service theo danh sách dịch vụ đủ điều kiện hiện hành. Redshift Reserved Nodes có mô hình reservation riêng và không nằm trong danh sách Database Savings Plans được liệt kê ở tài liệu plan types. Không suy diễn rằng mọi dịch vụ có reservation riêng đều được cover; hãy kiểm tra usage type hiện hành trước khi tính commitment.

## 11. So sánh Savings Plans, RI và Capacity Reservation

| Tiêu chí | Savings Plans | EC2 Regional RI | EC2 Zonal RI | On-Demand Capacity Reservation |
|---|---|---|---|---|
| Loại cam kết | USD/giờ | Cấu hình EC2 trong Region | Cấu hình EC2 trong AZ | Capacity trong AZ |
| Term | 1 hoặc 3 năm; Database SP 1 năm | 1 hoặc 3 năm | 1 hoặc 3 năm | Linh hoạt theo loại reservation |
| Discount | Có | Có | Có | Không tự có |
| Reserve capacity | Không | Không | Có | Có |
| Flexibility | Tùy loại SP | Region; size flexibility có điều kiện | Thấp hơn | Theo thuộc tính capacity |
| Áp dụng cho | Dịch vụ đủ điều kiện của từng loại | EC2 usage phù hợp | EC2 usage phù hợp | EC2 instance matching |
| Khi phù hợp | Usage nền ổn định nhưng cấu hình có thể đổi | EC2 family/config ổn định | Cần capacity và discount ở AZ | Cần capacity nhưng muốn giữ On-Demand pricing |

Một workload có thể kết hợp Savings Plans với ODCR. Nếu cần capacity ở một AZ nhưng vẫn muốn discount, có thể dùng ODCR cùng Savings Plans hoặc Regional RI phù hợp. Zonal RI vừa cung cấp discount vừa reserve capacity trong phạm vi của nó.

## 12. Savings Plans và RI được áp dụng vào hóa đơn như thế nào?

Billing engine tự động áp dụng các discount theo quy tắc. Người vận hành cần hiểu thứ tự để tránh mua chồng cam kết cho cùng một usage.

Với EC2:

1. EC2 Reserved Instance discount được áp dụng trước.
2. Savings Plans được áp dụng sau RI.
3. Trong nhóm Savings Plans, EC2 Instance Savings Plans được áp dụng trước Compute Savings Plans do phạm vi hẹp hơn.
4. AWS tính mức tiết kiệm của từng tổ hợp usage đủ điều kiện và áp dụng Savings Plans vào usage có tỷ lệ tiết kiệm cao nhất trước. Nếu tỷ lệ bằng nhau, usage có Savings Plans rate thấp hơn được ưu tiên.
5. Phần usage còn lại sau khi hết commitment được tính On-Demand.

Trong consolidated billing family, Savings Plans trước tiên áp dụng vào usage của account sở hữu plan. Phần commitment còn lại có thể chia sẻ sang account khác nếu discount sharing được bật và thiết lập sharing cho phép.

### 12.1. Savings Plans không cover Spot

Savings Plans không áp dụng cho Spot usage hoặc usage đã được RI cover. Vì vậy, khi lập mô hình cam kết, tách usage On-Demand đủ điều kiện khỏi Spot và các usage đã có discount khác.

### 12.2. Tránh double-count savings

Không cộng phần tiết kiệm tiềm năng của RI recommendation và Savings Plans recommendation như hai khoản độc lập nếu cả hai đang nhắm vào cùng một usage. AWS recommendation có thể giả định inventory cam kết hiện có và loại usage đã được cover. Hãy chạy Purchase Analyzer hoặc so sánh trên cùng một baseline sau khi tính các plan đang sở hữu.

### 12.3. Discount sharing trong AWS Organizations

Với Savings Plans, management account có thể phân tích usage ở payer scope khi discount sharing được bật. Plan được áp dụng cho usage account sở hữu trước, rồi mới đến các account khác theo sharing preference.

Có thể tổ chức chia sẻ theo group hoặc account level tùy cấu hình Billing. Điều này giúp tận dụng usage ổn định trên nhiều account, nhưng cần có governance để tránh một account mua commitment mà account khác thay đổi workload làm giảm utilization.

## 13. Coverage, utilization và savings

Ba chỉ số cần được xem cùng nhau:

- **Coverage:** tỷ lệ usage đủ điều kiện được cover bởi cam kết.
- **Utilization:** tỷ lệ commitment đã được sử dụng.
- **Net savings:** mức tiết kiệm thực tế sau khi tính chi phí cam kết và usage còn trả On-Demand.

Coverage và utilization không giống nhau.

Ví dụ:

- Tổ chức có commitment lớn, usage thấp: utilization thấp; coverage của phần usage còn lại có thể cao.
- Tổ chức có commitment nhỏ, usage cao: utilization có thể gần 100%; coverage vẫn thấp vì phần lớn usage còn On-Demand.
- Một cam kết vừa đủ cho baseline thường hướng tới utilization cao, đồng thời để phần peak biến động chạy On-Demand.

### 13.1. Công thức trực giác

Savings Plans utilization:

\[
Utilization = \frac{Commitment\ used}{Total\ commitment} \times 100\%
\]

Savings Plans coverage:

\[
Coverage = \frac{Eligible\ On\text{-}Demand\ equivalent\ usage\ covered}{Total\ eligible\ On\text{-}Demand\ equivalent\ usage} \times 100\%
\]

Các báo cáo AWS sử dụng cách tính chi tiết theo giá On-Demand equivalent, usage đủ điều kiện và mức cam kết. Dùng số liệu Cost Explorer hoặc CUR để báo cáo chính thức; công thức trên giúp hiểu ý nghĩa.

### 13.2. RI utilization và coverage

RI utilization cho biết reservation được dùng bao nhiêu so với lượng đã mua. RI coverage cho biết bao nhiêu usage đủ điều kiện được cover bởi RI.

Với EC2 size-flexible RI, xem normalized units thay vì chỉ đếm instance-hours. Một instance 2xlarge có thể tiêu thụ gấp đôi normalized units so với xlarge trong cùng family.

## 14. Xác định baseline trước khi cam kết

Cam kết nên dựa trên phần usage ổn định sau khi đã tối ưu tài nguyên. Không nên mua Savings Plans hoặc RI để hợp thức hóa tài nguyên đang chạy thừa.

Quy trình:

1. Thu thập usage theo giờ trong ít nhất 30–60 ngày; nếu có seasonality, cần xem chu kỳ dài hơn.
2. Loại bỏ resource idle, test không cần thiết và usage do cấu hình sai.
3. Right-size compute/database theo CPU, memory, network, I/O và latency.
4. Phân loại workload theo steady-state, seasonal, burst, ephemeral và interruptible.
5. Tách usage đã được cover bởi RI, Savings Plans hoặc Spot.
6. Tính mức usage tối thiểu lặp lại theo giờ, không chỉ lấy trung bình tháng.
7. Xác định phần workload có thể thay đổi Region, family, engine hoặc platform.
8. Chọn mức commitment thấp hơn hoặc bằng baseline có độ tin cậy cao theo risk tolerance.

### 14.1. Tại sao không dùng trung bình tháng?

Giả sử một workload chạy 24/7 nhưng ban đêm giảm còn 30% và ban ngày tăng gấp đôi. Trung bình tháng có thể che giấu nhiều giờ usage thấp. Savings Plans commitment được tiêu thụ theo từng giờ, không thể chuyển phần dư của giờ thấp sang giờ cao.

Phân tích hourly usage giúp nhận diện:

- Minimum hourly baseline.
- Median và percentile hourly usage.
- Peak usage.
- Giờ utilization thấp.
- Ngày nghỉ hoặc mùa thấp điểm.
- Tác động của deployment, maintenance và autoscaling.

### 14.2. Forecast và thay đổi kiến trúc

Lookback period không phải forecast. Nếu sắp migrate EC2 sang Graviton, chuyển Region, thay đổi database engine, tắt một workload hoặc dùng serverless nhiều hơn, dữ liệu lịch sử có thể không còn đại diện cho tương lai.

Hãy mô hình hóa các thay đổi đã được phê duyệt và loại phần usage sẽ biến mất trước khi mua cam kết dài hạn.

## 15. Chọn loại cam kết theo mức độ ổn định

| Tình huống | Lựa chọn cân nhắc | Lý do |
|---|---|---|
| EC2 có thể đổi family, Region hoặc chuyển sang Fargate/Lambda | Compute Savings Plans | Phạm vi compute rộng |
| EC2 ổn định một family và Region, nhưng đổi size/OS/tenancy | EC2 Instance Savings Plans | Discount trong family/Region |
| EC2 cấu hình ổn định, cần capacity trong AZ | Zonal Standard RI | Discount và capacity reservation |
| EC2 ổn định theo Region, không cần capacity guarantee | Regional Standard RI hoặc EC2 Instance Savings Plans | Chọn theo mức discount, flexibility và quản trị |
| EC2 cần đổi family/OS/tenancy trong term | Compute Savings Plans hoặc Convertible RI | Tránh bị khóa cấu hình; Convertible RI cần exchange thủ công |
| RDS ổn định engine, Region và class | RDS Reserved DB Instance | Billing discount theo thuộc tính database |
| Nhiều dịch vụ database, có thể đổi engine/Region/serverless | Database Savings Plans | Phạm vi linh hoạt hơn |
| SageMaker AI có usage instance ổn định | SageMaker AI Savings Plans | Phạm vi đúng cho SageMaker AI |
| Usage chưa rõ hoặc có thể ngừng sớm | On-Demand | Không khóa nghĩa vụ dài hạn |

Không có một loại cam kết phù hợp cho toàn bộ account. Nên chọn theo từng nhóm usage và xem tổng danh mục commitment.

## 16. Chọn term 1 năm hay 3 năm

Term dài hơn thường có mức giá ưu đãi tốt hơn nhưng khóa tổ chức lâu hơn. Term ngắn giảm rủi ro thay đổi kiến trúc và nhu cầu nhưng có thể có discount thấp hơn.

| Yếu tố | 1 năm | 3 năm |
|---|---|---|
| Mức linh hoạt | Cao hơn | Thấp hơn |
| Rủi ro thay đổi workload | Thấp hơn | Cao hơn |
| Mức discount | Thường thấp hơn | Thường cao hơn |
| Dòng tiền | Nghĩa vụ ngắn hơn | Nghĩa vụ dài hơn |
| Phù hợp | Nền tảng đang thay đổi, forecast chưa chắc | Workload ổn định, có kế hoạch dài hạn |

Đừng chọn 3 năm chỉ vì phần trăm discount cao hơn. So sánh NPV, rủi ro underutilization, chi phí cơ hội và kế hoạch migration trong term.

## 17. Chọn payment option và phân tích dòng tiền

No Upfront, Partial Upfront và All Upfront thay đổi thời điểm trả tiền và effective rate.

Khi so sánh, cần:

- Quy đổi upfront và recurring payment về cùng kỳ phân tích.
- Tính cost of capital hoặc discount rate của doanh nghiệp.
- Xem khả năng thanh khoản và budget theo quý/năm.
- Tính phần commitment có thể không sử dụng.
- Đối chiếu thời điểm ghi nhận chi phí với chính sách kế toán nội bộ.

### 17.1. Effective hourly cost

Với RI có upfront, có thể quy đổi khoản upfront thành chi phí phân bổ theo giờ trong term để so sánh công bằng:

\[
Effective\ hourly\ cost =
\frac{Upfront\ payment}{Term\ hours}
+ Recurring\ hourly\ charge
\]

Đây là cách nhìn kinh tế đơn giản. Báo cáo kế toán và amortization trong Cost Explorer/CUR có thể dùng cách phân bổ khác theo cấu hình và kỳ báo cáo.

### 17.2. Break-even

Break-even là thời điểm savings tích lũy bù được chi phí upfront hoặc chênh lệch so với phương án On-Demand. Nếu workload có thể ngừng trước break-even, commitment có thể làm tăng tổng chi phí.

Cost Explorer reservation recommendations có thể hiển thị break-even months cho một số reservation. Hãy dùng dữ liệu đó như ước tính dựa trên usage lịch sử và kiểm tra lại với forecast.

## 18. Dùng AWS Cost Explorer và Purchase Analyzer

AWS Cost Explorer cung cấp recommendation và báo cáo để phân tích cam kết.

### 18.1. Savings Plans Recommendations

Trong Billing and Cost Management:

1. Mở Cost Management.
2. Chọn Savings Plans → Recommendations.
3. Refresh recommendations để cập nhật usage và inventory.
4. Chọn Savings Plans type.
5. Chọn term và payment option.
6. Chọn lookback period 7, 30 hoặc 60 ngày.
7. Chọn payer scope hoặc linked account scope nếu có quyền.
8. Xem recommended commitment, estimated savings, coverage và utilization.

Recommendations được tính từ usage lịch sử và inventory cam kết hiện có. AWS không dự báo usage tương lai và không tự tính các purchase đã queue/scheduled như một forecast. Nếu vừa thay đổi workload, hãy chọn lookback period sau thay đổi hoặc dùng Purchase Analyzer với kịch bản tùy chỉnh.

### 18.2. Purchase Analyzer

Purchase Analyzer cho phép thử nhiều giả định:

- Savings Plans type.
- Payer hoặc linked account.
- Term 1 hoặc 3 năm (Database Savings Plans theo term hỗ trợ).
- Payment option.
- Lookback period trong phạm vi công cụ hỗ trợ.
- Exclude plan sắp hết hạn.
- Commitment theo recommended, target coverage hoặc custom hourly amount.

Sau khi chạy, so sánh ba khía cạnh:

1. Estimated monthly savings.
2. Average hourly coverage increase.
3. Average hourly utilization.

Không chọn recommendation chỉ dựa trên estimated monthly savings. Nếu utilization dự kiến thấp, hãy giảm commitment hoặc kiểm tra lại workload baseline.

### 18.3. RI Recommendations

Trong Cost Explorer, chọn Reservations → Recommendations. Có thể chọn service, term, offering class, payment option và lookback period. Recommendations có thể áp dụng cho EC2, RDS, ElastiCache, OpenSearch, Redshift, MemoryDB và DynamoDB theo loại reservation.

RI recommendations cũng dựa trên usage lịch sử, không dự báo sự thay đổi trong tương lai. Kiểm tra Region, engine, class, platform, tenancy, scope và size flexibility trước khi mua.

## 19. Theo dõi utilization và coverage

Sau khi mua, cần xem định kỳ:

- Savings Plans utilization report.
- Savings Plans coverage report.
- RI utilization report.
- RI coverage report.
- Cost and Usage Report (CUR) hoặc Data Exports.
- Chi phí thực tế theo linked account, service, Region và usage type.

### 19.1. Dấu hiệu mua thiếu

- Coverage thấp kéo dài.
- On-Demand eligible spend vẫn cao và ổn định.
- Utilization gần 100%.
- Workload baseline tăng và duy trì trong nhiều tuần.
- Recommendation đề xuất thêm commitment có utilization dự kiến cao.

### 19.2. Dấu hiệu mua thừa

- Utilization thấp kéo dài.
- Workload đã scale down, migrate hoặc terminate.
- RI matching usage giảm sau thay đổi family, engine hoặc Region.
- Chi phí unused commitment tăng.
- Một phần commitment chỉ được dùng trong mùa cao điểm.

Đừng mua thêm chỉ vì coverage thấp trong một ngày peak. Cũng đừng giữ cam kết không sử dụng mà không có kế hoạch xử lý.

### 19.3. Budget và cảnh báo

Có thể tạo Savings Plans budget theo utilization hoặc coverage threshold. Thiết lập alert khi utilization giảm dưới ngưỡng hoặc khi plan sắp hết hạn. Với RI, theo dõi expiration, coverage và unused hours.

Metrics và báo cáo có thể có độ trễ cập nhật. Không dùng một cảnh báo duy nhất làm căn cứ thay đổi commitment; đối chiếu với usage, deployment và lịch sự kiện.

## 20. Governance cho danh mục cam kết

Một tổ chức có nhiều account cần quy trình quản trị rõ:

- **Owner:** ai chịu trách nhiệm cho commitment theo workload hoặc account?
- **Approver:** ai có quyền duyệt nghĩa vụ tài chính 1–3 năm?
- **Budget:** khoản upfront và recurring được ghi nhận ở đâu?
- **Scope:** commitment thuộc payer account hay linked account?
- **Sharing:** có bật sharing trong Organizations và account nào được nhận benefit?
- **Renewal:** ai đánh giá plan sắp hết hạn?
- **Risk:** ngưỡng utilization tối thiểu và mức exposure được chấp nhận là gì?
- **Evidence:** recommendation, analyzer output và quyết định mua được lưu ở đâu?

### 20.1. Approval policy

Một purchase request nên có:

1. Workload và owner.
2. Loại Savings Plans/RI.
3. Hourly commitment hoặc reservation attributes.
4. Term và payment option.
5. Baseline usage và lookback period.
6. Expected utilization/coverage.
7. Estimated savings và break-even.
8. Kịch bản workload giảm hoặc thay đổi.
9. Người phê duyệt và ngày review tiếp theo.

Không cho phép mọi team tự mua commitment dài hạn mà không có visibility ở payer level. Điều này có thể dẫn đến nhiều plan chồng lấn, account này mua thừa trong khi account khác vẫn trả On-Demand.

### 20.2. Expiration calendar

Lập lịch hết hạn cho từng plan và RI. Trước ngày hết hạn:

- Xác định workload còn tồn tại không.
- Kiểm tra family, Region, engine và architecture đã thay đổi chưa.
- So sánh renew, đổi loại cam kết hoặc quay lại On-Demand.
- Refresh recommendation và Purchase Analyzer.
- Queue purchase mới nếu cần continuity.

Không tự động gia hạn chỉ vì reservation cũ từng có utilization cao. Nhu cầu có thể đã thay đổi.

## 21. Ví dụ tính commitment cho một workload EC2

Một workload chạy EC2 liên tục có hourly On-Demand equivalent như sau (số liệu giả lập):

| Khoảng thời gian | On-Demand equivalent |
|---|---:|
| Giờ thấp điểm | 80 USD/giờ |
| Giờ bình thường | 100 USD/giờ |
| Giờ cao điểm | 150 USD/giờ |

Đội vận hành phân tích 60 ngày và xác định baseline ổn định là 80 USD/giờ. Sau khi chọn Compute Savings Plans, mức giá cho cấu hình hiện tại tương đương 60 USD/giờ.

Đội thiết kế cân nhắc:

- Cam kết 60 USD/giờ để cover baseline.
- Giữ phần tăng từ 80 lên 150 USD/giờ trên On-Demand.
- Không cam kết theo peak vì mức peak chỉ xuất hiện trong một số giờ.

Nếu usage giảm xuống mức có Savings Plans rate 45 USD/giờ, utilization của commitment 60 USD/giờ là 75%. Nếu usage tăng, commitment được dùng hết và phần còn lại tiếp tục tính On-Demand.

Điểm cần lưu ý:

- 60 USD/giờ là Savings Plans rate commitment, không phải On-Demand equivalent.
- Mức baseline phải được kiểm chứng theo từng giờ.
- Nếu workload migrate khỏi EC2 sang dịch vụ không thuộc Compute Savings Plans, phải đánh giá lại usage đủ điều kiện.
- Sau purchase, không thể hủy hoặc giảm commitment giữa term.

## 22. Ví dụ chọn EC2 RI hay EC2 Instance Savings Plans

Một workload có 20 instance m7i.large Linux ở ap-southeast-1, chạy ổn định quanh năm.

Hai phương án:

**Phương án A – Regional Standard RI**

- Phù hợp nếu cấu hình family/platform/tenancy ổn định.
- Có thể áp dụng giữa các AZ trong Region.
- Với điều kiện size flexibility được hỗ trợ, có thể cover size khác trong cùng family.
- Không reserve capacity vì scope là Regional.

**Phương án B – EC2 Instance Savings Plans**

- Chỉ cam kết family m7i trong Region đã chọn.
- Có thể đổi size, OS hoặc tenancy trong phạm vi được hỗ trợ.
- Không reserve capacity.
- Không cần quản lý từng RI hoặc exchange.

Quyết định phụ thuộc:

- Cấu hình có ổn định không?
- Có cần capacity reservation không?
- Workload có khả năng đổi family không?
- Discount thực tế sau khi so sánh offering là bao nhiêu?
- Quy trình quản trị hiện tại có phụ thuộc RI không?

Nếu cần capacity trong một AZ cụ thể, xem Zonal RI hoặc ODCR. Nếu có khả năng chuyển family, Compute Savings Plans có thể linh hoạt hơn EC2 Instance Savings Plans.

## 23. Ví dụ database: RDS RI hay Database Savings Plans

Một tổ chức đang chạy PostgreSQL trên RDS ở hai Region. Trong 12 tháng tới, nhóm dữ liệu có thể:

- Nâng instance class.
- Chuyển một workload sang Aurora PostgreSQL.
- Chuyển một workload analytics sang DynamoDB hoặc OpenSearch.
- Dùng serverless cho môi trường có tải không đều.

RDS Reserved DB Instance có thể có discount tốt cho usage ổn định nhưng gắn với Region, engine và các thuộc tính reservation. Size flexibility chỉ áp dụng cho engine/class được hỗ trợ.

Database Savings Plans có phạm vi linh hoạt hơn giữa nhiều database service, engine, Region và usage serverless/provisioned đủ điều kiện. Tuy nhiên, term và payment option hiện hành khác với Compute Savings Plans.

Nhóm cần:

1. Tách database usage theo usage type và service.
2. Xác định phần provisioned/serverless đủ điều kiện.
3. Đối chiếu RDS RI recommendations với Database Savings Plans recommendation.
4. Mô hình hóa migration đã có lịch.
5. Chọn mức commitment theo baseline sau migration hoặc phần chưa thay đổi.
6. Theo dõi coverage và utilization sau khi mua.

Không mua RDS RI cho workload dự kiến bị migrate sớm chỉ vì chiết khấu hiện tại cao hơn.

## 24. Các sai lầm thường gặp

1. **Cam kết theo tổng chi tiêu tháng:** bỏ qua biến động theo giờ.
2. **Mua trước khi right-size:** khóa chi phí của tài nguyên đang dùng thừa.
3. **Dùng recommendation như forecast:** AWS recommendation dựa trên lịch sử.
4. **Nhầm commitment với On-Demand spend:** Savings Plans commitment dùng Savings Plans rate.
5. **Mua quá sát peak:** nhiều giờ thấp điểm sẽ làm utilization giảm.
6. **Nhầm Savings Plans với capacity reservation:** Savings Plans không giữ capacity.
7. **Nhầm Regional RI với Zonal RI:** chỉ Zonal RI reserve capacity trong AZ.
8. **Nhầm Standard và Convertible RI:** Standard không exchange; Convertible có điều kiện exchange.
9. **Cho rằng mọi RDS RI đều size-flexible:** SQL Server và Oracle License Included không có size flexibility theo quy tắc nêu trên.
10. **Cho rằng RDS RI giảm toàn bộ database bill:** storage, backup, I/O và data transfer có thể tính riêng.
11. **Coi No Upfront là không có cam kết:** vẫn phải trả theo term.
12. **Cộng dồn recommendation của RI và Savings Plans:** có thể double-count usage.
13. **Không xét Organizations sharing:** commitment có thể áp dụng sang account khác theo sharing preference.
14. **Bỏ qua kế hoạch migration:** usage đủ điều kiện có thể biến mất hoặc đổi phạm vi.
15. **Không theo dõi expiry:** hết term thì usage quay lại On-Demand nếu không có cam kết mới.
16. **Dựa vào Marketplace để thoát RI:** không bảo đảm bán được hoặc thu hồi đủ tiền.
17. **Chỉ nhìn phần trăm discount:** bỏ qua upfront, cash flow, utilization và risk.

## 25. Thực hành: lập kế hoạch cam kết trong Cost Explorer

### 25.1. Thu thập baseline

1. Mở Billing and Cost Management.
2. Mở Cost Explorer.
3. Chọn khoảng thời gian ít nhất 30–60 ngày; với workload có seasonality, xem thêm chu kỳ dài hơn.
4. Group theo service, Region, linked account và usage type.
5. Kiểm tra giờ thấp điểm, peak, ngày nghỉ và thay đổi sau deployment.
6. Loại usage đã được cover bởi RI, Savings Plans hoặc Spot khi xác định phần còn đủ điều kiện.

### 25.2. Mở Savings Plans Recommendations

1. Chọn Savings Plans → Recommendations.
2. Refresh dữ liệu.
3. Chọn loại Savings Plans.
4. Chọn term và payment option.
5. Thử lookback 7, 30 và 60 ngày.
6. So sánh recommended commitment, coverage và utilization.
7. Ghi lại phương án có mức commitment thấp hơn nếu usage biến động lớn.

### 25.3. Dùng Purchase Analyzer

1. Chọn Savings Plans → Purchase Analyzer.
2. Chọn payer hoặc linked account scope.
3. Chọn plan type, term và payment option.
4. Chọn lookback và loại trừ plan sắp hết hạn nếu cần.
5. Chạy Recommended, Target coverage và Custom commitment.
6. So sánh cost, coverage và utilization theo giờ.
7. Lưu kết quả phân tích vào purchase request.

### 25.4. Đánh giá RI

1. Chọn Reservations → Recommendations.
2. Chọn service, Region, term và offering class.
3. Đối chiếu instance type, engine, platform, tenancy và scope.
4. Xem expected utilization, break-even months, upfront cost và recurring cost.
5. Kiểm tra size flexibility và normalized units.
6. So sánh với Savings Plans cho cùng usage.

Không thực hiện purchase chỉ để hoàn thành bài lab. Dùng dữ liệu giả lập hoặc chỉ xem recommendations trong account test.

## 26. Kiểm tra bằng AWS CLI

Các lệnh sau giúp kiểm tra inventory và báo cáo. Chúng chỉ đọc dữ liệu, không mua hoặc thay đổi commitment.

Liệt kê EC2 Reserved Instances đang active:

~~~bash
aws ec2 describe-reserved-instances --filters Name=state,Values=active
~~~

Liệt kê RDS Reserved DB Instances:

~~~bash
aws rds describe-reserved-db-instances
~~~

Lấy Savings Plans utilization report theo tháng:

~~~bash
aws ce get-savings-plans-utilization --time-period Start=2026-10-01,End=2026-11-01 --granularity MONTHLY
~~~

Lấy Savings Plans coverage report:

~~~bash
aws ce get-savings-plans-coverage --time-period Start=2026-10-01,End=2026-11-01 --granularity MONTHLY
~~~

Lấy RI utilization report:

~~~bash
aws ce get-reservation-utilization --time-period Start=2026-10-01,End=2026-11-01 --granularity MONTHLY
~~~

Lấy RI coverage report:

~~~bash
aws ce get-reservation-coverage --time-period Start=2026-10-01,End=2026-11-01 --granularity MONTHLY
~~~

Các ngày ví dụ dùng định dạng UTC và khoảng thời gian End là exclusive theo API Cost Explorer. Tùy quyền, dữ liệu Billing và cấu hình account, kết quả có thể khác nhau. Dùng AWS CLI version hiện hành và kiểm tra help của lệnh trước khi đưa vào automation.

## 27. Tình huống cần xem xét lại commitment

### 27.1. Workload scale down

Nếu workload giảm đáng kể, kiểm tra utilization theo giờ và chi phí unused commitment. Với Savings Plans, không thể giảm commitment đang hoạt động; cần điều chỉnh danh mục cam kết mới và tránh mua thêm. Với RI, xem khả năng modify/exchange hoặc Marketplace nếu offering đủ điều kiện.

### 27.2. Chuyển Region

Compute Savings Plans có thể tiếp tục áp dụng EC2 usage đủ điều kiện ở Region mới. EC2 Instance Savings Plans gắn với Region đã chọn. Regional EC2 RI cũng gắn với Region; Convertible RI không thể exchange sang Region khác. RDS RI gắn với Region. Database Savings Plans có thể linh hoạt Region theo usage được hỗ trợ.

### 27.3. Chuyển EC2 sang Fargate hoặc Lambda

Compute Savings Plans có thể tiếp tục áp dụng cho EC2, Fargate và Lambda usage đủ điều kiện. EC2 Instance Savings Plans chỉ áp dụng EC2 trong family/Region đã chọn. Nếu có kế hoạch chuyển platform, ưu tiên phân tích Compute Savings Plans trước khi cam kết vào một family cụ thể.

### 27.4. Chuyển engine database

RDS RI gắn với engine và Region. Database Savings Plans có thể giữ discount khi chuyển giữa các database service/engine đủ điều kiện. Kiểm tra ngày migration, usage mới và phần commitment còn lại trước khi mua.

## 28. Checklist trước khi mua

- [ ] Đã right-size compute/database.
- [ ] Đã phân loại steady-state, peak, seasonal và interruptible workload.
- [ ] Đã phân tích hourly usage, không chỉ monthly average.
- [ ] Đã loại usage đã được cover bởi RI/SP hoặc Spot.
- [ ] Đã xác định loại Savings Plans hoặc RI phù hợp.
- [ ] Đã kiểm tra Region, family, engine, platform, tenancy, scope và size flexibility.
- [ ] Đã xem capacity reservation có thực sự cần thiết không.
- [ ] Đã chọn term theo mức ổn định của workload.
- [ ] Đã so sánh No/Partial/All Upfront và dòng tiền.
- [ ] Đã tính commitment theo Savings Plans rate, không nhầm với On-Demand spend.
- [ ] Đã xem utilization, coverage, break-even và unused commitment.
- [ ] Đã kiểm tra migration/modernization roadmap trong term.
- [ ] Đã đánh giá payer/linked account và discount sharing.
- [ ] Đã có approval của owner và người chịu trách nhiệm ngân sách.
- [ ] Đã lập lịch theo dõi utilization, coverage và expiry.

## 29. Bài tập tự kiểm tra

### Câu 1

Savings Plans cam kết theo loại đơn vị nào?

**Đáp án:** Theo một mức chi tiêu đủ điều kiện tính bằng USD mỗi giờ ở Savings Plans rate, trong term đã chọn.

### Câu 2

Compute Savings Plans có thể áp dụng cho những dịch vụ compute nào?

**Đáp án:** EC2, AWS Fargate và AWS Lambda usage đủ điều kiện.

### Câu 3

EC2 Instance Savings Plans có thể áp dụng cho instance family khác trong Region không?

**Đáp án:** Không. Plan gắn với family và Region đã chọn; có flexibility về size, OS và tenancy trong phạm vi hỗ trợ.

### Câu 4

Database Savings Plans có lợi thế gì khi tổ chức thay đổi engine hoặc database service?

**Đáp án:** Chúng có phạm vi linh hoạt giữa nhiều database service và usage provisioned/serverless đủ điều kiện, không khóa cứng vào một engine như RDS RI truyền thống.

### Câu 5

Nếu cam kết Savings Plans là 60 USD/giờ nhưng usage chỉ tiêu thụ 45 USD theo Savings Plans rate, điều gì xảy ra?

**Đáp án:** Utilization là 75%. Phần commitment không dùng vẫn bị tính phí và không chuyển sang giờ tiếp theo.

### Câu 6

Standard EC2 RI có thể exchange sang Convertible RI không?

**Đáp án:** Không. Standard RI có thể modify một số thuộc tính nhưng không thể exchange.

### Câu 7

EC2 Regional RI có reserve capacity trong một AZ không?

**Đáp án:** Không. Regional RI chỉ cung cấp billing discount trong Region. Zonal RI mới reserve capacity trong AZ cụ thể.

### Câu 8

Khi nào EC2 Regional RI có size flexibility?

**Đáp án:** Khi đáp ứng điều kiện như cùng instance family, Linux/Unix và default tenancy theo quy tắc AWS. Zonal RI không có size flexibility.

### Câu 9

RDS RI có giảm phí storage và backup không?

**Đáp án:** Không mặc định. RDS RI chủ yếu giảm hourly DB instance usage đủ điều kiện; storage, backup, I/O và data transfer có thể tính riêng.

### Câu 10

No Upfront có nghĩa là không phải cam kết thanh toán trong term không?

**Đáp án:** Không. No Upfront chỉ bỏ khoản thanh toán đầu kỳ; nghĩa vụ thanh toán theo term vẫn tồn tại.

### Câu 11

AWS áp dụng EC2 RI hay Savings Plans trước?

**Đáp án:** EC2 RI được áp dụng trước Savings Plans. Trong nhóm Savings Plans, EC2 Instance Savings Plans được áp dụng trước Compute Savings Plans.

### Câu 12

Savings Plans có áp dụng cho Spot usage không?

**Đáp án:** Không. Savings Plans không áp dụng cho Spot usage hoặc usage đã được RI cover.

### Câu 13

Vì sao không nên dùng Savings Plans recommendation như forecast?

**Đáp án:** Recommendation dựa trên usage lịch sử và inventory hiện tại, không dự báo workload tương lai hoặc mọi purchase đã queue. Cần điều chỉnh theo migration và kế hoạch kinh doanh.

### Câu 14

Nếu cần giữ capacity EC2 trong một AZ nhưng muốn discount, có những lựa chọn nào?

**Đáp án:** Có thể cân nhắc Zonal RI hoặc ODCR kết hợp với Savings Plans/Regional RI đủ điều kiện. Cần phân biệt capacity benefit và billing discount.

### Câu 15

Một workload database dự kiến chuyển từ RDS sang Aurora trong 4 tháng. Nên làm gì trước khi mua RDS RI 3 năm?

**Đáp án:** Mô hình hóa migration và phần usage còn lại; so sánh Database Savings Plans, term ngắn hơn hoặc On-Demand. Không khóa commitment dài hạn vào usage dự kiến biến mất.

## 30. Tài liệu tham khảo chính thức

- [AWS Savings Plans – What are Savings Plans?](https://docs.aws.amazon.com/savingsplans/latest/userguide/what-is-savings-plans.html)
- [AWS Savings Plans – Types of Savings Plans](https://docs.aws.amazon.com/savingsplans/latest/userguide/plan-types.html)
- [AWS Savings Plans – Compute Savings Plans and Reserved Instances](https://docs.aws.amazon.com/savingsplans/latest/userguide/sp-ris.html)
- [AWS Savings Plans – How Savings Plans apply to usage](https://docs.aws.amazon.com/savingsplans/latest/userguide/sp-applying.html)
- [AWS Savings Plans – Services eligible for Savings Plans benefits](https://docs.aws.amazon.com/savingsplans/latest/userguide/sp-services.html)
- [AWS Savings Plans – Recommendations calculations](https://docs.aws.amazon.com/savingsplans/latest/userguide/sp-rec-calculations.html)
- [AWS Savings Plans – Purchase Analyzer](https://docs.aws.amazon.com/savingsplans/latest/userguide/sp-purchase-analysis.html)
- [AWS Savings Plans – Purchasing a custom commitment](https://docs.aws.amazon.com/savingsplans/latest/userguide/purchase-sp-direct.html)
- [AWS Savings Plans – Savings Plans FAQ](https://aws.amazon.com/savingsplans/faqs/)
- [Amazon EC2 – Reserved Instances overview](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-reserved-instances.html)
- [Amazon EC2 – Standard and Convertible Reserved Instances](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/reserved-instances-types.html)
- [Amazon EC2 – Regional and Zonal Reserved Instances](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/reserved-instances-scope.html)
- [Amazon EC2 – How RI billing works](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/concepts-reserved-instances-application.html)
- [Amazon EC2 – Capacity Reservation pricing and billing](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/capacity-reservations-pricing-billing.html)
- [Amazon RDS – Reserved DB instances](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_WorkingWithReservedDBInstances.html)
- [AWS Cost Management – Reservation recommendations](https://docs.aws.amazon.com/cost-management/latest/userguide/ri-recommendations.html)
- [AWS Cost Management – Cost Explorer default reports](https://docs.aws.amazon.com/cost-management/latest/userguide/ce-default-reports.html)

Mức discount, offering, usage type, term và quota có thể thay đổi theo dịch vụ, Region và thời điểm. Trước khi mua, đối chiếu trang pricing và offering hiện hành trong account/Region cụ thể.


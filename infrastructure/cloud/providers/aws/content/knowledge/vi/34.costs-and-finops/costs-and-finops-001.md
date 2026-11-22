# Mô hình tính phí và các nguồn chi phí phổ biến

AWS cung cấp nhiều dịch vụ theo mô hình trả tiền theo mức sử dụng. Cách tính này giúp nhóm kỹ thuật bắt đầu với quy mô nhỏ và tăng tài nguyên khi nhu cầu thay đổi, nhưng hóa đơn có thể trở nên khó dự đoán nếu không hiểu đơn vị tính phí của từng dịch vụ. Một EC2 instance thường phát sinh phí theo thời gian chạy và loại cấu hình; Amazon S3 tính theo dung lượng, request và một số thao tác dữ liệu; NAT Gateway tính theo thời gian tồn tại và lượng dữ liệu xử lý; CloudWatch có thể phát sinh phí từ log ingestion, lưu trữ, metric và truy vấn.

Vì vậy, ước tính chi phí AWS không chỉ là nhân số máy chủ với đơn giá. Cần hiểu workload tạo ra bao nhiêu compute, storage, request, network traffic, log, backup và hoạt động quản trị. Cần phân biệt chi phí cố định theo thời gian với chi phí biến đổi theo mức sử dụng, đồng thời xác định tài khoản, Region, môi trường và nhóm chịu trách nhiệm cho từng khoản.

Trong hệ sinh thái CLOUD_PROVIDERS_AWS, người thiết kế cần chọn dịch vụ phù hợp, vận hành an toàn, có khả năng giám sát và phục hồi, đồng thời kiểm soát chi phí. Bài học này trình bày các mô hình tính phí phổ biến, những nguồn chi phí thường gặp và cách xây dựng quy trình FinOps để biến dữ liệu billing thành quyết định kỹ thuật và kinh doanh.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích mô hình pay-as-you-go và các yếu tố ảnh hưởng đến giá AWS.
- Phân biệt On-Demand, Savings Plans, Reserved Instances, Spot và các lựa chọn tenancy.
- Nhận diện nguồn chi phí trong compute, storage, networking, database, serverless, observability, security và backup.
- Ước tính chi phí dựa trên đơn vị tính phí, mức sử dụng và thời gian vận hành.
- Phân biệt chi phí theo tài khoản, Region, dịch vụ, usage type và cost allocation tag.
- Sử dụng AWS Pricing Calculator, Cost Explorer, AWS Budgets, Cost and Usage Reports/Data Exports và Cost Anomaly Detection.
- Đề xuất cách tối ưu chi phí mà vẫn đáp ứng hiệu năng, bảo mật, độ sẵn sàng và RPO/RTO.
- Thiết lập vòng lặp FinOps gồm quan sát, phân bổ, tối ưu và vận hành liên tục.

## 2. Nền tảng của mô hình tính phí AWS

### 2.1. Pay-as-you-go

Pay-as-you-go là mô hình trả tiền theo lượng tài nguyên hoặc hoạt động thực tế đã sử dụng. Thay vì phải mua trước một trung tâm dữ liệu với công suất cố định, tổ chức có thể tạo tài nguyên theo nhu cầu và trả phí theo cách dịch vụ đo lường.

Lợi ích:

- Giảm vốn đầu tư ban đầu cho phần cứng.
- Tăng hoặc giảm quy mô theo tải.
- Thử nghiệm dịch vụ mới mà không cần mua thiết bị.
- Có thể phân bổ chi phí theo workload, tài khoản hoặc môi trường.

Mô hình này không có nghĩa mọi tài nguyên đều tự động dừng khi không dùng. Một EC2 instance vẫn tính phí khi đang chạy dù ứng dụng không có request; EBS volume vẫn phát sinh phí lưu trữ khi instance đã stop; NAT Gateway và load balancer vẫn có thể tính phí theo thời gian tồn tại. Tổ chức cần xác định vòng đời tài nguyên và tự động dọn dẹp những gì không còn cần thiết.

### 2.2. Đơn vị tính phí

Mỗi dịch vụ đo lường mức sử dụng theo các đơn vị riêng. Một hóa đơn có thể chứa:

| Nhóm đơn vị | Ví dụ | Câu hỏi cần trả lời |
|---|---|---|
| Thời gian | Instance-hour, vCPU-hour, GB-month | Tài nguyên tồn tại hoặc chạy trong bao lâu? |
| Dung lượng | GB-month, TB-month | Dữ liệu được lưu bao nhiêu và trong thời gian nào? |
| Request | API request, read/write request | Có bao nhiêu thao tác được gọi? |
| Dữ liệu xử lý | GB processed, GB scanned | Dịch vụ đã xử lý hoặc truy vấn bao nhiêu dữ liệu? |
| Dữ liệu truyền | GB transferred | Dữ liệu đi qua AZ, Region, Internet hoặc edge như thế nào? |
| Công suất được cấp | Provisioned IOPS, throughput, capacity unit | Tổ chức đã đặt trước mức hiệu năng nào? |
| Đối tượng/đơn vị quản lý | Secret-month, metric, rule, resource item | Có bao nhiêu đối tượng được quản lý? |

Một dịch vụ có thể kết hợp nhiều đơn vị. Ví dụ, một database có thể tính phí compute theo thời gian, storage theo GB-month, I/O theo cấu hình hoặc mức sử dụng, backup theo dung lượng và data transfer theo luồng dữ liệu.

### 2.3. Công thức ước tính cơ bản

Một mô hình khái quát:

\[
\text{Chi phí} \approx \sum_i (\text{Lượng sử dụng}_i \times \text{Đơn giá}_i) + \text{Phí cố định} - \text{Ưu đãi}
\]

Trong thực tế, cần cộng thêm các yếu tố như data transfer, request, license, thuế và các khoản điều chỉnh trên hóa đơn. Đơn giá phụ thuộc Region, loại dịch vụ, cấu hình, operating system, tenancy, purchase option, tier sử dụng và thời điểm áp dụng.

Ví dụ một ứng dụng chạy trên EC2 có thể phát sinh:

1. Compute cho instance theo giờ hoặc giây tùy loại hệ điều hành và cách tính của dịch vụ.
2. EBS volume và snapshot.
3. Elastic IP hoặc địa chỉ IPv4 công khai theo chính sách tính phí hiện hành.
4. Data transfer ra Internet hoặc qua AZ/Region.
5. Load balancer và NAT Gateway.
6. CloudWatch Logs, metric, alarm và tracing.
7. Backup và các dịch vụ bảo mật liên quan.

Do đó, chỉ xem dòng EC2 trong Billing sẽ không phản ánh toàn bộ chi phí để vận hành ứng dụng.

### 2.4. Những yếu tố làm thay đổi đơn giá

Khi so sánh hai cấu hình, cần kiểm tra:

- **Region:** giá compute, storage, network và dịch vụ quản lý có thể khác nhau giữa các Region.
- **Availability Zone:** một số luồng dữ liệu liên AZ có phí truyền dữ liệu.
- **Loại tài nguyên:** CPU, memory, storage type, throughput, IOPS, network performance và kích thước.
- **Operating system và license:** Windows, SQL Server hoặc phần mềm có license đi kèm có thể làm thay đổi giá.
- **Tenancy:** shared tenancy, Dedicated Instances hoặc Dedicated Hosts có mô hình tính phí khác nhau.
- **Purchase option:** On-Demand, Spot, Savings Plans hoặc Reserved Instances.
- **Mức sử dụng:** tier, free allowance hoặc volume discount có thể ảnh hưởng đơn giá hiệu dụng.
- **Thời hạn và cam kết:** một số ưu đãi yêu cầu cam kết thời hạn hoặc mức chi tiêu.

Không nên so sánh giá hai dịch vụ chỉ bằng con số đơn giá đầu tiên nhìn thấy. Hãy so sánh tổng chi phí cho cùng một workload, cùng yêu cầu hiệu năng và cùng thời gian vận hành.

## 3. Các mô hình mua và cam kết sử dụng compute

### 3.1. On-Demand

On-Demand cho phép sử dụng compute mà không cần cam kết dài hạn. Tổ chức trả phí theo mức sử dụng của tài nguyên.

Phù hợp khi:

- Workload mới, chưa có dữ liệu tải đủ tin cậy.
- Môi trường phát triển, kiểm thử hoặc demo không chạy liên tục.
- Nhu cầu thay đổi mạnh và khó dự báo.
- Cần quyền linh hoạt để thay đổi instance family hoặc Region.

Ưu điểm là dễ bắt đầu và không bị ràng buộc cam kết. Nhược điểm là chi phí đơn vị thường cao hơn lựa chọn có cam kết khi workload chạy ổn định lâu dài.

### 3.2. Savings Plans

Savings Plans là cam kết chi tiêu compute theo mức USD mỗi giờ trong thời hạn thường gặp là một hoặc ba năm. Đổi lại, phần sử dụng đủ điều kiện được tính theo mức giá ưu đãi. Nếu mức sử dụng đủ điều kiện thấp hơn cam kết, tổ chức vẫn trả phần cam kết theo điều khoản của plan.

Các nhóm chính:

- **Compute Savings Plans:** linh hoạt hơn về loại compute đủ điều kiện, có thể áp dụng cho EC2, AWS Fargate và AWS Lambda theo quy tắc của chương trình.
- **EC2 Instance Savings Plans:** mức ưu đãi gắn với instance family trong một Region, đổi lại mức linh hoạt thấp hơn.

Savings Plans phù hợp với baseline compute có thể dự đoán. Trước khi mua, cần phân tích lịch sử sử dụng, mức tải tối thiểu, kế hoạch thay đổi kiến trúc và thời gian cam kết. Không nên cam kết toàn bộ peak capacity nếu phần tải đó chỉ xuất hiện trong thời gian ngắn.

### 3.3. Reserved Instances

Reserved Instances (RI) là lựa chọn định giá theo cam kết cho các dịch vụ và loại tài nguyên được hỗ trợ. RI thường được dùng với EC2, RDS và một số dịch vụ khác. Tùy loại RI, có thể có lựa chọn Standard hoặc Convertible, thời hạn và hình thức thanh toán khác nhau.

Đối với EC2:

- Regional RI thường mang lại lợi ích định giá cho mức sử dụng phù hợp trong Region nhưng không tự động dành riêng capacity.
- Zonal RI có thể cung cấp capacity reservation trong Availability Zone đã chọn và áp dụng ưu đãi theo điều kiện.
- Convertible RI cho phép đổi một số thuộc tính theo quy tắc của chương trình.

Đừng nhầm RI discount với việc luôn có máy chủ sẵn sàng. Nếu cần bảo đảm capacity, hãy kiểm tra thuộc tính reservation và chiến lược capacity riêng.

### 3.4. Spot Instances

Spot cho phép sử dụng EC2 capacity dư thừa của AWS với mức giá biến động và thường thấp hơn đáng kể so với On-Demand. AWS có thể thu hồi Spot capacity khi cần. Workload phải chịu được interruption và có thể khởi động lại hoặc tiếp tục ở tài nguyên khác.

Phù hợp với:

- Batch processing.
- CI/CD worker.
- Render hoặc xử lý dữ liệu phân tán.
- Tác vụ có checkpoint và có thể chạy lại.
- Fleet có thể kết hợp Spot với On-Demand để giữ baseline.

Không nên dùng Spot đơn lẻ cho workload có trạng thái không thể phục hồi hoặc yêu cầu sẵn sàng liên tục nếu chưa có thiết kế dự phòng. Có thể dùng EC2 Auto Scaling hoặc ECS capacity provider để kết hợp nhiều loại capacity.

### 3.5. Dedicated Instances và Dedicated Hosts

Dedicated Instances chạy trên phần cứng dành riêng cho một khách hàng ở cấp instance theo mô hình hỗ trợ. Dedicated Hosts cung cấp máy chủ vật lý chuyên dụng và tăng khả năng kiểm soát vị trí instance, socket/core và một số yêu cầu license.

Các lựa chọn này phù hợp khi có yêu cầu cách ly phần cứng, license theo socket/core hoặc tuân thủ cụ thể. Chi phí thường cao hơn shared tenancy; cần xác minh yêu cầu pháp lý và license trước khi chọn.

### 3.6. So sánh nhanh

| Mô hình | Cam kết | Khả năng thay đổi | Trường hợp phù hợp |
|---|---|---|---|
| On-Demand | Không | Cao | Workload mới, biến động, ngắn hạn |
| Savings Plans | Cam kết chi tiêu theo giờ | Tùy loại plan | Baseline compute ổn định |
| Reserved Instances | Cam kết theo dịch vụ/cấu hình được hỗ trợ | Tùy loại RI | Workload ổn định, có thể dự báo |
| Spot | Không cam kết capacity liên tục | Có thể bị thu hồi | Batch, worker chịu interruption |
| Dedicated | Theo mô hình tài nguyên chuyên dụng | Phụ thuộc loại lựa chọn | License hoặc yêu cầu cách ly |

Một kiến trúc thường kết hợp nhiều mô hình: baseline dùng Savings Plans hoặc RI, phần tải đột biến dùng On-Demand, còn batch chịu interruption dùng Spot.

## 4. Nguồn chi phí compute

### 4.1. Amazon EC2

Chi phí EC2 phụ thuộc instance type, Region, operating system, tenancy, purchase option và thời gian chạy. Một instance lớn hơn có thể tăng chi phí theo giờ, nhưng cũng có thể hoàn thành công việc nhanh hơn và giảm tổng giờ sử dụng.

Khi ước tính:

1. Xác định số instance theo môi trường và Availability Zone.
2. Chọn family, size, CPU, memory và network phù hợp.
3. Xác định operating system và license.
4. Ước tính số giờ chạy mỗi tháng, bao gồm thời gian dự phòng và bảo trì.
5. Chọn On-Demand, Savings Plans, RI hoặc Spot theo độ ổn định của tải.
6. Cộng EBS, snapshot, network, load balancer, NAT và monitoring.

Stop instance thường dừng phần compute billing của instance theo quy tắc EC2, nhưng EBS volume, snapshot, Elastic IP hoặc tài nguyên liên quan vẫn có thể phát sinh phí. Terminate instance cũng không đồng nghĩa mọi volume hoặc snapshot được xóa; hãy kiểm tra delete-on-termination và chính sách lưu trữ.

### 4.2. Auto Scaling và lịch chạy

Auto Scaling điều chỉnh số lượng instance theo metric hoặc lịch. Cơ chế này có thể giảm chi phí khi tải thấp, nhưng cần đặt minimum, desired và maximum capacity hợp lý.

Ví dụ:

- Production API giữ ít nhất hai instance để duy trì khả năng phục vụ.
- Worker batch tăng số lượng theo queue depth.
- Development environment tự dừng ngoài giờ làm việc.
- Job chạy định kỳ chỉ khởi tạo capacity trong cửa sổ xử lý.

Không giảm capacity dưới mức cần thiết cho tính sẵn sàng. Một hệ thống chạy ít instance hơn nhưng thường xuyên quá tải, timeout hoặc cần can thiệp thủ công có thể tạo ra tổng chi phí cao hơn.

### 4.3. AWS Fargate

Fargate tính phí dựa trên tài nguyên compute được cấp cho task hoặc pod và thời gian sử dụng, cùng một số thành phần khác theo dịch vụ. Với ECS on Fargate, cần ước tính vCPU, memory và thời gian task chạy. Với EKS on Fargate, cần tính cấu hình pod và thời gian chạy theo mô hình hỗ trợ.

Đặt CPU và memory quá lớn làm tăng chi phí dù ứng dụng không sử dụng hết. Đặt quá nhỏ có thể gây throttling, OOM hoặc kéo dài thời gian xử lý. Hãy dùng metric CPU, memory, task duration và throughput để điều chỉnh.

### 4.4. Amazon ECS và Amazon EKS

ECS control plane không tính phí theo cách một EC2 instance được tính, nhưng tài nguyên chạy task vẫn phát sinh chi phí. ECS trên EC2 có chi phí instance, EBS và network; ECS trên Fargate có chi phí theo cấu hình task và thời gian.

EKS có phí quản lý cluster theo thời gian và các khoản compute cho node EC2 hoặc Fargate, cùng chi phí storage, load balancer, network và add-on. Với cluster nhỏ, phí quản lý cluster có thể chiếm tỷ trọng đáng kể. Với nhiều cluster tách biệt, hãy tính phí cluster cùng chi phí node và công cụ vận hành.

### 4.5. AWS Lambda

Lambda thường có các thành phần tính phí:

- Số lần invocation.
- Thời gian thực thi và memory được cấp.
- Provisioned Concurrency nếu bật.
- Ephemeral storage vượt mức bao gồm hoặc các tính năng tính phí riêng.
- Data transfer và các dịch vụ được Lambda gọi.

Thời gian chạy tăng khi code xử lý chậm, gọi dependency nhiều lần hoặc cấu hình memory không phù hợp. Tăng memory có thể tăng giá mỗi đơn vị thời gian nhưng đồng thời giảm runtime; cần benchmark để so sánh tổng chi phí trên mỗi request hoặc mỗi tác vụ hoàn thành.

### 4.6. Ví dụ tính compute

Giả sử một worker chạy liên tục trong 30 ngày trên cấu hình cố định. Số giờ lý thuyết trong tháng 30 ngày là:

\[
30 \times 24 = 720\ \text{giờ}
\]

Nếu chạy hai worker cùng cấu hình, tổng mức sử dụng compute là 1.440 instance-hours trước khi tính các khoản ưu đãi, thay đổi thời gian thực tế và các tài nguyên đi kèm.

Đây mới là phần compute. Cần cộng volume, snapshot, truyền dữ liệu, load balancing, log và backup để có tổng chi phí vận hành.

## 5. Nguồn chi phí storage

### 5.1. Amazon EBS

EBS thường phát sinh chi phí theo dung lượng provisioned của volume trong thời gian volume tồn tại. Một số loại volume còn tính riêng IOPS hoặc throughput được provision vượt mức bao gồm.

Các yếu tố:

- Loại volume như gp3, io2 hoặc loại phù hợp khác.
- Dung lượng provisioned, không chỉ dữ liệu thực sự ghi.
- IOPS và throughput.
- Snapshot và bản sao snapshot.
- Data transfer hoặc thao tác liên quan nếu có.

gp3 cho phép cấu hình dung lượng, IOPS và throughput độc lập trong giới hạn của loại volume. Với workload không cần hiệu năng cao, provision IOPS/throughput vượt nhu cầu có thể gây lãng phí. Với database quan trọng, hạ cấu hình quá thấp có thể làm tăng latency và kéo dài thời gian xử lý.

### 5.2. EBS snapshots

EBS snapshot lưu dữ liệu theo cơ chế incremental sau snapshot đầu tiên. Chi phí phụ thuộc dung lượng snapshot được lưu và các tính năng/lớp lưu trữ được sử dụng. Xóa một snapshot không nhất thiết giải phóng toàn bộ block nếu block đó còn được snapshot khác tham chiếu.

Nên:

- Thiết lập lịch snapshot theo RPO.
- Dùng lifecycle để xóa snapshot quá hạn.
- Rà soát snapshot mồ côi và snapshot thuộc volume đã xóa.
- Phân biệt snapshot nguồn, bản sao cross-Region và archive.
- Kiểm tra khả năng restore và thời gian khởi tạo volume.

### 5.3. Amazon S3

Chi phí S3 có thể gồm:

- Dung lượng lưu theo storage class và thời gian.
- PUT, GET, LIST và các request khác.
- Data retrieval và retrieval request ở một số lớp.
- Data transfer ra ngoài hoặc giữa các Region.
- Replication, inventory, analytics và các tính năng quản lý bổ sung.

Các storage class phổ biến:

| Storage class | Đặc điểm sử dụng | Điểm cần xem xét về chi phí |
|---|---|---|
| S3 Standard | Dữ liệu truy cập thường xuyên | Lưu trữ và request |
| S3 Intelligent-Tiering | Dữ liệu có mẫu truy cập khó dự đoán | Phí monitoring/automation; retrieval ở các tier có điều kiện riêng |
| S3 Standard-IA | Dữ liệu ít truy cập nhưng cần truy xuất nhanh | Phí lưu trữ thấp hơn, có phí truy xuất và thời hạn lưu tối thiểu |
| S3 One Zone-IA | Dữ liệu ít truy cập, chấp nhận lưu trong một AZ | Chi phí và rủi ro availability khác Standard-IA |
| S3 Glacier Instant Retrieval | Dữ liệu archive cần truy xuất nhanh | Phí lưu trữ, request và truy xuất; có thời hạn lưu tối thiểu |
| S3 Glacier Flexible Retrieval | Archive, có thể chấp nhận thời gian khôi phục | Chi phí phụ thuộc cách retrieval và dung lượng |
| S3 Glacier Deep Archive | Lưu trữ rất dài hạn, hiếm khi truy xuất | Lưu trữ thấp hơn nhưng thời gian và phí khôi phục cần tính |

Chọn storage class theo tần suất truy cập, độ trễ chấp nhận được, thời hạn lưu giữ và chi phí truy xuất. Chuyển dữ liệu sang lớp rẻ hơn có thể không tiết kiệm nếu thường xuyên truy xuất hoặc xóa trước thời hạn tối thiểu.

### 5.4. Lifecycle và Intelligent-Tiering

S3 Lifecycle có thể chuyển object sang storage class khác hoặc hết hạn object theo quy tắc. Cần kiểm tra:

- Prefix hoặc tag áp dụng có đúng phạm vi không.
- Object versioning có giữ lại phiên bản cũ không.
- Delete marker và noncurrent versions có được xử lý không.
- Multipart upload chưa hoàn tất có được dọn không.
- Thời hạn tối thiểu của storage class có ảnh hưởng đến phí không.

Intelligent-Tiering tự chuyển object giữa các access tier theo mẫu truy cập, nhưng có phí monitoring/automation cho đối tượng đủ điều kiện. So sánh chi phí này với lifecycle rule thủ công nếu mẫu truy cập đã biết rõ.

### 5.5. Ví dụ ước tính storage

Giả sử một bucket giữ 2 TB dữ liệu trung bình trong tháng. Chi phí lưu trữ cơ bản có thể được ước tính theo:

\[
\text{Dung lượng tính phí} \times \text{Đơn giá GB-month của storage class}
\]

Nhưng cần cộng request, retrieval, replication, versioning và data transfer. Nếu dữ liệu được tải xuống nhiều lần, phần request và retrieval có thể đáng kể so với phí lưu trữ.

## 6. Nguồn chi phí networking và data transfer

### 6.1. Data transfer

Chi phí mạng thường bị bỏ sót vì không xuất hiện dưới tên workload. Các luồng cần xem:

- Data transfer ra Internet.
- Data transfer giữa Availability Zone.
- Data transfer giữa Region.
- Traffic qua NAT Gateway.
- Traffic qua load balancer.
- Traffic qua VPC endpoint hoặc dịch vụ edge.
- Cross-account hoặc cross-Region replication.

Một ứng dụng có thể có compute nhỏ nhưng truyền lượng dữ liệu lớn, ví dụ media processing, analytics hoặc API trả về file. Khi đó data transfer có thể trở thành một trong những khoản chi phí lớn.

### 6.2. NAT Gateway

NAT Gateway thường có phí theo thời gian tồn tại và theo GB dữ liệu được xử lý. Nếu nhiều private subnet cùng gửi traffic Internet qua NAT Gateway, tổng lượng dữ liệu có thể làm phí tăng nhanh.

Các cách kiểm soát:

- Dùng VPC endpoints cho các dịch vụ AWS phù hợp để tránh đưa traffic nội bộ qua NAT.
- Kiểm tra route table để bảo đảm traffic đi đúng endpoint.
- Đặt NAT Gateway theo kiến trúc AZ phù hợp để cân bằng chi phí, độ sẵn sàng và phí cross-AZ.
- Theo dõi bytes processed và thời gian tồn tại.
- Tránh tạo NAT Gateway ở môi trường thử nghiệm không cần truy cập Internet.

Không loại bỏ NAT chỉ để giảm phí nếu workload vẫn cần outbound connectivity. Cần đánh giá security, patching, external API và yêu cầu vận hành.

### 6.3. VPC endpoints

Gateway endpoint cho một số dịch vụ như S3 và DynamoDB có mô hình chi phí khác với interface endpoint. Interface endpoint thường có phí theo thời gian endpoint tồn tại và dữ liệu xử lý. Cần so sánh tổng phí endpoint với NAT Gateway và lưu lượng thực tế.

VPC endpoint có thể giảm đường đi qua Internet/NAT và cải thiện kiểm soát mạng, nhưng không phải mọi endpoint đều miễn phí. Số AZ, số endpoint, số giờ và lượng dữ liệu ảnh hưởng tổng chi phí.

### 6.4. Load balancer

Application Load Balancer và Network Load Balancer có thể tính phí theo thời gian hoạt động và đơn vị capacity/processed traffic tương ứng. Với ALB, cần xem số Load Balancer Capacity Units (LCU) và các chiều đo như kết nối mới, kết nối hoạt động, bytes processed và rule evaluations theo cách dịch vụ tính.

Một load balancer rỗng nhưng vẫn tồn tại có thể tiếp tục phát sinh phí theo giờ. Rà soát load balancer, target group, listener và môi trường đã ngừng hoạt động.

### 6.5. CloudFront và edge delivery

CloudFront có các khoản phí liên quan đến data transfer, request và tính năng bổ sung theo khu vực/plan. Dùng CDN có thể giảm tải origin và cải thiện độ trễ, nhưng cần so sánh:

- Lượng dữ liệu phân phối theo edge location.
- Request count và loại request.
- Cache hit ratio.
- Origin fetch và data transfer từ origin.
- Invalidations hoặc tính năng bổ sung nếu có tính phí.

Tối ưu cache policy, TTL, compression và object size có thể giảm request tới origin và tổng dữ liệu truyền. Đừng giả định CDN luôn rẻ hơn mọi đường truyền trực tiếp; hãy mô hình hóa theo traffic thực tế.

## 7. Nguồn chi phí database và cache

### 7.1. Amazon RDS và Aurora

RDS/Aurora có thể phát sinh chi phí từ:

- DB instance hoặc serverless capacity.
- Storage và IOPS.
- Multi-AZ hoặc read replica.
- Backup và snapshot vượt mức bao gồm.
- Data transfer.
- Proxy, monitoring hoặc tính năng bổ sung nếu bật.

Multi-AZ tăng khả năng sẵn sàng và có thể làm tăng chi phí compute/storage so với triển khai đơn AZ. Đây là lựa chọn kiến trúc theo yêu cầu reliability, không nên tắt chỉ để giảm hóa đơn nếu workload cần khả năng chịu lỗi.

Read replica có thể tăng chi phí nhưng giảm tải đọc trên writer. Trước khi thêm replica, hãy kiểm tra query pattern, cache, indexing và khả năng scale hiện có.

### 7.2. Aurora Serverless

Aurora Serverless tính phí theo capacity được cấp hoặc tiêu thụ theo mô hình serverless tương ứng, cùng storage, I/O và các thành phần khác. Mức capacity min/max ảnh hưởng chi phí nền và khả năng đáp ứng burst.

Nếu min capacity quá cao, workload ít tải vẫn có thể phát sinh chi phí đáng kể. Nếu min quá thấp hoặc scaling chậm so với pattern tải, ứng dụng có thể gặp latency. Cần đo mức sử dụng theo chu kỳ ngày/tuần và kiểm thử giờ cao điểm.

### 7.3. Amazon DynamoDB

DynamoDB có các mô hình capacity:

- **On-Demand:** tính phí theo read/write request units được sử dụng, phù hợp với tải khó dự đoán hoặc mới triển khai.
- **Provisioned:** cấp read/write capacity; có thể dùng auto scaling để điều chỉnh theo tải.

Ngoài request capacity, cần xem storage, backup/PITR, global tables, streams, export/import và các tính năng bổ sung. Thiết kế partition key không tốt có thể tạo hot partition và buộc phải tăng capacity hoặc làm giảm hiệu năng.

Chọn On-Demand không có nghĩa mọi chi phí đều chỉ tính theo request; storage, backup, replication và data transfer vẫn cần tính.

### 7.4. Cache

Amazon ElastiCache có thể tính phí theo node hoặc serverless capacity và thời gian sử dụng, tùy lựa chọn. Cache giúp giảm tải database và độ trễ, nhưng cũng tạo thêm compute, memory, backup và data transfer.

Đo cache hit ratio, memory utilization, eviction và request pattern. Cache quá lớn hoặc ít hit có thể không mang lại lợi ích kinh tế. Cache quá nhỏ gây eviction và làm tải quay lại database.

## 8. Nguồn chi phí serverless và tích hợp

### 8.1. API Gateway

API Gateway có thể tính theo số request, loại API, data transfer và các tính năng liên quan. Ước tính cần dựa trên request count, payload size, cache nếu dùng và số stage/environment.

Các endpoint thử nghiệm hoặc stage cũ không còn dùng nên được rà soát. Logging chi tiết cho mọi request có thể tạo chi phí CloudWatch Logs đáng kể, đặc biệt khi payload lớn.

### 8.2. SQS, SNS và EventBridge

Các dịch vụ messaging/event thường tính theo request, số lần xử lý, payload, loại API hoặc các tính năng liên quan. Một message được gửi, nhận, visibility timeout, retry hoặc redrive có thể làm tăng số request.

Khi thiết kế:

- Tránh polling quá thường xuyên khi queue trống nếu mô hình polling tạo nhiều request.
- Dùng long polling cho SQS để giảm empty receive.
- Kiểm soát retry loop và DLQ redrive.
- Giới hạn kích thước message và số lần fan-out không cần thiết.
- Theo dõi số event, số delivery, lỗi và độ trễ consumer.

### 8.3. AWS Step Functions

Step Functions có mô hình tính phí khác nhau theo loại workflow. Standard thường tính theo state transition; Express có mô hình request và duration. Một workflow nhiều state, retry hoặc vòng lặp có thể tạo số transition lớn hơn dự kiến.

Thiết kế state machine gọn, tránh polling quá dày, đặt retry có giới hạn và chọn loại workflow theo yêu cầu thời gian, lưu lịch sử và thông lượng.

### 8.4. Lambda và event-driven cost

Một kiến trúc event-driven có thể giảm compute chạy liên tục, nhưng số lượng event, invocation, retry, duration và downstream request có thể tăng. Hãy tính tổng chi phí của cả chuỗi:

Producer -> EventBridge/SNS/SQS -> Lambda -> Database/API -> Logs/Tracing

Đừng chỉ so sánh phí Lambda với một EC2 instance. Cần so sánh chi phí hoàn thành một đơn vị công việc, độ trễ, khả năng scale và chi phí vận hành.

## 9. Observability, security và backup cũng là nguồn chi phí

### 9.1. Amazon CloudWatch

CloudWatch có thể tính phí theo:

- Log ingestion và log storage.
- Custom metrics và metric resolution.
- Alarm.
- Dashboard hoặc tính năng quan sát nâng cao.
- Logs Insights query và dữ liệu quét.
- Một số loại metric, contributor insights hoặc tính năng bổ sung.

Log quá chi tiết, lưu quá lâu hoặc ghi cả payload lớn có thể tạo hóa đơn cao. Nên xác định retention theo mục đích: debug ngắn hạn, vận hành, bảo mật và kiểm toán. Không giảm retention dưới yêu cầu điều tra hoặc tuân thủ.

### 9.2. Tracing và audit

AWS X-Ray và các giải pháp tracing có thể phát sinh phí theo trace hoặc dữ liệu được thu thập/ghi nhận. CloudTrail có thể có chi phí cho data events, CloudTrail Lake ingestion và retention; Config tính phí theo configuration item hoặc loại hoạt động được hỗ trợ.

Chọn sampling phù hợp để giữ khả năng chẩn đoán mà không thu thập mọi trace ở mức chi tiết cao khi lưu lượng lớn. Với audit, xác định sự kiện cần ghi nhận theo rủi ro và nghĩa vụ tuân thủ.

### 9.3. Security services

Các dịch vụ như GuardDuty, Security Hub, Inspector, Macie và KMS có mô hình tính phí riêng theo lượng dữ liệu, tài nguyên, finding, request hoặc tính năng. Bật nhiều dịch vụ bảo mật giúp tăng độ bao phủ nhưng cần đưa chi phí vào thiết kế.

Không nên tắt kiểm soát bảo mật chỉ để giảm chi phí mà không đánh giá rủi ro. Thay vào đó, xác định phạm vi, nguồn dữ liệu, mức độ quan trọng và cấu hình phù hợp; theo dõi chi phí theo account/Region để phát hiện tăng trưởng bất thường.

### 9.4. AWS Backup

AWS Backup có thể phát sinh chi phí lưu recovery point, bản sao liên Region/liên tài khoản, restore, retrieval hoặc các tính năng bảo vệ tùy loại tài nguyên. Bản sao ở nhiều tài khoản làm tăng khả năng phục hồi nhưng tạo thêm dung lượng lưu trữ.

Để dự báo:

- Ước tính dung lượng nguồn và tỷ lệ thay đổi dữ liệu.
- Xác định số bản sao, Region và thời hạn lưu giữ.
- Kiểm tra storage tier và điều kiện lifecycle.
- Ước tính restore testing và tài nguyên tạm.
- Theo dõi recovery point tồn tại lâu hơn chính sách dự kiến.

## 10. Công cụ xem giá và ước tính trước triển khai

### 10.1. AWS Pricing Calculator

AWS Pricing Calculator giúp tạo estimate dựa trên dịch vụ, Region, cấu hình và mức sử dụng dự kiến. Có thể dùng để:

1. Liệt kê dịch vụ cần cho workload.
2. Chọn Region và cấu hình.
3. Nhập thời gian chạy, dung lượng, request hoặc data transfer.
4. Chọn purchase option phù hợp.
5. Lưu estimate và chia sẻ với nhóm liên quan.

Calculator là công cụ ước tính, không phải cam kết hóa đơn. Kết quả phụ thuộc input, giả định, đơn giá hiện hành, ưu đãi, thuế và các khoản chưa được mô hình hóa. Hãy ghi lại giả định và cập nhật khi workload thay đổi.

### 10.2. AWS Price List và trang giá dịch vụ

Trang giá chính thức của từng dịch vụ là nguồn để kiểm tra đơn vị tính phí, tier, Region và điều kiện. AWS Price List cung cấp dữ liệu giá có cấu trúc để hệ thống nội bộ truy vấn hoặc xây dựng công cụ estimate.

Khi đọc bảng giá:

- Kiểm tra đúng Region.
- Đọc rõ usage type và operation.
- Xác định đơn giá theo tier và điều kiện miễn/bao gồm.
- Phân biệt đơn giá On-Demand với giá sau ưu đãi.
- Kiểm tra thời điểm cập nhật và đơn vị tiền tệ.

Không sao chép một mức giá từ bài viết cũ mà không xác minh trang giá hiện hành.

### 10.3. Lập mô hình theo workload

Một estimate hữu ích phải mô tả workload, không chỉ danh sách dịch vụ. Ví dụ cho API thương mại điện tử:

| Thành phần | Input cần ước tính |
|---|---|
| Compute | Số task/instance, vCPU, memory, giờ chạy, mức scale |
| Database | Instance/capacity, storage, I/O, backup, replica |
| Storage | GB-month, object count, request, retrieval |
| Network | Egress, inter-AZ, NAT processed bytes, load balancer |
| API | Request/tháng, payload, cache, stage |
| Messaging | Message count, size, delivery, retry |
| Observability | Log GB/ngày, retention, metric, alarm, trace sampling |
| Security | Data events, findings, scan scope, KMS requests |
| Backup | Frequency, retention, copy count, restore tests |

Đầu vào càng gần thực tế, estimate càng có ích. Nếu chưa có số liệu, hãy tạo ba kịch bản: thấp, cơ sở và cao; ghi rõ giả định cho từng kịch bản.

## 11. Đọc hóa đơn và phân bổ chi phí

### 11.1. Consolidated Billing

AWS Organizations có thể hợp nhất billing cho các tài khoản trong tổ chức theo cơ chế consolidated billing. Điều này giúp theo dõi chi phí tập trung và có thể cho phép chia sẻ một số lợi ích định giá giữa các tài khoản theo điều kiện của chương trình.

Hợp nhất hóa đơn không có nghĩa mọi nhóm nhìn thấy cùng một khoản chi phí hoặc quyền truy cập billing tự động được cấp cho mọi người. Cần thiết kế quyền xem billing, cost allocation và báo cáo theo vai trò.

### 11.2. Các góc nhìn chi phí

Có thể phân tích chi phí theo:

- Linked account hoặc member account.
- Service.
- Region.
- Usage type.
- Operation.
- Purchase option.
- Tag và cost category.
- Thời gian, môi trường hoặc nhóm sản phẩm.

Một dòng EC2 có thể bao gồm nhiều usage type khác nhau như instance usage, EBS, data transfer hoặc license. Lọc chỉ theo tên service có thể chưa đủ để tìm nguyên nhân tăng chi phí.

### 11.3. Cost allocation tags

Cost allocation tags là thẻ được dùng để phân bổ chi phí theo ứng dụng, nhóm, môi trường hoặc chủ sở hữu. Thẻ cần được kích hoạt trong Billing/Cost Management trước khi có thể dùng trong báo cáo chi phí tương ứng.

Một bộ tag tham khảo:

| Tag | Mục đích | Ví dụ giá trị |
|---|---|---|
| Application | Ứng dụng chịu chi phí | commerce-api |
| Environment | Môi trường | production, staging, development |
| Team | Nhóm sở hữu | platform, payments |
| CostCenter | Trung tâm chi phí | CC-104 |
| Owner | Người/nhóm chịu trách nhiệm | team-payments |
| DataClass | Phân loại dữ liệu | internal, confidential |

Không cần gắn mọi tag vào mọi loại tài nguyên nếu không có giá trị quản trị. Hãy chuẩn hóa từ điển tag, quy định bắt buộc và kiểm tra tài nguyên thiếu tag.

### 11.4. Cost Categories

Cost Categories giúp nhóm chi phí theo quy tắc tùy chỉnh, chẳng hạn ánh xạ nhiều account hoặc tag vào một sản phẩm, đơn vị kinh doanh hoặc cost center. Điều này hữu ích khi cấu trúc AWS account không trùng với sơ đồ tổ chức.

Hãy quản lý quy tắc category có version, người sở hữu và thời điểm hiệu lực để các báo cáo tháng trước có thể được diễn giải đúng khi quy tắc thay đổi.

### 11.5. Unblended, blended và amortized cost

Các báo cáo AWS có thể trình bày chi phí theo nhiều cách:

- **Unblended cost:** chi phí theo mức giá và khoản phí của từng tài khoản/usage trước khi gộp theo cách blended.
- **Blended cost:** giá bình quân được áp dụng trong một số bối cảnh consolidated billing; không phải lúc nào cũng phù hợp để phân bổ chi phí nội bộ.
- **Amortized cost:** phân bổ chi phí trả trước hoặc cam kết theo thời gian sử dụng để phản ánh chi phí kinh tế trong kỳ.

Với Savings Plans hoặc Reserved Instances, unblended cash view và amortized view có thể khác nhau. Khi đánh giá hiệu quả cam kết, hãy xem cả khoản thanh toán, mức sử dụng được hưởng ưu đãi và chi phí đã phân bổ theo thời gian.

## 12. Công cụ quản lý và kiểm soát chi phí

### 12.1. AWS Cost Explorer

Cost Explorer giúp phân tích chi phí và mức sử dụng theo thời gian, dịch vụ, tài khoản, Region, tag và các chiều được hỗ trợ. Có thể dùng để:

- So sánh tháng này với tháng trước.
- Tìm dịch vụ hoặc account có mức tăng bất thường.
- Phân tích xu hướng theo ngày/tháng.
- Xem chi phí theo purchase option.
- Đánh giá Savings Plans/RI và cơ hội tối ưu được cung cấp.

Hãy lọc đúng khoảng thời gian và cost metric trước khi kết luận. Một khoản tăng có thể do workload tăng, thay đổi đơn giá, credit hết hạn, điều chỉnh hóa đơn hoặc thay đổi cách phân bổ.

### 12.2. AWS Budgets

AWS Budgets cho phép đặt ngân sách theo cost, usage, Savings Plans hoặc Reserved Instances theo loại budget được hỗ trợ. Có thể cấu hình ngưỡng cảnh báo và gửi thông báo tới người chịu trách nhiệm.

Ví dụ:

- Ngân sách production theo tháng.
- Ngân sách cho từng project hoặc cost center.
- Cảnh báo khi chi phí thực tế hoặc dự báo vượt 80%, 100% mức ngân sách.
- Theo dõi utilization và coverage của Savings Plans.

Budget alert là tín hiệu cần điều tra, không tự giải thích nguyên nhân. Cần có owner và quy trình phản hồi.

### 12.3. Cost Anomaly Detection

AWS Cost Anomaly Detection dùng phát hiện bất thường trong chi phí và gửi cảnh báo theo monitor/subscription. Có thể theo dõi toàn bộ dịch vụ, tài khoản hoặc phạm vi được cấu hình.

Anomaly detection hữu ích để phát hiện spike sớm, nhưng không thay thế budget. Một khoản chi phí tăng đều có thể không bị xem là anomaly nhưng vẫn vượt ngân sách; ngược lại, một spike ngắn có thể đáng điều tra dù tổng tháng vẫn thấp.

### 12.4. Cost and Usage Reports và Data Exports

AWS Cost and Usage Report (CUR) và các khả năng Data Exports cung cấp dữ liệu chi tiết về chi phí và mức sử dụng để phân tích trong hệ thống dữ liệu riêng. Tổ chức có thể lưu dữ liệu vào S3, truy vấn bằng Athena hoặc đưa vào công cụ BI.

Dữ liệu chi tiết hỗ trợ:

- Phân tích usage type và operation.
- Phân bổ chi phí theo tag/cost category.
- Đối chiếu hóa đơn với dữ liệu ứng dụng.
- Xây dựng dashboard và báo cáo chargeback.
- Phân tích chi phí cam kết và chi phí hiệu dụng.

CUR/Data Exports có thể chứa nhiều cột và dòng dữ liệu; cần thiết kế partition, retention, quyền truy cập và chi phí truy vấn/lưu trữ của hệ thống báo cáo.

### 12.5. Công cụ hỗ trợ tối ưu

Một số công cụ khác:

- **AWS Compute Optimizer:** đề xuất kích thước hoặc cấu hình phù hợp dựa trên metric sử dụng cho tài nguyên được hỗ trợ.
- **AWS Trusted Advisor:** cung cấp một số kiểm tra về tối ưu chi phí, hiệu năng, bảo mật và giới hạn dịch vụ theo gói/quyền hiện hành.
- **AWS Cost Optimization Hub:** tập hợp cơ hội tối ưu từ các nguồn được hỗ trợ.
- **S3 Storage Lens:** phân tích cách sử dụng và tăng trưởng dữ liệu S3.
- **CloudWatch:** cung cấp metric và alarm để liên hệ chi phí với hành vi workload.

Các đề xuất tự động cần được xem xét theo workload và yêu cầu reliability. Không áp dụng thay đổi instance size, retention hoặc network chỉ dựa vào một gợi ý mà chưa kiểm tra ảnh hưởng.

## 13. Quy trình FinOps

### 13.1. Inform, Optimize và Operate

FinOps là thực hành phối hợp giữa engineering, finance và business để tối đa hóa giá trị từ chi tiêu cloud.

Một vòng lặp phổ biến:

1. **Inform:** thu thập và phân bổ chi phí, làm rõ owner, tạo dashboard và giúp nhóm hiểu mức sử dụng.
2. **Optimize:** tìm cơ hội giảm lãng phí, cải thiện utilization, chọn mô hình mua và điều chỉnh kiến trúc.
3. **Operate:** đặt mục tiêu, ngân sách, quy trình review, trách nhiệm và đo kết quả liên tục.

FinOps không phải hoạt động cắt giảm hóa đơn một lần. Khi sản phẩm tăng trưởng, chi phí có thể tăng nhưng chi phí trên mỗi đơn hàng hoặc mỗi khách hàng lại giảm. Cần đánh giá chi phí cùng với giá trị kinh doanh.

### 13.2. Unit economics

Unit economics liên hệ chi phí cloud với một đơn vị đầu ra, ví dụ:

- Chi phí trên mỗi đơn hàng hoàn tất.
- Chi phí trên mỗi người dùng hoạt động.
- Chi phí trên mỗi GB dữ liệu xử lý.
- Chi phí trên mỗi lần chạy pipeline.
- Chi phí trên mỗi request thành công.

Ví dụ:

\[
\text{Cost per order} = \frac{\text{Tổng chi phí cloud của hệ thống trong kỳ}}{\text{Số đơn hàng hoàn tất trong kỳ}}
\]

Nếu tổng chi phí tăng 15% nhưng số đơn hàng tăng 40%, chi phí trên mỗi đơn hàng có thể giảm. Ngược lại, hóa đơn không đổi nhưng lưu lượng giảm một nửa có thể cho thấy utilization xấu đi.

### 13.3. Showback và chargeback

**Showback** cung cấp báo cáo để nhóm biết họ đang tiêu thụ bao nhiêu chi phí nhưng chưa nhất thiết chuyển khoản chi phí vào ngân sách của nhóm.

**Chargeback** phân bổ chi phí vào ngân sách hoặc báo cáo tài chính của nhóm chịu trách nhiệm.

Trước khi chargeback, cần thống nhất quy tắc cho chi phí dùng chung như NAT Gateway, transit gateway, logging account, security services và shared database. Có thể phân bổ theo mức sử dụng đo được, tỷ lệ thống nhất hoặc cost center; phải ghi rõ phương pháp để tránh tranh cãi.

### 13.4. Trách nhiệm và nhịp review

Một quy trình có thể bao gồm:

- Engineering owner theo dõi utilization và thực hiện tối ưu.
- Product owner hiểu tác động của thay đổi chi phí đến trải nghiệm.
- Finance/FinOps phân tích hóa đơn, ngân sách và cam kết.
- Platform team chuẩn hóa tag, account, dashboard và guardrail.
- Security team bảo đảm tối ưu không làm suy giảm kiểm soát.

Review chi phí nên có lịch định kỳ và được kích hoạt khi có thay đổi lớn như launch sản phẩm, tăng traffic, thêm Region, thay đổi database hoặc mua cam kết dài hạn.

## 14. Các cách tối ưu chi phí phổ biến

### 14.1. Rightsizing

Rightsizing là điều chỉnh kích thước tài nguyên theo tải thực tế. Dùng CPU, memory, network, disk I/O, latency và throughput trong một khoảng thời gian đủ đại diện. Kiểm tra cả peak, batch window và sự kiện theo mùa trước khi giảm cấu hình.

### 14.2. Tắt tài nguyên ngoài giờ

Môi trường development, test và demo có thể chạy theo lịch. Dùng automation để stop/start instance hoặc scale service về mức thấp. Cần giữ tài nguyên dữ liệu và cấu hình cần thiết; stop EC2 không xóa phí EBS và các thành phần khác.

### 14.3. Tối ưu storage

- Dọn snapshot, AMI, volume và object không còn cần.
- Áp dụng lifecycle theo chính sách dữ liệu.
- Chọn storage class theo access pattern.
- Giảm log retention khi không còn yêu cầu vận hành/kiểm toán.
- Tránh provision IOPS/throughput vượt nhu cầu.

### 14.4. Tối ưu network

- Dùng cache/CDN để giảm origin traffic khi phù hợp.
- Tận dụng VPC endpoint cho traffic AWS được hỗ trợ.
- Kiểm tra NAT Gateway và inter-AZ traffic.
- Đặt workload và dữ liệu gần nhau khi kiến trúc cho phép.
- Nén payload và loại bỏ response không cần thiết.

### 14.5. Tối ưu database và application

- Tối ưu query, index và connection pooling.
- Dùng cache cho dữ liệu đọc lặp lại.
- Chọn On-Demand hoặc Provisioned capacity theo pattern.
- Tự động scale theo metric phù hợp.
- Giảm request thừa và tránh polling quá dày.
- Tối ưu code để giảm duration và memory của Lambda.

### 14.6. Chọn purchase option sau khi hiểu baseline

Đầu tiên hãy tối ưu kích thước và loại bỏ lãng phí. Sau đó mới đánh giá Savings Plans hoặc RI trên phần tải ổn định. Cam kết mua trước khi rightsizing có thể khiến tổ chức tiếp tục trả tiền cho cấu hình không còn phù hợp.

### 14.7. Không đánh đổi reliability để giảm chi phí

Mỗi đề xuất tối ưu cần được đánh giá theo:

- Hiệu năng và latency.
- Availability và fault tolerance.
- RPO/RTO và khả năng restore.
- Bảo mật và yêu cầu tuân thủ.
- Trải nghiệm người dùng.
- Chi phí vận hành và độ phức tạp.

Ví dụ, giảm số AZ, tắt Multi-AZ database hoặc rút ngắn retention có thể giảm hóa đơn nhưng làm thay đổi mức độ rủi ro. Hãy ghi rõ trade-off và có owner phê duyệt.

## 15. Ví dụ thực hành: ước tính chi phí một API trên AWS

### 15.1. Bối cảnh

Một API thương mại điện tử có các thành phần:

- Application chạy trên ECS Fargate.
- ALB nhận HTTP request.
- RDS lưu dữ liệu giao dịch.
- S3 lưu ảnh sản phẩm.
- SQS xử lý công việc gửi thông báo.
- CloudWatch thu thập log và metric.
- NAT Gateway cho một phần outbound traffic.

Nhóm chưa có hóa đơn lịch sử vì đây là hệ thống mới. Thay vì đoán một tổng tiền, nhóm tạo mô hình input:

| Thành phần | Giả định đầu vào cần thu thập |
|---|---|
| API traffic | Request/ngày, peak requests/second, payload trung bình |
| ECS | Số task tối thiểu, mức scale, vCPU/memory mỗi task, giờ chạy |
| ALB | Số giờ hoạt động, kết nối mới, kết nối đồng thời, bytes processed |
| RDS | Instance/capacity, giờ chạy, storage, backup, Multi-AZ |
| S3 | GB lưu, số object, PUT/GET, download và lifecycle |
| SQS | Message count, message size, retry và DLQ |
| CloudWatch | Log GB/ngày, retention, custom metrics, alarm |
| NAT | Số gateway, giờ tồn tại, GB processed |

### 15.2. Tính theo ba kịch bản

Nhóm xây dựng ba kịch bản:

- **Thấp:** traffic trung bình thấp, ít peak, dữ liệu tăng chậm.
- **Cơ sở:** theo forecast của sản phẩm và mức sử dụng dự kiến.
- **Cao:** chiến dịch marketing hoặc mùa cao điểm làm traffic tăng mạnh.

Mỗi kịch bản dùng cùng kiến trúc nhưng thay đổi các input. Với ECS, có thể ước tính task count theo thời gian; với RDS, kiểm tra khả năng đáp ứng peak; với S3 và network, tính lượng dữ liệu tải lên/xuống; với log, ước tính theo request volume và kích thước log.

Sau đó nhập các giả định vào AWS Pricing Calculator theo Region và lưu lại estimate. Ghi rõ các khoản chưa tính như thuế, license bên thứ ba, chi phí hỗ trợ hoặc ưu đãi hợp đồng nếu calculator không mô hình hóa đầy đủ.

### 15.3. So sánh chi phí trên mỗi request

Sau khi triển khai thử nghiệm, lấy chi phí cloud của kỳ đo và chia cho số request thành công:

\[
\text{Cost per successful request} =
\frac{\text{Tổng chi phí cloud trong kỳ}}{\text{Số request thành công trong kỳ}}
\]

Nếu chi phí tăng nhanh hơn traffic, hãy phân tích dịch vụ có mức tăng cao, request lỗi, log trùng, cache hit ratio, NAT processed bytes và database utilization. Nếu chi phí giảm nhưng latency hoặc error rate tăng, cần xem lại việc tối ưu có làm giảm chất lượng dịch vụ không.

## 16. Những sai lầm thường gặp khi đọc và quản lý chi phí

| Sai lầm | Vì sao gây hiểu nhầm | Cách khắc phục |
|---|---|---|
| Chỉ tính EC2 | Bỏ qua EBS, network, ALB, NAT, log và backup | Lập cost model theo toàn bộ luồng workload |
| Nghĩ stop instance là hết phí | Storage và tài nguyên phụ thuộc vẫn tồn tại | Kiểm kê EBS, IP, snapshot, load balancer và NAT |
| Dùng đơn giá của Region khác | Giá và availability có thể khác | Chọn đúng Region trên bảng giá và calculator |
| Mua cam kết theo peak | Cam kết có thể lớn hơn mức sử dụng thực tế | Phân tích baseline trước khi mua |
| Dùng Spot cho workload không chịu interruption | Có thể mất tiến trình hoặc gián đoạn dịch vụ | Checkpoint, retry, capacity mix và fallback |
| Chuyển toàn bộ S3 sang Glacier | Retrieval và thời gian khôi phục có thể không phù hợp | Phân loại access pattern và thử retrieval |
| Không bật cost allocation tags | Khó xác định nhóm hoặc ứng dụng chịu chi phí | Chuẩn hóa và kích hoạt tag trong billing |
| Chỉ xem unblended cost | Có thể không phản ánh chi phí cam kết phân bổ theo kỳ | So sánh cash view và amortized view |
| Cắt log/backup không đánh giá | Mất khả năng điều tra hoặc phục hồi | Giữ yêu cầu bảo mật, tuân thủ và RPO/RTO |
| Chỉ dùng budget alert | Không biết nguyên nhân hoặc trách nhiệm xử lý | Gắn owner, dashboard và quy trình phản hồi |

## 17. Checklist kiểm soát chi phí AWS

### Trước khi triển khai

1. Xác định workload, Region, môi trường và mục tiêu kinh doanh.
2. Liệt kê compute, storage, database, network, messaging, observability, security và backup.
3. Xác định đơn vị tính phí cho từng dịch vụ.
4. Ước tính thấp/cơ sở/cao và ghi rõ giả định.
5. Dùng AWS Pricing Calculator và kiểm tra bảng giá chính thức.
6. Thiết kế tag, account và cost category để phân bổ.

### Trong vận hành

1. Theo dõi Cost Explorer theo account, service, Region và tag.
2. Thiết lập AWS Budgets và Cost Anomaly Detection.
3. Kiểm tra utilization và rightsizing định kỳ.
4. Rà soát tài nguyên rỗng, volume/snapshot cũ và log retention.
5. Theo dõi data transfer, NAT Gateway, load balancer và request volume.
6. Kiểm tra backup, restore test và các kiểm soát bảo mật có chi phí.
7. Đối chiếu unblended và amortized cost khi có cam kết.

### Khi tối ưu

1. Xác định nguyên nhân chi phí tăng bằng usage type và dữ liệu chi tiết.
2. Đo tác động đến hiệu năng, availability, security và RPO/RTO.
3. Ưu tiên loại bỏ lãng phí và rightsizing.
4. Chỉ mua Savings Plans/RI sau khi xác định baseline ổn định.
5. Thử thay đổi ở phạm vi nhỏ và đo kết quả.
6. Cập nhật estimate, ngân sách, owner và runbook.

## 18. Kết luận

Chi phí AWS hình thành từ nhiều đơn vị sử dụng: thời gian compute, dung lượng storage, request, dữ liệu xử lý, data transfer, capacity được provision và các tính năng quản lý. On-Demand mang lại tính linh hoạt; Savings Plans và Reserved Instances phù hợp với mức sử dụng ổn định; Spot phù hợp với workload chịu interruption. Mỗi dịch vụ như EC2, S3, RDS, Lambda, NAT Gateway, CloudWatch và AWS Backup có các thành phần tính phí riêng cần được đưa vào cost model.

AWS Pricing Calculator giúp ước tính trước triển khai; Cost Explorer, Budgets, Cost Anomaly Detection và dữ liệu CUR/Data Exports hỗ trợ theo dõi sau triển khai. Cost allocation tags và Cost Categories giúp xác định nhóm chịu trách nhiệm, trong khi FinOps kết nối dữ liệu chi phí với quyết định kỹ thuật và mục tiêu kinh doanh.

Một hệ thống tiết kiệm không chỉ có hóa đơn thấp. Nó cần tạo ra giá trị với chi phí hợp lý, đáp ứng hiệu năng, bảo mật, độ sẵn sàng và khả năng phục hồi. Bằng cách đo chi phí trên đơn vị đầu ra, tối ưu theo workload và review thường xuyên, tổ chức có thể mở rộng AWS một cách có kiểm soát.

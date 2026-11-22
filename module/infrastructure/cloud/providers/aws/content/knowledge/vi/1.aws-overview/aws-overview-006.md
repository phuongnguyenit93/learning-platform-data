# Danh mục dịch vụ và cách chọn dịch vụ AWS

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Nhìn một yêu cầu nghiệp vụ và xác định nhóm dịch vụ AWS cần khảo sát trước khi chọn sản phẩm cụ thể.
- Phân biệt các lựa chọn thường bị nhầm lẫn: EC2, ECS/EKS, Fargate, Lambda; S3, EBS, EFS; RDS/Aurora, DynamoDB; SQS, SNS, EventBridge.
- Giải thích vì sao Region, Availability Zone (AZ), IAM, VPC, giám sát, sao lưu và chi phí ảnh hưởng trực tiếp đến quyết định chọn dịch vụ.
- Đề xuất một kiến trúc tối thiểu có cơ sở, chỉ rõ đánh đổi và xác minh lựa chọn bằng các chỉ số thực tế.

**Bối cảnh:** AWS (Amazon Web Services) là hệ sinh thái dịch vụ đám mây, từ máy ảo, mạng, lưu trữ và cơ sở dữ liệu đến tích hợp, phân tích dữ liệu và serverless. Chọn dịch vụ AWS không phải là tìm dịch vụ “mạnh nhất”, mà là ghép đúng khả năng vào bài toán về hiệu năng, an toàn, vận hành, khả năng phục hồi và ngân sách.

## 1. Tư duy đọc danh mục dịch vụ AWS

Danh mục AWS rất rộng và liên tục thay đổi. Cách học hiệu quả là **đi từ nhu cầu đến nhóm năng lực**, thay vì cố ghi nhớ tên mọi dịch vụ. Một ứng dụng thường phải kết hợp nhiều nhóm:

| Câu hỏi cần trả lời | Nhóm dịch vụ thường khảo sát | Ví dụ |
| --- | --- | --- |
| Mã ứng dụng sẽ chạy ở đâu? | Compute / Containers / Serverless | Amazon EC2, Amazon ECS, Amazon EKS, AWS Fargate, AWS Lambda |
| Dữ liệu được giữ ở dạng nào? | Storage | Amazon S3, Amazon EBS, Amazon EFS |
| Ứng dụng truy vấn dữ liệu ra sao? | Database | Amazon RDS, Amazon Aurora, Amazon DynamoDB |
| Người dùng truy cập ứng dụng qua đường nào? | Networking / Content delivery | Amazon VPC, Elastic Load Balancing, Amazon Route 53, Amazon CloudFront, Amazon API Gateway |
| Các thành phần trao đổi sự kiện thế nào? | Application integration | Amazon SQS, Amazon SNS, Amazon EventBridge, AWS Step Functions |
| Ai được phép làm gì, và dữ liệu được bảo vệ ra sao? | Security / Identity | AWS IAM, AWS KMS, AWS Secrets Manager, AWS WAF |
| Làm sao biết hệ thống lỗi, phục hồi và tốn bao nhiêu? | Operations / Resilience / Cost | Amazon CloudWatch, AWS CloudTrail, AWS Backup, AWS Cost Explorer, AWS Budgets |

Một cách nhìn khác là chia dịch vụ theo **mức độ AWS quản lý hạ tầng**:

- **IaaS / nhiều quyền kiểm soát:** EC2 cho phép chọn máy ảo, hệ điều hành, phần mềm; đội ngũ phải tự chăm sóc nhiều thành phần.
- **Dịch vụ quản lý:** RDS, ECS, EKS, ElastiCache hoặc OpenSearch Service đảm nhận một phần vận hành nền tảng; người dùng vẫn chịu trách nhiệm về cấu hình và ứng dụng.
- **Serverless / quản lý theo nhu cầu:** Lambda, DynamoDB hoặc các khả năng serverless của từng dịch vụ giảm việc quản trị máy chủ và hỗ trợ mở rộng theo kiểu sử dụng.
- **Dịch vụ dùng trực tiếp:** S3, SQS, EventBridge, CloudWatch là các khối chức năng có API riêng; không cần dựng một máy ảo chỉ để cung cấp tính năng tương ứng.

“Managed” và “serverless” **không đồng nghĩa với không cần vận hành**. Vẫn phải cấu hình quyền truy cập, giới hạn chi tiêu, dự phòng, cảnh báo, kiểm thử và xử lý lỗi ứng dụng.

## 2. Danh mục dịch vụ theo nhu cầu

### 2.1. Tính toán: chạy ứng dụng và xử lý công việc

| Dịch vụ | Đặc tính chính | Chọn khi | Điểm cần cân nhắc |
| --- | --- | --- | --- |
| **Amazon EC2** | Máy ảo với quyền điều khiển hệ điều hành và runtime | Phần mềm cũ, yêu cầu hệ điều hành đặc biệt, workload ổn định hoặc cần kiểm soát sâu | Cần quản lý bản vá, ảnh máy, autoscaling, khả dụng và dung lượng |
| **Amazon ECS** | Điều phối container tích hợp AWS | Chạy nhiều dịch vụ container, muốn mô hình vận hành tương đối gọn | Cần hiểu task, service, image, network và deployment |
| **Amazon EKS** | Kubernetes được AWS quản lý một phần | Đã có kỹ năng/hệ sinh thái Kubernetes, cần API và công cụ Kubernetes | Độ phức tạp vận hành, quản trị cluster và chi phí cao hơn trong nhiều trường hợp |
| **AWS Fargate** | Năng lực chạy container không tự quản lý EC2; dùng cùng ECS hoặc EKS | Container theo dịch vụ, muốn tập trung vào ứng dụng | Giá theo tài nguyên cấp phát/thời gian chạy; ít tùy biến máy chủ |
| **AWS Lambda** | Chạy hàm theo sự kiện, tự co giãn trong giới hạn dịch vụ | API ngắn, webhook, xử lý file, tự động hóa và tác vụ không liên tục | Thời gian chạy giới hạn, cold start, quota, tính không trạng thái |
| **AWS Elastic Beanstalk** | Nền tảng triển khai ứng dụng, điều phối các tài nguyên nền | Muốn triển khai ứng dụng web truyền thống nhanh với mô hình quen thuộc | Tài nguyên phát sinh vẫn cần theo dõi; tùy biến theo cơ chế nền tảng |
| **Amazon Lightsail** | Gói tài nguyên đơn giản, cấu hình và giá dễ tiếp cận | Website, demo, dịch vụ nhỏ ít phức tạp | Ít linh hoạt hơn khi yêu cầu mạng và hệ thống tăng cao |
| **AWS Batch** | Xếp hàng và cấp phát môi trường cho công việc theo lô | Xử lý dữ liệu/báo cáo/render nhiều job có điểm kết thúc | Phải thiết kế job độc lập và theo dõi thời gian, chi phí thực thi |

**Lưu ý về thuật ngữ:** ECS và EKS là hệ thống **điều phối**; Fargate là một cách **cấp tài nguyên tính toán** cho container. Vì vậy so sánh đúng thường là “ECS trên Fargate” với “ECS trên EC2”, hoặc “EKS trên Fargate” với “EKS trên node EC2”.

### 2.2. Lưu trữ: object, block và file

| Dịch vụ | Dữ liệu và cách truy cập | Nên dùng | Không nên hiểu nhầm |
| --- | --- | --- | --- |
| **Amazon S3** | Object trong bucket, truy cập bằng API/HTTP | Ảnh, video, bản sao lưu, dữ liệu tĩnh, data lake | S3 không phải đĩa hệ điều hành hoặc hệ thống file POSIX thông thường |
| **Amazon EBS** | Block volume gắn với máy EC2 phù hợp | Đĩa boot, filesystem và dữ liệu cục bộ của EC2 | Volume thuộc một AZ; cần snapshot/thiết kế riêng để phục hồi |
| **Amazon EFS** | File system NFS dùng chung, quản lý bởi AWS | Nhiều máy/container cần đọc ghi chung file theo chuẩn file | Chi phí, độ trễ và kiểu truy cập khác EBS hoặc S3 |
| **Amazon FSx** | Các họ file system được quản lý cho nhu cầu chuyên biệt | Windows file share, Lustre/HPC và các hệ file được hỗ trợ | Cần chọn đúng biến thể FSx theo giao thức/workload |
| **AWS Backup** | Chính sách sao lưu và quản lý điểm khôi phục cho dịch vụ được hỗ trợ | Tập trung lịch sao lưu, thời gian giữ, kiểm soát bảo vệ | Backup không thay thế thiết kế HA hoặc diễn tập khôi phục |

**Quy tắc thực dụng:** Đối tượng tải lên như hóa đơn PDF và ảnh sản phẩm thường vào S3; đĩa hệ điều hành EC2 thường dùng EBS; thư mục phải được nhiều máy cùng mount thường khảo sát EFS. Với S3, xem thêm S3 Storage Classes, lifecycle, versioning và replication theo nhu cầu truy cập, giữ liệu và phục hồi.

### 2.3. Cơ sở dữ liệu, cache, tìm kiếm và phân tích

| Dịch vụ | Kiểu dữ liệu / công việc | Chọn khi | Cần chú ý |
| --- | --- | --- | --- |
| **Amazon RDS** | CSDL quan hệ được quản lý: PostgreSQL, MySQL và các engine được hỗ trợ | Giao dịch, SQL, JOIN, ràng buộc dữ liệu, hệ thống nghiệp vụ | Chọn kích thước, kết nối, backup, Multi-AZ, read replica; ứng dụng chịu trách nhiệm schema/query |
| **Amazon Aurora** | CSDL quan hệ tương thích MySQL/PostgreSQL, thiết kế lưu trữ chuyên biệt | Muốn khả năng mở rộng, hiệu năng và đặc tính HA của Aurora | Đánh giá chi phí và tương thích thực tế với workload |
| **Amazon DynamoDB** | NoSQL key-value/document được quản lý | Truy cập theo khóa, tải biến động cao, yêu cầu độ trễ thấp, mẫu truy vấn xác định | Thiết kế partition key, access pattern, index và tính nhất quán ngay từ đầu |
| **Amazon ElastiCache** | Cache trong bộ nhớ với engine được hỗ trợ | Giảm độ trễ đọc, session/cache và giảm tải database | Cache có thể hết hạn/mất dữ liệu; cần chính sách invalidation và xử lý cache miss |
| **Amazon OpenSearch Service** | Lập chỉ mục, tìm kiếm toàn văn và phân tích log | Tìm kiếm văn bản, lọc và phân tích dữ liệu đã index | Thường không thay thế nguồn dữ liệu giao dịch chính |
| **Amazon Redshift** | Kho dữ liệu phân tích (data warehouse) | BI/OLAP, tập hợp và truy vấn khối lượng dữ liệu lớn | Mô hình nạp dữ liệu và chi phí compute/storage |
| **AWS Glue + Amazon Athena** | Chuẩn bị/catalog dữ liệu + truy vấn dữ liệu trong S3 | Phân tích ad hoc trên data lake, không muốn quản lý máy chủ truy vấn | Chất lượng định dạng dữ liệu, partition, lượng dữ liệu quét |

**RDS và Aurora** đều phù hợp dữ liệu quan hệ; Aurora là một họ cơ sở dữ liệu riêng, không đơn giản là “bật nhanh hơn” cho mọi trường hợp RDS. **DynamoDB** không tự động tốt hơn RDS chỉ vì mang nhãn NoSQL: nếu nghiệp vụ có quan hệ phức tạp và giao dịch nhiều bảng, mô hình quan hệ có thể dễ triển khai và duy trì hơn.

### 2.4. Mạng, truy cập và phân phối nội dung

| Dịch vụ | Vai trò | Khi thường dùng |
| --- | --- | --- |
| **Amazon VPC** | Mạng logic riêng trong một Region, chia subnet, route, security group | Cách ly workload, phân vùng public/private, kiểm soát đường đi |
| **Elastic Load Balancing: ALB/NLB** | ALB định tuyến HTTP(S) tầng 7; NLB phục vụ kết nối tầng 4 như TCP/UDP | Nhiều instance/container cần điểm vào và phân tải |
| **Amazon Route 53** | DNS và điều hướng tên miền | Gắn tên miền với ứng dụng/điểm vào; dùng chính sách định tuyến phù hợp |
| **Amazon CloudFront** | CDN phân phối nội dung gần người dùng, tích hợp lớp bảo vệ/điểm edge | Nội dung tĩnh, website, API cần cache hoặc giảm độ trễ toàn cầu |
| **Amazon API Gateway** | Điểm vào API quản lý với tính năng định tuyến, xác thực/giới hạn | Backend Lambda hoặc dịch vụ HTTP cần quản lý API |
| **NAT Gateway** | Cho tài nguyên trong private subnet đi ra ngoài theo định tuyến | Workload private cần truy cập outbound Internet; chú ý chi phí |
| **VPC Endpoints / AWS PrivateLink** | Kết nối private tới dịch vụ được hỗ trợ mà không cần đi qua Internet công cộng | Truy cập S3 hoặc các API dịch vụ từ mạng private, giảm phơi lộ |
| **AWS Transit Gateway / Site-to-Site VPN / Direct Connect** | Kết nối nhiều VPC và/hoặc hạ tầng tại chỗ | Hệ thống nhiều mạng, hybrid cloud hoặc nhu cầu đường kết nối riêng |

Một **public subnet** có tuyến đến Internet Gateway; một **private subnet** không có tuyến trực tiếp ra Internet Gateway. Cho một EC2 vào subnet private không tự động bảo đảm dữ liệu an toàn: còn phải kiểm tra security group, IAM, ACL, định tuyến, endpoint và cổng ứng dụng.

### 2.5. Tích hợp ứng dụng và xử lý sự kiện

| Dịch vụ | Mô hình | Chọn khi | Ví dụ |
| --- | --- | --- | --- |
| **Amazon SQS** | Hàng đợi message; consumer kéo và xử lý | Tách producer/worker, đệm tải, retry bất đồng bộ | Sau khi thanh toán, xếp việc tạo PDF |
| **Amazon SNS** | Pub/sub đẩy thông báo tới nhiều subscriber | Một sự kiện cần phát tới nhiều đích | Đơn hàng mới gửi thông báo tới nhiều hệ thống |
| **Amazon EventBridge** | Event bus và rule định tuyến sự kiện | Routing theo thuộc tính sự kiện giữa ứng dụng/SaaS/dịch vụ AWS | OrderPlaced kích hoạt các luồng nghiệp vụ liên quan |
| **AWS Step Functions** | Điều phối workflow có các bước, nhánh, retry, state | Quy trình dài gồm nhiều tác vụ có điều kiện | Xác minh đơn → giữ hàng → ghi nhận → gửi thông báo |
| **Amazon Kinesis / Amazon MSK** | Thu nhận và xử lý dòng dữ liệu, hoặc Kafka được quản lý | Event streaming, telemetry, pipeline dữ liệu nhiều consumer | Dòng clickstream, dữ liệu cảm biến |
| **Amazon MQ** | Message broker được quản lý theo giao thức/engine hỗ trợ | Cần tương thích ứng dụng đang dùng broker truyền thống | Di chuyển hệ thống phụ thuộc AMQP/JMS và giao thức tương ứng |

SQS, SNS, EventBridge và Step Functions **không thay thế hoàn toàn nhau**. Hãy hỏi cần **xếp việc để worker xử lý**, **phát cùng một thông báo**, **định tuyến event theo rule**, hay **điều phối quy trình có trạng thái**. Một hệ thống có thể dùng EventBridge chuyển sự kiện vào SQS và để worker xử lý từ hàng đợi.

Với xử lý message, thiết kế **idempotency** (nhận lại cùng sự kiện không làm sai kết quả), retry có backoff và dead-letter queue (DLQ) ở nơi được hỗ trợ. Đừng giả định mọi hệ thống đều giao đúng một lần hoặc đúng thứ tự nếu chưa kiểm tra cấu hình và điều kiện thực tế.

### 2.6. Bảo mật, quản trị, giám sát và chi phí

| Dịch vụ | Giải quyết vấn đề |
| --- | --- |
| **AWS IAM** | Quyền người dùng, role, policy và nguyên tắc ít đặc quyền nhất |
| **AWS IAM Identity Center** | Truy cập và đăng nhập tập trung cho nhân sự, đặc biệt trong môi trường nhiều account |
| **AWS Organizations / Service Control Policies (SCP)** | Cấu trúc nhiều tài khoản và đặt giới hạn quyền ở cấp tổ chức; SCP không tự cấp quyền |
| **AWS KMS** | Quản lý và sử dụng khóa mã hóa trong các dịch vụ tích hợp |
| **AWS Secrets Manager / Systems Manager Parameter Store** | Quản lý secret hoặc tham số cấu hình; phân quyền theo độ nhạy |
| **Amazon GuardDuty / AWS Security Hub** | Phát hiện dấu hiệu bất thường và tổng hợp tư thế bảo mật/cảnh báo |
| **AWS WAF / AWS Shield** | Lọc yêu cầu web theo rule và hỗ trợ bảo vệ trước tấn công DDoS theo phạm vi dịch vụ |
| **Amazon CloudWatch** | Metric, log, alarm, dashboard; theo dõi hoạt động và lỗi |
| **AWS CloudTrail** | Ghi nhận hoạt động API và hành động quản trị để phục vụ kiểm toán/điều tra |
| **AWS Config** | Theo dõi cấu hình tài nguyên và đánh giá tuân thủ rule |
| **AWS CloudFormation / AWS CDK** | Khai báo hạ tầng bằng mã, có thể kiểm tra và triển khai lặp lại |
| **AWS Backup** | Chính sách sao lưu và điểm phục hồi tập trung |
| **AWS Cost Explorer / AWS Budgets** | Phân tích chi phí sử dụng và đặt ngưỡng cảnh báo ngân sách |
| **AWS Pricing Calculator / Compute Optimizer** | Ước lượng phương án triển khai và xem khuyến nghị điều chỉnh tài nguyên |

Ba công cụ thường cần cùng lúc: **CloudWatch** trả lời “hệ thống đang hoạt động thế nào?”, **CloudTrail** trả lời “ai/cái gì gọi API AWS?”, **AWS Config** trả lời “cấu hình tài nguyên đã thay đổi và có tuân thủ tiêu chí không?”.

## 3. Các nền tảng bắt buộc trước khi chọn dịch vụ

### 3.1. Region và Availability Zone

- **Region** là khu vực địa lý triển khai dịch vụ. Chọn theo vị trí người dùng, yêu cầu lưu trữ dữ liệu, tính sẵn có của dịch vụ, độ trễ và giá.
- **Availability Zone (AZ)** là vùng cơ sở hạ tầng riêng biệt bên trong một Region; nhiều AZ hỗ trợ thiết kế chịu lỗi của từng thành phần.
- **Multi-AZ** giúp ứng dụng tiếp tục chạy khi một AZ gặp sự cố, **nếu** các thành phần được triển khai và cấu hình đúng. Chạy hai EC2 ở một AZ không tạo khả năng chịu lỗi cấp AZ.
- **Multi-Region** phục vụ yêu cầu phục hồi sau sự cố quy mô Region hoặc phân bố địa lý, nhưng tăng độ phức tạp, đồng bộ dữ liệu và chi phí.
- Phạm vi dịch vụ không giống nhau: VPC thuộc Region, subnet thuộc AZ; EBS volume gắn với AZ; S3 bucket được tạo ở Region; IAM là dịch vụ có phạm vi toàn cục đối với tài khoản. Phải kiểm tra đặc tính cụ thể của dịch vụ.

Ví dụ: hệ thống bán hàng cần chịu lỗi một AZ có thể dùng ALB, tác vụ ECS ở ít nhất hai AZ và RDS cấu hình Multi-AZ. Vẫn phải kiểm tra đường truyền, quota, healthy check, kết nối tới DB và việc khôi phục khi gặp sự cố.

### 3.2. IAM, mạng và mô hình trách nhiệm chia sẻ

Trong mô hình **Shared Responsibility Model**, AWS chịu trách nhiệm bảo mật *của* hạ tầng đám mây; khách hàng chịu trách nhiệm bảo mật *trong* cấu hình và workload mình triển khai. Phần AWS quản lý thay đổi theo loại dịch vụ, nhưng trách nhiệm phân quyền, dữ liệu và cấu hình ứng dụng vẫn rất quan trọng.

Áp dụng tối thiểu:

1. Dùng role và thông tin xác thực tạm thời cho EC2, ECS task, Lambda; tránh nhúng access key dài hạn vào mã nguồn.
2. Giới hạn quyền IAM theo hành động/tài nguyên thực sự cần thiết, kiểm soát truy cập quản trị và bật MFA cho tài khoản phù hợp.
3. Đặt database và workload nội bộ ở subnet private khi phù hợp; chỉ mở cổng và tuyến cần thiết thông qua security group, route và endpoint.
4. Dùng TLS trong truyền tải và mã hóa dữ liệu lưu trữ khi cần; quản lý khóa và secret có phân quyền.
5. Bật logging, cấu hình theo dõi và bảo đảm có phương án phản ứng khi bị lộ thông tin xác thực.

**Phân biệt người dùng ứng dụng với IAM:** Khách đăng nhập website thường dùng một giải pháp quản lý danh tính ứng dụng, chẳng hạn Amazon Cognito hoặc nhà cung cấp danh tính tương đương. IAM chủ yếu dùng cho quyền truy cập tài nguyên và API AWS.

## 4. Quy trình chọn dịch vụ có căn cứ

Bắt đầu bằng yêu cầu đo được, rồi mới so sánh dịch vụ. Có thể đi qua sáu bước sau.

### Bước 1 — Mô tả workload

Ghi rõ chức năng chính, kiểu yêu cầu, dữ liệu, tốc độ tăng trưởng và thời gian hoạt động:

- **Traffic:** trung bình và cao điểm bao nhiêu request/giây? Có tăng vọt theo sự kiện không?
- **Tính toán:** mỗi request mất bao lâu? Chạy liên tục hay theo lịch/sự kiện? Có yêu cầu GPU, hệ điều hành hoặc giao thức đặc thù không?
- **Dữ liệu:** quan hệ chặt/SQL, key-value, file/object, hay log phân tích? Cần giao dịch và mức nhất quán nào?
- **Độ tin cậy:** mức sẵn sàng, RTO (thời gian phục hồi chấp nhận được) và RPO (mức mất dữ liệu tối đa chấp nhận được) là bao nhiêu?
- **Bảo mật:** dữ liệu nhạy cảm gì, ai có quyền, yêu cầu lưu dữ liệu ở đâu, nhật ký cần giữ bao lâu?
- **Con người:** đội ngũ có chuyên môn Kubernetes, cơ sở dữ liệu, vận hành 24/7 hay chủ yếu phát triển ứng dụng?
- **Ngân sách:** chi phí tháng bình thường, lúc cao điểm và ngưỡng cảnh báo mong muốn?

Thiếu thông tin thì nêu **giả định cần kiểm chứng**. Không nên dùng một từ chung như “cần mở rộng tốt” thay cho SLO, quy mô tải hoặc mức ngân sách.

### Bước 2 — Chọn mô hình vận hành của phần tính toán

Dùng các câu hỏi định hướng sau:

~~~text
Ứng dụng cần quyền kiểm soát OS/kernel hoặc cài agent đặc thù?
  ├─ Có → Cân nhắc EC2
  └─ Không
      ├─ Là hàm/tác vụ ngắn, độc lập, được kích hoạt bởi event?
      │    └─ Có → Cân nhắc Lambda
      └─ Là ứng dụng/container chạy lâu, nhiều HTTP request hoặc worker?
           ├─ Đội ngũ cần Kubernetes? → EKS (chọn EC2 hoặc Fargate phù hợp)
           └─ Không cần Kubernetes → ECS (ưu tiên so sánh Fargate và EC2)
~~~

Sơ đồ chỉ là **điểm khởi đầu**, không phải quy tắc tuyệt đối. Ví dụ API chạy ít traffic có thể là Lambda; API liên tục và có container hiện hữu có thể hợp ECS Fargate hơn. Quyết định cần kiểm chứng bằng benchmark và báo giá.

### Bước 3 — Chọn nơi lưu trữ và database từ đặc điểm dữ liệu

- Object/ảnh/file bất biến hoặc dữ liệu tĩnh → khảo sát **S3**.
- Đĩa cho VM → khảo sát **EBS**; nhiều máy cần filesystem dùng chung → **EFS/FSx**.
- SQL, JOIN, giao dịch nhiều thực thể → bắt đầu từ **RDS/Aurora**.
- Truy cập theo khóa với access pattern được thiết kế trước → khảo sát **DynamoDB**.
- Tìm kiếm văn bản và phân tích dữ liệu đã lập chỉ mục → **OpenSearch** bổ trợ.
- Truy vấn phân tích dữ liệu lớn → **S3 + Glue + Athena** hoặc **Redshift**, tùy mô hình sử dụng.
- Cần tăng tốc truy cập lặp lại → đánh giá **ElastiCache**, đồng thời thiết kế cache invalidation.

Chọn database là quyết định kiến trúc lớn: hãy thử ít nhất các truy vấn quan trọng, điều kiện giao dịch, kế hoạch backup/restore và dự báo chi phí trước khi chốt.

### Bước 4 — Chọn giao tiếp đồng bộ hay bất đồng bộ

- Người dùng cần kết quả ngay → HTTP(S), thường kết hợp API Gateway hoặc ALB với backend.
- Công việc có thể hoàn tất sau → đưa vào **SQS**, để worker xử lý độc lập và cập nhật trạng thái.
- Một sự kiện cần thông báo cho nhiều nơi → khảo sát **SNS** hoặc **EventBridge** theo kiểu subscriber/routing.
- Nhiều bước có trạng thái, retry, nhánh điều kiện → **Step Functions**.
- Streaming dữ liệu cần consumer xử lý độc lập theo dòng → **Kinesis/MSK** khi thực sự có yêu cầu.

### Bước 5 — Kiểm tra các ràng buộc xuyên suốt

**Security:** IAM, secret, mã hóa, VPC, quyền truy cập, audit. **Reliability:** đa AZ, retry, backup/restore, failover. **Observability:** metric, log, tracing, alarm. **Operations:** CI/CD và Infrastructure as Code. **Cost:** phí tài nguyên, lưu trữ, dữ liệu truyền, log, request, NAT, dự phòng và môi trường không sản xuất.

Nếu một phương án không đáp ứng ràng buộc bắt buộc, loại khỏi danh sách dù giá rẻ hoặc cấu hình đơn giản.

### Bước 6 — So sánh, thử nghiệm và ghi quyết định

Lập bảng lựa chọn ngắn, chỉ dùng dữ liệu đã kiểm chứng. Ví dụ cho API HTTP cần chạy container lâu dài:

| Tiêu chí | ECS trên Fargate | ECS trên EC2 | EKS |
| --- | --- | --- | --- |
| Công sức quản lý máy chủ | Thấp | Cao hơn | Cao hơn, gồm cả yếu tố Kubernetes |
| Tận dụng container hiện hữu | Tốt | Tốt | Tốt |
| Tùy biến máy chủ | Hạn chế hơn | Rộng | Phụ thuộc loại node và cấu hình |
| Kỹ năng nền tảng cần có | ECS/task/network | ECS + vận hành EC2 | Kubernetes + vận hành |
| Phù hợp khi | Nhóm nhỏ, muốn giảm vận hành | Tải ổn định, cần kiểm soát/cân đối chi phí | Tổ chức đã chuẩn hóa Kubernetes |

**Quyết định mẫu:** “Chọn ECS trên Fargate cho API container vì đội ngũ nhỏ, không cần Kubernetes và muốn hạn chế quản lý EC2. Kiểm chứng bằng thử tải giờ cao điểm, thời gian deploy, mức tiêu thụ CPU/RAM và dự toán chi phí theo tháng. Nếu chi phí duy trì liên tục vượt ngưỡng, so sánh lại với ECS trên EC2.” Đây là quyết định có **giả định, bằng chứng cần thu thập và điều kiện xem xét lại**, không chỉ là tên dịch vụ.

## 5. Ba ví dụ lựa chọn kiến trúc

### 5.1. Website và API bán hàng mới, lưu lượng thất thường

**Yêu cầu giả định:** đội phát triển nhỏ; giao diện web, API xử lý đơn giản, ảnh sản phẩm, thông báo sau khi tạo đơn; tải tăng theo chiến dịch. Dữ liệu giao dịch có quan hệ phức tạp hay không phải được xác định trước.

~~~mermaid
flowchart LR
    U[Người dùng] --> CF[CloudFront]
    CF --> FE[S3: tệp frontend]
    U --> APIGW[API Gateway]
    APIGW --> L[Lambda: API]
    L --> DB[(DynamoDB hoặc RDS)]
    L --> Q[SQS: việc hậu xử lý]
    Q --> W[Lambda: worker]
    W --> S3[S3: tệp, hóa đơn]
    L --> CW[CloudWatch: log, metric]
    W --> CW
~~~

**Lý do chọn:** S3 + CloudFront cho frontend tĩnh; API Gateway + Lambda khi mỗi yêu cầu có xử lý ngắn và tải biến động; SQS tách công việc hậu xử lý để API trả lời nhanh; S3 lưu object; CloudWatch theo dõi. **DynamoDB chỉ phù hợp nếu** mô hình khóa và truy vấn đáp ứng nghiệp vụ. Nếu cần JOIN và giao dịch quan hệ phức tạp, chọn RDS/Aurora và xử lý cấu hình kết nối/scale phù hợp với Lambda.

**Điểm kiểm chứng:** latency p95/p99, cold start, retry có idempotency, lỗi worker/DLQ, quyền IAM của từng hàm, dự toán request và log. Cần cấu hình truy cập S3 riêng tư cho CloudFront theo cơ chế hiện hành, không công khai bucket một cách tùy tiện.

### 5.2. Hệ thống đơn hàng dùng container và SQL, chạy liên tục

**Yêu cầu giả định:** API chạy suốt ngày, có nhiều dịch vụ và giao dịch SQL; cần chịu lỗi một AZ; đội ngũ quen Docker nhưng chưa quản trị Kubernetes.

~~~mermaid
flowchart TB
    User[Khách hàng] --> R53[Route 53]
    R53 --> CF[CloudFront / AWS WAF]
    CF --> ALB[Application Load Balancer]
    ALB --> A[ECS Fargate - AZ A]
    ALB --> B[ECS Fargate - AZ B]
    A --> DB[(RDS Multi-AZ)]
    B --> DB
    A --> Q[SQS]
    B --> Q
    Q --> Worker[ECS worker hoặc Lambda]
    A --> S3[S3: object]
    B --> S3
    A --> CW[CloudWatch]
    B --> CW
~~~

**Lý do chọn:** ECS/Fargate chạy container không phải tự quản lý node EC2; ALB health check và cân tải; triển khai task trải qua ít nhất hai AZ; RDS Multi-AZ tăng khả năng sẵn sàng của dữ liệu quan hệ; SQS tách gửi email/tạo báo cáo; S3 lưu file; WAF và CloudWatch hỗ trợ bảo vệ, giám sát.

**Chú ý:** sơ đồ mô tả thành phần logic, không chỉ ra subnet và security group. Khi triển khai, ALB thường ở public subnet, service và database ở private subnet theo yêu cầu; xác nhận DB không mở truy cập công cộng. RDS Multi-AZ là khả năng sẵn sàng, **không đồng nghĩa với read replica để tăng tải đọc**. Multi-AZ cũng không thay thế backup.

### 5.3. Báo cáo từ log và dữ liệu sự kiện

**Yêu cầu giả định:** thu thập log đơn hàng, định kỳ phân tích xu hướng, không cần truy vấn giao dịch trực tiếp trên kho log.

1. Tập trung dữ liệu thô ở **S3** (kèm phân quyền và vòng đời lưu trữ).
2. Dùng **Glue Data Catalog** và, nếu cần, job Glue để lập schema/biến đổi dữ liệu.
3. Dùng **Athena** truy vấn các tập dữ liệu trong S3; tối ưu định dạng cột và partition để giảm lượng quét.
4. Khi workload BI ổn định, nhiều phép JOIN/phân tích phức tạp hoặc có yêu cầu warehouse riêng, đánh giá **Redshift**.
5. Chỉ bổ sung **Kinesis/MSK** nếu thực sự phải thu nhận/xử lý dòng dữ liệu theo thời gian gần thực.

**Bài học:** chọn pipeline đơn giản đáp ứng mục tiêu hiện tại, bổ sung dịch vụ streaming và warehouse khi có chỉ số nhu cầu cụ thể.

## 6. Khả dụng, phục hồi và cách chọn cấu hình

Một dịch vụ được quản lý không mặc nhiên khiến **toàn ứng dụng** có độ tin cậy cao. Cần xem từng điểm có thể lỗi: điểm vào, compute, hàng đợi, database, DNS, quyền truy cập, phụ thuộc bên ngoài và thao tác con người.

| Nhu cầu | Biện pháp cần đánh giá | Điều phải thử |
| --- | --- | --- |
| Một máy/container dừng | Health check, nhiều task/instance, tự phục hồi | Dừng một instance/task và kiểm tra việc phục vụ |
| Một AZ không dùng được | Phân bố compute trên nhiều AZ, DB có cơ chế HA phù hợp | Mô phỏng failover và đo RTO |
| Dữ liệu bị xóa/sai | Backup, versioning, quyền hạn, điểm khôi phục | Khôi phục từ backup; đo RPO |
| Gọi API phụ thuộc bị lỗi | Timeout, retry có giới hạn, circuit breaker, DLQ | Kiểm thử lỗi dây chuyền và duplicate message |
| Sự cố cả Region | Kiến trúc DR liên Region theo mức độ bắt buộc | Diễn tập chuyển vùng, đồng bộ dữ liệu và DNS |

**RTO** (Recovery Time Objective) là thời gian tối đa chấp nhận để phục hồi. **RPO** (Recovery Point Objective) là khoảng dữ liệu tối đa có thể mất khi phục hồi. Ví dụ RTO 1 giờ và RPO 15 phút cần được chứng minh bằng khôi phục thử, không thể suy ra chỉ vì đã bật tính năng backup hoặc Multi-AZ.

## 7. Chi phí: tính tổng chi phí của một luồng sử dụng

AWS tính phí theo dịch vụ và kiểu tài nguyên. Giá khác nhau theo Region, cấu hình, mức sử dụng và thời điểm; cần dùng **AWS Pricing Calculator** và theo dõi hóa đơn/Cost Explorer thực tế. Một kiến trúc “serverless” vẫn có thể tốn đáng kể nếu có nhiều yêu cầu, truyền dữ liệu lớn hoặc lưu log lâu.

Những khoản thường bị quên:

- Compute chạy liên tục, dung lượng cấp phát, số AZ, autoscaling và tài nguyên rảnh.
- Lưu trữ: dung lượng, số request, bản sao, backup/snapshot, thời gian giữ.
- Truyền dữ liệu ra Internet, giữa Region hoặc giữa AZ theo chính sách tính phí từng dịch vụ.
- NAT Gateway, địa chỉ IPv4 công cộng, load balancer và endpoint mạng.
- CloudWatch log ingestion/retention, tracing, metrics tùy chỉnh.
- Database dự phòng, replica, I/O và số kết nối; quy mô môi trường development/staging.

**Cách quản lý:** gắn tag chi phí theo dự án/môi trường, đặt AWS Budgets và cảnh báo, dùng Cost Explorer phân tích theo thời gian, đặt lifecycle cho dữ liệu ít dùng, đặt log retention, tối ưu instance/compute khi có đo lường. Các mô hình cam kết sử dụng như Savings Plans hoặc Reserved Instances chỉ phù hợp khi hiểu tải nền và điều kiện áp dụng; không được xem như giảm giá tự động cho mọi dịch vụ.

Để ra quyết định, so sánh **chi phí sở hữu** chứ không chỉ giá compute. EC2 có thể rẻ hơn theo một cấu hình chạy liên tục nhưng đòi hỏi công vận hành, cập nhật bảo mật và hệ thống autoscaling. Ngược lại, Fargate/Lambda giảm phần việc vận hành nhưng biểu giá và giới hạn phù hợp với kiểu tải khác nhau.

## 8. Những nhầm lẫn phổ biến khi chọn AWS

| Nhầm lẫn | Cách hiểu chính xác hơn |
| --- | --- |
| “Serverless nghĩa là không cần thiết kế vận hành.” | Vẫn cần IAM, observability, concurrency/quota, retry, bảo mật và ngân sách. |
| “Dùng EKS chắc chắn hiện đại hơn ECS.” | Kubernetes chỉ có lợi rõ khi yêu cầu/kỹ năng hệ sinh thái đủ lớn để bù độ phức tạp. |
| “DynamoDB thay được mọi cơ sở dữ liệu SQL.” | Kiểu truy vấn, giao dịch, mô hình khóa và tính nhất quán quyết định độ phù hợp. |
| “S3 giống ổ đĩa gắn vào máy ảo.” | S3 là object storage qua API; EBS/EFS giải quyết các nhu cầu block/file khác. |
| “Có hai EC2 là đã Multi-AZ.” | Phải đặt ở hai AZ và bảo đảm cả điểm vào, dữ liệu, mạng đều chịu lỗi tương ứng. |
| “Multi-AZ là có backup.” | HA, backup và disaster recovery giải quyết các dạng lỗi khác nhau. |
| “Đưa database vào private subnet là đủ an toàn.” | Còn IAM, security group, xác thực, mã hóa, vá lỗi và theo dõi. |
| “Dùng mỗi CloudWatch là đủ audit toàn AWS.” | Cần phân biệt metric/log ứng dụng với CloudTrail và trạng thái cấu hình từ AWS Config. |
| “Chỉ cần nhìn giá máy chủ.” | Chi phí lưu trữ, network, request, log, dự phòng và nhân công vận hành đều đáng kể. |

## 9. Checklist đánh giá một phương án AWS

Trước khi chốt lựa chọn, nên có bằng chứng trả lời được:

- [ ] Nhu cầu nghiệp vụ, lưu lượng bình thường/cao điểm và mức độ nhạy cảm dữ liệu đã được mô tả.
- [ ] Đã xác định Region dựa trên độ trễ, yêu cầu dữ liệu, dịch vụ hỗ trợ và chi phí.
- [ ] Có lý do chọn EC2, container hoặc Lambda; đã nêu rõ công sức vận hành.
- [ ] Đã chọn S3/EBS/EFS theo kiểu lưu trữ và chọn database theo mẫu truy vấn/giao dịch.
- [ ] Đã phân biệt đồng bộ và bất đồng bộ; có timeout, retry, idempotency khi cần.
- [ ] IAM least privilege, secret, mã hóa, VPC và chính sách public/private đã được xét.
- [ ] Đã định nghĩa SLO, RTO, RPO; có chiến lược HA, backup và kiểm thử restore.
- [ ] CloudWatch metric/log/alarm và CloudTrail audit được cấu hình theo nhu cầu.
- [ ] Đã ước lượng đủ compute, database, request, storage, network và log; có budget alert.
- [ ] Có cách triển khai lặp lại (IaC), thử tải và điều kiện xem xét lại quyết định.

**Bài tập áp dụng:** Với một dịch vụ nhận ảnh người dùng, tạo thumbnail và trả URL để hiển thị toàn cầu, hãy viết hai phương án: (A) xử lý theo sự kiện với S3 + Lambda + CloudFront; (B) worker container với SQS + ECS/Fargate + S3 + CloudFront. So sánh theo kích thước/tần suất file, độ trễ, thời gian xử lý, quyền truy cập, retry và tổng chi phí. Không có phương án nào tốt hơn mọi trường hợp.

## 10. Kết luận

Cách chọn dịch vụ AWS bền vững là **xác định yêu cầu → chọn nhóm năng lực → cân nhắc mô hình vận hành → kiểm chứng bảo mật/khả dụng/chi phí → thử nghiệm và đo lường**. Với người mới, nên bắt đầu từ những khối nền tảng: Region/AZ, IAM, VPC, compute, storage, database, integration và CloudWatch/CloudTrail. Sau đó mở rộng khi có nhu cầu thực tế. Một kiến trúc tốt không nhất thiết dùng nhiều dịch vụ; nó đáp ứng rõ ràng yêu cầu hiện tại và có đường nâng cấp khi các giả định thay đổi.

**Tài liệu tra cứu khi triển khai:** AWS Service Catalog trên trang sản phẩm AWS, tài liệu từng dịch vụ, AWS Well-Architected Framework, AWS Shared Responsibility Model và AWS Pricing Calculator. Tính sẵn có của dịch vụ, quota, khả năng tích hợp và biểu giá cần được kiểm tra theo Region tại thời điểm triển khai.

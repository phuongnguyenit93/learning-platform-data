# Mô hình trách nhiệm chia sẻ trên AWS

> **Thuộc chương:** Tổng quan AWS  
> **Phạm vi:** CLOUD_PROVIDERS_AWS — tìm hiểu hệ sinh thái Amazon Web Services (AWS), từ Region/AZ, IAM, VPC đến tính toán, lưu trữ, cơ sở dữ liệu và serverless; biết thiết kế ứng dụng an toàn, có giám sát, khả năng phục hồi và kiểm soát chi phí.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích mô hình **Shared Responsibility Model** và phân biệt *security **of** the cloud* với *security **in** the cloud*.
2. Xác định phần việc của AWS và khách hàng trên các dịch vụ phổ biến như EC2, S3, RDS, Lambda và Fargate.
3. Áp dụng mô hình vào việc cấu hình IAM, mạng, mã hóa, logging, sao lưu, phục hồi và tuân thủ.
4. Phân tích sự cố để biết bên nào vận hành lớp hạ tầng liên quan và khách hàng phải thực hiện hành động bảo vệ nào.

## 1. Vì sao cần mô hình trách nhiệm chia sẻ?

Khi đặt ứng dụng trong trung tâm dữ liệu tự vận hành, doanh nghiệp thường phải quản lý từ cửa ra vào phòng máy, điện, thiết bị, mạng, hệ điều hành đến dữ liệu và ứng dụng. Khi chuyển lên AWS, AWS tiếp nhận một phần lớn hạ tầng ấy; tuy nhiên, **việc sử dụng AWS không tự động khiến ứng dụng và dữ liệu của khách hàng an toàn**.

AWS gọi cách phân định này là **mô hình trách nhiệm chia sẻ (AWS Shared Responsibility Model)**:

- **AWS chịu trách nhiệm về bảo mật *của* đám mây (security of the cloud):** bảo vệ và vận hành cơ sở hạ tầng cung cấp dịch vụ AWS.
- **Khách hàng chịu trách nhiệm về bảo mật *trong* đám mây (security in the cloud):** bảo vệ dữ liệu, danh tính, cấu hình và các thành phần phần mềm mà khách hàng kiểm soát.

Đây là cách xác định **ranh giới vận hành**, không phải một phép chia trách nhiệm theo tỷ lệ 50/50. Tỷ lệ công việc khách hàng phải quản lý thay đổi theo dịch vụ được sử dụng.

**Ví dụ mở đầu:** AWS giữ cho phần cứng lưu trữ Amazon S3 được vận hành và bảo vệ. Nhưng nếu một người quản trị cấp quyền đọc đối tượng cho mọi người trên Internet, AWS không thể biết nội dung đó có được phép công khai theo chính sách của doanh nghiệp hay không. Quyết định cấp quyền và hậu quả của cấu hình ấy thuộc phạm vi khách hàng.

## 2. Hai lớp trách nhiệm chính

### 2.1. AWS: bảo mật của đám mây

AWS chịu trách nhiệm đối với nền tảng mà dịch vụ đám mây chạy trên đó, ví dụ:

| Thành phần | Vai trò điển hình của AWS |
| --- | --- |
| Trung tâm dữ liệu | Kiểm soát tiếp cận vật lý, nguồn điện, làm mát và vận hành cơ sở vật chất. |
| Phần cứng | Quản lý máy chủ, thiết bị lưu trữ, thiết bị mạng và thay thế phần cứng lỗi. |
| Hạ tầng mạng AWS | Vận hành lớp mạng vật lý, hệ thống kết nối và cơ sở hạ tầng của AWS. |
| Ảo hóa, nền tảng dịch vụ | Bảo vệ và bảo trì lớp nền bên dưới các tài nguyên khách hàng, gồm hypervisor và hạ tầng liên quan khi áp dụng. |
| Dịch vụ được quản lý | Vận hành các lớp hạ tầng và phần mềm nền được AWS cam kết quản lý riêng cho từng dịch vụ. |

AWS xây dựng các Region và Availability Zone (AZ) để cung cấp các lựa chọn về vị trí và khả năng chịu lỗi. **AWS vận hành hạ tầng AZ; khách hàng quyết định có triển khai ứng dụng qua nhiều AZ, có sao lưu và có thử khôi phục hay không.**

### 2.2. Khách hàng: bảo mật trong đám mây

Những việc khách hàng thường chịu trách nhiệm:

| Thành phần | Câu hỏi khách hàng cần giải quyết |
| --- | --- |
| Dữ liệu | Dữ liệu nhạy cảm ở đâu? Ai được đọc? Lưu trong bao lâu? Khi nào phải xóa? |
| Danh tính và quyền truy cập | Ai hoặc workload nào được phép thực hiện hành động gì? Có MFA, phân quyền tối thiểu và kiểm soát thông tin xác thực không? |
| Cấu hình tài nguyên | Bucket S3, Security Group, public endpoint, database và role có được cấu hình đúng không? |
| Ứng dụng | Mã nguồn, thư viện, API, truy vấn dữ liệu và xác thực người dùng có an toàn không? |
| Hệ điều hành do khách hàng quản lý | Máy EC2 có được cập nhật bản vá, bảo vệ cấu hình, chống mã độc phù hợp không? |
| Mã hóa và quản lý khóa | Dữ liệu có được bảo vệ khi truyền và khi lưu trữ? Quyền dùng khóa KMS được cấp cho ai? |
| Logging, giám sát và phản ứng | Có đủ nhật ký để phát hiện, điều tra, cảnh báo và xử lý sự cố không? |
| Sao lưu và khôi phục | Có chiến lược backup, RPO/RTO và diễn tập khôi phục đáp ứng yêu cầu kinh doanh không? |
| Tuân thủ | Có đáp ứng các quy định và chính sách áp dụng cho chính dữ liệu, sản phẩm và ngành kinh doanh không? |

Không phải khách hàng trực tiếp thực hiện *mọi* tác vụ trong bảng ở *mọi* dịch vụ. Chẳng hạn AWS vá hệ điều hành hạ tầng của RDS, trong khi khách hàng tự vá hệ điều hành khách (guest OS) trên EC2 thông thường.

### 2.3. Sơ đồ ranh giới

~~~mermaid
flowchart TB
    subgraph AWS["AWS — Security OF the cloud"]
        A["Cơ sở vật chất và phần cứng"]
        B["Mạng và nền tảng ảo hóa của AWS"]
        C["Lớp nền dịch vụ AWS quản lý"]
    end
    subgraph CUSTOMER["Khách hàng — Security IN the cloud"]
        D["Dữ liệu và danh tính IAM"]
        E["Quyền truy cập, cấu hình mạng và mã hóa"]
        F["Ứng dụng, giám sát, sao lưu và phục hồi"]
        G["Hệ điều hành/ứng dụng tự quản lý nếu dùng EC2"]
    end
    AWS --> CUSTOMER
~~~

Sơ đồ là mô hình khái quát: **đường phân chia chi tiết phụ thuộc từng dịch vụ**. Chẳng hạn khách hàng phải quản lý guest OS khi dùng EC2, nhưng không trực tiếp quản lý hệ điều hành của máy chủ chạy Lambda.

## 3. Ranh giới thay đổi như thế nào theo dịch vụ?

Mức độ quản lý được AWS tiếp nhận thường tăng lên khi đi từ máy chủ ảo tự quản lý sang các dịch vụ được quản lý và serverless. Khách hàng vẫn sở hữu trách nhiệm về dữ liệu, danh tính, cấu hình và logic ứng dụng.

| Dịch vụ | AWS quản lý điển hình | Khách hàng quản lý điển hình |
| --- | --- | --- |
| **Amazon EC2** | Trung tâm dữ liệu, máy chủ vật lý, mạng hạ tầng, hypervisor. | Guest OS và bản vá, ứng dụng, cấu hình instance, Security Group, quyền IAM, dữ liệu, sao lưu. |
| **Amazon S3** | Hạ tầng dịch vụ lưu trữ, thiết bị và vận hành nền tảng S3. | Dữ liệu/đối tượng, bucket policy, IAM, quyền công khai, mã hóa và quyền dùng khóa, versioning/lifecycle theo yêu cầu. |
| **Amazon RDS** | Hạ tầng máy chủ, hệ điều hành nền, nhiều tác vụ vận hành cơ sở dữ liệu do dịch vụ đảm nhận. | Tài khoản và phân quyền DB, schema/truy vấn, cấu hình được phép, lựa chọn phiên bản/nâng cấp theo dịch vụ, bảo mật mạng, dữ liệu, thiết lập backup/HA. |
| **AWS Lambda** | Hạ tầng tính toán, máy chủ và môi trường thực thi được dịch vụ quản lý; runtime do AWS cung cấp theo chính sách cập nhật áp dụng. | Function code, thư viện/phụ thuộc và các bản vá liên quan, execution role, secret, cấu hình sự kiện, kết nối mạng, nhật ký và dữ liệu. |
| **Amazon ECS trên AWS Fargate** | Máy chủ nền, hạ tầng chạy container và hệ điều hành host. | Container image, package trong image, ứng dụng, IAM task role, network, cấu hình task, dữ liệu và quan sát hệ thống. |
| **Amazon EKS** | Control plane Kubernetes được AWS quản lý. | Workload, RBAC, cấu hình cluster, network policy, quyền truy cập và, nếu dùng EC2 worker node tự quản lý, cả node OS và bản vá của node. |

**Lưu ý:** Mỗi dịch vụ có cơ chế cập nhật phiên bản, bản vá và cấu hình cụ thể; không nên suy rằng cứ có chữ “managed” là khách hàng không còn trách nhiệm đối với phần mềm hay cấu hình.

### 3.1. EC2: linh hoạt đi kèm trách nhiệm lớn

Với EC2, AWS cung cấp hạ tầng cho máy ảo. Khách hàng chọn Amazon Machine Image (AMI), hệ điều hành, gói phần mềm, dịch vụ chạy trên máy và cách mở cổng mạng.

Ví dụ một nhóm phát triển chạy website trên EC2:

- AWS sửa lỗi máy chủ vật lý bên dưới một instance khi có sự cố hạ tầng.
- Nhóm phát triển phải cập nhật hệ điều hành và thư viện ứng dụng, giới hạn cổng SSH, quản lý người dùng và bảo vệ secret.
- Nếu máy chủ bị khai thác do dịch vụ ứng dụng tồn tại lỗ hổng chưa vá, việc chạy trên EC2 không chuyển trách nhiệm vá ứng dụng sang AWS.
- Nếu cần tránh gián đoạn khi một AZ gặp sự cố, nhóm phát triển phải **thiết kế và triển khai** nhiều instance/AZ, load balancing và cơ chế phục hồi phù hợp.

Khi sử dụng AMI do bên thứ ba cung cấp, khách hàng còn phải đánh giá nguồn image và trách nhiệm cập nhật các thành phần bên trong.

### 3.2. RDS: AWS vận hành lớp database nền, khách hàng bảo vệ dữ liệu

Amazon RDS hỗ trợ tạo và vận hành cơ sở dữ liệu quan hệ. AWS xử lý nhiều tác vụ như cấp phát hạ tầng và các phần vận hành/bảo trì theo chức năng RDS. Tuy vậy, khách hàng vẫn phải:

1. Đặt cơ sở dữ liệu trong mạng phù hợp, kiểm tra thuộc tính **PubliclyAccessible** và chỉ cho phép ứng dụng cần thiết kết nối.
2. Cấp tài khoản DB theo nguyên tắc tối thiểu quyền; giữ secret trong dịch vụ quản lý bí mật phù hợp.
3. Chọn cấu hình mã hóa, thời gian giữ backup, Multi-AZ và bảo trì/nâng cấp theo yêu cầu ứng dụng.
4. Kiểm soát schema, truy vấn, an toàn ứng dụng và thử nghiệm việc khôi phục dữ liệu.

**Hiểu đúng về backup:** RDS hỗ trợ automated backup, nhưng thời gian giữ và các tùy chọn phụ thuộc cấu hình/loại dịch vụ. Có khả năng tạo backup không đồng nghĩa ứng dụng đã đáp ứng RPO, RTO hoặc có kế hoạch khôi phục được kiểm chứng.

### 3.3. S3: dịch vụ bền vững không có nghĩa cấu hình luôn đúng

Với S3, hai phạm vi rất dễ bị nhầm:

- AWS thiết kế và vận hành hạ tầng lưu trữ của dịch vụ.
- Khách hàng quyết định **ai được truy cập object**, cách chia sẻ dữ liệu, thời gian lưu và cách khôi phục khi xóa hoặc ghi đè ngoài ý muốn.

S3 hiện hỗ trợ mã hóa phía máy chủ mặc định cho các object mới bằng SSE-S3; điều này **không** thay thế việc đánh giá bucket policy, IAM, dữ liệu nhạy cảm hoặc nhu cầu dùng khóa do khách hàng quản lý. Tương tự, chức năng chặn truy cập công khai (S3 Block Public Access) cần được kiểm tra cả ở cấp tài khoản và bucket trong môi trường đang vận hành, nhất là với tài nguyên được tạo từ trước hay cấu hình phức tạp.

Phiên bản hóa (versioning), replication, Object Lock và lifecycle đều giải quyết những yêu cầu khác nhau. Chúng cần được thiết kế phù hợp thay vì mặc định coi bản sao hoặc khả năng lưu trữ của AWS là một chiến lược backup hoàn chỉnh.

### 3.4. Lambda và serverless: ít quản lý máy chủ, vẫn phải bảo mật ứng dụng

AWS Lambda không yêu cầu khách hàng trực tiếp quản trị máy chủ host. Nhưng một Lambda function vẫn có thể bị khai thác nếu:

- Mã xử lý input thiếu kiểm tra, dẫn tới injection hay lộ dữ liệu.
- Execution role cho phép đọc tất cả bucket hoặc xóa nhiều tài nguyên dù function chỉ cần ghi một object.
- Token, password hoặc khóa API bị viết cứng trong mã nguồn hay in ra log.
- Thư viện trong deployment package/container image có lỗ hổng chưa được cập nhật.
- Endpoint/API kích hoạt function thiếu xác thực, rate limiting hoặc giám sát phù hợp.

Vì vậy **serverless giảm việc vận hành hạ tầng** nhưng không xóa bỏ trách nhiệm về code, dependency, identity và dữ liệu.

## 4. Áp dụng trách nhiệm chia sẻ theo từng trụ cột bảo mật

### 4.1. IAM: AWS cung cấp công cụ, khách hàng quyết định quyền

AWS IAM hỗ trợ user, role, policy và cơ chế cấp thông tin xác thực. Khách hàng chịu trách nhiệm xác định danh tính nào có quyền gì. Những cách làm cơ bản:

- Bảo vệ tài khoản root, sử dụng MFA và hạn chế dùng root cho công việc hằng ngày.
- Ưu tiên role/temporary credentials cho EC2, Lambda và ứng dụng; tránh phân phối access key dài hạn khi không cần.
- Áp dụng **least privilege**: chỉ cấp action và resource thật sự cần thiết, rà soát quyền định kỳ.
- Kiểm soát phân quyền giữa các account và yêu cầu xác thực đủ mạnh cho con người.
- Giám sát hành vi bất thường và thu hồi quyền khi nhân sự hoặc workload không còn nhu cầu.

Ví dụ: một function chỉ cần đọc báo cáo từ một prefix trong bucket thì policy dưới đây giới hạn quyền đọc ở prefix đó.

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:GetObject"],
      "Resource": "arn:aws:s3:::example-private-reports/approved/*"
    }
  ]
}
~~~

Đây là **đoạn minh họa quyền IAM**, không phải cấu hình hoàn chỉnh cho mọi ứng dụng. Quyền thực tế còn phụ thuộc các chính sách liên quan như bucket policy, resource policy, SCP, permission boundary, explicit deny và điều kiện môi trường. Đoạn policy không cho phép liệt kê toàn bộ bucket.

### 4.2. VPC, Security Group và NACL

AWS vận hành mạng nền. Trong Amazon VPC, khách hàng quyết định subnet, route table, kết nối Internet, Security Group, network ACL (NACL) và đường đi từ ứng dụng đến tài nguyên.

- **Security Group:** bộ lọc mạng có trạng thái (stateful) gắn với tài nguyên được hỗ trợ; khách hàng tự định nghĩa inbound/outbound rules.
- **Network ACL:** bộ lọc không trạng thái (stateless) ở cấp subnet; cần xem cả luồng đi và về.
- **Public/private subnet:** phụ thuộc thiết kế định tuyến và kết nối; đặt một máy trong VPC không có nghĩa nó mặc nhiên bị cô lập Internet.
- **Network segmentation:** chỉ mở đường kết nối thật sự cần thiết từ load balancer tới ứng dụng và từ ứng dụng tới database.

Ví dụ tốt hơn cho website là cho phép HTTPS từ Internet vào Application Load Balancer, chỉ cho phép lưu lượng của load balancer đến app, và chỉ cho app kết nối đến RDS ở cổng cơ sở dữ liệu. Không nên mở cổng quản trị hoặc database ra mọi địa chỉ chỉ để tiện thử nghiệm.

### 4.3. Mã hóa và khóa

Mã hóa cần xem ở hai trạng thái:

| Trường hợp | Biện pháp thường dùng | Trách nhiệm cần làm rõ |
| --- | --- | --- |
| **Data in transit** | HTTPS/TLS, kết nối mã hóa tới database và các API. | Khách hàng cấu hình endpoint, phiên bản/chính sách TLS phù hợp và xác minh kết nối dùng TLS. |
| **Data at rest** | Mã hóa lưu trữ của S3, EBS, RDS hoặc dịch vụ tương ứng. | Khách hàng kiểm tra chế độ mã hóa phù hợp, quyền đọc dữ liệu và yêu cầu dùng khóa. |
| **Quản lý khóa** | AWS KMS và các tùy chọn khóa do AWS/khách hàng quản lý. | AWS vận hành nền tảng KMS; khách hàng quản lý quyền dùng khóa, key policy và vòng đời khóa theo loại khóa đã chọn. |

**Mã hóa không thay thế phân quyền.** Một ứng dụng hoặc IAM role được phép giải mã và đọc dữ liệu vẫn có thể làm lộ dữ liệu nếu quyền bị cấp quá rộng hoặc tài khoản bị chiếm đoạt.

### 4.4. Giám sát, nhật ký và xử lý sự cố

AWS vận hành dịch vụ như Amazon CloudWatch, AWS CloudTrail, Amazon GuardDuty và AWS Config. Nhưng khách hàng phải xác định việc bật/thiết lập phù hợp, phạm vi thu thập, thời gian lưu trữ, cảnh báo và quy trình xử lý.

Một phương án cơ bản gồm:

1. Thu thập sự kiện API và thay đổi cấu hình cần thiết; bảo vệ quyền chỉnh sửa/xóa log.
2. Theo dõi lỗi ứng dụng, mức sử dụng tài nguyên, đăng nhập bất thường và thay đổi IAM nhạy cảm.
3. Gửi cảnh báo tới đầu mối trực vận hành; có hướng dẫn triage và ứng phó.
4. Kiểm tra định kỳ khả năng điều tra từ log thay vì chỉ bật dịch vụ rồi để đó.

Không nên đồng nhất **có dịch vụ logging** với **đã có logging đáp ứng yêu cầu**. Ví dụ, CloudTrail có Event History cho một tập sự kiện quản lý trong thời gian giới hạn, còn nhu cầu lưu trữ lâu hơn, ghi nhận data events hay tập trung log đa account đòi hỏi cấu hình bổ sung.

### 4.5. Khả năng sẵn sàng, phục hồi và chi phí

AWS quản lý hạ tầng Region/AZ và cung cấp dịch vụ cho hệ thống có thể mở rộng. Khách hàng quyết định kiến trúc ứng dụng và mức chịu lỗi cần đạt:

- **High availability:** cân nhắc nhiều AZ cho các thành phần quan trọng, health check, load balancing và cơ chế failover.
- **Disaster recovery:** định nghĩa RPO (mức mất dữ liệu tối đa chấp nhận) và RTO (thời gian khôi phục tối đa), sau đó chọn backup/cross-Region replication nếu cần.
- **Thử nghiệm:** diễn tập restore và chuyển đổi dự phòng để xác nhận mục tiêu thực tế.
- **Chi phí:** lựa chọn Multi-AZ, backup retention, logging, replication và mã hóa có thể làm tăng chi phí. Cần cân bằng yêu cầu kinh doanh, rủi ro và ngân sách.

Một hệ thống đặt toàn bộ ứng dụng và database trong một AZ vẫn có thể gián đoạn khi AZ đó gặp sự cố, dù AWS đang thực hiện đúng trách nhiệm vận hành hạ tầng của mình.

## 5. Bốn tình huống dễ nhầm trách nhiệm

| Tình huống | Phân tích trách nhiệm | Hành động cần thực hiện |
| --- | --- | --- |
| S3 chứa tài liệu khách hàng có policy vô tình cho phép truy cập công khai. | AWS vận hành S3, nhưng quyền chia sẻ object là cấu hình khách hàng. | Chặn quyền sai, kiểm tra account/bucket Block Public Access, phân tích log và phạm vi dữ liệu bị ảnh hưởng. |
| EC2 chạy thư viện web có lỗ hổng đã có bản vá nhưng chưa cập nhật. | AWS quản lý host/hypervisor; khách hàng quản lý app và OS bên trong EC2. | Vá thư viện/OS, rà soát instance, khóa quyền bị lộ, tái triển khai từ image tin cậy. |
| Một AZ ngừng hoạt động làm ứng dụng đơn AZ không truy cập được. | AWS chịu trách nhiệm hạ tầng AZ; khách hàng chịu trách nhiệm lựa chọn kiến trúc chịu lỗi đáp ứng yêu cầu. | Triển khai thành phần quan trọng trên nhiều AZ và kiểm thử failover. |
| Lambda dùng IAM role quá rộng, bị lợi dụng để đọc dữ liệu ngoài phạm vi cần thiết. | AWS vận hành môi trường Lambda; khách hàng định nghĩa quyền của function và bảo vệ mã. | Thu hẹp IAM policy, điều tra CloudTrail/log, sửa code hoặc cấu hình, luân chuyển secret khi cần. |

Khi điều tra một sự cố thực tế, **trách nhiệm thường liên quan cả hai bên ở các lớp khác nhau**. Ví dụ AWS có trách nhiệm duy trì độ an toàn của dịch vụ KMS, nhưng khách hàng phải xác định quyền sử dụng khóa thích hợp. Mô hình giúp phân rõ hành động và phạm vi kiểm soát; nó không thay thế hợp đồng dịch vụ, điều khoản hỗ trợ, nghĩa vụ pháp lý hoặc quy trình ứng phó sự cố.

## 6. Thiết kế minh họa: ứng dụng web bán hàng trên AWS

Giả sử một nhóm xây dựng ứng dụng nhận đơn hàng với các thành phần:

- Application Load Balancer (ALB) nhận HTTPS.
- EC2 chạy API và xử lý nghiệp vụ ở private subnet; nếu cần phục hồi khi lỗi AZ, dùng nhiều instance và Auto Scaling phù hợp.
- Amazon RDS lưu thông tin đơn hàng, giới hạn truy cập từ ứng dụng.
- S3 lưu hóa đơn/tệp đính kèm.
- IAM role cho EC2, CloudTrail/CloudWatch để theo dõi, KMS và cơ chế backup/restore theo yêu cầu.

~~~mermaid
flowchart TB
    USER["Người dùng"] -->|HTTPS| ALB["Application Load Balancer"]
    subgraph VPC["VPC của khách hàng"]
        ALB --> APP_A["Ứng dụng EC2 — AZ A"]
        ALB --> APP_B["Ứng dụng EC2 — AZ B"]
        APP_A --> DB[("RDS — database")]
        APP_B --> DB
    end
    APP_A --> S3[("Amazon S3 — tài liệu")]
    APP_B --> S3
    LOG["CloudTrail / CloudWatch"] -.-> APP_A
    LOG -.-> APP_B
~~~

Sơ đồ chỉ mô tả **luồng logic**; đường kết nối phải được hiện thực bằng route, Security Group, endpoint/NAT và cấu hình mạng phù hợp. Nếu RDS Multi-AZ được chọn thì topology standby/failover là phần cấu hình riêng, không được mặc định từ hình vẽ.

### Ma trận phân công cho kiến trúc trên

| Hạng mục | AWS chịu trách nhiệm | Nhóm ứng dụng chịu trách nhiệm |
| --- | --- | --- |
| EC2 | Hạ tầng vật lý và ảo hóa. | Image, hệ điều hành, bản vá, ứng dụng, IAM role, security rules. |
| ALB | Hạ tầng dịch vụ load balancing. | Listener, TLS/certificate, target group, định tuyến, kiểm soát truy cập. |
| RDS | Hạ tầng và các tác vụ vận hành do RDS cung cấp. | Thiết lập database, quyền, subnet/Security Group, backup retention, Multi-AZ, restore test. |
| S3 | Nền tảng lưu trữ. | Bucket/object policy, Block Public Access, loại dữ liệu, mã hóa, lifecycle/versioning. |
| IAM | Nền tảng xác thực và cấp quyền AWS. | Role, policy, permission boundary, quản trị vòng đời danh tính. |
| Monitoring | Vận hành công cụ quan sát AWS. | Chọn log/metric, cấu hình cảnh báo, phân công trực, điều tra và phản hồi. |

### Thực hành kiểm tra cấu hình theo trách nhiệm

Đoạn AWS CLI sau chỉ **đọc cấu hình** để hỗ trợ tự đánh giá; cần AWS CLI đã được cấu hình quyền phù hợp và thay các tên định danh minh họa bằng tài nguyên thuộc môi trường của bạn.

~~~bash
# Xác nhận danh tính AWS đang dùng cho phiên làm việc.
aws sts get-caller-identity

# Xem cấu hình Block Public Access của một bucket S3.
aws s3api get-public-access-block --bucket example-private-reports

# Xem cấu hình mã hóa phía máy chủ của bucket.
aws s3api get-bucket-encryption --bucket example-private-reports

# Xem inbound rule của một Security Group.
aws ec2 describe-security-groups \
  --group-ids sg-0123456789abcdef0 \
  --query "SecurityGroups[0].IpPermissions"

# Kiểm tra các thuộc tính liên quan đến mạng, mã hóa, HA và backup của RDS.
aws rds describe-db-instances \
  --db-instance-identifier example-orders-db \
  --query "DBInstances[0].[PubliclyAccessible,StorageEncrypted,MultiAZ,BackupRetentionPeriod]"
~~~

**Cách đọc kết quả:**

- Bucket policy, IAM policy và quyền cấp tài khoản vẫn cần được xem tổng thể; một lệnh kiểm tra Block Public Access không chứng minh dữ liệu chắc chắn an toàn.
- Nếu lệnh không tìm thấy bucket, bị từ chối quyền hoặc không có cấu hình tương ứng, cần kiểm tra bối cảnh; không coi đó là bằng chứng hệ thống đã được bảo vệ.
- Với Security Group, rà soát địa chỉ nguồn, giao thức và cổng; ví dụ quyền inbound SSH từ 0.0.0.0/0 thường cần được thu hẹp.
- Với RDS, các thuộc tính trả về hỗ trợ đánh giá bước đầu. Chúng không thay thế việc kiểm tra subnet, route, parameter group, database account và diễn tập restore.

## 7. Quy trình áp dụng trong dự án thực tế

Để tránh “khoảng trống trách nhiệm”, nhóm triển khai có thể áp dụng quy trình sau.

**Bước 1 — Lập bản đồ tài sản và dữ liệu.** Liệt kê AWS account, Region, VPC, EC2, S3, RDS, Lambda, luồng dữ liệu nhạy cảm và các dịch vụ bên thứ ba. Phân loại mức độ nhạy cảm và yêu cầu lưu trữ/phục hồi.

**Bước 2 — Đọc ranh giới trách nhiệm của từng dịch vụ.** Xác định AWS quản lý lớp hạ tầng nào, nhóm ứng dụng quản lý code/config nào, những tùy chọn nào yêu cầu khách hàng chủ động bật hay cấu hình.

**Bước 3 — Gán chủ sở hữu rõ ràng.** Chỉ định ai quản lý IAM, vá ứng dụng/OS, network, database, backup, logging, khóa mã hóa và quy trình xử lý sự cố. Nếu có nhà cung cấp dịch vụ quản trị (MSP), mô tả trách nhiệm trong hợp đồng nhưng vẫn đối chiếu với nghĩa vụ của chủ AWS account.

**Bước 4 — Triển khai kiểm soát có thể kiểm tra.** Dùng hạ tầng dưới dạng mã khi phù hợp; áp dụng MFA, least privilege, private network, mã hóa, logging, kiểm tra cấu hình và tiêu chuẩn build/deploy.

**Bước 5 — Kiểm chứng và cải tiến.** Thực hiện review quyền IAM, đánh giá Security Group/S3, quét lỗ hổng image/dependency, xem lại retention, thử khôi phục, kiểm tra cảnh báo và diễn tập tình huống bị lộ credential.

| Câu hỏi kiểm tra | Bằng chứng mong đợi |
| --- | --- |
| Ai chịu trách nhiệm cập nhật hệ điều hành máy EC2? | Owner cụ thể, lịch patch và trạng thái patch được ghi nhận. |
| Có object S3 nào có thể bị truy cập ngoài dự kiến? | Kiểm tra effective access, Block Public Access và các policy liên quan. |
| Workload có quyền nhiều hơn chức năng thực tế không? | IAM review và danh sách quyền cần thiết đã phê duyệt. |
| Khi mất một AZ, ứng dụng duy trì hoạt động thế nào? | Kiến trúc Multi-AZ/failover và kết quả kiểm thử. |
| Nếu dữ liệu bị xóa nhầm, khôi phục mất bao lâu? | Backup policy, bài diễn tập restore và kết quả RPO/RTO. |
| Khi có sự cố, nhóm phát hiện và điều tra bằng dữ liệu nào? | Nguồn log, cảnh báo, thời gian lưu và runbook xử lý. |

## 8. Các hiểu lầm phổ biến

**“AWS có chứng nhận tuân thủ nên hệ thống của tôi tự động tuân thủ.”** Không đúng. Chứng nhận và báo cáo tuân thủ của AWS liên quan phạm vi dịch vụ và lớp kiểm soát được đánh giá; khách hàng vẫn phải đáp ứng yêu cầu đối với dữ liệu, danh tính, ứng dụng, cách sử dụng dịch vụ và các quy định áp dụng. AWS Artifact có thể giúp truy cập một số tài liệu tuân thủ của AWS để phục vụ đánh giá.

**“Dùng dịch vụ managed thì không cần vá gì.”** Không đúng. AWS có thể vận hành host và các phần mềm nền, nhưng khách hàng vẫn quản lý ứng dụng, dependency, cấu hình và các lịch nâng cấp/phiên bản được quyền lựa chọn.

**“Bật mã hóa là đủ.”** Không đúng. Người có quyền giải mã/đọc vẫn có thể truy cập dữ liệu; cần phân quyền đúng, bảo vệ secret, giám sát và kiểm soát truy cập.

**“Dữ liệu ở AWS thì AWS sẽ tự sao lưu và khôi phục mọi lỗi của tôi.”** Không đúng. Cơ chế backup, versioning và replication khác nhau theo dịch vụ và cấu hình. Khách hàng phải quyết định mục tiêu phục hồi, thiết lập và kiểm tra kết quả.

**“AWS cung cấp Region/AZ nên ứng dụng mặc nhiên có tính sẵn sàng cao.”** Không đúng. Thiết kế single point of failure, lựa chọn Multi-AZ/Multi-Region, khả năng mở rộng và quy trình failover vẫn thuộc phần việc thiết kế ứng dụng của khách hàng.

## 9. Tự kiểm tra kiến thức

**Câu 1.** Ai chịu trách nhiệm vá lỗ hổng trong guest OS của EC2 thông thường?  
**Đáp án:** Khách hàng; AWS quản lý lớp hạ tầng vật lý và ảo hóa bên dưới.

**Câu 2.** Dùng RDS thay vì tự cài PostgreSQL trên EC2 chuyển trách nhiệm nào sang AWS?  
**Đáp án:** Nhiều tác vụ hạ tầng, hệ điều hành nền và vận hành database do dịch vụ RDS cung cấp. Khách hàng vẫn chịu trách nhiệm về dữ liệu, cấu hình/phiên bản được phép điều chỉnh, phân quyền, kết nối và mục tiêu sao lưu/khôi phục.

**Câu 3.** AWS có chịu trách nhiệm nếu bucket S3 bị công khai do bucket policy do khách hàng cấu hình?  
**Đáp án:** Việc thiết lập policy và kiểm soát đối tượng được chia sẻ thuộc trách nhiệm khách hàng; AWS bảo vệ hạ tầng dịch vụ S3. Cần đánh giá kỹ cấu hình hiệu lực ở các lớp.

**Câu 4.** Một ứng dụng Lambda bị lộ dữ liệu vì execution role có quyền đọc toàn bộ bucket. Serverless có chuyển trách nhiệm này sang AWS không?  
**Đáp án:** Không. Khách hàng quyết định quyền IAM của function, mã ứng dụng, dependency và dữ liệu.

**Câu 5.** Một website chỉ chạy trong một AZ bị gián đoạn khi AZ có sự cố. Bài học kiến trúc quan trọng là gì?  
**Đáp án:** Trách nhiệm AWS về hạ tầng không thay thế việc khách hàng xây dựng khả năng chịu lỗi. Cần thiết kế HA theo yêu cầu, phân tán tài nguyên phù hợp và kiểm chứng failover.

## 10. Ghi nhớ

Mô hình trách nhiệm chia sẻ giúp nhóm kỹ thuật trả lời câu hỏi thực tế: **AWS bảo vệ lớp nào, còn mình phải cấu hình và vận hành lớp nào?** AWS cung cấp và bảo vệ hạ tầng đám mây. Khách hàng bảo vệ dữ liệu, danh tính, quyền truy cập, ứng dụng, cấu hình và mức độ phục hồi theo yêu cầu kinh doanh. Khi chọn dịch vụ quản lý cao hơn, một số tác vụ hạ tầng chuyển sang AWS, nhưng trách nhiệm về dữ liệu và cách sử dụng dịch vụ vẫn hiện hữu.

Trong mọi thiết kế AWS, hãy xác định trách nhiệm theo **từng dịch vụ và từng thành phần**; sau đó gắn trách nhiệm với chủ sở hữu, cấu hình có thể kiểm chứng, nhật ký giám sát, phương án sao lưu và diễn tập phục hồi. Đây là nền tảng để chọn dịch vụ đúng, vận hành an toàn và quản lý rủi ro/chi phí.

### Đọc thêm từ AWS

- [AWS Shared Responsibility Model](https://aws.amazon.com/compliance/shared-responsibility-model/) — mô hình trách nhiệm chia sẻ chính thức của AWS.
- [AWS Well-Architected — Security Pillar](https://docs.aws.amazon.com/wellarchitected/latest/security-pillar/welcome.html) — nguyên tắc thiết kế và vận hành bảo mật trên AWS.
- [Amazon S3 — Security best practices](https://docs.aws.amazon.com/AmazonS3/latest/userguide/security-best-practices.html) — hướng dẫn bảo vệ dữ liệu và cấu hình quyền truy cập S3.

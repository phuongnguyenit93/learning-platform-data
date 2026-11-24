# Cấp quyền tối thiểu để ứng dụng gọi dịch vụ cloud

Một ứng dụng chạy trên VM, container hoặc nền tảng serverless thường cần gọi các dịch vụ cloud khác: đọc file từ object storage, ghi log, lấy cấu hình, truy cập secret, gửi message vào queue hoặc truy vấn database. Để thực hiện các thao tác đó, dịch vụ phải biết **ứng dụng nào đang gọi** và **ứng dụng được phép làm gì**.

Danh tính dành cho workload (workload identity hoặc machine identity) giải quyết phần nhận diện này. Hệ thống cấp cho VM, container, function hoặc tiến trình một danh tính riêng; dịch vụ đích xác minh danh tính rồi áp dụng chính sách quyền. **Least privilege** (đặc quyền tối thiểu) yêu cầu chỉ cấp đúng các hành động, tài nguyên và điều kiện mà workload cần để hoàn thành nhiệm vụ.

Trong module **CLOUD_CORE_SERVICES_COMPUTE**, bài học này tập trung vào cách cấp quyền tối thiểu để ứng dụng gọi dịch vụ cloud. Nội dung bao gồm danh tính máy, IAM role, managed identity, service account, credential ngắn hạn, quyền theo tài nguyên, federation, bảo vệ metadata endpoint, quản lý secret, audit và quy trình kiểm thử quyền.

## 1. Vì sao ứng dụng cần danh tính riêng?

Hãy tưởng tượng một VM chạy worker xử lý ảnh. Worker cần đọc file ảnh từ một bucket, ghi ảnh thu nhỏ vào một bucket khác và gửi thông báo hoàn tất vào queue. Nếu dùng một access key có quyền quản trị toàn bộ tài khoản cloud, một lỗi trong ứng dụng hoặc một lỗ hổng bảo mật có thể làm lộ toàn bộ tài nguyên.

Thay vào đó, cấp cho worker một danh tính riêng với các quyền:

- Đọc object trong bucket ảnh đầu vào.
- Ghi object vào đúng prefix của bucket kết quả.
- Gửi message vào đúng queue xử lý ảnh.
- Không có quyền xóa bucket, tạo user IAM, đọc dữ liệu thanh toán hoặc thay đổi network.

Nếu worker bị xâm nhập, phạm vi ảnh hưởng bị giới hạn theo những quyền đã cấp. Các workload khác như API catalog, batch báo cáo và backup nên có danh tính riêng vì chúng có nhiệm vụ và phạm vi dữ liệu khác nhau.

Danh tính riêng giúp:

1. Nhận diện rõ workload nào đã gọi API.
2. Cấp quyền theo nhiệm vụ và tài nguyên cần truy cập.
3. Thu hồi hoặc thay đổi quyền của một workload mà không ảnh hưởng workload khác.
4. Tránh chia sẻ một credential giữa nhiều ứng dụng.
5. Theo dõi hoạt động qua audit log.
6. Dùng credential ngắn hạn và tự động làm mới thay cho khóa tĩnh.

Không nên coi danh tính máy là tài khoản dùng chung cho mọi tiến trình trên host. Nếu nhiều ứng dụng có mức tin cậy khác nhau cùng dùng một role rộng, mỗi ứng dụng có thể kế thừa toàn bộ quyền của role đó. Hãy tách danh tính theo workload, môi trường và ranh giới tin cậy.

## 2. Phân biệt danh tính người dùng và danh tính workload

Hệ thống cloud thường có ít nhất hai nhóm principal (chủ thể thực hiện hành động):

| Nhóm danh tính | Đại diện cho | Ví dụ |
|---|---|---|
| Human identity | Con người đăng nhập để quản trị hoặc sử dụng hệ thống | Kỹ sư cloud, quản trị viên, nhân viên vận hành |
| Workload identity | Ứng dụng hoặc tiến trình tự động gọi dịch vụ | VM chạy API, Kubernetes Pod, serverless function, pipeline CI |

Danh tính người dùng thường gắn với đăng nhập tương tác, MFA, nhóm và quy trình cấp quyền cho nhân sự. Danh tính workload thường cần hoạt động tự động, không có người ngồi nhập mật khẩu, vì vậy cần cơ chế xác thực có thể cấp và làm mới credential an toàn.

Không nên dùng tài khoản cá nhân của kỹ sư làm danh tính cho ứng dụng. Khi nhân sự nghỉ việc, đổi vai trò hoặc thay MFA, workload có thể bị gián đoạn; audit cũng khó xác định hành động đến từ con người hay từ ứng dụng.

Một số thuật ngữ quan trọng:

- **Principal:** danh tính được hệ thống bảo mật nhận diện, có thể là user, role, service account hoặc federated identity.
- **Authentication:** xác minh chủ thể thực sự là ai.
- **Authorization:** quyết định chủ thể được phép thực hiện hành động nào trên tài nguyên nào.
- **Credential:** dữ liệu dùng để chứng minh danh tính, ví dụ token, certificate hoặc access key.
- **Policy:** tập quy tắc mô tả quyền được phép hoặc bị từ chối.
- **Resource:** tài nguyên được bảo vệ, ví dụ bucket, queue, secret hoặc database.

Authentication thành công không có nghĩa ứng dụng được phép làm mọi việc. Sau khi xác minh danh tính, dịch vụ vẫn phải kiểm tra authorization cho từng hành động.

## 3. Workload identity hoạt động như thế nào?

Một mô hình phổ biến là nền tảng compute gắn một danh tính vào workload. Khi ứng dụng cần gọi dịch vụ cloud, nó yêu cầu credential tạm thời từ cơ chế danh tính của nền tảng. Credential được gửi tới dịch vụ đích; dịch vụ xác minh token hoặc chữ ký và kiểm tra policy gắn với principal.

~~~mermaid
sequenceDiagram
    participant W as VM / Container / Function
    participant I as Identity Service
    participant T as Token / Credential Service
    participant S as Cloud Service
    W->>I: Yêu cầu danh tính workload
    I->>T: Xác minh workload và quyền gắn danh tính
    T-->>W: Credential ngắn hạn
    W->>S: API request kèm credential
    S->>S: Xác minh credential và đánh giá policy
    S-->>W: Cho phép hoặc từ chối
~~~

Các bước cụ thể phụ thuộc nhà cung cấp:

1. Quản trị viên tạo role, managed identity hoặc service account.
2. Danh tính được gắn vào VM, node, Pod hoặc function; hoặc được cấp qua federation.
3. Workload lấy token/credential bằng SDK hoặc endpoint được nền tảng hỗ trợ.
4. SDK ký request hoặc gửi bearer token tới dịch vụ đích.
5. Dịch vụ xác minh credential, principal, audience, thời hạn và policy.
6. Khi credential sắp hết hạn, SDK hoặc agent lấy credential mới.

Điểm quan trọng là ứng dụng không cần lưu access key dài hạn trong source code hoặc file cấu hình. Danh tính được gắn với môi trường chạy và credential được cấp tự động trong thời gian ngắn.

## 4. Các mô hình danh tính phổ biến trên cloud

Tên gọi và cách triển khai khác nhau giữa các nhà cung cấp, nhưng ý tưởng chung là gắn một principal vào workload và cấp credential có thời hạn.

| Nền tảng | Cơ chế thường dùng | Ví dụ |
|---|---|---|
| AWS | IAM role, instance profile, task role, Lambda execution role | EC2 instance dùng role để đọc một bucket S3 |
| Microsoft Azure | Managed identity: system-assigned hoặc user-assigned | VM dùng managed identity để đọc secret từ Key Vault |
| Google Cloud | Service account gắn với VM hoặc workload identity federation | Compute Engine VM dùng service account để ghi log hoặc đọc object |
| Kubernetes | ServiceAccount kết hợp projected token và workload identity/federation của cloud | Pod đổi token Kubernetes lấy credential của cloud role |
| Nền tảng CI/CD | OIDC federation hoặc credential ngắn hạn | Pipeline triển khai chỉ được cập nhật một môi trường |

### 4.1. AWS IAM role và instance profile

IAM role là danh tính có thể được một principal tin cậy đảm nhận (assume). Role có trust policy xác định ai được phép sử dụng role và permission policy xác định role được phép làm gì.

Với EC2, instance profile là cơ chế gắn IAM role vào instance. Ứng dụng trên VM có thể lấy credential tạm thời từ EC2 instance metadata service thông qua SDK. Khi credential hết hạn, SDK tương thích có thể tự làm mới.

Các workload khác có cơ chế tương ứng:

- EC2 instance sử dụng instance profile.
- ECS task sử dụng task role để cấp quyền cho mã ứng dụng trong task.
- Lambda function sử dụng execution role.
- EKS Pod có thể dùng IAM Roles for Service Accounts (IRSA) hoặc EKS Pod Identity tùy kiến trúc.

Không nên gắn role quản trị rộng cho toàn bộ EC2 fleet chỉ để một ứng dụng đọc một bucket.

### 4.2. Azure managed identity

Managed identity cung cấp danh tính được Microsoft Entra quản lý cho tài nguyên Azure. Có hai dạng phổ biến:

- **System-assigned:** vòng đời danh tính gắn với một tài nguyên Azure; khi tài nguyên bị xóa, danh tính đó cũng bị xóa.
- **User-assigned:** danh tính là tài nguyên độc lập, có thể gắn vào nhiều tài nguyên được phép và có vòng đời riêng.

VM hoặc dịch vụ hỗ trợ managed identity có thể yêu cầu token cho một audience/resource cụ thể rồi dùng token đó gọi dịch vụ Azure. Quyền thường được cấp thông qua Azure role-based access control (Azure RBAC) tại scope phù hợp, chẳng hạn một storage account, container hoặc Key Vault.

Managed identity loại bỏ nhu cầu lưu client secret trong ứng dụng, nhưng vẫn cần giới hạn scope và role. Một user-assigned identity gắn vào quá nhiều VM có thể làm tăng phạm vi ảnh hưởng nếu một VM bị xâm nhập.

### 4.3. Google Cloud service account

Service account đại diện cho workload trên Google Cloud. Có thể gắn service account vào Compute Engine VM hoặc workload tương ứng. Ứng dụng dùng Application Default Credentials (ADC) hoặc client library để lấy credential do nền tảng cấp.

IAM policy gắn role cho service account ở cấp tổ chức, project, folder hoặc resource. Hãy cấp quyền tại scope nhỏ nhất đáp ứng nhu cầu. Ví dụ, workload chỉ cần đọc object trong một bucket thì ưu tiên quyền đọc ở bucket đó thay vì cấp quyền rộng trên cả project.

Không nên tạo và tải service account key JSON xuống VM nếu workload có thể dùng service account gắn trực tiếp hoặc federation.

## 5. Thiết kế quyền theo nguyên tắc đặc quyền tối thiểu

Một policy nên trả lời ba câu hỏi:

1. **Who:** principal nào được thực hiện hành động?
2. **What:** hành động nào được phép?
3. **Where/when:** trên tài nguyên nào và trong điều kiện nào?

Quyền có thể được mô tả như một tập hợp:

\[
Permission = (Principal,\ Action,\ Resource,\ Condition)
\]

Ví dụ, worker thumbnail có thể được phép gọi hành động đọc object trên bucket product-uploads và ghi object vào prefix thumbnails/ của bucket product-assets, nhưng không được xóa object hoặc thay đổi policy của bucket.

### 5.1. Giới hạn theo action

Chỉ cấp những API action mà ứng dụng thực sự cần. Ví dụ:

- Đọc object: GetObject.
- Ghi object: PutObject.
- Gửi message: SendMessage.
- Đọc secret cụ thể: hành động đọc secret theo API của secret manager.
- Ghi log: các hành động ghi log cần thiết.

Tránh cấp wildcard hành động như dấu sao nếu không có lý do rõ ràng. Quyền List, Read, Write, Delete, Admin có phạm vi khác nhau; một ứng dụng chỉ đọc dữ liệu không nên có quyền xóa hoặc thay đổi cấu hình.

### 5.2. Giới hạn theo resource

Một action được phép trên mọi tài nguyên vẫn có thể rất rộng. Hãy giới hạn resource bằng ARN, resource ID, bucket, queue, database, secret hoặc scope tương ứng.

Ví dụ, s3:GetObject trên arn:aws:s3:::company-data/* cho phép đọc mọi object trong bucket đó; nếu worker chỉ xử lý ảnh tải lên, có thể giới hạn vào prefix uploads/*. Khi cần list bucket, policy cần cấp quyền bucket-level riêng và có thể dùng condition để giới hạn prefix.

### 5.3. Điều kiện bổ sung

Policy có thể giới hạn thêm bằng điều kiện:

- Môi trường hoặc tag của resource.
- VPC endpoint hoặc mạng nguồn.
- TLS bắt buộc.
- Principal tag hoặc session tag.
- Audience, subject hoặc issuer của token federation.
- Thời gian hoặc các thuộc tính ngữ cảnh được dịch vụ hỗ trợ.

Điều kiện giúp giảm phạm vi quyền, nhưng phải kiểm thử vì một condition sai có thể chặn cả workload hợp lệ. Không nên dựa vào địa chỉ IP nguồn như danh tính duy nhất; mạng có thể thay đổi và IP không chứng minh được principal.

### 5.4. Deny và quyền hiệu lực

Một số nền tảng hỗ trợ explicit deny hoặc policy ở nhiều tầng. Explicit deny thường có ưu tiên cao hơn allow trong các mô hình IAM tương ứng. Quyền hiệu lực có thể là kết quả kết hợp của identity policy, resource policy, organization policy, permission boundary, session policy và các điều kiện khác.

Không nên nhìn một policy riêng lẻ rồi kết luận ứng dụng có quyền. Cần xem toàn bộ đường cấp quyền và thử hành động thực tế trong môi trường kiểm thử.

## 6. Ví dụ: EC2 chỉ đọc một vùng dữ liệu trên S3

Giả sử một VM chạy ứng dụng báo cáo cần đọc file CSV từ prefix daily-input/ trong bucket analytics-data. Ứng dụng không cần ghi hoặc xóa object.

### 6.1. Trust policy cho EC2

Role cần cho phép dịch vụ EC2 assume role:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "ec2.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
~~~

Trust policy trả lời câu hỏi ai được đảm nhận role. Nó không cấp quyền đọc S3; quyền truy cập S3 nằm trong permission policy riêng.

### 6.2. Permission policy chỉ đọc object trong prefix

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadDailyInputObjects",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject"
      ],
      "Resource": "arn:aws:s3:::analytics-data/daily-input/*"
    }
  ]
}
~~~

Policy này cho phép đọc object trong prefix đã chỉ định. Nếu ứng dụng cần liệt kê object, có thể cần thêm s3:ListBucket trên ARN bucket với condition giới hạn s3:prefix. Chỉ thêm quyền đó sau khi xác nhận ứng dụng thật sự cần.

### 6.3. Gắn role vào EC2

Ví dụ Terraform rút gọn:

~~~hcl
resource "aws_iam_role" "report_reader" {
  name = "report-reader"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "ec2.amazonaws.com"
      }
      Action = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "read_daily_input" {
  name = "read-daily-input"
  role = aws_iam_role.report_reader.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["s3:GetObject"]
      Resource = "arn:aws:s3:::analytics-data/daily-input/*"
    }]
  })
}

resource "aws_iam_instance_profile" "report_reader" {
  name = "report-reader"
  role = aws_iam_role.report_reader.name
}

resource "aws_instance" "report_worker" {
  ami                  = var.approved_ami_id
  instance_type        = "t3.small"
  subnet_id            = var.private_subnet_id
  iam_instance_profile = aws_iam_instance_profile.report_reader.name
}
~~~

Đây là ví dụ minh họa cấu trúc; cần dùng image, subnet và provider version phù hợp với tài khoản thực tế. Trong production, role name, resource ARN, tag và chính sách nên được quản lý theo chuẩn tổ chức. Module tạo VM không nên tự cấp quyền rộng ngoài mục đích của workload.

### 6.4. Ứng dụng lấy credential

Với AWS SDK tương thích, ứng dụng thường dùng default credential provider chain. Khi chạy trên EC2 có instance profile, SDK có thể lấy credential tạm thời từ metadata service mà không cần access key trong file cấu hình.

Không nên ghi credential trả về vào log hoặc lưu lại thành file lâu dài. Để credential provider tự làm mới và chỉ truyền credential qua kênh bảo mật tới dịch vụ đích.

## 7. Credential ngắn hạn và vòng đời token

Credential dài hạn như access key hoặc service account key có thể tồn tại nhiều tháng. Nếu bị lộ, kẻ tấn công có thêm thời gian sử dụng chúng cho đến khi khóa bị thu hồi. Credential ngắn hạn giảm cửa sổ rủi ro vì có thời hạn và được cấp lại qua một quy trình danh tính.

Credential workload có thể là:

- Access key/secret key tạm thời kèm session token.
- OAuth 2.0 access token.
- JWT được ký bởi identity provider.
- X.509 certificate có thời hạn.
- Token projected cho Kubernetes ServiceAccount.

Khi nhận credential, cần kiểm tra:

- Expiration: thời điểm hết hạn.
- Audience: dịch vụ hoặc API mà token được phát hành để truy cập.
- Issuer: hệ thống phát hành token.
- Subject: danh tính workload được đại diện.
- Scope hoặc claim: phạm vi quyền và ngữ cảnh.

SDK nên quản lý refresh theo cơ chế chính thức. Không nên tự lưu token vào source code, biến môi trường tồn tại lâu dài hoặc file dùng chung nếu có thể dùng credential provider.

### 7.1. Token không phải secret vĩnh viễn

Token ngắn hạn vẫn là credential. Nếu bị đánh cắp khi còn hiệu lực, kẻ tấn công có thể sử dụng token trong phạm vi và thời gian mà nó cho phép. Vì vậy:

- Không ghi token vào log hoặc telemetry.
- Truyền token qua TLS.
- Giữ token trong bộ nhớ khi có thể.
- Không chia sẻ token giữa workload không liên quan.
- Dùng audience và subject phù hợp.
- Thu hồi hoặc giảm quyền khi phát hiện sự cố.

### 7.2. Credential rotation

Với credential tạm thời do nền tảng cấp, rotation thường được tự động hóa. Với credential tĩnh chưa thể loại bỏ, cần:

1. Lưu trong secret manager.
2. Phân quyền truy cập secret cho đúng workload.
3. Thiết lập lịch rotation và thời gian overlap phù hợp.
4. Cập nhật ứng dụng để đọc phiên bản mới.
5. Xác minh credential mới hoạt động.
6. Thu hồi credential cũ và kiểm tra log sử dụng.

Không nên chỉ tạo khóa mới rồi quên thu hồi khóa cũ. Nhiều khóa tồn tại song song làm tăng bề mặt tấn công.

## 8. Bảo vệ metadata service và credential endpoint

VM cloud thường có metadata service để cung cấp thông tin instance, cấu hình bootstrap và credential tạm thời cho role được gắn vào máy. Nếu ứng dụng hoặc proxy có lỗ hổng SSRF (Server-Side Request Forgery), kẻ tấn công có thể cố truy cập metadata endpoint để lấy thông tin nhạy cảm.

Metadata service không phải API công khai dành cho Internet. Nó được thiết kế để workload trên máy truy cập qua một đường mạng đặc biệt. Tuy nhiên, ứng dụng không an toàn có thể vô tình gửi request tới endpoint này thay cho người dùng.

### 8.1. Giảm rủi ro SSRF

- Bật cơ chế bảo vệ metadata theo khuyến nghị của cloud provider.
- Ưu tiên metadata token/session bắt buộc nếu nền tảng hỗ trợ.
- Chặn truy cập metadata từ tiến trình hoặc container không cần quyền.
- Không cho phép URL tùy ý từ người dùng được fetch mà không kiểm tra destination.
- Chặn truy cập tới link-local metadata IP ở proxy hoặc network policy khi phù hợp.
- Hạn chế role gắn trên host chỉ có quyền tối thiểu.
- Không chạy nhiều workload không tin cậy chung một host với một role rộng.

### 8.2. AWS IMDSv2

AWS EC2 Instance Metadata Service phiên bản 2 (IMDSv2) dùng quy trình session token trước khi truy vấn metadata. Có thể cấu hình instance yêu cầu token và giới hạn hop limit phù hợp với topology. Điều này giảm một số kiểu SSRF đơn giản, nhưng không thay thế việc sửa lỗ hổng SSRF hoặc giới hạn quyền role.

Trong Terraform, cấu hình thường có dạng:

~~~hcl
metadata_options {
  http_endpoint               = "enabled"
  http_tokens                 = "required"
  http_put_response_hop_limit = 1
}
~~~

Hop limit bằng 1 có thể không phù hợp với một số kiến trúc container hoặc network namespace cần thêm hop. Hãy thử nghiệm trên runtime thực tế và chọn giá trị nhỏ nhất vẫn đáp ứng ứng dụng. Không tắt metadata endpoint nếu workload cần credential qua instance profile; hãy cấu hình bảo vệ theo thiết kế.

## 9. Workload identity federation

Federation cho phép một workload dùng danh tính từ identity provider đã tin cậy để nhận credential của cloud mà không cần tạo khóa dài hạn. Ví dụ, một pipeline CI/CD chạy ngoài cloud có thể nhận OIDC token từ nền tảng CI, sau đó đổi token đó lấy credential tạm thời để triển khai vào một project hoặc account cụ thể.

Luồng khái quát:

1. Workload đăng nhập hoặc được nền tảng cấp token từ issuer đã tin cậy.
2. Token chứa issuer, subject, audience và các claim liên quan.
3. Cloud STS hoặc identity service xác minh chữ ký và claim.
4. Trust policy kiểm tra workload có đúng repository, branch, environment hoặc service account được phép không.
5. Cloud cấp credential ngắn hạn gắn với role.
6. Workload dùng credential đó gọi API trong phạm vi được cấp.

~~~mermaid
sequenceDiagram
    participant C as CI / Kubernetes Workload
    participant O as OIDC Identity Provider
    participant F as Cloud STS / Federation
    participant R as Cloud Resource
    C->>O: Yêu cầu identity token
    O-->>C: JWT có issuer, subject, audience
    C->>F: Đổi token lấy credential
    F->>F: Kiểm tra chữ ký và trust conditions
    F-->>C: Credential cloud ngắn hạn
    C->>R: Gọi API với credential
    R-->>C: Kết quả theo IAM policy
~~~

Trust policy nên giới hạn:

- Issuer cụ thể, không tin cậy mọi identity provider.
- Audience đúng với dịch vụ đổi token.
- Subject chính xác, chẳng hạn repository và branch hoặc Kubernetes namespace/service account.
- Environment hoặc claim bổ sung nếu nền tảng hỗ trợ.
- Role đích có quyền tối thiểu.

Nếu trust policy chỉ kiểm tra issuer mà không giới hạn subject/audience, nhiều workload khác trong cùng identity provider có thể tìm cách nhận role. Federation loại bỏ khóa tĩnh nhưng không loại bỏ nhu cầu bảo vệ trust policy.

## 10. Danh tính cho container và Kubernetes

Container thường chạy trên node có một danh tính nền. Nếu mọi Pod đều dùng credential của node, một Pod bị xâm nhập có thể kế thừa quyền của tất cả workload khác trên node.

Nên cấp danh tính ở cấp workload khi nền tảng hỗ trợ:

- Mỗi ứng dụng hoặc nhóm Pod có Kubernetes ServiceAccount riêng.
- Gắn quyền cloud với đúng service account thông qua federation hoặc cơ chế tích hợp của cloud.
- Chỉ mount projected token cho container cần dùng.
- Giới hạn namespace và quyền tạo/sử dụng service account.
- Không dùng chung service account mặc định cho mọi ứng dụng.

### 10.1. Kubernetes ServiceAccount

ServiceAccount là danh tính trong Kubernetes để Pod xác thực với Kubernetes API hoặc được ánh xạ sang danh tính cloud qua cơ chế tích hợp. Token hiện đại thường được cấp theo dạng projected token có audience và thời hạn; không nên tạo secret token tĩnh dùng lâu dài nếu không cần.

Ví dụ ServiceAccount:

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: image-worker
  namespace: media
automountServiceAccountToken: false
~~~

Nếu Pod chỉ cần danh tính cloud qua một cơ chế token projection cụ thể, cấu hình mount token phải theo hướng dẫn của nền tảng. Tắt auto-mount ở ví dụ giúp tránh cấp token Kubernetes API cho mọi container khi không cần; nó không tự cấu hình cloud federation.

### 10.2. Phân quyền Kubernetes RBAC và cloud IAM

Kubernetes RBAC kiểm soát quyền gọi Kubernetes API, ví dụ đọc ConfigMap hoặc xem Pod. Cloud IAM kiểm soát quyền gọi dịch vụ cloud, ví dụ đọc object storage hoặc lấy secret. Hai lớp quyền này độc lập và cần được đánh giá riêng.

Một Pod có thể không có quyền đọc Secret Kubernetes nhưng vẫn có quyền đọc secret từ cloud secret manager qua IAM role. Ngược lại, một service account có quyền đọc Pod trong namespace không tự động có quyền đọc bucket cloud.

### 10.3. Tránh kế thừa quyền của node

Trên một số nền tảng, Pod có thể truy cập credential của node nếu cấu hình network hoặc metadata không được giới hạn. Hãy dùng workload identity integration, chặn đường truy cập metadata từ Pod không cần thiết và kiểm thử ranh giới giữa các namespace. Không xem node role là role mặc định phù hợp cho mọi Pod.

## 11. Managed identity và truy cập secret

Danh tính workload và secret là hai khái niệm liên quan nhưng khác nhau:

- **Identity** cho biết workload là ai và quyết định nó được phép làm gì.
- **Secret** là dữ liệu nhạy cảm mà workload cần dùng, ví dụ mật khẩu database hoặc API key của hệ thống bên ngoài.

Nếu dịch vụ đích hỗ trợ IAM hoặc workload identity, ưu tiên xác thực bằng danh tính thay cho việc tạo một mật khẩu tĩnh. Nếu ứng dụng vẫn cần secret, hãy dùng workload identity để xác thực với secret manager rồi chỉ đọc đúng secret cần thiết.

Ví dụ:

1. VM có role orders-api.
2. Role chỉ được phép đọc secret prod/orders/database-password.
3. Ứng dụng dùng credential tạm thời để gọi secret manager.
4. Secret manager xác minh role và trả secret.
5. Ứng dụng dùng secret để kết nối database, không ghi secret vào log.

Không nên cấp quyền đọc toàn bộ secret trong account chỉ vì ứng dụng cần một mật khẩu.

## 12. Phạm vi quyền và mô hình phân tách workload

Nên tách role theo chức năng, môi trường và mức độ nhạy cảm:

| Workload | Quyền cần thiết | Quyền nên tránh |
|---|---|---|
| Catalog API | Đọc dữ liệu catalog, ghi log | Xóa bucket, sửa IAM |
| Order API | Ghi đơn hàng, gọi payment service qua endpoint được kiểm soát | Đọc dữ liệu nhân sự, quản trị tài khoản |
| Image worker | Đọc upload prefix, ghi thumbnail prefix, gửi queue result | Đọc dữ liệu thanh toán, xóa bucket |
| Backup agent | Đọc nguồn backup và ghi repository backup theo chính sách | Sửa code ứng dụng, tạo IAM user |
| Monitoring agent | Đọc metric và gửi log | Đọc payload nghiệp vụ hoặc secret không cần thiết |
| CI/CD deployment | Triển khai vào một ứng dụng/môi trường cụ thể | Quyền admin toàn bộ organization |

Development, staging và production nên có danh tính hoặc trust boundary riêng. Không nên dùng một role production cho pipeline chạy trên mọi branch. Với CI/CD, có thể chỉ cho branch được bảo vệ hoặc environment đã phê duyệt nhận role triển khai production.

### 12.1. Tách quyền đọc và ghi

Nếu một workload có thành phần chỉ đọc và thành phần ghi dữ liệu, cân nhắc tách thành hai danh tính. Ví dụ, API phục vụ tra cứu chỉ cần read permission; worker cập nhật chỉ cần write vào một prefix. Việc tách giúp giới hạn hậu quả khi một thành phần bị khai thác.

### 12.2. Tách quyền theo môi trường

Không nên để workload development đọc dữ liệu production chỉ vì dùng chung một account hoặc project. Dùng account/project/subscription hoặc resource scope tách biệt khi phù hợp. Nếu phải dùng chung, policy cần giới hạn rõ theo tag, resource path, condition và danh tính.

## 13. Audit và theo dõi hoạt động danh tính

Audit log giúp trả lời:

- Workload nào đã gọi API?
- Danh tính nào được assume hoặc đổi token?
- Hành động nào đã thực hiện?
- Tài nguyên nào bị truy cập hoặc thay đổi?
- Request đến từ thời điểm, địa chỉ và môi trường nào?
- Hành động bị từ chối vì policy nào?

Cloud provider thường có audit service ghi nhận hoạt động quản trị và API, ví dụ AWS CloudTrail, Azure Activity Log hoặc Google Cloud Audit Logs. Cần bật và lưu log theo yêu cầu tổ chức, giới hạn quyền xóa log và cảnh báo các hành động nhạy cảm.

Các sự kiện cần theo dõi:

- Tạo, sửa hoặc xóa role, policy và trust relationship.
- Gắn role mới vào VM, function hoặc workload.
- Tạo service account key hoặc access key dài hạn.
- Assume role hoặc token exchange bất thường.
- Truy cập secret ngoài phạm vi thông thường.
- Hành động bị deny tăng đột biến.
- Thay đổi policy làm quyền rộng hơn.

Không ghi access token, secret value hoặc private key vào log. Audit log nên giữ principal ID, request ID, action, resource, kết quả và ngữ cảnh cần thiết để điều tra.

## 14. Kiểm tra quyền trước khi đưa vào production

Một policy có thể hợp lệ về cú pháp nhưng vẫn cấp quá nhiều quyền hoặc làm ứng dụng không hoạt động. Cần kiểm tra cả hai chiều: workload có đủ quyền cần thiết và không có quyền thừa.

Quy trình gợi ý:

1. Liệt kê API action mà ứng dụng thực sự gọi.
2. Xác định resource ARN/ID hoặc scope cụ thể cho từng action.
3. Tạo role riêng cho workload và cấu hình trust policy.
4. Gắn role vào đúng VM, task, Pod hoặc function.
5. Chạy integration test cho các thao tác hợp lệ.
6. Thử các thao tác không được phép và xác minh bị từ chối.
7. Kiểm tra audit log để xác nhận principal thực tế.
8. Rà soát quyền không được sử dụng và thu hẹp policy.
9. Thiết lập cảnh báo thay đổi role/policy và truy cập bất thường.

### 14.1. Kiểm thử positive và negative

Ví dụ worker cần đọc object đầu vào và ghi thumbnail:

| Thao tác kiểm thử | Kết quả mong đợi |
|---|---|
| Đọc object trong prefix upload được phép | Allow |
| Ghi object trong prefix thumbnail được phép | Allow |
| Xóa object nguồn | Deny nếu không có yêu cầu nghiệp vụ |
| Đọc bucket dữ liệu thanh toán | Deny |
| Sửa IAM policy | Deny |
| Đọc secret của ứng dụng khác | Deny |

Negative test rất quan trọng. Nếu chỉ thử các hành động hợp lệ, nhóm chưa chứng minh được quyền đã bị giới hạn đúng mức.

### 14.2. Dùng công cụ phân tích quyền

Tùy nền tảng, có thể dùng IAM policy simulator, access analyzer, role assignment review, policy insights hoặc công cụ kiểm tra quyền tương đương. Công cụ hỗ trợ tìm quyền không sử dụng, trust relationship rộng hoặc resource policy có rủi ro.

Kết quả phân tích cần được đối chiếu với luồng nghiệp vụ. Không tự động xóa quyền chỉ vì một khoảng quan sát không thấy sử dụng; có thể workload chạy theo lịch hoặc chỉ dùng trong tình huống khẩn cấp.

## 15. Xử lý khi credential bị lộ hoặc role bị lạm dụng

Khi nghi ngờ credential bị lộ:

1. Xác định principal, credential ID, thời hạn và workload liên quan.
2. Thu hồi hoặc vô hiệu hóa credential nếu nền tảng hỗ trợ.
3. Gỡ role khỏi workload hoặc giảm quyền tạm thời khi cần.
4. Kiểm tra audit log để tìm action và resource đã bị truy cập.
5. Kiểm tra dữ liệu bị đọc, sửa hoặc xóa.
6. Xoay secret có liên quan và sửa lỗ hổng ban đầu.
7. Khôi phục dữ liệu nếu bị thay đổi trái phép.
8. Phát hành credential mới qua quy trình an toàn.
9. Ghi nhận sự cố và bổ sung kiểm soát để tránh tái diễn.

Credential ngắn hạn làm giảm thời gian sử dụng sau khi bị lộ nhưng không loại bỏ rủi ro. Kẻ tấn công vẫn có thể sử dụng token trong thời gian hiệu lực. Nếu role quá rộng, cửa sổ ngắn vẫn có thể gây thiệt hại lớn.

## 16. Ví dụ thực tế: hệ thống thương mại điện tử

Một hệ thống thương mại điện tử có API catalog, API orders, worker xử lý ảnh và job báo cáo. Mỗi thành phần gọi các dịch vụ cloud khác nhau.

| Workload | Danh tính | Quyền chính | Ranh giới |
|---|---|---|---|
| Catalog API | catalog-api-prod | Đọc catalog storage, gửi log | Chỉ tài nguyên catalog production |
| Orders API | orders-api-prod | Ghi database đơn hàng, đọc secret kết nối | Chỉ database và secret của orders |
| Image worker | image-worker-prod | Đọc upload, ghi thumbnail, gửi queue result | Bucket prefix và queue media |
| Report job | report-reader-prod | Đọc dữ liệu tổng hợp, ghi report output | Dataset và bucket báo cáo |

Khi worker xử lý ảnh bị xâm nhập, role của worker không cho phép đọc dữ liệu đơn hàng hoặc sửa IAM. Khi pipeline deploy catalog API chạy từ branch development, trust policy không cho phép nó nhận role production. Khi một VM bị thay thế, VM mới nhận cùng workload identity qua cấu hình instance, không cần sao chép access key từ máy cũ.

Thiết kế này tạo ranh giới rõ ràng giữa workload. Nhóm vận hành có thể xem audit log để biết API hoặc worker nào đã truy cập tài nguyên và thu hẹp quyền riêng cho từng thành phần.

## 17. Quy trình triển khai workload identity

Có thể áp dụng quy trình sau cho một workload mới:

1. **Mô tả nhiệm vụ:** liệt kê dịch vụ cloud mà ứng dụng cần gọi và hành động cần thực hiện.
2. **Xác định principal:** chọn IAM role, managed identity, service account hoặc federated identity phù hợp.
3. **Thiết kế trust:** giới hạn workload nào được nhận danh tính, issuer, subject, audience và môi trường.
4. **Thiết kế permission:** chỉ định action, resource và condition tối thiểu.
5. **Gắn danh tính:** cấu hình vào VM, task, Pod hoặc function bằng cơ chế của nền tảng.
6. **Tích hợp SDK:** dùng credential provider mặc định hoặc thư viện chính thức để lấy token và tự làm mới.
7. **Bảo vệ credential endpoint:** giới hạn metadata access, xử lý SSRF và không log token.
8. **Kiểm thử:** chạy positive test và negative test trong môi trường riêng.
9. **Bật audit:** theo dõi assume role, token exchange, API access và thay đổi policy.
10. **Rà soát định kỳ:** loại quyền thừa, danh tính không còn dùng và credential tĩnh cũ.

## 18. Những sai lầm thường gặp

- **Dùng access key dài hạn trong source code:** dễ bị lộ qua Git, image, log hoặc bản sao lưu.
- **Dùng chung role cho mọi workload:** một ứng dụng bị xâm nhập có thể kế thừa quyền của ứng dụng khác.
- **Gắn role quản trị vào VM:** biến lỗ hổng ứng dụng thành nguy cơ kiểm soát toàn tài khoản.
- **Chỉ giới hạn action mà quên resource:** quyền đọc vẫn có thể bao phủ toàn bộ bucket hoặc project.
- **Trust policy quá rộng:** workload không mong muốn có thể nhận role.
- **Coi authentication là authorization:** xác thực thành công không đồng nghĩa được phép truy cập tài nguyên.
- **Coi Kubernetes RBAC là cloud IAM:** hai lớp quyền bảo vệ các API khác nhau.
- **Cho mọi Pod dùng node role:** làm mất ranh giới quyền giữa workload.
- **Coi token ngắn hạn là vô hại:** token bị lộ vẫn dùng được trong thời gian hiệu lực.
- **Đặt secret trong user-data hoặc image:** dữ liệu nhạy cảm có thể bị đọc từ metadata, log hoặc bản sao image.
- **Chỉ kiểm thử quyền được phép:** bỏ qua negative test nên không phát hiện quyền thừa.
- **Không theo dõi policy drift:** quyền có thể rộng dần sau nhiều lần thay đổi.

## 19. Ghi nhớ

Workload identity giúp ứng dụng chứng minh danh tính khi gọi dịch vụ cloud. IAM role, managed identity, service account và federation là những cách phổ biến để cấp danh tính cho VM, container, function hoặc pipeline. Ưu tiên credential ngắn hạn được nền tảng cấp tự động thay cho khóa dài hạn được lưu trong ứng dụng.

Least privilege yêu cầu giới hạn principal, action, resource và condition theo đúng nhiệm vụ. Cần tách danh tính giữa workload và môi trường, bảo vệ metadata endpoint, quản lý secret riêng, kiểm thử cả thao tác được phép lẫn bị từ chối, đồng thời theo dõi audit log. Khi danh tính và quyền được thiết kế rõ ràng, ứng dụng có thể gọi dịch vụ cloud an toàn mà không cần nắm quyền quản trị rộng.

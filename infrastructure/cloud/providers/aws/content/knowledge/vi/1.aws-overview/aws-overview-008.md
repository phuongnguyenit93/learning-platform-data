# Thiết lập môi trường thực hành và quy ước đặt tên

> **Phạm vi:** AWS — Tổng quan AWS  
> **Bài học:** Thiết lập môi trường thực hành và quy ước đặt tên

Khi học AWS, việc tạo được một tài nguyên mới chỉ là bước đầu. Môi trường thực hành tốt còn phải giúp bạn biết **đang thao tác trên tài khoản nào, ở Region nào, bằng quyền gì, tài nguyên thuộc về ai và chi phí sẽ được theo dõi ra sao**. Bài này xây dựng nền tảng chung để tiếp tục thực hành IAM, VPC, EC2, S3, cơ sở dữ liệu, dịch vụ tích hợp và serverless; các nguyên tắc đặt tên, bảo mật, giám sát và dọn tài nguyên cũng áp dụng khi chuyển từ bài lab sang hệ thống thực tế.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Chuẩn bị một AWS account hoặc sandbox phù hợp cho học tập, thiết lập cảnh báo chi phí và bảo vệ tài khoản.
2. Phân biệt phạm vi **account**, **Region**, **Availability Zone (AZ)** và phạm vi toàn cầu của một số dịch vụ.
3. Truy cập AWS bằng danh tính có quyền phù hợp; thiết lập AWS CLI v2 hoặc sử dụng AWS CloudShell.
4. Xây dựng quy ước tên tài nguyên, tag và cấu trúc thư mục bài lab dễ truy vết.
5. Tạo, xác minh và dọn một tài nguyên S3 đơn giản theo đúng quy ước.
6. Nhận diện lỗi thường gặp về danh tính, Region, quyền truy cập, trùng tên và phát sinh chi phí.

## 1. Thiết kế phạm vi môi trường thực hành

Một môi trường học AWS tối thiểu nên có các thành phần sau:

~~~mermaid
flowchart TD
    A[AWS account / sandbox] --> B[Danh tính và quyền truy cập]
    A --> C[Theo dõi chi phí và cảnh báo]
    A --> D[Region thực hành]
    D --> E[AZ và tài nguyên mạng / tính toán]
    D --> F[S3, cơ sở dữ liệu, Lambda và dịch vụ khác]
    B --> E
    B --> F
    E --> G[Tên nhất quán, tag, nhật ký, dọn tài nguyên]
    F --> G
~~~

### 1.1. Chọn tài khoản học tập

**Ưu tiên một tài khoản AWS dành riêng cho thực hành** hoặc sandbox do tổ chức cấp. Tách môi trường học khỏi production để các thao tác thử nghiệm không ảnh hưởng đến hệ thống đang phục vụ người dùng.

- **Tài khoản cá nhân:** kiểm tra các bước đăng ký, phương thức thanh toán và điều kiện ưu đãi hiện hành trong AWS Console. Không giả định mọi tài nguyên thuộc “Free Tier” đều miễn phí hoặc giới hạn chi tiêu tự động.
- **Sandbox của công ty/trường học:** dùng đúng tài khoản, vai trò, Region và chính sách ngân sách được cấp. Nếu không có quyền quản trị Billing hoặc IAM, yêu cầu người quản trị thực hiện phần cấu hình tương ứng.
- **AWS Organizations / nhiều tài khoản:** nếu tổ chức đã áp dụng account riêng cho sandbox, dùng đúng account đó. Service Control Policy (SCP) có thể giới hạn hành động ngay cả khi IAM role có quyền cho phép.

Ghi lại thông tin môi trường bằng **mã hoặc tên môi trường**, không ghi mật khẩu, access key, mã MFA hoặc thông tin thanh toán vào repository:

| Thuộc tính | Ví dụ dùng trong bài | Ý nghĩa |
|---|---|---|
| Project | **aws-lab** | Nhận diện nhóm tài nguyên của khóa học |
| Environment | **dev** | Phân biệt môi trường dev, test, prod, sandbox |
| AWS account | **sandbox được cấp** | Ranh giới sở hữu và thanh toán |
| Region chính | **ap-southeast-1** | Region Singapore, dùng thống nhất cho bài minh họa |
| CLI profile | **aws-lab-dev** | Chọn đúng danh tính khi chạy lệnh |
| Owner | **team-cloud** | Đầu mối phụ trách, không cần dùng dữ liệu cá nhân |
| Công cụ | AWS Console + CLI v2 | Quản lý trực quan và thao tác có thể lặp lại |

**Lưu ý về Region:** **ap-southeast-1** chỉ là lựa chọn minh họa; hãy ưu tiên Region được tổ chức cho phép, có đủ dịch vụ cần học và phù hợp yêu cầu độ trễ, lưu trú dữ liệu, chi phí. Giá và tính sẵn có của dịch vụ khác nhau theo Region.

### 1.2. Account, Region và AZ không phải cùng một phạm vi

| Phạm vi | Ý nghĩa | Ví dụ / hệ quả khi thực hành |
|---|---|---|
| AWS account | Ranh giới quản trị và thanh toán | Kiểm tra account trước khi tạo hoặc xóa tài nguyên |
| Region | Vùng địa lý triển khai phần lớn dịch vụ | VPC/EC2/RDS thuộc Region; chuyển Region có thể khiến Console trông như “mất” tài nguyên |
| AZ | Một hoặc nhiều trung tâm dữ liệu độc lập trong Region, được thiết kế để cách ly sự cố | Subnet nằm trong một AZ; đặt tài nguyên trên nhiều AZ khi học khả năng sẵn sàng |
| Dịch vụ toàn cầu hoặc có phạm vi đặc biệt | Không tuân theo cùng một mô hình Region/AZ | IAM là dịch vụ toàn cầu; S3 bucket có tên duy nhất trong namespace áp dụng, nhưng bucket được tạo tại một Region |

**Không đồng nhất chữ cái AZ giữa các tài khoản.** Tên như **ap-southeast-1a** có thể ánh xạ đến AZ vật lý khác nhau theo account. Khi cần so sánh đúng AZ giữa nhiều tài khoản, dùng **AZ ID** (ví dụ dạng **apse1-az1**) nếu dịch vụ hỗ trợ.

Không cần tạo VPC, NAT Gateway hay RDS ngay trong bài mở đầu. Những dịch vụ đó có đặc tính tính phí và vòng đời phức tạp hơn; bài đầu tiên chỉ kiểm tra danh tính, Region và một bucket S3 đơn giản.

## 2. Thiết lập các hàng rào an toàn trước khi tạo tài nguyên

### 2.1. Bảo vệ tài khoản gốc và quản lý danh tính

**Root user** có quyền rất cao. Dùng root khi cần thiết lập account và một số công việc quản trị đặc biệt, không sử dụng root trong hoạt động học hằng ngày.

1. Bật **MFA** cho root user và bảo vệ phương thức khôi phục tài khoản; không tạo access key cho root.
2. Điền thông tin liên hệ, bảo mật và thanh toán theo chính sách tài khoản.
3. Với tổ chức, ưu tiên đăng nhập liên kết hoặc **IAM Identity Center** để nhận quyền qua role/permission set. Với môi trường cá nhân, chọn phương thức đăng nhập có MFA và quyền phù hợp với bài lab.
4. Áp dụng **least privilege**: chỉ cho phép những API, tài nguyên và Region cần thiết. Quyền quản trị rộng chỉ dành cho người thực sự quản trị sandbox.
5. Không đưa access key, secret key, session token, mật khẩu, private key, tệp **.env** chứa bí mật vào Git, ảnh chụp màn hình hoặc tài liệu bài học.

AWS xác thực yêu cầu API bằng danh tính (principal) và đánh giá quyền theo chính sách áp dụng. Người học có thể thấy **AccessDenied** dù tên lệnh đúng; nguyên nhân có thể nằm ở IAM policy, SCP, permission boundary, resource policy hoặc điều kiện bảo mật khác.

### 2.2. Cảnh báo chi phí trước khi bắt đầu

Mở **Billing and Cost Management** trong AWS Console (người dùng cần được cấp quyền Billing), sau đó:

1. Kiểm tra trang tổng quan chi phí, ưu đãi/credit đang có và chính sách cấp quyền truy cập Billing của account.
2. Tạo **AWS Budget** theo chi phí tháng với ngưỡng phù hợp, chẳng hạn **5 USD/tháng** cho sandbox nhỏ; cấu hình cảnh báo tại nhiều mức (ví dụ 50%, 80%, 100%) gửi tới địa chỉ nhận thông báo mà bạn kiểm soát.
3. Nếu khả dụng, cân nhắc **Cost Anomaly Detection** để được cảnh báo khi chi tiêu bất thường.
4. Kiểm tra chi phí theo **Service**, **Region** và **Tag** trong Cost Explorer khi dữ liệu đã sẵn có; cost allocation tags có thể cần được kích hoạt và chờ dữ liệu cập nhật.
5. Tạo thói quen **dọn tài nguyên sau mỗi phiên học**. Với các dịch vụ có phí theo giờ hoặc theo dung lượng, đặt lịch nhắc dọn là biện pháp hữu ích.

> **Cảnh báo quan trọng:** AWS Budget là cơ chế **theo dõi và thông báo**, không mặc định chặn tài nguyên hay đặt trần chi tiêu cứng. Chi phí có thể phát sinh trước khi thông báo được gửi. Ngay cả khi có ưu đãi, hãy đọc bảng giá và điều kiện áp dụng của dịch vụ/Region cụ thể.

Các tài nguyên dễ bị bỏ quên trong các bài nâng cao gồm EC2 chạy liên tục, EBS volume/snapshot, Elastic IP hoặc public IPv4, NAT Gateway, load balancer, RDS, log lưu quá lâu và dữ liệu S3. Thói quen quản lý chi phí cần xuất hiện từ bài đầu tiên.

### 2.3. Nhật ký và khả năng truy vết

- **CloudTrail Event history** cho phép xem các management event gần đây trong tài khoản theo phạm vi được AWS hỗ trợ; muốn lưu lâu hơn hoặc thu thập rộng hơn cần cấu hình trail hoặc các tính năng tương ứng và kiểm tra chi phí.
- **CloudWatch** hỗ trợ metrics, logs, alarms của dịch vụ; log group có thể tiếp tục lưu trữ và phát sinh chi phí sau khi workload đã dừng.
- **Tag** và **tên** giúp truy tìm mục đích tài nguyên; chúng không thay thế IAM, CloudTrail hay chính sách bảo mật.

## 3. Chuẩn bị công cụ thao tác

### 3.1. Chọn AWS Console, CloudShell hay AWS CLI

| Cách thao tác | Khi nào phù hợp | Lưu ý |
|---|---|---|
| AWS Management Console | Làm quen dịch vụ, quan sát cấu hình bằng giao diện | Kiểm tra tên account và Region trước mỗi thao tác |
| AWS CloudShell | Muốn chạy AWS CLI ngay trong trình duyệt mà không cần cài máy cục bộ | Quyền theo danh tính đăng nhập; kiểm tra Region và giới hạn môi trường CloudShell |
| AWS CLI v2 trên máy | Muốn lặp lại thao tác, viết script và kiểm thử cấu hình | Cần cài CLI và cấu hình danh tính an toàn |
| IaC (Terraform/CloudFormation/CDK) | Các bài sau khi cần triển khai có thể tái tạo | Chú ý state, quyền triển khai và thao tác hủy stack |

Đối với máy cá nhân, cài **AWS CLI v2** theo hướng dẫn chính thức của AWS, sau đó mở terminal mới và kiểm tra:

~~~bash
aws --version
~~~

Nếu chưa nhận lệnh, kiểm tra quá trình cài đặt và biến **PATH** của hệ điều hành. Có thể dùng Git và trình soạn thảo mã (VS Code hoặc công cụ tương đương) để lưu script và ghi chép; không cần cài SDK chỉ để hoàn thành bài này.

### 3.2. Đăng nhập bằng IAM Identity Center (khi được cấp)

Nếu tổ chức đã cấp IAM Identity Center và địa chỉ cổng truy cập, thiết lập profile tương tác:

~~~bash
aws configure sso --profile aws-lab-dev
aws sso login --profile aws-lab-dev
aws sts get-caller-identity --profile aws-lab-dev
~~~

Trong quá trình cấu hình, cung cấp **SSO start URL hoặc issuer URL, SSO Region, AWS account, role và Region mặc định** đúng theo thông tin quản trị viên cấp. Tên profile **aws-lab-dev** chỉ là bí danh cục bộ; không quyết định quyền trên AWS. Phiên đăng nhập hết hạn thì chạy lại lệnh **aws sso login**.

Nếu sử dụng **CloudShell**, có thể bỏ qua các bước cấu hình SSO cục bộ và bắt đầu bằng lệnh **aws sts get-caller-identity**. Không tự tạo access key dài hạn chỉ vì chưa cấu hình được SSO.

### 3.3. Cố định profile và Region cho phiên thực hành

Ví dụ dưới đây dùng **Bash** (Linux/macOS hoặc môi trường Bash khác):

~~~bash
export AWS_PROFILE=aws-lab-dev
export AWS_DEFAULT_REGION=ap-southeast-1

aws sts get-caller-identity
aws configure list
aws ec2 describe-availability-zones \
  --region ap-southeast-1 \
  --query 'AvailabilityZones[].{Name:ZoneName,Id:ZoneId,State:State}' \
  --output table
~~~

Nếu dùng **PowerShell trên Windows**, đặt hai biến môi trường của phiên terminal như sau:

~~~powershell
$env:AWS_PROFILE = "aws-lab-dev"
$env:AWS_DEFAULT_REGION = "ap-southeast-1"

aws sts get-caller-identity
aws configure list
~~~

Đọc kết quả **aws sts get-caller-identity** để xác nhận **Account** và **Arn** đúng với sandbox mong muốn. Đây là kiểm tra bắt buộc trước khi tạo, sửa hay xóa bất kỳ tài nguyên nào. Nếu CLI và Console hiển thị khác nhau, kiểm tra lại profile, role và Region. Tránh gửi nguyên đầu ra chứa định danh tài khoản hoặc ARN lên nơi công khai khi không cần thiết.

## 4. Quy ước đặt tên tài nguyên AWS

Quy ước tên có hai mục đích: giúp con người đọc được tài nguyên đang làm gì và giúp tự động hóa tìm đúng tài nguyên cần thao tác. Quy ước phải đơn giản, ổn định, đồng thời tôn trọng giới hạn của từng dịch vụ.

### 4.1. Cấu trúc tên cơ bản

Đề xuất một khuôn mẫu mặc định:

~~~text
<project>-<environment>-<component>[-<purpose>][-<unique-suffix>]
~~~

Ví dụ dùng xuyên suốt bài:

~~~text
aws-lab-dev-network
aws-lab-dev-app
aws-lab-dev-data
aws-lab-dev-artifacts-<unique-suffix>
~~~

| Thành phần | Quy ước | Ví dụ |
|---|---|---|
| Project | Tên dự án ngắn, ít thay đổi | **aws-lab** |
| Environment | Tập giá trị thống nhất: dev, test, prod, sandbox | **dev** |
| Component | Chức năng nghiệp vụ hoặc kỹ thuật | **api**, **web**, **network**, **data**, **logs** |
| Purpose | Chỉ thêm khi giúp phân biệt tài nguyên cùng nhóm | **private**, **public**, **backup** |
| Unique suffix | Chỉ dùng khi cần tên duy nhất hoặc tránh va chạm | Chuỗi ngẫu nhiên không chứa bí mật |

**Nguyên tắc nên áp dụng:**

- Ưu tiên chữ thường, số và dấu gạch nối (**kebab-case**) cho tên do nhóm tự đặt, trừ khi quy định dịch vụ yêu cầu khác.
- Đặt phần ổn định trước phần có thể thay đổi; tránh tên mơ hồ như **test1**, **new-v2-final**, **my-server**.
- Không đưa mật khẩu, token, email cá nhân, dữ liệu khách hàng hay thông tin nhạy cảm vào tên hoặc tag.
- Tránh nhúng ngày tháng vào mọi tên tài nguyên. Chỉ thêm thời gian khi thực sự cần phân biệt các bản triển khai ngắn hạn.
- Kiểm tra giới hạn độ dài, ký tự, tính duy nhất và quy tắc đổi tên **của từng dịch vụ** trước khi tạo.

### 4.2. Không phải dịch vụ nào cũng dùng cùng một tên

| Dịch vụ / tài nguyên | Cách áp dụng | Điều cần nhớ |
|---|---|---|
| VPC, subnet, EC2 instance | Gán **Name tag**, ví dụ **aws-lab-dev-network**, **aws-lab-dev-subnet-public-1** | ID thực tế vẫn là ID do AWS tạo (dạng **vpc-...**, **subnet-...**, **i-...**) |
| S3 bucket | **aws-lab-dev-artifacts-<unique-suffix>** | Tên bucket phải đáp ứng quy tắc DNS của S3 và là duy nhất trong namespace áp dụng; bucket được tạo tại một Region |
| Lambda function | **aws-lab-dev-api** | Tên function xuất hiện trong ARN và có các giới hạn riêng |
| IAM role | **aws-lab-dev-deployer** | IAM có phạm vi toàn cầu trong account; tên role và path có quy tắc riêng |
| RDS DB instance | **aws-lab-dev-db** | DB identifier có bộ ký tự/độ dài riêng; instance có thể phát sinh phí khi tồn tại |
| CloudWatch log group | Theo chuẩn service hoặc **/aws-lab/dev/api** | Một số log group được service tự tạo theo quy ước cố định |
| S3 object key | **raw/2026/11/sample.json** | “Thư mục” trên S3 chủ yếu là tiền tố trong object key, không phải thư mục máy tính truyền thống |

Ví dụ về tên **S3 general purpose bucket**: dùng 3–63 ký tự, chữ thường, số, dấu gạch nối hoặc dấu chấm theo những ràng buộc cụ thể; tránh dấu chấm cho bài lab để hạn chế vấn đề tương thích. S3 có nhiều loại bucket với quy tắc đặt tên khác nhau; ví dụ ở bài này dùng general purpose bucket. **Tên bucket đã tạo không thể đổi trực tiếp**: thông thường phải tạo bucket mới và di chuyển dữ liệu.

Đối với subnet/AZ, có thể dùng tên **aws-lab-dev-subnet-public-az1**; nhớ rằng ký hiệu **az1** chỉ là nhãn theo sơ đồ của dự án và phải được ánh xạ rõ sang AZ/AZ ID thực tế.

### 4.3. Tag dùng để quản lý, không chỉ để hiển thị

Tên trả lời “đây là tài nguyên gì?”; tag hỗ trợ trả lời “ai sở hữu, dùng cho việc gì, thuộc môi trường nào và có thể dọn khi nào?”. Bộ tag khuyến nghị:

| Tag key | Giá trị ví dụ | Mục đích |
|---|---|---|
| **Project** | **aws-lab** | Gom tài nguyên theo dự án |
| **Environment** | **dev** | Phân biệt mức độ quan trọng của môi trường |
| **Owner** | **team-cloud** | Nhóm hoặc bộ phận chịu trách nhiệm |
| **ManagedBy** | **manual** | Phân biệt thao tác thủ công, terraform, cloudformation… |
| **Purpose** | **learning** | Lý do tồn tại |
| **ExpiresOn** | **YYYY-MM-DD** | Mốc dự kiến xem xét/dọn tài nguyên |
| **CostCenter** | **training** | Tùy chọn: phân bổ chi phí theo đơn vị |

Tag key và value **phân biệt chữ hoa/chữ thường**: **Environment** khác **environment**. Nên thống nhất một cách viết cho toàn khóa học. Tag có giới hạn và dịch vụ hỗ trợ không đồng đều; không phải tài nguyên nào cũng gắn tag hoặc lọc tag theo cùng cách.

**ExpiresOn không tự động xóa tài nguyên.** Muốn dọn tự động cần có cơ chế được thiết kế, cấp quyền và kiểm thử riêng. Để dùng tag trong báo cáo chi phí, bạn còn có thể cần kích hoạt **cost allocation tags** ở Billing. Các tag liên quan đến phân quyền cũng phải được bảo vệ để người dùng không tự thay đổi nhằm vượt chính sách.

### 4.4. Quy ước tên trong mã nguồn và tài liệu

Cấu trúc repository mẫu cho các bài thực hành AWS:

~~~text
aws-lab/
├── README.md
├── .gitignore
├── docs/
│   ├── account-and-region.md
│   └── naming-conventions.md
├── scripts/
│   ├── verify-environment.sh
│   └── cleanup-lab.sh
└── infrastructure/
    └── examples/
~~~

Trong **README.md**, ghi rõ profile mẫu, Region dự kiến, quyền tối thiểu, tài nguyên bài lab tạo ra, chi phí có thể phát sinh và cách dọn. Với script, dùng biến thay cho việc rải account/Region cố định ở nhiều chỗ; với IaC, định nghĩa các tag chung một lần rồi truyền xuống tài nguyên hỗ trợ.

Ví dụ **.gitignore** bảo vệ các tệp có nguy cơ chứa thông tin nhạy cảm:

~~~gitignore
.env
.env.*
!.env.example
*.pem
*.key
.aws/
.terraform/
*.tfstate
*.tfstate.*
~~~

**.gitignore** không thay thế việc quét bí mật; nếu một thông tin nhạy cảm đã bị commit, cần thu hồi/luân chuyển thông tin đó và xử lý lịch sử repository theo quy trình an toàn.

## 5. Thực hành: tạo và dọn S3 bucket theo quy ước

Bài lab này kiểm tra đồng thời **đúng tài khoản, đúng Region, đúng quyền và đúng quy ước tên/tag**. Sử dụng dữ liệu thử nghiệm không chứa thông tin nhạy cảm. S3 có thể phát sinh chi phí theo lưu trữ, request và truyền dữ liệu; hoàn thành bước dọn ngay sau bài lab.

**Điều kiện đầu vào:** AWS CLI v2 hoạt động, profile **aws-lab-dev** đã đăng nhập (hoặc đang ở CloudShell), danh tính được phép tạo/đọc/xóa bucket, quản lý public access block và tag. Các lệnh tiếp theo viết cho **Bash**; với PowerShell, thay cách khai báo biến theo cú pháp PowerShell. Nếu dùng **CloudShell** và chưa tạo profile **aws-lab-dev**, bỏ dòng **export AWS_PROFILE=aws-lab-dev** ở bước 1 để sử dụng danh tính của phiên Console hiện tại.

### Bước 1 — Kiểm tra danh tính và chọn tên duy nhất

~~~bash
export AWS_PROFILE=aws-lab-dev
export AWS_DEFAULT_REGION=ap-southeast-1

aws sts get-caller-identity

REGION=ap-southeast-1
BUCKET="aws-lab-dev-artifacts-$(date +%s)-$RANDOM"
echo "$BUCKET"
~~~

Đối chiếu account trong kết quả **sts get-caller-identity** với sandbox đã đăng ký. Hậu tố thời gian/ngẫu nhiên trong ví dụ chỉ làm giảm khả năng trùng tên; nếu tên đã được dùng, tạo tên khác. Đừng chia sẻ tên bucket chứa thông tin nhạy cảm vì tên bucket có thể xuất hiện trong URL và nhật ký.

### Bước 2 — Tạo bucket tại Region đã chọn

~~~bash
aws s3api create-bucket \
  --bucket "$BUCKET" \
  --region "$REGION" \
  --create-bucket-configuration "LocationConstraint=$REGION"
~~~

Ví dụ dùng Region **ap-southeast-1**. Với **us-east-1**, cú pháp tạo general purpose bucket có điểm khác: thường bỏ tham số **--create-bucket-configuration**. Không thay Region tùy ý mà quên cập nhật cả lệnh và biến môi trường.

### Bước 3 — Bảo vệ bucket và gắn tag

Bucket S3 mới có các mặc định bảo mật quan trọng, nhưng ta đặt **Block Public Access** rõ ràng để người học quan sát được cấu hình mong muốn:

~~~bash
aws s3api put-public-access-block \
  --bucket "$BUCKET" \
  --public-access-block-configuration "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"

aws s3api put-bucket-tagging \
  --bucket "$BUCKET" \
  --tagging '{"TagSet":[{"Key":"Project","Value":"aws-lab"},{"Key":"Environment","Value":"dev"},{"Key":"Owner","Value":"team-cloud"},{"Key":"ManagedBy","Value":"manual"},{"Key":"Purpose","Value":"learning"}]}'

aws s3api get-public-access-block --bucket "$BUCKET"
aws s3api get-bucket-tagging --bucket "$BUCKET"
~~~

Các bucket S3 general purpose mới mặc định bật Block Public Access và mã hóa phía máy chủ **SSE-S3**; vẫn cần xác minh cấu hình thực tế, chính sách account và yêu cầu mã hóa của tổ chức. Không vô hiệu hóa public access chỉ để “thử cho dễ”. Khi học các mẫu chia sẻ dữ liệu, phải thiết kế quyền truy cập có chủ đích.

### Bước 4 — Ghi, liệt kê và đọc lại một object

~~~bash
printf 'Hello AWS lab!\n' > lab-hello-aws.txt

aws s3 cp ./lab-hello-aws.txt "s3://$BUCKET/demo/lab-hello-aws.txt"
aws s3 ls "s3://$BUCKET/demo/"
aws s3 cp "s3://$BUCKET/demo/lab-hello-aws.txt" ./lab-hello-aws-downloaded.txt
~~~

Kiểm tra nội dung file tải về. Nhận biết:

- **Bucket** là vùng chứa object tại Region đã chọn.
- **Object key** là **demo/lab-hello-aws.txt**; phần **demo/** là tiền tố để nhóm object.
- **Tag bucket** mô tả bucket; object có cơ chế object tag riêng nếu bài toán cần quản lý ở cấp object.

### Bước 5 — Dọn tài nguyên và xác minh

~~~bash
aws s3 rm "s3://$BUCKET/demo/lab-hello-aws.txt"

aws s3api delete-bucket \
  --bucket "$BUCKET" \
  --region "$REGION"
~~~

Lệnh xóa bucket yêu cầu bucket **trống**. Nếu đã tải thêm object, tạo version hoặc bật các tính năng khác, cần kiểm tra và dọn chúng theo quy trình phù hợp trước khi xóa bucket. Sau đó kiểm tra danh sách bucket trên Console hoặc bằng CLI để chắc chắn tài nguyên bài lab không còn; có thể xóa hai tệp thử nghiệm cục bộ khi không cần sử dụng.

**Kết quả mong đợi:** bạn đã xác minh danh tính, tạo bucket duy nhất tại Region đã chọn, bật chặn truy cập công khai, gắn tag, ghi/đọc object và dọn được bucket. Nếu gặp lỗi, dùng bảng xử lý bên dưới trước khi thử lại.

## 6. Mở rộng quy ước sang các bài AWS tiếp theo

Khi chuyển từ S3 sang các dịch vụ khác, giữ cùng **Project**, **Environment**, **Owner** và cách đặt tên, nhưng luôn đọc đặc điểm và giới hạn riêng của dịch vụ.

| Nhóm bài thực hành tiếp theo | Quy ước hoặc kiểm tra nên giữ |
|---|---|
| IAM / Identity Center | Dùng role và session tạm thời; kiểm tra principal; đặt tên role theo project + môi trường + chức năng |
| VPC / mạng | Tên VPC, subnet, route table, security group thể hiện project + môi trường + nhiệm vụ; ghi sơ đồ CIDR và AZ rõ ràng |
| EC2 / tính toán | Gắn Name tag và tag quản lý; kiểm tra instance type, IPv4/EBS và trạng thái dừng/xóa sau bài lab |
| S3 / lưu trữ | Chọn tên bucket duy nhất và Region; mặc định riêng tư, kiểm soát mã hóa, retention, lifecycle và phiên bản |
| RDS / cơ sở dữ liệu | Tách môi trường và dữ liệu thử; dự trù phí instance/storage/backup, dọn snapshot khi phù hợp |
| Lambda / API / tích hợp | Đặt tên function, queue, topic nhất quán; theo dõi request, thời gian chạy, retry và CloudWatch Logs |
| Giám sát / phục hồi | Định nghĩa log retention, alarm và cách kiểm tra phục hồi; bảo đảm tài nguyên khôi phục cũng được đặt tên/tag |
| Triển khai bằng IaC | Định nghĩa biến project, environment, region; quản lý state và vòng đời tạo/hủy rõ ràng |

Ở các bài về độ sẵn sàng, cần biết đặt subnet hay workload tại nhiều AZ thích hợp, thiết kế sao lưu và thử phục hồi. **Nhiều AZ không tự động bảo đảm ứng dụng phục hồi** nếu phụ thuộc hoặc dữ liệu vẫn có điểm lỗi đơn lẻ.

## 7. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra và hướng xử lý |
|---|---|---|
| **Unable to locate credentials**, **ExpiredToken** | Chưa đăng nhập hoặc session hết hạn | Kiểm tra profile; đăng nhập lại bằng **aws sso login --profile aws-lab-dev** |
| **AccessDenied**, **UnauthorizedOperation** | Không đủ quyền IAM, SCP hoặc chính sách liên quan | Xác minh ARN từ STS; đọc API bị từ chối và nhờ quản trị viên cấp đúng quyền |
| **BucketAlreadyExists** | Tên S3 đã được dùng trong namespace áp dụng | Tạo tên mới có hậu tố đủ duy nhất; không cố thao tác với bucket của người khác |
| **IllegalLocationConstraintException** | Cấu hình Region khi tạo bucket không khớp | Kiểm tra **--region** và **LocationConstraint**; lưu ý ngoại lệ **us-east-1** |
| Không thấy EC2/VPC/RDS trong Console | Đang xem Region hoặc account khác | Kiểm tra selector Region, account, profile và bộ lọc |
| Xóa S3 bucket báo **BucketNotEmpty** | Vẫn còn object hoặc version | Liệt kê dữ liệu/version và dọn theo đúng quy trình rồi thử lại |
| Phát sinh chi phí dù đã dừng workload | Vẫn còn EBS, public IPv4, NAT Gateway, RDS, logs, snapshots… | Kiểm tra Billing/Cost Explorer; liệt kê tài nguyên theo Region và tag; dọn tài nguyên còn sống |
| Tag không xuất hiện trong Cost Explorer | Chưa kích hoạt cost allocation tag hoặc dữ liệu chưa cập nhật | Kiểm tra phần cost allocation tags và thời gian cập nhật dữ liệu |

Khi gặp lỗi, ghi lại **thời điểm, profile, Region, dịch vụ, thao tác và thông báo lỗi đã lược bỏ thông tin nhạy cảm**. Điều này giúp tái hiện vấn đề nhanh hơn mà không lộ thông tin đăng nhập.

## 8. Checklist hoàn thành và quy trình cho mỗi phiên lab

Trước khi bắt đầu một bài học mới:

- [ ] Đang dùng đúng AWS account/sandbox, principal và Region.
- [ ] Root user được bảo vệ bằng MFA; tài khoản thực hành sử dụng quyền phù hợp.
- [ ] Có cảnh báo ngân sách và biết nơi kiểm tra chi phí.
- [ ] Có tên project/environment và bộ tag thống nhất.
- [ ] Biết bài lab sẽ tạo tài nguyên nào, có thể phát sinh phí gì và cách xóa chúng.

Trước khi kết thúc:

- [ ] Ghi lại những API, cấu hình và quan sát quan trọng vào tài liệu bài học.
- [ ] Dừng hoặc xóa tài nguyên đã tạo và kiểm tra cả tài nguyên phụ (storage, network, logs, snapshots).
- [ ] Kiểm tra lại các Region đã sử dụng; xem Billing khi dữ liệu mới cập nhật.
- [ ] Không commit tệp chứa thông tin xác thực hoặc dữ liệu nhạy cảm.
- [ ] Cập nhật ghi chú: tên tài nguyên, tag và quyết định thiết kế có nhất quán không?

**Tự kiểm tra hiểu bài:**

1. Vì sao **Name tag** của EC2 khác với instance ID do AWS cấp?
2. Vì sao hai account có cùng tên AZ kết thúc bằng **1a** chưa chắc cùng AZ vật lý?
3. Nếu đã tạo Budget 5 USD, AWS có chắc chắn dừng mọi khoản phí sau 5 USD không?
4. Khi một lệnh CLI trả về **AccessDenied**, nên xác minh danh tính và chính sách nào?
5. Khi xóa EC2 hoặc RDS, những tài nguyên phụ hoặc dữ liệu tồn lưu nào cần kiểm tra?

Bạn hoàn thành bài học khi có thể giải thích các câu hỏi trên và thực hiện trọn vẹn chuỗi **xác minh → tạo → gắn tag và bảo vệ → kiểm thử → dọn** trên account thực hành của mình.

## Tài liệu AWS chính thức để tra cứu

- [AWS Global Infrastructure — Regions and Availability Zones](https://aws.amazon.com/about-aws/global-infrastructure/regions_az/)
- [AWS IAM — Security best practices](https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html)
- [AWS CLI v2 — Cài đặt](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html)
- [AWS CLI — Cấu hình IAM Identity Center](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-sso.html)
- [AWS Budgets — Quản lý ngân sách](https://docs.aws.amazon.com/cost-management/latest/userguide/budgets-managing-costs.html)
- [S3 general purpose bucket naming rules](https://docs.aws.amazon.com/AmazonS3/latest/userguide/bucketnamingrules.html)
- [AWS tagging best practices](https://docs.aws.amazon.com/whitepapers/latest/tagging-best-practices/tagging-best-practices.html)

**Ghi nhớ:** Bảng giá, điều kiện ưu đãi, giao diện Console và dịch vụ khả dụng có thể thay đổi. Trước khi triển khai một bài lab mới, kiểm tra tài liệu và giá AWS hiện hành cho account/Region của bạn.

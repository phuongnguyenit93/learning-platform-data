# AWS Management Console, CloudShell và AWS CLI

Trong hệ sinh thái Amazon Web Services (AWS), một tài nguyên như EC2 instance, S3 bucket hay VPC có thể được quản lý qua giao diện web, cửa sổ dòng lệnh trên trình duyệt hoặc công cụ dòng lệnh cài trên máy cá nhân. Ba cách tiếp cận phổ biến là **AWS Management Console**, **AWS CloudShell** và **AWS Command Line Interface (AWS CLI)**. Nắm được điểm giống, khác và cách xác thực của chúng là kỹ năng nền tảng trước khi triển khai ứng dụng an toàn, giám sát vận hành hay tự động hóa hạ tầng.

> **Phạm vi bài học:** Tìm hiểu cách truy cập và thao tác với AWS bằng Console, CloudShell và AWS CLI; nhận diện đúng tài khoản, IAM principal và Region; thực hành các lệnh kiểm tra tài nguyên chỉ đọc; xử lý lỗi thường gặp; lựa chọn công cụ phù hợp với công việc. Các ví dụ dùng Region `ap-southeast-1` (Singapore), có thể thay bằng Region được tổ chức cho phép sử dụng.

## 1. Kết quả học tập

Sau bài này, người học có thể:

1. Phân biệt Console, CloudShell và AWS CLI theo nơi chạy, cách xác thực, tính lặp lại và mục đích sử dụng.
2. Xác định **AWS account**, **IAM identity/role**, **Region** trước khi thao tác; hiểu vì sao đăng nhập thành công chưa đồng nghĩa có quyền với mọi tài nguyên.
3. Mở CloudShell, dùng AWS CLI đã cài sẵn và biết dữ liệu nào được giữ lại giữa các phiên.
4. Cài AWS CLI v2 trên máy cá nhân, tạo profile qua **AWS IAM Identity Center** và thực thi lệnh với profile/Region rõ ràng.
5. Đọc kết quả JSON, lọc bằng `--query` và biết tác động của phân trang.
6. Thực hành kiểm tra tài nguyên AWS theo nguyên tắc đặc quyền tối thiểu, tránh tạo chi phí ngoài ý muốn.

## 2. Ba cách làm việc trên cùng hệ thống AWS

Mọi phương thức đều hướng đến **AWS service API** và chịu sự kiểm tra quyền truy cập của AWS. Giao diện khác nhau không làm thay đổi quy tắc ủy quyền của IAM.

| Tiêu chí | AWS Management Console | AWS CloudShell | AWS CLI cài cục bộ |
|---|---|---|---|
| Điểm truy cập | Trình duyệt web, giao diện trực quan | Terminal trong trình duyệt, mở từ Console | Terminal trên Windows, macOS, Linux hoặc môi trường tự động hóa |
| Chuẩn bị | Trình duyệt và quyền đăng nhập | Có phiên Console và quyền dùng CloudShell; CLI được cài sẵn | Cài AWS CLI và cấu hình cách nhận credentials |
| Xác thực | Phiên đăng nhập AWS, thường qua IAM Identity Center/role | Kế thừa credentials của phiên Console | Profile IAM Identity Center, IAM role hoặc nguồn credentials khác |
| Công việc phù hợp | Khám phá dịch vụ, xem cấu hình, thao tác ít bước | Kiểm tra nhanh, chạy lệnh/script ngắn mà không cài phần mềm | Tác vụ lặp lại, xử lý hàng loạt, tích hợp shell/CI |
| Điểm cần lưu ý | Dễ bỏ sót account hoặc Region khi chuyển màn hình | Có hạn mức phiên, lưu trữ và Region hỗ trợ | Cần quản lý profile, phiên đăng nhập, phiên bản và môi trường máy |

~~~mermaid
flowchart TD
    U[Người vận hành] --> C[AWS Management Console]
    C --> H[AWS CloudShell]
    U --> L[AWS CLI trên máy/CI]
    C --> A[AWS service APIs]
    H --> A
    L --> A
    A --> P[Đánh giá quyền IAM và các chính sách liên quan]
    P --> R[Tài nguyên trong AWS account và Region]
~~~

**Ví dụ:** Khi cần xem vì sao một EC2 instance không khởi động, người mới có thể mở **EC2 → Instances** trong Console để quan sát trạng thái. Người vận hành có thể dùng CloudShell chạy `aws ec2 describe-instances` để lấy dữ liệu nhanh. Một script dùng AWS CLI có thể chạy lệnh đọc tương tự trên nhiều account/Region đã được cấp quyền. Dù dùng cách nào, lệnh sửa/xóa tài nguyên vẫn cần quyền AWS phù hợp.

### 2.1. Bốn khái niệm cần phân biệt

- **Account:** Ranh giới quản trị, định danh bằng AWS account ID 12 chữ số. Một tổ chức có thể tách account phát triển, thử nghiệm và sản xuất.
- **Identity/principal:** IAM user hoặc vai trò đang được đảm nhận; khi người dùng đăng nhập qua IAM Identity Center, họ thường truy cập account thông qua một IAM role với tập quyền được gán.
- **Region:** Khu vực địa lý chứa các dịch vụ/tài nguyên có phạm vi Region, chẳng hạn VPC và EC2. Region Singapore có mã `ap-southeast-1`; Region Tokyo có mã `ap-northeast-1`.
- **Availability Zone (AZ):** Một hoặc nhiều trung tâm dữ liệu tách biệt trong Region. Ví dụ, subnet thuộc một AZ, còn VPC trải trên phạm vi Region.

Không phải mọi dịch vụ đều có cùng phạm vi. **IAM** là dịch vụ có phạm vi toàn cục ở mức account; **Amazon CloudFront** quản lý distribution toàn cục; **EC2/VPC** mang tính Region. **Tên S3 bucket** phải duy nhất trong phạm vi namespace bucket tương ứng, nhưng mỗi general purpose bucket thuộc một Region. Vì vậy, thay đổi Region trong Console có thể làm danh sách EC2 trống trong khi tài nguyên đang tồn tại ở Region khác.

## 3. AWS Management Console

AWS Management Console là giao diện web để duyệt dịch vụ, theo dõi tài nguyên, cấu hình quyền, xem số liệu giám sát và thực hiện nhiều tác vụ quản trị mà không cần tự soạn API request.

### 3.1. Đăng nhập và xác nhận ngữ cảnh

1. Mở [AWS Management Console](https://console.aws.amazon.com/) hoặc **AWS access portal** do tổ chức cung cấp.
2. Với môi trường tổ chức, ưu tiên **IAM Identity Center**, đăng nhập đa yếu tố (MFA), chọn đúng AWS account và vai trò/permission set được cấp.
3. Kiểm tra tên/account ID, role đang dùng ở menu danh tính, nhất là khi có các account `dev`, `staging` và `prod`.
4. Chọn Region tại thanh điều hướng, ví dụ **Asia Pacific (Singapore) – `ap-southeast-1`**.
5. Dùng ô tìm kiếm dịch vụ để mở **EC2**, **VPC**, **S3**, **CloudWatch** hoặc **IAM**.

**Không dùng root user để thao tác thường ngày.** Root có quyền đặc biệt ở cấp account, phù hợp với một số tác vụ quản trị bắt buộc và cần được bảo vệ nghiêm ngặt bằng MFA. Đăng nhập vào một account vẫn không có nghĩa được phép tạo, sửa hoặc xem mọi tài nguyên: IAM policies, permission boundaries, service control policies (SCP) và resource policies có thể giới hạn quyền.

### 3.2. Một hành trình khám phá an toàn

Ví dụ muốn kiểm tra hạ tầng mạng đang tồn tại:

1. Kiểm tra **account và Region** ở thanh đầu trang.
2. Vào **VPC → Your VPCs** và quan sát VPC ID, IPv4 CIDR, trạng thái, loại VPC mặc định hay tùy chỉnh.
3. Vào **VPC → Subnets** để nhận biết subnet nằm ở AZ nào.
4. Vào **EC2 → Instances** để xem instance ID, loại máy, trạng thái và VPC/subnet liên quan.
5. Nếu không thấy tài nguyên, xác minh lại Region, bộ lọc giao diện và quyền đọc; đừng vội tạo tài nguyên mới.

Một số chức năng Console dùng trình hướng dẫn nhiều bước và có thể ngầm gợi ý tạo security group, volume, public IP hoặc tài nguyên kèm theo. Trước nút **Create**, **Save**, **Delete**, **Terminate**, cần xem lại toàn bộ lựa chọn, ước lượng chi phí và ảnh hưởng. Việc chỉ mở trang/đọc cấu hình thường ít rủi ro hơn thao tác thay đổi trạng thái.

### 3.3. Ưu điểm và giới hạn

Console thuận tiện để phát hiện các thuộc tính chưa quen và xem quan hệ giữa dịch vụ. Tuy nhiên, nhiều lần nhấn chuột khó tái hiện chính xác, nhất là với hệ thống gồm hàng chục VPC, instance hoặc account. Khi đã hiểu thao tác, có thể diễn đạt nó bằng AWS CLI và cuối cùng chuyển các thay đổi hạ tầng lặp lại sang Infrastructure as Code (ví dụ CloudFormation hoặc Terraform), có kiểm soát thay đổi và lịch sử mã nguồn.

## 4. AWS CloudShell

**AWS CloudShell** là môi trường shell được AWS quản lý và mở ngay trong trình duyệt từ Console. Môi trường tiêu chuẩn dựa trên Amazon Linux 2023, hỗ trợ Bash, PowerShell và Z shell, có sẵn **AWS CLI v2** cùng nhiều công cụ thông dụng. CloudShell giúp thực hành lệnh AWS mà không phải cài CLI hoặc lưu access key trên máy cá nhân.

### 4.1. Mở CloudShell và kiểm tra phiên

1. Đăng nhập Console bằng identity có quyền CloudShell.
2. Chọn Region, tìm biểu tượng **CloudShell** trên thanh điều hướng hoặc ở khu vực điều khiển Console, rồi mở terminal.
3. Đợi môi trường sẵn sàng và nhập các lệnh sau:

~~~bash
aws --version
aws sts get-caller-identity
aws configure list
echo "$AWS_REGION"
~~~

`aws --version` cho biết phiên bản CLI đã cài. `aws sts get-caller-identity` trả về `UserId`, `Account` và `Arn` của principal thực sự gửi request. Đây là kiểm tra quan trọng nhất trước khi chạy lệnh làm thay đổi tài nguyên. `aws configure list` hiển thị **nguồn** cấu hình/credentials ở mức chẩn đoán; không in secret access key hay session token vào tài liệu, ticket hoặc log. `AWS_REGION` cho biết Region môi trường đang đặt làm mặc định.

Khi mở CloudShell theo phiên đăng nhập Console, **credentials được cung cấp tự động** nên thông thường **không cần `aws configure`** để khai báo access key. Quyền gọi API là quyền của principal đó, không tự động được nâng lên thành administrator. Một identity cần cả quyền dùng CloudShell (trong đó có cơ chế truyền credentials) và quyền trên dịch vụ muốn thao tác. Chính sách AWS-managed `AWSCloudShellFullAccess` là một cách cấp quyền dùng CloudShell khi tổ chức chấp thuận; không phải là yêu cầu cấp quyền administrator cho mọi người học.

### 4.2. Region trong CloudShell

CloudShell có Region chạy môi trường shell. Thông thường Region này đồng bộ với Region đã chọn khi mở từ Console. Region mặc định của AWS CLI trong CloudShell được đặt qua biến môi trường `AWS_REGION`.

~~~bash
# Chỉ tác động tới phiên shell đang mở
export AWS_REGION=ap-southeast-1

# Luôn có thể ghi rõ Region cho một lệnh
aws ec2 describe-vpcs --region ap-southeast-1 --output table
~~~

**Phân biệt:** Region chứa *môi trường CloudShell* và Region đích mà *AWS CLI gọi API* có thể khác nhau. Tham số `--region` của lệnh CLI chỉ định đích API; nó không di chuyển tệp trong CloudShell sang Region khác. Đổi Region của môi trường trên giao diện CloudShell có thể tạo phiên với thư mục home khác.

### 4.3. Tệp, thời gian phiên và chi phí

| Thành phần | Cách hoạt động cần nhớ |
|---|---|
| Thư mục `$HOME` (CloudShell tiêu chuẩn) | Có tối đa **1 GiB** lưu trữ bền vững **theo từng Region**, không đồng bộ giữa các Region |
| Tệp ngoài `$HOME` | Có thể bị dọn khi phiên/môi trường tạm thời kết thúc; không dùng để lưu dữ liệu cần giữ |
| Không dùng CloudShell trong một Region | Dữ liệu home có chính sách lưu giữ; theo tài liệu AWS, có thể bị xóa sau **120 ngày** không dùng tại Region đó |
| CloudShell VPC environment | Có khả năng kết nối tới tài nguyên VPC theo cấu hình, nhưng **không có lưu trữ home bền vững** như môi trường tiêu chuẩn |
| Phiên shell | Dành cho thao tác tương tác/script ngắn; có giới hạn phiên, thời gian không hoạt động và tài nguyên |
| Phí | CloudShell không thu phí riêng cho môi trường tiêu chuẩn, nhưng tài nguyên AWS được tạo/sử dụng và lưu lượng truyền dữ liệu có thể phát sinh phí |

Không lưu bí mật, khóa truy cập dài hạn hoặc dữ liệu khách hàng nhạy cảm trong script thực hành. Nếu cần công việc chạy hàng giờ, môi trường triển khai ổn định hoặc lịch chạy tự động, hãy dùng dịch vụ phù hợp như AWS Systems Manager, CodeBuild, Lambda, ECS hoặc một nền tảng CI được quản trị, tùy yêu cầu.

### 4.4. Dùng CloudShell khi nào?

CloudShell rất hợp với thao tác kiểm tra cấu hình, lệnh nhất thời, đối chiếu API với Console, hoặc xử lý tình huống khi máy làm việc chưa có AWS CLI. Giới hạn của nó là tài nguyên, thời lượng, tính lưu trữ và tính phụ thuộc vào phiên Console; không thay thế hệ thống chạy job dài hạn.

## 5. AWS CLI v2 trên máy cá nhân

**AWS CLI** là công cụ cho phép gọi AWS APIs qua cú pháp dòng lệnh. Cấu trúc tổng quát:

~~~text
aws <service> <operation> [tham-số-của-operation] [global-options]
~~~

Ví dụ:

~~~bash
aws sts get-caller-identity
aws ec2 describe-vpcs --region ap-southeast-1 --output json
aws s3 ls
~~~

Ở đây, `sts`, `ec2`, `s3` là nhóm dịch vụ; `get-caller-identity`, `describe-vpcs` và `ls` là thao tác. Một số dịch vụ có cả lệnh cấp cao, thân thiện như `aws s3 ls`, và lệnh ánh xạ gần API hơn như `aws s3api list-buckets`.

### 5.1. Cài đặt và xác minh

AWS CLI v2 có bộ cài riêng cho Windows, macOS và Linux. Sử dụng hướng dẫn chính thức [Installing or updating to the latest version of the AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) để lấy bộ cài đúng hệ điều hành/kiến trúc, rồi chạy:

~~~bash
aws --version
aws help
aws sts help
~~~

Kết quả `aws --version` phải cho biết `aws-cli/2...` nếu đang dùng v2. Nếu máy đang có CLI v1, kiểm tra lại đường dẫn executable/PATH; cả hai phiên bản đều gọi bằng lệnh `aws`.

Việc cài CLI **chưa đồng nghĩa đã xác thực được** với AWS: tiếp theo cần một cách lấy credentials hợp lệ.

### 5.2. Đăng nhập qua IAM Identity Center (khuyến nghị cho người dùng)

Trong môi trường doanh nghiệp, quản trị viên thường cung cấp **AWS access portal URL (SSO start URL)**, Region của IAM Identity Center và account/role được phép sử dụng. Tạo profile tên `dev`:

~~~bash
# Chạy ở terminal trên máy đã cài AWS CLI v2
aws configure sso --profile dev

# Làm theo hướng dẫn đăng nhập qua trình duyệt
# và chọn account, role, Region mặc định, định dạng output.
aws sso login --profile dev

# Kiểm tra danh tính thực sự của request
aws sts get-caller-identity --profile dev
~~~

`aws configure sso` tạo cấu hình để profile dùng phiên SSO và lấy **temporary credentials** cho role. `aws sso login` tiến hành đăng nhập và lưu thông tin phiên theo cơ chế của CLI. Khi phiên đăng nhập Identity Center hết hạn, đăng nhập lại thay vì tạo access key dài hạn.

**Hai Region khác nhau cần để ý:** `SSO region` là Region chứa cấu hình IAM Identity Center; `CLI default client Region` là Region mặc định của API AWS khi dùng profile. Chúng có thể không giống nhau.

Ví dụ cấu trúc minh họa của tệp `~/.aws/config` (địa chỉ/account/role chỉ là dữ liệu giả định):

~~~ini
[profile dev]
sso_session = company
sso_account_id = 111122223333
sso_role_name = ReadOnly
region = ap-southeast-1
output = json

[sso-session company]
sso_start_url = https://example.awsapps.com/start
sso_region = ap-southeast-1
sso_registration_scopes = sso:account:access
~~~

File trên là **ví dụ**, không phải cấu hình có thể dùng cho tài khoản thật. Trong thực tế, để CLI tạo file thay vì chép tay thì chạy `aws configure sso`; đừng commit cấu hình nội bộ hoặc thông tin phiên vào repository công khai.

### 5.3. Profile, Region và thứ tự ưu tiên

Một máy có thể dùng nhiều profile với các quyền/account khác nhau. Hãy truyền `--profile` và `--region` tường minh khi đang học hoặc thao tác trên tài nguyên quan trọng.

~~~bash
aws configure list-profiles
aws configure list --profile dev

aws sts get-caller-identity --profile dev
aws ec2 describe-vpcs --profile dev --region ap-southeast-1
~~~

Có thể chọn profile mặc định trong một phiên terminal:

~~~bash
# Bash, Z shell (Linux/macOS hoặc CloudShell)
export AWS_PROFILE=dev
export AWS_REGION=ap-southeast-1
~~~

~~~powershell
# PowerShell (Windows)
$env:AWS_PROFILE = 'dev'
$env:AWS_REGION = 'ap-southeast-1'
~~~

Đối với các tùy chọn như Region, thứ tự ưu tiên thông thường là **tham số lệnh `--region` → biến môi trường → cấu hình profile**. Trong AWS CLI v2, `AWS_REGION` có thể ghi đè `AWS_DEFAULT_REGION`. Với profile, `--profile` ghi đè lựa chọn từ `AWS_PROFILE`. Nguồn credentials có nhiều cơ chế và thứ tự ưu tiên riêng; nếu lệnh lấy nhầm identity, kiểm tra `aws configure list` và các biến môi trường liên quan trước khi chỉnh file cấu hình.

**Lưu ý bảo mật:** Không dùng `aws configure` với access key dài hạn của IAM user để thay thế đăng nhập SSO khi tổ chức đã hỗ trợ Identity Center. Với ứng dụng chạy trên EC2/ECS/Lambda, nên dùng IAM role được gắn với workload để nhận temporary credentials, không chép credentials của con người vào máy chủ.

### 5.4. Đọc output, lọc dữ liệu và tìm trợ giúp

AWS CLI hỗ trợ các định dạng đầu ra thông dụng:

- `--output json`: thuận tiện cho script, phân tích trường dữ liệu và công cụ xử lý JSON.
- `--output table`: thuận tiện cho người đọc nhanh ở terminal.
- `--output text`: dữ liệu dạng văn bản phân tách theo cột; cần thận trọng khi parse tự động, nhất là kết quả nhiều trang.

Tùy chọn `--query` dùng biểu thức **JMESPath** để lọc các trường trong kết quả trả về. Ví dụ truy vấn VPC:

~~~bash
aws ec2 describe-vpcs \
  --profile dev \
  --region ap-southeast-1 \
  --query 'Vpcs[].{Id:VpcId,Cidr:CidrBlock,Default:IsDefault}' \
  --output table
~~~

Đầu ra có thể hiển thị cột `Id`, `Cidr`, `Default`. Nếu account chưa có VPC ở Region này, bảng trống là điều bình thường. `--query` chỉ lọc dữ liệu **sau khi AWS cho phép request**, không tạo thêm quyền truy cập hay che dữ liệu mà người dùng không được phép xem theo IAM.

Để khám phá lệnh:

~~~bash
aws help
aws ec2 help
aws ec2 describe-vpcs help
~~~

Nếu CLI v2 bật trình phân trang đầu ra (pager), có thể thêm `--no-cli-pager` để in trực tiếp vào terminal. **Không nhầm `--no-cli-pager` với `--no-paginate`**: tùy chọn thứ hai tắt tự động gọi các trang kết quả của API và có thể chỉ trả trang đầu. Mặc định, CLI tự ghép các trang cho các lệnh hỗ trợ phân trang; dùng `--max-items` / `--starting-token` khi chủ đích xử lý dữ liệu theo từng đợt.

## 6. Bài thực hành: đối chiếu Console, CloudShell và CLI

### 6.1. Điều kiện ban đầu

Cần có một AWS account thực hành, quyền xem VPC/EC2/S3 phù hợp, quyền vào CloudShell nếu dùng giao diện này và (tùy chọn) một profile CLI `dev` đã đăng nhập qua IAM Identity Center. Không cần tạo EC2, VPC hay S3 bucket mới trong bài.

Đặt hai biến ngữ cảnh:

- **Account đích:** ID account được cấp cho môi trường học.
- **Region đích:** `ap-southeast-1` hoặc Region được người quản trị chỉ định.

Nếu dùng **CloudShell**, các lệnh bên dưới chạy với credentials kế thừa từ Console; bỏ `--profile dev`. Nếu dùng **CLI cục bộ**, thêm `--profile dev` vào các lệnh AWS hoặc đặt `AWS_PROFILE` trong terminal.

### 6.2. Bước A – xác nhận đúng account và role

Trong Console, mở menu danh tính và đọc account/role. Trong CloudShell chạy:

~~~bash
aws sts get-caller-identity \
  --query '{Account:Account,Principal:Arn}' \
  --output json
~~~

Ví dụ kết quả **minh họa**:

~~~json
{
  "Account": "111122223333",
  "Principal": "arn:aws:sts::111122223333:assumed-role/ExampleReadOnly/session-name"
}
~~~

So sánh trường `Account` với account đã chọn trong Console. Nếu `Arn` chứa `assumed-role/...`, bạn đang làm việc qua một role session. Không chép kết quả của tài khoản thật vào nơi công khai khi không có nhu cầu.

Trên CLI cục bộ, kiểm tra tương đương:

~~~bash
aws sts get-caller-identity --profile dev --output json
~~~

### 6.3. Bước B – xem VPC theo Region

Trong Console, mở **VPC → Your VPCs**, chọn Singapore và ghi nhận các VPC ID có quyền nhìn thấy. Trong CloudShell:

~~~bash
aws ec2 describe-vpcs \
  --region ap-southeast-1 \
  --query 'Vpcs[].{VpcId:VpcId,Cidr:CidrBlock,Default:IsDefault,State:State}' \
  --output table
~~~

Nếu không có VPC, API vẫn có thể trả danh sách rỗng thành công. Nếu báo `AccessDenied`, cần quyền `ec2:DescribeVpcs` tương ứng. **Không tạo VPC mới chỉ để có kết quả.**

### 6.4. Bước C – xem EC2 instance mà không thay đổi trạng thái

Trong Console, mở **EC2 → Instances** và bỏ bộ lọc không cần thiết. Chạy:

~~~bash
aws ec2 describe-instances \
  --region ap-southeast-1 \
  --query 'Reservations[].Instances[].{Id:InstanceId,Type:InstanceType,State:State.Name,Vpc:VpcId}' \
  --output table
~~~

Khi danh sách rỗng, có thể do chưa có instance, chọn sai Region, filter Console hoặc không đủ quyền. Các lệnh `describe-*` ở đây chỉ đọc metadata; tuyệt đối không tự thay bằng `run-instances`, `start-instances` hay `terminate-instances` trong account chung.

### 6.5. Bước D – quan sát danh sách S3 bucket

~~~bash
aws s3api list-buckets \
  --query 'Buckets[].Name' \
  --output table
~~~

Lệnh này cần quyền `s3:ListAllMyBuckets` thích hợp. S3 có mô hình phạm vi khác EC2: danh sách bucket của account không đồng nghĩa tất cả bucket đều nằm trong Region hiện tại. Với bucket cụ thể, có thể hỏi vị trí:

~~~bash
# Thay YOUR_BUCKET_NAME bằng bucket được phép xem.
aws s3api get-bucket-location --bucket YOUR_BUCKET_NAME
~~~

Kết quả `LocationConstraint` của bucket ở `us-east-1` có thể là `null` do quy ước API lịch sử; vì vậy không diễn giải `null` là bucket không có Region. Cần quyền IAM phù hợp để chạy `get-bucket-location`.

### 6.6. Bước E – ghi lại bằng chứng và đối chiếu

Ghi lại **account ID**, **principal ARN**, **Region**, số VPC và số EC2 instance bạn có quyền nhìn thấy; có thể dùng tên/ID giả lập khi trình bày công khai. Kiểm tra xem Console và CLI có đang cùng account/Region hay không. Nếu kết quả khác nhau, trước tiên kiểm tra **danh tính, Region, filter và quyền** trước khi nghi ngờ sự cố AWS.

Mở AWS CLI trên máy bằng profile `dev` và chạy lại lệnh VPC:

~~~bash
aws ec2 describe-vpcs \
  --profile dev \
  --region ap-southeast-1 \
  --query 'Vpcs[].VpcId' \
  --output json
~~~

Khi danh tính, Region và quyền tương đương, Console và CLI cần phản ánh cùng tập tài nguyên tại thời điểm truy vấn, trừ khác biệt do bộ lọc, thời điểm dữ liệu hoặc quyền truy cập.

## 7. Vận hành an toàn và kiểm soát chi phí

### 7.1. Trước khi chạy bất kỳ lệnh thay đổi nào

Một số lệnh CLI có thể tạo hoặc xóa hạ tầng chỉ bằng một dòng. Thói quen vận hành cần hình thành:

1. Chạy `aws sts get-caller-identity` và xác nhận account/role.
2. Ghi `--region` và `--profile` (khi cần) trong lệnh hoặc script quan trọng.
3. Xem quyền tác động, tên resource, tham số và phụ thuộc trước khi tạo/sửa/xóa.
4. Ưu tiên kiểm tra trước bằng lệnh `list-*`, `describe-*`, `get-*` thích hợp; dùng `--dry-run` **chỉ khi operation đó thực sự hỗ trợ**.
5. Với môi trường production, thực hiện quy trình review/approval của tổ chức và chuẩn bị cách khôi phục.

### 7.2. Quản trị quyền

**Least privilege** là nguyên tắc chỉ cấp quyền cần thiết cho nhiệm vụ. Một account có thể cho phép `ec2:DescribeInstances` nhưng từ chối `ec2:TerminateInstances`. AWS thực hiện đánh giá ủy quyền từ nhiều lớp: identity-based policies, resource-based policies, permission boundaries, session policies, SCP trong AWS Organizations và explicit deny khi áp dụng. Cấp quyền sử dụng CloudShell **không** tương đương cấp quyền quản lý EC2/S3.

Dùng IAM Identity Center + MFA cho nhân sự. Đối với workload, ưu tiên temporary credentials từ IAM role. Không viết access key/secret key vào mã nguồn, history shell, issue tracker hoặc log CI. Đừng dùng `--no-verify-ssl` để “sửa nhanh” lỗi chứng chỉ, vì cách đó làm mất bước xác minh TLS; cần sửa trust store/proxy đúng cách.

### 7.3. Quan sát và kiểm toán

AWS CloudTrail có thể ghi các hoạt động gọi API AWS theo cấu hình trail/event history và loại event; CloudWatch hỗ trợ metrics, logs và alarm tương ứng với dịch vụ. Khi điều tra thay đổi hạ tầng, cần quan tâm principal, action, thời điểm, Region, resource và kết quả request. Console và CLI là các **đường truy cập**; việc người dùng thao tác bằng cách nào không làm thay đổi yêu cầu ghi nhận, giám sát và kiểm toán của tổ chức.

### 7.4. Chi phí

Console và AWS CLI là cách điều khiển dịch vụ, không phải “chế độ miễn phí” cho tài nguyên được tạo. CloudShell thông thường không có phí môi trường riêng nhưng việc tạo EC2, ghi S3, truyền dữ liệu hoặc sử dụng các dịch vụ khác vẫn có thể phát sinh chi phí. Trước bài thực hành có thao tác tạo resource, nên kiểm tra Pricing Calculator, budget/cảnh báo chi phí, hạn mức quyền và kế hoạch dọn dẹp.

## 8. Sự cố thường gặp và hướng xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra/xử lý |
|---|---|---|
| `Unable to locate credentials` | CLI cục bộ chưa cấu hình profile/role, hoặc không tìm thấy nguồn credentials | Chạy `aws configure list --profile dev`; với Identity Center, cấu hình SSO và đăng nhập |
| `The SSO session associated with this profile has expired` | Phiên Identity Center hết hạn | Chạy lại `aws sso login --profile dev` |
| `AccessDenied` / `UnauthorizedOperation` | IAM thiếu action/resource phù hợp; có deny từ policy/SCP/boundary | Đối chiếu action cần thiết, account, principal, chính sách; xin cấp quyền tối thiểu qua quy trình tổ chức |
| `You must specify a region` | Lệnh cần endpoint Region nhưng chưa có giá trị mặc định | Thêm `--region ap-southeast-1` hoặc cấu hình Region của profile |
| Console thấy tài nguyên nhưng CLI trả rỗng | Khác account/role/Region, filter hoặc thời điểm truy vấn | Chạy `get-caller-identity`, xác nhận Region, bỏ filter; thử truy vấn lại |
| `aws: command not found` / `aws is not recognized` | Chưa cài AWS CLI hoặc PATH chưa đúng | Kiểm tra bộ cài chính thức, mở lại terminal, chạy `aws --version` |
| CloudShell không khởi động | Thiếu quyền CloudShell, Region không hỗ trợ, lỗi phiên hoặc hạn mức | Kiểm tra quyền CloudShell/Region và thông báo trên Console; liên hệ admin nếu cần |
| Không thấy file CloudShell từ phiên/Region trước | Đã lưu ngoài `$HOME` hoặc đổi Region; môi trường VPC không có lưu trữ bền vững | Kiểm tra đúng Region, thư mục home và giới hạn lưu trữ |
| CLI chỉ trả một phần danh sách | Đã dùng `--no-paginate` hoặc giới hạn `--max-items` | Kiểm tra cơ chế phân trang, `NextToken` và tùy chọn pager |

Dùng `--debug` chỉ khi cần chẩn đoán sâu và ở môi trường phù hợp: đầu ra debug có thể chứa URL, header, metadata request hoặc thông tin nhạy cảm. Luôn rà soát và che dữ liệu trước khi chia sẻ log.

## 9. Chọn công cụ trong các tình huống thực tế

| Nhu cầu | Lựa chọn xuất phát hợp lý | Lý do |
|---|---|---|
| Mới học VPC, IAM, EC2 và cần xem các trường cấu hình | Console | Dễ quan sát mối liên hệ giữa tài nguyên, filter và cài đặt |
| Đang mở Console và muốn kiểm tra account/Region ngay | CloudShell | Có AWS CLI v2, kế thừa credentials, không cần cài đặt |
| Cần chạy một lệnh kiểm tra trên môi trường máy cá nhân | AWS CLI + profile SSO | Dễ tái chạy, có lịch sử lệnh và quản lý profile |
| Cần thu thập báo cáo nhiều account/Region | AWS CLI trong script được quản trị | Dễ lặp, có thể sử dụng role và xử lý đầu ra JSON |
| Cần triển khai hạ tầng nhiều lần và có review phiên bản | Infrastructure as Code kết hợp CI/CD | Mô tả trạng thái mong muốn, review thay đổi và quản lý vòng đời tốt hơn |
| Cần một tiến trình chạy lâu, theo lịch hoặc có độ tin cậy cao | Dịch vụ vận hành chuyên dụng | CloudShell được thiết kế cho phiên tương tác, không cho job chạy bền vững |

**Tình huống tổng hợp:** Nhóm vận hành phát hiện một ứng dụng không kết nối được cơ sở dữ liệu RDS. Có thể dùng Console để xác định Region, VPC, security group và trạng thái DB; mở CloudShell để truy vấn nhanh metadata; dùng CLI trong script để thu thập thông số giữa các môi trường. Các bước cần quyền đọc ban đầu và sự phê duyệt tương ứng nếu sau đó phải thay đổi rule mạng, cấu hình database hoặc khởi động lại ứng dụng.

## 10. Tự kiểm tra sau bài học

Một người học đã nắm chắc kiến thức khi có thể thực hiện toàn bộ chuỗi sau bằng account thực hành được cấp quyền:

- Giải thích vì sao Console, CloudShell và CLI có thể cho cùng dữ liệu khi dùng chung principal/Region nhưng hiển thị khác nhau nếu đổi account hoặc bộ lọc.
- Tìm được account ID/role trên Console; dùng `aws sts get-caller-identity` đối chiếu.
- Mở CloudShell, xác nhận `aws --version`, chạy thành công ít nhất một lệnh `describe-*` hoặc giải thích rõ lỗi quyền.
- Nêu được điểm khác nhau giữa Region của CloudShell, Region của API, Region của IAM Identity Center và AZ.
- Tạo profile CLI theo SSO, chạy lệnh chỉ đọc với `--profile` và `--region` tường minh.
- Dùng `--query` để hiển thị trường cần thiết và không nhầm `--no-cli-pager` với `--no-paginate`.
- Giải thích vì sao quyền sử dụng CloudShell không cấp quyền quản trị tài nguyên, và vì sao một lệnh `create-*` có thể phát sinh chi phí.

## Tài liệu chính thức để tra cứu

1. [AWS Management Console](https://docs.aws.amazon.com/awsconsolehelpdocs/latest/gsg/what-is.html) – Khái niệm và cách sử dụng Console.
2. [What is AWS CloudShell?](https://docs.aws.amazon.com/cloudshell/latest/userguide/) – Môi trường shell, xác thực và công cụ đi kèm.
3. [AWS CloudShell: Working in AWS Regions](https://docs.aws.amazon.com/cloudshell/latest/userguide/working-with-aws-cloudshell.html) – Region, biến môi trường, dữ liệu bền vững.
4. [AWS CloudShell: Service quotas and restrictions](https://docs.aws.amazon.com/cloudshell/latest/userguide/limits.html) – Hạn mức và chính sách lưu trữ.
5. [AWS CloudShell: Managing access with IAM](https://docs.aws.amazon.com/cloudshell/latest/userguide/sec-auth-with-identities.html) – Quyền CloudShell và quyền gọi dịch vụ.
6. [AWS CLI v2: Install or update](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) – Cài đặt theo hệ điều hành.
7. [AWS CLI v2: Configure IAM Identity Center](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-sso.html) – Tạo profile SSO và đăng nhập.
8. [AWS CLI: Environment variables](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-envvars.html) – Cấu hình và thứ tự ưu tiên.
9. [AWS CLI: Pagination](https://docs.aws.amazon.com/cli/latest/userguide/cli-usage-pagination.html) – Truy xuất đầy đủ kết quả nhiều trang.

> **Ghi nhớ:** Trước mọi thao tác với AWS, hãy kiểm tra **ai đang gọi (principal), account nào, Region nào, cần quyền gì và lệnh có làm thay đổi tài nguyên/chi phí hay không**. Đây là nền tảng để dùng các dịch vụ tính toán, lưu trữ, cơ sở dữ liệu, mạng, serverless, giám sát và phục hồi một cách có kiểm soát.


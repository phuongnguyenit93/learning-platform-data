# Truy cập máy chủ qua Session Manager và EC2 Instance Connect

> **Chương:** Máy chủ EC2  
> **Học phần:** `CLOUD_PROVIDERS_AWS` — khám phá AWS từ Region/AZ, IAM và VPC tới tính toán, lưu trữ, dữ liệu, tích hợp và serverless; thực hành thiết kế, vận hành ứng dụng an toàn, có thể giám sát, phục hồi và kiểm soát chi phí.

Khi vận hành Amazon EC2, chúng ta thường cần đăng nhập để kiểm tra nhật ký, sửa cấu hình, chẩn đoán lỗi mạng hoặc xử lý sự cố. Cách truyền thống là mở SSH (cổng TCP 22) từ máy quản trị tới EC2 Linux. Trong môi trường production, mở SSH trực tiếp qua Internet làm tăng diện tấn công, khiến việc quản lý khóa SSH và kiểm soát danh tính trở nên phức tạp.

AWS cung cấp hai phương thức truy cập thường được cân nhắc:

- **AWS Systems Manager Session Manager**: thiết lập phiên làm việc thông qua Systems Manager và SSM Agent, thường không cần public IP hay mở cổng SSH inbound.
- **Amazon EC2 Instance Connect (EIC)**: cấp một **SSH public key tạm thời** cho EC2 Linux rồi kết nối bằng SSH. Với **EC2 Instance Connect Endpoint (EICE)**, kết nối có thể đi vào instance dùng private IP mà không cần Internet Gateway, bastion host hay public IP.

Hai phương thức đều kết hợp được với **IAM**, nhưng **cách kết nối, yêu cầu mạng, cách xác thực trong hệ điều hành và khả năng ghi nhật ký** khác nhau. Bài học hướng dẫn chọn phương án phù hợp với từng tình huống và kiểm tra đường truy cập trước khi dùng cho production.

## 1. Mục tiêu học tập

Sau khi hoàn thành bài này, người học có thể:

1. Phân biệt Session Manager, EC2 Instance Connect qua public IP và EC2 Instance Connect Endpoint qua private IP.
2. Chuẩn bị đúng IAM permissions, instance profile, agent hoặc gói hỗ trợ SSH, Security Group và kết nối VPC.
3. Dùng AWS Console/AWS CLI để mở phiên quản trị, hiểu vai trò của OS user và khóa SSH.
4. Thiết kế truy cập tới EC2 trong private subnet với VPC interface endpoints hoặc EIC Endpoint.
5. Giải thích giới hạn của session logging, CloudTrail và các biện pháp giảm rủi ro truy cập đặc quyền.
6. Chẩn đoán lỗi `TargetNotConnected`, `AccessDenied`, SSH timeout, sai OS user và lỗi kết nối mạng.

## 2. Một bản đồ về ba đường truy cập

~~~mermaid
flowchart TB
    A["Người quản trị đã xác thực IAM"]
    subgraph AWS["AWS control plane và kết nối được ủy quyền"]
        SSM["Systems Manager Session Manager"]
        EIC["EC2 Instance Connect API"]
        EICE["EC2 Instance Connect Endpoint"]
    end
    subgraph VPC["Amazon VPC"]
        Agent["EC2 Linux/Windows có SSM Agent"]
        Public["EC2 Linux có SSH và IP công khai"]
        Private["EC2 Linux có SSH, private IP"]
    end
    A -->|"StartSession, HTTPS"| SSM
    Agent -->|"Kênh outbound TLS 443"| SSM
    A -->|"SendSSHPublicKey, IAM"| EIC
    EIC -.->|"Khóa SSH tạm thời tại instance metadata"| Public
    A -->|"SSH TCP 22 qua Internet"| Public
    A -->|"OpenTunnel, IAM"| EICE
    EICE -->|"TCP 22 qua VPC"| Private
    EIC -.->|"Có thể cấp public key cho SSH"| Private
~~~

*Các nhánh mô tả phương thức điển hình. EICE là đường hầm TCP và có thể dùng với SSH key đã tồn tại; việc cấp khóa qua EIC API và việc tạo đường hầm EICE là **hai thao tác riêng**. Nhiều phiên cũng có thể sử dụng cấu hình khác như kết nối SSH qua Session Manager.*

| Tiêu chí | Session Manager | EIC qua public IP | EIC qua EIC Endpoint |
| --- | --- | --- | --- |
| Công nghệ điều khiển phiên | Systems Manager và SSM Agent | SSH và EIC API cấp public key | SSH/TCP tunnel qua EICE, có thể kết hợp EIC API |
| Instance cần public IP? | **Không** | Thường **có** nếu kết nối trực tiếp từ Internet | **Không** |
| Cần inbound TCP 22 trên EC2? | **Không** cho shell Session Manager chuẩn | **Có** từ nguồn SSH phù hợp | **Có** từ endpoint theo mô hình mạng |
| Yêu cầu trên instance | SSM Agent, quyền instance profile, mạng outbound tới SSM | SSH server, EIC hỗ trợ AMI/OS user, đường mạng public | SSH server; gói EIC nếu dùng khóa tạm thời; đường tới EICE |
| IAM của người dùng | `ssm:StartSession` và quyền liên quan | `ec2-instance-connect:SendSSHPublicKey` và quyền xem EC2 | `ec2-instance-connect:OpenTunnel` và quyền liên quan; thêm SendSSHPublicKey nếu dùng khóa tạm thời |
| Cơ chế ghi nhật ký nội dung | Có thể cấu hình với shell Session Manager chuẩn | Không tự ghi toàn bộ nội dung SSH qua Session Manager | Không tự ghi toàn bộ nội dung SSH/tunnel |
| Mục tiêu phù hợp | Quản trị phổ biến không cần SSH public | Hệ thống Linux có sẵn SSH và IP công khai | Máy Linux private cần SSH; một số TCP tunnel khác |

**Cần phân biệt thêm:** EIC Endpoint không phải **VPC interface endpoint cho dịch vụ SSM**. Một cái là đường hầm TCP đến EC2; cái kia là đường kết nối riêng từ **SSM Agent** tới API Systems Manager.

## 3. Session Manager hoạt động như thế nào?

**Session Manager** là thành phần của **AWS Systems Manager**. Khi người dùng được IAM cho phép bắt đầu một phiên, SSM Agent trên EC2 thiết lập kênh truyền dữ liệu thông qua dịch vụ AWS. Vì **kênh từ instance được khởi tạo outbound**, bạn thường không cần gán public IP, không cần mở TCP 22 inbound và không cần quản lý private key SSH cho shell tiêu chuẩn.

### 3.1. Luồng kết nối

~~~mermaid
sequenceDiagram
    participant User as Người quản trị
    participant IAM as IAM / AWS Systems Manager
    participant Agent as SSM Agent trên EC2
    participant OS as Shell của hệ điều hành
    User->>IAM: StartSession(target = instance ID)
    IAM-->>User: Kiểm tra quyền và thông tin phiên
    Agent->>IAM: Kênh TLS outbound tới dịch vụ SSM
    IAM-->>Agent: Khởi tạo phiên hợp lệ
    Agent->>OS: Tạo shell theo cấu hình Run As
    User<->>OS: Truyền lệnh/đầu ra qua kênh Session Manager
~~~

*Sơ đồ khái quát luồng điều khiển và dữ liệu. Các kết nối thực tế dùng endpoint/kênh dịch vụ liên quan; không phải lưu lượng được gửi trực tiếp từ máy quản trị tới private IP của instance.*

### 3.2. Điều kiện tiên quyết trên EC2

| Điều kiện | Nội dung cần kiểm tra | Vì sao cần |
| --- | --- | --- |
| **SSM Agent** | Được cài đặt, phiên bản hỗ trợ và đang hoạt động | Agent tạo kết nối tới Systems Manager và khởi tạo session |
| **IAM instance profile** | Có quyền SSM cho EC2, thường bắt đầu bằng AWS managed policy `AmazonSSMManagedInstanceCore` | Instance cần quyền giao tiếp với dịch vụ |
| **Kết nối mạng** | Instance gửi HTTPS/TLS outbound 443 tới endpoint SSM cần thiết, qua Internet/NAT hoặc PrivateLink | Agent phải kết nối được với AWS Systems Manager |
| **DNS** | Phân giải được tên endpoint; nếu dùng interface VPC endpoint, thiết lập private DNS/VPC DNS phù hợp | Agent tìm đúng địa chỉ dịch vụ |
| **IAM của người quản trị** | Có quyền bắt đầu phiên với đúng managed node và tài liệu phiên | Không phải ai xem thấy EC2 cũng được mở shell |
| **Client** | AWS Console hoặc AWS CLI cùng Session Manager plugin khi sử dụng CLI cục bộ | Hiển thị và truyền dữ liệu phiên |

**Chú ý phân quyền hai phía:** `AmazonSSMManagedInstanceCore` là quyền của **instance profile** trên máy chủ, không phải quyền bạn gắn cho người quản trị để họ được vào mọi EC2. Ngược lại, một IAM user có `ssm:StartSession` vẫn không thể vào instance chưa online trong Systems Manager.

### 3.3. SSM Agent và vai trò của managed node

Nhiều AMI do AWS cung cấp có sẵn SSM Agent, nhưng không nên giả định mọi AMI tự tạo, Linux image cũ hay Windows image tùy chỉnh đều có agent chạy đúng. Cần kiểm tra trạng thái trong **AWS Systems Manager → Fleet Manager / Managed nodes** hoặc lệnh describe phù hợp.

Trên một số hệ Linux dùng `systemd`:

~~~bash
# Chạy trên chính EC2 hoặc trong môi trường đã có quyền truy cập
sudo systemctl status amazon-ssm-agent
~~~

Với bản cài sử dụng Snap (ví dụ một số Ubuntu), tên service có thể khác như `snap.amazon-ssm-agent.amazon-ssm-agent.service`. Hãy kiểm tra tài liệu của AMI thay vì coi một lệnh systemctl là đúng cho mọi hệ điều hành. Nếu chưa thể truy cập máy, dùng thông tin Systems Manager/EC2 console, boot logs, EC2 serial console (nếu đáp ứng điều kiện) hoặc cơ chế khôi phục được chuẩn bị trước.

### 3.4. Dùng Session Manager không cần public IP

Ở private subnet, có hai hướng kết nối outbound chính:

1. **NAT Gateway / egress Internet:** instance dùng private IP, route mặc định đi tới NAT ở public subnet. Security Group và NACL cho phép luồng HTTPS outbound và phản hồi; không cần inbound 22.
2. **Interface VPC endpoints (AWS PrivateLink):** tạo những endpoint SSM cần thiết trong VPC, bật private DNS, cấu hình Security Group cho endpoint nhận TCP 443 từ các instance được quản lý. Instance giao tiếp với địa chỉ IP riêng của endpoint mà không cần NAT cho luồng SSM tương ứng.

Các endpoint cần tìm hiểu:

~~~text
com.amazonaws.<region>.ssm
com.amazonaws.<region>.ssmmessages
com.amazonaws.<region>.ec2messages  (chỉ khi phiên bản Agent/Region và luồng vận hành cần)
~~~

`ssmmessages` là dịch vụ tạo kênh truyền phiên quan trọng của Session Manager. `ec2messages` liên quan tới những luồng SSM Agent/Region cũ và không còn được hỗ trợ ở một số Region mới; **không tự động tạo hoặc yêu cầu endpoint này trên mọi Region**. Các chức năng như ghi CloudWatch Logs, S3, KMS, cập nhật Agent hoặc truy xuất gói cài đặt có thể cần endpoint/đường mạng và quyền bổ sung riêng.

Ví dụ với một private EC2 có SG `sg-ec2` và interface endpoints:

- SG của EC2: cho phép outbound TCP **443** đến endpoint theo chính sách mạng.
- SG của interface endpoint: cho phép inbound TCP **443** từ SG `sg-ec2`.
- VPC có DNS resolution/hostnames phù hợp và endpoint dùng private DNS khi cần.
- Route table phải cho phép đường nội bộ đến subnet của ENI endpoint; NACL nếu tùy chỉnh phải mở request/response hai chiều.
- EC2 instance profile có quyền SSM phù hợp; mọi endpoint policy không được chặn các thao tác cần thiết.

Nếu endpoint được đặt ở nhiều AZ, hệ thống có thể giảm phụ thuộc vào một vị trí cho kết nối tới dịch vụ; thiết kế thực tế vẫn cần đối chiếu DNS, quota, subnet endpoint và điều kiện AZ của dịch vụ.

## 4. Thực hành mở Session Manager

Giả sử instance Linux dùng ID minh họa `i-0123456789abcdef0` ở Region `ap-southeast-1`. Người học cần có quyền AWS hợp lệ; chỉ thực hành trên tài nguyên được phép quản trị.

### 4.1. Cách 1: AWS Management Console

1. Mở **EC2 console → Instances**, chọn đúng Region và EC2.
2. Chọn instance, nhấn **Connect**.
3. Chọn tab **Session Manager**.
4. Nếu instance online và đủ quyền, chọn **Connect** để mở shell trong trình duyệt.
5. Kiểm tra user đang chạy, thư mục hiện tại và phiên truy cập; đóng phiên khi hoàn tất.

Có thể mở từ **Systems Manager → Session Manager → Start session** hoặc trải nghiệm Fleet Manager. Giao diện cụ thể có thể thay đổi theo phiên bản console.

### 4.2. Cách 2: AWS CLI

Trên máy quản trị cần **AWS CLI**, credentials đã cấu hình đúng Region/account và **Session Manager plugin** (đối với CLI bắt đầu phiên tương tác). Kiểm tra danh tính trước khi truy cập:

~~~bash
aws sts get-caller-identity
aws --version
session-manager-plugin
~~~

Tùy phiên bản plugin, chạy `session-manager-plugin` không tham số có thể hiển thị thông tin cách dùng hoặc lỗi thiếu đối số; mục tiêu là xác minh chương trình có thể được gọi. Nếu shell báo không tìm thấy, hãy cài plugin theo hướng dẫn AWS tương ứng với hệ điều hành.

Kiểm tra EC2 có xuất hiện là managed node:

~~~bash
aws ssm describe-instance-information \
  --region ap-southeast-1 \
  --filters Key=InstanceIds,Values=i-0123456789abcdef0 \
  --query "InstanceInformationList[].{Id:InstanceId,Status:PingStatus,Agent:AgentVersion,Platform:PlatformType}" \
  --output table
~~~

Sau đó mở phiên:

~~~bash
aws ssm start-session \
  --region ap-southeast-1 \
  --target i-0123456789abcdef0
~~~

Bạn sẽ thấy một shell tương tác khi các điều kiện đã được đáp ứng. Dùng `exit` trong shell để kết thúc. Ngoài ra, có thể quản lý session qua Systems Manager và các quyền `ssm:TerminateSession` hoặc `ssm:ResumeSession` theo chính sách cụ thể.

**Lưu ý:** lệnh `describe-instance-information` liệt kê managed node và trạng thái quan sát gần nhất, không phải phép thử bảo đảm mọi bước `StartSession` sẽ thành công. Một instance hiển thị “Online” nhưng người dùng có thể thiếu IAM permission hoặc session document không được cho phép.

### 4.3. Tài khoản OS của Session Manager

Với Linux, Session Manager có thể dùng tài khoản `ssm-user` theo thiết lập mặc định hoặc tài khoản khác qua **Run As**. Ở nhiều cấu hình Linux, `ssm-user` có quyền sudo đáng kể. Vì vậy:

- Xem quyền `ssm:StartSession` như quyền truy cập quản trị thực sự, không phải quyền xem log vô hại.
- Đặt chính sách Run As, sudoers và quyền file phù hợp với mục đích công việc.
- Tách vai trò vận hành chỉ đọc, vai trò khắc phục sự cố và quyền nâng cao; không tùy tiện cấp shell production cho mọi thành viên.
- Với Windows, OS account và shell có hành vi riêng; không bê nguyên lệnh Linux vào phiên Windows.

### 4.4. Ví dụ IAM cho người bắt đầu phiên

Ví dụ **identity-based policy minh họa** chỉ cho phép bắt đầu phiên mặc định với **một EC2 cụ thể** và session document mặc định được tạo trong tài khoản/Region:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "StartSessionOnSelectedInstance",
      "Effect": "Allow",
      "Action": "ssm:StartSession",
      "Resource": [
        "arn:aws:ec2:ap-southeast-1:123456789012:instance/i-0123456789abcdef0",
        "arn:aws:ssm:ap-southeast-1:123456789012:document/SSM-SessionManagerRunShell"
      ]
    }
  ]
}
~~~

Đây là **một phần** của bộ quyền cho người vận hành. Với cách truy cập thực tế, bạn còn có thể cần quyền xem EC2/SSM và quyền trên session (ví dụ `ssm:ResumeSession`, `ssm:TerminateSession`, `ssmmessages:OpenDataChannel` theo tài liệu và phương thức client). Hãy dùng [mẫu IAM chính thức của Session Manager](https://docs.aws.amazon.com/systems-manager/latest/userguide/getting-started-restrict-access-quickstart.html) để ghép các statement thích hợp, hạn chế quyền kết thúc/tiếp tục phiên vào **phiên do chính danh tính đó tạo**.

Không cấp `ssm:StartSession` với `Resource="*"` cho mọi người dùng chỉ vì muốn xử lý lỗi truy cập. Trong môi trường production, nên dùng IAM Identity Center/federation, quyền theo nhóm hoặc tag đã kiểm soát, session duration, MFA khi cần và nhật ký phù hợp.

## 5. Quản trị qua Session Manager: logging, port forwarding và giới hạn

### 5.1. Nhật ký phiên và kiểm toán

Với **phiên shell Session Manager tiêu chuẩn**, có thể cấu hình session preferences để lưu output vào **Amazon CloudWatch Logs** hoặc **Amazon S3**; cũng có thể cấu hình mã hóa liên quan bằng KMS. IAM và đường mạng của instance/phần ghi log phải đáp ứng yêu cầu.

**AWS CloudTrail** có thể ghi các sự kiện API như `StartSession`, `TerminateSession`, tạo/sửa cấu hình IAM liên quan; CloudTrail **không tự ghi nội dung lệnh shell**. Để đáp ứng yêu cầu kiểm toán, phân biệt ba lớp:

| Lớp | Thông tin | Cần cấu hình |
| --- | --- | --- |
| **CloudTrail** | Ai gọi API bắt đầu/kết thúc session, thời điểm, ngữ cảnh API | Trail/Event data store và chính sách lưu trữ phù hợp |
| **Session Manager logs** | Nội dung đầu ra shell tiêu chuẩn, khi loại session và cấu hình hỗ trợ | Session preferences tới CloudWatch Logs/S3, quyền và endpoint |
| **OS/application logs** | Lệnh, thay đổi file, sudo, ứng dụng theo cơ chế ghi log tại máy | Cấu hình auditd/journald/syslog/agent và quy trình bảo vệ log |

**Rất quan trọng:** Session Manager **không cung cấp ghi nội dung phiên** cho những kết nối chạy **SSH qua Session Manager** hoặc **port forwarding session**. Với các luồng này, bạn cần cách kiểm toán tại hệ điều hành/ứng dụng và lớp mạng khác. Không khẳng định “dùng SSM thì mọi lệnh đều được lưu” nếu chưa kiểm chứng loại session.

### 5.2. Port forwarding qua Session Manager

Ngoài shell, Session Manager có thể tạo tunnel TCP qua managed node. Ví dụ, từ máy quản trị cần truy cập cơ sở dữ liệu nội bộ `db.internal.example:5432` mà không public DB:

~~~bash
aws ssm start-session \
  --region ap-southeast-1 \
  --target i-0123456789abcdef0 \
  --document-name AWS-StartPortForwardingSessionToRemoteHost \
  --parameters '{"host":["db.internal.example"],"portNumber":["5432"],"localPortNumber":["15432"]}'
~~~

Sau khi tunnel được thiết lập, client PostgreSQL có thể kết nối tới `localhost:15432` trên máy quản trị. Managed node phải **phân giải tên DB và được Security Group/NACL/route cho phép truy cập cổng 5432**. Endpoint DB vẫn yêu cầu xác thực database đúng cách; tunnel không tự cấp quyền cơ sở dữ liệu.

Đây là ví dụ để giải thích khả năng. Trong môi trường thật, giới hạn quyền dùng session document port forwarding, thời hạn phiên, máy trung gian và người được phép truy cập dữ liệu nhạy cảm.

### 5.3. Những trường hợp Session Manager phù hợp

- EC2 trong **private subnet** cần quản trị mà không mở inbound SSH.
- Hệ thống muốn kiểm soát quyền truy cập thông qua IAM và IAM Identity Center.
- Đội vận hành cần shell, theo dõi thời điểm tạo session và có thể lưu nội dung shell tiêu chuẩn.
- Máy chủ Windows hoặc Linux có SSM Agent phù hợp, không yêu cầu workflow SSH thuần túy.
- Môi trường muốn giảm việc phát hành, luân chuyển và lưu trữ SSH private keys.

Session Manager vẫn có điểm phụ thuộc: Agent, IAM instance profile, kết nối tới AWS Systems Manager và dịch vụ AWS liên quan. Nếu tất cả đều lỗi, truy cập qua Session Manager có thể không khả dụng; nên có phương án khôi phục được kiểm soát.

## 6. EC2 Instance Connect: SSH với public key tạm thời

**EC2 Instance Connect (EIC)** kết hợp **IAM** với cơ chế **SSH** truyền thống trên EC2 Linux. Khi người dùng được phép gọi API `SendSSHPublicKey`, AWS đặt **public key** vào instance metadata trong một khoảng ngắn (**60 giây**). Gói hỗ trợ EIC trên hệ điều hành tích hợp với SSH để kiểm tra public key này.

Điểm cần hiểu:

- **IAM kiểm tra quyền gửi public key** tới đúng instance.
- **SSH vẫn xác thực người dùng hệ điều hành** và tạo kết nối đến `sshd`. EIC không biến shell Linux thành API IAM.
- Khóa tạm thời có thời gian để **bắt đầu xác thực SSH**, không phải giới hạn phiên SSH còn tối đa 60 giây. Kết nối đã thiết lập có thể tiếp tục cho tới khi bị đóng theo cấu hình và chính sách vận hành.
- Phải có kết nối TCP đến port SSH; gửi public key thành công **không đồng nghĩa cổng 22 đang thông**.

### 6.1. Điều kiện tiên quyết với SSH public IP

| Điều kiện | Cách kiểm tra |
| --- | --- |
| Instance chạy **Linux** với SSH server | AMI hỗ trợ EIC và `sshd` chạy; kiểm tra hướng dẫn đúng hệ Linux |
| Gói/tích hợp **EC2 Instance Connect** | AMI có sẵn hoặc được cài và cấu hình tương thích; không tự giả định mọi custom AMI đều có |
| **OS username** đúng | `ec2-user` (nhiều Amazon Linux), `ubuntu` (nhiều Ubuntu AMI), hoặc username thật của AMI |
| IAM của người gọi | `ec2-instance-connect:SendSSHPublicKey` trên instance; quyền xem EC2 khi sử dụng Console |
| Đường mạng tới instance | Public IPv4/IPv6 được hỗ trợ, VPC route và Internet Gateway khi cần |
| Security Group và NACL | Inbound TCP 22 từ đúng nguồn; NACL cho phép request và traffic trả về |
| SSH key | Có cặp khóa phù hợp nếu dùng SSH client riêng; private key nằm trên máy quản trị |

**Không mở SSH `0.0.0.0/0` cho production chỉ để nhanh kết nối.** Nếu dùng direct SSH, thu hẹp nguồn quản trị theo IP/VPN hoặc dùng EIC Endpoint để tránh public SSH.

### 6.2. Cách 1: dùng EC2 Console

1. Mở **EC2 → Instances**, chọn Linux instance.
2. Chọn **Connect → EC2 Instance Connect**.
3. Chọn **Connect using a Public IP** khi instance có địa chỉ công khai phù hợp.
4. Xác minh **Username** đúng với AMI.
5. Chọn **Connect**, EC2 console sẽ hỗ trợ cấp khóa tạm thời và kết nối SSH trong trình duyệt.

Nếu máy chỉ có private IPv4, cần chọn đường qua **EC2 Instance Connect Endpoint** hoặc phương thức truy cập khác được hỗ trợ. Tab hoặc tùy chọn Console có thể thay đổi khi AWS cập nhật giao diện.

### 6.3. Cách 2: gửi public key bằng AWS CLI rồi SSH

Ví dụ dưới đây áp dụng cho Linux/macOS có OpenSSH; có thể làm tương đương trên Windows với OpenSSH và cú pháp đường dẫn phù hợp.

**Bước 1 — Tạo cặp khóa cục bộ cho bài thực hành:**

~~~bash
ssh-keygen -t ed25519 -f ./ec2-lab-key -C ec2-lab
~~~

Tập tin `ec2-lab-key` chứa **private key**, giữ bí mật, đặt quyền file phù hợp; `ec2-lab-key.pub` chứa **public key**. Không đẩy private key lên Git, paste vào ticket hoặc đưa lên server.

**Bước 2 — Gửi public key lên instance metadata:**

~~~bash
aws ec2-instance-connect send-ssh-public-key \
  --region ap-southeast-1 \
  --instance-id i-0123456789abcdef0 \
  --instance-os-user ec2-user \
  --ssh-public-key file://./ec2-lab-key.pub
~~~

API trả kết quả thành công khi AWS nhận yêu cầu phù hợp; cần **khởi tạo SSH sớm sau bước này** vì public key chỉ tồn tại trong khoảng ngắn. Một số trường hợp sẽ cần truyền thêm Availability Zone theo API/phiên bản CLI; kiểm tra cú pháp của AWS CLI đang sử dụng.

**Bước 3 — Kết nối tới địa chỉ công khai được phép:**

~~~bash
ssh -i ./ec2-lab-key ec2-user@PUBLIC_IPV4_OF_INSTANCE
~~~

`PUBLIC_IPV4_OF_INSTANCE` là placeholder, thay bằng địa chỉ thật. SSH vẫn sẽ kiểm tra **host key** của máy chủ; trước khi chấp nhận dấu vân tay mới, nên đối chiếu với thông tin host được phát hành qua kênh đáng tin cậy.

Nếu báo `Permission denied (publickey)`, cần phân biệt IAM từ chối gửi khóa, gửi khóa thành công nhưng quá 60 giây, sai OS user, SSHD/EIC package không hỗ trợ hoặc private key không khớp public key đã gửi.

### 6.4. CLI hỗ trợ kết nối trực tiếp

Với **AWS CLI v2** và môi trường OpenSSH phù hợp, có thể dùng lệnh EIC quản lý quy trình kết nối:

~~~bash
aws ec2-instance-connect ssh \
  --region ap-southeast-1 \
  --instance-id i-0123456789abcdef0 \
  --os-user ec2-user
~~~

CLI có thể lựa chọn loại kết nối tự động nếu môi trường hỗ trợ; khi cần xác định chắc chắn đường private qua EIC Endpoint, truyền `--connection-type eice`. Không dùng kết quả lựa chọn tự động như bằng chứng rằng instance không có public exposure; vẫn cần kiểm tra route và Security Group.

## 7. EC2 Instance Connect Endpoint: SSH đến private EC2

**EC2 Instance Connect Endpoint (EICE)** là dịch vụ proxy/tunnel TCP nhận kết nối được IAM cho phép từ máy quản trị, tạo đường truy cập đến EC2 trong VPC qua **private IP**. Người quản trị không cần VPN, bastion host hoặc public IP chỉ để mở đường SSH trong những tình huống được hỗ trợ.

EICE có một **network interface** trong subnet do bạn chỉ định. Đường tunnel qua EICE là kết nối TCP được IAM kiểm soát; **bản thân EICE không đăng nhập Linux thay cho SSH**. Để vào được shell:

1. IAM phải cho phép mở đường hầm EICE bằng `ec2-instance-connect:OpenTunnel` và các quyền điều kiện liên quan.
2. EICE phải nối được tới private IP/port của EC2 theo route, Security Group, NACL và tính năng IP address của endpoint.
3. Máy đích cần SSH server và cách xác thực SSH hợp lệ: **public key tạm thời qua EIC** hoặc **khóa SSH đã được cấu hình** trên máy.

### 7.1. Cấu hình mạng mẫu

~~~mermaid
flowchart LR
    ADMIN["Laptop quản trị / IAM role"] -->|"OpenTunnel qua AWS service"| EICE["EIC Endpoint ENI<br/>trong subnet VPC"]
    EICE -->|"TCP 22 - private IP"| EC2["EC2 Linux<br/>10.50.10.25"]
    EC2 -.->|"Có thể dùng EIC key tạm thời"| EIC["EC2 Instance Connect API"]
~~~

*Chỉ là luồng logic. Cần kiểm tra hỗ trợ endpoint, quota, subnet, IP type và route của VPC thực tế. Không xem luồng SSH này là Session Manager.*

Ví dụ:

- EC2 ở private subnet `10.50.10.0/24`, không có public IP.
- EIC Endpoint được tạo trong một subnet phù hợp thuộc VPC, có Security Group riêng.
- SG của endpoint cho phép **egress TCP 22** đến EC2.
- SG của EC2 cho phép **inbound TCP 22** từ SG của endpoint hoặc nguồn phù hợp với cấu hình preserve-client-IP.
- NACL nếu tùy chỉnh phải hỗ trợ cả hai chiều request/response, bao gồm port ephemeral. Đường route trong VPC cần hợp lệ.
- IAM người vận hành được giới hạn ở endpoint và instance cần truy cập; không cấp quyền tạo/sửa endpoint cho toàn bộ tài khoản nếu chỉ cần SSH.

**Source IP preservation:** khi EIC Endpoint bật tính năng giữ IP nguồn của client, IP được nhìn thấy ở máy đích và yêu cầu Security Group có thể khác so với chế độ không giữ. Không áp dụng máy móc quy tắc “cho EC2 inbound từ SG endpoint” cho mọi cấu hình; phải kiểm tra chế độ endpoint, loại IP và hướng dẫn AWS.

### 7.2. Truy cập EICE bằng AWS CLI

Để SSH từ AWS CLI v2 qua EICE và sử dụng hỗ trợ EIC trên AMI:

~~~bash
aws ec2-instance-connect ssh \
  --region ap-southeast-1 \
  --instance-id i-0123456789abcdef0 \
  --os-user ec2-user \
  --connection-type eice
~~~

Đây là cách thuận tiện khi instance không có public IP. Nếu có nhiều endpoint khả dụng/kiểu IP khác nhau hoặc yêu cầu riêng, cần cung cấp tham số endpoint/instance IP phù hợp theo tài liệu CLI.

### 7.3. Tạo tunnel rồi dùng OpenSSH riêng

EICE cũng cho phép mở tunnel TCP và dùng SSH client với khóa đã có sẵn. Ví dụ **terminal thứ nhất**:

~~~bash
aws ec2-instance-connect open-tunnel \
  --region ap-southeast-1 \
  --instance-id i-0123456789abcdef0 \
  --local-port 8888
~~~

Khi dòng trạng thái báo đang lắng nghe ở port cục bộ, từ **terminal thứ hai**:

~~~bash
ssh -i ./existing-ssh-key -p 8888 ec2-user@localhost
~~~

Ở ví dụ này `existing-ssh-key` là private key mà public key tương ứng **đã được hệ điều hành đích chấp nhận**. Nếu muốn dùng khóa tạm qua EIC API, phải có bước gửi public key phù hợp. Tunnel tự nó không thêm public key vào `authorized_keys`.

Ngoài SSH, EICE có thể chuyển một số kết nối TCP khác khi tính năng hỗ trợ, ví dụ truy cập RDP đến Windows thông qua tunnel riêng. Nhưng **EIC public-key login** như trình bày ở mục 6 là cơ chế **SSH cho Linux**, không nên áp dụng nguyên văn cho Windows.

### 7.4. Giới hạn và điểm đánh đổi

- EICE phụ thuộc vào dịch vụ AWS và quyền IAM để thiết lập tunnel; kết nối hiện có vẫn có giới hạn thời gian.
- Quota về số endpoint, kết nối đồng thời và thời lượng tối đa có thể ảnh hưởng tới vận hành, nên kiểm tra quota chính thức ở Region/tài khoản mục tiêu.
- EICE không có chi phí dịch vụ bổ sung theo chính sách AWS được công bố tại thời điểm biên soạn, nhưng **data transfer liên AZ** và tài nguyên mạng khác có thể phát sinh phí; luôn kiểm tra bảng giá hiện hành.
- Nếu endpoint nằm ở AZ mất khả dụng, một đường SSH từ xa có thể bị gián đoạn dù EC2 ở AZ khác còn chạy. Thiết kế phương án quản trị sự cố cần xem miền lỗi của chính endpoint.

## 8. IAM: tách quyền gửi khóa, mở tunnel và quản lý EC2

### 8.1. Mẫu quyền EIC public key

Identity-based policy sau minh họa việc chỉ được gửi khóa SSH đến **một EC2 Linux**, cho user hệ điều hành `ec2-user`:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "SendKeyToSelectedLinuxInstance",
      "Effect": "Allow",
      "Action": "ec2-instance-connect:SendSSHPublicKey",
      "Resource": "arn:aws:ec2:ap-southeast-1:123456789012:instance/i-0123456789abcdef0",
      "Condition": {
        "StringEquals": {
          "ec2:osuser": "ec2-user"
        }
      }
    },
    {
      "Sid": "ViewEC2ForConnection",
      "Effect": "Allow",
      "Action": "ec2:DescribeInstances",
      "Resource": "*"
    }
  ]
}
~~~

Chú ý:

- `ec2:DescribeInstances` thường yêu cầu `Resource="*"` vì cách dịch vụ hỗ trợ resource-level permissions.
- `ec2:osuser` chỉ giới hạn tên user khi gọi API EIC; không thay cho cấu hình sudo, tệp và quyền Linux.
- Policy này **chưa cấp** quyền `OpenTunnel` qua EICE; máy không có public IP vẫn cần đường mạng thích hợp.
- IAM Allow chỉ cho phép thao tác AWS API theo phạm vi đã nêu, vẫn chịu SCP, permissions boundary, explicit Deny và các policy liên quan.

### 8.2. Quyền EIC Endpoint

Để sử dụng EICE, người dùng cần `ec2-instance-connect:OpenTunnel` trên endpoint thích hợp; có thể giới hạn theo endpoint ARN và condition keys của dịch vụ như đích, port từ xa hoặc thời lượng tunnel khi được hỗ trợ. Quyền `SendSSHPublicKey` là một thao tác riêng nếu dùng khóa SSH tạm thời.

Với production, tách:

| Vai trò | Quyền AWS cần xem xét | Lý do |
| --- | --- | --- |
| **Người vận hành Session Manager** | `ssm:StartSession` theo instance/document; quyền quản lý session của chính mình | Đăng nhập qua SSM có kiểm soát |
| **Người vận hành EIC** | `ec2-instance-connect:SendSSHPublicKey` trên instance/OS user được chỉ định | Đưa khóa tạm để SSH |
| **Người vận hành EICE** | `ec2-instance-connect:OpenTunnel` trên endpoint được phép | Mở đường TCP riêng đến instance |
| **Quản trị mạng** | Quyền tạo/sửa EICE, subnet, route, SG | Thay đổi hạ tầng kết nối, rủi ro lớn hơn quyền sử dụng |
| **Quản trị quyền** | IAM role/policy và các giới hạn liên quan | Có thể thay đổi ai được truy cập tài nguyên |

Quyền tạo endpoint, quyền mở tunnel và quyền đăng nhập SSH là **những bước kiểm soát khác nhau**. Nếu một nhóm có thể tự thay IAM policy hoặc Security Group, giới hạn dành cho nhóm đó có thể bị vô hiệu hóa; phải bảo vệ cả quyền **sửa hệ thống cấp quyền**.

## 9. Chọn phương thức nào cho tình huống nào?

| Tình huống | Lựa chọn nên đánh giá trước | Lý do |
| --- | --- | --- |
| Quản trị EC2 Linux trong private subnet, muốn không mở inbound 22 | **Session Manager** | Chỉ cần SSM Agent và đường outbound tới SSM; truy cập qua IAM |
| Quản trị Windows EC2 cần shell và tích hợp IAM | **Session Manager** nếu điều kiện Agent phù hợp | Không phụ thuộc OpenSSH/Linux user |
| EC2 Linux public, có SSH và gói EIC | **EC2 Instance Connect** | Tận dụng SSH, khóa public tạm và quyền IAM |
| EC2 Linux private, nhóm vẫn cần workflow OpenSSH | **EC2 Instance Connect Endpoint** | Tunnel TCP qua private IP, không phải mở SSH Internet |
| Cần truyền một kết nối TCP nội bộ phục vụ điều tra | Session Manager **port forwarding** hoặc EICE tunnel theo quyền | Kiểm tra giao thức, đường mạng và kiểm toán phiên |
| Muốn lưu nội dung phiên shell cho kiểm toán | **Session Manager shell tiêu chuẩn** với logging được bật | Có thể xuất log ra S3/CloudWatch Logs; kiểm tra giới hạn loại session |
| AMI đặc thù không có SSM Agent nhưng có SSH được cấu hình | EIC/EICE nếu AMI hỗ trợ hoặc SSH qua EICE với khóa hiện có | Không phải phụ thuộc SSM Agent |
| Đang xử lý sự cố SSM Agent không online | Đường quản trị dự phòng được phê duyệt: EICE/SSH, EC2 Serial Console nếu hỗ trợ, kỹ thuật cứu hộ | Kênh SSM có thể không dùng được khi Agent/SSM networking lỗi |

**Gợi ý thiết kế:** với ứng dụng AWS thông thường, cân nhắc **Session Manager** là đường quản trị chính vì có thể giảm nhu cầu inbound SSH và quản lý khóa. Dùng **EICE** khi team bắt buộc làm việc qua SSH hay cần kênh thay thế được phân quyền. Cả hai vẫn cần kiểm soát OS user, IAM và khả năng khôi phục.

## 10. Tình huống thực tế: EC2 API nằm trong private subnet

Giả sử hệ thống bán hàng dùng ALB public và EC2 ứng dụng ở hai private subnet thuộc hai AZ:

~~~text
VPC 10.60.0.0/16
├── AZ A
│   ├── public-a          : ALB, NAT Gateway A (nếu cần)
│   └── app-private-a     : EC2 app A, không public IP
└── AZ B
    ├── public-b          : ALB, NAT Gateway B (nếu cần)
    └── app-private-b     : EC2 app B, không public IP

SSM interface VPC endpoints: ssm, ssmmessages (và endpoint bổ sung nếu cần)
EIC Endpoint: lựa chọn bổ sung nếu muốn SSH đến private instance
~~~

### 10.1. Phương án A — quản trị bằng Session Manager

1. Mỗi EC2 app có instance profile đủ quyền SSM.
2. SSM Agent được cài, chạy và hiển thị online.
3. Private subnet có NAT/egress hoặc interface endpoints hỗ trợ kết nối HTTPS 443 từ instance.
4. IAM vận hành được cấp `ssm:StartSession` với instance và document phù hợp.
5. Security Group của EC2 chỉ mở inbound **từ ALB đến cổng ứng dụng**; không cần inbound 22.
6. Ghi CloudTrail, cấu hình session logs cho shell chuẩn nếu bắt buộc; thiết lập log retention và phân quyền đọc logs.

Khi AZ A lỗi, app tại B có thể tiếp tục phục vụ nếu đã đủ capacity và các phụ thuộc sẵn sàng. Muốn vẫn quản trị được app B, phải đảm bảo đường của app B tới SSM **không phụ thuộc hoàn toàn vào NAT/endpoint đặt ở AZ A**. Nếu NAT Gateway zonal dùng chung tại AZ A, lỗi AZ A có thể cắt đường SSM outbound của app B; lựa chọn NAT theo AZ hoặc VPC endpoints nhiều AZ được cấu hình phù hợp giúp giảm rủi ro này.

### 10.2. Phương án B — SSH qua EIC Endpoint

1. Tạo EIC Endpoint trong VPC, đặt ở subnet phù hợp với IP type và đường route.
2. IAM cho phép mở tunnel tại endpoint đó; nếu dùng public key tạm, IAM thêm quyền SendSSHPublicKey trên EC2.
3. EC2 có SSH server; nếu dùng khóa EIC tạm, AMI phải có gói/tích hợp EIC.
4. SG của instance cho phép TCP 22 từ nguồn thực tế của tunnel; SG endpoint cho phép egress; NACL hỗ trợ traffic hai chiều.
5. Người vận hành dùng `aws ec2-instance-connect ssh --connection-type eice`.
6. Theo dõi CloudTrail và hệ thống audit OS, vì không có bản ghi nội dung shell kiểu Session Manager chuẩn mặc định.

Một endpoint đặt ở một AZ có thể là phụ thuộc vận hành. Khi thiết kế HA, hãy ghi rõ cách hỗ trợ người vận hành nếu endpoint gặp lỗi hoặc phải thay thế, thay vì coi việc endpoint kết nối được là bảo đảm availability của ứng dụng.

## 11. Bảo mật khi mở quyền truy cập production

**Quản trị server là hành động đặc quyền**. Dù truyền qua Session Manager hay SSH, người đã vào shell vẫn có thể đọc file, biến môi trường hoặc gọi API AWS với **instance role** trong phạm vi quyền của EC2.

Các kiểm soát quan trọng:

1. **Định danh cá nhân:** ưu tiên đăng nhập liên kết/IAM Identity Center và role theo nhóm thay vì dùng access key cố định chia sẻ.
2. **Least privilege:** scope `StartSession`, `SendSSHPublicKey`, `OpenTunnel` theo instance, endpoint, tài khoản, Region, tag và OS user khi điều kiện được hỗ trợ.
3. **Quản lý OS privilege:** cấu hình sudo/Run As/nhóm Linux hợp lý; session được IAM cho phép không tự là shell chỉ đọc.
4. **Không công khai SSH nếu không cần:** EC2 private IP, SG inbound 22 bị đóng khi dùng Session Manager; hoặc chỉ mở từ nguồn EICE phù hợp.
5. **Không lưu private key bừa bãi:** nếu còn dùng SSH, khóa phải được bảo vệ, luân chuyển khi cần và không commit vào repository.
6. **Audit phù hợp:** CloudTrail cho API, log shell Session Manager nếu hỗ trợ, audit trên OS cho SSH/port-forwarding.
7. **Giới hạn truy cập khi khẩn cấp:** role break-glass có phê duyệt, thời hạn ngắn và theo dõi; diễn tập để không bị mất đường quản trị khi Agent/SSM không hoạt động.
8. **Mã hóa và dữ liệu:** TLS, mã hóa bản ghi logs, phân quyền đọc log, tránh copy secret/database dump từ production vào máy cá nhân.
9. **Giám sát thay đổi quyền:** cảnh báo khi sửa IAM policy, security group SSH, tạo EICE hoặc khi có phiên bất thường.
10. **Cập nhật phần mềm:** vá SSM Agent, SSH server và AMI theo quy trình, kiểm tra tương thích trước rollout.

**Một ví dụ vi phạm least privilege:** người dùng chỉ cần xem log nhưng được quyền `ssm:StartSession` vào EC2 và session cho phép `sudo su`. Trên máy họ có thể đọc secret hoặc thay đổi tệp. Trong trường hợp đó, cấp quyền đọc CloudWatch Logs với phạm vi hẹp có thể phù hợp hơn shell.

## 12. Cách xử lý sự cố truy cập

### 12.1. Session Manager báo `TargetNotConnected` hoặc nút Connect không khả dụng

Kiểm tra theo thứ tự:

1. **Đúng account/Region/instance ID?** Instance phải chạy ở Region mà CLI/Console đang dùng.
2. **SSM Agent online?** Tìm managed node với `PingStatus=Online`. Nếu không, kiểm tra agent service, version và startup logs bằng đường truy cập dự phòng.
3. **Instance profile?** Có role được gắn dưới dạng EC2 instance profile và quyền SSM cần thiết không?
4. **Networking?** Agent gọi được endpoint `ssm`/`ssmmessages` qua NAT hoặc VPC interface endpoints không? DNS, endpoint SG TCP 443 và NACL có đúng không?
5. **Private endpoint policy?** Có giới hạn nhầm API của agent không?
6. **IAM của người dùng?** `StartSession`/session document có được Allow và không bị Deny/boundary/SCP chặn không?
7. **Session Manager plugin?** Máy local có plugin phù hợp khi dùng AWS CLI không?

Một lệnh chỉ đọc có thể giúp quan sát trạng thái kết nối:

~~~bash
aws ssm get-connection-status \
  --region ap-southeast-1 \
  --target i-0123456789abcdef0
~~~

Trạng thái chỉ cho biết khả năng kết nối được hệ thống ghi nhận tại thời điểm API trả lời; cần điều tra thêm nếu request phiên vẫn thất bại.

### 12.2. Session Manager báo `AccessDenied`

Phân biệt hai đối tượng:

- **Người vận hành:** có được `ssm:StartSession` vào instance và document? Quyền resume/terminate/ssmmessages khi dùng client có phù hợp không? Có explicit Deny ở IAM/SCP?
- **EC2 instance role:** có quyền SSM Agent để đăng ký/kết nối kênh liên lạc không? Đây là principal khác với người vận hành.

Không sửa lỗi bằng cách gắn `AdministratorAccess` hoặc mở toàn bộ `ssm:*`. Hãy xem CloudTrail/API error và bổ sung đúng action/resource.

### 12.3. EIC báo `SendSSHPublicKey AccessDenied`

- IAM người gọi có `ec2-instance-connect:SendSSHPublicKey` trên **ARN instance** không?
- `ec2:osuser` condition có khớp tên user được truyền không?
- Instance ID/Region/AZ và SCP/boundary có đúng không?
- Người gọi có quyền xem instance cần thiết với Console hay không?

### 12.4. SSH `Permission denied (publickey)`

API gửi khóa có thể đã thành công nhưng việc SSH thất bại vì:

- Mất quá **60 giây** trước khi bắt đầu xác thực với khóa tạm.
- Sai OS user (ví dụ dùng `ec2-user` cho AMI chỉ có `ubuntu`).
- Gói EIC hoặc tích hợp với `sshd` không hoạt động trên AMI.
- SSH client dùng private key khác với public key vừa gửi.
- Cấu hình `sshd`, quyền home directory hoặc cơ chế authorized keys không đúng.

Kiểm tra xác thực bằng verbose SSH (không chia sẻ bí mật từ output):

~~~bash
ssh -v -i ./ec2-lab-key ec2-user@PUBLIC_IPV4_OF_INSTANCE
~~~

### 12.5. SSH timeout hoặc `Connection refused`

| Hiện tượng | Nghi ngờ chính | Cách kiểm tra |
| --- | --- | --- |
| **Timeout** | Route, public IP, IGW, SG inbound 22, NACL, VPN hoặc đường EICE | Vẽ đường đi TCP và kiểm tra SG/NACL cả hai chiều |
| **Connection refused** | Đã đến máy/địa chỉ nhưng không có listener SSH ở port hoặc bị từ chối ở lớp khác | Kiểm tra `sshd`, port, firewall OS và instance health |
| **Host key changed** | IP/host đã đổi, instance được thay hoặc có rủi ro giả mạo | Xác minh host key qua kênh đáng tin trước khi chỉnh `known_hosts` |
| **EICE OpenTunnel denied** | Thiếu `ec2-instance-connect:OpenTunnel` hoặc condition endpoint/port | Xem IAM và CloudTrail cho OpenTunnel |
| **EICE tunnel mở nhưng SSH không vào** | Source IP/SG/port 22/SSH key/OS user sai | Kiểm tra mạng endpoint → instance và xác thực SSH riêng |

**Tránh thao tác nguy hiểm:** không tắt xác minh host key, không mở port 22 cho toàn Internet và không xóa Security Group/NACL chỉ để kiểm tra kết nối.

## 13. Quan sát bằng AWS CLI mà không thay đổi hệ thống

Các ví dụ sau chỉ đọc metadata trong Region `ap-southeast-1`; cần IAM permissions tương ứng. Tên tài nguyên và ID đều là placeholder.

### 13.1. Xem EC2 và địa chỉ

~~~bash
aws ec2 describe-instances \
  --region ap-southeast-1 \
  --instance-ids i-0123456789abcdef0 \
  --query "Reservations[].Instances[].{Id:InstanceId,State:State.Name,PrivateIP:PrivateIpAddress,PublicIP:PublicIpAddress,Subnet:SubnetId,Profile:IamInstanceProfile.Arn}" \
  --output table
~~~

Nếu không có public IP, **không đủ điều kiện** để dùng direct SSH qua public IPv4. Nhưng instance vẫn có thể truy cập qua Session Manager hoặc EICE nếu điều kiện từng phương thức được đáp ứng.

### 13.2. Xem tình trạng managed node

~~~bash
aws ssm describe-instance-information \
  --region ap-southeast-1 \
  --filters Key=InstanceIds,Values=i-0123456789abcdef0 \
  --query "InstanceInformationList[].{Id:InstanceId,Ping:PingStatus,Agent:AgentVersion,LastPing:LastPingDateTime}" \
  --output table
~~~

### 13.3. Xem EIC Endpoint trong VPC

~~~bash
aws ec2 describe-instance-connect-endpoints \
  --region ap-southeast-1 \
  --query "InstanceConnectEndpoints[].{Id:InstanceConnectEndpointId,State:State,Vpc:VpcId,Subnet:SubnetId}" \
  --output table
~~~

Nếu account/Region chưa có endpoint, kết quả có thể rỗng. Việc có endpoint không bảo đảm IAM và TCP 22 tới instance đã đúng.

### 13.4. Xem Session Manager sessions

~~~bash
aws ssm describe-sessions \
  --region ap-southeast-1 \
  --state Active \
  --query "Sessions[].{Id:SessionId,Target:Target,Owner:Owner,Start:StartDate}" \
  --output table
~~~

Danh sách session phụ thuộc quyền xem của principal. Session metadata là dữ liệu quản trị cần bảo vệ, đặc biệt khi dùng trong sản phẩm có thông tin người vận hành.

## 14. Bài thực hành và câu hỏi tự kiểm tra

### Bài tập 1 — chọn cách kết nối

Cho ba máy:

| Máy | Trạng thái | Mục tiêu |
| --- | --- | --- |
| **EC2 A** | Linux, private subnet, đã online trên Systems Manager | Kiểm tra log ứng dụng mà không mở SSH inbound |
| **EC2 B** | Linux, private subnet, không có SSM Agent, SSH đã cấu hình | Quản trị bằng OpenSSH từ laptop |
| **EC2 C** | Linux public, có EIC hỗ trợ, IAM người dùng chỉ cho phép gửi public key | SSH có thời hạn cấp khóa ngắn |

**Gợi ý:**

1. EC2 A: **Session Manager** nếu đủ quyền và mạng.
2. EC2 B: **EIC Endpoint + SSH key đã được máy chấp nhận** hoặc khôi phục cài Agent phù hợp; EICE tunnel không yêu cầu SSM Agent.
3. EC2 C: **EC2 Instance Connect qua public IP**, với SG/route được giới hạn và xác minh OS user.

### Bài tập 2 — tìm sai sót mạng

Private EC2 không có NAT, nhưng đã tạo hai interface endpoints `ssm` và `ssmmessages`. SG của endpoint chỉ cho phép inbound TCP 443 từ địa chỉ IP quản trị viên trên Internet. EC2 có SSM Agent và IAM role hợp lệ nhưng `PingStatus=ConnectionLost`.

**Hỏi:** rule SG của endpoint có vấn đề gì?

**Gợi ý:** nguồn gọi endpoint là **EC2 bên trong VPC**. SG endpoint phải cho inbound TCP 443 từ EC2 SG hoặc CIDR private thích hợp; SG inbound từ laptop Internet không giúp Agent kết nối tới endpoint. Cần kiểm tra thêm DNS, endpoint policy và NACL.

### Bài tập 3 — giải thích hai lỗi khác nhau

Người vận hành gọi `SendSSHPublicKey` thành công, nhưng SSH đến `10.50.10.25:22` từ Internet bị timeout. Sau đó tạo EICE và tunnel mở thành công, nhưng SSH nhận `Permission denied (publickey)`.

**Gợi ý đáp án:** kết nối trực tiếp tới private IPv4 không có đường Internet phù hợp nên timeout. EICE giải quyết **đường TCP**, còn lỗi `publickey` là lớp **xác thực SSH**; phải kiểm tra public key được cung cấp/đã hết hạn, OS user, private key và EIC package.

### Bài tập 4 — đọc policy và đánh giá rủi ro

Giả sử role `SupportReadOnly` được cấp:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "ssm:StartSession",
      "Resource": "*"
    }
  ]
}
~~~

**Hỏi:** tên role có phản ánh đúng khả năng được cấp? Rủi ro gì nếu instance chứa quyền truy cập database và file secret?

**Gợi ý:** tên “ReadOnly” không làm shell thành read-only. `Resource="*"` là phạm vi quá rộng nếu được kết hợp với các quyền/session documents liên quan; một phiên có thể chạy dưới OS user với quyền cao, đọc secret hoặc thay đổi dữ liệu. Nên giới hạn instance/document, quản lý Run As/sudo và dùng CloudWatch Logs đọc theo IAM khi nhu cầu chỉ là đọc log.

### Bài tập 5 — thiết kế đường quản trị dự phòng

Ứng dụng vận hành ở hai AZ, EC2 private trong cả hai AZ. Bình thường dùng Session Manager qua NAT Gateway duy nhất ở AZ A. Hãy phân tích điều gì xảy ra nếu AZ A mất, rồi đề xuất phương án giúp vận hành EC2 ở AZ B.

**Gợi ý:** EC2 B có thể vẫn chạy nhưng đường SSM outbound bị mất do NAT-A không hoạt động. Có thể dùng NAT theo AZ hoặc bố trí interface endpoints SSM cần thiết ở nhiều AZ với mạng/DNS/SG phù hợp. Cần kiểm thử phương án dự phòng khi một vùng bị cô lập.

## 15. Tổng kết

Ba khái niệm cần nhớ:

1. **Session Manager** truyền phiên qua **SSM Agent và dịch vụ Systems Manager**, thường không cần public IP hoặc inbound 22. Phải kiểm tra IAM cả người quản trị lẫn instance, kênh 443 và session preferences.
2. **EC2 Instance Connect** cấp **SSH public key tạm thời** qua API được IAM cho phép; sau đó vẫn phải có **SSH server, đúng OS user và đường TCP tới EC2**. Thời hạn 60 giây là thời hạn sử dụng public key để khởi tạo xác thực, không phải thời hạn của kết nối SSH đã lập.
3. **EC2 Instance Connect Endpoint** cấp một **đường TCP riêng đến private instance**. Nó không phải SSM Agent, không tự cài SSH key và không tự ghi toàn bộ nội dung phiên SSH.

Thiết kế truy cập EC2 production tốt bắt đầu từ **nhu cầu vận hành**, sau đó mới quyết định phương thức kết nối. IAM, mạng, OS privilege, audit, khả năng phục hồi và chi phí phải được đánh giá cùng nhau; kết quả chỉ đáng tin khi đã thử nghiệm trên chính đường kết nối dự kiến.

### Tài liệu AWS chính thức

- [AWS Systems Manager Session Manager](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager.html) — tổng quan và cách quản trị phiên.
- [Set up Session Manager](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-getting-started.html) — các bước chuẩn bị IAM, SSM Agent, mạng và client.
- [Verify or add instance permissions](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-getting-started-instance-profile.html) — `AmazonSSMManagedInstanceCore` và instance profile.
- [Sample IAM policies for Session Manager](https://docs.aws.amazon.com/systems-manager/latest/userguide/getting-started-restrict-access-quickstart.html) — quyền người dùng, managed nodes, sessions và session document.
- [VPC endpoints for Systems Manager](https://docs.aws.amazon.com/systems-manager/latest/userguide/setup-create-vpc.html) — endpoint `ssm`, `ssmmessages`, endpoint liên quan và yêu cầu mạng.
- [Session Manager logging](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-logging-auditing.html) — lưu và kiểm toán nội dung shell, giới hạn loại session.
- [EC2 Instance Connect tutorial](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-instance-connect-tutorial.html) — khóa SSH tạm và quyền IAM.
- [Connect using EC2 Instance Connect](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-instance-connect-methods.html) — Console, CLI và OpenSSH.
- [EC2 Instance Connect Endpoint](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/connect-with-ec2-instance-connect-endpoint.html) — cơ chế đường hầm, quyền, quota và chi phí.
- [Connect through EIC Endpoint](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/connect-using-eice.html) — kết nối private IPv4/IPv6 với AWS CLI và OpenSSH.
- [Troubleshooting SSM Agent](https://docs.aws.amazon.com/systems-manager/latest/userguide/troubleshooting-ssm-agent.html) — kiểm tra Agent, DNS, IAM và đường mạng.

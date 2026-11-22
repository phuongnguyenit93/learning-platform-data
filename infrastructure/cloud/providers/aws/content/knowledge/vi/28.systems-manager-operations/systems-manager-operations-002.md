# Session Manager và truy cập không mở cổng quản trị

Một đội vận hành có nhiều EC2 instances trong private subnets. Trước đây, kỹ sư phải mở TCP 22 cho SSH hoặc TCP 3389 cho RDP, duy trì bastion host, quản lý key pair và xử lý danh sách IP được phép truy cập. Mỗi lần mở rộng fleet, bề mặt mạng và quy trình cấp quyền lại phức tạp hơn.

**AWS Systems Manager Session Manager** cung cấp cách truy cập managed node thông qua IAM và SSM Agent. Người vận hành đăng nhập AWS, yêu cầu một session; SSM Agent trên node duy trì kết nối outbound tới Systems Manager và nhận luồng dữ liệu của session. Vì node chủ động mở kết nối HTTPS, security group không cần cho phép inbound SSH/RDP để sử dụng shell session hoặc port forwarding.

Session Manager hỗ trợ shell tương tác, chạy command theo session document, port forwarding tới node hoặc remote host, và SSH tunnel qua Systems Manager. Các kiểu session có khác biệt về xác thực, logging và yêu cầu agent. Đặc biệt, AWS đã công bố CVE-2026-89049 liên quan remote-host port forwarding; cần dùng SSM Agent đã vá và giới hạn quyền truy cập document này.

Bài học thuộc chương **Vận hành với Systems Manager** của module **CLOUD_PROVIDERS_AWS**. Chúng ta sẽ thiết kế Session Manager cho EC2/private subnet, phân quyền IAM theo node/tag/document, cấu hình logging/KMS, thực hiện shell và port forwarding, phân biệt SSH over Session Manager, đồng thời xây dựng runbook và guardrails production.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích Session Manager và vì sao không cần mở inbound SSH/RDP.
2. Mô tả luồng xác thực, control channel và data channel.
3. Liệt kê điều kiện managed node, SSM Agent, IAM và network.
4. Phân biệt quyền của managed node role với quyền của operator.
5. Giới hạn StartSession theo instance, tag, session document và session owner.
6. Bắt đầu shell session từ Console và AWS CLI.
7. Dùng Run As và hiểu quyền của tài khoản ssm-user.
8. Cấu hình idle timeout, maximum session duration và shell profile.
9. Thực hiện port forwarding tới managed node.
10. Thực hiện port forwarding tới remote host như RDS.
11. Phân biệt SSH over Session Manager với shell session tiêu chuẩn.
12. Bật session logging tới CloudWatch Logs hoặc S3.
13. Hiểu giới hạn logging của SSH và port forwarding.
14. Bổ sung KMS encryption và kiểm soát session data.
15. Thiết kế VPC endpoints, DNS và outbound connectivity.
16. Phân tích CVE-2026-89049 và yêu cầu SSM Agent đã vá.
17. Chẩn đoán TargetNotConnected, AccessDenied và session bị ngắt.
18. Xây dựng quy trình audit và vận hành Session Manager an toàn.

## 2. Session Manager giải quyết vấn đề gì?

Truy cập quản trị truyền thống thường cần một đường mạng từ máy kỹ sư tới máy chủ:

    Administrator
         |
         | SSH TCP 22 / RDP TCP 3389
         v
      Bastion host
         |
         v
      EC2 private node

Mô hình này yêu cầu inbound rule, IP allowlist, SSH keys hoặc RDP credentials, bastion patching, network routing và audit ở nhiều lớp. Khi số lượng node tăng, việc quản lý key và quyền truy cập trở nên khó kiểm soát.

Session Manager thay đổi luồng kết nối:

    Administrator / AWS CLI
             |
             | AWS identity + SigV4
             v
       Systems Manager
             |
             | Secure session channel
             v
          SSM Agent
             |
             v
        Managed node

Node chủ động mở kết nối outbound tới Systems Manager. Khi operator yêu cầu session, service xác thực IAM permissions, kiểm tra cấu hình session rồi chuyển dữ liệu qua channel đã thiết lập.

| Truy cập truyền thống | Session Manager |
|---|---|
| Inbound TCP 22/3389 thường phải mở | Không cần inbound SSH/RDP cho session shell và tunnel |
| SSH keys hoặc RDP credentials | IAM identity, policy và session document |
| Bastion host thường được dùng | Có thể truy cập node private qua Systems Manager |
| Audit phụ thuộc cấu hình từng máy | CloudTrail ghi API activity; session data có thể ghi CloudWatch Logs/S3 |
| Thu hồi key trên nhiều máy | Thu hồi hoặc điều chỉnh IAM permissions tập trung |

Session Manager không tự động làm mọi đường truy cập an toàn. Operator vẫn có thể chạy lệnh đặc quyền nếu policy/session document cho phép; cần giới hạn target, document, OS user và logging.

## 3. Kiến trúc và luồng kết nối

Một session có thể được khởi tạo từ Systems Manager Console, EC2 Console hoặc AWS CLI. Khi dùng CLI, máy operator cần AWS CLI và Session Manager plugin.

Luồng khái quát:

1. Operator xác thực bằng IAM identity (ví dụ IAM Identity Center/federated role).
2. Operator gọi StartSession với managed node và session document.
3. Systems Manager kiểm tra IAM policy, resource tags và document permissions.
4. Service gửi yêu cầu tới SSM Agent qua message infrastructure.
5. SSM Agent mở hoặc sử dụng secure channel outbound.
6. Session Manager kết nối client và node bằng kênh hai chiều.
7. Input từ operator được chuyển tới agent; output được gửi ngược về client.
8. Khi kết thúc, operator hoặc service đóng session; lịch sử và log được lưu theo cấu hình.

Traffic giữa client và managed node được bảo vệ bằng TLS 1.2. API requests được ký bằng AWS Signature Version 4. Có thể bật KMS encryption để tăng cường mã hóa session data ngoài lớp TLS mặc định.

### 3.1. Control channel và data channel

Control channel dùng để thiết lập/điều phối session. Data channel vận chuyển input/output của session. Các message channels của Systems Manager được SSM Agent sử dụng để trao đổi với service.

Điều này giải thích vì sao node cần outbound connectivity tới endpoint của Systems Manager. Operator không cần một route trực tiếp từ laptop tới private IP của node.

### 3.2. Không cần inbound rule không có nghĩa không cần network

Node vẫn phải kết nối được tới Systems Manager qua HTTPS. Nếu outbound bị chặn, DNS không phân giải được endpoint hoặc endpoint policy sai, node có thể vẫn ở trạng thái EC2 running nhưng Session Manager báo TargetNotConnected.

## 4. Điều kiện để sử dụng Session Manager

Trước khi bắt đầu session, xác minh các điều kiện:

- Node là Systems Manager managed node và có PingStatus Online.
- SSM Agent đã cài, đang chạy và đạt version tối thiểu cho loại session.
- Node có IAM credentials/permissions phù hợp.
- Node truy cập được các Systems Manager endpoints qua outbound HTTPS TCP 443.
- Operator có quyền StartSession tới đúng target và session document.
- Nếu dùng CLI, máy operator có AWS CLI và Session Manager plugin.
- Session preferences, KMS, CloudWatch Logs hoặc S3 được cấu hình nếu workload yêu cầu.

Các ngưỡng phiên bản được AWS tài liệu hóa:

| Tính năng | SSM Agent tối thiểu |
|---|---:|
| Shell session cơ bản | 2.3.68.0 |
| Mã hóa session data bằng KMS | 2.3.539.0 |
| Shell profiles | 3.0.161.0 |
| SSH session | 2.3.672.0 |
| Port forwarding tới managed node | 2.3.672.0 |
| Port forwarding tới remote host | 3.1.1374.0 |
| Stream session data tới CloudWatch Logs | 3.0.284.0 |

Đây là các ngưỡng feature tối thiểu, không phải version nên pin lâu dài. Hãy tự động cập nhật SSM Agent theo lịch và ưu tiên phiên bản hiện hành đã được kiểm tra.

### 4.1. Yêu cầu đặc biệt cho remote-host forwarding

Từ 09/10/2026, AWS công bố CVE-2026-89049 ảnh hưởng chức năng port forwarding tới remote host của SSM Agent. Lỗ hổng SSRF có thể cho phép người đã có quyền remote-host forwarding vượt qua denylist destination và truy cập link-local endpoint, từ đó có nguy cơ lấy temporary IAM credentials của managed node.

- Các phiên bản SSM Agent thấp hơn 3.3.4851.0 bị ảnh hưởng đối với remote-host port forwarding.
- Bản sửa được AWS công bố trong SSM Agent 3.3.4851.0.
- AWS khuyến nghị nâng lên phiên bản mới nhất.
- Trong khi chưa cập nhật, giới hạn chặt quyền dùng document AWS-StartPortForwardingSessionToRemoteHost và không cấp quyền này cho principal không tin cậy.

Đây là yêu cầu bảo mật bổ sung cho remote-host forwarding. Chỉ đạt ngưỡng 3.1.1374.0 để bật feature không có nghĩa agent đã được vá CVE. Với môi trường hiện tại, hãy dùng agent từ 3.3.4851.0 trở lên và cập nhật bản mới hơn khi AWS phát hành.

## 5. IAM: quyền của node và quyền của operator

Session Manager dùng hai nhóm quyền độc lập:

| Principal | Vai trò |
|---|---|
| Managed node IAM role | Cho SSM Agent đăng ký, giao tiếp và tạo message channels |
| Operator IAM identity | Cho phép xem node, bắt đầu/kết thúc/tiếp tục session và dùng session document |
| Logging/KMS role hoặc resource policy | Cho phép ghi log, mã hóa hoặc đọc dữ liệu theo cấu hình |

Với EC2 managed node, AWS managed policy thường dùng là `AmazonSSMManagedInstanceCore`. Policy này cấp quyền cốt lõi cho agent. Với hybrid managed node, dùng IAM service role đúng trust relationship và permissions.

Operator không cần quyền quản trị IAM role của node để bắt đầu session. Ngược lại, có quyền StartSession không giúp agent kết nối nếu node thiếu role hoặc network.

### 5.1. Các API permission thường gặp

| Action | Mục đích |
|---|---|
| ssm:StartSession | Bắt đầu session tới managed node bằng session document |
| ssm:ResumeSession | Tiếp tục session đang tồn tại |
| ssm:TerminateSession | Kết thúc session |
| ssm:DescribeSessions | Xem session list/status |
| ssm:GetConnectionStatus | Kiểm tra kết nối target |
| ssm:DescribeInstanceInformation | Xem managed-node information |
| ssmmessages:OpenDataChannel | Mở data channel cho session của caller |
| ssm:GetDocument / ssm:ListDocuments | Xem session documents khi cần chọn document từ Console |

Quyền cụ thể phụ thuộc Console, EC2 Console, CLI, session type và policy mẫu AWS. Không copy một policy lớn rồi cấp cho mọi operator; chọn policy theo workflow thực tế.

### 5.2. Giới hạn target theo ARN và tag

Có thể giới hạn StartSession vào một tập EC2 instances:

    {
      "Version": "2012-10-17",
      "Statement": [
        {
          "Effect": "Allow",
          "Action": "ssm:StartSession",
          "Resource": [
            "arn:aws:ec2:ap-southeast-1:111122223333:instance/i-0123456789abcdef0",
            "arn:aws:ssm:ap-southeast-1:111122223333:document/SSM-SessionManagerRunShell"
          ]
        }
      ]
    }

Đây là policy minh họa với một instance và default shell document. Trong thực tế, dùng tag condition để quản lý theo nhóm, ví dụ chỉ cho phép operator nhóm Finance truy cập node có tag Finance=WebServers. Giữ document ARN trong Resource để operator chỉ mở đúng loại session.

### 5.3. Chỉ cho phép operator kết thúc session của chính họ

Session Manager gắn AWS-managed resource tags vào session. Có thể dùng session-id resource tag và AWS caller identity để giới hạn ResumeSession/TerminateSession/OpenDataChannel vào session do caller tạo. AWS có policy mẫu cho IAM user và role session; cần dùng đúng condition key và format ARN theo tài liệu.

Không cấp quyền quản lý mọi session cho operator thông thường. Quyền TerminateSession trên mọi session có thể làm gián đoạn công việc của người khác.

### 5.4. Tách quyền quản trị session preferences

Người có quyền cập nhật Session Manager preferences có thể thay đổi logging, KMS encryption, Run As, timeout và shell profiles. Tách quyền này khỏi quyền bắt đầu session thông thường; thay đổi preferences ảnh hưởng tới nhiều người dùng trong account/Region.

## 6. Bắt đầu shell session từ Console

Có thể dùng Systems Manager Console hoặc EC2 Console.

Trong Systems Manager Console:

1. Chọn đúng AWS account và Region.
2. Mở Systems Manager.
3. Chọn Session Manager.
4. Chọn Start session.
5. Chọn managed node có trạng thái Online.
6. Chọn session document nếu policy cho phép; nếu không, dùng default document.
7. Chọn Start session.
8. Khi session mở, chạy Bash trên Linux/macOS hoặc PowerShell trên Windows.

Trong EC2 Console:

1. Mở EC2 → Instances.
2. Chọn instance.
3. Chọn Connect.
4. Chọn Session Manager.
5. Chọn Connect.

Nếu instance không xuất hiện, kiểm tra managed-node prerequisites và quyền của operator. Console chỉ hỗ trợ session documents có sessionType Standard_Stream khi người dùng chọn document từ giao diện.

## 7. Bắt đầu session bằng AWS CLI

Máy operator cần:

- AWS CLI đã cài và cấu hình profile/credential.
- Session Manager plugin tương thích.
- IAM identity có StartSession permission.
- Network tới AWS APIs từ máy operator.

Lệnh mở shell session:

    aws ssm start-session \
      --target i-0123456789abcdef0 \
      --region ap-southeast-1

Nếu dùng named profile:

    aws ssm start-session \
      --target i-0123456789abcdef0 \
      --region ap-southeast-1 \
      --profile production-operator

Khi session mở, terminal chuyển sang interactive stream. Kết thúc bằng lệnh thoát shell hoặc tổ hợp thoát của Session Manager plugin được hiển thị trong terminal.

Kiểm tra session đang hoạt động:

    aws ssm describe-sessions \
      --state Active \
      --region ap-southeast-1

Kết thúc một session cụ thể:

    aws ssm terminate-session \
      --session-id operator-abc123

Session ID được trả về khi StartSession thành công. Giữ ID này trong ticket/incident record nếu cần đối chiếu audit.

## 8. Quyền OS: ssm-user và Run As

Mặc định, SSM Agent tạo tài khoản OS `ssm-user` trên managed node và cấp quyền quản trị/root tương ứng. Session shell tiêu chuẩn thường chạy bằng credentials của tài khoản này.

Điều này tiện cho troubleshooting nhưng có ý nghĩa bảo mật lớn: người có quyền StartSession tới node có thể thực hiện thao tác đặc quyền theo quyền OS của session account.

### 8.1. Run As

Với Linux managed nodes, có thể bật Run As trong Session Manager preferences để chạy session bằng OS user được chỉ định thay vì ssm-user. User được chọn phải tồn tại trên node và có quyền đúng với nhiệm vụ.

Ví dụ:

- Developer chỉ cần đọc log có thể dùng OS user read-only.
- DBA cần chạy lệnh kiểm tra database có thể dùng account chuyên biệt.
- Platform administrator cần root có thể được cấp qua nhóm role có kiểm soát và approval.

Run As không thay thế IAM. IAM quyết định ai được mở session và tới node nào; Run As quyết định OS identity được dùng sau khi session được chấp nhận.

### 8.2. Kiểm soát ssm-user

Review quyền sudo/Administrator của ssm-user. Tổ chức có thể tắt hoặc thay đổi quyền quản trị mặc định theo chính sách, nhưng cần bảo đảm session documents và Run As workflow vẫn hoạt động.

Với Windows Server domain controller, có yêu cầu riêng về ssm-user; kiểm tra tài liệu AWS trước khi triển khai thay đổi account.

## 9. Session preferences

Session Manager preferences áp dụng cho account/Region hoặc được cấu hình qua session document phù hợp. Các tùy chọn thường dùng:

| Preference | Tác dụng |
|---|---|
| CloudWatch Logs | Ghi session data vào log group |
| Amazon S3 | Lưu session logs vào bucket |
| KMS encryption | Mã hóa thêm session data bằng customer managed key |
| Idle session timeout | Tự động kết thúc session không hoạt động |
| Maximum session duration | Giới hạn thời lượng tối đa |
| Run As | Chọn OS user trên Linux managed nodes |
| Shell profiles | Thiết lập shell, environment variables, working directory và startup commands |

Đặt idle timeout ngắn vừa đủ để tránh session bỏ quên. Maximum session duration nên tương ứng với quy trình change/incident. Với quyền production, yêu cầu lý do session và ghi nhận ticket/change ID trong workflow nếu tổ chức cần audit.

Không để mọi operator có quyền chỉnh preferences. Preferences thay đổi phạm vi account/Region và có thể làm mất logging hoặc giảm bảo vệ nếu cấu hình sai.

## 10. Port forwarding tới chính managed node

Port forwarding tạo tunnel từ một local port trên máy operator tới một port trên managed node. Ví dụ, kỹ sư cần mở ứng dụng nội bộ chỉ bind trong EC2 private node.

Lệnh:

    aws ssm start-session \
      --target i-0123456789abcdef0 \
      --document-name AWS-StartPortForwardingSession \
      --parameters '{"portNumber":["8080"],"localPortNumber":["18080"]}' \
      --region ap-southeast-1

Sau khi session mở, truy cập từ máy operator:

    http://localhost:18080

Ý nghĩa:

- portNumber: port trên managed node cần chuyển tiếp.
- localPortNumber: port local trên laptop/desktop của operator.
- Target: managed node đang chạy SSM Agent.

Traffic được tunnel qua Session Manager. Không cần mở inbound port 8080 từ Internet hoặc laptop tới instance; ứng dụng có thể chỉ bind trên interface nội bộ phù hợp.

### 10.1. Khi nào dùng port forwarding?

- Truy cập admin web UI chỉ có trong private subnet.
- Kiểm tra local service trên managed node.
- Kết nối tới database đang chạy ngay trên managed node.
- Tạo tunnel tạm thời để debug service.

Port forwarding không biến IAM thành database authentication. Operator vẫn cần credential riêng của ứng dụng/database nếu remote service yêu cầu.

## 11. Port forwarding tới remote host

Remote-host forwarding dùng managed node như một điểm trung chuyển để truy cập host khác mà managed node có thể kết nối tới. Remote host không bắt buộc phải là Systems Manager managed node.

Ví dụ: operator muốn kết nối Amazon RDS private endpoint qua một EC2 managed node trong cùng VPC.

    Operator laptop
        |
        | localhost:13306
        v
    Session Manager tunnel
        |
        v
    Managed EC2 node
        |
        | TCP 3306 trong VPC
        v
    RDS endpoint:3306

Lệnh:

    aws ssm start-session \
      --target i-0123456789abcdef0 \
      --document-name AWS-StartPortForwardingSessionToRemoteHost \
      --parameters '{"host":["orders-db.cluster-abc123.ap-southeast-1.rds.amazonaws.com"],"portNumber":["3306"],"localPortNumber":["13306"]}' \
      --region ap-southeast-1

Sau khi session mở, cấu hình database client:

    Host: 127.0.0.1
    Port: 13306
    Database: orders
    Username: <database-user>

Remote host phải được DNS resolve và network-reachable từ managed node. Security group của RDS cần cho phép inbound port 3306 từ security group của managed node; operator laptop không cần route trực tiếp tới RDS.

### 11.1. Quyền và phạm vi network

Remote-host forwarding có sức mạnh tương tự một TCP proxy từ máy operator qua managed node. Nếu node có thể truy cập nhiều subnet/service, người có quyền sử dụng document này có thể tiếp cận các destination đó theo phạm vi network của node.

Vì vậy:

- Chỉ cấp quyền cho nhóm DBA/operations thực sự cần.
- Giới hạn StartSession vào target node cụ thể.
- Giới hạn quyền vào document AWS-StartPortForwardingSessionToRemoteHost.
- Dùng security group/network ACL để node chỉ kết nối tới các destination cần thiết.
- Không cấp remote-host forwarding cho untrusted users hoặc public-facing workload.
- Dùng agent đã vá CVE-2026-89049 (3.3.4851.0 trở lên; ưu tiên latest).
- Theo dõi CloudTrail StartSession và review access thường xuyên.

### 11.2. Lưu ý bảo mật CVE-2026-89049

AWS công bố lỗ hổng SSRF trong remote-host port forwarding của SSM Agent. Các phiên bản thấp hơn 3.3.4851.0 bị ảnh hưởng; lỗ hổng có thể cho phép principal có quyền port forwarding truy cập link-local endpoint và có nguy cơ lấy temporary IAM credentials của managed node.

Cách xử lý:

1. Cập nhật SSM Agent lên ít nhất 3.3.4851.0, ưu tiên bản mới nhất.
2. Nếu chưa cập nhật được, tạm giới hạn hoặc gỡ quyền StartSession với document remote-host forwarding khỏi principal không tin cậy.
3. Giới hạn IAM role của managed node theo least privilege.
4. Giới hạn network egress từ managed node tới destination cần thiết.
5. Kiểm tra CloudTrail và hoạt động session đáng ngờ theo quy trình incident response.

Đừng coi ngưỡng feature 3.1.1374.0 là ngưỡng bảo mật đã vá. Remote-host forwarding chỉ nên được bật sau khi agent đáp ứng bản sửa bảo mật.

## 12. SSH qua Session Manager

SSH over Session Manager phù hợp khi công cụ hiện có yêu cầu giao thức SSH, ví dụ SCP hoặc IDE remote development. SSH daemon vẫn phải chạy trên target và user phải có SSH authentication phù hợp. Session Manager tạo tunnel TLS giữa client, service và SSM Agent; inbound TCP 22 từ mạng bên ngoài không cần mở.

SSH over Session Manager khác shell session tiêu chuẩn:

| Shell session | SSH over Session Manager |
|---|---|
| Dùng session document mặc định | Dùng SSH client và document AWS-StartSSHSession |
| Thường dùng ssm-user/Run As | Dùng OS user và SSH key/certificate của host |
| Session Manager có thể ghi command/output | Session Manager không thể ghi payload SSH |
| Không cần sshd trên node | Cần SSH daemon trên target |

Ví dụ cấu hình SSH client với ProxyCommand:

    Host i-* mi-*
      ProxyCommand sh -c "aws ssm start-session --target %h --document-name AWS-StartSSHSession --parameters 'portNumber=%p'"

Kết nối:

    ssh -i team-admin.pem ec2-user@i-0123456789abcdef0

Cấu hình thực tế có thể cần điều chỉnh quoting theo shell/OS. AWS CLI và Session Manager plugin phải được cài trên máy operator. Target cần SSH daemon, user và public key/certificate tương ứng.

Nếu chỉ cần terminal tương tác, shell session tiêu chuẩn thường đơn giản hơn và cho phép Session Manager ghi session data. Dùng SSH khi công cụ hoặc workflow thực sự cần SSH protocol.

## 13. Session logging: CloudTrail, CloudWatch Logs và S3

Cần phân biệt ba loại audit:

| Nguồn | Nội dung |
|---|---|
| AWS CloudTrail | API activity: StartSession, TerminateSession, thay đổi preferences và các request quản trị |
| Session Manager logging | Input/output của shell session theo cấu hình |
| OS/application logs | Hoạt động hệ điều hành, service, ứng dụng và database |

CloudTrail cho biết ai gọi API, khi nào và trên target nào. Nó không tự ghi toàn bộ command được nhập trong terminal. Muốn lưu command/output của shell session, cấu hình Session Manager logging tới CloudWatch Logs hoặc S3.

### 13.1. Ghi vào CloudWatch Logs

Trong Session Manager preferences:

1. Bật CloudWatch logging.
2. Chọn log group có retention phù hợp.
3. Bật tùy chọn chỉ cho phép encrypted log group nếu chính sách yêu cầu.
4. Đảm bảo quyền ghi log và KMS policy nếu log group dùng customer managed key.
5. Kiểm tra SSM Agent version đạt ngưỡng streaming logs.
6. Thử session và xác minh event xuất hiện trong log group.

CloudWatch Logs phù hợp khi cần tìm kiếm, alert, query và tích hợp CloudWatch dashboards.

### 13.2. Ghi vào Amazon S3

S3 phù hợp lưu trữ dài hạn, retention policy, lifecycle transition và audit archive. Cấu hình bucket/prefix, encryption, bucket policy và quyền ghi phù hợp.

Không cho operator đọc toàn bộ bucket chỉ vì họ có quyền StartSession. Tách quyền tạo session khỏi quyền truy cập session archive.

### 13.3. Giới hạn logging của SSH và port forwarding

Session Manager không ghi nội dung session data cho các session dùng SSH hoặc port forwarding. Với SSH, payload được mã hóa trong tunnel; với port forwarding, Session Manager chuyển tiếp dữ liệu ứng dụng thay vì diễn giải command.

Nếu cần audit các workflow đó, dùng lớp phù hợp:

- CloudTrail để audit ai mở/đóng session và target/document.
- SSH server logs cho hoạt động xác thực SSH.
- Database audit logs cho SQL statements/DB user.
- Application logs cho request/application activity.
- Client-side logs hoặc công cụ truy cập chuyên dụng theo policy.

Không tuyên bố rằng bật CloudWatch Logs trong Session Manager sẽ ghi được SQL query chạy qua tunnel port forwarding.

### 13.4. Tránh ghi secret vào session logs

Shell session logs có thể chứa lệnh và output. Không nhập password/token trực tiếp ở dạng echo hoặc command-line argument có thể bị ghi lại. Dùng prompt an toàn, secret manager và cơ chế nhập không echo. Hạn chế quyền đọc log, bật encryption và đặt retention phù hợp.

Trên Linux/macOS, AWS hướng dẫn có thể dùng lệnh đọc password mà tắt terminal echo; trên Windows, dùng PowerShell SecureString prompt. Cách cụ thể cần được kiểm thử trong shell profile và session logging setup.

## 14. Mã hóa session data bằng AWS KMS

TLS 1.2 là lớp mã hóa mặc định cho kết nối Session Manager. Có thể bật KMS encryption để tăng cường bảo vệ session data.

Khi bật KMS:

- Chọn customer managed key phù hợp.
- Key policy và IAM policy phải cho phép principal cần thiết.
- Operator có thể cần quyền KMS GenerateDataKey theo workflow.
- Managed node/Systems Manager cần network connectivity tới KMS nếu dùng VPC endpoints.
- SSM Agent phải đạt version tối thiểu 2.3.539.0.
- Kiểm thử cả session start và session reconnect.

KMS encryption bổ sung lớp mã hóa cho session data; nó không thay thế TLS, IAM authorization, logging hoặc endpoint security.

## 15. Session documents

Session document định nghĩa loại session và hành vi khi bắt đầu. Default shell session dùng document `SSM-SessionManagerRunShell`. AWS cung cấp các document khác như:

| Document | Mục đích |
|---|---|
| SSM-SessionManagerRunShell | Shell session tiêu chuẩn và session preferences |
| AWS-StartPortForwardingSession | Forward port tới managed node |
| AWS-StartPortForwardingSessionToRemoteHost | Forward port tới host khác từ managed node |
| AWS-StartSSHSession | Dùng SSH protocol qua Session Manager |

Custom Session document có thể giới hạn command, tham số, session type hoặc môi trường shell. Console chỉ hỗ trợ các document phù hợp với sessionType Standard_Stream khi người dùng chọn document.

Không cho phép user tự chọn mọi document nếu họ chỉ cần shell cơ bản. Document có thể định nghĩa command hoặc forwarding destination và làm thay đổi đáng kể quyền thực tế.

## 16. Network: endpoint và PrivateLink

Managed node cần outbound HTTPS TCP 443 tới các endpoint Systems Manager trong Region:

- `ssm.<region>.amazonaws.com`
- `ssmmessages.<region>.amazonaws.com`
- `ec2messages.<region>.amazonaws.com` khi agent/Region yêu cầu.

SSM Agent 3.3.40.0 trở lên dùng ssmmessages thay cho ec2messages khi endpoint đó có sẵn; một số Region mới không cung cấp ec2messages. Với Session Manager data channel, ssmmessages là endpoint quan trọng.

Private subnet có thể dùng:

1. NAT Gateway/egress path tới public service endpoints.
2. Interface VPC endpoints cho Systems Manager/ssmmessages.

Với PrivateLink, kiểm tra:

- Interface endpoint đúng Region và VPC.
- Private DNS enabled nếu dùng hostname chuẩn.
- Endpoint security group cho inbound TCP 443 từ managed node.
- Node security group cho outbound TCP 443 tới endpoint.
- Endpoint policy không chặn action cần thiết.
- VPC DNS resolution/hostnames và resolver rules đúng.

Nếu bật KMS encryption, CloudWatch Logs hoặc S3 session logging, cần endpoint và permissions bổ sung tương ứng cho KMS, Logs và S3.

Không cần inbound TCP 22/3389 trên managed node cho shell session hoặc tunnel. Tuy nhiên, nếu dùng SSH over Session Manager, sshd vẫn cần chạy trên target và local connection từ SSM Agent tới SSH service phải hoạt động.

## 17. VPC security group và remote destination

Session Manager không tự động thay đổi security groups. Khi port forwarding tới remote host:

- Managed node cần egress tới remote host/port.
- Remote host security group/firewall cần cho phép inbound từ managed node.
- Operator chỉ kết nối local port trên laptop.
- Không mở remote database port cho Internet hoặc laptop public IP nếu không có yêu cầu khác.

Ví dụ RDS MySQL:

| Thành phần | Rule |
|---|---|
| Operator laptop | Local TCP 13306 |
| Session Manager tunnel | Chuyển local 13306 tới managed node |
| Managed node SG | Egress TCP 3306 tới RDS SG |
| RDS SG | Inbound TCP 3306 từ managed node SG |
| RDS public access | Không cần bật |

Đây là cách kết nối quản trị phù hợp với private database, nhưng quyền IAM dùng remote-host forwarding phải được kiểm soát chặt.

## 18. Audit, notification và CloudTrail

CloudTrail ghi lại Session Manager API activity. Nên theo dõi:

- StartSession và target/document.
- TerminateSession/ResumeSession.
- Ai thay đổi Session Manager preferences.
- Ai thay đổi IAM policy hoặc role liên quan.
- Ai tạo/sửa session document.
- Các lần bật/tắt logging và KMS.
- Hoạt động activation/managed node liên quan nếu dùng hybrid fleet.

Có thể dùng EventBridge rule trên CloudTrail events để gửi SNS notification hoặc kích hoạt workflow khi session bắt đầu/kết thúc. Lưu ý event notification cho biết API activity; nó không thay thế session command logging.

## 19. Troubleshooting: TargetNotConnected

Khi StartSession trả TargetNotConnected, kiểm tra theo thứ tự:

1. Node có xuất hiện trong Systems Manager Managed nodes không?
2. PingStatus có Online không?
3. SSM Agent service có đang chạy không?
4. Agent version có đủ cho session type không?
5. Node IAM role có policy cốt lõi không?
6. Agent có truy cập được ssmmessages endpoint không?
7. DNS có resolve đúng Region không?
8. Node có outbound TCP 443 không?
9. Endpoint SG có inbound TCP 443 từ node không?
10. NACL/proxy/TLS inspection có chặn không?
11. Operator có StartSession permission và document permission không?
12. Session Manager plugin trên máy operator có cài/đúng version không?

Node Online nhưng session vẫn lỗi có thể do ssmmessages channel, operator IAM hoặc document authorization.

## 20. Troubleshooting: AccessDenied

AccessDenied thường đến từ một trong các lớp:

- Operator thiếu ssm:StartSession.
- Operator được phép target nhưng không được phép session document.
- Tag condition không khớp tag của managed node.
- Operator thiếu ResumeSession/TerminateSession cho session của chính họ.
- KMS key policy không cho phép sử dụng key.
- SCP, permissions boundary hoặc explicit Deny ghi đè Allow.
- Console cần GetDocument/ListDocuments nhưng policy chưa cấp.
- Remote-host forwarding document bị policy chặn có chủ đích.

Đọc CloudTrail event và IAM policy evaluation để xác định principal, action, resource và condition bị từ chối. Không khắc phục bằng cách cấp ssm:* hoặc Resource * cho mọi người.

## 21. Troubleshooting: session bị ngắt hoặc không ghi log

Nếu session bị ngắt:

- Kiểm tra idle timeout và maximum session duration.
- Kiểm tra agent restart/update.
- Kiểm tra network/proxy/NAT idle timeout.
- Kiểm tra ssmmessages reachability.
- Kiểm tra node CPU/memory/disk.
- Kiểm tra người dùng có terminate session hay không.

Nếu session mở được nhưng log không xuất hiện:

- Xác minh Session Manager preferences ở đúng account/Region.
- Kiểm tra log group/bucket và encryption settings.
- Kiểm tra IAM role/resource policy cho Logs/S3.
- Kiểm tra endpoint Logs/S3 nếu node private.
- Kiểm tra agent version.
- Xác định session có phải SSH hoặc port forwarding không; các loại này không được Session Manager ghi payload.

## 22. Bảo mật production

Session Manager là kênh quản trị có thể cung cấp quyền OS mạnh. Áp dụng các guardrails:

- Dùng IAM Identity Center/federation và MFA theo chính sách tổ chức.
- Giới hạn StartSession theo tag, instance ARN, Region và session document.
- Giới hạn Resume/Terminate vào session do caller tạo.
- Tách quyền quản trị preferences khỏi operator session.
- Review quyền ssm-user; cân nhắc Run As cho OS user ít quyền.
- Không cấp remote-host port forwarding cho nhóm không tin cậy.
- Cập nhật SSM Agent lên bản vá CVE-2026-89049 (3.3.4851.0 trở lên) và duy trì latest.
- Giới hạn network egress của managed node và remote destinations.
- Bật CloudTrail; bật CloudWatch Logs/S3 session logging cho shell session cần audit.
- Mã hóa log, giới hạn quyền đọc, đặt retention và lifecycle.
- Không nhập secret vào shell command có thể bị log.
- Review session documents và block public sharing nếu không cần.
- Giới hạn ai có quyền thay đổi preferences, IAM role, KMS key và VPC endpoint.
- Dùng approval/change management cho production access nếu workload yêu cầu.

### 22.1. Không nhầm “không mở cổng” với “không có rủi ro”

Session Manager giảm bề mặt inbound network và loại bỏ nhu cầu bastion trong nhiều trường hợp. Tuy nhiên, một session có quyền root vẫn có thể thay đổi hệ thống, đọc dữ liệu hoặc truy cập dependency từ node. IAM, OS permissions, network egress, logging và agent patching vẫn là các lớp bảo vệ bắt buộc.

## 23. Bài thực hành: shell session không mở SSH

Giả sử EC2 private node đã được đăng ký Systems Manager, có instance profile, agent Online và VPC endpoint.

1. Xác nhận security group không có inbound TCP 22 từ mạng operator.
2. Xác nhận node outbound TCP 443 tới SSM/ssmmessages.
3. Đăng nhập AWS bằng operator role.
4. Chạy lệnh StartSession tới instance.
5. Xác minh prompt shell xuất hiện.
6. Chạy lệnh read-only như hostname, uptime và systemctl status.
7. Thoát session.
8. Kiểm tra CloudTrail StartSession/TerminateSession.
9. Nếu logging được bật, kiểm tra CloudWatch Logs hoặc S3.
10. Xác nhận không có inbound SSH rule được thêm trong quá trình thực hành.

## 24. Bài thực hành: port forwarding tới RDS

Giả sử RDS MySQL ở private subnet và managed EC2 node có thể truy cập RDS qua security group.

1. Xác nhận SSM Agent đã vá và đạt version mới nhất.
2. Xác nhận operator được phép dùng document AWS-StartPortForwardingSessionToRemoteHost.
3. Xác nhận managed node egress TCP 3306 tới RDS.
4. Xác nhận RDS SG inbound TCP 3306 từ managed node SG.
5. Bắt đầu session remote-host forwarding với local port 13306.
6. Dùng database client kết nối 127.0.0.1:13306.
7. Xác thực bằng database credential riêng.
8. Kết thúc session và xác minh tunnel đóng.
9. Kiểm tra CloudTrail để audit StartSession.
10. Kiểm tra database audit logs nếu cần truy vết SQL statements.

Session Manager không ghi SQL traffic bên trong port-forwarding tunnel. Dùng database audit log để lưu truy vấn theo yêu cầu.

## 25. Tình huống thực tế

### Tình huống A — Developer cần shell trên EC2 private

Instance không có public IP và security group không mở SSH.

**Cách xử lý:** dùng Session Manager shell với node role, agent, ssmmessages connectivity và operator StartSession permission. Không cần bastion hoặc inbound 22.

### Tình huống B — DBA cần truy cập RDS private

Laptop không có route tới RDS.

**Cách xử lý:** dùng managed EC2 node làm tunnel endpoint, remote-host forwarding tới RDS endpoint và cấp quyền document cho nhóm DBA. Giới hạn network destination và agent version đã vá.

### Tình huống C — Session mở được nhưng không có log

Operator dùng port forwarding.

**Cách xử lý:** đây là giới hạn thiết kế: Session Manager không ghi payload port-forwarding/SSH. Dùng CloudTrail cho session API activity và database/application logs cho nội dung bên trong tunnel.

### Tình huống D — TargetNotConnected

Node có trong EC2 nhưng không Online trong Systems Manager.

**Cách xử lý:** kiểm tra agent, role, DNS, outbound 443, endpoint SG và ssmmessages. EC2 running không đồng nghĩa managed node connected.

### Tình huống E — Operator truy cập được mọi instance

Policy cho phép StartSession trên mọi resource.

**Cách xử lý:** thay bằng resource ARN/tag conditions và document ARN; giới hạn session owner cho Resume/Terminate.

### Tình huống F — Remote-host forwarding trên agent cũ

Managed node chạy SSM Agent 3.1.1374.0 và có document permission.

**Cách xử lý:** feature có thể chạy nhưng version này thấp hơn bản vá CVE-2026-89049. Nâng agent lên 3.3.4851.0 trở lên và thu hẹp document permission trong thời gian nâng cấp.

### Tình huống G — SSH qua Session Manager không hoạt động

Node Online nhưng SSH client báo connection refused.

**Cách xử lý:** kiểm tra sshd đang chạy, OS username, public key/certificate, SSH port và ProxyCommand. Session Manager tạo tunnel nhưng không tự khởi động SSH daemon hoặc cấp SSH key.

### Tình huống H — KMS encryption bật nhưng session không mở

Node có KMS key policy sai hoặc agent cũ.

**Cách xử lý:** kiểm tra agent từ 2.3.539.0, key policy, IAM permissions và KMS endpoint/private connectivity.

### Tình huống I — Session tự đóng sau thời gian không hoạt động

Session Manager preferences có idle timeout.

**Cách xử lý:** kiểm tra idle timeout và maximum duration. Chọn giá trị theo chính sách; không tắt timeout toàn cục chỉ để giữ session mở.

### Tình huống J — Người dùng nhập password và password xuất hiện trong log

Session logging đang bật và shell echo input.

**Cách xử lý:** dùng secure prompt/no-echo, secret manager và hạn chế log access. Xem xét xử lý log đã chứa secret theo quy trình incident/credential rotation.

## 26. Câu hỏi ôn tập

1. Session Manager là gì?
2. Vì sao không cần inbound TCP 22/3389 cho shell session?
3. Managed node cần kết nối outbound tới port nào?
4. Control channel và data channel có vai trò gì?
5. TLS và SigV4 bảo vệ phần nào của kết nối?
6. Quyền của managed node role khác operator role ra sao?
7. AmazonSSMManagedInstanceCore dùng cho principal nào?
8. ssm:StartSession kiểm soát điều gì?
9. Vì sao cần giới hạn session document ARN?
10. Session Manager default shell document có tên gì?
11. Session Manager CLI cần plugin nào?
12. ssm-user là tài khoản gì?
13. Run As thay đổi điều gì?
14. Session preferences có thể cấu hình những mục nào?
15. AWS-StartPortForwardingSession làm gì?
16. portNumber và localPortNumber khác nhau thế nào?
17. AWS-StartPortForwardingSessionToRemoteHost dùng khi nào?
18. Remote host có bắt buộc là managed node không?
19. Vì sao managed node cần network reachability tới remote host?
20. SSH over Session Manager có cần sshd không?
21. Vì sao SSH/port forwarding session không có Session Manager payload logs?
22. CloudTrail ghi loại activity nào?
23. CloudWatch Logs/S3 session logging ghi gì?
24. KMS encryption bổ sung điều gì ngoài TLS?
25. Remote-host forwarding cần SSM Agent version feature tối thiểu nào?
26. CVE-2026-89049 ảnh hưởng chức năng nào?
27. Bản SSM Agent nào sửa CVE-2026-89049?
28. Khi chưa cập nhật, cần hạn chế quyền gì?
29. ssmmessages endpoint có vai trò gì?
30. Vì sao port forwarding không thay thế database authentication?
31. Làm thế nào giới hạn operator theo tag?
32. Vì sao cần giới hạn ResumeSession/TerminateSession theo session owner?
33. TargetNotConnected nên kiểm tra theo thứ tự nào?
34. Session Manager có tự động ghi SQL statement qua tunnel không?
35. Vì sao không nên cấp ssm:* trên mọi resource?

**Đáp án nhanh:** (1) dịch vụ truy cập managed node qua Systems Manager; (2) node mở outbound channel; (3) TCP 443; (4) điều phối và vận chuyển dữ liệu; (5) TLS bảo vệ data channel, SigV4 ký API request; (6) node agent permissions so với quyền operator; (7) EC2 managed node role; (8) quyền mở session tới target/document; (9) document xác định loại và hành vi session; (10) SSM-SessionManagerRunShell; (11) Session Manager plugin; (12) OS account thường có quyền quản trị; (13) OS user chạy session; (14) logging, KMS, timeout, Run As, shell profile; (15) tunnel tới port trên managed node; (16) remote port và local port; (17) tunnel từ managed node tới host khác; (18) không; (19) node là điểm kết nối tới host; (20) có; (21) payload được tunnel/encrypt và service không diễn giải; (22) API activity; (23) command/output cho session được hỗ trợ; (24) thêm lớp encryption; (25) 3.1.1374.0; (26) remote-host port forwarding SSRF; (27) 3.3.4851.0; (28) StartSession tới document remote-host forwarding; (29) session message/data channels; (30) database vẫn cần credential riêng; (31) IAM condition ssm:resourceTag; (32) tránh quản lý session của người khác; (33) agent, node status, ssmmessages, DNS, 443, IAM/document; (34) không; (35) quyền quá rộng và có thể cấp quản trị ngoài ý muốn.

## 27. Checklist production

- [ ] Managed node có PingStatus Online.
- [ ] SSM Agent được cập nhật và tương thích với session type.
- [ ] Remote-host forwarding dùng SSM Agent 3.3.4851.0 trở lên.
- [ ] CVE-2026-89049 được xử lý; document remote-host forwarding không cấp cho principal không tin cậy.
- [ ] Node role có quyền SSM/ssmmessages tối thiểu.
- [ ] Operator StartSession bị giới hạn theo target ARN/tag.
- [ ] Session document ARN được giới hạn theo workflow.
- [ ] ResumeSession/TerminateSession chỉ cho session owner hoặc admin được ủy quyền.
- [ ] ssm-user privileges được review; Run As được cân nhắc.
- [ ] Session preferences có idle timeout và maximum duration.
- [ ] CloudTrail ghi nhận Session Manager API activity.
- [ ] Shell session logging tới CloudWatch Logs/S3 được bật theo audit policy.
- [ ] SSH/port-forwarding logging limitation được phản ánh trong audit design.
- [ ] Log group/bucket được mã hóa, có retention và access control.
- [ ] KMS key policy và IAM permissions được kiểm tra nếu bật encryption.
- [ ] Không nhập secret vào command/output có thể được log.
- [ ] Node outbound TCP 443 tới SSM/ssmmessages.
- [ ] PrivateLink endpoint và endpoint SG cho phép 443 từ managed nodes.
- [ ] Không mở inbound 22/3389 nếu không có use case khác.
- [ ] Remote-host forwarding bị giới hạn theo target, document và network egress.
- [ ] RDS/database audit logs được dùng cho SQL qua tunnel.
- [ ] Session documents có allowedValues/allowedPattern khi nhận parameters.
- [ ] Quyền thay đổi Session Manager preferences được tách riêng.
- [ ] Có EventBridge/SNS notification hoặc monitoring cho session activity nếu cần.
- [ ] Runbook xử lý TargetNotConnected, AccessDenied, missing logs và disconnected sessions.
- [ ] IAM, SSM Agent và session document permissions được review định kỳ.

## 28. Tổng kết

Session Manager cho phép operator truy cập managed node bằng IAM và SSM Agent qua kết nối outbound, giúp nhiều workload private không cần mở inbound SSH/RDP hoặc duy trì bastion host.

- Session shell dùng SSM-SessionManagerRunShell; operator có thể kết nối từ Console hoặc AWS CLI/Session Manager plugin.
- Managed node cần agent, IAM role và outbound TCP 443 tới Systems Manager/ssmmessages endpoints.
- IAM policy nên giới hạn target, tag, session document và session owner.
- ssm-user mặc định có quyền OS mạnh; Run As giúp chọn OS identity ít quyền hơn.
- Port forwarding tới node hoặc remote host tạo tunnel tới local port; remote host phải reachable từ managed node.
- SSH over Session Manager vẫn cần SSH daemon, OS user và SSH authentication.
- CloudTrail ghi API activity; CloudWatch Logs/S3 có thể lưu shell session data, nhưng không ghi payload SSH/port-forwarding.
- KMS encryption bổ sung lớp bảo vệ ngoài TLS; session preferences quản lý logging, timeout, Run As và shell profile.
- CVE-2026-89049 ảnh hưởng remote-host port forwarding trong SSM Agent dưới 3.3.4851.0; cập nhật agent và giới hạn document permissions.
- Production access cần least privilege, audit, network egress controls và runbook.

Session Manager giảm bề mặt inbound network, nhưng vẫn là một kênh quản trị mạnh. Hãy coi IAM policy, OS identity, session document, agent patch level, destination reachability và audit logging là một thiết kế thống nhất.

### Tài liệu AWS chính thức

1. Session Manager overview: https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager.html
2. Session Manager prerequisites: https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-prerequisites.html
3. Start a session: https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-sessions-start.html
4. Control session access to managed nodes: https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-getting-started-restrict-access.html
5. Sample IAM policies for Session Manager: https://docs.aws.amazon.com/systems-manager/latest/userguide/getting-started-restrict-access-quickstart.html
6. Additional sample IAM policies: https://docs.aws.amazon.com/systems-manager/latest/userguide/getting-started-restrict-access-examples.html
7. Session Manager SSH connections: https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-getting-started-enable-ssh-connections.html
8. Configure session preferences: https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-getting-started-configure-preferences.html
9. Enabling and disabling session logging: https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-logging.html
10. Logging session data to CloudWatch Logs: https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-logging-cloudwatch-logs.html
11. Logging session data to S3: https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-logging-s3.html
12. Use AWS PrivateLink for Session Manager: https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-getting-started-privatelink.html
13. Systems Manager VPC endpoints: https://docs.aws.amazon.com/systems-manager/latest/userguide/setup-create-vpc.html
14. Security best practices for Systems Manager: https://docs.aws.amazon.com/systems-manager/latest/userguide/security-best-practices.html
15. Troubleshooting Session Manager: https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-troubleshooting.html
16. AWS Security Bulletin CVE-2026-89049: https://aws.amazon.com/security/security-bulletins/2026-107-aws/
17. SSM Agent releases and fixes: https://github.com/aws/amazon-ssm-agent/releases

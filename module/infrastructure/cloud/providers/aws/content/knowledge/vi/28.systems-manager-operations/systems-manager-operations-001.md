# Systems Manager managed node và điều kiện kết nối

Một đội vận hành có EC2 instances chạy ứng dụng Java trong private subnets, máy chủ tại datacenter và VM ở cloud khác. Đội muốn dùng AWS Systems Manager để kiểm tra inventory, chạy lệnh, vá hệ điều hành và truy cập máy chủ qua Session Manager mà không mở SSH/RDP inbound. Để làm được điều đó, từng máy phải trở thành **managed node** và duy trì kết nối outbound tới Systems Manager.

Một instance đang ở trạng thái EC2 `running` chưa chắc đã xuất hiện trong Fleet Manager. Systems Manager cần SSM Agent hoạt động trên hệ điều hành được hỗ trợ, một nguồn IAM credentials có quyền phù hợp và đường mạng tới service endpoints. Với EC2, có thể dùng instance profile hoặc Default Host Management Configuration (DHMC). Với máy không phải EC2, thường dùng hybrid activation cùng IAM service role.

Bài học thuộc chương **Vận hành với Systems Manager** của module **CLOUD_PROVIDERS_AWS**. Nội dung tập trung vào điều kiện đăng ký managed node, SSM Agent, IAM identity, DHMC, hybrid activation, endpoint connectivity, Session Manager và quy trình chẩn đoán node không online.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích managed node là gì và Systems Manager quản lý những loại máy nào.
2. Nêu ba điều kiện nền tảng để node xuất hiện và duy trì trạng thái managed.
3. Kiểm tra hệ điều hành và phiên bản SSM Agent được hỗ trợ.
4. Phân biệt instance profile, DHMC và hybrid activation.
5. Chọn IAM policy phù hợp cho EC2 managed node.
6. Giải thích vai trò của IAM service role trong hybrid/multicloud.
7. Nhận biết cách SSM Agent lấy credentials và lỗi do credential source xung đột.
8. Xác định endpoint SSM cần thiết và cổng mạng.
9. Thiết kế kết nối qua NAT/Internet egress hoặc AWS PrivateLink.
10. Giải thích yêu cầu DNS, security group, network ACL và proxy.
11. Phân biệt yêu cầu quản lý node nói chung với yêu cầu riêng của Session Manager.
12. Kiểm tra trạng thái agent, registration và connection.
13. Dùng `ssm-cli` để chẩn đoán lỗi.
14. Đọc log SSM Agent và xử lý các lỗi thường gặp.
15. Thiết kế onboarding, cập nhật agent và vận hành managed-node fleet an toàn.

## 2. Managed node là gì?

**Managed node** là máy được cấu hình để AWS Systems Manager có thể nhận diện, liên lạc và thực hiện các thao tác quản lý trên đó. Managed node không chỉ là EC2 instance. Các loại máy có thể gồm EC2 instances, máy chủ vật lý tại on-premises datacenter, VM trên nền tảng ảo hóa nội bộ hoặc cloud khác, và một số edge devices/AWS IoT Greengrass core devices theo mô hình được hỗ trợ.

Các máy không phải EC2 thường được quản lý qua hybrid and multicloud activation. Với macOS, Systems Manager hỗ trợ EC2 Mac instances; không phải mọi loại macOS host ngoài EC2 đều được hỗ trợ.

Managed node có thể dùng nhiều khả năng của Systems Manager:

| Khả năng | Ví dụ |
|---|---|
| Session Manager | Truy cập shell hoặc port forwarding mà không mở SSH/RDP inbound |
| Run Command | Chạy lệnh hoặc SSM document trên một nhóm node |
| State Manager | Duy trì cấu hình và thực thi association theo lịch |
| Patch Manager | Quét và cài bản vá theo baseline |
| Inventory | Thu thập OS, phần mềm, network và metadata |
| Distributor | Phân phối package/agent |
| Fleet Manager | Xem và quản lý node tập trung |

Không phải mọi tính năng đều hỗ trợ mọi hệ điều hành hoặc loại máy. Trước khi thiết kế fleet, hãy kiểm tra ma trận hỗ trợ OS và yêu cầu riêng của từng capability.

## 3. Ba điều kiện nền tảng để node được quản lý

Để một máy được Systems Manager nhận diện và duy trì trạng thái managed, cần ba điều kiện:

1. **SSM Agent đã cài đặt và đang chạy** trên hệ điều hành được hỗ trợ.
2. **Node có IAM credentials và permissions phù hợp** để giao tiếp với Systems Manager.
3. **SSM Agent kết nối được tới service endpoints** trong đúng AWS Region.

    +-----------------------------+
    |  Operating system supported |
    +--------------+--------------+
                   |
                   v
    +-----------------------------+
    | SSM Agent installed/running |
    +--------------+--------------+
                   |
                   v
    +-----------------------------+
    | IAM credentials + permissions|
    +--------------+--------------+
                   |
                   v
    +-----------------------------+
    | DNS + HTTPS endpoint access |
    +--------------+--------------+
                   |
                   v
    +-----------------------------+
    | Systems Manager managed node|
    +-----------------------------+

Thiếu một điều kiện có thể khiến instance vẫn chạy bình thường ở EC2 nhưng không xuất hiện trong Managed nodes, hoặc xuất hiện rồi chuyển sang `Connection Lost`. AWS xác nhận tình trạng node bằng health signal định kỳ; tài liệu troubleshooting mô tả chu kỳ khoảng năm phút.

## 4. Hệ điều hành và AMI

Systems Manager chỉ hỗ trợ danh sách OS version và kiến trúc CPU được AWS công bố. Hỗ trợ đi theo vòng đời của nhà cung cấp OS:

- Không phải mọi OS do vendor hỗ trợ đều được Systems Manager hỗ trợ.
- Khi OS version hết vòng đời vendor (EOL), AWS Systems Manager support cho phiên bản đó cũng kết thúc theo chính sách tài liệu.
- Patch Manager có ma trận hỗ trợ riêng; OS được quản lý không đồng nghĩa mọi patch operation đều được hỗ trợ.
- Kiểm tra kiến trúc x86_64/ARM64 và phiên bản OS cụ thể trước khi chọn AMI hoặc tạo custom image.

Một số OS phổ biến gồm Amazon Linux 2/2023, Ubuntu Server, RHEL, Debian, SUSE và Windows Server. Danh sách/minor versions thay đổi theo thời gian; dùng trang Supported operating systems and machine types làm nguồn chuẩn.

Một số AWS managed AMIs có SSM Agent cài sẵn. Với custom AMI:

1. Cài SSM Agent đúng package/architecture.
2. Enable service khi boot.
3. Không bake activation code hoặc static credentials vào image.
4. Kiểm tra agent không giữ registration identity của image nguồn.
5. Cập nhật agent theo lịch.
6. Test image trong đúng account/Region/VPC trước khi phát hành.

## 5. SSM Agent

SSM Agent là phần mềm chạy trên managed node. Agent nhận yêu cầu từ Systems Manager, thực thi operation được phép và gửi trạng thái/kết quả về AWS. Agent chủ động giao tiếp outbound qua HTTPS và message channels; không cần mở inbound management port để AWS SSH vào máy.

Vai trò chính:

- Đăng ký node và gửi thông tin trạng thái.
- Nhận Run Command, Session Manager và SSM document operations.
- Thực thi lệnh bằng quyền OS của agent/document worker.
- Gửi execution status, command output và health information.
- Duy trì message channels cho session và command orchestration.

Trên Linux/macOS, agent thường chạy dưới quyền root. Trên Windows, agent chạy như Windows service với quyền hệ thống phù hợp. Vì vậy, quyền cho phép người dùng khởi chạy SSM document có thể tương đương quyền quản trị máy; cần kiểm soát IAM và document access chặt chẽ.

## 6. Kiểm tra SSM Agent

Linux với systemd:

    sudo systemctl status amazon-ssm-agent
    sudo systemctl enable amazon-ssm-agent
    sudo systemctl start amazon-ssm-agent

Một số Ubuntu image cài agent dưới dạng Snap:

    sudo systemctl status snap.amazon-ssm-agent.amazon-ssm-agent.service
    sudo snap start amazon-ssm-agent

Windows Server, PowerShell với quyền Administrator:

    Get-Service AmazonSSMAgent
    Start-Service AmazonSSMAgent

Service name có thể khác theo OS/package. Không restart agent hàng loạt khi chưa đánh giá ảnh hưởng tới các Session Manager sessions hoặc Run Command đang chạy.

### 6.1. Phiên bản agent và yêu cầu tính năng

| Capability | Phiên bản SSM Agent tối thiểu |
|---|---:|
| Session Manager shell cơ bản | 2.3.68.0 |
| Mã hóa session data bằng AWS KMS | 2.3.539.0 |
| Shell profiles | 3.0.161.0 |
| Port forwarding hoặc SSH qua Session Manager | 3.0.222.0 |
| Stream session data tới CloudWatch Logs | 3.0.284.0 |
| DHMC cho EC2 | 3.2.582.0 |

Đây là các ngưỡng tính năng cụ thể, không phải khuyến nghị giữ agent ở các version cũ. Hãy ưu tiên phiên bản agent hiện hành được AWS hỗ trợ.

## 7. IAM credentials qua EC2 instance profile

SSM Agent cần AWS credentials để gọi Systems Manager APIs. Với EC2, cách truyền thống là gắn IAM role qua **instance profile**.

    EC2 instance
       |
       | Instance Metadata Service (IMDS)
       v
    IAM instance profile
       |
       | Temporary role credentials
       v
    SSM Agent
       |
       | HTTPS API / message channels
       v
    AWS Systems Manager

Policy phổ biến cho EC2 managed node là AWS managed policy `AmazonSSMManagedInstanceCore`. Policy này cung cấp nhóm quyền cốt lõi để SSM Agent đăng ký và giao tiếp với Systems Manager. Nếu dùng custom policy, phải bảo đảm có đủ action cho capability đang bật; policy chỉ đủ registration có thể chưa đủ cho Session Manager, logging, inventory hoặc integration bổ sung.

Ví dụ CloudFormation tạo role và instance profile:

    Resources:
      ManagedNodeRole:
        Type: AWS::IAM::Role
        Properties:
          AssumeRolePolicyDocument:
            Version: "2012-10-17"
            Statement:
              - Effect: Allow
                Principal:
                  Service: ec2.amazonaws.com
                Action: sts:AssumeRole
          ManagedPolicyArns:
            - arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore

      ManagedNodeInstanceProfile:
        Type: AWS::IAM::InstanceProfile
        Properties:
          Roles:
            - !Ref ManagedNodeRole

EC2 instance cần tham chiếu instance profile trong property `IamInstanceProfile`. Không gắn IAM user access key vào file cấu hình của agent.

## 8. Default Host Management Configuration (DHMC)

**Default Host Management Configuration** cho phép Systems Manager tự động cung cấp IAM role ở cấp account/Region để quản lý EC2 instances. Cách này giảm nhu cầu tạo và gắn instance profile riêng cho từng EC2.

Các điều kiện quan trọng:

- DHMC phải được bật riêng trong từng AWS Region cần quản lý.
- EC2 instance phải dùng IMDSv2.
- SSM Agent phải từ version 3.2.582.0 trở lên.
- Role được chọn cho DHMC phải có trust relationship phù hợp với Systems Manager.
- Việc bật cấu hình có thể mất tối đa khoảng 30 phút để instance bắt đầu dùng credentials của role.

DHMC dùng role mặc định `AWSSystemsManagerDefaultEC2InstanceManagementRole` hoặc custom role được chỉ định. Policy mặc định liên quan là `AmazonSSMManagedEC2InstanceDefaultPolicy`.

### 8.1. DHMC và instance profile

Nếu EC2 đã có instance profile và policy của profile cho phép `ssm:UpdateInstanceInformation`, SSM Agent sẽ thử dùng quyền từ instance profile trước. Khi đó agent không chuyển sang credentials do DHMC cung cấp.

Nếu muốn node dùng DHMC, review instance profile hiện tại và loại bỏ quyền `ssm:UpdateInstanceInformation` khỏi profile đó theo hướng dẫn AWS. Không xóa cả instance profile nếu ứng dụng trên EC2 vẫn cần quyền AWS khác.

### 8.2. IMDSv2

DHMC yêu cầu IMDSv2. IMDSv2 sử dụng session token khi truy cập metadata endpoint, giảm rủi ro một số kiểu SSRF và credential exposure.

Kiểm tra metadata options:

    aws ec2 describe-instances \
      --instance-ids i-0123456789abcdef0 \
      --query 'Reservations[0].Instances[0].MetadataOptions'

Để yêu cầu IMDSv2 trong launch template:

    MetadataOptions:
      HttpTokens: required

Không chặn SSM Agent truy cập metadata endpoint `169.254.169.254`. Nếu dùng proxy, cấu hình bypass/no_proxy cho địa chỉ metadata.

## 9. Hybrid activation cho máy không phải EC2

Với on-premises server, VM ở cloud khác hoặc edge device được hỗ trợ, không thể gắn EC2 instance profile. Thay vào đó, tạo **hybrid activation** trong account và Region muốn quản lý node.

    Administrator
       |
       | Create activation
       v
    Activation ID + Activation Code
       |
       | Install/configure SSM Agent on non-EC2 host
       v
    SSM Agent registers with Systems Manager
       |
       v
    Managed node ID: mi-xxxxxxxxxxxxxxxxx

Activation gồm Activation ID, Activation Code, IAM service role, registration limit, expiration date và tags/default instance name nếu cấu hình. Sau khi đăng ký, non-EC2 managed node thường có ID bắt đầu bằng `mi-`.

### 9.1. IAM service role

IAM service role được dùng cho hybrid managed nodes. Trust policy phải cho phép service principal:

    {
      "Version": "2012-10-17",
      "Statement": [
        {
          "Effect": "Allow",
          "Principal": {
            "Service": "ssm.amazonaws.com"
          },
          "Action": "sts:AssumeRole"
        }
      ]
    }

Role cần policy cho phép Systems Manager operations phù hợp, thường bắt đầu từ `AmazonSSMManagedInstanceCore` rồi bổ sung quyền thực sự cần cho capability cụ thể.

Không dùng EC2 instance profile role thay cho hybrid service role. Hai loại role có trust relationship và cách phân phối credentials khác nhau.

### 9.2. Bảo vệ activation code

Activation code và activation ID cung cấp khả năng đăng ký node vào account/Region. Hãy lưu code trong secret manager/kênh quản trị được bảo vệ; không commit vào Git, image hoặc script dùng chung; giới hạn registration limit; đặt expiry ngắn phù hợp rollout; không in code vào log; deregister node không còn được quản lý.

Activation hết hạn chỉ ngăn đăng ký node mới bằng activation đó; các node đã đăng ký vẫn tiếp tục managed cho đến khi được deregister.

### 9.3. Thay đổi hybrid trong năm 2026

Activation code có thời hạn đăng ký tối đa 30 ngày; mặc định thường là 24 giờ nếu không chỉ định. Nếu cần đăng ký thêm máy sau khi activation hết hạn, tạo activation mới.

Theo tài liệu hiện hành:

- Trang Hybrid Activations cũ trong console dự kiến deprecated ngày 31/12/2026; activation hiện có vẫn có thể quản lý qua APIs và unified Systems Manager console.
- Advanced-instances tier đã được gỡ bỏ từ 30/06/2026.
- Session Manager và Run Command trên hybrid managed nodes chuyển sang pay-as-you-go pricing từ 30/09/2026.

Khi thiết kế hybrid fleet vào cuối năm 2026, hãy dùng unified console/API và kiểm tra AWS Systems Manager pricing hiện hành cho Region và loại node.

## 10. Credential source và lỗi credentials

SSM Agent cần lấy credentials từ nguồn phù hợp. Trên Linux/macOS, agent thường chạy dưới root nên environment variables hoặc credentials file mà agent thấy là của root, không phải user đăng nhập thông thường.

Một số nguồn credentials có thể xuất hiện trong môi trường: environment variables, shared credentials file, ECS task role trong một số môi trường container, EC2 instance profile và role do DHMC cung cấp.

Không trộn static credentials với instance role. Nếu agent đọc nhầm credential source cũ hoặc thiếu quyền, node có thể không đăng ký dù instance profile đúng.

Checklist:

1. Kiểm tra instance profile đã gắn đúng instance.
2. Kiểm tra role trust principal là `ec2.amazonaws.com`.
3. Kiểm tra policy chứa quyền cần thiết.
4. Kiểm tra IMDS có thể truy cập.
5. Kiểm tra proxy không chặn IMDS.
6. Kiểm tra environment/credentials file của root không chứa credentials cũ.
7. Nếu dùng DHMC, kiểm tra instance profile không giữ quyền `ssm:UpdateInstanceInformation` gây ưu tiên sai nguồn.

## 11. Endpoint connectivity: SSM Agent cần gọi gì?

SSM Agent khởi tạo kết nối outbound qua HTTPS tới endpoints trong Region của node. Các endpoint chính:

| Endpoint | Vai trò |
|---|---|
| `ssm.<region>.amazonaws.com` | Systems Manager API operations |
| `ssmmessages.<region>.amazonaws.com` | Message Gateway, Session Manager channels và agent communication |
| `ec2messages.<region>.amazonaws.com` | Message Delivery cho một số agent/Region cũ |

SSM Agent version 3.3.40.0 trở lên dùng `ssmmessages` thay cho `ec2messages` khi endpoint đó có sẵn. Một số AWS Regions mới không cung cấp `ec2messages`. Với agent cũ hoặc Region cũ, `ec2messages` vẫn có thể cần thiết.

Không copy cứng danh sách endpoint từ một Region sang mọi Region. Kiểm tra service availability và agent version đang chạy.

### 11.1. Cổng và hướng kết nối

Yêu cầu mạng cốt lõi:

- Node cho phép outbound TCP 443 tới endpoint.
- Security group của node phải cho phép egress tương ứng.
- Nếu dùng interface VPC endpoint, security group của endpoint phải cho inbound TCP 443 từ node security group hoặc CIDR phù hợp.
- Network ACL phải cho phép request và response traffic, gồm ephemeral return ports theo thiết kế subnet.
- DNS phải phân giải endpoint về địa chỉ đúng.
- TLS certificate chain phải được hệ điều hành/agent tin cậy.

Thông thường không cần mở inbound TCP 22 (SSH) hoặc 3389 (RDP) để dùng Session Manager. Operator gọi Systems Manager APIs; agent giữ outbound channel và session data đi qua message service.

## 12. Kết nối từ private subnet

### 12.1. Qua NAT Gateway hoặc Internet egress

Private subnet có thể dùng NAT Gateway để mở outbound HTTPS tới public AWS service endpoints. Instance không cần public IP nếu route table, NAT, security group và NACL cho phép.

Ưu điểm là dễ dùng cho nhiều AWS public endpoints. Hạn chế là traffic đi qua NAT, có thể phát sinh chi phí và phụ thuộc egress path.

### 12.2. Qua AWS PrivateLink

Nếu không muốn node đi Internet/NAT, tạo interface VPC endpoints trong VPC:

    com.amazonaws.<region>.ssm
    com.amazonaws.<region>.ssmmessages
    com.amazonaws.<region>.ec2messages

Chỉ tạo `ec2messages` khi Region/agent compatibility yêu cầu và endpoint có sẵn.

Cần kiểm tra Private DNS, VPC DNS support/hostnames, endpoint ENI/subnet/AZ, endpoint security group inbound 443 từ managed nodes, node security group egress 443, endpoint policy và DNS/proxy/firewall. PrivateLink endpoints giúp managed nodes private kết nối tới Systems Manager mà không cần Internet Gateway hoặc NAT cho traffic đó.

### 12.3. Endpoint bổ sung cho tính năng tùy chọn

| Tính năng | Endpoint/service có thể cần |
|---|---|
| Download package/document/script từ S3 | Amazon S3 |
| Ghi session/command output vào CloudWatch Logs | CloudWatch Logs |
| Ghi session/command output vào S3 | Amazon S3 |
| Mã hóa session data bằng customer managed key | AWS KMS |
| CloudWatch Agent/metrics monitoring | CloudWatch Monitoring |
| Các operation EC2 khác trong document | EC2 API |

Đây là yêu cầu phụ thuộc feature/document. Đừng tạo mọi endpoint chỉ vì SSM Agent cần endpoint cốt lõi; hãy đối chiếu operation thực tế của fleet.

## 13. DNS, proxy và TLS

Nếu DNS không phân giải được `ssm.<region>.amazonaws.com` hoặc `ssmmessages.<region>.amazonaws.com`, agent không thể mở channel.

Với PrivateLink, kiểm tra Private DNS, VPC DNS support/hostnames, resolver rules, DNS firewall và DNS resolver của node. Dùng `nslookup`/`dig` hoặc công cụ tương đương để xác minh hostname.

Nếu node đi qua HTTP proxy, cấu hình proxy cho SSM Agent; bảo đảm proxy cho phép CONNECT HTTPS tới SSM endpoints; bypass `169.254.169.254` cho IMDS; kiểm tra proxy credentials và TLS trust chain. TLS inspection proxy, custom CA hoặc certificate store không đầy đủ có thể gây lỗi handshake.

Không tắt certificate verification để xử lý tạm lỗi TLS. Sửa trust store/proxy policy theo chuẩn bảo mật.

## 14. Session Manager có yêu cầu riêng

Một managed node online chưa chắc đã sẵn sàng cho mọi kiểu Session Manager session. Ngoài điều kiện quản lý node, cần:

- SSM Agent version phù hợp với session type.
- `ssmmessages` connectivity và endpoint permissions.
- Operator IAM policy cho phép `ssm:StartSession` trên target/document phù hợp.
- Session preferences/KMS/S3/CloudWatch Logs nếu bật logging/encryption.
- Session Manager plugin trên máy operator nếu dùng AWS CLI.
- OS account và shell phù hợp trên managed node.

Session Manager thường dùng `ssm-user` account. Agent có thể tạo account này khi session đầu tiên bắt đầu; account thường có quyền quản trị/root tương ứng. Tổ chức cần review quyền của `ssm-user`, giới hạn ai được StartSession và ghi lại session theo yêu cầu audit.

Port forwarding hoặc SSH over Session Manager yêu cầu agent tối thiểu 3.0.222.0 và không cần mở inbound SSH port trên node. Nếu bật session logging tới S3/CloudWatch Logs, node và/hoặc service cần network/IAM permissions tương ứng. Mã hóa session data bằng KMS cũng có yêu cầu agent version và quyền KMS riêng.

## 15. Tách IAM permissions của node và operator

Có hai principal khác nhau:

| Principal | Quyền chính |
|---|---|
| IAM role của managed node | Cho SSM Agent đăng ký, gửi status, nhận/hoàn tất operation và dùng capability được cấu hình |
| IAM identity của operator | Cho phép xem node, StartSession, SendCommand, TerminateSession, quản lý documents và xem output theo quyền |

Gắn `AmazonSSMManagedInstanceCore` vào EC2 instance role không tự động cho mọi IAM user quyền truy cập máy. Ngược lại, cấp `ssm:StartSession` cho operator không giúp node kết nối nếu agent thiếu credentials hoặc network.

Với operator, giới hạn `ssm:StartSession` theo instance ARN/tag và session documents được phép; giới hạn `ssm:SendCommand` theo document và target; cấp `ssm:TerminateSession` cho session thuộc phạm vi phù hợp; review quyền `ssm:UpdateInstanceInformation`, `ssm:UpdateServiceSetting`, `iam:PassRole` và activation administration riêng. Dùng CloudTrail và session logging để audit.

Không cấp `ssm:*` trên mọi resource chỉ để đơn giản hóa onboarding.

## 16. Kiểm tra node từ AWS CLI

Liệt kê thông tin managed node theo instance ID:

    aws ssm describe-instance-information \
      --filters "Key=InstanceIds,Values=i-0123456789abcdef0" \
      --region ap-southeast-1

Trường cần xem gồm InstanceId, PingStatus, LastPingDateTime, AgentVersion, PlatformType/PlatformName/PlatformVersion và ResourceType.

Kiểm tra trạng thái kết nối:

    aws ssm get-connection-status \
      --target i-0123456789abcdef0 \
      --region ap-southeast-1

Với non-EC2 hybrid node, dùng managed node ID dạng `mi-...` làm target.

Để bắt đầu session sau khi node online:

    aws ssm start-session \
      --target i-0123456789abcdef0 \
      --region ap-southeast-1

AWS CLI cần Session Manager plugin cài trên máy operator để mở session tương tác. `describe-instance-information` là bước kiểm tra danh sách; `get-connection-status` kiểm tra trạng thái kết nối hiện tại.

## 17. Dùng ssm-cli chẩn đoán tại node

SSM Agent từ version 3.1.501.0 trở lên có kèm `ssm-cli`. Công cụ này kiểm tra các điều kiện cần để node được Systems Manager quản lý.

Linux/macOS:

    ssm-cli get-diagnostics --output table

Windows Server, chạy từ thư mục agent:

    cd "C:\Program Files\Amazon\SSM"
    .\ssm-cli.exe get-diagnostics --output table

Các nhóm kiểm tra có thể gồm EC2 Instance Metadata Service, hybrid instance registration, kết nối tới `ssm`, `ec2messages`, `ssmmessages` và một số endpoint bổ sung như S3, KMS, Logs, Monitoring.

Các kiểm tra S3/KMS/Logs/Monitoring phục vụ tính năng tùy chọn; kết quả fail ở endpoint phụ không nhất thiết có nghĩa managed-node registration thất bại. Đọc ghi chú từng check và đối chiếu feature mà node đang dùng.

## 18. Kiểm tra log của SSM Agent

SSM Agent ghi log về registration, execution, command, scheduled action, session worker và lỗi kết nối.

Linux/macOS:

    /var/log/amazon/ssm/amazon-ssm-agent.log
    /var/log/amazon/ssm/errors.log

Windows Server:

    %PROGRAMDATA%\Amazon\SSM\Logs\amazon-ssm-agent.log
    %PROGRAMDATA%\Amazon\SSM\Logs\errors.log

Với Linux, stdout/stderr của agent worker có thể nằm trong `/var/lib/amazon/ssm/`. Với Windows, dữ liệu instance/worker có thể nằm trong `%PROGRAMDATA%\Amazon\SSM\InstanceData\`.

Khi debug, ghi nhận thời điểm lỗi và Region; tìm error quanh thời điểm agent đăng ký/mất kết nối; phân loại DNS, TCP, TLS, credential, AccessDenied hay agent crash; chỉ bật debug logging trong thời gian cần thiết; tắt debug sau khi thu thập bằng chứng vì log volume có thể tăng và chứa metadata nhạy cảm.

## 19. Runbook: node không xuất hiện trong Managed nodes

Thực hiện theo thứ tự:

1. Xác nhận EC2 instance đang ở account và Region cần kiểm tra.
2. Xác nhận OS/version nằm trong danh sách hỗ trợ.
3. Kiểm tra SSM Agent đã cài, đúng version và đang chạy.
4. Kiểm tra node có đúng identity source: instance profile, DHMC hoặc hybrid activation.
5. Kiểm tra IAM role trust và permissions.
6. Kiểm tra IMDSv2/IMDS connectivity nếu dùng EC2.
7. Chạy `ssm-cli get-diagnostics --output table`.
8. Kiểm tra DNS phân giải SSM endpoints.
9. Kiểm tra outbound TCP 443, proxy, endpoint security group và NACL.
10. Đọc SSM Agent logs.
11. Dùng `describe-instance-information` để xem registration/last ping.
12. Sau khi sửa, đợi agent reconnect và xác minh `PingStatus=Online`.

Nếu node không có kết quả trong `describe-instance-information`, có thể registration chưa hoàn tất hoặc credentials/endpoint không đúng. Nếu node có nhưng `ConnectionLost`, ưu tiên kiểm tra agent process, heartbeat, IAM credential refresh và network path.

## 20. Runbook: Session Manager báo TargetNotConnected

`TargetNotConnected` thường có nghĩa Session Manager không thể thiết lập channel tới target. Kiểm tra node có PingStatus Online không; SSM Agent version có đủ cho loại session không; agent có kết nối `ssmmessages` không; endpoint security group có inbound TCP 443 từ node không; node có outbound 443 và DNS đúng không; IAM node role có quyền message channel không; operator có `ssm:StartSession` và quyền document không; Private DNS/endpoint policy có đúng không; proxy/TLS inspection có cho phép TLS channel không; node có thiếu CPU, memory hoặc disk không.

Không mở SSH/RDP inbound như bước sửa mặc định. Session Manager được thiết kế để quản lý qua outbound service connection.

## 21. Các lỗi thường gặp và nguyên nhân

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| EC2 running nhưng không xuất hiện | Agent chưa cài/chạy, OS không hỗ trợ | Kiểm tra agent và OS |
| Instance profile không có hiệu lực | Role chưa gắn, trust sai, thiếu policy | Review profile và IAM |
| DHMC không hoạt động | IMDSv1, agent cũ, profile vẫn có `ssm:UpdateInstanceInformation` | Đáp ứng DHMC prerequisites |
| ConnectionLost | Agent stopped, mất egress, credentials hết hiệu lực | Agent status, logs, endpoints |
| DNS resolution failure | Resolver/Private DNS sai | Kiểm tra VPC DNS và endpoint |
| TLS handshake error | Proxy inspection hoặc CA thiếu | Sửa trust chain |
| AccessDenied | IAM policy, endpoint policy hoặc KMS policy thiếu | Xác định principal/action/resource |
| Session không mở được | `ssmmessages`, agent version, operator permission | Kiểm tra session prerequisites |
| Run Command không có output | Document permission, S3/Logs path hoặc execution error | Kiểm tra command invocation và agent logs |
| Node online rồi offline định kỳ | Proxy/NAT idle timeout, resource pressure, agent crash | Kiểm tra channel, heartbeat và host health |

## 22. Bảo mật khi onboarding và vận hành managed nodes

Managed node là một kênh quản trị có quyền mạnh. Cần thiết kế các guardrails:

- Dùng IAM role/temporary credentials, tránh static access keys.
- EC2 role chỉ có quyền cần cho Systems Manager và workload.
- Tách role của node khỏi quyền operator.
- Giới hạn Session Manager theo tag, account, Region và document.
- Kiểm soát `ssm-user` và quyền root/administrator.
- Bật session logging tới CloudWatch Logs hoặc S3 khi yêu cầu audit.
- Dùng KMS cho session data nếu cần và quản lý key policy riêng.
- Bảo vệ activation code/ID như credential đăng ký.
- Không bake activation hoặc private credentials vào AMI.
- Cập nhật SSM Agent có kiểm soát và theo dõi rollout.
- Giới hạn quyền thay đổi DHMC, hybrid activations và instance profiles.
- Dùng VPC endpoints/private connectivity khi yêu cầu network isolation.
- Theo dõi CloudTrail cho StartSession, SendCommand, CreateActivation và thay đổi IAM/service settings.

Không cấp quyền chạy mọi SSM document cho mọi operator. Một document có thể thực thi shell/script dưới quyền mạnh trên managed node.

## 23. Cập nhật và duy trì SSM Agent

AWS thường xuyên phát hành SSM Agent mới để hỗ trợ feature và sửa lỗi. Nên tự động hóa update nhưng cần rollout có kiểm soát:

1. Dùng State Manager association hoặc Quick Setup để định kỳ cập nhật agent.
2. Chia fleet theo môi trường/nhóm canary.
3. Cập nhật trước một nhóm nhỏ.
4. Xác minh node vẫn Online và Session Manager/Run Command hoạt động.
5. Mở rộng rollout theo batch.
6. Theo dõi lỗi agent, CPU/memory và session failures.
7. Giữ quy trình rollback/reinstall cho image hoặc package lỗi.

Không cập nhật toàn bộ fleet cùng lúc nếu có yêu cầu availability cao. Agent version mới có thể thay đổi yêu cầu tương thích hoặc bổ sung hành vi; hãy test trên OS/image đại diện.

## 24. Tình huống thực tế

### Tình huống A — EC2 private subnet không xuất hiện

EC2 đang running, agent active, nhưng không có node trong Fleet Manager.

**Cách xử lý:** kiểm tra instance profile/DHMC, `ssm` endpoint DNS, outbound 443 và agent logs. Nếu không có NAT, tạo interface VPC endpoints phù hợp.

### Tình huống B — Instance profile đã gắn nhưng vẫn AccessDenied

Role có tên đúng nhưng policy không có quyền SSM cần thiết.

**Cách xử lý:** xác minh IAM role ARN thực tế trên instance, attach `AmazonSSMManagedInstanceCore` hoặc custom policy tương đương; kiểm tra permission boundary/SCP và credential refresh.

### Tình huống C — DHMC bật nhưng node không dùng role mặc định

EC2 có instance profile chứa `ssm:UpdateInstanceInformation`.

**Cách xử lý:** agent ưu tiên quyền instance profile. Nếu chủ đích dùng DHMC, loại quyền này khỏi profile theo hướng dẫn và kiểm tra IMDSv2/agent version.

### Tình huống D — Node hybrid không đăng ký

Activation đã tạo nhưng code hết hạn hoặc registration limit đã đạt.

**Cách xử lý:** tạo activation mới với expiry/limit phù hợp, lưu code an toàn và cài agent bằng ID/code mới. Node đã đăng ký trước đó không bị deregister chỉ vì activation hết hạn.

### Tình huống E — Session Manager không kết nối dù node Online

Agent đủ version nhưng endpoint `ssmmessages` không reachable.

**Cách xử lý:** kiểm tra PrivateLink endpoint, endpoint SG inbound 443, node egress, DNS Private DNS và endpoint policy. Không cần mở inbound SSH.

### Tình huống F — ssm-cli báo IMDS failure

Agent không lấy được EC2 instance identity/credentials.

**Cách xử lý:** kiểm tra IMDS options, host firewall, route/proxy và `no_proxy` cho `169.254.169.254`. Nếu dùng DHMC, xác minh IMDSv2 required.

### Tình huống G — Chỉ một Region không quản lý được EC2

DHMC đã bật ở Region A nhưng instance ở Region B.

**Cách xử lý:** cấu hình DHMC riêng ở Region B, kiểm tra IAM/service setting và endpoints của Region B.

### Tình huống H — Agent tự chuyển ConnectionLost sau vài phút

Host vẫn chạy nhưng agent không gửi heartbeat.

**Cách xử lý:** xem log agent, proxy/NAT idle timeout, resource pressure, credential expiration và TCP 443 reachability. Dùng VPC Flow Logs để tìm traffic bị REJECT nếu cần.

### Tình huống I — Session logging tới CloudWatch Logs thất bại

Node mở session được nhưng không ghi log.

**Cách xử lý:** kiểm tra Session Manager preferences, CloudWatch Logs endpoint/private connectivity, KMS nếu mã hóa và quyền ghi log của cấu hình logging. Đây là feature bổ sung, không phải điều kiện duy nhất để node registration thành công.

### Tình huống J — Activation code bị lộ trong CI logs

Một pipeline in toàn bộ output của `create-activation`.

**Cách xử lý:** tạo activation mới nếu code bị lộ, giới hạn registration, xóa/kiểm soát log theo quy trình, lưu code trong secret manager và tránh echo output trong pipeline.

## 25. Bài tập tình huống

### Bài A — Ba điều kiện managed node

Một EC2 có agent nhưng không có instance profile, DHMC hoặc credential source hợp lệ.

**Đáp án:** agent không thể xác thực với Systems Manager; cần cấp instance profile hoặc bật DHMC đúng điều kiện.

### Bài B — Private subnet không có NAT

EC2 cần Session Manager mà không đi Internet.

**Đáp án:** tạo interface endpoints cho SSM và ssmmessages, thêm ec2messages nếu agent/Region cần; cấu hình private DNS và endpoint security group.

### Bài C — Thiếu inbound 22

Operator muốn dùng Session Manager nhưng security group không mở SSH.

**Đáp án:** không cần mở inbound 22. Node tạo outbound HTTPS channels tới Systems Manager.

### Bài D — Agent cũ

Node dùng agent 2.3.100.0 nhưng cần port forwarding.

**Đáp án:** nâng lên tối thiểu 3.0.222.0 và tốt nhất dùng version hiện hành.

### Bài E — DHMC và instance profile

DHMC bật nhưng instance profile vẫn có `ssm:UpdateInstanceInformation`.

**Đáp án:** SSM Agent dùng credentials instance profile trước; loại permission đó khỏi profile nếu muốn sử dụng DHMC.

### Bài F — Hybrid role trust sai

Role không trust `ssm.amazonaws.com`.

**Đáp án:** cập nhật trust relationship cho Systems Manager service và xác minh service role có permissions cần thiết.

### Bài G — Node online nhưng Session Manager lỗi

Node có PingStatus Online nhưng `ssmmessages` endpoint bị chặn.

**Đáp án:** mở outbound 443 và endpoint SG inbound 443; kiểm tra DNS và endpoint policy.

### Bài H — Activation hết hạn

Activation hết hạn sau 24 giờ, nhưng một số node đã đăng ký.

**Đáp án:** node đã đăng ký vẫn managed; chỉ các node chưa đăng ký không thể dùng activation cũ.

### Bài I — ssm-cli báo endpoint phụ S3 fail

Node registration và SSM endpoint đều Success nhưng S3 check fail.

**Đáp án:** xác định document/feature có cần S3 không. Đây có thể là optional feature failure, không nhất thiết làm registration fail.

### Bài J — Managed node ở sai Region

Instance thuộc ap-southeast-1 nhưng operator đang xem Systems Manager ở us-east-1.

**Đáp án:** chọn đúng Region; managed node registration, endpoint và DHMC có phạm vi Region.

### Bài K — Người dùng được StartSession tới mọi instance

IAM policy cho `ssm:StartSession` trên `*`.

**Đáp án:** giới hạn theo instance ARN/tag, session document và account/Region; audit session và quản lý `ssm-user`.

### Bài L — Agent bị proxy chặn IMDS

Proxy nhận cả request tới `169.254.169.254`.

**Đáp án:** thêm bypass/no_proxy cho IMDS và cấu hình agent proxy theo hướng dẫn AWS; xác minh metadata credential retrieval.

## 26. Câu hỏi ôn tập

1. Managed node là gì?
2. Ba điều kiện nền tảng để một node được Systems Manager quản lý là gì?
3. EC2 running có đảm bảo node xuất hiện trong Fleet Manager không?
4. SSM Agent làm nhiệm vụ gì?
5. Vì sao cần hệ điều hành nằm trong danh sách hỗ trợ?
6. Instance profile cung cấp gì cho SSM Agent?
7. AmazonSSMManagedInstanceCore dùng cho principal nào?
8. DHMC giải quyết vấn đề gì?
9. DHMC yêu cầu phiên bản SSM Agent tối thiểu nào?
10. DHMC yêu cầu loại IMDS nào?
11. Vì sao phải bật DHMC ở từng Region?
12. ssm:UpdateInstanceInformation trong instance profile ảnh hưởng DHMC ra sao?
13. Hybrid activation dùng cho loại máy nào?
14. IAM service role của hybrid node cần trust principal nào?
15. Activation code và ID cần được bảo vệ vì sao?
16. Activation hết hạn có deregister node đã đăng ký không?
17. Managed node ID của hybrid node thường có prefix gì?
18. SSM Agent cần outbound port nào tới endpoint?
19. Các endpoint SSM cốt lõi thường gặp là gì?
20. Khi nào ec2messages có thể không cần?
21. Vì sao không cần inbound SSH/RDP cho Session Manager?
22. Interface endpoint security group cần cho phép inbound port nào?
23. Private DNS có vai trò gì khi dùng PrivateLink?
24. S3/KMS/CloudWatch Logs endpoints có luôn bắt buộc cho registration không?
25. ssm-cli get-diagnostics giúp kiểm tra gì?
26. PingStatus=ConnectionLost gợi ý điều gì?
27. Log SSM Agent trên Linux nằm ở đâu?
28. Log SSM Agent trên Windows nằm ở đâu?
29. Session Manager shell cơ bản yêu cầu agent version tối thiểu nào?
30. Port forwarding/SSH over Session Manager yêu cầu version nào?
31. Session Manager logging tới CloudWatch Logs yêu cầu version nào?
32. Vì sao cần phân biệt node IAM role và operator IAM policy?
33. ssm-user có quyền gì theo mặc định và vì sao cần review?
34. Vì sao cần cập nhật SSM Agent có kiểm soát?
35. Các thay đổi hybrid activation/pricing nào có hiệu lực trong năm 2026?

**Đáp án nhanh:** (1) máy được cấu hình để Systems Manager quản lý; (2) agent, IAM credentials/permissions, endpoint connectivity; (3) không; (4) nhận lệnh và gửi trạng thái; (5) support theo OS lifecycle; (6) temporary role credentials; (7) EC2 instance role; (8) tự cung cấp role ở cấp account/Region; (9) 3.2.582.0; (10) IMDSv2; (11) service settings theo Region; (12) agent ưu tiên instance profile và không dùng DHMC role; (13) on-prem/VM/cloud khác/edge được hỗ trợ; (14) ssm.amazonaws.com; (15) có thể đăng ký managed nodes; (16) không; (17) mi-; (18) TCP 443; (19) ssm, ssmmessages, ec2messages khi cần; (20) agent 3.3.40.0+ dùng ssmmessages khi có và một số Region mới không có ec2messages; (21) agent tạo outbound channel; (22) 443; (23) phân giải hostname chuẩn tới endpoint ENI; (24) không, tùy feature; (25) IMDS, registration, endpoint reachability; (26) agent/heartbeat/credential/network mất kết nối; (27) /var/log/amazon/ssm/; (28) %PROGRAMDATA%/Amazon/SSM/Logs/; (29) 2.3.68.0; (30) 3.0.222.0; (31) 3.0.284.0; (32) quyền agent khác quyền operator; (33) quyền quản trị/root tương ứng; (34) tránh lỗi feature và bảo mật; (35) hybrid console cũ deprecated 31/12/2026, advanced-instances tier bỏ 30/06/2026, pay-as-you-go Session Manager/Run Command hybrid từ 30/09/2026.

## 27. Checklist production

- [ ] OS, version và CPU architecture nằm trong danh sách Systems Manager hỗ trợ.
- [ ] AMI/custom image có SSM Agent đúng phiên bản.
- [ ] Agent service được enable và running sau reboot.
- [ ] EC2 có instance profile hoặc DHMC được cấu hình trong Region.
- [ ] DHMC nodes dùng IMDSv2 và agent từ 3.2.582.0.
- [ ] Instance profile không vô tình chặn việc dùng DHMC.
- [ ] Hybrid nodes có activation và IAM service role đúng trust.
- [ ] Activation code/ID không nằm trong Git, image hoặc CI logs.
- [ ] Role của node chỉ có permissions cần thiết.
- [ ] Operator policy tách biệt và giới hạn target/document.
- [ ] Node outbound TCP 443 tới SSM endpoints.
- [ ] VPC endpoint security group cho inbound 443 từ node.
- [ ] DNS/Private DNS, route, NACL và proxy được kiểm tra.
- [ ] ec2messages chỉ cấu hình khi Region/agent compatibility yêu cầu.
- [ ] Endpoint phụ S3/KMS/Logs được thêm theo feature thực tế.
- [ ] IMDS được bảo vệ nhưng SSM Agent vẫn truy cập được.
- [ ] Session Manager không phụ thuộc inbound SSH/RDP.
- [ ] ssm-user privileges được review.
- [ ] Session logging/KMS được bật theo audit requirements.
- [ ] Agent auto-update có canary và rollout theo batch.
- [ ] ssm-cli get-diagnostics được dùng trong onboarding/troubleshooting.
- [ ] Agent logs và CloudTrail có quy trình kiểm tra.
- [ ] Fleet được kiểm tra theo account, Region và PingStatus.
- [ ] Có runbook cho node missing, ConnectionLost và TargetNotConnected.
- [ ] Hybrid pricing/console changes năm 2026 được phản ánh trong kế hoạch vận hành.

## 28. Tổng kết

Một máy chỉ trở thành Systems Manager managed node khi đáp ứng đồng thời ba điều kiện: SSM Agent chạy trên OS được hỗ trợ, có IAM credentials/permissions phù hợp và kết nối được tới Systems Manager endpoints.

- EC2 có thể dùng instance profile hoặc Default Host Management Configuration.
- DHMC yêu cầu IMDSv2, SSM Agent từ 3.2.582.0 và được bật theo từng Region.
- Non-EC2 machines dùng hybrid activation và IAM service role; activation code/ID cần được bảo vệ.
- SSM Agent khởi tạo outbound HTTPS trên TCP 443; Session Manager không yêu cầu mở inbound SSH/RDP.
- Private subnet có thể dùng NAT egress hoặc PrivateLink interface endpoints như ssm và ssmmessages; ec2messages phụ thuộc agent version/Region.
- Session Manager có yêu cầu version, IAM và endpoint riêng cho shell, port forwarding, KMS và logging.
- ssm-cli, agent logs và AWS CLI giúp phân loại lỗi OS, agent, IAM, DNS, network và Region.
- Node role và operator permissions phải được tách biệt; ssm-user và session logging cần kiểm soát.
- Cập nhật agent và onboarding hybrid fleet phải có quy trình, audit và kế hoạch chi phí.

Khi thiết kế managed-node fleet, hãy kiểm tra OS, agent, identity và network như một chuỗi phụ thuộc. Một node online ổn định là nền tảng để Run Command, Session Manager, Patch Manager, Inventory và các công cụ vận hành khác hoạt động đáng tin cậy.

### Tài liệu AWS chính thức

1. Troubleshooting managed node availability: https://docs.aws.amazon.com/systems-manager/latest/userguide/fleet-manager-troubleshooting-managed-nodes.html
2. Supported operating systems and machine types: https://docs.aws.amazon.com/systems-manager/latest/userguide/operating-systems-and-machine-types.html
3. Working with SSM Agent: https://docs.aws.amazon.com/systems-manager/latest/userguide/ssm-agent.html
4. Checking SSM Agent status and starting the agent: https://docs.aws.amazon.com/systems-manager/latest/userguide/ssm-agent-status-and-restart.html
5. Viewing SSM Agent logs: https://docs.aws.amazon.com/systems-manager/latest/userguide/ssm-agent-logs.html
6. Troubleshooting managed node availability using ssm-cli: https://docs.aws.amazon.com/systems-manager/latest/userguide/troubleshooting-managed-nodes-using-ssm-cli.html
7. Configure instance permissions required for Systems Manager: https://docs.aws.amazon.com/systems-manager/latest/userguide/setup-instance-permissions.html
8. Managing EC2 instances automatically with Default Host Management Configuration: https://docs.aws.amazon.com/systems-manager/latest/userguide/fleet-manager-default-host-management-configuration.html
9. Session Manager prerequisites: https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-prerequisites.html
10. Troubleshooting Session Manager: https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-troubleshooting.html
11. Create a hybrid activation: https://docs.aws.amazon.com/systems-manager/latest/userguide/hybrid-activation-managed-nodes.html
12. Hybrid activation lifecycle and console changes: https://docs.aws.amazon.com/systems-manager/latest/userguide/activations.html
13. IAM service role for hybrid and multicloud: https://docs.aws.amazon.com/systems-manager/latest/userguide/hybrid-multicloud-service-role.html
14. Systems Manager VPC endpoints and PrivateLink: https://docs.aws.amazon.com/systems-manager/latest/userguide/setup-create-vpc.html
15. Troubleshooting SSM Agent: https://docs.aws.amazon.com/systems-manager/latest/userguide/troubleshooting-ssm-agent.html
16. SSM Agent release notes: https://github.com/aws/amazon-ssm-agent/releases
17. AWS Systems Manager pricing: https://aws.amazon.com/systems-manager/pricing/

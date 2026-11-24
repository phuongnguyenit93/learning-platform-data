# Tạo máy ảo trong subnet riêng và thiết lập truy cập quản trị

## Mục tiêu bài học

Sau bài học này, bạn có thể:

- Phân biệt subnet công khai và subnet riêng qua bảng định tuyến và khả năng nhận địa chỉ IP công khai.
- Thiết kế mạng để máy ảo không nhận kết nối quản trị trực tiếp từ Internet.
- Tạo máy ảo trong private subnet và cấp quyền quản trị theo nguyên tắc tối thiểu.
- Thiết lập truy cập quản trị qua dịch vụ quản lý phiên hoặc máy chủ trung gian.
- Xác minh đường mạng, quyền IAM, trạng thái máy ảo và khả năng truy cập; xử lý các lỗi thường gặp.

## 1. Kiến trúc cần triển khai

Máy ảo trong subnet riêng thường chạy ứng dụng, cơ sở dữ liệu hoặc thành phần nội bộ. Máy không cần địa chỉ IP công khai và không có đường định tuyến trực tiếp từ Internet đến giao diện mạng của nó. Người quản trị vẫn cần một kênh truy cập có xác thực, phân quyền và ghi nhận hoạt động.

Ví dụ trong bài dùng Amazon VPC và EC2. Các khái niệm tương đương có thể áp dụng cho Azure Virtual Network và Google Cloud VPC.

Kiến trúc mẫu:

~~~text
                         Internet
                            |
                     Internet Gateway
                            |
                  Public subnet 10.20.1.0/24
                     |              |
                 NAT Gateway    Bastion (tùy chọn)
                     |              |
              Private route table   | SSH chỉ từ VPN/IP quản trị
                     |              |
              Private subnet 10.20.11.0/24
                     |
                Private EC2 VM
                     |
          SSM Agent / ứng dụng nội bộ
                     |
       Interface VPC endpoints cho SSM
       hoặc egress qua NAT Gateway
~~~

Trong phương án ưu tiên, quản trị viên dùng AWS Systems Manager Session Manager để mở phiên đến máy ảo. Kết nối được khởi tạo từ SSM Agent trên máy ảo đi ra dịch vụ Systems Manager qua HTTPS; không cần mở cổng SSH hoặc RDP inbound. Bastion host là phương án thay thế khi có yêu cầu tương thích hoặc quy trình vận hành đặc thù.

## 2. Phân biệt subnet công khai và subnet riêng

Subnet không trở thành subnet công khai chỉ vì có tên chứa từ public. Điều quyết định là bảng định tuyến và cấu hình địa chỉ IP:

- Public subnet thường có route mặc định IPv4 đến Internet Gateway. Tài nguyên cần truy cập trực tiếp từ Internet còn phải có địa chỉ IPv4 công khai hoặc cơ chế địa chỉ công khai phù hợp và security rule cho phép.
- Private subnet không có route trực tiếp đến Internet Gateway. Máy ảo thường chỉ có private IP. Nếu cần kết nối outbound Internet, route mặc định có thể trỏ đến NAT Gateway đặt trong public subnet.
- Một private subnet cũng có thể không có default route ra Internet. Khi đó, chỉ các mạng nội bộ và dịch vụ qua VPC endpoint được truy cập theo những route đã cấu hình.

NAT Gateway cho phép tài nguyên trong private subnet khởi tạo kết nối outbound; nó không cung cấp kết nối inbound mới từ Internet đến máy ảo. Nếu máy ảo cần tải package hoặc cập nhật hệ điều hành, NAT Gateway là một lựa chọn. Nếu chỉ cần truy cập các dịch vụ AWS được hỗ trợ, VPC endpoint có thể giảm phụ thuộc vào Internet và NAT.

Không nên coi private subnet là ranh giới bảo mật duy nhất. Vẫn cần security group, network ACL, IAM, mã hóa, quản lý bản vá và kiểm soát outbound phù hợp.

## 3. Lập kế hoạch VPC, subnet và định tuyến

Với bài lab, có thể dùng sơ đồ địa chỉ sau:

| Thành phần | CIDR ví dụ | Vai trò |
|---|---|---|
| VPC | 10.20.0.0/16 | Không gian địa chỉ riêng cho workload |
| Public subnet | 10.20.1.0/24 | Đặt NAT Gateway hoặc bastion nếu cần |
| Private subnet | 10.20.11.0/24 | Đặt máy ảo không có public IP |
| VPC endpoint subnet | Dùng subnet riêng hoặc subnet ứng dụng theo thiết kế | Chứa network interface của interface endpoint |

CIDR chỉ là ví dụ. Trước khi tạo mạng, hãy đối chiếu với mạng tại văn phòng, VPN, VPC/VNet khác và mạng kết nối đối tác để tránh trùng dải địa chỉ.

Bảng định tuyến mẫu:

| Route table | Destination | Target |
|---|---|---|
| Public route table | 10.20.0.0/16 | local |
| Public route table | 0.0.0.0/0 | Internet Gateway |
| Private route table | 10.20.0.0/16 | local |
| Private route table | 0.0.0.0/0 | NAT Gateway, nếu cần outbound Internet |

Trong môi trường production, thường đặt NAT Gateway theo từng Availability Zone và định tuyến private subnet của AZ đến NAT Gateway cùng AZ để tăng tính sẵn sàng, giảm phụ thuộc liên vùng và kiểm soát chi phí truyền dữ liệu. Với bài lab một AZ, một NAT Gateway có thể đủ để minh họa nhưng tạo điểm lỗi đơn và vẫn phát sinh chi phí theo thời gian sử dụng cùng lưu lượng.

Nếu không dùng NAT, hãy tạo interface VPC endpoint cho các dịch vụ Systems Manager cần thiết. Thông thường cần xem xét endpoint cho Systems Manager và kênh nhắn tin của agent; endpoint cụ thể phụ thuộc phiên bản agent, region và dịch vụ được sử dụng. Bật private DNS khi phù hợp, đồng thời cho phép HTTPS 443 từ security group của máy ảo đến security group của endpoint. Nếu cần S3, CloudWatch Logs, KMS hoặc dịch vụ khác, bổ sung endpoint tương ứng theo luồng thực tế.

## 4. Tạo security group cho máy ảo

Security group là firewall trạng thái gắn với network interface. Với phương án Session Manager, máy ảo không cần inbound rule cho TCP 22 hoặc TCP 3389.

Một cấu hình tối thiểu có thể là:

| Hướng | Protocol/port | Nguồn hoặc đích | Mục đích |
|---|---|---|---|
| Inbound | Không có rule quản trị | — | Không nhận SSH/RDP trực tiếp |
| Outbound | TCP 443 | Security group của SSM interface endpoints | Cho SSM Agent kết nối dịch vụ quản lý |
| Outbound | Theo nhu cầu ứng dụng | Security group hoặc CIDR đích được phê duyệt | Kết nối database, API hoặc dịch vụ nội bộ |

Nếu dùng NAT để cập nhật hệ điều hành hoặc tải dependency, cần thiết kế outbound phù hợp với repository và dịch vụ cần truy cập. Tránh để outbound rộng hơn nhu cầu nếu tổ chức yêu cầu egress filtering.

Security group của endpoint cần cho phép inbound TCP 443 từ security group của máy ảo. DNS trong VPC phải hoạt động để máy ảo phân giải tên endpoint sang private IP. Security group là stateful nên lưu lượng phản hồi của kết nối được cho phép tự động; network ACL là stateless và cần quy tắc cả chiều đi lẫn chiều về, bao gồm ephemeral ports khi cần.

## 5. Chuẩn bị quyền quản trị bằng Systems Manager

Để Session Manager quản trị EC2, cần chuẩn bị cả quyền của máy ảo lẫn quyền của người vận hành.

**Quyền của máy ảo:**

1. Tạo IAM role dành cho EC2.
2. Gắn instance profile chứa role đó.
3. Cấp policy được AWS hỗ trợ cho Systems Manager, thường dùng AmazonSSMManagedInstanceCore làm điểm bắt đầu.
4. Đảm bảo SSM Agent đã cài đặt và đang chạy. Nhiều Amazon Machine Image phổ biến có agent sẵn, nhưng cần xác minh theo hệ điều hành và image đã chọn.
5. Đảm bảo máy ảo có kết nối outbound HTTPS đến các endpoint Systems Manager qua NAT hoặc interface VPC endpoints.

**Quyền của người quản trị:**

- Người dùng hoặc role quản trị cần được cấp quyền bắt đầu, tiếp tục và kết thúc phiên theo phạm vi instance và session document được cho phép.
- Dùng IAM Identity Center hoặc cơ chế định danh tập trung, MFA và nhóm quyền theo vai trò.
- Giới hạn quyền theo tag, account, environment hoặc resource ARN để tránh mọi người có thể truy cập mọi máy.
- Bật ghi log phiên vào CloudWatch Logs hoặc S3 nếu chính sách vận hành yêu cầu; cân nhắc mã hóa bằng KMS và quyền đọc log tách biệt.

Không gắn quyền quản trị rộng cho instance role chỉ để sửa lỗi kết nối. Instance role là danh tính của workload; quyền người dùng mở phiên là danh tính của người vận hành. Hai loại quyền này cần được quản lý riêng.

## 6. Tạo máy ảo trong private subnet

Trước khi chạy lệnh, chuẩn bị các giá trị:

- AMI ID tương thích với region và kiến trúc.
- ID private subnet.
- Security group không mở SSH/RDP inbound.
- Instance profile có quyền Systems Manager.
- Instance type phù hợp workload và ngân sách.

Ví dụ AWS CLI:

~~~bash
aws ec2 run-instances   --image-id ami-xxxxxxxxxxxxxxxxx   --instance-type t3.small   --subnet-id subnet-private-xxxxxxxx   --security-group-ids sg-private-xxxxxxxx   --iam-instance-profile Name=ec2-ssm-instance-profile   --no-associate-public-ip-address   --metadata-options HttpTokens=required   --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=private-admin-vm},{Key=Environment,Value=lab}]'
~~~

Thay các placeholder bằng ID thật trong tài khoản và region của bài lab. Lệnh yêu cầu không gắn public IPv4 cho instance và bắt buộc sử dụng IMDSv2 để truy cập instance metadata. AMI phải có SSM Agent tương thích và cấu hình mạng đến được endpoint Systems Manager.

Sau khi tạo, lấy instance ID từ kết quả lệnh. Chờ trạng thái instance là running và kiểm tra status checks đã đạt trước khi mở phiên quản trị.

## 7. Mở phiên quản trị qua Session Manager

Từ máy quản trị đã đăng nhập AWS CLI bằng IAM role hoặc profile được cấp quyền:

~~~bash
aws ssm describe-instance-information   --filters Key=InstanceIds,Values=i-0123456789abcdef0
~~~

Kết quả cần cho thấy instance đã được Systems Manager nhận diện là managed node và trạng thái kết nối trực tuyến. Sau đó mở phiên:

~~~bash
aws ssm start-session --target i-0123456789abcdef0
~~~

Máy quản trị cần có AWS CLI và Session Manager plugin theo yêu cầu của môi trường. Khi phiên mở thành công, người quản trị có shell trên máy ảo theo quyền hệ điều hành được cấu hình. Trên Linux, có thể xác minh:

~~~bash
hostname
whoami
ip addr
ip route
systemctl status amazon-ssm-agent
~~~

Lệnh trạng thái agent có thể khác theo bản phân phối hoặc cách cài đặt. Trên Windows, có thể dùng Session Manager hoặc Fleet Manager theo khả năng của dịch vụ. Nếu cần truy cập RDP đến một máy Windows riêng, có thể dùng port forwarding qua session theo chính sách cho phép thay vì mở cổng 3389 ra Internet.

Session Manager không tự động biến mọi người mở phiên thành root hoặc Administrator. Hãy xác định tài khoản hệ điều hành, quyền nâng cao, quy trình sudo/UAC và kiểm soát lệnh theo chính sách tổ chức.

## 8. Phương án bastion host khi cần SSH/RDP

Một số hệ thống cũ hoặc công cụ vận hành yêu cầu giao thức SSH/RDP trực tiếp. Khi đó có thể dùng bastion host làm điểm trung gian:

1. Đặt bastion trong public subnet hoặc trong mạng quản trị riêng có VPN.
2. Nếu bastion có public IP, chỉ cho phép SSH/RDP từ dải IP VPN hoặc IP quản trị đã phê duyệt. Không mở cổng quản trị đến 0.0.0.0/0.
3. Security group của máy ảo private chỉ cho phép cổng quản trị từ security group của bastion, không cho phép từ toàn bộ Internet.
4. Dùng khóa hoặc chứng thư ngắn hạn, MFA ở lớp truy cập, tài khoản cá nhân và ghi log phiên.
5. Cập nhật hệ điều hành bastion, giám sát đăng nhập, giới hạn outbound và triển khai dự phòng nếu bastion là thành phần quan trọng.

Ưu điểm của bastion là tương thích với SSH/RDP và công cụ quản trị hiện có. Đổi lại, đội vận hành phải vá lỗi, bảo vệ thông tin xác thực, giám sát và duy trì tính sẵn sàng của bastion. Một bastion đơn lẻ có thể trở thành điểm lỗi và mục tiêu tấn công tập trung.

Với Session Manager, đường quản trị không cần inbound SSH/RDP đến máy ảo. Với bastion, máy ảo vẫn nằm trong private subnet nhưng cần rule inbound từ bastion. Không nên mở đồng thời nhiều đường quản trị nếu không có nhu cầu và kiểm soát rõ ràng.

## 9. Ánh xạ sang Azure và Google Cloud

| Nền tảng | Máy ảo private | Kênh quản trị thường dùng | Kết nối outbound |
|---|---|---|---|
| AWS | EC2 trong private subnet, không public IP | Systems Manager Session Manager; bastion khi cần | NAT Gateway hoặc VPC endpoints |
| Azure | VM trong subnet của VNet, không gắn public IP | Azure Bastion, hoặc giải pháp quản trị riêng theo chính sách | NAT Gateway, Azure Firewall hoặc private endpoints tùy dịch vụ |
| Google Cloud | Compute Engine VM không có external IP | IAP TCP forwarding kết hợp IAM và OS Login | Cloud NAT hoặc Private Google Access/private connectivity tùy đích |

Tên dịch vụ và các bước cấu hình khác nhau, nhưng nguyên tắc giống nhau: máy ảo dùng private IP, quyền quản trị được cấp qua danh tính tập trung, firewall chỉ mở luồng cần thiết và outbound được kiểm soát. Hãy dùng tài liệu của đúng nền tảng để xác minh IAM role, firewall source range, agent, endpoint và logging.

## 10. Xác minh và xử lý sự cố

Sau khi tạo máy ảo, kiểm tra cả cấu hình mạng lẫn trạng thái quản trị.

**Xác minh thuộc subnet và không có public IP:**

~~~bash
aws ec2 describe-instances   --instance-ids i-0123456789abcdef0   --query 'Reservations[].Instances[].{State:State.Name,PrivateIP:PrivateIpAddress,PublicIP:PublicIpAddress,Subnet:SubnetId,Vpc:VpcId,Profile:IamInstanceProfile.Arn}'
~~~

PublicIP cần rỗng hoặc không được trả về. Subnet và VPC phải đúng với thiết kế. Tiếp tục kiểm tra route table gắn với subnet để xác nhận không có route trực tiếp đến Internet Gateway.

**Xác minh quyền và agent:**

- Instance có instance profile đúng.
- IAM role chứa policy cần thiết.
- SSM Agent đang chạy và instance xuất hiện trong danh sách managed nodes.
- DNS phân giải endpoint đúng; route và security group cho phép HTTPS 443.
- Người quản trị có quyền bắt đầu session và session được ghi log theo yêu cầu.

**Một số lỗi thường gặp:**

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Instance không xuất hiện trong Systems Manager | Thiếu instance profile, policy hoặc agent chưa chạy | Kiểm tra IAM role, trạng thái agent và log agent |
| Managed node offline | Không có route đến endpoint, DNS lỗi hoặc outbound 443 bị chặn | Kiểm tra NAT/VPC endpoint, private DNS, security group và network ACL |
| Người dùng không mở được session | IAM caller thiếu quyền hoặc bị giới hạn bởi session policy | Kiểm tra quyền StartSession, resource scope và document |
| SSH đến private VM thất bại | Không có đường VPN/bastion hoặc security group không cho phép nguồn | Kiểm tra route, peering/VPN và rule từ bastion security group |
| VM không cập nhật được package | Không có outbound đến repository hoặc thiếu DNS/NAT/egress rule | Kiểm tra route, NAT, DNS và chính sách egress |
| Phiên quản trị mở được nhưng không có quyền nâng cao | Tài khoản hệ điều hành không được cấp sudo/Administrator | Kiểm tra nhóm hệ điều hành và chính sách nâng quyền |

Không khắc phục bằng cách mở SSH/RDP từ Internet hoặc cấp Administrator/root không giới hạn. Hãy tìm đúng lớp gây lỗi: định danh, agent, DNS, route, firewall hay quyền hệ điều hành.

## 11. Checklist bàn giao

- [ ] VPC/VNet có CIDR không xung đột với mạng kết nối.
- [ ] Private subnet không có route trực tiếp đến Internet Gateway.
- [ ] Máy ảo có private IP và không có public IP.
- [ ] Security group không mở SSH/RDP inbound từ Internet.
- [ ] Route outbound chỉ đáp ứng nhu cầu cập nhật và truy cập dịch vụ.
- [ ] Instance profile và IAM role được cấp đúng quyền Systems Manager.
- [ ] SSM Agent hoạt động và có kết nối đến endpoint cần thiết.
- [ ] Người quản trị dùng định danh cá nhân, MFA và quyền tối thiểu.
- [ ] Session được ghi log và lưu theo chính sách.
- [ ] Đã thử truy cập quản trị, xác minh IP/route và kiểm tra lỗi thường gặp.
- [ ] Đã ghi nhận AMI, instance type, subnet, security group, IAM role và chủ sở hữu vận hành.

## Kết luận

Máy ảo trong private subnet giảm bề mặt tấn công bằng cách không nhận kết nối quản trị trực tiếp từ Internet. Một thiết kế hoàn chỉnh cần phối hợp subnet và route table, private IP, security group, outbound qua NAT hoặc endpoint, danh tính IAM và kênh quản trị có ghi log. Session Manager là lựa chọn thuận tiện khi nền tảng hỗ trợ; bastion vẫn có thể đáp ứng yêu cầu SSH/RDP nhưng cần được bảo vệ và vận hành như một thành phần hạ tầng quan trọng.
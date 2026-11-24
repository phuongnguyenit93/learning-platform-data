# Cấp phát compute bằng console, CLI, SDK và API

Điện toán đám mây cho phép tạo máy ảo, cụm container và môi trường serverless theo nhu cầu. Để đưa một ứng dụng vào chạy, nhóm vận hành cần chọn đúng loại tài nguyên, cấu hình mạng và lưu trữ, gắn quyền truy cập, khởi tạo phần mềm rồi theo dõi trạng thái cấp phát. Các nhà cung cấp thường cho phép thực hiện những việc này qua giao diện console, dòng lệnh (CLI), bộ thư viện lập trình (SDK) hoặc API.

Bốn cách tiếp cận dùng chung một nền tảng điều khiển và thường có thể tạo ra cùng một loại tài nguyên. Điểm khác nhau nằm ở cách người dùng mô tả yêu cầu, mức độ tự động hóa, khả năng tích hợp vào ứng dụng và cách kiểm soát thay đổi. Hiểu rõ từng cách giúp chọn đúng công cụ cho thao tác thử nghiệm, công việc lặp lại và hệ thống triển khai quy mô lớn.

Sau bài học, bạn có thể:

- Giải thích vai trò và điểm mạnh của console, CLI, SDK và API.
- Xác định các thông tin cần có trước khi tạo tài nguyên compute.
- Thực hiện quy trình cấp phát máy ảo qua giao diện hoặc dòng lệnh.
- Dùng SDK để tích hợp thao tác cấp phát vào chương trình.
- Hiểu vòng đời một yêu cầu API, xác thực, phản hồi và xử lý lỗi.
- Thiết kế quy trình có thể lặp lại, kiểm tra được, an toàn và có khả năng thu hồi tài nguyên.

## 1. Cấp phát compute gồm những gì?

Cấp phát (provisioning) là quá trình yêu cầu nền tảng tạo, cấu hình hoặc thu hồi tài nguyên điện toán. Với một máy ảo, thao tác tạo máy thường chỉ là một phần của quy trình. Một máy có thể chuyển sang trạng thái đang khởi tạo trước khi hệ điều hành khởi động và ứng dụng sẵn sàng nhận lưu lượng.

Một yêu cầu cấp phát máy ảo thường cần xác định:

| Thành phần | Nội dung cần quyết định | Ví dụ |
|---|---|---|
| Vị trí | Region, zone hoặc vùng khả dụng | Khu vực gần người dùng và dữ liệu |
| Image | Hệ điều hành hoặc image đã chuẩn bị | Linux LTS có sẵn runtime cần thiết |
| Kích thước | CPU, RAM, GPU và đặc tính phần cứng | 4 vCPU, 16 GiB RAM |
| Lưu trữ | Loại ổ đĩa, dung lượng, mã hóa và chính sách xóa | SSD 50 GiB, mã hóa khi lưu |
| Mạng | VPC/VNet, subnet, IP và quy tắc firewall | Subnet riêng, chỉ cho phép HTTPS qua load balancer |
| Danh tính | Role, service account hoặc managed identity | Quyền đọc một bucket dữ liệu cụ thể |
| Khởi tạo | Script, image tùy chỉnh hoặc cấu hình triển khai | Cài agent giám sát và tải ứng dụng |
| Quản trị | Nhãn, tags, owner, môi trường và thời hạn | Environment=dev, Owner=platform |
| Vòng đời | Tự động dừng, xóa, sao lưu và thay thế | Xóa máy thử nghiệm sau 8 giờ |

Với container, đối tượng được cấp phát có thể là cluster, node pool, task hoặc workload. Với serverless, người vận hành thường khai báo function, cấu hình runtime, bộ nhớ, thời gian chạy tối đa, quyền truy cập và nguồn kích hoạt. Mặc dù giao diện khác nhau, các nguyên tắc về vị trí, tài nguyên, mạng, danh tính, cấu hình và vòng đời vẫn tương tự.

### Chọn mô hình compute trước khi chọn công cụ

- **Máy ảo (VM):** phù hợp khi cần kiểm soát hệ điều hành, tiến trình nền, cấu hình máy hoặc phần mềm cài trực tiếp trên máy.
- **Container:** phù hợp khi ứng dụng đã được đóng gói thành image và cần triển khai nhất quán trên một cụm hoặc nền tảng điều phối.
- **Serverless:** phù hợp với tác vụ theo sự kiện hoặc tải biến động khi muốn nhà cung cấp quản lý phần lớn máy chủ nền.

Console, CLI, SDK và API là các cách điều khiển những dịch vụ này. Chọn công cụ không thay thế bước phân tích workload và yêu cầu vận hành.

## 2. Bốn cách làm việc với nền tảng đám mây

### Console: thao tác qua giao diện web

Console là giao diện đồ họa do nhà cung cấp cung cấp. Người dùng đăng nhập, chọn dịch vụ, điền biểu mẫu, xem cấu hình và xác nhận thao tác. Console thường phù hợp khi khám phá dịch vụ, kiểm tra tài nguyên hiện có hoặc tạo một môi trường thử nghiệm.

**Ưu điểm**

- Hiển thị lựa chọn và mô tả của nhà cung cấp ngay tại nơi cấu hình.
- Dễ quan sát trạng thái, cảnh báo và các thông số liên quan.
- Hữu ích cho người mới học hoặc thao tác hiếm khi thực hiện.

**Hạn chế**

- Dễ bỏ sót một trường cấu hình hoặc tạo các môi trường hơi khác nhau qua từng lần thao tác.
- Khó lặp lại chính xác cho nhiều tài khoản, vùng hoặc môi trường.
- Khó đưa trực tiếp vào pipeline tự động hóa và quy trình review bằng mã nguồn.

Console vẫn có thể là nơi kiểm tra kết quả của một quy trình tự động. Tuy nhiên, với thao tác lặp lại, nhóm nên lưu cấu hình dưới dạng mã hoặc dùng công cụ tự động hóa có quản lý trạng thái.

### CLI: điều khiển bằng lệnh

CLI (Command-Line Interface) là chương trình chạy trong terminal. Người dùng truyền tham số, tệp cấu hình và lệnh con để tạo, xem, cập nhật hoặc xóa tài nguyên.

Ví dụ, AWS CLI có thể tạo một EC2 instance bằng lệnh aws ec2 run-instances. Các CLI khác có lệnh tương tự nhưng cú pháp, tên tài nguyên và quy tắc xác thực sẽ khác.

**Ưu điểm**

- Lệnh có thể lưu thành script và chạy lại trong pipeline.
- Có thể kết hợp với công cụ xử lý JSON, shell và hệ thống CI/CD.
- Thường hỗ trợ tùy chọn xem trước hoặc kiểm tra trạng thái trước khi thay đổi.

**Hạn chế**

- Cần biết cú pháp, phiên bản CLI và định dạng tham số.
- Script thiếu kiểm tra lỗi có thể tạo tài nguyên trùng hoặc để lại tài nguyên dở dang.
- Cấu hình phụ thuộc môi trường terminal, profile, region và biến môi trường.

CLI phù hợp với thao tác vận hành có quy trình rõ ràng, công việc quản trị lặp lại và các bước triển khai trong CI/CD.

### SDK: điều khiển từ chương trình

SDK (Software Development Kit) là bộ thư viện của nhà cung cấp cho một ngôn ngữ lập trình. Chương trình có thể gọi hàm để tạo máy, truy vấn trạng thái, gắn nhãn, thay đổi cấu hình hoặc xử lý sự kiện.

Ví dụ, ứng dụng Python có thể dùng SDK để tạo máy ảo sau khi một bản ghi công việc được duyệt. SDK thường cung cấp lớp đối tượng, kiểm tra kiểu dữ liệu, phân trang, retry và xử lý xác thực thuận tiện hơn so với tự ghép HTTP request.

**Ưu điểm**

- Tích hợp thao tác cloud vào backend, công cụ nội bộ hoặc nền tảng tự phục vụ.
- Có thể áp dụng logic nghiệp vụ, kiểm tra đầu vào và ghi audit ngay trong chương trình.
- Dễ kết hợp với hàng đợi, cơ sở dữ liệu và hệ thống điều phối.

**Hạn chế**

- Phải quản lý phiên bản thư viện, dependency và tương thích runtime.
- Mã ứng dụng cần xử lý timeout, retry, trạng thái bất đồng bộ và lỗi một phần.
- Logic cấp phát có thể trở nên khó kiểm thử nếu gắn chặt với hệ thống bên ngoài.

SDK phù hợp khi một ứng dụng cần tương tác với tài nguyên cloud như một phần của luồng nghiệp vụ.

### API: giao tiếp trực tiếp qua giao thức

API (Application Programming Interface) là giao diện mà dịch vụ cung cấp để hệ thống khác gửi yêu cầu và nhận kết quả. Với dịch vụ cloud, API thường dùng HTTPS và dữ liệu JSON hoặc một định dạng đặc thù của nhà cung cấp. CLI và SDK phần lớn cũng gọi các API nền tảng này.

Một yêu cầu API thường có:

- Địa chỉ dịch vụ và thao tác cần thực hiện.
- Thông tin xác thực hoặc chữ ký số của yêu cầu.
- Phần header như loại nội dung, phiên bản API và mã tương quan.
- Phần thân mô tả tài nguyên cần tạo hoặc thay đổi.

**Ưu điểm**

- Cho phép tích hợp từ bất kỳ ngôn ngữ hoặc môi trường nào có thể gửi HTTP request.
- Cung cấp quyền kiểm soát chi tiết đối với request, header và phản hồi.
- Hữu ích khi xây dựng một lớp tích hợp chung hoặc khi SDK chưa hỗ trợ tính năng mới.

**Hạn chế**

- Người phát triển phải hiểu cơ chế ký request, token, phiên bản API và định dạng lỗi.
- Phải tự xử lý phân trang, retry, timeout, polling và tương thích API.
- Một lỗi nhỏ trong việc ký hoặc mã hóa tham số có thể khiến request bị từ chối.

API phù hợp khi cần tích hợp mức thấp, hỗ trợ tính năng chưa có trong SDK hoặc xây dựng một adapter độc lập với ngôn ngữ lập trình.

### So sánh nhanh

| Tiêu chí | Console | CLI | SDK | API |
|---|---|---|---|---|
| Cách tương tác | Biểu mẫu và nút trên web | Lệnh trong terminal | Hàm và đối tượng trong mã | HTTP request hoặc giao thức dịch vụ |
| Bắt đầu sử dụng | Dễ | Cần học cú pháp | Cần biết ngôn ngữ và thư viện | Cần hiểu giao thức và xác thực |
| Lặp lại thao tác | Thấp nếu làm thủ công | Tốt khi có script | Tốt khi có chương trình | Tốt khi có hệ thống gọi API |
| Tích hợp CI/CD | Gián tiếp | Rất phù hợp | Phù hợp | Phù hợp |
| Quan sát kết quả | Trực quan | Qua output và truy vấn | Qua response và log | Qua status code và response |
| Kiểm soát chi tiết | Theo trường giao diện | Theo tham số lệnh | Theo chức năng SDK | Chi tiết nhất ở mức request |
| Trường hợp phù hợp | Khám phá, thao tác thủ công | Vận hành và pipeline | Tự động hóa trong ứng dụng | Tích hợp đặc thù, adapter |

Không có một công cụ tốt nhất cho mọi tình huống. Có thể dùng console để khám phá một cấu hình, sau đó chuyển quy trình đã hiểu rõ thành CLI, SDK hoặc mã hạ tầng để triển khai nhất quán.

## 3. Chuẩn bị trước khi cấp phát

Một lệnh tạo máy chạy thành công chưa bảo đảm ứng dụng sẽ an toàn hoặc hoạt động đúng. Trước khi gọi công cụ, cần chuẩn bị các thông tin và kiểm tra những điều kiện liên quan.

### Xác định yêu cầu tài nguyên

Ghi lại nhu cầu CPU, RAM, GPU, dung lượng lưu trữ, băng thông mạng, hệ điều hành, kiến trúc CPU và thời gian chạy. Dựa vào đặc điểm tải để chọn loại máy phù hợp. Nếu chưa có số liệu, hãy bắt đầu bằng cấu hình nhỏ trong môi trường thử nghiệm, đo mức sử dụng rồi điều chỉnh.

Với workload có GPU, cần xác minh loại GPU, dung lượng bộ nhớ thiết bị, số lượng GPU trên mỗi máy, kết nối giữa các GPU và quota ở vùng dự kiến. Với workload container, phải xác định cả tài nguyên của node và request/limit của từng workload.

### Chọn image và phiên bản hệ điều hành

Image là khuôn mẫu dùng để khởi tạo máy. Có thể dùng image chuẩn của nhà cung cấp, image do tổ chức duy trì hoặc image đã được đóng gói sẵn ứng dụng. Cần xác minh:

- Image thuộc đúng hệ điều hành, kiến trúc và phiên bản còn được hỗ trợ.
- Image đến từ nguồn đáng tin cậy và có quy trình vá bảo mật.
- Driver GPU, agent quản trị và runtime cần thiết tương thích.
- Image có chứa dữ liệu hoặc khóa bí mật không phù hợp để nhân bản hay không.

Không nên dùng một image không rõ nguồn gốc chỉ vì nó có sẵn phần mềm mong muốn. Trong môi trường sản xuất, nên chuẩn hóa image, ghi nhận phiên bản và cập nhật theo quy trình.

### Thiết kế mạng và quyền truy cập

Chọn VPC/VNet, subnet, route table, firewall/security group và cách truy cập quản trị. Máy chủ backend thường không cần địa chỉ IP công khai. Nếu cần nhận lưu lượng Internet, nên đặt máy sau load balancer hoặc gateway có kiểm soát.

Quy tắc mạng nên giới hạn nguồn, đích và cổng theo nhu cầu. Ví dụ, cổng SSH không nên mở cho toàn Internet; có thể dùng VPN, bastion host hoặc dịch vụ quản trị từ xa được kiểm soát. Dịch vụ ứng dụng chỉ nên nhận lưu lượng từ load balancer hoặc các thành phần được phép.

Gắn role hoặc service account với quyền tối thiểu cần thiết. Không nhúng access key dài hạn vào user data, image, script hoặc mã nguồn. Ưu tiên danh tính workload và cơ chế cấp thông tin xác thực tạm thời của nhà cung cấp.

### Chuẩn bị lưu trữ và khởi tạo

Xác định loại ổ đĩa, dung lượng, hiệu năng, mã hóa, snapshot và chính sách xóa khi máy bị xóa. Dữ liệu cần tồn tại lâu dài nên được đặt trên dịch vụ lưu trữ độc lập hoặc volume có vòng đời phù hợp.

Startup script hoặc cloud-init có thể cài gói, tạo cấu hình và khởi động dịch vụ khi máy lần đầu khởi động. Script cần có thể chạy an toàn, ghi log, kiểm tra lỗi và tránh lưu bí mật ở dạng văn bản rõ. Với môi trường cần độ lặp lại cao, nên đóng gói phần mềm vào image hoặc container thay vì cài đặt quá nhiều bước mỗi lần boot.

### Kiểm tra quota, vùng và chi phí

Xác nhận tài khoản có quyền tạo tài nguyên, quota còn đủ và loại máy có thể cấp phát ở region/zone đã chọn. Ước tính chi phí của máy, ổ đĩa, IP công khai, snapshot, truyền dữ liệu và dịch vụ phụ trợ. Đặt tags hoặc labels ngay khi tạo để theo dõi chủ sở hữu, môi trường, dự án và trung tâm chi phí.

## 4. Cấp phát bằng console

Tên menu thay đổi theo nhà cung cấp, nhưng quy trình tạo máy ảo thường gồm các bước sau:

1. Đăng nhập vào console bằng tài khoản hoặc danh tính công việc được cấp quyền.
2. Chọn đúng tài khoản dự án và region/zone.
3. Mở dịch vụ máy ảo và chọn tạo instance.
4. Chọn image, phiên bản hệ điều hành và loại máy dựa trên CPU/RAM/GPU cần thiết.
5. Cấu hình ổ đĩa, dung lượng, mã hóa và chính sách xóa.
6. Chọn mạng, subnet, địa chỉ IP và quy tắc firewall.
7. Gắn role hoặc service account có quyền tối thiểu.
8. Cấu hình phương thức quản trị, startup script và metadata cần thiết.
9. Gắn tags/labels để quản lý và phân bổ chi phí.
10. Xem lại trang tổng hợp cấu hình, xác nhận chi phí và tạo máy.
11. Theo dõi trạng thái đến khi máy sẵn sàng, sau đó kiểm tra đăng nhập, dịch vụ và log khởi tạo.

Trang tổng hợp trước khi tạo rất quan trọng: hãy kiểm tra lại region, subnet, IP công khai, quyền truy cập và ổ đĩa. Một lựa chọn mặc định trong biểu mẫu có thể mở cổng mạng rộng hoặc tạo máy ở vùng có chi phí cao hơn dự kiến.

Console thường hiển thị trạng thái như Pending, Provisioning, Running hoặc Failed. Tên và ý nghĩa chính xác tùy dịch vụ. Trạng thái Running chỉ nói máy đã bật; nó chưa chứng minh ứng dụng đã sẵn sàng. Hãy kiểm tra health check hoặc endpoint của ứng dụng trước khi chuyển lưu lượng.

## 5. Cấp phát bằng CLI

CLI phù hợp khi muốn lưu lệnh, chạy lại theo môi trường hoặc đưa thao tác vào pipeline. Cần cài CLI chính thức, kiểm tra phiên bản, cấu hình profile và xác thực bằng danh tính được phép.

### Ví dụ tạo máy EC2 bằng AWS CLI

Ví dụ dưới đây minh họa việc tạo một EC2 instance trên AWS. Các giá trị ami-..., subnet-..., sg-... và tên instance profile là placeholder; phải thay bằng tài nguyên hợp lệ trong tài khoản và region của bạn. Đây là ví dụ Bash.

~~~bash
aws sts get-caller-identity

aws ec2 run-instances \
  --image-id ami-0123456789abcdef0 \
  --instance-type t3.medium \
  --subnet-id subnet-0123456789abcdef0 \
  --security-group-ids sg-0123456789abcdef0 \
  --iam-instance-profile Name=app-instance-profile \
  --metadata-options HttpEndpoint=enabled,HttpTokens=required \
  --block-device-mappings 'DeviceName=/dev/xvda,Ebs={VolumeSize=30,VolumeType=gp3,Encrypted=true,DeleteOnTermination=true}' \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=compute-demo},{Key=Environment,Value=dev},{Key=Owner,Value=platform}]' \
  --count 1
~~~

Trước tiên, aws sts get-caller-identity giúp xác nhận danh tính hiện tại. Lệnh run-instances yêu cầu image, loại máy, subnet, security group và instance profile. Metadata options buộc sử dụng IMDSv2; block device mapping tạo ổ đĩa mã hóa; tag specification gắn nhãn cho máy.

Trong môi trường thực tế, nên truyền cấu hình qua tệp JSON đã được review hoặc biến môi trường được quản lý an toàn. Tránh đặt token hay mật khẩu trực tiếp trong câu lệnh vì lịch sử shell và log pipeline có thể lưu lại nội dung đó.

### Theo dõi và quản lý máy sau khi tạo

Lệnh tạo máy có thể trả về trước khi hệ điều hành sẵn sàng. Dùng lệnh truy vấn trạng thái để xác nhận:

~~~bash
aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=compute-demo" \
  --query "Reservations[].Instances[].[InstanceId,State.Name,PrivateIpAddress]" \
  --output table

aws ec2 wait instance-status-ok \
  --instance-ids i-0123456789abcdef0
~~~

describe-instances giúp kiểm tra ID, trạng thái và địa chỉ IP riêng. wait instance-status-ok đợi đến khi kiểm tra trạng thái instance thành công hoặc hết thời gian chờ. Sau đó vẫn cần kiểm tra ứng dụng bằng health endpoint hoặc công cụ giám sát.

Khi môi trường thử nghiệm không còn cần thiết, hãy dừng hoặc xóa máy theo chính sách dữ liệu:

~~~bash
aws ec2 terminate-instances \
  --instance-ids i-0123456789abcdef0
~~~

Terminate có thể xóa các volume được cấu hình DeleteOnTermination; volume được giữ lại và snapshot có thể tiếp tục phát sinh phí. Luôn kiểm tra chính sách lưu trữ và sao lưu trước khi xóa tài nguyên.

### Viết script CLI có kiểm soát

Một script triển khai nên thực hiện các bước: xác nhận danh tính, kiểm tra tham số, xác minh quota và mạng, tạo tài nguyên, chờ trạng thái, kiểm tra health, ghi nhận ID và xử lý lỗi. Nếu một bước thất bại, script cần lưu thông tin để có thể tiếp tục hoặc thu hồi tài nguyên đã tạo.

Không nên dùng tên tài nguyên làm định danh duy nhất nếu tên đó có thể trùng. Hãy lưu ID do nền tảng trả về, gắn nhãn nhận diện lần triển khai và kiểm tra tài nguyên hiện có trước khi tạo mới.

## 6. Cấp phát bằng SDK

SDK giúp chương trình gọi dịch vụ cloud bằng các hàm có cấu trúc. Ví dụ dưới đây dùng Python và boto3 để tạo EC2 instance. Cần cài thư viện trong môi trường chạy bằng lệnh pip install boto3, cấu hình AWS credentials bằng profile hoặc role và thay các ID placeholder.

~~~python
import boto3
from botocore.exceptions import BotoCoreError, ClientError

region = "ap-southeast-1"
ec2 = boto3.client("ec2", region_name=region)

try:
    response = ec2.run_instances(
        ImageId="ami-0123456789abcdef0",
        InstanceType="t3.medium",
        MinCount=1,
        MaxCount=1,
        SubnetId="subnet-0123456789abcdef0",
        SecurityGroupIds=["sg-0123456789abcdef0"],
        IamInstanceProfile={"Name": "app-instance-profile"},
        MetadataOptions={
            "HttpEndpoint": "enabled",
            "HttpTokens": "required",
        },
        BlockDeviceMappings=[
            {
                "DeviceName": "/dev/xvda",
                "Ebs": {
                    "VolumeSize": 30,
                    "VolumeType": "gp3",
                    "Encrypted": True,
                    "DeleteOnTermination": True,
                },
            }
        ],
        TagSpecifications=[
            {
                "ResourceType": "instance",
                "Tags": [
                    {"Key": "Name", "Value": "compute-demo"},
                    {"Key": "Environment", "Value": "dev"},
                    {"Key": "Owner", "Value": "platform"},
                ],
            }
        ],
        ClientToken="compute-demo-deployment-2026-01",
    )
    instance_id = response["Instances"][0]["InstanceId"]
    print(f"Created instance: {instance_id}")

    waiter = ec2.get_waiter("instance_status_ok")
    waiter.wait(InstanceIds=[instance_id])
    print("Instance status checks passed")

except (ClientError, BotoCoreError) as error:
    print(f"Provisioning failed: {error}")
    raise
~~~

Trong ví dụ:

- Client được tạo cho một region cụ thể.
- run_instances nhận cấu hình máy, mạng, danh tính, metadata, ổ đĩa và tags.
- ClientToken là mã chống tạo trùng cho yêu cầu có tính idempotency trong khoảng thời gian dịch vụ quy định. Khi thiết kế thật, token cần gắn với một lần triển khai logic và được lưu ổn định để retry không tạo máy mới ngoài ý muốn.
- Waiter đợi kiểm tra trạng thái của máy. Ứng dụng vẫn cần bước kiểm tra health riêng.
- Lỗi từ dịch vụ hoặc tầng SDK được ghi nhận và đưa lên cho luồng gọi xử lý.

Đoạn mã chỉ minh họa luồng cấp phát. Một dịch vụ nội bộ hoàn chỉnh cần xác thực đầu vào, giới hạn số lượng máy, kiểm tra quyền người yêu cầu, ghi audit, áp dụng timeout và có chiến lược dọn dẹp nếu triển khai thất bại giữa chừng.

### Quản lý lỗi và retry trong SDK

Không phải lỗi nào cũng nên retry:

- Lỗi xác thực hoặc thiếu quyền thường cần sửa cấu hình danh tính.
- Tham số sai hoặc image không hợp lệ cần sửa đầu vào.
- Vượt quota cần yêu cầu tăng quota hoặc chọn cấu hình khác.
- Hết năng lực tạm thời có thể thử lại với backoff và jitter nếu thao tác an toàn.
- Timeout không có nghĩa thao tác thất bại: tài nguyên có thể đã được tạo nhưng phản hồi bị mất. Trước khi gửi lại, hãy truy vấn theo client token, tag hoặc mã triển khai để xác định kết quả.

Retry một yêu cầu tạo tài nguyên mà không có idempotency có thể tạo nhiều máy giống nhau. Đối với thao tác không idempotent, phải thiết kế khóa chống trùng hoặc quy trình đối soát trạng thái.

## 7. Cấp phát qua API

API là nền tảng của console, CLI và SDK. Khi cần gọi trực tiếp, chương trình phải tuân theo giao thức xác thực và định dạng request mà nhà cung cấp quy định.

Một quy trình API thường có các bước:

1. Lấy thông tin xác thực ngắn hạn từ identity provider hoặc cơ chế workload identity.
2. Xây dựng request gồm endpoint, method, header và body.
3. Ký request hoặc đính kèm access token theo yêu cầu dịch vụ.
4. Gửi HTTPS request và đặt timeout phù hợp.
5. Đọc HTTP status code cùng phần thân phản hồi.
6. Nếu thao tác bất đồng bộ, lấy operation ID và truy vấn trạng thái đến khi hoàn tất.
7. Ghi nhận request ID, operation ID và kết quả để audit hoặc điều tra.

### Ví dụ cấu trúc yêu cầu tạo máy

Các API của nhà cung cấp không dùng chung một endpoint hoặc schema. JSON dưới đây là ví dụ minh họa theo kiểu API quản lý compute, không phải endpoint có thể gọi trực tiếp:

~~~http
POST /v1/projects/project-demo/instances
Authorization: Bearer <short-lived-access-token>
Content-Type: application/json
Idempotency-Key: deploy-2026-001
~~~

~~~json
{
  "name": "app-worker-01",
  "location": {
    "region": "region-a",
    "zone": "zone-a"
  },
  "machine": {
    "image": "linux-lts-approved",
    "cpu": 4,
    "memoryGiB": 16
  },
  "network": {
    "subnet": "private-app-subnet",
    "publicIp": false,
    "firewallPolicy": "app-worker-policy"
  },
  "identity": {
    "serviceAccount": "app-worker"
  },
  "storage": [
    {
      "sizeGiB": 50,
      "encrypted": true,
      "deleteWithInstance": true
    }
  ],
  "labels": {
    "environment": "dev",
    "owner": "platform"
  }
}
~~~

API có thể trả 200 OK hoặc 201 Created nếu tài nguyên được tạo đồng bộ; với thao tác dài, dịch vụ có thể trả 202 Accepted cùng operation ID. Client cần đọc tài liệu API để biết chính xác trạng thái nào có nghĩa là đã tạo xong.

Ví dụ phản hồi bất đồng bộ:

~~~json
{
  "operationId": "op-7f12a",
  "status": "PENDING",
  "resource": "instances/app-worker-01"
}
~~~

Client dùng operation ID để truy vấn trạng thái. Khi hoàn tất, phản hồi có thể chứa ID tài nguyên, địa chỉ mạng hoặc lỗi chi tiết. Không nên coi 202 Accepted là ứng dụng đã sẵn sàng.

### Mã trạng thái và cách xử lý

| HTTP status | Ý nghĩa thường gặp | Hướng xử lý |
|---|---|---|
| 200/201 | Yêu cầu thành công hoặc tài nguyên đã tạo | Đọc response và xác minh trạng thái tài nguyên |
| 202 | Đã nhận yêu cầu, xử lý tiếp ở nền | Lưu operation ID và polling theo hướng dẫn |
| 400 | Request sai cấu trúc hoặc tham số | Sửa schema và dữ liệu đầu vào |
| 401 | Thiếu hoặc token không hợp lệ | Làm mới thông tin xác thực |
| 403 | Danh tính không có quyền | Kiểm tra IAM policy và phạm vi quyền |
| 404 | Tài nguyên hoặc endpoint không tồn tại | Kiểm tra ID, region và phiên bản API |
| 409 | Xung đột trạng thái hoặc tài nguyên trùng | Đọc chi tiết xung đột và đối soát trạng thái |
| 429 | Bị giới hạn tốc độ hoặc quota | Backoff, giảm tốc độ gọi hoặc yêu cầu tăng quota |
| 500/503 | Lỗi phía dịch vụ hoặc dịch vụ tạm thời không sẵn sàng | Retry có giới hạn nếu thao tác an toàn; theo dõi request ID |

Không nên retry vô hạn. Dùng exponential backoff với jitter, giới hạn tổng thời gian thử và phân biệt lỗi có thể khắc phục với lỗi cấu hình. Nếu request tạo máy bị timeout, hãy kiểm tra trạng thái tài nguyên trước khi gửi lại.

## 8. Từ thao tác đơn lẻ đến tự động hóa có thể lặp lại

Console, CLI, SDK và API đều có thể tạo tài nguyên. Để vận hành ổn định, nhóm cần một quy trình xác định rõ đầu vào, trạng thái mong muốn, quyền thay đổi và cách xử lý khi thất bại.

### Imperative và declarative

**Imperative (mệnh lệnh)** mô tả hành động cần chạy: tạo máy, gắn ổ đĩa, thêm rule mạng, rồi khởi động dịch vụ. CLI và SDK thường được sử dụng theo cách này.

**Declarative (khai báo)** mô tả trạng thái mong muốn: cần một máy với image, kích thước, mạng và tags xác định. Công cụ sẽ so sánh trạng thái hiện tại với trạng thái khai báo rồi tạo, cập nhật hoặc thay thế tài nguyên để đạt trạng thái mong muốn.

Infrastructure as Code (IaC) là cách lưu cấu hình hạ tầng thành mã có thể review, quản lý phiên bản và triển khai lặp lại. Terraform, OpenTofu và các công cụ IaC khác có thể dùng API của nhà cung cấp để thực hiện thay đổi. IaC hữu ích khi một môi trường gồm nhiều tài nguyên phụ thuộc như mạng, IAM, máy ảo, load balancer và giám sát.

| Cách làm | Mô tả | Điểm cần chú ý |
|---|---|---|
| Console thủ công | Người vận hành thay đổi từng trường | Ghi lại cấu hình và kiểm tra drift |
| Script CLI | Chuỗi lệnh theo thứ tự | Kiểm tra exit code, retry và dọn dẹp |
| Chương trình SDK | Logic cấp phát nằm trong ứng dụng | Tách logic nghiệp vụ, kiểm thử và audit |
| API trực tiếp | Tự xây request tới dịch vụ | Xác thực, schema, phiên bản và retry |
| IaC khai báo | Mô tả trạng thái mong muốn | Review plan, quản lý state và phát hiện drift |

Với tài nguyên dùng lâu dài, IaC thường giúp kiểm soát thay đổi tốt hơn. Với tác vụ ngắn hạn hoặc phản ứng theo sự kiện, CLI/SDK/API có thể phù hợp hơn. Các cách làm có thể kết hợp, miễn là xác định một nguồn quản lý trạng thái rõ ràng để tránh hai quy trình cùng thay đổi một tài nguyên.

### Một pipeline cấp phát mẫu

~~~mermaid
flowchart TD
    A["Nhận yêu cầu compute"] --> B["Xác thực người yêu cầu và tham số"]
    B --> C["Kiểm tra quota, chính sách và chi phí"]
    C --> D["Tạo tài nguyên qua CLI, SDK, API hoặc IaC"]
    D --> E["Chờ operation hoàn tất"]
    E --> F["Kiểm tra health và cấu hình bảo mật"]
    F --> G{"Đạt tiêu chí?"}
    G -- "Có" --> H["Ghi nhận ID, tags và audit"]
    G -- "Không" --> I["Thu hồi hoặc rollback theo chính sách"]
    I --> J["Ghi lỗi và thông báo hệ thống vận hành"]
~~~

Một pipeline cần lưu lại người yêu cầu, cấu hình đã duyệt, phiên bản mã, ID tài nguyên, thời điểm tạo và kết quả kiểm tra. Các bước này giúp truy vết khi có lỗi và hỗ trợ phân bổ chi phí.

## 9. Bảo mật trong quy trình cấp phát

Cấp phát là thao tác có quyền tạo hạ tầng và có thể làm phát sinh chi phí. Vì vậy, danh tính gọi công cụ và cấu hình tài nguyên phải được kiểm soát.

- **Least privilege:** chỉ cấp quyền cần thiết cho loại tài nguyên, dự án và vùng được phép.
- **Temporary credentials:** ưu tiên token ngắn hạn, role hoặc workload identity thay cho khóa dài hạn.
- **Network isolation:** chỉ mở cổng cần thiết; dùng subnet riêng và điểm truy cập quản trị có kiểm soát.
- **Secure metadata:** bật cơ chế metadata an toàn mà nền tảng hỗ trợ; giới hạn quyền truy cập metadata từ workload.
- **Encryption:** mã hóa volume, snapshot và dữ liệu truyền qua mạng theo chính sách tổ chức.
- **Image governance:** chỉ dùng image đã được phê duyệt, quét lỗ hổng và cập nhật bản vá.
- **Audit trail:** ghi người gọi, hành động, request ID, cấu hình và thời điểm thay đổi.
- **Secret handling:** lưu bí mật trong secret manager; không ghi vào user data, tag hoặc log.
- **Policy guardrails:** chặn cấu hình không phù hợp như IP công khai ngoài ý muốn, ổ đĩa không mã hóa hoặc loại máy vượt ngân sách.

Nên phân tách quyền tạo tài nguyên, quyền thay đổi mạng và quyền xóa dữ liệu. Trong pipeline, chỉ cho phép triển khai tới đúng project/account và environment được chỉ định.

## 10. Theo dõi vòng đời và chi phí

Tài nguyên compute có thể tồn tại lâu hơn mục đích ban đầu nếu không có quy tắc thu hồi. Mỗi tài nguyên nên có owner, project, environment và thời hạn hoặc chính sách vòng đời.

Các chỉ số cần theo dõi gồm:

- Số lượng máy theo trạng thái, vùng và loại máy.
- CPU, RAM, GPU, lưu trữ và mạng sử dụng thực tế.
- Thời gian từ lúc gửi yêu cầu đến khi máy hoặc ứng dụng sẵn sàng.
- Tỷ lệ cấp phát thành công, lỗi quota, lỗi quyền và lỗi thiếu năng lực.
- Chi phí theo dự án, chủ sở hữu, môi trường và đơn vị công việc.
- Tài nguyên không gắn owner, máy nhàn rỗi, ổ đĩa mồ côi và IP không còn sử dụng.

Với môi trường phát triển, có thể tự động dừng máy ngoài giờ hoặc xóa tài nguyên sau thời hạn. Với môi trường sản xuất, cần kết hợp lịch bảo trì, sao lưu, yêu cầu sẵn sàng và quy trình phê duyệt.

### Dừng và xóa là hai thao tác khác nhau

**Stop/deallocate** thường giải phóng năng lực tính toán nhưng giữ lại một phần tài nguyên như ổ đĩa. Chi phí compute có thể dừng, nhưng lưu trữ, IP tĩnh hoặc dịch vụ liên quan vẫn có thể tính phí.

**Terminate/delete** xóa đối tượng máy. Volume, snapshot, IP và dữ liệu có thể được giữ hoặc xóa tùy chính sách. Trước khi xóa, cần xác định dữ liệu nào phải lưu, backup có thể khôi phục không và các tài nguyên phụ thuộc có bị ảnh hưởng không.

Tự động hóa thu hồi nên có allowlist/denylist, thời gian ân hạn và log đầy đủ. Không xóa chỉ dựa trên việc CPU thấp trong một khoảng thời gian ngắn; một máy có thể đang chờ tác vụ theo lịch hoặc phục vụ dự phòng.

## 11. Sự cố thường gặp khi cấp phát

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra và xử lý |
|---|---|---|
| Access denied / 403 | Role thiếu quyền hoặc policy chặn | Kiểm tra danh tính, scope và audit log |
| Image không tìm thấy | Sai region, ID hoặc image đã bị gỡ | Xác minh image ở đúng tài khoản và vùng |
| Insufficient capacity | Vùng không còn năng lực cho loại máy | Thử zone khác, loại máy thay thế hoặc reservation |
| Quota exceeded | Đã đạt giới hạn tài khoản | Kiểm tra quota, thu hồi tài nguyên dư hoặc yêu cầu tăng |
| Máy chạy nhưng không SSH được | Route, firewall, IP hoặc khóa truy cập sai | Kiểm tra đường mạng và dùng kênh quản trị được phê duyệt |
| Máy chạy nhưng ứng dụng chưa sẵn sàng | Startup script lỗi, thiếu dependency hoặc health check thất bại | Xem system log, cloud-init log và log ứng dụng |
| Lệnh timeout nhưng máy vẫn tồn tại | Request đã được xử lý nhưng phản hồi bị mất | Tra cứu theo client token, tag hoặc operation ID trước khi retry |
| Chi phí cao bất thường | Máy nhàn rỗi, loại máy quá lớn hoặc tài nguyên phụ trợ tồn tại | Xem cost report, utilization và tài nguyên mồ côi |

Khi điều tra, ghi lại request ID, operation ID, resource ID, thời gian và region. Những thông tin này giúp nhóm vận hành tra cứu log phía nhà cung cấp.

## 12. Ví dụ tổng hợp: tạo worker cho môi trường thử nghiệm

Một nhóm cần tạo một máy worker để xử lý hàng đợi trong môi trường phát triển. Máy cần 4 vCPU, 16 GiB RAM, ổ đĩa mã hóa, không có IP công khai và chỉ truy cập được từ subnet ứng dụng.

Quy trình có thể triển khai như sau:

1. Nhóm ứng dụng gửi yêu cầu gồm mục đích, owner, thời hạn và tải dự kiến.
2. Hệ thống kiểm tra người yêu cầu có quyền tạo worker trong project dev.
3. Pipeline xác minh quota, image đã phê duyệt, subnet riêng và security group.
4. Máy được tạo bằng CLI hoặc SDK với role chỉ đọc queue và ghi kết quả vào storage đích.
5. Startup script cài agent giám sát, lấy cấu hình không bí mật và khởi động worker.
6. Pipeline đợi máy sẵn sàng rồi gọi health check. Nếu kiểm tra thất bại, tài nguyên được đánh dấu lỗi và xử lý theo chính sách thu hồi.
7. Tags ghi Environment=dev, Owner=team-app, Purpose=queue-worker và ExpiresAt để hệ thống dọn dẹp có thể nhận diện.
8. Sau khi thử nghiệm kết thúc, worker được dừng hoặc xóa; dữ liệu cần giữ được chuyển sang storage độc lập.

Với một máy thử nghiệm, console có thể đủ để kiểm tra lần đầu. Khi nhóm cần tạo nhiều worker theo yêu cầu hoặc theo lịch, cùng cấu hình nên được chuyển thành script CLI, chương trình SDK hoặc module IaC đã review.

## 13. Checklist trước và sau khi cấp phát

**Trước khi tạo**

- [ ] Đã chọn mô hình compute và cấu hình phù hợp với workload.
- [ ] Đã xác minh image, kiến trúc, phiên bản và nguồn gốc.
- [ ] Đã kiểm tra region, zone, quota và nguồn cung.
- [ ] Đã xác định subnet, firewall, IP và phương thức quản trị.
- [ ] Đã gắn role/service account với quyền tối thiểu.
- [ ] Đã cấu hình lưu trữ, mã hóa và chính sách dữ liệu.
- [ ] Đã ước tính chi phí và gắn tags/labels quản trị.
- [ ] Đã chuẩn bị startup script hoặc image triển khai có thể kiểm tra.

**Sau khi tạo**

- [ ] Đã lưu resource ID, request ID và operation ID.
- [ ] Đã xác nhận trạng thái máy và health check của ứng dụng.
- [ ] Đã kiểm tra log khởi tạo, quyền truy cập và kết nối mạng.
- [ ] Đã xác nhận giám sát, cảnh báo và phân bổ chi phí.
- [ ] Đã xác định người sở hữu và thời hạn vòng đời.
- [ ] Đã kiểm tra quy trình stop, delete và khôi phục dữ liệu.

## 14. Bài tập vận dụng

Một nhóm cần tạo 20 máy worker giống nhau trong hai vùng để xử lý tác vụ theo đợt. Các máy chỉ chạy vài giờ, cần truy cập một hàng đợi và ghi kết quả vào object storage. Nhóm muốn giảm thao tác thủ công và tránh tạo máy trùng khi pipeline bị timeout.

1. Bạn sẽ chọn console, CLI, SDK, API hay IaC làm cách triển khai chính? Giải thích theo tần suất, khả năng lặp lại và tích hợp pipeline.
2. Liệt kê các tham số phải chuẩn hóa trước khi cấp phát 20 máy.
3. Thiết kế cách chống tạo trùng khi yêu cầu tạo máy bị timeout nhưng dịch vụ có thể đã xử lý thành công.
4. Đề xuất quyền IAM, cấu hình mạng và cách cấp thông tin xác thực cho worker.
5. Xác định cách theo dõi health, chi phí và thu hồi máy sau khi đợt xử lý kết thúc.

Gợi ý: cân nhắc khai báo cấu hình chung, dùng ID triển khai hoặc idempotency key ổn định, kiểm tra trạng thái trước khi retry, giới hạn quyền theo tài nguyên và gắn tags có owner/thời hạn. Cần tính cả thời gian khởi động, lưu trữ và truyền dữ liệu giữa hai vùng.

## Kết luận

Console giúp khám phá và thao tác trực quan; CLI phù hợp với script và pipeline; SDK đưa khả năng cấp phát vào chương trình; API cho phép tích hợp ở mức giao thức. Dù dùng cách nào, quy trình vẫn cần xác định cấu hình compute, mạng, lưu trữ, danh tính, chi phí và vòng đời. Khi tự động hóa, hãy kiểm tra trạng thái sau mỗi thao tác, thiết kế idempotency và retry an toàn, lưu audit, kiểm tra health rồi thu hồi tài nguyên đúng chính sách.

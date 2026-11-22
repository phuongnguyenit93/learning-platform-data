# Instance Metadata Service và yêu cầu IMDSv2 trên Amazon EC2

**Instance Metadata Service (IMDS)** là dịch vụ dành cho mỗi Amazon EC2 instance, cho phép phần mềm chạy bên trong instance lấy thông tin về chính máy đó: instance ID, Region, Availability Zone, một số thông tin mạng, và khi máy được gắn **IAM instance profile**, thông tin xác thực tạm thời của IAM role tương ứng. Vì endpoint này có thể cấp credentials cho workload, việc quản lý cách truy cập IMDS là một phần quan trọng của bảo mật EC2.

**IMDSv2** dùng token phiên để truy cập metadata. Khi đặt **HttpTokens = required**, EC2 chỉ chấp nhận yêu cầu IMDSv2 có token hợp lệ, qua đó giảm một số nguy cơ lạm dụng endpoint metadata so với IMDSv1. Tuy nhiên, bảo vệ IMDS không chỉ dừng ở việc bật một tùy chọn: ứng dụng và SDK cần tương thích, chính sách IAM phải giới hạn quyền, và hệ thống container cần được kiểm tra đường đi mạng đến endpoint.

Bài học thuộc chương **Máy chủ EC2** của mô-đun **CLOUD_PROVIDERS_AWS**. Kiến thức IMDS giúp người học khám phá hệ sinh thái AWS từ Region/AZ, IAM, VPC đến compute, storage, database, tích hợp và serverless; thiết kế ứng dụng có phân quyền an toàn, giám sát và khả năng phục hồi tốt, đồng thời tránh chi phí vận hành phát sinh do cấu hình hoặc triển khai sai.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Nêu **IMDS** cung cấp những gì và phân biệt metadata, user data, instance profile với credentials của IAM role.
2. Giải thích sự khác biệt giữa **IMDSv1** và **IMDSv2**, vai trò của HTTP PUT, session token, thời hạn sống (TTL) và HTTP GET.
3. Cấu hình EC2 bắt buộc dùng IMDSv2 với **HttpTokens = required**, đồng thời hiểu **HttpEndpoint**, **HttpPutResponseHopLimit**, **HttpProtocolIpv6** và **InstanceMetadataTags**.
4. Giải thích thứ tự ưu tiên giữa cấu hình instance/launch template, mặc định của tài khoản theo Region và AMI.
5. Sử dụng AWS CLI và câu lệnh HTTP an toàn để kiểm tra cấu hình/truy cập IMDSv2, tránh in credentials nhạy cảm ra log.
6. Lập kế hoạch chuyển từ IMDSv1 sang IMDSv2 cho đội máy EC2, ASG, SDK, agent và container mà không làm gián đoạn ứng dụng.
7. Chẩn đoán những tình huống thường gặp như **401 Unauthorized**, timeout khi lấy token và thiếu credentials của role.

## 2. IMDS là gì và được dùng trong trường hợp nào?

IMDS là endpoint gắn với **từng EC2 instance**, có thể được truy cập từ hệ điều hành hoặc tiến trình được phép trên instance. Địa chỉ IPv4 quen thuộc là **169.254.169.254** (địa chỉ link-local), với các đường dẫn dưới **/latest/**. Đây không phải endpoint public thông thường trên Internet; thông tin trả về mô tả **instance đang thực hiện yêu cầu**, không phải toàn bộ tài khoản AWS.

| Nhóm thông tin | Ví dụ nội dung | Ứng dụng thực tế |
|---|---|---|
| Danh tính instance | Instance ID, AMI ID, loại instance | Gắn log/metric với đúng máy, chẩn đoán khởi động |
| Vị trí triển khai | Region, Availability Zone, thông tin instance identity document | Định vị môi trường và cấu hình endpoint dịch vụ |
| Mạng | Local IPv4, MAC, các thông tin network interface được hỗ trợ | Quan sát mạng và cấu hình agent |
| User data | Dữ liệu khởi tạo được cung cấp lúc launch | Script bootstrap, cài đặt/cấu hình ban đầu |
| IAM role credentials | Thông tin xác thực tạm thời của role gắn qua instance profile | SDK/CLI gọi S3, DynamoDB, CloudWatch... theo IAM role |
| Instance tags khi bật tùy chọn | Một số tag của instance qua metadata | Cấu hình và phân loại workload nếu được phê duyệt |

**Lưu ý:** không phải mọi trường dữ liệu hoặc tính năng đều tồn tại trên mọi hệ máy, image hoặc phiên bản; một số mục tùy cấu hình. Cần kiểm tra tài liệu phiên bản metadata đang dùng.

### 2.1. Metadata khác gì user data?

**Metadata** là thông tin do EC2 cung cấp về instance. **User data** là nội dung do người triển khai truyền vào khi tạo instance, thường dùng để bootstrap. Chúng đều có thể được truy cập từ trong instance theo những đường dẫn tương ứng, vì vậy **không đặt password, API key hoặc bí mật lâu dài trực tiếp trong user data**. Với dữ liệu nhạy cảm, nên dùng dịch vụ quản lý secret phù hợp kết hợp IAM role.

### 2.2. IMDS và IAM instance profile

Để EC2 gọi API AWS theo quyền của một role, thông thường bạn gắn **IAM role vào instance thông qua instance profile**. AWS cấp credentials tạm thời cho instance; SDK hoặc AWS CLI có thể tự lấy và làm mới các credentials đó qua provider chain khi không có nguồn credentials ưu tiên khác.

~~~mermaid
flowchart LR
    APP["Ứng dụng / AWS SDK<br/>trên EC2"] -->|"1. Lấy token IMDSv2"| IMDS["IMDS của instance"]
    IMDS -->|"2. Metadata / role credentials"| APP
    PROFILE["IAM instance profile + role"] -. "Quyền role được cấp cho EC2" .-> IMDS
    APP -->|"3. API request ký bằng<br/>credentials tạm thời"| S3["S3 / DynamoDB / CloudWatch"]
    S3 -->|"4. IAM và resource policy<br/>đánh giá quyền"| APP
~~~

Token IMDSv2 chỉ dùng để **truy vấn metadata**; nó **không phải** AWS access key, không thể dùng thay cho chữ ký SigV4 và **không tự cấp quyền IAM**. Quyền gọi API vẫn đến từ role, các policy áp dụng và ngữ cảnh của yêu cầu.

**Thực hành tốt:** để AWS SDK/CLI tự quản lý vòng đời credentials qua **default credential provider chain** và instance role. Không tự đọc rồi ghi các access key/secret key/session token lấy từ metadata vào file, log hoặc mã nguồn.

## 3. So sánh IMDSv1 và IMDSv2

| Tiêu chí | IMDSv1 | IMDSv2 |
|---|---|---|
| Cách truy cập metadata | HTTP GET trực tiếp | HTTP PUT lấy token, sau đó GET/HEAD kèm token |
| Token | Không có | Session token riêng của instance |
| Thời hạn token | Không áp dụng | Từ **1 đến 21.600 giây** (tối đa 6 giờ) |
| Có thể yêu cầu từ phía instance | Có, nếu instance cho phép | Có, nếu IMDS endpoint bật |
| Header bắt buộc để đọc metadata | Không cần header token | **X-aws-ec2-metadata-token** |
| Biện pháp giảm nguy cơ SSRF/proxy | Ít cơ chế ràng buộc ở lớp IMDS | PUT riêng, token phiên, từ chối một số kiểu proxy header và có response hop limit |
| Bắt buộc ở cấu hình EC2 nào | **HttpTokens = optional** vẫn có thể chấp nhận | **HttpTokens = required** từ chối yêu cầu không có token |

Nếu instance đặt **HttpTokens = optional**, cả IMDSv1 và IMDSv2 có thể hoạt động. **HttpTokens = required** mới thực sự **bắt buộc IMDSv2**; chỉ việc phần mềm chọn dùng IMDSv2 không có nghĩa IMDSv1 đã bị vô hiệu hóa ở instance.

### 3.1. Vì sao IMDSv2 an toàn hơn?

Một dạng rủi ro điển hình là **Server-Side Request Forgery (SSRF)**: ứng dụng web bị lừa gửi HTTP request đến địa chỉ mà kẻ tấn công chỉ định. Nếu web server có thể truy cập IMDS, metadata hoặc credentials từ role có thể bị tiết lộ khi lớp ứng dụng có lỗ hổng và không có biện pháp bảo vệ bổ sung.

IMDSv2 thêm nhiều trở ngại đối với những cách lạm dụng phổ biến:

- Bắt đầu bằng **HTTP PUT** để lấy token, rồi mới gửi GET với header token; một đường SSRF chỉ cho phép GET đơn giản khó đáp ứng quy trình này hơn.
- Endpoint token từ chối PUT chứa **X-Forwarded-For**, giảm một số hình thức khai thác qua reverse proxy không cấu hình phù hợp.
- Token gắn với instance tạo ra nó và chỉ có hiệu lực trong thời hạn đã chọn; không thể sử dụng token đó từ một instance khác.
- **HttpPutResponseHopLimit** giới hạn số hop IP đối với **phản hồi của yêu cầu PUT token**, có thể giúp hạn chế các luồng đi qua proxy/container ngoài dự tính.

**Không hiểu sai:** IMDSv2 là biện pháp **phòng vệ theo chiều sâu**. Mã độc hoặc tiến trình đã có quyền thực hiện PUT và GET từ trong instance có thể lấy token và truy vấn metadata. Vì vậy vẫn phải vá lỗi SSRF/RCE, hạn chế truy cập đến metadata từ tiến trình không cần thiết, đặt quyền IAM tối thiểu và cô lập workload.

## 4. Cơ chế token IMDSv2 từng bước

### 4.1. Đường đi request

~~~mermaid
sequenceDiagram
    participant App as Tiến trình trên EC2
    participant IMDS as 169.254.169.254
    App->>IMDS: PUT /latest/api/token<br/>TTL header
    IMDS-->>App: Session token
    App->>IMDS: GET /latest/meta-data/instance-id<br/>X-aws-ec2-metadata-token
    IMDS-->>App: Instance ID
    Note over App,IMDS: Hết TTL thì tạo token mới
~~~

**Bước 1 — lấy token.** Chạy lệnh bên dưới **trực tiếp trong một EC2 Linux instance được phép thử**. Ví dụ lưu token trong biến shell để không in token ra terminal:

~~~bash
TOKEN=$(curl -fsS --noproxy '*' \
  -X PUT 'http://169.254.169.254/latest/api/token' \
  -H 'X-aws-ec2-metadata-token-ttl-seconds: 21600')
~~~

**Bước 2 — đọc metadata bằng token.**

~~~bash
curl -fsS --noproxy '*' \
  -H "X-aws-ec2-metadata-token: $TOKEN" \
  'http://169.254.169.254/latest/meta-data/instance-id'
~~~

**Bước 3 — tái sử dụng trong thời gian hợp lệ.** Cùng token có thể phục vụ các GET/HEAD tiếp theo trong thời gian TTL. Sau khi hết hạn phải lấy token khác bằng PUT. TTL là thời hạn phiên IMDSv2, **không phải thời hạn IAM role credentials**.

Các lệnh dùng **/latest/api/token** để lấy token và **/latest/meta-data/** để đọc; khi viết mã không nên tự thay đường dẫn token bằng một version date khác. Dùng **--noproxy '*'** để yêu cầu nội bộ không vô tình đi qua proxy HTTP được cấu hình trong môi trường.

### 4.2. Hành vi khi thiếu token

Khi **HttpTokens = required**, một GET tới metadata không có token hợp lệ sẽ nhận **HTTP 401 Unauthorized**. Bạn có thể kiểm tra mã trạng thái trong môi trường lab:

~~~bash
curl -sS --noproxy '*' -o /dev/null -w '%{http_code}\n' \
  'http://169.254.169.254/latest/meta-data/instance-id'
~~~

Nếu trả **401**, endpoint đang từ chối kiểu GET không có token. Để xác minh IMDSv2 hoạt động, tiếp tục thử PUT token và GET hợp lệ. Nếu **timeout** hoặc kết nối không được, không nên kết luận ngay instance “bắt buộc IMDSv2”: có thể IMDS bị tắt, mạng/container bị chặn, proxy được cấu hình sai hoặc có vấn đề ở hệ điều hành.

### 4.3. IPv6 endpoint

IMDS có thể dùng địa chỉ IPv6 **[fd00:ec2::254]** trên **Nitro-based EC2 instance ở subnet hỗ trợ IPv6**, khi **HttpProtocolIpv6 = enabled**. IPv6 endpoint không tự bật chỉ vì subnet là IPv6-only; phải cấu hình rõ. Khi bật endpoint IPv6, endpoint IPv4 vẫn được bật nếu IMDS được cho phép. Cơ chế token IMDSv2 trên IPv6 tương tự IPv4.

Ví dụ lệnh GET sử dụng URL IPv6 sẽ có dạng **http://[fd00:ec2::254]/latest/meta-data/instance-id**, cũng cần header token thích hợp. Không phải mọi EC2 instance đều có thể bật endpoint này.

## 5. Các tùy chọn cấu hình IMDS

| Metadata option | Giá trị quan trọng | Ý nghĩa và khuyến nghị |
|---|---|---|
| **HttpEndpoint** | **enabled / disabled** | Bật/tắt IMDS; tắt sẽ làm ứng dụng/agent cần metadata hoặc role credentials không thể truy cập theo cách đó |
| **HttpTokens** | **optional / required** | **required** là cấu hình bắt buộc IMDSv2; optional còn chấp nhận yêu cầu IMDSv1 |
| **HttpPutResponseHopLimit** | Số nguyên **1–64** ở cấp instance | Giới hạn hop của **phản hồi PUT lấy token**; thông thường chọn mức thấp nhất đáp ứng topology, container thường cần thử mức **2** |
| **HttpProtocolIpv6** | **enabled / disabled** | Bật endpoint IMDS qua IPv6 khi loại instance/subnet đáp ứng điều kiện |
| **InstanceMetadataTags** | **enabled / disabled** | Có cho phép đọc instance tags qua IMDS hay không; chỉ bật khi workload cần và tags không chứa thông tin nhạy cảm |

**Điểm kỹ thuật quan trọng:** **HttpPutResponseHopLimit** không phải TTL của session token. Session TTL tối đa 21.600 giây là một tham số HTTP gửi khi PUT; hop limit là giới hạn IP của gói **phản hồi** khi IMDS trả token. Giá trị thấp có thể tăng cô lập nhưng cũng ảnh hưởng container có thêm hop mạng.

### 5.1. Trường hợp container trên EC2

Trong một số môi trường container, request từ network namespace của container đến IMDS đi qua một hop bổ sung. Nếu token response có hop limit **1**, phản hồi PUT có thể không về tới tiến trình container. Khi ứng dụng/agent cần IMDS, tài liệu AWS khuyến nghị xem xét **HttpPutResponseHopLimit = 2** hoặc thay đổi kiến trúc để truyền cấu hình (ví dụ Region) và credentials cho workload theo cơ chế chuyên dụng.

Không tăng hop limit lên giá trị rất lớn chỉ để xử lý timeout. Trước tiên xác định **container có thật sự cần truy cập IMDS của host hay không**. Với ECS, cân nhắc **task role** để cấp quyền cho từng task; với EKS, cân nhắc cơ chế identity dành cho pod khi phù hợp. Những cơ chế này giảm nhu cầu cho container dùng chung instance profile của host.

### 5.2. IMDS tags không phải kho bí mật

Khi bật **InstanceMetadataTags**, tiến trình có quyền IMDS có thể đọc những tag được hỗ trợ. Tag có thể được dùng để tham chiếu môi trường hoặc cấu hình, nhưng không lưu password, token dịch vụ, chuỗi kết nối nhạy cảm hoặc khóa bí mật trong tag. Nếu tag không cần thiết, giữ tính năng bị tắt.

## 6. Thứ tự ưu tiên cấu hình và phạm vi tác động

Khi launch instance, AWS xác định **từng metadata option riêng** theo thứ tự:

1. **Cấu hình tại lần launch** (gồm tham số RunInstances hoặc EC2 Launch Template).
2. **Account-level default trong Region** tương ứng nếu không có giá trị tường minh tại launch.
3. **AMI configuration** đối với các tùy chọn hỗ trợ như **ImdsSupport = v2.0**, nếu hai cấp trên không nêu giá trị.

Ví dụ, một AMI có **ImdsSupport = v2.0** có thể làm **HttpTokens = required** và mặc định hop limit **2** khi không có cấu hình cấp cao hơn. Nhưng nếu cấu hình launch ghi rõ **HttpTokens = optional**, giá trị đó có thể thắng AMI/account default, **trừ khi có enforcement hoặc policy giới hạn**. Mặc định ở tài khoản không tự chuyển đổi các EC2 instance đã tồn tại.

| Cấp thiết lập | Áp dụng tới | Điều cần kiểm tra |
|---|---|---|
| **Instance / Launch Template** | Instance được launch với cấu hình tương ứng | Version Launch Template mà Auto Scaling Group thực sự sử dụng |
| **Account default theo Region** | Instance **mới** ở tài khoản/Region nếu launch không ghi đè | Khác nhau theo Region; không sửa các instance đang tồn tại |
| **AMI ImdsSupport v2.0** | Instance mới dựa vào AMI khi không có override mạnh hơn | AMI version, launch options và account defaults |
| **Account/organization enforcement** | Chặn cấu hình không thỏa điều kiện bắt buộc IMDSv2 | Có thể làm yêu cầu launch với IMDSv1 **thất bại** |
| **IAM/SCP condition** | Hạn chế ai được launch/modify metadata options | Ngăn người dùng hạ chuẩn khi tạo/chỉnh instance |

AWS còn có **HttpTokensEnforced** ở phạm vi phù hợp để bắt buộc cấu hình IMDSv2. Enforcement được đánh giá **sau khi** suy ra metadata options theo thứ tự ưu tiên; nếu kết quả còn cho phép IMDSv1 thì thao tác launch có thể bị từ chối. Đây là mức kiểm soát mạnh hơn chỉ đặt account default, vì default có thể bị ghi đè bởi một thiết lập tường minh nếu không có enforcement.

**Khi dùng Auto Scaling Group (ASG):** phải kiểm tra Launch Template và phiên bản đang được ASG tham chiếu. Đổi template cho lần launch tiếp theo không tự cấu hình lại tất cả instance đã chạy. Cần kế hoạch thay thế/instance refresh theo SLO và khả năng phục hồi của ứng dụng.

## 7. Cấu hình và kiểm tra bằng AWS CLI

Những ví dụ sau dùng **Region ap-southeast-1** và instance ID giả định. Thay chúng bằng giá trị trong môi trường được phép truy cập. Lệnh **describe** là đọc; lệnh **modify** thay đổi cấu hình thật, vì vậy chỉ chạy sau khi đánh giá tương thích ứng dụng.

### 7.1. Kiểm kê instance đang dùng IMDSv1 hoặc IMDSv2

~~~bash
aws ec2 describe-instances \
  --region ap-southeast-1 \
  --query 'Reservations[].Instances[].{Id:InstanceId,State:State.Name,Metadata:MetadataOptions}' \
  --output json
~~~

Đọc các trường **MetadataOptions.HttpTokens**, **HttpEndpoint**, **HttpPutResponseHopLimit**, **HttpProtocolIpv6**, **InstanceMetadataTags** và **State** (trạng thái áp dụng tùy chọn, nếu được trả về). Instance có **HttpTokens = optional** vẫn có thể nhận IMDSv1; instance **required** chỉ chấp nhận IMDSv2.

Để kiểm tra một instance:

~~~bash
aws ec2 describe-instances \
  --region ap-southeast-1 \
  --instance-ids i-0123456789abcdef0 \
  --query 'Reservations[0].Instances[0].MetadataOptions' \
  --output json
~~~

Khi kiểm kê nhiều tài khoản/Region, lặp theo danh sách được quản lý, bởi kết quả của một lệnh với một Region **không đại diện cho toàn tổ chức**.

### 7.2. Bắt buộc IMDSv2 cho instance hiện hữu

Sau khi xác nhận agent, SDK, ứng dụng, container tương thích, có thể chỉnh sửa instance bằng API **ModifyInstanceMetadataOptions**:

~~~bash
aws ec2 modify-instance-metadata-options \
  --region ap-southeast-1 \
  --instance-id i-0123456789abcdef0 \
  --http-endpoint enabled \
  --http-tokens required \
  --http-put-response-hop-limit 1
~~~

Lệnh trên đặt instance ở chế độ **chỉ IMDSv2** với hop limit 1. Nếu instance chạy container cần lấy IMDS token qua thêm một hop, hãy đánh giá riêng lựa chọn **2** thay vì áp dụng giá trị 1 cho mọi workload.

Sau khi sửa, chạy lại **describe-instances** và xác nhận trạng thái cấu hình đã **applied**. Sau đó kiểm thử ứng dụng và SDK thực tế; việc CLI trả về thành công không bảo đảm tất cả tiến trình phụ thuộc metadata vẫn chạy bình thường.

### 7.3. Cấu hình trong Infrastructure as Code

Ví dụ đoạn Terraform **bên trong tài nguyên aws_instance**:

~~~hcl
metadata_options {
  http_endpoint               = "enabled"
  http_tokens                 = "required"
  http_put_response_hop_limit = 1
  instance_metadata_tags      = "disabled"
}
~~~

Đoạn này chỉ minh họa block **metadata_options**, chưa phải một cấu hình Terraform hoàn chỉnh. Với Auto Scaling Group, cấu hình các thuộc tính tương đương tại **Launch Template** được ASG dùng. Dù Terraform/CloudFormation/CLI cấu hình theo cách nào, phải xác minh metadata options cuối cùng trên instance vừa được launch.

### 7.4. Thiết lập mặc định và chính sách bắt buộc

Ở quy mô nhiều instance, quản trị bằng ba lớp bổ trợ:

- **Launch Template / IaC**: khai báo **HttpTokens = required** ngay trong cấu hình triển khai.
- **Account-level default và enforcement**: ưu tiên IMDSv2 cho instance mới và chặn các cấu hình launch cho phép IMDSv1 khi tổ chức đã sẵn sàng.
- **IAM/SCP/organization controls**: hạn chế quyền thay đổi metadata options hoặc yêu cầu không đáp ứng tiêu chuẩn.

AWS cung cấp condition keys của EC2 để yêu cầu IMDSv2 khi launch và kiểm soát khả năng sửa cấu hình. Một trong các condition key thường được dùng là **ec2:MetadataHttpTokens**. Thiết kế policy cần đối chiếu API nào hỗ trợ key nào, vì policy sai có thể vô tình chặn việc triển khai hợp lệ.

## 8. Vai trò của IAM và AWS SDK khi truy cập metadata

### 8.1. Không lưu access key dài hạn trên EC2

Giả sử service xử lý đơn hàng EC2 cần đọc S3 và ghi DynamoDB. Kiến trúc nên dùng:

1. IAM role giới hạn **s3:GetObject** trên prefix được cấp và quyền DynamoDB cần thiết trên bảng cụ thể.
2. Instance profile gắn role vào EC2.
3. Ứng dụng dùng SDK/CLI với credential provider chain để lấy credentials tạm thời từ môi trường runtime.
4. **HttpTokens = required** để IMDS của instance không nhận request metadata kiểu IMDSv1.
5. CloudTrail và các công cụ theo dõi quyền để kiểm chứng hành động API và giảm quyền dư thừa.

**Ví dụ với AWS SDK for Java 2.x** (minh họa sử dụng default provider chain; phần dependency, bucket và Region cần cấu hình theo dự án):

~~~java
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;

import java.nio.file.Paths;

public class DownloadReport {
    public static void main(String[] args) {
        try (S3Client s3 = S3Client.builder()
                .region(Region.AP_SOUTHEAST_1)
                .build()) {
            s3.getObject(
                GetObjectRequest.builder()
                    .bucket("example-report-bucket")
                    .key("reports/current.csv")
                    .build(),
                Paths.get("/tmp/current.csv")
            );
        }
    }
}
~~~

Code không ghi access key/secret key. AWS SDK lấy credentials theo **default credential provider chain**; trên EC2, nếu không có nguồn ưu tiên khác, SDK có thể lấy credentials từ instance profile qua IMDSv2. Các biến môi trường credentials hoặc profile được cấp tường minh **có thể được ưu tiên hơn role của EC2**, nên vẫn phải kiểm tra danh tính runtime khi thấy AccessDenied.

**Không giả định** mọi phiên bản SDK cũ đều hỗ trợ IMDSv2. Trước khi tắt IMDSv1, cập nhật phiên bản SDK/CLI/agent còn được hỗ trợ và thử các đường đi credentials thật, bao gồm code khởi động, script, bootstrap, cron job và sidecar.

### 8.2. IMDSv2 không thay thế least privilege

Nếu role của EC2 có **s3:*** trên mọi bucket hoặc quyền quản trị IAM quá rộng, việc bật IMDSv2 không sửa được lỗi phân quyền. Phần mềm có quyền chạy trên instance và truy cập IMDS vẫn có thể nhận credentials của role trong những điều kiện phù hợp.

Nguyên tắc là: **role chuyên dụng cho từng workload**, action/resource/condition được thu hẹp, credentials ngắn hạn, không lộ dữ liệu nhạy cảm và hạn chế tiến trình có thể tiếp cận metadata.

## 9. Chuyển đổi hệ thống từ IMDSv1 sang bắt buộc IMDSv2

Không nên bật **HttpTokens = required** đồng loạt khi chưa biết workload nào đang sử dụng IMDSv1. Một số ứng dụng đời cũ, agent hoặc script chỉ gửi GET trực tiếp tới metadata; chúng có thể ngừng lấy Region hoặc credentials và không còn gọi API AWS được.

### Bước 1 — Kiểm kê tài nguyên và nơi phụ thuộc metadata

Liệt kê EC2 instances, Auto Scaling Groups, Launch Templates, AMIs, hệ điều hành, agent giám sát, CLI/SDK và container đang chạy. Xác định tiến trình nào truy cập **169.254.169.254** và có dùng IMDSv2 token hay không.

**Đầu ra:** bảng danh sách instance/tài khoản/Region, cấu hình **HttpTokens**, owner và ứng dụng bị ảnh hưởng.

### Bước 2 — Quan sát CloudWatch trước khi sửa

Amazon EC2 xuất các metric giúp đánh giá IMDSv1:

| CloudWatch metric | Cách hiểu | Ứng dụng khi chuyển đổi |
|---|---|---|
| **MetadataNoToken** | Số lần truy cập IMDS **thành công không có token**; thể hiện việc sử dụng IMDSv1 khi được cho phép | Ưu tiên sửa ứng dụng/agent còn phát sinh IMDSv1 |
| **MetadataNoTokenRejected** | Số lần request kiểu IMDSv1 bị từ chối sau khi IMDSv1 đã bị vô hiệu hóa | Phát hiện workload chưa tương thích sau chuyển đổi |
| **ImdsV1Enabled** | Trạng thái instance có cho phép IMDSv1 không; **1** khi HttpTokens optional, **0** khi required | Kiểm tra posture/configuration, kể cả lúc không có traffic |

Hai lưu ý quan trọng:

- **MetadataNoToken = 0** trong một khoảng thời gian không chứng minh toàn bộ code đã bỏ IMDSv1: có thể tác vụ hiếm gặp chưa chạy trong thời gian đó hoặc metric không phát sinh khi không có request.
- **ImdsV1Enabled** phản ánh cấu hình cho phép IMDSv1, **không đo số request**. Để kiểm kê số instance còn cho phép IMDSv1, nên xem metric cùng dữ liệu EC2 inventory.

Có thể dùng **IMDS Packet Analyzer** do AWS cung cấp để xác định tiến trình còn thực hiện IMDSv1 trên môi trường được phép theo dõi; cần xem xét quyền ghi nhận lưu lượng, tài nguyên hệ điều hành và yêu cầu bảo mật khi bật công cụ.

### Bước 3 — Sửa các thành phần còn dùng IMDSv1

- Cập nhật SDK/CLI/agent đã cũ lên phiên bản hỗ trợ IMDSv2.
- Thay script GET trực tiếp bằng quy trình **PUT token → GET có token**.
- Kiểm tra bootstrap, cloud-init, user data, công cụ quản trị và job chạy nền.
- Với container, xác định có cần truy cập host IMDS không; nếu có, kiểm tra đường mạng và hop limit.
- Xác minh credential provider chain và khả năng tự làm mới credentials của IAM role.

### Bước 4 — Thử trên môi trường đại diện

Chọn một nhóm instance ít rủi ro hoặc môi trường staging. Đặt **HttpTokens = required**, kiểm tra lệnh lấy token, thử ứng dụng thực tế, khởi động lại agent/container nếu cần và theo dõi metric **MetadataNoTokenRejected**.

Nếu cần thay đổi hop limit, chọn mức nhỏ nhất đủ dùng; đối với container có thêm hop mạng có thể cân nhắc **2** theo hướng dẫn AWS.

### Bước 5 — Triển khai theo đợt và có phương án khôi phục

Thiết lập cách thay đổi theo từng nhóm instance/ASG, đường rollback phù hợp, cửa sổ triển khai và giám sát. Không bỏ qua khả năng một cấu hình không tương thích làm SDK mất credentials rồi gây hàng loạt **AccessDenied**.

**Quy trình khôi phục phải tuân thủ chính sách bảo mật:** trước hết sửa SDK/cấu hình container/hop limit. Việc tạm cho phép IMDSv1 chỉ là lựa chọn ngoại lệ cần được phê duyệt và có thời hạn trong môi trường cho phép; nếu account-level enforcement đã bật, việc hạ chuẩn có thể bị chặn.

### Bước 6 — Khóa cấu hình cho những lần launch sau

Khi dữ liệu quan sát và thử nghiệm đã đạt, cập nhật Launch Templates, account defaults, enforcement và IAM/SCP. Thực hiện instance refresh nếu cần để thay instance cũ; giám sát **ImdsV1Enabled** để tránh đội máy quay lại trạng thái **optional**.

## 10. Bảo mật nâng cao: IMDSv2 chỉ là một lớp phòng thủ

### 10.1. SSRF, remote code execution và ứng dụng có quyền mạng

IMDSv2 giúp cản những luồng SSRF/proxy không thể tự tạo PUT và gắn token vào GET. Nhưng nếu ứng dụng bị **remote code execution** và kẻ tấn công chạy được mã bên trong instance, IMDSv2 không ngăn tiến trình đó thực hiện đúng quy trình lấy token. Tương tự, những container có thể giao tiếp tới IMDS của host vẫn cần giới hạn quyền và cô lập đúng cách.

Vì vậy, luôn kết hợp:

- Kiểm soát đầu vào để chống SSRF, giới hạn URL/host mà ứng dụng có thể gọi, và cập nhật thư viện.
- Sử dụng **IAM role least privilege** và tách quyền giữa các workload.
- **Host firewall** hoặc chính sách mạng ở cấp host/container để giới hạn tiến trình cần truy cập IMDS; kiểm tra cả IPv4 và IPv6 nếu bật.
- Bảo vệ credentials khỏi log, trace, debug output, shell history và vùng lưu trữ không an toàn.
- Theo dõi CloudTrail và phát hiện việc dùng role ngoài mẫu thông thường.

**Security group và VPC NACL** phục vụ kiểm soát lưu lượng VPC, nhưng không nên coi chúng là biện pháp đủ để chặn mọi tiến trình *bên trong EC2* truy cập địa chỉ link-local IMDS. Khi cần kiểm soát theo tiến trình, sử dụng biện pháp tại hệ điều hành/container và xác minh hiệu quả thực tế.

### 10.2. Khi nào có thể tắt hẳn HttpEndpoint?

Nếu workload **không cần metadata và credentials qua IMDS**, có thể cân nhắc **HttpEndpoint = disabled** để giảm bề mặt tấn công. Tuy nhiên, điều này có thể phá vỡ ứng dụng hoặc AWS agent dựa vào instance profile, user data/metadata, các tiện ích bootstrap hoặc quá trình xác định Region.

Không tắt endpoint chỉ vì không thấy ứng dụng gọi trực tiếp trong một thử nghiệm ngắn. Cần xác nhận tất cả dependency, phương án cấp credentials thay thế và quy trình vận hành trước khi áp dụng.

### 10.3. Mạng doanh nghiệp và thiết bị chuyển tiếp

Trên một số cấu hình Nitro-based instance có thiết bị ảo đóng vai trò router hoặc network appliance, việc chuyển tiếp gói đến địa chỉ IMDS có thể gây rủi ro ngoài dự tính. AWS khuyến nghị chặn lưu lượng tới các địa chỉ IMDS qua thiết bị chuyển tiếp khi thiết kế mạng có tình huống đó. Kiểm tra **169.254.169.254** và **fd00:ec2::254** nếu endpoint IPv6 được bật.

## 11. Chẩn đoán lỗi IMDSv2 theo triệu chứng

| Triệu chứng | Nguyên nhân thường gặp | Cách xác minh và xử lý |
|---|---|---|
| GET metadata trả **401 Unauthorized** | **HttpTokens = required** nhưng thiếu token/token hết hạn | Lấy token bằng PUT, thêm header token vào GET, kiểm tra TTL |
| PUT token timeout trong container, nhưng truy cập từ host hoạt động | **HttpPutResponseHopLimit** quá thấp so với network hop | Kiểm tra metadata options, network namespace, cân nhắc hop limit 2 hoặc cơ chế credentials riêng |
| Cả PUT và GET không kết nối được | **HttpEndpoint = disabled**, firewall/proxy hoặc lỗi đường truy cập | Kiểm tra describe-instances, host firewall, thiết lập proxy, yêu cầu network |
| Lệnh thử HTTP bị chuyển qua proxy doanh nghiệp | HTTP_PROXY/HTTPS_PROXY hoặc NO_PROXY cấu hình chưa phù hợp | Không đi qua proxy cho địa chỉ IMDS; xác minh cấu hình proxy của SDK/agent |
| EC2 không lấy được credentials của instance profile | Không có role/profile, IMDS bị tắt hoặc SDK cũ/không tương thích | Kiểm tra instance profile, SDK provider chain và IMDS; không in secret ra log |
| Ứng dụng vẫn **AccessDenied** dù đọc metadata được | Role thiếu quyền hoặc credentials đến từ nguồn khác | Dùng STS GetCallerIdentity và IAM policy evaluation để xác nhận principal/action/resource |
| AWS CLI hoạt động trên host, ứng dụng trong container thất bại | Khác môi trường credentials, hop limit, proxy hoặc role của task | Kiểm tra identity/SDK trong container, cấu hình task role và đường IMDS |
| EC2 mới vẫn **HttpTokens = optional** dù AMI dùng IMDSv2 | Launch Template hoặc account setting có giá trị ưu tiên cao hơn | Kiểm tra thứ tự cấu hình cho từng metadata option |
| Launch thất bại khi cấu hình **optional** | Tài khoản/tổ chức đang enforce IMDSv2 hoặc IAM/SCP chặn | Xem thông báo EC2, account defaults/enforcement và Launch Template |
| **MetadataNoTokenRejected** tăng sau rollout | Tiến trình nào đó vẫn gọi IMDSv1 | Truy vết agent/script, cập nhật SDK, kiểm thử lại |
| Không đọc được IMDS qua IPv6 | Endpoint IPv6 chưa bật hoặc instance/subnet không hỗ trợ | Kiểm tra Nitro, subnet hỗ trợ IPv6, **HttpProtocolIpv6** |
| Vẫn truy cập metadata khi nghĩ đã tắt IMDSv1 | Chỉ phần mềm dùng v2, instance còn **HttpTokens = optional** | Xác minh trực tiếp metadata options phải là **required** |

### 11.1. Phân biệt ba loại sự cố hay bị gộp chung

**Không lấy được token** là vấn đề khả năng truy cập IMDS, cấu hình HTTP hoặc hop limit. **Lấy được token nhưng không lấy được credentials** là vấn đề instance profile, metadata endpoint/role path hoặc cách SDK dùng credential chain. **Có credentials nhưng gọi S3/DynamoDB thất bại** là vấn đề IAM, tài nguyên, điều kiện policy hoặc dịch vụ đích. Ba tình huống có hướng xử lý khác nhau và không nên sửa bằng một policy **AdministratorAccess** quá rộng.

### 11.2. Xác nhận principal thực tế bằng STS

Nếu EC2 có AWS CLI và cần điều tra AccessDenied của API AWS:

~~~bash
aws sts get-caller-identity --region ap-southeast-1
~~~

Lệnh này cho biết tài khoản và ARN của danh tính **AWS CLI đang sử dụng**, từ đó so khớp với instance role dự kiến. Nếu ARN là một user/role khác, hãy kiểm tra environment variables, shared credentials file, container task role và quá trình AssumeRole trước khi sửa instance profile. Không dùng lệnh in toàn bộ environment hay đọc nội dung credentials tạm thời để debug khi không cần thiết.

## 12. Tình huống thực tế và bài tập

### Tình huống A — Web API trên EC2 và nguy cơ SSRF

Một web API viết bằng Java chạy trên EC2. Ứng dụng cho phép người dùng nhập URL để tải dữ liệu từ bên ngoài. EC2 được gắn role có quyền đọc dữ liệu S3. Nhóm bảo mật lo ngại một URL đầu vào có thể khiến ứng dụng truy cập địa chỉ metadata.

**Câu hỏi:** chỉ bật **HttpTokens = required** có giải quyết hoàn toàn rủi ro không?

**Gợi ý xử lý:** IMDSv2 cản một số luồng SSRF GET đơn giản nhưng không loại bỏ SSRF/RCE. Cần kiểm soát URL và redirect, chặn đích link-local ở lớp ứng dụng/mạng phù hợp, giới hạn truy cập IMDS theo tiến trình nếu khả thi, giảm quyền IAM và kiểm tra logging/monitoring. SDK vẫn nên dùng instance role để lấy credentials đúng cách, không lưu access key dài hạn.

### Tình huống B — Container không nhận token

Một ứng dụng trong container chạy trên EC2 hoạt động khi **HttpTokens = optional**. Sau khi đổi sang **required**, ứng dụng không gọi S3 được; từ host vẫn lấy token bình thường.

**Câu hỏi:** lỗi này có nhất thiết do S3 bucket policy không?

**Gợi ý xử lý:** kiểm tra token PUT từ container, **HttpPutResponseHopLimit**, proxy và credential provider chain trước. Có thể token response bị chặn bởi thêm hop của container; nếu workload cần host IMDS thì cân nhắc hop limit **2**, hoặc ưu tiên cơ chế **task/pod identity** phù hợp. Chỉ sau khi xác nhận credentials lấy thành công mới kiểm tra IAM/S3 policy.

### Tình huống C — ASG tạo instance sai chuẩn

Tổ chức cập nhật AMI để hỗ trợ IMDSv2 nhưng Auto Scaling Group vẫn tạo một số instance có **HttpTokens = optional**. Các instance hiện hữu cũng chưa thay đổi sau khi đặt account default.

**Câu hỏi:** ở đâu có thể ghi đè thiết lập?

**Gợi ý xử lý:** kiểm tra phiên bản Launch Template đang dùng, account default của đúng Region và thuộc tính AMI theo thứ tự ưu tiên. Account default không cập nhật instance đã chạy; cần xử lý instance cũ riêng. Khi sẵn sàng, cân nhắc **enforcement** để launch cho phép IMDSv1 bị từ chối, kết hợp giám sát **ImdsV1Enabled**.

### Tình huống D — Có token nhưng vẫn AccessDenied

Một job lấy được instance ID qua IMDSv2, sau đó SDK gọi **dynamodb:PutItem** và báo **AccessDeniedException**.

**Câu hỏi:** việc đọc metadata thành công có chứng minh role có quyền ghi DynamoDB không?

**Gợi ý xử lý:** không. Xác minh instance profile, principal thực tế bằng STS, policy cho action **dynamodb:PutItem** trên ARN bảng, các boundary/SCP/resource policy liên quan và Region. IMDSv2 chỉ điều khiển **cách lấy metadata**, không cấp quyền cho DynamoDB.

## 13. Checklist triển khai IMDSv2 trong production

- [ ] Đã xác định tất cả EC2 instances và chủ sở hữu trong các tài khoản/Region liên quan.
- [ ] Đã hiểu ứng dụng/agent/SDK/script/container nào cần metadata hoặc role credentials.
- [ ] Đã đánh giá **MetadataNoToken**, **MetadataNoTokenRejected**, **ImdsV1Enabled** trong khoảng thời gian đại diện.
- [ ] Đã cập nhật SDK/CLI/agent và script GET IMDSv1 sang mô hình có token.
- [ ] Đã đặt **HttpTokens = required** và kiểm tra **HttpEndpoint** phù hợp.
- [ ] Đã đặt **HttpPutResponseHopLimit** theo topology thật; thử đường từ container nếu có.
- [ ] Đã kiểm tra **HttpProtocolIpv6** và **InstanceMetadataTags** theo nhu cầu, giới hạn bảo mật.
- [ ] Đã kiểm tra precedence của Launch Template, account defaults, AMI và enforcement.
- [ ] Đã áp dụng IAM role tối thiểu, credential provider chain và biện pháp giảm SSRF phù hợp.
- [ ] Đã thử PUT token, GET metadata, lấy credentials qua SDK và gọi API nghiệp vụ trong môi trường kiểm thử.
- [ ] Đã giám sát runtime và có phương án khôi phục khi thay đổi metadata options làm ứng dụng thất bại.
- [ ] Đã kiểm tra instance mới từ ASG/Launch Template, đặt policy ngăn hạ chuẩn và ghi lại quyết định vận hành.

## 14. Ghi nhớ

**IMDS** giúp tiến trình trên EC2 đọc metadata và, khi có instance profile, nhận credentials tạm thời của IAM role. **IMDSv2** yêu cầu bước **PUT lấy session token** và dùng token với các request metadata; **HttpTokens = required** là thiết lập để vô hiệu hóa lối truy cập IMDSv1. **HttpPutResponseHopLimit** kiểm soát số hop của phản hồi token, đặc biệt quan trọng cho container. Việc triển khai an toàn cần đồng thời kiểm tra **cấu hình cuối cùng trên instance, phiên bản SDK, IAM least privilege, rủi ro SSRF, giám sát CloudWatch và kế hoạch rollout có kiểm thử**.

### Tài liệu AWS chính thức để đối chiếu

- [Use the Instance Metadata Service to access instance metadata](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/configuring-instance-metadata-service.html) — IMDSv2 PUT/GET, token và TTL.
- [Configure instance metadata options](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/configuring-instance-metadata-options.html) — các tùy chọn, thứ tự ưu tiên và enforcement.
- [Configure instance metadata options for new instances](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/configuring-IMDS-new-instances.html) — Launch Template, AMI và default cho instance mới.
- [Modify instance metadata options for existing instances](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/configuring-IMDS-existing-instances.html) — cập nhật instance đang chạy và hỗ trợ IPv6.
- [Transition to using IMDSv2](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/instance-metadata-transition-to-version-2.html) — lộ trình chuyển đổi và metric theo dõi.
- [Limit access to the Instance Metadata Service](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/instance-metadata-limiting-access.html) — host firewall và hạn chế truy cập IMDS.
- [CloudWatch metrics for your EC2 instances](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/viewing_metrics_with_cloudwatch.html) — MetadataNoToken và các metric liên quan.
- [IAM roles for Amazon EC2](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/iam-roles-for-amazon-ec2.html) — instance profile và credentials tạm thời.
- [AWS SDK for Java 2.x default credentials provider chain](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/credentials-chain.html) — lựa chọn credentials ở runtime.

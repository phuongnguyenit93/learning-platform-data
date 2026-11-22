# Launch template và Auto Scaling Group

Một website có thể chỉ cần hai máy EC2 trong giờ thấp điểm nhưng cần thêm năng lực khi số người dùng tăng đột biến. Nếu tạo từng máy thủ công, việc triển khai thiếu nhất quán, thay thế máy lỗi và cập nhật phiên bản trở nên khó kiểm soát. **EC2 Launch Template** mô tả cấu hình dùng để tạo máy mới; **Amazon EC2 Auto Scaling Group (ASG)** duy trì và điều chỉnh năng lực của một nhóm instance theo quy tắc đã đặt. Khi kết hợp **Application Load Balancer (ALB)**, nhiều máy có thể cùng phục vụ yêu cầu, trải trên nhiều Availability Zone (AZ) và giảm ảnh hưởng khi một instance bị lỗi.

Bài thuộc chương **Cân bằng tải và mở rộng**, mô-đun **CLOUD_PROVIDERS_AWS**. Nội dung liên hệ với hạ tầng Region/AZ, IAM, VPC, EC2, lưu trữ, cơ sở dữ liệu, tích hợp và serverless để giúp người học chọn dịch vụ, triển khai ứng dụng an toàn, giám sát hiệu năng, phục hồi sau sự cố và kiểm soát chi phí.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt vai trò của **launch template**, **Auto Scaling Group**, **scaling policy** và **load balancer/target group**.
2. Giải thích **minimum**, **desired** và **maximum capacity** cùng cơ chế duy trì nhóm instance khỏe mạnh.
3. Cấu hình launch template có **AMI**, loại instance, security group, IAM instance profile, user data, EBS và **IMDSv2**.
4. Thiết kế ASG trải nhiều AZ, gắn ALB, cấu hình health check và thời gian khởi động ứng dụng.
5. Chọn **target tracking**, **step scaling**, **scheduled scaling** hoặc **predictive scaling** theo tải thực tế.
6. Hiểu cách áp dụng **launch template version**, **instance refresh**, lifecycle hook, scale-in protection, warm pool và Spot Instances.
7. Kiểm kê, giám sát, kiểm thử scale-out/scale-in, triển khai phiên bản mới và tính tổng chi phí.

## 2. Launch template và ASG giải quyết hai bài toán khác nhau

| Thành phần | Trả lời câu hỏi | Chức năng chính |
|---|---|---|
| **Launch template (LT)** | **Instance mới phải được tạo như thế nào?** | Định nghĩa cấu hình EC2: AMI, instance type, network, SG, instance profile, storage, user data, metadata options... |
| **Auto Scaling Group (ASG)** | **Cần duy trì bao nhiêu năng lực và ở những đâu?** | Tạo/loại bỏ/thay thế EC2 theo min/desired/max, AZ, health, scaling policy, lựa chọn capacity |
| **Scaling policy** | **Khi nào tăng hoặc giảm năng lực?** | Ra quyết định điều chỉnh desired capacity theo metric hoặc lịch |
| **Target group + load balancer** | **Request được chuyển tới instance khỏe mạnh nào?** | Cân bằng lưu lượng và kiểm tra sức khỏe ở lớp nhận request |
| **CloudWatch / scaling activity** | **Hệ thống đang hoạt động như kỳ vọng không?** | Metric, cảnh báo, lịch sử mở rộng, kiểm tra hiệu năng và chi phí |

~~~mermaid
flowchart TB
    U["Người dùng"] --> ALB["Application Load Balancer"]
    ALB --> TG["Target group<br/>Health check / routing"]
    LT["Launch template<br/>AMI, type, IAM, SG, EBS, IMDSv2"] -. "Cấu hình cho instance mới" .-> ASG["Auto Scaling Group<br/>Min / Desired / Max"]
    CW["CloudWatch metrics"] --> POL["Scaling policy"]
    POL --> ASG
    ASG --> A["EC2 instance<br/>AZ A"]
    ASG --> B["EC2 instance<br/>AZ B"]
    TG --> A
    TG --> B
~~~

Ví dụ, ASG có **min = 2, desired = 2, max = 6**. Khi metric tải vượt mục tiêu, policy có thể tăng desired capacity lên 3 hoặc 4 (tùy mức tải và cách tính); ASG dùng launch template để tạo các instance mới. Khi nhu cầu giảm đủ lâu, chính sách có thể yêu cầu scale-in; ASG giảm số máy theo cấu hình và chính sách chấm dứt. Nếu một instance trở nên unhealthy, ASG có thể **thay thế** nó để khôi phục desired capacity ngay cả khi không có scaling policy.

**Không hiểu nhầm:** Launch template tự nó **không khởi chạy** hoặc duy trì số lượng máy. ASG không cung cấp ứng dụng hoàn chỉnh: bạn vẫn phải thiết kế bootstrap, network, dữ liệu, bảo mật, xử lý request và trạng thái của ứng dụng.

## 3. Thiết kế launch template

### 3.1. Các thuộc tính cần xác định

| Thuộc tính | Ví dụ | Quyết định cần làm rõ |
|---|---|---|
| **AMI ID** | AMI Linux đã cài ứng dụng | AMI được vá lỗi, architecture phù hợp và có thể tái tạo |
| **Instance type** | Một loại EC2 phù hợp CPU/RAM | Tải compute, memory, network, architecture x86/ARM |
| **Security groups** | SG cho web/app | Port cần thiết từ ALB, mạng quản trị và các outbound rule |
| **IAM instance profile** | Role chỉ được đọc cấu hình và ghi log | Quyền tối thiểu, sử dụng temporary credentials |
| **Storage** | EBS gp3, mã hóa | Dung lượng, throughput, IOPS, EBS encryption, dữ liệu bền vững |
| **User data** | Script cloud-init cài/khởi động app | Tính lặp lại, thời gian bootstrap, cơ chế lấy secret |
| **Metadata options** | **HttpTokens = required** | Bắt buộc IMDSv2, xem xét hop limit cho container |
| **Tags** | Environment, Owner, Application | Cost allocation, vận hành, phân quyền theo tag |
| **Network interfaces** | SG, public IP, NIC trong cấu hình phù hợp | Cần tương thích subnet do ASG chọn; tránh ràng buộc mạng gây lỗi launch |

**AMI** có thể là image dựng sẵn (**golden AMI**) hoặc image nền, sau đó dùng **user data** để cài ứng dụng. Golden AMI có thể giảm thời gian instance sẵn sàng và giảm biến động bootstrap. Nếu mỗi lần scale-out đều tải hàng GB, build ứng dụng và cập nhật package từ Internet, tốc độ scale và độ tin cậy sẽ phụ thuộc mạnh vào đường mạng hoặc repository.

### 3.2. Launch template có nhiều version

Launch template hỗ trợ **version bất biến**: thay đổi AMI hoặc cấu hình sẽ tạo **version mới**, không sửa nội dung version đã tạo. Bạn có thể đặt một phiên bản làm **Default** hoặc tham chiếu **Latest**, nhưng production thường nên dùng **số version cụ thể** để kiểm soát cấu hình đang được ASG sử dụng.

| Tham chiếu | Ý nghĩa | Rủi ro cần chú ý |
|---|---|---|
| **Version = 3** | ASG launch instance theo version 3 | Dễ truy vết, rollback có kiểm soát |
| **Version = $Default** | ASG lấy version được đánh dấu Default ở lúc launch | Thay Default có thể thay cấu hình của những lần launch tiếp theo |
| **Version = $Latest** | ASG lấy version mới nhất có tại lúc launch | Tạo version mới có thể khiến instance thay thế/scale-out dùng cấu hình chưa được phê duyệt |

**Cập nhật launch template không tự thay toàn bộ EC2 đang chạy.** ASG chỉ dùng template được tham chiếu khi tạo **instance mới**. Để cập nhật toàn đội máy, cần kế hoạch **instance refresh**, rolling deployment hoặc một cơ chế phát hành phù hợp. Để rollback, tạo/cấu hình ASG dùng lại version đã được xác minh rồi thực hiện quy trình cập nhật và kiểm thử lại.

### 3.3. Cấu hình bảo mật tại nguồn

- Không ghi **access key**, mật khẩu hay token trong AMI, user data hoặc Git. Dùng instance profile và Secrets Manager/Systems Manager Parameter Store theo quyền tối thiểu.
- Bật **IMDSv2** bằng **HttpTokens = required**; đánh giá **HttpPutResponseHopLimit** theo topology, đặc biệt nếu container chạy trên EC2.
- Mã hóa EBS và đảm bảo chính sách KMS phù hợp; hạn chế SG để máy app chỉ nhận traffic từ thành phần cần thiết.
- Ứng dụng nên chạy với quyền hệ điều hành tối thiểu, được cập nhật bản vá và có đường xuất log/metric.
- Thiết kế bootstrap idempotent: instance mới được tạo bất kỳ lúc nào cũng phải đạt cùng trạng thái ứng dụng khỏe mạnh.

**Tài nguyên bền vững:** dữ liệu nghiệp vụ không nên chỉ nằm trên ổ root EBS của instance trong ASG. Máy bị thay thế hoặc chấm dứt có thể làm mất dữ liệu tại chỗ. Lưu trạng thái trong RDS/DynamoDB/S3/EFS hoặc dịch vụ phù hợp; dùng backup và retention riêng cho dữ liệu phải giữ lâu.

## 4. Auto Scaling Group: min, desired, max và vòng đời instance

### 4.1. Ba giới hạn công suất

| Tham số | Mô tả | Ví dụ |
|---|---|---|
| **MinSize** | Năng lực tối thiểu ASG duy trì | 2 |
| **DesiredCapacity** | Năng lực mục tiêu mà ASG tìm cách đạt tới | 2 |
| **MaxSize** | Giới hạn cao nhất cho điều chỉnh năng lực | 6 |

Với nhóm instance thông thường, các giá trị này thường được hiểu là số instance. Khi dùng **instance weighting/mixed instances**, capacity được tính bằng **đơn vị công suất** theo cấu hình, không nhất thiết bằng số máy vật lý. Vì vậy, **desired capacity 8** có thể tương ứng bốn instance với weight 2.

ASG hoạt động theo cơ chế **reconciliation**: so sánh trạng thái thật với desired capacity, launch instance khi thiếu, terminate instance khi dư, hoặc thay thế instance unhealthy. Nếu thiếu EC2 quota hoặc thiếu capacity của instance type/AZ, quá trình đạt desired capacity có thể thất bại hoặc chậm, tạo các sự kiện scaling lỗi cần điều tra.

### 4.2. Multi-AZ và giới hạn của HA

Một ASG có thể chọn các subnet thuộc **nhiều Availability Zone trong cùng Region**. ASG cố phân bố capacity cân bằng giữa các AZ trong phạm vi cấu hình và khả năng cung ứng. Khi một AZ có sự cố, khả năng tiếp tục phục vụ phụ thuộc việc ASG có thể đưa instance lên AZ còn khỏe, quota/capacity, đường mạng, ALB và backend.

**ASG trải hai AZ + ALB** giúp giảm rủi ro lỗi một EC2/AZ; tuy nhiên không bảo đảm ứng dụng HA nếu database, cache, session, DNS hoặc dependency chỉ nằm trong một AZ. ASG cũng không tự trở thành giải pháp **DR liên Region**.

Đặt **desired >= 2** cho hệ thống cần tiếp tục phục vụ khi một instance lỗi, và kiểm tra khả năng mỗi AZ còn lại xử lý tải cần thiết. Một nhóm **min = 0** có thể co về 0 để tiết kiệm cho job/môi trường thử nghiệm, nhưng ứng dụng trực tuyến sẽ không sẵn sàng cho đến khi capacity được khởi động lại.

### 4.3. Vòng đời cơ bản

~~~mermaid
flowchart LR
    L["Policy hoặc ASG yêu cầu launch"] --> P["Pending"]
    P --> H["Bootstrap + health checks"]
    H --> S["InService"]
    S -->|"Scale-in / unhealthy / refresh"| T["Terminating"]
    T --> X["Terminated"]
    H -->|"Launch không thành công"| F["Failed / launch lại"]
~~~

ASG có thêm các trạng thái chi tiết cho **lifecycle hooks**, **warm pool** và những quy trình khác. Sơ đồ trên chỉ thể hiện vòng đời đơn giản của một instance.

## 5. Kết hợp ASG với Application Load Balancer

### 5.1. Vai trò target group

ALB tiếp nhận yêu cầu HTTP/HTTPS qua listener rồi định tuyến đến **target group**. ASG có thể được gắn với target group dạng instance để tự đăng ký instance mới và hủy đăng ký instance đã loại bỏ. ALB kiểm tra **health check path** (chẳng hạn **/health**) để xác định target có thể nhận lưu lượng.

~~~mermaid
flowchart LR
    CLIENT["Client HTTPS"] --> ALB["ALB<br/>Public subnets AZ A/B"]
    ALB --> TG["Target group<br/>GET /health"]
    subgraph PRIVATE["Private application subnets"]
        A["EC2 AZ A"]
        B["EC2 AZ B"]
    end
    TG --> A
    TG --> B
    A --> DB["RDS / DynamoDB / S3<br/>dịch vụ dữ liệu"]
    B --> DB
~~~

Trong mô hình minh họa, ALB có thể ở public subnets, EC2 ở private subnets và EC2 security group chỉ cho phép cổng ứng dụng từ security group của ALB. Nếu EC2 cần tải package hoặc truy cập API AWS khi bootstrap, chuẩn bị NAT/VPC endpoints hoặc đường truy cập phù hợp.

### 5.2. EC2 health check và ELB health check

ASG có cơ chế kiểm tra mặc định dựa trên **trạng thái EC2**, và có thể được cấu hình để dùng thêm trạng thái từ **Elastic Load Balancing (ELB)**. Nếu gắn target group nhưng không bật chính sách sức khỏe phù hợp, ASG có thể không sử dụng kết quả target unhealthy theo cách bạn mong đợi.

| Cơ chế | Đánh giá điều gì? | Ví dụ |
|---|---|---|
| **EC2 status checks** | Tình trạng nền tảng/instance | Instance lỗi phần cứng hoặc hệ điều hành không đạt status check |
| **ALB target group health checks** | Target có đáp ứng giao thức, port và path theo cấu hình không | HTTP 200 từ **/health** |
| **ASG HealthCheckType = ELB** | Cho phép ASG xét trạng thái ELB khi quyết định thay instance | Target unhealthy liên tục có thể bị thay thế |
| **Health check grace period** | Thời gian chờ khi instance mới khởi động để tránh đánh unhealthy quá sớm theo phạm vi áp dụng | Đợi ứng dụng bootstrap hoàn tất |
| **Default instance warmup** | Thời gian để metric của instance mới ổn định khi scaling | Tránh phản ứng scaling quá mức với instance còn khởi động |

**Grace period và instance warmup là hai tham số khác nhau.** Grace period hỗ trợ quyết định thay máy dựa trên health, còn instance warmup phục vụ phép tính scaling/ổn định capacity mới. Giá trị phù hợp phụ thuộc thời gian bootstrap, thời gian kết nối backend và loại ứng dụng.

### 5.3. Health endpoint tốt cần kiểm tra gì?

Một endpoint **/health** nên phản ánh ứng dụng đủ điều kiện phục vụ lưu lượng, tránh trả 200 chỉ vì tiến trình HTTP còn chạy. Với hệ thống cần phân biệt mức sẵn sàng, có thể có **/live** và **/ready**:

- **Liveness**: tiến trình còn hoạt động và có thể tự phục hồi hay không.
- **Readiness**: ứng dụng đã tải cấu hình, mở listener và hoàn tất bootstrap thiết yếu để nhận request chưa.

Không làm health endpoint phụ thuộc quá nhiều vào những hệ thống tùy chọn vì có thể khiến toàn bộ target đồng loạt bị loại khi một dịch vụ phụ không quan trọng chậm. Phải xác định điều kiện nào thực sự khiến target không nên phục vụ.

### 5.4. Kết nối đang mở và giảm tải khi scale-in

Khi một instance bị scale-in, ALB target group có **deregistration delay** để cho những request/connection đang xử lý có cơ hội hoàn tất. Ứng dụng cũng cần xử lý tín hiệu chấm dứt, dừng nhận công việc mới và lưu checkpoint khi cần. Với background job dài, cân nhắc lifecycle hook và hàng đợi thay vì dựa hoàn toàn vào deregistration delay.

## 6. Các chính sách mở rộng (scaling policies)

### 6.1. Target tracking scaling

**Target tracking** cố giữ một metric gần giá trị mục tiêu bằng cách tăng/giảm desired capacity; đây thường là điểm bắt đầu cho web/app stateless. Ví dụ:

- **ASGAverageCPUUtilization** mục tiêu khoảng **50%**.
- **ALBRequestCountPerTarget** phản ánh lưu lượng request trên mỗi target, nếu kiến trúc có ALB phù hợp.
- Một custom metric biểu thị **số message đang chờ xử lý / năng lực worker**, nếu có quan hệ trực tiếp với capacity.

| Metric | Khi phù hợp | Khi dễ gây hiểu nhầm |
|---|---|---|
| CPU trung bình | Workload chủ yếu bị giới hạn CPU | Ứng dụng nghẽn RAM, I/O hoặc external API |
| ALB requests per target | Chi phí xử lý/request tương đối ổn định | Request có độ phức tạp rất khác nhau |
| Queue backlog per instance | Worker xử lý message theo hàng đợi | Thiếu metric chia cho capacity hoặc task có thời gian xử lý quá biến động |
| Custom metric | Có chỉ số gần mức sử dụng công suất thực | Metric không phản ánh được hiệu quả scale hoặc thiếu dữ liệu |

**Ví dụ tư duy:** nếu số request tăng gấp đôi nhưng mỗi request rất nhẹ, CPU có thể vẫn thấp; target CPU sẽ không tăng capacity như kỳ vọng. Cần chọn metric tương quan với nhu cầu năng lực thực tế. Ngược lại, một truy vấn database chậm có thể kéo dài response time nhưng thêm nhiều EC2 chỉ làm tăng số kết nối vào database và khiến nghẽn nặng hơn.

Target tracking hỗ trợ tự tính toán scale-out/scale-in theo cấu hình. Có thể **disable scale-in** khi policy dùng để mở rộng mà nhóm muốn kiểm soát việc giảm bằng cơ chế khác; lựa chọn này ảnh hưởng chi phí.

### 6.2. Step scaling và simple scaling

**Step scaling** điều chỉnh capacity theo các khoảng mức độ vi phạm CloudWatch alarm, ví dụ khi một metric cao hơn ngưỡng một ít thì thêm ít capacity, vượt nhiều thì tăng mạnh. Cần đặt alarm, step adjustments và thời gian warmup phù hợp.

**Simple scaling** cũng dựa trên alarm nhưng có cơ chế cooldown truyền thống. Với nhiều ứng dụng hiện đại, AWS khuyến nghị xem xét target tracking hoặc step scaling trước vì kiểm soát phản ứng và warmup rõ hơn.

### 6.3. Scheduled scaling

**Scheduled scaling** phù hợp cho tải có lịch cố định: bắt đầu làm việc lúc 8:00, chiến dịch quảng cáo đã biết, batch báo cáo lúc 23:00. Chính sách thay đổi min/max/desired theo thời điểm. Khi cấu hình lịch lặp, cần kiểm tra **timezone**, daylight saving time nếu liên quan và tác động đến năng lực đang chạy.

Ví dụ: mỗi ngày làm việc tăng desired lên 4 trước giờ cao điểm, rồi giảm về 2 sau khi kết thúc. Nếu nhu cầu tăng vượt dự đoán, dynamic scaling có thể bổ sung capacity trong giới hạn cấu hình; cần tránh lịch cố định làm giảm capacity trong lúc ứng dụng vẫn đang tải lớn.

### 6.4. Predictive scaling

**Predictive scaling** dự báo tải dựa trên dữ liệu lịch sử và có thể chuẩn bị capacity trước thời điểm cao điểm trong những cấu hình phù hợp. Cần dữ liệu/metric đủ đại diện và theo dõi sai số dự báo, đặc biệt với chiến dịch mới hoặc thay đổi workload không có lịch sử. Có thể chạy chế độ dự báo để đánh giá trước khi bật tự động thực thi.

### 6.5. Warmup, cooldown và tránh dao động

Khi instance mới được launch, cần thời gian để cài đặt ứng dụng, chạy migration thích hợp, kết nối dependency và đi vào target group. Nếu metric chỉ nhìn các máy cũ đang quá tải, policy có thể liên tục scale-out trước khi máy mới hoàn tất. Vì vậy phải cấu hình **default instance warmup** và quan sát hoạt động thực tế.

Không đặt warmup quá dài nếu ứng dụng khởi động rất nhanh: phản ứng scaling có thể chậm. Không đặt quá ngắn nếu ứng dụng cần nhiều phút bootstrap: dễ scale quá mức hoặc đưa traffic vào máy chưa sẵn sàng.

## 7. Mixed instances, On-Demand và Spot

ASG có thể sử dụng **Mixed Instances Policy** để chọn nhiều loại EC2 và kết hợp **On-Demand Instances** với **Spot Instances**. Mục tiêu có thể là tối ưu chi phí, tăng khả năng tìm được capacity hoặc đáp ứng biến động tải.

### 7.1. Khi nào nên dùng Spot?

**Spot Instances** có thể có chi phí thấp hơn On-Demand nhưng capacity có thể bị AWS thu hồi khi cần. Theo cơ chế thông thường, thông báo gián đoạn của EC2 Spot có thể được cung cấp khoảng **hai phút** trước khi instance bị terminate/stop/hibernate tùy thiết lập và khả năng hỗ trợ, nhưng không nên xem hai phút là thời gian cứu dữ liệu luôn được bảo đảm.

Ứng dụng phù hợp với Spot thường có những đặc điểm:

- Stateless API có nhiều target dự phòng.
- Worker xử lý hàng đợi, job có retry/checkpoint và tính idempotent.
- CI/build, phân tích batch hoặc workload phân tán có thể mất một node.

Không nên dựa vào Spot làm nguồn duy nhất cho dữ liệu hoặc các tác vụ không thể gián đoạn nếu không có thiết kế phục hồi rõ ràng.

### 7.2. Mixed Instances Policy

Một chính sách mixed instances có thể cấu hình:

| Thành phần | Ý nghĩa |
|---|---|
| **Instance requirements/overrides** | Danh sách instance types hoặc thuộc tính như vCPU/RAM |
| **On-Demand base capacity** | Năng lực cơ sở duy trì bằng On-Demand |
| **On-Demand percentage above base** | Tỷ lệ On-Demand của capacity vượt base |
| **Spot allocation strategy** | Cách chọn pools theo ưu tiên capacity hoặc mức giá/rủi ro phù hợp |
| **Instance weighting** | Cân theo đơn vị capacity giữa instance types khác nhau |
| **Capacity Rebalancing** | Chủ động tìm instance thay thế khi có tín hiệu Spot rebalance recommendation |

Phân tán nhiều instance type và AZ có thể cải thiện khả năng tìm capacity. Nhưng **không trộn các loại kiến trúc CPU (ví dụ x86 và Arm) nếu AMI, binary hoặc container image không tương thích**. Khi dùng instance weighting, các metric như CPU trung bình và số request/target phải được đánh giá cùng sự khác biệt về năng lực thật giữa các loại instance.

**Capacity Rebalancing** có thể khởi chạy instance thay thế sớm khi Spot có tín hiệu rủi ro bị gián đoạn; nó không bảo đảm sẽ luôn tìm được Spot mới hoặc giữ nguyên toàn bộ phiên ứng dụng. Cần drain request, checkpoint, retry và On-Demand capacity phù hợp.

## 8. Lifecycle hooks, warm pools và bảo vệ scale-in

### 8.1. Lifecycle hook dùng khi nào?

**Lifecycle hooks** cho phép ASG tạm dừng ở một số giai đoạn như launch hoặc terminate để một quy trình bên ngoài thực hiện tác vụ bổ sung. Ví dụ:

- **Launch hook:** cài chứng chỉ, cấu hình agent, đăng ký dịch vụ, warm cache hoặc xác nhận app đã sẵn sàng.
- **Terminate hook:** ngừng nhận công việc mới, xả hàng đợi, cập nhật trạng thái, gửi log/checkpoint.

Hook có **heartbeat timeout**, **global timeout** và **default result** theo cấu hình. Một hook không được hoàn tất đúng cách có thể làm instance ở trạng thái chờ quá lâu hoặc kết thúc không như dự tính. Khi hoàn thành, hệ thống có thể gửi tín hiệu **CONTINUE** hoặc **ABANDON** phù hợp; kết quả tác động khác nhau theo loại hook. Cần thử chính xác luồng sự kiện với EventBridge, Lambda, SQS hoặc cơ chế xử lý được chọn.

### 8.2. Warm pool

**Warm pool** giữ sẵn một nhóm instance đã được khởi tạo hoặc dừng theo chế độ hỗ trợ để giảm thời gian scale-out đối với ứng dụng bootstrap lâu. Khi cần thêm capacity, ASG có thể chuyển một instance từ warm pool sang phục vụ.

Đánh giá **chi phí EBS/storage và những tài nguyên còn tính phí**, thời gian hồi phục instance, trạng thái cache/credential và logic ứng dụng sau khi resume/start. Warm pool **không bảo đảm không còn thời gian warmup**, và không phải mọi workload hỗ trợ hibernate hoặc các trạng thái pool như nhau.

### 8.3. Instance scale-in protection

**Scale-in protection** bảo vệ một instance khỏi việc bị chọn chấm dứt trong **hoạt động scale-in**. Nó hữu ích khi một worker đang xử lý batch không thể dừng ngay. Nhưng nó **không phải** biện pháp bảo vệ tuyệt đối khỏi tất cả lý do terminate: cần hiểu riêng hành vi thay instance unhealthy, Spot interruption, instance refresh và thao tác quản trị.

Không gắn protection vĩnh viễn cho toàn bộ nhóm, bởi ASG có thể không giảm được capacity, chi phí tăng và chính sách scaling trở nên khó dự đoán. Worker nên chủ động bỏ protection sau khi kết thúc công việc hoặc chuyển sang cơ chế queue/checkpoint phù hợp.

## 9. Cập nhật ứng dụng và instance refresh

### 9.1. Vì sao cần instance refresh?

Giả sử ASG đang chạy launch template **version 1** với AMI cũ. Bạn phát hành AMI mới và tạo **version 2**; các instance đang chạy từ version 1 **không tự được nâng cấp**. Để triển khai đồng đều, **Instance Refresh** có thể thay instance theo từng đợt dựa trên launch template/version mong muốn và các preference được cấu hình.

~~~mermaid
flowchart LR
    LT1["Launch template v1"] --> OLD["ASG đang dùng EC2 v1"]
    NEW["AMI / cấu hình mới"] --> LT2["Launch template v2"]
    LT2 --> REF["Instance Refresh<br/>Giới hạn máy không khỏe"]
    OLD --> REF
    REF --> CAN["Thay instance theo đợt"]
    CAN --> HEALTH["Health checks + metric"]
    HEALTH --> DONE["Toàn ASG đạt cấu hình mục tiêu"]
~~~

### 9.2. Quy trình phát hành có kiểm soát

1. Tạo AMI/application artifact mới, thử khởi động, xác nhận IAM/SG/EBS/user data/IMDSv2.
2. Tạo launch template version mới và kiểm tra diff so với version đang chạy.
3. Chọn ASG, xác định **desired configuration**, min/max healthy percentages, **instance warmup**, checkpoint và thời gian bảo đảm ứng dụng sẵn sàng.
4. Bắt đầu refresh theo từng đợt; theo dõi trạng thái ASG, target group, HTTP 5xx, latency và capacity.
5. Nếu gặp lỗi, dừng/rollback theo cơ chế hỗ trợ; xác nhận **version cũ có thể chạy lại**, và dữ liệu/schema vẫn tương thích.
6. Khi hoàn tất, kiểm tra toàn bộ instance/AMI/version và ghi lại bản phát hành đã triển khai.

**Chọn tỷ lệ healthy hợp lý:** nếu desired capacity chỉ có 2 instance, một sai lệch nhỏ trong số máy healthy đã có tác động lớn. Cần tính **dư địa MaxSize/quota** và khả năng tạo máy mới trước khi chấm dứt máy cũ, nhất là khi yêu cầu zero-downtime.

**Dữ liệu và schema:** instance refresh xử lý các EC2 instance, không tự triển khai migration database an toàn. Với rollout ứng dụng có thay đổi schema, áp dụng cơ chế tương thích ngược, migration theo giai đoạn và đánh giá rollback độc lập.

## 10. Thực hành AWS CLI: tạo launch template và ASG minh họa

Các lệnh dưới đây là **mẫu học tập**, không tự thực thi. Chạy trong tài khoản/lab được phép, kiểm tra quyền IAM, quota, subnet, target group, AMI và chi phí trước khi tạo tài nguyên. Các placeholder phải được thay bằng giá trị có thật. Ví dụ giả định một ứng dụng Linux đã có AMI bootstrap sẵn, target group ALB có health check phù hợp và hai subnet ở hai AZ.

### 10.1. Tạo launch template

Ví dụ nội dung tệp đầu vào **launch-template-data.json** trong lab:

~~~json
{
  "ImageId": "ami-REPLACE_WITH_VALID_AMI",
  "InstanceType": "t3.small",
  "SecurityGroupIds": [
    "sg-REPLACE_WITH_APP_SG"
  ],
  "IamInstanceProfile": {
    "Name": "app-instance-profile"
  },
  "MetadataOptions": {
    "HttpEndpoint": "enabled",
    "HttpTokens": "required",
    "HttpPutResponseHopLimit": 1
  },
  "BlockDeviceMappings": [
    {
      "DeviceName": "/dev/xvda",
      "Ebs": {
        "VolumeType": "gp3",
        "Encrypted": true,
        "DeleteOnTermination": true
      }
    }
  ]
}
~~~

AMI, security group, profile name và **DeviceName** phải khớp image/hạ tầng đã chọn; đặc biệt một AMI có thể dùng tên root device khác. Nếu dùng container, kiểm tra hop limit thay vì sao chép giá trị 1 cho mọi môi trường.

~~~bash
aws ec2 create-launch-template \
  --region ap-southeast-1 \
  --launch-template-name web-app-lt \
  --version-description "web-app-v1" \
  --launch-template-data file://launch-template-data.json
~~~

Lệnh tạo LT chỉ lưu cấu hình, **chưa tạo EC2 instance**. Kiểm tra template và version sau khi tạo:

~~~bash
aws ec2 describe-launch-template-versions \
  --region ap-southeast-1 \
  --launch-template-name web-app-lt \
  --versions 1 \
  --query 'LaunchTemplateVersions[].[VersionNumber,VersionDescription,LaunchTemplateData.ImageId]' \
  --output table
~~~

### 10.2. Tạo ASG ở hai AZ và gắn target group

~~~bash
aws autoscaling create-auto-scaling-group \
  --region ap-southeast-1 \
  --auto-scaling-group-name web-app-asg \
  --launch-template "LaunchTemplateName=web-app-lt,Version=1" \
  --min-size 2 \
  --max-size 6 \
  --desired-capacity 2 \
  --vpc-zone-identifier "subnet-REPLACE_A,subnet-REPLACE_B" \
  --target-group-arns "arn:aws:elasticloadbalancing:ap-southeast-1:111122223333:targetgroup/REPLACE_NAME/REPLACE_ID" \
  --health-check-type ELB \
  --health-check-grace-period 300 \
  --default-instance-warmup 180
~~~

Hai subnet cần thuộc **hai AZ** và phù hợp kiến trúc mạng. Target group phải được tạo đúng VPC, target type tương thích và được ALB listener tham chiếu theo thiết kế. Các số **300 giây** và **180 giây** chỉ là ví dụ: đo thời gian bootstrap thực tế để điều chỉnh. Tài khoản cũng phải có quota và capacity EC2 phù hợp.

### 10.3. Thêm target tracking scaling

Ví dụ giữ mức CPU trung bình mục tiêu khoảng **50%**:

~~~bash
aws autoscaling put-scaling-policy \
  --region ap-southeast-1 \
  --auto-scaling-group-name web-app-asg \
  --policy-name cpu-target-50 \
  --policy-type TargetTrackingScaling \
  --target-tracking-configuration '{"PredefinedMetricSpecification":{"PredefinedMetricType":"ASGAverageCPUUtilization"},"TargetValue":50.0}'
~~~

Policy này chỉ thực sự hữu ích khi CPU liên quan đến mức tiêu thụ công suất của ứng dụng. Nó không tự tạo nên khả năng chịu tải của database hay dịch vụ phụ trợ.

### 10.4. Xem trạng thái ASG và lịch sử scaling

~~~bash
aws autoscaling describe-auto-scaling-groups \
  --region ap-southeast-1 \
  --auto-scaling-group-names web-app-asg \
  --query 'AutoScalingGroups[].{Name:AutoScalingGroupName,Min:MinSize,Desired:DesiredCapacity,Max:MaxSize,Instances:Instances[].[InstanceId,LifecycleState,HealthStatus]}' \
  --output json

aws autoscaling describe-scaling-activities \
  --region ap-southeast-1 \
  --auto-scaling-group-name web-app-asg \
  --max-items 20 \
  --output json
~~~

Kiểm tra cả **ALB target health** và metric ứng dụng để biết máy có thực sự nhận request, không chỉ trạng thái instance **InService** trong ASG.

### 10.5. Tạo version mới và khởi động instance refresh

Sau khi tạo version 2 của launch template bằng quy trình được phê duyệt, một ví dụ khởi động refresh:

~~~bash
aws autoscaling start-instance-refresh \
  --region ap-southeast-1 \
  --auto-scaling-group-name web-app-asg \
  --desired-configuration '{"LaunchTemplate":{"LaunchTemplateName":"web-app-lt","Version":"2"}}' \
  --preferences '{"MinHealthyPercentage":90,"InstanceWarmup":180}'
~~~

Đây là lệnh **có thể thay EC2 đang chạy**, cần đánh giá trước số lượng healthy, capacity/quota, chính sách termination và rollback. Với nhóm rất nhỏ, cần tính khả năng làm tròn healthy percentage và thời gian máy thay thế sẵn sàng. Theo dõi bằng:

~~~bash
aws autoscaling describe-instance-refreshes \
  --region ap-southeast-1 \
  --auto-scaling-group-name web-app-asg \
  --output table
~~~

## 11. Giám sát sức khỏe, mở rộng và chi phí

### 11.1. Bộ metric nên theo dõi

| Nhóm | Metric/signal | Tác động đến quyết định |
|---|---|---|
| **ASG capacity** | **GroupDesiredCapacity**, **GroupInServiceInstances**, **GroupPendingInstances**, **GroupTerminatingInstances** | Desired đã được đáp ứng chưa, có máy kẹt launch/terminate không |
| **ASG scaling activities** | StatusCode, StatusMessage, nguyên nhân scaling thất bại | Thiếu quota, capacity, AMI, IAM hoặc cấu hình mạng |
| **EC2** | CPUUtilization, StatusCheckFailed, memory/disk custom metrics khi cần | Tìm bottleneck, lỗi máy và sizing instance |
| **ALB target group** | HealthyHostCount, UnHealthyHostCount, TargetResponseTime, HTTPCode_Target_5XX_Count | Target có sẵn sàng và phục vụ đúng SLO không |
| **Lưu lượng** | RequestCount, RequestCountPerTarget, latency p95/p99 ở lớp ứng dụng | Scale theo demand và phát hiện tăng lỗi |
| **Chi phí** | EC2 hours, EBS, ALB LCU, data transfer, CloudWatch, NAT, Spot | Đánh giá hiệu quả sau khi bật scaling |

Một số **ASG group metrics** cần được bật collection để xuất số liệu tương ứng. EC2 memory utilization không phải metric cơ bản mặc định từ mọi instance; có thể cần **CloudWatch Agent/custom metric**. Thiết kế cảnh báo phân biệt **không đủ capacity**, **tài nguyên không khỏe**, **lỗi ứng dụng** và **mở rộng không hiệu quả**.

### 11.2. Kiểm tra scaling đúng cách

1. Bắt đầu bằng một baseline: desired, số target healthy, CPU/request, latency và chi phí theo giờ.
2. Tạo tải có kiểm soát trong lab và quan sát metric mục tiêu, scaling activity, số EC2 Pending/InService và thời gian tới lúc target healthy.
3. Xem hệ thống có đáp ứng SLO sau scale-out và backend còn đủ năng lực không.
4. Ngừng tải, kiểm tra hệ thống scale-in từ từ, không chấm dứt worker còn xử lý tác vụ.
5. Kiểm tra một instance unhealthy được ASG thay thế; thử tình huống lỗi AZ bằng phương án diễn tập được hỗ trợ.
6. Đo tổng thời gian phục hồi, mất request, tỷ lệ lỗi và mức chi phí thay đổi, rồi điều chỉnh policy.

### 11.3. Chi phí cần tính thực tế

**EC2 Auto Scaling không có phí riêng cho việc tạo ASG theo mô hình dịch vụ thông thường**, nhưng bạn trả tiền cho **EC2 On-Demand/Spot, EBS, ALB, CloudWatch, network/data transfer, NAT gateway, KMS, lưu trữ log** và các dịch vụ đi kèm theo bảng giá áp dụng. Để dự toán:

- Xác định **số máy nền** và số giờ phải duy trì dù lưu lượng thấp.
- Ước lượng thời gian chạy ở các mức tải và số máy tăng thêm.
- Kiểm tra tác động **instance warmup**, warm pool, scale-in protection và policies không cho giảm capacity.
- Tính công suất dự phòng khi mất một AZ, khả năng dùng Spot và chi phí thay thế.
- So sánh với mô hình không cần quản trị máy như ECS Fargate hoặc Lambda nếu ứng dụng phù hợp, nhưng không quyết định chỉ dựa vào giá EC2 theo giờ.

## 12. Các lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân khả dĩ | Bước kiểm tra |
|---|---|---|
| ASG không tạo được instance | AMI/instance type không phù hợp, quota, thiếu capacity, permission/launch template sai | **Scaling activities**, EC2 quota, launch template version, IAM instance profile |
| Instance vào ASG rồi bị thay liên tục | Health check không đạt, bootstrap chậm, grace period quá ngắn | **ALB target health reason**, EC2 status, app logs, timing |
| ALB trả 503 | Không có target healthy hoặc routing/target group cấu hình sai | Listener, target registration, health path, SG, cổng |
| EC2 InService nhưng request lỗi | App chưa ready hoặc ASG không dùng trạng thái ALB như mong muốn | HealthCheckType, target group health, logs |
| CPU cao nhưng không scale-out | Thiếu scaling policy, MaxSize, metric sai, policy bị tạm dừng hoặc thiếu data | Scaling policy, group limits, CloudWatch metrics, suspended processes |
| Scale-out nhiều nhưng latency không giảm | Bottleneck ở DB, I/O, downstream service hoặc sticky session | Tracing, DB connections, app metrics, load test |
| Scale-in cắt ngang job | Không có graceful shutdown, lifecycle hooks hoặc checkpoint | Termination handling, queue retry, protection phù hợp |
| Tạo launch template version mới nhưng ASG vẫn chạy AMI cũ | ASG pin version cũ, chưa instance refresh | ASG launch template version, danh sách instance AMIs |
| ASG chạy hỗn hợp hai version ngoài dự tính | Dùng **$Latest/$Default** hoặc rollout dang dở | Version trong từng instance, scaling activities, refresh |
| Spot instance biến mất | Spot interruption hoặc thiếu capacity pool | Spot events, Capacity Rebalancing, On-Demand base |
| Instance tăng chi phí khi tải đã giảm | Warmup/cooldown, MinSize cao, protection, policy không scale-in | Desired vs Min/Max, group metrics, warm pool và billing |
| Scale-out thất bại trong private subnet | User data cần Internet nhưng không có NAT/endpoints hoặc secret policy sai | Cloud-init, route, VPC endpoints, IAM và DNS |

## 13. Tình huống thực hành

### Tình huống A — Web API có tải biến động

Ứng dụng Java chạy EC2, có thể phục vụ đồng thời trên nhiều máy. Lưu session và dữ liệu lâu dài ở dịch vụ ngoài EC2. Traffic tăng vào khung giờ trưa; hiện đang dùng một instance duy nhất.

**Câu hỏi:** kiến trúc mở rộng phù hợp là gì?

**Gợi ý:** tạo launch template với AMI đã kiểm thử, role tối thiểu, IMDSv2, security group, EBS mã hóa. Tạo ASG trải hai AZ, min/desired từ 2, gắn ALB target group, health check **/ready**, đặt target tracking dựa theo CPU hoặc request count phù hợp. Kiểm tra load test và backend khi scale-out.

### Tình huống B — AMI mới nhưng không máy nào được cập nhật

Nhóm xây AMI v2, thêm version 2 của launch template. Tuy nhiên ASG vẫn có toàn bộ máy đang chạy phiên bản cũ.

**Câu hỏi:** tại sao và cần làm gì?

**Gợi ý:** tạo launch template version không thay thế instance hiện hữu. Xác minh ASG đang tham chiếu version nào, cập nhật desired configuration và chạy **instance refresh** theo đợt. Kiểm tra target health, thời gian warmup, capacity headroom và rollback.

### Tình huống C — Bật Spot để giảm chi phí

Worker xử lý ảnh nhận tác vụ từ SQS và có thể retry. Nhóm muốn giảm chi phí nhưng không muốn mất job khi Spot instance bị gián đoạn.

**Câu hỏi:** cần thay đổi thiết kế thế nào?

**Gợi ý:** chọn mixed instances/on-demand base hợp lý, nhiều Spot pools/AZ, bật Capacity Rebalancing khi phù hợp. Worker nhận message theo cách idempotent, có visibility timeout, checkpoint và graceful shutdown; nếu instance bị thu hồi, job được thử lại. Scale có thể dựa trên queue backlog per instance; đánh giá capacity bằng năng lực xử lý thực thay vì chỉ số lượng máy.

### Tình huống D — Scale-out nhưng ứng dụng vẫn chậm

ASG tăng từ 2 lên 6 EC2, CPU mỗi máy thấp nhưng p95 latency không cải thiện. Database báo số kết nối tăng và thời gian truy vấn dài.

**Câu hỏi:** có nên tăng MaxSize lên 20?

**Gợi ý:** chưa. Kiểm tra database bottleneck, query/index, connection pooling, cache và tracing. Thêm EC2 có thể khiến backend quá tải; tối ưu hoặc mở rộng tầng nghẽn trước khi thay chính sách scaling.

### Tình huống E — Scale-in làm mất tác vụ

Ứng dụng xử lý một file trong 15 phút trên mỗi EC2. Khi CPU giảm, ASG scale-in và terminate một máy đang xử lý khiến kết quả chưa được lưu.

**Câu hỏi:** nên giải quyết bằng cách tăng MinSize?

**Gợi ý:** tăng MinSize không giải quyết đúng bản chất. Dùng hàng đợi, checkpoint, idempotent retry, lifecycle hook hoặc instance scale-in protection trong lúc có tác vụ, cùng cơ chế graceful shutdown và thời gian chờ thích hợp. Cần kiểm tra timeout, chi phí và tác động khi spot/instance lỗi bất ngờ.

## 14. Checklist đưa Launch Template và ASG vào production

- [ ] Đã có **AMI/launch template version** có thể tái tạo và kiểm soát thay đổi.
- [ ] Đã cấu hình đúng IAM instance profile, SG, mã hóa EBS, IMDSv2 và secret retrieval.
- [ ] Đã xác nhận user data/bootstrap idempotent, không giữ dữ liệu nghiệp vụ duy nhất trên root disk.
- [ ] Đã chọn **MinSize, DesiredCapacity, MaxSize** dựa trên tải, SLO và năng lực phục hồi.
- [ ] Đã triển khai ASG qua nhiều AZ theo nhu cầu và thử ứng dụng khi một AZ/instance lỗi.
- [ ] Đã gắn ALB/target group đúng VPC, health check path, grace period và warmup.
- [ ] Đã chọn scaling metric thực sự tương quan với capacity, không chỉ sử dụng CPU theo thói quen.
- [ ] Đã kiểm tra lifecycle hooks, graceful shutdown, draining, scale-in protection và warm pool nếu cần.
- [ ] Đã kiểm tra hỗ trợ mixed instances/Spot, khả năng gián đoạn và On-Demand capacity dự phòng nếu áp dụng.
- [ ] Đã thiết kế quy trình phát hành **version mới + instance refresh + rollback**.
- [ ] Đã thiết lập CloudWatch metrics/alerts, scaling activities và log để điều tra lỗi.
- [ ] Đã benchmark scale-out/scale-in, health replacement và tính TCO ở các kịch bản tải.

## 15. Ghi nhớ

**Launch template** định nghĩa cách tạo một EC2 instance; **Auto Scaling Group** duy trì và điều chỉnh capacity; **scaling policy** quyết định khi nào tăng/giảm; **ALB và target group** điều phối lưu lượng đến những máy khỏe mạnh. Để mở rộng an toàn, cần phối hợp **Multi-AZ, ứng dụng stateless, health checks, warmup, IAM least privilege, version pinning, instance refresh, xử lý shutdown và giám sát**. Tăng số EC2 không tự sửa được bottleneck ở database hoặc dependency khác.

### Tài liệu AWS chính thức để đối chiếu khi triển khai

- [EC2 Launch Templates](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-launch-templates.html) — cấu hình và quản lý phiên bản template.
- [Create an Auto Scaling Group using a launch template](https://docs.aws.amazon.com/autoscaling/ec2/userguide/create-asg-launch-template.html) — liên kết template với ASG.
- [How Amazon EC2 Auto Scaling works](https://docs.aws.amazon.com/autoscaling/ec2/userguide/what-is-amazon-ec2-auto-scaling.html) — desired capacity, thay thế instance và phân bố AZ.
- [Health checks for Auto Scaling instances](https://docs.aws.amazon.com/autoscaling/ec2/userguide/health-checks-overview.html) — các nguồn kiểm tra sức khỏe.
- [Attach a load balancer to an Auto Scaling Group](https://docs.aws.amazon.com/autoscaling/ec2/userguide/attach-load-balancer-asg.html) — target group, ELB health và tích hợp ALB.
- [Target tracking scaling policies](https://docs.aws.amazon.com/autoscaling/ec2/userguide/as-scaling-target-tracking.html) — metric mục tiêu và instance warmup.
- [Step scaling policies](https://docs.aws.amazon.com/autoscaling/ec2/userguide/as-scaling-simple-step.html) — alarm, step adjustments.
- [Auto Scaling groups with multiple instance types](https://docs.aws.amazon.com/autoscaling/ec2/userguide/ec2-auto-scaling-mixed-instances-groups.html) — mixed instances, On-Demand và Spot.
- [Instance refresh](https://docs.aws.amazon.com/autoscaling/ec2/userguide/asg-instance-refresh.html) — cập nhật/khôi phục đội instance.
- [Lifecycle hooks](https://docs.aws.amazon.com/autoscaling/ec2/userguide/lifecycle-hooks.html) — tác vụ khi launch/terminate.
- [Monitor Amazon EC2 Auto Scaling](https://docs.aws.amazon.com/autoscaling/ec2/userguide/monitoring-overview.html) — metric, sự kiện và nhật ký hoạt động.
- [AWS Pricing Calculator](https://calculator.aws/) — dự toán EC2, EBS, ALB và các dịch vụ liên quan.

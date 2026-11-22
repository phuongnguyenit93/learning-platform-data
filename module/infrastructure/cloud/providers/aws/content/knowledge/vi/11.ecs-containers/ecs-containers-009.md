# ECS Service Auto Scaling và capacity provider

> **Chương:** Container với ECS  
> **Module:** CLOUD_PROVIDERS_AWS — khám phá AWS từ Region/Availability Zone (AZ), IAM, VPC, các dịch vụ tính toán và lưu trữ tới database, tích hợp và serverless; rèn khả năng lựa chọn dịch vụ, triển khai ứng dụng an toàn, có giám sát, khả năng phục hồi và kiểm soát chi phí.

## Mục tiêu học tập

Sau bài học, người học có thể:

1. Phân biệt **Amazon ECS Service Auto Scaling** (thay đổi **số lượng task**) với **capacity provider** (xác định và quản lý **năng lực chạy task**).
2. Cấu hình tư duy cho **Application Auto Scaling**: scalable target, **MinCapacity/MaxCapacity**, target tracking, step scaling, scheduled scaling và loại metric phù hợp.
3. Hiểu những thành phần và giới hạn của **FARGATE**, **FARGATE_SPOT**, **Auto Scaling group capacity provider** và **Amazon ECS Managed Instances**.
4. Tính ý nghĩa của **base**, **weight** và các quy tắc lựa chọn capacity provider strategy; giải thích vì sao tỷ lệ task thực tế không luôn đúng một tỷ lệ lý thuyết.
5. Mô tả cách **ECS managed scaling** tăng/giảm EC2 Auto Scaling group thông qua **CapacityProviderReservation** và mục tiêu **targetCapacity**.
6. Thiết kế mở rộng cho ứng dụng HTTP qua ALB hoặc worker đọc SQS, kết hợp health check, rolling deployment, multi-AZ, IAM và VPC.
7. Phát hiện các lỗi **RUNNING thấp hơn desiredCount**, task ở **PROVISIONING/PENDING**, Fargate Spot không đủ capacity, scale-in quá sớm hoặc chi phí tăng; dùng AWS CLI chỉ đọc để điều tra.

## 1. Hai vòng Auto Scaling khác nhau trong ECS

Một hệ thống ECS có thể cần mở rộng ở **hai tầng**:

- **Tầng ứng dụng (Service Auto Scaling):** “Cần chạy bao nhiêu bản sao của ứng dụng?” → điều chỉnh **desiredCount** của ECS Service.
- **Tầng hạ tầng (Capacity Provider / Cluster Auto Scaling):** “Những task đó sẽ chạy **ở đâu**, và có đủ CPU/RAM/khả năng đặt task không?” → cung cấp compute capacity thích hợp.

Hai vòng này **liên quan nhưng không đồng nhất**. Chỉ tăng desiredCount không làm một EC2 instance nhỏ tự có thêm bộ nhớ; chỉ thêm EC2 cũng không khiến ECS Service tự tăng số bản sao khi desiredCount không đổi.

~~~mermaid
flowchart TB
    L["Lưu lượng / hàng đợi / metric"] --> CW["CloudWatch metric và policy"]
    CW --> AAS["Application Auto Scaling"]
    AAS -->|"Điều chỉnh desiredCount"| S["ECS Service scheduler"]
    S -->|"Đặt thêm task"| CP["Capacity provider strategy"]
    CP --> F["Fargate / Fargate Spot"]
    CP --> EC2["EC2 Auto Scaling group capacity provider"]
    CP --> MI["ECS Managed Instances capacity provider"]
    EC2 --> CAS["ECS managed scaling: ASG DesiredCapacity"]
    CAS --> H["Thêm/bớt EC2 container instances"]
    H --> T["Task chuyển RUNNING khi đủ resource"]
    F --> T
    MI --> T
~~~

**Đây là sơ đồ logic:** ECS scheduler đặt task theo strategy, constraints và trạng thái capacity. Service Auto Scaling không trực tiếp gọi Auto Scaling group để tăng instance; capacity provider mới là thành phần liên quan đến cấp năng lực hạ tầng.

### 1.1. Tình huống dễ nhầm

Một ECS Service có:

- **desiredCount = 8**.
- **runningCount = 4**.
- Bốn task còn lại chưa thể được đặt vì EC2 cluster thiếu RAM.

Ứng dụng đang **thiếu capacity compute**, không nhất thiết là Service Auto Scaling không hoạt động. Nếu nhóm chỉ tăng desiredCount từ 8 lên 12 thì số task chờ có thể tăng, không giải quyết thiếu RAM.

Ngược lại, một cluster EC2 có 10 instance rảnh nhưng ECS Service **desiredCount = 2**, ECS scheduler không tự chạy 20 bản sao chỉ vì hạ tầng còn trống.

### 1.2. Tương quan khái niệm

| Thành phần | Nó điều khiển | Không tự điều khiển |
| --- | --- | --- |
| **ECS Service** | Số task mong muốn và việc duy trì task theo service deployment. | Không tự tăng EC2 chỉ vì có service. |
| **Application Auto Scaling** | Thay đổi **desiredCount** trong phạm vi policy. | Không quản lý trực tiếp EC2 ASG của cluster. |
| **Capacity provider strategy** | Task được phân bổ vào các loại/nhóm capacity nào. | Không phải metric scale-out theo lưu lượng. |
| **FARGATE / FARGATE_SPOT** | Compute Fargate cho mỗi task phù hợp. | Không đảm bảo Spot luôn còn capacity. |
| **EC2 ASG capacity provider** | Quan hệ giữa ECS tasks và EC2 Auto Scaling group; có thể bật managed scaling. | Không thay metric/ngưỡng của Service Auto Scaling. |
| **ECS Managed Instances** | Hạ tầng EC2 được ECS quản lý nhiều công đoạn hơn. | Không thay quyền IAM, dữ liệu và logic ứng dụng. |
| **ALB** | Nhận request, cân bằng tới healthy targets. | Không tự quyết định task count nếu chưa có scaling policy. |

## 2. Nền tảng ECS trước khi Auto Scaling

### 2.1. Cluster, task definition, task và service

- **ECS Cluster:** không gian quản lý logic cho services, tasks và capacity providers.
- **Task definition:** định nghĩa image, CPU, memory, ports, environment, logs, IAM roles và các thông số chạy container.
- **Task:** một lần chạy task definition cụ thể.
- **ECS Service:** duy trì số lượng task theo **desiredCount**, xử lý placement và deployment.
- **Capacity provider:** chỉ định nguồn compute được phép dùng để chạy task.
- **Capacity provider strategy:** quy tắc phân phối task giữa các providers trong một họ capacity tương thích.

ECS Service có scheduling strategy khác nhau; phần Service Auto Scaling ở đây tập trung vào **REPLICA**, không áp dụng cách điều chỉnh desiredCount tương tự cho **DAEMON**. DAEMON được dùng để chạy một task trên những EC2 container instances thỏa điều kiện tương ứng.

### 2.2. DesiredCount, RunningCount và PendingCount

Giả sử console hiển thị:

| Thuộc tính | Giá trị | Ý nghĩa |
| --- | ---: | --- |
| **desiredCount** | 6 | Service scheduler muốn duy trì sáu task. |
| **runningCount** | 4 | Bốn task đã ở trạng thái RUNNING. |
| **pendingCount** | 2 | Hai task chưa đến RUNNING theo trạng thái hiển thị. |

Không thể kết luận ứng dụng có thể phục vụ đủ tải chỉ vì **desiredCount = 6**. Cần kiểm tra trạng thái từng task, **health của container**, ALB target health và khả năng nhận traffic của ứng dụng.

Khi service triển khai task definition mới, có thể tồn tại task cũ/mới cùng lúc theo **deploymentConfiguration.minimumHealthyPercent**, **maximumPercent** và deployment strategy. Đọc deployment details trước khi so sánh số lượng task với desiredCount.

### 2.3. CPU và RAM task definition ảnh hưởng placement

Ví dụ một task Fargate có yêu cầu:

~~~json
{
  "family": "orders-api",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "512",
  "memory": "1024",
  "containerDefinitions": [
    {
      "name": "api",
      "image": "111122223333.dkr.ecr.ap-southeast-1.amazonaws.com/orders-api:release-42",
      "essential": true,
      "portMappings": [{"containerPort": 8080, "protocol": "tcp"}]
    }
  ]
}
~~~

Đây là **task definition minh họa rút gọn**, không phải template production đầy đủ. Giá trị task-level **cpu/memory** phải tương thích với Fargate theo những tổ hợp AWS hỗ trợ. Khi dùng EC2, resource yêu cầu cũng cần phù hợp compute của EC2 instance và các constraints như ports, ENI, GPU hoặc kiến trúc CPU.

Nếu container cần 2 GiB để chạy nhưng task definition chỉ cấp 1 GiB, tăng số lượng task **không giải quyết lỗi OOMKilled của mỗi task**. Phải điều chỉnh right-sizing và khả năng placement.

## 3. ECS Service Auto Scaling hoạt động ra sao?

ECS sử dụng **Application Auto Scaling** để tăng/giảm số task của ECS Service. Đối tượng có thể được scale được định danh bằng:

~~~text
Service namespace: ecs
Resource ID:       service/<cluster-name>/<service-name>
Scalable dimension: ecs:service:DesiredCount
~~~

Dấu **<cluster-name>** và **<service-name>** là placeholder, cần thay bằng tên thực. Application Auto Scaling tạo và quản lý các CloudWatch alarm cho các policy cần alarm.

### 3.1. Ba thành phần của một scalable target

| Thành phần | Chức năng | Ví dụ |
| --- | --- | --- |
| **MinCapacity** | Số task tối thiểu mà policy thường được phép thu xuống. | 2 |
| **MaxCapacity** | Số task tối đa mà policy thường được phép tăng lên. | 20 |
| **Scaling policy** | Metric và điều kiện thay đổi task count. | Target CPU 60%. |

Một service có MinCapacity 2, MaxCapacity 20 **không** đồng nghĩa chạy sẵn 20 task. Service chạy theo desiredCount hiện hành và các hoạt động scaling. Tăng MaxCapacity chỉ nới giới hạn, không tự tăng số task nếu không có điều kiện scale-out.

### 3.2. Metric mẫu của Service Auto Scaling

AWS hỗ trợ các predefined metrics thông dụng:

- **ECSServiceAverageCPUUtilization:** CPU utilization trung bình của ECS Service.
- **ECSServiceAverageMemoryUtilization:** memory utilization trung bình của ECS Service.
- **ALBRequestCountPerTarget:** số request trên mỗi target trong khoảng đo tương ứng khi service dùng ALB/target group theo điều kiện hỗ trợ.

Có thể dùng **custom CloudWatch metrics** được thiết kế đúng, ví dụ **queue backlog trên mỗi task** cho worker. Metric tốt phải phản ánh tải theo cách **tăng capacity thì metric có xu hướng giảm** ở cùng mức công việc, nếu dùng target tracking.

Lưu ý: ALBRequestCountPerTarget có giới hạn theo deployment type; tài liệu AWS chỉ rõ **không hỗ trợ** target tracking metric đó cho dịch vụ dùng **blue/green deployment type** tương ứng.

### 3.3. Target tracking — duy trì metric quanh ngưỡng

**Target tracking** là cách thường được chọn trước vì bạn định nghĩa một mục tiêu (ví dụ CPU 60%), hệ thống tự tính toán scale-out hoặc scale-in để hướng metric về mục tiêu.

Ví dụ:

- ECS Service có 4 task đang chạy.
- CPU trung bình đang là 90%.
- Target CPU là 60%.
- Có đủ tài nguyên để chạy thêm task.

Một ước lượng trực quan:

\[
\text{Số task cần} \approx
\text{task hiện có} \times
\frac{\text{utilization hiện tại}}{\text{target}}
=4\times\frac{90}{60}\approx6
\]

Con số **6 chỉ là ước lượng giải thích**, **không phải cam kết thuật toán ECS sẽ luôn thêm đúng hai task**. Application Auto Scaling xét CloudWatch samples, cooldown, min/max, số task RUNNING thực tế, cách làm tròn và trạng thái hệ thống.

### 3.4. Scale-out và scale-in không đối xứng

Mục tiêu vận hành thường ưu tiên **khả dụng**:

- **Scale-out:** tăng task khi tải tăng. Hệ thống có thể phản ứng tương đối nhanh, tùy chu kỳ metric và cooldown.
- **Scale-in:** giảm task thận trọng hơn để tránh giảm capacity trong lúc request còn được xử lý.
- **Scale-out cooldown:** hạn chế lặp scale-out quá nhanh, nhưng hành vi của scaling activity lớn hơn có ngoại lệ theo AWS.
- **Scale-in cooldown:** tránh liên tục loại bớt task. Khi tải tăng đột ngột, scale-out có thể thắng scale-in cooldown theo behavior được tài liệu hóa.

Thiết lập cooldown phù hợp **thời gian khởi động ứng dụng**, registration vào target group, warm-up và độ trễ metric. Nếu task cần 2 phút tải model trước khi ready mà scale-out cooldown quá ngắn, hệ thống có thể tăng task quá nhiều khi chưa thấy lợi ích của đợt tăng trước.

### 3.5. Nhiều target tracking policies đồng thời

Ví dụ service dùng hai policy:

- CPU target = 60%.
- Memory target = 75%.

Quy tắc tổng quát của Application Auto Scaling cho những policy target tracking trên metric khác nhau:

- **Scale-out khi bất kỳ policy nào cần scale-out**.
- **Scale-in khi mọi policy có scale-in enabled đều đủ điều kiện scale-in**.

Do đó CPU tăng cao có thể khiến số task tăng dù memory thấp. Ngược lại CPU thấp chưa đủ để scale-in nếu memory vẫn còn cao. Điều này ưu tiên giữ đủ capacity.

Không nên tạo hai target tracking policies trùng metric chỉ để “ép” scale nhanh hơn; tài liệu yêu cầu mỗi target tracking policy trên cùng scalable target sử dụng metric khác nhau. Tránh chỉnh sửa các CloudWatch alarms do Application Auto Scaling tự quản lý.

### 3.6. Missing metrics và scale-to-zero

CloudWatch metric có thể thiếu dữ liệu khi không có task nào đang chạy. Target tracking **không coi thiếu dữ liệu là utilization bằng 0**.

Nếu muốn **MinCapacity = 0**:

1. Xác định ứng dụng có chấp nhận cold start hay không.
2. Chọn metric **vẫn đo được demand khi không còn task**, ví dụ số message tồn trong SQS, một custom backlog metric hoặc kích hoạt ngoài.
3. Khi metric thể hiện demand từ 0 task, target tracking có thể chờ một data point và bắt đầu scale-out ở mức tối thiểu theo behavior AWS.
4. Kiểm thử khả năng tự khởi động lại từ 0 thay vì chỉ kiểm tra scale-in về 0.

**Không nên mặc định CPU utilization của service có thể kích hoạt scale-out từ zero task**, vì khi không có task chạy sẽ không còn CPU metric tương ứng để cho biết có công việc mới.

## 4. Các chế độ scaling và khi nào chọn

Amazon ECS thông qua Application Auto Scaling hỗ trợ nhiều cách thiết lập quy mô.

| Phương án | Cách hoạt động | Trường hợp thích hợp | Lưu ý |
| --- | --- | --- | --- |
| **Target tracking** | Hệ thống hướng một metric về target value. | Web/API với CPU/RPS phù hợp, worker có metric backlog/task. | Metric phải tỷ lệ hợp lý với workload/capacity. |
| **Step scaling** | Bạn định nghĩa CloudWatch alarms và lượng task tăng/giảm theo ngưỡng. | Muốn scale mạnh theo ngưỡng rõ ràng hoặc phản ứng đặc thù. | Cần thiết kế alarm, step adjustments và cooldown cẩn thận. |
| **Scheduled scaling** | Thay đổi giới hạn min/max ở thời điểm định trước. | Giờ cao điểm có thể dự báo, sự kiện bán hàng, giờ làm việc. | Lịch không thay thế metric khi tải bất thường. |
| **Predictive scaling** | Dự báo nhu cầu từ dữ liệu lịch sử khi tùy chọn/điều kiện được hỗ trợ. | Tải có tính mùa vụ lặp lại và cần capacity sớm. | Cần dữ liệu phù hợp và đánh giá mức hỗ trợ/tính chính xác. |

### 4.1. Step scaling

Ví dụ service đang chạy 4 task, có các ngưỡng do nhóm thiết kế:

| CPU trung bình được alarm nhận diện | Hành động minh họa |
| --- | --- |
| Vượt 70% trong khoảng đã cấu hình | Thêm 2 task. |
| Vượt 90% trong khoảng đã cấu hình | Thêm 5 task. |
| Dưới 25% đủ lâu | Giảm 1 task. |

Các hành động là ví dụ **step adjustments**, không phải mặc định AWS. Cần tránh đặt nhiều alarms chồng lấn khiến capacity dao động hoặc tăng không kiểm soát. Phải chú ý min/max và cấu hình evaluation periods, datapoints, cooldown.

### 4.2. Scheduled scaling

Giả sử traffic theo giờ:

- 07:30–09:30 có nhiều người dùng đăng nhập.
- 12:00 có lượng truy cập tăng.
- Ban đêm lưu lượng thấp.

Có thể đặt scheduled action nâng **MinCapacity** từ 2 lên 6 trước giờ cao điểm rồi hạ min sau khi đã qua đỉnh, trong điều kiện load thực tế cho phép. Scheduled action thường tác động vào **min/max scalable target** theo lịch, không nên diễn giải đơn giản “mỗi sáng buộc ECS chạy đúng sáu task bất kể policy và demand”.

### 4.3. Chọn metric đúng bản chất hệ thống

Một dịch vụ API có CPU 25% nhưng gọi database rất lâu và timeout nhiều; scale thêm API task có thể **làm database quá tải hơn** chứ không giải quyết nút thắt.

Cần phân biệt:

- **CPU-bound:** tăng số task có thể giúp nếu backend độc lập và các giới hạn khác cho phép.
- **Memory-bound:** thêm task có thể giảm áp lực một số workload, nhưng lỗi memory leak cần sửa code.
- **I/O-bound:** kiểm tra network, database connection pool, downstream latency và retry trước khi tăng concurrency.
- **Queue workers:** backlog per task và **age of oldest message** thường phản ánh khả năng đáp ứng tốt hơn CPU đơn thuần.

## 5. Capacity provider là gì?

**Capacity provider** cho ECS biết **nguồn compute capacity** dùng chạy task, đồng thời cung cấp các cơ chế quản lý capacity theo loại provider.

Các nhóm quan trọng:

1. **AWS Fargate capacity providers:** **FARGATE** (on-demand) và **FARGATE_SPOT**.
2. **EC2 Auto Scaling group capacity providers:** liên kết với một EC2 Auto Scaling group, có thể bật **managed scaling**, managed termination protection và managed instance draining.
3. **Amazon ECS Managed Instances capacity providers:** ECS quản lý nhiều công việc của vòng đời EC2 instance, bao gồm provisioning, capacity và quản trị hạ tầng theo các khả năng hiện hành.

### 5.1. Bảng lựa chọn compute

| Kiểu | Ai quản lý máy chủ underlying? | Tình huống | Điều cần chú ý |
| --- | --- | --- | --- |
| **FARGATE** | AWS cấp tài nguyên phù hợp với task. | API, microservices, batch không muốn quản lý EC2. | Chi phí dựa trên tài nguyên task/thời gian và phí liên quan. |
| **FARGATE_SPOT** | AWS cấp tài nguyên Spot rảnh. | Batch, workers chịu gián đoạn; tối ưu phí. | Capacity có thể không sẵn; task bị ngắt khi AWS thu hồi Spot. |
| **EC2 ASG capacity provider** | Bạn quản lý loại instance/AMI/OS/ASG; ECS có thể quản lý kích thước ASG. | Workload cần điều chỉnh EC2 type, custom AMI, GPU hoặc chi phí tối ưu theo mật độ. | Cần ECS agent, OS patching, ASG limits, capacity placement. |
| **ECS Managed Instances** | ECS quản lý nhiều công đoạn của EC2 lifecycle. | Muốn dùng compute EC2 với ít gánh nặng vận hành hơn. | Kiểm tra Region, task compatibility, IAM, quota và phí theo dịch vụ. |

**Lưu ý:** Không có một lựa chọn “luôn nhanh/rẻ hơn” cho mọi workload. Fargate giảm vận hành EC2, nhưng phí và tính năng khác EC2; ECS Managed Instances là một mô hình bổ sung, không đồng nghĩa Fargate.

### 5.2. Fargate và Fargate Spot

- **FARGATE:** dùng compute theo task requirements mà không cần bạn tự vận hành ASG.
- **FARGATE_SPOT:** dùng dung lượng compute dư của AWS, giá có thể ưu đãi nhưng không bảo đảm luôn sẵn.
- Khi Fargate Spot bị thu hồi, AWS thường gửi cảnh báo **khoảng hai phút** trước khi task dừng thông qua EventBridge task state-change event và tín hiệu **SIGTERM** tới container theo cơ chế hỗ trợ.
- Nếu Spot chưa có capacity, task có thể không được đặt ngay; ECS service sẽ tiếp tục cố đáp ứng desiredCount theo scheduler behavior.

**Quan trọng:** Fargate Spot thiếu capacity **không có nghĩa ECS tự động thay bằng FARGATE on-demand**. Capacity provider strategy không phải cơ chế fallback SLA chắc chắn; ứng dụng production cần cân nhắc base on-demand, phân bổ task, nhiều AZ, retry và phương án vận hành.

### 5.3. ECS Managed Instances không phải EC2 ASG tự quản

Một tổ chức có thể muốn:

- Vẫn có quyền chọn loại tài nguyên EC2 phù hợp.
- Nhưng giảm công việc tự cập nhật AMI, sửa launch template, scale instances và duy trì patching.

ECS Managed Instances phục vụ một số nhu cầu đó theo khả năng dịch vụ. Tuy vậy, không mặc định cấu hình hoặc API quản lý của **ASG capacity provider** áp dụng nguyên trạng cho **Managed Instances provider**.

Khi chọn, cần kiểm tra điều kiện **task definition compatibility**, các loại instances/hardware được hỗ trợ, giới hạn Region, networking, bảo mật, chiến lược nâng cấp và bảng giá thực tế.

## 6. Capacity provider strategy: base, weight và giới hạn

Một ECS Service hoặc standalone task có thể sử dụng:

- Một **capacity provider strategy** được chỉ định trực tiếp.
- **Default capacity provider strategy** của cluster nếu không chỉ định launch type hoặc strategy tương ứng.
- **launchType** (EC2 hoặc FARGATE theo tình huống), với quy tắc loại trừ khi đã chỉ định capacityProviderStrategy.

**Không truyền đồng thời launchType và capacityProviderStrategy cho cùng service request**. Cấu hình thực tế nào thắng phụ thuộc vào service definition/cluster default và khả năng update được AWS hỗ trợ.

### 6.1. Ý nghĩa của base

**base** là số task tối thiểu cố gắng đặt lên một capacity provider được chỉ định trước khi áp dụng weight cho phần còn lại.

Ví dụ:

- FARGATE **base = 2**.
- desiredCount = 10.
- Hai task nền được ưu tiên đặt vào **FARGATE** theo base.
- Tám task còn lại được phân chia theo **weight**.

Chỉ **một** provider trong strategy được khai báo base. Mặc định base là 0 nếu không chỉ định.

### 6.2. Ý nghĩa của weight

**weight** là tỷ lệ **tương đối** phân phối task sau khi đáp ứng base.

Ví dụ hai providers:

- Provider A weight = 1.
- Provider B weight = 3.

Với tám task sau base, tỷ lệ lý thuyết A:B ≈ 1:3, tức khoảng 2:6. Với số task nhỏ, placement/rounding, capacity availability và deployments khiến phân phối thực tế không phải lúc nào đúng chính xác trong từng thời điểm.

### 6.3. Ví dụ Fargate on-demand + Spot

~~~json
{
  "capacityProviderStrategy": [
    {
      "capacityProvider": "FARGATE",
      "base": 2,
      "weight": 1
    },
    {
      "capacityProvider": "FARGATE_SPOT",
      "weight": 3
    }
  ]
}
~~~

Đây là **đoạn cấu hình minh họa**, không phải đầy đủ request tạo ECS Service.

Với desiredCount **10** và đủ capacity:

- Trước tiên ưu tiên **2 task FARGATE** theo base.
- **8 task còn lại** có tỷ trọng dự kiến FARGATE:Spot = 1:3.
- Phân bố kỳ vọng gần **4 task FARGATE và 6 task FARGATE_SPOT**, không phải chính xác tuyệt đối tại mọi thời điểm.

Nếu desiredCount chỉ **2**, cả hai task có thể nằm trên FARGATE do base đã chiếm toàn bộ. Không nên đọc weight 1:3 thành **25% on-demand / 75% Spot của toàn bộ desiredCount** khi có base.

### 6.4. Quy tắc bắt buộc cần nhớ

- Mỗi provider trong strategy phải được **associate với cluster** theo điều kiện sử dụng.
- Strategy có giới hạn số providers theo AWS; thường tối đa **20** trong một strategy, kiểm tra quota/tài liệu hiện hành.
- **Ít nhất một weight phải lớn hơn 0** nếu strategy có nhiều providers; tất cả weight = 0 dẫn đến request không hợp lệ.
- Provider có **weight = 0 không được dùng để đặt task** theo cơ chế phân phối weight.
- Khi thao tác bằng **API/CLI**, nếu không chỉ định weight, mặc định thường là **0**; trong ECS console, mặc định có thể là **1**. **Nên luôn khai báo weight tường minh** để IaC có hành vi rõ ràng.
- Strategy **không trộn các họ capacity providers khác nhau**: không đặt FARGATE/FARGATE_SPOT cùng với ASG-based provider trong **một strategy**; cũng không ghép trực tiếp họ Managed Instances với hai họ khác vào cùng strategy.
- **Một cluster vẫn có thể chứa nhiều họ capacity providers** và phục vụ nhiều ECS services khác nhau, mỗi service có strategy tương thích riêng.

### 6.5. Weight không phải bảo đảm còn capacity

Ví dụ đặt FARGATE 20% và FARGATE_SPOT 80% bằng weight, nhưng Spot đang thiếu capacity:

- ECS không thể đặt đủ các task dự kiến trên Spot.
- Service có thể duy trì số task RUNNING thấp hơn desiredCount trong một khoảng thời gian.
- Tỷ lệ traffic thực tế cũng phụ thuộc **ALB targets health**, số task RUNNING và độ lệch capacity, không chỉ weight.

Không nên dùng weight để tuyên bố **đã đạt SLA 80/20 về số request**. Nếu cần số task Fargate tối thiểu để giữ availability, thiết kế **base on-demand** cùng cơ chế phục hồi/giám sát phù hợp.

### 6.6. Chuyển đổi giữa các kiểu capacity

Khả năng cập nhật service từ launch type sang capacity provider strategy hoặc giữa các kiểu compute phụ thuộc vào **tài liệu ECS tại thời điểm triển khai**, tính tương thích task definition và yêu cầu triển khai lại. Một số thay đổi có thể yêu cầu deployment mới và kiểm tra behavior của scheduler.

Không tự động thay thuộc tính chiến lược ở production mà không có kế hoạch rollback, migration và xác nhận tính tương thích của task definition, network, deployment controller và capacity family.

## 7. EC2 ASG capacity provider và ECS managed scaling

Với ECS chạy trên EC2, bản thân ECS Service có thể muốn nhiều task hơn, nhưng **EC2 instances trong cluster phải có đủ tài nguyên** để chạy chúng. **EC2 Auto Scaling group capacity provider** kết nối ECS placement với việc điều chỉnh quy mô EC2 Auto Scaling group.

~~~mermaid
flowchart TD
    S["ECS Service: tăng desiredCount"] --> P["Task chờ placement / capacity"]
    P --> C["ASG capacity provider với managed scaling"]
    C --> M["CapacityProviderReservation CloudWatch"]
    M --> ASG["EC2 Auto Scaling group DesiredCapacity"]
    ASG --> EC2["Thêm EC2 vào ECS cluster"]
    EC2 --> R["Scheduler đặt task để chạy"]
~~~

### 7.1. Phân biệt ba số lượng

| Chỉ số | Đơn vị | Do ai điều chỉnh? |
| --- | --- | --- |
| **Service desiredCount** | ECS tasks. | ECS Service Auto Scaling hoặc thao tác service update. |
| **ASG DesiredCapacity** | EC2 instances hoặc đơn vị capacity ASG theo cấu hình hỗ trợ. | Capacity provider managed scaling hoặc cơ chế quản trị ASG khác. |
| **Service runningCount** | ECS tasks thực sự chạy. | Kết quả placement/scheduler, health và runtime. |

Ví dụ:

- Một task cần 1 vCPU và 2 GiB RAM.
- Một EC2 instance có khoảng 4 vCPU và 8 GiB RAM trước khi trừ phần OS, agent và reserved resources.
- Theo lý thuyết có thể đặt nhiều task, nhưng số thực tế còn phụ thuộc ports, ENI, resource reservation, placement và kích thước overhead.

Khi có 20 task chờ placement, capacity provider cố gắng cung cấp thêm EC2 theo heuristic của ECS; **không** đơn giản chia 20 cho 4 rồi bảo đảm luôn tạo đúng năm instance.

### 7.2. Managed scaling

Trong một ASG capacity provider, **managedScaling.status = ENABLED** cho phép ECS quản lý scale-out/scale-in của ASG theo metric và các tham số cấu hình.

Những thuộc tính quan trọng:

- **targetCapacity**: phần trăm reservation mục tiêu, thường trong khoảng giá trị AWS hỗ trợ.
- **minimumScalingStepSize / maximumScalingStepSize**: giới hạn các bước điều chỉnh để không scale theo những bước quá nhỏ hoặc quá lớn ngoài dự định.
- **instanceWarmupPeriod**: giúp tránh scale quá mức khi instance mới chưa khởi động/đăng ký đầy đủ.
- **Auto Scaling group MinSize/MaxSize**: ranh giới capacity hạ tầng; ECS managed scaling **không tự nâng MaxSize** thay bạn.

**Lưu ý:** Capacity provider managed scaling có thể quản lý ASG DesiredCapacity, nhưng bạn vẫn phải tạo đúng **launch template**, cluster association, instance profile, IAM, VPC, subnet, security và EC2 ECS agent theo yêu cầu.

### 7.3. CapacityProviderReservation là gì?

Metric **CapacityProviderReservation** của ASG capacity provider phản ánh tỷ lệ tương quan giữa **số EC2 instance cần để đặt task** và **số instance đang có**:

\[
\text{CapacityProviderReservation} =
\frac{\text{instances needed}}{\text{instances running}}\times 100\%
\]

Công thức mang tính giải thích từ AWS. Các thuật toán tính số instance needed xem xét CPU, memory, ENI, ports, GPU, placement constraints và các yếu tố hỗ trợ; không được hiểu rằng chỉ cộng vCPU là đủ.

Ví dụ:

- Ước tính cần 8 EC2 instances.
- ASG đang có 10 instances.
- CapacityProviderReservation ≈ **80%**.

Nếu **targetCapacity = 80%**, hệ thống hướng tới một mức headroom khoảng 20% theo capacity model tương ứng. Nếu **targetCapacity = 100%**, đặt mục tiêu sử dụng capacity chặt hơn, ít dư địa dự phòng hơn.

**Không suy rằng targetCapacity 80% là giữ CPU của EC2 dưới 80%.** Metric này **khác CPUUtilization**, nó đo nhu cầu instance để chạy ECS tasks trên capacity provider.

### 7.4. TargetCapacity dưới 100% và placement strategy

Khi chọn **targetCapacity thấp hơn 100%**, doanh nghiệp muốn có capacity dự phòng để task mới có thể bắt đầu sớm hơn. Tuy nhiên chiến lược **placement** ảnh hưởng hiệu quả sử dụng headroom.

- **binpack:** cố gắng gom task để sử dụng resource của instances hiệu quả hơn, giúp giảm lượng instance rảnh bị phân tán.
- **spread:** phân bố task theo thuộc tính như Availability Zone hoặc instance để tăng phân tán rủi ro.
- **constraints:** có thể hạn chế việc đặt task vào những EC2 đáp ứng một điều kiện cụ thể.

AWS khuyến nghị khi dùng targetCapacity dưới 100%, trong cấu hình placement phù hợp **binpack nên được xét trước spread** để tránh capacity không đạt mục tiêu. Nhưng nếu yêu cầu chịu lỗi AZ/instance quan trọng, vẫn phải thiết kế mức phân tán/HA có chủ đích. Không tối ưu binpack tới mức mọi task quan trọng cùng nằm trên một EC2 đơn điểm lỗi.

### 7.5. Khi task không thể fit bất kỳ instance nào

Nếu task yêu cầu CPU/RAM/ENI/GPU/ports hoặc placement constraints mà **không có instance type nào trong ASG có thể đáp ứng**, tăng số EC2 cùng loại không giải quyết vấn đề.

Ví dụ task cần **16 GiB RAM** nhưng ASG chỉ có instance với tổng 8 GiB. Service có thể tiếp tục có task chờ mặc dù ASG scale-out và các instances rảnh. Cần sửa **task requirements hoặc loại instance/ASG**.

### 7.6. Managed termination protection và managed draining

**Managed termination protection** bảo vệ các EC2 container instances còn chạy ECS tasks trước một số hoạt động scale-in do ASG. Khi bật cần cấu hình tương thích **instance scale-in protection** của ASG, theo hướng dẫn AWS.

**Managed instance draining** giúp EC2 đang bị ngừng/thu hồi chuyển sang trạng thái **DRAINING**, để task được dừng/chuyển dịch có kiểm soát và service có thể duy trì khả dụng trong khả năng kiến trúc.

Hai tính năng không giống nhau:

- Protection cố **tránh chọn instance đang chạy task** cho termination ở những trường hợp liên quan.
- Draining xử lý **quy trình ngừng instance** và thay task đang chạy khi termination thực sự xảy ra.

Spot interruption hoặc instance refresh có thể ảnh hưởng instance dù đã bật protection trong những điều kiện mà AWS không thể bảo đảm giữ instance. Vì vậy ứng dụng vẫn cần **graceful shutdown, deregistration delay, checkpoint và retry**.

### 7.7. Tránh xung đột với ASG scaling policies thủ công

Nếu ECS managed scaling đã quản lý một Auto Scaling group:

- **Không tự chỉnh sửa/xóa scaling policy** do capacity provider quản lý.
- Tránh đồng thời dùng một policy ASG CPU target tracking khác tranh nhau sửa **ASG DesiredCapacity**, nếu không có thiết kế đặc biệt được hỗ trợ.
- Không xóa tag quản lý quan trọng như **AmazonECSManaged** khỏi ASG.
- Đừng chỉnh sửa instance/ASG thủ công không kiểm soát khi có managed termination protection.
- Đảm bảo ASG **MaxSize > 0** nếu muốn scale từ 0.

Các can thiệp ngoài cơ chế có thể gây scale in/out dao động, đặt task thất bại hoặc ngăn ECS dự đoán capacity chính xác.

## 8. Chuỗi scale-out thực tế với ECS trên EC2

Xét một API container chạy bằng ASG capacity provider.

**Trạng thái ban đầu:**

- DesiredCount = 4.
- RunningCount = 4.
- ASG có 2 EC2 instances.
- CloudWatch CPUUtilization trung bình của service = 85%, target = 55%.

### 8.1. Diễn tiến

1. **CloudWatch metric** tăng vượt target theo cấu hình.
2. **Application Auto Scaling** thay đổi desiredCount từ 4 lên một số cao hơn, ví dụ 6.
3. ECS scheduler tìm nơi đặt thêm task.
4. Nếu hai EC2 hiện tại không đủ CPU/RAM/port/ENI, task mới có thể ở trạng thái **PROVISIONING/PENDING**.
5. **ECS capacity provider managed scaling** nhận biết nhu cầu capacity cho các task thuộc provider và điều chỉnh **ASG DesiredCapacity** theo metric/logic liên quan.
6. ASG khởi chạy EC2 mới. Instance cần boot, chạy ECS agent, đăng ký vào cluster và đạt trạng thái phù hợp.
7. Scheduler đặt task. Task tải image, khởi động và kiểm tra health.
8. Khi ALB target healthy và ứng dụng sẵn sàng, task mới bắt đầu phục vụ request.
9. Application Auto Scaling tiếp tục quan sát metric sau cooldown để quyết định các bước tiếp theo.

~~~mermaid
sequenceDiagram
    participant CW as CloudWatch
    participant AAS as Application Auto Scaling
    participant ECS as ECS Service Scheduler
    participant CP as Capacity Provider
    participant ASG as EC2 Auto Scaling Group
    participant ALB as Application Load Balancer
    CW->>AAS: CPU cao / target tracking
    AAS->>ECS: Tăng desiredCount
    ECS->>CP: Nhu cầu thêm capacity cho task
    CP->>ASG: Managed scaling ASG desired
    ASG-->>ECS: Instance mới đăng ký cluster
    ECS->>ALB: Task mới qua health checks
    ALB-->>ECS: Target healthy
~~~

**Tổng độ trễ để phục vụ thêm request** không chỉ là thời gian CloudWatch alarm kích hoạt. Nó gồm thời gian tăng task count, EC2 launch (nếu có), pull image, khởi động app, warming cache, ALB health check và kết nối data store.

### 8.2. Scale-in

Khi tải giảm:

1. Service scaling policy có thể hạ desiredCount thận trọng.
2. ECS scheduler dừng task theo deployment/termination behavior.
3. Các EC2 trở nên rảnh có thể được capacity provider/ASG scale in.
4. Managed draining/termination protection giúp giảm nguy cơ hủy task đang chạy.
5. Metric, desired/running tasks và ASG capacity dần trở về mức mục tiêu.

Phải kiểm soát **stopTimeout**, xử lý SIGTERM, kết nối DB, session state và queue checkpoint. Nếu một task đang xử lý thanh toán 3 phút mà bị dừng sau vài giây, scale-in có thể gây lỗi nghiệp vụ dù các policy về CPU đều đúng.

## 9. Thiết kế Service Auto Scaling cho HTTP API qua ALB

Giả sử backend **orders-api** chạy ECS Fargate phía sau ALB:

- Task definition: CPU/memory phù hợp với tải thực.
- ECS Service REPLICA: desiredCount = 3.
- Application Auto Scaling: MinCapacity = 2, MaxCapacity = 20.
- Target tracking CPU = 60% hoặc **ALBRequestCountPerTarget** theo khả năng service/deployment type.
- Capacity strategy: FARGATE on-demand cho phần tối thiểu cần HA, có thể bổ sung Spot cho những thành phần chịu gián đoạn.

~~~mermaid
flowchart TB
    USER["Clients"] --> ALB["ALB HTTPS"]
    ALB --> TG["Target group / health"]
    subgraph AZA["AZ A"]
      T1["ECS task 1"]
    end
    subgraph AZB["AZ B"]
      T2["ECS task 2"]
    end
    subgraph AZC["AZ C"]
      T3["ECS task 3"]
    end
    TG --> T1
    TG --> T2
    TG --> T3
    CW["CloudWatch CPU/RPS metrics"] --> AAS["Application Auto Scaling"]
    AAS -->|"desiredCount"| S["ECS Service"]
    S -.->|"thêm/bớt task"| TG
~~~

Sơ đồ minh họa task phân tán theo AZ, không khẳng định scheduler luôn đặt đúng một task ở mỗi AZ trong mọi thời điểm. Subnets, deployment, placement, Fargate capacity và load balancer phải được thiết kế theo AZ khả dụng.

### 9.1. Chọn CPU hay request count?

| Metric | Phù hợp khi | Có thể gây sai lệch khi |
| --- | --- | --- |
| **CPU utilization** | CPU tăng tương đối cùng lượng công việc; CPU-bound API. | Ứng dụng chủ yếu chờ DB/network, CPU thấp nhưng latency cao. |
| **Memory utilization** | Mỗi task dùng RAM theo tải, không bị memory leak. | Memory cache tăng dần rồi không giảm, scaling không giải quyết leak. |
| **ALB RequestCountPerTarget** | Target group và số request/task phản ánh tải hợp lý. | Mỗi request có thời gian xử lý rất khác nhau; blue/green deployment type không hỗ trợ metric này cho target tracking. |
| **Custom latency/backlog** | Có cơ chế đo được demand và scale correlation. | Metric không tỷ lệ thuận/nghịch hợp lý với task count hoặc mất dữ liệu khi 0 task. |

Một API phụ thuộc DB có thể có p95 latency tăng dù CPU rất thấp. Tăng số task API lúc đó có thể tăng số kết nối DB và đẩy sự cố nặng hơn. Nên dùng metric kết hợp **sức khỏe backend và năng lực data store**, không scale mù.

### 9.2. Deployment và scaling

Theo cơ chế Application Auto Scaling cho ECS deployment controller phù hợp:

- Trong một **deployment đang diễn ra**, Application Auto Scaling thường **tạm dừng scale-in**.
- **Scale-out vẫn được phép** trừ khi bị chủ động suspend.
- Hành vi này có ngoại lệ với services dùng **external deployment controller**; phải kiểm tra loại controller.
- Nếu team muốn tạm dừng cả scale-out, cần quản lý suspended state của scalable target đúng quy trình và khôi phục lại sau deployment.

Ngoài ra rolling deployment có thể cần capacity **nhiều hơn desiredCount** tạm thời theo minimumHealthyPercent/maximumPercent. ASG gần full hoặc Fargate Spot thiếu capacity có thể khiến rollout stuck dù scaling policy của service hoạt động đúng.

### 9.3. Health check grace period và readiness

Một task vừa RUNNING chưa chắc đã sẵn sàng nhận request.

- **ALB health check path** nên kiểm tra endpoint readiness đúng.
- **healthCheckGracePeriodSeconds** của ECS Service (khi dùng load balancer/health check phù hợp) có thể ngăn service scheduler kết luận unhealthy quá sớm lúc container đang warm up.
- **Container health check** phát hiện tình trạng nội bộ container theo cấu hình.
- App nên trả lỗi/ready đúng trạng thái khởi động.
- Nếu DB cần migrations, tránh cho task mới nhận production traffic trước khi dependency sẵn sàng.

**Không dùng health check grace period thật dài để che một image đang crash liên tục.** Phải phân biệt startup chậm với cấu hình sai/thiếu dependency.

## 10. Thiết kế Auto Scaling cho SQS worker

Một hệ thống xử lý ảnh theo pipeline:

~~~mermaid
flowchart LR
    S3[("S3 uploads")] --> Q["SQS Standard queue"]
    Q --> W["ECS Service worker tasks"]
    W --> OUT[("S3 results")]
    Q --> M["CloudWatch queue metrics"]
    M --> AAS["Application Auto Scaling"]
    AAS -->|"scale desiredCount"| W
~~~

### 10.1. Vì sao CPU chưa chắc là metric tốt?

Worker có thể dành phần lớn thời gian chờ tải ảnh từ S3 hoặc chờ database ghi kết quả. CPU thấp không có nghĩa queue không tăng.

Một metric ứng dụng hữu ích là:

\[
\text{BacklogPerTask} =
\frac{\text{ApproximateNumberOfMessagesVisible}}{\max(\text{running tasks},1)}
\]

Đây là **công thức tham khảo** để hiểu, không phải metric ECS mặc định. Đặc biệt cần cân nhắc message đang invisible/in-flight, độ dài công việc và tình huống zero task.

### 10.2. Chọn target backlog per task

Giả sử:

- Mỗi task xử lý **0,5 message/giây** (30 message/phút) trong điều kiện ổn định.
- Thời gian chờ tối đa mong muốn trước khi bắt đầu xử lý ≈ **120 giây**.

Một backlog mục tiêu ban đầu theo capacity của một task:

\[
\text{Target backlog/task}
\approx
\text{task processing rate} \times
\text{acceptable queue wait}
=0.5\times120 = 60
\]

Nếu queue có **600 message** và chỉ tính heuristic này, nhu cầu capacity có thể ở mức khoảng **10 task**. Đó là ước tính giúp đặt policy, không phải công thức đảm bảo chính xác tuổi của tất cả message; công việc dài ngắn khác nhau, retry và queue semantics đều ảnh hưởng.

Cần theo dõi thêm **ApproximateAgeOfOldestMessage**, failures/DLQ và thời gian xử lý thực tế.

### 10.3. Worker cần idempotency và graceful shutdown

Khi ECS scale-in hoặc Spot interruption:

- Worker nên dừng lấy công việc mới khi nhận SIGTERM.
- Hoàn thành việc đang xử lý trong thời gian cho phép, hoặc ghi checkpoint/để message quay lại queue.
- Thiết lập SQS visibility timeout và DLQ phù hợp thời gian xử lý.
- Xử lý message idempotently vì SQS Standard có thể giao lại.
- Ghi trạng thái nghiệp vụ có điều kiện để tránh xử lý/charge hai lần.

**Scale-in không đồng nghĩa queue trống hoàn toàn**. Nếu metric sai hoặc pipeline có message invisible, hệ thống có thể giảm task dù vẫn còn công việc chưa hoàn tất.

### 10.4. Scale to zero: kiểm thử cả hai chiều

Với worker không cần phản hồi request ngay:

- MinCapacity = 0 có thể giúp giảm compute khi không có việc.
- Metric kích hoạt scale-out phải **được phát ngay cả khi không có worker**, ví dụ queue depth hoặc alarm/custom metric độc lập.
- Khi có message mới, cần đo thời gian từ queue xuất hiện công việc đến task chạy.
- Nếu dùng Fargate Spot, đừng giả định Spot capacity luôn có để bật task từ zero.

Nếu bài toán yêu cầu phản hồi rất nhanh hoặc cam kết SLA khắt khe, giữ MinCapacity ≥ 1 hoặc dùng FARGATE on-demand baseline có thể phù hợp hơn.

## 11. Bảo mật và mạng ảnh hưởng đến khả năng scale

Mở rộng thành công đòi hỏi task mới **có thể lấy image, truy cập secrets, nhận traffic và gọi dependency**.

### 11.1. IAM roles cần phân biệt

| Role | Vai trò | Ví dụ quyền |
| --- | --- | --- |
| **Task execution role** | ECS agent/Fargate runtime dùng để pull image, gửi logs, lấy một số secret/config qua cơ chế ECS. | ECR image pull, CloudWatch Logs, secret access nếu task definition dùng. |
| **Task role** | Quyền AWS API của **code chạy trong container**. | s3:GetObject, sqs:ReceiveMessage, dynamodb:PutItem. |
| **EC2 instance profile role** | Quyền hạ tầng cho ECS container instance khi dùng EC2. | ECS agent đăng ký/trao đổi với cluster theo managed policy phù hợp. |
| **Application Auto Scaling service-linked role** | Cho phép service tự điều chỉnh ECS desired count. | Quyền nội bộ theo **AWSServiceRoleForApplicationAutoScaling_ECSService**. |
| **ASG/Capacity provider service roles** | ECS/EC2 Auto Scaling quản lý capacity và instances. | Cơ chế service-linked roles theo tính năng. |

Không trao quyền **ecs:UpdateService**, **autoscaling:UpdateAutoScalingGroup** hoặc IAM admin cho task role chỉ để container được S3. Workload role chỉ nên có quyền nghiệp vụ cần thiết.

### 11.2. VPC, subnet và Security Group

- Fargate thường dùng **awsvpc network mode** và ENI cho task theo giới hạn dịch vụ.
- Task ở private subnet cần đường tới **ECR API/DKR, S3, CloudWatch Logs, Secrets Manager** hoặc dịch vụ liên quan qua **VPC endpoints/NAT** theo kiến trúc.
- ALB target group, target type, listener và Security Group phải cho phép kết nối tới container port.
- EC2 container instances cần có đủ subnet IP, network interfaces, ports và đăng ký đúng ECS cluster.
- Phân tán task trên **nhiều AZ** theo availability requirements; kiểm tra IP exhaustion và subnet capacity.

Nếu ECS không pull được image vì không có ECR/S3 endpoint hoặc NAT, tăng desiredCount **chỉ tạo thêm task failures**.

### 11.3. Secrets và KMS

ECS Task Definition có thể tham chiếu secrets từ Secrets Manager hoặc SSM Parameter Store tùy khả năng hỗ trợ. Khi task mới được tạo:

- Execution role/đường mạng phải truy cập secret được.
- KMS permissions phải phù hợp nếu dùng customer managed keys.
- Hạn chế in credentials/secret ra logs.
- Tính đến việc task mới có thể nhận version của secret tại thời điểm khởi động; rotation cần chiến lược ứng dụng phù hợp.

### 11.4. Image và nguồn container

Image quá lớn làm scale-out chậm. Chọn image gọn, multi-stage build, image scanning, tag/immutable digest và pull policy đúng giúp giảm thời gian startup và rủi ro supply-chain.

Khi workload cần nhiều AZ, các image, secrets và data dependencies phải sẵn sàng từ những subnets/Regions tương ứng, không chỉ ở một instance xây dựng.

## 12. Hiệu năng, chi phí và độ sẵn sàng

### 12.1. Chi phí khi scale trên Fargate

Fargate tính phí theo những thành phần như **vCPU, memory, thời gian sử dụng**, cấu hình OS/architecture/storage bổ sung và Region, tùy bảng giá hiện hành. Thêm task phục vụ cùng một lưu lượng có thể tăng compute cost nếu metric/cooldown không tối ưu.

FARGATE_SPOT có giá ưu đãi cho capacity có thể bị thu hồi, nhưng cần tính chi phí:

- Retry/reprocessing sau interruption.
- Thời gian xử lý kéo dài khi Spot capacity thiếu.
- Hệ thống monitoring và số lượng task nền FARGATE để giữ SLA.

**Spot rẻ hơn mỗi đơn vị capacity không tự chứng minh TCO thấp hơn**, nhất là với workload đòi hỏi phản hồi thời gian thực.

### 12.2. Chi phí trên EC2 capacity provider

Với EC2 ASG, tổng chi phí còn gồm:

- Số EC2 instances/loại instance/giờ chạy.
- EBS volumes, data transfer, NAT và networking.
- Vận hành AMI, patching, ECS agent, capacity planning.
- Headroom do **targetCapacity < 100%** để hỗ trợ start task nhanh.
- EC2 Spot/On-Demand/Savings Plans nếu dùng theo mô hình tương ứng.

**targetCapacity 80%** có thể giữ capacity dự phòng đáng kể hơn targetCapacity 100%. Mức dự phòng có giá trị cho thời gian phản hồi scale-out, nhưng phải cân đối phí hạ tầng đang rảnh.

### 12.3. Tối ưu theo số task thật sự cần thiết

Một kế hoạch hiệu quả:

1. **Right-size task definition:** CPU/RAM theo mức tiêu thụ thực.
2. **Đo workload:** RPS, CPU, memory, latency, queue wait, DB capacity.
3. **Tạo Min/Max phù hợp:** không scale dưới mức SLA cần.
4. **Chọn metric phản ánh demand:** tránh CPU nếu bottleneck nằm ở DB/IO.
5. **Đặt cooldown theo startup/termination:** tránh dao động.
6. **Chọn capacity provider:** Fargate để giảm vận hành, EC2/Managed Instances để phù hợp tính năng/chi phí, Spot khi chịu được interruption.
7. **Giữ observability:** số task pending, healthy targets, events và chi phí theo service.
8. **Load-test/failover-test:** đo sau khi scale và phục hồi thực tế, không chỉ nhìn policy.

### 12.4. Đặt guardrails cho scale-out

MaxCapacity không nên đặt vô hạn chỉ vì muốn giữ availability; backend có thể không chịu được hàng trăm task/API connections. Giới hạn qua:

- MaxCapacity phù hợp ngân sách và downstream throughput.
- Rate limiting và throttling ở API layer.
- Connection pool và concurrency cap cho database.
- Queue backpressure, DLQ, retry exponential backoff.
- AWS Budgets/Cost Anomaly Detection và cảnh báo metric.
- AWS Service Quotas/ASG MaxSize kiểm tra trước peak.

Mỗi lần scale-out phải cải thiện throughput hoặc độ trễ. Nếu số task tăng nhưng error rate cũng tăng, có thể hệ thống đang **scale vào bottleneck khác**.

## 13. Quan sát những chỉ số nào?

### 13.1. Theo từng lớp

| Lớp | Metrics/events | Ý nghĩa |
| --- | --- | --- |
| ECS Service | **desiredCount, runningCount, pendingCount**, deployment state, service events. | Service có đạt mục tiêu task không? |
| Application Auto Scaling | Scalable targets, scaling policies/activities, CloudWatch alarms. | Vì sao desiredCount thay đổi? |
| ECS task/container | CPU, memory, exitCode, stoppedReason, container health. | Vì sao task không khỏe hoặc bị dừng? |
| ALB | RequestCountPerTarget, TargetResponseTime, HTTP 5xx, HealthyHostCount. | Task mới có thực sự phục vụ request không? |
| SQS | ApproximateNumberOfMessagesVisible, AgeOfOldestMessage, DLQ. | Worker có theo kịp việc không? |
| EC2 capacity provider | **CapacityProviderReservation**, provider status, managed scaling/draining. | Hạ tầng có đáp ứng placement không? |
| EC2 ASG | DesiredCapacity, InService/Pending instances, scaling activities. | ASG có tăng/giảm đúng không? |
| Cost | Fargate usage, EC2 hours, logs, NAT, data transfer. | Chi phí có tăng tương xứng hiệu quả không? |

### 13.2. Các câu hỏi ưu tiên khi sự cố

- **desiredCount tăng nhưng runningCount không tăng:** kiểm tra placement, stoppedReason, container image, IAM, network, capacity provider.
- **runningCount tăng nhưng latency vẫn cao:** kiểm tra ALB health, startup/readiness, DB, rate limiting, downstream bottlenecks.
- **EC2 mới không được tạo:** kiểm tra capacity provider managedScaling, ASG MaxSize, CapacityProviderReservation, AmazonECSManaged tag, task placement, quota.
- **Task Fargate Spot pending lâu:** kiểm tra Fargate Spot availability và lựa chọn on-demand baseline; không giả định tự fallback.
- **Scale-in gây 5xx:** kiểm tra container SIGTERM/stopTimeout, deregistration delay, in-flight requests, readiness, task protection khi áp dụng.
- **CPU đã thấp nhưng không scale-in:** kiểm tra các target tracking policies khác, cooldown, deployment đang diễn ra, minCapacity và missing metric.

## 14. AWS CLI — khảo sát cấu hình ở chế độ chỉ đọc

Các lệnh sau **không tạo/sửa/xóa tài nguyên**. Bạn cần profile AWS có IAM read permissions, chọn đúng account/Region và thay placeholder bằng tên thật.

### 14.1. Xác định danh tính và danh sách cluster

~~~bash
aws sts get-caller-identity

aws ecs list-clusters \
  --region ap-southeast-1

aws ecs describe-clusters \
  --clusters demo-ecs-cluster \
  --include STATISTICS SETTINGS ATTACHMENTS \
  --region ap-southeast-1
~~~

Trong **describe-clusters**, xem **capacityProviders**, **defaultCapacityProviderStrategy**, trạng thái cluster, registered container instances và attachments. Khi service không khai báo capacity strategy/launch type, default strategy có thể quyết định nơi task được đặt.

### 14.2. Xem ECS Service

~~~bash
aws ecs list-services \
  --cluster demo-ecs-cluster \
  --region ap-southeast-1

aws ecs describe-services \
  --cluster demo-ecs-cluster \
  --services orders-api \
  --region ap-southeast-1 \
  --query "services[].{Name:serviceName,Status:status,Desired:desiredCount,Running:runningCount,Pending:pendingCount,Strategy:capacityProviderStrategy,Deployments:deployments,Events:events[:5]}"
~~~

Chú ý:

- **desiredCount/runningCount/pendingCount**.
- **capacityProviderStrategy** hoặc **launchType**.
- **deploymentController**, deployment state và events.
- **Task definition revision**, ALB target group, networking và health check grace period khi cần xem kết quả đầy đủ.

Nếu events báo **unable to place task**, vấn đề có thể ở capacity/placement chứ không phải CloudWatch scaling alarm.

### 14.3. Xem task và lý do task dừng

~~~bash
aws ecs list-tasks \
  --cluster demo-ecs-cluster \
  --service-name orders-api \
  --desired-status RUNNING \
  --region ap-southeast-1

aws ecs list-tasks \
  --cluster demo-ecs-cluster \
  --service-name orders-api \
  --desired-status STOPPED \
  --region ap-southeast-1
~~~

Chọn task ARN từ danh sách rồi kiểm tra:

~~~bash
aws ecs describe-tasks \
  --cluster demo-ecs-cluster \
  --tasks arn:aws:ecs:ap-southeast-1:111122223333:task/demo-ecs-cluster/0123456789abcdef0123456789abcdef \
  --region ap-southeast-1
~~~

Đọc **lastStatus**, **desiredStatus**, **launchType/capacityProviderName**, **stopCode**, **stoppedReason**, container **exitCode/reason**, **healthStatus** và ENI attachment.

**Lưu ý:** Task đã dừng chỉ được giữ một khoảng thời gian trong khả năng truy xuất ECS API; cần CloudWatch logs/EventBridge/task-state history để điều tra các sự cố cũ hơn.

### 14.4. Xem scalable targets và policies

~~~bash
aws application-autoscaling describe-scalable-targets \
  --service-namespace ecs \
  --resource-ids service/demo-ecs-cluster/orders-api \
  --scalable-dimension ecs:service:DesiredCount \
  --region ap-southeast-1

aws application-autoscaling describe-scaling-policies \
  --service-namespace ecs \
  --resource-id service/demo-ecs-cluster/orders-api \
  --scalable-dimension ecs:service:DesiredCount \
  --region ap-southeast-1

aws application-autoscaling describe-scaling-activities \
  --service-namespace ecs \
  --resource-id service/demo-ecs-cluster/orders-api \
  --scalable-dimension ecs:service:DesiredCount \
  --region ap-southeast-1
~~~

Kiểm tra **MinCapacity, MaxCapacity**, **SuspendedState**, policy type, metric target, cooldown, timestamps và activity reason. Nếu không thấy scalable target, service chưa chắc đã được đăng ký Application Auto Scaling dù ECS Service đang chạy.

### 14.5. Xem scheduled actions

~~~bash
aws application-autoscaling describe-scheduled-actions \
  --service-namespace ecs \
  --resource-id service/demo-ecs-cluster/orders-api \
  --scalable-dimension ecs:service:DesiredCount \
  --region ap-southeast-1
~~~

Kiểm tra cron/timezone/start/end, min/max và việc thay đổi theo lịch. Lịch trùng với target tracking có thể làm số task thay đổi khác so với dự tính nếu không xét cả hai cơ chế.

### 14.6. Xem capacity providers

~~~bash
aws ecs describe-capacity-providers \
  --capacity-providers FARGATE FARGATE_SPOT \
  --region ap-southeast-1

aws ecs describe-capacity-providers \
  --capacity-providers demo-asg-provider \
  --include TAGS \
  --region ap-southeast-1
~~~

Đối với ASG provider, xem các trường:

- **autoScalingGroupProvider.autoScalingGroupArn**.
- **managedScaling.status / targetCapacity**.
- **managedTerminationProtection / managedDraining**.
- Trạng thái **ACTIVE/UPDATING** và các capacity provider associations trong cluster.

Với provider thuộc họ Managed Instances, dùng lệnh **describe-capacity-providers** và cấu trúc tương ứng mà phiên bản AWS CLI/tài liệu hiện hành hỗ trợ; đừng mặc định trường **autoScalingGroupProvider** tồn tại trên mọi provider.

### 14.7. Xem EC2 ASG nếu đang dùng ASG capacity provider

~~~bash
aws autoscaling describe-auto-scaling-groups \
  --auto-scaling-group-names demo-ecs-asg \
  --region ap-southeast-1 \
  --query "AutoScalingGroups[].{Name:AutoScalingGroupName,Min:MinSize,Max:MaxSize,Desired:DesiredCapacity,Instances:Instances,Tags:Tags}"

aws autoscaling describe-scaling-activities \
  --auto-scaling-group-name demo-ecs-asg \
  --region ap-southeast-1
~~~

Kiểm tra ASG MaxSize/DesiredCapacity, instances lifecycle, health, scaling activities và **AmazonECSManaged** tag. Nếu managed scaling đang bật, không tự can thiệp ASG policy để thử nghiệm khi chưa có kế hoạch rollback và quyền phù hợp.

### 14.8. Xem CloudWatch metrics

~~~bash
# Liệt kê những metric ECS Service có trong CloudWatch.
aws cloudwatch list-metrics \
  --namespace AWS/ECS \
  --metric-name CPUUtilization \
  --dimensions Name=ClusterName,Value=demo-ecs-cluster Name=ServiceName,Value=orders-api \
  --region ap-southeast-1

# Liệt kê metric cluster capacity của capacity provider nếu có.
aws cloudwatch list-metrics \
  --namespace AWS/ECS/ManagedScaling \
  --metric-name CapacityProviderReservation \
  --region ap-southeast-1

# Xem CloudWatch alarms liên quan.
aws cloudwatch describe-alarms \
  --alarm-name-prefix TargetTracking-service \
  --region ap-southeast-1
~~~

Không phải metric nào cũng có sẵn khi ECS Service không có running tasks hoặc chưa bật monitoring hỗ trợ. Kiểm tra đúng **namespace, dimensions, metric resolution và thời gian** khi truy vấn số liệu lịch sử.

### 14.9. Những lệnh cố ý không chạy trong bài

Các thao tác như **update-service**, **register-scalable-target**, **put-scaling-policy**, **update-capacity-provider**, **put-cluster-capacity-providers** hoặc sửa ASG sẽ **thay đổi hạ tầng và chi phí**; không có trong các bước thực hành chỉ đọc này.

Trong môi trường được quản trị, cấu hình production nên được tạo/đổi qua IaC có review và thử nghiệm với khả năng rollback.

## 15. Bảng khắc phục sự cố

| Hiện tượng | Nguyên nhân có thể | Kiểm tra/khắc phục |
| --- | --- | --- |
| **CPU cao nhưng desiredCount không tăng.** | Chưa đăng ký scalable target, không có policy, alarm thiếu data, MaxCapacity đã đạt, scaling suspended. | Describe scalable targets/policies/activities, CloudWatch metric/alarms. |
| **Desired 10 nhưng Running 6.** | Compute thiếu, Fargate Spot unavailable, EC2 placement không đủ resource, image pull/lỗi startup. | ECS service events, stoppedReason, capacity provider và ASG. |
| **EC2 ASG không scale-out.** | Managed scaling disabled, task không dùng provider strategy, ASG MaxSize đã đạt, task không fit loại instance. | Describe capacity provider/ASG, CapacityProviderReservation, placement failure. |
| **ASG tăng mà task vẫn PROVISIONING/PENDING.** | Instance chưa đăng ký ECS, thiếu CPU/RAM/ENI, sai AZ/placement, agent/AMI/capacity shortage. | ECS container instances, agent logs, task placement và ASG activities. |
| **Scale-in không chạy dù CPU thấp.** | Memory policy chưa cho scale-in, MinCapacity, cooldown, deployment, missing metric. | Toàn bộ target tracking policies, deployment state, events. |
| **Scale-out lặp quá nhiều.** | Startup chậm, cooldown không phù hợp, metric lag, database bottleneck, readiness sai. | Task launch timeline, metrics, ALB, DB/CloudWatch logs. |
| **Spot tasks bị dừng.** | Spot interruption hoặc thiếu capacity. | ECS task state change/EventBridge, stoppedReason, phân bố FARGATE/Spot. |
| **Fargate Spot không được thay bằng Fargate.** | Spot capacity không tự fallback; capacity provider strategy chỉ định tỷ trọng riêng. | Xem base/weight, cân nhắc on-demand baseline hoặc phân tách service. |
| **Task RUNNING nhưng ALB 5xx.** | Container chưa ready, ALB target unhealthy, SG/port sai, ứng dụng/DB lỗi. | Target group health, service networking, app logs, DB. |
| **Sau deployment số task nhiều hơn desiredCount.** | Rolling deployment tạm chạy task cũ và mới, maximumPercent cho phép. | Describe deployments và deployment configuration. |
| **Không scale từ zero.** | Metric CPU/memory không phát khi không có task, policy không có tín hiệu demand. | Dùng queue-depth/custom metric phát độc lập, thử từ 0. |
| **Chi phí tăng khi traffic không tăng.** | Tasks đang dư, MinCapacity quá cao, ASG headroom lớn, CPU/memory task quá mức, Spot fail/retry. | Billing, CloudWatch, task count, capacity reservation và scaling activities. |

### 15.1. Cây quyết định nhanh

~~~mermaid
flowchart TD
    A["Ứng dụng cần nhiều năng lực hơn"] --> B{"DesiredCount có tăng?"}
    B -->|"Không"| C["Kiểm tra Application Auto Scaling metric / policy / min-max / suspended"]
    B -->|"Có"| D{"RunningCount có theo kịp?"}
    D -->|"Không"| E{"Capacity nào đang dùng?"}
    E -->|"Fargate"| F["Xem Spot capacity, quota, network, pull image, task stoppedReason"]
    E -->|"EC2"| G["Xem ASG managed scaling, reservation, resource fit, agent, ASG MaxSize"]
    E -->|"Managed Instances"| H["Xem provider status, compatibility, capacity/placement"]
    D -->|"Có"| I{"Task healthy và application latency cải thiện?"}
    I -->|"Không"| J["Kiểm tra ALB/DB/IO, errors, readiness, deployment, downstream"]
    I -->|"Có"| K["Tiếp tục đo p95, cost, cooldown và scale-in"]
~~~

**Mẹo chẩn đoán:** Luôn hỏi ba câu theo đúng thứ tự: (1) **service có muốn thêm task không?** (2) **ECS có chạy được task không?** (3) **task chạy rồi có thực sự phục vụ được nghiệp vụ không?**

## 16. Sai lầm thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “Capacity provider tự scale số task theo CPU.” | Capacity provider quản lý **nơi/capacity** chạy task; Service Auto Scaling thay **desiredCount**. |
| “Đã có Service Auto Scaling thì EC2 tự tăng.” | Với EC2 cần ASG capacity provider managed scaling hoặc cơ chế scale hạ tầng phù hợp. |
| “Tăng desiredCount đảm bảo RunningCount tăng ngay.” | Phải có capacity, task definition tương thích, image/network/health phù hợp. |
| “targetCapacity 80% nghĩa là CPU EC2 luôn dưới 80%.” | Nó nhắm **CapacityProviderReservation**, không phải CPU utilization. |
| “Fargate Spot thiếu thì ECS tự đổi sang Fargate.” | Không có fallback tự động được bảo đảm; cần thiết kế on-demand baseline/chuyển hướng có chủ đích. |
| “weight 1:3 là chính xác 25%/75% toàn bộ tasks.” | **base** được xử lý trước; tỷ lệ là mục tiêu cho phần task còn lại và chịu ảnh hưởng placement/availability. |
| “Có thể trộn FARGATE và EC2 ASG provider trong một strategy.” | Strategy không trộn các **họ capacity providers khác nhau**, dù cluster có thể chứa nhiều loại. |
| “Bỏ weight trong CLI thì mặc định bằng 1.” | API/CLI thường mặc định **0**; cần khai báo rõ, khác console. |
| “Scale to zero CPU target tracking sẽ tự biết có request mới.” | Khi zero task, CPU metric có thể vắng; cần demand metric ngoài tasks hoặc cơ chế khác. |
| “Mỗi service nên có thật nhiều CPU target policies.” | Nhiều policies cùng metric có thể không hợp lệ/không tăng lợi ích; nên phân tách metric có ý nghĩa. |
| “CPU thấp chắc chắn được scale-in.” | MinCapacity, cooldown, deployment và các metric policies khác có thể ngăn scale-in. |
| “ECS chạy hai task = luôn high availability.” | Còn phụ thuộc AZ placement, health, load balancing, data store và capacity. |
| “ALB health check và ECS task RUNNING là một.” | Task RUNNING có thể chưa ready hoặc không healthy trong ALB target group. |
| “Managed termination protection đảm bảo không task nào bị ngắt.” | Spot interruption/instance refresh và các lỗi khác vẫn có thể dừng instance. |
| “MaxCapacity càng lớn càng an toàn.” | Phải xét quota, backend capacity, cost và bottleneck khác. |
| “Auto Scaling giải quyết mọi vấn đề hiệu năng.” | Nó không tự sửa memory leak, SQL chậm, network sai hay ứng dụng không idempotent. |

## 17. Tình huống thực tế có lời giải

### Tình huống A — API tăng tải giờ cao điểm

**Đề bài:** Một ECS Fargate Service chạy Orders API sau ALB, thường có 3 task, giờ cao điểm CPU trung bình 85%. Muốn tự động tăng số bản sao, giữ ít nhất hai task để chịu lỗi một AZ.

**Phương án:**

1. Service dùng REPLICA và nhiều subnet/AZ.
2. Đăng ký Application Auto Scaling scalable target với **MinCapacity = 2**, **MaxCapacity = 20** (ví dụ).
3. Target tracking CPU khoảng 60% làm điểm bắt đầu, sau đó load-test điều chỉnh.
4. Đặt cooldown theo startup và ALB target health.
5. Dùng capacity strategy FARGATE baseline đủ HA; nếu đưa thêm Spot, chỉ cho các phần chịu gián đoạn và đo capacity availability.
6. Kiểm tra ALB TargetResponseTime, 5xx, CPU/memory, DB connections và chi phí.

**Giải thích:** Metric CPU có thể là tín hiệu tải tốt, nhưng vẫn phải chứng minh việc tăng task thực sự giảm latency mà không làm database quá tải.

### Tình huống B — ECS EC2 báo thiếu memory dù ASG còn instance rảnh

**Đề bài:** Service desiredCount = 12, runningCount = 8. ASG capacity provider có tám EC2 instances. Các task mới yêu cầu 16 GiB RAM, mỗi EC2 instance chỉ có 8 GiB tổng RAM.

**Lời giải:** Không task nào mới fit instance type hiện tại. Managed scaling thêm 10 EC2 8 GiB vẫn không tạo được một vị trí đủ RAM 16 GiB cho một task. Cần **chọn instance type có đủ RAM**, điều chỉnh task request dựa trên đo thực tế hoặc phân tách workloads/ASG phù hợp.

**Kiểm chứng:** Xem ECS service events, resource requirements của task definition và thuộc tính EC2 container instances; không chỉ nhìn ASG DesiredCapacity.

### Tình huống C — Web production muốn 30% task ở Spot

**Đề bài:** Ứng dụng đang chạy 10 task; chấp nhận Spot cho phần capacity phụ nhưng vẫn phải giữ ít nhất ba task on-demand.

**Thiết kế minh họa:**

- FARGATE base = 3, weight = 7.
- FARGATE_SPOT weight = 3.

Sau base, bảy task còn lại có tỷ trọng Spot kỳ vọng **30% của phần còn lại**, tức xấp xỉ 2–3 Spot tasks trong ví dụ, **không phải chính xác 30% toàn bộ 10 task**.

Muốn kiểm soát tỷ lệ Spot khác, phải tính lại base/weights cho đúng mục tiêu và nhớ rằng AWS không đảm bảo Spot capacity luôn có. Kiểm thử bằng load/placement thực tế.

### Tình huống D — SQS worker muốn tiết kiệm khi hết việc

**Đề bài:** Một worker ECS Fargate đọc SQS; ban đêm không có message, mong muốn MinCapacity = 0.

**Thiết kế:**

- Dùng demand metric **queue depth/backlog per task** được publish ngay cả khi running tasks = 0.
- Target tracking/step scaling dựa trên CloudWatch signal và MaxCapacity theo khả năng downstream.
- Khi có backlog, scale từ zero và đo thời gian cold start.
- Giữ idempotency, visibility timeout, DLQ và graceful shutdown.

Nếu thời gian khởi động quá lâu so với SLA, giữ MinCapacity = 1 hoặc một worker on-demand nền.

### Tình huống E — Scale-in trong deployment gây HTTP 502

**Đề bài:** Team rolling update ECS Service, vài phiên xử lý dài bị cắt giữa chừng.

**Phân tích:**

- Kiểm tra ECS deployment type, minHealthyPercent/maximumPercent, task health và service events.
- Application Auto Scaling thường tạm dừng scale-in trong deployment khi thuộc loại controller hỗ trợ, nhưng ECS scheduler vẫn có thể dừng **task cũ như một phần của rolling deployment**. Đây không nhất thiết là auto scaling scale-in.
- Kiểm tra ALB deregistration delay, SIGTERM/stopTimeout, connection draining, in-flight requests, graceful shutdown của ứng dụng.
- Nếu task đang xử lý queue, cần checkpoint/visibility timeout/idempotency.

**Bài học:** Phân biệt **scale-in do Application Auto Scaling** với **thay task khi triển khai phiên bản mới**.

## 18. Câu hỏi tự kiểm tra

**Câu 1.** Service Auto Scaling và capacity provider khác nhau ở đâu?  
**Đáp án:** Service Auto Scaling thay đổi desired task count; capacity provider quyết định nguồn compute và có thể quản lý capacity để đặt task.

**Câu 2.** ECS Service desiredCount = 8 nhưng runningCount = 4 chứng minh metric CPU không scale được?  
**Đáp án:** Không. Policy có thể đã tăng desiredCount; cần kiểm tra task placement, capacity provider, image, network và lỗi khởi động.

**Câu 3.** Ba predefined metrics phổ biến cho target tracking ECS Service?  
**Đáp án:** ECSServiceAverageCPUUtilization, ECSServiceAverageMemoryUtilization, ALBRequestCountPerTarget khi được hỗ trợ.

**Câu 4.** Hai target tracking policies theo CPU và Memory scale-out khi nào?  
**Đáp án:** Khi một policy cần scale-out; scale-in khi mọi policy có scale-in enabled cùng đủ điều kiện.

**Câu 5.** CPU thấp nhưng task không giảm trong deployment có thể là đúng behavior?  
**Đáp án:** Có. Application Auto Scaling thường tạm dừng scale-in khi ECS deployment đang diễn ra (có ngoại lệ theo deployment controller).

**Câu 6.** Với MinCapacity = 0 và không có task, CPU metric có thể tự đánh thức service không?  
**Đáp án:** Không nên giả định được. Cần metric demand được phát từ bên ngoài tasks, hoặc cơ chế kích hoạt phù hợp.

**Câu 7.** Ý nghĩa base = 2 trên FARGATE khi desiredCount = 10?  
**Đáp án:** Ưu tiên tối thiểu hai task vào FARGATE trước, sau đó chia phần còn lại theo weights.

**Câu 8.** Trong strategy FARGATE weight 1, FARGATE_SPOT weight 3 và không có base, tỷ lệ lý thuyết thế nào?  
**Đáp án:** Khoảng 25% và 75% của task được phân phối theo weight, không phải cam kết chính xác tại mọi thời điểm.

**Câu 9.** Fargate Spot thiếu capacity thì tự chuyển qua Fargate on-demand?  
**Đáp án:** Không. Cần cấu hình baseline/điều phối thay thế thích hợp; Spot không đảm bảo availability.

**Câu 10.** Một cluster có thể chứa cả EC2, Fargate và Managed Instances providers không?  
**Đáp án:** Có theo tính năng hỗ trợ, nhưng **một capacity provider strategy không trộn các họ provider khác nhau**.

**Câu 11.** CapacityProviderReservation đo CPUUtilization EC2 hay tỷ lệ số EC2 needed/available?  
**Đáp án:** Tỷ lệ capacity tính theo instances cần thiết so với instances đang có; không phải CPU utilization.

**Câu 12.** targetCapacity = 80% dùng làm gì?  
**Đáp án:** Hướng ASG provider duy trì capacity headroom theo metric CapacityProviderReservation, không đơn giản giới hạn CPU ở 80%.

**Câu 13.** Khi ASG MaxSize = 2 và managed scaling cần sáu instances, ECS có tự nâng MaxSize không?  
**Đáp án:** Không. Phải cấu hình giới hạn ASG phù hợp; managed scaling không tự thay đổi MaxSize cho bạn.

**Câu 14.** Managed termination protection khác managed draining thế nào?  
**Đáp án:** Protection tránh một số scale-in termination của instance đang chạy task; draining giúp dừng/chuyển task có kiểm soát khi instance bị ngừng.

**Câu 15.** Vì sao target tracking theo SQS queue depth/worker hữu ích?  
**Đáp án:** Nó phản ánh số công việc đang chờ tương quan với số task xử lý, có thể phù hợp hơn CPU khi worker I/O-bound.

**Câu 16.** Task RUNNING có chắc đã nhận được traffic ALB?  
**Đáp án:** Không. Target registration, health checks, network và readiness vẫn quyết định việc nhận request.

**Câu 17.** Cần kiểm tra hai vòng scaling bằng nhóm CLI nào?  
**Đáp án:** Application Auto Scaling describe-scalable-targets/policies/activities cho task count; ECS describe-capacity-providers và ASG describe-auto-scaling-groups cho hạ tầng.

**Câu 18.** Vì sao có thể scale-out nhưng latency vẫn xấu?  
**Đáp án:** Bottleneck có thể ở database/network/IO, ALB targets chưa healthy, startup chậm hoặc cấu hình task/ứng dụng sai.

## 19. Tổng kết và checklist triển khai

**ECS Service Auto Scaling** trả lời câu hỏi **“cần bao nhiêu tasks?”**; **capacity provider** trả lời **“tasks chạy trên compute nào và capacity có theo kịp không?”**.

Khi thiết kế:

1. **Bắt đầu từ workload:** đo CPU, memory, RPS, queue backlog, latency và yêu cầu HA.
2. **Chọn Service Auto Scaling policy:** target tracking cho metric hợp lý, hoặc step/scheduled/predictive theo nhu cầu; khai báo Min/Max và cooldown.
3. **Chọn capacity family:** Fargate cho serverless compute; Spot khi chịu được gián đoạn; EC2 ASG provider cho kiểm soát hạ tầng; ECS Managed Instances khi cần mô hình quản lý EC2 được AWS hỗ trợ.
4. **Tính base/weight:** có on-demand baseline nếu cần; không trộn providers khác họ trong một strategy và không kỳ vọng tỷ lệ tuyệt đối.
5. **Với EC2 provider:** bật managed scaling khi thích hợp, đặt ASG MaxSize, targetCapacity, instance warmup, draining và termination protection đúng.
6. **Bảo vệ ứng dụng:** IAM task/execution roles, image/ECR, VPC/SG, secrets/KMS, health check, SIGTERM và backup/data resilience.
7. **Quan sát cả ba kết quả:** desiredCount thay đổi → RunningCount theo kịp → healthy tasks thực sự cải thiện nghiệp vụ.
8. **Kiểm thử failure modes:** Spot interruption, mất AZ, task quá lớn, thiếu IP, thay phiên bản image, scale về 0/từ 0, database quá tải và rollback.
9. **Kiểm soát chi phí:** right-size task, min/max hợp lý, EC2 headroom/Spot mix, CloudWatch logs, network data transfer và budget alerts.

Tự động mở rộng hiệu quả không chỉ là tăng task thật nhanh. Nó là quá trình cân bằng **availability, latency, khả năng phục hồi, quyền bảo mật, mức tiêu thụ hạ tầng và chi phí** dựa trên quan sát thực tế.

### Tài liệu AWS chính thức

- [Automatically scale your Amazon ECS service](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/service-auto-scaling.html) — Service Auto Scaling, cooldown, deployment và scale-to-zero.
- [Target tracking scaling policies for ECS](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/service-autoscaling-targettracking.html) — predefined metrics và các giới hạn.
- [Application Auto Scaling and Amazon ECS](https://docs.aws.amazon.com/autoscaling/application/userguide/services-that-can-integrate-ecs.html) — scalable target, scaling methods và service-linked role.
- [Amazon ECS capacity providers](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/cluster-capacity-providers.html) — families, strategy và cluster defaults.
- [Amazon ECS Fargate capacity providers](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/fargate-capacity-providers.html) — FARGATE/FARGATE_SPOT, base/weight và interruptions.
- [Amazon ECS EC2 ASG capacity providers](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/asg-capacity-providers.html) — managed scaling, capacity constraints.
- [Amazon ECS managed scaling behavior](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/managed-scaling-behavior.html) — reservation và điều chỉnh ASG.
- [Control instances that ECS terminates](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/managed-termination-protection.html) — managed termination protection.
- [ECS managed instance draining](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/managed-instance-draining.html) — graceful drain của EC2 instances.
- [ECS task definition parameters](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task_definition_parameters.html) — CPU, memory, task/execution roles và container runtime.


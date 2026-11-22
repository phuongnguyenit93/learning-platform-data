# Vòng đời instance, stop, hibernate và terminate trong Amazon EC2

Một Amazon EC2 instance không tồn tại mãi ở trạng thái `running`. Trong quá trình triển khai và vận hành ứng dụng, instance có thể được khởi tạo, khởi động lại, dừng tạm thời, ngủ đông để giữ nội dung RAM hoặc bị chấm dứt hoàn toàn. Mỗi thao tác có tác động khác nhau tới **dữ liệu, địa chỉ IP, tiến trình ứng dụng, tài nguyên đính kèm, khả năng khôi phục và hóa đơn AWS**.

Đây là bài học thuộc chương **Máy chủ EC2** của mô-đun **CLOUD_PROVIDERS_AWS**. Khả năng quản lý đúng vòng đời EC2 là nền tảng để chạy ứng dụng Java/Spring Boot trên hạ tầng VPC, tích hợp IAM và EBS, kết nối RDS/S3, giám sát bằng CloudWatch, xây dựng kiến trúc phục hồi, tự động mở rộng và kiểm soát chi phí.

> **Điểm mấu chốt:** `stop` và `hibernate` đều đưa EC2 instance về trạng thái `stopped` nhưng khác nhau ở việc có giữ RAM hay không; `terminate` chấm dứt instance vĩnh viễn. Dừng tính phí compute không đồng nghĩa mọi chi phí AWS biến mất.

## 1. Kết quả học tập

Sau khi hoàn thành bài này, người học có thể:

1. Giải thích sáu EC2 instance states: `pending`, `running`, `stopping`, `stopped`, `shutting-down`, `terminated`.
2. So sánh `reboot`, `stop/start`, `hibernate/start` và `terminate`.
3. Phân biệt rõ **EBS-backed root volume** và **instance store-backed root volume** trong quyết định dừng instance.
4. Dự đoán những gì **được giữ lại hoặc mất đi**: RAM, EBS volumes, instance store, instance ID, private/public IP, Elastic IP.
5. Nêu các điều kiện bật hibernation tại thời điểm launch: AMI, loại instance, RAM, EBS root, mã hóa và dung lượng đĩa.
6. Kiểm tra thuộc tính `DeleteOnTermination`, stop protection, termination protection và tác động của Auto Scaling.
7. Sử dụng Console/CLI để **quan sát** trạng thái, nhận diện đúng account/Region và xử lý lỗi thường gặp.
8. Quyết định nên stop, hibernate hay terminate dựa trên ứng dụng, thời gian phục hồi, an toàn dữ liệu, chi phí và khả năng tự động hóa.

## 2. Thành phần quyết định điều gì còn tồn tại

Một EC2 instance bao gồm nhiều lớp có vòng đời không hoàn toàn giống nhau:

| Thành phần | Vai trò | Ghi nhớ khi thay đổi state |
|---|---|---|
| **Instance ID** (`i-...`) | Định danh logic của EC2 instance | Thường giữ nguyên qua reboot, stop/start, hibernate/start; instance đã terminate không khởi động lại được |
| **AMI** | Mẫu để tạo instance mới | AMI giúp **tạo** instance khác; không phải bản sao RAM/ứng dụng đang chạy |
| **Root volume** | Chứa hệ điều hành và dữ liệu khởi động | Có thể là EBS hoặc instance store; loại root quyết định khả năng stop/hibernate |
| **EBS data volumes** | Block storage tách khỏi host compute | Dữ liệu thường tồn tại sau stop; khi terminate phụ thuộc `DeleteOnTermination` |
| **Instance store volumes** | Ổ đĩa cục bộ gắn với host vật lý | Dữ liệu **mất** khi stop, hibernate hoặc terminate; có thể giữ khi reboot |
| **Elastic Network Interface (ENI)** | Kết nối VPC, private IPv4, IPv6, Security Groups | Thường được giữ khi stop/hibernate; sau terminate việc xóa/giữ ENI phụ thuộc attachment/lifecycle |
| **Public IPv4 tự động** | IP public không cố định do EC2 tự cấp | Thường mất khi stop/hibernate; khi start có thể được cấp IP khác |
| **Elastic IP** | Địa chỉ IPv4 tĩnh được cấp phát riêng | Có thể giữ liên kết qua stop/start; vẫn có thể phát sinh phí |
| **RAM, tiến trình, socket** | Trạng thái hoạt động tức thời | Mất khi stop/reboot; hibernate tìm cách ghi RAM ra EBS để resume |
| **IAM instance profile** | Role cấp temporary credentials cho workload | Thường giữ cấu hình gắn với instance; credentials đã cấp có thể hết hạn khi dừng lâu |

Đừng nhầm dữ liệu trên **filesystem EBS** với dữ liệu trên **RAM**, **instance store** hay database RDS bên ngoài. EC2 stop không tự tạo snapshot/backup, không sao lưu dữ liệu ra S3 và không bảo đảm một ứng dụng đang ghi file đã được flush sạch trước khi dừng đột ngột.

## 3. Sơ đồ vòng đời của một EC2 instance

AWS công bố sáu trạng thái chính:

~~~mermaid
stateDiagram-v2
    [*] --> pending: Launch instance
    pending --> running: Khởi động thành công
    running --> stopping: Stop hoặc Hibernate
    stopping --> stopped: Hoàn tất dừng
    stopped --> pending: Start instance
    running --> shutting_down: Terminate instance
    stopped --> shutting_down: Terminate instance
    shutting_down --> terminated: Hoàn tất terminate
    terminated --> [*]
    state "shutting-down" as shutting_down
~~~

**Quan sát quan trọng:** AWS **không có state `hibernated` riêng** trong danh sách state tiêu chuẩn. Cả stop và hibernate đều đi qua `stopping` rồi đến `stopped`. Thuộc tính `HibernationOptions.Configured = true` cho biết instance **được cấu hình có khả năng hibernate lúc launch**, không tự chứng minh lần dừng gần nhất đã lưu RAM thành công.

### 3.1. Ý nghĩa và chi phí theo state

| State | Đang xảy ra điều gì? | Compute instance usage |
|---|---|---|
| `pending` | Instance đang khởi tạo hoặc được start lại | Chưa tính phí compute theo state |
| `running` | Instance đã chạy, có thể sử dụng nếu OS/network sẵn sàng | Có tính phí compute |
| `stopping` | Instance thực hiện shutdown hoặc hibernation | Stop thường không tính compute; **hibernate vẫn bị tính phí khi còn `stopping`** |
| `stopped` | Instance đã dừng, không nhận lưu lượng ứng dụng như máy đang chạy | Không tính phí compute, **EBS và tài nguyên khác vẫn có thể tính phí** |
| `shutting-down` | Instance đang được chấm dứt | Không tính phí compute theo state |
| `terminated` | Instance đã chấm dứt vĩnh viễn | Không tính phí compute; kiểm tra tài nguyên còn sót |

Với các cấu hình On-Demand đủ điều kiện tính theo giây, mỗi lượt từ `stopped` sang `running` áp dụng **mức tối thiểu một phút**; sau đó tính theo thời gian sử dụng thực tế. Mô hình giá của Windows, Spot, Dedicated Hosts, Savings Plans/Reserved Instances có các điều kiện riêng; cần xem pricing và cam kết tương ứng.

## 4. So sánh nhanh reboot, stop, hibernate và terminate

| Câu hỏi | Reboot | Stop → Start | Hibernate → Start | Terminate |
|---|---|---|---|---|
| Có thể sử dụng lại instance ID? | Có | Có | Có | **Không** |
| Trạng thái EC2 trung gian | Thường vẫn `running` | `stopping → stopped → pending` | `stopping → stopped → pending` | `shutting-down → terminated` |
| Giữ nội dung RAM? | Không | Không | **Có**, nếu hibernate thành công | Không |
| Giữ data EBS root? | Có | Có | Có | Tùy `DeleteOnTermination`, mặc định thường bị xóa |
| Giữ data EBS volumes khác? | Có | Có | Có | **Tùy từng volume và cách attach** |
| Giữ data instance store? | Thường có | **Không** | **Không** | **Không** |
| Giữ private IPv4/IPv6 trên ENI? | Có | Có | Có | Không còn instance gốc |
| Giữ public IPv4 tự động? | Có | Thường không | Thường không | Không |
| Có thể đổi instance type? | Không trong lúc vẫn running | Có thể trong trạng thái stopped thông thường | **Không tùy tiện thay đổi** khi đang hibernated | Không |
| Compute billing trong lúc không hoạt động | Vẫn tính khi running | Không tính lúc stopped | Không tính lúc stopped; có phí khi hibernating/stopping | Không tính sau khi vào shutting-down |
| Khi nào chọn? | Bảo trì hệ điều hành | Tạm ngừng ứng dụng có thể khởi động lại | Giữ môi trường cần RAM/process state | Ngừng sử dụng vĩnh viễn |

**Reboot không phải stop/start.** Reboot thường diễn ra trên cùng host và giữ instance store/public IPv4. Stop/start có thể chuyển sang host vật lý khác, mất dữ liệu instance store và mất public IPv4 tự động. Hibernate có hành vi tương tự stop ở tầng hạ tầng nhưng thêm bước ghi RAM ra EBS.

## 5. Stop và Start: dừng compute nhưng giữ EBS

### 5.1. Điều kiện để stop

Instance cần sử dụng **Amazon EBS làm root volume** để hỗ trợ `StopInstances`/`StartInstances`. Với instance store-backed root volume, không thể stop/start theo cơ chế EC2 thông thường; cần thiết kế lại dựa trên AMI/EBS hoặc terminate và triển khai lại theo quy trình.

Trước khi stop, kiểm tra:

1. Ứng dụng đã có cơ chế tạm ngừng phục vụ, drain connection và lưu giao dịch chưa?
2. Log, cache, file upload, database transaction có dữ liệu chỉ nằm ở RAM/instance store không?
3. EBS volumes cần giữ đã tồn tại và trạng thái I/O bình thường chưa?
4. Instance có thuộc **Auto Scaling group**, ECS capacity/cluster hoặc hệ thống tự quản lý instance khác không?
5. Có yêu cầu uptime/SLA, lịch bảo trì hay phụ thuộc từ load balancer và DNS không?

### 5.2. EC2 làm gì khi stop?

Theo cơ chế thông thường, EC2 gửi yêu cầu shutdown tới guest OS để các service dừng tương đối an toàn. Nếu OS không dừng sạch trong vài phút, EC2 có thể thực hiện hard shutdown. Sau đó:

- `running → stopping → stopped`.
- Compute capacity được trả lại; khi start lại instance thường có thể chạy trên **host khác**.
- **RAM mất**; tiến trình phải khởi động lại khi OS boot.
- Dữ liệu trên **instance store mất**.
- EBS root và data volumes **được giữ** và thường vẫn gắn với instance logic.
- Primary/private IPv4, IPv6, ENI và Elastic IP đã gắn **được giữ**.
- Public IPv4 do EC2 tự động cấp **bị giải phóng**; khi start lại có thể nhận IP mới.
- Có thể thay đổi một số thuộc tính khi stopped, chẳng hạn instance type, theo giới hạn AWS.

### 5.3. Điều gì xảy ra khi Start?

`StartInstances` chuyển instance từ `stopped → pending → running`. AWS gắn lại EBS và ENI, hệ điều hành **boot lại**, các daemon cần khởi tạo, user-data tùy cấu hình cloud-init/EC2Launch và các dịch vụ khởi chạy theo cơ chế riêng.

Trạng thái `running` chỉ cho biết EC2 đã khởi động ở cấp dịch vụ. Để đánh giá sẵn sàng phục vụ, cần phân biệt:

- **System status checks:** tình trạng hạ tầng host/network AWS.
- **Instance status checks:** tình trạng guest OS hoặc khả năng truy cập của instance.
- **Application readiness:** ứng dụng Spring Boot đã mở cổng, kết nối RDS, xử lý migration, warm cache, đăng ký với load balancer hay chưa.

Chỉ đưa traffic trở lại khi health checks ở cấp ứng dụng đạt yêu cầu. Một instance `running` nhưng Java process chưa sẵn sàng vẫn có thể trả lỗi kết nối.

### 5.4. Stop để tiết kiệm chi phí cần lưu ý gì?

Stop là cách phổ biến để giảm phí compute cho môi trường dev/test chỉ cần giờ hành chính. Tuy nhiên:

- **EBS volumes** còn lưu trữ vẫn tính phí theo dung lượng/provisioned IOPS/throughput tùy loại.
- **Public IPv4 và Elastic IP** có thể tiếp tục bị tính phí theo chính sách hiện hành.
- Snapshot, load balancer, NAT gateway, database, các dịch vụ liên quan không tự dừng.
- Savings Plans/Reserved Instance cam kết dài hạn vẫn có nghĩa vụ tài chính theo điều khoản mua.
- Nếu có EC2 Auto Scaling, việc bạn stop thủ công có thể khiến nhóm đánh dấu instance unhealthy và **tạo instance thay thế**, nên không đạt mục tiêu giảm chi phí.

Do đó, muốn tắt môi trường dev để tiết kiệm, cần xem cả **đơn vị triển khai**: Auto Scaling desired capacity, database, load balancer và tài nguyên đi kèm, có lịch bật/tắt rõ ràng.

## 6. Hibernate: lưu RAM ra EBS rồi dừng instance

### 6.1. Cơ chế hoạt động

**EC2 hibernation** tương tự *suspend-to-disk*:

1. EC2 gửi tín hiệu cho OS thực hiện hibernation.
2. Hệ điều hành đóng băng tiến trình và ghi nội dung **RAM** vào **encrypted EBS root volume**.
3. Instance đi qua `stopping` rồi tới `stopped`; EBS volumes vẫn tồn tại, dữ liệu instance store bị mất.
4. Khi start, EC2 bật host/instance lên; OS tải dữ liệu RAM đã lưu trở lại, các tiến trình được resume từ trạng thái trước đó.

~~~mermaid
flowchart LR
    R["running: OS + JVM + RAM"] --> H["hibernate: ghi RAM vào EBS root"]
    H --> S["stopped: compute không chạy"]
    S --> P["start: đọc RAM từ EBS"]
    P --> R2["running: tiếp tục process state nếu resume thành công"]
~~~

Hibernate hữu ích khi phần mềm cần thời gian dài để khởi động lại, nạp model, tải dữ liệu vào RAM hoặc chuẩn bị môi trường làm việc. Nhưng **giữ RAM không đồng nghĩa giữ mọi kết nối ngoài máy**: socket TCP, DNS, STS session tokens, IAM credentials, database connections, khóa TLS phiên và thời gian timeout có thể đã hết hạn trong lúc instance ngủ. Sau resume, ứng dụng phải biết **reconnect, refresh credentials, revalidate health**.

### 6.2. Điều kiện tiên quyết

| Điều kiện | Yêu cầu |
|---|---|
| Bật ngay từ launch | Phải **enable hibernation khi tạo instance**; không thể bật về sau cho instance đã launch |
| Root volume | Bắt buộc **EBS-backed** |
| Mã hóa | **EBS root phải encrypted**, vì RAM có thể chứa dữ liệu nhạy cảm |
| Dung lượng root | Phải đủ chỗ cho OS, dữ liệu ứng dụng **và dữ liệu RAM** |
| Loại EBS | Các loại hỗ trợ gồm `gp2`, `gp3`, `io1`, `io2` theo tài liệu AWS |
| AMI và OS | Phải dùng AMI hỗ trợ hibernation; với một số distro có bước cấu hình bổ sung |
| Instance type | Chỉ các families/types được AWS hỗ trợ; bare-metal không được hỗ trợ |
| RAM | Theo điều kiện AWS hiện hành: **Linux ít hơn 150 GiB**, **Windows tối đa 16 GiB** |
| Quản lý vòng đời | Không hỗ trợ hibernate instance thuộc **Auto Scaling group** hoặc **được Amazon ECS sử dụng** |

Có thể xem các loại instance hỗ trợ hibernate tại EC2 Console → Instance Types, lọc **On-Demand Hibernation support**, hoặc lệnh CLI:

~~~bash
aws ec2 describe-instance-types \
  --region ap-southeast-1 \
  --filters Name=hibernation-supported,Values=true \
  --query 'InstanceTypes[].InstanceType' \
  --output text
~~~

Danh sách hỗ trợ **thay đổi theo Region/AMI và thời điểm**, nên không giả định mọi kiểu EC2 đều có tính năng này.

### 6.3. Bật hibernate khi khởi tạo

Trong **EC2 Console → Launch instance**, chọn AMI và instance type đủ điều kiện, cấu hình encrypted EBS root có đủ dung lượng, sau đó vào **Advanced details → Stop - Hibernate behavior → Enable** trước khi launch.

Đối với API/CLI, cấu hình hibernate tại launch thông qua `--hibernation-options Configured=true` của `run-instances` cùng root volume đáp ứng các điều kiện. Không nên thử thay đổi `HibernationOptions` của một instance đã tạo vì AWS không hỗ trợ bật hibernate sau launch.

### 6.4. Hibernate một instance đã được cấu hình

AWS CLI dùng thao tác `stop-instances` với tham số `--hibernate`. Ví dụ cú pháp **có tác động đến instance thật**:

~~~bash
# CHỈ MINH HỌA: dừng instance đã cho phép hibernate
aws ec2 stop-instances \
  --instance-ids i-0123456789abcdef0 \
  --hibernate \
  --region ap-southeast-1 \
  --profile dev
~~~

Nếu hibernation **thất bại**, AWS có thể thực hiện **shutdown thông thường**. Vì thế, không thể suy từ state `stopped` rằng RAM chắc chắn được lưu. Kiểm tra nhật ký OS/hibernation, trạng thái ứng dụng sau start và các dấu hiệu AWS tài liệu hóa. Nếu workload **không chấp nhận mất trạng thái RAM**, phải có phương án persistence độc lập hoặc quy trình kiểm chứng recovery.

### 6.5. Hạn chế cần nhớ

- Không hỗ trợ để instance ở trạng thái hibernate **quá 60 ngày**. Theo hướng dẫn AWS, để giữ lâu hơn cần start instance hibernated, stop instance và start lại theo quy trình; thường nên đánh giá giải pháp lưu trạng thái ứng dụng độc lập.
- **Không sửa các thuộc tính instance trong lúc hibernated** như cách sửa một instance stopped thông thường, vì có thể làm mất khả năng resume.
- Hibernation luôn làm **mất dữ liệu instance store**, tương tự stop.
- Hibernation có thể gặp vấn đề với thay đổi phần cứng, kernel/OS, bảo mật hoặc các yêu cầu update trong thời gian ngủ.
- Phí instance compute có thể tiếp tục phát sinh **trong state `stopping` của hibernate** đến khi `stopped`; EBS chứa RAM vẫn được tính phí.
- Một số instance được bật hibernate nhưng OS chưa chuẩn bị xong ngay sau launch; cần đợi và kiểm tra điều kiện theo tài liệu hibernation.

### 6.6. Hibernate với Spot Instances

AWS hỗ trợ hibernation cho **một số Spot Instances** khi có điều kiện phù hợp. Khác với On-Demand, **Spot có thể bị AWS reclaim capacity**:

- Spot request có thể chọn interruption behavior `terminate` (mặc định), `stop` hoặc `hibernate` tùy loại request/cấu hình hỗ trợ.
- Với **Spot bị AWS hibernate do interruption**, chỉ **Amazon EC2** có thể resume khi có capacity/giá phù hợp.
- Với **Spot do người dùng chủ động hibernate**, người dùng có thể yêu cầu start lại theo các điều kiện áp dụng.
- Không được kỳ vọng Spot khôi phục đúng thời gian mong muốn; có thể không có capacity. Ứng dụng quan trọng cần xử lý Spot interruption, lưu state bền vững và thiết kế fallback.

## 7. Terminate: kết thúc instance không thể khôi phục cùng ID

### 7.1. Tác động của TerminateInstances

`TerminateInstances` chuyển instance từ `running` hoặc `stopped` sang `shutting-down` rồi `terminated`. Sau đó:

- Không thể **start** hay kết nối lại vào chính instance đó.
- **Instance ID** không được sử dụng lại để phục hồi instance đã terminate.
- Dữ liệu trên **instance store** bị mất.
- EBS volumes có `DeleteOnTermination = true` bị **xóa** cùng quá trình terminate.
- EBS volumes có `DeleteOnTermination = false` được **giữ lại**, vẫn có thể phát sinh phí và có thể dùng để snapshot/attach vào instance khác.
- Tài nguyên không thuộc vòng đời EC2 (chẳng hạn RDS database, EBS snapshots, S3 buckets) **không tự bị xóa** chỉ vì một instance bị terminate.

**Không thể phục hồi instance đã terminate**. Nếu còn AMI, snapshot hay EBS volumes được giữ lại thì có thể **tạo instance mới**, nhưng đó là bản triển khai khác, có ID, host và nhiều thuộc tính khác. Đây không phải phép “undo Terminate”.

### 7.2. `DeleteOnTermination` là chính sách của *từng EBS volume*

Một quy tắc dễ nhớ là **root EBS mặc định thường có `DeleteOnTermination = true`**. Với EBS data volumes, giá trị mặc định phụ thuộc **thời điểm và cách attach**, cũng như cấu hình AMI/launch template; không được mặc định rằng mọi data volume đều luôn được giữ.

| EBS volume | Ví dụ hành vi mặc định thường thấy | Phải kiểm tra |
|---|---|---|
| Root volume đính kèm lúc launch | Thường `true`, bị xóa khi terminate | Giá trị thật trong block device mapping |
| Data volume thêm sau khi instance chạy | Thường `false`, được giữ lại | Có override từ thao tác attach không? |
| Data volume khai báo ngay lúc launch | Có thể khác theo Console/CLI/AMI | Tuyệt đối kiểm tra `DeleteOnTermination` thực tế |
| Volume cần giữ vì audit hoặc migration | Nên đặt `false`, snapshot/backup phù hợp | Đảm bảo access/encryption/key và dữ liệu đã nhất quán |

Ví dụ một instance có root `/dev/xvda` và data volume `/dev/sdf`. Nếu cả hai đều `DeleteOnTermination=true`, terminate sẽ xóa **cả hai**. Nếu data volume `false`, instance biến mất nhưng EBS vẫn tồn tại và tiếp tục tính phí.

Trong Console, mở **EC2 → Instances → chọn instance → Storage → Block devices → Delete on termination**. Với CLI, có thể đọc thuộc tính trong `BlockDeviceMappings` (xem phần lab).

### 7.3. Termination protection và stop protection

AWS cung cấp các điều khiển giảm nguy cơ thao tác nhầm:

- **Termination protection** là thuộc tính `DisableApiTermination`. Khi bật, nó ngăn terminate qua EC2 Console/CLI/API trong trường hợp hỗ trợ.
- **Stop protection** là thuộc tính `DisableApiStop`. Khi bật, nó ngăn thao tác stop ngoài ý muốn qua Console/CLI/API; theo hành vi AWS, nó còn ngăn terminate qua các giao diện này khi đang bật.
- Các cơ chế bảo vệ **không bảo đảm ngăn mọi trường hợp**: shutdown phát sinh từ guest OS theo `InstanceInitiatedShutdownBehavior`, AWS scheduled events hoặc xử lý của Auto Scaling có quy tắc riêng.
- Auto Scaling có **scale-in protection** riêng ở nhóm; nó không đồng nghĩa termination protection của một EC2 instance.

Dù bật protection, vẫn cần backup, least-privilege IAM, change approval và giám sát. Đây là lớp bảo vệ chống thao tác nhầm, không phải chiến lược khôi phục dữ liệu hoàn chỉnh.

### 7.4. Khi nào Terminate là lựa chọn đúng?

Terminate phù hợp nếu instance được tạo từ **Infrastructure as Code/AMI/container image**, mọi state quan trọng đã nằm trên S3/EBS được giữ/RDS/EFS hoặc hệ thống backup, và nhóm muốn giải phóng vòng đời instance cũ. Đây thường là cách vận hành **immutable infrastructure**: thay instance bằng bản mới đã kiểm thử, sau đó terminate bản cũ.

Terminate không phù hợp nếu người vận hành chưa biết dữ liệu local nào cần giữ, chưa kiểm tra `DeleteOnTermination`, chưa có backup, hoặc ứng dụng duy nhất đang phục vụ traffic mà chưa có kế hoạch chuyển tải.

## 8. Shutdown trong guest OS và thao tác qua AWS API

Người học cần phân biệt ba bối cảnh:

1. **Reboot qua OS/EC2:** khởi động lại hệ điều hành, không tạo ra trạng thái stopped.
2. **Stop qua EC2 Console/API/CLI:** API gửi yêu cầu shutdown cho guest OS và chuyển state theo mô hình EC2.
3. **OS shutdown/poweroff thực hiện bên trong EC2:** với EBS-backed instances, hành vi `InstanceInitiatedShutdownBehavior` quyết định liệu instance **stop** hay **terminate**; mặc định thường là `stop`.

Ví dụ nếu ai đó đổi `InstanceInitiatedShutdownBehavior` thành `terminate`, lệnh tắt máy trong OS có thể dẫn tới việc **mất instance** khi shutdown, khác hẳn kỳ vọng dừng tạm thời. Cần đọc thuộc tính này trước khi dùng lệnh shutdown trong script.

Lưu ý: lệnh Linux `halt` theo cơ chế `HLT` không nhất thiết làm instance vào trạng thái `stopped`; instance có thể vẫn tính phí `running`. Khi cần stop có audit, AWS khuyên dùng Console/CLI/API để request được ghi lại trong CloudTrail.

**Force stop/skip OS shutdown** bỏ qua quy trình shutdown an toàn và có thể làm mất dữ liệu chưa flush hoặc gây corruption. Chỉ sử dụng khi có quy trình xử lý sự cố và hiểu ảnh hưởng tới filesystem/database.

## 9. Địa chỉ IP, mạng VPC và truy cập ứng dụng

### 9.1. Điều gì xảy ra với IP?

| Thuộc tính mạng | Reboot | Stop/Start hoặc Hibernate/Start | Terminate |
|---|---|---|---|
| Primary private IPv4 trên ENI | Giữ | Giữ | Instance gốc mất |
| IPv6 trên ENI | Giữ | Giữ | Phụ thuộc ENI được giữ/xóa |
| Public IPv4 tự động | Giữ | Thường giải phóng và cấp IP khác lúc start | Giải phóng |
| Elastic IP đã associate | Giữ | Thường duy trì association và có phí | Cần kiểm tra release/disassociate và phí |
| Security Group gắn ENI | Giữ | Giữ | Nếu ENI bị xóa thì không còn attachment đó |
| VPC, subnet, route tables | Không đổi | Không đổi | Các tài nguyên VPC độc lập còn tồn tại |

Nếu ứng dụng dùng **public IPv4 tự động** trong DNS A record cố định hoặc danh sách allowlist của đối tác, stop/start có thể làm cấu hình sai. Thường nên đặt Application Load Balancer, Route 53 và domain ổn định trước instance; với trường hợp thực sự cần public IPv4 tĩnh, có thể dùng Elastic IP và tính chi phí tương ứng.

### 9.2. Start lại chưa đồng nghĩa hệ thống phục vụ được

Ví dụ EC2 chạy API Spring Boot `:8080` sau start:

- EC2 có thể `running` trước khi Spring Boot load đủ dependency và database connection.
- Load balancer target có thể chưa đạt health check nên chưa nhận traffic.
- EBS được giữ nhưng **local cache trong RAM** đã mất nếu stop; startup có thể cần warm cache.
- STS credentials, database sessions, TLS connection đang giữ trong RAM có thể đã hết hạn nếu hibernate.

Giải pháp là dùng readiness probes/target health, connection retry/backoff và thiết kế ứng dụng coi stop/start là một sự kiện vận hành bình thường.

### 9.3. Region/AZ và host

EC2 instance thuộc một AZ trong Region; khi stop/start, instance ID/ENI/subnet vẫn thuộc vị trí logic đó, nhưng thường được di chuyển đến **host vật lý khác**. Vì vậy đừng dựa vào đặc điểm của host cũ (instance store, local hardware state, một số thông số môi trường) để bảo đảm kết quả sau start. Một số cấu hình như Dedicated Host có ngoại lệ. Khởi động lại có thể thất bại nếu AZ/instance type thiếu capacity.

## 10. Chi phí theo vòng đời

Khi quyết định dừng một EC2, cần tách các lớp chi phí:

| Chi phí | Running | Stopped/Hibernated | Terminated |
|---|---|---|---|
| EC2 compute On-Demand | Có | Không khi `stopped`; **hibernate vẫn bị tính trong `stopping`** | Không sau `shutting-down` |
| EBS root/data volumes | Có | **Có**, EBS vẫn tồn tại | Có nếu volume được giữ |
| EBS snapshots | Có nếu snapshot tồn tại | Có | Có cho snapshot còn giữ |
| Public IPv4 / Elastic IP | Có thể tính phí | Có thể **vẫn tính phí** | Có thể tính nếu IP allocation còn giữ |
| RDS, NAT Gateway, ALB, S3... | Tính độc lập | **Không tự dừng** | **Không tự xóa** |
| Savings Plans/Reserved Instances | Theo cam kết mua | Cam kết tiếp tục có hiệu lực | Cam kết tiếp tục có hiệu lực |

**Ví dụ giả định:** Một instance dùng để chạy Spring Boot ở dev chỉ cần sử dụng 8 giờ/ngày. Nếu là EC2 On-Demand EBS-backed, stop 16 giờ còn lại có thể giảm compute usage. Tuy nhiên, nhóm phải tính EBS và IPv4 billing, các dịch vụ dữ liệu/ALB, và xác minh không có Auto Scaling tạo lại instance. Đây là **cơ hội tối ưu chi phí**, không phải công thức giảm đúng 2/3 hóa đơn toàn môi trường.

Hibernate dùng EBS root lớn hơn để lưu RAM nên **phí EBS có thể tăng** so với stop thông thường. Cân nhắc giá trị của thời gian khôi phục nhanh so với dung lượng EBS và rủi ro ứng dụng không resume được.

## 11. EC2 Auto Scaling, Spot và hạ tầng tự phục hồi

### 11.1. Instance thuộc Auto Scaling group

Với Amazon EC2 Auto Scaling (ASG), mục tiêu là duy trì **desired capacity**. Khi một instance bị stop hoặc đánh dấu unhealthy, ASG có thể **terminate và tạo instance khác** để đáp ứng số lượng mong muốn. Vì thế:

- Không stop thủ công một instance do ASG quản lý rồi giả định nó sẽ nằm yên ở `stopped`.
- Nếu muốn giảm số máy, điều chỉnh ASG desired/min capacity theo quy trình, cân nhắc graceful scale-in và target draining.
- **Instance scale-in protection** giúp bảo vệ khỏi một số scale-in do ASG, nhưng không thay thế EC2 stop/termination protection và các cơ chế khác.
- **Hibernate không được hỗ trợ cho instance trong ASG hoặc instance được ECS sử dụng** theo các hạn chế EC2 hiện hành.

### 11.2. Spot Instances có vòng đời đặc biệt

Spot được cung cấp từ spare capacity và **có thể bị gián đoạn**. Hành vi mặc định khi AWS interrupt là terminate, nhưng một số Spot request hỗ trợ stop/hibernate nếu thiết lập và điều kiện phù hợp.

- Instance bị AWS interrupt khi `terminate` sẽ mất instance như thông thường.
- Spot bị stop/hibernate có thể chưa start/resume lại được cho tới khi có capacity và đáp ứng ràng buộc giá.
- Spot request có vòng đời riêng với EC2 instance và có thể khiến instance mới được tạo sau sự kiện.
- Tránh đặt trạng thái duy nhất của database, queue consumer hay batch job vào RAM/instance store của Spot; dùng checkpoint trên S3/EBS/RDS hoặc dịch vụ phù hợp.

Ứng dụng quan trọng cần đảm bảo phục hồi từ **nguồn dữ liệu bền vững** và xử lý interruption, thay vì coi hibernate là bảo đảm luôn resume ngay.

## 12. Quy trình thao tác an toàn trên AWS Console

### 12.1. Kiểm tra trước khi thay đổi trạng thái

1. Đăng nhập **đúng AWS account/role**, chọn đúng Region; dùng MFA/Identity Center theo tổ chức.
2. Mở **EC2 → Instances**, lọc instance ID hoặc tag `Name`; xác nhận loại máy, AZ, owner, ASG/Spot hay On-Demand.
3. Trong tab **Storage**, kiểm tra root device type và **Delete on termination** của từng EBS volume.
4. Trong tab **Details**, kiểm tra hibernation enabled, stop protection, termination protection và shutdown behavior.
5. Xem application health/log, target group, snapshots/backup và phụ thuộc RDS/S3/queue.
6. Xác định mục tiêu: bảo trì OS (reboot), tạm dừng compute (stop), giữ RAM (hibernate) hay hủy instance (terminate).
7. Thực hiện theo runbook/change approval tương ứng; theo dõi state và xác minh lại ứng dụng sau start.

### 12.2. Các thao tác trong Console

- **Reboot:** Chọn instance → **Instance state → Reboot instance**.
- **Stop:** **Instance state → Stop instance**; chỉ có với cấu hình hỗ trợ.
- **Hibernate:** **Instance state → Hibernate instance**, chỉ khả dụng khi đã bật lúc launch và đáp ứng prerequisites.
- **Start:** Chọn instance `stopped` → **Instance state → Start instance**.
- **Terminate:** **Instance state → Terminate (delete) instance**; xác nhận instance ID, EBS deletion flags, backups và approval trước khi thực hiện.

Sau khi stop hoặc hibernate, trạng thái sẽ hiển thị `stopped`. Đây chỉ là trạng thái EC2; quy trình cần biết **lần dừng thực tế dùng thao tác nào** và có lưu RAM thành công không.

## 13. AWS CLI: kiểm tra trạng thái và thuộc tính quan trọng

### 13.1. Xác nhận identity và Region trước mọi thao tác

Các ví dụ dùng AWS CLI v2, profile `dev` đã có quyền đọc và Region `ap-southeast-1`. Thay bằng account/Region thực tế của môi trường học:

~~~bash
aws --version
aws sts get-caller-identity --profile dev --output json

aws ec2 describe-instances \
  --profile dev \
  --region ap-southeast-1 \
  --query 'Reservations[].Instances[].{Id:InstanceId,State:State.Name,Type:InstanceType,Root:RootDeviceType,HibernateEnabled:HibernationOptions.Configured,PrivateIP:PrivateIpAddress,PublicIP:PublicIpAddress}' \
  --output table
~~~

Tùy chọn `--query` lấy ra các trường cần quan sát; nếu dùng `--output table` mà không có instance trong Region này, kết quả có thể trống. Khi muốn lọc theo tag `Name`, nên dùng thêm bộ lọc EC2 `--filters Name=tag:Name,Values=...` với giá trị cụ thể, tùy yêu cầu.

### 13.2. Xem một instance cụ thể

~~~bash
# Đọc-only: không thay đổi trạng thái
aws ec2 describe-instances \
  --profile dev \
  --region ap-southeast-1 \
  --instance-ids i-0123456789abcdef0 \
  --query 'Reservations[].Instances[].{Id:InstanceId,State:State.Name,RootDevice:RootDeviceType,Type:InstanceType,HibernateEnabled:HibernationOptions.Configured,PrivateIP:PrivateIpAddress,PublicIP:PublicIpAddress}' \
  --output json
~~~

Kết quả **minh họa**:

~~~json
[
  {
    "Id": "i-0123456789abcdef0",
    "State": "stopped",
    "RootDevice": "ebs",
    "Type": "t3.small",
    "HibernateEnabled": true,
    "PrivateIP": "10.0.1.25",
    "PublicIP": null
  }
]
~~~

Ở ví dụ trên, `HibernateEnabled: true` chỉ là **cấu hình hỗ trợ**. Không suy ra RAM của lần stop cuối còn được lưu. Nếu cần biết điều này, kiểm tra hoạt động stop/hibernate thực tế và hibernation logs.

### 13.3. Kiểm tra `DeleteOnTermination`

~~~bash
aws ec2 describe-instances \
  --profile dev \
  --region ap-southeast-1 \
  --instance-ids i-0123456789abcdef0 \
  --query 'Reservations[].Instances[].BlockDeviceMappings[].{Device:DeviceName,Volume:Ebs.VolumeId,DeleteOnTermination:Ebs.DeleteOnTermination}' \
  --output table
~~~

Mục đích là biết volume nào **có thể bị xóa khi terminate**. Luôn kiểm tra từng mapping, không mặc định chỉ có root volume chịu ảnh hưởng.

### 13.4. Kiểm tra hai loại protection và shutdown behavior

~~~bash
aws ec2 describe-instance-attribute \
  --profile dev \
  --region ap-southeast-1 \
  --instance-id i-0123456789abcdef0 \
  --attribute disableApiTermination

aws ec2 describe-instance-attribute \
  --profile dev \
  --region ap-southeast-1 \
  --instance-id i-0123456789abcdef0 \
  --attribute disableApiStop

aws ec2 describe-instance-attribute \
  --profile dev \
  --region ap-southeast-1 \
  --instance-id i-0123456789abcdef0 \
  --attribute instanceInitiatedShutdownBehavior
~~~

Ba lệnh chỉ đọc. Một số state/loại instance có giới hạn khi truy vấn hoặc dùng các thuộc tính này; nếu gặp `AccessDenied`, kiểm tra quyền `ec2:DescribeInstanceAttribute`.

### 13.5. Đọc-only các instance theo state

~~~bash
aws ec2 describe-instances \
  --profile dev \
  --region ap-southeast-1 \
  --filters Name=instance-state-name,Values=running,stopped \
  --query 'Reservations[].Instances[].{Id:InstanceId,State:State.Name,Type:InstanceType,AZ:Placement.AvailabilityZone}' \
  --output table
~~~

Lệnh này hữu ích khi audit tài nguyên còn tính phí EBS hoặc những máy dev đã stop lâu. Nếu danh sách trống, kiểm tra account, Region và quyền IAM trước khi kết luận không có instance.

## 14. Lệnh đổi trạng thái: chỉ dùng khi được cấp quyền thực hiện

Những lệnh dưới đây **có tác động thật**, được cung cấp để người học hiểu cú pháp. Chỉ chạy trong môi trường lab được phép, đã xác minh account, Region, instance ID, backup, phụ thuộc và chính sách thay đổi.

~~~bash
# Stop một EBS-backed instance (RAM/instance store sẽ mất)
aws ec2 stop-instances \
  --instance-ids i-0123456789abcdef0 \
  --profile dev \
  --region ap-southeast-1

# Start sau khi instance stopped
aws ec2 start-instances \
  --instance-ids i-0123456789abcdef0 \
  --profile dev \
  --region ap-southeast-1

# Hibernate instance đã enable tại launch (có thể fallback sang stop)
aws ec2 stop-instances \
  --instance-ids i-0123456789abcdef0 \
  --hibernate \
  --profile dev \
  --region ap-southeast-1

# Terminate: XÓA INSTANCE VĨNH VIỄN; EBS deletion theo mapping
aws ec2 terminate-instances \
  --instance-ids i-0123456789abcdef0 \
  --profile dev \
  --region ap-southeast-1
~~~

Với các operation hỗ trợ, có thể dùng `--dry-run` để hỏi EC2 liệu principal có quyền gọi API; lệnh có thể trả lỗi `DryRunOperation` dù được phép, hoặc `UnauthorizedOperation` nếu bị từ chối. `--dry-run` **không đảm bảo** operation sau đó sẽ thành công, không kiểm tra toàn bộ tác động ứng dụng và không thay cho change approval.

AWS CLI cũng có **waiters** để đợi state sau một thao tác đã được cho phép:

~~~bash
aws ec2 wait instance-stopped \
  --instance-ids i-0123456789abcdef0 \
  --profile dev \
  --region ap-southeast-1

aws ec2 wait instance-running \
  --instance-ids i-0123456789abcdef0 \
  --profile dev \
  --region ap-southeast-1
~~~

`instance-running` waiter chỉ kiểm tra state; **không chứng minh** ứng dụng khỏe. Hãy kiểm tra EC2 status checks và endpoint/ALB target health trước khi hoàn tất bảo trì.

## 15. Kiểm toán, giám sát và tự động hóa vòng đời

### 15.1. EventBridge state-change notification

Amazon EC2 gửi event có `source = aws.ec2` và `detail-type = EC2 Instance State-change Notification` qua **Amazon EventBridge** khi state thay đổi. Ví dụ sự kiện:

~~~json
{
  "source": "aws.ec2",
  "detail-type": "EC2 Instance State-change Notification",
  "detail": {
    "instance-id": "i-0123456789abcdef0",
    "state": "stopped"
  }
}
~~~

Đoạn trên là **mẫu event pattern rút gọn** để học, không phải full EventBridge event có tất cả các trường metadata. Có thể dùng EventBridge Rules để gọi Lambda/SNS/Step Functions khi instance `stopped` hoặc `terminated`, từ đó thông báo nhóm trực hoặc kích hoạt quy trình vận hành đã thiết kế.

### 15.2. CloudTrail, CloudWatch và AWS Systems Manager

- **AWS CloudTrail:** kiểm toán API như `StopInstances`, `StartInstances`, `TerminateInstances` và thay đổi protection theo cấu hình log; biết **ai** thực hiện, **khi nào**, account và Region.
- **Amazon CloudWatch:** theo dõi metrics của instance lúc hoạt động, status check, alarms, logs ứng dụng; phân biệt thiếu metric do máy đã stopped với lỗi monitoring.
- **AWS Systems Manager:** có thể hỗ trợ automation/runbook, maintenance windows, patching và thao tác vận hành theo IAM.
- **AWS Backup/EBS snapshots:** giúp phục hồi dữ liệu của EBS theo thiết kế; snapshot chỉ bảo vệ dữ liệu đã được sao lưu, không tự đảm bảo consistency của database đang ghi nếu không có quiesce/snapshot coordination.
- **IaC và deployment pipelines:** lưu launch template, user data, ASG, volumes, alarm, tags và policy trong mã nguồn để tái dựng hạ tầng.

### 15.3. Mẫu automation tắt máy dev

Quy trình phù hợp cho EC2 phát triển **không nằm trong Auto Scaling**:

1. Gắn tags như `environment=dev`, `schedule=office-hours` và owner.
2. Vào cuối ngày, automation kiểm tra tag, state, phụ thuộc, sau đó stop theo thời gian tổ chức duyệt.
3. Sáng hôm sau, start lại; chờ state và health checks rồi xác nhận application readiness.
4. Ghi log kết quả, thông báo nếu fail, và có cơ chế loại trừ những instance không được phép dừng.
5. Theo dõi chi phí **toàn bộ stack**, kể cả EBS, IPv4, database, load balancer và snapshots.

Không dùng automation này trên production/ASG/ECS hoặc máy chạy batch quan trọng nếu chưa có thiết kế tương ứng.

## 16. Troubleshooting theo triệu chứng

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| Nút **Stop** bị vô hiệu | Root instance store, state không hỗ trợ, stop protection hoặc IAM deny | Đọc `RootDeviceType`, `State.Name`, `DisableApiStop` và quyền IAM |
| `IncorrectInstanceState` khi start/stop | Instance đang chuyển state hoặc đã ở state không phù hợp | Chạy `describe-instances`, đợi kết thúc transition |
| Hibernate không xuất hiện | Không enable lúc launch, AMI/instance/RAM/EBS không phù hợp, môi trường bị hạn chế | Kiểm tra `HibernationOptions.Configured` và prerequisites |
| Hibernate ra `stopped` nhưng RAM mất sau start | Hibernate thất bại rồi fallback normal stop; vấn đề OS/dung lượng | Kiểm tra system/hibernation logs, root EBS capacity/encryption, app state |
| Instance `stopping` quá lâu | OS không clean shutdown, I/O hoặc hibernation gặp sự cố | Xem EC2 status/system logs; tránh force stop nếu chưa đánh giá dữ liệu |
| `UnauthorizedOperation` / `AccessDenied` | IAM policy/SCP/permission boundary thiếu quyền | Kiểm tra `sts get-caller-identity` và IAM request/action |
| `start-instances` báo thiếu capacity | AZ/type/placement/capacity constraints | Kiểm tra thông báo, capacity reservation/type/AZ, runbook thay thế |
| Start xong mất kết nối SSH/HTTP qua IP cũ | Public IPv4 tự động đã thay đổi | Kiểm tra `PublicIpAddress`; cân nhắc Elastic IP hoặc DNS/ALB |
| EC2 `running` nhưng API vẫn lỗi | App chưa ready, DB/TLS/credentials đã hết hạn, SG/NACL | Kiểm tra app logs, health endpoint, target health, network |
| Terminate bị chặn | Termination protection hoặc stop protection đang bật | Xem cả `DisableApiTermination` và `DisableApiStop`, xác minh approval |
| Stop thủ công nhưng instance mới xuất hiện | Auto Scaling/ECS/Fleet đang quản lý desired capacity | Kiểm tra ASG/Spot/Fleet trước khi chỉnh instance đơn lẻ |
| Terminate nhưng phí vẫn tăng | EBS/IPv4/snapshot/ALB/RDS/NAT và cam kết tài chính còn | Kiểm tra billing theo service/resource và cleanup plan |
| File dữ liệu biến mất sau stop | File ở instance store hoặc memory/cache thay vì EBS | Xem mounts/storage layout; dùng EBS/EFS/S3 cho dữ liệu cần giữ |
| Cannot restart hibernated Spot | Chưa có capacity hoặc request/price không phù hợp | Kiểm tra Spot request và interruption behavior |

**Với production:** khi một instance không đáp ứng, ưu tiên điều tra status checks, ứng dụng, network và persistent storage. Stop/start thường thay host và giải phóng RAM, có thể giúp xử lý lỗi hệ thống nhưng cũng xóa bằng chứng trong bộ nhớ và gây outage; cần cân nhắc mục tiêu khôi phục trước khi thao tác.

## 17. Bài thực hành chỉ đọc: xác định hành động phù hợp

### 17.1. Điều kiện

Có AWS account học tập với profile `dev`, quyền đọc EC2 và STS. **Không cần tạo EC2 instance để làm bài**; có thể dùng output mẫu. Các ví dụ dùng Region Singapore (`ap-southeast-1`).

### 17.2. Phần A — Nhận diện account và state

~~~bash
aws sts get-caller-identity --profile dev

aws ec2 describe-instances \
  --profile dev \
  --region ap-southeast-1 \
  --query 'Reservations[].Instances[].{Id:InstanceId,State:State.Name,Root:RootDeviceType,Type:InstanceType,HibernateEnabled:HibernationOptions.Configured}' \
  --output table
~~~

Với mỗi instance, ghi `Id`, state, root device type và khả năng hibernate. Giải thích vì sao **hibernation enabled** chưa đủ chứng minh dữ liệu RAM vẫn còn nếu instance đang `stopped`.

### 17.3. Phần B — Dự đoán dữ liệu còn/mất

Tình huống: EC2 EBS-backed chạy Spring Boot có:
- file cấu hình trên EBS root;
- tệp tạm batch tại local instance store;
- Redis client connections và cache trong RAM;
- private IPv4 trong subnet, public IPv4 tự động.

Lập bảng dự đoán những gì còn/mất sau `reboot`, `stop/start`, `hibernate/start`, `terminate`. So sánh với bảng ở mục 4 và giải thích tại sao không nên lưu dữ liệu duy nhất trên instance store.

### 17.4. Phần C — Đọc EBS deletion flags

Nếu có instance ID hợp lệ:

~~~bash
aws ec2 describe-instances \
  --profile dev \
  --region ap-southeast-1 \
  --instance-ids i-0123456789abcdef0 \
  --query 'Reservations[].Instances[].BlockDeviceMappings[].{Device:DeviceName,DeleteOnTermination:Ebs.DeleteOnTermination,VolumeId:Ebs.VolumeId}' \
  --output json
~~~

Câu hỏi: nếu terminate, volume nào có thể bị xóa? Volume nào còn có thể tính phí? Nếu một volume cần giữ lại, nhóm phải làm gì **trước** khi thực hiện thao tác thật?

### 17.5. Phần D — Lựa chọn hành động theo mục tiêu

| Tình huống | Lựa chọn sơ bộ | Điều kiện kiểm tra |
|---|---|---|
| Bảo trì service Java và cần khởi động lại OS | Reboot | Có rollout/health check, không dựa vào RAM hiện tại |
| Máy dev không dùng ban đêm, dữ liệu ở EBS | Stop | Không nằm trong ASG, có lịch start, kiểm soát EBS/IPv4 cost |
| Workstation tính toán lớn cần resume RAM | Hibernate | Đã bật tại launch, RAM/AMI/EBS phù hợp, quy trình reconnect |
| Thay instance ứng dụng bằng immutable deployment mới | Terminate instance cũ | Traffic đã drain, backup/snapshot và `DeleteOnTermination` đã kiểm tra |
| EC2 production trong ASG bị lỗi | Theo runbook ASG/repair | Xem desired capacity/health, tránh stop đơn lẻ ngoài quy trình |
| Batch job trên Spot có nguy cơ interruption | Checkpoint và retry | Xác định behavior stop/hibernate/terminate, capacity không bảo đảm |

### 17.6. Phần E — Kiểm tra khả năng phục hồi

Đối với ứng dụng Spring Boot chạy trên EC2, viết ngắn một runbook sau start/hibernate resume:

1. Xác nhận trạng thái EC2 và status checks.
2. Xác nhận EBS mounts, secret/STS credential refresh, connection pool RDS.
3. Kiểm tra logs, application health và cache cần nạp lại.
4. Xác nhận target group/ALB nhận traffic và kiểm tra lỗi 5xx.
5. Kiểm tra CloudTrail/EventBridge event và thời gian phục hồi thực tế.

Bài thực hành hoàn thành khi người học phân biệt đúng **state của EC2** với **readiness của ứng dụng** và chỉ ra được dữ liệu/chi phí bị ảnh hưởng bởi mỗi thao tác.

## 18. Câu hỏi tự kiểm tra

1. Khi `stopped`, EC2 có bị tính phí compute không? Những chi phí nào vẫn có thể còn?
2. Vì sao EC2 EBS-backed có thể stop nhưng instance store-backed root không thể stop theo cơ chế thông thường?
3. `Reboot` và `Stop/Start` khác nhau thế nào về RAM, public IPv4 và dữ liệu instance store?
4. Có thể bật hibernation cho instance đã launch từ nhiều tuần trước không?
5. Hibernate lưu RAM vào đâu và tại sao root EBS phải được mã hóa?
6. Khi hibernation thất bại, điều gì có thể xảy ra thay vì resume RAM?
7. Một instance đang `stopped` và có `HibernationOptions.Configured=true` có chắc chắn đã được hibernate thành công không?
8. Điều gì khác nhau giữa `DeleteOnTermination=true` và `false`?
9. Vì sao bật termination protection không đủ bảo vệ khỏi mọi rủi ro trong Auto Scaling hoặc shutdown từ OS?
10. Vì sao stop một instance trong Auto Scaling group có thể dẫn đến instance thay thế?
11. Start xong EC2 `running` nhưng load balancer target vẫn unhealthy. Cần kiểm tra những gì?
12. Trong trường hợp sử dụng Spot, ai có quyền resume instance khi AWS là bên chủ động hibernate do interruption?
13. Hibernate hơn 60 ngày có phù hợp với giới hạn AWS hiện hành không?
14. Nếu team dùng immutable deployment và không có dữ liệu local duy nhất, lúc thay phiên bản ứng dụng nên ưu tiên phương án nào?
15. Làm thế nào theo dõi một thay đổi `running → stopped` qua EventBridge và điều tra người thực hiện qua CloudTrail?

### Đáp án định hướng

- **Stop:** giữ EBS/instance ID/private IP nhưng mất RAM, instance store và thường mất public IPv4 tự động.
- **Hibernate:** giống stop ở tầng compute, thêm lưu RAM vào encrypted EBS root; phải bật tại launch và kiểm tra giới hạn.
- **Terminate:** instance không phục hồi được, data EBS phụ thuộc từng `DeleteOnTermination`, nhiều tài nguyên khác vẫn có thể tính phí.
- **Vận hành an toàn:** xác minh account/Region/IAM, phương án backup, ASG/Spot dependencies, application readiness và billing ngoài compute.

## 19. Tài liệu AWS chính thức

1. [Amazon EC2 instance state changes](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-instance-lifecycle.html) — Sáu states, sơ đồ vòng đời và bảng so sánh reboot/stop/hibernate/terminate.
2. [Stop and start Amazon EC2 instances](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/Stop_Start.html) — Điều kiện EBS-backed và thao tác stop/start.
3. [How EC2 instance stop and start works](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/how-ec2-instance-stop-start-works.html) — RAM, instance store, EBS, ENI, private/public IP và phí.
4. [Hibernate your Amazon EC2 instance](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/Hibernate.html) — Tổng quan hibernation và cơ chế resume.
5. [Prerequisites for EC2 instance hibernation](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/hibernating-prerequisites.html) — AMI, instance family, RAM, root EBS, encryption.
6. [How EC2 instance hibernation works](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/instance-hibernate-overview.html) — Dữ liệu giữ/mất và giới hạn 60 ngày.
7. [Enable hibernation for an instance](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/enabling-hibernation.html) — Bật lúc launch và kiểm tra `HibernationOptions`.
8. [Terminate Amazon EC2 instances](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/terminating-instances.html) — Tính vĩnh viễn của terminate và quy trình.
9. [Preserve data when an instance is terminated](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/preserving-volumes-on-termination.html) — `DeleteOnTermination` và các giá trị mặc định cần kiểm tra.
10. [Change instance termination protection](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/Using_ChangingDisableAPITermination.html) — Thuộc tính `DisableApiTermination`.
11. [Enable stop protection](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-stop-protection.html) — Thuộc tính `DisableApiStop`.
12. [State change events for EC2 instances](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/monitoring-instance-state-changes.html) — EventBridge notifications.
13. [Spot Instance interruption behavior](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/interruption-behavior.html) — Stop/hibernate/terminate khi Spot bị reclaim.
14. [Amazon EC2 On-Demand Pricing](https://aws.amazon.com/ec2/pricing/on-demand/) — Cơ chế tính phí compute theo cấu hình.

> **Ghi nhớ cuối bài:** Trước khi nhấn Stop, Hibernate hoặc Terminate, hãy xác định **identity/account/Region, root volume, nơi lưu dữ liệu quan trọng, EBS deletion flags, Auto Scaling/Spot dependencies, phục hồi ứng dụng và chi phí còn lại**. Quyết định đúng vòng đời instance giúp hệ thống AWS bảo vệ dữ liệu, phục hồi có kiểm soát và tránh lãng phí ngân sách.


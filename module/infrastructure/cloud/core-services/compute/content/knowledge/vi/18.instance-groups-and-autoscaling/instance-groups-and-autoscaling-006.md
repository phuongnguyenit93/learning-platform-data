# Giới hạn min, max, desired capacity và dự phòng tài nguyên

Một nhóm máy có thể tự động tăng số instance khi tải tăng, nhưng autoscaling chỉ hoạt động an toàn khi nhóm có giới hạn và mức capacity được thiết kế rõ ràng. Nếu minimum quá thấp, hệ thống thiếu năng lực trong lúc chờ scale out. Nếu maximum quá cao, autoscaler có thể tạo quá nhiều máy, vượt quota hoặc làm database quá tải. Nếu desired capacity không phản ánh đúng nhu cầu, nhóm máy có thể chạy thiếu hoặc thừa tài nguyên dù chính sách scaling đã được bật.

Ba giá trị **minimum capacity**, **maximum capacity** và **desired capacity** tạo thành khung kiểm soát cho một nhóm máy. Chúng cần được tính cùng tải nền, tải đỉnh, thời gian khởi tạo instance, khả năng chịu lỗi, giới hạn dịch vụ phụ thuộc và ngân sách. Bài học này giải thích ý nghĩa từng giá trị, cách ước lượng capacity, cách dự phòng tài nguyên và cách kiểm chứng cấu hình trên instance group, VM scale set và Kubernetes.

## 1. Capacity là gì?

Capacity là năng lực hệ thống có thể cung cấp để xử lý công việc trong một khoảng thời gian mà vẫn đáp ứng yêu cầu về độ trễ, lỗi và tính sẵn sàng.

Capacity không chỉ là số lượng VM. Một nhóm 10 VM có thể có năng lực khác nhau tùy:

- Loại máy, số vCPU và thế hệ CPU.
- Dung lượng RAM và giới hạn bộ nhớ của workload.
- IOPS, throughput và latency của storage.
- Băng thông mạng, packet rate và số kết nối.
- Phần mềm, runtime, cấu hình worker và thread pool.
- Giới hạn database, message broker và API phụ thuộc.
- Tỷ lệ instance khỏe mạnh và phân bố theo availability zone.
- Thời gian bootstrap, warm-up và đăng ký vào load balancer.

Một nhóm máy chỉ có capacity hữu ích khi instance đã sẵn sàng phục vụ. Instance đang provisioning, booting, warming hoặc unhealthy có thể được tính trong một số trạng thái quản lý nhưng chưa đóng góp năng lực thực tế.

### Capacity theo số lượng và theo đơn vị tài nguyên

Có hai cách biểu diễn thường gặp:

- **Instance count:** số VM hoặc node.
- **Capacity unit:** đơn vị năng lực được gán cho từng instance, có thể dựa trên vCPU, memory hoặc trọng số tùy hệ thống.

Với nhóm máy dùng nhiều loại instance, 5 máy nhỏ không nhất thiết tương đương 5 máy lớn. Một số dịch vụ hỗ trợ weighted capacity để quy đổi loại máy thành đơn vị năng lực. Khi đó desired capacity có thể biểu diễn theo capacity unit thay vì số instance.

Cần đọc đúng cách dịch vụ autoscaling tính desired capacity, đặc biệt khi dùng mixed instance types, instance weights hoặc node pool không đồng nhất.

## 2. Phân biệt min, max và desired capacity

Ba giá trị có vai trò khác nhau:

| Giá trị | Ý nghĩa | Vai trò vận hành |
|---|---|---|
| Minimum capacity | Mức capacity thấp nhất nhóm được phép duy trì | Giữ năng lực nền và tránh scale in quá sâu |
| Maximum capacity | Mức capacity cao nhất nhóm được phép tạo | Giới hạn chi phí, quota và mức tiêu thụ tài nguyên |
| Desired capacity | Mức capacity mà nhóm đang được yêu cầu đạt tới | Mục tiêu hiện tại do người vận hành hoặc autoscaler đặt |

Ví dụ, một nhóm VM có:

- Minimum = 3 instance.
- Desired = 6 instance.
- Maximum = 12 instance.

Nhóm được phép dao động trong khoảng 3 đến 12 instance và hiện được yêu cầu duy trì 6 instance. Nếu tải tăng, policy có thể nâng desired lên 8 hoặc 10. Khi tải giảm, policy có thể hạ desired xuống nhưng không thấp hơn minimum.

### Desired không đồng nghĩa với healthy

Cần phân biệt thêm các trạng thái:

- **Desired:** số instance hoặc capacity mà hệ thống muốn có.
- **Current/actual:** số instance đã được tạo hoặc đang tồn tại.
- **Pending:** instance đang được cấp phát hoặc khởi động.
- **In service:** instance đã qua các bước quản lý cần thiết và được đưa vào nhóm phục vụ.
- **Healthy:** instance vượt qua health check theo policy.
- **Draining/terminating:** instance đang ngừng nhận công việc và chuẩn bị bị xóa.
- **Standby/warm:** instance được giữ sẵn nhưng chưa phục vụ traffic theo cách thông thường.

Ví dụ, desired là 8 nhưng chỉ có 6 instance healthy, 2 instance đang boot. Hệ thống chưa có đủ capacity phục vụ 8 instance. Dashboard chỉ hiển thị desired có thể khiến người vận hành đánh giá quá cao năng lực thực tế.

### Ràng buộc min và max

Thông thường, desired được yêu cầu nằm trong khoảng min và max. Nếu đặt desired thấp hơn min, dịch vụ có thể điều chỉnh lên min hoặc từ chối yêu cầu. Nếu đặt desired cao hơn max, dịch vụ có thể từ chối hoặc giới hạn theo quy tắc riêng.

Tên trường và hành vi chính xác tùy nền tảng. Hãy kiểm tra trạng thái sau khi cập nhật thay vì giả định API đã áp dụng giá trị mong muốn.

## 3. Minimum capacity: giữ năng lực nền

Minimum capacity là giới hạn dưới của nhóm máy. Khi tải giảm, autoscaler không được giảm nhóm thấp hơn mức này.

### Vì sao cần minimum?

Minimum thường được chọn để:

- Duy trì năng lực phục vụ tải nền.
- Giữ đủ replica cho tính sẵn sàng.
- Có năng lực dự phòng khi một instance lỗi.
- Tránh cold start hoặc bootstrap quá lâu.
- Duy trì cache nóng và kết nối đã được khởi tạo.
- Giữ đủ node cho các workload nền hoặc daemon cần thiết.
- Bảo đảm ứng dụng không phải scale từ zero nếu yêu cầu latency không cho phép.

### Minimum không bảo đảm tất cả instance đều khỏe

Nếu minimum là 3 nhưng 2 instance bị unhealthy, nhóm vẫn có thể thiếu capacity dù không được phép scale in thêm. Cần kết hợp health replacement, alarm, quota và kiểm tra số instance healthy.

Minimum là giới hạn quy mô, không phải cam kết về số máy luôn sẵn sàng. Cam kết đó còn phụ thuộc khả năng thay thế instance lỗi và capacity của vùng triển khai.

### Chọn minimum theo tải nền

Một cách tiếp cận:

1. Đo tải nền ở giờ thấp điểm và giờ thông thường.
2. Đo năng lực của một instance khi vẫn đáp ứng SLO.
3. Tính số instance cần cho tải nền.
4. Cộng phần dự phòng theo yêu cầu availability.
5. Kiểm tra minimum có đủ cho các workload bắt buộc và tác vụ vận hành không.

Nếu workload có tải biến động mạnh theo giờ, minimum có thể được đặt theo mức nền an toàn; lịch scaling hoặc target tracking sẽ điều chỉnh desired lên trước thời điểm cao điểm.

### Minimum và scale to zero

Một số workload batch hoặc event-driven có thể cho phép minimum bằng 0 để tiết kiệm chi phí. Điều này phù hợp khi có queue bền vững, không yêu cầu phản hồi ngay và chấp nhận thời gian khởi tạo.

Với API tương tác hoặc dịch vụ cần phản hồi nhanh, scale to zero có thể tạo cold start và latency cao. Cần cân nhắc warm pool, provisioned capacity hoặc minimum lớn hơn 0.

## 4. Maximum capacity: giới hạn tăng trưởng

Maximum capacity là giới hạn trên mà autoscaler không được vượt. Nó bảo vệ chi phí và các tài nguyên phụ thuộc khỏi tăng không kiểm soát.

### Các lý do cần đặt maximum

- Giới hạn ngân sách.
- Giới hạn quota vCPU, instance, GPU hoặc IP.
- Capacity thực tế của region/availability zone.
- Giới hạn database connection.
- Giới hạn API rate hoặc số consumer.
- Giới hạn license phần mềm.
- Giới hạn băng thông, NAT, storage hoặc load balancer.
- Giới hạn blast radius khi có lỗi hoặc scaling loop.

### Maximum quá thấp

Nếu max thấp hơn capacity cần thiết trong giờ cao điểm, autoscaler chạm trần nhưng hệ thống vẫn quá tải. Dấu hiệu:

- Desired bằng maximum trong thời gian dài.
- Queue và latency tiếp tục tăng.
- CPU, memory hoặc connection pool vẫn bão hòa.
- Request bị từ chối dù scaling policy đã kích hoạt.

Khi đó cần đánh giá lại max, quota, capacity region và dependency. Không chỉ tăng max nếu database hoặc network không thể chịu thêm tải.

### Maximum quá cao

Maximum lớn không tự động tạo ra capacity hữu ích. Nó có thể:

- Tăng chi phí khi scaling signal sai.
- Vượt giới hạn database connection.
- Gây cạn IP subnet hoặc NAT port.
- Tăng tải lên storage và message broker.
- Tạo nhiều instance trong một đợt retry hoặc traffic bất thường.
- Làm tăng thời gian rollout và lượng tài nguyên phải giám sát.

Maximum cần được kiểm tra bằng capacity test và dependency budget, không chỉ bằng giới hạn tối đa mà cloud provider cho phép.

### Maximum và quota

Trước khi nâng maximum, kiểm tra quota ở đúng scope: account/project/subscription, region, zone và loại tài nguyên. Quota vCPU tổng có thể bị chia sẻ giữa nhiều nhóm máy. Quota GPU, public IP, disk hoặc network interface có thể là giới hạn riêng.

Cần chừa quota cho:
- Instance replacement khi máy lỗi.
- Deployment surge hoặc rolling update.
- Disaster recovery.
- Nhóm máy khác trong cùng account/project.
- Tác vụ vận hành và môi trường staging nếu dùng chung quota.

## 5. Desired capacity: mục tiêu tại thời điểm hiện tại

Desired capacity là mục tiêu mà nhóm máy cần đạt ở thời điểm hiện tại. Nó có thể được thay đổi thủ công hoặc do autoscaling policy cập nhật.

### Ai điều chỉnh desired?

- Người vận hành đặt desired khi triển khai hoặc bảo trì.
- Target tracking thay đổi desired theo metric mục tiêu.
- Step scaling tăng/giảm desired theo các mức cảnh báo.
- Scheduled scaling đặt desired hoặc giới hạn vào thời điểm đã định.
- Orchestrator thay đổi replica count dựa trên policy.
- Deployment controller có thể tạm thời yêu cầu thêm capacity trong rollout.

Không nên để nhiều bộ điều khiển độc lập cùng ghi desired mà không có quy tắc phối hợp. Ví dụ, một script đặt desired cố định mỗi phút có thể liên tục ghi đè autoscaler.

### Desired có thể khác current trong một khoảng thời gian

Khi desired tăng, nền tảng cần cấp phát máy, boot OS, chạy bootstrap, đăng ký agent và chờ health check. Khi desired giảm, hệ thống cần drain connection, hoàn tất task và terminate instance.

Do đó:

\[
Desired\ Capacity \neq Healthy\ Capacity
\]

trong giai đoạn chuyển đổi hoặc khi có lỗi. Cần đo thời gian hội tụ từ lúc desired thay đổi đến khi healthy capacity đạt mục tiêu.

### Desired thủ công và autoscaling

Nếu autoscaler đang quản lý nhóm, thay đổi desired thủ công có thể chỉ là tạm thời. Policy có thể điều chỉnh lại ngay sau đó dựa trên metric.

Trước khi thay đổi thủ công, xác định:
- Policy nào đang điều khiển nhóm.
- Có scheduled action sắp chạy không.
- Có cooldown hoặc stabilization window không.
- Có deployment hoặc lifecycle hook đang hoạt động không.
- Desired hiện tại có bị một controller khác ghi đè không.

## 6. Tính capacity từ tải và SLO

Số instance nên được tính từ tải mà mỗi instance có thể xử lý khi vẫn đáp ứng SLO, thay vì dựa vào một tỷ lệ CPU chung cho mọi ứng dụng.

### Đo năng lực của một instance

Dùng load test hoặc dữ liệu production để xác định throughput an toàn của một instance:

- Tải tăng dần đến khi latency hoặc error rate chạm SLO.
- Ghi throughput tại thời điểm đó.
- Ghi CPU, memory, disk, network và dependency.
- Lặp lại ở cấu hình đại diện.
- Chọn mức capacity có headroom cho biến động.

Gọi **Q_safe** là throughput mỗi instance có thể duy trì trong điều kiện đã kiểm thử mà vẫn đáp ứng SLO.

Số instance cần thiết có thể ước lượng:

\[
N_{required} = \left\lceil \frac{D_{peak}}{Q_{safe}} \right\rceil
\]

Trong đó:
- \(D_{peak}\) là nhu cầu tải đỉnh dự kiến.
- \(Q_{safe}\) là throughput an toàn của một instance.

Nếu chỉ có số liệu throughput gần bão hòa \(Q_{sat}\), có thể dùng hệ số utilization mục tiêu \(U_{target}\):

\[
Q_{safe} = Q_{sat} \times U_{target}
\]

Không áp dụng hai cách nhân headroom cùng lúc nếu Q_safe đã được đo ở mức an toàn.

### Ví dụ sizing

Một API có tải đỉnh dự kiến 1.800 request/giây. Load test cho thấy một VM xử lý được 500 request/giây ở ngưỡng saturation, nhưng nhóm chọn mục tiêu sử dụng 65% để giữ headroom.

\[
Q_{safe} = 500 \times 0.65 = 325
\]

\[
N_{required} = \lceil 1800 / 325 \rceil = 6
\]

Nhóm cần tối thiểu 6 instance healthy để phục vụ tải đỉnh trong điều kiện đã kiểm thử. Đây là điểm sizing ban đầu; cần cộng thêm năng lực chịu lỗi theo yêu cầu availability.

### Không sizing theo CPU đơn lẻ

Một instance có thể còn CPU nhưng đã hết connection database, memory, network bandwidth hoặc IOPS. Năng lực của workload bị giới hạn bởi thành phần nghẽn trước tiên.

Có thể xem capacity hữu ích là giới hạn nhỏ nhất giữa các miền:

\[
C_{effective} = \min(C_{CPU}, C_{memory}, C_{storage}, C_{network}, C_{dependency})
\]

Đây là mô hình tư duy, không phải công thức đo trực tiếp. Mỗi thành phần cần đơn vị và phép đo riêng.

## 7. Headroom và dự phòng tài nguyên

Headroom là phần capacity còn dư so với nhu cầu hiện tại hoặc nhu cầu dự kiến. Nó giúp hệ thống hấp thụ burst, sự cố, rollout và thời gian chờ autoscaler bổ sung máy.

### Headroom vận hành

Nếu workload đang dùng 60% năng lực đã cấp, headroom theo tỷ lệ đơn giản còn 40%. Nhưng utilization của CPU không phản ánh toàn bộ headroom. Cần kiểm tra RAM, storage, network, queue và dependency.

Ví dụ:
- CPU còn 30% nhưng memory chỉ còn 2%: hệ thống thiếu headroom bộ nhớ.
- VM còn CPU/RAM nhưng DB pool đã hết connection: request vẫn phải chờ.
- Disk còn dung lượng nhưng IOPS chạm trần: workload vẫn chậm.
- Network throughput thấp nhưng NAT port cạn: kết nối mới vẫn thất bại.

### Headroom cho autoscaling lag

Autoscaling không bổ sung capacity tức thời. Thời gian hội tụ có thể gồm:

1. Metric phát hiện tải tăng.
2. Policy đánh giá và cập nhật desired.
3. Scheduler hoặc cloud provider tìm capacity.
4. Instance được tạo và boot.
5. Bootstrap cài cấu hình, agent và ứng dụng.
6. Cache/runtime warm-up.
7. Health check đạt và load balancer bắt đầu gửi traffic.

Trong khoảng này, tải phải được phục vụ bởi capacity hiện có. Minimum và warm capacity nên đủ để hấp thụ tải trong thời gian scale out.

### Headroom cho rolling deployment

Rolling update có thể tạo thêm instance tạm thời để thay máy cũ. Cần kiểm tra:
- Max surge hoặc batch size.
- Max unavailable.
- Desired/current trong lúc rollout.
- Quota và capacity còn lại.
- Database connection và network tăng tạm thời.
- Thời gian drain và health check.

Nếu maximum bằng đúng desired bình thường, deployment có thể không tạo được máy mới trước khi xóa máy cũ. Một số nền tảng có quy tắc rollout riêng; hãy tính surge vào quota và maximum phù hợp.

## 8. Dự phòng khi instance hoặc availability zone lỗi

### Dự phòng cấp instance

Nếu nhóm cần duy trì 6 instance healthy khi một instance bất kỳ lỗi, có thể cần capacity lớn hơn 6 để thay thế hoặc giữ một instance dự phòng. Số lượng dự phòng tùy thời gian thay thế và mức tải.

Ví dụ:
- Năng lực cần phục vụ: 6 instance.
- Một instance có thể lỗi bất kỳ lúc nào.
- Replacement mất 4 phút để boot và warm-up.
- Trong 4 phút đó, các instance còn lại phải tiếp tục đáp ứng SLO.

Có thể cần thêm một instance hoặc headroom tương đương để chịu lỗi. Không có một tỷ lệ dự phòng cố định phù hợp cho mọi hệ thống.

### Dự phòng theo availability zone

Phân bố instance qua nhiều AZ giúp giảm rủi ro lỗi một vùng. Tuy nhiên, số instance tổng phải đủ để phần còn lại phục vụ tải sau khi mất một AZ.

Nếu cần duy trì 6 instance tương đương sau khi mất một trong 3 AZ và capacity phân bố đều, cần:

\[
N_{total} \times \frac{2}{3} \geq 6
\]

\[
N_{total} \geq 9
\]

Ví dụ này giả định 3 AZ có capacity tương đương và phân bố đều. Nếu AZ không đồng nhất hoặc mỗi zone có quota khác nhau, cần tính theo capacity thực tế ở từng zone.

### Capacity không chỉ là instance count

Trong sự cố AZ, cần kiểm tra:
- Subnet/IP còn đủ cho các instance còn lại không.
- Quota vCPU có đủ ở zone dự phòng không.
- Instance family có capacity hay reservation không.
- Load balancer có health check và cross-zone routing đúng không.
- Storage có thể attach hoặc replicate ở zone còn lại không.
- Database và cache có đủ capacity sau failover không.

### On-demand, reserved và spot

- **On-demand:** linh hoạt theo nhu cầu nhưng vẫn phụ thuộc capacity vùng và quota.
- **Reserved/committed capacity:** có thể giảm chi phí hoặc bảo đảm một phần năng lực theo điều kiện dịch vụ.
- **Spot/preemptible:** chi phí thấp nhưng có thể bị thu hồi; không nên tính là capacity duy nhất cho workload quan trọng.
- **Capacity reservation:** có thể dành trước năng lực ở một phạm vi cụ thể tùy provider.

Một nhóm dùng spot nên có capacity nền đáng tin cậy và phân tán instance type/zone để giảm rủi ro mất nhiều máy cùng lúc.

## 9. Dự phòng cho dependency và connection pool

Scale out tăng số lượng instance nhưng cũng tăng tải lên các dịch vụ phía sau.

### Database connection

Nếu mỗi instance mở tối đa 20 connection và nhóm có 12 instance, số connection tiềm năng là:

\[
12 \times 20 = 240
\]

Con số này chưa gồm connection của admin, migration, monitoring và workload khác. Cần giới hạn tổng connection ở cấp hệ thống.

Khi tính maximum capacity, kiểm tra:
- Pool size mỗi instance.
- Số instance tối đa.
- Số pool trong mỗi process.
- Connection dành cho công việc nền.
- Giới hạn database và connection proxy.
- Thời gian query và concurrency thực tế.

### API và message broker

Nếu mỗi instance tạo 50 request đồng thời tới API ngoài, 12 instance có thể tạo 600 request in-flight. Cần kiểm tra quota, rate limit và giới hạn concurrency của dịch vụ đó.

Với message broker, số consumer có thể bị giới hạn bởi partition, throughput và thứ tự xử lý. Thêm instance không nhất thiết tăng throughput nếu số partition không đổi.

### Storage và network

Maximum instance count có thể làm tăng:
- IOPS và throughput tổng.
- Network egress và NAT connection.
- Số file share client.
- Số volume attach.
- Số IP hoặc network interface.

Capacity plan cần có budget cho các dependency này trước khi nâng max.

## 10. Warm capacity, warm pool và thời gian khởi động

Warm capacity là năng lực đã được chuẩn bị trước để có thể nhận tải nhanh hơn. Nó có thể gồm instance đang phục vụ với headroom, instance đã boot nhưng standby hoặc warm pool do nền tảng quản lý.

### Warm pool

Warm pool giữ sẵn các instance đã được khởi tạo một phần hoặc hoàn chỉnh để giảm thời gian từ lúc cần scale đến lúc máy sẵn sàng. Mức độ chuẩn bị có thể khác nhau:

- Stopped: image và disk đã có nhưng máy chưa chạy.
- Running/ready: OS đã boot, có thể cần warm-up ứng dụng.
- In-service: đang phục vụ traffic bình thường.

Tên trạng thái và chi phí phụ thuộc dịch vụ. Cần hiểu warm pool có được tính vào desired capacity hay không và có ảnh hưởng tới maximum hoặc quota như thế nào.

### Khi nên giữ warm capacity?

- Cold start hoặc bootstrap kéo dài.
- Workload có burst nhanh.
- SLO latency nghiêm ngặt.
- Image cần tải nhiều package.
- Ứng dụng cần warm cache hoặc JIT compilation.
- Region có capacity khan hiếm.

### Warm capacity có chi phí

Instance đang chạy hoặc được giữ ở trạng thái standby có thể phát sinh chi phí compute, disk và IP. So sánh chi phí giữ warm capacity với chi phí vi phạm SLO, queue backlog và thời gian phục hồi.

Không giữ warm pool quá lớn nếu tải nền thấp và cold start có thể chấp nhận.

## 11. Áp dụng trên instance group và VM scale set

Các cloud provider dùng tên gọi khác nhau nhưng thường có mô hình tương tự.

| Nền tảng | Dịch vụ | Các giới hạn thường gặp |
|---|---|---|
| AWS | EC2 Auto Scaling Group | Min size, desired capacity, max size; có thể dùng weighted capacity và warm pool |
| Microsoft Azure | Virtual Machine Scale Sets | Instance count/capacity, autoscale minimum/default/maximum theo profile |
| Google Cloud | Managed Instance Group | Minimum/maximum hoặc target size tùy chế độ autoscaler và loại MIG |

Cấu hình cụ thể phụ thuộc region, loại group, autoscaling mode và phiên bản API.

### Quy trình cấu hình

1. Xác định loại instance và capacity unit.
2. Đặt minimum theo tải nền và availability.
3. Đặt desired theo tải hiện tại hoặc baseline.
4. Đặt maximum theo peak forecast, quota và dependency budget.
5. Chọn distribution theo zone.
6. Cấu hình health check và replacement.
7. Xác định lifecycle hook, drain và warm-up.
8. Kiểm tra rolling deployment surge.
9. Kiểm tra quota và reservation.
10. Quan sát desired, current, pending và healthy capacity sau khi áp dụng.

### Weighted capacity

Nếu một group có nhiều loại VM, có thể dùng weight để quy đổi từng instance thành capacity unit. Ví dụ một máy lớn có weight 4, máy nhỏ có weight 1. Desired capacity 12 unit có thể được đáp ứng bằng tổ hợp instance khác nhau.

Cần kiểm tra:
- Weight có phản ánh throughput thực tế không.
- Tỷ lệ CPU/RAM có phù hợp workload không.
- Instance type thay thế có tương thích image/driver không.
- Capacity unit được autoscaler dùng nhất quán trong desired, max và metric không.

Không đặt weight chỉ dựa trên số vCPU nếu workload bị giới hạn bởi RAM, storage hoặc network.

## 12. Áp dụng trong Kubernetes

Kubernetes có nhiều lớp capacity:

- **Pod replicas:** số bản sao ứng dụng.
- **HPA:** thay đổi số replica trong minReplicas và maxReplicas.
- **VPA:** điều chỉnh CPU/memory request theo policy.
- **Node pool/managed node group:** giới hạn số node.
- **Cluster autoscaler:** tăng hoặc giảm node khi scheduler không thể xếp pod hoặc node dư.

### HPA min và max

Ví dụ HPA:

~~~yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: api-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: api
  minReplicas: 3
  maxReplicas: 20
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 65
~~~

Ví dụ này yêu cầu ít nhất 3 pod, cho phép tối đa 20 pod và dùng CPU utilization mục tiêu 65% tính theo request. Cần bảo đảm container có CPU request hợp lý; nếu request sai, phần trăm utilization có thể không phản ánh tải thực.

HPA thay đổi replica count, còn node autoscaler phải có khả năng cấp node để chứa pod. Nếu maxReplicas cao nhưng node pool max thấp, pod có thể ở trạng thái Pending.

### Node pool min/max

Node pool có giới hạn riêng. Tổng capacity cluster phải tính:
- Node count min/max.
- CPU/RAM allocatable sau khi trừ system reserved.
- Pod density và giới hạn IP.
- DaemonSet overhead.
- Topology/zone và storage locality.
- Quota và capacity của VM instance type.

### Desired replicas và healthy pods

Deployment có thể mong muốn 10 replica nhưng chỉ có 7 pod Ready. Cần xem desired/current/ready/available, pod Pending, CrashLoopBackOff và node capacity.

Replica count không phải năng lực phục vụ nếu pod chưa Ready hoặc bị throttling. Hãy theo dõi request latency, queue, CPU throttling và dependency pool.

## 13. Serverless và giới hạn concurrency

Serverless thường dùng các giới hạn tương đương min/max/desired dưới dạng concurrency, reserved capacity hoặc provisioned capacity.

Các khái niệm có thể gồm:
- Reserved concurrency: giới hạn concurrency dành riêng hoặc giới hạn tối đa theo cấu hình.
- Provisioned concurrency: giữ sẵn execution environment để giảm cold start trên một số nền tảng.
- Maximum instances/concurrency: giới hạn số execution environment hoặc request đồng thời.
- Queue backlog: lượng công việc đang chờ function xử lý.

Nếu function scale nhanh, downstream có thể bị quá tải. Cần giới hạn concurrency ở function và bảo vệ database/API bằng pooler, semaphore, queue hoặc rate limit.

Không giả định mọi nền tảng serverless có min/max giống instance group. Kiểm tra semantics của dịch vụ và runtime cụ thể.

## 14. Chi phí và ngân sách capacity

Minimum, desired và maximum tạo ra đường chi phí khác nhau.

- Minimum quyết định chi phí nền tối thiểu.
- Desired phản ánh chi phí gần với trạng thái hiện tại.
- Maximum là trần quy mô có thể đạt tới, không phải chi phí mặc định.
- Warm pool có thể tạo chi phí ngay cả khi chưa phục vụ traffic.
- Deployment surge có thể tăng chi phí tạm thời.
- Cross-zone traffic, disk, IP, NAT và license có thể tăng theo số instance.

### Ước lượng chi phí

Một mô hình đơn giản:

\[
Cost \approx \sum_{i=1}^{n} InstanceHours_i \times HourlyRate_i
+ Storage + Network + OtherServices
\]

Với instance có nhiều loại, tính riêng từng loại và thời gian chạy. Cộng thêm chi phí warm pool, snapshot, log, load balancer và dependency.

### Tối ưu minimum mà vẫn giữ SLO

Có thể giảm minimum khi:
- Tải nền thấp và dự báo được.
- Thời gian scale out đủ nhanh.
- Queue có thể hấp thụ burst.
- Workload chấp nhận cold start.
- Có thể scale to zero hoặc dùng warm pool nhỏ.

Không nên giảm minimum nếu:
- Dịch vụ có latency SLO nghiêm ngặt.
- Một AZ hoặc instance failure sẽ làm thiếu capacity.
- Bootstrap kéo dài.
- Workload có kết nối dài hoặc cache lớn.
- Dependency không chịu được spike khi nhiều instance mới cùng khởi động.

### Budget guardrail

Có thể dùng budget alert hoặc policy để phát hiện chi phí tăng bất thường. Nhưng không nên tự động hạ desired xuống dưới mức an toàn chỉ vì budget alert, nếu điều đó gây gián đoạn dịch vụ. Cần có policy riêng cho overload, cost control và SLO.

## 15. Quy trình tính min, desired và max

Một quy trình sizing thực tế:

1. **Xác định SLO:** throughput, latency, error rate và availability cần đáp ứng.
2. **Đo capacity mỗi instance:** load test với cấu hình và dependency gần production.
3. **Dự báo tải:** baseline, peak, burst, mùa vụ và tốc độ tăng trưởng.
4. **Tính capacity cần thiết:** dùng throughput an toàn mỗi instance, không chỉ CPU trung bình.
5. **Chọn minimum:** đủ phục vụ tải nền, warm-up và yêu cầu availability.
6. **Chọn desired:** phù hợp tải hiện tại hoặc baseline ban đầu.
7. **Chọn maximum:** đủ cho peak và surge, nhưng không vượt quota hoặc dependency budget.
8. **Tính AZ failure:** xác minh phần capacity còn lại khi mất một zone.
9. **Tính dependency:** database connection, API quota, storage, IP và network.
10. **Kiểm tra scale lag:** thời gian phát hiện, cấp máy, bootstrap và readiness.
11. **Kiểm tra cost:** chi phí min, desired, max và warm pool.
12. **Thử nghiệm:** load, stress, spike và failover test.
13. **Triển khai canary:** áp dụng cho nhóm nhỏ rồi mở rộng.
14. **Rà soát định kỳ:** cập nhật theo tăng trưởng, thay đổi image và SLO.

### Ví dụ cấu hình minh họa

Một nhóm API có tải nền cần 3 instance, tải cao điểm cần 6 instance theo capacity test. Nhóm muốn chịu được một instance lỗi trong giờ bình thường và cho phép tăng tới 10 instance khi có burst.

Có thể bắt đầu với:

| Thuộc tính | Giá trị minh họa | Lý do |
|---|---:|---|
| Minimum | 4 | Tải nền 3 instance và 1 instance dự phòng |
| Desired | 4 | Khởi động ở mức baseline an toàn |
| Maximum | 10 | Có thể đáp ứng peak và một phần burst theo quota/dependency |
| Warm capacity | 1 | Giảm thời gian phản ứng khi cần scale |
| AZ | 3 | Phân bố để giảm rủi ro một zone |

Cấu hình này chỉ là điểm bắt đầu. Nếu yêu cầu giữ đủ 6 instance phục vụ sau khi mất một AZ, phải tính lại tổng capacity theo phân bố zone, thay vì chỉ dựa trên minimum 4.

## 16. Giám sát capacity và cảnh báo

Cần theo dõi các metric:

| Nhóm | Metric | Câu hỏi |
|---|---|---|
| Group | Min, desired, max | Nhóm đang bị giới hạn ở đâu? |
| Instance | Current, pending, in-service, healthy | Có đủ máy sẵn sàng không? |
| Scaling | Scale event, cooldown, warm-up duration | Autoscaler có phản ứng đúng không? |
| Workload | Request rate, queue, p95/p99, errors | Capacity hiện tại có đáp ứng SLO không? |
| Compute | CPU, memory, throttling | Nút thắt có ở tài nguyên máy không? |
| Dependency | DB connections, API rate, broker lag | Scale out có làm downstream quá tải không? |
| Quota | vCPU, instance, IP, GPU, storage | Có thể cấp thêm máy khi cần không? |
| Cost | Instance hours, warm pool, network, disk | Capacity đang tiêu thụ bao nhiêu ngân sách? |

### Cảnh báo nên có

- Desired chạm maximum trong thời gian kéo dài.
- Healthy capacity thấp hơn desired.
- Pending instance quá lâu.
- Scale event thất bại do quota hoặc capacity.
- CPU/memory hoặc queue vượt SLO trong khi nhóm đã chạm max.
- Minimum không đủ sau khi một AZ hoặc instance bị lỗi.
- Database connection hoặc API quota tiến gần giới hạn.
- Warm pool không đủ hoặc bootstrap duration tăng.
- Chi phí tăng bất thường so với tải.

Không cảnh báo chỉ vì desired khác current trong vài giây. Cần xét thời gian hội tụ và ngưỡng phù hợp với thời gian khởi tạo.

## 17. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Desired tăng nhưng healthy không tăng | Quota, capacity zone, image lỗi hoặc bootstrap thất bại | Kiểm tra scaling activity, provisioning event, quota và bootstrap log |
| Desired luôn bằng max | Tải cao, target quá thấp hoặc max quá thấp | Xem SLO, capacity test, dependency và ngân sách trước khi nâng max |
| Scale in làm lỗi request | Minimum quá thấp hoặc drain không hoàn tất | Tăng min, cấu hình lifecycle/drain và kiểm tra termination policy |
| Nhiều instance mới nhưng throughput không tăng | DB, broker, storage hoặc API đã bão hòa | Giới hạn concurrency, tối ưu dependency hoặc tăng capacity phía sau |
| Pod Pending dù HPA đã tăng replicas | Node pool max, quota hoặc resource request quá lớn | Kiểm tra scheduler events, allocatable và node autoscaler |
| Autoscaling phản ứng chậm | Bootstrap, image pull, warm-up hoặc metric delay | Dùng warm capacity, image tối ưu và signal sớm hơn |
| Chi phí tăng đột biến | Scaling loop, metric sai, retry storm hoặc max quá cao | Kiểm tra policy, cooldown, alarm và dependency |
| Mất AZ khiến SLO không đạt | Capacity phân bố không đủ ở các zone còn lại | Tính lại N-1 zone capacity và quota dự phòng |
| Scale out gây database timeout | Tổng connection vượt giới hạn | Tính pool toàn hệ thống, dùng proxy/pooler và giới hạn concurrency |

### Quy trình điều tra

1. So sánh min, desired, max và current.
2. Xem số instance healthy, pending và draining.
3. Kiểm tra scaling activity hoặc event gần nhất.
4. Kiểm tra quota và capacity theo region/zone.
5. Đọc bootstrap, health check và load balancer state.
6. Đối chiếu request rate, queue, latency và error.
7. Kiểm tra database, broker, network và storage.
8. Xác định bottleneck trước khi nâng max hoặc tăng desired.
9. Thử thay đổi trong staging/canary.
10. Theo dõi SLO và chi phí sau thay đổi.

## 18. Checklist trước khi đưa capacity bounds vào production

- [ ] Đã phân biệt minimum, maximum và desired capacity.
- [ ] Đã phân biệt desired với current, healthy và available capacity.
- [ ] Đã xác định capacity theo instance count hay weighted units.
- [ ] Đã đo throughput an toàn mỗi instance bằng tải thử.
- [ ] Đã tính minimum theo tải nền và yêu cầu availability.
- [ ] Đã tính maximum theo peak, burst và deployment surge.
- [ ] Đã kiểm tra quota, reservation và capacity từng zone.
- [ ] Đã tính N-1 instance hoặc AZ failure theo yêu cầu.
- [ ] Đã tính database connection và dependency budget ở cấp toàn hệ thống.
- [ ] Đã xác định headroom cho autoscaling lag và warm-up.
- [ ] Đã cấu hình health check, replacement và graceful drain.
- [ ] Đã xem xét warm pool hoặc provisioned capacity khi cần.
- [ ] Đã kiểm tra rolling deployment và lifecycle hook.
- [ ] Đã theo dõi desired/current/healthy/pending.
- [ ] Đã tạo cảnh báo khi chạm max hoặc healthy capacity thiếu.
- [ ] Đã tính chi phí ở mức min, desired, max và warm pool.
- [ ] Đã thử load, spike, failover và scale-in.
- [ ] Có kế hoạch rollback và cập nhật capacity theo tăng trưởng.

## Kết luận

Minimum giữ năng lực nền, maximum giới hạn quy mô và desired thể hiện mục tiêu capacity hiện tại. Ba giá trị này chỉ có ý nghĩa khi được tính theo throughput an toàn, SLO, thời gian scale out, availability zone, quota và giới hạn dependency. Capacity thực tế phải tính cả instance healthy, không chỉ số máy được yêu cầu. Dự phòng CPU, RAM, storage, network, database connection và thời gian bootstrap giúp hệ thống chịu được burst và sự cố. Khi theo dõi desired/current/healthy, scaling activity, queue, SLO và chi phí, đội vận hành có thể đặt min/max hợp lý, duy trì headroom và tránh autoscaling tạo ra tải vượt khả năng của toàn hệ thống.

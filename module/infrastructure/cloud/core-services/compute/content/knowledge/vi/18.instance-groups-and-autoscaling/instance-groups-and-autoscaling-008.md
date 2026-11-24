# Phân phối capacity giữa nhiều zone và nhiều loại máy

Một instance group hoặc nhóm máy tự động co giãn thường cần chạy nhiều máy ảo để phục vụ tải, chịu lỗi và thay thế máy khi bảo trì. Khi nhóm trải trên nhiều availability zone (AZ) và dùng nhiều loại instance, bài toán không còn đơn giản là giữ một số lượng máy cố định. Hệ thống phải bảo đảm mỗi zone có đủ capacity, chọn được loại máy phù hợp khi một loại hết chỗ, đồng thời giữ tổng chi phí và hiệu năng trong mục tiêu.

Phân phối capacity tốt cần phối hợp ba quyết định: **đặt bao nhiêu capacity ở mỗi zone**, **cho phép dùng những loại máy nào** và **giữ bao nhiêu capacity dự phòng khi một zone hoặc một loại máy gặp sự cố**. Các quyết định này ảnh hưởng lẫn nhau. Một nhóm có thể đủ tổng vCPU nhưng vẫn thiếu RAM ở một zone; hoặc có đủ instance count nhưng không đủ năng lực xử lý khi loại máy nhỏ được thay cho loại máy lớn.

## 1. Capacity là gì trong một instance group?

Capacity là năng lực compute mà nhóm máy có thể cung cấp cho workload. Với nhóm chỉ dùng một loại instance, người vận hành thường biểu diễn capacity bằng số máy. Khi nhóm dùng nhiều loại máy, số lượng instance không còn phản ánh chính xác năng lực.

Ví dụ, hai máy 2 vCPU và một máy 8 vCPU đều được tính là một instance, nhưng năng lực CPU khác nhau. RAM, network throughput, IOPS, GPU và giới hạn packet-per-second cũng có thể khác. Vì vậy, cần chọn một đơn vị capacity phù hợp với workload.

Một số cách biểu diễn thường dùng:

- **Instance count:** số máy ảo đang chạy. Phù hợp khi mọi máy cùng loại hoặc có năng lực gần tương đương.
- **vCPU capacity:** tổng số vCPU được cấp. Có ích với workload CPU-bound, nhưng không phản ánh đầy đủ hiệu năng giữa các thế hệ CPU.
- **Memory capacity:** tổng RAM. Cần thiết với workload memory-bound, nhưng tổng RAM không bảo đảm một tác vụ có thể chạy trên máy bất kỳ nếu nó cần một lượng RAM tối thiểu trên từng node.
- **Weighted capacity units:** mỗi loại máy được gán trọng số đại diện cho năng lực tương đối. Instance lớn có thể đóng góp nhiều đơn vị hơn instance nhỏ.
- **Application capacity:** năng lực đo được như request/giây, worker concurrency, job/giờ hoặc số phiên đồng thời. Đây thường là thước đo gần với mục tiêu dịch vụ nhất nếu benchmark đáng tin cậy.

Không có một chỉ số duy nhất đại diện cho mọi workload. Nếu ứng dụng bị giới hạn bởi RAM, gán weight chỉ theo vCPU có thể khiến nhóm thay máy bằng cấu hình không đủ bộ nhớ. Nếu ứng dụng cần GPU hoặc local NVMe, một máy không có loại tài nguyên đó không thể được coi là thay thế tương đương chỉ vì tổng vCPU bằng nhau.

## 2. Phân biệt region, availability zone và fault domain

Region là khu vực địa lý gồm một hoặc nhiều zone. Availability zone là miền hạ tầng được thiết kế để giảm ảnh hưởng chung của một số sự cố so với zone khác trong cùng region. Tên gọi, phạm vi độc lập và cách ánh xạ zone có thể khác nhau giữa nhà cung cấp cloud.

Một nhóm máy chạy ở nhiều zone có thể tiếp tục phục vụ khi một zone bị gián đoạn, nếu workload và dependency cũng có thiết kế chịu lỗi tương ứng. Phân phối máy qua nhiều zone giúp giảm rủi ro tập trung, nhưng tự nó không bảo đảm tính sẵn sàng cao.

| Phạm vi | Vai trò trong thiết kế |
|---|---|
| Region | Xác định khu vực triển khai, độ trễ địa lý, residency và phạm vi dịch vụ |
| Availability zone | Phân tán máy qua các miền lỗi trong cùng region |
| Subnet/zone network | Cung cấp địa chỉ, route và chính sách mạng cho máy trong zone |
| Instance type | Xác định cấu hình CPU, RAM, network, storage và accelerator của từng máy |
| Instance group | Quản lý số lượng/capacity, thay thế và co giãn nhóm máy |

Một số dịch vụ có regional group cho phép chọn nhiều zone; một số dịch vụ yêu cầu tạo nhóm theo zone hoặc regional managed group có cách phân phối riêng. Trước khi thiết kế, xác minh phạm vi tài nguyên, giới hạn và thuật ngữ của nhà cung cấp đang dùng.

## 3. Phân phối đều giữa các zone

Một chiến lược phổ biến là phân phối capacity tương đối đều giữa các zone đang hoạt động. Nếu một nhóm có 300 đơn vị capacity và chạy trên ba zone, mục tiêu bình thường có thể là khoảng 100 đơn vị mỗi zone.

Lợi ích của phân phối đều:

- Giảm phụ thuộc vào một zone.
- Tạo capacity tương đối đồng đều cho load balancer phân phối request.
- Dễ so sánh mức sử dụng và phát hiện zone mất cân bằng.
- Có thể tiếp tục phục vụ khi một zone bị lỗi nếu phần còn lại đủ capacity.

Tuy nhiên, phân phối đều số instance không nhất thiết là phân phối đều capacity khi các máy có kích thước khác nhau. Nếu zone A có hai máy 8 vCPU còn zone B có hai máy 4 vCPU, số máy bằng nhau nhưng năng lực CPU không bằng nhau. Với mixed instance group, nên theo dõi cả instance count lẫn capacity unit và tài nguyên thực tế.

Một số dịch vụ tự cân bằng số máy giữa zone sau khi nhóm thay đổi; dịch vụ khác chỉ cố gắng phân bổ best-effort hoặc cần bật tùy chọn cân bằng. Việc một zone thiếu capacity có thể khiến nhóm tạm thời mất cân bằng. Không nên coi trạng thái “zone balanced” là bảo đảm mọi zone có cùng số instance tại mọi thời điểm.

## 4. Tính capacity cần thiết khi mất một zone

Khi thiết kế multi-zone, cần tính trường hợp một zone không còn phục vụ được. Nếu tổng nhu cầu peak là `D` và nhóm phân phối đều qua `N` zone, mỗi zone bình thường mang khoảng `D/N`. Khi một zone mất, các zone còn lại phải gánh toàn bộ `D`.

Nếu chia đều lại cho `N-1` zone còn sống, mỗi zone cần năng lực khoảng:

\[
C_{zone,failover} = \frac{D}{N-1}
\]

So với mức bình thường `D/N`, hệ số tăng tải trên mỗi zone còn sống là:

\[
F = \frac{N}{N-1}
\]

Với ba zone, hệ số này là `3/2 = 1,5`. Nghĩa là mỗi zone còn sống cần có thể phục vụ tải cao hơn 50% so với mức bình thường nếu phân phối đều.

Ví dụ, hệ thống cần 300 capacity units ở peak và chạy ba zone:

| Trạng thái | Zone A | Zone B | Zone C | Tổng capacity cần dùng |
|---|---:|---:|---:|---:|
| Bình thường | 100 | 100 | 100 | 300 |
| Mất zone A | 0 | 150 | 150 | 300 |
| Mất zone B | 150 | 0 | 150 | 300 |
| Mất zone C | 150 | 150 | 0 | 300 |

Trong ví dụ này, mỗi zone cần có khả năng cung cấp 150 units khi hai zone còn lại phải gánh peak. Có thể đạt điều đó bằng cách duy trì spare capacity, cho phép autoscaling nhanh và bảo đảm quota/capacity pool đủ lớn, hoặc kết hợp các cách trên.

Autoscaling sau khi zone hỏng chỉ giúp nếu capacity còn có thể được cấp phát kịp thời. Khi region đang thiếu máy hoặc quota bị chạm, scale-out có thể không hoàn tất. Với workload quan trọng, nên có headroom sẵn trong các zone còn lại hoặc capacity reservation phù hợp. Headroom cần được tính theo thời gian khởi động máy, bootstrap ứng dụng, warm-up và thời gian chuyển traffic.

## 5. Phân phối theo nhu cầu, không chỉ theo tỷ lệ cố định

Phân phối đều là điểm bắt đầu tốt, nhưng có workload cần placement khác nhau:

- Workload có dữ liệu local hoặc cache lớn có thể ưu tiên đặt gần nguồn dữ liệu.
- Workload có latency nhạy cảm có thể cần phân bố theo vùng người dùng hoặc dependency.
- Workload batch có thể tận dụng zone đang có capacity và chi phí phù hợp.
- Workload có yêu cầu license hoặc thiết bị đặc thù có thể bị giới hạn ở một số zone.
- Workload cần anti-affinity có thể yêu cầu các replica không cùng nằm trên một miền lỗi.

Nếu cố cân bằng đều mà bỏ qua dữ liệu và dependency, traffic liên zone có thể tăng độ trễ và chi phí. Nếu đặt quá nhiều máy ở zone thuận tiện nhất, khả năng chịu lỗi giảm. Cần xác định mục tiêu ưu tiên: availability, latency, throughput, data locality hay cost; sau đó kiểm thử trade-off.

## 6. Dùng nhiều loại instance trong cùng nhóm

Mixed instance group cho phép một nhóm dùng nhiều loại máy thay thế được về mặt workload. Điều này giúp tăng khả năng tìm được capacity khi một loại instance hoặc một zone đang thiếu nguồn cung, đồng thời có thể tối ưu chi phí.

Các loại máy nên được chọn dựa trên:

- Số vCPU và hiệu năng CPU đo được.
- RAM và giới hạn bộ nhớ của một instance.
- Network bandwidth, PPS và giới hạn kết nối.
- Loại storage, IOPS, throughput và khả năng dùng local/ephemeral disk.
- GPU hoặc accelerator nếu workload cần.
- Kiến trúc CPU như x86-64 hoặc Arm và tính tương thích của binary/runtime.
- Khả năng hỗ trợ ở từng zone và quota của tài khoản.
- Giá on-demand, giá theo cam kết và giá Spot/preemptible nếu sử dụng.

Không nên đưa mọi loại máy có tên gần giống vào một nhóm. Hai instance có cùng số vCPU có thể khác đáng kể về thế hệ CPU, RAM, network, local storage hoặc mức hiệu năng ổn định. Tạo một danh sách instance types tương thích đã benchmark, sau đó kiểm tra khả năng cung cấp ở từng zone.

## 7. Chọn nhóm loại máy tương đương

Một danh sách mixed instance nên gồm các loại máy có thể chạy cùng workload mà không cần thay đổi logic ứng dụng. Có thể tổ chức theo nhóm năng lực:

| Workload | Nhóm loại máy có thể cân nhắc | Tiêu chí tương đương cần xác minh |
|---|---|---|
| CPU-bound API | Compute-optimized cùng kiến trúc hoặc các thế hệ đã benchmark | CPU throughput, clock behavior, network và memory đủ |
| Memory-bound cache | Memory-optimized với RAM/instance phù hợp | RAM mỗi node, memory bandwidth, network và giới hạn kết nối |
| General-purpose service | General-purpose cùng dải tỷ lệ CPU/RAM | Cân bằng CPU, RAM, network và giá trên mỗi đơn vị workload |
| Batch xử lý độc lập | Nhiều cỡ máy tương thích | Throughput/job, thời gian hoàn tất và chi phí mỗi job |
| GPU workload | Các loại GPU được ứng dụng và driver hỗ trợ | GPU model/count, VRAM, driver, framework và topology |
| Storage-intensive | Loại máy có IOPS/throughput phù hợp | Loại volume, local NVMe, durability và dữ liệu có thể tái tạo |

Kiến trúc CPU là ràng buộc quan trọng. Binary native được biên dịch cho x86-64 không thể mặc định chạy trên Arm. Java bytecode thường portable hơn, nhưng JNI, native library, agent, driver và container image vẫn phải hỗ trợ kiến trúc đích. Với GPU, driver và phiên bản framework cần tương thích với từng loại instance.

Nên tránh một danh sách chỉ có một family hoặc một size. Đa dạng family, thế hệ và size có thể tăng lựa chọn capacity, nhưng đa dạng quá mức làm phức tạp kiểm thử, image, driver và sizing. Chọn tập nhỏ các loại máy đã xác minh trước khi mở rộng.

## 8. Weighted capacity cho các instance khác kích thước

Khi dùng instance types khác nhau, có thể gán mỗi loại một capacity weight. Nhóm quản lý desired capacity theo đơn vị thay vì chỉ đếm số máy. Ví dụ minh họa:

| Loại máy | vCPU | RAM | Capacity weight ví dụ |
|---|---:|---:|---:|
| Small | 2 | 8 GiB | 2 |
| Medium | 4 | 16 GiB | 4 |
| Large | 8 | 32 GiB | 8 |

Nếu desired capacity là 40 units, nhóm có thể chạy 10 máy Medium hoặc 5 máy Large, hoặc một tổ hợp tương đương theo weight. Các con số chỉ minh họa cách biểu diễn; weight thực tế phải dựa trên benchmark và đặc tính workload.

Weight theo vCPU chỉ phù hợp khi CPU là tài nguyên chi phối và RAM/network trên mỗi loại máy vẫn đáp ứng yêu cầu. Với workload cần tối thiểu 12 GiB RAM cho mỗi worker, Small trong ví dụ trên không phải lựa chọn thay thế hợp lệ dù có thể cộng dồn tổng RAM của nhiều máy.

Một nguyên tắc thực tế:

- Xác định giới hạn tối thiểu trên từng instance trước, ví dụ RAM tối thiểu, GPU memory, local disk hoặc network.
- Loại bỏ loại máy không đáp ứng điều kiện tối thiểu.
- Benchmark thông lượng thực tế và dùng kết quả đó để gán weight.
- Kiểm tra cách instance group làm tròn desired capacity khi một máy có weight lớn hơn phần capacity còn thiếu.
- Xác nhận scale-in và thay thế máy không làm nhóm vượt hoặc thiếu capacity ngoài mức chấp nhận.

Không dùng weighted capacity để che giấu khác biệt về khả năng chạy workload. Nếu một instance type chỉ phục vụ được một phần chức năng, hãy tách thành nhóm riêng hoặc dùng scheduling policy có ràng buộc rõ ràng.

## 9. Chiến lược chọn instance khi cần cấp phát

Khi một nhóm có nhiều loại máy, hệ thống cần chiến lược quyết định loại nào được yêu cầu trước. Một số chiến lược phổ biến về mặt khái niệm:

- **Ưu tiên chi phí thấp:** chọn loại có giá thấp nhất trong danh sách tương thích.
- **Ưu tiên capacity availability:** chọn loại có khả năng được cấp phát cao hơn trong zone hiện tại.
- **Ưu tiên đa dạng:** phân tán yêu cầu qua nhiều loại máy để giảm phụ thuộc một pool capacity.
- **Ưu tiên hiệu năng:** chọn loại có throughput hoặc latency tốt nhất theo benchmark.
- **Ưu tiên cân bằng:** phối hợp giá, khả năng cấp phát và năng lực xử lý.

Tên và thuật toán chính xác khác nhau theo cloud provider. Một số dịch vụ hỗ trợ capacity-optimized allocation cho Spot, diversified allocation hoặc lowest-price; một số dịch vụ có policy riêng cho regional managed group. Hãy xác định strategy có áp dụng cho On-Demand, Spot hay cả hai và cách nó xử lý khi loại máy không thể cấp phát.

Đối với workload production, không nên chọn loại rẻ nhất nếu nó có tỷ lệ interruption cao hoặc không đáp ứng SLO. Chi phí cần tính cả thời gian chạy lại job, mất cache, khởi động lại, lưu lượng chuyển vùng và công sức vận hành.

## 10. Kết hợp On-Demand, Spot và capacity reservation

Nhiều nhóm máy có thể kết hợp các mô hình mua capacity:

- **On-Demand:** phù hợp với phần tải nền cần tính sẵn sàng và thời gian chạy ổn định.
- **Spot/preemptible:** tận dụng capacity dư với giá thấp hơn, nhưng có thể bị thu hồi theo điều kiện của nhà cung cấp và thời gian cảnh báo giới hạn.
- **Capacity reservation:** giữ trước capacity trong phạm vi zone/loại máy hoặc theo cơ chế dịch vụ hỗ trợ, giúp giảm rủi ro không cấp phát được khi cần.
- **Savings/commitment plan:** giảm chi phí cho mức sử dụng cam kết, nhưng không nhất thiết bảo đảm capacity vật lý trừ khi sản phẩm nói rõ.

Một chiến lược thường gặp là giữ phần baseline bằng On-Demand hoặc capacity đã đặt trước, dùng Spot cho phần tải có thể gián đoạn. Worker xử lý batch stateless, có checkpoint và retry thường phù hợp hơn ứng dụng stateful giữ session trong RAM.

Không đặt toàn bộ capacity tối thiểu của dịch vụ quan trọng lên Spot nếu workload không thể chịu interruption. Cũng không giả định capacity reservation của một loại máy ở một zone có thể dùng thay cho loại khác hoặc zone khác; phạm vi reservation phụ thuộc sản phẩm.

## 11. Thiết kế autoscaling với nhiều zone và loại máy

Autoscaling quyết định khi nào tăng hoặc giảm capacity. Khi nhóm dùng nhiều zone và instance types, cần xác định rõ đơn vị scaling và cách tính desired capacity.

Các thành phần cơ bản:

- **Minimum capacity:** mức tối thiểu cần giữ để đáp ứng tải nền và yêu cầu availability.
- **Desired capacity:** mục tiêu hiện tại của nhóm, tính theo instance count hoặc weighted units.
- **Maximum capacity:** giới hạn trên do quota, ngân sách và capacity hạ tầng.
- **Scaling metric:** CPU, request count per target, queue depth, latency hoặc metric nghiệp vụ.
- **Cooldown/warm-up:** thời gian để instance mới boot, bootstrap và bắt đầu phục vụ.
- **Scale-in policy:** cách chọn instance bị loại khi giảm capacity.

Khi scale-out, nhóm có thể phân phối máy mới qua các zone và chọn instance type có sẵn. Khi scale-in, cần giữ phân bố zone và capacity đủ cho trường hợp lỗi. Nếu thuật toán scale-in chỉ loại máy rẻ nhất hoặc mới nhất mà không xét zone, nhóm có thể vô tình mất dự phòng ở một zone.

Metric trung bình toàn nhóm có thể che giấu mất cân bằng. Ví dụ, CPU trung bình là 50% nhưng một zone có 90% và zone khác 10%. Nên theo dõi metric theo zone, loại máy và instance, đồng thời kiểm tra request distribution từ load balancer.

## 12. Bảo đảm capacity khi một zone hoặc instance type không cấp phát được

Capacity cloud không phải lúc nào cũng sẵn có vô hạn. Một zone có thể tạm thời không cấp được một instance type, dù cùng loại đó vẫn có ở zone khác. Quota cũng có thể giới hạn tổng vCPU, GPU, địa chỉ IP hoặc số instance.

Để giảm rủi ro:

1. Chọn nhiều instance types tương thích, không phụ thuộc một size duy nhất.
2. Chọn nhiều zone trong cùng region nếu kiến trúc cho phép.
3. Kiểm tra quota cho từng họ máy, vCPU, GPU, Spot và địa chỉ mạng.
4. Dùng capacity reservation cho phần tải nền quan trọng khi cần bảo đảm cấp phát.
5. Có retry/backoff cho lỗi cấp phát tạm thời, nhưng tránh retry dồn dập.
6. Đặt cảnh báo khi desired capacity cao hơn actual capacity trong thời gian vượt ngưỡng.
7. Kiểm thử tình huống một zone hoặc một family không thể cấp máy.

Nếu tất cả loại máy trong danh sách đều hết capacity ở một zone, autoscaling không thể tạo ra máy mới tại zone đó. Hệ thống có thể phân bổ sang zone khác nếu dịch vụ hỗ trợ và subnet, quota, storage cùng dependency cho phép. Hãy kiểm tra hành vi thực tế khi một zone bị loại khỏi tập placement.

## 13. Tránh phân phối lệch khi dùng nhiều loại máy

Có thể xảy ra mất cân bằng theo hai chiều:

- **Lệch theo zone:** một zone có nhiều capacity hơn vì zone khác không cấp được máy hoặc nhóm chưa hoàn tất rebalancing.
- **Lệch theo instance type:** một loại máy chiếm phần lớn vì strategy ưu tiên nó, khiến workload phụ thuộc vào một pool capacity hoặc đặc tính hiệu năng.

Các biện pháp kiểm soát:

- Theo dõi instance count và weighted capacity theo từng zone/family.
- Giới hạn tỷ lệ tối đa của một loại máy nếu cần đa dạng hóa.
- Đặt danh sách loại máy theo nhóm tương đương đã benchmark.
- Kiểm tra capacity sau mỗi lần scale và sau sự kiện interruption.
- Dùng rebalancing hoặc replace policy theo tính năng của dịch vụ.
- Đảm bảo load balancer chỉ gửi traffic tới instance healthy và có readiness.

Không nên ép tỷ lệ máy theo family quá cứng nếu điều đó làm nhóm không thể cấp đủ capacity trong sự cố. Cần cân bằng giữa diversity mong muốn và khả năng cấp phát thực tế.

## 14. Rebalancing và thay thế instance

Rebalancing là quá trình đưa nhóm trở lại phân bố mong muốn sau khi một zone hoặc instance type thay đổi. Một dịch vụ có thể khởi tạo máy mới trước rồi mới terminate máy cũ, hoặc dùng quy trình khác tùy chính sách và giới hạn capacity.

Khi rebalancing, cần chú ý:

- **Surge capacity:** có đủ quota và giới hạn maximum để tạo máy mới trước khi xóa máy cũ không?
- **Connection draining:** load balancer đã ngừng gửi request mới và chờ request hiện tại hoàn tất chưa?
- **Stateful data:** dữ liệu có nằm trên volume gắn zone hoặc local ephemeral storage không?
- **Bootstrap:** instance mới có thể tải artifact, secret và cấu hình trong thời gian yêu cầu không?
- **Health/readiness:** máy mới chỉ nhận traffic khi đã sẵn sàng.
- **Scale-in protection:** máy giữ vai trò đặc biệt có cần được bảo vệ khỏi terminate tự động không?

Với instance dùng local/ephemeral disk, terminate có thể làm mất dữ liệu. Chỉ dùng loại storage này cho dữ liệu có thể tái tạo, cache hoặc workload có checkpoint. Dữ liệu bền vững nên nằm trên dịch vụ lưu trữ có vòng đời phù hợp và có kế hoạch replication/backup.

## 15. Kết hợp nhiều zone với dữ liệu và dependency

Compute có thể được phân bố nhiều zone nhưng database hoặc storage vẫn chỉ nằm ở một zone. Khi dependency đơn vùng gặp sự cố, các VM còn sống ở zone khác vẫn không thể phục vụ.

Kiểm tra các dependency:

- Database có replication, failover và endpoint phù hợp multi-zone không?
- Volume block có bị giới hạn trong một zone không? Có cần snapshot/replication hoặc volume thay thế?
- Cache có thể tái tạo và warm-up ở zone khác không?
- Queue/message broker có khả năng chịu lỗi zone không?
- DNS, secret manager, container/image registry và control plane có thể truy cập khi một zone lỗi không?
- NAT gateway, firewall, egress và route có điểm lỗi đơn không?

Traffic liên zone có thể phát sinh chi phí và độ trễ. Nếu workload thường xuyên đọc dữ liệu từ zone khác, tính tổng chi phí truyền dữ liệu và tác động tới p99. Có thể cần replica dữ liệu gần compute hoặc thay đổi placement để giảm cross-zone traffic.

## 16. Ví dụ thiết kế regional group ba zone với mixed instance types

Giả sử một API stateless cần phục vụ peak tương đương 300 capacity units. Nhóm chạy trong ba zone, mỗi zone có subnet riêng. Workload hỗ trợ hai loại máy đã benchmark: loại M có weight 4 và loại L có weight 8. Cả hai đều đáp ứng RAM tối thiểu và tương thích runtime.

Một thiết kế khởi đầu:

| Thành phần | Thiết kế minh họa |
|---|---|
| Region | Một region có ba AZ được hỗ trợ |
| Normal capacity | 300 units, mục tiêu khoảng 100 units mỗi AZ |
| Failover capacity | Hai AZ còn lại có khả năng đạt 150 units mỗi AZ khi một AZ mất |
| Instance types | M (weight 4), L (weight 8), đã benchmark |
| Purchase model | On-Demand cho baseline; Spot chỉ cho phần stateless có thể retry nếu phù hợp |
| Scaling signal | Request count per target kết hợp latency và queue depth |
| Min/Max | Min đủ tải nền và yêu cầu N-1; Max theo quota, budget và capacity test |
| Health | Readiness endpoint và load balancer health check |
| Scale-in | Drain connection, bảo vệ dữ liệu cần thiết, duy trì phân bố zone |

Vì mỗi AZ cần tối đa 150 units trong tình huống một AZ mất, có thể chọn giữ sẵn một phần headroom ở mỗi AZ và cho phép scale-out bổ sung phần còn lại. Nếu thời gian cấp phát máy mới không đáp ứng RTO, cần giữ nhiều capacity nóng hơn thay vì dựa hoàn toàn vào autoscaling sau sự cố.

Khi một AZ không cấp được loại L, nhóm có thể dùng nhiều máy M nếu tổng weight đạt mục tiêu và từng máy đủ RAM. Nếu chỉ có máy M nhưng mỗi instance không đáp ứng giới hạn memory của ứng dụng, không thể thay thế bằng cách cộng tổng weight; cần giữ loại máy đáp ứng yêu cầu tối thiểu.

## 17. Kiểm thử phân phối capacity và kịch bản lỗi

Kiểm thử nên xác minh không chỉ việc nhóm tạo đủ số máy mà cả năng lực thực tế và hành vi khi mất một miền lỗi.

Các bài kiểm thử nên có:

1. **Steady state:** xác nhận capacity và phân bố zone/family khi tải bình thường.
2. **Scale-out:** tăng tải, đo thời gian từ tín hiệu đến lúc instance healthy và nhận traffic.
3. **Scale-in:** giảm tải, xác nhận drain và dữ liệu được xử lý đúng.
4. **Zone impairment:** giả lập hoặc diễn tập quy trình loại một zone khỏi phục vụ, kiểm tra capacity N-1.
5. **Instance type unavailable:** kiểm tra nhóm có chọn được loại thay thế và đạt đúng capacity units.
6. **Spot interruption:** nếu dùng Spot, xác nhận checkpoint, retry, replacement và thông báo interruption.
7. **Rebalance:** kiểm tra surge capacity, quota và ảnh hưởng lên traffic.
8. **Dependency failure:** xác nhận compute còn sống không bị nhầm là ứng dụng vẫn phục vụ khi database/storage lỗi.

Ghi lại desired capacity, actual capacity, pending instances, capacity theo zone/family, thời gian boot, thời gian warm-up, health state, request rate, latency và error rate. Một bài test chỉ PASS khi SLO và mục tiêu phục hồi đạt, không chỉ khi API tạo instance trả về thành công.

## 18. Theo dõi và cảnh báo

Dashboard cho instance group nên hiển thị ít nhất:

- Desired, actual, minimum và maximum capacity.
- Instance count và weighted capacity theo zone.
- Capacity theo instance family/size và purchase model.
- Pending, unhealthy, terminating và interrupted instances.
- Tỷ lệ phân phối request, CPU, memory, network và disk theo zone/type.
- Thời gian từ scale request đến healthy capacity.
- Lỗi cấp phát do quota, thiếu capacity hoặc cấu hình không hợp lệ.
- Chi phí theo zone, loại máy và purchase model.

Các cảnh báo quan trọng:

- Actual capacity thấp hơn desired capacity quá thời gian cho phép.
- Một zone có tỷ lệ capacity thấp hoặc cao bất thường.
- Nhóm không còn đủ capacity cho kịch bản N-1.
- Tỷ lệ một instance type tăng quá cao hoặc loại thay thế không tương thích.
- Scale-out kéo dài, pending instance hoặc health check thất bại.
- Quota tiến gần giới hạn hoặc capacity reservation không còn phù hợp.
- Spot interruption tăng hoặc workload không checkpoint kịp.

Không chỉ cảnh báo theo số instance. Với mixed group, hãy dùng weighted capacity và kiểm tra resource tối thiểu trên từng máy.

## 19. Những lỗi thiết kế thường gặp

- **Đếm instance thay cho capacity:** nhóm có đủ số máy nhưng tổng năng lực không đủ. Dùng weight hoặc application throughput đã đo.
- **Cộng vCPU và bỏ qua RAM:** máy thay thế không thể chạy workload do thiếu bộ nhớ mỗi node. Đặt ràng buộc cấu hình tối thiểu.
- **Chỉ chạy một zone:** zone gặp sự cố làm mất toàn bộ compute. Phân tán qua các miền lỗi phù hợp.
- **Giả định autoscaling luôn tìm được máy:** zone hoặc family có thể hết capacity, quota có thể bị chạm. Đa dạng hóa loại máy và kiểm thử allocation failure.
- **Không có N-1 headroom:** khi mất một zone, phần còn lại quá tải trước khi scale-out hoàn tất. Tính capacity failover theo peak.
- **Chọn Spot cho tải không thể gián đoạn:** interruption làm mất request hoặc trạng thái. Dùng On-Demand cho baseline và checkpoint/retry cho phần có thể gián đoạn.
- **Mixed instance list quá rộng:** image, kiến trúc CPU, driver hoặc RAM không tương thích. Chỉ dùng loại đã xác minh.
- **Rebalance terminate trước khi tạo thay thế:** capacity giảm hoặc dữ liệu local bị mất. Kiểm tra surge và termination policy.
- **Chỉ quan sát metric toàn nhóm:** mất cân bằng theo zone hoặc type bị che khuất. Theo dõi chi tiết theo từng chiều.
- **Bỏ qua dependency đa zone:** compute còn sống nhưng database hoặc storage đã thành điểm lỗi đơn. Thiết kế resilience xuyên suốt.

## 20. Checklist thiết kế

- [ ] Đã xác định đơn vị capacity phù hợp với workload và giới hạn tài nguyên tối thiểu trên từng instance.
- [ ] Đã chọn các zone có hỗ trợ instance type, subnet và dependency cần thiết.
- [ ] Đã tính capacity peak và kịch bản mất một zone (N-1).
- [ ] Có headroom, quota hoặc reservation phù hợp với thời gian phục hồi yêu cầu.
- [ ] Danh sách instance types đã được benchmark về CPU, RAM, network, storage và accelerator.
- [ ] Kiến trúc CPU, runtime, native library và driver tương thích với mọi loại máy trong nhóm.
- [ ] Weighted capacity phản ánh năng lực đo được và xử lý đúng khi instance có weight lớn.
- [ ] Purchase model phân biệt baseline ổn định với phần workload có thể gián đoạn.
- [ ] Autoscaling min/desired/max, metric, warm-up và scale-in policy được cấu hình rõ.
- [ ] Rebalancing có surge capacity, connection draining và bảo vệ dữ liệu.
- [ ] Dependency như database, storage, queue, NAT và DNS cũng có thiết kế chịu lỗi zone.
- [ ] Dashboard theo dõi capacity theo zone, instance type, health và purchase model.
- [ ] Đã kiểm thử zone impairment, allocation failure, Spot interruption, scale-in và N-1.

Phân phối capacity giữa nhiều zone và nhiều loại máy giúp instance group vừa có khả năng chịu lỗi vừa linh hoạt khi nguồn cung cloud thay đổi. Khi capacity được đo theo năng lực workload, các loại máy được chọn theo điều kiện tương thích, zone có đủ headroom cho failover và autoscaling được kiểm thử trong tình huống thiếu capacity, hệ thống có thể duy trì SLO với chi phí và rủi ro dễ kiểm soát hơn.

# Phân biệt ưu đãi giá với bảo đảm capacity

Khi mua năng lực compute trên cloud, hai câu hỏi thường bị nhầm lẫn: “Làm sao trả ít tiền hơn cho VM?” và “Làm sao chắc chắn có đủ VM để khởi chạy khi cần?”. Một cam kết sử dụng dài hạn hoặc gói tiết kiệm có thể giảm đơn giá, nhưng không nhất thiết giữ sẵn CPU/RAM trong một zone. Ngược lại, một capacity reservation có thể giữ chỗ tài nguyên cho workload, nhưng không tự động đồng nghĩa với mức chiết khấu.

**Ưu đãi giá (pricing discount)** giảm số tiền phải trả cho mức sử dụng đủ điều kiện. **Bảo đảm capacity (capacity reservation/commitment)** giữ trước một lượng tài nguyên hoặc khả năng khởi chạy trong phạm vi cụ thể. Một số sản phẩm của nhà cung cấp kết hợp cả hai đặc tính, nhưng nhiều sản phẩm chỉ giải quyết một mục tiêu.

Trong **CLOUD_CORE_SERVICES_COMPUTE**, cần phân biệt rõ hai loại lợi ích khi chọn On-Demand, Reserved Instances, Savings Plans, Committed Use Discounts, Spot/Preemptible và Capacity Reservations. Quyết định tốt phải xét đồng thời mức sử dụng dự kiến, độ ổn định của workload, vị trí tài nguyên, khả năng bị gián đoạn, thời hạn cam kết và rủi ro trả tiền cho capacity không dùng đến.

## 1. Hai mục tiêu khác nhau: giảm giá và giữ capacity

### 1.1. Ưu đãi giá là gì?

Ưu đãi giá làm giảm đơn giá hoặc chi phí của phần usage đáp ứng điều kiện. Điều kiện có thể gồm:

- Cam kết chi tiêu hoặc sử dụng trong một khoảng thời gian.
- Dùng đúng họ dịch vụ, loại instance, hệ điều hành hoặc region.
- Duy trì một mức tiêu thụ compute mỗi giờ hoặc mỗi tháng.
- Trả trước một phần hoặc toàn bộ giá trị cam kết.
- Dùng một loại tài nguyên đủ điều kiện theo hợp đồng.

Ưu đãi có thể áp dụng cho usage thực tế phát sinh. Nếu workload không chạy, khoản tiết kiệm có thể không phát sinh; với một số commitment, người mua vẫn phải thanh toán mức cam kết dù usage thấp hơn.

### 1.2. Capacity reservation là gì?

Capacity reservation giữ trước khả năng sử dụng một lượng tài nguyên compute nhất định trong phạm vi được chỉ định. Phạm vi có thể gắn với:

- Region và availability zone.
- Instance family/type hoặc kích thước VM.
- Kiến trúc CPU, accelerator hoặc thuộc tính phần cứng.
- Platform, tenancy hoặc operating system.
- Số lượng instance, vCPU, GPU hoặc đơn vị capacity.
- Thời gian reservation còn hiệu lực và các điều kiện sử dụng.

Capacity reservation giải quyết rủi ro thiếu capacity khi cần tạo hoặc khởi động máy. Nó không tự làm ứng dụng nhanh hơn, không bảo đảm database hay network dependency cũng có capacity, và không nhất thiết giảm đơn giá.

### 1.3. Bảng phân biệt nhanh

| Tiêu chí | Ưu đãi giá | Bảo đảm capacity |
| --- | --- | --- |
| Mục tiêu | Giảm chi phí cho usage đủ điều kiện | Giữ chỗ tài nguyên có thể khởi chạy |
| Câu hỏi chính | “Đơn giá compute còn bao nhiêu?” | “Khi cần, có đủ máy ở đúng nơi không?” |
| Phạm vi | Có thể linh hoạt theo family, region hoặc mức chi tiêu | Thường cụ thể hơn về zone, loại máy và số lượng |
| Giá trị khi không dùng | Có thể mất phần tiết kiệm hoặc vẫn phải trả commitment | Reservation có thể vẫn bị tính phí dù chưa dùng |
| Tác động đến availability | Không mặc nhiên bảo đảm khả năng khởi chạy | Giảm rủi ro thiếu capacity trong phạm vi reservation |
| Ví dụ | Savings Plan, Committed Use Discount, nhiều loại Reserved Instance | On-Demand Capacity Reservation, Azure Capacity Reservation, Compute Engine Reservation |

Một hợp đồng hoặc sản phẩm có thể có cả hai tính năng. Luôn đọc đúng loại reservation và điều khoản của nhà cung cấp thay vì suy luận từ tên gọi.

## 2. Nhóm mô hình mua compute phổ biến

Các mô hình thường gặp có thể chia theo mục tiêu:

| Mô hình | Cách tính/hoạt động | Ưu tiên chính |
| --- | --- | --- |
| On-Demand/pay-as-you-go | Trả theo usage thực tế, không cam kết dài hạn | Linh hoạt |
| Reserved Instances/VM reservations | Cam kết theo điều kiện và thời hạn để nhận mức giá ưu đãi; một số loại có thêm capacity benefit | Giảm giá, đôi khi kết hợp capacity |
| Savings Plans | Cam kết mức chi tiêu compute theo thời gian để nhận đơn giá ưu đãi cho usage đủ điều kiện | Giảm giá linh hoạt |
| Committed Use Discounts (CUD) | Cam kết mức sử dụng hoặc chi tiêu trong thời hạn để nhận chiết khấu | Giảm giá |
| Spot/Preemptible | Dùng capacity dư thừa với giá thấp hơn, có thể bị thu hồi | Giảm chi phí cho workload chịu gián đoạn |
| Capacity Reservation | Đặt trước capacity cụ thể theo phạm vi dịch vụ | Bảo đảm khả năng khởi chạy |

Không nên coi Spot là một loại capacity guarantee. Spot sử dụng capacity dư thừa và có thể bị thu hồi; giá thấp đi cùng rủi ro gián đoạn và không có cam kết rằng capacity sẽ luôn sẵn có.

## 3. On-Demand: linh hoạt và dễ bắt đầu

On-Demand cho phép tạo VM và trả tiền theo mức sử dụng mà không cần ký cam kết một hoặc ba năm. Đây thường là lựa chọn phù hợp khi:

- Workload mới, chưa có dữ liệu sử dụng đủ dài.
- Tải biến động hoặc khó dự báo.
- Môi trường dev/test chỉ chạy theo giờ.
- Cần capacity ngắn hạn cho chiến dịch hoặc sự kiện.
- Cần thử nhiều loại instance trước khi chuẩn hóa.
- Workload cần khả năng thay đổi region, family hoặc kích thước thường xuyên.

Ưu điểm:

- Không phải dự báo dài hạn trước khi bắt đầu.
- Có thể tăng/giảm hoặc xóa tài nguyên theo nhu cầu.
- Không phải trả phí cam kết khi không dùng.
- Phù hợp làm baseline để đo usage và so sánh các phương án mua.

Hạn chế:

- Đơn giá thường cao hơn các lựa chọn có commitment.
- On-Demand không đồng nghĩa với capacity luôn có sẵn ở mọi zone hoặc instance type.
- Khi thiếu capacity, việc tạo VM vẫn có thể thất bại hoặc phải đổi zone/type.

On-Demand là mô hình mua linh hoạt, không phải một reservation. Nếu workload quan trọng cần chắc chắn có đủ máy tại một thời điểm, cần đánh giá capacity riêng.

## 4. Reserved Instances và các cam kết giá

Tên gọi “Reserved Instance” có thể chỉ một sản phẩm giảm giá, một sản phẩm có capacity benefit hoặc một cơ chế reservation theo từng cloud provider. Cần phân biệt theo nhà cung cấp và loại cụ thể.

### 4.1. Cam kết giá theo thời hạn

Một số chương trình cho phép cam kết dùng một loại compute hoặc mức chi tiêu trong 1 năm, 3 năm hay thời hạn khác. Đổi lại, usage phù hợp được tính theo mức giá thấp hơn.

Điều kiện có thể ràng buộc:

- Instance family hoặc loại máy.
- Region hoặc zone.
- Platform/OS và tenancy.
- Kích thước hoặc đơn vị vCPU/RAM.
- Mức trả trước và lịch thanh toán.
- Khả năng đổi, trao đổi hoặc hủy cam kết.

Cam kết càng cụ thể có thể có giá ưu đãi tốt hơn, nhưng rủi ro mismatch tăng nếu workload đổi loại máy, region hoặc kiến trúc.

### 4.2. AWS Reserved Instances

Trong AWS EC2, Reserved Instances chủ yếu là cơ chế giá cho usage đủ điều kiện. Cần phân biệt:

- **Regional Reserved Instance:** thường mang lại discount cho usage phù hợp trong region theo các điều kiện áp dụng; không phải capacity reservation theo zone.
- **Zonal Reserved Instance:** gắn với Availability Zone cụ thể và có thể cung cấp capacity reservation cho instance attributes đủ điều kiện, bên cạnh lợi ích giá.

AWS còn có **On-Demand Capacity Reservations**, là sản phẩm riêng để giữ capacity EC2 trong Availability Zone. Capacity Reservation được tính phí theo mức On-Demand cho capacity đã đặt, kể cả phần chưa dùng; discount từ Reserved Instance hoặc Savings Plans đủ điều kiện có thể áp dụng cho usage tương ứng theo quy tắc billing.

Vì vậy, không nên nói chung rằng “mua Reserved Instance là luôn có capacity” hoặc “mọi RI đều chỉ giảm giá”. Cần xem loại Regional/Zonal, thuộc tính instance và điều khoản hiện hành.

### 4.3. Azure Reservations

Azure Reservations cho nhiều dịch vụ compute thường giảm giá khi cam kết sử dụng trong thời hạn. Một Azure reservation cho VM không tự động có nghĩa là đã giữ trước capacity tại một zone.

Azure có **On-demand Capacity Reservation** cho một số cấu hình VM/region/zone. Reservation này giữ capacity theo thuộc tính được chọn và có thể được tính phí theo mức tương ứng ngay cả khi chưa dùng hết. Azure Reservation discount có thể áp dụng cho usage phù hợp theo quy tắc của dịch vụ.

Khi thiết kế, phân biệt VM reservation dùng để tối ưu giá với capacity reservation dùng để giữ chỗ. Kiểm tra riêng availability theo region, zone, VM size, subscription và quota.

### 4.4. Google Cloud committed use và reservations

Google Cloud có các dạng **Committed Use Discounts (CUD)** cho mức sử dụng compute đủ điều kiện. CUD giảm chi phí khi tổ chức cam kết trong thời hạn; bản thân commitment không tự bảo đảm tài nguyên sẽ được cấp phát ở một zone cụ thể.

Google Cloud **Reservations** dành cho Compute Engine có thể giữ capacity cho các VM có thuộc tính phù hợp. Reservation được tạo theo phạm vi và cấu hình được hỗ trợ; phần capacity đã đặt có thể phát sinh phí dù không được sử dụng. CUD có thể áp dụng cho usage đủ điều kiện theo cách billing của sản phẩm.

Phải phân biệt resource-based/flexible CUD, reservation và Spot VM. Chúng giải quyết các bài toán giá và capacity khác nhau.

## 5. Savings Plans và Committed Use Discounts

Savings Plans và CUD thường phù hợp khi tổ chức có mức sử dụng compute nền tương đối ổn định nhưng muốn linh hoạt hơn so với cam kết một loại instance rất cụ thể.

### 5.1. AWS Savings Plans

AWS Savings Plans là cam kết mức chi tiêu compute theo giờ trong thời hạn, đổi lại mức giá thấp hơn cho usage đủ điều kiện. Có các loại với phạm vi linh hoạt khác nhau, chẳng hạn Compute Savings Plans và EC2 Instance Savings Plans.

Điểm quan trọng:

- Đây là cơ chế giảm giá dựa trên cam kết chi tiêu.
- Compute Savings Plans linh hoạt hơn về loại compute đủ điều kiện.
- EC2 Instance Savings Plans thường gắn với family/region cụ thể hơn.
- Savings Plans không tự giữ capacity EC2 trong một Availability Zone.
- Nếu usage đủ điều kiện thấp hơn commitment, phần cam kết chưa dùng vẫn có thể bị tính phí.

Nếu workload cần capacity chắc chắn, có thể cần kết hợp Savings Plans với Capacity Reservations hoặc một chiến lược capacity khác.

### 5.2. Google Cloud Committed Use Discounts

CUD cho phép cam kết chi tiêu hoặc tài nguyên đủ điều kiện trong thời hạn để nhận mức giá ưu đãi. Phạm vi và cách áp dụng phụ thuộc loại commitment, dịch vụ, region và tài nguyên.

CUD nên được mua dựa trên baseline sử dụng có thể dự báo, không dựa trên đỉnh tải nhất thời. CUD không phải là lời hứa rằng một VM cụ thể sẽ có capacity ở zone mong muốn.

### 5.3. Azure Savings Plan for Compute

Azure Savings Plan for Compute áp dụng chiết khấu cho mức chi tiêu compute đủ điều kiện trong phạm vi sản phẩm và region được hỗ trợ. Nó mang lại sự linh hoạt về một số loại compute hơn so với một số reservation rất cụ thể, nhưng không tự giữ capacity trong zone.

Khi cần chắc chắn khởi chạy VM ở một zone cụ thể, đánh giá riêng Azure Capacity Reservation.

### 5.4. Cam kết linh hoạt và cam kết cụ thể

| Đặc tính | Commitment linh hoạt | Commitment gắn chặt tài nguyên |
| --- | --- | --- |
| Mục tiêu | Chiết khấu trên tập usage rộng hơn | Chiết khấu sâu hơn cho một cấu hình cụ thể |
| Độ linh hoạt | Có thể thay đổi family/service trong phạm vi cho phép | Thường bị giới hạn family, region, size hoặc platform |
| Rủi ro mismatch | Thấp hơn nhưng không bằng 0 | Cao hơn nếu workload thay đổi |
| Khả năng bảo đảm capacity | Không mặc nhiên có | Chỉ có nếu sản phẩm cụ thể nêu rõ capacity benefit |
| Phù hợp | Fleet có baseline compute ổn định nhưng thay đổi cấu hình | Workload ổn định và cấu hình ít thay đổi |

## 6. Capacity Reservation: giữ chỗ năng lực tính toán

Capacity Reservation nhằm giải quyết câu hỏi “liệu có thể khởi chạy đúng loại máy ở đúng nơi vào thời điểm cần hay không?”.

### 6.1. Vì sao cần giữ capacity?

Trong cloud, quota và capacity vật lý là hai giới hạn khác nhau:

- **Quota** là giới hạn tài nguyên được phép dùng trong account/project/subscription.
- **Capacity** là khả năng hạ tầng của provider cấp phát một loại tài nguyên tại một vị trí cụ thể.

Một account có quota còn dư vẫn có thể không tạo được một loại VM ở một zone do capacity tạm thời thiếu. Ngược lại, có reservation nhưng quota hoặc policy không đủ cũng có thể khiến việc sử dụng thất bại.

Capacity Reservation hữu ích khi:

- Có sự kiện hoặc đợt tải cần khởi chạy nhiều VM đồng thời.
- Có yêu cầu khôi phục DR tại một zone/region xác định.
- Workload cần instance family hoặc GPU khan hiếm.
- Có cửa sổ batch ngắn và không thể chờ capacity xuất hiện.
- Có yêu cầu duy trì capacity dự phòng cho hệ thống quan trọng.

### 6.2. Reservation có phạm vi cụ thể

Trước khi đặt reservation, kiểm tra:

- Region và zone.
- Machine type/family, vCPU, memory và accelerator.
- Kiến trúc CPU và platform/OS nếu có ràng buộc.
- Số lượng instance hoặc tổng capacity.
- Network/subnet và điều kiện attach.
- Thời gian reservation và cách điều chỉnh.
- Có thể chia sẻ reservation cho account/project khác hay không.
- Billing khi capacity chưa dùng và cách áp dụng discount.

Reservation chỉ bảo đảm những thuộc tính nằm trong phạm vi sản phẩm. Một reservation cho một loại VM không tự động bảo đảm GPU, IP public, disk IOPS, database connection hay băng thông của mọi dependency.

### 6.3. Unused reservation vẫn có thể tốn tiền

Capacity đã giữ có thể bị tính phí ngay cả khi không có VM sử dụng. Đây là chi phí để giữ quyền truy cập vào tài nguyên khan hiếm.

Ví dụ minh họa:

- Đặt chỗ 10 VM trong một zone.
- Trung bình chỉ dùng 6 VM.
- 4 VM capacity còn lại vẫn được giữ và có thể phát sinh chi phí.

Nếu nhu cầu chỉ cần 6 VM ổn định, reservation 10 VM có thể lãng phí. Nếu cần 10 VM trong sự kiện quan trọng, phần capacity dự phòng có thể là khoản chi phí hợp lý để giảm rủi ro không khởi chạy được.

### 6.4. Reservation không phải autoscaling

Autoscaling thay đổi số VM theo metric hoặc lịch. Capacity reservation giữ trước khả năng khởi chạy. Hai cơ chế có thể bổ trợ:

- Autoscaler quyết định cần bao nhiêu VM.
- Capacity Reservation cung cấp chỗ cho một phần hoặc toàn bộ số VM đó.
- Group/scale set tạo VM theo template.
- Health check xác nhận máy đã sẵn sàng.

Autoscaler không thể tạo capacity vật lý nếu provider không có chỗ và không có reservation phù hợp. Reservation cũng không tự khởi chạy VM nếu không có group hoặc automation điều khiển.

## 7. Spot và Preemptible: giá thấp đổi lấy khả năng bị thu hồi

Spot/Preemptible VM sử dụng capacity dư thừa của provider với giá thấp hơn On-Demand. Provider có thể thu hồi tài nguyên khi cần capacity hoặc theo điều kiện sản phẩm.

Đặc điểm:

- Giá thường thấp đáng kể so với On-Demand.
- Không có bảo đảm rằng instance tiếp tục chạy đến hết thời gian mong muốn.
- Có thể nhận interruption notice trong một số tình huống, nhưng không nên dựa vào notice như bảo đảm tuyệt đối.
- Capacity có thể thay đổi theo region, zone, instance type và nhu cầu.
- Workload phải chịu được restart, retry hoặc mất một phần tiến trình.

Phù hợp với:

- Batch processing có checkpoint.
- CI build/test có thể chạy lại.
- Distributed rendering.
- Một số workload ETL hoặc analytics.
- Training có checkpoint và dữ liệu ngoài instance.
- Worker xử lý queue có lease, idempotency và retry.

Không phù hợp nếu instance là nơi giữ duy nhất dữ liệu quan trọng, workload không thể khởi động lại hoặc yêu cầu capacity liên tục không có phương án thay thế.

Spot có giá thấp nhưng không phải công cụ capacity assurance. Muốn bảo đảm capacity cho workload không thể gián đoạn, cần On-Demand hoặc reservation/commitment có capacity phù hợp.

## 8. Ma trận phân loại theo lợi ích

| Sản phẩm/mô hình | Giảm giá | Bảo đảm capacity | Có thể bị gián đoạn theo cơ chế sản phẩm |
| --- | --- | --- | --- |
| On-Demand | Không có commitment discount | Không mặc nhiên | Không bị thu hồi theo cơ chế Spot, nhưng vẫn chịu sự cố/provider event |
| Savings Plans | Có | Không | Không theo cơ chế Spot |
| CUD | Có | Không mặc nhiên | Không theo cơ chế Spot |
| Regional RI (AWS) | Có | Không theo zone | Không theo cơ chế Spot |
| Zonal RI (AWS) | Có | Có capacity benefit theo điều kiện | Không theo cơ chế Spot |
| Capacity Reservation | Không tự có discount; có thể kết hợp discount đủ điều kiện | Có trong phạm vi reservation | Không theo cơ chế Spot |
| Azure VM Reservation | Có | Không mặc nhiên | Không theo cơ chế Spot |
| Azure Capacity Reservation | Không tự có discount; có thể kết hợp ưu đãi đủ điều kiện | Có trong phạm vi reservation | Không theo cơ chế Spot |
| Google Cloud CUD | Có | Không mặc nhiên | Không theo cơ chế Spot |
| Google Cloud Reservation | Không tự có discount; có thể kết hợp CUD đủ điều kiện | Có trong phạm vi reservation | Không theo cơ chế Spot |
| Spot/Preemptible | Có mức giá thấp | Không | Có thể bị thu hồi |

Bảng này là mô hình khái quát. Cách kết hợp discount, reservation và billing phụ thuộc sản phẩm, thuộc tính tài nguyên và điều khoản hiện hành. Với AWS Zonal Reserved Instances, capacity benefit có điều kiện và không nên suy rộng sang Regional RI hoặc Savings Plans.

## 9. Tính toán lợi ích và rủi ro commitment

Không nên chọn commitment chỉ dựa trên phần trăm discount quảng cáo. Cần tính tổng chi phí trong các kịch bản usage thực tế.

### 9.1. Công thức so sánh cơ bản

Với một mô hình đơn giản:

\[
\text{On-Demand cost} = \text{Eligible usage} \times \text{On-Demand rate}
\]

\[
\text{Commitment cost} =
\text{Committed amount} + \text{Usage vượt commitment}
\]

Chi phí commitment thực tế phụ thuộc cách sản phẩm tính cam kết theo giờ, theo tài nguyên, trả trước hoặc trả hàng tháng. Cần dùng billing model cụ thể của provider khi tính chính thức.

### 9.2. Ví dụ cam kết giảm giá

Giả sử một workload có giá On-Demand giả định là 0,10 USD cho mỗi giờ VM tương đương. Một commitment đủ điều kiện giảm giá 30%, còn 0,07 USD cho mỗi giờ đã cam kết. Để đơn giản, giả sử cam kết cho 1.000 giờ VM tương đương trong kỳ:

| Usage thực tế | On-Demand | Commitment 1.000 giờ ở 0,07 USD | Kết quả |
| ---: | ---: | ---: | --- |
| 1.200 giờ | 120 USD | 70 + 20 = 90 USD | Tiết kiệm 30 USD |
| 1.000 giờ | 100 USD | 70 USD | Tiết kiệm 30 USD |
| 800 giờ | 80 USD | 70 USD | Tiết kiệm 10 USD |
| 500 giờ | 50 USD | 70 USD | Tốn thêm 20 USD |

Ví dụ chỉ nhằm minh họa rủi ro underutilization. Trong sản phẩm thật, commitment có thể được tính theo mức chi tiêu mỗi giờ và usage được áp dụng theo thứ tự billing riêng, không phải một gói “giờ VM” đơn giản.

### 9.3. Tỷ lệ sử dụng commitment

\[
\text{Commitment utilization} =
\frac{\text{Eligible usage covered}}{\text{Committed amount}}
\times 100\%
\]

Theo dõi utilization cùng coverage:

- **Utilization:** phần commitment đã được sử dụng.
- **Coverage:** phần tổng eligible spend được commitment bao phủ.

Utilization thấp cho thấy đang trả tiền cho commitment chưa dùng hết. Coverage thấp cho thấy còn nhiều usage đang trả On-Demand dù có thể cân nhắc commitment.

Không tối đa hóa coverage bằng mọi giá. Nếu mua commitment để bao phủ cả đỉnh tải ngắn hạn, tổ chức có thể khóa chi phí dài hạn cao hơn lợi ích thực tế.

### 9.4. Ví dụ capacity reservation

Giả sử giữ 8 slot VM ở mức giá giả định 0,10 USD/slot/giờ trong 30 ngày:

\[
8 \times 0.10 \times 24 \times 30 = 576\ \text{USD}
\]

Nếu trung bình chỉ dùng 5 slot, khoản chi phí capacity chưa dùng tương đương:

\[
(8-5) \times 0.10 \times 24 \times 30 = 216\ \text{USD}
\]

Đây là mô hình tính đơn giản để thấy chi phí của capacity nhàn rỗi. Cách billing thật, discount được áp dụng và loại reservation có thể khác nhau. Giá trị của 3 slot dư là khả năng khởi chạy khi nhu cầu tăng đột ngột hoặc khi cần phục hồi.

## 10. Chọn công cụ theo loại workload

| Workload | Ưu đãi giá phù hợp | Capacity strategy |
| --- | --- | --- |
| Production baseline chạy 24/7 | Savings Plan/CUD/RI theo mức sử dụng ổn định | Reservation cho cấu hình/zone quan trọng nếu cần bảo đảm |
| API có tải biến động | Commitment cho baseline, On-Demand cho phần dao động | Autoscaling, capacity buffer và reservation cho sự kiện đã biết |
| Batch có thể retry | Spot/Preemptible kết hợp commitment cho phần nền nếu phù hợp | Diversify pool, checkpoint và fallback On-Demand |
| Dev/test theo giờ | On-Demand, lịch tự động tắt, Spot cho workload chịu gián đoạn | Không cần reservation dài hạn nếu không có nhu cầu cụ thể |
| GPU inference/training | Commitment nếu GPU usage ổn định; Spot cho job chịu interruption | Reservation theo GPU type/zone khi khan hiếm |
| Disaster recovery | Commitment cho baseline standby nếu có usage đều | Capacity reservation ở recovery zone/region khi RTO yêu cầu |
| Sự kiện tải lớn có lịch | Commitment cho phần nền nếu sử dụng dài hạn | Capacity reservation tạm thời hoặc theo kế hoạch |

Một fleet có thể kết hợp nhiều mô hình. Ví dụ, giữ baseline production bằng commitment, dùng On-Demand cho phần scale-out, Spot cho batch có thể retry và capacity reservation cho một nhóm VM cần khởi chạy chắc chắn trong DR.

## 11. Quy trình ra quyết định

~~~mermaid
flowchart TD
    A["Xác định nhu cầu compute"] --> B{"Cần bảo đảm có máy ở vị trí cụ thể?"}
    B -- "Có" --> C["Xác định zone, type, số lượng và thời gian"]
    C --> D["Đánh giá Capacity Reservation"]
    D --> E{"Usage có ổn định dài hạn?"}
    B -- "Không" --> E
    E -- "Có" --> F["Phân tích Savings Plan / CUD / RI"]
    E -- "Không" --> G{"Workload chịu được interruption?"}
    G -- "Có" --> H["Đánh giá Spot/Preemptible"]
    G -- "Không" --> I["Dùng On-Demand và autoscaling"]
    F --> J["Mô hình hóa utilization, coverage và tổng chi phí"]
    H --> J
    I --> J
    J --> K["Kiểm tra quota, capacity, scope và điều khoản"]
    K --> L["Thử nghiệm, theo dõi và điều chỉnh"]
~~~

Các bước chi tiết:

1. **Phân loại workload:** baseline, burst, batch, dev/test, DR hay GPU.
2. **Đo usage:** theo giờ, ngày, tuần, mùa vụ và vùng.
3. **Xác định availability requirement:** có cần capacity tại zone/instance type cụ thể không?
4. **Tách baseline và biến động:** commitment chỉ nên bao phủ phần có thể dự báo.
5. **Đánh giá interruption:** workload có checkpoint, retry, idempotency và state externalization không?
6. **Chọn sản phẩm:** pricing discount, capacity reservation hoặc kết hợp.
7. **Kiểm tra điều khoản:** term, scope, exchange/cancel, payment, sharing và billing.
8. **Mô phỏng kịch bản:** usage thấp, bình thường, tăng trưởng và peak.
9. **Mua theo giai đoạn:** tránh cam kết toàn bộ fleet ngay từ đầu.
10. **Theo dõi định kỳ:** utilization, coverage, unused capacity và hiệu quả thực tế.

## 12. Những câu hỏi phải kiểm tra trước khi mua

### 12.1. Về ưu đãi giá

- Commitment áp dụng cho service, family, region và platform nào?
- Có áp dụng cho instance size khác nhau không?
- Có thể đổi family, region hoặc account không?
- Có thể bán lại, trao đổi hoặc hủy không?
- Mức trả trước và lịch thanh toán thế nào?
- Usage nào không đủ điều kiện?
- Discount có được kết hợp với reservation hoặc license benefit không?
- Commitment chưa dùng được xử lý ra sao?

### 12.2. Về capacity

- Reservation có giữ đúng zone và loại máy cần thiết không?
- Số lượng là instance, vCPU, GPU hay capacity unit?
- Có thời hạn hoặc lịch bắt đầu/kết thúc không?
- Có cần bật/tắt reservation hoặc gắn với VM cụ thể không?
- Có thể chia sẻ cho account/project/subscription khác không?
- Quota có đủ để sử dụng reservation không?
- Reservation có bao gồm disk, network, public IP hoặc accelerator không?
- Billing khi không sử dụng và khi sử dụng một phần thế nào?

### 12.3. Về khả năng phục hồi

- Khi một zone mất, reservation ở zone đó còn giá trị sử dụng không?
- Có reservation hoặc capacity strategy ở zone dự phòng không?
- Nếu instance type bị ngừng cung cấp, có lựa chọn thay thế không?
- Autoscaler có thể tạo đúng cấu hình được giữ chỗ không?
- Startup time có phù hợp RTO không?
- Capacity dự phòng có đủ để phục vụ tải trong khi VM lỗi được thay thế không?

## 13. Các rủi ro phổ biến

### 13.1. Mua commitment cao hơn baseline

Nếu workload giảm sau tối ưu hoặc di chuyển sang container/serverless, commitment cũ có thể không còn usage đủ điều kiện. Phần không dùng vẫn tạo chi phí.

Biện pháp:

- Dùng dữ liệu usage nhiều chu kỳ.
- Trừ phần tải có tính mùa vụ hoặc sắp retire.
- Chừa biên cho tăng trưởng nhưng không lấy peak làm baseline.
- Mua theo từng đợt và review utilization.

### 13.2. Nhầm discount với capacity guarantee

Savings Plan hoặc CUD có thể giảm bill nhưng không giữ slot ở zone cụ thể. Khi region thiếu capacity, VM vẫn có thể không tạo được.

Biện pháp:

- Ghi riêng pricing commitment và capacity requirement.
- Kiểm tra sản phẩm reservation đúng loại.
- Thử tạo VM ở zone/type dự kiến.
- Đưa capacity test vào DR exercise và game day.

### 13.3. Đặt capacity reservation quá lớn

Reservation dư tạo chi phí ngay cả khi không dùng. Số lượng dự phòng cần dựa trên nhu cầu failover, burst và thời gian thay thế capacity.

Biện pháp:

- Tính minimum capacity cần có khi mất một zone.
- Dùng autoscaling cho phần nhu cầu biến động nếu có thể.
- Chọn reservation theo thời gian/scope phù hợp.
- Theo dõi utilization của reservation.

### 13.4. Reservation sai zone hoặc sai instance attributes

Một reservation không thể thay thế mọi loại máy. Nếu instance type, platform, tenancy hoặc zone không khớp, VM có thể không consume reservation.

Biện pháp:

- Xác minh thuộc tính bằng inventory thực tế.
- Kiểm tra reservation matching rules.
- Chạy thử launch với đúng template.
- Theo dõi unused reservation và On-Demand usage đồng thời.

### 13.5. Dựa vào Spot cho workload không chịu gián đoạn

Giá thấp có thể hấp dẫn nhưng interruption làm gián đoạn request, mất tiến trình hoặc gây lỗi dữ liệu.

Biện pháp:

- Chỉ dùng cho workload có thể retry/checkpoint.
- Externalize state và dùng idempotency.
- Phân tán qua nhiều pool/family/zone.
- Có fallback On-Demand hoặc capacity dự phòng cho phần quan trọng.

## 14. Theo dõi và tối ưu sau khi mua

Một quyết định mua compute không kết thúc ở thời điểm ký commitment. Usage và kiến trúc thay đổi theo thời gian.

Theo dõi:

- Commitment utilization và coverage.
- Chi phí On-Demand còn lại.
- Unused reservation capacity.
- Số lần launch thất bại do thiếu capacity.
- Mức sử dụng theo family, zone và region.
- Instance đang chạy nhưng không tạo giá trị nghiệp vụ.
- Thay đổi kiến trúc, lịch retire hoặc migration.
- Chi phí trên mỗi request, job hoặc giao dịch hoàn tất.

Review định kỳ:

1. Đối chiếu hóa đơn với forecast và usage thực tế.
2. Xác định commitment nào có utilization thấp.
3. Xác định usage On-Demand ổn định có thể được bao phủ.
4. Kiểm tra reservation có đang giữ đúng loại capacity cần thiết.
5. Đánh giá thay đổi workload trước khi gia hạn.
6. Điều chỉnh theo quy tắc exchange/cancel và thời hạn sản phẩm.

Không chỉ tối ưu theo phần trăm discount. Mục tiêu là giảm tổng chi phí mà vẫn đáp ứng capacity, availability và khả năng phục hồi.

## 15. Ví dụ thiết kế kết hợp pricing và capacity

Một dịch vụ API có tải nền tương đương 20 VM trong hầu hết thời gian, tăng lên 35 VM vào giờ cao điểm và cần thêm 10 VM trong một kịch bản DR.

Một cách tiếp cận:

| Phần nhu cầu | Cách mua/vận hành | Lý do |
| --- | --- | --- |
| 20 VM baseline | Commitment giá linh hoạt hoặc RI phù hợp | Usage ổn định, có thể dự báo |
| 15 VM peak | On-Demand theo autoscaling | Chỉ cần trong một số khung giờ |
| 10 VM DR capacity | Capacity Reservation ở site dự phòng nếu RTO yêu cầu | Giảm rủi ro thiếu capacity khi failover |
| Batch phụ trợ | Spot nếu job có checkpoint | Giảm chi phí cho workload chịu interruption |

Trước khi triển khai cần kiểm tra baseline 20 VM có thực sự ổn định trong toàn thời hạn cam kết, peak có thể giảm sau tối ưu, reservation DR có đúng zone/type và quota đủ hay không.

Nếu capacity reservation 10 VM được đặt nhưng chỉ dùng khi DR, phần capacity nhàn rỗi vẫn có thể tốn phí. So sánh chi phí đó với thiệt hại nghiệp vụ nếu không thể khởi chạy đủ máy trong RTO. Nếu tổ chức chấp nhận thời gian provision lâu hơn, pilot light hoặc On-Demand capacity có thể rẻ hơn nhưng cần diễn tập để xác minh.

## 16. Checklist trước khi quyết định

**Mục tiêu**

- [ ] Đã tách rõ mục tiêu giảm giá và mục tiêu bảo đảm capacity.
- [ ] Đã xác định workload baseline, peak, batch và DR.
- [ ] Đã thống nhất yêu cầu availability và RTO.

**Pricing commitment**

- [ ] Có dữ liệu usage đủ dài và đã loại phần sắp retire.
- [ ] Đã xác định scope, term, payment và eligible usage.
- [ ] Đã mô hình hóa utilization thấp, bình thường và tăng trưởng.
- [ ] Đã hiểu điều kiện exchange, modification hoặc cancellation.

**Capacity reservation**

- [ ] Đã xác định zone, instance attributes và số lượng cần giữ.
- [ ] Đã kiểm tra quota và khả năng matching reservation.
- [ ] Đã hiểu billing khi capacity không dùng.
- [ ] Đã kiểm tra capacity cho dependency và network liên quan.
- [ ] Đã có phương án khi zone hoặc instance type không sẵn sàng.

**Vận hành**

- [ ] Autoscaler và instance template có thể dùng reservation đúng cách.
- [ ] Có cảnh báo unused capacity và launch failure.
- [ ] Đã thử scale-out và DR failover.
- [ ] Có review utilization/coverage định kỳ.
- [ ] Có kế hoạch thay đổi commitment khi workload thay đổi.

## 17. Nguyên tắc vận hành

1. **Tách hai bài toán:** discount giảm đơn giá; capacity reservation giữ chỗ tài nguyên.
2. **Không suy luận từ tên sản phẩm:** Reserved Instance, Reservation và Commitment có semantics khác nhau theo provider.
3. **Dùng commitment cho baseline có thể dự báo:** tránh khóa phần peak ngắn hạn hoặc workload sắp thay đổi.
4. **Dùng capacity reservation cho yêu cầu khởi chạy chắc chắn:** xác định đúng zone, type và số lượng.
5. **Tính chi phí capacity nhàn rỗi:** reservation có thể bị tính phí dù chưa dùng.
6. **Dùng Spot cho workload chịu interruption:** cần checkpoint, retry, idempotency và fallback.
7. **Theo dõi quota riêng với capacity:** có quota không đồng nghĩa provider còn capacity.
8. **Kết hợp công cụ có chủ đích:** commitment cho baseline, On-Demand cho biến động, reservation cho nhu cầu chắc chắn và Spot cho batch phù hợp.
9. **Kiểm chứng bằng thử nghiệm:** thử launch, autoscaling, failover và billing matching.
10. **Review định kỳ:** usage, kiến trúc và điều khoản thay đổi có thể làm quyết định mua ban đầu mất hiệu quả.

Ưu đãi giá và bảo đảm capacity giải quyết hai rủi ro khác nhau. Commitment giúp giảm chi phí khi workload sử dụng đủ ổn định; capacity reservation giảm rủi ro không khởi chạy được tài nguyên tại vị trí cần thiết. Khi tách riêng hai mục tiêu, mô hình hóa usage và chi phí chưa dùng, rồi kết hợp chúng theo từng phần workload, tổ chức có thể vừa tối ưu ngân sách vừa giữ đủ năng lực compute cho production và phục hồi sự cố.

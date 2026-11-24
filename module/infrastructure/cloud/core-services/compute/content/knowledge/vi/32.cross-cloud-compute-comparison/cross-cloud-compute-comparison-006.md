# Đối chiếu tài nguyên có thể bị thu hồi, cam kết chi phí và đặt trước capacity

Khi chạy compute trên cloud, tổ chức thường lựa chọn giữa tài nguyên theo nhu cầu, tài nguyên giá thấp có thể bị thu hồi, cam kết sử dụng dài hạn để nhận chiết khấu và capacity được đặt trước để bảo đảm khả năng cấp phát. Các lựa chọn này giải quyết những vấn đề khác nhau. **Spot/Preemptible giảm giá nhưng chấp nhận interruption; savings plan hoặc committed-use discount giảm đơn giá khi cam kết chi tiêu/sử dụng; reservation về capacity giúp bảo đảm có tài nguyên phù hợp trong phạm vi đã đặt.** Một chương trình giảm giá không tự động bảo đảm capacity, và một capacity reservation không nhất thiết tự tạo ra chiết khấu.

Trong môi trường đa cloud, tên sản phẩm và phạm vi cam kết khác nhau giữa nhà cung cấp. Cần so sánh theo cơ chế kinh tế và vận hành thay vì chỉ so tên gọi. Bài này dùng các khái niệm phổ biến của AWS, Microsoft Azure và Google Cloud làm ví dụ, đồng thời tập trung vào cách xác định workload phù hợp, tính tổng chi phí, quản lý rủi ro interruption và tránh mua cam kết vượt nhu cầu.

## 1. Bốn nhóm lựa chọn compute và mục tiêu của chúng

| Nhóm | Mục tiêu chính | Đổi lại | Câu hỏi cần trả lời |
|---|---|---|---|
| On-demand/pay-as-you-go | Có thể cấp phát linh hoạt, trả theo mức sử dụng | Đơn giá thường cao hơn lựa chọn có cam kết | Workload cần linh hoạt đến mức nào? |
| Spot/Preemptible/interruptible | Tận dụng capacity dư thừa với giá thấp | Có thể bị thu hồi, không phù hợp mọi workload | Công việc có thể gián đoạn và tiếp tục không? |
| Savings/commitment discount | Giảm đơn giá khi cam kết chi tiêu hoặc sử dụng | Có nghĩa vụ tài chính trong kỳ cam kết | Mức sử dụng nền có đủ ổn định để cam kết không? |
| Capacity reservation | Giữ khả năng cấp phát một loại tài nguyên tại phạm vi nhất định | Có thể phát sinh phí kể cả khi không sử dụng | Có cần chắc chắn capacity ở zone/region cụ thể không? |

Một kiến trúc có thể kết hợp cả bốn. Ví dụ, database và control plane dùng on-demand hoặc capacity được đặt trước; workload nền ổn định dùng compute commitment; batch có thể chạy trên Spot; phần thiếu capacity được bù bằng on-demand.

### Ba câu hỏi không được đánh đồng

1. **Giá bao nhiêu?** Đây là câu hỏi về đơn giá, discount và billing commitment.
2. **Có cấp được máy khi cần không?** Đây là câu hỏi về capacity availability, quota, region và placement.
3. **Máy có thể bị dừng giữa chừng không?** Đây là câu hỏi về interruption policy và khả năng chịu lỗi của workload.

Một lựa chọn có thể tốt ở một câu hỏi nhưng không tốt ở hai câu hỏi còn lại. Ví dụ, compute commitment có thể giảm hóa đơn cho mức sử dụng đủ điều kiện nhưng không bảo đảm một instance cụ thể luôn có thể được khởi chạy trong zone mong muốn.

## 2. On-demand: mốc tham chiếu linh hoạt

On-demand là hình thức trả tiền theo mức sử dụng mà không cần mua cam kết dài hạn trước. Tổ chức có thể tạo hoặc xóa instance theo nhu cầu, trong giới hạn quota và capacity của provider.

### Ưu điểm

- Linh hoạt khi nhu cầu biến động hoặc chưa dự báo được.
- Không phải dự đoán trước một mức sử dụng dài hạn để mua commitment.
- Phù hợp với môi trường phát triển, thử nghiệm, workload ngắn hạn hoặc phần tải biến thiên.
- Là fallback hữu ích khi Spot bị thu hồi hoặc capacity được đặt trước không đủ.

### Giới hạn

- Đơn giá thường cao hơn khi so với mức giá hiệu dụng sau discount commitment.
- Không bảo đảm capacity vô hạn; quota, instance family, zone và tình trạng hạ tầng vẫn có thể giới hạn khả năng cấp phát.
- Nếu workload chạy ổn định quanh năm, trả toàn bộ theo on-demand có thể tốn kém.

On-demand là baseline hữu ích để so sánh chi phí. Khi đánh giá một chương trình tiết kiệm, hãy so với mức chi phí on-demand của cùng cấu hình, cùng region, hệ điều hành, license, thời gian sử dụng và thành phần liên quan.

## 3. Spot, Preemptible và interruptible compute

Spot/Preemptible là capacity dư thừa mà provider có thể cung cấp với mức giá thấp hơn. Nhà cung cấp có quyền thu hồi capacity để phục vụ nhu cầu khác hoặc quản lý hạ tầng. Vì vậy, người dùng phải thiết kế workload để chịu được việc instance hoặc task bị dừng.

Tên gọi khác nhau theo nền tảng, nhưng đặc tính cốt lõi tương tự:

- Capacity có thể không sẵn có tại thời điểm cần khởi chạy.
- Instance đang chạy có thể bị thu hồi theo chính sách provider.
- Thông báo interruption có thể được cung cấp nhưng thời gian cảnh báo và hành vi cụ thể khác nhau.
- Không nên dựa vào Spot cho một workload yêu cầu máy chạy liên tục mà không có cơ chế failover/checkpoint.
- Giá và tỷ lệ interruption có thể thay đổi theo region, zone, family, size và thời điểm.

### Ví dụ sản phẩm theo provider

| Provider | Tên thường gặp | Đặc điểm cần đối chiếu |
|---|---|---|
| AWS | EC2 Spot Instances | Dùng capacity EC2 dư thừa; có thể nhận interruption notice; nên đa dạng hóa instance type/zone và dùng capacity-optimized allocation khi phù hợp |
| Microsoft Azure | Azure Spot Virtual Machines | Giá thấp hơn pay-as-you-go; có eviction policy và tùy chọn mức giá tối đa theo sản phẩm; không có bảo đảm capacity liên tục |
| Google Cloud | Spot VMs | VM có thể bị preempt; phù hợp workload có thể restart/resume; kiểm tra giới hạn và hành vi của machine series/region |

Tên, điều kiện, giá và tính năng của các dịch vụ có thể thay đổi. Khi lập kế hoạch thực tế, kiểm tra tài liệu và giá hiện hành theo region, machine family, OS/license và loại workload.

### Workload phù hợp

- Batch processing có thể chia thành chunk.
- CI/CD runner và test worker có thể tạo lại.
- Render, encoding hoặc xử lý ảnh có checkpoint.
- Distributed training có thể lưu model/optimizer checkpoint.
- Big data job có khả năng retry partition.
- Stateless worker xử lý message theo semantics at-least-once.
- Môi trường phát triển hoặc thử nghiệm có thể bị dừng.

### Workload thường không phù hợp nếu chạy đơn lẻ trên Spot

- Database primary hoặc hệ thống stateful không có replication/failover.
- Control plane hoặc dịch vụ quản lý không có redundancy.
- Ứng dụng tương tác có phiên làm việc không thể gián đoạn.
- Tác vụ dài không có checkpoint và chi phí chạy lại lớn.
- Workload có license hoặc thiết bị gắn chặt với một instance.
- Dịch vụ có RTO rất ngắn nhưng không có capacity fallback.

Spot vẫn có thể tham gia các hệ thống này như worker phụ hoặc replica không thiết yếu, nếu kiến trúc đã xác định rõ failure mode.

## 4. Thiết kế workload để chịu interruption

Giá Spot thấp chỉ mang lại lợi ích nếu interruption không làm mất quá nhiều công việc hoặc gây tác động nghiệp vụ không thể chấp nhận.

### Chia nhỏ và checkpoint

Chia job thành partition/chunk có ranh giới commit rõ ràng. Lưu checkpoint vào object storage, database hoặc persistent storage độc lập với vòng đời instance. Khi worker bị thu hồi, task mới tiếp tục từ checkpoint hợp lệ.

Checkpoint cần chứa:

- Job ID và partition/chunk ID.
- Input version hoặc snapshot ID.
- Offset/cursor/step đã xử lý.
- Trạng thái thuật toán cần thiết để resume.
- Code/schema version và output reference.
- Checksum, sequence và thời điểm tạo.

Chỉ công bố checkpoint sau khi dữ liệu đã upload và được xác minh. Không ghi đè checkpoint tốt bằng file đang tạo dở.

### Idempotency và retry

Một task có thể được giao lại sau interruption hoặc mất acknowledgement. Dùng idempotency key ổn định, output key xác định, conditional write hoặc deduplication để chạy lại không tạo side effect trùng.

Retry nên có:

- Phân loại lỗi transient và permanent.
- Exponential backoff và jitter.
- Giới hạn attempt và tổng thời gian retry.
- Dead-letter hoặc trạng thái cần người xử lý khi vượt giới hạn.
- Concurrency limit để không tạo retry storm.

### Graceful shutdown

Khi nhận interruption notice hoặc tín hiệu dừng, worker nên ngừng nhận việc mới, hoàn tất phần việc an toàn, lưu checkpoint, flush log và thoát trong thời gian cho phép. Tuy nhiên, notice có thể không đến hoặc thời gian quá ngắn; checkpoint định kỳ vẫn là yêu cầu cơ bản.

### Diversification và fallback

Không phụ thuộc một instance type hoặc một zone duy nhất. Dùng nhiều machine family tương thích, nhiều zone hoặc pool capacity khác nhau khi workload cho phép. Nếu Spot không có capacity, scheduler có thể thử lại sau, chuyển sang pool khác hoặc dùng on-demand fallback theo budget.

## 5. Savings Plans và các cam kết chi tiêu

Savings plan hoặc chương trình tương đương giảm đơn giá khi khách hàng cam kết một mức chi tiêu đủ điều kiện trong một khoảng thời gian. Provider áp dụng mức giá ưu đãi cho usage phù hợp theo quy tắc sản phẩm; phần commitment không được sử dụng có thể vẫn phải thanh toán.

### Cơ chế chung

- Tổ chức ước tính mức sử dụng nền trong kỳ.
- Chọn mức cam kết, thời hạn, phạm vi áp dụng và hình thức thanh toán.
- Usage đủ điều kiện được tính theo mức giá ưu đãi.
- Usage vượt mức cam kết thường được tính theo mức giá còn lại/on-demand hoặc chương trình khác.
- Nếu usage thấp hơn cam kết, phần chưa dùng có thể trở thành chi phí lãng phí.

Cam kết chi tiêu là nghĩa vụ tài chính; nó không nhất thiết là một reservation cấp phát instance. Cần đọc rõ commitment được đo theo USD/giờ, mức tài nguyên, loại dịch vụ hay đơn vị khác.

### Ví dụ theo provider

| Provider | Chương trình thường gặp | Điểm cần so sánh |
|---|---|---|
| AWS | Compute Savings Plans, EC2 Instance Savings Plans | Cam kết chi tiêu theo giờ; phạm vi linh hoạt khác nhau giữa loại plan; discount áp dụng cho usage đủ điều kiện chứ không tự giữ capacity |
| Microsoft Azure | Savings plan for compute | Cam kết chi tiêu theo giờ trong kỳ; phạm vi compute và eligibility phụ thuộc điều kiện chương trình |
| Google Cloud | Spend-based hoặc resource-based Committed Use Discounts (CUDs) | Cơ chế và phạm vi khác nhau theo loại CUD; kiểm tra resource family, region, project/organization và cách áp dụng discount |

Tên sản phẩm, mức discount, thời hạn và quy tắc áp dụng có thể thay đổi. Không so sánh tỷ lệ quảng cáo giữa các provider nếu chưa chuẩn hóa loại usage, region, OS/license, term, payment và cách tính amortized cost.

### Khi phù hợp

- Workload nền chạy đều qua nhiều tháng.
- Production service có baseline capacity tương đối ổn định.
- Compute fleet đã có lịch sử sử dụng đủ dài để dự báo.
- Tổ chức có khả năng quản trị cam kết tập trung và phân bổ lợi ích cho team.

### Rủi ro

- Dự báo quá cao khiến commitment không được sử dụng hết.
- Workload chuyển region/family/service và không còn đủ điều kiện áp dụng.
- Tăng trưởng hoặc giảm tải lệch xa dự báo.
- Nhiều chương trình commitment chồng lấn, khó giải thích hiệu quả.
- Nhóm mua cam kết và nhóm sử dụng không có cơ chế chia sẻ chi phí minh bạch.

## 6. Reserved Instances và committed-use discounts

Reserved Instance (RI) hoặc committed-use discount là các chương trình cam kết gắn với cấu hình, mức tài nguyên hoặc chi tiêu trong thời gian xác định. Tùy provider, reservation có thể mang ý nghĩa discount billing, capacity reservation hoặc cả hai trong một phạm vi cụ thể.

Điểm quan trọng là phải đọc định nghĩa sản phẩm thay vì suy ra từ từ “Reserved”. Trong một số cloud, reservation là cách tính discount; capacity reservation là sản phẩm riêng. Trong trường hợp khác, reservation theo zone hoặc resource cụ thể có thể đồng thời đem lại capacity assurance.

### Những chiều cần so sánh

- Region hoặc zone.
- Machine family/series và size.
- OS, tenancy, license hoặc platform.
- Thời hạn commitment.
- Payment option: upfront, partial upfront, monthly hoặc no upfront.
- Scope chia sẻ giữa account/project/subscription.
- Khả năng exchange, modify, cancel hoặc sell theo điều kiện sản phẩm.
- Cách discount áp dụng vào usage và thứ tự ưu tiên với chương trình khác.

### Ví dụ theo provider

| Provider | Discount/commitment concept | Capacity concept cần phân biệt |
|---|---|---|
| AWS | EC2 Reserved Instances và Savings Plans | Zonal Reserved Instance có thể cung cấp capacity reservation trong phạm vi đủ điều kiện; Regional RI chủ yếu là billing discount; On-Demand Capacity Reservation là cơ chế giữ capacity riêng |
| Azure | VM Reservations và Savings plan for compute | Reservation giảm chi phí cho usage phù hợp; On-demand Capacity Reservation là cơ chế đặt trước capacity riêng theo phạm vi hỗ trợ |
| Google Cloud | Committed Use Discounts | Compute Engine reservations giữ capacity cho cấu hình/zone phù hợp; cần xác minh điều kiện áp dụng CUD với reservation và tài nguyên cụ thể |

Chi tiết sản phẩm có thể thay đổi và có ngoại lệ theo resource type. Hãy kiểm tra tài liệu provider trước khi ký commitment hoặc thiết kế kế hoạch capacity.

## 7. Capacity reservation: bảo đảm khả năng cấp phát

Capacity reservation giữ một lượng tài nguyên nhất định trong phạm vi mà provider hỗ trợ, ví dụ region/zone, machine family, size, platform hoặc thuộc tính phần cứng. Mục tiêu là giảm rủi ro không thể khởi chạy instance khi cần.

Capacity reservation đặc biệt quan trọng với:

- Production workload cần scale hoặc recover trong một zone cụ thể.
- Disaster recovery yêu cầu có compute sẵn ở vùng đích.
- Workload cần GPU/accelerator hoặc machine family khan hiếm.
- Ứng dụng có thời điểm cao điểm dự đoán được.
- Hệ thống cần thay instance lỗi nhanh và không thể chờ capacity xuất hiện.

### Capacity reservation không nhất thiết giảm giá

Reservation có thể bị tính phí theo tài nguyên được giữ, kể cả khi chưa sử dụng, tùy dịch vụ và loại reservation. Nếu muốn vừa bảo đảm capacity vừa giảm đơn giá, cần kiểm tra liệu provider có cho phép áp dụng commitment discount lên usage được reservation bao phủ hay không.

### Phạm vi và tính linh hoạt

Một reservation có thể bị giới hạn bởi:

- Zone cụ thể hoặc region.
- Instance family/series, size và kiến trúc CPU.
- GPU type, accelerator hoặc local storage.
- OS/platform và tenancy.
- Số lượng instance hoặc capacity unit.
- Thời gian bắt đầu, kết thúc và khả năng điều chỉnh.

Reservation càng cụ thể càng dễ bảo đảm đúng loại capacity nhưng càng có nguy cơ không khớp khi kiến trúc thay đổi. Cần cân bằng giữa độ chắc chắn và khả năng tái sử dụng.

## 8. Phân biệt discount commitment với capacity reservation

| Câu hỏi | Savings/committed-use discount | Capacity reservation |
|---|---|---|
| Mục tiêu | Giảm giá cho usage đủ điều kiện | Giữ khả năng cấp phát capacity |
| Có cam kết tài chính? | Thường có trong kỳ commitment | Có thể có phí giữ capacity theo thời gian và mức sử dụng |
| Có bảo đảm instance sẽ khởi chạy được? | Không tự động | Trong phạm vi, cấu hình và điều kiện reservation hỗ trợ |
| Có thể không dùng hết? | Có; phần commitment chưa dùng có thể lãng phí | Có; capacity idle vẫn có thể phát sinh chi phí |
| Phạm vi | Có thể linh hoạt theo spend, family, region hoặc resource | Thường gắn với region/zone và cấu hình capacity cụ thể |
| Dùng khi | Baseline usage đủ ổn định | Cần capacity chắc chắn tại thời điểm/vị trí cụ thể |

Một tổ chức có thể mua savings plan để giảm chi phí baseline, đồng thời giữ capacity reservation cho một số zone/instance cần thiết. Phải kiểm tra thứ tự áp dụng discount và billing để tránh giả định lợi ích bị tính hai lần.

## 9. So sánh nhanh giữa AWS, Azure và Google Cloud

Bảng dưới đây là bản đồ khái niệm, không phải bảng giá hoặc cam kết về mọi SKU. Tên sản phẩm và khả năng hỗ trợ thay đổi theo dịch vụ, region và thời điểm.

| Nhu cầu | AWS | Azure | Google Cloud |
|---|---|---|---|
| Compute có thể bị thu hồi | EC2 Spot Instances | Azure Spot VMs | Spot VMs |
| Cam kết chi tiêu linh hoạt | Compute Savings Plans; EC2 Instance Savings Plans | Savings plan for compute | Spend-based CUDs tùy dịch vụ |
| Cam kết theo tài nguyên/cấu hình | EC2 Reserved Instances | VM Reservations | Resource-based CUDs tùy loại |
| Giữ capacity riêng | On-Demand Capacity Reservations; một số zonal RI có capacity benefit | On-demand Capacity Reservation | Compute Engine reservations |
| Câu hỏi về Spot | Interruption behavior, pools, allocation strategy | Eviction policy, max price, capacity | Preemption behavior, machine series và zone |
| Câu hỏi về commitment | Spend/hour, plan scope, eligible usage | Hourly commitment, eligible compute scope | CUD type, resource scope và sharing |
| Câu hỏi về reservation | AZ, instance attributes, reservation utilization | Region/zone, VM attributes, reservation scope | Zone, machine type, reservation matching |

### Nguyên tắc đối chiếu công bằng

Khi so sánh ba provider, chuẩn hóa:

1. Cùng vCPU, memory và kiến trúc CPU hoặc benchmark hiệu năng tương đương.
2. Cùng region hoặc cùng điều kiện latency/data residency.
3. Cùng OS, license, tenancy và accelerator.
4. Cùng số giờ sử dụng và profile tải.
5. Cùng term và payment option của commitment.
6. Cùng mức độ capacity assurance.
7. Cùng giả định về interruption, retry và lost work.
8. Cùng cách tính network, storage, support, tax, discount và currency.

Không lấy giá Spot thấp nhất ở một zone làm đại diện cho chi phí production toàn cầu. Cũng không so sánh giá commitment 3 năm trả trước với on-demand theo tháng mà bỏ qua giá trị thời gian của tiền và rủi ro không dùng hết.

## 10. Chọn Spot pool và đa dạng hóa capacity

Spot capacity có thể cạn ở một pool nhưng còn ở pool khác. Pool thường được phân biệt theo zone, instance type/family và các thuộc tính hạ tầng. Diversification làm tăng khả năng tìm được capacity và giảm phụ thuộc vào một cấu hình.

### Chiến lược lựa chọn

- Khai báo nhiều instance family/size tương thích với ứng dụng.
- Mở rộng zone khi yêu cầu dữ liệu và network cho phép.
- Dùng allocation strategy tối ưu capacity hoặc cân bằng giữa giá và khả năng sẵn có theo tính năng provider.
- Tránh chọn một pool duy nhất chỉ vì giá thấp nhất tại thời điểm triển khai.
- Dùng capacity fallback on-demand hoặc reserved cho phần công việc quan trọng.
- Theo dõi interruption rate và capacity launch failure theo pool.

### Fleet đa dạng không có nghĩa mọi máy đều giống nhau

Nếu các machine type khác nhau về CPU architecture, instruction set, GPU, local disk hoặc network bandwidth, image và ứng dụng phải tương thích. Có thể dùng scheduler capability constraints để chỉ chạy task phù hợp với từng pool.

### Chọn pool theo workload

Workload có thể checkpoint thường xuyên có thể chấp nhận pool interruption cao hơn. Workload gần deadline hoặc cần nhiều giờ khởi tạo nên ưu tiên pool ổn định hơn hoặc fallback. Không tối ưu theo giá mỗi giờ mà bỏ qua xác suất hoàn tất.

## 11. Tính chi phí hiệu dụng của Spot

Giá theo giờ thấp không nhất thiết đồng nghĩa chi phí trên mỗi kết quả thấp. Cần tính interruption, thời gian chạy lại, checkpoint, startup, retry và phần output bị mất.

Một mô hình đơn giản:

\[
C_{effective} = C_{compute} + C_{restart} + C_{checkpoint} + C_{storage} + C_{network}
\]

Trong đó:

- `C_compute`: chi phí thời gian compute thực tế.
- `C_restart`: chi phí phần công việc phải chạy lại sau interruption.
- `C_checkpoint`: chi phí CPU, I/O và storage để tạo checkpoint.
- `C_storage`: input, output và artifact được lưu bền vững.
- `C_network`: truyền dữ liệu, egress và đồng bộ.

Có thể tính chi phí trên mỗi task hoàn tất:

\[
C_{per\ success} = \frac{C_{effective\ total}}{N_{completed}}
\]

### Ví dụ minh họa

Giả sử một batch job cần 100 giờ compute hữu ích. On-demand có đơn giá giả định 1,00 đơn vị/giờ. Spot có giá 0,30 đơn vị/giờ, nhưng interruption khiến 15% compute đã chạy phải làm lại; checkpoint và storage tốn thêm 4 đơn vị.

- On-demand: khoảng 100 đơn vị.
- Spot compute thô: 100 × 0,30 = 30 đơn vị.
- Nếu cần chạy lại 15% công việc: thêm khoảng 15 × 0,30 = 4,5 đơn vị.
- Checkpoint/storage: 4 đơn vị.
- Spot total minh họa: 38,5 đơn vị.

Trong ví dụ này Spot vẫn rẻ hơn, nhưng nếu interruption làm mất 150 giờ hoặc có deadline penalty lớn, kết quả có thể đảo ngược. Đây là mô hình đơn giản; thực tế cần dùng dữ liệu interruption, giá theo thời điểm và hiệu năng instance.

## 12. Tính mức commitment hợp lý

Commitment nên dựa trên mức sử dụng nền có thể dự đoán, không phải peak demand hoặc mục tiêu tăng trưởng chưa chắc chắn.

### Phân tách baseline và variable load

Một workload thường có:

- **Baseline:** mức sử dụng ổn định gần như luôn cần.
- **Seasonal/known peaks:** tăng tải có thể dự báo theo lịch.
- **Burst/uncertain demand:** nhu cầu bất thường, khó dự đoán.
- **Experimental/dev:** có thể dừng hoặc thay đổi nhanh.

Có thể dùng commitment cho baseline đủ ổn định; dùng capacity reservation cho peak quan trọng cần chắc chắn cấp phát; dùng on-demand hoặc Spot cho phần biến thiên tùy khả năng gián đoạn.

### Phân tích lịch sử

Thu thập usage theo giờ/ngày và theo các dimension quan trọng: service, region, family, OS, project/account và environment. Tách usage đủ điều kiện commitment khỏi usage không đủ điều kiện. Xem cả mùa vụ, maintenance, migration, downtime và kế hoạch retire workload.

### Chọn mức cam kết

Một cách tiếp cận thận trọng:

1. Xác định mức usage tối thiểu ổn định trong phần lớn thời gian.
2. Loại phần tải tạm thời, dev/test và workload sắp ngừng.
3. Tính discount hiệu dụng theo các mức commitment khác nhau.
4. Mô phỏng trường hợp usage giảm, tăng hoặc chuyển provider/region.
5. Bắt đầu với commitment thấp hơn mức dự báo trung bình nếu bất định còn lớn.
6. Theo dõi utilization và coverage sau khi mua.
7. Chỉ tăng cam kết khi dữ liệu thực tế xác nhận baseline.

Không nên mua commitment chỉ để đạt một tỷ lệ discount cao. Mục tiêu là giảm tổng chi phí sau rủi ro, không phải tối đa hóa phần trăm tiết kiệm trên một usage giả định.

## 13. Phân biệt commitment utilization và coverage

Hai chỉ số thường bị nhầm lẫn:

- **Commitment utilization:** tỷ lệ giá trị commitment đã được sử dụng.
- **Discount coverage:** tỷ lệ usage đủ điều kiện được hưởng discount.

Ví dụ, một tổ chức có commitment 100 đơn vị/giờ và usage đủ điều kiện 80 đơn vị/giờ. Utilization là 80%; 20 đơn vị commitment không được dùng. Nếu tổng usage đủ điều kiện của tổ chức là 160 đơn vị/giờ, coverage có thể là 50% vì chỉ 80 trong 160 đơn vị nhận discount.

Theo dõi cả hai để tránh tình huống commitment utilization cao nhưng coverage thấp, hoặc coverage cao nhờ mua commitment quá lớn dẫn tới lãng phí.

### Chỉ số bổ sung

- Effective discount rate so với on-demand baseline.
- Unused commitment cost.
- Reservation utilization và idle reserved capacity.
- On-demand spend sau khi áp dụng commitment.
- Spot interruption rate và lost work.
- Cost per completed job/request.
- Forecast variance theo tháng/quý.

## 14. Chọn capacity reservation theo rủi ro thiếu capacity

Capacity reservation có giá trị khi chi phí không có máy đúng lúc lớn hơn chi phí giữ capacity. Không phải mọi workload đều cần reservation.

### Định lượng rủi ro

Đánh giá:

- Xác suất cần scale hoặc recover trong một zone/region.
- Tác động doanh thu/SLO nếu không cấp được máy.
- Thời gian chờ capacity thay thế.
- Khả năng dùng machine family/zone khác.
- Mức độ cần GPU, accelerator hoặc cấu hình đặc thù.
- Chi phí reservation khi capacity không được dùng.

### Khi nên đặt trước

- Sự kiện có tải lớn và thời gian xác định.
- DR cần khởi chạy số lượng VM cụ thể trong RTO.
- Workload cần GPU hiếm hoặc cấu hình đặc biệt.
- Production fleet có yêu cầu capacity tối thiểu theo zone.
- Hệ thống cần thay node nhanh sau sự cố.

### Khi không nên đặt trước quá nhiều

- Workload có thể chuyển zone/family dễ dàng.
- Tải biến động lớn và chưa có lịch sử đủ dài.
- Tài nguyên chỉ dùng vài giờ mỗi tháng.
- Kiến trúc sắp thay đổi hoặc migration sắp hoàn tất.
- Có thể dùng autoscaling/on-demand mà rủi ro thiếu capacity thấp.

### Reservation không thay thế quota

Capacity reservation và quota là hai cơ chế khác nhau. Quota giới hạn mức sử dụng được phép; reservation giữ capacity trong phạm vi nhất định. Một reservation không nhất thiết tự nâng quota hoặc bảo đảm mọi ràng buộc IAM, network, image, license và dependency đều sẵn sàng. Kiểm tra quota và quyền trước khi diễn tập scale/DR.

## 15. Kết hợp Spot, commitment và capacity reservation

Một chiến lược hiệu quả thường dùng nhiều loại capacity theo mức quan trọng:

| Lớp workload | Lựa chọn có thể phù hợp | Lý do |
|---|---|---|
| Control plane và dịch vụ cốt lõi | On-demand hoặc capacity reservation | Cần khả năng phục hồi và tính sẵn sàng |
| Baseline production ổn định | Savings/committed-use discount | Usage dự đoán được, tối ưu đơn giá |
| Peak quan trọng theo lịch | Capacity reservation hoặc commitment phù hợp | Cần capacity tại thời điểm cụ thể |
| Batch có checkpoint | Spot/Preemptible | Chấp nhận interruption để giảm giá |
| Burst không dự đoán | On-demand hoặc pool linh hoạt | Tránh cam kết quá mức |
| Dev/test | On-demand ngắn hạn hoặc Spot | Có thể dừng và tạo lại |
| DR capacity | Reservation hoặc kế hoạch capacity đã kiểm thử | Phải đáp ứng RTO tại region/zone đích |

### Ví dụ phân tầng

Một nền tảng xử lý video có baseline 20 worker chạy liên tục, thêm 0-80 worker khi có chiến dịch. Có thể:

- Đặt commitment cho phần baseline 20 worker nếu cấu hình/usage đủ ổn định.
- Dùng Spot cho phần batch render có checkpoint.
- Dùng on-demand fallback cho job gần deadline.
- Giữ capacity reservation cho một nhóm GPU cần thiết ở zone cụ thể nếu rủi ro không có GPU quá lớn.
- Giới hạn concurrency để storage và database không bị quá tải khi scale-out.

Không cam kết toàn bộ peak 100 worker nếu phần lớn thời gian không cần tới mức đó.

## 16. Tác động của term, payment và khả năng thay đổi

Cam kết dài hạn thường có mức discount hấp dẫn hơn nhưng làm tăng rủi ro dự báo. Payment upfront có thể giảm đơn giá hoặc tổng chi phí danh nghĩa nhưng yêu cầu dòng tiền trước; no-upfront giảm khoản trả trước nhưng không loại bỏ nghĩa vụ commitment.

Trước khi chọn term/payment, kiểm tra:

- Thời hạn 1 năm, 3 năm hoặc lựa chọn khác được cung cấp.
- Upfront/partial/no-upfront và cách ghi nhận cash flow.
- Khả năng đổi family, size, region hoặc scope.
- Có thể hủy, bán lại hoặc chuyển commitment không.
- Điều kiện khi account/project được chuyển tổ chức.
- Hệ quả nếu workload ngừng hoặc chuyển sang kiến trúc khác.
- Cách discount được áp dụng khi nhiều commitment cùng đủ điều kiện.

Không coi “có thể modify” là quyền thay đổi tự do. Mỗi provider có quy tắc và giới hạn cụ thể.

## 17. Tính tổng chi phí đa cloud (TCO)

Đơn giá compute không phải toàn bộ chi phí. Một lựa chọn Spot hoặc commitment có thể kéo theo chi phí storage, network, license, monitoring và vận hành khác nhau.

### Thành phần chi phí

- Compute usage và commitment payment.
- Capacity reservation hoặc idle reserved capacity.
- Persistent disk, snapshot và object storage.
- Network egress, inter-region transfer và private connectivity.
- License, OS và phần mềm thương mại.
- Logging, metrics, tracing và backup.
- Retry, checkpoint, lost work và reprocessing.
- Engineering time để duy trì fleet đa dạng và xử lý interruption.
- Migration, data gravity và chi phí vận hành đa cloud.

### Công thức tổng quát

\[
TCO = C_{compute} + C_{commitment} + C_{reservation} + C_{storage} + C_{network} + C_{license} + C_{operations}
\]

Khi dùng commitment, không cộng cả giá on-demand giả định và phí commitment cho cùng một usage. Hãy dùng billing export hoặc calculator theo đúng semantics provider để tránh double count.

### Cost per successful work unit

Đối với batch/worker, so sánh chi phí trên mỗi job hoàn tất hoặc mỗi triệu bản ghi xử lý. Đối với API, so sánh cost per successful request ở cùng SLO. Cách này đưa interruption, retry và performance vào cùng một thước đo.

## 18. Ví dụ so sánh ba chiến lược

Giả sử một workload cần 1.000 vCPU-hour mỗi tuần, có baseline ổn định 500 vCPU-hour và 500 vCPU-hour còn lại biến động. Các con số giá dưới đây chỉ là giả định minh họa.

| Chiến lược | Cách triển khai | Điểm mạnh | Rủi ro |
|---|---|---|---|
| 100% on-demand | Trả theo toàn bộ usage | Linh hoạt, đơn giản | Đơn giá cao |
| Commitment cho 500 + on-demand phần còn lại | Cam kết baseline, phần biến động trả theo usage | Discount đúng phần ổn định | Usage baseline giảm có thể lãng phí commitment |
| Commitment cho 500 + Spot cho phần biến động | Baseline được discount, batch chạy Spot | Có thể giảm chi phí hơn | Cần checkpoint, retry và fallback |
| Commitment + reservation cho peak bắt buộc | Discount baseline, giữ capacity cho peak quan trọng | Tăng độ chắc chắn capacity | Reservation idle có thể phát sinh phí |

Trước khi chọn, mô phỏng ít nhất ba kịch bản: usage giảm 30%, usage tăng 30% và interruption/thiếu capacity kéo dài. So sánh tổng chi phí và xác suất hoàn thành SLO, không chỉ giá theo giờ.

## 19. Governance cho commitment và reservation

Commitment là quyết định tài chính nhiều kỳ; reservation là quyết định capacity. Cần có owner, approval và review cadence riêng.

### Vai trò

| Vai trò | Trách nhiệm |
|---|---|
| Service owner | Dự báo workload, xác nhận baseline và SLO |
| Platform/cloud team | Phân tích instance family, region, capacity và kỹ thuật áp dụng |
| FinOps/Finance | Mô hình hóa discount, commitment utilization, budget và cash flow |
| Procurement | Rà soát term, hợp đồng và điều khoản thương mại |
| SRE/Operations | Xác nhận interruption tolerance, fallback và DR capacity |
| Architecture review | Xem xét portability, lock-in và kế hoạch migration |

### Quy trình mua commitment

1. Thu thập usage lịch sử đủ đại diện cho mùa vụ.
2. Chuẩn hóa usage theo region, family, OS/license và account scope.
3. Xác định baseline thực sự ổn định.
4. Mô phỏng nhiều mức commitment và payment option.
5. Tính unused commitment risk khi workload giảm.
6. Xác định owner ngân sách và cơ chế chia sẻ discount.
7. Phê duyệt theo hạn mức tài chính.
8. Theo dõi utilization/coverage và điều chỉnh ở kỳ review tiếp theo.

### Quy trình đặt trước capacity

1. Xác định workload, zone, machine type và thời điểm cần capacity.
2. Xác minh quota, eligibility, network và image.
3. Định lượng chi phí capacity idle so với rủi ro thiếu máy.
4. Đặt reservation trong phạm vi nhỏ nhất đáp ứng RTO/SLO.
5. Kiểm tra utilization và khả năng scale/attach thực tế.
6. Diễn tập scale-out hoặc DR trong zone đã đặt.
7. Giảm reservation khi nhu cầu hoặc kiến trúc thay đổi.

## 20. Các chỉ số vận hành cần theo dõi

### Spot/Preemptible

- Interruption rate theo pool/zone/family.
- Launch failure hoặc capacity unavailable rate.
- Thời gian từ notice tới termination nếu có notice.
- Lost compute time và số lần resume.
- Retry success rate và task completion time.
- Tỷ lệ fallback sang on-demand.
- Cost per completed task.

### Commitment

- Commitment utilization.
- Discount coverage.
- Unused commitment cost.
- Effective discount rate so với baseline.
- On-demand spend còn lại.
- Forecast variance và mức sử dụng theo mùa vụ.

### Capacity reservation

- Reserved capacity utilization.
- Idle reservation cost.
- Capacity launch success trong phạm vi reservation.
- Quota headroom.
- Số lần reservation được dùng trong scale/DR test.
- Mismatch giữa reservation attributes và workload thực tế.

### Dashboard cần phân biệt

Không gộp Spot savings, commitment savings và reservation utilization thành một con số duy nhất. Một dashboard tốt hiển thị riêng:

- Chi phí on-demand tương đương.
- Chi phí thực tế sau discount.
- Chi phí commitment chưa sử dụng.
- Chi phí reservation idle.
- Spot savings so với baseline và chi phí reprocessing.
- Tác động tới SLO và completion rate.

## 21. Troubleshooting và quyết định điều chỉnh

| Triệu chứng | Nguyên nhân có thể | Hành động |
|---|---|---|
| Spot thường xuyên không khởi chạy | Pool/zone thiếu capacity hoặc cấu hình quá hẹp | Mở rộng pool tương thích, zone hoặc dùng fallback |
| Spot interruption tăng | Capacity pressure thay đổi hoặc tập trung một pool | Diversify, đổi allocation strategy và tăng checkpoint resilience |
| Spot rẻ nhưng cost/job cao | Rework, retry hoặc startup overhead lớn | Đo lost work, tăng checkpoint phù hợp hoặc chuyển job quan trọng sang on-demand |
| Commitment utilization thấp | Mua cao hơn baseline hoặc workload đã giảm | Xem điều kiện modify/share và giảm commitment tương lai |
| Discount coverage thấp | Commitment scope không khớp usage hoặc commitment quá nhỏ | Kiểm tra eligibility, region/family và sharing scope |
| Reservation idle kéo dài | Đặt sai zone/size hoặc peak đã thay đổi | Đánh giá điều chỉnh/hủy nếu điều khoản cho phép |
| Reservation có nhưng launch vẫn lỗi | Quota, attribute mismatch, IAM, image hoặc dependency | Kiểm tra mọi điều kiện ngoài reservation |
| Chi phí đa cloud không so sánh được | Currency, tax, license, term hoặc amortization khác nhau | Chuẩn hóa cost basis và workload benchmark |
| DR không khởi chạy được | Thiếu quota, reservation hoặc dependency tại vùng đích | Diễn tập định kỳ và kiểm tra capacity plan |
| Team tranh luận về discount allocation | Owner và phương pháp chia sẻ không rõ | Thiết lập showback/chargeback minh bạch |

### Khi nào chuyển workload khỏi Spot?

Chuyển một phần hoặc toàn bộ workload sang on-demand/capacity reservation khi:

- Interruption làm vi phạm deadline hoặc SLO.
- Chi phí reprocessing khiến cost per success không còn lợi thế.
- Workload chưa có checkpoint hoặc idempotency đủ an toàn.
- Capacity pool không ổn định trong khung thời gian cần thiết.
- Phần công việc còn lại có giá trị cao và gần deadline.

Không nhất thiết bỏ toàn bộ Spot. Có thể chỉ chuyển phần task quan trọng hoặc phần còn lại sang capacity ổn định hơn.

## 22. Những sai lầm thường gặp

- **Coi Spot là capacity rẻ luôn sẵn có:** giá thấp không đồng nghĩa khả năng khởi chạy được bảo đảm.
- **Dùng Spot cho stateful primary không có failover:** interruption có thể gây gián đoạn hoặc mất dữ liệu.
- **Coi savings plan là capacity reservation:** discount không tự giữ instance ở zone cần thiết.
- **Coi mọi Reserved Instance đều giữ capacity:** semantics khác nhau theo provider và loại reservation.
- **Cam kết theo peak:** phần usage không tồn tại vẫn có thể làm lãng phí commitment.
- **Chỉ xem phần trăm discount:** bỏ qua term, upfront, usage eligibility và unused commitment.
- **Đặt capacity quá cụ thể:** workload đổi family/zone khiến reservation không còn phù hợp.
- **Bỏ qua quota:** reservation không thay thế mọi giới hạn cấp phát.
- **Không đa dạng hóa Spot pool:** phụ thuộc một zone/family làm tăng rủi ro interruption.
- **So sánh giá không cùng điều kiện:** khác region, OS, license, term hoặc hiệu năng làm kết luận sai.
- **Không tính lost work và network:** giá compute thấp nhưng tổng chi phí có thể cao.
- **Không có owner cho commitment:** không ai theo dõi utilization hoặc chịu trách nhiệm ngân sách.

## 23. Checklist chọn tài nguyên có thể bị thu hồi, commitment và capacity

**Spot/Preemptible:**

- [ ] Workload có thể checkpoint, retry và xử lý idempotent.
- [ ] Có durable storage tách khỏi instance.
- [ ] Có interruption handling và không phụ thuộc hoàn toàn vào notice.
- [ ] Đã đa dạng hóa pool/zone/family phù hợp.
- [ ] Có on-demand fallback cho task quan trọng.
- [ ] Đo interruption, lost work và cost per success.

**Savings/commitment:**

- [ ] Baseline được xác định từ usage lịch sử đủ đại diện.
- [ ] Scope region/family/service/OS và eligibility đã được kiểm tra.
- [ ] Đã mô phỏng usage giảm, tăng và migration.
- [ ] Đã tính term, upfront/payment và unused commitment risk.
- [ ] Có owner ngân sách và cơ chế phân bổ discount.
- [ ] Theo dõi utilization, coverage và effective savings.

**Capacity reservation:**

- [ ] Có yêu cầu capacity cụ thể gắn với SLO/RTO.
- [ ] Zone/region, machine type, size và thuộc tính phần cứng khớp workload.
- [ ] Quota, IAM, image, network và dependency đã sẵn sàng.
- [ ] Đã tính chi phí idle và khả năng thay đổi reservation.
- [ ] Có diễn tập scale-out/DR trong phạm vi reservation.
- [ ] Theo dõi utilization và rà soát khi kiến trúc thay đổi.

**So sánh đa cloud:**

- [ ] Cùng workload benchmark và hiệu năng tương đương.
- [ ] Cùng region/latency và data residency assumptions.
- [ ] Cùng OS/license, term, payment và cost basis.
- [ ] Tính network, storage, support, retry và operations.
- [ ] Tách discount khỏi capacity guarantee.
- [ ] Có quyết định placement và fallback được ghi nhận.

## Kết luận

Spot/Preemptible phù hợp với workload có thể bị gián đoạn, checkpoint và retry; savings plan hoặc committed-use discount phù hợp với baseline sử dụng ổn định cần giảm đơn giá; capacity reservation phù hợp khi tổ chức cần bảo đảm khả năng cấp phát ở một phạm vi cụ thể. Ba lựa chọn có thể kết hợp nhưng không thay thế nhau. Khi so sánh AWS, Azure và Google Cloud, hãy chuẩn hóa cấu hình, region, term, payment, eligibility và mức bảo đảm capacity; sau đó tính cả interruption, unused commitment, reservation idle, network và vận hành. Một chiến lược tốt thường cam kết phần baseline có thể dự báo, giữ capacity cho workload thực sự cần chắc chắn và dùng Spot cho phần công việc có khả năng phục hồi, đồng thời theo dõi cost per successful work unit để kiểm chứng lợi ích.

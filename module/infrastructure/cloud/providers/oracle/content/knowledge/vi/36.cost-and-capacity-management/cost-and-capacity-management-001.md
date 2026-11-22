# Đọc mô hình giá OCI theo compute, storage và network

Trong chương **Chi phí và quản lý năng lực** của Oracle Cloud Infrastructure (OCI), đọc mô hình giá là bước chuyển từ một bản vẽ hạ tầng sang dự toán có thể giải thích được. Một ứng dụng Java chạy trên hai máy ảo không chỉ phát sinh “tiền hai máy chủ”: còn có RAM, boot volume, dữ liệu, bản sao lưu và đường truyền phục vụ người dùng.

Bài học tập trung vào ba nhóm **Compute, Storage và Network** trong phạm vi CLOUD_PROVIDERS_ORACLE. Mục tiêu là xác định đúng đại lượng tính phí, dựng công thức dự toán và nhận ra tác động của cấu hình, thời gian sử dụng, tăng trưởng dữ liệu và tính sẵn sàng.

> Các đơn giá bằng USD trong ví dụ đều là **số giả định phục vụ học tập**, không phải báo giá OCI. Quy tắc dịch vụ được đối chiếu với tài liệu Oracle ngày 21/11/2026. Khi lập dự toán thật, dùng SKU, đơn vị, vùng, loại tiền và rate card áp dụng cho tài khoản tại thời điểm tính.

## 1. Bắt đầu từ đại lượng được tính phí

Một dòng tài nguyên trên sơ đồ có thể tạo nhiều dòng tính phí. Với từng dòng, hãy ghi lại:

| Thành phần cần đọc | Ý nghĩa | Ví dụ đầu vào cần ghi |
| --- | --- | --- |
| Service và SKU | Dịch vụ, mã sản phẩm cụ thể | Compute Standard của đúng họ shape |
| Metric hoặc unit | Đại lượng dùng để đo mức sử dụng | OCPU-hour, GB-hour, GB-month |
| Quantity | Lượng sử dụng theo chính đơn vị đó | 2.880 OCPU-hour |
| Unit price | Giá cho một đơn vị | USD/OCPU-hour |
| Pricing rule | Bậc giá, phần miễn phí, mức tối thiểu, cách chia theo thời gian | Có tách phí RAM không? |
| Phạm vi áp dụng | Vùng, kỳ tính, subscription và điều kiện tài khoản | Cùng tháng và cùng loại tiền |
| Thành tiền | Quantity nhân giá sau khi áp dụng quy tắc | Chi phí của một SKU trong kỳ |

Công thức khởi đầu:

```text
Chi phí một dòng = lượng sử dụng có tính phí × đơn giá tương ứng

Chi phí hạ tầng =
    tổng các dòng Compute
  + tổng các dòng Storage
  + tổng các dòng Network
  + các dịch vụ bổ sung trong kiến trúc
```

Không cộng trực tiếp các quantity khác đơn vị. “1.000 OCPU-hour + 500 GB-month” không phải một tổng mức sử dụng có ý nghĩa; phải đổi từng dòng thành tiền trước.

### 1.1. Phân biệt giá niêm yết với giá áp dụng

OCI có mô hình Pay As You Go và Annual Universal Credits. Mức sử dụng vẫn được đo theo metric của dịch vụ; giá áp dụng và nghĩa vụ thanh toán phụ thuộc thỏa thuận. BYOL là lựa chọn cho một số dịch vụ đủ điều kiện, cần được tách khỏi phương án có kèm giấy phép. [Nguồn: Billing Models Offered](https://docs.oracle.com/en/cloud/get-started/subscriptions-cloud/ocpib/billing-models-offered.html).

Một bảng dự toán nên có cột “nguồn giá” và “ngày lấy giá”. Nếu dùng giá trong hợp đồng cho Compute nhưng dùng giá niêm yết cho Network, phải thể hiện rõ; nếu không, người đọc dễ tưởng toàn bộ bảng đã được chiết khấu giống nhau.

Đối với hợp đồng cam kết, cần xem riêng lượng dịch vụ đã tiêu thụ và số tiền cam kết phải thanh toán. Không suy ra rằng tháng dùng ít thì mọi nghĩa vụ thanh toán đều tự giảm theo.

### 1.2. Chuẩn hóa thời gian và dung lượng

Dùng nhất quán một kỳ dự toán:

- Tháng 30 ngày có 720 giờ; tháng 31 ngày có 744 giờ.
- 730 giờ có thể dùng làm giả định trung bình để lập kế hoạch, nhưng phải ghi rõ.
- Máy chỉ phục vụ 10 giờ/ngày trong 22 ngày làm việc có 220 giờ hoạt động theo lịch dự kiến.
- GB, GiB, TB và TiB cần được đối chiếu với định nghĩa metric của SKU, không tự đổi theo thói quen.

“GB-month” là dung lượng tích lũy theo thời gian. Với một tài nguyên giữ dung lượng không đổi trong nửa kỳ, mô hình dự toán theo tỷ lệ thời gian có thể dùng một nửa dung lượng-tháng, nếu quy tắc dịch vụ cho phép.

Không lấy 220 giờ chạy Compute để áp luôn cho boot volume còn tồn tại cả tháng.

## 2. Compute: trả tiền cho cấu hình nào và trong bao lâu?

### 2.1. Đọc OCPU và RAM thành hai dòng riêng

Với các Standard Flex tương ứng, bảng giá liệt kê OCPU theo giờ và bộ nhớ theo GB-giờ. Một số SKU khác dùng GPU-hour hoặc metric riêng; cần đọc đúng dòng sản phẩm. [Nguồn: Oracle Cloud Price List, Compute](https://www.oracle.com/cloud/price-list/#pricing-compute).

Mô hình cho một nhóm máy đồng nhất:

```text
C_compute = N × H × (O × P_ocpu + M × P_memory)

N        : số instance
H        : số giờ được tính phí của mỗi instance
O        : số OCPU cấp phát cho mỗi instance
M        : bộ nhớ GB cấp phát cho mỗi instance
P_ocpu   : USD/OCPU-hour
P_memory : USD/GB-hour
```

Ví dụ giả định, một máy có 2 OCPU và 16 GB RAM:

```text
P_ocpu   = 0,040 USD/OCPU-hour
P_memory = 0,003 USD/GB-hour

Chi phí mỗi giờ = 2 × 0,040 + 16 × 0,003
                = 0,128 USD

Chạy 720 giờ    = 720 × 0,128
                = 92,16 USD
```

Nếu chỉ nhân 2 OCPU với giá OCPU, bạn mới tính được 57,60 USD và bỏ sót 34,56 USD RAM.

Phần trăm CPU quan sát được giúp đánh giá sử dụng tài nguyên. Trong mô hình cấp phát này, một máy 2 OCPU chỉ dùng trung bình 15% CPU không vì thế mà chỉ bị tính 15% tiền OCPU. Muốn giảm chi phí cần thay đổi lượng tài nguyên hoặc thời gian được tính phí, trong khi vẫn đáp ứng tải.

### 2.2. OCPU không luôn bằng một vCPU

Theo tài liệu Compute Shapes:

| Nhóm kiến trúc | Quan hệ cần chú ý |
| --- | --- |
| x86 thông dụng | 1 OCPU tương ứng 2 vCPU |
| Ampere A1 | 1 OCPU tương ứng 1 core, 1 vCPU |
| Arm A2 và A4 | 1 OCPU tương ứng 2 core, 2 vCPU |

Đối chiếu đúng họ shape; không dùng quy tắc của A1 cho mọi máy Arm. [Nguồn: Compute Shapes](https://docs.oracle.com/en-us/iaas/Content/Compute/References/computeshapes.htm).

Khi so sánh hai phương án, cần giữ cùng mục tiêu hiệu năng. Tên “4 CPU” có thể đang chỉ bốn vCPU hoặc bốn OCPU. Với ứng dụng Java, hãy ghi thêm kết quả tải thử, bộ nhớ cần cho JVM, độ trễ và số yêu cầu xử lý được. Cấu hình có ít tiền mỗi OCPU hơn chưa chắc có ít tiền mỗi giao dịch hơn.

Ví dụ tự xây dựng:

```text
Phương án A: 0,128 USD/giờ, xử lý được 200 yêu cầu/giây
Phương án B: 0,100 USD/giờ, xử lý được 120 yêu cầu/giây

Mục tiêu: ít nhất 180 yêu cầu/giây, cùng yêu cầu độ trễ
```

Phương án B rẻ hơn theo máy, nhưng chưa đạt mục tiêu với một máy. Quyết định cần dựa trên cấu hình hoàn chỉnh đủ tải.

### 2.3. Giá theo giờ và độ nhỏ của chu kỳ đo

OCI công bố tính Compute theo giây, với mức tối thiểu một phút cho VM và một giờ cho bare metal, sau đó theo giây. Phải kiểm tra điều khoản của sản phẩm cụ thể khi đưa vào dự toán. [Nguồn: Per-second billing for Compute instances](https://docs.oracle.com/en-us/iaas/releasenotes/changes/20facdce-34bf-4648-a0a7-de5db73657ce/index.htm).

Vì vậy, đơn vị “USD/giờ” không tự có nghĩa là mọi phiên chạy đều bị làm tròn thành một giờ.

Nếu cấu hình hoặc số lượng máy thay đổi, chia thành từng khoảng:

```text
C_compute = Σ [N_i × H_i × (O_i × P_ocpu_i + M_i × P_memory_i)]
```

Ví dụ hệ thống có hai máy nền chạy cả tháng và thêm ba máy trong 40 giờ cao điểm:

```text
Tổng instance-hour = 2 × 720 + 3 × 40
                   = 1.560 instance-hour
```

Không lấy năm máy nhân 720 giờ nếu ba máy bổ sung chỉ thực sự được tính phí 40 giờ mỗi máy. Ngược lại, không bỏ qua thời gian khởi động, chờ việc hoặc phục vụ sau cao điểm nếu những khoảng đó vẫn được tính phí.

### 2.4. Stop, shutdown và terminate ảnh hưởng khác nhau

Quy tắc phụ thuộc shape:

| Tình huống | Điểm cần đọc trên OCI |
| --- | --- |
| Standard được stop bằng Console/API | Phí Compute tạm dừng |
| Dense I/O, HPC và nhiều shape GPU được stop | Có thể tiếp tục tính phí |
| VM thuộc dòng GPU A10 được stop | Là trường hợp tạm dừng tính phí được tài liệu nêu |
| Chỉ shutdown bên trong hệ điều hành | Không thay thế thao tác stop trên OCI |

Kiểm tra đúng shape trước khi dự toán tiết kiệm. [Nguồn: Resource Billing for Stopped Instances](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/resource-billing-stopped-instances.htm).

Đối với kế hoạch tắt môi trường development ngoài giờ, hãy tách hai câu hỏi:

1. Khoảng thời gian nào được loại khỏi phí Compute?
2. Những tài nguyên nào vẫn được giữ lại và tiếp tục có chi phí?

Boot volume, dữ liệu, bản sao lưu và các dịch vụ còn tồn tại phải được tính độc lập. Terminate một instance cũng không nên được diễn giải thành “mọi tài nguyên liên quan chắc chắn đã bị xóa”.

## 3. Storage: dung lượng, hiệu năng và hoạt động truy cập

Storage không có một mô hình giá duy nhất. Cần phân biệt ổ đĩa cấp cho máy, kho object và bản sao phục hồi.

### 3.1. Block Volume và boot volume: dung lượng cấp phát

Block Volume được đo theo dung lượng đã cấp phát và lựa chọn hiệu năng. Boot volume tính theo giá Block Volume, ngoài giá instance. Backup volume nằm trong Object Storage và được đo theo dung lượng lưu trữ mà backup tiêu thụ. [Nguồn: Block Volumes FAQ, Billing](https://www.oracle.com/cloud/storage/block-volumes/faq/).

Ví dụ, một volume đã cấp phát 500 GB chỉ chứa 80 GB dữ liệu vẫn cần được dự toán theo 500 GB cấp phát. Xóa file trong hệ điều hành không đồng nghĩa dung lượng volume được cấp phát giảm theo.

Một danh mục storage nên ghi riêng:

| Tài nguyên | Đầu vào cần lấy | Câu hỏi chống bỏ sót |
| --- | --- | --- |
| Boot volume | Dung lượng, hiệu năng, thời gian tồn tại | Đã tính cho từng instance chưa? |
| Data block volume | Dung lượng cấp phát và VPUs/GB | Đã tính phần dung lượng trống được cấp chưa? |
| Backup | Dung lượng backup thực tế, chính sách giữ bản | Đã tính lịch sử phục hồi chưa? |
| Bản sao ở vùng khác | Dung lượng tại đích và luồng sao chép | Đã tính cả lưu trữ đích và network chưa? |

### 3.2. Tách tiền dung lượng và tiền hiệu năng

Đối với dòng giá Block Volume có phần hiệu năng VPU, dùng mô hình:

```text
C_block = S × P_capacity × T
        + S × V × P_vpu × T

S          : dung lượng GB cấp phát
V          : mức VPU/GB được cấu hình
P_capacity : USD/GB-month
P_vpu      : giá cho một VPU trong một tháng, theo cách chuẩn hóa dưới đây
T          : tỷ lệ thời gian của kỳ tháng
```

Để kiểm tra thứ nguyên:

```text
S GB × V (VPU/GB) = tổng VPU

Tổng VPU × giá USD/(VPU-month) × T month = USD
```

Cách viết này giúp tránh nhân mức VPU hai lần. Nếu công cụ báo giá đã cho sẵn **phụ phí của cả mức hiệu năng trên mỗi GB-tháng**, dùng trực tiếp:

```text
C_block = S × (P_capacity + P_performance_level) × T
```

Ví dụ giả định:

```text
S = 500 GB
V = 10 VPU/GB
P_capacity = 0,020 USD/GB-month
P_vpu = 0,001 USD/(VPU-month)
T = 1

Dung lượng = 500 × 0,020             = 10,00 USD
Hiệu năng  = 500 × 10 × 0,001        =  5,00 USD
Tổng       = 500 × (0,020 + 0,010)   = 15,00 USD
```

Nếu đã dùng phụ phí 0,010 USD/GB-month của mức hiệu năng trong ví dụ, không nhân thêm 10 lần nữa.

Bảng giá OCI nêu Block Volume được chia phí theo thời gian, tối thiểu một phút và sau đó theo giây trong tháng lịch. Dùng số giây của đúng tháng khi cần dự toán chi tiết. [Nguồn: Oracle Cloud Price List, Storage](https://www.oracle.com/cloud/price-list/#pricing-storage).

### 3.3. Mua thêm VPU phải đi cùng mục tiêu hiệu năng

Hiệu năng thực tế còn chịu giới hạn của volume, instance và phương thức kết nối. Cần đọc các giới hạn IOPS và throughput của cấu hình sử dụng. [Nguồn: Block Volume Performance](https://docs.oracle.com/en-us/iaas/Content/Block/Concepts/blockvolumeperformance.htm).

Ví dụ suy luận: ứng dụng cần 20.000 IOPS, nhưng instance hoặc đường kết nối đang giới hạn thấp hơn mục tiêu. Chỉ tăng hiệu năng volume có thể làm tăng dự toán mà không giải quyết được nút thắt.

Trong bảng dự toán, nên thêm cột “lý do chọn mức hiệu năng”: số đo IOPS, throughput hoặc yêu cầu tải thử. Nhờ đó, thay đổi VPU có thể được đánh giá cùng lợi ích thực tế.

### 3.4. Object Storage: dung lượng theo thời gian và số request

Object Storage đo dung lượng bằng byte-hour tích lũy theo tháng, số request và dữ liệu đi ra Internet; request DELETE được tài liệu liệt kê là miễn phí. [Nguồn: Object Storage FAQ](https://www.oracle.com/cloud/storage/object-storage/faq/).

Mô hình dự toán mở rộng:

```text
C_object =
    C_capacity
  + C_requests
  + C_retrieval_nếu_áp_dụng
  + C_early_deletion_nếu_áp_dụng
  + C_restored_copy_nếu_áp_dụng
  + C_data_transfer_nếu_áp_dụng
```

Chỉ đưa network vào một nơi trong bảng tổng để tránh tính trùng.

Dung lượng cần là giá trị có xét thời gian, không chỉ là số nhìn thấy ở cuối tháng:

```text
Giả định một tháng gồm hai nửa bằng nhau:

Nửa đầu: 1.000 GB
Nửa sau: 3.000 GB

Dung lượng-tháng = 1.000 × 0,5 + 3.000 × 0,5
                  = 2.000 GB-month
```

Dùng 3.000 GB cho cả tháng sẽ dự toán cao hơn mô hình này; chỉ dùng 1.000 GB lại bỏ sót tăng trưởng.

Request cũng cần đúng đơn vị báo giá. Ví dụ giá giả định là 0,004 USD cho 10.000 request và có 2.000.000 request có tính phí:

```text
Số đơn vị giá = 2.000.000 / 10.000 = 200
C_requests   = 200 × 0,004 = 0,80 USD
```

Một trang ứng dụng có thể tạo nhiều lần gọi object. Không đồng nhất số người dùng, số lượt mở trang và số API request đến kho lưu trữ.

### 3.5. Tier rẻ hơn cần được đọc cùng điều kiện truy cập

| Tier | Điều kiện quan trọng |
| --- | --- |
| Standard | Dữ liệu thường xuyên truy cập, không có thời gian lưu tối thiểu như hai tier dưới |
| Infrequent Access | Tối thiểu 31 ngày; có phí retrieval |
| Archive | Tối thiểu 90 ngày; cần restore trước khi đọc và tính thêm lưu trữ bản phục hồi theo quy tắc |

Xóa hoặc ghi đè làm dữ liệu bị loại bỏ sớm có thể phát sinh phần phí thời gian lưu tối thiểu còn thiếu. [Nguồn: Object Storage Storage Tiers](https://docs.oracle.com/en-us/iaas/Content/Object/Concepts/understandingstoragetiers.htm).

Khi chọn tier, cần mô hình hóa cả chu kỳ sống:

```text
Chi phí chu kỳ dữ liệu =
    lưu trữ trong thời gian giữ dữ liệu
  + request thao tác
  + retrieval/restore và bản phục hồi nếu có
  + truyền dữ liệu
  + phần phí lưu tối thiểu còn thiếu nếu có
```

Ví dụ suy luận: log chỉ giữ bảy ngày nhưng được đưa ngay vào tier có thời gian lưu tối thiểu dài hơn nhiều. Giá mỗi GB-tháng thấp chưa đủ chứng minh phương án đó tiết kiệm.

Backup cũng cần số đo dung lượng thực tế và tỷ lệ thay đổi dữ liệu. Không mặc định “backup luôn miễn phí”, cũng không mặc định mỗi bản backup chiếm nguyên dung lượng volume nguồn.

## 4. Network: đọc theo đường đi của dữ liệu

### 4.1. Đừng gộp mọi lưu lượng thành một con số

Hãy lập bảng các luồng trước khi chọn đơn giá:

| Luồng | Cần phân loại |
| --- | --- |
| Người dùng gửi dữ liệu vào OCI | Inbound |
| Ứng dụng gửi phản hồi hoặc file cho người dùng ngoài OCI | Outbound Internet |
| Ứng dụng và dịch vụ trong cùng region trao đổi dữ liệu | Intra-region |
| Sao chép dữ liệu sang region khác | Cross-region |
| Hệ thống tại doanh nghiệp kết nối OCI | Internet/VPN hoặc FastConnect |
| Lưu lượng qua Load Balancer | Phí dịch vụ cân bằng tải và phần truyền dữ liệu liên quan |

Oracle công bố không thu phí di chuyển dữ liệu trong cùng region, kể cả giữa các availability domain, và 10 TB/tháng đầu của egress Internet miễn phí. Phải xác định đúng điều kiện và phạm vi áp dụng ưu đãi trước khi trừ. [Nguồn: Virtual Cloud Network Pricing](https://www.oracle.com/cloud/networking/virtual-cloud-network/pricing/).

Dòng inbound được niêm yết miễn phí; đơn giá outbound vượt ngưỡng có phân nhóm theo nơi xuất phát. Không chọn giá theo nơi người xem đang đứng. [Nguồn: Oracle Cloud Price List, Networking](https://www.oracle.com/cloud/price-list/#pricing-networking).

Lưu lượng intra-region không có phí truyền dữ liệu không có nghĩa mọi dịch vụ xử lý luồng đó đều miễn phí.

### 4.2. Tách GB truyền dữ liệu khỏi Mbps băng thông

- **GB trong kỳ**: lượng dữ liệu đã truyền, phù hợp với mô hình egress theo dung lượng.
- **Mbps hoặc Gbps**: tốc độ, phù hợp với mô tả năng lực đường truyền hoặc metric băng thông dịch vụ.
- **Mbps-hour**: băng thông được tính phí trong một khoảng thời gian; không phải GB.

Ví dụ theo hệ thập phân, một đường truyền thực sự giữ 100 Mbps trong một giờ mang lượng dữ liệu lý thuyết:

```text
100.000.000 bit/giây × 3.600 giây / 8
= 45.000.000.000 byte
= 45 GB theo hệ thập phân
```

Đây là phép đổi đơn vị để hiểu tốc độ và lượng dữ liệu. Nó không phải quy tắc quy đổi hóa đơn OCI, cũng không chứng minh đường truyền cấu hình 100 Mbps luôn truyền đủ 45 GB mỗi giờ.

Để ước tính egress ứng dụng:

```text
Egress xấp xỉ =
    số phản hồi gửi ra ngoài × kích thước phản hồi trung bình sau nén
  + file người dùng tải xuống
  + các luồng outbound khác
```

Một triệu phản hồi, mỗi phản hồi 100 KB theo hệ thập phân, tạo khoảng 100 GB phần dữ liệu phản hồi. Cần bổ sung các luồng thực tế khác nếu có; dùng số đo mạng để hiệu chỉnh dự toán.

### 4.3. Công thức egress có phần miễn phí và bậc giá

Với một nhóm lưu lượng đủ điều kiện, một ngưỡng và một giá vượt ngưỡng:

```text
G_billable = max(0, G_eligible - F_available)
C_egress   = G_billable × P_egress

G_eligible : GB thuộc đúng phạm vi tính giá
F_available: phần miễn phí còn áp dụng được trong kỳ
P_egress   : giá cho nhóm outbound tương ứng
```

Nếu có nhiều bậc:

```text
C_egress = Σ (GB nằm trong bậc k × giá của bậc k)
```

Các đầu vào phải cùng đơn vị. Không lấy một số đo GiB trừ trực tiếp một ngưỡng TB mà chưa chuẩn hóa.

Phần miễn phí có thể đã được sử dụng bởi những tải công việc khác trong phạm vi tính phí liên quan. Vì vậy, không tự cấp lại toàn bộ ngưỡng cho từng VM, bucket hoặc compartment trong bảng dự toán ứng dụng. Khi đối soát, dùng quantity có tính phí của đúng SKU và điều kiện hợp đồng.

### 4.4. Flexible Load Balancer có mô hình riêng

Flexible Load Balancer có phí base và phí băng thông. Tài liệu mô tả đo theo phút: băng thông tính phí là mức tối thiểu cấu hình nếu dùng thấp hơn mức đó, hoặc mức thực dùng của phút nếu cao hơn. [Nguồn: Creating a Load Balancer, Bandwidth](https://docs.oracle.com/en-us/iaas/Content/Balance/Tasks/managingloadbalancer_topic-Creating_Load_Balancers.htm).

Mô hình dự toán chuẩn hóa theo giờ:

```text
C_lb = H × P_base
     + Σ [B_billable_i × H_i × P_bandwidth]

B_billable_i : Mbps được tính phí trong khoảng i
P_bandwidth  : USD/(Mbps-hour)
```

Ví dụ giả định, một giờ chỉ dùng 5 Mbps trong khi minimum là 20 Mbps: dùng 20 Mbps cho phần dự toán băng thông của khoảng đó. Không lấy 5 Mbps, và cũng không mặc định lấy maximum cấu hình nếu chưa đạt tới.

Khoản tiền Load Balancer và khoản tiền egress là hai dòng khác nhau. Dữ liệu đến người dùng ngoài OCI vẫn cần được xét theo quy tắc network của tuyến truyền.

### 4.5. FastConnect và sao chép sang vùng khác

FastConnect tính theo port-hour dựa trên tốc độ cổng. Theo FAQ, private virtual circuit không bị tính thêm phí truyền dữ liệu OCI; nhà cung cấp kết nối có thể có phí riêng. [Nguồn: FastConnect FAQ](https://www.oracle.com/cloud/networking/fastconnect/faq/).

Đối với phương án dự phòng ở region khác, lập riêng danh mục:

```text
Chi phí dự phòng =
    tài nguyên lưu trữ tại vùng đích
  + lượng dữ liệu sao chép qua vùng
  + Compute được duy trì tại vùng đích
  + các dịch vụ hỗ trợ và kết nối được sử dụng
```

Đó là mô hình kiểm kê kiến trúc, không phải một mức phụ phí cố định. Dung lượng dữ liệu gốc, tốc độ thay đổi dữ liệu, tần suất đồng bộ và cách vận hành dự phòng quyết định quantity cần đưa vào từng dòng.

## 5. Ví dụ tổng hợp: dự toán tầng ứng dụng Java trong 30 ngày

### 5.1. Giả định và ranh giới dự toán

Một nhóm triển khai tầng ứng dụng gồm:

- Hai VM Standard Flex, mỗi máy 2 OCPU, 16 GB RAM, được tính phí 720 giờ.
- Mỗi máy có một boot volume 50 GB và một data volume 250 GB.
- Toàn bộ 600 GB block storage giữ nguyên cả tháng, cùng mức giả định 10 VPU/GB.
- Object Storage có dung lượng trung bình 1.000 GB trong tháng.
- Có 2.000.000 request Object Storage có tính phí.
- Outbound đủ điều kiện là 5.000 GB; phần miễn phí còn áp dụng cho bài toán là 2.000 GB.
- Một Flexible Load Balancer tồn tại 720 giờ, giả định băng thông tính phí ổn định 20 Mbps.

**2.000 GB ở đây là đầu vào giả định còn lại của bài toán**, không phải công bố một hạn mức OCI riêng cho mỗi ứng dụng.

Ví dụ tính trước thuế, chưa áp dụng chiết khấu và credit. Các quantity được nêu là lượng có tính phí theo giả định, ngoại trừ egress còn cần trừ phần miễn phí đã cho.

Phạm vi này chưa gồm database, backup, logging, DNS, WAF hay giấy phép phần mềm trả phí. Khi kiến trúc thực tế có các thành phần đó, phải bổ sung dòng của chúng. Nếu dùng Oracle Database được quản lý, cần lấy SKU và lựa chọn giấy phép của chính dịch vụ database.

### 5.2. Bộ đơn giá giả định

| Dòng giá | Đơn giá giả định | Đơn vị |
| --- | ---: | --- |
| Compute OCPU | 0,040 | USD/OCPU-hour |
| Compute memory | 0,003 | USD/GB-hour |
| Block capacity | 0,020 | USD/GB-month |
| Block performance | 0,001 | USD/(VPU-month), nhân với tổng VPU |
| Object capacity | 0,015 | USD/GB-month |
| Object request | 0,004 | USD/10.000 request |
| Egress vượt phần miễn phí đã cho | 0,020 | USD/GB |
| Load Balancer base | 0,010 | USD/giờ |
| Load Balancer bandwidth | 0,0001 | USD/(Mbps-hour) |

Các giá này được đặt để minh họa phép tính. Không dùng chúng để quyết định mua dịch vụ.

### 5.3. Tính từng dòng rồi mới cộng

| Thành phần | Phép tính | Chi phí giả định, USD |
| --- | --- | ---: |
| OCPU hai VM | 2 × 2 × 720 × 0,040 | 115,20 |
| RAM hai VM | 2 × 16 × 720 × 0,003 | 69,12 |
| Dung lượng block, gồm boot và data | 600 × 0,020 | 12,00 |
| Hiệu năng block | 600 × 10 × 0,001 | 6,00 |
| Dung lượng object trung bình | 1.000 × 0,015 | 15,00 |
| Request object | 2.000.000 / 10.000 × 0,004 | 0,80 |
| Egress có tính phí | max(0, 5.000 − 2.000) × 0,020 | 60,00 |
| Load Balancer base | 720 × 0,010 | 7,20 |
| Load Balancer bandwidth | 720 × 20 × 0,0001 | 1,44 |
| **Tổng trong phạm vi giả định** | **Cộng chín dòng trên** | **286,76** |

Nhóm Compute là 184,32 USD, Storage là 33,80 USD và Network cùng Load Balancer là 68,64 USD.

Bảng này giúp giải thích chênh lệch: tăng RAM làm thay đổi dòng RAM; tăng dữ liệu tải xuống làm thay đổi egress; tăng VPU làm thay đổi hiệu năng block. Không cần sửa toàn bộ mô hình khi một đầu vào thay đổi.

### 5.4. Ba thay đổi và tác động dự toán

**Chỉ chạy hai VM 220 giờ trong tháng**, nếu đây là trường hợp phí Compute thực sự được tạm dừng ngoài giờ:

```text
Compute mới = 2 × 220 × (2 × 0,040 + 16 × 0,003)
             = 56,32 USD

Giảm phần Compute = 184,32 − 56,32 = 128,00 USD
```

Nếu mọi thành phần còn lại vẫn giữ nguyên như bảng, tổng còn 158,76 USD. Đây là kết quả của giả định giữ nguyên các dòng khác; không thể tự giảm storage hay Load Balancer theo cùng tỷ lệ giờ chạy máy.

**Giảm RAM mỗi VM từ 16 GB xuống 12 GB**, vẫn chạy 720 giờ:

```text
Giảm chi phí RAM = 2 × (16 − 12) × 720 × 0,003
                 = 17,28 USD/tháng
```

Trước khi áp dụng, cần đo heap, bộ nhớ ngoài heap, mức dùng của hệ điều hành và độ trễ khi tải cao. Cấu hình rẻ hơn chỉ có ích khi còn đáp ứng yêu cầu.

**Tăng mức hiệu năng block từ 10 lên 20 VPU/GB** trong cả tháng:

```text
Tăng phần hiệu năng = 600 × (20 − 10) × 0,001
                    = 6,00 USD/tháng
```

Phần dung lượng trong ví dụ không đổi. Nếu đồng thời tăng volume size, cả dòng dung lượng lẫn dòng hiệu năng đều thay đổi.

Ba phép tính trên là ba kịch bản độc lập so với bảng gốc; không cộng chồng chúng trừ khi chủ động thiết kế một kịch bản kết hợp.

## 6. Đưa yêu cầu năng lực và tính sẵn sàng vào bảng giá

Một dự toán thấp nhưng thiếu năng lực phục vụ chưa thể dùng để phê duyệt kiến trúc. Hãy ghi giả định kỹ thuật bên cạnh quantity:

| Yêu cầu | Tác động lên mô hình giá |
| --- | --- |
| Chịu được mất một instance | Các instance còn lại cần đủ năng lực gánh tải |
| Giữ dữ liệu phục hồi 30 ngày | Cần dự toán dung lượng lịch sử và lượng thay đổi |
| Có dự phòng ở region khác | Thêm lưu trữ, đồng bộ và tài nguyên dự phòng |
| Tăng gấp đôi lượt tải file | Cần tính lại lượng outbound và bậc giá |
| Tăng số instance để mở rộng ngang | Thêm OCPU, RAM, boot volume và dịch vụ liên quan |
| Tăng tài nguyên theo mùa | Chia thành các khoảng thời gian và số lượng khác nhau |

Đây là các quan hệ để dựng mô hình, không phải khẳng định mọi thành phần đều tăng tuyến tính. Hai máy có thể dùng chung một bucket hoặc một Load Balancer; không nhân đôi toàn bộ hệ thống khi chỉ nhân đôi số VM.

Với ví dụ hai VM, cần ghi rõ mỗi VM có thể xử lý toàn bộ tải tối thiểu khi máy còn lại gặp sự cố hay không. Nếu mỗi máy chỉ đủ gánh một nửa tải bình thường, con số “hai VM” chưa tự chứng minh yêu cầu sẵn sàng.

Nên lập tối thiểu ba cột dự toán: tải nền, tải kỳ vọng và tải cao điểm. Mỗi cột giữ nguyên phương pháp tính nhưng thay quantity bằng giả định của kịch bản tương ứng.

## 7. Từ dự toán sang đối soát trên OCI

### 7.1. Lập danh mục đầu vào trước khi dùng công cụ

Một mẫu ghi nhận có thể đặt trực tiếp trong tài liệu thiết kế:

```text
Kỳ dự toán:
Loại tiền:
Ngày lấy giá và nguồn giá:
Region / nhóm giá network:
Mô hình thanh toán:
Compartment / môi trường / chủ sở hữu:

Compute:
  họ shape, số instance, OCPU, RAM, giờ được tính phí
  OS / phần mềm trả phí nếu có

Storage:
  boot volume, data volume, GB cấp phát, VPU/GB
  object tier, dung lượng theo thời gian, request, retrieval
  backup, thời gian giữ bản, bản sao ở vùng khác

Network:
  nguồn → đích, chiều truyền, đường kết nối
  GB outbound, phần miễn phí còn áp dụng, đơn giá từng nhóm
  Load Balancer base và bandwidth, FastConnect nếu có

Giả định tải, dự phòng và tăng trưởng:
Các thành phần chưa nằm trong tổng:
```

Oracle cung cấp Cost Estimator để ước tính mức dùng và chi phí tháng. Dùng công cụ sau khi đã có các đầu vào, rồi kiểm tra xem các dòng được thêm đã phủ hết kiến trúc chưa. [Nguồn: Estimating Monthly Costs](https://docs.oracle.com/en-us/iaas/Content/Billing/Tasks/signingup_topic-Estimating_Costs.htm).

Không coi một tổng tiền do công cụ hiển thị là bằng chứng rằng backup, network hay database đã tự được tính. Phạm vi kết quả phụ thuộc các thành phần và quantity được đưa vào.

### 7.2. Đối chiếu theo SKU và cùng kỳ thời gian

Cost Analysis hỗ trợ xem chi phí theo service, SKU, compartment, region và các bộ lọc liên quan. Chọn cùng khoảng thời gian và chú ý mốc ngày theo UTC. [Nguồn: Cost Analysis](https://docs.oracle.com/en-us/iaas/Content/Billing/Concepts/costanalysisoverview.htm).

Một trình tự đối soát hữu ích:

1. Chọn kỳ và loại tiền khớp với dự toán.
2. Lọc phạm vi ứng dụng hoặc môi trường cần xem.
3. Tách theo service và SKU để thấy riêng OCPU, RAM, storage và network.
4. So lượng sử dụng trước, sau đó mới so đơn giá và thành tiền.
5. Ghi nguyên nhân chênh lệch vào giả định của kỳ dự toán tiếp theo.

Nếu quantity đúng nhưng tiền khác, kiểm tra giá hiệu lực, bậc giá, credit và điều kiện áp dụng. Nếu quantity khác, tìm thời gian chạy, tài nguyên còn tồn tại, cấu hình thực tế hoặc các luồng dữ liệu bị bỏ sót.

Với báo cáo chi tiết, dùng quantity phục vụ tính giá và đơn vị của SKU; không mặc định mọi trường “usage” đều đã là quantity sau quy tắc làm tròn hoặc tính phí. [Nguồn: Cost Reports](https://docs.oracle.com/en-us/iaas/Content/Billing/Concepts/costusagereportsoverview.htm).

Các dòng khác đơn vị phải được đối chiếu độc lập. Một máy Flex có hai dòng sử dụng cho CPU và RAM là tình huống dự kiến trong mô hình này, không tự đồng nghĩa bị tính trùng.

## 8. Những lỗi đọc giá làm sai cả dự toán

| Lỗi | Cách sửa mô hình |
| --- | --- |
| Coi một OCPU luôn là một vCPU | Đối chiếu đúng họ shape và kiến trúc |
| Chỉ tính CPU cho máy Flex | Thêm dòng RAM với quantity riêng |
| Dùng phần trăm CPU để nhân giảm hóa đơn | Dùng lượng tài nguyên và thời gian được tính phí |
| Lấy dung lượng file đang dùng làm dung lượng block tính phí | Ghi dung lượng volume được cấp phát |
| Bỏ boot volume | Thêm boot volume cho từng instance |
| Bỏ phần hiệu năng hoặc nhân VPU hai lần | Xác định giá là theo một VPU hay đã theo cả mức hiệu năng |
| Chỉ nhìn giá GB-tháng của object | Thêm request, retrieval, restore, thời gian lưu tối thiểu khi áp dụng |
| Lấy dung lượng object cuối tháng cho cả kỳ | Tính dung lượng có xét thời gian |
| Trừ lại toàn bộ phần miễn phí cho mỗi tài nguyên | Xác minh phạm vi ưu đãi và phần còn áp dụng |
| Nhầm Mbps với GB truyền ra ngoài | Tách năng lực băng thông khỏi tổng lượng dữ liệu |
| Tắt máy rồi xóa mọi dòng liên quan khỏi dự toán | Kiểm kê tài nguyên vẫn còn tồn tại |
| Nhân đôi VM rồi nhân đôi toàn bộ bảng giá | Tách phần theo máy và phần được dùng chung |
| Gộp giá niêm yết, giá hợp đồng và credit vào một con số | Ghi rõ từng bước từ mức dùng đến tiền phải trả |

Một bản dự toán đọc được cần trả lời cho từng khoản: **đang trả cho đại lượng nào, lấy quantity ở đâu, áp dụng đơn giá nào và giả định nào sẽ làm con số thay đổi**. Khi bốn điểm này rõ ràng, mô hình giá trở thành công cụ để lựa chọn cấu hình OCI, cân bằng chi phí với năng lực và theo dõi chênh lệch sau triển khai.

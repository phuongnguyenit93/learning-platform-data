# Dự báo tăng trưởng, theo dõi quotas và lập kế hoạch capacity

## 1. Mục tiêu và bối cảnh

Trong chương **Chi phí và quản lý năng lực** của module **CLOUD_PROVIDERS_ORACLE**, lập kế hoạch capacity là quá trình chuyển nhu cầu kinh doanh thành tài nguyên Oracle Cloud Infrastructure (OCI) có thể triển khai đúng lúc, đáp ứng mức dịch vụ và nằm trong ngân sách.

Một hệ thống có thể dùng CPU thấp nhưng vẫn không mở rộng được vì hết quota bộ nhớ, thiếu địa chỉ IP trong subnet hoặc thiếu host phù hợp. Ngược lại, tenancy có service limit lớn vẫn có thể tốn chi phí không cần thiết nếu tài nguyên luôn chạy ở mức cực đại.

Sau bài học, người học có thể:

- Xây dựng baseline từ lưu lượng, độ trễ, mức sử dụng và tăng trưởng dữ liệu.
- Chuyển dự báo thành nhu cầu Compute, lưu trữ, mạng và cơ sở dữ liệu Oracle.
- Đọc đúng service limits, compartment quotas và phần còn có thể cấp phát.
- Tính phần dự phòng cho mở rộng, triển khai phiên bản mới và sự cố.
- Xây dựng cảnh báo sớm, phân công người xử lý và theo dõi chi phí của phương án.

Bài học giả định người đọc đã hiểu tenancy, compartment, IAM, VCN và cách xem metrics cơ bản. Các con số dưới đây là **giả định phục vụ tính toán**, không phải hạn mức mặc định, giá niêm yết hoặc cam kết cấp phát của Oracle.

## 2. Phân biệt nhu cầu, hạn mức và năng lực thực tế

| Khái niệm | Câu hỏi cần trả lời | Ý nghĩa trong kế hoạch |
| --- | --- | --- |
| Demand — nhu cầu | Ứng dụng cần xử lý bao nhiêu công việc? | Request/giây, giao dịch/giây, batch/giờ, dữ liệu phát sinh/ngày |
| Provisioned capacity — năng lực đã cấp phát | Hiện đã có những tài nguyên nào? | Số instance, OCPU, RAM, dung lượng, cấu hình DB |
| Service limit | Oracle cho tenancy dùng tối đa bao nhiêu trong scope tương ứng? | Trần do Oracle đặt; phải kiểm tra giá trị thực tế của tenancy |
| Compartment quota | Tổ chức cho compartment sử dụng tối đa bao nhiêu? | Ranh giới phân bổ nội bộ do quản trị viên thiết lập |
| Resource availability trong Limits API | Theo usage và các hạn mức, còn được cấp phát bao nhiêu? | Headroom về hạn mức; không phải số host đang trống |
| Host capacity | OCI có hạ tầng phù hợp để cấp phát lúc này không? | Phụ thuộc vị trí, shape và các yêu cầu placement |
| Budget | Dự kiến hoặc thực tế sẽ chi bao nhiêu? | Cơ chế theo dõi tiền và cảnh báo |

Oracle phân biệt service limits do Oracle thiết lập với compartment quotas do quản trị viên đặt. Một số giới hạn không thể tăng; không nên xây dựng kế hoạch dựa trên giả định mọi yêu cầu tăng limit đều được chấp thuận. Xem [Service Limits](https://docs.oracle.com/en-us/iaas/Content/General/service-limits/overview.htm) và [Manage Your Service Limits](https://docs.oracle.com/en/solutions/oci-best-practices/manage-your-service-limits1.html).

Trong vận hành, cần kiểm tra ba lớp độc lập:

1. **Được phép:** IAM có cho phép tạo, thay đổi và sử dụng các tài nguyên liên quan không?
2. **Còn hạn mức:** service limit và quota áp dụng còn đủ không?
3. **Có thể cấp phát:** hạ tầng, subnet, cấu hình shape và các tài nguyên phụ thuộc có đáp ứng không?

Việc có đủ ngân sách cũng phải được xác nhận, nhưng ngân sách không thay thế ba lớp kiểm tra trên.

### 2.1. Scope là một phần của định danh hạn mức

Không ghi đơn giản “Compute còn 40 OCPU”. Một bản ghi có ích cần xác định:

~~~text
tenancy / subscription nếu áp dụng / region / service /
limit-name / scope-type / availability-domain nếu áp dụng /
compartment được đánh giá / thời điểm lấy dữ liệu
~~~

Tên limit, đơn vị và scope phải được đọc từ OCI. Không cộng các OCPU còn dư ở nhiều AD rồi coi chúng là tài nguyên có thể cấp cho một instance duy nhất. Cũng không lấy limit của region chính để kết luận region phục hồi thảm họa còn đủ hạn mức.

Tài liệu [Limits by Service](https://docs.oracle.com/en-us/iaas/Content/General/service-limits/default.htm) nêu scope theo từng tài nguyên. Trong kế hoạch thực tế, dùng giá trị đang hiển thị cho tenancy và subscription liên quan thay cho việc sao chép bảng mặc định.

### 2.2. Quota trong cây compartment

Usage của compartment con được tính vào compartment cha. Quota theo AD áp dụng cho từng AD nếu không có điều kiện giới hạn một AD cụ thể; quota theo region cũng phải được hiểu theo scope của nó. Service limit vẫn ràng buộc dù quota nội bộ cao hơn. Xem [Quota Policy Syntax](https://docs.oracle.com/en-us/iaas/Content/Quotas/Concepts/quota_policy_syntax.htm).

Ví dụ, đội ứng dụng có thể còn 24 OCPU trong quota riêng, nhưng compartment cha chỉ còn 8 OCPU sau khi tính các đội khác. Khi đó, kế hoạch thêm 20 OCPU chưa khả thi.

Không suy quota hiệu lực bằng cách cộng tất cả policy tìm thấy. Phải xét cấp cha, điều kiện áp dụng và quy tắc kết hợp policy; dùng kết quả availability phù hợp khi API hỗ trợ.

## 3. Xây dựng baseline có thể kiểm chứng

Baseline là ảnh chụp nhu cầu và hành vi của hệ thống trong một giai đoạn đại diện. Chọn cửa sổ đủ bao phủ chu kỳ làm việc: chẳng hạn vài tuần có ngày thường, cuối tuần và lần chạy batch định kỳ. Nếu chưa có mùa cao điểm trong dữ liệu, ghi rõ đó là khoảng trống dự báo.

### 3.1. Thu thập cả đầu vào kinh doanh và tín hiệu kỹ thuật

| Thành phần | Dữ liệu nên thu thập | Mục đích |
| --- | --- | --- |
| Nghiệp vụ | Người dùng hoạt động, đơn hàng, khách hàng mới, lịch chiến dịch | Nhận biết nguyên nhân tăng tải và sự kiện chưa có trong lịch sử |
| Compute hoặc worker | Throughput, CPU, RAM, hàng đợi, thời gian xử lý | Tìm giới hạn xử lý và tài nguyên cần tăng |
| Ứng dụng | p95/p99 latency, tỷ lệ lỗi, timeout, concurrency | Xác định năng lực đáp ứng SLO |
| Block Volume và filesystem | Dung lượng đã dùng, dung lượng cấp phát, IOPS, throughput, latency | Phân biệt thiếu dung lượng với nghẽn hiệu năng I/O |
| Object Storage và log | Dữ liệu mới, dữ liệu hết hạn, version, retention | Dự báo dung lượng giữ lại |
| Cơ sở dữ liệu Oracle | TPS, CPU, session, wait, I/O, dung lượng, tăng trưởng redo/archive | Tìm nút thắt dữ liệu và điều kiện mở rộng |
| VCN và kết nối | Địa chỉ IP còn dùng được, throughput, kết nối, lưu lượng truyền | Kiểm tra khả năng tạo thêm node và khả năng phục vụ |
| Tài chính | Chi phí theo compartment, môi trường, ứng dụng và kỳ | Đối chiếu tăng tài nguyên với giá trị sử dụng |

Dữ liệu RAM có thể cần agent hoặc công cụ quan sát trong guest. Xác nhận nguồn đo và tình trạng thu thập; một biểu đồ không có dữ liệu không chứng minh RAM đang rảnh.

Với cơ sở dữ liệu, xác định rõ loại dịch vụ đang dùng: Base Database Service, Autonomous Database hay một cấu hình Oracle khác. Ghi đúng đơn vị năng lực của cấu hình đó; không chuyển OCPU sang ECPU bằng một tỷ lệ mặc định để lập kế hoạch chung cho mọi dịch vụ.

### 3.2. Ghi lại điều kiện của mỗi phép đo

Một số liệu “350 request/giây mỗi node” chỉ hữu ích nếu biết:

- Shape, số OCPU, RAM, image và phiên bản ứng dụng.
- Kích thước request, tỷ lệ đọc/ghi, cache hit và phân bố endpoint.
- Độ trễ, tỷ lệ lỗi và mức sử dụng tương ứng.
- Tải nền, kết nối đến DB và số node cùng tham gia thử nghiệm.
- Khoảng thời gian, múi giờ và độ phân giải của mẫu.

Giữ các mốc thời gian thống nhất, ví dụ UTC khi tổng hợp. Đánh dấu deploy, incident, import dữ liệu và thay đổi cấu hình trên cùng trục thời gian.

### 3.3. Tránh baseline gây hiểu nhầm

CPU trung bình tháng thấp có thể che khuất đỉnh tải kéo dài 20 phút. Bên cạnh trung bình, cần xem các cửa sổ cao điểm, percentile và đường thời gian.

Không cộng p95 của từng instance rồi gọi kết quả là p95 của toàn hệ thống. Nếu cần percentile tổng hợp, phải dùng dữ liệu hoặc histogram có thể tổng hợp phù hợp.

Cũng không coi mọi bất thường đều là xu hướng. Một lần reindex hoặc backfill cần được gắn nhãn riêng, nhưng vẫn phải có chỗ trong kế hoạch nếu công việc đó sẽ lặp lại.

## 4. Dự báo tăng trưởng từ nhu cầu đến số node

### 4.1. Chọn mô hình theo nguồn tăng trưởng

Hai mô hình đơn giản thường đủ để bắt đầu:

~~~text
Tăng tuyến tính:
D(t) = D0 + a × t

Tăng theo tỷ lệ:
D(t) = D0 × (1 + g)^t
~~~

Trong đó:

- `D0` là nhu cầu tại mốc gốc.
- `a` là lượng tăng tuyệt đối trong một kỳ.
- `g` là tỷ lệ tăng theo kỳ.
- `t` là số kỳ, cùng đơn vị thời gian với `a` hoặc `g`.

Ví dụ, số khách hàng mới đều đặn mỗi tháng có thể phù hợp với mô hình tuyến tính. Tải của sản phẩm đang tăng theo tỷ lệ có thể phù hợp với mô hình lũy thừa trong một khoảng thời gian ngắn.

Nếu có sự kiện được biết trước, có thể dùng:

~~~text
D_peak(t) = D0 × (1 + g)^t × S(t) + E(t)
~~~

`S(t)` biểu diễn hệ số mùa vụ; `E(t)` là tải bổ sung chưa nằm trong xu hướng. Phải kiểm tra dữ liệu gốc đã bao gồm mùa vụ hay sự kiện chưa để tránh tính hai lần.

Dự báo nên có ít nhất ba kịch bản: thấp, cơ sở và cao. Mỗi kịch bản cần lý do kinh doanh, ngày cập nhật và người chịu trách nhiệm về giả định.

### 4.2. Ví dụ dự báo lưu lượng sau ba tháng

Giả sử đỉnh tải hiện tại là **1.200 request/giây**. Đội sản phẩm dự kiến chiến dịch vào cuối tháng thứ ba.

| Kịch bản | Tăng mỗi tháng | Hệ số chiến dịch | Phép tính | Đỉnh tải làm tròn lên |
| --- | --- | --- | --- | --- |
| Thấp | 4% | 1,2 | 1.200 × 1,04³ × 1,2 | 1.620 request/giây |
| Cơ sở | 8% | 1,4 | 1.200 × 1,08³ × 1,4 | 2.117 request/giây |
| Cao | 12% | 1,6 | 1.200 × 1,12³ × 1,6 | 2.698 request/giây |

Đây là các kịch bản giả định, không phải khoảng tin cậy thống kê. Khi có dữ liệu mới, cập nhật cả tốc độ tăng và hệ số chiến dịch.

### 4.3. Từ throughput sang năng lực Compute

Giả sử load test cho thấy một node **4 OCPU, 32 GB RAM** phục vụ được **350 request/giây**, đồng thời đạt:

- p95 latency không quá 200 ms.
- Tỷ lệ lỗi dưới 0,1%.
- CPU và RAM trong ngưỡng vận hành mà nhóm đã chấp nhận.

350 request/giây là năng lực **đã thỏa SLO ở cấu hình thử nghiệm**, không phải throughput tại 100% CPU. Không tự nhân thêm một hệ số CPU dự phòng nếu hệ số đó đã được dùng để xác định con số 350.

Công thức:

~~~text
N_serve = ceil(D_peak / throughput_an_toàn_mỗi_node)
N_steady = N_serve + số_node_dự_phòng_theo_kịch_bản_sự_cố
~~~

Với yêu cầu chịu mất một node:

| Kịch bản | Node cần để phục vụ | Node chạy ổn định, có N+1 | OCPU | RAM |
| --- | --- | --- | --- | --- |
| Thấp | ceil(1.620 / 350) = 5 | 6 | 24 | 192 GB |
| Cơ sở | ceil(2.117 / 350) = 7 | 8 | 32 | 256 GB |
| Cao | ceil(2.698 / 350) = 8 | 9 | 36 | 288 GB |

Kịch bản cao có chín node, nhưng khi một node hỏng vẫn còn tám node với tổng năng lực đã giả định là 2.800 request/giây.

Phép tính trên giả định khả năng mở rộng gần tuyến tính. Trước khi dùng trong production, cần thử với nhiều node và DB tương ứng: connection pool, lock hoặc dịch vụ dùng chung có thể khiến node thứ chín không tạo thêm throughput như dự kiến.

### 4.4. Kiểm tra tài nguyên phụ thuộc

Nếu mỗi node mở tối đa 40 kết nối DB, chín node có thể tạo tới 360 kết nối. Khi rolling deployment dùng 11 node, giá trị cấu hình tối đa thành 440 kết nối.

Đó chưa phải dự báo số session hoạt động thực tế, nhưng là mức cần đối chiếu với năng lực DB, giới hạn kết nối và cách ứng dụng tái sử dụng connection. Tăng số node mà giữ nguyên một DB đang nghẽn I/O có thể chỉ làm hàng đợi dài hơn.

Cùng nguyên tắc đó, kiểm tra IP của subnet, backend của load balancer, boot volume, logging và các phụ thuộc khác trước khi chốt số node.

## 5. Dự báo lưu trữ và thời điểm phải mở rộng

### 5.1. Phân biệt dung lượng sử dụng với dung lượng cấp phát

Giả sử dữ liệu ứng dụng hiện dùng 2.048 GiB, tăng ròng 20 GiB/ngày và cần kế hoạch cho 90 ngày:

~~~text
Dung_lượng_dữ_liệu_sau_90_ngày
= 2.048 + 20 × 90
= 3.848 GiB
~~~

Nếu muốn dung lượng đã dùng không vượt 75% dung lượng cấp phát:

~~~text
Dung_lượng_cần_cấp
>= 3.848 / 0,75
>= 5.130,67 GiB

Mức tính toán tối thiểu sau làm tròn: 5.131 GiB
~~~

Sau đó chọn cấu hình hợp lệ của dịch vụ, có xét bước tăng dung lượng và các giới hạn liên quan.

“Giữ trống 25% tổng dung lượng” khác với “cộng thêm 25% dữ liệu”. Trong ví dụ này, phép tính đúng cho mục tiêu giữ trống là chia cho 0,75.

GiB trong phép tính là đơn vị dữ liệu của ví dụ. Khi đối chiếu OCI, quy đổi nhất quán về byte hoặc đơn vị thực tế của metric, quota và cấu hình; đừng mặc định mọi nhãn GB đều có cùng cách biểu diễn với GiB.

### 5.2. Tính thời gian đến ngưỡng vận hành

Nếu hiện đã cấp 4.000 GiB, ngưỡng 75% là 3.000 GiB:

~~~text
Số_ngày_đến_ngưỡng
= (3.000 - 2.048) / 20
= 47,6 ngày
~~~

Giá trị này hữu ích hơn câu “ổ đĩa còn gần một nửa” vì có thể so với thời gian cần để xin duyệt, thay đổi cấu hình và xác minh.

Công thức tổng quát với tốc độ tăng ròng dương:

~~~text
T_ngưỡng = (Ngưỡng_dung_lượng - Dữ_liệu_hiện_tại) / Tăng_ròng_mỗi_ngày
~~~

Nếu tốc độ tăng bằng không hoặc âm, không chia trực tiếp. Ghi “chưa dự báo chạm ngưỡng theo mô hình hiện tại” và tiếp tục theo dõi biến động.

### 5.3. Lưu trữ cần nhiều hơn một đường dự báo

Lập kế hoạch riêng cho:

- Dữ liệu đang phục vụ, index và phần trống cho các thao tác bảo trì.
- Redo, archive log, log ứng dụng và thời gian retention.
- Backup, bản sao phục hồi, version của object và dữ liệu bị giữ theo chính sách.
- Không gian tạm khi import, rebuild index hoặc chuyển đổi dữ liệu.
- IOPS, throughput và latency cần thiết ở mức tải dự báo.

Với một luồng log đều 10 GiB/ngày và retention 30 ngày, phần dữ liệu giữ lại ở trạng thái ổn định xấp xỉ 300 GiB nếu việc xóa hết hạn hoạt động đúng. Không ngoại suy thành tăng vô hạn; cũng không giả định tác vụ hết hạn đã chạy nếu chưa có số liệu xác nhận.

Snapshot, backup tăng dần, nén và khử trùng lặp có cách tiêu thụ dung lượng khác nhau. Dùng dữ liệu đo của cơ chế đang triển khai thay vì nhân cố định số bản backup với toàn bộ dung lượng nguồn.

## 6. Tính capacity cho triển khai và sự cố

### 6.1. Nhu cầu vận hành thường nhỏ hơn nhu cầu cấp phát cực đại

Tiếp tục ví dụ kịch bản cao: chín node phục vụ ổn định, mỗi node 4 OCPU và 32 GB RAM.

| Trạng thái | Số node cần tính trong kế hoạch | OCPU | RAM | Điều kiện |
| --- | --- | --- | --- | --- |
| Hiện tại | 6 | 24 | 192 GB | Baseline giả định |
| Vận hành ở tải cao có N+1 | 9 | 36 | 288 GB | Tám node còn lại đủ tải khi mất một node |
| Thay một node trước khi xóa node cũ | 10 | 40 | 320 GB | Cần chỗ cho node cũ và mới cùng tồn tại |
| Rolling deployment có tối đa hai node surge | 11 | 44 | 352 GB | Chín node hiện có và hai node bổ sung |

Trong ví dụ, mức cần kiểm tra hạn mức là **11 node**, tương đương **44 OCPU và 352 GB RAM**, dù mức chạy ổn định chỉ là chín node.

Nếu quy trình cho phép thêm một node thay thế ngoài hai slot surge khi có sự cố đồng thời, cực đại có thể thành 12 node. Kế hoạch phải nêu rõ các trạng thái nào được phép chồng lấn; không mặc định mọi dự phòng đều cộng độc lập hoặc đều có thể dùng chung.

Một instance không còn phục vụ lưu lượng chưa chắc đã giải phóng phần usage liên quan. Chỉ tính tài nguyên đã được giải phóng sau khi xác nhận trạng thái và cách dịch vụ ghi nhận usage.

### 6.2. Chịu lỗi một node khác với chịu mất một AD

N+1 trong bảng chỉ mô hình hóa việc mất **một node**. Nó không tự chứng minh hệ thống chịu được việc mất toàn bộ AD chứa nhiều node.

Giả sử ứng dụng được triển khai tại hai AD và mỗi AD phải tự xử lý kịch bản cao khi AD kia ngừng hoạt động. Với năng lực 350 request/giây mỗi node, mỗi AD cần tối thiểu tám node sẵn sàng phục vụ để đáp ứng 2.698 request/giây. Tổng cộng là 16 node trước khi tính yêu cầu dự phòng bổ sung.

Đây là mô hình giả định cho region có topology phù hợp. Nếu region chỉ có một AD, phân bố qua fault domain không tạo ra khả năng chịu mất AD đó.

### 6.3. Capacity cho phục hồi thảm họa

Kế hoạch DR cần xác định:

- RTO: thời gian phục hồi tối đa được chấp nhận.
- RPO: mức mất dữ liệu tối đa được chấp nhận.
- Tải cần phục vụ ngay sau failover: toàn bộ hay một tập chức năng ưu tiên.
- Tài nguyên nào đã chạy sẵn, được giữ chỗ hoặc sẽ tạo khi có sự cố.
- Hạn mức, mạng, image, IAM, secret và dữ liệu tại region phục hồi.
- Thời gian provisioning, restore, đồng bộ và chuyển lưu lượng đã đo.

Không coi một Terraform plan hợp lệ là bằng chứng có thể phục hồi trong RTO. Cần diễn tập đường phục hồi và đánh dấu rõ thông số nào đã đo, thông số nào mới là ước tính.

## 7. Tính headroom theo service limit và quota

### 7.1. Mô hình đơn giản cho một loại tài nguyên

Với cùng service, limit-name, đơn vị và scope, đặt:

- `L`: service limit của tenancy.
- `U_tenancy`: tổng usage thuộc scope đó.
- `Q_prod`: quota hiệu lực của compartment Production.
- `U_prod`: usage trong Production, gồm các compartment con áp dụng.

Nếu không có ràng buộc chặt hơn ở cấp cha hoặc điều kiện khác:

~~~text
H_service = L - U_tenancy
H_prod = Q_prod - U_prod
H_effective = max(0, min(H_service, H_prod))
~~~

Khi compartment cha có quota áp dụng, phải đưa phần còn lại ở cấp cha vào phép lấy min tương ứng. Đây là mô hình số học để hiểu headroom; nó không thay thế toàn bộ quy tắc đánh giá policy của OCI.

### 7.2. Ví dụ CPU và bộ nhớ cùng giới hạn việc mở rộng

Giả sử ảnh chụp tại cùng một AD và thời điểm cho kết quả:

| Tài nguyên | Service limit | Usage tenancy | Quota Production | Usage Production | Headroom hiệu lực trong mô hình |
| --- | --- | --- | --- | --- | --- |
| OCPU của family đang dùng | 160 | 132 | 96 | 72 | min(28, 24) = 24 OCPU |
| RAM của family đang dùng | 1.280 GB | 1.056 GB | 768 GB | 576 GB | min(224, 192) = 192 GB |

Usage Production gồm ứng dụng đang xét và các workload khác. Sáu node hiện tại của ứng dụng chỉ chiếm 24 OCPU trong tổng 72 OCPU của compartment.

Để đi từ sáu node lên cực đại 11 node, cần **thêm năm node**:

~~~text
OCPU bổ sung = 5 × 4 = 20 OCPU
RAM bổ sung = 5 × 32 = 160 GB
~~~

Theo hai hạn mức trong bảng, yêu cầu bổ sung này còn nằm trong phần được cấp phát:

~~~text
Usage Production sau mở rộng:
OCPU = 72 + 20 = 92 trên quota 96
RAM  = 576 + 160 = 736 GB trên quota 768 GB
~~~

Cả hai quota đều đạt khoảng 95,8%. Việc “còn tạo được” chỉ chứng minh bước mở rộng hiện tại chưa vượt hai ràng buộc này; khoảng trống sau đó quá nhỏ để mặc nhiên coi kế hoạch trung hạn đã an toàn.

Nếu muốn biết số node mới tối đa chỉ xét hai tài nguyên trên:

~~~text
N_add_by_CPU = floor(24 / 4) = 6
N_add_by_RAM = floor(192 / 32) = 6
N_add_by_limits = min(6, 6) = 6
~~~

Kết quả chưa xét IP, boot volume, limit khác hoặc host capacity.

### 7.3. Trường hợp quota cha làm thay đổi kết luận

Bây giờ giả sử compartment cha còn đúng 8 OCPU. Headroom OCPU hiệu lực giảm còn:

~~~text
min(28 OCPU ở tenancy, 24 OCPU ở Production, 8 OCPU ở cha)
= 8 OCPU
~~~

Chỉ đủ cho hai node 4 OCPU; năm node mới sẽ bị chặn về hạn mức. Cần điều chỉnh phân bổ tại cấp cha hoặc thay đổi phương án trước ngày triển khai.

Quotas phân bổ quyền tiêu thụ, không đặt riêng host cho compartment. Tăng quota nội bộ vẫn chưa chứng minh OCI có thể cấp phát đủ tài nguyên vào thời điểm cần dùng.

## 8. Đọc limits và usage trên OCI

### 8.1. Quy trình trên Console

Tại trang **Limits, Quotas and Usage**:

1. Xác nhận tenancy, region và subscription nếu có lựa chọn tương ứng.
2. Chọn service và loại tài nguyên cần xem.
3. Kiểm tra scope, AD nếu áp dụng, đơn vị, limit, usage và availability.
4. Chọn compartment cần đánh giá.
5. Đối chiếu quota ở compartment đó và các cấp cha liên quan.
6. Ghi thời điểm lấy dữ liệu và người chịu trách nhiệm xử lý.

Lập bản theo dõi theo từng ràng buộc thực tế. Không chỉ chụp màn hình hàng OCPU rồi bỏ qua hàng RAM hoặc nhóm tài nguyên reservation nếu phương án có dùng giữ chỗ.

### 8.2. Quyền IAM để đọc dữ liệu

Ví dụ cho nhóm `CapacityReaders`:

~~~text
Allow group CapacityReaders to inspect resource-availability in tenancy
Allow group CapacityReaders to read resource-availability in compartment Production
~~~

Quyền inspect ở tenancy phục vụ tra cứu services, definitions và values; quyền read cho phép đọc resource availability tại compartment được cấp. Điều chỉnh tên nhóm, compartment và cú pháp định danh theo tenancy. Xem phần IAM trong [Service Limits](https://docs.oracle.com/en-us/iaas/Content/General/service-limits/overview.htm).

Các policy này không phải bộ quyền để sửa quota hoặc triển khai hạ tầng. Nếu cần đọc inventory và metrics của dịch vụ khác, cấp thêm đúng quyền đọc cho mục đích đó.

### 8.3. Ví dụ OCI CLI để tra cứu

Các lệnh sau dùng **Bash**, chẳng hạn trong môi trường đã có OCI CLI và thông tin xác thực phù hợp. Thay các giá trị mẫu trước khi chạy.

~~~bash
TENANCY_OCID="ocid1.tenancy.oc1..THAY_GIA_TRI"
PROD_OCID="ocid1.compartment.oc1..THAY_GIA_TRI"
REGION="THAY_REGION"
SERVICE="compute"

# Tra định nghĩa: tên limit, scope và khả năng hỗ trợ quota.
oci limits definition list --compartment-id "$TENANCY_OCID" --service-name "$SERVICE" --region "$REGION" --all

# Tra giá trị service limit của tenancy trong region đang xét.
oci limits value list --compartment-id "$TENANCY_OCID" --service-name "$SERVICE" --region "$REGION" --all
~~~

Lấy `LIMIT_NAME` từ kết quả definition, không suy tên kỹ thuật từ tên hiển thị của shape. Thuộc tính hỗ trợ quota cho biết có thể đặt compartment quota cho limit đó hay không. Tham khảo [definition list](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/limits/definition/list.html) và [value list](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/limits/value/list.html).

Với limit có scope `AD`:

~~~bash
LIMIT_NAME="THAY_LIMIT_NAME_DA_TRA_CUU"
AD_NAME="THAY_TEN_AD_DAY_DU_CUA_TENANCY"

oci limits resource-availability get --compartment-id "$PROD_OCID" --service-name "$SERVICE" --limit-name "$LIMIT_NAME" --availability-domain "$AD_NAME" --region "$REGION"
~~~

Với limit có scope `REGION`, dùng lệnh riêng không có tham số AD:

~~~bash
LIMIT_NAME="THAY_LIMIT_NAME_CO_SCOPE_REGION"

oci limits resource-availability get --compartment-id "$PROD_OCID" --service-name "$SERVICE" --limit-name "$LIMIT_NAME" --region "$REGION"
~~~

Chỉ chạy nhánh phù hợp. Theo [resource-availability get](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/limits/resource-availability/get.html), tham số AD là bắt buộc với scope AD và phải bỏ khi không phải scope AD. Một số limit không hỗ trợ API này và có thể trả 404; cần phân biệt với sai định danh hoặc vấn đề truy cập.

Nếu dịch vụ gắn với subscription, chọn đúng subscription và truyền `--subscription-id` ở các lệnh hỗ trợ khi cần. Giữ nguyên ngữ cảnh đó giữa các lần lấy dữ liệu.

Kết quả từ Limits API mô tả availability theo usage, service limits và quotas. Nó không phải báo cáo host capacity; một số trường cũng có thể không được cung cấp cho mọi limit. Xem [resource-availability](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/limits/resource-availability.html).

### 8.4. Mẫu bản ghi theo dõi

| Trường | Nội dung cần lưu |
| --- | --- |
| Context | Tenancy, subscription nếu áp dụng, region, compartment |
| Resource key | Service, limit-name, scope-type, AD nếu có |
| Measurement | Đơn vị, limit, usage, availability nếu có |
| Planning | Nhu cầu bổ sung, cực đại đồng thời, ngày dự kiến chạm ngưỡng |
| Freshness | Thời điểm thu thập, lần thành công cuối, lỗi gần nhất |
| Ownership | Người vận hành, người có quyền sửa quota, đầu mối yêu cầu tăng limit |
| Action | Công việc cần làm, ngày cần hoàn tất, trạng thái xác minh |

Không cộng usage tenancy với usage compartment vì compartment đã có thể nằm trong tổng tenancy. Không cộng usage của cha và con để tính tổng lần nữa.

Với giá trị phân số, giữ độ chính xác phù hợp. Với trường rỗng, không được hỗ trợ hoặc trạng thái không giới hạn, xử lý theo định nghĩa API thay vì ép thành số 0.

## 9. Cảnh báo trước khi hết quota

### 9.1. Theo dõi cả tỷ lệ và thời gian còn lại

Tỷ lệ sử dụng giúp nhận biết mức độ sát trần:

~~~text
Tỷ_lệ_quota = Usage / Quota
~~~

Nhưng thứ quyết định thời điểm hành động thường là:

~~~text
T_cạn = Headroom_hiện_tại / Tăng_usage_ròng_mỗi_ngày

T_chuẩn_bị
= Thời_gian_xử_lý_limit_hoặc_quota
+ Thời_gian_triển_khai_và_xác_minh
+ Biên_dự_phòng_thời_gian
~~~

Nên mở công việc khi `T_cạn <= T_chuẩn_bị`, hoặc khi một sự kiện đã biết cần lượng tài nguyên vượt headroom, dù tỷ lệ hiện tại chưa cao.

Ví dụ độc lập: quota 96 OCPU, usage 72 OCPU và tăng đều 1 OCPU/ngày. Headroom là 24 OCPU, tương đương 24 ngày. Nếu cần 14 ngày xử lý, bảy ngày triển khai kiểm chứng và bảy ngày dự phòng, tổng là 28 ngày. Phải bắt đầu xử lý ngay dù mới dùng 75% quota.

Các thời gian trên là giả định lập kế hoạch của đội, không phải SLA xử lý yêu cầu của Oracle. Khi chưa có dữ liệu lead time, ghi nhận sự không chắc chắn và làm việc sớm với đầu mối hỗ trợ.

### 9.2. Ngưỡng vận hành mẫu

| Điều kiện mẫu | Hành động |
| --- | --- |
| Usage trên 70% và tiếp tục tăng | Kiểm tra dự báo, tài nguyên chưa dọn và kế hoạch sắp tới |
| Usage trên 85% hoặc thời gian còn lại ngắn hơn thời gian chuẩn bị | Tạo công việc có chủ sở hữu và hạn hoàn tất |
| Usage trên 95% hoặc sự kiện sắp tới không còn đủ headroom | Ưu tiên xử lý trước deploy, chốt phương án thay thế |
| Dữ liệu không cập nhật trong thời gian cho phép | Cảnh báo lỗi thu thập, chưa kết luận còn capacity |

Đây là ngưỡng minh họa. Với tốc độ tăng nhanh hoặc tài nguyên khan hiếm, cần cảnh báo sớm hơn. Với workload gần như cố định, cần tránh tạo cảnh báo lặp không có hành động cụ thể.

### 9.3. Tự động hóa thu thập và cảnh báo

Một thiết kế có thể triển khai:

~~~mermaid
flowchart LR
    A["Tác vụ thu thập theo lịch"] --> B["Limits API và inventory"]
    A --> C["Metrics tải và dữ liệu"]
    B --> D["Chuẩn hóa scope, đơn vị, thời điểm"]
    C --> D
    D --> E["Tính headroom và dự báo"]
    E --> F["Ghi lịch sử và custom metrics"]
    F --> G["Monitoring Alarm / hệ thống cảnh báo"]
    G --> H["Notifications và người phụ trách"]
~~~

Đây là thiết kế tích hợp do đội vận hành xây dựng. Không giả định mọi quota tự có sẵn một metric OCI Monitoring để chọn cảnh báo trực tiếp.

Logic khái quát:

~~~text
Với mỗi resource key đang quản lý:
    Lấy limit, usage và availability nếu được hỗ trợ.
    Nếu dữ liệu lỗi hoặc quá cũ:
        Đánh dấu UNKNOWN, cảnh báo bộ thu thập.
        Không phát kết luận "còn đủ".
    Nếu dữ liệu hợp lệ:
        Đối chiếu nhu cầu bổ sung và thời gian chuẩn bị.
        Phát cảnh báo có scope, số thiếu, ngày cần và người xử lý.
Lưu lần thu thập thành công cuối cho từng resource key.
~~~

Khi viết bộ thu thập, xử lý phân trang, lỗi tạm thời, retry có backoff và giới hạn tần suất. Tránh polling quá dày hoặc tạo metric dimension theo từng request.

Ảnh chụp capacity có thể thay đổi do pipeline khác hoặc đội khác cùng cấp phát. Cần kiểm tra lại trước thao tác lớn; kết quả “PASS” từ hôm trước không phải khóa giữ lại headroom cho hôm nay.

## 10. Kiểm tra host capacity và sử dụng capacity reservations

### 10.1. Capacity report khác với Limits API

OCI có API/CLI tạo Compute capacity report để đánh giá host capacity cho cấu hình shape trong một AD trước khi tạo hoặc thay đổi instance. Khi gọi CLI này, compartment phải là root compartment. Tham khảo [compute-capacity-report create](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/compute/compute-capacity-report/create.html).

Khi sử dụng báo cáo, ghi đúng shape, OCPU, RAM, vị trí và thời điểm được đánh giá. Một kết quả khả dụng là thông tin tại thời điểm kiểm tra; việc đọc báo cáo không tự tạo reservation giữ tài nguyên cho lần triển khai sau.

Không suy luận “hết host” chỉ từ một lỗi tạo instance chung chung. Cần đọc lỗi hoặc work request để phân biệt thiếu capacity với lỗi quota, IAM, image hoặc cấu hình.

### 10.2. Khi nào cân nhắc giữ chỗ

Capacity reservation phù hợp khi chi phí không có tài nguyên đúng lúc lớn hơn chi phí giữ phần tài nguyên chưa dùng, chẳng hạn một đợt chuyển hệ thống có lịch cố định hoặc yêu cầu phục hồi quan trọng.

Reservation Compute gắn với tenancy và AD cụ thể; không bao phủ toàn region. Instance sử dụng reservation phải khớp cấu hình tương ứng, gồm shape và các yêu cầu placement. Phần giữ chỗ chưa dùng vẫn phát sinh chi phí. Xem [Capacity Reservations](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/reserve-capacity.htm).

Trước khi chọn phương án, xác nhận shape, loại tài khoản và các tính năng đi kèm có hỗ trợ reservation. Không mặc định mọi tài nguyên OCI hoặc mọi chế độ Compute đều có cùng cơ chế giữ chỗ.

### 10.3. Kiểm tra số lượng được cấp thực tế

Khi tạo reservation, OCI có thể cấp được ít hơn số yêu cầu, kể cả không giữ được instance nào nếu thiếu capacity. Phải đọc kết quả sau khi yêu cầu hoàn tất. Việc có đối tượng reservation chưa đủ để kết luận đã giữ đủ số lượng. Xem [Creating a Capacity Reservation](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/capacity-reservations-create_tabs.htm).

Đưa vào bằng chứng kế hoạch:

- Số lượng yêu cầu và số lượng thực tế được cấp.
- Cấu hình shape, OCPU, RAM và AD.
- Số lượng đang dùng và chưa dùng.
- Kết quả thử khởi tạo instance theo reservation.
- Chủ sở hữu, ngày rà soát và điều kiện giải phóng.

Không ghi một thử nghiệm “đã đạt” khi mới gửi yêu cầu hoặc chỉ xem cấu hình dự kiến.

### 10.4. Theo dõi quota và vòng đời reservation

Compute có nhóm quota dành cho capacity reservations; cần đối chiếu các mục Reservable và Reserved tương ứng. Khi instance trong reservation bị terminate, capacity quay về reservation; phần chưa dùng không tự biến mất. Xem [Compute Quotas](https://docs.oracle.com/en-us/iaas/Content/Quotas/Concepts/resourcequotas_topic-Compute_Quotas.htm).

Do đó, sau chiến dịch phải kiểm tra cả instance và reservation còn tồn tại. Việc xóa node phục vụ chưa chứng minh đã ngừng chi phí giữ chỗ.

### 10.5. Chuẩn bị phương án thay thế có kiểm chứng

Nếu on-demand capacity không đáp ứng, phương án thay thế có thể gồm shape khác, AD khác hoặc giảm tạm các tác vụ nền. Mỗi phương án phải có điều kiện rõ ràng:

| Phương án | Nội dung cần kiểm tra trước |
| --- | --- |
| Đổi family hoặc thế hệ CPU | Hiệu năng, image, driver, license, bộ nhớ và tên limit áp dụng |
| Chuyển kiến trúc CPU | Binary, thư viện native, image và toàn bộ benchmark liên quan |
| Chuyển AD | Mạng, tài nguyên phụ thuộc, vị trí dữ liệu và thời gian triển khai |
| Chuyển region | Dữ liệu, độ trễ, IAM, kết nối, RTO/RPO và chi phí truyền |
| Giảm tải nền hoặc xếp hàng | Ảnh hưởng nghiệp vụ, thời gian xử lý tồn đọng và giới hạn hàng đợi |

Không coi một shape có nhiều OCPU hơn là phương án tương đương trước khi đo lại throughput và chi phí trên đơn vị công việc.

## 11. Lập kế hoạch tăng limit và phân bổ quota

### 11.1. Phân loại đúng việc cần làm

| Vấn đề | Công việc phù hợp | Đầu mối |
| --- | --- | --- |
| Service limit không đủ | Gửi yêu cầu tăng limit cho đúng tài nguyên và scope | Chủ tenancy hoặc đầu mối làm việc với Oracle |
| Quota compartment không đủ | Rà soát và thay đổi phân bổ nội bộ | Quản trị viên có quyền quản lý quota |
| Hạn mức đủ nhưng thiếu host | Kiểm tra placement, capacity report, reservation hoặc phương án thay thế | Đội hạ tầng |
| IAM chặn thao tác | Bổ sung quyền đúng tài nguyên và compartment | Quản trị IAM |
| Subnet thiếu IP | Điều chỉnh kế hoạch mạng và cách triển khai node | Đội mạng |
| Chi phí vượt mức chấp nhận | Điều chỉnh lịch chạy, cấu hình, phạm vi phục vụ hoặc ngân sách | Chủ ứng dụng và bộ phận tài chính |

Một yêu cầu tăng limit nên có:

- Tenancy, subscription liên quan, region và AD nếu áp dụng.
- Service và limit-name chính xác.
- Giá trị hiện tại, usage hiện tại và giá trị **đích** mong muốn.
- Ngày cần có, dự báo tăng trưởng và sự kiện kinh doanh liên quan.
- Nhu cầu cực đại khi deploy, thay thế hoặc phục hồi.
- Dữ liệu minh chứng, người liên hệ và phương án dự phòng.

Phân biệt “tăng thêm 40” với “nâng tổng limit lên 160”; ghi rõ ý nghĩa để tránh sai mục tiêu.

### 11.2. Lập lịch ngược từ ngày cần dùng

Giả sử cần capacity phục vụ chiến dịch vào ngày D:

~~~text
Ngày D: vận hành ở cấu hình chiến dịch
Trước D: hoàn tất kiểm tra tải và đường chuyển lưu lượng
Trước đó: xác minh tài nguyên, quota và reservation nếu có
Sớm hơn nữa: hoàn tất xử lý các yêu cầu tăng limit hoặc quota
~~~

Khoảng cách giữa các mốc phải dựa trên lịch thay đổi, kinh nghiệm xử lý và độ quan trọng của hệ thống. Với tài nguyên mới hoặc quy mô lớn, cần trao đổi sớm thay vì dựa vào thời gian xử lý từng có ở một lần khác.

Trạng thái công việc nên phân biệt rõ:

~~~text
Dự kiến → Đã gửi → Được chấp thuận → Đã thấy giá trị hiệu lực
→ Đã kiểm tra cấp phát → Sẵn sàng sử dụng
~~~

Yêu cầu được chấp thuận vẫn cần đối chiếu giá trị hiệu lực trong đúng scope. Bằng chứng cấp phát cũng chỉ có ý nghĩa với cấu hình và thời điểm đã thử.

### 11.3. Phân bổ để giữ chỗ cho vận hành

Khi đặt quota cho môi trường phát triển, kiểm thử và production, cần dành phần đủ cho:

- Nhu cầu chạy ổn định.
- Đợt triển khai và rollback.
- Thay thế tài nguyên.
- Các dự án hoặc chiến dịch đã được xác nhận.
- Các thao tác phục hồi cần chạy cùng hệ thống hiện tại.

Quota của các đội có thể cộng lớn hơn service limit nếu tổ chức chủ động chấp nhận phân bổ vượt tổng trần. Khi đó không thể hứa mọi đội đều mở rộng đến quota cùng lúc; phải có quy tắc ưu tiên và cách phối hợp khi trùng nhu cầu.

## 12. Gắn capacity với chi phí và hiệu quả sử dụng

### 12.1. Phân biệt cực đại được phép với tài nguyên phải trả tiền

Quota là ranh giới tiêu thụ; tăng quota không tự tạo instance. Bảng capacity phải có hai cột khác nhau:

- **Mức cực đại cần có khả năng cấp phát**, ví dụ 11 node khi rolling deployment.
- **Mức dự kiến chạy theo thời gian**, ví dụ sáu node ở tải thấp và chín node trong cửa sổ cao điểm.

Đối với shape tính CPU và RAM riêng, có thể ước lượng:

~~~text
C_compute
= OCPU-giờ × đơn_giá_OCPU-giờ
+ GB_RAM-giờ × đơn_giá_GB_RAM-giờ
~~~

Sau đó cộng chi phí lưu trữ, hiệu năng lưu trữ, DB, backup, mạng, quan sát hệ thống và các dịch vụ phụ thuộc theo mô hình giá đang áp dụng.

Nếu có reservation, tách thời gian và số lượng **đã dùng** với **chưa dùng**. Không cộng toàn bộ chi phí reservation lên toàn bộ instance tương ứng như hai tập tài nguyên độc lập.

Bài học không dùng đơn giá cố định. Khi lập phương án thật, lấy giá và điều kiện thương mại đang áp dụng cho đúng cấu hình, region và hợp đồng.

### 12.2. Kết hợp dự báo chi phí với dự báo kỹ thuật

Cost Analysis có chức năng ước tính tương lai từ dữ liệu quá khứ. Kết quả là dự báo, có thể khác thực tế. Nó cần được bổ sung bằng thông tin về chiến dịch, migration hoặc thay đổi kiến trúc chưa xuất hiện trong lịch sử. Xem [Cost Analysis](https://docs.oracle.com/en-us/iaas/Content/Billing/Concepts/costanalysisoverview.htm).

OCI Budgets là soft limit để cảnh báo chi tiêu; nó không tự ngăn tài nguyên vượt ngân sách. Vì vậy vẫn phải lập kế hoạch quota, autoscaling và quy trình xử lý riêng. Xem [Track and Manage Usage and Cost](https://docs.oracle.com/en/solutions/oci-best-practices/track-and-manage-usage-and-cost1.html).

So sánh ít nhất các phương án:

| Phương án | Lợi ích cần đánh giá | Chi phí hoặc điều kiện cần tính |
| --- | --- | --- |
| Chạy thường trực theo tải cao | Ít phụ thuộc mở rộng tức thời | Nhiều thời gian tài nguyên chưa dùng hết |
| Chạy nền tối thiểu và mở rộng theo tải | Gắn chi phí với nhu cầu | Thời gian khởi động, headroom và khả năng cấp phát |
| Giữ chỗ cho phần tải quan trọng | Chuẩn bị capacity cho mốc cần thiết | Chi phí giữ chỗ chưa dùng và phạm vi reservation |
| Tối ưu truy vấn, cache hoặc batch | Giảm tài nguyên trên đơn vị công việc | Công phát triển, kiểm thử và tác động tính đúng đắn |

Tối ưu không chỉ là giảm số node. Một phương án có tổng chi phí cao hơn nhưng giữ được SLO trong chiến dịch quan trọng có thể phù hợp hơn về nghiệp vụ.

### 12.3. Đo chi phí trên đơn vị công việc

~~~text
Chi_phí_trên_1_triệu_request
= Chi_phí_thuộc_phạm_vi / Số_request × 1.000.000

Chi_phí_trên_đơn_hàng
= Chi_phí_thuộc_phạm_vi / Số_đơn_hàng_thành_công
~~~

Giữ nhất quán kỳ thời gian và phạm vi phân bổ. Ghi rõ đã bao gồm DB, backup, log, network và phần dịch vụ dùng chung hay chưa.

Theo dõi đồng thời đơn giá công việc, latency, lỗi và thời gian xử lý tồn đọng. Giảm chi phí bằng cách để request thất bại hoặc batch trễ hạn không đáp ứng mục tiêu capacity.

## 13. Thực hành: lập kế hoạch 90 ngày bằng dữ liệu đọc

Bài thực hành này dùng truy vấn và tính toán; không yêu cầu tạo tài nguyên tính phí hoặc thay đổi quota.

### Bước 1. Chốt phạm vi

Chọn một ứng dụng, compartment, region và AD nếu có. Ghi:

- SLO và cửa sổ cao điểm.
- Đơn vị nghiệp vụ dùng để dự báo.
- Các tài nguyên và nhóm vận hành phụ thuộc.
- Mốc 30, 60, 90 ngày cùng lịch deploy hoặc chiến dịch.

Nếu tenancy chưa có workload, dùng bộ số giả định trong bài và đánh dấu rõ là dữ liệu mô phỏng.

### Bước 2. Lập baseline

Thu thập dữ liệu lịch sử hoặc dùng giả định đã nêu. Tách throughput ứng dụng, tài nguyên đã cấp phát và usage của cả compartment.

Với số liệu thật, ghi thời điểm, nguồn đo và các khoảng thiếu dữ liệu. Chỉ ghi “đã đo” khi có bằng chứng đo tương ứng.

### Bước 3. Tính ba kịch bản nhu cầu

Tính nhu cầu kinh doanh, số node, OCPU, RAM và dung lượng cho từng mốc. Ghi cách làm tròn và các hệ số dự phòng đã áp dụng.

Đối chiếu các kịch bản với lịch sản phẩm. Nếu phải dùng giả định chưa xác nhận, gắn người phụ trách và ngày cần cập nhật.

### Bước 4. Đọc limits và availability

Dùng Console hoặc lệnh CLI ở phần 8. Lấy đúng limit-name và scope cho từng tài nguyên cần kiểm tra.

Với dữ liệu không được API hỗ trợ, ghi `UNKNOWN` cùng cách xác minh tiếp theo. Không điền 0 hoặc “đủ” để hoàn thiện bảng.

### Bước 5. Tính cực đại đồng thời

Lập bảng cho chạy ổn định, rolling deployment, thay thế node và phương án phục hồi. Ghi rõ trạng thái nào có thể xảy ra cùng lúc.

Với ví dụ trong bài:

~~~text
Hiện tại: 6 node
Cực đại kế hoạch: 11 node
Phần cần cấp thêm: 5 node = 20 OCPU + 160 GB RAM
~~~

So phần cần thêm với **headroom còn lại**, không so lại toàn bộ 11 node với headroom, vì sáu node hiện tại đã nằm trong usage.

### Bước 6. Kiểm tra một ràng buộc ở cấp cha

Dùng ví dụ compartment cha chỉ còn 8 OCPU. Giải thích vì sao kế hoạch thêm năm node thất bại dù quota riêng còn 24 OCPU.

Chỉ mô phỏng trên bảng tính hoặc bản kế hoạch; không cần hạ quota thật để tạo lỗi.

### Bước 7. Chốt hành động và cảnh báo

Mỗi thiếu hụt cần có tài nguyên, scope, số lượng, ngày cần, người xử lý và phương án thay thế. Với tài nguyên chưa thiếu, tính ngày dự kiến chạm ngưỡng và ngưỡng cảnh báo phù hợp lead time.

Nếu có đề xuất reservation, ghi chi phí dự kiến, số lượng cần giữ và điều kiện giải phóng. Việc tạo thật thuộc một thay đổi hạ tầng riêng có đánh giá chi phí tương ứng.

### Bước 8. Hoàn thiện bảng quyết định

| Hạng mục | Nhu cầu cực đại | Hiện trạng và headroom | Kết luận | Hành động |
| --- | --- | --- | --- | --- |
| Compute OCPU | Cực đại và phần tăng thêm | Limit, quota, usage đúng scope | Đủ / thiếu / chưa xác minh | Tăng limit, phân bổ quota hoặc đổi phương án |
| RAM | Cực đại và phần tăng thêm | Hạn mức RAM tương ứng | Đủ / thiếu / chưa xác minh | Xử lý độc lập với OCPU |
| Lưu trữ | Dung lượng và hiệu năng | Dữ liệu, phần trống, tốc độ tăng | Ngày đến ngưỡng | Mở rộng hoặc điều chỉnh retention |
| Mạng | IP, throughput, kết nối | Năng lực hiện tại | Đủ / thiếu / chưa xác minh | Điều chỉnh mạng trước khi thêm node |
| Oracle Database | TPS, session, I/O, dữ liệu | Kết quả đo và cấu hình dịch vụ | Nút thắt và điều kiện scale | Tối ưu hoặc thay đổi cấu hình |
| Host capacity | Shape và vị trí cần dùng | Báo cáo, kiểm tra hoặc reservation | Mức độ sẵn sàng đã xác minh | Hoàn tất chuẩn bị trước ngày cần |
| Chi phí | Chi phí theo lịch chạy | Budget và dự báo | Trong / ngoài mức chấp nhận | Chọn phương án và người phê duyệt nội bộ |

## 14. Các lỗi thường gặp và tiêu chí hoàn tất

### 14.1. Những kết luận cần tránh

| Kết luận sai | Hệ quả | Cách sửa |
| --- | --- | --- |
| Còn quota nghĩa là chắc chắn tạo được instance | Kế hoạch phụ thuộc capacity chưa có | Kiểm tra host capacity và phương án giữ chỗ khi cần |
| Còn OCPU là đủ | Bị chặn bởi RAM, IP hoặc tài nguyên phụ thuộc | Theo dõi toàn bộ chuỗi cấp phát |
| Chỉ tính số node phục vụ ổn định | Deploy hoặc thay thế không còn chỗ | Tính số tài nguyên cùng tồn tại ở đỉnh |
| Quota của đội còn nhiều nên không cần xem cấp cha | Bị giới hạn ở compartment cha | Đánh giá cây compartment và usage liên quan |
| Autoscaling sẽ tự giải quyết mọi đợt tăng tải | Scale chậm hoặc bị từ chối | Chuẩn bị ngưỡng, thời gian khởi động và headroom |
| Tăng OCPU chắc chắn sửa được mọi nghẽn DB | Tốn tiền nhưng latency không giảm | Dựa vào CPU, wait, I/O, lock và tải thực tế |
| Xóa node là hết mọi chi phí liên quan | Reservation, volume hoặc backup vẫn còn | Kiểm tra vòng đời từng tài nguyên |
| Dữ liệu thu thập lỗi có nghĩa usage bằng 0 | Bỏ sót tình trạng sắp hết hạn mức | Dùng trạng thái UNKNOWN và cảnh báo độ mới |
| CPU trung bình thấp chứng minh đang dư thừa | Bỏ sót đỉnh tải hoặc áp lực RAM/I/O | Đánh giá theo SLO và cửa sổ tải đại diện |
| Được duyệt tăng limit là đã sẵn sàng | Giá trị hoặc capacity thực tế chưa được kiểm chứng | Đối chiếu giá trị hiệu lực và bằng chứng cấp phát |

### 14.2. Một kế hoạch có thể bàn giao phải thể hiện được gì?

Kế hoạch đạt yêu cầu khi người tiếp nhận có thể trả lời bằng dữ liệu:

1. Đang phục vụ tải bao nhiêu và dự kiến tải nào ở từng mốc?
2. Nhu cầu tài nguyên được suy từ benchmark và SLO nào?
3. Đâu là cực đại đồng thời khi deploy hoặc có sự cố?
4. Những limit và quota nào áp dụng, trong scope nào?
5. Headroom còn bao nhiêu sau khi tính các workload dùng chung?
6. Khi nào phải bắt đầu tăng hạn mức hoặc thay đổi kiến trúc?
7. Khả năng cấp phát đã được kiểm chứng tới mức nào?
8. Chi phí của lịch chạy và phần giữ chỗ là bao nhiêu?
9. Ai xử lý từng thiếu hụt và cần hoàn tất trước ngày nào?
10. Dữ liệu, giả định và kế hoạch sẽ được cập nhật khi nào?

Rà soát lại dự báo sau chiến dịch, thay đổi shape, thay đổi code đáng kể hoặc diễn tập phục hồi. So sánh dự báo với thực tế để điều chỉnh tốc độ tăng, throughput mỗi node, thời gian chuẩn bị và phần dự phòng cho kỳ kế tiếp.

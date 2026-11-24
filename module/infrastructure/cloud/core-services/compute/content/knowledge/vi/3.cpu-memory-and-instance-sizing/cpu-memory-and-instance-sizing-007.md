# Ảnh hưởng của giới hạn mạng và đĩa khi lựa chọn machine type

Khi chọn machine type cho workload trên đám mây, số vCPU và dung lượng RAM chưa mô tả đầy đủ năng lực của máy. Ứng dụng có thể có đủ CPU và bộ nhớ nhưng vẫn chậm vì máy không truyền được đủ dữ liệu qua mạng, không phát sinh đủ thao tác đọc/ghi trên đĩa hoặc phải chờ hàng đợi I/O. Một machine type phù hợp cần đáp ứng đồng thời năng lực tính toán, bộ nhớ, mạng và lưu trữ theo đặc tính tải thực tế.

Trong **CLOUD_CORE_SERVICES_COMPUTE**, hiểu giới hạn mạng và đĩa giúp lựa chọn đúng nhóm instance, dự đoán khả năng phục vụ, bảo đảm tính sẵn sàng và kiểm soát chi phí. Các giới hạn này cũng ảnh hưởng đến cách thiết kế ứng dụng: dịch vụ truyền nhiều dữ liệu cần băng thông và packet rate phù hợp; cơ sở dữ liệu cần IOPS, throughput và latency ổn định; workload kết hợp cả hai cần tránh để các luồng I/O cạnh tranh cùng một giới hạn của instance.

## 1. Machine type cung cấp nhiều năng lực khác nhau

Machine type là cấu hình máy tính toán được nhà cung cấp đám mây cung cấp. Tùy nền tảng, cấu hình có thể xác định số vCPU, RAM, loại CPU, băng thông mạng, năng lực lưu trữ cục bộ, giới hạn lưu trữ mạng và các đặc tính tăng tốc.

Các nhóm machine type thường gặp:

- **General purpose:** cân bằng CPU, RAM và năng lực I/O; phù hợp nhiều ứng dụng web, dịch vụ nghiệp vụ và môi trường phát triển.
- **Compute optimized:** ưu tiên năng lực CPU trên mỗi máy; phù hợp xử lý tính toán, batch hoặc ứng dụng CPU-bound.
- **Memory optimized:** cung cấp nhiều RAM cho cache, cơ sở dữ liệu trong bộ nhớ và workload có working set lớn.
- **Network optimized:** tập trung vào băng thông, packet rate hoặc khả năng xử lý lưu lượng mạng cao.
- **Storage optimized:** cung cấp năng lực lưu trữ cục bộ hoặc thông lượng/IOPS lưu trữ cao cho workload I/O-intensive.
- **Accelerated computing:** bổ sung GPU hoặc bộ tăng tốc chuyên dụng; vẫn cần kiểm tra riêng năng lực mạng và lưu trữ để cấp dữ liệu cho accelerator.

Tên nhóm chỉ mang tính định hướng. Các thế hệ machine type khác nhau trong cùng nhóm có thể có giới hạn mạng, đĩa và cách tính burst khác nhau. Cần đọc thông số của đúng loại máy, vùng triển khai và loại volume dự kiến sử dụng.

## 2. Các giới hạn mạng cần hiểu

Năng lực mạng không chỉ là tốc độ Gbps ghi trong bảng cấu hình. Một ứng dụng có thể bị giới hạn bởi băng thông tổng, số gói tin mỗi giây, số kết nối, một luồng truyền đơn lẻ hoặc độ trễ của đường đi.

### 2.1. Băng thông và thông lượng thực tế

**Băng thông (bandwidth)** là năng lực truyền dữ liệu tối đa của một liên kết hoặc giao diện trong điều kiện xác định. **Thông lượng (throughput)** là lượng dữ liệu thực tế truyền được trong một đơn vị thời gian.

Ví dụ, 1 Gbps tương đương 1 tỷ bit mỗi giây, tức tối đa khoảng 125 MB/s theo đơn vị thập phân trước khi tính overhead giao thức. Thông lượng ứng dụng thường thấp hơn vì Ethernet, IP, TCP/TLS, xác nhận truyền, mã hóa, giới hạn của peer và các thành phần trung gian đều sử dụng một phần năng lực đường truyền.

Khi đọc thông số machine type, cần xác minh:

- Con số công bố là mức tối đa, mức cơ sở hay mức có thể duy trì.
- Băng thông là tổng hai chiều hay được công bố riêng cho ingress và egress.
- Giới hạn áp dụng cho một NIC, toàn máy, một luồng hay tổng các luồng.
- Có cơ chế burst, credit hoặc điều chỉnh theo tải hay không.
- Băng thông có chia sẻ với lưu trữ mạng hoặc dịch vụ khác hay không.

Không nên quy đổi trực tiếp Gbps thành tốc độ tải file của ứng dụng mà bỏ qua overhead, packet loss, latency và giới hạn phía nhận.

### 2.2. Packet per second và kích thước gói

**PPS (packets per second)** là số gói tin được xử lý mỗi giây. Một workload gửi nhiều gói nhỏ có thể chạm giới hạn PPS trước khi dùng hết băng thông theo bit/giây.

Ví dụ, dịch vụ xử lý hàng triệu thông điệp nhỏ, DNS, API có nhiều request ngắn hoặc hệ thống proxy có thể cần PPS cao. Một luồng truyền file lớn thường quan tâm băng thông nhiều hơn, dù vẫn cần đủ PPS để xử lý các gói dữ liệu.

Hai machine type có cùng băng thông Gbps vẫn có thể khác nhau về khả năng xử lý gói nhỏ, số hàng đợi NIC, số luồng mạng và mức CPU cần thiết cho networking. Với workload nhiều kết nối ngắn hoặc gói nhỏ, hãy đo PPS, CPU networking và tỷ lệ packet drop cùng throughput.

### 2.3. Latency, jitter và packet loss

- **Latency:** thời gian để dữ liệu đi từ nguồn đến đích hoặc để một thao tác mạng hoàn tất.
- **Jitter:** mức biến động của latency theo thời gian.
- **Packet loss:** tỷ lệ gói tin bị mất trên đường truyền.

Ứng dụng tương tác, giao dịch và hệ thống phân tán thường nhạy với latency và jitter. TCP có thể phải truyền lại gói bị mất, làm tăng thời gian hoàn tất; với giao thức thời gian thực, packet loss có thể ảnh hưởng trực tiếp đến chất lượng phiên.

Băng thông cao không tự động bảo đảm latency thấp. Một đường truyền có thể còn dư thông lượng nhưng hàng đợi tại NIC, gateway hoặc thiết bị mạng đã tăng độ trễ. Cần đo latency theo phân vị, packet loss và retransmission trong điều kiện tải đại diện.

### 2.4. Giới hạn theo luồng và kết nối

Một số nền tảng áp dụng giới hạn theo luồng (flow), kết nối hoặc hàng đợi mạng. Vì vậy, một ứng dụng dùng một kết nối TCP duy nhất có thể không đạt tổng băng thông tối đa công bố cho cả instance. Nhiều luồng song song đôi khi khai thác được nhiều năng lực hơn, nhưng tăng số luồng cũng làm tăng trạng thái kết nối, chi phí CPU và áp lực lên dịch vụ đích.

Không nên tăng số kết nối vô hạn để vượt một giới hạn. Hãy kiểm tra connection pool, giới hạn file descriptor, NAT/conntrack, cổng tạm thời, giới hạn phía server và chính sách của nhà cung cấp.

## 3. Các giới hạn lưu trữ cần hiểu

Một hệ thống đĩa thường được đánh giá qua ba chỉ số chính:

- **IOPS (I/O operations per second):** số thao tác đọc/ghi mỗi giây.
- **Throughput:** lượng dữ liệu đọc/ghi mỗi giây, thường tính bằng MB/s hoặc MiB/s.
- **Latency:** thời gian hoàn thành một thao tác đọc/ghi.

Ba chỉ số có liên hệ nhưng không thay thế cho nhau. Một volume có thể đạt IOPS cao với thao tác nhỏ nhưng chưa đạt throughput lớn; ngược lại, đọc tuần tự các khối lớn có thể đạt throughput cao với IOPS thấp hơn.

### 3.1. Quan hệ giữa IOPS, kích thước I/O và throughput

Trong điều kiện lý tưởng, throughput gần đúng được tính bằng:

\[
\text{Throughput} \approx \text{IOPS} \times \text{Kích thước mỗi I/O}
\]

Ví dụ, nếu workload thực hiện 8.000 thao tác mỗi giây, mỗi thao tác 16 KiB:

\[
8.000 \times 16\ \text{KiB} = 125\ \text{MiB/s}
\]

Đây là mức dữ liệu lý thuyết trước overhead và các giới hạn khác. Nếu volume chỉ cho phép 100 MiB/s thì throughput sẽ bị chặn ở mức thấp hơn. Nếu machine type chỉ hỗ trợ 80 MiB/s cho lưu trữ mạng thì năng lực hiệu quả cũng không vượt quá giới hạn 80 MiB/s đó.

Kích thước I/O thường được ứng dụng, hệ thống tệp, cơ sở dữ liệu hoặc bộ điều khiển lưu trữ quyết định. Cần dùng kích thước thao tác gần với workload thực tế khi benchmark.

### 3.2. Đọc ngẫu nhiên, đọc tuần tự và ghi

**I/O tuần tự (sequential I/O)** truy cập các vùng dữ liệu liền kề, thường phù hợp đọc file lớn, backup hoặc streaming dữ liệu. Kiểu tải này thường quan tâm throughput.

**I/O ngẫu nhiên (random I/O)** truy cập các vị trí phân tán, thường gặp ở cơ sở dữ liệu, index và workload truy cập nhiều bản ghi nhỏ. Kiểu tải này thường quan tâm IOPS và latency.

Tỷ lệ đọc/ghi cũng quan trọng. Một workload ghi đồng bộ có thể chờ xác nhận dữ liệu bền vững trước khi tiếp tục; một workload đọc cache có thể giảm số lần truy cập đĩa. Benchmark chỉ dùng đọc tuần tự sẽ không đại diện tốt cho cơ sở dữ liệu có nhiều thao tác đọc ngẫu nhiên và ghi nhỏ.

### 3.3. Queue depth và latency

**Queue depth** là số yêu cầu I/O đang chờ hoặc đang được xử lý. Khi nhiều yêu cầu đến nhanh hơn khả năng hoàn tất, hàng đợi tăng và latency thường tăng theo.

Tăng queue depth có thể giúp thiết bị tận dụng tốt hơn khả năng xử lý song song, nhưng sau một điểm nhất định, thêm yêu cầu chỉ làm thời gian chờ dài hơn. Với workload nhạy latency, cần tìm queue depth mà tại đó throughput đạt yêu cầu trong khi p95/p99 vẫn nằm trong SLO.

Không nên đánh giá đĩa chỉ qua IOPS tối đa. Một volume đạt IOPS cao nhưng latency p99 quá lớn vẫn có thể không phù hợp với giao dịch cần phản hồi nhanh.

## 4. Giới hạn ở cấp instance và cấp volume

Đây là điểm quan trọng khi chọn machine type: năng lực lưu trữ có thể bị giới hạn đồng thời ở cấp volume và cấp instance.

Một volume có thể được cấp một mức IOPS và throughput nhất định. Tuy nhiên, machine type gắn volume đó cũng có thể có trần tổng băng thông lưu trữ. Nếu gắn nhiều volume, tổng năng lực của các volume vẫn có thể bị chặn bởi trần của instance.

Có thể hình dung năng lực lưu trữ khả dụng bị giới hạn bởi giá trị nhỏ nhất trong các giới hạn áp dụng:

\[
\text{Năng lực khả dụng} \leq
\min(\text{giới hạn instance},\ \text{tổng giới hạn volume},\ \text{giới hạn burst/quota})
\]

Đây là mô hình tổng quát. Cách tính chính xác phụ thuộc nhà cung cấp, loại volume, số volume, vùng và chính sách chia sẻ.

Ví dụ:

| Thành phần | Giới hạn giả định |
| --- | ---: |
| Machine type: băng thông lưu trữ tối đa | 500 MiB/s |
| Volume A: throughput được cấp | 300 MiB/s |
| Volume B: throughput được cấp | 300 MiB/s |
| Tổng theo hai volume | 600 MiB/s |
| Mức tối đa qua instance | 500 MiB/s |

Mặc dù hai volume cộng lại có thể cung cấp 600 MiB/s theo thông số riêng, machine type chỉ cho phép tối đa 500 MiB/s ở tầng instance. Khi cả hai volume cùng tải cao, chúng phải chia sẻ giới hạn đó.

Một số nhà cung cấp còn có giới hạn IOPS riêng ở cấp instance, giới hạn theo kích thước volume, hoặc mức hiệu năng cơ sở và burst. Cần kiểm tra tất cả các giới hạn cùng lúc trước khi chọn cấu hình.

## 5. Các kiểu lưu trữ và ảnh hưởng đến lựa chọn máy

### 5.1. Block storage qua mạng

Block storage được cung cấp như thiết bị khối có thể gắn vào máy ảo. Dữ liệu thường được lưu trên hệ thống lưu trữ phân tán của nhà cung cấp, tách khỏi vòng đời của máy ảo ở mức độ nhất định.

Ưu điểm thường gặp là có thể chọn dung lượng, hiệu năng, snapshot và cơ chế sao lưu riêng. Tuy nhiên, I/O phải đi qua hạ tầng mạng lưu trữ và có thể chịu giới hạn ở volume, instance hoặc đường truyền dùng chung.

Khi chọn machine type cho block storage, hãy kiểm tra giới hạn IOPS và throughput của volume, trần lưu trữ của instance, số volume được hỗ trợ và liệu lưu lượng storage có dùng chung ngân sách mạng với traffic ứng dụng hay không.

### 5.2. Local SSD/NVMe

Local SSD hoặc NVMe gắn trực tiếp với host thường có latency thấp và throughput cao. Loại lưu trữ này phù hợp cache, scratch data, dữ liệu trung gian, index có thể tái tạo hoặc workload cần I/O rất nhanh.

Điểm cần chú ý là dữ liệu local có thể gắn với vòng đời của instance hoặc host. Khi dừng, xóa, thay đổi host hay gặp sự cố, dữ liệu có thể không được bảo toàn tùy loại dịch vụ và chính sách. Không nên dùng local ephemeral storage làm bản lưu duy nhất cho dữ liệu quan trọng nếu dịch vụ không cam kết độ bền phù hợp.

Với local SSD, cần xem số thiết bị, dung lượng, hiệu năng tổng, giới hạn theo instance và cơ chế RAID hoặc ghép thiết bị nếu ứng dụng cần. Machine type có nhiều vCPU nhưng ít local storage chưa chắc phù hợp với workload I/O-intensive.

### 5.3. Các mức hiệu năng và cơ chế burst

Các dịch vụ lưu trữ có thể cung cấp volume mục đích chung, volume provisioned IOPS, volume tối ưu throughput hoặc thiết bị HDD/SSD theo các mức giá khác nhau. Một số loại có hiệu năng phụ thuộc dung lượng; một số loại cho phép burst trong một khoảng thời gian hoặc dùng credit.

Nếu workload có đỉnh tải ngắn, burst có thể đáp ứng tốt. Nếu workload duy trì tải cao liên tục, cần sizing theo năng lực duy trì sau khi credit cạn. Hãy xác định rõ baseline, mức burst, thời gian tích lũy/tiêu thụ credit và cách metric thể hiện việc bị giới hạn.

## 6. Mạng và lưu trữ có thể dùng chung giới hạn

Trong nhiều môi trường đám mây, block storage được truy cập qua mạng nội bộ của nhà cung cấp. Một số machine type có giới hạn tổng cho lưu lượng mạng và lưu lượng storage, hoặc có các ngân sách riêng nhưng cùng dùng hạ tầng vật lý phía dưới.

Điều này có thể tạo ra cạnh tranh giữa:

- Traffic ứng dụng gửi và nhận qua NIC.
- Đọc/ghi volume từ máy ảo.
- Sao lưu, snapshot hoặc replication.
- Truyền dữ liệu giữa các node trong cụm.

Ví dụ, một máy vừa phục vụ API truyền file vừa chạy job quét dữ liệu lớn từ volume mạng. Hai loại tải có thể cùng làm tăng lưu lượng trên hạ tầng mạng của instance. API có thể chậm dù CPU còn dư và volume chưa đạt giới hạn riêng.

Không phải nhà cung cấp nào cũng gộp các giới hạn này. Cần xem tài liệu của đúng machine family để biết băng thông mạng và lưu trữ được tính riêng hay chia sẻ, đồng thời kiểm tra metric quan sát được.

## 7. Xác định workload cần mạng hay đĩa ở mức nào

Trước khi chọn machine type, hãy phân loại workload theo kiểu I/O.

| Workload | Đặc tính mạng | Đặc tính lưu trữ |
| --- | --- | --- |
| API phục vụ nội dung lớn | Egress cao, nhiều kết nối, cần throughput ổn định | Có thể cần đọc file lớn theo luồng |
| Cơ sở dữ liệu giao dịch | Nhiều request nhỏ, nhạy latency và kết nối | I/O ngẫu nhiên, ghi đồng bộ, IOPS và p99 latency quan trọng |
| Data warehouse/ETL | Truyền dữ liệu giữa các node hoặc dịch vụ | Đọc/ghi tuần tự lớn, throughput cao |
| Cache phân tán | Nhiều gói nhỏ, PPS và latency quan trọng | Có thể cần persistence hoặc snapshot tùy yêu cầu |
| Backup/replication | Egress/ingress kéo dài, có thể cạnh tranh với traffic chính | Đọc dữ liệu lớn và ghi bản sao liên tục |
| Streaming | Kết nối dài, nhiều thông điệp, cần kiểm soát jitter | Ghi log hoặc segment theo chu kỳ, phụ thuộc retention |
| AI/ML | Truyền dữ liệu giữa worker và accelerator | Đọc dataset, checkpoint và lưu model có thể tạo tải lớn |

Một workload có thể thay đổi đặc tính theo giai đoạn. Ví dụ, cơ sở dữ liệu khi khởi động có thể đọc nhiều dữ liệu từ đĩa, khi hoạt động ổn định có thể chủ yếu phục vụ từ cache, còn khi checkpoint hoặc backup sẽ tạo tải ghi/đọc lớn.

## 8. Cách tính sơ bộ nhu cầu mạng và đĩa

Ước lượng ban đầu giúp thu hẹp nhóm machine type trước khi benchmark. Kết quả cần cộng thêm overhead, tải đỉnh, tăng trưởng và biên dự phòng.

### 8.1. Ước lượng băng thông mạng

Với một API, có thể ước lượng egress ứng dụng:

\[
\text{Egress} \approx
\text{Số response mỗi giây} \times
\text{Kích thước response trung bình}
\]

Ví dụ, dịch vụ trả 200 response/giây, mỗi response trung bình 80 KB:

\[
200 \times 80\ \text{KB} = 16\ \text{MB/s}
\]

Tương đương khoảng 128 Mbps theo đơn vị thập phân, chưa tính overhead và các traffic khác. Khi sizing, cần cộng thêm request ingress, replication, log, health check, backup và tải tăng đột biến. Nếu response có phân bố kích thước lệch, hãy xem cả kích thước p95/p99 và lưu lượng ở giờ cao điểm.

### 8.2. Ước lượng năng lực đĩa

Giả sử cơ sở dữ liệu cần 12.000 IOPS với kích thước I/O trung bình 8 KiB:

\[
12.000 \times 8\ \text{KiB} = 93.75\ \text{MiB/s}
\]

Như vậy, volume cần đáp ứng cả mức IOPS và throughput tương ứng. Nếu machine type có trần lưu trữ 80 MiB/s thì máy vẫn có thể trở thành nút thắt dù volume được cấp nhiều IOPS hơn. Nếu latency tăng khi queue depth cao, cần kiểm tra giới hạn duy trì và mô hình đọc/ghi trước khi tăng cấu hình.

### 8.3. Dự phòng và tải đỉnh

Không nên chọn machine type đúng bằng tải trung bình. Cần tính:

- Tải cao điểm và thời gian duy trì đỉnh.
- Tăng trưởng dữ liệu, số người dùng và số kết nối.
- Traffic nền như backup, replication, logging và monitoring.
- Mức giảm hiệu năng khi burst credit cạn hoặc có tranh chấp.
- Năng lực còn lại khi một node hoặc một đường truyền gặp sự cố.

Biên dự phòng phải dựa trên SLO và mô hình tải. Dự phòng quá thấp gây bão hòa; dự phòng quá cao làm chi phí tăng mà không tạo thêm giá trị tương xứng.

## 9. Quy trình chọn machine type

Một quy trình có thể áp dụng cho workload mới hoặc khi tối ưu hệ thống hiện tại:

1. **Xác định mục tiêu dịch vụ:** throughput, latency p95/p99, tỷ lệ lỗi, thời gian hoàn thành job và yêu cầu tính sẵn sàng.
2. **Đo baseline:** thu thập traffic ingress/egress, PPS, kết nối, latency mạng, IOPS, kích thước I/O, throughput đĩa và queue depth.
3. **Phân loại kiểu tải:** mạng nhiều gói nhỏ hay truyền file lớn; đĩa ngẫu nhiên hay tuần tự; đọc nhiều hay ghi nhiều; tải ổn định hay burst.
4. **Đọc giới hạn nền tảng:** kiểm tra mức tối đa và mức duy trì của NIC, instance, volume, storage pool, quota và credit.
5. **Tính giới hạn tổng hợp:** kiểm tra các volume có chia sẻ trần instance không; traffic mạng và storage có dùng chung ngân sách không.
6. **Chọn nhóm machine type:** network optimized cho tải mạng cao, storage optimized cho I/O cao, hoặc general purpose khi các nhu cầu cân bằng.
7. **Benchmark trên cấu hình đại diện:** dùng dữ liệu và tỷ lệ đọc/ghi gần với production; tăng tải từng bước.
8. **Kiểm tra điểm bão hòa:** tìm lúc throughput không tăng nhưng latency, queue depth, packet drop hoặc lỗi bắt đầu tăng.
9. **Đánh giá chi phí:** so sánh chi phí machine, volume, IOPS/throughput provisioned, traffic truyền dữ liệu và capacity dự phòng.
10. **Triển khai và giám sát:** theo dõi metric sau thay đổi, xác nhận SLO và giữ khả năng quay lại cấu hình trước.

## 10. Theo dõi và chẩn đoán giới hạn

Khi ứng dụng chậm, hãy xác định tầng nào đang giới hạn trước khi đổi machine type.

| Tầng | Chỉ số cần xem | Dấu hiệu cần điều tra |
| --- | --- | --- |
| Ứng dụng | Request latency, timeout, throughput, queue, retry | Tác vụ chậm ở bước gọi dịch vụ nào? |
| Mạng instance | Ingress/egress, PPS, packet drop, retransmission, connection count | Có chạm giới hạn NIC, PPS hoặc kết nối không? |
| Đường truyền | Latency, jitter, loss, throughput đến peer | Điểm nghẽn nằm ở máy, gateway hay phía đích? |
| Volume | IOPS, throughput, read/write latency, burst balance/credit | Volume có đạt giới hạn được cấp hoặc hết credit không? |
| Instance storage | Throughput/IOPS tổng, queue, giới hạn lưu trữ của máy | Nhiều volume có cùng chạm trần instance không? |
| Hệ điều hành | I/O wait, queue depth, CPU softirq, socket statistics | CPU có bận xử lý mạng hoặc chờ I/O không? |

Trên Linux, các công cụ như **iostat**, **sar**, **ss**, **ip -s link**, **vmstat** và **ethtool** có thể hỗ trợ quan sát hệ điều hành và giao diện mạng nếu được cài đặt và quyền truy cập cho phép. Công cụ không thay thế metric của nhà cung cấp: một số giới hạn nằm ở tầng host hoặc hạ tầng mạng mà máy ảo không quan sát trực tiếp được.

Hãy đồng bộ thời gian giữa metric ứng dụng và metric hạ tầng. Nếu latency API tăng đúng lúc volume queue tăng, đó là bằng chứng để điều tra storage. Nếu packet drop hoặc retransmission tăng cùng lúc timeout, cần điều tra mạng. Một chỉ số đơn lẻ không đủ chứng minh nguyên nhân; cần đối chiếu nhiều tín hiệu và kiểm tra theo tải đại diện.

## 11. Ví dụ thực tế: chọn máy cho dịch vụ cơ sở dữ liệu

Một nhóm triển khai cơ sở dữ liệu giao dịch trên máy ảo. Máy hiện tại có đủ RAM để giữ working set và CPU utilization trung bình thấp, nhưng giờ cao điểm xuất hiện truy vấn chậm. Metric cho thấy IOPS tăng, p99 latency của volume cao và hàng đợi I/O kéo dài. Máy cũng chạy tác vụ backup, tạo thêm lưu lượng đọc từ volume và truyền dữ liệu qua mạng.

Nhóm kiểm tra theo trình tự:

1. Đo tỷ lệ đọc/ghi, kích thước I/O và IOPS ở giờ bình thường lẫn giờ cao điểm.
2. Đối chiếu throughput/IOPS được cấp của volume với trần lưu trữ ở cấp instance.
3. Kiểm tra backup có chạy trùng giờ cao điểm và có chia sẻ giới hạn mạng hoặc storage với truy vấn hay không.
4. Benchmark volume với kích thước I/O và tỷ lệ đọc/ghi gần production.
5. So sánh machine type có trần storage cao hơn, hoặc tách backup sang thời điểm khác hay máy riêng.
6. Đánh giá p95/p99 truy vấn, thời gian backup, độ trễ replication và tổng chi phí sau thay đổi.

Nếu volume được cấp đủ IOPS nhưng instance chạm trần storage, nâng riêng thông số volume sẽ không giải quyết nút thắt. Nếu backup gây tranh chấp, tách lịch hoặc tách workload có thể cải thiện truy vấn mà không cần tăng toàn bộ cấu hình máy. Nếu latency vẫn cao khi các giới hạn đều còn dư, cần tiếp tục xem execution plan, cache, lock và thiết kế truy vấn.

## 12. Những sai lầm thường gặp

- Chọn máy chỉ theo vCPU và RAM, bỏ qua giới hạn NIC và lưu trữ.
- Nhầm Gbps với GB/s hoặc MB/s; không phân biệt bit và byte.
- Chỉ xem băng thông mà bỏ qua PPS, latency, jitter và packet loss.
- Chỉ xem IOPS mà không xét kích thước I/O, throughput và latency.
- Cộng thông số của nhiều volume mà quên trần tổng ở cấp instance.
- Giả định volume riêng đồng nghĩa với thiết bị vật lý riêng hoặc không có tranh chấp.
- Dùng local ephemeral disk làm nơi lưu duy nhất cho dữ liệu cần độ bền.
- Sizing theo mức burst ngắn hạn nhưng workload lại chạy tải cao liên tục.
- Tăng số kết nối hoặc queue depth vô hạn để cố đạt throughput cao hơn.
- Benchmark bằng dữ liệu hoặc tỷ lệ đọc/ghi không giống production.
- Không tính backup, replication, logging và traffic nền vào ngân sách mạng/đĩa.

## 13. Nguyên tắc lựa chọn và vận hành

1. **Xem toàn bộ cấu hình:** machine type phải phù hợp với CPU, RAM, mạng và lưu trữ cùng lúc.
2. **Đọc đúng loại giới hạn:** phân biệt mức tối đa, mức duy trì, giới hạn theo luồng, theo volume và theo instance.
3. **Đo đúng workload:** dùng traffic, kích thước gói, kích thước I/O và tỷ lệ đọc/ghi đại diện.
4. **Theo dõi latency phân vị:** throughput cao không có ý nghĩa nếu p95/p99 vượt SLO.
5. **Tính giới hạn tổng hợp:** kiểm tra các volume và luồng mạng có cùng chia sẻ một trần năng lực hay không.
6. **Chọn lưu trữ theo độ bền:** local SSD phù hợp dữ liệu tạm hoặc có thể tái tạo; dữ liệu quan trọng cần dịch vụ có cam kết độ bền phù hợp.
7. **Tách tải khi cần:** backup, batch và replication có thể cần lịch riêng hoặc tài nguyên riêng để bảo vệ traffic chính.
8. **Đánh giá chi phí trên đơn vị công việc:** tính cả machine, volume, IOPS, throughput, truyền dữ liệu và dự phòng.

Lựa chọn machine type chính xác bắt đầu từ cách ứng dụng trao đổi dữ liệu với bên ngoài và truy cập lưu trữ. Khi xác định được giới hạn mạng, IOPS, throughput và latency ở từng tầng, đội kỹ thuật có thể chọn cấu hình phù hợp, tránh trả chi phí cho năng lực không sử dụng và giảm nguy cơ nút thắt khi tải tăng.

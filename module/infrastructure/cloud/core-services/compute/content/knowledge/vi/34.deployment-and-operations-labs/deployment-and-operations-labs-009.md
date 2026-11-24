# Đo hiệu năng, right-size cấu hình và tính chi phí workload

## Mục tiêu bài học

Sau bài học này, bạn có thể:

- Xây dựng baseline hiệu năng cho một workload chạy trên máy ảo cloud.
- Đo CPU, bộ nhớ, lưu trữ, mạng, độ trễ và thông lượng bằng metric hệ điều hành và nền tảng.
- Phân tích điểm nghẽn để điều chỉnh cấu hình CPU, RAM, disk và network phù hợp.
- Ước tính chi phí theo thời gian chạy và các tài nguyên đi kèm.
- So sánh chi phí trên mỗi đơn vị công việc, kiểm chứng thay đổi và lập kế hoạch tối ưu liên tục.

## 1. Bắt đầu từ workload và mục tiêu dịch vụ

Right-sizing là quá trình chọn cấu hình tài nguyên vừa đủ để workload đạt yêu cầu hiệu năng, độ tin cậy và khả năng mở rộng với chi phí hợp lý. Không thể chọn cấu hình chỉ dựa trên tên ứng dụng hoặc mức CPU trung bình trong một khoảng thời gian ngắn. Cần hiểu workload thực sự làm gì, tải thay đổi ra sao và người dùng cần nhận kết quả trong bao lâu.

Trước khi đo, hãy mô tả workload:

- **Kiểu xử lý:** web/API, batch, xử lý dữ liệu, database, cache, build hoặc tác vụ tính toán.
- **Mẫu tải:** số request/giây, số job, số người dùng đồng thời, kích thước dữ liệu và thời điểm cao điểm.
- **Đặc tính tài nguyên:** CPU-bound, memory-bound, I/O-bound hay network-bound.
- **Mục tiêu dịch vụ:** throughput, p95/p99 latency, tỷ lệ lỗi, thời gian hoàn thành batch và thời gian phục hồi.
- **Ràng buộc vận hành:** số bản sao tối thiểu, vùng triển khai, yêu cầu dự phòng, giấy phép phần mềm và cửa sổ bảo trì.

Ví dụ, API tra cứu đơn hàng có thể cần p95 dưới 300 ms ở 500 request/giây. Một batch xử lý ảnh có thể chấp nhận hoàn thành trong 40 phút nhưng phải xử lý 100.000 ảnh mỗi đêm. Hai workload có mục tiêu khác nhau nên cách chọn CPU, RAM, disk và mô hình tính phí cũng khác nhau.

Hãy xác định trước mức tải đại diện và mức tải đỉnh. Nếu chỉ benchmark ở tải thấp, cấu hình được chọn có thể thiếu tài nguyên khi concurrency tăng. Nếu chỉ benchmark ở mức đỉnh cực đoan, hệ thống có thể bị cấp dư tài nguyên trong phần lớn thời gian.

## 2. Thiết lập baseline và đo hiệu năng

Baseline là tập số liệu mô tả hành vi hiện tại của workload khi chạy trên cấu hình và dữ liệu xác định. Ghi nhận cả cấu hình máy, hệ điều hành, phiên bản ứng dụng, loại volume, loại instance, số bản sao và thời điểm đo để có thể so sánh công bằng.

### 2.1. Các nhóm metric cần theo dõi

| Nhóm | Metric nên quan sát | Dấu hiệu cần điều tra |
|---|---|---|
| CPU | Utilization, load average, thời gian user/system/iowait, CPU throttling nếu có | CPU bão hòa kéo dài, hàng đợi runnable tăng hoặc thời gian xử lý tăng |
| Bộ nhớ | Used/available, working set, swap, page fault, OOM kill | RAM gần cạn, swap tăng, tiến trình bị OOM hoặc GC liên tục |
| Lưu trữ | IOPS, throughput, latency, queue length, dung lượng sử dụng | I/O chờ cao, queue dài, latency tăng hoặc volume hết dung lượng |
| Mạng | Bytes/s, packets/s, retransmission, lỗi/drop, latency | Băng thông hoặc PPS chạm giới hạn, retransmission tăng |
| Ứng dụng | Request rate, throughput, p50/p95/p99, error rate, queue depth | Độ trễ tăng dù CPU thấp, lỗi timeout hoặc backlog tích tụ |
| Nền tảng | Instance status, burst balance/credit, autoscaling, throttling | Tài nguyên bị giới hạn bởi loại instance hoặc chính sách scale |

CPU utilization thấp không chứng minh workload không cần thêm tài nguyên. Ứng dụng có thể đang chờ disk, database, lock hoặc API bên ngoài. Tương tự, CPU cao trong một đợt ngắn có thể là hành vi bình thường nếu p95, throughput và error rate vẫn đạt mục tiêu.

### 2.2. Công cụ trên Linux

Có thể dùng các lệnh sau để quan sát tại máy ảo:

~~~bash
uptime
top
free -h
vmstat 1
iostat -xz 1
df -h
ip -s link
ss -s
~~~

- uptime và load average cho biết mức độ có việc chờ thực thi; cần so với số vCPU và loại workload.
- top hoặc công cụ tương đương giúp tìm tiến trình tiêu thụ CPU và RAM.
- free -h cho biết bộ nhớ available; không nên chỉ nhìn cột free vì Linux dùng RAM làm cache.
- vmstat cho thấy runnable queue, swap, I/O wait và hoạt động hệ thống theo thời gian.
- iostat -xz giúp quan sát độ trễ và hàng đợi thiết bị block nếu sysstat đã được cài.
- df -h kiểm tra dung lượng filesystem; disk đầy có thể gây lỗi dù IOPS vẫn thấp.
- ip -s link và ss -s hỗ trợ phát hiện lỗi interface, packet drop và số lượng socket.

Chạy lệnh trong khoảng thời gian có tải đại diện. Một ảnh chụp tại một thời điểm không đủ để kết luận. Nếu chưa cài công cụ, hãy dùng gói phù hợp với hệ điều hành và chính sách image của tổ chức.

### 2.3. Metric từ nền tảng cloud

Với Amazon EC2 và CloudWatch, có thể bắt đầu từ CPUUtilization, NetworkIn, NetworkOut và trạng thái kiểm tra instance. Các metric EBS như VolumeReadOps, VolumeWriteOps, VolumeReadBytes, VolumeWriteBytes và VolumeQueueLength giúp đánh giá hoạt động lưu trữ. Bộ metric cụ thể phụ thuộc loại volume và cấu hình.

Metric bộ nhớ và filesystem bên trong máy ảo thường không được thu thập mặc định bởi metric EC2 cơ bản. Cài CloudWatch Agent hoặc agent giám sát được phê duyệt để thu thập memory used/available, disk used và các metric hệ điều hành. Cần kiểm tra chu kỳ thu thập, độ phân giải, chi phí ingest và retention của dữ liệu giám sát.

Trên Azure, có thể dùng Azure Monitor và VM Insights. Trên Google Cloud, dùng Cloud Monitoring và Ops Agent. Luôn kiểm tra định nghĩa metric, đơn vị, chu kỳ lấy mẫu và phạm vi tổng hợp của từng nền tảng trước khi so sánh.

## 3. Thiết kế phép thử có thể lặp lại

Một phép benchmark có giá trị phải tái lập được và không làm ảnh hưởng người dùng production.

1. Chọn môi trường thử nghiệm có cấu hình gần production, dùng cùng phiên bản ứng dụng và loại dữ liệu đại diện.
2. Ghi lại instance type, vCPU, RAM, kiến trúc, disk type/size, giới hạn IOPS/throughput, mạng, hệ điều hành và số bản sao.
3. Tạo dữ liệu thử nghiệm đủ lớn để thể hiện hành vi thực tế, nhưng không chứa dữ liệu nhạy cảm.
4. Chạy một giai đoạn warm-up để cache, JIT hoặc connection pool ổn định.
5. Tăng tải theo các mức xác định, giữ mỗi mức đủ lâu để quan sát metric ổn định.
6. Ghi throughput, p50/p95/p99, error rate, CPU, memory, disk, network và queue depth.
7. Lặp lại phép thử và so sánh cùng điều kiện. Đánh dấu những lần bị ảnh hưởng bởi tác vụ nền hoặc sự cố phụ thuộc.

Ví dụ với API, có thể thử 100, 250, 500 và 750 request/giây, giữ mỗi mức 10 phút sau warm-up. Các con số này chỉ minh họa cách chia mức tải; hãy chọn theo SLO và lưu lượng dự kiến. Dừng thử nghiệm nếu error rate hoặc latency vượt ngưỡng an toàn đã thống nhất.

Đối với batch, ghi thời gian hoàn thành, số record xử lý/giây, CPU time, I/O wait, memory peak và chi phí cho một batch. Không chỉ ghi tổng thời gian vì hai cấu hình có thể hoàn thành cùng lúc nhưng tiêu thụ tài nguyên và chi phí rất khác nhau.

## 4. Phân tích điểm nghẽn và right-size CPU

Khi CPU là nút thắt, dấu hiệu thường gồm CPU utilization cao kéo dài, runnable queue tăng, throughput không tăng tương ứng với tải và latency xấu đi. Cần phân biệt CPU user, system và iowait để tránh tăng vCPU khi ứng dụng thực tế đang chờ I/O.

Quy trình điều chỉnh:

1. Kiểm tra mức CPU ở giờ bình thường và giờ cao điểm, không chỉ giá trị trung bình cả ngày.
2. Xác định tiến trình hoặc thread tiêu thụ CPU; tìm vòng lặp tốn kém, serialization, nén/mã hóa hoặc truy vấn làm việc quá nhiều.
3. Thử instance có số vCPU lớn hơn hoặc kiến trúc khác nếu workload có thể tận dụng song song.
4. Đo lại throughput và p95/p99. Nếu throughput tăng nhưng latency không cải thiện, có thể còn nút thắt khác.
5. Nếu CPU luôn thấp và không có burst cần thiết, thử cấu hình nhỏ hơn rồi xác minh SLO.

Với instance burstable, cần theo dõi CPU credit hoặc chỉ số burst balance theo mô hình của nhà cung cấp. Mức CPU trung bình thấp có thể che giấu việc workload thường xuyên tiêu hết credit rồi bị giới hạn hiệu năng. Đối với workload chạy liên tục, loại instance có hiệu năng CPU ổn định có thể phù hợp hơn dù đơn giá khác.

Không giảm vCPU chỉ dựa trên CPUUtilization trung bình. Một luồng đơn có thể bão hòa một core trong khi mức tổng thể trên máy nhiều core vẫn thấp. Hãy kiểm tra theo từng core và đặc tính song song của ứng dụng.

## 5. Right-size bộ nhớ, lưu trữ và mạng

### 5.1. Bộ nhớ

Quan sát memory available, working set, swap, page fault và OOM kill. Xác định mức sử dụng cao nhất trong tải đỉnh và khoảng tăng trưởng cần dự phòng.

Nếu memory gần cạn, tìm nguyên nhân trước khi tăng RAM: memory leak, cache không giới hạn, buffer quá lớn hoặc số worker đồng thời vượt thiết kế. Nếu tăng RAM, chạy lại benchmark và kiểm tra liệu thời gian xử lý có cải thiện hay chỉ làm tăng chi phí.

Trên máy ảo Linux, bộ nhớ dùng cho page cache có thể được thu hồi; vì vậy available thường hữu ích hơn free. Trên container, cần xem cả giới hạn memory của container và memory của node. Một tiến trình có thể bị OOM kill do vượt container limit dù máy chủ vẫn còn RAM.

### 5.2. Lưu trữ

Đánh giá đồng thời dung lượng, IOPS, throughput và latency. Volume đủ dung lượng chưa chắc đủ hiệu năng. Database thường nhạy với latency và IOPS ngẫu nhiên; xử lý file lớn thường nhạy với throughput tuần tự.

Với EBS, có thể chọn loại volume phù hợp rồi điều chỉnh dung lượng, IOPS và throughput theo khả năng của loại volume. Với gp3, IOPS và throughput có thể được cấu hình độc lập trong giới hạn dịch vụ. Đừng tăng IOPS nếu ứng dụng đang chờ lock hoặc CPU; xác định đúng nguyên nhân từ queue và latency trước.

Kiểm tra cả filesystem, inode, log growth, snapshot và dung lượng tạm. Nếu volume thường xuyên gần đầy, hãy mở rộng dung lượng hoặc thiết lập lifecycle cho log và dữ liệu tạm.

### 5.3. Mạng

Theo dõi throughput, packets per second, retransmission, packet drop và độ trễ đến dịch vụ phụ thuộc. Loại instance có giới hạn mạng khác nhau; một workload truyền dữ liệu lớn có thể cần instance/network tier cao hơn dù CPU còn thấp.

Nếu mạng bão hòa, kiểm tra kích thước payload, số kết nối, keep-alive, nén, vị trí vùng của dịch vụ phụ thuộc và khả năng tận dụng batch. Tăng băng thông không giải quyết được độ trễ do database ở region khác hoặc DNS lookup lặp lại.

## 6. Ví dụ thực hành right-size một API trên EC2

Giả sử API tra cứu đơn hàng đang chạy trên hai máy ảo cùng loại. Trong giờ cao điểm, phép thử cho kết quả:

| Chỉ số | Baseline |
|---|---:|
| Request rate | 400 request/giây |
| p50 latency | 75 ms |
| p95 latency | 420 ms |
| Error rate | 0,4% |
| CPU trung bình trong giờ cao điểm | 88% |
| Memory available thấp nhất | 1,1 GiB |
| Disk I/O wait | 2% |
| Network throughput | 35% giới hạn đo được |

CPU cao và p95 tăng trong khi disk I/O wait thấp, memory vẫn còn và mạng chưa bão hòa. Đây là dấu hiệu nên thử tăng năng lực CPU hoặc tối ưu đường xử lý CPU trước khi tăng disk hay network.

Giả sử thử cấu hình có thêm vCPU cho kết quả:

| Chỉ số | Baseline | Sau điều chỉnh |
|---|---:|---:|
| Request rate | 400 request/giây | 400 request/giây |
| p95 latency | 420 ms | 235 ms |
| Error rate | 0,4% | 0,1% |
| CPU cao điểm | 88% | 54% |
| Memory available thấp nhất | 1,1 GiB | 1,0 GiB |

Nếu tải cao điểm tiếp tục tăng, cần kiểm tra khả năng scale ngang và giới hạn database connection. Không mặc định tăng kích thước instance là giải pháp duy nhất. Có thể tăng số bản sao, giảm công việc mỗi request, cache kết quả phù hợp hoặc tối ưu truy vấn.

Đây là số liệu minh họa cho cách ra quyết định, không phải cam kết hiệu năng của một loại instance cụ thể. Kết quả thật phụ thuộc mã ứng dụng, dữ liệu, vùng cloud và cấu hình dịch vụ.

## 7. Xây dựng mô hình chi phí workload

Chi phí workload thường gồm nhiều thành phần. Chỉ nhân giá máy ảo theo số giờ sẽ bỏ sót lưu trữ, truyền dữ liệu, địa chỉ IP, NAT, load balancer, backup, log, license và các dịch vụ phụ thuộc.

Công thức tổng quát:

~~~text
Tổng chi phí kỳ =
  Compute
+ Storage
+ Network egress và phí xử lý mạng
+ Load balancer và địa chỉ IP
+ Backup và snapshot
+ Monitoring và log
+ License / support / dịch vụ phụ thuộc
~~~

Với compute theo giờ:

~~~text
Compute cost =
  Số instance
  x Số giờ chạy trong kỳ
  x Đơn giá mỗi instance-giờ
~~~

Với storage theo dung lượng:

~~~text
Storage cost =
  Dung lượng được tính phí (GB-tháng)
  x Đơn giá mỗi GB-tháng
~~~

Với network egress:

~~~text
Egress cost =
  Dung lượng outbound chịu phí (GB)
  x Đơn giá mỗi GB
~~~

Một số dịch vụ có phí theo request, IOPS, throughput được cấp, dung lượng log ingest, số lần truy vấn hoặc thời gian giữ dữ liệu. Cần dùng đơn vị tính đúng theo bảng giá của region và dịch vụ.

### 7.1. Ví dụ tính chi phí tháng

Giả sử một workload chạy liên tục trong tháng 730 giờ, gồm hai VM, mỗi VM có giá giả định 0,096 USD/giờ; mỗi VM dùng một volume 100 GB; egress ra Internet 200 GB; snapshot giữ 50 GB; log ingest 20 GB.

Để minh họa phép tính, giả sử các đơn giá sau. Đây là số giả định, không phải bảng giá cloud hiện hành:

| Thành phần | Khối lượng | Đơn giá giả định | Chi phí |
|---|---:|---:|---:|
| Compute | 2 x 730 instance-giờ | 0,096 USD/instance-giờ | 140,16 USD |
| Block storage | 2 x 100 GB-tháng | 0,08 USD/GB-tháng | 16,00 USD |
| Network egress | 200 GB | 0,09 USD/GB | 18,00 USD |
| Snapshot | 50 GB-tháng | 0,05 USD/GB-tháng | 2,50 USD |
| Log ingest | 20 GB | 0,50 USD/GB | 10,00 USD |
| **Tổng** | | | **186,66 USD/tháng** |

Phép tính compute: 2 x 730 x 0,096 = 140,16 USD. Các dòng còn lại được tính theo khối lượng nhân đơn giá. Tổng chưa bao gồm thuế, chiết khấu, NAT Gateway, load balancer, IP công khai, request API, license, phí hỗ trợ hoặc các dịch vụ chưa liệt kê. Hãy thay toàn bộ đơn giá giả định bằng giá trong region, mô hình mua và thời điểm triển khai thực tế.

### 7.2. So sánh phương án theo tổng chi phí

Giả sử phương án B dùng instance lớn hơn nhưng hoàn thành cùng khối lượng công việc trong thời gian ngắn hơn, hoặc cho phép giảm số bản sao. Không thể kết luận phương án nào rẻ hơn bằng đơn giá mỗi giờ; hãy tính chi phí toàn kỳ và chi phí trên mỗi giao dịch thành công.

~~~text
Cost per successful request =
  Tổng chi phí workload trong kỳ
  / Số request thành công trong kỳ

Cost per job =
  Tổng chi phí workload trong kỳ
  / Số job hoàn thành trong kỳ
~~~

Nếu cấu hình lớn làm thời gian xử lý giảm một nửa nhưng đơn giá compute tăng ít hơn gấp đôi, chi phí compute trên mỗi job có thể giảm. Tuy nhiên, phải cộng storage, network và các dịch vụ liên quan để so sánh đúng.

## 8. Công cụ ước tính và phân bổ chi phí

Các công cụ cloud giúp ước tính và kiểm tra chi phí theo dữ liệu sử dụng:

- **AWS Pricing Calculator:** lập ước tính trước triển khai theo loại instance, giờ chạy, volume, truyền dữ liệu và dịch vụ đi kèm.
- **AWS Cost Explorer:** xem xu hướng chi phí thực tế theo thời gian, service, region và tag.
- **AWS Cost and Usage Report:** phân tích chi tiết mức sử dụng và khoản phí ở cấp dòng dữ liệu.
- **AWS Compute Optimizer:** nhận khuyến nghị right-size cho một số tài nguyên được hỗ trợ dựa trên metric lịch sử và phạm vi quan sát.
- **Azure Pricing Calculator, Cost Management và Advisor:** ước tính, phân tích chi tiêu và nhận khuyến nghị cho tài nguyên Azure.
- **Google Cloud Pricing Calculator, Billing reports và Recommender:** ước tính, phân tích chi phí và xem khuyến nghị tối ưu.

Khuyến nghị tự động là đầu vào để điều tra, không phải lệnh thay đổi cấu hình. Kiểm tra cửa sổ quan sát, mức sử dụng đỉnh, lịch sử scale, SLO và các đợt tải theo mùa trước khi áp dụng.

Gắn tag hoặc label nhất quán như service, owner, environment, cost-center và workload. Nếu không phân bổ được chi phí cho chủ sở hữu, nhóm vận hành khó biết workload nào tạo ra mức tăng chi phí. Thiết lập budget và cảnh báo theo service/team để phát hiện sai lệch sớm.

## 9. Tối ưu chi phí sau khi right-size

Sau khi tìm được cấu hình phù hợp, xem xét thêm cách vận hành:

- **Tắt tài nguyên không dùng:** schedule môi trường dev/test, máy lab và batch không cần chạy ngoài cửa sổ đã định.
- **Dùng autoscaling:** scale theo metric phù hợp như request rate, queue depth hoặc CPU; đặt min/max và cooldown để tránh dao động.
- **Chọn mô hình mua:** On-Demand phù hợp tải khó dự báo; Savings Plans hoặc Reserved Instances có thể giảm chi phí cho mức sử dụng ổn định; Spot phù hợp batch có thể gián đoạn và có checkpoint.
- **Tối ưu storage:** xóa volume không gắn, snapshot hết hạn, log dư thừa; chọn loại volume và mức IOPS theo nhu cầu.
- **Giảm truyền dữ liệu:** đặt compute gần dependency, cache nội dung phù hợp, giảm payload và tránh truyền dữ liệu liên vùng không cần thiết.
- **Theo dõi chi phí nhàn rỗi:** instance chạy nhưng ít việc, volume lớn nhưng không sử dụng, NAT hoặc load balancer tồn tại cho workload đã dừng.
- **Giữ dự phòng hợp lý:** không cắt tài nguyên đến mức mất headroom cho tải đỉnh, failover hoặc rolling deployment.

Cam kết mua dài hạn chỉ nên áp dụng sau khi xác định baseline ổn định và mức sử dụng có thể dự đoán. Không mua cam kết chỉ vì một tháng có mức tiêu thụ cao bất thường. Spot có giá thấp hơn trong một số trường hợp nhưng có thể bị thu hồi; ứng dụng cần chịu được gián đoạn và lưu checkpoint ở nơi bền vững.

## 10. Quy trình thực hành và xác minh

Thực hiện trong môi trường lab hoặc staging có giới hạn chi phí:

1. Gắn tag cho tài nguyên và ghi lại cấu hình ban đầu.
2. Chạy workload đại diện, thu thập CPU, memory, disk, network, throughput, p95/p99 và error rate.
3. Xác định nút thắt dựa trên nhiều metric liên quan, không dựa vào một chỉ số đơn lẻ.
4. Thay đổi một nhóm cấu hình tại một thời điểm: CPU/instance family, memory, volume hoặc network.
5. Chạy lại cùng bộ dữ liệu, cùng mức tải và cùng thời lượng. Ghi lại kết quả sau điều chỉnh.
6. Tính chi phí compute, storage, network, backup, log và các dịch vụ phụ thuộc cho cùng một kỳ.
7. Tính cost per request/job và so sánh với SLO, throughput và error rate.
8. Kiểm tra khả năng scale, failover, khởi động lại và phục hồi trước khi áp dụng cho production.
9. Theo dõi chi phí thực tế sau thay đổi và rollback nếu hiệu năng hoặc độ tin cậy không đạt mục tiêu.

Bảng kết quả nên có tối thiểu:

| Cấu hình | vCPU/RAM | Disk | Throughput | p95 | Error rate | Chi phí kỳ | Chi phí/job |
|---|---|---|---:|---:|---:|---:|---:|
| Baseline | Ghi cấu hình gốc | Ghi loại/size | Đo | Đo | Đo | Tính | Tính |
| Candidate A | Ghi cấu hình thử 1 | Ghi loại/size | Đo | Đo | Đo | Tính | Tính |
| Candidate B | Ghi cấu hình thử 2 | Ghi loại/size | Đo | Đo | Đo | Tính | Tính |

Chỉ chấp nhận cấu hình mới khi hiệu năng đạt SLO, tỷ lệ lỗi không tăng ngoài ngưỡng, có đủ headroom cho tải đỉnh và chi phí được tính đầy đủ. Lưu lại metric, cấu hình, giả định giá và kết quả để lần đánh giá sau có thể tái lập.

## 11. Checklist right-sizing và chi phí

- [ ] Đã mô tả workload, mẫu tải, SLO và giờ cao điểm.
- [ ] Baseline có cấu hình phần cứng, phần mềm, dữ liệu và thời điểm đo.
- [ ] Đã thu thập CPU, memory, disk, network và metric ứng dụng.
- [ ] Đã kiểm tra bottleneck bằng nhiều metric liên quan.
- [ ] Đã benchmark nhiều cấu hình trong cùng điều kiện.
- [ ] Đã giữ headroom cho burst, failover và rolling deployment.
- [ ] Đã tính compute, storage, egress, NAT, load balancer, backup, log và license liên quan.
- [ ] Đã tính cost per request/job hoặc đơn vị nghiệp vụ phù hợp.
- [ ] Đã dùng giá đúng region, loại mua và thời điểm; giả định được ghi rõ.
- [ ] Tài nguyên có tag owner, service, environment và cost center.
- [ ] Budget, cảnh báo và quy trình xem xét chi phí định kỳ đã được thiết lập.
- [ ] Có kế hoạch rollback nếu cấu hình mới không đạt SLO.

## Kết luận

Đo hiệu năng giúp xác định workload thực sự cần CPU, bộ nhớ, lưu trữ và mạng ở mức nào. Right-sizing phải dựa trên tải đại diện, metric ở cả tầng hạ tầng lẫn ứng dụng, và được xác minh sau từng thay đổi. Mô hình chi phí cần tính đầy đủ tài nguyên trực tiếp và dịch vụ đi kèm, sau đó quy đổi thành chi phí trên mỗi request hoặc job thành công. Kết hợp benchmark lặp lại, phân bổ chi phí và giám sát liên tục giúp duy trì hiệu năng trong ngân sách.
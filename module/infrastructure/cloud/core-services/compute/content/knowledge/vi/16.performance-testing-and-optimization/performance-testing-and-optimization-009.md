# So sánh hiệu năng trên mỗi đơn vị chi phí giữa các cấu hình

Khi chọn cấu hình compute trên cloud, cấu hình có nhiều vCPU hoặc RAM nhất chưa chắc là lựa chọn kinh tế nhất. Một VM lớn có thể xử lý tải nhanh hơn nhưng chi phí mỗi giờ cao; một VM nhỏ có thể rẻ hơn nhưng cần nhiều instance, tạo thêm overhead mạng, load balancer và vận hành. So sánh đúng cần đo **khối lượng công việc hoàn thành với chi phí thực tế**, đồng thời giữ các yêu cầu về latency, lỗi và độ sẵn sàng.

Hiệu năng trên mỗi đơn vị chi phí (performance per cost) giúp trả lời câu hỏi: với cùng một ngân sách, cấu hình nào tạo ra nhiều kết quả hữu ích hơn; hoặc để hoàn thành cùng một khối lượng công việc ở chất lượng dịch vụ yêu cầu, cấu hình nào tốn ít chi phí hơn? Bài học này trình bày cách xác định workload, thiết kế benchmark công bằng, tính chi phí trên một đơn vị kết quả, đọc trade-off và lựa chọn cấu hình phù hợp.

## 1. Vì sao phải so sánh hiệu năng trên chi phí?

Một cấu hình compute có thể mạnh hơn về throughput nhưng kém hiệu quả về chi phí. Ngược lại, cấu hình rẻ hơn theo giờ có thể cần nhiều máy, tăng thời gian xử lý hoặc không đáp ứng latency khi tải cao.

Các câu hỏi cần trả lời:

- Cấu hình nào xử lý được nhiều request, job hoặc giao dịch thành công nhất trong cùng thời gian?
- Chi phí để xử lý một triệu request hoặc một job là bao nhiêu?
- Cấu hình nào đáp ứng SLO với mức headroom phù hợp?
- Tăng gấp đôi CPU hoặc RAM có làm throughput tăng tương ứng không?
- Nên dùng ít VM lớn hay nhiều VM nhỏ?
- Chi phí network, storage, license và vận hành có làm thay đổi kết quả không?
- Cấu hình nào duy trì hiệu quả khi tải biến động và autoscaling?

Mục tiêu không phải tối đa hóa một con số benchmark riêng lẻ. Cấu hình cần đáp ứng chất lượng dịch vụ, độ ổn định và khả năng vận hành với tổng chi phí hợp lý.

## 2. Xác định đơn vị công việc trước khi đo

Không thể so sánh hai cấu hình nếu chưa định nghĩa chính xác chúng đang hoàn thành cùng một công việc. Workload có thể là:

- Request HTTP/API: số request thành công mỗi giây.
- Giao dịch: số giao dịch nghiệp vụ hoàn tất mỗi phút.
- Batch job: số bản ghi hoặc file xử lý mỗi giờ.
- Database: truy vấn/transaction mỗi giây với cùng dữ liệu và mức consistency.
- Media processing: số phút video hoặc ảnh xử lý trong một giờ.
- Inference: số request hoặc token xử lý với cùng model và chất lượng đầu ra.
- Build/test: số pipeline hoặc test case hoàn tất trong một khoảng thời gian.

Đơn vị phải phản ánh kết quả hữu ích. Ví dụ, API trả HTTP 200 nhưng bỏ qua bước ghi dữ liệu không được tính là một request thành công nếu nghiệp vụ yêu cầu ghi bền vững. Với batch, job kết thúc nhưng thiếu bản ghi hoặc sai kết quả cũng không được tính vào throughput hữu ích.

### 2.1. Chuẩn hóa workload

Trước khi benchmark, ghi lại:

- Kích thước và phân bố dữ liệu đầu vào.
- Tỷ lệ đọc/ghi và độ phức tạp truy vấn.
- Số request đồng thời, tốc độ đến và burst pattern.
- Tỷ lệ cache hit/miss.
- Kích thước payload, response và file.
- Số lần gọi dependency cho mỗi tác vụ.
- Mức mã hóa, compression và consistency.
- Phiên bản ứng dụng, runtime, thư viện và cấu hình.
- Điều kiện dữ liệu nóng/lạnh và trạng thái cache.

Hai lần chạy chỉ so sánh được nếu workload tương đương. Thay đổi dataset, cache hoặc concurrency có thể làm kết quả khác đáng kể ngay cả khi cấu hình VM giữ nguyên.

## 3. Chọn chỉ số hiệu năng có ý nghĩa

Không có một metric duy nhất mô tả đầy đủ hiệu năng. Nên đo một nhóm chỉ số cùng nhau.

| Chỉ số | Ý nghĩa | Cách dùng |
|---|---|---|
| Throughput | Số đơn vị công việc hoàn thành trong một đơn vị thời gian | Request/s, transaction/s, job/hour |
| Successful throughput | Số đơn vị hoàn tất đúng và không lỗi | Dùng làm tử số khi tính hiệu quả chi phí |
| Latency p50 | Thời gian phản hồi ở phân vị 50 | Đại diện trải nghiệm điển hình |
| Latency p95/p99 | Thời gian phản hồi ở phân vị 95/99 | Thể hiện tail latency và trải nghiệm request chậm |
| Error rate | Tỷ lệ request/job lỗi hoặc bị từ chối | Xác định chất lượng và tính hợp lệ của benchmark |
| CPU utilization | Mức sử dụng CPU | Phát hiện CPU saturation hoặc cấu hình dư |
| Memory/working set | Bộ nhớ thực tế tiến trình sử dụng | Phát hiện thiếu RAM, paging và dư thừa |
| Network throughput/latency | Lưu lượng và thời gian truyền | Đánh giá giới hạn mạng và dependency |
| Storage IOPS/latency | Số thao tác I/O và độ trễ | Đánh giá disk/database bottleneck |
| Queue depth/wait time | Công việc chờ được xử lý | Phát hiện saturation và backpressure |

Throughput cao nhưng p99 vượt SLO hoặc error rate tăng không phải kết quả tốt. Hãy đặt điều kiện chất lượng trước khi so sánh hiệu quả chi phí.

### 3.1. SLO là điều kiện hợp lệ

Ví dụ một API có yêu cầu:

- p95 latency không quá 200 ms.
- p99 latency không quá 500 ms.
- Error rate dưới 0,1%.
- Không mất giao dịch đã xác nhận thành công.

Cấu hình chỉ được coi là ứng viên nếu đáp ứng các điều kiện này trong tải đại diện. Không nên chọn cấu hình có chi phí thấp nhất nếu nó vi phạm SLO.

## 4. Các chỉ số hiệu quả chi phí

Có hai cách nhìn bổ sung: hiệu năng tạo ra trên một đơn vị chi phí và chi phí cần thiết để tạo ra một đơn vị kết quả.

### 4.1. Throughput trên chi phí

Nếu chi phí tính theo giờ:

\[
\text{Throughput per cost} =
\frac{\text{Successful operations per second}}
{\text{Cost per hour}}
\]

Đơn vị có thể biểu diễn là request/second trên mỗi USD/hour. Giá trị càng cao càng tốt nếu workload, SLO và chất lượng kết quả giống nhau.

### 4.2. Chi phí trên một triệu tác vụ thành công

\[
\text{Cost per 1M operations} =
\frac{\text{Total cost during test}}
{\text{Successful operations during test}}
\times 1{,}000{,}000
\]

Chỉ tính các tác vụ hoàn tất đúng. Request lỗi, bị timeout hoặc bị loại do vi phạm dữ liệu không được đưa vào số lượng thành công.

### 4.3. Chi phí trên mỗi job

Với batch workload:

\[
\text{Cost per job} =
\frac{\text{Compute + storage + network + license cost}}
{\text{Number of completed valid jobs}}
\]

Nếu job có kích thước khác nhau, có thể chuẩn hóa theo bản ghi, GB hoặc đơn vị công việc đã định nghĩa thay vì so sánh số job đơn thuần.

### 4.4. Chi phí trên mỗi đơn vị công việc hữu ích

Một số workload cần định nghĩa metric riêng:

- USD trên một triệu transaction thành công.
- USD trên một GB dữ liệu đã xử lý.
- USD trên một giờ video đã chuyển mã đạt chất lượng.
- USD trên một triệu token inference với model và cấu hình chất lượng cố định.
- USD trên một bản build hoàn tất với cùng test suite.

Đơn vị càng gần giá trị nghiệp vụ thì quyết định cấu hình càng hữu ích.

## 5. Tính tổng chi phí đúng phạm vi

Giá VM theo giờ chỉ là một phần chi phí. Khi so sánh, cần xác định các thành phần thực sự thay đổi theo cấu hình và khối lượng công việc.

| Thành phần | Ví dụ chi phí | Vì sao cần tính |
|---|---|---|
| Compute | VM, container node, vCPU, RAM, GPU | Thành phần chính nhưng không phải duy nhất |
| Storage | Boot/data disk, IOPS/throughput provisioned, snapshot | Cấu hình nhanh hơn có thể cần disk đắt hơn |
| Network | Data egress, NAT, load balancer, inter-zone/inter-region traffic | Nhiều VM hoặc kiến trúc phân tán có thể tăng network cost |
| License | OS, database, commercial runtime, software per-core | VM nhiều core có thể tăng phí license |
| Observability | Log ingest, metrics, traces, retention | Tải cao và nhiều instance có thể tạo thêm telemetry |
| Backup | Snapshot, backup storage, replication | Cần thiết cho production và có thể khác giữa cấu hình |
| Support/operations | Dịch vụ quản lý hoặc effort vận hành có thể định lượng | Cấu hình phức tạp có thể làm tăng chi phí dài hạn |
| Idle capacity | Instance chờ, headroom, minimum replica | Phần tài nguyên không xử lý request vẫn có thể bị tính phí |

Tổng chi phí của benchmark nên dùng cùng một phạm vi cho mọi cấu hình. Nếu chỉ so giá VM, hãy ghi rõ đây là compute-only comparison. Nếu muốn chọn cấu hình production, hãy tính thêm storage, network, license và dịch vụ phụ trợ liên quan.

### 5.1. Dùng cùng cơ sở giá

Các mức giá cloud có thể khác nhau theo region, hệ điều hành, tenancy, billing option và thời điểm. Khi so sánh:

- Dùng cùng region và cùng currency.
- So on-demand với on-demand hoặc cùng loại commitment/discount.
- Tính giá thực trả nếu dùng Savings Plan, Reserved Instance hoặc committed use, đồng thời phân bổ chi phí cam kết hợp lý.
- Không so một cấu hình dùng Spot/Preemptible với cấu hình on-demand mà không tính rủi ro gián đoạn.
- Ghi rõ thời điểm lấy giá và các giả định.
- Phân bổ phí license và support theo đúng cách tính của nhà cung cấp.

Nếu benchmark chỉ chạy 20 phút, không nên lấy hóa đơn một tháng làm chi phí test mà không phân bổ nhất quán. Hãy dùng rate card hoặc billing export với cùng quy tắc phân bổ.

## 6. Thiết kế benchmark công bằng

Benchmark có thể sai lệch nếu môi trường chạy không tương đương hoặc thứ tự chạy làm ảnh hưởng cache, nhiệt độ CPU và trạng thái dependency.

Một quy trình cơ bản:

1. Xác định workload, đơn vị kết quả và SLO.
2. Chọn các cấu hình ứng viên với biến số cần so sánh.
3. Dùng cùng phiên bản ứng dụng, image, runtime và dữ liệu.
4. Đặt các dependency ở cùng điều kiện hoặc đo riêng chi phí của chúng.
5. Warm up ứng dụng và cache theo kịch bản đã định.
6. Chạy tải theo các mức concurrency hoặc arrival rate cố định.
7. Ghi throughput, latency phân vị, error rate và resource metrics.
8. Lặp lại nhiều lần, đổi thứ tự cấu hình nếu có thể.
9. Tính tổng chi phí trong cùng khoảng thời gian hoặc theo đơn vị công việc.
10. Loại các lần chạy có yếu tố nhiễu đã xác định và ghi rõ lý do.
11. Đối chiếu kết quả với SLO và chọn cấu hình có hiệu quả tốt nhất trong nhóm đạt chuẩn.

### 6.1. Warm-up và thời gian ổn định

Một số ứng dụng cần warm-up để JIT compiler, cache, connection pool và runtime đạt trạng thái ổn định. Nếu đo ngay sau khi process vừa khởi động, kết quả có thể phản ánh startup overhead thay vì hiệu năng ổn định.

Tuy nhiên, startup time cũng quan trọng với workload scale-to-zero hoặc autoscaling nhanh. Nên tách hai bài đo:

- **Steady-state benchmark:** đo sau khi ứng dụng đã warm-up.
- **Cold-start benchmark:** đo từ lúc khởi tạo tới khi sẵn sàng phục vụ.

Không dùng kết quả warm-up để đại diện cold start hoặc ngược lại.

### 6.2. Repeated runs và biến động

Chạy mỗi cấu hình nhiều lần và báo cáo median, phân vị hoặc khoảng biến động. Nếu kết quả chênh lệch lớn giữa các lần chạy, hãy tìm nguyên nhân như noisy neighbor, cache state, autoscaling, throttling hoặc dependency variability.

Không nên chọn cấu hình chỉ vì một lần chạy có throughput cao nhất. Cần xem tính lặp lại và độ ổn định.

## 7. Chọn kiểu tải phù hợp với workload

Có nhiều kiểu benchmark, mỗi kiểu trả lời một câu hỏi khác nhau.

| Kiểu thử nghiệm | Cách tạo tải | Mục tiêu |
|---|---|---|
| Constant concurrency | Giữ số client đồng thời cố định | So sánh năng lực ở cùng mức concurrency |
| Constant arrival rate | Giữ tốc độ request đến cố định | So latency và error rate dưới cùng demand |
| Ramp test | Tăng tải từng bước | Tìm điểm saturation |
| Spike test | Tăng tải đột ngột | Đo phản ứng với burst |
| Soak test | Giữ tải lâu | Phát hiện memory leak, degradation và chi phí dài hạn |
| Batch benchmark | Chạy cùng dataset/job | So thời gian hoàn thành và chi phí mỗi job |
| Cold-start test | Tạo instance mới rồi gửi request | Đo startup/readiness latency |

Constant concurrency và constant arrival rate không tương đương. Khi server chậm, số client đồng thời cố định có thể làm tốc độ request đến giảm theo thời gian. Với API có demand cố định, constant arrival rate thường giúp so sánh latency và error rate rõ hơn.

## 8. Các yếu tố cấu hình compute ảnh hưởng tới hiệu quả chi phí

### 8.1. CPU và kiến trúc processor

Các yếu tố cần xem:

- Số vCPU và hiệu năng mỗi core.
- Thế hệ CPU, xung nhịp và instruction set.
- Kiến trúc x86-64 hoặc Arm.
- Hiệu năng single-thread và multi-thread.
- CPU credit hoặc giới hạn burst với loại instance burstable.
- CPU throttling, steal time và noisy neighbor.
- Giới hạn license theo core/socket.

Workload nhiều tác vụ tuần tự có thể hưởng lợi từ CPU có hiệu năng đơn luồng cao. Workload song song tốt có thể tận dụng nhiều core hơn. Một cấu hình có nhiều vCPU nhưng hiệu năng mỗi core thấp hoặc bị throttling không nhất thiết nhanh hơn.

Khi so x86 với Arm, phải xác minh binary, runtime, native library và image tương thích. Nếu cần build lại hoặc tối ưu mã, tính cả effort chuyển đổi và kiểm thử.

### 8.2. Bộ nhớ

RAM ảnh hưởng tới working set, cache, garbage collection và khả năng tránh paging. Thiếu RAM có thể làm latency tăng mạnh hoặc gây OOM; quá nhiều RAM làm chi phí tăng mà throughput không cải thiện.

Đo:

- Resident set/working set của ứng dụng.
- Heap và non-heap nếu dùng JVM.
- Page fault, swap và memory pressure.
- Cache hit rate.
- OOM event và memory limit của container.
- Bộ nhớ dành cho OS, agent và sidecar.

Đừng chỉ nhìn RAM của VM. Container có thể bị giới hạn bởi cgroup thấp hơn RAM vật lý. Workload cần được đo trong đúng giới hạn runtime production.

### 8.3. Storage

Storage có thể trở thành bottleneck ngay cả khi CPU còn dư. Đo IOPS, throughput, latency p95/p99, queue depth và tỷ lệ cache hit. Cần dùng cùng loại disk, filesystem, mount option và dữ liệu khi so CPU configurations; nếu đổi disk cùng lúc, không thể biết cải thiện đến từ đâu.

Với database, benchmark phải phản ánh write durability, replication và consistency. Tắt fsync hoặc giảm durability để tăng điểm benchmark sẽ làm kết quả không đại diện cấu hình production.

### 8.4. Network

Đo throughput, packet rate, latency, retransmission và số connection. Một số loại VM có network bandwidth khác nhau hoặc phụ thuộc kích thước instance. Workload gọi nhiều dependency có thể bị giới hạn bởi network trước khi CPU đạt mức cao.

Nếu các VM ở khác zone hoặc region, tính cả chi phí truyền dữ liệu và latency. Không so một benchmark chạy cùng host với benchmark qua network nhiều hop mà không ghi rõ topology.

### 8.5. GPU và accelerator

Với workload ML, inference hoặc media, so sánh cần bao gồm loại accelerator, memory, precision, batch size, model version và thời gian khởi tạo. GPU đắt hơn có thể giảm cost per inference nếu throughput tăng đủ lớn; nhưng utilization thấp, memory không phù hợp hoặc batch quá nhỏ có thể làm chi phí mỗi request tăng.

Không chỉ so số phép tính lý thuyết. Hãy đo kết quả với model, độ chính xác, latency và chất lượng đầu ra tương đương.

## 9. Ít VM lớn hay nhiều VM nhỏ?

Hai chiến lược có trade-off khác nhau.

| Tiêu chí | Ít VM lớn | Nhiều VM nhỏ |
|---|---|---|
| Throughput | Có thể tận dụng CPU/RAM lớn, ít network hop nội bộ | Có thể mở rộng ngang tốt nếu ứng dụng stateless |
| Chi phí cố định | Ít instance overhead | Có thêm chi phí theo từng instance |
| Fault domain | Một VM lỗi có thể mất phần capacity lớn | Lỗi một VM thường ảnh hưởng phần nhỏ hơn |
| Autoscaling | Scale theo bước lớn, có thể dư capacity | Scale mịn hơn, nhưng cần nhiều lần khởi tạo |
| Network | Ít giao tiếp giữa instance hơn trong một số kiến trúc | Có thể tăng east-west traffic và load balancing |
| License | Có thể license theo core tập trung | Có thể tăng phí theo instance hoặc core tùy sản phẩm |
| Vận hành | Ít node hơn nhưng mỗi node quan trọng hơn | Nhiều node hơn, cần automation và observability tốt |

Không có lựa chọn chung cho mọi workload. Ứng dụng stateless, scale ngang tốt có thể đạt hiệu quả với nhiều VM nhỏ. Database hoặc workload cần bộ nhớ lớn có thể phù hợp với VM lớn hơn. Cần benchmark cả phương án scale-up và scale-out.

## 10. Autoscaling và chi phí khi tải biến động

Benchmark một instance ở steady state chưa phản ánh chi phí của hệ thống autoscaling. Với tải thay đổi, cần tính:

- Số instance trung bình và cực đại.
- Thời gian scale-out và thời gian warm-up.
- Thời gian scale-in và lượng capacity idle.
- Minimum replica để bảo đảm availability.
- Request/job bị chờ trong lúc scale.
- Chi phí load balancer, NAT, storage và telemetry theo số instance.
- Chi phí của capacity dự phòng trong nhiều zone.

Một cấu hình có throughput/giá tốt ở một VM có thể không tốt khi autoscaling do startup lâu hoặc hiệu năng không tuyến tính. Ngược lại, instance nhỏ có thể scale nhanh và tiết kiệm ở tải thấp nhưng cần nhiều node khi tải cao.

Hãy chạy benchmark theo chu kỳ tải đại diện: giờ thấp điểm, giờ cao điểm, burst và thời gian phục hồi sau burst. Tính chi phí trên tổng số tác vụ thành công trong toàn chu kỳ.

### 10.1. Capacity headroom

Không nên vận hành liên tục ở 100% utilization chỉ để giảm chi phí. Cần headroom cho burst, node failure, rolling update và biến động dependency. Headroom làm tăng chi phí danh nghĩa nhưng có thể giảm lỗi và duy trì SLO.

Hãy tính chi phí theo capacity thực sự cần có để đáp ứng SLO, bao gồm replica dự phòng và giới hạn failure domain.

## 11. Ví dụ tính cost per million requests

Giả sử benchmark cùng một API với cùng dữ liệu và cùng SLO:

- p95 latency phải dưới 200 ms.
- Error rate dưới 0,1%.
- Đếm request thành công, không tính request lỗi.
- Giá compute được phân bổ theo USD/giờ.

Kết quả minh họa:

| Cấu hình | Chi phí/giờ | Throughput thành công | p95 | Error rate |
|---|---:|---:|---:|---:|
| A: 8 vCPU, 32 GB RAM | $0,40 | 1.200 request/s | 180 ms | 0,03% |
| B: 16 vCPU, 64 GB RAM | $0,72 | 1.900 request/s | 190 ms | 0,04% |
| C: 4 vCPU, 16 GB RAM | $0,20 | 500 request/s | 260 ms | 0,02% |

Cấu hình C có error rate thấp nhưng không đạt p95 dưới 200 ms, nên không đủ điều kiện để chọn nếu SLO này bắt buộc.

Chi phí trên một triệu request thành công:

\[
\text{Cost per 1M} =
\frac{\text{USD/hour}}
{\text{successful requests/second} \times 3600}
\times 1{,}000{,}000
\]

Cấu hình A:

\[
\frac{0.40}{1200 \times 3600} \times 1{,}000{,}000
\approx \$0.0926
\]

Cấu hình B:

\[
\frac{0.72}{1900 \times 3600} \times 1{,}000{,}000
\approx \$0.1053
\]

Trong ví dụ này, A có chi phí trên một triệu request thấp hơn B, còn B có throughput tuyệt đối cao hơn. Nếu nhu cầu peak vượt 1.200 request/s trên mỗi instance hoặc cần headroom lớn hơn, B có thể là lựa chọn phù hợp. Kết luận phụ thuộc tải thực tế và số instance cần triển khai.

Các số liệu trên chỉ minh họa phương pháp tính, không phải giá hoặc benchmark của một nhà cung cấp cụ thể. Khi đưa vào production, cần cộng các chi phí phụ trợ và kiểm tra SLO ở nhiều mức tải.

## 12. So sánh cấu hình theo nhiều mức tải

Một cấu hình có thể hiệu quả ở tải thấp nhưng kém khi tải tăng. Nên tạo bảng kết quả ở nhiều mức demand.

Ví dụ bảng báo cáo:

| Demand | Config A throughput | Config A p95 | Config B throughput | Config B p95 | Chi phí/1M thành công |
|---|---:|---:|---:|---:|---:|
| 300 req/s | ... | ... | ... | ... | ... |
| 600 req/s | ... | ... | ... | ... | ... |
| 900 req/s | ... | ... | ... | ... | ... |
| 1.200 req/s | ... | ... | ... | ... | ... |
| 1.500 req/s | ... | ... | ... | ... | ... |

Từ kết quả có thể xác định:

- Điểm bắt đầu latency tăng nhanh.
- Mức tải làm error rate vượt ngưỡng.
- Cấu hình nào có vùng vận hành hiệu quả rộng hơn.
- Cấu hình nào cần scale-out sớm hơn.
- Chi phí trên mỗi tác vụ thay đổi thế nào khi utilization tăng.

Không nên chỉ lấy peak throughput làm kết quả cuối. Điểm vận hành tốt thường nằm dưới vùng saturation để còn headroom cho burst và sự cố.

## 13. Tính hiệu quả khi so sánh VM với container hoặc serverless

Đơn vị tính chi phí có thể khác giữa các mô hình compute:

- VM thường tính theo thời gian instance chạy, cộng storage/network và dịch vụ phụ trợ.
- Container có thể tính theo node VM hoặc theo vCPU/RAM được cấp cho task/pod, tùy nền tảng.
- Serverless có thể tính theo số request, thời gian thực thi, memory allocation, CPU hoặc tài nguyên phụ trợ.

Để so sánh, hãy dùng cùng một đơn vị kết quả nghiệp vụ, ví dụ USD trên một triệu request thành công. Tính đủ chi phí hạ tầng dùng chung như load balancer, NAT, logging, registry, database và minimum capacity.

Cũng cần tính các khác biệt vận hành:

- Cold start và thời gian scale.
- Giới hạn thời gian chạy hoặc kích thước payload.
- Concurrency và quota.
- Khả năng giữ connection hoặc local state.
- Chi phí khi workload nhàn rỗi.
- Chi phí observability và network.

Không nên so trực tiếp giá vCPU/giờ của VM với giá mỗi lần gọi serverless mà không quy đổi về cùng workload và cùng SLO.

## 14. Hiệu quả chi phí và mô hình giá cloud

Các tùy chọn thanh toán có thể thay đổi kết quả:

- **On-demand/pay-as-you-go:** linh hoạt, phù hợp benchmark ban đầu và tải không chắc chắn.
- **Reserved/committed use:** giảm giá khi cam kết thời hạn hoặc mức chi tiêu, nhưng có rủi ro capacity không sử dụng hết.
- **Savings Plan hoặc discount theo usage:** có thể giảm chi phí nếu workload ổn định và phù hợp điều kiện.
- **Spot/preemptible:** chi phí thấp hơn nhưng có thể bị thu hồi; cần workload chịu gián đoạn, checkpoint và retry.
- **Dedicated host/instance:** phù hợp yêu cầu isolation hoặc license đặc thù, nhưng có thể làm chi phí tăng.

Khi so sánh, nên báo cáo ít nhất hai góc nhìn:

1. Hiệu quả kỹ thuật trên giá on-demand để so cấu hình compute tương đối độc lập với hợp đồng.
2. Chi phí thực trả theo billing model mà tổ chức dự định sử dụng.

Với Spot/preemptible, thêm xác suất interruption, thời gian khôi phục và công việc phải chạy lại vào cost per successful job. Một job rẻ nhưng thường xuyên bị ngắt có thể tốn tổng chi phí cao hơn.

## 15. Các nguồn sai lệch thường gặp trong benchmark

**So sánh workload khác nhau.** Dataset, request mix hoặc cache state không giống nhau làm kết quả mất ý nghĩa. Hãy cố định input và mô tả rõ workload.

**Chỉ đo thời gian ngắn.** Benchmark ngắn có thể không phát hiện memory leak, throttling, thermal behavior hoặc chi phí autoscaling. Bổ sung soak test khi workload chạy dài.

**Bỏ qua tail latency.** Average latency tốt có thể che giấu p99 rất cao. Luôn đo phân vị và error rate.

**Không warm-up hoặc warm-up không đồng nhất.** JIT, cache và connection pool làm lệch kết quả. Định nghĩa riêng cold-start và steady-state test.

**Không tính dependency.** VM nhanh hơn nhưng gọi database chậm hoặc network đắt hơn có thể không giảm chi phí toàn hệ thống. Đo end-to-end và ghi chi phí liên quan.

**So giá khác billing model.** On-demand, committed use và Spot có điều kiện khác nhau. Chuẩn hóa giả định giá và ghi thời điểm.

**Không đo CPU throttling/credit.** Instance burstable có thể nhanh trong giai đoạn đầu rồi giảm hiệu năng. Soak test và theo dõi credit/throttling.

**Chạy benchmark đồng thời trên cùng host hoặc dependency.** Nhiễu làm kết quả không ổn định. Cô lập test hoặc ghi nhận ảnh hưởng.

**Tối ưu benchmark nhưng làm giảm chất lượng.** Bỏ validation, giảm durability hoặc hạ chất lượng model làm throughput tăng giả tạo. Giữ nguyên điều kiện correctness và SLO.

## 16. Quy trình ra quyết định chọn cấu hình

Có thể dùng quy trình sau:

1. **Định nghĩa workload:** đơn vị công việc, dataset, arrival pattern và dependency.
2. **Đặt SLO:** latency p95/p99, error rate, availability và correctness.
3. **Chọn ứng viên:** loại instance, CPU architecture, RAM, disk và network.
4. **Chuẩn hóa môi trường:** image, runtime, region, phiên bản, cấu hình và dữ liệu.
5. **Chạy benchmark:** warm-up, ramp, steady-state, spike và soak nếu cần.
6. **Thu thập metrics:** throughput thành công, latency, errors, CPU, memory, I/O, network và pool.
7. **Tính tổng chi phí:** compute, storage, network, license, backup, logging và idle capacity.
8. **Tính cost per unit:** cost per million requests, cost per job hoặc đơn vị nghiệp vụ.
9. **Loại ứng viên không đạt SLO:** không chọn cấu hình chỉ vì giá rẻ.
10. **Kiểm tra headroom và failure scenario:** node failure, rolling update và burst.
11. **Xác nhận bằng pilot production:** theo dõi trong tải thực tế trước khi áp dụng rộng.
12. **Định kỳ benchmark lại:** khi ứng dụng, runtime, dữ liệu, giá hoặc thế hệ instance thay đổi.

### 16.1. Ma trận quyết định

| Tiêu chí | Trọng số tham khảo | Câu hỏi |
|---|---:|---|
| SLO và correctness | Điều kiện bắt buộc | Có đáp ứng latency, error rate và tính đúng đắn không? |
| Cost per unit | Cao | Chi phí trên một request/job thành công là bao nhiêu? |
| Capacity/headroom | Cao | Có chịu được burst và mất một node không? |
| Tail latency | Cao | p95/p99 có ổn định không? |
| Khả năng scale | Trung bình/cao | Scale-out/in có nhanh và dự đoán được không? |
| Vận hành | Trung bình | Có dễ triển khai, giám sát và khắc phục không? |
| Portability/compatibility | Theo workload | Runtime, native dependency và license có tương thích không? |

Trọng số cần điều chỉnh theo mục tiêu dịch vụ. Với API giao dịch, latency và correctness có thể quan trọng hơn chi phí compute nhỏ nhất. Với batch có thể chạy lại, cost per job và thời gian hoàn thành có thể là tiêu chí chính.

## 17. Checklist benchmark hiệu năng trên chi phí

- [ ] Đã xác định đơn vị công việc hữu ích và điều kiện tính thành công.
- [ ] Workload, dataset, request mix và concurrency được chuẩn hóa.
- [ ] SLO về p95/p99, error rate và correctness được xác định trước.
- [ ] Cấu hình ứng viên được ghi rõ CPU, RAM, storage, network và kiến trúc.
- [ ] Cùng image, runtime, phiên bản ứng dụng và dependency được sử dụng.
- [ ] Đã tách cold-start test khỏi steady-state benchmark.
- [ ] Có warm-up, repeated runs và thời gian đo đủ dài.
- [ ] Đã đo throughput thành công, latency phân vị và error rate.
- [ ] Đã thu thập CPU, memory, I/O, network, pool và queue metrics.
- [ ] Đã kiểm tra throttling, burst credit và noisy neighbor.
- [ ] Giá được so trên cùng region, currency và billing model.
- [ ] Tổng chi phí bao gồm compute, storage, network, license và dịch vụ liên quan.
- [ ] Đã tính cost per request/job hoặc đơn vị nghiệp vụ.
- [ ] Cấu hình vi phạm SLO đã bị loại khỏi danh sách ứng viên.
- [ ] Đã kiểm tra autoscaling, headroom và failure scenario.
- [ ] Đã thử nghiệm pilot với tải thực tế trước khi chuẩn hóa cấu hình.
- [ ] Đã ghi giả định, thời điểm giá, kết quả và quyết định để benchmark lại sau này.

## 18. Kết luận

So sánh hiệu năng trên mỗi đơn vị chi phí cần đo cùng một workload, đếm kết quả thành công và đặt SLO làm điều kiện lựa chọn. Throughput, latency phân vị, error rate và tài nguyên phải được xem cùng nhau; chi phí cần bao gồm compute, storage, network, license, observability, backup và capacity nhàn rỗi trong cùng phạm vi so sánh.

Benchmark công bằng cần kiểm soát dữ liệu, runtime, warm-up, concurrency, dependency và billing model. Sau đó, tính cost per million operations hoặc cost per job, đánh giá headroom và thử nghiệm với tải biến động. Cấu hình tốt là cấu hình đáp ứng yêu cầu dịch vụ ổn định với chi phí trên mỗi kết quả hữu ích hợp lý, chứ không đơn thuần là VM có giá theo giờ thấp nhất hoặc điểm throughput cao nhất.

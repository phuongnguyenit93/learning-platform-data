# Đo thông lượng tối đa trong phạm vi mục tiêu độ trễ và tỷ lệ lỗi

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Định nghĩa năng lực phục vụ bằng thông lượng hoàn tất trong khi vẫn đáp ứng giới hạn độ trễ và tỷ lệ lỗi.
- Phân biệt offered load, throughput hoàn tất, goodput và giới hạn tải bền vững.
- Thiết kế workload đọc/ghi đại diện, chọn mô hình phát tải và tăng tải có kiểm soát.
- Đọc latency theo p50, p95, p99, error rate, queue và các dấu hiệu bão hòa.
- Xác định điểm gãy (saturation knee) nơi tăng tải không còn làm tăng goodput mà làm độ trễ hoặc lỗi tăng mạnh.
- Kết hợp metric ứng dụng, connection pool, execution plan và tài nguyên database để tìm giới hạn.
- Lập báo cáo capacity có điều kiện, phạm vi, độ tin cậy và khuyến nghị vận hành.

## 1. Thông lượng tối đa phải gắn với mục tiêu chất lượng

Một hệ thống có thể xử lý rất nhiều request mỗi giây nếu chấp nhận để request chờ lâu hoặc trả lỗi. Con số đó không mô tả năng lực phục vụ mà người dùng thực sự nhận được. Khi đo capacity, cần xác định mức thông lượng cao nhất mà hệ thống vẫn đáp ứng đồng thời các mục tiêu về độ trễ và tỷ lệ lỗi.

Trong module DATABASE_PERFORMANCE, việc đo này phải phản ánh đường đi thực tế từ ứng dụng đến cơ sở dữ liệu: connection pool, SQL, execution plan, transaction, log flush, I/O, lock contention và network. Một database có thể đạt throughput cao trong bài test INSERT đơn giản nhưng không đạt cùng mức với workload thật có JOIN, UPDATE, index maintenance và transaction nhiều bước.

Ta định nghĩa **throughput tối đa trong phạm vi mục tiêu** là mức tải cao nhất mà hệ thống duy trì được trong một khoảng đo đủ dài, với goodput đạt yêu cầu, latency nằm trong ngưỡng và tỷ lệ lỗi không vượt giới hạn đã đặt.

Đây là một điểm vận hành có điều kiện, không phải con số tối đa tuyệt đối của phần cứng. Kết quả luôn gắn với workload, dữ liệu, cấu hình, concurrency, thời lượng và SLO được sử dụng.

## 2. Phân biệt offered load, throughput và goodput

Ba khái niệm cần được tách riêng:

- **Offered load:** tốc độ client hoặc load generator gửi yêu cầu đến hệ thống, thường đo bằng request/s hoặc transaction/s.
- **Completed throughput:** tốc độ yêu cầu hoàn tất, kể cả thành công và thất bại nếu bộ đo tính mọi kết quả đã kết thúc.
- **Goodput:** tốc độ giao dịch nghiệp vụ hoàn tất thành công và hợp lệ theo định nghĩa của bài test.

Ví dụ, load generator gửi 2.000 giao dịch mỗi giây. Hệ thống hoàn tất 1.700 giao dịch, trong đó 1.600 thành công và 100 thất bại. Khi đó offered load là 2.000/s, completed throughput là 1.700/s và goodput là 1.600/s.

Không được báo cáo 2.000 transaction/s là năng lực database nếu 300 yêu cầu còn nằm trong hàng đợi hoặc đã timeout. Cũng không được tính một câu SQL thành công là giao dịch nghiệp vụ thành công nếu transaction cuối cùng rollback hoặc dữ liệu không đạt điều kiện kiểm tra.

### Định nghĩa đơn vị công việc

Trước khi đo, xác định một đơn vị throughput là gì:

- HTTP request, nếu đang đo toàn bộ API.
- Logical transaction, nếu một nghiệp vụ gồm nhiều câu SQL.
- Database transaction đã commit.
- Một statement hoặc một batch, nếu mục tiêu là đo riêng database engine.
- Rows/s hoặc bytes/s, nếu đo nạp dữ liệu hoặc xử lý theo lô.

Không trộn các đơn vị. Một logical transaction có thể chạy 5 statement; so sánh transaction/s với statement/s sẽ tạo kết luận sai.

## 3. Xác định SLO trước khi chạy benchmark

SLO (Service Level Objective) là mục tiêu định lượng về chất lượng dịch vụ trong một cửa sổ đo. Với bài đo capacity, thường cần tối thiểu:

- Goodput tối thiểu cần đạt.
- Ngưỡng latency p95 và p99.
- Tỷ lệ lỗi tối đa.
- Thời gian duy trì tải ở mức mục tiêu.
- Các điều kiện tài nguyên và tính đúng dữ liệu.

Ví dụ minh họa:

| Chỉ tiêu | Mục tiêu thử nghiệm |
| --- | ---: |
| Goodput | Ít nhất 1.500 giao dịch thành công/s |
| p95 end-to-end latency | Không quá 150 ms |
| p99 end-to-end latency | Không quá 300 ms |
| System error rate | Không quá 0,5% |
| Thời gian duy trì | 15 phút liên tục sau warm-up |
| Data correctness | Không mất, nhân đôi hoặc sai kết quả nghiệp vụ |

Đây chỉ là bộ ngưỡng mẫu. Ngưỡng thực tế phải xuất phát từ yêu cầu sản phẩm, hợp đồng dịch vụ và hành vi người dùng. Không chọn ngưỡng sau khi xem kết quả chỉ để làm benchmark có vẻ đạt.

### Phân loại lỗi đúng cách

Không phải mọi kết quả không thành công đều là lỗi hạ tầng. Ví dụ, giao dịch rút tiền bị từ chối vì số dư không đủ có thể là kết quả nghiệp vụ hợp lệ. Ngược lại, connection timeout, deadlock vượt retry budget, database unavailable hoặc lỗi serialization không được xử lý là lỗi hệ thống theo định nghĩa phù hợp.

Hãy định nghĩa rõ:

- Business rejection: nghiệp vụ từ chối hợp lệ, được tính riêng.
- Validation error: dữ liệu đầu vào không hợp lệ, thường loại khỏi capacity của database nếu không đến database.
- Transient database error: deadlock, serialization failure hoặc lỗi tạm thời khác.
- Timeout: request vượt deadline hoặc client ngừng chờ.
- Infrastructure error: connection failure, network reset, storage hoặc node failure.
- Unknown/incorrect result: response không đúng hoặc dữ liệu sai; cần coi là lỗi nghiêm trọng.

Error rate phải có mẫu số rõ ràng. Có thể tính system errors chia cho số request đã được phát hoặc số request đã kết thúc; hãy ghi công thức và không đổi cách tính giữa các lần so sánh.

## 4. Đo latency theo phân vị

Average latency có thể che khuất tail latency. Một hệ thống có phần lớn request nhanh nhưng một nhóm nhỏ chờ nhiều giây vẫn có thể làm người dùng gặp lỗi timeout.

Các phân vị thường dùng:

- **p50:** trung vị, mô tả request điển hình.
- **p90:** 90% request hoàn tất trong thời gian này hoặc thấp hơn.
- **p95:** hữu ích để đánh giá phần lớn request nhưng vẫn thấy đuôi chậm.
- **p99:** nhạy với tail latency và queueing.
- **p99.9:** hữu ích với hệ thống có lượng request rất lớn và yêu cầu chặt.

Đo latency end-to-end từ lúc phát request đến khi nhận kết quả cuối. Với database, có thể đo thêm các stage như acquire connection, execute, fetch, commit và mapping, nhưng không dùng một stage thay cho latency mà người dùng trải nghiệm.

### Vì sao p99 tăng trước khi throughput giảm?

Khi CPU, I/O hoặc connection pool tiến gần giới hạn, hàng đợi bắt đầu tích tụ. Request mới vẫn được nhận, nhưng phải chờ lâu hơn. Trong giai đoạn này, throughput hoàn tất có thể chưa giảm rõ rệt trong khi p95/p99 đã tăng nhanh.

Đó là lý do không nên tìm capacity chỉ bằng cách tăng tải đến khi throughput dừng tăng. Mục tiêu là tìm mức cao nhất trước khi latency hoặc error rate vi phạm SLO.

### Tổng hợp histogram đúng cách

Nếu có nhiều instance load generator hoặc nhiều ứng dụng, không lấy trung bình các p99 riêng lẻ để tạo p99 toàn hệ thống. Hãy hợp nhất histogram/bucket hoặc dùng hệ thống metrics hỗ trợ tính quantile từ dữ liệu tổng hợp phù hợp.

Phân vị cũng cần đủ mẫu. Với rất ít request, p99 không ổn định và có thể chỉ phản ánh một vài mẫu. Ghi số lượng request trong mỗi cửa sổ cùng phân vị để đánh giá độ tin cậy.

## 5. Throughput tối đa trong phạm vi SLO

Giả sử benchmark chạy nhiều mức offered load. Với mỗi mức, thu thập goodput, p95, p99 và error rate trong một cửa sổ ổn định.

| Offered load | Goodput | p95 | p99 | Error rate | Đạt SLO? |
| ---: | ---: | ---: | ---: | ---: | --- |
| 800/s | 798/s | 45 ms | 80 ms | 0,05% | Có |
| 1.000/s | 997/s | 55 ms | 105 ms | 0,08% | Có |
| 1.200/s | 1.195/s | 72 ms | 145 ms | 0,10% | Có |
| 1.400/s | 1.390/s | 115 ms | 260 ms | 0,20% | Có |
| 1.500/s | 1.470/s | 170 ms | 390 ms | 0,80% | Không |
| 1.700/s | 1.510/s | 310 ms | 900 ms | 3,20% | Không |

Giả sử SLO đặt p95 không quá 150 ms, p99 không quá 300 ms và error rate không quá 0,5%. Mức 1.400 offered request/s là mức cao nhất trong bảng vẫn đạt tất cả ngưỡng. Goodput tương ứng khoảng 1.390/s.

Không lấy 1.510/s ở mức tải cuối làm capacity vì latency và error rate đã vi phạm. Cũng không khẳng định 1.400/s là giới hạn vật lý; đó là mức cao nhất đã được chứng minh đạt SLO trong các điểm thử nghiệm hiện có.

### Capacity và headroom

Production thường không nên vận hành liên tục sát capacity đã đo. Cần headroom cho burst, thay đổi query mix, backup, failover, node degradation và tăng trưởng dữ liệu.

Nếu capacity đã xác nhận là 1.400 good transaction/s và chính sách vận hành chỉ cho phép sử dụng 70% mức đó, mức planning ban đầu là khoảng 980/s. Tỷ lệ headroom phải dựa trên độ biến động tải và khả năng phục hồi, không phải một hằng số chung.

## 6. Xác định saturation knee

Saturation knee là vùng mà khi tăng offered load, goodput tăng rất ít hoặc không tăng nữa, trong khi latency, queue hoặc error rate tăng mạnh.

```text
Goodput
   ^                         ________
   |                     ___/
   |                 ___/
   |             ___/
   |         ___/
   |     ___/
   |____/________________________________> Offered load
        vùng tăng tốt       saturation knee

Latency / Error
   ^                              /
   |                           __/
   |                       ___/
   |                  ____/
   |____________ ____/__________________> Offered load
```

Đồ thị chỉ mang tính minh họa. Điểm gãy không nhất thiết sắc nét; có thể là một dải tải mà hiệu quả tăng thêm giảm dần và tail latency bắt đầu xấu đi.

Ở vùng dưới knee, tăng tải thường làm goodput tăng gần tương ứng. Sau knee, request bắt đầu xếp hàng, thời gian chờ tăng, retry nhiều hơn và hệ thống có thể rơi vào vòng khuếch đại tải.

Không cần đẩy hệ thống đến crash để xác định knee. Dừng tăng tải khi SLO bị vi phạm ổn định hoặc xuất hiện dấu hiệu nguy hiểm như OOM, log gần đầy, replication lag không hồi phục hay storage queue tăng liên tục.

## 7. Chọn mô hình phát tải

Load model quyết định cách request được phát và ảnh hưởng đến kết quả đo.

### Closed-loop load

Trong closed-loop, mỗi virtual user gửi request tiếp theo sau khi request trước hoàn tất, có thể kèm thời gian think time.

Ưu điểm:

- Dễ mô phỏng số lượng người dùng đồng thời.
- Phản ánh một số ứng dụng mà người dùng chờ kết quả trước khi thao tác tiếp.
- Dễ kiểm soát concurrency.

Giới hạn:

- Khi hệ thống chậm, tốc độ phát tải tự giảm.
- Offered load không còn độc lập với latency.
- Có thể che khuất điểm hệ thống không đáp ứng được một arrival rate cố định.

### Open-loop load

Trong open-loop, generator phát request theo arrival rate mục tiêu độc lập với thời gian phản hồi của request trước.

Ưu điểm:

- Đo được hệ thống có đáp ứng một tốc độ đến cố định hay không.
- Phát hiện queue buildup và latency tăng khi server không theo kịp.
- Phù hợp với workload có arrival rate từ bên ngoài.

Giới hạn:

- Cần kiểm soát queue ở load generator.
- Nếu generator không đủ năng lực, offered load thực tế thấp hơn mục tiêu.
- Khi server chậm, request chờ có thể tăng rất lớn; cần deadline và chính sách bỏ tải.

### Chọn mô hình theo mục tiêu

Đo capacity của API theo lượng người dùng đồng thời có thể cần closed-loop. Đo khả năng tiếp nhận một arrival rate cố định thường cần open-loop. Có thể chạy cả hai để hiểu hai góc nhìn, nhưng phải báo cáo rõ mô hình.

## 8. Tránh coordinated omission

Coordinated omission xảy ra khi load generator chỉ ghi latency cho request mà nó đã gửi, nhưng ngừng hoặc giảm gửi trong lúc server chậm. Khoảng thời gian đáng lẽ có request đến nhưng không được phát ra không được tính vào latency, làm kết quả trông tốt hơn thực tế.

Ví dụ, hệ thống bị pause 2 giây. Một generator closed-loop chỉ có 10 virtual users; trong lúc chờ, nó không phát thêm request. Histogram có thể không phản ánh các request đáng lẽ đến trong 2 giây đó.

Để hạn chế:

- Dùng arrival-rate/open-loop model khi cần đo theo tốc độ đến cố định.
- Chọn load generator có cách ghi nhận latency phù hợp và hỗ trợ correction nếu có.
- Ghi offered rate, dropped/queued requests và completed rate.
- Đặt giới hạn queue và deadline, không âm thầm loại bỏ request.
- Đối chiếu thời gian gửi dự kiến với thời gian gửi thực tế.

Không bật correction một cách mù quáng. Cần hiểu công cụ đang tính latency như thế nào và tránh đếm hai lần phần thời gian đã được ghi nhận.

## 9. Xây dựng workload đại diện cho database

Benchmark chỉ có giá trị nếu workload gần với hệ thống cần dự báo. Một workload chỉ đọc primary key không đại diện cho ứng dụng có nhiều JOIN, sort, update và commit.

Thu thập hoặc mô hình hóa:

- Tỷ lệ SELECT, INSERT, UPDATE, DELETE và UPSERT.
- Query fingerprint phổ biến và tỷ trọng của từng nhóm.
- Kích thước hàng, số index, foreign key, trigger và constraint.
- Phân bố tham số: key nóng, key hiếm, tenant lớn và dữ liệu lệch.
- Số hàng trả về, số hàng examined và kích thước payload.
- Transaction gồm bao nhiêu statement và commit frequency.
- Tỷ lệ cache hit/miss và dữ liệu nóng/lạnh.
- Mức concurrency, connection pool và think time.
- Các tác vụ nền như vacuum, purge, checkpoint, backup và replication.

### Transaction mix

Ví dụ workload thương mại điện tử:

| Nhóm nghiệp vụ | Tỷ trọng mẫu | Đặc điểm |
| --- | ---: | --- |
| Đọc chi tiết sản phẩm | 35% | SELECT theo khóa, một số JOIN |
| Tìm kiếm danh sách | 25% | Filter, sort, pagination |
| Đọc đơn hàng | 15% | JOIN customer/order/items |
| Cập nhật giỏ hàng | 10% | UPDATE/UPSERT, transaction ngắn |
| Tạo đơn và trừ tồn kho | 10% | Nhiều statement, khóa và commit |
| Ghi sự kiện/audit | 5% | INSERT và log generation |

Tỷ trọng chỉ minh họa. Workload thực cần dựa trên telemetry đã loại bỏ dữ liệu nhạy cảm và được tổng hợp theo query fingerprint.

### Giữ đúng semantics nghiệp vụ

Không đơn giản hóa transaction đến mức bỏ qua ràng buộc hoặc commit nếu production cần chúng. Ví dụ tạo đơn phải kiểm tra tồn kho, ghi đơn, ghi chi tiết và cập nhật tồn kho trong cùng transaction hoặc theo workflow được thiết kế.

Nếu benchmark chỉ INSERT vào một bảng không index trong auto-commit tắt, nó không thể dự báo capacity của nghiệp vụ tạo đơn có nhiều index và transaction commit.

## 10. Dữ liệu thử nghiệm và trạng thái cache

Quy mô và phân bố dữ liệu ảnh hưởng execution plan, index size, cache residency và I/O.

Benchmark cần xác định rõ:

- Dataset nhỏ hơn RAM hay lớn hơn RAM?
- Bảng và index đã đạt kích thước production dự kiến chưa?
- Key được truy cập đều hay có skew?
- Dữ liệu đã warm cache hay bắt đầu từ trạng thái lạnh?
- Có cập nhật/xóa đủ để tạo vacuum/purge workload không?
- Statistics có được cập nhật như production không?

### Cold cache và warm cache

Warm cache phù hợp với workload thường xuyên truy cập tập dữ liệu nóng. Cold cache có thể phù hợp với batch hoặc truy vấn lịch sử ít dùng. Cần đo riêng nếu cả hai đều quan trọng.

Không giả định restart database là cách duy nhất để tạo cold cache; thao tác đó có thể gây tác động ngoài ý muốn và không tái tạo chính xác trạng thái production. Dùng môi trường thử nghiệm, dữ liệu và quy trình có kiểm soát.

### Dataset phải đủ lớn

Nếu index vừa RAM trong benchmark nhưng lớn hơn nhiều so với buffer pool production, kết quả đọc có thể lạc quan. Nếu chỉ có một vài khóa nóng, lock contention và cache locality cũng không phản ánh workload thật.

## 11. Tăng tải theo bậc và giữ cửa sổ ổn định

Một quy trình cơ bản:

1. **Baseline:** chạy mức tải thấp để xác nhận correctness và overhead đo.
2. **Warm-up:** cho JVM, pool, database cache và plan cache đạt trạng thái cần khảo sát.
3. **Ramp-up:** tăng offered load hoặc concurrency theo bậc nhỏ.
4. **Stabilization:** chờ hàng đợi và metric ổn định sau mỗi lần tăng.
5. **Measurement:** giữ mức tải đủ lâu để thu được số mẫu và metric đại diện.
6. **Ramp-down:** giảm tải có kiểm soát và quan sát backlog được xử lý.
7. **Validation:** kiểm tra dữ liệu, lỗi, rollback, replication và tài nguyên sau test.

Không dùng một khoảng warm-up cố định cho mọi hệ thống. Hãy xác nhận trạng thái bằng metric: cache, throughput, latency và queue đã ổn định tương đối.

### Thời lượng cửa sổ đo

Một cửa sổ vài giây thường không đủ cho workload có checkpoint, GC, autoscaling, storage burst credits hoặc background maintenance. Chọn thời lượng dựa trên:

- Số lượng mẫu cần để phân vị ổn định.
- Chu kỳ checkpoint, log flush và tác vụ nền.
- Thời gian cache/storage đạt steady state.
- Chu kỳ traffic và batch trong môi trường thực.
- Thời gian cần phát hiện lỗi tích lũy hoặc memory leak.

Với mỗi mức tải, lưu kết quả theo các cửa sổ thời gian nhỏ để phát hiện throughput giảm dần hoặc p99 tăng theo thời gian. Không chỉ lưu một average cuối bài.

## 12. Concurrency và định luật Little

Concurrency là số công việc đang được xử lý hoặc đang chờ trong hệ thống. Tăng concurrency có thể tận dụng CPU/I/O tốt hơn cho đến khi tài nguyên bão hòa; sau đó nó chủ yếu làm hàng đợi và thời gian chờ tăng.

Định luật Little:

[ L = lambda 	imes W ]

Trong đó:

- (L): số request trung bình đang ở trong hệ thống.
- (lambda): throughput hoàn tất trung bình (request/s).
- (W): thời gian trung bình trong hệ thống (giây).

Ví dụ, nếu hệ thống hoàn tất 1.000 transaction/s và thời gian trung bình trong hệ thống là 0,05 giây, số transaction trung bình đang được xử lý hoặc chờ là khoảng 50.

Little's Law mô tả quan hệ trung bình trong điều kiện ổn định; không thay thế đo latency phân vị hoặc phân tích hàng đợi. Khi hệ thống không ổn định và queue tăng liên tục, giả định steady state không còn phù hợp.

### Chọn concurrency

Thử nhiều mức concurrency để xác định:

- Throughput tăng đến mức nào?
- p95/p99 bắt đầu tăng ở đâu?
- Connection pool có pending request không?
- CPU, I/O hoặc lock đạt giới hạn nào?
- Tăng concurrency có làm goodput tăng hay chỉ tăng request đang chờ?

Không lấy số connection tối đa làm concurrency mục tiêu. Connection đang idle, query đang chạy và transaction đang giữ lock là các trạng thái khác nhau.

## 13. Đo ở cả load generator, ứng dụng và database

Load generator có thể là nút thắt. Nếu generator hết CPU, network hoặc socket, offered load sẽ không đạt mức yêu cầu và benchmark có thể đánh giá thấp capacity server.

### Load generator

Thu thập:

- Offered rate và actual dispatch rate.
- Số request đang queued, dropped hoặc chưa được phát.
- CPU, memory, network và file descriptor.
- Số worker/virtual user và event loop saturation.
- Clock synchronization và thời gian đo.

### Ứng dụng

Thu thập:

- Request throughput, goodput, p50/p95/p99 và error rate.
- Connection acquisition, active/idle/pending pool.
- Execute, fetch, commit và transaction duration.
- JVM CPU, heap, allocation, GC pause và thread pool queue.
- Retry count, timeout và số query trên mỗi request.

### Database

Thu thập:

- CPU, memory, I/O, storage latency và queue.
- Active sessions, connections, locks, deadlocks và wait events.
- Query fingerprint, execution time, rows examined/returned.
- Logical/physical reads, buffer hit và temp spill.
- WAL/redo/log generation, flush latency và checkpoint.
- Replication lag, background maintenance và transaction age.

Đặt timestamp và cửa sổ tổng hợp tương thích để liên hệ sự kiện giữa các lớp. Nếu p99 tăng lúc pool pending tăng nhưng database CPU còn thấp, nguyên nhân có thể ở pool sizing hoặc transaction giữ connection quá lâu. Nếu log flush latency tăng cùng commit p99, cần điều tra đường ghi log.

## 14. Quan sát execution plan trong bài capacity

Capacity test không chỉ đo tổng query time. Cần biết query mix có đang dùng access path dự kiến không.

Kiểm tra:

- Estimated rows so với actual rows.
- Scan/seek và số hàng được đọc trước khi lọc.
- Join order và join algorithm.
- Sort/hash memory, spill và temp I/O.
- Logical reads, physical reads và buffer activity.
- Index usage và chi phí cập nhật index.
- Plan regression giữa các lần chạy hoặc sau statistics update.

Ví dụ PostgreSQL:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, total_amount
FROM orders
WHERE tenant_id = 42
  AND created_at >= TIMESTAMPTZ '2026-01-01 00:00:00+00'
ORDER BY created_at DESC
LIMIT 50;
```

`EXPLAIN ANALYZE` thực thi câu lệnh; dùng cẩn thận với statement có tác dụng ghi và trong môi trường phù hợp. Với PostgreSQL, `pg_stat_statements` giúp tổng hợp query fingerprint; `pg_stat_activity`, `pg_locks` và wait events hỗ trợ xem trạng thái đồng thời.

Với MySQL, dùng Performance Schema statement digest, `EXPLAIN ANALYZE` khi phiên bản hỗ trợ và InnoDB status để xem query, lock, buffer pool và redo. Với SQL Server, dùng Query Store, actual execution plan, `SET STATISTICS IO, TIME ON` và wait statistics.

Plan trong benchmark phải tương ứng với tham số và trạng thái thống kê đại diện. Một query chạy nhanh ở một giá trị tham số không bảo đảm mọi phân bố tham số đều có cùng plan.

## 15. Phân loại bottleneck theo dấu hiệu

| Dấu hiệu | Khả năng cần kiểm tra | Metric xác nhận |
| --- | --- | --- |
| CPU gần bão hòa, throughput chững | CPU-bound query, expression, join, parallelism | CPU time, run queue, top query fingerprints |
| CPU thấp nhưng latency tăng | I/O wait, lock wait, network hoặc pool wait | wait events, storage latency, lock wait, pool pending |
| Logical reads tăng mạnh | Scan rộng, index kém phù hợp, cardinality sai | execution plan, rows examined, buffer reads |
| Commit p99 tăng | Log flush, storage hoặc replication acknowledgement | WAL/redo flush latency, log I/O, replica lag |
| Deadlock/retry tăng | Thứ tự khóa, transaction dài, hotspot | deadlock graph, lock waits, retry count |
| Temp spill tăng | Memory grant/work_mem thiếu hoặc sort/hash lớn | spill metrics, temp bytes, memory pressure |
| Pool pending tăng | Pool nhỏ, connection leak hoặc database quá tải | active/idle/pending, usage duration, DB sessions |
| Throughput giảm theo thời gian | Cache exhaustion, checkpoint, storage burst hết, backlog | time-series I/O, checkpoint, dirty pages, queue |
| Một shard/node nóng | Skew hoặc hot key | per-node CPU, I/O, requests, data size |

Không suy ra nguyên nhân từ một metric. Ví dụ CPU thấp có thể do tất cả worker đang chờ lock; storage utilization thấp không loại trừ latency cao ở một volume hoặc giới hạn IOPS.

## 16. Connection pool và giới hạn đồng thời

Pool quá nhỏ có thể làm request xếp hàng trước database. Pool quá lớn có thể gửi nhiều session đến database hơn khả năng xử lý, làm CPU scheduling, memory, lock và I/O contention tăng.

Khi benchmark, ghi:

- Maximum pool size và số instance ứng dụng.
- Active, idle, pending connection.
- Acquisition latency và timeout.
- Connection usage duration.
- Tổng session ở database.
- Số transaction đồng thời và thời gian giữ transaction.

Tính tổng connection có thể mở từ mọi ứng dụng, worker, scheduler, admin và service tích hợp. Không chỉ nhìn pool của một instance.

Benchmark có thể thử nhiều pool size, nhưng thay đổi từng yếu tố và giữ cùng offered load. Nếu tăng pool làm goodput không tăng nhưng p99 và DB CPU tăng, đó là dấu hiệu đã vượt concurrency hữu ích.

## 17. Retry và error amplification

Retry giúp một số lỗi tạm thời như deadlock hoặc serialization failure có thể được phục hồi. Tuy nhiên, khi tải cao, retry làm tăng số thao tác thực tế gửi đến database.

Ví dụ 1.000 request/s, mỗi request trung bình thử 1,2 lần, có thể tạo khoảng 1.200 lần thực thi transaction/s. Nếu benchmark chỉ tính request gốc, tải database bị đánh giá thấp.

Thu thập:

- Request gốc và số attempt.
- Retry theo từng loại lỗi.
- Số transaction commit thành công.
- Transaction rollback và lỗi cuối cùng.
- Tổng thời gian bao gồm backoff.
- Idempotency và duplicate side effect.

Không tắt retry để làm đẹp số liệu nếu production có retry. Ngược lại, không để retry vô hạn. Benchmark cần dùng chính sách retry có giới hạn, backoff, jitter và idempotency giống cấu hình dự kiến.

## 18. Capacity test, stress test và soak test

Ba kiểu thử nghiệm có mục đích khác nhau:

| Loại test | Mục tiêu | Cách chạy |
| --- | --- | --- |
| Capacity/load test | Xác định mức tải đáp ứng SLO | Tăng tải theo bậc và đo goodput/latency/error |
| Stress test | Hiểu hành vi khi vượt capacity | Tăng tải vượt ngưỡng có kiểm soát, quan sát degrade và recovery |
| Soak/endurance test | Phát hiện vấn đề tích lũy theo thời gian | Giữ tải đại diện trong thời gian dài, theo dõi memory, log, queue và bloat |

Capacity test không cần làm hệ thống sập. Stress test phải có ngưỡng dừng và môi trường phù hợp. Soak test giúp phát hiện connection leak, memory leak, transaction dài, log growth và backlog nền mà test ngắn không thấy.

## 19. Kiểm soát biến số để kết quả có thể lặp lại

Khi so sánh hai cấu hình, giữ ổn định:

- Phiên bản database, driver, JVM và ứng dụng.
- Schema, index, constraints và dữ liệu.
- Query mix, tham số và phân bố khóa.
- Isolation level, durability và replication mode.
- CPU/RAM quota, storage tier, IOPS và network.
- Load model, concurrency, ramp-up và cửa sổ đo.
- Cache state, statistics và background jobs.

Chỉ thay một nhóm yếu tố chính mỗi lần nếu muốn xác định nguyên nhân. Nếu đồng thời tăng CPU, memory, pool, index và thay query mix, không thể biết thay đổi nào tạo ra kết quả.

Chạy lặp lại đủ số lần để đánh giá độ biến thiên. Nếu kết quả chênh lệch lớn, điều tra tác vụ nền, cache, noisy neighbor, thermal throttling, GC hoặc storage burst trước khi công bố một con số capacity.

## 20. Quy trình đo throughput tối đa trong SLO

1. **Chốt SLO.** Định nghĩa goodput, p95/p99, error rate, thời lượng và correctness.
2. **Chọn đơn vị công việc.** Xác định request, logical transaction hay committed database transaction.
3. **Mô hình hóa workload.** Dùng query mix, transaction, dữ liệu và phân bố tham số đại diện.
4. **Chọn load model.** Dùng open-loop hoặc closed-loop theo câu hỏi cần trả lời; ghi rõ cách đo offered load.
5. **Kiểm tra generator.** Bảo đảm client không phải bottleneck và không bỏ request âm thầm.
6. **Chạy baseline và warm-up.** Xác nhận tính đúng, plan và trạng thái cache.
7. **Tăng tải theo bậc.** Mỗi bậc có stabilization và measurement window đủ dài.
8. **Thu thập metric đồng bộ.** Goodput, latency histogram, errors, pool, query plan, DB waits, CPU, memory, I/O và replication.
9. **Xác định knee và mức đạt SLO.** Chọn mức cao nhất đã được chứng minh đạt tất cả ngưỡng trong cửa sổ ổn định.
10. **Lặp lại và kiểm tra biến động.** Chạy lại với cùng điều kiện, xác nhận không phải kết quả ngẫu nhiên.
11. **Thử fail/recovery khi cần.** Đo hành vi khi shard chậm, replica lag, node restart hoặc storage degrade trong môi trường kiểm thử.
12. **Đặt headroom.** Chuyển capacity đo được thành giới hạn vận hành an toàn.
13. **Lưu báo cáo.** Ghi cấu hình, workload, thời lượng, kết quả, giới hạn và điều kiện áp dụng.

## 21. Ví dụ lập kế hoạch ramp-up

Giả sử mục tiêu đo API ghi đơn hàng có SLO p95 ≤ 200 ms, p99 ≤ 400 ms và system error rate ≤ 0,3%. Một lịch thử nghiệm có thể là:

| Giai đoạn | Offered load | Thời lượng đo sau ổn định |
| --- | ---: | ---: |
| Baseline | 200/s | 5 phút |
| Step 1 | 400/s | 5 phút |
| Step 2 | 600/s | 5 phút |
| Step 3 | 800/s | 10 phút |
| Step 4 | 1.000/s | 10 phút |
| Step 5 | 1.200/s | 10 phút |
| Step 6 | 1.400/s | 10 phút |

Đây chỉ là ví dụ. Nếu p99 vượt ngưỡng ở 1.200/s trong nhiều cửa sổ liên tiếp, không cần tiếp tục lên 1.400/s chỉ để hoàn thành bảng. Có thể giữ tải thấp hơn để điều tra hoặc chuyển sang stress test riêng với ngưỡng dừng an toàn.

Ở mỗi bước, kiểm tra actual dispatch rate có đạt offered rate không. Nếu generator chỉ phát được 900/s khi mục tiêu là 1.000/s, không thể kết luận database đã xử lý 1.000/s.

## 22. Ví dụ báo cáo capacity

Một báo cáo có thể ghi:

| Trường | Giá trị mẫu |
| --- | --- |
| Workload | 60% read, 25% search, 15% write transaction |
| Dataset | 80 triệu hàng, index và phân bố key gần production |
| Load model | Open-loop, arrival rate tăng theo bậc |
| Durability | Commit durable, replication theo cấu hình thử nghiệm |
| SLO | p95 ≤ 150 ms, p99 ≤ 300 ms, error ≤ 0,5% |
| Mức cao nhất đạt SLO | 1.400 offered transaction/s |
| Goodput tại mức đó | 1.390 successful transaction/s |
| p95/p99 | 115 ms / 260 ms |
| Error rate | 0,20% |
| Saturation signal | Log I/O latency và connection queue bắt đầu tăng ở bước kế tiếp |
| Headroom vận hành | 70% capacity đã đo, cần xác nhận bằng traffic profile |

Con số này chỉ áp dụng cho workload, cấu hình và môi trường đã ghi. Nếu thay dataset, index, replication, storage tier hoặc query mix, cần đo lại.

## 23. Điều kiện dừng và an toàn khi thử nghiệm

Trước khi chạy, xác định điều kiện dừng:

- p95/p99 vượt ngưỡng trong số cửa sổ liên tiếp đã quy định.
- Error rate hoặc timeout vượt giới hạn.
- Database connection pool hoặc session đạt mức nguy hiểm.
- Storage latency, IOPS queue hoặc log capacity vượt ngưỡng.
- Replication lag tăng không hồi phục.
- OOM, restart, deadlock storm hoặc dữ liệu sai.
- Load generator hoặc môi trường thử nghiệm mất khả năng kiểm soát.

Không chạy capacity/stress test trên production nếu chưa có kế hoạch, cửa sổ, giới hạn tải và cơ chế dừng được phê duyệt. Dùng dữ liệu đã ẩn danh hoặc dữ liệu tổng hợp, không để benchmark tạo side effect nghiệp vụ thật như gửi thanh toán hoặc email.

## 24. Những sai lầm thường gặp

- **Báo cáo offered load như throughput.** Request được gửi không đồng nghĩa đã hoàn tất thành công.
- **Tìm throughput cực đại mà bỏ qua latency.** Người dùng có thể nhận response quá chậm dù goodput cao.
- **Chỉ dùng average latency.** Tail latency p95/p99 có thể vi phạm SLO trước khi average thay đổi.
- **Không định nghĩa error rate.** Business rejection và system failure bị trộn lẫn.
- **Dùng closed-loop cho arrival-rate capacity mà không nhận ra load tự giảm.** Có thể che coordinated omission.
- **Load generator không đủ mạnh.** Offered rate thực thấp hơn mục tiêu nhưng báo cáo vẫn dùng mục tiêu cấu hình.
- **Workload quá đơn giản.** Một SELECT point lookup không đại diện cho transaction mix thực tế.
- **Dataset quá nhỏ.** Cache và index residency làm kết quả lạc quan.
- **Chỉ đo trong vài giây.** Không thấy checkpoint, cache exhaustion, GC hoặc backlog tích lũy.
- **Tăng concurrency vô hạn.** Queue và retry tăng nhưng goodput không cải thiện.
- **Gộp p99 của các instance bằng trung bình.** Phân vị tổng hợp bị sai.
- **Không đo query plan và wait events.** Không xác định được nguyên nhân saturation.
- **Không tính retry.** Một request có thể tạo nhiều transaction attempt.
- **Công bố capacity không kèm điều kiện.** Kết quả mất ý nghĩa khi workload hoặc cấu hình thay đổi.

## 25. Danh sách kiểm tra trước khi công bố throughput

- [ ] Đơn vị throughput và định nghĩa goodput đã rõ.
- [ ] SLO latency p95/p99 và error rate được chốt trước khi thử.
- [ ] Business rejection được tách khỏi system error.
- [ ] Workload, query mix và transaction semantics đại diện.
- [ ] Dataset, index, statistics và cache state được ghi nhận.
- [ ] Load model open-loop/closed-loop được lựa chọn có chủ đích.
- [ ] Offered rate, actual dispatch, completed throughput và dropped request được ghi riêng.
- [ ] Đã kiểm tra coordinated omission và năng lực load generator.
- [ ] Đã chạy warm-up, ramp-up và cửa sổ đo đủ dài.
- [ ] Latency histogram được tổng hợp đúng trên mọi instance.
- [ ] Có metric pool, application, database, storage và replication.
- [ ] Execution plan và wait events được kiểm tra ở mức tải cao.
- [ ] Retry, timeout, rollback và correctness được tính vào kết quả.
- [ ] Có saturation knee, stop condition và headroom.
- [ ] Đã chạy lặp lại và lưu cấu hình để tái hiện.
- [ ] Báo cáo ghi rõ phạm vi và giới hạn áp dụng của capacity.

## Kết luận

Thông lượng tối đa có ý nghĩa vận hành là goodput cao nhất vẫn đáp ứng mục tiêu độ trễ, tỷ lệ lỗi và tính đúng dữ liệu trong một cửa sổ tải ổn định. Hãy phân biệt offered load với transaction hoàn tất, đo p95/p99 thay vì chỉ average, chọn open-loop hoặc closed-loop đúng câu hỏi và tránh coordinated omission. Workload, dataset, query plan, concurrency, connection pool, durability và replication phải gần với môi trường cần dự báo. Tăng tải theo bậc, quan sát saturation knee bằng goodput, latency, errors và queue, rồi xác nhận nguyên nhân qua metric ứng dụng và database. Capacity đã đo cần đi kèm headroom, cấu hình và điều kiện áp dụng; không dùng một con số benchmark tách rời SLO để cam kết năng lực hệ thống.

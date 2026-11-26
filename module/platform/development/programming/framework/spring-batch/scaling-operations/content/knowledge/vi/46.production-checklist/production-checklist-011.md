# Checklist production: Đã xác nhận SLA và throughput

Trong vận hành **SPRING_BATCH_SCALING_OPERATIONS**, tăng số thread, chạy nhiều step song song, partitioning hoặc mở rộng worker sang nhiều máy chỉ có giá trị khi **job hoàn thành đúng cam kết về thời gian và chất lượng dữ liệu**. Một lần chạy thử với throughput cao chưa đủ để kết luận hệ thống sẵn sàng production: phải chứng minh job có thể đáp ứng khối lượng thật, lúc tải đỉnh, khi các dịch vụ khác cùng dùng tài nguyên, và sau những sự cố có khả năng xảy ra.

Bài học thuộc chương **Checklist production**, tập trung vào hạng mục **“Đã xác nhận SLA và throughput”**. Kết quả mong đợi là một bộ tiêu chí **Go/No-Go có số liệu, ngưỡng, người xác nhận và bằng chứng lưu lại**. Nội dung áp dụng cho Spring Batch xử lý dữ liệu lớn qua **multi-threaded step, parallel steps, local/remote partitioning và remote chunking**, đồng thời xem xét thread safety, restart, retry và năng lực của database, broker, API và hạ tầng thực tế.

> **Định nghĩa hoàn thành:** SLA và throughput chỉ được coi là đã xác nhận khi có mục tiêu định lượng, cách đo thống nhất, thử nghiệm đại diện production và bằng chứng rằng **dữ liệu đầu ra đúng**. `BatchStatus.COMPLETED` và số worker đang chạy không tự chứng minh hai điều đó.

## 1. Phân biệt SLA, SLO, SLI và throughput

Bốn khái niệm dễ bị trộn lẫn:

| Khái niệm | Ý nghĩa | Ví dụ đối với batch |
| --- | --- | --- |
| **SLA** (Service Level Agreement) | Cam kết dịch vụ giữa các bên, có quy định phạm vi và hậu quả nếu không đạt | “Dữ liệu đối soát ngày D có sẵn trước 06:00 theo lịch nghiệp vụ” |
| **SLO** (Service Level Objective) | Mục tiêu nội bộ dùng để vận hành dịch vụ | “Ít nhất 99,5% số ngày trong kỳ đo hoàn tất trước 05:45, giữ 15 phút dự phòng” |
| **SLI** (Service Level Indicator) | Chỉ số đo việc đạt mục tiêu | Tỷ lệ ngày job hoàn thành và dữ liệu đầu ra đạt đối soát trước hạn |
| **Throughput** | Khối lượng công việc hữu ích xử lý trên đơn vị thời gian | 4.000 bản ghi hợp lệ được ghi thành công/giây trong cửa sổ đo |

Nếu một công ty không có SLA pháp lý/chính thức, vẫn cần xác lập **mục tiêu thời hạn và chất lượng** do chủ sở hữu nghiệp vụ chấp thuận; tránh gọi mọi chỉ số hiệu năng là SLA.

Các trường hợp cần phân biệt:

- **Đạt throughput tức thời nhưng trượt SLA:** job xử lý nhanh lúc đầu, sau đó kẹt một partition lớn, chờ API hoặc mất thời gian đối soát.
- **Job `COMPLETED` nhưng trượt SLA:** kết thúc sau thời điểm nghiệp vụ cần dữ liệu.
- **Đạt SLA thời gian nhưng dữ liệu sai:** ghi thiếu, trùng hoặc bỏ qua record ngoài chính sách; không được đánh dấu đạt.
- **Throughput cao nhờ retry/đọc lại:** số lần attempt lớn không có nghĩa số record hữu ích hoàn thành cao.

Vì vậy, định nghĩa một lần chạy “đạt” phải gắn **deadline, tính đúng đắn, độ sẵn sàng của output và giới hạn ảnh hưởng tới các hệ thống phụ thuộc**.

## 2. Chốt phạm vi SLA trước khi đo

Một hợp đồng đo lường cho batch tối thiểu cần:

| Trường | Câu hỏi cần giải đáp | Ví dụ minh họa |
| --- | --- | --- |
| Đối tượng | Job/pipeline nào, tenant nào, phân đoạn dữ liệu nào? | `dailyPaymentReconciliation` cho toàn bộ giao dịch D-1 |
| Mốc bắt đầu | Tính từ lúc schedule kích hoạt, dữ liệu nguồn đến đủ, hay lúc `JobExecution` bắt đầu? | 00:30 sau khi upstream phát tín hiệu dữ liệu sẵn sàng |
| Mốc hoàn thành | Khi Spring Batch báo `COMPLETED` hay khi output đã publish và đối soát? | 04:30, tất cả partition hoàn tất và file/report khả dụng |
| Time zone & lịch | Ngày nghiệp vụ, ngày nghỉ, lịch mùa vụ, timezone? | `Asia/Ho_Chi_Minh`, mỗi ngày theo lịch nghiệp vụ |
| Khối lượng phạm vi | Khối lượng kỳ vọng, cực đại, tỷ lệ record lỗi? | Bình thường 18 triệu, ngày đỉnh 26 triệu bản ghi |
| Đúng dữ liệu | Điều kiện kiểm tra số lượng/tổng tiền/unique key/skip? | Sai lệch tổng tiền = 0; không tạo giao dịch trùng |
| Tỷ lệ đạt | Bao nhiêu kỳ chạy cần đúng hạn? Cách xử lý maintenance? | 99,5% số kỳ hợp lệ trong tháng |
| Sự cố cho phép | Có được retry, restart, chờ downstream bao lâu? | Một lần worker crash vẫn phải hoàn thành trong cửa sổ |
| Phạm vi chia sẻ | Có được gây giảm hiệu năng API online/DB dùng chung? | API vẫn giữ SLO latency đã thống nhất |
| Chủ sở hữu | Ai xác nhận nghiệp vụ, kỹ thuật và vận hành? | Product owner + DBA + batch/on-call lead |

Chọn **mốc đo bên ngoài** khi SLA yêu cầu dữ liệu sẵn sàng cho bên tiêu thụ. Nếu chỉ đo `END_TIME - START_TIME` của Spring Batch mà bỏ thời gian chờ lịch, lấy dữ liệu nguồn, đẩy file và đối soát, phép đo có thể bỏ sót thời gian thực tế làm trượt deadline.

Nên lưu cả hai khoảng thời gian:

1. **Execution duration:** từ `JobExecution.START_TIME` tới `END_TIME`, phục vụ phân tích hiệu năng Batch.
2. **End-to-end latency:** từ thời điểm cam kết nhận đầu vào đến khi dữ liệu đúng và khả dụng ở đích, phục vụ tính SLA.

Với pipeline nhiều job, SLA tính trên đường găng (critical path) của toàn pipeline. Tổng duration của từng step không nhất thiết bằng duration của job khi các step chạy song song.

## 3. Xác định throughput nào được phép dùng để nghiệm thu

Một batch pipeline có nhiều bộ đếm khác nhau; phải đặt tên và quy tắc rõ ràng:

| Chỉ số | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| **Input read throughput** | Số item được reader đọc/giây | Chưa nói được có ghi thành công hay không |
| **Process throughput** | Số item đi qua processor/giây | Có thể bao gồm item bị filter hoặc xử lý lại |
| **Successful output throughput** | Số record nghiệp vụ hợp lệ đã được ghi bền vững/giây | Nên dùng để chứng minh năng lực hoàn thành công việc |
| **Commit rate** | Số chunk transaction commit/giây | Kích thước chunk khác nhau nên không thay cho records/s |
| **Attempt throughput** | Số lần xử lý/giây kể cả retry | Chỉ số tải và overhead, không dùng thay output hữu ích |
| **Queue consumption rate** | Số message/giây được consumer lấy hoặc ack | Có thể khác số record thành công; cần đối chiếu redelivery |
| **Validated throughput** | Số đơn vị nghiệp vụ *đúng, duy nhất và đã đối soát*/giây | Chỉ số phù hợp nhất nếu SLA gắn với chất lượng dữ liệu |

Công thức chung cho cửa sổ đo `[t_1,t_2]`:

\[
R_{\mathrm{effective}} =
\frac{N_{\mathrm{accepted,unique}}(t_2) -
      N_{\mathrm{accepted,unique}}(t_1)}
     {t_2 - t_1}
\]

Trong đó `N_accepted,unique` là số bản ghi đầu ra thành công, **không đếm lại** record đã retry/redeliver. Nếu một input sinh nhiều output, phải định nghĩa “đơn vị công việc” hợp lý (giao dịch, đơn hàng, file, byte…) và quy tắc ánh xạ đầu vào–đầu ra, không lấy `WRITE_COUNT` đơn giản làm số input đã hoàn tất.

**Lưu ý về Spring Batch:** `READ_COUNT`, `WRITE_COUNT`, `COMMIT_COUNT`, `ROLLBACK_COUNT` và skip counts là metadata hữu ích để quan sát. Ngữ nghĩa các bộ đếm phụ thuộc vòng đời step/chunk và cách item được filter/skip; riêng các bộ đếm này **không phải bằng chứng độc lập của exactly-once hoặc dữ liệu nghiệp vụ chính xác**. Cần đối soát output trong hệ thống đích.

Thêm các chỉ số để giải thích hiệu suất:

- **Error/skip rate:** số record bị lỗi hoặc skip hợp lệ/không hợp lệ trong cửa sổ.
- **Retry amplification:** số attempt cho mỗi đơn vị thành công, hoặc số retry trên mỗi record.
- **Failure rate:** tỷ lệ job/step/partition thất bại.
- **Lag/backlog:** tổng việc đang chờ và tuổi của công việc cũ nhất.
- **Elapsed time:** thời gian hoàn thành toàn job/pipeline, gồm cả phần chờ liên quan SLA.

## 4. Tính throughput bắt buộc từ SLA

Đừng đo xong rồi mới đặt một mục tiêu records/s tùy ý. Hãy **suy ra từ khối lượng và thời gian khả dụng**.

Gọi:

- `V`: khối lượng item nghiệp vụ phải hoàn tất.
- `T_window`: số giây từ lúc bắt đầu đủ dữ liệu đến deadline.
- `T_fixed`: thời gian cố định dành cho scheduling, khởi tạo, bước phụ, publish/đối soát.
- `T_recovery`: ngân sách dự phòng cho retry, restart, incident recovery.
- `T_process = T_window - T_fixed - T_recovery`: thời gian thực để xử lý dữ liệu.

Nếu `T_process > 0`, tốc độ hữu ích tối thiểu:

\[
R_{\mathrm{required}} = \frac{V}{T_{\mathrm{process}}}
\]

Nếu cần một biên năng lực cao hơn tối thiểu, dùng hệ số dự phòng đã định nghĩa rõ:

\[
R_{\mathrm{target}} =
R_{\mathrm{required}}\,(1+h)
\]

Trong đó `h=0,20` nghĩa là **mục tiêu throughput cao hơn tối thiểu 20%**; điều này khác với điều kiện vận hành tại **tối đa 80% công suất**, vốn yêu cầu công suất `R_required/0,8`.

### Ví dụ tính có headroom

Giả sử:

- 18 triệu giao dịch phải sẵn sàng trong **90 phút** kể từ mốc upstream được xác nhận.
- Dành 5 phút khởi tạo/đối soát/publish và **10 phút** cho một sự cố nhỏ + khởi động lại.
- Còn `90 - 5 - 10 = 75` phút, tương đương **4.500 giây** xử lý.
- `R_required = 18.000.000 / 4.500 = 4.000` giao dịch hợp lệ/giây.
- Nếu yêu cầu dự phòng throughput **20%**, `R_target = 4.800` giao dịch hợp lệ/giây.

Một bài kiểm thử đạt 5.000 lần gọi processor/giây nhưng chỉ ghi thành công 3.900 giao dịch/giây **chưa đạt** mục tiêu. Ngược lại, đạt 4.900 giao dịch/giây trong 30 giây rồi sụt còn 2.500 trong 60 phút cũng **chưa chứng minh** hệ thống đáp ứng deadline.

Với tải cực đại 26 triệu giao dịch, cần tính lại theo thời gian cửa sổ có thể thay đổi. Nếu vẫn 75 phút xử lý, `R_required≈5.778` giao dịch/giây, mục tiêu thêm 20% vào khoảng **6.933** giao dịch/giây. Việc lấy tốc độ trung bình ngày thường làm chuẩn duy nhất sẽ bỏ qua ngày cao điểm.

## 5. Thu thập baseline đại diện production

Trước khi scale, tạo baseline từ một cấu hình ổn định và tài nguyên có thể lặp lại.

**Dữ liệu đầu vào cần đại diện:**

- Volume thường ngày, p95/p99 theo ngày, ngày cao điểm và kịch bản tăng trưởng đã dự báo.
- Kích thước record, độ phức tạp nghiệp vụ, tỷ lệ filter/skip, khả năng dữ liệu gây retry.
- Phân bố khóa partition và hot keys, record lớn, skew giữa dải thời gian/ID/tenant.
- Tần suất phát sinh lỗi downstream, latency query/API và đặc điểm giao dịch.
- Cùng khoảng tải của ứng dụng khác đang dùng chung database, broker, storage hoặc API.

**Môi trường cần tương đồng những gì thật sự giới hạn tốc độ:**

- Cấu hình JVM/GC, số vCPU/RAM, container requests/limits, số replica.
- Phiên bản Spring Batch, JDBC driver, database và broker; schema, indexes, statistics.
- `DataSource` pool size, connection cap, isolation, timeout, chunk size, số executor threads.
- Đường mạng, số kết nối, quota/429 của dịch vụ ngoài, queue topology và cơ chế ack.
- Các trigger chạy đồng thời, backup, ETL khác hoặc tác vụ DBA theo lịch.

Nếu dùng staging nhỏ hơn production, phải ghi rõ sự khác biệt và **không ngoại suy tuyến tính** từ records/s staging sang production mà không có benchmark hoặc mô hình capacity đã kiểm chứng.

Một baseline có giá trị gồm cả **thời gian hoàn thành, throughput hữu ích và dấu hiệu nút thắt** (CPU, I/O, DB lock, connection wait, queue lag, GC). Chỉ một con số “job mất 70 phút” chưa đủ để chọn cách scale.

## 6. Chạy benchmark theo quy trình nhất quán

Đề xuất quy trình đo cho mỗi ứng viên cấu hình:

1. **Chốt phiên bản và dataset**: cùng code, schema, index, phân bố dữ liệu và yêu cầu output; ghi commit/config của bản chạy thử.
2. **Chuẩn bị trạng thái đầu vào**: reset/migrate dữ liệu thử có kiểm soát, xử lý dữ liệu đã được ghi từ lần đo trước; không để cache hoặc upsert bỏ qua dữ liệu làm méo so sánh.
3. **Warm-up đúng mức**: cho JVM, connection pool và DB cache ổn định nếu phù hợp; ghi riêng chi phí cold start nếu SLA có tính startup.
4. **Chạy đủ dài**: phải bao trùm giai đoạn đầu, giữa và cuối dữ liệu, thời điểm flush/GC/DB checkpoint và đường găng partition lớn.
5. **Thu thập ở nhiều mức**: ít nhất tại baseline, mức concurrency dự kiến và một hoặc hai mức cao hơn/thấp hơn; không mặc định thêm worker luôn cải thiện.
6. **Lặp và báo phân bố**: chạy nhiều lần để thấy biến thiên; dùng median, p95 và worst case khi số lượng mẫu có ý nghĩa. Với số mẫu rất ít, nêu rõ chưa đủ căn cứ để khẳng định percentile.
7. **Thử tải cạnh tranh**: cho ứng dụng online hoặc job khác chạy ở tải đại diện; xác định SLA nào bị ảnh hưởng.
8. **Thử failure/restart**: kết hợp kịch bản mất worker, timeout DB, broker redelivery hoặc restart manager với đo tổng thời gian thực tế.
9. **Đối soát dữ liệu**: kiểm tra count, unique key, tổng tiền/hash/tính toàn vẹn theo nghiệp vụ; ghi retry/skip đúng chính sách.
10. **Lưu bằng chứng**: report, dashboard permalink, log trace, cấu hình, dữ liệu thử và phiên bản áp dụng.

Ví dụ mẫu báo cáo giả định (không phải số đo thực):

| Cấu hình | Dữ liệu | Output hợp lệ/s trung bình | p95 chunk latency | Job duration | DB CPU p95 | Kết quả |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| 1 worker | 18M | 2.100 | 1,2 s | 143 phút | 42% | Trượt thời hạn |
| 4 workers | 18M | 4.950 | 1,6 s | 64 phút | 71% | Có tiềm năng |
| 6 workers | 18M | 5.250 | 2,1 s | 61 phút | 84% | Cần kiểm tra headroom |
| 10 workers | 18M | 4.700 | 5,0 s | 68 phút | 98% | Không đáng scale thêm |

**Không so sánh lẫn lộn throughput trung bình và thời gian job nếu phạm vi đo khác nhau.** Ví dụ records/s chỉ đo giai đoạn reader/writer active, còn job duration bao gồm scheduling hoặc publish. Hãy chú thích phương pháp tính và mốc đo rõ ràng.

Khi DB gần bão hòa, throughput đạt mức trần có thể đi kèm **tỷ lệ timeout/retry tăng mạnh**, làm giảm khả năng đáp ứng SLA trong ngày cao điểm hoặc khi worker chết.

## 7. Mở rộng phải giải quyết đúng nút thắt

Trong Spring Batch, các mô hình scale có điều kiện vận hành riêng:

| Mô hình | Throughput có thể tăng khi | Điều phải xác nhận trước production |
| --- | --- | --- |
| **Multi-threaded step** | Xử lý item đủ độc lập, CPU hoặc I/O có thể song song | `ItemReader`/`ItemWriter` và state thread-safe, checkpoint không bỏ sót/lặp, executor/pool giới hạn |
| **Parallel steps** | Có nhiều flow/step độc lập về dữ liệu và tài nguyên | Không tạo race phụ thuộc, đo đường găng thay vì cộng tổng step durations |
| **Local partitioning** | Có thể chia nguồn theo range/key/file và một JVM còn headroom | Boundary ổn định, partition skew, checkpoint và restart từng `StepExecution` |
| **Remote partitioning** | Cần thêm CPU/RAM ở nhiều node, broker/network/DB còn headroom | Manager–worker correlation, trạng thái partition, worker lạc, deploy, queue và retry |
| **Remote chunking** | Đọc nhanh, xử lý/ghi tốn thời gian, worker có thể xử lý chunk độc lập | In-flight/ack/redelivery, idempotent writer, manager throughput, broker/backpressure |

Cần xác định **bottleneck ban đầu**, tối ưu truy vấn/chunk/serialization/caching phù hợp, rồi mới chọn mô hình scale. Nếu database đã mất nhiều thời gian chờ lock hoặc storage chạm trần, tăng thêm 20 worker thường không giải quyết nguyên nhân.

### Ước tính giới hạn DB connection

Với `W` worker replicas, mỗi worker có pool tối đa `P` connection tới cùng database, ngân sách trần đơn giản là:

\[
W\cdot P + C_{\mathrm{manager}} + C_{\mathrm{other}}
 + C_{\mathrm{reserve}} \le C_{\mathrm{db,max}}
\]

Ví dụ 8 pod, mỗi pod có `maximumPoolSize=12` sẽ **có khả năng dùng tới 96 connection** chỉ cho một pool worker; phải cộng các pool khác và chừa ngân sách cho dịch vụ online, admin và failover. Pool size là **giới hạn tối đa**, không phải số connection đang mở thực tế tại mọi thời điểm.

Đo đồng thời DB CPU, I/O, WAL/redo, lock waits, connection acquisition latency, query latency và replication lag. Công thức chỉ giúp tránh vượt trần connection; DB vẫn có thể bão hòa do CPU/I/O/lock trước khi chạm trần slot.

### Đọc throughput theo chi phí tài nguyên

Hai cấu hình cùng 4.800 giao dịch/giây có thể khác nhau lớn:

- A dùng 70% DB CPU và không tăng lock wait/timeout.
- B dùng 97% DB CPU, p95 query tăng gấp đôi và nhiều chunk rollback.

Nếu cả hai đáp ứng SLA, A có thể an toàn hơn cho production vì còn headroom xử lý tải đỉnh và lỗi. Kết quả quyết định nên so sánh **throughput hiệu dụng trên một đơn vị tài nguyên và tác động lên hệ thống dùng chung**, bên cạnh thời gian hoàn thành.

## 8. Xác nhận throughput khi có retry, skip và restart

Production không vận hành trong trạng thái lý tưởng mãi. Một benchmark cần cho thấy **số đơn vị đúng hoàn tất trong hạn**, ngay cả khi một phần công việc phải thực hiện lại.

### Các kịch bản cần thử

| Kịch bản | Cách thử có kiểm soát | Tiêu chí thành công |
| --- | --- | --- |
| Worker chết trước commit | Kill một worker ở staging trong lúc xử lý chunk | Chunk chưa commit được xử lý lại theo chính sách, không mất record |
| Worker chết sau side effect ngoài transaction | Cho writer gọi API rồi dừng worker trước khi nhận ack | Idempotency key/chống trùng ngăn tác dụng phụ lặp |
| Partition skew | Dữ liệu một partition lớn hơn hẳn phần còn lại | Tổng job vẫn trong deadline, partition lớn được quan sát |
| DB pool cạn/DB timeout | Giới hạn kết nối hoặc tạo tải cạnh tranh có kiểm soát | Retry có giới hạn/backoff, throughput phục hồi sau giảm tải |
| Broker chậm hoặc redelivery | Tạo độ trễ message và phát lại ở staging | Không nhân đôi output, backlog được tiêu thụ an toàn |
| Restart sau lỗi step | Cho job dừng giữa chừng, restart với thông số định danh phù hợp | Chỉ phần cần xử lý lại được thực thi, output được đối soát |
| Thời gian khởi động lâu | Restart toàn bộ worker/manager | Tính startup + recover + catch-up vào tổng SLA |

**Không tự sửa metadata trong `BATCH_*` để đánh dấu job đã xong.** Dùng cơ chế stop/restart được ứng dụng và Spring Batch hỗ trợ; xác nhận worker cũ đã dừng hoặc được cô lập trước khi reassign partition.

Tính hiệu quả phục hồi theo:

\[
T_{\mathrm{total}} =
T_{\mathrm{normal\,work}} +
T_{\mathrm{detect}} + T_{\mathrm{repair/restart}} +
T_{\mathrm{replay}} + T_{\mathrm{validate/publish}}
\]

Đây là mô hình thời gian có thể chồng lấn một số phần trong hệ thống thực; khi báo cáo SLA hãy dùng **thời gian wall-clock thực tế** từ mốc cam kết đến output sẵn sàng, tránh cộng các giai đoạn chồng lấn hai lần.

**Đạt throughput thường ngày chưa đủ nếu recovery kéo dài hơn phần dự phòng trong SLA.** Một hệ thống có throughput 6.000/s nhưng cần 45 phút để tìm worker lỗi có thể không bằng hệ thống 5.000/s nhưng khôi phục có kiểm soát trong 5 phút.

## 9. Đo đúng tiến độ với JobRepository và metrics

Spring Batch `JobRepository` là nguồn trạng thái chuẩn của `JobExecution` và `StepExecution`, nhưng không phải một time-series metric store hoặc heartbeat liên tục.

### 9.1. SQL đọc thời lượng của job

Ví dụ truy vấn chỉ đọc với tên bảng mặc định (thay đổi prefix/schema nếu ứng dụng cấu hình khác):

```sql
SELECT
    ji.JOB_NAME,
    je.JOB_EXECUTION_ID,
    je.STATUS,
    je.EXIT_CODE,
    je.START_TIME,
    je.END_TIME
FROM BATCH_JOB_EXECUTION AS je
JOIN BATCH_JOB_INSTANCE AS ji
  ON ji.JOB_INSTANCE_ID = je.JOB_INSTANCE_ID
WHERE ji.JOB_NAME = ?
ORDER BY je.JOB_EXECUTION_ID DESC;
```

Dấu `?` là tham số cho prepared statement. `END_TIME` rỗng khi execution đang chạy hoặc chưa ghi kết thúc; không được tự điền giờ hiện tại và coi đó là thời gian hoàn thành chính thức. Một số SQL dialect xử lý alias/timestamp khác nhau, cần điều chỉnh cho DB đích.

### 9.2. Theo dõi step/partition

```sql
SELECT
    STEP_EXECUTION_ID,
    JOB_EXECUTION_ID,
    STEP_NAME,
    STATUS,
    READ_COUNT,
    WRITE_COUNT,
    FILTER_COUNT,
    READ_SKIP_COUNT,
    PROCESS_SKIP_COUNT,
    WRITE_SKIP_COUNT,
    COMMIT_COUNT,
    ROLLBACK_COUNT,
    START_TIME,
    END_TIME
FROM BATCH_STEP_EXECUTION
WHERE JOB_EXECUTION_ID = ?
ORDER BY STEP_EXECUTION_ID;
```

Với partitioning, so sánh các `STEP_NAME` và thời lượng của từng partition; **partition chậm nhất** có thể quyết định thời điểm hoàn thành chung. Trong multi-threaded step, nhiều thread chia sẻ một `StepExecution`, vì vậy metadata này không đủ để quy trách nhiệm cho từng thread.

`LAST_UPDATED` (nếu có truy vấn) thể hiện lúc metadata được cập nhật, **không phải heartbeat từng giây**. Một step đang xử lý chunk dài có thể không cập nhật trong nhiều phút dù worker còn sống.

### 9.3. Metric tiến độ riêng cho SLA

Ngoài metadata, nên xuất các metric application theo quy ước nhất quán, ví dụ:

```text
# Ví dụ tên metric tự thiết kế, không mặc định được Spring Batch xuất.
batch_business_accepted_total{job="dailyPaymentReconciliation"} 18000000
batch_business_rejected_total{job="dailyPaymentReconciliation"} 17
batch_active_workers{job="dailyPaymentReconciliation"} 6
batch_last_success_timestamp_seconds{job="dailyPaymentReconciliation"} 1792936800
```

Các metric trên chỉ là ví dụ mô tả **ngữ nghĩa**; muốn dùng trong Prometheus/Grafana phải triển khai instrumentation đúng. Với counter, dùng rate/increase trên cửa sổ thời gian phù hợp. Không dùng `jobExecutionId`, `recordId` hay `partitionId` tùy ý làm label trên mọi metric nếu gây cardinality lớn; đặt các ID chi tiết trong log/tracing.

Để kiểm tra output đúng, dùng bảng audit/đối soát nghiệp vụ hoặc metric accepted đã chuẩn hóa, **không lấy một counter tăng trước khi transaction commit làm bằng chứng thành công**. Nếu metric được phát trước commit mà transaction rollback, counter có thể cao hơn output thực tế.

## 10. Cảnh báo và theo dõi khả năng trượt SLA

Chỉ cảnh báo “job FAILED” là quá muộn nếu có thể **dự báo trượt deadline** trước khi lỗi xảy ra.

### 10.1. Theo dõi ETA và tốc độ còn cần

Giả sử tại thời điểm `t`:

- `V_remaining`: số đơn vị nghiệp vụ thực sự còn phải hoàn tất.
- `D`: deadline.
- `T_reserved`: thời gian cần dành cho validate/publish và recovery còn lại.

Tốc độ còn cần để đúng hạn:

\[
R_{\mathrm{catchup}}(t) =
\frac{V_{\mathrm{remaining}}}
     {D - t - T_{\mathrm{reserved}}}
\]

Công thức chỉ dùng khi mẫu số dương. Nếu `D - t - T_reserved \le 0` mà vẫn còn việc, deadline đang ở tình trạng nguy cấp. Dùng tốc độ **hữu ích có tính cửa sổ** thay cho tốc độ tức thời và nhớ rằng việc còn lại có thể khó hơn (partition skew), vì vậy ETA có độ bất định.

Ví dụ còn 6 triệu record và 25 phút tới hạn, trong đó 5 phút phải dành cho đối soát; tốc độ tối thiểu cần là `6.000.000/(20×60)=5.000` record/giây. Nếu hệ thống chỉ duy trì 3.000/s và DB đã bão hòa, việc tăng worker không mặc định giúp đạt 5.000/s; cần kích hoạt kế hoạch ứng phó.

### 10.2. Ma trận cảnh báo đề xuất

| Tín hiệu | Mục tiêu quan sát | Hành động |
| --- | --- | --- |
| ETA vượt deadline có dự phòng | Cảnh báo sớm khi xu hướng không đạt | Điều tra partition chậm, bottleneck và việc có thể tối ưu |
| Throughput hữu ích dưới `R_required` đủ lâu | Phân biệt slowdown tạm thời và suy giảm bền vững | Xem CPU, DB, broker, GC, retry và data skew |
| Backlog/oldest-item age tăng | Đánh giá tốc độ tiêu thụ so với nguồn | Hạn chế phát việc, tối ưu downstream, tránh scale mù |
| Pool pending/DB lock wait tăng | Nhận diện DB gần trần | Dừng tăng concurrency, điều chỉnh pool và truy vấn |
| Retry/rollback/skip ngoài ngưỡng | Phát hiện lỗi kỹ thuật hoặc dữ liệu sai | Kiểm tra exception gốc, idempotency và chính sách skip |
| Partition không tiến triển | Phát hiện worker kẹt hoặc partition lệch | Ghép `StepExecution` với runtime/log, xác minh trước khi restart |
| Đối soát output có sai lệch | Coi là lỗi chất lượng nghiêm trọng dù job `COMPLETED` | Ngừng publish nếu cần, điều tra và sửa dữ liệu |

Ngưỡng cảnh báo phải dựa trên baseline, khả năng biến động theo giờ/ngày và SLA, tránh giả định một ngưỡng records/s cho tất cả loại job. SLO của các dịch vụ online cùng dùng database vẫn phải được giám sát trong lúc batch tăng tốc.

## 11. Tính SLA theo chu kỳ, không chỉ theo một lần chạy mẫu

Một lần benchmark thành công xác nhận **khả năng kỹ thuật trong điều kiện đo**. Muốn tuyên bố tỷ lệ đạt SLA theo thời gian (ví dụ 99,5%/tháng), phải có dữ liệu lịch sử hoặc cơ chế thống kê phù hợp.

Quy tắc ví dụ cho một kỳ báo cáo:

\[
\mathrm{SLI_{on-time-and-correct}} =
\frac{\#\{\text{kỳ dữ liệu hợp lệ, đúng và sẵn sàng trước hạn}\}}
     {\#\{\text{tất cả kỳ nằm trong phạm vi cam kết}\}}
     \times 100\%
\]

Cần thống nhất trước cách tính lịch nghỉ, mất dữ liệu upstream, maintenance windows và sự kiện loại trừ. Nếu tháng có 30 kỳ chạy, **chỉ một lần trượt** đã làm tỷ lệ đạt khoảng 96,67%, nên cam kết 99,5% theo tháng có ý nghĩa rất chặt đối với batch chỉ chạy mỗi ngày một lần. Không nên báo “99,5%” dựa trên 3–5 lần chạy thử.

Ngoài tỷ lệ đạt, lưu:

- p50/p95 và thời lượng tối đa, có ghi rõ số mẫu và phân bố.
- Peak input volume và thời gian xử lý khi dữ liệu tăng.
- Số lần trượt do upstream, batch engine và downstream.
- Thời gian phát hiện, khắc phục, restart và đối soát.
- Chi phí tài nguyên/capacity và mức biến động theo phiên bản.
- Ngày phát sinh duplicate, mất dữ liệu, reconciliation discrepancy.

**Nếu chưa có đủ lịch sử**, có thể ghi “đạt tiêu chí kiểm thử tải và failure drill trong phạm vi đã thử”; tiếp tục thu thập chỉ số khi production chạy thật. Không suy diễn thành “đã đạt SLA 99,5%” khi không có số kỳ đo cần thiết.

## 12. Mẫu nghiệm thu Go/No-Go có thể kiểm toán

Một quyết định triển khai nên có các dòng chấp nhận **rõ giá trị, ngưỡng và nguồn bằng chứng**:

| Hạng mục | Mục tiêu/ngưỡng ví dụ | Bằng chứng bắt buộc | Người xác nhận |
| --- | --- | --- | --- |
| Phạm vi SLA | Dữ liệu D-1 đúng trước 04:30 | Văn bản SLA/định nghĩa mốc giờ & nghiệp vụ | Product/Data owner |
| Tải chuẩn | 18 triệu record, hoàn tất trong 90 phút kể cả publish | Báo cáo benchmark end-to-end | Batch owner |
| Tải cao điểm | 26 triệu record vẫn đúng deadline đã cam kết | Báo cáo peak-load và cấu hình | Batch owner + DBA |
| Throughput có ích | `≥ R_target` trong cửa sổ bền vững, đúng output | Dashboard output/audit + phương pháp đo | Batch owner |
| Chất lượng dữ liệu | Không có giao dịch thiếu/trùng ngoài quy tắc hợp lệ | Reconciliation tổng tiền, khóa duy nhất, skip audit | Data owner |
| Tài nguyên | DB/API/queue vẫn trong giới hạn thống nhất | Metrics DB/pool/CPU/I/O/latency | DBA/SRE |
| Sự cố & restart | Một worker crash và restart vẫn hoàn thành trong ngân sách | Failure drill + log/tracing + đối soát | Operator/QA |
| Độ ổn định | Không có xu hướng retry storm hay trượt hạn khi test lặp | Dashboard nhiều lần chạy; error budget | SRE |
| Triển khai/rollback | Có cách giới hạn worker/stop job và quay lại cấu hình cũ | Runbook và thử rollback | Ops lead |

Giá trị trong bảng là ví dụ. Mỗi sản phẩm cần thay bằng **ngưỡng được phê duyệt**, môi trường thực, mốc đo, ngày kiểm thử và liên kết bằng chứng.

Mẫu một dòng biên bản nghiệm thu:

```yaml
# Minh họa hồ sơ nghiệm thu, không phải cấu hình Spring Batch.
service: daily-payment-reconciliation
batchVersion: "build-2026.11.26"
environment: preprod-prod-like
inputProfile: peak-26m-payments
deadline: "04:30 Asia/Ho_Chi_Minh"
measuredEndToEndDurationMinutes: 81
requiredEffectiveThroughputPerSecond: 5778
measuredEffectiveThroughputPerSecond: 6990
validatedOutput: PASS
workerCrashRestartWithinBudget: PASS
databaseHeadroomAndOnlineSlo: PASS
decision: GO
evidence:
  - "benchmark report ID / dashboard link"
  - "reconciliation report ID"
approvedBy:
  - "Data owner"
  - "Batch operator"
  - "DBA/SRE"
```

Con số trong ví dụ không phải cam kết chung; trước khi ghi `GO`, phải xác nhận `measuredEndToEndDuration` khớp các mốc đo của SLA và output được kiểm toán. Một hệ thống có thể đạt mục tiêu throughput nhưng vẫn bị **NO-GO** nếu sai dữ liệu, thiếu khả năng restart hoặc gây ảnh hưởng không chấp nhận được lên API online.

## 13. Tình huống: job chạy nhanh nhưng không đáp ứng hợp đồng

Giả sử doanh nghiệp có pipeline gồm ba công đoạn:

1. Đọc giao dịch từ database nguồn và xử lý bằng 12 partition.
2. Ghi kết quả vào database đích.
3. Tạo file đối soát và xuất bản cho hệ thống kế toán.

Đội benchmark công đoạn 1 và 2 được **5.500 record/giây**, trong khi mục tiêu tính từ volume là **4.800 record/giây**. Báo cáo ban đầu đánh dấu “đạt throughput”.

Tuy nhiên, lúc chạy trên dữ liệu thật, hai partition có khóa nóng bị lock wait kéo dài. Công đoạn 1 và 2 kết thúc sau 76 phút; công đoạn 3 cần thêm 18 phút để đối soát và publish. Nếu deadline của pipeline là **90 phút**, end-to-end mất **94 phút**, tức **trượt SLA 4 phút**. Một phần record đã retry và làm metadata `READ_COUNT` tăng, nhưng số output duy nhất thấp hơn kỳ vọng.

**Chẩn đoán đúng:**

- Công thức throughput bị dùng cho phạm vi hẹp hơn deadline nghiệp vụ.
- Tốc độ 5.500/s không đại diện toàn bộ job khi partition skew và DB lock wait xuất hiện.
- Thời gian validate/publish thực tế dài hơn ngân sách ban đầu.
- Bảng kết quả cần được đối soát trước khi tuyên bố hoàn tất.

**Hành động hợp lý:**

1. Ghi lại 94 phút là **end-to-end** và coi ca chạy này **chưa đạt SLA**.
2. Đo theo từng step/partition, xác định đường găng và chi phí lock wait/đối soát.
3. Tối ưu partitioning theo khóa, transaction contention, pipeline publish hoặc điều chỉnh budget trên cơ sở nghiệp vụ.
4. Benchmark lại ở tải chuẩn và tải đỉnh; thử failure/restart, giữ giới hạn DB và đối soát kết quả.
5. Cập nhật quyết định Go/No-Go theo số liệu mới; không chỉ tăng `gridSize` hoặc pod count.

Tình huống này cho thấy phải kiểm tra **deadline của sản phẩm dữ liệu cuối cùng**, chứ không dừng ở records/s của phần xử lý chính.

## 14. Các lỗi đánh giá thường gặp

| Sai lầm | Rủi ro | Cách khắc phục |
| --- | --- | --- |
| Lấy records/s của processor làm throughput hoàn tất | Đếm cả item chưa commit hoặc đã filter | Đo output hữu ích, duy nhất và đã đối soát |
| Lấy một peak 30 giây để kết luận SLA 2 giờ | Che giấu GC, I/O, drift, skew, checkpoint | Chạy sustained test đủ dài và lặp lại |
| Chỉ đo `JobExecution` mà bỏ publish/đối soát | Pipeline trượt deadline dù job báo `COMPLETED` | Đặt mốc end-to-end |
| Dùng dataset nhỏ/đều làm đại diện | Không thấy hot key, partition lệch hoặc record lớn | Tải phân bố gần production và peak |
| Tăng worker theo queue depth bất chấp DB | Connection/lock wait tăng, throughput giảm | Tính DB budget và backpressure |
| Dùng `WRITE_COUNT` làm bằng chứng không trùng | External API hoặc broker redelivery có thể lặp tác dụng phụ | Unique key, idempotency và business reconciliation |
| Không tính thời gian restart | Trượt deadline khi worker chết | Failure drill và recovery time budget |
| Không ghi mốc/timezone | Tranh cãi SLA, sai thời gian ngày nghiệp vụ | Chốt timezone và thời điểm đầu–cuối |
| Báo 99,9% từ vài lần chạy mẫu | Số mẫu không chứng minh tỷ lệ theo kỳ | Tách load-test pass khỏi SLI lịch sử |
| Không đo ảnh hưởng lên hệ thống khác | Batch đạt SLA nhưng API production bị chậm | Đo tải chung, DB/API SLO và headroom |

## 15. Checklist thực thi trước khi đánh dấu hoàn tất

### A. Hợp đồng và đơn vị đo

- [ ] Xác định tên job/pipeline, workload, ngày nghiệp vụ và nơi tiêu thụ dữ liệu.
- [ ] SLA/SLO có deadline cụ thể, timezone, mốc bắt đầu/kết thúc và chủ sở hữu.
- [ ] Đã định nghĩa “đầu ra đúng” gồm count, unique key, tổng tiền/hash hoặc quy tắc nghiệp vụ.
- [ ] Đã chốt đơn vị throughput hữu ích và phân biệt attempted/read/written/validated.
- [ ] Đã xác định khối lượng thường ngày, tải đỉnh và mức tăng trưởng.
- [ ] Đã tính throughput tối thiểu với thời gian publish, validation và recovery reserve.

### B. Benchmark và headroom

- [ ] Chạy baseline trên dữ liệu đại diện và môi trường có giới hạn tương đồng production.
- [ ] Đo sustained throughput, end-to-end duration, percentiles và biến động nhiều lần chạy.
- [ ] Thử tải đồng thời của các job khác, API online và phụ thuộc downstream.
- [ ] So sánh số worker/threads/partitions để biết điểm bão hòa, không scale vượt ngưỡng.
- [ ] Đã tính ngân sách DB connection, CPU, memory, I/O, broker/API và headroom.
- [ ] Có bằng chứng chất lượng output và không tạo duplicate khi concurrency tăng.

### C. Reliability và khả năng vận hành

- [ ] Đã thử worker/manager crash, DB timeout, broker redelivery hoặc sự cố phù hợp topology.
- [ ] Đo thời gian phát hiện, restart, replay, validate; tổng vẫn nằm trong ngân sách SLA.
- [ ] Thread safety, checkpoint và `ExecutionContext` được thử với cấu hình concurrent thực.
- [ ] Có dashboard `JobExecution`/`StepExecution`, throughput hữu ích, lag, rollback và DB pool.
- [ ] Có alert ETA/trượt deadline, người trực, runbook dừng/giảm tải/restart.
- [ ] Có kế hoạch rollback về concurrency/build trước khi mở rộng production.

### D. Nghiệm thu Go/No-Go

- [ ] Owner nghiệp vụ đã phê duyệt phạm vi SLA và quy tắc đối soát.
- [ ] Batch lead đã phê duyệt benchmark, throughput và kịch bản failure.
- [ ] DBA/SRE xác nhận headroom và ảnh hưởng tới dịch vụ khác ở ngưỡng chấp nhận.
- [ ] Đã lưu báo cáo, dashboard, log/correlation, config/version và ngày thử nghiệm.
- [ ] Có quyết định `GO` hoặc `NO-GO` cùng lý do và điều kiện đánh giá lại.

**Nếu một tiêu chí bắt buộc chưa đạt**, giữ trạng thái nghiệm thu **chưa hoàn tất** và ghi rõ blocker, người phụ trách cùng bằng chứng cần bổ sung. Không đổi ý nghĩa “đã xác nhận” thành “có thể đạt trong điều kiện lý tưởng”.

## 16. Bài tập áp dụng

**Bài tập 1 — Tính mục tiêu throughput.** Job cần hoàn thành 9 triệu đơn hàng trong 50 phút. Dành 5 phút khởi động/publish và 5 phút cho recovery. Hãy tính tốc độ tối thiểu và mục tiêu có dự phòng throughput 15%.

Giải: thời gian xử lý `50 - 5 - 5 = 40` phút = 2.400 giây; `R_required = 9.000.000 / 2.400 = 3.750` đơn hàng/giây; `R_target = 3.750 × 1,15 = 4.312,5` đơn hàng/giây. Khi chọn ngưỡng số nguyên, có thể làm tròn lên **4.313** đơn hàng hợp lệ/giây. Vẫn phải thử trên dữ liệu đỉnh và với đối soát output.

**Bài tập 2 — Phân biệt throughput hữu ích.** Một worker xử lý 1.000 message/phút, trong đó 150 là redelivery của message đã thành công, 50 thất bại và 800 tạo record hợp lệ mới. Có thể tuyên bố 1.000 record/s thành công không?

Không. Thông lượng hữu ích ở ví dụ này là `800/60 ≈ 13,33` record hợp lệ mới/giây. Nếu record còn phải được publish/đối soát, cần kiểm tra thêm giai đoạn đó; attempted message throughput = `1.000/60 ≈ 16,67` attempt/giây.

**Bài tập 3 — Quyết định Go/No-Go.** Job benchmark hoàn tất trong 62 phút so với SLA 70 phút, nhưng một lần thử kill worker khiến job phải restart 28 phút, tạo output trùng ở API đích. Có được đánh dấu “đã xác nhận SLA và throughput” không?

**Không**. Chưa đáp ứng khả năng phục hồi và tính đúng đắn. Cần bổ sung idempotency/chống trùng, thử lại, tính vào ngân sách phục hồi; đo end-to-end khi sự cố thực xảy ra rồi mới quyết định.

## Tài liệu tham khảo

- [Spring Batch — Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html): các mô hình multi-threaded step, parallel steps, remote chunking và partitioning.
- [Spring Batch — Monitoring and Metrics](https://docs.spring.io/spring-batch/reference/monitoring-and-metrics.html): khả năng giám sát batch và các metric liên quan; đối chiếu tên metric theo phiên bản thực tế.
- [Spring Batch — JobRepository](https://docs.spring.io/spring-batch/reference/job/configuring-repository.html): repository lưu metadata, job/step execution và trạng thái phục hồi.
- [Spring Batch — Metadata Schema](https://docs.spring.io/spring-batch/reference/schema-appendix.html): các bảng `BATCH_JOB_EXECUTION`, `BATCH_STEP_EXECUTION` và context.
- [HikariCP — Configuration](https://github.com/brettwooldridge/HikariCP#configuration-knobs-baby): giới hạn pool và hành vi chờ kết nối JDBC.

**Tiêu chuẩn kết thúc:** hạng mục “**Đã xác nhận SLA và throughput**” chỉ được đánh dấu đạt khi có **cam kết đo lường rõ ràng, throughput hữu ích đủ cho tải đỉnh, thời gian end-to-end đúng hạn, dữ liệu đúng sau retry/restart, downstream còn headroom và bằng chứng có thể kiểm tra lại**. Đây là điều kiện production readiness cho một Spring Batch job mở rộng bền vững, không phải một con số records/second đẹp trong benchmark.


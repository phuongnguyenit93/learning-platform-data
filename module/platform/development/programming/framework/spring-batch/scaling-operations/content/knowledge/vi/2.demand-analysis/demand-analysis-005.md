# Xác định SLA và cửa sổ chạy batch

Một job Spring Batch đọc được 60 triệu bản ghi nhưng mất 7 giờ để hoàn tất có thể hoạt động đúng về kỹ thuật mà vẫn **không đáp ứng yêu cầu kinh doanh** nếu dữ liệu phải sẵn sàng trước 06:00. Ngược lại, tăng số worker để hoàn thành trong 2 giờ có thể không đem lại giá trị nếu job chỉ được phép truy cập database trong một cửa sổ 4 giờ và mức tăng tải gây ảnh hưởng giao dịch trực tuyến.

Vì vậy, trước khi chọn multi-threaded step, parallel steps, partitioning hoặc remote processing, cần xác định **SLA** (*Service Level Agreement*) và **cửa sổ chạy batch** (*batch window*) bằng các con số có thể đo và kiểm chứng. Đây là chủ đề thuộc chương **Phân tích nhu cầu** của module **SPRING_BATCH_SCALING_OPERATIONS**: mở rộng xử lý dữ liệu lớn dựa trên nút thắt thực tế, bảo đảm thread safety, retry/restart và khả năng vận hành đúng hạn.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt SLA, SLO và SLI khi đo một pipeline Spring Batch.
2. Chuyển yêu cầu “dữ liệu phải có vào sáng mai” thành deadline, mốc sẵn sàng đầu vào, tiêu chí chất lượng và cửa sổ thực thi rõ ràng.
3. Lập **time budget** bao gồm khởi động, xử lý, xác minh, xuất bản kết quả và thời gian dự phòng phục hồi.
4. Tính throughput tối thiểu và capacity cần có từ dữ liệu đầu vào, deadline và các ràng buộc tăng trưởng.
5. Phân tích dependency, critical path và tài nguyên dùng chung để chọn mô hình scale phù hợp.
6. Thiết kế cảnh báo sớm khi job có nguy cơ trễ SLA, thay vì chỉ biết khi job đã quá hạn.
7. Định nghĩa nghiệm thu bằng một bộ workload, ngưỡng đo và kịch bản lỗi/restart có thể tái lập.

## 2. SLA, SLO và SLI khác nhau thế nào?

Ba khái niệm liên quan nhưng không đồng nhất:

| Khái niệm | Ý nghĩa | Ví dụ cho batch |
| --- | --- | --- |
| **SLA** | Cam kết dịch vụ với đối tác/người dùng, thường có quy định trách nhiệm hoặc hậu quả nếu không đạt | Báo cáo giao dịch ngày D phải được xuất bản chậm nhất 06:00 ngày D+1 theo giờ Việt Nam |
| **SLO** (*Service Level Objective*) | Mục tiêu vận hành định lượng, có thể nghiêm hơn mức cam kết để tạo headroom | 99,9% các lần chạy đủ điều kiện hoàn tất và xuất bản trước 05:45 trong một quý |
| **SLI** (*Service Level Indicator*) | Phép đo thực tế dùng để đánh giá mục tiêu | Tỷ lệ run có trạng thái thành công, dữ liệu đầy đủ và `publishedAt ≤ deadline` |

SLA không chỉ là “mất bao nhiêu phút để chạy job”. Một job có `BatchStatus.COMPLETED` vẫn có thể vi phạm SLA nếu thiếu bản ghi, trễ xuất bản, dữ liệu quá cũ hoặc không thể truy cập ở downstream. Cần tách các chiều đo:

- **Timeliness (đúng hạn):** kết quả đã sẵn sàng trước deadline chưa?
- **Completeness (đầy đủ):** đã xử lý đủ phạm vi dữ liệu phải có chưa?
- **Correctness/quality (đúng và đạt chất lượng):** tổng tiền, số lượng, khóa duy nhất, reconciliation và quy tắc nghiệp vụ có đạt không?
- **Freshness (độ mới):** kết quả đại diện cho dữ liệu tới mốc nào?
- **Availability (khả dụng):** downstream có đọc/sử dụng được dữ liệu đã xuất bản không?
- **Recoverability (khả năng phục hồi):** nếu job lỗi, còn thời gian khắc phục và restart trước deadline hay không?

Ví dụ một job hoàn tất lúc 05:00 nhưng chỉ chứa giao dịch đến 20:00 của ngày D (thay vì đến 23:59:59) có thể **đúng hạn về thời gian** nhưng **sai về freshness/completeness**.

### 2.1. Viết SLO đủ chính xác để đo

Mẫu diễn đạt:

> Với mỗi **business date D** có upstream input hợp lệ đến 00:15 ngày D+1, hệ thống phải xuất bản snapshot dữ liệu đầy đủ đến hết ngày D trước 05:30 (múi giờ `Asia/Ho_Chi_Minh`). Tính thành công khi dữ liệu đã được kiểm tra reconciliation, checkpoint/manifest hoàn tất và downstream đọc được snapshot. Trong một quý, ít nhất 99,5% số run đủ điều kiện phải đạt mốc này; mọi vi phạm bắt buộc ghi nhận và điều tra.

Đây là **mẫu giả định**, không phải SLA mặc định của Spring Batch. Khi thỏa thuận SLA thật, phải chốt:

1. Đơn vị đo: **mỗi ngày**, mỗi kỳ chốt sổ, mỗi file đến hay mỗi đợt xử lý?
2. Run nào được tính vào mẫu số: ngày nghỉ, ngày không có input, reprocess, backfill, run thử có tính không?
3. Deadline gắn với múi giờ nào và quy tắc chuyển giờ mùa hè (*DST*) ra sao?
4. “Hoàn tất” là `JobExecution.COMPLETED`, DB commit cuối hay **kết quả đã được kiểm tra và xuất bản**?
5. Input đến muộn có làm dịch deadline không? Ai chịu trách nhiệm và điều kiện loại trừ nào được thống nhất?
6. Vi phạm SLA kéo theo cảnh báo, rollback, giao bản tạm hay quy trình xử lý nghiệp vụ nào?

Nếu job mỗi ngày một lần, SLO 99,9% trên 30 ngày chỉ cho phép khoảng `0,03` lần trễ theo kỳ tính toán lý thuyết; đây không phải “ngân sách 0,03 lần” có thể sử dụng thực tế vì một lần trễ đã là sự kiện nguyên. Cần chọn **kỳ đánh giá** và quy tắc xử lý vi phạm cho phù hợp tần suất chạy.

### 2.2. Chất lượng dữ liệu là một phần của kết quả

Đừng chỉ định nghĩa:

~~~text
SLA đạt khi JobExecution.status == COMPLETED
~~~

Thay bằng tiêu chí tổng hợp:

~~~text
run_success =
    job_completed
    AND input_watermark >= expected_cutoff
    AND processed_count + accepted_rejections == expected_count
    AND reconciliation_passed
    AND output_published
    AND output_readable_by_downstream
    AND published_at <= deadline
~~~

Đây là biểu thức chính sách minh họa. `accepted_rejections` phải thuộc danh mục lỗi dữ liệu đã được thống nhất; không tự coi mọi dòng bị skip là hợp lệ. Có thể có các SLO riêng cho **chất lượng dữ liệu**, **đúng hạn** và **khả dụng** để tìm nguyên nhân vi phạm rõ hơn.

## 3. Xác định các mốc thời gian trước khi đo throughput

Cần lập một timeline bao gồm nguồn dữ liệu, batch, downstream và quy định vận hành. Ví dụ có một báo cáo tổng hợp cho ngày nghiệp vụ D:

| Mốc | Thời điểm (D+1, UTC+07:00) | Ý nghĩa |
| --- | --- | --- |
| **Cutoff dữ liệu** | Hết 23:59:59 ngày D | Giới hạn dữ liệu nghiệp vụ phải có |
| **Input ready** | 00:15 | Upstream xác nhận snapshot đầy đủ, không còn cập nhật |
| **Earliest batch start** | 00:30 | Được phép bắt đầu job nặng |
| **Expected finish** | 04:45 | Mục tiêu vận hành nội bộ trước deadline |
| **Publish deadline** | 05:30 | Kết quả đã kiểm tra và downstream đọc được |
| **Business consumption** | 06:00 | Báo cáo được sử dụng trong vận hành |

Trong ví dụ này, cửa sổ được cấp cho pipeline từ **00:30 đến 05:30 = 300 phút**, nhưng **không có đủ 300 phút cho riêng xử lý item**: còn thời gian khởi tạo, tải input, xác minh và dự phòng lỗi. Khoảng 00:15–00:30 là buffer giữa upstream readiness và start, không mặc nhiên cộng vào thời gian chạy batch.

### 3.1. Phân biệt các loại cửa sổ

| Khái niệm | Câu hỏi cần trả lời |
| --- | --- |
| **Business data window** | Dữ liệu của ngày/kỳ nào được xử lý? Cutoff theo event time hay processing time? |
| **Input readiness window** | Upstream đảm bảo dữ liệu sẵn sàng vào lúc nào; có thể đến muộn bao lâu? |
| **Execution window** | Job được phép sử dụng tài nguyên mạnh từ lúc nào đến lúc nào? |
| **Maintenance/blackout window** | Khi nào database, network hoặc downstream bị hạn chế truy cập? |
| **Publish/availability window** | Khi nào kết quả phải được kiểm tra, chuyển sang trạng thái chính thức và cho người dùng đọc? |
| **Recovery window** | Khi job lỗi, còn bao nhiêu thời gian để phát hiện, xử lý và restart? |
| **Backfill window** | Xử lý lại dữ liệu lịch sử được phép diễn ra khi nào mà không ảnh hưởng kỳ hiện tại? |

Sự khác nhau giữa *data window* và *execution window* rất quan trọng: xử lý dữ liệu ngày D có thể bắt đầu sau nửa đêm D+1. Kết quả đúng hạn không tự chứng minh đã dùng đúng dữ liệu ngày D.

### 3.2. Múi giờ và DST

Ghi timezone bằng tên IANA, ví dụ `Asia/Ho_Chi_Minh`, thay vì chỉ viết “giờ địa phương”. Với múi giờ có DST, mốc 02:30 có thể **không tồn tại** hoặc xuất hiện **hai lần** trong ngày chuyển giờ. Quy tắc xử lý cần được thống nhất: giữ deadline theo giờ tường (*wall-clock time*), dùng timestamp UTC, hay điều chỉnh lịch trong ngày chuyển giờ.

Đối với deadline, nên lưu **timestamp có ngữ cảnh múi giờ**, sử dụng `Instant`/UTC để so sánh và định dạng theo business timezone khi báo cáo. Tránh kết luận thời lượng luôn là 24 giờ cho hai thời điểm “cùng giờ, khác ngày” ở vùng có DST.

## 4. Tạo time budget thực tế

Đặt:

- `W` = tổng số phút trong execution + publish window.
- `Tsetup` = thời gian chờ tài nguyên, khởi tạo và chuẩn bị input.
- `Tvalidate` = thời gian kiểm tra chất lượng, đối soát và publication.
- `Tdownstream` = thời gian bàn giao, kiểm tra downstream (nếu nằm trong deadline).
- `Trecovery` = ngân sách dự phòng cho phát hiện lỗi, retry, restart hoặc xử lý sự cố.
- `Tprocess` = thời gian cho phép xử lý dữ liệu chính.

\[
T_{\mathrm{process}}
= W-T_{\mathrm{setup}}-T_{\mathrm{validate}}
-T_{\mathrm{downstream}}-T_{\mathrm{recovery}}
\]

Với cửa sổ 00:30–05:30 = **300 phút**, lập kế hoạch minh họa:

| Thành phần | Ngân sách |
| --- | ---: |
| Khởi động, acquire nguồn input, kiểm tra manifest | 15 phút |
| Xử lý chunk/partition | **225 phút** |
| Đối soát và kiểm tra chất lượng | 15 phút |
| Xuất bản/bàn giao downstream | 15 phút |
| Dự phòng lỗi, retry, restart | 30 phút |
| **Tổng** | **300 phút** |

Dự phòng 30 phút **không phải một công đoạn luôn chạy ở cuối**. Đó là khoảng thời gian không nên tiêu hết trong kế hoạch bình thường để còn cơ hội phục hồi khi có lỗi. Nếu không có lỗi, pipeline có thể hoàn tất trước 05:00, tạo headroom.

Các con số này là ngân sách ban đầu; phải điều chỉnh bằng phân phối thời gian thực từ production hoặc tải thử đại diện. Nếu SLA cần độ tin cậy cao, dùng **p95/p99 thời lượng** và mô phỏng lỗi thay vì chỉ dùng thời gian chạy trung bình.

### 4.1. Tính throughput tối thiểu

Giả sử mỗi ngày cần xử lý **60 triệu item** độc lập trong `Tprocess = 225 phút`:

\[
R_{\mathrm{required}}=
\frac{60{,}000{,}000}{225\times60}
\approx 4{,}444\ \text{items/giây}
\]

Đây là throughput **xử lý hoàn tất, ghi bền vững**, không phải tốc độ đọc đầu vào hoặc số task được submit. Muốn vận hành ở khoảng **80% công suất đo được** để giữ headroom, công suất hữu ích tại tải đại diện cần ít nhất:

\[
R_{\mathrm{capacity}}
\ge \frac{4{,}444}{0.8}
\approx 5{,}556\ \text{items/giây}
\]

**80% là lựa chọn minh họa**, không phải “quy tắc Spring Batch”. Nếu hệ thống chỉ ổn định ở mức 65% khi có job khác cùng dùng DB, hãy chọn hệ số an toàn nhỏ hơn sau thử nghiệm. Không dự đoán throughput bằng cách lấy tốc độ đọc (items/s) rồi giả định processor và writer đều theo kịp.

### 4.2. Dự báo tăng trưởng

Nếu dữ liệu tăng 50% thành **90 triệu item/ngày**, trong khi time budget không đổi:

\[
R_{\mathrm{required,new}}
=\frac{90{,}000{,}000}{13{,}500}
\approx 6{,}667\ \text{items/giây}
\]

Với mục tiêu dùng 80% capacity:

\[
R_{\mathrm{capacity,new}}\ge\frac{6{,}667}{0.8}
\approx 8{,}334\ \text{items/giây}
\]

Ngay cả khi job hôm nay vừa đạt SLA, kiến trúc có thể không còn đủ sức khi đầu vào tăng nhanh. Phải ghi rõ **quy mô dự kiến theo quý/năm**, phân phối daily peak, ngày chốt tháng và các đợt backfill.

## 5. Đo “thời gian chạy” theo đúng ranh giới

Một câu trả lời thiếu chính xác là “job chạy 2 giờ” khi thực tế scheduler phải đợi nguồn dữ liệu 45 phút, step xử lý 2 giờ, kiểm tra 15 phút và xuất bản thêm 20 phút. Cần chọn ranh giới đo phù hợp SLA.

~~~mermaid
flowchart LR
    A["Upstream cutoff"] --> B["Input ready"]
    B --> C["Scheduled / queued"]
    C --> D["Job start"]
    D --> E["Read / process / write"]
    E --> F["Commit completed"]
    F --> G["Reconciliation"]
    G --> H["Publish"]
    H --> I["Downstream readable"]
~~~

Có thể đo riêng:

- **Data freshness lag:** từ cutoff dữ liệu tới thời điểm output đáp ứng tiêu chí truy cập.
- **Queue/start lag:** từ input ready hoặc scheduled start tới lúc JobExecution thực sự bắt đầu.
- **Job runtime:** từ `JobExecution.START_TIME` tới `END_TIME` (cần định nghĩa xử lý trường hợp null).
- **Processing time:** thời gian các step/chunk thực thi, không mặc định bằng job runtime.
- **Publish lag:** từ commit dữ liệu cuối đến lúc downstream đọc được kết quả.
- **Total SLA latency:** từ mốc nghiệp vụ đã cam kết đến kết quả được xuất bản hợp lệ.

Dùng `JobRepository` để theo dõi job/step execution, kết hợp log/metric và tín hiệu publication từ hệ thống downstream. Không dùng duy nhất `JobExecution.COMPLETED` như sự kiện “data product available” nếu còn bước validate và publish ngoài job.

## 6. Đọc dependency graph và critical path

Một batch pipeline thường có các nhánh phụ thuộc, không đơn thuần là một job:

~~~mermaid
flowchart TD
    A["Nguồn A sẵn sàng"] --> J1["Normalize A<br/>40 phút"]
    B["Nguồn B sẵn sàng"] --> J2["Normalize B<br/>70 phút"]
    J1 --> J3["Join + enrich<br/>60 phút"]
    J2 --> J3
    J3 --> J4["Aggregate<br/>45 phút"]
    J4 --> J5["Validate + publish<br/>20 phút"]
~~~

Nếu A và B sẵn sàng cùng lúc, hai bước normalize chạy song song được, critical path lý tưởng là:

\[
70+60+45+20 = 195\ \text{phút}
\]

Cộng mọi bước thành 235 phút là **sai** trong mô hình hai nhánh thực sự song song. Ngược lại, lấy bước dài nhất 70 phút và bỏ qua các bước phụ thuộc phía sau cũng sai.

Khi tính critical path cần tính thêm:

- Thời điểm **từng nguồn** thực sự sẵn sàng; nguồn B tới trễ 40 phút có thể đẩy toàn pipeline.
- Tài nguyên dùng chung: hai nhánh có thể phải chạy tuần tự nếu database chỉ chịu được một query lớn cùng lúc.
- Các khoảng đợi queue, kết nối và khóa, không chỉ CPU time.
- Tỷ lệ dữ liệu bất thường, partition bị lệch tải (*skew*) và số lần retry.
- Thời gian kiểm tra/duyệt dữ liệu thủ công nếu là bước bắt buộc của SLA.

**Parallel steps** chỉ cải thiện deadline khi các nhánh độc lập và không tranh nhau một nút thắt chung. Việc mở rộng thêm thread không tự động rút ngắn critical path nếu dependency bắt buộc tuần tự.

## 7. Chọn kiến trúc scale dựa trên thời gian và giới hạn tài nguyên

Đầu tiên hãy đo throughput hiện tại và xác định phần nào trên critical path đang tiêu thụ time budget. Sau đó chọn cách mở rộng phù hợp:

| Tình huống | Hướng thiết kế thử nghiệm | Điều phải kiểm tra |
| --- | --- | --- |
| Job chạy tuần tự nhưng đã đạt deadline với dự phòng lớn | Giữ đơn giản, tối ưu I/O và quan sát | Tránh thêm độ phức tạp không cần thiết |
| Một step xử lý chunk độc lập, processor đợi I/O | Multi-threaded step | Reader/writer thread-safe, checkpoint/restart, connection pool |
| Các bước độc lập nhưng đang chạy tuần tự | Parallel steps | Dependency, shared DB/API và transaction |
| Dữ liệu chia được thành khoảng ID/file/key ổn định | Local partitioning | Cân bằng partition, tên ổn định, reader `@StepScope`, restart partition lỗi |
| CPU/IO một máy không đủ hoặc cần scale độc lập | Remote partitioning | Worker scheduling, metadata, network/broker, input accessibility và idempotency |
| Manager reader còn đủ nhanh nhưng processor/writer là nút thắt | Remote chunking | Manager bottleneck, request/reply topology, delivery, retry và idempotency |
| Writer bị DB lock/IOPS hoặc API 429 | Tối ưu downstream, điều tiết tốc độ, chia khóa, batching | Tăng thread có thể làm trễ SLA hơn |
| Một partition kéo dài quá mức | Cải thiện partition strategy và skew | Tổng dữ liệu, checkpoint và overhead của nhiều partition |

Một architecture choice hợp lệ phải có **bằng chứng tải thử**. Ví dụ manager đọc tối đa 3.000 items/giây nhưng mục tiêu là 5.556 items/giây thì tăng số remote-chunking workers không giải quyết được riêng nút thắt của manager reader. Có thể cần partitioning dữ liệu đầu vào, tối ưu source query hoặc thiết kế pipeline khác.

### 7.1. Tính tải song song ban đầu

Giả sử một worker xử lý ổn định **400 items/giây** ở dữ liệu đại diện và không chia sẻ nút thắt:

\[
N_{\text{theoretical}} \approx \left\lceil
\frac{5{,}556}{400}\right\rceil = 14\text{ worker}
\]

Đây mới là **ước lượng lý tưởng**. Cần thử nghiệm 4, 8, 12, 16 worker và đo throughput *end-to-end*. Khi tăng worker, database, CPU, network hoặc HTTP quotas có thể khiến throughput/worker giảm. Một job có 14 worker không nhất thiết đạt 14 × 400 = 5.600 items/giây.

### 7.2. Đừng đánh đổi restartability chỉ để đạt thời gian

Khi có nhiều worker/partition, phải bảo đảm:

- Phạm vi dữ liệu mỗi partition ổn định và không chồng lấn.
- Checkpoint của `ItemStream`/`ExecutionContext` phù hợp để phục hồi.
- Writer idempotent hoặc có khóa nghiệp vụ chống ghi trùng.
- Retry/skip có giới hạn, được đối soát và phản ánh đúng chất lượng output.
- Dữ liệu đầu vào không thay đổi giữa các lần restart của cùng `JobInstance`.
- Mức song song tổng cộng không vượt ngân sách JDBC connection, broker và API.
- Thời gian phát hiện lỗi và restart được tính trong recovery budget.

Nếu một job chỉ đạt deadline khi **không xảy ra bất kỳ lỗi nào**, còn một lỗi tạm thời luôn khiến quá hạn, cấu hình đó chưa đáp ứng mục tiêu vận hành có tính phục hồi.

## 8. Thiết kế ngân sách phục hồi theo thời điểm xảy ra lỗi

Một time budget ghi “30 phút cho retry” chưa đủ nếu job có thể lỗi ngay trước deadline. Hãy mô tả toàn bộ quá trình hồi phục:

\[
T_{\mathrm{recovery\ needed}}
=T_{\mathrm{detect}}+T_{\mathrm{diagnose}}
+T_{\mathrm{restart}}+T_{\mathrm{remaining\ work}}
+T_{\mathrm{revalidate/publish}}
\]

Ví dụ lỗi xảy ra lúc 04:30, deadline 05:30, dữ liệu còn 15 phút xử lý, cần:

| Hoạt động | Thời gian |
| --- | ---: |
| Phát hiện và alert | 3 phút |
| Phân loại/khắc phục lỗi tạm thời | 10 phút |
| Khởi động lại đúng JobInstance | 2 phút |
| Chạy phần chưa hoàn tất | 15 phút |
| Reconciliation và publish | 15 phút |
| **Tổng** | **45 phút** |

Còn 60 phút đến deadline, nên **vẫn có 15 phút headroom** trong giả định này. Nếu lỗi xảy ra lúc 05:05 với cùng lượng việc chưa hoàn tất, hệ thống không thể đáp ứng deadline trừ khi có recovery nhanh hơn, phương án dự phòng hoặc thay đổi nghiệp vụ đã thỏa thuận.

### 8.1. Thiết kế ba mức cảnh báo

- **Early warning:** dự báo `estimatedCompletionAt` đã vượt mốc mục tiêu nội bộ, ví dụ 04:45.
- **At-risk:** thời gian còn lại nhỏ hơn **ước lượng xử lý phần còn lại + validate/publish + recovery cushion**; kích hoạt xử lý và thông báo owner.
- **Breached:** vượt deadline mà kết quả chưa hợp lệ và khả dụng; ghi nhận vi phạm theo chính sách.

Không nên chỉ alert khi `JobExecution.status == FAILED`. Một job vẫn `STARTED` nhưng chỉ xử lý 10% khi còn 15 phút có thể đã chắc chắn trễ SLA.

### 8.2. Ước lượng hoàn tất từ tốc độ thực

Đặt:

- `Nremaining` = số item hợp lệ còn lại ước tính.
- `Robserved` = throughput *committed items/second* ở cửa sổ đo đủ dài.
- `Tfinalize` = thời gian validation, publish và các bước còn lại.
- `TrecoveryCushion` = phần dự phòng cần giữ ở thời điểm quan sát.

\[
T_{\mathrm{ETA}} \approx
\frac{N_{\mathrm{remaining}}}{R_{\mathrm{observed}}}
+T_{\mathrm{finalize}}
\]

Nếu `Robserved = 0` hoặc không tin cậy, không lấy ETA là vô hạn rồi im lặng; phải báo trạng thái không thể dự đoán, bao gồm stall/no-progress. Với partition skew hoặc pipeline nhiều bước, ETA kiểu tổng item/giây có thể lạc quan; thay bằng **ETA critical path** và phân phối thời gian từng partition.

Quy tắc cảnh báo minh họa:

~~~text
available_seconds = deadline - now
need_seconds = estimated_remaining_processing
             + remaining_validation_and_publish
             + recovery_cushion

if now >= deadline and not output_valid_and_published:
    SLA_BREACHED
else if available_seconds < need_seconds:
    SLA_AT_RISK
else:
    SLA_ON_TRACK
~~~

Chỉ số `SLA_AT_RISK` là **dự báo**, không phải một vi phạm SLA đã xảy ra. Bản ghi cảnh báo nên chứa business date, JobInstance/JobExecution, input watermark, ETA, phần việc còn lại và contact owner.

## 9. Ví dụ Java: tính deadline và throughput yêu cầu

Ví dụ thuần `java.time` sau không phụ thuộc phiên bản Spring Batch; nó minh họa cách chuyển ngày nghiệp vụ thành deadline có timezone và tính throughput theo time budget. Ứng dụng thật nên nhận business date, data volume và timezone từ job parameters/config đã kiểm soát.

~~~java
import java.time.Duration;
import java.time.LocalDate;
import java.time.LocalTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;

public final class BatchSlaBudget {

    private static final ZoneId BUSINESS_ZONE =
            ZoneId.of("Asia/Ho_Chi_Minh");

    public record Budget(
            ZonedDateTime earliestStart,
            ZonedDateTime deadline,
            long processingSeconds,
            long requiredItemsPerSecond) {}

    public static Budget forBusinessDate(
            LocalDate businessDate, long expectedItems) {

        if (expectedItems < 0) {
            throw new IllegalArgumentException("expectedItems < 0");
        }

        LocalDate executionDate = businessDate.plusDays(1);
        ZonedDateTime earliestStart =
                executionDate.atTime(LocalTime.of(0, 30))
                        .atZone(BUSINESS_ZONE);
        ZonedDateTime deadline =
                executionDate.atTime(LocalTime.of(5, 30))
                        .atZone(BUSINESS_ZONE);

        Duration totalWindow = Duration.between(
                earliestStart.toInstant(), deadline.toInstant());

        // 15 phút setup, 15 phút validate, 15 phút publish,
        // 30 phút dự phòng retry/restart.
        Duration reserve = Duration.ofMinutes(75);
        long processingSeconds =
                totalWindow.minus(reserve).getSeconds();

        if (processingSeconds <= 0) {
            throw new IllegalStateException("No processing time budget");
        }

        long requiredRate = (long) Math.ceil(
                (double) expectedItems / processingSeconds);

        return new Budget(
                earliestStart, deadline,
                processingSeconds, requiredRate);
    }

    public static void main(String[] args) {
        Budget budget = forBusinessDate(
                LocalDate.of(2026, 11, 25), 60_000_000L);
        System.out.println(budget);
        // 13.500 giây xử lý; cần >= 4.445 items/s
        // (làm tròn lên từ 4.444,44).
    }
}
~~~

**Lưu ý:** Ví dụ dùng `ZonedDateTime` và đổi sang `Instant` khi tính khoảng cách thời gian để giảm nhầm lẫn do timezone. Tại vùng có DST, chính sách xử lý mốc giờ không tồn tại/trùng lặp vẫn phải được chốt với nghiệp vụ. `expectedItems` cũng phải lấy từ manifest đáng tin cậy; với nguồn chưa đếm được chính xác, nên đo bằng bytes/partitions hoặc độ phủ input và thể hiện độ bất định của ETA.

Nếu muốn tính **headroom 20%**, cần chia `requiredItemsPerSecond` cho 0,8 khi lập sizing. Không nhầm số 4.445 trong chương trình với 5.556 là capacity đề xuất có dự phòng ở ví dụ phía trước.

## 10. Lập lịch, quyền chạy và bảo vệ cửa sổ

Spring Batch cung cấp xử lý job, metadata, retry/restart và API chạy job; **lịch kích hoạt** thường do thành phần khác đảm nhiệm như Spring `@Scheduled`, Quartz, Kubernetes CronJob hoặc orchestrator của dữ liệu. Những lựa chọn ấy không thay đổi SLA: lịch chỉ phát tín hiệu chạy, còn kết quả phải đạt deadline.

Quy trình orchestration thường cần:

1. Chờ tín hiệu `input_ready` hoặc manifest đủ dữ liệu, không bắt đầu chỉ vì đồng hồ báo 00:30.
2. Xác minh đúng **business date** và identifying `JobParameters`; kiểm tra job cùng kỳ có đang chạy hoặc đã hoàn tất chưa.
3. Khởi chạy pipeline trong execution window cho phép.
4. Theo dõi trạng thái và progress qua `JobRepository`, metrics và tín hiệu từ downstream.
5. Nếu lỗi, xử lý retry/restart **đúng JobInstance**, giữ nguyên checkpoint và input snapshot.
6. Đối soát output, xuất bản snapshot theo cơ chế atomic swap/versioning khi phù hợp.
7. Ghi `publishedAt` và kết quả SLI/SLA, gửi cảnh báo khi at-risk hoặc breached.

### 10.1. Chồng lịch và backfill

Nếu kỳ D kéo dài đến khi kỳ D+1 bắt đầu, phải xác định chính sách:

- **Không cho chồng:** tạm hoãn kỳ mới, ưu tiên phục hồi kỳ cũ, đồng thời chấp nhận hoặc leo thang rủi ro deadline mới.
- **Cho chồng có kiểm soát:** cấp resource quota riêng, tách input/output theo business date, tránh tranh chấp metadata và DB.
- **Hàng đợi theo thứ tự ưu tiên:** kỳ hiện tại ưu tiên, backfill chạy khi có tài nguyên; vẫn giám sát deadline riêng của từng kỳ.

Đừng tăng `run.id` để “restart” một kỳ đã lỗi: đó có thể tạo **JobInstance mới** và làm mất khả năng skip dữ liệu đã hoàn tất. Backfill khác với restart và cần có job parameters, output versioning, kế hoạch đối soát riêng.

### 10.2. Blackout và tài nguyên dùng chung

Một cửa sổ 00:30–05:30 trên giấy không có nghĩa toàn bộ thời gian được dùng hết công suất. Nếu database backup từ 02:00–02:45, khóa đường truyền từ 03:00–03:15 hoặc API phía đích giới hạn ban đêm, có thể phải:

- Tách công đoạn đọc/biến đổi khỏi khoảng hạn chế ghi.
- Điều chỉnh lịch hoặc phối hợp thay đổi maintenance window với hệ thống khác.
- Dùng staging/snapshot, chỉ commit/publish vào thời điểm phù hợp.
- Kiểm tra áp lực lên online workload; ưu tiên SLA của dịch vụ giao dịch trực tuyến nếu đã được cam kết cao hơn.

Không được tính một blackout dài 45 phút vào `Tprocess` như thời gian xử lý đầy đủ khi thực tế mọi writer bị chặn.

## 11. Theo dõi SLI và báo cáo SLA qua nhiều ngày

Để đo SLA, cần **một bản ghi tổng hợp cho mỗi business run**, không chỉ một dòng `JobExecution`. Tối thiểu nên có:

| Field | Ý nghĩa |
| --- | --- |
| `businessDate` / `jobKey` | Định danh kỳ dữ liệu và workflow |
| `inputCutoff` / `inputReadyAt` | Mốc phủ dữ liệu nguồn và lúc nguồn sẵn sàng |
| `scheduledStartAt` / `actualStartAt` | Mốc lịch và mốc thực thi |
| `deadlineAt` / `publishedAt` | Deadline và thời điểm output hợp lệ sẵn sàng |
| `jobInstanceId` / `lastJobExecutionId` | Nối với metadata của Spring Batch và lịch sử restart |
| `expectedCount` / `committedCount` | Phạm vi đầu vào và dữ liệu đã ghi bền vững |
| `reconciliationStatus` | Trạng thái kiểm tra chất lượng |
| `eligible` / `eligibilityReason` | Run có thuộc mẫu số tính SLO hay không |
| `outcome` / `breachReason` | Đạt, không đạt hoặc chưa xác định; nguyên nhân vi phạm |

Ví dụ cách tính tỷ lệ đúng hạn với một kỳ báo cáo:

\[
\mathrm{SLO\ attainment}
=\frac{\text{số run đủ điều kiện đạt tất cả tiêu chí}}
{\text{tổng số run đủ điều kiện}}\times100\%
\]

Nếu có 92 run đủ điều kiện trong một quý và 91 run đạt, tỷ lệ là:

\[
91/92\times100\%\approx98.91\%
\]

Nó **không đạt** SLO 99,5%. Cần định nghĩa loại trừ input upstream bị trễ trước khi nhìn kết quả; không được tùy tiện bỏ ngày lỗi ra khỏi mẫu số để làm đẹp SLO. SLA thương mại có thể có công thức/kỳ đánh giá khác SLO nội bộ.

### 11.1. Metric cần có

- **End-to-end:** input readiness lag, scheduled-to-start lag, job runtime, publish lag, deadline slack.
- **Spring Batch:** trạng thái job/step, read/write/skip/retry/rollback/commit counts, duration, progress theo partition.
- **Nút thắt:** CPU, GC, I/O disk, JDBC pool active/pending, DB locks và slow queries, broker lag/unacked, HTTP rate limit/429.
- **Độ ổn định:** số lần restart, thời gian phục hồi, poison messages, duplicate/reconciliation failures.
- **Business correctness:** coverage/cutoff và số liệu đối chiếu trước khi publish.

Số liệu từ `JobRepository` thường có `BATCH_JOB_EXECUTION`, `BATCH_STEP_EXECUTION` cùng execution context. Giữ retention phù hợp để đối chiếu các đợt chạy và restart; không xóa metadata của job còn cần phục hồi.

### 11.2. Alert dựa trên phần thời gian còn lại

Ví dụ chính sách vận hành có thể là:

| Tình huống | Ngưỡng giả định | Hành động |
| --- | --- | --- |
| Input ready trễ | Chưa thấy manifest lúc 00:15 | Cảnh báo upstream, cập nhật ETA và quyền chạy |
| Start lag | Đến 00:45 vẫn chưa bắt đầu | Kiểm tra scheduler, backlog và kết nối |
| Throughput rơi | Throughput commit dưới mức cần thiết trong khoảng quan sát đáng tin cậy | Xem DB/API/CPU và ETA |
| ETA có nguy cơ trễ | Dự báo hoàn tất + publish sau 05:15 | On-call kiểm tra, mở runbook phục hồi |
| SLA breached | Qua 05:30 mà output chưa hợp lệ hoặc chưa đọc được | Ghi nhận breach, thông báo chủ sở hữu SLA |

Đây là các ngưỡng **minh họa**, không nên copy cứng vào hệ thống nếu chưa đo baseline. Cần làm rõ ai nhận alert, mức severity, thời gian trực, quy trình escalation và phương án xử lý khi không thể đạt deadline.

## 12. Xây dựng kế hoạch kiểm thử capacity gắn SLA

Một benchmark có giá trị phải trả lời: **“Với volume và tình huống bất lợi đại diện, pipeline có xuất bản dữ liệu hợp lệ đúng hạn không?”**

### 12.1. Ma trận tải

| Kịch bản | Dữ liệu | Mục đích |
| --- | --- | --- |
| Typical day | Khối lượng trung bình, tỷ lệ lỗi thông thường | Xây baseline |
| Peak day | p95/p99 số bản ghi theo lịch sử | Kiểm tra headroom |
| Month/quarter-end | Chênh lệch skew và truy vấn/ghi lớn | Bắt nút thắt kỳ chốt |
| Growth forecast | 1,5–2 lần typical theo dự báo | Xác minh khả năng tăng trưởng |
| Input arrives late | Input ready sau mốc cam kết | Kiểm tra dependency và policy deadline |
| DB degradation | Latency SQL tăng, pool pending | Kiểm tra giới hạn downstream |
| Worker crash / restart | Lỗi sau khi commit vài chunk | Đo thời gian phục hồi và dữ liệu không trùng |
| Concurrent online load | DB/API phục vụ hệ thống nghiệp vụ | Đánh giá tác động tài nguyên dùng chung |

### 12.2. Điều kiện nghiệm thu mẫu

Ví dụ kế hoạch *engineering acceptance* trước production (các ngưỡng phải được chủ sản phẩm xác nhận):

- Với 60 triệu bản ghi trên snapshot bất biến, output cuối cùng **đúng và đủ**, có manifest, hoàn tất và readable trước **05:30**.
- Ở tải peak đã thống nhất, p95 runtime nội bộ không vượt **mốc mục tiêu 04:45**; đây là mục tiêu benchmark, còn deadline SLA đo riêng theo mỗi run.
- Có ít nhất một thử nghiệm crash/restart thành công trong recovery budget; không làm tăng sai số đối soát.
- Không vượt ngân sách JDBC/HTTP, tỷ lệ lỗi/retry trong giới hạn và không làm xấu SLO của hệ thống online dùng chung.
- Khi giả lập pipeline trễ, cảnh báo `SLA_AT_RISK` phải xuất hiện **trước** deadline với thông tin hành động được.

Nếu chỉ chạy một lần nhanh trên dữ liệu nhỏ, kết quả không đại diện cho p95/p99 duration hay năng lực chịu lỗi. Cần lặp lại benchmark ở tải có phân phối dữ liệu, contention và dependency tương đương production.

## 13. Tình huống khó: ngày chạy không đủ cửa sổ

Giả sử tải mới 90 triệu bản ghi, trong khi hệ thống chỉ đạt **5.000 items/giây hoàn tất**:

\[
T_{\mathrm{process,actual}}
=\frac{90{,}000{,}000}{5{,}000}
=18{,}000\ \text{giây} =300\ \text{phút}
\]

Chỉ riêng xử lý đã bằng **toàn bộ cửa sổ 300 phút**, chưa tính setup, validation, publish và recovery. Kế hoạch chắc chắn **không đáp ứng** time budget 225 phút.

Các lựa chọn cần đánh giá:

1. **Tối ưu phần nghẽn:** query/index/fetch size, batch insert, transaction, I/O, partition skew; đo lại throughput thực.
2. **Scale đúng tài nguyên:** nếu CPU-bound thì thêm CPU/partition; nếu I/O-bound có thể tăng worker khi DB/API còn năng lực; nếu DB đã bão hòa thì thêm thread thường không giúp.
3. **Thay đổi pipeline:** chạy incremental/các bước tiền xử lý trước cửa sổ nếu dữ liệu và SLA cho phép; dùng staging rồi publish atomically.
4. **Thỏa thuận lại cửa sổ hoặc deadline:** nếu hệ thống đích có ràng buộc cứng, tăng năng lực không khả thi về chi phí hoặc business cho phép.
5. **Thiết kế graceful degradation có phê duyệt trước:** xuất bản phần có nhãn “partial” chỉ khi business cho phép và **không báo SLA đạt** theo tiêu chí yêu cầu dữ liệu đầy đủ.

Việc phân tích phải đưa ra **tradeoff cụ thể** giữa chi phí, deadline, tác động online service và khả năng recovery, thay vì đưa ra đề xuất “tăng số worker” chưa có kiểm chứng.

## 14. Những sai lầm thường gặp

| Nhận định | Vì sao chưa đúng? |
| --- | --- |
| “SLA là job phải có trạng thái `COMPLETED`.” | Kết quả có thể vẫn thiếu dữ liệu, sai cutoff hoặc chưa publish/readable. |
| “Cửa sổ 5 giờ thì có thể dành 5 giờ xử lý.” | Phải trừ setup, validation, publish, dependencies và recovery buffer. |
| “Thời gian chạy trung bình 4 giờ tức là luôn đạt deadline 5 giờ.” | Tail latency, skew, lỗi, input trễ và contention có thể làm nhiều ngày vượt 5 giờ. |
| “60 triệu item/225 phút chỉ cần reader đọc 4.444 items/s.” | Cần throughput **được xử lý và ghi thành công** end-to-end. |
| “Thêm worker tuyến tính sẽ tăng throughput.” | DB/API/broker/manager có thể bão hòa; overhead và tranh chấp tăng. |
| “Job chạy sớm hơn đồng nghĩa dữ liệu mới hơn.” | Nếu source cutoff không đổi, output chỉ sớm hơn, không tăng freshness. |
| “Có retry/restart thì không cần recovery buffer.” | Retry cần thời gian; restart có thể cần đối soát và chạy lại phần chưa commit. |
| “SLO 99,5% cho phép loại trừ mọi lần input trễ.” | Tiêu chí eligible phải được thỏa thuận và audit được, không tự sửa hậu nghiệm. |
| “Cửa sổ theo cron luôn là 24 giờ giữa hai lần.” | Múi giờ/DST, lịch nghỉ và overlapping executions có thể thay đổi thời gian thực. |
| “Chạy thêm backfill không ảnh hưởng kỳ hiện tại.” | Backfill cạnh tranh cùng CPU, DB, I/O, API và có thể làm trễ SLA chính. |

## 15. Checklist làm việc với nghiệp vụ và vận hành

Trước khi thiết kế kiến trúc scale, cần có văn bản thống nhất:

- [ ] Đã định nghĩa dữ liệu xử lý, business date, watermark/cutoff và nguồn xác nhận input ready.
- [ ] Đã chốt múi giờ, deadline, tập run tính SLA và cách xử lý ngày nghỉ/DST.
- [ ] Đã định nghĩa output “hoàn tất” bằng điều kiện đúng, đủ và downstream đọc được.
- [ ] Đã tách mốc input ready, earliest start, expected finish, publish deadline và blackout.
- [ ] Đã tính time budget cho setup, processing, validation, publish và retry/restart.
- [ ] Đã đo volume điển hình, peak, tăng trưởng, phân phối item size/partition skew.
- [ ] Đã tính throughput commit tối thiểu và kiểm chứng capacity với dữ liệu đại diện.
- [ ] Đã phân tích critical path, upstream/downstream dependencies và shared-resource quotas.
- [ ] Đã lựa chọn mô hình scale phù hợp với bottleneck thực, bảo đảm thread safety và idempotency.
- [ ] Đã có metadata/SLI, dashboard tiến độ, ETA và cảnh báo `at-risk` trước deadline.
- [ ] Đã thống nhất runbook khi trễ deadline, input đến muộn, crash và backfill.
- [ ] Đã có tiêu chí nghiệm thu và kết quả kiểm thử kịch bản peak/restart.

## 16. Câu hỏi tự kiểm tra

1. Job `dailySettlement` có trạng thái `COMPLETED` lúc 05:00 nhưng thiếu dữ liệu từ 23:00–23:59. SLA “chốt đầy đủ ngày D trước 06:00” có đạt không? Cần đo SLI nào?
2. Cửa sổ 00:30–05:30, setup 15 phút, validate 15 phút, publish 15 phút và recovery buffer 30 phút. Có bao nhiêu phút xử lý? Với 60 triệu bản ghi, throughput tối thiểu là bao nhiêu?
3. Nếu giữ throughput 4.444 items/giây nhưng dữ liệu tăng lên 90 triệu item, điều gì xảy ra với cửa sổ 225 phút?
4. Hai nhánh A mất 40 phút và B mất 70 phút chạy song song; sau đó cần join 60 phút và publish 20 phút. Critical path là bao lâu nếu cả hai nguồn sẵn sàng cùng lúc và không tranh tài nguyên?
5. Một job đạt throughput 6.000 items/giây khi chạy một mình nhưng chỉ 3.500 items/giây vào cuối tháng. Điều gì cần thay đổi trong capacity planning?
6. Vì sao `JobOperator.restart` không tự bảo đảm SLA nếu job lỗi lúc 05:20 với deadline 05:30?
7. Khi job vẫn `STARTED`, làm thế nào để phát hiện nguy cơ trễ trước khi `FAILED` hoặc qua deadline?
8. Vì sao một SLO tính theo mỗi lần chạy hằng ngày có thể cần kỳ đánh giá khác với một SLO tính theo hàng triệu HTTP requests?

**Gợi ý trả lời:** (1) Không, thiếu completeness/freshness; cần kiểm tra cutoff và reconciliation. (2) 225 phút, khoảng 4.444,44 items/s, nên làm tròn lên 4.445; capacity có headroom còn phải cao hơn. (3) Cần khoảng 337,5 phút ở throughput đó, vượt ngân sách. (4) `max(40,70)+60+20=150 phút`. (5) Benchmark với tải production đồng thời, peak/period-end và quota tài nguyên, không dùng số đo chạy một mình. (6) Cần thời gian phát hiện, restart, chạy phần còn lại, đối soát và publish. (7) Dựa vào tiến độ commit, remaining work, ETA critical path và time budget. (8) Tần suất mẫu nhỏ, một lần trễ tạo tỷ lệ vi phạm lớn và cần quy tắc đánh giá rõ.

## Tài liệu tham khảo

- [Spring Batch Reference — Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html): multi-threaded step, parallel flows, partitioning và remote processing, để chọn kiến trúc khi time budget thiếu.
- [Spring Batch Reference — Monitoring and Metrics](https://docs.spring.io/spring-batch/reference/monitoring-and-metrics.html): thông tin về metric job/step và quan sát thời gian xử lý.
- [Spring Batch Reference — Configuring a Step for Restart](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/restart.html): restart, checkpoint và giới hạn khi phục hồi.
- [Spring Framework Reference — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): lập lịch và TaskExecutor, là thành phần phối hợp với Spring Batch.
- [Google SRE Workbook — Implementing SLOs](https://sre.google/workbook/implementing-slos/): cách định nghĩa indicator, objective và chu kỳ đo.
- [Google SRE Workbook — Alerting on SLOs](https://sre.google/workbook/alerting-on-slos/): tư duy cảnh báo theo mục tiêu dịch vụ; khi áp dụng cho batch cần đổi sang đơn vị một run và deadline phù hợp.

**Điểm cần ghi nhớ:** Xác định SLA và cửa sổ chạy batch trước khi tăng concurrency. Hãy biến yêu cầu nghiệp vụ thành **cutoff, input ready, deadline, tiêu chí output đúng/đủ, time budget và recovery buffer**; sau đó đo throughput hoàn tất, critical path và giới hạn tài nguyên để chọn phương án scale có thể kiểm chứng. Một job nhanh nhưng dữ liệu sai hoặc không phục hồi kịp khi sự cố vẫn có thể vi phạm SLA.

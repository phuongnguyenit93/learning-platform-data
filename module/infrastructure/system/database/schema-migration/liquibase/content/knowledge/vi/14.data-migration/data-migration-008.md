# Chia nhỏ tác vụ bổ sung dữ liệu cho bảng lớn

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, chương **Chuyển đổi dữ liệu**, việc bổ sung dữ liệu (*backfill*) cho một bảng lớn là bài toán khác với việc chỉ thêm một cột vào schema. Một câu lệnh **UPDATE** có thể đúng về logic nhưng gây transaction kéo dài, giữ khóa quá lâu, tăng dung lượng transaction log/WAL, làm chậm replica và khiến thời gian triển khai không thể dự đoán. Vì vậy, cần biết **chia dữ liệu thành nhiều lô nhỏ, xử lý có kiểm soát và tiếp tục được sau lỗi**.

Phạm vi học của module là quản lý thay đổi schema và dữ liệu bằng Liquibase với **changelog, changeset, precondition, checksum và lịch sử triển khai**, thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Trong phạm vi đó, Liquibase giúp khai báo cấu trúc đích, ghi nhận các bước migration và chặn bước tiếp theo nếu dữ liệu chưa sẵn sàng. Với backfill hàng triệu bản ghi, một **job xử lý theo lô** được điều phối bên ngoài Liquibase thường thích hợp hơn một changeset chứa UPDATE khổng lồ. Điều quan trọng là phân định rõ trách nhiệm giữa các bước.

Sau bài học, người học có thể xác định khi nào cần chia lô, thiết kế thuật toán theo khóa chính và checkpoint, tạo thao tác cập nhật có thể chạy lại, xử lý dữ liệu bị ghi đồng thời, kiểm soát tải database, và đưa bằng chứng hoàn tất backfill vào quy trình triển khai Liquibase.

## 1. Backfill là gì và vì sao bảng lớn cần cách làm riêng?

**Backfill** là quá trình điền hoặc tính lại dữ liệu cho những bản ghi **đã tồn tại** nhằm đáp ứng schema hoặc quy tắc nghiệp vụ mới. Ví dụ:

- Thêm cột **search_name** rồi tính giá trị từ **full_name** cho khách hàng cũ.
- Thêm cột **order_channel** và xác định nguồn đặt hàng từ dữ liệu lịch sử.
- Chuyển giá trị từ một cột cũ sang cột mới trước khi đổi kiểu hoặc xóa cột cũ.
- Chuẩn hóa mã trạng thái trước khi thêm **CHECK** hoặc **NOT NULL**.
- Tạo khóa tra cứu hoặc dữ liệu tổng hợp để phục vụ truy vấn mới.

Một thay đổi schema có thể rất nhanh nếu chỉ tác động metadata, nhưng xử lý dữ liệu liên quan có thể đụng đến hàng triệu dòng. Ví dụ:

~~~sql
UPDATE customer
SET search_name = LOWER(TRIM(full_name))
WHERE search_name IS NULL;
~~~

Câu SQL minh họa trên có thể cập nhật hầu hết bảng **customer** nếu cột search_name vừa được thêm và tất cả giá trị đang NULL. Dù SQL ngắn, khi chạy trên bảng lớn nó có thể:

- Tạo một transaction rất dài hoặc một lượng thay đổi lớn trong thời gian ngắn.
- Giữ row lock lâu, tranh chấp với các giao dịch phục vụ người dùng.
- Sinh nhiều WAL/redo/transaction log và làm tăng độ trễ replication.
- Tạo áp lực lên CPU, I/O, cache, vacuum/garbage collection tùy DBMS.
- Gây timeout, hết tài nguyên hoặc làm chậm quá trình deploy ứng dụng.
- Khó khôi phục tiến độ nếu bị lỗi trước khi commit.

Không phải mọi UPDATE lớn đều thất bại; hiệu quả phụ thuộc DBMS, chỉ mục, bảng, isolation, phần trăm dòng thay đổi và tải hiện tại. Tuy nhiên, **kích thước dữ liệu phải là đầu vào thiết kế migration**, không được suy từ số dòng SQL.

## 2. Nguyên tắc: mỗi lô là đơn vị xử lý có thể kiểm chứng

Thay vì cập nhật toàn bộ dữ liệu trong một transaction, chia công việc thành các **batch** có giới hạn. Một batch nên có:

1. **Phạm vi xác định**: tập dòng nào được xử lý, ví dụ khoảng khóa chính hoặc một tập khóa được chọn có thứ tự.
2. **Đơn vị commit rõ ràng**: hoàn tất một batch rồi commit trước khi chuyển sang batch tiếp theo.
3. **Tính lặp lại an toàn**: retry không tạo dữ liệu sai hoặc ghi đè dữ liệu hợp lệ.
4. **Tiến độ bền vững**: biết batch nào đã commit và nên tiếp tục từ đâu.
5. **Cơ chế giảm tải**: điều chỉnh batch size, số worker và khoảng nghỉ theo trạng thái database.
6. **Điều kiện kết thúc kiểm chứng được**: không dựa duy nhất vào việc vòng lặp đã chạy đến khóa cuối.

**Batch không đồng nghĩa với changeset.** Changeset là đơn vị lịch sử migration mà Liquibase theo dõi bằng ID, author và changelog; batch là đơn vị dữ liệu được xử lý trong runtime của backfill. Một changeset có thể mô tả một khoảng dữ liệu cố định, nhưng hàng nghìn batch linh hoạt thường không nên biến thành hàng nghìn changeset được sinh động hoặc sửa đổi sau khi triển khai.

Hình dung dòng triển khai:

~~~text
Expand schema (Liquibase)
         |
         v
Ứng dụng mới duy trì dữ liệu cho bản ghi mới
         |
         v
Backfill worker chạy từng batch nhỏ
         |
         +--> batch 1 --> COMMIT --> ghi checkpoint
         +--> batch 2 --> COMMIT --> ghi checkpoint
         +--> batch 3 --> retry nếu lỗi
         |       ...
         v
Kiểm chứng không còn hàng thiếu/sai
         |
         v
Contract schema (Liquibase: precondition + constraint)
~~~

Các bước có thể nằm trong **nhiều lần phát hành**. Chỉ tách thành nhiều changeset trong cùng một changelog không tự tạo điểm dừng để backfill hoàn tất.

## 3. Chọn tiêu chí chia lô: ưu tiên khóa ổn định và có thứ tự

Phương án phổ biến nhất khi bảng có khóa chính tăng dần là **keyset batching**: duyệt bản ghi theo khóa chính mà không sử dụng OFFSET ngày càng lớn.

Giả sử bảng **customer** có:

~~~text
id BIGINT PRIMARY KEY
full_name VARCHAR(200) NOT NULL
search_name VARCHAR(200) NULL       -- cột mới
~~~

Mục tiêu: điền **search_name = lower(trim(full_name))** cho các dòng cũ; ứng dụng mới chịu trách nhiệm ghi đúng search_name cho những thay đổi tiếp theo.

### 3.1. Duyệt bằng khóa chính

Trong một job xử lý:

1. Lấy một **high-water mark** (ví dụ MAX(id)) để xác định phạm vi ban đầu cần backfill.
2. Bắt đầu cursor tại mốc trước khóa nhỏ nhất hoặc một checkpoint đã lưu.
3. Lấy tối đa N khóa thỏa **id > cursor** và **id <= highWater** theo thứ tự tăng dần.
4. Cập nhật những dòng cần bổ sung trong khoảng vừa chọn.
5. Commit cập nhật dữ liệu cùng checkpoint.
6. Tiếp tục từ khóa lớn nhất của batch đã commit.
7. Sau vòng chính, chạy kiểm tra toàn bộ điều kiện và xử lý các dòng còn sót nếu có.

Ví dụ câu truy vấn lấy ranh giới batch:

~~~sql
SELECT id
FROM customer
WHERE id > :last_id
  AND id <= :high_water_id
ORDER BY id
LIMIT :batch_size;
~~~

Đây là cú pháp minh họa phù hợp với PostgreSQL và một số DBMS. Với SQL Server, Oracle hoặc các phiên bản DBMS khác, cú pháp giới hạn số dòng có thể khác. Các tham số có dấu hai chấm do job truyền vào, **không phải biến đặc biệt tự được Liquibase hiểu**.

Nếu kết quả là các ID 101, 104, 109 thì **batch_end_id = 109**, không phải 103. Không được suy ra khóa liên tiếp chỉ vì batch_size là 3.

### 3.2. Vì sao OFFSET thường là lựa chọn kém?

Ví dụ:

~~~sql
SELECT id
FROM customer
ORDER BY id
LIMIT 1000 OFFSET 900000;
~~~

Khi OFFSET tăng, database có thể phải đi qua số lượng dòng lớn trước khi lấy batch cuối. Ngoài hiệu năng, INSERT/DELETE đồng thời có thể làm vị trí các dòng dịch chuyển, khiến một số dòng bị lặp hoặc bỏ sót. Keyset dựa trên mốc khóa ổn định thường hiệu quả và dễ lưu tiến độ hơn.

### 3.3. Nếu bảng không có ID tăng dần

Không nhất thiết mọi bảng đều có khóa BIGINT tuần tự:

- **UUID**: có thể dùng thứ tự theo UUID nếu phù hợp DBMS/chỉ mục, hoặc phân đoạn bằng khoảng/hash với thiết kế riêng.
- **Khóa tổng hợp**: dùng thứ tự từ nhiều cột và cursor kết hợp, ví dụ **(created_at, id)** để phá hòa.
- **Dữ liệu phân vùng**: chia theo partition/time window rồi dùng cursor trong từng phân vùng.
- **Không có khóa ổn định**: cần thiết kế cơ chế đánh dấu/claim công việc; không dựa vào thứ tự ngẫu nhiên.
- **Khoảng thời gian với bản ghi cùng timestamp**: không chỉ dùng created_at vì các dòng có cùng thời điểm có thể bị bỏ qua; cần khóa phụ ổn định.

Chọn khóa phải xét khả năng **bị sửa trong khi chạy**. Một cột có thể thay đổi liên tục không phù hợp làm cursor nếu thay đổi thứ tự gây bỏ sót.

## 4. High-water mark và dữ liệu ghi đồng thời

Giả sử ở thời điểm bắt đầu, ID lớn nhất là **8.000.000**. Backfill chọn **high_water_id = 8.000.000** để xử lý dữ liệu tồn tại trước hoặc trong thời điểm chụp mốc.

Sau đó ứng dụng tiếp tục INSERT thêm ID 8.000.001, 8.000.002... Nếu ứng dụng mới đã ghi search_name đúng ngay từ đầu, các bản ghi mới không cần backfill. Đó là một lý do quan trọng để triển khai **dual-write hoặc writer-compatible code** trước khi chạy job.

Nhưng high-water mark **không tự ngăn mọi dữ liệu thiếu**:

- Một transaction tạo bản ghi trước đó có thể commit muộn sau khi mốc được lấy.
- Một ứng dụng cũ có thể vẫn INSERT một bản ghi thiếu search_name.
- Một luồng UPDATE cũ có thể đổi full_name mà không cập nhật search_name.
- Với khóa không tăng tuần tự, dữ liệu mới có thể nằm trong khoảng khóa đã đi qua.

Vì vậy, thuật toán cần **bước quét lại và kiểm chứng cuối**, không chỉ tuyên bố hoàn thành khi cursor vượt qua high-water mark. Nếu dữ liệu có khả năng bị chỉnh sửa đồng thời, cần điều phối nguồn ghi hoặc thiết kế cách tính lại khi stale.

Quy tắc an toàn là:

> Backfill xử lý lịch sử; ứng dụng hoặc cơ chế đồng bộ mới phải duy trì tính đúng đắn sau khi backfill đi qua.

Nếu chưa thể kiểm soát các writer cũ, cần giữ giai đoạn chuyển tiếp lâu hơn hoặc áp dụng một cơ chế đồng bộ phù hợp; không vội thêm NOT NULL chỉ vì worker đã chạy hết vòng.

## 5. Ví dụ batch SQL theo khoảng khóa chính

Giả sử batch đã xác định khoảng **id > :last_id AND id <= :batch_end_id**. Một câu cập nhật có khả năng chạy lại:

~~~sql
UPDATE customer
SET search_name = LOWER(TRIM(full_name))
WHERE id > :last_id
  AND id <= :batch_end_id
  AND search_name IS NULL;
~~~

Predicate **search_name IS NULL** giúp tránh ghi đè những bản ghi đã được worker xử lý hoặc đã có giá trị do ứng dụng mới cung cấp. Nó là một hình thức **idempotency** hữu ích, nhưng chưa đủ cho mọi yêu cầu:

- Nếu công thức mới sửa lại dữ liệu không chính xác từ công thức cũ, chỉ cập nhật NULL sẽ không chỉnh những giá trị không NULL nhưng sai.
- Nếu full_name đổi sau khi search_name đã được tính, search_name có thể bị stale. Ứng dụng phải cập nhật nhất quán hoặc job phải có cơ chế kiểm tra khác.
- Nếu full_name không hợp lệ hoặc NULL, hàm xử lý có thể tạo NULL; cần quy tắc dữ liệu và kiểm tra riêng.
- Nếu nhiều worker cùng xử lý một hàng, các transaction có thể tranh chấp. Cần partition/claim rõ ràng thay vì mong WHERE tự giải quyết mọi race condition.

Với bài toán “điền các giá trị thiếu” thì điều kiện **IS NULL** phù hợp. Với bài toán “chuẩn hóa lại mọi giá trị”, cần định nghĩa tiêu chí khác, ví dụ so sánh giá trị hiện tại với giá trị mong đợi theo cú pháp của DBMS, và đánh giá việc ghi đồng thời.

### Lưu ý về thứ tự thao tác

Một batch cần commit **cả cập nhật dữ liệu lẫn tiến độ** hoặc có cơ chế phục hồi tương đương. Nếu checkpoint báo xong nhưng dữ liệu chưa commit, job có thể bỏ qua những dòng chưa xử lý. Nếu dữ liệu đã commit nhưng checkpoint chưa lưu, job có thể chạy lại batch; khi đó idempotency giúp giữ an toàn.

Mô hình lý tưởng khi checkpoint được lưu **trong cùng database**:

~~~text
BEGIN TRANSACTION
    đọc checkpoint hiện tại
    chọn batch_end_id
    UPDATE các dòng của batch
    UPDATE checkpoint.last_processed_id = batch_end_id
COMMIT
~~~

Mã trên là **thuật toán khái niệm**, không phải cú pháp SQL chuẩn để chạy nguyên văn. Việc khóa bản ghi checkpoint, chống hai worker cùng nhận một batch và xác định thời điểm commit phải được triển khai theo DBMS/transaction isolation thực tế.

## 6. Lưu checkpoint để tiếp tục sau khi lỗi

Một backfill có thể chạy hàng giờ hoặc nhiều ngày. Vì vậy, cần trạng thái bền vững, không chỉ giữ cursor trong RAM.

Ví dụ mô hình metadata cho job:

| Trường | Ví dụ | Ý nghĩa |
|---|---|---|
| **job_key** | customer-search-name-v1 | Nhận diện phiên bản logic backfill |
| **high_water_id** | 8000000 | Giới hạn quét chính ban đầu |
| **last_processed_id** | 1200456 | Ranh giới đã xử lý và commit |
| **batch_size** | 2000 | Giá trị cấu hình, có thể điều chỉnh |
| **rows_updated** | 1140120 | Số dòng thực sự được cập nhật |
| **status** | RUNNING / PAUSED / VERIFIED | Trạng thái vận hành, không thay thế kiểm chứng dữ liệu |
| **updated_at** | thời gian gần nhất | Nhận biết job kẹt hoặc không tiến triển |

Bảng checkpoint, nếu có, là một **đối tượng dữ liệu do hệ thống backfill quản lý**; nó không phải bảng **DATABASECHANGELOG** hay cơ chế tự động có sẵn cho mọi job Liquibase.

Các nguyên tắc:

1. **Checkpoint chỉ tiến lên sau khi batch commit thành công.**
2. **Cùng khóa job không được đồng thời chạy với hai logic backfill khác nhau.** Nếu đổi công thức hay điều kiện cập nhật, cần version logic/khóa job và đánh giá checkpoint cũ.
3. **Retry bắt đầu từ checkpoint đã commit**; phải xác định batch nào có thể được xử lý lại.
4. **Bỏ qua khóa không còn tồn tại**: keyset không nên yêu cầu ID phải liên tục.
5. **Không đánh dấu VERIFIED chỉ vì cursor tới high-water mark**; cần truy vấn điều kiện toàn bảng.
6. **Không xóa checkpoint để “chạy lại từ đầu” trong production** nếu chưa đánh giá tác động dữ liệu và tải.

Nếu tiến độ được lưu ngoài database (queue, file hoặc dịch vụ orchestration), phải phân tích khả năng mất đồng bộ giữa việc commit dữ liệu và ghi checkpoint. Khi không có transaction chung, thuật toán **at-least-once + idempotent update** thường đáng tin cậy hơn việc giả định exactly-once.

## 7. Thiết kế một worker backfill có thể chạy lại

Pseudo-code sau minh họa job **một worker** duyệt bảng customer bằng ID. Đây không phải script triển khai cụ thể hay API Liquibase.

~~~text
config:
    job_key = "customer-search-name-v1"
    initial_batch_size = 2000
    pause_between_batches = adaptive

startup:
    ensure all application writers maintain search_name
    load or initialize durable checkpoint
    if first run:
        checkpoint.high_water_id = SELECT MAX(id) FROM customer
        checkpoint.last_processed_id = lower_bound
    retain same high_water_id on resume

loop:
    begin transaction
    lock checkpoint row for this job
    read last_processed_id and high_water_id

    ids = SELECT id FROM customer
          WHERE id > last_processed_id AND id <= high_water_id
          ORDER BY id
          LIMIT batch_size

    if ids is empty:
        commit
        break

    batch_end_id = maximum id from ids

    UPDATE customer
    SET search_name = normalized(full_name)
    WHERE id > last_processed_id
      AND id <= batch_end_id
      AND search_name IS NULL

    save checkpoint.last_processed_id = batch_end_id
    save rows_updated based on actual affected rows
    commit transaction

    observe latency, locks, CPU/I/O and replica lag
    pause or adjust batch_size when required

verification:
    verify no missing or incorrect search_name remains
    reconcile late commits and concurrent writers
    if needed, run a targeted cleanup/sweep then reverify
    only after successful verification mark job VERIFIED
~~~

Với SQL thực tế, **normalized(full_name)** phải được thay bằng biểu thức hợp lệ, chẳng hạn **LOWER(TRIM(full_name))** trên DBMS hỗ trợ.

### Vì sao khóa checkpoint?

Giả sử hai worker đọc **last_processed_id = 1000** cùng lúc. Nếu không có cơ chế claim/lock, cả hai có thể chọn cùng khoảng 1001–3000, gây công việc trùng lặp, tranh chấp khóa và tiến độ khó giải thích. Khóa hàng checkpoint trong transaction hoặc cơ chế phân vùng công việc rõ ràng sẽ tránh tình huống này.

Chạy nhiều worker chỉ nên thực hiện khi đã có thiết kế phân công batch. Có thể dùng các cơ chế DBMS như **FOR UPDATE SKIP LOCKED** trên nền tảng hỗ trợ, hoặc hàng đợi claim ID. Nhưng nếu cursor tăng vượt qua các dòng bị SKIP LOCKED bỏ qua thì job **có nguy cơ không quay lại xử lý chúng**; cần lưu từng claim/chunk, retry batch chưa hoàn tất và quét lại toàn bảng. Không nên trộn **SKIP LOCKED** với một cursor đơn giản rồi giả định không có hàng nào bị bỏ sót.

## 8. Chọn batch size và tốc độ chạy

Không có batch size cố định phù hợp mọi bảng. **1.000 hoặc 2.000 hàng** chỉ là giá trị thử nghiệm ban đầu, không phải khuyến nghị chuẩn cho mọi môi trường. Batch phù hợp còn tùy:

- Mỗi hàng có bao nhiêu cột và kích thước dữ liệu phải ghi.
- Có bao nhiêu chỉ mục, foreign key, trigger hoặc cơ chế replication liên quan.
- Tỷ lệ hàng thực sự cần thay đổi trong khoảng khóa được quét.
- Transaction isolation và khả năng giữ lock của DBMS.
- Tốc độ I/O, CPU, network và tải ứng dụng cùng lúc.
- Độ trễ replica, dung lượng WAL/redo log và khả năng rollback transaction.
- SLO/SLI của ứng dụng, thời gian maintenance window nếu có.

Một cách thử nghiệm thực tế:

1. Bắt đầu với batch nhỏ trên **database đại diện** có dữ liệu và chỉ mục gần production.
2. Đo thời gian transaction, số hàng cập nhật, lock wait, log growth và replication lag.
3. Tăng dần batch size nếu ứng dụng vẫn ổn định và transaction ngắn.
4. Giảm batch size, thêm pause hoặc tạm dừng job nếu có cảnh báo.
5. Ghi lại cấu hình và kết quả để biết vì sao batch size được chọn.

Ví dụ bảng theo dõi giả định:

| Batch | Hàng được quét | Hàng cập nhật | Thời gian transaction | Quyết định |
|---|---:|---:|---:|---|
| 1 | 1.000 | 980 | 180 ms | Tiếp tục |
| 2 | 2.000 | 1.950 | 420 ms | Có thể thử tiếp |
| 3 | 5.000 | 4.960 | 3.200 ms | Giảm kích thước |
| 4 | 2.000 | 1.940 | 450 ms | Giữ mức này nếu ổn định |

**Các số trên chỉ minh họa cách ra quyết định, không phải benchmark hoặc cam kết hiệu năng.**

Nếu dữ liệu có phân bố không đều, batch giới hạn theo **số dòng** vẫn có thể tạo chi phí rất khác nhau. Nên theo dõi cả **thời gian xử lý** và **số byte/log thực tế**, không chỉ batch_size.

## 9. Liquibase nên làm gì trong chuỗi backfill lớn?

Liquibase giỏi quản lý **các thay đổi có trạng thái triển khai rõ ràng**: thêm cột, index, constraint, bước SQL có phạm vi hữu hạn, precondition và lịch sử changeset. Tuy nhiên, một vòng lặp backfill hàng triệu dòng cần điều chỉnh tốc độ, checkpoint và pause/resume thường phù hợp với **job chuyên trách** hơn.

Có ba cách triển khai phổ biến:

| Phương án | Nên dùng khi | Hạn chế |
|---|---|---|
| **Một changeset chứa UPDATE toàn bảng** | Bảng nhỏ, chạy nhanh và đã được đo an toàn | Transaction lớn nếu quy mô tăng; khó checkpoint theo lô |
| **Nhiều changeset với khoảng dữ liệu tĩnh** | Một số lô hữu hạn, ranh giới cố định, cần lịch sử riêng | Changelog phình to; thiếu cơ chế điều tiết tự động; khoảng dữ liệu cần được quản lý |
| **Liquibase quản lý schema, job bên ngoài xử lý batch** | Bảng rất lớn, cần throttle, retry/checkpoint và giám sát lâu dài | Phải điều phối job với bước contract, lưu bằng chứng hoàn tất và xử lý lỗi job |

**Đừng đặt hàng nghìn UPDATE trong cùng một changeset rồi cho rằng Liquibase sẽ commit sau mỗi câu.** Liquibase thường chạy một changeset trong một transaction khi DBMS cho phép và thuộc tính **runInTransaction** ở mặc định **true**. Nếu muốn có commit riêng cho từng batch, cần tạo ranh giới transaction thực sự; chỉ chia thành nhiều câu SQL bên trong một changeset không tự tạo ranh giới này.

Cũng không nên dùng **runAlways** hoặc **runOnChange** như một vòng lặp job để “chạy batch tiếp theo” sau mỗi lần update. Những thuộc tính này điều khiển hành vi changeset được thực thi lại và checksum, không cung cấp sẵn checkpoint an toàn cho dữ liệu lớn.

### 9.1. Ví dụ các lô tĩnh trong changeset

Nếu bài toán nhỏ và biết rõ khoảng ID, có thể chọn một số changeset độc lập, mỗi changeset cập nhật một khoảng:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-101-search-name-range-1"
      author: "platform"
      changes:
        - sql:
            sql: |
              UPDATE customer
              SET search_name = LOWER(TRIM(full_name))
              WHERE id >= 1 AND id < 1001
                AND search_name IS NULL;

  - changeSet:
      id: "20261119-102-search-name-range-2"
      author: "platform"
      changes:
        - sql:
            sql: |
              UPDATE customer
              SET search_name = LOWER(TRIM(full_name))
              WHERE id >= 1001 AND id < 2001
                AND search_name IS NULL;
~~~

Ví dụ SQL này phụ thuộc khả năng hàm chuỗi và cú pháp của **DBMS đích**; cần kiểm tra trên đúng runtime. Các khoảng chỉ là minh họa, không bao phủ toàn bộ bảng nếu ID nằm ngoài 1–2000.

Hai changeset có định danh và lịch sử khác nhau, nên trên DBMS hỗ trợ transaction như dự kiến, lỗi ở changeset thứ hai không tự xóa lịch sử thành công của changeset thứ nhất. Tuy nhiên, nếu tất cả changeset được phép chạy trong **một lệnh update**, Liquibase sẽ tiếp tục xét chúng theo thứ tự mà không tự nghỉ giữa hai batch hay tự giảm tải. Với hàng triệu ID, cách tạo thay đổi tĩnh theo từng khoảng thường khó quản lý hơn job batch có checkpoint.

Các thay đổi kiểu này cần giữ nguyên sau triển khai: chỉnh sửa khoảng WHERE trong changeset đã chạy có thể gây lỗi **checksum**.

## 10. Kịch bản đầy đủ: expand → duy trì dữ liệu mới → backfill → contract

Giả sử bảng **customer** có **id** và **full_name** đã được điền hợp lệ. Hệ thống muốn bổ sung **search_name** để phục vụ tìm kiếm, và sau khi chuyển đổi xong, search_name trở thành bắt buộc.

### Bước A — Expand schema bằng Liquibase

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-001-customer-search-name-expand"
      author: "platform"
      changes:
        - addColumn:
            tableName: customer
            columns:
              - column:
                  name: search_name
                  type: VARCHAR(200)
~~~

Cột mới để nullable, giúp ứng dụng cũ tiếp tục hoạt động trong giai đoạn chuyển tiếp. Đừng thêm NOT NULL ngay khi bảng có hàng cũ chưa được backfill.

### Bước B — Phát hành writer tương thích

Ứng dụng mới tính search_name khi tạo hoặc đổi full_name. Nếu nhóm chọn dual-write, cần bảo đảm nó được thực hiện trong cùng logic ghi dữ liệu có tính nhất quán phù hợp. Trong rolling deployment, ứng dụng cũ có thể vẫn ghi dữ liệu thiếu; cần kế hoạch xử lý giai đoạn giao thoa, không chỉ bật backfill rồi xem như đã xong.

### Bước C — Chạy job theo lô

Job dùng khóa chính, high-water mark và checkpoint như mục 3–7. Chỉ cập nhật các dòng thiếu hoặc sai theo tiêu chí đã xác nhận. Theo dõi tổng số hàng còn thiếu, retry batch thất bại và giới hạn tải theo điều kiện thực tế.

Nếu job chạy ngoài Liquibase, đừng ghi nhận một changeset “backfill hoàn thành” chỉ vì job đã được **khởi động**. Cần phân biệt **job scheduled**, **job running**, **job finished without error** và **data verified**. Chỉ trạng thái cuối cùng kèm bằng chứng dữ liệu mới đủ để mở bước contract.

### Bước D — Kiểm chứng dữ liệu trước ràng buộc

Kiểm tra tối thiểu:

~~~sql
SELECT COUNT(*) AS missing_search_name
FROM customer
WHERE search_name IS NULL;
~~~

Nếu search_name phải trùng với hàm chuẩn hóa của full_name, trên **PostgreSQL** có thể kiểm tra thêm:

~~~sql
SELECT COUNT(*) AS mismatched_search_name
FROM customer
WHERE search_name IS DISTINCT FROM LOWER(BTRIM(full_name));
~~~

**IS DISTINCT FROM** là phép so sánh có xử lý NULL trên PostgreSQL; nếu dùng DBMS khác, phải chọn cú pháp tương đương phù hợp. Truy vấn kiểm tra trên bảng lớn có thể tốn thời gian/quét dữ liệu; hãy đo và thực hiện ở thời điểm phù hợp. Nếu còn mismatch, cần xác định nguyên nhân: dữ liệu bất thường, race với writer, lỗi công thức, hoặc batch bị bỏ sót.

Một sự khác biệt có thể có chủ đích theo nghiệp vụ. Nếu search_name sử dụng một thuật toán chuẩn hóa phức tạp, truy vấn kiểm chứng phải dùng **cùng quy tắc đã thống nhất**, không áp một biểu thức đơn giản rồi đánh dấu dữ liệu đúng/sai sai cách.

### Bước E — Contract bằng Liquibase, chỉ khi dữ liệu sẵn sàng

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-002-customer-search-name-not-null"
      author: "platform"
      preConditions:
        - onFail: HALT
        - sqlCheck:
            expectedResult: "0"
            sql: SELECT COUNT(*) FROM customer WHERE search_name IS NULL
      changes:
        - addNotNullConstraint:
            tableName: customer
            columnName: search_name
            columnDataType: VARCHAR(200)
      rollback:
        - dropNotNullConstraint:
            tableName: customer
            columnName: search_name
            columnDataType: VARCHAR(200)
~~~

Precondition giúp Liquibase **dừng** nếu còn hàng NULL, tránh tự ghi nhận thay đổi thành công trong khi dữ liệu chưa đáp ứng. Tuy vậy:

- **COUNT(*) có thể tốn tài nguyên** trên bảng lớn; phải dự kiến thời gian và tải khi chạy.
- Precondition không khóa vĩnh viễn các writer. Một writer cũ vẫn có thể ghi NULL sau khi check nhưng trước ALTER; cần điều phối ứng dụng và xem xét race condition.
- NOT NULL chỉ bảo đảm không NULL, **không bảo đảm** search_name chính xác với full_name. Nếu cần điều đó, cần cơ chế duy trì và kiểm chứng riêng.
- Rollback gỡ NOT NULL **không đảo backfill**, cũng không khôi phục nguyên trạng các dòng cũ.

### Bước F — Dọn giai đoạn chuyển tiếp

Khi schema và ứng dụng ổn định, có thể bỏ logic tương thích cũ, các cột dự phòng hoặc job không còn cần thiết theo kế hoạch release riêng. Đừng gộp bước phá vỡ tương thích với expand ban đầu.

## 11. Vì sao cần idempotency khi retry?

Trong vận hành, một batch có thể thất bại hoặc không rõ kết quả từ phía worker:

- Database đã commit nhưng kết nối bị mất trước khi client nhận phản hồi.
- Worker chết sau khi commit, trước khi lưu tiến độ ở một dịch vụ ngoài.
- Tiến trình được khởi động lại bởi orchestrator.
- Operator chủ động cho chạy lại một khoảng ID để sửa lỗi.

Nếu update có dạng:

~~~sql
UPDATE customer
SET backfill_counter = backfill_counter + 1
WHERE id BETWEEN :start_id AND :end_id;
~~~

thì retry sẽ **tăng hai lần**: không idempotent. Ngược lại, nếu mục tiêu là đặt một giá trị xác định:

~~~sql
UPDATE customer
SET search_name = LOWER(TRIM(full_name))
WHERE id BETWEEN :start_id AND :end_id
  AND search_name IS NULL;
~~~

thì retry trên hàng đã được điền sẽ không cập nhật lại. Tuy nhiên, nếu công thức chuẩn hóa cần sửa các giá trị cũ bị sai, điều kiện IS NULL sẽ không đủ; phải thiết kế phiên bản mới của công thức và migration bù.

Một checklist idempotency hữu ích:

- Dữ liệu đầu vào để tính kết quả có ổn định trong khoảng xử lý không?
- Nếu chạy cùng batch hai lần, kết quả cuối có giống lần đầu không?
- Có side effect ngoài database như gửi email, thanh toán hay xuất sự kiện không?
- Nếu một batch chỉ commit một phần (do cách tổ chức transaction), có xác định được phần cần retry không?
- Có trường hợp NULL hợp lệ hoặc giá trị đã được người dùng sửa mà job không được ghi đè không?

**Không phải mọi backfill đều nên cập nhật mọi hàng mỗi lần chạy.** Nguyên tắc là xác định những hàng thực sự cần sửa và một phép biến đổi có thể đối chiếu, chứ không mặc định “chạy lại càng nhiều càng tốt”.

## 12. Giới hạn transaction, khóa và tính sẵn sàng

Liquibase mặc định cố gắng chạy từng changeset trong transaction khi DBMS hỗ trợ, nhưng khả năng transaction đối với DDL không giống nhau giữa các hệ quản trị. Với **job batch DML**, ranh giới commit rõ ràng thường là thành phần thiết kế chính.

### Transaction ngắn

Một batch ngắn giúp giảm thời gian giữ row lock và tạo điểm phục hồi. Nhưng batch quá nhỏ có thể tăng overhead do nhiều commit, kết nối, round-trip và cập nhật checkpoint. Cần chọn mức cân bằng dựa trên đo đạc, không dựa vào một con số cố định.

### Tránh khóa chéo không cần thiết

Nếu có nhiều worker, nên chia phạm vi ID không chồng lấn. Những transaction chạm cùng bản ghi theo thứ tự khác nhau có thể gây deadlock. Khi xảy ra deadlock hoặc timeout, nên retry batch theo chính sách có giới hạn, ghi lại nguyên nhân và không âm thầm lặp vô hạn.

### Throttling

Có thể giảm batch size, thêm khoảng nghỉ giữa batch, giới hạn số worker hoặc pause hoàn toàn khi:

- p95/p99 latency của ứng dụng tăng mạnh;
- CPU, I/O hoặc lock wait vượt ngưỡng vận hành;
- WAL/redo log hoặc disk tăng quá nhanh;
- độ trễ replica tăng;
- có maintenance, backup hoặc migration khác sắp chạy.

Các ngưỡng cần dựa trên quan sát hệ thống thực tế. Một job báo **100% CPU sử dụng được** không có nghĩa là backfill an toàn cho dịch vụ đang chịu tải.

### Index và phạm vi quét

Keyset theo **primary key có index** thường hiệu quả hơn quét với OFFSET lớn. Nhưng một predicate như **search_name IS NULL** có thể chưa có index phù hợp; tạo index riêng để phục vụ backfill cũng có chi phí build, disk và maintenance. Đánh giá execution plan trước khi thêm index tạm. Không tạo index lớn chỉ vì muốn tăng tốc một job ngắn mà chưa so sánh tổng chi phí.

## 13. Theo dõi tiến độ: số dòng đã duyệt không phải số dòng đã sửa

Một batch 2.000 ID có thể chỉ cập nhật 300 dòng vì 1.700 dòng đã có search_name. Vì vậy cần phân biệt:

| Chỉ số | Ý nghĩa |
|---|---|
| **rows_scanned** | Số dòng/khóa trong phạm vi batch đã được xét |
| **rows_updated** | Số dòng thực sự bị thay đổi trong batch |
| **last_processed_id** | Mốc khóa đã xử lý và commit |
| **high_water_id** | Mốc cuối của vòng quét ban đầu |
| **remaining_missing** | Số dòng còn thiếu giá trị theo điều kiện nghiệp vụ |
| **remaining_invalid** | Số dòng có giá trị sai/không nhất quán, không nhất thiết NULL |
| **batch_latency** | Thời gian chạy và commit một batch |
| **retry_count** | Số lần phải thử lại |
| **replica_lag / lock_wait** | Tín hiệu tác động lên database và ứng dụng |

Không được tính phần trăm tiến độ bằng **last_processed_id / MAX(id)** nếu ID có nhiều khoảng trống hoặc phân bố không đều rồi diễn giải là chính xác số dòng đã xử lý. Có thể dùng để ước tính vị trí cursor, nhưng kết luận hoàn thành cần dựa trên điều kiện dữ liệu.

Ví dụ SQL kiểm tra phần còn thiếu:

~~~sql
SELECT COUNT(*) AS remaining
FROM customer
WHERE search_name IS NULL;
~~~

Khi báo cáo “đã xong”, cần đi kèm bằng chứng **remaining = 0** hoặc bằng chứng tương ứng với tiêu chí nghiệp vụ. Với dữ liệu được ghi liên tục, kết quả đo tại một thời điểm chưa thay thế cơ chế ngăn xuất hiện bản ghi sai về sau.

## 14. Lỗi thường gặp và cách phục hồi

| Tình huống | Nguyên nhân điển hình | Hướng xử lý |
|---|---|---|
| Backfill chạy rất lâu, ứng dụng chậm | Batch quá lớn, lock/IO/log pressure | Giảm batch size/concurrency, pause và đo lại |
| Tiến độ đạt high-water nhưng vẫn còn NULL | Writer cũ, commit muộn, khóa bị bỏ sót | Chạy sweep có kiểm chứng, sửa writer, không contract vội |
| Worker chết giữa batch | Process hoặc kết nối lỗi | Retry từ checkpoint đã commit và bảo đảm idempotency |
| DB đã commit nhưng checkpoint chưa ghi ngoài DB | Hai hệ thống không có transaction chung | Retry an toàn, tránh giả định exactly-once |
| Một số dòng bị xử lý hai lần | Hai worker claim trùng nhau hoặc retry | Thiết kế claim/partition, đảm bảo update idempotent |
| Dữ liệu không NULL nhưng sai công thức | Update chỉ lọc IS NULL | Thiết kế kiểm tra mismatch và migration sửa chữa riêng |
| UPDATE theo OFFSET bỏ sót dòng | Dữ liệu thay đổi khi phân trang | Chuyển sang keyset/checkpoint và quét lại |
| CI/CD chạy bước NOT NULL trước job | Không có điểm dừng/điều kiện hoàn thành | Tách release, precondition HALT, gate bằng bằng chứng dữ liệu |
| Đã backfill nhưng rollback không về dữ liệu cũ | Dữ liệu được biến đổi, thiếu snapshot | Ưu tiên roll-forward sửa lỗi hoặc phục hồi từ nguồn tin cậy |
| Sửa changeset cũ để tăng phạm vi ID | Checksum/history thay đổi | Giữ nguyên changeset đã chạy, thêm bước migration mới |
| Mỗi batch là một SQL trong một changeset lớn | Vẫn là transaction dài khi DBMS hỗ trợ | Tạo transaction boundary thực hoặc chuyển sang job batch |
| Thiếu chỉ mục phù hợp | Range lookup/full scan tốn chi phí | Kiểm tra execution plan và đánh giá index có lợi ròng |

Điều cần tránh là **tự đánh dấu job thành công vì pipeline không báo lỗi**, trong khi một số dòng không được xử lý hoặc dữ liệu bị cập nhật sai. Kết quả backfill phải có bước xác minh độc lập.

## 15. Kiểm chứng với Liquibase và pipeline triển khai

Đối với những phần do Liquibase quản lý, các lệnh thường gặp:

~~~bash
liquibase --version
liquibase validate
liquibase status --verbose
liquibase update-sql
~~~

**validate** kiểm tra changelog theo khả năng của engine; **status --verbose** giúp xem changeset chưa chạy; **update-sql** trình bày SQL dự kiến thực thi. Các lệnh cần dùng đúng changelog, URL và thông số môi trường. Thành công của validate hoặc update-sql **không chứng minh** dữ liệu lớn sẽ được cập nhật nhanh hay job bên ngoài đã hoàn tất.

Sau khi kiểm tra, pipeline có thể triển khai:

~~~text
Release A:
    liquibase update  # expand schema
    deploy application that maintains new values

Backfill phase:
    start/resume batch worker
    monitor progress and database load
    verify all required rows and invariants

Release B:
    require verified backfill evidence
    liquibase update  # contract changesets
    verify schema and application behavior
~~~

Đây là **sơ đồ orchestration**, không phải script copy-paste. Hai lần update phải được phân tách bằng cấu hình artifact, release hoặc bộ lọc có chủ đích. Nếu cả expand lẫn contract cùng đủ điều kiện trong một lần update, Liquibase có thể chạy chúng liên tiếp. Cần thử chính xác bộ lọc context/label và lịch sử changeset mà pipeline sử dụng; thiếu filter trong một số trường hợp có thể làm phạm vi rộng hơn dự kiến.

Với Spring Boot, Liquibase có thể chạy khi ứng dụng khởi động. Một changeset quá lớn làm app startup kéo dài hoặc thất bại khi database chịu tải; cần cân nhắc **migration job chuyên trách** hoặc cơ chế phối hợp release rõ ràng. Liquibase có cơ chế lock cho quá trình migration, nhưng không tự điều chỉnh tải một backfill dài và không thay thế ứng dụng duy trì dữ liệu đúng.

## 16. Tính đúng đắn và khả năng rollback

Backfill thường là thao tác **biến đổi dữ liệu**, có thể không có phép đảo ngược an toàn. Ví dụ tính search_name từ full_name có thể được tính lại nếu nguồn full_name còn nguyên. Nhưng nếu migration thay thế hoặc xóa thông tin cũ, chỉ rollback schema sẽ không đưa dữ liệu về trạng thái ban đầu.

Ba câu hỏi cần tách riêng:

1. **Rollback schema**: bỏ NOT NULL hoặc cột mới có thể thực hiện được không, và có làm mất dữ liệu đã phát sinh không?
2. **Rollback dữ liệu**: có thể khôi phục chính xác giá trị cũ không, có snapshot hoặc nguồn đối chiếu không?
3. **Rollback ứng dụng**: phiên bản cũ có hiểu dữ liệu được phiên bản mới viết không?

Nếu không thể đảo một cách an toàn, **roll-forward** bằng migration sửa chữa mới có thể là chiến lược phù hợp hơn. Mọi phương án cần được kiểm thử trên dữ liệu đại diện trước khi phát hành.

Trong các hệ thống cần audit, có thể ghi nhận số dòng theo batch, phạm vi ID, thời gian xử lý, công thức chuyển đổi và version job. Không lưu dữ liệu nhạy cảm không cần thiết vào log.

Bản thân Liquibase ghi lịch sử changeset trong DATABASECHANGELOG, nhưng **không tự lưu số dòng hoàn tất và checkpoint của một worker bên ngoài**. Cần quản lý lịch sử job riêng và gắn nó với commit/release để có thể truy nguyên.

## 17. Bài thực hành: mô phỏng một lần backfill an toàn

**Bài toán:** Một database có bảng customer khoảng vài triệu dòng, full_name đã có; cột search_name vừa được thêm và phần lớn hàng đang NULL. Yêu cầu là mọi customer có search_name phù hợp, sau đó cột có NOT NULL.

### Bước 1 — Ước lượng khối lượng và rủi ro

- Đếm số hàng tổng và số hàng có search_name NULL.
- Kiểm tra primary key, kiểu dữ liệu, execution plan của truy vấn theo ID.
- Xác định các luồng ghi mới, bảng có trigger/index nào ảnh hưởng.
- Chọn batch size ban đầu dựa trên thử nghiệm, không dựa vào số dòng lý thuyết.

### Bước 2 — Viết thay đổi schema expand

Dùng **addColumn** tạo search_name nullable, ghi changeset ID ổn định và test cả đường nâng cấp từ database có dữ liệu. Không sửa lại changeset đã phát hành khi chuyển sang bước contract.

### Bước 3 — Tạo worker có checkpoint

- Lưu high-water mark và cursor bền vững.
- Chọn khóa theo **id > last_id**, ORDER BY id, LIMIT N.
- Chỉ UPDATE những dòng thực sự cần bổ sung.
- Commit dữ liệu và checkpoint nhất quán.
- Cấu hình retry, pause và giám sát transaction latency.

### Bước 4 — Thử lỗi có chủ đích

- Giết worker giữa batch và xác nhận khi khởi động lại không bị mất/hỏng dữ liệu.
- Mô phỏng kết nối bị ngắt ngay sau commit, kiểm tra retry idempotent.
- Chạy ứng dụng ghi dữ liệu đồng thời, kiểm tra có hàng mới thiếu hoặc stale không.
- Nếu thử nhiều worker, xác nhận không claim trùng hoặc bỏ qua hàng đang bị khóa.

### Bước 5 — Kiểm chứng cuối

- Đếm hàng còn NULL.
- Đối chiếu công thức với dữ liệu thật, kiểm tra cả các dòng không NULL nhưng sai.
- Kiểm tra checkpoint và metadata job: đã quét đến mốc, số batch, lỗi chưa giải quyết.
- Chạy quét bù nếu cần và lặp lại kiểm chứng.

### Bước 6 — Contract schema

Chỉ khi đã đủ bằng chứng và các writer đã tương thích, chạy **addNotNullConstraint** với precondition. Xác nhận schema sau update và thử INSERT/UPDATE vi phạm trên database thử nghiệm để biết ràng buộc có hiệu lực.

### Bước 7 — Phục hồi

Thử rollback phần schema trên database thử nghiệm; giải thích vì sao rollback không tự khôi phục dữ liệu cũ. Nếu job dùng một công thức sai, đề xuất changeset/job sửa chữa version mới, không sửa lịch sử changeset đã triển khai.

## 18. Checklist review trước khi chạy bảng lớn

Trước khi merge hoặc bật một job backfill, reviewer nên trả lời được:

- Đã biết số dòng, kích thước bảng, tỷ lệ hàng cần cập nhật và rủi ro locking?
- Đã xác định nguồn dữ liệu, công thức chuyển đổi và các trường hợp dữ liệu bất thường?
- Đã có cơ chế duy trì giá trị mới cho các INSERT/UPDATE đồng thời?
- Đã chọn khóa/cursor ổn định, có index phù hợp và tránh OFFSET lớn?
- Đã thiết kế high-water mark và bước quét bù cho bản ghi đến muộn?
- Batch có transaction riêng, commit và checkpoint nhất quán?
- Retry có idempotent, không tăng counter hoặc phát side effect trùng?
- Nếu nhiều worker, đã có cơ chế claim không trùng và không bỏ sót?
- Đã đo batch size, transaction time, lock wait, WAL/log, replica lag và có throttle?
- Đã phân biệt lịch sử Liquibase changeset với checkpoint của job xử lý dữ liệu?
- Đã có bước kiểm chứng độc lập về **remaining_missing** và **remaining_invalid**?
- Pipeline có điểm dừng thật giữa expand, backfill và contract?
- Contract có precondition **HALT** khi dữ liệu chưa sẵn sàng?
- Đã thử trên database có lịch sử và dữ liệu đại diện, không chỉ database trống?
- Rollback/roll-forward đã được thiết kế cho schema, dữ liệu và phiên bản ứng dụng?
- Đã giữ nguyên những changeset đã chạy và không dùng chỉnh sửa checksum để che lỗi?

**Kết luận:** Với bảng lớn, nhiệm vụ bổ sung dữ liệu phải được xem là một **quy trình dài có trạng thái**, không chỉ là một câu UPDATE trong changelog. Chia lô bằng khóa ổn định, transaction ngắn, checkpoint bền vững, retry idempotent, giảm tải theo quan sát và kiểm chứng dữ liệu cuối là những yếu tố cốt lõi. Liquibase nên quản lý các mốc schema, điều kiện contract và lịch sử changeset; job batch đảm nhận khối lượng dữ liệu lớn khi cần. Sự phối hợp đó giúp migration có thể tiếp tục sau lỗi, giảm tác động lên hệ thống đang chạy và duy trì khả năng triển khai an toàn qua Spring Boot, CI/CD và nhiều môi trường.


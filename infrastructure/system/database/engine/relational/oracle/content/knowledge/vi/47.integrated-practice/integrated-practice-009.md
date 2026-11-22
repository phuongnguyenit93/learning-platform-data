# Triển khai thay đổi schema tương thích nhiều phiên bản ứng dụng

Trong một hệ thống Oracle Database, ứng dụng và schema thường được phát hành ở những thời điểm khác nhau. Khi triển khai rolling, blue-green hoặc nhiều replica, có thể tồn tại đồng thời phiên bản ứng dụng cũ và mới cùng truy cập một database. Một thay đổi schema chỉ an toàn nếu mọi phiên bản ứng dụng đang chạy trong cửa sổ triển khai đều hiểu được cấu trúc dữ liệu tại thời điểm đó.

Ví dụ, ứng dụng R10 đang đọc cột CUSTOMER_PHONE. Release R11 muốn chuyển sang CUSTOMER_PHONE_E164 để lưu số điện thoại chuẩn hóa. Nếu migration đổi tên hoặc xóa cột cũ trước khi mọi instance R10 dừng, instance cũ sẽ lỗi ngay khi chạy câu SQL tham chiếu cột đã mất. Nếu deploy app mới trước khi cột mới tồn tại, app mới cũng lỗi. Cần chia thay đổi thành nhiều bước để schema và code tương thích trong suốt quá trình chuyển tiếp.

Chiến lược thường dùng là **expand → migrate → contract**:

1. **Expand**: thêm cấu trúc mới theo cách tương thích ngược; app cũ vẫn chạy.
2. **Migrate**: triển khai code có thể làm việc với cấu trúc cũ và mới, backfill dữ liệu, chuyển dần traffic và xác minh.
3. **Contract**: chỉ loại bỏ cấu trúc cũ sau khi mọi consumer đã chuyển và rollback window đã đóng.

Với Oracle, thiết kế này đặc biệt quan trọng vì phần lớn DDL có implicit commit. Không thể bọc một chuỗi ALTER TABLE/CREATE INDEX trong @Transactional rồi kỳ vọng rollback toàn bộ schema khi có lỗi. Rollback ứng dụng, rollback schema và phục hồi database là ba thao tác khác nhau, cần kế hoạch riêng.

## 1. Vì sao cần tương thích nhiều phiên bản?

Một ứng dụng production hiếm khi dừng toàn bộ trong một thời điểm để thay cả binary lẫn schema. Những mô hình triển khai phổ biến đều tạo ra khoảng thời gian mà nhiều phiên bản cùng tồn tại.

### 1.1. Rolling deployment

Khi triển khai nhiều replica:
- Một số instance vẫn chạy version N.
- Instance mới lần lượt được đưa lên version N+1.
- Load balancer chuyển traffic từng phần.
- Trong một khoảng thời gian, N và N+1 cùng truy cập một schema.

Nếu schema chỉ tương thích với N+1, các instance N còn lại có thể lỗi.

### 1.2. Blue-green deployment

Môi trường blue chạy phiên bản hiện tại, green chạy phiên bản mới. Hai môi trường có thể dùng chung database trong lúc kiểm tra hoặc chuyển traffic. Khi đó schema phải tương thích với cả hai app version, trừ khi có database riêng và cơ chế đồng bộ dữ liệu được thiết kế đầy đủ.

Chỉ đổi traffic sang green không giải quyết được vấn đề nếu green đã ghi dữ liệu theo format mà blue không đọc được. Rollback traffic khi ấy có thể khiến app cũ lỗi hoặc diễn giải sai dữ liệu.

### 1.3. Nhiều consumer dùng chung database

Một schema có thể được truy cập bởi:
- API service.
- Batch job.
- Reporting service.
- ETL pipeline.
- Stored procedure/package.
- Scheduler job.
- Consumer khác đọc trực tiếp table hoặc view.

Không chỉ kiểm tra phiên bản web/API chính. Một job chạy mỗi đêm có thể vẫn dùng cột cũ sau khi app mới đã deploy thành công.

### 1.4. Compatibility window

Compatibility window là khoảng thời gian mà schema phải hỗ trợ nhiều phiên bản consumer. Trước khi bắt đầu, xác định:
- Phiên bản app cũ nhất còn được phép chạy.
- Phiên bản app mới nhất sẽ được triển khai.
- Job/consumer nào có lịch chạy trễ.
- Thời gian rollback window.
- Khi nào được phép xóa cấu trúc cũ.
- Ai xác nhận không còn consumer dùng cấu trúc cũ.

Không thực hiện contract chỉ vì deployment pipeline báo tất cả pod mới đã healthy. Có thể vẫn còn worker, scheduled job hoặc consumer ngoài cluster.

## 2. Các nguyên tắc thiết kế

### 2.1. Thay đổi additive trước

Các thay đổi thường tương thích ngược hơn:
- Thêm nullable column.
- Thêm table mới.
- Thêm index không làm thay đổi semantics.
- Thêm view/API mới.
- Thêm giá trị trạng thái mà app cũ có thể bỏ qua an toàn.
- Thêm constraint sau khi dữ liệu đã được chuẩn hóa.

Các thay đổi rủi ro cao:
- DROP hoặc RENAME column/table.
- Đổi datatype theo cách không bảo toàn dữ liệu.
- Thêm NOT NULL khi app cũ chưa gửi giá trị.
- Đổi ý nghĩa của một column đang được nhiều consumer dùng.
- Thay đổi enum/status khiến code cũ rơi vào nhánh xử lý sai.
- Xóa giá trị hoặc format mà app cũ vẫn cần đọc.

Additive không tự động đồng nghĩa an toàn. Thêm một column NOT NULL không có default phù hợp có thể làm INSERT của app cũ thất bại. Thêm constraint có thể làm DML cũ vi phạm.

### 2.2. Giữ contract dữ liệu ổn định trong cửa sổ chuyển tiếp

Trong compatibility window:
- Cột cũ vẫn tồn tại.
- Cột mới có thể được thêm.
- Code mới phải xử lý dữ liệu cũ chưa backfill.
- Code cũ phải tiếp tục đọc/ghi được theo contract cũ.
- Các consumer mới không được giả định backfill đã hoàn tất trước khi có bằng chứng.
- Mọi chuyển đổi phải xác định rõ nguồn dữ liệu có thẩm quyền.

### 2.3. Tách schema migration và data migration

Schema migration thay đổi cấu trúc: column, table, index, constraint, view, package.

Data migration thay đổi nội dung: backfill, normalize, copy, split/merge giá trị, chuyển đổi format.

Hai loại có rủi ro và thời gian chạy khác nhau. Thêm một column thường nhanh; backfill hàng trăm triệu row có thể kéo dài hàng giờ. Không gộp cả hai thành một migration lớn nếu cần quan sát, retry hoặc rollback riêng.

### 2.4. Migration phải có thể tiếp tục an toàn

Một migration dài nên có:
- Batch/chunk boundary.
- Checkpoint hoặc progress marker.
- Điều kiện idempotent.
- Số dòng dự kiến và số dòng đã xử lý.
- Cơ chế retry.
- Cách xử lý row lỗi.
- Thời gian và giới hạn tài nguyên.
- Trạng thái cuối có thể kiểm chứng.

Không giả định migration chỉ chạy một lần và luôn hoàn tất. Process có thể dừng do deploy timeout, session disconnect, database restart hoặc lỗi dữ liệu giữa chừng.

### 2.5. Không xóa dữ liệu cũ quá sớm

Giữ dữ liệu cũ trong thời gian app mới được xác nhận. Một cột cũ có thể cần cho:
- Rollback binary.
- Consumer chưa nâng cấp.
- Báo cáo/ETL chưa chuyển.
- Đối soát dữ liệu.
- Khôi phục lỗi migration.

Đặt thời điểm contract dựa trên bằng chứng usage và chính sách retention, không dựa trên cảm giác release đã ổn định.

## 3. Ma trận tương thích app và schema

Trước khi triển khai, viết rõ app version nào chạy được trên schema version nào.

Ví dụ:

| Schema | App R10 | App R11 | App R12 |
| --- | --- | --- | --- |
| S20: chỉ có phone | Có | Không | Không |
| S21: thêm phone_e164, giữ phone | Có | Có | Có |
| S22: cả hai cột được duy trì | Có | Có | Có |
| S23: bỏ phone cũ | Không | Không nếu còn đọc phone | Có |

Ma trận minh họa cho thấy:
- S21 là expand schema.
- R11/R12 có thể triển khai trên S21.
- S22 là giai đoạn migrate/backfill.
- Chỉ R12 được thiết kế hoàn toàn với schema S23.
- Contract S23 chỉ an toàn khi R10/R11 và mọi consumer cũ đã ngừng sử dụng phone.

### 3.1. Tương thích ngược và tương thích xuôi

- **Backward compatibility**: app mới hoạt động với schema cũ hoặc schema cũ hơn trong phạm vi đã cam kết.
- **Forward compatibility**: app cũ tiếp tục hoạt động với schema mới.
- **N/N-1 compatibility**: release mới hỗ trợ schema của release hiện tại và release liền trước, hoặc hỗ trợ app version cũ trong giai đoạn rolling.

Không phải hệ thống nào cũng cần mọi tổ hợp. Nhưng cần ghi rõ những tổ hợp được hỗ trợ thay vì suy đoán.

### 3.2. Consumer inventory

Lập danh sách:
- App/service và version.
- Database user/schema.
- Bảng/view/package được truy cập.
- Cột cũ đang được đọc/ghi.
- Tần suất chạy.
- Owner.
- Cách kiểm tra usage.

Có thể dùng SQL audit, application metrics, SQL monitoring, source search và log để tìm consumer. Không dựa riêng vào source repository vì có thể tồn tại SQL động, job ngoài repo hoặc công cụ BI.

## 4. Expand: thêm cấu trúc mới an toàn

Giai đoạn expand tạo nền tảng cho app mới trong khi app cũ còn hoạt động.

### 4.1. Thêm nullable column

Ví dụ:

~~~sql
ALTER TABLE customers
ADD (phone_e164 VARCHAR2(20));
~~~

Cột mới nullable để app cũ có thể tiếp tục INSERT mà không cung cấp giá trị. Kiểm tra storage, datatype, length, character semantics và naming convention.

Không thêm NOT NULL ngay nếu app cũ chưa biết cột mới. Sau khi backfill và app mới đã ghi đầy đủ, có thể xem xét constraint ở giai đoạn sau.

### 4.2. Thêm bảng mới

Nếu thay đổi mô hình dữ liệu lớn, thêm table mới có thể ít rủi ro hơn thay đổi cấu trúc cũ ngay lập tức.

Ví dụ tách địa chỉ khách hàng:

~~~sql
CREATE TABLE customer_addresses (
    address_id   NUMBER GENERATED BY DEFAULT AS IDENTITY,
    customer_id  NUMBER NOT NULL,
    address_type VARCHAR2(30),
    line_1       VARCHAR2(200),
    city         VARCHAR2(100),
    country_code VARCHAR2(2),
    created_at   TIMESTAMP DEFAULT SYSTIMESTAMP,
    CONSTRAINT customer_addresses_pk PRIMARY KEY (address_id),
    CONSTRAINT customer_addresses_customer_fk
        FOREIGN KEY (customer_id)
        REFERENCES customers(customer_id)
);
~~~

Nếu app cũ chỉ dùng cột address trên CUSTOMERS, table mới có thể tồn tại mà không ảnh hưởng app cũ. App mới cần chiến lược đọc/ghi và backfill rõ ràng.

### 4.3. Thêm index

Index có thể được tạo trước khi app mới dùng query mới. Với bảng lớn, đánh giá tùy chọn ONLINE, edition/database release, edition licensing, DML concurrency và thời gian giữ lock. ONLINE không có nghĩa hoàn toàn không có lock hoặc không có tác động tài nguyên.

Ví dụ:

~~~sql
CREATE INDEX customers_phone_e164_ix
ON customers(phone_e164);
~~~

Trên môi trường lớn, xác minh cú pháp và khả năng online index creation theo Oracle release/edition. Đo I/O, redo, undo, TEMP và ảnh hưởng tới DML.

### 4.4. Thêm constraint theo giai đoạn

Nếu dữ liệu cũ chưa đáp ứng constraint, có thể thêm constraint theo cách phù hợp với trạng thái dữ liệu và phiên bản Oracle. Ví dụ, một số constraint hỗ trợ NOVALIDATE để áp dụng với DML mới mà chưa xác nhận toàn bộ dữ liệu cũ:

~~~sql
ALTER TABLE customers
ADD CONSTRAINT customers_phone_e164_ck
CHECK (phone_e164 IS NULL OR LENGTH(phone_e164) BETWEEN 8 AND 20)
ENABLE NOVALIDATE;
~~~

ENABLE NOVALIDATE không có nghĩa dữ liệu cũ đã hợp lệ. Nó áp dụng kiểm tra cho DML mới theo semantics của constraint nhưng chưa validate toàn bộ row hiện hữu. Sau khi làm sạch/backfill, có thể validate:

~~~sql
ALTER TABLE customers
ENABLE VALIDATE CONSTRAINT customers_phone_e164_ck;
~~~

Xác nhận trạng thái trong USER_CONSTRAINTS/ALL_CONSTRAINTS. Kiểm tra semantics và giới hạn cụ thể của constraint type trước khi dùng.

### 4.5. Default và app cũ

Cần phân biệt:
- DEFAULT cho INSERT bỏ qua column.
- DEFAULT ON NULL trong các phiên bản hỗ trợ.
- Giá trị được app chủ động gửi NULL.
- NOT NULL constraint.

Một default không tự động bảo đảm app cũ có semantics đúng. Nếu app cũ gửi NULL tường minh, hành vi có thể khác với việc bỏ column khỏi INSERT. Kiểm thử đúng SQL do app cũ phát ra.

## 5. Migrate: triển khai code tương thích cả cũ và mới

Sau expand, triển khai app version mới với khả năng hiểu trạng thái chuyển tiếp.

### 5.1. Dual-read

App mới có thể đọc cột mới nếu đã có dữ liệu, nếu không thì fallback sang cột cũ:

~~~sql
SELECT COALESCE(phone_e164, phone_legacy) AS phone_value
FROM customers
WHERE customer_id = :customer_id;
~~~

Ví dụ này chỉ minh họa fallback. Nếu hai cột có format khác nhau, không nên coi giá trị cũ và mới tương đương trước khi normalize. App có thể cần parse/normalize theo contract và ghi nhận row chưa migrate.

### 5.2. Dual-write

Trong giai đoạn chuyển tiếp, app mới có thể ghi cả cột cũ và cột mới:

~~~sql
UPDATE customers
SET phone = :legacy_phone,
    phone_e164 = :normalized_phone
WHERE customer_id = :customer_id;
~~~

Mục tiêu là giữ app cũ đọc cột phone và app mới đọc phone_e164 đều thấy dữ liệu nhất quán.

Dual-write cần quy tắc rõ:
- Giá trị canonical nào là nguồn có thẩm quyền?
- Nếu hai giá trị khác nhau, giá trị nào thắng?
- Có normalize ở application hay database?
- Các app version cũ có thể ghi phone sau khi app mới đã ghi phone_e164 không?
- Có consumer nào chỉ cập nhật một trong hai cột không?

Nếu app cũ vẫn ghi cột cũ trong khi app mới ghi hai cột, hai giá trị có thể lệch. Cần trigger/CDC/compatibility service hoặc quy trình đồng bộ để xử lý mọi writer.

### 5.3. Tránh dual-write không kiểm soát

Dual-write giữa hai hệ thống hoặc hai database riêng có thể tạo partial success. Trong cùng một Oracle transaction, cập nhật hai cột trên cùng database có thể atomic; nhưng nếu một write đi qua service khác hoặc message broker, không có atomicity tự động.

Nếu dùng trigger để đồng bộ cột:
- Xác định trigger là nguồn đồng bộ tạm thời hay lâu dài.
- Tránh vòng lặp trigger.
- Kiểm tra bulk load/replication.
- Kiểm tra hiệu năng và lỗi trigger.
- Có kế hoạch bỏ trigger sau contract.
- Đảm bảo app không tự ghi hai giá trị mâu thuẫn.

Trigger có thể bảo vệ writer cũ, nhưng cũng làm logic ghi khó nhìn thấy và khó debug. Dùng có thời hạn và tài liệu rõ.

### 5.4. Feature flag

Feature flag giúp chuyển hành vi theo tỷ lệ hoặc nhóm:
- Đọc cột cũ.
- Đọc cột mới.
- Dual-read.
- Dual-write.
- Chỉ ghi cột mới sau khi consumer cũ đã dừng.

Flag cần được quản lý tập trung và có default an toàn. Không để hai instance cùng version có flag khác nhau mà không hiểu ảnh hưởng dữ liệu.

## 6. Backfill dữ liệu an toàn

Backfill chuyển dữ liệu cũ sang cấu trúc mới. Đây thường là phần dài và dễ gây ảnh hưởng production nhất.

### 6.1. Backfill theo batch

Ví dụ cập nhật phone_e164 từ phone_legacy theo một hàm normalize đã được xác định:

~~~sql
UPDATE customers
SET phone_e164 = normalize_phone(phone)
WHERE phone_e164 IS NULL
  AND customer_id BETWEEN :low_id AND :high_id;
~~~

Đây là ví dụ giả định có function normalize_phone phù hợp. Function phải xử lý null, mã quốc gia, ký tự, extension và dữ liệu lỗi theo contract. Không viết regex đơn giản rồi xem mọi số là hợp lệ.

Chia theo key range hoặc partition để:
- Giới hạn undo/redo mỗi transaction.
- Giảm lock duration.
- Có checkpoint.
- Retry từng chunk.
- Theo dõi tiến độ.
- Không tạo một transaction quá lớn.

### 6.2. Idempotency

Backfill có thể chạy lại mà không ghi đè giá trị đã được app mới cập nhật:

~~~sql
UPDATE customers
SET phone_e164 = normalize_phone(phone)
WHERE phone_e164 IS NULL
  AND customer_id BETWEEN :low_id AND :high_id;
~~~

Điều kiện phone_e164 IS NULL giúp tránh overwrite giá trị đã có, nhưng cần kiểm tra race với app writer. Nếu app đang cập nhật cùng row, dùng transaction/isolation và predicate phù hợp; xem lại số row thực sự được cập nhật.

Idempotent không chỉ là chạy lại không lỗi. Nó phải bảo đảm lần chạy lại không làm sai dữ liệu hoặc ghi đè thông tin mới hơn.

### 6.3. Backfill cạnh tranh với app writes

Trong lúc backfill:
- App cũ có thể cập nhật phone.
- App mới có thể cập nhật cả phone và phone_e164.
- Batch có thể đọc giá trị cũ rồi ghi sau khi app đã ghi giá trị mới.

Để tránh lost update:
- Chỉ cập nhật row còn ở trạng thái cần migrate.
- Dùng optimistic version column nếu phù hợp.
- Dùng predicate kiểm tra giá trị nguồn chưa đổi.
- Dùng khóa/chunk ownership có kiểm soát.
- Có thể tạm dừng writer hoặc chạy catch-up pass.
- So sánh source/target trước khi đánh dấu complete.

Ví dụ kiểm tra nguồn chưa đổi:

~~~sql
UPDATE customers
SET phone_e164 = :normalized_value
WHERE customer_id = :customer_id
  AND phone = :source_value
  AND phone_e164 IS NULL;
~~~

Nếu rowcount bằng 0, row đã đổi hoặc đã được xử lý; đọc lại và quyết định theo logic nghiệp vụ. Không coi zero rows tự động là lỗi.

### 6.4. Checkpoint và tiến độ

Có thể lưu batch progress:

~~~sql
CREATE TABLE migration_progress (
    migration_name VARCHAR2(100) PRIMARY KEY,
    last_customer_id NUMBER,
    rows_processed NUMBER DEFAULT 0,
    updated_at TIMESTAMP DEFAULT SYSTIMESTAMP,
    status VARCHAR2(20)
);
~~~

Checkpoint phải commit cùng với batch data nếu cần bảo đảm progress không đi trước dữ liệu. Nếu checkpoint commit trước data, process crash có thể khiến bỏ sót row. Nếu data commit trước checkpoint, retry có thể chạy lại; vì vậy update phải idempotent.

### 6.5. Giới hạn tài nguyên

Theo dõi:
- Undo tablespace.
- Redo generation và archive volume.
- TEMP.
- CPU/I/O.
- Row lock waits.
- Buffer busy/contention.
- Replication/Data Guard lag.
- Query latency của ứng dụng.
- Batch duration và rows/sec.

Điều chỉnh batch size và concurrency dựa trên đo đạc. Tăng số worker có thể làm throughput giảm do contention.

### 6.6. Dữ liệu không thể chuyển đổi

Không bỏ qua hoặc tự gán giá trị mặc định. Phân loại:
- Thiếu nguồn.
- Sai format.
- Không đủ thông tin để normalize.
- Giá trị ngoài miền nghiệp vụ.
- Trùng lặp hoặc mâu thuẫn.
- Lỗi do encoding.

Lưu row key, raw value, lỗi và hướng xử lý vào bảng quarantine hoặc migration error log. Quy định ai sửa và cách chạy lại row đó.

## 7. Cutover đọc/ghi sang cấu trúc mới

Khi backfill gần hoàn tất, chuyển consumer theo kế hoạch.

### 7.1. Read cutover

Trước khi app chỉ đọc cột mới:
- Backfill đã hoàn tất theo tiêu chí.
- Không còn row hợp lệ nào thiếu target value, trừ trường hợp NULL có ý nghĩa nghiệp vụ.
- Đã xử lý quarantine.
- Các consumer đọc mới đã test.
- Query plan/index đã sẵn sàng.
- Có metrics so sánh giá trị cũ và mới.

Có thể chạy dual-read một thời gian để phát hiện khác biệt:

~~~sql
SELECT COUNT(*) AS mismatch_count
FROM customers
WHERE phone_e164 IS NOT NULL
  AND normalize_phone(phone) <> phone_e164;
~~~

Câu query là ví dụ; xử lý NULL và function semantics cho đúng. Không chạy phép normalize nặng trên toàn bảng production liên tục nếu chưa đánh giá chi phí.

### 7.2. Write cutover

Khi mọi writer đã được nâng cấp:
- App mới ghi cột mới.
- Cột cũ vẫn được duy trì trong rollback window nếu cần.
- Writer cũ phải được ngừng hoặc được compatibility layer hỗ trợ.
- Theo dõi mọi thay đổi chỉ có ở cột cũ.
- Xác nhận batch/ETL không ghi format cũ.

Không bỏ dual-write cho tới khi mọi consumer phụ thuộc cột cũ đã chuyển.

### 7.3. Đóng băng thời điểm cutover

Ghi nhận:
- Release ID.
- Schema version.
- Thời điểm bắt đầu/kết thúc.
- Feature flag state.
- Backfill checkpoint.
- Số row mismatch.
- Consumer đã chuyển.
- Error rate và latency.
- Owner phê duyệt.

Điểm này giúp tái dựng trạng thái nếu cần rollback hoặc điều tra sau release.

## 8. Contract: loại bỏ cấu trúc cũ

Contract là bước phá vỡ tương thích ngược. Chỉ thực hiện sau khi app/consumer cũ đã rời hệ thống và rollback window đã đóng.

### 8.1. Điều kiện trước khi DROP

- Không còn code chạy đọc/ghi cột cũ.
- Batch job và report đã chuyển.
- Không còn SQL động hoặc database package tham chiếu cột cũ.
- Không còn consumer bên ngoài.
- Backfill và reconciliation đạt tiêu chí.
- App version mới ổn định.
- Không cần binary rollback về version phụ thuộc cột cũ.
- Backup/recovery plan đã được xác nhận.
- Có change approval và maintenance plan.

### 8.2. Drop column

~~~sql
ALTER TABLE customers
DROP COLUMN phone;
~~~

Đây là DDL có tác động không thể coi như một thao tác DML có thể rollback. Tùy table size, dependency, edition và release, thao tác có thể cần thời gian/lock và có ảnh hưởng storage. Đánh giá trước bằng clone hoặc môi trường staging.

Có thể cân nhắc SET UNUSED rồi DROP UNUSED COLUMNS trong một số tình huống để tách việc ngừng sử dụng khỏi việc giải phóng storage:

~~~sql
ALTER TABLE customers
SET UNUSED (phone);

ALTER TABLE customers
DROP UNUSED COLUMNS;
~~~

SET UNUSED làm column không còn truy cập được bằng tên và là thay đổi phá vỡ code cũ ngay lập tức. Nó không phải cách giữ tương thích cho rollback. Chỉ dùng khi đã đủ điều kiện contract.

### 8.3. Rename column có an toàn không?

~~~sql
ALTER TABLE customers
RENAME COLUMN phone TO phone_legacy;
~~~

Rename thường làm code cũ tham chiếu tên cũ lỗi ngay. Trong rolling deployment, dùng add-new-column → migrate → switch consumers → drop-old-column thay vì rename trực tiếp.

### 8.4. Drop constraint/index

Trước khi xóa:
- Xác định query, foreign key, package và report phụ thuộc.
- Kiểm tra index có được dùng bởi constraint hay không.
- Kiểm tra execution plan sau khi bỏ.
- Xác nhận app không còn cần semantics cũ.
- Lưu DDL và trạng thái trước thay đổi.

## 9. Ví dụ hoàn chỉnh: đổi cột phone sang phone_e164

Giả sử bảng CUSTOMERS hiện có PHONE VARCHAR2(40). Release mới cần PHONE_E164 VARCHAR2(20).

### 9.1. Trạng thái ban đầu S100/R10

~~~sql
CREATE TABLE customers (
    customer_id NUMBER PRIMARY KEY,
    phone       VARCHAR2(40)
);
~~~

App R10:
- INSERT/UPDATE PHONE.
- SELECT PHONE.
- Không biết PHONE_E164.

### 9.2. Expand schema S101

~~~sql
ALTER TABLE customers
ADD (phone_e164 VARCHAR2(20));
~~~

R10 vẫn hoạt động vì column mới nullable và không làm thay đổi contract cũ.

### 9.3. Deploy R11 dual-read/dual-write

R11:
- Đọc PHONE_E164 nếu có.
- Nếu chưa có thì fallback PHONE và normalize.
- Ghi PHONE và PHONE_E164 trong cùng transaction.
- Ghi metric khi fallback được dùng.

Nếu R10 vẫn chạy và chỉ ghi PHONE, R11 hoặc compatibility mechanism phải bảo đảm PHONE_E164 được cập nhật sau các write đó. Có thể dùng trigger tạm thời hoặc catch-up process; phải xác định một nguồn chuẩn.

### 9.4. Backfill

~~~sql
UPDATE customers
SET phone_e164 = normalize_phone(phone)
WHERE phone_e164 IS NULL
  AND customer_id BETWEEN :low_id AND :high_id;
~~~

Commit theo chunk. Ghi checkpoint và quarantine các row normalize thất bại. Chạy catch-up pass sau khi R10 đã ngừng để xử lý các row được cập nhật trong quá trình backfill.

### 9.5. Reconcile

~~~sql
SELECT COUNT(*) AS missing_count
FROM customers
WHERE phone IS NOT NULL
  AND phone_e164 IS NULL;
~~~

~~~sql
SELECT COUNT(*) AS mismatch_count
FROM customers
WHERE phone_e164 IS NOT NULL
  AND normalize_phone(phone) <> phone_e164;
~~~

Các query trên cần điều chỉnh cho NULL, số không hợp lệ và semantics normalize. Chỉ đánh dấu complete khi mọi row được phân loại và mismatch còn lại nằm trong exception được phê duyệt.

### 9.6. Deploy R12 chỉ đọc/ghi cột mới

R12:
- Đọc PHONE_E164.
- Ghi PHONE_E164.
- Có thể vẫn dual-write PHONE trong rollback window.
- Không còn fallback sang PHONE sau khi đã chứng minh coverage.

Đợi mọi R10/R11 instance, batch và external consumer phụ thuộc PHONE dừng hoạt động.

### 9.7. Contract S102

Sau rollback window và consumer inventory xác nhận không còn phụ thuộc:

~~~sql
ALTER TABLE customers
DROP COLUMN phone;
~~~

Deploy R13 hoặc migration riêng. Sau contract, không thể rollback binary về R10/R11 mà không phục hồi lại schema cũ hoặc có compatibility layer mới.

## 10. DDL Oracle và transaction boundary

Oracle DDL có implicit commit theo quy tắc database. Điều này ảnh hưởng cách viết migration và cách xử lý lỗi.

### 10.1. DDL không giống DML

Ví dụ:

~~~sql
UPDATE customers
SET status = 'ACTIVE'
WHERE customer_id = 100;

ALTER TABLE customers
ADD (new_flag CHAR(1));

ROLLBACK;
~~~

DDL có thể commit transaction đang mở trước khi thực thi và commit sau khi thực hiện thành công theo semantics Oracle. UPDATE trước DDL có thể đã được commit; ROLLBACK sau đó không đưa trạng thái về ban đầu.

### 10.2. @Transactional không làm DDL rollback được

Không giả định:

~~~java
@Transactional
public void migrate() {
    jdbcTemplate.execute("ALTER TABLE customers ADD new_flag CHAR(1)");
    jdbcTemplate.update("UPDATE customers SET new_flag = 'N'");
    throw new IllegalStateException("force rollback");
}
~~~

sẽ hoàn tác cả ALTER TABLE. DDL đã có implicit commit. DML sau DDL có thể thuộc transaction khác và có thể rollback theo transaction semantics, nhưng schema change vẫn tồn tại.

### 10.3. Tách migration DDL và DML

Thiết kế migration:
- DDL nhỏ, có precondition/postcondition.
- Data backfill chạy riêng theo batch.
- Migration metadata ghi rõ bước đã hoàn tất.
- Có script kiểm tra trạng thái nếu process dừng giữa chừng.
- Không dựa vào transaction rollback để undo DDL.
- Có forward-fix hoặc compensating action khi cần.

### 10.4. Flyway và Liquibase

Các công cụ migration giúp version hóa và áp dụng thay đổi có thứ tự. Tuy nhiên, khả năng transaction của migration phụ thuộc database và loại câu lệnh. Với Oracle DDL, công cụ không thể biến implicit commit thành transaction rollback nguyên tử.

Kiểm tra:
- Version tool.
- Transaction mode của migration.
- Statement nào là DDL.
- Migration có thể chạy lại không.
- Schema history table có phản ánh trạng thái đúng không.
- Cách phục hồi khi migration dừng giữa chừng.

Không chạy migration tự động đồng thời từ mọi application replica khi khởi động. Dùng một migration job/owner có kiểm soát để tránh race và lock.

## 11. Constraint và index trong rolling deployment

### 11.1. Thêm NOT NULL

Nếu app cũ không gửi column mới, thêm NOT NULL ngay có thể làm INSERT cũ thất bại. Trình tự an toàn thường là:
1. Thêm nullable column.
2. Deploy code ghi giá trị mới.
3. Backfill dữ liệu cũ.
4. Kiểm tra không còn NULL ngoài trường hợp được phép.
5. Thêm/validate constraint.
6. Chỉ sau đó mới dựa vào invariant mới trong code.

### 11.2. CHECK constraint

Dùng constraint để bảo vệ dữ liệu tại database, không chỉ validation ở app. Nhưng cần đảm bảo app cũ không tạo dữ liệu vi phạm. Có thể triển khai NOVALIDATE rồi VALIDATE theo kế hoạch nếu semantics phù hợp.

### 11.3. Foreign key

Thêm foreign key có thể làm DML của app cũ thất bại nếu dữ liệu tham chiếu không hợp lệ. Kiểm tra dữ liệu trước, thêm constraint theo giai đoạn và validate sau.

### 11.4. Index mới

Index có thể làm DML chậm hơn do thêm maintenance cost. Tạo index trước khi app mới bật query, nhưng đo thời gian build, redo, I/O, lock và ảnh hưởng Data Guard. Nếu dùng ONLINE, kiểm tra giới hạn và điều kiện cụ thể của Oracle release/edition.

## 12. Thay đổi datatype an toàn

Đổi datatype trực tiếp có thể gây lỗi hoặc mất dữ liệu. Ví dụ VARCHAR2 sang NUMBER:
- Có row không parse được.
- Leading zeros có thể có ý nghĩa.
- Precision/scale có thể không đủ.
- App cũ vẫn gửi string.
- Index/constraint phụ thuộc cột.

Cách an toàn thường là:
1. Thêm column mới với datatype đích.
2. Deploy code dual-read/write.
3. Backfill bằng conversion có validation.
4. Quarantine giá trị không hợp lệ.
5. Đối soát.
6. Chuyển consumer sang column mới.
7. Đóng rollback window.
8. Drop column cũ sau cùng.

Với datatype tăng độ rộng hoặc thay đổi semantics, vẫn phải đánh giá NLS, rounding, truncation, nullability và index.

## 13. Edition-Based Redefinition (EBR)

Oracle Edition-Based Redefinition là kỹ thuật nâng cấp ứng dụng/schema online cho những thay đổi phức tạp hơn, đặc biệt khi cần nhiều edition cùng tồn tại trong một database.

EBR sử dụng các khái niệm như:
- Editions.
- Editioned objects.
- Editioning views.
- Crossedition triggers.
- Code deployment theo edition.
- Service/session được gắn với edition phù hợp.

### 13.1. Editioning view

Editioning view cung cấp một lớp view ổn định cho code theo edition, giúp thay đổi cấu trúc table underlying mà code edition khác vẫn có thể sử dụng view contract của nó.

### 13.2. Crossedition trigger

Crossedition trigger có thể đồng bộ dữ liệu giữa biểu diễn cũ và mới trong quá trình chuyển đổi edition. Trigger cần thiết kế để tránh loop, xử lý concurrency và bảo đảm consistency.

### 13.3. Khi nào cân nhắc EBR?

- Ứng dụng lớn cần online upgrade.
- Có nhiều PL/SQL object cần thay đổi đồng bộ.
- Cần chạy old/new edition trong một khoảng chuyển tiếp.
- Đội DBA/DevOps có kinh nghiệm quản lý edition.
- Phiên bản Oracle và license/feature support đáp ứng yêu cầu.

EBR không phải giải pháp tự động cho mọi schema change. Kiểm tra object type, editionability, restrictions và runbook của release đang dùng.

## 14. Database API và view compatibility

Một cách giảm coupling là không để mọi ứng dụng truy cập trực tiếp table schema.

### 14.1. View như contract

Có thể cung cấp view giữ tên/shape cũ trong khi table underlying đã thay đổi. App cũ truy cập view, app mới dùng API/view mới.

~~~sql
CREATE OR REPLACE VIEW customer_legacy_v AS
SELECT customer_id,
       phone
FROM customers;
~~~

View phải bảo toàn semantics cũ. Nếu cột underlying bị đổi tên hoặc bỏ, view cần được điều chỉnh hoặc giữ nguồn dữ liệu cũ cho tới khi consumer rời đi.

### 14.2. Stored procedure/package API

Package PL/SQL có thể che giấu thay đổi table structure:
- App gọi procedure thay vì DML trực tiếp.
- Package duy trì contract ổn định.
- Schema có thể thay đổi phía sau package.
- Versioned package/API có thể hỗ trợ transition.

Nhưng package cũng có consumer và dependency. Compile invalid hoặc thay đổi signature vẫn có thể phá app cũ.

### 14.3. Tránh shared-table coupling

Nếu nhiều team tự truy cập bảng của nhau, thay đổi schema rất khó điều phối. Tạo data access API, views hoặc service boundary giúp kiểm soát contract và consumer inventory.

## 15. Message/event schema cũng cần tương thích

Ứng dụng thường trao đổi JSON, message hoặc event. Database schema có thể tương thích nhưng event contract lại không.

Nguyên tắc:
- Thêm field optional trước.
- Consumer cũ bỏ qua field không biết nếu serializer hỗ trợ.
- Không đổi ý nghĩa field đang tồn tại.
- Không tái sử dụng enum value cũ với nghĩa mới.
- Version event khi có thay đổi phá vỡ.
- Dùng tolerant reader có giới hạn, không âm thầm chấp nhận dữ liệu sai.
- Có compatibility test producer/consumer N và N-1.

Nếu app mới ghi format JSON mà app cũ không parse được, rollback binary vẫn thất bại dù database column không đổi.

## 16. Testing schema compatibility

Kiểm thử phải bao gồm các tổ hợp app/schema quan trọng trong compatibility window.

### 16.1. Compatibility matrix test

Ví dụ:

| Test | Schema S21 | Schema S22 |
| --- | --- | --- |
| App R10 read/write | PASS yêu cầu | PASS trong transition |
| App R11 dual-read/write | PASS | PASS |
| App R12 new-column only | Chỉ sau khi backfill | PASS |
| Batch R10 | PASS | PASS cho tới khi retire |
| Reporting consumer | PASS | PASS sau khi query chuyển |

Không test chỉ R12 với schema cuối. Cần test app cũ trên schema expand và app mới trên schema transition.

### 16.2. Migration test

Trên clone có dữ liệu gần production:
- Chạy DDL expand.
- Chạy backfill.
- Dừng giữa chừng rồi resume.
- Chạy lại migration để xác nhận idempotency.
- Test concurrent app writes.
- Test dữ liệu invalid.
- Test lock/timeout.
- Test rollback/forward-fix.
- Test contract chỉ khi đủ điều kiện.

### 16.3. Load và performance test

Đo:
- DDL duration.
- Lock wait.
- DML latency.
- Backfill rows/sec.
- Redo/undo growth.
- Index build cost.
- Query plan.
- Connection pool.
- Data Guard transport/apply lag.
- Replication/CDC lag.

### 16.4. Failure injection

Diễn tập:
- Migration job bị kill giữa batch.
- Database restart.
- Connection timeout.
- Một chunk có dữ liệu không parse được.
- App mới rollback trong lúc backfill.
- Một consumer cũ vẫn ghi.
- Scheduler job chạy trùng.
- Index build thất bại.
- Feature flag bị bật nhầm.
- Contract migration bị gọi khi consumer cũ chưa dừng.

Mỗi kịch bản cần xác định trạng thái database sau lỗi và cách tiếp tục.

## 17. Deployment orchestration

### 17.1. Một migration owner

Chọn một job hoặc pipeline chịu trách nhiệm chạy schema migration. Các replica ứng dụng không nên tự đua nhau thực hiện DDL lúc startup.

Migration owner cần:
- Distributed lock hoặc cơ chế single runner.
- Migration history.
- Precondition/postcondition.
- Logging.
- Timeout.
- Approval cho destructive migration.
- Quyền database tối thiểu phù hợp.

### 17.2. Triển khai theo thứ tự

Một thứ tự phổ biến:
1. Backup/checkpoint theo policy.
2. Expand schema.
3. Deploy app mới ở chế độ tương thích.
4. Xác nhận instance health.
5. Backfill theo batch.
6. Reconcile.
7. Chuyển feature flag/traffic.
8. Theo dõi compatibility window.
9. Retire consumer cũ.
10. Contract trong release riêng.

Một số hệ thống cần deploy app hỗ trợ dual-write trước khi backfill; hệ thống khác cần schema expand trước app. Chọn thứ tự theo contract code và test, nhưng bảo đảm mỗi bước trung gian đều chạy được.

### 17.3. Readiness và liveness

Readiness nên kiểm tra app có thể phục vụ traffic với schema hiện tại. Tránh readiness chỉ kiểm tra database connection mà không phát hiện schema version không tương thích.

Có thể:
- Kiểm tra schema capability/version.
- Kiểm tra cột/index/package bắt buộc.
- Kiểm tra quyền.
- Fail startup nếu schema quá cũ và app không hỗ trợ.
- Cho phép app mới chạy trên schema expand nhưng chưa contract.

Liveness không nên phụ thuộc vào một truy vấn nặng hoặc backfill hoàn tất nếu process vẫn khỏe và có thể phục vụ request phù hợp.

### 17.4. Migration lock và concurrent deployment

Nếu hai pipeline deploy cùng lúc:
- Có thể cùng chạy migration.
- Một pipeline có thể contract trong khi pipeline khác đang deploy app cũ.
- Migration history có thể bị race.
- DDL lock có thể chặn DML.

Sử dụng release lock/change coordination và single migration executor. Chỉ một release owner được phép thay schema tại một thời điểm.

## 18. Rollback và forward-fix

### 18.1. Binary rollback

Quay app về artifact trước chỉ an toàn nếu schema vẫn tương thích với app cũ. Trong expand/migrate, giữ cột cũ để hỗ trợ binary rollback.

### 18.2. Schema rollback

Không phải migration nào cũng có inverse:
- Thêm nullable column: có thể giữ nguyên khi rollback app.
- Thêm index: có thể drop nếu không cần.
- Backfill: có thể giữ dữ liệu mới, không nhất thiết phải xóa.
- Normalize dữ liệu: inverse có thể không khôi phục raw representation.
- Drop/rename column: cần backup/restore hoặc compatibility layer.
- Chuyển đổi lossy: không thể khôi phục đầy đủ chỉ bằng SQL ngược.

### 18.3. Forward-fix

Khi schema đã thay đổi và dữ liệu mới đã phát sinh, forward-fix có thể an toàn hơn rollback:
- Sửa code mới.
- Giữ schema additive.
- Sửa dữ liệu lỗi có kiểm soát.
- Bổ sung index/constraint.
- Tạo migration tiếp theo để khắc phục.

Không ép database quay lại trạng thái cũ nếu điều đó làm mất giao dịch hợp lệ.

### 18.4. Restore point/PITR

Flashback Database hoặc PITR có thể đưa database về trước migration, nhưng có thể loại bỏ transaction sau target. Cần xác định RPO, dữ liệu phát sinh sau target, Data Guard và service cutover trước khi dùng. Đây là database recovery, không phải rollback app thông thường.

## 19. Giám sát sau triển khai

Theo dõi trong suốt compatibility window:
- App version theo instance.
- Schema migration version.
- Số instance cũ còn hoạt động.
- Query/error rate theo SQL_ID.
- ORA-00904 invalid identifier.
- ORA-01400 cannot insert NULL.
- ORA-02291/02292 constraint violations.
- ORA-00054 resource busy.
- DDL lock wait.
- Backfill progress và row errors.
- Old/new column mismatch.
- Index status.
- Data Guard lag.
- Queue/CDC lag.
- Connection pool.
- Scheduled job failures.

Tạo metric cho fallback read và legacy-column write. Khi metric về 0 trong một khoảng thời gian đủ dài và consumer inventory xác nhận, mới xem xét contract.

## 20. Runbook triển khai thay đổi schema

### Trước release

1. Xác định schema và consumer inventory.
2. Vẽ ma trận app/schema compatibility.
3. Chọn expand/migrate/contract steps.
4. Kiểm tra DDL implicit commit.
5. Kiểm tra lock, storage, redo/undo và Data Guard.
6. Viết migration và pre/postcondition.
7. Viết backfill chunk/checkpoint.
8. Xác định quarantine và reconciliation.
9. Chuẩn bị rollback/forward-fix.
10. Test trên clone với dữ liệu đại diện.
11. Phê duyệt destructive contract riêng.

### Trong release

1. Chạy expand migration một lần.
2. Xác nhận schema capability.
3. Deploy app tương thích.
4. Chạy smoke test.
5. Bật dual-read/write theo feature flag.
6. Chạy backfill theo batch.
7. Theo dõi error, lag và resource.
8. Reconcile old/new data.
9. Chuyển read path và write path.
10. Ghi nhận release state.

### Sau release

1. Xác nhận mọi app instance mới.
2. Xác nhận batch/consumer đã chuyển.
3. Theo dõi legacy access.
4. Giữ schema cũ trong rollback window.
5. Đóng rollback window có phê duyệt.
6. Chạy contract migration riêng.
7. Kiểm tra object/index/constraint.
8. Cập nhật schema/API documentation.
9. Lưu evidence và release record.

## 21. Checklist thiết kế compatibility

- [ ] Đã xác định tất cả app/job/consumer dùng schema.
- [ ] Đã biết version cũ nhất có thể còn chạy.
- [ ] Đã lập ma trận app/schema.
- [ ] Thay đổi phá vỡ được tách khỏi expand.
- [ ] Cột mới/table mới được thêm theo cách app cũ chịu được.
- [ ] App mới xử lý row chưa backfill.
- [ ] Dual-write có nguồn dữ liệu canonical và xử lý conflict.
- [ ] Backfill có chunk, checkpoint và retry.
- [ ] Backfill không ghi đè update mới hơn.
- [ ] Dữ liệu lỗi được quarantine.
- [ ] Có reconciliation count/aggregate/hash.
- [ ] Constraint được thêm và validate theo giai đoạn.
- [ ] Index build được kiểm thử.
- [ ] DDL implicit commit đã được tính đến.
- [ ] Migration chỉ chạy từ một owner.
- [ ] Binary rollback vẫn tương thích trong rollback window.
- [ ] Event/message contract cũng tương thích.
- [ ] Không còn consumer cũ trước khi contract.
- [ ] Contract có approval và recovery plan.
- [ ] Có metrics xác nhận legacy usage đã về 0.

## 22. Bài tập tự luyện

1. Vì sao rolling deployment cần schema tương thích nhiều phiên bản?
2. Phân biệt backward compatibility và forward compatibility.
3. Vẽ ba giai đoạn expand, migrate và contract.
4. Lập ma trận tương thích giữa app R10/R11/R12 và schema S20/S21/S22.
5. Vì sao thêm nullable column thường an toàn hơn rename column?
6. Khi nào thêm NOT NULL có thể làm app cũ lỗi?
7. Phân biệt schema migration và data migration.
8. Vì sao backfill cần checkpoint và idempotency?
9. Thiết kế dual-read khi cột mới chưa được backfill hết.
10. Nêu rủi ro khi app cũ chỉ ghi cột legacy trong lúc app mới dual-write.
11. Khi nào cần trigger đồng bộ hai cột?
12. Vì sao trigger compatibility nên có thời hạn?
13. Thiết kế backfill theo key range cho bảng hàng trăm triệu row.
14. Làm thế nào tránh lost update giữa backfill và app write?
15. Vì sao checkpoint nên commit cùng batch data?
16. Thiết kế quarantine cho dữ liệu không normalize được.
17. Viết query đối soát missing và mismatch giữa hai cột.
18. Khi nào được chuyển read path sang column mới?
19. Vì sao không DROP column cũ ngay sau khi app mới deploy?
20. Phân biệt DROP COLUMN và SET UNUSED.
21. Vì sao Oracle DDL implicit commit làm migration rollback khác DML rollback?
22. Flyway/Liquibase có thể rollback Oracle DDL tự động không?
23. Thiết kế quy trình thêm CHECK constraint bằng NOVALIDATE rồi VALIDATE.
24. Những gì cần kiểm tra khi tạo index ONLINE?
25. Khi nào cân nhắc Edition-Based Redefinition?
26. Editioning view và crossedition trigger có vai trò gì?
27. Làm thế nào giữ event/message contract tương thích N/N-1?
28. Khi nào forward-fix an toàn hơn schema rollback?
29. Thiết kế failure-injection test cho backfill bị dừng giữa chừng.
30. Lập runbook expand-migrate-contract cho việc đổi một column đang được nhiều service sử dụng.

**Triển khai schema tương thích nhiều phiên bản là quá trình chuyển đổi có kiểm soát qua một khoảng thời gian mà app cũ và mới cùng tồn tại.** Hãy thêm cấu trúc mới trước, triển khai code đọc/ghi tương thích, backfill theo batch có checkpoint, đối soát dữ liệu, chuyển toàn bộ consumer rồi mới contract. Với Oracle, DDL có implicit commit nên cần migration nhỏ, precondition/postcondition, forward-fix và recovery plan riêng; binary rollback chỉ an toàn khi schema vẫn giữ contract mà app cũ cần.

